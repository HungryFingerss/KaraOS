# P0.6.2 — TrackStore Inventory

**Store:** `TrackStore` in `core/track_store.py`
**Globals migrated:** `_unrecognized_tracks`, `_stranger_track_map`, `_track_identity`, `_unrecognized_embeddings`
**Sub-PR:** P0.6.2 (alongside PresenceStore)

---

## Design Rationale

These four globals are all keyed by **SORT track_id** (int), not person_id. They represent per-track state in the vision pipeline:
- `_unrecognized_tracks`: tracks that have no identity yet (track_id → last_seen_ts)
- `_stranger_track_map`: mapping from an unrecognized track to its assigned stranger-pid (track_id → stranger_pid)
- `_track_identity`: mapping from a recognized track to its confirmed person_id (track_id → person_id)
- `_unrecognized_embeddings`: the face embedding captured for an unrecognized track (track_id → embedding bytes)

Collapsing them into `TrackEntry` eliminates the cross-dict invariant burden ("if track in `_unrecognized_tracks` then also in `_unrecognized_embeddings`").

---

## Fields

| Field | Type | Default | Lifecycle |
|---|---|---|---|
| `track_id` | `int` | required | track-scoped — key of the entry |
| `first_seen_at` | `float` | `0.0` | track-scoped |
| `last_seen_at` | `float` | `0.0` | track-scoped — updated each scan pass |
| `stranger_pid` | `str \| None` | `None` | track-scoped — set when stranger mint fires |
| `bound_identity` | `str \| None` | `None` | track-scoped — set when recognition confirms a person_id |
| `embedding` | `bytes \| None` | `None` | track-scoped — face embedding for progressive enrollment |

**Dict key:** `track_id` (int) — SORT tracker output.

**Lifecycle note:** All TrackStore entries are track-scoped. They are created when a new track appears, updated each recognition scan, and removed when:
1. The track leaves the frame (background vision loop prunes to `_active_tids`)
2. Session close removes entries bound to that session's person_id
3. SCENE_STALE_SECS age-out removes old entries

---

## Module-level Declarations

```
L846: _unrecognized_tracks:      dict = {}
L847: _unrecognized_embeddings:  dict = {}
L848: _stranger_track_map:       dict = {}
L849: _track_identity:           dict = {}
```

---

## Write Sites

### `_unrecognized_tracks`

| Line | Function | Mutation shape | Snippet |
|---|---|---|---|
| L846 | module-level | init/declaration | `_unrecognized_tracks: dict = {}` |
| L2825 | `_background_vision_loop` | dict-comprehension reassignment (prune to live tracks) | `_unrecognized_tracks = {tid: ts for tid, ts in _unrecognized_tracks.items() if _bv_scan_now - ts < SCENE_STALE_SECS}` |
| L2926 | `_background_vision_loop` | key-set `[k]=v` | `_unrecognized_tracks[_tid] = _bv_scan_now` |

### `_stranger_track_map`

| Line | Function | Mutation shape | Snippet |
|---|---|---|---|
| L848 | module-level | init/declaration | `_stranger_track_map: dict = {}` |
| L2356 | `_close_session` | dict-comprehension reassignment (drop closing session's bindings) | `_stranger_track_map = {tid: pid for tid, pid in _stranger_track_map.items() if pid != person_id}` |
| L2833 | `_background_vision_loop` | dict-comprehension reassignment (prune to live tracks) | `_stranger_track_map = {tid: pid for tid, pid in _stranger_track_map.items() if tid in _unrecognized_tracks}` |
| L2931 | `_background_vision_loop` | key-set `[k]=v` (new stranger mint) | `_stranger_track_map[_tid] = f"stranger_{uuid4().hex[:8]}"` |
| L7385 | `run` (new_stranger branch) | key-set `[k]=v` | `_stranger_track_map[_speaker_track] = _sid` |

### `_track_identity`

| Line | Function | Mutation shape | Snippet |
|---|---|---|---|
| L849 | module-level | init/declaration | `_track_identity: dict = {}` |
| L2366 | `_close_session` | dict-comprehension reassignment (drop closing session's bindings) | `_track_identity = {tid: pid for tid, pid in _track_identity.items() if pid != person_id}` |
| L2838 | `_background_vision_loop` | dict-comprehension reassignment (prune to active tids) | `_track_identity = {tid: pid for tid, pid in _track_identity.items() if tid in _active_tids}` |
| L2869 | `_background_vision_loop` | key-set `[k]=v` | `_track_identity[_det.track_id] = _pid2` |
| L6412 | `run` (primary face loop) | key-set `[k]=v` | `_track_identity[det.track_id] = person_id` |

### `_unrecognized_embeddings`

| Line | Function | Mutation shape | Snippet |
|---|---|---|---|
| L847 | module-level | init/declaration | `_unrecognized_embeddings: dict = {}` |
| L2361 | `_close_session` | dict-comprehension reassignment (prune to live tracks) | `_unrecognized_embeddings = {tid: emb for tid, emb in _unrecognized_embeddings.items() if tid in _stranger_track_map}` |
| L2829 | `_background_vision_loop` | dict-comprehension reassignment (prune to live tracks) | `_unrecognized_embeddings = {tid: emb for tid, emb in _unrecognized_embeddings.items() if tid in _unrecognized_tracks}` |
| L2927 | `_background_vision_loop` | key-set `[k]=v` | `_unrecognized_embeddings[_tid] = _emb2` |

**Required mutation methods:**
- `async mark_unrecognized(track_id, ts)` — adds/updates `_unrecognized_tracks`
- `async mint_stranger(track_id, stranger_pid)` — sets `stranger_pid` and `_stranger_track_map`
- `async bind_identity(track_id, person_id)` — sets `bound_identity` and `_track_identity`
- `async set_embedding(track_id, embedding)` — stores face embedding
- `async remove_track(track_id)` — removes one track entry
- `async prune_stale(before_ts)` — removes entries older than ts (replaces unrecognized-tracks prune)
- `async prune_for_session_close(person_id)` — removes entries bound to a closing session's person_id (replaces all 3 dict-comprehension reassignments in `_close_session`)
- `async prune_to_active_tids(active_tids)` — removes entries not in active_tids set (replaces `_track_identity` prune in background loop)
- `def reset()` — clears all entries

---

## Read Sites

### `_unrecognized_tracks`

| Line | Function | Access pattern |
|---|---|---|
| L2826 | `_background_vision_loop` | iteration source for prune |
| L2831 | `_background_vision_loop` | `if tid in _unrecognized_tracks` membership (guards `_unrecognized_embeddings` prune) |
| L2835 | `_background_vision_loop` | `if tid in _unrecognized_tracks` membership (guards `_stranger_track_map` prune) |
| L2845 | `_background_vision_loop` | positional to `_should_run_recognition` |
| L3041 | `_background_vision_loop` | `.values()` iteration for count |
| L3162 | `_kairos_tick` | positional arg |
| L5124 | `conversation_turn` | positional arg |
| L7195 | `run` | positional to `_resolve_actual_speaker` |
| L7258 | `run` | `unrecognized_tracks=...` kwarg to `_build_routing_inputs` |
| L7345 | `run` (new_stranger) | `.items()` iteration |

### `_stranger_track_map`

| Line | Function | Access pattern |
|---|---|---|
| L2357 | `_close_session` | iteration source — `_stranger_track_map.items()` |
| L2363 | `_close_session` | `if tid in _stranger_track_map` membership |
| L2834 | `_background_vision_loop` | iteration source for prune |
| L2929 | `_background_vision_loop` | `_tid not in _stranger_track_map` membership |
| L7357 | `run` (new_stranger) | `.get(_speaker_track)` |
| L7589 | `run` (progressive enroll gate) | `.items()` iteration to find track for pid |

### `_track_identity`

| Line | Function | Access pattern |
|---|---|---|
| L2367 | `_close_session` | iteration source |
| L2839 | `_background_vision_loop` | iteration source for prune |
| L2845 | `_background_vision_loop` | positional to `_should_run_recognition` |
| L6424 | `run` | `.get(det.track_id)` |

### `_unrecognized_embeddings`

| Line | Function | Access pattern |
|---|---|---|
| L2362 | `_close_session` | iteration source |
| L2830 | `_background_vision_loop` | iteration source for prune |
| L7591 | `run` (progressive enroll gate) | `if _gate_track is not None and _gate_track in _unrecognized_embeddings:` |
| L7592 | `run` | `_gate_emb = _unrecognized_embeddings[_gate_track]` |

**Required peek methods:**
- `peek_snapshot(track_id) → TrackSnapshot | None`
- `peek_all_track_ids() → frozenset[int]` — for active-tids membership checks
- `peek_stranger_pid(track_id) → str | None` — fast accessor
- `peek_identity(track_id) → str | None` — fast accessor (replaces `_track_identity.get`)
- `peek_embedding(track_id) → bytes | None` — fast accessor
- `peek_tracks_for_person(person_id) → tuple[int, ...]` — for `_close_session` and progressive enroll (replaces `.items()` iteration)
- `peek_unrecognized_count() → int` — replaces `len(...)` counting

---

## Cleanup-path Sites

| Line | Function | Context | Snippet |
|---|---|---|---|
| L2356 | `_close_session` | session-close, stranger_track_map — drop bindings for closing pid | `_stranger_track_map = {tid: pid ... if pid != person_id}` |
| L2361 | `_close_session` | session-close, embeddings — prune to stranger_track_map survivors | `_unrecognized_embeddings = {tid: emb ... if tid in _stranger_track_map}` |
| L2363 | `_close_session` | session-close, embeddings read + prune | `if tid in _stranger_track_map` |
| L2366 | `_close_session` | session-close, track_identity — drop bindings for closing pid | `_track_identity = {tid: pid ... if pid != person_id}` |
| L2825 | `_background_vision_loop` | SCENE_STALE_SECS age-out for unrecognized_tracks | dict-comprehension reassignment |
| L2829 | `_background_vision_loop` | prune embeddings to live unrecognized_tracks | dict-comprehension reassignment |
| L2833 | `_background_vision_loop` | prune stranger_track_map to live unrecognized_tracks | dict-comprehension reassignment |
| L2838 | `_background_vision_loop` | prune track_identity to active tids | dict-comprehension reassignment |

**CRITICAL:** Three independent cleanup paths:
1. `_close_session` — per-session prune of all tracks bound to the closing person_id
2. Background loop per-scan SCENE_STALE_SECS age-out
3. Background loop active-tids prune (tracks that left frame)

All three must be preserved as separate named methods on `TrackStore`.

---

## Cross-field Invariants

- If a track has `embedding != None`, it should also have `stranger_pid != None` (an embedding is only captured for recognized-stranger tracks). Exception: the `_close_session` prune deletes `stranger_track_map` entries first, then uses that map as a filter for `_unrecognized_embeddings`. The unified `TrackEntry` collapses this invariant — if `stranger_pid` is cleared, `embedding` can be cleared atomically in the same operation.
- `bound_identity != None` and `stranger_pid != None` should be mutually exclusive for a given track (once identity is confirmed, the track moves from stranger to recognized). This invariant was implicit in the original design where `_track_identity` and `_stranger_track_map` were separate dicts.
- `_unrecognized_tracks` membership was the filter for `_unrecognized_embeddings` prune (L2831) and `_stranger_track_map` prune (L2835). In `TrackEntry`, these are co-located — no cross-dict membership check needed.

---

## Mutation Shapes Summary

| Shape | Count | Notes |
|---|---|---|
| key-set `[k]=v` | 6 | L2926, L2927, L2931, L2869, L6412, L7385 |
| dict-comprehension reassignment (prune) | 6 | L2825, L2829, L2833, L2838, L2356, L2366 |
| dict-comprehension reassignment (`_close_session`) | 3 | L2356 (stranger_map), L2361 (embeddings), L2366 (track_identity) |

All "prune via dict-comprehension reassignment" shapes map to named prune methods on `TrackStore`.

---

## Lifecycle Phase

1. **Entry created:** `mark_unrecognized(track_id, ts)` when a new track appears with no identity (background vision loop).
2. **Stranger assigned:** `mint_stranger(track_id, stranger_pid)` when the background loop assigns a stranger-pid to a new unrecognized track.
3. **Embedding stored:** `set_embedding(track_id, embedding)` after face embedding is captured.
4. **Identity confirmed:** `bind_identity(track_id, person_id)` when recognition succeeds (background loop or primary face loop in `run`).
5. **Entry pruned (per-session close):** `prune_for_session_close(person_id)` removes all tracks bound to the closing session.
6. **Entry pruned (age-out):** `prune_stale(before_ts)` removes entries older than threshold.
7. **Entry pruned (left frame):** `prune_to_active_tids(active_tids)` removes entries not in current frame.
