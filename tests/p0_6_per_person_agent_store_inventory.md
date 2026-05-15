# P0.6.4b — PerPersonAgentStore Inventory

**Store:** `PerPersonAgentStore` in `core/per_person_agent_store.py`
**Globals migrated:** `_emotion_agents`, `_sessions_started`
**Sub-PR:** P0.6.4 (alongside VoiceGalleryStore)

---

## Design Note — Live-ref Pattern (Intentional Deviation)

Unlike `SessionStore`, `PresenceStore`, and other Stores that return immutable `*Snapshot` objects, `PerPersonAgentStore.get_or_create_emotion_agent(pid)` returns the **live `EmotionAgent` instance**. This is deliberate:

- Callers need to **invoke methods** on the agent (e.g., `agent.process_turn(...)`) — a frozen snapshot of agent state would be meaningless.
- The Store's discipline (replacing snapshot immutability): only `PerPersonAgentStore` creates and destroys agents. Callers receive a live reference but treat it as read-and-call-only — they do NOT mutate the Store's internal dict or reach into agent internals.

This pattern applies to any future per-pid live-agent instance (e.g., per-pid model adapters in future P1.RA work). Do NOT propose tightening to a snapshot pattern without understanding the per-pid live-agent invocation requirement.

---

## Fields

### Per-pid state (`_emotion_agents`)

| Field | Type | Default | Lifecycle |
|---|---|---|---|
| `emotion_agent` | `EmotionAgent` | (created lazily) | session-scoped — created on first `conversation_turn`, popped on `_open_session` (fresh session reset), and cleared on boot reinit |

**Dict key:** `person_id` (str).

### Store-level state (`_sessions_started`)

| Field | Type | Default | Lifecycle |
|---|---|---|---|
| `_sessions_started` | `set[str]` | `set()` | session-scoped — pid added when greeting fires for the first time, discarded on `_close_session` |

**Lifecycle distinction:**
- `_emotion_agents` is reset per-fresh-session (L2104 pops on `_open_session`) but not per-session-close. The reset fires when a NEW session opens for the same pid, not when the previous session closes.
- `_sessions_started` is discarded on `_close_session` (L2354) — this is the standard session-close cleanup path.

---

## Module-level Declarations

```
L836: _emotion_agents:        dict                       = {}
L752: _sessions_started:      set[str]             = set()
```

---

## Write Sites

### `_emotion_agents`

| Line | Function | Mutation shape | Snippet |
|---|---|---|---|
| L836 | module-level | init/declaration | `_emotion_agents: dict = {}` |
| L2104 | `_open_session` (fresh session open) | `.pop()` — reset per-person agent on fresh session | `_emotion_agents.pop(person_id, None)` |
| L5038 | `conversation_turn` | key-set `[k]=v` — create agent on first turn | `_emotion_agents[person_id] = EmotionAgent()` |
| L6105 | `run` (boot reinit) | dict-literal assignment — wipe all agents | `_emotion_agents = {}` |

### `_sessions_started`

| Line | Function | Mutation shape | Snippet |
|---|---|---|---|
| L752 | module-level | init/declaration | `_sessions_started: set[str] = set()` |
| L2354 | `_close_session` | `.discard()` (CLEANUP — session close) | `_sessions_started.discard(person_id)` |
| L6276 | `run` (factory reset) | `.clear()` (CLEANUP) | `_sessions_started.clear()` |
| L6509 | `run` (returning stranger) | `.add()` | `_sessions_started.add(person_id)` |
| L6555 | `run` (known/best_friend greeting) | `.add()` | `_sessions_started.add(person_id)` |
| L6835 | `run` (voice/camera-fallback) | `.add()` | `_sessions_started.add(_primary_pid_conv)` |

**Required mutation methods:**
- `async get_or_create_emotion_agent(pid) → EmotionAgent` — returns live ref; creates `EmotionAgent()` if absent
- `async reset_emotion_agent(pid)` — pops the agent (called on fresh session open); NOT the same as session-close
- `async clear_all_emotion_agents()` — wipes all agents (boot reinit + factory reset)
- `async mark_session_started(pid)` — `.add(pid)` to `_sessions_started`
- `async clear_session_started(pid)` — `.discard(pid)` from `_sessions_started` (session-close cleanup)
- `async clear_all_sessions_started()` — `.clear()` (factory reset)
- `def reset()` — clears everything (test isolation)

---

## Read Sites

### `_emotion_agents`

| Line | Function | Access pattern |
|---|---|---|
| L3193 | `_kairos_tick` | passed to `_build_room_block` (whole dict) |
| L5037 | `conversation_turn` | `if person_id not in _emotion_agents:` membership test (lazy-create gate) |
| L5039 | `conversation_turn` | `_cur_agent = _emotion_agents[person_id]` — index read (get live ref) |
| L5066 | `conversation_turn` | `for _emo_pid, _emo_ag in _emotion_agents.items():` — iteration for multi-person emotion context |
| L7544 | `run` | passed to `_build_room_block` (whole dict) |

### `_sessions_started`

| Line | Function | Access pattern |
|---|---|---|
| L6833 | `run` | `if _primary_pid_conv not in _sessions_started:` membership test |

**Required peek methods:**
- `peek_emotion_agent(pid) → EmotionAgent | None` — returns live ref or None (for code that checks membership before creating)
- `peek_all_emotion_agents() → dict[str, EmotionAgent]` — for callers that pass whole dict to `_build_room_block`
- `peek_session_started(pid) → bool` — for membership check `if pid not in _sessions_started:`

Note: `_build_room_block` receives the entire `_emotion_agents` dict. Its signature will need updating to accept either `PerPersonAgentStore` or a `dict[str, EmotionAgent]` snapshot-reference (live refs, not frozen snapshots).

---

## Cleanup-path Sites

| Line | Function | Context | Snippet |
|---|---|---|---|
| L2104 | `_open_session` | fresh-session reset (NOT session-close) | `_emotion_agents.pop(person_id, None)` |
| L2354 | `_close_session` | session-close | `_sessions_started.discard(person_id)` |
| L6105 | `run` (boot) | boot reinit — `global _emotion_agents; _emotion_agents = {}` | dict-literal reassignment |
| L6276 | `run` (factory reset) | factory reset | `_sessions_started.clear()` |

**IMPORTANT — reset_emotion_agent vs clear_session_started lifecycle distinction:**

- `_emotion_agents.pop(person_id)` fires on `_open_session` — this is a FRESH SESSION OPEN event, not session close. The intent (Critical #5, Session 111 annotation) is to clear the per-person emotional state when a new visit begins, so the agent doesn't inherit stale emotional context from a prior visit. **The migration must NOT move this pop to `_close_session`.**

- `_sessions_started.discard(person_id)` fires on `_close_session` — standard per-session cleanup.

These two are different lifecycle events and must remain as separate named methods.

---

## Cross-field Invariants

- `pid in _sessions_started` implies that a session has been greeted for that pid in the current pipeline run. It does NOT imply `pid in _emotion_agents` (an agent is created lazily on first `conversation_turn`, but `_sessions_started` is set at greeting time before the conversation loop).
- `pid in _emotion_agents` does NOT imply `pid in _sessions_started` (an agent can survive if `_close_session` runs but `_open_session` has not yet fired for the same pid in the current run).
- `_emotion_agents = {}` at L6105 (boot reinit) and `_sessions_started.clear()` at L6276 (factory reset) are in different code paths — they are NOT always called together. The Store's `reset()` method (for test isolation) must clear both, but production code clears them independently.

---

## Mutation Shapes Summary

| Global | Shape | Count |
|---|---|---|
| `_emotion_agents` | key-set `[k]=v` (lazy create) | 1 (L5038) |
| `_emotion_agents` | `.pop()` (fresh-session reset) | 1 (L2104) |
| `_emotion_agents` | dict-literal reassignment (boot wipe) | 1 (L6105) |
| `_sessions_started` | `.add()` | 3 (L6509, L6555, L6835) |
| `_sessions_started` | `.discard()` (session-close) | 1 (L2354) |
| `_sessions_started` | `.clear()` (factory reset) | 1 (L6276) |

---

## Lifecycle Phase

1. **Emotion agent created:** Lazily on first `conversation_turn(pid)` — `get_or_create_emotion_agent(pid)` returns existing or creates new `EmotionAgent()`.
2. **Emotion agent reset:** On `_open_session` (fresh session open) — `reset_emotion_agent(pid)` ensures new visit starts with clean emotional state.
3. **Session started marked:** On greeting (returning stranger, known/best_friend, voice/camera fallback paths) — `mark_session_started(pid)`.
4. **Session started cleared:** On `_close_session` — `clear_session_started(pid)`.
5. **All agents wiped:** On boot reinit — `clear_all_emotion_agents()`.
6. **Factory reset:** `reset()` clears everything.
