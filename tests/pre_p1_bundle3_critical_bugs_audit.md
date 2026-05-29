# Pre-P1 Bundle 3 — Critical Bugs (MF4 + MF5) Phase 0 Audit (2026-05-28)

**Cycle**: Pre-P1 must-fix Bundle 3 (Critical Bugs)
**Scope**: MF4 (`time.time()` → `time.monotonic()` for deadline-math) + MF5 (production `assert` → `if not: raise`)
**Source**: skeptic1-bugs-edges-2026-05-27.md BUG-1 + BUG-2
**Sequencing**: Pre-P1 must-fix sequence position 3 of 5 (per CEO synthesis Path A locked) — sequential after Bundle 2 close 2026-05-28
**Discipline**: Strict-mode; §0 NEW commitment EXTENSION (Bundle 2 carry-forward) applied — explicit per-bucket grep enumeration at Phase 0
**Architect**: Claude
**Auditor**: External

---

## §0 Procedural commitments (Bundle 2 carry-forward)

Per Bundle 2 closure-audit ratification 2026-05-28:

1. **Path C grep-verify** at closure surface (production code + memory files + index entries + `to_be_checked.md` fresh-disk Python read)
2. **Cross-path memory-file discipline** if any new memory files land
3. **DEFERRED-CANARY-ENTRY-OMISSION preventive** via fresh-disk Python read at closure
4. **Closure-audit verdict forwarding** to auditor (8th-cycle routinization)
5. **CODE-TEMPLATE-MISIDENTIFICATION preventive** — verify production-code templates (deadline-math patterns) against canonical examples (Linux kernel CLOCK_MONOTONIC + ROS 2 rclcpp::Clock RCL_STEADY_TIME + systemd Timer monotonic) before locking
6. **§0 NEW commitment EXTENSION** — Bundle 1 + Bundle 2 lesson: developer Pass-3 grep at Phase 4 pre-implementation MUST verify file-count consistency + semantic-correctness per site (Bundle 3 dual-axis = deadline-vs-wallclock semantic + assert-vs-raise replacement correctness)
7. **9-discipline preventive convergence enumeration** at Plan v1 §5.4 + preserved at closure (elevation-event-lock discipline applied)
8. **BIDIRECTIONAL-VALIDATION sub-rule honoring** — 3-instance threshold reached at Bundle 2; sub-rule active for Bundle 3+

---

## §1 Grep-verified scope baseline (2026-05-28)

Per `### Grep-baseline-before-drafting` doctrine + Bundle 2's `Phase-0-globbed-pattern-estimates-imprecise-explicit-enumeration-precise` lesson: explicit per-bucket grep enumeration locked at Phase 0 drafting time. NO globbed-pattern approximation.

### §1.1 MF4 — `time.time()` total inventory

| Bucket | `time.time()` site count | Notes |
|---|---|---|
| `pipeline.py` | 84 | Includes deadline-math + wallclock-write + log-timestamp sites |
| `core/brain_agent.py` | 87 | Mostly wallclock — DB writes, agent log timestamps |
| `core/audio.py` | 11 | Mix; mic/playback timing candidates for monotonic |
| `core/db.py` | 18 | Mostly wallclock — `last_seen` / `enrolled_at` / `valid_at` |
| `core/room_orchestrator.py` | 5 | Room session timing — likely mixed |
| `core/brain.py` | 3 | Wallclock — request log timestamps |
| `core/cache_store.py` | 2 | Cache TTL — likely DEADLINE-MATH (monotonic candidate) |
| `core/emotion.py` | 2 | Likely TTL — DEADLINE candidate |
| `core/event_log/producer.py` | 2 | Event log timestamps — WALLCLOCK |
| `core/heavy_worker.py` | 2 | Heavy-worker watchdog — likely DEADLINE candidate |
| `core/health.py` | 2 | Health snapshot — likely WALLCLOCK |
| `core/reconciler_state.py` | 2 | State timestamps — TBD |
| `core/state.py` | 2 | Persistent state — WALLCLOCK |
| `core/vision_channel.py` | 2 | Vision channel state — TBD |
| `core/voice.py` | 2 | Voice profile state — TBD |
| `core/crash_logs.py` | 2 | Crash diagnostic timestamps — WALLCLOCK |
| `core/classifier_db.py` | 1 | Classifier DB timestamp — WALLCLOCK |
| `core/classifier_graph.py` | 1 | Classifier graph timestamp — WALLCLOCK |
| `core/dashboard_token.py` | 1 | Dashboard token timestamp — WALLCLOCK |
| `core/reconciler.py` | 1 | TBD |
| `core/vision_provider_state.py` | 1 | TBD |
| **TOTAL** | **233 sites across 21 files** | |

### §1.2 MF4 — Initial deadline-math grep (Pass-1)

Pattern: `_deadline = time\.time\(\)|while time\.time\(\)|time\.time\(\) - _` (initial heuristic; Plan v1 will broaden to comparison-with-stored-timestamp patterns):

13 deadline-math candidates surfaced at Phase 0 §1.2 Pass-1 grep:
- `pipeline.py:963` — `time.time() - _pipeline_state_store.peek_last_silent_update() < 5.0` (silence TTL check)
- `pipeline.py:2773-2774` — `_deadline = time.time() + VISION_WATCHDOG_RESTART_TIMEOUT_SECS; while time.time() < _deadline:` (Skeptic-1's canonical BUG-1 example)
- `pipeline.py:2915` — `time.time() - _conversation_store.peek_last_greeted(_pid) >= GREET_COOLDOWN`
- `pipeline.py:3313` — `time.time() - _pipeline_state_store.peek_cloud_failed_at()` (cloud-state recovery elapsed)
- `pipeline.py:3396` — `time.time() - _pipeline_state_store.peek_last_face_seen() < 2.0` (face-in-frame staleness)
- `pipeline.py:5636` — `time.time() - _yolo_last_ran < 30.0` (YOLO throttle)
- `pipeline.py:5758` — `elapsed = time.time() - _pipeline_state_store.peek_cloud_failed_at()` (cloud-flap race per BUG-10)
- `pipeline.py:7454` — `grace_expired = time.time() - _pipeline_state_store.peek_last_face_seen() > FACE_LOSS_GRACE`
- `pipeline.py:7753` — `time.time() - _fl_snap.last_face_seen > FACE_LOSS_GRACE`
- `pipeline.py:8419` — `time.time() - _presence_store.peek_last_recognized_at(_cur_pid, 0.0)`
- `pipeline.py:8457` — `time.time() - _pipeline_state_store.peek_last_face_seen() < 2.0`
- `core/brain_agent.py:6908` — `_rebuild_secs = time.time() - _rebuild_t0` (Kuzu graph rebuild duration)

**Plan v1 will exhaustively classify all 233 sites** via per-line grep + semantic inspection. Pass-1 surface gives initial scope sense; Plan v1's Pass-2 enumeration + auditor's Pass-2 verification + developer's Pass-3 at Phase 4 pre-implementation are the load-bearing layers.

### §1.3 MF5 — `assert` statement inventory

| Bucket | `assert` site count | Notes |
|---|---|---|
| `pipeline.py` | 14 | Skeptic-1's canonical BUG-2 enumeration: lines 1742, 2016-2028, 6611, 6635, 6641, 6661, 6667, 6672, 6692, 6698 |
| `core/brain_db_migrations.py` | 18 | Schema-version assertions in migration apply/verify functions |
| `core/faces_db_migrations.py` | 11 | Schema-version assertions in migration apply/verify functions |
| `core/db.py` | 1 | DB invariant |
| **TOTAL** | **44 sites across 4 files** | |

### §1.4 Out-of-scope siblings (Bundle 3.X candidates)

Skeptic-1's catalog flagged the following same-class bugs that don't fit Bundle 3's narrow MF4+MF5 scope:

- **BUG-15** (`pipeline.py:152-156` `_archive_terminal_output` uses `st_mtime`) — same monotonic-vs-wall-clock class but fix is "parse from filename", NOT monotonic migration. Sev: LOW. **Bundle 3.X candidate** — file separately.
- **BUG-3** (`_log_drain` / `_log_q` / `_LOG_FILE` quartet) — observability bug; goes in Bundle 4 per CEO synthesis.
- **BUG-9** (assert + docstring contradiction at pipeline.py:2009-2013) — fix is "drop the assert and let Layer 3 None-checks handle it" per Skeptic-1's spec. **In-scope** for MF5 since Bundle 3 deletes the assert + relies on the docstring's Layer 3 contract. Plan v1 §1.5 sub-decision.
- **BUG-12** (`_LOG_FILE` rebound without lock) — concurrency bug; goes in Bundle 4 per CEO synthesis.

### §1.5 Phase 0 grep-baseline counts (per `### Grep-baseline-before-drafting`)

Pre-Bundle-3 baseline (post-Bundle-2 closure-ratification 2026-05-28):
- Strict-industry-standard mode applications: 119
- Strict-industry-standard mode closures: 34
- Spec-first review cycle: 128
- `### Grep-baseline-before-drafting`: 86
- Cross-cycle-handoff transparency: 89
- Spec-time grep-verification: 96
- `### Twin-filename-pitfall-prevention`: 33
- `### Architect-reads-production-code-before-sign-off`: 32 (with 4 sub-rules including elevated BIDIRECTIONAL-VALIDATION)
- `### Multi-discipline-preventive-convergence`: NEW numbered doctrine (Bundle 2 ELEVATION; baseline = 9 preventives preserved at Bundle 2 closure)
- Auditor-Q5-estimates-trail-grep: 38
- `### Phase-0-granular-decomposition-enables-accurate-estimates`: 32 supporting
- `Doctrine-prediction-precision-improving-over-arc`: 11 consecutive 0%-streak instances
- OPTIONAL-Plan-v2 sub-rule track record: 19 (STAYS — 2 consecutive blocked Pre-P1 bundles signal architecture-cost-benefit lesson)

---

## §2 D-decisions (initial; subject to Plan v1 refinement)

### D1 — MF4 deadline-math migration (production code)

Replace `time.time()` with `time.monotonic()` at every deadline-math site (subtraction-of-stored-timestamp + comparison-to-elapsed + `_deadline =` assignments + `while time.time() < ...` loop conditions).

**Scope (Plan v1 will lock exact count via exhaustive per-site classification)**: ~15-20 deadline-math sites across `pipeline.py` + `core/` (initial Pass-1 surfaced 13 candidates; Plan v1 broadens to all comparison-with-stored-timestamp patterns).

**`# WALLCLOCK:` annotation discipline**: legitimate wall-clock sites (DB writes, log timestamps, JSON-serialized event payloads, archive filename generation) MUST carry an inline `# WALLCLOCK:` annotation comment so the AST invariant test can allowlist them. Same shape as P0.4 `# OPTIONAL:` / `# RACE:` / `# CLEANUP:` annotation pattern.

**Stored timestamp interpretation**: when a deadline-math site reads from a Store (e.g., `_pipeline_state_store.peek_cloud_failed_at()`), the Store's setter must also be migrated to write monotonic time. Plan v1 enumerates Store getter/setter pairs.

### D2 — MF4 AST invariant test (production-code-only)

New `tests/test_no_walltime_deadline_math.py` (preferred) OR extend `tests/test_silent_except_invariant.py`. AST-walks `pipeline.py` + `core/*.py`; rejects `time.time()` calls inside:
- `ast.While` test expressions
- `ast.Compare` expressions involving subtraction (`time.time() - X`)
- `ast.Assign` targets ending in `_deadline` (heuristic; may broaden)
- `ast.Call` to `time.time` followed by `+ <timedelta>` for deadline construction

**Allowlist via `# WALLCLOCK:` inline comment** at the offending line OR same-line+1 (matching P0.4 annotation pattern). Self-tests for the detector itself (forward-test catches violations; inverse-test passes on allowlisted sites).

### D3 — MF5 assert → raise replacement (production code)

Replace every `assert <cond>, "<msg>"` in `pipeline.py` + `core/*.py` with explicit:

```python
if not <cond>:
    raise RuntimeError("<msg>")
```

Preserves error semantic AND survives `python -O`. Mechanical-extraction discipline (sed-able pattern per Skeptic-1's spec).

**Exception classes**: `RuntimeError` is the default; specific sites may use `AssertionError` (if downstream catches that explicitly), `ValueError` (if input validation), or domain-specific exceptions (e.g., `sqlite3.IntegrityError` for migration assertions). Plan v1 enumerates per-site exception choice.

**Migration files exception**: `core/brain_db_migrations.py` (18 asserts) + `core/faces_db_migrations.py` (11 asserts) — these are schema-integrity post-checks. Skeptic-1's example said "assert post-state correctness in migration verify_post functions". These are LOAD-BEARING (a stripped-under-`-O` migration assert means schema drift goes silent). Plan v1 confirms exception choice.

**BUG-9 in-scope (per Skeptic-1's spec)**: `pipeline.py:2009-2013` docstring says "face_db/brain_orchestrator may be None"; the assert contradicts this. Plan v1 either (a) keeps the assert (treating docstring as outdated), (b) drops the assert (treating docstring as authoritative), or (c) replaces with `if not condition: raise` + reconciles docstring. **Q1 RAISED to auditor — see §6**.

### D4 — MF5 AST invariant test (production-code-only)

New `tests/test_no_production_assert.py` (preferred) OR extend `tests/test_silent_except_invariant.py`. AST-walks `pipeline.py` + `core/*.py` + `bootstrap/classifier/*.py` + `tools/*.py`; rejects `ast.Assert` nodes.

**Allowlist via path** (not annotation): `tests/*.py` + `tests/fixtures/*.py` + top-level `test_*.py` files. Assertions in test code are legitimate (test framework consumes them). Plan v1 locks exact allowlist scope.

**Self-test for detector**: forward-test catches a synthetic `assert` in production; inverse-test passes on a test-file assertion.

### D5 — Closure-narrative update + CI integration

Append Bundle 3 closure entry to CLAUDE.md banner per locked template. Update test counts. Document MF4 + MF5 architectural invariants in CLAUDE.md doctrine section (sibling to P0.4 silent-except invariant). Wire new AST invariant tests into `fast.yml` workflow (already runs `pytest -m "not slow and not network and not models"` by default; new tests are not slow/network/models marked).

---

## §3 Q5 LOCK projection — anchor count estimate

**Initial estimate (Phase 0)**: **5 anchors** at mid; NARROW band ±15% = [4.25, 5.75] → ON-TARGET = {5}; SLIGHT-DRIFT = {4, 6, 7} within ±30%; FALSIFICATION = ≤3 OR ≥8.

| # | Anchor | Type |
|---|---|---|
| A1 | D1 deadline-math migration | structural parametrize across deadline-math sites (count locked at Plan v1 §1.2 Pass-2 grep enumeration) + behavioral test for vision watchdog under simulated NTP-jump scenario |
| A2 | D2 AST invariant (no `time.time()` in deadline contexts) | structural — AST walk + WALLCLOCK allowlist + self-test |
| A3 | D3 assert → raise replacement | structural parametrize across 44 assert sites + behavioral test that `python -O pipeline.py` no longer silently bypasses load-bearing invariants |
| A4 | D4 AST invariant (no production `assert`) | structural — AST walk + path-based allowlist + self-test |
| A5 | D5 CI integration + closure-narrative | source-inspection: closure-narrative banked + invariant tests landed in `fast.yml` default-include |

**Auditor-Q5 estimate requested**: ratify Q5 LOCK at 5 OR adjust based on auditor's read of D-decision granularity + AST-invariant complexity.

**Per `### Phase-0-granular-decomposition-enables-accurate-estimates` discipline**: Plan v1 will decompose each D-decision into named-edit-site granularity to maximize estimate precision. Bundle 3's 233 `time.time()` + 44 `assert` sites are HIGH-fan-out work; A1 + A3 parametrize fan-out will be the dominant collection contributors at closure.

---

## §4 Cross-spec impact

### §4.1 File-impact table (initial; Plan v1 will refine via Pass-2 grep)

| D | New files | Modified files | Approx scope |
|---|---|---|---|
| D1 | — | `pipeline.py` + `core/*.py` (subset; Plan v1 locks exact list) + possibly Store classes (peek_X_at setter/getter pairs) | ~15-20 deadline-math sites |
| D2 | `tests/test_no_walltime_deadline_math.py` (NEW) | None | 1 new test file + N parametrize cases |
| D3 | — | `pipeline.py` (14 asserts) + `core/brain_db_migrations.py` (18) + `core/faces_db_migrations.py` (11) + `core/db.py` (1) | 44 assert sites |
| D4 | `tests/test_no_production_assert.py` (NEW) | None | 1 new test file + N parametrize cases |
| D5 | — | `CLAUDE.md` banner + closure-narrative entry | 1 banner update + doctrine section addition |

**Total scope estimate (Phase 0)**: 2 new test files + ~60-65 line-level production-code edits (15-20 deadline + 44 assert) + 1 banner update.

**Plan v1's developer Pass-3 grep at Phase 4 pre-implementation** will lock exact counts per §0 NEW commitment EXTENSION.

### §4.2 No Bundle 4-5 dependency

Bundle 4 (Observability+concurrency MF6+MF9) + Bundle 5 (Contract typing MF7+MF8) are code-only with no governance/CI dep on Bundle 3. **All 3 remaining bundles can ship in parallel after Bundle 2 closes** OR sequentially per Path A locked at CEO decisions doc. User chose sequential (per Bundle 2 close adjudication 2026-05-28).

### §4.3 Bundle 3.X candidates (filed at Phase 0)

- **Bundle 3.X — BUG-15 archive `st_mtime`** (separate cycle): `pipeline.py:152-156` `_archive_terminal_output` uses wall-clock `st_mtime`. Sev: LOW. Fix: parse creation time from filename (`_YYYY-MM-DD_HHMMSS` already in archive names) rather than `st_mtime`. NOT in Bundle 3 scope.
- **Bundle 3.Y — exhaustive `time.time()` audit** (if Phase 0's classification proves ambiguous): rather than block Bundle 3 on classification debates, ship the unambiguous deadline-math sites + file Bundle 3.Y for the ambiguous-class sites. Plan v1 will adjudicate.

---

## §5 Auditor pre-emption + RATIFICATION QUESTIONS

### Q1 — BUG-9 in-scope or deferred?

**Skeptic-1's framing**: `pipeline.py:2009-2013` assert contradicts the docstring ("face_db / brain_orchestrator may be None"). Skeptic-1's prescribed fix: "drop the assert and let the Layer 3 None-checks (per docstring) handle it".

**Options**:
- **(a) In-scope**: D3 drops the assert; docstring becomes the contract; Layer 3 None-checks (downstream consumers) handle the None case. Plan v1 grep-verifies that Layer 3 None-checks exist at the named call sites.
- **(b) Deferred to Bundle 3.Y**: BUG-9 is structurally distinct from MF5's "production assert vanishes under -O" core concern. Bundle 3 ships the mechanical 14-site assert→raise migration in pipeline.py; BUG-9's docstring/assert contradiction gets a dedicated cycle.
- **(c) Hybrid**: D3 replaces with `if not...: raise` (default) + Plan v1 §1.5 sub-decision documents the docstring contradiction as a known-resolved tension.

**Architect lean**: (c). Mechanical migration preserves the assert's intent (load-bearing fail-loud); the docstring's "may be None" framing is the test-context concession; the conflict gets resolved by keeping the runtime invariant + updating the docstring to reflect production-vs-test scope.

**Auditor adjudication requested**.

### Q2 — Migration-file asserts: keep or migrate?

**Context**: 29 asserts in `core/brain_db_migrations.py` (18) + `core/faces_db_migrations.py` (11). These are schema-integrity post-checks (e.g., `assert cur.execute("SELECT ...").fetchone()[0] == expected_value, "...migration verify_post..."`). They're LOAD-BEARING — a stripped-under-`-O` migration assert means schema drift goes silent.

**Options**:
- **(a) In-scope (default)**: migrate all 29 to `if not...: raise RuntimeError(...)`. Preserves runtime correctness. Adds verbosity.
- **(b) Custom exception**: migrate to `if not...: raise SchemaMigrationError(...)` with a domain-specific exception class. Cleaner downstream catching.
- **(c) Bundle 3 ships pipeline.py 14 sites only; migration asserts deferred** to Bundle 3.Y. Reduces Bundle 3 scope.

**Architect lean**: (a). Mechanical migration; matches Skeptic-1's spec ("replace every assert in `core/*.py` and `pipeline.py`"); preserves the bug-prevention property without adding new exception machinery.

**Auditor adjudication requested**.

### Q3 — D2 AST invariant scope: pipeline.py + core/ only OR broader?

**Skeptic-1's spec**: "AST invariant: ban `time.time()` inside `while` / `for` loop conditions in production code (allowlist explicit DB-timestamp sites with `# WALLCLOCK:` annotation)".

**Options**:
- **(a) Narrow**: `pipeline.py` + `core/*.py` only.
- **(b) Standard**: `pipeline.py` + `core/*.py` + `bootstrap/classifier/*.py` + `tools/*.py` (matches Bundle 2 D6 SPDX scope, excluding `core/_minifasnet/`).
- **(c) Broad**: any `.py` file outside `tests/*.py`.

**Architect lean**: (b). Matches the SPDX scope locked at Bundle 2 (same boundaries; consistent disciplines). Future P1.* cycles inherit the same allowlist.

**Auditor adjudication requested**.

### Q4 — D4 AST invariant: allowlist `tests/fixtures/*.py` + top-level `test_*.py`?

**Architect lean**: yes. `tests/*.py` includes `tests/fixtures/*.py`. Top-level test files (`test_brain_agent.py`, `test_brain_response.py`, etc., per Bundle 2 §11.1 enumeration) are out-of-Bundle-2-SPDX-scope but ARE legitimate test code where `assert` is appropriate. Allowlist includes them.

**Auditor adjudication requested**.

### Q5 — Anchor count: 5 mid? OR auditor sees different decomposition?

Per `### Phase-0-granular-decomposition-enables-accurate-estimates`: auditor independent enumeration may identify additional anchors (e.g., split A3 into "pipeline.py 14 sites" + "migration files 29 sites" + "core/db.py 1 site"). Auditor's lean requested for anchor count + decomposition shape.

### Q6 — `# WALLCLOCK:` annotation scope

Should the annotation be:
- **(a)** Inline at the offending line (`x = time.time()  # WALLCLOCK: DB write`)
- **(b)** On the line above as a separate comment line (`# WALLCLOCK: DB write\nx = time.time()`)
- **(c)** Either accepted by detector (P0.4 `# CLEANUP:` precedent allows both inline + above)

**Architect lean**: (c). Same flexibility as P0.4's `# CLEANUP:` discipline.

**Auditor adjudication requested**.

### Q7 — OPTIONAL-Plan-v2 path eligibility

If auditor returns Phase 0 with 0 PIs AND Plan v1 absorbs no PIs at auditor verdict, Bundle 3 ships 3-artifact (Phase 0 + Plan v1 + closure). **20th OPTIONAL-Plan-v2 proof case** could finally lock at Bundle 3 closure after 2 consecutive blocked Pre-P1 bundles (Bundle 1 + Bundle 2).

**Architect's read**: Bundle 3's scope is mechanical (assert→raise + deadline-math migration) — fewer architectural decision surfaces than Bundle 2's governance/SPDX work. OPTIONAL-Plan-v2 plausible IF Phase 0 + Plan v1 both clear cleanly. But Bundle 1+2 evidence suggests Phase 0 estimates may need multi-axis verification.

**Auditor adjudication requested**: conditional approval of OPTIONAL-Plan-v2 path subject to Plan v1 review outcomes.

### Q8 — Bundle 3.X (BUG-15) sequencing

File Bundle 3.X concurrent with Bundle 3 closure OR defer to separate cycle?

**Architect lean**: defer. BUG-15 fix (parse-from-filename) is mechanically distinct from monotonic migration. Bundling them would inflate Bundle 3 scope without clear closure-narrative cohesion.

**Auditor adjudication requested**.

---

## §6 Procedural commitments (Phase 0 → Plan v1 transition)

1. **Plan v1 §1 MUST locks exhaustive per-site classification** of all 233 `time.time()` sites (DEADLINE-MATH vs WALLCLOCK) + all 44 `assert` sites (in-scope vs out-of-scope per Q1+Q2 adjudications).
2. **Plan v1 §0 NEW commitment**: developer Pass-3 grep at Phase 4 pre-implementation MUST verify both file-count consistency AND semantic-correctness per migrated site (deadline-vs-wallclock semantic categorization; assert-vs-raise replacement preserves error message + exception class).
3. **Plan v1 §5.4 9-discipline preventive convergence enumeration** preserved + extended for Bundle 3 (Multi-discipline-preventive-convergence numbered doctrine carry-forward).
4. **3-part Pass-2 grep operational rule applied** at Plan v1 §1.* (symbol-name uniqueness + behavioral-semantic verification + symmetric verification reject/preserve classes — per P0.S10 Plan v4 + Bundle 2 Plan v3 license-precision dual-axis extension).
5. **Closure-audit verdict forwarding** to auditor before declaring Bundle 3 CLOSED (8th-cycle routinization).

---

## §7 Standing by for auditor Phase 0 verdict

Phase 0 grep-baseline locked. 233 `time.time()` + 44 `assert` site counts independently verified at architect Pass-1 grep 2026-05-28.

If auditor returns CLEAN (0 PIs): proceed to Plan v1 drafting with locked Q1-Q8 ratifications.

If auditor returns with PIs: Plan v1 absorbs at architect-side; auditor's Plan v1 review verdict drives Plan v2 path.

8 RATIFICATION QUESTIONS surfaced for explicit auditor adjudication (Q1-Q8). All have architect leans documented.

---

**Filed**: 2026-05-28
**Architect**: Claude
**Forwarded to**: Auditor (external)
**Predecessor**: Pre-P1 Bundle 2 CLOSED 2026-05-28 (5-artifact cycle ratified; 3 simultaneous sub-rule elevation events locked)
