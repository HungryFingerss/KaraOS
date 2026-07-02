# Pre-P1 Bundle 4 — Observability+Concurrency (MF6 + MF9) Plan v1 (2026-05-28)

**Cycle**: Pre-P1 must-fix Bundle 4 (Observability+Concurrency)
**Predecessor**: `tests/pre_p1_bundle4_observability_concurrency_audit.md` (Phase 0 ACCEPT WITH 1 PI at auditor verdict 2026-05-28; Q1-Q8 RATIFICATIONS in architect's favor; Q5 CONDITIONAL on Plan v1 cleanliness)
**Discipline**: Strict-mode; **stakes ELEVATED** — Plan v1 outcome adjudicates 20th OPTIONAL-Plan-v2 proof case LOCK vs Multi-axis-precision-pattern SUB-RULE ELEVATION EVENT
**Architect**: Claude
**Auditor**: External (Phase 0 verdict in `info.md` 2026-05-28)

---

## §0 Procedural commitments

All 13 Phase 0 §0 commitments PRESERVED verbatim. NEW for Plan v1:

### §0 NEW commitment — PI #1 absorbed via grep-verified BEFORE-code refresh

Per auditor §2 PI #1 + §6 NEW commitment: Plan v1 §2 D1 BEFORE-code MUST match actual production at pipeline.py:171-184 via fresh-disk Read at drafting time. **Architect executed fresh Read at Plan v1 drafting 2026-05-28** — grep-verified actual production text now embedded verbatim at §2 D1 below.

**Doctrine bumps locked at Phase 0 verdict** (auditor §4):
- `Per-artifact-arithmetic-drift-survives-grep-baseline` 18 → 19 (PI #1 structural drift sub-shape candidate)
- NEW `Phase-0-spec-text-BEFORE-code-doesnt-match-production` 1st instance (sub-shape under parent doctrine; 3-instance threshold)
- `Multi-axis-precision-pattern-confirmed-by-3-consecutive-blocked-bundles` 1 → 2 instances (Bundle 4 Phase 0 surfaces PI; sub-rule elevation candidacy STRENGTHENS approaching 3-instance threshold)
- `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` 11 → 12 (CAUGHT-REAL-GAP event — Phase 0 §2 D1 BEFORE-code drift)
- Strict-mode 123 → 124, spec-first 132 → 133, Grep-baseline 90 → 91, Cross-cycle 93 → 94, Spec-time grep 100 → 101
- `### Twin-filename-pitfall-prevention` 34 → 35 preventive

### §0 architect "HIGH with strengthened reservation" confidence framing

Per Bundle 3 carry-forward + Q5 CONDITIONAL ratification: Plan v1 confidence is HIGH for the mechanical surfaces (D4 + D5 file-scoped invariants) but explicit acknowledgment of `Zero-precision-items-pre-closure-predictions-blocked` 6-instance prior history. Plan v1 absorbs PI #1 cleanly; if Plan v1 review surfaces NEW PIs, Plan v2 absorbs + Multi-axis-precision-pattern 3rd instance LOCKS sub-rule elevation.

---

## §1 PI #1 absorption + §2 D1 BEFORE-code refresh (grep-verified)

### §1.1 Actual production code at pipeline.py:171-184 (fresh-disk Read 2026-05-28)

```python
def _log_drain() -> None:
    """Daemon thread — writes queued log messages to terminal + log file."""
    while True:
        stream, data = _log_q.get()
        try:
            stream.write(data)
            stream.flush()
        except Exception:
            pass  # OPTIONAL: raising kills the daemon and silences all subsequent logging
        try:
            _LOG_FILE.write(data)
            _LOG_FILE.flush()
        except Exception:
            pass  # OPTIONAL: raising kills the daemon and silences all subsequent logging
```

Function body = 12 lines (def line 171 + docstring 172 + body 173-184). BOTH inner try/except wraps present per P0.4 annotation discipline. NO `if _LOG_FILE:` guard in production (Phase 0 §2 D1 fabricated). Function comments are `# OPTIONAL: raising kills the daemon and silences all subsequent logging` (P0.4-annotated swallow sites).

### §1.2 §2 D1 AFTER-code (architectural design preserved verbatim per auditor §2)

```python
# NEW module-level observability state (added near line 169 _log_q declaration)
_log_drain_count: int = 0  # observability counter — successful drains
_log_drain_last_at: float = 0.0  # WALLCLOCK: observability — last successful drain timestamp
_log_drain_error_count: int = 0  # observability counter — exception count

def _log_drain() -> None:
    """Daemon thread — writes queued log messages to terminal + log file.

    P0.B4 D1 (Bundle 4 observability) — outer-loop try/except catches:
      - _log_q.get() failures (the load-bearing silent-death failure mode per Skeptic-1 BUG-3)
      - _log_drain_count / _log_drain_last_at counter update failures (exotic)
      - any unforeseen exception sites
    Inner try/except blocks (stream.write + _LOG_FILE.write) preserved per P0.4 discipline.
    """
    global _log_drain_count, _log_drain_last_at, _log_drain_error_count
    while True:
        try:
            stream, data = _log_q.get()
            try:
                stream.write(data)
                stream.flush()
            except Exception:
                pass  # OPTIONAL: raising kills the daemon and silences all subsequent logging
            try:
                _LOG_FILE.write(data)
                _LOG_FILE.flush()
            except Exception:
                pass  # OPTIONAL: raising kills the daemon and silences all subsequent logging
            _log_drain_count += 1
            _log_drain_last_at = time.time()  # WALLCLOCK: observability timestamp
        except Exception as e:
            # P0.B4 D1 outer-loop wrap: DO NOT swallow silently. Emit to stderr directly
            # (bypassing _Tee which routes through _log_q — would create an infinite loop).
            _log_drain_error_count += 1
            import sys as _sys
            try:
                _sys.__stderr__.write(f"[Log] _log_drain exception: {type(e).__name__}: {e}\n")
                _sys.__stderr__.flush()
            except Exception:
                pass  # OPTIONAL: stderr unavailable; nothing more we can do
            # Continue the loop — drain thread stays alive
```

**Critical invariants preserved**:
- Producer-side `_log_q.put()` in `_Tee.write` keeps blocking-free semantics (out-of-scope; unchanged)
- BOTH inner try/except wraps preserved exactly (stream.write + `_LOG_FILE.write`) per P0.4 discipline
- P0.4-annotated `# OPTIONAL:` comments preserved verbatim
- Outer-loop wrap catches: `_log_q.get()` failures (load-bearing) + counter updates + exotic failures
- `_sys.__stderr__` direct bypass prevents `_Tee` infinite loop on stderr write
- Counter + timestamp accessible from `core/health.py` for D2 liveness check

### §1.3 PI #1 absorption summary

**Architect's Phase 0 §2 D1 BEFORE-code drift** (4 discrepancies vs production):
1. OMITTED second inner try/except wrap on `_LOG_FILE.write` (lines 180-184)
2. ADDED fabricated `if _LOG_FILE:` guard not in production
3. OMITTED docstring at line 172
4. Comment text mismatch (`# producer keeps going` vs production's P0.4-annotated `# OPTIONAL: raising kills the daemon and silences all subsequent logging`)

**Substantive impact (per auditor §2)**: D1's load-bearing fix (outer-loop wrap) is STILL CORRECT — actual silent-death failure mode is at `_log_q.get()` (line 174 unguarded), not at file-writes (both already inner-wrapped). Architectural design unchanged.

**Absorption locked at Plan v1 §1.1 + §1.2 above**. PI #1 closed cleanly with grep-verified BEFORE-code text + AFTER-code preserved verbatim from Phase 0.

---

## §2 D-decisions refined (Q1-Q8 ratifications applied)

### D1 — MF6 `_log_drain` outer-loop try/except + observability counter (PI #1 absorbed)

Per §1.2 above. Q1 (a) RATIFIED outer-loop wrap scope.

**Scope**: pipeline.py:171-184 (function body refactor) + 3 NEW module-level observability vars near line 169.

**Critical preservation**: BOTH inner try/except wraps stay; P0.4 annotations preserved verbatim; comments preserved.

### D2 — MF6 `HealthSnapshot` log-drain liveness field + actionable alert

Per Phase 0 §2 D2. Q7 RATIFIED `LOG_DRAIN_STALENESS_SECS=60.0` + Q8 RATIFIED separate success+error counters.

**Scope**: `core/health.py` + `core/config.py`. NEW fields on `HealthSnapshot`:
- `log_drain_alive: bool = True`
- `log_drain_count: int = 0`
- `log_drain_error_count: int = 0`

`gather_health_snapshot()` populates via `pipeline._log_drain_thread.is_alive()` AND `time.time() - pipeline._log_drain_last_at < LOG_DRAIN_STALENESS_SECS`. `format_health_line` conditional emit `log_drain=DEAD` when not alive AND `log_drain_errors=N` when error_count > 0.

`format_health_alerts` actionable recovery alert with 5 verbatim substrings:
1. `"Log drain thread degraded"`
2. `"check pipeline restart"`
3. `"messages drained:"` (numeric N follows)
4. `"errors:"` (numeric M follows)
5. `"LOG_DRAIN_STALENESS_SECS"`

NEW `core/config.py` constant: `LOG_DRAIN_STALENESS_SECS: float = 60.0`.

### D3 — MF6 AST invariant: `_log_drain` body has try/except + non-swallow stderr emit

Per Phase 0 §2 D3. Single-function scope (NOT file-wide; Bundle 4 sub-shape distinct from Bundle 3 STANDARD scope).

**New test file**: `tests/test_log_drain_observability_invariant.py`

**Detector logic**:
- AST-walks `pipeline.py`; locates `_log_drain` `ast.FunctionDef` by name
- Asserts outer `while True:` body wraps in `ast.Try` with at least one `ast.ExceptHandler`
- Asserts except handler body does NOT contain `ast.Pass` as sole body element (non-swallow contract)
- Asserts except handler body contains substring match for `_sys.__stderr__` OR equivalent stderr-emit pattern
- Self-tests: forward (synthetic violation where except body is just `pass` fires) + inverse (correct shape passes)

### D4 — MF9 `_persistent` lock extension to `**_persistent` SPREAD read

Per Phase 0 §2 D4. Q2 (a) RATIFIED lock-around-shallow-copy-only granularity.

**Scope**: `core/state.py:65` (single-line edit + 4-line lock-snapshot block before line 55 state-dict construction).

```python
def write(...):
    # P0.B4 D4 (Bundle 4 observability+concurrency) — extends P0.B5 D4 writer-side lock
    # to the read-side spread for GIL-free Python 3.13+ --disable-gil forward-compat.
    # Lock held ONLY for shallow dict() copy; released BEFORE the file I/O to avoid
    # contention with concurrent set_persistent writers.
    with _persistent_lock:
        _persistent_snapshot = dict(_persistent)
    state = {
        "status":            status,
        ...
        "online":            True,
        **_persistent_snapshot,
    }
    # ... atomic file write unchanged ...
```

### D5 — MF9 AST invariant: `_persistent` accessed only under lock

Per Phase 0 §2 D5. Q3 RATIFIED production-scope `core/state.py` only + test-files unrestricted.

**New test file**: `tests/test_persistent_lock_invariant.py`

**Detector logic**:
- AST-walks `core/state.py`; locates every `ast.Name(id='_persistent', ctx=Load|Store)` AND `ast.keyword(arg=None, value=ast.Name(id='_persistent'))` (DictUnpacking via `**_persistent`)
- Asserts each occurrence's enclosing scope is one of:
  - Module-level declaration (line 18 only)
  - Inside `ast.With` block whose `withitem.context_expr` is `_persistent_lock`
  - Inside function body where the lock is acquired in same scope
- Allowlist path-based: production scope = `core/state.py` only; test files unrestricted
- Self-tests: forward (synthetic unguarded read in production scope fires) + inverse (under-lock read passes)

---

## §3 Q5 LOCK at mid 5 + closure-projection band table (Q4 RATIFIED)

UNCHANGED from Phase 0 §3.

NARROW band [4.25, 5.75]. Falsification: ≤3 OR ≥8.

### §3.1 Anchor breakdown finalized

| # | Anchor | Type | Parametrize fan-out projection |
|---|---|---|---|
| A1 | D1 `_log_drain` body refactor + observability state | source-inspection on pipeline.py `_log_drain` + 3 module-level var declarations | 1 |
| A2 | D2 `HealthSnapshot` log-drain field + format_health_alerts | source-inspection: 3 new fields + 5 alert substrings + 1 config constant | ~9 |
| A3 | D3 AST invariant single-function `_log_drain` try/except non-swallow | structural AST scan + 2 self-tests (forward + inverse) | ~3 |
| A4 | D4 `**_persistent` read-side lock + snapshot pattern | source-inspection on core/state.py:65 lock-snapshot block | 1 |
| A5 | D5 AST invariant file-scoped `_persistent` accessed-only-under-lock | structural AST scan + 2 self-tests | ~3 |

**Total = 5 logical anchors. NARROW band [4.25, 5.75]. Q5 LOCK = 5.**

**A1+A2+A3+A4+A5 parametrize fan-out: ~17 collections** (Plan v1 §3 projection per Bundle 3 Q4 ratification lesson — explicitly accounting for AST invariant fan-out across scope). Much smaller than Bundle 3's 185 because Bundle 4 invariants are scoped to single-function (D3) + single-file (D5), NOT STANDARD scope.

### §3.2 Closure-projection band table

| Closure-actual | % vs mid | Reading | Doctrine consequence |
|---|---|---|---|
| 3 anchors | -40% | FALSIFICATION TRIGGER | falsification IF wrong-premise root cause |
| 4 anchors | -20% | SLIGHT-DRIFT-DOWN within ±30%; doctrine holds | doctrine HOLDS at 33; streak interrupted |
| **5 anchors (Q5 LOCK)** | **0%** | exact mid | doctrine bumps 33 → 34; **13th consecutive 0%-streak rebuild** (P0.S10 9th + Bundle 1 10th + Bundle 2 11th + Bundle 3 12th + Bundle 4 13th) |
| 6 anchors | +20% | SLIGHT-DRIFT-UP within ±30%; doctrine holds | doctrine HOLDS at 33; streak interrupted |
| 7 anchors | +40% | FALSIFICATION TRIGGER | falsification IF wrong-premise root cause |
| ≤2 OR ≥8 | ≥±50% | FALSIFICATION + emergency review | falsification + same-cycle Plan v2 absorption |

---

## §4 Cross-spec impact

### §4.1 File-impact table (Phase 0 estimate preserved + 4-part Pass-2 grep arithmetic verification)

| D | New files | Modified files | Approx scope |
|---|---|---|---|
| D1 | — | `pipeline.py` (3 module-level vars near line 169 + `_log_drain` body refactor lines 171-184) | ~30 line-level edits |
| D2 | — | `core/health.py` (3 new HealthSnapshot fields + gather_health_snapshot wiring + format_health_line conditional emit + format_health_alerts with 5 verbatim substrings) + `core/config.py` (1 new constant) | ~35 line-level edits across 2 files |
| D3 | `tests/test_log_drain_observability_invariant.py` (NEW) | None | 1 new test file + ~50 LOC AST detector + self-tests |
| D4 | — | `core/state.py:65` (4-line lock-snapshot block + single-line spread update) | ~5 line-level edits |
| D5 | `tests/test_persistent_lock_invariant.py` (NEW) | None | 1 new test file + ~50 LOC AST detector + self-tests |

**Total scope (Plan v1 ARITHMETIC SUM-AGAINST-TOTAL verified per Bundle 3 4-part Pass-2 grep rule)**:
- New files: 2 (test files)
- Modified files: 4 (`pipeline.py` + `core/health.py` + `core/config.py` + `core/state.py`)
- Line-level edits: 30 (D1) + 35 (D2) + 5 (D4) = **70 line-level production-code edits**
- Test files: 100 LOC AST detectors + self-tests total

**Pass-2 arithmetic sum-against-total verified**: 2 new + 4 modified = 6 file events; 70 line-level edits; 100 LOC test-file additions.

### §4.2 No further git ripple

No `.gitignore` changes. No LICENSE/governance file changes. Bundle 4 is pure code-correctness work.

### §4.3 Bundle 4.X (`logging` framework migration) DEFERRED per Q6 RATIFIED

Filed at architect-memory; user-trigger gated.

### §4.4 Bundle 5 unchanged dependency

Bundle 5 (Contract typing MF7+MF8) code-only with no dependency on Bundle 4.

---

## §5 Discipline counts + Multi-discipline preventive convergence enumeration

### §5.1 Per-artifact-driven disciplines (3-artifact OPTIONAL-Plan-v2 cycle per Q5 conditional approval)

Locked +1-per-artifact convention applied:

| Discipline | Pre-Bundle-4 | Phase 0 | **Plan v1** | Closure |
|---|---|---|---|---|
| Strict-industry-standard mode applications | 123 | 124 | **125** | 126 |
| Spec-first review cycle | 132 | 133 | **134** | 135 |
| `### Grep-baseline-before-drafting` | 90 | 91 | **92** | 93 |
| Cross-cycle-handoff transparency | 93 | 94 | **95** | 96 |
| Spec-time grep-verification | 100 | 101 | **102** | 103 |

### §5.2 Closure-event disciplines (single +1 at closure)

| Discipline | Pre-Bundle-4 | After closure |
|---|---|---|
| Strict-industry-standard mode closures | 35 | 36 |
| `### Twin-filename-pitfall-prevention` | 34 | 35 (Phase 0 +1 already banked at Phase 0 verdict) |
| `### Architect-reads-production-code-before-sign-off` | 33 | 34 (closure-audit event) |
| Auditor-Q5-estimates-trail-grep | 39 | 40 banked closures (if Q5 within NARROW band) |
| Deferred-canary strategy | 37 | 38 applications |

### §5.3 NEW doctrine instances banked at closure

| Discipline | Pre-Bundle-4 | After Phase 0 | After closure | Cycle event |
|---|---|---|---|---|
| `Per-artifact-arithmetic-drift-survives-grep-baseline` | 18 | **19 (Phase 0 PI #1)** | 19 | Structural BEFORE-code drift; sub-shape candidate |
| NEW `Phase-0-spec-text-BEFORE-code-doesnt-match-production` | 0 | **+1 (Phase 0)** | 1 | 1st instance; 3-instance threshold for sub-rule formalization under `Per-artifact-arithmetic-drift-survives-grep-baseline` parent doctrine |
| `Multi-axis-precision-pattern-confirmed-by-3-consecutive-blocked-bundles` | 1 (Bundle 3) | **2** (Phase 0 PI #1) | 2 or 3 (CONDITIONAL on Plan v1 outcome) | Bundle 4 Phase 0 surfaces PI; pattern continues across 4th consecutive Pre-P1 bundle |
| `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` | 11 | **12 (CAUGHT-REAL-GAP)** | 12 | Auditor Phase 0 verdict caught architect's BEFORE-code drift via independent grep |
| OPTIONAL-Plan-v2 sub-rule track record | 19 | 19 (CONDITIONAL on Plan v1) | **CONDITIONAL** | 20 LOCKS if Plan v1 clears 0 PIs; STAYS at 19 if Plan v1 surfaces PIs |
| `Doctrine-prediction-precision-improving-over-arc` 0%-streak | 12 consecutive (Bundle 3 = 5 exact) | TBD | **13 IF closure-actual = 5 exact** | Conditional on closure-actual = 5 |
| `### Phase-0-granular-decomposition-enables-accurate-estimates` | 33 supporting | TBD | **34 (if within NARROW band [4.25, 5.75])** | Conditional |
| `### Phase-0-catches-wrong-premise` | 13 | **STAYS 13** | 13 | Bundle 4 PI #1 was representational drift NOT wrong-premise; premise was ON-TARGET |

### §5.4 Multi-discipline preventive convergence enumeration — Bundle 4

Per elevated `### Multi-discipline-preventive-convergence` numbered doctrine (Bundle 2 elevation):

1. **LINE-REF-DRIFT preventive** — Phase 0 §1.1 cited line numbers refreshed at Plan v1 §1.1 grep-verify (line 171-184 confirmed)
2. **CROSS-PATH-SYNC-OMISSION preventive commitment** — no new memory files this cycle expected
3. **DEFERRED-CANARY-ENTRY-OMISSION grep-verify** — closure narrative fresh-disk verifies Bundle 4 entry in `to_be_checked.md`
4. **Closure-audit verdict forwarding 9th-cycle routinization** — §6 procedural commitment
5. **CODE-TEMPLATE-MISIDENTIFICATION preventive** — `Thread.is_alive()` canonical pattern verified pre-implementation
6. **Developer Pass-3 grep at Phase 4 pre-implementation** — Bundle 3 elevated numbered doctrine carry-forward
7. **§0 NEW commitment EXTENSION dual-axis** — file-count + semantic-correctness
8. **BIDIRECTIONAL-VALIDATION sub-rule active** — Bundle 2 elevation; Bundle 3+ carry-forward
9. **Phase 0 explicit-per-bucket grep enumeration** — Bundle 2 lesson
10. **Cross-bundle architectural-coherence preventive** — D3+D5 AST invariant scope discipline (single-function + file-scoped) is Bundle 4 sub-shape distinct from Bundle 3 STANDARD scope
11. **NEW Plan v1 §1.1 grep-verified BEFORE-code refresh** — Bundle 4 NEW preventive (extends `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` rule's behavioral-semantic axis to spec-text-vs-production-code representational integrity)

**11 preventives applied at Bundle 4 Plan v1** (same count as Bundle 3 Plan v2). Trajectory: Bundle 1 (7) → Bundle 2 Plan v3 (9) → Bundle 3 Plan v2 (11) → Bundle 4 Plan v1 (11). Trajectory holds at sustained 11-discipline floor.

### §5.5 4-part Pass-2 grep operational rule extension candidacy CONTINUED

Per Bundle 3 §5.5 ratification: 4-part Pass-2 grep rule (symbol-name uniqueness + behavioral-semantic + symmetric verification + ARITHMETIC SUM-AGAINST-TOTAL). 2nd instance applied at Plan v1 §4.1 file-impact arithmetic. If 1 more arithmetic-axis PI surfaces at Bundle 4+5 + P1, formalize as locked rule extension (3-instance threshold).

---

## §6 Closure-narrative paste template (Plan v1-aware)

```markdown
| **Pre-P1 Bundle 4 (Observability+Concurrency MF6 `_log_drain` daemon-thread failure detection + MF9 `_persistent` read-side lock extension — 3-artifact cycle [Phase 0 + Plan v1 + closure] / **20th OPTIONAL-Plan-v2 proof case LOCKS** if Plan v1 clears 0 PIs OR Multi-axis-precision-pattern SUB-RULE ELEVATION EVENT LOCKS if Plan v1 escalates) CLOSED 2026-05-2X** — [SUMMARY: `_log_drain` daemon thread gains outer-loop try/except wrap catching `_log_q.get()` silent-death failure mode + observability counter/timestamp/error-count via 3 module-level vars + `_sys.__stderr__` direct bypass for stderr emit (avoids `_Tee` infinite loop); `HealthSnapshot.log_drain_alive` field + 5-substring actionable alert + `LOG_DRAIN_STALENESS_SECS=60.0` config; AST invariant ensures `_log_drain` outer-loop try/except + non-swallow stderr-emit pattern (single-function scope); `core/state.py:65` `**_persistent` SPREAD READ extends to lock-around-shallow-copy pattern (P0.B5 D4 writer-side lock extended to reader-side for GIL-free Python forward-compat); AST invariant ensures all `_persistent` access in production scope under `_persistent_lock` (file-scoped to core/state.py)]. **5/5 anchor tests A1-A5 GREEN** with ~17 pytest collections via A2+A3+A5 parametrize fan-outs (much smaller than Bundle 3's 185; Bundle 4 invariants scoped narrowly per sub-shape). **5/5 deliberate-regression confirmations passed cleanly** per `### Induction-surfaces-invariant-gaps`. **Doctrine bumps banked**: `Per-artifact-arithmetic-drift-survives-grep-baseline` 18 → 19 (Phase 0 PI #1 structural BEFORE-code drift). NEW `Phase-0-spec-text-BEFORE-code-doesnt-match-production` 1st instance. `Multi-axis-precision-pattern-confirmed-by-3-consecutive-blocked-bundles` 1 → 2 (Bundle 4 Phase 0 surfaces PI; CONDITIONAL 3 at closure if Plan v1 escalates). `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` 11 → 12 (CAUGHT-REAL-GAP). **CONDITIONAL OPTIONAL-Plan-v2 locks at 20 IF Plan v1 clears 0 PIs OR STAYS at 19 with Multi-axis-precision-pattern 3rd instance LOCKING sub-rule elevation event at closure narrative work**. `### Phase-0-granular-decomposition` 33 → 34 supporting (if closure-actual within NARROW band). `Doctrine-prediction-precision-improving-over-arc` 13th consecutive 0%-streak (if closure-actual = 5 exact). Strict-mode 123 → 126 applications + 35 → 36 closures (3-artifact cycle IF Plan v1 clean OR 4-artifact IF escalates). **Multi-discipline preventive convergence 11 disciplines applied** at Bundle 4 Plan v1 (sustained 11-floor across Bundle 3+4). **`### Architect-reads-production-code-before-sign-off` 33 → 34 banked at closure-audit** (Phase 0 §2 D1 BEFORE-code drift caught at auditor independent grep verification surface).
```

---

## §7 Honest-count commitment

Per `Explicit-closure-honest-count-commitment` discipline:

- Plan v1 §7 MADE → closure §7 HONORED counts as 2 separate instances
- Architect commits to honest closure-actual reporting regardless of band
- IF closure-actual = 5 exact + Plan v1 0 PIs → `Doctrine-prediction-precision-improving-over-arc` 13th-streak banks + OPTIONAL-Plan-v2 sub-rule 20th proof case LOCKS
- IF closure-actual ∈ {4, 6} → ON-TARGET via SLIGHT-DRIFT within ±15%; doctrine bumps; streak interrupted
- IF closure-actual ∈ {3, 7} → SLIGHT-DRIFT within ±30%; doctrine HOLDS at 33; streak interrupted
- IF closure-actual ≤2 OR ≥8 → FALSIFICATION-WATCH activates
- IF Plan v1 surfaces PIs → Multi-axis-precision-pattern 3rd instance LOCKS sub-rule elevation event at closure narrative work (cycle escalates to 4-artifact)

---

## §8 Plan v2 path adjudication (defensive)

Per Q5 CONDITIONAL APPROVAL: OPTIONAL-Plan-v2 path conditional on Plan v1 clearing 0 PIs at auditor review.

Plan v1 covers:
- ✓ Q1-Q8 ratifications applied verbatim (§1-§2)
- ✓ PI #1 absorbed via §1.1 grep-verified BEFORE-code refresh (production text embedded at §1.1 verbatim)
- ✓ §2 D-decisions refined with all ratifications
- ✓ §3 Q5 LOCK at 5 with closure-projection band table
- ✓ §4 file-impact table refined with 4-part Pass-2 grep arithmetic verification
- ✓ §5.4 11-discipline preventive convergence enumeration locked
- ✓ §5.5 4-part Pass-2 grep operational rule extension candidacy 2nd instance applied
- ✓ §6 closure-narrative paste template Plan v1-aware
- ✓ §7 honest-count commitment

If auditor returns Plan v1 review CLEAN (0 PIs) → ship to developer; cycle ships 3-artifact; **20th OPTIONAL-Plan-v2 proof case LOCKS**; pattern-broken streak rebuilds after Bundle 1+2+3 escalation.

If auditor returns Plan v1 with NEW PIs → cycle escalates to 4-artifact (Plan v2 absorbs); **Multi-axis-precision-pattern 3rd instance CONFIRMS → SUB-RULE ELEVATION EVENT LOCKS at Bundle 4 closure narrative work** per locked elevation procedure.

**Architect Plan v1 confidence: HIGH (with strengthened reservation)**. Honest epistemic stance: Bundle 1+2+3 prior-prediction-blocked history per `Zero-precision-items-pre-closure-predictions-blocked` 6-instance sub-rule elevation context (Plan v2 verdict at Bundle 3). Mechanical surfaces (D2 + D4 + D5) are straightforward; D1 outer-loop wrap on top of preserved inner wraps is the load-bearing intervention. PI #1 absorbed cleanly via §1.1 grep-verified refresh. If Plan v1 review surfaces NEW PIs on different axis (e.g., D2 alert-substring count precision OR D5 AST detector scope), cycle escalates to Plan v2.

---

## §9 Procedural commitments (closure-audit) — PRESERVED from Phase 0 §0 + extended

All 13 Phase 0 §0 commitments preserved verbatim. Plan v1 adds 0 NEW commitments — Phase 0 framework sufficient.

NEW commitment carried from auditor §6: Plan v1 §2 D1 BEFORE-code MUST be grep-verified against actual pipeline.py:171-184 production text via fresh-disk Read at drafting time — **HONORED at §1.1 above**.

---

## §10 Known Limitations

1. **Bundle 4.X (full `logging` framework migration)** — deferred per Q6 RATIFIED. Skeptic-1 BUG-3 broader fix migrates to Python `logging.Handler` + `QueueHandler` is mechanically distinct + architecturally larger. Bundle 4 addresses silent-failure-mode acutely; full migration is post-P1 user-discretion work.

2. **`_sys.__stderr__` direct bypass dependency** — D1 exception handler imports `sys as _sys` inside the except block + calls `_sys.__stderr__.write()`. If `sys.__stderr__` is itself failed (e.g., closed by `os.dup2()` in extreme test fixture), the inner try/except swallows. Acceptable trade-off — operator visibility via at-least-counter-increment + log file write attempt preserved.

3. **Counter overflow** — `_log_drain_count: int` will overflow in Python at... essentially never (CPython int is arbitrary precision). Out of scope.

4. **`LOG_DRAIN_STALENESS_SECS=60.0` calibration** — per Q7 RATIFIED. If operator observes false-positive alerts on low-activity pipeline runs, recalibrate to 120.0s in a follow-up.

5. **Bundle 4.Y (broader `state.py` concurrency surfaces)** — if Phase 4 surfaces additional unguarded `_persistent` OR other concurrent state surfaces in `core/state.py`, file Bundle 4.Y.

6. **NEW (Plan v1 §10 #6)**: Phase-0-spec-text-BEFORE-code-doesnt-match-production sub-shape banked at Phase 0 §0 NEW commitment + auditor §4 banking. 1st instance candidate at Bundle 4 Phase 0. Future Plan v1 drafting must grep-verify BEFORE-code against production at drafting time. Same shape as Bundle 3's BIDIRECTIONAL Pass-3 file-count verification but at spec-text representational axis instead of quantifier-precision axis.

---

## §11 Architect Pass-2 grep clearance (4-part rule per Bundle 3 ratification)

Per `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` doctrine + 4-part operational rule extension (Bundle 3 candidacy):

1. **Symbol-name-uniqueness grep** ✓ — `_log_drain` / `_log_q` / `_LOG_FILE` / `_persistent` / `_persistent_lock` all unambiguous in production scope.
2. **Behavioral semantic verification** ✓ — §1.1 grep-verified BEFORE-code production text against pipeline.py:171-184; §1.2 AFTER-code preserves all 4 architectural invariants (inner wraps + P0.4 annotations + outer wrap + stderr bypass).
3. **Symmetric verification** ✓ — D1+D2 preserve existing inner-wrap behavior on non-failure path; D4 preserves `_persistent` content semantic on read; D5 preserves `set_persistent` writer-side existing protection.
4. **ARITHMETIC SUM-AGAINST-TOTAL verification** ✓ — §4.1 file-impact table: 2 new + 4 modified = 6 file events; 30+35+5 = 70 line-level edits; arithmetic verified. NEW preventive at Plan v1 (Bundle 3 § 5.5 lesson applied 2nd instance).

### §11.1 Plan v1 §1.1 BEFORE-code grep-verify result (per §0 NEW commitment)

Executed fresh-disk Read at Plan v1 drafting 2026-05-28 → production at pipeline.py:171-184 embedded verbatim at §1.1 above. NO discrepancies vs production text. PI #1 absorbed cleanly.

---

## §12 Standing by for auditor Plan v1 verdict

If CLEAN (0 PIs) → OPTIONAL-Plan-v2 path activates; Plan v1 ships to developer for Phase 4 implementation; cycle becomes 3-artifact; **20th OPTIONAL-Plan-v2 proof case LOCKS at Bundle 4 closure**; Multi-axis-precision-pattern STAYS at 2 (no 3rd instance confirmation).

If PIs surface → Plan v2 absorbs; cycle escalates to 4-artifact; Multi-axis-precision-pattern 3rd instance CONFIRMS → SUB-RULE ELEVATION EVENT LOCKS at closure narrative work per locked elevation procedure.

**Architect's Plan v1 confidence: HIGH (with strengthened reservation)** per §0 + §8. Honest epistemic stance: Bundle 1+2+3 prior-prediction-blocked history acknowledged; PI #1 absorbed cleanly via grep-verified refresh; mechanical surfaces straightforward.

---

**Filed**: 2026-05-28
**Architect**: Claude
**Forwarded to**: Auditor (external)
**Predecessor**: `tests/pre_p1_bundle4_observability_concurrency_audit.md` (Phase 0 ACCEPT WITH 1 PI; Q1-Q8 RATIFIED with architect's leans; Q5 CONDITIONAL on Plan v1 cleanliness; OPTIONAL-Plan-v2 stakes elevated to 20th proof case LOCK vs Multi-axis-precision-pattern SUB-RULE ELEVATION EVENT)
