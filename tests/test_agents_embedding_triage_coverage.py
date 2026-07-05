"""100% coverage for the EmbeddingAgent cache-eviction path + TriageAgent's
defensive non-user role branch. Part of the coverage-to-100 campaign."""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from core.brain_agent.agents.embedding import EmbeddingAgent
from core.brain_agent.agents.triage import TriageAgent


def test_evict_cache_pops_oldest_over_cap():
    a = EmbeddingAgent(http=object())  # http unused by _evict_cache
    a._MAX_CACHE = 2
    a._cache = {"a": [1.0], "b": [2.0], "c": [3.0]}  # 3 > 2 -> evict
    a._evict_cache()
    assert len(a._cache) == 2 and "a" not in a._cache  # oldest popped


def test_evict_cache_noop_when_under_cap():
    a = EmbeddingAgent(http=object())
    a._cache = {"a": [1.0]}
    a._evict_cache()
    assert a._cache == {"a": [1.0]}


def test_triage_non_user_non_assistant_role_skipped():
    ok, reason = TriageAgent().should_process(role="system", content="anything")
    assert ok is False and reason == "assistant turn"


def test_triage_user_meaningful_content_passes():
    ok, reason = TriageAgent().should_process(
        role="user", content="I really enjoy playing cricket on weekends"
    )
    assert ok is True and reason == "ok"
