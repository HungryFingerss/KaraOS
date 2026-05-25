# P0.R12-R15 — Resilience Hygiene Bundle (Plan v1)

**Date**: 2026-05-25
**Author**: architect (Claude)
**Cycle shape**: SMALL-MEDIUM band, 3-artifact OPTIONAL-Plan-v2 path projected
**Phase 0 verdict**: ACCEPTED with 0 BLOCKING PIs + 0 non-blocking observations (cleanest verdict surface in recent cycle batch)
**Q1-Q9**: all 9 RATIFIED at Phase 0 verdict
**Anchor count**: 9 RATIFIED at exact mid INCLUSIVE band [7.65, 10.35]

---

## §0 Phase 0 absorption + procedural commitments

Phase 0 audit ACCEPTED 2026-05-25. 7 auditor recommendations absorbed:

**(1) §5 explicit step enumeration** per P0.R11 Observation 1 absorption pattern — Plan v1 §5 below provides 7 explicit mutation steps with independence verification.

**(2) LINE-REF-DRIFT preventive re-verification at Plan v1 refresh** — architect performed fresh grep-tool re-verification of every line ref in §1 at Plan v1 drafting time. **No drift caught** (clean refresh). All Phase 0 line refs hold: `CAMERA_INDEX=0` at `core/config.py:16` + `CONVERSATION_ARCHIVE_AFTER_DAYS=30` at `core/config.py:1297` + `archive_old_conversation_log` at `core/db.py:301` + `_archive_db_path` at `core/db.py:267` + `_init_conversation_archive` at `core/db.py:272` + `_archive_terminal_output` at `pipeline.py:34` + `_archived_log` at `pipeline.py:81` + `_LOG_FILE` at `pipeline.py:83` + `time.sleep` sync at `core/vision.py:451 + 543` + `await asyncio.sleep` at `core/vision.py:470` + `cv2.VideoCapture` at `core/vision.py:419 + 433` + `_dream_loop` at `pipeline.py:3405` + existing `archive_old_conversation_log` call at `pipeline.py:3501` + P0.R11 D4 crash log prune block at `pipeline.py:3516+`. **3rd consecutive LINE-REF-DRIFT preventive application** (P0.R10 Phase 0 + Plan v1 + P0.R12-R15 Plan v1).

**(3) A7 + A8 AST helper functions explicitly spec'd** with test coverage — §3 below details `_get_call_name` + `_is_inside_class_method` helper signatures + their own test coverage anchors.

**(4) A5 size-cap behavioral test fast-path scope** — auditor flagged writing 100MB test data is expensive. Plan v1 §3 A5 spec uses monkeypatched `_LOG_PATH.stat()` returning fake `st_size` value to simulate over-cap without I/O cost. Test runs <0.1s.

**(5) §6 cross-path memory-file work scheduled** — NO new memory files projected. IF any introduced at closure, cross-path discipline applied per locked operational rule (P0.R9 + P0.R10 precedent). DEFERRED-CANARY entry verification via PowerShell fresh-disk read mechanism (P0.R10 STALE-CACHED-VERIFICATION lesson).

**(6) §9 closure-audit verdict forwarding commitment** — already locked at Phase 0 §0; reaffirmed at §9 below. P0.R12-R15 closure-audit will be forwarded to auditor for explicit ratification before bundle declared CLOSED. 2nd cycle to honor §9 procedural integrity discipline post-P0.R10.

**(7) P0.R arc completion milestone narrative at closure** — if bundle clears clean, closes the LAST 4 outstanding P0.R items → resilience-track arc COMPLETE (14-cycle arc: R1 + R2 + R3 + R4 + R5 + R6.* + R8 + R9 + R10 + R11 + R12 + R13 + R14 + R15). Auditor flagged as **bank-worthy architectural anchor**. Closure narrative will explicitly document the milestone + bank `### Resilience-track-arc-completion` candidate per Phase 0 §8.

**Q1-Q9 ratifications applied to §2 D-decisions**: all 9 architect leans RATIFIED at Phase 0 verdict. §2 D-decision specifications LOCKED at architect's lean shapes.

---

## §1 Grep findings (Pass-2 — Plan v1 refresh)

### §1.1 P0.R12 — Conversation_log_archive retention surfaces (REFRESHED — no drift)

| # | Surface | File:Line | Current behavior |
|---|---|---|---|
| 1 | `CONVERSATION_ARCHIVE_AFTER_DAYS = 30` | `core/config.py:1297` | Rows older than 30 days move from `conversation_log` → archive DB |
| 2 | `CONVERSATION_ARCHIVE_ENABLED` flag | `core/config.py` (verify at Phase 5) | Existing guard for archival path |
| 3 | `FaceDB.archive_old_conversation_log(cutoff_days, now)` | `core/db.py:301-357` | ATTACH DATABASE + INSERT + DELETE under `BEGIN EXCLUSIVE`; P0.9.1 Imp-2 tightened rollback |
| 4 | `FaceDB._archive_db_path()` | `core/db.py:267-270` | Returns `{db_stem}_conversation_archive.db` |
| 5 | `FaceDB._init_conversation_archive()` | `core/db.py:272+` | Creates archive DB with same schema as conversation_log |
| 6 | Existing dream-loop call site | `pipeline.py:3501` | `await loop.run_in_executor(None, db.archive_old_conversation_log)` inside `if config.CONVERSATION_ARCHIVE_ENABLED:` guard |
| 7 | Archive DB read paths | `core/db.py:1329 + 1612` | `load_conversation_history` + `search_conversation` UNION-merge across main + archive |

### §1.2 P0.R13 — terminal_output.md surfaces (REFRESHED — no drift)

| # | Surface | File:Line | Current behavior |
|---|---|---|---|
| 1 | `_archive_terminal_output(log_path)` | `pipeline.py:34-78` | Renames existing `terminal_output.md` → `terminal_output_YYYY-MM-DD_HHMMSS.md` at startup; mtime-based stamp; collision-safe |
| 2 | `_archived_log = _archive_terminal_output()` | `pipeline.py:81` | Called once at module import |
| 3 | `_LOG_FILE = open(_LOG_PATH, "w", encoding="utf-8", buffering=1)` | `pipeline.py:83-88` | Fresh per session (P1.5 design); prior session's content in timestamped archive |
| 4 | `HEALTH_LOG_INTERVAL_SECS = 300` | `core/config.py:1592` | Disk monitor poll cycle = 5 min |
| 5 | Disk monitor poll loop | `core/disk_monitor.py` + `pipeline.py::_health_log_loop` | Runs every `HEALTH_LOG_INTERVAL_SECS` |

### §1.3 P0.R14 — Camera index references (REFRESHED — no drift)

| # | Surface | File:Line | Current behavior |
|---|---|---|---|
| 1 | `CAMERA_INDEX = 0` config | `core/config.py:16` | Operator-tunable |
| 2 | `Camera(CAMERA_INDEX)` instantiation | `pipeline.py:6569` | Reads from config ✓ |
| 3 | `cv2.VideoCapture(index, backend)` (init path) | `core/vision.py:419` | `index` param passed through cleanly |
| 4 | `cv2.VideoCapture(self._index, self._backend)` (reconnect path) | `core/vision.py:433` | Uses stored `_index` from construction |

### §1.4 P0.R15 — time.sleep references (REFRESHED — no drift)

| # | Surface | File:Line | Current behavior |
|---|---|---|---|
| 1 | `time.sleep(interval)` in `Camera.capture_frames` | `core/vision.py:451` | SYNC `def`, explicitly "for use outside async contexts" |
| 2 | `await asyncio.sleep(interval)` in `Camera.capture_frames_async` | `core/vision.py:470` | ASYNC counterpart |
| 3 | `time.sleep(interval)` in `Camera.capture_frames_with_preview` | `core/vision.py:543` | SYNC `def`, GUI preview path for enrollment |
| 4 | Test-only `time.sleep(...)` | `tests/*.py` | Multiple test files — OUT-OF-SCOPE per Q6 (a) RATIFIED |

### §1.5 Cross-spec interactions (unchanged from Phase 0; verified clean)

| Spec | Interaction | Status |
|---|---|---|
| Wave 6 Item 21 | `conversation_log` archival mechanism | EXTENDS — D1 adds retention layer |
| Wave 5 Item 20 | Disk monitor poll cadence + threshold pattern | EXTENDS — D2 piggybacks on disk monitor cycle |
| P0.0.7 | `_archive_terminal_output` startup hook | EXTENDS — D2 adds in-session size-cap + archive retention |
| P0.9.1 Imp-1 | `isolation_level="IMMEDIATE"` discipline | LOAD-BEARING — D1 prune follows same pattern |
| P0.9.1 Imp-2 | Tightened S65 rollback pattern | LOAD-BEARING — D1 prune SQL must use explicit-error-classification rollback |
| P0.4 silent-except policy | `# CLEANUP:` annotation discipline | LOAD-BEARING — D1 + D2 swallow sites all annotated |
| P0.R10 Q3 (a) | None-return contract | NOT APPLICABLE — these are admin/janitor paths, not user-facing |
| P0.R11 D4 | Crash log prune block at `pipeline.py:3516+` | PRECEDENT — D1 + D2 prune blocks mirror this dream-loop wiring pattern |

---

## §2 D-decisions LOCKED (per Q1-Q9 ratifications)

### D1 — Conversation_log_archive retention (P0.R12; Q1 RATIFIED + Q8 RATIFIED)

**`core/config.py`** — new constant after `CONVERSATION_ARCHIVE_AFTER_DAYS` at line 1297:

```python
# P0.R12 — conversation_log_archive retention. Archive DB at
# `{db_stem}_conversation_archive.db` accumulates rows after Wave 6 Item 21
# moves them from main conversation_log. Without retention, archive grows
# indefinitely. 1-year default per Q1 (a) RATIFIED — operator-tunable.
CONVERSATION_ARCHIVE_RETENTION_DAYS = 365
```

**`core/db.py`** — new `FaceDB.prune_old_archive_conversation_log` method after `archive_old_conversation_log` (line 357):

```python
def prune_old_archive_conversation_log(
    self, retention_days: "int | None" = None, now: "float | None" = None
) -> int:
    """P0.R12 D1 — delete rows from conversation_log_archive table older than
    retention_days. Returns count deleted.

    Mirrors archive_old_conversation_log's ATTACH DATABASE + BEGIN EXCLUSIVE +
    P0.9.1 Imp-2 rollback discipline. Different polarity: that method MOVES
    from main → archive; this method DELETES from archive.

    Pruning at retention_days=365 keeps archive bounded to ~1 year of history.
    Operator-tunable via config (Q1 (a) RATIFIED).
    """
    if retention_days is None:
        retention_days = CONVERSATION_ARCHIVE_RETENTION_DAYS
    if now is None:
        now = time.time()
    cutoff_ts = now - retention_days * 86400

    archive_path = self._archive_db_path()
    if not archive_path.exists():
        return 0

    self._conn.execute("ATTACH DATABASE ? AS archive", (str(archive_path),))
    try:
        n = self._conn.execute(
            "SELECT COUNT(*) FROM archive.conversation_log WHERE ts < ?",
            (cutoff_ts,),
        ).fetchone()[0]
        if n == 0:
            return 0
        self._conn.execute("BEGIN EXCLUSIVE")
        self._conn.execute(
            "DELETE FROM archive.conversation_log WHERE ts < ?",
            (cutoff_ts,),
        )
        self._conn.execute("COMMIT")
    except Exception:
        try:
            self._conn.execute("ROLLBACK")
        except sqlite3.OperationalError as _rbe:
            if "no transaction is active" not in str(_rbe).lower():
                print(f"[FaceDB] archive-prune rollback failed: {_rbe!r}")
                raise
            # else: # RACE: S65 — known race, suppress per P0.9.1 Imp-2
        raise
    finally:
        try:
            self._conn.execute("DETACH DATABASE archive")
        except Exception:
            pass  # CLEANUP: DETACH raises if ATTACH failed earlier
    return n
```

**`pipeline.py::_dream_loop`** — wire after existing `archive_old_conversation_log` call at line 3506 (inside the same `if config.CONVERSATION_ARCHIVE_ENABLED:` guard for consistency):

```python
# P0.R12 D1 — prune old archive rows after archival
if config.CONVERSATION_ARCHIVE_ENABLED:
    try:
        n_pruned = await loop.run_in_executor(
            None, db.prune_old_archive_conversation_log,
        )
        if n_pruned:
            print(
                f"[Dream] Archive-prune: {n_pruned} conversation_log row(s) "
                f"deleted from archive (older than {config.CONVERSATION_ARCHIVE_RETENTION_DAYS}d)"
            )
    except Exception as _e:
        print(f"[Dream] archive prune failed: {_e!r}")  # CLEANUP: best-effort
```

### D2 — terminal_output.md size cap + rotation (P0.R13; Q2 + Q3 + Q4 RATIFIED)

**`core/config.py`** — 2 new constants:

```python
# P0.R13 — terminal_output.md size cap + archive retention.
# `_check_terminal_output_size_cap` rotates the file when size exceeds cap;
# `_prune_old_terminal_archives` removes archive files older than retention.
# Q2 (a) RATIFIED: 100 MB cap is generous; rotation is non-destructive.
# Q3 (a) RATIFIED: 30 day archive retention matches canary-feedback window.
TERMINAL_OUTPUT_SIZE_CAP_MB            = 100
TERMINAL_OUTPUT_ARCHIVE_RETENTION_DAYS = 30
```

**`pipeline.py`** — 2 new helpers (placed near `_archive_terminal_output` at line 34):

```python
def _check_terminal_output_size_cap(log_path: _pathlib.Path = _LOG_PATH) -> bool:
    """P0.R13 D2 — if log_path > TERMINAL_OUTPUT_SIZE_CAP_MB, rotate it.

    Q2 (a) RATIFIED 100 MB default; Q4 (a) RATIFIED disk-monitor-poll cadence.

    Closes current log, renames to timestamped archive (matches startup
    archive shape), opens fresh log file. Returns True if rotation fired.

    Called from disk monitor poll cadence (~5 min) so size check is amortized
    over session, not per-print.
    """
    global _LOG_FILE
    try:
        if not log_path.exists():
            return False
        size_mb = log_path.stat().st_size / (1024 * 1024)
        from core.config import TERMINAL_OUTPUT_SIZE_CAP_MB  # noqa: PLC0415
        if size_mb < TERMINAL_OUTPUT_SIZE_CAP_MB:
            return False
        # Close current file before rename (Windows file-lock semantics)
        try:
            _LOG_FILE.flush()
            _LOG_FILE.close()
        except Exception:
            pass  # CLEANUP: best-effort
        # Rotate via same archive shape as startup
        _archive_terminal_output(log_path)
        _LOG_FILE = open(log_path, "w", encoding="utf-8", buffering=1)
        print(
            f"[Pipeline] terminal_output.md rotated at {size_mb:.1f}MB "
            f"(cap={TERMINAL_OUTPUT_SIZE_CAP_MB}MB)",
            flush=True,
        )
        return True
    except Exception as e:
        print(f"[Pipeline] terminal_output rotation failed: {e!r}", flush=True)
        return False


def _prune_old_terminal_archives(
    retention_days: "int | None" = None,
    log_dir: "_pathlib.Path | None" = None,
) -> int:
    """P0.R13 D2 — delete terminal_output_*.md archive files older than
    retention_days. Returns count deleted.

    Q3 (a) RATIFIED 30 day archive retention default.

    Pattern: terminal_output_YYYY-MM-DD_HHMMSS*.md (matches
    `_archive_terminal_output` naming scheme).
    """
    if retention_days is None:
        from core.config import TERMINAL_OUTPUT_ARCHIVE_RETENTION_DAYS  # noqa: PLC0415
        retention_days = TERMINAL_OUTPUT_ARCHIVE_RETENTION_DAYS
    if log_dir is None:
        log_dir = _LOG_PATH.parent
    cutoff_ts = time.time() - retention_days * 86400
    deleted = 0
    try:
        for path in log_dir.glob("terminal_output_*.md"):
            try:
                if path.stat().st_mtime < cutoff_ts:
                    path.unlink()
                    deleted += 1
            except Exception:
                pass  # CLEANUP: skip individual archive prune failures
    except Exception:
        pass  # CLEANUP: glob failure
    return deleted
```

**Wire into disk monitor poll** in `pipeline.py::_health_log_loop` (or `_dream_loop` if cleaner) — Q4 (a) RATIFIED disk-monitor cadence:

```python
# P0.R13 D2 — terminal_output.md size cap + archive retention
try:
    _check_terminal_output_size_cap()
    _prune_old_terminal_archives()
except Exception as e:
    print(f"[Pipeline] terminal output hygiene failed: {e!r}")  # CLEANUP: best-effort
```

### D3 — Camera index structural invariant (P0.R14; Q5 RATIFIED)

**`tests/test_p0_r12_r15_resilience_hygiene.py`** — AST scan anchor with explicit AST helpers:

```python
def _get_call_name(node: ast.expr) -> "str | None":
    """Extract function name from ast.Call.func node.

    Supports: simple Name (e.g. `Camera`), Attribute (e.g. `cv2.VideoCapture`).
    Returns None for complex expressions (lambdas, subscripts, etc).
    """
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _get_call_name(node.value)
        if prefix:
            return f"{prefix}.{node.attr}"
        return node.attr
    return None


def _is_inside_class_method(
    target_node: ast.AST, tree: ast.Module, class_name: str
) -> bool:
    """Check if target_node is inside a method of the named class.

    Walks the tree, finds ClassDef nodes matching class_name, checks if
    target_node is nested inside any of its methods. Returns True if found.

    Used by D3 invariant to allow `cv2.VideoCapture(self._index, ...)` inside
    Camera class methods (where `self._index` IS the config-driven value).
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for child in ast.walk(node):
                if child is target_node:
                    return True
    return False


def test_p0_r14_no_hardcoded_camera_index():
    """P0.R14 D3 — verify no hardcoded camera index in production code.

    Q5 (a) RATIFIED: scan `core/*.py` + `pipeline.py` only. CLI scripts
    (enroll.py, delete_person.py) may legitimately hardcode for one-off ops.

    Camera() and cv2.VideoCapture() must take index from CAMERA_INDEX config
    (or other Name reference), not from literal int Constant.

    Allowed inside Camera class methods (self._index uses stored config value).
    """
    import ast
    files_to_scan = ["pipeline.py"] + sorted(str(p) for p in Path("core").glob("*.py"))
    violations = []
    for filename in files_to_scan:
        with open(filename, encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func_name = _get_call_name(node.func)
                if func_name in ("Camera", "cv2.VideoCapture", "VideoCapture"):
                    if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, int):
                        # Allow inside Camera class methods (uses self._index)
                        if not _is_inside_class_method(node, tree, "Camera"):
                            violations.append(f"{filename}:{node.lineno}")
    assert not violations, f"Hardcoded camera index found: {violations}"
```

### D4 — time.sleep in async invariant (P0.R15; Q6 RATIFIED)

```python
def test_p0_r15_no_time_sleep_in_async_bodies():
    """P0.R15 D4 — verify no `time.sleep(...)` inside async def bodies.

    Q6 (a) RATIFIED: async-only invariant scope. Sync def bodies allowed
    (capture_frames + capture_frames_with_preview explicitly). Scans
    `core/*.py` + `pipeline.py` (production only).

    Async loop must use `await asyncio.sleep(...)`. Catches future regression
    where someone adds `time.sleep` inside an async function.
    """
    import ast
    files_to_scan = ["pipeline.py"] + sorted(str(p) for p in Path("core").glob("*.py"))
    violations = []
    for filename in files_to_scan:
        with open(filename, encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef):
                for inner in ast.walk(node):
                    if isinstance(inner, ast.Call):
                        func_name = _get_call_name(inner.func)
                        if func_name == "time.sleep":
                            violations.append(
                                f"{filename}:{inner.lineno} (inside async {node.name})"
                            )
    assert not violations, f"time.sleep inside async def: {violations}"
```

---

## §3 Anchor enumeration (Q5 LOCKED = 9 anchors)

NEW `tests/test_p0_r12_r15_resilience_hygiene.py` with 9 anchors + 2 AST helper test coverage tests bundled inline:

| # | Anchor name | Surface | Type |
|---|---|---|---|
| A1 | `test_p0_r12_d1_prune_archive_method_exists` | `core/db.py` | SOURCE — verify `FaceDB.prune_old_archive_conversation_log` method present + signature `(self, retention_days, now)` |
| A2 | `test_p0_r12_d1_prune_archive_removes_old_rows` | `core/db.py` | **BEHAVIORAL** — seed archive DB via `archive_old_conversation_log` with rows at varied ts; call `prune_old_archive_conversation_log(retention_days=30)`; verify rows older than 30d deleted, recent preserved, return count matches actual deletion |
| A3 | `test_p0_r12_d1_dream_loop_calls_prune` | `pipeline.py` | SOURCE — AST scan `_dream_loop` body for `db.prune_old_archive_conversation_log` call inside `config.CONVERSATION_ARCHIVE_ENABLED` guard |
| A4 | `test_p0_r13_d2_size_cap_rotation_helper_exists` | `pipeline.py` | SOURCE — verify `_check_terminal_output_size_cap` + `_prune_old_terminal_archives` module-level functions present + signatures match |
| A5 | `test_p0_r13_d2_size_cap_triggers_rotation_at_threshold` | `pipeline.py` | **BEHAVIORAL (FAST-SCOPED)** — auditor recommendation #4: monkeypatch `_LOG_PATH.stat()` to return synthetic `st_size = (TERMINAL_OUTPUT_SIZE_CAP_MB + 1) * 1024 * 1024`; call `_check_terminal_output_size_cap`; verify returns True + `_archive_terminal_output` was called + new `_LOG_FILE` opened. ALSO verify under-cap case (st_size = 10MB) returns False without rotation. Test runs <0.1s (no actual I/O). |
| A6 | `test_p0_r13_d2_archive_prune_removes_old_files` | `pipeline.py` | **BEHAVIORAL** — seed `terminal_output_*.md` files at known mtimes via `os.utime`; call `_prune_old_terminal_archives(retention_days=30)`; verify old deleted, recent preserved, return count matches actual deletion |
| A7 | `test_p0_r14_d3_no_hardcoded_camera_index` | `core/*.py` + `pipeline.py` | AST SCAN — D3 structural invariant per §2 + uses `_get_call_name` + `_is_inside_class_method` helpers |
| A8 | `test_p0_r15_d4_no_time_sleep_in_async_bodies` | `core/*.py` + `pipeline.py` | AST SCAN — D4 structural invariant per §2 + uses `_get_call_name` helper |
| A9 | `test_p0_r12_r15_config_constants_present` | `core/config.py` | SOURCE — verify 3 constants present with sanity values: `CONVERSATION_ARCHIVE_RETENTION_DAYS == 365` + `TERMINAL_OUTPUT_SIZE_CAP_MB == 100` + `TERMINAL_OUTPUT_ARCHIVE_RETENTION_DAYS == 30` |

**Bundled-inline AST helper test coverage** (auditor recommendation #3 — explicit helper test coverage):

```python
def test_get_call_name_helper():
    """A7+A8 sanity: _get_call_name extracts callable name from ast.Call.func."""
    import ast
    assert _get_call_name(ast.parse("Camera(0)").body[0].value.func) == "Camera"
    assert _get_call_name(ast.parse("cv2.VideoCapture(0)").body[0].value.func) == "cv2.VideoCapture"
    assert _get_call_name(ast.parse("time.sleep(1)").body[0].value.func) == "time.sleep"


def test_is_inside_class_method_helper():
    """A7 sanity: _is_inside_class_method correctly identifies class-internal calls."""
    import ast
    src = '''
class Camera:
    def __init__(self):
        self._index = 0
    def reconnect(self):
        cv2.VideoCapture(self._index)
def standalone():
    cv2.VideoCapture(0)
    '''
    tree = ast.parse(src)
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
    # cv2.VideoCapture(self._index) is inside Camera class
    inside_call = next(c for c in calls if isinstance(c.args[0], ast.Attribute))
    # cv2.VideoCapture(0) is in standalone function (not Camera class)
    outside_call = next(c for c in calls if isinstance(c.args[0], ast.Constant))
    assert _is_inside_class_method(inside_call, tree, "Camera") is True
    assert _is_inside_class_method(outside_call, tree, "Camera") is False
```

**Note**: 2 helper tests are bundled-inline + count toward A7/A8 coverage; they validate that the AST scan logic itself is correct. NOT counted as additional anchors per Q5 LOCKED 9 (helper tests are co-located test infrastructure, not new architectural invariants).

---

## §4 Phase 4 deliberate-regression confirmation matrix

9 reverts (one per anchor) per `### Induction-surfaces-invariant-gaps` discipline:

| # | Revert action | Expected anchor failure |
|---|---|---|
| (a) | Delete `prune_old_archive_conversation_log` method from `core/db.py` | A1 fires (method missing AttributeError) |
| (b) | Replace `prune_old_archive_conversation_log` body with `return 0` | A2 fires (rows not actually deleted; count assertion fails) |
| (c) | Drop `db.prune_old_archive_conversation_log` call from `_dream_loop` | A3 fires (AST scan finds no matching Call inside guard) |
| (d) | Delete `_check_terminal_output_size_cap` from `pipeline.py` | A4 fires (function missing) |
| (e) | Replace `_check_terminal_output_size_cap` body with `return False` unconditionally | A5 fires (over-cap monkeypatched size still doesn't trigger rotation) |
| (f) | Replace `_prune_old_terminal_archives` body with `return 0` | A6 fires (old files not deleted; count mismatch) |
| (g) | Add hardcoded `cv2.VideoCapture(1, cv2.CAP_DSHOW)` to a NEW module-level function in `core/vision.py` (outside Camera class) | A7 fires (D3 invariant catches new hardcoded literal in production code) |
| (h) | Add `time.sleep(0.1)` inside an existing async def in `pipeline.py` (e.g., inside `_dream_loop` body) | A8 fires (D4 invariant catches new async-body violation) |
| (i) | Delete `CONVERSATION_ARCHIVE_RETENTION_DAYS` from `core/config.py` | A9 fires (constant missing) |

All 9 reverts MUST fire correctly + revert cleanly + suite green before closure narrative drafting.

---

## §5 Phase 5 implementation enumeration (explicit 7-step mutation per P0.R11 Observation 1 absorption)

Per auditor's Recommendation #1 + P0.R11 Observation 1 absorption pattern. 4 D-decisions × 2-3 mutation steps each = 7 explicit steps + mutation-step independence verification.

**Step 1 — `core/config.py` D1 + D2 constants (additive, no breakage)**:

- Step 1.1: Add `CONVERSATION_ARCHIVE_RETENTION_DAYS = 365` after `CONVERSATION_ARCHIVE_AFTER_DAYS` at line 1297
- Step 1.2: Add `TERMINAL_OUTPUT_SIZE_CAP_MB = 100` at appropriate location (suggested near `HEALTH_LOG_INTERVAL_SECS` at line 1592 for disk-hygiene grouping)
- Step 1.3: Add `TERMINAL_OUTPUT_ARCHIVE_RETENTION_DAYS = 30` after Step 1.2

**Step 2 — `core/db.py` D1 prune method (additive)**:

- Step 2.1: Add `prune_old_archive_conversation_log(self, retention_days, now)` method after `archive_old_conversation_log` (line 357)
- Step 2.2: Ensure body mirrors `archive_old_conversation_log`'s ATTACH DATABASE + BEGIN EXCLUSIVE + P0.9.1 Imp-2 rollback discipline
- Step 2.3: Verify P0.4 `# CLEANUP:` annotation on the DETACH swallow site

**Step 3 — `pipeline.py` D1 dream-loop wiring**:

- Step 3.1: After existing `db.archive_old_conversation_log` call at line 3501-3506, add the prune call inside the same `if config.CONVERSATION_ARCHIVE_ENABLED:` guard
- Step 3.2: Verify log message format includes retention day count + actual rows deleted
- Step 3.3: Confirm error-swallow site has `# CLEANUP: best-effort` annotation

**Step 4 — `pipeline.py` D2 helpers (additive)**:

- Step 4.1: Add `_check_terminal_output_size_cap(log_path)` function near `_archive_terminal_output` at line 34
- Step 4.2: Add `_prune_old_terminal_archives(retention_days, log_dir)` function after Step 4.1
- Step 4.3: Both functions must declare `global _LOG_FILE` if mutating module-level state; verify `# CLEANUP:` annotations on swallow sites

**Step 5 — `pipeline.py` D2 disk-monitor wiring**:

- Step 5.1: Identify the correct integration point — either `_health_log_loop` (matches Q4 (a) RATIFIED disk-monitor cadence) OR `_dream_loop` (per `_dream_loop` precedent for cleanup tasks)
- Step 5.2: Wire `_check_terminal_output_size_cap()` + `_prune_old_terminal_archives()` calls inside try/except
- Step 5.3: Confirm error log + `# CLEANUP:` annotation

**Step 6 — `tests/test_p0_r12_r15_resilience_hygiene.py` NEW (9 anchors + 2 helper tests per §3)**:

- Step 6.1: Create test file with `_get_call_name` + `_is_inside_class_method` helpers at module top
- Step 6.2: Add helper tests (`test_get_call_name_helper` + `test_is_inside_class_method_helper`) — co-located not counted as anchors
- Step 6.3: Add A1-A9 test functions per §3 anchor enumeration
- Step 6.4: A5 specifically uses monkeypatched `_LOG_PATH.stat()` returning synthetic `st_size` (auditor recommendation #4 — avoid 100MB I/O)
- Step 6.5: A2 + A6 use `tmp_path` fixture for filesystem isolation

**Step 7 — Phase 4 verify-on-revert pass (per §4 matrix)**:

- Step 7.1: Apply each of 9 reverts (a-i) in sequence via temporary Edit
- Step 7.2: After each revert, run the corresponding anchor test in isolation; verify it fires correctly
- Step 7.3: Revert the revert; verify suite green at end of each revert cycle
- Step 7.4: Bank reverts (a-i) in closure narrative `### Induction-surfaces-invariant-gaps` X → X+1 instance

**Mutation-step independence verification**: Steps 1-5 are independent and can land in any order. Step 6 must land last (depends on all prior implementation steps). Step 7 depends on Step 6. Per the P0.R11 Observation 1 absorption pattern — defends against missing-step silent-masking shape.

---

## §6 SCHEDULED memory-file work at closure (cross-path discipline preventive)

Per `feedback_architect_reads_catches_phase_7_memory_file_omission.md` operational rules locked at P0.R9 + P0.R10 closures:

**P0.R12-R15 closure does NOT project NEW memory files**. The bundled-cycle closure does NOT introduce new sub-shapes / sub-variants / observation candidates per Phase 0 audit verdict (0 non-blocking observations).

**IF any memory-file edits surface at closure** (unlikely given clean Phase 0 verdict):

- Step 6.1.a: Apply at architect-memory path `C:\Users\jagan\.claude\projects\C--Users-jagan-dog-ai-dog-ai\memory\`
- Step 6.1.b: Apply at auditor-facing path `C:\Users\jagan\.claude\projects\C--Users-jagan-dog-ai\memory\`
- Step 6.1.c: Update MEMORY.md index entries at BOTH paths
- Step 6.1.d: Fresh Read both paths post-edit; verify entries land

**MEMORY-FILE INDEX GAP family stays at 5 instances** if no new sub-variants fire at this closure (cross-path discipline applied preventively at §0 + §6).

### §6.1 DEFERRED-CANARY-ENTRY-OMISSION grep-verify (P0.R10 LESSON)

At P0.R12-R15 closure, architect MUST grep-verify `to_be_checked.md` actually contains the P0.R12-R15 deferred-canary entry via **PowerShell fresh-disk read** (NOT Grep tool — per P0.R9 closure-audit STALE-CACHED-VERIFICATION 2nd instance lesson + P0.R10 closure-audit 3rd recursive instance lesson).

```powershell
$content = Get-Content "C:\Users\jagan\dog-ai\to_be_checked.md" -Raw
$r12cnt = ([regex]::Matches($content, "P0.R12")).Count
$r13cnt = ([regex]::Matches($content, "P0.R13")).Count
$r14cnt = ([regex]::Matches($content, "P0.R14")).Count
$r15cnt = ([regex]::Matches($content, "P0.R15")).Count
# Expected: ≥1 match each post-deferred-canary entry pasted
```

### §6.2 P0.R arc completion milestone narrative (auditor recommendation #7)

If P0.R12-R15 closes clean, closure narrative MUST document the **P0.R arc completion milestone**:

```markdown
**P0.R arc COMPLETE** at P0.R12-R15 closure 2026-05-25 — 14-cycle resilience-track
arc fully closed (P0.R1 → R12-R15 inclusive; P0.R7 DEFERRED per user's plans).
This is a meaningful architectural milestone.

Bank as `### Resilience-track-arc-completion` candidate at closure (auditor
recommendation #7); per locked elevation procedure, sub-rule elevation
candidacy WARRANTED at next major architect-side narrative work.
```

---

## §7 Closure-projection band table (Q5 LOCKED at 9)

| closure-actual | overage vs mid 9 | band | doctrine outcome |
|---|---|---|---|
| 7 | −22.2% | SLIGHT-DRIFT-DOWN | `### Phase-0-granular-decomposition` HOLDS at 26 |
| 8 | −11.1% | ON-TARGET | 26 → 27 supporting |
| 9 | 0% | ON-TARGET exact mid | 26 → 27 supporting + **6th consecutive 0%-streak rebuild instance** — additional supporting evidence for the `Doctrine-prediction-precision-improving-over-arc` sub-observation extension RATIFIED at P0.R10 closure |
| 10 | +11.1% | ON-TARGET | 26 → 27 supporting |
| 11 | +22.2% | SLIGHT-DRIFT-UP | HOLDS at 26 |
| ≥12 OR ≤6 | beyond ±30% | FALSIFICATION TRIGGER | demotes back to architect-memory |

**Architect closure-actual projection (Plan v1 §7 honest-count commitment)**: 9 anchors at exact mid (per Q5 RATIFIED at Phase 0 verdict). Bundled-cycle anchor count is stable + spec-time projection matches Phase 0 LOCK.

---

## §8 Doctrine-firing projections at closure

If P0.R12-R15 closes cleanly with closure-actual = 9 anchors at exact mid:

- `### Phase-0-granular-decomposition-enables-accurate-estimates` 26 → 27 supporting
- `Doctrine-prediction-precision-improving-over-arc` 6th consecutive 0%-streak rebuild instance (additional supporting evidence — sub-observation extension already RATIFIED at P0.R10)
- `### Pre-audit-quantifier-precision-refined-by-grep` STAYS at 8 instances (5th consecutive clean-confirmation per operational rule 3 — already validated at Phase 0)
- `### Phase-0-catches-wrong-premise` STAYS at 13 (premise correct)
- `### Zero-precision-items-at-auditor-review` 33 → 34 (Plan v1 if cycle clears cleanly)
- `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` 15 → 16 consecutive cycle (clean-pass mode)
- OPTIONAL-Plan-v2 sub-rule track record 15 → 16 proof cases
- `### Architect-reads-production-code-before-sign-off` 26 → 27 at closure-audit (9th-cycle self-sustaining adoption)
- Strict-industry-standard mode 95 → 98 applications + 28 → 29 closures
- Spec-first review cycle 104 → 107-for-107 at closure
- `### Grep-baseline-before-drafting` 62 → 65 instances
- Cross-cycle-handoff transparency 65 → 68 successful
- Spec-time grep-verification 72 → 75 instances
- `### Twin-filename-pitfall-prevention` 27 → 28 preventive events
- Auditor-Q5-estimates-trail-grep 32 → 33 banked closures
- Deferred-canary strategy 30 → 31 applications (per locked PowerShell fresh-disk read mechanism)
- CODE-TEMPLATE-MISIDENTIFICATION sub-shape: 4th preventive application
- LINE-REF-DRIFT sub-shape: 3rd preventive application (continued BOTH-modes maturation)
- MEMORY-FILE INDEX GAP family: stays at 5 (no new sub-variant firings projected)
- DEFERRED-CANARY-ENTRY-OMISSION sibling class: stays at 2 (PowerShell verification mechanism applied)
- `feedback_multi_discipline_preventive_convergence.md`: 2 → 3 instance candidate (P0.R10 1st + P0.R12-R15 2nd + this cycle if 5+ disciplines apply preventively = 3rd watch criteria milestone reached)
- Bundled-cycle precedent: 2nd instance (P0.B5 + P0.R12-R15) — 3rd instance candidacy at next bundled cycle
- **NEW `### Resilience-track-arc-completion` candidate**: 1st instance — 14-cycle arc closure milestone
- Closure-audit verdict forwarding commitment: 2nd cycle honoring procedural integrity (P0.R10 1st + P0.R12-R15 2nd)

---

## §9 Architect-handoff items for auditor Plan v1 verdict + closure-audit forwarding commitment

1. **Pass-2 grep verification** (per `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` — 15th consecutive cycle at Plan v1 surface): auditor independent re-grep of §1.1 7-row + §1.2 5-row + §1.3 4-row + §1.4 4-row + §1.5 8-row tables. **LINE-REF-DRIFT preventive applied at Plan v1 drafting** — no drift caught (clean refresh).

2. **Q1-Q9 already RATIFIED at Phase 0 verdict** — no Plan v1 adjudication needed. Plan v1 §2 D-decisions are LOCKED at Phase 0 architect leans.

3. **Phase 0 absorption verification**:
   - **§5 explicit 7-step mutation enumeration** (Recommendation #1 absorption): mutation-step independence verification documented at line 451 ("Steps 1-5 are independent... Step 6 must land last... Step 7 depends on Step 6.")
   - **LINE-REF-DRIFT preventive re-verification** (Recommendation #2 absorption): all line-ref claims grep-verified at Plan v1 drafting; no drift caught
   - **A7 + A8 AST helper coverage** (Recommendation #3 absorption): `_get_call_name` + `_is_inside_class_method` explicit signatures + bundled-inline helper tests at §3
   - **A5 fast-scoped behavioral test** (Recommendation #4 absorption): monkeypatched `_LOG_PATH.stat()` synthetic `st_size` avoids 100MB I/O; test runs <0.1s
   - **§6 cross-path memory-file work scheduled** (Recommendation #5 absorption): no new memory files projected; if introduced, cross-path discipline applied per locked operational rule + DEFERRED-CANARY grep-verify via PowerShell fresh-disk read
   - **§9 closure-audit verdict forwarding** (Recommendation #6 absorption): COMMITTED at §0 + §9; 2nd cycle to honor procedural integrity discipline post-P0.R10
   - **P0.R arc completion milestone narrative scheduling** (Recommendation #7 absorption): §6.2 explicit narrative scheduling + `### Resilience-track-arc-completion` candidate banking at closure

4. **Closure-audit verdict forwarding commitment** (per §0 + §9): at P0.R12-R15 Phase 7 closure-audit, architect explicitly forwards closure-audit findings + cross-path verification results + any caught gaps to auditor for explicit ratification verdict BEFORE declaring bundle CLOSED. Preserves 4-step cycle integrity (Phase 0 verdict → Plan v1 verdict → closure-audit verdict → next-cycle Phase 0). 2nd cycle post-P0.R10 honoring this procedural commitment.

5. **Cross-path discipline preventive commitment** (per locked operational rule): if P0.R12-R15 closure introduces any NEW memory files (NOT projected — clean Phase 0 verdict), architect verifies updates at BOTH paths; architect verifies DEFERRED-CANARY entry lands at `to_be_checked.md` via PowerShell fresh-disk read per P0.R9 + P0.R10 STALE-CACHED-VERIFICATION lessons.

6. **6th consecutive 0%-streak rebuild candidacy**: if closure-actual = 9 at exact mid, P0.R12-R15 provides additional supporting evidence for the `Doctrine-prediction-precision-improving-over-arc` sub-observation already RATIFIED at P0.R10. NOT a re-elevation event; just sustained empirical evidence.

7. **P0.R arc completion milestone** (auditor's Recommendation #7): closure narrative will document 14-cycle resilience-track arc closure milestone + bank `### Resilience-track-arc-completion` candidate per Phase 0 §8. **Sub-rule elevation candidacy WARRANTED at next major architect-side narrative work**.

---

**End of Plan v1.** Ready for auditor verdict.
