# Pre-P1 Bundle 4 — Observability+Concurrency (MF6 + MF9) Phase 0 Audit (2026-05-28)

**Cycle**: Pre-P1 must-fix Bundle 4 (Observability+Concurrency)
**Scope**: MF6 (`_log_drain` daemon-thread failure detection) + MF9 (`_persistent` lock extension to read-side spread)
**Source**: skeptic1-bugs-edges-2026-05-27.md BUG-3 (MF6) + P0.B5 closure narrative 2026-05-21 known-limitation (MF9 deferred read-side gap)
**Sequencing**: Pre-P1 must-fix sequence position 4 of 5 (CEO synthesis Path A locked) — sequential after Bundle 3 close 2026-05-28
**Discipline**: Strict-mode; Bundle 3 carry-forward (Developer-Pass-3-grep-at-Phase-4-pre-implementation numbered doctrine + 4-part Pass-2 grep rule + Multi-axis-precision-pattern watch)
**Architect**: Claude
**Auditor**: External

---

## §0 Procedural commitments (Bundle 3 carry-forward + Bundle 4 NEW)

All 8 Bundle 3 Phase 0 §0 commitments PRESERVED. Bundle 4 NEW:

1. **Path C grep-verify at closure surface** — production code + memory files + `to_be_checked.md` fresh-disk Python read
2. **Cross-path memory-file discipline** if any new memory files land
3. **DEFERRED-CANARY-ENTRY-OMISSION preventive** via fresh-disk Python read at closure
4. **Closure-audit verdict forwarding** to auditor (9th-cycle routinization)
5. **CODE-TEMPLATE-MISIDENTIFICATION preventive** — daemon-thread observability template verified against Python `threading.Thread` canonical examples (`Thread.is_alive()` + `Thread.join(timeout=...)`); `_persistent_lock` extension template verified against existing P0.B5 D4 pattern
6. **§0 NEW commitment EXTENSION dual-axis verification** at developer Pass-3 (file-count + semantic-correctness) — Bundle 3 elevation carry-forward; **MANDATORY** per `### Developer-Pass-3-grep-at-Phase-4-pre-implementation` numbered doctrine (Bundle 3 closure 2026-05-28)
7. **4-part Pass-2 grep operational rule** applied at Plan v1+ (symbol-name uniqueness + behavioral-semantic + symmetric verification + **ARITHMETIC SUM-AGAINST-TOTAL** — Bundle 3 lesson)
8. **Multi-discipline preventive convergence enumeration** at Plan v1 §5.4 + preserved at closure (Bundle 3 = 11 disciplines; Bundle 4 target ≥7 disciplines per locked elevation framework)
9. **BIDIRECTIONAL-VALIDATION sub-rule active** — Bundle 2 elevation; Bundle 3 carry-forward
10. **Phase 0 explicit-per-bucket grep enumeration** — applied at §1 below (no globbed-pattern approximation; Bundle 2 lesson)
11. **Cross-bundle architectural-coherence preventive** — D3 + D5 AST invariant scope = Bundle 2 D6 SPDX + Bundle 3 D2/D4 STANDARD scope (carry-forward Q3 STANDARD scope discipline)
12. **`Multi-axis-precision-pattern-confirmed-by-3-consecutive-blocked-bundles` 1st instance carry-forward** — Bundle 4 enters Phase 0 expecting Plan v2+ absorption per locked Bundle 3 Plan v2 verdict observation
13. **Plan v2-collection-estimate-omits-AST-invariant-fan-out lesson applied** — Plan v1+ Q5 estimation MUST explicitly account for AST invariant detector parametrize across STANDARD scope (Bundle 3 Q4 ratification)

---

## §1 Grep-verified scope baseline (2026-05-28)

Per `### Grep-baseline-before-drafting` doctrine + Bundle 2 `Phase-0-globbed-pattern-estimates-imprecise-explicit-enumeration-precise` lesson + Bundle 3 4-part Pass-2 grep arithmetic discipline: explicit per-bucket grep enumeration locked at Phase 0 drafting.

### §1.1 MF6 — `_log_drain` cluster inventory in pipeline.py

24 references across pipeline.py (cluster lines 32-244):

| Surface | Line(s) | Role | Bundle 4 scope |
|---|---|---|---|
| `import queue as _log_queue_mod` | 32 | Module import | Out-of-scope |
| `_LOG_FILE: "Any" = None` (placeholder) | 92 | Module-level guard | Out-of-scope |
| `if _LOG_FILE:` + flush/close in `_check_terminal_output_size_cap` | 107-118 | Pre-rotation cleanup | Out-of-scope |
| `_LOG_FILE = open(log_path, "w", ...)` | 123 | Post-rotation reopen | Out-of-scope |
| `_log_q: SimpleQueue` module-level | 169 | Queue declaration | Out-of-scope |
| **`def _log_drain() -> None:`** | 171 | **DRAIN FUNCTION (D1 target)** | **IN SCOPE D1** |
| `_log_q.get()` inside drain | 174 | Queue blocking read | D1 target — wrap in try/except |
| `_LOG_FILE.write(data)` + `_LOG_FILE.flush()` | 181-182 | File I/O — failure point | D1 target — wrap in try/except |
| `class _Tee:` | 186 | Stdout/stderr hook | Out-of-scope |
| `_log_q.put((self._s, data))` in Tee | 191 | Producer-side queue write | Out-of-scope (producer doesn't crash) |
| Tier 1 module-level main-only block | 216-244 | Daemon-thread spawn | In scope for D2/D3 (liveness check entry point) |
| `_LOG_FILE = open(...)` in main-only | 233 | Logfile open | Out-of-scope (already guarded) |
| **`_log_drain_thread = Thread(target=_log_drain, daemon=True, name="log-writer")`** | 240 | **THREAD HANDLE** | **IN SCOPE D2** (liveness check needs `_log_drain_thread.is_alive()`) |
| `_log_drain_thread.start()` | 241 | Thread spawn | Out-of-scope |
| `sys.stdout = _Tee(sys.stdout)` + `sys.stderr = _Tee(sys.stderr)` | 243-244 | Tee install | Out-of-scope |

**Total Bundle 4 in-scope sites for MF6**: 3 (drain function body + thread handle + liveness check integration point).

### §1.2 MF9 — `_persistent` lock extension production surfaces

Per `core/state.py` grep (5 production lines after subtracting docstrings):

| Line | Pattern | Lock status | Bundle 4 scope |
|---|---|---|---|
| 18 | `_persistent: dict = {}` (module-level declaration) | N/A (initial value) | Out-of-scope |
| 22 | `def set_persistent(key, value)` | N/A (def line) | Out-of-scope |
| 41 | `global _persistent` | Inside `set_persistent` body | Out-of-scope |
| 43 | `_persistent = {**_persistent, key: value}` (writer + spread) | **ALREADY UNDER `_persistent_lock`** (P0.B5 D4) | Out-of-scope (already protected) |
| **65** | **`**_persistent`** SPREAD READ in `write()` | **NOT under lock** | **IN SCOPE D4** (THE Bundle 4 gap) |

**Total Bundle 4 in-scope sites for MF9**: 1 (`**_persistent` SPREAD READ at `core/state.py:65`).

Cross-file `_persistent` references (95 grep hits total across 7 files): pipeline.py 1 + tests 89 + core/state.py 5. The 89 test references include 59 `set_persistent` calls + 6 `_persistent` read assertions + ~24 mock/fixture references. Tests are out-of-scope for the production lock extension; D5 AST invariant verifies test-fixture access patterns don't bypass the production protection.

### §1.3 Bundle 4 Phase 0 baseline counts (per `### Grep-baseline-before-drafting`)

Pre-Bundle-4 baseline (post-Bundle-3 closure-ratification 2026-05-28):
- Strict-industry-standard mode applications: 123
- Strict-industry-standard mode closures: 35
- Spec-first review cycle: 132
- `### Grep-baseline-before-drafting`: 90
- Cross-cycle-handoff transparency: 93
- Spec-time grep-verification: 100
- `### Twin-filename-pitfall-prevention`: 34
- `### Architect-reads-production-code-before-sign-off`: 33
- `### Multi-discipline-preventive-convergence`: 11-discipline trajectory (Bundle 3 closure)
- `### Developer-Pass-3-grep-at-Phase-4-pre-implementation`: 3 cycle-events (Bundle 1+2+3); ELEVATED to numbered doctrine at Bundle 3 closure
- `### Pass-2-grep-auditor-verified-before-Plan-v1-approval`: 11 instances (Bundle 3 = CAUGHT-REAL-GAP event)
- Auditor-Q5-estimates-trail-grep: 39
- `### Phase-0-granular-decomposition-enables-accurate-estimates`: 33 supporting
- `Doctrine-prediction-precision-improving-over-arc`: 12 consecutive 0%-streak (P0.S10 9th + Bundle 1 10th + Bundle 2 11th + Bundle 3 12th)
- OPTIONAL-Plan-v2 sub-rule track record: 19 (3 consecutive blocked Pre-P1 bundles; `Multi-axis-precision-pattern-confirmed-by-3-consecutive-blocked-bundles` 1st instance)

---

## §2 D-decisions

### D1 — MF6 `_log_drain` body try/except + observability counter + last-drain-timestamp

**Scope (§1.1 locked)**: `pipeline.py:171-183` `_log_drain` function body.

**Mechanical replacement** (initial framing; Plan v1 will refine):

```python
# BEFORE (current production)
def _log_drain() -> None:
    while True:
        stream, data = _log_q.get()
        try:
            stream.write(data)
            stream.flush()
        except Exception:
            pass  # producer keeps going
        if _LOG_FILE:
            _LOG_FILE.write(data)
            _LOG_FILE.flush()

# AFTER (Bundle 4 D1)
_log_drain_count: int = 0  # observability counter (module-level)
_log_drain_last_at: float = 0.0  # last successful drain timestamp (WALLCLOCK — operator-readable)
_log_drain_error_count: int = 0  # exception counter (module-level)

def _log_drain() -> None:
    global _log_drain_count, _log_drain_last_at, _log_drain_error_count
    while True:
        try:
            stream, data = _log_q.get()
            try:
                stream.write(data)
                stream.flush()
            except Exception:
                pass  # producer keeps going (preserves prior behavior)
            if _LOG_FILE:
                _LOG_FILE.write(data)
                _LOG_FILE.flush()
            _log_drain_count += 1
            _log_drain_last_at = time.time()  # WALLCLOCK: observability timestamp
        except Exception as e:
            # Defense-in-depth — DO NOT swallow silently. Emit to stderr directly
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

**Critical contract preserved**:
- Producer-side `_log_q.put()` (`_Tee.write`) keeps blocking-free semantics
- Loop-level try/except prevents thread death from a single bad item
- `_sys.__stderr__` bypass prevents Tee-routed infinite loop on stderr write
- Counter + timestamp accessible from `core/health.py` for D2

### D2 — MF6 `HealthSnapshot` log-drain liveness field + actionable alert

**Scope**: `core/health.py` (existing module). New fields:
- `log_drain_alive: bool = True` — set by `gather_health_snapshot()` checking `_log_drain_thread.is_alive()` AND `time.time() - _log_drain_last_at < LOG_DRAIN_STALENESS_SECS=60.0`
- `log_drain_count: int = 0` — copies `pipeline._log_drain_count` snapshot
- `log_drain_error_count: int = 0` — copies `pipeline._log_drain_error_count` snapshot

**`format_health_line` conditional emit**: when `not log_drain_alive`, append `log_drain=DEAD` field. When `log_drain_error_count > 0`, append `log_drain_errors=N` field.

**`format_health_alerts` actionable recovery alert** (5 verbatim substrings per locked alert-message discipline P0.R10 D5 + P0.R12-R15 D2 precedent):
- `"Log drain thread degraded"`
- `"check pipeline restart"`
- `"messages drained: N"` (N = log_drain_count)
- `"errors: M"` (M = log_drain_error_count)
- `"LOG_DRAIN_STALENESS_SECS"`

**New `core/config.py` constants** (1 addition):
- `LOG_DRAIN_STALENESS_SECS: float = 60.0` — staleness threshold for liveness check

### D3 — MF6 AST invariant: `_log_drain` body has try/except + non-swallow stderr emit

**New test file**: `tests/test_log_drain_observability_invariant.py`

**Detector logic**:
- AST-walks `pipeline.py`; locates `_log_drain` `ast.FunctionDef` by name
- Asserts the outer `while True:` body wraps in `ast.Try` with at least one `ast.ExceptHandler`
- Asserts the except handler does NOT contain `ast.Pass` as sole body element (must have non-pass body)
- Asserts the except handler body contains a string match for `_sys.__stderr__` OR equivalent stderr-emit pattern
- Self-tests: forward (synthetic violation where except body is just `pass` fires) + inverse (correct shape passes)

**Cross-bundle architectural-coherence preventive**: same AST invariant test-file pattern as Bundle 3 D2/D4 (path-based allowlist + AST detector + self-tests). Sub-shape: this invariant is **scoped to a single function** (not file-wide like Bundle 3 D2/D4). Plan v1 §1.4 below documents the sub-shape distinction.

### D4 — MF9 `_persistent` lock extension to `**_persistent` SPREAD read

**Scope**: `core/state.py:65` — `**_persistent` SPREAD in `write()` body.

**Mechanical replacement**:

```python
# BEFORE (current production, P0.B5 D4 era)
def write(...):
    state = {
        ...
        "online":            True,
        **_persistent,
    }
    # ... atomic file write ...

# AFTER (Bundle 4 D4)
def write(...):
    # P0.B5 D4 (Bug 10 / V5) wrote set_persistent under _persistent_lock; Bundle 4 D4
    # extends defense-in-depth to the read-side spread for GIL-free Python 3.13+
    # --disable-gil forward-compat.
    with _persistent_lock:
        _persistent_snapshot = dict(_persistent)  # cheap shallow copy under lock
    state = {
        ...
        "online":            True,
        **_persistent_snapshot,
    }
    # ... atomic file write ...
```

**Critical design**: lock held ONLY for the shallow dict() copy — NOT held across the file I/O (avoids contention with concurrent `set_persistent` writers). Same shape as P0.B5 D4's atomic-replace pattern.

### D5 — MF9 AST invariant: `_persistent` accessed only under lock

**New test file**: `tests/test_persistent_lock_invariant.py`

**Detector logic**:
- AST-walks `core/state.py`; locates every `ast.Name(id='_persistent', ctx=Load|Store)` AND `**_persistent` (DictUnpacking) occurrence
- Asserts each occurrence's enclosing scope is one of:
  - Module-level declaration (line 18 only — initial assignment)
  - Inside `ast.With` block whose `withitem.context_expr` is `_persistent_lock` (writer/reader-under-lock)
  - Inside function body that is the lock-acquisition source itself
- Allowlist via path: production scope `core/state.py` only; test files unrestricted (allowed to inspect state for fixtures)
- Self-tests: forward (synthetic unguarded read fires) + inverse (under-lock read passes)

**Cross-bundle architectural-coherence preventive**: same architectural-defense pattern as Bundle 3 D4 (locked-resource invariant via AST scope detection). Detector self-tests follow Bundle 3 D2/D4 precedent.

---

## §3 Q5 LOCK projection — anchor count estimate (Bundle 3 collection-fan-out lesson applied)

**Initial estimate (Phase 0)**: **5 anchors** at mid; NARROW band ±15% = [4.25, 5.75]; SLIGHT-DRIFT ±30%; FALSIFICATION ≤3 OR ≥8.

| # | Anchor | Type | Parametrize fan-out |
|---|---|---|---|
| A1 | D1 `_log_drain` body try/except + counter/timestamp | structural source-inspection on `pipeline.py:171-183` `_log_drain` function | 1 (single-function scope; not file-wide) |
| A2 | D2 `HealthSnapshot` log-drain field + format_health_alerts | source-inspection: 3 new fields + 5 alert substrings + 1 config constant | ~5 (alert substring parametrize) |
| A3 | D3 AST invariant `_log_drain` try/except non-swallow | structural — single-function AST scan + self-tests (forward + inverse) | 1 + 2 self-tests |
| A4 | D4 `**_persistent` read-side lock + snapshot pattern | source-inspection on `core/state.py:65` | 1 (single-line scope) |
| A5 | D5 AST invariant `_persistent` accessed-only-under-lock | structural — file-scoped AST scan + self-tests | 1 + 2 self-tests |

**Total = 5 logical anchors. NARROW band [4.25, 5.75]. Q5 LOCK = 5.**

**Bundle 3 Q4 lesson applied**: A1+A2+A3+A4+A5 parametrize fan-out projection (per Plan-v2-collection-estimate-omits-AST-invariant-fan-out 1st instance carry-forward):
- A1: 1 source-inspection
- A2: ~5 alert substring parametrize + 3 field-presence + 1 config = ~9 collections
- A3: 1 + 2 self-tests = ~3 collections (single-function scope; NOT file-wide)
- A4: 1 source-inspection
- A5: 1 + 2 self-tests = ~3 collections (file-scoped to core/state.py only; ~5 production lines)

**Total parametrize fan-out projection: ~17 collections** (much smaller than Bundle 3's 185 — Bundle 4 invariants are scoped to single function (D3) + single file (D5), NOT STANDARD scope. Bundle 3 D2+D4 67-file STANDARD-scope parametrize is the dominant cost.)

**Phase 4 strengthening caveat** (Bundle 1+2+3 pattern): if Phase 4 surfaces detector gap requiring same-cycle strengthening, STRENGTHEN in same cycle + bank as `### Induction-surfaces-invariant-gaps` family event (would be 10th instance after Bundle 3's 9th annotation-idempotency).

---

## §4 Cross-spec impact

### §4.1 File-impact table (Phase 0 estimate; Plan v1 will refine via Pass-2 grep)

| D | New files | Modified files | Approx scope |
|---|---|---|---|
| D1 | — | `pipeline.py` (3 module-level vars + body refactor) | ~25 line-level edits in `_log_drain` cluster |
| D2 | — | `core/health.py` (3 new fields + format_health_line conditional + format_health_alerts) + `core/config.py` (1 new constant) | ~30 line-level edits across 2 files |
| D3 | `tests/test_log_drain_observability_invariant.py` (NEW) | None | 1 new test file + ~50 LOC AST detector + self-tests |
| D4 | — | `core/state.py:65` (single-line edit + 4-line lock-snapshot block) | ~5 line-level edits |
| D5 | `tests/test_persistent_lock_invariant.py` (NEW) | None | 1 new test file + ~50 LOC AST detector + self-tests |

**Total scope estimate (Phase 0)**: 2 new test files + ~60 line-level production-code edits across 4 files (`pipeline.py` + `core/health.py` + `core/config.py` + `core/state.py`).

### §4.2 Bundle 4-5 unchanged dependencies

Bundle 5 (Contract typing MF7+MF8) is code-only with no dependency on Bundle 4. **Can ship sequentially per Path A locked at CEO decisions doc** (Bundle 4 → Bundle 5).

### §4.3 Bundle 4.X candidates filed at Phase 0

- **Bundle 4.X — Migrate `_log_drain` to Python `logging` framework** (Skeptic-1 BUG-3 broader fix). Bundle 4 ships observability instrumentation only; full migration to `logging.Handler` + `QueueHandler` deferred to Bundle 4.X. Sev: HIGH per Skeptic-1; Bundle 4's observability fix addresses the most-acute failure-mode (silent drain death).
- **Bundle 4.Y — Other `state.py` concurrency surfaces** (if Phase 4 surfaces additional unguarded `_persistent` access OR other concurrent state surfaces in `core/state.py`). Currently scoped narrowly to the `**_persistent` SPREAD read; broader audit deferred to 4.Y.

---

## §5 Auditor pre-emption + RATIFICATION QUESTIONS

### Q1 — D1 `_log_drain` outer-loop try/except vs inner-call-only try/except scope

**Skeptic-1's framing**: "drain-thread crash = total log loss with no operator signal". Implies the catastrophe is loop-level death.

**Options**:
- **(a) Outer-loop try/except** (Phase 0 §2 D1 default): wraps the entire body in `try: ... except Exception as e: stderr-emit + continue`. Catches all exceptions including `_log_q.get()` failures, `stream.write` failures (already inner-wrapped), `_LOG_FILE.write` failures.
- **(b) Inner-call-only try/except**: wraps only `_log_q.get()` separately from the existing inner `stream.write` and proposed `_LOG_FILE.write` wraps. More granular but might miss exotic exception sites (e.g., `_log_drain_count += 1` integer overflow — vanishingly improbable but possible).
- **(c) Hybrid**: outer + inner (defense-in-depth). Most exception-aware but most code.

**Architect lean**: (a). Outer-loop wrap is the most direct fix for "drain-thread silent death"; inner-only wraps are best-case but don't catch unforeseen failure modes.

**Auditor adjudication requested**.

### Q2 — D4 `_persistent_lock` granularity: dict-copy under lock vs lock-held-across-IO

**Phase 0 §2 D4 default**: lock held ONLY for `dict(_persistent)` shallow copy; released BEFORE the file I/O.

**Options**:
- **(a) Lock around shallow-copy only** (default): minimal contention; aligns with P0.B5 D4 pattern.
- **(b) Lock around full `write()` body**: holds lock across atomic file write (~ms-scale). Eliminates ANY concurrent-mutation possibility during write composition. But: heavier lock contention; could starve other `set_persistent` writers during disk-busy moments.

**Architect lean**: (a). State.write() runs at ~10Hz dashboard refresh cadence; lock contention with ~1Hz set_persistent calls is negligible at shallow-copy granularity. (b)'s extra protection isn't load-bearing because the file-write is atomic-replace.

**Auditor adjudication requested**.

### Q3 — D5 AST invariant: allowed scopes for `_persistent` access

**Architect lean**: production scope = `core/state.py` only. Allowed sites:
- Line 18 (module-level declaration; initial empty dict)
- Lines 41-43 (writer inside `set_persistent` body — under existing lock)
- Line 65 (Bundle 4 D4 new — reader inside `write` body, under lock for shallow-copy)

Out-of-scope (allowlist): test files (`tests/*.py` + top-level `test_*.py`) — tests inspect state for fixture/setup purposes; not production runtime.

**Auditor adjudication requested**.

### Q4 — Q5 anchor count: 5 mid? OR auditor sees different decomposition?

Per `### Phase-0-granular-decomposition-enables-accurate-estimates`: auditor independent enumeration may identify additional anchors (e.g., split A1 into `_log_drain body refactor` + `module-level counter declarations`). Auditor's lean requested.

### Q5 — OPTIONAL-Plan-v2 path eligibility

Bundle 1+2+3 all blocked at Plan v1 review (3 consecutive blocked Pre-P1 bundles confirmed `Multi-axis-precision-pattern-confirmed-by-3-consecutive-blocked-bundles` 1st instance). Bundle 4's scope is structurally smaller (5 in-scope sites vs Bundle 3's 80+ migration sites + 67-file invariant scope). OPTIONAL-Plan-v2 path candidacy at Bundle 4 closure depends on:
- Whether Plan v1 surfaces 0 PIs at auditor review
- Whether Phase 0's narrow scope (5 in-scope production sites) avoids the multi-axis precision pitfalls of Bundle 1+2+3's broader scopes

**Architect's read**: Bundle 4 has GENUINELY smaller scope than prior Pre-P1 bundles. Multi-axis-precision-pattern might NOT confirm at Bundle 4 if Plan v1 is clean. 20th OPTIONAL-Plan-v2 proof case could finally LOCK at Bundle 4 closure (after 3 consecutive blocked Pre-P1 bundles).

**Auditor adjudication requested**: conditional approval of OPTIONAL-Plan-v2 path subject to Plan v1 review outcomes.

### Q6 — Bundle 4.X (full `logging` framework migration) sequencing

File Bundle 4.X concurrent with Bundle 4 closure OR defer to separate cycle?

**Architect lean**: defer. Full `logging.Handler` + `QueueHandler` migration is mechanically distinct (and architecturally larger). Bundle 4's observability fix addresses the silent-failure-mode immediately. Bundle 4.X file at user discretion post-P1.

**Auditor adjudication requested**.

### Q7 — `LOG_DRAIN_STALENESS_SECS=60.0` default vs different value

**Phase 0 §2 D2 default**: 60.0 seconds.

**Rationale**: log drain processes producer-emitted messages from stdout/stderr. At typical pipeline cadence (10Hz health logs + ~1Hz state writes + bursty print() calls during conversations), messages are continuous. 60s of no-drain is unambiguously a stuck-thread signal.

**Options**:
- **(a) 60.0s** (default): conservative; minimizes false-positive alerts on low-activity sessions.
- **(b) 30.0s**: more sensitive; matches `SCENE_STALE_SECS` precedent.
- **(c) 120.0s**: extra-conservative; even fewer false-positives.

**Auditor adjudication requested**.

### Q8 — `_log_drain` exception counter scope: error-count only OR error+success ratio?

**Phase 0 §2 D1 default**: separate `_log_drain_count` (success) + `_log_drain_error_count` (failure).

**Rationale**: separate counters surface both health-success rate AND absolute failure count; more diagnostically useful than a ratio.

**Auditor adjudication requested**.

---

## §6 Procedural commitments (Phase 0 → Plan v1 transition)

1. **Plan v1 §1 MUST locks exhaustive per-site verification** of all 3 MF6 in-scope sites + 1 MF9 in-scope site (`core/state.py:65`).
2. **Plan v1 §0 NEW commitment**: developer Pass-3 grep at Phase 4 pre-implementation MUST verify both file-count consistency AND semantic-correctness per migrated site per `### Developer-Pass-3-grep-at-Phase-4-pre-implementation` numbered doctrine (Bundle 3 elevation).
3. **Plan v1 §5.4 Multi-discipline preventive convergence enumeration** preserved per elevated `### Multi-discipline-preventive-convergence` numbered doctrine (Bundle 2 elevation; Bundle 3 carry-forward).
4. **4-part Pass-2 grep operational rule applied** at Plan v1 §1.* (symbol-name uniqueness + behavioral-semantic + symmetric verification + arithmetic sum-against-total — Bundle 3 carry-forward).
5. **Closure-audit verdict forwarding** to auditor before declaring Bundle 4 CLOSED (9th-cycle routinization).

---

## §7 Standing by for auditor Phase 0 verdict

Phase 0 grep-baseline locked. **3 MF6 + 1 MF9 = 4 in-scope production sites** independently verified at architect Pass-1 grep 2026-05-28. Bundle 4 scope is structurally smaller than Bundle 3 (4 sites vs Bundle 3's 80+ sites).

If auditor returns CLEAN (0 PIs): proceed to Plan v1 drafting with locked Q1-Q8 ratifications. OPTIONAL-Plan-v2 path candidacy gated at Plan v1 review.

If auditor returns with PIs: Plan v1 absorbs at architect-side.

8 RATIFICATION QUESTIONS surfaced for explicit auditor adjudication (Q1-Q8). All have architect leans documented.

---

**Filed**: 2026-05-28
**Architect**: Claude
**Forwarded to**: Auditor (external)
**Predecessor**: Pre-P1 Bundle 3 CLOSED 2026-05-28 (4-artifact cycle ratified; 10 numbered doctrines including newly elevated `### Developer-Pass-3-grep-at-Phase-4-pre-implementation`)
