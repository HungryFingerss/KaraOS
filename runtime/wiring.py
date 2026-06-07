# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors
"""runtime/wiring.py — the DI container (P1.A1 SP-5, the wiring pivot).

Single canonical home for the 16 Store singletons + global service refs
that pipeline.py and the SP-6 engine modules share.

11 reset-in-place stores (conftest .reset()s the same object) are
from-import SAFE — pipeline.py + extracted modules `from runtime.wiring
import _presence_store`. 5 rebound/lazy/re-pointed refs (_session_store,
_pipeline_state_store, _brain_orchestrator, _face_db_ref, _room_orchestrator)
are rebound by the autouse fixture / factory-reset / run() / ~150 test
mocks; a from-import would SNAPSHOT the stale binding, so pipeline.py
forwards their READS via a module-level __getattr__ (installed at SP-5
step c) and every REBIND targets runtime.wiring._X (via
set_brain_orchestrator() for the ~150 _brain_orchestrator sites).

P1.A1-canary note: standing up this module is behavior-neutral; the
make-or-break is the rebind-site migration (step b) + the __getattr__
facade (step c), proven by the cross-module reset-propagation test.
"""
from __future__ import annotations

from core.anti_spoof_rejection_store import AntiSpoofRejectionStore
from core.cache_store import CacheStore
from core.config import SCENE_BLOCK_CACHE_MAX_ENTRIES
from core.conversation_store import ConversationStore
from core.per_person_agent_store import PerPersonAgentStore
from core.pipeline_state_store import PipelineStateStore
from core.presence_store import PresenceStore
from core.session_state import SessionStore
from core.track_store import TrackStore
from core.vision_frame_store import VisionFrameStore
from core.voice_gallery_store import VoiceGalleryStore
from core.vision import LipTracker
from runtime.state_enums import PipelineState, CloudState


_identity_hints_store: "CacheStore" = CacheStore("identity_hints")
_face_db_ref:           "FaceDB | None"       = None # Obs 1: module-level reference to FaceDB instance, set in run() — gives module-level helpers (e.g. _open_session) authoritative DB access for voice count fallback when the in-memory cache may be stale.
_session_store:      SessionStore      = SessionStore()        # P0.7 — typed session state
_conversation_store: ConversationStore = ConversationStore()   # P0.6.3 — conversation history + timestamps
_brain_orchestrator:    "BrainOrchestrator | None" = None  # set in run() after event loop starts
_query_embedding_store: "CacheStore"               = CacheStore("query_embedding")  # person_id → embedding from previous turn
_presence_store:        "PresenceStore"             = PresenceStore()  # replaces _persons_in_frame
_track_store:           "TrackStore"               = TrackStore()     # replaces _unrecognized_tracks/_embeddings/_stranger_track_map/_track_identity
_anti_spoof_rejection_store: "AntiSpoofRejectionStore" = AntiSpoofRejectionStore()
_voice_gallery_store:   "VoiceGalleryStore"         = VoiceGalleryStore()   # P0.6.4 — replaces _voice_gallery + _voice_gallery_sizes
_per_person_agent_store: "PerPersonAgentStore"      = PerPersonAgentStore() # P0.6.4 — replaces _emotion_agents + _sessions_started + _ambient_wake_pending
_vision_frame_store:    "VisionFrameStore"          = VisionFrameStore()    # P0.6.7v2 — replaces _latest_vision_frame + _latest_frame_time + _vision_prev_det_count
_scene_block_store: "CacheStore" = CacheStore("scene_block", max_entries=SCENE_BLOCK_CACHE_MAX_ENTRIES)
_pipeline_state_store: "PipelineStateStore" = PipelineStateStore(
    initial_pipeline_state=PipelineState.WATCHING,
    initial_cloud_state=CloudState.ONLINE,
)
_room_orchestrator: "RoomOrchestrator | None" = None
_CLASSIFIER_CACHE_TTL_SECS = 5.0
_CLASSIFIER_CACHE_MAX_SIZE = 64
_classifier_cache_store: "CacheStore" = CacheStore("classifier", ttl=_CLASSIFIER_CACHE_TTL_SECS, max_entries=_CLASSIFIER_CACHE_MAX_SIZE)

# P1.A1 SP-6.1 — relocated from pipeline.py. Never-rebound singleton (LipTracker
# .update()/.reset() in-place); cycle-safe neutral home shared by runtime.session
# + runtime.vision_loop, neither of which then imports the other.
lip_tracker = LipTracker()

# P1.A1 SP-6.3 — WIRE-d vision globals (multi-module read+write: the vision-loop
# functions in runtime.vision_loop + staying pipeline code [run/enrollment]).
# Canonical home so reads+writes from both modules share one __dict__ (SP-5 lesson).
_anti_spoof_checker:    "AntiSpoofChecker | None"  = None  # set in run(); None when ANTISPOOFING_ENABLED=False
_vision_task: "asyncio.Task | None" = None
_vision_last_heartbeat:       float         = 0.0  # epoch time of last [Vision] status print
_vision_last_heartbeat_state: str           = ""   # last printed heartbeat content — skip if unchanged

# P1.A1 SP-6.4 — WIRE-d background-loop global (multi-module read+write: the loop fns in
# runtime.background_loops + staying pipeline code [run/first_boot/enrollment/conversation_turn]).
# Canonical home so reads+writes from both modules share one __dict__ (SP-5 lesson). Created
# inside run() once the event loop is running (signal handlers fire outside the loop).
_shutdown_event:     asyncio.Event | None      = None


def set_brain_orchestrator(value):
    """Canonical-home setter for the rebound _brain_orchestrator (P1.A1 SP-5).

    The ~150 `pipeline._brain_orchestrator = mock` test rebinds + run()'s
    lazy None->real set + sim_runner funnel through here so every rebind
    targets runtime.wiring._brain_orchestrator (NOT pipeline's namespace,
    which would shadow the __getattr__ facade). Plain setter — each test's
    own save/restore (`_prev = pipeline._brain_orchestrator` ... finally
    `set_brain_orchestrator(_prev)`) is preserved verbatim (behavior-neutral).
    """
    global _brain_orchestrator
    _brain_orchestrator = value
