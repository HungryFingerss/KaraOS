# P0.B2 Plan v1 — Async FAISS Rebuild Correctness (Option (a) 5-surface refactor + sentinel)

**Phase 0 base:** `tests/p0_b2_faiss_async_rebuild_audit.md` (auditor APPROVED 2026-05-21 with Option (a) locked + all 3 open questions adjudicated to architect's leans + Q5 framing imprecision noted + 4 anticipated Plan v1 precision items predicted).

**Plan v1 absorbs:**
- **Q1 LOCK:** Option (a) — 5-surface refactor + sentinel discipline (both layers shipped).
- **Q2 LOCK:** `cursor.lastrowid` post-INSERT for pending-add row_id capture.
- **Q3 LOCK:** DB UPDATE batch AFTER `_index_lock` release (matches sync precedent at `core/db.py:1066-1079`).
- **Q5 framing correction:** acknowledge Phase 0 §6's "+11.1% SLIGHT-DRIFT-UP edge" was off — `+11.1% < 15%` = **ON-TARGET**, NOT slight-drift. Band lock per auditor verdict: **8-14 mid 11** (intermediate band for high-complexity-per-site cycles).
- **P1-P4 anticipated precision items** absorbed proactively at §2-§4 below.
- **Grep-baseline-before-drafting** discipline applied at Phase 0; baseline counts cited per auditor's standing observation locked at P0.B1 closure.

All 5 D-decisions stand. Plan v1 enumerates the contracts + Pass-2 grep enumeration + ordering invariants explicitly.

---

## §1. P1 — Pass-2 grep enumeration (LOCKED)

### §1.1 — `_pending_adds_during_rebuild` write/read sites (7 in production, 1 in test)

| File | Line | Pattern | Migration |
|---|---|---|---|
| `core/db.py` | 104 | `# list of (vec, person_id)` declaration comment | Update comment → `# list of (vec, person_id, row_id)` |
| `core/db.py` | 707 | `_pending_adds_during_rebuild.append((emb[0].copy(), person_id))` | Append 3-tuple: `(emb[0].copy(), person_id, _row_id)` where `_row_id = cursor.lastrowid` captured immediately after INSERT |
| `core/db.py` | 972 | `self._pending_adds_during_rebuild = []` (Phase 1 init) | No change — list assignment |
| `core/db.py` | 985 | `self._pending_adds_during_rebuild = []` (Phase 2 exception cleanup) | No change |
| `core/db.py` | 993 | `for vec, person_id in self._pending_adds_during_rebuild:` (Phase 3 unpack) | 3-tuple unpack: `for vec, person_id, row_id in self._pending_adds_during_rebuild:` |
| `core/db.py` | 1000 | `self._pending_adds_during_rebuild = []` (Phase 3 cleanup) | No change |
| `tests/test_faiss_async_rebuild.py` | 183 | `assert db._pending_adds_during_rebuild == []` | No change — empty-list compare, no shape dependency |

### §1.2 — `add_embedding` call sites (43 callers; ALL backward-compat preserved)

All 43 `add_embedding` callers use the public API `db.add_embedding(person_id, emb, source, ...)`. The change at line 707 happens INSIDE `add_embedding`'s method body. Callers don't see `_pending_adds_during_rebuild` directly. **Zero caller migrations needed.**

### §1.3 — `_mark_faiss_dirty` / `_clear_faiss_dirty` call sites (existing + new)

Existing sites (P0.5 + P0.X heritage):
- `core/db.py:372,379` — method definitions
- `core/db.py:417` — clear on boot reconciliation success
- `core/db.py:711,796,874,925,1778` — mark on FAISS write failure in 5 paired-write paths
- AST scans in `tests/test_faiss_atomicity_invariants.py` (lines 14,97,134,137,182,352,365)

**NEW sites for P0.B2 D4:**
- `core/db.py:~957-1008` — TWO new calls inside `rebuild_faiss_async`:
  - `_mark_faiss_dirty()` at the START of Phase 3 (sentinel set BEFORE in-memory swap)
  - `_clear_faiss_dirty()` after successful Phase 4 disk save

### §1.4 — Helper function direct callers (D1 + D2 signature changes)

`_fetch_all_embeddings_for_index` direct callers: **1 site** (`rebuild_faiss_async` Phase 1 at line 971). Plus possibly test mocks — Pass-2 grep below.

`_build_faiss_from_snapshot` direct callers: **1 production site** (`rebuild_faiss_async` Phase 2 at line 977-981) + tests in `tests/test_faiss_async_rebuild.py` (5 tests, some may call directly — confirm at impl time).

---

## §2. P2 — D4 sentinel ordering atomically specified (LOCKED)

### §2.1 — ORDERING INVARIANT (locked at call site comment)

The async path's `rebuild_faiss_async` MUST follow this sequence exactly:

```python
async def rebuild_faiss_async(self, loop):
    if not self._rebuild_lock.acquire(blocking=False):
        return

    try:
        # Phase 1 — snapshot under lock
        with self._index_lock:
            vecs, person_ids, row_ids = self._fetch_all_embeddings_for_index()   # D1: 3-tuple
            self._pending_adds_during_rebuild = []
            self._rebuild_in_progress = True

        snapshot = (vecs, person_ids, row_ids)

        # Phase 2 — build new index in worker thread (slow, no lock held)
        try:
            new_index, new_idx_to_person, snapshot_idx_updates = await loop.run_in_executor(
                None, self._build_faiss_from_snapshot, snapshot,
            )                                                                     # D2: 3-tuple return
        except Exception:
            with self._index_lock:
                self._rebuild_in_progress = False
                self._pending_adds_during_rebuild = []
            raise

        # ── ORDERING INVARIANT (P0.B2 D4, locked at Plan v1 §2.1) ────────────
        # _mark_faiss_dirty() MUST run BEFORE Phase 3 swap. The sentinel
        # marks the disk file + DB state as potentially-divergent during the
        # rebuild window; if any step between here and _clear_faiss_dirty()
        # crashes (Phase 3 swap exception, DB UPDATE crash, _save_faiss
        # failure), the next boot's _load_faiss reads the sentinel and
        # triggers _rebuild_faiss() to reconcile.
        #
        # Mirror of P0.5 sync paired-write pattern: SQL durable + FAISS
        # derived + sentinel as crash-recovery beacon.
        # ─────────────────────────────────────────────────────────────────
        self._mark_faiss_dirty()

        # Phase 3 — replay pending adds, swap atomically (under lock, fast)
        idx_updates: list[tuple[int, int]] = list(snapshot_idx_updates)   # snapshot rows
        with self._index_lock:
            for vec, person_id, row_id in self._pending_adds_during_rebuild:   # D3: 3-tuple
                new_idx = new_index.ntotal
                new_index.add(vec.reshape(1, -1))
                new_idx_to_person[new_idx] = person_id
                idx_updates.append((new_idx, row_id))                          # capture pending row_id
            self.index = new_index
            self._idx_to_person = new_idx_to_person
            self._rebuild_in_progress = False
            self._pending_adds_during_rebuild = []

        # ── DB UPDATE batch AFTER _index_lock release (Q3 LOCK; matches
        #    sync precedent at core/db.py:1075-1079) ─────────────────────
        for new_idx, row_id in idx_updates:
            self._conn.execute(
                "UPDATE embeddings SET faiss_idx = ? WHERE id = ?",
                (new_idx, row_id),
            )
        self._conn.commit()

        # Phase 4 — persist to disk (lock-free; no readers depend on file content)
        try:
            await loop.run_in_executor(None, self._save_faiss)
        except Exception as e:
            print(f"[FaceDB] async save_faiss failed (index in memory OK): {e!r}")
            # Sentinel stays set; next boot will reconcile.
            raise

        # Sentinel CLEAR only after BOTH DB UPDATE commit AND _save_faiss success.
        self._clear_faiss_dirty()
    finally:
        self._rebuild_lock.release()
```

### §2.2 — ORDERING INVARIANT properties

1. **`_mark_faiss_dirty()` BEFORE Phase 3 swap.** Sentinel set while rebuild is in flight.
2. **In-memory swap UNDER `_index_lock`.** `recognize()` either sees the OLD state OR the NEW state — never half-and-half.
3. **DB UPDATE batch AFTER `_index_lock` release.** Same lock surface as sync precedent; doesn't extend lock-hold time.
4. **`_save_faiss()` AFTER DB UPDATE commit.** Disk file matches the durable DB state.
5. **`_clear_faiss_dirty()` LAST, only on full success.** Crash anywhere between mark and clear → sentinel stays set → next boot reconciles via `_rebuild_faiss()`.

### §2.3 — Crash safety analysis per step

| Crash at | DB state | Disk faiss.index | In-memory | Sentinel | Boot recovery |
|---|---|---|---|---|---|
| Phase 2 build | stale `faiss_idx` | unchanged | unchanged | NOT set yet | counts match → no rebuild needed (rebuild aborted cleanly) |
| Phase 3 swap (mid-replay) | stale | unchanged | partial — _rebuild_in_progress=True | **SET** | sentinel triggers `_rebuild_faiss()` ✓ |
| DB UPDATE (mid-batch) | partial-new | unchanged | new ✓ | **SET** | sentinel triggers `_rebuild_faiss()` ✓ |
| `_save_faiss` (mid-write or post-write) | new ✓ | partial/new | new ✓ | **SET** | sentinel triggers `_rebuild_faiss()` ✓ |
| After `_clear_faiss_dirty()` | new ✓ | new ✓ | new ✓ | cleared | normal boot — no rebuild ✓ |

Every crash point is covered by the sentinel mechanism.

---

## §3. P3 — D5 crash-injection test scenarios (LOCKED)

### §3.1 — Test 1: prune→restart→recognize HAPPY PATH (closes Bug 2)

**Test name:** `test_prune_async_then_restart_recognizes_known_person`

**Surface:** new test in `tests/test_faiss_sql_atomicity.py` (slow-tier — uses real FAISS index).

**Scenario:**
1. Create `FaceDB` instance against `tmp_path/"faces"`.
2. Insert 10 persons via `add_embedding` (mix of stranger + known person_types). 5 strangers are aged > `STRANGER_TTL_DAYS` (via direct UPDATE on `persons.last_seen`); 5 known.
3. Call `await db.prune_old_strangers_async(loop)` → deletes 5 strangers + rebuilds FAISS via the (now fixed) async path.
4. Capture embeddings of 5 remaining known persons before restart.
5. Close `FaceDB` instance.
6. Open new `FaceDB` instance against same `tmp_path/"faces"` (simulates process restart).
7. For each of 5 known persons: `recognize()` with their embedding → MUST return `(person_id, name, score >= RECOGNITION_THRESHOLD)`, NOT `(None, None, score)`.

**Pre-fix behavior:** at least some recognitions return `(None, None, score)` because DB `faiss_idx` is stale, `_idx_to_person` is built with wrong mapping, recognize routes to wrong pids.

**Post-fix behavior:** all 5 recognitions succeed (DB UPDATE corrected `faiss_idx` during async rebuild).

### §3.2 — Test 2: async rebuild crash mid-DB-UPDATE → sentinel triggers boot reconciliation

**Test name:** `test_prune_async_crash_mid_db_update_recovers_via_sentinel`

**Surface:** new test in `tests/test_faiss_sql_atomicity.py` (slow-tier).

**Scenario:**
1. Create `FaceDB` instance against `tmp_path/"faces"`.
2. Insert 10 persons (5 strangers stale, 5 known).
3. Monkeypatch `_conn.execute` to raise `sqlite3.OperationalError("disk I/O error")` on the 3rd call to "UPDATE embeddings SET faiss_idx" (mid-batch crash).
4. `await db.prune_old_strangers_async(loop)` raises → caught at outer level.
5. Verify sentinel file exists on disk (set at D4 ORDERING INVARIANT point before Phase 3).
6. Close FaceDB.
7. Open new FaceDB → `_load_faiss` sees sentinel → calls `_rebuild_faiss()` (sync, with full DB UPDATE) → clears sentinel.
8. For each of 5 known persons: `recognize()` → MUST succeed with correct identity.

**Why this scenario:** validates that the sentinel-based crash recovery works for the specific failure mode P0.B2 D4 is designed to catch. Adjacent to existing `test_artificial_divergence_reconciles_on_boot` (line ~5 in current slow-tier file) but specifically exercises the async-prune crash path.

### §3.3 — Test 3 (optional, depth-coverage): concurrent add_embedding during async rebuild captures row_id correctly

**Test name:** `test_add_embedding_during_async_rebuild_tracks_row_id`

**Surface:** new test in `tests/test_faiss_async_rebuild.py` (fast-tier — uses mocks).

**Scenario:**
1. Create `FaceDB` instance.
2. Insert 5 persons.
3. Start `rebuild_faiss_async` in a background task — pause execution after Phase 1 (via monkeypatched executor delay).
4. Call `add_embedding` for a 6th person → its row gets a DB `faiss_idx` value; AND its `(vec, person_id, row_id)` 3-tuple lands in `_pending_adds_during_rebuild`.
5. Resume async rebuild → completes Phase 3 (replay) + DB UPDATE batch.
6. Verify the 6th person's DB `faiss_idx` value matches its new in-memory position in `_idx_to_person`.

**Architect lean:** include Test 3 for depth coverage. If auditor prefers minimal anchors, defer Test 3.

---

## §4. P4 — Bug 2 honest comment correction text (LOCKED)

**Surface:** `tests/test_faiss_atomicity_invariants.py:29-32`

**Pre-fix comment (the documentation drift):**

```python
SCOPE LIMIT: This test checks the methods listed in PAIRED_WRITE_METHODS.
prune_old_strangers_async uses a delegation pattern (calls
prune_old_strangers_sql_only + rebuild_faiss_async) and is tested via
the slow-tier crash tests instead.
```

**Post-fix comment (honest, cites the actual test names):**

```python
SCOPE LIMIT: This test checks the methods listed in PAIRED_WRITE_METHODS.
prune_old_strangers_async uses a delegation pattern (calls
prune_old_strangers_sql_only + rebuild_faiss_async). Its end-to-end
crash recovery + DB write-through correctness is covered by:
  - tests/test_faiss_sql_atomicity.py::test_prune_async_then_restart_recognizes_known_person
  - tests/test_faiss_sql_atomicity.py::test_prune_async_crash_mid_db_update_recovers_via_sentinel
(P0.B2 D5 closure 2026-05-21 — landed after the prior comment claimed
slow-tier coverage that did not exist; documentation-vs-reality drift
explicitly named here so it doesn't recur.)
```

**Why the verbose attribution:** strict-mode discipline + transparent narrative. The prior comment was wrong for ~weeks; the new comment names the test references that close the gap + the historical drift event so future maintainers don't repeat the pattern.

---

## §5. D-decisions — final contracts

### D1 — `_fetch_all_embeddings_for_index()` returns 3-tuple
- **Surface:** `core/db.py:932-944`
- **Contract:** SELECT widens to `SELECT id, person_id, vector` (matches sync `_rebuild_faiss:1062`). Return shape: `(vecs: np.ndarray, person_ids: list[str], row_ids: list[int])`. Empty case returns `(empty_array, [], [])`.

### D2 — `_build_faiss_from_snapshot()` accepts + returns row_ids
- **Surface:** `core/db.py:946-955`
- **Contract:** signature `(snapshot=(vecs, person_ids, row_ids)) -> (new_index, new_idx_to_person, snapshot_idx_updates)`. The `snapshot_idx_updates` is `list[tuple[int, int]]` of `(new_idx, row_id)` pairs (parallel to sync `_rebuild_faiss:1073` `idx_updates`).

### D3 — Phase 3 captures snapshot + pending-add row_ids + applies DB UPDATE
- **Surface:** `core/db.py:957-1008` (Phase 3 block) + `core/db.py:702-712` (`add_embedding` pending append at line 707).
- **Contract:**
  1. `add_embedding` captures `cursor.lastrowid` immediately after INSERT (Q2 LOCK).
  2. `_pending_adds_during_rebuild` element shape extends 2-tuple → 3-tuple per §1.1.
  3. Phase 3 builds combined `idx_updates` from `snapshot_idx_updates` (snapshot rows) + pending-replay positions (pending-add rows).
  4. DB UPDATE batch runs AFTER `_index_lock` release (Q3 LOCK; matches sync precedent).
  5. `self._conn.commit()` finalizes the batch.

### D4 — `_mark_faiss_dirty()` sentinel discipline on async path
- **Surface:** `core/db.py:957-1008`
- **Contract:** ORDERING INVARIANT per §2.1 + §2.2 + crash-safety table at §2.3. Sentinel SET before Phase 3 swap; CLEARED only after BOTH DB UPDATE commit AND `_save_faiss` success.

### D5 — Real crash-injection tests + honest comment correction
- **Surface 1 (new tests):** 2 (or optionally 3) tests in `tests/test_faiss_sql_atomicity.py` + optionally `tests/test_faiss_async_rebuild.py`.
- **Surface 2 (comment correction):** `tests/test_faiss_atomicity_invariants.py:29-32` per §4 above.

---

## §6. Multi-direction trace (already in audit §4; not repeated here — refer to `tests/p0_b2_faiss_async_rebuild_audit.md` §4)

---

## §7. Quality gate checklist (re-verification from Phase 0 §8; unchanged)

10 APPLIES + 1 N/A (privacy). Matches canonical shape.

---

## §8. Forecast: test count + cadence

### §8.1 — Test count at Plan v1 lock

**~10 logical anchors mid-range** (down from Phase 0's 8-10 estimate due to specificity gain):

- **D1** (1): 3-tuple signature unit test + empty-case test.
- **D2** (1): 3-tuple signature + idx_updates return unit test.
- **D3** (3): pending-add row_id capture via `cursor.lastrowid` unit test; Phase 3 combines snapshot + pending row_ids into idx_updates source-inspection test; DB UPDATE batch AFTER lock release source-inspection test.
- **D4** (2): `_mark_faiss_dirty` called BEFORE Phase 3 swap source-inspection + AST ORDERING INVARIANT comment present; `_clear_faiss_dirty` called only after Phase 4 success source-inspection.
- **D5** (2-3): 2 slow-tier crash tests per §3.1+§3.2 (Test 1 + Test 2); architect lean includes Test 3 (§3.3) for depth coverage → 3 total.
- **Cross-cutting** (1): comment correction at `tests/test_faiss_atomicity_invariants.py:29-32` verified by source-inspection structural test.

**Anchors mid: 10 (with Test 3) or 9 (without Test 3).**

### §8.2 — Q5 reading correction (P0 §6 imprecision acknowledged)

**Phase 0 §6 said:** "+11.1% SLIGHT-DRIFT-UP edge"

**CORRECTED per auditor Phase 0 verdict + locked methodology:**
- ±15% from mid = **ON-TARGET**
- ±15-30% from mid = SLIGHT DRIFT
- ≥±30% from mid = FALSIFICATION TRIGGER

**Architect Phase 0 §6 framing "+11.1% SLIGHT-DRIFT-UP edge" was WRONG.** 11.1% < 15% = ON-TARGET (no drift-band qualifier needed).

**Plan v1 forecast under auditor's intermediate band 8-14 mid 11:**
- 10 anchors vs mid 11 = `(10-11)/11 = −9.1%` → **ON-TARGET** (within ±15%)
- 9 anchors (if Test 3 dropped) → `(9-11)/11 = −18.2%` → SLIGHT-DRIFT-DOWN
- 11 anchors (if parametrize fan-out adds) → `(11-11)/11 = 0%` → exact ON-TARGET

**Architect lean:** include Test 3 for depth coverage → 10 anchors → ON-TARGET.

### §8.3 — Cadence prediction

5 D-decisions / single subsystem / HIGH per-site complexity (cross-storage atomicity) / multi-pass grep expected → **v1 → v2 floor minimum**. Possibly v3 if Pass-N at Plan v2 review surfaces residual sites (e.g., a test fixture I haven't grepped or a sentinel-call ordering subtlety the architect-side missed).

Per `feedback_plan_version_cadence_multi_axis.md`: medium-D + HIGH per-site complexity → v3 floor possible. Aligns with auditor's Phase 0 prediction.

---

## §9. Cross-spec impact (unchanged from Phase 0 §7; not repeated)

---

## §10. Banked dispositions for auditor v1 review

- **Sub-pattern A `### Phase-0-catches-wrong-premise`:** STAYS at 7.
- **`### Phase-0-granular-decomposition`:** STAYS at 8 supporting (closure-conditional bump to 9 if P0.B2 closes ON-TARGET under re-baselined methodology).
- **`### Spec-first review cycle`:** 42 → **43 at Plan v1 close** per locked +1-per-artifact convention.
- **Strict-industry-standard mode:** 32 → **33 consecutive applications** + 9 closures.
- **`### Twin-filename-pitfall-prevention`:** stays at 7th preventive instance from Phase 0.
- **Auditor-Q5:** 13 banked + 1 in-flight at −9.1% vs mid 11 (ON-TARGET) — projected.
- **Discipline-count-bump-needs-explicit-justification:** stays at 10 preventive (no preventive event at Plan v1).
- **Cross-cycle-handoff transparency precedent:** stays at 7 (no in-flight items at Plan v1).
- **Convention-drift-on-discipline-counts:** stays at 3 (clean baseline applied via grep-baseline-before-drafting at Phase 0).
- **`Grep-baseline-before-drafting` informal observation:** stays at 1 instance (P0.B2 Phase 0; banked at auditor Phase 0 verdict).
- **`Explicit-closure-honest-count-commitment`:** stays at 2 instances (P0.B1 Plan v2 + closure); P0.B2 closure may bump if falsification-watch fires.
- **Auditor-precision-item-misframe (auditor-side):** STAYS at 2.

---

## §11. Open questions for auditor (1)

**Q1.** Test 3 (`test_add_embedding_during_async_rebuild_tracks_row_id`) — architect lean: INCLUDE for depth coverage. If auditor prefers minimal anchors (drop to 9 anchors, lands SLIGHT-DRIFT-DOWN −18.2%), defer Test 3 to a follow-up cycle. Architect's lean is INCLUDE because the pending-add row_id tracking is the most complex part of D3 + only this test exercises the concurrent-write code path.

---

**End of Plan v1.** Ready to forward to auditor.

**Architect prediction:** APPROVED with 0-1 precision items. Plan v2 likely needed per multi-axis cadence (5-D + HIGH per-site complexity = v1 → v2 floor). On Plan v2 cleared → ship to developer.
