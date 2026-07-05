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
    "core/brain_agent/__init__.py",
    "core/brain_agent/orchestrator.py",
    "core/brain_agent/privacy.py",
    "core/brain_agent/agents/extraction.py",
    "core/brain_agent/agents/briefing.py",
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
    # ── core/brain.py (10 entries) ──────────────────────────────────────
    # P0.S10 LINE-REF-DRIFT ripple: D2 (topic-correction bullet in tool desc)
    # shifted lines 521+ by +8; D1 (ASSERTION-DOMAIN RULE in classifier prompt)
    # shifted lines 843+ by additional +21 (cumulative +29 for lines after 843).
    # All entries below updated to post-P0.S10 line numbers.
    # #123 LINE-REF-DRIFT refresh (2026-05-31): the two ping `# OPTIONAL:` annotations
    # shifted brain.py lines after :543 by +6 (533 stays — it sits above the first ping);
    # the brain_agent.py triage (:296 jellyfish +2, :2906 _safe_loads +3, :3872 Kuzu LOG +5)
    # shifted :462 by +2 and all sites after :3872 by +10. Line keys refreshed via the
    # detector RUN's reported current linenos; all entries remain legitimately indirect.
    # SB.4.1 LINE-REF-DRIFT refresh (2026-06-17): the prompt-block registry refactor
    # (dynamic-slice _render_* fns + _RENDER_BY_NAME builder in core/brain.py) moved the
    # Section-3 block-render code out of _build_system_prompt into the render fns. That
    # shifted ONLY the FOUR brain.py role:user Dict sites that live BELOW the dynamic-slice
    # render fns (web-search re-injection + the 3 greeting/order sites in generate_greeting
    # / choose_greeting_order) — all by +118. The first 7 brain.py entries (all <=2080,
    # ABOVE the render fns) are UNCHANGED, and the 4 brain_agent entries are UNCHANGED
    # (SB.4.1 touched brain.py only). Line keys re-derived via a fresh Pass-2 grep of
    # `"role": "user"` sites; all entries remain legitimately indirect — these are
    # system-constructed prompts, NOT raw user-role content (the refactor builds
    # system-prompt strings, never user-role message dicts).
    # SB.6 LINE-REF-DRIFT refresh (2026-06-26): the visual_query classifier-prompt
    # additions in core/brain.py::_INTENT_CLASSIFIER_SYSTEM (the enumeration entry +6
    # lines + the VISUAL vs LIVE-DATA RULE block +24 lines) shifted every brain.py
    # role:user Dict site BELOW the classifier prompt by +30. The first 2 brain.py
    # entries (543, 765 — ABOVE the prompt) were UNCHANGED by that step.
    # SB.6 Step 5 describe_frame deletion (2026-06-26): the orphaned `describe_frame`
    # function (the only `describe_frame` role:user Dict site, formerly at key 765) was
    # HARD-DELETED — the cloud vision tier lives in core/object_detection.py now (PI-2).
    # The ~49-line deletion sits ABOVE the classifier prompt, so it shifts every brain.py
    # role:user site BELOW 738 UPWARD by -49; the 543 ping entry (above 738) is UNCHANGED.
    # The 4 brain_agent entries are UNCHANGED (SB.6 touched core/brain.py + config +
    # object_detection only). Line keys re-derived via a fresh AST scan of role:user sites
    # (NOT hand arithmetic); all entries remain legitimately indirect (system-constructed /
    # upstream-wrapped / history-deferred).
    # SB.6 Step-5 fold (2026-06-26): the architect-ratified completion of the
    # describe_frame deletion removed its 2 now-orphaned imports (`import base64`,
    # `import cv2`) from the top of core/brain.py. Those 2 lines sit ABOVE every
    # role:user Dict site, so EVERY brain.py key below shifts UPWARD by -2 — INCLUDING
    # the 541 ping entry (the import block is above it). Line keys re-derived via a
    # fresh AST scan of role:user sites (NOT hand arithmetic); the wrapped
    # _build_context append at 1846 stays correctly OUT of the allowlist.
    # SB.8 LINE-REF-DRIFT refresh (2026-07-02): the persona-pack two-slot
    # template conversion shifted every brain.py role:user site below the old
    # SYSTEM_PROMPT (:203) by +34 net (template header comment +8, the two
    # character lines collapsing into one {persona_character} slot -1, the
    # _compose_system_prompt fn + SYSTEM_PROMPT rebind +27), and sites below
    # the greeting region by a further +8 (fallbacks guard/comment + the
    # {greeting_persona_line} template + _compose_greeting_prompt) = +42
    # cumulative. Line keys re-derived from the detector RUN's reported
    # current linenos (NOT hand arithmetic). NOTE the caught key-collision:
    # the shifted autocompact-Together site (1984 → 2018) landed EXACTLY on
    # the stale synthetic-summary key (2018), so the detector under-reported
    # 9 violations for 10 stale entries — a fresh-scan refresh (this one)
    # eliminates the accidental blessing; all entries remain legitimately
    # indirect (system-constructed / upstream-wrapped / history-deferred).
    ("core/brain.py", 575):
        "ping_together health check — 'hi' literal, no user_text (+34 SB.8)",
    ("core/brain.py", 1163):
        "_classify_intent _user_prompt — UPSTREAM-WRAPPED via "
        "wrap_user_input(_snip); messages-list line consumes composite "
        "(system context + history + wrapped user content) per Plan v2 P4 (+34 SB.8)",
    ("core/brain.py", 2018):
        "autocompact_history Together — history-injection deferred to P0.S5.X per Plan v3 §2 (+34 SB.8)",
    ("core/brain.py", 2038):
        "autocompact_history Ollama retry — same as the Together path (+34 SB.8)",
    ("core/brain.py", 2052):
        "autocompact synthetic-summary — system-constructed compacted prompt "
        "wrapping LLM-generated summary; history-derived deferred to P0.S5.X (+34 SB.8)",
    ("core/brain.py", 2093):
        "_build_context user_msg — UPSTREAM-WRAPPED via "
        "wrap_user_input(message.strip()); web-context augmentation "
        "concatenates AROUND the wrapped user_msg so wrap survives (+34 SB.8)",
    ("core/brain.py", 3302):
        "web-search re-injection — concatenates web_context with "
        "already-wrapped user_msg from upstream (+34 SB.8)",
    ("core/brain.py", 3507):
        "greeting generation Together — system-constructed greeting prompt (+42 SB.8)",
    ("core/brain.py", 3537):
        "greeting generation Ollama — system-constructed (parallel to Together) (+42 SB.8)",
    ("core/brain.py", 3606):
        "choose_greeting_order — structured names-list prompt, no raw user-text (+42 SB.8)",
    # ── core/brain_agent privacy.py(1) + agents/extraction.py(1) + agents/briefing.py(2) ─────────────────────────────────
    ("core/brain_agent/privacy.py", 164):
        "_ask_privacy_llm — entity/attribute/value triples (already-wrapped upstream extraction) (+2 #123)",
    ("core/brain_agent/agents/extraction.py", 537):
        "extract_assistant_room_turn — assistant's own prior output, not user-typed (+10 #123)",
    ("core/brain_agent/agents/briefing.py", 118):
        "BriefingAgent.generate — structured event-derived prompt (gate-validated names + system templates) (+10 #123)",
    ("core/brain_agent/agents/briefing.py", 186):
        "ConversationInsightAgent — conversation summary, not raw turns (+10 #123)",
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

    Plan v3 §5 + developer Pass-4 catch lock: 14 direct sites + 15
    allowlist entries = 29 line-level boundaries audited. Line numbers
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
