# P0.6.4a — VoiceGalleryStore Inventory

**Store:** `VoiceGalleryStore` in `core/voice_gallery_store.py`
**Globals migrated:** `_voice_gallery`, `_voice_gallery_sizes`, `_ambient_wake_pending`
**Sub-PR:** P0.6.4 (alongside PerPersonAgentStore)

---

## Fields

### Per-pid entry (`VoiceGalleryEntry`)

| Field | Type | Default | Lifecycle |
|---|---|---|---|
| `profile` | `object` (numpy array / profile object) | `None` | persistent — survives session close; loaded from DB on boot, updated by `_accumulate_voice` |
| `sample_count` | `int` | `0` | persistent — monotonically increasing (updated by `_accumulate_voice`, loaded/reconciled by `_dream_loop`) |

**Dict key:** `person_id` (str).

### Store-level state

| Field | Type | Default | Lifecycle |
|---|---|---|---|
| `_ambient_wake_pending` | `set[str]` | `set()` | session-scoped — pid added when ambient-debounce threshold fires, discarded when greeting branch consumes it |

**Lifecycle note:** `_voice_gallery` and `_voice_gallery_sizes` are persistent — they survive session close because the voice embedding profiles are long-lived (they span multiple visits). They are loaded at boot from `db.load_voice_profiles()` and `db.load_voice_profile_sizes()`, updated incrementally, and reconciled against DB by `_dream_loop`.

`_ambient_wake_pending` is session-scoped — it is consumed by the greeting branch and has no DB backing.

---

## Module-level Declarations

```
L750: _voice_gallery:         dict                  = {}
L751: _voice_gallery_sizes:   dict                  = {}
L749: _ambient_wake_pending:  set[str]              = set()
```

---

## Write Sites

### `_voice_gallery`

| Line | Function | Mutation shape | Snippet |
|---|---|---|---|
| L750 | module-level | init/declaration | `_voice_gallery: dict = {}` |
| L2675 | `_accumulate_voice` | key-set `[k]=v` — update profile after embedding accumulation | `_voice_gallery[person_id] = updated` |
| L3336 | `_dream_loop` (stranger TTL) | `.pop()` (CLEANUP — pre-DB-delete cache eviction) | `_voice_gallery.pop(_pid, None)` |
| L3361 | `_dream_loop` (reconciliation, vanished profile) | `.pop()` (CLEANUP) | `_voice_gallery.pop(_pid, None)` |
| L3363 | `_dream_loop` (reconciliation, reload) | key-set `[k]=v` — reload from DB | `_voice_gallery[_pid] = _prof` |
| L6093 | `run` (boot) | `.update()` — bulk load from DB | `_voice_gallery.update(db.load_voice_profiles())` |
| L6274 | `run` (factory reset) | `.clear()` (CLEANUP) | `_voice_gallery.clear()` |

### `_voice_gallery_sizes`

| Line | Function | Mutation shape | Snippet |
|---|---|---|---|
| L751 | module-level | init/declaration | `_voice_gallery_sizes: dict = {}` |
| L2154 | `_open_session` (repair from DB count) | key-set `[k]=v` — sync size from DB | `_voice_gallery_sizes[person_id] = _db_voice_count` |
| L2677 | `_accumulate_voice` | key-set `[k]=v` — update count after accumulation | `_voice_gallery_sizes[person_id] = count` |
| L3337 | `_dream_loop` (stranger TTL) | `.pop()` (CLEANUP) | `_voice_gallery_sizes.pop(_pid, None)` |
| L3356 | `_dream_loop` (reconciliation) | `.clear()` (CLEANUP — before reload) | `_voice_gallery_sizes.clear()` |
| L3357 | `_dream_loop` (reconciliation) | `.update()` — reload from DB | `_voice_gallery_sizes.update(_fresh_sizes)` |
| L6094 | `run` (boot) | `.update()` — bulk load from DB | `_voice_gallery_sizes.update(db.load_voice_profile_sizes())` |
| L6275 | `run` (factory reset) | `.clear()` (CLEANUP) | `_voice_gallery_sizes.clear()` |

### `_ambient_wake_pending`

| Line | Function | Mutation shape | Snippet |
|---|---|---|---|
| L749 | module-level | init/declaration | `_ambient_wake_pending: set[str] = set()` |
| L2795 | `_background_vision_loop` (ambient debounce) | `.add()` | `_ambient_wake_pending.add(_pid)` |
| L6476 | `run` (greeting consumes wake signal) | `.discard()` (CLEANUP) | `_ambient_wake_pending.discard(person_id)` |

**Required mutation methods:**
- `async set_profile(pid, profile)` — update/create gallery entry
- `async set_sample_count(pid, count)` — update sample count
- `async bulk_load(profiles_dict, sizes_dict)` — boot load from DB
- `async reload_sizes(sizes_dict)` — reconciliation size reload (`_voice_gallery_sizes.clear()` + `.update()`)
- `async pop_profile(pid)` — pre-delete eviction / reconciliation pop
- `async reload_profile(pid, profile)` — reconciliation reload
- `async clear_all()` — factory reset
- `async mark_ambient_wake(pid)` — `.add(pid)` to `_ambient_wake_pending`
- `async consume_ambient_wake(pid)` — `.discard(pid)` from `_ambient_wake_pending`
- `def reset()` — clears everything (test isolation)

---

## Read Sites

### `_voice_gallery`

| Line | Function | Access pattern |
|---|---|---|
| L2651 | `_accumulate_voice` | passed to `voice_mod.identify(...)` as gallery |
| L6095 | `run` (boot log) | `len(_voice_gallery)` |
| L6750 | `run` (ambient voice ID) | passed to voice identification function |
| L7000 | `run` (per-turn voice ID) | passed to voice identification function |
| L7046 | `run` (diarize executor) | passed to diarize function |
| L7129 | `run` (voice_state dict) | `"gallery_size": len(_voice_gallery)` |
| L7222 | `run` (Voice Channel shadow) | passed to shadow voice ID |
| L7333 | `run` (switch_enrolled voice_state rebuild) | `"gallery_size": len(_voice_gallery)` |

### `_voice_gallery_sizes`

| Line | Function | Access pattern |
|---|---|---|
| L2149 | `_open_session` | `.get(person_id, 0)` — cached size lookup |
| L2153 | `_open_session` | `.get(person_id, -1)` — divergence check |
| L2201 | `_open_session` (Wave 2 backfill heuristic) | `.get(person_id, 0)` — compare against N_INITIAL_VOICE |
| L2207 | `_open_session` (backfill log) | `.get(person_id, 0)` — log entry |
| L3351 | `_dream_loop` (divergence detection) | `set(_voice_gallery_sizes)` — iterate pids |
| L3352 | `_dream_loop` | `.get(_pid)` — compare against fresh DB sizes |
| L7196 | `run` | passed to `_resolve_actual_speaker` |
| L7262 | `run` | `voice_gallery_sizes=_voice_gallery_sizes` kwarg to `_build_routing_inputs` |

### `_ambient_wake_pending`

| Line | Function | Access pattern |
|---|---|---|
| L2791 | `_background_vision_loop` | `_pid not in _ambient_wake_pending` membership test |

**Required peek methods:**
- `peek_profile(pid) → object | None` — returns gallery profile (live ref, passed to `voice_mod.identify`)
- `peek_all_profiles() → dict[str, object]` — for callers that pass whole gallery dict (voice identification functions)
- `peek_sample_count(pid) → int` — fast size accessor
- `peek_all_sizes() → dict[str, int]` — for callers that pass whole sizes dict (routing, resolve_actual_speaker)
- `peek_gallery_len() → int` — for `len(_voice_gallery)` sites
- `peek_ambient_wake_pending() → frozenset[str]` — for membership check in background loop

Note: `voice_mod.identify`, `_accumulate_voice`, `_dream_loop` divergence detection, `_resolve_actual_speaker`, and `_build_routing_inputs` all receive the entire gallery dict. Their signatures will need updating to accept either `VoiceGalleryStore` or a `dict[str, object]` snapshot.

---

## Cleanup-path Sites

| Line | Function | Context | Snippet |
|---|---|---|---|
| L3336 | `_dream_loop` (stranger TTL) | STRANGER_VOICE_TTL prune, pre-DB-delete | `_voice_gallery.pop(_pid, None)` |
| L3337 | `_dream_loop` (stranger TTL) | STRANGER_VOICE_TTL prune | `_voice_gallery_sizes.pop(_pid, None)` |
| L3356 | `_dream_loop` (reconciliation) | clear before full reload | `_voice_gallery_sizes.clear()` |
| L6274 | `run` (factory reset) | factory reset | `_voice_gallery.clear()` |
| L6275 | `run` (factory reset) | factory reset | `_voice_gallery_sizes.clear()` |
| L6476 | `run` (greeting branch) | wake-signal consumption | `_ambient_wake_pending.discard(person_id)` |

**Note:** The `_dream_loop` stranger-TTL path pops both `_voice_gallery` and `_voice_gallery_sizes` atomically (L3336 and L3337 are adjacent). The migration must preserve this atomicity — `pop_profile(pid)` should pop both gallery profile and size in a single locked operation.

---

## Cross-field Invariants

- `_voice_gallery_sizes[pid] == len(profile.embeddings)` should hold for known persons (verified by `_dream_loop` divergence detection at L3351-L3352). The Store's `set_profile` and `set_sample_count` should not enforce this invariant — the divergence check is the caller's responsibility.
- If `_voice_gallery[pid]` exists, `_voice_gallery_sizes[pid]` should also exist (and vice versa for known persons). The `_dream_loop` reconciliation path that calls `_voice_gallery_sizes.clear()` before `_voice_gallery_sizes.update(_fresh_sizes)` is a bulk replacement — it must be atomic in the Store (not two separate async calls).
- `_ambient_wake_pending` has no cross-field invariant with the gallery entries.

---

## Mutation Shapes Summary

| Global | Shape | Count |
|---|---|---|
| `_voice_gallery` | key-set `[k]=v` | 2 (L2675 update, L3363 reconcile reload) |
| `_voice_gallery` | `.update()` (bulk) | 1 (L6093 boot) |
| `_voice_gallery` | `.pop()` (cleanup) | 2 (L3336, L3361) |
| `_voice_gallery` | `.clear()` (cleanup) | 1 (L6274) |
| `_voice_gallery_sizes` | key-set `[k]=v` | 2 (L2154 open_session, L2677 accumulate) |
| `_voice_gallery_sizes` | `.update()` (bulk) | 2 (L6094 boot, L3357 reconcile) |
| `_voice_gallery_sizes` | `.pop()` (cleanup) | 1 (L3337) |
| `_voice_gallery_sizes` | `.clear()` (cleanup) | 2 (L3356 reconcile-before-reload, L6275 factory) |
| `_ambient_wake_pending` | `.add()` | 1 (L2795) |
| `_ambient_wake_pending` | `.discard()` | 1 (L6476) |

---

## Lifecycle Phase

1. **Gallery loaded:** On boot, `bulk_load(profiles, sizes)` initializes both dicts from DB.
2. **Profile updated:** `_accumulate_voice` calls `set_profile(pid, updated)` and `set_sample_count(pid, count)` after each accumulation.
3. **Size synced on session open:** `_open_session` reads `peek_sample_count(pid)` and may call `set_sample_count(pid, db_count)` if divergence detected.
4. **Stranger TTL cleanup:** `_dream_loop` calls `pop_profile(pid)` atomically when a stranger's voice TTL expires (pre-DB-delete cache eviction).
5. **Reconciliation:** `_dream_loop` calls `reload_sizes(fresh_sizes)` atomically when DB count diverges from cached sizes.
6. **Ambient wake:** Background loop calls `mark_ambient_wake(pid)` when debounce threshold fires. Greeting branch calls `consume_ambient_wake(pid)` to clear the signal.
7. **Factory reset:** `clear_all()` clears everything including persistent gallery data.
