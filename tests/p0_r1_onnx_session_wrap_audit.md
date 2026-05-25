# P0.R1 Phase 0 audit — ONNX `session.run()` wrap + lazy CPU-EP fallback

**Status:** DRAFT 2026-05-23 — pending auditor review.

**Pre-audit framing (parent `complete-plan.md:716`):**

```
### P0.R1 — ONNX `session.run()` not wrapped

**Fix:** wrap every `session.run()` in try/except. On `RuntimeError` (CUDA OOM):
log; fall back to lazily-built CPU-EP session for that single call; degrade
gracefully.
```

**Phase 0 outcome:** Pre-audit framing PARTIALLY ACCURATE per grep. The premise's "every session.run()" claim is FALSIFIED — 1 of 2 call sites already wrapped at original session ship. Load-bearing scope is the 1 remaining unwrapped site at `core/vision.py:334` (AdaFace embed). Real cycle (NOT WONTFIX); SMALL-band single-D-decision.

---

## §1. ONNX `session.run()` call site inventory (Pass-1 grep)

Grep `session\.run\(|ort\.InferenceSession|onnxruntime` across `core/*.py`:

| File:line | Caller | Wrap status | Notes |
|---|---|---|---|
| `core/audio.py:177` | `predict()` for Smart-Turn neural turn-end | **WRAPPED ✓** (lines 170-180) | try/except returns 0.0 on any failure; logs `[Audio] Smart-Turn predict failed: {e}` |
| `core/vision.py:334` | `FaceEmbedder.embed()` for AdaFace 512-dim embedding | **UNWRAPPED ✗ — the gap** | Bare `self._session.run(None, {self._input_name: img})`; no try/except; no CPU-EP fallback |

**Audio.py wrap reference** (existing pattern P0.R1 should mirror):

```python
# core/audio.py:170-180
try:
    target = 8 * MIC_SAMPLE_RATE
    padded = audio[-target:] if len(audio) >= target else np.concatenate(
        [np.zeros(target - len(audio), dtype=np.float32), audio]
    )
    features = _st_extractor(padded, sampling_rate=MIC_SAMPLE_RATE,
                              return_tensors="np").input_features
    return float(_st_session.run(None, {"input_features": features})[0][0][0])
except Exception as e:
    print(f"[Audio] Smart-Turn predict failed: {e}")
    return 0.0
```

**Vision.py gap** (current state):

```python
# core/vision.py:327-340
self._session    = ort.InferenceSession(model_path, providers=["CUDAExecutionProvider"])
self._input_name = self._session.get_inputs()[0].name
print(f"[Vision] AdaFace loaded on GPU")

def embed(self, face_crop: np.ndarray) -> np.ndarray:
    """Extract 512-dim embedding from a face crop."""
    img = self._preprocess(face_crop)
    output = self._session.run(None, {self._input_name: img})  # ← unwrapped
    embedding = output[0].flatten()
    norm = np.linalg.norm(embedding)
    if norm > 0:
        embedding = embedding / norm
    return embedding.astype(np.float32)
```

---

## §2. Grep-verified findings

### §2.1 Load-bearing finding — `core/vision.py:334` is the single unwrapped session.run() in core/

CUDA OOM during AdaFace embedding currently crashes the recognition path entirely. Symptom: `RuntimeError: CUDA OOM` propagates up through `embed()` → recognize() → `_background_vision_loop` → asyncio task crash → vision degraded for the rest of the session.

P0.R1's per-call lazy CPU-EP fallback strategy is the right shape: catch the RuntimeError, log it, build a CPU session ONCE (cached as instance attribute), retry the embed call with CPU, return the embedding transparently. Process stays alive; one embed call degrades from ~30ms CUDA to ~200ms CPU; brain never sees the difference.

### §2.2 Symmetry with existing Smart-Turn wrap

`core/audio.py:170-180` already implements the wrap pattern. P0.R1's vision.py wrap should mirror the SAME shape:
- broad `except Exception as e:` catch
- log via `print(f"[Vision] AdaFace inference failed: {e}, falling back to CPU")`
- on failure, build CPU session lazily (NOT in audio.py since Smart-Turn returns 0.0; in vision.py we build CPU session because embedding return is load-bearing)
- return CPU embedding transparently OR return None on cascading CPU failure

### §2.3 Other ONNX-backed model paths

- **MiniFASNet anti-spoof (core/_minifasnet/)** — uses PyTorch `torch.load` of `.pth` weights per Session 52 closure ("`AntiSpoofChecker` rewritten to load both `.pth` via `torch`"). NOT ONNX. Out of P0.R1 scope.
- **buffalo_l face detector** — goes through `insightface` library wrapper. session.run is library-internal; can't wrap at our layer. Out of P0.R1 scope (would need library-level patch or wrapper refactor).
- **Smart-Turn (core/audio.py:177)** — already wrapped; nothing to do.
- **Whisper STT** — uses faster-whisper library; no direct ONNX session.run in our code.

---

## §3. Out-of-scope

1. **P0.R2 (proactive CPU-EP at startup)** — separate cycle per parent stub. P0.R1 does lazy/per-call fallback; P0.R2 does proactive multi-provider architecture with CUDA-retry timer. P0.R1 closes the immediate crash-surface; P0.R2 makes it proactive. Architect lean: SPLIT per parent stubs (Q1 below).
2. **MiniFASNet PyTorch error handling** — different framework (PyTorch, not ONNX). Banked as P0.R-future or P0.R5 territory (anti-spoof robustness).
3. **buffalo_l library-internal session.run** — would require either an insightface library fork OR a wrapper that intercepts internal calls. Both substantially larger scope than P0.R1.
4. **CUDA recovery / retry logic** — P0.R2 territory. P0.R1 stays on CPU once fallback fires; no retry until process restart.

---

## §4. D-decisions (single D-decision, decomposed with named edit sites)

### D1 — Wrap `core/vision.py:334` + lazy CPU-EP fallback

**Files:** `core/vision.py` (~10 LOC added to `FaceEmbedder` class)

**Edits:**

1. Add `self._cpu_session: ort.InferenceSession | None = None` instance attribute in `FaceEmbedder.__init__()` (lazy slot).
2. Refactor `embed()` body to wrap `session.run()` in try/except.
3. On RuntimeError catch: log `[Vision] AdaFace inference failed: {e}, falling back to CPU`; lazily build `self._cpu_session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])` if not already cached; retry session.run with `self._cpu_session`.
4. On nested CPU failure (CPU build OR CPU session.run raises): log second-tier failure; return `None` (caller handles graceful turn-skip via existing recognize() empty-result path).
5. Mirror Smart-Turn log shape; mirror existing audio.py wrap discipline.

**Implementation sketch:**

```python
def embed(self, face_crop: np.ndarray) -> "np.ndarray | None":
    """Extract 512-dim embedding from a face crop. Returns None on cascading
    CUDA + CPU failure (caller treats as recognize-miss)."""
    img = self._preprocess(face_crop)
    try:
        output = self._session.run(None, {self._input_name: img})
    except (RuntimeError, ort.OrtException, Exception) as e:
        print(f"[Vision] AdaFace inference failed: {e}, falling back to CPU")
        try:
            if self._cpu_session is None:
                self._cpu_session = ort.InferenceSession(
                    self._model_path,
                    providers=["CPUExecutionProvider"],
                )
                print(f"[Vision] AdaFace CPU fallback session built")
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

Plus `self._model_path = model_path` storage in `__init__()` so the lazy CPU build can find the model file.

**Note on return type change:** `embed()` currently returns `np.ndarray` unconditionally; post-D1 returns `np.ndarray | None`. Callers (`recognize()`, `add_embedding()`) need to handle None — existing code paths probably treat None as "no match" but verification needed at Plan v1 §1 Pass-2 grep.

**Discipline anchors (D1):**
- **D1 Anchor 1** (source-inspection): `core/vision.py::FaceEmbedder.embed()` body contains `try:` + `except` AND lazy CPU-EP session construction pattern (`providers=["CPUExecutionProvider"]`).
- **D1 Anchor 2** (source-inspection): failure-log substring `[Vision] AdaFace inference failed` present (mirroring Smart-Turn shape).
- **D1 Anchor 3** (behavioral): monkeypatch CUDA `_session.run` to raise `RuntimeError("CUDA OOM")`; assert `embed()` returns embedding from CPU fallback session (verify shape + L2-normalized).
- **D1 Anchor 4** (behavioral): monkeypatch BOTH CUDA `_session.run` AND CPU session construction to raise; assert `embed()` returns `None` gracefully (no crash propagation).

---

## §5. Cross-spec impact analysis

| Cross-spec | Interaction with P0.R1 | Disposition |
|---|---|---|
| **P0.R2** (proactive CPU-EP) | Downstream — P0.R2 changes the CPU session construction from lazy to proactive; P0.R2 might refactor `embed()` to use a provider-pool abstraction | SPLIT per parent stubs; P0.R2 follows P0.R1 |
| **P0.S1** (anti-spoof on every face match) | Anti-spoof + face match both call `embed()`; fallback works for both transparently | No interaction concern |
| **P0.5** (FAISS+SQL atomicity) | Embedding output flows to `add_embedding()` SQL writes; None return → caller skip-add | Existing P0.5 add_embedding handles None per `if embedding is not None:` check (verification needed at Plan v1) |
| **P0.S7 privacy_critical CI** | Vision-related tests don't carry privacy_critical marker | No interaction |
| **P0.R6** (process pool executor) | Future cycle moves heavy ML to process pool; P0.R1's lazy CPU session would migrate to worker process state | Banked; P0.R1 stays single-process compatible |

---

## §6. Pre-mortem (10 failure modes)

1. **CPU EP not available in onnxruntime install** — fallback fails entirely; log + return None + caller treats as recognize-miss. Mitigated by D1 Anchor 4 + the existing `_background_vision_loop` graceful handling of empty embeddings.
2. **Memory pressure when both CUDA + CPU sessions resident** — accept ~80MB extra one-time cost; documented limitation.
3. **CPU embedding numerical drift vs CUDA** — same ONNX model weights + same preprocessing; numerical equivalence within float32 precision. Recognition threshold tolerance (0.28) absorbs any drift well under 1%.
4. **CUDA OOM during CPU session build (rare)** — log second-tier + return None; process continues with vision degraded for that turn.
5. **Lazy build race (two threads hit CUDA failure simultaneously)** — `_session.run` releases GIL during inference, but `_cpu_session = ...` assignment is GIL-protected. Two threads might both BUILD the CPU session before either caches it; second build wastes ~1s. Acceptable; not a correctness issue. Plan v1 may add `threading.Lock` if observed in practice.
6. **CUDA recovery** — not in P0.R1 scope; stay on CPU once fallback fires until process restart. P0.R2 territory.
7. **Anti-spoof + face match both call embed()** — both paths use same FaceEmbedder instance; fallback transparent. No additional wiring needed.
8. **Test isolation** — mocking `session.run` on FaceEmbedder via `monkeypatch.setattr(_session, "run", lambda *a, **k: raise_runtime())` requires careful fixture (need to access `_session` private attr); architect lean: refactor to expose `_session` as `session` property if needed for test cleanliness.
9. **Broad `except Exception` vs specific exception list** — broad catch is safer (catches `RuntimeError`, `ort.OrtException`, future onnxruntime exception classes); narrow catch could miss new failure modes. Architect lean: broad backstop.
10. **Concurrent embed() calls during fallback build** — first call builds CPU session (~1s); concurrent calls during build would see `_cpu_session is None` and ALSO try to build. Race acceptable per (5) above; not load-bearing.

---

## §7. Multi-direction invariant trace

### D1 forward invariant
After D1: every `embed()` call either (a) returns CUDA embedding successfully, (b) returns CPU embedding via lazy fallback, OR (c) returns None on cascading failure. NO code path raises RuntimeError out of `embed()`.

### D1 inverse invariant
After D1: no code in `core/vision.py::FaceEmbedder.embed()` bypasses the try/except. Future refactor that adds a bare `self._session.run(...)` call OUTSIDE the wrap would fail the D1 Anchor 1 source-inspection test.

### D1 corner case — cascading failure
After D1: when BOTH CUDA AND CPU paths fail, `embed()` returns `None`. Caller (`recognize()` and `add_embedding()`) must handle None safely. Plan v1 §1 Pass-2 grep verifies caller behavior.

### D1 lazy build singleton invariant
After D1: `self._cpu_session` is built AT MOST ONCE per FaceEmbedder instance. Subsequent CUDA failures reuse the cached CPU session. No D1-Anchor enforces this (would require call-counting test) — left as documented behavior, not invariant-tested.

---

## §8. Open questions for auditor (4)

- **Q1 — Bundle P0.R1 + P0.R2 or split per stubs?** Architect lean: **SPLIT**. P0.R1 closes the immediate crash-surface with lazy/per-call fallback (single D-decision; SMALL-band). P0.R2 then layers proactive provider-switching + CUDA retry timer on top. Matches parent stubs' design intent.

- **Q2 — Failure log shape?** Architect lean: **mirror Smart-Turn** — `[Vision] AdaFace inference failed: {e}, falling back to CPU`. Tier-2 log on cascading CPU failure: `[Vision] AdaFace CPU fallback also failed: {e2}`. Both via `print()` (pipeline's tee captures to stdout + terminal_output.md per Session 81 archive hook).

- **Q3 — CPU session lifecycle?** Architect lean: **lazy build + singleton cache as instance attribute** (`self._cpu_session`). Build once on first CUDA failure (~1s build cost); cache for process lifetime; memory cost ~80MB extra ONNX session. Build/destroy per failure would be unacceptable UX (~1-2s rebuild latency per failed turn).

- **Q4 — Fallback signal semantics?** Architect lean: **return CPU embedding normally** (the whole point of fallback). Brain doesn't need to know which provider produced the embedding — same model weights, numerically equivalent. On cascading CPU failure: return `None` (caller treats as recognize-miss via existing `if embedding is not None:` paths).

---

## §9. Q5 baseline estimation

**Auditor mid: 4 anchors** (NARROW band [3.4, 4.6]; only EXACT 4 qualifies ON-TARGET — same NARROW-band pattern as P0.B6 + P0.S8).

Anchor breakdown:
- D1 source-inspection (try/except + CPU-EP construction pattern): 1
- D1 source-inspection (failure log substring): 1
- D1 behavioral (CUDA-OOM → CPU fallback returns embedding): 1
- D1 behavioral (cascading CUDA+CPU failure → returns None): 1
- **Total: 4 anchors at exact mid.**

Q5 prediction: 4 anchors at closure = 0% ON-TARGET. 6th consecutive 0% exact-mid streak candidate per `Doctrine-prediction-precision-improving-over-arc` sub-observation (extends streak from 5+ to 6+ if closure-actual = 4).

---

## §10. Sub-pattern A status

P0.R1 premise is **partially accurate** (1/2 ONNX call sites wrapped, 1/2 unwrapped). NOT a wrong-premise catch — the premise's "every session.run()" claim was inaccurate but the REMAINING work is real (vision.py wrap + CPU-EP fallback). Distinct from P0.S10/P0.S11/P0.8 WONTFIX cluster (where work was fully complete at prior cycles).

**No sub-pattern A 13th instance candidacy at P0.R1.** Real cycle with real work scope.

`Tracking-row-stays-open-post-completion` not applicable — P0.R1 row never carried `[VERIFY]` tag; the unwrapped vision.py site was genuinely pending.

---

## §11. Twin-filename pitfall check (14th preventive event candidate)

Pass-2 grep at audit drafting:
- `tests/p0_r1_*.md` — zero pre-existing files. ✓ Clean disambiguation.
- `tests/p0_r*_*.md` (other P0.R-track artifacts) — zero pre-existing P0.R files. Entire P0.R track is greenfield.

14th preventive event of `### Twin-filename-pitfall-prevention` (after P0.S10's 12th + P0.S11's 13th preventive events earlier today). Doctrine instance count holds at 7 per locked enumeration rule.

---

## §12. Verdict + handoff

**Architect prediction:** Plan v1 absorbs all 4 architect leans (Q1-Q4) proactively; auditor returns 0 precision items at Plan v1 review → 8th OPTIONAL-Plan-v2 path proof case candidate under absorbed sub-rule (extending P0.S3 + P0.B3 + P0.B5 + P0.B6 + P0.S8 + P0.S9-ESCALATED-DOESN'T-COUNT track; would be 6th genuine proof case since P0.S9 escalated to Plan v2).

**Discipline counts at Phase 0 close:**
- Spec-first review cycle: 62 → 63
- Strict-industry-standard mode: 52 → 53 applications + 15 closures
- `### Grep-baseline-before-drafting`: 19 → 20
- Spec-time grep-verification: 29 → 30
- Cross-cycle-handoff transparency precedent: 25 → 26
- `### Twin-filename-pitfall-prevention`: 7 + 4 op rules (stays; 14th preventive event)

**Next:** auditor Phase 0 verdict.
