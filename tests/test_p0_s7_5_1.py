"""tests/test_p0_s7_5_1.py — P0.S7.5.1 visitor alert marker/metadata asymmetry fix.

Closes the canary-2 failure mode where `update_visitor_alert_for_promoted_person`
silently no-op'd on every stranger promotion because `_run_visitor_alert` writes
ASYMMETRIC content (marker `[visitor_name:unknown]`) and metadata
(`visitor_name='visitor'`). The Session 114 Part 5 literal-substring check
`if f"[visitor_name:{old_name}]" in content` only fired when the metadata
`old_name` matched the marker placeholder — but stranger sessions guarantee
they don't match.

D1 fix (lambda-replacement `re.sub`):
- Regex pattern `r"\\[visitor_name:[^\\]]+\\]"` matches ANY current marker placeholder
- Lambda replacement (callable) uses `new_marker` VERBATIM — no regex
  backreference interpretation (`\\1`, `\\g<name>`, `\\`)
- Robust to asymmetric metadata + future placeholder drift + special-char
  defense-in-depth on `new_name`

Plan v2 §5.1 — 5 Phase 1 tests:
  1. test_regex_swaps_existing_marker (unit) — primary happy path
  2. test_regex_noop_when_marker_absent (unit) — defensive no-marker case
  3. test_regex_idempotent_when_already_renamed (unit) — idempotency
  4. test_update_alert_uses_regex_not_literal_substring (AST forward-property)
  5. test_regex_replacement_handles_backslash_in_new_name (unit; defense-in-depth)
"""
from __future__ import annotations

import ast
import inspect
import json
import time

import pytest


def _seed_visitor_alert_row(
    brain_db,
    *,
    visitor_id: str,
    content: str,
    metadata: dict,
    target_person_id: str = "jagan_001",
) -> int:
    """Direct INSERT bypasses `store_nudge`'s metadata serialization path so
    tests can control the asymmetric marker-vs-metadata shape the canary
    actually produces (marker '[visitor_name:unknown]', metadata
    visitor_name='visitor').
    """
    cur = brain_db._conn.execute(
        """INSERT INTO proactive_nudges
           (target_person_id, nudge_type, content, metadata,
            confidence, generated_at, expires_at)
           VALUES (?,?,?,?,?,?,?)""",
        (
            target_person_id,
            "VISITOR_ALERT",
            content,
            json.dumps(metadata),
            0.9,
            time.time(),
            time.time() + 86400,
        ),
    )
    brain_db._conn.commit()
    return cur.lastrowid


def test_regex_swaps_existing_marker(tmp_path):
    """Plan v2 §9.1 Test 1 — D1 primary happy path.

    Asymmetric setup: marker `[visitor_name:unknown]`, metadata
    `visitor_name='visitor'`. The Session 114 literal-substring check
    would no-op here (its `if f"[visitor_name:{old_name}]" in content`
    check fails — `[visitor_name:visitor]` is NOT in the content).
    Regex `[^\\]]+` wildcard matches the `unknown` placeholder and the
    swap fires correctly.
    """
    from core.brain_agent import BrainDB

    brain_db = BrainDB(str(tmp_path / "brain.db"))
    try:
        nudge_id = _seed_visitor_alert_row(
            brain_db,
            visitor_id="p1",
            content="Someone visited: [visitor_name:unknown] spoke for a while.",
            metadata={"visitor_id": "p1", "visitor_name": "visitor"},
        )

        updated = brain_db.update_visitor_alert_for_promoted_person(
            person_id="p1", new_name="Lexi"
        )
        assert updated == 1, "MUST update exactly one row"

        row = brain_db._conn.execute(
            "SELECT content, metadata FROM proactive_nudges WHERE id = ?",
            (nudge_id,),
        ).fetchone()
        assert "[visitor_name:Lexi]" in row[0], (
            "Marker MUST be swapped to new name — without regex, the "
            "asymmetric metadata old_name='visitor' would not match the "
            "marker placeholder 'unknown' and the swap would silently no-op"
        )
        assert "[visitor_name:unknown]" not in row[0], (
            "Original placeholder MUST be replaced"
        )
        meta = json.loads(row[1])
        assert meta["visitor_name"] == "Lexi"
        assert meta["visitor_type"] == "known"
    finally:
        brain_db._conn.close()


def test_regex_noop_when_marker_absent(tmp_path):
    """Plan v2 §9.2 Test 2 — D1 defensive: no marker → no spurious content
    write, metadata still updated. Legacy data or schema-drift safety net.
    """
    from core.brain_agent import BrainDB

    brain_db = BrainDB(str(tmp_path / "brain.db"))
    try:
        nudge_id = _seed_visitor_alert_row(
            brain_db,
            visitor_id="p1",
            content="plain text with no markers",
            metadata={"visitor_id": "p1", "visitor_name": "visitor"},
        )

        updated = brain_db.update_visitor_alert_for_promoted_person(
            person_id="p1", new_name="Lexi"
        )
        assert updated == 1, "metadata still updated even when marker absent"

        row = brain_db._conn.execute(
            "SELECT content, metadata FROM proactive_nudges WHERE id = ?",
            (nudge_id,),
        ).fetchone()
        assert row[0] == "plain text with no markers", (
            "Content MUST be byte-identical when no marker present — "
            "re.sub on a no-match input returns the string unchanged"
        )
        meta = json.loads(row[1])
        assert meta["visitor_name"] == "Lexi"
        assert meta["visitor_type"] == "known"
    finally:
        brain_db._conn.close()


def test_regex_idempotent_when_already_renamed(tmp_path):
    """Plan v2 §9.3 Test 3 — D1 idempotency invariant.

    Repeated call with the same `new_name` against already-renamed content
    leaves content byte-identical. Defends against re-rename loops AND
    against future callers that may double-fire on a single promotion.
    """
    from core.brain_agent import BrainDB

    brain_db = BrainDB(str(tmp_path / "brain.db"))
    try:
        original_content = "Someone visited: [visitor_name:Lexi] spoke for a while."
        nudge_id = _seed_visitor_alert_row(
            brain_db,
            visitor_id="p1",
            content=original_content,
            metadata={"visitor_id": "p1", "visitor_name": "Lexi", "visitor_type": "known"},
        )

        updated = brain_db.update_visitor_alert_for_promoted_person(
            person_id="p1", new_name="Lexi"
        )
        assert updated == 1

        row = brain_db._conn.execute(
            "SELECT content FROM proactive_nudges WHERE id = ?",
            (nudge_id,),
        ).fetchone()
        assert row[0] == original_content, (
            "Idempotent call MUST leave content byte-identical — "
            "regex matches the existing marker, replacement produces "
            "the same `[visitor_name:Lexi]`; net change is zero"
        )
    finally:
        brain_db._conn.close()


def test_update_alert_uses_regex_not_literal_substring():
    """Plan v2 §9.4 Test 4 — D1 structural AST forward-property.

    Parses `core/brain_agent.py`, locates
    `update_visitor_alert_for_promoted_person`, walks the function body
    and asserts:
      (a) at least one `Call` node references `re.sub`
      (b) no `Call` to `.replace(` exists whose first arg is an f-string
          literal of the f"[visitor_name:{X}]" shape — that's the
          Session 114 literal-substring pattern D1 fix removed

    AST over source-inspection because docstring / comment / log strings
    can contain the literal-substring f-string form even when the actual
    call is gone (4th instance of this pattern across the sibling
    arc — see `feedback_adjacent_string_literal_normalizer.md`).
    """
    from core import brain_agent

    src = inspect.getsource(brain_agent)
    tree = ast.parse(src)

    target_fn = None
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.FunctionDef)
            and node.name == "update_visitor_alert_for_promoted_person"
        ):
            target_fn = node
            break
    assert target_fn is not None, (
        "update_visitor_alert_for_promoted_person not found in brain_agent.py"
    )

    # (a) at least one `re.sub` call in the body
    has_re_sub = False
    for node in ast.walk(target_fn):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if (
                node.func.attr == "sub"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "re"
            ):
                has_re_sub = True
                break
    assert has_re_sub, (
        "update_visitor_alert_for_promoted_person MUST call `re.sub` — "
        "the literal-substring `content.replace(f'[visitor_name:{old_name}]', "
        "f'[visitor_name:{new_name}]')` pattern is the canary-2 root cause "
        "and D1 explicitly removes it"
    )

    # (b) no `.replace(` call whose first arg is an f-string of shape
    # f"[visitor_name:{X}]"  (the Session 114 pattern)
    for node in ast.walk(target_fn):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "replace"
            and node.args
        ):
            first = node.args[0]
            if isinstance(first, ast.JoinedStr):
                rendered = "".join(
                    v.value if isinstance(v, ast.Constant) else ""
                    for v in first.values
                )
                assert "[visitor_name:" not in rendered, (
                    "Literal `[visitor_name:{old}]` substring `.replace(` "
                    "pattern detected — D1 removes this in favor of `re.sub`"
                )


def test_regex_replacement_handles_backslash_in_new_name(tmp_path):
    """Plan v2 §2.5 Test 4b (NEW in Plan v2) — defense-in-depth.

    `re.sub(pattern, replacement, string)` interprets the REPLACEMENT
    argument as a template supporting `\\1`, `\\g<name>`, `\\\\`, etc.
    If `new_name` contains a backslash and we use f-string replacement,
    the backslash gets interpreted (literal backslash → start of escape
    sequence) and either raises `re.error` or produces unexpected output.

    Plan v2 §2.4 locks the lambda-replacement implementation: the lambda
    returns `new_marker` VERBATIM (no backreference interpretation).
    This test verifies that contract.

    Realistic risk: name-injection vectors via LLM-hallucinated names,
    future enrollment-from-path workflows, or non-ASCII → backslash
    locale glitches.
    """
    from core.brain_agent import BrainDB

    brain_db = BrainDB(str(tmp_path / "brain.db"))
    try:
        nudge_id = _seed_visitor_alert_row(
            brain_db,
            visitor_id="p1",
            content="Someone visited: [visitor_name:unknown] spoke for a while.",
            metadata={"visitor_id": "p1", "visitor_name": "visitor"},
        )

        # `new_name` contains a literal backslash. With an f-string
        # replacement, `re.sub` would interpret `\n` as a newline (or
        # raise on `\1`); with the lambda replacement, the backslash is
        # preserved as-is.
        backslash_name = "Test\\name"
        updated = brain_db.update_visitor_alert_for_promoted_person(
            person_id="p1", new_name=backslash_name
        )
        assert updated == 1

        row = brain_db._conn.execute(
            "SELECT content, metadata FROM proactive_nudges WHERE id = ?",
            (nudge_id,),
        ).fetchone()
        assert "[visitor_name:Test\\name]" in row[0], (
            "Lambda replacement MUST preserve the literal backslash in "
            "new_name verbatim. If this assertion fails, the implementation "
            "likely reverted to f-string replacement, which interprets "
            "regex backreferences (\\1, \\g<name>, \\\\) and corrupts "
            f"backslash-bearing names. Actual content: {row[0]!r}"
        )
        meta = json.loads(row[1])
        assert meta["visitor_name"] == backslash_name, (
            "Metadata stores the new_name verbatim (independent of regex)"
        )
    finally:
        brain_db._conn.close()


# ───────────────────────────────────────────────────────────────────────
# Phase 2 — Behavioral E2E (Plan v2 §9.5 Test 5)
# ───────────────────────────────────────────────────────────────────────


async def test_visitor_alert_marker_swap_e2e(tmp_path):
    """Plan v2 §9.5 Test 5 — full lifecycle behavioral E2E.

    Reproduces the exact canary-2 failure mode end-to-end through the
    real `_run_visitor_alert` + `on_identity_confirmed` paths (NOT
    the BrainDB method in isolation):

      1. Stranger session opens; stranger has spoken at least once.
      2. `_run_visitor_alert(stranger_pid)` fires at session end —
         queues a VISITOR_ALERT nudge with the asymmetric shape:
         content marker `[visitor_name:unknown]`, metadata
         `visitor_name='visitor'`.
      3. User reveals their name; faces.db person row renamed +
         person_type flipped to 'known'.
      4. `on_identity_confirmed(stranger_pid, 'visitor', 'Lexi')`
         fires inside the promotion chain, which calls
         `update_visitor_alert_for_promoted_person(stranger_pid, 'Lexi')`.

    Canary-2 root cause: step (4)'s literal-substring check fired on
    `[visitor_name:visitor]` (from metadata) which is NOT in the
    content (which has `[visitor_name:unknown]`), so the swap silently
    no-op'd. Brain later saw `[visitor_name:unknown]` in the addendum
    and followed the unknown-branch template ("Someone stopped by but
    didn't tell me their name"). Owner asked about Lexi anyway, brain
    fabricated absence.

    D1 fix: regex-replace with `[^\\]]+` wildcard matches the `unknown`
    placeholder regardless of metadata `old_name`, swap succeeds end-to-end.

    Asserts:
      (a) Pre-promotion: nudge content has `[visitor_name:unknown]`
          (stranger branch of `_run_visitor_alert`)
      (b) Post-promotion: nudge content has `[visitor_name:Lexi]`
          (D1 regex swap succeeded)
      (c) Post-promotion: metadata `visitor_name == 'Lexi'`
      (d) Post-promotion: metadata `visitor_type == 'known'`
    """
    import sqlite3 as _sq3
    from core.brain_agent import BrainDB, BrainOrchestrator

    # Set up orchestrator with real BrainDB + faces.db schema, graph_db None.
    orch = BrainOrchestrator.__new__(BrainOrchestrator)
    orch._brain_db = BrainDB(str(tmp_path / "brain.db"))
    orch._faces_conn = _sq3.connect(str(tmp_path / "faces.db"))
    orch._faces_conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS persons (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            person_type TEXT NOT NULL DEFAULT 'known'
        );
        CREATE TABLE IF NOT EXISTS conversation_log (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            person_id TEXT NOT NULL,
            role      TEXT NOT NULL,
            content   TEXT NOT NULL
        );
        """
    )
    orch._faces_conn.commit()
    # _graph_db = None → on_identity_confirmed skips graph rebuild branch.
    orch._graph_db = None
    orch._kuzu_degraded = False
    try:
        # (1) Seed best_friend + stranger.
        bf_id = "jagan_001"
        stranger_pid = "stranger_abc"
        orch._faces_conn.execute(
            "INSERT INTO persons (id, name, person_type) VALUES (?,?,?)",
            (bf_id, "Jagan", "best_friend"),
        )
        orch._faces_conn.execute(
            "INSERT INTO persons (id, name, person_type) VALUES (?,?,?)",
            (stranger_pid, "visitor", "stranger"),
        )
        # Conversation turn (scope gate requires turn_count > 0).
        orch._faces_conn.execute(
            "INSERT INTO conversation_log (person_id, role, content) "
            "VALUES (?,?,?)",
            (stranger_pid, "user", "hi there"),
        )
        orch._faces_conn.commit()

        # (2) Fire visitor alert at session-end. Stranger branch of
        # _run_visitor_alert writes [visitor_name:unknown] marker because
        # person_type='stranger' AND name.lower()=='visitor'.
        await orch._run_visitor_alert(stranger_pid)

        nudges_before = orch._brain_db.get_pending_nudges(bf_id)
        assert len(nudges_before) == 1, (
            "Visitor alert MUST queue for the best_friend at stranger "
            "session end (Session 98 Bug A behavior preserved)"
        )
        # (a) Asymmetric marker confirmed pre-promotion.
        assert "[visitor_name:unknown]" in nudges_before[0]["content"], (
            "Stranger branch MUST write `[visitor_name:unknown]` marker — "
            "this is exactly the canary-2 asymmetry that broke S114's "
            "literal-substring swap"
        )
        assert nudges_before[0]["metadata"]["visitor_name"] == "visitor", (
            "Stranger metadata MUST store the placeholder name 'visitor' "
            "(this is the asker side of the asymmetry)"
        )

        # (3) Promote stranger to known: rename row + flip person_type.
        orch._faces_conn.execute(
            "UPDATE persons SET name = ?, person_type = ? WHERE id = ?",
            ("Lexi", "known", stranger_pid),
        )
        orch._faces_conn.commit()

        # (4) Trigger the promotion chain. on_identity_confirmed calls
        # update_visitor_alert_for_promoted_person inside its brain.db
        # transaction. With _graph_db=None the post-transaction graph
        # rebuild branch is skipped cleanly.
        orch.on_identity_confirmed(
            stranger_pid, old_name="visitor", new_name="Lexi"
        )

        nudges_after = orch._brain_db.get_pending_nudges(bf_id)
        assert len(nudges_after) == 1, (
            "Promotion MUST NOT duplicate the nudge — same row updated in-place"
        )
        content = nudges_after[0]["content"]
        # (b) D1 regex swap succeeded.
        assert "[visitor_name:Lexi]" in content, (
            "Post-promotion marker MUST be `[visitor_name:Lexi]`. This is "
            "the canary-2 regression guard: without D1's regex swap, the "
            "marker stays `[visitor_name:unknown]` and brain follows the "
            "unknown-branch VISITOR CONTEXT template, fabricating absence "
            "when owner asks about Lexi. Actual content: " + repr(content)
        )
        assert "[visitor_name:unknown]" not in content, (
            "Original placeholder MUST be fully replaced; mixed content "
            "indicates the swap fired but failed to cover the asymmetric case"
        )
        # (c)+(d) Metadata reconciled.
        meta_after = nudges_after[0]["metadata"]
        assert meta_after["visitor_name"] == "Lexi"
        assert meta_after["visitor_type"] == "known", (
            "Promotion MUST flip visitor_type to 'known' so downstream "
            "consumers can render the name-known branch of VISITOR CONTEXT"
        )
    finally:
        orch._brain_db._conn.close()
        orch._faces_conn.close()
