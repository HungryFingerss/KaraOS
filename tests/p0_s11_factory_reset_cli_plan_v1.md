# P0.S11 Plan v1 — Factory reset path audit + standalone CLI tool

**References:** `tests/p0_s10_s11_s12_canary_day1_bundle_audit.md` §2 (Phase 0).

**Canary source-of-truth:** `terminal_output_2026-05-27_115642.md` lines 2-38 (factory reset claim vs DB state mismatch — partial reset only deleted `.dashboard_token`; faces.db + brain.db + Kuzu graph survived).

**Sibling spec context:** Plan v1 #2 of 3 in the canary-Day-1 bundled audit. P0.S12 RATIFIED + ready for Phase 4 (8th `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` application, clean). P0.S10 next (per §4.2 shipping order).

**Cycle shape proposal:** OPTIONAL-Plan-v2 path (architect's lean — Pass-2 grep widened scope BEFORE auditor review; pre-mortem covers known risks). If auditor returns ≥1 PI, cycle escalates to 4-artifact.

---

## §1 Architect-side Pass-2 grep (scope widening + existing-surface audit)

**Phase 0 framing:** 3 D-decisions (NEW CLI script + summary log in wipe_all + runbook reference). Estimated 6 anchors.

**Pass-2 grep findings (architect, this Plan v1):**

### §1.1 Surface audit — existing factory reset entry points

Grep verified there are **exactly 3 existing reset entry points** (no others hidden):

| # | Entry point | Caller | When live | When offline |
|---|---|---|---|---|
| 1 | `core.db.wipe_all()` programmatic API | Python code (pipeline + tests) | Caller must close DB connections first | Direct call OK |
| 2 | Dashboard `POST /api/factory-reset` (`dog-ai-dashboard/app/api/factory-reset/route.ts`) | User via dashboard UI | Sends IPC via `reset_request.json` → pipeline handler | Node.js wipes files directly (mirrors wipe_all in JS) |
| 3 | Pipeline runtime IPC handler at `pipeline.py:6932-6979` | Polls `RESET_REQUEST_FILE.exists()` in main loop | Calls `wipe()` → `close()` → `wipe_all()` → re-init | n/a (pipeline must be running to detect IPC) |

**Gap confirmed:** **NO STANDALONE CLI** for factory reset exists. `tools/factory_reset.py` does not exist (verified via Glob earlier in Phase 0). The canary runbook at `tests/canary_week_2026-05-26.md:39` references it as if it does — that reference is stale.

### §1.2 wipe_all body audit (`core/db.py:1984-2063`)

Grep + Read verified the 10 distinct delete groups:

| Group | Target | Failure mode (existing) |
|---|---|---|
| 1 | `faces.db` + `faces.db-shm` + `faces.db-wal` | `print(f"[Reset] Could not delete {p.name}: {e}")` per-file |
| 2 | `faiss.index` | Same per-file pattern |
| 3 | `brain.db` + `brain.db-shm` + `brain.db-wal` | Same |
| 4 | `brain_graph/` directory (Linux) OR file (Windows) | Same, via `shutil.rmtree` (dir) OR `unlink` (file) |
| 5 | `brain_graph.wal` + `brain_graph-lock` | Same |
| 6 | `faces/*.jpg` photos (glob) | Per-photo unlink |
| 7 | `ENROLL_REQUEST_FILE`, `ENROLL_RESULT_FILE`, `RESET_REQUEST_FILE`, `RESET_RESULT_FILE` IPC files | Same |
| 8 | `sim_session_state.json` (project root) | Same |
| **Preserved** | `.dashboard_token` + `.dashboard_auth_url` | **P0.S2 INVARIANT** documented at lines 1991-1998 |

**Critical:** wipe_all has **NO success-summary log**. On clean execution, the only output is silence (the per-file error logs fire only on failure). The user has no visible signal that the function actually ran or what was deleted. THIS is the canary's diagnostic gap — Jagan's "factory reset" produced no log evidence whatsoever, leaving him unable to confirm it ran.

### §1.3 Existing test surfaces (preserve semantics)

5 existing tests touch factory-reset paths — Plan v1 D2 MUST NOT break any of them:

| Test file | Test name | Existing invariant | Plan v1 impact |
|---|---|---|---|
| `tests/test_dashboard_token.py:221` | `test_wipe_all_preserves_dashboard_token` | `.dashboard_token` survives `wipe_all()` call | **UNCHANGED** by P0.S11 — D2 summary doesn't delete the preserved token |
| `tests/test_classifier_db.py:329` | `test_factory_reset_does_not_touch_classifier_db` | `data/` dir is outside `wipe_all()` scope | **UNCHANGED** — D2 summary won't claim to delete anything outside FACES_DIR |
| `tests/test_dashboard_auth_route.py:251` | `test_factory_reset_route_preserves_dashboard_token` | Dashboard route preserves token | **UNCHANGED** — Plan v1 doesn't touch the Node.js route |
| `tests/test_dashboard_middleware.py:123` | `test_factory_reset_is_gated_by_middleware` | `/api/factory-reset` requires auth | **UNCHANGED** — Plan v1 doesn't touch middleware |
| `tests/test_scene_block_cache.py:110` | `test_factory_reset_clears_cache` | Pipeline runtime path clears cache on reset | **UNCHANGED** — D2 summary doesn't touch the pipeline IPC path |

**One ripple-fix flagged for Phase 4:** if D2's summary log calls `Path.exists()` or `Path.stat()` to count actual deletions, the existing `test_wipe_all_preserves_dashboard_token` may need to ensure the test directory's `.dashboard_token` still exists post-call. Should be a no-op since the preservation invariant already holds, but worth a Phase 4 sanity-check.

### §1.4 Pipeline-liveness check requirement (Pass-2 scope widening)

The dashboard route at `dog-ai-dashboard/app/api/factory-reset/route.ts:71-79` has:
```typescript
function isPipelineLive(): boolean {
  try {
    if (!fs.existsSync(STATE_PATH)) return false
    const data = JSON.parse(fs.readFileSync(STATE_PATH, 'utf8'))
    return (Date.now() / 1000 - (data.updated_at || 0)) < 10
  } catch { return false }
}
```

If pipeline live → dashboard sends IPC via `reset_request.json`. If pipeline offline → dashboard wipes files directly.

**The standalone CLI MUST mirror this check.** Running `python tools/factory_reset.py --confirm` while pipeline is live would hit Windows file-locks on `faces.db` → cryptic `PermissionError 32` instead of an actionable error message. Phase 0 didn't anticipate this as a separate anchor — it's added now via D1.A4.

**Scope widening:** Phase 0 estimated 6 anchors. Plan v1 locks 7 (added D1 sub-anchor for pipeline-liveness check). +16.7% from Phase 0 mid — `### Pre-audit-quantifier-precision-refined-by-grep` SCALE-OF-WORK-AXIS sub-shape, 10th instance candidate (if elevated at closure).

---

## §2 D-decisions (LOCKED)

### D1 — `tools/factory_reset.py` NEW standalone CLI script

**Edit site:** NEW file at `tools/factory_reset.py`. Mirrors `tools/replay_session.py` shape:

```python
"""Standalone factory reset CLI — wipes faces.db / brain.db / FAISS / Kuzu / photos.

Preserves `.dashboard_token` and `.dashboard_auth_url` per P0.S2 invariant
(re-issuing auth URL on every reset is hostile UX; token is single-user-
scoped — no cross-tenant risk). Use --include-dashboard-token to override.

P0.S11 Plan v1 §2 D1 — addresses the 2026-05-27 canary day-1 diagnostic gap
where the user thought a factory reset had been performed but in fact only
`.dashboard_token` was removed; faces.db + brain.db + voice gallery survived.

Safety:
  - DEFAULT MODE = DRY RUN. Lists what WOULD be deleted; takes no destructive
    action. Requires explicit --confirm flag to actually delete.
  - PIPELINE-LIVENESS CHECK. Refuses to run if pipeline is currently active
    (Windows file-locks would make wipe_all() partially fail with cryptic
    PermissionError 32 messages). Polls faces/state.json::updated_at — if
    last update was within 10s, considers pipeline live.
  - .dashboard_token PRESERVED by default per P0.S2 invariant. Use
    --include-dashboard-token to delete it too (e.g. full re-init scenarios
    where dashboard auth needs re-issuance).

Usage:

    python tools/factory_reset.py                              # dry-run (default)
    python tools/factory_reset.py --confirm                    # actually wipe
    python tools/factory_reset.py --confirm --include-dashboard-token
    python tools/factory_reset.py --confirm --force            # bypass pipeline-liveness check (use ONLY when pipeline known stopped)

Exit codes:
    0   Success (dry-run completed OR wipe completed cleanly)
    1   Pipeline is live and --force not specified
    2   wipe_all() raised an exception
    3   --include-dashboard-token specified but token files couldn't be deleted

Spec: tests/p0_s11_factory_reset_cli_plan_v1.md
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core.db import wipe_all, FACES_DIR, DB_PATH, BRAIN_DB_PATH, FAISS_INDEX_PATH, GRAPH_DB_PATH


def _is_pipeline_live() -> bool:
    """Mirror of dashboard's isPipelineLive() heuristic — read faces/state.json,
    check if updated_at is within last 10 seconds. False on missing file or
    parse error (safer to assume offline + let wipe_all proceed than to
    refuse-and-leave-stuck)."""
    import json
    state_path = FACES_DIR / "state.json"
    if not state_path.exists():
        return False
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        updated_at = float(data.get("updated_at", 0))
        return (time.time() - updated_at) < 10.0
    except (json.JSONDecodeError, OSError, ValueError):
        return False


def _enumerate_targets(include_dashboard_token: bool) -> tuple[list[str], list[str]]:
    """Return (to_delete, to_preserve) lists for dry-run + summary purposes.
    Order matches wipe_all() body for grep-correspondence."""
    targets = [
        str(DB_PATH) + s for s in ("", "-shm", "-wal")
    ] + [
        str(FAISS_INDEX_PATH),
    ] + [
        str(BRAIN_DB_PATH) + s for s in ("", "-shm", "-wal")
    ] + [
        str(GRAPH_DB_PATH),
        str(GRAPH_DB_PATH) + ".wal",
        str(GRAPH_DB_PATH) + "-lock",
    ] + [
        str(p) for p in FACES_DIR.glob("*.jpg")
    ] + [
        str(FACES_DIR / "enroll_request.json"),
        str(FACES_DIR / "enroll_result.json"),
        str(FACES_DIR / "reset_request.json"),
        str(FACES_DIR / "reset_result.json"),
        str(FACES_DIR.parent / "sim_session_state.json"),
    ]
    preserved = [
        str(FACES_DIR / ".dashboard_token"),
        str(FACES_DIR / ".dashboard_auth_url"),
    ]
    if include_dashboard_token:
        targets.extend(preserved)
        preserved = []
    return targets, preserved


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Standalone factory reset for dog-ai (wipes faces.db / brain.db / FAISS / Kuzu / photos)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--confirm", action="store_true",
                        help="Actually perform the wipe (default: dry-run)")
    parser.add_argument("--include-dashboard-token", action="store_true",
                        help="Also delete .dashboard_token and .dashboard_auth_url (default: preserved per P0.S2)")
    parser.add_argument("--force", action="store_true",
                        help="Bypass pipeline-liveness check (use only when pipeline known stopped)")
    args = parser.parse_args()

    # Pipeline-liveness check (D1.A4)
    if not args.force and _is_pipeline_live():
        print(
            "[Reset] ERROR: Pipeline appears to be running "
            "(faces/state.json::updated_at within last 10s).\n"
            "Stop the pipeline first OR use the dashboard's /api/factory-reset endpoint\n"
            "(which sends IPC to the running pipeline). Override with --force ONLY if you\n"
            "are certain the pipeline is stopped.",
            file=sys.stderr,
        )
        return 1

    targets, preserved = _enumerate_targets(args.include_dashboard_token)

    # Dry-run mode (D1.A2 — default-deny safety gate)
    if not args.confirm:
        print("[Reset] DRY RUN — no files will be deleted.")
        print(f"[Reset] Would delete {len(targets)} target(s):")
        for t in targets:
            exists = "  ✓" if Path(t).exists() else "  ·"  # ✓ = exists, · = absent
            print(f"  {exists} {t}")
        print(f"[Reset] Would preserve {len(preserved)} target(s):")
        for p in preserved:
            exists = "  ✓" if Path(p).exists() else "  ·"
            print(f"  {exists} {p}")
        print("[Reset] To actually wipe, re-run with --confirm.")
        return 0

    # Real wipe (D1.A1 + D1.A3)
    print(f"[Reset] CONFIRMED — wiping {len(targets)} target(s) (preserving {len(preserved)})...")
    try:
        wipe_all()
        # D1.A3 — if --include-dashboard-token, ALSO delete the preserved files
        # (wipe_all preserves them per P0.S2; CLI's job is to override that
        # when the user explicitly asks for it)
        if args.include_dashboard_token:
            for p in [FACES_DIR / ".dashboard_token", FACES_DIR / ".dashboard_auth_url"]:
                try:
                    p.unlink(missing_ok=True)
                    print(f"[Reset] Deleted {p.name} (--include-dashboard-token)")
                except Exception as e:
                    print(f"[Reset] WARN: could not delete {p.name}: {e}", file=sys.stderr)
                    return 3
    except Exception as e:
        print(f"[Reset] ERROR: wipe_all() raised: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

**D1 sub-decision shape:**
- **D1.A1** — `tools/factory_reset.py` file exists with module docstring naming `P0.S11` + canary date
- **D1.A2** — `--confirm` flag default-deny; absent → dry-run mode (lists targets, exits 0 without action)
- **D1.A3** — `--include-dashboard-token` opt-in flag preserves token by default
- **D1.A4** — Pipeline-liveness check via `faces/state.json::updated_at` heuristic; refuses to run if pipeline live AND `--force` not specified

### D2 — Confirmation summary log in `wipe_all()` (`core/db.py:1984-2063`)

**Edit site:** `core/db.py::wipe_all()` body (immediately before the function returns at line 2063).

**Add a summary block** that probes file existence post-call to count actual deletions:

```python
    # P0.S11 D2 — Post-wipe summary so callers (CLI, dashboard, pipeline IPC)
    # see a clear log of what was deleted vs preserved. Without this, wipe_all
    # is silent on success — the 2026-05-27 canary surfaced exactly this
    # diagnostic gap (Jagan thought factory reset had run; no log proved it).
    # Probe Path.exists() post-call (NOT pre-call enumeration) so the count
    # reflects ACTUAL deletions — files that failed to delete (per-line WARN
    # logged above) will show up as "still present" in the summary.
    _DELETED_PROBE_TARGETS = (
        (str(DB_PATH), "faces.db"),
        (str(DB_PATH) + "-shm", "faces.db-shm"),
        (str(DB_PATH) + "-wal", "faces.db-wal"),
        (str(FAISS_INDEX_PATH), "faiss.index"),
        (str(BRAIN_DB_PATH), "brain.db"),
        (str(BRAIN_DB_PATH) + "-shm", "brain.db-shm"),
        (str(BRAIN_DB_PATH) + "-wal", "brain.db-wal"),
        (str(GRAPH_DB_PATH), "brain_graph"),
        (str(FACES_DIR.parent / "sim_session_state.json"), "sim_session_state.json"),
    )
    _PRESERVED_PROBE_TARGETS = (
        (str(FACES_DIR / ".dashboard_token"), ".dashboard_token"),
        (str(FACES_DIR / ".dashboard_auth_url"), ".dashboard_auth_url"),
    )
    _deleted_count = sum(1 for path, _ in _DELETED_PROBE_TARGETS if not Path(path).exists())
    _total_targets = len(_DELETED_PROBE_TARGETS)
    _photos_remaining = sum(1 for _ in FACES_DIR.glob("*.jpg"))
    _preserved_count = sum(1 for path, _ in _PRESERVED_PROBE_TARGETS if Path(path).exists())
    print(
        f"[Reset] Summary: deleted {_deleted_count}/{_total_targets} target(s) + "
        f"{_photos_remaining} photo(s) remaining (expected 0); "
        f"preserved {_preserved_count}/{len(_PRESERVED_PROBE_TARGETS)} (P0.S2 invariant)",
    )
    # Verbose enumeration for diagnostic clarity
    print("[Reset] Deleted targets:")
    for path, name in _DELETED_PROBE_TARGETS:
        status = "  ✓ gone" if not Path(path).exists() else "  ✗ STILL PRESENT (delete failed)"
        print(f"  {status}: {name}")
    print("[Reset] Preserved targets (per P0.S2 invariant):")
    for path, name in _PRESERVED_PROBE_TARGETS:
        status = "  ✓ kept" if Path(path).exists() else "  · absent (not present at start)"
        print(f"  {status}: {name}")
```

**Why probe post-call vs pre-call:** the existing per-file `try/except` in wipe_all catches deletion failures silently (just prints WARN). If we counted pre-call targets we'd overstate "deleted" — the post-call probe shows ACTUAL state. The verbose enumeration distinguishes "delete failed (still present)" from "wasn't there to begin with."

### D3 — Canary runbook reference fix (`tests/canary_week_2026-05-26.md`)

**Edit site:** `tests/canary_week_2026-05-26.md:39` (pre-canary checklist).

Current text:
> - [ ] **Factory reset done** — `python tools/factory_reset.py` OR manually delete `faces/` directory + `state.json` + `sim_session_state.json`

After D1 ships, this reference becomes accurate. NO CHANGE NEEDED to the runbook text — D1 makes the reference resolve. **D3 is a verify-step, not an edit-step.** Plan v1 D3 anchor is: confirm via grep that the runbook reference resolves to a real file post-D1.

If `tools/factory_reset.py` STILL doesn't exist after Phase 4 implementation (developer error), D3 anchor fires → caught at closure-audit grep-verify.

---

## §3 Anchor count LOCK

**Plan v1 LOCK: 7 anchors** at exact mid 7, inclusive ±15% band [5.95, 8.05].

**Breakdown:**

| Anchor | D-decision | Type | Coverage |
|---|---|---|---|
| A1 | D1.A1 | Source-inspection | `tools/factory_reset.py` file exists with module-level docstring containing `P0.S11` + canary date + Usage block |
| A2 | D1.A2 | Behavioral | Invoking script WITHOUT `--confirm` returns exit 0 + prints "DRY RUN" + lists targets; verify no files deleted (probe `tmp_path` files survive) |
| A3 | D1.A3 | Behavioral | Invoking with `--confirm` (no `--include-dashboard-token`) preserves `.dashboard_token` + `.dashboard_auth_url`; invoking with `--confirm --include-dashboard-token` deletes them too |
| A4 | D1.A4 | Behavioral | Pipeline-liveness check: write a `state.json` with `updated_at = time.time()` → script exits 1 + actionable error to stderr; mtime-backdate to `time.time() - 30` → script proceeds normally |
| A5 | D2 | Source-inspection | `core/db.py::wipe_all` body contains the post-wipe summary block + probes via `Path.exists()` + prints `[Reset] Summary:` line |
| A6 | D2 | Behavioral | After `wipe_all()` call against tmp_path with fake faces.db + brain.db pre-seeded: summary line shows correct deleted count + verbose enumeration; preserved `.dashboard_token` shows `✓ kept` |
| A7 | D3 | Source-inspection | `tests/canary_week_2026-05-26.md` reference to `tools/factory_reset.py` resolves to a real file post-D1 (grep-trail confirms) |

**Q5 closure projection:**
- Closure-actual = 7 → 0% drift vs Plan v1 LOCK → ON-TARGET exact-mid; extends `Doctrine-prediction-precision-improving-over-arc` sub-rule streak IF P0.S12 also closed 0% (7+8 consecutive)
- Closure-actual = 6 → −14.3% vs Plan v1 LOCK → ON-TARGET edge (within ±15%); doctrine holds
- Closure-actual = 8 → +14.3% vs Plan v1 LOCK → ON-TARGET edge; doctrine holds

---

## §4 Pre-mortem (3 ways this fix could fail)

1. **D1 pipeline-liveness check misfires (false negative) — user runs CLI thinking pipeline is offline but state.json was updated within last 10s by a stale background scan.**
   - Risk: CLI refuses with "Pipeline appears to be running" but user sees no pipeline.
   - Mitigation: `--force` flag bypass + actionable error message names the exact heuristic (mtime + 10s window) so user can check `faces/state.json` themselves. Acceptable false-negative rate; better than file-lock cryptic errors.

2. **D2 summary block uses `Path.exists()` which doesn't catch all delete-failure shapes (e.g. `unlink` succeeds but `os` race re-creates the file via background scan).**
   - Risk: Summary reports `✓ gone` even though the file is back due to a race.
   - Mitigation: The whole reason wipe_all docstring says "Caller must close any open FaceDB / BrainOrchestrator" is to AVOID this race. D1 CLI honors the docstring via pipeline-liveness check. Dashboard route honors it via IPC delegation. Pipeline IPC handler honors it via `db.close()` + `_brain_orchestrator.close_connections()`. **All 3 callers honor; no race expected.**

3. **D2 break existing `test_wipe_all_preserves_dashboard_token` because summary print adds stdout noise.**
   - Risk: Test captures stdout and asserts something incompatible with the new summary lines.
   - Mitigation: Pass-2 grep of the test (architect §1.3) verified it asserts on **file existence post-call**, NOT on stdout content. New summary lines don't affect file-existence assertions. **No regression expected.**

---

## §5 Multi-direction invariant trace

**Forward (user runs CLI):**
```
python tools/factory_reset.py --confirm
  → _is_pipeline_live() heuristic → reads faces/state.json::updated_at
      → if (now - updated_at) < 10s → exit 1 + actionable error
      → else proceed
  → enumerate targets via _enumerate_targets()
  → call wipe_all() → 10 delete groups fire → D2 summary log emits
      → [Reset] Summary: deleted N/9 target(s) + 0 photo(s) remaining (expected 0); preserved 2/2 (P0.S2 invariant)
      → [Reset] Deleted targets: ✓ gone: faces.db / ✓ gone: brain.db / ...
      → [Reset] Preserved targets (per P0.S2 invariant): ✓ kept: .dashboard_token / ...
  → if --include-dashboard-token → delete .dashboard_token + .dashboard_auth_url
  → exit 0
```

**Reverse (pipeline IPC path still works):**
```
Dashboard POST /api/factory-reset → reset_request.json written
  → Pipeline main loop polls RESET_REQUEST_FILE.exists() → fires
  → _brain_orchestrator.wipe() (in-memory state)
  → db.close() + _brain_orchestrator.close_connections() (file handles)
  → wipe_all() → D2 summary log emits in pipeline's terminal_output.md too
  → re-init FaceDB + buffers + state stores
  → write reset_result.json {success: True}
```

**Cross-spec:**
- **P0.S2 preservation invariant (`.dashboard_token` survives):** D1 CLI default preserves; D2 summary explicitly reports preserved status; only `--include-dashboard-token` opt-in overrides. Invariant intact.
- **P0.S12 (terminal_output archive guard):** independent; P0.S12 only touches pipeline.py module-level code. P0.S11 touches `core/db.py` + new `tools/` script. **Zero overlap.**
- **P0.S10 (brain identity-mismatch precision):** independent; P0.S10 touches `core/brain.py` + `pipeline.py::_intent_allows`. **Zero overlap.**
- **Existing 5 reset-touching tests** (§1.3): all preserved-by-design.

---

## §6 11-gate quality checklist

Per `feedback_strict_industry_standard_mode.md` §1:

| # | Gate | Status |
|---|---|---|
| 1 | Pre-mortem written (3 failure modes) | ✅ §4 |
| 2 | Multi-direction invariant trace (forward + reverse + cross-spec) | ✅ §5 |
| 3 | Pass-1 grep verified (Phase 0 §2.1) | ✅ |
| 4 | Pass-2 grep verified (architect-side widening; auditor-side pending) | ✅ §1 |
| 5 | Honest Q5 closure projection (§3 +1 anchor vs Phase 0 banked) | ✅ §3 |
| 6 | Cross-spec impact analyzed (P0.S2 + P0.S12 + P0.S10 + 5 existing tests) | ✅ §5 + §1.3 |
| 7 | Closure-audit scheduled (§7 commitment) | ✅ §7 |
| 8 | Doctrine firings catalogued (§9) | ✅ §9 |
| 9 | Open questions surface with architect's leans (§8 — 4 questions) | ✅ §8 |
| 10 | 11-gate self-audit documented (this section) | ✅ §6 |
| 11 | Architect closure-audit verdict forwarding committed (§7) | ✅ §7 |

---

## §7 Closure-audit commitment

Per `### Architect-reads-production-code-before-sign-off` + `feedback_closure_audit_verdict_cycle_elision.md` (4th cycle routinization at this closure, following P0.R12-R15 + P0.R10 + P0.S12 pending):

**At Phase 4 completion (developer side), architect performs closure-audit:**

1. **Grep-verify D1 contract** — `glob tools/factory_reset.py` returns the new file; module docstring contains `P0.S11` + canary date; argparse defines `--confirm`, `--include-dashboard-token`, `--force` flags
2. **Grep-verify D1.A4** — `_is_pipeline_live` function exists + reads `faces/state.json::updated_at` + 10s window
3. **Grep-verify D2 contract** — `core/db.py::wipe_all` body contains `_DELETED_PROBE_TARGETS` + `_PRESERVED_PROBE_TARGETS` + `[Reset] Summary:` print
4. **Grep-verify D3 contract** — `tests/canary_week_2026-05-26.md:39` references `tools/factory_reset.py` AND file exists
5. **Run D4 test suite** — `pytest tests/test_p0_s11_factory_reset_cli.py -v` reports all 7 anchors passing
6. **Run deliberate-regression cycle** — temporarily MOVE one D2 probe target out of summary OR rename `tools/factory_reset.py` → confirm A1/A5 fire → revert → confirm tests pass again
7. **Run cumulative suite** — `pytest --tb=no -q` reports baseline + P0.S12 6 anchors + P0.S11 7 anchors = 2773 passed + 14 skipped + 9 xfailed; no regressions in existing 5 factory-reset tests
8. **Sanity-check the CLI on a real tmp directory** — `python tools/factory_reset.py` (dry-run) + verify output formatting + `python tools/factory_reset.py --confirm --force` on a tmp-redirected `FACES_DIR` + verify the summary line
9. **PowerShell fresh-disk verify** on `to_be_checked.md` deferred-canary entry per locked §6.4 mechanism
10. **Forward closure-audit verdict to auditor** for ratification BEFORE declaring P0.S11 CLOSED

---

## §8 Open questions for auditor (4 questions; architect's lean per each)

### Q1 — D1 `--force` flag: ship or defer?

- **(a)** Ship `--force` as proposed (`§2 D1`). Lets operators bypass pipeline-liveness check when they know pipeline is stopped but state.json is stale.
- **(b)** Drop `--force`; force operators to wait 10s past last state.json update OR manually delete state.json before reset.

**Architect's lean: (a).** `--force` is an operator-control safety valve. Without it, a stale state.json (e.g. pipeline crashed mid-write, didn't clear updated_at) leaves the user unable to reset. The flag's name + documentation make the risk explicit; the "ONLY when pipeline known stopped" guidance is clear.

### Q2 — D2 summary format: minimal one-liner OR verbose enumeration?

- **(a)** Verbose enumeration (per §2 D2): one-line summary + per-target `✓/✗/·` lines. Heavy for routine use but excellent for diagnostic clarity (the canary failure mode).
- **(b)** Minimal one-liner only: `[Reset] Summary: deleted N/9 target(s) ...`. Less log noise; user has to dig into faces/ to verify.

**Architect's lean: (a) verbose.** The 2026-05-27 canary failure was EXACTLY because the user had no visible signal of what was deleted. Verbose enumeration is the diagnostic surface that prevents recurrence. Routine resets are infrequent; log noise is acceptable cost.

### Q3 — D3 (runbook reference fix): explicit edit OR verify-only?

- **(a)** Verify-only (per §2 D3). Plan v1 commits no text change to `canary_week_2026-05-26.md`; the existing reference becomes accurate AFTER D1 ships.
- **(b)** Also edit `canary_week_2026-05-26.md` to add a verification step ("verify `tools/factory_reset.py` exists before running") so future canary weeks catch any regression.

**Architect's lean: (a) verify-only.** Simplest path; runbook reference is already correct after D1; adding a verify step bloats the runbook without proportionate value. Future canary regressions in `tools/factory_reset.py` would surface as A1 test failure at CI.

### Q4 — Anchor count: 7 LOCKED or 6 (Phase 0 mid)?

- Phase 0 mid was 6. Pass-2 grep widened to 7 (added D1.A4 pipeline-liveness check). +16.7% from Phase 0 mid.
- **Architect's lean: 7 LOCKED.** Same shape as P0.S12 Pass-2 widening (1→6 was the architect's; 5→6 the auditor ratified). SCALE-OF-WORK-AXIS sub-shape firing — 10th instance candidate.
- Auditor's Pass-2 grep on `tools/replay_session.py` pattern + dashboard route's `isPipelineLive()` + the 5 existing factory-reset tests SHOULD converge on 7 anchors. If auditor returns 6 (rejects D1.A4 split), Plan v1 collapses to 6 and the SCALE-OF-WORK-AXIS sub-shape doesn't fire.

---

## §9 Doctrine track-record update commitments (at P0.S11 closure)

If/when P0.S11 closes:

| Doctrine | Pre-P0.S11 | Post-P0.S11 (projected) |
|---|---|---|
| `### Architect-reads-production-code-before-sign-off` | 28 (post-P0.S12) | 29 |
| `### Phase-0-granular-decomposition-enables-accurate-estimates` (if 0% Q5) | 28 supporting (post-P0.S12) | 29 supporting |
| `Doctrine-prediction-precision-improving-over-arc` sub-rule (if 0% Q5) | 7 consecutive 0%-streak (post-P0.S12) | 8 consecutive 0%-streak |
| `### Pre-audit-quantifier-precision-refined-by-grep` | 9 (post-P0.S12) | 10 (NEW SCALE-OF-WORK-AXIS — 10th overall, 2nd consecutive instance) |
| `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` | 8 (post-P0.S12) | 9 |
| `### Zero-precision-items-at-auditor-review` | 20 (post-P0.S12, assuming clean) | 22 if Phase 0 + Plan v1 clear cleanly |
| OPTIONAL-Plan-v2 sub-rule track record | 17 proof cases (post-P0.S12) | 18 if Plan v1 clears cleanly |
| Closure-audit verdict forwarding routinization | 3 cycles (post-P0.S12) | 4 cycles |
| `Explicit-closure-honest-count-commitment` (per locked precedent) | 25 (post-P0.S12 MADE+HONORED) | 27 (Plan v1 MADE + closure HONORED) |

**Notable:** if P0.S12 + P0.S11 BOTH close 0% ON-TARGET → 8 consecutive 0%-streak rebuild — would warrant sub-observation extension to "high-precision regime" beyond the original 5-instance threshold.

---

## §10 Cumulative suite impact

- **Baseline (pre-P0.S12):** 2760 passed + 14 skipped + 9 xfailed
- **Post-P0.S12 (projected):** 2766 passed (+6 anchors)
- **Post-P0.S11 (projected):** 2773 passed (+7 anchors, cumulative +13 from canary-Day-1 bundle)
- **No retirements expected** — D1 + D2 add new test surface; D3 is source-inspection only. Phase 0 §1.3 audit verified the 5 existing factory-reset tests preserve their semantics.

---

## §11 Cycle shape recommendation

**Architect's lean: OPTIONAL-Plan-v2 path** (3-artifact cycle: Phase 0 + Plan v1 + closure).

Rationale: Pass-2 grep widened scope BEFORE auditor review; the 5 existing reset-touching tests are explicitly preserved; pipeline-liveness check is the only architectural addition vs Phase 0 and is well-justified. No precision items anticipated.

If auditor returns ≥1 PI: cycle escalates to 4-artifact (Phase 0 + v1 + v2 + closure). Common escalation triggers from prior cycles: ENUMERATION-DRIFT (Pass-2 enumeration missed a site), CODE-TEMPLATE-MISIDENTIFICATION (architect copied template that diverges from canonical surface — applicable here if D1 doesn't match `tools/replay_session.py` shape precisely), LINE-REF-DRIFT (line numbers in Plan v1 don't match current production code).

---

## §12 Ready for auditor

Plan v1 forwarded for:
1. Pass-2 grep convergence check (auditor's standing offer)
2. Q5 estimate calibration (auditor's mid vs architect's LOCK 7)
3. Q1-Q4 open question adjudication
4. Doctrine firings ratification at this Plan v1 review

Architect commits to Plan v2 within ~2 hours of auditor's verdict if any precision items surface. Otherwise: hand off to developer Phase 4 implementation (parallel with P0.S12 OR after P0.S12 Phase 4 completes — both acceptable per §4.2 zero-line-overlap of the bundle).