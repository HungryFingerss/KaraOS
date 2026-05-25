# P0.R2 Phase 0 audit — Proactive CPU-EP fallback + provider-state-machine + CUDA-retry timer + banner UX

**Status:** DRAFT 2026-05-23 — pending auditor review.

**Pre-audit framing (parent `complete-plan.md:720-722`):**

```
### P0.R2 — No CPU fallback path

**Fix:** at startup, build CPU-EP sessions alongside CUDA. On CUDA failure:
switch active provider for next N requests; banner; retry CUDA every M minutes.
```

**Phase 0 outcome:** Pre-audit framing PARTIALLY ACCURATE per grep. The premise's "No CPU fallback path" is REFINED post-P0.R1: AdaFace has LAZY CPU fallback shipped at P0.R1 (1st instance of `Pre-audit-quantifier-precision-refined-by-grep` 2026-05-23); buffalo_l face detector + AdaFace boot-hard-fail path still have NO fallback (the genuine gaps). Real cycle with MEDIUM-band scope; 5 D-decisions; builds on P0.R1's lazy fallback infrastructure.

**Quantifier-precision banking:** This is the **2nd instance of `Pre-audit-quantifier-precision-refined-by-grep`** (architect-memory observation banked at P0.R1 Phase 0). Same family-shape: pre-audit's quantifier ("No CPU fallback path") overstated coverage post-P0.R1; grep refines to precise subset (2 of 3 sites still gap). Pattern recurs once. Toward 5+ instances for potential elevation.

---

## §1. ONNX CUDA-only session-construction inventory (Pass-1 grep)

Grep `CUDAExecutionProvider|CPUExecutionProvider|providers=|get_available_providers` across `core/*.py`:

| File:line | Caller | P0.R1 CPU fallback status | P0.R2 D-decision |
|---|---|---|---|
| `core/vision.py:184` | `FaceDetector.__init__()` — `insightface.app.FaceAnalysis(name='buffalo_l', allowed_modules=['detection'], providers=['CUDAExecutionProvider'])` | **NO fallback** (CUDA-only) | D2 |
| `core/vision.py:321-326` | `FaceEmbedder.__init__()` — `RuntimeError("CUDAExecutionProvider not available")` boot-hard-fail | **Boot-time fail-hard** | D3 |
| `core/vision.py:327` | `FaceEmbedder._session` — `ort.InferenceSession(model_path, providers=["CUDAExecutionProvider"])` at startup | CUDA primary; lazy CPU fallback per P0.R1 D1 | D1 (proactive migration) |
| `core/vision.py:333` (P0.R1) | `self._cpu_session: "ort.InferenceSession | None" = None` (lazy slot) | LAZY (built on first failure) | D1 (eliminates lazy build) |
| `core/vision.py:350-356` (P0.R1) | `embed()` lazy CPU-EP construction on RuntimeError | LAZY (P0.R1 D1) | D1 (refactor to use proactive `_cpu_session`) |

---

## §2. Grep-verified findings

### §2.1 Load-bearing findings — 3 distinct gap shapes post-P0.R1

**Gap 1 (buffalo_l face detector — `core/vision.py:184`):** Entirely CUDA-only via `insightface.app.FaceAnalysis(providers=['CUDAExecutionProvider'])`. CUDA OOM during face detection crashes the entire detection path. No P0.R1-equivalent lazy fallback. Architecturally NEW gap not covered by P0.R1.

**Gap 2 (AdaFace boot-hard-fail — `core/vision.py:321-326`):** Explicit `if "CUDAExecutionProvider" not in available: raise RuntimeError(...)` at FaceEmbedder construction. Pipeline boot crashes if CUDA missing entirely (e.g., CPU-only laptop, broken NVIDIA driver, CUDA library version mismatch). NO graceful degradation; user gets RuntimeError stack trace instead of a working CPU-only pipeline.

**Gap 3 (AdaFace embed() lazy → proactive — P0.R1 D1):** Lazy build at first CUDA failure costs ~1s latency on the first failed call. Proactive build at startup eliminates the latency penalty + makes the provider-state-machine simpler (CPU session always ready, just switch active reference).

### §2.2 P0.R1 lazy fallback contract preserved

D1 of P0.R2 refactors P0.R1's `_cpu_session = None` lazy slot into `_cpu_session = ort.InferenceSession(...)` proactive construction at `FaceEmbedder.__init__()`. The `embed()` try/except wrap stays — fallback semantic unchanged from caller's perspective; only the build-timing shifts from "on first failure" to "at startup". Plan v1 must verify P0.R1's 4 D1 anchors stay green post-D1 refactor.

### §2.3 Provider-state-machine architecture

Parent stub specifies "switch active provider for next N requests" + "retry CUDA every M minutes". This requires a STATE MACHINE tracking active provider globally. Architect lean: place in new module `core/vision_provider_state.py` with:

```python
# Sketch (subject to Plan v1 refinement)
_active_provider: Literal["cuda", "cpu"] = "cuda"
_cpu_requests_remaining: int = 0
_cpu_switch_at: float | None = None  # timestamp of last cuda→cpu switch

def record_cuda_failure() -> None:
    """Called by embed/detect on RuntimeError catch; switches active to cpu for VISION_CPU_SWITCH_N_REQUESTS."""

def record_success(provider: Literal["cuda", "cpu"]) -> None:
    """Called on successful inference; decrements counter; restores cuda on N exhausted."""

def get_active_provider() -> Literal["cuda", "cpu"]:
    """Read by FaceEmbedder/FaceDetector to route inference."""

def maybe_retry_cuda(now: float) -> None:
    """Called by _health_log_loop every M minutes; attempts CUDA test inference if active=cpu and elapsed > VISION_CUDA_RETRY_M_MINUTES."""
```

State machine is small (~50-80 LOC) + testable in isolation. D4 ships this module.

### §2.4 Banner UX architecture

Two surfaces:
- **Boot log**: `[Vision] CUDA primary + CPU fallback both built (graceful degradation ready)` at FaceEmbedder/FaceDetector construction OR `[Vision] CUDA unavailable; running CPU-only` at boot if CUDA missing.
- **Health log** (via `core/health.py::format_health_line`): emit `vision_provider=cpu` field when active provider is CPU; absent when active=cuda (mirrors existing `kuzu=degraded` conditional emit pattern).

NO dashboard surface in P0.R2 scope (dashboard `vision_provider` field via state.json would require P0.S2 extension — banked as P0.R2.X if operator pain point emerges).

---

## §3. Out-of-scope

1. **Smart-Turn CPU fallback** — different failure-mode shape (returns 0.0 on failure, doesn't need a CPU session). Banked as P0.R-future if neural-turn-end-on-CPU becomes operator pain point.
2. **MiniFASNet anti-spoof** — PyTorch (not ONNX). Different framework; out of P0.R2 scope.
3. **Whisper STT + Kokoro TTS** — library-internal sessions (faster-whisper + kokoro_onnx wrap session.run internally). Can't wrap at our layer cleanly.
4. **Dashboard `vision_provider` field via state.json** — requires P0.S2 dashboard auth gate extension. Banked as P0.R2.X.
5. **CUDA OOM root-cause diagnostic** — P0.R2 closes the crash-surface but doesn't diagnose WHY CUDA OOM happened (memory pressure from concurrent inference, leaked tensors, etc.). Banked as separate observability spec.

---

## §4. D-decisions (5 D-decisions, MEDIUM-band)

### D1 — AdaFace lazy → proactive CPU session
**File:** `core/vision.py::FaceEmbedder` (~15 LOC).
**Edits:**
1. `__init__()` — replace `self._cpu_session: "ort.InferenceSession | None" = None` (P0.R1 D1 lazy slot) with `self._cpu_session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])` at startup. Log `[Vision] AdaFace CPU fallback session built (proactive at startup)`.
2. `embed()` — remove the lazy `if self._cpu_session is None: build` block from P0.R1; the proactive `_cpu_session` is always non-None. Try/except wrap + log shape from P0.R1 stays.

### D2 — buffalo_l face detector CPU fallback
**File:** `core/vision.py::FaceDetector` (~30 LOC).
**Edits:**
1. `__init__()` — build TWO `FaceAnalysis` instances:
   - `self._app_cuda = FaceAnalysis(name='buffalo_l', allowed_modules=['detection'], providers=['CUDAExecutionProvider'])` (primary)
   - `self._app_cpu = FaceAnalysis(name='buffalo_l', allowed_modules=['detection'], providers=['CPUExecutionProvider'])` (fallback)
2. `detect()` — route via provider-state-machine: `app = self._app_cpu if _vision_provider_state.get_active_provider() == "cpu" else self._app_cuda`. Wrap `app.get(frame)` in try/except; on RuntimeError catch, call `_vision_provider_state.record_cuda_failure()` + retry with `self._app_cpu`.

### D3 — AdaFace boot-hard-fail → graceful degradation
**File:** `core/vision.py::FaceEmbedder.__init__()` (~10 LOC).
**Edits:**
1. Remove the `RuntimeError("CUDAExecutionProvider not available")` raise at lines 321-326.
2. When `"CUDAExecutionProvider" not in available`: log `[Vision] CUDA unavailable; AdaFace running CPU-only` + build CPU-only session (`self._session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])`). Skip the proactive `_cpu_session` build since CUDA isn't available anyway (`_cpu_session = _session` to satisfy the embed() fallback contract).
3. Sync state-machine to `active_provider="cpu"` permanently (no CUDA-retry timer when CUDA is structurally unavailable).

### D4 — Provider-state-machine module
**File:** NEW `core/vision_provider_state.py` (~80 LOC).
**Module-level state:** `_active_provider`, `_cpu_requests_remaining`, `_cpu_switch_at`.
**Functions:** `record_cuda_failure()`, `record_success(provider)`, `get_active_provider()`, `maybe_retry_cuda(now)`, `reset_for_tests()`.
**Config additions** (`core/config.py`):
- `VISION_CPU_SWITCH_N_REQUESTS: int = 100` (stay on CPU for N requests after CUDA failure)
- `VISION_CUDA_RETRY_M_MINUTES: float = 5.0` (retry CUDA every M minutes when active=cpu)
**Wiring in pipeline.py:** `_health_log_loop` calls `_vision_provider_state.maybe_retry_cuda(time.time())` after the existing health-snapshot work.

### D5 — Banner UX (boot log + health log)
**File:** `core/health.py::format_health_line` (~5 LOC) + boot log in `core/vision.py` (~3 LOC).
**Edits:**
1. Boot log line at `FaceEmbedder.__init__()` + `FaceDetector.__init__()` post-construction: `[Vision] CUDA primary + CPU fallback both built (graceful degradation ready)` OR `[Vision] CUDA unavailable; running CPU-only` (D3 path).
2. `format_health_line()` — conditional emit `vision_provider=cpu` field when `_vision_provider_state.get_active_provider() == "cpu"`. Absent emit when active=cuda (mirrors existing `kuzu=degraded` conditional pattern at `core/health.py:format_health_line`).

---

## §5. Cross-spec impact analysis

| Cross-spec | Interaction with P0.R2 | Disposition |
|---|---|---|
| **P0.R1** (lazy CPU fallback for AdaFace) | D1 refactors P0.R1's lazy build into proactive at-startup; P0.R1's 4 D1 anchors must stay green post-refactor | Plan v1 Pass-2 grep verifies P0.R1 anchor compatibility |
| **P0.S1** (anti-spoof) | Anti-spoof calls FaceEmbedder.embed() + FaceDetector.detect(); D1+D2+D3 fallback transparent | Architect-side test: P0.S1 50 tests stay green |
| **P0.5** (FAISS+SQL atomicity) | Embedding output flows to add_embedding(); None return per P0.R1 already handled | No interaction concern |
| **P0.S2** (dashboard auth) | NO dashboard surface in P0.R2; future P0.R2.X may add via state.json | Banked for later |
| **P0.R3** (watchdog on _background_vision_loop) | Downstream — if both CUDA + CPU fail, vision degraded; P0.R3's watchdog needs to detect this | Banked; P0.R3 may need P0.R2's state-machine API |
| **P0.R6** (process pool executor) | Future cycle moves heavy ML to process pool; provider-state-machine would live in worker process | Banked; P0.R2 stays single-process compatible |
| **Health log + disk monitor** (Wave 5 Items 19+20) | `format_health_line` already has conditional emit pattern; D5 mirrors it | Clean integration |

---

## §6. Pre-mortem (10 failure modes)

1. **CPU EP not available in onnxruntime install** — D1/D2 CPU session construction fails at startup; pipeline boots with vision fully degraded. Mitigation: try/except around the CPU session construction at startup + warn + continue with CUDA-only (pre-P0.R2 behavior). Operator alerted via boot log.
2. **Memory pressure when both CUDA + CPU sessions resident** — ~80MB extra for AdaFace CPU + ~200MB for buffalo_l CPU = ~280MB total. Documented limitation; on memory-constrained devices (Jetson Orin 32GB has headroom; lower-end hardware may not), banked as known cost.
3. **CPU embedding numerical drift vs CUDA** — same ONNX model weights + same preprocessing; numerically equivalent within float32 precision. Recognition threshold tolerance absorbs any drift well under 1%.
4. **CUDA OOM during startup CPU session build** — rare but possible (CUDA-OOM during CPU build doesn't make sense; this would be a memory pressure issue). Build CPU session FIRST then CUDA in __init__() to isolate.
5. **Provider-state-machine race condition** — concurrent embed() calls + concurrent detect() calls + _health_log_loop's maybe_retry_cuda all read `_active_provider`. Use `threading.Lock` around state writes (matches `core/state.py` P0.11 atomic-replace pattern). Reads are GIL-protected.
6. **CUDA-retry timer fires DURING ongoing CUDA failure** — health-log-loop calls maybe_retry_cuda every 5 min; if CUDA is still broken, the retry attempt itself crashes. Mitigation: maybe_retry_cuda wraps the test-inference in try/except; on failure, stays active=cpu + resets timer.
7. **N-request counter wraps to negative** — `_cpu_requests_remaining -= 1` after N failures could go negative; mitigation: `_cpu_requests_remaining = max(0, ...)` clamp.
8. **buffalo_l InsightFace API change** — `FaceAnalysis(providers=[...])` accepts provider list per current API; future insightface release might change signature. Mitigation: pin insightface version in requirements; Plan v1 verifies current API.
9. **D3 boot-graceful-degradation breaks `### Architect-reads-production-code-before-sign-off` test fixtures** — some tests mock CUDA via boot-hard-fail; removing the RuntimeError changes test expectations. Mitigation: Plan v1 §1 Pass-2 grep enumerates all tests that mock the boot-hard-fail path.
10. **Banner UX conflicts with health log multi-line format** — `format_health_line` returns single ≤200-char line. Adding `vision_provider=cpu` field conditionally must stay within 200-char budget. Mitigation: conditional emit only when CPU active (rare; budget unused most of the time).

---

## §7. Multi-direction invariant trace

### D1 forward invariant
After D1: `FaceEmbedder.__init__()` builds BOTH CUDA + CPU sessions at startup. `_cpu_session` is non-None from `__init__` onwards.

### D1 inverse invariant
After D1: no code in `embed()` constructs `_cpu_session` lazily. Future refactor that re-adds `if self._cpu_session is None: build` would fail D1 source-inspection.

### D2 forward invariant
After D2: `FaceDetector.__init__()` builds BOTH `_app_cuda` and `_app_cpu`. `detect()` routes via `_vision_provider_state.get_active_provider()`. CUDA OOM during detect → state-machine records failure + retries with CPU app.

### D2 inverse invariant
After D2: no bare `self._app.get(...)` call in detect() (only routed-via-state-machine calls).

### D3 forward invariant
After D3: `FaceEmbedder.__init__()` does NOT raise on CUDA-unavailable; builds CPU-only sessions. Pipeline boots successfully with vision degraded.

### D3 inverse invariant
After D3: no code path in FaceEmbedder.__init__() raises `RuntimeError("CUDAExecutionProvider not available")` (must be a log + CPU-only path).

### D4 forward invariant
After D4: `core/vision_provider_state.py` exists with module-level state + 5 public functions. Pipeline `_health_log_loop` calls `maybe_retry_cuda()` every cycle.

### D4 inverse invariant
After D4: no FaceEmbedder/FaceDetector code accesses `_active_provider` directly; all routes through state-machine API.

### D5 forward invariant
After D5: boot log emits `[Vision] CUDA primary + CPU fallback both built` OR `[Vision] CUDA unavailable; running CPU-only`. Health log conditionally emits `vision_provider=cpu` field when active=cpu.

### D5 inverse invariant
After D5: when active=cuda, health log does NOT emit `vision_provider` field (silent default; mirrors `kuzu=degraded` pattern).

---

## §8. Open questions for auditor (5)

- **Q1 — Bundle vs split:** 5 D-decisions in single cycle OR split into P0.R2a (D1+D2+D3 proactive sessions) + P0.R2b (D4+D5 state machine + banner)? **Architect lean: 5 D-decisions in single cycle.** State machine is small (~80 LOC); retry timer piggybacks on existing _health_log_loop; banner is 1-2 lines. Splitting would be over-cautious. MEDIUM-band cycle vs P0.R1's SMALL-band.

- **Q2 — Provider-state-machine scope:** global "active provider" flag (single state across all ONNX paths) vs per-session (each FaceEmbedder/FaceDetector instance has own state) vs per-tool (recognize vs add_embedding routed differently)? **Architect lean: global flag.** Simplest; matches parent stub's "switch active provider" singular framing; one source-of-truth easier to reason about + test.

- **Q3 — Retry timer architecture:** own background asyncio task (~5min interval) vs piggyback on existing `_health_log_loop` (also 5min)? **Architect lean: piggyback on `_health_log_loop`.** Avoids spawning extra background task; same cadence; cheaper; matches existing background-loop pattern.

- **Q4 — Banner UX scope:** boot log + health log only, OR dashboard surface via state.json `vision_provider` field? **Architect lean: boot log + health log only.** Dashboard surface = P0.S2 extension; deferred to P0.R2.X if operator pain point emerges.

- **Q5 — "N requests" semantics:** counter-based switch back to CUDA after N successful CPU requests? OR time-based (stay on CPU for M minutes regardless of request count)? OR counter+timer hybrid (whichever fires first)? **Architect lean: counter + timer hybrid.** High-traffic: counter exhausts → retry CUDA. Low-traffic / idle: timer fires → retry CUDA. Belt-and-suspenders for both cycle shapes. Configurable via `VISION_CPU_SWITCH_N_REQUESTS` (counter) + `VISION_CUDA_RETRY_M_MINUTES` (timer).

---

## §9. Q5 baseline estimation

**Architect estimate: 9 anchors** (D1=2 + D2=2 + D3=1 + D4=3 + D5=1) mid 9.

Per ±15% band: [7.65, 10.35]. **Interpretation question for auditor:**
- **Strict NARROW (P0.B6/P0.S8/P0.S9/P0.R1 precedent):** only EXACT 9 qualifies ON-TARGET; 8 or 10 = SLIGHT-DRIFT; ≤7 or ≥11 = FALSIFICATION.
- **Inclusive ±15% (P0.B5 precedent at mid 9):** 8/9/10 all qualify ON-TARGET; ≤7 or ≥11 = FALSIFICATION.

Architect lean for the question itself: **strict NARROW per the more recent locked precedents** (4 consecutive cycles applied strict NARROW at mid 4 / 5 / 7 / 4 respectively). P0.B5's looser interpretation was a one-off architect framing; subsequent cycles have all applied strict. Recommend Plan v1 §4 honest-count commitment table use strict NARROW interpretation.

If auditor adjusts to inclusive ±15% per P0.B5 precedent, Plan v1 §4 table updates accordingly. Banking: this is an `Auditor-adjudication-drift-clarified-by-architect` 4th instance candidate IF auditor accepts strict NARROW + ratifies as the canonical interpretation (would close the prior P0.B5 looser-reading drift).

---

## §10. Sub-pattern A status

**Sub-pattern A NOT triggered at P0.R2.** Pre-audit premise "No CPU fallback path" is partially accurate post-P0.R1 (1 of 3 sites has lazy fallback; 2 still gap). Quantifier-precision refinement (banked as `Pre-audit-quantifier-precision-refined-by-grep` 2nd instance) — distinct from sub-pattern A wrong-premise (which is about WHAT or WHETHER, not quantifier modifier).

**`### Phase-0-catches-wrong-premise` count holds at 12.**

---

## §11. Twin-filename pitfall check (16th preventive event candidate)

Pass-2 grep at audit drafting:
- `tests/p0_r2_*.md` — zero pre-existing files. ✓ Clean disambiguation.
- `core/vision_provider_state.py` (D4 NEW file) — zero pre-existing files at `core/vision_provider*.py` pattern. ✓ Greenfield.

16th preventive event of `### Twin-filename-pitfall-prevention` (after P0.R1's 15th at closure 2026-05-23). Doctrine instance count holds at 7 per locked enumeration rule.

---

## §12. Verdict + handoff

**Architect prediction:** Plan v1 absorbs all 5 architect leans (Q1-Q5) proactively; auditor returns 0 precision items at Plan v1 review (**caveat: per `Zero-precision-items-pre-closure-predictions-blocked` 1-candidate observation banked at P0.R1, 2 consecutive Plan v1 reviews were blocked by auditor PI; P0.R2 Plan v1 may extend this pattern to 3 consecutive, formalizing the operational rule per `Zero-precision-items-pre-closure-predictions-blocked` watch criteria**).

**Discipline counts at Phase 0 close (per locked +1-per-artifact convention):**
- Spec-first review cycle: 66 → 67
- Strict-industry-standard mode: 56 → 57 applications
- `### Grep-baseline-before-drafting`: 23 → 24
- Spec-time grep-verification: 33 → 34
- Cross-cycle-handoff transparency precedent: 29 → 30
- `### Twin-filename-pitfall-prevention`: 7 + 4 op rules (16th preventive event but doctrine count holds)
- `Pre-audit-quantifier-precision-refined-by-grep`: 1 → 2 instances (NEW recurrence banked)

**Plan v1 LOCK forward-projection:** 9 anchors at exact mid (strict NARROW interpretation pending auditor confirmation).

**§9 Q5 interpretation question is the ONE Phase 0 open question worth explicit auditor adjudication.** All other leans (Q1-Q5 design choices) follow established precedent; only the NARROW-band interpretation at mid 9 has a prior precedent inconsistency (P0.B5 vs P0.B6/S8/S9/R1) worth locking.

**Next:** auditor Phase 0 verdict.
