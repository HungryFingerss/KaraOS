"""A8 STRENGTHENED — `tools/add_spdx_headers.py` idempotency + EXCLUDED=6 invariant.

Per Plan v3 §6 (Bundle 2) + SB.6 Resolution C. The vendored-third-party exclusion
contract: EXCLUDED_PATHS catches `core/_minifasnet/*.py` (2 files, MIT, Bundle 2)
+ `core/_florence2/*.py` (4 files: 3 vendored modeling .py with Apache-2.0 template
headers + the wrapper __init__.py, MIT repo, SB.6) = exactly 6 files on every run.

A8 STRENGTHENING: an idempotency assertion alone is insufficient to lock the
vendored-exclusion contract — running the script once on a state where EXCLUDED_PATHS
is empty would still report `Added: 0` if the headers already exist. The
STRENGTHENED A8 asserts `Excluded: 6` is reported, proving the exclusion
machinery is wired and would catch any future EXCLUDED_PATHS removal.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _run_script() -> str:
    result = subprocess.run(
        [sys.executable, "tools/add_spdx_headers.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def test_a8_script_idempotent_and_exclusion_invariant() -> None:
    """A8 STRENGTHENED — running tools/add_spdx_headers.py once on a fully-headered repo
    must report `Added: 0` AND `Excluded: 6` AND `.gitignore lines added: 0`.
    """
    output = _run_script()
    # Idempotency property
    assert re.search(r"^Added: 0\s*$", output, re.MULTILINE), (
        f"A8 idempotency violation: expected `Added: 0`; got:\n{output}"
    )
    # EXCLUDED invariant — vendored-third-party exclusion machinery wired
    # (2 minifasnet + 4 florence2 = 6; PI #3 / SB.6 Resolution C)
    assert re.search(r"^Excluded: 6\s*$", output, re.MULTILINE), (
        f"A8 EXCLUDED count invariant violation: expected `Excluded: 6`; got:\n{output}"
    )
    # .gitignore whitelist already-applied (idempotent on the gitignore update side too)
    assert re.search(r"^\.gitignore lines added: 0\s*$", output, re.MULTILINE), (
        f"A8 .gitignore idempotency violation: expected `0 added`; got:\n{output}"
    )
    # Error count must be zero
    assert re.search(r"^Errors: 0\s*$", output, re.MULTILINE), (
        f"A8 error count: expected `Errors: 0`; got:\n{output}"
    )


def test_a8_excluded_paths_constant_locked() -> None:
    """A8 — EXCLUDED_PATHS constant in tools/add_spdx_headers.py contains both vendored dirs.
    Lock: removing either entry should fail this test before the script runs.
    """
    script = (REPO_ROOT / "tools" / "add_spdx_headers.py").read_text(encoding="utf-8")
    assert 'EXCLUDED_PATHS' in script
    assert '"core/_minifasnet/"' in script, (
        "PI #3 absorption requires EXCLUDED_PATHS to contain 'core/_minifasnet/' "
        "as a string-literal entry; removing it breaks the vendored MIT compliance contract"
    )
    assert '"core/_florence2/"' in script, (
        "SB.6 Resolution C requires EXCLUDED_PATHS to contain 'core/_florence2/' "
        "as a string-literal entry; removing it would stamp KaraOS SPDX headers onto "
        "the vendored Florence-2 modeling code (Apache-2.0 template headers / MIT repo)"
    )
