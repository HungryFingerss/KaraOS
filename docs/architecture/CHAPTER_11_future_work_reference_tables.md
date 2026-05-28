> **CHAPTER 11 — Future Work + Reference Tables** | Sourced from `everything_about_system.md` §141-149 (verbatim mechanical extraction per Plan v2 §1.6 section-number stability invariant).

---

## 141. ReSpeaker Barge-In

The 4-mic ReSpeaker array will give us:
- Beamforming (directional mic).
- Hardware echo cancellation.
- Stronger VAD signal-to-noise.

With these, we can re-enable `_vad_interrupt_listener` that was removed in Session 2 due to self-interrupt issues on the laptop mic. The pipeline code has a comment at the removal site: "Do NOT re-add `_vad_interrupt_listener` until ReSpeaker hardware arrives."

## 142. Jetson Deployment Checklist

When the Jetson arrives:

1. Clone repo; create venv.
2. `pip install faiss-gpu` instead of faiss-cpu.
3. Verify buffalo_l auto-downloads.
4. CUDA 12.x + cuDNN 9.x matching onnxruntime-gpu version.
5. V4L2 backend: automatic via `sys.platform != "win32"` check.
6. `loop.add_signal_handler(SIGTERM, ...)` path becomes active.
7. Smoke test: first-boot flow, multi-person routing, dispute.
8. Export Whisper + AdaFace + RetinaFace to TensorRT for ~2x latency reduction.
9. systemd service for auto-start on boot.
10. Physical robot integration via `robot.py` (§144).
11. **CI on Jetson** — slow-test workflow (`.github/workflows/slow.yml`) must be runnable from a self-hosted Jetson runner. Currently both CI workflows run on `ubuntu-latest`. The model-heavy tests aren't representative of Jetson-side behavior. Open.
12. **Power management for the always-on listening loop** — see §143.

## 143. openWakeWord Push-to-Talk

Current design: the pipeline is always listening. Mic is always on. This is fine on mains-powered dev but bad on battery.

openWakeWord would let us gate everything on a wake word — the system is in low-power listening until someone says "Kara" (or whatever the wake word is), then jumps into the full pipeline.

Tradeoff: wake-word false-rejects feel worse than always-on. Decision pending user testing.

## 144. `robot.py` Hardware Abstraction

When physical actuators arrive (head pan/tilt, tail wag, LED eyes), we need a clean boundary between "pipeline thinks" and "robot moves." The plan is a `core/robot.py` module with methods like `look_at(azimuth, elevation)`, `express(mood)`, `tail_wag(intensity)`.

The pipeline calls these at semantic boundaries; the robot module translates to servo commands. Mocks during dev so nothing breaks before hardware lands.

The decomposition will benefit from P1.A (Part LI §336) — once `pipeline.py` is split into ~30 focused modules, `robot.py` is a natural addition that consumes events from the event log (Part XLIX) and emits actuator commands, without needing to be threaded through a 10000-line monolithic pipeline.

## 145. Q3 — History Architecture Redesign

**Status: schema-side landed in Session 107 / P0.0.7; retrieval-side pending RoomOrchestrator.**

Pre-Phase-3B, `conversation_log` was per-person. A turn in a multi-person scene belonged to the speaker but was overheard by everyone. The Phase 3B work (Part XXVI) introduced room awareness via the `<<<ROOM>>>` block, but the underlying schema was still per-person.

Phase 3A.6 / Session 107 added two columns to `conversation_log`:
- `room_session_id` — the room context the turn happened in.
- `audience_ids` — JSON array of pids allowed to see the turn.

Plus a new index `idx_conv_log_room` for room-scoped queries.

Session 111 added a third column:
- `addressed_to` — pid the assistant turn was addressed to (for `[addressing:X]` marker disambiguation).

**Schema is in place.** Retrieval-side wiring lands when RoomOrchestrator ships (currently deferred under Phase 3B follow-up). At that point, `<<<SHARED CONTEXT>>>` block will pull recent shared turns from `conversation_log` filtered by `room_session_id` AND privacy via the existing `_visibility_clause` (Part XXV §152). The Kuzu v3 schema bump (Part LI §338) lands alongside.

The deferral is intentional. The schema is forward-compatible; existing per-person retrieval paths continue to work. RoomOrchestrator can land in a separate sub-PR cycle without touching the data layer.

---
---

# Part XXIV — Appendices

## 146. Glossary

- **AdaFace** — The face embedding model we use. IR101 backbone, 512-d output.
- **Anti-spoof** — MiniFASNet ensemble that rejects photo/screen-replay attacks.
- **Bootstrap credits** — Path C of voice accumulation; free accumulations granted at engagement gate.
- **BrainDB** — SQLite database at `faces/brain.db` holding structured knowledge.
- **BrainOrchestrator** — Coordinator that runs all 15+ knowledge agents.
- **Centroid gate** — Anti-poisoning check: new embedding must be close to gallery centroid.
- **Companion (vs Assistant)** — The design philosophy that prioritises presence over task completion.
- **Dispute** — A session state where speaker claim contradicts sensor evidence.
- **Dream** — Idle-triggered knowledge consolidation.
- **ECAPA-TDNN** — Speaker embedding model from SpeechBrain.
- **Engagement gate** — Strangers must say the system name before the system responds.
- **Evidence dict** — The `identity_evidence` dict on each session.
- **FaceDB** — The `FaceDB` class in `core/db.py`; SQLite + FAISS.
- **FAISS** — Facebook AI Similarity Search; exact and approximate nearest-neighbour library.
- **First-boot flow** — The dialogue flow for enrolling the best friend on a fresh install.
- **Function calling** — LLM capability to emit structured tool call requests.
- **KAIROS** — Proactive wake mechanism that pokes the brain during user silence.
- **Kokoro** — Primary TTS model; ONNX runtime.
- **Kuzu** — Embedded property graph database.
- **MiniFASNet** — Anti-spoof model architecture (vendored from minivision-ai).
- **Ollama** — Local LLM server used as fallback when Together.ai is unreachable.
- **Path A / B / C** — Three paths through which voice accumulation can be granted.
- **person_type** — One of {stranger, known, best_friend, disputed}.
- **PipelineState** — Enum of {WATCHING, LISTENING, THINKING, SPEAKING, ENROLLING}.
- **Progressive enrollment** — Enrolling a stranger who just passed the engagement gate.
- **RetinaFace** — Face detector from InsightFace buffalo_l pack.
- **RetroScan** — Post-contradiction scan for stale neighbour facts.
- **Session** — A live interaction with one person; `_active_sessions[pid]`.
- **Silent observation** — A face seen but never engaged; stored separately from persons.
- **Smart-Turn** — Neural end-of-turn classifier; ~8MB ONNX.
- **SORT** — Simple Online and Realtime Tracking; Kalman + Hungarian for track persistence.
- **system_name** — The robot's name, given by the best friend. Default "Dog".
- **TOOL_PRIVILEGES** — Fail-closed table mapping tool name → allowed person_types.
- **Together.ai** — Cloud LLM provider for primary chat + extraction + embeddings.
- **TTFT** — Time To First Token, a streaming LLM latency metric.
- **V1 / V2 / V3 / V4** — Face quality gates: size/blur, yaw, temporal pool, adaptive threshold.

## 147. Full Config Constant Table

This table lists every tunable constant in `core/config.py` with its current value and purpose.

| Constant | Value | Purpose |
|---|---|---|
| `RECOGNITION_THRESHOLD` | 0.28 | Face cosine threshold for "known" verdict |
| `DETECTION_CONFIDENCE` | 0.50 | RetinaFace min confidence |
| `EMBEDDING_DIM` | 512 | AdaFace output dim |
| `VOICE_RECOGNITION_THRESHOLD` | 0.25 | Voice cosine EER threshold |
| `VOICE_SPEAKER_SWITCH_THRESHOLD` | 0.50 | Min to switch session to a different voice |
| `MAX_VOICE_EMBEDDINGS` | 20 | Per-person cap |
| `VOICE_EMBEDDING_DIM` | 192 | ECAPA-TDNN output dim |
| `VOICE_DIVERSITY_THRESHOLD` | 0.85 | Skip too-similar voice sample |
| `N_INITIAL_VOICE` | 5 | First N bypass diversity |
| `DIARIZE_WINDOW_SECS` | 0.50 | Diarization window |
| `DIARIZE_HOP_SECS` | 0.25 | Diarization hop |
| `DIARIZE_CHANGE_THRESH` | 0.70 | Boundary cosine threshold |
| `DIARIZE_MIN_SECS` | 2.00 | Min utterance length to diarize |
| `SELF_UPDATE_THRESHOLD` | 0.45 | Min cosine for recognition_update |
| `SELF_UPDATE_COOLDOWN` | 30 | Seconds between self-updates per person |
| `SELF_UPDATE_CENTROID_MIN` | 0.55 | Centroid gate for recognition_update |
| `MAX_EMBEDDINGS` | 50 | Per-person face cap |
| `FACE_DIVERSITY_THRESHOLD` | 0.92 | Skip too-similar face sample |
| `FACE_QUALITY_PRESENCE` | 0.05 | Face detectably present |
| `FACE_QUALITY_RECOGNITION` | 0.20 | Recognition viable |
| `FACE_QUALITY_ENROLLMENT` | 0.50 | Gate for enrollment write |
| `FACE_QUALITY_SELF_UPDATE` | 0.70 | Gate for self-update write |
| `N_INITIAL_FACE` | 5 | First N face embeddings bypass diversity |
| `VALID_PERSON_TYPES` | frozenset(...) | Asserted at every write |
| `VOICE_ROUTING_MIDRANGE_SWITCH_MIN` | 0.30 | Priority 2 floor |
| `VOICE_ROUTING_SELF_MATCH_FLOOR` | 0.30 | Priority 3 absolute floor |
| `VOICE_ROUTING_SELF_MATCH_OFFSCREEN` | 0.45 | Priority 3 offscreen floor |
| `N_INITIAL_VOICE_BOOTSTRAP` | 6 | Path C credits at engagement |
| `VOICE_ACCUM_FACE_WITNESS_MIN_CONF` | 0.45 | Path A face conf floor |
| `VOICE_ACCUM_FACE_WITNESS_MAX_AGE_SEC` | 10.0 | Path A face freshness |
| `VOICE_ACCUM_VOICE_SELF_MATCH_MIN` | 0.45 | Path B voice floor |
| `VOICE_ACCUM_MATURE_SAMPLE_COUNT` | 5 | Path B maturity bar |
| `IDENTITY_EVIDENCE_BLOCK_ENABLED` | True | Inject `<<<IDENTITY EVIDENCE>>>` |
| `TOOL_PRIVILEGES` | {...} | Privilege table |
| `GREET_COOLDOWN` | 300 | Seconds between greetings |
| `FACE_LOSS_GRACE` | 10 | Face-session expiry |
| `VOICE_SESSION_TIMEOUT` | 30 | Voice-session expiry |
| `VAD_SWITCH` | False | RMS vs Silero |
| `VAD_THRESHOLD` | 0.5 | Silero cutoff |
| `RMS_THRESHOLD` | 0.01 | RMS speech cutoff |
| `SILENCE_DURATION` | 1.5 | Hard end-of-turn fallback |
| `FILLER_ENABLED` | False | "Hmm..." fillers |
| `MIC_SAMPLE_RATE` | 16000 | |
| `SMART_TURN_SILENCE` | 0.5 | Trigger silence for Smart-Turn |
| `SMART_TURN_THRESHOLD` | 0.80 | Turn-complete confidence |
| `SMART_TURN_ADDENDUM` | 0.5 | Grace window |
| `LIP_MAX_EXTENSION` | 2.0 | Max lip-tracking extension |
| `ADDENDUM_ONSET_WINDOW` | 0.10 | Re-listen window after turn |
| `SPEAKER_LANGUAGES` | ["en"] | Whisper auto-detect candidates |
| `OLLAMA_MODEL` | qwen2.5:7b | Local fallback |
| `CHAT_MODEL` | Llama-3.3-70B-Turbo | Primary LLM |
| `EXTRACT_MODEL` | same | Background extraction |
| `EMBED_MODEL` | multilingual-e5-large-instruct | Semantic embeddings |
| `EMBED_MAX_RETRIES` | 2 | |
| `EXTRACT_MAX_RETRIES` | 2 | |
| `CLOUD_OFFLINE_TIMEOUT` | 120 | Seconds to OFFLINE |
| `CLOUD_RETRY_INTERVAL` | 30 | Retry ping interval |
| `STRANGER_REQUIRE_SYSTEM_NAME` | True | Engagement gate |
| `TAVILY_SEARCH_DEPTH` | advanced | |
| `TAVILY_MAX_RESULTS` | 5 | |
| `SEARCH_CACHE_TTL_SECS` | 300 | |
| `SEARCH_MAX_PER_TURN` | 2 | |
| `ANTISPOOFING_ENABLED` | True | |
| `ANTISPOOFING_THRESHOLD` | 0.5 | live_prob floor |
| `LOG_ANTISPOOF_PROBS` | False | Per-frame debug |
| `LOG_ANTISPOOF_SUMMARY` | True | Rolling summary |
| `LOG_ANTISPOOF_SUMMARY_INTERVAL` | 100 | Summary frequency |
| `LOG_TIME_FORMAT` | `%H:%M:%S.%f` | |
| `LOG_LATENCY_ENABLED` | True | |
| `LOG_STT_MAX_CHARS` | 0 | 0 = no truncation |
| `AUTOCOMPACT_KEEP_TURNS` | 15 | |
| `MICRO_CHAR_LIMIT` | 2000 | |
| `TOKEN_CHARS_PER_TOKEN` | 3.5 | |
| `TOKEN_COMPACT_THRESHOLD` | 50000 | |
| `TOKEN_WARN_THRESHOLD` | 90000 | |
| `TOKEN_HARD_LIMIT` | 100000 | |
| `HOUSEHOLD_DISPUTE_SETTLE_SESSIONS` | 2 | |
| `DEFAULT_SYSTEM_NAME` | Dog | |
| `BRAIN_AGENT_POLL_INTERVAL` | 2.0 | |
| `BRAIN_AGENT_CONTEXT_TURNS` | 6 | |
| `BRAIN_AGENT_MIN_WORDS` | 4 | |
| `PREF_AUTO_CONFIRM_THRESHOLD` | 3 | |
| `PREF_ANALYSIS_TURNS` | 40 | |
| `SCHEMA_NORM_TRIGGER` | 30 | |
| `SCHEMA_NORM_THRESHOLD` | 0.97 | |
| `SCHEMA_NORM_DISTINCT_FAMILIES` | (...) | |
| `SCHEMA_NORM_AMBIGUOUS` | 0.72 | |
| `CONFIDENCE_BOOST` | 0.08 | |
| `INTRA_PREF_TURN` | 15 | |
| `INTRA_PREF_TURNS_LIMIT` | 6 | |
| `FRICTION_MIN_CONFIDENCE` | 0.70 | |
| `PREDICATE_VOLATILITY_THRESHOLD` | 3 | |
| `PREDICATE_CONFIDENCE_CAP` | 0.75 | |
| `PRIVATE_ATTRIBUTES` | {...} | |
| `SCENE_STALE_SECS` | 5.0 | |
| `VOICE_ROUTING_FACE_STALE_SECS` | 2.0 | |
| `SCENE_BLOCK_ENABLED` | True | |
| `SCENE_VOICE_STALE` | 30.0 | |
| `CONVERSATION_HISTORY_LIMIT` | 100 | |
| `KNOWLEDGE_MAX_ROWS` | 2000 | |
| `PRESENCE_MAX_ROWS` | 1000 | |
| `EPISODE_MAX_ROWS` | 500 | |
| `SOCIAL_MENTIONS_MAX_ROWS` | 500 | |
| `WATCHDOG_MAX_AGE_DAYS` | 30 | |
| `AGENT_LOG_MAX_AGE_DAYS` | 30 | |
| `AGENT_LOG_MAX_ROWS` | 50000 | |
| `PATTERN_Q_MAX_AGE_DAYS` | 7 | |
| `DREAM_IDLE_MINUTES` | 5 | |
| `DREAM_COOLDOWN` | 3600 | |
| `DREAM_MAX_INTERVAL` | 10800 | |
| `STRANGER_TTL_DAYS` | 7 | |
| `STRANGER_VOICE_TTL_DAYS` | 3 | |
| `DISPUTE_MAX_DURATION` | 180 | |
| `DISPUTE_RENAME_BLOCK_THRESHOLD` | 3 | |
| `DREAM_PRUNE_FLOOR` | 0.15 | |
| `DREAM_DECAY_WRITE_THRESHOLD` | 0.005 | |
| `DECAY_LAMBDA` | 0.002 | |
| `MAX_RETROACTIVE_FACTS` | 5 | |
| `RETRO_STALE_PENALTY` | 0.15 | |
| `GRAPH_SCHEMA_VERSION` | 2 | |
| `EMOTION_ENABLED` | True | |
| `EMOTION_WINDOW` | 5 | |
| `EMOTION_MIN_SCORE` | 0.40 | |
| `EMOTION_FACT_VALIDITY_HOURS` | 4.0 | |
| `EMOTION_WINDOW_TTL_SECS` | 90 | |
| `SORT_DETECT_EVERY` | 5 | |
| `SORT_MAX_AGE` | 30 | |
| `SORT_MIN_HITS` | 2 | |
| `EMBED_DIM` | 1024 | |
| `EMBED_TOP_K` | 10 | |
| `EMBED_MIN_CONFIDENCE` | 0.60 | |
| `KAIROS_SILENCE_THRESHOLD` | 30.0 | |
| `KAIROS_COOLDOWN` | 120.0 | |
| `PATTERN_MIN_SIGHTINGS` | 30 | |
| `PATTERN_COOLDOWN` | 3600 | |
| `PATTERN_MAX_QUESTIONS` | 5 | |
| `PATTERN_ANALYSIS_DAYS` | 7 | |
| `PATTERN_MIN_CONF` | 0.70 | |
| `VISION_YOLO_ENABLED` | False | |
| `VISION_YOLO_MODEL` | yolo11s.pt | |
| `VISION_DETECT_EVERY` | 15 | |
| `VISION_DETECT_CONF` | 0.40 | |
| `VISION_SIGHTING_GAP` | 60 | |
| `VISION_MAX_SIGHTINGS` | 5000 | |
| `BRIEFING_MIN_ABSENCE` | 1800 | |
| `INSIGHT_MIN_TURNS` | 3 | |
| `INSIGHT_MAX_TOKENS` | 300 | |
| `EPISODE_TOPIC_MATCH_DAYS` | 30 | |
| `MIN_PRESENCE_SESSIONS` | 5 | |
| `ROUTINE_STD_THRESHOLD` | 2.0 | |
| `PRESENCE_DEVIATION_HOURS` | 2.0 | |
| `NUDGE_MIN_CONFIDENCE` | 0.40 | |
| `NUDGE_FUZZY_MATCH_RATIO` | 80 | |
| `NUDGE_EXPIRY_HOURS` | 72.0 | |
| `CROSS_PERSON_MAX_NUDGES` | 3 | |
| `WATCHDOG_INTERVAL` | 60.0 | |
| `WATCHDOG_SILENT_OBS_SPIKE` | 5 | |
| `WATCHDOG_UNUSUAL_HOUR_START` | 0 | |
| `WATCHDOG_UNUSUAL_HOUR_END` | 5 | |
| `IDENTITY_SOFT_THRESHOLD` | 0.35 | |
| `IDENTITY_ASK_THRESHOLD` | 0.65 | |
| `IDENTITY_AUTO_THRESHOLD` | 0.85 | |
| `SILENT_OBS_SIMILARITY` | 0.82 | |
| `SILENT_OBS_RETENTION_DAYS` | 45 | |
| `SILENT_OBS_SCAN_DAYS` | 7 | |
| `HISTORY_OVERRIDE_TOOLS` | {update_person_name, update_system_name} | |
| `TOOL_REPEAT_MAX_CONSECUTIVE` | 2 | |
| `PRIVACY_LEVELS` | frozenset{public, personal, household, system_only} | Phase 3A closed-world tier enum |
| `PRIVACY_LEVEL_DEFAULT` | "personal" | Fail-closed default for novel attributes |
| `PRIVACY_LEVEL_STATIC_MAP` | dict (22 entries) | Fast-path attribute → tier; bypasses LLM classifier |
| `PRIVACY_CLASSIFIER_TIMEOUT_SECS` | 5.0 | LLM fallback timeout (matches `_classify_intent`) |
| `PRIVACY_CLASSIFIER_MAX_TOKENS` | 150 | Tight JSON envelope budget |
| `SAFETY_CRITICAL_ATTRIBUTE_PATTERNS` | frozenset of regex | `expressed_*_thoughts`, `mentioned_*`, `reported_*_abuse`, `has_experienced_crisis` — append-only |
| `SHADOW_NAME_BLOCKLIST` | frozenset (~36 entries) | Prevents HouseholdAgent from creating shadow nodes for pronouns / relationship roles |
| `CROSS_PERSON_PRIVACY_BLOCK_ENABLED` | True | Gate for the refusal + owner variants |
| `VISITOR_CONTEXT_BLOCK_ENABLED` | True | Gate for `<<<VISITOR CONTEXT>>>` (fires on `[visitor_id:` marker in prompt_addendum) |
| `STRANGER_IDENTITY_BLOCK_ENABLED` | True | Gate for `<<<STRANGER IDENTITY>>>` promotion nudge |
| `STRANGER_IDENTITY_BLOCK_MIN_TURNS` | 2 | Min user turns before nudge fires |
| `HONESTY_POLICY_BLOCK_ENABLED` | True | Gate for `<<<HONESTY POLICY>>>` |
| `HEDGED_NAMING_CONTRACT_ENABLED` | True | Gate for `<<<HEDGED NAMING CONTRACT>>>` |
| `INTENT_CONTRACT_BLOCK_ENABLED` | False | Gate for the deprecated `<<<STRUCTURED OUTPUT CONTRACT>>>` (off as of Session 79) |
| `INTENT_LABELS` | frozenset of 12 strings | Phase 1 classifier output enum |
| `TOOL_INTENT_MAP` | dict | Tool name → (required_intent, arg_key) for 4 mutation tools (search_web removed S79) |
| `INTENT_CONFIDENCE_MIN` | 0.75 | General classifier gate |
| `INTENT_SHUTDOWN_CONF_MIN` | 0.80 | Higher-blast-radius gate for shutdown |
| `INTENT_CLASSIFIER_TIMEOUT_SECS` | 10.0 | Bumped from 5 → 8 → 10 across sessions 77, 79 |
| `INTENT_CLASSIFIER_MAX_TOKENS` | 500 | Bumped from 300 in S78 |
| `INTENT_FALLBACK_TO_REGEX` | True | Dual-gate (classifier primary, regex safety net). Flip at P1.17 |
| `INTENT_SHADOW_MODE_ENABLED` | True | Whether classifier fires at all |
| `ADDRESS_DECISION_BLOCK_ENABLED` | True | Gate for multi-person `[addressing:X]` marker arbitration |
| `BATCH_GREETING_ENABLED` | True | LLM-decided greeting order for simultaneous arrivals |
| `BATCH_GREETING_MIN_PEOPLE` | 2 | Min people to trigger LLM call |
| `BATCH_GREETING_LLM_TIMEOUT_SECS` | 1.0 | Fallback to detection order on timeout |
| `ROOM_BLOCK_ENABLED` | True | Gate for `<<<ROOM>>>` block |
| `ROOM_BLOCK_TURN_CAP` | 10 | Max interleaved turns rendered |
| `TURN_ARBITRATION_ENABLED` | True | Gate for TURN ARBITRATION sub-block |
| `ROOM_STAY_SILENT_ON_USER_TO_USER` | True | Classifier-driven silent skip for user-to-user addressing |
| `SEARCH_ROOM_MEMORY_ENABLED` | True | Master gate for `search_room_memory` tool |
| `SEARCH_ROOM_MEMORY_MIN_TURNS` | 5 | Below this, tool returns hint |
| `ROOM_END_SYNTHESIS_ENABLED` | True | Master rollback for `synthesize_room` |
| `ROOM_SUMMARY_LLM_TIMEOUT_SECS` | 3.0 | Fallback to topic-only summary on timeout |
| `ROOM_RECENT_CONTEXT_HOURS` | 24 | Lookback window for `<<<RECENT ROOMS>>>` |
| `SCENE_VISITOR_RECENCY_SECS` | 600.0 | Session 108 SCENE "Recent visitors" window |
| `DIARIZATION_BACKEND` | "pyannote" | "pyannote" or "ecapa_valley" fallback |
| `DIARIZATION_FALLBACK_ON_ERROR` | True | Fallback enabled |
| `DIARIZE_MIN_SEGMENT_SECS` | 0.5 | Drop segments below this (ECAPA noise floor) |
| `DIARIZE_MIN_EMBED_SECS` | 1.0 | Min embedding window for attribution |
| `VOICE_ROUTING_SHORT_UTT_MISMATCH_ENABLED` | True | P3.23 tier 1 hard mismatch drop |
| `VOICE_ROUTING_SHORT_UTT_FLOOR` | 0.20 | Hard mismatch threshold |
| `VOICE_ROUTING_SHORT_UTT_AMBIGUOUS` | 0.40 | Ambiguous zone threshold (tier 2) |
| `VOICE_ROUTING_MIN_UTTERANCE_SECS` | 1.0 | Short-utterance threshold |
| `VOICE_ROUTING_MIN_AUDIO_FOR_SCORE` | 0.5 | Below this, skip directional check |
| `VOICE_ROUTING_FACE_ASSIST_MIN` | 0.42 | Priority 2 face+voice shortcut floor |
| `VOICE_BOOTSTRAP_REPLENISH_ENABLED` | True | Bootstrap credit replenishment on engaged strangers |
| `VOICE_MAX_BOOTSTRAP_CREDITS` | 10 | Cap on replenished credits |
| `DISPUTE_AUTO_CLEAR_VOICE_MIN` | 0.70 | Face-corroborated auto-clear floor |
| `DISPUTE_AUTO_CLEAR_VOICE_SOLO_MIN` | 0.85 | Voice-solo auto-clear floor |
| `DISPUTE_AUTO_CLEAR_CONSECUTIVE_TURNS` | 3 | Min consecutive high-voice turns for clear |
| `LOG_ANTISPOOF_PROBS` | False | Per-frame probs dump |
| `LOG_ANTISPOOF_SUMMARY` | True | Rolling summary every N frames |
| `LOG_ANTISPOOF_SUMMARY_INTERVAL` | 100 | Summary cadence |
| `LOG_LATENCY_ENABLED` | True | Emit "(Nms)" elapsed tags |
| `LOG_STT_MAX_CHARS` | 0 | 0 = no truncation |
| `SEARCH_QUERY_MIN_CHARS` | 3 | Server-side Bug R guard on `search_web` empty query |
| `SEARCH_WEB_LIVE_DATA_PATTERNS` | tuple of regex | Allow patterns for live-data gate (Bug T) |
| `SEARCH_WEB_BLOCK_PATTERNS` | tuple of regex | Block patterns (personal / opinion / closers) |

## 148. Full Tool Schema Reference

### 148.1 update_person_name

```json
{
    "type": "function",
    "function": {
        "name": "update_person_name",
        "description": "Call when the speaker tells you their name or corrects a mis-attribution. For a stranger this promotes them to known. For a known speaker, this flips the session to disputed pending verification — it does NOT rename.",
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"]
        }
    }
}
```

### 148.2 update_system_name

```json
{
    "type": "function",
    "function": {
        "name": "update_system_name",
        "description": "Call when the best friend gives you a name or renames you. Only callable by best_friend.",
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"]
        }
    }
}
```

### 148.3 search_web

```json
{
    "type": "function",
    "function": {
        "name": "search_web",
        "description": "Call for real-time information (news, facts, current events) that you don't know from training. Do NOT call for personal/memory questions — use search_memory for those. Do NOT call for self-awareness questions ('what is your name', 'who am i'). Results are cached for 5 minutes per query.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"]
        }
    }
}
```

### 148.4 shutdown

```json
{
    "type": "function",
    "function": {
        "name": "shutdown",
        "description": "Call when the best friend asks you to shut down or go to sleep. Only callable by best_friend.",
        "parameters": {"type": "object", "properties": {}}
    }
}
```

### 148.5 search_memory

```json
{
    "type": "function",
    "function": {
        "name": "search_memory",
        "description": "Call to retrieve stored facts about the current speaker or the system. Use scope='self' for their own memories, scope='system' for shared household knowledge.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "scope": {"type": "string", "enum": ["self", "system"]}
            },
            "required": ["query"]
        }
    }
}
```

### 148.6 report_identity_mismatch

```json
{
    "type": "function",
    "function": {
        "name": "report_identity_mismatch",
        "description": "ONLY call when the CURRENT SPEAKER (the person talking to you right now) explicitly denies being the person the sensor identified them as. DO NOT call for questions about prior conversation activity (e.g. 'Who were you talking to?'). TRIGGER CHECKLIST: (1) current speaker talking about themselves, (2) denying sensor's identification, (3) contradicted at least twice, (4) no replacement name given. If user's utterance contains 'who', 'what', 'did' — almost certainly NOT an identity mismatch.",
        "parameters": {
            "type": "object",
            "properties": {"reason": {"type": "string"}},
            "required": ["reason"]
        }
    }
}
```

### 148.7 search_room_memory (Phase 3B.5, Session 113)

```json
{
    "type": "function",
    "function": {
        "name": "search_room_memory",
        "description": "Search the CURRENT ROOM SESSION's conversation log (turns from ALL speakers who participated, interleaved chronologically). Use for cross-speaker room-wide questions ('what have we talked about tonight?', 'when did Lexi mention her interview?'). DO NOT call for prior-session questions (use search_memory), anything said in the last 2-3 turns (already in context), or single-person history (use search_memory). Returns empty+hint on rooms <5 turns.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"]
        }
    }
}
```

## 149. Session History Timeline

This table summarises the major sessions that shaped the system. For the complete list see `CLAUDE.md` § Completed Sessions.

| Session | Date | Theme |
|---|---|---|
| 1-7 | early | Foundations: FAISS, WAL, memory system, voice recognition |
| 8-11 | 2026-03-23-25 | Function calling rewrite, CloudState, brain-decides architecture |
| 12-17 | late March | Brain agent phases: extraction, graph, embeddings, schema norm, spatial vision |
| 18-20 | April 7 | Test coverage, Piper TTS, anti-spoof v1, memory pruning |
| 21-22 | April 10 | Multi-person sessions, household agent, anti-spoof gates, identity promotion |
| 23-24 | April 11 | G5a visitor alert, B1-B7 DB robustness, I2 targeted gallery update |
| 25-27 | April 12 | L1-L5 tool calling reliability, per-turn speaker routing, unrecognized face tracking |
| 28-38 | April 12-13 | Issue A-B, tool tightening, date injection, TTS hallucination filter, bug fixes |
| 39-41 | April 14-17 | Multi-person architecture, diarization, emotion, ConversationRoutingAgent, G4 phonetic |
| 42-44 | April 18 | Issues #13-29, privilege table, identity evidence, observability, delete_person |
| 45-46 | April 19 | Findings A-F, kairos scene, cleanup, verify_live wrapper |
| 47-50 | April 19 | Findings G-M + NEW-1..5, Priority 3.5, hydration, collision guards |
| 51 | April 19 | Uncle-false-match fixes: gallery poisoning, dispute state machine, schema families |
| 52 | April 19 | Anti-spoofing MiniFASNet vendored |
| 53-57 | April 19 | Dispute hardening, Findings G-M, dispute-rename burst watchdog |
| 58 | April 19 | Kuzu self-heal |
| 59-60 | April 19 | Anti-spoof preprocessing bug, Problem B best_friend downgrade, STT truncation |
| 61 | April 20 | Robustness refactor Steps 0-3: anti-spoof summary, log_utils, TOOL_PRIVILEGES, identity evidence |
| 62 | April 20 | Reviewer findings: verdict constants tracked config, set_language removed, pipeline literal |
| 63 | April 20 | Routing thresholds → config |
| 64 | April 20 | Bugs A-C + 2/3/5/6 from live run: voice accumulation, source tagging, dispute resilience |
| 65 | April 20 | Post-review hardening: Obs 1 cache fallback, Obs 2 in_transaction, Obs 3 finish_reason, Obs 4 voice-expiry log |
| 66 | April 20 | Obs 1-4 hardening: `_safe_commit`, voice gallery DB fallback, finish_reason plumbing, voice-session observability |
| 67 | April 21 | Phase 1 bugs F, O, I + BOOTSTRAP=20 — short-utterance floor, face-assist floor, accumulation ordering |
| 68 | April 21 | Phase 2 narrative correctness: confabulation prevention (BriefingAgent + HONESTY POLICY), meta-commentary leak, tail-retry split |
| 69 | April 21 | Phase 3 knowledge hygiene: PromptPref dedup + blacklist, unified `_call_llm_chat` retry helper |
| 70–74 | April 21-22 | Tool-dispatch hygiene: R/P/Q/S/T/V/W/X/Y/G/D bugs; server-side user-text gates; `_is_disputed` helper; dispute state machine hardening; `DISPUTE_MAX_DURATION`, `DISPUTE_AUTO_CLEAR_*` |
| 75 | April 22 | **VISION_ROADMAP Phase 1.1+1.2** — `INTENT_LABELS`, `TOOL_INTENT_MAP`, `<<<STRUCTURED OUTPUT CONTRACT>>>` block (observation only) |
| 76 | April 22 | **Phase 1.3** — shadow classifier: `_classify_intent` + `_parse_intent_sidecar` + `<<<HEDGED NAMING CONTRACT>>>` |
| 77 | April 22 | Ollama rename-retry hedge, classifier timeout 5s → 8s |
| 78 | April 22 | Short-utterance floor regression root fix, `_strip_im_contraction` normalization, max_tokens 300 → 500 |
| 79 | April 22 | `search_web` removed from `TOOL_INTENT_MAP` (scope-shrink); 3 P0 fixes from live canary |
| 80 | April 22 | **Phase 1.4** — `_intent_allows()` server-side validator + Cyrillic homoglyph defense (shadow only) |
| 81 | April 22 | **Phase 1.5** — golden intent set (146 → 149 rows), `harvest_golden.py`, archive hook for `terminal_output.md` |
| 82 | April 22 | **Phase 1.6** — eval bench pure layer + CLI + persisted runs for drift detection |
| 83 | April 22 | Classifier prompt hardening: QUESTION vs ASSERTION rule + INJECTION DEFENSE clause |
| 84 | April 22 | Narrowed injection defense + 5 shutdown positive anchors |
| 85 | April 22 | **Phase 1.7a canary** — `update_person_name` classifier gate + `intent_divergences` table |
| 86 | April 22 | **Phase 1.7b** — 4-site mutation wire-in: report_identity_mismatch, update_system_name, auto-confirm, shutdown |
| 87 | April 22 | `_intent_allows` ungrounded-arg bug fix + golden harvest +3 rows |
| 88 | April 22 | **Phase 2** — pyannote.audio 3.3.2 diarization wire-in + 7 patches to unblock torch 2.10 |
| 89 | April 22 | Session 88 post-live audit — pyannote load-failure root-cause fix + loader traceback observability |
| 90 | April 22 | Phase 2 ACCEPTED (multi-convo live) + ContradictionAgent silent-timeout fix + voice-accumulation evidence-write gap |
| 91 (Phase 3 kickoff) | April 22 | **P3.21** `<<<CROSS-PERSON PRIVACY>>>` prompt block (honest-phrasing, honest-not-denial) |
| 92 | April 22 | **P3.23 tier 1** — multi-speaker-aware short-utterance floor (hard mismatch drop) |
| 93 | April 22 | **P3.23 tier 2** — ambiguous-zone drop (0.20–0.40 with `n_active_sessions ≥ 2`) |
| 94 | April 22 | Multi-speaker canary fixes #1/#2/#5: greeting-vs-assign rule, Im-contraction, bootstrap credit replenishment |
| 95 (3A.1–3A.4.6) | April 22 | **Phase 3A** — 4-tier privacy model + LLM classifier + `_visibility_clause` + `query_knowledge_for` + owner-access simplification |
| 96 | April 22 | Canary-failure patch: `report_identity_mismatch` tightening, Ollama fallback visitor_hint, `<<<VISITOR CONTEXT>>>` block |
| 97 | April 23 | Stranger promotion hole + zero-value ghost session prune + HouseholdAgent shadow dedupe + `<<<STRANGER IDENTITY>>>` block |
| 98 | April 23 | 4 downstream fixes after Session 97: visitor-alert gate, tool misroute teeth, owner-mode privacy, extraction QUESTION-vs-STATEMENT |
| 99–104 | April 23 | Pre-Phase-3B: Session 99 extraction hygiene; Session 100 BriefingAgent; Session 101/102 classifier calibration; Session 103 visibility hardening; Session 104 eval bench refresh |
| 105 | April 23 | **Safety-flag preservation (Bug N)** — `SAFETY_CRITICAL_ATTRIBUTE_PATTERNS`, dual-attribute extraction, `SHADOW_NAME_BLOCKLIST` |
| 106–109 | April 23 | SCENE block Phase 3A.7 (4-section restructure), `safety_flags` metadata on visitor nudges, `get_recent_visitor_alerts` |
| 110 | April 23 | **Pre-3B #1**: latency fix — SCENE-block bulk-write race between `_open_session` and visibility queries |
| 111 | April 23 | **Pre-3B #2/#3**: session-boundary history filter + `addressed_to` column on `conversation_log` |
| 112 | April 23 | **Pre-3B #4**: `_active_room_session` + `_active_room_started_at` + `_active_room_participants` lifecycle + `_on_room_end` |
| 113 | April 23 | **Pre-3B #5**: LLM turn allocation via `[addressing:X]` markers + `_resolve_addressed_to` three-source router + batched greeting |
| 113.1 | April 23 | Observability 2.0 — `[Pipeline] Turn addressed` + `[Room]` log categories |
| 3B.1 | April 23 | `<<<ROOM>>>` block replaces SCENE(in-room) + cross-person excerpts + per-person mood — `_build_room_block` helper |
| 3B.2 | April 23 | `ROOM_STAY_SILENT_ON_USER_TO_USER` — classifier-driven user-to-user detection skips AI response while still logging |
| 3B.3 | April 23 | `<<<TURN ARBITRATION>>>` rules appended to ROOM block (mumble continuation, pending thread, long-silence re-engagement, direct question) |
| 3B.4 | April 23 | N-speaker verification — ROOM block + arbitration + address marker validated on 3-person scenarios |
| 3B.5 | April 23 | `search_room_memory` tool + `BrainDB.search_room_turns` + `SEARCH_ROOM_MEMORY_MIN_TURNS=5` gate |
| 3B.6 | April 23 | `room_summaries` table + `synthesize_room` + `<<<RECENT ROOMS>>>` greeting-enrichment block |

---
---

# Part XXV — Cross-Person Privacy and Safety (Phase 3A)

Phase 3A is the largest architectural addition since the dispute state machine. It is the answer to the question: *when Person A talks to Kara-OS and Person B later asks about that session, what should Kara-OS share?* The answer is **nuanced** — it depends on who A and B are, what attribute we're talking about, and whether any of the content crossed a safety line.

This Part documents the model in full: the four tiers, the static map, the LLM classifier fallback, the SQL composer, the retrieval site that consumes it, the two variants of the `<<<CROSS-PERSON PRIVACY>>>` prompt block, the `<<<VISITOR CONTEXT>>>` and `<<<STRANGER IDENTITY>>>` complements, and the safety-flag preservation subsystem added in Session 105.

> **Source of truth.** All code references in this Part live in `core/brain_agent.py` (privacy helpers, `BrainDB.query_knowledge_for`), `core/brain.py` (prompt blocks in `_build_system_prompt`), `pipeline.py` (`_make_memory_search_fn` — the only retrieval site wired in the 3A.4 canary), and `core/config.py` (the tier enum, static map, classifier params, safety-critical regex).

