"""SB.8 A6 — docs reframe grep-lock (Step 7, the SEPARATE docs slice per D4).

The three positioning docs (README + SETUP + competitive_positioning) carry
the runtime framing — "domain-agnostic embodied-presence runtime; the
companion is the first reference persona" — and the old product-is-a-dog
framing is gone from their positioning sections. The two HISTORICAL hits
(CHAPTER_07 architecture record + the silent-except-policy title) stay
untouched — D4: don't rewrite history — and the reframe must NOT leak into
them. Prose-only slice: no behavior surface, never bundled with steps 1-6.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import pathlib

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

_FRAMING = "domain-agnostic embodied-presence runtime"
_PERSONA_FRAMING = "first reference persona"

_POSITIONING_DOCS = (
    "README.md",
    "SETUP.md",
    "docs/embodied/competitive_positioning.md",
)


@pytest.mark.parametrize("doc", _POSITIONING_DOCS)
def test_a6_runtime_framing_present(doc) -> None:
    text = (REPO_ROOT / doc).read_text(encoding="utf-8")
    assert _FRAMING in text, f"{doc} lost the runtime positioning framing"
    assert _PERSONA_FRAMING in text, (
        f"{doc} lost the companion-as-reference-persona framing"
    )


def test_a6_old_product_is_a_dog_framing_gone_from_readme() -> None:
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "to the dog" not in text, (
        "README's enrollment section reverted to the product-is-a-dog phrasing"
    )
    assert not text.startswith("# DOG-AI"), (
        "README's title reverted to the pre-SB.8 product framing — the h1 "
        "leads with the runtime identity (the repo dir name stays in parens)"
    )


def test_a6_historical_docs_untouched() -> None:
    # D4: the 2 historical hits stay AS-IS — the architecture record keeps its
    # dated persona line, the policy doc keeps its title — and the NEW framing
    # must not leak into them (rewriting history would be its own regression).
    ch07 = (REPO_ROOT / "docs" / "architecture"
            / "CHAPTER_07_reconciler_and_conversation_turn.md").read_text(encoding="utf-8")
    assert "You are a robot dog named" in ch07, (
        "CHAPTER_07's historical persona-line record was rewritten — D4 "
        "forbids rewriting history"
    )
    assert _FRAMING not in ch07

    policy = (REPO_ROOT / "docs" / "silent-except-policy.md").read_text(encoding="utf-8")
    assert policy.startswith("# Silent-Except Policy — Dog-AI"), (
        "silent-except-policy's historical title was rewritten — D4 forbids "
        "rewriting history"
    )
    assert _FRAMING not in policy
