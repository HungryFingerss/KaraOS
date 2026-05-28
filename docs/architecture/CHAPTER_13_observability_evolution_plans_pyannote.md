> **CHAPTER 13 — Observability 2.0 + Evolution Plans + Pyannote** | Sourced from `everything_about_system.md` §177-197 (verbatim mechanical extraction per Plan v2 §1.6 section-number stability invariant).

---

## 177. Enrollment Mishear Candidate Gate

### 177.1 The issue

Progressive Enrollment accepts name-reveal turns as promotion triggers. In multi-person rooms, a stranger's name reveal could be mis-heard as a different name, and the gate would accept. Session 112 canary: Lexi says "I'm Lexi", Whisper transcribes "I'm Leigh", stranger gets promoted to "Leigh".

### 177.2 The fix — `_is_enrollment_mishear_candidate`

A predicate that checks whether the claimed name is likely a mishear of an already-known participant's name. Inputs: DB handle, the claimed name, the current session dict. Uses (a) phonetic distance (jellyfish Double Metaphone) and (b) exact-match against all current-room `person_name`s.

When the predicate returns True, `conversation_turn` takes one of three remediation intents:

- **Ask-to-confirm.** TTS: "I heard Leigh — did you mean Lexi, or someone new?"
- **Prefer known name.** Silent rename to the matched known name.
- **Reject promotion, keep stranger.** Wait for a second turn with clearer phonetics.

The default is the first (ask-to-confirm) — matches the HEDGED NAMING CONTRACT's overall philosophy of verbalising uncertainty rather than committing to a guess.

## 178. Turn-Dispatch Addressee Logging

Detailed in Part XXVIII §179. The `[Pipeline] Turn addressed: X (source)` signature is what the pre-3B work left as its observability legacy. Without the log line, the arbitration rules would have no measurable signal.

---
---

# Part XXVIII — Observability 2.0

Session 113.1 was a pure observability round after the Pre-3B work and the 3B.1–3B.6 rollout. No functional changes; only log lines. But the signal-to-noise of the runtime logs matters enormously for diagnosing live canaries, so each addition was thought through.

## 179. The `[Pipeline] Turn addressed` Signature

Format: `[Pipeline] Turn addressed: <name> (<source>)` where source ∈ `{llm, default, fallback}`.

- **`llm`** — the brain emitted `[addressing:X]` and X is the addressee. The arbitration rules are firing.
- **`default`** — no marker; current speaker's name is the addressee. Single-person rooms; multi-person rooms without arbitration redirection.
- **`fallback`** — person_name was missing; pid used. Defensive path — should not appear in healthy logs.

## 180. The `[Room]` Log Category

New category signalling room lifecycle events:

- `[Room] New room session: room_<ts>_<hex>` on mint.
- `[Room] Participant added: <name> (n_participants=2)` on second+ session open.
- `[Room] Ended: room_<ts>_<hex> — 4 participants, 18 turns` on `_on_room_end`.
- `[Room] Synthesis complete: room_<ts>_<hex> — topic_tags=[...], safety_flags=[...]` after `synthesize_room` writes.

## 181. Richer Voice-Routing Logs

The `[Voice] Routing:` prefix survives from earlier but now renders detailed diagnostics: reason, scores on the compared priorities, and — for the multi-speaker short-utterance cases — the P3.23 tier (hard/ambiguous/trusted).

Examples:

```
[Voice] Routing: current (thin stranger 3/5, offscreen floor skipped, score=0.312)
[Voice] Routing: short_utterance_voice_mismatch (v_score=0.14, hard-floor 0.20 — drop)
[Voice] Routing: short_utterance_voice_mismatch (v_score=0.36, ambiguous + n=2 — drop)
[Voice] Routing: switch_enrolled → jagan_905848 (score=0.617, priority 1)
```

## 182. The `[Intent]` Log Category

From Phase 1. Every gated-tool turn emits:

```
[Intent] tools=['update_person_name'] classified=assign_own_name value='Lexi' conf=0.95 reason=explicit first-person introduction
[Intent] divergence: allow
```

The two lines together give a single-turn view of (a) what the classifier decided and (b) whether the gate allowed it. Phase 5's drift detection consumes this.

## 183. Terminal Output Archival Hook

Added in Session 81. On pipeline startup, `_archive_terminal_output()` renames existing `terminal_output.md` to `terminal_output_YYYY-MM-DD_HHMMSS.md` (mtime-based). New session writes fresh; no data is lost. The archive feeds the golden-set harvest (`tests/harvest_golden.py`).

---
---

# Part XXIX — Phase 4 Placeholder — Implicit Intent (NOT YET IMPLEMENTED)

> **Status.** Planned but not yet shipped. This section exists so the blueprint has a home for Phase 4 when it lands. All content below comes from `VISION_ROADMAP.md` §4 and should be treated as **design intent**, not implementation docs.

## 184. Motivation

Phase 1 extracts **explicit** intent (the user said they want a rename). Phase 4 targets **implicit** intent — the subtext underneath the surface text.

Examples of implicit signals:

- User says "I've been thinking" → they want meaningful conversation, not a direct answer.
- User says "it's fine, I guess" → the qualifier carries the real meaning; they're not fine.
- User pauses 3 seconds before responding → hesitation signal (non-verbal).
- Tone mismatch (emotion classifier disagrees with textual sentiment) → internal conflict.

The research backing: Chain-of-Thought prompting plus emotion and knowledge-discourse graphs let LLMs reason over implicit signals without a dedicated classifier agent.

## 185. Planned Architecture

### 185.1 The `<<<IMPLICIT SIGNALS>>>` block

A new always-on prompt block added to `_build_system_prompt`, gated by `IMPLICIT_SIGNALS_BLOCK_ENABLED=True`. Teaches the brain to read hedges ("sort of", "maybe"), qualifiers ("it's fine, BUT"), deflection ("let's not talk about that"), meta-questions ("you know?"), long pauses, and tone mismatch — with the instruction *"prefer asking a follow-up that acknowledges the subtext over giving a direct answer. Don't call it out explicitly."*

### 185.2 The `<<<NON-VERBAL CONTEXT>>>` block (dynamic per turn)

Renders per-turn when non-default signals exist:

```
<<<NON-VERBAL CONTEXT>>>
PAUSE_BEFORE_SPEAKING: 3.7s   (2-5s = contemplating)
SPEECH_RATE: 1.4 wps           (<1.5 = thoughtful)
EMOTION_DOMINANT: sadness (71%)
EMOTION_TREND: rising stress
<<<END NON-VERBAL CONTEXT>>>
```

Three signals: pause-before-speaking, speech-rate (words per second from Whisper duration), and emotion trend (rolling 3-turn window diff on dominant-emotion score).

## 186. Planned Data Capture

### 186.1 `last_pause_secs`

Measure from `tts_end_time` (last TTS finish) to user's next `speech_start_time`. Store on the session dict.

### 186.2 `last_speech_rate`

Whisper returns transcript + duration. `len(text.split()) / duration`. Store per turn.

### 186.3 `emotion_trend`

Extend `EmotionAgent` with an `emotion_trend()` method returning `"rising <emotion>"`, `"calming"`, or `"stable"` based on a 3-point window on dominant-emotion score.

## 187. Task List (From VISION_ROADMAP §4.4)

- [ ] P4.1 Add `<<<IMPLICIT SIGNALS>>>` block + gate.
- [ ] P4.2 Track `last_pause_secs` in session dict.
- [ ] P4.3 Track `last_speech_rate`.
- [ ] P4.4 Add `emotion_trend()` method on EmotionAgent.
- [ ] P4.5 Build `<<<NON-VERBAL CONTEXT>>>` from session + EmotionAgent.
- [ ] P4.6 Inject only when signals are meaningfully non-default (avoid prompt bloat).
- [ ] P4.7 Curate 20 test cases `(user_text, pause_secs, emotion, expected_response_tone)`.
- [ ] P4.8 `test_implicit_intent.py` — runs each case, asserts response tone matches (LLM-judge or manual review).
- [ ] P4.9 3 live sessions with varied emotional content; manual review of 20 turns.

### Phase 4 exit criteria

- 20-case eval ≥70% match.
- No regression on existing tests.
- User reports system "feels more present" (subjective but documented).

---
---

# Part XXX — Phase 5 Placeholder — Continuous Evaluation (NOT YET IMPLEMENTED)

> **Status.** Ongoing once Phase 4 lands; no dedicated ship date. Phase 5 is a set of rituals rather than a code delivery. This section describes the planned shape.

## 188. Motivation

LLM systems drift:

- Providers update models silently.
- Users evolve phrasings.
- New bug classes surface with every live run.

Without continuous evaluation, drift is invisible until a live failure. The golden set + weekly ritual + shadow sample together keep the system honest.

## 189. Golden Set as Living Artifact

`tests/golden_intent.jsonl` (Phase 1) and `tests/golden_implicit.jsonl` (Phase 4) are append-only regression sets.

Rules:

- Every live-run bug → new row.
- Rows never deleted; only marked `"active": false` if superseded.
- Quarterly re-label drift check: random 20 rows re-labeled by fresh review; if labels disagree, golden truth itself needs updating.

The source taxonomy (`real_observed`, `adversarial`, `synthetic_common`, `regression_<session>`, `legacy_synthetic`) already lives in CLAUDE.md § Golden Intent Set. The rule for `synthetic_common` → `legacy_synthetic` transition (≥25 `real_observed` rows per intent) is the anti-cheat: without it, synthetic pairs could silently prop up metrics after real data is available.

## 190. Divergence Monitoring Table

`brain.db.intent_divergences` table (shipped in Phase 1.7a):

```sql
CREATE TABLE intent_divergences (
    id INTEGER PRIMARY KEY,
    turn_id INTEGER,
    person_id TEXT,
    user_text TEXT,
    structured_intent TEXT,
    structured_extracted TEXT,
    structured_confidence REAL,
    tool_proposed TEXT,
    gate_decision TEXT,   -- 'allow' | 'reject: <reason>' | 'regex_fallback_allow' | ...
    reviewed INTEGER DEFAULT 0,
    ts TEXT
);
```

Every gated-tool turn writes a row. Phase 5 queries this table for drift signals: top 20 lowest-confidence decisions in the last 7 days, top 20 rejected decisions (false-reject review), per-intent precision trend.

## 191. Weekly Review Ritual

Planned CLI: `python eval_weekly.py`. Outputs markdown:

- Top 20 lowest-confidence decisions from last 7 days.
- Top 20 rejected decisions.
- Golden-set re-run — precision/recall/ECE trend line.
- Flags for drift: "intent X precision dropped from 0.96 → 0.91 this week."

Plus a quarterly variant (`python eval_quarterly.py`) that does the random-20-relabel drift check on the golden set itself.

## 192. Canary Shadow Sample

1% of gated-tool turns run a second classifier in parallel (a "shadow" classifier — could be the same prompt at a different model, or an IntentAgent alternative). Divergences logged. If the shadow > main divergence ever crosses 5% for a full week, review for drift.

`SHADOW_SAMPLE_RATE = 0.01` in config. The sampling decision is made at classifier call time, deterministic per-turn-id.

## 193. Task List (From VISION_ROADMAP §5.3)

- [ ] P5.1 Write `eval_weekly.py` — queries divergence table, runs golden set, prints markdown.
- [ ] P5.2 Write `tests/golden_set_drift.py` — quarterly drift check harness.
- [ ] P5.3 Add `SHADOW_SAMPLE_RATE=0.01` config.
- [ ] P5.4 Document rituals in CLAUDE.md (weekly and quarterly, exact commands).
- [ ] P5.5 Automated alert: if weekly golden-set precision drops >5pp, fail CI.

### Phase 5 exit criteria

Phase 5 is ongoing — no "exit". But healthy steady-state:

- Weekly review produces ≤3 action items.
- Golden-set precision stable (within ±2 pp) month-over-month.
- No unreviewed divergence rows older than 30 days.

---
---

# Part XXXI — Pyannote Dependency Maintenance

## 194. Why the Patches Exist

Phase 2 wired `pyannote.audio==3.3.2` as the diarization backend (§33). torch 2.9+ removed several legacy torchaudio audio-backend APIs (`set_audio_backend`, `list_audio_backends`, `AudioMetaData`); torch 2.6+ flipped `torch.load`'s default `weights_only=True`; huggingface_hub renamed `use_auth_token` → `token`. pyannote 3.x predates all three and its upstream compat release is stuck in review.

Production torch is **2.10** (load-bearing for faster-whisper STT + SpeechBrain ECAPA-TDNN); downgrading torch is forbidden per Session 88 reviewer call — "fighting the ecosystem cascades". pyannote 4.0.x is torchcodec-native but torchcodec 0.11.1 is itself incompatible with torch 2.10 AND requires FFmpeg on Windows.

File-level patches are the community-validated workaround (same pattern used in whisper-webui Docker images).

## 195. Patched Files

| File | Patch | Reason |
|---|---|---|
| `pyannote/audio/core/io.py` | `-> torchaudio.AudioMetaData:` → `-> object:` | Type annotation only; class removed in torchaudio 2.9 |
| `pyannote/audio/core/io.py` | `torchaudio.list_audio_backends()` → `getattr(..., lambda: ['sox_io'])()` | API removed; our audio path is in-memory tensors, not file I/O |
| `pyannote/audio/core/pipeline.py` | `use_auth_token=use_auth_token,` → `token=use_auth_token,` | huggingface_hub kwarg rename |
| `pyannote/audio/core/inference.py` | same kwarg rename | same reason |
| `pyannote/audio/core/model.py` | same kwarg rename × 2 sites | same reason |
| `pyannote/audio/core/model.py` | add `weights_only=False` to `pl_load(...)` + `Klass.load_from_checkpoint(...)` | torch 2.6+ default flip; pyannote checkpoints are HF-gated + license-signed |
| `pyannote/audio/tasks/segmentation/mixins.py` | `from torchaudio import AudioMetaData` → try/except stub | Import must not crash; stub is only hit on training path |
| `pyannote/audio/utils/protocol.py` | same `list_audio_backends()` fallback as io.py | Same cause, different file |
| `speechbrain/utils/torch_audio_backend.py` | same `list_audio_backends()` fallback | SpeechBrain imports torchaudio through pyannote |

## 196. Reapplication Workflow

```
python tests/patch_pyannote_io.py
```

Idempotent — second+ runs write nothing. Re-verify with `python -c "from pyannote.audio import Pipeline; print('ok')"` plus a live-model smoke test. **Mandatory after any `pip install pyannote.audio`** — a library upgrade restores the unpatched source.

## 197. Deprecation Plan

When pyannote 4.x ships a stable torchcodec-native release WITH torchcodec providing torch 2.10+ wheels AND Windows FFmpeg packaging:

- Pin the new version.
- Delete `tests/patch_pyannote_io.py`.
- Remove this Part.

Track via GitHub issue #1974 on pyannote-audio.

**Alternative if patches ever break beyond shim-ability.** SpeechBrain's built-in diarization recipe — already in venv for ECAPA-TDNN. Spectral-clustering, not end-to-end pre-trained like pyannote. Trade-off: ~2–3pp higher DER, cleaner dep surface.

---

# Part XXXII — Voice/Vision Independence and the Reconciler (Phases 1–4)

