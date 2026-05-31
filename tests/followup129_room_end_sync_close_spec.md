# Follow-up #129 — Room-end misfire on simultaneous multi-expiry → `SessionStore._sync_close_session`

**Status:** LOCKED — auditor GREENLIGHT 2026-05-31. Ready for the developer.
**Lineage:** surfaced during Canary #4 Layer-3; the symmetric completion of Canary #4 B1.
**Order rationale:** first of the four follow-ups because it closes the SessionStore
lifecycle-visibility invariant that B1 only half-finished (open made synchronous; close left
fire-and-forget). Strengthens the spine the router, room lifecycle, and reconciler all hang off.

**Auditor disposition (folded in below):** C1-C4 ratified as the symmetric close-side mirror of
B1 (all four B1 conditions carry forward). Q1 = leave :7200 unchanged + forward-consistency note.
Q2 = keep the :2217 exclusion AND rewrite the stale :2212-2214 comment. Q3 = both assertions +
both-participants check. **Sharp PI: the §7 drain-retirement is close-pop-only** — room-end and
full-cleanup synthesis stay async, so GT0/GT2 still need a loop drain for their spy/state
assertions; GT0 must be `@pytest.mark.asyncio` with a running loop. Closure gate in §10.

---

## 0. Wrong-premise correction (Phase 0) — auditor-confirmed

The issue title says "room-end **misfires**," which reads as a double-fire. Grep-verified
reality: it is a **missed fire**, not a double fire. The single-expiry double-fire is already
guarded by the synchronous `_sync_clear_room()` at `pipeline.py:2228` (the comment at 2222-2227
says so verbatim). The real defect is that on **simultaneous multi-expiry the room-end never fires
at all**, leaving `_active_room_session` orphaned.

---

## 1. Root cause (grep-verified, auditor-confirmed line-by-line)

`pipeline.py:2134 _close_session()` removes the session via **fire-and-forget**:

```
2153:  asyncio.get_running_loop().create_task(_session_store.close_session(person_id))
```

`_session_store.close_session` (`core/session_state.py:246-248`) is `async with self._lock:
self._sessions.pop(pid, None)` — so the pop runs on a **later** event-loop tick.

The room-end gate (`_close_session`, 2215-2218) excludes only the **single** current person:

```
2215:  _room_snap = _pipeline_state_store.peek_active_room_session()
2216:  _remaining_sessions = [s for s in _session_store.peek_all_snapshots()
2217:                         if s.person_id != person_id]
2218:  if not _remaining_sessions and _room_snap is not None:
```

`_expire_stale_sessions` (2257) collects `_expired` then closes each in a **synchronous loop**
(2361/2376).

**Trace, two sessions A+B both expiring in one pass:**
- `_close_session(A)` → schedules A's pop (pending). `_remaining = [B]` (B fully present) → non-empty → no room-end.
- `_close_session(B)` → schedules B's pop. `_remaining = [A]` — **A's pop is still pending, A is in the store** → non-empty → no room-end.
- Result: **room-end never fires.** `_sync_clear_room()` never runs. `_active_room_session` orphaned.

**Secondary bug (same root cause):** the full-cleanup at line 2379
(`if _expired and not _session_store.peek_all_snapshots():`) reads the store in the same tick as
the pending pops, so it is non-empty even on full close — misfires even for single expiry (the one
pop is also pending). Fixed by the same C4 line.

### Confirmed consequences (grep-verified)
- `_open_session` reads `peek_active_room_session()` to inherit-or-mint (`1867`, `1989`). A stale
  `_active_room_session` → the **next arrival joins the dead room** instead of minting a fresh one.
- `conversation_turn` passes the room session id at `3583` + `5967` → a stale id **contaminates
  `conversation_log.room_session_id`** for the new room's turns.
- Room-end synthesis (`_on_room_end`, 2077) never runs for that room (3A: logging; 3B widens this).

### Severity
**Low-medium.** Triggers in the realistic "whole multi-person room goes quiet / leaves together"
case (≥2 sessions cross `VOICE_SESSION_TIMEOUT`/`FACE_LOSS_GRACE` in one poll). Effect is room-id
contamination + skipped cleanup, not a crash or wrong-attribution.

---

## 2. Fix — Option C (symmetric `_sync_close_session`)

Mirror Canary #4 B1 exactly. B1 added the blessed sync **open**; this adds the blessed sync
**close**, completing the lifecycle so every post-close check reads true state. Four conditions
C1-C4 (the B1 condition shape).

### C1 — `SessionStore._sync_close_session(pid)` (the second blessed sync mutator)
`core/session_state.py`, immediately after `_sync_open_session`:

```python
def _sync_close_session(self, pid: str) -> None:
    """C1 (#129) — the blessed SYNC session removal, mirror of _sync_open_session.
    Purely sync: NO await, NO `async with self._lock`. `dict.pop` is GIL-atomic, so a
    concurrent peek_snapshot sees the session present or gone, never a half-state — the
    same single-threaded-asyncio safety argument as the sync open (strictly simpler: a
    single pop, no build phase to leave half-state). Used by pipeline._close_session so
    the removal is visible the instant it returns, closing the multi-expiry room-end race
    (the close-side mirror of Canary #4's open-side fix)."""
    self._sessions.pop(pid, None)
```

### C2 — `close_session` delegates (so async + sync can't diverge)
```python
async def close_session(self, pid: str) -> None:
    async with self._lock:
        self._sync_close_session(pid)
```
(Mirrors `open_session` → `_build_and_insert`. Single removal site = no divergence.)

### C3 — allowlist + class-docstring (the SessionStore invariant; docstring is MANDATORY per B1)
- `tests/test_session_state_invariants.py` `SYNC_METHOD_ALLOWLIST` gains `_sync_close_session`
  with justification (the AST "no sync mutators" test now permits exactly
  `{_build_and_insert, _sync_open_session, _sync_close_session}` — `_build_and_insert` is already
  a sync writer post-B1; INV1 enforces "exactly these three, no others").
- The `SessionStore` class docstring (item 2, `core/session_state.py:161-167`) updates its
  sync-write enumeration from "the one blessed sync write" to the **sync open/close pair**,
  preserving the precise-necessary framing. (Auditor's non-negotiable B1 condition 4, carried.)

### C4 — `pipeline._close_session` uses the sync removal + comment rewrite (Q2)
`pipeline.py:2152-2155`, replace the fire-and-forget create_task with the direct sync removal:
```python
_session_store._sync_close_session(person_id)
```
Drop the surrounding `try/except RuntimeError` (a sync pop needs no running loop). This is the
**only behavioral line**; everything downstream now reads true post-removal state:
- 2216 `_remaining_sessions`: on multi-expiry, A is already removed when B closes → the **last**
  expiry sees `_remaining = []` → room-end fires **exactly once**. `_sync_clear_room()` (2228)
  still makes a third close idempotent. Fires once, not zero, not twice.
- 2379 full-cleanup: `not peek_all_snapshots()` now reads true state → fires when all closed.

**Q2 stale-comment rewrite (auditor-required).** The comment at `pipeline.py:2212-2214` currently
reads "close_session() is a create_task (async) so the session may still be in the store at this
point." Post-C4 that is a **falsehood** — the session is already removed when the gate runs.
Leaving an "async close" rationale once close is synchronous is exactly the stale-rationale drift
that misleads the next reader (same class as B1's PI-1 stale "legacy dict" comment). Rewrite to:

> close is now synchronous via `_sync_close_session`, so the session is already gone when this gate
> runs; the `person_id` exclusion below is retained as belt-and-braces for any future caller that
> reaches this gate without sync-removing first.

The `if s.person_id != person_id` filter at :2217 **stays** (harmless no-op when the pid is already
absent; defends a future non-sync-removing caller).

---

## 3. Golden tests — RED-first (drive the real pipeline; the async-drain rule is load-bearing)

**Critical authoring rule (auditor PI).** After C4, `peek_active_room_session() → None` is
**synchronous** (`_sync_clear_room()` at :2228). But `_on_room_end` is still fired via
`create_task` (the guard at :2230+ keeps room-end synthesis async by design — it's heavyweight 3B
work that must never block the close path), and the line-2379 full-cleanup fires
`create_task(_presence_store.clear())` + `create_task(set_detected_lang("en"))` — also async. So
any assertion that reads an **async-fired** effect (the `_on_room_end` spy, the presence/lang
cleanup) needs **`await asyncio.sleep(0)` after `_expire_stale_sessions()`** to let those tasks
run; the sync `peek_active_room_session()` assertion does **not**. GT0/GT2 must be
`@pytest.mark.asyncio` with a running loop — in a no-loop sync context the :2230+ guard logs
without scheduling `_on_room_end`, so the spy would read zero regardless of the fix (a vacuity-class
false-pass).

- **GT0 (load-bearing) — multi-expiry fires room-end once, clears the room.**
  `@pytest.mark.asyncio`. Open A+B into one room (`_open_session` ×2, same `_active_room_session`),
  spy `_on_room_end`, backdate both past timeout, call `_expire_stale_sessions()`, then
  `await asyncio.sleep(0)` (drain the async `_on_room_end` task). Assert all three (Q3 — they pin
  different halves of the contract; a bug could fire-without-clearing or clear-without-firing):
  1. `_on_room_end` spy **call-count == 1** (zero = the current bug; two = broken `_sync_clear_room`
     idempotency) — reads the async-fired task, needs the drain.
  2. the spy call carried **both participants** (guards a truncated `_ended_participants` read at
     :2221).
  3. `peek_active_room_session()` is `None` after (the orphaned-room-id consequence; sync, no drain
     needed).
  **RED before C4** (room-end never fires, `_active_room_session` still set); **GREEN after**.
- **GT1 — single-expiry regression.** Open A only, expire it, `await asyncio.sleep(0)`. Assert
  `_on_room_end` fires exactly once (guards against the fix breaking the already-working single
  path).
- **GT2 — full-cleanup fires on full close.** Multi-expiry → `await asyncio.sleep(0)` → assert the
  line-2379 cleanup ran (`set_detected_lang("en")` / presence cleared). Locks the secondary fix;
  these reads are async-fired, so the drain is required.

These are SessionStore/pipeline-state behavioral tests (no `core.voice`/`core.audio` hardware), so
they are **not** vacuity-prone against the conftest stub and run on any box. (The systemic vacuity
guard is follow-up #126; these don't need it.)

## 4. Invariant tests
- **INV1** — `_sync_close_session ∈ SYNC_METHOD_ALLOWLIST`; the AST scan permits exactly the three
  sync writers and no others. (Closure proof: RED when `_sync_close_session` is added without the
  allowlist entry → GREEN once allowlisted — the invariant doing its job.)
- **INV2** — `close_session` body delegates to `_sync_close_session` (source/AST), so the two
  removal paths cannot diverge.

## 5. Behavioral-RED proof (per-fix discipline)
Revert C4 (restore the fire-and-forget `create_task(close_session(...))`) → **GT0 goes RED for the
production reason** (room-end never fires on multi-expiry; `_active_room_session` orphaned) →
restore → net-zero. Confirms GT0 fails for the real defect, not a mock/drain artifact.

## 6. Ripple audit (grep-verified)
- `_close_session` callers (bare module-level call — grep `_close_session(` at closure to confirm
  exhaustive): `2376` (`_expire_stale_sessions`, the bug locus) + `8504` (ambiguous-drift, single
  close). Neither relies on the session remaining present after the call (`_close_session` captures
  `_close_snap` at its top, 2136, before removal; the drift caller sets `_cur_pid = None` after).
  Both correct under sync removal. The full-suite run is the universal completeness proof that no
  caller relies on post-close presence (§10).
- **Q1 (auditor: leave :7200 unchanged — scope-correct).** `pipeline.py:7197-7204` is a separate
  reset-path close loop (`create_task(close_session(...))` then `_pipeline_state_store.reset()`) —
  no room-end gate, no synchronous-visibility dependency, and reset clears room state
  synchronously, so the multi-expiry race does not exist there. Factory reset is not concurrent
  with normal expiry. **Do not widen this cycle into a reset-path refactor.**
  **Forward note (non-binding, file as one-line low-priority tidiness):** now that
  `_sync_close_session` exists, the reset loop *could* adopt it for consistency (it iterates a
  `peek_all_snapshots()` tuple, so sync-popping during iteration is safe) — so a future reader
  isn't left puzzling "why is close sync everywhere except this reset path?" Not this cycle.

## 7. Architectural-tidiness bonus — scoped to close-pop drains ONLY (auditor PI)
Canary #4 added **test-only** `asyncio.sleep(0)` drains to make sync-context closes take effect
(the "pre-existing sync-context close-no-op" finding). With `_sync_close_session`, the **session
pop** is synchronous in tests too, so the drains added **for the pop** retire — the genuine
tidiness win (the new build removes scaffolding the previous one needed).
**But room-end synthesis (`_on_room_end`, fired via `create_task` at :2230+) and the full-cleanup
(:2379) stay async by design — their drains do NOT retire.** Scope the retirement to close-pop
drains only; do not over-retire into a flake. (This is the same constraint that makes GT0/GT2 need
their own drain in §3.)

## 8. Estimate
~8 logical anchors (auditor-confirmed sound): C1/C2 collapse to one sync-close-pair anchor,
C3-allowlist overlaps INV1, leaving the sync-pair + C3-docstring + C4(line) + C4(comment) + GT0 +
GT1 + GT2 + INV1 + INV2, ≈ 8. Actual count lands at closure.

## 9. Open questions — RESOLVED (auditor 2026-05-31)
- **Q1 — RESOLVED:** leave `:7200` unchanged (scope-correct) + file the forward-consistency
  tidiness candidate (§6).
- **Q2 — RESOLVED:** KEEP the `:2217` exclusion AND rewrite the stale `:2212-2214` comment (§2 C4).
- **Q3 — RESOLVED:** GT0 asserts all three — spy call-count == 1, both-participants, post-state
  None (§3 GT0).

## 10. Closure gate (auditor-affirmed)
- **Full suite on the CUDA box, 0 failed** — the "sync-close breaks nothing" proof + the universal
  completeness proof that no `_close_session` caller relies on post-close presence (grep
  `_close_session(` confirms the 2-caller enumeration is exhaustive).
- **GT0 / GT1 / GT2 RED→GREEN** (authored with the §3 drain rule).
- **INV1 RED→GREEN** — RED when `_sync_close_session` is added without the allowlist entry, GREEN
  once allowlisted.
- **§5 behavioral-RED proof** — revert C4 → GT0 RED for the production reason → restore net-zero.
- **Layer-3** — architect independent full-suite run on the CUDA box + line-by-line re-read before
  closure.
