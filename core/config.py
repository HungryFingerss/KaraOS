import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

# ── Paths ─────────────────────────────────────────────────────────────────────
FACES_DIR        = ROOT / "faces"
PIPER_MODELS_DIR = ROOT / "models" / "piper"
DB_PATH          = ROOT / "faces" / "faces.db"
FAISS_INDEX_PATH = ROOT / "faces" / "faiss.index"
FACES_DIR.mkdir(exist_ok=True)

# ── Camera ────────────────────────────────────────────────────────────────────
CAMERA_INDEX     = 0
FRAME_WIDTH      = 1280
FRAME_HEIGHT     = 720

# ── Face recognition ──────────────────────────────────────────────────────────
RECOGNITION_THRESHOLD       = 0.28   # cosine similarity — above = known person (raised from 0.18; AdaFace IR101 stable EER region is 0.28–0.45)
DETECTION_CONFIDENCE        = 0.50   # RetinaFace detection confidence threshold (lowered from 0.7 — upward-angle cameras give lower det_scores)
EMBEDDING_DIM               = 512    # AdaFace IR101

# ── Voice recognition ──────────────────────────────────────────────────────────
# Model: SpeechBrain ECAPA-TDNN (speechbrain/spkrec-ecapa-voxceleb)
# 0.80% EER on VoxCeleb1-O; cosine similarity on L2-normalized 192-dim embeddings.
VOICE_RECOGNITION_THRESHOLD    = 0.25  # cosine similarity EER operating point
VOICE_SPEAKER_SWITCH_THRESHOLD = 0.50  # min confidence to auto-open session for a DIFFERENT enrolled speaker
                                       # Intentionally higher than VOICE_RECOGNITION_THRESHOLD (0.25):
                                       # identifying a voice ≠ switching sessions; switching needs stronger evidence.
MAX_VOICE_EMBEDDINGS        = 20     # max voice embeddings per person (covers mic distances/conditions)
VOICE_EMBEDDING_DIM         = 192    # ECAPA-TDNN output dimension
VOICE_DIVERSITY_THRESHOLD   = 0.85   # cosine sim above this = same condition already stored → skip
N_INITIAL_VOICE             = 5      # first N voice embeddings bypass diversity (enrollment baseline)

# ── Within-utterance speaker diarization ─────────────────────────────────────
DIARIZE_WINDOW_SECS   = 0.50   # ECAPA-TDNN window size per embedding (seconds)
DIARIZE_HOP_SECS      = 0.25   # hop between windows (seconds)
DIARIZE_CHANGE_THRESH = 0.70   # cosine similarity below this = speaker boundary
DIARIZE_MIN_SECS      = 2.00   # minimum utterance length to attempt diarization

# VISION_ROADMAP Phase 2 (Session 88) — pyannote-backed diarization.
# The legacy ECAPA-valley backend (_diarize_ecapa_valley) handles 2-speaker
# binary splits via cosine-valley detection. Pyannote 3.1 handles variable
# speaker counts via segmentation + clustering, with better DER on 3+
# speakers and overlap cases. Dispatch happens in ``diarize()`` at module
# scope in core/voice.py.
DIARIZATION_BACKEND           = "pyannote"   # "pyannote" | "ecapa_valley"
DIARIZATION_FALLBACK_ON_ERROR = True          # degrade to ecapa_valley if pyannote errors
DIARIZE_MIN_SEGMENT_SECS      = 0.5           # drop pyannote segments shorter than this — ECAPA embedding is too noisy
DIARIZE_MIN_EMBED_SECS        = 1.0           # segments shorter than this get speaker_id=None (kept in output, not attributed)

# ── Self-update gallery ───────────────────────────────────────────────────────
SELF_UPDATE_THRESHOLD       = 0.45   # min confidence for gallery write — must be > RECOGNITION_THRESHOLD (0.28)
                                       # 0.45 is clearly-confident territory; 0.32 was only 0.04 above recognition floor
                                       # and allowed marginal matches (e.g. lookalike uncle) to corrupt the gallery.
SELF_UPDATE_COOLDOWN        = 30     # seconds between update attempts per person
SELF_UPDATE_CENTROID_MIN    = 0.55   # reject recognition_update writes whose cosine to the existing
                                       # gallery centroid is below this — catches outliers at write time.
MAX_EMBEDDINGS              = 50     # max face embeddings per person (covers all angles/conditions)
FACE_DIVERSITY_THRESHOLD    = 0.92   # cosine sim above this = same angle already stored → skip

# face_quality_score() returns a continuous grade in [0.05, 1.0] — callers choose their gate
FACE_QUALITY_PRESENCE       = 0.05   # face is detectably present (anything above floor)
FACE_QUALITY_RECOGNITION    = 0.20   # recognition viable (allows motion blur / partial occlusion)
FACE_QUALITY_ENROLLMENT     = 0.50   # clean enough to store as gallery embedding
FACE_QUALITY_SELF_UPDATE    = 0.70   # high-quality crop required for gallery self-update
N_INITIAL_FACE              = 5      # first N face embeddings bypass diversity (enrollment baseline)

# ── Session integrity ─────────────────────────────────────────────────────────
# Frozenset of valid person_type values. Used at every write site as an assert
# target so literal-string bugs like `person_type = "known"` on a best_friend
# session fail fast with AssertionError instead of silent downgrade.
VALID_PERSON_TYPES     = frozenset({"stranger", "known", "best_friend", "disputed"})

# ── Voice routing thresholds (used by _resolve_actual_speaker in pipeline.py) ─
# Kept distinct from VOICE_ACCUM_* — routing and accumulation tune independently.
# The 0.45 numerically matches VOICE_ACCUM_FACE_WITNESS_MIN_CONF by coincidence,
# not by design — don't alias them.
# Voice routing — switch thresholds by profile maturity.
# Used by _effective_switch_threshold in core/reconciler.py.
# Mature profiles tolerate a lower switch bar; thin profiles need higher
# confidence to switch into them (avoids false-positive switches when a
# new speaker's voice happens to score ~0.40 against an under-trained mean).
# Promoted from inline literals 2026-04-29 (S176/Phase 3) — calibration-preserving.
VOICE_SWITCH_THRESHOLD_MATURE = 0.40   # voice_n >= N_INITIAL_VOICE samples
VOICE_SWITCH_THRESHOLD_THIN   = 0.55   # voice_n < N_INITIAL_VOICE — needs higher confidence

# Phase 4 cutover flag — flip True to make core/reconciler.reconcile() the
# primary routing source in pipeline.run(). Rollback: set False.
# Set True on 2026-04-29 after canary #3 (10/10 sentinel coverage, 0 divergences).
ROUTING_USE_RECONCILER = True

VOICE_ROUTING_MIDRANGE_SWITCH_MIN   = 0.30   # Priority 2: different-person switch floor
VOICE_ROUTING_FACE_ASSIST_MIN       = 0.42   # Priority 2: min v_score for face-assisted
                                              # confident switch. Below this, even with the
                                              # claimed face in frame, route as ambiguous.
                                              # Bug O (2026-04-20 live run): a phone caller's
                                              # audio scored 0.314 against Jagan with Jagan's
                                              # face visible → mis-attributed to Jagan's pid.
                                              # The visible face doesn't mean that face is the
                                              # speaker in multi-person / phone-audio scenarios.
VOICE_ROUTING_SELF_MATCH_FLOOR      = 0.30   # Priority 3: absolute self-match floor
VOICE_ROUTING_SELF_MATCH_OFFSCREEN  = 0.45   # Priority 3: higher floor when holder offscreen
VOICE_ROUTING_MIN_UTTERANCE_SECS    = 1.0    # below this, short-utterance MISMATCH gates
                                              # (Tier 1/2) still apply. Bug F (2026-04-20 live
                                              # run): short social closers ("Thank you", "Yes",
                                              # "Hey") at 0.02-0.25 misfired as new_stranger,
                                              # opening phantom sessions that cascaded into
                                              # visitor_log → BriefingAgent fabrication (Bug N).
VOICE_ROUTING_NOISE_FLOOR_SECS      = 0.30   # below this, ECAPA is pure noise — hold current
                                              # as last resort regardless of score. 0.3s is the
                                              # absolute minimum embedding window. Above 0.3s the
                                              # full gallery cascade applies (Phase 4 cutover,
                                              # 2026-04-29). Replaces the 1.0s hold-current floor
                                              # for _p0_pure_noise_hold_current.

# VISION_ROADMAP P3.23 (Session 92) — multi-speaker-aware short-utterance floor.
# 2026-04-22 P3.21 live-canary failure showed the single-speaker floor (above)
# mis-attributing Lexi's "Hi Kara" (0.67s, voice=0.08 vs Jagan) to Jagan's
# active session. Real conversations start short; requiring 1.5s utterances
# before accepting a speaker change is broken by design. This policy keeps
# the 1.0s floor AS the default but adds a "voice clearly not cur_pid"
# escape: when audio is at least MIN_AUDIO_FOR_SCORE (0.5s — enough for a
# noisy-but-directional ECAPA embedding) and the voice ID score against the
# whole gallery is below SHORT_UTT_FLOOR (0.20 — "obviously not anyone we
# know"), drop the turn entirely rather than mis-attribute to cur_pid. The
# user naturally speaks a longer sentence next which reliably opens a
# stranger session via the normal path. Two-turn cost for correctness.
VOICE_ROUTING_SHORT_UTT_MISMATCH_ENABLED = True   # toggle the mismatch-drop policy
VOICE_ROUTING_SHORT_UTT_FLOOR            = 0.20   # v_score below this = "obviously not cur_pid"
VOICE_ROUTING_MIN_AUDIO_FOR_SCORE        = 0.5    # under this, ECAPA too noisy even for
                                                   # directional judgement; fall back to current

# Session 93 refinement — the single-threshold P3.23 shipped in S92 caught
# HARD mismatches (< 0.20) but left the AMBIGUOUS zone (0.20-0.40) silently
# attributing to cur_pid. In a multi-session room that produced a real-world
# cascade: 2026-04-22 live run had Lexi's 0.64s "You know, I love cheese"
# score 0.38 vs Jagan's mature profile (normal Jagan scores 0.6-0.8) → routed
# to Jagan → brain extracted Jagan.likes_cheese='true' → next turn retrieved
# it → extracted Lexi.likes_cheese='true' (hallucinated — Lexi never said
# it) → extracted Lexi.has_influence_on_jagan='true' (further hallucination).
# Memory pollution compounds fast.
#
# Tiered policy: 0.20-0.40 scores are ambiguous. Drop ONLY when the room has
# multiple active sessions (i.e. there IS plausibly another speaker present).
# Solo case keeps the old "trust" behavior to avoid false-negative drops
# when a single person's voice just dips below 0.40 due to recording quality
# or brief phonation. No regression on solo use.
VOICE_ROUTING_SHORT_UTT_AMBIGUOUS         = 0.40   # 0.20 <= v_score < this + multi-session = drop

# ── Voice accumulation policy ─────────────────────────────────────────────────
# Three-path policy (see pipeline._voice_accum_allowed):
#   A) recent face witness  — face match was confident, live, and fresh
#   B) mature voice profile — profile has >= MATURE_SAMPLE_COUNT samples and self-matches
#   C) bootstrap credits    — session opened via an engagement gate (face greeting,
#                             system-name gate pass) gets N free accumulations so the
#                             profile has something to self-match against on turn 1.
# All magic thresholds live here — no inline `count < 3` or `> 0.45` in decision code.
N_INITIAL_VOICE_BOOTSTRAP            = 20      # free accumulations granted at engagement
                                                # Session 67 (2026-04-21): raised 6 → 20 to match
                                                # MAX_VOICE_EMBEDDINGS ceiling. Voice and vision
                                                # are independent sensor channels — a voice-only
                                                # speaker (no face ever visible) must be able to
                                                # fully populate their voice profile in a single
                                                # engagement-gated session without depending on
                                                # vision for Path A witnessing. Diversity gate
                                                # (VOICE_DIVERSITY_THRESHOLD=0.85) still filters
                                                # near-identical samples, so 20 credits = 20
                                                # opportunities, not 20 forced writes.
                                                # Invariant (still holds): BOOTSTRAP > MATURE (5).
VOICE_ACCUM_FACE_WITNESS_MIN_CONF    = 0.45    # min face-match cosine to count as witness
                                                # (symmetry with SELF_UPDATE_THRESHOLD — one knob)
VOICE_ACCUM_FACE_WITNESS_MAX_AGE_SEC = 10.0    # face must have been seen within this window
VOICE_ACCUM_VOICE_SELF_MATCH_MIN     = 0.45    # voice self-match floor for path B
VOICE_ACCUM_MATURE_SAMPLE_COUNT      = 5       # sample count at which profile is "mature"
                                                # (matches N_INITIAL_VOICE — one knob)

# Session 94 Fix #5 — bootstrap credit replenishment.
# 2026-04-22 live canary showed a stranger's voice profile frozen at 2
# samples across multiple session re-opens. Root cause: N_INITIAL_VOICE_BOOTSTRAP
# credits only seed at first engagement-gated open; subsequent re-opens via
# voice match don't re-grant, so after credits are burned the profile stops
# growing. Without face witness (ElevenLabs / offscreen speakers) Path A is
# blocked; Path B requires MATURE_SAMPLE_COUNT which the stranger never reaches.
#
# Fix: while the engagement gate remains valid (stranger said the system name
# and ``waiting_for_name=False``) AND the profile hasn't reached maturity,
# top up bootstrap credits 1-per-turn at the start of ``_accumulate_voice``,
# capped at MAX_BOOTSTRAP_CREDITS. Each accumulation burns 1 credit (existing
# decrement stays), but the cap prevents unbounded indefinite replenishment
# and the maturity check stops the top-up once Path B is reachable.
VOICE_BOOTSTRAP_REPLENISH_ENABLED    = True    # toggle the per-turn top-up
VOICE_BOOTSTRAP_DEBUG                = False   # F2 diagnostic — gating [Voice-Debug] trace lines
VOICE_MAX_BOOTSTRAP_CREDITS          = 10      # ceiling for per-turn replenishment
                                                # (distinct from N_INITIAL_VOICE_BOOTSTRAP=20:
                                                # the initial grant is generous, the
                                                # replenishment cap is stricter — we want
                                                # profiles to grow naturally, not balloon)
IDENTITY_EVIDENCE_BLOCK_ENABLED      = True    # render <<<IDENTITY EVIDENCE>>> in brain prompt

# ── Bug N (2026-04-20 live run) — confabulation prevention ────────────────────
# The 2026-04-20 run surfaced a narrative-layer bug: when asked about a
# thinly-recorded person or event, the LLM pattern-completes from adjacent
# memories and produces plausible-sounding false memories. The fix is four
# layers of defense; these three constants govern the per-layer thresholds.
BRIEFING_VISITOR_MIN_TURNS          = 2       # minimum conversation-log user turns for a
                                               # visitor to appear in BriefingAgent output.
                                               # A phantom / gate-blocked visitor with
                                               # turn_count 0 shouldn't produce "we had a
                                               # nice chat" phrasing — the briefing template
                                               # asserts real exchange, so anchor it to one.
MEMORY_SPARSE_THRESHOLD             = 2       # below this result count, search_memory
                                               # flags the response as sparse so the LLM
                                               # knows not to fabricate details from
                                               # adjacent memories.
HONESTY_POLICY_BLOCK_ENABLED        = True    # render the <<<HONESTY POLICY>>> block in
                                               # the system prompt — tells the LLM to say
                                               # "I don't have details" when memory is
                                               # sparse rather than inventing content.

# ── Bug L (2026-04-20 live run) — PromptPref dedup + blacklist ────────────────
# The 2026-04-20 run showed PromptPrefAgent producing duplicate-ish and
# contradictory "activated" prefs across sessions. Dedup and blacklist
# knobs live here so tuning is a single-knob operation.
PREF_DEDUP_THRESHOLD                = 0.85    # cosine similarity above which a new pref
                                               # description is treated as a duplicate of
                                               # an existing one; we bump sessions_seen on
                                               # the existing row instead of inserting a
                                               # near-duplicate ("Keep it brief" activated
                                               # 4 separate times in the 2026-04-20 run).
PREF_BLACKLIST_PATTERNS             = (
    # Mistake-recovery patterns that shouldn't become prefs — the agent
    # was inferring these from the LLM apologising for its own confusion
    # (e.g. Bug N cascade, stranger misattribution) and learning the
    # apology as a user preference. Reject at the activation gate.
    r"avoid\s+apolog",
    r"don[\'`’]t\s+apolog",
    r"stop\s+apologizing",
    r"avoid\s+(?:correcting|clarifying|rephrasing|explaining)\s+(?:mistakes|internal)",
    r"stop\s+(?:correcting|clarifying|rephrasing|explaining)\s+(?:mistakes|internal)",
    r"avoid\s+explain\w+\s+internal",
    r"no\s+more\s+mistakes",
    r"deflect",    # "deflects questions about X" is usually inference from silence
)

# ── Tool privilege policy ─────────────────────────────────────────────────────
# Who (by person_type) can invoke each tool. The pipeline reads this at tool-
# call time; the brain sees a human-readable <<<TOOL ACCESS>>> summary in the
# system prompt so it knows upfront which tools are callable and doesn't burn
# turns on silently-blocked calls. Privilege change = edit this table, no code
# change in pipeline or brain prompt logic.
#
# SAFETY MODEL: fail-closed. Tools NOT in this table are BLOCKED, not
# unrestricted. A startup assertion (below) requires every tool in
# brain.TOOLS to have an entry here — missing = assertion error at launch.
TOOL_PRIVILEGES: dict[str, frozenset[str]] = {
    "shutdown":                 frozenset({"best_friend"}),
    "update_system_name":       frozenset({"best_friend"}),
    "update_person_name":       frozenset({"stranger", "known", "best_friend", "disputed"}),
    "report_identity_mismatch": frozenset({"stranger", "known", "best_friend", "disputed"}),
    "search_web":               frozenset({"stranger", "known", "best_friend"}),
    "search_memory":            frozenset({"known", "best_friend"}),
    # Phase 3B.5 — room-level search: same access shape as search_memory
    # (strangers are gated pre-engagement and rely on direct recall).
    "search_room_memory":       frozenset({"known", "best_friend"}),
}

# ── Greeting ──────────────────────────────────────────────────────────────────
GREET_COOLDOWN         = 300    # seconds before re-greeting same person (5 min)
FACE_LOSS_GRACE        = 10     # seconds of no face before ending a face-started session
VOICE_SESSION_TIMEOUT  = 30     # seconds of session-holder silence before ending a voice-started session

# ── Audio ─────────────────────────────────────────────────────────────────────
# VAD_SWITCH: True  = Silero VAD (accurate, requires GPU — use on Jetson/PCB)
#             False = RMS energy-based silence detection (no model, works on laptop)
VAD_SWITCH             = False
VAD_THRESHOLD          = 0.5       # Silero confidence threshold (VAD_SWITCH=True only)
RMS_THRESHOLD          = 0.01      # energy threshold for speech detection (VAD_SWITCH=False)
SILENCE_DURATION       = 1.5       # seconds of silence = hard end-of-turn fallback (raised from 1.2)
FILLER_ENABLED         = False     # disabled — predictable fillers on every turn feel robotic
MIC_SAMPLE_RATE        = 16000

# Smart-Turn: neural end-of-turn detection (pipecat-ai/smart-turn)
# Model: models/smart_turn.onnx (~8MB ONNX, BSD-2 license)
# Download: https://github.com/pipecat-ai/smart-turn/releases
SMART_TURN_MODEL_PATH  = ROOT / "models" / "smart_turn.onnx"
SMART_TURN_SILENCE     = 0.5      # seconds of silence → trigger Smart-Turn check
SMART_TURN_THRESHOLD   = 0.80     # probability above this = turn is complete (raised from 0.55 — was cutting off mid-thought)
SMART_TURN_ADDENDUM    = 0.5      # grace window after Smart-Turn fires at moderate confidence;
                                   # high-confidence path (p>0.95) uses 0.20s adaptive (audio.py)
LIP_MAX_EXTENSION      = 2.0      # max seconds lip tracking can extend beyond silence
ADDENDUM_ONSET_WINDOW  = 0.10     # seconds: re-listen after turn ends; exit if no speech onset (was 0.15)

# Languages this user speaks — Whisper language detection is restricted to this set.
# This prevents Tamil/Hindi false positives when the user speaks Telugu.
# Whisper auto-detects from 100 languages; we force it to only pick from these candidates.
# Change for different users: ["hi", "en"] for Hindi speaker, ["te", "hi", "en"] for both.
SPEAKER_LANGUAGES      = ["en"]

# ── LLM ───────────────────────────────────────────────────────────────────────
OLLAMA_MODEL           = "qwen2.5:7b"
OLLAMA_URL             = "http://localhost:11434"

# ── Provider credentials ──────────────────────────────────────────────────────
# P0.S3 §1.P1 — strip whitespace at module load (single source of truth).
# Empty default is preserved; "".strip() == "". Consumers (CHAT_API_KEY etc.)
# see the stripped value, so an httpx Authorization: Bearer header is never
# whitespace-padded. env_validation.py reads BOTH _RAW (for the diagnostic
# WARNING) and the stripped value (for the empty-check). Strip is idempotent:
# if RAW is already clean, stripped == raw, no WARNING fires at boot.
_TOGETHER_API_KEY_RAW = os.getenv("TOGETHER_API_KEY", "")
TOGETHER_API_KEY      = _TOGETHER_API_KEY_RAW.strip()
TOGETHER_BASE_URL     = "https://api.together.xyz/v1"
# P0.S3 §1.P4 — HF_TOKEN centralized at module load for consistency with the
# TOGETHER_API_KEY pattern. env_validation.py reads config.HF_TOKEN (not
# os.getenv) so the P0.S6 test_env_var_reads_centralized invariant stays
# green without adding a new allowlist entry. core/voice.py:302 still reads
# os.getenv("HF_TOKEN") at lazy-load time (per the existing P0.S6 allowlist
# entry); migrating voice.py to config.HF_TOKEN is S3.X scope, not P0.S3.
# Same value read twice during process lifetime is harmless (env vars are
# immutable during a Python process).
HF_TOKEN          = os.getenv("HF_TOKEN", "")
GROQ_API_KEY      = os.getenv("GROQ_API_KEY", "")
GROQ_BASE_URL     = "https://api.groq.com/openai/v1"

# ── Role-based model config ───────────────────────────────────────────────────
# Each agent role owns its model + provider. To move a role to a different
# provider (e.g. chat → Groq), change only that role's 3 lines — nothing
# else in the codebase needs to change.

# Conversation (brain.py) — streaming, function calling, real-time
# Together Turbo: speculative decoding, ~200-500ms TTFT, no rate limits
# Switch to GROQ_BASE_URL + GROQ_API_KEY when Dev tier is available for ~100ms TTFT
CHAT_MODEL    = "meta-llama/Llama-3.3-70B-Instruct-Turbo"
CHAT_BASE_URL = TOGETHER_BASE_URL
CHAT_API_KEY  = TOGETHER_API_KEY

# Background extraction agents (brain_agent.py) — async, JSON mode, not latency-critical
EXTRACT_MODEL    = "meta-llama/Llama-3.3-70B-Instruct-Turbo"
EXTRACT_BASE_URL = TOGETHER_BASE_URL
EXTRACT_API_KEY  = TOGETHER_API_KEY

# Semantic embeddings (brain_agent.py) — 1024-dim multilingual
EMBED_MODEL       = "intfloat/multilingual-e5-large-instruct"
EMBED_BASE_URL    = TOGETHER_BASE_URL
EMBED_API_KEY     = TOGETHER_API_KEY
EMBED_MAX_RETRIES = 2   # extra attempts after first failure (transient errors only)
EXTRACT_MAX_RETRIES = 2 # same pattern for ExtractionAgent Together.ai calls —
                        # network-bound + idempotent, retry once on ReadTimeout / ConnectTimeout
                        # with exponential backoff. 4xx errors propagate (not transient).

# Vision / image description (brain.py) — disabled until base is solid
# VISION_YOLO_ENABLED and describe_frame are both off; model is ready for when we enable.
VISION_MODEL    = "Qwen/Qwen3-VL-8B-Instruct"
VISION_BASE_URL = TOGETHER_BASE_URL
VISION_API_KEY  = TOGETHER_API_KEY

# ── Cloud health ───────────────────────────────────────────────────────────────
CLOUD_OFFLINE_TIMEOUT  = 120   # seconds of consecutive failure before switching to Ollama
CLOUD_RETRY_INTERVAL   = 30    # seconds between Together.ai reconnect attempts in background

# ── Stranger interaction ───────────────────────────────────────────────────────
STRANGER_REQUIRE_SYSTEM_NAME = True   # strangers must say system name before engaging

# Tavily — web search for ONLINE-classified queries
TAVILY_API_KEY         = os.getenv("TAVILY_API_KEY", "")
TAVILY_SEARCH_DEPTH    = "advanced"  # "basic" (1 credit) or "advanced" (5 — richer results)
TAVILY_MAX_RESULTS     = 5           # number of results fetched (was hardcoded 3)
SEARCH_CACHE_TTL_SECS  = 300         # seconds to reuse cached result for identical query
SEARCH_QUERY_MIN_CHARS = 3           # client-side arg validation floor — reject empty /
                                      # whitespace / nonsense-short queries before hitting
                                      # Tavily. Bug R (2026-04-21 live run): LLM called
                                      # search_web('') on a self-awareness question and
                                      # Tavily returned 400. Below this threshold we return
                                      # a structured error-hint instead so the LLM knows
                                      # to answer from training knowledge.

# ── Bug S (2026-04-21 live run) — user-text gates for rename tools ────────────
# The LLM pattern-matched "Do you know Detroit?" → update_system_name('Kara')
# without the user actually assigning a name (Kara = Detroit: Become Human
# character). Symmetric to the shutdown handler's user-text guard: reject a
# tool call that the user's CURRENT utterance doesn't support. "Every
# side-effect tool must have a server-side user-text gate" is the architectural
# invariant the shutdown handler already embodied; these extend it to rename.
SYSTEM_NAME_ASSIGN_PATTERNS: tuple[str, ...] = (
    # Bug G1 (2026-04-22 live run): upgraded from `\w` to `(\w+)` capture
    # group. The old patterns only verified that an assignment PHRASE was
    # present AND that the name appeared somewhere in the turn (OR-logic).
    # "Do you know the game called Detroit?" satisfied the presence check
    # and renamed the system to "Detroit". Capture-group verification forces
    # the assignment phrase itself to contain the name — `game called Detroit`
    # doesn't match `call\s+you\s+(\w+)` because "you" isn't there.
    r"\bcall\s+you\s+(\w+)",
    r"\byour\s+name\s+(?:is|will\s+be|should\s+be)\s+(\w+)",
    r"\bname\s+you\s+(\w+)",
    r"\bi(?:'ll|\s+will|\s+want\s+to)\s+(?:call|name)\s+you\s+(\w+)",
    r"\bfrom\s+now\s+on\s+you(?:'re|\s+are)\s+(\w+)",
    r"\blet(?:'s|\s+us)\s+(?:call|name)\s+you\s+(\w+)",
    # "I decided on Kara" — capture the noun after the commit verb.
    r"\bi\s+(?:decided|choose|chose|pick(?:ed)?)\s+(?:on\s+)?(\w+)",
)
PERSON_NAME_ASSIGN_PATTERNS: tuple[str, ...] = (
    # Bug G2 (2026-04-22 live run): capture-group upgrade — same rationale.
    r"\bmy\s+name\s+(?:is|was|will\s+be)\s+(\w+)",
    r"\bcall\s+me\s+(\w+)",
    r"\bi(?:'m|\s+am)\s+(\w+)",                                 # "I'm Sarah"
    r"\bthis\s+is\s+(\w+)\s+(?:speaking|here)\b",
    r"\bpeople\s+call\s+me\s+(\w+)",
    r"\bit(?:'s|\s+is)\s+me,?\s+(\w+)",                         # "it's me, Sarah"
)
# Bug G3 (2026-04-22 live run) — identity-denial patterns for
# report_identity_mismatch. Unlike rename patterns, these don't need to
# capture a specific name — the gate just needs a clear denial signal.
# Jagan's legit question "who are you talking to?" triggered dispute in the
# live run precisely because there was no gate on this tool.
IDENTITY_DENIAL_PATTERNS: tuple[str, ...] = (
    r"\bi(?:'m|\s+am)\s+not\s+\w",                              # "I'm not Jagan"
    r"\bthat(?:'s|\s+is)\s+not\s+me\b",
    r"\byou(?:'ve|\s+have)\s+got\s+the\s+wrong\s+person\b",
    r"\byou(?:'re|\s+are)\s+confusing\s+me\s+(?:with|for)\s+\w",
    r"\bi(?:'m|\s+am)\s+not\s+(?:the\s+person\s+you\s+think|who\s+you\s+think)\b",
    r"\bstop\s+calling\s+me\s+\w",
)

# ── Bug D1 (2026-04-22 live run) — dispute auto-clear thresholds ──────────────
# Disputed sessions currently only clear via DISPUTE_MAX_DURATION=180s timeout.
# In a 5-minute demo, 180s = 60% of the demo broken. Add signal-based auto-
# clear when the speaker's voice match has been strong for 3 consecutive turns
# OR their face is in frame with a confident face_match_conf.
# Asymmetric blast radius: a wrongly-persistent dispute wastes time; a wrongly-
# cleared dispute leaks sensor-pid facts. Pick the safer (higher) threshold.
DISPUTE_AUTO_CLEAR_VOICE_MIN         = 0.70    # per-turn voice_match_conf floor when
                                                # corroborated by face (face in frame
                                                # with face_match_conf ≥ this too).
DISPUTE_AUTO_CLEAR_VOICE_SOLO_MIN    = 0.85    # Session 73 post-review Medium C2:
                                                # higher threshold for voice-only
                                                # dispute clearance (no face corroboration).
                                                # Voice auto-clear trusts the same sensor
                                                # that triggered the dispute; without face
                                                # witness, raise the bar so a wrongly-
                                                # cleared dispute requires essentially
                                                # a confirmed-voice-auth level of match.
DISPUTE_AUTO_CLEAR_CONSECUTIVE_TURNS = 3      # how many consecutive turns must pass

# ── VISION_ROADMAP Phase 1 — structured intent output on primary 70B ─────────
# Replaces the 5+ regex pattern lists (SYSTEM_NAME_ASSIGN_PATTERNS,
# PERSON_NAME_ASSIGN_PATTERNS, IDENTITY_DENIAL_PATTERNS, shutdown literals,
# SEARCH_WEB_LIVE_DATA/BLOCK_PATTERNS) with structured JSON emitted by the
# same 70B chat call we already make. Every regex patch since Session 71
# traded one bug for another (Detroit false-accept; Kara false-reject);
# structured output moves semantic intent classification to the model while
# a small server-side validator enforces consistency: intent ↔ tool_calls,
# extracted_value ↔ user_text, confidence ≥ threshold.
#
# Rollout: P1.1–P1.6 build the infrastructure without flipping the gates;
# P1.7–P1.12 wire each tool behind INTENT_FALLBACK_TO_REGEX=True so the
# existing regex gate remains the source of truth until the shadow-mode
# divergence data confirms the structured path is reliable.

# Exhaustive label set. Every turn the brain classifies lands in exactly one.
# "unclear" is the safety-valve label — preferred over a guessed confident
# classification when the turn is genuinely ambiguous.
INTENT_LABELS: frozenset = frozenset({
    "assign_system_name",
    "assign_own_name",
    "deny_identity",
    "confirm_identity",
    "live_data_query",
    "general_knowledge_query",
    "opinion_query",
    "personal_statement",
    "request_shutdown",
    "question_about_shutdown",
    "casual_conversation",
    "unclear",
    # Phase 3B.2 — user speaking TO another person in the room (not to AI).
    # Classifier extracts the addressee's name into extracted_value. Pipeline
    # skips the LLM response when the name ≠ system_name — brain stays silent.
    "direct_address_to_person",
    # Spec-1 follow-up Item 7 (2026-04-28) — user correcting the AI's previous
    # turn ("No Kara, I was talking to my friend"). The graph classifier
    # detects its own corrections via this label, then the pipeline applies
    # outcome supervision (decrement scenarios that voted for the wrong
    # label on turn N-1, optionally extract correction target via regex).
    # Linchpin of LLM-free online learning — see Spec 2.
    "correction_to_previous_response",
    # NOTE: `topical_participant_response` was added in Session 119 (Path 1)
    # then rolled back; the prompt no longer emits it and no production gate
    # routes on it. Removed from INTENT_LABELS in the Spec 1 follow-up
    # session (2026-04-28) since the orphan was confusing bootstrap
    # distribution counts. The bridge `output_mapper.py` SPEAK branch for it
    # is harmless residue — it never fires once the label is gone.
})

# Tool → (required turn_intent, tool-arg key to cross-check against
# extracted_value). arg_key is None when the tool doesn't need value
# verification (denial / shutdown — match on intent alone is sufficient).
TOOL_INTENT_MAP: dict = {
    "update_system_name":       ("assign_system_name", "name"),
    "update_person_name":       ("assign_own_name",    "name"),
    "report_identity_mismatch": ("deny_identity",      None),
    "shutdown":                 ("request_shutdown",   None),
    # Phase 1 classifier scope is MUTATION tools only (rename / deny /
    # shutdown). search_web was intentionally removed after Session 79's
    # architectural audit: search_web is consumed inline inside
    # core.brain._ask_stream (its tool_call never reaches the classifier
    # gate in conversation_turn), AND its extracted_value ("Chennai
    # temperature today") is a semantic transformation of user_text rather
    # than a literal substring — the grounding check doesn't cleanly apply.
    # search_web retains its dedicated server-side gate (_should_search_web
    # + SEARCH_WEB_LIVE_DATA_PATTERNS / SEARCH_WEB_BLOCK_PATTERNS from
    # Session 71 Bug T), which is working (2026-04-22 session line 438
    # confirmed rejection of 'highest temperature in India today' on a
    # no-live-data-marker turn). Deferred to Phase 1.5 for re-evaluation
    # after the mutation classifier stabilizes in production for 2-3 weeks.
    # See VISION_ROADMAP.md section 1.5 appendix for the deferral rationale.
}

# ── P0.S6 D1 — Intent-gate-optional companion set ──────────────────────────────
#
# Companion to TOOL_INTENT_MAP. Tools listed here are INTENTIONALLY exempt
# from the classifier-gate (`_intent_allows`) verification — not because they
# escaped the audit, but because their architectural shape doesn't fit the
# mutation-tool gate model. The startup assertion at pipeline.run() entry
# enforces that every tool in brain.TOOLS appears in EITHER TOOL_INTENT_MAP
# OR this set; future maintainers adding a new tool MUST classify it here
# explicitly (no silent default).
#
# Naming choice (P0.S6 Plan v1 §1.D1 + §3.1 mitigation): plural-subject-noun
# `INTENT_OPTIONAL_TOOLS` signals "set of tool names," NOT a map shape.
# Prevents future readers from adding (intent, arg_key) tuples by analogy
# to TOOL_INTENT_MAP.
#
# Per-entry rationale:
#   - `search_web` — consumed inline inside `core.brain._ask_stream`; the
#     tool_call NEVER bubbles to `conversation_turn`'s classifier gate
#     (Session 79 audit). Deferred to Phase 1.5 per the VISION_ROADMAP
#     appendix; until then, server-side `_should_search_web` is the
#     authoritative gate (NOT the classifier).
#   - `search_memory` — read-only query path with no privilege escalation.
#     The classifier gate would add latency without security benefit; the
#     result rendering (per-person knowledge lookup) is the actual value
#     surface, not the dispatch decision.
#   - `search_room_memory` — same architectural shape as `search_memory`
#     (Phase 3B.5 sibling). Gate would be cosmetic; deferred-to-callback
#     consumption (`_make_room_search_fn`) parallels search_memory's path.
INTENT_OPTIONAL_TOOLS: frozenset = frozenset({
    "search_web",
    "search_memory",
    "search_room_memory",
})


# ── P0.S6 D4 — Inline-dispatched tools companion set ───────────────────────────
#
# Companion to `_TOOL_HANDLERS` (pipeline.py:4191). Tools listed here are
# consumed via INLINE ask_stream callbacks (`_make_memory_search_fn` /
# `_make_room_search_fn`), NOT through the `_execute_tool` dispatch table.
# The startup assertion at pipeline.run() entry enforces that every tool in
# brain.TOOLS appears in EITHER `_TOOL_HANDLERS` OR this set; future
# maintainers adding a new tool MUST classify it here explicitly.
#
# Note: `search_memory` is INTENTIONALLY NOT in this set despite having a
# callback path. It ALSO has a `_handle_search_memory` entry in
# `_TOOL_HANDLERS` (legacy dual-path from Session 56-58 timing). Both paths
# are live; the registry assertion holds via the _TOOL_HANDLERS membership.
# Future cleanup may collapse to one path, at which point search_memory
# moves here.
INLINE_DISPATCHED_TOOLS: frozenset = frozenset({
    "search_web",
    "search_room_memory",
})


INTENT_CONFIDENCE_MIN       = 0.75   # general confidence floor — below this, gate rejects
INTENT_SHUTDOWN_CONF_MIN    = 0.80   # higher floor for shutdown (bigger blast radius)
INTENT_MAX_USER_TEXT_CHARS  = 500    # truncate very long user_text before grounding
                                      # check; prevents pathological prompts from
                                      # wedging the substring validator.

# Shadow-mode flag: when True, structured intent runs in parallel with the
# existing regex gates but the regex gate remains authoritative. Divergences
# are logged. Flipped to False after P1.17 acceptance criteria are met
# (golden-set precision ≥ 0.95, ECE ≤ 0.05, ≥1500 real classifications with
# ≤5% divergence). Safety: default is True so the refactor can't silently
# replace proven gates before the data is in.
INTENT_FALLBACK_TO_REGEX    = True

# VISION_ROADMAP Phase 1.3 — shadow classifier for gated-tool turns.
# When the main 70B stream proposes a gated tool (update_system_name,
# update_person_name, report_identity_mismatch, search_web, shutdown), we
# run a SEPARATE Together.ai call with response_format=json_object to
# classify the turn's intent + extract the grounded value. This sidecar is
# what P1.7+ will feed into the gate validator. Lazy fire: only ~5% of
# turns (the ones that propose gated tools). Non-gated turns pay nothing.
INTENT_SHADOW_MODE_ENABLED     = True
INTENT_CLASSIFIER_TIMEOUT_SECS = 10.0  # Session 79: bumped 8.0 → 10.0 after
                                        # 2026-04-22 live session showed 1/7
                                        # (14%) timeout rate at 8s. 10s covers
                                        # the observed cold-start variance. No
                                        # retry yet — ship this first + measure
                                        # before compounding complexity.
                                        # Tail latency on
                                        # observed p99 without blocking the
                                        # main tool-dispatch path excessively.
INTENT_CLASSIFIER_MAX_TOKENS   = 500   # Session 78 Item 3: bumped 300 → 500
                                         # after observation logs showed the
                                         # reasoning field truncating mid-word
                                         # ('so the int...'). The JSON envelope
                                         # + 4 required fields + room for a
                                         # full sentence reasoning comfortably
                                         # fits in 500. Negligible cost vs. the
                                         # observability gain.

# P1.3 reviewer refinement #2 — hedged naming content.
# Tells the 70B to phrase rename / shutdown acknowledgments as questions
# ("I heard Kara — is that right?") rather than confirmations ("Kara it
# is!"). Closes the divergence risk where the main stream says "confirmed"
# but the shadow classifier rejects the tool — user would hear confirmation
# without the state change. Belt-and-braces with the structured-output
# contract. Gated separately so it can be toggled without touching the
# main contract block.
HEDGED_NAMING_CONTRACT_ENABLED = True

# VISION_ROADMAP P3.21 (Session 91) — cross-person privacy prompt block.
# Addresses a live-run finding from the 2026-04-22 multi-convo session:
# when Jagan asked "who are you talking to when I was away?" (referring to
# John's session during Jagan's absence), the brain answered "No one" —
# technically privacy-correct (John's session was out-of-scope for Jagan's
# context) but phrased as a denial. That's a lie. The fix is a prompt
# block teaching honest-without-disclosure phrasing: "Someone else was in
# the room and spoke with me — I can't share their specifics without
# their consent" rather than "No one."
#
# Gated separately from HONESTY_POLICY_BLOCK_ENABLED so it can be toggled
# independently: HONESTY_POLICY covers intra-session truthfulness,
# CROSS_PERSON_PRIVACY covers cross-session visibility boundaries.
# Together they form the honesty-with-privacy contract P3.26 will
# generalize once this block has lived through a few live sessions.
CROSS_PERSON_PRIVACY_BLOCK_ENABLED  = True    # render <<<CROSS-PERSON PRIVACY>>> in brain prompt

# ── Wave 4 Item 18 — tier memory: core vs archive ────────────────────────────
# Core memory = always-on stable facts injected into Section 2 of the
# session-stable prefix (render_session_stable_prefix). Archive memory =
# existing semantic search + search_memory tool (unchanged). Additive — core
# is a superset of what the brain previously had to fetch via search_memory.
CORE_MEMORY_ENABLED        = True
CORE_MEMORY_MAX_FACTS      = 30    # max rows injected per session
CORE_MEMORY_MIN_CONFIDENCE = 0.40  # rows below this are too uncertain for always-on
CORE_MEMORY_ATTRIBUTES: frozenset = frozenset({
    # Identity anchors — stable self-descriptions
    "name", "preferred_name", "nickname",
    "lives_in", "from_country", "from_state", "from_city",
    "works_at", "job_title", "occupation",
    "relationship_to_best_friend", "relationship_to_jagan",
    # Safety-critical (S105 — append-only, always surface so the brain
    # proactively addresses past disclosures without being prompted)
    "expressed_suicidal_thoughts",
    "mentioned_self_harm",
    "mentioned_abuse",
    "reported_substance_abuse",
    "has_experienced_crisis",
    # Long-term preferences that shape every conversation
    "dietary_preference", "favorite_food", "food_restriction",
    "communication_style", "language_preference",
    # Household facts
    "visited_household", "household_role", "lives_in_household",
})

# ── Session 96 Bug 3 — visitor-context block ────────────────────────────────
# When a VISITOR_ALERT nudge is present in prompt_addendum AND the current
# speaker is the household owner, inject a <<<VISITOR CONTEXT>>> block that
# tells the brain to route owner queries about "who was here" / "who did you
# talk to" through `search_memory(visitor_name, ...)` rather than
# `report_identity_mismatch`. Canary 2026-04-22 exposed the routing gap —
# brain misread "who are you talking to" as an identity dispute and picked
# the wrong tool. This block closes the gap by naming the correct tool for
# the question shape when owner-context signals are present.
VISITOR_CONTEXT_BLOCK_ENABLED = True

# ── Session 97 Fix 1 — stranger promotion nudge block ──────────────────────
# When a stranger session has been going for >=2 user turns WITHOUT the
# brain having called `update_person_name`, inject a <<<STRANGER IDENTITY>>>
# block reminding the brain that stranger name reveals ARE promotion
# triggers. 2026-04-22 canary showed Lexi's "my name is Lexi by the way"
# (turn ~41) producing a conversational ack but no tool call → orphaned
# shadow node + standalone facts never linked to her real person_id.
# Tool description tightening covers the explicit case; this block covers
# the elapsed-time case where the stranger has been unpromoted for
# multiple turns AND the brain needs a gentle reminder that promotion
# is overdue if a name has surfaced.
STRANGER_IDENTITY_BLOCK_ENABLED = True
STRANGER_IDENTITY_BLOCK_MIN_TURNS = 0  # P0.S7.5.2 D5: 2→0; block fires on every stranger turn so canary-3 question-shapes hit guidance immediately

# P0.S7.5.2 D3 — voice gallery accumulation gates. Mirrors face gallery's
# SELF_UPDATE_CENTROID_MIN=0.55 discipline (Session 51 P0.5). Without
# these gates, canary 3 (2026-05-20) Jagan's voice profile drifted to
# the point where his own utterances scored 0.3-0.4 against his mature
# gallery — symptom of centroid contamination from short-utterance noise.
MIN_VOICE_ACCUM_DURATION_SECS: float = 1.5  # ECAPA-TDNN min reliable length (per core/voice.py:147); shorter audio produces noisy embeddings
VOICE_SELF_UPDATE_CENTROID_MIN: float = 0.55  # cosine-to-centroid floor; mirrors face gallery SELF_UPDATE_CENTROID_MIN per Session 51
VOICE_CENTROID_GATE_MIN_SAMPLES: int = 5  # bootstrap-safe: gate fires only when ≥5 samples present so early enrollment isn't blocked

# P0.S7.5.2 D4 — STT 1-word artifact filter. Canary 3 (2026-05-20)
# surfaced multiple turns where Whisper emitted bare "You", "Yeah",
# "Thank" without terminal punctuation — phantom acknowledgments that
# triggered phantom downstream work. 1-word transcripts now pass only
# when EITHER (a) terminated with .!? OR (b) the lowercased word is in
# the known-imperative allowlist below.
MIN_STT_WORD_COUNT: int = 2  # minimum words to keep STT output unless terminated or allowlisted
STT_KNOWN_IMPERATIVES: frozenset[str] = frozenset({
    "yes", "no", "stop", "help", "okay", "ok", "sure", "yeah", "yep", "nope",
})
"""1-word Whisper-allowlist for legitimate confirmation/denial responses.

Expansion criteria (P0.S7.5.2 Plan v2 §4.2):
  - 3+ canary instances of the word being legitimately spoken AND filtered
    (evidence: terminal_output.md grep + user confirmation that the word
    was spoken as a real response, not Whisper noise)
  - No semantic ambiguity (multi-meaning words → require punctuation instead)
  - Documented in CLAUDE.md closure narrative with the 3-instance evidence trail
"""

# Session 113 Part 1 — LLM turn allocation via <<<ADDRESS DECISION>>> block.
# In multi-person rooms the brain (not the pipeline's voice routing) decides
# who to address. Block is injected only when 2+ active sessions exist; the
# brain prefixes its response with `[addressing:Name]` or the literal
# `[addressing:current]` (shorthand for "the last speaker, no override").
# Pipeline parses the marker, sets the addressed_to field (Session 111
# Critical #3), and strips it before TTS. Single-person sessions skip the
# block entirely — current dispatch-to-the-one-pid behavior preserved.
# Toggle False for one-line rollback to legacy "dispatch to resolved
# speaker" behavior if the marker introduces regressions.
ADDRESS_DECISION_BLOCK_ENABLED = True

# Session 113 Part 2 — batched-greeting LLM decision.
# When 2+ new known people enter the frame in the same vision-scan iteration,
# the brain (not the face-detection order) decides whom to greet first.
# Keeps behavior unchanged when only one person enters. Stranger greetings
# already gate on the system-name utterance, so they're out of scope.
# Fallback: if the LLM call fails or exceeds BATCH_GREETING_LLM_TIMEOUT_SECS,
# fall back to detection order (current behavior).
#   BATCH_GREETING_ENABLED          — master flag; False = legacy detection-order
#   BATCH_GREETING_MIN_PEOPLE       — minimum people to trigger LLM call (1 skips)
#   BATCH_GREETING_LLM_TIMEOUT_SECS — caps the extra latency we'll eat for ordering
BATCH_GREETING_ENABLED          = True
BATCH_GREETING_MIN_PEOPLE       = 2
BATCH_GREETING_LLM_TIMEOUT_SECS = 1.0

# Phase 3B.1 — unified <<<ROOM>>> block for multi-person scenes.
# Replaces the fragmented trio of SCENE (in-room portion), cross-person
# excerpts, and per-person mood addendums with a single block that gives
# brain full room-state awareness in one coherent structure: active
# speakers + interleaved turns across all speakers + per-person mood +
# room duration. Fires ONLY when 2+ active sessions exist; single-person
# sessions keep existing SCENE-only path unchanged (backward compat).
# SCENE block still renders — it handles OUT-of-room concerns (recent
# visitors, ended-session safety flags) that ROOM doesn't cover.
#   ROOM_BLOCK_ENABLED  — master flag; False = skip ROOM block entirely
#   ROOM_BLOCK_TURN_CAP — max turns rendered chronologically (rolling window)
ROOM_BLOCK_ENABLED  = True
ROOM_BLOCK_TURN_CAP = 10

# P0.S7.D-C Stage 1 — flag-gate the legacy `_build_cross_person_excerpts`
# block (pipeline.py:1202). Default OFF — runtime renders only <<<ROOM>>>
# (S113 P3B.1) + <<<SHARED CONTEXT>>> (P0.S7 D-A) for multi-person scenes.
# Function code stays in source for the duration of D-B/D-D/D-E work;
# rollback path is one-flag-flip. Stage 2 hard-deletes the function +
# flag after the bundled-queue canary validates D-A + D-C + D-B + D-D +
# D-E + γ AS A SET (Plan v1 §8 trigger spec).
CROSS_PERSON_EXCERPTS_ENABLED: bool = False

# P0.S7 D-A — SHARED CONTEXT block (room-scoped conversation history pulled
# from conversation_log via FaceDB.get_recent_room_conversation).
# Complements ROOM block (in-memory state) with persisted SQL retrieval that
# survives session expiry and the CONVERSATION_HISTORY_LIMIT in-memory trim.
# Fires under the same multi-person + room_session_id gate as ROOM block;
# additionally skipped on disputed callers (T-A).
#   SHARED_CONTEXT_BLOCK_ENABLED  — master flag; False = skip block entirely
#   SHARED_CONTEXT_BLOCK_TURN_CAP — max turns retrieved from conversation_log
SHARED_CONTEXT_BLOCK_ENABLED  = True
SHARED_CONTEXT_BLOCK_TURN_CAP = 10

# P0.S7.5 D1 — nudge types that are ONE-SHOT proactive reminders.
# These get mark_nudge_injected on first delivery (legacy behavior).
# Nudge types NOT in this set default to PERSISTENT context — they
# stay pending and re-inject every turn until expires_at or dismissed.
# VISITOR_ALERT is INTENTIONALLY excluded: owner needs persistent
# context about visitor presence whenever they ask, not just first turn.
# When adding a new nudge type, default behavior is PERSISTENT — opt
# into one-shot only when the type is a proactive reminder that
# should not repeat.
ONE_SHOT_NUDGE_TYPES: frozenset[str] = frozenset({
    "CROSS_PERSON_HYPOTHESIS",
    "INTENTION_FOLLOWUP",
    "MEMORY_PROMPT",
})

# P0.S7.5 D2 — SHARED CONTEXT widening window. When the current scene
# is single-person but the requester appears in recent room sessions'
# audience_ids within this window, render persisted history from those
# rooms. Matches the visitor-alert expiry (24h) so the two defenses
# align temporally.
SHARED_CONTEXT_RECENT_AUDIENCE_HOURS: float = 24.0

# P0.S7.5 D4 — gate the KNOWN SPEAKER IDENTITY block. Default True;
# rollback is a one-line flip if the block proves too verbose for
# normal turns.
KNOWN_SPEAKER_IDENTITY_BLOCK_ENABLED: bool = True

# Phase 3B.3 — TURN ARBITRATION rules appended to the ROOM block. Gives
# the brain concrete reasons to emit the [addressing:X] marker (Session
# 113 Part 1 mechanism) — mumble continuation, pending-thread circle-back,
# long-silence re-engagement, direct-question-across-context. Pure prompt
# engineering; no new code paths. Gated ALONGSIDE ROOM_BLOCK_ENABLED —
# arbitration has no meaning without the ROOM block's context.
TURN_ARBITRATION_ENABLED = True

# Phase 3B.5 — room-level memory retrieval via `search_room_memory` tool.
# Lets brain search the whole current room session's turn log (all speakers,
# interleaved chronologically) instead of the per-person search_memory
# shape. Enables queries like "what have we talked about tonight?" or
# "when did Lexi mention her interview?" that span multiple speakers.
#   SEARCH_ROOM_MEMORY_ENABLED  — master flag (False = tool call returns
#                                 empty with a hint; avoids dynamic tool
#                                 registration complexity)
#   SEARCH_ROOM_MEMORY_MIN_TURNS — below this turn count, tool returns
#                                 empty + hint so brain routes to
#                                 search_memory or direct recall instead
#                                 (avoids noisy results on 1-3 turn rooms)
SEARCH_ROOM_MEMORY_ENABLED   = True
SEARCH_ROOM_MEMORY_MIN_TURNS = 5

# Phase 3B.6 — room-end synthesis. When the last person leaves a room
# session, orchestrator writes a synthesized summary (topic tags, safety
# flags, LLM narrative) to the room_summaries table so future greetings
# can surface recent-room context without re-running retrieval.
# Fire-and-forget from _on_room_end; room lifecycle never blocks on
# synthesis latency. On LLM failure, falls back to topic-only summary.
#   ROOM_END_SYNTHESIS_ENABLED     — master rollback flag
#   ROOM_SUMMARY_LLM_TIMEOUT_SECS  — narrative LLM call ceiling
#   ROOM_RECENT_CONTEXT_HOURS      — lookback window for greeting enrichment
ROOM_END_SYNTHESIS_ENABLED    = True
ROOM_SUMMARY_LLM_TIMEOUT_SECS = 3.0
ROOM_RECENT_CONTEXT_HOURS     = 24

# Phase 3B.2 — stay silent when one person in the room addresses ANOTHER
# person by name (user-to-user, not user-to-AI). Classifier-driven: when
# `_classify_intent` labels a turn as `direct_address_to_person` with a
# target name that is NOT the system name, skip the LLM response phase
# but still log the turn to history (so brain learns from what was said).
# False = legacy behavior (brain responds to every user utterance).
ROOM_STAY_SILENT_ON_USER_TO_USER = True

# Session 115 Fix 1 — heuristic pre-check before the user-to-user
# classifier call. Eliminates ~80% of LLM calls by pattern-matching
# vocative names against active session display names. Falls through
# to the classifier (with cache) when the heuristic is inconclusive.
# Toggle False for one-line rollback to classifier-only path.
USER_TO_USER_HEURISTIC_ENABLED = True

# Session 117 — <<<SYSTEM IDENTITY>>> prompt block. Anchors the brain on
# its own name once set, preventing hallucinated rename re-asks during
# long conversations (canary 2026-04-25 17:04: brain emitted "What name
# would you like to give me?" mid-conversation despite system_name being
# 'Kara' for several turns). Block + tool-description hardening combine
# to make the regression diagnosable and unrecoverable in the failure
# mode. Toggle False for one-line rollback.
SYSTEM_IDENTITY_BLOCK_ENABLED = True

# Session 118 Fix A — multi-segment voice routing with stranger detection.
# Canary 2026-04-25 23:21: pyannote returned 2 segments (Jagan + a
# stranger asking "what is the escape velocity of earth?"); voice ID
# couldn't match the second voice against any enrolled gallery and the
# resolver fell through to "route to current" (Jagan). Result: Jagan got
# wrongly attributed with the stranger's question. When pyannote signals
# multiple voices AND voice match against ALL known speakers is below
# this floor, the routing logic drops the turn — user/stranger repeats
# with cleaner audio, normal routing fires next iteration.
VOICE_ROUTING_STRANGER_FLOOR = 0.30

# Session 120 (2026-04-28) — single-segment voice mismatch drop.
# Same threat model as Session 118's multi_segment_voice_mismatch but for
# the case where pyannote returns ONE segment AND ECAPA can't match the
# enrolled holder AND there's no other candidate session in scene. Without
# this gate, the routing fallback "no other candidates → route to current"
# silently misattributes the stranger's voice to the holder. Toggleable
# for canary rollback.
VOICE_ROUTING_SINGLE_SEGMENT_MISMATCH_ENABLED = True

# Phase 2 of Voice/Vision Independence (Session 124, 2026-04-28).
# Throttle the vision_channel shadow comparison call. observe_scene runs
# embed+recognize on already-detected boxes; cheap but not free, so we
# sample once per N seconds instead of every scan iteration.
VISION_SHADOW_INTERVAL_SECS  = 5.0

# Phase 5 (Session 119) — continuous evaluation infrastructure.
# Pure observability — none of these flags affect production behavior.
#   SHADOW_SAMPLE_RATE             — 1% of production classifier calls
#                                    also log to intent_divergences with
#                                    mode='shadow' for offline review.
#   SHADOW_SAMPLE_ENABLED          — kill switch; False stops sampling.
#   EVAL_WEEKLY_ALERT_PRECISION_DROP_PP
#                                  — per-intent precision drop (in
#                                    percentage points) that flags an
#                                    alert in `eval_weekly.py --alert`.
#   EVAL_WEEKLY_DIVERGENCE_LOOKBACK_DAYS
#                                  — window for the divergence query in
#                                    the weekly review.
#   EVAL_WEEKLY_TOP_N              — how many top-N rows to surface per
#                                    section (low-confidence, rejections).
SHADOW_SAMPLE_RATE                  = 0.01
SHADOW_SAMPLE_ENABLED               = True
EVAL_WEEKLY_ALERT_PRECISION_DROP_PP = 5.0
EVAL_WEEKLY_DIVERGENCE_LOOKBACK_DAYS = 7
EVAL_WEEKLY_TOP_N                   = 20

# ─────────────────────────────────────────────────────────────────────────
# VISION_ROADMAP Phase 3A (P3.1, Session 95) — privacy model scaffolding.
# Visibility levels for knowledge facts + conversation turns. Enforced at
# retrieval time by ``_visibility_clause()`` (P3.3, coming next). Fail-
# closed default is ``"personal"`` — novel / unclassified attributes are
# scoped to their owner only, because getting privacy wrong in the
# permissive direction is worse than in the restrictive direction.
#
# Tier semantics (Session 94 reviewer refinement — best_friend override):
#   * public      — visible to every person in the household (names,
#                   country-of-origin, relationship-to-household roles)
#   * personal    — owner-only (lives_in, job_title, mood, concerns)
#   * household   — visible to best_friend + future flagged roommates;
#                   NOT to non-household speakers. This is the tier the
#                   "Jagan asks who was here" scenario depends on —
#                   presence facts, general topics, visitor metadata.
#   * system_only — internal inferences (voice/face embedding hashes,
#                   bootstrap credit state); NEVER surfaced to any user.
#
# Policy: best_friend = public + household + their own personal facts.
# Non-best-friend = public + their own personal facts only.
# ─────────────────────────────────────────────────────────────────────────
PRIVACY_LEVELS: frozenset[str] = frozenset({
    "public",        # visible to all persons in the household
    "personal",      # visible only to the person_id who owns the fact
    "household",     # visible to best_friend (+ future flagged roommates)
    "system_only",   # never surfaced to any user (internal inferences)
})

PRIVACY_LEVEL_DEFAULT: str = "personal"  # Fail-closed: novel attributes → personal

# Attribute → privacy_level static map. Known attributes don't need LLM
# classification (P3.2) — this is the fast path. Extend as new attributes
# emerge from live runs. Novel attributes get cached LLM classification
# with PRIVACY_LEVEL_DEFAULT as the safe fallback.
PRIVACY_LEVEL_STATIC_MAP: dict[str, str] = {
    # Public (everyone in household can see)
    "name":                        "public",
    "from_country":                "public",

    # Household (best_friend + roommates see; strangers don't)
    # Reviewer S95 refinement: relationship_to_* moved public→household.
    # "Lexi is Jagan's classmate" reveals Jagan's social graph to third
    # visitors; keeping it household means best_friend sees the relationship
    # (owner visibility) but random strangers don't (social privacy).
    "relationship_to_jagan":       "household",
    "relationship_to_best_friend": "household",
    "preferred_ai_name":     "household",
    "lives_in_household":    "household",
    "household_role":        "household",
    "visited_household":     "household",  # presence facts
    "discussed_topic":       "household",  # general topic area, not content

    # Personal (owner-only)
    "lives_in":              "personal",
    # NB: from_country is public (nationality), from_state is personal
    #     (narrower location identifiable). Don't normalize — the asymmetry
    #     is intentional privacy granularity.
    "from_state":            "personal",
    "works_at":              "personal",
    "job_title":             "personal",
    "current_mood":          "personal",
    "current_activity":      "personal",
    "dietary_preference":    "personal",
    "favorite_food":         "personal",
    "confided_concern":      "personal",  # explicit confidential tier
    "health_condition":      "personal",

    # System-only (never surfaced to any user)
    "voice_embedding_hash":  "system_only",
    "face_embedding_hash":   "system_only",
    "bootstrap_credits":     "system_only",
}

# ── VISION_ROADMAP P3.2/3A.2 — privacy-level classifier call params ──────────
# LLM fallback parameters for `_classify_privacy_level` (core/brain_agent.py).
# Classifier returns a tiny JSON envelope (`{"level": "...", "reasoning":
# "..."}`) so the token budget is intentionally small — 150 covers the JSON
# keys, a tier string, and a one-sentence reasoning with headroom. Timeout
# 5s mirrors `_classify_intent` in Phase 1. On timeout or any classifier
# failure, the caller falls back to `PRIVACY_LEVEL_DEFAULT` ("personal") and
# does NOT cache — failed classifications must be retried on the next
# attribute-novel fact so a transient provider blip doesn't permanently
# poison the cache.
PRIVACY_CLASSIFIER_TIMEOUT_SECS: float = 5.0
PRIVACY_CLASSIFIER_MAX_TOKENS: int    = 150

# ── Bug T (2026-04-21 live run) — server-side live-data gate for search_web ──
# The LLM's tool description alone is not enough — Llama-3.3 consistently
# ignores NEVER clauses when context pattern-matches a plausible call. Live
# evidence: 3 search_web calls fired on personal statements / AI-opinion
# questions in one session. Server-side regex gate rejects the call before
# it hits Tavily. Block patterns run FIRST (catch opinion / personal
# statements), then allow patterns check for live-data markers. Default deny
# if neither matches — the LLM should prefer answering from training
# knowledge over a speculative search.
#
# Block list deliberately narrow (tightened from reviewer's broader set
# during implementation): only verbs that clearly signal preference / opinion
# / memory-recall are blocked. Broader verbs like "know" / "have" were left
# out so "do you know today's weather?" still reaches the allow pattern
# (\btoday\b + \bweather\b both match → allowed).
SEARCH_WEB_LIVE_DATA_PATTERNS: tuple[str, ...] = (
    # Time markers — must be fresh, not historical
    r"\btoday\b", r"\btonight\b", r"\bthis\s+(?:week|morning|evening|afternoon)\b",
    r"\brecent(?:ly)?\b", r"\blatest\b", r"\bcurrent(?:ly)?\b",
    r"\bright\s+now\b", r"\bat\s+the\s+moment\b", r"\bbreaking\b",
    r"\btomorrow\b", r"\byesterday\b",
    # Live-data domain keywords
    r"\bweather\b", r"\btemperature\b", r"\bforecast\b",
    r"\bscore\b", r"\bscores\b",
    r"\bmatch\s+(?:today|tonight|tomorrow|now|live)\b",
    r"\bgame\s+(?:today|tonight|tomorrow)\b",
    r"\bnews\b", r"\bheadlines\b",
    r"\bprice\s+of\b", r"\bstock\b", r"\btraffic\b",
    # Specific question shapes
    r"\bwhat[\'`]?s\s+(?:happening|going\s+on|new)\b",
    r"\bwho\s+(?:won|is\s+playing|is\s+winning)\b",
)
SEARCH_WEB_BLOCK_PATTERNS: tuple[str, ...] = (
    # Personal statements — user talking about themselves. These are never
    # live-data needs and routing them to search wastes budget.
    r"^\s*(?:i\s+(?:'m|am|think|like|love|hate|want|prefer|find|feel|need|believe))\b",
    r"\bmy\s+(?:favorite|favourite|team|car|hobby|job|friend)\b",
    # AI-opinion questions — user asking the AI for ITS preference/take.
    # Deliberately narrow: only preference / opinion verbs. "have" / "know" /
    # "remember" were excluded so legit live-data phrasings like "do you know
    # today's weather?" still reach the allow check below.
    r"\bdo\s+you\s+(?:like|think|prefer|want|feel|believe)\b",
    r"\bwhat[\'`]?s\s+your\s+(?:favourite|favorite|opinion|take|view|thought)\b",
    r"\bwhat\s+do\s+you\s+(?:think|like|prefer|feel|believe)\b",
    r"\bhow\s+do\s+you\s+feel\b",
    r"\bin\s+your\s+opinion\b",
    # Conversational closers / filler — no search warranted.
    r"^\s*(?:okay|ok|yeah|yes|no|alright|sure)\s*[.!?]?\s*$",
    r"\bi[\'`]?ll\s+(?:come\s+back|be\s+back|see\s+you)\b",
)
SEARCH_MAX_PER_TURN    = 2           # max sequential web searches per conversation turn

# ── TTS ───────────────────────────────────────────────────────────────────────
# TTS handled in audio.py — Kokoro (English, primary) + Piper English (fallback)

# ── Anti-spoofing ─────────────────────────────────────────────────────────────
# MiniFASNet liveness detection gates enrollment and first-time recognition.
# Prevents photo / screen-replay attacks. Requires: pip install silent-face-anti-spoofing
# Falls back silently (allow) if the package is not installed.
ANTISPOOFING_ENABLED    = True   # set False to bypass (e.g. during dev without camera)
ANTISPOOFING_THRESHOLD  = 0.5    # min liveness score to accept as real (0–1).
                                  # Restored from temp 0.3 (Session 59 debug value) to 0.5
                                  # after Session 60 live validation: MiniFASNet outputs
                                  # live_prob ≥ 0.95 consistently on genuine faces in typical
                                  # indoor lighting. 0.5 leaves huge headroom while still
                                  # rejecting photo attacks (observed live_prob ≈ 0.016).
                                  # Revisit after 2 weeks of logs with LOG_ANTISPOOF_SUMMARY
                                  # data — raise to 0.6 if the rolling minimum stays > 0.8.

# Anti-spoof observability flags.
#  - LOG_ANTISPOOF_PROBS:   per-frame probs dump. OFF by default (noisy). Flip ON when
#                           acutely debugging liveness misclassification.
#  - LOG_ANTISPOOF_SUMMARY: rolling stats emitted every N calls. ON by default — gives
#                           passive drift detection (camera aging, lighting changes) without
#                           reading every frame. Format:
#                           [Anti-spoof] summary over last N frames: min=X.XX mean=Y.YY max=Z.ZZ rejects=N thr=0.50
LOG_ANTISPOOF_PROBS            = False
LOG_ANTISPOOF_SUMMARY          = True
LOG_ANTISPOOF_SUMMARY_INTERVAL = 100

# ── P0.S1 anti-spoof gating ───────────────────────────────────────────────────
# Per-track burst threshold for watchdog alert (C2 contract). When the same
# SORT track produces >=ANTI_SPOOF_BURST_THRESHOLD rejections within
# ANTI_SPOOF_BURST_WINDOW_SECS, the watchdog fires ONCE (exact-equality
# trigger per Plan v2 §14b.1 — `count == THRESHOLD`, not `>=`). Per-track
# scope: track_A burst does NOT lock out track_B (no cross-track lockout).
# Voice channel is NOT gated by anti-spoof burst (C2 — no voice lockout).
ANTI_SPOOF_BURST_THRESHOLD   = 3
ANTI_SPOOF_BURST_WINDOW_SECS = 60.0

# Reason-code distinguishability for dashboard + replay (C1 contract).
# Four codes, never collapsed. Operators distinguish hardware-down
# (unavailable) from active attack (rejected) from missing-frame
# (no_verdict) from clean (passed).
ANTI_SPOOF_REASON_PASSED      = "passed"
ANTI_SPOOF_REASON_REJECTED    = "rejected"
ANTI_SPOOF_REASON_UNAVAILABLE = "unavailable"
ANTI_SPOOF_REASON_NO_VERDICT  = "no_verdict"

# ── Logging / observability ───────────────────────────────────────────────────
# Single source of truth for log time formatting. Every timestamped print path
# goes through core.log_utils._now_log_ts() — grep-able invariant. No ad-hoc
# datetime.strftime / time.strftime anywhere in those paths.
#   LOG_TIME_FORMAT:      strftime string. %f is 6-digit microseconds; the
#                         helper trims to ms for readability.
#   LOG_LATENCY_ENABLED:  emit "(Nms)" elapsed tags on STT/turn-cycle lines.
#   LOG_STT_MAX_CHARS:    0 = no truncation (default). Positive N truncates
#                         log lines longer than N chars + ellipsis.
LOG_TIME_FORMAT    = "%H:%M:%S.%f"
LOG_LATENCY_ENABLED = True
LOG_STT_MAX_CHARS  = 0

# ── Context Compression ───────────────────────────────────────────────────────
# Three-tier compression keeps the LLM context window healthy for long sessions.
# Tier 1 (MicroCompact): sync, truncates individual messages > MICRO_CHAR_LIMIT in old history
# Tier 2 (AutoCompact):  async, LLM-summarizes old turns when history exceeds TOKEN_COMPACT_THRESHOLD
# Tier 3 (hard trim):    emergency fallback — drop oldest turns if still over TOKEN_HARD_LIMIT
AUTOCOMPACT_KEEP_TURNS    = 15       # recent turn-pairs kept verbatim after AutoCompact
MICRO_CHAR_LIMIT          = 2_000    # individual message char cap in old history (MicroCompact)

# ── Token estimation (Pattern 6) ──────────────────────────────────────────────
# Char-based heuristic: avoids tokenizer dependency (no sentencepiece/tiktoken needed).
# 3.5 chars/token is conservative for English voice transcripts; handles mixed content.
# Accuracy ±20% — sufficient for compaction decisions, not for billing.
#
# Llama-3.3-70B context: 128K tokens. System prompt ≈ 1.5K; response reserve = 400.
# Effective history budget ≈ 126K tokens. Compact well before hitting the wall.
TOKEN_CHARS_PER_TOKEN   = 3.5     # chars per token for mixed voice/English content
TOKEN_COMPACT_THRESHOLD = 50_000  # estimated history tokens → trigger AutoCompact
TOKEN_WARN_THRESHOLD    = 90_000  # estimated full-context tokens → log approaching limit
TOKEN_HARD_LIMIT        = 100_000 # estimated tokens → emergency drop oldest turns

# Household context agent
HOUSEHOLD_DISPUTE_SETTLE_SESSIONS = 2  # sessions of corroboration before "provisional" → "settled"

# ── Brain Agent ───────────────────────────────────────────────────────────────
DEFAULT_SYSTEM_NAME        = "Dog"  # AI's default name before user assigns one
BRAIN_DB_PATH              = FACES_DIR / "brain.db"
GRAPH_DB_PATH              = FACES_DIR / "brain_graph"   # Kuzu property graph directory

# ── Classifier graph (Spec 1) ────────────────────────────────────────────────
# Lives separately from faces/ — system intelligence, factory-reset-immune.
CLASSIFIER_DATA_DIR             = ROOT / "data"
CLASSIFIER_DB_PATH              = CLASSIFIER_DATA_DIR / "classifier_scenarios.db"
CLASSIFIER_SEED_PATH            = CLASSIFIER_DATA_DIR / "classifier_scenarios_seed.jsonl"
CLASSIFIER_AUDIT_LOG_PATH       = CLASSIFIER_DATA_DIR / "classifier_audit_log.jsonl"
CLASSIFIER_SNAPSHOT_DIR         = CLASSIFIER_DATA_DIR / "classifier_snapshots"
CLASSIFIER_EMBEDDING_MODEL_ID   = "multilingual-e5-large-instruct-v1"
CLASSIFIER_ABSTRACT_RULE_VERSION = 1
CLASSIFIER_DATA_DIR.mkdir(exist_ok=True)

# ── Graph classifier (Spec 2) ────────────────────────────────────────────────
# Three-stage rollout: shadow (default after ship) → primary (config flip
# after divergence rate is acceptable) → retired (LLM never called).
GRAPH_CLASSIFIER_VALID_MODES: frozenset = frozenset({"shadow", "primary", "retired"})
GRAPH_CLASSIFIER_MODE             = "shadow"
GRAPH_K_NEIGHBORS                 = 20      # top-K in cosine k-NN
GRAPH_ABSTAIN_THRESHOLD           = 0.40    # winning_weight / total_weight floor
GRAPH_PRIMARY_CONFIDENCE_FLOOR    = 0.55    # in primary mode, fall back below this
GRAPH_LATENCY_BUDGET_MS           = 100     # log warning if exceeded
GRAPH_OUTCOME_HOLDING_TURNS       = 3       # how many turns to wait before crediting confirmation
GRAPH_USE_LOCAL_EMBEDDINGS        = True    # local E5 (HF Transformers) instead of Together.ai network endpoint
GRAPH_LOCAL_EMBEDDING_MODEL       = "intfloat/multilingual-e5-large-instruct"
GRAPH_LOCAL_EMBEDDING_DEVICE      = "auto"  # "auto" | "cuda" | "cpu"
BRAIN_AGENT_POLL_INTERVAL  = 2.0   # seconds between polls for new turns
BRAIN_AGENT_CONTEXT_TURNS  = 6     # prior turns fed as context to extraction
BRAIN_AGENT_MIN_WORDS      = 4     # turns shorter than this are skipped

# P0.S7.2 D5 — minimum content length for multi-person assistant-turn
# extraction (κ branch). Below this threshold the turn is skipped — filters
# acknowledgments + KAIROS check-ins + filler that wouldn't yield useful
# topic-bearing facts for participants' cross-session retrieval. Auditor
# approved 80 (~15-20 words).
ASSISTANT_TURN_EXTRACT_MIN_CHARS: int = 80
PREF_AUTO_CONFIRM_THRESHOLD = 3    # sessions_seen needed to auto-activate a staged pref
PREF_ANALYSIS_TURNS         = 40   # conversation turns fed to PromptPrefAgent

# ── Schema normalization (Phase 4) ───────────────────────────────────────────
# SchemaNormAgent clusters synonymic attribute names by embedding cosine similarity.
SCHEMA_NORM_TRIGGER    = 30    # run normalization when schema_catalog has this many rows
SCHEMA_NORM_THRESHOLD  = 0.97  # cosine similarity above this = auto-merge (same concept)
                                # raised from 0.95: too-loose similarity was merging distinct
                                # semantics (e.g. 'former_name' into 'presence'). Distinct
                                # semantic families are additionally protected by SCHEMA_NORM_DISTINCT_FAMILIES.

# Attribute families that must NEVER auto-merge even if the embedding model says they're similar.
# Each entry is a tuple of substrings; if a candidate attribute matches one family and the target
# matches a different family, the merge is skipped. Extend as new confusions surface in the schema_catalog.
SCHEMA_NORM_DISTINCT_FAMILIES = (
    ("name",),                    # former_name, current_name, nickname
    ("presence", "arrived", "here", "location", "whereabouts"),
    ("time", "date", "when", "arrived_at", "left_at"),
)
SCHEMA_NORM_AMBIGUOUS  = 0.72  # below THRESHOLD but above this = log for review (same domain)

# Confidence feedback — applied when user confirms/denies AI's recalled facts
CONFIDENCE_BOOST       = 0.08  # added when user explicitly confirms an AI-recalled fact
INTRA_PREF_TURN        = 15    # run lightweight pref analysis after this many turns per session
INTRA_PREF_TURNS_LIMIT = 6     # number of recent turns fed to the lightweight intra-session pass

# ── Phase 5: Self-improvement loops ──────────────────────────────────────────
FRICTION_MIN_CONFIDENCE        = 0.70  # min confidence for FrictionDetectionAgent to flag a pref
PREDICATE_VOLATILITY_THRESHOLD = 3     # contradiction_count ≥ this = volatile predicate
PREDICATE_CONFIDENCE_CAP       = 0.75  # max stored confidence for volatile-predicate facts

# Session 105 Bug N — safety-critical attribute patterns that must NEVER be
# overwritten by the ContradictionAgent. 2026-04-23 canary: Lexi's
# `current_mood='suicidal'` got REPLACED by `current_mood='loving'` four
# turns later when she said "I like food and I like my boyfriend." In a
# real-world companion AI this is a safety failure — the crisis
# disclosure was erased before best_friend could be informed. Fix:
# extraction emits a dual-attribute pair (momentary `current_mood`
# alongside historical `expressed_suicidal_thoughts='true'`) and the
# ContradictionAgent pre-check short-circuits when the attribute matches
# any of these regex patterns, preserving the history append-only.
# Patterns are intentionally wide: catches expressed_*_thoughts,
# mentioned_* (abuse/self_harm/crisis/domestic_violence), reported_*_abuse,
# and has_experienced_crisis.
SAFETY_CRITICAL_ATTRIBUTE_PATTERNS: frozenset[str] = frozenset({
    r"^expressed_.*_thoughts$",
    r"^mentioned_.*$",
    r"^reported_.*_abuse$",
    r"^has_experienced_crisis$",
})

# Session 105 Obs B — HouseholdExtractionAgent shadow-node name blocklist.
# 2026-04-23 canary: HouseholdAgent created shadow_persons rows for
# "boyfriend", "him" (line 308, 361, 498). Pronouns and relationship
# roles aren't people names — they pollute the shadow graph with
# unlinkable placeholders. When the brain later learns the actual name
# ("her name is Sarah"), it can create the shadow at that point. The
# role-only shadow contributes zero recall value.
SHADOW_NAME_BLOCKLIST: frozenset[str] = frozenset({
    # Pronouns
    "him", "her", "them", "they", "he", "she", "it",
    # Indefinite references
    "someone", "anyone", "nobody", "somebody", "no one",
    # Relationship roles
    "boyfriend", "girlfriend", "husband", "wife", "partner",
    "mother", "father", "mom", "dad", "mum", "papa", "mama",
    "brother", "sister", "son", "daughter", "child", "kid",
    # Generic social labels
    "boss", "friend", "colleague", "neighbor", "classmate",
    "roommate", "teacher", "student",
})

# ── G7b: Multi-person scene awareness ────────────────────────────────────────
# Attributes whose names CONTAIN any of these keys (case-insensitive) are tagged
# privacy_level='private' on write. Best_friend bypasses all privacy filters.
PRIVATE_ATTRIBUTES: dict[str, str] = {
    "health":       "private",
    "medical":      "private",
    "diagnosis":    "private",
    "medication":   "private",
    "finance":      "private",
    "salary":       "private",
    "debt":         "private",
    "income":       "private",
    "secret":       "private",
    "relationship": "private",
    "affair":       "private",
    "confession":   "private",
}
SCENE_STALE_SECS              = 5.0   # _persons_in_frame entries older than this are excluded from scene block
VOICE_ROUTING_FACE_STALE_SECS = 2.0   # tighter staleness for voice-routing decisions (vs 5.0 for LLM scene)
SCENE_BLOCK_ENABLED           = True  # master on/off for the <<<SCENE>>> sensor block (injected every turn)
SCENE_VOICE_STALE             = 30.0  # offscreen voice mention window: sessions older than this are omitted
# Session 108 Phase 3A.7 — recent-visitor TTL for the new SCENE
# "Recent visitors" section. Visitors whose session ended within this
# window (default 10 min) are surfaced to the brain alongside any
# safety flags stored on their VISITOR_ALERT nudge metadata (Session
# 105 Bug N Part 3). Window chosen to roughly match the natural
# attention span of a follow-up query — if Jagan comes back after 30
# min asking "did anyone visit?", the knowledge graph answers via
# search_memory + the VISITOR_CONTEXT block; the SCENE block's
# recent-visitor section is for within-the-minute context where the
# brain should proactively acknowledge "Lexi just left."
SCENE_VISITOR_RECENCY_SECS    = 600.0
# Wave 6 Item 23: scene_block string cache — avoids redundant string-building
# when consecutive turns have identical scene state (same faces, same speaker).
SCENE_BLOCK_CACHE_ENABLED    = True   # master toggle
SCENE_BLOCK_CACHE_MAX_ENTRIES = 256   # LRU-evict when size reaches this cap

# ── Memory consolidation/pruning (E) ─────────────────────────────────────────
# Hard caps on table row counts — enforced during each autoDream run.
# Rows over the cap are deleted (presence/episodes/mentions) or soft-deleted
# (knowledge rows are invalidated, not hard-deleted, for graph rebuild safety).
CONVERSATION_HISTORY_LIMIT = 100   # turns loaded into LLM context; older turns stay in DB, retrievable via search_memory
# Wave 6 Item 21: conversation log archival
CONVERSATION_ARCHIVE_ENABLED    = True   # move old conversation_log turns to a separate archive DB
CONVERSATION_ARCHIVE_AFTER_DAYS = 30     # archive turns older than this many days
# P0.R12 — conversation_log_archive retention. Archive DB at
# `{db_stem}_conversation_archive.db` accumulates rows after Wave 6 Item 21
# moves them from main conversation_log. Without retention, archive grows
# indefinitely. 1-year default per Q1 (a) RATIFIED — operator-tunable.
CONVERSATION_ARCHIVE_RETENTION_DAYS = 365
KNOWLEDGE_MAX_ROWS                = 2000   # active (non-invalidated) knowledge rows
KNOWLEDGE_HARD_DELETE_ENABLED    = True   # Wave 6 Item 22: hard-delete soft-deleted knowledge rows
KNOWLEDGE_HARD_DELETE_AFTER_DAYS = 60     # conservative 60d buffer (archive cutoff is 30d)
PRESENCE_MAX_ROWS        = 1000   # presence_log rows (oldest pruned first)
EPISODE_MAX_ROWS         = 500    # episodes rows (oldest pruned first)
SOCIAL_MENTIONS_MAX_ROWS = 500    # social_mentions rows (oldest updated_at pruned first)
WATCHDOG_MAX_AGE_DAYS    = 30     # resolved watchdog alerts older than this are deleted
AGENT_LOG_MAX_AGE_DAYS   = 30     # agent_log rows older than this are deleted
AGENT_LOG_MAX_ROWS       = 50_000 # hard cap on agent_log after age-based pruning
PATTERN_Q_MAX_AGE_DAYS   = 7      # asked pattern questions older than this are deleted

# ── autoDream — background memory consolidation (Pattern 4) ──────────────────
# Runs during idle (no active person) to apply decay writes and tidy schema.
# If the system is always busy, DREAM_MAX_INTERVAL forces a run regardless.
DREAM_IDLE_MINUTES         = 5      # minutes of idle before first dream can run
DREAM_COOLDOWN             = 3600   # minimum seconds between dream runs (1 hour)
DREAM_MAX_INTERVAL         = 10800  # force dream even if busy after this many seconds (3 hours)
DAILY_BACKUP_ENABLED       = True   # take daily SQLite snapshots of faces.db + brain.db
SNAPSHOT_RETENTION_DAYS    = 30     # prune snapshots older than this many days
SNAPSHOT_DIR               = "faces/snapshots"  # relative to repo root
WAL_CHECKPOINT_ENABLED     = True   # flush WAL into main DB file at end of each dream cycle
STRANGER_TTL_DAYS          = 7      # delete unidentified strangers unseen for this many days
STRANGER_VOICE_TTL_DAYS    = 3      # prune voice_embeddings of strangers whose voice profile never
                                      # reached N_INITIAL_VOICE samples and hasn't been updated in
                                      # this window — prevents thin profiles from false-matching later.
DISPUTE_MAX_DURATION       = 180    # force-close an identity-disputed session after this many seconds
                                      # without resolution. Without this, vision keeps matching the
                                      # stranger to the wrong pid → last_face_seen never goes stale →
                                      # session can't expire via FACE_LOSS_GRACE.
DISPUTE_RENAME_BLOCK_THRESHOLD = 3   # blocked disputed-rename attempts in one session before the
                                       # watchdog fires DISPUTE_RENAME_BURST. 1 is noise (LLM retry),
                                       # 3 is persistence (IDENTITY DISPUTED has been in the prompt for
                                       # several turns yet the brain keeps trying to rename).
# Session 100 Bug F — enrollment-name rename escape hatch.
# When STT mishears the name at enrollment (2026-04-23 canary: "Jagan" →
# "Gevan"), the speaker's corrective "my name is Jagan" lands on a best_friend
# session whose only corroboration is the face match. The classic
# known/best_friend dispute-flip was the wrong call here — it protects
# against mid-session impersonation, but enrollment-mishear is the common
# case, not the adversarial one. This grace window allows the rename to
# land through the normal stranger-promotion chain (migrate_entity_name +
# graph rebuild) when BOTH conditions hold:
#   - session opened within ENROLLMENT_RENAME_GRACE_SECS ago (fresh session)
#   - DB voice sample count < ENROLLMENT_RENAME_VOICE_THRESHOLD (no voice
#     corroboration yet — face is the ONLY signal that bound pid to name)
# The classifier must have already validated the rename (assign_own_name
# intent, grounded in user_text) — this grace just unblocks the known-type
# dispute-flip that would otherwise trigger.
ENROLLMENT_RENAME_GRACE_SECS       = 600   # 10 min — long enough for a real user to notice
                                            # STT garbled their name at first boot, short
                                            # enough that returning users past mature voice
                                            # profiling don't accidentally qualify.
ENROLLMENT_RENAME_VOICE_THRESHOLD  = 5     # matches N_INITIAL_VOICE: below this, the system
                                            # hasn't accumulated enough voice data to
                                            # independently corroborate the stored name.
DREAM_PRUNE_FLOOR          = 0.15   # effective confidence below this → fact invalidated
DREAM_DECAY_WRITE_THRESHOLD = 0.005 # minimum decay delta to bother writing back

# ── Memory confidence decay (Item 6) ─────────────────────────────────────────
# Non-destructive exponential decay: eff_conf = stored_conf × e^(-λ × days)
# λ=0.002 → half-life ≈ 347 days (a 0.95-confidence fact drops below 0.60 after ~235 days)
# Increase λ to forget faster; decrease to remember longer.
DECAY_LAMBDA           = 0.002

# ── A-MEM retroactive memory evolution (Item 4) ──────────────────────────────
# After a ContradictionAgent REPLACE, retroactively scan related facts for staleness.
MAX_RETROACTIVE_FACTS  = 5     # max LLM calls per REPLACE event (caps cost)
RETRO_STALE_PENALTY    = 0.15  # confidence reduction applied to STALE verdicts

# ── Kuzu graph schema version ─────────────────────────────────────────────────
# Bump this when RELATES_TO schema changes. BrainOrchestrator wipes + rebuilds
# the graph from SQLite when the stored version doesn't match.
GRAPH_SCHEMA_VERSION   = 3   # P0.S7.D-B: bumped v2→v3 to add `privacy_level STRING` to the RELATES_TO edge schema. Forces drop_schema()+_init_schema()+rebuild on DBs at v2. Closes the κ-ship-surfaced active leak where personal-tier `received_*`/`witnessed_*` facts (P0.S7.2) were ingested as graph edges without privacy filter (S107/S112 deferral premise falsified).

# ── Emotion detection (Item 7) ───────────────────────────────────────────────
# Model: j-hartmann/emotion-english-distilroberta-base (CPU-only, ~15-25ms/turn)
# 7 emotions: joy, sadness, anger, fear, disgust, surprise, neutral
EMOTION_ENABLED             = True
EMOTION_WINDOW              = 5     # rolling turns per person (was 3 — larger window is more stable)
EMOTION_MIN_SCORE           = 0.40  # minimum confidence to surface a non-neutral emotion
EMOTION_FACT_VALIDITY_HOURS = 4.0   # how long a detected emotion persists as a stored fact
EMOTION_WINDOW_TTL_SECS     = 90    # entries older than this are excluded from dominant-emotion calc

# ── SORT face tracking (Item 8) ──────────────────────────────────────────────
# Detect every Nth frame (neural net), predict in between (Kalman filter).
# ~80% GPU reduction on detection; accurate for ≤10 simultaneous faces.
SORT_DETECT_EVERY      = 5     # run RetinaFace every Nth frame
SORT_MAX_AGE           = 30    # frames to keep a track alive without a detection match (1s @ 30fps)
SORT_MIN_HITS          = 2     # detections required before a track is confirmed

# ── P0.R2 D4: Vision provider state machine (CUDA ↔ CPU fallback) ─────────────
# After a CUDA failure triggers `record_cuda_failure()`, the active provider
# switches to CPU. Two restoration triggers (counter-OR-timer, whichever first):
VISION_CPU_SWITCH_N_REQUESTS = 100   # restore CUDA after N successful CPU inferences
VISION_CUDA_RETRY_M_MINUTES  = 5.0   # restore CUDA after M minutes elapsed since failure

# ── P0.R3 D2: Vision-loop watchdog (heartbeat + supervised restart) ───────────
# Watchdog polls vision-loop heartbeat at INTERVAL_SECS; if heartbeat staleness
# exceeds STALE_THRESHOLD_SECS, the watchdog cancels the vision task + respawns
# a fresh one. Restart success is detected by heartbeat advancing past pre-restart
# value within RESTART_TIMEOUT_SECS; timeout OR exception → vision_degraded flag.
VISION_WATCHDOG_INTERVAL_SECS         = 5.0    # watchdog polls every N seconds
VISION_WATCHDOG_STALE_THRESHOLD_SECS  = 30.0   # heartbeat older than M secs → stale
VISION_WATCHDOG_RESTART_TIMEOUT_SECS  = 30.0   # restart-success deadline

# P0.R8 — heavy-worker pool watchdog + burst-limit constants. The watchdog
# at pipeline._heavy_worker_watchdog_loop polls every WATCHDOG_INTERVAL_SECS;
# for each of the 4 pools (AdaFace/Whisper/ECAPA/Pyannote), if BURST_THRESHOLD
# crashes occur within BURST_WINDOW_SECS rolling window, the pool is marked
# "degraded" + a WatchdogAgent alert fires. Recovery is implicit:
# ProcessPoolExecutor auto-respawns subprocesses on next submit; when the
# rolling crash count drops below threshold, the pool re-arms + clears
# degraded automatically.
HEAVY_WORKER_WATCHDOG_INTERVAL_SECS    = 5.0    # poll cadence (matches P0.R3)
HEAVY_WORKER_RESTART_BURST_THRESHOLD   = 3      # N crashes in window → degraded
HEAVY_WORKER_RESTART_BURST_WINDOW_SECS = 300.0  # 5 minute rolling window

# ── Heavy-worker VRAM budget guard (P0.R9) ───────────────────────────────────
# Static per-pool VRAM estimates + cumulative cap at VRAM_CEILING_PCT of
# available CUDA memory + priority order determining which pools refuse spawn
# on budget exhaustion. Q5 (a) lock: skip enforcement on non-CUDA dev/CI
# environments (see core/heavy_worker.py::check_vram_budget). Tune estimates +
# ceiling + priority based on production canary signal; restart to re-evaluate.
HEAVY_WORKER_VRAM_ESTIMATES_MB = {
    "adaface_embed":      100,
    "ecapa_embed":        200,
    "whisper_transcribe": 3000,
    "pyannote_diarize":   3000,
}
VRAM_CEILING_PCT = 80.0  # cap at 80% of available CUDA memory
VRAM_POOL_PRIORITY = [
    "adaface_embed",      # highest priority — face recognition is core
    "ecapa_embed",        # voice ID for greeting
    "whisper_transcribe", # STT (could degrade to other STT)
    "pyannote_diarize",   # lowest — has ECAPA-valley fallback
]

# ── Audio device failure resilience (P0.R10) ─────────────────────────────────
# Per-channel burst detection for mic + speaker device failures. Q1 (a) lock:
# per-channel counter granularity (mic + speaker tracked independently \u2014 USB
# mic disconnect != speaker driver crash). Q7 (a) lock: moderate defaults
# (3 failures in 60s); operator-tunable per environment.
AUDIO_DEVICE_WATCHDOG_INTERVAL_SECS = 10.0  # poll cadence
AUDIO_DEVICE_BURST_THRESHOLD        = 3     # N failures in window → degraded
AUDIO_DEVICE_BURST_WINDOW_SECS      = 60.0  # 1 minute rolling window

# ── Crash diagnostic capture (P0.R11) ────────────────────────────────────────
# persist_crash_diagnostic writes JSON-per-crash to faces/crash_logs/;
# prune_old_crash_logs removes files older than RETENTION_DAYS via dream-loop
# cleanup. HealthSnapshot.recent_crash_logs surfaces up to RECENT_LIMIT entries
# for dashboard visibility.
CRASH_LOG_RETENTION_DAYS         = 7      # files older than N days pruned at dream loop
HEALTH_CRASH_LOG_RECENT_LIMIT    = 10     # HealthSnapshot.recent_crash_logs cap
CRASH_LOG_SCHEMA_VERSION         = 1      # JSON payload schema version (mirror of core.crash_logs._CRASH_LOG_SCHEMA_VERSION)

# ── Semantic embeddings (Phase 3) ─────────────────────────────────────────────
# Model: intfloat/multilingual-e5-large-instruct (1024-dim, multilingual)
# Instruction format: "Instruction: represent the {purpose} for retrieval: {text}"
EMBED_DIM             = 1024   # multilingual-e5-large-instruct output dimension
EMBED_TOP_K           = 10     # top-K facts returned by semantic_search_knowledge
EMBED_MIN_CONFIDENCE  = 0.60   # facts below this confidence are excluded from context

# ── KAIROS — proactive conversation tick (Pattern 7) ─────────────────────────
# Robot breaks silence proactively using a pending PatternAgent question.
# Only fires when a known person is in active session and has been silent.
# P0.S7.3 — silence countdown begins from max(last_user_speech_at, _tts_end_time),
# so brain-speaking time doesn't accumulate as "silence." 120s (2 min) gives the
# user comfortable breathing room after a brain response before KAIROS proactively
# re-engages. Adjustable per user preference.
KAIROS_SILENCE_THRESHOLD_SECS: float = 120.0   # seconds of user silence before KAIROS fires
KAIROS_COOLDOWN          = 120.0  # minimum seconds between proactive initiations
# Session 112 Part 2 — room-aware KAIROS speaker selection. When
# multiple people are active and the best_friend is one of them,
# KAIROS fires for the best_friend rather than the most-recent
# speaker. Rationale: the owner is the most natural engagement target
# for proactive content (household context, cross-person insights).
# In owner-absent multi-person scenes, the selector falls back to the
# person with the longest individual silence (not the most-recent
# speaker — they just spoke). Toggle lets rollback revert to
# _primary_person_id() behavior without code churn.
KAIROS_PREFER_BEST_FRIEND = True

# ── Object Pattern Analysis ───────────────────────────────────────────────────
# Analyzes sighting statistics to find interesting behavioral patterns and
# generates proactive questions the robot asks naturally during conversation.
PATTERN_MIN_SIGHTINGS  = 30    # minimum total sightings before running analysis
PATTERN_COOLDOWN       = 3600  # seconds between analysis runs (1 hour)
PATTERN_MAX_QUESTIONS  = 5     # max pending questions stored at once
PATTERN_ANALYSIS_DAYS  = 7     # days of sighting history fed to LLM
PATTERN_MIN_CONF       = 0.70  # minimum confidence to store a pattern question

# ── Spatial Memory Vision ────────────────────────────────────────────────────
# YOLO11 nano object detection — runs every Nth frame, stores sightings in brain.db.
# Model auto-downloads from Ultralytics HuggingFace on first run (~6MB for nano).
VISION_YOLO_ENABLED  = False          # set True when ready to use spatial memory
VISION_YOLO_MODEL    = "yolo11s.pt"   # small: 41.2% mAP vs nano's 37.3%; ~21MB vs 6MB
VISION_DETECT_EVERY  = 15             # run YOLO every Nth frame (~2fps at 30fps camera)
VISION_DETECT_CONF   = 0.40           # minimum YOLO confidence to store a sighting
VISION_SIGHTING_GAP  = 60             # seconds: skip re-storing same object in same zone
VISION_MAX_SIGHTINGS = 5000           # max rows in object_sightings before pruning oldest

# ── Dashboard API ─────────────────────────────────────────────────────────────
# Pipeline writes state here — dashboard reads it
STATE_FILE             = ROOT / "faces" / "state.json"
ENROLL_REQUEST_FILE    = ROOT / "faces" / "enroll_request.json"
ENROLL_RESULT_FILE     = ROOT / "faces" / "enroll_result.json"
RESET_REQUEST_FILE     = ROOT / "faces" / "reset_request.json"
RESET_RESULT_FILE      = ROOT / "faces" / "reset_result.json"

# ── Briefing agent ────────────────────────────────────────────────────────────
# Best friend must be absent this long before a spoken briefing fires on return.
BRIEFING_MIN_ABSENCE = 1800   # 30 minutes

# ── ConversationInsightAgent (Phase 4.2) ──────────────────────────────────────
INSIGHT_MIN_TURNS         = 3      # skip episode generation for very short sessions
INSIGHT_MAX_TOKENS        = 300    # LLM output cap for episode JSON
EPISODE_TOPIC_MATCH_DAYS  = 30     # lookback window for cross-person topic matching

# ── RoutineAgent (Phase 4.3) ──────────────────────────────────────────────────
MIN_PRESENCE_SESSIONS     = 5      # sessions required before pattern detection
ROUTINE_STD_THRESHOLD     = 2.0   # std-dev hours; above = unstable pattern
PRESENCE_DEVIATION_HOURS  = 2.0   # hours past typical arrival = late alert

# ── ProactiveNudgeAgent (Phase 4.4) ───────────────────────────────────────────
NUDGE_MIN_CONFIDENCE      = 0.40   # minimum score to persist a nudge
NUDGE_FUZZY_MATCH_RATIO   = 80     # rapidfuzz threshold for name similarity
NUDGE_EXPIRY_HOURS        = 72.0   # hours before an unshown nudge expires
CROSS_PERSON_MAX_NUDGES   = 3      # max pending cross-person nudges per person

# ── WatchdogAgent (Phase 4.5) ─────────────────────────────────────────────────
WATCHDOG_INTERVAL          = 60.0  # seconds between watchdog check passes
WATCHDOG_SILENT_OBS_SPIKE  = 5     # new silent obs in one interval = anomaly
WATCHDOG_UNUSUAL_HOUR_START = 0    # hours (0–5 inclusive) considered unusual
WATCHDOG_UNUSUAL_HOUR_END   = 5

# ── Identity resolution thresholds ────────────────────────────────────────────
# When a stranger's conversation matches a person the best friend mentioned:
IDENTITY_SOFT_THRESHOLD = 0.35   # inject soft hint into LLM context only
IDENTITY_ASK_THRESHOLD  = 0.65   # system asks "are you X?" naturally
IDENTITY_AUTO_THRESHOLD = 0.85   # auto-confirm: update name without asking

# ── Silent observation ────────────────────────────────────────────────────────
# Faces seen but never engaged (no system name spoken).
# Stored as SilentObservation rows — NOT person records.
SILENT_OBS_SIMILARITY   = 0.82   # cosine sim above this = same silent visitor → update row
SILENT_OBS_RETENTION_DAYS = 45   # days before pruning old observations
SILENT_OBS_SCAN_DAYS    = 7    # look back this many days when matching; must be < RETENTION_DAYS

# ── Enroll intent keywords ────────────────────────────────────────────────────
ENROLL_KEYWORDS = [
    "enroll", "add me", "remember me", "register me",
    "add to system", "save me", "learn my face",
    "who am i", "don't know me", "new person"
]

# ── Tool calling reliability ───────────────────────────────────────────────────
# Layer 1: Action tools whose LLM-generated response text must be replaced with
# a canonical acknowledgment in conversation history when the tool succeeds.
# Prevents wrong streaming text ("Sorry, I missed that") from poisoning history
# and triggering infinite repeat loops on the next turn.
HISTORY_OVERRIDE_TOOLS: frozenset = frozenset({
    "update_system_name",
    "update_person_name",
})

# Layer 3: Max consecutive identical (tool_name, args_hash) executions allowed
# before the repeat guard fires and aborts the call. Prevents infinite loops
# where the LLM keeps calling the same tool with the same args with no progress.
TOOL_REPEAT_MAX_CONSECUTIVE: int = 2

# ── P0.8: Per-tool execution timeouts ──────────────────────────────────────
# Default wall-clock budget for any tool handler.  Layer 0 / privilege /
# repeat-guard gates run OUTSIDE this budget (they're micro-operations).
# Asymmetric overrides accommodate tools that legitimately exceed the
# default (network round-trips for search_web; faster pure-SQL for
# search_memory; small fixed deadlines for control-flow tools).
#
# On timeout, _execute_tool returns "tool_timeout" — distinct from existing
# handled/handled_noop/rejected/unknown/None taxonomy.  asyncio.wait_for
# cancels the handler task, which propagates CancelledError through
# transaction __aexit__ (FaceDB.transaction / BrainDB._safe_commit) — partial
# SQL writes are rolled back. Behavioral test enforces this.
TOOL_TIMEOUT_SECS: float = 10.0
TOOL_TIMEOUT_OVERRIDES: "dict[str, float]" = {
    "search_web":              20.0,   # Tavily multi-query + retries
    "search_memory":            5.0,   # local SQLite read; fast
    "update_person_name":       5.0,
    "update_system_name":       5.0,
    "shutdown":                 3.0,
    "report_identity_mismatch": 3.0,
}

# ── Health summary log (Wave 5 / Item 19) ──────────────────────────────────
HEALTH_LOG_ENABLED          = True
HEALTH_LOG_INTERVAL_SECS    = 300   # 5 min — first log fires immediately at boot
HEALTH_THIN_VOICE_MAX       = 3     # cap thin-gallery [Health-Alert] lines to avoid log spam

# ── terminal_output.md size cap + archive retention (P0.R13) ────────────────
# `_check_terminal_output_size_cap` rotates the file when size exceeds cap;
# `_prune_old_terminal_archives` removes archive files older than retention.
# Q2 (a) RATIFIED: 100 MB cap is generous; rotation is non-destructive
# (renames to timestamped archive matching startup archive shape).
# Q3 (a) RATIFIED: 30 day archive retention matches canary-feedback window.
# Q4 (a) RATIFIED: integrated into disk-monitor poll cadence (~5 min).
TERMINAL_OUTPUT_SIZE_CAP_MB            = 100
TERMINAL_OUTPUT_ARCHIVE_RETENTION_DAYS = 30

# ── Disk space monitor (Wave 5 / Item 20) ──────────────────────────────────
# Single-volume assumption: all monitored dirs must live on the same filesystem
# as root_path. If KaraOS ever spans volumes, only the root's volume is monitored.
DISK_MONITOR_ENABLED        = True
DISK_ALERT_WARNING_PCT      = 80    # first threshold: warning severity
DISK_ALERT_CRITICAL_PCT     = 90    # second threshold: critical severity
DISK_ALERT_BLOCKER_PCT      = 95    # third threshold: critical/blocker — operator must act
DISK_MONITORED_DIRS         = ["faces/", "data/", "faces/snapshots/", "faces/brain_graph/"]

