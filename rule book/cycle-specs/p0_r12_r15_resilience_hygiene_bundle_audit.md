# P0.R12-R15 — Resilience Hygiene Bundle (Phase 0 audit)

**Date**: 2026-05-25
**Author**: architect (Claude)
**Cycle shape**: SMALL-MEDIUM band, 3-artifact OPTIONAL-Plan-v2 path projected
**Estimated effort**: ~3h MEDIUM-band cycle (4 small specs bundled)
**Pattern precedent**: P0.B5 (4 bugs bundled in single cycle) — same shape
**Companion specs**: P0.0.7 (`_archive_terminal_output` startup hook), Wave 5 Item 20 (disk monitor pattern), Wave 6 Item 21 (conversation_log archival mechanism), Wave 7 Item 24+25 (concurrent DB precedents), P0.R10 (audio resilience — DEFERRED-CANARY-ENTRY-OMISSION grep-verify mechanism inherited)

---

## §0 Pre-audit framing (LOCKED 2026-05-25 by architect BEFORE Phase 0 grep verification)

> "P0.R12-R15 bundles 4 small resilience-hygiene items originally listed as P0.R8-R11 in pre-2026-05-25 plan; renumbered to R12-R15 at plan-sync 2026-05-25 after resilience-track work shipped under R8-R11 numbering. D1 (R12): conversation_log_archive table retention — NEW `prune_old_archive_conversation_log(retention_days)` method on FaceDB + wire into `_dream_loop` + `CONVERSATION_ARCHIVE_RETENTION_DAYS=365` config. D2 (R13): terminal_output.md size cap + rotation — NEW `_check_terminal_output_size_cap()` helper called from disk monitor poll cadence; `TERMINAL_OUTPUT_SIZE_CAP_MB=100` config. D3 (R14): structural invariant test — AST scan for hardcoded camera index (literal `0` or other non-config value passed to `Camera()` or `cv2.VideoCapture()` constructors outside `CAMERA_INDEX` config reference). D4 (R15): structural invariant test — AST scan for `time.sleep(` calls inside `async def` bodies across `pipeline.py` + `core/*.py`. ~3h MEDIUM-band cycle; bundled to amortize Phase 0 + Plan v1 + closure overhead per P0.B5 precedent."

**LINE-REF-DRIFT prevention** (per `feedback_pass_2_grep_caught_real_gap_subshape.md` 3rd sub-shape locked at P0.R9 closure + BOTH-modes maturation at P0.R10): all line refs grep-verified at Phase 0 drafting time via fresh tool invocation.

**CODE-TEMPLATE-MISIDENTIFICATION preventive risk-check** (validated in BOTH modes at P0.R11 + P0.R9 + P0.R10): §2 D-decision code templates verified against current production surfaces upfront. Result: LOW risk; all references grep-verifiable.

**Cross-path discipline preventive commitment** (per `feedback_architect_reads_catches_phase_7_memory_file_omission.md` 4th sub-variant CROSS-PATH-SYNC-OMISSION + NEW DEFERRED-CANARY-ENTRY-OMISSION sibling class operational rule, locked at P0.R9 + P0.R10 closures): NO new memory files projected at closure. IF any memory-file edits introduced at closure, architect MUST verify at BOTH paths + DEFERRED-CANARY entry verification at `to_be_checked.md` via PowerShell fresh-disk read.

**Closure-audit verdict forwarding commitment** (per §9 commitment locked at P0.R10 Plan v1 + RATIFIED at P0.R10 closure-audit): P0.R12-R15 closure-audit will be forwarded to auditor for explicit ratification before bundle is declared CLOSED. Preserves 4-step cycle integrity.

---

## §1 Grep findings (Pass-1 baseline) — COMPREHENSIVE upfront

### §1.1 P0.R12 — Conversation_log_archive retention surfaces

| # | Surface | File:Line | Current behavior |
|---|---|---|---|
| 1 | `CONVERSATION_ARCHIVE_AFTER_DAYS = 30` | `core/config.py:1297` | Rows older than 30 days move from `conversation_log` → archive DB |
| 2 | `FaceDB.archive_old_conversation_log(cutoff_days, now)` | `core/db.py:301-357` | ATTACH DATABASE + INSERT + DELETE under `BEGIN EXCLUSIVE`; P0.9.1 Imp-2 tightened rollback |
| 3 | `FaceDB._archive_db_path()` | `core/db.py:267-270` | Returns `{db_stem}_conversation_archive.db` |
| 4 | `FaceDB._init_conversation_archive()` | `core/db.py:272+` | Creates archive DB with same schema as conversation_log |
| 5 | Wire in `_dream_loop` | `pipeline.py` | `archive_old_conversation_log` called periodically (cleanup pattern) |
| 6 | Archive DB read paths | `core/db.py:1329 + 1612` | `load_conversation_history` + `search_conversation` UNION-merge across main + archive |

**Gap**: archive DB has ZERO retention policy. Rows accumulate indefinitely.

### §1.2 P0.R13 — terminal_output.md surfaces

| # | Surface | File:Line | Current behavior |
|---|---|---|---|
| 1 | `_archive_terminal_output(log_path)` | `pipeline.py:34-78` | Renames existing `terminal_output.md` → `terminal_output_YYYY-MM-DD_HHMMSS.md` at startup; mtime-based stamp; collision-safe |
| 2 | `_archived_log = _archive_terminal_output()` | `pipeline.py:81` | Called once at module import |
| 3 | `_LOG_FILE = open(_LOG_PATH, "w", encoding="utf-8", buffering=1)` | `pipeline.py:83-88` | Fresh per session (P1.5 design); prior session's content in timestamped archive |
| 4 | Disk monitor poll cycle | `core/disk_monitor.py` | Runs every health cycle (`HEALTH_LOG_INTERVAL_SECS=300`) |

**Gaps**: (a) NO in-session size cap — single session could write GB if log-intensive; (b) NO retention policy on archived terminal_output_*.md files — accumulate indefinitely.

### §1.3 P0.R14 — Camera index references

| # | Surface | File:Line | Current behavior |
|---|---|---|---|
| 1 | `CAMERA_INDEX = 0` config | `core/config.py:16` | Operator-tunable |
| 2 | `Camera(CAMERA_INDEX)` instantiation | `pipeline.py:6569` | Reads from config ✓ |
| 3 | `cv2.VideoCapture(index, backend)` (init path) | `core/vision.py:419` | `index` param passed through cleanly |
| 4 | `cv2.VideoCapture(self._index, self._backend)` (reconnect path) | `core/vision.py:433` | Uses stored `_index` from construction |

**Verdict**: Already config-driven. Just needs structural invariant test to prevent future hardcoded-literal regression.

### §1.4 P0.R15 — time.sleep references

| # | Surface | File:Line | Current behavior |
|---|---|---|---|
| 1 | `time.sleep(interval)` in `Camera.capture_frames` | `core/vision.py:451` | SYNC `def`, explicitly "for use outside async contexts" |
| 2 | `time.sleep(interval)` in `Camera.capture_frames_with_preview` | `core/vision.py:543` | SYNC `def`, GUI preview path for enrollment |
| 3 | `await asyncio.sleep(interval)` in `Camera.capture_frames_async` | `core/vision.py:470` | ASYNC counterpart (P1.A1 lineage) |
| 4 | Test-only `time.sleep(...)` | `tests/*.py` | Multiple test files — not production concern |

**Verdict**: Production `time.sleep` only in 2 sync methods. Async counterpart correctly uses `asyncio.sleep`. Just needs structural invariant test to prevent future violation in async bodies.

### §1.5 Cross-spec interactions (Pass-2 grep)

| Spec | Interaction | Status |
|---|---|---|
| Wave 6 Item 21 | `conversation_log` archival mechanism + archive DB schema | EXTENDS — D1 adds retention layer to existing archive DB |
| Wave 5 Item 20 | Disk monitor poll cadence + threshold pattern | EXTENDS — D2 piggybacks on disk monitor cycle for size-cap check |
| P0.0.7 | `_archive_terminal_output` startup hook | EXTENDS — D2 adds in-session size-cap + archive retention |
| P0.9.1 Imp-1 | `isolation_level="IMMEDIATE"` discipline | LOAD-BEARING — D1 new `prune_old_archive_conversation_log` must follow the same connection-level isolation pattern |
| P0.9.1 Imp-2 | Tightened rollback `# RACE: S65` pattern | LOAD-BEARING — D1 prune SQL must use same explicit-error-classification rollback |
| P0.4 silent-except policy | Annotation discipline | LOAD-BEARING — D2 size-cap check + D1 prune must use `# CLEANUP:` annotation if any swallowed-by-design errors |
| P0.R10 Q3 (a) | None-return contract | NOT APPLICABLE — these are admin/janitor paths, not user-facing |

---

## §2 Architectural justification

Pre-audit framing is structurally CORRECT. Phase 0 grep ADDS:

1. **Bundled-cycle precedent** (P0.B5): 4 bugs in single cycle worked cleanly + saved cycle overhead. P0.R12-R15 follows same pattern. Each spec contributes 1 D-decision.

2. **D3 + D4 are pure structural invariants** (no production code change): the original P0.R10 + P0.R11 concerns are already RESOLVED by project design; the only remaining work is ensuring the property continues to hold via AST-scan invariants. Same shape as P0.0 S2 tripwire (preventive structural lock).

3. **D1 + D2 are real new work**: archive table retention + terminal_output.md size cap are genuinely missing.

Risk/benefit:
- **Risk D1**: `prune_old_archive_conversation_log` removing data operator may want. Mitigation: `CONVERSATION_ARCHIVE_RETENTION_DAYS=365` default = 1 year; operator-tunable.
- **Risk D2**: aggressive size cap may rotate mid-session at inconvenient moment. Mitigation: `TERMINAL_OUTPUT_SIZE_CAP_MB=100` is generous default; rotation is non-destructive (renames to timestamped archive, opens new file).
- **Risk D3 + D4**: structural invariants may false-positive on legitimate sync code paths. Mitigation: D4 explicitly allow-lists sync `def` bodies + test code paths.
- **Benefit**: closes 4 hygiene items as a single SMALL-MEDIUM cycle vs 4 separate cycles. Lower closure-audit overhead.

---

## §3 D-decision proposal (4 D-decisions)

### D1 — Conversation_log_archive retention (P0.R12)

**`core/config.py`** — new constant after `CONVERSATION_ARCHIVE_AFTER_DAYS`:

```python
# P0.R12 — conversation_log_archive retention. Archive DB at
# `{db_stem}_conversation_archive.db` accumulates rows after Wave 6 Item 21
# moves them from main conversation_log. Without retention, archive grows
# indefinitely. 1-year default — operator-tunable.
CONVERSATION_ARCHIVE_RETENTION_DAYS = 365
```

**`core/db.py`** — new `FaceDB.prune_old_archive_conversation_log` method after `archive_old_conversation_log`:

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
    Operator-tunable via config.
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
        # Count first for return value
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
            # else: # RACE: S65 — known race, suppress
        raise
    finally:
        try:
            self._conn.execute("DETACH DATABASE archive")
        except Exception:
            pass  # CLEANUP: DETACH raises if ATTACH failed earlier
    return n
```

**`pipeline.py::_dream_loop`** — wire after existing `archive_old_conversation_log` call:

```python
# P0.R12 D1 — prune old archive rows after archival
try:
    pruned = await loop.run_in_executor(
        None, db.prune_old_archive_conversation_log, CONVERSATION_ARCHIVE_RETENTION_DAYS
    )
    if pruned > 0:
        print(f"[Dream] Archive-pruned {pruned} conversation_log rows older than {CONVERSATION_ARCHIVE_RETENTION_DAYS} days")
except Exception as e:
    print(f"[Dream] archive prune failed: {e!r}")  # CLEANUP: best-effort
```

### D2 — terminal_output.md size cap + rotation (P0.R13)

**`core/config.py`** — 2 new constants:

```python
# P0.R13 — terminal_output.md size cap + archive retention.
# `_check_terminal_output_size_cap` rotates the file when size exceeds cap;
# `_prune_old_terminal_archives` removes archive files older than retention.
# 100 MB cap is generous for typical session; 30 day archive retention matches
# typical canary-feedback window.
TERMINAL_OUTPUT_SIZE_CAP_MB         = 100
TERMINAL_OUTPUT_ARCHIVE_RETENTION_DAYS = 30
```

**`pipeline.py`** — new helpers + wire into disk monitor poll:

```python
def _check_terminal_output_size_cap(log_path: _pathlib.Path = _LOG_PATH) -> bool:
    """P0.R13 D2 — if log_path > TERMINAL_OUTPUT_SIZE_CAP_MB, rotate it.

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
        print(f"[Pipeline] terminal_output.md rotated at {size_mb:.1f}MB (cap={TERMINAL_OUTPUT_SIZE_CAP_MB}MB)", flush=True)
        return True
    except Exception as e:
        print(f"[Pipeline] terminal_output rotation failed: {e!r}", flush=True)
        return False


def _prune_old_terminal_archives(
    retention_days: int = TERMINAL_OUTPUT_ARCHIVE_RETENTION_DAYS,
    log_dir: _pathlib.Path = None,
) -> int:
    """P0.R13 D2 — delete terminal_output_*.md archive files older than
    retention_days. Returns count deleted.

    Pattern: terminal_output_YYYY-MM-DD_HHMMSS*.md
    """
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

**Wire into disk monitor poll** (`pipeline.py::_health_log_loop` or `_dream_loop`):

```python
# P0.R13 D2 — size cap + archive prune
try:
    _check_terminal_output_size_cap()
    _prune_old_terminal_archives()
except Exception as e:
    print(f"[Pipeline] terminal output hygiene failed: {e!r}")  # CLEANUP: best-effort
```

### D3 — Camera index structural invariant (P0.R14)

**`tests/test_p0_r12_r15_resilience_hygiene.py`** — AST scan anchor:

```python
def test_p0_r14_no_hardcoded_camera_index():
    """P0.R14 D3 — verify no hardcoded camera index in production code.

    Camera() and cv2.VideoCapture() must take `index` from CAMERA_INDEX config
    (or other config), not from literal int. Scans core/*.py + pipeline.py.

    Allowed: `Camera(index)` where `index` is a Name node (variable reference);
    Forbidden: `Camera(0)` where literal int is passed directly.
    """
    import ast
    files_to_scan = [
        "core/vision.py",
        "core/camera.py" if (Path("core/camera.py").exists()) else None,
        "pipeline.py",
    ]
    files_to_scan = [f for f in files_to_scan if f]
    violations = []
    for filename in files_to_scan:
        with open(filename) as f:
            source = f.read()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func_name = _get_call_name(node.func)
                if func_name in ("Camera", "cv2.VideoCapture", "VideoCapture"):
                    if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, int):
                        # Allow inside Camera class methods (self.__init__ + reconnect both use stored _index)
                        if not _is_inside_class_method(node, tree, "Camera"):
                            violations.append(f"{filename}:{node.lineno}")
    assert not violations, f"Hardcoded camera index found: {violations}"
```

### D4 — time.sleep in async invariant (P0.R15)

**`tests/test_p0_r12_r15_resilience_hygiene.py`** — AST scan anchor:

```python
def test_p0_r15_no_time_sleep_in_async_bodies():
    """P0.R15 D4 — verify no `time.sleep(...)` inside async def bodies.

    Async loop must use `await asyncio.sleep(...)`. Sync def bodies are
    allowed (capture_frames + capture_frames_with_preview explicitly).
    Scans core/*.py + pipeline.py.
    """
    import ast
    files_to_scan = ["pipeline.py"] + list(Path("core").glob("*.py"))
    violations = []
    for filename in files_to_scan:
        with open(filename) as f:
            source = f.read()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef):
                for inner in ast.walk(node):
                    if isinstance(inner, ast.Call):
                        func_name = _get_call_name(inner.func)
                        if func_name == "time.sleep":
                            violations.append(f"{filename}:{inner.lineno} (inside {node.name})")
    assert not violations, f"time.sleep inside async def: {violations}"
```

---

## §4 Anchor count proposal (Q5 LOCKED = 9 anchors)

**Mid 9 INCLUSIVE ±15% band → [7.65, 10.35] → ON-TARGET = 8, 9, or 10 anchors**:

| # | Anchor | Surface | Type |
|---|---|---|---|
| A1 | `test_p0_r12_d1_prune_archive_method_exists` | `core/db.py` | SOURCE — verify `FaceDB.prune_old_archive_conversation_log` method present + signature matches |
| A2 | `test_p0_r12_d1_prune_archive_removes_old_rows` | `core/db.py` | BEHAVIORAL — seed archive DB with rows at different ts; call `prune_old_archive_conversation_log(retention_days=30)`; verify rows older than 30d are deleted, recent rows preserved |
| A3 | `test_p0_r12_d1_dream_loop_calls_prune` | `pipeline.py` | SOURCE — AST scan `_dream_loop` for `prune_old_archive_conversation_log(CONVERSATION_ARCHIVE_RETENTION_DAYS)` call |
| A4 | `test_p0_r13_d2_size_cap_rotation_helper_exists` | `pipeline.py` | SOURCE — verify `_check_terminal_output_size_cap` + `_prune_old_terminal_archives` functions present |
| A5 | `test_p0_r13_d2_size_cap_triggers_rotation_at_threshold` | `pipeline.py` | BEHAVIORAL — write `TERMINAL_OUTPUT_SIZE_CAP_MB + 1` MB to monkeypatched `_LOG_PATH`; call `_check_terminal_output_size_cap`; verify rotation fires (file renamed + new file opened); ALSO verify under-cap case = no rotation |
| A6 | `test_p0_r13_d2_archive_prune_removes_old_files` | `pipeline.py` | BEHAVIORAL — seed `terminal_output_*.md` archives with backdated mtime; call `_prune_old_terminal_archives(retention_days=30)`; verify old deleted, recent preserved |
| A7 | `test_p0_r14_d3_no_hardcoded_camera_index` | `core/*.py` + `pipeline.py` | AST SCAN — D3 structural invariant per §3 |
| A8 | `test_p0_r15_d4_no_time_sleep_in_async_bodies` | `core/*.py` + `pipeline.py` | AST SCAN — D4 structural invariant per §3 |
| A9 | `test_p0_r12_r15_config_constants_present` | `core/config.py` | SOURCE — verify `CONVERSATION_ARCHIVE_RETENTION_DAYS=365` + `TERMINAL_OUTPUT_SIZE_CAP_MB=100` + `TERMINAL_OUTPUT_ARCHIVE_RETENTION_DAYS=30` constants present with sanity values |

**Closure-projection band table**:

| closure-actual | overage vs mid 9 | band | doctrine outcome |
|---|---|---|---|
| 7 | −22.2% | SLIGHT-DRIFT-DOWN | `### Phase-0-granular-decomposition` HOLDS at 26 |
| 8 | −11.1% | ON-TARGET | 26 → 27 supporting |
| 9 | 0% | ON-TARGET exact mid | 26 → 27 supporting + **6th consecutive 0%-streak rebuild instance** (P0.R6.Z + P0.R8 + P0.R11 + P0.R9 + P0.R10 + P0.R12-R15; sub-observation extension WARRANTED at P0.R10 closure already RATIFIED — this would be additional supporting evidence) |
| 10 | +11.1% | ON-TARGET | 26 → 27 supporting |
| 11 | +22.2% | SLIGHT-DRIFT-UP | HOLDS at 26 |
| ≥12 OR ≤6 | beyond ±30% | FALSIFICATION TRIGGER | demotes back to architect-memory |

---

## §5 OUT-OF-SCOPE classification

1. **Force-eviction on disk full** — `LOW_DISK_PANIC` mode from original P0.R8 row deferred; current `DISK_ALERT_BLOCKER_PCT=95` threshold + WatchdogAgent alert is sufficient. If empirical pressure surfaces, file follow-up.
2. **Multi-camera support** — original P0.R10 row's "Multi-camera scaffolding (P1.MM3)" stays at P1; not in P0.R14.
3. **Per-table storage budget doc** (`docs/storage_budget.md`) — original P0.R8 row deliverable 1; deferred to follow-up if operator surfaces real disk pressure. Current spec ships the prune mechanism without the storage-budget doc.
4. **Compressed parquet archives** — original P0.R8 row deliverable 2 ("compress archive to parquet at 1y, delete at 5y"); simplified to plain DELETE at retention_days. Parquet conversion is a future optimization if archive size dominates disk usage.
5. **logrotate / systemd journald integration** — original P0.R9 row's logrotate config deferred to operator-deployment concern; in-process rotation via Python is the bundled-cycle scope.
6. **Live canary validation** — per deferred-canary discipline locked at P0.S7.5.2, no live canaries until end-of-P0.R11 (now reached at P0.R10 closure 2026-05-25); P0.R12-R15 entry banked to `to_be_checked.md` at closure for canary-week validation.

---

## §6 Locked-down discipline counters

Per `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` doctrine: auditor's DILIGENT Pass-2 grep at Plan v1 §1 will independently verify §1.1-§1.5 surface tables.

**LINE-REF-DRIFT prevention applied at Phase 0 drafting** — all line refs grep-verified at draft time per the sub-shape's BOTH-modes locked discipline (P0.R10 closure validation).

**CODE-TEMPLATE-MISIDENTIFICATION sub-shape preventive risk-check** — §2 D-decision code templates reference:
- `archive_old_conversation_log` at `core/db.py:301-357` ✓
- `_archive_db_path` at `core/db.py:267-270` ✓
- `_archive_terminal_output` at `pipeline.py:34-78` ✓
- `_LOG_PATH` + `_LOG_FILE` module globals at `pipeline.py:81-88` ✓
- `Camera.__init__` + reconnect at `core/vision.py:419 + 433` ✓
- `cv2.VideoCapture` is OpenCV stdlib API ✓
- `_dream_loop` exists in pipeline.py (verified via earlier grep) ✓

CODE-TEMPLATE-MISIDENTIFICATION risk: LOW (4th consecutive preventive application after P0.R11 + P0.R9 + P0.R10).

**`### Pre-audit-quantifier-precision-refined-by-grep` instance enumeration**:

Phase 0 grep CONFIRMS pre-audit framing — no quantifier refinement event. Pre-audit said "4 small specs bundled" + "1 D-decision per spec" + "9 anchors total"; grep verified all claims match production state. Per operational rule 3, no instance bank fires. Doctrine STAYS at 8 instances. **5th consecutive clean-confirmation since elevation** (P0.R8 + P0.R11 + P0.R9 + P0.R10 + P0.R12-R15) — sustained negative-evidence validation continues to mature.

---

## §7 Q-questions for adjudication

**Q1 (D1 retention default)**:
- (a) `CONVERSATION_ARCHIVE_RETENTION_DAYS = 365` (1 year)
- (b) `CONVERSATION_ARCHIVE_RETENTION_DAYS = 1825` (5 years)
- (c) No default; operator-tunable only with explicit config

**Architect lean: (a)** — 1 year covers typical operator concern; 5 years is parquet-compression territory (OUT-OF-SCOPE per §5).

**Q2 (D2 size cap default)**:
- (a) `TERMINAL_OUTPUT_SIZE_CAP_MB = 100` (generous)
- (b) `TERMINAL_OUTPUT_SIZE_CAP_MB = 50` (stricter)
- (c) `TERMINAL_OUTPUT_SIZE_CAP_MB = 500` (lax)

**Architect lean: (a)** — 100 MB is generous for typical session; rotation is non-destructive.

**Q3 (D2 archive retention default)**:
- (a) `TERMINAL_OUTPUT_ARCHIVE_RETENTION_DAYS = 30` (matches canary-feedback window)
- (b) `TERMINAL_OUTPUT_ARCHIVE_RETENTION_DAYS = 90` (longer history)
- (c) `TERMINAL_OUTPUT_ARCHIVE_RETENTION_DAYS = 7` (aggressive)

**Architect lean: (a)** — 30 days matches typical canary-feedback window; longer retention is operator-tunable.

**Q4 (D2 size-cap check cadence)**:
- (a) Disk monitor poll cycle (every `HEALTH_LOG_INTERVAL_SECS=300`)
- (b) Dream-loop cadence (5 min idle)
- (c) Per-print check (expensive)

**Architect lean: (a)** — disk monitor poll is the natural fit; size-cap is a disk-hygiene concern.

**Q5 (D3 invariant scope)**:
- (a) Scan `core/*.py` + `pipeline.py` only
- (b) Include all of `tests/*.py`
- (c) Include `enroll.py`, `delete_person.py`, other CLI scripts

**Architect lean: (a)** — production code only; CLI scripts may legitimately hardcode for one-off ops.

**Q6 (D4 invariant scope)**:
- (a) Scan `core/*.py` + `pipeline.py` for `time.sleep` inside `async def` bodies
- (b) Also scan `tests/*.py` (production-side only)
- (c) Include sync `def` bodies as warnings

**Architect lean: (a)** — async-only is the load-bearing invariant; sync `def` use of `time.sleep` is intentional (capture_frames + capture_frames_with_preview).

**Q7 (Bundled vs sequential)**:
- (a) Single bundled cycle per user direction
- (b) Sequential cycles

**Architect lean: (a)** — RATIFIED per user 2026-05-25 + P0.B5 precedent.

**Q8 (D1 + D2 retention units)**:
- (a) Both use `_DAYS` suffix (consistency)
- (b) D1 uses `_DAYS`, D2 uses `_HOURS` for finer-grained rotation

**Architect lean: (a)** — `_DAYS` suffix matches existing `CONVERSATION_ARCHIVE_AFTER_DAYS` + `CRASH_LOG_RETENTION_DAYS` conventions.

**Q9 (Closure-narrative bundling)**:
- (a) Single closure narrative covering all 4 D-decisions (P0.B5 precedent)
- (b) 4 separate closure narratives

**Architect lean: (a)** — single bundled narrative + cross-reference per-spec headers in CLAUDE.md.

---

## §8 Doctrine-firing projections at closure

If P0.R12-R15 closes cleanly with closure-actual = 9 anchors at exact mid:

- `### Phase-0-granular-decomposition-enables-accurate-estimates` 26 → 27 supporting
- `Doctrine-prediction-precision-improving-over-arc` 6th consecutive 0%-streak rebuild (sub-observation extension RATIFIED at P0.R10; this provides additional supporting evidence)
- `### Pre-audit-quantifier-precision-refined-by-grep` STAYS at 8 instances (5th consecutive clean-confirmation per operational rule 3)
- `### Phase-0-catches-wrong-premise` STAYS at 13 (premise correct)
- `### Zero-precision-items-at-auditor-review` 32 → 34 (Phase 0 + Plan v1 if cycle clears cleanly with 0 BLOCKING PIs)
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
- Deferred-canary strategy 30 → 31 applications
- CODE-TEMPLATE-MISIDENTIFICATION sub-shape: 4th preventive application (1 caught + 4 preventive)
- LINE-REF-DRIFT sub-shape: 3rd preventive application (1 caught + 3 preventive — continued BOTH-modes maturation)
- MEMORY-FILE INDEX GAP family: stays at 5 if cross-path discipline applied cleanly (no new memory files projected)
- DEFERRED-CANARY-ENTRY-OMISSION sibling class: stays at 2 if entry actually lands at `to_be_checked.md` per locked PowerShell fresh-disk read mechanism

---

## §9 Architect-handoff items for auditor verdict

1. **Pass-2 grep verification** (per `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` — 15th consecutive cycle at Phase 0 surface): independent re-grep §1.1-§1.5 tables. **CODE-TEMPLATE-MISIDENTIFICATION risk-check**: §3 D-decision code templates reference all grep-verifiable surfaces per §6. **LINE-REF-DRIFT prevention applied** at Phase 0 drafting per §6.

2. **Q1-Q9 adjudication**: confirm architect leans. Q1-Q4 are LOAD-BEARING (default values + cadence affect operational behavior); Q5-Q9 are implementation refinements.

3. **Anchor count adjudication**: confirm mid 9 INCLUSIVE ±15% band [7.65, 10.35].

4. **Bundled-cycle justification**: per user direction + P0.B5 precedent. §5 explicit OUT-OF-SCOPE enumeration prevents scope creep.

5. **Cross-spec interaction verification** (§1.5): P0.9.1 Imp-1 + Imp-2 patterns inherited; P0.4 silent-except `# CLEANUP:` annotation applied at all swallow sites.

6. **5th consecutive clean-confirmation for `### Pre-audit-quantifier-precision-refined-by-grep`**: per §6, sustained empirical validation continues.

7. **Closure-audit verdict forwarding commitment** (per §0 commitment): P0.R12-R15 closure-audit will be forwarded to auditor for explicit ratification before bundle declared CLOSED. Same procedural integrity discipline locked at P0.R10 §9.

8. **Cross-path discipline preventive commitment**: NO new memory files projected; if any introduced at closure, both paths + DEFERRED-CANARY entry verification via PowerShell fresh-disk read per locked operational rule.

---

**End of Phase 0 audit.** Ready for auditor verdict.
