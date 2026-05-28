> **CHAPTER 06 — Sessions + Evidence** | Sourced from `everything_about_system.md` §47-58 (verbatim mechanical extraction per Plan v2 §1.6 section-number stability invariant).

---

## 47. SessionStore and the `Session` Dataclass

> **Architectural note (2026-05-15).** Before P0.7 (the typed-session-state migration; see **Part XL**), active sessions lived in a free-form `_active_sessions: dict[str, dict]` at module scope in `pipeline.py`. ~190 sites across `pipeline.py` and `test_pipeline.py` wrote to this dict directly. Field typos silently created garbage keys; concurrent access went unsynchronised; invariants ("dispute_set_at must be present whenever person_type == 'disputed'") had to be defended at every site. P0.7 replaced the free-form dict with a typed `SessionStore` owning typed `Session` dataclasses. This section describes the production session state surface as it exists today.

### 47.1 The three dataclasses (from `core/session_state.py`)

```python
@dataclass(slots=True)
class VoiceEvidence:
    voice_match_conf:      float = 0.0          # last voice ID cosine (CAN be negative)
    voice_last_heard_ts:   float = 0.0          # unix ts of last voice ID match
    voice_sample_count:    int = 0              # DB-hydrated at open_session
    bootstrap_credits:     int = 0              # remaining credits from engagement gate
    recent_voice_confs:    list[float] = field(default_factory=list)   # maxlen-3 deque
    # face evidence
    face_match_conf:       float = 0.0
    face_last_seen_ts:     float = 0.0
    anti_spoof_live:       bool = False
    anti_spoof_score:      float = 0.0

@dataclass(slots=True)
class Session:
    person_id:             str
    person_name:           str
    person_type:           str             # stranger | known | best_friend | disputed
    started_at:            float
    last_face_seen:        float = 0.0
    last_spoke_at:         float = 0.0
    # dispute state
    dispute_set_at:        Optional[float] = None
    disputed_claimed_name: Optional[str] = None
    prior_person_type:     Optional[str] = None
    disputed_block_count:  int = 0
    disputed_block_alerted: bool = False
    # progressive enrollment
    voice_only_origin:     bool = False    # set at engagement gate if face NOT witnessed
    voice_face_confirmed:  bool = False    # set at progressive-enrollment gate pass
    waiting_for_name:      bool = False    # stranger awaiting "my name is X"
    # context + cache
    cached_prefix:         Optional[str] = None
    core_memory:           Optional[dict] = None
    # room
    room_session_id:       Optional[str] = None
    # turn counter (stranger gate progress)
    user_turns:            int = 0
    # voice + face evidence
    evidence:              VoiceEvidence = field(default_factory=VoiceEvidence)

@dataclass(frozen=True, slots=True)
class SessionSnapshot:
    """Immutable frozen snapshot returned by SessionStore.peek_snapshot().
    Same fields as Session, but collections are NEW copies — mutating
    them has no effect on the underlying Session."""
    # ... same 29 fields as Session
```

`slots=True` on every dataclass is load-bearing: it makes every typo into an `AttributeError` at runtime AND shrinks the per-session memory footprint substantially. `frozen=True` on `SessionSnapshot` is the read-only contract — anywhere in the codebase that needs session state in a logging context, prompt-assembly context, or background coroutine context calls `_session_store.peek_snapshot(pid)` and gets back a snapshot that's safe to pass across `await` boundaries.

### 47.2 Key invariants

- **Pid is the key.** Not name — multiple people can share a name.
- **Pid prefix identifies origin.** `stranger_<uuid>` means this person was created via stranger enrollment; anything else is explicitly created.
- **`person_type` is authoritative.** `stranger`, `known`, `best_friend`, `disputed`. The DB stores `person_type`; the Session mirrors it so hot-path routing doesn't hit the DB every turn.
- **Single-owner.** `SessionStore` is the only writer of `self._sessions: dict[str, Session]`. Every mutation acquires `self._lock` (an `asyncio.Lock`) before touching the dict.
- **Async mutators, sync peek reads.** Every mutation is an `async def` named transition method. Every read is a `def peek_*` returning either a `SessionSnapshot` or a primitive — peeks do NOT acquire the lock, per the single-thread-asyncio safety contract (Part XL §268).

### 47.3 Why a typed Store, not a free-form dict

The shift from `dict[str, dict]` to `SessionStore` carrying `dict[str, Session]` was justified by four concrete failure modes pre-migration:

1. **Field-typo drift.** `_active_sessions[pid]["displute_set_at"] = ...` silently created a new key. `slots=True` makes this an `AttributeError`.
2. **No invariant guards.** A session could be in `person_type == "disputed"` without `dispute_set_at` being set. The named transition `transition_to_disputed(...)` captures `prior_person_type` AND sets `dispute_set_at` AND flips `person_type` atomically.
3. **Concurrent access.** Test and background-coroutine writes interleaved without coordination. The `asyncio.Lock` serialises them.
4. **~190 ad-hoc write sites.** Any future invariant (e.g. "engagement gate must always set bootstrap_credits") had to be defended at every site individually. The 21 named transition methods (§264) replace those sites with semantically-meaningful operations.

## 48. `person_type` Taxonomy

### 48.1 The four types

- **`stranger`** — someone we don't know yet. Pid starts with `stranger_`. Cannot shut down the system or rename it. Can search the web. Cannot search memory (no personal memory yet).
- **`known`** — we know their name and have a face gallery. Can search memory. Cannot rename the system or shut down.
- **`best_friend`** — the household owner. One at a time. Can do everything.
- **`disputed`** — temporary state. A session entered dispute when the speaker's claim contradicted sensor evidence (Session 51). Brain treats them as unknown; agent extraction pauses; renames blocked.

### 48.2 `VALID_PERSON_TYPES` frozenset

```python
VALID_PERSON_TYPES = frozenset({"stranger", "known", "best_friend", "disputed"})
```

Asserted at every write site. The `SessionStore.open_session` method type-checks against this frozenset, and the dispute transition methods (`transition_to_disputed`, `clear_dispute`) carry their own VALID_PERSON_TYPES assertions on the restored type.

### 48.3 Promotion paths

- stranger → known: `update_person_name` tool fires during a stranger session, name is valid.
- stranger → best_friend: never. Best_friend is only set during first_boot_flow.
- known → disputed: sensor and claim disagree; `update_person_name` on a known session flips to disputed via `transition_to_disputed`.
- best_friend → disputed: same (Session 55 Finding L). The `prior_person_type` field captures `best_friend` so `clear_dispute` can restore it.
- disputed → resolved: either `update_person_name` clears it (rename path), `clear_dispute(pid)` runs (auto-clear), or `DISPUTE_MAX_DURATION` force-closes the session.

## 49. `_open_session` Anatomy

The pipeline's wrapper around `SessionStore.open_session`:

```python
async def _open_session(
    person_id: str,
    person_name: str,
    session_type: str,
    *,
    person_type: str,
    engagement_gate_passed: bool = False,
    voice_confidence: float = 0.0,
) -> None:
    assert person_type in VALID_PERSON_TYPES, f"invalid person_type {person_type!r}"

    now = time.time()
    existing = _session_store.peek_snapshot(person_id)
    if existing is not None:
        # Idempotent re-open: refresh timestamps, do NOT clobber person_type.
        await _session_store.update_on_reopen(
            person_id, voice_confidence=voice_confidence, now=now
        )
        return

    print(f"[Session] Open: {person_id} ({session_type}) — {person_name}")

    # DB-preferred voice_sample_count hydration (Obs 1).
    db_voice_count = _voice_gallery_store.peek_size(person_id)
    if _face_db_ref is not None:
        try:
            live_count = _face_db_ref.count_voice_embeddings(person_id)
            if db_voice_count != live_count:
                await _voice_gallery_store.set_size(person_id, live_count)
            db_voice_count = live_count
        except Exception:
            pass

    bootstrap_credits = N_INITIAL_VOICE_BOOTSTRAP if engagement_gate_passed else 0

    await _session_store.open_session(
        person_id=person_id,
        person_name=person_name,
        person_type=person_type,
        session_type=session_type,
        started_at=now,
        last_face_seen=now,
        last_spoke_at=now,
        voice_sample_count=db_voice_count,
        bootstrap_credits=bootstrap_credits,
        voice_match_conf=voice_confidence,
    )
```

### 49.1 The `engagement_gate_passed` flag

Only callers who can prove they gated on engagement pass True. Strangers who said the system name → True. Known/best_friend greetings → True (the greeting itself is gated by anti-spoof + face recognition). Random voice-ID-matched someone without explicit consent gating → False.

Bootstrap credits are seeded only when True. This is the key design choice: we only trust a voice enough to accumulate against when we explicitly gated them in.

### 49.2 Idempotent re-open

If the pid already has an active session, `_open_session` delegates to `update_on_reopen` (atomic refresh of timestamps + voice_match_conf) instead of constructing a new Session. The named transition keeps three properties intact in one operation: `person_type` is NOT clobbered (so a stranger→known promotion done via `update_person_name` since the last open isn't reverted), `dispute_set_at` is preserved if the session is currently disputed, `voice_only_origin` and `voice_face_confirmed` flags are preserved.

## 50. `_close_session` Cleanup

```python
async def _close_session(person_id: str) -> None:
    snap = _session_store.peek_snapshot(person_id)
    if snap is None:
        return
    print(f"[Session] Close: {person_id} — {snap.person_name}")

    await _session_store.close_session(person_id)
    _sessions_started_store.discard(person_id)
    _pending_stranger_voice_store.pop(person_id)        # Bug-2 (Session 33)
    _query_embedding_cache.pop(person_id)               # Finding B (Session 45)
    _identity_hints_store.pop(person_id)                # Finding B (Session 45)
    await _track_store.unbind_stranger_pid(person_id)   # remove track bindings
    await _presence_store.pop_pid(person_id)            # remove from visible roster
    _per_person_agent_store.pop(person_id)              # P0.6.4 — emotion + ambient agents

    # Notify brain orchestrator for session-end synthesis
    if _brain_orchestrator is not None:
        _brain_orchestrator.notify_session_end(person_id, snap.person_name)

    # Room lifecycle: if last session closed, fire _on_room_end fire-and-forget
    if not _session_store.has_any_active_session():
        room_id, room_started_at, participants = _pipeline_state_store.consume_room_session()
        if room_id is not None:
            asyncio.create_task(_on_room_end(room_id, list(participants), room_started_at))
```

### 50.1 Cleanup discipline

Every Store that keys on pid must be cleaned up here. The Store-pattern migration (P0.6, Part XXXIX) made this enforceable: each store exposes a `pop(pid)` or equivalent method, and the M2 autouse coverage meta-test (Part XXXIX §257) catches any store that's not in the cleanup list. Tests fail if a new store is added without a cleanup hook.

### 50.2 BrainOrchestrator.notify_session_end

Triggers a bundle of async tasks:
- `PromptPrefAgent` full analysis on the session's turns.
- `InsightAgent` episode extraction.
- `HouseholdExtractionAgent` relationship inference.
- `NudgeAgent` visitor-alert if this was a non-owner session with turn_count > 0.
- `SocialGraphAgent` aggregation.
- `BrainOrchestrator.synthesize_room` (if this was the last session of a multi-person room, see Part XXVI §171).

All gated on dispute: if the session ended in dispute state, the synthesis helpers are skipped (Session 53 Finding A, see §105).

## 51. Session Expiry Paths

### 51.1 `_expire_stale_sessions()`

Runs both in the outer WATCHING loop and inside the conversation loop. Iterates `_session_store.peek_all_snapshots()` (Part XL §268) and finds sessions where:
- `session_type == "voice"` and `(now - last_spoke_at) > VOICE_SESSION_TIMEOUT`
- OR `session_type == "face"` and `(now - last_face_seen) > FACE_LOSS_GRACE`
- OR `person_type == "disputed"` and `(now - dispute_set_at) > DISPUTE_MAX_DURATION`

For each, calls `_close_session(pid)`.

Auto-clear (P0.7.3): for disputed sessions where the dispute conditions have resolved (3 consecutive voice matches at ≥ `DISPUTE_AUTO_CLEAR_VOICE_MIN`, OR the holder's face is in frame with `face_match_conf ≥ DISPUTE_AUTO_CLEAR_VOICE_MIN`), call `transition_clear_dispute(pid, now)` to restore the session via `prior_person_type`.

### 51.2 FACE_LOSS_GRACE (10s)

A face-started session doesn't immediately end when the face leaves frame. We give the user 10 seconds of grace — they might look down, walk behind a pillar, or briefly turn away. Past that, we close.

### 51.3 VOICE_SESSION_TIMEOUT (30s)

A voice-started session ends when the holder has been silent for 30 seconds. Longer than FACE_LOSS_GRACE because voice-only users don't have the visual anchor — we give them more benefit of the doubt.

### 51.4 DISPUTE_MAX_DURATION (180s)

Disputed sessions can't self-expire via the above because the sensor may keep matching the wrong person (keeping `last_face_seen` fresh) while the speaker is actually a different person. Without this force-close, the session could live indefinitely. 3 minutes is long enough for a misunderstanding to be clarified but short enough that stuck states recover.

## 52. Primary Person Selection

> **Phase 3B addendum.** The notion of a "primary person" as the sole speaker of a turn is softening post-Phase 3B. In multi-person rooms, every turn still has a *current speaker* (the pid whose audio was captured), but the brain decides *addressee* independently via the `[addressing:X]` marker (Part XXVI §168). Future refactors may drop the module-level "primary pid" concept in favour of passing the current speaker as a parameter — that's part of Phase 3 backlog (Q3 History Architecture and deferred RoomOrchestrator class).

## 52b. The Room Session Lifecycle

See **Part XXVI §163** for the full story. Briefly: `PipelineStateStore.room_session_id` (currently-active room session id), `room_started_at` (timestamp), and `room_participants` (set of person_ids) together describe the current multi-person room. Minted on first session open after empty; populated on every subsequent `_open_session`; torn down in `_on_room_end` when the last session leaves. `_on_room_end` schedules `BrainOrchestrator.synthesize_room` fire-and-forget so room-end latency doesn't block the next turn.


### 52.1 `_primary_person_id() -> pid | None`

When multiple sessions are active, which one is "primary" — the one the brain is currently responding to?

```python
def _primary_person_id() -> str | None:
    snaps = _session_store.peek_all_snapshots()
    if not snaps:
        return None
    # Most recently spoken wins; tie-break by pid (deterministic, Session 34 Bug-5)
    return max(snaps, key=lambda s: (s.last_spoke_at, s.person_id)).person_id
```

Simple ordering: the person who spoke most recently is the primary. Tie-break on pid keeps it deterministic.

### 52.2 Why "most recent speaker"

In a multi-person scene, the brain's role is to answer whoever just spoke. We don't need to track a "conversation leader" — each turn can have a different speaker, and the brain sees the full scene roster through the `<<<SCENE>>>` block.

### 52.3 Interaction with routing

The primary is computed *before* the current turn's reconciler call (Part X §59). Routing may switch to a different pid — that pid becomes the primary for this turn's `conversation_turn` call, and after `log_turn` records the user turn, the session's `last_spoke_at` is updated via `update_voice_heard` or `update_face_seen`, making this pid the primary on the next iteration.

---
---

# Part IX — Identity Evidence

## 53. The `VoiceEvidence` Dataclass

> **Architectural note (2026-05-15).** Pre-P0.7, identity evidence lived in a free-form `identity_evidence: dict` field inside each session's free-form dict. A `_update_identity_evidence(person_id, **fields)` writer guarded against typos via a KeyError on unknown field names. P0.7 (Part XL) replaced both with a typed `VoiceEvidence` slotted dataclass nested inside `Session`. The typo-detection contract is now structural — `slots=True` makes every typo a runtime `AttributeError` — and the writers are named transition methods on `SessionStore` instead of a single multi-purpose helper.

The `VoiceEvidence` dataclass on every session captures "how confident are we that this session's pid is the person currently speaking?":

### 53.1 Fields (from `core/session_state.py`)

```python
@dataclass(slots=True)
class VoiceEvidence:
    # voice channel
    voice_match_conf:      float = 0.0          # last voice ID cosine — CAN BE NEGATIVE
    voice_last_heard_ts:   float = 0.0          # unix ts of last voice ID match
    voice_sample_count:    int = 0              # DB-hydrated at open_session
    bootstrap_credits:     int = 0              # remaining credits from engagement gate
    recent_voice_confs:    list[float] = field(default_factory=list)   # maxlen-3 deque
    # face channel
    face_match_conf:       float = 0.0          # last face recognition cosine (0 if none)
    face_last_seen_ts:     float = 0.0          # unix ts of last face match
    anti_spoof_live:       bool = False         # last anti-spoof verdict
    anti_spoof_score:      float = 0.0          # last live_prob
```

`anti_spoof_last_ts` (separate field for the timestamp of the most recent anti-spoof check) is currently merged into `face_last_seen_ts` since the greeting path and the background vision scan both write them together. If P0.S1's anti-spoof-on-every-match work surfaces a need for a separate timestamp, it'll be added as an explicit field on `VoiceEvidence`.

### 53.2 `voice_match_conf` can be negative

ECAPA-TDNN cosine similarity between anti-correlated speakers is routinely negative (values like -0.05, -0.08 are normal). `voice_match_conf` carries the *actual* cosine returned by `voice.identify()`, NOT the absolute value. The reconciler's P4 rules (Part X §60.5) interpret negative scores as "confident not-this-speaker" signal; the post-2026-05-02 negative-cosine fix made this distinction load-bearing. Storing the raw cosine preserves the signal.

### 53.3 Ephemeral vs persistent

- **Face-side fields are ephemeral** — re-established each session. The face seen 5 minutes ago isn't guaranteed to be the same person 30 minutes later.
- **`voice_sample_count` is DB-persistent** via hydration. Voice samples persist across sessions; sample count reflects that. `_open_session` hydrates from `_voice_gallery_store.peek_size(pid)` and falls back to `db.count_voice_embeddings(pid)` if the cache is stale (Obs 1, Part XL §266).
- **`bootstrap_credits` is per-session** — once consumed, gone (replenishment for engaged voice-only strangers via Session 94 lands here too; see §337 for the known fix-queued bug after promotion).

## 54. The Named-Transition Writer Invariant

Pre-P0.7 had `_update_identity_evidence(person_id, **fields)` — one writer, validation via KeyError on unknown fields. P0.7 replaced this with named transition methods on `SessionStore`, each one writing exactly the field set its name implies:

```python
# In core/session_state.py::SessionStore
async def update_voice_heard(self, pid: str, conf: float, ts: float) -> None:
    """Update voice_match_conf + voice_last_heard_ts; append to recent_voice_confs."""

async def update_face_seen(self, pid: str, ts: float, conf: float, live: bool) -> None:
    """Update face_match_conf + face_last_seen_ts + anti_spoof_live."""

async def set_bootstrap_credits(self, pid: str, n: int) -> None:
    """Seed bootstrap credits at engagement-gate pass."""

async def decrement_bootstrap_credits(self, pid: str) -> bool:
    """Consume one credit on accumulation. Returns False if 0; no-mutate."""
```

### 54.1 Why named transitions instead of a single multi-purpose writer

Three reasons over the pre-P0.7 design:

1. **Semantic clarity.** `update_voice_heard(pid, conf, ts)` reads better than `_update_identity_evidence(pid, voice_match_conf=..., voice_last_heard_ts=...)`. Future maintainers immediately see what the call site means.
2. **Atomic multi-field writes.** `update_voice_heard` writes 3 fields (`voice_match_conf`, `voice_last_heard_ts`, append to `recent_voice_confs`) in one lock acquisition. The pre-P0.7 caller had to make 3 separate `_update_identity_evidence` calls and the dispute auto-clear's 3-consecutive-voice-match check could race with a deque mutation between them.
3. **Type safety.** `slots=True` on `VoiceEvidence` makes `e.voice_match_conff = 0.5` (note the typo) a runtime `AttributeError`. The dynamic `**fields` writer needed an explicit KeyError check; the typed dataclass needs none.

### 54.2 Call sites and which transition fires where

| Call site | Transition method | What it writes |
|---|---|---|
| Greeting path (anti-spoof passes, about to greet known) | `update_face_seen` | face_match_conf, face_last_seen_ts, anti_spoof_live=True, anti_spoof_score |
| Background vision scan (face recognised as active session pid) | `update_face_seen` | same shape |
| Per-turn voice ID (voice matches session holder) | `update_voice_heard` | voice_match_conf, voice_last_heard_ts, append to recent_voice_confs |
| Engagement gate pass (face captured: known/best_friend greeting) | `set_bootstrap_credits(N_INITIAL_VOICE_BOOTSTRAP)` + `update_face_seen` + `set_voice_face_confirmed(True)` | bootstrap_credits, face evidence, voice_face_confirmed |
| Engagement gate pass (voice-only: stranger said system name, no face) | `set_bootstrap_credits(N_INITIAL_VOICE_BOOTSTRAP)` + `set_voice_only_origin(True)` | bootstrap_credits, voice_only_origin (no face evidence — fixes Bug C, see Part XL §263) |
| Accumulation success in `_accumulate_voice` | `decrement_bootstrap_credits` (Path C) OR no-op (Path A/B); voice_sample_count bumped via `_voice_gallery_store.set_size` | bootstrap_credits decrement |

### 54.3 Silent no-op on missing session

If the session was closed between the caller's snapshot and the transition call, the transition's first line — `sess = self._sessions.get(pid); if sess is None: return` — returns silently. Caller doesn't need null-checks. This is especially important for async paths like `_accumulate_voice` where the session may close while the task is pending.

## 55. Path A / B / C Accumulation Policy

### 55.1 The function

```python
def _voice_accum_allowed(session: dict) -> tuple[bool, str, str]:
    ev = session.get("identity_evidence") or {}
    now = time.time()

    # Path A — recent confident face witness
    face_age = now - ev.get("face_last_seen_ts", 0.0)
    if (ev.get("face_match_conf", 0.0) >= VOICE_ACCUM_FACE_WITNESS_MIN_CONF
            and ev.get("anti_spoof_live", False)
            and face_age <= VOICE_ACCUM_FACE_WITNESS_MAX_AGE_SEC):
        return (True, f"face witness (...)", "face_witness")

    # Path B — mature voice profile self-matching
    if (ev.get("voice_match_conf", 0.0) >= VOICE_ACCUM_VOICE_SELF_MATCH_MIN
            and ev.get("voice_sample_count", 0) >= VOICE_ACCUM_MATURE_SAMPLE_COUNT):
        return (True, f"voice self-match (...)", "voice_self_match")

    # Path C — bootstrap credits from engagement gate
    if ev.get("bootstrap_credits", 0) > 0:
        return (True, f"bootstrap (...)", "bootstrap")

    return (False, f"no witness (...)", "refused")
```

### 55.2 Path A — face witness

The speaker's face is currently in frame, recognition confidence is high (≥ 0.45), anti-spoof passed, and the face was seen within the last 10 seconds. Voice can be accumulated under this pid with high trust.

This path covers the normal case: a known person sitting in front of the camera.

### 55.3 Path B — mature voice profile

The pid has ≥ 5 voice samples (profile is "mature"), and the current voice ID matches that profile at cosine ≥ 0.45. Voice can be accumulated.

This path covers the user who stepped out of frame but keeps talking. No face witness, but the voice profile is trustworthy enough on its own.

### 55.4 Path C — bootstrap credits

The session was opened via an engagement gate (engagement_gate_passed=True) and `bootstrap_credits > 0`. We grant the accumulation without voice-self-match or face-witness — this is how a brand-new voice profile *starts*. Without Path C, a fresh profile couldn't reach the `voice_sample_count ≥ 5` threshold of Path B, because Path A requires face (may not have) and Path B requires samples (doesn't have yet).

## 56. Bootstrap Credits

### 56.1 The arithmetic gap (Bug A)

`N_INITIAL_VOICE_BOOTSTRAP=6` must exceed `VOICE_ACCUM_MATURE_SAMPLE_COUNT=5`. Discovered in Session 64 (Bug A) when we saw voice-only Chloe stalling at 3 samples: bootstrap=3, mature=5, so Path C exhausted at sample 3 and Path B couldn't engage yet. Raised bootstrap to 6 with an invariant test.

The test:
```python
def test_bootstrap_budget_exceeds_mature_threshold():
    assert N_INITIAL_VOICE_BOOTSTRAP > VOICE_ACCUM_MATURE_SAMPLE_COUNT, (
        "BOOTSTRAP must exceed MATURE — otherwise voice-only strangers get stuck"
    )
```

Guards against any future tuning that would re-introduce the gap.

### 56.2 Credits are consumed, not reset

Once consumed, bootstrap_credits goes to 0. Session restart starts fresh — but with DB-hydrated voice_sample_count (Obs 1), so a restarted session with 6+ prior samples goes straight to Path B and doesn't need bootstrap.

## 57. DB-Hydrated Voice Sample Count

### 57.1 The problem

Before Session 64 Bug A, `_open_session` initialised `voice_sample_count=0`. A voice-only stranger whose session expired at 30 seconds would lose their profile progress on reopen.

### 57.2 The fix

Session 64 Part 1 hydrates from `_voice_gallery_sizes` at open time. Post-review Obs 1 hardened it to prefer `db.count_voice_embeddings(pid)` over the cache so out-of-process deletes (dashboard, CLI) can't leave stale counts.

```python
_db_voice_count = _voice_gallery_sizes.get(person_id, 0)
if _face_db_ref is not None:
    try:
        _db_voice_count = _face_db_ref.count_voice_embeddings(person_id)
        if _voice_gallery_sizes.get(person_id, -1) != _db_voice_count:
            _voice_gallery_sizes[person_id] = _db_voice_count
    except Exception:
        pass
```

DB-preferred, cache-fallback, opportunistic cache repair, exception-guarded.

### 57.3 Dream loop reconciliation (Obs 1)

Every dream cycle, the dream loop re-loads `db.load_voice_profile_sizes()` and compares to `_voice_gallery_sizes`. Divergence triggers a full reload (both sizes and mean embeddings) plus a log line `[Dream] Voice gallery cache reconciled: N pid(s) out of sync`.

## 58. The `<<<IDENTITY EVIDENCE>>>` Brain Block

### 58.1 Purpose

The brain sees a snapshot of the evidence every turn in a dedicated system-prompt block. This gives the LLM the sensor state it needs to decide, for example, whether to trust a claimed identity change.

### 58.2 Block format

```
<<<IDENTITY EVIDENCE>>>
  face: conf=0.85, age=1.2s, anti-spoof=live (score=0.98)
  voice: conf=0.62, samples=12, age=0.8s
  bootstrap_credits: 0
  verdict: high-confidence identity
<<<END>>>
```

### 58.3 Verdict heuristic

The verdict is computed in `brain.py`:

```python
_face_ok = (
    _face_conf >= VOICE_ACCUM_FACE_WITNESS_MIN_CONF
    and _live
    and _face_age is not None
    and _face_age <= VOICE_ACCUM_FACE_WITNESS_MAX_AGE_SEC
)
_voice_ok = (
    _voice_conf >= VOICE_ACCUM_VOICE_SELF_MATCH_MIN
    and _voice_n >= VOICE_ACCUM_MATURE_SAMPLE_COUNT
)
if _face_ok and _voice_ok:
    _verdict = "high-confidence identity"
elif _face_ok or _voice_ok:
    _verdict = "medium-confidence identity (one channel weak or missing)"
elif _face_conf > 0 or _voice_conf > 0:
    _verdict = "low-confidence identity"
else:
    _verdict = "no sensor evidence"
```

Uses the same `VOICE_ACCUM_*` constants as `_voice_accum_allowed`. Session 62 fixed a drift bug where `brain.py` used literals (0.45 / 5 / 10.0) that didn't track config changes — now they're imported from the same place.

### 58.4 Toggle

`IDENTITY_EVIDENCE_BLOCK_ENABLED=True` globally. Can be turned off via config for debugging prompts.

### 58.5 Why the brain needs this

Two cases:
1. **Dispute detection.** If the speaker claims to be Jagan but the evidence says low-confidence, the brain can call `report_identity_mismatch` to flag dispute.
2. **Trust calibration.** The brain's reply can be hedged when evidence is weak ("I think I remember you — are you...?") vs confident when it's strong.

---
---

# Part X — Multi-Person Routing

> **Architectural note (2026-05-17).** The original routing function `_resolve_actual_speaker` in `pipeline.py` was the project's first multi-person routing primitive (Sessions 26-49). After the voice/vision independence rearchitecture (Phases 1–4 of `VOICE_VISION_INDEPENDENCE_PLAN.md`, see Part XXXII) the routing logic moved into `core/reconciler.py::reconcile`, a 22-rule cascade that consumes a structured `IdentityClaim` + `PresenceState` + `SessionState` and emits a single `RoutingDecision`. The Phase 4 cutover (`ROUTING_USE_RECONCILER=True`, Session 121) made the reconciler primary; P0.10 Phase 2 (2026-05-17) **deleted `_resolve_actual_speaker` entirely**. This Part describes the production routing surface as it exists today — the reconciler. The historical algorithm and the Bug-W coverage gap that the deletion exposed are documented in **Part XLIII §285-§292**.

