# P0.R11 — Crash diagnostic capture (Phase 0 audit)

**Date**: 2026-05-25
**Author**: architect (Claude)
**Cycle shape**: SMALL-MEDIUM band, extends P0.R8's `(task_name, timestamp)` tuples with full forensic capture
**Estimated effort**: ~2-3h SMALL-MEDIUM cycle
**Companion specs**: P0.R8 (crash detection + burst limit; provides the `BrokenProcessPool` catch site that P0.R11 extends), P0.S2 + Wave 5 Item 20 (cleanup-loop precedents), P0.4 (silent-except policy)

---

## §0 Pre-audit framing (LOCKED 2026-05-25 by architect BEFORE grep verification)

> "P0.R11 extends P0.R8's `(task_name, timestamp)` crash history with full forensic capture: exception_type + exception_message + stack_trace + crash_count_at_capture. Writes structured JSON to `faces/crash_logs/{task_name}_{timestamp}.json`. Retention via cleanup helper (default 7 days). HealthSnapshot exposes recent crash log paths for dashboard visibility. Architectural foundation enables future extension to ANY unhandled subprocess exception — P0.R11 lands the foundation + heavy-worker pool integration; broader exception capture is follow-up cycle. ~2-3h SMALL-MEDIUM cycle."

Grep verifies framing. Findings below.

---

## §1 Grep findings (Pass-1 baseline)

### §1.1 P0.R8 crash recording infrastructure (extension point)

| # | Surface | File:Line | Current behavior |
|---|---|---|---|
| 1 | `_record_pool_crash(task_name, now=None)` | `core/heavy_worker.py:55-70` | Appends `now` to `_HEAVY_WORKER_CRASH_HISTORY[task_name]` list. Thread-safe via `_HEAVY_WORKER_CRASH_LOCK`. |
| 2 | `run_heavy` D2 wrapper | `core/heavy_worker.py:182-187` | `except concurrent.futures.process.BrokenProcessPool:` catches + calls `_record_pool_crash(task_name)` + bare `raise` |
| 3 | `count_recent_crashes(task_name, window_secs)` | `core/heavy_worker.py:73-87` | Rolling-window count for burst detection |
| 4 | `peek_crash_history(task_name)` | `core/heavy_worker.py:90-94` | Read-only accessor for tests + health |

**Extension surface**: P0.R8's `_record_pool_crash` takes only `task_name` + `now`. P0.R11 adds a sibling function `persist_crash_diagnostic(task_name, exc, traceback_str, now)` that writes structured JSON to disk. The two functions are called TOGETHER from `run_heavy`'s except block — `_record_pool_crash` for in-memory burst detection (fast, no I/O), `persist_crash_diagnostic` for disk-persisted forensic capture.

### §1.2 Existing `faces/` directory conventions

| # | Surface | File:Line | Notes |
|---|---|---|---|
| 1 | `FACES_DIR = ROOT / "faces"` | `core/config.py:9` | Root data dir |
| 2 | `FACES_DIR.mkdir(exist_ok=True)` | `core/config.py:13` | Auto-create on import |
| 3 | `BRAIN_DB_PATH = FACES_DIR / "brain.db"` | `core/config.py:1144` | Convention: dbs live in FACES_DIR |
| 4 | `GRAPH_DB_PATH = FACES_DIR / "brain_graph"` | `core/config.py:1145` | Convention: subdirs live in FACES_DIR |
| 5 | Photo: `FACES_DIR / f"{person_id}.jpg"` | `delete_person.py:67` | File-naming precedent |
| 6 | Photo glob: `FACES_DIR.glob("*.jpg")` | `core/db.py:1986` | Iteration precedent for cleanup |
| 7 | Conversation archive: `{db_stem}_conversation_archive.db` | `core/db.py:301` (`archive_old_conversation_log`) | Cleanup-loop precedent (P0.S2/Wave 5) |

**P0.R11 path convention**: `FACES_DIR / "crash_logs" / "{task_name}_{timestamp}.json"`. Subdir under `FACES_DIR` matches `brain_graph/` precedent. JSON file-per-crash matches existing structured-data conventions.

### §1.3 Cleanup-loop precedents (P0.S2 + Wave 5 Item 20)

| # | Surface | File:Line | Notes |
|---|---|---|---|
| 1 | `archive_old_conversation_log(cutoff_days, now)` | `core/db.py:301` | Method-on-FaceDB precedent for retention-based cleanup |
| 2 | `_dream_loop` invocation | `pipeline.py:3424` (`db.archive_old_conversation_log`) | Cleanup wired into dream loop — matches P0.R11's cleanup cadence target |
| 3 | `gather_disk_snapshot` per-dir | `core/disk_monitor.py:32-58` | Per-directory size aggregation precedent (P0.R11's crash_logs/ dir gets tracked) |
| 4 | `DISK_MONITORED_DIRS` config | `core/config.py` | Existing monitored dirs list — crash_logs/ may be added to disk monitor scope |

**P0.R11 cleanup cadence**: dream loop trigger (~5min idle + hourly force) matches the cleanup cadence of `archive_old_conversation_log`. New function `prune_old_crash_logs(retention_days)` in `core/crash_logs.py` called from dream loop.

### §1.4 HealthSnapshot integration surface

| # | Surface | File:Line | Notes |
|---|---|---|---|
| 1 | `HealthSnapshot` dataclass | `core/health.py:~37-80` | P0.R8 added `heavy_worker_status` + `heavy_worker_crash_counts` fields; P0.R11 adds `recent_crash_logs` field |
| 2 | `gather_health_snapshot` | `core/health.py` | Reads from `core.heavy_worker`; P0.R11 extends to read from `core.crash_logs.list_recent_crash_logs` |
| 3 | `format_health_line` | `core/health.py` | P0.R8 added `heavy_worker_crashes=N` conditional emit; P0.R11 adds `crash_logs=N` conditional emit when recent_crash_logs non-empty |
| 4 | `format_health_alerts` | `core/health.py` | P0.R8 added degraded-pool alert; P0.R11 extends with crash-log-available alert hint (operator-actionable: "check faces/crash_logs/ for forensic data") |

### §1.5 P0.4 silent-except policy interaction (LOAD-BEARING)

`P0.R11::persist_crash_diagnostic` writes to disk → can fail (disk full, permission denied, etc.). MUST NOT cascade failure back to caller (would mask the original crash that triggered persistence).

**Pattern**: try/except inside `persist_crash_diagnostic` wraps file write with `# OPTIONAL: silent crash log write failure → log warning, continue` annotation per P0.4 silent-except policy. Same shape as P0.0.7 Step 5 `safe_emit_sync` consolidation. Failure logged via `print` to stderr; `_record_pool_crash` still fires (in-memory tracking still works); `raise` at end of `run_heavy` except block STILL propagates `BrokenProcessPool` to caller.

### §1.6 Cross-spec interactions (Pass-2 grep)

| Spec | Interaction | Status |
|---|---|---|
| P0.R8 | Crash detection + burst limit | EXTENDS — P0.R11 adds persistence alongside existing in-memory tracking |
| P0.4 | Silent-except policy | LOAD-BEARING — persist failure must log + continue (annotated `# OPTIONAL:`) |
| P0.S2 / Wave 5 Item 20 | Conversation archive cleanup-loop | EXTENDS pattern (dream-loop-driven retention cleanup) |
| Wave 5 Item 19 | Health log + disk monitor | EXTENDS — HealthSnapshot adds field; format_health_line adds conditional emit |
| WatchdogAgent | Existing alert dispatch | NO conflict (P0.R11 captures diagnostics for already-alerted crashes; doesn't fire new alerts) |
| Dashboard (Next.js) | dog-ai-dashboard/app/api routes | DEFERRED — P0.R11 ships HealthSnapshot field; dedicated dashboard crash-log browser is follow-up cycle |
| P0.R6.* arc | 4 heavy-worker pools | INHERITS — P0.R8 wrapper covers all 4 pools; P0.R11 captures diagnostics for all 4 uniformly |

---

## §2 Architectural justification refresh

Pre-audit framing was structurally CORRECT. Phase 0 grep ADDS:

1. **`BrokenProcessPool` stack trace limitations**: pyannote/whisper/ecapa/adaface subprocesses crash BEFORE reporting their exception back. `concurrent.futures.process.BrokenProcessPool` is raised main-process-side WITHOUT the original subprocess exception in its traceback. P0.R11 captures main-process-side trace which is useful for context (task_name + call site + crash count) but doesn't capture root-cause exception type from subprocess. Documented limitation; future cycle could add subprocess-side exception handler (catch + serialize exception object + re-raise as a pickled wrapper) for full root-cause capture. Banked at Known Limitations.

2. **Standalone value framing**: P0.R11's `persist_crash_diagnostic` API designed to accept `(task_name, exc, traceback_str, now)` — generic enough to be called from any context that catches an exception. P0.R11 ships heavy-worker integration only; broader extension (asyncio task crashes, dream-loop crashes, etc.) is follow-up cycle. The API is the foundation.

3. **JSON schema_version**: forward-compat field included from cycle 1. Schema evolves cleanly without breaking dashboard readers.

Risk/benefit:

- **Risk**: disk space — crash logs accumulate. Default retention 7 days × typical crash rate ≤1/day = ~7 files at steady state, ~1-5KB each → negligible. Pathological case (constant-crashing pool) bounded by P0.R8 watchdog alert + operator intervention BEFORE disk fills.
- **Risk**: persist failure during crash storm — if disk is already full when crashes happen, `persist_crash_diagnostic` fails. P0.4 annotated try/except wraps write; failure logged + continues. Original crash propagation unaffected.
- **Risk**: file naming collision — sub-second granularity (`{task_name}_{YYYY-MM-DDTHHMMSS}_{micros}.json`) handles ≥1µs separation. If two crashes happen in same µs (extremely rare), second write may overwrite first. Acceptable trade-off vs UUID-suffix overhead.
- **Benefit**: post-mortem analysis without re-running the failure — `BrokenProcessPool` events from CUDA OOM / segfault / model corruption all have task_name + timestamp + stack_trace + crash_count context preserved.
- **Benefit**: foundation for broader exception capture — future asyncio task / dream loop / vision watchdog crash capture all reuse `persist_crash_diagnostic` API.

---

## §3 D-decision proposal (5 D-decisions)

**D1 (`core/crash_logs.py` NEW module)**:

3 public functions + 1 module-level state:

```python
# core/crash_logs.py
"""Crash diagnostic capture (P0.R11). Extends P0.R8's in-memory crash
history with persistent JSON-per-crash forensic data for post-mortem
analysis. Used by core.heavy_worker.run_heavy's BrokenProcessPool catch
block; designed for broader unhandled-exception capture in follow-up cycle.
"""
from __future__ import annotations

import json
import logging
import os
import time
import traceback
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_CRASH_LOG_SCHEMA_VERSION = 1


def _crash_log_dir() -> Path:
    """Return crash_logs/ subdir under FACES_DIR; auto-create on first call."""
    from core.config import FACES_DIR
    d = FACES_DIR / "crash_logs"
    d.mkdir(exist_ok=True, parents=True)
    return d


def persist_crash_diagnostic(
    task_name: str,
    exc: BaseException,
    traceback_str: str,
    crash_count: int,
    now: "float | None" = None,
) -> "Path | None":
    """Write structured JSON crash diagnostic to faces/crash_logs/.

    Q4 (a) lock: schema_version=1 + task_name + timestamp + exception_type +
    exception_message + stack_trace + crash_count fields.

    Q5 (a) lock: filename {task_name}_{YYYY-MM-DDTHHMMSS}_{micros}.json for
    sortable + collision-resistant naming.

    Per P0.4 silent-except policy: write failure (disk full, permission
    denied) is logged + swallowed; returns None on failure. The original
    crash propagation via run_heavy's bare `raise` is UNAFFECTED.

    Returns the path to the written file on success, None on failure.
    """
    if now is None:
        now = time.time()
    try:
        log_dir = _crash_log_dir()
        ts_struct = time.gmtime(now)
        ts_str = time.strftime("%Y-%m-%dT%H%M%S", ts_struct)
        micros = int((now - int(now)) * 1_000_000)
        filename = f"{task_name}_{ts_str}_{micros:06d}.json"
        log_path = log_dir / filename
        payload = {
            "schema_version": _CRASH_LOG_SCHEMA_VERSION,
            "task_name": task_name,
            "timestamp": now,
            "exception_type": type(exc).__name__,
            "exception_message": str(exc),
            "stack_trace": traceback_str,
            "crash_count": crash_count,
        }
        log_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return log_path
    except Exception as e:  # OPTIONAL: persist failure → log + swallow per P0.4
        logger.warning(
            "[CrashLogs] persist_crash_diagnostic failed for task_name=%s: %s: %s",
            task_name, type(e).__name__, e,
        )
        return None


def prune_old_crash_logs(retention_days: int, now: "float | None" = None) -> int:
    """Remove crash log files older than retention_days. Returns count
    of files removed. Called periodically from pipeline._dream_loop.

    Per P0.4: file-level unlink failures are logged + swallowed (a single
    corrupt file shouldn't break the cleanup pass for the rest).
    """
    if now is None:
        now = time.time()
    cutoff = now - (retention_days * 86_400)
    removed = 0
    log_dir = _crash_log_dir()
    for path in log_dir.glob("*.json"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
                removed += 1
        except Exception as e:  # OPTIONAL: per-file unlink failure
            logger.warning(
                "[CrashLogs] prune unlink failed for %s: %s: %s",
                path.name, type(e).__name__, e,
            )
    return removed


def list_recent_crash_logs(limit: int = 10) -> "list[dict[str, Any]]":
    """Return parsed JSON contents of the most recent crash logs (by mtime),
    up to `limit` entries. Read accessor for HealthSnapshot + dashboard.

    Each entry: dict matching persist_crash_diagnostic's payload shape.
    Corrupt files (malformed JSON) are skipped with warning.
    """
    log_dir = _crash_log_dir()
    paths = sorted(log_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    results: "list[dict[str, Any]]" = []
    for path in paths[:limit]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            results.append(data)
        except Exception as e:  # OPTIONAL: parse failure → skip + warn
            logger.warning(
                "[CrashLogs] parse failed for %s: %s: %s",
                path.name, type(e).__name__, e,
            )
    return results
```

**D2 (`run_heavy` wrapper extension)** — extends P0.R8 D2 to call `persist_crash_diagnostic` alongside `_record_pool_crash`:

```python
# core/heavy_worker.py — replaces P0.R8 D2 wrapper at lines 182-187
async def run_heavy(...) -> Any:
    pool = get_or_create_pool(task_name)
    loop = asyncio.get_running_loop()
    bound = functools.partial(fn, *args, **kwargs)
    try:
        return await loop.run_in_executor(pool, bound)
    except concurrent.futures.process.BrokenProcessPool as e:
        # P0.R8: record in-memory burst-detection event.
        _record_pool_crash(task_name)
        # P0.R11: capture full forensic JSON for post-mortem. Persist failure
        # is silently logged (P0.4) — the original BrokenProcessPool MUST
        # propagate via the bare `raise` below regardless.
        try:
            from core.crash_logs import persist_crash_diagnostic
            crash_count = len(_HEAVY_WORKER_CRASH_HISTORY.get(task_name, []))
            persist_crash_diagnostic(
                task_name,
                e,
                traceback.format_exc(),
                crash_count,
            )
        except Exception:  # OPTIONAL: P0.R11 import/call failure
            pass
        raise  # bare — preserves traceback + caller fallback
```

**D3 (`HealthSnapshot` extension + format_health_line + format_health_alerts)**:

```python
# core/health.py — HealthSnapshot dataclass field addition
recent_crash_logs: "list[dict]" = field(default_factory=list)

# gather_health_snapshot addition
from core.crash_logs import list_recent_crash_logs
from core.config import HEALTH_CRASH_LOG_RECENT_LIMIT
recent_crash_logs = list_recent_crash_logs(HEALTH_CRASH_LOG_RECENT_LIMIT)

# format_health_line conditional emit
if recent_crash_logs:
    parts.append(f"crash_logs={len(recent_crash_logs)}")

# format_health_alerts crash-log-available alert
if snapshot.recent_crash_logs:
    most_recent = snapshot.recent_crash_logs[0]
    alerts.append(
        f"Recent crash logs available — most recent: "
        f"task_name={most_recent.get('task_name')} "
        f"at {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(most_recent.get('timestamp', 0)))}. "
        f"Check faces/crash_logs/ for forensic data; clears after "
        f"CRASH_LOG_RETENTION_DAYS via dream-loop cleanup."
    )
```

**D4 (cleanup wiring — `pipeline._dream_loop` extension)**:

```python
# pipeline.py — inside _dream_loop, after existing cleanup calls
from core.crash_logs import prune_old_crash_logs
from core.config import CRASH_LOG_RETENTION_DAYS
_removed = await loop.run_in_executor(None, prune_old_crash_logs, CRASH_LOG_RETENTION_DAYS)
if _removed > 0:
    print(f"[CrashLogs] dream-loop pruned {_removed} crash logs older than {CRASH_LOG_RETENTION_DAYS}d")
```

**D5 (`core/config.py` constants)**:

```python
# core/config.py — new section near other watchdog/observability constants
# P0.R11 — crash diagnostic capture. persist_crash_diagnostic writes
# JSON-per-crash to faces/crash_logs/; prune_old_crash_logs removes
# files older than RETENTION_DAYS via dream-loop cleanup.
CRASH_LOG_RETENTION_DAYS         = 7      # files older than N days pruned at dream loop
HEALTH_CRASH_LOG_RECENT_LIMIT    = 10     # HealthSnapshot.recent_crash_logs cap
CRASH_LOG_SCHEMA_VERSION         = 1      # JSON payload schema version (mirror of _CRASH_LOG_SCHEMA_VERSION)
```

---

## §4 Anchor count proposal (Q5)

**Mid 9 INCLUSIVE ±15% band → [7.65, 10.35] → ON-TARGET = 8, 9, or 10 anchors**:

- **A1**: `core/crash_logs.py` module exists with `persist_crash_diagnostic` + `prune_old_crash_logs` + `list_recent_crash_logs` functions (source-inspection)
- **A2**: `persist_crash_diagnostic` writes JSON to `FACES_DIR/crash_logs/{task_name}_{timestamp}_{micros}.json` with full schema (behavioral test)
- **A3**: JSON payload includes `schema_version` + `task_name` + `timestamp` + `exception_type` + `exception_message` + `stack_trace` + `crash_count` fields (behavioral test with crafted exception)
- **A4**: `prune_old_crash_logs(retention_days)` removes files older than retention_days (behavioral test with backdated mtime)
- **A5**: `list_recent_crash_logs(limit)` returns most recent N entries sorted by mtime descending (behavioral test)
- **A6**: `run_heavy` wrapper calls BOTH `_record_pool_crash` AND `persist_crash_diagnostic` on `BrokenProcessPool` (AST positive + behavioral)
- **A7**: `HealthSnapshot.recent_crash_logs: list[dict]` field present + `format_health_line` conditional `crash_logs=N` emit (source-inspection + behavioral)
- **A8**: Cleanup wired into `pipeline._dream_loop` — `prune_old_crash_logs` called per dream cycle (AST source-inspection)
- **A9**: 3 config constants (`CRASH_LOG_RETENTION_DAYS` + `HEALTH_CRASH_LOG_RECENT_LIMIT` + `CRASH_LOG_SCHEMA_VERSION`)

**Closure-projection band table**:

| closure-actual | overage vs mid 9 | band | doctrine outcome |
|---|---|---|---|
| 7 | −22.2% | SLIGHT-DRIFT-DOWN (within ±30%) | `### Phase-0-granular-decomposition` HOLDS at 23 supporting |
| 8 | −11.1% | ON-TARGET | `### Phase-0-granular-decomposition` 23 → 24 supporting |
| 9 | 0% | ON-TARGET exact mid | `### Phase-0-granular-decomposition` 23 → 24 supporting + **3rd consecutive 0%-streak rebuild instance** |
| 10 | +11.1% | ON-TARGET | `### Phase-0-granular-decomposition` 23 → 24 supporting |
| 11 | +22.2% | SLIGHT-DRIFT-UP (within ±30%) | `### Phase-0-granular-decomposition` HOLDS at 23 supporting |
| ≥12 OR ≤6 | beyond ±30% | FALSIFICATION TRIGGER | doctrine demotes back to architect-memory + reasoning audit |

---

## §5 OUT-OF-SCOPE classification

1. **Subprocess-side exception capture** — `BrokenProcessPool` raised main-process-side without original subprocess exception in traceback. Capturing root-cause would require subprocess-side exception handler (catch + serialize exception object + re-raise pickled wrapper); separate cycle.
2. **Broader unhandled-exception capture** (asyncio task crashes, dream-loop crashes, vision-watchdog crashes) — API designed for this but P0.R11 ships heavy-worker integration only. Follow-up cycle.
3. **Dedicated dashboard crash-log browser** — P0.R11 ships HealthSnapshot field for existing dashboard visibility; dedicated browser page is follow-up cycle.
4. **Crash-log compression / archival** — crash log volumes are tiny (~1-5KB × ≤7 days = negligible). Compression OUT-OF-SCOPE; if disk space becomes a concern, P0.R9 (cumulative VRAM budget) + existing disk monitor cover the failure mode.
5. **Email/notification dispatch on crash log** — WatchdogAgent burst alert already covers operator notification (P0.R8 D4); P0.R11 adds forensic data without changing alert dispatch.
6. **Cross-process crash log access** — single-writer / single-reader assumption (main process writes via `run_heavy`; main process reads via `gather_health_snapshot`). No locking needed beyond OS-level file atomicity for write+read.

---

## §6 Locked-down discipline counters

Per `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` doctrine: auditor DILIGENT Pass-2 grep at Plan v1 §1 will independently verify §1.1 4-row + §1.2 7-row + §1.3 4-row + §1.4 4-row + §1.5 silent-except policy + §1.6 7-row cross-spec table.

Per `feedback_pass_2_grep_deferral_pattern.md` (banked at P0.R6.Y closure-audit): NO "developer Phase N surfaces enumeration" framings in this Phase 0 — all surfaces enumerated upfront with explicit per-surface disposition.

Per `feedback_pass_2_grep_caught_real_gap_subshape.md` (banked at P0.R8 closure-audit): both ENUMERATION-DRIFT and CODE-TEMPLATE-MISIDENTIFICATION sub-shapes risk-assessed at Phase 0. The Phase 0 §2 code template at D1 references `FACES_DIR` (verified at `core/config.py:9`) + `json` + `traceback` + `logging` (stdlib) + `Path` (stdlib) — no non-existent predicates. CODE-TEMPLATE-MISIDENTIFICATION risk: LOW.

**`### Pre-audit-quantifier-precision-refined-by-grep` instance enumeration** (post-P0.R8 closure baseline; CLAUDE.md canonical at lines 656-745 with 8-axis sub-shape taxonomy):

Phase 0 grep CONFIRMS pre-audit framing — no quantifier refinement event fires. Pre-audit said "extends P0.R8" + "JSON to faces/crash_logs/" + "retention via cleanup helper" + "HealthSnapshot exposure"; grep verified all 4 claims match production (P0.R8 wrapper at heavy_worker.py:182-187 ✓ / FACES_DIR convention at config.py:9 ✓ / cleanup-loop precedent at db.py:301 ✓ / HealthSnapshot dataclass at health.py:~37 ✓). Per operational rule 3, no instance bank fires. Doctrine STAYS at 8 instances.

This is the **2nd clean-confirmation since elevation** (after P0.R8). Empirical evidence that the doctrine's operational rule 3 (no firing when grep confirms pre-audit) applies cleanly to SMALL-MEDIUM cycles that extend prior cycles' surface.

---

## §7 Q-questions for adjudication

**Q1 (Call site for `persist_crash_diagnostic`)**:
- Option (a): Same `run_heavy` `BrokenProcessPool` except block, alongside `_record_pool_crash`
- Option (b): Separate hook called from heavy-worker watchdog loop (defers persistence to next poll)

**Architect lean: (a)** — synchronous with crash detection preserves timing precision. Watchdog-deferred would lose original `BrokenProcessPool` exception object + traceback (catch context is local to except block).

**Q2 (Stack trace capture mechanism)**:
- Option (a): `traceback.format_exc()` inside except block (reads from current exception context)
- Option (b): `traceback.format_exception(type(e), e, e.__traceback__)` explicit form

**Architect lean: (a)** — simpler; both produce same string within except block. P0.4 silent-except policy compliance: `format_exc()` call itself doesn't raise.

**Q3 (BrokenProcessPool traceback limitation acknowledgment)**:
- Pyannote/whisper/ecapa/adaface subprocesses crash BEFORE reporting their exception
- Main-process-side trace shows `concurrent.futures` internals + `BrokenProcessPool`, NOT root-cause exception type from subprocess
- **Architect lean: ACKNOWLEDGE as Known Limitation** — document in Phase 5 closure narrative; future cycle adds subprocess-side exception serialization

**Q4 (JSON schema versioning)**:
- Option (a): Add `schema_version: 1` field for future-proofing
- Option (b): No version field; rely on field presence for migration

**Architect lean: (a)** — cheap forward-compat (~1 LOC); dashboard readers can branch on version.

**Q5 (File naming convention)**:
- Option (a): `{task_name}_{YYYY-MM-DDTHHMMSS}_{micros}.json` — sortable + sub-second collision-resistant
- Option (b): `{task_name}_{uuid4}.json` — collision-free, not sortable
- Option (c): `{uuid4}.json` — collision-free, no task_name in filename (must parse JSON to filter)

**Architect lean: (a)** — sortable filenames help operators eyeball recent crashes via `ls`; sub-second granularity sufficient for realistic crash rates.

**Q6 (Cleanup trigger location)**:
- Option (a): `pipeline._dream_loop` (matches `archive_old_conversation_log` cadence)
- Option (b): `pipeline._health_log_loop` (every 5 min — too frequent)
- Option (c): New dedicated background task (overkill for a ~1ms file-glob + unlink operation)

**Architect lean: (a)** — matches existing cleanup-loop precedents.

**Q7 (Retention default)**:
- Option (a): 7 days
- Option (b): 30 days
- Option (c): Indefinite (operator must manually clean)

**Architect lean: (a)** — 7 days is sufficient for post-mortem analysis; disk impact negligible. Operator-tunable via `core/config.py`.

**Q8 (Dashboard exposure scope)**:
- Option (a): P0.R11 ships HealthSnapshot field + format_health_alerts mention only; dedicated dashboard browser page is follow-up cycle
- Option (b): P0.R11 ships HealthSnapshot + dedicated `/api/crash-logs` Next.js route + browser UI

**Architect lean: (a)** — keeps P0.R11 scope SMALL-MEDIUM. Dashboard browser is genuine follow-up work.

**Q9 (Standalone value framing)**:
- Option (a): API designed for broader use (`persist_crash_diagnostic(task_name, exc, ...)` accepts any task_name); P0.R11 ships heavy-worker integration only
- Option (b): API tightly coupled to heavy-worker (only `run_heavy` calls it)

**Architect lean: (a)** — per auditor's "standalone value beyond heavy-worker pools" framing at P0.R8 closure. API foundation enables future cycle to call from asyncio task crash handlers, dream-loop crash handlers, etc.

---

## §8 Doctrine-firing projections at closure

If P0.R11 closes cleanly with closure-actual = 9 anchors at exact mid:

- `### Phase-0-granular-decomposition-enables-accurate-estimates` 23 → 24 supporting
- `Doctrine-prediction-precision-improving-over-arc` **3rd consecutive 0%-streak rebuild instance** (P0.R6.Z 1st + P0.R8 2nd + P0.R11 3rd; watch criteria 5+ for sub-observation elevation)
- `### Pre-audit-quantifier-precision-refined-by-grep` STAYS at 8 instances (clean-confirmation per operational rule 3 — **2nd consecutive negative-evidence validation** since elevation)
- `### Phase-0-catches-wrong-premise` STAYS at 13 (premise correct)
- `### Zero-precision-items-at-auditor-review` 25 → 27 (Phase 0 + Plan v1 if cycle clears cleanly)
- OPTIONAL-Plan-v2 sub-rule track record 12 → 13 proof cases (if 3-artifact cycle ships)
- `### Architect-reads-production-code-before-sign-off` 22 → 23 at closure-audit (6th-cycle self-sustaining adoption per `Implicit-doctrine-firings-not-narrative-tracked` operational rule)
- Strict-industry-standard mode 86 → 89 applications + 25 → 26 closures
- Spec-first review cycle 95 → 98-for-98 at closure
- `### Grep-baseline-before-drafting` 53 → 56 instances
- Cross-cycle-handoff transparency 59 → 62 successful
- Spec-time grep-verification 63 → 66 instances
- `### Twin-filename-pitfall-prevention` 24 → 25 preventive events
- Auditor-Q5-estimates-trail-grep 29 → 30 banked closures
- Deferred-canary strategy 27 → 28 applications

---

## §9 Architect-handoff items for auditor verdict

1. **Pass-2 grep verification** (per `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` doctrine): independent re-grep §1.1 4-row + §1.2 7-row + §1.3 4-row + §1.4 4-row + §1.6 7-row cross-spec table. **CODE-TEMPLATE-MISIDENTIFICATION sub-shape risk-check**: §2 D1+D2+D3+D4 code templates reference `FACES_DIR` (config.py:9 ✓), `json`/`traceback`/`logging`/`Path` (stdlib), P0.R8 D2 wrapper (heavy_worker.py:182-187 ✓), `_dream_loop` (pipeline.py:3424 ✓). All references grep-verifiable.

2. **Q1-Q9 adjudication**: confirm architect leans OR substitute. Q1 (call site sync with crash) + Q3 (limitation acknowledgment) + Q9 (standalone API design) are LOAD-BEARING; Q2-Q8 are implementation refinements.

3. **Anchor count adjudication**: confirm mid 9 INCLUSIVE ±15% band [7.65, 10.35] OR substitute.

4. **2nd clean-confirmation for `### Pre-audit-quantifier-precision-refined-by-grep`**: per §6 banking, Phase 0 grep CONFIRMS pre-audit framing — doctrine STAYS at 8 instances. Confirm this is correct application of operational rule 3 (2 consecutive clean-confirmations since elevation = empirical validation of negative-evidence semantic).

5. **P0.R11 scope boundary**: Q5-Q8 OUT-OF-SCOPE items (subprocess-side exception capture / broader exception capture / dedicated dashboard page / crash log compression) explicitly deferred. Confirm Phase 0 scope is appropriately bounded.

---

**End of Phase 0 audit.** Ready for auditor verdict.
