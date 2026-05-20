# P0.S1 — Anti-Spoof on Every Face Match — Plan v1

**Date:** 2026-05-18
**Author:** architect
**Status:** Plan v1. Drafted against locked D1-D10 + three contract clauses from the joint Phase-0 audit lock. Standing by for auditor review → Plan v2 (if needed) → joint sign-off → code phase.
**Phase-0 audit:** `tests/p0_s1_audit.md` (2026-05-18, premise reset documented + D1-D10 surfaced).

---

## 1. Locked decision reference

For ease of review, the locked D-decisions are summarised here. Full rationale is in `p0_s1_audit.md` + the auditor's lock message.

| ID | Decision | Locked at |
|---|---|---|
| **D1** | Gate placement | **Hybrid** — per-call-site explicit `verify_live` + `add_embedding` catch-all enforcing verdict argument |
| **D2** | Frame source for progressive_enroll | **D2.b** — TrackStore carries anti-spoof verdict co-temporal with embedding |
| **D2.b.i** | Anti-spoof frequency in background vision loop | **Every embedding-capture** — same frame, no verdict caching across frames |
| **D3** | Failure handling | **Fail-closed reject + watchdog burst alert** |
| **D4** | `legacy_unknown` source | **Delete** — pending doc-grep verification (Phase 1 pre-step) |
| **D5** | Invariant shape | **Source-list frozenset + forward AST scan** (`ALLOWED_EMBEDDING_SOURCES_REQUIRING_ANTI_SPOOF`) |
| **D6** | Throttling on gate | **None** — progressive_enroll is one-shot per session |
| **D7** | Replay-fixture coverage | **Parameterize** `build_stranger_first_encounter` with `anti_spoof_live: bool | None = True` |
| **D8** | Validation gate | **Live canary** with multi-attack-type runbook |
| **D9** | Session disposition after rejection | **Voice-only fallthrough** (D9.a) + **tripwire** asserting no alternate path upgrades the track |
| **D10** | User-facing surfacing | **Dashboard yes, TTS no** (D10.c) |

Three Plan v1 contract clauses additionally locked:
- **C1** — Anti-spoof unavailable contract: `_anti_spoof_checker is None OR not .available OR verify_live() == False` → refuse. Two distinct reason codes: `"rejected"` (verdict False) vs `"unavailable"` (checker None or .available False). Dashboard / watchdog can distinguish.
- **C2** — Watchdog burst threshold: 3 rejections / 60s / per-track. Breach surfaces to dashboard; does NOT lock out other tracks; does NOT lock out the voice channel.
- **C3** — Pre-existing poisoned galleries filed as P0.S1.X backlog. NOT in P0.S1 scope.

Plus the C0 same-frame contract from D2.b.i auditor refinement:
- **C0** — Verdict-embedding atomicity: the anti-spoof verdict MUST be derived from the same frame as the embedding. No cross-frame verdict caching. Atomic upsert to TrackStore.

---

## 2. Architectural overview

P0.S1 introduces a **face-embedding provenance** model: every face embedding persisted to the gallery carries with it the anti-spoof verdict obtained against the same frame that produced the embedding. The verdict is structurally co-located with the embedding, persisted atomically, and read by every consumer that writes to the gallery.

```
┌──────────────────────────────────────────────────────────────────────┐
│  Background vision loop  (pipeline.py:2619 zone)                     │
│                                                                      │
│    frame ──► detector.detect ──► face crops ──► embedder.embed       │
│      │                            │                  │               │
│      │                            └── bbox           ▼               │
│      └────────────────────► verify_live(frame, bbox, checker)        │
│                                                  │                   │
│                                                  ▼                   │
│                              _track_store.upsert_embedding_with_verdict(│
│                                  track_id, embedding,                │
│                                  anti_spoof_live, anti_spoof_reason, │
│                                  captured_at)                        │
│                              # atomic — same TrackEntry              │
└──────────────────────────────────────────────────────────────────────┘
                                  │
                          time passes; track stable
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│  progressive_enroll gate  (pipeline.py:7690 zone)                    │
│                                                                      │
│    user says "Hey Kara" → engagement gate passes                     │
│    snap = _track_store.peek_snapshot(gate_track)                     │
│    if snap.anti_spoof_live is True:                                  │
│        db.add_embedding(                                             │
│            pid, snap.embedding, "progressive_enroll",                │
│            anti_spoof_verdict=True,                                  │
│        )  # face-witness path                                        │
│    else:  # False OR None — fail-closed                              │
│        _record_anti_spoof_rejection(                                 │
│            pid, gate_track,                                          │
│            reason=snap.anti_spoof_reason or "no_verdict",            │
│        )  # watchdog + dashboard                                     │
│        # D9.a voice-only fallthrough                                 │
└──────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│  FaceDB.add_embedding catch-all  (core/db.py:574 zone)               │
│                                                                      │
│    if source in ALLOWED_EMBEDDING_SOURCES_REQUIRING_ANTI_SPOOF:      │
│        assert anti_spoof_verdict is True, (                          │
│            f"add_embedding called with source={source!r} but no      │
│             verdict — caller MUST gate with verify_live first")      │
└──────────────────────────────────────────────────────────────────────┘
```

The three load-bearing properties:

1. **Verdict-embedding co-temporality (C0).** Producer-side: the verify_live call runs against the same frame variable that fed into embedder.embed. No frame switching between embedding capture and verdict; no cross-frame verdict caching. The atomic `upsert_embedding_with_verdict` puts both into the same TrackEntry in a single mutation under the TrackStore lock.

2. **Verdict-required-for-protected-source (D1 + D5).** Consumer-side enforced at both the per-call-site level (`progressive_enroll` and `recognition_update` both gate explicitly) AND at the centralised `add_embedding` level (refuses the write when a protected source is passed without `anti_spoof_verdict=True`). Double-barrel: the call site fails first (semantically obvious), the catch-all backs it up structurally.

3. **Fail-closed-on-unavailable (C1).** Distinguishable from fail-closed-on-rejection via two reason codes. `"unavailable"` → checker is None OR model not loaded. `"rejected"` → checker present, model loaded, verdict returned False. Both refuse the write; downstream observability can tell them apart.

---

## 3. Implementation phases

Four phases. Each one independently shippable, with full pytest-green between phases. Estimated total: **1.5-2 days** focused work, per the auditor's revised calibration.

### Phase 1 — Foundation (≈0.5 day)

**Pre-step: D4 doc-grep verification.** Grep `legacy_unknown` across:
- `docs/`
- `complete-plan.md`
- `everything_about_system.md`
- `KARAOS_COMPLETE_GUIDE.md`, `KARAOS_KNOWLEDGE.md`
- `tests/p0_*_plan_*.md`, `tests/p0_*_audit.md`
- `CLAUDE.md` recent-session table (last 50 sessions)

Expected outcome: zero forward-looking references. If any planned use surfaces, fall back to D4.a (keep + AST invariant prevents new callers). Document the grep result in Phase 1 closure report.

**Code changes:**

1. **`core/db.py`** — extend module-level frozensets:
   ```python
   # Existing (Session 46 Finding D):
   VALID_EMBEDDING_SOURCES: frozenset[str] = frozenset({
       "enrollment",
       "recognition_update",
       "progressive_enroll",
       # legacy_unknown DELETED in P0.S1 D4 (no production callers, no planned use)
   })

   # New:
   ALLOWED_EMBEDDING_SOURCES_REQUIRING_ANTI_SPOOF: frozenset[str] = frozenset({
       "enrollment",
       "recognition_update",
       "progressive_enroll",
   })
   # Per P0.S1 D5 — single source of truth for which sources need a verdict.
   # Equals VALID_EMBEDDING_SOURCES under D4 delete. If D4 falls back to keep,
   # this set is VALID_EMBEDDING_SOURCES - {"legacy_unknown"}.
   ```

2. **`core/config.py`** — three new constants:
   ```python
   # P0.S1 — Anti-spoof watchdog burst (C2)
   ANTI_SPOOF_BURST_THRESHOLD: int = 3
   ANTI_SPOOF_BURST_WINDOW_SECS: float = 60.0

   # P0.S1 — Reason codes for distinguishing rejection cause (C1)
   ANTI_SPOOF_REASON_REJECTED: str = "rejected"     # verify_live returned False
   ANTI_SPOOF_REASON_UNAVAILABLE: str = "unavailable"  # checker None or .available=False
   ANTI_SPOOF_REASON_PASSED: str = "passed"         # verdict True (informational)
   ANTI_SPOOF_REASON_NO_VERDICT: str = "no_verdict" # consumer-side: no captured-frame
   ```

3. **`core/track_store.py`** — TrackEntry dataclass extension:
   ```python
   @dataclass(slots=True)
   class TrackEntry:
       track_id:                str
       last_seen:               float
       last_bbox:               tuple[int, int, int, int]
       embedding:               Optional[np.ndarray] = None
       identity_pid:            Optional[str] = None
       last_recognized_at:      float = 0.0
       # P0.S1 D2.b additions — verdict co-temporal with embedding (C0):
       anti_spoof_live:         Optional[bool] = None     # True/False/None
       anti_spoof_score:        Optional[float] = None    # live_prob from MiniFASNet
       anti_spoof_reason:       Optional[str] = None      # one of ANTI_SPOOF_REASON_*
       anti_spoof_captured_at:  Optional[float] = None    # ts of the verdict frame
   ```

4. **`core/track_store.py`** — new async mutator + sync peek:
   ```python
   async def upsert_embedding_with_verdict(
       self,
       *,
       track_id: str,
       embedding: np.ndarray,
       anti_spoof_live: Optional[bool],
       anti_spoof_score: Optional[float],
       anti_spoof_reason: str,
       captured_at: float,
       bbox: tuple[int, int, int, int],
   ) -> None:
       """Atomic upsert: embedding + verdict together in a single TrackEntry mutation.
       Per P0.S1 C0 — verdict-embedding co-temporality contract.
       """
       async with self._lock:
           entry = self._entries.get(track_id)
           # ... construct or update under lock, both fields together ...

   def peek_anti_spoof_verdict(self, track_id: str) -> Optional[tuple[bool, str]]:
       """Returns (live, reason) if known, else None. Sync — single-thread-asyncio safety."""
       entry = self._entries.get(track_id)
       if entry is None or entry.anti_spoof_live is None:
           return None
       return (entry.anti_spoof_live, entry.anti_spoof_reason or ANTI_SPOOF_REASON_NO_VERDICT)
   ```

5. **`core/db.py`** — `FaceDB.add_embedding` signature extension (D1 catch-all):
   ```python
   def add_embedding(
       self,
       person_id: str,
       embedding: np.ndarray,
       source: str = "legacy_unknown",  # kept for backward-compat callers; AST invariant blocks new ones
       confidence: Optional[float] = None,
       *,
       anti_spoof_verdict: Optional[bool] = None,   # P0.S1 D1 — required for protected sources
   ) -> bool:
       # Existing source validation:
       assert source in VALID_EMBEDDING_SOURCES, (...)

       # P0.S1 D1 catch-all — refuse write if protected source lacks verdict.
       if source in ALLOWED_EMBEDDING_SOURCES_REQUIRING_ANTI_SPOOF:
           if anti_spoof_verdict is not True:
               print(
                   f"[FaceDB] BLOCKED add_embedding({person_id=!r}, {source=!r}): "
                   f"protected source requires anti_spoof_verdict=True. "
                   f"Got {anti_spoof_verdict!r}. Per-call-site gate missing?"
               )
               return False
       # ... rest of existing add_embedding body unchanged ...
   ```

**Phase 1 deliverables (test surface):**
- 1 doc-grep verification step (Phase 1 closure report; not a pytest test)
- 3-5 tests for the TrackStore extension (D2.b plumbing)
- 1 frozenset invariant test (ALLOWED_EMBEDDING_SOURCES_REQUIRING_ANTI_SPOOF shape)
- 1 add_embedding catch-all test (protected source + verdict=None → return False with log)
- 1 add_embedding catch-all test (protected source + verdict=False → return False with log)
- 1 add_embedding catch-all test (protected source + verdict=True → proceeds normally)

### Phase 2 — Producer (≈0.5 day)

**Code changes:**

1. **`pipeline.py` background vision loop** (around line 2619, the embedding-capture site in the secondary face scan):
   ```python
   _raw_emb2 = await loop.run_in_executor(None, embedder.embed, _crop)
   _emb2 = temporal_buffer.add_and_pool(_det.bbox, _raw_emb2, track_id=_det.track_id)

   # P0.S1 D2.b.i — anti-spoof at every embedding-capture, same frame (C0).
   _anti_spoof_live = verify_live(frame, _det.bbox, _anti_spoof_checker)
   _anti_spoof_score = None
   _anti_spoof_reason: str
   if _anti_spoof_checker is None or not getattr(_anti_spoof_checker, "available", False):
       _anti_spoof_reason = ANTI_SPOOF_REASON_UNAVAILABLE
       _anti_spoof_live = None  # distinguish unavailable from rejected
   elif _anti_spoof_live:
       _anti_spoof_reason = ANTI_SPOOF_REASON_PASSED
       _anti_spoof_score = getattr(_anti_spoof_checker, "last_score", None)
   else:
       _anti_spoof_reason = ANTI_SPOOF_REASON_REJECTED
       _anti_spoof_score = getattr(_anti_spoof_checker, "last_score", None)

   # Atomic upsert — verdict + embedding together (C0).
   await _track_store.upsert_embedding_with_verdict(
       track_id=_det.track_id,
       embedding=_emb2,
       anti_spoof_live=_anti_spoof_live,
       anti_spoof_score=_anti_spoof_score,
       anti_spoof_reason=_anti_spoof_reason,
       captured_at=_bv_scan_now,
       bbox=_det.bbox,
   )

   # Event log H2 (vision_frame) — P0.0.7 already captures these fields,
   # now they're real instead of always-True placeholders.
   safe_emit_sync("vision_frame", VisionFramePayload(
       frame_id=_frame_id,
       frame_path=_frame_path,
       anti_spoof_live=_anti_spoof_live,
       anti_spoof_score=_anti_spoof_score,
       # ... other fields ...
   ))
   ```

2. **Primary vision loop** (around line 2558-2570 zone) — same shape. Every embedding-capture site that writes to TrackStore must include the verdict.

**Same-frame discipline assertion** (C0 contract enforced structurally): the `frame` variable passed to `verify_live` and the `_crop` variable passed to `embedder.embed` are derived from the same source frame. AST scan in Phase 4 asserts this property (see test list).

**Phase 2 deliverables (test surface):**
- 2 tests verifying the background vision loop calls verify_live at every embedding-capture point
- 2 tests verifying the atomic upsert (verdict and embedding together in TrackStore, no separate writes)
- 1 test verifying the three reason codes are emitted correctly (passed/rejected/unavailable)

### Phase 3 — Consumer + watchdog (≈0.5 day)

**Code changes:**

1. **`pipeline.py` progressive_enroll** (around line 7686-7693):
   ```python
   _face_captured = False
   _gate_track = _track_store.peek_track_for_stranger_pid(_cur_pid)
   if _gate_track is not None:
       _track_snap = _track_store.peek_snapshot(_gate_track)
       if _track_snap is not None and _track_snap.embedding is not None:
           _gate_emb = _track_snap.embedding
           # P0.S1 D9 + C1 — read verdict from co-temporal TrackEntry.
           _verdict = _track_snap.anti_spoof_live
           _reason = _track_snap.anti_spoof_reason or ANTI_SPOOF_REASON_NO_VERDICT

           if _verdict is True:
               # Face-witness path — verdict was True at embedding capture.
               if db.add_embedding(
                   _cur_pid, _gate_emb, "progressive_enroll",
                   anti_spoof_verdict=True,
               ):
                   print(f"[Pipeline] Progressive enroll: face embedding stored for {_cur_pid}")
                   _face_captured = True
           else:
               # Fail-closed reject — D9.a voice-only fallthrough.
               # Distinguish "unavailable" from "rejected" via _reason (C1).
               print(
                   f"[Pipeline] Anti-spoof: BLOCKED progressive_enroll for {_cur_pid} "
                   f"(track={_gate_track}, reason={_reason})"
               )
               _record_anti_spoof_rejection(
                   person_id=_cur_pid,
                   track_id=_gate_track,
                   reason=_reason,
               )
               # _face_captured stays False — voice-only branch downstream runs.
   ```

2. **`pipeline.py` new helper** `_record_anti_spoof_rejection`:
   ```python
   # Module-level state — per-track rejection log for burst detection (C2)
   _anti_spoof_rejection_log: dict[str, list[float]] = {}

   def _record_anti_spoof_rejection(*, person_id: str, track_id: str, reason: str) -> None:
       """Records an anti-spoof rejection for burst-threshold tracking.
       Always emits the per-instance dashboard event (D10.c).
       Fires a watchdog burst alert if ANTI_SPOOF_BURST_THRESHOLD is met within
       ANTI_SPOOF_BURST_WINDOW_SECS on this track (C2).
       """
       now = time.time()
       log = _anti_spoof_rejection_log.setdefault(track_id, [])
       log.append(now)
       cutoff = now - ANTI_SPOOF_BURST_WINDOW_SECS
       _anti_spoof_rejection_log[track_id] = [t for t in log if t >= cutoff]

       # D10.c — per-instance dashboard event (NOT TTS).
       # Persisted via watchdog_alerts table with severity="info" for individual rejections.
       if _brain_orchestrator is not None:
           _brain_orchestrator.report_anti_spoof_rejection(
               track_id=track_id,
               person_id=person_id,
               reason=reason,
               burst_count=len(_anti_spoof_rejection_log[track_id]),
               window_secs=ANTI_SPOOF_BURST_WINDOW_SECS,
           )

       # C2 — burst breach raises severity to "warning". Per-track only;
       # other tracks unaffected; voice channel unaffected.
       if len(_anti_spoof_rejection_log[track_id]) >= ANTI_SPOOF_BURST_THRESHOLD:
           if _brain_orchestrator is not None:
               _brain_orchestrator.report_anti_spoof_burst(
                   track_id=track_id,
                   person_id=person_id,
                   reason=reason,
                   count=len(_anti_spoof_rejection_log[track_id]),
                   window_secs=ANTI_SPOOF_BURST_WINDOW_SECS,
               )
   ```

3. **`core/brain_agent.py`** `WatchdogAgent` — two new methods:
   ```python
   def report_anti_spoof_rejection(
       self, *, track_id: str, person_id: str, reason: str,
       burst_count: int, window_secs: float,
   ) -> None:
       """Per-instance rejection event. Severity 'info'."""
       # Persist to watchdog_alerts with metadata
       # Fields per D10.c: timestamp, track_id, reason, burst_count
       # NOT the raw embedding, NOT the frame

   def report_anti_spoof_burst(
       self, *, track_id: str, person_id: str, reason: str,
       count: int, window_secs: float,
   ) -> None:
       """Burst breach event. Severity 'warning'. Same metadata + escalation flag."""
   ```

4. **`pipeline.py` `_close_session` and track-store stale-prune** must clear the per-track rejection log entry when the track is lost. Memory hygiene + the burst window resets when the attack scenario ends (attacker leaves frame, track id is freed).

5. **`reset_anti_spoof_rejection_log()`** helper for tests + factory reset.

**Phase 3 deliverables (test surface):**
- 3 behavioural tests for progressive_enroll gate (verdict True / False / None matrix)
- 2 tests for D9.a voice-only fallthrough (rejected verdict still opens session and grants bootstrap credits; just no face embedding)
- 1 test for C1 reason codes distinguishability (unavailable vs rejected dashboard payloads differ)
- 1 test for C2 watchdog burst (3 rejections / 60s / per-track triggers warning-severity alert; 4th rejection does not double-fire)
- 1 test for C2 per-track blast radius (rejections on track_A do not trigger burst on track_B)
- 1 test for `_close_session` clearing the per-track rejection log

### Phase 4 — Structural invariants + tripwire (≈0.25 day)

**Code changes:**

1. **`tests/test_p0_s1_anti_spoof_invariants.py`** — new file. Six tests:

   ```python
   def test_allowed_sources_frozenset_matches_protected_sources(): ...
   def test_no_legacy_unknown_in_production_call_sites(): ...
   def test_every_protected_source_add_embedding_passes_verdict(): ...
   def test_every_protected_source_call_site_has_upstream_verify_live(): ...
   def test_track_store_upsert_uses_atomic_verdict_embedding_path(): ...
   def test_same_frame_discipline_in_background_vision_loop(): ...
   ```

2. **`tests/test_p0_s1_tripwire.py`** — D9 tripwire (auditor refinement). Three tests:

   ```python
   def test_rejected_verdict_does_not_route_through_alternate_path():
       """The D9 deferral surface is 'vision-channel enrollment blocked'.
       This tripwire fails if anything in the rejection path persists
       a face embedding via a non-vision side path."""

   def test_voice_only_fallthrough_does_not_promote_face(): ...
   def test_burst_alert_does_not_promote_or_unblock_track(): ...
   ```

3. **`tests/test_p0_s1_replay.py`** — replay smoke tests (D7). Five tests:

   ```python
   def test_progressive_enroll_replay_with_anti_spoof_True(): ...
   def test_progressive_enroll_replay_with_anti_spoof_False(): ...
   def test_progressive_enroll_replay_with_anti_spoof_None(): ...
   def test_replay_carries_distinct_reason_codes(): ...
   def test_burst_fixture_simulates_three_rejections_within_60s(): ...
   ```

4. **`tests/fixtures/event_log_fixtures.py`** — extend `build_stranger_first_encounter` per D7:

   ```python
   def build_stranger_first_encounter(
       session_id: str,
       *,
       pid_hint: str = "stranger_xyz",
       anti_spoof_live: Optional[bool] = True,  # P0.S1 D7 — parameter for the matrix
       ...
   ) -> List[int]:
       ...
       # vision_frame events emitted with the parameterized verdict
   ```

5. **`pipeline.py`** — induction-protocol deliberate-regression check at closure time (per the induction-surfaces-invariant-gaps discipline). Three checks confirmed:
   - Inject a code path that calls `add_embedding(source="progressive_enroll")` without `anti_spoof_verdict=...` → AST test must fire.
   - Inject a code path that reads embedding from track without reading verdict → tripwire test must fire.
   - Inject `verify_live` call against a different frame variable from the one embedder.embed used → same-frame discipline test must fire.

**Phase 4 deliverables (test surface):**
- 6 AST structural invariants
- 3 tripwire tests (D9 deferral surface)
- 5 replay smoke tests (D7 matrix)
- 3 deliberate-regression checks (induction protocol, confirmed at closure)

---

## 4. Test plan summary

Total: **~28 new tests** across the four phases.

| Phase | Tests | Type |
|---|---|---|
| Phase 1 | 9 | 5 TrackStore behavioural + 1 frozenset invariant + 3 add_embedding catch-all |
| Phase 2 | 5 | 2 vision-loop integration + 2 atomic upsert + 1 reason code |
| Phase 3 | 8 | 3 progressive_enroll matrix + 2 voice-only fallthrough + 1 reason distinguishability + 1 burst + 1 per-track scope + 1 cleanup |
| Phase 4 | 14 | 6 AST invariants + 3 tripwires + 5 replay smoke + 3 deliberate-regression confirmations |

Plus updates to ~5 pre-existing tests (`test_pipeline.py` progressive_enroll tests must now pass the verdict kwarg; the existing `recognition_update` tests also need the verdict kwarg added to their `add_embedding` calls under D1 hybrid).

Net suite growth: roughly **+30 tests** for P0.S1 (2,215 → ~2,245 baseline, assuming P0.0.7 closure stays at 2,215).

---

## 5. Validation runbook stub

Full runbook lands as `tests/p0_s1_validation_runbook.md` during code phase. Plan v1 commits to the following sections:

- **5.1 Test environment** — anti-spoof model loaded, MiniFASNet ensemble live, dashboard running, watchdog alerts log path captured.
- **5.2 Attack matrix** — three attack types, each canary'd:
  - **Photo (printed)** — Jagan holds an 8x10 printed photo of his own face in front of the camera, says "Hey Kara" with audio replay.
  - **Screen replay (phone display)** — Jagan holds a phone showing a still image of his face, says "Hey Kara."
  - **Video replay** — Jagan plays a recording of his face (eyes moving, head turning) on a tablet, says "Hey Kara."
- **5.3 Expected outcomes per attack** — gate fires, dashboard logs rejection with correct reason code, voice-only session opens, face gallery is NOT populated for this attack attempt, watchdog burst alert fires if ≥3 rapid attempts on the same track.
- **5.4 Negative control** — Jagan engages normally (live face, says "Hey Kara"). Gate passes, face embedding stored, dashboard shows `[Anti-Spoof] PASSED` event.
- **5.5 Gate criteria for closure** — all three attack types reject correctly across 3 independent canary sessions, reason codes match expectations, burst alert fires within window when reproduced, normal engagement still passes.

---

## 6. Open items / risks

1. **`AntiSpoofChecker.last_score` attribute** — Plan v1 assumes the checker exposes the last MiniFASNet `live_prob` for logging. Need to verify the attribute exists or add it as a small extension to `core/vision.py` in Phase 1. Estimated +10 minutes if needed.

2. **TrackStore lock contention** — the producer side (background vision loop) writes verdict + embedding atomically under the TrackStore lock. The consumer side (progressive_enroll) reads via `peek_snapshot` which is lock-free per the single-thread-asyncio safety contract (Part XL §268). No contention expected, but the test surface includes a stress test (Phase 1 #5) confirming the upsert is observably atomic.

3. **Empty track at gate time** — if the gate fires before the background vision loop has had a chance to populate the track with embedding+verdict, `peek_anti_spoof_verdict` returns `None` and the verdict path is `(None, ANTI_SPOOF_REASON_NO_VERDICT)`. This routes through the rejection path (D9.a voice-only fallthrough), which is the correct fail-closed behavior. Test surface includes this case explicitly.

4. **Multi-track sessions** — if a single stranger has multiple SORT tracks during their engagement window (track id flipped due to face-detection gap), only the track currently bound to the pid via `_track_store.peek_track_for_stranger_pid` is queried. Other tracks for the same physical person are not consulted. This is acceptable because the binding logic upstream already picks the best track; if the picked track has a False verdict, we fail closed even though some other track might have True. Conservative is correct here.

5. **Anti-spoof score logging** — when `_anti_spoof_score` is None (model unavailable), the dashboard payload distinguishes via reason code. When `_anti_spoof_score` is present (model ran), it's included for debugging. No PII concern — the score is a float between 0 and 1.

---

## 7. Estimated effort

**1.5-2 days focused work**, per auditor's revised calibration:

- Phase 1: ≈0.5 day (TrackStore extension + config + catch-all + doc-grep)
- Phase 2: ≈0.5 day (producer integration in background vision loop)
- Phase 3: ≈0.5 day (consumer + watchdog burst + brain orchestrator hooks)
- Phase 4: ≈0.25 day (AST invariants + tripwire + replay extensions)

Plus closure work (induction-regression confirmation + closure report) ≈ 0.25 day.

**Live canary validation:** separate session post-merge, ≈ 0.5 day for the three-attack-type canary.

---

## 8. Discipline-count clarifications

Per the auditor's prior note, no count bumps until closure. Holding at:

- Spec-first review cycle: **6-for-6** (P0.S1 earns 7th on closure)
- Developer-improves-on-spec: **5-for-5** (no bumps until any v1→v2 deviation gets banked)
- Sub-pattern A (Phase 0 audit caught wrong premise): **2 instances** (P0.10 + P0.S1). Tracked as observation worth watching in CLAUDE.md.
- Tripwires-must-match-deferral-surface: **3-for-3** (D9's tripwire requirement is the 4th if it lands cleanly; bumps to 4-for-4 on P0.S1 closure if so).
- Induction-surfaces-invariant-gaps: **7-for-7** (Phase 4 deliberate-regression checks are the protocol; counts depend on whether they surface a gap mid-flight).

---

## 9. Next steps

1. **Auditor review of this Plan v1** — expected: precision items on the Phase boundaries, the AST scan shapes, the watchdog burst implementation, the D9 tripwire enumeration, the validation runbook detail.
2. **Plan v2 incorporating precision items** (if any).
3. **Joint sign-off** → code phase starts.
4. **Phase-by-phase implementation** with full-suite verification between phases (per the verification-before-completion lesson banked in P0.0.7 Step 5 polish).
5. **Closure report** with deliberate-regression confirmations + discipline-count updates.
6. **Live canary validation session** following the runbook.
7. **P0.S1 closure** unlocks the next item in the locked sequence — review whether P0.S6 (secrets management) or P0.S5 (dashboard CSRF) comes next.

---

## 10. Reference documents

- `tests/p0_s1_audit.md` — Phase 0 audit (premise reset + D1-D10 surfaced)
- `core/db.py:34, 574` — VALID_EMBEDDING_SOURCES + add_embedding entry point
- `core/track_store.py` — TrackStore (P0.6 Store-pattern base)
- `core/vision.py::verify_live` — canonical anti-spoof wrapper (Session 46 Finding D)
- `core/vision.py::AntiSpoofChecker` — MiniFASNet ensemble (Session 52)
- `pipeline.py:6466-6482` — reference gate shape (recognition_update)
- `pipeline.py:7670-7720` — progressive_enroll gap site + voice-only fallthrough path
- `core/event_log/types.py::VisionFramePayload` — already carries `anti_spoof_live` + `anti_spoof_score` (P0.0.7 load-bearing)
- `tests/fixtures/event_log_fixtures.py::build_stranger_first_encounter` — replay scaffold for D7 matrix
- `everything_about_system.md` Part XXIV (Anti-Spoofing) + Part XXXVIII (Atomicity) + Part L (Disciplines)
