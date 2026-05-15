# P0.6.6 — PipelineStateStore Inventory

**Store:** `PipelineStateStore` in `core/pipeline_state_store.py`
**Globals migrated:** `_active_system_name`, `_detected_lang`, `_pipeline_state`, `_active_room_session`, `_active_room_started_at`, `_active_room_participants`, `_cloud_state`, `_cloud_monitor_task`, `_cloud_failed_at`, `_cloud_recovered`, `_last_face_seen`, `_last_user_speech_at`, `_last_kairos_at`, `_last_silent_update`
**Sub-PR:** P0.6.6

---

## Fields

| Field | Type | Default | Lifecycle |
|---|---|---|---|
| `active_system_name` | `str` | `DEFAULT_SYSTEM_NAME` | persistent (pipeline-level) |
| `detected_lang` | `str` | `"en"` | persistent; reset to `"en"` on all-sessions-closed and factory reset |
| `pipeline_state` | `PipelineState` | `PipelineState.WATCHING` | state-machine (only mutated via `_set_state()`) |
| `active_room_session` | `str \| None` | `None` | room-scoped — minted on first person entry, cleared on last leave |
| `active_room_started_at` | `float \| None` | `None` | room-scoped — paired with `active_room_session` |
| `active_room_participants` | `set[str]` | `set()` | room-scoped — cleared atomically with room session close |
| `cloud_state` | `CloudState` | `CloudState.ONLINE` | state-machine |
| `cloud_monitor_task` | `asyncio.Task \| None` | `None` | task handle — spawned when SICK, cancelled on shutdown |
| `cloud_failed_at` | `float` | `0.0` | timestamp companion to `cloud_state == SICK` |
| `cloud_recovered` | `bool` | `False` | one-shot flag — set on recovery, consumed (cleared) once |
| `last_face_seen` | `float` | `0.0` | monotonically advancing timestamp |
| `last_user_speech_at` | `float` | `0.0` | KAIROS clock — reset on user speech |
| `last_kairos_at` | `float` | `0.0` | KAIROS cooldown — reset on kairos tick |
| `last_silent_update` | `float` | `0.0` | throttle — reset by `_maybe_record_silent_obs` |

---

## Module-level Declarations

```
L769: _active_system_name: str = DEFAULT_SYSTEM_NAME
L828: _detected_lang:      str                   = "en"
L795: _pipeline_state:     PipelineState         = PipelineState.WATCHING
L807: _active_room_session: "str | None" = None
L812: _active_room_started_at: "float | None" = None
L818: _active_room_participants: "set[str]" = set()
L761: _cloud_state:         CloudState        = CloudState.ONLINE
L764: _cloud_monitor_task:  asyncio.Task | None = None
L762: _cloud_failed_at:     float             = 0.0
L763: _cloud_recovered:     bool              = False
L829: _last_face_seen:     float                 = 0.0
L840: _last_user_speech_at:   float                       = 0.0
L845: _last_kairos_at:        float                       = 0.0
L841: _last_silent_update:    float                       = 0.0
```

---

## Write Sites with Bucket Categorization

**(a) read-only** — not a write
**(b) scalar-write** — unconditional assignment, no guard on current value
**(c) state-machine-transition** — conditional assignment that inspects the current value before writing

### `_active_system_name`

| Line | Function | Category | Snippet |
|---|---|---|---|
| L769 | module-level | (b) | `_active_system_name: str = DEFAULT_SYSTEM_NAME` |
| L4262 | `_execute_tool` (update_system_name) | **(c)** — guarded by `if new_name.lower() != _active_system_name.lower():` at L4261 | `_active_system_name = new_name` |
| L6082 | `run` (boot, invalid name) | **(c)** — inside `if _loaded_name.lower() in _INVALID_SYSTEM_NAMES:` | `_active_system_name = DEFAULT_SYSTEM_NAME` |
| L6084 | `run` (boot, valid name) | (b) — else branch, simple assignment | `_active_system_name = _loaded_name` |
| L6284 | `run` (factory reset) | (b) — cleanup reset | `_active_system_name = DEFAULT_SYSTEM_NAME` |

### `_detected_lang`

| Line | Function | Category | Snippet |
|---|---|---|---|
| L828 | module-level | (b) | `_detected_lang: str = "en"` |
| L2540 | `_expire_stale_sessions` (all sessions closed) | (b) — cleanup reset | `_detected_lang = "en"` |
| L6285 | `run` (factory reset) | (b) — cleanup reset | `_detected_lang = "en"` |

Note: `_detected_lang` has no write site that updates it to anything other than `"en"` in the current pipeline. The write at L2540 resets it to default when sessions expire. This suggests the detected-language feature may be disabled or incomplete. No (c) transition for this field.

### `_pipeline_state`

| Line | Function | Category | Snippet |
|---|---|---|---|
| L795 | module-level | (b) | `_pipeline_state: PipelineState = PipelineState.WATCHING` |
| L863 | `_set_state` | **(c)** — guarded by `if new_state == _pipeline_state: return` at L860 (idempotence check) | `_pipeline_state = new_state` |

All `_pipeline_state` mutations go through `_set_state(new_state)`. The idempotence check (L860) is a classic state-machine guard — must be preserved in `transition_pipeline_state`.

### `_active_room_session` + `_active_room_started_at` + `_active_room_participants` (atomic trio)

These three fields are always mutated together. They constitute a single room-lifecycle state machine:

| Line | Function | Category | Snippet |
|---|---|---|---|
| L807 | module-level | (b) | `_active_room_session: "str | None" = None` |
| L812 | module-level | (b) | `_active_room_started_at: "float | None" = None` |
| L818 | module-level | (b) | `_active_room_participants: "set[str]" = set()` |
| L2113 | `_open_session` (first-into-empty-room) | **(c)** — guarded by `if _active_room_session is None:` at L2111 (only mints when no room is live) | `_active_room_session = f"room_{int(now)}_{uuid4().hex[:6]}"` |
| L2117 | `_open_session` (first-into-empty-room) | **(c)** — same guard as L2113 | `_active_room_started_at = now` |
| L2119 | `_open_session` (first-into-empty-room) | **(c)** — same guard as L2113 | `_active_room_participants = set()` |
| L2129 | `_open_session` (any participant join) | (b) — `.add()` mutation | `_active_room_participants.add(person_id)` |
| L2397 | `_close_session` (last-leave) | **(c)** — guarded by `if not _session_store.peek_all_snapshots() and _active_room_session is not None:` at L2393 | `_active_room_session = None` |
| L2400 | `_close_session` (last-leave) | **(c)** — same guard as L2397 | `_active_room_started_at = None` |
| L2403 | `_close_session` (last-leave) | **(c)** — same guard as L2397 | `_active_room_participants = set()` |

**Required atomic operations:**
- `async start_room_session(room_id, now)` — sets all three fields atomically under lock (minting case)
- `async end_room_session()` — clears all three fields atomically under lock
- `async add_room_participant(pid)` — adds to participants set
- `async remove_room_participant(pid)` — discards from participants set (not currently used as a standalone op but needed for completeness)

All three fields MUST be mutated under a single lock acquisition to preserve atomicity — the end-of-room synthesis in `_close_session` captures all three values (L2394–L2396) before clearing them. A multi-step mutation without a lock would create a TOCTOU hazard.

### `_cloud_state`, `_cloud_failed_at`, `_cloud_monitor_task` (cloud state machine)

These three fields constitute the cloud state machine. They are mutated in coordinated groups:

| Line | Function | Category | Snippet |
|---|---|---|---|
| L761 | module-level | (b) | `_cloud_state: CloudState = CloudState.ONLINE` |
| L762 | module-level | (b) | `_cloud_failed_at: float = 0.0` |
| L764 | module-level | (b) | `_cloud_monitor_task: asyncio.Task | None = None` |
| L3102 | `_cloud_retry_loop` (recovery) | **(c)** — conditional on `available` from ping result (guarded by loop structure: `if _cloud_state == CloudState.ONLINE: continue` at L3095 short-circuits the loop when already ONLINE) | `_cloud_state = CloudState.ONLINE` |
| L5202 | `conversation_turn` (SICK→ONLINE mid-conversation) | **(c)** — inside `if _cloud_state == CloudState.SICK:` branch | `_cloud_state = CloudState.ONLINE` |
| L5209 | `conversation_turn` (SICK→OFFLINE timeout) | **(c)** — inside `elif elapsed >= CLOUD_OFFLINE_TIMEOUT:` (guards against premature OFFLINE) | `_cloud_state = CloudState.OFFLINE` |
| L5487 | `conversation_turn` (ONLINE→SICK on exception) | **(c)** — exception handler on ONLINE stream path (implicit guard: only reachable from ONLINE branch) | `_cloud_state = CloudState.SICK` |
| L5488 | `conversation_turn` (ONLINE→SICK) | (b) — timestamp set unconditionally on SICK transition | `_cloud_failed_at = time.time()` |
| L5210 | `conversation_turn` (spawn retry task) | **(c)** — guarded by `if _cloud_monitor_task is None or _cloud_monitor_task.done():` | `_cloud_monitor_task = asyncio.create_task(_cloud_retry_loop())` |
| L5489 | `conversation_turn` (spawn retry task) | **(c)** — same guard | `_cloud_monitor_task = asyncio.create_task(_cloud_retry_loop())` |
| L5490 | `conversation_turn` | **(c)** — same guard, paired with ONLINE→SICK | `_cloud_monitor_task = asyncio.create_task(_cloud_retry_loop())` |

**Required atomic methods for cloud state machine:**
- `async transition_cloud_to_online()` — sets `cloud_state = ONLINE`, sets `cloud_recovered = True` if prior != ONLINE. Must capture prior state BEFORE write (B1 fix).
- `async transition_cloud_to_sick(now=None)` — sets `cloud_state = SICK`, sets `cloud_failed_at`. Must refresh `cloud_failed_at` unconditionally (SICK→SICK refreshes timestamp — P2 note).
- `async transition_cloud_to_offline()` — sets `cloud_state = OFFLINE`.
- `async ensure_cloud_monitor_task()` — spawns `_cloud_retry_loop()` task if None or done. Returns the task. The caller must call `asyncio.create_task()` — the Store holds the handle.

Note: `_cloud_monitor_task` is an asyncio.Task handle, not a data value. The Store owns the reference; the shutdown `finally:` block at L7714–L7717 cancels and awaits it. The Store should expose `get_cloud_monitor_task() → asyncio.Task | None` and `set_cloud_monitor_task(task)` for this lifecycle.

### `_cloud_recovered`

| Line | Function | Category | Snippet |
|---|---|---|---|
| L763 | module-level | (b) | `_cloud_recovered: bool = False` |
| L3103 | `_cloud_retry_loop` (recovery) | **(c)** — only fires when `available` returned True (paired with ONLINE transition) | `_cloud_recovered = True` |
| L6907 | `run` (consume recovery flag) | **(c)** — guarded by `if _cloud_recovered:` at L6906 (one-shot flag pattern) | `_cloud_recovered = False` |

The `cloud_recovered` flag is a one-shot: set by recovery, cleared exactly once by the consumer. Must be preserved as an atomic read-and-clear operation: `async consume_cloud_recovered() → bool` — returns current value and sets to False atomically under lock. This prevents the TOCTOU hazard where a second consumer sees `True` between the read and the clear.

### `_last_face_seen`

| Line | Function | Category | Snippet |
|---|---|---|---|
| L829 | module-level | (b) | `_last_face_seen: float = 0.0` |
| L2751 | `_background_vision_loop` (ambient, no active sessions) | (b) — unconditional timestamp advance | `_last_face_seen = time.time()` |
| L6286 | `run` (factory reset) | (b) — cleanup reset | `_last_face_seen = 0.0` |
| L6692 | `run` (ambient timer, no active sessions) | (b) — unconditional timestamp advance | `_last_face_seen = time.time()` |
| L6698 | `run` (active session, face belongs to session) | **(c)** — guarded by `if _d.person_id and _session_store.peek_snapshot(_d.person_id) is not None:` | `_last_face_seen = time.time()` |

### `_last_user_speech_at`

| Line | Function | Category | Snippet |
|---|---|---|---|
| L840 | module-level | (b) | `_last_user_speech_at: float = 0.0` |
| L6039 | `run` (boot init) | (b) — unconditional reset to now | `_last_user_speech_at = time.time()` |
| L6858 | `run` (kairos_clock_reset) | **(c)** — guarded by `if _kcr_snap is not None and _kcr_snap.kairos_clock_reset:` | `_last_user_speech_at = time.time()` |
| L6916 | `run` (after ambient text consumed) | (b) — unconditional KAIROS reset | `_last_user_speech_at = time.time()` |
| L6960 | `run` (after main listen returns text) | (b) — unconditional KAIROS reset | `_last_user_speech_at = time.time()` |

### `_last_kairos_at`

| Line | Function | Category | Snippet |
|---|---|---|---|
| L845 | module-level | (b) | `_last_kairos_at: float = 0.0` |
| L3251 | `_kairos_tick` (brain chose silence) | (b) — advance cooldown even on silent path | `_last_kairos_at = time.time()` |
| L3286 | `_kairos_tick` (brain spoke) | (b) — advance cooldown on speak | `_last_kairos_at = time.time()` |
| L6040 | `run` (boot init) | (b) — unconditional init to now | `_last_kairos_at = time.time()` |

### `_last_silent_update`

| Line | Function | Category | Snippet |
|---|---|---|---|
| L841 | module-level | (b) | `_last_silent_update: float = 0.0` |
| L790 | `_maybe_record_silent_obs` | (b) — throttle timestamp update | `_last_silent_update = time.time()` |
| L6178 | `run` (boot reinit) | (b) — cleanup/init reset | `_last_silent_update = 0.0` |

---

## Read Sites

| Line | Function | Field read | Access pattern |
|---|---|---|---|
| L788 | `_maybe_record_silent_obs` | `last_silent_update` | `if time.time() - _last_silent_update < 5.0:` throttle guard |
| L860 | `_set_state` | `pipeline_state` | `if new_state == _pipeline_state:` idempotence check |
| L862 | `_set_state` | `pipeline_state` | `print(f"... {_pipeline_state.name} -> ...")` |
| L2111 | `_open_session` | `active_room_session` | `if _active_room_session is None:` room-mint guard |
| L2120 | `_open_session` | `active_room_session` | log — `print(f"... {_active_room_session}")` |
| L2121 | `_open_session` | `active_room_session` | `_current_room_session = _active_room_session` local snapshot |
| L2128 | `_open_session` | `active_room_participants` | `_was_new = person_id not in _active_room_participants` |
| L2134 | `_open_session` | `active_room_participants` | `len(_active_room_participants)` |
| L2393 | `_close_session` | `active_room_session` | end-of-room guard `... _active_room_session is not None:` |
| L2394 | `_close_session` | `active_room_session` | `_ended_room = _active_room_session` local snapshot |
| L2395 | `_close_session` | `active_room_started_at` | `_ended_started_at = _active_room_started_at` local snapshot |
| L2396 | `_close_session` | `active_room_participants` | `_ended_participants = list(_active_room_participants)` local snapshot |
| L2427 | `_expire_stale_sessions` | `detected_lang` | `global _vision_prev_det_count, _detected_lang` (declaration) |
| L3087 | `_cloud_retry_loop` | `cloud_state`, `cloud_recovered` | `global _cloud_state, _cloud_recovered` (declaration) |
| L3095 | `_cloud_retry_loop` | `cloud_state` | `if _cloud_state == CloudState.ONLINE:` guard |
| L3106 | `_cloud_retry_loop` | `cloud_failed_at` | `elif _cloud_failed_at and _brain_orchestrator:` |
| L3107 | `_cloud_retry_loop` | `cloud_failed_at` | `time.time() - _cloud_failed_at` elapsed |
| L3119 | `_kairos_tick` | `last_kairos_at` | `global _last_kairos_at` (declaration) |
| L3132 | `_kairos_tick` | `last_user_speech_at` | `_silence_elapsed = now - _last_user_speech_at` |
| L3133 | `_kairos_tick` | `last_kairos_at` | `_cooldown_elapsed = now - _last_kairos_at` |
| L3170 | `_kairos_tick` | `last_face_seen` | `"face_in_frame": time.time() - _last_face_seen < 2.0` |
| L3208 | `_kairos_tick` | `active_system_name` | `system_name=_active_system_name` kwarg |
| L3230 | `_kairos_tick` | `detected_lang` | `language=_detected_lang` kwarg |
| L3234 | `_kairos_tick` | `active_room_session` | `room_search_fn=_make_room_search_fn(_active_room_session, ...)` |
| L3194 | `_kairos_tick` | `active_room_started_at` | positional to `_build_room_block` |
| L3443 | (sensors block) | `cloud_state` | `cloud_state=_cloud_state` kwarg |
| L4261 | `_execute_tool` (update_system_name guard) | `active_system_name` | `if new_name.lower() != _active_system_name.lower():` |
| L4283 | `_execute_tool` (no-op log) | `active_system_name` | `'{_active_system_name}'` |
| L5184 | `conversation_turn` | `cloud_state` | `if _cloud_state == CloudState.SICK:` branch |
| L5206 | `conversation_turn` | `cloud_failed_at` | `elapsed = time.time() - _cloud_failed_at` |
| L5210 | `conversation_turn` | `cloud_monitor_task` | `if _cloud_monitor_task is None or _cloud_monitor_task.done():` |
| L5240 | `conversation_turn` | `cloud_state` | `elif _cloud_state == CloudState.OFFLINE:` |
| L5271 | `conversation_turn` | `active_system_name` | `system_name=_active_system_name` kwarg |
| L5433 | `conversation_turn` | `cloud_state` | `and not tool_calls and _cloud_state == CloudState.ONLINE` |
| L5489 | `conversation_turn` | `cloud_monitor_task` | task-done guard |
| L5694 | `conversation_turn` | `cloud_state` | `if _cloud_state == CloudState.ONLINE:` routing |
| L5957 | `conversation_turn` | `detected_lang` | `language=_detected_lang` kwarg |
| L6085–6086 | `run` | `active_system_name` | boot log checks |
| L6127 | `run` | `active_system_name` | `_brain_orchestrator.set_system_name(...)` |
| L6466 | `run` | `pipeline_state` | `if _pipeline_state == PipelineState.WATCHING:` |
| L6668 | `run` | `last_face_seen` | `grace_expired = time.time() - _last_face_seen > FACE_LOSS_GRACE` |
| L6669 | `run` | `pipeline_state` | state check for unknown sighting |
| L6706 | `run` | `pipeline_state` | `if _pipeline_state == PipelineState.WATCHING and ...` |
| L6742 | `run` | `pipeline_state` | ambient listen gate |
| L6769 | `run` | `active_system_name` | `_name_heard_in(_ambient_text, _active_system_name)` |
| L6826 | `run` | `pipeline_state` | conversation loop gate |
| L6906 | `run` | `cloud_recovered` | `if _cloud_recovered:` one-shot flag read |
| L7303 | `run` | (switch_enrolled) | multiple fields read for context |
| L7525 | `run` | `last_face_seen` | `"face_in_frame": time.time() - _last_face_seen < 2.0` |
| L7544 | `run` | `active_room_session`, `active_room_started_at` | `_build_room_block` args |
| L7563 | `run` | `active_system_name` | `_name_heard_in(text, _active_system_name)` G4 gate |
| L7631 | `run` | `active_system_name` | gate-blocked log |
| L7714–7717 | `run` (shutdown finally) | `cloud_monitor_task` | `.cancel()` + `await asyncio.wait_for(...)` |

**Required peek methods:**
- `peek_snapshot() → PipelineRuntimeSnapshot` — immutable snapshot of all fields (used for multi-field reads)
- `peek_latest_frame() → np.ndarray | None` — live ref (not in snapshot — see spec)
- `get_cloud_monitor_task() → asyncio.Task | None` — live task handle for shutdown finally

---

## Cleanup-path Sites

| Line | Function | Context | Snippet |
|---|---|---|---|
| L2397–L2403 | `_close_session` (last leave) | room-end (guarded state-machine transition) | `_active_room_session = None`, `_active_room_started_at = None`, `_active_room_participants = set()` |
| L2540 | `_expire_stale_sessions` | all-sessions-closed reset | `_detected_lang = "en"` |
| L6284–L6286 | `run` (factory reset) | factory reset | `_active_system_name = DEFAULT_SYSTEM_NAME`, `_detected_lang = "en"`, `_last_face_seen = 0.0` |
| L6907 | `run` | one-shot flag consumption | `_cloud_recovered = False` |
| L7714–L7717 | `run` (shutdown `finally:`) | graceful shutdown — cancel cloud retry loop | `_cloud_monitor_task.cancel()` + `await asyncio.wait_for(...)` |

---

## Cross-field Invariants

1. **Room session atomic trio:** `active_room_session`, `active_room_started_at`, `active_room_participants` must always be mutated atomically. When `active_room_session is not None`, `active_room_started_at` must also be non-None, and `active_room_participants` must be the current participant set. These three are never partially-valid — they form a unit.

2. **Cloud state + failed_at:** When `cloud_state == SICK`, `cloud_failed_at` must be non-zero (set in the same transition). `transition_cloud_to_sick()` must set both atomically.

3. **Cloud state + recovered:** When `cloud_state` transitions from non-ONLINE to ONLINE, `cloud_recovered` must be set to True atomically. The B1 bug was: capturing prior state AFTER the assignment broke recovery detection. Fix: `prior = self._state.cloud_state; self._state.cloud_state = new_state; if new_state is ONLINE and prior is not ONLINE: self._state.cloud_recovered = True`.

4. **cloud_monitor_task lifecycle:** The retry task is spawned when `cloud_state` transitions to SICK or OFFLINE. It is NOT spawned when it is already running (`is None or .done()` guard). It is cancelled only on shutdown (the `finally:` block in `run`). The Store must hold the task reference across the `conversation_turn` → `_cloud_retry_loop` lifecycle.

5. **pipeline_state idempotence:** `transition_pipeline_state(new_state)` must be a no-op if `new_state == current state`. This is the `_set_state()` guard at L860 — must be preserved in the mutation method.

---

## Mutation Shapes Summary

| Field | Category | Count |
|---|---|---|
| `active_system_name` | (b) scalar-write | 3 |
| `active_system_name` | (c) state-machine | 2 |
| `detected_lang` | (b) scalar-write | 3 |
| `pipeline_state` | (c) state-machine | 1 (via `_set_state`) |
| `active_room_session` | (c) state-machine | 2 (mint + clear) |
| `active_room_started_at` | (c) state-machine | 2 (mint + clear) |
| `active_room_participants` | (c) state-machine + (b) | 3 |
| `cloud_state` | (c) state-machine | 5 |
| `cloud_failed_at` | (b) scalar-write | 1 (paired with SICK transition) |
| `cloud_monitor_task` | (c) state-machine | 2 (spawn-if-done) |
| `cloud_recovered` | (c) state-machine | 2 (set + consume) |
| `last_face_seen` | (b) scalar-write + (c) one | 4 |
| `last_user_speech_at` | (b) + (c) | 4 |
| `last_kairos_at` | (b) scalar-write | 3 |
| `last_silent_update` | (b) scalar-write | 2 |

Total (c) state-machine-transition sites: **~17** — all require individual architect review before sub-PR P0.6.6 closes.

---

## Lifecycle Phase

1. **Initialized:** All fields initialized at module level to defaults at pipeline start.
2. **Runtime mutations:** Each field is updated during normal pipeline operation (per frame, per turn, per tick, per session event).
3. **Room session lifecycle:** `start_room_session` + `end_room_session` are atomic operations managing the trio.
4. **Cloud state machine lifecycle:** Transitions via `transition_cloud_to_*` methods; monitor task spawned/cancelled.
5. **Factory reset:** `reset()` returns all fields to initial defaults. Cancels cloud monitor task if live.
6. **Shutdown:** `peek_snapshot().cloud_monitor_task` (or `get_cloud_monitor_task()`) allows the shutdown `finally:` block to cancel the retry loop.
