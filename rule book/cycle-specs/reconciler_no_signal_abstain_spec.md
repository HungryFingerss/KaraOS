# Spec 1 (DRAFT) — Reconciler: "voice abstains, never veto"

**Status:** WORKING DRAFT. Not for auditor yet. To be cross-checked against Spec 2
(voice accumulation) + Spec 3 (vision-presence router) + the accumulation deep-dig
before finalizing.

**Surfaced by:** canary #2, 2026-05-30 (`terminal_output.md`). Three turns the system
heard but never responded to.

**Principle (the user's directive, 2026-05-30):** vision and voice are TRULY
independent channels. `confidence_is_no_signal=True` means *voice has no opinion*
(empty gallery OR embedding failure). A no-opinion voice must DEFER to vision/session
routing. **It must never DROP a turn.** Today it does — and that is the coupling.

---

## §1 — Root cause (confirmed by code trace + observed behavior)

The single trigger in canary #2: the voice gallery was EMPTY (`terminal_output.md:18`
"Gallery loaded — 0 person(s) with voice profiles"). Jagan's face was recognized
perfectly (vision, score 0.914) but his voice profile is `voice_n=0`.

With an empty gallery, `core/voice.py::identify()` returns `confidence_is_no_signal=True`
on **every** utterance — there is nothing to score against. The reconciler then treats
that abstention as a routing verdict and drops the turn.

Three drop sites, each confirmed by tracing the cascade in `core/reconciler.py` and
cross-checked against the observed log behavior:

| Canary turn | Inputs | Rule fired | Why it drops | Spec fix |
|---|---|---|---|---|
| "Travel anywhere for free." (~0.8s, line 239) | no_signal, cur=Jagan, n_seg=1 | `_p0_short_utterance_hard_mismatch` (:164) | fires on `confidence < SHORT_UTT_FLOOR (0.20)` and **never checks `confidence_is_no_signal`** — so 0.0 reads as a "hard mismatch" | D1 |
| Lexi "Hi Kara, my name is Lexi" (~1.6s, line 505) | no_signal, cur=None, no face track | `_p5_no_session_no_action` (:795) | `_p5_no_session_new_stranger` (:771) **requires `not no_signal`** so it skips → no_action drops | D2 |
| "Is there any other game" (post-expiry, line 565) | no_signal, cur=None, no face track | `_p5_no_session_no_action` (:795) | same as Lexi (plus no "Kara", so even if a session opened the engagement gate stays closed — see §5) | D2 (partial; full fix is Spec 2 voice-recognition resume) |

**Behavioral confirmation of the trace:** Lexi's turn was dropped via a `cur_pid=None`
path. The ONLY `cur_pid=None` drop rule in the cascade is `_p5_no_session_no_action`,
which requires `confidence_is_no_signal=True`. So the log itself proves her
`identify()` returned no_signal — i.e., the empty-gallery → no_signal claim holds.

The drop rules predate the `confidence_is_no_signal` flag (added at the Session 119 /
Pre-P1 Bundle 5 MF7 work). The flag was threaded everywhere it was *added* (e.g.
`_p4_new_stranger_low_match` :666, `_p4_voice_ambiguous_no_candidates` :725) but the
**older P0 short-utterance drop rules and the P5 stranger-open rule were never
updated to honor it.** An empty gallery falls straight through that gap.

Note: the "stuck in THINKING" display (pipeline.py — drop `continue` at 8434/8438/8443/
8456/8468/8479 skips the LISTENING reset at :8786) is a *cosmetic* artifact, NOT the
turn-blocker. The blocker is the reconciler verdict. Do not "fix" the state machine.

---

## §2 — D-decisions (the changes)

All changes are in `core/reconciler.py`. The cascade ordering is load-bearing
(`test_cascade_ordering_*`); **no rule is reordered, added, or removed.** Two rules
gain a `confidence_is_no_signal` guard; one rule gains an OR clause. The shape is
identical to the Session 119 negative-cosine fix: teach existing rules to respect a
field they already receive.

### D1 — short-utterance drop rules exclude no_signal

`_p0_short_utterance_hard_mismatch` (:164) and `_p0_short_utterance_ambiguous_multi_session`
(:193): add `and not claim.confidence_is_no_signal` to each guard.

Rationale: these rules say "voice scored the holder and it's clearly NOT them, on a
short utterance → drop." A no_signal score is not "clearly not them" — it is "voice
has no profile to compare." That is not a mismatch; it is an abstention. Excluding
no_signal lets the turn fall through to the hold-current rules.

**Fall-through verified** for the canary-1 case (Jagan, 0.77s, no_signal, alone,
n_seg=1): after D1 the cascade reaches `_p4_voice_ambiguous_no_candidates` (:711),
which holds `cur_pid` when `scene_candidates == 0`. Jagan is the only person present
→ holds his session → turn processes. Robust to the face flicker, because that rule
counts OTHER candidates, not whether the holder is currently in-frame.

### D2 — no-session stranger-open fires on real speech even when no_signal

`_p5_no_session_new_stranger` (:771): extend the guard so a real-length utterance opens
a session even when voice abstains.

Current:
```
(not claim.confidence_is_no_signal or len(presence.unrecognized_track_ids) > 0)
```
Proposed (add a third OR):
```
(not claim.confidence_is_no_signal
 or len(presence.unrecognized_track_ids) > 0
 or claim.utterance_duration >= <REAL_SPEECH_FLOOR>)
```

Rationale: with an empty gallery, no_signal is permanent, so the existing guard can
NEVER open a session by voice — the system is locked out of voice-first engagement.
A real-length utterance is real speech regardless of whether voice can name the
speaker. Opening a session does not bypass safety: the new stranger session opens
GATED (`STRANGER_REQUIRE_SYSTEM_NAME=True`), so it only actually engages if the
speaker said the system name (handled downstream at pipeline.py:8383-8388). Noise
that crosses the duration floor opens a gated session that never engages and expires
harmlessly.

**`<REAL_SPEECH_FLOOR>` — OPEN QUESTION (Q1):** two candidates:
- `VOICE_ROUTING_MIN_AUDIO_FOR_SCORE` (0.5s) — the existing "is this real audio vs ECAPA
  noise" floor. Snappier engagement; relies on the engagement gate to reject non-"Kara"
  noise. **Leaning here** — it is the principled "real speech" line already in config.
- `VOICE_ROUTING_MIN_UTTERANCE_SECS` (1.0s) — conservative; matches "long enough to seed a
  voice profile." Safer against noise, but a brief "Hi Kara" under 1.0s would still be
  dropped.

Defer the lock to the cross-check + auditor. Both are one-line.

### D3 — (verify-only) confirm no other drop rule swallows no_signal silently

Audit pass, not a code change: walk every rule that returns a non-`current`,
non-`switch`, non-`new_stranger` action (i.e. every `ambiguous` / `*_mismatch` /
`no_action` / `*_skip` producer) and confirm each either (a) correctly requires a real
score, or (b) is unreachable for the no_signal-with-active-session case after D1.

Known-correct after D1 (do not change): `_p4_voice_ambiguous_with_candidates` (:739)
correctly drops when no_signal AND other candidates exist — that is "I can't tell who
spoke and there genuinely are alternatives," which is the right time to drop. The
solo case is handled by `_p4_voice_ambiguous_no_candidates`. This is the boundary
between "abstain → hold" (solo) and "abstain → drop" (genuinely ambiguous multi-person).

---

## §3 — What this fix does and does NOT fix

**Fixes:**
- Failure 1 (Jagan's short answers dropped) — fully, via D1.
- Failure 2 (Lexi can't engage) — fully, via D2 (she said "Kara" → opens + engages).

**Does NOT fix (by design — belongs to other specs):**
- Failure 3 ("Is there any other game" after Jagan's session expired, no "Kara"):
  D2 opens a gated stranger session but the engagement gate stays closed (no system
  name). The clean experience is for VOICE to recognize Jagan and resume his session
  without re-addressing — which requires his gallery to be non-empty. **That is Spec 2
  (accumulation).** This spec deliberately does not try to make an unrecognized,
  non-engaging voice route to a prior holder.
- The multi-person "voice abstains, holder is on camera, someone else also visible →
  who is speaking?" case. After D1, that falls to `_p4_voice_ambiguous_with_candidates`
  → drop. Making vision route it independently is **Spec 3 (held design work)**.

---

## §4 — Verification (how the developer proves it)

Behavioral, against the real cascade (`reconcile()` + `_build_routing_inputs()`), with
an EMPTY voice gallery (the canary state). No mocking the reconciler.

1. **D1 fail-on-revert / hold-current:** empty gallery, cur=best_friend holder, alone,
   utterance 0.77s, n_seg=1 → assert action == "current", pid == holder. Pre-D1 this
   returns "short_utterance_voice_mismatch". (Reproduces "Travel anywhere for free.")
2. **D1 boundary — multi-person still drops:** same but with a second visible person →
   assert action == "ambiguous" (the genuinely-ambiguous case still drops; D1 did not
   over-relax).
3. **D1 don't-disable sanity:** non-empty gallery, real low score (NOT no_signal),
   short utterance, clearly-not-holder → assert still "short_utterance_voice_mismatch"
   (the real-mismatch drop is preserved; only no_signal abstains).
4. **D2 stranger opens:** empty gallery, no session, 1.6s utterance, no face track →
   assert action == "new_stranger". Pre-D2 this returns "no_action". (Reproduces Lexi.)
5. **D2 boundary — sub-floor noise still no_action:** empty gallery, no session,
   utterance below `<REAL_SPEECH_FLOOR>`, no track → assert action == "no_action"
   (a hiccup doesn't spawn a session).
6. **D3 audit:** an AST or table test asserting every `*_mismatch` / `ambiguous` drop
   rule that keys on `confidence` also gates on `not confidence_is_no_signal` OR is
   documented in an allowlist as "correctly drops on no_signal" (e.g.
   `_p4_voice_ambiguous_with_candidates`). Prevents a future drop rule re-opening the gap.
7. **Full suite green** — the universal completeness proof. The cascade-ordering tests
   (`test_cascade_ordering_*`, `test_reconciler.py` per-rule tests, `EXPECTED_RULES_BY_BAND`)
   MUST stay green; this fix touches rule *guards*, not order.

---

## §5 — Open questions for the cross-check + auditor

- **Q1:** `<REAL_SPEECH_FLOOR>` = 0.5 (MIN_AUDIO_FOR_SCORE) vs 1.0 (MIN_UTTERANCE_SECS).
  Lean 0.5 (engagement gate makes it safe). Lock at cross-check.
- **Q2:** Does Spec 2 (accumulation) make D2 mostly moot in steady state (a non-empty
  gallery means a returning speaker voice-matches and resumes, never hitting the
  no-session-no-signal path)? If so, D2 is the **first-ever-speaker / cold-start**
  safety net — still needed (the empty-gallery state is real on a fresh enroll), but
  its framing should say "cold-start," not "primary path." Resolve in cross-check.
- **Q3:** Should EXPECTED_RULES_BY_BAND (`reconciler.py:947`) gain an entry for the
  no_signal-short-utterance case so the band-divergence watchdog doesn't log a false
  "regression" when a no_signal short utterance now legitimately falls through to a
  P4 hold rule instead of a P0 rule? Likely yes — the watchdog currently expects P0
  rules for the short_hard band. Verify against `pipeline.py:8205` watch logic.
