# Spec 2 (DRAFT) — Voice accumulation: empty gallery never fills

**Status:** WORKING DRAFT. Not for auditor yet. **Two-phase by necessity** (see §3):
the exact fix can't be locked from static analysis — it needs one instrumented run.
To be cross-checked against Spec 1 + Spec 3 first.

**Surfaced by:** canary #2, 2026-05-30. Jagan talked for ~3 minutes (turns 11–26) and
his voice gallery stayed at **0 samples** the entire session (`terminal_output.md:18`
"Gallery loaded — 0 voice profiles", and again at health line 551). The empty gallery
is the trigger for *every* canary #2 failure (it makes `voice.identify()` return
`no_signal` on every turn — see Spec 1 §1). If the gallery grew, the system would
leave the degenerate no_signal state on its own.

---

## §1 — The dig: what is established

Traced `_accumulate_voice` (pipeline.py:2339) → `_voice_accum_allowed` (:1974) →
`db.add_voice_embedding` (db.py:1714) → `voice.embed` (voice.py:110). Findings, all
confirmed against code + the canary log:

1. **`_accumulate_voice` ran on every Jagan turn.** Routing returned `current`
   (cascade rule `_p4_voice_ambiguous_no_candidates`), which reaches the accumulation
   call at pipeline.py:8519.
2. **It produced ZERO terminal output all session.** None of its three terminal prints
   appear anywhere in the log: "Refused accumulation" (:2434, *unconditional*),
   "Skipped accum … short utterance" (:2470), "Profile updated" (:2490). Nor the
   centroid skip (db.py:1775).
3. **The first sample bypasses every gate.** In `add_voice_embedding`, an empty gallery
   (count=0) skips the diversity check (count<5) and the centroid gate
   (count<MIN_SAMPLES), then INSERTs unconditionally and returns True (db.py:1739-1788).
   So *if* `_accumulate_voice` reached the write, the gallery would grow and
   "Profile updated" would print.
4. **Therefore the failure is upstream of the write, and it is SILENT.** The function
   exits before db.py:1782 without logging.

**The silent-exit candidates** (pipeline.py `_accumulate_voice`, in cascade order):
- `_voice_accum_allowed` returns refused → **prints "Refused" (:2434)**. Not seen ⇒
  either it was *allowed*, or the function crashed before :2430.
- duration gate `len(audio)/16000 < 1.5` → **prints "Skipped" (:2470)**. Not seen ⇒
  passed or not reached.
- `else: return` at :2458 (Path B "OK but self-match weak") → **SILENT**.
- `if emb is None: return` at :2476-2477 → **SILENT**. `voice.embed` returns None on
  empty audio OR when the ECAPA heavy-worker returns None (model-load fail / inference
  crash / sub-1.5s worker-side gate) — voice.py:121-138.
- a raised exception anywhere → **SWALLOWED**: the call site at pipeline.py:8519-8522
  is fire-and-forget (`_voice_tasks.add(_t); _t.add_done_callback(_voice_tasks.discard)`)
  with no exception retrieval, so any raise vanishes with no log.

**What is NOT yet pinned:** which of `:2458` / `:2476-2477` / a swallowed embed
exception is firing, and why. The strongest single hypothesis is **`voice.embed`
returning None** (the ECAPA `ecapa_embed` subprocess pool — its FIRST real use this
session, because `identify` short-circuits to no_signal on an empty gallery without
embedding, so the pool's health was never exercised until accumulation). But that is a
hypothesis, not a confirmed root cause. **Per systematic-debugging discipline, I will
not guess the fix.** The log's silence is itself the evidence: the path is blind.

---

## §2 — Candidate clock contributors (flag, do not assume)

Two clock-fabric items sit in this path (deferred from the clock spec). Neither fully
explains the silent failure, but both are real and belong in the same review:

- **pipeline.py:8515** — `time.monotonic() - _presence_store.peek_last_recognized_at(...)`
  reads a WALL presence timestamp with a monotonic `now`. `mono - wall ≈ -1.78e9 < FACE_STALE`
  is always true → `_face_vis_acc` always True. Permissive here (would *help*
  accumulation), but it is a genuine mismatch.
- **`_voice_accum_allowed` Path A (:1990)** — `face_age = now(wall) - ev.face_last_seen_ts`.
  If the evidence `face_last_seen_ts` is written monotonic anywhere, `face_age ≈ 1.78e9`
  ≫ 10s → **Path A (face witness) always fails**, silently forcing reliance on Path C
  (bootstrap credits). Needs a clock check on the evidence write path.

These are candidate *contributors*, not the confirmed cause. They get verified, not
assumed, in Phase B.

---

## §3 — D-decisions (two phases)

### Phase A — make the accumulation path observable (ship FIRST, low-risk)

Goal: the next canary run must show EXACTLY where accumulation dies. This is also a
real fix on its own — it closes "never silent except / always log" doctrine
violations that are currently hiding the bug.

- **A1** — pipeline.py:2476-2477: log before the silent `emb is None` return
  (e.g. `[Voice] accum skip {pid}: embed returned None (worker/length)`).
- **A2** — pipeline.py:2458: log before the silent Path-B `else: return`.
- **A3** — pipeline.py:8519-8522: the fire-and-forget accumulation task MUST surface
  exceptions. Replace the bare `add_done_callback(_voice_tasks.discard)` with a
  callback that retrieves the exception and logs it
  (`[Voice] accum task error: {type}: {exc}`), then discards. This is the structural
  hole; it must never silently swallow again. (Same shape as the P0.4 silent-except
  remediation — log, don't pass.)
- **A4** — optional: one INFO line at accumulation entry naming the chosen Path
  (face_witness / bootstrap / refused) regardless of `VOICE_BOOTSTRAP_DEBUG`, so the
  Path-A-clock question (§2) is answerable from a normal log without flipping debug on.

Phase A is independently shippable and independently valuable. It is the evidence-
gathering instrumentation the systematic-debugging method requires before any fix.

### Phase B — fix the revealed root cause (locked AFTER one instrumented run)

Once Phase A reveals the exact failure, fix that cause. Pre-enumerated fix shapes per
candidate (the cross-check + the instrumented run pick which one lands):

- **B-embed-None:** if `voice.embed` returns None because the ECAPA `ecapa_embed`
  pool is unhealthy → that is a heavy-worker reliability fix (pool restart / fallback),
  cross-references the P0.R6.Y / P0.R8 worker infrastructure. If None because of the
  sub-1.5s worker gate firing on audio that passed `_accumulate_voice`'s own 1.5s gate
  → reconcile the two length measurements (buffer-length vs speech-length).
- **B-PathA-clock:** if the §2 evidence-clock mismatch is forcing Path A to always fail
  → fix the evidence read/write to one clock (consistency, per the clock-spec
  discipline). Belongs with the deferred fabric work; may merge there.
- **B-not-allowed:** if Phase A shows accumulation was *refused* every turn (and the
  "Refused" print was somehow missed) → the bootstrap-credit replenishment
  (pipeline.py:2392, S120/S94 Fix #5) isn't granting credits for this best_friend
  voice_only_origin session; fix the replenishment gate.

**Do not pre-commit to one B.** The instrumented run decides.

---

## §4 — Verification

- **Phase A:** behavioral test that an accumulation task which raises (monkeypatch
  `voice.embed` to raise) produces a logged `[Voice] accum task error` line and does
  NOT crash the turn; and that an `embed → None` produces a logged skip line. Plus a
  source/AST check that the call site at 8519 retrieves task exceptions.
- **Phase B:** the real proof is behavioral + canary — after the fix, a best_friend
  voice_only_origin session with an empty gallery grows to ≥1 sample within a few turns
  ("Profile updated" appears), and on a fresh run the same person is voice-recognized
  on re-entry. Full suite green is the completeness proof.

---

## §5 — Open questions for the cross-check

- **Q1:** Does Spec 1's D2 (open a stranger on a no_signal real utterance) make the
  empty-gallery state *recoverable* even while this accumulation bug exists? Yes —
  Spec 1 makes turns route; Spec 2 makes the gallery grow so the system stops needing
  Spec 1's no_signal fallback in steady state. They are complementary, not redundant.
  Confirm the framing in task 120.
- **Q2:** Should Phase A ship as its own tiny PR *before* Spec 1, so the next canary
  already carries the accumulation instrumentation and we get Phase B's evidence for
  free on the Spec 1 validation run? Strong lean: **yes** — it is low-risk pure
  observability and it accelerates everything downstream. Decide in task 120 /
  with the user.
- **Q3:** Is the empty gallery on a *best_friend* even expected? Jagan has a face
  profile (5 embeddings, db FAISS rebuild line 8) but voice_n=0. Was he re-enrolled
  face-only (dashboard / first-boot), or did a prior factory-reset wipe voice but not
  face? Worth a one-line confirmation; it tells us whether "empty gallery" is a
  fresh-enroll cold-start (expected, must self-heal) or a data-corruption artifact.
