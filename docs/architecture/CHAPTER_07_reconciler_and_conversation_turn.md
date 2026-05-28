> **CHAPTER 07 — Reconciler + Conversation Turn** | Sourced from `everything_about_system.md` §59-71 (verbatim mechanical extraction per Plan v2 §1.6 section-number stability invariant).

---

## 59. The Reconciler — Single Routing Source of Truth

Production routing for every turn flows through one function:

```python
def reconcile(
    claim:    IdentityClaim,
    presence: PresenceState,
    session:  SessionState,
) -> RoutingDecision: ...
```

`reconcile` is pure — no module-level state reads, no I/O, no side effects. Three inputs come from three independent producers:

- **`IdentityClaim`** is built by `core/voice_channel.py::identify_speaker` (Part XXXII §199). It captures voice-side observation only: `pid`, `confidence`, `n_diarize_segments`, `utterance_duration`, optional `raw_segment_scores`, plus a human-readable `reasoning` string. Voice does not read vision state to construct the claim.
- **`PresenceState`** is built by `core/vision_channel.py::observe_scene` (Part XXXII §200). It captures vision-side observation only: `visible_pids`, `unrecognized_track_ids`, `per_pid_confidence`, frame `timestamp`. Vision does not read voice state.
- **`SessionState`** is built by the pipeline immediately before the reconciler call. It snapshots: `cur_pid`, `cur_person_type`, `n_active_sessions`, `voice_gallery_sizes`, `cur_holder_voice_n`, `now`.

The output `RoutingDecision` is a frozen dataclass: `action`, `pid`, `rule` (which rule fired), `utt_band` (`noise` / `gap` / `short_hard` / `normal`), `reasoning`. The `action` is one of: `current`, `switch_enrolled`, `new_stranger`, `ambiguous`, `short_utterance_skip`, `short_utterance_voice_mismatch`, `multi_segment_voice_mismatch`, `no_action`.

## 60. The 22-Rule Cascade — Priority Bands

`reconcile` runs a fixed cascade in deterministic order. Each rule is a pure function `(claim, presence, session) -> Optional[RoutingDecision]`. The first rule that matches wins. If no rule matches (degenerate state), the cascade returns `RoutingDecision(action="no_action", ...)` — a logged escape hatch that should never fire in practice given the cascade's coverage.

The cascade is grouped into 5 priority bands. Each rule carries a `LOWER_BOUND` attribute documenting the minimum utterance duration at which it is eligible to fire (introduced in P0.10 Phase 1; see Part XLIII §287 for the non-decreasing band-ordering invariant).

| Band | Rules | What they handle |
|---|---|---|
| **P0** | `_p0_pure_noise_hold_current`, `_p0_short_utterance_no_session`, `_p0_short_utterance_gap_hold_current`, `_p0_short_utterance_hard_mismatch`, `_p0_short_utterance_ambiguous_multi_session` | Sub-MIN_UTTERANCE_SECS audio: hard-mismatch drops, ambiguous-zone drops, pure-noise hold-current, the Bug-W gap fix (`gap` band, see §60.3) |
| **P1** | `_p1_confident_voice_switch` | Voice score above `SPEAKER_SWITCH_THRESHOLD` and matches a different pid → confident switch |
| **P2** | `_p2_face_assist_switch`, `_p2_voice_face_agree` | Mid-range voice score where face co-presence corroborates the switch |
| **P3** | `_p3_self_match_with_face`, `_p3_self_match_below_floor`, `_p3_above_self_match` | Holder's own voice score relative to self-match floor (gallery-poisoning protection) |
| **P4** | `_p4_pyannote_vouched_stranger`, `_p4_new_stranger_low_match`, `_p4_voice_ambiguous_no_candidates`, `_p4_voice_ambiguous_with_candidates`, `_p4_single_segment_mismatch`, `_p4_multi_segment_mismatch` | Below-threshold voice scores: open new stranger, drop turn, hold ambiguous |
| **P5** | `_p5_no_session_new_stranger`, `_last_resort_ambiguous` | No active session: any real signal opens a stranger session; last-resort fall-through |

The grouping is intentional and load-bearing. P0 fires before P1 because a sub-second utterance scoring 0.85 against the holder is still too short to attribute reliably (high score is artifactual from acoustic prior, not identity match). P3's self-match floor fires before P4's mismatch handling because "current holder said something quiet" must route differently from "stranger said something we can't match."

Every rule is independently unit-tested in `tests/test_reconciler.py`. The cascade is integration-tested by passing pinned `(claim, presence, session)` fixtures captured from real canary failure modes (the Bug-W gap fixture from 2026-05-01 and the negative-cosine fixture from 2026-05-02 are two examples).

### 60.1 P1 — confident voice switch

The simplest case. Voice score above `VOICE_SPEAKER_SWITCH_THRESHOLD` (effective threshold may be higher for thin profiles, see §61) and `claim.pid != session.cur_pid`. Routes to `claim.pid` as `switch_enrolled`. Face agreement is not required — the voice alone is strong enough.

### 60.2 P2 — mid-range switch with face corroboration

Score between the mid-range floor (`VOICE_ROUTING_MIDRANGE_SWITCH_MIN`) and `VOICE_SPEAKER_SWITCH_THRESHOLD`. Voice alone is too weak, but if `claim.pid` also appears in `presence.visible_pids`, the two independent signals agreeing gives confidence to switch. Without face corroboration in this band, the rule returns ambiguous and the turn is dropped.

The `face_assist_min` floor (`VOICE_ROUTING_FACE_ASSIST_MIN = 0.42`) was added in 2026-04-21 Session 67 Bug O after a 0.314 phone-audio score with the holder's face in frame was misattributed. Even with face corroboration, the voice must clear the assist floor.

### 60.3 P0 — short-utterance handling and the Bug-W gap fix

The `_p0_short_utterance_gap_hold_current` rule (added in P0.10 Phase 1, Session ~119+) fires when:
- `utterance_duration` is between `MIN_UTTERANCE_SECS` and `SHORT_UTTERANCE_FLOOR`
- The session is active (`session.cur_pid is not None`)
- No signal disqualifies the holder

This rule fills the **Bug-W coverage gap** (Part XLIII §286): pre-P0.10, a 0.3–0.5s utterance from a known holder with no other signal would fall through every cascade rule and exit `no_action` (turn dropped). The legacy `_resolve_actual_speaker` had a catch-all `return cur_pid, "current"` that incidentally papered over the gap; the reconciler's positive-contract design needed an explicit rule.

The rule tags `utt_band="gap"`. The `EXPECTED_RULES_BY_BAND` invariant (Part XLIII §291) asserts that any rule firing on a `gap` band utterance must be `_p0_short_utterance_gap_hold_current`.

### 60.4 P3 — self-match floors (gallery-poisoning protection)

`_p3_self_match_with_face` covers the common case: voice matches the current holder + face is visible → trust the match. `_p3_above_self_match` covers the offscreen case with a higher floor (`VOICE_ROUTING_SELF_MATCH_OFFSCREEN = 0.45`). `_p3_self_match_below_floor` returns ambiguous when the score is below the absolute floor (`VOICE_ROUTING_SELF_MATCH_FLOOR = 0.30`) — this is the poisoning protection: if the holder's own voice scores below 0.30, the audio is likely something else (replay attack, recorded clip).

P0.11 Bug-W fix did NOT change P3 floors. The poisoning protection is calibrated for mature speakers; bootstrap is handled by a separate path (P5 thin-profile relaxation, §60.6).

### 60.5 P4 — below-threshold voice scores and the negative-cosine fix

The four P4 rules handle voice scores below the switch threshold:

- `_p4_pyannote_vouched_stranger` — pyannote reported 2+ segments (multi-speaker turn) AND ECAPA didn't find a confident match. Open a new stranger session.
- `_p4_new_stranger_low_match` — single-segment turn with score below threshold. Open a new stranger session.
- `_p4_voice_ambiguous_no_candidates` — ambiguous score, no presence candidates → hold current.
- `_p4_voice_ambiguous_with_candidates` — ambiguous score, multiple visible candidates → return ambiguous.

The **negative-cosine fix** (2026-05-02, documented in Part XXXII §202) changed the precondition on `_p4_pyannote_vouched_stranger` and `_p4_new_stranger_low_match` from `claim.confidence == 0.0` (exact equality on gallery miss) to `claim.confidence <= 0.0` and `claim.confidence < VOICE_RECOGNITION_THRESHOLD AND claim.confidence != 0.0` respectively. ECAPA-TDNN routinely returns negative cosines for anti-correlated speakers; the original `== 0.0` check silently dropped these.

### 60.6 P5 — no-session and last-resort

`_p5_no_session_new_stranger` fires when no session is active and there's any real signal — a non-zero `claim.confidence` or a non-empty `presence.unrecognized_track_ids` opens a stranger session. The "thin-profile relaxation" carry-over from `_p3_self_match_with_face`'s historical Priority 3.5 — bootstrap-period strangers with thin profiles are handled by the engagement gate's bootstrap credits (Part XL §266) rather than a routing-cascade special case.

The `_last_resort_ambiguous` rule is the cascade's safety net: returns `ambiguous` when no other rule matched. In a fully-covered cascade this never fires; the P0.10 B2 fail-safe in `pipeline.py` logs `[Reconciler] WARN: no rule fired` if `_rc_decision is None` despite this rule's existence (structural insurance against a future refactor that drops the last-resort rule).

## 61. Effective Switch Threshold (Thin-Profile Adaptation)

The P1 confident-switch floor is not constant. The reconciler reads `session.voice_gallery_sizes[claim.pid]` and applies an adaptive floor:

```python
def _effective_switch_threshold(v_pid: str, sizes: dict[str, int]) -> float:
    n = sizes.get(v_pid, 0)
    if n < N_INITIAL_VOICE:
        return 0.70  # thin profile — require more evidence to switch
    return VOICE_SPEAKER_SWITCH_THRESHOLD  # mature profile — configured threshold (0.50)
```

A mature profile produces stable scores; a thin profile (fewer than `N_INITIAL_VOICE = 5` samples) can spike above the configured threshold on a single utterance that happens to resemble the mean. Requiring 0.70 for thin-profile switches prevents spurious hand-overs early in the profile's life.

The function is part of `core/reconciler.py` (not `pipeline.py` — it's a pure helper consumed by `_p1_confident_voice_switch`).

## 62. `presence.visible_pids` and `unrecognized_track_ids` — How Vision Talks to Routing

The `PresenceState` shape is the contract between the vision channel and the reconciler:

```python
@dataclass(frozen=True)
class PresenceState:
    visible_pids:           tuple[str, ...]        # face-recognised pids in frame
    unrecognized_track_ids: tuple[str, ...]        # SORT track ids without recognition
    per_pid_confidence:     dict[str, float]       # face_match_conf per visible pid
    timestamp:              float = 0.0            # frame timestamp
```

The vision channel emits *what is currently visible*. Stale-state expiry happens upstream (the vision loop applies `SCENE_STALE_SECS` before calling `observe_scene`). The reconciler acts on the snapshot it gets and does not look up "what was visible 30 seconds ago".

`visible_pids` is the face-only roster — voice-only sessions are NOT included (compare the legacy `_persons_in_frame` dict which dual-sourced face + voice and required the `_face_in_frame` helper to disambiguate). The architectural cleanup in Part XXXII makes this explicit by design: vision only sees vision, voice only sees voice, the reconciler integrates.

`unrecognized_track_ids` carries the SORT tracker's track ids for faces detected but not yet recognised. The reconciler uses this for the `_p5_no_session_new_stranger` "any real signal" condition (an unrecognized face is real signal even if no voice match fires).

## 63. The Reconciler-Shadow Block and Band Divergence

`pipeline.py` (~line 7100 pre-P0.10-Phase-2-cleanup) carries a Reconciler-Shadow logging block — a 14-field rich-format log line emitted on every routing decision for observability during the cutover validation window. The block's trigger evolved across phases:

- **Phase 3 (shadow mode):** `_rc_decision.action != _routing_action` — compare the reconciler's decision to the legacy router's decision; log divergences.
- **Phase 4 (cutover) + P0.10:** retargeted to band-divergence detection. The trigger fires when the rule that fired isn't the rule expected for the utterance's `utt_band` per the `EXPECTED_RULES_BY_BAND` map.

The legacy "compare to `_resolve_actual_speaker`" trigger became unworkable after Phase 2 deletion. The retarget to band-divergence was the **developer-improves-on-spec** moment for P0.10 Block C (Part L §327 — 4th instance) — the architectural intent (catch divergences between expected and actual routing) was preserved while the mechanism changed.

The shadow block + the `ROUTING_USE_RECONCILER` flag are scheduled for deletion at the close of the P0.10 validation window (`tests/p0_10_validation_runbook.md`, Part XLIII §292).

## 64. Scene Roster (`_build_scene_block`)

The `<<<SCENE>>>` prompt block is built once per turn and injected into the system prompt. Its inputs are the session state + `presence.visible_pids` + voice-only-offscreen recency. The structure:

```
<<<SCENE>>>
  speaking now: Jagan (best friend)
  also present: Chloe (visitor, recently spoke 4s ago)
  offscreen recent: Sweetie (known, heard 25s ago)
<<<END>>>
```

### 64.1 Sources combined

- **Speaking now** — the current turn's pid (after routing).
- **Also present** — other sessions active in the SessionStore.
- **Offscreen recent** — pids heard within `SCENE_VOICE_STALE` (30s) that no longer have a session.

### 64.2 Dispute label override (Finding M, Session 56)

If a session is `disputed`, it's labeled "disputed identity" regardless of its base person_type. This keeps the SCENE block consistent with the `<<<IDENTITY DISPUTED>>>` block (Part XV §103) — both treat the speaker as unknown until the dispute resolves.

### 64.3 SHA-256 caching (Wave 6 Item 23)

`_build_scene_block` caches its output by SHA-256 of all inputs. Repeated turns with no scene change return the previously-built string directly. See **Part XLVII §304** for the cache architecture and invariants. Gated by `SCENE_BLOCK_CACHE_ENABLED = True`.

### 64.4 Toggle

`SCENE_BLOCK_ENABLED = True` globally. The block is injected every turn. Disabling it removes multi-person awareness from the brain's context — useful only for single-speaker test configurations.

---
---

# Part XI — Engagement Gate and Enrollment

## 65. Stranger Workflow

### 65.1 High-level flow

```
stranger voice detected (v_pid = None, v_score < threshold)
  ↓
new session pid = stranger_<uuid>
session opens, waiting_for_name = True
person_type = "stranger"
no bootstrap credits yet (engagement_gate_passed = False)
  ↓
stranger speaks — gate check
  ↓
did they say the system name?  ← phonetic match (§66)
  ↓
NO                        YES
  ↓                         ↓
Silent        waiting_for_name = False
[gate blocked]  engagement_gate_passed = True (retroactively)
Log, do not respond.   Progressive enroll DB row
                       (§67) + bootstrap credits
                         ↓
                    normal conversation flow
```

### 65.2 `STRANGER_REQUIRE_SYSTEM_NAME` toggle

`True` by default. If we ever want to disable the gate (e.g., for demo scenarios), this flag does it. We keep it on for two reasons:
- Privacy: strangers can't just walk up and start pulling data.
- Feel: the system feels *invited into* conversation rather than *lurking*.

## 66. System-Name Phonetic Gate

### 66.1 `_name_heard_in(text, system_name) -> (bool, method)`

```python
def _name_heard_in(text, system_name):
    # Exact word-boundary match first
    if re.search(r"\b" + re.escape(system_name) + r"\b", text, re.IGNORECASE):
        return True, "exact"
    # Phonetic fallback via jellyfish Double Metaphone
    sys_codes = dmetaphone(system_name)
    for word in re.findall(r"\b\w+\b", text):
        for code in dmetaphone(word):
            if code and code in sys_codes:
                return True, "phonetic"
    return False, None
```

### 66.2 Why phonetic fallback

Whisper isn't perfect. "Kara" may come back as "Cara", "Carah", "Karah", "Carrow". Requiring exact spelling match would fail users whose accent Whisper transcribes differently.

Double Metaphone produces a phonetic code for each word; two words with the same code sound similar. `Kara` → `('KR', None)`, `Cara` → `('KR', None)`. Same code → match.

### 66.3 Word boundary enforcement

The exact-match branch uses `\b...\b` to prevent false positives like "Kara" matching in "reflex". Session 22 G4 fixed this.

### 66.4 The gate in the conversation loop

```python
if _cur_pid and _active_sessions.get(_cur_pid, {}).get("waiting_for_name"):
    _name_heard, _method = _name_heard_in(text, _active_system_name)
    if _name_heard:
        _active_sessions[_cur_pid]["waiting_for_name"] = False
        print(f"[Pipeline] Stranger {_cur_pid} addressed system by name{_method_note} — engaging")
        # Progressive enroll (§67) ...
    else:
        print(f"[STT] STRANGER/{_cur_name} [gate blocked — '{_active_system_name}' not heard]: {text}")
        continue   # skip the turn, no response
```

## 67. Progressive Enrollment

### 67.1 What it does

When a stranger first passes the gate, we:
1. Create a DB row in `persons` with their stranger pid.
2. If a face was captured for this pid in `_unrecognized_embeddings[track_id]`, add that embedding to `embeddings` with `source='progressive_enroll'`.
3. Grant bootstrap credits (6) to the session's identity_evidence.
4. Accumulate the current audio buffer as their first voice sample.

### 67.2 Two branches (Bug C post-review)

```python
_face_captured = False
_gate_track = next((tid for tid, pid in _stranger_track_map.items() if pid == _cur_pid), None)
if _gate_track is not None and _gate_track in _unrecognized_embeddings:
    _gate_emb = _unrecognized_embeddings[_gate_track]
    if db.add_embedding(_cur_pid, _gate_emb, "progressive_enroll"):
        print(f"[Pipeline] Progressive enroll: face embedding stored for {_cur_pid}")
        _face_captured = True

if len(audio_buf) > 0:
    if _face_captured:
        # Real face captured — seed full witness evidence
        _active_sessions[_cur_pid]["voice_face_confirmed"] = True
        _update_identity_evidence(
            _cur_pid,
            face_last_seen_ts=time.time(),
            anti_spoof_live=True,
            face_match_conf=0.50,
            bootstrap_credits=N_INITIAL_VOICE_BOOTSTRAP,
        )
        _t = asyncio.create_task(_accumulate_voice(_cur_pid, audio_buf, db, face_verified=True))
    else:
        # Voice-only — only bootstrap credits; NO face evidence fabrication
        _update_identity_evidence(
            _cur_pid,
            bootstrap_credits=N_INITIAL_VOICE_BOOTSTRAP,
        )
        _t = asyncio.create_task(_accumulate_voice(_cur_pid, audio_buf, db, face_verified=False))
    _voice_tasks.add(_t); _t.add_done_callback(_voice_tasks.discard)
```

### 67.3 Why the split matters

Before the split (Bug C), face evidence was written unconditionally at gate pass. Chloe (voice-only, behind the laptop) had `face_match_conf=0.50` in her evidence despite never being on camera. The brain's `<<<IDENTITY EVIDENCE>>>` block lied, and Path A (face witness) would falsely grant accumulation until the ts aged past 10s. Post-fix, voice-only strangers only get bootstrap credits; the evidence reflects reality.

## 68. First-Boot Enrollment Flow

See §10. Key points:
- Only runs when no best_friend exists in DB.
- Captures 20 face embeddings with explicit user consent.
- Anti-spoof gated.
- Creates the `best_friend` row and sets system_identity.

## 69. Background Enrollment

Not currently enabled. An earlier iteration allowed background enrollment of unknown faces that were consistently seen. Removed because:
- Privacy: background-enrolling a face without consent is creepy.
- Anti-spoof is less reliable passively.
- Progressive enrollment (§67) covers the legitimate cases.

We do, however, track unidentified faces as `silent_observations` — see §119.

---
---

# Part XII — Conversation Flow

## 70. `conversation_turn` Anatomy

This is the function that runs once per turn. It takes a pid, a transcribed user text, and the audio buffer; it produces (via TTS) a spoken response and (via DB writes) a logged turn.

### 70.1 Signature

```python
async def conversation_turn(
    person_id: str,
    text: str,
    audio_buf: np.ndarray,
    *,
    voice_state: dict,
    vision_state: dict,
    ...
) -> None:
```

### 70.2 Flow

1. **Primary-person and state update.** Resolve `_cur_pid` = pid passed in. Set pipeline state to THINKING.
2. **Voice accumulation decision.** Call `_voice_accum_allowed(session)` → if allowed, spawn `_accumulate_voice` task.
3. **History load.** `history = db.load_conversation_history(pid)` — up to `CONVERSATION_HISTORY_LIMIT=100` turns.
4. **System prompt composition.** Call `_build_system_prompt(...)` with all the context blocks.
5. **Memory search callback.** Construct `_make_memory_search_fn(pid, db)` — this is the function the brain calls when it invokes `search_memory`.
6. **Streaming call.** Start the `ask_stream(text, ...)` async generator.
7. **Sentence-streaming TTS.** Pipe tokens into `_sentence_stream`, then `speak_stream`. Tool-call events are intercepted and dispatched.
8. **Truncation check.** After the stream ends, check `finish_reason`. If truncated (Obs 3: `finish_reason in ("length", "content_filter", None)`) AND the response is a single unterminated word, retry via Ollama.
9. **Logging.** `db.log_turn(pid, "user", text)`; `db.log_turn(pid, "assistant", response)`.
10. **Orchestrator notify.** `_brain_orchestrator.notify()` wakes the agent loop.
11. **State update.** Pipeline state → LISTENING.
12. **State.json write.**

## 71. System Prompt Composition

### 71.1 `_build_system_prompt(...)` in `core/brain.py`

Produces a single string containing all the context blocks glued together. The blocks are (in order):

1. **Persona / identity line.** "You are a robot dog named {system_name}. Your best friend is {best_friend_name}. ..."
2. **`<<<SENSORS>>>`** — vision and voice channel state.
3. **`<<<SCENE>>>`** — multi-person scene roster.
4. **`<<<TOOL ACCESS FOR THIS SPEAKER>>>`** — which tools the current speaker's person_type allows.
5. **`<<<IDENTITY EVIDENCE>>>`** — structured evidence dict with verdict.
6. **`<<<IDENTITY DISPUTED>>>`** — only included when session is disputed.
7. **Memory context.** Results of `search_memory` calls if any, injected here.
8. **Emotion context.** Rolling 3-turn dominant emotion per speaker.
9. **Prompt addendum.** PromptPrefAgent's active-preferences string.
10. **Room context.** Cross-person excerpts (when multiple sessions active).
11. **Household context.** Household facts injected if relevant.

### 71.2 Why so many blocks

Each block addresses a specific failure mode we saw in early versions:
- `<<<SENSORS>>>` — prevents the brain from saying "I see you smiling" when vision says no face visible.
- `<<<SCENE>>>` — prevents ignoring other people in the room.
- `<<<TOOL ACCESS>>>` — prevents burning 5 turns trying a blocked tool (Session 61).
- `<<<IDENTITY EVIDENCE>>>` — gives the brain sensor-level trust calibration.
- `<<<IDENTITY DISPUTED>>>` — prevents the brain from treating a claimed identity as real when sensor disagrees.
- Memory context — the brain can't "recall" without explicit memory injection.
- Emotion context — enables "you seem tired today" responses without forcing an emotion-check tool.
- Prompt addendum — communication-style prefs ("keep responses under 2 sentences").
- Room context — cross-person awareness.
- Household context — relationship awareness.

### 71.3 Block order matters

Sensor/scene/tool blocks come before content blocks because:
- The brain uses them to *frame* the content.
- Truncation in the middle of the prompt (rare but possible) is less damaging to the front than the back.

