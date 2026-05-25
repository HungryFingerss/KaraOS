# P0.R11 — Crash diagnostic capture (Plan v1)

**Date**: 2026-05-25
**Author**: architect (Claude)
**Phase 0 verdict**: ACCEPTED with 0 BLOCKING PIs + 1 non-blocking observation (Plan v1 §5 implementation-step enumeration gap; absorbed at §5 + §3 A6 specification refinement). 9/9 Q-questions RATIFIED per architect leans.
**Cycle shape**: SMALL-MEDIUM band, 3-artifact OPTIONAL-Plan-v2 path candidate (13th proof case if Plan v1 clears cleanly)

---

## §0 Non-blocking observation absorption

**Observation 1 (auditor Phase 0 §Recommendation)**: Plan v1 §5 implementation phase MUST enumerate 3 non-trivial mutation steps explicitly, NOT just show the FINAL state of `run_heavy` post-modification. The outer `except Exception: pass` at the P0.R11 try-block would silently swallow a `NameError` from missing `import traceback`, masking the missing-feature bug.

**Absorption**:

1. **§5 Phase 1 expanded** to enumerate 3 sub-steps explicitly (X.1: add `import traceback` + X.2: change `except ... :` → `except ... as e:` + X.3: insert P0.R11 try-block).
2. **§3 A6 specification refined**: behavioral component MUST invoke `run_heavy` with monkeypatched pool raising `BrokenProcessPool`, then verify a JSON crash log file is written + contains non-empty `stack_trace` field. NOT just AST source-inspection that the `persist_crash_diagnostic` call exists.

**Banking event**: this absorption is a **clean Plan v1 PI absorption** of an auditor's non-blocking observation. Same family as P0.R6.Y / P0.R8 non-blocking observation handling. No `Plan-v1-Pass-2-grep-undercount` instance fires (observation is implementation-step enumeration, not enumeration drift).

---

## §1 Pass-2 grep verification (architect-side, per `### Pass-2-grep-auditor-verified-before-Plan-v1-approval`)

### §1.1 P0.R8 crash recording infrastructure (Phase 0 §1.1 LOCKED; re-verified at Plan v1 draft)

Identical to Phase 0 §1.1; auditor Pass-2 confirmed all 4 line refs (55-70 / 182-187 / 73-87 / 90-94).

### §1.2 Existing `faces/` directory conventions (Phase 0 §1.2 LOCKED)

Identical to Phase 0 §1.2; auditor Pass-2 confirmed all 7 references.

### §1.3 Cleanup-loop precedents (Phase 0 §1.3 LOCKED)

Identical to Phase 0 §1.3; auditor Pass-2 confirmed `archive_old_conversation_log` at db.py:301 + dream-loop call at pipeline.py:3424 + `DISK_MONITORED_DIRS` at config.py:1564.

### §1.4 HealthSnapshot integration surface (Phase 0 §1.4 LOCKED)

Identical to Phase 0 §1.4; auditor Pass-2 confirmed dataclass at health.py:37-80 + existing P0.R8 fields at lines 70 / 76.

### §1.5 P0.4 silent-except policy interaction (Phase 0 §1.5 LOCKED)

Identical to Phase 0 §1.5; auditor Pass-2 confirmed LOAD-BEARING interaction.

### §1.6 Current `core/heavy_worker.py` import state (Plan v1 NEW — surfaces Observation 1 absorption)

Auditor's independent grep verified at Phase 0 verdict:

```
core/heavy_worker.py imports (lines 27-33):
- asyncio
- concurrent.futures
- functools
- multiprocessing as mp
- threading
- time
- typing.Any, Callable

NOT IMPORTED:
- traceback  ← REQUIRED for Phase 5 D2 modification (P0.R11)
```

**Phase 5 Step 1 mutation**: add `import traceback` at top of `core/heavy_worker.py`.

### §1.7 Current `core/heavy_worker.py` except binding state (Plan v1 NEW — surfaces Observation 1 absorption)

Production code at `core/heavy_worker.py:184`:

```python
except concurrent.futures.process.BrokenProcessPool:
    _record_pool_crash(task_name)
    raise
```

**Phase 5 Step 2 mutation**: change `except concurrent.futures.process.BrokenProcessPool:` → `except concurrent.futures.process.BrokenProcessPool as e:` (add binding for `e` so `persist_crash_diagnostic(task_name, e, ...)` can access the exception object).

### §1.8 Cross-spec interactions (Phase 0 §1.6 LOCKED)

Identical to Phase 0 §1.6; 7-row cross-spec table all consistent.

---

## §2 D-decision spec (5 D-decisions; Q1-Q9 RATIFIED)

### §2.1 D1 — `core/crash_logs.py` NEW module

**LOCKED** per Phase 0 §2.1 code template. Module-level `_CRASH_LOG_SCHEMA_VERSION = 1` + 3 public functions:

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
import time
import traceback as _traceback  # NOTE: only used if caller doesn't pass traceback_str
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_CRASH_LOG_SCHEMA_VERSION = 1


def _crash_log_dir() -> Path:
    """Return crash_logs/ subdir under FACES_DIR; auto-create on first call.

    Per P0.4 silent-except policy: if FACES_DIR is unwritable (extreme
    failure mode), this raises at mkdir — persist_crash_diagnostic's outer
    try/except catches + logs, returning None.
    """
    from core.config import FACES_DIR
    d = FACES_DIR / "crash_logs"
    d.mkdir(exist_ok=True, parents=True)
    return d


def persist_crash_diagnostic(
    task_name: str,
    exc: "BaseException",
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
    denied, unwritable FACES_DIR) is logged + swallowed; returns None on
    failure. The original crash propagation via run_heavy's bare `raise`
    is UNAFFECTED.

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
    try:
        log_dir = _crash_log_dir()
    except Exception as e:  # OPTIONAL: dir-create failure
        logger.warning(
            "[CrashLogs] prune_old_crash_logs: dir access failed: %s: %s",
            type(e).__name__, e,
        )
        return 0
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
    try:
        log_dir = _crash_log_dir()
    except Exception as e:  # OPTIONAL: dir-create failure
        logger.warning(
            "[CrashLogs] list_recent_crash_logs: dir access failed: %s: %s",
            type(e).__name__, e,
        )
        return []
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

### §2.2 D2 — `run_heavy` wrapper extension (3-step Phase 5 mutation per Observation 1 absorption)

**LOCKED**. Three explicit mutation steps on `core/heavy_worker.py`:

**Step 2.2.a** — Add import at top of file (after existing `import threading` at line 30):

```python
import traceback
```

**Step 2.2.b** — Change `except` binding at line 184 from bare to `as e`:

```python
# BEFORE
except concurrent.futures.process.BrokenProcessPool:
# AFTER
except concurrent.futures.process.BrokenProcessPool as e:
```

**Step 2.2.c** — Insert P0.R11 try-block between `_record_pool_crash(task_name)` (line 186) and `raise` (line 187):

```python
# AFTER mutation (replaces lines 182-187)
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

### §2.3 D3 — `HealthSnapshot` extension + format_health_line + format_health_alerts

**LOCKED** per Phase 0 §2.3:

1. **`HealthSnapshot` dataclass field**: `recent_crash_logs: "list[dict]" = field(default_factory=list)`
2. **`gather_health_snapshot` extension**: import + call `list_recent_crash_logs(HEALTH_CRASH_LOG_RECENT_LIMIT)`
3. **`format_health_line` conditional emit**: `parts.append(f"crash_logs={len(recent_crash_logs)}")` when non-empty
4. **`format_health_alerts` actionable alert**: includes verbatim substrings `"Recent crash logs available"` + `"check faces/crash_logs/"` + `"CRASH_LOG_RETENTION_DAYS"`

### §2.4 D4 — Cleanup wired into `pipeline._dream_loop`

**LOCKED** per Phase 0 §2.4. After existing cleanup calls in `_dream_loop`:

```python
from core.crash_logs import prune_old_crash_logs
from core.config import CRASH_LOG_RETENTION_DAYS
_removed = await loop.run_in_executor(None, prune_old_crash_logs, CRASH_LOG_RETENTION_DAYS)
if _removed > 0:
    print(f"[CrashLogs] dream-loop pruned {_removed} crash logs older than {CRASH_LOG_RETENTION_DAYS}d")
```

### §2.5 D5 — `core/config.py` constants

**LOCKED** per Phase 0 §2.5:

```python
# P0.R11 — crash diagnostic capture
CRASH_LOG_RETENTION_DAYS         = 7      # files older than N days pruned at dream loop
HEALTH_CRASH_LOG_RECENT_LIMIT    = 10     # HealthSnapshot.recent_crash_logs cap
CRASH_LOG_SCHEMA_VERSION         = 1      # JSON payload schema version
```

### §2.6 Deliberate-regression scenarios (9 scenarios for 9 anchors)

| Revert | Expected anchor fire | Catches |
|---|---|---|
| (a) Delete `core/crash_logs.py` module entirely | A1 | Module gone |
| (b) Replace `persist_crash_diagnostic` body with `return None` unconditionally | A2 + A3 | No JSON file written; behavioral test fails |
| (c) Remove `prune_old_crash_logs` body's `path.unlink()` call | A4 | Files older than retention NOT removed |
| (d) Replace `list_recent_crash_logs` body with `return []` | A5 | No recent entries returned |
| (e) **Remove `persist_crash_diagnostic` call from `run_heavy` wrapper** | **A6** | **Behavioral test fails — no JSON file written during BrokenProcessPool simulation; defense against missing-import silent-masking shape** |
| (f) Remove `recent_crash_logs` field from `HealthSnapshot` | A7 | Field missing |
| (g) Remove `prune_old_crash_logs` call from `_dream_loop` | A8 | Cleanup not wired |
| (h) Delete any 1 of 3 config constants | A9 | Constant missing |
| (i) **Revert Phase 5 Step 2.2.a (remove `import traceback`)** | **A6 behavioral component** | **`NameError: name 'traceback' is not defined` raised inside `run_heavy`'s P0.R11 try-block; outer `except Exception: pass` swallows it; behavioral test still detects via "no JSON file written" assertion** |

9/9 1:1 mapping. Scenarios (e) + (i) jointly cover the missing-import silent-masking shape that auditor's Observation 1 flagged.

---

## §3 Logical anchor LOCK (Q5 LOCK = 9 anchors at EXACT MID; A6 REFINED per Observation 1)

Per auditor Phase 0 verdict §4 Q5 ratification: **9 anchors at exact mid 9 INCLUSIVE ±15% band [7.65, 10.35]**.

| # | Anchor | Surface | Coverage |
|---|---|---|---|
| A1 | `core/crash_logs.py` module exists with `persist_crash_diagnostic` + `prune_old_crash_logs` + `list_recent_crash_logs` functions + `_CRASH_LOG_SCHEMA_VERSION` module-level constant | Source-inspection | D1 |
| A2 | `persist_crash_diagnostic` writes JSON file to `FACES_DIR/crash_logs/{task_name}_{YYYY-MM-DDTHHMMSS}_{micros}.json` (behavioral test with crafted exception + verify file existence + correct path) | Behavioral | D1 |
| A3 | JSON payload includes ALL 7 fields: `schema_version` + `task_name` + `timestamp` + `exception_type` + `exception_message` + `stack_trace` + `crash_count` (behavioral test with crafted exception + parse written file + verify field presence) | Behavioral | D1 |
| A4 | `prune_old_crash_logs(retention_days)` removes files with mtime older than `retention_days * 86400` seconds (behavioral test with backdated mtime + verify removal count) | Behavioral | D1 |
| A5 | `list_recent_crash_logs(limit)` returns most recent N entries sorted by mtime descending (behavioral test with N files + verify ordering + limit truncation) | Behavioral | D1 |
| **A6** | **`run_heavy` wrapper INVOKES `persist_crash_diagnostic` on `BrokenProcessPool`. Behavioral test (REFINED per Observation 1): monkeypatch pool to raise `BrokenProcessPool`; invoke `run_heavy`; verify a JSON crash log file exists at `FACES_DIR/crash_logs/` AND its `stack_trace` field is non-empty. Defense against missing-import silent-masking shape — AST source-inspection alone would pass even if `import traceback` was missing because outer `except Exception: pass` swallows the `NameError`.** | **Behavioral (NOT just source-inspection)** | D2 |
| A7 | `HealthSnapshot.recent_crash_logs: list[dict]` field present + `format_health_line` conditional emits `crash_logs=N` field when non-empty + `format_health_alerts` includes verbatim substrings (`Recent crash logs available`, `check faces/crash_logs/`, `CRASH_LOG_RETENTION_DAYS`) | Source-inspection + behavioral | D3 |
| A8 | `_dream_loop` body AST shows call to `prune_old_crash_logs(CRASH_LOG_RETENTION_DAYS)` via `loop.run_in_executor(None, prune_old_crash_logs, ...)` (AST source-inspection) | AST | D4 |
| A9 | 3 config constants present: `CRASH_LOG_RETENTION_DAYS` + `HEALTH_CRASH_LOG_RECENT_LIMIT` + `CRASH_LOG_SCHEMA_VERSION` (source-inspection) | Source-inspection | D5 |

---

## §4 Honest-count commitment (per `Explicit-closure-honest-count-commitment` discipline)

Closure-actual count will land at exactly **9 anchors** per Plan v1 LOCK. ON-TARGET range is 8-10. If implementation reveals a 10th anchor warranting addition (e.g. additional defense-in-depth for missing-import shape at developer Phase 5), closure-narrative SHALL bank as ON-TARGET +11.1% per band table. Closure-actual UNDER 8 OR OVER 10 SHALL invoke the honest-narrative path.

**21st instance of `Explicit-closure-honest-count-commitment` discipline** banked here at Plan v1 §4 (MADE); closure HONORED at closure-audit firing 22nd instance per STRICT separation locked at P0.B3.

---

## §5 Phase-by-phase implementation plan (EXPANDED per Observation 1 absorption)

**Phase 1 — `core/crash_logs.py` NEW module + `core/heavy_worker.py` 3-step mutation (D1 + D2)** (~45 min):

1. **Create `core/crash_logs.py`** per §2.1 spec. 3 public functions + 1 module-level constant + JSON-write/-read/-prune logic.
2. **Open `core/heavy_worker.py`**. Apply the 3 mutation sub-steps to D2 wrapper:
   - **Step 1.2.a**: Add `import traceback` at top of file (alphabetically positioned after existing `import threading` at line 30).
   - **Step 1.2.b**: Change `except concurrent.futures.process.BrokenProcessPool:` (line 184) → `except concurrent.futures.process.BrokenProcessPool as e:`.
   - **Step 1.2.c**: Insert P0.R11 try-block between `_record_pool_crash(task_name)` (line 186) and `raise` (line 187) per §2.2.c code block.
3. **Verify mutation correctness via Pass-3 grep**: confirm `import traceback` present at top + `as e:` binding at line ~184 + `from core.crash_logs import persist_crash_diagnostic` inside inner try-block + `traceback.format_exc()` call present.

**Phase 2 — `core/config.py` constants (D5)** (~5 min):

1. Add 3 constants per §2.5 at end of `core/config.py` (or near other observability constants).

**Phase 3 — `core/health.py` extension (D3)** (~20 min):

1. Add `recent_crash_logs: "list[dict]" = field(default_factory=list)` to `HealthSnapshot` dataclass.
2. Update `gather_health_snapshot` to populate from `list_recent_crash_logs(HEALTH_CRASH_LOG_RECENT_LIMIT)`.
3. Extend `format_health_line` with conditional `crash_logs=N` emit when non-empty.
4. Extend `format_health_alerts` with verbatim-substring alert per §2.3.

**Phase 4 — `pipeline._dream_loop` cleanup wiring (D4)** (~10 min):

1. Insert `prune_old_crash_logs(CRASH_LOG_RETENTION_DAYS)` call after existing cleanup calls in `_dream_loop` per §2.4 code block.

**Phase 5 — Test surface (`tests/test_p0_r11_crash_diagnostics.py` NEW)** (~75 min):

1. Create `tests/test_p0_r11_crash_diagnostics.py`.
2. Implement **9 anchors** per §3 LOCK using same shape as `tests/test_p0_r8_heavy_worker_watchdog.py` precedent.
3. **A6 behavioral implementation per Observation 1 specification**: monkeypatch `hw._HEAVY_WORKER_POOLS["test_pool"]` with a pool that raises `BrokenProcessPool` on `submit()`; invoke `hw.run_heavy("test_pool", fake_fn)`; verify JSON file exists at `FACES_DIR/crash_logs/` AND `stack_trace` field is non-empty. This catches both Step 2.2.a (missing `import traceback`) AND Step 2.2.b (missing `as e:` binding) silent-masking shapes.
4. Run 9/9 deliberate-regression confirmations per §2.6 table. Specifically run revert (i) to confirm A6 behavioral catches missing-import shape.
5. Full suite verification — expect 2722 + 9 = 2731 passing post-P0.R11 closure.

**Phase 6 — Closure narrative + audit (~25 min)**:

1. Update `CLAUDE.md` line 3 test count.
2. Bank P0.R11 closure entry with all explicit X → Y narrative lines per Plan v1 §10 item 4.
3. Architect closure-audit Path C grep-verify against production code.
4. **Phase 7 attention items**: bank `feedback_pass_2_grep_caught_real_gap_subshape.md` extension — CODE-TEMPLATE-MISIDENTIFICATION sub-shape validated in BOTH modes (P0.R8 caught + P0.R11 preventive). Update MEMORY.md if changes needed.

---

## §6 Closure-projection band table + doctrine outcomes

| closure-actual | overage vs mid 9 | band | doctrine outcome |
|---|---|---|---|
| 7 | −22.2% | SLIGHT-DRIFT-DOWN (within ±30%) | `### Phase-0-granular-decomposition` HOLDS at 23 supporting |
| 8 | −11.1% | ON-TARGET | `### Phase-0-granular-decomposition` 23 → 24 supporting |
| 9 | 0% | ON-TARGET exact mid | `### Phase-0-granular-decomposition` 23 → 24 supporting + **3rd consecutive 0%-streak rebuild instance** (P0.R6.Z 1st + P0.R8 2nd + P0.R11 3rd; watch criteria 5+ for sub-observation extension) |
| 10 | +11.1% | ON-TARGET | `### Phase-0-granular-decomposition` 23 → 24 supporting |
| 11 | +22.2% | SLIGHT-DRIFT-UP (within ±30%) | `### Phase-0-granular-decomposition` HOLDS at 23 supporting |
| ≥12 OR ≤6 | beyond ±30% | FALSIFICATION TRIGGER | doctrine demotes back to architect-memory + reasoning audit |

---

## §7 Pass-3 grep verification baseline (architect-side at closure-narrative drafting)

3-artifact OPTIONAL-Plan-v2 cycle has 4 grep-verify checkpoints:

- Architect Pass-1 grep at Phase 0 baseline ✓
- Auditor Pass-2 grep at Phase 0 verdict ✓ (zero PIs; 1 non-blocking observation absorbed at Plan v1)
- Architect Pass-2 grep at Plan v1 §1 (this artifact) ✓ (Plan v1 ADDS §1.6 + §1.7 for Observation 1 absorption documentation; rest identical to Phase 0)
- Auditor Pass-2 grep at Plan v1 verdict (standing flag per `### Pass-2-grep-auditor-verified-before-Plan-v1-approval`)
- Architect Pass-3 grep at closure-narrative drafting (catches developer Phase 5 implementation drift if any)

If Pass-3 surfaces enumeration drift, `Plan-v1-Pass-2-grep-undercount` 11 → 12 candidate AT ARCHITECT-SIDE.

---

## §8 Discipline-counter projections (locked +1-per-artifact)

Per locked convention: 3-artifact OPTIONAL-Plan-v2 cycle (Phase 0 + Plan v1 + closure) increments discipline counters by +1 per artifact.

Baseline post-P0.R8 closure (2026-05-25):

| Discipline | Baseline | Plan v1 close (this artifact) | P0.R11 closure projection |
|---|---|---|---|
| Strict-industry-standard mode applications | 86 | 88 | 89 |
| Strict-mode successful closures | 25 | 25 | 26 |
| Spec-first review cycle | 95-for-95 | 97-for-97 | 98-for-98 |
| `### Grep-baseline-before-drafting` instances | 53 | 55 | 56 |
| Cross-cycle-handoff transparency successful | 56 | 58 | 59 |
| Spec-time grep-verification instances | 63 | 65 | 66 |
| `### Twin-filename-pitfall-prevention` preventive events | 24 | stays 24 | 25 |
| Auditor-Q5-estimates-trail-grep banked closures | 29 | 29 | 30 |
| Deferred-canary strategy applications | 27 | 27 | 28 |

**OPTIONAL-Plan-v2 path candidacy**: if auditor returns 0 precision items at this Plan v1 review (Observation 1 already absorbed cleanly), cycle ships as 3-artifact. **13th OPTIONAL-Plan-v2 proof case candidate post-closure**.

**`### Pre-audit-quantifier-precision-refined-by-grep`**: STAYS at 8 instances per operational rule 3 (Phase 0 grep CONFIRMED pre-audit framing; 2nd consecutive clean-confirmation since elevation).

**CODE-TEMPLATE-MISIDENTIFICATION sub-shape track record** (per `feedback_pass_2_grep_caught_real_gap_subshape.md`):
- 1st caught instance: P0.R8 PI #1 (caught at auditor's Pass-2 grep)
- 1st preventive-application instance: P0.R11 Phase 0 (architect's proactive grep-verify upfront)
- Sub-shape now validated in BOTH modes (caught + preventive) at 1 instance each

---

## §9 Locked Q1-Q9 adjudication (per auditor Phase 0 verdict RATIFIED)

| Q | Locked | Implementation effect |
|---|---|---|
| Q1 (LOAD-BEARING) | (a) sync with crash detection | persist_crash_diagnostic called from `run_heavy` BrokenProcessPool except block; preserves timing precision + exception object access |
| Q2 | (a) `traceback.format_exc()` | Simpler; both forms equivalent inside except |
| Q3 (LOAD-BEARING) | ACKNOWLEDGE as Known Limitation | BrokenProcessPool main-process-side trace; subprocess-side exception capture is follow-up cycle |
| Q4 | (a) `schema_version=1` field | Cheap forward-compat |
| Q5 | (a) sortable + sub-second granularity filename | Operator UX |
| Q6 | (a) `_dream_loop` cleanup trigger | Matches archive_old_conversation_log cadence |
| Q7 | (a) 7 days retention | Operator-tunable; negligible disk impact |
| Q8 | (a) HealthSnapshot field only | Dashboard browser is follow-up cycle |
| Q9 (LOAD-BEARING) | (a) generic API design | API foundation enables broader exception capture follow-up |

---

## §10 Architect-handoff items for auditor verdict

1. **Pass-2 grep verification** (per `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` doctrine): independent re-grep §1.1-§1.8 surface tables. Plan v1 ADDS §1.6 (import state) + §1.7 (except-binding state) for Observation 1 absorption documentation. Confirm both sub-tables match production state.

2. **Q1-Q9 adjudication**: confirm architect leans match Phase 0 RATIFY verdict (zero changes).

3. **Anchor count adjudication**: confirm mid 9 INCLUSIVE ±15% band [7.65, 10.35]. A6 REFINED per Observation 1 (behavioral verification of `persist_crash_diagnostic` invocation, NOT just AST source-inspection).

4. **Observation 1 absorption verification**: §5 Phase 1 enumerates 3 mutation sub-steps explicitly. §2.6 deliberate-regression scenarios (e) + (i) jointly cover missing-import silent-masking shape. §3 A6 specification refined.

5. **CODE-TEMPLATE-MISIDENTIFICATION sub-shape preventive-application banking**: Plan v1 §8 documents 1st preventive-application instance under `feedback_pass_2_grep_caught_real_gap_subshape.md`. Sub-shape now validated in BOTH modes (P0.R8 caught + P0.R11 preventive). Memory file extension at Phase 6 closure-audit.

6. **Closure-audit Path C grep-verify items** (banked for architect closure-audit at Phase 6):
   - Verify `core/crash_logs.py` exists with all 3 functions + `_CRASH_LOG_SCHEMA_VERSION` constant
   - Verify `core/heavy_worker.py` has `import traceback` at top + `except ... as e:` at line ~184 + `from core.crash_logs import persist_crash_diagnostic` inside inner try-block
   - Verify `HealthSnapshot.recent_crash_logs` field + format_health_line emit + format_health_alerts text
   - Verify `_dream_loop` calls `prune_old_crash_logs(CRASH_LOG_RETENTION_DAYS)`
   - Verify 3 config constants in `core/config.py`
   - Verify 9 anchors in `tests/test_p0_r11_crash_diagnostics.py`
   - Verify A6 behavioral test invokes monkeypatched `BrokenProcessPool` + verifies JSON file with non-empty `stack_trace`

7. **Closure-narrative explicit doctrine X → Y lines** (per `Implicit-doctrine-firings-not-narrative-tracked` 6th-cycle self-sustaining adoption):
   - `### Architect-reads-production-code-before-sign-off` 22 → 23 with explicit narrative line (6th-cycle self-sustaining adoption)
   - `### Pre-audit-quantifier-precision-refined-by-grep` STAYS at 8 (2nd consecutive clean-confirmation per operational rule 3 — empirical validation continues)
   - `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` 11th consecutive cycle validated; clean-pass mode (8 clean + 2 caught-real-gap track record)
   - `### Zero-precision-items-at-auditor-review` 25 → 27 (Phase 0 CLEAN + Plan v1 CLEAN if cycle clears cleanly)
   - `### Phase-0-catches-wrong-premise` STAYS at 13 (premise correct)
   - `### Phase-0-granular-decomposition-enables-accurate-estimates` 23 → 24 IF closure-actual ∈ [8, 10]
   - `Doctrine-prediction-precision-improving-over-arc` 3rd consecutive 0%-streak rebuild instance IF closure-actual = 9 exact (watch criteria 5+ for sub-observation extension)
   - OPTIONAL-Plan-v2 sub-rule track record 12 → 13 proof cases (if 3-artifact cycle ships)
   - CODE-TEMPLATE-MISIDENTIFICATION sub-shape: 1 caught + 1 preventive instance both validated; sub-shape validated in BOTH modes
   - Cross-cycle-handoff transparency 56 → 59 (Q9 standalone-API framing honors P0.R8 closure-time recommendation; banked per auditor's Cross-doctrine observation)
   - `### Twin-filename-pitfall-prevention` 24 → 25 preventive events at closure
   - Strict-mode 86 → 89 + 25 → 26 closures
   - Spec-first 95 → 98-for-98 at closure

---

**End of Plan v1.** Ready for auditor verdict.
