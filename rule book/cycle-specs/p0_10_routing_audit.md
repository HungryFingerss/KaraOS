# P0.10 Phase 0 Routing Audit

**Status:** Pre-Plan audit. Pure documentation, zero production code changes.
**Date:** 2026-05-17.
**Suite at audit time:** 2189 passing, 8 pre-existing infra failures.

**Companion file:** `tests/p0_10_pre_audit_bug_w_evidence.md` — full bug-report for the load-bearing Bug-W finding.

---

## Executive summary

**P0.10's v1 simple-deletion plan does NOT work as-stated.** The audit surfaced one load-bearing finding that revises the plan scope:

> **Bug-W is in the NEW reconciler, not the legacy.** The legacy router (`_resolve_actual_speaker`) correctly returned `"current"` for the 0.45s "Thank you." utterance; the new reconciler's `_p4_new_stranger_low_match` rule fired and opened a phantom stranger session. Phase 4 cutover (`ROUTING_USE_RECONCILER=True`) made the reconciler primary, so the wrong decision was dispatched.

**Implication:** P0.10 cannot delete `_resolve_actual_speaker` until the new reconciler is patched to cover the 0.3–0.5s utterance band that the legacy's catch-all "current" fallback was silently guarding. Otherwise the deletion locks Bug-W in.

**N=1 finding (deliverable 1):** there is exactly ONE source of `_routing_action` in the dispatch path — the override at pipeline.py:7417-7419. Plan v1's "delete `_resolve_actual_speaker`" applies cleanly to the code path. The complication is purely semantic (the new reconciler has rules-gap regressions the legacy guarded against).

---

## Deliverable 1 — Routing-path enumeration

**Result: N=1** (single source of `_routing_action` after Phase 4 cutover).

| Path # | file:lineno | Condition that fires it | Action produced | Caller context | Notes |
|---|---|---|---|---|---|
| 1 (legacy) | pipeline.py:7325-7341 | `_resolve_actual_speaker(v_pid, v_score, ...)` always called per turn | tuple `(pid, action)` | Inside `conversation_turn` voice-routing block | After Phase 4 cutover, result is **shadow-only** — feeds Reconciler-Shadow divergence log at L7400-7408 but does NOT drive dispatch |
| 2 (reconciler) | pipeline.py:7377-7413 | `reconcile(claim, presence, session)` always called per turn (wrapped in try/except so bugs can't break the turn) | `RoutingDecision(pid, action, rule_fired, reasoning)` | Same call site | **Primary router** when `ROUTING_USE_RECONCILER=True` (current state) |
| 3 (override) | pipeline.py:7417-7419 | `if ROUTING_USE_RECONCILER and _rc_decision is not None` | Overwrites `_routing_action = _rc_decision.action` | Dispatch gate | This is THE single source of the dispatched `_routing_action`. Rollback: flip flag to False → legacy decision dispatches instead |
| 4 (dispatch) | pipeline.py:7421-7618 | Branches on `_routing_action ∈ {switch_enrolled, new_stranger, ambiguous, no_action, short_utterance_skip, short_utterance_voice_mismatch, multi_segment_voice_mismatch, single_segment_voice_mismatch, current}` | Side effects (open session / close session / drop turn / record attribution) | Same block | One consumer; well-bounded |
| 5 (test-side) | test_pipeline.py:16590-16593 | Source-inspection test references `_routing_action == "switch_enrolled"` and `_routing_action ==` patterns | n/a (asserts structure) | Source-inspection regression guard | Test will need updating after legacy delete to scan the reconciler dispatch instead |

**No other sources found.** Wide-net grep confirmed:
- `_route_action` — zero matches
- `routing_decision` — zero matches outside reconciler internals
- `_open_session(` voice-routing-driven calls — all gate on the dispatched `_routing_action` from path 3
- Action strings (`new_stranger`/`current`/etc.) — appear only inside `_resolve_actual_speaker`, `core/reconciler.py` rules, and the dispatch block at pipeline.py:7421+

**Plan v1 implication:** the deletion is structurally simple — remove the `_resolve_actual_speaker` function + the legacy call site at L7325-7341 + the divergence-detection block at L7400-7408 + the conditional override at L7415-7419 (becomes unconditional `_routing_action = _rc_decision.action`). Five surgical edits.

---

## Deliverable 2 — Bug-W mechanism trace

**Documented in detail in `tests/p0_10_pre_audit_bug_w_evidence.md`.** Summary:

The Bug-W input (0.45s utterance, voice=0.021, cur_pid active, mature gallery, n_diarize=0) falls into a coverage gap in the new reconciler's Priority 0 rules:

- `_p0_pure_noise_hold_current` requires `utterance_duration < 0.3s` (NOISE_FLOOR_SECS); 0.45s is **above** the noise floor.
- `_p0_short_utterance_hard_mismatch` and `_p0_short_utterance_ambiguous_multi_session` both require `utterance_duration >= 0.5s` (MIN_AUDIO_FOR_SCORE); 0.45s is **below** the audio-gate floor.

The 0.3–0.5s band has NO P0 rule that fires. Fall-through reaches `_p4_new_stranger_low_match` which fires unconditionally on `(no v_pid match, session active, score below threshold, score != 0.0)` → opens phantom stranger.

The legacy router's Priority 0 (pipeline.py:1206-1237) had a catch-all `return cur_pid, "current"` at L1233 for ANY `utterance_duration < MIN_UTTERANCE_SECS (1.0s)` with `cur_pid is not None`. That catch-all is the missing safety net.

---

## Deliverable 3 — `_resolve_actual_speaker` branch catalog

Function spans `pipeline.py:1147-1417` (270 lines).

| Branch | Line range | Gate condition | Action returned | Provenance | Bug-W-adjacent? |
|---|---|---|---|---|---|
| **P0a** (Tier 1 short-utt hard mismatch) | 1206-1217 | `utt_dur < 1.0` AND `utt_dur >= 0.5` AND `v_score < 0.20` AND `cur_pid` | `short_utterance_voice_mismatch` | Session 92 P3.23 | No |
| **P0b** (Tier 2 ambiguous multi-session) | 1218-1232 | `utt_dur < 1.0` AND `utt_dur >= 0.5` AND `v_score < 0.40` AND `n_active >= 2` | `short_utterance_voice_mismatch` | Session 93 P3.23 refinement | No |
| **P0c** (catch-all hold current) | 1233-1235 | `utt_dur < 1.0` AND `cur_pid is not None` | `current` (cur_pid) | Bug F (Session 67) | **YES — load-bearing for Bug-W** |
| **P0d** (no-session short-utt skip) | 1236-1237 | `utt_dur < 1.0` AND `cur_pid is None` | `short_utterance_skip` | Bug F (Session 67) | No |
| **P1** (confident voice switch) | 1241-1244 | `v_pid != cur_pid` AND `v_score >= switch_threshold` | `switch_enrolled` (v_pid) | Original 3-tier routing (Session 26) | No |
| **P2a** (face+voice agree switch) | 1247-1258 | `v_pid != cur_pid` AND mid-range score AND face in frame AND `v_score >= FACE_ASSIST_MIN (0.42)` | `switch_enrolled` (v_pid) | Bug O (Session 49) | No |
| **P2b** (face but weak voice → ambiguous) | 1259-1263 | `v_pid != cur_pid` AND face in frame AND `v_score < FACE_ASSIST_MIN` | `ambiguous` | Bug O (Session 49) | No |
| **P2c** (no face → ambiguous) | 1264-1265 | `v_pid != cur_pid` AND mid-range score AND face NOT in frame | `ambiguous` | Bug O (Session 49) | No |
| **P3a** (self-match below floor) | 1268-1274 | `v_pid == cur_pid` AND `v_score < SELF_MATCH_FLOOR (0.30)` | `ambiguous` | Bug 51 #3 (poisoning protection) | No |
| **P3b** (thin stranger self-match relaxed) | 1296-1307 | `v_pid == cur_pid` AND offscreen AND `v_score < OFFSCREEN_FLOOR (0.45)` AND thin stranger | `current` (cur_pid) | Bug W original (Session 72) — name collision unrelated to current Bug-W | No |
| **P3c** (offscreen mature → ambiguous) | 1296-1309 | `v_pid == cur_pid` AND offscreen AND `v_score < OFFSCREEN_FLOOR` AND mature holder | `ambiguous` | Bug 51 #3 | No |
| **P3d** (self-match confirmed) | 1310-1311 | `v_pid == cur_pid` AND (face in frame OR `v_score >= OFFSCREEN_FLOOR`) | `current` (cur_pid) | Original | No |
| **P3.5** (bootstrapping stranger hold) | 1325-1329 | `v_pid is None` AND cur is stranger AND `gallery_count < N_INITIAL_VOICE` | `current` (cur_pid) | NEW-1 (Session 49) | No |
| **P4a** (multi-segment mismatch) | 1349-1360 | `v_pid is None` AND `n_diarize >= 2` AND `v_score < STRANGER_FLOOR (0.25)` AND `n_active >= 2` | `multi_segment_voice_mismatch` | Session 118 Fix A + Session 121 refinement | No |
| **P4b** (new stranger low match) | 1361-1363 | `v_pid is None` AND `0 < v_score < VOICE_RECOGNITION_THRESHOLD (0.25)` | `new_stranger` | Original | No |
| **P4c** (single-segment mismatch) | 1378-1394 | `v_pid is None` AND `n_diarize == 1` AND mature holder AND audio ≥ 0.5s AND `n_active >= 2` | `single_segment_voice_mismatch` | Session 120 + Session 121 inversion | No |
| **P4d** (voice ambiguous, no candidates) | 1396-1401 | `v_pid is None` AND `v_score == 0` AND scene_candidates == 0 | `current` (cur_pid) | Original | No |
| **P4e** (voice ambiguous, with candidates) | 1402-1403 | `v_pid is None` AND scene_candidates ≥ 1 | `ambiguous` | Original | No |
| **P5a** (no session, low-score stranger) | 1411-1413 | `cur_pid is None` AND (`0 < v_score < 0.25` OR active unrec track) | `new_stranger` | Original | No |
| **P5b** (no session, no signal) | 1414 | `cur_pid is None` AND `v_score == 0` AND no unrec tracks | `no_action` | Original | No |
| **P-last-resort** | 1416-1417 | All other cases | `ambiguous` | Original | No |

**Branch count:** 21 distinct branches.

**Bug-W-adjacent branch:** **P0c only.** The legacy's catch-all "current" fallback for `utt_dur < 1.0s AND cur_pid is not None` is the load-bearing safety net the new reconciler lost.

---

## Deliverable 4 — KEEP/DROP/REVISE classification

Cross-referenced against `core/reconciler.py` rule set (Sessions 118-119 architecture). Reconciler rules are listed at reconciler.py:797-817.

| Legacy branch | New reconciler rule | Classification | Rationale |
|---|---|---|---|
| **P0a** (Tier 1 short-utt hard mismatch) | `_p0_short_utterance_hard_mismatch` | **KEEP** | Behavior preserved with identical guards (utt < 1.0, utt ≥ 0.5, v_score < 0.20 floor). Reconciler covers this case correctly. |
| **P0b** (Tier 2 ambiguous multi-session) | `_p0_short_utterance_ambiguous_multi_session` | **KEEP** | Behavior preserved with identical guards. |
| **P0c** (catch-all hold current) | **partial: `_p0_pure_noise_hold_current` (utt < 0.3 only)** | **REVISE** | Reconciler's `_p0_pure_noise_hold_current` covers ONLY the sub-0.3s band, not the 0.3–1.0s band the legacy covered. This is **Bug-W's root cause**. New reconciler needs an additional rule (e.g. `_p0_short_utterance_gap_hold_current`) that fires for `0.3 ≤ utt < 1.0` AND `cur_pid is not None` AND P0a/P0b didn't fire (no audio-gate satisfied OR ambiguous-zone gate didn't fire). |
| **P0d** (no-session short-utt skip) | `_p0_short_utterance_no_session` | **KEEP** | Behavior preserved (cur_pid is None). |
| **P1** (confident voice switch) | `_p1_confident_voice_switch` | **KEEP** | Same gate semantic. |
| **P2a** (face+voice agree switch) | `_p2_midrange_face_assist_switches` | **KEEP** | Same gate semantic (mid-range + face in frame + FACE_ASSIST_MIN floor). |
| **P2b** (face but weak voice → ambiguous) | `_p2_midrange_face_assist_below_floor` | **KEEP** | Same. |
| **P2c** (no face → ambiguous) | `_p2_midrange_no_face_returns_ambiguous` | **KEEP** | Same. |
| **P3a** (self-match below floor) | `_p3_self_match_below_floor` | **KEEP** | Same. |
| **P3b** (thin stranger self-match relaxed) | `_p3_self_match_thin_stranger_relaxed` | **KEEP** | Same. |
| **P3c** (offscreen mature → ambiguous) | `_p3_self_match_offscreen_mature` | **KEEP** | Same. |
| **P3d** (self-match confirmed) | `_p3_self_match_with_face` | **KEEP** | Same. |
| **P3.5** (bootstrapping stranger hold) | `_p3_5_bootstrapping_stranger_hold` | **KEEP** | Same. |
| **P4a** (multi-segment mismatch) | `_p4_multi_segment_mismatch` | **KEEP** | Same gate (n_diarize ≥ 2 + low score + multi-session). |
| **P4b** (new stranger low match) | `_p4_new_stranger_low_match` | **KEEP** for the post-P0-handled range, but **the rule's preconditions need a P0-gap guard** so Bug-W's 0.3–0.5s input doesn't reach it. (Equivalent to REVISE on P0c — fixing P0c naturally fixes the regression.) |
| **P4c** (single-segment mismatch) | `_p4_single_segment_mismatch` | **KEEP** | Same. |
| **P4d** (voice ambiguous, no candidates) | `_p4_voice_ambiguous_no_candidates` (and `_p4_pyannote_vouched_stranger` for the multi-segment variant) | **KEEP** | Same. |
| **P4e** (voice ambiguous, with candidates) | `_p4_voice_ambiguous_with_candidates` | **KEEP** | Same. |
| **P5a** (no session, low-score stranger) | `_p5_no_session_new_stranger` | **KEEP** | Same. |
| **P5b** (no session, no signal) | `_p5_no_session_no_action` | **KEEP** | Same. |
| **P-last-resort** | (catch-all `ambiguous` after all rules return None) | **KEEP** | Reconciler's post-loop default produces the same outcome. |

**Summary**: 20/21 branches **KEEP** (full coverage in new reconciler). **1/21 branch REVISE** — P0c needs an explicit "0.3–1.0s gap holds current" rule added to the new reconciler.

No DROP-classified branches — every legacy decision corresponds to a correct semantic the new reconciler should preserve.

---

## Deliverable 5 — Contract spec for the new reconciler

### 5.A — Positive contract

After legacy router is deleted, the new reconciler MUST guarantee:

| # | Invariant | Source branch |
|---|---|---|
| C1 | On `utt < 1.0s` AND `utt ≥ 0.5s` AND `v_score < SHORT_UTT_FLOOR (0.20)` AND `cur_pid is not None`, return `short_utterance_voice_mismatch` | P0a |
| C2 | On `utt < 1.0s` AND `utt ≥ 0.5s` AND `v_score < SHORT_UTT_AMBIGUOUS (0.40)` AND `n_active >= 2`, return `short_utterance_voice_mismatch` | P0b |
| **C3** | **On `utt < 1.0s` AND `cur_pid is not None` AND C1/C2 not fired, return `current` (cur_pid)** | **P0c — currently violated; Bug-W's failure mode** |
| C4 | On `utt < 1.0s` AND `cur_pid is None`, return `short_utterance_skip` | P0d |
| C5 | On `v_pid != cur_pid` AND `v_score >= switch_threshold`, return `switch_enrolled` (v_pid) | P1 |
| C6 | On mid-range voice + face-in-frame + `v_score >= FACE_ASSIST_MIN`, return `switch_enrolled` (v_pid) | P2a |
| C7 | On mid-range voice + face-in-frame + `v_score < FACE_ASSIST_MIN`, return `ambiguous` | P2b |
| C8 | On mid-range voice without face, return `ambiguous` | P2c |
| C9 | On `v_pid == cur_pid` AND `v_score < SELF_MATCH_FLOOR`, return `ambiguous` | P3a |
| C10 | On `v_pid == cur_pid` AND offscreen AND thin stranger, return `current` (cur_pid) | P3b |
| C11 | On `v_pid == cur_pid` AND offscreen AND mature holder AND `v_score < OFFSCREEN_FLOOR`, return `ambiguous` | P3c |
| C12 | On `v_pid == cur_pid` AND (face-visible OR `v_score >= OFFSCREEN_FLOOR`), return `current` (cur_pid) | P3d |
| C13 | On `v_pid is None` AND stranger holder AND `gallery < N_INITIAL_VOICE`, return `current` (cur_pid) | P3.5 |
| C14 | On `n_diarize >= 2` AND `v_score < STRANGER_FLOOR` AND `n_active >= 2`, return `multi_segment_voice_mismatch` | P4a |
| C15 | On `v_pid is None` AND `0 < v_score < VOICE_RECOGNITION_THRESHOLD` AND C3 not fired, return `new_stranger` | P4b |
| C16 | On `n_diarize == 1` AND `v_score < STRANGER_FLOOR` AND mature AND audio ≥ 0.5s AND `n_active >= 2`, return `single_segment_voice_mismatch` | P4c |
| C17 | On `v_pid is None` AND `v_score == 0` AND no scene candidates, return `current` (cur_pid) | P4d |
| C18 | On `v_pid is None` AND `v_score == 0` AND scene candidates ≥ 1, return `ambiguous` | P4e |
| C19 | On `cur_pid is None` AND (`0 < v_score < threshold` OR active unrec track), return `new_stranger` | P5a |
| C20 | On `cur_pid is None` AND no signal, return `no_action` | P5b |
| C21 | All else: return `ambiguous` | P-last-resort |

### 5.B — Negative contract

After legacy router is deleted, the new reconciler MUST NEVER:

| # | Forbidden behavior | Source |
|---|---|---|
| **N1** | **Open a stranger session for a 0.45s utterance with voice_score=0.021, cur_pid active, mature gallery, n_diarize=0** | **Bug-W exact failure mode** |
| N2 | More generally: open a stranger session for ANY `utt_dur ∈ [0.3, 1.0)` with `cur_pid is not None` | Bug-W class — the 0.3–1.0s band must hold current when in-session |
| N3 | Attribute a turn to `cur_pid` when `v_pid != cur_pid` AND `v_score >= switch_threshold` (would silently mis-attribute the switched-in speaker's words to the previous holder) | C5 contrapositive |
| N4 | Open a stranger session on `n_diarize >= 2` + low score + `n_active >= 2` (cross-talk-between-knowns) | C14 — Session 118 protection |
| N5 | Drop a turn on `n_diarize == 1` + low score when holder is bootstrapping (immature gallery) — drop only applies when holder is mature | C16 conditions |
| N6 | Fire any decision with `pid` referencing a `cur_pid` value that's stale (caller's responsibility, but the reconciler must not invent pids) | Architectural |

---

## Decisions to surface for D1-D8 locking BEFORE Plan v1

### D1 — Scope: `_resolve_actual_speaker` only, or all sources?

**N=1 finding makes this trivial.** Only one source of `_routing_action` after Phase 4 cutover.

Options:
- **(a) Delete `_resolve_actual_speaker` + shadow-log block + override conditional only.** No call site remains. Single source becomes `_rc_decision.action`.
- (b) Also delete `ROUTING_USE_RECONCILER` flag (becomes dead).
- (c) Also delete `_count_scene_candidates`, `_face_in_frame`, `_effective_switch_threshold` helpers if no external callers.

**Recommendation: (a) + (b).** (c) is a follow-up cleanup; check external callers first.

### D2 — Shadow-window divergence policy

Phase 4 cutover already shipped (`ROUTING_USE_RECONCILER=True` is the production state). The shadow window served its purpose. P0.10 closes it.

Options:
- (a) Accept ≤ 2% divergence threshold; ship deletion.
- (b) Re-enter shadow with the Bug-W fix; require 7-day clean window; then ship deletion.
- **(c) Treat the Bug-W finding itself as proof the shadow window worked — fix Bug-W (REVISE classification) + delete legacy in the same PR.**
- (d) Abandon P0.10 entirely; keep legacy as permanent debt.

**Recommendation: (c).** Bug-W is THE divergence the shadow window was supposed to catch. Fixing it + deleting in one PR is the correct closure.

### D3 — Bug-W status

Options:
- (a) Follow-up P0.X — file separately, ship P0.10 with Bug-W still present.
- **(b) P0.10 acceptance criterion — must pass before merge. The Bug-W regression test (proposed shape in `tests/p0_10_pre_audit_bug_w_evidence.md`) ships with the deletion.**

**Recommendation: (b)** per auditor's R3. Confirmed by this audit's evidence — Bug-W is in the NEW reconciler, deleting legacy without fixing it locks the bug in.

### D4 — Shadow logging granularity

**Bug-W's discovery required only the minimal "legacy=A, new=B" line.** No richer logging was needed.

Options:
- **(a) Minimal — the existing format is sufficient.**
- (b) Add full state snapshot (audio ref, session state, _persons_in_frame, intent classifier) — pays off only for ambiguous divergences. Bug-W wasn't ambiguous.

**Recommendation: (a).** Shadow is being deleted anyway in P0.10.

### D5 — Shadow infrastructure deletion timing

Options:
- **(a) Same PR as legacy deletion — atomic cleanup.**
- (b) Separate PR after legacy delete validates against post-fix prod boot.

**Recommendation: (a)** — the shadow's whole purpose is comparing legacy vs new; deleting legacy without removing the divergence-log block leaves dead code with a broken contract.

### D6 — Rollback plan

If P0.10 ships and a regression appears within 7 days:

Options:
- (a) Single-file revert (revert the P0.10 commit).
- **(b) Re-enable shadow + feature flag the reconciler (`ROUTING_USE_RECONCILER=False` revert path stays available until P0.10 fully validates).**
- (c) Hot-fix in the reconciler rule set without touching the deletion.

**Recommendation: (b) for the deletion-cycle's first 7 days, then (a) once validation closes.** The `ROUTING_USE_RECONCILER` flag should NOT be deleted in the same PR — keep it as the rollback hatch for one validation window, then a follow-up PR deletes the flag.

This contradicts D1's (b) — revise D1 to (a) only, keep the flag for the validation window.

### D7 — Short-utterance + pyannote-0-segments specific decision

**This is Bug-W's exact signature.** Deserves its own design call.

Options:
- (a) Add `_p0_short_utterance_gap_hold_current` covering `0.3 ≤ utt < 1.0` AND `cur_pid is not None`.
- (b) Generalize `_p0_pure_noise_hold_current` to fire on `utt < 1.0` instead of `utt < 0.3` (effectively restoring the legacy blanket-hold floor).
- (c) Move the audio-gate condition: change `_p0_short_utterance_*_mismatch` rules' `MIN_AUDIO_FOR_SCORE` precondition from "fire only if audio ≥ 0.5s" to "fire if audio ≥ 0.5s; ELSE fall through to a 'hold current' default."
- (d) Add an explicit `_p4_new_stranger_low_match` precondition: do not fire for `utt < MIN_UTTERANCE_SECS`.

**Recommendation: (a)** — explicit new rule with the legacy's gate semantic preserved verbatim. Cleanest, most reviewable; doesn't change Phase 4 cutover's design intent (post-expiry scoring), only fills the in-session gap that was left exposed.

### D8 — Other architectural items surfaced

- **D8.1**: The `RoutingDecision` dataclass (reconciler.py) doesn't appear to carry `cur_person_type` into Bug-W's chain — `_p4_new_stranger_low_match` doesn't differentiate stranger-holder from known-holder. Worth auditing whether other rules silently lose context the legacy passed through. (Low priority; not a Bug-W root cause.)
- **D8.2**: Test-side coverage at `test_pipeline.py:16590-16593` source-inspects `if _routing_action == "switch_enrolled":`. After deletion, this test needs to either retarget the reconciler's action handling OR get deleted as no-longer-relevant.

---

## Appendix — Tests-side references to routing surface (out-of-scope inventory)

Per auditor C2: documented separately, not mixed into deliverable 1.

| Location | Reference | Action needed in P0.10 |
|---|---|---|
| `test_pipeline.py:16590` | `src.find('if _routing_action == "switch_enrolled":')` | Update to scan reconciler dispatch OR delete (test purpose may be obsolete) |
| `test_pipeline.py:16593` | `src.find('elif _routing_action ==', idx + 1)` | Same |

Plus the regression test for Bug-W proposed in `tests/p0_10_pre_audit_bug_w_evidence.md` — ships as a new test in P0.10's acceptance gate.

---

## Acceptance gate check

| Item | Status |
|---|---|
| `tests/p0_10_routing_audit.md` exists with all 5 deliverable sections populated | ✅ |
| All routing paths in pipeline.py + core/ enumerated in deliverable 1 (zero TBD rows) | ✅ — N=1 with 5 path-rows |
| Bug-W mechanism trace (deliverable 2) identifies the specific code path producing `_routing_action == "new_stranger"` | ✅ — pipeline.py:7417-7419 override + reconciler.py:596-621 `_p4_new_stranger_low_match` |
| Every legacy decision in deliverable 3 has KEEP/DROP/REVISE classification in deliverable 4 | ✅ — 21/21 classified (20 KEEP, 1 REVISE, 0 DROP) |
| Positive + Negative contract (deliverable 5) populated | ✅ — 21 positive (C1-C21), 6 negative (N1-N6) |
| D1-D8 decisions explicitly listed with options | ✅ — 8 decisions surfaced, each with 2-4 options + recommendations |
| `tests/p0_10_pre_audit_bug_w_evidence.md` exists with full bug-report shape | ✅ |
| `git status core/` shows zero modifications | ✅ (pure documentation discipline held — Phase 0 audit gate satisfied) |

---

## What this audit does NOT do

- Does not propose Plan v1 implementation
- Does not modify any production code
- Does not modify any test code  
- Does not write the new `_p0_short_utterance_gap_hold_current` rule
- Does not write the Bug-W regression test

All of those land in Plan v1 after architect + auditor review of D1-D8.
