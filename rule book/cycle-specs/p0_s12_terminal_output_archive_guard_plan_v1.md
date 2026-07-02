# P0.S12 Plan v1 — terminal_output.md PermissionError on multiprocessing.spawn re-import

**References:** `tests/p0_s10_s11_s12_canary_day1_bundle_audit.md` §3 (Phase 0).

**Canary source-of-truth:** `terminal_output_2026-05-27_115642.md` lines 37 + 42 + 47 + 60 + 120 (repeated PermissionError 13).

**Auditor standing offer:** Pass-2 grep verification + fresh Read on pipeline.py module-level side-effect surface area when forwarded. Architect-side Pass-2 grep performed BEFORE this Plan v1 drafting (§1 below); auditor's independent Pass-2 will provide convergence check per `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` doctrine.

**Cycle shape proposal:** OPTIONAL-Plan-v2 path (architect's lean — clean Plan v1, no precision items expected to surface). If auditor returns ≥1 PI, cycle escalates to 4-artifact (Phase 0 + v1 + v2 + closure).

---

## §1 Architect-side Pass-2 grep (scope widening)

**Phase 0 framing:** 1 site — `_archive_terminal_output()` call at `pipeline.py:81` is the bug surface. Estimated 5 anchors.

**Pass-2 grep finding (architect, this Plan v1):** the auditor's hint ("fresh Read on pipeline.py module-level side-effect surface area") was load-bearing. Re-reading `pipeline.py:1-220` surfaced **9 distinct module-level side-effect sites**, classified into 3 tiers by spawn-subprocess impact:

### §1.1 Tier 1 — SUBPROCESS-HARMFUL (must gate behind `__name__ == "__main__"`)

| Line(s) | Side effect | Why subprocess-harmful |
|---|---|---|
| `pipeline.py:81` | `_archived_log = _archive_terminal_output()` | Disk-rename op; subprocess attempts rename of file held by parent → Windows PermissionError 13. **The original canary bug.** |
| `pipeline.py:83-88` | `_LOG_FILE = open(_LOG_PATH, "w", ...)` | Mode `"w"` **TRUNCATES** existing file. Subprocess opening this competes with parent's open write-handle. On Windows the subprocess open may fail OR may grab a SEPARATE handle that silently corrupts parent's log stream. |
| `pipeline.py:182-183` | `_log_drain_thread = Thread(...).start()` | Starts a daemon thread in subprocess. Each subprocess gets its own drain thread that reads from a subprocess-local `_log_q` (line 165) — orphaned resource, no functional purpose in subprocess. |
| `pipeline.py:197-198` | `sys.stdout = _Tee(sys.stdout)` + `sys.stderr = _Tee(sys.stderr)` | Wraps subprocess's stdout/stderr in subprocess-local Tee. Tee writes route to subprocess's `_log_q` which is drained by subprocess's daemon thread → writes to subprocess's `_LOG_FILE` (which is the truncated/competing handle from row 2 above). Subprocess output never reaches parent's terminal_output.md anyway (multiprocessing.spawn inherits parent fd 1; subprocess prints land in terminal via OS-level fd inheritance, NOT via the Tee chain). |
| `pipeline.py:203-204` | `if _archived_log is not None: print(f"[Pipeline] Prior session log archived → {_archived_log.name}")` | Subprocess's archive attempt either succeeded (creating duplicate "Prior session log archived" log lines) or failed (already covered by Tier 1 row 1). In the canary log this didn't appear because subprocess's archive failed silently at the inner WARN. But the conditional print is still part of the same subprocess re-import cascade. |

**Pass-2 widening: 1 site → 5 distinct sites.** This is the `### Pre-audit-quantifier-precision-refined-by-grep` SCALE-OF-WORK-AXIS sub-shape — 9th instance of the doctrine if elevated at closure.

### §1.2 Tier 2 — SUBPROCESS-HARMLESS (keep unguarded)

| Line(s) | Side effect | Why safe in subprocess |
|---|---|---|
| `pipeline.py:18-19` | `sys.stdout.reconfigure(encoding='utf-8', errors='replace')` + `sys.stderr.reconfigure(...)` | Encoding reconfigure is idempotent. Subprocess inherits parent's already-reconfigured streams; reconfiguring again is no-op. Safe to leave at module level so subprocess output (when it bypasses Tee via fd inheritance) still uses UTF-8 encoding. |
| `pipeline.py:218+` (warnings filter block, Session 114) | `_w114.filterwarnings("ignore", message=...)` × N | Warnings module-level state; idempotent across subprocess imports. Subprocess that runs into the same deprecation warnings benefits from the filter. |

### §1.3 Tier 3 — STATE-ONLY (keep unguarded; subprocess gets fresh local copy)

| Line(s) | Side effect | Why safe in subprocess |
|---|---|---|
| `pipeline.py:165` | `_log_q: SimpleQueue = SimpleQueue()` | Module-level queue object. Subprocess gets its own empty queue per re-import. With Tier 1 row 3 gated, no thread drains subprocess's queue — it stays empty + idle. Acceptable resource footprint. |

### §1.4 Function definitions referencing `_LOG_FILE`

`pipeline.py:167-180` `_log_drain` function references `_LOG_FILE` at line 177. After D1 gates `_LOG_FILE` behind `__main__`, the function's reference resolves at CALL TIME (not def time). Since `_log_drain` is only INVOKED by the daemon thread (Tier 1 row 3, also gated), the function is never called in subprocess. `_LOG_FILE` global lookup at call time will resolve to the module-level placeholder (D2). No NameError surfaces.

---

## §2 D-decisions (LOCKED)

### D1 — Wrap Tier 1 side-effects in `if __name__ == "__main__":` block

**Edit site:** `pipeline.py` — restructure the boot-block sequence to gate 5 Tier 1 sites behind a single `__main__` guard.

**Pre-edit structure (current):**
```
Line  1-19:  imports + sys.stdout/stderr.reconfigure  [Tier 2 — UNCHANGED]
Line 21-31:  imports + _LOG_PATH
Line 34-78:  def _archive_terminal_output(...)  [def, no side effect]
Line  81:    _archived_log = _archive_terminal_output()  [Tier 1 — GATE]
Line 83-88:  _LOG_FILE = open(_LOG_PATH, "w", ...)  [Tier 1 — GATE]
Line 91-128: def _check_terminal_output_size_cap(...)  [def, no side effect]
Line 131-161: def _prune_old_terminal_archives(...)  [def, no side effect]
Line 165:    _log_q = SimpleQueue()  [Tier 3 — UNCHANGED]
Line 167-180: def _log_drain(...)  [def, no side effect — references _LOG_FILE at call time]
Line 182-183: _log_drain_thread = Thread(...).start()  [Tier 1 — GATE]
Line 185-195: class _Tee  [def, no side effect]
Line 197-198: sys.stdout = _Tee(sys.stdout) + sys.stderr = ...  [Tier 1 — GATE]
Line 203-204: if _archived_log is not None: print(...)  [Tier 1 — GATE]
Line 206+:   import time / uuid / warnings filter ...
```

**Post-edit structure (locked):**
```
Line  1-19:  imports + sys.stdout/stderr.reconfigure  [UNCHANGED]
Line 21-31:  imports + _LOG_PATH
Line 34-78:  def _archive_terminal_output(...)
Line  80-81: _archived_log: "_pathlib.Path | None" = None  ← D2 PLACEHOLDER
Line  82-83: _LOG_FILE: "Any" = None  ← D2 PLACEHOLDER
Line 86-128: def _check_terminal_output_size_cap(...)
Line 131-161: def _prune_old_terminal_archives(...)
Line 165:    _log_q = SimpleQueue()  [UNCHANGED]
Line 167-180: def _log_drain(...)  [UNCHANGED]
Line 182-194: class _Tee  [UNCHANGED — moved up so it's defined before the guard]
Line 196-218: ← D3 INLINE DOC BLOCK explaining the guard's purpose
Line 220:    if __name__ == "__main__":  ← GATE OPEN
Line 221:        _archived_log = _archive_terminal_output()
Line 223-228:    _LOG_FILE = open(_LOG_PATH, "w", encoding="utf-8", buffering=1)
Line 230-231:    _log_drain_thread = _log_thread_mod.Thread(target=_log_drain, daemon=True, name="log-writer")
Line 232:        _log_drain_thread.start()
Line 234-235:    sys.stdout = _Tee(sys.stdout)
Line 236:        sys.stderr = _Tee(sys.stderr)
Line 238-239:    if _archived_log is not None:
Line 240:            print(f"[Pipeline] Prior session log archived → {_archived_log.name}")
Line 242+:   import time / uuid / warnings filter ...  [Tier 2 + 3 — UNCHANGED]
```

**Critical preservation invariants:**
- `_log_q` (Tier 3) stays at module level so subprocess re-imports get a fresh local queue (harmless).
- `_log_drain` function definition stays at module level so the function exists as a callable in subprocess (never invoked there post-D1).
- `_Tee` class definition moves UP (above the guard) so it's defined before the guard accesses it.
- Tier 2 `sys.stdout/stderr.reconfigure` stays UNCHANGED at lines 18-19 (no gate).

### D2 — Module-level `None` placeholders for `_archived_log` + `_LOG_FILE`

**Edit site:** `pipeline.py` BEFORE the `__main__` guard.

```python
# D2 — Module-level placeholders so subprocess re-imports of pipeline.py
# get None-valued names rather than NameError on attribute access. The
# _log_drain function (defined below) references _LOG_FILE at CALL time
# (not def time), so the None value here is invisible — _log_drain is only
# ever invoked from the daemon thread which is only started in main.
_archived_log: "_pathlib.Path | None" = None
_LOG_FILE: "Any" = None  # opened by D1 main-only block; None in subprocess
```

Subprocess code that grep-references `pipeline._LOG_FILE` or `pipeline._archived_log` for any reason finds the names defined as None — no AttributeError, no behavioral surprise (subprocess shouldn't be doing this anyway; the placeholders are belt-and-braces).

### D3 — Inline doc block at the `__main__` guard

**Edit site:** `pipeline.py` IMMEDIATELY ABOVE the `if __name__ == "__main__":` line.

```python
# ─────────────────────────────────────────────────────────────────────────────
# P0.S12 — Module-level side-effect guard (Windows-spawn-mode safe boot block)
# ─────────────────────────────────────────────────────────────────────────────
#
# Canary 2026-05-27 (terminal_output_2026-05-27_115642.md lines 37/42/47/60/120)
# surfaced repeated `PermissionError 13` from _archive_terminal_output() firing
# in heavy-worker subprocess re-imports of this module.
#
# Root cause (P0.S12 Phase 0 §3.1, grep-verified): on Windows, multiprocessing
# uses `spawn` start-method which RE-IMPORTS the main module in every child
# process. Without this guard, module-level side-effects (archive rename, log
# file open, daemon thread start, Tee install, success-log print) fire in
# every child — corrupting the parent's terminal_output.md handle and emitting
# PermissionError noise on every spawn.
#
# This guard gates 5 Tier 1 sites (subprocess-harmful) behind `__main__`:
#   - _archive_terminal_output() call (the original PermissionError surface)
#   - _LOG_FILE = open(_LOG_PATH, "w", ...) (truncating-mode handle competition)
#   - _log_drain_thread.start() (orphan daemon in subprocess)
#   - sys.stdout = _Tee(sys.stdout) + sys.stderr = _Tee(sys.stderr) (subprocess-local Tee)
#   - "Prior session log archived" success print (subprocess-duplicate)
#
# Tier 2 side-effects (sys.stdout/stderr.reconfigure, warnings filter) stay
# UNGUARDED at module top — they're idempotent and subprocess inheritance
# benefits from them. Tier 3 (_log_q SimpleQueue) stays unguarded — subprocess
# gets its own empty queue, harmless.
#
# DO NOT move any Tier 2 / Tier 3 site inside this guard without rationale.
# DO NOT move any Tier 1 site outside this guard without re-evaluating
# subprocess re-import behavior on Windows. See test_p0_s12_*.py D4 anchors.
# ─────────────────────────────────────────────────────────────────────────────
```

### D4 — Test surface: `tests/test_p0_s12_terminal_output_archive_guard.py` NEW

6 anchors covering source-inspection of the guard structure + behavioral subprocess simulation:

| # | Type | Coverage |
|---|---|---|
| **A1** | Source-inspection | `if __name__ == "__main__":` block exists in pipeline.py AND contains all 5 Tier 1 site signatures (`_archive_terminal_output(` call, `_LOG_FILE = open(`, `_log_drain_thread.start()`, `sys.stdout = _Tee(`, `print(f"[Pipeline] Prior session log archived`) |
| **A2** | Source-inspection | Module-level `_LOG_FILE = None` placeholder exists BEFORE the `__main__` guard (D2 contract) |
| **A3** | Source-inspection | Inline doc block at the guard mentions all 4 anchors: `P0.S12`, `Windows-spawn-mode`, `terminal_output_2026-05-27`, 5-bullet Tier 1 enumeration (D3 contract) |
| **A4** | BEHAVIORAL — subprocess spawn re-import | Use `multiprocessing.get_context("spawn").Process(target=_subprocess_import_target)` where `_subprocess_import_target` does `import pipeline; assert pipeline._LOG_FILE is None; assert pipeline._archived_log is None`. Assert subprocess exits cleanly (exit code 0) with NO PermissionError raised. Parent's terminal_output.md handle stays valid (size unchanged). |
| **A5** | BEHAVIORAL — `_log_drain` function still importable | `from pipeline import _log_drain` succeeds in subprocess context (function defined at module level even when daemon thread not started). NameError on `_LOG_FILE` only fires if `_log_drain` is actually CALLED — which subprocess never does. |
| **A6** | AST forward-property tripwire | Walk pipeline.py AST; assert all 5 Tier 1 expression statements (Call of `_archive_terminal_output`, Assign of `_LOG_FILE = open(...)`, Call of `_log_drain_thread.start`, Assign of `sys.stdout = _Tee(...)`, conditional print) live as descendants of the `if __name__ == "__main__":` If node — NOT at module top level. Catches future refactors that accidentally move a Tier 1 site back outside the guard. |

---

## §3 Anchor count LOCK

**Plan v1 LOCK: 6 anchors** at exact mid 6, inclusive ±15% band [5.1, 6.9].

**Auditor Q5 deviation from Phase 0:** Phase 0 mid was 5. Plan v1 widens to 6 (+20% from Phase 0 mid) per Pass-2 grep refinement — 1 archive call → 5 Tier 1 sites + 1 AST forward-property tripwire (A6, architect's defensive addition).

**Q5 closure projection:**
- Closure-actual = 6 → 0% drift vs Plan v1 LOCK → ON-TARGET exact-mid; would extend `Doctrine-prediction-precision-improving-over-arc` sub-rule 7-consecutive-0%-streak (currently at 6 instances post-P0.R12-R15)
- Closure-actual = 5 → −16.7% vs Plan v1 LOCK → SLIGHT-DRIFT-DOWN band (>15%); doctrine HOLDS within ±30%; streak BREAKS
- Closure-actual = 7 → +16.7% vs Plan v1 LOCK → SLIGHT-DRIFT-UP band; same disposition

Per `Explicit-closure-honest-count-commitment` discipline: this Plan v1 §3 commitment locked at 6; closure narrative will report closure-actual honestly regardless of streak implications.

---

## §4 Pre-mortem (3 ways this fix could fail)

1. **Test imports of pipeline break because `_LOG_FILE` is `None`.**
   - Risk: existing tests that mock or directly reference `pipeline._LOG_FILE` get a None instead of a file object.
   - Grep verification (architect Pass-2): search `pipeline._LOG_FILE` + `from pipeline import _LOG_FILE` references across `tests/`. Pending Pass-2 result.
   - Mitigation: D2 placeholder ensures the name exists (no AttributeError). Tests that need a real file handle must use a fixture that monkeypatches `pipeline._LOG_FILE = io.StringIO()` or similar. If existing tests break, fix at Phase 4 + flag in closure narrative as A6-adjacent ripple.

2. **Subprocess loses stdout forwarding because subprocess-local Tee isn't installed.**
   - Risk: subprocess `print()` calls don't appear in parent's terminal_output.md.
   - Investigation (architect's read): subprocess `print()` writes to fd 1 (inherited from parent). The parent's terminal capture happens at the OS level (terminal scrollback OR the parent's Tee for parent-process writes ONLY). Subprocess stdout reaching parent's terminal is via INHERITED fd 1, NOT via the Tee chain. Heavy-worker subprocesses don't currently call print() except for their own error logs (which print to fd 2/fd 1 directly). **No regression expected.**
   - Mitigation: A4 + A5 subprocess simulation verifies subprocess can complete its target function without depending on local Tee/log-file. If a regression surfaces (e.g. heavy-worker prints get lost), file as P0.S12.X follow-up — NOT in scope for P0.S12 itself.

3. **Future maintainer moves a Tier 2 site (e.g. warnings filter) inside the guard, breaking subprocess functionality.**
   - Risk: warnings filter inside `__main__` block means subprocess doesn't suppress the SpeechBrain deprecation warning, generating log noise on every face-recognition turn.
   - Mitigation: D3 inline doc explicitly classifies Tier 1 / Tier 2 / Tier 3 + names DO-NOT-MOVE rules. A3 anchor enforces doc presence. A6 AST tripwire catches Tier 1 sites moving OUT of the guard (the inverse direction).

---

## §5 Multi-direction invariant trace

**Forward (main-process boot):**
```
python pipeline.py
  → __name__ == "__main__"
  → Tier 1 sites fire (parent only):
      _archive_terminal_output() rename succeeds (no contention)
      _LOG_FILE = open(..., "w", ...) gets fresh handle
      _log_drain_thread starts
      sys.stdout = _Tee(...) installs
      "Prior session log archived" prints
  → main loop proceeds normally
  → heavy-worker subprocesses spawn → spawn-mode re-imports pipeline.py
      → __name__ != "__main__" in child (it's "__mp_main__" on Windows-spawn)
      → Tier 1 sites SKIPPED
      → _archived_log + _LOG_FILE remain None (D2 placeholders)
      → no PermissionError, no Tee install, no duplicate daemon
  → subprocess executes target function (face embed / STT / etc.)
  → result returned to parent via mp queue
  → parent logs via its own Tee normally
```

**Reverse (subprocess crash recovery):**
- Subprocess raises BrokenProcessPool → parent's `run_heavy` catches → records via `_record_pool_crash` (P0.R8) → persist_crash_diagnostic (P0.R11) → bare `raise` → caller-side fallback (P0.R1 D1 None-return contract). NONE of this path touches `_LOG_FILE`, `_archived_log`, or the Tee. No interaction with P0.S12.

**Cross-spec:**
- **P1.5 (Session 81 archive hook origin):** same architect. P0.S12 corrects the spawn-mode interaction Session 81 didn't anticipate. The archive's PURPOSE (preserve session boundaries for golden-intent harvest) is unchanged — it just fires only in main now.
- **P0.R6 + R6.X/Y/Z (heavy-worker pools):** they're the TRIGGER (introduced spawn-mode at scale). P0.S12 accommodates without changing their architecture. Verify by running `pytest tests/test_p0_r6_*.py tests/test_p0_r6_x_*.py tests/test_p0_r6_y_*.py tests/test_p0_r6_z_*.py` after implementation — should stay green.
- **P0.R13 D2 (terminal_output size-cap rotation):** the size-cap helper at `pipeline.py:91-128` calls `_archive_terminal_output(log_path)` at line 118. The helper is ONLY called from the dream-loop (`pipeline.py:3626-3627`) which runs IN THE MAIN PROCESS event loop — never from subprocess. Size-cap rotation path stays unchanged + safe.
- **P0.R11 D4 (crash log retention prune from dream-loop):** dream-loop runs in main only — no interaction.

---

## §6 11-gate quality checklist

Per `feedback_strict_industry_standard_mode.md` §1:

| # | Gate | Status |
|---|---|---|
| 1 | Pre-mortem written (3 failure modes) | ✅ §4 |
| 2 | Multi-direction invariant trace (forward + reverse + cross-spec) | ✅ §5 |
| 3 | Pass-1 grep verified (Phase 0 §3.1) | ✅ |
| 4 | Pass-2 grep verified (architect-side widening; auditor-side pending) | ✅ §1 |
| 5 | Honest Q5 closure projection (§3 deviation banked) | ✅ §3 |
| 6 | Cross-spec impact analyzed (4 specs cross-referenced) | ✅ §5 |
| 7 | Closure-audit scheduled (§7 commitment) | ✅ §7 |
| 8 | Doctrine firings catalogued (§9) | ✅ §9 |
| 9 | Open questions surface with architect's leans (§8 — 4 questions) | ✅ §8 |
| 10 | 11-gate self-audit documented (this section) | ✅ §6 |
| 11 | Architect closure-audit verdict forwarding committed (§7) | ✅ §7 |

---

## §7 Closure-audit commitment

Per `### Architect-reads-production-code-before-sign-off` + `feedback_closure_audit_verdict_cycle_elision.md` (RATIFIED at P0.R12-R15 2nd cycle):

**At Phase 4 completion (developer side), architect performs closure-audit:**

1. **Grep-verify D1 contract** — `grep -n 'if __name__ == "__main__":' pipeline.py` returns the expected guard line; visual scan confirms all 5 Tier 1 sites moved inside; A6 AST tripwire passes
2. **Grep-verify D2 placeholders** — `grep -n '_LOG_FILE: .*= None' pipeline.py` returns the placeholder assignment BEFORE the guard
3. **Grep-verify D3 doc block** — `grep -n 'P0.S12' pipeline.py` returns the inline doc anchor; visual scan confirms the 5-bullet Tier 1 enumeration + DO-NOT-MOVE rules
4. **Run D4 test suite** — `pytest tests/test_p0_s12_terminal_output_archive_guard.py -v` reports all 6 anchors passing
5. **Run deliberate-regression cycle** — temporarily MOVE one Tier 1 site (e.g. the archive call) OUT of the guard → confirm A1 + A4 + A6 fire → revert → confirm tests pass again. Bank as 9th `### Induction-surfaces-invariant-gaps` instance if regression confirms gap.
6. **Run cumulative suite** — `pytest --tb=no -q` reports 2766 passed + 14 skipped + 9 xfailed (2760 baseline + 6 new P0.S12 anchors); no regressions in P0.R6 + R6.X/Y/Z + P0.R8 + P0.R11 subprocess paths
7. **Forward closure-audit verdict to auditor** for ratification BEFORE declaring P0.S12 CLOSED — 3rd cycle routinization of closure-audit verdict forwarding discipline

---

## §8 Open questions for auditor (4 questions; architect's lean per each)

### Q1 — D4 Anchor 4 subprocess simulation: real spawn vs monkeypatch fixture?

- **(a)** Real subprocess via `multiprocessing.get_context("spawn").Process(target=_subprocess_import_target)`. Realistic; slow (~3-5s in CI for one subprocess spin-up).
- **(b)** Monkeypatch `__name__ == "__main__"` to False in a test fixture + re-execute module body. Fast (~50ms); less realistic (doesn't actually simulate spawn-mode re-import).
- **(c)** Both — A4 = real spawn (slow), A4-alt = monkeypatch (fast). Cumulative anchor count = 7 if both kept.

**Architect's lean: (a).** Slow subprocess test is acceptable cost for the load-bearing behavioral validation. P0.S12 is a Windows-spawn-mode bug; the test should EXERCISE that exact mechanism. Run-time impact: +5s in CI; cumulative suite stays well under any timeout.

### Q2 — Tier 2 boundary: should `sys.stdout/stderr.reconfigure` ALSO gate?

- Architect-side reasoning (§1.2): subprocess inherits parent's already-reconfigured streams; reconfiguring again is no-op on Python's stdio.
- **Counter-argument:** in spawn-mode, subprocess re-creates fd 1/2 — they're FRESH file descriptors with default encoding (cp1252 on Windows). Reconfiguring to UTF-8 in subprocess is the SAME fix the parent applied; it's needed.
- **Architect's lean: keep Tier 2 (unguarded).** Subprocess fd 1 needs UTF-8 reconfigure too (for any subprocess print output that lands in parent terminal via inheritance). Removing the reconfigure from subprocess would break Unicode handling in subprocess prints. Tier 2 classification stands.

### Q3 — `_log_drain` function — explicit guard against subprocess invocation?

- Current design (post-D1): `_log_drain` is defined at module level but never CALLED in subprocess (daemon thread not started in subprocess per Tier 1 row 3).
- **Counter-argument:** if any future code accidentally calls `_log_drain()` directly from subprocess (e.g. a misguided refactor), the function would NameError on `_LOG_FILE` → silent daemon crash.
- **Architect's lean: defer.** A5 anchor verifies the function is importable; no current caller invokes it from subprocess. Adding explicit `if _LOG_FILE is None: return` at function entry adds dead-code complexity for a theoretical regression. Bank as known limitation; revisit if a real subprocess-side invocation surfaces.

### Q4 — Doctrine firings to bank at Plan v1?

- **`### Pre-audit-quantifier-precision-refined-by-grep` — 8 → 9 (NEW SCALE-OF-WORK-AXIS instance).** Phase 0 estimated "1 archive call surface"; Plan v1 grep refined to "5 distinct Tier 1 sites + 4 Tier 2/3 sites classified." Architect's lean: bank at Plan v1 review (per locked precedent of similar SCALE-OF-WORK-AXIS instances).
- **`### Architect-reads-production-code-before-sign-off` — 27 → 28 at Plan v1 review.** Grep-verified the surface area widening (not pre-audit framing). Architect's lean: bank.
- **`### Pass-2-grep-auditor-verified-before-Plan-v1-approval` — 7 → 8 (8th application).** Architect did Pass-2 grep at Plan v1 drafting; auditor's standing-offer Pass-2 makes this the 8th application. Architect's lean: bank one count; auditor's Pass-2 either CONVERGES (clean count) or surfaces a real gap (caught-real-gap count — would be the 2nd caught-real-gap of the doctrine after P0.R4).
- **`### Phase-0-granular-decomposition-enables-accurate-estimates` watch criterion:** Q5 closure with 6 anchors vs Plan v1 LOCK 6 → 0% drift expected; would extend 6-consecutive-0%-streak to 7 cycles. Architect's lean: bank if closure-actual confirms.

---

## §9 Doctrine track-record update commitments (at P0.S12 closure)

If/when P0.S12 closes:

| Doctrine | Pre-P0.S12 | Post-P0.S12 (projected) |
|---|---|---|
| `### Architect-reads-production-code-before-sign-off` | 27 | 28 |
| `### Phase-0-granular-decomposition-enables-accurate-estimates` (if 0% Q5) | 27 supporting | 28 supporting |
| `Doctrine-prediction-precision-improving-over-arc` sub-rule (if 0% Q5) | 6 consecutive 0%-streak | 7 consecutive 0%-streak |
| `### Pre-audit-quantifier-precision-refined-by-grep` | 8 | 9 (NEW SCALE-OF-WORK-AXIS) |
| `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` | 7 | 8 |
| `### Zero-precision-items-at-auditor-review` | 18 instances | 20 if both Phase 0 + Plan v1 + Plan-v2-skip (OPTIONAL path) clear cleanly |
| OPTIONAL-Plan-v2 sub-rule track record | 16 proof cases | 17 if Plan v1 clears cleanly |
| Closure-audit verdict forwarding routinization | 2 cycles | 3 cycles |
| `Explicit-closure-honest-count-commitment` | 23 | 24 (Plan v1 §3 = MADE; closure = HONORED — 2 instance increments) → 25 |

---

## §10 Cumulative suite impact

- **Baseline:** 2760 passed + 14 skipped + 9 xfailed (per CLAUDE.md header)
- **P0.S12 anchors:** +6 (D4 A1-A6)
- **Projected post-P0.S12:** 2766 passed + 14 skipped + 9 xfailed
- **No retirements expected** — D4 anchors are all NEW; no existing tests touched by D1/D2/D3 directly. Pre-mortem #1 flagged risk of test breakage if `_LOG_FILE` references exist in tests — that's a Phase 4 in-flight issue, banked as ripple-fix at closure if surfaces.

---

## §11 Cycle shape recommendation

**Architect's lean: OPTIONAL-Plan-v2 path** (3-artifact cycle: Phase 0 + Plan v1 + closure).

Rationale: Plan v1 is comprehensive (Pass-2 grep widened scope BEFORE auditor review; pre-mortem covers known risks; cross-spec impact analyzed; D-decisions locked precisely). No precision items anticipated to surface at auditor's review. If auditor returns 0 PIs → ship straight to developer.

If auditor returns ≥1 PI: cycle escalates to 4-artifact (Phase 0 + v1 + v2 + closure). Common escalation triggers from prior cycles: ENUMERATION-DRIFT (Pass-2 enumeration missed a site), CODE-TEMPLATE-MISIDENTIFICATION (architect copied a template that diverges from canonical surface), LINE-REF-DRIFT (line numbers in Plan v1 don't match current production code).

---

## §12 Ready for auditor

Plan v1 forwarded for:
1. Pass-2 grep convergence check (auditor's standing offer)
2. Q5 estimate calibration (auditor's mid vs architect's LOCK 6)
3. Q1-Q4 open question adjudication
4. Doctrine firings ratification at this Plan v1 review

Architect commits to Plan v2 within ~2 hours of auditor's verdict if any precision items surface. Otherwise: hand off to developer Phase 4 implementation.