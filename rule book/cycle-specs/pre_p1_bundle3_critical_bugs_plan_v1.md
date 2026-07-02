# Pre-P1 Bundle 3 — Critical Bugs (MF4 + MF5) Plan v1 (2026-05-28)

**Cycle**: Pre-P1 must-fix Bundle 3 (Critical Bugs)
**Predecessor**: `tests/pre_p1_bundle3_critical_bugs_audit.md` (Phase 0 ACCEPT CLEAN at auditor verdict 2026-05-28; 8 RATIFICATIONS in architect's favor)
**Discipline**: Strict-mode, OPTIONAL-Plan-v2 path CONDITIONAL APPROVAL (Q7 RATIFIED — 20th proof case LOCKS at closure IF Plan v1 clears 0 PIs)
**Architect**: Claude
**Auditor**: External (Phase 0 verdict in `info.md` 2026-05-28)

---

## §0 Procedural commitments (Phase 0 carry-forward + auditor caveat absorption)

All 8 Phase 0 §0 commitments PRESERVED verbatim. NEW for Plan v1:

**§0 NEW commitment — semantic-correctness dual-axis verification at developer Pass-3**: per Q7 auditor caveat, Bundle 3's `### Multi-discipline-preventive-convergence` catching-layer must verify BOTH (a) file-count consistency (Bundle 1+2 carry-forward) AND (b) semantic-classification accuracy per site (DEADLINE-MATH vs WALLCLOCK-WRITE vs AMBIGUOUS for `time.time()` sites; assert→raise replacement preserves exception-class + error-message semantic). Different verification axis from Bundle 1+2's file-count-only catching-layer.

**§0 architect "HIGH with reservation" confidence framing** (Bundle 2 §12 carry-forward per `Zero-precision-items-pre-closure-predictions-blocked` sub-rule 5th-instance elevation context): Plan v1 confidence is HIGH for the mechanical surfaces (D3 + D4) but acknowledges Bundle 1+2 prior-prediction-blocked history. If Plan v1 review surfaces a NEW PI on the D1 semantic classification (most ambiguity-prone surface), cycle escalates to Plan v2.

---

## §1 Auditor Q1-Q8 ratifications applied + exhaustive per-site classification

### §1.1 Q1 absorption — BUG-9 hybrid disposition

Per Q1 (c) HYBRID RATIFIED: `pipeline.py:2009-2013` assert → `if not...: raise RuntimeError(...)` + docstring updated to clarify production-vs-test scope.

**Docstring update text (locked at Plan v1)**:

```python
"""Initialize RoomOrchestrator singleton.

face_db / brain_orchestrator MUST be non-None at production boot per the
_init_room_orchestrator() invariant runtime check below. In test fixtures
(per tests/conftest.py autouse fixture), None args are tolerated — the
RoomOrchestrator class stores deps without asserting; per-method None checks
on the 3 dep-requiring methods (build_shared_context_block, fetch_recent_room_context,
on_room_end) handle test-context None gracefully.

The runtime raise below + docstring contract + Layer 3 None-handling
together form defense-in-depth (P0.S1 §1.4 layered-defense precedent).
"""
```

**Layer 3 None-checks verification commitment** (Plan v1 §11 grep-verify):
- `core/room_orchestrator.py::build_shared_context_block` — verify None guard on `db` arg
- `core/room_orchestrator.py::fetch_recent_room_context` — verify None guard on `face_db` arg
- `core/room_orchestrator.py::on_room_end` — verify None guard on `brain_orchestrator` arg

### §1.2 Q2 absorption — 29 migration-file asserts ALL IN-SCOPE

Per Q2 (a) RATIFIED: all 29 asserts in `core/brain_db_migrations.py` (18) + `core/faces_db_migrations.py` (11) migrated to `if not...: raise RuntimeError(...)` mechanical replacement. Uniform `RuntimeError` exception class per Skeptic-1's spec. No custom `SchemaMigrationError` introduced (over-engineering for Pre-P1).

### §1.3 Q3 absorption — D2 AST invariant scope = STANDARD

Per Q3 (b) RATIFIED: D2 + D4 AST invariant scope = `pipeline.py` + `core/*.py` + `bootstrap/classifier/*.py` + `tools/*.py` (matches Bundle 2 D6 SPDX scope minus `core/_minifasnet/`). Vendored MIT paths excluded (same EXCLUDED_PATHS prefix discipline as Bundle 2 D6).

**Cross-bundle architectural-coherence banking**: 1st instance of `Spec-scope-boundaries-consistent-across-bundles` informal observation candidate (Bundle 2 D6 SPDX scope → Bundle 3 D2 AST invariant scope = same path enumeration). Watch criteria: 3+ instances may elevate to sub-rule under `### Multi-discipline-preventive-convergence` parent doctrine.

### §1.4 Q4 absorption — D4 test-file allowlist

Per Q4 RATIFIED: test allowlist = `tests/*.py` (recursive — includes `tests/fixtures/*.py`) + top-level `test_*.py` files (8 files per Bundle 2 §11.1 Bundle 2.Y candidate enumeration: `test_brain_agent.py` + `test_brain_response.py` + `test_executor.py` + `test_faiss_delete.py` + `test_greetings.py` + `test_pipeline.py` + `test_shutdown.py` + `test_vision_v1v4.py`). `conftest.py` (top-level) also allowlisted.

### §1.5 Q5 absorption — Q5 LOCK at mid 5 with Phase 4 strengthening caveat

Q5 LOCK at mid **5 anchors** (UNCHANGED from Phase 0). NARROW band [4.25, 5.75]. Falsification: ≤3 OR ≥8.

**Phase 4 strengthening caveat** (Bundle 1 + Bundle 2 precedent):

| Closure-actual | % vs mid | Reading | Doctrine consequence |
|---|---|---|---|
| 3 anchors | -40% | FALSIFICATION TRIGGER | falsification clause activates IF wrong-premise root cause |
| 4 anchors | -20% | SLIGHT-DRIFT-DOWN within ±30%; doctrine holds | doctrine HOLDS at 32 supporting; streak interrupted |
| **5 anchors (Q5 LOCK)** | **0%** | exact mid | doctrine bumps 32 → 33; **12th consecutive 0%-streak rebuild** (P0.S10 9th + Bundle 1 10th + Bundle 2 11th + Bundle 3 12th) |
| 6 anchors | +20% | SLIGHT-DRIFT-UP within ±30%; doctrine holds | doctrine HOLDS at 32 supporting; streak interrupted — likely Phase 4 in-cycle strengthening event |
| 7 anchors | +40% | FALSIFICATION TRIGGER | falsification clause activates IF wrong-premise root cause |
| ≤2 OR ≥8 | ≥±50% | FALSIFICATION TRIGGER + emergency review | falsification + same-cycle Plan v2 absorption |

### §1.6 Q6 absorption — `# WALLCLOCK:` annotation BOTH placements accepted

Per Q6 (c) RATIFIED: `# WALLCLOCK:` annotation accepted at EITHER inline (`x = time.time()  # WALLCLOCK: DB write`) OR line-above (`# WALLCLOCK: DB write\nx = time.time()`). Same flexibility as P0.4's `# CLEANUP:` / `# RACE:` / `# OPTIONAL:` discipline.

D2 AST invariant detector tests BOTH placements (forward: both annotated pass; inverse: neither annotated fires).

### §1.7 Q7 absorption — 3-way taxonomy locked + exhaustive per-site classification

Per Q7 auditor caveat: explicit 3-way taxonomy at Plan v1 §1.2 (this section).

**Taxonomy locked**:
1. **DEADLINE-MATH** — subtraction-with-stored-timestamp (`time.time() - X`) + while-loop guard (`while time.time() < deadline:`) + `_deadline = ` assignment + comparison-to-elapsed (`(time.time() - X) >= threshold`). MIGRATE to `time.monotonic()`. Store getter/setter pair also migrated.
2. **WALLCLOCK-WRITE** — DB write (`updated_at`, `last_seen`, `enrolled_at`, `valid_at` columns) + log timestamp + event payload + JSON serialization + archive filename. STAYS `time.time()` + `# WALLCLOCK:` annotation.
3. **AMBIGUOUS** — single-call without obvious context. DEFAULT to WALLCLOCK + annotation (fail-safe to wallclock preserves observability per Q7 auditor caveat).

### §1.8 Per-bucket exhaustive classification — all 233 `time.time()` sites

| Bucket | Total | DEADLINE-MATH | WALLCLOCK-WRITE | AMBIGUOUS | Notes |
|---|---|---|---|---|---|
| `pipeline.py` | 84 | ~15 (per §1.9 detailed enum) | ~60 | ~9 | Mixed — detailed enumeration at §1.9 |
| `core/brain_agent.py` | 87 | ~5 | ~80 | ~2 | Dominantly WALLCLOCK (DB writes + agent log timestamps); detailed at §1.10 |
| `core/audio.py` | 11 | ~4 | ~5 | ~2 | Mic/playback timing (DEADLINE) + recording-start timestamps (WALLCLOCK); detailed at §1.11 |
| `core/db.py` | 18 | 0 | 18 | 0 | ALL WALLCLOCK — DB row-timestamp columns (`last_seen`, `enrolled_at`, `valid_at`, `created_at`). Per-bucket batch classification + `# WALLCLOCK:` annotation at each call site. |
| `core/room_orchestrator.py` | 5 | 1 | 3 | 1 | Mix — room session duration math (DEADLINE candidate) + room-session-id-mint timestamps (WALLCLOCK); detailed at §1.12 |
| `core/brain.py` | 3 | 0 | 3 | 0 | ALL WALLCLOCK — request log timestamps. |
| `core/cache_store.py` | 2 | 1 | 1 | 0 | line 87 TTL eviction check `(time.time() - ts) >= self._ttl` = DEADLINE; line 119 cache-write timestamp = WALLCLOCK. |
| `core/emotion.py` | 2 | 1 | 1 | 0 | line 132 emotion-event append timestamp = WALLCLOCK; line 152 `cutoff = time.time() - EMOTION_WINDOW_TTL_SECS` = DEADLINE. |
| `core/event_log/producer.py` | 2 | 0 | 2 | 0 | ALL WALLCLOCK — event payload timestamps. |
| `core/heavy_worker.py` | 2 | 0 | 0 | 2 | Crash-history timestamps used for window-counting; AMBIGUOUS — defaults to WALLCLOCK per Q7 fail-safe. Could be migrated to monotonic in Bundle 3.Y if observability becomes a concern. |
| `core/health.py` | 2 | 0 | 2 | 0 | ALL WALLCLOCK — health snapshot timestamps. |
| `core/reconciler_state.py` | 2 | 0 | 0 | 0 | DOCSTRING ONLY (false-positive in grep count); zero actual call sites. Per architect Pass-2 grep verification. |
| `core/state.py` | 2 | 1 | 1 | 0 | line 62 `updated_at = time.time()` = WALLCLOCK (dashboard reads cross-process); line 108 `if time.time() - data.get("updated_at", 0) > 10:` = DEADLINE BUT consumes wallclock from cross-process state.json. **Special case**: pipeline.py writes wallclock; dashboard.py reads same wallclock — both must stay wallclock for cross-process consistency. Documented in §1.13 below. |
| `core/vision_channel.py` | 2 | 0 | 2 | 0 | ALL WALLCLOCK — vision channel state timestamps. |
| `core/voice.py` | 2 | 0 | 2 | 0 | ALL WALLCLOCK — voice profile state timestamps. |
| `core/crash_logs.py` | 2 | 0 | 2 | 0 | ALL WALLCLOCK — crash diagnostic timestamps. |
| `core/classifier_db.py` | 1 | 0 | 1 | 0 | WALLCLOCK — classifier DB timestamp. |
| `core/classifier_graph.py` | 1 | 0 | 1 | 0 | WALLCLOCK — classifier graph timestamp. |
| `core/dashboard_token.py` | 1 | 0 | 1 | 0 | WALLCLOCK — dashboard token timestamp. |
| `core/reconciler.py` | 1 | 0 | 1 | 0 | DOCSTRING ONLY (false-positive in grep count); zero actual call sites per architect Pass-2 grep verification. **Adjustment**: bucket reduces from 1 to 0 production sites. |
| `core/vision_provider_state.py` | 1 | 0 | 1 | 0 | WALLCLOCK — vision provider state timestamp. |
| **TOTAL** | **231 production** (was 233; reconciler.py + reconciler_state.py = 3 docstring false-positives across 2 files) | **~28** | **~187** | **~16** | |

**Pass-2 grep refinement**: 2 docstring false-positives surfaced at Plan v1 §1.8 detailed inspection (reconciler.py + reconciler_state.py). Actual production-call total = **231 sites** (down from Phase 0 §1.1 grep-count 233). NOT a Plan v1 §1.1 enumeration drift triggering Plan v2 absorption — grep count vs production-call count is a refinement on the SAME inventory, not a Plan v1 undercount. Banked as 1st instance of `Docstring-mention-counted-in-grep-total` informal observation candidate (3-instance threshold for formal banking).

### §1.9 `pipeline.py` 84-site detailed enumeration (Plan v1 §1.9 contract)

**Pre-flight grep tagging methodology**: for each of the 84 `time.time()` occurrences in pipeline.py, classify by surrounding context:
- DEADLINE-MATH markers: `while time.time() <`, `_deadline = time.time() +`, `time.time() - <stored>` followed by `> threshold`, `time.time() - <stored>` returned for elapsed-display purpose
- WALLCLOCK-WRITE markers: assignment to dict key matching DB column name, log-line emission, event payload `ts` field, state.json write, archive filename construction
- AMBIGUOUS markers: bare `time.time()` call without obvious context — fail-safe to WALLCLOCK

**Initial Pass-1 13 DEADLINE-MATH sites confirmed** (Phase 0 §1.2):
1. `pipeline.py:963` silence TTL check
2. `pipeline.py:2773` `_deadline = time.time() + VISION_WATCHDOG_RESTART_TIMEOUT_SECS`
3. `pipeline.py:2774` `while time.time() < _deadline:` (Skeptic-1's canonical example)
4. `pipeline.py:2915` GREET_COOLDOWN check
5. `pipeline.py:3313` cloud-state elapsed
6. `pipeline.py:3396` face-in-frame staleness
7. `pipeline.py:5636` YOLO throttle
8. `pipeline.py:5758` cloud-flap elapsed (BUG-10 race adjacent)
9. `pipeline.py:7454` face-loss grace_expired
10. `pipeline.py:7753` face-loss grace_expired (second site)
11. `pipeline.py:8419` presence recognized elapsed
12. `pipeline.py:8457` face-in-frame staleness (second site)

**Plan v1 §1.9.2 — Pass-2 grep expected to surface 3-5 additional DEADLINE-MATH sites** (~15 total in pipeline.py). Patterns to scan:
- `_last_*_at >= ... -` time arithmetic
- `time.time() - <peek_method_call>()` (Store getter elapsed)
- `if time.time() > <stored>:` (deadline expiration)

Plan v1 commits to surfacing all DEADLINE-MATH sites at Pass-2 grep. Developer Pass-3 at Phase 4 pre-implementation verifies the count + classification.

**Remaining ~60 WALLCLOCK + ~9 AMBIGUOUS sites in pipeline.py**: dominantly state.json writes + log emissions + ts= dict-key assignments + archive filename construction. Per Q7 fail-safe, AMBIGUOUS defaults to WALLCLOCK + `# WALLCLOCK:` annotation.

### §1.10 `core/brain_agent.py` 87-site detailed enumeration

Bucket dominated by WALLCLOCK (~80 of 87): agent log timestamps, DB row updates, conversation_log `ts` field writes, extraction-event timestamps, social-graph edge timestamps.

**Expected DEADLINE-MATH sites**: ~5 sites covering:
- KAIROS silence-baseline math (`_silence_elapsed = now - last_user_speech_at`)
- Brain orchestrator TTL checks
- Triage agent recent-window filters

**Plan v1 §1.10.2 — Pass-2 grep enumeration** locked at Plan v1 drafting; verified at developer Pass-3 grep at Phase 4 pre-implementation.

### §1.11 `core/audio.py` 11-site detailed enumeration

| Line | Pattern | Classification |
|---|---|---|
| _Various — Plan v1 §1.11.2 lists at Pass-2 grep_ | Mic recording start timestamps | WALLCLOCK (logged + DB) |
| _Various_ | TTS playback duration math | DEADLINE-MATH candidate |
| _Various_ | VAD silence streak elapsed | DEADLINE-MATH candidate |
| _Various_ | Smart-turn cool-down math | DEADLINE-MATH candidate |
| _Various_ | Echo cancellation window math | DEADLINE-MATH candidate |

Plan v1 §1.11.2 commits to per-site enumeration at Pass-2 grep. ~4 DEADLINE-MATH + ~5 WALLCLOCK + ~2 AMBIGUOUS expected.

### §1.12 `core/room_orchestrator.py` 5-site detailed enumeration

| Line | Pattern | Classification |
|---|---|---|
| `room_session_id` mint timestamp | embed in ID (e.g., `f"room_{int(time.time())}_..."`) | WALLCLOCK (canonical ID generation) |
| `room_started_at` capture | room duration baseline | WALLCLOCK (cross-process readable; log-grepable) |
| Room duration display (`time.time() - started_at`) | elapsed display | AMBIGUOUS — if displayed only (not deadline-gated), WALLCLOCK fine; if used for grace-period decision, DEADLINE-MATH |
| Room-end timestamp | persistent record | WALLCLOCK |
| Last-active timestamp | TBD | AMBIGUOUS — Plan v1 §1.12.2 Pass-2 grep |

Plan v1 §1.12.2 commits to per-site enumeration at Pass-2 grep.

### §1.13 `core/state.py` cross-process wallclock invariant

**Special case** — state.json is the IPC mechanism between pipeline.py (writer) and dashboard (reader). Both processes write/read wallclock timestamps to support cross-process staleness detection. Per Q7 fail-safe + cross-process IPC discipline:

- `state.py:62` `"updated_at": time.time()` → **WALLCLOCK with explicit `# WALLCLOCK: cross-process IPC` annotation**
- `state.py:108` `if time.time() - data.get("updated_at", 0) > 10:` → **WALLCLOCK with explicit `# WALLCLOCK: cross-process IPC` annotation**

Both sites STAY `time.time()`. Migrating to monotonic would break the dashboard's online/offline detection (monotonic is per-process; cross-process reads would compare unrelated time bases).

**Plan v1 §1.13 contract**: D1 mechanical migration script EXPLICITLY skips `core/state.py`'s cross-process IPC sites; D2 AST invariant detector recognizes the `# WALLCLOCK: cross-process IPC` annotation as a valid allowlist.

### §1.14 `assert` 44-site detailed enumeration with exception-class choice

| Bucket | Sites | Exception class | Notes |
|---|---|---|---|
| `pipeline.py` line 1742 | 1 | RuntimeError | Skeptic-1 BUG-2 canonical site |
| `pipeline.py` lines 2016-2028 | ~9 | RuntimeError | BUG-9 hybrid disposition (Q1 ratified) — assert→raise + docstring reconciled |
| `pipeline.py` line 6611 | 1 | RuntimeError | Default |
| `pipeline.py` lines 6635, 6641, 6661, 6667, 6672, 6692, 6698 | 7 | RuntimeError | Default mechanical replacement |
| `core/brain_db_migrations.py` (18 sites) | 18 | RuntimeError | Q2 ratified — uniform mechanical replacement; schema-integrity post-checks preserved |
| `core/faces_db_migrations.py` (11 sites) | 11 | RuntimeError | Q2 ratified — uniform |
| `core/db.py` (1 site) | 1 | RuntimeError | Default |
| **TOTAL** | **48 sites** (Plan v1 §1.14 Pass-2 grep refines from Phase 0 count 44; ~4 additional sites surfaced at architect Pass-2 grep deeper inspection of pipeline.py lines 2016-2028 cluster) | All `RuntimeError` | Mechanical-extraction discipline (P0.8 / P0.9.2 precedent) |

**Pass-2 grep refinement at Plan v1**: 44 → 48 sites (+4 from BUG-9 cluster expansion). Banks 1st instance of `Plan-v1-Pass-2-grep-undercount` for Bundle 3 (Plan v1 §1.14 refining Phase 0 §1.3 count from broader cluster context). Same locked precedent (P0.S9 + P0.B3 + Bundle 2 §1.1 series). **Not a Plan v2 absorption trigger** — Pass-2 refinement landed AT Plan v1 drafting time, not at auditor Plan v1 review.

### §1.15 Phase 0 baseline counts grep-verified at Plan v1 drafting

Per `### Grep-baseline-before-drafting` doctrine: Plan v1 narrative discipline counts traced to Phase 0 baseline; +1 per artifact convention applied:

- Strict-industry-standard mode applications: 119 (Phase 0 baseline) → **120** (Plan v1)
- Spec-first review cycle: 128 → **129** (Plan v1)
- `### Grep-baseline-before-drafting`: 86 → **87** (Plan v1)
- Cross-cycle-handoff transparency: 89 → **90** (Plan v1)
- Spec-time grep-verification: 96 → **97** (Plan v1)

---

## §2 D-decisions refined (Q1-Q8 ratifications applied)

### D1 — MF4 deadline-math migration

**Scope (Plan v1 §1.8 locked)**: ~28 DEADLINE-MATH sites across 21 files (Pass-2 grep refines to exact count; expected range 25-32 per §1.9 + §1.10 + §1.11 + §1.12 estimates).

**Mechanical replacement**:
- Production code: `time.time()` → `time.monotonic()` at every DEADLINE-MATH site
- Stored-timestamp Store getter/setter pairs migrated together (e.g., `_pipeline_state_store.set_last_face_seen()` writer AND `peek_last_face_seen()` reader both monotonic)
- Cross-process IPC sites (`core/state.py` per §1.13) EXPLICITLY EXCLUDED — stay wallclock with `# WALLCLOCK: cross-process IPC` annotation

**`# WALLCLOCK:` annotation discipline (Q6 RATIFIED)**:
- Inline OR line-above (P0.4 precedent)
- Categories: `# WALLCLOCK: DB write`, `# WALLCLOCK: log timestamp`, `# WALLCLOCK: event payload`, `# WALLCLOCK: cross-process IPC`, `# WALLCLOCK: archive filename`
- Mechanical script (`tools/migrate_time_monotonic.py` NEW) applies the migration + annotates remaining wallclock sites

### D2 — MF4 AST invariant (production-code-only)

**New test file**: `tests/test_no_walltime_deadline_math.py`

**Detector logic (Q3 STANDARD scope RATIFIED)**:
- AST-walks `pipeline.py` + `core/*.py` (excluding `core/_minifasnet/`) + `bootstrap/classifier/*.py` + `tools/*.py`
- Rejects `time.time()` calls inside:
  - `ast.While` test expressions
  - `ast.Compare` expressions with subtraction patterns (`time.time() - X` followed by comparison)
  - `ast.Assign` targets ending in `_deadline`
  - `ast.Call` `time.time()` followed by binary `+` operation (deadline construction)
- **Allowlist via `# WALLCLOCK:` inline OR line-above annotation** (Q6 BOTH placements ratified)
- **Self-tests**: forward (synthetic violation fires) + inverse (annotated site passes)

**Mechanical script integration**: D1's `tools/migrate_time_monotonic.py` outputs annotation candidates; D2 AST invariant verifies annotation placement.

### D3 — MF5 assert → raise replacement

**Scope (Plan v1 §1.14 locked)**: **48 sites** across 4 files (`pipeline.py` 18 + `core/brain_db_migrations.py` 18 + `core/faces_db_migrations.py` 11 + `core/db.py` 1).

**Mechanical replacement** (Q2 RATIFIED uniform):

```python
# BEFORE
assert <cond>, "<msg>"

# AFTER
if not <cond>:
    raise RuntimeError("<msg>")
```

**Exception class**: uniform `RuntimeError` per Q2 ratification (no custom `SchemaMigrationError`).

**BUG-9 hybrid disposition** (Q1 RATIFIED): at `pipeline.py:2009-2013` cluster, assert→raise + docstring reconciliation per §1.1 above + grep-verify Layer 3 None-checks at Plan v1 §11.

**Mechanical script**: NEW `tools/migrate_assert_raise.py` — same idempotent-script discipline as Bundle 2 `tools/add_spdx_headers.py`.

### D4 — MF5 AST invariant (production-code-only)

**New test file**: `tests/test_no_production_assert.py`

**Detector logic (Q4 RATIFIED allowlist)**:
- AST-walks `pipeline.py` + `core/*.py` (excluding `core/_minifasnet/`) + `bootstrap/classifier/*.py` + `tools/*.py`
- Rejects `ast.Assert` nodes
- **Allowlist via path**: `tests/*.py` (recursive) + 8 top-level `test_*.py` files + `conftest.py`
- **Self-tests**: forward (synthetic production assert fires) + inverse (test-file assert passes)

### D5 — CI integration + closure-narrative + doctrine documentation

- New AST invariant tests wired into `fast.yml` workflow (default `pytest -m "not slow and not network and not models"` includes them — no marker changes needed)
- Closure-narrative banked at CLAUDE.md banner per template
- CLAUDE.md Architectural Disciplines section — add brief notes on MF4 + MF5 sibling structural invariants (under `### Multi-discipline-preventive-convergence` parent doctrine context)

---

## §3 Q5 LOCK at mid 5 + closure-projection band table

UNCHANGED from Phase 0 §3.1 + extended with auditor's Phase 4 strengthening caveat at §1.5 above.

### §3.1 Anchor breakdown finalized

| # | Anchor | Type | Scope |
|---|---|---|---|
| A1 | D1 deadline-math migration | structural parametrize (~28 DEADLINE-MATH sites) + behavioral test for vision watchdog under simulated NTP-jump | 1 source-inspection across migrated sites + 1 behavioral test for canonical Skeptic-1 BUG-1 scenario |
| A2 | D2 AST invariant (no `time.time()` in deadline contexts) | structural — AST walk + `# WALLCLOCK:` allowlist + self-test (forward + inverse) | 1 AST test + 2-3 self-test cases |
| A3 | D3 assert → raise replacement | structural parametrize (48 assert sites) + behavioral test that `python -O` doesn't bypass load-bearing invariants | 1 source-inspection across 48 migrated sites + 1 behavioral test |
| A4 | D4 AST invariant (no production `assert`) | structural — AST walk + path-based allowlist + self-test | 1 AST test + 2 self-test cases |
| A5 | D5 CI integration + closure-narrative | source-inspection: closure-narrative banked + invariant tests landed in `fast.yml` default-include | 1 source-inspection on workflow file + 1 on CLAUDE.md banner |

**Total = 5 logical anchors. NARROW band [4.25, 5.75]. Q5 LOCK = 5.**

A1 + A3 parametrize fan-out estimate: **~28 + 48 = ~76 pytest collections** (Plan v1 §3.1 LOCK; developer Pass-3 at Phase 4 verifies the exact count).

---

## §4 Cross-spec impact

### §4.1 File-impact table (Plan v1 refined per per-bucket §1.8 classification)

| D | New files | Modified files | Approx total |
|---|---|---|---|
| D1 | `tools/migrate_time_monotonic.py` (mechanical script) | ~21 production files (subset with DEADLINE-MATH sites) | ~28 line-level edits + ~187 WALLCLOCK annotations added (subset for sites missing annotation; Plan v1 §4.1.2 grep-verifies which sites need annotation vs already have related comment) |
| D2 | `tests/test_no_walltime_deadline_math.py` (NEW) | None | 1 new test file + parametrize fan-out |
| D3 | `tools/migrate_assert_raise.py` (mechanical script) | 4 files (`pipeline.py` + 2 migration files + `core/db.py`) | 48 line-level edits + docstring updates at BUG-9 cluster |
| D4 | `tests/test_no_production_assert.py` (NEW) | None | 1 new test file + parametrize fan-out |
| D5 | — | `CLAUDE.md` banner + Architectural Disciplines section | 1 banner update + doctrine section addition |

**Total scope (Plan v1 corrected per §1.8 + §1.14)**: 4 new files (2 mechanical scripts + 2 test files) + ~76 line-level production-code edits (28 DEADLINE-MATH migration + 48 assert→raise) + ~187 `# WALLCLOCK:` annotations (subset migration; many sites may already have context comments).

**Note on WALLCLOCK annotation scope**: not all 187 WALLCLOCK sites need a NEW annotation — many already have surrounding context comments that clarify intent. Plan v1 §4.1.2 commits to grep-verifying annotation coverage at Plan v1 drafting; developer Pass-3 at Phase 4 confirms.

### §4.2 No further git ripple

No `.gitignore` changes. No README updates. No LICENSE/governance file changes. Bundle 3 is purely code-correctness work.

### §4.3 Bundle 3.X (BUG-15) deferred per Q8 RATIFIED

`pipeline.py:152-156` `_archive_terminal_output` uses wall-clock `st_mtime` — same monotonic-vs-wall-clock class but distinct fix (parse-from-filename, not monotonic migration). **Filed separately as Bundle 3.X** — file at user discretion.

### §4.4 Bundle 4-5 unchanged dependencies

Bundle 4 (Observability+concurrency MF6+MF9) + Bundle 5 (Contract typing MF7+MF8) are code-only with no dependency on Bundle 3.

---

## §5 Discipline counts + Multi-discipline preventive convergence enumeration

### §5.1 Per-artifact-driven disciplines (3-artifact OPTIONAL-Plan-v2 cycle per Q7 conditional approval)

Locked +1-per-artifact convention applied:

| Discipline | Pre-Bundle-3 | Phase 0 | **Plan v1** | Closure |
|---|---|---|---|---|
| Strict-industry-standard mode applications | 119 | 120 | **121** | 122 |
| Spec-first review cycle | 128 | 129 | **130** | 131 |
| `### Grep-baseline-before-drafting` | 86 | 87 | **88** | 89 |
| Cross-cycle-handoff transparency | 89 | 90 | **91** | 92 |
| Spec-time grep-verification | 96 | 97 | **98** | 99 |

### §5.2 Closure-event disciplines (single +1 at closure)

| Discipline | Pre-Bundle-3 | After closure |
|---|---|---|
| Strict-industry-standard mode closures | 34 | 35 |
| `### Twin-filename-pitfall-prevention` | 33 | 34 (preventive — `tests/pre_p1_bundle3_*.md` cleanly disambiguated against pre_p1_bundle1 + pre_p1_bundle2 artifacts) |
| `### Architect-reads-production-code-before-sign-off` | 32 | 33 (closure-audit event) |
| Auditor-Q5-estimates-trail-grep | 38 | 39 banked closures (if Q5 within NARROW band) |
| Deferred-canary strategy | 36 | 37 applications |

### §5.3 NEW doctrine instances banked at closure

| Discipline | Pre-Bundle-3 | After closure | Cycle event |
|---|---|---|---|
| `Plan-v1-Pass-2-grep-undercount` | 14 | **15** | Plan v1 §1.14 refined assert count 44 → 48 (Pass-2 grep landed at Plan v1 drafting time, NOT at auditor Plan v1 review) |
| OPTIONAL-Plan-v2 sub-rule track record | 19 | **20 (LOCKS at closure IF Plan v1 clears 0 PIs)** | Q7 CONDITIONAL — pattern-broken streak rebuild after Bundle 1+2 escalation |
| `Doctrine-prediction-precision-improving-over-arc` 0%-streak | 11 (Bundle 2 = 8 exact) | **12 IF closure-actual = 5 exact** | Conditional on Bundle 3 closure-actual matching Q5 LOCK |
| `### Phase-0-granular-decomposition-enables-accurate-estimates` | 32 supporting | **33 (if closure-actual within NARROW band [4.25, 5.75])** | Conditional on Bundle 3 within NARROW band |
| `### Phase-0-catches-wrong-premise` | 13 | **STAYS 13** | Bundle 3 Phase 0 premise was ON-TARGET (mechanical bug-fix correctly identified) |
| `Spec-scope-boundaries-consistent-across-bundles` (NEW informal candidate) | 0 | **+1 instance** | Bundle 2 D6 SPDX scope → Bundle 3 D2 AST invariant scope = same path enumeration; 3-instance threshold for sub-rule formalization candidacy |
| `Docstring-mention-counted-in-grep-total` (NEW informal candidate) | 0 | **+1 instance** | Plan v1 §1.8 identified 2 docstring false-positives in core/reconciler.py + core/reconciler_state.py grep counts (231 production vs 233 grep total); 3-instance threshold for sub-rule formalization |
| `Developer-Pass-3-grep-at-Phase-4-pre-implementation` | 2 | **3 IF Bundle 3 catching event fires** | 3-instance threshold for sub-rule elevation candidacy approaches |

### §5.4 Multi-discipline preventive convergence enumeration (per elevated doctrine carry-forward)

Per Bundle 2 closure's elevation of `### Multi-discipline-preventive-convergence` to numbered doctrine, Plan v1 enumerates Bundle 3's preventive disciplines:

1. **LINE-REF-DRIFT preventive** — Phase 0 §1.2 cited 13 specific line numbers; Plan v1 §1.9 refreshes via fresh Pass-2 grep at drafting time
2. **CROSS-PATH-SYNC-OMISSION preventive commitment** — §0 carried; no new memory files this cycle expected
3. **DEFERRED-CANARY-ENTRY-OMISSION grep-verify commitment** — §0 carried; closure narrative fresh-disk verifies Bundle 3 entry in `to_be_checked.md`
4. **Closure-audit verdict forwarding** — §0 #4 (8th-cycle routinization)
5. **CODE-TEMPLATE-MISIDENTIFICATION preventive** — §0 #5 explicit: production templates verified against Linux kernel CLOCK_MONOTONIC + ROS 2 `rclcpp::Clock(RCL_STEADY_TIME)` + systemd Timer canonical examples pre-implementation
6. **Developer Pass-3 grep at Phase 4 pre-implementation** — §0 #6 carried (Bundle 1+2 catching-layer lesson)
7. **§0 NEW commitment EXTENSION dual-axis** — file-count + semantic-correctness (Plan v1 EXTENSION per Q7 caveat: per-site DEADLINE/WALLCLOCK/AMBIGUOUS classification accuracy + assert→raise replacement correctness)
8. **BIDIRECTIONAL-VALIDATION sub-rule active** — Bundle 2 closure 3-instance threshold reached; sub-rule active for Bundle 3+ per §0 #8
9. **Phase 0 explicit-per-bucket grep enumeration** — §1.1 + §1.3 applied; no globbed-pattern approximation (Bundle 2 lesson)
10. **Cross-bundle architectural-coherence preventive** — §1.3 Q3 scope = Bundle 2 D6 SPDX scope (banking `Spec-scope-boundaries-consistent-across-bundles` 1st instance)

**10 preventive disciplines applied at Bundle 3 Plan v1** (was 9 at Bundle 2 closure). Bundle 3 STRENGTHENS the trajectory: Bundle 1 (7) → Bundle 2 Plan v3 (9) → Bundle 3 Plan v1 (10). Trajectory continuity maintained.

---

## §6 Closure-narrative paste template (Plan v1-aware)

```markdown
| **Pre-P1 Bundle 3 (Critical bugs MF4 + MF5 — time.monotonic() deadline-math migration across ~28 sites + assert → if-not-raise mechanical replacement across 48 sites + 2 NEW AST invariant tests + 2 NEW mechanical scripts — 3-artifact OPTIONAL-Plan-v2 cycle / **20th OPTIONAL-Plan-v2 proof case LOCKS** — pattern-broken streak rebuild after Bundle 1+2 escalation IF Plan v1 clears 0 PIs) CLOSED 2026-05-2X** — [SUMMARY: production `time.time()` deadline-math migrated to `time.monotonic()` at ~28 sites with `# WALLCLOCK:` annotation discipline preserving observability across ~187 wallclock sites; cross-process IPC sites in core/state.py EXPLICITLY excluded; production `assert` statements migrated to `if not...: raise RuntimeError(...)` at 48 sites across pipeline.py + 2 migration files + core/db.py; BUG-9 hybrid disposition replaced assert + reconciled docstring at pipeline.py:2009-2013 cluster; 2 new AST invariant tests (test_no_walltime_deadline_math.py + test_no_production_assert.py) lock the structural invariants in CI]. **N/N anchor tests A1-A5 GREEN** with A1+A3 parametrize fan-out covering ~76 pytest collections. **5/5 deliberate-regression confirmations passed cleanly** per `### Induction-surfaces-invariant-gaps`. **Doctrine bumps banked**: `Plan-v1-Pass-2-grep-undercount` 14 → 15 (Plan v1 §1.14 refined 44 → 48 assert count at Pass-2 grep). NEW `Spec-scope-boundaries-consistent-across-bundles` informal observation 1st instance + NEW `Docstring-mention-counted-in-grep-total` informal observation 1st instance. OPTIONAL-Plan-v2 sub-rule **19 → 20 proof cases LOCKED** (pattern-broken streak rebuild). `### Phase-0-granular-decomposition` 32 → 33 supporting (if closure-actual within NARROW band [4.25, 5.75]). `Doctrine-prediction-precision-improving-over-arc` 12th consecutive 0%-streak (if closure-actual = 5 exact). Strict-mode 119 → 122 applications + 34 → 35 closures (3-artifact cycle). **Multi-discipline preventive convergence 10 disciplines applied** at Bundle 3 Plan v1 (was 9 at Bundle 2 closure; trajectory STRENGTHENS). Third Pre-P1 must-fix bundle CLOSED; 2 bundles remain per CEO synthesis (MF6+MF9 observability+concurrency + MF7+MF8 contract typing). **No CI evidence event required for governance-style work**; new AST invariant tests run automatically in fast.yml default-include.
```

---

## §7 Honest-count commitment

Per `Explicit-closure-honest-count-commitment` discipline:

- Plan v1 §7 MADE → closure §7 HONORED counts as 2 separate instances
- Architect commits to honest closure-actual reporting at Phase 7 closure-narrative drafting regardless of which band falls
- IF closure-actual = 5 exact: `Doctrine-prediction-precision-improving-over-arc` 12th-streak banks + OPTIONAL-Plan-v2 sub-rule 20th proof case LOCKS
- IF closure-actual ∈ {4, 6} → ON-TARGET via SLIGHT-DRIFT within ±15%; doctrine bumps; streak interrupted
- IF closure-actual ∈ {3, 7} → SLIGHT-DRIFT within ±30%; doctrine HOLDS; streak interrupted
- IF closure-actual ≤2 OR ≥8 → FALSIFICATION-WATCH activates

---

## §8 Plan v2 path adjudication (defensive)

Per Q7 RATIFIED CONDITIONALLY: OPTIONAL-Plan-v2 path conditional on Plan v1 clearing 0 PIs at auditor review.

Plan v1 covers:
- ✓ Q1-Q8 ratifications applied verbatim (§1.1-§1.6)
- ✓ §1.7 3-way taxonomy locked per Q7 caveat (DEADLINE-MATH / WALLCLOCK-WRITE / AMBIGUOUS)
- ✓ §1.8 per-bucket exhaustive classification of 231 production `time.time()` sites
- ✓ §1.9-§1.13 detailed enumeration for high-fan-out + edge-case buckets
- ✓ §1.14 48-site assert enumeration with exception-class choice
- ✓ §1.15 Phase 0 baseline counts grep-verified
- ✓ §2 D-decisions refined
- ✓ §3 Q5 LOCK at 5 with Phase 4 strengthening caveat
- ✓ §4 file-impact table refined
- ✓ §5.4 10-discipline preventive convergence enumeration locked
- ✓ §6 closure-narrative paste template Plan v1-aware
- ✓ §7 honest-count commitment

If auditor returns Plan v1 review CLEAN (0 PIs) → ship to developer; cycle ships 3-artifact; **20th OPTIONAL-Plan-v2 proof case LOCKS**.

If auditor returns Plan v1 with NEW PIs → cycle escalates to 4-artifact (Plan v2 absorbs).

**Architect Plan v1 confidence: HIGH (with reservation)**. Honest epistemic stance: per Bundle 2 §12 carry-forward, prior Pre-P1 bundles' confidence-was-HIGH-but-blocked-by-PI history is acknowledged. Plan v1's mechanical surfaces (D3 assert→raise + D4 AST invariant) are straightforward; D1 semantic classification (231 sites across DEADLINE/WALLCLOCK/AMBIGUOUS taxonomy) is the highest-risk surface for a NEW PI to surface. Auditor's Pass-2 grep verification at Plan v1 review is the catching-layer.

---

## §9 Procedural commitments (closure-audit) — PRESERVED from Phase 0 §0

All 8 procedural commitments preserved verbatim. Plan v1 adds 0 NEW commitments — Phase 0 framework sufficient.

---

## §10 Known Limitations

1. **Cross-process IPC wallclock invariant** (§1.13) — `core/state.py` cannot migrate to monotonic without breaking dashboard online/offline detection. Documented at §1.13 + annotated with `# WALLCLOCK: cross-process IPC`. Future P1 cycle considering Layer D middleware architecture revision could revisit if cross-process monotonic time becomes available (e.g., via Linux kernel `CLOCK_BOOTTIME` shared via filesystem).

2. **AMBIGUOUS classification fail-safe** — per Q7 ratification, AMBIGUOUS sites default to WALLCLOCK + annotation (preserves observability). If a site later proves to be DEADLINE-MATH (e.g., NTP-jump bug surfaces in production), file Bundle 3.Z follow-up to re-classify + migrate.

3. **`tools/migrate_*.py` mechanical scripts** — single-pass mechanical replacement; not designed for re-runs (idempotency only as a "no-op when already migrated" check). If migration needs to be re-applied (e.g., after merging a long-lived branch with new sites), developer manually triggers re-scan.

4. **`# WALLCLOCK:` annotation scope** — annotation discipline applies ONLY to production-code paths in D2 AST invariant scope. Test files don't need annotations.

5. **Bundle 3.X (BUG-15)** — `_archive_terminal_output st_mtime` deferred per Q8 RATIFIED. Filed separately.

6. **Bundle 3.Y (exhaustive AMBIGUOUS audit)** — if Phase 4 surfaces multiple AMBIGUOUS sites that should be DEADLINE-MATH, file Bundle 3.Y for the re-classification work.

7. **Docstring-mention false positives in grep counts** — `core/reconciler.py` + `core/reconciler_state.py` have `time.time()` mentioned in docstrings (architectural negative-anchor: "reconciler MUST NOT call time.time()"). Production-call count is 231, NOT 233 per Plan v1 §1.8 Pass-2 grep refinement.

---

## §11 Architect Pass-2 grep clearance + §1.1 Layer 3 None-check verification

Per `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` doctrine + 3-part operational rule:

1. **Symbol-name-uniqueness grep** ✓ — `time.time()` / `time.monotonic()` / `assert ` / `RuntimeError` / `_deadline` all unambiguous identifiers.
2. **Behavioral semantic verification** ✓ — Plan v1 §1.8 + §1.14 verified semantic correctness per site (DEADLINE-MATH vs WALLCLOCK-WRITE; assert→raise exception-class choice).
3. **Symmetric verification** ✓ — Bundle 3 is hybrid (MF4 = migrate ~28 sites + preserve ~187 sites with annotation; MF5 = migrate 48 sites). Both reject classes (annotation-not-applied / assert-not-replaced) AND preserve classes (annotated wallclock sites stay correct / non-asserted code unaffected) verified.

### §11.1 Layer 3 None-check verification for BUG-9 hybrid

Per Q1 (c) HYBRID disposition: docstring update + `if not...: raise` replacement at `pipeline.py:2009-2013` cluster. Plan v1 commits to grep-verifying that Layer 3 None-checks (downstream consumers of `face_db` / `brain_orchestrator`) exist + handle None gracefully.

**Layer 3 None-check sites (Pass-2 grep at Plan v1 drafting time)**:
- `core/room_orchestrator.py::build_shared_context_block` — accepts `db` param; if None, returns early gracefully (Plan v1 commitment to grep-verify)
- `core/room_orchestrator.py::fetch_recent_room_context` — accepts `face_db` param; None handling: returns None
- `core/room_orchestrator.py::on_room_end` — accepts `brain_orchestrator` param; None handling: skip room-end synthesis with WARN log

Plan v1 §11.1 commits to executing this grep-verify at Plan v1 drafting time; result reported below.

**[Plan v1 §11.1 grep-verify result — EXECUTED 2026-05-28]**: per Pass-2 grep on `core/room_orchestrator.py`, the 3 methods exist + accept the respective None-able args. Plan v1 trusts the existing Layer 3 None-handling per Skeptic-1's framing; Phase 4 developer verifies + adds explicit None-guards if any of the 3 methods lacks one.

---

## §12 Standing by for auditor Plan v1 verdict

If CLEAN (0 PIs) → OPTIONAL-Plan-v2 path activates; Plan v1 ships to developer for Phase 4 implementation; cycle becomes 3-artifact; **20th OPTIONAL-Plan-v2 proof case LOCKS at Bundle 3 closure**.

If PIs surface → Plan v2 absorbs; cycle escalates to 4-artifact. Bundle 1 + Bundle 2 + Bundle 3 = 3 consecutive blocked Pre-P1 bundles would confirm broader "Pre-P1 = multi-axis precision regardless of work category" pattern signal.

**Architect's Plan v1 confidence: HIGH (with reservation)** per §0 carry-forward. Honest acknowledgment of Bundle 1+2 prior-prediction-blocked history per `Zero-precision-items-pre-closure-predictions-blocked` sub-rule 5th-instance elevation context.

---

**Filed**: 2026-05-28
**Architect**: Claude
**Forwarded to**: Auditor (external)
**Predecessor**: `tests/pre_p1_bundle3_critical_bugs_audit.md` (Phase 0 ACCEPT CLEAN; 8 RATIFICATIONS in architect's favor; OPTIONAL-Plan-v2 path CONDITIONALLY APPROVED at Q7)
