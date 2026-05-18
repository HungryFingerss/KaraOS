# Bug-W: phantom stranger session on short utterance

**Status:** Documented during P0.10 Phase 0 audit (2026-05-17).
**Source:** Live boot log `terminal_output_2026-05-17_143659.md`, lines 685–696.
**Discovered during:** P0.9 prod-DB validation gate. Flagged by reviewer + auditor as a P0.10 acceptance criterion (auditor's R3).

---

## Trigger signature

| Field | Value |
|---|---|
| text | `"Thank you."` |
| utterance_duration_s | 0.45 |
| voice_score (v_score) | 0.021 |
| voice_pid (v_pid) | None (gallery miss) |
| pyannote_segments (n_diarize_segments) | 0 |
| n_active_sessions | 2 (Jagan + Lexi already in room) |
| prior cur_pid | Jagan's session (active, mature voice profile) |
| `_persons_in_frame` | Jagan visible (face-sourced) |
| `cur_holder_voice_n` | ≥ N_INITIAL_VOICE (Jagan is mature) |
| cur_person_type | `"best_friend"` |

## Expected behavior

**`(cur_pid, "current")`** — hold the current session, do NOT open a stranger.

Rationale: 0.45s is well below the legacy 1.0s `VOICE_ROUTING_MIN_UTTERANCE_SECS` floor AND below the new reconciler's documented 0.3s `VOICE_ROUTING_NOISE_FLOOR_SECS` only in interpretation — the legacy router's Priority 0 (pipeline.py:1206-1237) has a catch-all fallback at L1233 that returns "current" for any `utterance_duration < MIN_UTTERANCE_SECS` AND `cur_pid is not None`. That fallback covered the 0.3–0.5s gap that the new reconciler accidentally exposed.

## Actual behavior

**Opened phantom stranger session** `stranger_c907181f` despite the legacy router correctly returning `"current"` at the same call.

Confirmed by boot log:
- L689: `[Voice] 14:36:17.974 Routing: current (short utterance 0.45s < 1.0s floor)` ← legacy CORRECT
- L691: `[Reconciler-Shadow] 14:36:17.995 divergence: legacy='current' new='new_stranger' rule='_p4_new_stranger_low_match' pid=None reason='new stranger — score 0.021 < threshold 0.25'`
- L692: `[Room] Participant joined: visitor (stranger_c907181f) → room_1779008452_83f4ea (now 3 participant(s))`
- L693: `[Session] Open: stranger_c907181f (voice) — visitor`
- L694: `[Voice] Unrecognized speaker → new session stranger_c907181f`

Phase 4 cutover (`ROUTING_USE_RECONCILER=True`) makes the reconciler the primary router; legacy decision is shadow-only. The wrong decision was dispatched.

## Boot log evidence (verbatim L685–L696)

```
[STT] 14:36:17.316 (206ms) 'Thank you.'
[Audio] Listening...
[Pipeline] State: LISTENING -> THINKING
[Voice] diarize: pyannote returned 0 segment(s)
[Voice] 14:36:17.974 Routing: current (short utterance 0.45s < 1.0s floor)
[Voice] diarize: pyannote returned 0 segment(s)
[Reconciler-Shadow] 14:36:17.995 divergence: legacy='current' new='new_stranger' rule='_p4_new_stranger_low_match' pid=None reason='new stranger — score 0.021 < threshold 0.25'
[Room] Participant joined: visitor (stranger_c907181f) → room_1779008452_83f4ea (now 3 participant(s))
[Session] Open: stranger_c907181f (voice) — visitor
[Voice] Unrecognized speaker → new session stranger_c907181f (track=None)
[STT] STRANGER/visitor (voice=0.02): Thank you.
[Pipeline] Turn start 14:36:17.996: visitor — 'Thank you.'
```

## State snapshot at failure point

Reconstructed from boot log surrounding context (multi-person session with Jagan + Lexi):

- `cur_pid` = Jagan's session (last_spoke_at recent — within the conversation)
- `_persons_in_frame` = {Jagan: face-sourced, recent}
- `_voice_gallery_sizes[cur_pid]` ≥ `N_INITIAL_VOICE` (Jagan's voice profile is mature)
- `unrecognized_tracks` = {} (no unrecognized faces in scene at that moment)
- `_session_store.peek_all_snapshots()` count = 2 (Jagan + Lexi)

## Mechanism trace

**Single source of `_routing_action` for the dispatch at pipeline.py:7474**: the conditional reconciler-vs-legacy override block at pipeline.py:7417-7419:

```python
if ROUTING_USE_RECONCILER and _rc_decision is not None:
    _resolved_pid = _rc_decision.pid
    _routing_action = _rc_decision.action
```

`ROUTING_USE_RECONCILER=True` (Phase 4 cutover, set in `core/config.py`) → the dispatched `_routing_action` IS the new reconciler's output, NOT the legacy's. Legacy is shadow-only.

The new reconciler's RULES list (reconciler.py:797-817) runs in order. For this input:

| Rule | Verdict | Why |
|---|---|---|
| `_p0_short_utterance_hard_mismatch` | None (returns None) | Requires `utterance_duration >= VOICE_ROUTING_MIN_AUDIO_FOR_SCORE` (0.5s); 0.45s < 0.5s **fails the audio gate** |
| `_p0_short_utterance_ambiguous_multi_session` | None | Same `MIN_AUDIO_FOR_SCORE` gate fails |
| `_p0_pure_noise_hold_current` | None | Requires `utterance_duration < VOICE_ROUTING_NOISE_FLOOR_SECS` (0.3s); 0.45s > 0.3s **above the noise floor** |
| `_p0_short_utterance_no_session` | None | `cur_pid is not None` |
| `_p1_confident_voice_switch` | None | `v_pid is None` |
| `_p2_*` rules | None | All require `v_pid is not None` |
| `_p3_*` rules | None | All require `v_pid is not None` |
| `_p3_5_bootstrapping_stranger_hold` | None | `cur_person_type='best_friend'`, not stranger |
| `_p4_multi_segment_mismatch` | None | `n_diarize_segments=0`, not ≥2 |
| `_p4_pyannote_vouched_stranger` | None | `n_diarize_segments=0`, requires ≥2 |
| **`_p4_new_stranger_low_match`** | **fires** | `claim.pid is None ✓, session.cur_pid is not None ✓, claim.confidence (0.021) < VOICE_RECOGNITION_THRESHOLD (0.25) ✓, claim.confidence != 0.0 ✓` → returns `("new_stranger", None, ...)` |

**Root cause:**

The new reconciler's Priority 0 rules collectively gate the "hold current on short utterance" decision behind one of two preconditions:

- `utterance_duration < VOICE_ROUTING_NOISE_FLOOR_SECS` (0.3s) → `_p0_pure_noise_hold_current` fires
- `utterance_duration >= VOICE_ROUTING_MIN_AUDIO_FOR_SCORE` (0.5s) → `_p0_short_utterance_*_mismatch` fires (if score below floor)

The **0.3s–0.5s utterance band** has NO P0 rule that fires. Anything in that gap falls through P1/P2/P3 (which all require `v_pid is not None`), through P3.5 (which requires stranger holder), and lands on `_p4_new_stranger_low_match` — which fires unconditionally on `(no v_pid match, session active, score below threshold, score != 0.0)`.

Legacy router's Priority 0 (pipeline.py:1206-1237) had a catch-all `return cur_pid, "current"` at L1233 for ANY `utterance_duration < MIN_UTTERANCE_SECS` with `cur_pid is not None`. That catch-all is the missing safety net.

**The Phase 4 cutover removed the 1.0s blanket-hold floor (reconciler.py:222-223 comment):** "removes the old 1.0s blanket-hold floor so post-expiry voices are scored rather than silently mis-attributed." That change was intentional for post-expiry scenarios but accidentally exposed the 0.3–0.5s band for in-session noise.

## Reproduction

**Deterministic minimal:** any input matching:
- `claim.utterance_duration` ∈ [0.3, 0.5)
- `claim.confidence` ∈ (0.0, VOICE_RECOGNITION_THRESHOLD) — i.e. positive but below 0.25
- `claim.pid is None`
- `session.cur_pid is not None`
- `claim.n_diarize_segments` ∈ {0, 1}

Triggers `_p4_new_stranger_low_match` and opens a phantom stranger session.

**Synthetic reproduction (proposed test fixture for P0.10's acceptance criterion):**

```python
def test_bug_w_short_utterance_gap_holds_current_session():
    """Bug-W: utterance in 0.3-0.5s band with active session and low
    voice score must hold current — not open a phantom stranger."""
    from core.reconciler import reconcile, IdentityClaim, PresenceState, SessionState

    claim = IdentityClaim(
        pid=None, confidence=0.021,
        utterance_duration=0.45, n_diarize_segments=0,
        reasoning="ECAPA gallery miss on short utt",
    )
    presence = PresenceState(persons_in_frame={"jagan_001": ...}, unrecognized_tracks={})
    session = SessionState(
        cur_pid="jagan_001", cur_person_type="best_friend",
        n_active_sessions=2, voice_gallery_sizes={"jagan_001": 30},
        cur_holder_voice_n=30,
    )

    decision = reconcile(claim, presence, session)

    assert decision.action == "current", (
        f"Bug-W regression: 0.45s utterance with low voice score opened "
        f"action={decision.action!r} (rule={decision.rule_fired!r}); "
        "expected 'current' — the 0.3-0.5s band must hold the session "
        "to prevent phantom stranger sessions on short social closers."
    )
    assert decision.pid == "jagan_001"
```

This test ships as part of P0.10's acceptance gate (auditor's R3).

## Bug-W's classification

**Decision pending** — see audit deliverable 4 (KEEP/DROP/REVISE).

Provisional read from this evidence: **REVISE** (legacy's catch-all "current" fallback is the correct behavior for the 0.3–0.5s band, but the implementation should be explicit — a new rule `_p0_short_utterance_gap_hold_current` that fires for the documented band rather than relying on a fall-through). The Phase 4 cutover's removal of the blanket 1.0s floor was correct for post-expiry but needs the 0.3–0.5s gap re-covered by an explicit rule.

The architect + auditor confirm this classification during Plan v1 review.

## P0.10 acceptance criterion

Plan v1 MUST include a regression test pinning Bug-W's failure mode. The above synthetic reproduction is the proposed test shape. If P0.10 ships and Bug-W's exact input still produces `new_stranger`, the deletion isn't safe — the legacy was guarding against a real regression in the new reconciler.
