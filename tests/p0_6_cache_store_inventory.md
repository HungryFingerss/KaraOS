# P0.6.5 — CacheStore Inventory

**Store:** `CacheStore` in `core/cache_store.py`
**Globals migrated:** `_scene_block_cache`, `_classifier_cache`, `_identity_hints`, `_query_embedding_cache`
**Sub-PR:** P0.6.5

---

## Design Note — TTL-Aware CacheStore

All four globals are manual key-value caches. Two of them (`_classifier_cache`) have a manual 5-second TTL check at every read site (`time.time() - cached_at > TTL`). The `CacheStore` design bakes TTL into `peek(key)` — expired entries return `None`. This eliminates the scattered manual time-since-cached checks.

Each cache instance has its own TTL configured at construction. See per-cache TTL settings below.

**Eviction semantics (from spec):** NOT LRU. Eviction is "oldest-by-cached-at" on WRITE only. `peek()` is genuinely read-only — no hidden mutation through reads.

---

## Per-Cache Configuration

| Cache global | Store instance name | TTL | Max size |
|---|---|---|---|
| `_scene_block_cache` | `_scene_block_cache_store` | None (no expiry) | `SCENE_BLOCK_CACHE_MAX_ENTRIES` |
| `_classifier_cache` | `_classifier_cache_store` | 5.0 seconds | `_CLASSIFIER_CACHE_MAX_SIZE` |
| `_identity_hints` | `_identity_hints_store` | None (no expiry) | 64 (or current unbounded — confirm at migration) |
| `_query_embedding_cache` | `_query_embedding_store` | None (no expiry) | 256 (or current unbounded — confirm at migration) |

`_identity_hints` and `_query_embedding_cache` have no TTL today and no explicit max-size cap in the current code. The CacheStore should use a conservative max-size to bound memory growth. Confirm the values at migration time by measuring typical entry counts.

---

## Module-level Declarations

```
L852:  _scene_block_cache:        "dict[tuple, str]" = {}
L1074: _classifier_cache:         "dict[tuple, tuple]" = {}
L283:  _identity_hints:           dict[str, dict] = {}
L838:  _query_embedding_cache:    dict                       = {}
```

---

## Write Sites

### `_scene_block_cache`

| Line | Function | Mutation shape | Snippet |
|---|---|---|---|
| L852 | module-level | init/declaration | `_scene_block_cache: "dict[tuple, str]" = {}` |
| L1885 | `_get_scene_block_cached` | `del d[key]` (size-overflow eviction of oldest entry) | `del _scene_block_cache[oldest]` |
| L1887 | `_get_scene_block_cached` | key-set `[k]=v` — store computed result | `_scene_block_cache[key] = result` |
| L6283 | `run` (factory reset) | `.clear()` | `_scene_block_cache.clear()` |

### `_classifier_cache`

| Line | Function | Mutation shape | Snippet |
|---|---|---|---|
| L1074 | module-level | init/declaration | `_classifier_cache: "dict[tuple, tuple]" = {}` |
| L1096 | `_classify_intent_cached` | `.pop(key, None)` (TTL-expired entry drop) | `_classifier_cache.pop(key, None)` |
| L1104 | `_classify_intent_cached` | key-set `[k]=v` — store result + timestamp | `_classifier_cache[key] = (sidecar, now)` |
| L1109 | `_classify_intent_cached` | `.pop(old_key, None)` (oldest-25% LRU eviction) | `_classifier_cache.pop(old_key, None)` |

### `_identity_hints`

| Line | Function | Mutation shape | Snippet |
|---|---|---|---|
| L283 | module-level | init/declaration | `_identity_hints: dict[str, dict] = {}` |
| L2372 | `_close_session` | `.pop()` (CLEANUP — session close evicts hint) | `_identity_hints.pop(person_id, None)` |
| L5862 | `conversation_turn` (stranger identity scoring) | key-set `[k]=v` — store identity hint | `_identity_hints[person_id] = _id_hit` |
| L5952 | `conversation_turn` (auto-confirm promotion) | `.pop()` (CLEANUP — hint consumed by promotion) | `_identity_hints.pop(person_id, None)` |

### `_query_embedding_cache`

| Line | Function | Mutation shape | Snippet |
|---|---|---|---|
| L838 | module-level | init/declaration | `_query_embedding_cache: dict = {}` |
| L2371 | `_close_session` | `.pop()` (CLEANUP — session close) | `_query_embedding_cache.pop(person_id, None)` |
| L4416 | `_refresh_query_embedding` | key-set `[k]=v` — store computed embedding | `_query_embedding_cache[person_id] = emb` |
| L7302 | `run` (switch_enrolled) | `.pop()` (CLEANUP — invalidate stale embedding) | `_query_embedding_cache.pop(_resolved_pid, None)` |

**Required mutation methods on `CacheStore`:**
- `async set(key, value, ttl_secs=None)` — store with optional per-entry TTL override
- `async invalidate(key)` — explicit cache eviction (replaces `.pop()` at session close, promotion, switch_enrolled)
- `async invalidate_all()` — factory reset (replaces `.clear()`)
- `def peek(key) → object | None` — sync read, returns None if absent OR expired
- `def reset()` — clears all entries (test isolation)

---

## Read Sites

### `_scene_block_cache`

| Line | Function | Access pattern |
|---|---|---|
| L1859 | `_get_scene_block_cached` | `global _scene_block_cache` (declaration) |
| L1872 | `_get_scene_block_cached` | `.get(key)` — cache lookup |
| L1883 | `_get_scene_block_cached` | `len(_scene_block_cache) >= SCENE_BLOCK_CACHE_MAX_ENTRIES` — size gate |
| L1884 | `_get_scene_block_cached` | `next(iter(_scene_block_cache))` — oldest entry for eviction |
| L1896 | `get_scene_block_cache_stats` | `len(_scene_block_cache)` — stats reporting |

### `_classifier_cache`

| Line | Function | Access pattern |
|---|---|---|
| L1090 | `_classify_intent_cached` | `.get(key)` — cache lookup |
| L1095 | `_classify_intent_cached` | cache hit check — `cached[1]` = timestamp, check TTL |
| L1105 | `_classify_intent_cached` | `len(_classifier_cache) > _CLASSIFIER_CACHE_MAX_SIZE` — size gate |
| L1107 | `_classify_intent_cached` | `len(_classifier_cache) // 4` — evict count calculation |
| L1108 | `_classify_intent_cached` | `list(_classifier_cache.keys())[:_evict_n]` — oldest keys for eviction |

Note: The TTL check at L1095 is the manual `time.time() - cached[1] > TTL` check that the `CacheStore` TTL mechanism will replace. After migration, the read path becomes simply `peek(key)` — if `None`, cache miss (either absent or TTL-expired).

### `_identity_hints`

| Line | Function | Access pattern |
|---|---|---|
| L5146 | `conversation_turn` (stranger hint injection) | `if person_id in _identity_hints:` membership test |
| L5147 | `conversation_turn` | `_id_h = _identity_hints[person_id]` — index read |

### `_query_embedding_cache`

| Line | Function | Access pattern |
|---|---|---|
| L5002 | `conversation_turn` | `.get(person_id)` — cached embedding lookup |

**Required peek method:**
- `peek(key) → object | None` — covers all read sites (`.get(key)`, `key in d`, `d[key]`)

For `_scene_block_cache`, the `get_scene_block_cache_stats()` function needs a `peek_size() → int` or the stat function itself is refactored to call the store.

---

## Cleanup-path Sites

| Line | Function | Context | Snippet |
|---|---|---|---|
| L1096 | `_classify_intent_cached` | TTL-expired entry drop (at every read) | `_classifier_cache.pop(key, None)` |
| L1109 | `_classify_intent_cached` | oldest-25% overflow eviction (at every write) | `_classifier_cache.pop(old_key, None)` |
| L1885 | `_get_scene_block_cached` | size-overflow eviction of oldest entry | `del _scene_block_cache[oldest]` |
| L2371 | `_close_session` | session-close | `_query_embedding_cache.pop(person_id, None)` |
| L2372 | `_close_session` | session-close | `_identity_hints.pop(person_id, None)` |
| L5952 | `conversation_turn` (auto-confirm promotion) | hint consumed — identity confirmed | `_identity_hints.pop(person_id, None)` |
| L6283 | `run` (factory reset) | factory reset | `_scene_block_cache.clear()` |
| L7302 | `run` (switch_enrolled) | stale-embedding invalidation | `_query_embedding_cache.pop(_resolved_pid, None)` |

**IMPORTANT — cleanup path consolidation after migration:**

After migration, the explicit `.pop()` and `.clear()` cleanup sites all collapse to `await store.invalidate(key)` or `await store.invalidate_all()`. The TTL-driven cleanup in `_classifier_cache` (L1096 and L1109) disappears entirely — the `CacheStore.peek()` method handles TTL expiry transparently, and `CacheStore.set()` handles overflow eviction automatically.

---

## Cross-field Invariants

No cross-field invariants between the four cache globals — they operate on different key types and value types. Each `CacheStore` instance is independent.

Within each cache:
- `_classifier_cache`: entries have shape `(sidecar, timestamp)` — the timestamp is the manual TTL reference. After migration, `CacheStore` stores the timestamp internally; callers only see `sidecar` as the value.
- `_identity_hints`: entries are `dict` — the identity hit dict from the scoring path.
- `_query_embedding_cache`: entries are numpy embedding arrays.
- `_scene_block_cache`: entries are rendered block strings (str).

---

## Mutation Shapes Summary

| Global | Shape | Count |
|---|---|---|
| `_scene_block_cache` | key-set `[k]=v` | 1 (L1887) |
| `_scene_block_cache` | `del d[key]` (size overflow eviction) | 1 (L1885) |
| `_scene_block_cache` | `.clear()` | 1 (L6283) |
| `_classifier_cache` | key-set `[k]=v` (with timestamp) | 1 (L1104) |
| `_classifier_cache` | `.pop()` TTL expiry | 1 (L1096) |
| `_classifier_cache` | `.pop()` LRU eviction | 1 (L1109) |
| `_identity_hints` | key-set `[k]=v` | 1 (L5862) |
| `_identity_hints` | `.pop()` session-close | 1 (L2372) |
| `_identity_hints` | `.pop()` promotion cleanup | 1 (L5952) |
| `_query_embedding_cache` | key-set `[k]=v` | 1 (L4416) |
| `_query_embedding_cache` | `.pop()` session-close | 1 (L2371) |
| `_query_embedding_cache` | `.pop()` switch_enrolled invalidation | 1 (L7302) |

---

## Lifecycle Phase

1. **Entry created:** Each cache stores its first entry when the compute path fires (recognition, intent classification, identity scoring, query embedding refresh).
2. **Entry hit (cache hit):** `peek(key)` returns the cached value. TTL-aware — returns None if expired.
3. **Entry evicted (overflow):** `CacheStore.set()` evicts oldest-by-cached-at when `len > max_size`.
4. **Entry invalidated (explicit):** Session-close, promotion, switch_enrolled all call `invalidate(key)`. Factory reset calls `invalidate_all()`.
5. **TTL expiry (transparent):** `peek()` returns None for expired entries in `_classifier_cache_store` (5-sec TTL). No explicit eviction step needed.
