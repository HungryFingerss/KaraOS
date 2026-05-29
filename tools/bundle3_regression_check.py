"""One-shot deliberate-regression harness for Pre-P1 Bundle 3 per Plan v2 §5.2.

For each scenario (a)-(e):
    1. Snapshot file bytes.
    2. Apply mutation.
    3. Run targeted anchor test via pytest.
    4. Assert targeted anchor fails.
    5. Restore from snapshot.
    6. Re-run to confirm clean restoration.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PYTEST_BIN = [sys.executable, "-m", "pytest", "-q", "--tb=line", "--no-header"]


def run_test(node_id: str) -> int:
    r = subprocess.run(PYTEST_BIN + [node_id], cwd=REPO_ROOT, capture_output=True, text=True)
    return r.returncode


def scenario_content_swap(label: str, target: Path, old: bytes, new: bytes, anchor: str) -> bool:
    snapshot = target.read_bytes()
    if old not in snapshot:
        print(f"  {label} SETUP-FAIL: old-string not found in {target.name}")
        return False
    target.write_bytes(snapshot.replace(old, new, 1))
    try:
        fail_on_mutation = run_test(anchor) != 0
    finally:
        target.write_bytes(snapshot)
    restored_clean = run_test(anchor) == 0
    status = "OK" if (fail_on_mutation and restored_clean) else "FAIL"
    print(f"  {label} {status}: fired-on-mutation={fail_on_mutation} | restored-clean={restored_clean}")
    return fail_on_mutation and restored_clean


def main() -> int:
    PIPELINE = REPO_ROOT / "pipeline.py"
    STATE_PY = REPO_ROOT / "core" / "state.py"

    print("Deliberate-regression harness for Pre-P1 Bundle 3 (Critical Bugs)\n")
    results = []

    # (a) Insert `time.time()` in a while-loop pattern at MODULE LEVEL (end of file) so the
    # AST parses cleanly (Q1 (b) re-run after fixing nested-indent injection issue).
    # Per auditor's strict-read: the harness must produce a real syntactic + semantic
    # violation that A2 can detect via AST walk.
    results.append(scenario_content_swap(
        label="(a) Insert time.time() in While loop (module-level)",
        target=PIPELINE,
        old=b"if __name__ == \"__main__\":\n    asyncio.run(run())\n",
        new=(
            b"def _regression_a_q1b():\n"
            b"    while time.time() < 100:\n"
            b"        break\n"
            b"\n"
            b"if __name__ == \"__main__\":\n"
            b"    asyncio.run(run())\n"
        ),
        anchor="tests/test_no_walltime_deadline_math.py::test_a2_no_deadline_math_walltime[pipeline.py]",
    ))

    # (b) Insert `assert` at MODULE LEVEL (end of file) so AST parses cleanly.
    results.append(scenario_content_swap(
        label="(b) Insert assert in production (module-level)",
        target=PIPELINE,
        old=b"if __name__ == \"__main__\":\n    asyncio.run(run())\n",
        new=(
            b"def _regression_b_q1b(x):\n"
            b"    assert x > 0, \"x must be positive\"\n"
            b"\n"
            b"if __name__ == \"__main__\":\n"
            b"    asyncio.run(run())\n"
        ),
        anchor="tests/test_no_production_assert.py::test_a4_no_production_assert[pipeline.py]",
    ))

    # (c) Strip # WALLCLOCK: cross-process IPC annotation from state.py → A2 fires (Compare with subtraction).
    results.append(scenario_content_swap(
        label="(c) Strip state.py:108 WALLCLOCK annotation",
        target=STATE_PY,
        old=b"# If pipeline hasn't written in 10 seconds, mark offline\n            # WALLCLOCK: cross-process IPC\n",
        new=b"# If pipeline hasn't written in 10 seconds, mark offline\n",
        anchor="tests/test_no_walltime_deadline_math.py::test_a2_no_deadline_math_walltime[core/state.py]",
    ))

    # (d) Revert one DEADLINE-MATH site back to time.time() → A1 fires.
    results.append(scenario_content_swap(
        label="(d) Revert pipeline.py:548 to time.time()",
        target=PIPELINE,
        old=b"return (time.monotonic() - last_seen) < SCENE_STALE_SECS",
        new=b"return (time.time() - last_seen) < SCENE_STALE_SECS",
        anchor="tests/test_no_walltime_deadline_math.py::test_a2_no_deadline_math_walltime[pipeline.py]",
    ))

    # (e) Revert one assert→raise migration to `assert` → A4 fires.
    results.append(scenario_content_swap(
        label="(e) Revert one raise RuntimeError to assert",
        target=PIPELINE,
        old=b"if not (_session_store is not None):\n        raise RuntimeError('_init_room_orchestrator: _session_store must be initialized')",
        new=b"assert _session_store is not None, '_init_room_orchestrator: _session_store must be initialized'",
        anchor="tests/test_no_production_assert.py::test_a4_no_production_assert[pipeline.py]",
    ))

    print()
    print(f"Summary: {sum(results)}/{len(results)} scenarios passed.")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
