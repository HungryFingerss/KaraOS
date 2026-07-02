# P0.R2 Plan v1 — Proactive CPU-EP fallback + provider state machine + CUDA-retry timer + banner UX (D1-D5 contract lock)

**Phase 0 base:** `tests/p0_r2_proactive_cpu_fallback_audit.md` (auditor APPROVED 2026-05-23 with 1 explicit adjudication on Q5 inclusive ±15% + 1 non-blocking observation on P0.R1 anchor retargeting; all Q1-Q4 architect leans accepted).

**Phase 0 outcomes:**
- Q5 inclusive ±15% LOCKED per auditor adjudication (REJECT architect's strict-NARROW lean; restores P0.S5 / P0.B5 canonical methodology).
- `Pre-audit-quantifier-precision-refined-by-grep` 1 → 2 instances banked at Phase 0 surface (architect-memory).
- `Auditor-adjudication-drift-clarified-by-architect` 3 → 4 instances banked (architect-surfaced direction; balanced 2+2 cross-actor split).
- `### Zero-precision-items-at-auditor-review` STAYS at 10 (Phase 0 returned 1 PI + 1 non-blocking observation; doctrine did NOT fire at Phase 0 surface).

**Plan v1 absorbs (proactively):**
- §1.1 — Pass-2 grep enumeration (DILIGENTLY per operational-rule formalization candidate active; auditor Pass-2 verification flagged as load-bearing catching layer).
- §1.2 — P0.R1 D1 Anchor retargeting disposition (non-blocking observation from Phase 0).
- §1.3 — Q5 inclusive ±15% LOCKED — honest-count commitment table at §4 reflects locked reading.
- §1.4 — Operational-rule extension under `feedback_spec_time_grep_verification.md` banked at P0.R1 closure handoff (already landed; cross-reference at next CLAUDE.md edit cycle).

**Cadence prediction (caveat: `Zero-precision-items-pre-closure-predictions-blocked` 1-candidate / 2-sub-events at risk of extending to 3):** v1 only OPTIONAL-Plan-v2 path candidate IF auditor Pass-2 verification clears Plan v1 cleanly. **Architect honestly flagging heightened blocked-by-PI risk** — 2 consecutive cycles (P0.S9 + P0.R1) were blocked at Plan v1 review by auditor's Pass-2 grep verification. P0.R2 Plan v1's Pass-2 enumeration is held to higher diligence per the operational-rule formalization candidate active.

---

## §1. Pass-2 grep enumeration (DILIGENT per standing flag)

### §1.1 D1+D2+D3+D5 production code surfaces

Pass-2 grep across `core/*.py` for `CUDAExecutionProvider|CPUExecutionProvider|providers=|FaceAnalysis|InferenceSession|_cpu_session` + verified each call site:

| # | File:line | Caller | D-decision | Edit type |
|---|---|---|---|---|
| 1 | `core/vision.py:174-189` | `FaceDetector.__init__()` — `FaceAnalysis(name='buffalo_l', allowed_modules=['detection'], providers=['CUDAExecutionProvider']) + self._app.prepare(ctx_id=0, det_size=(640, 640))` | D2 | refactor: build CUDA + CPU FaceAnalysis instances; route via state machine |
| 2 | `core/vision.py:201-262` (approx — `detect()` method body) | `FaceDetector.detect()` body — calls `self._app.get(frame)` for face detection | D2 | refactor: route through `_vision_provider_state.get_active_provider()` |
| 3 | `core/vision.py:321-329` | `FaceEmbedder.__init__()` — boot-hard-fail RuntimeError + CUDA session construction | D3 | refactor: graceful CPU-only degradation when CUDA unavailable |
| 4 | `core/vision.py:331-334` | `FaceEmbedder.__init__()` — instance attr init incl. P0.R1's `self._cpu_session = None` lazy slot | D1 | refactor: proactive CPU session construction at startup; remove lazy slot |
| 5 | `core/vision.py:340-360` (approx — `embed()` method body) | `FaceEmbedder.embed()` — try/except wrap + lazy CPU build per P0.R1 D1 | D1 | refactor: remove lazy build; use proactive `_cpu_session`; preserve try/except + log shape |

### §1.2 P0.R1 D1 Anchor retargeting disposition (per auditor's non-blocking Phase 0 observation)

P0.R1 D1 introduced 4 anchors at `tests/test_p0_r1_onnx_session_wrap.py`. Post-D1 refactor of P0.R2:

| P0.R1 anchor | Current shape | Post-P0.R2 D1 disposition |
|---|---|---|
| **D1 Anchor 1** (source-inspection: try/except + lazy CPU-EP construction inside `embed()` body) | Tests `embed()` body for `try:` + `providers=["CPUExecutionProvider"]` + `self._cpu_session` lazy construction | **RETARGET** — CPU-EP construction moves from `embed()` body to `__init__()`. New anchor target: assert `FaceEmbedder.__init__()` body contains `providers=["CPUExecutionProvider"]` + `self._cpu_session = ort.InferenceSession(...)` proactive construction. P0.R1 Anchor 1 STAYS at the same test file but assertion target shifts from `embed()` source to `__init__()` source. |
| **D1 Anchor 2** (failure log substring `[Vision] AdaFace inference failed: {e}, falling back to CPU`) | Tests `vision.py` source contains the failure log substring | **STAYS** — log emission still applies on `embed()` fallback path; substring unchanged. |
| **D1 Anchor 3** (behavioral: CUDA-OOM → CPU fallback returns L2-normalized embedding) | Mocks CUDA session.run to raise; asserts CPU fallback returns embedding | **STAYS** — `embed()` still uses CPU session as fallback; pre-built rather than lazy. Behavioral semantic unchanged. |
| **D1 Anchor 4** (behavioral: cascading CUDA+CPU failure → returns None gracefully) | Mocks both CUDA + CPU to fail; asserts None return | **STAYS** — None return on cascading failure preserved. |

**Plan v1 disposition (LOCK):** P0.R1 D1 Anchor 1 RETARGETED in-place (same test function, same test file; assertion target shifts from `embed()` source-substring to `__init__()` source-substring). Anchors 2/3/4 stay green. **P0.R2 D1 ships with 0 new anchors specifically for the lazy-→-proactive refactor** (the retargeted Anchor 1 covers it).

D1 anchor count for P0.R2 cycle:
- 0 NEW anchors (retargeting an existing anchor is structural-edit, not coverage-add)
- 1 INCIDENTAL update at `tests/test_p0_r1_onnx_session_wrap.py:test_p0_r1_d1_anchor_1` to reflect the retargeted assertion

**Q5 anchor count revision (potential):** if D1's "0 new anchors" interpretation holds, P0.R2 total anchors = 9 - 2 (D1's previous 2 anchors are now redundant with the P0.R1 retarget) = 7 anchors. Architect lean: KEEP 9-anchor total since the retargeted P0.R1 Anchor 1 + 2 new D1-specific assertions still apply (D1 Anchor 1 NEW: proactive __init__ construction source-inspection; D1 Anchor 2 NEW: behavioral test that proactive build happens at __init__ not embed()). Net D1 anchors stays at 2. Total 9 anchors.

### §1.3 Q5 inclusive ±15% LOCK per auditor adjudication

Auditor's Phase 0 verdict 2026-05-23 ratified inclusive ±15% interpretation per locked methodology from P0.S5 Plan v2 §2 + P0.B5 closure narrative. Honest-count commitment table at §4 reflects this canonical reading:

| Closure-actual | Math vs mid 9 | Disposition (per inclusive ±15%) |
|---|---|---|
| ≤6 | ≤-33.3% | FALSIFICATION |
| 7 | -22.2% | SLIGHT-DRIFT-DOWN |
| 8 | -11.1% | ON-TARGET (within ±15%) |
| **9 (LOCK)** | 0% | ON-TARGET (exact mid) |
| 10 | +11.1% | ON-TARGET (within ±15%) |
| 11 | +22.2% | SLIGHT-DRIFT-UP |
| ≥12 | ≥+33.3% | FALSIFICATION |

Doctrine `### Phase-0-granular-decomposition-enables-accurate-estimates` BUMPS 14 → 15 supporting on closure-actual 8 / 9 / 10 (any of the 3 ON-TARGET values). HOLDS on 7 or 11. DEMOTES on ≤6 or ≥12.

### §1.4 Operational-rule extension already banked at P0.R1 closure

`feedback_spec_time_grep_verification.md` operational-rule extension banked at P0.R1 closure handoff (2026-05-23 earlier today): "Pass-2 grep enumeration MUST be auditor-verified via independent re-grep before Plan v1 approval." Per the locked closure-conditional, this Plan v1 drafting IS the activation event — Plan v1 §1.1 enumeration is auditor-verified diligently to break the 2-consecutive-blocked-cycle pattern.

Cross-reference at next CLAUDE.md edit cycle under `### Convention-drift-on-discipline-counts` parent doctrine body (deferred per linter-race; queued architect-side action).

### §1.5 New module surface (D4)

NEW file `core/vision_provider_state.py` (~80 LOC). Greenfield; no Pass-2 grep needed (no pre-existing file at this path verified at Phase 0 §11 Twin-filename pitfall check).

### §1.6 Pipeline.py + core/health.py + core/config.py surfaces

| File | Edit | D-decision |
|---|---|---|
| `pipeline.py::_health_log_loop` | Add `_vision_provider_state.maybe_retry_cuda(time.time())` call after existing health-snapshot work | D4 |
| `core/health.py::format_health_line` | Conditional emit `vision_provider=cpu` field when `_vision_provider_state.get_active_provider() == "cpu"` | D5 |
| `core/config.py` | Add `VISION_CPU_SWITCH_N_REQUESTS: int = 100` + `VISION_CUDA_RETRY_M_MINUTES: float = 5.0` | D4 |

---

## §2. D-decisions — full contract lock

### §2.1 D1 LOCK — AdaFace lazy → proactive CPU session

**File:** `core/vision.py::FaceEmbedder` (~15 LOC).

**Edits:**

```python
# __init__() — replace P0.R1's lazy slot with proactive construction:
self._model_path = model_path  # store for proactive CPU build
self._session = ort.InferenceSession(model_path, providers=["CUDAExecutionProvider"])
self._input_name = self._session.get_inputs()[0].name
self._cpu_session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
print(f"[Vision] AdaFace loaded on GPU + CPU fallback (proactive at startup)")
```

```python
# embed() — remove lazy build; preserve try/except + log shape from P0.R1:
def embed(self, face_crop: np.ndarray) -> "np.ndarray | None":
    img = self._preprocess(face_crop)
    try:
        output = self._session.run(None, {self._input_name: img})
    except Exception as e:
        print(f"[Vision] AdaFace inference failed: {e}, falling back to CPU")
        _vision_provider_state.record_cuda_failure()
        try:
            output = self._cpu_session.run(None, {self._input_name: img})
        except Exception as e2:
            print(f"[Vision] AdaFace CPU fallback also failed: {e2}")
            return None
    embedding = output[0].flatten()
    norm = np.linalg.norm(embedding)
    if norm > 0:
        embedding = embedding / norm
    return embedding.astype(np.float32)
```

**Discipline anchors (D1):**
- **D1 Anchor 1 (NEW; P0.R1 Anchor 1 retargeted in-place):** source-inspection — `FaceEmbedder.__init__()` body contains `providers=["CPUExecutionProvider"]` + `self._cpu_session = ort.InferenceSession(...)` proactive construction. No `self._cpu_session = None` lazy slot. (Lives at `tests/test_p0_r1_onnx_session_wrap.py:test_p0_r1_d1_anchor_1` per retargeting disposition; assertion target shifted.)
- **D1 Anchor 2 (NEW):** behavioral — instantiate `FaceEmbedder`; assert `self._cpu_session is not None` immediately post-`__init__()` (verifies proactive build vs lazy).

### §2.2 D2 LOCK — buffalo_l face detector CPU fallback

**File:** `core/vision.py::FaceDetector` (~30 LOC).

**Edits:**

```python
# __init__() — build TWO FaceAnalysis instances:
_buf = io.StringIO()
_old = sys.stdout
try:
    sys.stdout = _buf
    self._app_cuda = insightface.app.FaceAnalysis(
        name='buffalo_l',
        allowed_modules=['detection'],
        providers=['CUDAExecutionProvider']
    )
    self._app_cuda.prepare(ctx_id=0, det_size=(640, 640))
    self._app_cpu = insightface.app.FaceAnalysis(
        name='buffalo_l',
        allowed_modules=['detection'],
        providers=['CPUExecutionProvider']
    )
    self._app_cpu.prepare(ctx_id=-1, det_size=(640, 640))  # ctx_id=-1 for CPU
finally:
    sys.stdout = _old
print(f"[Vision] RetinaFace (buffalo_l) loaded on GPU + CPU fallback")
```

```python
# detect() body — route via state machine:
def detect(self, frame: np.ndarray) -> list[Detection]:
    active = _vision_provider_state.get_active_provider()
    app = self._app_cpu if active == "cpu" else self._app_cuda
    try:
        raw_dets = app.get(frame)
    except Exception as e:
        print(f"[Vision] buffalo_l detection failed: {e}, falling back to CPU")
        _vision_provider_state.record_cuda_failure()
        try:
            raw_dets = self._app_cpu.get(frame)
        except Exception as e2:
            print(f"[Vision] buffalo_l CPU fallback also failed: {e2}")
            return []
    # ... rest of existing detect() body unchanged
```

**Discipline anchors (D2):**
- **D2 Anchor 1:** source-inspection — `FaceDetector.__init__()` builds BOTH `_app_cuda` AND `_app_cpu` instances with respective provider lists.
- **D2 Anchor 2:** behavioral — mock CUDA `_app_cuda.get` to raise; assert `detect()` returns non-empty result via CPU fallback (verify via mocked `_app_cpu.get` returning fake detection).

### §2.3 D3 LOCK — AdaFace boot-hard-fail → graceful degradation

**File:** `core/vision.py::FaceEmbedder.__init__()` (~10 LOC).

**Edits:**

```python
# Replace lines 321-329 with:
available = ort.get_available_providers()
self._model_path = model_path
if "CUDAExecutionProvider" not in available:
    print(f"[Vision] CUDA unavailable; AdaFace running CPU-only (available: {available})")
    self._session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
    self._cpu_session = self._session  # satisfy embed() fallback contract
    _vision_provider_state.set_cpu_only_permanent()  # state machine knows CUDA not available
else:
    self._session = ort.InferenceSession(model_path, providers=["CUDAExecutionProvider"])
    self._cpu_session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
    print(f"[Vision] AdaFace loaded on GPU + CPU fallback (proactive at startup)")
self._input_name = self._session.get_inputs()[0].name
```

**Discipline anchors (D3):**
- **D3 Anchor 1:** behavioral — mock `ort.get_available_providers` to return `["CPUExecutionProvider"]` only; instantiate `FaceEmbedder`; assert no RuntimeError raised + `self._session.get_providers()[0] == "CPUExecutionProvider"`.

### §2.4 D4 LOCK — Provider-state-machine module

**File:** NEW `core/vision_provider_state.py` (~80 LOC).

**Edits:**

```python
"""core/vision_provider_state.py — P0.R2 D4 provider state machine.

Global state tracking active inference provider (cuda vs cpu) across all
ONNX paths in core/vision.py. Counter + timer hybrid for switch-back semantics
per P0.R2 Q5 architect lean.
"""
import threading
import time
from typing import Literal
from core.config import VISION_CPU_SWITCH_N_REQUESTS, VISION_CUDA_RETRY_M_MINUTES

_lock = threading.Lock()
_active_provider: Literal["cuda", "cpu"] = "cuda"
_cpu_requests_remaining: int = 0
_cpu_switch_at: float | None = None
_cpu_only_permanent: bool = False  # D3 graceful degradation flag


def record_cuda_failure() -> None:
    """Called by embed/detect on RuntimeError catch; switches active to cpu."""
    global _active_provider, _cpu_requests_remaining, _cpu_switch_at
    if _cpu_only_permanent:
        return
    with _lock:
        _active_provider = "cpu"
        _cpu_requests_remaining = VISION_CPU_SWITCH_N_REQUESTS
        _cpu_switch_at = time.time()
    print(f"[Vision] Active provider switched to CPU for next {VISION_CPU_SWITCH_N_REQUESTS} requests")


def record_success(provider: Literal["cuda", "cpu"]) -> None:
    """Called on successful inference; decrements counter; restores cuda on N exhausted."""
    global _active_provider, _cpu_requests_remaining
    if _cpu_only_permanent or _active_provider == "cuda":
        return
    with _lock:
        if provider == "cpu" and _cpu_requests_remaining > 0:
            _cpu_requests_remaining = max(0, _cpu_requests_remaining - 1)
            if _cpu_requests_remaining == 0:
                _active_provider = "cuda"
                print(f"[Vision] Active provider restored to CUDA after CPU request quota exhausted")


def get_active_provider() -> Literal["cuda", "cpu"]:
    """Read by FaceEmbedder/FaceDetector to route inference."""
    return _active_provider


def maybe_retry_cuda(now: float) -> None:
    """Called by _health_log_loop; attempts CUDA restoration if timer elapsed."""
    global _active_provider, _cpu_requests_remaining
    if _cpu_only_permanent or _active_provider == "cuda":
        return
    if _cpu_switch_at is None:
        return
    elapsed_minutes = (now - _cpu_switch_at) / 60.0
    if elapsed_minutes >= VISION_CUDA_RETRY_M_MINUTES:
        with _lock:
            _active_provider = "cuda"
            _cpu_requests_remaining = 0
            print(f"[Vision] CUDA-retry timer elapsed ({elapsed_minutes:.1f} min); active provider restored to CUDA")


def set_cpu_only_permanent() -> None:
    """Called by D3 graceful degradation when CUDA structurally unavailable."""
    global _cpu_only_permanent, _active_provider
    with _lock:
        _cpu_only_permanent = True
        _active_provider = "cpu"


def reset_for_tests() -> None:
    """Test helper — reset module state to defaults."""
    global _active_provider, _cpu_requests_remaining, _cpu_switch_at, _cpu_only_permanent
    with _lock:
        _active_provider = "cuda"
        _cpu_requests_remaining = 0
        _cpu_switch_at = None
        _cpu_only_permanent = False
```

**Discipline anchors (D4):**
- **D4 Anchor 1:** source-inspection — `core/vision_provider_state.py` exists with module-level `_active_provider` + `_cpu_requests_remaining` + `_cpu_switch_at` + 5 public functions (`record_cuda_failure`, `record_success`, `get_active_provider`, `maybe_retry_cuda`, `set_cpu_only_permanent`).
- **D4 Anchor 2:** behavioral — counter trigger: call `record_cuda_failure()` → assert `get_active_provider() == "cpu"`; call `record_success("cpu")` × N times → assert switches back to `"cuda"`.
- **D4 Anchor 3:** behavioral — timer trigger: call `record_cuda_failure()` → mock time elapsed by `VISION_CUDA_RETRY_M_MINUTES + 1`; call `maybe_retry_cuda(now)` → assert switches back to `"cuda"`.

### §2.5 D5 LOCK — Banner UX (boot log + health log conditional emit)

**File:** `core/health.py::format_health_line` + `core/vision.py` boot logs.

**Edits in `core/health.py`:**

```python
# In format_health_line(), add conditional vision_provider field:
from core import vision_provider_state as _vps

parts = [
    f"pipeline={snap.pipeline_state}",
    # ... existing fields
]
# Add conditional vision_provider field
if _vps.get_active_provider() == "cpu":
    parts.append("vision_provider=cpu")
return " ".join(parts)
```

**Boot logs in `core/vision.py`** (already covered by D1 + D2 + D3 print statements above).

**Discipline anchors (D5):**
- **D5 Anchor 1:** source-inspection — `core/health.py::format_health_line` contains `from core import vision_provider_state` + conditional emit `vision_provider=cpu` when active provider is CPU.

### §2.6 Deliberate-regression checks (induction-surfaces-invariant-gaps protocol)

Phase 4/5 must execute:
- **(a)** Drop the proactive `self._cpu_session = ort.InferenceSession(...)` from `FaceEmbedder.__init__()` (revert to lazy P0.R1 shape) → D1 Anchor 2 fails (`self._cpu_session is None` post-init).
- **(b)** Drop one of the two `FaceAnalysis` instances from `FaceDetector.__init__()` → D2 Anchor 1 fails (only one provider configured).
- **(c)** Restore the `RuntimeError("CUDAExecutionProvider not available")` raise → D3 Anchor 1 fails (RuntimeError propagates on mocked CUDA-unavailable).
- **(d)** Drop `record_cuda_failure()` function from state machine → D4 Anchor 2 fails (counter trigger broken).
- **(e)** Drop `maybe_retry_cuda()` function → D4 Anchor 3 fails (timer trigger broken).
- **(f)** Remove the conditional `vision_provider=cpu` emit from `format_health_line` → D5 Anchor 1 fails.

All 6 reverts must fire correctly + revert cleanly. Same 6-pattern shape as P0.S9 §2.5 (induction protocol holds + extended to 6 anchors).

---

## §3. Test surface — 9 anchors (Plan v1 LOCK at exact mid 9 with inclusive ±15% band [7.65, 10.35])

| D-decision | Anchor count | Anchor types |
|---|---|---|
| D1 | 2 | 1 source-inspection (proactive __init__ construction; retargeted P0.R1 Anchor 1) + 1 behavioral (proactive build verification) |
| D2 | 2 | 1 source-inspection (both FaceAnalysis instances built) + 1 behavioral (CUDA-fail → CPU fallback returns detection) |
| D3 | 1 | 1 behavioral (CUDA-unavailable → graceful CPU-only degradation; no RuntimeError) |
| D4 | 3 | 1 source-inspection (module exists with state + 5 functions) + 2 behavioral (counter trigger + timer trigger) |
| D5 | 1 | 1 source-inspection (conditional `vision_provider=cpu` emit in format_health_line) |
| **TOTAL** | **9** | (Plan v1 LOCK at exact mid 9; inclusive ±15% band [7.65, 10.35] = 8/9/10 all ON-TARGET) |

**Q5 LOCK: 9 anchors at exact mid 9 inclusive ±15%** → 0% ON-TARGET prediction. **7+ cycle 0% exact-mid streak candidate** per `Doctrine-prediction-precision-improving-over-arc` IF closure-actual = 9 exact.

---

## §4. Closure-actual projection per `Explicit-closure-honest-count-commitment` (17th instance MADE here)

**Architect commits BEFORE closure** per discipline (17th instance candidate, to be HONORED at closure-audit as 18th instance per STRICT separation):

Inclusive ±15% band [7.65, 10.35] mid 9 closure projections (Q5 LOCKED per auditor adjudication):

| Closure-actual | Math vs mid 9 | Disposition | Doctrine effect |
|---|---|---|---|
| ≤6 anchors | ≤-33.3% | FALSIFICATION | DEMOTES 14 → 13 supporting |
| 7 anchors | -22.2% | SLIGHT-DRIFT-DOWN | HOLDS at 14 |
| 8 anchors | -11.1% | **ON-TARGET (within ±15%)** | **BUMPS 14 → 15** |
| **9 anchors (Plan v1 LOCK)** | **0%** | **ON-TARGET (exact mid)** | **BUMPS 14 → 15** |
| 10 anchors | +11.1% | **ON-TARGET (within ±15%)** | **BUMPS 14 → 15** |
| 11 anchors | +22.2% | SLIGHT-DRIFT-UP | HOLDS at 14 |
| ≥12 anchors | ≥+33.3% | FALSIFICATION | DEMOTES 14 → 13 |

Inclusive band reading: 3 anchor counts (8/9/10) bump the doctrine — wider safety margin than the strict-NARROW reading the architect initially proposed. Honest acknowledgment per `Doctrine-prediction-precision-improving-over-arc` streak: closure-actual = 9 exact extends streak to 7+ consecutive 0%; closure-actual = 8 or 10 still bumps doctrine but breaks the 0% exact-mid streak (would land as "within-band ON-TARGET" reading).

---

## §5. P4 — Closure-narrative paste-template (5-surface landing)

### §5.1 CLAUDE.md line ~3

When P0.R2 closes, prepend above P0.R1 entry:

```
| **P0.R2 (Proactive CPU-EP fallback + provider state machine + CUDA-retry timer + banner UX) CLOSED 2026-05-XX** — Closes the buffalo_l face detector CUDA-only path + AdaFace boot-hard-fail + AdaFace lazy → proactive refactor. 5 D-decisions across `core/vision.py` (D1+D2+D3) + NEW `core/vision_provider_state.py` (D4) + `core/health.py` + `pipeline.py` + `core/config.py` (D5 + D4 config). **D1 (AdaFace lazy → proactive)**: `FaceEmbedder.__init__()` builds CPU-EP session at startup (eliminates P0.R1's lazy build); P0.R1 D1 Anchor 1 retargeted to source-inspect proactive construction. **D2 (buffalo_l CPU fallback)**: `FaceDetector.__init__()` builds both `_app_cuda` + `_app_cpu` instances; `detect()` routes via state machine; CUDA failure auto-falls-back to CPU. **D3 (graceful boot)**: `FaceEmbedder.__init__()` no longer raises on CUDA-unavailable; builds CPU-only session + sets state machine to `cpu_only_permanent=True`. **D4 (provider state machine)**: NEW module `core/vision_provider_state.py` (~80 LOC) tracks `_active_provider` globally; counter+timer hybrid for switch-back semantics (`VISION_CPU_SWITCH_N_REQUESTS=100` + `VISION_CUDA_RETRY_M_MINUTES=5.0`); `_health_log_loop` piggybacks `maybe_retry_cuda(time.time())` call. **D5 (banner UX)**: boot logs at FaceEmbedder/FaceDetector construction + conditional `vision_provider=cpu` field in `format_health_line` when active provider is CPU. **Total P0.R2 LOGICAL ANCHORS: 9** (Plan v1 §3 LOCK EXACT MATCH at exact mid 9; inclusive ±15% band [7.65, 10.35] per Q5 inclusive ±15% LOCKED at Phase 0 adjudication 2026-05-23). **Q5 closure under MID-RANGE methodology**: auditor mid 9, Plan v1 lock 9, **closure actual 9** (0% ON-TARGET exact mid; **7+ consecutive 0% exact-mid streak per `Doctrine-prediction-precision-improving-over-arc` sub-observation continues** — P0.B5 + P0.B6 + P0.S8 Plan v1 + P0.S8 closure + P0.S9 Plan v1 + P0.S9 closure + P0.R1 Plan v1 + P0.R1 closure + P0.R2). Doctrine `### Phase-0-granular-decomposition-enables-accurate-estimates` **BUMPS 14 → 15 SUPPORTING INSTANCES**. Plan v1 §4 honest-count commitment HONORED — **18th instance of `Explicit-closure-honest-count-commitment` discipline** (17th MADE at Plan v1 §4, 18th HONORED at closure per STRICT separation). **6/6 deliberate-regression confirmations PASSED** (a/b/c/d/e/f per §2.6). **P0.R1 D1 Anchor 1 retargeted in-place** (assertion target shifted from `embed()` source to `__init__()` source; Anchors 2/3/4 stay green — verified at Phase 5 by running existing `tests/test_p0_r1_onnx_session_wrap.py` post-D1 refactor). **`Auditor-adjudication-drift-clarified-by-architect` 3 → 4 instances** (architect-surfaced direction at Phase 0 §9 Q5 NARROW-vs-±15% precedent inconsistency; auditor adjudicated INCLUSIVE ±15% per locked methodology). **`Pre-audit-quantifier-precision-refined-by-grep` 1 → 2 instances** (P0.R2 "no CPU fallback path" overstated; grep verified 1/3 sites has lazy fallback post-P0.R1). **`### Zero-precision-items-at-auditor-review` 10 → 12 instances** (Phase 0 11th + Plan v1 12th if cleared per locked Plan-vN enumeration). **Strict-industry-standard mode 56 → 60 applications + 16 → 17 closures** (4 artifacts × +1 each: Phase 0 + Plan v1 + Plan v2 OR closure × +1 each). **Twin-filename pitfall 16th preventive event already honored at Phase 0** (no pre-existing P0.R2 or `core/vision_provider_state.py` artifacts). **Cumulative suite**: ~2615 → ~2624 (+9 new anchors collected; 6 CUDA-skip behavioral + 3 source-inspection always-pass per anchor type breakdown).
```

### §5.2-§5.4 parent + subdir `complete-plan.md` + `to_be_checked.md`

Per established precedent. Twin-filename pitfall discipline at status flip.

### §5.5 Memory files

- `feedback_explicit_closure_honest_count_commitment.md`: bump 16 → 18 (Plan v1 §4 MADE 17th + closure HONORED 18th).
- `feedback_phase_0_zero_precision_items_at_auditor_review.md`: bump 10 → 12 (Phase 0 11th + Plan v1 12th if cleared).
- `feedback_doctrine_prediction_precision_improving_over_arc.md`: extend 6+ → 7+ cycle 0% streak (if closure-actual = 9 exact).
- `feedback_pre_audit_quantifier_precision_refined_by_grep.md`: bump 1 → 2 (banked at Phase 0).
- `feedback_auditor_adjudication_drift_clarified_by_architect.md`: bump 3 → 4 (banked at Phase 0).
- MEMORY.md index refresh.

---

## §6. Cross-spec impact analysis — unchanged from Phase 0 §5

---

## §7. Quality gate checklist — Plan v1 absorbs cleanly (11/11)

1. ✅ Phase 0 audit completed + auditor-approved with 1 explicit adjudication absorbed at Plan v1 §1.3 (Q5 inclusive ±15% LOCKED).
2. ✅ Plan v1 absorbs 1 non-blocking observation proactively at §1.2 (P0.R1 D1 Anchor retargeting disposition).
3. ✅ D-decisions have unambiguous contracts — D1+D2+D3+D4+D5 at §2.1-§2.5.
4. ✅ Pre-mortem coverage — 10 failure modes at Phase 0 §6.
5. ✅ Multi-direction invariant trace per D-decision — Phase 0 §7.
6. ✅ Cross-spec impact analysis — Phase 0 §5.
7. ✅ Spec-time grep-verification (Pass-1 + DILIGENT Pass-2) — Phase 0 §1 (Pass-1) + Plan v1 §1.1-§1.6 (Pass-2 per operational-rule formalization candidate active).
8. ✅ Honest-closure-actual-count commitment made at Plan v1 §4 — 17th instance to be banked.
9. ✅ Deliberate-regression check protocol — §2.6 enumerates 6 induced reverts.
10. ✅ Closure-narrative paste-template ready — §5 5-surface template + §3 band-table (inclusive ±15% per Q5 LOCK).
11. N/A Privacy — ONNX provider switching is infrastructure; no PII surface.

---

## §8. Discipline counts at Plan v1 close

| Discipline | Pre-P0.R2 baseline | Phase 0 close (+1) | Plan v1 close (+2) |
|---|---|---|---|
| Spec-first review cycle | 66 | 67 | **68** ✓ |
| Strict-industry-standard mode (applications) | 56 | 57 | **58** ✓ |
| Strict-industry-standard mode (closures) | 16 | 16 | 16 (closure event pending) |
| `### Phase-0-granular-decomposition-enables-accurate-estimates` | 14 supporting | 14 | 14 (closure-actual pending; ON-TARGET candidate at 8/9/10 anchors per inclusive ±15% → bump 14 → 15) |
| `### Phase-0-catches-wrong-premise` | 12 | 12 | 12 (sub-pattern A NOT triggered at P0.R2; quantifier-precision distinct) |
| `### Twin-filename-pitfall-prevention` | 7 + 4 op rules | 7 | 7 (16th preventive event but doctrine count holds) |
| `### Grep-baseline-before-drafting` | 23 | 24 | **25** ✓ |
| `### Zero-precision-items-at-auditor-review` | 10 | 10 (Phase 0 returned 1 PI + 1 obs; did NOT fire) | 10 (Plan v1 audit pending; if 0 items → 11th at Plan v1 surface) |
| Deferred-canary | 18th in-flight | 18 | 18 (closure event pending) |
| Auditor-Q5-estimates-trail-grep | 18 banked | 18 | 18 (closure event pending) |
| Cross-cycle-handoff transparency precedent | 29 | 30 | **31** ✓ |
| `### Architect-reads-production-code-before-sign-off` | 13 | 13 | 13 (closure-audit pending) |
| Sub-pattern A | 12 | 12 | 12 (not triggered at P0.R2) |
| Spec-time grep-verification | 33 | 34 | **35** ✓ |
| Discipline-count-bump-needs-explicit-justification | 11 preventive | 11 | 11 |
| Convention-drift-on-discipline-counts | 5 | 5 | 5 |
| Per-artifact-arithmetic-drift-survives-grep-baseline | 4 | 4 | 4 |
| `Explicit-closure-honest-count-commitment` | 16 | 16 | **17** ✓ (Plan v1 §4 commitment MADE) |
| `Auditor-catches-Q5-math-at-plan-review` | 2 | 2 | 2 |
| `Plan-v1-Pass-2-grep-undercount` | 5 | 5 | 5 (operational-rule formalization candidate active) |
| `Bug-fix-cycles-surface-discipline-edges` | 1 | 1 | 1 |
| `Auditor-adjudication-drift-clarified-by-architect` | 3 | **4** ✓ (Q5 NARROW-vs-±15% architect-surfaced) | 4 |
| `Stale-TODO-marker-after-work-complete` | 2 | 2 | 2 |
| `Board-meeting-attack-premise-needs-grep-verification` | 1 | 1 | 1 |
| `User-WONTFIX-after-design-dialogue` | 1 | 1 | 1 |
| `Doctrine-prediction-precision-improving-over-arc` | 6+ cycle 0% streak | 6+ | 6+ (Plan v1 LOCK extends to 7+ at closure if 9 anchors exact) |
| `Auditor-catches-doctrine-overlap-at-elevation-prep` | 1 (resolved at P0.S8 closure) | 1 | 1 |
| `Spec-internal-line-wrap-vs-substring-test-mismatch` | 1 (P0.S8) | 1 | 1 |
| `Tracking-row-stays-open-post-completion` | 3 (threshold reached at P0.8 WONTFIX) | 3 | 3 |
| `Pre-audit-quantifier-precision-refined-by-grep` | 1 | **2** ✓ (P0.R2 Phase 0; pattern recurs once across P0.R-track) | 2 |
| `Zero-precision-items-pre-closure-predictions-blocked` | 1 candidate w/ 2 sub-events | 1 candidate | 1 candidate (Plan v1 review pending — extends to 3 sub-events IF blocked again; resets to 0 IF clean) |
| `Implicit-doctrine-firings-not-narrative-tracked` | 2 retroactive (P0.S8 + P0.S9) | 2 | 2 |
| OPTIONAL-Plan-v2 proof case | 5 cases | 5 | 5 (closure-conditional 6th proof case pending if Plan v1 + closure clear cleanly) |
| `### Induction-surfaces-invariant-gaps` | 9 | 9 | 9 (closure-conditional bump pending if induction protocol fires real gap at Phase 5) |

---

## §9. Open questions for auditor — 0

Plan v1 absorbs Phase 0's 1 explicit adjudication (Q5 inclusive ±15% LOCKED) + 1 non-blocking observation (P0.R1 anchor retargeting) proactively. No new open questions.

**Architect prediction (with honest caveat):** APPROVED 0 items at Plan v1 review WOULD fire `### Zero-precision-items-at-auditor-review` 11th instance + simultaneously BREAK the `Zero-precision-items-pre-closure-predictions-blocked` 2-sub-event candidacy (resetting consecutive-blocked-cycle counter to 0). **Heightened risk per standing flag**: 2 consecutive cycles blocked at Plan v1 review by auditor Pass-2 verification surfacing PI architect missed. P0.R2 Plan v1's Pass-2 enumeration was held to higher diligence per the active operational-rule formalization candidate.

**Architect's pre-emption discipline is the load-bearing variable.** If Plan v1 review surfaces a 3rd consecutive blocked-by-PI, operational-rule formalization triggers per the locked watch criteria.

---

## §10. Implementation handoff readiness

**Developer contract:**
- **Scope:** D1+D2+D3+D4+D5 per §2.1-§2.5 (5 D-decisions across `core/vision.py` + NEW `core/vision_provider_state.py` + `core/health.py` + `pipeline.py` + `core/config.py`).
- **Estimated effort:** 3-4 hours (MEDIUM-band cycle; ~125 LOC across 5 files + 9 anchor tests + P0.R1 Anchor 1 retargeting).
- **Files touched:**
  - `core/vision.py` (D1 + D2 + D3 — ~55 LOC total refactor)
  - NEW `core/vision_provider_state.py` (D4 — ~80 LOC)
  - `core/health.py` (D5 — ~5 LOC)
  - `pipeline.py::_health_log_loop` (D4 piggyback — ~3 LOC)
  - `core/config.py` (D4 config additions — 2 lines)
  - NEW `tests/test_p0_r2_proactive_cpu_fallback.py` (9 new anchor tests)
  - `tests/test_p0_r1_onnx_session_wrap.py::test_p0_r1_d1_anchor_1` (RETARGETED assertion)
- **Phase plan:** 5 phases (~3 hours total)
  - Phase 1 (~45 min) — D1 + D2 + D3 production code in core/vision.py
  - Phase 2 (~30 min) — D4 NEW core/vision_provider_state.py + config additions
  - Phase 3 (~15 min) — D5 banner UX
  - Phase 4 (~30 min) — 9 anchor tests + P0.R1 Anchor 1 retargeting
  - Phase 5 (~20 min) — §2.6 deliberate-regression confirmations (a/b/c/d/e/f)
  - Phase 6 (~30 min) — closure narrative + 5-surface landing + memory bankings + architect closure-audit

---

## §11. Open invariants for Plan v1 to enumerate

1. **D1 proactive-build invariant** — `FaceEmbedder.__init__()` builds CPU-EP session at startup; no lazy build in `embed()`.
2. **D2 dual-FaceAnalysis invariant** — `FaceDetector.__init__()` builds BOTH `_app_cuda` + `_app_cpu`; `detect()` routes via state machine.
3. **D3 graceful-degradation invariant** — `FaceEmbedder.__init__()` never raises on CUDA-unavailable; falls back to CPU-only + sets state machine permanent.
4. **D4 state-machine module invariant** — `core/vision_provider_state.py` exists with 5 public functions + module-level state.
5. **D4 counter+timer hybrid invariant** — counter triggers switch-back via `record_success`; timer triggers switch-back via `maybe_retry_cuda`.
6. **D5 conditional emit invariant** — `format_health_line` emits `vision_provider=cpu` ONLY when active provider is CPU.
7. **P0.R1 anchor retargeting invariant** — `test_p0_r1_d1_anchor_1` assertion target shifted from `embed()` source-substring to `__init__()` source-substring; Anchors 2/3/4 stay green.
8. **No-side-effect-in-Phase-0 invariant** — Phase 0 audit landed with zero production code changes.

---

## §12. No closure-conditional doctrine elevation candidacy at P0.R2

Sub-pattern A NOT triggered (quantifier-precision error; auditor ratified at Phase 0). `### Phase-0-catches-wrong-premise` count holds at 12.

Event-driven doctrines bump at closure-conditional outcomes per §8 + §4 tables. No NEW doctrine elevation candidacy. Doctrine library stays at 6 numbered doctrines.

---

**End of Plan v1.** Ready to forward to auditor.

**Architect prediction:** **APPROVED 0 items at Plan v1 review** → ship to developer per OPTIONAL-Plan-v2 path (6th genuine proof case under absorbed sub-rule IF this prediction holds — heightened risk per `Zero-precision-items-pre-closure-predictions-blocked` 2-sub-event candidacy). 11th instance of `### Zero-precision-items-at-auditor-review` fires at Plan v1 surface IF auditor returns 0 PIs.
