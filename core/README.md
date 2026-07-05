# core/: the engine

The domain-agnostic runtime engine: perception, identity, memory, speech, resilience. Everything here is product-neutral, what the system deploys AS (companion, robot, kiosk) is selected by `profiles/` + `persona/`, never hardcoded here. 46 top-level modules + 4 subpackages.

## Perception
| Module | What it actually does |
|---|---|
| `vision.py` | `FaceDetector` (SCRFD/RetinaFace + SORT tracking, detect every 5th frame), `FaceEmbedder` (AdaFace IR101 ONNX, 512-dim), `Camera` (DirectShow/V4L2 + reconnect), `AntiSpoofChecker` (MiniFASNet liveness), quality gates V1-V4 (size/blur/brightness, yaw, temporal pooling, adaptive threshold) |
| `vision_channel.py` | pure `observe_scene()`, zero pipeline imports (AST-enforced boundary) |
| `sort.py` | SORT tracking (Kalman + Hungarian assignment) |
| `object_detection.py` | Florence-2 on-device + Qwen-VL cloud fallback, **gated OFF by default** (`OBJECT_DETECTION_ENABLED=False`) until the Jetson accuracy benchmark passes |
| `_florence2/`, `_minifasnet/` | vendored model code, pinned, LICENSE files included, `trust_remote_code=False` |

## Audio & voice
| Module | What it actually does |
|---|---|
| `audio.py` | faster-whisper STT (large-v3-turbo), Kokoro ONNX TTS (Piper fallback), RMS/Silero VAD, Smart-Turn neural end-of-turn, lip-tracking extension, hallucination filters |
| `voice.py` | SpeechBrain ECAPA-TDNN speaker ID + pyannote 3.3.2 diarization (both from pinned forks, see NOTICE) |
| `voice_channel.py` | the voice evidence channel (abstains on no-signal, never vetoes) |

## Identity & sessions
| Module | What it actually does |
|---|---|
| `reconciler.py` | the sole speaker-routing authority, a 23-rule ordered cascade with per-rule LOWER_BOUND band invariants; locked by contract + per-rule + golden tests |
| `session_state.py` | typed `Session`/`SessionSnapshot`/`VoiceEvidence` (frozen dataclasses) + `SessionStore` (async mutators, sync peeks) |
| `presence_store.py`, `track_store.py`, `reconciler_state.py` | typed stores for presence/tracks/routing state |
| `anti_spoof_rejection_store.py` | per-track anti-spoof rejection history + burst alerting |

## Memory & knowledge
| Module | What it actually does |
|---|---|
| `db.py` | `FaceDB`, SQLite (WAL) + FAISS face index with SQL-first paired-write atomicity, sentinel crash-recovery, boot reconciliation |
| `brain_agent/` | the knowledge pipeline package: `orchestrator.py`, 15 agent classes across 12 files under `agents/` (triage, extraction, contradiction, prefs [PromptPref + FrictionDetection], household, social [SocialGraph + Identity], briefing [Briefing + ConversationInsight], nudge, routine, schema, watchdog, embedding), `memory/` (SQLite store + Kuzu graph), `privacy.py` (4-tier visibility), `_llm.py` (the shared retry-safe LLM helper, the only sanctioned chat-endpoint caller) |
| `classifier_db.py`, `classifier_graph.py`, `abstraction.py` | the pure-graph intent classifier (no LLM in the hot path) + its seed DB + NER abstraction |
| `cache_store.py`, `conversation_store.py`, `voice_gallery_store.py`, `per_person_agent_store.py`, `vision_frame_store.py`, `pipeline_state_store.py` | the typed Store family (all subclass `store_base.Store`, all reset between tests) |

## Brain & language
| Module | What it actually does |
|---|---|
| `brain.py` | LLM interface: Together.ai primary (Llama-3.3-70B, streaming + tool calling), Ollama fallback (qwen2.5:7b), the persona-slotted system prompt is composed here (`_compose_system_prompt`) |
| `persona_loader.py`, `profile_loader.py` | fail-loud loaders for `persona/` packs and `profiles/` (unknown id = crash, never silent fallback) |
| `sanitize.py` | `wrap_user_input`, NFKC + control-char rejection + XML-tag strip on every direct user-text to LLM path (AST-enforced coverage) |
| `emotion.py` | distilroberta emotion classifier, rolling 3-turn window |

## Infrastructure & resilience
| Module | What it actually does |
|---|---|
| `config.py` | ALL constants, the single source of truth; no magic numbers elsewhere |
| `heavy_worker.py` | ProcessPoolExecutor subprocess pools for all 4 GPU inference paths (AdaFace/Whisper/ECAPA/pyannote), the asyncio loop never blocks on C-extension inference; crash detection + burst watchdog |
| `event_log/` | append-only event sourcing (12 payload types, bounded queue, replay via `tools/replay_session.py`) |
| `health.py`, `disk_monitor.py`, `crash_logs.py` | 5-min health pulse, disk thresholds, JSON-per-crash forensics, all with operator-actionable alerts |
| `schema_migrations.py` + `faces_db_migrations.py` + `brain_db_migrations.py` | versioned ledger migrations (apply + verify_post + verify_present per entry) |
| `state.py`, `backup.py`, `env_validation.py`, `dashboard_token.py` | atomic state IPC, daily backups, boot env validation, dashboard auth token |
| `pipeline_invariants.py`, `log_utils.py`, `vision_provider_state.py` | shared invariant constants, log helpers, CUDA/CPU provider state machine |

**Rules that hold everywhere here**: no silent excepts (annotated or logged (AST-enforced), no wall-clock in deadline math (monotonic) AST-enforced), fail-closed defaults, all blocking I/O off the event loop. See `rule book/disciplines/developer/02-coding-standards.md`.
