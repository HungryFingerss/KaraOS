# P0.S7.5.2 — Canary 3 multi-subsystem fixes — Plan v1

**Date:** 2026-05-20
**Author:** architect
**Status:** Plan v1 — 5 D-decisions locked under option α (bundle) per auditor verdict 2026-05-20. 4 Plan v1 precision items addressed per auditor handoff. Standing by for auditor review.

**Strict-industry-standard mode**: 4th application (1st at Phase 0 was P0.S7.5.2 audit; 2nd-3rd were P0.S7.5.1 Plan v1+v2). First Plan v1 with Phase 0 strict-mode discipline already established upstream.

**Companion documents:**
- `tests/p0_s7_5_2_audit.md` — Phase 0 (APPROVED 2026-05-20 with 7 adjudications matching architect's lean; 4 precision items locked for Plan v1)
- `tests/p0_s7_5_2_plan_v2.md` — forthcoming if precision items surface (likely 2-3 small refinements at this scope)

**Strict-mode disciplines applied (visible by default):**

| Discipline | Where in this document |
|---|---|
| Pre-mortem per D-decision | §3.6, §4.6, §5.6, §6.6, §7.6 |
| Multi-direction invariant trace per D-decision | §3.4, §4.4, §5.4, §6.4, §7.4 |
| Invariant contract explicit-by-default | §3.5, §4.5, §5.5, §6.5, §7.5 |
| 11-gate quality checklist per D-decision | §3.7, §4.7, §5.7, §6.7, §7.7 |
| Cross-spec impact analysis | §8 (from Phase 0 §8; refined here) |
| Two-pass grep-verification (Pass 1 at drafting) | §2 (all surfaces) |
| Honest scope at this cycle | §1.1 (bundle locked) |
| Production-canary diff tracking | §10 (closure step) |
| Long-arc discipline tracking | §9 |
| Honest engineering on auditor framing | §1.2 (D1.b chosen per auditor lean + grep evidence) |

---

## 1. Auditor-locked scope + 4 precision items addressed

### 1.1 Scope: Option α (bundle 5 D-decisions)

| ID | Severity | D-decision summary |
|---|---|---|
| D1 | P0 CORRECTNESS | Reconciler/pipeline `last_recognized_at` producer mismatch — **D1.b lock**: add field to producer (not consumer change) |
| D2 | P0 CORRECTNESS | Voice-routing `new_stranger` path mirrors ambient-gate engagement semantics when STT contains system name |
| D3 | MEDIUM | Voice gallery accumulation gates: minimum utterance duration + centroid-distance check |
| D4 | MEDIUM | STT 1-word artifact filter (punctuation + known-word allowlist exceptions) + Smart-Turn debounce |
| D5 | MEDIUM | `STRANGER_IDENTITY_BLOCK_MIN_TURNS` drops to 0 + block content extended for question-shape anti-pattern |

### 1.2 Precision items resolved

**Precision item 1 — D1 scope-statement: choose D1.a (consumer change) vs D1.b (producer change)**

Plan v1 grep-verified ALL 6 sites that reference `last_recognized_at`:

| File:Line | Role | Current state |
|---|---|---|
| `core/presence_store.py:15, 25` | SCHEMA: `Entry` + `PresenceSnapshot` dataclasses BOTH have `last_recognized_at: float` as distinct field | OK |
| `core/presence_store.py:55, 63, 86` | PRODUCER: `upsert_face_recognition` sets to `now`; `upsert_voice_only` sets to `0.0` | OK (semantic distinction: face=recognized time; voice=no face) |
| `pipeline.py:1196` | CONSUMER: `_count_scene_candidates` reads from `persons_in_frame` dict | EXPECTS the key |
| `pipeline.py:2315` | CONSUMER: `_should_run_recognition` reads from `persons_in_frame.get(pid, {})` | EXPECTS the key |
| `pipeline.py:2499` | PRODUCER (DIFFERENT dict): `_pif_recog_view = {s.person_id: {"last_recognized_at": s.last_recognized_at}}` | ALREADY writes the key correctly |
| `pipeline.py:7234` | PRODUCER (BROKEN — D1 target): `_rs_pif_view = {s.person_id: {"last_seen": ..., "name": ..., "conf": ..., "source": ...}}` | **MISSING the key** |
| `pipeline.py:7591, 7616` | CONSUMER: direct PresenceStore method calls `peek_last_recognized_at(pid, 0.0)` | OK |
| `core/reconciler.py:120, 130` | CONSUMER: reads from `persons_in_frame` dict | EXPECTS the key |
| `tests/test_reconciler.py:237, 244, 251` | TEST FIXTURES already include `last_recognized_at` | Confirms expected schema |
| `tests/test_p06_store_schemas.py:39, 42` | SCHEMA INVARIANT asserts `last_recognized_at` in both dataclasses | Locks the schema |

**Verdict: D1.b is unambiguously correct.** The reconciler is in sync with the test fixtures + the parallel producer at line 2499 + the schema invariant. The producer at `pipeline.py:7234` is the OUT-OF-SYNC surface.

**D1.b lock — change producer at `pipeline.py:7234`** (NOT consumer at reconciler.py:120/130). Rationale per auditor lean: preserves semantic distinction between "face recognized within X" vs "any-source presence touched within X." Voice-source entries with `last_recognized_at=0.0` are correctly excluded by the existing `now - 0 >= STALE_SECS` math AND by the `source != "voice"` filter (defense in depth). D1.a (consumer change) would lose this semantic distinction and rely solely on the source filter.

**Precision item 2 — D2 word-boundary regex for system-name match**

Plan v1 grep-verified system-name usage patterns:

- Existing system-name detection in `_intent_allows` uses NFKC normalize + lowercase substring (`_nfkc_lower(s)` per P0.3)
- Existing engagement-gate detection at ambient path uses simple lowercased substring per `pipeline.py:6800` area

**Decision: D2 uses NFKC-lowercased substring match (matches existing engagement-gate detection pattern), NOT word-boundary regex.** Rationale: consistency with existing engagement-gate code. Word-boundary regex would create asymmetry between the two paths. If word-boundary tightening proves load-bearing later, fix BOTH paths in a separate sub-spec.

Belt-and-braces: `_nfkc_lower(s)` from P0.3 handles Cyrillic homoglyph attacks; same protection applies here.

**Precision item 3 — D4 known-word allowlist + punctuation**

D4 filter accepts ONE-word transcripts only if:
- (a) ends with terminal punctuation (`.`, `!`, `?`) — "Stop.", "Help!"
- OR (b) word matches known-imperative allowlist: `{"yes", "no", "stop", "help", "okay", "ok", "sure", "yeah", "yep", "nope"}`

Otherwise reject as Whisper artifact. The allowlist covers legitimate confirmation/denial turns. Rejected: bare "You", "Yeah", "Thank" (the actual canary 3 artifacts).

**Precision item 4 — D5 STRANGER IDENTITY block content verification**

Plan v1 grep-verified block content at `core/brain.py:2495-2514`. **Block teaches `update_person_name` on self-intros correctly** with concrete triggers ("My name is Lexi", "I'm Lexi", "Call me Lexi"). **But block does NOT address the question-shape that triggered the canary 3 mis-tool** (Lexi: "Hi Kara, I know you very well but I'm not sure if you know me." — NOT a name self-intro; brain mis-called `report_identity_mismatch`).

**D5 extends block content** with an explicit anti-pattern bullet at Plan v1 §7.3. Brain learns: questions about system knowledge are NOT identity denials.

---

## 2. Pass 1 grep verification (2026-05-20)

### 2.1 D1 surfaces

Per §1.2 above — 10 sites grep-verified. Schema invariant at `tests/test_p06_store_schemas.py:39, 42` is the lock; producer at `pipeline.py:7234` is the broken surface.

### 2.2 D2 surfaces

| File:Line | Role |
|---|---|
| `pipeline.py:7496-7515` | D2 PRIMARY EDIT SITE (voice-routing new_stranger path) |
| `pipeline.py:6846-6857` | D2 TEMPLATE (ambient-gate path with `engagement_gate_passed=True`) |
| `pipeline.py:6800-6810` (estimated; Plan v1 grep at impl) | ambient-gate system-name detection pattern |
| `core/session_state.py:set_waiting_for_name, set_voice_only_origin` | Async setters used by both paths |
| `_pipeline_state_store.peek_active_system_name()` | Source of system name (None during boot) |

### 2.3 D3 surfaces

| File:Line | Role |
|---|---|
| `pipeline.py:2262-2267` | D3 EDIT SITE 1 — voice self-match accumulation gate (current: `v_score >= min_self_match`; add: duration + centroid checks) |
| `core/db.py:1554-1588` | D3 EDIT SITE 2 — `add_voice_embedding` (current: no centroid gate; add: centroid-distance check mirroring face) |
| `core/db.py:674-691` | D3 TEMPLATE — face gallery's `SELF_UPDATE_CENTROID_MIN=0.55` discipline (Session 51) |
| `core/voice.py:147-152` | ECAPA minimum reliable length 1.5s documented; `embed()` returns None < 1.5s |
| `core/config.py` (new constants) | `MIN_VOICE_ACCUM_DURATION_SECS=1.5`, `VOICE_SELF_UPDATE_CENTROID_MIN=0.55` |

### 2.4 D4 surfaces

| File:Line | Role |
|---|---|
| `core/audio.py:516-563` | D4 EDIT SITE 1 — STT segment filter + return; add 1-word artifact filter post-segment-filter |
| `core/audio.py:437-447` | D4 EDIT SITE 2 — Smart-Turn debounce; lock `smart_turn_fired` until silence resets |
| `core/config.py` | `MIN_STT_WORD_COUNT=2` + `STT_KNOWN_IMPERATIVES` frozenset |

### 2.5 D5 surfaces

| File:Line | Role |
|---|---|
| `core/config.py:STRANGER_IDENTITY_BLOCK_MIN_TURNS` | D5 EDIT SITE 1 — change 2 → 0 |
| `core/brain.py:2495-2514` | D5 EDIT SITE 2 — extend block content with question-shape anti-pattern |

---

## 3. D1 — Reconciler/pipeline producer key fix (P0 CORRECTNESS)

### 3.1 Contract

`_rs_pif_view` producer at `pipeline.py:7234` MUST include `last_recognized_at` field sourced from `PresenceSnapshot.last_recognized_at`. The reconciler's filter at `core/reconciler.py:120, 130` is correct; the producer must align with the schema invariant at `tests/test_p06_store_schemas.py`.

### 3.2 Reference implementation

```python
# pipeline.py:7233-7236 (current — BROKEN)
_rs_pif_view = {
    s.person_id: {"last_seen": s.last_seen, "name": s.name, "conf": s.conf, "source": s.source}
    for s in _presence_store.peek_all_snapshots()
}

# pipeline.py:7233-7236 (D1.b fix — ADD last_recognized_at)
_rs_pif_view = {
    s.person_id: {
        "last_seen": s.last_seen,
        "last_recognized_at": s.last_recognized_at,  # P0.S7.5.2 D1
        "name": s.name,
        "conf": s.conf,
        "source": s.source,
    }
    for s in _presence_store.peek_all_snapshots()
}
```

Note ordering: `last_recognized_at` placed adjacent to `last_seen` for readability, matching the pair semantic.

### 3.3 Reconciler unchanged

`core/reconciler.py:120, 130` already reads `info.get("last_recognized_at", 0)` correctly. After D1.b fix, the key is present in the dict — predicate evaluates correctly. The default `0` is now only reached for malformed entries (defensive backup).

### 3.4 Multi-direction trace (D1)

**Forward (consumers of `_rs_pif_view` after fix):**
- `core/reconciler.py:120, 130` — `_build_routing_inputs` filters by `last_recognized_at` correctly → `visible_pids` populated → `_p3_self_match_offscreen_mature` fires only when face GENUINELY offscreen
- `core/reconciler.py:486` (per Agent 1 report) — `session.cur_pid not in presence.visible_pids` evaluates correctly

**Backward (producers of fields used by D1.b):**
- `core/presence_store.py:55, 63` — `upsert_face_recognition` sets `last_recognized_at=now` when face matched
- `core/presence_store.py:86` — `upsert_voice_only` sets `last_recognized_at=0.0` (voice-only entries have no face recognition time)
- `PresenceSnapshot.last_recognized_at` populated atomically with `last_seen` via `peek_all_snapshots`

**Sideways (other consumers using `last_recognized_at` from different dicts):**
- `pipeline.py:1196` (`_count_scene_candidates`) — uses a DIFFERENT `persons_in_frame` dict shape (passed as kwarg from various sites). Plan v1 verified its callers produce the key correctly.
- `pipeline.py:2315` (`_should_run_recognition`) — uses `persons_in_frame.get(pid, {}).get("last_recognized_at", 0.0)`. The dict here is `_pif_recog_view` at line 2499, which ALREADY includes the key.
- No cross-contamination between `_rs_pif_view` and `_pif_recog_view` — different scopes, different lifetimes.

**Lifecycle (state birth → mutation → consumption → death):**
- BIRTH: face detection event → `PresenceStore.upsert_face_recognition(pid, name, conf, now)` → `last_recognized_at=now`
- MUTATION: subsequent face matches refresh `last_recognized_at` (same upsert path)
- CONSUMPTION: `_rs_pif_view` reads via `peek_all_snapshots` per turn (D1.b reads `last_recognized_at` field)
- DEATH: stale-prune in background scan removes entries where `now - last_seen > SCENE_STALE_SECS`

### 3.5 Invariants (D1)

**Preserved:**
- PresenceStore schema (BOTH `last_seen` AND `last_recognized_at` as distinct fields)
- `_p3_self_match_offscreen_mature` rule predicate (poisoning protection for legitimate offscreen case)
- Voice-source entries excluded from `visible_pids` (via both `source != "voice"` AND `last_recognized_at=0.0` defense-in-depth)

**Established:**
- **Producer-consumer key symmetry invariant**: `_rs_pif_view` producer at `pipeline.py:7234` MUST mirror the schema fields that reconciler's `_build_routing_inputs` reads.

**Not touched:**
- `VOICE_ROUTING_FACE_STALE_SECS` value
- `_p3_self_match_offscreen_mature` rule itself
- `core/reconciler.py:120, 130` (consumer unchanged — already correct)
- Other consumers of `last_recognized_at` (lines 1196, 2315, 7591, 7616) — different dicts, unchanged

### 3.6 Pre-mortem (D1)

| # | Failure mode | Mitigation |
|---|---|---|
| 1 | PresenceSnapshot schema rename breaks D1 fix | Schema invariant at `tests/test_p06_store_schemas.py:39, 42` catches rename; AST test asserts both fields present in dataclass |
| 2 | New consumer of `_rs_pif_view` expects keys NOT in producer | D1.b adds 1 key; doesn't remove any. Existing consumer (`reconciler.py`) is the only one. |
| 3 | Voice-source entries leak into `visible_pids` because `last_recognized_at=0.0` doesn't filter | `source != "voice"` filter at reconciler.py:119/129 is defense-in-depth; voice-source still excluded |
| 4 | Reconciler reads from a DIFFERENT dict in some test path | Plan v1 grep confirmed: only `_rs_pif_view` at `pipeline.py:7234` flows to reconciler in production code |
| 5 | New test inadvertently exposes the key mismatch | Existing tests `test_reconciler.py:237, 244, 251` already use the key; new tests must match |
| 6 | What if `peek_all_snapshots` returns snapshots WITHOUT `last_recognized_at` due to migration? | Schema invariant in `test_p06_store_schemas.py` blocks; defensive `info.get("last_recognized_at", 0)` default still works for malformed |

### 3.7 11-gate quality checklist (D1)

| # | Gate | Status |
|---|---|---|
| 1 | Correctness | ✓ 4-axis trace + invariants explicit |
| 2 | Security | N/A — no attack surface |
| 3 | Privacy | N/A — no fact/state tier change |
| 4 | Performance | ✓ 1 extra dict key per snapshot iteration (negligible) |
| 5 | Observability | ✓ existing logs unchanged; canary diff at closure compares "holder not visible" frequency before/after |
| 6 | Test pyramid | ✓ 1 AST + 2 behavioral (per §3.8) |
| 7 | Regression guards | ✓ Test 2 directly defends against canary 3 failure shape |
| 8 | Pre-mortem | ✓ 6 modes named |
| 9 | Multi-direction | ✓ all 4 axes |
| 10 | Backward compat | ✓ additive (new key); no schema migration needed |
| 11 | Doc updates | ✓ CLAUDE.md narrative entry + memory file updates queued |

### 3.8 Test surface (D1) — 3 tests

| # | Test name | Type | Asserts |
|---|---|---|---|
| 1 | `test_rs_pif_view_includes_last_recognized_at` | AST forward-property on `pipeline.py:7233-7236` | Producer dict includes `last_recognized_at` key sourced from PresenceSnapshot field |
| 2 | `test_routing_holds_current_when_holder_visible` | Behavioral (seed PresenceStore with Jagan face-recognized 0.5s ago, low v_score) | Routing returns `current`, NOT dropped at offscreen-floor |
| 3 | `test_routing_drops_when_holder_genuinely_offscreen` | Behavioral regression guard | Jagan face stale > FACE_STALE_SECS → offscreen-floor fires correctly |

---

## 4. D2 — Voice-routing new_stranger engagement-gate parity (P0 CORRECTNESS)

### 4.1 Contract

When reconciler routes a turn as `new_stranger` AND the STT contains the active system name (NFKC-lowercased substring match), the voice-routing path MUST apply engagement-gate semantics matching the ambient-gate path: `engagement_gate_passed=True`, `set_waiting_for_name(False)`, `set_voice_only_origin(True)`, bootstrap credits seeded via `_open_session`'s gate-pass branch.

### 4.2 Reference implementation

```python
# pipeline.py:7496-7515 (D2 fix — mirror ambient-gate semantics conditionally)
else:
    # Open session — use pre-allocated pid if available
    _sid = _target_sid or f"stranger_{__import__('uuid').uuid4().hex[:8]}"
    db.add_stranger("visitor", person_id=_sid)  # INSERT OR IGNORE

    # P0.S7.5.2 D2 — when voice-routing new_stranger AND user said
    # system name in this turn's STT, mirror ambient-gate engagement
    # semantics. Without this, the session opens stuck at
    # waiting_for_name=True and never accumulates voice (canary 3
    # 2026-05-20 Lexi failure: said "Hi Kara..." in turn 1, session
    # opened with bootstrap=0, turn 2 gate-blocked because
    # waiting_for_name still True).
    _system_name = _pipeline_state_store.peek_active_system_name() or ""
    _engagement_passed = bool(
        _system_name
        and text
        and _nfkc_lower(_system_name) in _nfkc_lower(text)
    )

    _open_session(_sid, "visitor", "voice",
                  person_type="stranger",
                  engagement_gate_passed=_engagement_passed)
    await _conversation_store.init_empty(_sid)
    try:
        _loop = asyncio.get_running_loop()
        if _engagement_passed:
            # Mirror ambient-gate path at pipeline.py:6853-6857
            _loop.create_task(_session_store.set_waiting_for_name(_sid, False))
            _loop.create_task(_session_store.set_voice_only_origin(_sid, True))
        else:
            # Original behavior — keep gate active until system name heard
            _loop.create_task(_session_store.set_waiting_for_name(_sid, STRANGER_REQUIRE_SYSTEM_NAME))
    except RuntimeError:
        pass  # OPTIONAL: no running loop in test/early-boot context

    _cur_pid  = _sid
    _cur_name = "visitor"
    if _speaker_track is not None:
        try:
            asyncio.get_running_loop().create_task(
                _track_store.mint_stranger(_speaker_track, _sid)
            )
        except RuntimeError:
            pass  # OPTIONAL: no running loop in test context
    if _engagement_passed:
        print(f"[Pipeline] Stranger engaged (voice-only, system addressed) — {_sid}")
    print(f"[Voice] Unrecognized speaker → new session {_cur_pid} (track={_speaker_track})")
```

### 4.3 Multi-direction trace (D2)

**Forward**: bootstrap credits seeded → voice accumulation fires on turn 1 → voice_n grows → engagement gate clears naturally → stranger promotes via `update_person_name` on later turn
**Backward**: reconciler returns `new_stranger` action; `text` is STT output in scope; `_pipeline_state_store.peek_active_system_name()` returns current system name
**Sideways**: ambient-gate path at `pipeline.py:6846-6857` is the template; D2 makes the voice-routing path symmetric. No conflict.
**Lifecycle**: stranger session BIRTH (D2 — both paths now seed engagement state correctly) → MUTATION (voice accumulation) → CONSUMPTION (voice ID matching) → DEATH (timeout or promotion)

### 4.4 Invariants (D2)

**Preserved:**
- Ambient-gate path at `pipeline.py:6846-6857` unchanged
- `STRANGER_REQUIRE_SYSTEM_NAME` config unchanged
- Sessions opened without system name in user_text still gate-active (`waiting_for_name=True`)

**Established:**
- **Engagement-gate parity invariant**: voice-routing new_stranger path produces SAME session state as ambient-gate path when system name detected in STT
- Both paths now log `[Pipeline] Stranger engaged (voice-only, system addressed)` when gate passes

**Not touched:**
- System-name detection algorithm (NFKC-lowercased substring — matches existing engagement-gate pattern per Plan v1 Precision Item 2)
- Engagement-gate config values
- Other voice-routing actions (current / switch_enrolled / ambiguous / etc.)

### 4.5 Pre-mortem (D2)

| # | Failure mode | Mitigation |
|---|---|---|
| 1 | NFKC-substring false-positive on partial words ("Karasu" contains "Kara") | System names typically short proper nouns; risk acceptable. P0.3's NFKC + casefold also defends against Cyrillic homoglyph |
| 2 | LLM-hallucinated STT containing system name grants credits to non-existent visitor | Engagement at session-OPEN is bounded; future turns refine via voice accumulation; worst case is one false-grant session that expires |
| 3 | Multi-language system names | NFKC normalization handles |
| 4 | `peek_active_system_name` returns None during boot | Guard `_system_name = ... or ""` handles None |
| 5 | `text` is None or empty | Guard `text and ...` short-circuits |
| 6 | Race: another path opens session for same pid concurrently | SessionStore async lock ensures atomicity |
| 7 | Word-boundary tightening needed later (auditor Q1 deferred) | If false-positive surfaces in canary 4, fix BOTH paths (voice-routing + ambient-gate) in a separate sub-spec for symmetry |

### 4.6 11-gate quality checklist (D2)

| # | Gate | Status |
|---|---|---|
| 1 | Correctness | ✓ |
| 2 | Security | ✓ — engagement-gate semantics preserved; no new attack surface |
| 3 | Privacy | N/A |
| 4 | Performance | ✓ — 1 substring check per new_stranger event (rare) |
| 5 | Observability | ✓ — `[Pipeline] Stranger engaged...` log fires on D2-pass; canary diff compares to canary 3 absence |
| 6 | Test pyramid | ✓ 1 AST + 2 behavioral |
| 7 | Regression guards | ✓ Test 1 directly defends against canary 3 Lexi failure |
| 8 | Pre-mortem | ✓ 7 modes |
| 9 | Multi-direction | ✓ |
| 10 | Backward compat | ✓ — gate-fail path unchanged |
| 11 | Doc updates | ✓ |

### 4.7 Test surface (D2) — 3 tests

| # | Test | Type | Asserts |
|---|---|---|---|
| 1 | `test_voice_routing_new_stranger_with_system_name_seeds_engagement` | Behavioral | reconciler new_stranger + text="Hi Kara..." → `engagement_gate_passed=True`, `voice_only_origin=True`, `bootstrap > 0`, `waiting_for_name=False` |
| 2 | `test_voice_routing_new_stranger_without_system_name_keeps_gate_active` | Behavioral | reconciler new_stranger + text without system name → `waiting_for_name=True` (legacy behavior preserved) |
| 3 | `test_voice_routing_engagement_log_fires` | AST forward-property | `[Pipeline] Stranger engaged...` log conditional matches ambient-gate path's structure |

---

## 5. D3 — Voice gallery accumulation gates (MEDIUM)

### 5.1 Contract

Voice gallery accumulation (both via `_decide_and_accumulate_voice` at `pipeline.py:2262-2267` AND via `core/db.py:1554-1588::add_voice_embedding`) MUST gate on:
- **Minimum utterance duration**: audio length >= `MIN_VOICE_ACCUM_DURATION_SECS=1.5` seconds (matches ECAPA-TDNN minimum reliable length per `core/voice.py:147`)
- **Centroid-distance check**: proposed embedding's cosine to current gallery centroid >= `VOICE_SELF_UPDATE_CENTROID_MIN=0.55` (mirrors face gallery's `SELF_UPDATE_CENTROID_MIN=0.55` per Session 51)

### 5.2 Reference implementation (locations)

**Location 1 — pipeline.py voice self-match path** (around line 2262-2267):

```python
# Existing
if v_score >= min_self_match:
    db.add_voice_embedding(pid, emb, source="voice_self_match")
    ...

# After D3 — add duration guard at the call site
from core.config import MIN_VOICE_ACCUM_DURATION_SECS
_audio_duration_secs = len(audio) / MIC_SAMPLE_RATE
if v_score >= min_self_match and _audio_duration_secs >= MIN_VOICE_ACCUM_DURATION_SECS:
    db.add_voice_embedding(pid, emb, source="voice_self_match")
    ...
else:
    if v_score >= min_self_match:
        print(f"[Voice] Skipped accum for {pid}: short utterance {_audio_duration_secs:.2f}s < {MIN_VOICE_ACCUM_DURATION_SECS}s")
```

**Location 2 — core/db.py::add_voice_embedding** (around line 1554-1588):

```python
# After D3 — add centroid-distance gate before INSERT
# Mirrors core/db.py:674-691 face-gallery pattern
def add_voice_embedding(self, person_id: str, embedding: np.ndarray, source: str) -> bool:
    """..."""
    # Existing schema validation, normalization, etc.
    ...

    # P0.S7.5.2 D3 — centroid-distance gate (mirrors face gallery
    # Session 51 P0.5). Compute current centroid; reject embedding
    # whose cosine to centroid < VOICE_SELF_UPDATE_CENTROID_MIN.
    # Prevents short-utterance noise from drifting the gallery over
    # time (canary 3 2026-05-20 Jagan v_score 0.3-0.4 on his own
    # mature profile — symptom of centroid contamination).
    from core.config import VOICE_SELF_UPDATE_CENTROID_MIN
    existing_embeddings = self._fetch_voice_embeddings_for(person_id)
    if len(existing_embeddings) >= VOICE_CENTROID_GATE_MIN_SAMPLES:  # only gate once gallery has enough samples for a stable centroid
        centroid = np.mean(existing_embeddings, axis=0)
        centroid = centroid / np.linalg.norm(centroid)
        cosine_to_centroid = float(np.dot(embedding, centroid))
        if cosine_to_centroid < VOICE_SELF_UPDATE_CENTROID_MIN:
            print(f"[Voice] Skipped accum for {person_id}: centroid-distance {cosine_to_centroid:.3f} < {VOICE_SELF_UPDATE_CENTROID_MIN}")
            return False

    # Existing INSERT logic
    ...
    return True
```

Note: `VOICE_CENTROID_GATE_MIN_SAMPLES` (e.g., 5) prevents the gate from rejecting during bootstrap when centroid isn't yet stable. Mirrors the face-gallery design pattern.

### 5.3 New config constants

```python
# core/config.py additions
MIN_VOICE_ACCUM_DURATION_SECS: float = 1.5  # P0.S7.5.2 D3 — ECAPA-TDNN min reliable length (per core/voice.py:147)
VOICE_SELF_UPDATE_CENTROID_MIN: float = 0.55  # P0.S7.5.2 D3 — mirror face gallery SELF_UPDATE_CENTROID_MIN
VOICE_CENTROID_GATE_MIN_SAMPLES: int = 5  # P0.S7.5.2 D3 — gate fires only when centroid has ≥5 samples (bootstrap-safe)
```

### 5.4 Multi-direction trace (D3)

**Forward**: short utterances filtered → gallery stays clean → centroid stays stable → mature-profile match scores stay reliable → Bug 1 (offscreen-floor on low scores) becomes structurally less likely
**Backward**: producers of voice accumulation — `_decide_and_accumulate_voice` (multiple paths converge here) — all gated at the helper call site
**Sideways**: face gallery has equivalent gate at `core/db.py:674-691` (Session 51 P0.5); voice now mirrors. Cross-spec consistency.
**Lifecycle**: voice sample BIRTH (recording) → embedding (ECAPA) → D3 gate (duration + centroid) → gallery accumulation → centroid update → CONSUMPTION (voice ID matching) → DEATH (gallery prune)

### 5.5 Invariants (D3)

**Preserved:** long-utterance accumulation path unchanged; existing gallery contents unchanged (D3 fixes future writes, NOT existing contamination)

**Established:**
- Minimum-utterance-duration invariant for voice gallery writes
- Centroid-distance invariant matching face-gallery design
- Bootstrap-safe gate (only fires when ≥5 samples present)

**Not touched:** ECAPA model, gallery storage format, voice ID matching algorithm, voice diarization

### 5.6 Pre-mortem (D3)

| # | Failure mode | Mitigation |
|---|---|---|
| 1 | Existing contaminated galleries stay broken | Documented as Known Limitation §13.1; factory reset between canaries handles tests |
| 2 | 1.5s threshold too aggressive — slows enrollment | First-N samples below threshold get rejected; user must speak longer. Acceptable enrollment slowdown. |
| 3 | Bootstrap-safe gate misfires (rejects during enrollment) | `VOICE_CENTROID_GATE_MIN_SAMPLES=5` ensures gate only fires after ≥5 samples present. Mirrors face-gallery's bootstrap behavior. |
| 4 | Centroid-distance computation cost | <5ms per add; negligible vs current ECAPA embedding cost (~50ms) |
| 5 | Centroid recomputed on every add (vs cached) | Acceptable; recompute is O(N) where N≤20. Future micro-optimization possible. |
| 6 | Test fixtures inject samples with no audio source | Behavioral tests use seeded embeddings; bypass the duration gate by calling `add_voice_embedding` directly. AST tests cover the duration gate at the caller. |
| 7 | Network race: voice ID matches but accumulation blocked by gate | Voice ID success path unchanged; gate ONLY blocks GALLERY ADD, not match-decision |

### 5.7 11-gate quality checklist (D3)

| # | Gate | Status |
|---|---|---|
| 1 | Correctness | ✓ |
| 2 | Security | N/A |
| 3 | Privacy | N/A — same privacy tier as existing voice samples |
| 4 | Performance | ✓ — <5ms per add (centroid compute) + duration check is O(1) |
| 5 | Observability | ✓ — skip logs surface drift events |
| 6 | Test pyramid | ✓ 2 AST + 3 behavioral (per §5.8) |
| 7 | Regression guards | ✓ Test 4 defends against canary 3 short-utterance contamination |
| 8 | Pre-mortem | ✓ 7 modes |
| 9 | Multi-direction | ✓ |
| 10 | Backward compat | ⚠️ existing contaminated galleries stay broken — documented Known Limitation |
| 11 | Doc updates | ✓ |

### 5.8 Test surface (D3) — 4 tests

| # | Test | Type | Asserts |
|---|---|---|---|
| 1 | `test_voice_accum_rejects_short_utterance` | Behavioral | audio < 1.5s → accumulation skipped, log emitted |
| 2 | `test_voice_accum_rejects_centroid_outlier_after_bootstrap` | Behavioral | seed gallery with 5 clean samples; submit outlier embedding cosine 0.4 → rejected |
| 3 | `test_voice_accum_accepts_centroid_outlier_during_bootstrap` | Behavioral | seed gallery with 3 samples; submit outlier cosine 0.4 → accepted (bootstrap-safe gate inactive) |
| 4 | `test_voice_accum_constants_present` | AST/config invariant | `MIN_VOICE_ACCUM_DURATION_SECS`, `VOICE_SELF_UPDATE_CENTROID_MIN`, `VOICE_CENTROID_GATE_MIN_SAMPLES` all in config.py |

---

## 6. D4 — STT 1-word artifact filter + Smart-Turn debounce (MEDIUM)

### 6.1 Contract

`core/audio.py` STT output MUST filter 1-word transcripts unless EITHER (a) terminated with `.`, `!`, or `?`, OR (b) the word matches a known-imperative allowlist `STT_KNOWN_IMPERATIVES = frozenset({"yes", "no", "stop", "help", "okay", "ok", "sure", "yeah", "yep", "nope"})`. Smart-Turn MUST debounce within the same silence streak (don't re-fire on consecutive checks).

### 6.2 Reference implementation

**STT filter** (core/audio.py post-segment-filter, around line 563):

```python
# Existing
words = text.strip().split()
# ... existing repetition filter ...

# P0.S7.5.2 D4 — filter 1-word artifacts (Whisper noise hallucinations like "You", "Yeah", "Thank")
from core.config import MIN_STT_WORD_COUNT, STT_KNOWN_IMPERATIVES
_t_stripped = text.strip()
if len(words) < MIN_STT_WORD_COUNT:
    _terminated = _t_stripped.endswith(('.', '!', '?'))
    _word_lower = _t_stripped.lower().rstrip('.!?,;:')
    _allowed = _word_lower in STT_KNOWN_IMPERATIVES
    if not (_terminated or _allowed):
        print(f"[Audio] STT: 1-word artifact filtered: {_t_stripped!r}")
        return "", "en"
```

**Smart-Turn debounce** (core/audio.py around line 437-447):

```python
# Existing logic with `smart_turn_fired` flag
# After D4 — ensure smart_turn_fired blocks re-invocation until silence resets
if silent_streak >= smart_turn_count and not smart_turn_fired:
    # ... existing smart-turn invocation ...
    smart_turn_fired = True
# Existing: smart_turn_fired = False reset on resumed speech
```

### 6.3 New config constants

```python
# core/config.py additions
MIN_STT_WORD_COUNT: int = 2  # P0.S7.5.2 D4 — minimum words to keep STT output unless terminated/allowlisted
STT_KNOWN_IMPERATIVES: frozenset[str] = frozenset({
    "yes", "no", "stop", "help", "okay", "ok", "sure", "yeah", "yep", "nope",
})
```

### 6.4 Multi-direction trace (D4)

**Forward**: STT output cleaner → downstream brain prompts have less noise → routing reconciler processes fewer phantom turns
**Backward**: Whisper STT (faster-whisper) returns transcripts; D4 gates at the output edge
**Sideways**: VAD floor at `core/audio.py:365` (`min_speech=0.10s`) is the upstream gate; D4 is the downstream gate. Defense-in-depth.
**Lifecycle**: audio chunks → VAD (≥100ms) → STT (Whisper) → D4 filter (1-word + allowlist) → conversation_turn

### 6.5 Invariants (D4)

**Preserved:** legitimate multi-word turns unchanged; long terminated 1-word imperatives ("Stop.") accepted

**Established:**
- 1-word artifact rejection invariant (Whisper hallucinations like "You", "Yeah", "Thank" filtered)
- Allowlist for known confirmation/denial turns
- Smart-Turn no-double-fire invariant

**Not touched:** VAD floor, STT model, audio recording loop

### 6.6 Pre-mortem (D4)

| # | Failure mode | Mitigation |
|---|---|---|
| 1 | Allowlist incomplete — legitimate 1-word response rejected | Allowlist covers top-10 confirmation/denial words; uncommon responses ("indeed", "absolutely") get filtered. Acceptable; user can rephrase. |
| 2 | Smart-Turn debounce breaks adaptive grace logic | Verify with behavioral test: grace=0.19/0.48 still fires correctly on first invocation |
| 3 | Whisper occasionally returns terminated 1-word ("Sure.") that's NOT in allowlist | Terminated takes precedence; "Sure." passes via punctuation branch |
| 4 | Allowlist needs case-insensitive match for Unicode | `.lower()` + strip handle ASCII; Unicode covered by Python's default lower() |
| 5 | User says "Y" or "N" alone (typing-style abbreviation in voice) | Not in allowlist; would be filtered. Edge case; acceptable. |

### 6.7 11-gate quality checklist (D4)

| # | Gate | Status |
|---|---|---|
| 1 | Correctness | ✓ |
| 2 | Security | N/A |
| 3 | Privacy | N/A |
| 4 | Performance | ✓ — O(1) string checks |
| 5 | Observability | ✓ — skip log surfaces filter events |
| 6 | Test pyramid | ✓ 2 unit |
| 7 | Regression guards | ✓ Test 1 covers canary 3 "You" artifact |
| 8 | Pre-mortem | ✓ 5 modes |
| 9 | Multi-direction | ✓ |
| 10 | Backward compat | ✓ additive filter; existing pipeline downstream unaffected |
| 11 | Doc updates | ✓ |

### 6.8 Test surface (D4) — 2 tests

| # | Test | Type | Asserts |
|---|---|---|---|
| 1 | `test_stt_filters_1_word_noise_keeps_allowlist` | Unit | "You" → empty; "Yeah" → passes (allowlist); "Stop." → passes (punctuation); "Indeed" → filtered |
| 2 | `test_smart_turn_debounces_within_silence_streak` | Behavioral | Smart-Turn fires once per silence streak (not multiple times) |

---

## 7. D5 — STRANGER IDENTITY block min_turns=0 + question-shape anti-pattern (MEDIUM)

### 7.1 Contract

`STRANGER_IDENTITY_BLOCK_MIN_TURNS` drops from 2 to 0. Block fires on every stranger turn (turns 0, 1, 2+). Block content extended with explicit anti-pattern: "questions about system knowledge are NOT identity denials; do NOT call `report_identity_mismatch` for them."

### 7.2 Config change

```python
# core/config.py
# Existing:
STRANGER_IDENTITY_BLOCK_MIN_TURNS: int = 2

# P0.S7.5.2 D5:
STRANGER_IDENTITY_BLOCK_MIN_TURNS: int = 0
```

### 7.3 Block content extension

Insert BEFORE the closing `<<<END STRANGER IDENTITY>>>` at `core/brain.py:2514`:

```python
"\n\n"
"QUESTION-SHAPE ANTI-PATTERN (Canary 3, 2026-05-20):\n"
"If the stranger asks a question about whether YOU know them — "
"e.g. \"do you know me?\", \"do you remember me?\", \"I know you "
"very well but I'm not sure if you know me\", \"have we met before?\" "
"— this is NOT an identity denial. Do NOT call "
"`report_identity_mismatch`. That tool is ONLY for the current "
"speaker denying their OWN identity (e.g. \"I'm not Jagan\").\n\n"
"For these questions, respond conversationally: ask the stranger "
"for their name (\"I don't think we've met — what's your name?\"). "
"If they then state their name, THAT is the trigger to call "
"`update_person_name` per the rules above."
```

### 7.4 Multi-direction trace (D5)

**Forward**: stranger turn 0/1 → block renders → brain reads explicit anti-pattern → mis-tooling on question-shapes prevented
**Backward**: `session_user_turns` from conversation_turn → MIN_TURNS=0 gate always passes for strangers
**Sideways**: KNOWN SPEAKER IDENTITY block (P0.S7.5 D4) excludes strangers; mutual exclusion preserved
**Lifecycle**: block renders every stranger turn until promotion → after `update_person_name`, person_type flips known → block stops rendering automatically

### 7.5 Invariants (D5)

**Preserved:**
- KNOWN SPEAKER IDENTITY block (P0.S7.5 D4) mutual exclusion with STRANGER IDENTITY (different person_type gates)
- VISITOR CONTEXT block (visitor_alert nudge marker) independent — fires regardless of STRANGER IDENTITY
- Block content for self-intros (concrete triggers, anti-conversational-ack)

**Established:**
- **Turn-0 stranger guidance invariant**: brain has block-level guidance on every stranger turn from the first
- **Question-shape anti-pattern invariant**: stranger questions about system knowledge route to conversational response, not `report_identity_mismatch`

**Not touched:** report_identity_mismatch tool description; VISITOR CONTEXT block; classifier intent labels

### 7.6 Pre-mortem (D5)

| # | Failure mode | Mitigation |
|---|---|---|
| 1 | Block fires on every stranger turn — token cost | Block is ~25 lines; <300 tokens. Negligible vs context cost. |
| 2 | Anti-pattern doesn't generalize to novel question shapes | Concrete examples cover canary 3 case; LLM generalizes from pattern. If canary 4 surfaces new question-shape, extend block. |
| 3 | Stranger says "do you know my name?" — ambiguous | Block teaches "ask for name conversationally" — same response works |
| 4 | Mutual exclusion with KNOWN SPEAKER IDENTITY breaks | Gates are mutually exclusive by person_type; verify in test |
| 5 | Block too verbose — overshadows other prompt context | Plan v1 verified block is ~25 lines; comparable to existing SYSTEM IDENTITY block (~22 lines). |

### 7.7 11-gate quality checklist (D5)

| # | Gate | Status |
|---|---|---|
| 1 | Correctness | ✓ |
| 2 | Security | ✓ — anti-pattern prevents tool-misuse on legitimate visitor questions |
| 3 | Privacy | N/A |
| 4 | Performance | ✓ — small prompt-block addition (~300 tokens) |
| 5 | Observability | ✓ — canary 4 will show whether report_identity_mismatch mis-fires recur |
| 6 | Test pyramid | ✓ 2 tests |
| 7 | Regression guards | ✓ Test 1 defends against canary 3 Lexi question-shape |
| 8 | Pre-mortem | ✓ 5 modes |
| 9 | Multi-direction | ✓ |
| 10 | Backward compat | ✓ — block now fires earlier; existing block-content invariants preserved |
| 11 | Doc updates | ✓ |

### 7.8 Test surface (D5) — 2 tests

| # | Test | Type | Asserts |
|---|---|---|---|
| 1 | `test_stranger_identity_block_fires_on_turn_zero` | Behavioral | session_user_turns=0 + person_type=stranger → block in rendered prompt |
| 2 | `test_stranger_identity_block_contains_question_anti_pattern` | Source-inspection (AST or substring with adjacent-string-literal normalizer per `feedback_adjacent_string_literal_normalizer.md`) | Block contains "QUESTION-SHAPE ANTI-PATTERN" + "do not call report_identity_mismatch" + Lexi-canary phrasing |

---

## 8. Cross-spec impact analysis (refined from Phase 0 §8)

### 8.1 D1

| Affected spec | Disposition |
|---|---|
| P0.10 Phase 2 (reconciler is sole routing source) | D1 fixes latent bug in P0.10's expected schema |
| P0.6.2 (PresenceStore introduction) | D1 syncs producer with PresenceStore schema |
| `tests/test_p06_store_schemas.py` invariant | D1.b satisfies this invariant (schema unchanged) |
| `tests/test_reconciler.py:237-251` | D1.b makes pipeline match these fixtures' expected dict shape |

### 8.2 D2

| Affected spec | Disposition |
|---|---|
| Session 22 G4 (stranger system-name gate) | D2 extends gate-passing to voice-routing path; ambient-gate preserved |
| P0.10 Phase 2 (new_stranger action) | D2 closes the engagement-gate gap P0.10 didn't address |
| Session 49 NEW-3 (voice_face_confirmed) | D2 mirrors voice_only_origin (Session 120) |

### 8.3 D3

| Affected spec | Disposition |
|---|---|
| Session 51 Finding #1 (face anti-poisoning) | D3 mirrors face-gallery design to voice-gallery |
| Session 18 voice gallery cache | Cache untouched; gate at write time only |

### 8.4 D4

| Affected spec | Disposition |
|---|---|
| Session 67 Bug F (short-utterance floor) | D4 complements routing-side floor with audio-side filter |
| Session 38 STT pyannote integration | D4 doesn't touch pyannote |

### 8.5 D5

| Affected spec | Disposition |
|---|---|
| Session 97 Fix 1 (stranger promotion) | D5 strengthens prompt-block guidance |
| P0.S7.5 D4 (KNOWN SPEAKER IDENTITY block) | Mutual exclusion preserved (different person_type gates) |
| Session 100/104 Bug F/G/J (VISITOR CONTEXT) | Independent block — D5 unrelated |

**No cross-spec conflicts.** All 5 D-decisions additive or symmetric.

---

## 9. Phase decomposition + discipline counts

### 9.1 Phase decomposition

**Phase 1** (~4-5 hours) — D1 + D2 + D5 + tests:
- D1.b: add `last_recognized_at` to `_rs_pif_view` producer at `pipeline.py:7234`
- D2: NFKC-substring engagement detection at `pipeline.py:7496-7515`
- D5: `STRANGER_IDENTITY_BLOCK_MIN_TURNS=0` + question-shape anti-pattern bullet
- Tests for D1+D2+D5: 3+3+2 = 8 tests

**Phase 2** (~3-4 hours) — D3 + D4 + tests:
- D3: voice gallery duration + centroid gates (`pipeline.py:2262-2267` + `core/db.py:1554-1588` + 3 new config constants)
- D4: STT 1-word filter + Smart-Turn debounce
- Tests for D3+D4: 4+2 = 6 tests

**Phase 3** (~1 hour) — Behavioral integration + closure narrative:
- E2E test (optional): multi-turn stranger session with system name + voice accumulation through D2+D3
- Closure narrative with mandatory "Known Limitations" subsection (D3 existing contamination)

**Phase 4** (~0.5 hours) — Deliberate-regression confirmations + memory updates:
- 5 confirmations (one per D-decision; mirror P0.S7.5 a/b/c/d/e shape)
- Memory updates:
  - `feedback_strict_industry_standard_mode.md` — 4th application banked
  - `feedback_auditor_q5_estimates_trail_grep.md` — 6th instance
  - **NEW CLAUDE.md doctrine `### Canary-surfaces-real-gaps`** banked at closure (5th instance threshold-crossing per auditor pre-approval)

**Total: ~8-10 hours = ~1.5 days.** Matches Phase 0 §7 forecast.

### 9.2 Test surface forecast

| Phase | Tests |
|---|---|
| Phase 1 | 8 (D1: 3, D2: 3, D5: 2) |
| Phase 2 | 6 (D3: 4, D4: 2) |
| Phase 3 | 0-1 (optional E2E) |
| Phase 4 | 0 new (5 deliberate-regression confirmations against existing tests) |
| **Total** | **14-15 tests** |

**Plan v1 forecast: +14 (no E2E) or +15 (with E2E).** Auditor pre-spec estimate: 12-16 tests. Plan v1 lands within range. Auditor-Q5 6th instance prediction: ON-TARGET.

### 9.3 Discipline counts on closure

| Discipline | Pre-P0.S7.5.2 | Post-closure |
|---|---|---|
| Spec-first review cycle | 16-for-16 | **17-for-17** |
| Sub-pattern A (`### Phase-0-catches-wrong-premise`) | 5 | stays at **5** |
| Tripwires-must-match-deferral-surface | 4-for-4 | stays |
| Developer-improves-on-spec | 6-for-6 | stays |
| Induction-surfaces-invariant-gaps | 7-for-7 | stays |
| Canary-finding tracker | 4 instances | **5th + ELEVATION** — `### Canary-surfaces-real-gaps` numbered doctrine added to CLAUDE.md Architectural Disciplines at closure (auditor pre-approved threshold-crossing) |
| Auditor-Q5-estimates-trail-grep (architect-memory) | 5 instances | **6th instance** — Phase 0 granularity sub-observation test at 5-D-decision scale |
| Strict-industry-standard mode (auto-memory) | 2 Plans + 1 closure (P0.S7.5.1) + 1 Phase 0 (P0.S7.5.2 audit) | **4th application** at Plan v1 — discipline holding across 4 consecutive artifacts |
| Partial-falsification-tentative | 2 instances | stays at 2 |
| Spec-time grep-verification | 5 instances | stays at 5 unless drift surfaces |

---

## 10. Strict-industry-standard mode discipline self-audit (Plan v1)

| Operational test | Status |
|---|---|
| Pre-mortem section exists per D-decision | ✓ (§3.6, §4.6, §5.6, §6.6, §7.6 — 5+ failure modes each) |
| Multi-direction invariant trace exists per D-decision | ✓ (§3.4, §4.4, §5.4, §6.4, §7.4 — all 4 axes) |
| Quality-gate checklist named per D-decision | ✓ (§3.7, §4.7, §5.7, §6.7, §7.7 — 11 gates each, with N/A rationales) |
| Cross-spec impact analysis exists | ✓ (§8 — per D-decision) |
| Closure-audit step scheduled | ✓ (§9.1 Phase 4 + production-canary diff tracking) |
| Honest engineering on auditor framing | ✓ (§1.2 — D1.a vs D1.b chosen with grep evidence + auditor lean adopted) |
| Auditor precision items addressed | ✓ (§1.2 — all 4 precision items handled) |

**Discipline status: APPLIED.** 4th consecutive artifact under strict mode (1st Phase 0 at audit; this is 1st full strict-mode Plan v1).

---

## 11. Plan v1 → Plan v2 anticipated precision items

Per auditor's expected ~2-3 precision items at this scope:

1. **D2 production-text grep verification at Plan v2** — verify `text` variable is in scope at `pipeline.py:7499` (Plan v1 references it but Plan v2 should explicitly grep-confirm)
2. **D3 centroid-distance: cache vs recompute** — auditor may prefer cached centroid (computed once on gallery change) over recompute-per-add. Performance optimization; non-blocking.
3. **D4 allowlist completeness** — auditor may want explicit test cases for each allowlist word + a documented "expanding the allowlist" follow-up procedure.
4. **D5 block-content review** — auditor reviews the exact wording of the new question-shape anti-pattern bullet before lock.

None blockers; Plan v2 anticipated to be ~1 page refinement.

---

## 12. Next steps

1. **Auditor reviews Plan v1.** Adjudicates §11 precision items.
2. **Plan v2** drafted with precision items locked (likely 2-3 small refinements).
3. **Joint sign-off** → developer handoff.
4. **Phase 1-3 implementation** under strict mode.
5. **Phase 4 closure** + memory bankings + **CLAUDE.md `### Canary-surfaces-real-gaps` doctrine elevation** (5th instance threshold-crossing).
6. **RE-CANARY 4** IMMEDIATELY on closure. Same multi-person scenario. Expected:
   - D1 fix: Jagan's offscreen-but-visible turns route correctly
   - D2 fix: Lexi engages on turn 1 with "Hi Kara..."
   - D3: short-utterance gallery contamination prevented
   - D4: STT 1-word artifacts filtered
   - D5: brain handles Lexi's question-shape turn 1 without mis-tooling
7. **On RE-CANARY 4 PASS**: combined Stage 2 PR fires (D-C Stage 2 + D-D Stage 2 hard-deletes + 130 test-site migrations) — **P0.S7 family arc closes definitively.**

---

## 13. Known limitations (closure narrative template)

### 13.1 D3 existing voice gallery contamination

Voice galleries contaminated by short-utterance accumulation BEFORE D3 deployment stay contaminated. D3 fixes future writes; doesn't remediate. Mitigations:
- **Factory reset between canaries** — handles test scenarios; canary 4 starts with clean state
- **Production gradual re-convergence** — long-utterance samples dominate over time as D3 prevents new short-utterance pollution; centroid gradually re-converges
- **One-shot gallery-rebuild migration** — not in P0.S7.5.2 scope; bank as candidate future spec if production canaries surface persistent contamination

### 13.2 D2 word-boundary regex tightening (deferred)

D2 uses NFKC-lowercased substring match. False-positives on partial-word matches ("Karasu" containing "Kara") are theoretically possible but bounded by typical short proper-noun system names. If canary 4 surfaces false-positive, fix BOTH paths (voice-routing AND ambient-gate per `pipeline.py:6800` area) in a separate sub-spec for symmetry.

### 13.3 D4 allowlist completeness

`STT_KNOWN_IMPERATIVES` covers top-10 confirmation/denial words. Uncommon 1-word responses ("indeed", "absolutely", "definitely") get filtered. Acceptable trade-off; user rephrases or extends allowlist if pattern recurs.

---

## 14. Reference documents

- `tests/p0_s7_5_2_audit.md` — Phase 0 (APPROVED with 4 precision items)
- `tests/p0_s7_5_1_*.md` — P0.S7.5.1 reference (preceding spec; lambda-replacement marker fix shipped)
- Canary 3 evidence: `terminal_output_2026-05-20_101936.md` + `terminal_output.md`
- `core/reconciler.py:117-131` — D1 verified consumer (correct as-is)
- `pipeline.py:7233-7236` — D1 PRIMARY EDIT SITE (producer; missing `last_recognized_at`)
- `pipeline.py:7496-7515` — D2 PRIMARY EDIT SITE
- `pipeline.py:6846-6857` — D2 TEMPLATE (ambient-gate path)
- `core/presence_store.py:15-86` — PresenceSnapshot schema (BOTH last_seen + last_recognized_at fields)
- `core/voice.py:147-152` — ECAPA minimum reliable length
- `core/db.py:1554-1588` — D3 EDIT SITE 2
- `core/db.py:674-691` — D3 TEMPLATE (face gallery centroid gate)
- `core/audio.py:516-563` — D4 EDIT SITE 1 (STT filter)
- `core/audio.py:437-447` — D4 EDIT SITE 2 (Smart-Turn debounce)
- `core/brain.py:2495-2514` — D5 EDIT SITE 2 (STRANGER IDENTITY block)
- `core/config.py` — D1/D3/D4/D5 config additions
- Memory: `feedback_strict_industry_standard_mode.md` — 4th application
- Memory: `feedback_auditor_q5_estimates_trail_grep.md` — 6th instance at closure
- Memory: `feedback_spec_time_grep_verification.md` — Pass 1 applied (D1 + D2 verified)
- Memory: `feedback_adjacent_string_literal_normalizer.md` — applied to D5 test 2

---

**Standing by for auditor review of Plan v1. Anticipated precision items per §11.**

5 D-decisions, 14-15 tests forecast, ~1.5 days effort. 4 Plan v1 precision items addressed; 2-3 small refinements likely at Plan v2. Strict-mode discipline self-audit: APPLIED across all sections.

**Canary-surfaces-real-gaps doctrine elevation pre-approved by auditor for closure** (5th instance threshold-crossing event).
