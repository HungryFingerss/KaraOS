"""One-shot deliberate-regression harness for Pre-P1 Bundle 4 per Plan v1 §5.2.

For each scenario (a)-(e):
    1. Snapshot file bytes.
    2. Apply mutation.
    3. Run targeted anchor test via pytest.
    4. Assert targeted anchor fails.
    5. Restore from snapshot.
    6. Re-run to confirm clean restoration.

Per Bundle 3 closure-audit Q1 (b) lesson — synthetic-injection MUST fire correctly.
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
    print(
        f"  {label} {status}: fired-on-mutation={fail_on_mutation} | "
        f"restored-clean={restored_clean}"
    )
    return fail_on_mutation and restored_clean


def main() -> int:
    PIPELINE = REPO_ROOT / "pipeline.py"
    STATE_PY = REPO_ROOT / "core" / "state.py"
    HEALTH_PY = REPO_ROOT / "core" / "health.py"

    print("Deliberate-regression harness for Pre-P1 Bundle 4 (Observability + Concurrency)\n")
    results = []

    # (a) Strip outer-loop try/except wrap from _log_drain → A3 detector fires
    # (test_log_drain_has_outer_loop_try_except: while body must start with ast.Try).
    results.append(scenario_content_swap(
        label="(a) Strip outer-loop try/except from _log_drain",
        target=PIPELINE,
        old=(
            b"    global _log_drain_count, _log_drain_last_at, _log_drain_error_count\n"
            b"    while True:\n"
            b"        try:\n"
            b"            stream, data = _log_q.get()\n"
        ),
        new=(
            b"    global _log_drain_count, _log_drain_last_at, _log_drain_error_count\n"
            b"    while True:\n"
            b"        stream, data = _log_q.get()\n"
        ),
        anchor="tests/test_log_drain_observability_invariant.py::test_log_drain_has_outer_loop_try_except",
    ))

    # (b) Replace outer except body with bare `pass` (swallow) → A3 fires
    # (test_log_drain_except_handler_does_not_swallow). Same pattern as (a) but
    # keeps the try/except scaffolding intact; just collapses handler body.
    results.append(scenario_content_swap(
        label="(b) Replace outer except body with bare pass",
        target=PIPELINE,
        old=(
            b"        except Exception as e:\n"
            b"            # P0.B4 D1 outer-loop wrap: DO NOT swallow silently. Emit to stderr directly\n"
            b"            # (bypassing _Tee which routes through _log_q \xe2\x80\x94 would create an infinite loop).\n"
            b"            _log_drain_error_count += 1\n"
            b"            import sys as _sys\n"
            b"            try:\n"
            b"                _sys.__stderr__.write(f\"[Log] _log_drain exception: {type(e).__name__}: {e}\\n\")\n"
            b"                _sys.__stderr__.flush()\n"
            b"            except Exception:\n"
            b"                pass  # OPTIONAL: stderr unavailable; nothing more we can do\n"
            b"            # Continue the loop \xe2\x80\x94 drain thread stays alive\n"
        ),
        new=(
            b"        except Exception as e:\n"
            b"            pass\n"
        ),
        anchor="tests/test_log_drain_observability_invariant.py::test_log_drain_except_handler_does_not_swallow",
    ))

    # (c) Strip _sys.__stderr__ substring from outer except handler → A3 fires
    # (test_log_drain_except_handler_emits_to_stderr).
    results.append(scenario_content_swap(
        label="(c) Strip _sys.__stderr__ from outer except handler",
        target=PIPELINE,
        old=b"_sys.__stderr__.write(f\"[Log] _log_drain exception: {type(e).__name__}: {e}\\n\")\n                _sys.__stderr__.flush()",
        new=b"print(f\"[Log] _log_drain exception: {type(e).__name__}: {e}\")",
        anchor="tests/test_log_drain_observability_invariant.py::test_log_drain_except_handler_emits_to_stderr",
    ))

    # (d) Remove `with _persistent_lock:` wrap around shallow copy → A5 fires
    # (test_all_persistent_loads_under_lock_or_module_level). Replace the
    # 2-line lock+snapshot block with a bare snapshot assignment.
    results.append(scenario_content_swap(
        label="(d) Remove with _persistent_lock: wrap from state.write",
        target=STATE_PY,
        old=(
            b"    with _persistent_lock:\n"
            b"        _persistent_snapshot = dict(_persistent)\n"
        ),
        new=(
            b"    _persistent_snapshot = dict(_persistent)\n"
        ),
        anchor="tests/test_persistent_lock_invariant.py::test_all_persistent_loads_under_lock_or_module_level",
    ))

    # (e) Strip "Log drain thread degraded" verbatim substring from format_health_alerts
    # → A2 fires (parametrize collection for that exact substring).
    # The substring appears TWICE: once in the substring-lock comment block, once in
    # the actual alert. Mutating both via replace_all so the test surfaces the
    # missing alert substring (test checks for substring anywhere in function body
    # — must remove ALL instances to falsify).
    snapshot = HEALTH_PY.read_bytes()
    new_bytes = snapshot.replace(b"Log drain thread degraded", b"Log drain thread BROKEN")
    HEALTH_PY.write_bytes(new_bytes)
    try:
        fail_on_mutation = run_test(
            "tests/test_bundle4_anchors.py::"
            "test_a2_format_health_alerts_contains_verbatim_substring[Log drain thread degraded]"
        ) != 0
    finally:
        HEALTH_PY.write_bytes(snapshot)
    restored_clean = run_test(
        "tests/test_bundle4_anchors.py::"
        "test_a2_format_health_alerts_contains_verbatim_substring[Log drain thread degraded]"
    ) == 0
    label = "(e) Strip 'Log drain thread degraded' from format_health_alerts (all instances)"
    status = "OK" if (fail_on_mutation and restored_clean) else "FAIL"
    print(
        f"  {label} {status}: fired-on-mutation={fail_on_mutation} | "
        f"restored-clean={restored_clean}"
    )
    results.append(fail_on_mutation and restored_clean)

    print()
    print(f"Summary: {sum(results)}/{len(results)} scenarios passed.")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
