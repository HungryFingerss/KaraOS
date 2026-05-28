> **CHAPTER 08 — Prompt Blocks + Brain Agents** | Sourced from `everything_about_system.md` §72-99 (verbatim mechanical extraction per Plan v2 §1.6 section-number stability invariant).

---

## 72. Prompt Blocks (Full Catalog as of Session 113.1)

> **Note.** The original "All Eight Prompt Blocks" catalogue has expanded to sixteen blocks since Session 65 with the Phase 3A and Phase 3B work. The sub-sections below retain the original block descriptions (SENSORS / SCENE / TOOL ACCESS / IDENTITY EVIDENCE / IDENTITY DISPUTED / memory context / emotion / prompt addendum) and then reference Parts XXV and XXVI for the full story on the new blocks.

### The full prompt-block list (order matters — most rendered conditionally):

| Block | Gated By | Details |
|---|---|---|
| `<<<SENSORS>>>` | always | §72.1 |
| `<<<SCENE>>>` | `SCENE_BLOCK_ENABLED` | §64, §72.2 |
| `<<<ROOM>>>` | `ROOM_BLOCK_ENABLED` + ≥2 sessions | Part XXVI §164-§165 |
| `<<<TURN ARBITRATION>>>` | `TURN_ARBITRATION_ENABLED` (appended to ROOM) | Part XXVI §166 |
| `<<<RECENT ROOMS>>>` | `ROOM_END_SYNTHESIS_ENABLED` + recent rows exist | Part XXVI §172 |
| `<<<TOOL ACCESS FOR THIS SPEAKER>>>` | always | §72.3 |
| `<<<IDENTITY EVIDENCE>>>` | `IDENTITY_EVIDENCE_BLOCK_ENABLED` | §58, §72.4 |
| `<<<IDENTITY DISPUTED>>>` | disputed session | §72.5 |
| `<<<STRANGER IDENTITY>>>` | `STRANGER_IDENTITY_BLOCK_ENABLED` + stranger + ≥2 user turns | Part XXV §158 |
| `<<<VISITOR CONTEXT>>>` | `VISITOR_CONTEXT_BLOCK_ENABLED` + `[visitor_id:` marker | Part XXV §157 |
| `<<<CROSS-PERSON PRIVACY>>>` | non-best_friend session | Part XXV §156 |
| `<<<CROSS-PERSON PRIVACY (OWNER MODE)>>>` | best_friend session | Part XXV §156 |
| `<<<HONESTY POLICY>>>` | `HONESTY_POLICY_BLOCK_ENABLED` | §72.9 |
| `<<<HEDGED NAMING CONTRACT>>>` | `HEDGED_NAMING_CONTRACT_ENABLED` | §72.10 |
| `<<<SAFETY CRITICAL>>>` (appended narrative) | visitor with safety_flags | Part XXV §159 |
| `<<<EMOTION>>>` | `EMOTION_ENABLED` | §72.7 |
| `<<<PREFERENCES>>>` (prompt addendum) | PromptPrefAgent output | §72.8 |

### The original eight — verbatim entries follow.


### 72.1 `<<<SENSORS>>>`

```
<<<SENSORS>>>
  face: Jagan (conf=0.82)
  voice: 2 speakers detected: Jagan + Chloe
    (mic is picking up two people this turn — consider addressing both)
<<<END>>>
```

Fields:
- `face:` — name + recognition_conf label (high ≥ 0.45 / medium ≥ 0.28 / low), or "none" if no face.
- `voice:` — speaker-ID result. Can be single speaker, multi-speaker (diarization), or no-voice.

### 72.2 `<<<SCENE>>>`

See §64.

### 72.3 `<<<TOOL ACCESS FOR THIS SPEAKER (person_type='...')>>>`

```
<<<TOOL ACCESS FOR THIS SPEAKER (person_type='best_friend')>>>
  Allowed:
    - shutdown
    - update_system_name
    - update_person_name
    - report_identity_mismatch
    - search_web
    - search_memory
<<<END>>>
```

Human-readable summary of `TOOL_PRIVILEGES[tool]` for the current person_type. The brain doesn't have to guess what it can call.

For a stranger, the list is shorter:
```
  Allowed:
    - update_person_name
    - report_identity_mismatch
    - search_web
  Blocked:
    - shutdown (best_friend only)
    - update_system_name (best_friend only)
    - search_memory (known or best_friend only)
```

### 72.4 `<<<IDENTITY EVIDENCE>>>`

See §58.

### 72.5 `<<<IDENTITY DISPUTED>>>` (conditional)

Only rendered when the current session's person_type is "disputed":

```
<<<IDENTITY DISPUTED>>>
  The speaker has contradicted sensor evidence about who they are.
  Treat them as unknown. Do not reference stored facts about them by
  any name. Use update_person_name if they give a valid clean name.
<<<END>>>
```

### 72.6 Memory context

When `search_memory(query)` fires during the turn, results are injected inline as a user-role message. The brain sees them as "system-provided retrieved context."

### 72.7 Emotion context

```
<<<EMOTION>>>
  Jagan's dominant emotion over last 3 turns: joy (0.72)
<<<END>>>
```

### 72.8 Prompt addendum

The prompt addendum is injected from PromptPrefAgent:

```
<<<PREFERENCES>>>
  Prefers brief and direct responses — keep all replies under 2 sentences regardless of topic
  Avoid starting responses with 'So' — vary starters
<<<END>>>
```

### 72.9 `<<<HONESTY POLICY>>>` (Session 68, Bug N Confabulation Defense)

Rendered when `HONESTY_POLICY_BLOCK_ENABLED=True`. Teaches the brain to hedge when memory is sparse, never narrate fabricated conversations, use temporal framing for just-learned facts ("you just mentioned X"), and reference visible conversation turns directly. The block is an always-on companion to `<<<CROSS-PERSON PRIVACY>>>` — honesty covers *don't fabricate what you don't have*; privacy covers *don't disclose what you have but someone else owns*.

Key rules (paraphrased):

- Use "I don't have details about that" when search_memory is empty.
- Never narrate a conversation without specific turn references.
- Never answer "who was the visitor?" from unrelated facts.
- For just-learned facts in the current session, use "you just mentioned X" / "you said earlier" — not "I remember that you..." (reserve the latter for older sessions / search_memory retrieval).
- Reference visible turns directly — don't say "I don't know" when the answer is two turns up.

### 72.10 `<<<HEDGED NAMING CONTRACT>>>` (Session 76, Phase 1.3)

Rendered when `HEDGED_NAMING_CONTRACT_ENABLED=True`. Tells the brain that when it proposes `update_system_name` / `update_person_name` / `shutdown`, its spoken content must use *hedged* phrasing ("I heard Kara — is that right?") rather than confirmation ("Kara it is!"). Closes the divergence risk where content confirms but the server-side gate rejects.

Lands alongside the Phase 1 STRUCTURED OUTPUT CONTRACT (deprecated after Session 79 scope-shrink but the HEDGED NAMING block survived because its concern — verbal uncertainty for rename-class tools — is orthogonal to the JSON-sidecar mechanism).

### 72.11 The `[addressing:X]` marker protocol

Not a full prompt block, but worth mentioning here. In multi-person rooms, the brain prefixes its response with `[addressing:Name]` (or `[addressing:current]`) to express who it's talking to. The pipeline parses + strips the marker before TTS. See Part XXVI §168.

## 73. Streaming Token Flow

### 73.1 `ask_stream` generator

The generator yields events, each a tuple:
- `("text", str)` — a chunk of response text.
- `("tool_calls", list[dict])` — a tool call emission.
- `("finish", str | None)` — end-of-stream with finish_reason.

### 73.2 Consumption in pipeline

```python
async def _token_gen():
    async for ev_type, payload in ask_stream(text, ...):
        if ev_type == "text":
            response_parts.append(payload)
            yield payload
        elif ev_type == "tool_calls":
            tool_calls.extend(payload)
            if any(tc["name"] in HISTORY_OVERRIDE_TOOLS for tc in payload):
                stop_audio()
        elif ev_type == "finish":
            _stream_finish_reason[0] = payload
```

Text chunks are yielded downstream to `_sentence_stream` → `speak_stream` for TTS. Tool calls are deferred — collected into `tool_calls` list for dispatch after stream end.

### 73.3 HISTORY_OVERRIDE_TOOLS

```python
HISTORY_OVERRIDE_TOOLS = frozenset({"update_system_name", "update_person_name"})
```

When these fire mid-stream, we `stop_audio()` immediately. The LLM's streaming text may have already spoken wrong content (e.g., "Sorry I missed that" while calling `update_person_name`); the audio is cut and the tool result's canonical acknowledgment replaces the LLM text in history.

### 73.4 `_stream_finish_reason` as a closure box

A mutable single-element list holds the finish_reason so the nested async generator can write through it. The outer scope reads it after the stream ends.

```python
_stream_finish_reason: list[str | None] = [None]
# ... inside _token_gen:
elif ev_type == "finish":
    _stream_finish_reason[0] = payload
# ... after stream ends:
_finish = _stream_finish_reason[0]
```

This pattern sidesteps Python's `nonlocal` limitations across async generator boundaries. Obs 3 (post-review).

## 74. Sentence Splitter

See §35. Key point: we split on `. ! ?` at word boundaries, emitting complete sentences downstream for TTS. Buffers incomplete tails until the next token.

## 75. Tool Dispatch

### 75.1 `_execute_tool(tool_name, args, pid, person_name, *, db, ...)`

```python
async def _execute_tool(tool_name: str, args: dict, pid: str, person_name: str, *, db, ...):
    # Layer 2: privilege check
    caller_type = _active_sessions.get(pid, {}).get("person_type", "stranger")
    if not _tool_allowed(tool_name, caller_type):
        print(f"[Brain] Tool {tool_name} BLOCKED — {caller_type} not permitted")
        return
    # Layer 3: repeat guard — abort if same (name, args_hash) seen 2+ consecutive times
    ...
    # Layer 4: dispatch
    if tool_name == "update_person_name":
        return await _handle_update_person_name(args, pid, person_name, db)
    elif tool_name == "update_system_name":
        return await _handle_update_system_name(args, pid, person_name, db)
    elif tool_name == "search_web":
        return await _handle_search_web(args, pid, person_name)
    elif tool_name == "shutdown":
        return await _handle_shutdown(args, pid, person_name)
    elif tool_name == "search_memory":
        return await _handle_search_memory(args, pid, person_name, db)
    elif tool_name == "report_identity_mismatch":
        return await _handle_report_identity_mismatch(args, pid, person_name, db)
    else:
        print(f"[Brain] Unknown tool {tool_name!r} — fail-closed, ignoring")
```

### 75.2 Per-tool handlers

Each tool has its own handler in `pipeline.py`. Handlers:
- Validate args.
- Execute the side effect (DB write, network call, etc.).
- Emit a canonical acknowledgment via TTS if HISTORY_OVERRIDE tool.
- Log the outcome.

### 75.3 Dispatch log

Every tool call logs:
```
[Brain] HH:MM:SS.mmm Tool: {name}({args})
[Pipeline] Tool: {canonical-outcome-line}
```

For example:
```
[Brain] 01:22:16.430 Tool: update_system_name({'name': 'Kara'})
[Pipeline] Tool: system name → 'Kara'
```

## 76. History Management

### 76.1 `db.load_conversation_history(pid)` returns turns

```python
def load_conversation_history(self, person_id: str) -> list[dict]:
    cursor = self._conn.execute(
        "SELECT role, content FROM conversation_log WHERE person_id = ? ORDER BY id DESC LIMIT ?",
        (person_id, CONVERSATION_HISTORY_LIMIT),
    )
    rows = cursor.fetchall()
    return [{"role": r[0], "content": r[1]} for r in reversed(rows)]
```

`LIMIT=100` turns returned. Older turns stay in DB and can be retrieved via `search_memory`.

### 76.2 `db.log_turn(pid, role, content)`

INSERT INTO conversation_log. Timestamps auto-populated.

### 76.3 History override on HISTORY_OVERRIDE_TOOLS

When `update_person_name` fires, the LLM text streamed may be wrong. We replace the stored assistant turn with a canonical line ("Got it, Chloe.") rather than logging the LLM's actual output. Session 25 L1 introduced this to prevent history poisoning.

### 76.4 Disputed-session gating

If the session is disputed, `db.log_turn(...)` is *skipped*. Turns stay in-memory only until identity resolves. Session 53 Finding B added this.

### 76.5 Context compression

When estimated token count in history exceeds TOKEN_COMPACT_THRESHOLD (50K), AutoCompact fires — an LLM summarises old turns into a bullet list. Further growth past TOKEN_HARD_LIMIT (100K) triggers hard-trim.

---
---

# Part XIII — Brain / LLM

## 77. Together.ai as Primary

### 77.1 Why Together.ai

- **Streaming** — we need token-by-token output for low TTFT.
- **Function calling** — native support for tool definitions.
- **Turbo tier** — speculative decoding gives ~200-500ms TTFT, dramatically better than non-Turbo.
- **No rate limits** in practice on paid tier.
- **Price** — cheap relative to OpenAI / Anthropic for a model of this quality.

### 77.2 Model choice

`meta-llama/Llama-3.3-70B-Instruct-Turbo`. 70B is the sweet spot: 8B is noticeably less coherent in long multi-turn conversations; 405B is overkill and slower per token.

### 77.3 Switching providers

Config is role-factored:

```python
CHAT_MODEL    = "meta-llama/Llama-3.3-70B-Instruct-Turbo"
CHAT_BASE_URL = TOGETHER_BASE_URL
CHAT_API_KEY  = TOGETHER_API_KEY
```

To move chat to Groq, change those 3 lines. Nothing in pipeline or brain_agent needs to know.

## 78. Ollama as Fallback

### 78.1 Why Ollama

- **Local** — works without internet.
- **Zero config** — `ollama serve` on localhost:11434, pull a model, done.
- **Q&A only** — stateless fallback. No tools, no memory writes.

### 78.2 Model choice

`qwen2.5:7b` — runs comfortably on a laptop GPU, good instruction-following. We only use it when Together.ai is unreachable; it never needs to do the full job.

### 78.3 `ask_offline(text, person_name, history, language, system_note=None)`

The fallback entry point. Takes the same inputs (text + last 10 turns + person name) but produces a single response. No streaming. No function calling. The brain module handles the Ollama HTTP call with a 15-second timeout.

## 79. CloudState Machine

### 79.1 The states

- **ONLINE** — Together.ai is responsive; `ask_stream` routes cloud.
- **SICK** — Together.ai failed one or more calls; next turn uses Ollama. A background `_cloud_retry_loop` pings every 30 seconds.
- **OFFLINE** — reserved for multi-minute outage; same behaviour as SICK for now.

### 79.2 Transitions

```
ONLINE --(call exception)--> SICK
SICK --(background ping OK)--> ONLINE
```

### 79.3 Messaging

When the first call fails:

```
[Brain] Together.ai stream failed: {exception}
[Cloud] State: ONLINE → SICK ({exception class})
```

The user hears a fallback line: "Oops, I'm feeling a bit sick right now... give me a moment to sort myself out." — then the Ollama response.

When recovery:
```
[Cloud] Together.ai recovered — state ONLINE
```

Subsequent turns resume cloud.

### 79.4 Retry loop

Session 22 B8 fixed a bug where the retry loop exited after one success. Now it continues indefinitely; `continue` instead of `return` inside the while loop.

## 80. The Seven Function-Calling Tools

> **Note (Sessions 76 onward).** The tool count grew from 6 to 7 with the addition of `search_room_memory` in Phase 3B.5 (Session 113). The seventh tool is scoped to the current room session's interleaved turn log, which complements the per-person scope of `search_memory`. The descriptions below reflect the current production prompts; the `report_identity_mismatch` and `update_person_name` descriptions were hardened across Sessions 73, 95, 96, 97, 98 after canary runs surfaced misrouting bugs.



### 80.1 `update_person_name`

**Purpose.** The LLM calls this when a speaker tells the system their name ("My name is Chloe") or corrects a mis-attribution.

**Schema.**
```json
{
    "type": "function",
    "function": {
        "name": "update_person_name",
        "description": "...",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "the speaker's correct name"}
            },
            "required": ["name"]
        }
    }
}
```

**Privileges.** All person_types (stranger, known, best_friend, disputed).

**Semantics.**
- Stranger session → promotes to `known`, renames in DB, migrates knowledge (`BrainDB.migrate_entity_name`), rebuilds Kuzu entity (`GraphDB.rebuild_entity_from_knowledge`), promotes shadow node if one exists, clears `waiting_for_name` flag.
- Known or best_friend session → flips session to `disputed` (Session 54/55). Does NOT rename the DB — the speaker's claim conflicts with sensor evidence.
- Disputed session → blocked (Session 54 Finding G); the real person is safe from corruption.

### 80.2 `update_system_name`

**Purpose.** The best friend calls this to name or rename the robot.

**Privileges.** `best_friend` only.

**Semantics.** Updates `system_identity.name` in DB; next system prompt reflects the new name. TTS acknowledges: "Got it, I'll go by {name}."

If already the current name, logs `no-op (already '{name}')` and still returns gracefully.

### 80.3 `search_web`

**Purpose.** Query Tavily for real-time information (news, facts, etc.).

**Privileges.** stranger, known, best_friend.

**Schema.** `{"query": "string"}`

**Semantics.** Called via `ask_stream` tool execution. Cached for 5 minutes per identical query. Time-sensitive queries get automatic date injection. Up to `SEARCH_MAX_PER_TURN=2` sequential calls per turn.

Result format: answer + top snippets concatenated, ≤ 800 chars, injected into the assistant response.

### 80.4 `shutdown`

**Purpose.** Best friend asks the robot to shut down ("go to sleep").

**Privileges.** `best_friend` only.

**Semantics.** Spawns graceful shutdown (`_shutdown_event.set()`). TTS acknowledges "Goodbye!" and the process exits cleanly.

Session 25 B3 added a false-trigger guard — the LLM sometimes called `shutdown` when the user hadn't actually asked. The guard checks the transcript for explicit dismissal keywords before executing.

### 80.5 `search_memory`

**Purpose.** The LLM retrieves relevant stored facts about the current speaker.

**Privileges.** known, best_friend only. Strangers can't search their own memory (they don't have any yet) and can't peek at others'.

**Schema.** `{"query": "string", "scope": "self" | "system"}`

**Semantics.** Routes through BrainDB + EmbeddingAgent semantic search. Returns top K facts above confidence threshold.

### 80.6 `report_identity_mismatch`

**Purpose.** The LLM flags a dispute when the speaker contradicts sensor evidence but doesn't give a replacement name.

**Privileges.** All person_types.

**Schema.** `{"reason": "string"}` — the LLM explains what it observed.

**Semantics.** Flips session to `disputed`. `_disputed_persons.add(pid)` so the BrainOrchestrator pauses extraction. `<<<IDENTITY DISPUTED>>>` block enters the prompt on next turn.

Session 51 Issue #2B added this tool. Before it, the LLM had no way to express "I don't think they are who they claim" without making up a wrong rename.

Sessions 95–98 hardened the description after a cluster of live-canary misroutes. The tool's production description now opens with an **ONLY** clause, enumerates the specific question shapes that are NOT identity denials ("Who were you talking to?", "Who was here?", "Did someone else visit?"), and names `search_memory` as the correct alternative for those question shapes. A 4-item `TRIGGER CHECKLIST` requires all conditions to be true before the call fires (speaker is talking about themselves, denying the sensor, contradicted twice, no replacement name given), and a question-phrase shortcut tells the LLM that utterances containing "who"/"what"/"did" are almost certainly *not* denials.

### 80.7 `search_room_memory` (Phase 3B.5, Session 113)

**Purpose.** Retrieve turns from the current multi-person room session — interleaved across every speaker, sorted chronologically — for questions that span speakers rather than one person's history.

**Privileges.** All person_types (same visibility as the room itself; the room turns already lived behind the same `_visibility_clause` when they were extracted).

**Schema.** `{"query": "string"}` — one search term. The pipeline auto-injects the current `room_session_id` from `_active_room_session`, so the LLM doesn't have to track or pass it.

**Semantics.** Routes through `BrainDB.search_room_turns(room_session_id, query, ...)` in `pipeline._make_room_search_fn`. Returns an empty result with a hint when the room is younger than `SEARCH_ROOM_MEMORY_MIN_TURNS=5` (avoids noisy matches on 1–3 turn rooms) or when `SEARCH_ROOM_MEMORY_ENABLED=False`.

**Good reasons to call (from the tool description).** "What have we talked about tonight?", "When did Lexi mention her interview?", "Did anyone bring up the movie?", "What did we decide about dinner?".

**Do-not-call (also in the description).** Prior sessions — use `search_memory` (per-person scope, different day / different gathering). Last 2–3 turns — already in context. Single-person history questions — use `search_memory`.

**Observability.** On fire: `[Brain] Tool: search_room_memory query='interview' ...`; on the result injection: `[Brain] search_room_memory: N match(es) for 'interview' in room_<id>`; on empty below `SEARCH_ROOM_MEMORY_MIN_TURNS`: `[Brain] search_room_memory: room too young (N<5 turns), returning hint`.

**Why a separate tool, not a `scope` arg on `search_memory`.** The contract is different: `search_memory` is person-scoped (returns facts about one entity, with per-fact `privacy_level` filtering); `search_room_memory` is room-scoped (returns conversation turns, with an implicit "you were participant or owner" boundary). Overloading `scope="room"` on the existing tool would require dynamic arg semantics, make the description block longer, and make retrieval tests harder to reason about. Two tools with clean contracts beat one tool with a mode flag.

## 81. Stream Truncation Handling

### 81.1 When it fires

Post-Obs 3, the condition for retry:
- `response` non-empty.
- `_stream_words ≤ 1`.
- No terminal punctuation (`. ! ? …`).
- `finish_reason in ("length", "content_filter", None)` — authoritative truncation signal.
- No tool calls.
- CloudState ONLINE.

All must be true. Defense in depth: without any one of these, retry is suppressed.

### 81.2 Retry mechanics

- `stop_audio()` cuts the tail of the truncated response.
- `ask_offline` generates the retry via Ollama.
- If the retry is longer than the original, `speak(retry)` plays it.
- History records the retry, not the fragment.

Session 64 Bug 5 + Obs 3 made this robust. The `finish_reason` gate was critical — legitimate short replies like "Hello!" have `finish_reason="stop"` and no longer trigger retry.

## 82. Context Compression — Three Tiers

### 82.1 Tier 1 — MicroCompact (sync)

Truncates individual messages in old history that exceed `MICRO_CHAR_LIMIT=2000` chars. Keeps recent messages intact. Runs every turn as history is built.

### 82.2 Tier 2 — AutoCompact (async LLM)

When estimated tokens (3.5 chars/token heuristic) exceed `TOKEN_COMPACT_THRESHOLD=50000`, async LLM summarises old turns into a bullet list. Keeps `AUTOCOMPACT_KEEP_TURNS=15` recent turn-pairs verbatim; everything older is summarised.

One retry with 2-second backoff on 5xx/network errors (Session 35 Bug-11). 4xx errors skip retry.

### 82.3 Tier 3 — Hard trim

If still over `TOKEN_HARD_LIMIT=100000`, emergency drop oldest turns until budget fits. Logs a warning — this path indicates a failure in Tier 2.

### 82.4 Warning threshold

At `TOKEN_WARN_THRESHOLD=90000` we log `[Brain] Context approaching limit (Ntok)`. Gives human operators a signal without forcing action.

## 83. KAIROS Proactive Wake

### 83.1 Trigger

Every 0.5 seconds, `_kairos_tick()` checks:
- Any active session exists.
- Time since last user speech > `KAIROS_SILENCE_THRESHOLD=30s`.
- Time since last KAIROS fire > `KAIROS_COOLDOWN=120s`.
- Session is not disputed (Session 54 Finding H).
- If there's a pending PatternAnalysisAgent question for this person, prefer it; else let the brain improvise.

### 83.2 The brain call

```python
_kairos_prompt = (
    "The user has been silent for 30 seconds. "
    "If you have something natural to say or ask, say it. "
    "Otherwise respond with the single word SILENT."
)
```

The brain decides — if it responds "SILENT", nothing is spoken and the cooldown still applies (so we don't re-fire immediately). Otherwise, TTS speaks the output.

### 83.3 Why brain-driven

Earlier iterations had deterministic KAIROS questions ("Hey, still there?") that felt robotic. Passing the decision to the brain with a "only speak if natural" instruction produces much better emissions.

### 83.4 Terminal log

```
[KAIROS] Brain proactive wake — 44s silence
[KAIROS] Brain spoke: 'Hey Jagan, is everything okay?'
```

or if SILENT:
```
[KAIROS] Brain proactive wake — 44s silence
[KAIROS] Brain chose silence
```

### 83.5 History and orchestrator

Session 22 B3 made KAIROS log to DB: the user's silence period gets `db.log_turn(pid, "user", "[silence]")` and the brain's response gets logged as assistant. Orchestrator is notified. This keeps the knowledge extraction pipeline consistent — KAIROS-initiated turns are first-class.

---
---

# Part XIV — Knowledge System

The knowledge system is the largest subsystem in the codebase (`core/brain_agent.py` is 6105 lines). Its job is to turn raw conversation transcripts into structured, searchable, evolving knowledge about each person.

## 84. BrainDB Schema

### 84.1 Overview

`brain.db` is a separate SQLite database from `faces.db`. The split is deliberate:
- `faces.db` — identity and conversation log. Core runtime data.
- `brain.db` — derived knowledge, can be wiped and reconstructed from conversation_log.

### 84.2 Tables

| Table | Purpose |
|---|---|
| `knowledge` | Structured facts: (person_id, entity, attribute, value, confidence, captured_at, privacy_level, invalidated_at, ...) |
| `schema_catalog` | Observed attribute names; used for semantic normalisation |
| `agent_log` | Per-turn log of which agents ran, outcomes, latencies |
| `prompt_prefs` | Communication preferences per person (5 types) |
| `object_sightings` | YOLO11 detections (when spatial memory enabled) |
| `object_pattern_questions` | Proactive questions generated from sighting patterns |
| `episodes` | Session summaries by InsightAgent |
| `presence_log` | When people arrived/left (for routine detection) |
| `proactive_nudges` | Hints the brain should consider injecting (VISITOR_ALERT, CROSS_PERSON_HYPOTHESIS, etc.) |
| `watchdog_alerts` | Anomaly signals from WatchdogAgent |
| `social_mentions` | When person A mentions person B |
| `predicate_stats` | Per-attribute contradiction counts (volatility tracking) |
| `household_facts` | Multi-person relationship facts (spouse, parent, cousin) |
| `inter_person_relationships` | Explicit pair relationships |
| `shadow_persons` | Mentioned-but-not-yet-enrolled people |
| `brain_state` | Singleton row tracking `last_turn_id` processed |

### 84.3 `knowledge` — the central table

```sql
CREATE TABLE knowledge (
    id              INTEGER PRIMARY KEY,
    person_id       TEXT NOT NULL,
    entity          TEXT NOT NULL,    -- usually = person's name, sometimes an object
    attribute       TEXT NOT NULL,    -- "favorite_color", "current_mood", etc.
    value           TEXT NOT NULL,
    confidence      REAL NOT NULL,    -- 0-1
    captured_at     REAL NOT NULL,
    contradiction_count INTEGER DEFAULT 0,
    privacy_level   TEXT DEFAULT 'personal',   -- public | personal | household | system_only
    invalidated_at  REAL,                       -- NULL = currently valid
    invalidated_by  INTEGER,                    -- fk to another knowledge.id that superseded this
    stale_penalty   REAL DEFAULT 0.0,           -- RetroScan decrements this
    ...
);
```

The `privacy_level` column is the foundation of the Phase 3A privacy model — it was a 2-tier field (`public` / `private`) through Session 94, and is now a 4-tier field (`public` / `personal` / `household` / `system_only`) as of Session 95 3A.4.5. A one-shot idempotent migration in `BrainDB.__init__` converts legacy `'private'` rows to `'personal'` on first start after the schema change. The default flipped from `'public'` to `'personal'` — fail-closed. Every row written by `ExtractionAgent` carries a tier decided at write time by `_classify_privacy_level` (static map → process cache → LLM fallback). See **Part XXV — Cross-Person Privacy and Safety (Phase 3A)** for the complete story.

### 84.4 Why non-destructive

Deleting facts loses history. `invalidated_at` + `invalidated_by` lets us see the chain of beliefs: Jagan's `current_project` was `"creating an operating system for robots"` at T1, then replaced with `"Kara"` at T2 (with the old row marked invalidated and pointing forward). The past fact is searchable and can be surfaced when relevant.

**Session 105 Bug N addendum.** Non-destructive is not enough on its own for *safety-critical* attributes. When Lexi's `current_mood='suicidal'` was later overwritten by `current_mood='loving'` four turns later during a canary run, the crisis disclosure was effectively erased — the old row sat in the DB with `invalidated_at` set, but no retrieval path surfaced it. The fix is a second attribute family, `expressed_suicidal_thoughts` (and its siblings `mentioned_*`, `reported_*_abuse`, `has_experienced_crisis`), which is append-only by policy: the `ContradictionAgent` short-circuits on any attribute matching `SAFETY_CRITICAL_ATTRIBUTE_PATTERNS` and refuses to REPLACE. The momentary mood keeps its normal overwrite semantics; the historical flag accumulates. See §159 for the full design.

### 84.5 `room_summaries` — the per-room synthesis table (Phase 3B.6)

```sql
CREATE TABLE room_summaries (
    id              INTEGER PRIMARY KEY,
    room_session_id TEXT NOT NULL UNIQUE,
    participants    TEXT NOT NULL,        -- JSON list of person_ids
    started_at      REAL NOT NULL,
    ended_at        REAL NOT NULL,
    topic_tags      TEXT,                 -- JSON list of strings
    safety_flags    TEXT,                 -- JSON list of strings
    summary         TEXT,                 -- LLM narrative, ≤1 paragraph
    turn_count      INTEGER DEFAULT 0
);
CREATE INDEX idx_room_summaries_ended_at ON room_summaries(ended_at DESC);
```

Written by `BrainOrchestrator.synthesize_room` at the end of every multi-person session. Consumed by `get_recent_room_context(person_id, hours=24)` for the `<<<RECENT ROOMS>>>` greeting-enrichment block (Phase 3B.6). See Part XXVI §171.

## 85. BrainOrchestrator

### 85.1 The coordinator

```python
class BrainOrchestrator:
    def __init__(self, db, graph, ...):
        self._triage         = TriageAgent()
        self._extraction     = ExtractionAgent()
        self._contradiction  = ContradictionAgent()
        self._embedding      = EmbeddingAgent()
        self._pref           = PromptPrefAgent()
        self._friction       = FrictionDetectionAgent()
        self._household      = HouseholdExtractionAgent()
        self._pattern        = PatternAnalysisAgent()
        self._nudge          = NudgeAgent()
        self._social         = SocialGraphAgent()
        self._retro          = RetroScanAgent()
        self._watchdog       = WatchdogAgent()
        self._insight        = InsightAgent()
        self._schema_norm    = SchemaNormAgent()
        self._disputed_persons: set[str] = set()
```

### 85.2 The loop

A background task started by `run()`:

```python
async def _loop(self):
    while not self._shutdown:
        new_turns = self._brain_db.fetch_turns_since(last_id)
        for turn in new_turns:
            await self._process_turn(turn)
        await asyncio.sleep(BRAIN_AGENT_POLL_INTERVAL)
```

Polled every 2 seconds; `notify()` can wake it up early.

### 85.3 `notify()` and `notify_session_end()`

- `notify()` — wake the loop immediately (used after each turn).
- `notify_session_end(pid, name)` — schedule session-end synthesis tasks.

Session-end tasks run when a person's session closes:
- PromptPrefAgent full analysis.
- InsightAgent episode storage.
- HouseholdExtractionAgent inference.
- NudgeAgent visitor alert if stranger.
- SocialGraphAgent aggregation.

All gated on dispute state — skipped if the session closed while disputed (Session 53 Finding A).

### 85.4 Dispute gate

```python
if person_id and person_id in self._disputed_persons:
    self._brain_db.log_agent(turn_id, "triage", "skip", "identity disputed")
    return
```

First check in `_process_turn`. If the session is flagged disputed, no extraction. Prevents contradictory facts polluting the wrong pid's knowledge.

### 85.5 `report_dispute_rename_burst(pid, victim_name, victim_type, claimed_name, count, dispute_ts)`

Session 57 N3 added this. When disputed-rename attempts in a single session cross `DISPUTE_RENAME_BLOCK_THRESHOLD=3`, the orchestrator stores a `watchdog_alerts` row with severity `critical` (for best_friend victims) or `warning` (for known victims). Dashboard can surface it.

## 86. TriageAgent

### 86.1 Purpose

Fast no-LLM filter. Decides whether a turn is worth extracting facts from.

### 86.2 Rules

- Skip turns with `role == "assistant"` — only user turns produce new facts.
- Skip turns shorter than `BRAIN_AGENT_MIN_WORDS=4` — too little signal.
- Skip turns from disputed persons.
- Skip turns with `[silence]` content (KAIROS silence markers).

### 86.3 Log format

```
[BrainAgent] HH:MM:SS.mmm Triage: PASS turn N — processing
[BrainAgent] HH:MM:SS.mmm Triage: SKIP turn N — assistant turn
```

### 86.4 Cost

~1ms. Zero LLM tokens.

## 87. ExtractionAgent

### 87.1 Purpose

Call the LLM to turn a conversation turn into a JSON list of (entity, attribute, value) facts.

### 87.2 Prompt

The prompt includes:
- Current turn text.
- Last `BRAIN_AGENT_CONTEXT_TURNS=6` turns as context.
- Instructions to emit structured JSON.
- The speaker's name.

Example output:
```json
[
  {"entity": "Jagan", "attribute": "favorite_car", "value": "BMW M2", "confidence": 0.90},
  {"entity": "Jagan", "attribute": "preferred_transmission_type", "value": "manual", "confidence": 0.80}
]
```

### 87.3 Validation

JSON parsing, whitespace-trim, lowercase attribute normalisation (`Favorite_Car` → `favorite_car`).

### 87.4 Retry (Bug 6 post-review)

`EXTRACT_MAX_RETRIES=2` extra attempts on transient network errors (`httpx.ReadTimeout`, `httpx.ConnectTimeout`, `httpx.NetworkError`). Exponential backoff (1s, 2s). 4xx errors propagate — not retried.

### 87.5 Log format

```
[BrainAgent] HH:MM:SS.mmm Extracted N fact(s) (Nms): Jagan.attr='val', ...
```

## 88. ContradictionAgent

### 88.1 Purpose

When a new fact `(entity, attribute, value)` arrives, check whether it contradicts an existing fact with the same `(entity, attribute)` but different value.

### 88.2 The check

For each new fact:
1. SELECT existing knowledge rows with the same entity+attribute AND `invalidated_at IS NULL`.
2. If none exist → new fact, insert normally.
3. If one exists with the same value → `COMPATIBLE` (just bump confidence with CONFIDENCE_BOOST).
4. If one exists with a different value → call LLM with both values and ask REPLACE or COMPATIBLE.
5. On REPLACE → set old row's `invalidated_at`, insert new row, increment `contradiction_count`.
6. On COMPATIBLE → insert new row alongside (multiple valid values, e.g., multiple hobbies).

### 88.3 Log format

```
[BrainAgent] Contradiction check (Nms): K replaced, L compatible, M new
```

### 88.4 Triggers RetroScan

When a REPLACE happens, `RetroScan` is invoked on up to `MAX_RETROACTIVE_FACTS=5` nearby facts. See §97.

## 89. EmbeddingAgent

### 89.1 Purpose

Semantic embeddings for knowledge rows. Enables `search_memory` to find "facts about cars" without knowing the exact attribute names.

### 89.2 Model

`intfloat/multilingual-e5-large-instruct` via Together.ai. 1024-d embeddings. Instruction-formatted input:

```
Instruction: represent the personal fact for retrieval: Jagan's favorite car is BMW M2.
```

### 89.3 In-memory cache

Keyed by SHA-256 of the input string. Max 1000 entries. Evicted LRU.

### 89.4 Retry

Same pattern as ExtractionAgent: `EMBED_MAX_RETRIES=2` extra attempts on transient errors (Session 24 A8). This is the pattern we reused for Bug 6.

### 89.5 `semantic_search_knowledge(pid, query, top_k)`

Embeds the query, computes cosine similarity against all stored knowledge embeddings for this person (and the person's household if scope=system), returns top K above `EMBED_MIN_CONFIDENCE=0.60`.

## 90. GraphDB — Kuzu

### 90.1 Why a graph

Querying "what does Jagan know about cars" via SQL would be ugly and slow. As a graph query, it's a one-hop traversal from a Person node through MENTIONED edges to Entity nodes.

### 90.2 Schema (v2)

```
Node: Person (name PK, face_id UNIQUE)
Node: Entity (name PK)
Rel:  MENTIONED (from Person to Entity, with properties: count, last_mentioned, shared)
Rel:  RELATES_TO (from Person to Person, with: type, strength)
```

### 90.3 Auto-rebuild on schema bump

`GRAPH_SCHEMA_VERSION=2`. Stored schema version is checked at startup. If different, the graph is wiped and rebuilt from `knowledge` rows. This is the migration mechanism — we don't write migration scripts.

### 90.4 Kuzu self-heal (Session 58)

A corrupted Kuzu directory used to crash startup. Fix: wrap `kuzu.Database()` in try/except, wipe the path + retry once. Knowledge rows are the source of truth; rebuild is deterministic.

### 90.5 `find_shared_entities(name_a, name_b)`

Returns entities both persons have mentioned. Used by NudgeAgent for CROSS_PERSON_HYPOTHESIS.

## 91. PromptPrefAgent

### 91.1 Purpose

Infer and store communication preferences so the brain can adapt its style per person.

### 91.2 Five preference types

1. **communication_style** — formal vs casual vs playful.
2. **response_length** — brief vs detailed.
3. **greeting_style** — warm vs perfunctory.
4. **response_habit** — avoid starters, avoid filler, etc.
5. **topic_interest** — areas they want to hear about.

### 91.3 Staging and auto-confirm

Each pref starts `staged`. After seeing the same pref `PREF_AUTO_CONFIRM_THRESHOLD=3` sessions in a row without contradiction, it becomes `activated`. Only activated prefs are injected into the prompt addendum.

### 91.4 Intra-session pass

Every `INTRA_PREF_TURN=15` turns, a lightweight analysis runs on the last `INTRA_PREF_TURNS_LIMIT=6` turns to detect emerging prefs mid-session. The result may be "addendum injected" for the next turn (nudge rather than confirm).

### 91.5 Session-end analysis

On `notify_session_end`, a full analysis runs on the last `PREF_ANALYSIS_TURNS=40` turns of the session. Any new staged pref is written; existing prefs are bumped in sessions_seen count.

## 92. FrictionDetectionAgent

### 92.1 Purpose

Detect when a person's observed behaviour contradicts an active preference.

### 92.2 Example

Active pref: `response_length = "brief — keep under 2 sentences"`. Observed: the brain just emitted a 5-sentence reply. Friction detected. Next turn, the addendum escalates the injection urgency: the active pref appears with stronger wording.

### 92.3 Escalation n+1

If friction persists, the injection gets more forceful each session until either the behaviour aligns or the user explicitly revokes the pref.

### 92.4 When not to fire

Below `FRICTION_MIN_CONFIDENCE=0.70` the pref is considered too weak to enforce.

## 93. HouseholdExtractionAgent

### 93.1 Purpose

Extract household-level facts: who lives together, family relationships, shared spaces.

### 93.2 Outputs

- `household_facts` rows — facts that apply to the household as a whole.
- `inter_person_relationships` rows — explicit (A, relationship, B) tuples.
- `shadow_persons` rows — people mentioned but not enrolled.

### 93.3 Provisional → settled

A household fact starts `provisional`. After `HOUSEHOLD_DISPUTE_SETTLE_SESSIONS=2` sessions of corroboration without contradiction, it becomes `settled`.

### 93.4 Shadow person promotion

When someone enrolls whose name matches a shadow_persons entry (phonetic match), the shadow is promoted to a real person. Its existing facts attach to the new pid via `BrainOrchestrator.promote_shadow_to_confirmed`.

## 94. PatternAnalysisAgent

### 94.1 Purpose

Analyse object sightings (YOLO11 when enabled) for interesting behavioural patterns. Generate proactive questions the robot can ask naturally during lulls.

### 94.2 Triggers

Runs when `object_sightings` has ≥ `PATTERN_MIN_SIGHTINGS=30` rows; cooldown `PATTERN_COOLDOWN=3600s`.

### 94.3 Output

Questions stored in `object_pattern_questions` with confidence. KAIROS consumes them — when the user is silent, the brain may grab a pending pattern question.

### 94.4 Currently disabled

`VISION_YOLO_ENABLED=False`. We haven't turned on spatial memory vision yet. The agent is wired but inactive. Turning it on is a config flip.

## 95. NudgeAgent

### 95.1 Purpose

Write `proactive_nudges` rows that the brain can surface in future turns.

### 95.2 Nudge types

- **VISITOR_ALERT** — a stranger visited while best_friend was absent. Generated on session-end for stranger sessions with ≥ 1 user turn.
- **CROSS_PERSON_HYPOTHESIS** — two enrolled people both mentioned the same entity. Maybe they're connected.
- **ROUTINE_DEVIATION** — person arrived later than usual (RoutineAgent).
- **PATTERN_QUESTION** — pulled from PatternAnalysisAgent.

### 95.3 Template fix (Bug 3 post-review)

Session 64 Bug 3 fixed `(possibly your null)` rendering when the relationship field was the string `"null"` or `"None"`. Both graph-match (line 4458) and fuzzy-match (line 4503) paths reject these.

### 95.4 Expiry

Nudges expire after `NUDGE_EXPIRY_HOURS=72`. Max `CROSS_PERSON_MAX_NUDGES=3` pending per person.

## 96. SocialGraphAgent

### 96.1 Purpose

Track which person mentions which other person in their conversations.

### 96.2 `social_mentions` table

```sql
CREATE TABLE social_mentions (
    id                INTEGER PRIMARY KEY,
    source_person_id  TEXT NOT NULL,
    name              TEXT NOT NULL,    -- mentioned name (may be shadow)
    relationship      TEXT,             -- "friend", "mother", etc. or NULL
    context           TEXT,
    count             INTEGER DEFAULT 1,
    last_mentioned    REAL NOT NULL,
    ...
);
```

### 96.3 Usage

- NudgeAgent uses it for CROSS_PERSON_HYPOTHESIS.
- HouseholdAgent uses it to infer relationships.
- Log format: `[SocialGraph] Mention stored: {name} ({relationship}) — []`

## 97. RetroScan

### 97.1 Purpose

When a fact is REPLACEd, look back at related facts for staleness.

### 97.2 Mechanism

Call an LLM on up to `MAX_RETROACTIVE_FACTS=5` nearby facts (by attribute similarity) with both the old value, the new value, and the neighbour fact. The LLM returns STALE or VALID.

STALE verdicts apply `RETRO_STALE_PENALTY=0.15` to the neighbour's confidence via `stale_penalty` column.

### 97.3 Log format

```
[RetroScan] Stale: Jagan.recent_focus (-0.15) — The related fact "developing a system" is still generally true, but its specificity has decreased...
```

### 97.4 Non-destructive

STALE doesn't delete. The confidence drop may eventually push the fact below `DREAM_PRUNE_FLOOR=0.15` where dream consolidation invalidates it.

## 98. WatchdogAgent

### 98.1 Purpose

Detect anomalies and store `watchdog_alerts` for dashboard surfacing.

### 98.2 Alert types

- `SILENT_OBS_SPIKE` — sudden jump in silent_observations rows (new strangers in frame).
- `UNUSUAL_HOUR_ACTIVITY` — activity between WATCHDOG_UNUSUAL_HOUR_START and WATCHDOG_UNUSUAL_HOUR_END (0-5am).
- `DISPUTE_RENAME_BURST` — from Session 57 N3; fires when a single session crosses DISPUTE_RENAME_BLOCK_THRESHOLD=3.
- `ANTISPOOF_SPIKE` — sustained anti-spoof rejections.

### 98.3 Interval

Runs every `WATCHDOG_INTERVAL=60s`.

### 98.4 Alert schema

```sql
CREATE TABLE watchdog_alerts (
    id         INTEGER PRIMARY KEY,
    kind       TEXT NOT NULL,
    severity   TEXT NOT NULL,  -- info/warning/critical
    metadata   TEXT,            -- JSON
    created_at REAL NOT NULL,
    resolved_at REAL
);
```

## 99. InsightAgent

### 99.1 Purpose

At session end, produce a short episode summary — a ~100-token narrative of what happened in the session, the dominant mood, the significance.

### 99.2 Schema

```sql
CREATE TABLE episodes (
    id              INTEGER PRIMARY KEY,
    person_id       TEXT NOT NULL,
    session_start_ts REAL NOT NULL,
    session_end_ts   REAL NOT NULL,
    turn_count      INTEGER,
    summary         TEXT,
    mood            TEXT,        -- neutral, positive, negative
    significance    REAL,        -- 0-1
    ...
);
```

### 99.3 Thresholds

Skip when session has `< INSIGHT_MIN_TURNS=3`. LLM output capped at `INSIGHT_MAX_TOKENS=300`.

### 99.4 Uses

- `run_intention_followup` checks episodes for unfollowed promises ≥ 24h old.
- Dashboard can show a timeline.
- LLM can pull episodes via search_memory if relevant.

