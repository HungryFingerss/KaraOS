"""Pre-P1 Bundle 2 (Governance) anchor tests A1-A5 + A7.

Per `tests/pre_p1_bundle2_governance_plan_v3.md` §3.1 Q5 LOCK at 8 anchors.
A6 (SPDX parametrize) and A8 (script idempotency STRENGTHENED) live in
sibling test files for separation of concerns.

A1 = LICENSE | A2 = NOTICE | A3 = GOVERNANCE.md | A4 = CODE_OF_CONDUCT.md
A5 = CONTRIBUTING.md | A7 = README License & Governance section
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LICENSE = REPO_ROOT / "LICENSE"
NOTICE = REPO_ROOT / "NOTICE"
GOVERNANCE = REPO_ROOT / "GOVERNANCE.md"
CODE_OF_CONDUCT = REPO_ROOT / "CODE_OF_CONDUCT.md"
CONTRIBUTING = REPO_ROOT / "CONTRIBUTING.md"
README = REPO_ROOT / "README.md"
MINIFASNET_LICENSE = REPO_ROOT / "core" / "_minifasnet" / "LICENSE"


# A1 — D1: LICENSE file exists at repo root + Apache 2.0 verbatim markers.
def test_a1_license_apache_2_0_at_repo_root():
    assert LICENSE.is_file(), "LICENSE file missing at repo root"
    text = LICENSE.read_text(encoding="utf-8")
    assert "Apache License" in text
    assert "Version 2.0, January 2004" in text
    assert "http://www.apache.org/licenses/" in text
    assert "TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION" in text
    assert "END OF TERMS AND CONDITIONS" in text


# A2 — D2: NOTICE file exists + all 3 vendored attributions present.
def test_a2_notice_with_three_vendored_attributions():
    assert NOTICE.is_file(), "NOTICE file missing at repo root"
    text = NOTICE.read_text(encoding="utf-8")
    assert "KaraOS" in text
    assert "Copyright 2025-2026 The KaraOS Authors" in text
    assert "pyannote.audio" in text and "MIT License" in text
    assert "speechbrain" in text and "Apache License 2.0" in text
    assert "MiniFASNet" in text and "core/_minifasnet/" in text


# A3 — D3: GOVERNANCE.md has 5 required checkpoints + Phase 1/2/3 evolution.
def test_a3_governance_required_checkpoints():
    assert GOVERNANCE.is_file()
    text = GOVERNANCE.read_text(encoding="utf-8")
    # 5 checkpoints per Plan v3 §3 D3
    assert "Philosophy" in text
    assert "Layer D cognitive runtime middleware" in text
    assert "BDFL" in text
    assert "Jagannivas" in text
    assert "Decision-making process" in text or "decision-making" in text.lower()
    assert "Contributor expectations" in text
    assert "Escalation" in text
    # 3-phase evolution path
    assert "Phase 1" in text and "Phase 2" in text and "Phase 3" in text
    assert "3 or more regular external contributors" in text or "3+ regular" in text
    assert "10" in text and "Committers" in text  # Phase 3 trigger criterion


# A4 — D4: CODE_OF_CONDUCT.md is Contributor Covenant 2.1 with customizations.
def test_a4_code_of_conduct_contributor_covenant_2_1():
    assert CODE_OF_CONDUCT.is_file()
    text = CODE_OF_CONDUCT.read_text(encoding="utf-8")
    assert "Contributor Covenant" in text
    assert "Version 2.1" in text or "version 2.1" in text.lower()
    # Customization #1 (locked): contact substitution
    assert "jagannivas.001@gmail.com" in text
    assert "[INSERT CONTACT METHOD]" not in text
    # Project name reference somewhere
    assert "KaraOS" in text or "community" in text.lower()


# A5 — D5: CONTRIBUTING.md has required sections.
def test_a5_contributing_required_sections():
    assert CONTRIBUTING.is_file()
    text = CONTRIBUTING.read_text(encoding="utf-8")
    # 5 required sections per Plan v3 §3 D5
    lower = text.lower()
    assert "clone" in lower and "install" in lower
    assert "pytest" in lower
    assert "submit" in lower and ("pr" in lower or "pull request" in lower)
    assert "strict-mode" in lower or "strict mode" in lower
    # CLAUDE.md as conventions source
    assert "CLAUDE.md" in text
    # SETUP.md cross-reference
    assert "SETUP.md" in text


# A7 — D7: README.md has License & Governance section with 4 doc links.
def test_a7_readme_license_governance_section():
    assert README.is_file()
    text = README.read_text(encoding="utf-8")
    assert "License & Governance" in text
    assert "Apache License 2.0" in text
    # 4 doc links present (LICENSE + NOTICE + GOVERNANCE.md + CODE_OF_CONDUCT.md + CONTRIBUTING.md)
    for ref in ("[LICENSE](LICENSE)", "[NOTICE](NOTICE)", "[GOVERNANCE.md](GOVERNANCE.md)",
                "[CONTRIBUTING.md](CONTRIBUTING.md)", "[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)"):
        assert ref in text, f"README License & Governance section missing link: {ref}"


# Bundle 2.X — concurrent commit per Path α adjudication:
# core/_minifasnet/LICENSE present with verbatim MIT text from upstream.
def test_bundle_2_x_minifasnet_mit_license():
    assert MINIFASNET_LICENSE.is_file(), (
        "Bundle 2.X concurrent deliverable missing: core/_minifasnet/LICENSE"
    )
    text = MINIFASNET_LICENSE.read_text(encoding="utf-8")
    assert "MIT License" in text
    assert "Copyright (c) 2020 Minivision" in text
    assert "Permission is hereby granted, free of charge" in text
    assert "The above copyright notice and this permission notice shall be included" in text
    assert "THE SOFTWARE IS PROVIDED \"AS IS\"" in text
