"""Pre-P1 Bundle 1 (Docs+CI) anchor tests A1-A14.

Per `tests/pre_p1_bundle1_docs_ci_plan_v2.md` §3.1 Q5 LOCK at 14 anchors.

Tests use pure stdlib (`re`, `pathlib`) to keep collection clean on Windows dev
machines that don't have pyannote/speechbrain installed.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"
EVERYTHING = REPO_ROOT / "everything_about_system.md"
GITIGNORE = REPO_ROOT / ".gitignore"
SETUP_MD = REPO_ROOT / "SETUP.md"
DOCS_ARCH = REPO_ROOT / "docs" / "architecture"
README_MD = DOCS_ARCH / "README.md"

CHAPTER_FILES = (
    "CHAPTER_01_introduction_and_tech_stack.md",
    "CHAPTER_02_lifecycle_and_pipeline_states.md",
    "CHAPTER_03_async_and_vision_basics.md",
    "CHAPTER_04_audio_and_stt_tts.md",
    "CHAPTER_05_face_voice_galleries.md",
    "CHAPTER_06_sessions_and_evidence.md",
    "CHAPTER_07_reconciler_and_conversation_turn.md",
    "CHAPTER_08_prompt_blocks_and_brain_agents.md",
    "CHAPTER_09_dispute_tool_privileges_logging.md",
    "CHAPTER_10_schemas_tests_dashboard.md",
    "CHAPTER_11_future_work_reference_tables.md",
    "CHAPTER_12_privacy_rooms_recent_work.md",
    "CHAPTER_13_observability_evolution_plans_pyannote.md",
    "CHAPTER_14_voice_vision_independence_pure_graph_classifier.md",
    "CHAPTER_15_external_benchmarks_multilayer_architecture.md",
    "CHAPTER_16_p0_correctness_store_session_migrations.md",
    "CHAPTER_17_p0_timeout_schema_router_concurrency_property.md",
    "CHAPTER_18_observability_ci_event_log.md",
    "CHAPTER_19_architectural_disciplines_upcoming_work.md",
)

ACTIVE_DOC_SURFACES = (CLAUDE_MD, GITIGNORE, SETUP_MD, EVERYTHING)


def _chapter_text(name: str) -> str:
    return (DOCS_ARCH / name).read_text(encoding="utf-8")


def _chapters_containing_h2(section_num: int) -> list[str]:
    pat = re.compile(rf"^## {section_num}\.", re.MULTILINE)
    return [name for name in CHAPTER_FILES if pat.search(_chapter_text(name))]


# A1 — D1.b: stale P1.P1 entries removed from CLAUDE.md.
def test_a1_no_stale_p1_p1_no_ci_config_in_claude_md():
    text = CLAUDE_MD.read_text(encoding="utf-8")
    assert "P1.P1 \u2014 No CI config" not in text, (
        "D1 must remove the stale `P1.P1 \u2014 No CI config` entries"
    )


# A2 — D1.b: consolidated P0.0 CI scaffold narrative present.
def test_a2_p0_0_ci_scaffold_narrative_present():
    text = CLAUDE_MD.read_text(encoding="utf-8")
    assert "P0.0 CI scaffold live" in text
    assert "4 GitHub Actions workflows" in text
    assert "informational-mode gates" in text
    assert "post-P1 deferred-tightening candidate" in text


# A3 — D2: Layer D lead sentence verbatim.
def test_a3_d2_layer_d_lead_sentence_verbatim():
    text = CLAUDE_MD.read_text(encoding="utf-8")
    assert (
        "Layer D cognitive runtime middleware for embodied AI"
        in text
    ), "D2 lead sentence missing from Project Overview"


# A4 — D2: two-stack architecture (companion + robotics) both named.
def test_a4_d2_two_stack_phrases_present():
    text = CLAUDE_MD.read_text(encoding="utf-8")
    assert "companion stack" in text
    assert "robotics stack" in text
    assert "3-5 year market-defining horizon" in text


# A5 — D2+D3: every `docs/architecture/` chapter reference resolves to an
# existing file. Parametrized across all 4 active-doc surfaces.
@pytest.mark.parametrize(
    "surface",
    ACTIVE_DOC_SURFACES,
    ids=lambda p: p.name,
)
def test_a5_chapter_refs_resolve(surface: Path):
    text = surface.read_text(encoding="utf-8")
    chapter_refs = re.findall(r"docs/architecture/(CHAPTER_\d+_[a-z_]+\.md)", text)
    for fname in chapter_refs:
        assert (DOCS_ARCH / fname).exists(), (
            f"{surface.name} references missing chapter file: {fname}"
        )
    if "docs/architecture/README.md" in text:
        assert README_MD.exists(), (
            f"{surface.name} references README.md but it is missing"
        )


# A6 — D3.a: 19 chapter files present with locked names.
def test_a6_d3a_19_chapter_files_present():
    assert DOCS_ARCH.is_dir(), "docs/architecture/ directory missing"
    for fname in CHAPTER_FILES:
        assert (DOCS_ARCH / fname).is_file(), f"missing chapter file: {fname}"
    glob_count = len(list(DOCS_ARCH.glob("CHAPTER_*.md")))
    assert glob_count == 19, f"expected 19 chapter files; got {glob_count}"


# A7 — D3.a: parent README index lists every chapter.
def test_a7_d3a_readme_lists_all_chapters():
    assert README_MD.is_file()
    text = README_MD.read_text(encoding="utf-8")
    for fname in CHAPTER_FILES:
        assert fname in text, f"README missing chapter file ref: {fname}"


# A8 — D3.b: thin redirect <50 lines, DO-NOT-WRITE-HERE notice, all 19 chapters.
def test_a8_d3b_thin_redirect_shape():
    text = EVERYTHING.read_text(encoding="utf-8")
    lines = text.split("\n")
    assert len(lines) < 50, (
        f"thin redirect must be <50 lines, got {len(lines)}"
    )
    assert "DO NOT WRITE HERE" in text
    for fname in CHAPTER_FILES:
        assert fname in text, f"thin redirect missing chapter ref: {fname}"


# A9 — D3.c: .gitignore comment block reflects split.
def test_a9_d3c_gitignore_reflects_split():
    text = GITIGNORE.read_text(encoding="utf-8")
    assert "thin redirect" in text
    assert "docs/architecture/" in text
    # /*.md rule still in place, repo-root-only semantic intact.
    assert "/*.md" in text
    assert "!/everything_about_system.md" in text


# A10 — D3.c: SETUP.md lines 71/85/108 redirect to chapter surfaces.
# Per-site window check: each of the 3 anchor phrases must have a
# `docs/architecture/...` reference within ~200 chars after it.
def test_a10_d3c_setup_md_chapter_redirects():
    text = SETUP_MD.read_text(encoding="utf-8")
    sites = (
        ("Apply the pyannote dependency patches", "docs/architecture/CHAPTER_13"),
        ("Architecture docs (CLAUDE.md", "docs/architecture/"),
        ("pyannote returns 0 segments on multi-speaker audio", "docs/architecture/CHAPTER_13"),
    )
    for anchor_phrase, required_ref in sites:
        idx = text.find(anchor_phrase)
        assert idx >= 0, f"anchor phrase missing from SETUP.md: {anchor_phrase!r}"
        window = text[idx:idx + 400]
        assert required_ref in window, (
            f"SETUP.md site {anchor_phrase!r} missing required ref {required_ref!r} "
            f"within 400-char window"
        )


# A11 — D3.d: zero stale `everything_about_system.md §NN` refs in CLAUDE.md.
def test_a11_d3d_no_stale_section_refs_in_claude_md():
    text = CLAUDE_MD.read_text(encoding="utf-8")
    stale = re.findall(r"everything_about_system\.md\s*\u00a7\d+", text)
    assert not stale, f"stale §-level refs in CLAUDE.md: {stale}"


# A12 — Plan v2 §3.1 NEW: §177-§340 coverage parametrize.
# Every §NN in 177-340 lands in exactly one chapter file.
@pytest.mark.parametrize("section_num", list(range(177, 341)))
def test_a12_section_177_340_in_exactly_one_chapter(section_num: int):
    matches = _chapters_containing_h2(section_num)
    assert len(matches) == 1, (
        f"\u00a7{section_num} appears in {len(matches)} chapters: {matches}"
    )


# A13 — Plan v2 §3.1 NEW: README covers all 19 chapters in navigation table.
def test_a13_readme_navigation_table_complete():
    text = README_MD.read_text(encoding="utf-8")
    for n in range(1, 20):
        cn = f"CHAPTER_{n:02d}"
        assert cn in text, f"README missing {cn} in chapter listing/navigation"


# A14 — Plan v2 §1.6 LOAD-BEARING section-number stability invariant.
# Parametrize across §1-§340; every §NN appears in EXACTLY ONE chapter
# (zero duplicates + zero missing). LOAD-BEARING per Plan v2 §1.6 contract.
@pytest.mark.parametrize("section_num", list(range(1, 341)))
def test_a14_section_stability_invariant(section_num: int):
    matches = _chapters_containing_h2(section_num)
    assert len(matches) == 1, (
        f"\u00a7{section_num} appears in {len(matches)} chapters: {matches}"
    )
