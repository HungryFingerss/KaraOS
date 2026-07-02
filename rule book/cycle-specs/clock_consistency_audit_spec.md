# Clock-Consistency Audit — Systemic `time.time()` / `time.monotonic()` Mismatch (pre-P1)

**Author:** Architect
**Date:** 2026-05-30
**Trigger:** Surfaced by the canary #2 bug-class sweep while verifying the vision-watchdog lag bug (`tests/pipeline_latency_fix_spec.md` §2 D1). The sweep found that **one** loud lag bug is the tip of a **systemic** clock-inconsistency class.
**Status:** CLOSED 2026-06-02 (architect Layer-3 verification of a pre-existing implementation, same inverted shape as the latency spec). The #2–#6 clock production already landed in `3a2360db` (Canary #3+#4, 2026-05-31); the parked working tree held the *completion* — the `core/audio.py` #4 split + the auto-derived paired-clock invariant + per-field behavioral tests + 2 ripple test fixes. #7 presence was **re-scoped out** (dict-woven into the reconciler routing clock; deferred to the SessionSnapshot/now-var fabric follow-up, allowlisted). This closure commits that completion after Layer-2 + Layer-3. See §8. Layer-4 (a leave-and-return + long-pause canary) remains the runtime proof and is the user's run.

---

## §0 — The finding

The Bundle-3 DEADLINE-MATH migration (`tools/migrate_time_monotonic.py`) converted elapsed-duration math from wall-clock (`time.time()`) to monotonic (`time.monotonic()`). **It was applied inconsistently across paired write/read sites — in BOTH directions** — leaving stored timestamps written with one clock and read with the other. Because `time.time()` ≈ 1.78 × 10⁹ and `time.monotonic()` ≈ 10²–10³ on a freshly-booted process, any subtraction across the two clocks is off by ~1.78 billion seconds.

**Only one instance manifests as user-visible lag:** the vision watchdog (polls every 5 s → broken staleness math → infinite restart loop → GPU thrash). That one is fixed for the *lag* in the latency spec (`:2594` one-liner). **The rest are latent correctness bugs** that a short single-person canary does not exercise but a longer / multi-person / leave-and-return canary will: broken re-greet, broken gallery self-update, broken KAIROS proactive timing, broken cloud-recovery timing.

This spec fixes the **whole class** and adds an invariant so it cannot regress.

> This is, again, the `Full-suite-run-is-the-universal-completeness-proof` lesson: three static layers (the migration tool, the P0.R3 tests, the Bundle-3 AST invariant) all passed the vision bug, and the existing AST invariant cannot even see most of these (see §2). **Only the live canary surfaced it.**

---

## §1 — Two directions, two detection problems

The mismatch occurs in two distinct shapes. They matter because the existing AST invariant (`tests/test_no_walltime_deadline_math.py`) only catches one of them.

**Direction A — `time.time()` appears in the elapsed-math** (write monotonic, read wall-clock):
```python
val = peek_X()                 # X was written with time.monotonic()
elapsed = time.time() - val    # time.time() − monotonic ≈ +1.78e9  (huge POSITIVE)
```
Result: "elapsed" reads as ~1.78 billion → any `elapsed >= threshold` is **always true**, any `elapsed < threshold` is **always false**. The vision watchdog and KAIROS-cooldown are this shape. The existing AST invariant *can* catch this **once strengthened** for the variable hop (see latency spec §3) — the `time.time()` is in the subtraction.

**Direction B — `time.monotonic()` minus a wall-clock-written value** (write wall-clock, read monotonic):
```python
store.touch_X(pid, time.time())          # WRITE: wall-clock
...
elapsed = time.monotonic() - peek_X()    # monotonic − walltime ≈ −1.78e9  (huge NEGATIVE)
```
Result: "elapsed" reads as ~−1.78 billion → any `elapsed >= threshold` is **always false**. `last_greeted` / `last_self_update` / `_yolo_last_ran` are this shape. **The existing AST invariant CANNOT catch this** — there is no `time.time()` in the subtraction (it's in the *store write*, a plain function-call argument). Catching Direction B requires **paired-write clock analysis**: connect each stored-timestamp field's write clock to its read clock and assert they match.

---

## §2 — Confirmed mismatches (all line numbers verified against the current tree)

| # | Field | WRITE clock + sites | READ clock + sites | Dir | User-visible impact |
|---|---|---|---|---|---|
| 1 | vision heartbeat | `time.monotonic()` — pipeline.py:2845 | `time.time()` — :2594 (`_staleness = _now - heartbeat`, :2596) | A | **Vision watchdog restart loop / GPU thrash (LAG).** Fixed for lag in latency spec D1. Listed here for completeness. |
| 2 | `last_greeted` | `time.time()` — :2313, :2316, :7278, :7464, :7647 (`touch_greeted(pid, time.time())`) | `time.monotonic()` — :2947, :7264, :7463 | B | **Re-greet cooldown never expires.** First greet works (default 0.0); after the first `touch_greeted` the cooldown gate `monotonic − walltime ≈ −1.78e9 < GREET_COOLDOWN` is permanently false → a known person who leaves and returns is **never re-greeted** within the process. |
| 3 | `last_self_update` | `time.time()` — :7244, :7254 (`touch_self_update(pid, time.time())`) | `time.monotonic()` — :7235 | B | **Gallery self-update permanently disabled** after the first. The `monotonic − walltime ≥ SELF_UPDATE_COOLDOWN` gate is always false → face embeddings stop refreshing → recognition quality degrades over time. |
| 4 | `last_user_speech_at`, `last_kairos_at`, `_tts_end_time` | mixed — `last_user_speech_at`/`last_kairos_at` `time.monotonic()` (pipeline.py:6720/6721/3524/3568/7671/7726/7770); `_tts_end_time` `time.time()` (core/audio.py:734/876) | `now = time.time()` — pipeline.py:3368, used at :3379 (`now − silence_baseline`) and :3380 (`now − peek_last_kairos_at()`) | A + B | **KAIROS proactive timing broken two ways:** (a) `_cooldown_elapsed = time.time() − last_kairos_at(monotonic) ≈ +1.78e9` → cooldown **always expired**, no rate-limit; (b) `silence_baseline = max(last_user(monotonic), tts_end(walltime))` → walltime always wins the max → the monotonic `last_user_speech_at` is **always discarded** → the P0.S7.3 silence-baseline fix is silently defeated. |
| 5 | `cloud_failed_at` | `time.time()` — pipeline.py:6074 (`_ct_failed_at = time.time()` → `transition_to_sick`) | `time.monotonic()` — :3345, :5790 | A/B | **Cloud SICK→OFFLINE timeout never fires:** `:5790` `elapsed = monotonic − walltime ≈ −1.78e9; if elapsed >= CLOUD_OFFLINE_TIMEOUT` is always false. `:3345` reports a garbage ~−1.78e9 "elapsed" to the watchdog. |
| 6 | `_yolo_last_ran` | `time.time()` — pipeline.py:7114 | `time.monotonic()` — :5668 | B | Stale-gate `monotonic − walltime < 30.0` always true → YOLO detections never treated as stale. **Low impact** (YOLO is disabled: `VISION_YOLO_ENABLED=False`), but same class — fix for consistency. |

### #7 presence — CONFIRMED (auditor-verified 2026-05-30, elevated from candidate per Auditor PI-2)

| # | Field | WRITE clock + sites | READ clock + sites | Dir | User-visible impact |
|---|---|---|---|---|---|
| 7 | presence `last_seen` / `last_recognized_at` | `time.time()` — upsert call-sites pipeline.py:7822, :8223, :8619; plus `_now_ext = time.time()` :8395 | `time.monotonic()` — :574 (scene-staleness, every turn) + :8425 (voice-routing face-stale); **wall-clock** — :8400 (`_now_ext − peek_last_recognized_at`) | B | **Routing-corrupting, EVERY TURN.** The two monotonic reads (:574/:8425) subtract a wall-clock-written value → −1.78e9; the :8400 read is wall-clock-consistent with the write but disagrees with :8425 on the SAME field. Scene-staleness + voice-routing face-stale are computed wrong on every turn. |

**The fix touches MULTIPLE write call-sites** (:7822/:8223/:8619 + the `_now_ext` read at :8395), not one — the original "candidate / defer to the audit" framing understated the surface and was itself an instance of the deferral-pattern undercount (`feedback_pass_2_grep_deferral_pattern`). Enumerated here at spec time so the developer has the full set. Decision: flip all writes + all reads (and `_now_ext`) to `time.monotonic()` (this is per-turn staleness math — monotonic is correct; verify presence is not displayed/persisted first per §3).

### Confirmed CONSISTENT (do NOT touch — listed so the developer doesn't "fix" a correct site)

- `last_silent_update`: write monotonic (:999), read monotonic (:995). ✓
- `last_face_seen`: write monotonic (:2865/:2867), reads monotonic (:3428/:7459/:8463). ✓
- vision frame ts: write monotonic (:2856), reads monotonic (:7065/:7565). ✓
- `core/cache_store.py`: write monotonic (:125), read monotonic (:87) — fixed at Bundle 5. ✓
- `core/state.py` cross-process IPC sites: intentionally wall-clock, `# WALLCLOCK:`-annotated. ✓ (Do not migrate.)

---

## §3 — The fix principle

**Rule:** every stored timestamp used for **elapsed-duration math** (cooldowns, staleness, deadlines, "X seconds since Y") uses `time.monotonic()` **on both the write and every read.** Wall-clock (`time.time()`) is reserved ONLY for timestamps that are **persisted to disk, sent cross-process, or displayed to a human**, and every such site carries a `# WALLCLOCK: <reason>` annotation.

**Per-field decisions (recommended — developer confirms each is not persisted/displayed before flipping):**

- **#2 `last_greeted`, #3 `last_self_update`, #6 `_yolo_last_ran`** → flip the **writes** to `time.monotonic()` (the reads are already monotonic). These are in-memory cooldowns; verify none is persisted or displayed (grep each field for serialization / log-formatting). If a field IS displayed (e.g. a health line "last greeted Xs ago"), that display must convert, or the field splits into a wall-clock display copy + a monotonic cooldown copy — flag to the architect if found.
- **#4 KAIROS** → flip the **read** `now = time.time()` (pipeline.py:3368) to `time.monotonic()`, AND flip `_tts_end_time` (core/audio.py:734/876) to `time.monotonic()` so the `max(last_user, tts_end)` baseline compares like-for-like. **Verify `_tts_end_time` has no wall-clock consumer** (grep it repo-wide) before flipping — if another site uses it as wall-clock, split it.
- **#5 `cloud_failed_at`** → decide: if it is only used for elapsed-math (the two reads at :3345/:5790), flip the **write** (pipeline.py:6074) to `time.monotonic()`. **Verify `cloud_failed_at` is not displayed** in any health/status line first (grep `cloud_failed_at` + `peek_cloud_failed_at`); if it is shown to a human, keep a wall-clock display value and add a separate monotonic value for the elapsed-math, or convert at the read.
- **#7 presence** → trace the `upsert_*` caller clock; make the write and all three reads (`:574`, `:8400`, `:8425`) use `time.monotonic()`; reconcile `_now_ext` at `:8400`.
- **#1 vision** → already covered by the latency spec D1 read-side fix (`:2594`). Do NOT double-fix.

**Decision discipline:** for each field the developer must state, in the closure report, "this field is {elapsed-math-only → monotonic} / {persisted|cross-process|displayed → wall-clock, annotated}" with the grep that proves it. No silent clock flip.

---

## §4 — Verification (how this gets proven)

Three layers, all required, per `Full-suite-run-is-the-universal-completeness-proof`.

### Layer 1 — Static + unit

1. **Strengthen the DEADLINE-MATH AST invariant** (`tests/test_no_walltime_deadline_math.py`) to catch **Direction A via variable indirection** — track names assigned from a bare `time.time()` call within a function scope, then flag those names used as the left operand of a `-` subtraction (this is the same strengthening the latency spec asks for; it catches #1 read-side, #4 KAIROS `now`, and any `time.time() - monotonic` site). Add forward + inverse self-tests.

2. **NEW paired-clock-consistency invariant** for **Direction B** (`tests/test_clock_consistency_paired.py`): the existing AST invariant cannot see Direction B (no `time.time()` in the subtraction — it's in the store write). This invariant **MUST AUTO-DERIVE its registry from the source, NOT hand-list the fields** (Auditor PI-1 — load-bearing).

   **Why auto-derive (do not skip this):** a hand-curated registry inherits the *exact* completeness hole that caused this bug — it checks only the fields someone remembered to list, missing both fields the manual sweep missed AND every future field. This is the recursion of this bundle's own lesson (`Full-suite-run-is-the-universal-completeness-proof`): a grep is bounded by its pattern; a hand-list is bounded by the author's recall. The auditor's `time.time()` sweep of `pipeline.py` alone found **~30 wall-clock sites** beyond the six confirmed here — e.g. `_dispute_ts` (:4267/:4472), `_conv_start_ts` (:7654), `captured_at` (:2937), multiple `now = time.time()` reads, the recognition `ts = time.time()` writes — **several of which are additional mismatches** (the presence `ts=` writes ARE bugs, now #7). A hand-listed registry enumerating only the original six would silently pass all of them.

   **The detector must structurally autodiscover the surface:** scan the in-scope tree for every stored-timestamp field — any name assigned from / passed to a setter as a bare `time.*()` call (the WRITE clock), and any `peek_*` / getter / field subtracted against a `time.*()` (the READ clock) — pair them by field name, and assert **write-clock == read-clock per field**, with a `# WALLCLOCK: <reason>`-annotated allowlist for the legitimate exceptions (cross-process IPC, persisted, displayed). A field that appears with two clocks and no annotation FAILS. New fields are caught automatically because nobody has to remember to register them.

   **Two layers, both required:**
   - **(a) the auto-derived structural invariant** above — the forward guard that catches what no one listed (this is the completeness mechanism; the word *auto-derived* is the whole point).
   - **(b) behavioral per-field tests** (§4 Layer 1 item 3) for the confirmed fields — write via the real setter using the real production clock + read via the real getter-subtraction + assert elapsed is sane (0 ≤ elapsed < small). These are the *runtime* proof for the known fields; (a) is the *structural* proof for the unknown ones.

   **Expected outcome:** running (a) repo-wide will likely surface MORE than the seven confirmed here. Every site it flags is either a real mismatch (fix it) or a legitimate wall-clock use (annotate it). The audit is not "fix the seven" — it is "make the invariant green," which by construction fixes the whole class.

3. **Per-field behavioral tests** for the user-visible ones — each must FAIL on the current code and PASS after the fix:
   - `last_greeted`: greet → advance the monotonic clock past `GREET_COOLDOWN` → assert re-greet is allowed (currently never allowed).
   - `last_self_update`: self-update → advance past `SELF_UPDATE_COOLDOWN` → assert next self-update allowed.
   - KAIROS: assert (i) the cooldown is respected (not always-expired), (ii) `silence_baseline` reflects `last_user_speech_at` when the user spoke after TTS (currently always discarded).
   - `cloud_failed_at`: simulate cloud failure → advance past `CLOUD_OFFLINE_TIMEOUT` → assert SICK→OFFLINE fires (currently never).

   **Why per-field behavioral tests are mandatory:** the existing P0.R3 vision tests were green while production was broken because they used `time.time()` on *both* sides — internally consistent, blind to the mismatch. Every new test here must use the **real production write/read clocks**, not a test-local consistent clock.

### Layer 2 — Full-suite gate

`pytest -q`, output shown, exact counts reported. Baseline 3795 passing / 0 failed; delta = the new clock tests. Any pre-existing failure surfaced is reported, not absorbed. (Note: the `last_greeted` / `last_self_update` fixes may flip the behavior some existing tests asserted around cooldowns — those tests, if any, must be checked: were they asserting the *broken* behavior? Fix the test to assert the *correct* behavior, and call it out in the closure report — this is the same "test encoded the bug" pattern as the latency spec D1.)

### Layer 3 — Architect deep re-verification (post-developer, pre-canary)

The architect re-reads every changed clock site against §2/§3, re-runs the paired-consistency registry to confirm zero remaining mismatches repo-wide, confirms each per-field decision has its grep-proof in the closure report, and confirms the new tests fail-on-revert.

### Layer 4 — Canary

A longer canary than #2: include a **leave-and-return** (walk away > `GREET_COOLDOWN`, come back → must be re-greeted), a **long pause** (trigger KAIROS, confirm it fires once on real silence and respects cooldown), and — if feasible — a cloud-failure simulation. These exercise the latent bugs a short canary cannot.

---

## §5 — Scope guards (OUT of scope)

- **Do NOT migrate the `# WALLCLOCK:`-annotated cross-process IPC sites** (`core/state.py`, `tools/factory_reset.py` state.json, `brain_agent.py` stored-in-DB expiry) — those are correctly wall-clock by design.
- **Do NOT touch the confirmed-consistent fields** listed in §2 (`last_face_seen`, `last_silent_update`, vision-frame ts, cache_store).
- **Do NOT change clock *semantics* of a field that is genuinely displayed/persisted** — if a field turns out to be shown to a human, split it rather than corrupting the display. Flag to the architect.
- **No "while I'm here" refactors** of the store classes beyond the clock fix.
- This spec does **not** re-fix the vision watchdog read-side (`:2594`) — that ships in the latency spec to fix the lag. This spec covers fields #2–#7.

---

## §6 — Acceptance criteria

1. The paired-clock-consistency invariant passes repo-wide — every elapsed-math timestamp field uses one clock on write + all reads (or is `# WALLCLOCK:`-annotated).
2. The strengthened DEADLINE-MATH invariant catches the Direction-A variable-indirection pattern (forward self-test fires).
3. Per-field behavioral tests for `last_greeted`, `last_self_update`, KAIROS, `cloud_failed_at` pass (and failed-on-revert).
4. Full suite green, 0 failed, counts shown; any "test encoded the broken cooldown" cases fixed + called out.
5. Canary: a known person who leaves > `GREET_COOLDOWN` and returns **is re-greeted**; KAIROS fires on real silence and respects its cooldown.
6. Each per-field clock decision documented with grep-proof in the closure report.

---

## §7 — Relationship to the latency spec

| | Latency spec (`pipeline_latency_fix_spec.md`) | This spec |
|---|---|---|
| Vision watchdog (#1) | **fixes the lag** (`:2594` read-side, one line) | references only — not re-fixed |
| Strengthened DEADLINE-MATH AST invariant | adds it (Direction A) | depends on it + adds the Direction-B paired-consistency invariant |
| `last_greeted`/`self_update`/KAIROS/`cloud_failed_at`/`yolo`/presence | NOT addressed (latent, not lag) | **fixes all (#2–#7)** |
| Concern | latency / seamless conversation | correctness / latent feature breakage |

Ship order: the **latency spec first** (it restores responsiveness — the user's immediate pain), this spec **immediately after** (it restores the latent-broken features before P1). Both run the same auditor → developer → architect-deep-reverify → canary loop.

---

## §8 — Closure record (architect, 2026-06-02)

Same inverted shape as the latency spec: the production already shipped, this closure is the architect's **Layer-2/3 verification + commit of the parked completion** (the lock layer + one production refinement + 2 ripple test fixes).

### Production state — verified against the committed tree
- **#2 `last_greeted`, #3 `last_self_update`** (dict-mediated `ConversationStore._last_greeted[pid]=ts` / `_last_self_update[pid]=ts`) — all `touch_greeted`/`touch_self_update` writes in pipeline.py are `time.monotonic()` (committed). The auto-derived paired invariant is *blind* to these (Subscript stores, not Attribute), so the **Part-A AST write-guard** in `test_clock_done_field_behavioral.py` is their only structural lock.
- **#4 KAIROS** — `pipeline.py:3455` read `now = time.monotonic()` (committed); silence baseline reads the monotonic companion via `getattr(_audio_mod, "_tts_end_time_monotonic", 0.0)` (the `0.0` default makes it safe without the parked audio.py). The **`core/audio.py` split** (parked production, committed here): `_tts_end_time` stays wall-clock for the echo-window consumer (`# WALLCLOCK:`-annotated), a new `_tts_end_time_monotonic` carries the KAIROS elapsed-math — the spec §3-#4 "split if there's a wall-clock consumer" path, taken correctly.
- **#5 `cloud_failed_at`, #6 `_yolo_last_ran`** — `_ct_failed_at = time.monotonic()` / `_yolo_last_ran = time.monotonic()` (committed). The paired invariant covers `cloud_failed_at` (store-mediated); the AST write-guard covers both.
- **#7 presence `last_seen`/`last_recognized_at` + `last_face_seen` — DEFERRED, not fixed here.** They are dict-woven into the reconciler routing clock (`persons_in_frame` → `_rc_now`), which the store-getter-mediated invariant cannot see. `_DEFERRED_ALLOWLIST` in `test_clock_consistency_paired.py` documents each with its sites; the inverse test fails if a stale entry lingers. Owned by the SessionSnapshot/now-var fabric follow-up.

### Lock layer — committed this closure
- `tests/test_clock_consistency_paired.py` — the **auto-deriving** Direction-B paired-clock invariant (Auditor-PI-1): builds the receiver→class map + setter/getter model from source, pairs write-clock vs read-clock per `(class, field)` with scope-local + getter-side variable-hop, gates on one consistent clock, allowlists only the deferred fabric. Inverse test prevents stale allowlist config.
- `tests/test_clock_done_field_behavioral.py` — Part A AST write-guard (the only structural lock for the dict-mediated greeted/self_update) + Part B runtime gate-logic proofs against the real production stores (re-greet / self-update / cloud-offline cooldowns open correctly with monotonic-consistent write+read).
- `tests/test_p0_s7_3_kairos_baseline.py` + `tests/test_p0_r6_heavy_worker_foundation.py` — **2 ripple test fixes that close latent committed-tree failures** (see below).

### Two latent committed-tree failures closed (stash-verified)
The #2–#6 production shipped in `3a2360db` but its matching test updates were parked, so HEAD carried 2 failures masked only by the parked working tree:
- `test_p0_r6_d3_anchor_1` — the latency-spec **D2 boot warmup** added a 5th `hw.run_heavy("adaface_embed")`; the anchor counts exactly 4. The fix excludes the warm call. (This is a #2/latency ripple folded in here per user direction.)
- `test_kairos_fires_after_threshold_from_tts_end` — the committed test seeded `_tts_end_time` (wall) while committed production reads `_tts_end_time_monotonic`; the fix seeds the monotonic companion. **Fail-on-revert proof:** stashing the test fix + `core/audio.py` made it fail with `Expected 'get_pending_question' to have been called` (KAIROS over-suppressed) — the genuine production reason.

### Layer-2 + Layer-3 — both PASS on the CUDA box
- **Layer-2:** full suite **3866 passed / 12 skipped / 10 xfailed / 0 failed** (330 s), full clock+latency lock layer collected, production net-zero.
- **Layer-3 fail-on-revert:** the paired invariant + the AST write-guard both fired when a committed write was reverted to `time.time()` — dict-mediated `touch_greeted` → AST guard (`:7819 ← time.time()`); store-mediated `cloud_failed_at` → **auto-derived** paired invariant (`PipelineStateStore._cloud_failed_at: writes=['wall'] reads=['mono']`, discovered from source). Restored net-zero. The audio.py-split + KAIROS read were proven by the KAIROS ripple stash-verify above.

### Scope handoffs
- **#7 presence + SessionSnapshot fabric** → the "SessionSnapshot / now-var timestamp fabric migration" follow-up (effort **#5**), which owns the dict-mediated reconciler routing clock. Allowlisted here; the inverse test forces the allowlist to be cleared when that follow-up lands.
- **Layer-4 canary** — a longer run than #2: leave-and-return (> `GREET_COOLDOWN` → must re-greet), long-pause (KAIROS fires once on real silence + respects cooldown), optionally a cloud-failure sim. The user's run.
