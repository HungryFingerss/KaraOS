"""
Behavioral unit tests for SessionStore — P0.7.1

Fast tier except Category D (concurrent stress, marked slow).
"""
import asyncio
import dataclasses
import time

import pytest


# ---------------------------------------------------------------------------
# Category A: Session/VoiceEvidence shape
# ---------------------------------------------------------------------------

class TestSessionShape:

    def test_session_has_slots(self):
        from core.session_state import Session
        s = Session(
            person_id="p1", person_name="Alice", person_type="known",
            session_type="face", started_at=1.0, last_face_seen=1.0, last_spoke_at=1.0,
        )
        assert hasattr(type(s), "__slots__"), "Session must use __slots__"
        with pytest.raises(AttributeError):
            s.nonexistent_field = "x"

    def test_session_required_fields_have_correct_types(self):
        from core.session_state import Session, VoiceEvidence
        s = Session(
            person_id="p1", person_name="Alice", person_type="known",
            session_type="face", started_at=1.0, last_face_seen=2.0, last_spoke_at=3.0,
        )
        assert isinstance(s.person_id, str)
        assert isinstance(s.person_name, str)
        assert isinstance(s.person_type, str)
        assert isinstance(s.session_type, str)
        assert isinstance(s.started_at, float)
        assert isinstance(s.last_face_seen, float)
        assert isinstance(s.last_spoke_at, float)
        assert isinstance(s.evidence, VoiceEvidence)

    def test_session_optional_fields_default_correctly(self):
        from core.session_state import Session
        s = Session(
            person_id="p1", person_name="Alice", person_type="known",
            session_type="face", started_at=1.0, last_face_seen=1.0, last_spoke_at=1.0,
        )
        assert s.voice_confidence == 1.0
        assert s.room_session_id == ""
        assert s.user_turns == 0
        assert s.kairos_clock_reset is True
        assert s.voice_only_origin is False
        assert s.waiting_for_name is False
        assert s.voice_face_confirmed is False
        assert s.db_enrolled is False
        assert s.confidence_tier == ""
        assert s.prior_person_type is None
        assert s.dispute_reason is None
        assert s.disputed_claimed_name is None
        assert s.dispute_set_at is None
        assert s.disputed_block_count == 0
        assert s.disputed_block_alerted is False
        assert s.recent_voice_confs == []
        assert s.cached_prefix is None
        assert s.core_memory == []
        assert s.tool_repeat_last is None
        assert s.tool_repeat_count == 0
        assert s.recent_attributions == []

    def test_voice_evidence_has_slots(self):
        from core.session_state import VoiceEvidence
        ev = VoiceEvidence()
        assert hasattr(type(ev), "__slots__"), "VoiceEvidence must use __slots__"
        # P0.B1 D1 (2026-05-21): VoiceEvidence is now @dataclass(frozen=True, slots=True).
        # Frozen blocks ALL attribute writes (existing or new); slots additionally
        # blocks new-attribute writes via `__dict__` absence. The structural
        # slots-only check is the absence of `__dict__`. The "writes raise"
        # assertion is covered by test_p0_b1_voice_evidence_frozen.py Anchor 3
        # (direct mutation raises FrozenInstanceError). The pre-P0.B1
        # `pytest.raises(AttributeError)` check is moot under frozen+slots
        # combination in Python 3.13 (the dataclass-generated __setattr__ for
        # slotted-frozen dataclasses raises TypeError in some paths via the
        # super(type, obj) re-dispatch — known quirk).
        assert not hasattr(ev, "__dict__"), (
            "VoiceEvidence must NOT have __dict__ (slots-only memory layout)"
        )

    def test_voice_evidence_defaults(self):
        from core.session_state import VoiceEvidence
        ev = VoiceEvidence()
        assert ev.face_match_conf == 0.0
        assert ev.face_last_seen_ts == 0.0
        assert ev.anti_spoof_live is False
        assert ev.anti_spoof_score == 0.0
        assert ev.anti_spoof_last_ts == 0.0
        assert ev.voice_match_conf == 0.0
        assert ev.voice_sample_count == 0
        assert ev.voice_last_heard_ts == 0.0
        assert ev.bootstrap_credits == 0


# ---------------------------------------------------------------------------
# Category B: Snapshot immutability
# ---------------------------------------------------------------------------

class TestSnapshotImmutability:

    def _make_snapshot(self):
        from core.session_state import Session, _to_snapshot
        s = Session(
            person_id="p1", person_name="Alice", person_type="known",
            session_type="face", started_at=1.0, last_face_seen=1.0, last_spoke_at=1.0,
        )
        return _to_snapshot(s)

    def test_snapshot_is_frozen(self):
        snap = self._make_snapshot()
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            snap.person_name = "Bob"

    def test_snapshot_has_slots(self):
        snap = self._make_snapshot()
        assert hasattr(type(snap), "__slots__"), "SessionSnapshot must use __slots__"

    def test_snapshot_mirrors_session_fields(self):
        from core.session_state import Session, SessionSnapshot
        session_fields = {f.name for f in dataclasses.fields(Session)}
        snapshot_fields = {f.name for f in dataclasses.fields(SessionSnapshot)}
        assert session_fields == snapshot_fields

    def test_snapshot_values_match_session(self):
        from core.session_state import Session, _to_snapshot
        s = Session(
            person_id="p1", person_name="Alice", person_type="best_friend",
            session_type="face", started_at=100.0, last_face_seen=200.0, last_spoke_at=300.0,
        )
        s.voice_confidence = 0.88
        s.user_turns = 7
        snap = _to_snapshot(s)
        assert snap.person_id == "p1"
        assert snap.person_name == "Alice"
        assert snap.person_type == "best_friend"
        assert snap.voice_confidence == 0.88
        assert snap.user_turns == 7


# ---------------------------------------------------------------------------
# Category C: SessionStore API
# ---------------------------------------------------------------------------

class TestSessionStoreLifecycle:

    @pytest.mark.asyncio
    async def test_open_creates_session(self):
        from core.session_state import SessionStore
        store = SessionStore()
        now = time.time()
        await store.open_session("p1", "Alice", "known", "face", now=now)
        snap = await store.get_snapshot("p1")
        assert snap is not None
        assert snap.person_name == "Alice"
        assert snap.person_type == "known"

    @pytest.mark.asyncio
    async def test_close_removes_session(self):
        from core.session_state import SessionStore
        store = SessionStore()
        now = time.time()
        await store.open_session("p1", "Alice", "known", "face", now=now)
        await store.close_session("p1")
        snap = await store.get_snapshot("p1")
        assert snap is None

    @pytest.mark.asyncio
    async def test_close_nonexistent_is_noop(self):
        from core.session_state import SessionStore
        store = SessionStore()
        await store.close_session("nonexistent")  # must not raise

    @pytest.mark.asyncio
    async def test_open_bootstrap_credits(self):
        from core.session_state import SessionStore
        store = SessionStore()
        await store.open_session("p1", "Bob", "stranger", "voice", now=1.0, bootstrap_credits=20)
        snap = await store.get_snapshot("p1")
        assert snap.evidence.bootstrap_credits == 20

    @pytest.mark.asyncio
    async def test_update_on_reopen(self):
        from core.session_state import SessionStore
        store = SessionStore()
        await store.open_session("p1", "Alice", "known", "face", now=1.0)
        await store.update_on_reopen("p1", voice_confidence=0.75)
        snap = await store.get_snapshot("p1")
        assert snap.voice_confidence == 0.75


class TestSessionStoreFaceVoice:

    @pytest.mark.asyncio
    async def test_update_face_seen(self):
        from core.session_state import SessionStore
        store = SessionStore()
        await store.open_session("p1", "Alice", "known", "face", now=1.0)
        await store.update_face_seen("p1", conf=0.92, ts=2.5,
                                      anti_spoof_live=True, anti_spoof_score=0.88)
        snap = await store.get_snapshot("p1")
        assert snap.last_face_seen == 2.5
        assert snap.evidence.face_match_conf == 0.92
        assert snap.evidence.face_last_seen_ts == 2.5
        assert snap.evidence.anti_spoof_live is True
        assert snap.evidence.anti_spoof_score == 0.88
        assert snap.evidence.anti_spoof_last_ts == 2.5

    @pytest.mark.asyncio
    async def test_update_voice_heard(self):
        from core.session_state import SessionStore
        store = SessionStore()
        await store.open_session("p1", "Alice", "known", "face", now=1.0)
        await store.update_voice_heard("p1", conf=0.80, ts=5.0)
        snap = await store.get_snapshot("p1")
        assert snap.last_spoke_at == 5.0
        assert snap.evidence.voice_match_conf == 0.80
        assert snap.evidence.voice_last_heard_ts == 5.0

    @pytest.mark.asyncio
    async def test_increment_voice_sample_count(self):
        from core.session_state import SessionStore
        store = SessionStore()
        await store.open_session("p1", "Alice", "known", "face", now=1.0)
        await store.increment_voice_sample_count("p1")
        await store.increment_voice_sample_count("p1")
        snap = await store.get_snapshot("p1")
        assert snap.evidence.voice_sample_count == 2

    @pytest.mark.asyncio
    async def test_decrement_bootstrap_credits_floors_at_zero(self):
        from core.session_state import SessionStore
        store = SessionStore()
        await store.open_session("p1", "Alice", "stranger", "voice", now=1.0, bootstrap_credits=1)
        await store.decrement_bootstrap_credits("p1")
        await store.decrement_bootstrap_credits("p1")  # should floor at 0
        snap = await store.get_snapshot("p1")
        assert snap.evidence.bootstrap_credits == 0

    @pytest.mark.asyncio
    async def test_append_voice_conf(self):
        from core.session_state import SessionStore
        store = SessionStore()
        await store.open_session("p1", "Alice", "known", "face", now=1.0)
        await store.append_voice_conf("p1", conf=0.9)
        await store.append_voice_conf("p1", conf=0.85)
        snap = await store.get_snapshot("p1")
        assert snap.recent_voice_confs == [0.9, 0.85]


class TestSessionStoreDispute:

    @pytest.mark.asyncio
    async def test_transition_to_disputed_captures_prior_type(self):
        from core.session_state import SessionStore
        store = SessionStore()
        await store.open_session("p1", "Alice", "known", "face", now=1.0)
        await store.transition_to_disputed("p1", "Bob", "voice_mismatch", now=2.0)
        snap = await store.get_snapshot("p1")
        assert snap.person_type == "disputed"
        assert snap.prior_person_type == "known"
        assert snap.disputed_claimed_name == "Bob"
        assert snap.dispute_reason == "voice_mismatch"
        assert snap.dispute_set_at == 2.0

    @pytest.mark.asyncio
    async def test_transition_to_disputed_fails_closed_for_best_friend(self):
        from core.session_state import SessionStore
        store = SessionStore()
        await store.open_session("p1", "Alice", "best_friend", "face", now=1.0)
        await store.transition_to_disputed("p1", "Attacker", "suspicious", now=2.0)
        snap = await store.get_snapshot("p1")
        assert snap.prior_person_type == "best_friend"  # captured, not "known"

    @pytest.mark.asyncio
    async def test_clear_dispute_restores_prior_type(self):
        from core.session_state import SessionStore
        store = SessionStore()
        await store.open_session("p1", "Alice", "known", "face", now=1.0)
        await store.transition_to_disputed("p1", "Bob", "reason", now=2.0)
        await store.clear_dispute("p1", now=3.0)
        snap = await store.get_snapshot("p1")
        assert snap.person_type == "known"
        assert snap.prior_person_type is None
        assert snap.dispute_reason is None
        assert snap.disputed_claimed_name is None

    @pytest.mark.asyncio
    async def test_clear_dispute_fails_closed_on_missing_prior(self):
        """If prior_person_type is None, clear_dispute must default to 'stranger'."""
        from core.session_state import SessionStore
        store = SessionStore()
        await store.open_session("p1", "Alice", "known", "face", now=1.0)
        # Manually force prior_person_type=None by opening then directly clearing
        # (simulates edge case where prior was never set)
        await store.clear_dispute("p1", now=2.0)  # prior is None -> must restore as stranger
        snap = await store.get_snapshot("p1")
        assert snap.person_type == "stranger"  # fail-closed

    @pytest.mark.asyncio
    async def test_increment_block_count(self):
        from core.session_state import SessionStore
        store = SessionStore()
        await store.open_session("p1", "Alice", "disputed", "face", now=1.0)
        await store.increment_block_count("p1")
        await store.increment_block_count("p1")
        snap = await store.get_snapshot("p1")
        assert snap.disputed_block_count == 2

    @pytest.mark.asyncio
    async def test_mark_block_alerted(self):
        from core.session_state import SessionStore
        store = SessionStore()
        await store.open_session("p1", "Alice", "disputed", "face", now=1.0)
        await store.mark_block_alerted("p1")
        snap = await store.get_snapshot("p1")
        assert snap.disputed_block_alerted is True


class TestSessionStoreNameType:

    @pytest.mark.asyncio
    async def test_rename(self):
        from core.session_state import SessionStore
        store = SessionStore()
        await store.open_session("p1", "Alice", "known", "face", now=1.0)
        await store.rename("p1", "Alicia")
        snap = await store.get_snapshot("p1")
        assert snap.person_name == "Alicia"

    @pytest.mark.asyncio
    async def test_promote_type(self):
        from core.session_state import SessionStore
        store = SessionStore()
        await store.open_session("p1", "Alice", "known", "face", now=1.0)
        await store.promote_type("p1", "best_friend")
        snap = await store.get_snapshot("p1")
        assert snap.person_type == "best_friend"

    @pytest.mark.asyncio
    async def test_set_waiting_for_name(self):
        from core.session_state import SessionStore
        store = SessionStore()
        await store.open_session("p1", "s_abc", "stranger", "voice", now=1.0)
        await store.set_waiting_for_name("p1", True)
        snap = await store.get_snapshot("p1")
        assert snap.waiting_for_name is True

    @pytest.mark.asyncio
    async def test_mark_voice_face_confirmed(self):
        from core.session_state import SessionStore
        store = SessionStore()
        await store.open_session("p1", "Alice", "known", "face", now=1.0)
        await store.mark_voice_face_confirmed("p1")
        snap = await store.get_snapshot("p1")
        assert snap.voice_face_confirmed is True


class TestSessionStoreTurnAccounting:

    @pytest.mark.asyncio
    async def test_increment_user_turns(self):
        from core.session_state import SessionStore
        store = SessionStore()
        await store.open_session("p1", "Alice", "known", "face", now=1.0)
        await store.increment_user_turns("p1")
        await store.increment_user_turns("p1")
        await store.increment_user_turns("p1")
        snap = await store.get_snapshot("p1")
        assert snap.user_turns == 3

    @pytest.mark.asyncio
    async def test_consume_kairos_reset(self):
        from core.session_state import SessionStore
        store = SessionStore()
        await store.open_session("p1", "Alice", "known", "face", now=1.0)
        snap_before = await store.get_snapshot("p1")
        assert snap_before.kairos_clock_reset is True
        await store.consume_kairos_reset("p1")
        snap = await store.get_snapshot("p1")
        assert snap.kairos_clock_reset is False

    @pytest.mark.asyncio
    async def test_record_attribution(self):
        from core.session_state import SessionStore
        store = SessionStore()
        await store.open_session("p1", "Alice", "known", "face", now=1.0)
        await store.record_attribution("p1", "face")
        await store.record_attribution("p1", "voice")
        snap = await store.get_snapshot("p1")
        assert snap.recent_attributions == ["face", "voice"]

    @pytest.mark.asyncio
    async def test_update_tool_repeat(self):
        from core.session_state import SessionStore
        store = SessionStore()
        await store.open_session("p1", "Alice", "known", "face", now=1.0)
        await store.update_tool_repeat("p1", "update_system_name:Kara", 2)
        snap = await store.get_snapshot("p1")
        assert snap.tool_repeat_last == "update_system_name:Kara"
        assert snap.tool_repeat_count == 2


class TestSessionStoreCacheWrites:

    @pytest.mark.asyncio
    async def test_set_cached_prefix(self):
        from core.session_state import SessionStore
        store = SessionStore()
        await store.open_session("p1", "Alice", "known", "face", now=1.0)
        await store.set_cached_prefix("p1", "Hello Alice")
        snap = await store.get_snapshot("p1")
        assert snap.cached_prefix == "Hello Alice"

    @pytest.mark.asyncio
    async def test_set_core_memory(self):
        from core.session_state import SessionStore
        store = SessionStore()
        await store.open_session("p1", "Alice", "known", "face", now=1.0)
        mem = [{"attr": "lives_in", "value": "Bangalore"}]
        await store.set_core_memory("p1", mem)
        snap = await store.get_snapshot("p1")
        assert snap.core_memory == mem

    @pytest.mark.asyncio
    async def test_mark_enrolled(self):
        from core.session_state import SessionStore
        store = SessionStore()
        await store.open_session("p1", "Alice", "known", "face", now=1.0)
        await store.mark_enrolled("p1", tier="high")
        snap = await store.get_snapshot("p1")
        assert snap.db_enrolled is True
        assert snap.confidence_tier == "high"


# ---------------------------------------------------------------------------
# Category D: Concurrent stress (slow)
# ---------------------------------------------------------------------------

class TestSessionStoreConcurrent:

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_100_concurrent_openers_no_torn_state(self):
        """100 coroutines each open a unique pid; final count must be exactly 100."""
        from core.session_state import SessionStore
        store = SessionStore()
        now = time.time()

        async def open_one(i):
            await store.open_session(f"pid_{i}", f"Person{i}", "known", "face", now=now)

        await asyncio.gather(*[open_one(i) for i in range(100)])
        # Every pid must be readable and have a coherent snapshot
        for i in range(100):
            snap = await store.get_snapshot(f"pid_{i}")
            assert snap is not None, f"pid_{i} not found after concurrent open"
            assert snap.person_name == f"Person{i}"

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_100_concurrent_mutations_correct_final_state(self):
        """100 coroutines each increment user_turns; final count must be exactly 100."""
        from core.session_state import SessionStore
        store = SessionStore()
        now = time.time()
        await store.open_session("shared_pid", "Shared", "known", "face", now=now)

        async def increment_one():
            await store.increment_user_turns("shared_pid")

        await asyncio.gather(*[increment_one() for _ in range(100)])
        snap = await store.get_snapshot("shared_pid")
        assert snap.user_turns == 100, f"Expected 100, got {snap.user_turns} (torn write)"

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_peek_snapshot_never_raises_under_concurrent_mutation(self):
        """peek_snapshot() must never raise even while mutations are running."""
        from core.session_state import SessionStore
        store = SessionStore()
        now = time.time()
        await store.open_session("peek_pid", "PeekPerson", "known", "face", now=now)
        errors = []

        async def mutate():
            for _ in range(20):
                await store.increment_user_turns("peek_pid")
                await asyncio.sleep(0)

        async def peek():
            for _ in range(50):
                try:
                    store.peek_snapshot("peek_pid")
                except Exception as e:
                    errors.append(e)
                await asyncio.sleep(0)

        await asyncio.gather(mutate(), peek())
        assert not errors, f"peek_snapshot raised: {errors}"


# ---------------------------------------------------------------------------
# Category E: Snapshot semantics
# ---------------------------------------------------------------------------

class TestSessionStoreSnapshotSemantics:

    @pytest.mark.asyncio
    async def test_snapshot_list_fields_are_copies_not_references(self):
        """Modifying Session's list after snapshot must not affect snapshot."""
        from core.session_state import SessionStore
        store = SessionStore()
        await store.open_session("p1", "Alice", "known", "face", now=1.0)
        await store.append_voice_conf("p1", conf=0.9)
        snap1 = await store.get_snapshot("p1")
        # Now add another conf to the session
        await store.append_voice_conf("p1", conf=0.5)
        # snap1 must still see only [0.9]
        assert snap1.recent_voice_confs == [0.9], "Snapshot leaked session list reference"

    @pytest.mark.asyncio
    async def test_snapshot_reflects_latest_state(self):
        """Two snapshots of the same pid taken before/after mutation differ."""
        from core.session_state import SessionStore
        store = SessionStore()
        await store.open_session("p1", "Alice", "known", "face", now=1.0)
        snap_before = await store.get_snapshot("p1")
        await store.increment_user_turns("p1")
        snap_after = await store.get_snapshot("p1")
        assert snap_before.user_turns == 0
        assert snap_after.user_turns == 1

    @pytest.mark.asyncio
    async def test_get_snapshot_none_for_unknown_pid(self):
        from core.session_state import SessionStore
        store = SessionStore()
        snap = await store.get_snapshot("ghost_pid")
        assert snap is None

    def test_peek_snapshot_none_for_unknown_pid(self):
        from core.session_state import SessionStore
        store = SessionStore()
        snap = store.peek_snapshot("ghost_pid")
        assert snap is None

    def test_peek_snapshot_sync_returns_correct_data(self):
        """peek_snapshot should work synchronously without awaiting."""
        from core.session_state import SessionStore
        import asyncio
        store = SessionStore()
        asyncio.run(store.open_session("p1", "SyncTest", "known", "face", now=1.0))
        snap = store.peek_snapshot("p1")
        assert snap is not None
        assert snap.person_name == "SyncTest"

    @pytest.mark.asyncio
    async def test_mutations_on_unknown_pid_are_noops(self):
        """All mutation methods on a missing pid must silently no-op."""
        from core.session_state import SessionStore
        store = SessionStore()
        pid = "ghost_pid"
        # None of these should raise
        await store.update_face_seen(pid, conf=0.9, ts=1.0, anti_spoof_live=True, anti_spoof_score=0.8)
        await store.update_voice_heard(pid, conf=0.8, ts=1.0)
        await store.increment_voice_sample_count(pid)
        await store.increment_user_turns(pid)
        await store.rename(pid, "NewName")
        await store.close_session(pid)
        snap = await store.get_snapshot(pid)
        assert snap is None
