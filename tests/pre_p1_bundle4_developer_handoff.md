# Pre-P1 Bundle 4 — Developer Phase 4 Handoff (2026-05-28)

**Status**: Plan v1 RATIFIED CLEAN by auditor 2026-05-28. Phase 4 GREENLIT.
**Cycle shape**: 3-artifact (Phase 0 + Plan v1 + closure) — **OPTIONAL-Plan-v2 path ACTIVATED**
**Major milestone at closure**: **20th OPTIONAL-Plan-v2 proof case LOCKS** + 13th consecutive 0%-streak rebuild candidate
**Scope**: 4 in-scope production sites (3 MF6 + 1 MF9)

---

## §1 Source-of-truth artifacts

Read in order:

1. **Plan v1** (`tests/pre_p1_bundle4_observability_concurrency_plan_v1.md`) — authoritative; PI #1 absorbed via §1.1 grep-verified BEFORE-code refresh
2. **Phase 0 audit** (`tests/pre_p1_bundle4_observability_concurrency_audit.md`) — Q1-Q8 ratifications + 13 procedural commitments

Plan v1 supersedes Phase 0 on every detail involving PI #1 absorption.

---

## §2 Shipping order (Q1-Q8 RATIFIED at Phase 0)

**D1 → D2 → D3 → D4 → D5**

Each step lands as own commit. D1+D2 (MF6 observability) → D3 (MF6 invariant) → D4 (MF9 lock extension) → D5 (MF9 invariant).

---

## §3 §0 NEW commitment EXTENSION dual-axis Pass-3 grep at Phase 4 pre-implementation

Per `### Developer-Pass-3-grep-at-Phase-4-pre-implementation` numbered doctrine (Bundle 3 elevation) — **MANDATORY BEFORE invoking any code changes**.

### §3.1 File-count verification axis

Run Pass-3 grep verifying:
- `_log_drain` / `_log_q` / `_LOG_FILE` / `_Tee` cluster references in pipeline.py = 24 total (matches Phase 0 §1.1 enumeration)
- `_log_drain` function body at pipeline.py:171-184 (12 lines: def 171 + docstring 172 + body 173-184) — matches Plan v1 §1.1 grep-verified production text VERBATIM
- `_persistent` references in core/state.py = 5 production (matches Plan v1 §1.8 / Phase 0 §1.2 enumeration; lines 18, 22, 41, 43, 65)
- `_persistent_lock` references in core/state.py = 2 (declaration line 19 + acquisition line 42)

### §3.2 Semantic-correctness verification axis (Bundle 3 carry-forward)

Per Bundle 3 dual-axis discipline carry-forward + Bundle 4 NEW preventive (Plan v1 §5.4 #11 grep-verified BEFORE-code refresh): each migrated site MUST preserve:
- For D1: BOTH inner try/except wraps preserved EXACTLY (stream.write at 175-179 + `_LOG_FILE.write` at 180-184); P0.4-annotated `# OPTIONAL: raising kills the daemon and silences all subsequent logging` comments preserved verbatim
- For D4: lock granularity = shallow-copy-only (NOT lock-across-IO per Q2 (a) RATIFIED)

### §3.3 If file-count drift > ±10% OR semantic-correctness anomaly surfaces → STOP

Raise to architect for Plan v2 absorption (would surface Multi-axis-precision-pattern 3rd instance + SUB-RULE ELEVATION EVENT LOCKS). Per Bundle 3 catching-layer precedent.

If clean → proceed to Phase 4 implementation.

---

## §4 D-decisions (Plan v1-authoritative)

### D1 — MF6 `_log_drain` outer-loop try/except + 3 observability state vars

**Scope**: pipeline.py near line 169 (3 NEW module-level vars) + lines 171-184 (function body refactor).

**3 NEW module-level observability vars** (insert near `_log_q: SimpleQueue` declaration at line 169):

```python
_log_drain_count: int = 0  # observability counter — successful drains
_log_drain_last_at: float = 0.0  # WALLCLOCK: observability — last successful drain timestamp
_log_drain_error_count: int = 0  # observability counter — exception count
```

**Function body refactor** (replace pipeline.py:171-184 with):

```python
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

**Critical preservation** (per Plan v1 §1.2):
- BOTH inner try/except wraps stay EXACTLY (stream.write + `_LOG_FILE.write`)
- P0.4-annotated `# OPTIONAL: raising kills the daemon and silences all subsequent logging` comments preserved verbatim at both inner swallow sites
- Outer-loop wrap catches `_log_q.get()` failures (load-bearing) + counter updates + exotic failures
- `_sys.__stderr__` direct bypass prevents `_Tee` infinite loop on stderr write

### D2 — MF6 `HealthSnapshot` log-drain liveness field + actionable alert

**Scope**: `core/health.py` + `core/config.py`.

**`core/config.py` NEW constant**:

```python
LOG_DRAIN_STALENESS_SECS: float = 60.0  # Bundle 4 D2 — log drain liveness threshold
```

**`core/health.py` modifications**:

NEW fields on `HealthSnapshot` dataclass:
- `log_drain_alive: bool = True`
- `log_drain_count: int = 0`
- `log_drain_error_count: int = 0`

`gather_health_snapshot()` populates via:
```python
import pipeline  # late import to avoid circular
log_drain_alive = (
    pipeline._log_drain_thread.is_alive()
    if pipeline._log_drain_thread is not None
    else True  # not-yet-spawned = alive (boot-time race tolerance)
) and (
    time.time() - pipeline._log_drain_last_at < config.LOG_DRAIN_STALENESS_SECS
    if pipeline._log_drain_last_at > 0
    else True  # never-drained = alive (boot-time race tolerance)
)
log_drain_count = pipeline._log_drain_count
log_drain_error_count = pipeline._log_drain_error_count
```

`format_health_line` conditional emit:
- when `not log_drain_alive`: append `log_drain=DEAD` field
- when `log_drain_error_count > 0`: append `log_drain_errors=N` field

`format_health_alerts` actionable recovery alert (5 VERBATIM SUBSTRINGS — per locked alert-message discipline P0.R10 D5 + P0.R12-R15 D2 precedent):

```python
if not snapshot.log_drain_alive:
    alerts.append(
        f"Log drain thread degraded — check pipeline restart "
        f"(messages drained: {snapshot.log_drain_count}, "
        f"errors: {snapshot.log_drain_error_count}, "
        f"LOG_DRAIN_STALENESS_SECS={config.LOG_DRAIN_STALENESS_SECS})"
    )
```

The 5 verbatim substrings (each MUST appear in the alert string):
1. `"Log drain thread degraded"`
2. `"check pipeline restart"`
3. `"messages drained:"`
4. `"errors:"`
5. `"LOG_DRAIN_STALENESS_SECS"`

### D3 — MF6 AST invariant: `_log_drain` body has try/except + non-swallow stderr emit

**New test file**: `tests/test_log_drain_observability_invariant.py`

**Detector logic** (single-function scope):

```python
"""Bundle 4 D3 — AST invariant: pipeline.py:_log_drain body has outer-loop try/except
that does NOT swallow silently. Catches the silent-death failure mode per Skeptic-1 BUG-3.

Single-function scope (NOT file-wide). Distinct from Bundle 3 D2/D4 STANDARD-scope.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

import ast
import pathlib


PIPELINE_PATH = pathlib.Path(__file__).parent.parent / "pipeline.py"


def _find_log_drain_function(source: str) -> ast.FunctionDef:
    """Locate _log_drain FunctionDef in pipeline.py."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_log_drain":
            return node
    raise AssertionError("_log_drain function not found in pipeline.py")


def test_log_drain_has_outer_loop_try_except() -> None:
    """Outer-loop try/except wraps the while True body — catches _log_q.get() silent-death."""
    source = PIPELINE_PATH.read_text(encoding="utf-8")
    func = _find_log_drain_function(source)
    # Find while True body
    while_node = next(
        n for n in ast.walk(func) if isinstance(n, ast.While)
    )
    # First statement in while body MUST be ast.Try with at least one handler
    assert len(while_node.body) >= 1, "_log_drain while body is empty"
    first_stmt = while_node.body[0]
    assert isinstance(first_stmt, ast.Try), (
        f"_log_drain outer-loop body must start with try/except; got {type(first_stmt).__name__}"
    )
    assert len(first_stmt.handlers) >= 1, "_log_drain outer try has no except handlers"


def test_log_drain_except_handler_does_not_swallow() -> None:
    """Outer except handler body MUST NOT be just `pass` — must emit observability signal."""
    source = PIPELINE_PATH.read_text(encoding="utf-8")
    func = _find_log_drain_function(source)
    while_node = next(n for n in ast.walk(func) if isinstance(n, ast.While))
    outer_try = while_node.body[0]
    for handler in outer_try.handlers:
        # except body MUST contain at least one non-Pass statement
        non_pass_statements = [s for s in handler.body if not isinstance(s, ast.Pass)]
        assert len(non_pass_statements) >= 1, (
            "_log_drain outer except handler is pure pass — violates non-swallow contract"
        )


def test_log_drain_except_handler_emits_to_stderr() -> None:
    """Outer except handler MUST contain _sys.__stderr__ substring (stderr bypass)."""
    source = PIPELINE_PATH.read_text(encoding="utf-8")
    func = _find_log_drain_function(source)
    while_node = next(n for n in ast.walk(func) if isinstance(n, ast.While))
    outer_try = while_node.body[0]
    handler_source_chunks = []
    for handler in outer_try.handlers:
        handler_source_chunks.append(ast.unparse(handler))
    handler_source = " ".join(handler_source_chunks)
    assert "_sys.__stderr__" in handler_source or "sys.__stderr__" in handler_source, (
        "_log_drain outer except handler must emit to sys.__stderr__ "
        "(direct bypass; not via _Tee/_log_q infinite loop)"
    )


# Self-test forward (detector catches synthetic violation)
def test_self_test_forward_pure_pass_detection() -> None:
    """Self-test: synthetic FunctionDef with except: pass body fails the non-swallow check."""
    synthetic_source = """
def _log_drain():
    while True:
        try:
            x = 1
        except Exception:
            pass
"""
    tree = ast.parse(synthetic_source)
    func = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef))
    while_node = next(n for n in ast.walk(func) if isinstance(n, ast.While))
    outer_try = while_node.body[0]
    for handler in outer_try.handlers:
        non_pass_statements = [s for s in handler.body if not isinstance(s, ast.Pass)]
        # Synthetic violation produces 0 non-pass statements
        assert len(non_pass_statements) == 0


# Self-test inverse (detector passes correct shape)
def test_self_test_inverse_correct_shape_passes() -> None:
    """Self-test: synthetic FunctionDef with proper non-swallow + stderr emit passes."""
    synthetic_source = """
def _log_drain():
    while True:
        try:
            x = 1
        except Exception as e:
            import sys as _sys
            _sys.__stderr__.write('error\\n')
"""
    tree = ast.parse(synthetic_source)
    func = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef))
    while_node = next(n for n in ast.walk(func) if isinstance(n, ast.While))
    outer_try = while_node.body[0]
    handler = outer_try.handlers[0]
    non_pass = [s for s in handler.body if not isinstance(s, ast.Pass)]
    assert len(non_pass) >= 1
    assert "_sys.__stderr__" in ast.unparse(handler)
```

### D4 — MF9 `_persistent` lock extension to `**_persistent` SPREAD read

**Scope**: `core/state.py:65` (single-line edit + 4-line lock-snapshot block before line 55 state-dict construction).

**Code change**:

```python
def write(
    status: str = "idle",
    current_person: Optional[str] = None,
    current_person_id: Optional[str] = None,
    visible_people: list = None,
    mode: str = "watching",
    message: str = ""
):
    """Write current pipeline state to state file."""
    # P0.B4 D4 (Bundle 4 observability+concurrency) — extends P0.B5 D4 writer-side lock
    # to the read-side spread for GIL-free Python 3.13+ --disable-gil forward-compat.
    # Lock held ONLY for shallow dict() copy; released BEFORE the file I/O to avoid
    # contention with concurrent set_persistent writers.
    with _persistent_lock:
        _persistent_snapshot = dict(_persistent)
    state = {
        "status":            status,
        "current_person":    current_person,
        "current_person_id": current_person_id,
        "visible_people":    visible_people or [],
        "mode":              mode,
        "message":           message,
        # WALLCLOCK: cross-process IPC
        "updated_at":        time.time(),
        "online":            True,
        **_persistent_snapshot,
    }
    # ... atomic file write unchanged ...
```

**Critical design** (per Q2 (a) RATIFIED):
- Lock held ONLY for shallow `dict(_persistent)` copy
- Lock released BEFORE file I/O to avoid contention with `set_persistent` writers
- Same shape as P0.B5 D4 atomic-replace pattern

### D5 — MF9 AST invariant: `_persistent` accessed only under lock

**New test file**: `tests/test_persistent_lock_invariant.py`

**Detector logic** (file-scoped to `core/state.py`):

```python
"""Bundle 4 D5 — AST invariant: every _persistent access in core/state.py is either
(a) module-level declaration OR (b) under `with _persistent_lock:` block.

File-scoped to core/state.py production. Test files unrestricted per Q3 RATIFIED.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

import ast
import pathlib


STATE_PATH = pathlib.Path(__file__).parent.parent / "core" / "state.py"


def _is_inside_lock_with_block(node: ast.AST, source_tree: ast.Module) -> bool:
    """Return True if node is descendant of an ast.With block whose context_expr is _persistent_lock."""
    # Walk parent chain
    for parent in ast.walk(source_tree):
        if isinstance(parent, ast.With):
            for item in parent.items:
                if (
                    isinstance(item.context_expr, ast.Name)
                    and item.context_expr.id == "_persistent_lock"
                ):
                    # Check if `node` is a descendant of this With block
                    for desc in ast.walk(parent):
                        if desc is node:
                            return True
    return False


def _is_module_level(node: ast.AST, source_tree: ast.Module) -> bool:
    """Return True if node is a direct child of module-level body."""
    for top_stmt in source_tree.body:
        if hasattr(top_stmt, "targets"):
            for desc in ast.walk(top_stmt):
                if desc is node:
                    return True
        elif top_stmt is node:
            return True
    return False


def test_all_persistent_loads_under_lock_or_module_level() -> None:
    """Every _persistent Name(Load) OR DictUnpacking spread must be under lock OR module-level decl."""
    source = STATE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    violations = []
    for node in ast.walk(tree):
        # Match `_persistent` Name nodes
        if isinstance(node, ast.Name) and node.id == "_persistent":
            if isinstance(node.ctx, ast.Load):
                if not (_is_inside_lock_with_block(node, tree) or _is_module_level(node, tree)):
                    violations.append((getattr(node, "lineno", "?"), "_persistent Load"))
            elif isinstance(node.ctx, ast.Store):
                if not (_is_inside_lock_with_block(node, tree) or _is_module_level(node, tree)):
                    violations.append((getattr(node, "lineno", "?"), "_persistent Store"))
        # Match `**_persistent` DictUnpacking spread (ast.keyword with arg=None)
        if isinstance(node, ast.keyword) and node.arg is None:
            if isinstance(node.value, ast.Name) and node.value.id == "_persistent":
                if not (_is_inside_lock_with_block(node, tree) or _is_module_level(node, tree)):
                    violations.append((getattr(node, "lineno", "?"), "_persistent SPREAD"))

    assert not violations, (
        f"Bundle 4 D5 violations in core/state.py: {violations}. "
        "All _persistent access must be under `with _persistent_lock:` block OR module-level declaration."
    )


def test_self_test_forward_unguarded_load_detection() -> None:
    """Self-test: synthetic unguarded _persistent Load fires the detector."""
    synthetic_source = """
import threading
_persistent = {}
_persistent_lock = threading.Lock()

def bad_read():
    return _persistent.get('foo')  # unguarded Load — should fire
"""
    tree = ast.parse(synthetic_source)
    found_unguarded = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "_persistent" and isinstance(node.ctx, ast.Load):
            # Check if inside `with _persistent_lock:` block
            inside_lock = False
            for parent in ast.walk(tree):
                if isinstance(parent, ast.With):
                    for item in parent.items:
                        if isinstance(item.context_expr, ast.Name) and item.context_expr.id == "_persistent_lock":
                            for desc in ast.walk(parent):
                                if desc is node:
                                    inside_lock = True
            # Check if module-level
            is_module_level = False
            for top_stmt in tree.body:
                if top_stmt is node or (hasattr(top_stmt, "targets") and any(
                    isinstance(t, ast.Name) and t.id == "_persistent" for t in top_stmt.targets
                )):
                    if top_stmt is node:
                        is_module_level = True
            if not inside_lock and not is_module_level:
                found_unguarded = True
                break
    assert found_unguarded, "Self-test forward: synthetic violation should be detected"


def test_self_test_inverse_under_lock_passes() -> None:
    """Self-test: synthetic _persistent under lock passes the detector."""
    synthetic_source = """
import threading
_persistent = {}
_persistent_lock = threading.Lock()

def good_read():
    with _persistent_lock:
        snap = dict(_persistent)  # Load under lock — passes
    return snap
"""
    tree = ast.parse(synthetic_source)
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "_persistent" and isinstance(node.ctx, ast.Load):
            # Verify it's under lock
            for parent in ast.walk(tree):
                if isinstance(parent, ast.With):
                    for item in parent.items:
                        if isinstance(item.context_expr, ast.Name) and item.context_expr.id == "_persistent_lock":
                            for desc in ast.walk(parent):
                                if desc is node:
                                    break
                            else:
                                violations.append((getattr(node, "lineno", "?"), "Load"))
    # Synthetic correct-shape should produce 0 violations
    assert len(violations) == 0
```

---

## §5 A1-A5 anchor tests + 5/5 deliberate-regression confirmations

### §5.1 Anchor test mapping

- A1 (D1 outer-loop wrap + observability state) → source-inspection on pipeline.py `_log_drain` + 3 module-level vars (1 collection)
- A2 (D2 HealthSnapshot + alert) → source-inspection on `core/health.py` + `core/config.py` (~9 collections)
- A3 (D3 single-function AST invariant) → `tests/test_log_drain_observability_invariant.py` (~3 collections including self-tests)
- A4 (D4 lock-snapshot block) → source-inspection on `core/state.py:65` lock-snapshot (1 collection)
- A5 (D5 file-scoped AST invariant) → `tests/test_persistent_lock_invariant.py` (~3 collections including self-tests)

**Total ~17 pytest collections** per Plan v1 §3.1 projection.

### §5.2 5/5 deliberate-regression confirmations (per `### Induction-surfaces-invariant-gaps`)

Per Bundle 3 closure-audit Q1 (b) lesson: synthetic-injection harness must fire correctly for ALL 5 scenarios.

After Phase 4 implementation:
1. **(a)** Strip the outer-loop try/except wrap from `_log_drain` → A3 fires (no outer try/except detected); revert
2. **(b)** Replace outer except body with bare `pass` (swallow) → A3 fires (non-swallow contract violated); revert
3. **(c)** Strip `_sys.__stderr__` substring from outer except handler → A3 fires (stderr-emit contract violated); revert
4. **(d)** Remove `with _persistent_lock:` wrap from `core/state.py:65` (or revert to bare `**_persistent`) → A5 fires (unguarded Load); revert
5. **(e)** Strip the `Log drain thread degraded` substring from `format_health_alerts` → A2 fires (alert substring missing); revert

Document each regression result in closure narrative under "5/5 deliberate-regression confirmations passed cleanly".

---

## §6 Closure narrative requirements

When Phase 4 complete + all 5 anchors green + 5/5 regressions passed cleanly:

1. **Append closure entry** to CLAUDE.md banner using Plan v1 §6 paste template (substitute actual closure date + closure-actual anchor count)
2. **Update test count** at top of CLAUDE.md banner (~3734 + ~17 new collections = ~3751)
3. **Update `to_be_checked.md`** with Bundle 4 entry (deferred-canary strategy 38th application)
4. **Path C grep-verify** at closure-narrative drafting:
   - Production code surfaces (pipeline.py `_log_drain` + 3 module-level vars + `core/health.py` HealthSnapshot fields + `core/config.py` LOG_DRAIN_STALENESS_SECS + `core/state.py:65` lock-snapshot block)
   - 2 NEW test files landed (`tests/test_log_drain_observability_invariant.py` + `tests/test_persistent_lock_invariant.py`)
   - CLAUDE.md banner Bundle 4 entry
   - `to_be_checked.md` Bundle 4 entry via Python `File.read_text` fresh-disk verify
5. **Forward closure-audit findings to auditor** for explicit ratification BEFORE declaring Bundle 4 CLOSED (9th-cycle routinization)
6. **Enumerate 11-discipline preventive convergence** for closure-audit ratification (preserve Plan v1 §5.4 enumeration)

### §6.1 Major milestone events to lock at closure

Per auditor Plan v1 verdict §7:
- **20th OPTIONAL-Plan-v2 proof case LOCKS** (pattern-broken streak rebuilds after Bundle 1+2+3 escalation)
- **`Multi-axis-precision-pattern-confirmed-by-3-consecutive-blocked-bundles` STAYS at 2** (NOT 3; sub-rule elevation candidacy NOT TRIGGERED; preserved for Bundle 5 adjudication)
- **`Doctrine-prediction-precision-improving-over-arc` 13th consecutive 0%-streak** (if closure-actual = 5 exact)
- **11-discipline preventive convergence trajectory maintained** at sustained 11-floor (Bundle 3 [11] → Bundle 4 [11])
- **4-part Pass-2 grep rule 2nd instance locked at Plan v1 §11** (1 more for formalization at 3-instance threshold)

### §6.2 Architect-side closure-audit verdict-forwarding template

```markdown
Bundle 4 Phase 4 implementation COMPLETE 2026-05-2X. Standing by for auditor closure-audit ratification BEFORE declaring CLOSED.

Phase 4 outcomes:
- 5/5 anchors A1-A5 GREEN; ~17 pytest collections via A2+A3+A5 parametrize fan-outs
- 5/5 deliberate-regression confirmations passed cleanly via synthetic-injection harness
- Suite: ~3734 → ~3751 passing (+17 collections)
- §0 NEW commitment Pass-3 grep dual-axis verification: {clean/drift?}
- 2 NEW test files landed + 1 mechanical scope (no migration scripts this cycle)
- 11-discipline preventive convergence preserved at closure

Major milestone events:
- 20th OPTIONAL-Plan-v2 proof case LOCKS (pattern-broken streak rebuilds)
- Multi-axis-precision-pattern STAYS at 2 (no 3rd instance confirmation)
- 13th consecutive 0%-streak conditional on closure-actual = 5 exact
- 4-part Pass-2 grep rule 2nd instance locked

Doctrine bumps banked at Plan v1 verdict (locked):
- Per-artifact-arithmetic-drift-survives-grep-baseline 18 → 19
- NEW Phase-0-spec-text-BEFORE-code-doesnt-match-production 1st instance
- Multi-axis-precision-pattern STAYS at 2
- ### Pass-2-grep-auditor-verified-before-Plan-v1-approval 11 → 12 (CAUGHT-REAL-GAP)
- ### Zero-precision-items-at-auditor-review 41 → 42 (Plan v1 CLEAN — pattern-broken streak rebuilds)
- OPTIONAL-Plan-v2 sub-rule track record 19 → 20 LOCKS at closure
- NEW Spec-text-baseline-representation-integrity-vs-production-current-state 1st instance

Closure-actual: {X} anchors; {ON-TARGET / SLIGHT-DRIFT / FALSIFICATION} per Q5 LOCK band.

Conditional bumps (closure-actual dependent):
- Doctrine-prediction-precision-improving-over-arc 12 → 13 IF closure-actual = 5
- ### Phase-0-granular-decomposition-enables-accurate-estimates 33 → 34 IF closure-actual ∈ [4.25, 5.75]

Auditor ratification requested.
```

---

## §7 Closure-projection Q5 reading

Q5 LOCK at mid 5 anchors. NARROW band [4.25, 5.75]. Falsification: ≤3 OR ≥8.

Per `Explicit-closure-honest-count-commitment`:
- IF closure-actual = 5 exact → `Doctrine-prediction-precision-improving-over-arc` 13th-streak banks
- IF closure-actual ∈ {4, 6} → ON-TARGET via SLIGHT-DRIFT within ±15%; doctrine bumps; streak interrupted
- IF closure-actual ∈ {3, 7} → SLIGHT-DRIFT within ±30%; doctrine HOLDS at 33; streak interrupted
- IF closure-actual ≤2 OR ≥8 → FALSIFICATION-WATCH activates

Anchor enumeration: A1 (D1) + A2 (D2) + A3 (D3) + A4 (D4) + A5 (D5). Total = 5 logical anchors UNCHANGED across Phase 0 + Plan v1.

**Phase 4 in-cycle strengthening caveat** (Bundle 1+2+3 pattern; Bundle 3 = 9th `### Induction-surfaces-invariant-gaps` family event): if Phase 4 surfaces detector gap requiring same-cycle strengthening, STRENGTHEN in same cycle + bank as 10th family event. Auditor ratifies via closure-audit verdict.

---

## §8 Standing by

Phase 4 ready to execute. Implementation order: §3 Pass-3 grep dual-axis → D1 outer-loop wrap + observability vars → D2 HealthSnapshot + alert → D3 AST invariant → D4 lock-snapshot block → D5 AST invariant → 5/5 regressions → closure-audit forwarding.

On Phase 4 completion: forward closure-audit findings + 11-discipline preventive convergence enumeration for explicit auditor ratification per 9th-cycle routinization discipline.

---

**Filed**: 2026-05-28
**Architect**: Claude
**For**: Developer Phase 4 implementation
**Prior artifact**: `tests/pre_p1_bundle4_observability_concurrency_plan_v1.md` (RATIFIED CLEAN at auditor Plan v1 verdict 2026-05-28; OPTIONAL-Plan-v2 path ACTIVATED; 20th proof case LOCKS at Bundle 4 closure pending Q5 LOCK adjudication)
