"""One-shot deliberate-regression harness for Pre-P1 Bundle 2 (Governance).

For each scenario (a)-(e) per Plan v3 §7:
    1. Snapshot the production file's bytes.
    2. Apply the regression mutation.
    3. Run the targeted anchor test via pytest.
    4. Assert the targeted anchor fails (regression confirmed).
    5. Restore the file from snapshot.
    6. Run the targeted test again to confirm restoration is clean.

Prints a one-line summary per scenario; non-zero exit if any scenario didn't
fail-on-mutation or didn't restore cleanly.
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


def scenario_file_delete(label: str, target: Path, anchor: str) -> bool:
    snapshot = target.read_bytes()
    target.unlink()
    try:
        fail_on_mutation = run_test(anchor) != 0
    finally:
        target.write_bytes(snapshot)
    restored_clean = run_test(anchor) == 0
    status = "OK" if (fail_on_mutation and restored_clean) else "FAIL"
    print(f"  {label} {status}: fired-on-mutation={fail_on_mutation} | restored-clean={restored_clean}")
    return fail_on_mutation and restored_clean


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
    LICENSE = REPO_ROOT / "LICENSE"
    NOTICE = REPO_ROOT / "NOTICE"
    GITIGNORE = REPO_ROOT / ".gitignore"
    SPDX_SCRIPT = REPO_ROOT / "tools" / "add_spdx_headers.py"
    # Pick a representative in-scope Python file (small + stable) to strip a header from.
    TARGET_FILE = REPO_ROOT / "tools" / "factory_reset.py"

    print("Deliberate-regression harness for Pre-P1 Bundle 2 (Governance)\n")
    results = []

    # (a) D1: delete LICENSE → A1 fires.
    results.append(scenario_file_delete(
        label="(a) D1 delete LICENSE",
        target=LICENSE,
        anchor="tests/test_pre_p1_bundle2_docs_governance.py::test_a1_license_apache_2_0_at_repo_root",
    ))

    # (b) D2: delete NOTICE → A2 fires.
    results.append(scenario_file_delete(
        label="(b) D2 delete NOTICE",
        target=NOTICE,
        anchor="tests/test_pre_p1_bundle2_docs_governance.py::test_a2_notice_with_three_vendored_attributions",
    ))

    # (c) D6/PI #3: remove EXCLUDED_PATHS entry from script → A8 EXCLUDED-count
    # invariant fires (EXCLUDED count would be 0 not 2). Use the constant-lock test which
    # asserts EXCLUDED_PATHS contains 'core/_minifasnet/'.
    results.append(scenario_content_swap(
        label="(c) D6 PI #3 EXCLUDED_PATHS removal",
        target=SPDX_SCRIPT,
        old=b'EXCLUDED_PATHS: tuple[str, ...] = ("core/_minifasnet/",)',
        new=b'EXCLUDED_PATHS: tuple[str, ...] = ()',
        anchor="tests/test_spdx_script_idempotency.py::test_a8_excluded_paths_constant_locked",
    ))

    # (d) D6 .gitignore whitelist: drop !/GOVERNANCE.md from .gitignore → A6 whitelist test fires.
    results.append(scenario_content_swap(
        label="(d) D6 drop !/GOVERNANCE.md whitelist",
        target=GITIGNORE,
        old=b"!/GOVERNANCE.md\n",
        new=b"",
        anchor="tests/test_spdx_headers_invariant.py::test_a6_gitignore_whitelist_present[!/GOVERNANCE.md]",
    ))

    # (e) D6 SPDX header: strip from one in-scope Python file → A6 parametrize hit fires.
    results.append(scenario_content_swap(
        label="(e) D6 strip SPDX header from sample file",
        target=TARGET_FILE,
        old=b"# SPDX-License-Identifier: Apache-2.0\n# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors\n",
        new=b"",
        anchor="tests/test_spdx_headers_invariant.py::test_a6_file_has_spdx_header[tools/factory_reset.py]",
    ))

    print()
    print(f"Summary: {sum(results)}/{len(results)} scenarios passed.")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
