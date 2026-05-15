# P0.6.2 — PresenceStore Inventory

**Store:** `PresenceStore` in `core/presence_store.py`
**Globals migrated:** `_persons_in_frame`
**Sub-PR:** P0.6.2 (alongside TrackStore)

---

## Fields

| Field | Type | Default | Lifecycle |
|---|---|---|---|
| `name` | `str` | `""` | session-scoped — cleared on `remove(pid)` at session close |
| `last_seen` | `float` | `0.0` | session-scoped |
| `last_recognized_at` | `float` | `0.0` | session-scoped |
| `conf` | `float` | `0.0` | session-scoped |
| `source` | `Literal["face", "voice", ""]` | `""` | session-scoped |

**Dict key:** `person_id` (str) — same as `SessionStore` key.

**Lifecycle note:** `PresenceStore` entries are session-scoped — created/updated when a person is recognized by face or voice, removed on `_close_session`. They are also age-pruned (after `SCENE_STALE_SECS`) by the background vision loop regardless of whether a session is open.

---

## Module-level Declaration

`L842: _persons_in_frame:      dict[str, dict]             = {}`

---

## Write Sites

| Line | Function | Mutation shape | Snippet |
|---|---|---|---|
| L842 | module-level | init/declaration | `_persons_in_frame: dict[str, dict] = {}` |
| L2880 | `_background_vision_loop` | dict-literal entry create | `_persons_in_frame[_pid2] = {"name": _pname2, ...}` |
| L2889 | `_background_vision_loop` | key-set `[k]=v` | `_persons_in_frame[_pid2]["last_seen"] = _bv_scan_now` |
| L2890 | `_background_vision_loop` | key-set `[k]=v` | `_persons_in_frame[_pid2]["last_recognized_at"] = _bv_scan_now` |
| L2891 | `_background_vision_loop` | key-set `[k]=v` | `_persons_in_frame[_pid2]["conf"] = _conf2` |
| L2892 | `_background_vision_loop` | key-set `[k]=v` | `_persons_in_frame[_pid2]["source"] = "face"` |
| L2903 | `_background_vision_loop` | key-set `[k]=v` | `_persons_in_frame[_pid2]["name"] = _pname2` |
| L3828 | `_execute_tool` (enrollment-mishear rename) | key-set `[k]=v` | `_persons_in_frame[person_id]["name"] = new_name` |
| L3962 | `_execute_tool` (update_person_name rename) | key-set `[k]=v` | `_persons_in_frame[person_id]["name"] = new_name` |
| L4069 | `_execute_tool` (stranger rename) | key-set `[k]=v` | `_persons_in_frame[person_id]["name"] = new_name` |
| L7010 | `run` (voice-id update) | key-set `[k]=v` | `_persons_in_frame[_v_pid]["last_seen"] = time.time()` |
| L7011 | `run` (voice-id update) | key-set `[k]=v` | `_persons_in_frame[_v_pid]["conf"] = _v_score` |
| L7017 | `run` (voice-id update) | key-set `[k]=v` | `_persons_in_frame[_v_pid]["name"] = _v_name_pif` |
| L7019 | `run` (voice-id new entry) | dict-literal entry create | `_persons_in_frame[_v_pid] = {"name": _v_name_pif, "conf": _v_score, "last_seen": ..., "last_recognized_at": ..., "source": "voice"}` |

**Required mutation methods:**
- `async upsert_face_recognition(pid, name, conf, ts)` — create or update on face recognition
- `async update_field(pid, field, value)` — field-level update (used by voice-id path for `last_seen`, `conf`, `name`)
- `async upsert_voice_recognition(pid, name, conf, ts)` — create or update on voice recognition (sets `source="voice"`)
- `async rename(pid, new_name)` — name rename from `_execute_tool` paths
- `async remove(pid)` — session-close removal
- `def reset()` — clears all entries

---

## Read Sites

| Line | Function | Access pattern |
|---|---|---|
| L393 | `_has_recent_face_evidence` | `.get(person_id)` — returns entry or None |
| L2462 | `_expire_stale_sessions` | passed to `_face_in_frame(snap.person_id, _persons_in_frame)` |
| L2809 | `_background_vision_loop` | `global _persons_in_frame, ...` declaration |
| L2846 | `_background_vision_loop` | positional arg to `_should_run_recognition` |
| L2879 | `_background_vision_loop` | `if _pid2 not in _persons_in_frame:` membership test |
| L2933 | `_background_vision_loop` | `.items()` iteration (prune pass) |
| L3007 | `_background_vision_loop` (shadow log) | `.items()` iteration |
| L3036 | `_background_vision_loop` | `.values()` iteration for name list |
| L3065 | `_background_vision_loop` (heartbeat) | `.values()` iteration for known-faces list |
| L3161 | `_kairos_tick` | positional arg to `_get_scene_block_cached` |
| L3168 | `_kairos_tick` | `.get(person_id, {}).get("conf", 0.0)` |
| L3827 | `_execute_tool` (enrollment-mishear) | `if person_id in _persons_in_frame:` membership test |
| L3961 | `_execute_tool` (update_person_name) | `if person_id in _persons_in_frame:` membership test |
| L4068 | `_execute_tool` (stranger rename) | `if person_id in _persons_in_frame:` membership test |
| L5123 | `conversation_turn` | positional arg to `_get_scene_block_cached` |
| L7009 | `run` | `if _v_pid in _persons_in_frame:` membership test |
| L7195 | `run` | positional to `_resolve_actual_speaker` |
| L7257 | `run` | `persons_in_frame=_persons_in_frame` kwarg to `_build_routing_inputs` |
| L7461 | `run` (#22 voice ext) | membership test `_cur_pid in _persons_in_frame` |
| L7462 | `run` | `.get("last_recognized_at", 0)` |
| L7486 | `run` (face_vis_acc) | membership test |
| L7487 | `run` | `time.time() - _persons_in_frame[_cur_pid].get("last_recognized_at", 0)` |
| L7499 | `run` | `.get(_cur_pid, {}).get("conf", 0.0)` |

**Required peek methods:**
- `peek_snapshot(pid) → PresenceSnapshot | None`
- `peek_all_snapshots() → tuple[PresenceSnapshot, ...]`
- `peek_pids() → tuple[str, ...]` — for membership checks
- `peek_recent_at(pid) → float` — `last_recognized_at` fast accessor
- `peek_conf(pid) → float` — `conf` fast accessor

Note: callers that pass the whole dict to helper functions (`_should_run_recognition`, `_get_scene_block_cached`, `_build_routing_inputs`, `_resolve_actual_speaker`, `_face_in_frame`) will need their signatures updated to accept `PresenceStore` or a `tuple[PresenceSnapshot, ...]` instead. This is part of the migration scope.

---

## Cleanup-path Sites

| Line | Function | Context | Snippet |
|---|---|---|---|
| L2386 | `_close_session` | session-close (called from `run` when person leaves) | `_persons_in_frame.pop(person_id, None)` |
| L2539 | `_expire_stale_sessions` | all-sessions-closed (final cleanup after expiry) | `_persons_in_frame.clear()` |
| L2954 | `_background_vision_loop` | SCENE_STALE_SECS age-out (continuous background prune) | `_persons_in_frame.pop(_stale_k, None)` |

**Important:** Two independent cleanup sources. Both must be preserved in the Store:
1. `async remove(pid)` — for `_close_session` (per-person)
2. `async prune_stale(before_ts)` — for background age-out pass (all entries older than ts)
3. `async clear()` — for `_expire_stale_sessions` final clear and factory reset

---

## Cross-field Invariants

- If `source == "face"`, `last_recognized_at` was set by the face recognition path.
- If `source == "voice"`, `last_recognized_at` was set by voice-id path.
- `conf` is the most recently observed recognition confidence regardless of source.
- There is no hard invariant between `_persons_in_frame` and `SessionStore` — a person can be in `_persons_in_frame` without an active session (they are in-frame but session hasn't been opened yet), and vice versa (session open but person left frame).

---

## Mutation Shapes Summary

| Shape | Count | Notes |
|---|---|---|
| Entry create (dict-literal) | 2 | L2880, L7019 |
| Field update `[k]["field"]=v` | 9 | L2889–2892, L2903, L7010, L7011, L7017 — collapses to `update_field` |
| Rename (`["name"] = new_name`) | 3 | L3828, L3962, L4069 — all `_execute_tool` paths |
| `.pop(pid, None)` cleanup | 2 | L2386 session-close, L2954 age-out |
| `.clear()` cleanup | 1 | L2539 all-sessions-closed |

---

## Lifecycle Phase

1. **Entry created:** When face recognition fires for a track in `_background_vision_loop` (L2880) or voice-id creates a new entry in `run` (L7019).
2. **Entry updated:** Each recognition pass updates `last_seen`, `last_recognized_at`, `conf`, `source`. Voice-id path also creates if absent.
3. **Name renamed:** `_execute_tool` rename paths mirror the SessionStore rename into `_persons_in_frame`.
4. **Entry removed (per-person):** `_close_session` pops the entry when a session closes (L2386). Age-out prune in background loop pops stale entries (L2954).
5. **All entries cleared:** `_expire_stale_sessions` clears all when no sessions remain (L2539). Factory reset clears (not yet inventoried — pattern is same as `_conversation.clear()` at L6283 area).
