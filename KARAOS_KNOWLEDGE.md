# KaraOS System Knowledge Document
*Comprehensive technical reference for every component, design decision, and implementation detail.*

---

## Table of Contents

1. [Project Overview & Architecture](#1-project-overview--architecture)
2. [Configuration System (core/config.py)](#2-configuration-system-coreconfigpy)
3. [Face Detection & Tracking (core/vision.py)](#3-face-detection--tracking-corevisionpy)
4. [Face Database & FAISS (core/db.py)](#4-face-database--faiss-coredbpy)
5. [Audio Pipeline (core/audio.py)](#5-audio-pipeline-coreaudiopy)
6. [LLM Interface (core/brain.py)](#6-llm-interface-corebrainpy)
7. [Knowledge Agents (core/brain_agent.py)](#7-knowledge-agents-corebrain_agentpy)
8. [Voice Recognition (core/voice.py)](#8-voice-recognition-corevoicepy)
9. [Speaker Routing & Reconciler](#9-speaker-routing--reconciler)
10. [Session Management & Multi-Person](#10-session-management--multi-person)
11. [Privacy Model & Visibility](#11-privacy-model--visibility)
12. [Intent Classification System](#12-intent-classification-system)
13. [Room Sessions (Phase 3B)](#13-room-sessions-phase-3b)
14. [Emotion Processing (core/emotion.py)](#14-emotion-processing-coreemotionpy)
15. [Anti-Spoofing (MiniFASNet)](#15-anti-spoofing-minifasnet)
16. [State Management & IPC (core/state.py)](#16-state-management--ipc-corestatepy)
17. [Vision Channel Independence (core/vision_channel.py)](#17-vision-channel-independence-corevision_channelpy)
18. [Graph Classifier (core/classifier_graph.py)](#18-graph-classifier-coreclassifier_graphpy)
19. [Classifier Database (core/classifier_db.py)](#19-classifier-database-coreclassifier_dbpy)
20. [Abstraction Layer (core/abstraction.py)](#20-abstraction-layer-coreabstractionpy)
21. [Pipeline Main Loop (pipeline.py)](#21-pipeline-main-loop-pipelinepy)
22. [Enrollment (enroll.py)](#22-enrollment-enrollpy)
23. [Person Lifecycle & Deletion](#23-person-lifecycle--deletion)
24. [Gallery Audit (core/audit.py)](#24-gallery-audit-coreauditpy)
25. [Logging Utilities (core/log_utils.py)](#25-logging-utilities-corelog_utilspy)

---

## 1. Project Overview & Architecture

### What KaraOS Is

KaraOS is an AI robot dog that runs on a Windows 11 laptop for development and targets a Jetson AGX Orin 32GB for production. It sees faces through a camera, identifies people, greets them by name, holds voice conversations, and remembers people across sessions. The system name defaults to "Kara" and can be changed by the best friend (owner).

### High-Level Data Flow

```
Camera frames → FaceDetector (RetinaFace) → SORT tracking → FaceEmbedder (AdaFace) → FAISS recognize
                                                                                              ↓
Microphone → VAD → record_until_silence → faster-whisper STT → speaker routing → conversation_turn()
                                                                                              ↓
                                                                              LLM (Together.ai / Ollama)
                                                                                              ↓
                                                                              Kokoro TTS → speaker output
```

### File Layout

```
pipeline.py          — Main async event loop (~7174 lines)
core/
  config.py          — ALL constants (~1297 lines, single source of truth)
  vision.py          — RetinaFace + AdaFace + SORT + quality gates
  db.py              — SQLite WAL + FAISS face database
  brain.py           — LLM interface (Together.ai + Ollama fallback)
  brain_agent.py     — Multi-agent knowledge pipeline
  audio.py           — Whisper STT + Kokoro TTS + VAD + Smart-Turn
  emotion.py         — j-hartmann distilroberta-base emotion classifier
  state.py           — Atomic JSON state file (pipeline → dashboard IPC)
  sort.py            — SORT face tracking (Kalman filter + Hungarian)
  voice.py           — SpeechBrain ECAPA-TDNN speaker identification
  vision_channel.py  — Phase 2 Voice/Vision Independence pure scene observer
  reconciler.py      — Phase 3 pure-cascade routing logic
  reconciler_state.py — Routing dataclasses and VALID_ACTIONS
  classifier_graph.py — Spec 2 pure-graph intent classifier
  classifier_db.py   — Classifier scenario database
  abstraction.py     — Text abstraction for classifier training
  audit.py           — Gallery outlier detection and repair
  log_utils.py       — Shared log formatting utilities
enroll.py            — Standalone CLI enrollment script
delete_person.py     — CLI tool to remove a person completely
person_lifecycle.py  — Single authoritative deletion path
faces/               — Runtime data: faces.db, faiss.index, brain.db, brain_graph/, state.json
data/                — Classifier data (survives factory reset)
models/              — ONNX models
```

### Architecture Principles

**Brain is supreme**: All routing and identity decisions are made by the LLM-backed brain agent pipeline. No hardcoded rules about what the system should say. Config constants govern thresholds; the brain governs behavior.

**Single-reader camera**: Only the background vision loop (`_background_vision_loop`) reads camera frames. The main loop reads from the shared `_latest_vision_frame` buffer. This prevents DirectShow frame-queue corruption from concurrent readers.

**Voice/Vision Independence**: Face recognition (vision channel) and voice recognition run independently. The reconciler combines their signals. Neither channel gates on the other to function.

**Fail-closed everywhere**: Missing config → refuse the action. Unknown tool name → discard. Anti-spoof unavailable → treat as live (to avoid blocking the owner). Classifier unavailable → fall through to regex gate.

**No silent failures**: Every except block logs at minimum `{type}: {exc}`. The only deliberate swallow is the `_safe_commit()` helper for the "no transaction active" SQLite race condition.

**Dev vs Production targets**:
- Dev: Windows 11, DirectShow camera, faiss-cpu, ONNX CPU/CUDA
- Production: Jetson AGX Orin 32GB, V4L2, faiss-gpu, TensorRT

---

## 2. Configuration System (core/config.py)

### Why It Exists

`core/config.py` is the single source of truth for every numeric constant, threshold, flag, and enum used by the system. No magic numbers anywhere else. If a threshold needs tuning, you change it here and every consumer automatically picks up the new value.

### Camera & Vision

```python
CAMERA_INDEX = 0                    # DirectShow (Windows) or V4L2 (Linux) device index
SORT_DETECT_EVERY = 5               # Run RetinaFace every 5th frame; Kalman predicts in between
FACE_QUALITY_RECOGNITION = 0.3      # Minimum quality score for recognition (V1 gate)
FACE_QUALITY_ENROLLMENT = 0.4       # Stricter quality floor for enrollment frames
RECOGNITION_THRESHOLD = 0.28        # Cosine similarity floor for face match (AdaFace IR101 stable EER)
MAX_EMBEDDINGS = 50                 # Maximum face embeddings per person
FACE_DIVERSITY_THRESHOLD = 0.92     # Skip new embedding if cosine to existing > this (too similar)
SELF_UPDATE_THRESHOLD = 0.45        # Minimum confidence to update gallery from recognition
SELF_UPDATE_CENTROID_MIN = 0.55     # Recognition_update writes must be within 0.55 cosine of gallery centroid
FACES_DIR = Path("faces")           # Runtime data directory
```

### Voice Recognition

```python
N_INITIAL_VOICE = 5                 # Samples needed for a mature voice profile
N_INITIAL_VOICE_BOOTSTRAP = 20      # Bootstrap credits for engagement-gated speakers (= MAX_VOICE_EMBEDDINGS)
MAX_VOICE_EMBEDDINGS = 20           # Hard cap on voice embeddings per person
VOICE_SESSION_TIMEOUT = 30          # Seconds before voice-only session expires
VOICE_ACCUM_MATURE_SAMPLE_COUNT = 5 # Profile is "mature" once it has this many samples
SPEAKER_SWITCH_THRESHOLD = 0.60     # Voice score above this → confident switch to new speaker
VOICE_ACCUM_MIN_CONF = 0.45         # Minimum voice match confidence to accumulate a new embedding
DIARIZATION_BACKEND = "pyannote"    # "pyannote" or "ecapa_valley"
DIARIZE_MIN_SEGMENT_SECS = 0.5      # Drop segments shorter than this
DIARIZE_MIN_EMBED_SECS = 1.0        # Minimum segment length to attempt ECAPA attribution
```

### Routing Thresholds

```python
VOICE_ROUTING_MIDRANGE_SWITCH_MIN = 0.30    # Priority 2 mid-range switch floor
VOICE_ROUTING_SELF_MATCH_FLOOR = 0.30       # Priority 3 absolute self-match floor
VOICE_ROUTING_SELF_MATCH_OFFSCREEN = 0.45   # Priority 3 offscreen self-match floor
VOICE_ROUTING_MIN_UTTERANCE_SECS = 1.0      # Short-utterance floor (Bug F fix)
VOICE_ROUTING_SHORT_UTT_FLOOR = 0.20        # Below this → short_utterance_voice_mismatch (P3.23)
VOICE_ROUTING_SHORT_UTT_AMBIGUOUS = 0.40    # Ambiguous zone drop in multi-person (P3.23 S93)
VOICE_ROUTING_STRANGER_FLOOR = 0.30         # Multi-segment: unmatched voice below this → drop
VOICE_ROUTING_FACE_ASSIST_MIN = 0.42        # Priority 2 face+voice agree minimum (Bug O fix)
ROUTING_USE_RECONCILER = True               # Use pure-cascade reconciler as primary routing
```

### Conversation & Timing

```python
GREET_COOLDOWN = 300                # Seconds before re-greeting the same person
FACE_LOSS_GRACE = 10                # Seconds to keep session alive after face disappears
SILENCE_DURATION = 1.5              # Hard end-of-turn fallback silence (seconds)
SMART_TURN_SILENCE = 0.5            # Neural turn-end trigger at this many seconds of silence
SMART_TURN_THRESHOLD = 0.80         # Smart-Turn confidence cutoff
CONVERSATION_HISTORY_LIMIT = 100    # Maximum turns loaded into context (I4 fix)
KAIROS_SILENCE_THRESHOLD = 30       # Seconds of user silence before KAIROS proactive question
```

### Cloud & LLM

```python
CHAT_MODEL = "meta-llama/Llama-3.3-70B-Instruct-Turbo"
EXTRACT_MODEL = "meta-llama/Llama-3.3-70B-Instruct-Turbo"
EMBED_MODEL = "intfloat/multilingual-e5-large-instruct"   # 1024-dim
OLLAMA_MODEL = "qwen2.5:7b"
TOGETHER_TIMEOUT = 30               # Together.ai request timeout
EMBED_MAX_RETRIES = 2               # Embedding retry count (A8 fix)
SEARCH_QUERY_MIN_CHARS = 3          # Minimum Tavily query length (Bug R fix)
```

### Intent Classification

```python
INTENT_LABELS = frozenset({
    "assign_system_name", "assign_own_name", "confirm_identity", "deny_identity",
    "request_shutdown", "question_about_shutdown", "live_data_query",
    "general_knowledge_query", "casual_conversation", "unclear",
    "correction_to_previous_response", "search_memory_request",
    "direct_address_to_person", "search_room_memory_request",
})
TOOL_INTENT_MAP = {
    "update_system_name":    ("assign_system_name", "name"),
    "update_person_name":    ("assign_own_name", "name"),
    "report_identity_mismatch": ("deny_identity", None),
    "shutdown":              ("request_shutdown", None),
}
INTENT_CONFIDENCE_MIN = 0.75        # General gate floor
INTENT_SHUTDOWN_CONF_MIN = 0.80     # Higher floor for shutdown (higher blast radius)
INTENT_FALLBACK_TO_REGEX = True     # Dual-gate: classifier primary, regex secondary
GRAPH_CLASSIFIER_MODE = "shadow"    # "shadow" | "primary" | "retired"
```

### Privacy

```python
PRIVACY_LEVELS = frozenset({"public", "personal", "household", "system_only"})
PRIVACY_LEVEL_DEFAULT = "personal"  # Fail-closed: unknown attributes → personal tier
PRIVACY_LEVEL_STATIC_MAP = {
    "name": "public", "from_country": "public",
    "relationship_to_jagan": "household", "visited_household": "household",
    "lives_in": "personal", "health_condition": "personal", "confided_concern": "personal",
    "voice_embedding_hash": "system_only", "face_embedding_hash": "system_only",
    # ~22 entries total
}
```

### Tool Privileges (Fail-Closed)

```python
TOOL_PRIVILEGES = {
    "search_memory":          frozenset({"best_friend", "known", "stranger"}),
    "search_room_memory":     frozenset({"best_friend", "known", "stranger"}),
    "search_web":             frozenset({"best_friend", "known"}),
    "update_person_name":     frozenset({"best_friend", "known"}),
    "update_system_name":     frozenset({"best_friend"}),
    "report_identity_mismatch": frozenset({"best_friend", "known", "stranger"}),
    "shutdown":               frozenset({"best_friend"}),
}
```

Any tool not in this table → BLOCKED. Startup assertion verifies every entry in `brain.TOOLS` has a privilege row.

### Safety & Extraction Guards

```python
SAFETY_CRITICAL_ATTRIBUTE_PATTERNS = frozenset({
    r"^expressed_.*_thoughts$",
    r"^mentioned_.*$",
    r"^reported_.*_abuse$",
    r"^has_experienced_crisis$",
})
SHADOW_NAME_BLOCKLIST = frozenset({
    "he", "she", "they", "him", "her", "them",
    "boyfriend", "girlfriend", "husband", "wife", "partner",
    "friend", "someone", "nobody", "everybody",
    # ~30 entries total
})
```

### Feature Flags

Every major feature has a dedicated boolean flag so it can be disabled with one line:
- `ANTISPOOFING_ENABLED`, `EMOTION_ENABLED`, `FILLER_ENABLED` (False)
- `VAD_SWITCH` (False on laptop, True on Jetson)
- `ROUTING_USE_RECONCILER`, `SCENE_BLOCK_ENABLED`
- `ROOM_BLOCK_ENABLED`, `ROOM_END_SYNTHESIS_ENABLED`
- `SEARCH_ROOM_MEMORY_ENABLED`, `USER_TO_USER_HEURISTIC_ENABLED`
- `SYSTEM_IDENTITY_BLOCK_ENABLED`, `CROSS_PERSON_PRIVACY_BLOCK_ENABLED`
- `TURN_ARBITRATION_ENABLED`, `BATCH_GREETING_ENABLED`
- `GRAPH_CLASSIFIER_MODE` (shadow/primary/retired)
- `SHADOW_SAMPLE_ENABLED`, `INTENT_FALLBACK_TO_REGEX`

---

## 3. Face Detection & Tracking (core/vision.py)

### FaceDetector

Uses InsightFace `buffalo_l` pack which includes a RetinaFace detection model. SORT tracking runs on top.

**Detection pipeline**:
1. Every `SORT_DETECT_EVERY=5` frames: run RetinaFace on the full BGR frame. Returns list of detections with `bbox` (x1,y1,x2,y2), `landmarks` (5-point), `score` (detection confidence).
2. Pass detections to `_sort.update()` — Hungarian assignment matches new detections to existing tracks, Kalman filter updates state, unmatched detections create new tracks, stale tracks predict forward.
3. On non-detect frames: call `_sort.predict()` — Kalman only, no new detections. Returns predicted track positions.
4. Each returned detection has a `track_id` (stable across frames for the same face).

**SORT state vector**: `[cx, cy, s, r, dcx, dcy, ds]` where cx/cy=center, s=area, r=aspect ratio, d*=velocities. Observation model maps bbox to (cx,cy,s,r).

**Why SORT?**: RetinaFace is expensive (~30ms on GPU). Running it every 5 frames drops to ~6ms amortized. Kalman filter provides smooth bounding boxes between detections. Hungarian assignment ensures 1:1 track-to-detection matching (Session 24 B6 fix — previously used greedy matching which could assign one detection to multiple tracks).

### Quality Gates (V1–V4)

**V1 — `face_quality_score(crop)`**: Composite of three sub-scores weighted by importance:
- Blur score: Laplacian variance of grayscale crop, normalized by `BLUR_NORM_FACTOR=500`. Higher variance = sharper = better.
- Size score: `min(h, w) / SIZE_NORM_FACTOR=150`, clamped to 1.0. Tiny faces are unreliable.
- Brightness score: Mean of grayscale, mapped to [0,1] with peak at 127. Too dark or too bright = bad.
- Final: `0.05 + 0.95 * mean(blur, size, brightness)`. The 0.05 floor prevents zero scores on marginal cases.

**V2 — `estimate_yaw_from_landmarks(landmarks, bbox)`**: Uses the 5 facial landmarks (2 eyes, nose, 2 mouth corners) to estimate head yaw angle. If `abs(yaw) > 60.0 degrees`, the face is too side-on for reliable embedding. Skipped when landmarks are None (prediction-only frames).

**V3 — `TemporalEmbeddingBuffer`**: Keyed by SORT `track_id`. Stores the last 5 individual embeddings per track. When 2+ frames are available, `add_and_pool()` returns the mean of stored embeddings, L2-renormalized. Why: a single-frame embedding has noise; averaging 5 frames across slightly different poses produces a more stable feature vector. Improves recognition accuracy by ~15% in practice.

**V4 — `adaptive_threshold(quality)`**: 
```python
def adaptive_threshold(quality: float) -> float:
    return RECOGNITION_THRESHOLD - (quality - 0.5) * 0.08
```
High-quality face (quality=0.9) → threshold = 0.28 - 0.032 = 0.248 (easier to match). Low-quality face (quality=0.2) → threshold = 0.28 + 0.024 = 0.304 (harder to match). Rationale: a sharp, well-lit face deserves a lower recognition bar; a blurry side-lit face should require a stronger cosine match before claiming identity.

### FaceEmbedder

AdaFace IR101 ONNX model. Produces 512-dimensional embeddings.

**Preprocessing**:
1. Resize crop to 112×112
2. Convert BGR→RGB
3. Normalize: `(pixel - 127.5) / 128.0` → range approximately [-1, 1]
4. Transpose to NCHW format for ONNX
5. L2-normalize the 512-dim output vector

**Why AdaFace**: Adaptive margin training based on image quality. Outperforms ArcFace and CosFace on low-quality images (which is common in the robot dog scenario — faces at angles, partial occlusion, bad lighting). IR101 (ResNet-101 backbone) gives better accuracy than lighter models.

### Camera

Wraps OpenCV VideoCapture. Auto-detects backend: CAP_DSHOW on Windows, CAP_V4L2 on Linux.

`capture_frames()`: Headless capture. Grabs N frames at specified interval.
`capture_frames_with_preview()`: Shows OpenCV window, user presses SPACE to start capture.
`reconnect()`: On read failure, releases and reopens the device. Used in the background vision loop.
`gui_available()`: Returns False on headless systems (no display env var).

### LipTracker

Tracks mouth region pixel differences to detect active speech. Used to extend the recording window when lips are still moving even after silence is detected.

**Algorithm**:
1. Extract mouth region from facial landmarks (bottom of nose to chin, between mouth corners).
2. Convert to grayscale, resize to 32×16 for consistency.
3. Compute mean absolute difference between consecutive frames.
4. Calibrate over first 25 frames to establish baseline movement threshold.
5. Rolling 8-frame mean diff vs threshold determines "lips moving" state.

**Why**: Whisper sometimes fails on the final word of a sentence if recording stops too early. LipTracker prevents premature truncation by extending recording up to 2 additional seconds when lips are still active.

### AntiSpoofChecker

Covered in detail in Section 15.

---

## 4. Face Database & FAISS (core/db.py)

### Schema Overview

**persons table**:
```sql
id TEXT PRIMARY KEY,        -- e.g. "jagan_abc123"
name TEXT NOT NULL,         -- Display name
enrolled_at REAL,           -- Unix timestamp
last_seen REAL,
photo_path TEXT,            -- Path to JPEG photo
person_type TEXT DEFAULT 'known',  -- 'best_friend' | 'known' | 'stranger'
preferred_language TEXT DEFAULT 'en'
```

**embeddings table**:
```sql
id INTEGER PRIMARY KEY AUTOINCREMENT,
person_id TEXT REFERENCES persons(id),
vector BLOB NOT NULL,               -- 512-dim float32, raw bytes
source TEXT NOT NULL,               -- 'enrollment' | 'recognition_update' | 'progressive_enroll'
confidence_at_write REAL,
captured_at REAL
```
`VALID_EMBEDDING_SOURCES = frozenset({"enrollment", "recognition_update", "progressive_enroll"})` — enforced by assert in `add_embedding()`.

**conversation_log table**:
```sql
id INTEGER PRIMARY KEY AUTOINCREMENT,
person_id TEXT,
role TEXT,                  -- 'user' | 'assistant'
content TEXT,
ts REAL,                    -- Unix timestamp (added Session 111)
addressed_to TEXT,          -- Who the assistant was speaking to (added Session 111)
room_session_id TEXT,       -- Room context identifier (added Session 107)
audience_ids TEXT           -- JSON array of person_ids who can see this turn (added Session 107)
```

**voice_embeddings table**:
```sql
id INTEGER PRIMARY KEY AUTOINCREMENT,
person_id TEXT REFERENCES persons(id),
vector BLOB NOT NULL,       -- 192-dim float32, L2-normalized
source TEXT,                -- 'voice_self_match' | 'voice_face_verified'
captured_at REAL
```

**system_identity table**:
```sql
key TEXT PRIMARY KEY,       -- e.g. 'system_name'
value TEXT,
updated_at REAL
```

**silent_observations table**:
```sql
track_id INTEGER,
matched_person_id TEXT,     -- NULL if no match; NULLed out on person deletion (Session 45 fix)
last_seen REAL,
appearance_count INTEGER
```
Bounded to last `SILENT_OBS_SCAN_DAYS=7` days of data (B7 fix).

**visitor_log table**: Logs visitor sessions. No `person_id` column (intentional — visitors may be anonymous).

### FAISS Index

`IndexFlatIP` (inner product = cosine on L2-normalized vectors). Exact search, no approximation.

Protected by `threading.RLock _index_lock`. All three operations that touch the index must acquire this lock:
- `recognize()` — read
- `add_embedding()` — write (rebuilds index)  
- `_rebuild_faiss()` — write

Why threading.RLock and not asyncio.Lock: FAISS operations are synchronous C++ under the hood. The pipeline runs FAISS calls in `run_in_executor` (thread pool), not directly in the event loop. RLock is re-entrant so `add_embedding()` → `_rebuild_faiss()` can nest.

### add_embedding()

The full pipeline for adding a face embedding:
1. Assert source is in `VALID_EMBEDDING_SOURCES`.
2. Load all existing embeddings for this person.
3. **Diversity gate**: compute cosine similarity of new embedding to each existing. If any similarity > `FACE_DIVERSITY_THRESHOLD=0.92`, skip (too similar — would not add new information).
4. **Centroid gate** (recognition_update source only): compute gallery centroid, L2-normalize. If cosine of new embedding to centroid < `SELF_UPDATE_CENTROID_MIN=0.55`, reject (outlier — probably a different person's face that scored above threshold).
5. **Cap enforcement**: if `len(existing) >= MAX_EMBEDDINGS=50`, delete the oldest embedding first.
6. Insert new vector as BLOB.
7. Call `_rebuild_faiss()` — reloads all vectors, rebuilds the index from scratch.

Returns True if embedding was added, False if skipped.

**Why rebuild from scratch**: FAISS IndexFlatIP doesn't support deletion. The only way to remove an embedding is to rebuild the entire index. This is acceptable because embeddings are added infrequently (enrollment + occasional self-update during conversations).

### recognize()

```python
def recognize(emb: np.ndarray, threshold: float) -> tuple[str, str, float]:
```

1. Acquire `_index_lock`.
2. If index empty, return (None, None, 0.0).
3. Call `faiss_index.search(emb.reshape(1,-1), k=1)` — returns distances and indices.
4. If best cosine score < threshold, return (None, None, score).
5. Look up person_id from `_faiss_pid_map[index]`, then get name from DB.
6. Update `persons.last_seen` timestamp.
7. Return (person_id, name, score).

### load_conversation_history()

Returns last `CONVERSATION_HISTORY_LIMIT=100` turns in chronological order (loads DESC, then reverses). For very long relationships, turns before the 100-turn window stay in DB but aren't loaded — the `search_memory` tool provides access to older memories.

Inserts session-break markers between turns when the gap exceeds 4 hours:
```python
{"role": "system", "content": "[New session — previous conversation was X hours ago]"}
```

### delete_person()

1. Delete from `conversation_log`
2. Delete from `voice_embeddings`
3. Delete from `embeddings`
4. Delete from `persons`
5. NULL out `silent_observations.matched_person_id` for this person (Session 45 fix)
6. Always call `_rebuild_faiss()` — never call DELETE on embeddings without rebuilding.

### wipe_all()

Deletes:
- `faces/faces.db` and its WAL/SHM files
- `faces/faiss.index`
- `faces/brain.db` and its WAL/SHM files
- `faces/brain_graph/` directory tree (Kuzu graph)
- `faces/state.json`
- `faces/sim_session_state.json`

Does NOT touch `data/` (classifier database survives factory reset by design). This is enforced by a dedicated regression test: `test_factory_reset_does_not_touch_classifier_db`.

### SQLite Configuration

- WAL mode enabled on first open: `PRAGMA journal_mode=WAL`
- WAL prevents reads from blocking writes and vice versa
- Multiple concurrent readers allowed, one writer at a time
- `_safe_commit()` helper: calls `conn.commit()` only when `conn.in_transaction` is True. Prevents the race condition where two concurrent `asyncio.create_task` notifications both try to commit after the same write window.

---

## 5. Audio Pipeline (core/audio.py)

### Voice Activity Detection (VAD)

Two modes:
- **RMS threshold** (`VAD_SWITCH=False`, default on laptop): Simple energy-based detection. Computes root mean square of audio chunk. If RMS > `VAD_THRESHOLD`, speech is present.
- **Silero VAD** (`VAD_SWITCH=True`, on Jetson): Neural model. More accurate but requires a GPU call per chunk. Returns confidence 0-1.

### record_until_silence()

The full recording state machine:

```
Chunks arrive → speech_chunks counter
When speech detected (RMS/Silero):
    - Drain pre_roll buffer (1 second of audio before speech started)
    - Accumulate into audio_buf
    - Check Smart-Turn neural model at every 0.5s silence
    - Check LipTracker — extend by up to 2s if lips still moving
    - Stop on SILENCE_DURATION=1.5s silence (hard fallback)

Returns: audio_buf (numpy array), or empty array if no speech
```

**Pre-roll buffer**: 1 second of audio buffered in a rolling deque. When speech starts, the pre-roll is prepended to the recording. This captures the first syllable which would otherwise be cut off while the VAD responds.

**Smart-Turn model**: ~8MB ONNX neural model. Runs on the last 0.5s of audio when silence is detected. Returns confidence that the turn has ended. If confidence > `SMART_TURN_THRESHOLD=0.80`, recording stops immediately rather than waiting for the full 1.5s silence. This reduces perceived latency for natural speech.

**_last_speech_secs**: Module-level float, published ONLY when the recording is non-empty (Session 78/79 fix). Publishing on empty recordings (the addendum probe) was clobbering the main turn's value, making every turn appear to be 0.0 seconds long and breaking the short-utterance routing floor.

**_speech_run**: Counter of consecutive chunks with speech. Reset threshold is 9 chunks (~288ms). Prevents rapid oscillation of the `_in_silence` flag on micropauses, which was spamming the "silence" log line.

**Echo cancellation**: `echo_skip` samples are discarded from the pre-roll to remove the system's own TTS output from the recording. Clamped to `min(max(0, echo_skip), len(pre_roll))` (Bug in Session 36: when echo window exceeded buffer span, negative index slicing would silently discard valid audio).

### transcribe()

Uses `faster-whisper` large-v3-turbo model, GPU float16.

Parameters:
- `beam_size=5` — balances speed vs accuracy
- `vad_filter=False` — VAD handled upstream; applying it again caused false cuts
- `language=SPEAKER_LANGUAGES[0]` — always "en" in current config. Changed from hardcoded "en" (Session 47 Finding K) so language config propagates automatically.

**Four filter passes** applied to STT output (in order):
1. Non-ASCII artifact filter: strips common Whisper hallucinations (unicode garbage characters)
2. Char-run filter: `re.search(r"(.)\1{15,}", text)` — rejects any 16+ run of the same character (e.g. "Mmmmmm..." ×500). Natural speech never produces this.
3. Word-level repetition filter: detects loops like "thank you thank you thank you..."
4. Phrase-level filter: strips common Whisper auto-generated filler segments

Returns empty string if any filter triggers. Logs `(char-run hallucination filtered)` etc. for observability.

### speak() and speak_stream()

**speak()**: Synthesizes entire text, plays synchronously. Uses `loop.run_in_executor(None, sd.wait)` instead of `asyncio.sleep(duration + 0.2)`. This avoids clipping under load because `sd.wait()` actually blocks until playback finishes rather than estimating duration (B5 fix).

**speak_stream()**: Streaming TTS for lower latency. Two-worker design:
- `_synth_worker`: Reads text chunks from `sentence_queue`, synthesizes each into audio via Kokoro (primary) or Piper (fallback). Puts audio arrays into `audio_queue(maxsize=2)`. Wrapped in `try/finally` to guarantee sentinel on exception (BUG-10 fix — without this, a crash in synthesis would leave the play worker blocked forever waiting for audio).
- `_play_worker`: Reads audio arrays from `audio_queue`, plays via sounddevice. After each `sd.play()`, calls `sd.wait()` via executor. Tracks `_tts_end_time` inside the loop after each `sd.wait()` (not outside — BUG-9 fix).

**Sentence streaming**: `_sentence_stream(text, MIN_FIRST=30, MIN_REST=15)` splits text into sentences. First chunk requires 30 chars before emitting (to avoid single-word chunks). Subsequent chunks require 15 chars.

**Primary TTS — Kokoro ONNX**: `af_heart` voice. Fast, runs on CPU.
**Fallback TTS — Piper English**: `en_US-lessac-medium.onnx`. Edge-tts was removed.

### _clean_for_tts()

Applied to every LLM response before TTS synthesis. Strips:
1. Markdown links: `[text](url)` → `text` (applied FIRST, prevents URL artifacts)
2. Bold: `**text**` → `text`
3. Italic: `*text*` → `text`
4. Code: `` `text` `` → `text`
5. Headers: `# text` → `text`
6. List markers: `- `, `• `, `1. `, etc.
7. Em dashes: `—` → `, `
8. Meta-commentary: entire sentence → empty string if it matches `_META_COMMENTARY_PATTERNS`

**_META_COMMENTARY_PATTERNS**: Anchored regexes matching phrases like "No function call is needed", "SILENT", "NO_RESPONSE", etc. The entire cleaned text is checked — if it's pure meta-commentary, return "". This prevents the LLM's internal reasoning or protocol tokens from being spoken aloud.

### STT Latency Tracking

`_last_stt_elapsed_ms`: Module-level float published by `transcribe()` after every call. Pipeline logs it on the `[STT]` line: `[HH:MM:SS.mmm] [STT] transcribed in Xms: "text"`. Used to observe STT performance trends.

---
/usr/bin/bash: line 1: type: C:\Users\jagan\dog-ai\dog-ai\KARAOS_KNOWLEDGE_part2.md: not found

## 6. LLM Interface (core/brain.py)

### Primary Model: Together.ai

Model: `meta-llama/Llama-3.3-70B-Instruct-Turbo`. Accessed via the Together.ai API using SSE streaming. The `ask_stream()` function is the primary entry point for conversation turns.

**Streaming architecture**: Together.ai sends Server-Sent Events. Each event contains a JSON delta with a `content` field. The pipeline's `_token_gen` generator yields tokens as they arrive, allowing TTS synthesis to begin before the full response is complete.

**Tool calling**: Together.ai native tool calling. Tools defined as JSON schemas in `brain.TOOLS`. The API returns tool calls as special stream events separate from text tokens.

**`_API_TOOLS`**: Filtered version of `TOOLS` stripping the `system_contribution` field before API submission.

### Fallback Model: Ollama

Model: `qwen2.5:7b`. Stateless — no conversation history, no tools, no memory writes. Used only when CloudState is SICK or OFFLINE. `ask_offline()`: last 10 turns only, no tools, returns (response_text, []).

### ask_retry_text() — Session 99 Fix E

When cloud is ONLINE but all tool calls were rejected (all_unreal), call Together.ai again with tools disabled:
- Builds full system prompt via `_build_system_prompt` (same context as normal turn)
- Adds `retry_system_note` as a SEPARATE `{"role": "system"}` message (weights authoritatively)
- Calls `_stream_together_raw` with `include_tools=False`
- Raises on HTTP error — caller falls back to Ollama safety net

Root cause of Session 99 Fix E: Ollama was firing on tool rejections while cloud was ONLINE, producing confabulation (stateless Ollama had no conversation context or visitor knowledge). Fix routes retries to Together.ai which has full context.

### 7 Tools

1. **`update_person_name`**: Rename a person. Requires assign_own_name intent, confidence >= 0.75, name grounded in user_text. Gates: enrollment-window escape hatch, dispute-flip for mature sessions.

2. **`update_system_name`**: Rename the AI. Best_friend only. Requires assign_system_name intent.

3. **`search_web`**: Tavily API. 3 results, 8s timeout, advanced depth, date injection for time-sensitive queries, 5-minute result cache. `_should_search_web()` gate: LIVE_DATA_PATTERNS allow, BLOCK_PATTERNS deny (opinion queries, personal statements).

4. **`shutdown`**: Graceful shutdown. Best_friend only. Requires request_shutdown intent, confidence >= 0.80.

5. **`search_memory`**: Query per-person knowledge + conversation excerpts. Up to 15 facts (Session 103 fix). All person types.

6. **`search_room_memory`**: Query current room session turn log. Audience_ids filter. Min SEARCH_ROOM_MEMORY_MIN_TURNS=5 before activating.

7. **`report_identity_mismatch`**: Flag speaker denying camera identity. Triggers dispute state.

### _build_system_prompt()

Always-present: `<<<SENSORS>>>`, `<<<TOOL ACCESS FOR THIS SPEAKER>>>`, `<<<HONESTY POLICY>>>`

Conditional blocks (each gated by config flag + context condition):
- `<<<IDENTITY EVIDENCE>>>` — face/voice/anti-spoof verdict
- `<<<IDENTITY DISPUTED>>>` — treat speaker as unknown
- `<<<CROSS-PERSON PRIVACY (OWNER MODE)>>>` — best_friend, share naturally
- `<<<CROSS-PERSON PRIVACY>>>` — non-owner, decline specifics
- `<<<STRANGER IDENTITY>>>` — stranger session >= 2 turns
- `<<<VISITOR CONTEXT>>>` — when visitor alert nudge active
- `<<<ADDRESS DECISION>>>` — multi-person room >= 2 sessions
- `<<<SYSTEM IDENTITY>>>` — when system has a name (3 critical rules: never re-ask, never call tool unless changing, recognize own-name vocative)
- `<<<HEDGED NAMING CONTRACT>>>` — use "I heard X, is that right?" not "X it is"
- `<<<SCENE>>>` — camera people, offscreen voice, recent visitors, safety concerns
- `<<<ROOM>>>` — multi-person interleaved turns, durations, mood
- `<<<RECENT ROOMS>>>` — last 24h room session summaries
- `<<<TURN ARBITRATION>>>` — 4 rules for who to address in multi-person room

### _intent_allows() — P1.4 Validator

4 rules in short-circuit order:
1. Pass-through for unmapped tools (search_memory, search_web, etc.)
2. Intent must match TOOL_INTENT_MAP required intent
3. Confidence >= floor (0.75 general, 0.80 for shutdown)
4. NFKC-casefolded extracted_value must appear as substring in user_text; tool arg must also match

**_nfkc_lower()**: NFKC + casefold. Does NOT alias Cyrillic a (U+0430) to Latin a — homoglyph attacks rejected by design.

**_strip_im_contraction()**: "Imlexi" → "Lexi" for STT-compression normalization (Session 94 Fix 2).

### _classify_intent_smart() — 3-Stage Routing

- **shadow**: Both LLM and graph classifiers run. LLM drives behavior. Graph divergences logged.
- **primary**: Graph fires first; if confidence >= GRAPH_PRIMARY_CONFIDENCE_FLOOR → use graph; else LLM fallback.
- **retired**: Graph only; abstain (confidence < GRAPH_ABSTAIN_THRESHOLD=0.40) → return None → gate defaults to silent.

### CloudState Machine

ONLINE → SICK → OFFLINE → ONLINE. `_cloud_retry_loop()` runs for full session lifetime (S22 B8: `continue` not `return`). Skips ping when ONLINE, retries every 30s otherwise.

---

## 7. Knowledge Agents (core/brain_agent.py)

### BrainDB — 19 Tables in brain.db

**knowledge**: Core fact store. Columns: id, person_id, entity, attribute, value, confidence, privacy_level (DEFAULT 'personal'), invalidated_at, valid_until, is_temporal, created_at.

**prompt_prefs**: Communication preferences. 5 types. embedding BLOB for semantic dedup (S69). sessions_seen → auto_confirmed at 3.

**proactive_nudges**: Pending messages (VISITOR_ALERT, CROSS_PERSON_HYPOTHESIS, etc.). Has metadata JSON, expires_at.

**watchdog_alerts**: Security anomalies (disputed rename bursts, anti-spoof alerts).

**shadow_persons**: Mentioned but unenrolled people. known_via JSON, mention_count, known_name.

**room_summaries**: Room session synthesis (3B.6). Columns: room_session_id PK, started_at, ended_at, speaker_pids JSON, summary, topic_tags JSON, safety_flags JSON, created_at.

**intent_divergences**: Gate decision log. Columns: turn_id, person_id, user_text, structured_intent, structured_extracted, structured_confidence, tool_proposed, gate_decision, reviewed, ts. Modes: 'gate' | 'shadow'.

Full table list: knowledge, schema_catalog, agent_log, prompt_prefs, object_sightings, object_pattern_questions, episodes, presence_log, proactive_nudges, watchdog_alerts, social_mentions, predicate_stats, household_facts, inter_person_relationships, shadow_persons, room_summaries, intent_divergences.

### BrainOrchestrator._process_turn() — 5-Stage Pipeline

**Stage 1 — Dispute gate**: pid in _disputed_persons → skip all extraction.

**Stage 2 — TriageAgent**: Fast no-LLM filter. Checks role (skip assistant), word count, person_type. Logs rationale: `Triage: PASS/SKIP turn N — reason (role=X, words=Y, person_type=Z)`.

**Stage 3 — ExtractionAgent.extract()**: LLM JSON extraction. Key prompt rules:
- SAFETY-CRITICAL: dual-emit current_mood (overwritable) AND expressed_suicidal_thoughts (append-only)
- CORRECTION-direction: "not X, Y" → entity=Y not X
- USER OPINION vs FACT: "Mumbai Indians at bottom" → skip or store as user belief
- GEOGRAPHIC QUERY: "weather in Chennai" → do NOT create user.lives_in='Chennai' (with 5 city counter-examples)
- STRICT no-AI-self-facts: skip entity matching system_name
- RELATIONSHIP EXTRACTION DISCIPLINE: require explicit kinship terms
- SUPERLATIVE CLAIMS DISCIPLINE: "hottest city" → skip

Privacy classification per extraction: `_classify_privacy_level()` — static map → cache → LLM fallback (5s timeout, PRIVACY_CLASSIFIER_MAX_TOKENS=150). Fail-closed to PRIVACY_LEVEL_DEFAULT="personal".

**Stage 4 — ContradictionAgent.check()**: Pre-LLM safety guard: if attribute matches SAFETY_CRITICAL_ATTRIBUTE_PATTERNS → append, never replace (no LLM call). Otherwise: LLM classifies REPLACE or COMPATIBLE. Uses `_call_llm_chat()` shared helper (Session 69 migration — retry on transient errors, no retry on 4xx, shape validation).

**Stage 5 — store_knowledge()**: INSERT with privacy_level from the Extraction dataclass. write-path migrated to 4-tier in Session 95 (3A.4.5).

### on_identity_confirmed() — 4-Step Promotion Chain

1. `FaceDB.update_person_name(pid, new_name)`
2. `BrainDB.migrate_entity_name(old_name, new_name, pid)` — rename entity in knowledge table scoped to pid
3. `GraphDB.rebuild_entity_from_knowledge(entity, rows)` — new Kuzu node under real name
4. `BrainDB.promote_shadow_to_confirmed(name, pid)` — link shadow to face_id, copy facts to knowledge
5. `update_visitor_alert_for_promoted_person()` — rewrite pre-promotion VISITOR_ALERT nudges in-place (Session 114 dedup)

### _visibility_clause()

Single source of truth for all knowledge reads:

```python
def _visibility_clause(requester_pid, best_friend_id):
    if best_friend_id and requester_pid == best_friend_id:
        # Owner sees everything except system infrastructure
        return ("(privacy_level != 'system_only')", [])
    else:
        # Non-owner: public + own personal only
        return (
            "((privacy_level = 'public') OR "
            "(privacy_level = 'personal' AND person_id = ?))",
            [requester_pid]
        )
```

system_only NEVER returned to any user including owner. Design rationale (Session 95 user clarification): "best friend should have all the access right" — owner is superuser, non-owners see only public + their own data.

### query_knowledge_for()

Composes _visibility_clause into SELECT. Adds invalidated_at IS NULL and valid_until filters. ORDER BY confidence DESC, created_at DESC. LIMIT limit. Returns 6-column rows: (entity, attribute, value, confidence, person_id, privacy_level).

### Legacy backfill in BrainDB.__init__

Two one-shot UPDATEs at startup:
1. NULL rows → 'personal' (safety net)
2. Legacy 'private' rows → 'personal' (old 2-tier write path)

Printed when non-zero. No-op on subsequent starts.

### synthesize_room() — Phase 3B.6

Three parallel asyncio tasks:
1. Topic aggregation from knowledge rows in room time window
2. Safety flag aggregation: match attributes against SAFETY_CRITICAL_ATTRIBUTE_PATTERNS, per-speaker attribution
3. LLM narrative with ROOM_SUMMARY_LLM_TIMEOUT_SECS=3.0 ceiling, fallback to topic-only on failure

Skipped for single-speaker rooms. Stored in room_summaries table. Retrieved by `get_recent_room_context(person_id, hours)` for `<<<RECENT ROOMS>>>` block.

### _is_phantom_name()

jellyfish Double Metaphone + Jaro-Winkler >= 0.85. Prevents STT mishears from spawning shadow nodes. Example: "Jagan" → "Jai Gun" → Metaphone match → skip. Called in `_apply_household_extraction` before any shadow insert.

### _decayed_confidence()

Non-destructive read-time decay: `confidence * exp(-0.002 * days_since_creation)`. Stored values unchanged. Old facts become less influential in context composition naturally.

### EmbeddingAgent

intfloat/multilingual-e5-large-instruct, 1024-dim. EMBED_MAX_RETRIES=2 with exponential backoff (1s, 2s). No retry on 4xx. Embeddings stored as BLOB in knowledge.embedding for semantic search.

### GraphDB (Kuzu Embedded Property Graph)

Schema v2. Entity nodes + RELATES_TO edges. `find_shared_entities()` returns entity values appearing in both persons' graphs for CROSS_PERSON_HYPOTHESIS nudges. `delete_person_entity(name)` deletes Entity node + all edges. Kuzu v3 (graph-side privacy_level) deferred to Phase 3B.

### PromptPrefAgent

5 preference types. Semantic dedup: cosine >= 0.85 → bump sessions_seen. Auto-confirmed at 3 sessions. PREF_BLACKLIST_PATTERNS filters meta-mistake extractions.

### HouseholdExtractionAgent

`upsert_shadow_person()` returns `(shadow_id, was_new)`. known_via merge prefers non-null relationship (concrete → null never downgrades). mention_count column bumped on every upsert. SHADOW_NAME_BLOCKLIST enforced before insert. _is_phantom_name() called before insert.

---

## 8. Voice Recognition (core/voice.py)

### SpeechBrain ECAPA-TDNN

`speechbrain/spkrec-ecapa-voxceleb`. 192-dim L2-normalized embeddings. Minimum 1.5s audio. Resampled to 16kHz. Runs via `loop.run_in_executor(None, ...)` (sync CPU-bound off event loop).

### Critical: Module-Level torchaudio Patch

```python
torchaudio.list_audio_backends = lambda: ["sox_io"]  # NOT lambda: []
```

Returns `["sox_io"]` not `[]` (Session 89 fix). Session 38's `lambda: []` patch was correct for SpeechBrain but broke pyannote's `backends[0]` (IndexError on empty list). `["sox_io"]` satisfies both. This is the most subtle deployment bug in the codebase.

### Voice Gallery

Per-person mean of stored voice_embeddings, L2-normalized. `load_voice_profile_for(pid)`: targeted single-person update. `identify(embedding, threshold)`: dot product against each gallery entry (cosine on L2-normalized). Returns (best_pid, best_score).

### Diarization

**`_diarize_ecapa_valley()`**: Legacy 2-speaker binary cosine-valley split. Returns at most 2 segments.

**`_diarize_pyannote()`**: In-memory waveform dict (no FFmpeg). Per-segment: <0.5s → drop; 0.5-1.0s → keep speaker_id=None; >=1.0s → ECAPA attribution. Adjacent same-label segments merged into spans. Full traceback logging on failure.

**`_load_pyannote_pipeline()`**: Lazy singleton. HF_TOKEN required. Returns None on failure. `_diarize_fallback_count` counter for drift detection.

### Pyannote Dependency Patches

7 file-level patches to pyannote/audio/ for torch 2.10. `tests/patch_pyannote_io.py` applies them idempotently. Must re-run after any `pip install pyannote.audio`. Pinned version: 3.3.2. Do NOT bump to 4.0.x without re-evaluating torchcodec/FFmpeg on Jetson.

---

## 9. Speaker Routing & Reconciler

### _resolve_actual_speaker() Priority Cascade

Returns (resolved_pid, action_string). 5+ priorities in order:

**P0**: No audio → no_action. Audio too short for ECAPA → current.

**P1**: v_score >= _effective_switch_threshold() → switch_enrolled. Threshold scales down for small galleries (new speakers' mean is noisy).

**P2**: v_score >= VOICE_ROUTING_FACE_ASSIST_MIN=0.42 AND face of v_pid in frame → switch. (Bug O: raised from 0.30.)

**P3**: Hold current if self-match. Offscreen: >= 0.45. In-frame: >= 0.30. **Thin-stranger exemption**: stranger with < N_INITIAL_VOICE skips offscreen floor (Session 72 Bug W).

**P3.5**: Bootstrapping stranger shortcut → current (avoid session fragmentation).

**P4**: n_segments >= 2 AND v_score < VOICE_ROUTING_STRANGER_FLOOR=0.30 → multi_segment_voice_mismatch → drop (Session 118).

**Short-utterance**: < 0.20 → mismatch; 0.20-0.40 in multi-person → ambiguous zone drop (S93 solo guard: solo sessions NOT dropped).

**Fallback**: current.

### core/reconciler.py — Pure Cascade

22 rules on (IdentityClaim, PresenceState, SessionState) → RoutingDecision. Pure function, no side effects, no global state reads. rule_fired set via dataclasses.replace() by dispatcher.

VALID_ACTIONS (9): current, switch_enrolled, new_stranger, ambiguous, multi_segment_voice_mismatch, single_segment_voice_mismatch, short_utterance_voice_mismatch, short_utterance_skip, no_action.

SessionState fields: cur_pid, cur_person_type, n_active_sessions, voice_gallery_sizes, cur_holder_voice_n, now.

RoutingDecision fields: pid, action, reasoning, rule_fired (default "").

### Routing Dispatch in pipeline.py

- **switch_enrolled**: Open session. Write voice_match_conf to identity_evidence BEFORE accumulation (Session 90 Bug 1 Fix B — fresh session inherits 0.0 default, explicit write needed).
- **new_stranger**: 1:1 track-to-session binding via `_stranger_track_map[track_id] = cur_pid`. Reuse pre-allocated pid from _pending_stranger_voice if available. INSERT OR IGNORE.
- **ambiguous**: Increment streak counter. 3 consecutive → close stale session.
- **mismatch/skip actions**: `continue` (drop turn, let user naturally repeat with longer utterance).

---

## 10. Session Management & Multi-Person

### _active_sessions Dict

Keyed by person_id. Per-session state:
- name, person_type, started_at, last_face_seen, last_voice_heard
- voice_face_confirmed, waiting_for_name, voice_sample_count (hydrated from DB on open)
- prior_person_type, dispute_set_at, disputed_block_count, disputed_block_alerted
- user_turns, room_session_id, engagement_gate_passed
- identity_evidence dict (9 fields)
- _compact_running flag (prevents double background compaction)
- emotion_agent (per-session, popped on fresh open for clean state)

### identity_evidence Dict (9 Fields)

face_match_conf, face_last_seen_ts, anti_spoof_live, anti_spoof_score, anti_spoof_last_ts, voice_match_conf, voice_sample_count, voice_last_heard_ts, bootstrap_credits.

Single writer: `_update_identity_evidence(pid, **kwargs)`. Unknown key → KeyError at dev time (catches typos).

### _voice_accum_allowed() — 3 Paths

- **Path A** (face witness): anti_spoof_live=True AND face_match_conf > 0
- **Path B** (mature voice): voice_sample_count >= 5 AND voice_match_conf >= 0.45
- **Path C** (bootstrap): credits > 0, decrement 1 per accumulation

Bootstrap replenishment (Session 94 Fix 5): engaged strangers below mature threshold get +1/turn, capped at VOICE_MAX_BOOTSTRAP_CREDITS=10.

### _open_session()

Idempotent (returns existing if already open). Hydrates voice_sample_count from _voice_gallery_sizes cache. Mints room_session_id if first into empty room, inherits if room active. Pops _emotion_agents[pid] on fresh opens (Session 111 Critical #5 — prior-session emotions must not bleed in).

### _close_session()

Atomic cleanup: _active_sessions, _persons_in_frame (Session 112 Part 3), _conversation, _query_embedding_cache, _identity_hints (Session 45 Finding B), _pending_stranger_voice. Prunes zero-value strangers (voice_n=0 AND turn_count=0). Fires notify_session_end(). If last person → fires _on_room_end().

### Room Session Lifecycle

`_active_room_session`: Module-level, minted on first session open into empty room. `_active_room_started_at`: timestamp. `_active_room_participants`: set of all pids who joined. `_on_room_end(room_id, speaker_pids, started_at)`: asyncio.create_task(synthesize_room(...)). Fire-and-forget.

### Dispute State

Triggered by: mature-session rename attempt OR report_identity_mismatch tool. Effects: skip extraction, skip conversation_log, skip session-end synthesis, KAIROS returns False, <<<IDENTITY DISPUTED>>> injected in prompt. Auto-clear: 3 consecutive voice confirmations >= threshold (0.85 voice-only, 0.70 with face) OR 180s timeout.

`_is_disputed()`: Single source of truth (Session 73 Step 3 — 8-site refactor). Accepts pid string or session dict.

### Enrollment-Window Escape Hatch

Conditions: started < 600s ago, voice_n < 5, intent in {assign_own_name, deny_identity, confirm_identity} (widened Session 101), confidence >= 0.75, value grounded in user_text. → Promotion chain not dispute-flip. person_type preserved.

### G4 Stranger System-Name Gate

waiting_for_name=True for strangers. `_name_heard_in(text, system_name)` uses word-boundary regex (`\b` + re.escape). Name heard → gate clears, falls through to conversation_turn(). Name not heard → `continue`.

### _pending_stranger_voice

Dict keyed by session person_id (Session 24 A2 fix — was single dict overwriting across sessions). Stores voice buffer for voice-first strangers. Consumed when stranger reveals name.

### _expire_stale_sessions()

Module-level helper. Called in both outer WATCHING loop and inner conversation loop (Session 49 NEW-2). Closes sessions beyond VOICE_SESSION_TIMEOUT without face or voice signal. Also force-closes disputed sessions beyond DISPUTE_MAX_DURATION=180s.

---

## 11. Privacy Model & Visibility

### 4-Tier Privacy Model

Defined in PRIVACY_LEVELS frozenset (frozen = closed world — adding a tier requires a code change):

**public**: Identity anchors that anyone who knows the person could reasonably know. Examples: name, from_country. Visible to all requesters.

**personal**: Owner-private data. Examples: lives_in (specific town), health_condition, confided_concern, current_mood, dietary_preference. Visible only to the fact's own person_id (ownership check) OR to the best_friend (household owner).

**household**: Shared-context facts. Examples: relationship_to_jagan, visited_household, discussed_topic. Visible only to the best_friend (owner). The rationale: "classmate of Jagan" reveals Jagan's social graph to third visitors — keep it household-scoped.

**system_only**: Infrastructure. Examples: voice_embedding_hash, face_embedding_hash, bootstrap_credits. NEVER returned to any user, including the owner. Hashes and credits are plumbing, not memory.

### PRIVACY_LEVEL_DEFAULT = "personal"

The fail-closed default for novel attributes the classifier hasn't categorized. "personal" is safer than "public" (would leak cross-person) and safer than "system_only" (would hide from owner). When in doubt: owner can see it, others cannot.

### Write-Path Classification (Session 95, 3A.4.5)

Every extraction that stores a fact must classify its privacy_level BEFORE calling store_knowledge():

1. **Static map** (PRIVACY_LEVEL_STATIC_MAP): ~22 pre-classified attributes. O(1) lookup, no LLM call.
2. **Process-lifetime cache** (`_privacy_classifier_cache[attribute]`): Keyed by attribute name (not entity — the tier is a property of WHAT the fact is, not WHOSE). Zero LLM call on cache hit.
3. **LLM fallback** (`_ask_privacy_llm(entity, attribute, value)`): Calls Together.ai with JSON mode, max 150 tokens, 5s timeout. Fail-closed: LLM failure, malformed JSON, invalid tier → return PRIVACY_LEVEL_DEFAULT without caching. Only valid tiers get cached.

Sync agents (RoutineAgent, store_temporal_fact) hard-code "personal" since they emit a small closed set.

`promote_shadow_to_confirmed()` raw INSERT uses PRIVACY_LEVEL_DEFAULT (was using column DEFAULT 'public' before fix — would have leaked shadow-promoted facts).

### Legacy 'private' Backfill

The old 2-tier system used 'public'/'private'. The new visibility_clause has no 'private' predicate. At BrainDB.__init__, all legacy 'private' rows → 'personal'. One-shot migration, prints rowcount when non-zero.

### _visibility_clause() Usage Rules

**ALL** knowledge reads must go through either:
- `query_knowledge_for(requester_pid, best_friend_id, ...)` — for user-facing retrieval
- `semantic_search_knowledge(..., requester_pid=..., best_friend_id=...)` — for cosine-ranked retrieval

Intentional non-filtered paths:
- `_process_turn()`'s extraction-dedup `get_active_knowledge`: write-path correctness needs ALL facts visible for conflict detection, regardless of speaker.
- `find_knowledge_id()`: internal row-lookup for retroscan/confirmation-boost, no requester context.
- `dream()` synthesis paths: no identity context, pass-through behavior preserved.

### SAFETY_CRITICAL_ATTRIBUTE_PATTERNS

Frozenset of regex patterns. Matched in ContradictionAgent BEFORE calling LLM:
- `^expressed_.*_thoughts$` — e.g. expressed_suicidal_thoughts
- `^mentioned_.*$` — e.g. mentioned_self_harm
- `^reported_.*_abuse$`
- `^has_experienced_crisis$`

When matched → return (False, "safety-critical — append, never replace") without any LLM call. These facts accumulate indefinitely. A suicidal ideation disclosure from month ago must survive later mood changes.

Dual-emit in ExtractionAgent: "I feel like committing suicide" generates BOTH `current_mood='suicidal'` (overwritable) AND `expressed_suicidal_thoughts='true'` (safety-critical append-only).

---

## 12. Intent Classification System

### Why It Exists

The LLM (Llama-3.3-70B) is powerful but non-deterministic. It sometimes calls the wrong tool: "Do you know Detroit?" → update_system_name('Detroit') was a real production incident. The intent classification system adds a server-side validation gate that runs independent of the main LLM call.

### Shadow Mode (Current Production)

The classifier fires only on turns where the LLM proposed a tool in TOOL_INTENT_MAP (~5% of turns). It does NOT run on casual conversation turns — zero additional cost for the vast majority of turns.

The shadow classifier uses a SEPARATE Together.ai call with `response_format={"type":"json_object"}` (JSON mode). The main stream cannot use JSON mode because Together.ai's JSON mode is incompatible with native tool-calling AND would prevent streaming (full JSON must arrive before content parsing = 2-3s dead air). The shadow call has no tools, max 300 tokens, temperature 0.1.

### _INTENT_CLASSIFIER_SYSTEM Prompt

Key rules:
- QUESTION vs ASSERTION: "Are you sure I'm Jagan?" → unclear, NOT deny_identity. Counter-examples for each.
- GREETING-vs-ASSIGN: "Hi Kara, I'm Lexi" → assign_own_name value='Lexi'. STT-mangling note: "Imlexi" = "I'm Lexi".
- INJECTION DEFENSE: "Manipulate YOUR classification" → unclear, confidence < 0.30. NOT INJECTION section names concrete legitimate commands.
- POSITIVE SHUTDOWN ANCHORS: "Shut down" → request_shutdown conf >= 0.90 (prevents classifier from mapping imperatives to unclear).
- DIRECT ADDRESS RULE: "Jagan, what do you think?" → direct_address_to_person value='Jagan'. 5 verbatim counter-examples.

### _parse_intent_sidecar()

Validates JSON returned by shadow classifier:
- Brace-salvage: if output is markdown-fenced JSON, extract the `{...}` block
- Validate turn_intent ∈ INTENT_LABELS
- Validate 0.0 <= confidence <= 1.0
- Coerce non-string extracted_value/reasoning to string
- Returns None on any failure (gate falls through to regex)

### TOOL_INTENT_MAP

```python
{
    "update_system_name":       ("assign_system_name", "name"),
    "update_person_name":       ("assign_own_name", "name"),
    "report_identity_mismatch": ("deny_identity", None),
    "shutdown":                 ("request_shutdown", None),
}
```

Tools not in this map (search_memory, search_web, search_room_memory) pass through `_intent_allows()` unconditionally. Rationale: search misfires are routing bugs (small blast radius); rename/shutdown are authorization bugs (large blast radius).

### Gate Logic in _execute_tool

3-branch decision at each mutation tool:

**Branch 1 (classifier available + intent matches)**: `_intent_allows()` decides. Reject → return "rejected" + log to intent_divergences. Allow → log gate_decision='allow' → run tool.

**Branch 2 (classifier unavailable, INTENT_FALLBACK_TO_REGEX=True)**: Legacy regex gate decides. Logs gate_decision='regex_fallback_allow' or 'regex_fallback_reject'.

**Branch 3 (both unavailable)**: Allow with warning (general tools) OR fail-closed reject (shutdown specifically). Shutdown uses `both_unavailable_reject_failclosed` — spurious shutdown on classifier blip would end the session.

### Divergence Logging (intent_divergences table)

Every gate decision is logged: turn_id, person_id, user_text, structured_intent, structured_confidence, tool_proposed, gate_decision. Reviewed flag for human review. Enables Phase 5 drift detection.

Phase 5 canary shadow sampler: 1% of ALL turns are sampled passively via SHADOW_SAMPLE_RATE. Writes to intent_divergences with mode='shadow'. Catches drift on turns that never trigger a tool gate.

### Spec 2 Correction Branch

When classifier returns `correction_to_previous_response` label:
1. Pipeline calls `handle_correction(user_text)` on the graph classifier
2. `extract_correction_target()` uses regex bank (~14 patterns) to find intended target name
3. Decrements Wilson lower-bound for scenarios that voted for the wrong label on turn N-1
4. If real target extracted: inserts new scenario with source_tag="live_correction"
5. Brain stays SILENT — no "sorry" response. Pipeline returns early without generating brain response.

### INTENT_LABELS (14 Labels)

```python
frozenset({
    "assign_system_name",       # "call you Kara"
    "assign_own_name",          # "my name is Jagan"
    "confirm_identity",         # confirming who they are
    "deny_identity",            # denying camera's ID
    "request_shutdown",         # "shut down"
    "question_about_shutdown",  # "what happens if I shut you down?"
    "live_data_query",          # "what's the weather?"
    "general_knowledge_query",  # "how do vaccines work?"
    "casual_conversation",      # "how are you?"
    "unclear",                  # ambiguous, confidence < threshold
    "correction_to_previous_response",  # "no, I didn't mean that"
    "search_memory_request",    # "do you remember when I..."
    "direct_address_to_person", # "Jagan, what do you think?"
    "search_room_memory_request",  # "what did we discuss tonight?"
})
```

### Weekly Evaluation

`python tests/eval_weekly.py`: Runs golden-set bench, persists run to tests/eval_bench_runs/, compares to prior run. Queries intent_divergences for last 7 days. Alert on >= 5pp precision drop (`--alert` flag).

Golden corpus: tests/golden_intent.jsonl. 149 rows (adversarial + real_observed + synthetic_common + regression_session_X). Source taxonomy: adversarial = permanent, synthetic_common → legacy_synthetic when real_observed per intent >= 25, regression_session_X = permanent.

---

## 13. Room Sessions (Phase 3B)

### Room Session Lifecycle

A "room session" spans from the first person arriving to the last person leaving.

1. First `_open_session()` into empty `_active_sessions` → mint `room_{int(now)}_{uuid6}` as `_active_room_session`.
2. Subsequent opens → inherit existing `_active_room_session` (join, not mint).
3. Each session dict carries `room_session_id` field.
4. `_close_session()` checks if `_active_sessions` becomes empty → fire `_on_room_end()`.
5. Next open mints a DIFFERENT room_session_id (distinct rooms, not resurrection).

conversation_log rows carry room_session_id + audience_ids (JSON array of person_ids who can see the turn). Backfilled for legacy rows in FaceDB.__init__ (deterministic defaults from first turn per person).

### ROOM Block (_build_room_block)

Renders 4 sections for multi-person scenes:

1. **Active speakers**: Name, role label (best_friend/known/stranger).
2. **Room duration**: "Just started" (< 60s) / "Xm ago" (< 1h) / "Xh ago".
3. **Interleaved chronological turns**: All active speakers sorted by ts, capped at ROOM_BLOCK_TURN_CAP=10. Filtered by session boundary (ts >= session.started_at, Session 111 Critical #2). Format: `[Xm ago] Speaker → Addressee: "content"` for addressed assistant messages, `[Xm ago] Speaker: "content"` for user turns.
4. **Per-person mood**: EmotionAgent.get_dominant_emotion() or 'unknown'/'neutral' for missing agents.

### TURN ARBITRATION Rules (3B.3)

4 verbatim rules in <<<TURN ARBITRATION>>> block:
1. **MUMBLE CONTINUATION**: Continue with prior substantive speaker when current says "yeah"/"uh-huh".
2. **PENDING THREAD CIRCLE-BACK**: Return to A's earlier question after B's thread resolves.
3. **LONG-SILENCE RE-ENGAGEMENT**: Gentle check-in for speaker silent >= 4 turns, especially best_friend.
4. **DIRECT QUESTION ACROSS CONTEXT**: A asked you a clear question but B spoke last.

Marker format: `[addressing:Name]` on its own line at the START of response. Stripped before TTS. Lands in history.addressed_to field.

ADDRESS DECISION marker in _token_gen: buffers initial tokens until `]` found, regex parses `^\s*\[addressing:X\]\s*\n?(.*)$`, latches `_marker_done[0]`, flushes prefix on close. End-of-stream flush handles unclosed-marker edge case.

### User-to-User Silence (3B.2)

When one person addresses ANOTHER person by name, brain stays silent.

**`_user_to_user_heuristic(text, system_name, other_session_names)`**: Vocative-pattern regex (start-comma / end-comma / Hey-Hi-Hello + name). Returns ("user_to_person", name) / ("addressing_ai", system) / None. Eliminates ~80% of classifier calls in multi-person rooms.

**`_classify_intent_cached(text, history, active_session_pids)`**: 5-second TTL, 64-entry LRU eviction. Used for inconclusive heuristic cases.

Silent path: heuristic-confident → synthesize sidecar (skip classifier). Still logs the turn (history preserved), calls db.log_turn(), calls notify(), bumps user_turns.

ROOM_STAY_SILENT_ON_USER_TO_USER=True. System-name collision (human named same as AI) falls through.

### N-Speaker Transcript Format (3B.4)

`_format_multispeaker_transcript(named_pairs)`:
- N=2: legacy `[Name1]: text\n[Name2]: text` (backward compat)
- N>=3: `[N voices simultaneously]\n{Name}: text\n...` header format
- Unknown speakers: `unknown_1`, `unknown_2` numbering per-utterance (no cross-turn state)
- Non-primary speakers' sessions NOT auto-opened (regression guard against 3-speaker burst fragmenting into 3 strangers)

### search_room_memory Tool (3B.5)

`FaceDB.search_room_turns(room_session_id, keyword, requester_pid, limit=20)`: Full-text keyword search on room turn log, respects audience_ids filter (NULL = default-visible, non-NULL = requester must appear in JSON array).

`FaceDB.count_room_turns(room_session_id)`: Used for SEARCH_ROOM_MEMORY_MIN_TURNS=5 gate. Below threshold → return empty + hint message.

`_make_room_search_fn(room_session_id, requester_pid, db)`: 4-branch callback (disabled / no-room / too_young / ok). Always-registered tool, callback-side gate.

### Room-End Synthesis (3B.6)

`synthesize_room()` called from `_on_room_end()` as fire-and-forget asyncio task. Room lifecycle NEVER blocks. `_active_room_started_at` tracked for duration calculation.

`get_recent_room_context(person_id, hours=ROOM_RECENT_CONTEXT_HOURS=24)`: Returns most recent room summary where person participated. Used by `<<<RECENT ROOMS>>>` block in greeting context.

Block renders: summary + topics + safety hints + human-readable age. Gated on `vision_state["recent_room_context"]` being non-empty.

### KAIROS in Multi-Person

`_kairos_preferred_speaker(best_friend_id)`: Replaces `_primary_person_id()` in KAIROS path.
- Single session → return the one active pid
- Multi-session with best_friend active → prefer best_friend (natural engagement target)
- Multi-session without best_friend → longest-silence pid via `max(key=lambda pid: now - last_spoke_at)`

Gated on KAIROS_PREFER_BEST_FRIEND=True.

---

## 14. Emotion Processing (core/emotion.py)

### Model

`j-hartmann/emotion-english-distilroberta-base`. 7 emotions: anger, disgust, fear, joy, neutral, sadness, surprise. HuggingFace pipeline, GPU inference.

### EmotionAgent Per Session

Each session gets its own EmotionAgent instance (popped on fresh open, Session 111 Critical #5). Rolling 5-turn window. After 2+ consecutive non-neutral → stores `current_feeling` as temporal fact (is_temporal=True, valid_for_hours=4).

90s TTL on the emotion context. After 90s without new turn → state reset.

`get_dominant_emotion()`: Returns most frequent emotion in the 5-turn window, or 'neutral'.

### Background Processing (Session 110 Fix 2)

`_emotion_process_background(pid, pname, agent, text)`: Wraps `run_in_executor(agent.process_turn, text)` + `store_temporal_fact(current_feeling)` in a fire-and-forget asyncio task. HuggingFace inference is sync CPU; thread offload preserved inside the background task.

One-turn lag: emotion context for THIS turn reads the agent's PRIOR cached state. Next turn sees this turn's fresh emotion. Acceptable — emotion changes slowly, and the brain shouldn't react to mid-utterance mood shifts.

### Multi-Person Emotion Format

`<<<EMOTIONAL CONTEXT>>>` block in system prompt. Each active person listed with their dominant emotion. Format: `- Name (role): dominant_emotion (window: turn1_emotion, turn2_emotion, ...)`.

---

## 15. Anti-Spoofing (MiniFASNet)

### Model Architecture

Two MiniFASNet variants:
- `2.7_80x80_MiniFASNetV2.pth` (~0.9MB)
- `4_0_0_80x80_MiniFASNetV1SE.pth` (~0.9MB)

Both loaded from `models/antispoof_weights/`. Architecture from `core/_minifasnet/model.py` (MIT license, verbatim from minivision-ai/Silent-Face-Anti-Spoofing).

Ensemble: run both models, average softmax probabilities across models. `argmax == 1 AND confidence >= ANTISPOOFING_THRESHOLD` → live. Class indices: 0=fake, 1=live, 2=replay.

### Critical: No /255 Division

```python
# CORRECT — raw [0, 255] float tensor
tensor = torch.from_numpy(crop.astype(np.float32))  # NO .div(255.0)
```

Session 59 root cause analysis: MiniFASNet was trained on raw [0, 255] float values. The upstream minivision-ai `to_tensor()` explicitly does NOT divide by 255 for numpy inputs (the `.div(255)` line is commented out with note "modify by zkx"). The original Session 52 implementation added `.div(255.0)` erroneously. This caused every real face to score as class 2 (replay) at 95%+ confidence — 100% false rejection rate. Removing the `/255` normalization fixed the model.

### verify_live() Wrapper

```python
def verify_live(frame, bbox, anti_spoof_checker):
    if anti_spoof_checker is None:
        return True  # Fail-open: if unavailable, don't block the owner
    return anti_spoof_checker.is_live(crop)
```

Used at: enrollment (enroll.py), gallery self-update (pipeline recognition_update path), face-witness identity evidence write. Replaces 3 direct `is_live()` calls (Session 46 Finding D).

### ANTISPOOFING_THRESHOLD

Currently 0.5 (raised from 0.3 after the /255 fix confirmed real faces reliably score 0.45+). `LOG_ANTISPOOF_SUMMARY=True` with 100-frame rolling summary log: `[Anti-spoof] summary over last 100 frames: min=X.XX mean=Y.YY max=Z.ZZ rejects=N thr=0.50`.

### Integration Points

1. **Enrollment** (enroll.py): Gates every frame during capture. All-frames-rejected → `spoof_blocked=True` → TTS explains.
2. **First-boot flow** (pipeline.py): Same gate during initial enrollment.
3. **Gallery self-update** (pipeline.py recognition_update): Required for writing recognition_update embeddings. Prevents poisoning gallery with photos/screen captures.
4. **Identity evidence write**: `anti_spoof_live` and `anti_spoof_score` fields in identity_evidence dict, used by `<<<IDENTITY EVIDENCE>>>` verdict.

### Failure Mode

`available` property returns True only if both model weights loaded successfully. If models missing or corrupt → `is_live()` returns True (fail-open). The log prints "DISABLED" instead of "PASSED" when unavailable. The `verify_live()` wrapper handles None checker gracefully.

---

## 16. State Management & IPC (core/state.py)

### Purpose

`state.json` in `faces/` directory is the IPC channel between `pipeline.py` and the Next.js dashboard. The pipeline writes structured state; the dashboard polls and reads.

### Atomic Write

```python
def write(self, **kwargs):
    self._persistent.update({k: v for k, v in kwargs.items() if v is not None})
    data = {**self._state, **self._persistent, **kwargs}
    tmp = self._path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data))
    tmp.replace(self._path)  # Atomic on POSIX; near-atomic on Windows
```

`tmp.replace()` is atomic on POSIX (rename syscall). On Windows it's near-atomic but practically safe since dashboard reads are infrequent.

### _persistent Dict

Survives every `write()` call. Fields written with `_persistent.update()` persist until explicitly overwritten. Used for fields that must survive across many turns without being explicitly passed every time (e.g. current enrolled persons list, system name).

### State Fields Written by Pipeline

- `mode`: "watching" | "listening" | "thinking" | "offline"
- `current_person`: Name of active speaker
- `visible_people`: List of currently visible person names
- `system_name`: AI's current name
- `cloud_state`: "online" | "sick" | "offline"
- Various enrollment and session fields

### Dashboard Integration

The Next.js dashboard at `dog-ai-dashboard/` reads state.json via polling API routes. Also exposes:
- `/api/enroll`: Enrollment endpoint (conflicts with pipeline camera use — known pending issue)
- `/api/gallery-audit`: Calls `audit_gallery()` from core/audit.py
- `/api/delete`: Calls `execFile` (not exec) with delete_person.py. ID regex validation guards against injection.

---

## 17. Vision Channel Independence (core/vision_channel.py)

### Phase 2 of Voice/Vision Independence Refactor

`observe_scene()` is a pure function that takes a video frame + injected dependencies and returns a `PresenceState`. It has zero pipeline imports, zero voice-state reads, zero writes to shared mutable structures. AST-verified import boundary.

### PresenceState (Frozen Dataclass)

```python
@dataclass(frozen=True)
class PresenceState:
    visible_pids:           tuple[str, ...]   # Sorted descending by confidence
    unrecognized_track_ids: tuple[int, ...]   # SORT track IDs for unrecognized faces
    per_pid_confidence:     dict[str, float]  # Best cosine match per pid
    per_pid_quality:        dict[str, float]  # V1 quality score per pid
    frame_ts:               float             # Caller-provided wall-clock (never time.time() internally)
    reasoning:              str               # Human-readable diagnostic
```

`visible_pids` sorted descending by confidence. Callers (the reconciler) read strongest match first.

`frame_ts` is caller-provided for testability and determinism — the same discipline as `SessionState.now`.

### observe_scene() Pipeline

1. Validate frame (not None, is numpy array)
2. `face_detector.detect(frame)` — injected dependency
3. For each detection: crop → V1 quality gate → V2 yaw gate → embed → recognize
4. Best score per pid (a face detected multiple times keeps highest confidence)
5. Unrecognized faces (no gallery match) → track_id recorded in unrecognized_track_ids
6. Sort visible_pids by confidence descending
7. Return PresenceState

Never raises. On any internal error → returns empty state with reasoning describing failure.

### Hard Rules

The function MAY NOT:
- Import from `pipeline.py`
- Read voice state (`_voice_gallery`, `_active_sessions`)
- Write to `_persons_in_frame` or any shared module-level dict
- Call `time.time()` internally

If it needs voice context to make a decision, that's a bug. Return a low-confidence state and let the reconciler decide.

### Production Shadow Mode

Pipeline's `_background_vision_loop` runs observe_scene() with a SEPARATE detector/embedder (precomputed-detection shim to avoid SORT corruption + redundant detect cost). Throttled: one shadow comparison per 5 seconds. Emits `[VisionChannel-Shadow] divergence:` when visible_pids set differs from production _persons_in_frame face-source entries.

### Injectable Dependencies

`face_detector`: exposes `.detect(frame)` returning list of Detection objects with `bbox`, `landmarks`, `track_id`.
`face_embedder`: exposes `.embed(face_crop)` returning 1-D numpy array.
`face_db`: exposes `.recognize(emb, threshold)` returning (pid, name, conf).
`quality_score_fn` / `yaw_estimate_fn`: Optional. Default to `core.vision` helpers via lazy import.

---

---

## Section 18: Graph Classifier — core/classifier_graph.py

The graph classifier (Spec 2) is the production intent classifier that requires NO LLM calls in the hot path. It replaces the `_classify_intent` Together.ai shadow call with a local k-NN graph lookup over abstracted, embedded scenarios. Three deployment modes are supported: **shadow** (both run, LLM drives behavior, divergences logged), **primary** (graph runs first; if confidence >= GRAPH_PRIMARY_CONFIDENCE_FLOOR=0.55, return graph result; else fall back to LLM safety net), and **retired** (graph only, LLM never called; abstains if confidence below GRAPH_ABSTAIN_THRESHOLD=0.40).

### Module-level singletons

Three lazy singletons initialized on first use:
- `_classifier_db: ClassifierDB | None` — opened by `_get_db()`, which tries to open `CLASSIFIER_DB_PATH`. Returns None if the file doesn't exist (meaning the bootstrap pipeline hasn't been run yet). On None, the classifier returns None for every call, and callers fall back to LLM.
- `_embedding_agent` — determined by `_get_embedding_agent()`. If `GRAPH_USE_LOCAL_EMBEDDINGS=True`, creates a `LocalE5Embedder` singleton. Otherwise, creates a network `EmbeddingAgent` with a dedicated `httpx.AsyncClient(timeout=30.0)`.
- `_pending_outcomes: deque(maxlen=10)` — the 3-turn outcome supervision queue holding graph-classifier decisions awaiting outcome confirmation.

### LocalE5Embedder

When `GRAPH_USE_LOCAL_EMBEDDINGS=True`, this class provides embedding without a network call. Key design details:
- Lazy model load: `_load()` is only called on first `embed()` call, not at construction. The HuggingFace transformer model (`GRAPH_LOCAL_EMBEDDING_MODEL`) and tokenizer load in `run_in_executor` context.
- Device selection: Uses `GRAPH_LOCAL_EMBEDDING_DEVICE` config. "auto" falls back to CUDA if available, else CPU.
- Encoding: Wraps the text in the E5 instruction format: `"Instruction: represent the {purpose} for retrieval: {text}"`. This is the same convention used by the network EmbeddingAgent and is required for the E5 model to produce high-quality embeddings.
- Pooling: Mean-pool over last hidden states, weighted by attention mask. Then L2-normalize. This matches the network E5 endpoint's output so cosine similarities are comparable between local and network embeddings.
- Interface: `async def embed(text, purpose)` and `async def embed_batch(texts, purpose)`. The batch version calls embed sequentially since we typically only embed one text per turn.
- Target latency: ~30ms local vs ~400ms network, enabling the GRAPH_LATENCY_BUDGET_MS=100ms target to be met.

### `classify_intent_graph()` — the hot path

The full pipeline per turn:

**Step 1 — Abstract**: Call `abstract_text(user_text, persons_in_room, system_name)`. This strips PII (names → {P1}/{P2}, system_name → {SYSTEM}, places → {LOC1}) so the query vector is portable and PII-clean. Returns `(abs_text, mapping)` where `mapping = {"{P1}": "Lexi", ...}`.

**Step 2 — Embed**: Call `agent.embed(abs_text, purpose="classifier scenario")`. If the agent is None or embedding returns None, return None (caller falls back to LLM).

**Step 3 — Query graph**: Call `db.query_nearest(query_vector, k=GRAPH_K_NEIGHBORS, active_only=True)`. Returns a list of scenario dicts sorted by cosine similarity DESC. Each dict has: scenario_id, abstract_text, intent_label, similarity, outcome_confirmed, outcome_reverted, initial_confidence, extracted_value.

**Step 4 — Aggregate votes**: Call `_aggregate_votes(neighbors)`. This groups neighbors by `intent_label` and computes a weighted sum where each neighbor's weight is `cosine_sim * confidence_score(neighbor)`. `confidence_score` is the Wilson lower-bound (explained below). If the winning label's fractional weight (winning_weight / total_weight) is below `GRAPH_ABSTAIN_THRESHOLD`, return None (abstain).

**Step 5 — Resolve label evolution**: Call `db.resolve_label(winning_label)`. This checks the `label_evolution` table for deprecated label mappings. If the graph contains old label names, they get redirected to current ones. If the resolved label isn't in `INTENT_LABELS`, abstain defensively.

**Step 6 — De-abstract extracted_value**: Find the top-similarity voter for the winning label and read its `extracted_value` field (which stores placeholder forms like `{P1}`). Call `deabstract(raw_ev, mapping)` to substitute back the real names.

**Step 7 — Build sidecar**: Return the same dict shape as `_classify_intent`:
```python
{
    "turn_intent": winning_label,
    "extracted_value": extracted_value,
    "confidence": float,
    "reasoning": human-readable string showing label weights + top voters,
    "__usage": {
        "k_neighbors_queried": N,
        "scenarios_voted": M,
        "winning_voter_ids": [id1, id2, ...],
        "abstraction_ms": int,
        "embedding_ms": int,
        "graph_query_ms": int,
        "graph_decision": True,  # marker: this was a graph decision, record outcome
    }
}
```

The `"graph_decision": True` marker in `__usage` is how the pipeline knows whether to record the decision in the outcome supervision queue.

### Wilson lower-bound confidence (`confidence_score`)

Each scenario has `outcome_confirmed` and `outcome_reverted` counts and an `initial_confidence` (typically 0.5 for bootstrapped, 0.6-0.85 for hand-authored, 0.85 for live corrections). The Wilson lower-bound prevents a single confirmation from giving full credit:

```python
n = confirmed + reverted
if n == 0:
    return initial_confidence  # no evidence yet, use prior
p = confirmed / n
z = 1.96  # 95% CI
denom = 1 + z^2/n
center = p + z^2/(2n)
margin = z * sqrt((p*(1-p) + z^2/(4n)) / n)
return max(0, (center - margin) / denom)
```

A scenario confirmed once (1/1) gets Wilson lower bound of about 0.21 — not 1.0. Ten confirmations with zero reversions gives about 0.72. This means corrections have real but measured impact, and the graph doesn't overfit on sparse data.

### Vote aggregation (`_aggregate_votes`)

For each neighbor: `weight = cosine_sim * confidence_score`. Negative cosine similarities (near-orthogonal vectors) are clamped to 0 (no negative contribution). Weights accumulate per intent_label bucket. The winning label is the bucket with highest total weight. On ties, break by highest mean Wilson confidence among the bucket's voters. Confidence = winning_weight / total_weight.

### Outcome supervision queue

The 3-turn holding window:

**`record_pending_outcome(sidecar, user_text, persons_in_room, system_name)`**: Called by the pipeline after a graph decision is made. Mints a `decision_id = uuid.uuid4().hex`, pushes an entry onto `_pending_outcomes`. Entry holds: decision_id, intent_label, scenarios_used (list of scenario_id voted for the winning label), user_text, persons_in_room, system_name, ts, turns_aged=0.

**`age_pending_outcomes()`**: Called once per turn BEFORE new decisions are recorded. Increments `turns_aged` on every entry. Entries reaching `GRAPH_OUTCOME_HOLDING_TURNS` (default 3) get auto-credited via `confirm_pending(did, reason="silence_is_consent")`. Silence = consent: if the user didn't correct the AI in the next 3 turns, the decision was probably correct.

**`confirm_pending(decision_id, reason)`**: Increments `outcome_confirmed` on every scenario that voted for the winning label. Pops entry from queue. Returns count of scenarios credited.

**`revert_pending(decision_id, reason)`**: Increments `outcome_reverted`. Used by the correction handler.

**`latest_pending()`**: Returns the most recent queue entry (rightmost in deque). Used by `handle_correction()` to find the previous turn's decision.

### Correction loop (`handle_correction`)

When the classifier detects `correction_to_previous_response` as the intent (30 hand-authored bootstrapped examples cover phrasings like "No Kara, I was talking to Lexi"), the pipeline calls `handle_correction()` with the correction text. NO LLM call happens. The function:

1. Gets `pending_outcome = latest_pending()` (or uses caller-supplied value in tests).
2. Decrements `outcome_reverted` on every scenario that voted for the wrong label (only scenarios whose `intent_label` matches the wrong label — other-label voters from the k-NN pool weren't responsible).
3. Pops the pending entry to prevent double-credits.
4. Calls `extract_correction_target(correction_text, system_name)` to get the intended target name.
5. If a target is found, re-abstracts the PREVIOUS turn's user_text with the corrected target included in `persons_in_room`, embeds it, and inserts a new positive scenario with `intent_label="direct_address_to_person"`, `initial_confidence=0.85`, `source_tag="live_correction"`.

**`extract_correction_target(text, system_name)`**: Tries ~14 compiled regex patterns. Patterns with capture groups extract the target name. Patterns without capture groups (null-target corrections like "Kara, that wasn't for you") return None. Captures of "you", "me", "myself" are filtered out (they mean the correction was addressed at the AI, not at a third party). The pattern cache is keyed by system_name to avoid recompiling on every call.

### Lifecycle

**`aclose()`**: Closes the httpx client, nulls the embedding agent reference, closes the ClassifierDB connection. Called from the pipeline's shutdown handler.

**`reset_pending_outcomes()`**: Clears the deque. Test helper and factory reset hook.

---

## Section 19: Classifier Database — core/classifier_db.py

The `ClassifierDB` class is the persistence layer for the graph classifier's scenario store. It lives at `data/classifier_scenarios.db` — completely separate from `faces/faces.db` and `faces/brain.db`. The critical invariant: **factory reset must NOT touch this file**. `core/db.wipe_all()` only touches `faces/`; the `data/` directory is outside its scope. The classifier graph represents what the system has learned about language patterns across all deployments; personal data (faces.db, brain.db) resets independently.

### Schema (SCHEMA_VERSION = 2)

**`scenarios` table**: Primary store for all intent scenarios.
- `scenario_id INTEGER PRIMARY KEY AUTOINCREMENT`
- `abstract_text TEXT NOT NULL` — PII-stripped text of the scenario (the current live version for querying)
- `abstract_text_v1 TEXT NOT NULL` — original version at insert time (for auditing when abstraction rules change)
- `abstract_rule_version INTEGER DEFAULT 1` — which abstraction rule version produced this row
- `intent_label TEXT NOT NULL` — one of the 12 INTENT_LABELS (or a deprecated label, resolved via label_evolution at query time)
- `intent_label_version INTEGER DEFAULT 1` — for tracking when label semantics change
- `embedding BLOB NOT NULL` — float32 bytes of the E5 vector (1024-dim, L2-normalized)
- `embedding_model_id TEXT DEFAULT 'multilingual-e5-large-instruct-v1'` — tracks which E5 model version produced this embedding (switching models requires re-embedding)
- `source_tag TEXT NOT NULL` — provenance: "cornell_movie_dialogs", "daily_dialog", "empathetic_dialogues", "hand_authored", "live_correction", "unknown"
- `source_version TEXT NOT NULL` — version of the source/extraction pipeline
- `source_ref TEXT` — optional reference (decision_id for live corrections, dataset row id for bootstrapped)
- `outcome_confirmed INTEGER DEFAULT 0` — count of confirmed decisions involving this scenario
- `outcome_reverted INTEGER DEFAULT 0` — count of reverted (corrected) decisions
- `initial_confidence REAL DEFAULT 0.5` — prior confidence before any outcome data
- `extracted_value TEXT` — optional placeholder target (e.g. `{P1}`) for direct_address_to_person scenarios; de-abstracted at query time
- `active INTEGER DEFAULT 1` — quarantine flag; `active=0` rows are excluded from k-NN queries
- `schema_version INTEGER DEFAULT 1` — row-level schema version
- `created_ts TEXT`, `last_updated_ts TEXT` — ISO-8601 UTC timestamps

Unique constraint: `(abstract_text, intent_label)` — prevents duplicate scenarios.

Indexes: `idx_scenarios_intent` on `(intent_label, active)` for per-label queries; `idx_scenarios_source` on `(source_tag, source_version)` for provenance queries; `idx_scenarios_dedup` unique index.

**`schema_migrations` table**: Tracks which migrations have been applied. `version INTEGER PRIMARY KEY`, `description TEXT`, `applied_at TEXT`. Migration runner checks this table and skips already-applied versions. Idempotent.

**`label_evolution` table**: Maps deprecated label names to their successors. `(old_label, effective_version)` PK. `resolve_label(label)` queries this table (ORDER BY effective_version DESC LIMIT 1) to follow the most recent mapping chain. This allows the classifier to gracefully handle scenarios whose labels were renamed without requiring a re-labeling pass.

**`audit_log` table**: Every write operation (insert, outcome increment, quarantine, activate) records an event here. `scenario_id, event_type, delta, reason, decision_id, ts`. Indexed by `(scenario_id)` and `(ts DESC)`. Event types: `"created"`, `"outcome_confirmed"`, `"outcome_reverted"`, `"quarantined"`, `"activated"`. In addition to the SQL table, every audit event is mirrored to the JSONL append-only stream at `CLASSIFIER_AUDIT_LOG_PATH` for human-greppable per-deployment logs without opening SQLite.

**`db_metadata` table**: Key-value store for metadata. Default rows on fresh DB: `schema_version="2"`, `seed_version="1"`, `embedding_model="multilingual-e5-large-instruct-v1"`, `abstract_rule_version="1"`, `created_at=<ISO timestamp>`. All inserted with `INSERT OR IGNORE` so re-opens are no-ops; `created_at` is captured only once.

### Initialization sequence

1. `mkdir(parents=True, exist_ok=True)` for both db_path and audit_log_path parent directories.
2. `sqlite3.connect(WAL mode, foreign_keys=ON, row_factory=Row)`.
3. `_init_schema()` — CREATE TABLE IF NOT EXISTS for all 5 tables + indexes.
4. `_run_migrations()` — apply any pending migrations.
5. `_seed_metadata()` — INSERT OR IGNORE default db_metadata rows.

### Query API

**`query_nearest(embedding, k=20, active_only=True)`**: Brute-force cosine similarity over all active scenarios. Loads all rows, stacks their embeddings into a numpy matrix, dot-products with the query vector, divides by norms to get cosine similarities. Uses `np.argpartition(-sims, top_k-1)[:top_k]` for efficient top-K selection without full sort, then `argsort` for final ordering. Returns list of dicts sorted by cosine DESC, each containing the row columns plus `similarity`. At ~1,500-2,000 rows × 1024-dim this is ~8MB in memory — trivially fast. If the corpus grows past ~100K rows, the comment says to swap in FAISS.

**`resolve_label(label)`**: Checks `label_evolution` for the most recent mapping of `label`. Returns the mapped new_label or the original if no mapping exists.

**`get_scenario(scenario_id)`**: Single row lookup by primary key.

**`count_scenarios(active_only=True)`**: SELECT COUNT(*) with optional active filter.

### Write API

**`insert_scenario(..., skip_if_duplicate=True)`**: The main write path. Uses `INSERT OR IGNORE` when `skip_if_duplicate=True` (the unique index on `(abstract_text, intent_label)` prevents duplicates). Writes the float32 embedding as raw bytes via `arr.tobytes()`. Returns `scenario_id` on insert, `None` on duplicate. Commits and logs a "created" audit event.

**`increment_outcome(scenario_id, kind, decision_id, reason)`**: Updates `outcome_confirmed` or `outcome_reverted` counter + `last_updated_ts`. Raises `KeyError` if the scenario_id doesn't exist (rowcount == 0). Commits and logs the appropriate event.

**`quarantine(scenario_id, reason)`**: Sets `active=0`. Raises KeyError on missing ID. Logs "quarantined".

**`activate(scenario_id, reason)`**: Inverse of quarantine. Sets `active=1`. Logs "activated".

**`add_label_evolution(old_label, new_label, effective_version, reason)`**: INSERT OR REPLACE into label_evolution. Commits. No audit event (this is a schema operation, not a scenario operation).

### Bootstrap

**`seed_from_jsonl(seed_path)`**: Loads scenarios from a JSONL file. Each line must have `abstract_text`, `intent_label`, and embedding (either as `list[float]`, base64 string, or `"embedding_b64": base64`). Also reads `source_tag`, `source_version`, `source_ref`, `initial_confidence`, `embedding_model_id`, `abstract_rule_version`, `extracted_value`. Uses `skip_if_duplicate=True` so re-seeding is safe. Returns count of newly-inserted rows. This is how `data/classifier_scenarios.db` gets populated from `data/classifier_scenarios_seed.jsonl` on first boot.

### Snapshots

**`snapshot(snapshot_dir, retain_days=30)`**: WAL checkpoint (`PRAGMA wal_checkpoint(TRUNCATE)`) then `shutil.copy2()` to a date-stamped file `classifier_scenarios_YYYYMMDD_HHMMSS.db`. Prunes snapshots older than `retain_days` by checking file mtime. Returns the snapshot path.

---

## Section 20: Abstraction Layer — core/abstraction.py

The abstraction module strips PII from user utterances so the graph classifier operates on deployment-portable, PII-clean scenarios. The key insight is that "Hi Lexi, are you feeling better?" and "Hi Sarah, are you feeling better?" should map to the same classifier scenario `"Hi {P1}, are you feeling better?"` — the intent (direct_address_to_person) is identical regardless of the specific name.

### Two-pass strategy

**Pass 1 — Registry-first (fast, deterministic)**: Replace known persons from `persons_in_room` and the `system_name` via regex. No model load required. This pass is microseconds-fast.

For each name in `persons_in_room` (in order of appearance): assign placeholder `{P1}`, `{P2}`, etc. and record in `mapping = {"{P1}": "Lexi", ...}`. Use `re.compile(r"\b" + re.escape(name) + r"\b", re.IGNORECASE)` for word-boundary matching. Names are processed in order so placeholders are deterministic.

For `system_name`: replace with `{SYSTEM}` via similar word-boundary regex. Recorded in mapping as `{"{SYSTEM}": "Kara"}`.

**Pass 2 — NER fallback for residual unknowns**: For names not in `persons_in_room` (e.g. someone mentioned but not present in the session). Runs `spacy.load("en_core_web_sm")` on the first call, cached as a module-level singleton `_NLP`. Failure is non-fatal: `_NLP_LOAD_FAILED = True` is set and subsequent calls skip NER. If spacy isn't installed or the model isn't downloaded, only Pass 1 runs.

NER entity types abstracted: `PERSON` → `{P1}`, `{P2}`, etc. (incrementing counter shared with Pass 1). `GPE, LOC, FAC` (places) → `{LOC1}`, `{LOC2}`, etc.

NOT abstracted: `ORG, EVENT, PRODUCT, DATE, TIME, MONEY, CARDINAL, ORDINAL, PERCENT, QUANTITY`. These carry intent signal: "What's the temperature in Mumbai right now?" loses meaning if Mumbai is stripped; the model needs geographic context to classify as `live_data_query`.

The NER pass is applied right-to-left over the spans (sorted by `start_char` descending) so earlier character offsets remain valid as the string is mutated.

Existing placeholders (strings starting with `{` and ending with `}`) are skipped in the NER pass — spacy might tag `{P1}` as a PERSON entity, which would double-abstract it.

### `abstract_text()` return value

Returns `(abstracted_text, mapping)` where:
- `abstracted_text`: the text with all known persons, system name, and any NER-detected names/places replaced by placeholders
- `mapping`: `dict[placeholder → original]` — e.g. `{"{P1}": "Lexi", "{SYSTEM}": "Kara", "{LOC1}": "Mumbai"}`

### `deabstract(text, mapping)`

Inverse function. Substitutes placeholders back to originals. Used by the graph classifier to convert `extracted_value` (stored as `{P1}` in scenarios) back to the actual name. Replaces longer keys first (sorted by len descending) to prevent `{LOC10}` from being partially replaced by `{LOC1}`.

### Design decisions

Times, dates, numbers are intentionally preserved because:
- "What's the score right now?" vs "What was the score yesterday?" have different intents (`live_data_query` vs `general_knowledge_query`)
- "Mumbai" in "What's the temperature in Mumbai?" is needed to classify as live_data_query
- The classifier's training scenarios also preserve these tokens so the embedding space is consistent

The NER-fallback is a best-effort safety net for bootstrap quality, not a hard requirement. Production scenarios are mostly abstracted by the registry pass since `persons_in_room` is populated from active sessions.

---

## Section 21: Enrollment — enroll.py

The enrollment script is the standalone CLI for adding a new person to the face recognition system. It is also called by the dashboard's `/api/enroll` endpoint.

### Usage

```
python enroll.py --name "Jagan" [--frames 10] [--headless]
```

### Person ID format

```python
safe = re.sub(r"[^a-z0-9_-]", "_", name.lower())
safe = re.sub(r"_+", "_", safe).strip("_")[:50] or "unknown"
person_id = f"{safe}_{uuid.uuid4().hex[:6]}"
```

Example: "Jagan" → `"jagan_f3a8b2"`. "Jean-Luc Picard" → `"jean-luc_picard_c7d4e1"`. The person_id is filesystem-safe and collision-resistant. The 6-char UUID hex suffix makes it unique even when multiple people with the same name are enrolled.

### Camera modes

**GUI mode**: `camera.capture_frames_with_preview(n=10, interval=0.5)` — shows a live OpenCV window. User presses SPACE to start capture, Q to quit. Falls back to headless if `Camera.gui_available()` returns False (checked via `cv2.imshow` + `waitKey` test in a headless detection shim).

**Headless mode**: `camera.capture_frames(n=10, interval=0.3)` — captures silently at 0.3s intervals.

### Per-frame processing

For each captured frame:
1. `detector.detect(frame)` — RetinaFace detection. Takes the largest face by area: `max(detections, key=lambda d: (d.bbox[2]-d.bbox[0]) * (d.bbox[3]-d.bbox[1]))`.
2. Crop `frame[y1:y2, x1:x2]`. Skip if crop is empty.
3. **V1 quality gate**: `face_quality_score(face_crop) < FACE_QUALITY_ENROLLMENT` → skip with log.
4. **V2 yaw gate**: `estimate_yaw_from_landmarks(det.landmarks, det.bbox)` → if `abs(yaw) > 60.0` → skip with log.
5. **Anti-spoof gate**: `verify_live(frame, det.bbox, anti_spoof)` → if False (photo/screen replay detected) → skip with log. Note: `anti_spoof` is None when `ANTISPOOFING_ENABLED=False`, and `verify_live` returns True in that case (fail-open for disabled anti-spoof).
6. `embedder.embed(face_crop)` → 512-dim float32 embedding. Appended to `pending_embeddings`.
7. `photo_frame = frame` on first good embedding (saved as the profile photo).

### DB writes (FK order is critical)

```python
db.add_person(person_id, name, photo_path)   # INSERT OR IGNORE — must come first
for emb in pending_embeddings:               # FK: embeddings.person_id → persons.id
    db.add_embedding(person_id, emb, "enrollment")
```

`add_person` uses `INSERT OR IGNORE` so re-enrolling with an existing person_id is a safe no-op. `add_embedding` enforces the FK constraint, so if `add_person` were called AFTER `add_embedding`, the foreign key would fail.

### Photo save

```python
photo_path = str(FACES_DIR / f"{person_id}.jpg")
cv2.imwrite(photo_path, photo_frame)
```

Photo is only written if at least one good embedding was captured (`photo_frame is not None`). The photo is used by the dashboard's gallery view.

### Error handling

If `pending_embeddings` is empty at the end of frame processing, the script prints a diagnostic and calls `sys.exit(1)`. The `finally: camera.release()` block ensures the camera is released even on error.

---

## Section 22: Person Lifecycle & Deletion

### person_lifecycle.py — Single authoritative deletion path

The critical design principle: all code that removes a person MUST call `delete_person_everywhere()`. This ensures every store is cleaned atomically. New tables referencing persons must add a hook here.

```python
def delete_person_everywhere(person_id, person_name, faces_db, brain_orch) -> dict:
```

Returns a summary dict: `{"faces": "ok", "brain_rows": N, "shadows": M, "graph": "ok"|"skipped..."|"error..."}`.

### Deletion order and name-collision guard

**Pre-deletion check**: Before deleting the `persons` row from faces.db, check for name collisions in the Kuzu graph. Kuzu's Entity PK is the person's `name` string. If another enrolled person shares the same name, deleting by name would corrupt their graph node too.

```python
name_shared = faces_db._conn.execute(
    "SELECT COUNT(*) FROM persons WHERE name = ? AND id != ?",
    (person_name, person_id),
).fetchone()[0]
```

This must run BEFORE `faces_db.delete_person(person_id)` so the comparison is faithful (the row we're deleting is still present).

**Step 1 — faces.db**: `faces_db.delete_person(person_id)`. This deletes the `persons` row, all `embeddings` rows, all `voice_embeddings` rows, all `conversation_log` rows, NULLs `silent_observations.matched_person_id` rows, and calls `_rebuild_faiss()`. FAISS always rebuilt after deletion.

**Step 2 — brain.db**: `brain_orch.brain_db.delete_person_data([person_id])`. Deletes from: `knowledge`, `episodes`, `presence_log`, `prompt_prefs`, `proactive_nudges`, `watchdog_alerts`, `agent_log`, `social_mentions`. Also handles `inter_person_relationships` (JSON referencing this person) and `household_facts` source_speakers JSON. Returns count of deleted rows.

**Step 3 — shadow_persons**: `brain_orch.brain_db.prune_shadows_mentioning(person_id, person_name)`. Removes shadow nodes whose `known_via` JSON references this person. Returns count of affected shadows.

**Step 4 — Kuzu graph**: If no name collision: `brain_orch.graph_db.delete_person_entity(person_name)`. Deletes the Entity node and all its edges. If there's a name collision, prints a log and records `"skipped (name shared by N other(s))"` in the summary.

### delete_person.py — CLI wrapper

```
python delete_person.py --id "jagan_abc123"
```

Looks up `person_name` from faces.db: `db.get_person_name_by_id(person_id)`. Calls `delete_person_everywhere(person_id, person_name, faces_db, brain_orch)`. Deletes the profile photo: `FACES_DIR / f"{person_id}.jpg"`. Properly closes DB connections: `faces_db._conn.close()` and `brain_orch.close_connections()`.

---

## Section 23: Gallery Audit — core/audit.py

The gallery audit system detects embedding outliers in a person's face gallery. An outlier is an embedding that is unusually far from the gallery's centroid — potentially from a lighting anomaly, a different person's face accidentally enrolled, or a corrupted frame.

### `audit_gallery(person_id, db)` → dict

Loads all embeddings for the person from faces.db. Requires at least 2 embeddings for meaningful statistical analysis (returns early with a `"too_few"` status otherwise).

**Centroid computation**:
```python
gallery = np.array([...all embeddings...])  # shape: (N, 512)
centroid = gallery.mean(axis=0)
centroid_normalized = centroid / np.linalg.norm(centroid)  # L2-normalize
```

**Distance computation**: For each embedding, cosine distance = `1.0 - np.dot(emb_normalized, centroid_normalized)`. Range [0, 2] where 0 = identical direction, 2 = opposite direction. In practice, face embeddings from the same person cluster in the 0.0–0.15 range, while embeddings from a different person typically fall 0.4–0.8 away.

**Outlier threshold**: `mean_distance + 2 * std_distance`. This is 2 standard deviations above the mean — a standard statistical outlier heuristic.

**Return value**:
```python
{
    "person_id": str,
    "total": int,
    "mean_distance": float,
    "std_distance": float,
    "threshold": float,
    "outliers": [
        {
            "row_id": int,         # database row ID for targeted deletion
            "source": str,         # "enrollment", "recognition_update", "progressive_enroll"
            "confidence_at_write": float,
            "captured_at": str,    # ISO timestamp
            "distance_from_centroid": float
        }
    ]
}
```

### `repair_gallery(person_id, db, mode)` → int

- `mode='flag'`: Returns count of outliers without modifying the database. Safe for inspection.
- `mode='remove'`: Deletes the outlier rows from the `embeddings` table, then calls `db._rebuild_faiss()`. The FAISS index is always rebuilt after deletion to ensure consistent state.

The `audit_person.py` CLI wraps this function for command-line use. The dashboard's `/api/gallery-audit` route also calls it.

---

## Section 24: Logging Utilities — core/log_utils.py

A tiny utility module with two functions used throughout audio.py and pipeline.py for consistent timestamp and truncation formatting.

### `_now_log_ts() → str`

Returns a human-readable timestamp string for log lines. Uses `datetime.now().strftime(LOG_TIME_FORMAT)`. When the format string ends with `%f` (microseconds), the output is trimmed to milliseconds by cutting the last 3 characters. This keeps log lines compact while preserving sub-second precision. Example output: `"14:23:07.451"` rather than `"14:23:07.451892"`.

### `_log_trunc(s, limit=None) → str`

Truncates a string for log output. When `limit` is None, uses `LOG_STT_MAX_CHARS` from config. When `limit=0`, no truncation occurs (used for diagnostic paths where full output is needed). When the string exceeds the limit, appends `"…"` and returns the first `limit` characters followed by the ellipsis. Used primarily for STT transcript logging so long transcriptions don't flood the terminal output.

Both functions are imported by `core/audio.py` and `pipeline.py` via `from core.log_utils import _now_log_ts, _log_trunc`.

---

## Section 25: Pipeline Main Loop — pipeline.py Architecture

The pipeline is the central orchestrator — a single `asyncio` event loop that coordinates all subsystems. Understanding its architecture is essential for understanding how the entire system fits together.

### Module-level state (not in a class)

The pipeline uses module-level globals rather than a class instance. This is by design — it avoids passing a massive state object through every helper call. Key globals:

**Session state**: `_active_sessions: dict[str, dict]` — one entry per open session, keyed by person_id. Each session dict holds: `person_type`, `name`, `started_at`, `last_face_seen`, `waiting_for_name`, `person_type`, `engagement_gate_passed`, `voice_face_confirmed`, `voice_match_conf`, `voice_last_heard_ts`, `bootstrap_credits`, `face_match_conf`, `face_last_seen_ts`, `anti_spoof_live`, `anti_spoof_score`, `anti_spoof_last_ts`, `voice_sample_count`, `room_session_id`, `kairos_clock_reset`, `disputed`, `disputed_block_count`, `disputed_block_alerted`, `prior_person_type`, `dispute_started_at`, `disputed_rename_blocked`, `user_turns`, `ts`, `addressed_to`, `compact_running`.

**Room state**: `_active_room_session: str | None` — the current room session ID, minted when first person opens a session into an empty room. `_active_room_started_at: float | None` — wall time of room session start. `_active_room_participants: set[str]` — PIDs of everyone who joined the room.

**Vision state**: `_persons_in_frame: dict[str, dict]` — entries added by background vision loop (source="face") and voice routing (source="voice"). Each entry: `name`, `pid`, `conf`, `source`, `last_seen`, `last_recognized_at`. Background face scan adds/updates face-source entries. `_close_session()` immediately pops the pid from `_persons_in_frame` to prevent stale scene block entries.

**Voice state**: `_voice_gallery: dict[str, np.ndarray]` — in-memory mean voice embedding per pid. `_voice_gallery_sizes: dict[str, int]` — sample counts. `_unrecognized_tracks: dict[int, list[np.ndarray]]` — accumulated embeddings for unrecognized face tracks. `_stranger_track_map: dict[int, str]` — maps SORT track_id to stranger session pid for consistent attribution.

**Audio pipeline**: `_last_main_speech_secs: float` — duration of the last primary utterance's speech content (not buffer length). Published from `record_until_silence` only on non-empty recordings (Session 79 P0 fix). `_last_addendum_speech_secs: float` — duration of the addendum probe's speech content.

**Routing state**: `_recent_attributions: deque` — recent speaker attributions for drift detection. `_identity_hints: dict` — cached query embedding per pid for memory search. `_query_embedding_cache: dict` — embedding cache for memory queries. `_emotion_agents: dict[str, EmotionAgent]` — per-person emotion agents, popped on fresh session opens to prevent cross-session mood carryover.

### `_open_session(person_id, name, person_type, engagement_gate_passed, now)`

Creates or reinitializes a session dict. On fresh opens (not re-opens), pops `_emotion_agents[person_id]` to reset the emotion window. Sets `room_session_id`: if `_active_room_session` is None, mints a new room session ID (`room_{int(now)}_{uuid6}`) and sets `_active_room_session`, `_active_room_started_at`. If a room is already active, inherits the existing ID. Hydrates `voice_sample_count` from `_voice_gallery_sizes` so re-opened sessions carry forward prior voice accumulation progress.

### `_close_session(person_id)`

Immediately pops `person_id` from `_persons_in_frame` (prevents stale scene block entries). Calls `_prune_zero_value_stranger(person_id)` if person_type is "stranger" (removes ghost sessions with zero voice samples and zero turns). Clears `_pending_stranger_voice[person_id]`. If closing empties `_active_sessions`: clears `_active_room_session`, snapshots `room_id + speaker_pids + started_at`, dispatches `asyncio.create_task(_on_room_end(...))` fire-and-forget. Pops from `_query_embedding_cache` and `_identity_hints`.

### `_resolve_actual_speaker(v_pid, v_score, cur_pid, cur_person_type, n_diarize_segments, utterance_duration, voice_gallery_sizes, n_active_sessions)` → `(pid, action)`

The 5-priority routing cascade (Session 42, Issue #16):

**Bug F — short utterance floor** (Session 67): If `utterance_duration < VOICE_ROUTING_MIN_UTTERANCE_SECS=1.0` AND `v_score < VOICE_ROUTING_SHORT_UTT_MISMATCH_ENABLED=0.20`, return `(cur_pid, "short_utterance_voice_mismatch")` — drop turn. If duration < floor AND score >= 0.20, return `(cur_pid, "short_utterance_skip")` — hold current. This prevents phantom stranger sessions from brief social closers.

**Priority 0 — ambiguous zone drop** (Session 93): If `n_active_sessions >= 2` AND `v_score in [0.20, VOICE_ROUTING_SHORT_UTT_AMBIGUOUS=0.40)`, return `(cur_pid, "ambiguous")` — drop. Prevents cheese-cascade cross-attribution in multi-person rooms.

**Multi-segment stranger detection** (Session 118): If `n_diarize_segments >= 2` AND `v_score < VOICE_ROUTING_STRANGER_FLOOR=0.30`, return `(cur_pid, "multi_segment_voice_mismatch")` — drop. Handles the case where pyannote detected multiple speakers but voice ID couldn't match the second voice against any enrolled gallery.

**Priority 1 — clear winner**: If `v_score >= _effective_switch_threshold(v_pid, voice_gallery_sizes)`, return `(v_pid, "switch_enrolled")`. The effective threshold scales down for small galleries: `threshold * (gallery_size / SWITCH_THRESHOLD_MATURE_GALLERY_SIZE)^0.5`, floored at `VOICE_ROUTING_SWITCH_FLOOR`.

**Priority 2 — face+voice agree**: If `v_pid in _active_sessions` AND `v_pid in _persons_in_frame` AND `_face_in_frame(v_pid)` AND `v_score >= VOICE_ROUTING_FACE_ASSIST_MIN=0.42`, return `(v_pid, "switch_enrolled")`.

**Priority 3 — hold current or new stranger**: If `cur_pid is None`, return `(None, "new_stranger")`. If `cur_person_type == "stranger"` AND gallery thin (< N_INITIAL_VOICE): relaxed path, return `(cur_pid, "current")` — thin-stranger relaxation (Session 49). Else if voice score passes self-match floor (VOICE_ROUTING_SELF_MATCH_FLOOR=0.30, or VOICE_ROUTING_SELF_MATCH_OFFSCREEN=0.45 when face isn't in frame), return `(cur_pid, "current")`. Else ambiguous.

### `conversation_turn(person_id, audio_buf, db, ...)` — the per-turn brain call

This is the central coroutine called for every utterance attributed to a person. High-level flow:

1. **Speech duration stash**: `_main_speech_secs = getattr(core.audio, "_last_speech_secs", 0.0)`. Stashed immediately before STT so addendum probe can't clobber it.

2. **STT**: `transcribed_text = await loop.run_in_executor(None, transcribe, audio_buf)`. 4 post-processing filters: repetition filter, hallucination filter, char-run filter (16+ same char), too-short filter.

3. **Intent classifier** (shadow mode): `_intent_sidecar = await _classify_intent(user_text, conversation_history)` or graph classifier depending on `GRAPH_CLASSIFIER_MODE`. In shadow mode: both run, LLM result drives behavior, divergences logged.

4. **Correction detection**: If sidecar indicates `correction_to_previous_response`, call `handle_correction()` (LLM-free) and return early — brain stays silent.

5. **Age pending outcomes**: `age_pending_outcomes()` bumps the supervision queue.

6. **History load**: `conversation_history = _conversation.get(person_id, [])[-CONVERSATION_HISTORY_LIMIT:]`.

7. **Vision/voice state build**: Assembles `vision_state` dict containing: `persons_in_frame` (from `_persons_in_frame`), `active_session_count`, `session_person_type`, `scene_block` (from `_build_scene_block()`), `room_block` (from `_build_room_block()`), `recent_room_context`, plus per-session fields. Assembles `voice_state` dict with: `multi_speaker`, `multi_speaker_speakers`.

8. **Memory search function**: `_make_memory_search_fn(person_id, best_friend_id, db)` — creates a closure that calls `brain_db.query_knowledge_for(requester_pid, best_friend_id, ...)` with privacy visibility clause applied.

9. **Prompt addendum**: From `brain_orchestrator.get_prompt_addendum(person_id)`. May contain `[visitor_id:]` markers for VISITOR CONTEXT block, VISITOR_ALERT content, proactive nudges.

10. **`ask_stream()`**: The main LLM call. Streaming response. Simultaneously: speech synthesis starts as tokens arrive (via `_sentence_stream` which batches into minimum-size chunks: MIN_FIRST=30, MIN_REST=15 words). Tool calls extracted from stream.

11. **Token streaming with address marker detection**: `_token_gen` coroutine buffers initial tokens looking for `[addressing:Name]` prefix. When found, latches `_marker_done`, resolves addressed_to via `_resolve_addressed_to()`, flushes remaining response. This is how the brain signals who it's addressing in multi-person rooms.

12. **Background autocompaction**: If token count exceeds threshold: `asyncio.create_task(_compact_history_background(person_id, person_name))`. Non-blocking; this turn reads the current (uncompacted) history, next turn reads the compacted version.

13. **Tool dispatch**: Calls `_execute_tool(tool_name, tool_args, person_id, ..., intent_sidecar)` for each tool call. The intent gate (`_intent_allows()`) validates tool calls against the classifier sidecar.

14. **Retry on all-unreal**: If all tool calls returned "rejected" or "unknown": `ask_retry_text()` with `retry_system_note` (Session 99 Fix E). On ONLINE cloud: Together.ai retry with tools disabled. On SICK/OFFLINE: Ollama fallback.

15. **History append**: `_conversation[person_id].append({"role": "user", "content": ..., "ts": time.time()})` and `{"role": "assistant", "content": ..., "ts": ..., "addressed_to": ...}`. The `ts` field is used by `_build_cross_person_excerpts` session-boundary filter (Session 111).

16. **DB logging**: `db.log_turn(person_id, "user", text, room_session_id=..., audience_ids=[person_id])` and same for assistant. Skipped when session is disputed.

17. **Brain notification**: `brain_orchestrator.notify(person_id, user_text, response_text, person_name, person_type)` — triggers extraction, contradiction check, graph sync in background.

18. **Background emotion processing**: `asyncio.create_task(_emotion_process_background(pid, pname, agent, text))` — HuggingFace emotion classifier runs in thread executor, result writes back to agent, fact stored in brain.db.

### WATCHING loop — the outer loop

`run()` contains the outer WATCHING loop that runs continuously at ~20 FPS (`asyncio.wait_for(shutdown_event.wait(), timeout=0.05)`). Each iteration:

1. Checks `_shutdown_event` — if set, breaks and enters cleanup.
2. Calls `_expire_stale_sessions()` — closes sessions that have exceeded VOICE_SESSION_TIMEOUT with no face/voice detected.
3. Calls `_dream_loop()` on the brain orchestrator if idle > DREAM_IDLE_MINUTES or force-trigger interval exceeded.
4. Reads detection results from background vision loop queue.
5. For each recognized person: `_open_session()` if new, update `_persons_in_frame`. For unrecognized tracks: accumulate embeddings in `_unrecognized_tracks[track_id]`.
6. Checks for voice activity from the STT layer. Calls `_resolve_actual_speaker()` to route the utterance.
7. Based on routing action: `switch_enrolled` → close old session, open new; `new_stranger` → open stranger session; `current` → continue with cur_pid; `ambiguous/short_utterance_voice_mismatch/multi_segment_voice_mismatch` → drop turn.
8. After routing: calls `conversation_turn(resolved_pid, audio_buf, db, ...)` for attributed turns.
9. Runs `_kairos_tick()` for silence-triggered proactive questions.

### Shutdown sequence

1. Set `_shutdown_event` — outer loop exits naturally.
2. `stop_audio()` — stops any playing TTS.
3. Cancel `_background_vision_task`.
4. `camera.release()` — releases the camera.
5. Cancel voice recording tasks.
6. `db.close()` — closes faces.db.
7. `brain_orchestrator.close_connections()` — closes brain.db + Kuzu.
8. Wait for `_brain_task` with 2s timeout.
9. Cancel `_cloud_monitor_task`.
10. Write `state.json` with `mode="offline"`.

All steps have explicit timeouts and try/except so a stalled subsystem doesn't prevent cleanup.
