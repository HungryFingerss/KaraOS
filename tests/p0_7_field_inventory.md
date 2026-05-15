# P0.7 Phase 0a — Session Dict Field Inventory

**Generated:** 2026-05-09
**Source:** `pipeline.py` — grep audit of all `_active_sessions[...]` access sites (72 total)
**Purpose:** Mandatory pre-flight for P0.7.1. The `Session` dataclass is derived directly
from this inventory. DO NOT write P0.7.1 code until this document has been architect-reviewed.

---

## Phase 0 Measurements

| Question | Answer |
|---|---|
| Q1: Total `_active_sessions[` access sites | **72** |
| Q2: Distinct top-level field keys | **24** (15 base + identity_evidence sub-dict counted separately) |
| Q3: `.get(key, default)` pattern count | **~40** (across all read sites) |
| Q4: `.setdefault()` pattern count | **1** (line 4156: `prior_person_type`) |
| Q5: Sync helpers reading session state | **11** (see table below) |

**Sync helpers that read session state:**

| Helper | Line | Fields read |
|---|---|---|
| `_primary_person_id()` | 868 | `last_spoke_at` |
| `_primary_person_name()` | 875 | `person_name` |
| `_kairos_preferred_speaker()` | 881 | `last_spoke_at` |
| `_count_scene_candidates()` | 1162 | `person_type`, `session_type` |
| `_resolve_actual_speaker()` | 1180 | `last_spoke_at`, `voice_confidence`, `session_type`, `person_type`, `recent_attributions` |
| `_build_cross_person_excerpts()` | 1453 | `person_name`, `person_type`, `started_at` |
| `_build_room_block()` | 1573 | `person_name`, `person_type`, `started_at`, `room_session_id` |
| `_build_scene_block()` | 1891 | `person_name`, `person_type`, `session_type`, `last_face_seen`, `last_spoke_at` |
| `_voice_accum_allowed()` | 2245 | `identity_evidence`, `voice_only_origin`, `waiting_for_name` |
| `_expire_stale_sessions()` | 2440 | `session_type`, `last_face_seen`, `last_spoke_at`, `dispute_set_at`, `identity_evidence`, `recent_voice_confs`, `prior_person_type`, `person_name`, `person_type` |
| `_is_disputed()` | 463 | `person_type` |

---

## Field Inventory — Base Dict (always present after `_open_session`)

### F01: `person_id`
- **Type:** `str`
- **Default:** required — passed to `_open_session`
- **Mutation shape:** write-once (never mutated after creation)
- **Lifecycle phase:** P0.7.1 `Session.__init__` field
- **Read sites:** everywhere a session dict is used — most frequently via `_active_sessions[pid]` key lookups; directly accessed inside the dict e.g. `_active_sessions[_tracked_pid]["person_id"]` (line 6399 area)
- **Write sites:** `_open_session` only (line 2142)
- **Notes:** Redundant — the key into `_active_sessions` is the pid. Session needs it for self-contained snapshot semantics. Keep in `Session`.

### F02: `person_name`
- **Type:** `str`
- **Default:** required — passed to `_open_session`
- **Mutation shape:** mutated by rename paths (update_person_name, promotion chain, auto-confirm)
- **Lifecycle phase:** open + mutation-on-rename
- **Read sites:** scene block, excerpts, room block, KAIROS, conversation_turn, _close_session, many
- **Write sites:** lines 3821, 3955, 4053, 5925, 6399 area, `_open_session` (line 2143)
- **Notes:** Critical field — read by many sync helpers. Changes trigger `_persons_in_frame` name cache refresh.

### F03: `person_type`
- **Type:** `str` — one of `"stranger"`, `"known"`, `"best_friend"`, `"disputed"`
- **Default:** required — passed to `_open_session`; validated against `VALID_PERSON_TYPES`
- **Mutation shape:** mutated by dispute-flip, promotion, auto-confirm, dispute-clear
- **Lifecycle phase:** open + mutation-on-event
- **Read sites:** `_is_disputed()`, `_voice_accum_allowed()`, `_build_scene_block()`, privilege gate, `_expire_stale_sessions()`, `_resolve_actual_speaker()`, conversation_turn, many
- **Write sites:** lines 3984, 4064, 5926 (auto-confirm), 2512 (dispute clear restore), `_open_session` (line 2144)
- **Notes:** The P0.2 fail-closed fix (prior_person_type defaults to "stranger") directly relates to this field's mutation in the dispute path. The `Session` dataclass mutation for this must use a named method (`transition_to_disputed`, `restore_type`, etc.) — direct writes are the root cause of P0.2.

### F04: `session_type`
- **Type:** `str` — `"face"` or `"voice"`
- **Default:** required — passed to `_open_session`
- **Mutation shape:** write-once (never mutated after creation)
- **Lifecycle phase:** P0.7.1 `Session.__init__` field
- **Read sites:** `_expire_stale_sessions()` line 2534, `_build_scene_block()`, `_count_scene_candidates()`, `_voice_accum_allowed()` (checks `session_type != "voice"` at line 1959)
- **Write sites:** `_open_session` only (line 2145)

### F05: `last_face_seen`
- **Type:** `float` (Unix timestamp)
- **Default:** `time.time()` at session open
- **Mutation shape:** updated continuously by face scan
- **Lifecycle phase:** updated in background vision loop
- **Read sites:** `_expire_stale_sessions()` line 2535, `_build_scene_block()`, face-loss grace check
- **Write sites:** `_open_session` (line 2146, also 2072 on re-open), background vision loop line 2900, `_close_session` via FACE_LOSS_GRACE path

### F06: `last_spoke_at`
- **Type:** `float` (Unix timestamp)
- **Default:** `time.time()` at session open
- **Mutation shape:** updated on every utterance attribution
- **Lifecycle phase:** updated throughout the conversation loop
- **Read sites:** `_primary_person_id()` line 872, `_kairos_preferred_speaker()`, `_expire_stale_sessions()` line 2538, VOICE_SESSION_TIMEOUT check, `_resolve_actual_speaker()`
- **Write sites:** `_open_session` (lines 2147, 2071 on re-open), lines 6803, 7086, 7253, 7312, 7399

### F07: `voice_confidence`
- **Type:** `float` (0.0–1.0)
- **Default:** `1.0` (face-opened sessions) or passed score (voice-opened sessions)
- **Mutation shape:** updated on each speaker-routing event
- **Lifecycle phase:** updated in voice routing path
- **Read sites:** `_resolve_actual_speaker()` (indirectly via voice score comparisons), logging
- **Write sites:** `_open_session` (line 2148, also 2073 on re-open), lines 7087, 7254

### F08: `started_at`
- **Type:** `float` (Unix timestamp)
- **Default:** `time.time()` at session open
- **Mutation shape:** write-once
- **Lifecycle phase:** P0.7.1 `Session.__init__` field
- **Read sites:** `_is_enrollment_mishear_candidate()` line 449 (`session.get("started_at")`), `_build_cross_person_excerpts()` line 1504, `_build_room_block()` line 1573 area
- **Write sites:** `_open_session` only (line 2149)

### F09: `room_session_id`
- **Type:** `str`
- **Default:** copied from module-level `_active_room_session` at open time
- **Mutation shape:** write-once (room doesn't change mid-session)
- **Lifecycle phase:** P0.7.1 `Session.__init__` field
- **Read sites:** `log_turn` call sites (lines 3266 area, 7432 area), `_build_room_block()`
- **Write sites:** `_open_session` only (line 2153)

### F10: `kairos_clock_reset`
- **Type:** `bool`
- **Default:** `True`
- **Mutation shape:** consumed once (read and cleared) at conversation_turn entry
- **Lifecycle phase:** open + single-consume-on-first-turn
- **Read sites:** `conversation_turn()` (gates KAIROS silence-clock reset)
- **Write sites:** `_open_session` (line 2154)
- **Notes:** Prevents KAIROS from firing immediately on a new session because silence timer hasn't had time to accumulate. Once read as True it should be set to False — this is a latch pattern.

### F11: `recent_attributions`
- **Type:** `collections.deque(maxlen=3)`
- **Default:** empty deque at open
- **Mutation shape:** append-only (deque auto-evicts oldest)
- **Lifecycle phase:** updated in speaker routing
- **Read sites:** `_resolve_actual_speaker()` (drift detection, issue #21)
- **Write sites:** `_open_session` (line 2155), speaker routing attribution path
- **Notes:** The `deque` type is mutable and not serializable as a plain dict value. Needs explicit handling in `SessionSnapshot` (convert to tuple or list).

### F12: `user_turns`
- **Type:** `int`
- **Default:** `0`
- **Mutation shape:** incremented each user utterance
- **Lifecycle phase:** incremented at conversation_turn entry
- **Read sites:** `_kairos_sess.get("user_turns", 0)` at KAIROS (line 3200), vision_state builds (line 7453), `_cur_sess.get("user_turns", 0)` (line 7432), `STRANGER_IDENTITY_BLOCK_MIN_TURNS` comparison (line 7438)
- **Write sites:** `_open_session` (line 2161), `_cur_sess["user_turns"] = _prev_turns + 1` (line 7433)

### F13: `voice_only_origin`
- **Type:** `bool`
- **Default:** `False` (may be backfilled to `True` post-open for pre-S120 promoted persons)
- **Mutation shape:** set True at engagement-gate pass for voice-only opens, False on face-witness event
- **Lifecycle phase:** open + mutation-on-event
- **Read sites:** `_voice_accum_allowed()` line 2618, logging, replenishment gate
- **Write sites:** `_open_session` (line 2167), lines 2214, 6506, 6780

### F14: `identity_evidence`
- **Type:** `dict` — nested sub-record (see below)
- **Default:** fully initialized sub-dict (see F14a–F14i)
- **Mutation shape:** sub-fields updated by `_update_identity_evidence()` helper
- **Lifecycle phase:** updated throughout session
- **Read sites:** `_voice_accum_allowed()`, `_expire_stale_sessions()`, vision_state builds, KAIROS vision_state
- **Write sites:** `_open_session` (line 2170), `_update_identity_evidence()` (single-writer helper)
- **Notes:** The `_update_identity_evidence()` API enforces single-writer discipline and raises KeyError on unknown fields — preserves an invariant `Session` must maintain.

#### F14a: `identity_evidence.face_match_conf`
- **Type:** `float` (0.0–1.0)
- **Default:** `0.0`
- **Write sites:** `_update_identity_evidence(person_id, face_match_conf=score)` in face recognition paths

#### F14b: `identity_evidence.face_last_seen_ts`
- **Type:** `float` (Unix timestamp)
- **Default:** `0.0`
- **Write sites:** `_update_identity_evidence(person_id, face_last_seen_ts=time.time())`

#### F14c: `identity_evidence.anti_spoof_live`
- **Type:** `bool`
- **Default:** `False`
- **Write sites:** `_update_identity_evidence(person_id, anti_spoof_live=result)`

#### F14d: `identity_evidence.anti_spoof_score`
- **Type:** `float`
- **Default:** `0.0`
- **Write sites:** `_update_identity_evidence(person_id, anti_spoof_score=score)`

#### F14e: `identity_evidence.anti_spoof_last_ts`
- **Type:** `float` (Unix timestamp)
- **Default:** `0.0`
- **Write sites:** `_update_identity_evidence(person_id, anti_spoof_last_ts=time.time())`

#### F14f: `identity_evidence.voice_match_conf`
- **Type:** `float` (0.0–1.0)
- **Default:** `0.0`
- **Write sites:** `_update_identity_evidence(person_id, voice_match_conf=score)` in voice routing

#### F14g: `identity_evidence.voice_sample_count`
- **Type:** `int`
- **Default:** DB-hydrated from `_voice_gallery_sizes` at open time
- **Write sites:** `_update_identity_evidence(person_id, voice_sample_count=n)` after accumulation

#### F14h: `identity_evidence.voice_last_heard_ts`
- **Type:** `float` (Unix timestamp)
- **Default:** `0.0`
- **Write sites:** `_update_identity_evidence(person_id, voice_last_heard_ts=time.time())`

#### F14i: `identity_evidence.bootstrap_credits`
- **Type:** `int`
- **Default:** `N_INITIAL_VOICE_BOOTSTRAP` if `engagement_gate_passed=True` else `0`
- **Write sites:** `_update_identity_evidence(person_id, bootstrap_credits=n)` decremented in `_voice_accum_allowed` path C

### F15: `core_memory`
- **Type:** `list` (of dicts from `BrainDB.get_core_memory_for`)
- **Default:** `[]` — populated post-open if `_brain_orchestrator` is available
- **Mutation shape:** set once at open, not mutated mid-session
- **Lifecycle phase:** open
- **Read sites:** KAIROS vision_state `core_memory=_kairos_sess.get("core_memory")` (line 3229), `render_session_stable_prefix()` call sites
- **Write sites:** `_open_session` (line 2191 post-init fetch), lines 2183/2191

---

## Field Inventory — Lazily Added Fields (NOT present at `_open_session`)

These fields are absent from newly-opened sessions. Every read site must use `.get(key, default)` to be safe.

### L01: `cached_prefix`
- **Type:** `str`
- **Default:** absent (must `.get("cached_prefix")`)
- **Mutation shape:** set by render_session_stable_prefix call, re-set when prefix changes
- **Lifecycle phase:** first conversation_turn + on-rename
- **Read sites:** conversation_turn before context build
- **Write sites:** lines 3222, 5253

### L02: `_tool_repeat_last`
- **Type:** `str | None`
- **Default:** absent (`.get("_tool_repeat_last")` at line 3726)
- **Mutation shape:** set on each tool execution
- **Lifecycle phase:** updated per tool-call (Session 70 Bug Q repeat guard)
- **Read sites:** `_session.get("_tool_repeat_last")` (line 3726)
- **Write sites:** `_active_sessions[person_id]["_tool_repeat_last"] = _repeat_key` (line 3741)

### L03: `_tool_repeat_count`
- **Type:** `int`
- **Default:** absent (`.get("_tool_repeat_count", 1)` at line 3727)
- **Mutation shape:** incremented on repeat, reset on different tool
- **Lifecycle phase:** updated per tool-call
- **Read sites:** line 3727
- **Write sites:** lines 3738, 3742

### L04: `prior_person_type`
- **Type:** `str` — one of `VALID_PERSON_TYPES`
- **Default:** absent until first dispute-flip
- **Mutation shape:** set at dispute-flip, read at dispute-clear, set by report_identity_mismatch setdefault
- **Lifecycle phase:** set on dispute-flip event
- **Read sites:** `_sess.get("prior_person_type", "stranger")` (line 2511), `_sess.get("prior_person_type")` (line 4032)
- **Write sites:** line 3989, line 4156 (setdefault in report_identity_mismatch)
- **Notes:** P0.2 fix — the "stranger" default in `.get("prior_person_type", "stranger")` is load-bearing (fail-closed). Must be encoded in the `transition_to_disputed()` method on `Session`.

### L05: `dispute_reason`
- **Type:** `str`
- **Default:** absent until dispute-flip
- **Mutation shape:** set at dispute-flip
- **Read sites:** `_sess.get("dispute_reason")` or vision_state (indirect)
- **Write sites:** `_active_sessions[person_id]["dispute_reason"] = ...` (line 3990)

### L06: `disputed_claimed_name`
- **Type:** `str | None`
- **Default:** absent until dispute-flip
- **Mutation shape:** set at dispute-flip
- **Read sites:** `_kairos_sess.get("disputed_claimed_name")` (line 3191), vision_state builds, `_cur_sess.get("disputed_claimed_name")` (line 7447)
- **Write sites:** `_active_sessions[person_id]["disputed_claimed_name"] = new_name` (line 3993)

### L07: `dispute_set_at`
- **Type:** `float` (Unix timestamp)
- **Default:** absent until dispute-flip (may also be set by `_expire_stale_sessions` at line 2462 if missing)
- **Mutation shape:** set at dispute-flip, used for DISPUTE_MAX_DURATION timeout
- **Read sites:** `_sess.get("dispute_set_at")` (line 2460), `_sess.get("dispute_set_at")` (line 4039)
- **Write sites:** `_active_sessions[person_id]["dispute_set_at"] = time.time()` (line 3994), line 2462 (backfill anchor in `_expire_stale_sessions`)

### L08: `disputed_block_count`
- **Type:** `int`
- **Default:** absent (`.get("disputed_block_count", 0)` at line 4016)
- **Mutation shape:** incremented on each blocked rename during dispute
- **Read sites:** `_sess.get("disputed_block_count", 0)` (line 4016)
- **Write sites:** `_active_sessions[person_id]["disputed_block_count"] = _block_count` (line 4018)

### L09: `disputed_block_alerted`
- **Type:** `bool`
- **Default:** absent (`.get("disputed_block_alerted")` treats absence as falsy)
- **Mutation shape:** set once to True when watchdog alert fires for this dispute burst
- **Read sites:** `not _sess.get("disputed_block_alerted")` (line 4026)
- **Write sites:** `_active_sessions[person_id]["disputed_block_alerted"] = True` (line 4029)

### L10: `waiting_for_name`
- **Type:** `bool`
- **Default:** absent for known/best_friend sessions; set to `STRANGER_REQUIRE_SYSTEM_NAME` (True) for new strangers
- **Mutation shape:** set at engagement-gate open (strangers), cleared when gate passes
- **Lifecycle phase:** stranger-specific gate field
- **Read sites:** `session.get("waiting_for_name", '(absent)')` in logging, `session.get("waiting_for_name", False)` in `_voice_accum_allowed()`
- **Write sites:** lines 6486, 6776, 7319, 7481

### L11: `voice_face_confirmed`
- **Type:** `bool`
- **Default:** absent (treated as False at line 7416)
- **Mutation shape:** set to True when face+voice together confirm identity
- **Lifecycle phase:** set on progressive-enroll gate pass or greeting path
- **Read sites:** `_active_sessions.get(_cur_pid, {}).get("voice_face_confirmed", False)` (line 7416)
- **Write sites:** lines 6502, 7508
- **Notes:** Compat shim for backward compatibility. The identity_evidence sub-dict is the canonical record. Keep in `Session` as a computed property or deprecated compat field.

### L12: `db_enrolled`
- **Type:** `bool`
- **Default:** absent
- **Mutation shape:** set to True when progressive enrollment writes to DB
- **Read sites:** (used in accumulation gate logic, line 7489 area)
- **Write sites:** `_active_sessions[_cur_pid]["db_enrolled"] = True` (line 7489)

### L13: `confidence_tier`
- **Type:** `str`
- **Default:** absent
- **Mutation shape:** set at progressive-enrollment gate pass
- **Read sites:** (gate-pass context, logging)
- **Write sites:** `_active_sessions[_cur_pid]["confidence_tier"] = "enrolled_1"` (line 7490)

### L14: `recent_voice_confs`
- **Type:** `collections.deque` (implicitly, based on `.append()` usage at line 7110)
- **Default:** absent — created on first append
- **Mutation shape:** append-only (new voice confidence scores pushed)
- **Lifecycle phase:** updated per voice-routing event, used by dispute auto-clear
- **Read sites:** `_sess.get("recent_voice_confs", ())` (line 2488), `_dsess.get("recent_voice_confs")` (line 7106)
- **Write sites:** lines 7106–7110 — if None, created as deque with maxlen; else append
- **Notes:** Creation pattern is lazy — the deque is created on first use. Needs careful handling in `Session` init (initialize as `deque(maxlen=DISPUTE_AUTO_CLEAR_CONSECUTIVE_TURNS)` always, not lazily).

---

## Cross-Field Invariants

These invariants must be enforced by `Session` mutation methods, not by callers.

| Invariant | Description |
|---|---|
| **I01: dispute atomicity** | When `person_type` → `"disputed"`, MUST also write `prior_person_type` (defaulting to "stranger"), `dispute_reason`, `disputed_claimed_name`, `dispute_set_at` in the same operation. Violation = prior_person_type absent on auto-clear → fails P0.2 fix. |
| **I02: dispute clear atomicity** | When clearing dispute (restore `person_type`), MUST also pop `prior_person_type`, `dispute_reason`, `disputed_claimed_name`, `dispute_set_at`, `disputed_block_count`, `disputed_block_alerted`, `recent_voice_confs`. Leaving stale dispute fields with non-disputed `person_type` is unsafe. |
| **I03: prior_person_type fail-closed** | `prior_person_type` MUST default to `"stranger"` when absent (P0.2 fix). Any Session method that reads it must use `"stranger"` as the fallback, not `"known"`. |
| **I04: identity_evidence single-writer** | All writes to identity_evidence sub-fields MUST go through `_update_identity_evidence()` / `Session.update_evidence()`. No direct dict assignment to sub-fields. |
| **I05: voice_sample_count DB-hydrated at open** | `identity_evidence.voice_sample_count` is DB-authoritative and must be re-fetched from `FaceDB.count_voice_embeddings()` at every `_open_session`, not just taken from the in-memory cache. |
| **I06: room_session_id consistency** | `room_session_id` matches the module-level `_active_room_session` at open time. Must be write-once after that. |
| **I07: voice_only_origin + waiting_for_name gate** | Replenishment (Path C bootstrap) fires only when `voice_only_origin=True` AND `waiting_for_name=False`. Mutation of either field can flip the gate — must be done via named methods. |
| **I08: kairos_clock_reset latch** | `kairos_clock_reset` is a one-shot flag — set True at open, consumed (reset to False) on first conversation_turn. After that it must remain False. |
| **I09: person_type valid values** | `person_type` must always be one of `VALID_PERSON_TYPES`. Validated at `_open_session`; `Session.transition_*` methods must enforce this too. |

---

## Session Dataclass Field List (for P0.7.1 `core/session_state.py`)

```python
@dataclasses.dataclass(slots=True)
class VoiceEvidence:
    face_match_conf:     float = 0.0
    face_last_seen_ts:   float = 0.0
    anti_spoof_live:     bool  = False
    anti_spoof_score:    float = 0.0
    anti_spoof_last_ts:  float = 0.0
    voice_match_conf:    float = 0.0
    voice_sample_count:  int   = 0
    voice_last_heard_ts: float = 0.0
    bootstrap_credits:   int   = 0


@dataclasses.dataclass(slots=True)
class Session:
    # --- Identity (write-once or named-mutation-only) ---
    person_id:            str
    person_name:          str
    person_type:          str   # "stranger"|"known"|"best_friend"|"disputed"
    session_type:         str   # "face"|"voice"

    # --- Timestamps (updated by lifecycle + signal events) ---
    started_at:           float
    last_face_seen:       float
    last_spoke_at:        float

    # --- Voice / identity signal ---
    voice_confidence:     float = 1.0
    evidence:             VoiceEvidence = dataclasses.field(default_factory=VoiceEvidence)

    # --- Room ---
    room_session_id:      str   = ""

    # --- Turn accounting ---
    user_turns:           int   = 0
    kairos_clock_reset:   bool  = True

    # --- Voice-only origin tracking ---
    voice_only_origin:    bool  = False

    # --- Stranger gate ---
    waiting_for_name:     bool  = False

    # --- Progressive enrollment compat shim ---
    voice_face_confirmed: bool  = False
    db_enrolled:          bool  = False
    confidence_tier:      str   = ""

    # --- Dispute state (lazily set — all None when not disputed) ---
    prior_person_type:    str | None   = None   # P0.2: None → read as "stranger"
    dispute_reason:       str | None   = None
    disputed_claimed_name: str | None  = None
    dispute_set_at:       float | None = None
    disputed_block_count: int          = 0
    disputed_block_alerted: bool       = False
    recent_voice_confs:   list[float]  = dataclasses.field(default_factory=list)
    # Note: in production this is a deque(maxlen=DISPUTE_AUTO_CLEAR_CONSECUTIVE_TURNS);
    # for the dataclass use list and truncate in SessionStore.append_voice_conf()

    # --- Caches (computed, invalidated on rename) ---
    cached_prefix:        str | None   = None
    core_memory:          list         = dataclasses.field(default_factory=list)

    # --- Tool repeat guard ---
    tool_repeat_last:     str | None   = None
    tool_repeat_count:    int          = 0

    # --- Voice routing drift detection ---
    # Uses deque in production; list here, truncated by SessionStore
    recent_attributions:  list         = dataclasses.field(default_factory=list)
```

**Total fields: 29** (including VoiceEvidence sub-fields counted as 9 within the nested record).

---

## SessionStore API — Named Mutation Methods (~21 methods)

Every write to `_active_sessions[pid]["X"]` in pipeline.py must eventually be replaced by one of these named methods. Methods group logically related mutations so atomicity invariants (I01–I09 above) are enforced in one place.

### Lifecycle methods
| Method | Writes | Notes |
|---|---|---|
| `open_session(person_id, person_name, person_type, session_type, voice_confidence, engagement_gate_passed, room_session_id, db_voice_count, core_memory)` | F01–F15 (full init) | Replaces `_open_session` dict creation block |
| `close_session(person_id)` → `Session \| None` | removes session | Returns snapshot of closed session |
| `update_on_reopen(person_id, voice_confidence)` | `last_face_seen`, `last_spoke_at`, `voice_confidence` | Idempotent re-open update |

### Face/voice signal updates
| Method | Writes |
|---|---|
| `update_face_seen(person_id, conf, ts, anti_spoof_live, anti_spoof_score)` | `evidence.face_match_conf`, `evidence.face_last_seen_ts`, `evidence.anti_spoof_live`, `evidence.anti_spoof_score`, `evidence.anti_spoof_last_ts`, `last_face_seen` |
| `update_voice_heard(person_id, conf, ts)` | `evidence.voice_match_conf`, `evidence.voice_last_heard_ts`, `last_spoke_at`, `voice_confidence` |
| `increment_voice_sample_count(person_id)` | `evidence.voice_sample_count` |
| `decrement_bootstrap_credits(person_id)` | `evidence.bootstrap_credits` |
| `append_voice_conf(person_id, conf)` | `recent_voice_confs` (append + maxlen truncate) |

### Dispute state (atomic — enforce I01/I02/I03)
| Method | Writes |
|---|---|
| `transition_to_disputed(person_id, claimed_name, reason, now)` | `person_type="disputed"`, `prior_person_type` (fail-closed to "stranger"), `dispute_reason`, `disputed_claimed_name`, `dispute_set_at` |
| `clear_dispute(person_id, now)` | restores `person_type` from `prior_person_type`; clears all dispute fields |
| `increment_block_count(person_id)` | `disputed_block_count` |
| `mark_block_alerted(person_id)` | `disputed_block_alerted = True` |

### Name / type mutations
| Method | Writes |
|---|---|
| `rename(person_id, new_name)` | `person_name`, `cached_prefix = None` (invalidate) |
| `promote_type(person_id, new_type)` | `person_type` — for known/best_friend promotions only |
| `set_waiting_for_name(person_id, value)` | `waiting_for_name` |
| `set_voice_only_origin(person_id, value)` | `voice_only_origin` |
| `mark_voice_face_confirmed(person_id)` | `voice_face_confirmed = True` |

### Turn accounting
| Method | Writes |
|---|---|
| `increment_user_turns(person_id)` | `user_turns` |
| `consume_kairos_reset(person_id)` | `kairos_clock_reset = False` |
| `record_attribution(person_id, label)` | `recent_attributions` (append + maxlen=3 truncate) |
| `update_tool_repeat(person_id, repeat_key, count)` | `tool_repeat_last`, `tool_repeat_count` |

### Cache writes
| Method | Writes |
|---|---|
| `set_cached_prefix(person_id, prefix)` | `cached_prefix` |
| `set_core_memory(person_id, memory)` | `core_memory` |
| `mark_enrolled(person_id, tier)` | `db_enrolled = True`, `confidence_tier` |

**Total: 21 named methods.** All are the sole authorized write path for their respective fields.

---

## Architect Review Gate

**Before P0.7.1 code starts, confirm:**

1. [ ] Field list is complete (no `_active_sessions[pid]["X"]` access in pipeline.py uses a key not listed here)
2. [ ] `VoiceEvidence` sub-record correctly captures all `identity_evidence` sub-fields
3. [ ] All 9 cross-field invariants (I01–I09) are covered by the named mutation methods above
4. [ ] `SessionStore` mutation list covers all 72 write sites from the grep audit
5. [ ] `prior_person_type` fail-closed default of `"stranger"` is explicitly encoded in `transition_to_disputed()`
6. [ ] `recent_attributions` and `recent_voice_confs` handled as list-with-maxlen (not raw deque) in `Session` dataclass
7. [ ] `kairos_clock_reset` latch pattern (I08) is encoded as `consume_kairos_reset()` method
8. [ ] `voice_face_confirmed` compat shim retained in `Session` (needed by lines 7416, 6502, 7508 until P0.7.5)
9. [ ] `waiting_for_name` absent-vs-False semantics preserved (`Session.waiting_for_name: bool = False` is equivalent to absent→False in legacy code)

---

*This document was authored from a grep audit of pipeline.py as of 2026-05-09.
It must be re-verified against the live source before P0.7.1 implementation begins.*
