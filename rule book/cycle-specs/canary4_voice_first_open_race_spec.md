# Spec — Canary #4: voice-first session-open race drops turns + spawns phantom visitors

**Status:** GREENLIT — Option B / B1 RATIFIED by auditor 2026-05-31 (4 conditions + 3 PIs, §8). Ready for developer.
**Author:** architect
**Date:** 2026-05-31
**Canary:** 2026-05-31 live run (`terminal_output.md`). Camera closed, Jagan spoke; got no answer, then got assigned to a visitor.
**Relation:** validates the durable directive *vision and voice must be truly independent* — with vision off, voice alone currently can't sustain a conversation. Adjacent to the HELD Spec 3 (vision-presence independent router); this is the narrower, root-caused fix for the observed failure.

---

## 0. One-paragraph summary

When the camera is off (no face in frame), the voice-first path identifies a known speaker by voice and calls `_open_session(...)`. But `_open_session` registers the session via a fire-and-forget `create_task` (`pipeline.py:1905`), so the session is **not synchronously visible**. The very next line, `if not _session_store.peek_all_snapshots():` (`pipeline.py:7684`), therefore runs the stranger **engagement-gate block even after a known speaker was identified**. For an utterance without the system name, the gate fails and clears `_ambient_text` (`:7760`) — the user's message is silently dropped and the session expires with no answer. For an utterance containing the system name, the gate passes and opens a **phantom visitor session** (`:7746`), to which the conversation then routes. One race produces both observed symptoms. The fix (Option B) makes the session synchronously visible so the re-check is reliable.

---

## 1. Evidence (canary `terminal_output.md`, camera off)

**Embed fix (Canary #3) validated, for the record:** `[Voice] Profile updated for jagan_39194f` climbed 1/20 → 17/20 via `face_witness`, **zero `embed returned None`**. This spec is a *different* bug.

**Symptom A — no answer** (lines 3109-3128): STT *"I think Lexi is taking a little bit time with the new grinder… I think you can shut down now"* → `Voice-first: heard speech` → `Session Open: jagan_39194f (voice)` → `Identified Jagan by voice (score=0.865)` → `Conversation started for Jagan` → `State: WATCHING -> LISTENING` → `Listening for Jagan…` → `Vision Active (LISTENING) — Jagan` (state never advances to THINKING) → `Session expired: Jagan`. **No `Turn start`, no brain call, no TTS.** The utterance had no system name → the gate cleared `_ambient_text`.

**Symptom B — assigned to a visitor** (lines 3147-3156): STT *"Shut down now Kara, Lexi will talk to you later in the evening"* → `Session Open: jagan_39194f (voice)` → `Identified Jagan by voice (score=0.808)` → `Participant joined: visitor (stranger_visitor_cdac53)` → `Session Open: stranger_visitor_cdac53 (voice) — visitor` → `Stranger engaged (voice-only, system addressed)` → `Conversation started for visitor`. The "Stranger engaged" printed **before** "Conversation started" → it came from the **voice-first gate (`:7757`)**, not the in-loop new-stranger path (`:8453`). The utterance contained "Kara" → the gate passed → phantom visitor.

---

## 2. Root cause (code-confirmed)

`pipeline.py:1902-1913` (inside `_open_session`):

    # P0.7.2-SHIM: canonical-first — populate SessionStore BEFORE legacy dict
    _loop.create_task(_session_store.open_session(person_id, ..., now=now, ...))

The session is registered **asynchronously**. `_session_store.peek_snapshot(pid)` / `peek_all_snapshots()` will not show it until that task drains.

The codebase already recognized this exact hazard for the **room** state and fixed *that* synchronously (`:1851-1854`, `:1865-1868` — `_pipeline_state_store._sync_mint_room`, `_sync_add_room_participant`, comment "see the minted id without waiting for a create_task to drain"). The **session** open was left async. NB: those sync helpers live on `PipelineStateStore`, which has no "all-async" invariant; SessionStore is stricter (see §3) — so this is the *first* sync write on SessionStore, not a direct mirror.

The voice-first block then does (`pipeline.py:7669-7760`, abridged):

    v_pid, v_score, _ = await voice_mod.identify(_ambient_audio, ...)        # 7670
    if v_pid:
        row = db.get_person(v_pid)
        if row:
            _open_session(v_pid, row["name"], "voice", person_type=_v_pt, ...)   # 7677 — async-registered
            print("Identified … by voice")                                       # 7678
            await _conversation_store.ensure_history_loaded(v_pid, ...)           # 7679 — returns from cache w/o yielding
    if not _session_store.peek_all_snapshots():                                   # 7684 — RACES the open
        # … first_boot / name-heard engagement gate / camera-fallback / stranger …
        elif _name_heard_in(_ambient_text, system_name)[0]:                      # 7689
            # gate PASSED → camera fallback → if no face: open stranger (7746) + "Stranger engaged" (7757)
        else:
            _ambient_text = ""                                                   # 7760 — gate FAILED → drop the turn

When `ensure_history_loaded` (`:7679`) returns synchronously from cache (a *returning* speaker like Jagan), the `await` does not yield, the `open_session` task at `:1905` has not drained, and `:7684` sees an empty store. The gate runs despite `v_pid` having matched.

- **No system name** → `else: _ambient_text = ""` (`:7760`) → the conversation loop at `:7848` finds `_ambient_text` empty → re-listens (`:7859`) → state stays LISTENING → the session (visible once the task drains) idles 30s → `_expire_stale_sessions` closes it (`now - last_spoke_at > VOICE_SESSION_TIMEOUT`, `:2330`). **Symptom A.**
- **System name present** → gate passes → no face → `_open_session(stranger)` (`:7746`) → `_primary_person_id()` (`:7762`) returns the visitor → `Conversation started for visitor` → routes to the visitor. **Symptom B.**

Deterministic for returning speakers (cached history → no yield at `:7679`) — which is why it surfaced for Jagan with the camera off.

---

## 3. Fix — Option B: synchronous session visibility [SELECTED]

Make the session visible the instant `_open_session` returns, so `:7684` (and every other peek-after-open) reliably sees it and the engagement gate is skipped for an already-identified known speaker. Fixes the whole class of peek-after-open races, not just this one site.

### The invariant collision (one ratification required)

SessionStore **deliberately has no sync mutators**: `core/session_state.py:158` ("No sync mutators … all mutations protected by self._lock via async methods") + `peek_snapshot` is a lock-free dict read, safe *because* nothing writes the dict synchronously. `tests/test_session_state_invariants.py::test_session_store_no_sync_mutators` enforces this — `SYNC_METHOD_ALLOWLIST` = dunders + the two sync **reads** only; **zero sync writes** today. Synchronous visibility therefore requires the **first sync write** on SessionStore. Two ways to deliver Option B:

**B1 — blessed sync mutator (architect-recommended).**
- Add `SessionStore._sync_open_session(person_id, person_name, person_type, session_type, *, now, bootstrap_credits, room_session_id, voice_sample_count) -> None`: construct the full `Session` object, then atomically insert `self._sessions[person_id] = s` — **no `await`, no lock**.
- The async `open_session` delegates to the same construct-and-insert (e.g. `async with self._lock: <shared insert>`) so the two paths cannot diverge.
- `pipeline._open_session` (`:1902-1913`) calls `_sync_open_session(...)` **directly**, replacing the `create_task(_session_store.open_session(...))`. The session is visible when `_open_session` returns → `:7684` reliably sees it → gate skipped. No change needed at `:7684` itself.
- Add `_sync_open_session` to `SYNC_METHOD_ALLOWLIST` **with a documented justification** (the invariant test goes RED until then — the invariant working as designed; the test message at `:177-178` explicitly invites this).
- **Safety justification:** atomic construct-then-insert under single-threaded asyncio is safe for the same reason `peek_snapshot` is — one thread, no real parallelism; the dict insert is a single atomic op on a fully-built `Session`; a concurrent peek observes either the old state (no pid) or the fully-built new state, never a half-written one. `peek_snapshot`'s safety is preserved. This is a **deliberate, narrow weakening** of "no sync mutators," confined to the open path, justified by atomicity.

**B2 — async `_open_session` + awaiting callers (keeps the invariant pristine).**
- Make `pipeline._open_session` `async def` and `await _session_store.open_session(...)` instead of `create_task`; update its callers (~6 sites) to `await _open_session(...)`. No sync mutator → the invariant is untouched.
- Cost: larger ripple (every `_open_session` caller); GT0 becomes "visible after `await`" rather than "synchronously visible"; must confirm no caller is in a sync context (if any is, it can't `await` → B2 fails for that caller).

**Architect recommendation: B1.** It delivers exactly the synchronous-visibility semantics + clean GT0 the chosen option intends; the atomic-insert safety argument is solid; the allowlist is the sanctioned escape hatch. B2 is the fallback if the auditor prefers not to introduce the first sync mutator to SessionStore. (Option A from the prior draft — a local `_voice_id_opened` flag gating only `:7684` — was the surgical alternative; not chosen, since it leaves the async-visibility gap intact for other peek-after-open sites.)

---

## 4. Golden tests (RED-first — the directive)

**GT0 — synchronous session visibility [unit; the root-cause assertion].** (B1) `_open_session("jagan_x", "Jagan", "voice", person_type="known")` → assert `_session_store.peek_snapshot("jagan_x") is not None` **synchronously** (no `await`/drain). RED today (async `create_task`); GREEN after B1. (B2 variant: `await _open_session(...)` → visible after the await.)

**GT-A — camera off, known speaker, NO system name → answered, not dropped [behavioral].** Drive the voice-first arbitration with `voice_mod.identify` → (Jagan, strong score), no face available, `_ambient_text` = a message **without** the system name. Assert: (i) **no** `stranger_visitor_*` session opened; (ii) `_ambient_text` is **preserved** (the turn reaches processing for Jagan), i.e. the engagement-gate `else: _ambient_text=""` did not run. RED today; GREEN after the fix.

**GT-B — camera off, known speaker, WITH system name → routes to the known speaker, no visitor [behavioral].** Same setup but `_ambient_text` **contains** the system name. Assert: (i) **no** `stranger_visitor_*` session opened; (ii) `_primary_person_id()` resolves to the known speaker, not a visitor. RED today (phantom visitor opens, primary → visitor); GREEN after the fix.

**Invariant test update.** `test_session_store_no_sync_mutators` must add `_sync_open_session` to `SYNC_METHOD_ALLOWLIST` with the §3 justification. Adding the method goes RED first (the invariant correctly catches the new sync write); blessing it + the justification is the conscious decision the invariant is designed to force.

**Testable-surface note (Q2).** GT-A/GT-B target logic currently inlined in `run()`'s main loop, which is not directly callable. The spec proposes extracting the voice-first arbitration decision — "given (voice-ID result, face-available, `_ambient_text`, system_name), did we open a known-speaker session, or must the engagement gate run?" — into a small pure helper (e.g. `_voice_first_should_engage_stranger(...) -> bool`) that both `run()` and the tests call (same discipline as `_resolve_actual_speaker`). GT0 needs no extraction.

---

## 5. Scope / non-goals

- **In-loop new-stranger path (`:8430-8454`) is NOT changed.** It fires on `_routing_action == "new_stranger"` from `_resolve_actual_speaker` — correct for genuine mid-conversation new speakers. The canary's phantom visitor came from the voice-first gate (`:7757`), not here. (Q3: should we *also* audit whether `_resolve_actual_speaker` can return `new_stranger` for an active known speaker who says the system name? Flagged, not in this spec.)
- **Spec 3 (vision-presence independent router) stays HELD.** This is the narrow root-cause repair, a concrete down payment on the voice/vision-independence directive, not the redesign.
- **No change to `VOICE_SESSION_TIMEOUT` / `_expire_stale_sessions`.** The 30s expiry is correct; the session only idled because the turn was dropped. Fixing the gate removes the idle.
- **Together.ai flapping** (`Retrying… reconnected!` ~7× in 3 min) is a separate reliability concern — noted, not in scope. It did not cause the no-answer (the turn never started).

## 6. Files touched (Option B / B1)

- `core/session_state.py` — add `SessionStore._sync_open_session(...)` (sync construct-then-insert); `open_session` delegates to the shared insert.
- `pipeline.py:1902-1913` — call `_sync_open_session(...)` directly, drop the `create_task(open_session)`. (`:7684` unchanged — it now reliably sees the session.) Optional: extract `_voice_first_should_engage_stranger(...)` for GT-A/GT-B (Q2).
- `tests/test_session_state_invariants.py` — add `_sync_open_session` to `SYNC_METHOD_ALLOWLIST` + documented justification.
- `tests/test_canary4_voice_first_open_race.py` (new) — GT0, GT-A, GT-B.
- No production behavior change beyond the fix.

## 7. Q-block (architect → auditor)

- **Q1 — invariant ratification (the decision).** Option B is chosen; within it, **B1** (blessed sync mutator `_sync_open_session` + allowlist + justification) vs **B2** (async `_open_session` + awaiting ~6 callers, invariant untouched). B1 adds the first sync write to SessionStore — a deliberate, narrow weakening of "no sync mutators," justified by atomic construct-then-insert under single-threaded asyncio. Architect lean: **B1** (clean synchronous-visibility semantics + GT0; safe). Auditor's call.
- **Q2 — testable surface.** Extract `_voice_first_should_engage_stranger(...)` so GT-A/GT-B are unit-testable? Architect lean: yes.
- **Q3 — in-loop audit.** Separate follow-up to confirm `_resolve_actual_speaker` cannot return `new_stranger` for an active known speaker who utters the system name (the in-loop sibling of this gate)? Architect lean: file separately, not this cycle.
- **Q4 — safety check.** Preliminary grep shows `_open_session` is used sparsely in tests with no reliance on a session being invisible right after open; the full 3850-suite run on the CUDA box is the definitive check that B1's synchronous visibility breaks nothing. Confirm this is the closure gate.

---

## 8. Auditor verdict — RATIFIED 2026-05-31 (locked for developer)

**GREENLIGHT — Option B / B1.** No blocking items. The first sync write on SessionStore is approved on FOUR conditions (all required — they make the weakening narrow + auditable):

**C1 — `_sync_open_session` MUST be purely sync.** No `await`, no `async with`. The entire safety argument rests on it being uninterruptible; any await reintroduces a yield point and breaks the atomicity guarantee.

**C2 — shared insert, no path divergence.** Extract construct-and-insert into ONE sync helper (e.g. `_build_and_insert(...)`); `open_session` does `async with self._lock: self._build_and_insert(...)`, `_sync_open_session` does `self._build_and_insert(...)` directly. A literal shared code path so the two opens can't drift (one setting `room_session_id`, the other forgetting). `open_session`'s body (`session_state.py:182-200`) is already atomic-once-acquired (no internal await) — `_sync_open_session` is mechanically that body minus the lock wrapper.

**C3 — allowlist entry carries the reasoning.** The `SYNC_METHOD_ALLOWLIST` addition must include a written justification anchoring the atomicity argument (single-threaded asyncio + atomic construct-then-insert + no await → peek never sees a half-state) AND citing the `_sync_mint_room` precedent — so a future auditor reading the allowlist understands why this one sync write is blessed.

**C4 — update the SessionStore class docstring (`session_state.py:153-160`) — MANDATORY.** Condition 2 currently reads "No sync mutators (all mutations protected by self._lock via async methods)" — false after B1. Reword to the precise-necessary form: `_sync_open_session` is the one blessed sync write, safe by atomic construct-then-insert (no await → cannot interleave with `peek_snapshot`). The docstring is the invariant's canonical English; leaving it stale = the next reader believing a lie about the invariant.

**Safety basis (auditor, for the record):** peek_snapshot's "no sync mutators" is a *sufficient*, not *necessary*, condition. The necessary condition is "no mutator leaves the dict in a half-state observable by a concurrent peek." A purely-sync atomic construct-then-insert satisfies it. B1 narrows condition 2 from conservative-sufficient ("no sync writes at all") to precise-necessary ("no sync write that yields or leaves a half-state"). peek_snapshot's safety is preserved.

**Q2 — RATIFIED:** extract `_voice_first_should_engage_stranger(...)` with **mechanical-extraction discipline (P0.8 rule)** — pull out ONLY the boolean decision ("given voice-ID result, face-available, `_ambient_text`, system_name → did we open a known session, or must the gate run?"); the camera-fallback face recognition + the actual `_open_session` calls stay in `run()`. Pure verbatim move, no "while I'm here" behavior changes. The `:7684-:7760` region is tangled — extract the decision cleanly, leave the side-effecting work in place.

**Q3 — RATIFIED as a tracked follow-up (task #128), NOT this cycle.** Audit whether `_resolve_actual_speaker` can return `new_stranger` for an active known speaker who utters the system name (the in-loop sibling at `:8430-8454`). Same bug class at a sibling site; B1's fix may or may not also close it.

**Q4 — CONFIRMED closure gate:** the full 3850-suite run on the CUDA box, PLUS two per-fix proofs:
- **Invariant deliberate-regression:** confirm `test_session_store_no_sync_mutators` goes RED when `_sync_open_session` is added WITHOUT the allowlist entry, then GREEN once allowlisted — the invariant doing its job (the §4 commitment).
- **GT RED→GREEN (RED-first):** GT0, GT-A, GT-B each confirmed RED against current code, then GREEN after B1. GT0 is RED today purely because of the `create_task`.

**Non-blocking PIs (absorb during implementation):**
- **PI-1 — drop the stale comment at `:1902`.** `# P0.7.2-SHIM: canonical-first — populate SessionStore BEFORE legacy dict` — P0.7.4 deleted the legacy `_active_sessions` dual-write; there is no legacy dict. Don't carry it forward onto the `_sync_open_session` call.
- **PI-2 — verify single production open-path.** Grep-confirm no production path calls `_session_store.open_session(...)` directly (only via `pipeline._open_session`); tests may (canary3 GT1b does). No new race even if not (last-writer-wins, same as today's double-`create_task`), but a clean single-path production invariant is worth verifying.
- **PI-3 — GT0 must exercise the cached path.** GT0's RED-today depends on `await ensure_history_loaded(...)` being a no-yield cache hit — set up GT0 with a returning (cached-history) speaker so the assertion captures the deterministic race, not an incidental timing win. GT-A/GT-B stub `voice_mod.identify` → strong known-speaker match, no face available (the camera-off shape).
