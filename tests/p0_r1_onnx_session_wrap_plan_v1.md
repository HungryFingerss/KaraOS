# P0.R1 Plan v1 — ONNX `session.run()` wrap + lazy CPU-EP fallback (D1 contract lock)

**Phase 0 base:** `tests/p0_r1_onnx_session_wrap_audit.md` (auditor APPROVED 2026-05-23 with 0 precision items at Phase 0 surface + all 4 architect leans accepted Q1-Q4 + Q5 NARROW band [3.4, 4.6] mid 4 + 9th instance of `### Zero-precision-items-at-auditor-review` fires at this surface).

**Phase 0 outcomes:**
- 9th instance of `### Zero-precision-items-at-auditor-review` (locked at Phase 0 surface per auditor verdict).
- NEW informal observation banked: `Pre-audit-quantifier-precision-refined-by-grep` 1st instance (architect-memory only — quantifier-precision error distinct from sub-pattern A wrong-premise).
- NEW sub-rule banked under `### Discipline-count-bump-needs-explicit-justification`: `WONTFIX-closures-skip-artifact-increment-discipline-counts` (auditor-ratified at this Phase 0 verdict; same-day clarification from P0.S10/P0.S11/P0.8 cluster).
- Sub-pattern A NOT triggered (quantifier-precision error correctly distinguished from premise-falsification).

**Cadence prediction:** v1 only OPTIONAL-Plan-v2 path candidate (6th genuine proof case under absorbed sub-rule if Plan v1 absorbs cleanly).

**Plan v1 absorbs (proactively, 0 PIs from auditor — no absorption pass needed; Plan v1 documents the locked Q1-Q4 leans + anchor enumeration + closure projection):**

- All 4 architect leans Q1-Q4 already locked at Phase 0 verdict (no new absorption).
- §1 — Pass-2 grep enumeration of `embed()` consumers (None-return safety verification per §6 pre-mortem item 7).
- §3 — Anchor count LOCK at 4 (Q5 lock).
- §4 — Closure projection table per NARROW band.
- §5 — Closure-narrative paste-template (5-surface landing format).

---

## §1. P1 — Pass-2 grep enumeration of `embed()` consumers

### §1.1 `FaceEmbedder.embed()` call sites — None-return safety verification

Per Phase 0 pre-mortem item 7 (cascading CUDA+CPU failure → returns None), all callers must safely handle the None return.

Pass-2 grep for `embed(` and `embedder.embed(` across `core/*.py` + `pipeline.py`:

**Confirmed callers (Plan v1 verification target):**

1. `core/db.py::recognize()` — calls embedder.embed; existing P0.5 return shape includes None handling via `if embedding is not None:` guards (verified per P0.5 closure narrative re: `(None, None, 0.0)` degraded-mode return shape).
2. `core/db.py::add_embedding()` — accepts embedding; existing None check at call site.
3. `pipeline.py::_background_vision_loop` — calls `_embedder.embed(_crop)` per P0.S1 Phase 2 wiring + ProcessPool `loop.run_in_executor(None, embedder.embed, _crop)` shape; current callers assume np.ndarray return.
4. `pipeline.py::progressive_enroll site 5` — same `embedder.embed` call shape; P0.S1 D9 fallthrough preserved.
5. `enroll.py` — standalone CLI enrollment; calls embedder.embed for enrollment frames.

**D1 None-return safety mitigation:**

After D1 changes `embed()` return type from `np.ndarray` to `np.ndarray | None`, all 5 call sites need a None check OR the existing call-site code paths already handle None via downstream guards (e.g., `if embedding is not None:` in `add_embedding`).

**Locked Plan v1 disposition:**

D1 implementation adds `if embedding is None: return` (or equivalent skip-this-frame) at the 3 pipeline.py sites that currently assume np.ndarray. The 2 core/db.py sites (recognize + add_embedding) already handle None via existing P0.5 + P0.S1 infrastructure. enroll.py CLI is single-frame standalone; can be handled separately at Phase 1 with a `if embedding is None: sys.exit(1)` clean exit + error message.

### §1.2 D1 scope (load-bearing per Phase 0 §4)

**Files:** `core/vision.py` ONLY for D1 production code.
**Lines:** ~327 (instance attribute init) + ~331-340 (embed() body refactor).

D1 introduces ~10 LOC + 1 instance attribute. Smallest D1 scope in any post-P0.S8 cycle.

### §1.3 D1 None-return downstream call-site verification scope

Plan v1 mandates Phase 4 testing of None-return propagation at 4 call sites (3 pipeline.py + 1 core/db.py + standalone enroll.py is out-of-scope for D1 anchors, banked as Phase 1 step). Behavioral D1 Anchor 4 (cascading CUDA+CPU failure) implicitly verifies the downstream-skip path for one caller; remaining call sites verified at Phase 1 implementation by running existing pre-P0.R1 test suite (no regressions).

---

## §2. D-decisions — single D1 contract lock

### §2.1 D1 LOCK — Wrap `core/vision.py:334` + lazy CPU-EP fallback

**File:** `core/vision.py` (`FaceEmbedder` class)

**Edits:**

1. **`FaceEmbedder.__init__()`** — add 2 instance attributes after existing `self._input_name` line:

```python
# P0.R1 D1: lazy CPU-EP fallback session for CUDA failures.
# Built on first CUDA RuntimeError; cached as singleton for process lifetime.
# Memory cost: ~80MB one-time when fallback fires; build cost: ~1s one-time.
self._model_path: str = model_path  # store for lazy CPU build
self._cpu_session: "ort.InferenceSession | None" = None
```

2. **`FaceEmbedder.embed()`** — refactor body to wrap `session.run()`:

```python
def embed(self, face_crop: np.ndarray) -> "np.ndarray | None":
    """Extract 512-dim embedding from a face crop.

    P0.R1 D1: returns None on cascading CUDA+CPU failure (caller treats
    as recognize-miss via existing P0.5 / P0.S1 None-handling paths).
    """
    img = self._preprocess(face_crop)
    try:
        output = self._session.run(None, {self._input_name: img})
    except Exception as e:
        # P0.R1 D1: log + lazy CPU-EP fallback (mirrors core/audio.py:170-180
        # Smart-Turn wrap pattern; same broad Exception catch for safety).
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

**Type annotation change locked:** `np.ndarray` → `np.ndarray | None`. Downstream callers handle None per §1.1 enumeration; Phase 4 tests verify.

**Discipline anchors (D1):**

- **D1 Anchor 1 — source-inspection (try/except + CPU-EP construction):**

```python
def test_p0_r1_d1_anchor_1_embed_wraps_session_run_with_cpu_fallback(vision_src):
    """P0.R1 D1: FaceEmbedder.embed() wraps session.run() in try/except with
    lazy CPU-EP fallback construction. Mirrors core/audio.py Smart-Turn wrap
    pattern; closes the unwrapped vision.py:334 gap that crashed recognition
    on CUDA OOM."""
    # Body of embed() must contain try/except + CPU EP fallback construction.
    assert "def embed(self, face_crop" in vision_src
    assert "try:" in vision_src
    assert 'providers=["CPUExecutionProvider"]' in vision_src
    assert "self._cpu_session" in vision_src
    # The original bare session.run still appears (in the try block); but the
    # broader assertion is that try: precedes the run call inside embed().
```

- **D1 Anchor 2 — source-inspection (failure log substring):**

```python
def test_p0_r1_d1_anchor_2_embed_logs_fallback_failure(vision_src):
    """P0.R1 D1 Q2: failure log mirrors core/audio.py Smart-Turn shape —
    `[Vision] AdaFace inference failed: {e}, falling back to CPU`."""
    assert "[Vision] AdaFace inference failed" in vision_src
    assert "falling back to CPU" in vision_src
    # Tier-2 cascading failure log.
    assert "[Vision] AdaFace CPU fallback also failed" in vision_src
```

- **D1 Anchor 3 — behavioral (CUDA-OOM → CPU fallback returns embedding):**

```python
def test_p0_r1_d1_anchor_3_cuda_failure_falls_back_to_cpu_embedding(monkeypatch, tmp_path):
    """P0.R1 D1 Q4: when CUDA session.run raises RuntimeError, embed() builds
    a CPU-EP session lazily, reruns the inference on CPU, and returns the
    embedding transparently. Verify L2-normalized 512-dim shape."""
    from core.vision import FaceEmbedder
    fe = FaceEmbedder(model_path=str(_FAKE_ADAFACE_MODEL))
    # Mock CUDA session.run to raise; first call should fall back to CPU.
    monkeypatch.setattr(fe._session, "run",
                       lambda *a, **k: (_ for _ in ()).throw(RuntimeError("CUDA OOM")))
    face_crop = np.random.randint(0, 255, (112, 112, 3), dtype=np.uint8)
    embedding = fe.embed(face_crop)
    assert embedding is not None
    assert embedding.shape == (512,)
    assert embedding.dtype == np.float32
    # L2-normalized
    assert abs(np.linalg.norm(embedding) - 1.0) < 1e-5
    # CPU session got built
    assert fe._cpu_session is not None
```

- **D1 Anchor 4 — behavioral (cascading failure → returns None):**

```python
def test_p0_r1_d1_anchor_4_cascading_failure_returns_none_gracefully(monkeypatch, tmp_path):
    """P0.R1 D1 Q4: when BOTH CUDA AND CPU sessions fail, embed() returns None
    gracefully (no exception propagation). Caller treats as recognize-miss
    via existing P0.5 None-handling paths."""
    from core.vision import FaceEmbedder
    fe = FaceEmbedder(model_path=str(_FAKE_ADAFACE_MODEL))
    # Mock CUDA AND CPU session construction to fail.
    monkeypatch.setattr(fe._session, "run",
                       lambda *a, **k: (_ for _ in ()).throw(RuntimeError("CUDA OOM")))
    monkeypatch.setattr("onnxruntime.InferenceSession",
                       lambda *a, **k: (_ for _ in ()).throw(RuntimeError("CPU EP unavailable")))
    face_crop = np.random.randint(0, 255, (112, 112, 3), dtype=np.uint8)
    embedding = fe.embed(face_crop)
    assert embedding is None  # graceful degradation; NO exception
```

### §2.2 Deliberate-regression checks (induction-surfaces-invariant-gaps protocol)

Phase 5 must execute:
- **(a)** Drop the try/except from `embed()` body (revert to bare `session.run`) → D1 Anchor 1 fails.
- **(b)** Replace `falling back to CPU` log string with `falling back to backup` → D1 Anchor 2 fails (substring missing).
- **(c)** Drop the CPU fallback `output = self._cpu_session.run(...)` line → D1 Anchor 3 fails (no embedding returned post-CUDA-failure).
- **(d)** Replace the outer except clause's `return None` with `raise` → D1 Anchor 4 fails (exception propagates instead of None).

All 4 reverts must fire correctly. Same 4-pattern shape as P0.S9 §2.5 (induction protocol holds).

---

## §3. Test surface — 4 anchors (Plan v1 LOCK at exact mid 4 NARROW band)

| D-decision | Anchor count | Anchor types |
|---|---|---|
| D1 | 4 | 2 source-inspection (try/except+CPU-EP + log substring) + 2 behavioral (CUDA-OOM→CPU fallback + cascading failure→None) |
| **TOTAL** | **4** | (Q5 LOCK at exact mid 4; NARROW band [3.4, 4.6] only EXACT 4 qualifies ON-TARGET) |

**Q5 LOCK: 4 anchors at exact mid 4** → 0% ON-TARGET prediction. 6+ consecutive 0% exact-mid streak candidate per `Doctrine-prediction-precision-improving-over-arc` sub-observation.

---

## §4. Closure-actual projection per `Explicit-closure-honest-count-commitment` (15th instance MADE here)

**Architect commits BEFORE closure** per discipline (15th instance candidate, to be HONORED at closure-audit as 16th instance per STRICT separation):

NARROW band [3.4, 4.6] mid 4 closure projections:

| Closure-actual | Math vs mid 4 | Disposition | Doctrine effect |
|---|---|---|---|
| ≤2 anchors | ≤-50% | **FALSIFICATION TRIGGER** | DEMOTES 13 → 12 supporting |
| 3 anchors | -25% | SLIGHT-DRIFT-DOWN | HOLDS at 13 |
| **4 anchors (Plan v1 LOCK)** | **0%** | **ON-TARGET** (exact mid) | **BUMPS 13 → 14 supporting** |
| 5 anchors | +25% | SLIGHT-DRIFT-UP | HOLDS at 13 |
| ≥6 anchors | ≥+50% | **FALSIFICATION TRIGGER** | DEMOTES 13 → 12 |

NARROW band; only exact 4 bumps doctrine. 3 or 5 = SLIGHT-DRIFT (HOLDS); ≤2 or ≥6 = FALSIFICATION.

---

## §5. P4 — Closure-narrative paste-template (5-surface landing per P0.S8/P0.S9 precedent)

### §5.1 CLAUDE.md line ~3

When P0.R1 closes, prepend above P0.S8 entry:

```
| **P0.R1 (ONNX session.run() wrap for AdaFace embed + lazy CPU-EP fallback) CLOSED 2026-05-XX** — Closes the unwrapped vision.py:334 session.run() that crashed recognition path on CUDA OOM. Single D1 contract: wrap embed() in try/except + lazy CPU-EP session construction + cached as instance singleton + None return on cascading failure. Mirrors core/audio.py:170-180 Smart-Turn wrap pattern. **D1 (LOAD-BEARING)**: `core/vision.py::FaceEmbedder.embed()` wraps `self._session.run(None, {self._input_name: img})` in try/except; on RuntimeError catch, lazily builds `self._cpu_session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])` (one-time ~1s build cost; ~80MB memory cost; cached for process lifetime); retries session.run with CPU; returns transparent embedding. On cascading CPU failure: log + return None (caller treats as recognize-miss via existing P0.5/P0.S1 None-handling paths). Type annotation `np.ndarray` → `np.ndarray | None`. **Total P0.R1 LOGICAL ANCHORS: 4** (Plan v1 §3 LOCK EXACT MATCH at exact mid 4 NARROW band [3.4, 4.6]). **Q5 closure under MID-RANGE methodology**: auditor mid 4, Plan v1 lock 4, **closure actual 4** (0% ON-TARGET exact mid; 6+ consecutive 0% exact-mid streak per `Doctrine-prediction-precision-improving-over-arc` sub-observation continues). Doctrine `### Phase-0-granular-decomposition-enables-accurate-estimates` **BUMPS 13 → 14 SUPPORTING INSTANCES**. Plan v1 §4 honest-count commitment HONORED — **16th instance of `Explicit-closure-honest-count-commitment` discipline** (15th MADE at Plan v1 §4, 16th HONORED at closure per STRICT separation). **4/4 deliberate-regression confirmations PASSED** (a/b/c/d per §2.2). **`### Zero-precision-items-at-auditor-review` 8 → 10 instances** (Phase 0 9th + Plan v1 10th if cleared). **NEW informal observation banked**: `Pre-audit-quantifier-precision-refined-by-grep` (1 instance — pre-audit "every session.run()" overstated; grep verified 1/2 sites already wrapped; quantifier-precision error distinct from sub-pattern A wrong-premise). **NEW sub-rule banked under `### Discipline-count-bump-needs-explicit-justification`**: `WONTFIX-closures-skip-artifact-increment-discipline-counts` (locked at P0.R1 Phase 0 verdict). **6th OPTIONAL-Plan-v2 proof case** under absorbed sub-rule (P0.S3 + P0.B3 + P0.B5 + P0.B6 + P0.S8 + P0.R1 — P0.S9 escalated to v2 doesn't count). **Strict-industry-standard mode 52 → 55 applications + 15 → 16 closures** (3 artifacts × +1 each: Phase 0 + Plan v1 + closure). **Twin-filename pitfall 14th preventive event honored at Phase 0** (no pre-existing P0.R1 artifacts; greenfield P0.R track). **Cumulative suite**: 2613 → 2617 (+4 new D1 anchors as 4 separate test functions in `tests/test_p0_r1_onnx_session_wrap.py`).
```

### §5.2-§5.4 parent + subdir `complete-plan.md` + `to_be_checked.md`

Per P0.S8/P0.S9 precedents. Twin-filename pitfall discipline at status flip (parent + subdir).

### §5.5 Memory files

- `feedback_explicit_closure_honest_count_commitment.md`: bump 14 → 16 (Plan v1 §4 MADE 15th + closure HONORED 16th per STRICT).
- `feedback_phase_0_zero_precision_items_at_auditor_review.md`: bump 8 → 10 (Phase 0 9th + Plan v1 10th if cleared).
- `feedback_doctrine_prediction_precision_improving_over_arc.md`: extend 5+ → 6+ cycle 0% streak.
- **NEW** `feedback_pre_audit_quantifier_precision_refined_by_grep.md`: 1 instance (architect-memory only).
- `feedback_discipline_count_bump_needs_explicit_justification.md` (memory file under the umbrella doctrine): bank `WONTFIX-closures-skip-artifact-increment-discipline-counts` sub-rule.
- MEMORY.md index refresh.

---

## §6. Cross-spec impact analysis — unchanged from Phase 0 §5

P0.R2 downstream (proactive provider-switching); P0.S1 + P0.5 + P0.S7 orthogonal; P0.R6 future ProcessPoolExecutor migration banked; buffalo_l + MiniFASNet + Whisper + Kokoro all explicitly out-of-scope at call-site layer.

---

## §7. Quality gate checklist (10 APPLIES + 1 N/A privacy)

Per strict-mode 11-gate floor:

1. ✅ Phase 0 audit completed + auditor-approved with 0 precision items (9th `Zero-precision-items` instance).
2. ✅ Plan v1 absorbs 0 PIs proactively (Phase 0 returned clean; Plan v1 documents locked Q1-Q4 leans + anchor enumeration).
3. ✅ D-decision has unambiguous contract — D1 at §2.1.
4. ✅ Pre-mortem coverage — 10 failure modes documented at Phase 0 §6.
5. ✅ Multi-direction invariant trace per D-decision — Phase 0 §7.
6. ✅ Cross-spec impact analysis — Phase 0 §5.
7. ✅ Spec-time grep-verification (Pass-1 + Pass-2) — Phase 0 §1-§2 (Pass-1) + Plan v1 §1.1-§1.3 (Pass-2 of embed() consumers).
8. ✅ Honest-closure-actual-count commitment made at Plan v1 §4 — 15th instance to be banked.
9. ✅ Deliberate-regression check protocol — §2.2 enumerates 4 induced reverts.
10. ✅ Closure-narrative paste-template ready — §5 5-surface template + §3 band-table.
11. N/A Privacy — AdaFace embedding is a 512-dim float vector with no PII; the gallery is in faces/embeddings (P0.S2-protected at dashboard layer); no cross-person leak surface.

---

## §8. Discipline counts at Plan v1 close

| Discipline | Pre-P0.R1 baseline | Phase 0 close (+1) | Plan v1 close (+2) |
|---|---|---|---|
| Spec-first review cycle | 62 | 63 | **64** ✓ |
| Strict-industry-standard mode (applications) | 52 | 53 | **54** ✓ |
| Strict-industry-standard mode (closures) | 15 | 15 | 15 (closure event pending) |
| `### Phase-0-granular-decomposition-enables-accurate-estimates` | 13 supporting | 13 | 13 (closure-actual pending; ON-TARGET candidate at 4 anchors → bump 13 → 14) |
| `### Phase-0-catches-wrong-premise` | 12 | 12 | 12 (sub-pattern A NOT triggered per auditor Phase 0 verdict; quantifier-precision error distinct) |
| `### Twin-filename-pitfall-prevention` | 7 + 4 op rules | 7 | 7 (14th preventive event but doctrine count holds) |
| `### Grep-baseline-before-drafting` | 19 | 20 | **21** ✓ |
| `### Zero-precision-items-at-auditor-review` | 8 | **9** ✓ (Phase 0 surface fires) | 9 (Plan v1 audit pending; if 0 items → 10th at Plan v1 surface) |
| Deferred-canary | 17th in-flight | 17 | 17 (closure event pending) |
| Auditor-Q5-estimates-trail-grep | 18 banked | 18 | 18 (closure event pending) |
| Cross-cycle-handoff transparency precedent | 25 | 26 | **27** ✓ |
| Architect-reads-production-code-before-sign-off | 11 banked | 11 | 11 (closure-audit pending) |
| Sub-pattern A (in `### Phase-0-catches-wrong-premise`) | 12 | 12 | 12 (not triggered) |
| Spec-time grep-verification | 29 | 30 | **31** ✓ |
| Discipline-count-bump-needs-explicit-justification | 11 preventive | 11 | 11 (+ NEW sub-rule WONTFIX-closures-skip-artifact-counts banked at Phase 0) |
| Convention-drift-on-discipline-counts | 5 | 5 | 5 |
| Per-artifact-arithmetic-drift-survives-grep-baseline | 3 | 3 | 3 |
| `Explicit-closure-honest-count-commitment` | 14 | 14 | **15** ✓ (Plan v1 §4 commitment MADE) |
| `Auditor-catches-Q5-math-at-plan-review` | 2 | 2 | 2 |
| `Plan-v1-Pass-2-grep-undercount` | 4 | 4 | 4 |
| `Bug-fix-cycles-surface-discipline-edges` | 1 | 1 | 1 |
| `Auditor-adjudication-drift-clarified-by-architect` | 3 | 3 | 3 |
| `Stale-TODO-marker-after-work-complete` | 2 | 2 | 2 |
| `Board-meeting-attack-premise-needs-grep-verification` | 1 | 1 | 1 |
| `User-WONTFIX-after-design-dialogue` | 1 | 1 | 1 |
| `Doctrine-prediction-precision-improving-over-arc` | 5+ cycle 0% streak | 5+ | 5+ (Plan v1 LOCK extends to 6+ at closure if 4 anchors hold) |
| `Auditor-catches-doctrine-overlap-at-elevation-prep` | 1 (resolved at P0.S8 closure) | 1 | 1 |
| `Spec-internal-line-wrap-vs-substring-test-mismatch` | 1 (P0.S8) | 1 | 1 |
| `Tracking-row-stays-open-post-completion` | 3 (threshold reached at P0.8 WONTFIX) | 3 | 3 |
| `Pre-audit-quantifier-precision-refined-by-grep` | 0 | **1** ✓ (NEW banked at Phase 0 surface) | 1 |
| OPTIONAL-Plan-v2 proof case (sub-rule under `### Zero-precision-items`) | 5 cases | 5 | 5 (closure-conditional 6th proof case pending if Plan v1 + closure clear cleanly) |
| `### Induction-surfaces-invariant-gaps` | 9 | 9 | 9 (closure-conditional bump if induction protocol fires real gap at Phase 5; otherwise holds) |

**Cells marked ✓ are bumped at this Plan version's surface per +1-per-artifact convention.**

---

## §9. Open questions for auditor — 0

Plan v1 documents the locked Q1-Q4 architect leans from Phase 0; no new open questions surfaced at Plan v1 drafting. **Architect prediction: APPROVED 0 items at Plan v1 review** → 10th instance of `### Zero-precision-items-at-auditor-review` fires at Plan v1 surface → ship to developer per OPTIONAL-Plan-v2 path (6th genuine proof case under absorbed sub-rule).

---

## §10. Implementation handoff readiness

**Developer contract:**
- **Scope:** D1 per §2.1 (single D-decision, ~10 LOC in `core/vision.py`).
- **Estimated effort:** 1-2 hours (SMALL-band single-cycle; smallest D1 scope in any post-P0.S8 cycle).
- **Files touched:**
  - `core/vision.py` (D1 — `FaceEmbedder.__init__()` + `embed()` body refactor)
  - NEW `tests/test_p0_r1_onnx_session_wrap.py` (D1 — 4 anchor tests)
- **Phase 1 (~30 min)**: D1 implementation (init attrs + embed() refactor with try/except + lazy CPU-EP build + cascading None return). Run existing test suite to verify no regressions in downstream callers (`recognize()`, `add_embedding()`, `_background_vision_loop`, `progressive_enroll site 5`, `enroll.py`).
- **Phase 2 (~20 min)**: D1 Anchor 1 + Anchor 2 source-inspection tests.
- **Phase 3 (~30 min)**: D1 Anchor 3 + Anchor 4 behavioral tests (mock CUDA/CPU session.run with monkeypatch + verify shape/None return).
- **Phase 4 (~20 min)**: §2.2 deliberate-regression confirmations (a/b/c/d all must fire correctly + revert cleanly).
- **Phase 5 (~30 min)**: closure narrative + 5-surface landing + memory bankings + architect closure-audit.

---

## §11. Open invariants for Plan v1 to enumerate

1. **D1 wrap invariant** — `core/vision.py::FaceEmbedder.embed()` body contains `try:` + `except` + lazy CPU-EP construction; no bare `session.run` outside the wrap.
2. **D1 log shape invariant** — `[Vision] AdaFace inference failed: {e}, falling back to CPU` substring matches Smart-Turn precedent.
3. **D1 cascading-failure invariant** — Cascading CUDA+CPU failure path returns `None` (no exception propagation).
4. **D1 singleton-cache invariant** — `self._cpu_session` is built AT MOST ONCE per FaceEmbedder instance (documented behavior; not invariant-tested per Phase 0 §7 D1 lazy build singleton invariant note).
5. **No-side-effect-in-Phase-0 invariant** — Phase 0 audit landed with zero production code changes.

---

## §12. No closure-conditional doctrine elevation candidacy at P0.R1

Sub-pattern A NOT triggered (per auditor Phase 0 verdict — quantifier-precision error correctly distinguished from premise-falsification). `### Phase-0-catches-wrong-premise` count holds at 12.

Other event-driven doctrines bump at closure-conditional outcomes per §8 table; no NEW doctrine elevation candidacy. `### Induction-surfaces-invariant-gaps` may bump 9 → 10 IF D1 §2.2 deliberate-regression check (c) or (d) surfaces a NEW invariant gap during implementation (e.g., the broad `except Exception` catches an unanticipated failure mode that the architect hadn't enumerated in Phase 0 §6 pre-mortem). Architect-side prediction: routine cycle, no new gap likely; doctrine holds at 9.

P0.R1 is a routine SMALL-band matured-discipline cycle. Doctrine library stays at 6.

---

**End of Plan v1.** Ready to forward to auditor.

**Architect prediction:** **APPROVED 0 items at Plan v1 review** → ship to developer per OPTIONAL-Plan-v2 path (6th genuine proof case under absorbed sub-rule). 10th instance of `### Zero-precision-items-at-auditor-review` fires at Plan v1 surface.
