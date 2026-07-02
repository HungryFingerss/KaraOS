# Pipeline Latency & Conversation-Lag Fix — Combined Spec (Canary #2)

**Author:** Architect
**Date:** 2026-05-30
**Trigger:** Pre-P1 live canary #2 — user reported heavy conversation lag ("said hi 5 min ago", "pipeline too slow"). Full evidence in `terminal_output.md` (542-line run, 2026-05-30 11:44–11:48).
**Status:** CLOSED 2026-06-01 (architect Layer-3 verification of a pre-existing implementation). The production fixes D1/D2/D5a/D5b/D6 had already landed in commit `3a2360db` (Canary #3+#4 fixes, 2026-05-31 — the day after this spec was drafted), bundled rather than going through a separate auditor round. This closure commits the **golden-test lock layer** (the parked + untracked tests) after architect Layer-2 + Layer-3 verification. See §8 for the closure record. Layer-4 (live canary) remains the runtime proof and is the user's run.

---

## §0 — The verdict up front (answers the user's question)

The user asked: *is this the laptop, the GPU, or "everything running on one thread"?*

**Measured answer: none of those is the root cause.** The architecture is already decoupled correctly, and the lag is a small set of **specific bugs**, not a hardware limit and not a threading-model problem.

What the log proves about the threading model (so we do NOT chase a re-architecture):
- **The 18 brain agents do NOT block the conversation.** Extraction / autocompact / emotion / social-graph run as fire-and-forget background tasks (`[BrainAgent] Spawn (background)…`, log lines 183/185/240/294). Line 209: extraction took 2276 ms but ran *after* `Turn end` — the user never waited on it. (This decoupling was done in Session 110.)
- **Heavy GPU inference runs in separate subprocesses,** not the main thread: Whisper / ECAPA / AdaFace / pyannote each live in their own `ProcessPoolExecutor` worker (the P0.R6 arc).
- **More threads would not help** — Python's GIL means threads don't parallelize CPU/GPU work. The right model (single asyncio loop + subprocess workers for GPU + background tasks for the LLM agents) is already in place.

> **SCOPE GUARD (load-bearing):** This spec does **NOT** re-architect anything into threads. The decoupling already exists. Do not add threads for the agents or the pipeline. The fixes below are surgical.

### Measured per-turn latency (from the canary timestamps)

| Turn | User said | STT-complete → audio-out | Dominant cost |
|---|---|---|---|
| 0 | "Hi" | **~20 s** | Whisper subprocess **cold-load** (first STT 20,383 ms; later STTs 456–905 ms) |
| 1 | "tell me about you…" | **~30 s** | pyannote **cold-load** (~23 s) + 70B stream (~7 s) |
| 2 | "I'll call you Kara" | ~4.8 s | classifier 2.2 s + 70B 1.8 s |
| 3 | "your capabilities?" | ~10.5 s | 70B long stream |
| 4 | "knowledge examples?" | ~5.6 s | 70B |
| 5 | "highlight news today" | ~11.3 s | Tavily web search + 70B re-stream |
| 6 | "bye, shut down" | ~4.2 s | classifier 1.6 s + 70B 1.9 s |

The "5 minutes" feeling = the first two turns burned ~50 s on **cold-starts**, while the **vision watchdog restart loop thrashed the GPU underneath every turn** the whole session.

---

## §1 — Surface classification (be honest about what is a code fix vs a measurement)

Per the `Full-suite-run-is-the-universal-completeness-proof` doctrine: classify each surface before fixing.

| ID | Issue | Class | Action |
|---|---|---|---|
| **D1** | Vision watchdog restart loop (clock mismatch) | **CRITICAL BUG — code fix** | One-line fix + strengthen the AST invariant + new behavioral test |
| **D2** | First-turn cold-starts (Whisper/pyannote not warmed) | **CRITICAL — code fix** | Warm all heavy-worker pools at boot |
| **D3** | Classifier shadow on the critical path | **MEASURE + DON'T-REGRESS** | Re-measure post-D1; **no** behavior change to the gate |
| **D4** | 70B cloud latency | **MEASURE + DOCUMENT** | No code change; record options for a future spec |
| **D5** | Ollama dead + greeting silently tool-calls | **RELIABILITY — code fix + OPS** | Boot health-check warning + drop `tools` from greeting call |
| **D6** | Log/IO flood | **LOW — mostly a symptom of D1** | D1 removes the bulk; gate shadow diagnostics behind a flag |

**D1 and D2 are where the real seconds are.** D3/D4 are honest measurements (no blind fixes). D5/D6 are reliability + cleanliness.

---

## §2 — The fixes

### D1 — Vision watchdog clock mismatch (CRITICAL BUG)

**Root cause (VERIFIED in code):**
- The heartbeat is **written** with a monotonic clock: `pipeline.py:2845` →
  `loop.create_task(_pipeline_state_store.set_vision_heartbeat(time.monotonic()))`
- The watchdog measures staleness against the **wall clock**: `pipeline.py:2594-2597` →
  ```python
  _now = time.time()                                              # 2594  WALL CLOCK
  _heartbeat_at = _pipeline_state_store.peek_vision_heartbeat_at()  # 2595  MONOTONIC value
  _staleness = _now - _heartbeat_at                              # 2596  time.time() − time.monotonic()
  if _staleness < VISION_WATCHDOG_STALE_THRESHOLD_SECS:          # 2597  threshold = 30.0
      continue
  ```
- `time.time()` (~1.78 × 10⁹) minus `time.monotonic()` (seconds-since-boot, ~10²–10³) ≈ **1.78 billion**. That is `_staleness` on **every poll**, which is always ≫ 30 s → the watchdog cancels + respawns the vision task **every `VISION_WATCHDOG_INTERVAL_SECS` = 5.0 s for the entire session.**

**Evidence:** `terminal_output.md` shows `staleness=1778948850.2s` (= the Unix epoch in seconds) on every poll, and ~70 `[Vision] stale detected … restarting` / `[Vision] watchdog: restart success` pairs across the 4-minute run. The restart helper "succeeds" each time (the respawned loop writes a fresh monotonic heartbeat that *is* greater than `_prev_heartbeat` — see below), so the watchdog re-detects stale on the very next poll and restarts again. Infinite loop.

**Impact:** every 5 s the vision task is cancelled + respawned, re-running RetinaFace face-detection + AdaFace embed on the GPU, competing with the conversation's Whisper / ECAPA / pyannote / E5 inference. This is almost certainly why the local E5 classifier took **2182 ms** (log line 198) when it should be ~400 ms — GPU contention. It also churns the asyncio loop with constant task cancel/create, and floods the log.

**The fix (ONE LINE):**
```python
# pipeline.py:2594
_now = time.monotonic()        # was: time.time()
```

**Why this is correct:**
- Staleness is a pure **elapsed-duration** measurement ("how long since the last heartbeat") — the canonical DEADLINE-MATH case. `time.monotonic()` is the correct clock. There is no cross-process / persisted-to-disk reason for the watchdog `now` to be wall-clock.
- The restart helper is **already** monotonic-consistent and must NOT be touched: `pipeline.py:2777` reads the heartbeat (monotonic), `:2805` `_deadline = time.monotonic() + …`, `:2808` `peek_vision_heartbeat_at() > _prev_heartbeat` (monotonic > monotonic). Its heartbeat-advance check is fine. The bug is *only* line 2594.

**Load-bearing constraints (do NOT break):**
- Do **not** change the heartbeat write at `:2845` (already monotonic — correct).
- Do **not** change the restart helper (`:2777`, `:2805`, `:2808` — already monotonic — correct).
- Change **only** `:2594` *for the lag fix*.

> ### ⚠️ ADJACENT CRITICAL FINDING — this bug is NOT isolated (read before scoping)
>
> While verifying D1, the architect ran a repo-wide sweep for the bug class and found the Bundle-3 `time.monotonic()` migration was applied **inconsistently across the whole timestamp surface, in both directions.** D1 is the only instance that manifests as *lag* (the watchdog polls every 5 s, so the broken staleness math screams). **Seven paired write/read clock mismatches are confirmed** (auditor-verified 2026-05-30), and the auto-derived invariant is expected to surface more (~30 wall-clock sites in pipeline.py alone). The others are **latent correctness bugs** a longer / multi-person canary will surface:
> - `last_greeted` (writes wall-clock, reads monotonic) → **re-greet cooldown never expires** within a process.
> - `last_self_update` (writes wall-clock, reads monotonic) → **gallery self-update permanently disabled** after the first.
> - `last_user_speech_at` + `last_kairos_at` + `_tts_end_time` (KAIROS — `now=time.time()` vs monotonic writes) → **KAIROS cooldown always expired + the P0.S7.3 silence-baseline fix defeated.**
> - `cloud_failed_at` (writes wall-clock, reads monotonic) → **cloud SICK→OFFLINE timeout never fires.**
> - `_yolo_last_ran` (writes wall-clock, reads monotonic) → stale-gate always "fresh" (low — YOLO disabled).
> - presence `last_seen` / `last_recognized_at` → **CONFIRMED** (writes wall-clock @7822/8223/8619 + `_now_ext` @8395; reads monotonic @574/8425, wall @8400) → **routing corrupted on every turn**.
>
> **The `:2594` one-liner here fixes the lag.** The full systemic fix is a separate, focused effort: see the companion **`tests/clock_consistency_audit_spec.md`**. The architect recommends the clock-consistency audit be done as the **immediate next spec** (it is a pre-P1 correctness blocker), but it is intentionally NOT bundled into this latency spec so each gets a clean, focused auditor review.

---

### D2 — First-turn cold-starts: warm the heavy-worker pools at boot (CRITICAL)

**Root cause (VERIFIED in code):**
- `_warmup_models` (`pipeline.py:6575`) warms **ECAPA only** — its task list (`:6594-6601`) contains a single `_warm("ECAPA", voice_mod.load_speaker_embedder)`. Its own docstring (`:6580`) admits "covers ECAPA only post-P0.R6.Z".
- The run() pool warm-up (`:6874-6916`) calls `hw.get_or_create_pool("adaface_embed" / "whisper_transcribe" / "ecapa_embed" / "pyannote_diarize")`. **`get_or_create_pool` only spawns the subprocess; it does NOT load the model.** The model loads lazily on the **first** real `hw.run_heavy(...)` call. The comment at `:6800` *claims* "warm pyannote + ECAPA … so first-turn pays no cold-start cost" — **the log proves this claim false.**

**Evidence:** first STT = **20,383 ms** (cold Whisper subprocess load + first inference; subsequent STTs 456–905 ms). First diarize ≈ **23 s** (cold pyannote subprocess load; subsequent diarizes ~0.8 s, e.g. Turn 2). `[Warmup]` log shows only `ECAPA ready`.

**The fix:** after the 4 `get_or_create_pool(...)` calls in run() (`:6874-6916`), fire **one dummy `hw.run_heavy(...)` inference per pool** to force the lazy model load at boot, gathered in parallel, and **awaited before** `[Pipeline] All systems ready. Watching...`:

- `whisper_transcribe` — dummy ~1 s of silence (`np.zeros(16000, np.float32)`).
- `pyannote_diarize` — dummy ~2 s of silence (`np.zeros(32000, np.float32)`).
- `adaface_embed` — dummy face crop (worker's expected uint8 shape).
- `ecapa_embed` — dummy ~1.5 s audio (`np.zeros(24000, np.float32)`).

Crib the **exact** argument shapes from the existing real call sites so the dummy matches each worker's signature:
- Whisper: `pipeline.py:7167` (`hw.run_heavy("whisper_transcribe", …)`).
- AdaFace: `pipeline.py:2910` / `:3015` / `:7167` region (`adaface_embed`).
- ECAPA: `pipeline.py:7577` + `core/voice.py` ecapa embed call.
- pyannote: `core/voice.py::_diarize_pyannote()` `hw.run_heavy("pyannote_diarize", …)`.

Each dummy call wrapped in `try/except` (warm-up failure is non-fatal — mirror `_warmup_models`'s `_warm` helper). Log each: `[Warmup] {pool} pool warm — {x:.1f}s`.

**Why this is correct:** moves the 20 s + 23 s cold-loads from the user's first turn to the boot phase. Boot will take ~20–25 s longer (the cold-loads, overlapped in parallel via `asyncio.gather`, dominated by pyannote ~23 s) — **this is the intended trade:** the user waits a bit longer at boot once, instead of 40 s mid-first-conversation every session. Document the boot-time increase explicitly.

**Load-bearing constraints:**
- The warmup must **await** before "All systems ready" so the first turn is genuinely warm (do NOT background it — a backgrounded warm-up loses the race against a user who speaks 3 s after boot, which is exactly what happened in the canary).
- Parallelize via `asyncio.gather` so total boot cost ≈ the slowest single pool (~23 s), not the sum.
- Must tolerate a degraded pool (P0.R9 VRAM budget refusal can make `run_heavy` return `None`) — `try/except`, non-fatal.
- Do NOT remove the existing `_warmup_models` ECAPA warm or the E5 warm (`:6795`) — they cover the main-process loaders; D2 adds the **subprocess pool** warm on top.

---

### D3 — Classifier shadow on the critical path (MEASURE + DON'T-REGRESS — no code change)

**Root cause (VERIFIED):** for gated-tool turns (rename / shutdown), the pipeline awaits `_classify_intent_smart` (`pipeline.py:1262-1264`, routed via `_classify_intent_cached`) before the tool gate `_intent_allows` decides (`:4121-4124`). In **shadow mode** (current default), `_classify_intent_smart` returns the **LLM** classifier result (Together.ai, ~1.5 s) and also runs the **graph** classifier (local E5). Log: line 193 (tool proposed) → 198 (`classifier_graph latency 2182ms`) → 200 (classified) → 204 (TTS). The ~2.2 s is on the critical path for gated-tool turns.

**Disposition — this is a measurement, not a fix:**
1. Most of the graph 2182 ms is GPU contention from **D1**. After D1, re-measure; expect graph E5 to drop to ~0.4–0.6 s.
2. **Do NOT move the classifier off the critical path.** The classifier IS the gate authority (it fixed the Detroit/Kara false-rename bugs that the regex-only gate had). Reverting to regex-first to save latency **regresses gate quality** — explicitly out of scope.
3. The real structural win is the **graph-classifier PRIMARY cutover** (`CLASSIFIER_GRAPH_SPEC_2`): once shadow-divergence validation accumulates (the canary showed "0 divergences over 2 classifications" — insufficient data), flip to primary mode so the gate uses the **fast local graph (~0.4 s)** instead of the slow shadow LLM (~1.5 s). That is a **separate, already-planned effort**, gated on shadow data — NOT this spec.

**Verification for D3:** re-measure classifier latency in the post-D1 canary (expect graph E5 < 0.6 s; LLM shadow ~1.5 s residual). Document. No assertion of a behavior change.

---

### D4 — 70B cloud latency (MEASURE + DOCUMENT — no code change)

**Root cause (VERIFIED):** the brain stream is 3–10 s/turn (Together.ai network + inference on an ~8000-token prompt — log lines 189/246/299/380/448/517). Inherent to a cloud LLM.

**Disposition — no code change in this spec.** Honest framing:
- The ~8000-token prompt: Together.ai does **not** do prompt caching the way Anthropic does, so the full prompt is re-processed every call. This is the main lever, but trimming risks behavior regressions (every prompt block was added for a documented reason).
- Optional **future** levers (each a separate design decision, NOT here): (a) speculative TTS — start speaking sentence 1 while the rest streams (cuts *perceived* latency the most); (b) a smaller/faster model for simple turns (routing); (c) prompt trimming for non-gated turns.

**Verification for D4:** measure the residual brain-stream latency in the post-D1+D2 canary. This is the floor. If the user wants it lower, open a dedicated latency-optimization spec (speculative TTS is the highest-leverage candidate).

---

### D5 — Ollama reliability + greeting silently tool-calls (RELIABILITY)

This is **two** findings.

**D5a — Ollama is down (offline fallback dead system-wide).**
- **Root cause (VERIFIED):** Ollama at `localhost:11434` returns `500` (log lines 116-117). This breaks `_ask_offline_safe` (`pipeline.py:4993`, **8 call sites**) AND the greeting Ollama fallback. If the cloud ever goes SICK, **every** turn falls to a dead fallback.
- **Fix (two parts):**
  - **OPS (user/environment, not code):** ensure Ollama is running (`ollama serve`) with the model pulled (`ollama pull qwen2.5:7b`, matching `OLLAMA_MODEL` in `core/config.py`).
  - **CODE:** add a **boot-time Ollama health-check** — a single `ping_together`-style probe of `OLLAMA_URL` during the warmup phase that prints a **loud** warning if Ollama is unreachable, so the operator knows the offline fallback is dead *before* the cloud goes SICK. Example: `[Warmup] WARNING — Ollama unreachable at {OLLAMA_URL}; offline fallback DISABLED. Run 'ollama serve' + 'ollama pull qwen2.5:7b'.` Non-fatal (do not block boot).

**D5b — Greeting passes `tools`, model returns a tool-call, content is empty, silent fallthrough.**
- **Root cause (VERIFIED in code; ONE inference flagged below):** `generate_greeting` (`core/brain.py:3190`) tries the cloud first (`:3212-3234`) but passes `"tools": _API_TOOLS, "tool_choice": "auto"` (`:3224-3225`). The 70B can return a **tool call** instead of greeting content → `greeting = (… .get("content") or "").strip()` (`:3229`) is empty → `if greeting:` (`:3232`) is False → **silent fallthrough** to the Ollama path (`:3239`) with **no** "cloud failed" log → Ollama 500s → hardcoded template fallback (`:3257-3259`).
  - **INFERENCE TO CONFIRM (honest flag):** the log shows the Ollama-500 line (`localhost:11434`) **without** a preceding `[Brain] Greeting (cloud) failed … — trying Ollama` line (which `:3236` would print on a cloud *exception*). The most consistent explanation is the empty-content (tool-call) fallthrough at `:3232`. The developer **must confirm** by logging the raw cloud `choices[0].message` in a one-shot repro before declaring D5b fixed (do not fix-by-assumption).
- **Fix:** remove `"tools": _API_TOOLS` and `"tool_choice": "auto"` from the greeting cloud call (`:3224-3225`). A greeting never needs to call a tool; dropping them guarantees the model returns content. (If the empty-content path can still occur, also treat empty cloud content as a logged failure, not a silent fallthrough — developer's discretion, but the tools-removal is the primary fix.)

**Latency note:** D5 is a **reliability** finding, not a per-turn latency source (the greeting is one event and the fallback is instant). It is in scope because the canary surfaced it and because a dead offline fallback is a real hole before P1.

---

### D6 — Log / IO flood (LOW — mostly a symptom of D1)

**Root cause (VERIFIED):** the canary log is ~80% non-conversation noise:
- (a) `[Vision] stale detected … / watchdog: restart success` — **the D1 thrash**.
- (b) `[Vision] Jagan / none` + `[Vision] Person left frame` repeating while Jagan is clearly present (lines 113/124/138…) — partly a **D1 symptom** (the restart resets frame state, re-triggering "left frame").
- (c) `[VisionChannel-Shadow] divergence` every 5 s (`pipeline.py:3133-3188`, throttled by `VISION_SHADOW_INTERVAL_SECS`) — a Phase-2 dev diagnostic.
- (d) `[VoiceChannel-Shadow]` (`:8046`) + `[Reconciler-Shadow]` (`:8141`) — Phase-2 dev diagnostics.

**The fix:**
- (a)+(b): **resolved by D1** — fixing the restart loop stops the thrash and the spurious "left frame".
- (c)+(d): gate the three shadow-channel diagnostics behind a **`SHADOW_CHANNEL_LOGGING_ENABLED`** flag in `core/config.py` (default `False` for canary cleanliness; `True` during active Phase-2 shadow-rollout review). Do NOT delete the shadow comparisons — only gate their **print** statements.

**NOTE — possible real divergence behind the noise (flag, do not fix here):** the `[VisionChannel-Shadow]` divergence is *persistent* (`new_only=['jagan_edf1b1'] prod_only=[] prod_total=0`) — the new channel sees Jagan while production `_persons_in_frame` is empty. This is **likely a D1 symptom** (the restart loop clears `_persons_in_frame`). **After D1**, re-check whether the divergence resolves. If it persists post-D1, it is a genuine Phase-2 divergence warranting a **separate** investigation — NOT this spec.

---

## §3 — How this gets verified (the user asked for this explicitly)

Verification has three escalating layers; **all three are required** before the canary, per the `Full-suite-run-is-the-universal-completeness-proof` doctrine (no static layer can see the runtime; the live run is the only completeness proof).

### Layer 1 — Per-fix verification (static + unit)

**D1 (vision watchdog):**
1. **New behavioral test** — `tests/test_vision_watchdog_clock_consistency.py` (or extend `tests/test_p0_r3_vision_loop_watchdog.py`): set the heartbeat via the **real write path** (`set_vision_heartbeat(time.monotonic())`), then exercise the **watchdog staleness computation** (`_now - peek_vision_heartbeat_at()`), and assert `staleness < VISION_WATCHDOG_STALE_THRESHOLD_SECS`. This test **must FAIL on the current `time.time()` code and PASS after the fix.**
   - **Why a new test is mandatory:** the existing P0.R3 tests (`test_p0_r3_vision_loop_watchdog.py:114/171/199`) seed the heartbeat with `time.time()` on *both* sides — internally consistent, so they were **green while production was broken**. They are blind to the clock-mismatch by construction. They must be **supplemented**, not relied on.
2. **Strengthen the AST invariant** — `tests/test_no_walltime_deadline_math.py` missed D1 because it only catches *direct* `time.time() - X` (`:56-62`, requires `node.left` to be a literal `time.time()` call) and `*_deadline` assigns. It does NOT catch `now = time.time()` on one line + `now - X` on another (the variable hop). **Add a pattern:** within each function scope, track names assigned from a bare `time.time()` call, then flag those names used as the left operand of a `-` subtraction (unless `# WALLCLOCK:`-annotated). Add forward + inverse self-tests for the new pattern.
3. **Run the strengthened invariant across the whole in-scope set** (`pipeline.py` + `core/*.py` + `bootstrap/classifier/*.py` + `tools/*.py`) to **surface any OTHER instances** of this Bundle-3 monotonic-migration bug class — but **DISCOVER + DOCUMENT only; do NOT fix anything beyond #1 (`:2594`) in this spec.** Every other site the invariant surfaces is handed to the companion **`clock_consistency_audit_spec.md`**, which owns the whole-class fix (#2–#7 and any new sites). The AST-invariant strengthening is implemented **once, here**, and shared by both specs. Rationale (Auditor PI-3): a clean scope boundary — the latency spec restores *responsiveness* (fixes #1 only + builds the detector); the clock spec restores *correctness* (fixes the class). Without this boundary the two specs would double-own KAIROS's Direction-A `now = time.time()` (pipeline.py:3368, which the clock spec owns as #4).

**D2 (pool warmup):** source/AST test asserting the run() startup block fires a `hw.run_heavy(...)` warm for each of the four pools (`whisper_transcribe`, `pyannote_diarize`, `adaface_embed`, `ecapa_embed`) and that the warm is `await`ed before the "All systems ready" print.

**D5b (greeting):** (i) source test — the greeting cloud call in `core/brain.py::generate_greeting` does **not** pass `tools` / `tool_choice`; (ii) behavioral test — `generate_greeting` with a mocked cloud response returning non-empty content returns that greeting (no fallthrough to Ollama). Plus the developer's one-shot repro confirming the raw cloud-response inference (per the D5b honesty flag) — record the result in the closure report.

**D5a (Ollama health-check):** source test — boot warmup probes `OLLAMA_URL` and prints a warning on failure; behavioral test — health-check with a mocked-unreachable Ollama prints the warning and does not raise.

**D6 (log gating):** source test — the three shadow-channel print statements are gated by `SHADOW_CHANNEL_LOGGING_ENABLED`; default is `False`.

**D3 / D4:** no code, no unit test — measurement items (Layer 3).

### Layer 2 — Full-suite gate (the completeness proof)

Run the **complete** test suite end-to-end, **output shown**:
```
pytest -q
```
Report the exact pass/skip/xfail/fail counts from the actual run. **Anchor-subset + `--collect-only` are NOT a substitute** (this is the lesson that surfaced 2 latent Bundle-3 production bugs at Bundle 5; D1 is a *third* instance of that class). The suite must be green (baseline: 3795 passing, 16 skipped, 9 xfailed, 0 failed — net delta should be the new D1/D2/D5/D6 tests added, 0 failed). Any pre-existing failure surfaced must be reported, not silently absorbed.

### Layer 3 — Architect deep re-verification (post-developer, pre-canary)

The architect (me) re-verifies **before** the canary:
1. Re-read **every changed line** against this spec (D1 = exactly `:2594`; D2 = the warm block + the 4 dummy calls' shapes; D5b = `tools` removed; D5a = the probe; D6 = the flag gating). Confirm no load-bearing constraint was violated (heartbeat write + restart helper untouched; `_warmup_models` ECAPA + E5 warm untouched).
2. Confirm the strengthened AST invariant actually catches the variable-indirection pattern (read the new detector code + its self-tests).
3. Confirm the new behavioral tests fail-on-revert (spot-check: revert D1, the new test must fire).
4. Confirm the full-suite run-log is real (counts, 0 failed).

### Layer 4 — Live canary (the runtime proof — only this proves it works)

Fresh `python pipeline.py` + a short multi-turn conversation. Capture `terminal_output.md`. The architect re-builds the per-turn latency table from the new timestamps and checks the acceptance criteria (§5). Per D1's doctrine: **no static layer can see the runtime; the canary is the proof.**

---

## §4 — Scope guards (explicitly OUT of scope)

- **No thread re-architecture.** The asyncio + subprocess + background-task model is already correct (§0).
- **No 70B provider swap / no prompt trimming** (D4 is measure-only).
- **No classifier-off-the-critical-path change** (D3 — would regress gate quality).
- **No graph-classifier primary cutover** here (separate planned `CLASSIFIER_GRAPH_SPEC_2` effort, gated on shadow data).
- **No Phase-2 shadow-channel divergence-correctness fix** (D6 note — re-check post-D1; separate investigation if it persists).
- **Dashboard #1b host-mismatch** (`localhost` vs `127.0.0.1`) is **parked** by the user until canaries are complete — not in this spec.
- **No "while I'm here" refactors.** D1 is one line. Resist the urge to "clean up" the watchdog or the warmup beyond the spec.

---

## §5 — Acceptance criteria (concrete, measurable)

Post-fix canary must show:
1. **Zero** `[Vision] stale detected … restarting` lines after boot (at most one at boot before the first heartbeat lands). *(D1)*
2. **First-turn latency < ~2 s** for STT and < ~2 s for first diarize — i.e., the first "Hi" feels instant, not a 20–40 s wait. *(D2)*
3. **Warm-turn latency dominated by the 70B**, not by the classifier or GPU contention — graph E5 < ~0.6 s. *(D1 + D3 measurement)*
4. **Readable log** — conversation events visible, not buried in vision/shadow spam. *(D6)*
5. **Ollama status known at boot** — either Ollama responds, or a loud warning is printed. *(D5a)*
6. **Greeting uses the cloud** (real generated greeting, not the hardcoded template) when the cloud is up. *(D5b)*
7. **Full suite green**, 0 failed, with the run-log counts shown. *(Layer 2)*

---

## §6 — Doctrine note (why this canary mattered)

D1 is the **third** in-production instance of the Bundle-3 `time.monotonic()` migration bug class (after cache_store TTL and the enrollment-rename WALLCLOCK). It slipped past **three** independent static layers:
- the migration tool (changed the write to monotonic, missed the watchdog read-site),
- the P0.R3 behavioral tests (use `time.time()` on both sides — internally consistent, so green while production was broken),
- the Bundle-3 AST invariant (catches `time.time() - X` directly, but the `now = time.time(); now - X` variable hop evades all four patterns).

**Only the live run caught it.** This is the precise justification for (a) strengthening the AST invariant to close the variable-indirection blind spot, (b) adding a behavioral test that uses the *real* write path, and (c) keeping the canary as a hard gate. The canary-before-P1 decision found a 100%-of-session GPU-thrashing bug that 3795 green tests never noticed. That is the whole argument for not stacking the robotics layer on an unvalidated foundation.

---

## §7 — Suggested implementation order (developer)

1. **D1** (one line + strengthened invariant + new behavioral test) — highest leverage, smallest diff. Run the strengthened invariant repo-wide; fix any other instances it surfaces.
2. **D2** (pool warmup) — eliminates the first-turn cold-start.
3. **D5b** (greeting `tools` removal + confirm the inference) then **D5a** (Ollama boot health-check).
4. **D6** (shadow-logging flag gating).
5. **D3 / D4** — measurement only; record findings in the closure report (no code).
6. Full-suite run (Layer 2), then hand back for architect deep re-verification (Layer 3) → canary (Layer 4).

---

## §8 — Closure record (architect, 2026-06-01)

This spec closed **inverted** from the normal cycle: the production fixes were already implemented and committed (bundled into the Canary #3+#4 commit `3a2360db`, 2026-05-31) before the formal auditor round happened. This closure is the architect's **Layer-1/2/3 verification of that pre-existing implementation plus the commit of the golden-test lock layer** — turning "the code is shaped right" into "the suite proves it works and a regression can't slip back in."

### Production state — verified line-by-line (all in `3a2360db`, working tree clean)
- **D1** `pipeline.py:2680` — `_now = time.monotonic()` (blame: `3a2360db`). The staleness read is monotonic; the heartbeat write (`:2931`) + restart helper (`:2863`/`:2894`) were already monotonic and untouched.
- **D2** `pipeline.py:6696` `_warm_heavy_worker_pools` — fires a real `hw.run_heavy(...)` dummy inference on all 4 pools (adaface/whisper/ecapa/pyannote) with VERBATIM-cribbed arg shapes, `asyncio.gather`-parallel, per-pool `try/except`, **awaited at `:6990` before** `[Pipeline] All systems ready` (`:7007`). Not the no-op `get_or_create_pool` the spec warned against.
- **D5a** `pipeline.py:6996-7005` — `ping_ollama()` boot probe + LOUD `Ollama unreachable` warning, non-fatal.
- **D5b** `core/brain.py:3214 generate_greeting` — cloud call carries **no** `tools`/`tool_choice`; empty cloud content is a **logged** failure (`:3264`), not a silent fallthrough.
- **D6** `SHADOW_CHANNEL_LOGGING_ENABLED` (config + pipeline + reconciler) — the 3 shadow divergence prints (`:3270` / `:8219` / `:8317`) gated behind the flag (default `False`); the comparisons still run.

### Lock layer — committed this closure (test/spec-only)
- `tests/test_no_walltime_deadline_math.py` (+192) — the Direction-A **variable-hop** AST detector (`_find_variable_hop`, scope-local) + 4 self-tests + a **non-gating** repo-wide `xfail` discovery. Kept OUT of the hard gate (`_find_violations`) on purpose: the clock-consistency audit (`clock_consistency_audit_spec.md`) owns the site fixes and later promotes variable-hop into the gate + removes the xfail.
- `tests/test_vision_watchdog_clock_consistency.py` (D1 behavioral — drives the REAL `_vision_watchdog_loop` via the REAL monotonic write path) + `tests/test_pipeline_boot_warmup.py` (D2) + `tests/test_greeting_and_ollama_health.py` (D5a+D5b) + `tests/test_shadow_channel_logging_gate.py` (D6).

### Layer-2 (completeness) + Layer-3 (non-vacuity) — both PASS on the CUDA box
- **Layer-2:** full suite **3866 passed / 12 skipped / 10 xfailed / 0 failed** (378 s), lock layer collected, production tree net-zero. The variable-hop discovery `xfail` surfaces **43** Direction-A clock-debt sites for the clock spec; the fixed watchdog `:2680` is correctly **absent**.
- **Layer-3 fail-on-revert (5/5, each RED for the production reason, restored net-zero):**
  - D1 → revert `:2680`→`time.time()` → behavioral test fired: "spuriously detected staleness **9x**", `staleness=1778948842.2s` (the `time.time() − time.monotonic() ≈ 1.78e9` GPU-thrash bug).
  - D5b → re-add `tools` → AST json-key check fired ("must NOT include a `tools` key").
  - D2 → remove the warm `await` → ordering check fired ("must `await _warm_heavy_worker_pools()`").
  - D5a → remove the `ping_ollama()` call → boot-health check fired ("must call ping_ollama() at boot").
  - D6 → un-gate one shadow print → AST gating check fired ("print at line 3269 is NOT gated").

### Scope handoffs (unchanged from §2/§3)
- The **43** Direction-A variable-hop sites belong to `clock_consistency_audit_spec.md` (#1) — fixed/annotated there, then variable-hop is promoted into the hard gate. The detector + discovery `xfail` ship here.
- D3/D4 are measurements for the Layer-4 canary (no code). D5b's raw-cloud-tool-call inference + first-turn latency are runtime facts the canary records.

### Remaining
- **Layer-4 live canary** — the user's `python pipeline.py` run; acceptance criteria in §5. Only the runtime proves the lag is gone.
- This closure subsumes the separately-listed greeting/ollama-health effort (it IS D5).
