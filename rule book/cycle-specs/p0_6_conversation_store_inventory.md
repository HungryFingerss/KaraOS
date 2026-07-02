# P0.6.3 — ConversationStore Inventory

**Store:** `ConversationStore` in `core/conversation_store.py`
**Globals migrated:** `_conversation`, `_last_greeted`, `_last_self_update`, `_compact_pids`
**Sub-PR:** P0.6.3

---

## Fields

### Per-pid entry (`ConversationEntry`)

| Field | Type | Default | Lifecycle |
|---|---|---|---|
| `history` | `list[dict]` | `[]` | session-scoped — loaded on session open, cleared on session close via `_expire_stale_sessions` |
| `last_greeted_at` | `float` | `0.0` | **persistent across sessions** — set on greeting, survives session close for cooldown discipline |
| `last_self_update_at` | `float` | `0.0` | persistent across sessions (anti-spoof / voice gallery self-update TTL) |

### Store-level state

| Field | Type | Default | Lifecycle |
|---|---|---|---|
| `_compact_pids` | `set[str]` | `set()` | in-flight compaction tracker — pid is added before compaction task starts, discarded in `finally:` after |

**Dict key:** `person_id` (str).

**Critical lifecycle distinction (Architectural decision #2):**
- `history` is session-scoped — it's loaded from DB on session open and discarded on session close/expiry.
- `last_greeted_at` and `last_self_update_at` are persistent — they survive session close because the greeting cooldown (`GREET_COOLDOWN`) and self-update TTL must persist between visits.
- The Store must support separate cleanup for session-scoped fields vs persistent fields.

---

## Module-level Declarations

```
L794: _conversation:       dict                  = {}
L747: _last_greeted:          dict[str, float]      = {}
L748: _last_self_update:      dict[str, float]      = {}
L796: _compact_pids:       set[str]              = set()
```

---

## Write Sites

### `_conversation`

| Line | Function | Mutation shape | Snippet |
|---|---|---|---|
| L794 | module-level | init/declaration | `_conversation: dict = {}` |
| L2528 | `_expire_stale_sessions` | `.pop(pid, None)` (CLEANUP — session expiry) | `_conversation.pop(_pid, None)` |
| L3256 | `_kairos_tick` | `.setdefault().extend()` — append silence+response turns | `_conversation.setdefault(person_id, []).extend([...])` |
| L4871 | `conversation_turn._compact_history_background` | key-set `[k]=v` — replace history with compacted version | `_conversation[_pid] = _compacted` |
| L4971 | `conversation_turn` (user-to-user silent-skip) | key-set `[k]=v` — store history after modifications | `_conversation[person_id] = history` |
| L5828 | `conversation_turn` | key-set `[k]=v` — store history after conversation turn | `_conversation[person_id] = history` |
| L6273 | `run` (factory reset) | `.clear()` (CLEANUP) | `_conversation.clear()` |
| L6512 | `run` (greeting / returning stranger) | key-set `[k]=v` — load from DB | `_conversation[person_id] = db.load_conversation_history(person_id)` |
| L6596 | `run` (greeting known) | key-set `[k]=v` — load from DB | `_conversation[person_id] = history_from_db` |
| L6759 | `run` (voice-id ambient-listen) | key-set `[k]=v` — load from DB | `_conversation[v_pid] = db.load_conversation_history(v_pid)` |
| L6792 | `run` (camera fallback) | key-set `[k]=v` — load from DB | `_conversation[_best_pid] = db.load_conversation_history(_best_pid)` |
| L6812 | `run` (voice-only stranger gate) | key-set `[k]=v` — init empty | `_conversation[_sid] = []` |
| L7298 | `run` (switch_enrolled) | key-set `[k]=v` — load from DB | `_conversation[_resolved_pid] = db.load_conversation_history(_resolved_pid)` |
| L7381 | `run` (new_stranger) | key-set `[k]=v` — init empty | `_conversation[_sid] = []` |

### `_last_greeted`

| Line | Function | Mutation shape | Snippet |
|---|---|---|---|
| L747 | module-level | init/declaration | `_last_greeted: dict[str, float] = {}` |
| L2529 | `_expire_stale_sessions` | key-set `[k]=v` — record last-seen timestamp on session expiry | `_last_greeted[_pid] = time.time()` |
| L6271 | `run` (factory reset) | `.clear()` (CLEANUP) | `_last_greeted.clear()` |
| L6486 | `run` (greeting) | key-set `[k]=v` | `_last_greeted[person_id] = time.time()` |
| L6673 | `run` (unknown sighting) | key-set `[k]=v` | `_last_greeted[unknown_key] = time.time()` |
| L6836 | `run` (voice/camera-fallback session) | key-set `[k]=v` | `_last_greeted[_primary_pid_conv] = time.time()` |

### `_last_self_update`

| Line | Function | Mutation shape | Snippet |
|---|---|---|---|
| L748 | module-level | init/declaration | `_last_self_update: dict[str, float] = {}` |
| L6272 | `run` (factory reset) | `.clear()` (CLEANUP) | `_last_self_update.clear()` |
| L6456 | `run` (anti-spoof fail path) | key-set `[k]=v` | `_last_self_update[person_id] = time.time()` |
| L6461 | `run` (anti-spoof live path) | key-set `[k]=v` | `_last_self_update[person_id] = time.time()` |
| L6457 | `run` | `_prune_dict(_last_self_update)` — helper mutates dict by deleting oldest key | passive mutation via helper |
| L6462 | `run` | `_prune_dict(_last_self_update)` | passive mutation via helper |

### `_compact_pids`

| Line | Function | Mutation shape | Snippet |
|---|---|---|---|
| L796 | module-level | init/declaration | `_compact_pids: set[str] = set()` |
| L4875 | `conversation_turn._compact_history_background` (FINALLY) | `.discard()` (CLEANUP) | `_compact_pids.discard(_pid)` |
| L4877 | `conversation_turn` | `.add()` | `_compact_pids.add(person_id)` |

**Required mutation methods:**
- `async set_history(pid, history)` — store or replace history list (session open, compaction, turn save)
- `async append_turns(pid, turns)` — append multiple message dicts (kairos silence+response)
- `async clear_history(pid)` — session-close pop of history only (not `last_greeted_at`)
- `async clear_all_histories()` — factory reset (pops all `history` fields but preserves `last_greeted_at`)
- `async mark_greeted(pid, ts)` — set `last_greeted_at`
- `async mark_self_update(pid, ts)` — set `last_self_update_at`
- `async prune_self_update(pid)` — replaces `_prune_dict(_last_self_update)` passive mutation
- `async mark_compact_running(pid)` — `.add(pid)` to compact_pids
- `async clear_compact_running(pid)` — `.discard(pid)` from compact_pids (MUST be called in `finally:`)
- `def is_compact_running(pid) → bool` — sync read for compaction gate
- `def reset()` — clears everything (test isolation)

---

## Read Sites

### `_conversation`

| Line | Function | Access pattern |
|---|---|---|
| L3157 | `_kairos_tick` | `.get(person_id, [])` — get history for silence-handling |
| L3193 | `_kairos_tick` | passed to `_build_room_block` (whole dict) |
| L3812 | `_execute_tool` (enrollment-mishear) | `.get(person_id, [])` iteration |
| L3952 | `_execute_tool` (update_person_name) | `.get(person_id, [])` iteration |
| L4060 | `_execute_tool` (stranger rename) | `.get(person_id, [])` iteration |
| L4869 | `conversation_turn._compact_history_background` | `.get(_pid, [])` — read current history for compaction |
| L4896 | `conversation_turn` | `.get(person_id, [])` — read history for turn |
| L5087 | `conversation_turn` | passed to `_build_cross_person_excerpts` |
| L5859 | `conversation_turn` (identity scoring) | `.get(person_id, [])` |
| L5939 | `conversation_turn` (auto-confirm) | `.get(person_id, [])` iteration |
| L6758 | `run` | `if v_pid not in _conversation:` membership test |
| L6791 | `run` | `if _best_pid not in _conversation:` membership test |
| L7298 | `run` (switch_enrolled) | membership test (also write — see write sites) |
| L7544 | `run` | passed to `_build_room_block` |

### `_last_greeted`

| Line | Function | Access pattern |
|---|---|---|
| L2790 | `_background_vision_loop` | `.get(_pid, 0)` — cooldown check |
| L6467 | `run` (greeting) | `.get(person_id, 0)` — cooldown check |
| L6671 | `run` (unknown sighting) | `.get(unknown_key, 0)` — cooldown check |

### `_last_self_update`

| Line | Function | Access pattern |
|---|---|---|
| L6446 | `run` (gallery self-update gate) | `.get(person_id, 0)` — TTL check |

### `_compact_pids`

| Line | Function | Access pattern |
|---|---|---|
| L4864 | `conversation_turn` | `if person_id not in _compact_pids:` membership test (compaction gate) |

**Required peek methods:**
- `peek_history(pid) → tuple[dict, ...]` — returns frozen tuple copy of history list
- `peek_last_greeted(pid) → float` — returns `last_greeted_at` or 0.0
- `peek_last_self_update(pid) → float` — returns `last_self_update_at` or 0.0
- `peek_has_history(pid) → bool` — for membership tests (`if pid not in _conversation`)
- `is_compact_running(pid) → bool` — sync read (no lock needed — single-thread asyncio safe)
- `peek_all_histories() → dict[str, tuple[dict, ...]]` — for callers that pass whole dict to helper functions

Note: `_build_room_block` and `_build_cross_person_excerpts` receive the entire `_conversation` dict. Their signatures will need updating to accept either the `ConversationStore` or a `dict[str, tuple[dict, ...]]` snapshot.

---

## Cleanup-path Sites

| Line | Function | Context | Snippet |
|---|---|---|---|
| L2528 | `_expire_stale_sessions` | session expiry | `_conversation.pop(_pid, None)` |
| L4875 | `_compact_history_background` (FINALLY) | background compaction task finally block | `_compact_pids.discard(_pid)` |
| L6271 | `run` (factory reset) | factory reset | `_last_greeted.clear()` |
| L6272 | `run` (factory reset) | factory reset | `_last_self_update.clear()` |
| L6273 | `run` (factory reset) | factory reset | `_conversation.clear()` |

**CRITICAL — `_compact_pids` finally block:** The `.discard(_pid)` at L4875 is inside a `finally:` clause of `_compact_history_background`. If the compaction task throws, this discard is the ONLY mechanism preventing the compaction gate (`person_id not in _compact_pids` at L4864) from being permanently blocked for that pid. The Store's `clear_compact_running(pid)` method MUST be called in a `finally:` block at the migration site. This cannot be moved to a simple `async with` context manager without preserving the try/finally shape.

---

## Cross-field Invariants

- `last_greeted_at > 0` does NOT imply that `history` is non-empty. A person can be greeted (last_greeted_at set) after a session expires (history cleared by `_expire_stale_sessions`).
- `if pid not in _conversation` checks are used as a proxy for "no active session history loaded" — the Store's `peek_has_history(pid)` should return `False` when `history == []` OR when no entry exists. (Current code uses membership + empty list to mean the same thing; the Store should preserve this semantic.)
- `_compact_pids` membership is invariant within a compaction task: `add` before task start, `discard` in `finally`. No other write to `_compact_pids` is valid. The Store must not expose a `clear()` that would invalidate in-flight compaction guards.

---

## Mutation Shapes Summary

| Global | Shape | Count |
|---|---|---|
| `_conversation` | key-set (load from DB, save after turn) | 8 |
| `_conversation` | `.setdefault().extend()` (append kairos turns) | 1 |
| `_conversation` | `.pop(pid, None)` (session expiry) | 1 |
| `_conversation` | `.clear()` (factory reset) | 1 |
| `_last_greeted` | key-set `[k]=v` (mark greeted) | 4 |
| `_last_greeted` | `.clear()` (factory reset) | 1 |
| `_last_self_update` | key-set `[k]=v` (mark update) | 2 |
| `_last_self_update` | `_prune_dict(...)` (passive size cap) | 2 |
| `_last_self_update` | `.clear()` (factory reset) | 1 |
| `_compact_pids` | `.add()` | 1 |
| `_compact_pids` | `.discard()` (finally) | 1 |

---

## Lifecycle Phase

1. **Entry created:** On session open — `set_history(pid, db_history)` when greeting first loads conversation from DB. For strangers: `set_history(pid, [])` on new stranger.
2. **History updated:** Each `conversation_turn` saves modified history back via `set_history`. Compaction replaces history with compacted version. Kairos tick appends silence+response turns via `append_turns`.
3. **`last_greeted_at` set:** On greeting (multiple paths). Also set on session expiry to record last-seen time.
4. **`last_self_update_at` set:** When voice gallery self-update fires (face seen, anti-spoof checked).
5. **History cleared (session expiry):** `_expire_stale_sessions` calls `clear_history(pid)` — removes history but leaves `last_greeted_at` intact.
6. **All cleared (factory reset):** `reset()` clears everything including persistent fields.
