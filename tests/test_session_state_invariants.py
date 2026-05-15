"""
Structural invariant tests for core/session_state.py — P0.7.1

Fast tier — no I/O, no network. AST-based checks enforce architectural rules
so that future modifications can't silently violate the SessionStore contract.
"""
import ast
import inspect
import pathlib
import pytest

SESSION_STATE_PATH = pathlib.Path(__file__).parent.parent / "core" / "session_state.py"

# ---------------------------------------------------------------------------
# Expected field sets — canonical spec from p0_7_field_inventory.md
# ---------------------------------------------------------------------------

EXPECTED_SESSION_FIELDS = frozenset({
    "person_id", "person_name", "person_type", "session_type",
    "started_at", "last_face_seen", "last_spoke_at", "voice_confidence",
    "evidence", "room_session_id", "user_turns", "kairos_clock_reset",
    "voice_only_origin", "waiting_for_name", "voice_face_confirmed",
    "db_enrolled", "confidence_tier", "prior_person_type", "dispute_reason",
    "disputed_claimed_name", "dispute_set_at", "disputed_block_count",
    "disputed_block_alerted", "recent_voice_confs", "cached_prefix",
    "core_memory", "tool_repeat_last", "tool_repeat_count", "recent_attributions",
})  # 29 fields

EXPECTED_VOICE_EVIDENCE_FIELDS = frozenset({
    "face_match_conf", "face_last_seen_ts", "anti_spoof_live", "anti_spoof_score",
    "anti_spoof_last_ts", "voice_match_conf", "voice_sample_count",
    "voice_last_heard_ts", "bootstrap_credits",
})  # 9 fields

EXPECTED_STORE_METHODS = frozenset({
    # Lifecycle
    "open_session", "close_session", "update_on_reopen",
    # Face/voice signals
    "update_face_seen", "update_voice_heard", "increment_voice_sample_count",
    "decrement_bootstrap_credits", "append_voice_conf",
    "set_last_face_seen", "set_last_spoke_at", "record_voice_spoke",
    "set_voice_sample_count", "set_bootstrap_credits", "increment_bootstrap_credits",
    # Dispute
    "transition_to_disputed", "clear_dispute", "increment_block_count", "mark_block_alerted",
    "set_dispute_set_at",
    # Name/type
    "rename", "promote_type", "set_waiting_for_name", "set_voice_only_origin",
    "mark_voice_face_confirmed",
    # Turn accounting
    "increment_user_turns", "consume_kairos_reset", "record_attribution", "update_tool_repeat",
    # Cache writes
    "set_cached_prefix", "set_core_memory", "mark_enrolled",
    # Reads
    "get_snapshot", "peek_snapshot", "peek_all_snapshots",
})  # 34 methods


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_session_store_class():
    from core.session_state import SessionStore
    return SessionStore


def _parse_session_state_ast() -> ast.Module:
    src = SESSION_STATE_PATH.read_text(encoding="utf-8")
    return ast.parse(src)


def _find_class_node(tree: ast.Module, class_name: str) -> ast.ClassDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return node
    raise AssertionError(f"Class {class_name!r} not found in session_state.py")


# ---------------------------------------------------------------------------
# I1: Session field completeness
# ---------------------------------------------------------------------------

class TestSessionFieldInvariants:

    def test_session_field_set_matches_expected(self):
        from core.session_state import Session
        import dataclasses
        actual = frozenset(f.name for f in dataclasses.fields(Session))
        assert actual == EXPECTED_SESSION_FIELDS, (
            f"Session fields changed — update EXPECTED_SESSION_FIELDS.\n"
            f"  Extra in Session:   {actual - EXPECTED_SESSION_FIELDS}\n"
            f"  Missing in Session: {EXPECTED_SESSION_FIELDS - actual}"
        )

    def test_voice_evidence_field_set_matches_expected(self):
        from core.session_state import VoiceEvidence
        import dataclasses
        actual = frozenset(f.name for f in dataclasses.fields(VoiceEvidence))
        assert actual == EXPECTED_VOICE_EVIDENCE_FIELDS, (
            f"VoiceEvidence fields changed — update EXPECTED_VOICE_EVIDENCE_FIELDS.\n"
            f"  Extra:   {actual - EXPECTED_VOICE_EVIDENCE_FIELDS}\n"
            f"  Missing: {EXPECTED_VOICE_EVIDENCE_FIELDS - actual}"
        )

    def test_snapshot_mirrors_session_fields(self):
        """Every Session field must appear in SessionSnapshot (same names)."""
        from core.session_state import Session, SessionSnapshot
        import dataclasses
        session_fields = frozenset(f.name for f in dataclasses.fields(Session))
        snapshot_fields = frozenset(f.name for f in dataclasses.fields(SessionSnapshot))
        assert session_fields == snapshot_fields, (
            f"SessionSnapshot must mirror Session fields exactly.\n"
            f"  In Session but not Snapshot: {session_fields - snapshot_fields}\n"
            f"  In Snapshot but not Session: {snapshot_fields - session_fields}"
        )


# ---------------------------------------------------------------------------
# I2: SessionStore method completeness (forward + inverse)
# ---------------------------------------------------------------------------

class TestSessionStoreMethods:

    def test_store_has_all_expected_methods(self):
        """Forward: every method in EXPECTED_STORE_METHODS exists on SessionStore."""
        from core.session_state import SessionStore
        for method_name in sorted(EXPECTED_STORE_METHODS):
            assert hasattr(SessionStore, method_name), (
                f"SessionStore missing expected method: {method_name!r}"
            )

    def test_no_undocumented_public_methods(self):
        """Inverse: every public non-dunder method on SessionStore is in EXPECTED_STORE_METHODS."""
        from core.session_state import SessionStore
        actual_public = frozenset(
            name for name, _ in inspect.getmembers(SessionStore, predicate=inspect.isfunction)
            if not name.startswith("_")
        )
        undocumented = actual_public - EXPECTED_STORE_METHODS
        assert not undocumented, (
            f"SessionStore has public methods not in EXPECTED_STORE_METHODS: {undocumented!r}.\n"
            f"Add them to EXPECTED_STORE_METHODS or rename with _ prefix."
        )


# ---------------------------------------------------------------------------
# I3: Sync mutator invariant (architect Strong 3)
# ---------------------------------------------------------------------------

class TestSyncMutatorInvariant:

    def test_session_store_no_sync_mutators(self):
        """All SessionStore methods must be async, except __init__ and peek_snapshot.

        peek_snapshot is sync-safe because:
        1. Single-threaded asyncio (no real thread parallelism)
        2. No sync mutators (all mutations go through async methods + lock)
        3. Returned SessionSnapshot is frozen + slots
        """
        SYNC_METHOD_ALLOWLIST = frozenset({
            "__init__", "__repr__", "__eq__", "__str__",
            "__hash__", "__del__",
            "peek_snapshot", "peek_all_snapshots",
        })
        tree = _parse_session_state_ast()
        store_node = _find_class_node(tree, "SessionStore")
        for child in store_node.body:
            if isinstance(child, ast.FunctionDef):  # sync def, NOT AsyncFunctionDef
                assert child.name in SYNC_METHOD_ALLOWLIST, (
                    f"SessionStore.{child.name}() is sync (def, not async def) "
                    f"but is not in the allowlist.\n"
                    f"Sync mutators break peek_snapshot() safety invariant.\n"
                    f"Either make it async or add it to SYNC_METHOD_ALLOWLIST "
                    f"with a documented justification."
                )


# ---------------------------------------------------------------------------
# I4: No Session objects leaked from SessionStore (architect Minor 3)
# ---------------------------------------------------------------------------

class TestNoSessionLeak:

    def test_session_store_methods_never_return_session_directly(self):
        """No SessionStore method may return a bare Session object.

        All reads must go through _to_snapshot() to return SessionSnapshot.
        Returning the mutable Session would allow callers to mutate state
        without going through the lock.
        """
        tree = _parse_session_state_ast()
        store_node = _find_class_node(tree, "SessionStore")
        # Variable names that would indicate returning a raw Session
        SESSION_VAR_NAMES = {"s", "_s", "session", "_session"}
        for method in store_node.body:
            if not isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for stmt in ast.walk(method):
                if isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.Name):
                    assert stmt.value.id not in SESSION_VAR_NAMES, (
                        f"SessionStore.{method.name}() returns {stmt.value.id!r} directly — "
                        f"this leaks the mutable Session. Use _to_snapshot() instead."
                    )


# ---------------------------------------------------------------------------
# I5: Dataclass decorators present
# ---------------------------------------------------------------------------

class TestDataclassDecorators:

    def _has_decorator(self, tree: ast.Module, class_name: str, decorator_check) -> bool:
        node = _find_class_node(tree, class_name)
        for dec in node.decorator_list:
            if decorator_check(dec):
                return True
        return False

    def _decorator_has_kwarg(self, dec: ast.expr, kwarg_name: str, kwarg_value: bool) -> bool:
        if not isinstance(dec, ast.Call):
            return False
        for kw in dec.keywords:
            if kw.arg == kwarg_name and isinstance(kw.value, ast.Constant):
                return kw.value.value == kwarg_value
        return False

    def test_session_has_slots(self):
        tree = _parse_session_state_ast()
        node = _find_class_node(tree, "Session")
        has_slots = any(
            isinstance(dec, ast.Call) and self._decorator_has_kwarg(dec, "slots", True)
            for dec in node.decorator_list
        )
        assert has_slots, "Session must have @dataclasses.dataclass(slots=True)"

    def test_session_snapshot_has_frozen_and_slots(self):
        tree = _parse_session_state_ast()
        node = _find_class_node(tree, "SessionSnapshot")
        has_frozen = any(
            isinstance(dec, ast.Call) and self._decorator_has_kwarg(dec, "frozen", True)
            for dec in node.decorator_list
        )
        has_slots = any(
            isinstance(dec, ast.Call) and self._decorator_has_kwarg(dec, "slots", True)
            for dec in node.decorator_list
        )
        assert has_frozen, "SessionSnapshot must have frozen=True"
        assert has_slots, "SessionSnapshot must have slots=True"

    def test_voice_evidence_has_slots(self):
        tree = _parse_session_state_ast()
        node = _find_class_node(tree, "VoiceEvidence")
        has_slots = any(
            isinstance(dec, ast.Call) and self._decorator_has_kwarg(dec, "slots", True)
            for dec in node.decorator_list
        )
        assert has_slots, "VoiceEvidence must have @dataclasses.dataclass(slots=True)"


# ---------------------------------------------------------------------------
# I6: _to_snapshot copies list fields (no reference aliasing)
# ---------------------------------------------------------------------------

class TestToSnapshotListCopy:

    def test_to_snapshot_copies_list_fields(self):
        """_to_snapshot must create new list objects, not aliases."""
        from core.session_state import Session, _to_snapshot
        s = Session(
            person_id="p1", person_name="Alice", person_type="known",
            session_type="face", started_at=1.0, last_face_seen=1.0, last_spoke_at=1.0,
        )
        s.recent_voice_confs = [0.9, 0.8]
        s.core_memory = ["mem1"]
        s.recent_attributions = ["attr1"]
        snap = _to_snapshot(s)
        assert snap.recent_voice_confs is not s.recent_voice_confs
        assert snap.core_memory is not s.core_memory
        assert snap.recent_attributions is not s.recent_attributions

    def test_to_snapshot_copies_voice_evidence(self):
        """_to_snapshot must copy VoiceEvidence, not alias it."""
        from core.session_state import Session, _to_snapshot
        import dataclasses
        s = Session(
            person_id="p1", person_name="Alice", person_type="known",
            session_type="face", started_at=1.0, last_face_seen=1.0, last_spoke_at=1.0,
        )
        s.evidence.face_match_conf = 0.95
        snap = _to_snapshot(s)
        assert snap.evidence is not s.evidence
        assert snap.evidence.face_match_conf == 0.95
