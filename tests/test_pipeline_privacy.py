"""test_pipeline_privacy — privacy tests (split from test_pipeline.py, P1.A1 SP-1).

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
from tests._pipeline_helpers import (
    _s3b1_sess,
)


@pytest.fixture
def _clear_privacy_cache():
    """Reset the module-level privacy classifier cache around each test —
    classifier state is process-lifetime, so tests must isolate."""
    from core import brain_agent
    brain_agent._privacy_classifier_cache.clear()
    yield
    brain_agent._privacy_classifier_cache.clear()


async def test_classify_privacy_static_map_hit_never_calls_llm(_clear_privacy_cache, monkeypatch):
    """3A.2 path #1: 'name' is pre-classified in the static map → should
    return 'public' without the cache or LLM being consulted at all.
    Monkeypatch _call_llm_chat to blow up on any call so the assertion is
    strict: the classifier MUST short-circuit on static-map hits."""
    from core import brain_agent

    async def _boom(*_a, **_kw):
        raise AssertionError("LLM must not be called on static-map hit")

    monkeypatch.setattr(brain_agent, "_call_llm_chat", _boom)
    level = await brain_agent._classify_privacy_level(
        "Lexi", "name", "Lexi", http=object()
    )
    assert level == "public"
    assert "name" not in brain_agent._privacy_classifier_cache


async def test_classify_privacy_cache_hit_never_calls_llm(_clear_privacy_cache, monkeypatch):
    """3A.2 path #2: attribute not in static map but cached from a prior LLM
    classification → returns cached tier, does NOT re-invoke the LLM."""
    from core import brain_agent

    brain_agent._privacy_classifier_cache["novel_attr"] = "household"

    async def _boom(*_a, **_kw):
        raise AssertionError("LLM must not be called on cache hit")

    monkeypatch.setattr(brain_agent, "_call_llm_chat", _boom)
    level = await brain_agent._classify_privacy_level(
        "Lexi", "novel_attr", "something", http=object()
    )
    assert level == "household"


async def test_classify_privacy_llm_success_caches_result(_clear_privacy_cache, monkeypatch):
    """3A.2 path #3: novel attribute, no cache → LLM returns valid JSON with
    a valid tier → classifier returns that tier AND writes it to the cache
    so the next call with the same attribute short-circuits."""
    from core import brain_agent

    call_count = {"n": 0}

    async def _fake_llm(*_a, **_kw):
        call_count["n"] += 1
        return '{"level": "personal", "reasoning": "sensitive"}'

    monkeypatch.setattr(brain_agent, "_call_llm_chat", _fake_llm)
    level = await brain_agent._classify_privacy_level(
        "Lexi", "secret_hobby", "birdwatching", http=object()
    )
    assert level == "personal"
    assert brain_agent._privacy_classifier_cache.get("secret_hobby") == "personal"

    # Second call with same attribute → cache hit, LLM not invoked again.
    level2 = await brain_agent._classify_privacy_level(
        "Jagan", "secret_hobby", "fencing", http=object()
    )
    assert level2 == "personal"
    assert call_count["n"] == 1


async def test_classify_privacy_llm_timeout_fails_closed_no_cache(_clear_privacy_cache, monkeypatch):
    """3A.2 path #4: `_call_llm_chat` returns None on timeout/transient
    failures → classifier returns PRIVACY_LEVEL_DEFAULT ('personal') AND
    does NOT write to cache (a transient blip must be retried next time)."""
    from core import brain_agent

    async def _timeout_llm(*_a, **_kw):
        return None  # _call_llm_chat swallows transient errors → None

    monkeypatch.setattr(brain_agent, "_call_llm_chat", _timeout_llm)
    level = await brain_agent._classify_privacy_level(
        "Lexi", "unseen_attr", "x", http=object()
    )
    assert level == "personal"
    assert "unseen_attr" not in brain_agent._privacy_classifier_cache


async def test_classify_privacy_llm_invalid_level_fails_closed_no_cache(
    _clear_privacy_cache, monkeypatch
):
    """3A.2 path #5: LLM returns well-formed JSON but with a bogus tier
    ('secret') outside PRIVACY_LEVELS → fail-closed to 'personal' AND do
    NOT cache. An invalid classification is worse than none — caching it
    would permanently wedge the attribute at the wrong tier."""
    from core import brain_agent

    async def _bogus_llm(*_a, **_kw):
        return '{"level": "secret", "reasoning": "classifier went rogue"}'

    monkeypatch.setattr(brain_agent, "_call_llm_chat", _bogus_llm)
    level = await brain_agent._classify_privacy_level(
        "Lexi", "forbidden_knowledge", "x", http=object()
    )
    assert level == "personal"
    assert "forbidden_knowledge" not in brain_agent._privacy_classifier_cache


async def test_classify_privacy_llm_malformed_json_fails_closed_no_cache(
    _clear_privacy_cache, monkeypatch
):
    """3A.2 path #6: LLM returns non-JSON prose (model forgot the contract)
    → `_parse_json`'s brace-salvage can't recover → fail-closed to
    'personal' AND do NOT cache. Same logic as invalid tier: caching a
    parse failure would silently pin the attribute forever."""
    from core import brain_agent

    async def _prose_llm(*_a, **_kw):
        return "I think this is probably personal but I'm not sure"

    monkeypatch.setattr(brain_agent, "_call_llm_chat", _prose_llm)
    level = await brain_agent._classify_privacy_level(
        "Lexi", "mystery_attr", "x", http=object()
    )
    assert level == "personal"
    assert "mystery_attr" not in brain_agent._privacy_classifier_cache


@pytest.mark.privacy_critical
def test_visibility_clause_best_friend_excludes_only_system_only():
    """3A.3 / 3A.4.6: revised owner-access model — best_friend (household
    owner) has unconditional access to every non-mechanical fact. Single
    exclusion predicate (`privacy_level != 'system_only'`) with zero
    params. No per-tier enumeration needed because owner sees everything
    else. The user's clarification: "best friend should have all the
    access... bestfriend have the access for everything"."""
    from core.brain_agent import _visibility_clause
    clause, params = _visibility_clause("jagan_abc", "jagan_abc")
    assert "privacy_level != 'system_only'" in clause
    # No positive tier enumeration — owner sees everything, no need to list.
    assert "privacy_level = 'public'" not in clause
    assert "privacy_level = 'personal'" not in clause
    assert "privacy_level = 'household'" not in clause
    assert params == []


@pytest.mark.privacy_critical
def test_visibility_clause_non_best_friend_sees_public_own_personal_not_household():
    """3A.3: non-best-friend speakers (strangers, visitors) get public +
    their own personal ONLY. Household tier is the critical exclusion —
    without this, Lexi could see visited_household/discussed_topic which
    leak Jagan's social graph. The whole point of 3A.1's tier choices."""
    from core.brain_agent import _visibility_clause
    clause, params = _visibility_clause("lexi_xyz", "jagan_abc")
    assert "privacy_level = 'public'" in clause
    assert "privacy_level = 'personal' AND person_id = ?" in clause
    assert "privacy_level = 'household'" not in clause  # critical
    assert "system_only" not in clause
    assert params == ["lexi_xyz"]


@pytest.mark.privacy_critical
def test_visibility_clause_no_best_friend_id_acts_as_non_privileged():
    """3A.3: pre-first-boot / best_friend not yet set (None) means nobody
    has owner privilege. Household tier excluded universally. Matches the
    `if best_friend_id and requester_pid == best_friend_id:` guard."""
    from core.brain_agent import _visibility_clause
    clause, _ = _visibility_clause("jagan_abc", None)
    assert "privacy_level = 'household'" not in clause


@pytest.mark.privacy_critical
def test_visibility_clause_never_permits_system_only():
    """3A.3 / 3A.4.6: system_only is the single 'never disclose' tier.
    No (requester, best_friend) combination should yield a clause that
    permits a system_only row through. Under the simplified owner model,
    best_friend's clause explicitly excludes it (`!= 'system_only'`);
    non-best-friend enumerates public + own-personal, with system_only
    absent from the allowed list. Either way the invariant holds: no
    clause contains `privacy_level = 'system_only'` as a MATCH."""
    from core.brain_agent import _visibility_clause
    for (req, bf) in [("jagan_abc", "jagan_abc"), ("other", "jagan_abc"), ("jagan_abc", None)]:
        clause, _ = _visibility_clause(req, bf)
        # No positive match clause for system_only (the dangerous form).
        assert "privacy_level = 'system_only'" not in clause
        # When system_only appears in the clause at all, it must be an
        # exclusion (best_friend branch) — not an inclusion.
        if "'system_only'" in clause:
            assert "!= 'system_only'" in clause


@pytest.mark.privacy_critical
def test_visibility_clause_composes_cleanly_with_and():
    """3A.3: the returned clause must be wrapped so caller composition with
    outer AND doesn't accidentally mix OR precedence. Per-tier predicates
    are parenthesized and OR-joined; the caller wraps THAT in its own
    outer parens when composing — resulting in double parens in the final
    SQL. Checking for `((` in the composed form proves the shape."""
    from core.brain_agent import _visibility_clause
    clause, _ = _visibility_clause("jagan_abc", "jagan_abc")
    assert clause.startswith("(")
    assert clause.endswith(")")
    composed = f"SELECT 1 FROM knowledge WHERE entity = ? AND ({clause})"
    assert "WHERE entity = ? AND ((" in composed


@pytest.mark.privacy_critical
def test_visibility_clause_params_align_with_placeholders():
    """3A.3: SQL driver will throw if ? count != params length. Verify
    across all 3 distinct shapes (best_friend, non-best-friend, no-bf).
    Without this test a future refactor that adds a param but forgets a
    placeholder (or vice versa) would slip through."""
    from core.brain_agent import _visibility_clause
    for (req, bf) in [("jagan", "jagan"), ("lexi", "jagan"), ("x", None)]:
        clause, params = _visibility_clause(req, bf)
        assert clause.count("?") == len(params)


def test_distinct_schema_families_detects_cross_family():
    """'former_name' and 'former_presence' belong to different families — no merge."""
    from core.brain_agent import _distinct_schema_families
    assert _distinct_schema_families("former_name", "former_presence") is True
    assert _distinct_schema_families("current_name", "arrived_at") is True


def test_distinct_schema_families_allows_same_family():
    """Attributes in the same family (both name-like) return False so they can still merge."""
    from core.brain_agent import _distinct_schema_families
    assert _distinct_schema_families("former_name", "current_name") is False


def test_schema_norm_threshold_raised_to_097():
    """SCHEMA_NORM_THRESHOLD must be at least 0.97 — 0.95 was bridging semantically distinct attrs."""
    from core.config import SCHEMA_NORM_THRESHOLD
    assert SCHEMA_NORM_THRESHOLD >= 0.97


@pytest.mark.parametrize(
    "n_disputed,n_total,case_name",
    [
        (0, 3, "no_disputed"),
        (1, 3, "one_disputed"),
        (2, 3, "n_disputed"),
        (3, 3, "all_disputed"),
    ],
    ids=["0_disputed", "1_disputed", "N_disputed", "all_disputed"],
)
@pytest.mark.privacy_critical
def test_p0_s7_dc_build_room_block_section1_renders_disputed_identity(
    n_disputed, n_total, case_name,
):
    """P0.S7.D-C Plan v1 §6 Phase 1 test 3 + LOW#2 parametrize expansion.

    Section 1 of `_build_room_block` MUST render `(disputed identity)`
    for any active participant whose session is in disputed state —
    mirrors the SCENE block (pipeline.py:1800) and legacy block
    (pipeline.py:1234) pattern.

    Without this, flag-gating the legacy block drops the "Lexi
    (disputed identity)" signal in multi-person scenes where the
    disputed participant isn't the current speaker (the
    <<<IDENTITY DISPUTED>>> block in brain.py only fires for the
    speaker — see Plan v1 §3.1).

    Parametrized over 4 cases per LOW#2: 0 / 1 / N / all participants
    disputed. The 0-case is a negative control — a session-store with
    no disputed snapshots must NOT emit any "disputed identity" labels."""
    import pipeline as _pl
    import time as _t
    _pl._session_store._sessions.clear()
    now = _t.time()
    _pids = [f"p{i+1}" for i in range(n_total)]
    _names = [f"P{i+1}" for i in range(n_total)]
    sessions = tuple(
        _s3b1_sess(pid, name, ptype="known")
        for pid, name in zip(_pids, _names)
    )
    # Seed _session_store so `_is_disputed(pid)` returns True for the
    # first N participants. The other participants stay non-disputed.
    for i, pid in enumerate(_pids):
        asyncio.run(_pl._session_store.open_session(
            pid, _names[i], "known", "face", now=now
        ))
        if i < n_disputed:
            asyncio.run(_pl._session_store.transition_to_disputed(
                pid, None, "test dispute", now=now,
            ))
    convo = {pid: [] for pid in _pids}
    out = _pl._build_room_block(
        active_sessions=sessions,
        conversation=convo,
        emotion_agents={},
        room_start_ts=now - 60,
        turn_cap=10,
    )
    assert out is not None, f"multi-person room must render block; case={case_name}"
    # Each disputed participant gets exactly one `(disputed identity)`
    # label in Section 1.
    assert out.count("(disputed identity)") == n_disputed, (
        f"case={case_name}: expected {n_disputed} disputed-identity labels, "
        f"got {out.count('(disputed identity)')}. Block:\n{out}"
    )
    # Each non-disputed participant gets `(known)` in Section 1.
    assert out.count("(known)") == n_total - n_disputed, (
        f"case={case_name}: expected {n_total - n_disputed} '(known)' "
        f"labels; got {out.count('(known)')}. Block:\n{out}"
    )
    # Cleanup — drain the session_store so subsequent parametrize cases
    # start clean.
    _pl._session_store._sessions.clear()


@pytest.mark.privacy_critical
def test_p0_s7_dc_build_room_block_section1_renders_best_friend_role():
    """P0.S7.D-C Plan v1 §6 Phase 1 test 4 — Section 1 MUST render
    `(best_friend)` for the participant whose pid matches the passed
    `best_friend_id` kwarg.

    Companion to the disputed-identity test: the full role hierarchy
    mirrors SCENE + legacy blocks (disputed → best_friend → person_type).
    Without the best_friend branch, a best_friend whose session
    `person_type` somehow says "stranger" or "known" (rename-path edge
    case) would render with the raw type instead of the privileged
    role, breaking parity with the legacy block.

    Non-disputed best_friend takes the best_friend label; disputed
    best_friend takes "disputed identity" (verified in test 3 case
    all_disputed via the strictly-higher-precedence dispute check)."""
    import pipeline as _pl
    import time as _t
    _pl._session_store._sessions.clear()
    now = _t.time()
    # Jagan as best_friend — session person_type is "known" so the
    # default path (without the elif branch) would mislabel. The
    # elif `pid == best_friend_id` branch is the one being exercised.
    sessions = (
        _s3b1_sess("jagan_bf", "Jagan", ptype="known"),
        _s3b1_sess("lexi_001", "Lexi",  ptype="stranger"),
    )
    convo = {"jagan_bf": [], "lexi_001": []}
    # Seed sessions so _is_disputed returns False for both.
    asyncio.run(_pl._session_store.open_session(
        "jagan_bf", "Jagan", "known", "face", now=now
    ))
    asyncio.run(_pl._session_store.open_session(
        "lexi_001", "Lexi", "stranger", "face", now=now
    ))
    out = _pl._build_room_block(
        active_sessions=sessions,
        conversation=convo,
        emotion_agents={},
        room_start_ts=now - 60,
        turn_cap=10,
        best_friend_id="jagan_bf",
    )
    assert out is not None, "multi-person room must render block"
    assert "Jagan (best_friend)" in out, (
        f"Jagan must render as (best_friend) when pid matches "
        f"best_friend_id. Block:\n{out}"
    )
    # Negative — Lexi (stranger, not best_friend_id) keeps her raw type.
    assert "Lexi (stranger)" in out, (
        f"Lexi must keep her raw person_type label (stranger). Block:\n{out}"
    )
    _pl._session_store._sessions.clear()


@pytest.mark.privacy_critical
def test_p0_s7_dc_brain_context_summary_room_field_repointed_to_active_sessions():
    """P0.S7.D-C Plan v1 §6 Phase 2 test 5 — `[Brain] Context:` log line's
    `room=yes/no` field MUST be derived from `len(_all_snaps_ct) >= 2`
    (i.e. multi-person session active), NOT from `room_context`
    truthiness.

    Under the Stage 1 flag-gate, `room_context` is always None →
    legacy formula would always print `room=no` even in multi-person
    scenes. The repoint preserves the field's semantic ("multi-person
    context in scope this turn") despite the implementation source
    flipping from "legacy block rendered" → "multi-person session
    exists." Grep tooling that reads this field for canary
    multi-person assertions stays unbroken.

    Source-inspection on conversation_turn — asserts the new
    `_multi_person = len(_all_snaps_ct) >= 2` derivation precedes the
    `[Brain] Context:` print AND the print uses `_multi_person` not
    `room_context` for the `room=` field.
    """
    import inspect, pipeline
    src = inspect.getsource(pipeline.conversation_turn)
    assert "_multi_person = len(_all_snaps_ct) >= 2" in src, (
        "the [Brain] Context: log line must derive room=yes/no from "
        "_multi_person = len(_all_snaps_ct) >= 2 (Plan v1 §5.2)"
    )
    # The print statement must use _multi_person for room=, NOT room_context.
    # Find the [Brain] Context: print line and assert its room= clause.
    _print_idx = src.find("[Brain] Context: history=")
    assert _print_idx != -1, "[Brain] Context: log line missing"
    _print_line_end = src.find("\n", _print_idx)
    _print_line = src[_print_idx:_print_line_end]
    assert "'yes' if _multi_person else 'no'" in _print_line, (
        "room= clause must read _multi_person; got line:\n"
        f"  {_print_line}"
    )
    # Negative — the room= clause MUST NOT reference room_context (legacy).
    # The room_context local can still exist (Stage 1 keeps the legacy
    # callable under the flag); the assertion is that the LOG line no
    # longer uses it for the room field.
    assert "'yes' if room_context else 'no'" not in _print_line, (
        "room= clause must NOT reference room_context (legacy source);"
        f" got line:\n  {_print_line}"
    )
