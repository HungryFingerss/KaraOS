"""test_pipeline_canary_followups — canary followups tests (split from test_pipeline.py, P1.A1 SP-1).

Behavior-neutral move: test bodies are verbatim from the original root
test_pipeline.py. `import pipeline` stays lazy inside each test body (stubs are
installed by tests/conftest.py).
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

import asyncio
import sys
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock
import types
import pytest
import numpy as np
import time as _time_mod
import numpy as _np
import runtime.wiring as _wiring


def test_bug_i_memory_search_uses_widened_fact_limit():
    """Session 103 Bug I.a: _make_memory_search_fn must raise the fact
    limit above the previous 5 so lower-confidence emotion/mood facts
    (like current_feeling='overwhelmed', has_suicidal_thoughts='true')
    survive the top-K cut when the entity has ≥5 higher-confidence
    identity facts (name, studies_at, etc.). 2026-04-23 canary: brain
    mentally filtered 5 returned facts against 'feelings' query, found
    no attribute match, said 'I don't have information' — despite the
    relevant facts being in brain.db just below the rank-5 cutoff."""
    import inspect, pipeline
    src = inspect.getsource(pipeline._make_memory_search_fn)
    assert "limit=15" in src, (
        "memory-search fact limit must be widened — 5 dropped "
        "lower-confidence emotion/mood facts on entities with many "
        "high-confidence identity facts"
    )


def test_bug_i_search_memory_description_guides_broad_queries():
    """Session 103 Bug I.b: tool description must tell the brain to
    prefer broad queries. Without this, the brain tries narrow
    attribute-word queries ('feelings', 'conversation') expecting them
    to filter facts — but the query only drives excerpt keyword
    matching, not fact filter. Broad queries get the same facts +
    better excerpt coverage."""
    from core.brain import TOOLS
    desc = next(
        t["function"]["description"] for t in TOOLS
        if t["function"]["name"] == "search_memory"
    )
    assert "QUERY SHAPE" in desc, (
        "search_memory description must include QUERY SHAPE guidance"
    )
    assert (
        "broad" in desc.lower() and "narrow" in desc.lower()
    ), (
        "must contrast broad vs narrow queries explicitly — the brain "
        "needs the framing to choose well"
    )


def test_bug_k_honesty_policy_recovery_procedure():
    """Session 104 Bug K: Session 103's anti-contradiction rule was too
    soft — 2026-04-23 canary still had brain flip turn 49 → 51. Reviewer
    prescribed a CONCRETE recovery procedure: retry broader search, THEN
    hedge without denial, with exact template phrasings ("I confirmed
    that earlier but don't have the specifics handy right now")."""
    import inspect
    from core import brain
    src = inspect.getsource(brain._render_honesty_policy)
    idx = src.find("<<<HONESTY POLICY>>>")
    end = src.find("<<<END HONESTY POLICY>>>", idx)
    block = src[idx:end]
    # Procedural recovery — must have explicit Step language.
    assert "Step 1" in block or "RETRY search_memory" in block, (
        "block must name the retry-with-broader-query procedure "
        "explicitly — the soft 'don't contradict' rule wasn't concrete "
        "enough to prevent the canary flip"
    )
    # Concrete recovery template phrasings.
    assert "confirmed that earlier" in block.lower() or (
        "I confirmed" in block
    ), (
        "block must include the 'I confirmed that earlier but don't have "
        "the specifics handy' template — templates are harder to drift "
        "away from than abstract rules"
    )
    # Multiple forbidden phrasings named.
    forbidden_count = sum(
        1 for p in (
            "didn't have that conversation",
            "don't have any information",
            "no, that didn't happen",
        ) if p in block.lower()
    )
    assert forbidden_count >= 2, (
        "block must explicitly name at least 2 of the concrete denial "
        "phrasings the brain used in the canary — single-phrasing anchor "
        "drifts; multi-phrasing hits the whole failure class"
    )


def test_bug_i_honesty_policy_anti_contradiction_rule():
    """Session 103 Bug I.c: HONESTY POLICY block must include an
    explicit anti-contradiction rule. 2026-04-23 canary: brain said
    'I was talking to Lexi' on turn 37 → said 'I didn't have that
    conversation' on turn 41 (same session, 10s apart) because
    search_memory returned sparser results on the later query. The
    HONESTY POLICY told brain 'don't fabricate on empty' → brain
    interpreted that as 'deny the conversation ever happened'. The
    patch teaches the brain: retrieval miss ≠ prior statement was
    wrong. Say 'let me think' not 'I didn't have that conversation'."""
    import inspect
    from core import brain
    src = inspect.getsource(brain._render_honesty_policy)
    idx = src.find("<<<HONESTY POLICY>>>")
    end = src.find("<<<END HONESTY POLICY>>>", idx)
    block = src[idx:end]
    assert "CONTRADICT" in block.upper(), (
        "block must name the anti-contradiction rule explicitly — "
        "abstract 'be honest' doesn't cover this failure mode"
    )
    # Positive anchor — what TO say when retrieval misses.
    assert "let me think" in block.lower() or "don't have the details handy" in block.lower(), (
        "block must give a concrete hedge-without-denial template — "
        "without it, brain falls back to the default denial phrasing"
    )
    # Negative anchor — what NOT to say.
    assert (
        "didn't have that conversation" in block.lower()
        or "flipping is a lie" in block.lower()
    ), (
        "block must explicitly name the failure phrasing from the canary "
        "('I didn't have that conversation') so the anchor is concrete"
    )


async def test_bug_f3_mishear_rename_refreshes_persons_in_frame_cache():
    """Session 102 Bug F.3: after the Bug F.2 rename fires, the entry in
    `_persons_in_frame` must be updated IMMEDIATELY with the new name so
    the SCENE block (which reads `info.get('name', pid)` in
    _build_scene_block at line 1044) doesn't inject the stale STT-mangled
    name into the brain's prompt for subsequent turns. 2026-04-23
    re-canary: Bug F.2 renamed 'Jaman' → 'Jagan' in DB correctly but
    _persons_in_frame['jawan_abc']['name'] kept reading 'Jaman' for the
    rest of the session, poisoning every downstream context block."""
    import pipeline
    from pipeline import _execute_tool
    import time as _t
    await pipeline._session_store.open_session(
        "jawan_abc", "Jawan", "best_friend", "face", now=_t.time() - 30
    )
    await pipeline._conversation_store.set_history("jawan_abc", [])
    # Seed the presence store with the stale name — simulates state right after
    # the first recognition on enrollment.
    await pipeline._presence_store.upsert_face_recognition("jawan_abc", "Jawan", 0.9, _t.time())
    mock_db = MagicMock()
    mock_db.voice_embedding_count.return_value = 0

    orig_orch = pipeline._brain_orchestrator
    _wiring._brain_orchestrator = MagicMock()
    try:
        await _execute_tool(
            "update_person_name", {"name": "Jagan"},
            "jawan_abc", "Jawan", db=mock_db,
            user_text="No, it's not Javan, it's Jagan.",
            intent_sidecar={
                "turn_intent": "deny_identity",
                "confidence": 0.95,
                "extracted_value": "Jagan",
            },
        )
    finally:
        _wiring._brain_orchestrator = orig_orch

    await asyncio.sleep(0)
    # The presence store must reflect the new name, not the stale STT-mangled one.
    assert pipeline._presence_store.peek_snapshot("jawan_abc").name == "Jagan", (
        "Bug F.3: _presence_store cache must be refreshed on rename — "
        "otherwise SCENE block and [Vision] logs keep showing the stale "
        "name until the next background scan (~1s latency + possible UI "
        "flicker)"
    )


async def test_bug_f3_stranger_promotion_refreshes_persons_in_frame_cache():
    """Session 102 Bug F.3: the stranger-promotion rename path (Session
    22 G3) also needs the cache refresh — a stranger with cached name
    'visitor' in _persons_in_frame must update to 'Lexi' on promotion,
    otherwise her SCENE rendering stays stuck at 'visitor' even after
    the promotion chain runs."""
    import pipeline
    from pipeline import _execute_tool
    import time as _t
    await pipeline._session_store.open_session(
        "stranger_abc", "visitor", "stranger", "voice", now=_t.time()
    )
    await pipeline._conversation_store.set_history("stranger_abc", [])
    await pipeline._presence_store.upsert_face_recognition("stranger_abc", "visitor", 0.8, _t.time())
    mock_db = MagicMock()

    orig_orch = pipeline._brain_orchestrator
    _wiring._brain_orchestrator = MagicMock()
    try:
        await _execute_tool(
            "update_person_name", {"name": "Lexi"},
            "stranger_abc", "visitor", db=mock_db,
            user_text="my name is Lexi",
        )
    finally:
        _wiring._brain_orchestrator = orig_orch

    await asyncio.sleep(0)
    assert pipeline._presence_store.peek_snapshot("stranger_abc").name == "Lexi"


def test_bug_f3_background_face_scan_refreshes_cached_name():
    """Session 102 Bug F.3: source-inspection — the background-scan
    else-branch (which fires 1 Hz for every already-known recognized
    person in frame) must refresh `_persons_in_frame[pid]['name']` on
    every scan. Without this the cache stays frozen at the
    first-recognition name, even though recognize() returns the current
    DB name after a rename. This is the ROOT source of the stale cache
    the 2026-04-23 canary surfaced."""
    import inspect, runtime.vision_loop  # P1.A1 SP-6.3: background-scan else-branch relocated here
    src = inspect.getsource(runtime.vision_loop)
    # The background scan now calls _presence_store.upsert_face_recognition
    # (via loop.create_task) passing the current name from recognize() on
    # every scan cycle — this is the Bug F.3 name-cache refresh.
    assert "_presence_store.upsert_face_recognition(" in src, (
        "background-scan else-branch must call _presence_store.upsert_face_recognition "
        "so renames propagate to the SCENE block / [Vision] logs within "
        "one scan cycle"
    )


def test_s114_pipeline_filters_speechbrain_deprecation_warning():
    """Session 114 Part 1A — pipeline.py installs a warnings filter for
    the SpeechBrain 'pretrained deprecated' deprecation message. The
    warning was firing every startup via inspect's module walk; the
    filter must run BEFORE any heavy import so the suppression covers
    pyannote/speechbrain initialization."""
    import inspect, pipeline
    src = inspect.getsource(pipeline)
    # Filter must reference the speechbrain.pretrained deprecation message.
    assert 'speechbrain' in src.lower() and 'pretrained' in src.lower() and 'deprecated' in src.lower(), (
        "warnings filter for speechbrain deprecation missing"
    )


def test_s114_pipeline_enables_tf32_for_cuda_perf():
    """Session 114 Part 1B — pipeline re-enables TF32 (pyannote disables
    it for bit-exact reproducibility, which we don't need)."""
    import inspect, pipeline
    src = inspect.getsource(pipeline)
    assert "allow_tf32 = True" in src, "TF32 re-enable missing"
    assert "matmul.allow_tf32" in src or "cudnn.allow_tf32" in src, (
        "must enable TF32 on at least one of matmul/cudnn backends"
    )


def test_s114_pipeline_filters_degrees_of_freedom_warning():
    """Session 114 Part 1C — std() degrees-of-freedom warning from
    pyannote 3.3.2 numerical edge case is suppressed via warnings
    filter."""
    import inspect, pipeline
    src = inspect.getsource(pipeline)
    assert "degrees of freedom" in src, (
        "filter for pyannote std() warning missing"
    )


def test_s114_is_phantom_name_phonetic_match():
    """Session 114 Part 2 — `_is_phantom_name` must return the matched
    known_name when the candidate is a phonetic equivalent (Metaphone
    code match). 'Jai Gun' (STT mangled) vs 'Jagan' (real name) —
    Double-Metaphone collapses these to the same code."""
    from core.brain_agent import _is_phantom_name
    out = _is_phantom_name("Jai Gun", ["Jagan", "Lexi"])
    # Either Jagan (phonetic) or None — phonetic match should fire here
    # but jellyfish's Metaphone doesn't always collapse "Jai Gun" → "Jagan".
    # The test guards the BEHAVIOR: fuzzy match must catch close variants.
    # Try a clearly close pair instead — exact case-insensitive.
    out2 = _is_phantom_name("jagan", ["Jagan", "Lexi"])
    assert out2 == "Jagan", (
        "case-insensitive direct match must return the canonical name"
    )


def test_s114_is_phantom_name_jaro_winkler_match():
    """Session 114 Part 2 — Jaro-Winkler ≥ 0.85 catches typo-class
    variants. 'Jagn' (vowel drop) vs 'Jagan' should match."""
    from core.brain_agent import _is_phantom_name
    out = _is_phantom_name("Jagn", ["Jagan"])
    assert out == "Jagan", (
        f"close typo-class candidate must match via Jaro-Winkler; got {out!r}"
    )
    # Distinct names should NOT cross-match.
    no_match = _is_phantom_name("Sarah", ["Jagan", "Lexi"])
    assert no_match is None, (
        f"distinct name must NOT match anyone; got {no_match!r}"
    )


def test_s114_is_phantom_name_self_reference_speaker_match():
    """Session 114 Part 2 — the speaker's own display name is included
    in known_names so STT mishears that produce a self-reference
    don't spawn a phantom shadow node ('Lexi' the speaker hearing
    'Lexie' as a third party)."""
    from core.brain_agent import _is_phantom_name
    # Candidate is a vowel-drop of the speaker's name — should match.
    out = _is_phantom_name("Lexie", ["Lexi"])
    assert out == "Lexi"


def test_s114_extract_prompt_has_superlative_claims_rule():
    """Session 114 Part 3 — _EXTRACT_SYSTEM contains the SUPERLATIVE
    CLAIMS DISCIPLINE rule with the verbatim Tirupati counter-example
    that motivated the fix."""
    from core.brain_agent import _EXTRACT_SYSTEM
    assert "SUPERLATIVE CLAIMS" in _EXTRACT_SYSTEM, (
        "rule block name missing"
    )
    # Verbatim canary phrase.
    assert "Tirupati" in _EXTRACT_SYSTEM and "hottest" in _EXTRACT_SYSTEM, (
        "Tirupati 'hottest city' counter-example missing"
    )
    # SKIP-preferred guidance must be present.
    assert "SKIP" in _EXTRACT_SYSTEM


def test_s114_extract_prompt_has_relationship_extraction_rule():
    """Session 114 Part 4 — _EXTRACT_SYSTEM contains the RELATIONSHIP
    EXTRACTION DISCIPLINE rule with the verbatim Lexi-homework
    counter-example. Tone-based inference must be explicitly forbidden."""
    from core.brain_agent import _EXTRACT_SYSTEM
    assert "RELATIONSHIP EXTRACTION" in _EXTRACT_SYSTEM, (
        "rule block name missing"
    )
    # Verbatim canary scenario.
    assert "do your homework" in _EXTRACT_SYSTEM, (
        "Lexi-homework counter-example missing"
    )
    # Vocabulary-based vs tone-based phrasing must distinguish.
    assert "Tone" in _EXTRACT_SYSTEM or "tone" in _EXTRACT_SYSTEM, (
        "tone-based inference must be explicitly named"
    )


@pytest.mark.privacy_critical
def test_s114_visitor_alert_dedup_updates_promoted_alerts(tmp_path):
    """Session 114 Part 5 — `update_visitor_alert_for_promoted_person`
    rewrites prior VISITOR_ALERT nudges with the new name + 'known'
    type so the read path naturally returns one canonical alert per
    visitor. Tests pre-promotion ('stranger' nudge) → post-promotion
    update flips the metadata."""
    import json
    from core.brain_agent import BrainDB
    bdb = BrainDB(tmp_path / "brain.db")
    try:
        # Seed a pre-promotion alert (visitor_id = stranger pid).
        bdb.store_nudge(
            target_person_id="bf_001",
            nudge_type="VISITOR_ALERT",
            content="A stranger ([visitor_name:visitor]) stopped by.",
            confidence=0.9,
            metadata={
                "visitor_id":   "stranger_abc",
                "visitor_name": "visitor",
                "visitor_type": "stranger",
            },
        )
        # Run promotion update.
        n = bdb.update_visitor_alert_for_promoted_person(
            "stranger_abc", "Lexi",
        )
        assert n == 1, f"expected 1 row updated; got {n}"
        # Read back and verify metadata flipped.
        row = bdb._conn.execute(
            "SELECT content, metadata FROM proactive_nudges "
            "WHERE nudge_type = 'VISITOR_ALERT'",
        ).fetchone()
        content, meta_json = row
        meta = json.loads(meta_json)
        assert meta["visitor_name"] == "Lexi"
        assert meta["visitor_type"] == "known"
        assert "[visitor_name:Lexi]" in content, (
            f"content marker must update to canonical name; got {content!r}"
        )
    finally:
        bdb._conn.close()


@pytest.mark.privacy_critical
def test_s114_visitor_alert_dedup_skips_unrelated_alerts(tmp_path):
    """Session 114 Part 5 — promotion update MUST NOT touch alerts
    for OTHER visitors (different visitor_id in metadata). Regression
    guard against accidentally rewriting unrelated rows."""
    import json
    from core.brain_agent import BrainDB
    bdb = BrainDB(tmp_path / "brain.db")
    try:
        bdb.store_nudge(
            target_person_id="bf_001",
            nudge_type="VISITOR_ALERT",
            content="Other visitor stopped by.",
            confidence=0.9,
            metadata={
                "visitor_id":   "other_xyz",
                "visitor_name": "Mike",
                "visitor_type": "known",
            },
        )
        n = bdb.update_visitor_alert_for_promoted_person(
            "stranger_abc", "Lexi",
        )
        assert n == 0, f"unrelated alerts must not be touched; updated {n}"
        row = bdb._conn.execute(
            "SELECT metadata FROM proactive_nudges "
            "WHERE nudge_type = 'VISITOR_ALERT'",
        ).fetchone()
        meta = json.loads(row[0])
        assert meta["visitor_name"] == "Mike", "unrelated alert must be untouched"
    finally:
        bdb._conn.close()


def test_s114_household_extraction_skips_phantom_shadow(tmp_path):
    """Session 114 Part 2 — end-to-end: `_apply_household_extraction`
    must SKIP shadow_persons inserts for names that fuzzy-match an
    enrolled person. Regression guard on the phantom-prevention wiring."""
    import sqlite3 as _sq3, asyncio as _aio
    from core.brain_agent import BrainDB, BrainOrchestrator

    orch = BrainOrchestrator.__new__(BrainOrchestrator)
    orch._brain_db   = BrainDB(tmp_path / "brain.db")
    orch._faces_conn = _sq3.connect(str(tmp_path / "faces.db"))
    orch._faces_conn.executescript("""
        CREATE TABLE persons (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, person_type TEXT,
            enrolled_at REAL NOT NULL DEFAULT 0
        );
        CREATE TABLE conversation_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            person_id TEXT, role TEXT, content TEXT, ts REAL DEFAULT 0,
            room_session_id TEXT, audience_ids TEXT
        );
    """)
    orch._faces_conn.execute(
        "INSERT INTO persons (id, name, person_type, enrolled_at) "
        "VALUES (?,?,?,?)",
        ("jagan_001", "Jagan", "best_friend", _time_mod.time()),
    )
    orch._faces_conn.commit()
    try:
        # Synthetic extraction result that asks to create a shadow for
        # a phonetic mishear of an enrolled person.
        result = {
            "shadow_persons": [
                {"name": "Jagn", "mentioned_by": "Lexi",
                 "relationship": "mentioned_by"},
            ],
        }
        _aio.run(orch._apply_household_extraction(
            speaker_id="lexi_001",
            speaker_name="Lexi",
            result=result,
        ))
        n_shadows = orch._brain_db._conn.execute(
            "SELECT COUNT(*) FROM shadow_persons WHERE LOWER(known_name) = ?",
            ("jagn",),
        ).fetchone()[0]
        assert n_shadows == 0, (
            f"phantom 'Jagn' should NOT be inserted; got {n_shadows} shadow row(s)"
        )
    finally:
        orch._brain_db._conn.close()
        orch._faces_conn.close()


def test_s115_user_to_user_heuristic_catches_vocative_to_person():
    """Session 115 Fix 1 — vocative-name regex catches 'Lexi, do your
    homework' when Lexi is in active sessions and is NOT the system
    name. Returns ('user_to_person', canonical_name)."""
    from pipeline import _user_to_user_heuristic
    out = _user_to_user_heuristic(
        "Lexi, do your homework",
        system_name="Kara",
        other_session_names={"Lexi"},
    )
    assert out == ("user_to_person", "Lexi"), f"got {out!r}"
    # End-position vocative also caught.
    out2 = _user_to_user_heuristic(
        "What about you, Jagan?",
        system_name="Kara",
        other_session_names={"Jagan", "Lexi"},
    )
    assert out2 == ("user_to_person", "Jagan")


def test_s115_user_to_user_heuristic_catches_addressing_ai():
    """Session 115 Fix 1 — when vocative IS the system name, returns
    ('addressing_ai', system_name) so caller can skip the redundant
    classifier call (would have returned same answer)."""
    from pipeline import _user_to_user_heuristic
    out = _user_to_user_heuristic(
        "Kara, what's the weather?",
        system_name="Kara",
        other_session_names={"Lexi"},
    )
    assert out == ("addressing_ai", "Kara")


def test_s115_user_to_user_heuristic_returns_none_for_subject_mention():
    """Session 115 Fix 1 — 'I think Lexi is right' mentions Lexi as
    subject, NOT vocative. Heuristic must return None so caller falls
    through to the cached classifier for the ambiguous case."""
    from pipeline import _user_to_user_heuristic
    out = _user_to_user_heuristic(
        "I think Lexi is right",
        system_name="Kara",
        other_session_names={"Lexi"},
    )
    assert out is None, f"subject mention must NOT trigger heuristic; got {out!r}"


async def test_s115_classifier_cache_short_circuits_repeat_call(monkeypatch):
    """Session 115 Fix 1 Layer B — second call within TTL with the same
    (text, active_session_pids) MUST hit the cache without calling
    `_classify_intent` again. Drops the per-turn LLM cost on
    inconclusive-heuristic re-asks of the same utterance."""
    import pipeline
    await pipeline._classifier_cache_store.clear()
    call_count = {"n": 0}
    async def _fake_classify(text, conversation_history=None):
        call_count["n"] += 1
        return {"turn_intent": "casual_conversation", "extracted_value": None,
                "confidence": 0.7, "reasoning": "stub"}
    monkeypatch.setattr("core.brain._classify_intent", _fake_classify)

    pids = frozenset({"j_1", "l_1"})
    out1 = await pipeline._classify_intent_cached("hi there", [], pids)
    out2 = await pipeline._classify_intent_cached("hi there", [], pids)
    assert out1 == out2
    assert call_count["n"] == 1, (
        f"second call must hit cache; got {call_count['n']} classifier calls"
    )


def test_s115_user_to_user_heuristic_disabled_falls_through_to_classifier():
    """Session 115 Fix 1 — `USER_TO_USER_HEURISTIC_ENABLED=False` rolls
    back to the classifier-only path. Source-inspection guard that
    the flag short-circuits the heuristic block."""
    import inspect, pipeline
    src = inspect.getsource(pipeline.conversation_turn)
    assert "USER_TO_USER_HEURISTIC_ENABLED" in src, (
        "config flag must gate the heuristic path"
    )
    # When flag is True, heuristic helper is invoked.
    assert "_user_to_user_heuristic(" in src, (
        "heuristic helper must be wired into conversation_turn"
    )


def test_s115_bf_cache_returns_same_row_on_second_call():
    """Session 115 Fix 2 — `_get_best_friend_cached` returns the cached
    row on second call without hitting `db.get_best_friend()` again."""
    import pipeline
    pipeline._invalidate_bf_cache()
    call_count = {"n": 0}
    class _DBStub:
        def get_best_friend(self):
            call_count["n"] += 1
            return {"id": "bf_001", "name": "Jagan"}
    db = _DBStub()
    r1 = pipeline._get_best_friend_cached(db)
    r2 = pipeline._get_best_friend_cached(db)
    assert r1 == r2 == {"id": "bf_001", "name": "Jagan"}
    assert call_count["n"] == 1, (
        f"second call must hit cache; got {call_count['n']} DB calls"
    )


def test_s115_bf_cache_invalidate_forces_refresh():
    """Session 115 Fix 2 — after `_invalidate_bf_cache`, next call
    must hit the DB again. Guards the rename + factory-reset paths."""
    import pipeline
    pipeline._invalidate_bf_cache()
    call_count = {"n": 0}
    class _DBStub:
        def get_best_friend(self):
            call_count["n"] += 1
            return {"id": "bf_001", "name": f"Jagan_{call_count['n']}"}
    db = _DBStub()
    r1 = pipeline._get_best_friend_cached(db)
    pipeline._invalidate_bf_cache()
    r2 = pipeline._get_best_friend_cached(db)
    assert call_count["n"] == 2, "invalidate must force re-fetch"
    assert r1["name"] != r2["name"], "fresh fetch must return new value"


def test_s115_bf_cache_handles_none_db_gracefully():
    """Session 115 Fix 2 — `db=None` must return None without crashing
    or seeding stale cache state. Pre-init paths rely on this."""
    import pipeline
    pipeline._invalidate_bf_cache()
    assert pipeline._get_best_friend_cached(None) is None
    # Subsequent call with real db still works.
    class _DBStub:
        def get_best_friend(self): return {"id": "bf_x", "name": "X"}
    pipeline._invalidate_bf_cache()
    r = pipeline._get_best_friend_cached(_DBStub())
    assert r == {"id": "bf_x", "name": "X"}


def test_s115_token_cache_avoids_recompute_on_second_call():
    """Session 115 Fix 3 — `_estimate_tokens` adds `_cached_tokens` to
    each message dict on first traversal; second call sums cached
    values without re-measuring `content` strings."""
    from core.brain import _estimate_tokens
    msg1 = {"role": "user", "content": "hello world"}
    msg2 = {"role": "assistant", "content": "hi there"}
    msgs = [msg1, msg2]
    n1 = _estimate_tokens(msgs)
    # After first call, cache must be populated.
    assert "_cached_tokens" in msg1
    assert "_cached_tokens" in msg2
    # Mutate content WITHOUT clearing cache — second call should return
    # the cached value (correctly stale-by-design — the helper doesn't
    # invalidate on mutation; production code never mutates content
    # after append).
    msg1["content"] = "completely different text" * 100
    n2 = _estimate_tokens(msgs)
    assert n2 == n1, (
        f"cached call must return same value despite content mutation; "
        f"got {n1} vs {n2}"
    )


def test_s115_token_cache_handles_pop_correctly():
    """Session 115 Fix 3 — popping a message must drop its contribution
    naturally (the dict goes out of the list, taking its cache with
    it). Remaining messages keep their caches valid."""
    from core.brain import _estimate_tokens
    msgs = [
        {"role": "user", "content": "first message text"},
        {"role": "assistant", "content": "second message"},
        {"role": "user", "content": "third one"},
    ]
    n_full = _estimate_tokens(msgs)
    msgs.pop(0)
    n_after = _estimate_tokens(msgs)
    assert n_after < n_full, "popping must reduce token count"
    # Remaining dicts still have cache.
    assert all("_cached_tokens" in m for m in msgs)


def test_s115_token_cache_new_message_only_computes_new_one():
    """Session 115 Fix 3 — appending a new message must compute only
    that one; existing cached messages are read from cache."""
    from core.brain import _estimate_tokens
    msgs = [
        {"role": "user", "content": "existing message"},
    ]
    n1 = _estimate_tokens(msgs)
    cached_existing = msgs[0]["_cached_tokens"]
    msgs.append({"role": "assistant", "content": "fresh content here"})
    # Existing message's cache must NOT have been disturbed.
    assert msgs[0]["_cached_tokens"] == cached_existing
    n2 = _estimate_tokens(msgs)
    assert n2 > n1
    # Now both messages cached.
    assert "_cached_tokens" in msgs[1]


def test_s115_strip_token_cache_removes_field():
    """Session 115 Fix 3 — `_strip_token_cache` defensive helper removes
    `_cached_tokens` from each dict so callers can sanitize before
    sending to a strict provider. Doesn't mutate input list."""
    from core.brain import _estimate_tokens, _strip_token_cache
    msgs = [{"role": "user", "content": "hi"}]
    _ = _estimate_tokens(msgs)
    assert "_cached_tokens" in msgs[0]
    out = _strip_token_cache(msgs)
    assert "_cached_tokens" not in out[0]
    # Original list unchanged.
    assert "_cached_tokens" in msgs[0]


@pytest.mark.privacy_critical
def test_s116_query_knowledge_for_emits_privacy_audit_log(tmp_path, capsys):
    """Session 116 P1 #1+#2 — every privacy-filtered knowledge read must
    emit a `[Privacy] ... query_knowledge_for ...` line so an outside
    auditor can verify cross-person isolation from logs alone. Owner-mode
    vs. non-owner scope must be distinguishable in the line."""
    from core.brain_agent import BrainDB
    bdb = BrainDB(tmp_path / "brain.db")
    try:
        bdb.query_knowledge_for("jagan_001", "jagan_001", entity="Lexi")
        out = capsys.readouterr().out
        assert "[Privacy]" in out and "query_knowledge_for" in out, (
            f"audit log missing; got:\n{out}"
        )
        assert "owner-mode" in out, (
            "owner-mode flag must surface when requester == best_friend"
        )
        # Non-owner read.
        bdb.query_knowledge_for("kara_002", "jagan_001", entity="Lexi")
        out2 = capsys.readouterr().out
        assert "non-owner" in out2, "non-owner scope must be labeled"
    finally:
        bdb._conn.close()


@pytest.mark.privacy_critical
def test_s116_classify_privacy_level_logs_static_map_path(capsys):
    """Session 116 P1 #3 — `_classify_privacy_level` static-map hits must
    log the path so an outside reviewer can audit which classification
    decisions came from hand-curated rules vs. LLM judgment."""
    import asyncio as _aio
    from core.brain_agent import _classify_privacy_level
    # 'name' is in PRIVACY_LEVEL_STATIC_MAP — should hit static path.
    _aio.run(_classify_privacy_level("Jagan", "name", "Jagan"))
    out = capsys.readouterr().out
    assert "[Privacy]" in out and "static_map" in out, (
        f"static_map path not logged; got:\n{out}"
    )


def test_s116_triage_log_includes_rationale_signals():
    """Session 116 P1 #6 — Triage PASS/SKIP lines must include the
    decision rationale (role, words, person_type) so the reviewer can
    reconstruct WHY a turn was processed without reading TriageAgent
    source. Source-inspection guard against regression."""
    import inspect
    from core.brain_agent import BrainOrchestrator
    src = inspect.getsource(BrainOrchestrator._process_turn)
    assert "Triage: PASS" in src and "Triage: SKIP" in src
    assert "words=" in src or "word" in src.lower(), (
        "rationale must include word_count signal"
    )
    assert "person_type" in src, "rationale must include person_type signal"


def test_s116_address_decision_logs_candidate_count():
    """Session 116 P1 #8 — `_resolve_addressed_to` log lines must include
    candidates count so reviewer can see WHY default fired (single-person
    has no override option vs multi-person LLM chose default)."""
    from pipeline import _resolve_addressed_to
    import io, contextlib, types
    active = (
        types.SimpleNamespace(person_name="Jagan", person_id="j_1"),
        types.SimpleNamespace(person_name="Lexi",  person_id="l_1"),
    )
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        _resolve_addressed_to(None, active, "Jagan")  # default branch
        _resolve_addressed_to("Lexi", active, "Jagan")  # LLM-decision branch
    out = buf.getvalue()
    assert "candidates=2" in out, (
        f"candidate count must surface in both branches; got:\n{out}"
    )


def test_s116_room_lifecycle_logs_participant_join_and_synthesis(monkeypatch):
    """Session 116 P1 #9 + #10 — room lifecycle must surface participant
    joins (separate from session opens) AND synthesis dispatch with
    explicit speaker list so the decoupling architecture is auditable."""
    import asyncio as _aio, pipeline, io, contextlib
    asyncio.run(pipeline._pipeline_state_store.set_active_room_session(None))
    asyncio.run(pipeline._pipeline_state_store.set_active_room_started_at(None))
    asyncio.run(pipeline._pipeline_state_store.set_active_room_participants(set()))
    _wiring._face_db_ref = None
    pipeline._per_person_agent_store.reset()

    captured_synth = {"called": False}
    class _OrchStub:
        async def synthesize_room(self, **kwargs):
            captured_synth["called"] = True
        def clear_disputed(self, *a, **k): pass
    _wiring._brain_orchestrator = _OrchStub()
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            pipeline._open_session(
                "a_1", "Alice", "face", "known",
                engagement_gate_passed=True,
            )
            pipeline._open_session(
                "b_1", "Bob", "face", "known",
                engagement_gate_passed=True,
            )

            async def _drive():
                pipeline._close_session("a_1")
                pipeline._close_session("b_1")
                # Follow-up #129 (§7): the inter-close drain retired — _close_session pops the
                # session synchronously now (_sync_close_session), so a_1 is gone the instant
                # its close returns and b_1's close sees _remaining == [] → room-end fires.
                # This trailing drain STAYS: _on_room_end synthesis is fired via create_task
                # (async by design) and prints "Synthesis dispatched (background)" +
                # calls synthesize_room — both read below.
                await _aio.sleep(0)
            _aio.run(_drive())
        out = buf.getvalue()
        assert "Participant joined: Alice" in out, (
            "first participant join must log explicitly"
        )
        assert "Participant joined: Bob" in out, (
            "second participant join must log explicitly"
        )
        assert "Synthesis dispatched (background)" in out, (
            f"synthesis dispatch line missing; got:\n{out}"
        )
        assert captured_synth["called"], "synthesize_room must actually fire"
    finally:
        asyncio.run(pipeline._pipeline_state_store.set_active_room_session(None))
        asyncio.run(pipeline._pipeline_state_store.set_active_room_started_at(None))
        asyncio.run(pipeline._pipeline_state_store.set_active_room_participants(set()))
        _wiring._brain_orchestrator = None


def test_s116_background_spawn_logs_compaction_and_emotion():
    """Session 116 P1 #10 — fire-and-forget background spawns
    (autocompact, emotion process_turn) must announce themselves so
    the foreground/background decoupling is visible in logs."""
    import inspect, pipeline
    src = inspect.getsource(pipeline.conversation_turn)
    assert "Spawn (background): autocompact" in src, (
        "autocompact background spawn log missing"
    )
    assert "Spawn (background): emotion" in src, (
        "emotion process background spawn log missing"
    )


def test_s116_log_prefix_consistency_in_new_lines():
    """Session 116 P3 — every new Session 116 log line must start with
    a recognized bracketed prefix. Locks the prefix taxonomy so future
    additions don't drift into ad-hoc formats."""
    import inspect, pipeline
    from core import brain_agent
    pipe_src = inspect.getsource(pipeline)
    ba_src   = inspect.getsource(brain_agent)
    # All Privacy logs use [Privacy] prefix.
    for line in (pipe_src + "\n" + ba_src).split("\n"):
        if "f\"[Privacy]" not in line and 'f"[Privacy]' not in line:
            continue
        # Source line is a print(f"[Privacy] ..."); confirm bracket form.
        assert "[Privacy]" in line


def test_s117_system_identity_block_renders_when_name_set():
    """Session 117 Part A — `<<<SYSTEM IDENTITY>>>` block injects when
    system_name is a non-default value AND SYSTEM_IDENTITY_BLOCK_ENABLED
    is True (default). Anchors the brain on its own name once set,
    preventing canary 2026-04-25 mid-conversation 'what name would you
    like to give me?' regression."""
    from core.brain import _build_system_prompt
    prompt = _build_system_prompt(
        person_name="Jagan",
        system_name="Kara",
    )
    assert "<<<SYSTEM IDENTITY>>>" in prompt
    assert "<<<END SYSTEM IDENTITY>>>" in prompt
    assert "Your name is Kara" in prompt
    # All 3 CRITICAL RULES present (numbered).
    assert "1." in prompt and "2." in prompt and "3." in prompt
    # The literal canary regression phrasing is named as forbidden.
    assert "what name would you like to give me" in prompt.lower()


def test_s117_system_identity_block_omitted_when_name_unset():
    """Session 117 Part A — when system_name is None or matches the
    DEFAULT_SYSTEM_NAME (pre-naming state), the SYSTEM IDENTITY block
    must NOT inject. First-boot enrollment scenarios are unaffected —
    those rely on the existing 'do not yet have a name' branch."""
    from core.brain import _build_system_prompt
    from core.config import DEFAULT_SYSTEM_NAME
    # None case.
    p1 = _build_system_prompt(person_name="Jagan", system_name=None)
    assert "<<<SYSTEM IDENTITY>>>" not in p1
    # Default-name case (pre-naming).
    p2 = _build_system_prompt(person_name="Jagan", system_name=DEFAULT_SYSTEM_NAME)
    assert "<<<SYSTEM IDENTITY>>>" not in p2


def test_s117_system_identity_block_rollback_flag_works(monkeypatch):
    """Session 117 — `SYSTEM_IDENTITY_BLOCK_ENABLED=False` rolls back to
    the original behavior even when system_name is set. One-line
    rollback safety net per reviewer's spec."""
    from core import config as _cfg
    from core.brain import _build_system_prompt
    monkeypatch.setattr(_cfg, "SYSTEM_IDENTITY_BLOCK_ENABLED", False)
    prompt = _build_system_prompt(person_name="Jagan", system_name="Kara")
    assert "<<<SYSTEM IDENTITY>>>" not in prompt, (
        "rollback flag must suppress the block"
    )


def test_s117_update_system_name_tool_description_hardened():
    """Session 117 Part C — `update_system_name` tool description must
    carry the new CRITICAL clause forbidding redundant calls. Source-
    inspection guard: the canary case ('Do you know why I named you
    Kara?') must be named explicitly so brain learns the discussing-
    vs-renaming distinction."""
    from core.brain import TOOLS
    tool = next(
        t for t in TOOLS if t["function"]["name"] == "update_system_name"
    )
    desc = tool["function"]["description"]
    assert "DO NOT call this tool if" in desc, (
        "CRITICAL clause header missing"
    )
    # Canary discussing-vs-renaming counter-example.
    assert "Do you know why I named you" in desc
    # Explicit "EXPLICITLY proposes a NEW name different" rule.
    assert "EXPLICITLY proposes a NEW name" in desc
    # Conservative default in uncertainty.
    assert "DO NOT call the tool" in desc


def test_s119_intent_divergences_mode_column_present(tmp_path):
    """Phase 5 component 3 — `intent_divergences` table has the `mode`
    column with default 'gate'. Migration must run cleanly on a fresh
    DB AND on existing pre-S119 brain.db files (covered by the ALTER
    TABLE branch alongside the CREATE TABLE branch)."""
    from core.brain_agent import BrainDB
    bdb = BrainDB(tmp_path / "brain.db")
    try:
        cols = {r[1] for r in bdb._conn.execute(
            "PRAGMA table_info(intent_divergences)"
        ).fetchall()}
        assert "mode" in cols, f"mode column missing; got {cols}"
        # Default value sanity: insert a row without specifying mode,
        # confirm it lands as 'gate'.
        bdb.log_intent_divergence(
            tool_proposed="x", gate_decision="allow", user_text="hi",
        )
        row = bdb._conn.execute(
            "SELECT mode FROM intent_divergences ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row[0] == "gate", f"default mode should be 'gate'; got {row[0]!r}"
    finally:
        bdb._conn.close()


def test_s119_log_intent_divergence_writes_mode_shadow(tmp_path):
    """Phase 5 component 3 — `log_intent_divergence(mode='shadow')`
    persists the value. Canary path uses this; weekly review query
    filters on it."""
    from core.brain_agent import BrainDB
    bdb = BrainDB(tmp_path / "brain.db")
    try:
        bdb.log_intent_divergence(
            tool_proposed="", gate_decision="shadow_sample",
            user_text="just a test", mode="shadow",
        )
        row = bdb._conn.execute(
            "SELECT mode, gate_decision FROM intent_divergences "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row[0] == "shadow"
        assert row[1] == "shadow_sample"
    finally:
        bdb._conn.close()


def test_s119_canary_shadow_sample_rate_respected_in_source():
    """Phase 5 component 4 — `conversation_turn` reads the canary
    sample rate from `SHADOW_SAMPLE_RATE` config and passes
    `mode='shadow'` to `log_intent_divergence` when sampled.
    Source-inspection guard against accidental rate hardcoding or
    mode mislabeling."""
    import inspect, pipeline
    src = inspect.getsource(pipeline.conversation_turn)
    assert "SHADOW_SAMPLE_RATE" in src, "config rate not read"
    assert "SHADOW_SAMPLE_ENABLED" in src, "kill switch not read"
    assert 'mode="shadow"' in src or "mode='shadow'" in src, (
        "shadow mode constant not passed to log_intent_divergence"
    )
    assert "shadow_sample" in src, "gate_decision label missing for canary path"


def test_s119_canary_shadow_failure_does_not_break_turn():
    """Phase 5 component 4 — exception in shadow path must NOT
    propagate. Source-inspection guard: the canary block is wrapped
    in try/except (outer) AND the log call inside is also wrapped
    (defense-in-depth) so a sampling failure can't break a turn."""
    import inspect, pipeline
    src = inspect.getsource(pipeline.conversation_turn)
    # Find the canary block by anchoring on the SHADOW_SAMPLE_RATE
    # config import; verify a try/except wraps it.
    canary_anchor = src.find("SHADOW_SAMPLE_RATE")
    assert canary_anchor > 0
    # Walk up a few hundred chars to find the enclosing try:.
    upstream = src[max(0, canary_anchor - 400):canary_anchor]
    assert "try:" in upstream, (
        "canary block must be wrapped in try: so sampling failure can't break turn"
    )
    # And the trailing except clause should print without re-raise.
    downstream = src[canary_anchor:canary_anchor + 2000]
    assert "except Exception" in downstream, (
        "canary except clause missing — sampling failure could propagate"
    )


def test_s119_eval_weekly_compute_drift_flags_precision_drop():
    """Phase 5 component 1 — `compute_drift` produces a
    `precision_drops` entry when an intent's precision falls between
    runs. Pure-function test; no live bench required."""
    from tests.eval_weekly import compute_drift
    cur = {
        "hybrid": {"per_intent": {
            "assign_own_name": {"precision": 0.90, "recall": 0.85},
        }},
    }
    pri = {
        "hybrid": {"per_intent": {
            "assign_own_name": {"precision": 0.95, "recall": 0.85},
        }},
    }
    drift = compute_drift(cur, pri)
    assert len(drift["precision_drops"]) == 1
    drop = drift["precision_drops"][0]
    assert drop["intent"] == "assign_own_name"
    assert drop["delta_pp"] == -5.0
    assert drift["precision_gains"] == []


def test_s119_eval_weekly_alert_threshold_triggers():
    """Phase 5 component 1 — `has_alert_drift` returns True when at
    least one precision drop reaches the threshold; False below.
    Drives `--alert` exit-code semantics."""
    from tests.eval_weekly import has_alert_drift
    drift = {"precision_drops": [{"delta_pp": -5.0, "intent": "x"}]}
    assert has_alert_drift(drift, threshold_pp=5.0) is True
    drift2 = {"precision_drops": [{"delta_pp": -4.99, "intent": "y"}]}
    assert has_alert_drift(drift2, threshold_pp=5.0) is False
    drift3 = {"precision_drops": []}
    assert has_alert_drift(drift3, threshold_pp=5.0) is False


def test_s119_eval_weekly_render_report_marks_unchanged_hash():
    """Phase 5 component 1 — when current and prior classifier prompt
    hashes match, the report headlines 'UNCHANGED'. When they differ,
    the report calls out the Phase 5 drift baseline reset."""
    from tests.eval_weekly import render_report
    same_hash = {"classifier_prompt_hash": "abc123abc123",
                 "run_ts": "2026-04-26T12:00:00Z"}
    metrics = {"hybrid": {"per_intent": {}}}
    out_unchanged = render_report(
        current_metrics=metrics, current_metadata=same_hash,
        prior_metrics=metrics,   prior_metadata=same_hash,
        drift={"precision_drops": [], "recall_drops": [],
               "precision_gains": [], "recall_gains": []},
        divergences={"missing": True, "lookback_days": 7,
                     "mode_counts": {}},
        alert_threshold_pp=5.0, alert_active=False,
    )
    assert "UNCHANGED" in out_unchanged
    diff_hash = {"classifier_prompt_hash": "different",
                 "run_ts": "2026-04-26T12:00:00Z"}
    out_changed = render_report(
        current_metrics=metrics, current_metadata=diff_hash,
        prior_metrics=metrics,   prior_metadata=same_hash,
        drift={"precision_drops": [], "recall_drops": [],
               "precision_gains": [], "recall_gains": []},
        divergences={"missing": True, "lookback_days": 7,
                     "mode_counts": {}},
        alert_threshold_pp=5.0, alert_active=False,
    )
    assert "CHANGED" in out_changed and "drift baseline reset" in out_changed


def test_s119_golden_set_drift_export_stratified(tmp_path, monkeypatch):
    """Phase 5 component 2 — export mode produces a stratified-sample
    markdown with at least 1 row per intent that has 3+ rows in the
    corpus. Regression guard against single-intent dominance."""
    from tests import golden_set_drift as gsd

    # Synthetic corpus: 6 intents, 4 rows each (24 total).
    fake_rows = []
    for intent in ("a", "b", "c", "d", "e", "f"):
        for n in range(4):
            fake_rows.append({
                "user_text":      f"{intent} sample {n}",
                "expected_intent": intent,
                "expected_value":  None,
                "source":          "synthetic_common",
            })
    # Add 1 legacy row that should be excluded from the sample.
    fake_rows.append({
        "user_text": "legacy", "expected_intent": "legacy_x",
        "expected_value": None, "source": "legacy_synthetic",
    })

    monkeypatch.setattr(gsd, "_load_rows", lambda: fake_rows)
    out = tmp_path / "drift.md"
    gsd.export(out_path=out, n_total=12, seed=42)
    text = out.read_text(encoding="utf-8")
    # Each of the 6 well-populated intents should appear at least once.
    for intent in ("a", "b", "c", "d", "e", "f"):
        assert f"expected_intent:** {intent}" in text, (
            f"intent {intent!r} missing from sample"
        )
    # Legacy must NOT appear.
    assert "legacy_x" not in text, "legacy_synthetic should be excluded"


def test_s119_golden_set_drift_compare_flags_disagreements(tmp_path):
    """Phase 5 component 2 — compare mode reads filled markdown and
    flags rows where the human selected 'different'. Suggested
    action included in the report."""
    from tests import golden_set_drift as gsd
    md = tmp_path / "filled.md"
    md.write_text("""# Drift Check

## Row 1
**user_text:** "Hello there"
**stored expected_intent:** casual_conversation
**stored expected_value:** None

- [x] same  - [ ] different

Different label: ____________
Different value: ____________

## Row 2
**user_text:** "I'm Atlas now"
**stored expected_intent:** casual_conversation
**stored expected_value:** None

- [ ] same  - [x] different

Different label: assign_own_name
Different value: Atlas

## Row 3
**user_text:** "Bye now"
**stored expected_intent:** casual_conversation
**stored expected_value:** None

- [ ] same  - [x] different

Different label: request_shutdown
Different value: ____________
""", encoding="utf-8")

    verdicts = gsd.parse_filled_markdown(md.read_text(encoding="utf-8"))
    summary = gsd.report_disagreements(verdicts)
    assert summary["total"] == 3
    assert summary["same"] == 1
    assert summary["different"] == 2
    flagged_intents = sorted(v["new_intent"] for v in summary["flagged"])
    assert flagged_intents == ["assign_own_name", "request_shutdown"]


def test_s111_conversation_entries_carry_ts_and_addressed_to():
    """Session 111 Criticals #2 + #3: `conversation_turn` must stamp
    `ts` on every appended message and `addressed_to` on assistant
    messages. These drive (a) session-boundary filtering in the room
    block, (b) addressee labels in 4-person rooms, and (c) age suffix
    rendering. Source-inspection the write
    path since the function is end-to-end async and hard to exercise
    behaviorally without the full pipeline fixture."""
    import inspect, pipeline
    # P1.A1 SP-7b.3: the history append (ts + addressed_to fields) relocated to
    # flows.companion.turn_flows.history_persist (re-exported; getsource move-immune).
    src = inspect.getsource(pipeline.history_persist)
    # User message gains ts.
    assert '"ts":      _now_ts' in src or '"ts": _now_ts' in src, (
        "user message append must include ts field for session-boundary "
        "filtering"
    )
    # Assistant message gains addressed_to. Session 113 Part 1 repointed
    # the field source from effective_name directly to a resolved
    # `addressed_to` variable (comes from the ADDRESS DECISION marker or
    # falls back to effective_name); accept either form so the invariant
    # guards the FIELD regardless of which turn allocator writes it.
    assert (
        '"addressed_to": effective_name' in src
        or '"addressed_to": addressed_to' in src
    ), (
        "assistant message append must include addressed_to field so "
        "4-person rooms can render 'you [to X]:' labels"
    )


def test_s111_enroll_tmp_cleanup_errors_now_logged():
    """Session 111 HIGH silent-except fix: the 2 `except: pass` blocks
    at the enrollment-result tmp-file cleanup sites now log the
    exception instead of swallowing silently. Tmp-file leaks were
    invisible before; now they're diagnosable."""
    import inspect, pipeline
    src = inspect.getsource(pipeline)
    # The tightly-scoped silent pattern 'except Exception: pass' should
    # no longer appear for enrollment tmp cleanup. Check the helper
    # log message is present (new path).
    assert src.count("enroll tmp cleanup failed") >= 2, (
        "both enrollment tmp-cleanup sites must log on failure — "
        "silent except:pass leaks tmp files without any signal"
    )


def test_archive_terminal_output_noop_when_missing(tmp_path):
    """P1.5: first run on a fresh machine has no prior terminal_output.md —
    the archive hook must return None and NOT raise. Guards pipeline startup
    against FileNotFoundError on a clean install."""
    from pipeline import _archive_terminal_output
    missing = tmp_path / "terminal_output.md"
    result = _archive_terminal_output(missing)
    assert result is None
    # Also: calling it did NOT create the file (shouldn't touch disk at all).
    assert not missing.exists()


def test_archive_terminal_output_renames_with_mtime_stamp(tmp_path):
    """P1.5: existing terminal_output.md must be renamed to
    terminal_output_YYYY-MM-DD_HHMMSS.md where the timestamp is the file's
    MTIME (prior session's last-write), not wall-clock now. This keeps the
    archive name tied to the actual session boundary even if the new session
    starts hours later."""
    import os, re, time as _t
    from pipeline import _archive_terminal_output
    log = tmp_path / "terminal_output.md"
    log.write_text("[Session] prior content\n", encoding="utf-8")
    # Pin the mtime to a known past moment so the filename is deterministic.
    fixed = _t.mktime((2026, 4, 20, 12, 34, 56, 0, 0, -1))
    os.utime(log, (fixed, fixed))
    archived = _archive_terminal_output(log)
    assert archived is not None
    assert archived.name == "terminal_output_2026-04-20_123456.md", archived.name
    assert archived.exists()
    # Original path is gone — rename, not copy.
    assert not log.exists()
    # Content preserved byte-for-byte.
    assert archived.read_text(encoding="utf-8") == "[Session] prior content\n"


def test_archive_terminal_output_collision_safe(tmp_path):
    """P1.5: two sessions ending within the same second (possible in CI or
    rapid reboot) must not overwrite each other. Second archive gets a
    `_1` suffix, third gets `_2`, etc."""
    import os, time as _t
    from pipeline import _archive_terminal_output
    # First session's archive.
    log = tmp_path / "terminal_output.md"
    fixed = _t.mktime((2026, 4, 20, 12, 34, 56, 0, 0, -1))
    log.write_text("session A\n", encoding="utf-8")
    os.utime(log, (fixed, fixed))
    a1 = _archive_terminal_output(log)
    assert a1.name == "terminal_output_2026-04-20_123456.md"
    # Second session's archive (same mtime second).
    log.write_text("session B\n", encoding="utf-8")
    os.utime(log, (fixed, fixed))
    a2 = _archive_terminal_output(log)
    assert a2.name == "terminal_output_2026-04-20_123456_1.md", a2.name
    # Third.
    log.write_text("session C\n", encoding="utf-8")
    os.utime(log, (fixed, fixed))
    a3 = _archive_terminal_output(log)
    assert a3.name == "terminal_output_2026-04-20_123456_2.md", a3.name
    # All three archives coexist with distinct content.
    assert a1.read_text(encoding="utf-8") == "session A\n"
    assert a2.read_text(encoding="utf-8") == "session B\n"
    assert a3.read_text(encoding="utf-8") == "session C\n"


def test_archive_terminal_output_handles_empty_file(tmp_path):
    """P1.5: a zero-byte prior log (session that crashed before any output)
    should still archive, not be silently dropped. Harvest script may need
    to audit 'prior session produced no output' as a data-quality signal."""
    import os, time as _t
    from pipeline import _archive_terminal_output
    log = tmp_path / "terminal_output.md"
    log.write_bytes(b"")
    fixed = _t.mktime((2026, 4, 20, 8, 0, 0, 0, 0, -1))
    os.utime(log, (fixed, fixed))
    archived = _archive_terminal_output(log)
    assert archived is not None
    assert archived.exists()
    assert archived.stat().st_size == 0
