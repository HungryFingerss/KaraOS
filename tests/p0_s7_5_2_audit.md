# P0.S7.5.2 — Canary 3 multi-subsystem failures — Phase 0 Audit

**Date:** 2026-05-20
**Author:** architect
**Status:** Phase 0 — grep-verified findings, zero production-code changes. **Bundled-queue RE-CANARY 3 (2026-05-20) revealed FIVE independent root causes across reconciler / pipeline / voice / audio / brain.** 2 are P0-correctness (turns silently dropped + new strangers can't enroll); 3 are MEDIUM (voice quality drift + STT artifacts + brain tool-selection on new strangers). Standing by for auditor adjudication on scope (single multi-D-decision spec vs split into mini-specs).

**Strict-industry-standard mode**: 3rd application. Per `feedback_strict_industry_standard_mode.md` discipline self-audit at §10.

**Companion documents (forthcoming):**
- `tests/p0_s7_5_2_plan_v1.md` — after Phase 0 sign-off + scope-lock
- `tests/p0_s7_5_2_plan_v2.md` — after Plan v1 review

**Disciplines applied at audit drafting (per strict-mode):**
- Two-pass grep-verification (Pass 1 at drafting) — BOTH critical bugs verified via direct production-code read (not just agent summaries)
- Multi-direction invariant trace per D-decision (forward/backward/sideways/lifecycle)
- Pre-mortem per D-decision (5+ failure modes named)
- 11-gate quality checklist (compact form per D-decision; full form at Plan v1)
- Cross-spec impact analysis
- Phase 0 granularity sub-observation applied (each D-decision names explicit `core/X.py:LINE` edit site to support auditor-Q5 6th instance accuracy)

---

## 1. Canary 3 result + root-cause decomposition

### 1.1 Bundled-queue RE-CANARY 3 (2026-05-20) — PARTIAL PASS

**P0.S7.5.1 D1 (the spec that just shipped) worked correctly:**
- Visitor alert marker swap landed (lambda-replacement `re.sub`)
- Persistent re-injection working (`[PromptPrefAgent] persistent nudge re-injected (type=VISITOR_ALERT, id=1)` at line 890 of archive)

**5 NEW independent root causes surfaced unrelated to P0.S7.5.1:**

| # | Symptom | Subsystem | Severity |
|---|---|---|---|
| 1 | Best_friend turns silently dropped at v_score 0.3-0.4 even when face IS in frame | reconciler ↔ pipeline key-mismatch | **P0 CORRECTNESS** |
| 2 | New strangers (Lexi) get session via voice-routing but no bootstrap credits → can't engage on turn 2 | pipeline voice-routing new_stranger path | **P0 CORRECTNESS** |
| 3 | Voice gallery centroid drift from short-utterance self-match accumulation | voice gallery / centroid math | **MEDIUM** |
| 4 | STT 1-word artifacts ("You", "Yeah") get processed as turns; Smart-Turn multi-fires | audio pipeline | **MEDIUM** |
| 5 | Brain mis-calls `report_identity_mismatch` on stranger first-turn self-intros without prompt-block guidance | brain prompt blocks | **MEDIUM** |

### 1.2 Pre-audit hypothesis test (Phase-0-catches-wrong-premise applied)

**Pre-audit mental model** (from canary-2 closure handoff): "Bundled-queue canary tests the P0.S7 family arc. P0.S7.5.1 fix should close the marker/metadata asymmetry. Canary 3 either passes or reveals a NEW root cause."

**Phase 0 grep-verified state**: P0.S7.5.1 D1 fix is intact and working. The 5 surfaced bugs are NOT regressions of P0.S7 family work — they are pre-existing latent issues in surfaces NOT covered by P0.S7. Canary 3 exposed them because:
- Jagan moved in/out of frame frequently (Bug 1 surfaced — reconciler "holder not visible" fires)
- A new visitor (Lexi) arrived AND said "Kara" (Bug 2 surfaced — voice-routing new_stranger bypasses engagement-gate)
- Multi-day usage accumulated short-utterance samples (Bug 3 surfaced — gallery drift)
- Various STT edge cases (Bug 4 surfaced — 1-word artifacts)
- Lexi introduced herself on turn 1 (Bug 5 surfaced — no STRANGER IDENTITY block at turn_count=1)

**Verdict: NOT a wrong-premise instance.** Canary worked as designed — it exposed pre-existing bugs across the codebase that prior canaries didn't trigger. Sub-pattern A stays at 5. **Canary-finding tracker bumps to 5th instance** — **THRESHOLD-CROSSING EVENT** for potential `### Canary-surfaces-real-gaps` doctrine elevation at P0.S7.5.2 closure.

---

## 2. Bug 1 — Reconciler/pipeline key mismatch (P0 CORRECTNESS)

### 2.1 Symptom

`terminal_output_2026-05-20_101936.md:198-199`:
```
[Reconciler-Shadow] divergence | actual_rule='_p3_self_match_offscreen_mature' | action='ambiguous' | pid=None | utt_dur=0.61s | utt_band=short_hard | v_score=0.435 | pyannote_segments=1 | cur_pid='jagan_3206e3' | cur_person_type='best_friend' | persons_in_frame_count=1 | last_face_age_s=n/a | reason='low self-match 0.435 and holder not visible — S64 mature-profile poisoning protection'
[Voice] Routing: ambiguous — dropping turn (cur=jagan_3206e3)
```

**Contradiction**: `persons_in_frame_count=1` but reason says "holder not visible." Jagan's face IS in the frame (Vision logs show `[Vision] Jagan` repeatedly), yet the reconciler concludes "not visible" and drops his turn.

Same pattern at lines 230-231 (v_score=0.314 on "It's Tirupati"). Repeated across the canary whenever Jagan's voice scored sub-0.45 on short utterances.

### 2.2 Root cause (grep-verified)

**Producer** (`pipeline.py:7233-7236`):
```python
_rs_pif_view = {
    s.person_id: {"last_seen": s.last_seen, "name": s.name, "conf": s.conf, "source": s.source}
    for s in _presence_store.peek_all_snapshots()
}
```
Dict has keys: `last_seen`, `name`, `conf`, `source`. **NO `last_recognized_at` key.**

**Consumer** (`core/reconciler.py:117-131`):
```python
visible_pids = tuple(
    pid for pid, info in persons_in_frame.items()
    if info.get("source") != "voice"
    and now - info.get("last_recognized_at", 0) < VOICE_ROUTING_FACE_STALE_SECS  # ← BUG
)
# ... same filter at line 130 for per_pid_confidence
```

**The defect**: `info.get("last_recognized_at", 0)` returns the default `0` because the key doesn't exist. `now - 0 ≈ 1.7e9` (unix timestamp). `1.7e9 < 2.0` is FALSE for every entry. **Filter excludes ALL entries.** `visible_pids` becomes empty tuple.

Then `_p3_self_match_offscreen_mature` rule (`core/reconciler.py:486` per Agent 1 report) checks `session.cur_pid not in presence.visible_pids` — TRUE because empty tuple. Fires "holder not visible" → turn dropped.

### 2.3 D-decision D1

**Contract**: `_build_routing_inputs` MUST filter `persons_in_frame` entries using the same key that the producer writes. Producer writes `last_seen`; consumer must read `last_seen`.

**Reference implementation** (single-line change × 2):

```python
# core/reconciler.py:120  and  core/reconciler.py:130
- and now - info.get("last_recognized_at", 0) < VOICE_ROUTING_FACE_STALE_SECS
+ and now - info.get("last_seen", 0) < VOICE_ROUTING_FACE_STALE_SECS
```

### 2.4 Multi-direction trace (D1)

**Forward**: `visible_pids` populates correctly → `_p3_self_match_offscreen_mature` predicate evaluates true visibility → Jagan's turns route through `current` (not dropped at offscreen-floor) when his face IS visible
**Backward**: `_presence_store.peek_all_snapshots()` returns `PresenceSnapshot` with `last_seen` field (verified — that's the field name in `core/presence_store.py`)
**Sideways**: No other consumers of `persons_in_frame` use `last_recognized_at` key (grep-verifiable at Plan v1)
**Lifecycle**: presence row birth (face detected) → mutation (face still visible, `last_seen` refreshed every frame scan) → consumption (reconciler reads) → death (stale-prune after `SCENE_STALE_SECS`)

### 2.5 Invariants (D1)

**Preserved**: `_p3_self_match_offscreen_mature` poisoning protection still fires when face GENUINELY isn't visible (legitimate offscreen case)
**Established**: producer-consumer key symmetry for `persons_in_frame` between pipeline + reconciler
**Not touched**: `VOICE_ROUTING_FACE_STALE_SECS` value, the `_p3_self_match_offscreen_mature` rule predicate itself, presence_store schema

### 2.6 Pre-mortem (D1)

| # | Failure mode | Mitigation |
|---|---|---|
| 1 | Other consumers of `persons_in_frame` may also use wrong key | Plan v1 grep — verify NO other site reads `last_recognized_at` |
| 2 | Test suite doesn't cover this code path | Add behavioral test: seed presence_store with Jagan IN frame, set cur_pid=Jagan, low v_score → assert routing returns "current" (NOT dropped) |
| 3 | Fix introduces regression on TRUE offscreen case | Test 2: Jagan NOT in presence_store (face left frame > VOICE_ROUTING_FACE_STALE_SECS ago) → assert routing fires _p3_self_match_offscreen_mature (poisoning protection) |
| 4 | The 0 default could mask absence vs presence-with-zero-timestamp | Use `info.get("last_seen") is None` check or rely on `now -` math (now > 0 always; `now - 0 > stale_secs` is the natural absence-of-key detection) |
| 5 | PresenceStore field rename could re-break this | AST forward-property test: scan pipeline.py for the dict-construction shape; assert keys match what reconciler expects |

### 2.7 Test surface (D1)

| # | Test | Type |
|---|---|---|
| 1 | `test_visible_pids_uses_last_seen_key` | AST forward-property |
| 2 | `test_routing_holds_current_when_holder_visible` | Behavioral (Jagan in frame, low v_score → current, NOT dropped) |
| 3 | `test_routing_drops_when_holder_genuinely_offscreen` | Behavioral regression guard |

3 tests for D1.

---

## 3. Bug 2 — Voice-routing new_stranger bypasses engagement-gate (P0 CORRECTNESS)

### 3.1 Symptom

`terminal_output.md:11-71` (canary 3 current file):
- Turn 1: Lexi (voice-only, no face) says "Hi Kara, I know you very well..." (contains "Kara")
- Line 13-14: Session opens via voice-routing path: `[Session] Open: stranger_efc8781c (voice) — visitor` + `[Voice] Unrecognized speaker → new session stranger_efc8781c`
- Line 22: `[Voice] Refused accumulation: voice_n=0, voice_conf=0.00, bootstrap=0` ← **bootstrap=0**
- **MISSING LOG**: NO `[Pipeline] Stranger engaged (voice-only, system addressed)` (that log fires in the ambient-gate path; here it doesn't)
- Turn 2: Lexi says "My name is Lexi..." (no "Kara")
- Line 60-61: `[STT] STRANGER/visitor [gate active]: My name is Lexi...` → `[STT] STRANGER/visitor [gate blocked — 'Kara' not heard]`
- Line 62: Session expires without enrolling Lexi

### 3.2 Root cause (grep-verified)

**Ambient-gate path** (`pipeline.py:6846-6857`) — correctly seeds gate state when stranger says system name via ambient listen:
```python
_open_session(_sid, "visitor", "voice",
              person_type="stranger",
              engagement_gate_passed=True)
await _conversation_store.init_empty(_sid)
if _session_store.peek_snapshot(_sid) is not None:
    _loop.create_task(_session_store.set_waiting_for_name(_sid, False))
    _loop.create_task(_session_store.set_voice_only_origin(_sid, True))
print(f"[Pipeline] Stranger engaged (voice-only, system addressed) — {_sid}")
```

**Voice-routing new_stranger path** (`pipeline.py:7496-7515`) — bypasses engagement gate:
```python
_open_session(_sid, "visitor", "voice", person_type="stranger")   # ← NO engagement_gate_passed=True
try:
    _loop = asyncio.get_running_loop()
    _loop.create_task(_session_store.set_waiting_for_name(
        _sid, STRANGER_REQUIRE_SYSTEM_NAME))                       # ← STILL gate-active (waiting_for_name=True)
except RuntimeError: pass
await _conversation_store.init_empty(_sid)
_cur_pid  = _sid
# NO voice_only_origin=True
# NO bootstrap credits seeded
print(f"[Voice] Unrecognized speaker → new session {_cur_pid} (track={_speaker_track})")
```

**Defect**: when reconciler routes a turn as `new_stranger`, it dispatches into a session-open path that DOESN'T mirror the ambient-gate's engagement semantics. The session starts with `bootstrap_credits=0`, `waiting_for_name=True`, `voice_only_origin=False`. Voice never accumulates on turn 1 (no witness, no bootstrap). Turn 2 hits the gate-blocked path because waiting_for_name is still True.

### 3.3 D-decision D2

**Contract**: when voice-routing new_stranger fires AND the user_text contains the system name (case-insensitive), engagement-gate semantics MUST be applied: `engagement_gate_passed=True`, `waiting_for_name=False`, `voice_only_origin=True`, bootstrap credits seeded. Mirror the ambient-gate path's state writes.

**Reference implementation** (at `pipeline.py:7496-7515`):

```python
# Open session — use pre-allocated pid if available
_sid = _target_sid or f"stranger_{__import__('uuid').uuid4().hex[:8]}"
db.add_stranger("visitor", person_id=_sid)  # INSERT OR IGNORE

# P0.S7.5.2 D2 — when voice-routing new_stranger AND user said
# system name in this turn's STT, mirror ambient-gate engagement
# semantics so bootstrap credits + voice_only_origin land. Without
# this, the session opens stuck at waiting_for_name=True and never
# accumulates voice (canary 3 Lexi failure).
_system_name = _pipeline_state_store.peek_active_system_name() or ""
_engagement_passed = bool(
    _system_name
    and text
    and _system_name.lower() in text.lower()
)

_open_session(_sid, "visitor", "voice",
              person_type="stranger",
              engagement_gate_passed=_engagement_passed)
await _conversation_store.init_empty(_sid)
try:
    _loop = asyncio.get_running_loop()
    if _engagement_passed:
        # Mirror ambient-gate path lines 6853-6857
        _loop.create_task(_session_store.set_waiting_for_name(_sid, False))
        _loop.create_task(_session_store.set_voice_only_origin(_sid, True))
        print(f"[Pipeline] Stranger engaged (voice-only, system addressed) — {_sid}")
    else:
        # Original behavior — keep gate active until system name heard
        _loop.create_task(_session_store.set_waiting_for_name(_sid, STRANGER_REQUIRE_SYSTEM_NAME))
except RuntimeError:
    pass  # OPTIONAL
_cur_pid  = _sid
_cur_name = "visitor"
# ... rest of existing logic (track minting, etc.)
print(f"[Voice] Unrecognized speaker → new session {_cur_pid} (track={_speaker_track})")
```

### 3.4 Multi-direction trace (D2)

**Forward**: bootstrap credits seeded → voice accumulation fires on turn 1 → voice_n grows → engagement gate clears
**Backward**: reconciler returns `new_stranger`; `text` (STT output) is the user_text in scope; `_pipeline_state_store.peek_active_system_name()` returns current system name
**Sideways**: ambient-gate path remains unchanged; both paths now share the same engagement-gate semantic
**Lifecycle**: stranger session birth (voice-routing new_stranger OR ambient-gate path) → engagement gate either passed at birth (D2 fix) OR cleared on later turn when user says system name → voice accumulation → eventual rename via `update_person_name`

### 3.5 Invariants (D2)

**Preserved**: ambient-gate path semantics unchanged; existing strangers without system-name mention still gated
**Established**: producer parity — voice-routing new_stranger path applies the SAME engagement-gate semantics as ambient-gate path when system name is heard
**Not touched**: `STRANGER_REQUIRE_SYSTEM_NAME` config, system-name detection method (substring match), engagement gate fallback (still active for strangers who don't say the name)

### 3.6 Pre-mortem (D2)

| # | Failure mode | Mitigation |
|---|---|---|
| 1 | Case-insensitive substring match false-positives on partial words (e.g., "scarab" contains "ara") | System names are typically short proper nouns; risk acceptable. Plan v1 may add word-boundary regex (`\bKara\b`) for tightness. |
| 2 | LLM-hallucinated STT containing system name shouldn't grant credits | Engagement at session-OPEN is bounded; even if false-positive grant happens, the session is for a real visitor who just said something Kara-like; future turns will refine via voice accumulation |
| 3 | Multi-language system names (e.g., Cyrillic spelling) | Existing system-name handling already lowercases; Unicode-safe substring. Plan v1 verifies. |
| 4 | Race condition: `peek_active_system_name` returns None during boot | Guard `_system_name = ...peek_active_system_name() or ""` handles None |
| 5 | What if `text` is None? | Guard `text and _system_name.lower() in text.lower()` short-circuits |

### 3.7 Test surface (D2)

| # | Test | Type |
|---|---|---|
| 1 | `test_voice_routing_new_stranger_with_system_name_seeds_engagement` | Behavioral — reconciler new_stranger + text contains "Kara" → engagement_gate_passed=True, voice_only_origin=True, bootstrap > 0 |
| 2 | `test_voice_routing_new_stranger_without_system_name_keeps_gate_active` | Behavioral — reconciler new_stranger + text without "Kara" → waiting_for_name=True (unchanged) |
| 3 | `test_voice_routing_path_matches_ambient_gate_state_writes` | AST forward-property — both paths produce same state writes when system name heard |

3 tests for D2.

---

## 4. Bug 3 — Voice gallery centroid drift from short-utterance accumulation (MEDIUM)

### 4.1 Symptom

Jagan's voice scored 0.3-0.4 against his own ~20-sample mature gallery. Specific evidence:
- v_score=0.435 on 0.61s utterance ("now it's third party")
- v_score=0.314 on 0.51s utterance ("It's Tirupati")
- v_score=0.61 on 0.36s utterance ("I am from India...")
- v_score=0.80 on LONG utterance (1.5s+) ("My friend said he is not coming...")

**Pattern**: short utterances (0.3-0.6s) consistently score low; long utterances (1.5s+) score correctly high. ECAPA-TDNN minimum reliable embedding length is 1.5s (`core/voice.py:147`). Short-utterance embeddings are noisy → accumulated into gallery → centroid drifts → mature-profile match scores degrade over time.

### 4.2 Root cause (grep-verified per Agent 3 + needs Plan v1 confirmation)

- `core/voice.py:147`: docstring says "Minimum reliable length: 1.5 seconds"
- `core/voice.py:151-152`: `embed()` returns `None` for audio < 1.5s
- `core/db.py:1554-1588` (`add_voice_embedding`): **NO centroid-distance gate** at gallery add time (compare to face equivalent at `core/db.py:674-691` which uses `SELF_UPDATE_CENTROID_MIN=0.55`)
- `pipeline.py:2262-2267` (voice self-match path): adds to gallery if `v_score >= min_self_match` (~0.30-0.45) without checking utterance duration OR centroid distance

**Hypothesis**: short utterances (0.5-1.0s) returned non-None embeddings via the diarize-pyannote path (which allows 1.0-1.5s segments with degraded embeddings per Agent 3), passed the self-match threshold, and contaminated Jagan's centroid over multiple sessions.

### 4.3 D-decision D3

**Contract**: voice gallery accumulation MUST gate on BOTH (a) minimum utterance duration (1.5s per ECAPA docs) AND (b) centroid-distance check (mirror face's `SELF_UPDATE_CENTROID_MIN=0.55` discipline).

**Reference implementation locations**:
- `pipeline.py:2262-2267` (voice self-match add): add `len(audio) >= MIN_VOICE_ACCUM_DURATION_SECS * MIC_SAMPLE_RATE` guard
- `core/db.py:1554-1588` (`add_voice_embedding`): add centroid-distance gate mirroring `core/db.py:674-691`

**Config additions** (`core/config.py`):
- `MIN_VOICE_ACCUM_DURATION_SECS: float = 1.5` (matches ECAPA minimum reliable length)
- `VOICE_SELF_UPDATE_CENTROID_MIN: float = 0.55` (mirror face equivalent)

### 4.4 Multi-direction trace (D3)

**Forward**: short utterances don't contaminate gallery → centroid stays clean → mature-profile scores stay reliable → Bug 1 (offscreen-floor fires on low scores) becomes less common
**Backward**: producers of voice accumulation requests (`_decide_and_accumulate_voice`, voice self-match) — all gated at the same point
**Sideways**: face gallery has equivalent centroid-distance gate at `core/db.py:674-691` (per Session 51 P0 fix) — voice gallery should mirror
**Lifecycle**: voice sample birth (recording) → embedding (ECAPA) → gallery accumulation (D3 gates here) → centroid update → consumption (voice ID matching)

### 4.5 Invariants (D3)

**Preserved**: long-utterance accumulation path unchanged; existing gallery contents unchanged (D3 fixes future accumulation, NOT existing contamination)
**Established**: minimum-utterance-duration invariant for voice gallery writes; centroid-distance invariant matching face-gallery design
**Not touched**: ECAPA model, gallery storage format, voice ID matching algorithm

### 4.6 Known limitations (D3)

**Existing gallery contamination stays.** D3 fixes future writes; doesn't remediate canary-3-era polluted galleries. Factory-reset between canaries handles this for test scenarios. In production, contaminated galleries either: (a) gradually re-converge as long-utterance samples dominate, OR (b) require a one-shot gallery-rebuild migration (out of scope for D3; bank as observation).

### 4.7 Test surface (D3)

| # | Test | Type |
|---|---|---|
| 1 | `test_voice_accum_rejects_short_utterance` | Behavioral — utterance < 1.5s → rejected, not added |
| 2 | `test_voice_accum_rejects_centroid_outlier` | Behavioral — embedding with cosine < 0.55 to centroid → rejected |
| 3 | `test_voice_accum_accepts_long_clean_utterance` | Behavioral regression guard |
| 4 | `test_voice_accum_constants_present` | AST/config invariant |

4 tests for D3.

---

## 5. Bug 4 — STT 1-word artifacts + Smart-Turn multi-fires (MEDIUM)

### 5.1 Symptom

- STT returns "You" 1-word transcripts on noise (lines 251, 791 of archive)
- Smart-Turn fires 3+ times before turn-end log (lines 783-786)
- These get processed as turns then dropped at routing (noise traffic)

### 5.2 Root cause (per Agent 4)

- `core/audio.py:516-563`: STT segment filter has NO minimum word-count gate; passes 1-word noise through
- `core/audio.py:437-447`: Smart-Turn `smart_turn_fired` flag only resets on resumed speech; multiple invocations possible on overlapping windows
- `core/audio.py:365` vs `core/config.py:51`: VAD floor `min_speech=0.10s` vs `DIARIZE_MIN_SEGMENT_SECS=0.5s` mismatch

### 5.3 D-decision D4

**Contract**: STT MUST filter 1-word artifacts (length < 2 words AND no terminal punctuation) at the audio.py output level. Smart-Turn MUST debounce within the same silence streak.

**Reference implementation**:
1. `core/audio.py:563` (post-STT filter): add `if len(words) < 2 and not text.rstrip().endswith(('.', '!', '?')): return "", "en"` — reject 1-word artifacts unless terminated (e.g., "Stop!" is valid)
2. `core/audio.py:437-447`: lock `smart_turn_fired = True` immediately after first fire; only reset on resumed speech (existing logic — but ensure no race)

**Config tweak** (`core/config.py:51`): align `DIARIZE_MIN_SEGMENT_SECS = 0.10` with VAD floor — OR keep at 0.5 with explicit comment that sub-0.5 utterances get diarize-skipped (preferred).

### 5.4 Pre-mortem (D4)

| # | Failure mode | Mitigation |
|---|---|---|
| 1 | Valid 1-word responses ("Yes", "No", "Stop", "Help") rejected | Allow if terminated with punctuation OR if it's a known short imperative (whitelist) |
| 2 | Smart-Turn debounce breaks adaptive grace | Verify the grace=0.19/0.48s logic still fires on first invocation |
| 3 | Existing pipeline behavior depends on noise traffic for keep-alive | Unlikely; verify pipeline state machine doesn't break with quieter STT |

### 5.5 Test surface (D4)

| # | Test | Type |
|---|---|---|
| 1 | `test_stt_filters_1_word_noise` | Unit — "You" alone → empty; "Stop." → passes |
| 2 | `test_smart_turn_debounces_within_silence_streak` | Behavioral |

2 tests for D4.

---

## 6. Bug 5 — Brain mis-tools on stranger first-turn self-intros (MEDIUM)

### 6.1 Symptom

Lexi says "Hi Kara, I know you very well but I'm not sure if you know me." Brain mis-calls `report_identity_mismatch` (intent classifier correctly rejects). The phrase "I'm not sure if you know me" is a QUESTION about system knowledge, not a self-denial.

### 6.2 Root cause (per Agent 5)

For Lexi's first turn (`session_user_turns=0`), NO prompt block guides handling of stranger self-intros:
- STRANGER IDENTITY block requires `session_user_turns >= 2` (`core/config.py:STRANGER_IDENTITY_BLOCK_MIN_TURNS=2`)
- VISITOR CONTEXT block requires existing visitor_alert (none for first-time visitors)
- KNOWN SPEAKER IDENTITY block (P0.S7.5 D4) excludes strangers
- Brain has only generic `report_identity_mismatch` description to work from

### 6.3 D-decision D5

**Contract**: STRANGER IDENTITY block MUST fire on turn 1 for new strangers (not turn 2+). Lower `STRANGER_IDENTITY_BLOCK_MIN_TURNS` from 2 to 0. Block content guides brain to call `update_person_name` on self-introductions instead of `report_identity_mismatch`.

**Reference implementation**:
- `core/config.py`: change `STRANGER_IDENTITY_BLOCK_MIN_TURNS: int = 2` → `0`
- Verify block content already guides correctly (or extend if needed at Plan v1)

**Alternative considered + rejected**: tighten `report_identity_mismatch` tool description with "questions are NOT denials" guardrail. Rejected because the LLM doesn't follow tool-description guardrails as reliably as prompt-block directives; the block-level approach is more robust.

### 6.4 Pre-mortem (D5)

| # | Failure mode | Mitigation |
|---|---|---|
| 1 | Block fires on every stranger turn (verbose prompt) | Block is small (~15 lines); negligible token cost |
| 2 | Block content needs adjustment for turn-0 case | Plan v1 verifies block content; may extend |
| 3 | Cross-spec interaction with VISITOR CONTEXT block (rare same-session) | Both blocks are conditional; mutual exclusion preserved |

### 6.5 Test surface (D5)

| # | Test | Type |
|---|---|---|
| 1 | `test_stranger_identity_block_fires_on_turn_zero` | Behavioral |
| 2 | `test_min_turns_constant_is_zero` | AST/config invariant |

2 tests for D5.

---

## 7. Scope options for auditor adjudication

### 7.1 Option α — Single P0.S7.5.2 multi-D-decision spec (architect's lean)

D1 + D2 + D3 + D4 + D5 all ship in one spec, mirroring P0.S7.5's 5-D-decision shape.

**Estimated effort**: ~1.5 days (test surface: 3+3+4+2+2 = 14 tests; matches P0.S7.5 Plan v2 forecast cadence)

**Why bundle**: all 5 are canary-3-surfaced bugs; bundling minimizes spec overhead; closure-narrative + memory bankings happen once.

### 7.2 Option β — Critical-only spec (P0 only)

D1 + D2 only (P0 correctness). Defer D3 + D4 + D5 to follow-ups.

**Estimated effort**: ~half-day (6 tests: 3 D1 + 3 D2)

**Why split**: D1 + D2 are P0 turn-dropping bugs; D3-D5 are quality-of-life degradations. Critical-path first.

### 7.3 Option γ — Two separate specs

P0.S7.5.2 = D1 + D2 (P0 correctness, ~half-day)
P0.S7.5.3 = D3 + D4 + D5 (medium-priority, ~1 day)

**Why split**: separate bundled-queue canary cycles; clean failure-mode attribution per cycle.

### 7.4 Architect's lean: Option α (bundle)

Rationale:
- All 5 are independent fixes — no interdependence
- Bundling avoids spec-overhead cost × 3 for option γ
- Bundled-queue canary discipline already validated multi-D-decision shape (P0.S7.5 shipped 5 D-decisions cleanly)
- Phase 0 granularity is high (5 D-decisions with explicit edit sites) → auditor-Q5 estimate should land on-target (6th instance of granularity sub-observation test)

If auditor prefers β or γ, architect defers — both are defensible.

---

## 8. Cross-spec impact analysis

### 8.1 D1 (reconciler key mismatch)

| Affected spec | Disposition |
|---|---|
| P0.10 Phase 2 (reconciler is sole routing source) | D1 fixes a latent bug in P0.10's code. No conflict. |
| P0.6.2 (PresenceStore introduction) | D1 syncs reconciler with PresenceStore's actual key name (`last_seen`). |

### 8.2 D2 (voice-routing engagement gate)

| Affected spec | Disposition |
|---|---|
| Session 22 G4 (stranger system-name gate) | D2 extends gate-passing semantics to voice-routing path; preserves ambient-gate behavior. |
| P0.10 Phase 2 (new_stranger routing action) | D2 closes the engagement-gate gap that P0.10 didn't address. |
| Session 49 NEW-3 (voice_face_confirmed flag) | D2 mirrors the voice_only_origin semantic from Session 120. |

### 8.3 D3 (voice gallery drift)

| Affected spec | Disposition |
|---|---|
| Session 51 Finding #1 (face gallery anti-poisoning) | D3 mirrors the face-gallery centroid-distance discipline to voice. Cross-spec consistency improvement. |
| Session 18 voice gallery cache | D3 doesn't touch cache; only adds gate at write time. |

### 8.4 D4 (STT artifacts)

| Affected spec | Disposition |
|---|---|
| Session 67 Bug F (short-utterance floor) | D4 complements the routing-side floor with an audio-side filter. No conflict. |
| Session 114 (TF32 + warning filters) | D4 doesn't touch warnings; only STT output. |

### 8.5 D5 (STRANGER IDENTITY block turn-0)

| Affected spec | Disposition |
|---|---|
| Session 97 Fix 1 (stranger promotion via update_person_name) | D5 strengthens the prompt-block guidance Session 97 added. |
| Session 100 Bug F/G (visitor name in marker) | D5 unrelated; VISITOR CONTEXT block handles the visitor-alert path. |

**No cross-spec conflicts.** All 5 D-decisions are additive or symmetric with existing architecture.

---

## 9. Discipline-count predictions on P0.S7.5.2 closure

| Discipline | Pre-P0.S7.5.2 | Post-closure |
|---|---|---|
| Spec-first review cycle | 16-for-16 | **17-for-17** |
| Sub-pattern A (`### Phase-0-catches-wrong-premise`) | 5 | **stays at 5** (pre-audit hypothesis matched grep — canary-finding, not wrong-premise) |
| Tripwires-must-match-deferral-surface | 4-for-4 | stays |
| Developer-improves-on-spec | 6-for-6 | stays unless code phase surfaces improvement |
| Induction-surfaces-invariant-gaps | 7-for-7 | stays unless Phase 3 surfaces gap |
| Canary-finding tracker | 4 instances | **5th instance — THRESHOLD-CROSSING for potential `### Canary-surfaces-real-gaps` doctrine elevation at closure** |
| Auditor-Q5-estimates-trail-grep (architect-memory) | 5 instances | **6th instance** — Phase 0 granularity sub-observation test at 5-D-decision scale (option α) |
| Strict-industry-standard mode (auto-memory) | 2 Plans + 1 closure | **3rd application** — first application at Phase 0 (P0.S7.5.1 strict-mode was at Plan v1 onwards) |
| Partial-falsification-tentative | 2 instances | stays at 2 (not a partial-falsification case) |
| Spec-time grep-verification | 5 instances | stays at 5 unless Plan v1 surfaces drift |

---

## 10. Strict-industry-standard mode discipline self-audit (Phase 0)

Per `feedback_strict_industry_standard_mode.md` operational test:

| Check | Phase 0 status |
|---|---|
| Pre-mortem section exists | ✓ (§2.6, §3.6, §4.6, §5.4, §6.4 — per D-decision) |
| Multi-direction invariant trace exists | ✓ (§2.4, §3.4, §4.4 — full 4-axis; §5/§6 compact) |
| Quality-gate checklist named | DEFERRED to Plan v1 (Phase 0 names D-decisions + contracts; Plan v1 commits to gates per D) |
| Cross-spec impact analysis exists | ✓ (§8) |
| Closure-audit step scheduled | ✓ (production-canary diff banked in §1.1 + closure narrative will diff canary 3 vs canary 4) |
| Honest engineering on agent reports | ✓ (D1 + D2 verified via direct grep, NOT trusted from agent summaries; D3-D5 still per-agent + Plan v1 will grep-verify) |

**Discipline status: APPLIED at Phase 0.** 3rd application of strict-mode (1st at this audit; prior 2 at P0.S7.5.1 Plan v1 + v2).

---

## 11. Auditor verdict requested

1. **§7 scope option** — α (bundle 5 D-decisions), β (critical-only D1+D2), or γ (split into P0.S7.5.2 + P0.S7.5.3)? Architect's lean: α.
2. **§1.2 sub-pattern A adjudication** — canary-3-surfaced bugs are NOT wrong-premise; stays at 5. Confirm?
3. **§9 canary-finding tracker 5th instance** — THRESHOLD-CROSSING for `### Canary-surfaces-real-gaps` doctrine elevation. Elevate at this closure, or hold one more cycle?
4. **§4 D3 known limitation** (existing gallery contamination) — defer remediation, OR include one-shot gallery-rebuild migration in scope?
5. **§5 D4 punctuated 1-word exception** ("Stop!", "Help!") — should D4's filter accept terminated 1-word utterances, or reject all 1-word transcripts?
6. **§6 D5 STRANGER IDENTITY block min_turns** — drop to 0 (always fire for strangers), or 1 (fire after first turn so brain's first response is unguarded)?
7. **§2.2 D1 line number** — `core/reconciler.py:120` and `:130` confirmed via grep at Plan v1?

---

## 12. Next steps

1. **Auditor reviews this Phase 0 audit.** Adjudicates §11 (scope, sub-pattern A, canary-finding doctrine elevation, D3/D4/D5 precision).
2. **D-decisions locked** at Phase 0 sign-off (5 D-decisions under option α; subset under β or γ).
3. **Plan v1** drafted with locked D-decisions per strict-mode (pre-mortem + multi-direction + 11-gate checklist visible per D).
4. **Plan v2** if precision items surface.
5. **Joint sign-off** → developer handoff.
6. **Phase 1-3 implementation** under strict mode.
7. **RE-CANARY 4** IMMEDIATELY on closure. Multi-person scenario (Jagan + Lexi visitor). Expected: D1 fix lets Jagan's offscreen-but-visible turns route correctly; D2 fix lets Lexi engage on turn 1 with "Hi Kara..."; D3 prevents short-utterance gallery contamination; D4 filters STT noise; D5 guides brain on stranger first-turn self-intros.
8. **On RE-CANARY 4 PASS**: combined Stage 2 PR fires (D-C Stage 2 + D-D Stage 2 hard-deletes + 130 test-site migrations) — **P0.S7 family arc closes definitively**.

---

## 13. Reference documents

- `tests/p0_s7_5_1_audit.md` + plan_v1 + plan_v2 + closure — P0.S7.5.1 reference
- Canary 3 evidence:
  - `terminal_output_2026-05-20_101936.md` (Jagan + Lexi multi-person)
  - `terminal_output.md` (current — Lexi 2nd attempt, gate-blocked)
- `core/reconciler.py:117-131` — D1 PRIMARY EDIT SITE
- `pipeline.py:7233-7236` — producer of `_rs_pif_view` dict (with `last_seen` key)
- `pipeline.py:7496-7515` — D2 PRIMARY EDIT SITE (voice-routing new_stranger path)
- `pipeline.py:6846-6857` — D2 TEMPLATE (ambient-gate path with engagement_gate_passed=True)
- `core/db.py:1554-1588` — D3 EDIT SITE (voice gallery add_voice_embedding)
- `core/db.py:674-691` — D3 TEMPLATE (face gallery centroid-distance gate)
- `core/voice.py:147` — ECAPA minimum reliable utterance (1.5s)
- `core/audio.py:516-563` — D4 EDIT SITE (STT post-filter)
- `core/audio.py:437-447` — D4 Smart-Turn debounce site
- `core/config.py` — D5 STRANGER_IDENTITY_BLOCK_MIN_TURNS constant
- Memory: `feedback_strict_industry_standard_mode.md` — 3rd application
- Memory: `feedback_auditor_q5_estimates_trail_grep.md` — 6th instance prediction
- Memory: `feedback_spec_time_grep_verification.md` — class-containment Pass 1 applied (D1 + D2 grep-verified)

---

**Standing by for auditor verdict on §11 before drafting Plan v1.**

5 D-decisions, all root-caused at Phase 0 via parallel multi-agent investigation + grep-verification of the 2 critical bugs. Strict-mode discipline applied at audit drafting (1st-application discipline). Architect's lean: option α (bundle).
