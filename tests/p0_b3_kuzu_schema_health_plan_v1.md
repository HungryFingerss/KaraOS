# P0.B3 Plan v1 — Kuzu schema migration ordering + Kuzu health observable (D1 + D2 contract lock)

**Phase 0 base:** `tests/p0_b3_kuzu_schema_health_audit.md` (auditor APPROVED 2026-05-21 with all 3 open questions adjudicated to architect leans + Q5 band locked at 4-8 mid 6 + 0 open precision items at Phase 0 review — `Phase-0-zero-precision-items-at-auditor-review` 1st instance banked).

**Plan v1 absorbs (proactively, all 4 anticipated precision items from auditor verdict):**

- **P1** §1 Pass-2 grep enumeration of existing P0.X SCHEMA_MIGRATION tests + explicit REVERSAL of the `test_ensure_graph_sync_sql_first_before_kuzu_ops` invariant which today asserts the BUG ordering.
- **P2** §3 D2 HealthSnapshot field shape — `kuzu_degraded: bool` grep-verified against the `event_log_drops: int` conditional-emit pattern at `core/health.py:37-38, 187-192, 244-256`.
- **P3** §2 D1 ORDERING INVARIANT comment template (10-step verbatim format per P0.B2 precedent).
- **P4** §5 Closure-narrative paste-template (5-surface landing format per P0.B2 §2 precedent) + §6 Closure-actual projection per `Explicit-closure-honest-count-commitment` discipline (5th instance to be banked on Plan v1 sign-off + Plan v2 if applicable).

Cadence prediction: **v1 only OPTIONAL-Plan-v2 path** per Phase 0 §6. Plan v2 escalation possible if auditor surfaces ≥1 unresolved precision item; realistically the closure-template lock + ORDERING INVARIANT comment text may merit explicit v2 verification per the P0.S6 / P0.S7 precedent.

---

## §1. P1 — Pass-2 grep enumeration of existing P0.X tests

### §1.1 Existing tests touching `update_graph_schema_version` / `_ensure_graph_sync` (3 files)

**File 1 — `tests/test_kuzu_atomicity_invariants.py`** (P0.X structural-invariant suite, 28 tests):

| Line | Test | Asserts | D1 impact | Disposition |
|---|---|---|---|---|
| 195-207 | `test_ensure_graph_sync_checks_sentinel_and_count_mismatch` | Sentinel + entity-count mismatch are both checked | **No change** — boot reconciliation logic unchanged in D1 | KEEP |
| 210-225 | `test_ensure_graph_sync_sets_degraded_on_rebuild_failure` | `_kuzu_degraded=True` in except block | **No change** — except handlers unchanged in D1 | KEEP |
| 228-237 | `test_ensure_graph_sync_clears_sentinel_on_success` | `_clear_kuzu_dirty()` after rebuild | **No change** — D1 preserves clear-on-success; D1 just moves `update_graph_schema_version` AFTER this point | KEEP |
| **240-260** | **`test_ensure_graph_sync_sql_first_before_kuzu_ops`** | `commit_line < drop_line` (SQL-first BEFORE Kuzu ops) | **REVERSE** — this test ENCODES the bug; D1's fix means the assertion must INVERT to `commit_line > clear_dirty_line` (SQL-AFTER full Kuzu success) | **MIGRATE — rename + invert** |

**File 2 — `tests/test_kuzu_brain_atomicity.py`** (P0.X behavioral crash-injection suite, ~10 slow-tier tests):

| Line | Test | Asserts | D1 impact | Disposition |
|---|---|---|---|---|
| 129-164 | `test_schema_upgrade_drop_schema_failure_writes_sentinel` | Sentinel exists when drop_schema crashes + constructor degraded-mode | **No change** — sentinel discipline unchanged | KEEP |
| 167-195 | `test_schema_upgrade_init_schema_failure_writes_sentinel` | Sentinel persists through `_init_schema` failure | **No change** — sentinel discipline unchanged | KEEP |
| 198-229 | `test_schema_upgrade_sql_commit_failure_writes_sentinel` | SQL UPDATE failure leaves stored_version unchanged + sentinel present | **NUANCED CHANGE** — pre-D1: SQL fails after sentinel write before Kuzu ops (SQL-first). Post-D1: SQL fails after Kuzu rebuild succeeds. Assertion "stored_version unchanged + sentinel present" holds either way (SQL never committed → version unchanged; sentinel preserved through failure). **No assertion change needed** but the test docstring's pre/post-fix narrative needs an update to reflect the new ordering. | KEEP + docstring update |

**File 3 — `tests/test_graph_db_drop_schema.py`** (P0.X drop_schema-error-propagation, 1 test):

| Line | Test | Asserts | D1 impact | Disposition |
|---|---|---|---|---|
| All ~50 lines | `test_drop_schema_propagates_kuzu_errors` | `drop_schema` doesn't silently swallow Kuzu errors — propagates so `_ensure_graph_sync` can catch + set degraded | **No change** — D1 doesn't touch `drop_schema` semantics; only reorders the SQL commit relative to the rebuild | KEEP |

**Summary:** 1 test REVERSAL (file 1, lines 240-260) + 1 docstring update (file 2, lines 198-229) + 7 tests unchanged. Net delta: 0 deletions, 0 additions to existing tests. New anchors land in a NEW file (`tests/test_p0_b3_kuzu_schema_health.py`) per the per-spec test-file convention.

### §1.2 Pass-2 grep — production-code call sites of `update_graph_schema_version`

Production:
- `core/brain_agent.py:826` — `BrainDB.update_graph_schema_version` method definition.
- `core/brain_agent.py:6721` — `_ensure_graph_sync` call site (the BUG site; D1 RELOCATES this call).
- No other production callers (grep-verified).

Tests:
- `tests/test_kuzu_atomicity_invariants.py:251` — `_first_call_lineno(method, "update_graph_schema_version(")` (re-pointed by D1 — same find, opposite assertion).
- `tests/test_kuzu_brain_atomicity.py:213` — `"UPDATE brain_state SET graph_schema_version" in s` (substring filter for the proxy that intercepts the SQL UPDATE; works identically under D1).

**D1 invariant lock:** the `update_graph_schema_version` call MUST appear in `_ensure_graph_sync`'s function body exactly ONCE (preserve current cardinality) but its lineno MUST be AFTER both `self._graph_db.rebuild(` AND `self._clear_kuzu_dirty()` call linenos. AST structural test at §4.1 D1.4 enforces this.

### §1.3 Pass-2 grep — production-code call sites of `_kuzu_degraded`

Production (5 sites):
- `core/brain_agent.py:6677` — declaration (`self._kuzu_degraded: bool = False`).
- `core/brain_agent.py:6728` — writer in `_ensure_graph_sync` migration-block except handler.
- `core/brain_agent.py:6741` — reader in `_ensure_graph_sync` rebuild-branch gate.
- `core/brain_agent.py:6764` — writer in `_ensure_graph_sync` rebuild-branch except handler.
- `core/brain_agent.py:6854` — reader in `_persist_extraction_to_kuzu` SWALLOW gate.

Tests (3 references):
- `tests/test_kuzu_atomicity_invariants.py:223` — `self._kuzu_degraded = True` substring check.
- `tests/test_kuzu_brain_atomicity.py:156` — `orch._kuzu_degraded` read in degraded-mode assertion.
- `tests/test_kuzu_atomicity_invariants.py:211` — test docstring reference.

**D2 reader-site:** `core/health.py::gather_health_snapshot()` reads `brain_orchestrator._kuzu_degraded` via `getattr(..., False)` defensive pattern (matches the existing brain.db query block at lines 84-99 + event_log lazy-import pattern at lines 122-134). NEW reader site, no new writer sites.

---

## §2. D1 LOCK — `_ensure_graph_sync()` re-ordering + ORDERING INVARIANT comment template

### §2.1 D1 contract (LOCKED at Plan v1)

**Function:** `BrainOrchestrator._ensure_graph_sync()` at `core/brain_agent.py:6696-6765`.

**Mechanism (10-step verbatim per P0.B2 ORDERING INVARIANT comment block template):**

```python
def _ensure_graph_sync(self) -> None:
    """Rebuild graph from SQLite if needed.

    Handles two cases:
    1. Cold start / crash recovery: graph is empty but SQLite has rows.
    2. Schema upgrade: GRAPH_SCHEMA_VERSION bumped — Kuzu REL tables can't
       be ALTER TABLE'd, so we wipe the graph and rebuild with new schema.

    P0.B3 D1 ORDERING INVARIANT (Finding 2 board-meeting 2026-05-21 fix):
      1. Capture `_did_schema_upgrade = (stored_version < GRAPH_SCHEMA_VERSION)`
         at function entry — BEFORE any state mutation. This is the in-flight
         intent flag; tells the success path whether to commit the SQL version
         bump at the end.
      2. _mark_kuzu_dirty() FIRST — sentinel SET BEFORE any destructive op.
      3. IF schema upgrade pending: drop_schema() + _init_schema() (Kuzu ops).
         Crash here: kuzu_degraded=True, sentinel persists, stored_version=OLD
         → next boot re-enters via predicate at step 1.
      4. Compute need_rebuild via the migration-block-success OR boot-reconciliation
         (sentinel-exists OR entity-count-mismatch).
      5. IF need_rebuild AND NOT degraded: rebuild(knowledge_rows). Crash here:
         kuzu_degraded=True, sentinel persists, stored_version=OLD → next boot
         re-enters via predicate at step 1.
      6. _clear_kuzu_dirty() ONLY after rebuild() success.
      7. IF `_did_schema_upgrade` AND NOT degraded: update_graph_schema_version(NEW)
         — SQL commit ONLY at the end, AFTER Kuzu schema + data both at NEW + sentinel
         cleared. This is the LOAD-BEARING fix: pre-P0.B3 the SQL bump happened at step
         3-pre-Kuzu-ops, which left SQL=NEW + Kuzu=PARTIAL on crash; the migration
         predicate at step 1 became FALSE on next boot, silently trapping the system
         in permanent _kuzu_degraded=True with no operator-visible recovery signal.
         Post-P0.B3 the SQL bump lands ONLY at full success; any crash before this
         leaves stored_version=OLD → next boot retries idempotently.
      8. Sentinel-only rebuild paths (boot reconciliation, count mismatch) MUST NOT
         bump the SQL version — `_did_schema_upgrade=False` gates this correctly.
      9. degraded-mode caught-but-unfixable crashes leave sentinel + stored_version=OLD
         on disk → next process restart re-enters the migration block fresh + retries.
     10. Cross-spec invariant: P0.X SCHEMA_MIGRATION pattern's "SQL-first" framing
         applies to paired DATA writes (brain.db row + Kuzu edge). For the version
         BUMP itself, SQL-LAST is correct because SQL is the source-of-truth FOR
         which schema-state-is-canonical — committing it prematurely commits a
         lie. P0.X behavior for paired data writes is unchanged.
    """
    _did_schema_upgrade = self._brain_db.get_graph_schema_version() < GRAPH_SCHEMA_VERSION
    stored_version = self._brain_db.get_graph_schema_version()  # local var for the print

    need_rebuild = False
    if _did_schema_upgrade:
        print(
            f"[BrainAgent] Graph schema v{stored_version}→v{GRAPH_SCHEMA_VERSION}: "
            "wiping Kuzu graph for rebuild with new schema"
        )
        # P0.B3 D1: SQL version bump REMOVED from this block per Finding 2 fix.
        # Sentinel + Kuzu ops only here; SQL commit deferred to step 7 below.
        self._mark_kuzu_dirty()
        try:
            self._graph_db.drop_schema()
            self._graph_db._init_schema()
            need_rebuild = True
        except Exception as e:
            self._kuzu_degraded = True
            print(f"[BrainAgent] Graph schema migration failed — degraded mode: {e!r}")

    # Boot reconciliation: sentinel OR entity-count mismatch (unchanged).
    if not need_rebuild:
        if self._kuzu_sentinel_path().exists():
            need_rebuild = True
        else:
            sql_entity_count = self._brain_db.count_active_knowledge_entities()
            kuzu_entity_count = self._graph_db.entity_count()
            if sql_entity_count != kuzu_entity_count:
                need_rebuild = True

    if need_rebuild and not self._kuzu_degraded:
        knowledge_rows = self._brain_db.get_all_knowledge_rows()
        try:
            if knowledge_rows:
                _rebuild_t0 = time.time()
                self._graph_db.rebuild(knowledge_rows)
                _rebuild_secs = time.time() - _rebuild_t0
                _ent_count = self._graph_db.entity_count()
                print(
                    f"[BrainAgent] Graph rebuilt from {len(knowledge_rows)} SQLite rows"
                )
                print(
                    f"[Schema] Graph rebuild v{stored_version}→v{GRAPH_SCHEMA_VERSION} "
                    f"completed in {_rebuild_secs:.2f}s "
                    f"({_ent_count} entities, {len(knowledge_rows)} edges)"
                )
            self._clear_kuzu_dirty()
            # P0.B3 D1: SQL commit ONLY here — after rebuild success + sentinel clear.
            # Gated on `_did_schema_upgrade` so sentinel-only rebuilds (boot reconciliation,
            # count mismatch) do NOT bump the version. See §2.1 of plan v1 for rationale.
            if _did_schema_upgrade:
                self._brain_db.update_graph_schema_version(GRAPH_SCHEMA_VERSION)
        except Exception as e:
            self._kuzu_degraded = True
            print(f"[BrainAgent] Graph rebuild failed at boot — degraded mode: {e!r}")
```

### §2.2 Crash-safety table (post-D1)

| Crash point | After-crash state | Next boot behavior | Outcome |
|---|---|---|---|
| Pre step 2 (sentinel mark) | (no mutation) | Predicate `stored_version=OLD < NEW` → enter migration block → retry from scratch | ✓ Recovers |
| Step 2 mid-sentinel | sentinel only | Predicate true → enter migration → idempotent retry | ✓ Recovers |
| Step 3 mid-drop_schema | sentinel + Kuzu schema partial + SQL=OLD | Predicate `stored_version=OLD < NEW` → re-enter migration → drop_schema idempotent (DROP IF EXISTS) → succeed → continue | ✓ Recovers |
| Step 3 mid-_init_schema | sentinel + Kuzu schema partial + SQL=OLD | Same as above — predicate retries from scratch | ✓ Recovers |
| Step 4 boot-recon decision | (transient — no persistent mutation) | N/A | ✓ |
| Step 5 mid-rebuild | sentinel + Kuzu schema NEW + Kuzu data partial + SQL=OLD | Predicate true → re-enter migration block → drop+reinit (idempotent — already at NEW) → rebuild (clean re-population) → succeed → SQL commit at step 7 | ✓ Recovers |
| Step 6 between rebuild + clear_dirty | sentinel + Kuzu fully NEW + SQL=OLD | Predicate true → re-enter → drop+reinit idempotent → rebuild (REDUNDANT but idempotent — clean re-population from same knowledge_rows) → succeed → SQL commit | ✓ Recovers (with one extra rebuild — performance gnat, not correctness) |
| Step 7 mid-SQL-commit | sentinel cleared + Kuzu fully NEW + SQL=OLD-or-NEW (atomicity dep) | If SQL commit succeeded atomically: stored_version=NEW → predicate FALSE → skip migration. Sentinel cleared → no rebuild trigger → consistent state. If SQL commit failed: stored_version=OLD → predicate true → migration re-runs (idempotent) → succeed | ✓ Recovers (SQLite COMMIT atomicity guarantees one or the other) |
| Step 8 sentinel-only rebuild paths | (unchanged from current behavior) | Boot reconciliation handles | ✓ Recovers |
| Step 9 degraded-mode (drop_schema or rebuild raises) | sentinel + stored_version=OLD + degraded flag in-memory only | Next process restart: degraded flag fresh-False, predicate true, retry the upgrade | ✓ Recovers on restart |

**No regression in P0.X SCHEMA_MIGRATION pattern recovery guarantees.** All crash points have a convergent next-boot recovery path. Step 7 (the SQL commit itself) is now the ONLY point where the upgrade "commits" persistently; SQLite's COMMIT atomicity makes this a single instant.

### §2.3 Why D1 doesn't break the P0.X "SQL-first" framing

P0.X's locked invariant: "for paired writes between brain.db (SQL) and Kuzu (graph), SQL is committed FIRST so a crash leaves SQL with authoritative data + Kuzu sentinel set for next-boot rebuild."

This applies to **DATA writes** — `on_identity_confirmed` storing knowledge + Kuzu edges, `_persist_extraction_to_kuzu` storing extractions + Kuzu edges. The SQL row IS the canonical fact; the Kuzu edge is derived state that can be reconstructed.

**For the SCHEMA-VERSION bump itself, SQL is NOT the derived state — it's the COORDINATION SIGNAL.** Committing it prematurely commits a lie ("we claim to be at v3") while the actual reality is still in progress. D1's correctness argument: the version row should track "completed migration to NEW," not "intent to migrate to NEW." Same observability commitment as the sentinel discipline — both are state markers, but they track different state-machine states:
- **Sentinel** = "an upgrade is in flight; consult this on next boot for reconciliation."
- **`graph_schema_version`** = "the upgrade to this version completed cleanly."

Locked language for the comment block: **"P0.X SCHEMA_MIGRATION's SQL-first framing applies to paired DATA writes. For the version BUMP itself, SQL-LAST is correct because SQL is the source-of-truth FOR which schema-state-is-canonical."** (Step 10 of the ORDERING INVARIANT comment, verbatim.)

---

## §3. D2 LOCK — HealthSnapshot.kuzu_degraded + conditional emit + actionable alert

### §3.1 D2 contract (LOCKED at Plan v1)

**Files touched:** `core/health.py` (single subsystem).

**Sub-contract 1 — Dataclass field addition (lines 10-38):**

```python
@dataclass
class HealthSnapshot:
    # ... [existing 15 fields unchanged] ...
    event_log_drops: int = 0
    event_log_emit_failures: int = 0
    # P0.B3 D2 — Kuzu graph degraded-mode observability.
    # `kuzu_degraded`: True iff BrainOrchestrator._kuzu_degraded is True in
    #     the current process. Set when graph schema upgrade fails (drop_schema
    #     or _init_schema raises) or when boot rebuild from knowledge rows
    #     raises. In degraded mode: graph queries silently return empty;
    #     cross-person privacy traversal (find_shared_entities) is broken;
    #     the P0.S7.D-B privacy-on-edges fix is bypassed. Recovery requires
    #     operator intervention: stop pipeline + delete the Kuzu directory
    #     + restart (brain.db facts will rebuild on next start). The
    #     format_health_alerts() output embeds the recovery procedure
    #     verbatim — operator never needs to grep logs or read source.
    # In-memory flag only — does not persist across process restarts.
    # Next boot's _ensure_graph_sync may set or clear it anew depending on
    # actual schema-state convergence (see P0.B3 audit §3.5).
    kuzu_degraded: bool = False
```

**Sub-contract 2 — Gather wiring (lines 84-99 pattern, new try-block):**

```python
# In gather_health_snapshot(), after the existing brain.db block:
try:
    kuzu_degraded = bool(getattr(brain_orchestrator, "_kuzu_degraded", False))
except Exception:
    # CLEANUP: defensive — brain_orchestrator may be partial during boot.
    # Default to False (not-degraded) rather than True, so the health
    # snapshot doesn't false-alarm during early-boot windows.
    kuzu_degraded = False
```

Plus thread `kuzu_degraded=kuzu_degraded` into the `return HealthSnapshot(...)` call at lines 136-153.

**Sub-contract 3 — `format_health_line` conditional emit (mirrors `event_log_drops` pattern at lines 187-192):**

```python
# In format_health_line(), after the existing evlog_parts collection:
# P0.B3 D2 — surface kuzu_degraded only when True (clean health line
# in steady-state; non-zero state tags the surface explicitly).
kuzu_parts: list[str] = []
if s.kuzu_degraded:
    kuzu_parts.append("kuzu=degraded")
kuzu_str = (" | " + " ".join(kuzu_parts)) if kuzu_parts else ""

return (
    # ... existing f-string ...
    f"{evlog_str}"
    f"{kuzu_str}"  # <-- new line
)
```

**Sub-contract 4 — `format_health_alerts` actionable alert (mirrors `event_log_drops` pattern at lines 244-256):**

```python
# In format_health_alerts(), after the existing event_log alerts:
# P0.B3 D2 — Kuzu degraded-mode actionable recovery alert.
if s.kuzu_degraded:
    # Resolve the graph DB path for the recovery instruction; defensive
    # try/except so a missing attribute doesn't break the alert format.
    try:
        from pathlib import Path
        _gp = getattr(brain_orchestrator, "_graph_db_path", "<unknown>")
        _gp_resolved = str(Path(_gp).resolve()) if _gp != "<unknown>" else "<unknown>"
    except Exception:
        # CLEANUP: path resolution failure — emit alert with literal placeholder.
        _gp_resolved = "<graph_db_path>"
    alerts.append(
        f"[Health-Alert] Kuzu graph in degraded mode — graph queries "
        f"returning empty (cross-person traversal broken; privacy "
        f"enforcement on RELATES_TO edges bypassed). "
        f"Recovery: stop pipeline, run `rm -rf {_gp_resolved}`, restart. "
        f"brain.db facts will rebuild from SQLite on next start."
    )
```

### §3.2 Why `bool` (not `int`) for `kuzu_degraded`

The existing `event_log_drops: int` counts cumulative drops over the process lifetime (writer-task falling behind multiple times). Useful for trend detection.

`kuzu_degraded` is a binary state — either we ARE degraded (`find_shared_entities` returns empty + Kuzu writes silently skip) or we are NOT. There's no meaningful "count of degraded events" because degradation persists until process restart OR operator intervention; it doesn't toggle within a single process lifetime under normal operation.

Locked: `bool` not `int`. The conditional-emit pattern is identical for both.

### §3.3 Recovery-instruction text LOCK (per Q3 auditor adjudication)

**Literal alert string (exact substring CI-tested at §4 D2 anchor 3):**

```
[Health-Alert] Kuzu graph in degraded mode — graph queries returning empty (cross-person traversal broken; privacy enforcement on RELATES_TO edges bypassed). Recovery: stop pipeline, run `rm -rf <path>`, restart. brain.db facts will rebuild from SQLite on next start.
```

**Substrings the test MUST verify present (per §4 D2 anchor 3):**
- `Kuzu graph in degraded mode`
- `Recovery: stop pipeline`
- `` `rm -rf ` `` (the command)
- `restart`
- `brain.db facts will rebuild`

**Substrings the test MUST verify ABSENT** (to prevent regression to doc-URL form per Q3 lock):
- `http://` / `https://` / `docs.` / `see the wiki`
- `consult logs` / `check documentation`

### §3.4 Backward compatibility — HealthSnapshot field addition

`HealthSnapshot` is reconstructed every emit; no persistent snapshots exist. Adding `kuzu_degraded: bool = False` field with a `False` default:
- Existing `gather_health_snapshot()` callers that don't pass the new field: still work (default applies).
- Existing `format_health_line` consumers iterating fields: backward-compatible (new field appears at end of dataclass field order).
- No JSON serialization in production paths (`format_health_line` is f-string; no `dataclasses.asdict()` serializer in current callers).

No regression risk.

---

## §4. Test surface — 6 anchors + 1 existing-test migration

### §4.1 D1 anchors (3 logical anchors — `tests/test_p0_b3_kuzu_schema_health.py` NEW file)

**D1 Anchor 1 — ORDERING INVARIANT AST line-order:**

```python
def test_d1_ensure_graph_sync_sql_commit_after_kuzu_rebuild():
    """P0.B3 D1: update_graph_schema_version lineno > rebuild lineno > _clear_kuzu_dirty lineno."""
    source = _read_source(BRAIN_AGENT_PATH)
    tree = ast.parse(source)
    method = _find_method_in_class(tree, "BrainOrchestrator", "_ensure_graph_sync")
    assert method is not None

    commit_line = _first_call_lineno(method, "update_graph_schema_version(")
    rebuild_line = _first_call_lineno(method, "self._graph_db.rebuild(")
    clear_dirty_line = _first_call_lineno(method, "_clear_kuzu_dirty(")
    drop_line = _first_call_lineno(method, "drop_schema(")
    mark_dirty_line = _first_call_lineno(method, "_mark_kuzu_dirty(")

    assert mark_dirty_line is not None, "must call _mark_kuzu_dirty()"
    assert drop_line is not None, "must call drop_schema()"
    assert rebuild_line is not None, "must call rebuild()"
    assert clear_dirty_line is not None, "must call _clear_kuzu_dirty()"
    assert commit_line is not None, "must call update_graph_schema_version()"

    assert mark_dirty_line < drop_line, "P0.B3 D1: sentinel mark must precede drop_schema"
    assert drop_line < rebuild_line, "P0.B3 D1: drop_schema must precede rebuild()"
    assert rebuild_line < clear_dirty_line, "P0.B3 D1: rebuild must precede _clear_kuzu_dirty"
    assert clear_dirty_line < commit_line, (
        "P0.B3 D1 (Finding 2 board-meeting 2026-05-21 fix): "
        "update_graph_schema_version() MUST appear AFTER _clear_kuzu_dirty(). "
        "Pre-fix the SQL commit happened BEFORE Kuzu rebuild — crash-window left "
        "SQL=NEW + Kuzu=PARTIAL, trapping next boot in permanent _kuzu_degraded."
    )
```

**D1 Anchor 2 — Slow-tier crash-injection mid-drop_schema:**

```python
@pytest.mark.slow
def test_d1_crash_mid_drop_schema_leaves_sql_version_old(tmp_path, monkeypatch):
    """P0.B3 D1: drop_schema raises → SQL version UNCHANGED → next boot retries."""
    orch1 = _make_orch(tmp_path)
    current_version = _get_schema_version(orch1._brain_db)
    _close_orch(orch1)
    gc.collect()

    monkeypatch.setattr(brain_agent_mod, "GRAPH_SCHEMA_VERSION", current_version + 1)
    monkeypatch.setattr(
        GraphDB, "drop_schema",
        lambda self: (_ for _ in ()).throw(RuntimeError("simulated drop crash")),
    )

    orch2 = _make_orch(tmp_path)  # constructor enters degraded mode
    try:
        assert orch2._kuzu_degraded, "must be in degraded mode after drop_schema crash"
        stored = _get_schema_version(orch2._brain_db)
        assert stored == current_version, (
            f"P0.B3 D1: stored_version advanced to {stored} despite drop crash "
            f"(expected {current_version}). SQL commit must NOT happen pre-rebuild."
        )
    finally:
        _close_orch(orch2)

    # Recovery: revert the monkeypatch, restart, verify stored_version advances cleanly.
    monkeypatch.undo()  # restore drop_schema + GRAPH_SCHEMA_VERSION
    monkeypatch.setattr(brain_agent_mod, "GRAPH_SCHEMA_VERSION", current_version + 1)
    orch3 = _make_orch(tmp_path)
    try:
        assert not orch3._kuzu_degraded, "recovery boot should clear degraded state"
        stored2 = _get_schema_version(orch3._brain_db)
        assert stored2 == current_version + 1, (
            f"P0.B3 D1 recovery: stored_version should advance to {current_version + 1} "
            f"after clean retry; got {stored2}"
        )
    finally:
        _close_orch(orch3)
```

**D1 Anchor 3 — Slow-tier crash-injection mid-rebuild:**

```python
@pytest.mark.slow
def test_d1_crash_mid_rebuild_leaves_sql_version_old(tmp_path, monkeypatch):
    """P0.B3 D1: rebuild() raises → SQL version UNCHANGED → next boot retries."""
    orch1 = _make_orch(tmp_path)
    # Seed a knowledge row so rebuild has work to do.
    orch1._brain_db._conn.execute(
        "INSERT INTO knowledge (entity, attribute, value, confidence, ...) VALUES (...)"
    )
    orch1._brain_db._conn.commit()
    current_version = _get_schema_version(orch1._brain_db)
    _close_orch(orch1)
    gc.collect()

    monkeypatch.setattr(brain_agent_mod, "GRAPH_SCHEMA_VERSION", current_version + 1)
    monkeypatch.setattr(
        GraphDB, "rebuild",
        lambda self, rows: (_ for _ in ()).throw(RuntimeError("simulated rebuild crash")),
    )

    orch2 = _make_orch(tmp_path)
    try:
        assert orch2._kuzu_degraded, "must be in degraded mode after rebuild crash"
        stored = _get_schema_version(orch2._brain_db)
        assert stored == current_version, (
            f"P0.B3 D1: stored_version advanced to {stored} despite rebuild crash "
            f"(expected {current_version}). SQL commit must NOT happen pre-_clear_kuzu_dirty."
        )
    finally:
        _close_orch(orch2)

    # Recovery boot — same shape as D1 Anchor 2.
    monkeypatch.undo()
    monkeypatch.setattr(brain_agent_mod, "GRAPH_SCHEMA_VERSION", current_version + 1)
    orch3 = _make_orch(tmp_path)
    try:
        assert not orch3._kuzu_degraded
        stored2 = _get_schema_version(orch3._brain_db)
        assert stored2 == current_version + 1
    finally:
        _close_orch(orch3)
```

### §4.2 D2 anchors (3 logical anchors — same file)

**D2 Anchor 1 — HealthSnapshot has kuzu_degraded field with bool=False default:**

```python
def test_d2_health_snapshot_has_kuzu_degraded_field():
    """P0.B3 D2: HealthSnapshot.kuzu_degraded: bool = False."""
    from dataclasses import fields
    from core.health import HealthSnapshot

    field_names = {f.name for f in fields(HealthSnapshot)}
    assert "kuzu_degraded" in field_names, "P0.B3 D2: kuzu_degraded field missing"

    snap = HealthSnapshot(
        timestamp=0.0, active_sessions=0, sessions_by_type={},
        persons_count=0, total_face_embeddings=0,
        knowledge_active_rows=0, shadow_persons_count=0,
        classifier_scenarios_active=0, classifier_scenarios_quarantined=0,
        cloud_state="ONLINE", active_disputes=0, unresolved_watchdog_alerts=0,
        last_dream_run_seconds_ago=None, thin_voice_galleries=[],
    )
    assert snap.kuzu_degraded is False, "P0.B3 D2: default must be False (not-degraded)"
```

**D2 Anchor 2 — format_health_line conditional emit:**

```python
def test_d2_format_health_line_emits_kuzu_degraded_only_when_true():
    """P0.B3 D2: format_health_line includes 'kuzu=degraded' substring iff snap.kuzu_degraded."""
    from core.health import HealthSnapshot, format_health_line

    base_kwargs = dict(
        timestamp=0.0, active_sessions=0, sessions_by_type={},
        persons_count=0, total_face_embeddings=0,
        knowledge_active_rows=0, shadow_persons_count=0,
        classifier_scenarios_active=0, classifier_scenarios_quarantined=0,
        cloud_state="ONLINE", active_disputes=0, unresolved_watchdog_alerts=0,
        last_dream_run_seconds_ago=None, thin_voice_galleries=[],
    )
    line_clean = format_health_line(HealthSnapshot(**base_kwargs, kuzu_degraded=False))
    line_degraded = format_health_line(HealthSnapshot(**base_kwargs, kuzu_degraded=True))

    assert "kuzu=degraded" not in line_clean, (
        "P0.B3 D2: 'kuzu=degraded' must NOT appear when kuzu_degraded=False"
    )
    assert "kuzu=degraded" in line_degraded, (
        "P0.B3 D2: 'kuzu=degraded' MUST appear when kuzu_degraded=True"
    )
```

**D2 Anchor 3 — format_health_alerts actionable recovery instruction (substring lock per §3.3):**

```python
def test_d2_format_health_alerts_includes_recovery_procedure_when_degraded():
    """P0.B3 D2: format_health_alerts includes verbatim recovery instructions."""
    from core.health import HealthSnapshot, format_health_alerts
    from unittest.mock import MagicMock

    base_kwargs = dict(
        timestamp=0.0, active_sessions=0, sessions_by_type={},
        persons_count=0, total_face_embeddings=0,
        knowledge_active_rows=0, shadow_persons_count=0,
        classifier_scenarios_active=0, classifier_scenarios_quarantined=0,
        cloud_state="ONLINE", active_disputes=0, unresolved_watchdog_alerts=0,
        last_dream_run_seconds_ago=None, thin_voice_galleries=[],
    )

    snap_clean = HealthSnapshot(**base_kwargs, kuzu_degraded=False)
    snap_degraded = HealthSnapshot(**base_kwargs, kuzu_degraded=True)

    mock_orch = MagicMock()
    mock_orch._brain_db._conn.execute().fetchall.return_value = []
    mock_orch._graph_db_path = "/fake/faces/brain_graph"

    alerts_clean = format_health_alerts(snap_clean, mock_orch)
    alerts_degraded = format_health_alerts(snap_degraded, mock_orch)

    # MUST be absent when not degraded
    for line in alerts_clean:
        assert "kuzu" not in line.lower(), "P0.B3 D2: no Kuzu alert when not degraded"

    # MUST be present + actionable when degraded
    kuzu_alert = "\n".join(alerts_degraded)
    assert "Kuzu graph in degraded mode" in kuzu_alert
    assert "Recovery: stop pipeline" in kuzu_alert
    assert "rm -rf" in kuzu_alert
    assert "brain.db facts will rebuild" in kuzu_alert

    # MUST NOT contain doc-URL form (Q3 LOCK)
    for forbidden in ("http://", "https://", "see the wiki", "consult docs"):
        assert forbidden not in kuzu_alert.lower(), (
            f"P0.B3 D2 Q3 LOCK violation: alert contains '{forbidden}' — "
            "recovery procedure must be HARDCODED inline, not deferred to docs."
        )
```

### §4.3 Cross-cutting anchor (1 logical anchor — existing test migration)

**Migration target — `tests/test_kuzu_atomicity_invariants.py:240-260`:**

The existing `test_ensure_graph_sync_sql_first_before_kuzu_ops` encodes the BUG. Rename + invert the assertion. Final shape:

```python
def test_ensure_graph_sync_sql_commit_after_kuzu_rebuild():
    """P0.B3 D1: update_graph_schema_version() must commit AFTER Kuzu rebuild + sentinel clear.

    Pre-P0.B3 (BUG, Finding 2 board-meeting 2026-05-21):
        SQL version bump happened BEFORE drop_schema + rebuild. On crash mid-Kuzu,
        SQL=NEW + Kuzu=PARTIAL → next boot's migration predicate FALSE → permanent
        _kuzu_degraded=True with no operator-visible recovery signal.

    Post-P0.B3 D1: SQL commit moves to AFTER _clear_kuzu_dirty().
        Any crash before the SQL commit leaves stored_version=OLD → next boot
        re-enters migration via the predicate at function entry → retries
        idempotently.
    """
    source = _read_source(BRAIN_AGENT_PATH)
    tree = ast.parse(source)
    method = _find_method_in_class(tree, "BrainOrchestrator", "_ensure_graph_sync")
    assert method is not None

    commit_line = _first_call_lineno(method, "update_graph_schema_version(")
    clear_dirty_line = _first_call_lineno(method, "_clear_kuzu_dirty(")
    rebuild_line = _first_call_lineno(method, "self._graph_db.rebuild(")

    assert commit_line is not None, "must call update_graph_schema_version()"
    assert clear_dirty_line is not None, "must call _clear_kuzu_dirty()"
    assert rebuild_line is not None, "must call rebuild()"

    assert commit_line > clear_dirty_line, (
        f"P0.B3 D1 ordering violation: update_graph_schema_version (line {commit_line}) "
        f"must appear AFTER _clear_kuzu_dirty (line {clear_dirty_line}). "
        "Pre-P0.B3 the order was reversed — Finding 2 bug."
    )
    assert commit_line > rebuild_line, (
        f"P0.B3 D1 ordering violation: update_graph_schema_version (line {commit_line}) "
        f"must appear AFTER rebuild (line {rebuild_line})."
    )
```

This is an IN-PLACE migration of the existing test — single anchor's content is REPLACED, not a new test added on top. Net delta: 0 new test functions in the file, just modified body.

### §4.4 Deliberate-regression checks (induction-surfaces-invariant-gaps protocol)

Phase 4 must execute:
- (a) Revert D1's reordering (put `update_graph_schema_version` back at the pre-fix location) → D1 anchor 1 AND the cross-cutting migrated anchor MUST fail with the ordering violation. D1 crash-injection anchors 2+3 MUST fail (stored_version advances despite simulated crash).
- (b) Remove `if _did_schema_upgrade:` gate at step 7 → sentinel-only rebuild paths would spuriously bump version → caught by... hmm, this needs a 4th anchor or be folded into anchor 2/3. Let me leave this as a NICE-TO-HAVE but not a required logical anchor.
- (c) Remove `kuzu_degraded` field from HealthSnapshot → D2 anchor 1 fails.
- (d) Remove conditional-emit in `format_health_line` → D2 anchor 2 fails.
- (e) Remove actionable recovery instruction from `format_health_alerts` → D2 anchor 3 fails.

All 5 reverts confirm the invariants are correctly anchored.

### §4.5 Total Plan v1 anchor count

| Anchor source | Count | Location |
|---|---|---|
| D1 anchors (new file) | 3 | `tests/test_p0_b3_kuzu_schema_health.py` |
| D2 anchors (new file) | 3 | same |
| Cross-cutting (migrated existing) | 1 | `tests/test_kuzu_atomicity_invariants.py` (in-place rewrite of test_ensure_graph_sync_sql_first_before_kuzu_ops) |
| **TOTAL** | **7 logical anchors** | |

**Q5 LOCK: 7 anchors.** Auditor Q5 band 4-8 mid 6. Locked-actual 7 = +16.7% SLIGHT-DRIFT-UP per Plan v3 §1.1 band-table precedent (within ±15-30% band; doctrine HOLDS at 9 supporting, no bump).

Architect commitment to honest closure-actual count per `Explicit-closure-honest-count-commitment` discipline (5th instance to be banked on Plan v1 sign-off):
- **≤3 anchors at closure → −50% FALSIFICATION TRIGGER → DEMOTES 9 → 8.**
- **4 anchors at closure → −33.3% FALSIFICATION TRIGGER → DEMOTES 9 → 8.**
- **5 anchors at closure → −16.7% SLIGHT-DRIFT-DOWN → HOLDS at 9.**
- **6 anchors at closure → 0% ON-TARGET → BUMPS 9 → 10 supporting.**
- **7 anchors at closure (Plan v1 LOCK) → +16.7% SLIGHT-DRIFT-UP → HOLDS at 9.**
- **8 anchors at closure → +33.3% FALSIFICATION TRIGGER → DEMOTES 9 → 8.**
- **≥9 anchors at closure → ≥+50% FALSIFICATION TRIGGER → DEMOTES 9 → 8.**

Closure-actual = the binding count; this commitment governs the doctrine outcome regardless of architect's preference.

---

## §5. P4 — Closure-narrative paste-template (5-surface landing per P0.B2 precedent)

When P0.B3 closes, the closure narrative MUST land verbatim across these 5 surfaces:

### §5.1 CLAUDE.md line ~3 (Last-updated line + suite count + entry summary)

Pattern (per P0.B2 closure precedent, line 3): single-line summary appended to the existing list of closed specs. Format:

```
| **P0.B3 (Kuzu schema migration ordering + Kuzu health observable) CLOSED 2026-05-XX** — [one-paragraph summary including: Bug ID (Finding 2 + Vulnerability B), surface (`core/brain_agent.py:6710-6765` + `core/health.py`), D1 fix shape (re-order SQL commit AFTER Kuzu rebuild + sentinel clear via `_did_schema_upgrade` flag), D2 fix shape (HealthSnapshot.kuzu_degraded + conditional-emit + verbatim recovery procedure), test anchor count (Plan v1 LOCK 7), Q5 closure disposition per §4.5 commitment table, doctrine count outcomes, discipline counts table delta].
```

### §5.2 `complete-plan.md` (parent) — section per spec

Pattern: dedicated section with full closure narrative. Per P0.B2 §710-770 precedent.

### §5.3 `complete-plan.md` (subdir) — same section, possibly differing slightly

Pattern: per P0.B2 subdir line 769 precedent. Twin-filename pitfall discipline applied at status flip (verify both parent + subdir surfaces).

### §5.4 `to_be_checked.md` (deferred-canary tracker)

Pattern: per P0.B2 closure precedent — entry pasted verbatim with discipline-count snapshot for end-of-P0.R11 canary validation.

### §5.5 Memory files (3 entries)

- `feedback_explicit_closure_honest_count_commitment.md`: bump 4 → 5 instances.
- `feedback_strict_industry_standard_mode.md` track-record entry: +N artifacts per +1-per-artifact convention.
- `feedback_auditor_q5_estimates_trail_grep.md`: +1 banked closure with closure-actual reading.

Plus the Convention-drift, Per-artifact-arithmetic-drift, Grep-baseline-before-drafting counters as applicable.

### §5.6 Paste-template lock per Plan v2 §2 precedent

This template is the LOCKED paste shape; deviation at closure is auditor-side-flag candidate per `Convention-drift-on-discipline-counts` discipline. Architect MUST grep-verify baseline counts at closure-narrative drafting time per `Grep-baseline-before-drafting` discipline (5th instance to be banked at closure).

---

## §6. Closure-actual projection per Explicit-closure-honest-count-commitment (5th instance)

**Architect commits BEFORE closure** (per `Explicit-closure-honest-count-commitment` discipline 5th instance candidate, to be honored at closure-audit):

Honest closure-actual count is the binding number for doctrine disposition. No silent over-bumping to claim ON-TARGET when closure lands at 7 anchors. No silent under-counting to dodge falsification. The §4.5 band table is the locked decision rule.

**Plan v1 LOCK: 7 anchors at closure projection.** Architect prediction matches the SLIGHT-DRIFT-UP band (+16.7%); doctrine `### Phase-0-granular-decomposition-enables-accurate-estimates` HOLDS at 9 supporting (no bump, no demote per the strict ±15% ON-TARGET threshold locked at P0.S7 closure adjudication 2026-05-21).

**Honest acknowledgment of architect prediction:** 7 anchors is the SLIGHT-DRIFT-UP edge of the band. If the developer at Phase 4 implementation finds a clean way to consolidate (e.g. D2 anchors 2+3 share a fixture that lets a single parametrized test cover both line + alert assertions), closure-actual could drop to 6 → ON-TARGET → doctrine bumps. If the developer surfaces an additional fixture-level test (e.g. the §4.4 "if _did_schema_upgrade gate removed" deliberate-regression check graduates to a logical anchor), closure-actual could rise to 8 → FALSIFICATION TRIGGER → doctrine demotes. Either outcome will be honestly reported.

---

## §7. Q5 closure projection table (LOCKED at Plan v1)

| Closure-actual anchor count | Math (vs mid 6) | Disposition | Doctrine effect |
|---|---|---|---|
| ≤3 anchors | `≤−50%` | **FALSIFICATION TRIGGER** | **DEMOTES 9 → 8 supporting** |
| 4 anchors | `−33.3%` | **FALSIFICATION TRIGGER** | **DEMOTES 9 → 8 supporting** |
| 5 anchors | `−16.7%` | **SLIGHT-DRIFT-DOWN** | HOLDS at 9 (no bump, no demote) |
| **6 anchors** | `0%` | **ON-TARGET** | **BUMPS 9 → 10 supporting** |
| **7 anchors (Plan v1 LOCK)** | `+16.7%` | **SLIGHT-DRIFT-UP** | HOLDS at 9 (no bump, no demote) |
| 8 anchors | `+33.3%` | **FALSIFICATION TRIGGER** | **DEMOTES 9 → 8 supporting** |
| ≥9 anchors | `≥+50%` | **FALSIFICATION TRIGGER** | **DEMOTES 9 → 8 supporting** |

Band definitions per Plan v3 §1.1 corrected band table (locked at P0.B2 closure):
- ±15% ON-TARGET = [5.1, 6.9] = only 6 anchors qualifies.
- ±15% to ±30% SLIGHT-DRIFT = 5 or 7 anchors.
- ≥±30% FALSIFICATION = ≤4 or ≥8 anchors.

---

## §8. Quality gate checklist (10 APPLIES + 1 N/A privacy)

Per strict-mode 11-gate floor:

1. ✅ **Phase 0 audit completed + auditor-approved** with 0 open precision items at review.
2. ✅ **Plan v1 absorbs all 4 anticipated precision items proactively** (P1 Pass-2 grep + P2 field shape + P3 ORDERING INVARIANT comment + P4 closure paste-template).
3. ✅ **D-decisions have unambiguous contracts** — D1 at §2.1 + D2 at §3.1.
4. ✅ **Pre-mortem coverage** — 10 failure modes documented at Phase 0 §3 with mitigation per mode.
5. ✅ **Multi-direction invariant trace per D-decision** — Phase 0 §4.
6. ✅ **Cross-spec impact analysis** — Phase 0 §5 explicitly names P0.X interaction (SCHEMA_MIGRATION pattern strengthening, not weakening).
7. ✅ **Spec-time grep-verification (Pass-1 + Pass-2)** — Phase 0 §1 (Pass-1) + Plan v1 §1 (Pass-2). 15th instance of the discipline at Plan v1 close.
8. ✅ **Honest-closure-actual-count commitment made at Plan v1 §6** — 5th instance to be banked.
9. ✅ **Deliberate-regression check protocol** — §4.4 enumerates 5 induced reverts that MUST fire correctly at Phase 4 closure.
10. ✅ **Closure-narrative paste-template ready** — §5 5-surface template + §6 band-table.
11. N/A **Privacy** — no PII or sensitive-data path touched by D1 or D2.

---

## §9. Discipline counts at Plan v1 close

**Per auditor's Post-P0.B2 ratified baseline + Phase 0 audit deltas + Plan v1 artifact (+1):**

| Discipline | Phase 0 close | Plan v1 close |
|---|---|---|
| Spec-first review cycle | 47 | **48** ✓ (Plan v1 artifact +1) |
| Strict-industry-standard mode | 37 applications + 10 closures | **38 applications + 10 closures** |
| `### Phase-0-granular-decomposition-enables-accurate-estimates` | 9 supporting | stays 9 (closure pending) |
| `### Phase-0-catches-wrong-premise` | 7 | stays 7 |
| `### Twin-filename-pitfall-prevention` | 7 + 4 op rules | stays 7 (no new filename event) |
| Deferred-canary | 11th in-flight | stays 11 (closure-event pending) |
| Auditor-Q5-estimates-trail-grep | 14 banked + 1 in-flight | stays 14 + 1 in-flight (Plan v1 LOCK 7 anchors; closure pending) |
| Cross-cycle-handoff transparency precedent | 10 successful | **11th successful** ✓ per auditor Plan v1 verdict (architect honored Phase 0 verdict's locked counts at Plan v1 baseline grep — same shape as the 10th instance at Phase 0 where architect honored P0.B2 closure verdict's supplemented counts) |
| Architect-reads-production-code-before-sign-off | 7 banked | stays 7 (closure-audit pending) |
| Spec-time grep-verification | 14 instances | **15 instances** ✓ (Plan v1 §1 Pass-2 grep enumerated 3 test files + 5 production call sites of `_kuzu_degraded` + production/test surfaces of `update_graph_schema_version`) |
| Discipline-count-bump-needs-explicit-justification | 10 preventive | stays 10 |
| Convention-drift-on-discipline-counts (parent) | 4 | stays 4 |
| Per-artifact-arithmetic-drift-survives-grep-baseline (child) | 1 | stays 1 |
| Explicit-closure-honest-count-commitment | 4 | **5** ✓ (Plan v1 §6 commitment MADE; closure-audit will determine honor at 5th instance closure) |
| Grep-baseline-before-drafting | 4 | **5** ✓ (Plan v1 drafted from Post-P0.B2 ratified counts + Phase 0 ratified deltas; 5th preventive instance — approaches 5+ elevation candidacy per Convention-drift sub-rule pattern) |
| Auditor-catches-Q5-math-at-plan-review | 2 | stays 2 (no Q5 math error in Plan v1 — closure-actual projection table is straightforward arithmetic verified per §7) |
| Phase-0-zero-precision-items-at-auditor-review (NEW) | 1 (Phase 0) | stays 1 (Plan v1 absorbs proactively; Plan v1 audit pending) |
| HEAVY-band cadence (working hypothesis) | 2 | stays 2 (P0.B3 is SMALL-band; does NOT add evidence) |

---

## §10. Open questions for auditor (0)

No new open questions. Plan v1 absorbs all 4 anticipated precision items from auditor Phase 0 verdict proactively. Architect prediction: **APPROVED 0 items → ship straight to developer per OPTIONAL-Plan-v2 path** (2nd proof case after P0.S3).

If auditor surfaces ≥1 unresolved item (e.g. ORDERING INVARIANT comment text needs additional language, or test-migration disposition is ambiguous), escalate to Plan v2.

---

## §11. Implementation handoff readiness

**Developer contract:**
- **Scope:** D1 + D2 per §2.1 + §3.1.
- **Estimated effort:** 2-3 hours (SMALL-band v1-only cycle).
- **Files touched:** `core/brain_agent.py` (~1 function refactor + comment block) + `core/health.py` (~30 lines additive) + `tests/test_p0_b3_kuzu_schema_health.py` (NEW, ~6 anchors) + `tests/test_kuzu_atomicity_invariants.py` (in-place rewrite of 1 test, ~20 lines).
- **Phase 1:** D1 refactor + ORDERING INVARIANT comment block + D2 dataclass field + gather wiring (~1 hour).
- **Phase 2:** D1+D2 anchor tests (3+3 = 6) + cross-cutting migrated test (1) = 7 anchors (~1 hour).
- **Phase 3:** existing tests review pass (no expected changes per §1.1, except docstring nuance at `test_schema_upgrade_sql_commit_failure_writes_sentinel`) + suite run (~30 min).
- **Phase 4:** §4.4 deliberate-regression confirmations (5 reverts) + closure narrative drafting per §5 paste-template (~30 min).

**Plan v1 → developer:** ship at auditor Plan v1 sign-off (assuming APPROVED 0 items).

**Plan v1 → Plan v2:** ship Plan v2 if auditor surfaces ≥1 unresolved item.

---

---

## §12. Closure-conditional doctrine elevation candidate — `### Grep-baseline-before-drafting`

Per auditor Plan v1 verdict 2026-05-21: `Grep-baseline-before-drafting` informal observation reaches 5+ elevation candidacy at Plan v1 close. **Pre-draft elevation candidate banked here per Twin-filename pitfall doctrine pre-draft precedent (locked at P0.S7 Plan v2 §2.2 closure-conditional contract).**

**Closure-conditional contract:** if at P0.B3 closure ALL FOUR criteria are confirmed —

1. 5+ instances confirmed (architect re-counts at closure narrative drafting per the discipline itself)
2. Discipline-stability across 5 applications (no silent rollbacks; no false-positive flags; consistent application)
3. No silent rollbacks across cycles
4. No false-positive flags

— THEN elevate to numbered CLAUDE.md doctrine at the P0.B3 closure narrative with VERBATIM text per the pre-draft below. If criteria not met (e.g. closure-audit surfaces a Convention-drift recurrence that the discipline failed to prevent), demote back to architect-memory + bank as "elevation candidate rejected at closure" instance for `feedback_doctrine_elevation_candidate_rejected.md` (does not yet exist).

### §12.1 Pre-draft doctrine text (VERBATIM-LOCK candidate)

```markdown
### Grep-baseline-before-drafting

Before drafting closure narratives or Plan v1/v2/v3 doctrine track-record updates,
grep-verify prior baseline counts from source-of-truth files. Stale-copy baselines
from much earlier closure narratives cause systematic +N/−N drift on discipline
counts; the only way to prevent this drift is to grep-verify against the most
recently ratified counts BEFORE writing.

**Track record (5 instances at elevation 2026-05-XX):**

- **P0.B1 closure (2026-05-21):** 1st instance — architect closure-audit corrected
  stale-baseline drift (subdir "27 → 30" off-by-one → "31") via grep-verification.
  Convention-drift-on-discipline-counts 3rd instance banked simultaneously; the
  discipline was BORN at this closure as the prevention-side counterpart.
- **P0.B2 Phase 0 (2026-05-21):** 2nd instance — Phase 0 audit drafted from
  grep-verified baseline (audit-side preventive application).
- **P0.B2 Plan v2 §2 (2026-05-21):** 3rd instance — explicit baseline citation
  in closure-narrative paste-template (template-side preventive application).
- **P0.B3 Phase 0 (2026-05-21):** 4th instance — Phase 0 audit drafted from
  Post-P0.B2 ratified counts (cross-cycle-handoff preventive application).
- **P0.B3 Plan v1 (2026-05-21):** 5th instance — Plan v1 drafted from Phase 0
  + auditor Phase 0 verdict's locked counts (continued cross-cycle application;
  elevation candidacy reached).

**Discipline-stability evidence (auditor adjudication at P0.B3 Plan v1 verdict
2026-05-21):**

The discipline was applied CONSISTENTLY across 5 consecutive applications without
silent drift. Cross-actor validation: auditor recommended at P0.B1 closure →
architect adopted → auditor's verdict-counts adopted at next-cycle Phase 0 →
no recurrence of stale-copy baseline drift. Working as intended.

**Operational rules:**

1. Before drafting closure narratives, grep `discipline-count: N`-style values
   in the most recently ratified source-of-truth files (CLAUDE.md + parent
   complete-plan.md + subdir complete-plan.md + memory-file track records).
   Cite the grep-verified baseline EXPLICITLY in the narrative + reference the
   source-of-truth file.
2. Before drafting Plan v1/v2/v3 doctrine track-record updates, perform the
   same grep-verify pass. Track-record additions MUST flow from grep-verified
   baseline, NOT from architect's working memory of "what the count was last
   time."
3. If a discrepancy surfaces between the grep-verified baseline AND the
   in-flight closure-narrative draft, the GREP wins. Auditor adjudication
   for the closure-actual count is the binding arbiter.

**Cross-disciplines (parent-child relationships):**

- `feedback_convention_drift_discipline_counts.md` (PARENT): closure-narrative
  count drift is the BASELINE drift class that this discipline prevents.
- `feedback_per_artifact_arithmetic_drift_survives_grep_baseline.md` (CHILD):
  the arithmetic drift class is OUT OF SCOPE for this discipline — grep-baseline
  catches BASELINE drift, not arithmetic drift. The CHILD observation tracks
  the gap.
- `### Phase-0-granular-decomposition-enables-accurate-estimates` (CLAUDE.md):
  symmetric counterpart on the estimation axis. Decomposed Phase 0 → narrow
  estimate; grep-verified baseline → accurate count.

**Falsification clause (locked at elevation, mirrors the other 3 elevated
doctrines — Phase-0-catches-wrong-premise + Twin-filename-pitfall-prevention +
Phase-0-granular-decomposition-enables-accurate-estimates):**

If a future instance reveals the 5-instance threshold was incorrectly counted
(e.g. one of the 5 "preventive" applications wasn't actually preventive, it was
a false-positive flag), the doctrine demotes back to architect-memory + the
falsification banking applies. Specifically: a closure where grep-baseline-
before-drafting WAS applied but Convention-drift drift STILL surfaced would
falsify the discipline (the prevention claim is the load-bearing property).

**Future instances** continue to be banked under this doctrine's track record.
The doctrine matures rather than re-elevating at higher thresholds.
```

### §12.2 If criteria not met at closure → demotion path

If at P0.B3 closure the audit surfaces ANY of:
- Convention-drift recurrence that the discipline failed to prevent (e.g. a closure-narrative count is wrong despite architect's grep-baseline claim),
- An instance previously banked as "preventive" turns out to have been a false-positive,
- A silent rollback of the discipline at any prior cycle is discovered,

then: skip the elevation, bank the failure instance, and continue tracking the discipline as informal observation. Same shape as P0.S7 Plan v2 §2.2 closure-conditional pattern (the closure event ratifies OR de-ratifies the candidacy).

### §12.3 Architect closure-audit ratification step

At P0.B3 closure, architect MUST explicitly verify:
1. **Instance enumeration**: confirm 5 instances at the track record above are all genuine preventive applications (not re-counted instances of the same event).
2. **Discipline-stability evidence**: review each of the 5 applications for any silent rollback or false-positive flag.
3. **Cross-reference integrity**: verify the parent-child relationships with Convention-drift + Per-artifact-arithmetic-drift remain accurate post-elevation.
4. **Falsification clause integrity**: verify the falsification clause's load-bearing property (closure where discipline applied but drift still surfaced) is testable.

If all 4 verification steps pass → elevate VERBATIM per §12.1 + bank as 4th `###`-level doctrine in CLAUDE.md Architectural Disciplines section.

If any verification step fails → defer elevation + bank failure instance.

---

**End of Plan v1.** Ready to forward to auditor.

**Architect prediction:** **APPROVED 0 items → ship to developer per OPTIONAL-Plan-v2 path** (P0.S3 was 1st instance; this would be 2nd).
