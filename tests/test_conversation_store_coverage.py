"""Covers ConversationStore's clear_all_* mutators + the timestamp-prune helper
(P0.6.3). Part of the coverage-to-100 campaign (see COVERAGE.md)."""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from core.conversation_store import ConversationStore, _prune_timestamp_dict


def test_prune_timestamp_dict_deletes_oldest_over_cap():
    d = {"a": 1.0, "b": 2.0, "c": 3.0}
    _prune_timestamp_dict(d, max_size=2)  # over cap -> del min-by-value (oldest ts)
    assert len(d) == 2 and "a" not in d


def test_prune_timestamp_dict_noop_under_cap():
    d = {"a": 1.0}
    _prune_timestamp_dict(d, max_size=5)
    assert d == {"a": 1.0}


async def test_clear_all_history():
    s = ConversationStore()
    await s.set_history("p1", [{"role": "user", "content": "hi"}])
    await s.clear_all_history()
    assert s.peek_history("p1") == [] and s.peek_pids() == []


async def test_clear_all_greeted():
    s = ConversationStore()
    await s.touch_greeted("p1", 10.0)
    await s.clear_all_greeted()
    assert s.peek_last_greeted("p1") == 0.0


async def test_clear_all_self_update():
    s = ConversationStore()
    await s.touch_self_update("p1", 10.0)
    await s.clear_all_self_update()
    assert s.peek_last_self_update("p1") == 0.0


async def test_clear_all_compact():
    s = ConversationStore()
    await s.add_compact("p1")
    await s.clear_all_compact()
    assert s.is_compacting("p1") is False


async def test_clear_all_resets_every_structure():
    s = ConversationStore()
    await s.set_history("p1", [{"role": "user", "content": "hi"}])
    await s.touch_greeted("p1", 1.0)
    await s.touch_self_update("p1", 2.0)
    await s.add_compact("p1")
    await s.clear_all()
    assert s.peek_pids() == []
    assert s.peek_last_greeted("p1") == 0.0
    assert s.peek_last_self_update("p1") == 0.0
    assert s.is_compacting("p1") is False
