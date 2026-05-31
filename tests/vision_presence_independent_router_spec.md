# Spec 3 (DESIGN / HELD) — Vision as a first-class independent router

**Status:** DESIGN DOCUMENT. **Held** — not for implementation now. Drafted alongside
Spec 1 + Spec 2 so the three can be cross-checked as a set. This is the deepest part of
"vision and voice are truly independent," and it is the genuinely hard part, so it gets
its own design pass and its own multi-person canary, not a bundle.

**Principle (the user's directive, 2026-05-30):** vision and voice are independent
channels; neither's failure may block the other. Spec 1 makes voice *abstain instead of
veto*. This spec asks the harder question: when voice abstains, can **vision route the
turn on its own** — including telling apart *which* of several visible people is
speaking?

---

## §1 — Why this is separate from Spec 1

Spec 1 already delivers the solo case of vision-independent routing. After Spec 1, a
no_signal turn with the holder present and **no one else** in the scene falls to
`_p4_voice_ambiguous_no_candidates` (reconciler.py:711) → holds the holder. That is
vision routing by absence-of-alternatives. Good enough when one person is in the room.

The gap Spec 3 owns is **multi-person**: two or more faces visible, voice abstains
(empty/failed gallery, or a genuine non-match) → after Spec 1 this hits
`_p4_voice_ambiguous_with_candidates` (reconciler.py:739) → **drop**. That drop is
correct *today* (the system genuinely cannot tell who spoke from voice alone), but it
is exactly the coupling the directive wants gone: vision can see who is talking, and is
not being asked.

So: Spec 1 = "voice abstains, never vetoes." Spec 3 = "when voice abstains, vision
*decides* — even among several people."

---

## §2 — The vision signals available (what we already have)

The system is not starting from zero. Independent vision speaker-evidence already
exists and is mostly unused for routing:

- **Lip activity** — `core/vision.py::LipTracker` + `pipeline.py::_lip_tracking_loop`
  (started per-turn at 7817). Inter-frame mouth-region pixel motion. This is the
  natural "who is speaking" signal and it is already wired for recording extension. It
  is *not* fed into the reconciler.
- **Presence / who is on camera** — `_presence_store`, `visible_pids` in
  `PresenceState`. Already in the reconciler inputs; used only as a co-witness gate.
- **Per-face quality / yaw** — `face_quality_score`, `estimate_yaw_from_landmarks`
  (V1/V2). Could weight "is this the person facing the camera and talking."

Lip activity is the load-bearing one: it is the only signal that distinguishes
*speaking* from *merely present*. Presence alone can't disambiguate two people in
frame; lip motion can.

---

## §3 — The design space (to be chosen in the design pass, not now)

Rough shape of a `_p?_vision_routes_when_voice_abstains` rule (or rules), fired only
when `claim.confidence_is_no_signal` (voice has no opinion):

- **Single visible candidate → route to them.** If exactly one face is visible and
  voice abstains, vision routes the turn to that person. (Spec 1 covers the
  zero-other-candidates case; this extends to "one visible, holder differs.")
- **Multiple visible, one lip-active → route to the lip-active one.** The hard,
  high-value case. Requires plumbing a per-pid lip-activity signal into the reconciler
  inputs (`_build_routing_inputs`) and a rule that prefers the lip-active face.
- **Multiple visible, lip signal ambiguous → drop (status quo).** Honest fallback when
  vision *also* can't tell. The bar to clear before dropping is "vision tried and
  couldn't," not "voice couldn't."

Cascade placement is delicate. The existing P0–P5 ordering encodes Sessions 60–122 bug
fixes and is guarded by `test_cascade_ordering_*`. A vision-abstain rule most likely
sits in the P4 band (voice unrecognized, active session) and the no-session P5 band,
gated hard on `confidence_is_no_signal` so it never overrides a real voice match. This
needs careful placement + the same regression-test rigor as every other cascade change.

---

## §4 — The hard problems (why it's held)

1. **Lip-activity reliability.** Mouth-motion pixel-diff is noisy: chewing, smiling,
   off-camera audio, occlusion, low light, profile faces. A naive "lip-active → that's
   the speaker" will misroute. Needs a confidence model + a "vision also abstains"
   path, not a hard pick.
2. **Latency / sync.** Lip activity must be sampled over the *utterance window* and
   aligned to the audio turn boundary. The lip loop today extends *recording*; routing
   needs a per-pid activity summary for the just-ended turn.
3. **Sensor-fusion semantics.** When voice gives a weak-but-real match AND vision points
   at a different lip-active face, who wins? "Truly independent" does not mean "vision
   always overrides voice" — it means each channel is authoritative when the other
   abstains, and fusion is principled when both speak. That fusion policy is a design
   decision, not a one-liner.
4. **Test surface.** This needs multi-person behavioral fixtures + a real multi-person
   canary (two people, empty/mismatched voice gallery, talking in turns). That is a
   heavier validation loop than Specs 1–2.

Specs 1 + 2 fix every observed canary #2 failure without any of this. Spec 3 is the
"make multi-person robust" layer, and it earns a deliberate design pass rather than
being rushed in behind a quick fix.

---

## §5 — Relationship to Specs 1 and 2 (for the cross-check)

- **Depends on Spec 1.** Spec 3 only matters once `confidence_is_no_signal` reliably
  means "abstain" (Spec 1). Building Spec 3 before Spec 1 would be building on the very
  veto we are removing.
- **Reduced in urgency by Spec 2.** Once the gallery actually grows (Spec 2), the
  common multi-person case has *real* voice matches and never reaches the abstain band.
  Spec 3 is then the cold-start / unenrolled-visitor / voice-failure safety net — high
  value, lower frequency. This is why it is correctly held: Spec 2 shrinks how often it
  is the only thing standing between a multi-person turn and a drop.
- **No conflict.** Spec 3 adds rules gated on `confidence_is_no_signal` and vision
  evidence; it does not change Spec 1's guards or Spec 2's accumulation path. The one
  thing to keep aligned: Spec 1 §5 Q3 (the EXPECTED_RULES_BY_BAND watchdog) must account
  for any new abstain-band rules Spec 3 introduces later.

---

## §6 — Open design questions (for the design pass, not the cross-check)

- How is per-pid lip activity summarized over an utterance, and where does it enter
  `_build_routing_inputs`?
- What is the fusion policy when voice gives a weak real match and vision points
  elsewhere?
- What is vision's own "I also can't tell" threshold, below which the honest drop stays?
- Does any of this generalize the existing P2 face-assist rules, or sit beside them?

**Recommendation:** finalize Spec 1 (and ship Spec 2 Phase A) first, get a clean
canary, THEN open this design pass with real multi-person logs in hand. Designing
multi-person disambiguation without multi-person evidence would be guessing.
