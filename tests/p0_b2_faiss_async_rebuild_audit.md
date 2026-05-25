# P0.B2 Phase 0 audit — FAISS Async Rebuild Correctness (Bug 1 + Bug 2)

**Spec ID:** P0.B2 — second cycle in the "Board-bug remediation" track. Per `### Twin-filename-pitfall-prevention` operational rule 4 (locked at P0.B1 Plan v1): bug-fix specs use `P0.B` prefix; sub-name disambiguates within the track.

**Twin-filename pitfall check:** grep confirms no existing `p0_b2_*.md` files in `tests/`. Filename `p0_b2_faiss_async_rebuild_audit.md` is unique. **7th preventive instance.**

**Baseline counts (grep-verified from P0.B1 closure narrative + auditor ratified table 2026-05-21, per the locked grep-baseline-before-drafting discipline):**
- Spec-first 41-for-41
- Strict-mode 31 applications + 9 closures
- `### Phase-0-catches-wrong-premise` 7
- `### Phase-0-granular-decomposition-enables-accurate-estimates` 8 supporting
- `### Twin-filename-pitfall-prevention` 6 instances + operational rule 4
- Auditor-Q5 13 banked closures
- Cross-cycle-handoff transparency 7 successful
- Discipline-count-bump 10 preventive
- Convention-drift 3 instances
- Spec-time grep-verification 12 instances
- Deferred-canary 8th application
- Explicit-closure-honest-count-commitment 2 instances

---

## §1. Grep-verified production surface (Pass-1)

### §1.1 — Bug 1: `rebuild_faiss_async` never updates `embeddings.faiss_idx` (CONFIRMED)

**Sync path (`_rebuild_faiss`, `core/db.py:1050-1082`) — correct:**

```python
rows = self._conn.execute(
    "SELECT id, person_id, vector FROM embeddings WHERE vector IS NOT NULL ORDER BY id"
).fetchall()

idx_updates = []
with self._index_lock:
    self.index = faiss.IndexFlatIP(EMBEDDING_DIM)
    self._idx_to_person = {}
    for new_idx, (row_id, person_id, vector_bytes) in enumerate(rows):
        emb = ...
        self.index.add(emb)
        self._idx_to_person[new_idx] = person_id
        idx_updates.append((new_idx, row_id))            # ← row_id captured

for new_idx, row_id in idx_updates:
    self._conn.execute(
        "UPDATE embeddings SET faiss_idx = ? WHERE id = ?",
        (new_idx, row_id)                                # ← DB UPDATE happens
    )
self._conn.commit()
self._save_faiss()
```

**Async path (`rebuild_faiss_async`, `core/db.py:957-1008`) — broken:**

```python
async def rebuild_faiss_async(self, loop):
    # Phase 1: snapshot under lock
    with self._index_lock:
        snapshot = self._fetch_all_embeddings_for_index()   # ← returns (vecs, person_ids) only
        self._pending_adds_during_rebuild = []
        self._rebuild_in_progress = True

    # Phase 2: build in worker thread
    new_index, new_idx_to_person = await loop.run_in_executor(
        None,
        self._build_faiss_from_snapshot,                    # ← returns (new_index, new_idx_to_person) only
        snapshot,
    )

    # Phase 3: replay pending adds, swap atomically
    with self._index_lock:
        for vec, person_id in self._pending_adds_during_rebuild:   # ← no row_id tracked
            new_idx = new_index.ntotal
            new_index.add(vec.reshape(1, -1))
            new_idx_to_person[new_idx] = person_id
        self.index = new_index
        self._idx_to_person = new_idx_to_person
        self._rebuild_in_progress = False
        self._pending_adds_during_rebuild = []
        # ← NO DB UPDATE for snapshot row faiss_idx values
        # ← NO DB UPDATE for pending-add row faiss_idx values
        # ← NO _mark_faiss_dirty() call

    # Phase 4: persist to disk
    await loop.run_in_executor(None, self._save_faiss)
```

**Helper functions returning 2-tuple (no row_ids):**

- `_fetch_all_embeddings_for_index` at `core/db.py:932-944` returns `(vecs, person_ids)` — no row IDs.
- `_build_faiss_from_snapshot` at `core/db.py:946-955` accepts `(vecs, person_ids)` snapshot, returns `(new_index, new_idx_to_person)` — no row IDs.

### §1.2 — Boot reconciliation safety net analysis (`_load_faiss`, `core/db.py:386-427`)

```python
def _load_faiss(self):
    if self._faiss_path.exists():
        self.index = faiss.read_index(str(self._faiss_path))
    ...
    valid_count = self._conn.execute("SELECT COUNT(*) ...").fetchone()[0]
    sentinel = self._sentinel_path()
    needs_rebuild = sentinel.exists() or self.index.ntotal != valid_count
    if needs_rebuild:
        ...
        self._rebuild_faiss()
        self._clear_faiss_dirty()
        return
    # Build idx → person_id map from DB
    rows = self._conn.execute("SELECT faiss_idx, person_id FROM embeddings ...").fetchall()
    self._idx_to_person = {r[0]: r[1] for r in rows}    # ← reads STALE faiss_idx after async rebuild
```

**Safety net analysis:**
- Sentinel check fires rebuild → BUT `rebuild_faiss_async` doesn't call `_mark_faiss_dirty()`, so sentinel doesn't exist.
- Count mismatch fires rebuild → BUT after async rebuild, `index.ntotal` == `valid_count` (the async rebuild matched counts to the deletion count). Count check passes.
- **Both safety nets fail to trigger on the async-rebuild-then-restart sequence.**
- Code at line 424-427 builds `_idx_to_person` from DB's STALE `faiss_idx` values → wrong position-to-pid mapping → `recognize()` returns wrong identity OR None.

### §1.3 — Bug 2: false test-coverage claim (CONFIRMED)

**Documentation lie at `tests/test_faiss_atomicity_invariants.py:30-32`:**

```python
"""
...
SCOPE LIMIT: This test checks the methods listed in PAIRED_WRITE_METHODS.
prune_old_strangers_async uses a delegation pattern (calls
prune_old_strangers_sql_only + rebuild_faiss_async) and is tested via
the slow-tier crash tests instead.
"""
```

**Grep-verified false:**
- `tests/test_faiss_sql_atomicity.py` (the slow-tier crash test file): 7 test functions, **ZERO references to `prune_old_strangers_async` or `rebuild_faiss_async`**.
- `tests/test_faiss_async_rebuild.py`: 5 class-method tests, **all about in-memory rebuild correctness (ntotal counts, pending-add replay, concurrent recognize). NONE simulate process restart + recognize**.

**Conclusion:** the "tested via slow-tier crash tests" claim is documentation that doesn't match reality. The path is structurally untested at the prune→restart→recognize level.

### §1.4 — Pending-add row tracking (architectural complexity)

**`add_embedding` at `core/db.py:694-712`:**

```python
with self._index_lock:
    faiss_idx = self.index.ntotal                       # ← reads CURRENT index size
    with self.transaction():
        self._conn.execute(
            "INSERT INTO embeddings (person_id, faiss_idx, vector, ...)",
            (person_id, faiss_idx, ...)                  # ← writes faiss_idx at INSERT time
        )
    ...
    self.index.add(emb)
    self._idx_to_person[faiss_idx] = person_id
    if self._rebuild_in_progress:
        self._pending_adds_during_rebuild.append((emb[0].copy(), person_id))
        # ← row_id NOT captured; only (vec, person_id) stored
    self._save_faiss()
```

**Pending-add complication:**
- `add_embedding` runs between async-rebuild Phase 1 and Phase 3.
- INSERT happens under `_index_lock`, with `faiss_idx = self.index.ntotal` (the OLD index's current size).
- Row gets a DB `faiss_idx` value at INSERT time.
- Pending list captures `(vec, person_id)` — NO `row_id`.
- At Phase 3 replay: pending row's NEW in-memory position = `new_index.ntotal` (the freshly built index's current size).

**Mismatch arithmetic:**
- Before async rebuild: `self.index.ntotal = K` (full old index)
- After SQL prune (sql_only): `M` strangers deleted from DB; in-memory index still has `K` positions.
- During async rebuild Phase 2: in-memory index still `K`. A concurrent `add_embedding` inserts row with `faiss_idx = K`. In-memory grows to `K+1`.
- At Phase 3: new index built from snapshot of `K-M` rows. Replay pending add: `new_idx = K-M` (the new index's first replay position).
- **Mismatch:** DB `faiss_idx=K`, new in-memory position `K-M`.

Fix requires tracking `row_id` in `_pending_adds_during_rebuild` so the post-swap DB UPDATE covers BOTH snapshot rows AND pending adds.

---

## §2. Pre-audit premise check

**Pre-audit premise (from board-meeting consolidation 2026-05-21, repeated by Skeptic-1 ATTACK 5):**

> "5-surface refactor:
> 1. Change `_fetch_all_embeddings_for_index()` signature → 3-tuple
> 2. Change `_build_faiss_from_snapshot()` to accept and return row IDs alongside the new index
> 3. Change Phase 3 swap to capture the (new_idx → row_id) mapping
> 4. Add the DB update after Phase 3 but before Phase 4
> 5. Add dirty sentinel management"

**Grep-verified verdict: ON-TARGET with 1 refinement.**

**Refinement R1 (architect-side Phase 0 finding):** the 5-surface enumeration MISSES pending-add row tracking. Skeptic-1's items 1-3 cover only the snapshot rows. The pending-add path (`_pending_adds_during_rebuild`) needs separate row_id tracking — at `add_embedding` insertion time or via post-INSERT lookup. Without this, snapshot row write-backs land correctly but pending-add row write-backs are missing.

This is NOT a sub-pattern A wrong-premise catch — it's scope precision. The underlying concern is correct; one mechanism detail was overlooked. Sub-pattern A stays at 7.

**Architectural decision required (surface in Phase 0):**

**Option (a) — 5-surface refactor (Skeptic-1's recommendation) + sentinel discipline.** Both runtime DB UPDATE AND sentinel on async path. Defense-in-depth.
- Cost: ~6-10 hours
- Benefit: structurally correct; DB stays in sync at runtime; sentinel as belt-and-braces if a future refactor regresses

**Option (b) — Sentinel-only fix.** Add `_mark_faiss_dirty()` to async path. Boot reconciliation fires after every prune-and-restart sequence. DB is "eventually consistent" — stale between async rebuild + next restart.
- Cost: ~1-2 hours
- Benefit: minimal change
- Drawback: DB intentionally stale at runtime; future maintenance reading DB `faiss_idx` could be confused; ~500ms-1s boot overhead after every dream-loop prune

**Architect lean:** Option (a) per strict-mode "never compromise quality." DB consistency at runtime is the right invariant; sentinel is defense-in-depth.

---

## §3. D-decisions (5 — medium-spec band)

### D1 — `_fetch_all_embeddings_for_index()` returns 3-tuple with row IDs
- **Surface:** `core/db.py:932-944`
- **Contract:** signature change from `() -> (vecs, person_ids)` → `() -> (vecs, person_ids, row_ids)`. SELECT widened to `SELECT id, person_id, vector` (matches sync `_rebuild_faiss`).

### D2 — `_build_faiss_from_snapshot()` signature accepts + returns row_ids
- **Surface:** `core/db.py:946-955`
- **Contract:** signature change from `(snapshot=(vecs, person_ids)) -> (new_index, new_idx_to_person)` → `(snapshot=(vecs, person_ids, row_ids)) -> (new_index, new_idx_to_person, snapshot_idx_updates)`. `snapshot_idx_updates` is `list[tuple[int, int]]` of `(new_idx, row_id)` pairs.

### D3 — Phase 3 captures (new_idx → row_id) for pending adds + applies combined DB UPDATE after swap
- **Surface:** `core/db.py:957-1008` (Phase 3 block) + `core/db.py:702-712` (`add_embedding` pending-list append).
- **Contract:**
  1. `_pending_adds_during_rebuild` element shape extends `(vec, person_id)` → `(vec, person_id, row_id)`.
  2. `add_embedding` appends with row_id (captured via `cursor.lastrowid` after INSERT).
  3. Phase 3 builds combined `idx_updates` from snapshot + pending replay positions.
  4. After releasing `_index_lock`: execute DB UPDATE batch for all idx_updates + commit.
  5. Phase 4 (`_save_faiss`) follows.

### D4 — `_mark_faiss_dirty()` sentinel discipline on async path (defense-in-depth per Option (a))
- **Surface:** `core/db.py:957-1008`.
- **Contract:**
  1. `_mark_faiss_dirty()` called BEFORE Phase 3 swap (matches sync `_rebuild_faiss` precedent + P0.5 SQL-first discipline).
  2. `_clear_faiss_dirty()` called AFTER successful Phase 4 disk save.
  3. On Phase 2 or Phase 3 exception: sentinel stays → next boot rebuilds via `_rebuild_faiss` (which clears the sentinel on success). Already-degraded mode is preserved by existing `_load_faiss` exception handling at line 419-420.

### D5 — Real prune→restart→recognize crash-injection test + honest documentation update (closes Bug 2)
- **Surface 1 (new test):** `tests/test_faiss_sql_atomicity.py` — add 2 slow-tier tests:
  - `test_prune_async_then_restart_recognizes_known_person` — full flow: insert N people + run prune_old_strangers_async → simulate process restart by recreating FaceDB instance → `recognize()` returns correct identity for each remaining person.
  - `test_prune_async_crash_mid_db_update_recovers_via_sentinel` — inject crash AFTER Phase 3 swap but BEFORE DB UPDATE commit → restart → sentinel triggers `_rebuild_faiss` → recognize succeeds.
- **Surface 2 (documentation correction):** `tests/test_faiss_atomicity_invariants.py:29-32` — update the "tested via slow-tier crash tests instead" comment to honestly describe new coverage (cite the 2 new tests in `test_faiss_sql_atomicity.py`).

---

## §4. Multi-direction trace (per D-decision)

### D1 (`_fetch_all_embeddings_for_index` signature)
- **Forward:** D2 (`_build_faiss_from_snapshot`) consumes the 3-tuple snapshot.
- **Backward:** `core/db.py:932-944` SELECT statement is the producer.
- **Sideways:** sync `_rebuild_faiss` at line 1061 reads `id, person_id, vector` directly (not via this helper) — no shared producer. Tests in `test_faiss_async_rebuild.py` may call `_fetch_all_embeddings_for_index` directly — Pass-2 grep verifies.
- **Lifecycle:** invoked once per `rebuild_faiss_async` call under `_index_lock` Phase 1.

### D2 (`_build_faiss_from_snapshot` signature)
- **Forward:** `rebuild_faiss_async` Phase 2 consumes the 3-tuple return. New `snapshot_idx_updates` propagates to Phase 3.
- **Backward:** D1's 3-tuple snapshot is the input.
- **Sideways:** function is "pure" — no DB access, no lock; safe to run in worker thread. Test `test_rebuild_async_produces_correct_index_size` may call it directly — Pass-2 grep verifies.
- **Lifecycle:** invoked once per `rebuild_faiss_async` call in the executor thread.

### D3 (Phase 3 + pending-add row tracking + DB UPDATE)
- **Forward:** post-Phase-3, `recognize()` reads `_idx_to_person` (correct in-memory). Next boot reads DB `faiss_idx` (now correct after DB UPDATE).
- **Backward:** D1 + D2 supply snapshot idx_updates. `add_embedding` supplies pending-add row_ids. D4 sentinel covers failure modes.
- **Sideways:** concurrent `recognize()` during Phase 3 sees the new `_idx_to_person` correctly (under lock). Concurrent `add_embedding` after Phase 3 swap reads fresh `self.index.ntotal` and INSERTs with new faiss_idx — consistent.
- **Lifecycle:** Phase 3 = once per rebuild. DB UPDATE batch runs AFTER `_index_lock` released (matches sync precedent at lines 1075-1080).

### D4 (Sentinel discipline)
- **Forward:** on async-rebuild exception or partial commit, sentinel triggers `_rebuild_faiss` on next boot → DB UPDATE re-applied + state reconciled.
- **Backward:** `_mark_faiss_dirty()` called before Phase 3; `_clear_faiss_dirty()` after Phase 4.
- **Sideways:** sentinel ALSO covers the legitimate `add_embedding` crash case (P0.5 precedent at lines 710-712). Both sync `_rebuild_faiss` and async `rebuild_faiss_async` now use sentinel uniformly.
- **Lifecycle:** sentinel file created at rebuild start, deleted at rebuild success. Lifetime ≤ rebuild duration (50ms-3s).

### D5 (Bug 2 closing test)
- **Forward:** crash-injection test fires on every CI run via slow-tier; structural invariant test asserts comment accuracy.
- **Backward:** test infrastructure (process-restart simulation, sentinel manipulation) reads the production code paths.
- **Sideways:** existing 7 slow-tier crash tests stay green. New 2 tests join them.
- **Lifecycle:** run-time test execution. New tests inherit `@pytest.mark.slow` marker.

---

## §5. Pre-mortem (12 failure modes — strict-mode floor 5-10)

### §5.1 — Pending-add row tracking via cursor.lastrowid
**Risk:** SQLite's `cursor.lastrowid` semantics under `with self.transaction()` block + concurrent writers. If the INSERT was inside a nested transaction, `lastrowid` might return 0 or stale ID.
**Mitigation:** Pass-2 grep verifies the existing transaction context manager's behavior. Plan v1 includes a unit test that exercises `add_embedding` → assert `cursor.lastrowid > 0` post-INSERT.

### §5.2 — DB UPDATE batch under wrong lock state
**Risk:** if DB UPDATE happens INSIDE `_index_lock`, it blocks concurrent recognize() readers for the duration of N UPDATE statements (~10-100ms for N=100-1000 rows). Skeptic-1's recommendation was "DB update after Phase 3 but before Phase 4" — does that mean inside or outside the lock?
**Mitigation:** match sync `_rebuild_faiss` precedent: DB UPDATE batch happens AFTER releasing `_index_lock` (lines 1075-1080 in sync path are outside the `with self._index_lock` block at 1066-1073). Same pattern for async path.

### §5.3 — Async rebuild crashes mid-DB-UPDATE
**Risk:** Phase 3 swap completes (new in-memory state) but DB UPDATE batch crashes halfway through (e.g., disk full). DB has partial-new + partial-old faiss_idx values.
**Mitigation:** D4 sentinel set BEFORE the batch. On boot, sentinel triggers `_rebuild_faiss` which re-runs the full SELECT + UPDATE under sync semantics. Eventually consistent + repaired.

### §5.4 — `_save_faiss` order vs DB UPDATE
**Risk:** Phase 4 `_save_faiss` writes the new in-memory index to disk. If `_save_faiss` runs BEFORE the DB UPDATE batch, an exception during the UPDATE leaves the disk file in NEW state but DB in OLD state → recognize() works (in-memory good) but next boot sees the same `_load_faiss` bug all over again. Sentinel still catches it, but the ordering matters for atomicity intent.
**Mitigation:** lock the ordering: D4 sentinel SET → Phase 3 in-memory swap → DB UPDATE batch + commit → Phase 4 `_save_faiss` → D4 sentinel CLEAR. Same shape as sync `_rebuild_faiss`. Plan v1 §X documents this as ORDERING INVARIANT (mirrors P0.S2/S3/S6 ordering-invariant precedents).

### §5.5 — Process-restart simulation in pytest
**Risk:** new Bug 2 crash-injection tests need to simulate process restart. Pure-Python pytest can't actually restart the process; need to construct a new `FaceDB` instance against the same disk files (faces.db + faiss.index).
**Mitigation:** Plan v1 §X locks the pattern: `db1 = FaceDB(tmp_path/"faces")` → run prune + async rebuild → close db1 → `db2 = FaceDB(tmp_path/"faces")` → assert recognize. Same shape as existing test_faiss_sql_atomicity.py crash tests (e.g., `test_crash_post_sql_commit_pre_faiss_update_recovers_on_boot`).

### §5.6 — Backward-compat: existing tests calling helpers directly
**Risk:** `tests/test_faiss_async_rebuild.py` 5 tests + possibly others call `_fetch_all_embeddings_for_index` or `_build_faiss_from_snapshot` directly. Signature changes break those calls.
**Mitigation:** Pass-2 grep enumerates direct callers; Plan v1 updates each call site. Likely 2-5 sites; ~30 min of mechanical migration.

### §5.7 — Concurrent prune + add_embedding race
**Risk:** between Phase 1 snapshot and Phase 3 swap, `add_embedding` runs and INSERTs a row. The row's DB `faiss_idx` matches the OLD index's ntotal at insertion time. After Phase 3 + pending replay, the row's new in-memory position matches `new_index.ntotal` at replay time. If prune deleted M rows, these differ by M. DB UPDATE batch must include both snapshot rows AND pending-add rows.
**Mitigation:** D3 contract explicitly handles BOTH snapshot and pending-add row IDs. Plan v1 §X locks the unified idx_updates list.

### §5.8 — Sentinel race during async rebuild
**Risk:** if `_mark_faiss_dirty()` is set at Phase 3 entry, then async rebuild completes successfully, then `_clear_faiss_dirty()` runs at Phase 4 end — what if a CONCURRENT `add_embedding` failure (line 710-711) sets the sentinel during this window? The clear in `rebuild_faiss_async` would wipe the legitimate dirty marker.
**Mitigation:** ordering invariant per §5.4: sentinel CLEAR happens only after BOTH DB UPDATE commit AND `_save_faiss`. During async rebuild, `_rebuild_in_progress=True` is set — any concurrent `add_embedding` that fails could check this and avoid clearing on its own. Plan v1 §X audits the existing `_mark_faiss_dirty` callers + locks the discipline.

### §5.9 — Existing `_pending_adds_during_rebuild` element-shape backward compat
**Risk:** test files may construct `_pending_adds_during_rebuild` entries directly (via `db._pending_adds_during_rebuild.append(...)`) for fixture seeding. Signature change from 2-tuple → 3-tuple breaks those.
**Mitigation:** Pass-2 grep verifies test-side usage. Likely zero direct mutations (the field is module-private convention); if any, migrate.

### §5.10 — Test infrastructure for crash-injection mid-batch UPDATE
**Risk:** D5 includes `test_prune_async_crash_mid_db_update_recovers_via_sentinel` — needs to crash AFTER swap but DURING UPDATE batch. How to inject?
**Mitigation:** monkeypatch `_conn.execute` to raise after Nth call, OR use a trigger-based crash injection (existing crash tests use similar patterns). Plan v1 §X picks the simplest viable approach + tests it.

### §5.11 — Cost amplification at boot if sentinel always fires
**Risk:** if D4 sentinel is set on EVERY async rebuild + the user restarts soon after, the boot triggers a full sync `_rebuild_faiss` (cost ~50ms-3s). Repeated dream-loop+restart sequences accumulate cost.
**Mitigation:** sentinel is set during rebuild AND CLEARED on success. Only stays set if rebuild crashed. Cost amplification only happens on failure path — desired behavior.

### §5.12 — Pass-N grep-verification fatigue (P0.S5 precedent)
**Risk:** P0.S5 had 4 grep passes to converge. P0.B2 may exceed Plan v1 enumeration; Pass-2 at Plan v1 drafting + Pass-3 at developer entry expected.
**Mitigation:** explicit prediction at Phase 0; multi-axis cadence hypothesis predicts v1 → v2 → v3 floor for 5-D + HIGH-fan-out specs (per `feedback_plan_version_cadence_multi_axis.md`).

---

## §6. Forecast: Plan v1 test count

**~8-10 logical anchors mid-range:**

- D1 (1): 3-tuple return shape unit test.
- D2 (1): 3-tuple signature + idx_updates return unit test.
- D3 (3): Phase 3 captures snapshot row_ids + pending-add row_ids + applies DB UPDATE behavioral test; concurrent add_embedding during rebuild captures row_id behavioral test; ordering invariant source-inspection test.
- D4 (2): `_mark_faiss_dirty` called before Phase 3 swap source-inspection; sentinel cleared after Phase 4 source-inspection.
- D5 (2): the 2 new crash tests in slow-tier (prune→restart→recognize + mid-UPDATE crash recovery).
- Cross-cutting (1): false-coverage comment at `test_faiss_atomicity_invariants.py:29-32` corrected (AST or source-inspection structural test).

**Mid: 10 anchors.**

**Q5 prediction:** under medium-spec band 6-12 mid 9 → 10 vs mid 9 = **+11.1% SLIGHT-DRIFT-UP** (within ±15% → ON-TARGET candidate). Architect's prediction is at upper edge of ON-TARGET band; consolidation at Plan v1 drafting could push to 8-9 anchors (ON-TARGET).

**Cadence prediction:** 5 D-decisions / HIGH architectural complexity / multi-pass grep expected → v1 → v2 floor minimum, **possibly v3 if Pass-N surfaces residual sites** (per `feedback_plan_version_cadence_multi_axis.md` HIGH-complexity refinement).

---

## §7. Cross-spec impact analysis

- **P0.5** (CLOSED): FAISS+SQL atomicity for SYNC paths. P0.B2 EXTENDS this discipline to the async path. No invariant impact on P0.5.
- **P0.0.7** (CLOSED): event log foundation. P0.B2 doesn't emit new event types.
- **P0.S1** (CLOSED): anti-spoof on every face match. Distinct surface.
- **P0.B1** (CLOSED): frozen VoiceEvidence. Distinct subsystem (voice vs face FAISS).
- **PAIRED_WRITE_METHODS tuple** at `tests/test_faiss_atomicity_invariants.py:48-54`: enumerates sync paired-write methods; `prune_old_strangers_async` is intentionally excluded with comment lines 29-32. **P0.B2 D5 corrects that exclusion's documentation** (Bug 2 fix).
- **`_TOOL_HANDLERS` / `TOOL_PRIVILEGES` (P0.S6)**: distinct subsystem.
- **No invariant impact on any closed spec.** P0.B2 is pure additive architectural hardening.

---

## §8. Quality gate checklist (11 gates — all explicit)

- **[APPLIES] Correctness** — invariants 4-axis traced at §4.
- **[APPLIES] Security** — silent corruption of recognition affects identity → privilege gating relies on correct identity → P0.B2 closes a security-adjacent failure mode (best_friend's session could be misrouted to another pid post-restart). Same class as P0.S1.
- **[N/A] Privacy** — no new facts/state; structural code change is not user-visible.
- **[APPLIES] Performance** — DB UPDATE batch adds ~10-50ms per async rebuild. Negligible (rebuild itself is 50ms-3s; UPDATE is small fraction). Boot reconciliation cost on sentinel-set: ~50ms-1s — happens only on async-rebuild failure path.
- **[APPLIES] Observability** — Pass-2 grep verifies existing log lines around rebuild + add_embedding. D4 sentinel state is observable via `_load_faiss` log message ("FAISS dirty sentinel found — rebuilding to reconcile").
- **[APPLIES] Test pyramid** — unit (signature tests) + AST (ordering invariant + sentinel calls) + behavioral (concurrent rebuild + recognize) + slow-tier crash injection (prune→restart→recognize, mid-UPDATE crash).
- **[APPLIES] Regression guards** — deliberate-regression: remove DB UPDATE → existing recognition test post-rebuild fires. Remove sentinel call → mid-UPDATE crash test fires.
- **[APPLIES] Pre-mortem** — 12 failure modes at §5 (above 5-10 floor).
- **[APPLIES] Multi-direction trace** — §4 per D-decision.
- **[APPLIES] Backward compat** — signature changes are private helpers (`_fetch_all_embeddings_for_index`, `_build_faiss_from_snapshot`); private convention; callers within `core/db.py` + 5 test methods.
- **[APPLIES] Doc updates** — 5-surface closure narrative (CLAUDE.md + parent + subdir + to_be_checked + memory files) + comment correction at `tests/test_faiss_atomicity_invariants.py:29-32`.

**Total: 10 APPLIES + 1 N/A (privacy, with rationale).** Matches P0.S5/S6/S7/B1 canonical shape.

---

## §9. Banked dispositions for Plan v1 review

- **Sub-pattern A `### Phase-0-catches-wrong-premise`:** STAYS at 7. P0.B2 premise is ON-TARGET with 1 mechanism refinement (pending-add row tracking). Not a wrong-premise catch.
- **`### Phase-0-granular-decomposition`:** STAYS at 8 supporting (closure-conditional bump to 9 if P0.B2 closes ON-TARGET under re-baselined methodology).
- **`### Spec-first review cycle`:** 41 → **42 at Phase 0 close** per locked +1-per-artifact convention.
- **Strict-industry-standard mode:** 31 → **32 consecutive applications** + 9 closures (in-flight to 10 at P0.B2 close).
- **`### Twin-filename-pitfall-prevention`:** **7th preventive instance** (P0.B2 filename + sub-name disambiguation per locked operational rule 4).
- **Deferred-canary:** 9th application in-flight.
- **Auditor-Q5 prediction:** 10 anchors vs mid 9 = +11.1% **SLIGHT-DRIFT-UP edge** under re-baselined methodology. Closure-conditional reading.
- **Architectural-decision lock (Option (a) vs (b)):** architect lean Option (a); auditor adjudication welcome at Phase 0 review.

---

## §10. Open questions for auditor (3)

**Q1.** Architectural decision: Option (a) 5-surface refactor + sentinel discipline (architect lean) vs Option (b) sentinel-only fix. Per strict-mode "never compromise quality," Option (a) is the architect lean. If auditor agrees, Plan v1 locks Option (a) with 5 D-decisions. If auditor prefers Option (b), Plan v1 simplifies to 2 D-decisions (sentinel + Bug 2 test).

**Q2.** Pending-add row tracking mechanism: `cursor.lastrowid` post-INSERT OR re-SELECT-by-vec OR INSERT...RETURNING? Architect lean: `cursor.lastrowid` (simplest, SQLite-native, matches existing P0.5 patterns). If auditor prefers a different mechanism, lock at Plan v1.

**Q3.** DB UPDATE batch positioning: AFTER releasing `_index_lock` (matches sync precedent at lines 1075-1080) OR INSIDE the `_index_lock` block (atomicity argument)? Architect lean: AFTER lock release (matches sync pattern + minimizes lock contention). If auditor prefers inside-lock, Plan v1 absorbs.

---

**End of Phase 0 audit.** Ready to forward to auditor for Phase 0 review → Plan v1.

**Architect prediction:** auditor approves Option (a). Plan v1 forecasts ~8-10 logical anchors. Cadence v1 → v2 → potentially v3 if Pass-N surfaces additional sites.
