"""tests/test_p0_s5_wrap_user_input_coverage.py — P0.S5 D2 structural invariant.

D2 contract:
  Every ``messages=[{"role": "user", "content": <expr>}]`` site in the
  scanned files MUST either (a) have ``<expr>`` be a direct call to
  ``wrap_user_input(...)``, OR (b) be in ``_INDIRECT_BOUNDARIES_ALLOWLIST``
  with an explanatory rationale.

The allowlist captures:
  - Structurally indirect consumers (system-constructed prompts, structured
    derived data, embeddings input)
  - Sites where the user-content wrap fires UPSTREAM at construction time
    (e.g., ``_user_prompt = "Recent conversation:\\n... + wrap_user_input(_snip)``
    where the messages-list line uses the composite variable)
  - History-injection consumers deferred to P0.S5.X per Plan v3 §2
    narrow-scope disposition

Plan v3 §5 originally locked 15 entries; developer Pass-4 grep at Phase 2
implementation surfaced **2 additional upstream-wrapped sites** (brain.py
lines 1083 + 2013) bringing the allowlist to 17. Banked at Phase 5
closure as Pass-4-catch sub-observation per
``feedback_spec_time_grep_verification.md``.

Spec: tests/p0_s5_audit.md §2.D2 + tests/p0_s5_plan_v1.md §1.P1 +
tests/p0_s5_plan_v2.md §1 + tests/p0_s5_plan_v3.md §4 + §5.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import ast
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCAN_TARGETS = [
    "core/brain.py",
    "core/brain_agent.py",
]


# Per-entry tuple: (file_path, line_number, rationale).
# Plan v3 §5 + developer Pass-4 catch at Phase 2 implementation (2026-05-20).
# Line numbers grep-verified at Plan v3 drafting + Pass-4 refresh; structural
# test uses ast.Dict node line numbers which drift on file edits — Pass-2
# re-grep at every closure refreshes the entries.
# Pre-P1 Bundle 5 LINE-REF-DRIFT refresh (2026-05-29): brain.py sites +4,
# brain_agent.py sites +3 from post-P0.S10 edits in later cycles. All 17
# entries remain legitimately indirect (system-constructed / upstream-wrapped /
# history-deferred); only line keys refreshed via Pass-2 re-grep.
_INDIRECT_BOUNDARIES_ALLOWLIST: dict[tuple[str, int], str] = {
    # ── core/brain.py (11 entries) ──────────────────────────────────────
    # P0.S10 LINE-REF-DRIFT ripple: D2 (topic-correction bullet in tool desc)
    # shifted lines 521+ by +8; D1 (ASSERTION-DOMAIN RULE in classifier prompt)
    # shifted lines 843+ by additional +21 (cumulative +29 for lines after 843).
    # All entries below updated to post-P0.S10 line numbers.
    ("core/brain.py", 533):
        "ping_together health check — 'hi' literal, no user_text (line shifted +8 from 521 at P0.S10 D2)",
    ("core/brain.py", 731):
        "describe_frame vision — system-constructed describe-instruction; no user_text path (line shifted +8 from 719 at P0.S10 D2)",
    ("core/brain.py", 1116):
        "_classify_intent _user_prompt — UPSTREAM-WRAPPED via "
        "wrap_user_input(_snip); messages-list line consumes composite "
        "(system context + history + wrapped user content) per Plan v2 P4 (line shifted +29 from 1083 at P0.S10 D1+D2)",
    ("core/brain.py", 1971):
        "autocompact_history Together — history-injection deferred to P0.S5.X per Plan v3 §2 (line shifted +29 from 1938 at P0.S10 D1+D2)",
    ("core/brain.py", 1991):
        "autocompact_history Ollama retry — same as line 1967 (line shifted +29 from 1958 at P0.S10 D1+D2)",
    ("core/brain.py", 2005):
        "autocompact synthetic-summary — system-constructed compacted prompt "
        "wrapping LLM-generated summary; history-derived deferred to P0.S5.X (line shifted +29 from 1972 at P0.S10 D1+D2)",
    ("core/brain.py", 2046):
        "_build_context user_msg — UPSTREAM-WRAPPED via "
        "wrap_user_input(message.strip()); web-context augmentation "
        "concatenates AROUND the wrapped user_msg so wrap survives (line shifted +29 from 2013 at P0.S10 D1+D2)",
    ("core/brain.py", 3023):
        "web-search re-injection — concatenates web_context with "
        "already-wrapped user_msg from upstream (line shifted +29 from 2990 at P0.S10 D1+D2)",
    ("core/brain.py", 3220):
        "greeting generation Together — system-constructed greeting prompt (line shifted +29 from 3187 at P0.S10 D1+D2)",
    ("core/brain.py", 3244):
        "greeting generation Ollama — system-constructed (parallel to 3216) (line shifted +29 from 3211 at P0.S10 D1+D2)",
    ("core/brain.py", 3313):
        "choose_greeting_order — structured names-list prompt, no raw user-text (line shifted +29 from 3280 at P0.S10 D1+D2)",
    # ── core/brain_agent.py (6 entries) ─────────────────────────────────
    ("core/brain_agent.py", 462):
        "_ask_privacy_llm — entity/attribute/value triples (already-wrapped upstream extraction)",
    ("core/brain_agent.py", 4517):
        "extract_assistant_room_turn — assistant's own prior output, not user-typed (line shifted +6 from 4508 at P0.S9 D2 transaction-wrap)",
    ("core/brain_agent.py", 5650):
        "ObjectPatternAgent Together — structured sighting patterns + stats, not raw turns (line shifted +6 from 5641 at P0.S9 D2)",
    ("core/brain_agent.py", 5673):
        "ObjectPatternAgent Ollama — parallel to 5647 (line shifted +6 from 5664 at P0.S9 D2)",
    ("core/brain_agent.py", 5952):
        "BriefingAgent.generate — structured event-derived prompt (gate-validated names + system templates) (line shifted +6 from 5943 at P0.S9 D2)",
    ("core/brain_agent.py", 6020):
        "ConversationInsightAgent — conversation summary, not raw turns (line shifted +6 from 6011 at P0.S9 D2)",
}


def _content_is_wrap_call(content_node: ast.expr) -> bool:
    """Return True iff content_node is a direct `wrap_user_input(...)` call.

    Walks through one level of subscript / attribute / call to handle the
    common shapes:
      - `wrap_user_input(x)` — Call with Name func
      - `wrap_user_input(x[:N])` — Call with Subscript arg (still detected)
      - `wrap_user_input(x.strip())` — Call with Method-call arg
    """
    if not isinstance(content_node, ast.Call):
        return False
    func = content_node.func
    # Direct name: wrap_user_input(...)
    if isinstance(func, ast.Name) and func.id == "wrap_user_input":
        return True
    # Module-qualified: sanitize.wrap_user_input(...)
    if isinstance(func, ast.Attribute) and func.attr == "wrap_user_input":
        return True
    return False


def _scan_file_for_user_role_sites(file_path: Path) -> list[tuple[int, ast.expr]]:
    """Walk file's AST and return list of (line_no, content_expr) for every
    ``{"role": "user", "content": <expr>}`` dict literal.

    Line-number reference: uses the ``role`` value's lineno (the line where
    ``"user"`` appears as a string constant). This matches the natural
    grep line for ``"role": "user"`` and stays stable across content-value
    shapes (parenthesized multi-line expressions, dict-of-dicts, lists,
    etc., all of which can have unpredictable AST linenos for the content
    value itself).
    """
    src = file_path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    sites: list[tuple[int, ast.expr]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        # Must have 'role' key and 'content' key both
        role_value = None
        content_value = None
        for key, value in zip(node.keys, node.values):
            if not isinstance(key, ast.Constant):
                continue
            if key.value == "role" and isinstance(value, ast.Constant) and value.value == "user":
                role_value = value
            elif key.value == "content":
                content_value = value
        if role_value is not None and content_value is not None:
            # Use role-value's line number for stable allowlist matching
            sites.append((role_value.lineno, content_value))
    return sites


def test_every_user_role_content_passes_through_wrap_user_input():
    """D2 structural invariant — every messages-list ``{"role": "user"}``
    content site MUST either be a ``wrap_user_input(...)`` call OR be in
    ``_INDIRECT_BOUNDARIES_ALLOWLIST`` with documented rationale.

    Prevents silent regression when a future agent adds an LLM call
    without sanitizing user-text. Same shape as P0.S6
    ``test_no_secret_value_in_prints_or_logs`` — structural prevention
    via CI, not developer discipline.

    Plan v3 §5 + developer Pass-4 catch lock: 14 direct sites + 17
    allowlist entries = 31 line-level boundaries audited. Line numbers
    drift over time; the test reports violations with file:line so
    Pass-2 re-grep at closure refreshes the allowlist (entries with
    drifted line numbers will surface as new violations needing
    rationale + line-number update).
    """
    violations: list[tuple[str, int, str]] = []
    for target in _SCAN_TARGETS:
        path = _REPO_ROOT / target
        for line_no, content_node in _scan_file_for_user_role_sites(path):
            if _content_is_wrap_call(content_node):
                continue  # OK — wrapped
            if (target, line_no) in _INDIRECT_BOUNDARIES_ALLOWLIST:
                continue  # OK — explicitly indirect
            # Render the content expression for diagnostic context
            try:
                expr_src = ast.unparse(content_node)
            except Exception:
                expr_src = "<unparseable>"
            violations.append((target, line_no, expr_src))

    assert not violations, (
        "P0.S5 D2 invariant FAILED: user-role content at the following sites "
        "does NOT route through wrap_user_input AND is not in "
        "_INDIRECT_BOUNDARIES_ALLOWLIST:\n"
        + "\n".join(
            f"  {f}:{ln}  content={expr!r}" for f, ln, expr in violations
        )
        + "\n\nFix: either (a) wrap the content via wrap_user_input(...), OR "
        "(b) add ({file!r}, {line}) to _INDIRECT_BOUNDARIES_ALLOWLIST with a "
        "comment explaining why the content is structurally safe "
        "(system-constructed prompt / structured derived data / "
        "upstream-wrapped composite / history-injection deferred to P0.S5.X)."
    )


def test_indirect_boundaries_allowlist_entries_are_real_sites():
    """D2 inverse check — every allowlist entry MUST correspond to a real
    ``{"role": "user", "content": ...}`` site in the scanned file.

    Catches stale allowlist entries (line drift, removed code paths).
    Without this, a refactor that deletes a site but forgets to remove
    its allowlist entry creates dead config that silently grows over time.
    """
    stale: list[tuple[str, int]] = []
    actual_sites: dict[str, set[int]] = {}
    for target in _SCAN_TARGETS:
        path = _REPO_ROOT / target
        actual_sites[target] = {
            line_no for line_no, _ in _scan_file_for_user_role_sites(path)
        }
    for (target, line_no) in _INDIRECT_BOUNDARIES_ALLOWLIST.keys():
        if line_no not in actual_sites.get(target, set()):
            stale.append((target, line_no))
    assert not stale, (
        "P0.S5 D2 inverse-check FAILED: the following _INDIRECT_BOUNDARIES_"
        "ALLOWLIST entries reference lines that no longer have a "
        '{"role": "user", "content": ...} site (stale entries):\n'
        + "\n".join(f"  {f}:{ln}" for f, ln in stale)
        + "\n\nFix: re-grep the file at Pass-2 closure time, update the "
        "line number, OR remove the entry if the site was deleted."
    )
