# P0.S1 — Anti-Spoof on Every Face Match — Phase 0 Audit

**Date:** 2026-05-18
**Author:** architect
**Status:** Phase 0 audit (pre-Plan-v1). Grep-verified findings + D1-D8 decisions surfaced for joint architect-auditor lock before Plan v1 is drafted. Zero production-code changes in this document.

---

## Premise check (load-bearing — the architect's original framing was wrong)

The locked-sequence framing for P0.S1 was:

> "Every code path that calls `FaceDB.add_embedding(...)` with `source='recognition_update'` must pass through `verify_live(...)` first. The recognition update path (background scan, voice-route-confirmed face) currently writes to the gallery on a high-confidence face match WITHOUT necessarily going through anti-spoof. A presentation attack (photo, screen, video replay) could poison the legitimate person's gallery."

**This premise is wrong.** The recognition_update path is **already** anti-spoof gated with the strictest fail-closed semantics in the codebase.

`pipeline.py:6466-6482` (the only recognition_update call site in production):

```python
if directly_recognized and quality >= FACE_QUALITY_SELF_UPDATE:
    last = _conversation_store.peek_last_self_update(person_id)
    if time.time() - last >= SELF_UPDATE_COOLDOWN and conf >= SELF_UPDATE_THRESHOLD:
        _anti_spoof_ok = (
            _anti_spoof_checker is not None
            and getattr(_anti_spoof_checker, "available", False)
            and verify_live(frame, det.bbox, _anti_spoof_checker)
        )
        if not _anti_spoof_ok:
            # Fail-closed: skip the write when liveness is unavailable or failed.
            await _conversation_store.touch_self_update(person_id, time.time())
        else:
            added = db.add_embedding(person_id, embedding, "recognition_update", conf)
```

This is **stricter** than what P0.S1 was originally meant to add. The current check refuses the write when:
1. The checker is None (anti-spoof not configured)
2. OR the checker's MiniFASNet model is not loaded (`available=False`)
3. OR the liveness verdict is False

The pre-P0.S1 state already has fail-closed-when-unavailable semantics on this path. Session 51 Finding #1 hardened this in 2026-05-08.

**This is the same shape as P0.10 Phase 0** (architect thought Bug-W was in legacy; audit revealed Bug-W was in the new reconciler). The premise reset here is just as load-bearing: shipping a Plan v1 that "adds anti-spoof to recognition_update" would be redundant work against a path that already has it, while the real gap stays unfixed.

---

## The actual gap — `progressive_enroll` at `pipeline.py:7690`

`VALID_EMBEDDING_SOURCES` in `core/db.py:34` enumerates four sources. Three are non-legacy:

| Source | Call site | Anti-spoof gated? |
|---|---|---|
| `enrollment` | `pipeline.py:3367` (first_boot_flow), `pipeline.py:3440` (enrollment_flow), `enroll.py:95` (CLI) | ✓ `verify_live` immediately upstream at lines 3351, 3421, and enroll.py:74 |
| `recognition_update` | `pipeline.py:6479` (background vision self-update) | ✓ Strictest fail-closed (lines 6469-6478) |
| `progressive_enroll` | `pipeline.py:7690` (voice-only stranger said system name → store tracked face emb) | ✗ **NO ANTI-SPOOF CHECK** |
| `legacy_unknown` | (no production callers — migration-only marker) | n/a |

The `progressive_enroll` path runs when a previously-unrecognized face on camera says the system name ("Hey Kara") and triggers the engagement gate. At that moment the pipeline:

1. Creates a DB entry for the new stranger (`db.add_stranger(...)`).
2. Fetches the face embedding the background vision loop had captured for this SORT track via `_track_store.peek_embedding(_gate_track)`.
3. Commits the embedding to the gallery via `db.add_embedding(_cur_pid, _gate_emb, "progressive_enroll")`.

**No anti-spoof check fires anywhere on this path.** The embedding came from the background vision loop's tracking buffer — a face that's been on camera for some duration. A presentation attack (photo, screen-replayed face) that gets tracked across frames and accumulates an embedding in `_track_store` would, at the moment the attacker (or attacker's audio replay) says the system name, get committed to the gallery as an enrolled stranger.

The mitigation today is that the attacker has to ALSO produce a believable "say the system name" audio — but a recording could do that. Combined with replay or a held-up photo, the system enrolls a poisoned identity that grants `stranger` privileges (search_web, conversation persistence, voice gallery growth). Subsequent gallery drift via recognition_update writes (which ARE anti-spoof gated) cannot un-poison the initial embedding — the bad embedding is permanently in the gallery until manual `delete_person`.

---

## Why the gap exists structurally

The progressive_enroll path consumes a face embedding produced earlier (background vision loop, line 2619-2621) and stored in `_track_store`. By the time the engagement gate fires, the frame that produced the embedding may already be discarded. The track store holds the embedding, not the source frame.

So the architect's natural framing — "insert `verify_live(frame, bbox, checker)` immediately before `add_embedding`" — fails because there is no `frame` variable available at `pipeline.py:7690`. The frame was processed and freed minutes ago.

This is the architectural decision P0.S1 has to make. Three plausible designs, surfaced in D2 below.

---

## D1-D8 architectural decisions surfaced for joint lock

### D1 — Gate placement: per-call-site vs centralised in `add_embedding`

Three options for where the anti-spoof gate lives:

- **D1.a — Per-call-site (status quo, extended).** Each upstream caller of `add_embedding` carries its own `verify_live(...)` check, identical to the recognition_update path's structure. AST scan enforces every non-legacy source has an upstream gate.
- **D1.b — Centralised in `add_embedding`.** `FaceDB.add_embedding(...)` itself takes a `verify_live` callable or anti-spoof verdict argument; refuses the write when missing. Single point of enforcement; upstream callers can't bypass.
- **D1.c — Hybrid.** Gate inside `add_embedding` as the safety net AND structural invariant requiring upstream gating too (defense in depth). Belt-and-braces.

**Architect's lean:** D1.c. The current code is already partially shaped this way (the recognition_update site has the upstream gate; centralising it doesn't break anything; the structural invariant + safety net both fire). Open for auditor pushback toward D1.b for simpler narrative.

### D2 — Frame source for `progressive_enroll`

Three options for what frame anti-spoof gets to inspect at gate time, given that the embedding-capture frame is gone:

- **D2.a — Capture a fresh frame at gate time.** `camera.read()` immediately before the `add_embedding` call. Pro: liveness verdict is fresh. Con: adds a camera-read latency at the engagement moment (~30ms on dev hardware); also captures a frame at a different moment than the embedding, so liveness verdict and embedding identity don't strictly correspond.
- **D2.b — Carry anti-spoof verdict alongside the embedding in `TrackStore`.** `_track_store.upsert_embedding(...)` is extended to also store `anti_spoof_live` + `anti_spoof_score` + `frame_at` timestamp. Anti-spoof runs in the background vision loop alongside recognition (which it partially does already — line 2647 has a `verify_live` for "new person in frame" logging). At gate time, `progressive_enroll` reads the stored verdict. Pro: liveness verdict corresponds exactly to the embedding-capture frame. Con: more plumbing through TrackStore.
- **D2.c — Read the most recent frame from `VisionFrameStore` and run anti-spoof against the gate-time bbox.** `VisionFrameStore.peek_frame_if_fresh(...)` already exists (called at line 6792 for the voice-fallback path). Pro: cheap, no camera read. Con: frame may be 0.5s stale; bbox is the track's last bbox not the frame's.

**Architect's lean:** D2.b. Long-term cleanest architecture — every face embedding carries its provenance evidence. P0.S1 sets up the right primitive for future security work (P0.S5+). Open for auditor pushback toward D2.a for simpler MVP.

### D3 — Failure behavior

- **D3.a — Fail-closed reject.** Refuse the `add_embedding` if liveness unavailable / failed. Log the rejection. Stranger session opens but face embedding is NOT stored. Their face will not be recognized in future sessions (they'd have to re-engage and the attack would have to re-pass anti-spoof, presumably failing again). Voice profile still grows normally because voice-only enrollment is not blocked.
- **D3.b — Fail-closed reject + watchdog alert.** Same as D3.a + if `progressive_enroll` rejections exceed a threshold in a time window, fire a watchdog alert (potential presentation-attack signal).

**Architect's lean:** D3.b. Watchdog signal is cheap to add and gives operators visibility into attack attempts. Consistent with the project's "fail-closed on security AND log to watchdog when patterns suggest attack" pattern (see Part XV §107 dispute-rename burst watchdog).

### D4 — Scope: is `legacy_unknown` also gated?

`legacy_unknown` exists in `VALID_EMBEDDING_SOURCES` per `core/db.py:38` as a migration-only marker, with an inline comment `# one-time migration only — do not use in new code`.

- **D4.a — Don't gate.** Migration-only, no production callers, AST invariant catches any future caller.
- **D4.b — Gate.** Defensive — if any future migration path uses it, the gate fires.
- **D4.c — Delete the source entirely.** No production code uses it. The frozenset can drop the entry; any future need re-introduces it under a real name.

**Architect's lean:** D4.c. Cleanest is to remove the dead source rather than gate-around-it. But this is borderline scope creep on P0.S1; if the auditor prefers minimal scope, D4.a is fine (the AST invariant catches any future user).

### D5 — Structural invariant shape

- **D5.a — Forward AST scan.** Every `add_embedding(..., source=<non-legacy>, ...)` call site in production code must have a `verify_live(...)` call within the same function body upstream of it.
- **D5.b — Forward + inverse.** D5.a PLUS an inverse scan asserting every `verify_live(...)` site in production code either gates an `add_embedding` OR is documented as a defense-in-depth check elsewhere (engagement signaling, scene logging).
- **D5.c — Source-list invariant.** A frozenset `EMBEDDING_SOURCES_REQUIRING_ANTI_SPOOF = {"enrollment", "recognition_update", "progressive_enroll"}` in `core/db.py`. The forward AST scan checks against this set. Adding a new source forces an explicit decision: anti-spoof required or not.

**Architect's lean:** D5.c paired with D5.a. The frozenset is the single source of truth (Part XXII §138); the AST scan enforces. The inverse check (D5.b) is overkill for P0.S1 — the verify_live sites that don't gate add_embedding are legitimately serving different purposes (greeting log, scene heartbeat).

### D6 — Throttling

Anti-spoof inference is ~30-50ms per call on dev hardware. The recognition_update path already has `SELF_UPDATE_COOLDOWN` throttling so the gate is rate-limited by design. The progressive_enroll path fires once per session, not per turn — no throttling needed.

- **D6.a — No throttling.** progressive_enroll is one-shot per session.
- **D6.b — Cache verdict by frame_hash for 1 second.** Defensive against future per-turn gates (none planned).

**Architect's lean:** D6.a. No need; revisit if a future path adds high-frequency anti-spoof.

### D7 — Replay-fixture coverage

P0.0.7 Step 7 (Part XLIX §320) shipped 4 reusable scenario builders. `VisionFramePayload` carries `anti_spoof_live` + `anti_spoof_score` — this was the load-bearing prerequisite for P0.S1.

`build_stranger_first_encounter` emits 3 vision_frame events with `anti_spoof_live=True` before the engagement-gate `audio_in` and `routing_decision`. The replay regression test for P0.S1 needs to verify:

1. **Gate passes when fixture frames carry `anti_spoof_live=True`** → progressive_enroll add_embedding fires.
2. **Gate fails when fixture frames carry `anti_spoof_live=False`** → add_embedding does NOT fire; session opens (voice-only enrollment proceeds) but face embedding rejected.
3. **Gate fails when fixture frames carry `anti_spoof_live=None`** (model unavailable) → fail-closed: add_embedding does NOT fire.

**Decision:** add a new scenario builder `build_stranger_first_encounter_with_spoof_attempt` or parameterize the existing builder with `anti_spoof_live: bool | None = True`. Auditor's call which is cleaner.

### D8 — Validation gate

After Phase N closes, what gates the follow-up live-canary?

- **D8.a — Pytest-green sufficient.** Standard discipline.
- **D8.b — Live validation window.** Production canary with deliberate presentation-attack attempt (Jagan holds a phone showing his own face during the engagement gate) → verify the gate fires and the embedding is rejected. Documented in `tests/p0_s1_validation_runbook.md`.

**Architect's lean:** D8.b. Schema-migration and routing-cutover phases (P0.9, P0.10) have live-validation gates; security phases especially should. The attack is easy to stage; failure to catch it would be a real bug.

---

## What this audit is NOT claiming

To stay honest about scope:

- **Anti-spoof model quality is out of scope.** MiniFASNet is what we have; tuning ANTISPOOFING_THRESHOLD or swapping models is separate work.
- **Voice spoofing is out of scope.** P0.S1 covers face presentation attacks only. Voice replay attacks are a future P0.S item.
- **Gallery-poisoning via recognition_update drift is out of scope.** That path is already gated; the SELF_UPDATE_CENTROID_MIN + ANTISPOOFING combo already protects it. P0.S1 closes a different gap.
- **Pre-existing enrolled identities are out of scope.** P0.S1 cannot un-poison a gallery that's already been poisoned. Audit-and-repair via `audit_person.py` is the right tool for that.

---

## Test-plan sketch (for Plan v1, after D-decisions lock)

Anticipating the test surface that will land in Plan v1:

| Test | Scope | Asserts |
|---|---|---|
| `test_progressive_enroll_rejects_when_anti_spoof_fails` | Behavioural | Stub `verify_live → False`; assert `add_embedding` not called; assert stranger session DOES open (voice-only path); assert face embedding absent from gallery |
| `test_progressive_enroll_rejects_when_checker_unavailable` | Behavioural | Set `_anti_spoof_checker.available = False`; assert same as above (fail-closed) |
| `test_progressive_enroll_passes_when_anti_spoof_passes` | Behavioural | Stub `verify_live → True`; assert `add_embedding` called with `source="progressive_enroll"` |
| `test_anti_spoof_invariant_every_non_legacy_source_gated` | AST structural | Scan `pipeline.py` + `enroll.py` for every `add_embedding(..., source=<X>)` call where `X ∈ EMBEDDING_SOURCES_REQUIRING_ANTI_SPOOF`; assert each has an upstream `verify_live(...)` call OR is wrapped by a gating helper |
| `test_anti_spoof_source_list_frozen` | Invariant | `EMBEDDING_SOURCES_REQUIRING_ANTI_SPOOF` is a frozenset; equals `VALID_EMBEDDING_SOURCES - {"legacy_unknown"}` |
| `test_progressive_enroll_replay_fixture_with_spoof_True` | Replay smoke | Build scenario with `anti_spoof_live=True`; replay through reconciler/pipeline; assert face embedding stored |
| `test_progressive_enroll_replay_fixture_with_spoof_False` | Replay smoke | Same scenario with `anti_spoof_live=False`; assert face embedding rejected |
| `test_progressive_enroll_replay_fixture_with_spoof_None` | Replay smoke | Same scenario with `anti_spoof_live=None`; assert face embedding rejected (fail-closed-on-unavailable) |
| `test_watchdog_fires_on_progressive_enroll_burst` | Behavioural (if D3.b locked) | N consecutive rejections within window → watchdog alert |

Approximately 9 tests. If D2.b (TrackStore-carries-verdict) is locked, additional tests for the TrackStore schema extension (3-5 tests on the upsert/peek path).

---

## Estimated effort

Once D-decisions lock and Plan v1 is approved:

- **D2.a (fresh camera frame)**: 2-3 hours of code + tests. Smallest scope.
- **D2.b (TrackStore-carries-verdict)**: 1 day. Schema extension on `_track_store` + plumbing the verdict through background vision loop + progressive_enroll consumer + tests.
- **D2.c (VisionFrameStore peek)**: 4-6 hours of code + tests. Middle ground.

Either D2.a or D2.c could ship the same day after Plan v1 lock. D2.b is a half-day to one-day spec because it touches the TrackStore architecture.

---

## Next steps (waiting on auditor)

1. **Auditor reviews this Phase 0 audit document.**
2. **Auditor locks D1-D8** (or pushes back with alternatives).
3. **Architect drafts Plan v1** against the locked decisions. Target: same day as D-lock.
4. **Auditor reviews Plan v1.** Plan v2 (if needed) incorporates feedback.
5. **Joint sign-off → code phase starts.** Per the spec-first review cycle discipline (6-for-6).

---

## Reference documents

- `core/db.py:34` — `VALID_EMBEDDING_SOURCES` frozenset
- `core/db.py:574` — `FaceDB.add_embedding` signature + assertion
- `core/vision.py::verify_live` — the canonical wrapper (Session 46 Finding D)
- `core/vision.py::AntiSpoofChecker` — MiniFASNet ensemble (Session 52)
- `pipeline.py:6466-6482` — the recognition_update gate (reference shape for progressive_enroll)
- `pipeline.py:7670-7710` — the progressive_enroll gap site
- `tests/fixtures/event_log_fixtures.py::build_stranger_first_encounter` — replay scaffold ready for P0.S1 anti-spoof scenarios (Part XLIX §320)
- `core/event_log/types.py::VisionFramePayload` — `anti_spoof_live` + `anti_spoof_score` fields, load-bearing for P0.S1 replay-based regression tests
