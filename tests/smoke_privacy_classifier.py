"""
Manual smoke test for Session 95 3A.2 `_classify_privacy_level`.

Per reviewer's 3A.2 sign-off (info.md): run 3 edge-case novel attributes
against the real Together.ai endpoint to confirm the prompt + JSON contract
round-trips correctly on attributes that are NOT in `PRIVACY_LEVEL_STATIC_MAP`
(forcing the LLM-fallback path) and land on the expected tier.

Invoke:
    python tests/smoke_privacy_classifier.py

Not a pytest test — makes live API calls (~$0.01 total). Keep as a
repeatable manual tool for future prompt revisions / 3A.3 re-verification.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import httpx  # noqa: E402

from core import brain_agent  # noqa: E402

# Each row: (entity, attribute, value, expected_tier, rule_path)
SMOKE_CASES: list[tuple[str, str, str, str, str]] = [
    (
        "Jagan", "current_anxiety", "deadline",
        "personal",
        "Rule 3 (embarrass/harm if shared) + matches confided_worry example",
    ),
    (
        "Lexi", "roommate_of", "Kara",
        "household",
        "Rule 2 (social graph -> household) + matches relationship_to_jagan example",
    ),
    (
        "stranger_abc", "session_token", "f4a8c91d7e2b3f5a",
        "system_only",
        "Rule 4 (mechanical -> system_only) + matches voice_embedding_hash example",
    ),
]


async def main() -> int:
    # Belt-and-suspenders: clear cache so previous runs don't short-circuit.
    brain_agent._privacy_classifier_cache.clear()
    results: list[tuple[str, str, str, bool]] = []
    async with httpx.AsyncClient() as http:
        for entity, attribute, value, expected, rule in SMOKE_CASES:
            assert attribute not in brain_agent.PRIVACY_LEVEL_STATIC_MAP, (
                f"{attribute!r} is in the static map — would skip LLM; smoke "
                "test must exercise the LLM path."
            )
            actual = await brain_agent._classify_privacy_level(
                entity, attribute, value, http=http
            )
            ok = actual == expected
            results.append((attribute, expected, actual, ok))
            print(
                f"[{'PASS' if ok else 'FAIL'}] "
                f"({entity}, {attribute}, {value!r})\n"
                f"        rule path:  {rule}\n"
                f"        expected:   {expected}\n"
                f"        actual:     {actual}\n"
            )
    all_ok = all(r[3] for r in results)
    print("-" * 70)
    print(f"Summary: {sum(r[3] for r in results)}/{len(results)} matched")
    if not all_ok:
        print("\nMismatches — prompt has a gap; tune examples before 3A.3 wire-in.")
        for attribute, exp, act, ok in results:
            if not ok:
                print(f"  * {attribute}: expected {exp}, got {act}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    if not os.environ.get("TOGETHER_API_KEY"):
        print("TOGETHER_API_KEY not set in environment — cannot run live smoke test.")
        sys.exit(2)
    sys.exit(asyncio.run(main()))
