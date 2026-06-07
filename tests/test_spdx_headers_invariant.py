"""A6 anchor — structural parametrize across in-scope SPDX files + .gitignore whitelist.

Per Plan v3 §3.1 + §5. PI #3 absorbed: `core/_minifasnet/*.py` EXCLUDED per vendored MIT
compliance (Bundle 2.X handles directory-level MIT compliance via a separate LICENSE file).

The in-scope file list is derived dynamically from the same bucket logic as
`tools/add_spdx_headers.py::collect_in_scope` so the test stays in sync as scope
expands (e.g. new tools/ or tests/ files land naturally).
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

SPDX_LICENSE_LINE = "# SPDX-License-Identifier: Apache-2.0"
SPDX_COPYRIGHT_LINE = "# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors"

EXCLUDED_PATHS = ("core/_minifasnet/",)  # PI #3 absorption

WHITELIST_LINES = (
    "!/GOVERNANCE.md",
    "!/CODE_OF_CONDUCT.md",
    "!/CONTRIBUTING.md",
)


def _collect_in_scope() -> list[Path]:
    files: list[Path] = []
    for p in sorted((REPO_ROOT / "core").rglob("*.py")):
        if "_minifasnet" not in p.parts:
            files.append(p)
    for name in ("pipeline.py", "enroll.py", "delete_person.py", "audit_person.py"):
        p = REPO_ROOT / name
        if p.is_file():
            files.append(p)
    files.extend(sorted(p for p in (REPO_ROOT / "tools").glob("*.py") if p.is_file()))
    files.extend(sorted((REPO_ROOT / "runtime").rglob("*.py")))  # P1.A1 SP-4 engine package
    files.extend(sorted((REPO_ROOT / "flows").rglob("*.py")))  # P1.A1 SP-6.2 app-layer flows
    boot = REPO_ROOT / "bootstrap" / "classifier"
    if boot.exists():
        files.extend(sorted(boot.rglob("*.py")))
    files.extend(sorted((REPO_ROOT / "tests").rglob("*.py")))
    files.extend(sorted((REPO_ROOT / ".github" / "workflows").glob("*.yml")))
    return files


IN_SCOPE_FILES = _collect_in_scope()


@pytest.mark.parametrize(
    "path",
    IN_SCOPE_FILES,
    ids=lambda p: p.relative_to(REPO_ROOT).as_posix(),
)
def test_a6_file_has_spdx_header(path: Path) -> None:
    """A6 — every in-scope file has both SPDX lines at line-start in the first 200 lines."""
    content = path.read_text(encoding="utf-8")
    head = content.split("\n", 200)[:200]
    has_license = any(line.lstrip().startswith(SPDX_LICENSE_LINE) for line in head)
    has_copyright = any(line.lstrip().startswith(SPDX_COPYRIGHT_LINE) for line in head)
    rel = path.relative_to(REPO_ROOT).as_posix()
    assert has_license, f"{rel} missing SPDX-License-Identifier at line-start"
    assert has_copyright, f"{rel} missing SPDX-FileCopyrightText at line-start"


@pytest.mark.parametrize("line", WHITELIST_LINES)
def test_a6_gitignore_whitelist_present(line: str) -> None:
    """A6 — .gitignore contains 3 governance-doc whitelist negations."""
    content = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert line in content, f".gitignore missing whitelist line: {line}"


def test_a6_excluded_paths_not_in_scope() -> None:
    """A6 inverse — vendored MIT files (core/_minifasnet/*.py) NOT in IN_SCOPE list."""
    for path in IN_SCOPE_FILES:
        rel = path.relative_to(REPO_ROOT).as_posix()
        for excluded_prefix in EXCLUDED_PATHS:
            assert not rel.startswith(excluded_prefix), (
                f"PI #3 absorption violation: {rel} should be EXCLUDED but is in scope"
            )


def test_a6_excluded_directory_has_license_at_directory_level() -> None:
    """A6 — Bundle 2.X concurrent: core/_minifasnet/LICENSE exists (MIT verbatim)."""
    minifasnet_license = REPO_ROOT / "core" / "_minifasnet" / "LICENSE"
    assert minifasnet_license.is_file(), (
        "PI #3 directory-level vendored MIT compliance requires core/_minifasnet/LICENSE"
    )
