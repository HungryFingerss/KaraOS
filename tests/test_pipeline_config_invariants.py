"""test_pipeline_config_invariants — config invariants tests (split from test_pipeline.py, P1.A1 SP-1).

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


def test_intent_labels_exhaustive():
    """P1.1: INTENT_LABELS must cover every case the brain can classify a
    turn as. Missing labels force the gate into 'unclear' fallback; extra
    labels bloat the prompt. Lock the set so additions are deliberate."""
    from core.config import INTENT_LABELS
    expected = {
        "assign_system_name", "assign_own_name",
        "deny_identity", "confirm_identity",
        "live_data_query", "general_knowledge_query",
        "opinion_query", "personal_statement",
        "request_shutdown", "question_about_shutdown",
        "casual_conversation", "unclear",
        # Phase 3B.2 addition — user-to-user address for multi-person rooms.
        "direct_address_to_person",
        # Spec-1 follow-up Item 7 (2026-04-28): user correcting the AI's
        # previous turn — drives LLM-free online learning in the graph
        # classifier (Spec 2 wires the outcome supervision).
        "correction_to_previous_response",
        # Spec-1 follow-up (2026-04-28): `topical_participant_response` was
        # removed — Session 119 rollback orphan; prompt no longer emits it
        # and no production gate routes on it.
    }
    assert INTENT_LABELS == expected, (
        f"INTENT_LABELS changed unexpectedly. Got {sorted(INTENT_LABELS)}, "
        f"expected {sorted(expected)}"
    )


def test_tool_intent_map_every_value_points_to_valid_label():
    """P1.1 invariant: every tool's required intent MUST be in INTENT_LABELS.
    A typo here silently fails the gate at runtime; this catches it at CI."""
    from core.config import INTENT_LABELS, TOOL_INTENT_MAP
    for tool_name, (required_intent, arg_key) in TOOL_INTENT_MAP.items():
        assert required_intent in INTENT_LABELS, (
            f"TOOL_INTENT_MAP[{tool_name!r}] requires intent "
            f"{required_intent!r} which is NOT in INTENT_LABELS"
        )
        # arg_key is either None (denial-style) or a non-empty string.
        assert arg_key is None or (isinstance(arg_key, str) and arg_key), (
            f"TOOL_INTENT_MAP[{tool_name!r}] arg_key must be None or non-empty str"
        )


@pytest.mark.privacy_critical
def test_privacy_levels_exhaustive_and_frozen():
    """P3.21/3A.1: PRIVACY_LEVELS is the exhaustive, locked tier set. A new
    tier ('secret'/'room_private'/etc.) requires a deliberate code change
    rather than silently accepting unknown levels at runtime — fail-closed
    classifier logic depends on the level set being closed."""
    from core.config import PRIVACY_LEVELS
    assert PRIVACY_LEVELS == frozenset({"public", "personal", "household", "system_only"})
    assert isinstance(PRIVACY_LEVELS, frozenset)


@pytest.mark.privacy_critical
def test_privacy_default_is_personal_fail_closed():
    """P3.21/3A.1: novel attributes without explicit classification default to
    'personal' — the most restrictive owner-visible tier. Fail-closed policy:
    when in doubt, don't leak. Public/household exposure must be explicit."""
    from core.config import PRIVACY_LEVEL_DEFAULT, PRIVACY_LEVELS
    assert PRIVACY_LEVEL_DEFAULT == "personal"
    assert PRIVACY_LEVEL_DEFAULT in PRIVACY_LEVELS


@pytest.mark.privacy_critical
def test_privacy_static_map_values_valid():
    """P3.21/3A.1: every value in the static fast-path map MUST be a valid
    PRIVACY_LEVEL, otherwise the retrieval site would see a bogus level and
    either throw or (worse) silently mis-filter. Also pin the high-stakes
    anchors: health/confided→personal, visited/discussed→household."""
    from core.config import PRIVACY_LEVEL_STATIC_MAP, PRIVACY_LEVELS
    invalid = {k: v for k, v in PRIVACY_LEVEL_STATIC_MAP.items() if v not in PRIVACY_LEVELS}
    assert not invalid, f"Invalid privacy levels in static map: {invalid}"
    assert PRIVACY_LEVEL_STATIC_MAP.get("confided_concern") == "personal"
    assert PRIVACY_LEVEL_STATIC_MAP.get("health_condition") == "personal"
    assert PRIVACY_LEVEL_STATIC_MAP.get("visited_household") == "household"
    assert PRIVACY_LEVEL_STATIC_MAP.get("discussed_topic") == "household"


def test_tool_intent_map_covers_all_gated_mutation_tools():
    """P1.1 (Session 79 scope-shrink): every MUTATION tool (rename / deny /
    shutdown) that had a user-text gate in Sessions 70-74 must have an
    intent map entry, otherwise the structured path can't replace the
    regex gate. Session 79 removed `search_web` — it's gated by
    `_should_search_web` instead (its tool_call is consumed inline in
    ask_stream, never reaching the classifier, and its extracted_value is
    a semantic transformation not a literal substring of user_text).
    search_web may re-join the map in Phase 1.5 after the mutation
    classifier stabilizes."""
    from core.config import TOOL_INTENT_MAP
    expected_tools = {
        "update_system_name",
        "update_person_name",
        "report_identity_mismatch",
        "shutdown",
    }
    assert expected_tools.issubset(set(TOOL_INTENT_MAP.keys())), (
        f"missing tools in TOOL_INTENT_MAP: {expected_tools - set(TOOL_INTENT_MAP.keys())}"
    )
    # Invariant the other direction: search_web must NOT be in the map
    # (until Phase 1.5 re-evaluation). Guards against an accidental add-back
    # that would resurrect the dead-classifier-call problem.
    assert "search_web" not in TOOL_INTENT_MAP, (
        "search_web must remain OUT of TOOL_INTENT_MAP until Phase 1.5 — "
        "adding it back would wire the classifier to fire on search turns "
        "where the tool_call never bubbles to conversation_turn, producing "
        "zero [Intent] log lines (the Session 79 verification-gap symptom)"
    )


def test_intent_confidence_thresholds_reasonable():
    """P1.1: shutdown threshold must be strictly higher than general floor
    (larger blast radius justifies stricter gate). Guard against someone
    accidentally equalizing them."""
    from core.config import INTENT_CONFIDENCE_MIN, INTENT_SHUTDOWN_CONF_MIN
    assert 0.50 <= INTENT_CONFIDENCE_MIN <= 0.90
    assert INTENT_SHUTDOWN_CONF_MIN > INTENT_CONFIDENCE_MIN, (
        "shutdown floor must be strictly higher than general — "
        "bigger blast radius, stricter gate"
    )


def test_intent_fallback_defaults_to_safe_regex_path():
    """P1.1 safety: INTENT_FALLBACK_TO_REGEX must default to True. Only after
    P1.17 (shadow-mode divergence ≤ 5% + golden-set precision ≥ 0.95) should
    it flip to False. A premature flip leaves the system gateless."""
    from core.config import INTENT_FALLBACK_TO_REGEX
    assert INTENT_FALLBACK_TO_REGEX is True, (
        "shadow-mode safety: legacy regex gate must remain authoritative "
        "until structured intent shadow data proves reliable"
    )


def test_is_disputed_by_pid_lookup():
    """Bug D4: helper accepts a pid, looks up _session_store, returns True
    iff person_type == 'disputed'. Fail-closed on unknown pids (False)."""
    import asyncio
    import time
    import pipeline

    async def _setup():
        now = time.time()
        await pipeline._session_store.open_session(
            "p1", "p1", "disputed", "face", now=now
        )
        await pipeline._session_store.open_session(
            "p2", "p2", "known", "face", now=now
        )

    asyncio.run(_setup())

    assert pipeline._is_disputed("p1") is True
    assert pipeline._is_disputed("p2") is False
    assert pipeline._is_disputed("unknown_pid") is False
    assert pipeline._is_disputed(None) is False
    assert pipeline._is_disputed("") is False


def test_is_disputed_by_session_dict():
    """Bug D4: helper also accepts a pre-fetched session dict — saves a
    lookup when the caller already has the session in hand. Same predicate."""
    import pipeline
    assert pipeline._is_disputed({"person_type": "disputed"}) is True
    assert pipeline._is_disputed({"person_type": "best_friend"}) is False
    assert pipeline._is_disputed({}) is False


def test_no_raw_disputed_string_comparisons_outside_helper():
    """Bug D4 GREP INVARIANT: every dispute check in pipeline.py must route
    through ``_is_disputed()``. Scans the source for raw ``== "disputed"``
    AND ``!= "disputed"`` comparisons outside the helper definition itself.
    Catches future drift at CI time — the 'distributed policy = missing
    policy' antipattern.

    Session 73 post-review Critical #1: the original invariant only caught
    `==`, which let `_kairos_tick`'s `!= "disputed"` slip through. Now both
    polarities are covered so the negation form can't become a new escape
    hatch for the single-source-of-truth.

    A single new dispute check with raw-string comparison silently bypasses
    the helper. This test fails loudly when that happens."""
    from pathlib import Path
    src = Path("pipeline.py").read_text(encoding="utf-8")
    lines = src.split("\n")
    raw_checks = []
    for idx, ln in enumerate(lines, start=1):
        # Skip the helper definition itself (lines that define _is_disputed).
        if "pid_or_session.get" in ln or '_active_sessions.get(pid_or_session' in ln:
            continue
        # Skip the P0.7.3+ snapshot branch inside _is_disputed().
        if "_disp_snap" in ln:
            continue
        # Skip comments that reference "disputed" as literal text.
        _stripped = ln.strip()
        if _stripped.startswith("#"):
            continue
        # Flag `==` and `!=` raw comparisons in executable positions.
        if any(pat in ln for pat in (
            '== "disputed"',
            "== 'disputed'",
            '!= "disputed"',
            "!= 'disputed'",
        )):
            raw_checks.append(f"pipeline.py:{idx}: {_stripped[:100]}")
    assert not raw_checks, (
        "Raw `== \"disputed\"` / `!= \"disputed\"` comparisons bypass the "
        f"single-source-of-truth _is_disputed helper:\n  " + "\n  ".join(raw_checks)
    )


def test_recognition_threshold_raised_to_stable_region():
    """#5: RECOGNITION_THRESHOLD must be ≥ 0.25 (AdaFace IR101 stable EER region)."""
    from core.config import RECOGNITION_THRESHOLD
    assert RECOGNITION_THRESHOLD >= 0.25, \
        f"RECOGNITION_THRESHOLD={RECOGNITION_THRESHOLD} too low — strangers will false-match"


def test_sort_max_age_raised():
    """#8: SORT_MAX_AGE must be ≥ 30 to cover 1s occlusions at 30fps."""
    from core.config import SORT_MAX_AGE
    assert SORT_MAX_AGE >= 30, f"SORT_MAX_AGE={SORT_MAX_AGE} — too short, faces re-tracked on brief occlusion"


def test_is_unknown_flag_removed_from_conversation_turn():
    """The is_unknown variable and its branch are deleted from conversation_turn."""
    import ast, pathlib
    src = pathlib.Path("pipeline.py").read_text()
    assert "is_unknown" not in src, "is_unknown flag must be removed"
    assert '"unknown" in _active_sessions' not in src, "'unknown' in _active_sessions must be removed"


def test_conversation_memory_table_not_created(tmp_path, capsys):
    """FaceDB no longer creates a conversation_memory table."""
    from core.db import FaceDB
    db = FaceDB(db_path=tmp_path / "faces.db", faiss_path=tmp_path / "faiss.index")
    tables = {r[0] for r in db._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    assert "conversation_memory" not in tables
    db._conn.close()


def test_memory_paths_removed_from_config():
    """MEMORY_DB_PATH and MEMORY_VECTORS_PATH no longer exist in config."""
    import core.config as cfg
    assert not hasattr(cfg, "MEMORY_DB_PATH"), "MEMORY_DB_PATH must be removed from config"
    assert not hasattr(cfg, "MEMORY_VECTORS_PATH"), "MEMORY_VECTORS_PATH must be removed from config"


def test_recognition_soft_threshold_removed_from_config():
    import core.config as cfg
    assert not hasattr(cfg, "RECOGNITION_SOFT_THRESHOLD"), \
        "RECOGNITION_SOFT_THRESHOLD must be removed — it is dead config"


def test_brain_orchestrator_mark_clear_disputed_registry():
    """mark_disputed adds to the set; clear_disputed removes."""
    from core.brain_agent import BrainOrchestrator
    orch = BrainOrchestrator.__new__(BrainOrchestrator)
    orch._disputed_persons = set()
    orch.mark_disputed("p1")
    assert "p1" in orch._disputed_persons
    orch.clear_disputed("p1")
    assert "p1" not in orch._disputed_persons


def test_tool_allowed_returns_true_for_caller_in_privilege_set():
    """_tool_allowed returns True when caller_type is listed for the tool."""
    from pipeline import _tool_allowed
    assert _tool_allowed("shutdown", "best_friend") is True
    assert _tool_allowed("search_web", "stranger") is True


def test_tool_allowed_returns_false_for_caller_not_in_privilege_set():
    """_tool_allowed returns False when caller_type is NOT in the tool's set."""
    from pipeline import _tool_allowed
    assert _tool_allowed("shutdown", "known") is False
    assert _tool_allowed("update_system_name", "stranger") is False


def test_tool_allowed_fails_closed_for_unregistered_tool():
    """Adjustment 4: a tool NOT in TOOL_PRIVILEGES must be BLOCKED, not unrestricted.
    Protects against future additions that forget to add a privilege row."""
    from pipeline import _tool_allowed
    assert _tool_allowed("some_unregistered_tool_xyz", "best_friend") is False


def test_tool_privileges_covers_every_brain_tool():
    """Startup-assertion invariant: every tool in brain.TOOLS must have a row
    in TOOL_PRIVILEGES. Same check that runs at pipeline.run() entry — here as a
    pytest-reachable form so CI catches it even if the app isn't launched."""
    from core.brain import TOOLS
    from core.config import TOOL_PRIVILEGES
    tool_names = {t["function"]["name"] for t in TOOLS}
    missing = tool_names - set(TOOL_PRIVILEGES)
    assert not missing, f"TOOL_PRIVILEGES missing entries for: {sorted(missing)}"


def test_set_language_removed_from_brain_tools():
    """English-only: set_language must NOT appear in brain.TOOLS (exposing a
    tool that's silently blocked is the anti-pattern we're eliminating)."""
    from core.brain import TOOLS
    assert not any(t["function"]["name"] == "set_language" for t in TOOLS)
