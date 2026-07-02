# Spec (DRAFT) — Canary #3 fix: ECAPA subprocess embed + rename safety

**Status:** WORKING DRAFT for the auditor. This is the **first golden-test-first cycle**
(per the 2026-05-30 directive): the two golden tests in §2 are written RED first by the
developer, confirmed to reproduce the canary, and only then is the fix in §4 implemented
to turn them GREEN.

**Surfaced by:** live canary 2026-05-30 (`terminal_output.md`, 1034 lines). The system
renamed Jagan → Lexi when Lexi (an ElevenLabs voice, never on camera) said "Hi Kara, my
name is Lexi." Jagan's identity + 19 brain.db rows were corrupted (line 781).

**Confirmed root cause (two coupled bugs, one trigger):**
1. **Part A — `voice.embed` returns None on every call.** Confirmed by the Phase A
   instrumentation: every turn logged `[Voice] accum path … face_witness` →
   `[Voice] accum skip … embed returned None`. The ECAPA subprocess loader
   `core/heavy_worker.py::_get_subprocess_ecapa` (line 495) calls
   `EncoderClassifier.from_hparams(...)` **without** the `hf_hub_download` compatibility
   patch that the main-process loader `core/voice.py::load_speaker_embedder` applies
   (voice.py:73-95: strip `use_auth_token` + convert huggingface_hub-1.x 404 →
   `ValueError`, in both the global and `speechbrain.utils.fetching` namespaces).
   SpeechBrain 1.0.3 cannot load without that patch → `from_hparams` raises → swallowed
   silently at heavy_worker.py:500 → returns None → embed returns None → voice gallery
   never fills (`voice_n=0` forever). **Introduced by P0.R6.Y** (the ECAPA→subprocess
   migration in the `eeb8855` batch, ~2026-05-24): the migration carried the inference
   code into the subprocess but left the compatibility patch behind in the main loader.
2. **Part B — the enrollment-mishear gate renamed a 55-turn best_friend.**
   `pipeline.py::_is_enrollment_mishear_candidate` (line 592) returns True on only two
   checks: session age < `ENROLLMENT_RENAME_GRACE_SECS` (600s) AND
   `voice_n < ENROLLMENT_RENAME_VOICE_THRESHOLD` (5). At canary turn 55 BOTH were
   incidentally true — the conversation was ~6 min old, and `voice_n=0` because of
   Part A. So Lexi's "my name is Lexi" (mis-attributed to Jagan's active session,
   because the empty gallery can't tell the voices apart) flowed through the
   enrollment-mishear escape hatch and renamed Jagan instead of disputing. Neither
   check asks the real question: *is this still the enrollment moment?* A 55-turn
   established conversation is not.

**Why it was invisible for a week** (this is the directive, demonstrated): no live
canary in the deferred window (May 19–30); the 3795 tests MOCK `voice.embed` so a real
subprocess failure stayed green; the boot "warmup" only proves the subprocess SPAWNS,
not that embed returns a value; and the silent swallows at heavy_worker.py:500 + 564
erased the evidence. A behavioral test running the real subprocess (GT1 below) would
have gone red the day the migration landed.

---

## §1 — Scope

Two parts, both fixing this canary, reviewed together:
- **Part A** — restore ECAPA embedding (the root cause; fills the gallery, dissolves the
  whole cascade).
- **Part B** — harden the enrollment-mishear gate (defense-in-depth; a best_friend must
  not be renamed by a voice-only claim during an established conversation, even in the
  pre-gallery window).

Out of scope (operational, user-owned): repairing the already-corrupted Jagan→Lexi DB
state (line 781) — a factory reset or manual rename-back before the next canary.

---

## §2 — Golden tests (write RED first, before any fix)

Developer step 1 is to write these and confirm they are RED against current code
(reproducing the canary). They become the permanent regression guard.

### GT1 — the ECAPA subprocess actually returns an embedding

Behavioral, runs the REAL subprocess path (not a mock):
```
emb = await voice.embed(<real-length mono float32 audio, >= 1.5s>)
assert emb is not None
assert emb.shape == (192,)   # real ECAPA embedding, not None
```
RED now: returns None (subprocess load fails on `use_auth_token`). GREEN after Part A.
**This is the test whose absence let the break hide for a week.**

- Hardware-gated like the P0.R5 anchors: skip when CUDA / the SpeechBrain model is
  unavailable (CI without GPU), so it runs where the hardware is — the dev box and the
  canary host. (Q2: also add a lighter unit test that the subprocess loader *calls* the
  shared patch helper, so CI has a guard even without GPU.)

### GT1b — accumulation grows the gallery end-to-end (higher-level companion)

Drive `_accumulate_voice` with a face-witnessed session + real ≥1.5s audio and assert
`db.voice_embedding_count(pid)` increases by 1 (and `[Voice] Profile updated` is the
outcome, not `embed returned None`). RED now, GREEN after Part A. This is the
"voice accumulates over a conversation" guard.

### GT2 — a voice-only name claim does NOT rename an established best_friend

Behavioral, against the real gate:
```
session = <best_friend session, user_turns = 50, started recently, voice_n = 0>
assert _is_enrollment_mishear_candidate(db, pid, session) is False
# → the rename routes to the dispute-flip path, NOT update_person_name
```
Plus an end-to-end assertion that a grounded "my name is Lexi" on that 50-turn
best_friend session does NOT migrate the person's name/rows. RED now (returns True →
renames, the exact canary corruption). GREEN after Part B. **This is the guard that
would have caught the Jagan→Lexi corruption before it shipped.**

---

## §3 — D-decisions

### Part A — restore ECAPA embedding

- **A1** — extract the `hf_hub_download` compatibility patch (currently inline in
  `load_speaker_embedder`, voice.py:73-95) into a SHARED helper that applies it
  idempotently (both the global `huggingface_hub.hf_hub_download` AND
  `speechbrain.utils.fetching.hf_hub_download`, including the 404→ValueError conversion).
  Call it from BOTH `load_speaker_embedder` (main) AND `_get_subprocess_ecapa`
  (subprocess) immediately before `EncoderClassifier.from_hparams`. One source of truth;
  the subprocess gets the identical patch. (Q1: placement so the subprocess import stays
  light — a small standalone function, not a heavy module import.)
- **A2** — make the two silent swallows visible: `_get_subprocess_ecapa` line 500 and
  `ecapa_embed_worker` line 564 must LOG the exception (type + message) before returning
  None — the "never silent except / always log" doctrine. These are exactly the swallows
  that hid this bug; they must never hide it again. (The main loader at voice.py:105
  already logs a WARNING; the subprocess sites do not.)

### Part B — harden the enrollment-mishear gate

- **B1** — add a turn-count condition to `_is_enrollment_mishear_candidate`:
  `session.user_turns <= ENROLLMENT_RENAME_MAX_TURNS` (new config constant). The
  enrollment-mishear escape hatch only fires in the genuine first-few-turns enrollment
  window; an established multi-turn conversation routes any rename claim to the
  dispute-flip path (which protects a known/best_friend identity). At the canary's
  turn 55 this is far past the window → no rename. (Q3: value — lean **3**.)
- **B2** — new config `ENROLLMENT_RENAME_MAX_TURNS` with a comment naming the canary
  (2026-05-30 Jagan→Lexi).

Rationale for turn-count over a vision check (Q4): vision had Jagan on camera the whole
time, but a *genuine* enrollment-mishear (Jagan correcting "Gevan"→"Jagan" at turn 1)
ALSO has his face on camera — so face-presence doesn't distinguish the two. The
distinguisher is that a mishear correction happens in the first turns, while the name is
fresh; by turn 55 the name has been used 50+ times without correction. Turn-count is the
principled signal. (Note: once Part A fills the gallery, `voice_n >= 5` by ~turn 5 also
independently blocks this — Part B covers the pre-gallery window.)

---

## §4 — Verification

- GT1 / GT1b / GT2 go RED → GREEN.
- Full suite green (the universal proof) — and per the C20 lesson last batch, expect to
  grep for other tests that assert the OLD `_is_enrollment_mishear_candidate` behavior
  (the existing Bug-F / Bug-F.2 rename tests at pipeline.py:4094 / 4258 sites) and update
  any that encode "renames on a fresh best_friend" without a turn-count — the developer
  must enumerate the full enrollment-mishear test surface, not just C-style undercount.
- Canary confirmation: `[Voice] Profile updated jagan …` appears within a few turns;
  no more `embed returned None`; a voice-only "my name is X" mid-conversation no longer
  renames the holder.

---

## §5 — Auditor rulings (LOCKED 2026-05-30) + PIs

- **Q1 → LOCKED:** shared helper is a light standalone in `core/voice.py` that
  encapsulates the FULL order-dependent sequence (global `hf_hub_download` patch →
  import `EncoderClassifier` → `speechbrain.utils.fetching` namespace patch →
  `from_hparams` → return classifier|None). Both loaders call it; each owns only its own
  singleton assignment. Idempotent (sentinel on the global wrapper). Lazy
  speechbrain/hf imports inside the helper → subprocess import stays light. Rationale:
  encapsulating patch→import→namespace-patch→load makes the two-phase ordering
  uncopyable-wrong (a naive block-extract would collapse the phases and miss the
  namespace patch).
- **Q2 → LOCKED:** gated GT1 (real subprocess, CUDA/model-gated) PLUS a MANDATORY
  always-CI structural AST invariant — bidirectional inverse-check (P0.5): every
  SpeechBrain `from_hparams` is reached only through the shared patch helper. GT1's RED
  must be confirmed on the CUDA dev box, never a vacuous skip.
- **Q3 → LOCKED:** `ENROLLMENT_RENAME_MAX_TURNS = 3` (asymmetric: too-tight fails safe;
  overlaps the voice_n gate once Part A fills the gallery — two-layer).
- **Q4 → LOCKED:** turn-count ALONE; no vision signal (vision is non-discriminative —
  both a genuine turn-1 mishear and the canary had the face on camera; the real speaker
  was voice-only/never-on-camera, so a require-the-speaker's-face check is unanswerable
  in the empty-gallery state).
- **Q5 → LOCKED:** both swallows (heavy_worker.py:500 absorbed into the helper's
  logging; :564 separate inference swallow) log type+message. Preventive observability
  sweep: add a load-failure log to the sibling loaders `_get_subprocess_embedder` (:131),
  `_get_subprocess_whisper` (:395), `_get_subprocess_pyannote` (:575). LOG ONLY — do NOT
  add the SpeechBrain patch to them (verified different load mechanisms; missing-patch is
  SpeechBrain-specific). Induction-surfaces-invariant-gaps rule 1.

**Non-blocking PIs (folded into the developer handoff):**
- **PI-1 (symmetric verification):** add the preserve-class GT2 companion — a turn-1
  fresh best_friend + grounded "my name is X" → gate returns True (genuine
  enrollment-mishear still renames). Make any existing Session 100/101 positive-path
  test's in-window turn count explicit, not incidental.
- **PI-2 (full-suite is the proof, not the grep):** B1 is *likely* backward-compatible
  (positive-path tests open fresh `user_turns=0` sessions) but PROVE it with the full
  run; enumerate the whole enrollment-mishear surface (pipeline.py:4094 / 4258).
- **PI-3 (tracked follow-up, OUT of this cycle):** the P0.4 silent-except AST invariant
  catches `except: pass` but NOT `except: return None`/falsy-return — the exact class of
  this bug. A2 + the Q5 sweep fix the concrete instances; extending the detector is
  separate work (architect-filed). Until it lands, per-site logging is the coverage.

**Separate concern:** the Part A clock contributors (pipeline.py:8515/:1990) — the embed
fix dissolves the embed-None cause, but the paired-clock items still want the unified
clock-fabric fix when that follow-up lands.
