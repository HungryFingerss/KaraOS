# P0.B3 Phase 0 audit — Kuzu schema migration ordering + Kuzu health observable (Finding 2 + Vulnerability B)

**Spec ID:** P0.B3 — third cycle in the "Board-bug remediation" track (10 bugs surfaced by skeptic1/skeptic2/ceo-morning/ceo-evening board meetings 2026-05-20/21). Per `### Twin-filename-pitfall-prevention` operational rule 4 (locked at P0.B1 Plan v1): bug-fix specs use `P0.B` prefix; sub-name disambiguates within the track.

**Twin-filename pitfall check:** no existing `p0_b3_*` files in `tests/`. Clean disambiguation. **8th preventive instance** of `### Twin-filename-pitfall-prevention` doctrine (P0.B2 was the 7th).

**Pre-audit premise (verbatim from board-meeting consolidation 2026-05-21):**

- **Finding 2 (HIGH — `ceo-morning-2026-05-21.md` §2.2 + `skeptic1-2026-05-21.md` Attack 6):** `core/brain_agent.py:6718–6729` — Kuzu schema upgrade SQL version is committed (line 6721) BEFORE the destructive Kuzu ops (lines 6724-6725 drop_schema + _init_schema) and BEFORE the rebuild from knowledge rows (line 6751). On crash at line 6724 OR mid-rebuild: SQL says `graph_schema_version = NEW`, Kuzu schema state is OLD-or-partial. Next boot: migration branch is gated on `stored_version < GRAPH_SCHEMA_VERSION` (line 6713) → predicate is now FALSE → migration block is **silently skipped**. Sentinel triggers rebuild, but `rebuild(knowledge_rows)` calls `_create_edge(privacy_level=...)` against the OLD Kuzu schema (RELATES_TO lacks the `privacy_level` column at v2) → `_create_edge` raises → except handler logs degraded mode → system enters **permanent `_kuzu_degraded=True` state** with no operator-visible recovery path. `find_shared_entities()` returns empty; cross-person graph traversal is broken; the P0.S7.D-B privacy-on-edges fix is bypassed silently.

  **Fix direction (verbatim):** Commit SQL version bump AFTER Kuzu rebuild succeeds, not before.

- **Vulnerability B (HIGH — `skeptic1-2026-05-21.md` §"Architecture Vulnerabilities Found"):** `core/health.py` — `HealthSnapshot` does not expose `_kuzu_degraded`. An operator running the system in Kuzu-degraded mode sees silence, not an alarm. Graph queries silently return empty results. This violates the observability commitment of P0.0.7. Note: the in-code recovery is "delete the Kuzu directory" but there is no operator-visible signal that recovery is needed.

**Cadence prediction (initial):** 2 D-decisions / 2 subsystems (brain_agent + health) / LOW fan-out (one function refactor + one dataclass extension) → **v1 only OPTIONAL-Plan-v2 path**. Similar shape to P0.B1 (1 D-decision, single-subsystem migration).

---

## §1. Grep-verified surface (Pass-1)

### §1.1 Finding 2 — Kuzu schema upgrade ordering (CONFIRMED at exact coordinates)

**Production surface:** `core/brain_agent.py:6710-6765` (function `BrainOrchestrator._ensure_graph_sync`).

```python
6710:        stored_version = self._brain_db.get_graph_schema_version()
6711:
6712:        need_rebuild = False
6713:        if stored_version < GRAPH_SCHEMA_VERSION:
6714:            print(
6715:                f"[BrainAgent] Graph schema v{stored_version}→v{GRAPH_SCHEMA_VERSION}: "
6716:                "wiping Kuzu graph for rebuild with new schema"
6717:            )
6718:            # 1. Eager sentinel BEFORE any destructive op.
6719:            self._mark_kuzu_dirty()
6720:            # 2. SQL-first: commit version bump before touching Kuzu.
6721:            self._brain_db.update_graph_schema_version(GRAPH_SCHEMA_VERSION)
6722:            # 3. Kuzu ops AFTER SQL commit — wrapped for degraded-mode boot on failure.
6723:            try:
6724:                self._graph_db.drop_schema()
6725:                self._graph_db._init_schema()
6726:                need_rebuild = True
6727:            except Exception as e:
6728:                self._kuzu_degraded = True
6729:                print(f"[BrainAgent] Graph schema migration failed — degraded mode: {e!r}")
6730:
6731:        # Boot reconciliation: sentinel OR entity-count mismatch.
6732:        if not need_rebuild:
6733:            if self._kuzu_sentinel_path().exists():
6734:                need_rebuild = True
6735:            else:
6736:                sql_entity_count = self._brain_db.count_active_knowledge_entities()
6737:                kuzu_entity_count = self._graph_db.entity_count()
6738:                if sql_entity_count != kuzu_entity_count:
6739:                    need_rebuild = True
6740:
6741:        if need_rebuild and not self._kuzu_degraded:
6742:            knowledge_rows = self._brain_db.get_all_knowledge_rows()
6743:            try:
6744:                if knowledge_rows:
6745:                    # ... [rebuild + log scale of pain]
6746:                    _rebuild_t0 = time.time()
6747:                    self._graph_db.rebuild(knowledge_rows)
6748:                    _rebuild_secs = time.time() - _rebuild_t0
6749:                    # ... [logs]
6762:                self._clear_kuzu_dirty()
6763:            except Exception as e:
6764:                self._kuzu_degraded = True
6765:                print(f"[BrainAgent] Graph rebuild failed at boot — degraded mode: {e!r}")
```

**Ordering trace (current, BUGGY):**

| Step | Action | Persistent state after |
|---|---|---|
| 1 | `_mark_kuzu_dirty()` (sentinel file written) | sentinel on disk |
| 2 | `update_graph_schema_version(NEW)` (SQL commit) | `brain_state.graph_schema_version = NEW` |
| 3 | `drop_schema()` (DROP TABLE RELATES_TO + DROP TABLE Entity) | Kuzu schema gone |
| 4 | `_init_schema()` (CREATE NODE/REL TABLE with NEW schema) | Kuzu schema at NEW |
| 5 | `need_rebuild = True` | (only if 3+4 succeeded) |
| 6 | `rebuild(knowledge_rows)` (populate Kuzu from brain.db) | Kuzu data populated |
| 7 | `_clear_kuzu_dirty()` (delete sentinel) | sentinel removed |

**Crash scenarios:**

| Crash point | After-crash state | Next boot behavior | Outcome |
|---|---|---|---|
| Step 1 | sentinel only | stored_version=OLD < NEW → enter migration block → idempotent retry → success | ✓ Recovers |
| **Step 2 mid-commit** | sentinel + partial SQL (SQLite atomicity should prevent — but if it did) | indeterminate | (theoretical; SQLite COMMIT is atomic) |
| **Step 3 mid-drop_schema** | sentinel + SQL=NEW + Kuzu schema partial | `stored_version=NEW == NEW` → SKIP migration block. sentinel triggers rebuild. rebuild against partial Kuzu schema → `_create_edge(privacy_level=...)` raises → **`_kuzu_degraded=True` permanently** | ✗ **BUG (silent permanent degradation)** |
| **Step 4 mid-_init_schema** | sentinel + SQL=NEW + Kuzu schema partial | SAME as Step 3 | ✗ **BUG** |
| **Step 6 mid-rebuild** | sentinel + SQL=NEW + Kuzu schema NEW + partial data | SKIP migration block. sentinel triggers rebuild. rebuild from EMPTY (since `rebuild` recreates from knowledge_rows, not idempotent over existing data) — but `_create_edge` should succeed against NEW schema → recovery actually works | ~ Tested via existing test_kuzu_brain_atomicity.py? |
| Step 7 fails | sentinel + SQL=NEW + Kuzu schema+data NEW (fully migrated) | sentinel triggers rebuild on next boot → idempotent → succeeds → sentinel cleared | ✓ Recovers |

**The bug is specifically Steps 3+4** — the crash window between SQL commit (Step 2) and Kuzu schema fully migrated (end of Step 4). In that window, persistent state lies: SQL says NEW, Kuzu says PARTIAL. The migration block's idempotency guard (`stored_version < GRAPH_SCHEMA_VERSION`) is false → can't re-enter → only the sentinel path runs → but the sentinel path runs rebuild against the wrong schema state.

**Fix shape:** Swap Step 2 and Steps 3-6. Commit SQL AFTER Kuzu schema + data are both at NEW.

### §1.2 Vulnerability B — No Kuzu health observable (CONFIRMED via grep)

**Production surface:** `core/health.py` — `HealthSnapshot` dataclass (lines 10-38) + `gather_health_snapshot()` (lines 41-153) + `format_health_line()` (lines 156-202) + `format_health_alerts()` (lines 205-258).

**Grep result:** zero references to `_kuzu_degraded`, `_kuzu_dirty`, `_kuzu_sentinel`, or `graph_schema_version` in `core/health.py`.

**Current state surface that IS exposed:**
- `active_sessions` / `sessions_by_type` / `active_disputes`
- `persons_count` / `total_face_embeddings` / `thin_voice_galleries`
- `knowledge_active_rows` / `shadow_persons_count`
- `classifier_scenarios_active` / `classifier_scenarios_quarantined`
- `cloud_state` (ONLINE/SICK/OFFLINE) — clean parallel for `kuzu_degraded`
- `unresolved_watchdog_alerts`
- `event_log_drops` / `event_log_emit_failures` (P0.0.7 conditional-emit pattern)

**Pattern to mirror:** event_log conditional-emit (lines 187-192 + 244-256). On non-zero / non-default state, append to health line via `evlog_parts` collector AND emit a per-alert line in `format_health_alerts` with actionable recovery text. Same shape applies to `kuzu_degraded`.

**Operator-recovery action (Vulnerability B framing):** "delete the Kuzu directory at `<path>`; brain.db facts will rebuild from SQLite on next start." This text needs to live in the alert message itself — operator should NOT need to grep logs or read source to find it.

### §1.3 Sentinel + degraded-mode primitives ALREADY EXIST

**Production surface (already in place — no new primitives needed for D1):**
- `core/brain_agent.py:6680` — `_kuzu_sentinel_path()` — `<graph_db_path>.dirty` file
- `core/brain_agent.py:6684` — `_mark_kuzu_dirty()` — `.touch()` the sentinel
- `core/brain_agent.py:6690` — `_clear_kuzu_dirty()` — `.unlink(missing_ok=True)`
- `core/brain_agent.py:6677` — `_kuzu_degraded: bool = False` (in-memory, instance lifetime)
- `core/brain_agent.py:6641-6642` — early sentinel mark BEFORE `GraphDB.__init__` (covers the case where `_init_schema()` itself fails on upgrade)

**What's missing for D2:**
- Persistent operator-visible signal of `_kuzu_degraded` state (in-memory only today).
- `HealthSnapshot.kuzu_degraded` field + `format_health_line` conditional + `format_health_alerts` actionable line.

### §1.4 Pass-1 grep for downstream consumers of `_kuzu_degraded`

```
core/brain_agent.py:6728:        self._kuzu_degraded = True    # migration drop+init failed
core/brain_agent.py:6764:        self._kuzu_degraded = True    # rebuild failed
core/brain_agent.py:6854:        if self._kuzu_degraded:        # SWALLOW: skip Kuzu writes in degraded mode
                                    return
```

Three writer sites (two failure paths in `_ensure_graph_sync` + degraded-mode gate at `_persist_extraction_to_kuzu`). One reader gate at the persist site. No other production code reads the flag — consistent with the "in-memory only" current behavior. D2 surfaces it to the health subsystem; no additional reader-side wiring needed.

### §1.5 Phase 0 source-of-truth — board-meeting + grep cross-reference

| Source | Page reference | Bug name | Claim | Code-verified? |
|---|---|---|---|---|
| `ceo-morning-2026-05-21.md` §2.2 | line 104-107 | Finding 2 | `brain_agent.py:6718-6729` SQL commit before Kuzu rebuild | ✓ exact lines confirmed |
| `skeptic1-2026-05-21.md` Attack 6 | line 131-151 | Same (with code snippet) | Same | ✓ verbatim agreement |
| `skeptic1-2026-05-21.md` Vulnerability B | line 190-191 | No Kuzu health observable | `core/health.py` lacks `_kuzu_degraded` | ✓ grep confirmed |
| `skeptic2-2026-05-21.md` Q6 | line 323 | "Kuzu migration ordering" in 4-bug list | (Cross-reference only) | ✓ |

**Phase 0 grep verdict: PRE-AUDIT PREMISE FULLY ON-TARGET.** No wrong-premise refinements needed (`### Phase-0-catches-wrong-premise` doctrine NOT bumped this cycle). Both halves of Bug 3 (Finding 2 + Vulnerability B) verified at exact coordinates; fix direction is unambiguous; no additional surfaces surfaced during Pass-1 grep.

---

## §2. Phase 0 verdict + D-decisions to lock

### §2.1 D-decisions (to be locked at Plan v1)

**D1 (P0 CORRECTNESS — Finding 2 anchor):** Refactor `_ensure_graph_sync()` ordering so SQL version commit happens AFTER Kuzu schema+data fully migrated, not before. Specifically:

- **Capture** schema-upgrade intent at function entry: `_did_schema_upgrade = stored_version < GRAPH_SCHEMA_VERSION` (local variable, captured BEFORE any mutation).
- **Remove** `self._brain_db.update_graph_schema_version(GRAPH_SCHEMA_VERSION)` from the migration block (current line 6721).
- **Add** the same call AFTER `self._clear_kuzu_dirty()` in the rebuild branch's success path (current line ~6762), gated on `_did_schema_upgrade`. Bare-rebuild-without-schema-upgrade paths (sentinel-only, count-mismatch) MUST NOT bump the version — only schema-upgrade-triggered cycles do.
- **Comment block** at function docstring explicitly naming the ORDERING INVARIANT (mirroring P0.B2's pattern at `rebuild_faiss_async`): "SQL version bump lands AFTER Kuzu schema + data both at NEW. Crash at any step before that leaves stored_version=OLD → next boot re-enters migration via the predicate at line ~6713 → retries idempotently. P0.B3 D1 fix for Finding 2 board-meeting 2026-05-21."

**D2 (P0 OBSERVABILITY — Vulnerability B anchor):** Surface `_kuzu_degraded` state via the existing health-snapshot infrastructure.

- Add `kuzu_degraded: bool = False` to `HealthSnapshot` dataclass (`core/health.py` lines 10-38).
- Wire `gather_health_snapshot()` to read `getattr(brain_orchestrator, '_kuzu_degraded', False)` with the same try/except defensive shape as the brain.db query block (lines 84-99).
- `format_health_line()` conditional-emit: `| kuzu=degraded` only when `s.kuzu_degraded` is True (mirrors `event_log_drops` conditional at lines 187-192).
- `format_health_alerts()` actionable alert: `[Health-Alert] Kuzu graph in degraded mode — graph queries returning empty (cross-person traversal broken; privacy enforcement bypassed). Recovery: stop pipeline, delete <path>, restart. brain.db facts will rebuild on next start.` Path interpolated from `brain_orchestrator._graph_db_path`.

### §2.2 D-decisions NOT in scope (deliberate non-claims)

- **NOT in scope:** Persistence of `_kuzu_degraded` across process restarts. Today the flag is in-memory only; on next boot the `__init__` flow re-attempts schema sync and the flag is set or cleared anew. D2 surfaces only the CURRENT-process state. A future spec could add persistent degraded-mode marking (e.g. a `.degraded` companion file), but that's separate.
- **NOT in scope:** Generalizing the Kuzu schema migration to P0.9's versioned MIGRATIONS framework. Kuzu cannot ALTER REL TABLES; the "wipe + rebuild" mechanism IS the migration. Adopting `apply_fn`/`verify_post_fn`/`verify_present_fn` 5-tuple framework would be over-engineering for a single migration path.
- **NOT in scope:** FAISS health observable (analog of D2 for `_faiss_degraded` from P0.5). Skeptic1 did not flag this; the board-meeting consolidation lists only Vulnerability B (Kuzu). If demand surfaces, file P0.B3.X follow-up.
- **NOT in scope:** Adjacent Skeptic1 Finding 3 (`_save_faiss()` RLock re-entrancy implicit dependency). That's a separate bug class (LOW severity per ceo-morning). Defer to a later board-bug cycle.
- **NOT in scope:** Adjacent Skeptic1 Vulnerability C (`find_shared_entities` unbounded Cartesian product). Different surface; defer.

---

## §3. Pre-mortem (10 failure modes — strict-mode floor 5-10)

### §3.1 — D1 reordering breaks the existing `_kuzu_degraded` skip at line 6741

**Risk:** Current code skips rebuild on `_kuzu_degraded=True`. After D1, the migration block sets `_kuzu_degraded=True` on failure WITHOUT committing the SQL version. The next-boot retry path re-enters migration via `stored_version < NEW` → would still need to set `_kuzu_degraded` cleanly OR retry the same failure mode.

**Mitigation:** D1 preserves the `except` clause that sets `_kuzu_degraded=True` on drop_schema/_init_schema failure. The IMPORTANT change is that SQL version bump is deferred — the failure path naturally re-enters on next boot. Phase 1 must verify the existing test in `tests/test_kuzu_atomicity_invariants.py` for the SCHEMA_MIGRATION pattern still passes after the reorder.

### §3.2 — Boot-reconciliation block (lines 6731-6739) double-bumps version on sentinel-only path

**Risk:** Sentinel-triggered rebuilds (no schema upgrade) MUST NOT bump version. If D1's "commit SQL after rebuild" lands in a path that runs unconditionally, a sentinel-only rebuild (e.g. crash after rebuild but before sentinel clear) would spuriously bump version.

**Mitigation:** D1 explicitly gates the SQL commit on `_did_schema_upgrade` flag captured at function entry. Boot-reconciliation paths leave `_did_schema_upgrade=False` → SQL commit skipped → version stays at NEW (already correct from prior successful migration).

### §3.3 — `_init_schema` is called by `GraphDB.__init__` at line 3570 BEFORE `_ensure_graph_sync()` runs

**Risk:** `GraphDB.__init__` calls `_init_schema()` at construction time (line 3570). At that point the Kuzu schema is created against the NEW schema definition. If a legacy DB has the OLD schema and we constructed GraphDB before running the migration block, `_init_schema`'s `CREATE NODE TABLE IF NOT EXISTS Entity` + `CREATE REL TABLE IF NOT EXISTS RELATES_TO` would NOT recreate (the IF NOT EXISTS short-circuits). The actual schema upgrade happens in `_ensure_graph_sync`'s migration block via `drop_schema` + `_init_schema`.

**Mitigation:** Existing code at lines 6639-6642 handles this — eager sentinel BEFORE GraphDB construction when upgrade is pending. D1 preserves this. The IF NOT EXISTS short-circuit is a NO-OP when the table already exists at OLD schema; the explicit `drop_schema()` call is what forces re-creation at NEW schema. No change needed.

### §3.4 — `_init_schema` idempotency relies on CREATE IF NOT EXISTS — drop_schema partial failure could leave inconsistent state

**Risk:** `drop_schema` runs two statements: `DROP TABLE IF EXISTS RELATES_TO` then `DROP TABLE IF EXISTS Entity`. If RELATES_TO drop succeeds but Entity drop raises (transient Kuzu IO error), the next `_init_schema` would do nothing (NODE Entity still exists — but RELATES_TO is gone). The next CREATE REL TABLE IF NOT EXISTS RELATES_TO would create RELATES_TO at NEW schema referencing the still-existing OLD-schema Entity. Inconsistent.

**Mitigation:** Plan v1 must specify that D1's retry-on-next-boot logic survives this case. Since stored_version is still OLD (D1's reorder), the next boot's migration block re-runs drop_schema (idempotently dropping the leftover RELATES_TO, then dropping Entity — possibly succeeding this time) + _init_schema. Eventually converges. The catch: if Entity is INTRINSICALLY undroppable (Kuzu bug?), system stays in a loop. That's an out-of-scope environmental issue.

### §3.5 — D2 observability flag may go stale if BrainOrchestrator is replaced mid-process

**Risk:** `gather_health_snapshot()` reads `brain_orchestrator._kuzu_degraded`. If a factory reset replaces the orchestrator (constructs a fresh instance), the new instance starts with `_kuzu_degraded=False` even if the prior instance was degraded.

**Mitigation:** That's correct behavior — factory reset is intended to clear all degraded state and start fresh. The reset path explicitly wipes brain.db + brain_graph (per `wipe_all()`) so any prior schema-mismatch is gone. D2 surfaces CURRENT-process state, not historical state. Document this in HealthSnapshot's docstring.

### §3.6 — Health-snapshot read of `_kuzu_degraded` races with `_ensure_graph_sync` mutation

**Risk:** `_ensure_graph_sync` runs on the event loop during BrainOrchestrator construction. `gather_health_snapshot` runs in an executor every `HEALTH_LOG_INTERVAL_SECS=300s`. Race: gather reads the flag mid-`_ensure_graph_sync`, sees stale value.

**Mitigation:** Boolean reads in Python are atomic. The race is benign — at worst, health surfaces a FALSE NEGATIVE for one 5-minute window (says "not degraded" when it's about to become degraded). The next emit picks up the corrected state. Documented.

### §3.7 — Existing tests in test_kuzu_brain_atomicity.py + test_kuzu_atomicity_invariants.py may encode the OLD ordering

**Risk:** Existing tests for the SCHEMA_MIGRATION pattern (P0.X work) may assert that SQL version is bumped during the migration block. After D1, the bump moves out of that block.

**Mitigation:** Plan v1 Pass-2 grep must enumerate every test asserting `update_graph_schema_version` call site. Each must be re-pointed at the new post-rebuild site OR converted to assert the ORDERING INVARIANT (`update_graph_schema_version` lineno > `rebuild` lineno > `_init_schema` lineno) via AST source-inspection.

### §3.8 — D2 HealthSnapshot field addition breaks legacy snapshot consumers

**Risk:** Adding a new field to `HealthSnapshot` dataclass could break any pickled / serialized snapshots OR any test asserting exact field set.

**Mitigation:** HealthSnapshot is recomputed on every emit; nothing persists snapshots. New field has a `False` default — backward-compatible for any consumer iterating `dataclasses.fields(snap)`. Plan v1 must verify no test asserts `HealthSnapshot` exact `__match_args__` or similar.

### §3.9 — `format_health_line` 200-char budget is tight; `kuzu=degraded` adds ~14 chars

**Risk:** Health-line format has a "≤200 chars" target (line 157 docstring). Adding `| kuzu=degraded` when degraded eats budget.

**Mitigation:** The kuzu surface is CONDITIONAL-emit — only appears when degraded (which should be rare in steady-state). Steady-state health line is unaffected. Document the budget impact in HealthSnapshot docstring.

### §3.10 — Operator-recovery instruction ("delete <path>; restart") could be wrong on some platforms

**Risk:** Graph DB path is interpolated via `brain_orchestrator._graph_db_path`. On Windows, this might be a forward-slash path that confuses operators expecting `del /F /S /Q`. On Linux it's a relative path that could be misinterpreted.

**Mitigation:** Use the absolute path via `Path(...).resolve()` in the alert string. Defensive try/except around path interpolation (fall back to the literal `<graph_db_path>` if resolution fails). Phase 1 must verify Path.resolve() doesn't raise on a missing directory.

---

## §4. Multi-direction invariant trace per D-decision

### §4.1 D1 (re-order SQL commit after Kuzu rebuild)

**Forward (consumers reading `graph_schema_version`):**
- `_ensure_graph_sync()` reads it on every BrainOrchestrator construction to gate the migration block.
- No other production code reads `brain_state.graph_schema_version` (grep-verified — only writers + the gate predicate above).
- After D1, the SQL value tracks "Kuzu actually at this version" instead of "we intend to be at this version." Strictly stricter invariant; no consumer breaks.

**Backward (callers / order of operations):**
- `BrainOrchestrator.__init__` calls `_ensure_graph_sync()` once at construction.
- No other caller. D1 is local to the function body.

**Sideways (paired-write atomicity):**
- Sentinel discipline + SQL version bump now both gated on full Kuzu success. P0.X SCHEMA_MIGRATION pattern is strengthened, not weakened.
- The `_persist_extraction_to_kuzu` SWALLOW pattern (line 6854) reads `_kuzu_degraded` to skip Kuzu writes — unchanged by D1.

**Lifecycle:** On every cold start, `_ensure_graph_sync` runs idempotently. With D1, partial failures naturally re-enter on next boot via the unchanged predicate. Stable convergent.

### §4.2 D2 (HealthSnapshot.kuzu_degraded field)

**Forward (consumers of HealthSnapshot):**
- `format_health_line(s)` reads fields to build the one-line pulse.
- `format_health_alerts(s, brain_orchestrator)` reads fields to build per-issue alert lines.
- Dashboard or external consumers MAY iterate `dataclasses.fields(snap)` — backward-compatible since the new field has default `False`.

**Backward (producer / writer):**
- `gather_health_snapshot()` is the sole producer. Reads `brain_orchestrator._kuzu_degraded` with defensive `getattr(..., False)` to handle the case where the orchestrator is None or pre-init.

**Sideways (parallel observability):**
- `event_log_drops` / `event_log_emit_failures` follow the same "conditional-emit + actionable alert" pattern. D2 is symmetric — same shape, different surface. No conflict.

**Lifecycle:** Snapshot is recomputed every health emit (every 300s). Field is read-only post-construction. No mutation.

---

## §5. Cross-spec impact analysis

**P0.5 (FAISS atomicity):** No interaction. FAISS sentinel discipline is independent of Kuzu sentinel discipline.

**P0.X (Kuzu↔brain.db SCHEMA_MIGRATION/RAISE/SWALLOW patterns):** D1 strengthens the SCHEMA_MIGRATION pattern. P0.X locked the invariant "SQL-first for paired writes." D1 specifies that this invariant DOES NOT apply to the schema-upgrade case — schema upgrade has fundamentally different ordering semantics (the "intent" lives in the version constant, not the SQL row; the "fact" of upgrade-completion lives in the SQL row). Plan v1 must update P0.X's documented pattern + the test in `tests/test_kuzu_atomicity_invariants.py` that asserts the SCHEMA_MIGRATION ordering shape.

**P0.S7.D-B (RELATES_TO `privacy_level` column, v2→v3 bump):** This is the ACTUAL motivating example. The current code's silent-degradation behavior on schema upgrade IS the failure mode Skeptic1 highlighted — a crash during the v2→v3 upgrade in production would have permanently broken cross-person privacy enforcement. D1 closes the upgrade-safety gap that P0.S7.D-B inadvertently surfaced.

**P0.9 (schema migration framework):** No structural change. P0.9 lives in `core/schema_migrations.py` for brain.db / faces.db / classifier.db. Kuzu's wipe+rebuild mechanism is fundamentally different (Kuzu cannot ALTER REL TABLE) and stays outside P0.9's framework by design. D1 is a localized Kuzu-side fix.

**Wave 5 Item 19 (health log infrastructure):** D2 extends `HealthSnapshot` + the existing format helpers. Backward-compatible field addition. No conflict.

**P0.0.7 (event log subsystem):** D2 mirrors the `event_log_drops` conditional-emit pattern — same observability commitment, different surface.

**P0.B1 + P0.B2 (prior Board-bug cycles):** No interaction. Different subsystems.

---

## §6. Cadence prediction

**SMALL-band (1-2 D-decisions, low fan-out, 5-7 logical anchors)** → **v1 only OPTIONAL-Plan-v2 path**.

Comparable to P0.B1 (1 D-decision, single-subsystem migration → v1 + closure). P0.B2's HEAVY-band v1→v2→v3 cadence does NOT apply here — D1+D2 are localized fixes without the multi-surface fan-out P0.B2 had (5 production sites + 3 test layers + sentinel ordering).

**If Plan v1 surfaces ≥1 precision item** (e.g. existing tests need re-pointing, or D2 needs additional fields surfaced) → escalate to Plan v2. Cleanly aligns with `### Phase-0-granular-decomposition-enables-accurate-estimates` doctrine (decomposed Phase 0 + named edit sites → narrow estimate).

---

## §7. Q5 baseline estimation

**Per `### Phase-0-granular-decomposition-enables-accurate-estimates` doctrine:**

Estimate range: **5-8 logical anchors**, mid-range **6-7**.

Breakdown:
- D1 (3 anchors): function-source-inspection ordering invariant + slow-tier crash-injection mid-drop_schema + slow-tier crash-injection mid-rebuild.
- D2 (2-3 anchors): HealthSnapshot field present + format_health_line conditional emit + format_health_alerts actionable text.
- Cross-cutting (1 anchor): existing `tests/test_kuzu_atomicity_invariants.py` SCHEMA_MIGRATION pattern test updated to assert NEW ordering.

Plan v1 will lock anchor count + auditor confirms / refines mid-range estimate. ON-TARGET band per Plan v3 (P0.B2 precedent) = ±15% of mid-range → ON-TARGET if closure lands in [6, 7, 8] (using mid 7).

---

## §8. Open questions for auditor (3 items)

**Q1 — Should D1's `_did_schema_upgrade` flag be exposed externally (e.g. surfaced in HealthSnapshot at next health emit)?**

Architect lean: NO. The flag is an in-function state-machine variable. Exposing it would conflate "we just did an upgrade this boot" with "we're degraded" — distinct concerns. D2 surfaces the degraded state cleanly. Plan v1 absorbs as locked rationale.

**Q2 — Should `_kuzu_degraded` persist across process restarts via a `.degraded` sentinel file?**

Architect lean: NOT in P0.B3 scope. Today's behavior: the flag is in-memory + the underlying schema mismatch persists on disk → next boot re-attempts sync and re-discovers degradation if it persists. If recovery succeeds on retry, the flag clears naturally. Persistent degraded sentinel would help recovery-tracking but adds another sentinel file + state-machine complexity. File P0.B3.X follow-up if production canary shows operators benefit from persistent marking.

**Q3 — Should D2's `format_health_alerts` message hardcode the recovery procedure or reference a doc URL?**

Architect lean: HARDCODE the procedure in the alert string. Doc URLs rot; operator-recovery instructions need to be inline in the alert so a future maintainer / on-call operator sees the recovery path WITHOUT navigation. Three lines max. The procedure is small and stable ("delete the Kuzu directory; brain.db facts rebuild on next start").

---

## §9. Discipline counts at Phase 0 close

**Post-P0.B2 ratified baseline (per Cycle 2 auditor verdict):**

| Discipline | Baseline | After P0.B3 Phase 0 |
|---|---|---|
| Spec-first review cycle | 46 | **47** (+1 Phase 0 artifact per locked +1-per-artifact convention) |
| Strict-industry-standard mode | 36 + 10 closures | **37 applications + 10 closures** (Phase 0 +1; closure deferred until cycle close) |
| `### Phase-0-granular-decomposition-enables-accurate-estimates` | 9 supporting | stays 9 (no closure yet) |
| `### Phase-0-catches-wrong-premise` | 7 | stays 7 (premise fully on-target this cycle — NOT a wrong-premise instance) |
| `### Twin-filename-pitfall-prevention` (elevated doctrine) | 7 + 4 op rules | stays 7 (preventive at audit drafting; clean disambiguation against zero pre-existing P0.B3 artifacts; counted at doctrine-elevation precedent per the doctrine's instance-enumeration rule — preventive uses without a gap-catch don't auto-bump) |
| Deferred-canary | 10th in-flight | **11th application in-flight** ✓ (per auditor verdict 2026-05-21 — each spec cycle = +1 in-flight application; closure cancels into to_be_checked.md entry per the locked strategy) |
| Auditor-Q5-estimates-trail-grep | 14 banked closures | **14 banked + 1 in-flight** (P0.B3 = 12th-projection at SMALL-band mid 6) ✓ per auditor Phase 0 verdict |
| Cross-cycle-handoff transparency precedent | 9 successful | **10th successful** ✓ per auditor verdict (architect honored P0.B2 closure verdict's supplemented counts at Phase 0 baseline grep — auditor verdict → architect adoption at next cycle → no silent drift; transparency precedent working end-to-end) |
| Architect-reads-production-code-before-sign-off | 7 banked | stays 7 (closure-audit pending) |
| Sub-pattern A (now elevated as Phase-0-catches-wrong-premise) | 7 | stays 7 |
| Spec-time grep-verification | 13 | **14** (Phase 0 §1 + §1.5 Pass-1 grep enumerated all 3 _kuzu_degraded writer sites + 0 cross-DB consumers + board-meeting cross-reference — instance bumped at Phase 0 audit drafting) |
| Discipline-count-bump-needs-explicit-justification | 10 preventive | stays 10 |
| Convention-drift-on-discipline-counts (parent) | 4 | stays 4 (no count drift surfaced yet) |
| Per-artifact-arithmetic-drift-survives-grep-baseline (child) | 1 | stays 1 |
| Explicit-closure-honest-count-commitment | 4 | stays 4 (commitment-making pending Plan v1/v2 if applicable) |
| Grep-baseline-before-drafting | 3 | **4** (Phase 0 audit drafted from Post-P0.B2 ratified baseline — 4th instance preventive) |
| Auditor-catches-Q5-math-at-plan-review | 2 | stays 2 |
| HEAVY-band cadence (working hypothesis) | 2 | stays 2 (P0.B3 is SMALL-band — does NOT add evidence either way) |

**Phase 0 commitments banked for closure-audit:**

1. Spec-first review cycle expected at closure: 47 (Phase 0) + 1 (Plan v1) + (+1 if Plan v2) + 1 (closure) per +1-per-artifact convention.
2. Q5 estimate range LOCKED at 5-8 anchors, mid 6-7. Closure-actual reading triggers band-table disposition per P0.B2 precedent.
3. `### Phase-0-catches-wrong-premise` NOT activated this cycle (premise verified ON-TARGET via board-meeting + grep cross-reference at §1.5).
4. Cadence: SMALL-band v1 only, OPTIONAL-Plan-v2 path if Plan v1 surfaces ≥1 precision item.

---

## §10. Open invariants for Plan v1 to enumerate

1. **D1 ordering invariant** — explicit AST-line-order test that `update_graph_schema_version` call lineno > `rebuild` call lineno > `_init_schema` call lineno > `_mark_kuzu_dirty` call lineno inside `_ensure_graph_sync`.

2. **D1 idempotency invariant** — slow-tier crash injection at each of 3 distinct points (mid-drop_schema, mid-_init_schema, mid-rebuild) must converge after one restart with `stored_version` updated correctly and `_kuzu_degraded=False`.

3. **D2 conditional-emit invariant** — `format_health_line` returns string WITHOUT `kuzu=degraded` when `kuzu_degraded=False`, WITH the literal `kuzu=degraded` substring when True.

4. **D2 actionable-alert invariant** — `format_health_alerts` includes the literal recovery procedure ("delete the Kuzu directory" + path resolution) when `kuzu_degraded=True`.

5. **D2 default-False invariant** — `HealthSnapshot.kuzu_degraded` defaults to False; existing callers of `gather_health_snapshot` without a Kuzu-aware orchestrator get clean default.

6. **No-side-effect-in-Phase-0 invariant** (closure-narrative discipline) — this Phase 0 audit landed with zero production code changes. All §1 grep results are read-only.

---

**End of Phase 0 audit.** Ready to forward to auditor.

**Architect's request to auditor:** confirm pre-audit premise + Phase 0 scope decomposition + D1/D2 are the right shape + cadence prediction (SMALL-band v1 only OPTIONAL-Plan-v2) is defensible. 3 open questions at §8 await adjudication.
