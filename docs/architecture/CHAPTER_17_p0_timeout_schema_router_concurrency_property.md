> **CHAPTER 17 — P0 Timeout + Schema + Router/Concurrency/Property** | Sourced from `everything_about_system.md` §271-299 (verbatim mechanical extraction per Plan v2 §1.6 section-number stability invariant).

---

## 271. The Hang Surface Before P0.8

Every LLM-callable tool handler (Part XII §75) was a branch in a big if/elif chain inside `_execute_tool`. The branches were synchronous in places, async in others, and none of them had a per-tool timeout budget. The visible failure mode: any tool whose underlying I/O hung (SQLite holding a lock, Tavily API stalling, Ollama under load) would freeze the LLM dispatch path indefinitely. The user would say something, the brain would propose a tool, the tool would hang, and the conversation would be dead for the user.

The architectural fix: extract every tool branch into a top-level `async def _handle_<tool>(args, ctx)` function, register them in a module-level `_TOOL_HANDLERS: dict[str, Callable]`, and wrap the dispatch in `asyncio.wait_for` with a per-tool budget. On timeout, `wait_for` cancels the handler task. The cancellation propagates through any open transaction `__aexit__`, rolling back partial SQL writes.

## 272. `_TOOL_HANDLERS` Extraction and `_ToolContext`

The 5 LLM-callable tools (`update_person_name`, `report_identity_mismatch`, `update_system_name`, `shutdown`, `search_memory`) each got their own handler:

```python
async def _handle_update_person_name(args: dict, ctx: _ToolContext) -> str | None:
    # ... handler body verbatim from the prior if/elif branch
    return "handled"  # or "rejected" / "handled_noop" / "shutdown" / None

_TOOL_HANDLERS: dict[str, Callable] = {
    "update_person_name": _handle_update_person_name,
    "report_identity_mismatch": _handle_report_identity_mismatch,
    "update_system_name": _handle_update_system_name,
    "shutdown": _handle_shutdown,
    "search_memory": _handle_search_memory,
}
```

`_ToolContext` is a frozen slots dataclass that carries everything a handler needs (`args`, `person_id`, `person_name`, `db`, `user_text`, `intent_sidecar`, `exec_snap`, `caller_type`). It's built once after the privilege gate fires, then passed into the handler. The handlers all start with a small unpack header (`person_id = ctx.person_id`, etc.) so the moved branch body reads identically to the pre-extraction code.

The extraction discipline was *purely mechanical*: no "while I'm here" changes to handler logic. The tool `tools/extract_tool_handler.py` (idempotent helper) dedents the branch body, builds the `_handle_<tool>(args, ctx)` wrapper, and replaces the original branch with delegation. Each extraction was a single sub-PR with full-suite verification before the next handler.

## 273. `asyncio.wait_for` and the Per-Tool Budgets

`_execute_tool` runs the un-budgeted gates first (Layer 0 unknown filter, repeat guard, privilege gate). Then it dispatches:

```python
budget = TOOL_TIMEOUT_OVERRIDES.get(name, TOOL_TIMEOUT_SECS)
try:
    return await asyncio.wait_for(handler(args, _ctx), timeout=budget)
except asyncio.TimeoutError:
    return "tool_timeout"
```

The per-tool budgets in `core/config.py`:

- `TOOL_TIMEOUT_SECS = 10.0` — default
- `TOOL_TIMEOUT_OVERRIDES = {"search_web": 20.0, "search_memory": 5.0, "update_person_name": 5.0, "update_system_name": 5.0, "shutdown": 3.0, "report_identity_mismatch": 3.0}`

The override for `search_web` is 20s because Tavily does multi-query searches and legitimate live-data queries can take 8-15s. `search_memory` is 5s because it's a fast SQLite query. `shutdown` is 3s because it should be near-instant; a hung shutdown is itself a bug.

The new `tool_timeout` status was added to the taxonomy alongside `handled`/`handled_noop`/`rejected`/`unknown`/`None`/`shutdown`. The `_all_unreal` classifier in `conversation_turn` (Part XII §70) was widened to include `tool_timeout` so the Together.ai/Ollama retry path acknowledges the action didn't complete and the LLM emits a hedged re-ask instead of fabricating "I did it".

## 274. Cancellation Rollback Through Transaction `__aexit__`

The cancellation flow on `asyncio.TimeoutError`:

1. `wait_for` cancels the handler task.
2. `CancelledError` propagates up the handler's call stack.
3. If the handler is inside a `FaceDB.transaction()` or `BrainDB._safe_commit()` block, the `__aexit__` method runs with the exception in flight.
4. `__aexit__` issues `ROLLBACK`, restoring the SQL state to the pre-transaction snapshot.
5. The `CancelledError` re-raises (transaction `__aexit__` does not swallow).
6. `_execute_tool` catches the timeout (which manifests as `TimeoutError` at the `wait_for` level, not `CancelledError`), returns `"tool_timeout"`.

The property is structurally proven by `TestHardCaseCancellationRollback` in `tests/test_tool_timeout.py`: a handler that does 10k `cursor.execute()` inside a transaction with periodic `await asyncio.sleep(0)` every 100 writes, with a forced 1ms timeout mid-loop, ends with `SELECT COUNT(*) == 0` (everything rolled back). The test is structural insurance against a future handler that forgets the periodic checkpoint and locks out cancellation.

## 275. P0.8.1 — Tavily Wrap and the Hidden Inline Consumer

P0.8's wait_for covered every tool in `_TOOL_HANDLERS`. But `search_web` is consumed *inline* inside `ask_stream` (Part XIII §80) — split out of `raw_tool_calls` and handled in-stream, not dispatched through `_TOOL_HANDLERS`. The `wait_for` wrap didn't reach it. The 20s `TOOL_TIMEOUT_OVERRIDES["search_web"]` budget was dead config.

Tavily API hangs are the single most likely real-world hang point. P0.8.1 fixed this with an explicit wrap inside `core.brain._web_search`:

```python
try:
    response = await asyncio.wait_for(
        _tavily_http.post(...),
        timeout=TOOL_TIMEOUT_OVERRIDES.get("search_web", TOOL_TIMEOUT_SECS),
    )
except asyncio.TimeoutError:
    return {"error": "timeout", "hint": "Tavily timed out — answer from training knowledge or honestly acknowledge the network failure (no fabricated search results)."}
```

The returned dict shape matches the existing short-query / empty-query error shape, so both call sites (`ask_stream` and non-streaming `ask`) handle it via the existing `isinstance(result, dict)` branch — timeout surfacing flows through unchanged.

The lesson: **the wait_for wrap must cover every consumer of the underlying I/O**, not just the dispatch path. P0.8's wrap was correct but incomplete; P0.8.1 found the inline consumer and closed it. Future tool work should grep for the underlying I/O call (here `_tavily_http.post`) at audit time, not just trust that wrap-coverage at the dispatcher is sufficient.

## 276. P0.8.2 — F1 + F2 Structural Invariants

Two AST-based CI invariants now enforce the timeout architecture's load-bearing properties:

- **F1 — handler-checkpoint discipline.** Every async handler in `_TOOL_HANDLERS` containing a sync `for` / `while` / `async for` loop with a raw `.execute(...)` call inside MUST also contain `await asyncio.sleep(0)` in the same loop body. Without the checkpoint, `wait_for` cancellation cannot fire mid-loop and transaction rollback never runs. P0.8.1's `TestHardCaseCancellationRollback` proved the property structurally when checkpoints exist; F1 enforces they continue to exist as the codebase grows.
- **F2 — retry-path one-shot guarantee.** `ask_retry_text` MUST internally call `_stream_together_raw(..., include_tools=False)` on every code path. AST scan walks the function body, finds every `_stream_together_raw` invocation, asserts each carries `include_tools=False` as a literal `False` constant (no kwarg / non-literal / `True` all fail). The retry path stays structurally one-shot — no recursive tool dispatch is possible.

The deliberate-regression checks confirmed both invariants fire correctly: F1 caught an injected sync `.execute()` loop without checkpoint in `_handle_search_memory` (assertion mentions `sync loop at line X` + violation explanation), F2 caught `include_tools=True` flip in `ask_retry_text` (assertion mentions `passes include_tools=True — must be the literal False`). Both reverted to green.

The F2 case is the **developer-improves-on-spec** moment for P0.8.2 (Part L §327): the auditor's original prescription targeted call sites in pipeline.py, but the actual contract is internal (`ask_retry_text` doesn't accept `include_tools` as a public parameter by design). The developer's caller audit found the internal contract and the F2 invariant verifies that instead.

---

# Part XLII — Schema Migrations Versioning (P0.9)

## 277. The Drift Problem with Inline `ALTER TABLE` Calls

Pre-P0.9 architecture: every schema change was an inline `ALTER TABLE` call inside the relevant DB class's `_init_tables` or `_migrate` method. Example pattern:

```python
def _init_tables(self) -> None:
    cur = self._conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS persons (...)")
    try:
        cur.execute("ALTER TABLE persons ADD COLUMN preferred_language TEXT")
    except sqlite3.OperationalError:
        pass  # column already exists
    # ... repeat for every historical schema change
```

The pattern works for fresh DBs (CREATE creates everything) and for already-migrated DBs (every ALTER is a no-op via the OperationalError swallow). It breaks on:

1. **Partial-state DBs.** If a backfill migration is half-complete, the ALTER passes (column exists) but the backfill never runs (no idempotency guard, no progress tracking).
2. **Cross-DB ordering.** If migration X on `brain.db` reads a column added by migration Y on `faces.db`, the order is implicit in import order — fragile.
3. **Failed-mid-migration recovery.** If `_init_tables` crashes mid-way, the DB is in an unknown state. No ledger says what completed.
4. **Silent OperationalError swallowing.** Every ALTER `except OperationalError: pass` swallows unrelated errors too (disk full, lock contention).

P0.9 generalises the versioned-ledger pattern that `classifier_scenarios.db` (Spec 1, Session 122) shipped first and applies it to `faces.db` and `brain.db`.

## 278. `core/schema_migrations.py` — The Generalised Helper

Three exports:

- **`init_ledger(conn)`** — self-evolving migration-history table. Creates `schema_migrations(version, description, applied_at, is_initial)` on a fresh DB. On a pre-P0.9 DB that already has a partial ledger, idempotently adds the `is_initial` column via `PRAGMA table_info` + ALTER.
- **`bootstrap_ledger_if_unversioned(conn, migrations)`** — stamps `v=1` baseline on a legacy DB with `is_initial=1`, walks the `migrations` list and stamps each entry whose `verify_present_fn` returns True as `is_initial=1`. Without this, a fresh boot against a legacy DB would crash on `OperationalError: duplicate column name` when the runner tried to re-apply each historical migration.
- **`apply_migrations(conn, migrations)`** — runs pending entries in version order under `BEGIN IMMEDIATE`, calls `apply_fn` then `verify_post_fn` inside the same transaction so a verify failure rolls back the apply (atomic migrate-or-fail).

The transaction wrapping uses the tightened S65 rollback discipline (§282) — only the known "no transaction is active" race is suppressed; unexpected operational errors are loud.

## 279. The 5-Tuple Migration Shape and Why

Every entry in `MIGRATIONS: list[tuple[int, str, Callable, Callable, Callable]]`:

```python
(version, description, apply_fn, verify_post_fn, verify_present_fn)
```

- **`version: int`** — monotonically increasing. Determines apply order.
- **`description: str`** — human-readable label for boot logs (e.g. `"Add preferred_language column to persons"`).
- **`apply_fn(conn) -> None`** — performs the schema mutation. Raises on failure.
- **`verify_post_fn(conn) -> None`** — raises if the post-state is wrong. Used by the runner after apply_fn.
- **`verify_present_fn(conn) -> bool`** — returns True if the migration's effect is already present on disk. Used by bootstrap to decide whether to stamp `is_initial=1` on a legacy DB.

For schema-only migrations (add column, add index, create table) `verify_post` and `verify_present` collapse to the same check. For backfill migrations (e.g. `faces v=9 conversation_log backfill`, `brain v=10 privacy_level remediation`) they diverge meaningfully.

## 280. `verify_post` vs `verify_present` — The Developer-Improved-on-Spec Split

The architect's original spec for P0.9.2 defined a single `verify(conn) -> bool` function per migration. The developer split it into two during implementation, with explicit reasoning that became one of the entries in the developer-improves-on-spec track record (Part L §327).

The split is load-bearing for backfill migrations. Consider `faces v=9` — adds `conversation_memory_archived` column AND backfills all pre-existing rows. The two scenarios:

- **`verify_post`** is used by the runner after `apply_fn`. It must assert "post-condition achieved": column exists AND zero rows have NULL `conversation_memory_archived`.
- **`verify_present`** is used by bootstrap on a legacy DB to decide whether to stamp `is_initial=1`. The right answer is "is the migration's effect already in place?" Which for a backfill means: column exists AND no NULL rows remain.

For most schema-only migrations the two collapse: `verify_present` is "column exists"; `verify_post` is "column exists". For backfills they MUST diverge:

- If the backfill is partially run on a legacy DB, `verify_present` returns False (column exists but NULL rows remain) → bootstrap doesn't stamp → runner runs the migration → `apply_fn` is idempotent (`ALTER TABLE IF NOT EXISTS`) → the backfill completes → `verify_post` confirms completion → ledger stamped.
- With a single function, the partial-state DB would either get stamped at boot (silent data loss — the backfill never finishes) or never reach a stable state.

The split correctly handles partial-migration scenarios. Architecturally, it's the right primitive. The developer's improvement on the architect's spec is documented in the closure report and banked in §327.

## 281. Imp-1 — `isolation_level="IMMEDIATE"` on Every Connect

Python's sqlite3 default `isolation_level` is `""` (deferred). When the connection is in deferred mode, the first write takes a `BEGIN DEFERRED` lock — meaning two concurrent connections can both be reading, and the first to write gets the lock, the second writes upgrade to EXCLUSIVE and may collide.

`FaceDB.transaction()` and `BrainDB.transaction()` issue explicit `BEGIN IMMEDIATE` to take a write lock upfront. But if a *different* connection (one of the 5 connect sites in core/*.py outside the transaction context) is using deferred mode, it can interleave with the IMMEDIATE transaction's writes in unsafe ways.

Imp-1 ships `isolation_level="IMMEDIATE"` on every `sqlite3.connect()` in `core/*.py` (excluding `core/backup.py`'s one-shot file-copy use). 5 connect sites updated: `FaceDB.__init__`, `FaceDB._init_conversation_archive`, two FaceDB archive-read sites, `BrainDB.__init__`, `ClassifierDB.__init__`, plus two `_faces_conn` sites. AST source-inspection test in `tests/test_schema_migrations.py` rejects any future `sqlite3.connect` in core/* that doesn't pass `isolation_level="IMMEDIATE"`.

## 282. Imp-2 — Tightened S65 Rollback Discipline

The S65 race (Session 65 finding): inside `transaction()` `__aexit__`, the rollback is wrapped in `except sqlite3.OperationalError: pass` to swallow the known "no transaction is active" race that occurs when a parallel close races with the rollback. Pre-Imp-2: the swallow was unconditional — it would also silently absorb a disk-full error, a lock-contention error, or a schema mismatch.

The tightening: every `# RACE: S65` rollback site now reads `if "no transaction is active" not in str(_rbe).lower(): print(...); raise`. The known S65 race stays suppressed; everything else is loud. 4 sites tightened: `core/schema_migrations.py::apply_migrations`, `core/db.py::FaceDB.transaction`, `core/db.py::FaceDB.archive_old_conversation_log`, `core/brain_agent.py::BrainDB.transaction`.

AST scan in `tests/test_schema_migrations.py` asserts every `# RACE: S65` site uses the tightened message-check pattern. The discipline is now CI-enforced.

## 283. The 19 Retrofitted Historical Migrations

P0.9 Phase 2 retrofitted 19 historical schema mutations into versioned `MIGRATIONS` lists with full 5-tuple shape: 10 migrations on faces.db (v=2 through v=10), 10 migrations on brain.db (v=2 through v=11), 1 destructive op (`_m_0010_drop_conversation_memory` on faces.db, with the documented S24 cleanup exemption).

Each migration is a verbatim move of the existing inline `ALTER TABLE` from `_init_tables` / `_migrate` — mechanical-extraction discipline (P0.8 lineage). The inline calls KEEP RUNNING in Phase 2 as defense-in-depth — both are idempotent; Phase 3 cleans up the redundancy after live-prod-DB validation.

Two new migration modules house the retrofitted entries: `core/faces_db_migrations.py` (~280 lines) and `core/brain_db_migrations.py` (~270 lines). Each `_m_NNNN_*` function is a verbatim function-extraction of the prior inline code; the migration registry is the only authoritative source for the schema change record.

Pre-Phase-3 validation passed against Jagan's actual production DBs (boot log captured in `terminal_output.md`, 2026-05-17 multi-person session). Phase 3 then deleted the redundant inline calls: `FaceDB._init_tables`'s 2 try/except loops + 1 idx_conv_log_room CREATE + 1 backfill block + DROP TABLE conversation_memory, plus `BrainDB._migrate`'s 10 PRAGMA-guarded ALTERs + privacy_level remediation backfill. `BrainDB._migrate` is now a no-op stub kept for the `__init__` call-chain continuity.

## 284. The Structural Invariants That Lock the Pattern

Four invariants in `tests/test_schema_migrations.py`:

1. **`TestNoIdempotencyTryExceptOutsideRunner`** — AST scan rejects any `try: ALTER/CREATE ...; except sqlite3.OperationalError: pass` pattern in `core/db.py` + `core/brain_agent.py`. Idempotency now lives in the runner only.
2. **`TestNoAlterTableOutsideMigrationModules`** — regex scan rejects any `ALTER TABLE` in `core/db.py` + `core/brain_agent.py`. Lives only in `core/{faces,brain}_db_migrations.py` + the meta-migration in `core/schema_migrations.py`.
3. **`TestNoDestructiveOpsInMigrationBodies`** — AST scan rejects `DROP TABLE` / `DROP COLUMN` / `ALTER TABLE ... RENAME` in `_m_*_apply` bodies, with single documented exemption (`_m_0010_drop_conversation_memory_apply` — S24 legacy cleanup).
4. **Sanity guard** that the exemption's body actually contains the destructive op (catches typos in DOCUMENTED_EXEMPTIONS set).

Plus the 5-tuple invariant: `test_every_entry_is_5_tuple_with_both_verify_companions` asserts both callables present on every migration.

P0.9 closed boot observability with three new log lines on every boot:

- `[Schema] {db_label}: bootstrap stamped baseline v=1 + N pre-existing migration(s) as is_initial=1 (legacy DB)`
- `[Schema] {db_label}: apply_migrations ran 0 pending`
- `[Schema] {db_label}: ledger already versioned`

These are the validation gates that consumed Jagan's live-prod-DB validation in 2026-05-17.

---

# Part XLIII — Legacy Router Deletion and Bug-W Closure (P0.10)

## 285. The Phase 0 Premise Reset

P0.10's original architect framing: "the new reconciler (Part XXXII) is correct; delete the 273-line legacy router (`_resolve_actual_speaker` in `pipeline.py`); ship Plan v1."

Phase 0 audit, before any plan was drafted, ran a grep + behavioral audit of the legacy router's exact decision space and the new reconciler's rule cascade. The finding was load-bearing: **the new reconciler was *not* correct**. It had a 0.3–0.5s coverage gap — the **Bug-W class** — where short utterances (0.3 to 0.5 seconds of audio, just above the `MIN_UTTERANCE_SECS` floor) with an active session could fall through every P0 / P1 / P2 / P3 / P4 / P5 rule and exit the cascade unhandled.

The legacy router's catch-all `return cur_pid, "current"` at the end of `_resolve_actual_speaker` was incidentally papering over the gap. Every short-utterance turn that fell through the cascade just defaulted to "current speaker continues to hold". The pre-P0.10 production system worked correctly *because* of this catch-all, not despite it.

Phase 4 cutover (`ROUTING_USE_RECONCILER=True`, Session 121) had already removed the legacy blanket-hold floor for the in-production routing path. The exposure to Bug-W began at that cutover. The reconciler was running standalone, and any time a short utterance fell through the cascade, the turn was silently dropped (no `RoutingDecision` returned).

Phase 1 v2 plan was rewritten against the corrected premise. The new spec: **fill the cascade's gap with explicit rules, THEN delete the legacy.** The audit saved an entire spec-cycle — Plan v1 as originally written would have shipped legacy deletion → Bug-W active in production → silent turn drops on every short-utterance turn.

This is the **premise-correction sub-pattern** documented in §327 — different from the standard developer-improves-on-spec because it changes WHAT gets built, not just HOW.

## 286. The Bug-W Coverage Gap

The empirical bug: a short utterance (0.3 to 0.5s of audio) from a known speaker who was the current session holder, with no other signal (no face in frame at that exact instant, no voice gallery match strong enough to fire P1, no pyannote multi-segment to fire P4), would hit P0's short-utterance handling — but only `_p0_short_utterance_hard_mismatch` and `_p0_short_utterance_ambiguous_multi_session`, both of which require *some* signal (voice score below floor + session candidates). When there was no signal at all, no rule matched, the cascade returned `no_action`, and the turn was dropped.

The legacy router treated this as "current speaker continues to hold" via its catch-all. The reconciler, designed as a positive-contract rule cascade with no implicit fallback, didn't.

The fix: explicit P0 rule `_p0_short_utterance_gap_hold_current` that fires when audio is between `MIN_UTTERANCE_SECS` and `SHORT_UTTERANCE_FLOOR`, there's an active session, and no signal disqualifies the holder. The rule returns `RoutingDecision(action="current", pid=cur_pid, rule="_p0_short_utterance_gap_hold_current", utt_band="gap", reasoning="short utterance with active session, no disqualifying signal")`.

## 287. `_p0_short_utterance_gap_hold_current` and the `LOWER_BOUND` Attribute

Every P0 rule was given a `LOWER_BOUND` attribute documenting the minimum utterance duration at which the rule is eligible to fire. The new rule fires at `MIN_UTTERANCE_SECS` (currently 0.3s). The pre-existing rules (e.g. `_p0_pure_noise_hold_current`) fire at 0.0s. The architectural invariant: **the cascade's rule order, when sorted by `LOWER_BOUND`, must be non-decreasing**.

This is enforced by `tests/test_reconciler.py::TestRulesOrderingInvariant`. The test reads the cascade's rule list, extracts each rule's `LOWER_BOUND` (default 0.0 if absent), and asserts the list is non-decreasing. Ties are allowed (`_p0_pure_noise_hold_current` and `_p0_short_utterance_no_session` are both at 0.0; `_p0_short_utterance_hard_mismatch` and `_p0_short_utterance_ambiguous_multi_session` are both at 0.5). The point is to catch misorder, not to enforce strict monotonicity.

## 288. The Non-Decreasing Band-Ordering Invariant

The auditor's R1 refinement during plan-v2 review: the ordering test catches misorder but NOT coverage gaps. A new utt_band (e.g. a `medium_utt` band between `short_hard` and `normal`) could be added without any rule explicitly covering it; the cascade would silently fall through every existing rule and exit with `no_action`. Coverage gaps remain a human-review responsibility (the validation window §292 is the empirical safety net).

The pragmatic stance: an AST-level "every band must have at least one rule firing in it" test would require a static map from band → expected_rules. P0.10.1 ships exactly that map (§291).

## 289. The Band-Divergence Block C Trigger

The Reconciler-Shadow block at `pipeline.py:7100+` (the divergence log between legacy and new routing) needed to be retargeted when the legacy was deleted. The original "legacy != new" trigger became unworkable — there's no legacy decision to compare against.

The developer-improved-on-spec trigger: **band-divergence**. The block fires when the utt_band of the firing rule (read from the `utt_band` tag the rule sets on its `RoutingDecision`) doesn't match the band the architect expected for that band (per the `EXPECTED_RULES_BY_BAND` map in §291). If a `gap` band utterance fires a `short_hard` rule, the divergence log warns; if a `short_hard` band fires a `normal` rule, same.

The developer's reasoning at closure: the architect's spec said "extend the existing divergence-log block with more fields, don't change trigger" — but Step 7's legacy deletion made the original trigger untestable. The band-divergence trigger preserves the architectural intent (catch divergences between expected and actual routing) while changing the mechanism. This is the 4th instance of developer-improves-on-spec banked in §327.

## 290. Phase 2 Cutover and the –15 / +40 Coverage Shift

Phase 2 (legacy deletion) shipped on 2026-05-17. Net test count change: **–15 tests, but +40 architectural-coverage tests**.

The math: Phase 1 added +35 contract/invariant tests, Phase 2 added +4 AST/N7 source-inspection tests, P0.10.1 polish added +1 EXPECTED_RULES_BY_BAND structural invariant — total +40. Phase 2 deletion of `_resolve_actual_speaker` + its 54 legacy `test_pipeline.py` tests subtracted –54. Net: –15 raw tests.

**This is not a coverage regression.** It's the natural outcome of legacy-deletion with replacement. Coverage shifted from "legacy 270-line function tests" (which tested implementation details of the legacy function: dispute-flip handling, scene-candidate counting, offscreen-floor calculation, etc.) to "rule-cascade + invariant tests" (which test architectural properties of the new reconciler: per-rule behavior, ordering, band-coverage, etc.).

The new tests test stronger properties. The deleted tests tested weaker properties (specific implementations of those weaker properties). The architectural coverage measurably increased; the raw test count decreased. Future maintainers should not misread P0.10's test count as a coverage regression.

## 291. P0.10.1 — `EXPECTED_RULES_BY_BAND` Lock

P0.10.1 closed the band-coverage gap that R1 review flagged. A static map in `core/reconciler.py`:

```python
EXPECTED_RULES_BY_BAND: dict[str, frozenset[str]] = {
    "noise":        frozenset({"_p0_pure_noise_hold_current", "_p0_short_utterance_no_session"}),
    "gap":          frozenset({"_p0_short_utterance_gap_hold_current"}),
    "short_hard":   frozenset({"_p0_short_utterance_hard_mismatch", "_p0_short_utterance_ambiguous_multi_session"}),
    "normal":       frozenset({"_p1_confident_voice_switch", "_p2_face_assist_switch", ...}),
}
```

The structural invariant: `test_every_band_has_rules()` asserts every band in `EXPECTED_RULES_BY_BAND` has at least one rule registered, and every rule's `utt_band` tag matches at least one band in the map. The map is the single source of truth for the band-divergence trigger and the per-band rule coverage assertion.

## 292. The Validation Runbook and Gate Criteria

`tests/p0_10_validation_runbook.md` is the daily-checklist file for the validation window opened by Phase 2 cutover. The gate criteria are explicit:

- Zero `[Reconciler] WARN: no rule fired` log lines for 7 consecutive days of normal use.
- Zero band-divergence log warnings for 7 consecutive days.
- The B2 fail-safe (when `_rc_decision is None`, the pipeline holds current and logs) must not fire.

Closure of the validation window unlocks the follow-up PR:
- DELETES the shadow block (`pipeline.py:7100+` Reconciler-Shadow logging code)
- DELETES `ROUTING_USE_RECONCILER` flag from `core/config.py`
- DELETES the B2 fail-safe and its corresponding tests
- KEEPS the new reconciler rule + LOWER_BOUND attrs + Bug-W regression test + RULES-ordering invariant + N2-N6 contracts + AST single-write-site test + EXPECTED_RULES_BY_BAND map + band-coverage invariant

As of 2026-05-18 the window is OPEN. Validation pending the next 7 days of canary use.

---

# Part XLIV — State Race Hardening (P0.11)

## 293. Preventive Hardening for a Latent Race

`core.state._persistent: dict` carries the cross-turn persistent settings (the anti-spoof enabled flag, the language, the system name's display-form preference). The dict is mutated by `set_persistent(key, value)` and read by `state.write()` (which serialises the entire dict to `state.json` for the dashboard IPC).

The race that P0.11 hardens against: a writer mutates `_persistent[key] = value` (in-place subscript assignment) while a reader iterates `**_persistent` inside the JSON serialisation. CPython does not guarantee iteration consistency under concurrent mutation — `RuntimeError("dictionary changed size during iteration")` is the visible failure; torn iteration (reader sees half-mutated state) is the invisible failure.

The race has **never been observed in production**. The single writer (`pipeline.py:6264 state.set_persistent("anti_spoof_enabled", _)`) runs ONCE at startup, before the event loop, before any reader can run. P0.11 closes the door against three latent activation conditions:

1. A future runtime `set_persistent` call lands after startup.
2. `state.write()` is moved off the asyncio loop into an executor thread.
3. `state.write()` gains an `await` point and the writer interleaves between `**_persistent` spread and JSON dump.

## 294. The Atomic-Replace Pattern and Why It Works

The production change in `core/state.py:16-31`:

```python
def set_persistent(key: str, value) -> None:
    global _persistent
    _persistent = {**_persistent, key: value}  # atomic replace via STORE_NAME
```

The pattern: never mutate `_persistent` in place. Build a new dict with `{**_persistent, key: value}` and rebind the module-level name. CPython's `STORE_NAME` bytecode is GIL-atomic — the rebind completes in one bytecode instruction, no possibility of a half-rebind.

Concurrent readers holding the OLD dict reference (e.g. mid-iteration in `state.write()`) see the consistent old snapshot through to completion. The new dict only becomes visible to readers on next dereference of `_persistent`. The race goes away because there is never a half-mutated state visible to any observer.

The docstring is honest about scope: this protects readers from torn iteration. It does NOT protect against concurrent *writers* losing updates (the RMW race — two writers both reading the old dict, both writing back with their respective single updates; one update is lost). Multi-writer correctness would require explicit `threading.Lock`, which is deferred until runtime writers actually land.

## 295. Three Deliberate-Regression Checks and the Detector-Strengthening Cycle

P0.11's induction protocol ran three deliberate-regression checks:

1. **Revert `set_persistent` to `_persistent[key]=value`** → `tests/test_state_race.py::test_no_subscript_assign_in_state_py` fired with `core/state.py:30: subscript-assign forbidden`. Reverted to atomic-replace.
2. **Drop the `global _persistent` decl from `set_persistent`** → `test_state_py_rebind_with_global` fired with `function 'set_persistent' rebinds _persistent without declaring global`. Without `global`, the assignment creates a function-local variable, the rebind doesn't propagate, and the module-level dict is silently never updated. Reverted.
3. **Inject `state._persistent["regression_check_3"]=True` in `pipeline.py:6265`** (attribute-form access from outside the state module) → `test_no_subscript_assign_in_repo` fired with `pipeline.py:6265: subscript-assign forbidden (attribute-form)`.

The third check **surfaced a detector gap** in the original AST scanner. The initial detector only caught bare-name subscript-assign (`_persistent[X]=Y` inside `core/state.py`). The deliberate regression injected attribute-form access (`state._persistent[X]=Y` from `pipeline.py`). The original detector didn't see it. The detector was strengthened in the same cycle to catch BOTH shapes (bare-name AND attribute-form).

This is the canonical induction-surfaces-invariant-gaps moment (Part L §322). The discipline working as designed: deliberate-regression check identifies a gap, the gap is closed in the same sub-PR, the invariant becomes load-bearing rather than theatrical. P0.11's count: 3 deliberate-regressions, 3 fires, 1 detector strengthening, all confirmed.

---

# Part XLV — JSON Parser Hardening (P0.12 + P0.12.1)

## 296. Why Property-Based Testing

The pre-P0.12 `core/brain_agent.py::_parse_json` and `core/brain.py::_parse_intent_sidecar` carried failure modes that example-based tests couldn't cover:

- Arbitrary text the LLM hallucinated as JSON (`raw='0'`, `raw='[1,2,3]'`, `raw='"just a string"'`)
- Truncated JSON streams (mid-tokens)
- Markdown code-fence wrappers (` ```json\n{...}\n``` `)
- Doubled keys (Python's `json.loads` contract: last wins)
- Unescaped nested quotes
- Trailing commas
- BOM + leading whitespace
- Surrogate / control / format unicode
- Empty / whitespace-only input
- Extremely large input (1 MB repeated payload + N-key dicts up to 5000)
- Deeply nested (`[`×N + `]`×N AND `{"a":` ×N — up to 2000 depth)
- Python 3.11+ `ValueError` on oversized integer string conversion (the new `sys.get_int_max_str_digits()=4300` DoS limit)

The combinatorial space defeats hand-curated test cases. P0.12 introduced **Hypothesis property-based testing** with `max_examples=1000` per test. Hypothesis searches the input space, shrinks failing cases to minimal reproducers, and surfaces real production bugs in the same sub-PR.

## 297. The Two Production Bugs Hypothesis Surfaced

**Bug 1 — `_parse_json` contract violation.** The type annotation declared `dict | None`, but the strict `json.loads(raw)` path returned WHATEVER `json.loads` produced. For `raw="0"` it returned `int`. For `raw="[1,2,3]"` it returned `list`. For `raw='"string"'` it returned `str`. Callers (7+ extraction agents in `core/brain_agent.py`) do `parsed.get(...)` assuming dict → silent `AttributeError` at runtime on any non-dict valid JSON.

Hypothesis's `TestArbitraryText` shrank the falsifying input to `raw='0'` (minimal possible JSON-parsable string that returns non-dict). Fix: added `return result if isinstance(result, dict) else None` gate. The contract is now structurally enforced — the dict|None type annotation matches the runtime behavior.

**Bug 2 — `_parse_intent_sidecar` uncaught ValueError.** Input with a 5000-digit integer literal triggered Python 3.11+'s `sys.get_int_max_str_digits()=4300` DoS limit, raising `ValueError` (not `JSONDecodeError`). The original except clause caught `(json.JSONDecodeError,)` exclusively. An adversarial LLM output could crash the parser.

Hypothesis's `TestLargeInput` shrank to `payload='1'` (Hypothesis-simplified to a long run of '1's exceeding the limit). Fix: extended except clauses on both code paths to `(json.JSONDecodeError, RecursionError, ValueError)`.

Both bugs got dedicated regression tests pinned to their falsifying inputs (`test_bug1_parse_json_returns_none_for_non_dict_top_level`, `test_bug2_parse_intent_sidecar_handles_oversized_int_string`, plus source-inspection guard `test_bug1_fix_visible_in_source` that catches future reverts via `inspect.getsource` + AST-style string check on the dict-isinstance gate).

CI cost: full Hypothesis suite runs in ~12s. Well under the 60s budget.

The lesson banked: **Hypothesis is a structural-validation tool, not a quality nice-to-have.** It finds bugs example-based tests can't reach. Standard practice now is `max_examples=1000` for contract surfaces (parsers, validators, serializers).

## 298. P0.12.1 — The SocialGraphAgent Dead-Branch Audit

P0.12 narrowed `_parse_json`'s return type to `dict | None`. The auditor's follow-up caller audit found one downstream regression: `SocialGraphAgent.extract` had an `isinstance(data, list)` branch handling the case where the LLM returned a top-level array. After P0.12's narrowing, `_parse_json` would return None instead of the list, so the list branch became unreachable and the extraction silently dropped list-shaped responses.

The other 6 caller audit findings: all handled None defensively via `if data is None: return []` or equivalent before `.get(...)`. PrivacyClassifier was an auditor false positive — its caller already had a dual-guard `if not parsed or not isinstance(parsed, dict): return None` that catches the case.

## 299. `_parse_json_array` — The Sibling Parser

Fix: added sibling `_parse_json_array(raw) -> list | None` in `core/brain_agent.py` with the same brace-salvage discipline but `[`/`]` markers and the same `RecursionError`/`ValueError` catches. SocialGraphAgent.extract now tries dict-wrapper shape first (matches what `response_format={"type":"json_object"}` asks for), then `_parse_json_array` fallback for raw-array LLM responses.

`_parse_json`'s narrow `dict | None` contract is preserved — no risk to the other 6 callers. The sibling parser is the right primitive for callers that legitimately want a list. Future contract surfaces (a third top-level shape, e.g. a string with embedded JSON) would add their own `_parse_json_X` sibling rather than re-broadening `_parse_json`.

Source-inspection regression test `test_p012_1_site_a_privacy_classifier_guards_none` pins the PrivacyClassifier dual-guard so future refactors can't strip it. Behavioral test `test_p012_1_site_b_socialgraph_recovers_raw_array` monkeypatches the LLM call to return raw `[{"name":"Sarah"},{"name":"Mike"}]` array, asserts both names recovered.

---

# Part XLVI — Health and Disk Observability (Wave 5)

