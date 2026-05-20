# P0.S1 — Anti-Spoof on Every Face Match — Plan v2

**Date:** 2026-05-18
**Author:** architect
**Status:** Plan v2. Drafted against locked D1-D10 + contract clauses C0-C3 (from Phase-0 audit + Plan v1 lock) AND auditor's 9-item precision pass on Plan v1. Plan v1 retained at `tests/p0_s1_plan_v1.md` for delta visibility.

**Delta from Plan v1:**
- **HIGH 1** — Same-frame structural test pulled forward from Phase 4 → Phase 2 (closes the unenforced gap between Phase 2 closure and Phase 4 closure).
- **HIGH 2** — Three AST scan shapes explicitly specified (upstream-verify_live, same-frame discipline, non-literal source handling).
- **HIGH 3** — Enrollment-flow migration enumerated. ALL 5 protected-source call sites surveyed with verdict-source per site. Phase 1 deliverables expanded.
- **MED 4** — D9 tripwire suite extended: `test_recognition_update_with_rejected_verdict_blocked_by_catch_all`.
- **MED 5** — `_anti_spoof_rejection_log` becomes `AntiSpoofRejectionStore` (`core/anti_spoof_rejection_store.py`) per P0.6 Store-pattern discipline; legacy-global-progress ratchet preserved at cap=0.
- **MED 6** — TrackStore concurrency stress test enumerated in Phase 1.
- **LOW 7** — Test count reconciled (math below).
- **LOW 8** — Validation runbook "independent canary session" criteria specified.
- **LOW 9** — Primary vision loop code shape shown explicitly (two scan paths: ambient + secondary).

Locked D-decisions and C-contract clauses unchanged.

---

## 1. Locked decision reference (unchanged from Plan v1)

| ID | Locked at |
|---|---|
| D1 Gate placement | Hybrid (per-call-site + add_embedding catch-all) |
| D2 Frame source | D2.b TrackStore carries verdict |
| D2.b.i Frequency | Every embedding-capture, same frame |
| D3 Failure handling | Fail-closed reject + watchdog burst |
| D4 legacy_unknown | Delete (pending doc-grep verification) |
| D5 Invariant shape | Source-list frozenset + forward AST scan |
| D6 Throttling | None |
| D7 Replay fixtures | Parameterize with `anti_spoof_live: bool | None` |
| D8 Validation gate | Live canary multi-attack-type |
| D9 Session disposition | Voice-only fallthrough + tripwire |
| D10 User-facing | Dashboard yes, TTS no |
| C0 Same-frame discipline | Atomic upsert; no cross-frame verdict caching |
| C1 Reason code distinguishability | 4 codes: passed/rejected/unavailable/no_verdict |
| C2 Burst threshold | 3/60s/per-track; no cross-track lockout; no voice lockout |
| C3 Pre-existing poisoned galleries | P0.S1.X backlog |

---

## 2. Complete add_embedding call-site enumeration (HIGH 3 — Plan v1 gap)

Plan v1 enumerated the gap (progressive_enroll) but didn't specify how *existing* protected-source call sites migrate to satisfy the catch-all. Without the migration, Phase 1's catch-all blocks enrollment entirely.

**All 5 production call sites of `add_embedding(... source=<protected>, ...)`:**

| # | Site | Source | Existing upstream gate | Verdict-source in P0.S1 |
|---|---|---|---|---|
| 1 | `pipeline.py:3367` (first_boot_flow) | `enrollment` | `verify_live` at line 3351 | Capture verdict in local var; pass `anti_spoof_verdict=_verdict` |
| 2 | `pipeline.py:3440` (enrollment_flow) | `enrollment` | `verify_live` at line 3421 | Same pattern as #1 |
| 3 | `enroll.py:95` (CLI enrollment) | `enrollment` | `verify_live` at line 74 | Same pattern as #1 |
| 4 | `pipeline.py:6479` (recognition_update) | `recognition_update` | `_anti_spoof_ok` computed at 6469-6473 (already a verdict var) | Pass `anti_spoof_verdict=_anti_spoof_ok` |
| 5 | `pipeline.py:7690` (progressive_enroll) | `progressive_enroll` | **NONE** — THE GAP | Read verdict from `_track_store.peek_snapshot(gate_track).anti_spoof_live` |

Phase 1 ships the catch-all + the migration of sites 1-4 in the same commit; Phase 1 closure verifies all 5 sites pass through the gate. Phase 3 then closes the gap at site 5.

**Migration pattern for sites 1-3 (enrollment paths):**

```python
# Pre-P0.S1 (pipeline.py:3351-3367 zone):
if not verify_live(frame, det.bbox, _anti_spoof_checker):
    # rejection handling ...
    continue
emb = embedder.embed(crop)
db.add_embedding(person_id, emb, "enrollment")

# Post-P0.S1:
_verdict = verify_live(frame, det.bbox, _anti_spoof_checker)
if not _verdict:
    # rejection handling ...
    continue
emb = embedder.embed(crop)
db.add_embedding(person_id, emb, "enrollment", anti_spoof_verdict=_verdict)
```

The verdict is a `bool` (verify_live returns bool, never None) — passes the catch-all's `verdict is True` check.

**Migration pattern for site 4 (recognition_update):**

```python
# Pre-P0.S1 (pipeline.py:6469-6479):
_anti_spoof_ok = (
    _anti_spoof_checker is not None
    and getattr(_anti_spoof_checker, "available", False)
    and verify_live(frame, det.bbox, _anti_spoof_checker)
)
if not _anti_spoof_ok:
    await _conversation_store.touch_self_update(person_id, time.time())
else:
    added = db.add_embedding(person_id, embedding, "recognition_update", conf)

# Post-P0.S1:
_anti_spoof_ok = (
    _anti_spoof_checker is not None
    and getattr(_anti_spoof_checker, "available", False)
    and verify_live(frame, det.bbox, _anti_spoof_checker)
)
if not _anti_spoof_ok:
    await _conversation_store.touch_self_update(person_id, time.time())
else:
    added = db.add_embedding(
        person_id, embedding, "recognition_update", conf,
        anti_spoof_verdict=_anti_spoof_ok,  # bool True at this point
    )
```

Trivial change — `_anti_spoof_ok` was already computed and trusted; the kwarg threads it through.

---

## 3. AST scan shape specifications (HIGH 2)

Three Plan v1 AST tests had underspecified shapes. Plan v2 locks them.

### 3.1 `test_every_protected_source_call_site_has_upstream_verify_live`

**Definition of "upstream":** `verify_live(...)` must appear as a `Call` node in the same function body (innermost enclosing `ast.FunctionDef` or `ast.AsyncFunctionDef`) AND at a strictly lower line number than the `add_embedding(...)` call within that function. Cross-function "upstream" (e.g. caller threading verdict in via parameter) is NOT accepted by the AST scan; those cases must be handled by the catch-all alone (with `# noqa: P0S1-allow-cross-function-verdict` annotation if explicitly desired).

**Algorithm:**
1. Parse `pipeline.py` and `enroll.py` to AST.
2. For each `Call` node where `func.attr == "add_embedding"` AND first/second/third positional or keyword `source` arg resolves to a literal string in `ALLOWED_EMBEDDING_SOURCES_REQUIRING_ANTI_SPOOF`:
   a. Walk up the AST to find the enclosing `FunctionDef` / `AsyncFunctionDef`.
   b. Within that function body, search for `Call` nodes where `func.id == "verify_live"` OR `func.attr == "verify_live"`.
   c. Assert at least one such call exists AND its line number < add_embedding's line number.
3. If the source arg is non-literal (Name, Attribute, expression): flag for review per §3.3.

**Edge cases handled explicitly:**
- `_anti_spoof_ok = (... and verify_live(...))` — the `verify_live` is inside a parenthesized boolean expression; ast.walk still finds the Call node. ✓
- `if verify_live(...): db.add_embedding(...)` — verify_live in test expression of If; still ast.walk-findable. ✓
- `verify_live` inside lambda/nested function — only counted if it's in the SAME `FunctionDef` body as the add_embedding (not a nested closure). The walk is depth-bounded to the immediate function body.

### 3.2 `test_same_frame_discipline_in_background_vision_loop`

**Definition of "same frame":** within the scan-loop body of `_background_vision_loop`, the variable consumed as the first positional arg to `verify_live(<frame>, <bbox>, <checker>)` MUST be the same `Name.id` as the value-side of the slicing expression that produced the crop fed to `embedder.embed(<crop>)`. Formally:

- Find the `Call` node `verify_live(name_v, ...)`.
- Find the nearest preceding `Call` node `embedder.embed(name_c)` (the embedding-producer).
- Find the assignment `name_c = name_f[<slice>]` (the crop's slice base).
- Assert `name_v == name_f`.

**Allowlisted producer functions** (per the `_ANTI_SPOOF_PRODUCER_FUNCTIONS` frozenset):

```python
_ANTI_SPOOF_PRODUCER_FUNCTIONS: frozenset[str] = frozenset({
    "_background_vision_loop",     # ambient + secondary scan path
})
```

Only these functions are scanned for the same-frame discipline. Other functions calling verify_live (greeting path, scene logging) don't need to satisfy it because they don't produce embeddings.

**Implementation note:** the scan uses local-variable provenance (find the `Assign` node whose target.id == `name_c`, check the value's structure). If the variable provenance is too indirect (e.g. crop passed through 2+ intermediate variables), the test fails with an informative message asking the developer to either (a) refactor to direct assignment, or (b) annotate with `# P0S1-C0: same-frame verified manually — <rationale>`. The annotation accepts the case but logs to a registry for future review.

**Fallback if AST scan is intractable:** marker-comment-based check. Production code carries `# P0S1-C0:` markers; the scan finds the marker and asserts the verify_live + embedder.embed calls in the next K lines pass through the same frame variable. Less elegant but unambiguous. Plan v2 favors the AST graph approach with this as a documented fallback.

### 3.3 `test_every_protected_source_add_embedding_passes_verdict`

**Handling of non-literal source args:**

- If `source` arg is `ast.Constant(value=str)` in `ALLOWED_EMBEDDING_SOURCES_REQUIRING_ANTI_SPOOF`: assert `anti_spoof_verdict` kwarg is present, AND its value is either `ast.Constant(value=True)` OR an `ast.Name` whose nearest preceding assignment is from `verify_live(...)` or `_anti_spoof_ok` or `_verdict` (a small allowlist of "verdict-source-name patterns").
- If `source` arg is non-literal (`ast.Name`, `ast.Attribute`, expression): **flag for review** — the test fails with message:
  ```
  Non-literal source arg at <file>:<line>. Cannot statically determine whether the call
  uses a protected source. Either:
  (1) literalize the source arg, OR
  (2) add `# noqa: P0S1-allow-non-literal-source: <rationale>` to explicitly opt out
      of the static check. The runtime catch-all in add_embedding will still enforce
      the verdict requirement at call time.
  ```
- Test ships with a registry of allowed non-literal sites (empty in Plan v2; populated only when a real case arises).

Rationale: the AST scan is compile-time defense; the runtime catch-all is the safety net. Non-literal sources opt out of compile-time but stay protected by runtime. Both layers are independently enforceable.

---

## 4. Module-level state → `AntiSpoofRejectionStore` (MED 5)

Plan v1's `_anti_spoof_rejection_log: dict[str, list[float]]` at module scope in `pipeline.py` would trigger the P0.6 legacy-global-progress ratchet (cap=0). Plan v2 promotes to a `Store` subclass.

**New file: `core/anti_spoof_rejection_store.py`**

```python
import time
from collections import defaultdict
from typing import Optional
import asyncio

from core.store_base import Store


class AntiSpoofRejectionStore(Store[dict[str, list[float]]]):
    """Per-track anti-spoof rejection log for burst-threshold detection.

    Tracks rejection timestamps per SORT track_id with prune-on-write
    against the burst window. Used by P0.S1 watchdog burst alert (C2).

    Single-thread-asyncio safety contract: peek_count is sync (no lock);
    record_rejection is async (acquires lock). Reset clears all tracks.
    Per-track scope (NOT per-pid) because pid does not exist yet at
    progressive_enroll gate time.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._log: dict[str, list[float]] = {}

    async def record_rejection(
        self, track_id: str, now: float, window_secs: float
    ) -> int:
        """Append a rejection at `now`; prune entries older than now-window_secs.
        Returns the post-prune count for this track."""
        async with self._lock:
            entries = self._log.setdefault(track_id, [])
            entries.append(now)
            cutoff = now - window_secs
            self._log[track_id] = [t for t in entries if t >= cutoff]
            return len(self._log[track_id])

    def peek_count(self, track_id: str, now: float, window_secs: float) -> int:
        """Sync read of current rejection count in window.
        No lock — single-thread-asyncio safety per P0.6 contract."""
        entries = self._log.get(track_id, [])
        cutoff = now - window_secs
        return sum(1 for t in entries if t >= cutoff)

    async def pop(self, track_id: str) -> None:
        """Remove a track's rejection history. Called on track stale-prune
        and on session close."""
        async with self._lock:
            self._log.pop(track_id, None)

    def reset(self) -> None:
        """Required by Store ABC. Clear all rejection history.
        Called by autouse fixture between tests + factory reset."""
        self._log.clear()
```

**Module-level singleton in `pipeline.py`:**

```python
# Replacement for Plan v1's _anti_spoof_rejection_log module-level dict.
# P0.S1 MED 5 — Store pattern preserves P0.6 ratchet at cap=0.
from core.anti_spoof_rejection_store import AntiSpoofRejectionStore
_anti_spoof_rejection_store = AntiSpoofRejectionStore()
```

**Autouse fixture entries** in `conftest.py` (root) AND `tests/conftest.py`:

```python
# Existing autouse loop:
_anti_spoof_rejection_store.reset()  # P0.S1 MED 5
```

**M2 coverage meta-test update:** the P0.6.6 meta-test `test_p06_store_invariants.py::test_autouse_fixture_resets_all_stores` validates that both conftest files reset all stores. Adding `_anti_spoof_rejection_store` to the loop is checked by this test on next run.

**`_STORE_MODULES` extension** in `test_p06_store_invariants.py`:

```python
_STORE_MODULES = (
    # ... existing entries ...
    ("anti_spoof_rejection_store", "AntiSpoofRejectionStore"),
)
```

**Phase 1 deliverable count update:** AntiSpoofRejectionStore adds 5 store-unit tests (init/record/peek/pop/reset round-trip + concurrency stress + sync peek under writer pressure).

---

## 5. Same-frame test pulled into Phase 2 (HIGH 1)

`test_same_frame_discipline_in_background_vision_loop` moves from Phase 4 → Phase 2. Phase 2's deliverable list now includes the structural test alongside the behavioral integration tests. This means Phase 2 closure structurally proves C0; Phase 4 keeps the broader AST invariant suite.

**Phase 2 updated deliverable list:**

1. Background-vision-loop behavioral test — `verify_live` called at every embedding-capture point (2 tests, 1 each for the ambient-listen path and the secondary-scan path).
2. Atomic upsert observability — verdict+embedding visible together in TrackEntry, never apart (1 behavioral + 1 concurrency stress).
3. Three reason codes emitted correctly per scenario (passed/rejected/unavailable) — 1 test.
4. **NEW (HIGH 1)** — `test_same_frame_discipline_in_background_vision_loop` AST scan with the §3.2 shape spec. Asserts the C0 contract structurally before Phase 4.

Phase 4 retains the broader invariant suite (the catch-all + cross-call-site + non-literal-source scans) but no longer carries the same-frame test alone.

---

## 6. D9 tripwire suite extension (MED 4)

Plan v1's tripwire enumeration covered voice-only fallthrough and burst-alert paths. Plan v2 adds:

```python
def test_recognition_update_with_rejected_verdict_blocked_by_catch_all():
    """The recognition_update path is gated explicitly at its call site
    (pipeline.py:6469-6482). The D9 tripwire enumeration is incomplete
    without verifying that the add_embedding catch-all ALSO blocks
    recognition_update when the explicit gate is bypassed.

    This test directly calls FaceDB.add_embedding(person_id, emb,
    "recognition_update", confidence=0.5, anti_spoof_verdict=False) and
    asserts the catch-all returns False with the correct log message.

    Strictly belt-and-braces: the call site has the explicit gate, this
    test verifies the structural backstop also fires.
    """
```

Plan v2 tripwire suite: 4 tests (was 3 in Plan v1) — voice-only fallthrough, recognition_update catch-all, burst-alert dispatch, recognition_update verdict-None path.

---

## 7. TrackStore concurrency stress test (MED 6)

Phase 1 deliverable expansion. Pattern matches P0.6.4 VoiceGalleryStore stress test (1 writer + 1000 readers).

```python
async def test_track_store_upsert_with_verdict_is_atomically_observable():
    """Phase 1 #6 — under concurrent producer + consumer load, peek_snapshot
    never returns a TrackEntry where anti_spoof_live is set but embedding is None,
    OR embedding is set but anti_spoof_live is None.

    Pattern: 1 writer task issues upsert_embedding_with_verdict every 1ms for 100ms;
    50 reader tasks call peek_snapshot in tight loop. Aggregate all snapshots
    observed; assert zero torn states.

    Validates the C0 atomicity contract structurally rather than relying on
    'no contention expected' assumption.
    """
```

---

## 8. Primary vision loop sampling — code shape (LOW 9)

Plan v1 said "Primary vision loop (around line 2558-2570 zone) — same shape." Plan v2 shows the explicit shape for both paths.

There are TWO scan paths inside `_background_vision_loop` that produce face embeddings landing in `_track_store`:

### 8.1 Ambient-listen path (around line 2540-2570)

Fires during WATCHING state when no active session is open. Looking for face recognition to trigger ambient wake.

```python
# Pre-P0.S1:
_raw_emb = await loop.run_in_executor(None, embedder.embed, _crop)
_emb = temporal_buffer.add_and_pool(_det.bbox, _raw_emb, track_id=_det.track_id)
# ... db.recognize ...

# Post-P0.S1:
_raw_emb = await loop.run_in_executor(None, embedder.embed, _crop)
_emb = temporal_buffer.add_and_pool(_det.bbox, _raw_emb, track_id=_det.track_id)

# C0 same-frame discipline — verify_live on the SAME `frame` variable
# from which _crop = frame[bbox] was sliced.
_anti_spoof_live = verify_live(frame, _det.bbox, _anti_spoof_checker)
_anti_spoof_score = None
if _anti_spoof_checker is None or not getattr(_anti_spoof_checker, "available", False):
    _anti_spoof_reason = ANTI_SPOOF_REASON_UNAVAILABLE
    _anti_spoof_live = None  # None semantic — distinguish from False
elif _anti_spoof_live:
    _anti_spoof_reason = ANTI_SPOOF_REASON_PASSED
    _anti_spoof_score = getattr(_anti_spoof_checker, "last_score", None)
else:
    _anti_spoof_reason = ANTI_SPOOF_REASON_REJECTED
    _anti_spoof_score = getattr(_anti_spoof_checker, "last_score", None)

# Atomic upsert — verdict + embedding together.
await _track_store.upsert_embedding_with_verdict(
    track_id=_det.track_id,
    embedding=_emb,
    anti_spoof_live=_anti_spoof_live,
    anti_spoof_score=_anti_spoof_score,
    anti_spoof_reason=_anti_spoof_reason,
    captured_at=_bv_scan_now,
    bbox=_det.bbox,
)

# Event-log emission (H2 vision_frame) — P0.0.7 H2 already captures these.
safe_emit_sync("vision_frame", VisionFramePayload(
    frame_id=_frame_id,
    frame_path=_frame_path,
    anti_spoof_live=_anti_spoof_live,
    anti_spoof_score=_anti_spoof_score,
    # ... other fields ...
))
```

### 8.2 Secondary-scan path (around line 2580-2620)

Fires during active conversation. Resolves face identities for the brain's scene block.

```python
# Same shape as 8.1, applied at the corresponding embedder.embed call site
# inside the secondary-scan if-branch (`if not _should_run_recognition(...): continue`
# guard followed by embedding capture).
_raw_emb2 = await loop.run_in_executor(None, embedder.embed, _crop)
_emb2 = temporal_buffer.add_and_pool(_det.bbox, _raw_emb2, track_id=_det.track_id)

# C0 same-frame — frame variable is the SAME as the one feeding the recognition call.
_anti_spoof_live = verify_live(frame, _det.bbox, _anti_spoof_checker)
# ... same classification + reason code logic as 8.1 ...

await _track_store.upsert_embedding_with_verdict(
    track_id=_det.track_id,
    embedding=_emb2,
    anti_spoof_live=_anti_spoof_live,
    anti_spoof_score=_anti_spoof_score,
    anti_spoof_reason=_anti_spoof_reason,
    captured_at=_bv_scan_now,
    bbox=_det.bbox,
)
```

Both paths share a helper to reduce duplication:

```python
def _classify_anti_spoof_verdict(
    frame: np.ndarray, bbox: tuple[int, int, int, int],
    checker: "AntiSpoofChecker | None",
) -> tuple[Optional[bool], Optional[float], str]:
    """Classify a verify_live result into (live, score, reason). Single source of
    truth for the four-reason-code mapping (C1). Called from both ambient-listen
    and secondary-scan paths in _background_vision_loop.

    Pure function — no module state, no I/O beyond verify_live's own model call.
    """
    if checker is None or not getattr(checker, "available", False):
        return (None, None, ANTI_SPOOF_REASON_UNAVAILABLE)
    live = verify_live(frame, bbox, checker)
    score = getattr(checker, "last_score", None)
    if live:
        return (True, score, ANTI_SPOOF_REASON_PASSED)
    return (False, score, ANTI_SPOOF_REASON_REJECTED)
```

Lives in `pipeline.py` next to the existing anti-spoof helpers. Same-frame discipline preserved because the helper takes the `frame` arg explicitly — the caller passes the same `frame` they already pass to `embedder.embed` via the `_crop = frame[bbox]` derivation.

---

## 9. Validation runbook closure-gate criteria (LOW 8)

"Three independent canary sessions" definition for `tests/p0_s1_validation_runbook.md`:

A canary session is **independent** of another canary session when ALL FOUR of the following hold:

1. **Process restart.** The pipeline process is fully terminated between sessions (no warm state, no in-memory caches). Re-launch fresh.
2. **Minimum wall-clock gap.** At least 30 minutes between session-end-of-prior and session-start-of-next.
3. **Lighting condition variation.** No two of the three sessions use the same lighting. Acceptable variation: daylight overhead, evening warm artificial, morning natural light through window, dim ambient + lamp, etc. The variation tests anti-spoof robustness across realistic conditions; the gate must reject attacks under each.
4. **Attack-artifact regeneration.** Photos are reprinted (or different print used), screen-replay images are re-captured on the attacker's phone (or different image used), video replay sources are re-recorded. The gate must reject attacks against fresh artifacts, not the same artifact 3× (which could pass if the system cached a "saw this artifact already" verdict — unlikely given the architecture but the runbook controls for it).

Closure gate: all three attack types reject correctly across all three independent sessions = 9 successful rejections + correct reason codes + correct burst-alert behavior under deliberate burst reproduction (deliberately do 3+ attack attempts in <60s during one canary session, verify burst alert fires).

Plus negative control: live engagement passes in all three sessions (3 successful enrollments via live face).

Anything less than 9 successful rejections + 3 successful negative-control passes = closure blocked; investigate before retrying.

---

## 10. Test count reconciliation (LOW 7)

Plan v1's math was off in two places (Phase 3 bullets summed to 9 not 8, and Phase 4's same-frame test was double-counted in some readings). Plan v2 reconciles:

| Phase | New tests | Detail |
|---|---|---|
| **Phase 1** | **17** | 5 TrackStore behavioral (extension, upsert, peek, pop, reset) + 1 frozenset invariant + 3 add_embedding catch-all (verdict True / False / None) + 3 enrollment-site migration verification + 1 TrackStore concurrency stress (MED 6) + 5 AntiSpoofRejectionStore (init/record/peek/pop/reset + concurrency, MED 5) — minus 1 if we collapse AntiSpoofRejectionStore tests into a single file with 4 not 5 tests, accept 4 |
| **Phase 2** | **6** | 2 vision-loop integration (ambient + secondary) + 1 atomic-upsert behavioral + 1 atomic-upsert concurrency stress + 1 reason-code matrix (passed/rejected/unavailable) + 1 same-frame AST (HIGH 1 — pulled forward from Phase 4) |
| **Phase 3** | **9** | 3 progressive_enroll matrix (verdict True/False/None) + 2 voice-only fallthrough (session opens + bootstrap granted) + 1 reason-code distinguishability dashboard payload + 1 burst threshold (3-in-60s triggers warning) + 1 per-track scope (track_A burst does not affect track_B) + 1 cleanup (close_session pops from rejection store) |
| **Phase 4** | **14** | 5 AST invariants (ALLOWED set / no-legacy / verdict-passed / upstream-verify_live / non-literal-source-flag) + 4 D9 tripwires (voice-only fallthrough, recognition_update catch-all (MED 4), burst-alert dispatch, recognition_update verdict-None) + 5 replay smoke (verdict True/False/None matrix + distinct reason codes + burst fixture) + 0 deliberate-regression confirmations (those run at closure, not as pytest cases) |

**Total new tests: 17 + 6 + 9 + 14 = 46.**

Plus 5 pre-existing tests updated (the three enrollment-site tests now assert `anti_spoof_verdict=` kwarg present; the recognition_update tests similarly).

**Net suite growth ~+46 tests** (2,215 + 46 = ~2,261 post-P0.S1).

---

## 11. Phase deliverables — Plan v2 final

### Phase 1 — Foundation (≈0.5-0.75 day)

**Code:**
- Pre-step: D4 doc-grep verification (no production callers, no planned use of `legacy_unknown`).
- `core/db.py` — `VALID_EMBEDDING_SOURCES` (drop `legacy_unknown` if grep is clean) + `ALLOWED_EMBEDDING_SOURCES_REQUIRING_ANTI_SPOOF` + `add_embedding` catch-all.
- `core/config.py` — `ANTI_SPOOF_BURST_THRESHOLD`, `ANTI_SPOOF_BURST_WINDOW_SECS`, `ANTI_SPOOF_REASON_*` constants.
- `core/track_store.py` — TrackEntry extension + `upsert_embedding_with_verdict` + `peek_anti_spoof_verdict`.
- `core/anti_spoof_rejection_store.py` — new Store subclass (MED 5).
- Conftest autouse loop extensions (root + tests/conftest.py).
- `pipeline.py` enrollment-site migrations (sites 1-4 from §2) + `_anti_spoof_rejection_store` singleton.

**Tests:** 17 new + 5 updated. Phase 1 closure: full pytest-green.

### Phase 2 — Producer (≈0.5 day)

**Code:**
- `pipeline.py` `_background_vision_loop` — both scan paths (§8.1 + §8.2) wired with `_classify_anti_spoof_verdict` helper + atomic `upsert_embedding_with_verdict` + event-log emission with real verdict fields.

**Tests:** 6 new (incl. same-frame AST pulled from Phase 4 per HIGH 1). Phase 2 closure: full pytest-green AND structural proof of C0.

### Phase 3 — Consumer + watchdog (≈0.5 day)

**Code:**
- `pipeline.py` progressive_enroll (around line 7686-7693) — `peek_anti_spoof_verdict` read + verdict-True branch (face-captured) + verdict-False/None branch (voice-only fallthrough + `_record_anti_spoof_rejection` call).
- `pipeline.py` `_record_anti_spoof_rejection` helper using `_anti_spoof_rejection_store`.
- `core/brain_agent.py` `WatchdogAgent.report_anti_spoof_rejection` + `report_anti_spoof_burst` methods.
- `_close_session` + track-store stale-prune both call `_anti_spoof_rejection_store.pop(track_id)`.

**Tests:** 9 new. Phase 3 closure: full pytest-green.

### Phase 4 — Invariants + tripwire (≈0.25-0.5 day)

**Code:**
- `tests/test_p0_s1_anti_spoof_invariants.py` — 5 AST invariants (per §3 shape specs).
- `tests/test_p0_s1_tripwire.py` — 4 D9 tripwires (incl. MED 4 recognition_update tripwire).
- `tests/test_p0_s1_replay.py` — 5 replay smoke tests with extended `build_stranger_first_encounter`.
- `tests/fixtures/event_log_fixtures.py` — D7 parameterization.
- 3 deliberate-regression induction-protocol confirmations (not pytest cases — closure-report items).

**Tests:** 14 new. Phase 4 closure: full pytest-green + induction confirmations + closure report.

### Closure (≈0.25 day)

- Closure report with discipline-count updates (spec-first 6→7-for-7; tripwires 3→4-for-4 if D9 tripwire lands cleanly; induction 7→? depending on what surfaces).
- `CLAUDE.md` milestone entry + `complete-plan.md` P0.S1 [CLOSED] entry.
- `everything_about_system.md` Part LII (or appended to existing Anti-Spoof Part XXIV) with P0.S1 architectural narrative.

### Live canary validation (separate session, ≈0.5 day)

- Three independent canary sessions per §9 criteria.
- 9 expected rejections + 3 expected passes.
- Burst-alert reproduction during one session.
- Runbook closure when gate criteria met.

**Total Plan v2 estimate: 1.75-2.5 days focused work + 0.5 day live canary.**

---

## 12. Open items / risks (unchanged from Plan v1 except noted)

1. **`AntiSpoofChecker.last_score` attribute** — verify exists; add in Phase 1 if not (+10 min).
2. **TrackStore lock contention** — explicitly stress-tested in Phase 1 #6 (MED 6).
3. **Empty track at gate time** — handled by verdict-None routing through reject path with `no_verdict` reason. Test covered.
4. **Multi-track sessions** — gate-bound track's verdict is authoritative. Conservative choice documented.
5. **Anti-spoof score logging** — float [0, 1], no PII.
6. **NEW (Plan v2)** — `_classify_anti_spoof_verdict` helper inputs assume `verify_live` returns `bool` not `Optional[bool]`. Verified in core/vision.py:: `verify_live(...)` returns bool. ✓
7. **NEW (Plan v2)** — AST scan implementation complexity. The same-frame scan walks variable provenance; if intractable in practice (cases with multiple intermediate assignments), Plan v2 documents the fallback to marker-comment-based check at §3.2.

---

## 13. Discipline-count clarifications (unchanged from Plan v1)

Holding all counts at audit-time values until P0.S1 closure:

- Spec-first review cycle: **6-for-6** (P0.S1 earns 7-for-7 on closure)
- Developer-improves-on-spec: **5-for-5**
- Sub-pattern A (Phase 0 audit caught wrong premise): **2 instances** (P0.10 + P0.S1) — observation tracked in CLAUDE.md
- Tripwires-must-match-deferral-surface: **3-for-3** (4-for-4 candidate on P0.S1 closure if D9 tripwire lands cleanly)
- Induction-surfaces-invariant-gaps: **7-for-7** (Plan v2 Phase 4 induction confirmations are protocol firings, not new instances — instances counted only when they surface a real gap)

---

## 14. Next steps

1. **Auditor review of Plan v2** — expected: confirmation that items 1-9 are correctly addressed; any residual precision items become Plan v3 or get banked as in-flight clarifications during code phase.
2. **Joint sign-off** → code phase starts.
3. **Phase-by-phase implementation** with full-suite verification between phases (per `pytest --tb=no -q` discipline banked from P0.0.7 Step 5 polish).
4. **Closure report** with deliberate-regression confirmations + discipline-count updates.
5. **Live canary validation session** following the runbook.
6. **P0.S1 closure** unlocks the next item in the locked sequence.

---

## 14b. Implementation notes (auditor sign-off clarifications, 2026-05-18)

Two clarifications banked during sign-off that refine the Plan v2 contract without requiring a Plan v3. Developer codes against these notes as part of the Phase 3 + Phase 2 implementation.

### 14b.1 Burst-alert dedup — exact-equality trigger (Phase 3)

The `_record_anti_spoof_rejection` helper (§ Phase 3 deliverables) MUST fire `report_anti_spoof_burst` exactly once on threshold crossing, not on every rejection past threshold. The auditor's recommendation — accepted as the implementation lock — is the exact-equality trigger:

```python
async def _record_anti_spoof_rejection(*, person_id: str, track_id: str, reason: str) -> None:
    now = time.time()
    count = await _anti_spoof_rejection_store.record_rejection(
        track_id, now, ANTI_SPOOF_BURST_WINDOW_SECS,
    )

    # D10.c — per-instance dashboard event (severity=info) fires every rejection.
    if _brain_orchestrator is not None:
        _brain_orchestrator.report_anti_spoof_rejection(
            track_id=track_id,
            person_id=person_id,
            reason=reason,
            burst_count=count,
            window_secs=ANTI_SPOOF_BURST_WINDOW_SECS,
        )

    # C2 burst alert — EXACT-EQUALITY trigger: fires exactly once on the
    # threshold-crossing rejection. Subsequent rejections in the window
    # produce the per-instance dashboard event (above) but do NOT re-fire
    # the burst alert.
    if count == ANTI_SPOOF_BURST_THRESHOLD:
        if _brain_orchestrator is not None:
            _brain_orchestrator.report_anti_spoof_burst(
                track_id=track_id,
                person_id=person_id,
                reason=reason,
                count=count,
                window_secs=ANTI_SPOOF_BURST_WINDOW_SECS,
            )
```

**Why exact-equality (not `>=`):**

- No extra dedup state required (no `burst_fired_at` timestamp per track, no "alert sent" boolean).
- Deterministic semantic: the 3rd rejection in a 60s window fires the burst alert; the 4th and 5th do not. If the burst pattern continues past the window (entries from start of window prune out, fresh entries arrive), the count drops back below threshold, and the next time it crosses 3 again, the alert fires anew. This is the correct behavioral shape — burst alerts mark new escalation events, not sustained activity.
- Matches the Phase 3 test description ("4th rejection does not double-fire") directly.

The Phase 3 test `test_burst_threshold_fires_once_then_per_instance_only` explicitly verifies this — 3 rejections fire the burst exactly once; the 4th rejection produces only the per-instance event; after window prune, a new burst pattern fires the burst alert again.

**Closure report obligation:** Phase 3 closure report explicitly flags that the exact-equality trigger landed (not the per-track-timestamp variant). If the developer surfaces a reason during implementation that exact-equality doesn't work (a corner case not yet anticipated), they raise it in the closure rather than silently switching to the timestamp variant.

### 14b.2 AST same-frame scan — route flexibility (Phase 2)

§3.2 of Plan v2 documents two implementable routes for the same-frame structural test:

- **Primary route:** AST variable-provenance graph walk — finds `_crop = frame[bbox]` slice base assignment, asserts `verify_live`'s first arg's `Name.id` matches the slice base's `Name.id`.
- **Fallback route:** marker-comment scan — production code carries `# P0S1-C0:` annotation; AST locates the annotation, asserts `verify_live` + `embedder.embed` calls in the next K lines share the frame variable.

Both routes are contract-preserving — either one satisfies C0's structural enforcement by Phase 2 closure. Developer picks during Phase 2 implementation based on implementation tractability.

**Closure report obligation:** Phase 2 closure report names which route landed. If the marker-comment fallback ships AND turns out cleaner than the AST graph walk in practice (less brittle, faster to scan, easier to debug failures), this is a candidate developer-improves-on-spec instance — bank it explicitly in the closure with the architectural rationale, per the standard pattern (Part L §327).

If the AST graph walk lands cleanly, no banking — it's the route Plan v2 prescribed.

---

## 15. Reference documents

- `tests/p0_s1_audit.md` — Phase 0 audit (premise reset + D1-D10)
- `tests/p0_s1_plan_v1.md` — Plan v1 (this document supersedes; v1 retained for delta visibility)
- `tests/p0_s1_validation_runbook.md` — will be drafted during code phase (closure-gate criteria per §9)
- `core/db.py:34, 574` — VALID_EMBEDDING_SOURCES + add_embedding entry point
- `core/track_store.py` — TrackStore (P0.6 Store-pattern base)
- `core/vision.py::verify_live` — canonical wrapper (returns bool, no None)
- `core/vision.py::AntiSpoofChecker` — MiniFASNet ensemble
- `pipeline.py:6466-6482` — reference gate (recognition_update, migrated in Phase 1 site #4)
- `pipeline.py:7670-7720` — progressive_enroll gap site (closed in Phase 3)
- `pipeline.py:2540-2680` — _background_vision_loop both scan paths (Phase 2 producer integration)
- `tests/fixtures/event_log_fixtures.py::build_stranger_first_encounter` — D7 fixture extension target
- `everything_about_system.md` Part XXIV (Anti-Spoofing), Part XXXVIII (Atomicity), Part XXXIX §259 (P0.6 ratchet at cap=0), Part L (Disciplines)
