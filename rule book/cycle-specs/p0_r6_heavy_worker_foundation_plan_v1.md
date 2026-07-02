# P0.R6 — Heavy-task worker foundation + AdaFace migration — Plan v1

**Status:** Plan v1 drafted 2026-05-24 with Q1-Q8 locked + PI #1 absorbed (D3 enumeration drift; auditor's Option α — expand to all 4 async-hot-path sites). APPROVED-AT-AUDITOR-REVIEW pending.

**Parent audit:** `tests/p0_r6_heavy_worker_foundation_audit.md` (Phase 0 ACCEPTED with 1 BLOCKING PI + multiple non-blocking observations + NEW CLAUDE.md doctrine elevation candidacy activated).

---

## §1 — Phase 0 reconciliation

**§1.1 PI #1 absorbed per Option α (auditor's lean) — D3 EXPANDED to all 4 async-hot-path AdaFace sites:**

Architect's Phase 0 §1.1 listed 2 AdaFace call sites (lines 2569 + 2663). Auditor's independent re-grep of `embedder\.embed\(` revealed 6 distinct call sites — 4 in async hot paths (2 currently unmigrated; sync direct calls blocking the asyncio loop). Expanded enumeration:

| # | Line | Pattern | Function context | Async hot path? | D3 disposition |
|---|---|---|---|---|---|
| 1 | 2569 | `await loop.run_in_executor(None, embedder.embed, _crop)` | `_background_vision_loop` | ✓ already wrapped | **D3 IN-SCOPE — migrate to `hw.run_heavy("adaface_embed", ...)`** |
| 2 | 2663 | `await loop.run_in_executor(None, embedder.embed, _crop)` | `_background_vision_loop` | ✓ already wrapped | **D3 IN-SCOPE — migrate** |
| 3 | 3474 | `embedding = embedder.embed(face_crop)` | `first_boot_flow` | sync boot flow | **D3 OUT-OF-SCOPE** — sync flow; doesn't block asyncio loop |
| 4 | 3551 | `embedding = embedder.embed(face_crop)` | `enrollment_flow` | sync enrollment flow | **D3 OUT-OF-SCOPE** — sync flow; doesn't block asyncio loop |
| 5 | **6716** | `raw_embedding = embedder.embed(face_crop)` | **background scan async path** | ✗ **async-hot-path SYNC DIRECT CALL — currently BLOCKS asyncio loop** | **D3 IN-SCOPE — migrate (NEW per PI #1 absorption)** |
| 6 | **7112** | `_emb = embedder.embed(crop)` | **camera fallback path** | ✗ **async-hot-path SYNC DIRECT CALL — likely BLOCKS asyncio loop** | **D3 IN-SCOPE — migrate (NEW per PI #1 absorption)** |

**D3 IN-SCOPE: 4 sites** (2569 + 2663 + 6716 + 7112) — all async-hot-path; all migrate to `hw.run_heavy("adaface_embed", ...)` per the foundation contract.

**D3 OUT-OF-SCOPE: 2 sites** (3474 + 3551) — sync boot/enrollment flows; don't block asyncio loop; rationale documented in §2.4 below.

**§1.2 Q1-Q8 lock summary per auditor verdict 2026-05-24:**

| Q | Lock |
|---|---|
| Q1 | **(a) Decompose** RATIFIED — P0.R6 ships foundation + AdaFace; P0.R6.X-Z subsequent migrations |
| Q2 | **(a) AdaFace first** RATIFIED |
| Q3 | **(a) Pickle** for foundation cycle |
| Q4 | **(a) Persistent workers** + max_workers=1 per task |
| Q5 | **10 anchors at exact mid 10** inclusive ±15% band [8.5, 11.5] — A4 broadened per PI #1 (covers all 4 async sites instead of 2); anchor count stays at 10 |
| Q6 | **(a) Explicit spawn** for cross-platform consistency |
| Q7 | DOCUMENT + DEFER — foundation cycle ~100MB VRAM addition acceptable |
| Q8 | **(a) Hybrid** source-inspection + CUDA-gated behavioral |

**§1.3 Diligent Pass-2 grep enumeration (per `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` doctrine + lessons learned from Phase 0 PI #1):**

Files affected by P0.R6 foundation cycle:

| Path | Edit type | D-decision | Notes |
|---|---|---|---|
| `core/heavy_worker.py` | NEW file (~120-180 LOC) | D1 + D2 | ProcessPoolExecutor wrapper + AdaFace worker bootstrap |
| `pipeline.py` lines 2569 + 2663 + 6716 + 7112 | EDIT (4 sites; D3 migration per PI #1 expansion) | D3 | All 4 async-hot-path sites converted from `loop.run_in_executor(None, embedder.embed, ...)` → `hw.run_heavy("adaface_embed", hw.adaface_embed_worker, ...)` |
| `pipeline.py` lines 3474 + 3551 | UNCHANGED (sync boot/enrollment flows; D3 OUT-OF-SCOPE per §1.1) | n/a | Out-of-scope rationale documented at §2.4 |
| `core/pipeline_state_store.py` | EDIT (+1 field `heavy_worker_status: dict[str, str]` + setter/peeker) | D4 | Health observability |
| `core/health.py` | EDIT (HealthSnapshot field + format_health_line conditional + format_health_alerts) | D4 | Conditional emit + actionable alert |
| `pipeline.py::run()` startup + shutdown | EDIT (worker pool spawn before vision task + shutdown finally cancel) | D5 | Lifecycle wiring |
| `tests/test_p0_r6_heavy_worker_foundation.py` | NEW file (~150-200 LOC) | D6 | 10 anchors |

**Auditor verification target**: all 4 async-hot-path AdaFace sites migrated (NOT just 2); A4 anchor verifies via AST scan.

**§1.4 NEW CLAUDE.md doctrine elevation event at P0.R6 closure-audit (ratified at Phase 0 verdict):**

`### Pre-audit-quantifier-precision-refined-by-grep` doctrine ELEVATION CANDIDACY ACTIVATED at P0.R6 Phase 0 per 5-instance threshold + 4-criteria adjudication. Doctrine library expands from 7 → 8 numbered doctrines at P0.R6 closure-audit landing event (same shape as `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` elevation at P0.R4 closure). Auditor-proposed doctrine body verbatim per Phase 0 verdict — architect-handoff item for closure-narrative drafting.

**§1.5 Cross-spec orthogonality verified clean** (unchanged from Phase 0 §1.3 + §3):

- P0.R1 D1 None-return fallback preserved inside worker subprocess
- P0.R2 vision_provider_state independent per-subprocess (subprocess gets own CUDA context)
- P0.R3 vision watchdog interaction: worker startup BEFORE vision task per D5 ordering (watchdog never sees worker-startup-induced staleness)
- P0.R5 vendored pyannote orthogonal (subsequent P0.R6.Z benefits but unrelated this cycle)

**§1.6 Twin-filename pitfall 20th preventive event already honored at Phase 0 audit drafting** (no doctrine count bump per locked enumeration rule).

---

## §2 — D-decision contracts (LOCKED per Q1-Q8 verdicts + PI #1 absorption per Option α)

### §2.1 D1 — NEW `core/heavy_worker.py` module (UNCHANGED from Phase 0 §2.1)

LOCKED spec unchanged. See Phase 0 audit §2.1.

### §2.2 D2 — Worker bootstrap (UNCHANGED from Phase 0 §2.2)

LOCKED spec unchanged. See Phase 0 audit §2.2.

### §2.3 D3 — Migrate AdaFace async-hot-path call sites (EXPANDED per PI #1 absorption per Option α)

**Edit sites (4 sites; LOCKED at Plan v1 per Phase 0 verdict's Option α adjudication):**

**Sites 1+2 — already-wrapped via `loop.run_in_executor` (foundation case):**

Site 1 (`pipeline.py:2569`):
```python
# BEFORE:
_raw_emb = await loop.run_in_executor(None, embedder.embed, _crop)

# AFTER:
import core.heavy_worker as hw
_raw_emb_bytes = await hw.run_heavy("adaface_embed", hw.adaface_embed_worker, _crop.tobytes(), _crop.shape)
_raw_emb = np.frombuffer(_raw_emb_bytes, dtype=np.float32) if _raw_emb_bytes is not None else None
```

Site 2 (`pipeline.py:2663`): same pattern as Site 1.

**Sites 3+4 — currently SYNC DIRECT CALLS (NEW per PI #1 absorption — converting sync→async via worker):**

Site 3 (`pipeline.py:6716`):
```python
# BEFORE (SYNC direct call inside async function — blocks asyncio loop):
raw_embedding = embedder.embed(face_crop)

# AFTER (async via worker pool; non-blocking):
raw_embedding_bytes = await hw.run_heavy("adaface_embed", hw.adaface_embed_worker, face_crop.tobytes(), face_crop.shape)
raw_embedding = np.frombuffer(raw_embedding_bytes, dtype=np.float32) if raw_embedding_bytes is not None else None
```

Site 4 (`pipeline.py:7112`): same pattern as Site 3 (`crop` variable instead of `face_crop`).

**Contract:**
- Behavioral equivalence — `embed()` returns same shape + value; only dispatch mechanism changes
- Sites 3+4 gain ASYNC non-blocking semantic (previously blocked asyncio loop with sync ~50-100ms inference)
- P0.R1 D1 None-return fallback contract preserved at all 4 sites (`raw_embedding is None` check)

**OUT-OF-SCOPE (sync boot/enrollment sites — explicitly enumerated per Option α):**

Site 5 (`pipeline.py:3474` in `first_boot_flow`): sync flow during boot; runs before asyncio loop is the bottleneck for that work. No migration needed.

Site 6 (`pipeline.py:3551` in `enrollment_flow`): sync flow during user enrollment; user-initiated, single-call latency tolerable. No migration needed.

**Rationale for OUT-OF-SCOPE classification**: both sites are SYNC functions called during single-event flows (boot OR enrollment-initiated). Not in asyncio hot path. Migrating them to worker would add subprocess startup cost without proportionate benefit. Future P0.R6.X follow-up could re-evaluate IF profiling shows blocking concerns.

### §2.4 D4 — Health observability (UNCHANGED from Phase 0 §2.4)

LOCKED spec unchanged. See Phase 0 audit §2.3 (D4 numbered).

### §2.5 D5 — Startup + shutdown wiring (UNCHANGED from Phase 0 §2.5)

LOCKED spec unchanged. See Phase 0 audit §2.5.

### §2.6 D6 — Test surface (A4 BROADENED per PI #1; anchor count preserved at 10)

A4 anchor broadened from "verify 2 async sites use hw.run_heavy" → "verify all 4 async sites (2569 + 2663 + 6716 + 7112) use hw.run_heavy". Anchor count stays at 10 (broadening, not splitting per auditor verdict Q5 NOTE).

### §2.7 Deliberate-regression protocol (6 reverts per D-decision coverage; (e) updated for D3 expanded scope)

| Revert | Removed contract | Expected fire |
|---|---|---|
| **(a)** Delete `core/heavy_worker.py` module | D1 module gone | A1 source-inspection fires (file existence) |
| **(b)** Replace `mp.get_context("spawn")` with `mp.get_context("fork")` | D1 cross-platform contract violated | A2 source-inspection fires (spawn substring missing) |
| **(c)** Change `adaface_embed_worker` from module-level to local function | D2 pickleability broken | A3 source-inspection fires (NOT at module scope) |
| **(d)** Revert site 6716 from `hw.run_heavy` back to sync `embedder.embed(face_crop)` | D3 PI #1 absorption regression (most-async-blocking site) | A4 AST scan fires (4-site enforcement) |
| **(e)** Remove `vision_degraded` → `heavy_worker_status` field from PipelineStateStore | D4 field absent | A5 source-inspection fires |
| **(f)** Reverse startup ordering: spawn vision task BEFORE worker pool | D5 ordering invariant violated | A7 AST line-order check fires |

---

## §3 — Anchor decomposition LOCK (10 anchors at exact mid 10 inclusive ±15%; A4 broadened per PI #1)

| # | D | Anchor name | Type | Plan v1 status |
|---|---|---|---|---|
| A1 | D1 | `test_p0_r6_d1_anchor_1_heavy_worker_module_exists` | source-inspection | UNCHANGED |
| A2 | D1 | `test_p0_r6_d1_anchor_2_uses_spawn_start_method` | source-inspection | UNCHANGED |
| A3 | D2 | `test_p0_r6_d2_anchor_1_adaface_worker_function` | source-inspection | UNCHANGED |
| **A4** | **D3** | **`test_p0_r6_d3_anchor_1_all_4_async_sites_use_heavy_worker`** | **source-inspection (AST)** | **BROADENED per PI #1 — verifies all 4 async-hot-path sites (2569 + 2663 + 6716 + 7112) use `hw.run_heavy("adaface_embed"`; verifies sites 3474 + 3551 ARE NOT migrated (sync boot/enrollment OUT-OF-SCOPE)** |
| A5 | D4 | `test_p0_r6_d4_anchor_1_health_snapshot_has_worker_status` | source-inspection | UNCHANGED |
| A6 | D4 | `test_p0_r6_d4_anchor_2_format_health_emits_worker_degraded` | source-inspection | UNCHANGED |
| A7 | D5 | `test_p0_r6_d5_anchor_1_startup_spawns_pool_before_vision_task` | source-inspection (AST line-order) | UNCHANGED |
| A8 | D5 | `test_p0_r6_d5_anchor_2_shutdown_cancels_pools` | source-inspection | UNCHANGED |
| A9 | D2/D3 | `test_p0_r6_d3_anchor_2_adaface_embed_via_worker_returns_correct_shape` | behavioral (CUDA-gated smoke) | UNCHANGED |
| A10 | D2 | `test_p0_r6_d2_anchor_2_worker_handles_none_return_from_embed` | behavioral (mocked) | UNCHANGED |

**Total: 10 logical anchors preserved. Mid 10 LOCK preserved per Plan v1 §3.**

---

## §4 — Honest-count commitment table (UNCHANGED from Phase 0 §6; inclusive ±15% per locked methodology)

See Phase 0 audit §6. No changes. **`Explicit-closure-honest-count-commitment` 24 → 26** (25th MADE at Plan v1 §4 + 26th HONORED at closure per STRICT separation).

---

## §5 — Closure-narrative paste-template

(Architect's pre-draft; subject to closure-actual reconciliation + Path C grep-verify discipline.)

**P0.R5 closure-actual ratified at developer Phase 5 + my closure-audit (2026-05-23) so baselines below reflect post-P0.R5-closure state:**

| Discipline | Post-P0.R5 closure baseline |
|---|---|
| Spec-first review cycle | 78 |
| Strict-mode applications | 69 |
| Strict-mode closures | 20 |
| `### Grep-baseline-before-drafting` | 36 |
| Spec-time grep-verification | 46 |
| Cross-cycle-handoff transparency | 42 |
| `### Phase-0-granular-decomposition` | 18 |
| `### Zero-precision-items-at-auditor-review` | 18 (Plan v1 18th was post-P0.R5 closure event; Phase 0 19 reached at P0.R5 closure; auditor reconciliation note) |
| `Doctrine-prediction-precision-improving-over-arc` | 10+ cycle 0% streak |
| `### Architect-reads-production-code-before-sign-off` | 17 |
| OPTIONAL-Plan-v2 sub-rule proof cases | 8 |
| `Plan-v1-Pass-2-grep-undercount` | 7 (P0.R6 Phase 0 = NEW PHASE-0-CATCHING-LAYER sub-shape) |
| `Pre-audit-quantifier-precision-refined-by-grep` | 5 (P0.R6 Phase 0 = 5-instance elevation threshold) |
| `### Twin-filename-pitfall-prevention` preventive events | 20 (P0.R6 Phase 0 = 20th preventive event) |

**P0.R6 closure note (architect pre-draft):**

> ## P0.R6 — Heavy-task worker foundation + AdaFace migration — D1+D2+D3+D4+D5+D6 + 10 anchors + 6 deliberate-regression checks + Plan v1 absorbed PI #1 (D3 EXPANDED to 4 async-hot-path sites per Option α) + NEW CLAUDE.md doctrine `### Pre-audit-quantifier-precision-refined-by-grep` elevation (library 7 → 8) + Q1 decomposition LOCKED: P0.R6.X (Whisper) + P0.R6.Y (ECAPA) + P0.R6.Z (pyannote) as subsequent specs  [CLOSED 2026-05-24]
> 
> **Sub-PR sequence:** Phase 0 audit (APPROVED with 1 BLOCKING PI — D3 enumeration drift; `Plan-v1-Pass-2-grep-undercount` 6 → 7 NEW PHASE-0-CATCHING-LAYER sub-shape + `Pre-audit-quantifier-precision-refined-by-grep` 4 → 5 LAYERED-AXIS continuation; NEW CLAUDE.md doctrine elevation candidacy activated) → Plan v1 (RATIFIED with PI #1 absorbed per Option α — D3 expanded from 2 → 4 async-hot-path sites; A4 broadened; anchor count preserved at 10; 19th instance of `### Zero-precision-items-at-auditor-review` at Plan v1 surface if clean) → Phase 1-4 implementation + closure with NEW CLAUDE.md doctrine landing.
> 
> **Cycle decomposition LOCKED per Q1 (a) RATIFIED**: P0.R6 ships foundation `core/heavy_worker.py` + AdaFace migration (4 async-hot-path sites; sync boot/enrollment sites OUT-OF-SCOPE); P0.R6.X follow-up = Whisper STT migration; P0.R6.Y = ECAPA voice ID migration; P0.R6.Z = pyannote diarization migration. Subsequent specs file as separate audits + Plan v1s + closures per the discipline pattern.
> 
> **What shipped:** NEW `core/heavy_worker.py` (~150 LOC ProcessPoolExecutor wrapper + AdaFace worker bootstrap) + `pipeline.py` D3 migration (4 sites) + `core/pipeline_state_store.py` D4 fields + `core/health.py` D4 conditional + `pipeline.py::run()` D5 startup/shutdown wiring + `tests/test_p0_r6_heavy_worker_foundation.py` D6 (10 anchors).
> 
> **D3 EXPANDED scope (per PI #1 absorption per Option α):**
> - Sites 2569 + 2663 (already-async-wrapped): migrated to `hw.run_heavy`
> - Sites 6716 + 7112 (currently SYNC DIRECT CALLS in async hot paths): migrated to `hw.run_heavy` — these are the NET-NEW asyncio-non-blocking improvements over Phase 0's narrower scope
> - Sites 3474 + 3551 (sync boot/enrollment flows): explicit OUT-OF-SCOPE; rationale documented in Plan v1 §2.4
> 
> **Total P0.R6 LOGICAL ANCHORS: 10** (Plan v1 §3 LOCK EXACT MATCH at exact mid 10 inclusive ±15% band [8.5, 11.5]). A4 broadened to verify all 4 async-hot-path sites; anchor count preserved.
> 
> **Q5 closure under MID-RANGE methodology**: auditor mid 10, Plan v1 lock 10, **closure actual {{N}}** ({{0%|−11.1%|+11.1%}}; {{exact mid|ON-TARGET}}). Doctrine `### Phase-0-granular-decomposition-enables-accurate-estimates` **BUMPS 18 → 19 SUPPORTING INSTANCES**.
> 
> **Plan v1 §4 honest-count commitment HONORED — 26th instance of `Explicit-closure-honest-count-commitment` discipline** (25th MADE + 26th HONORED per STRICT separation).
> 
> **6/6 deliberate-regression confirmations PASSED** (a/b/c/d/e/f per §2.7 with (d) UPDATED for D3 expanded scope — reverting site 6716 fires A4 AST 4-site enforcement).
> 
> **`### Zero-precision-items-at-auditor-review` doctrine 18 → 19 instances** (Plan v1 19th — Phase 0 BLOCKED by PI #1; Plan v1 absorbed cleanly per Option α). Plan-v2 NOT taken (Plan v1 cleanly absorbs; cycle proceeds as 3-artifact: Phase 0 + Plan v1 + closure).
> 
> **NEW CLAUDE.md DOCTRINE LANDED**: `### Pre-audit-quantifier-precision-refined-by-grep` per 4-criteria adjudication at P0.R6 Phase 0 verdict. Doctrine library 7 → 8 at this closure.
> 
> **`Plan-v1-Pass-2-grep-undercount` 6 → 7 instances** banked at Phase 0 verdict (NEW PHASE-0-CATCHING-LAYER sub-shape; earliest catching layer in track record).
> 
> **`Pre-audit-quantifier-precision-refined-by-grep` 4 → 5 instances** banked at Phase 0 verdict (LAYERED-AXIS 2-axis continuation TASK-COMPLETENESS + SCALE-OF-WORK).
> 
> **Strict-mode 69 → 72 applications + 20 → 21 closures** (3-artifact cycle: Phase 0 + Plan v1 + closure). **Discipline counts (3-artifact cycle)**: spec-first review cycle 78 → 81-for-81 at closure. `### Grep-baseline-before-drafting` 36 → 39 instances. Cross-cycle-handoff transparency precedent 42 → 45 successful. Spec-time grep-verification 46 → 49 instances.
> 
> **`### Architect-reads-production-code-before-sign-off` 17 → 18** at closure-audit firing (explicit X → Y line per `Implicit-doctrine-firings-not-narrative-tracked` 5-instance threshold reached at P0.R5 closure — architect adopts the operational rule in this closure narrative).
> 
> **`### Twin-filename-pitfall-prevention` 20 → 21 preventive events** honored at Phase 0 (no doctrine count bump per locked enumeration rule).
> 
> **Auditor-Q5-estimates-trail-grep 24 → 25 banked closures** at 0% ON-TARGET reading (if closure-actual = 10 exact). Trajectory: 11th consecutive 0% reading per `Doctrine-prediction-precision-improving-over-arc`.
> 
> **Deferred-canary strategy 23rd application** — entry pasted verbatim into `c:\Users\jagan\dog-ai\to_be_checked.md`.
> 
> **Known Limitations (P0.R6 closure)**:
> 1. **P0.R6.X-Z follow-up specs required** for full 4-task scope (Whisper + ECAPA + pyannote migrations). Foundation cycle ships AdaFace only per Q1 (a) decomposition + Q2 (a) first-target lean.
> 2. **GPU memory** per Q7 — foundation cycle adds ~100MB VRAM for persistent AdaFace worker; future P0.R6.X-Z add ~3.3GB cumulative. Document at this closure; revisit if VRAM ceiling hit on Jetson production.
> 3. **Sync boot/enrollment sites unmigrated** (3474 + 3551) per D3 OUT-OF-SCOPE; rationale: not in asyncio hot path. Future P0.R6.X follow-up could re-evaluate if profiling shows blocking concerns.
> 4. **Pickle IPC overhead** per Q3 — ~0.5-1ms per call; acceptable for AdaFace (~10-50ms inference). Future P0.R6.X may revisit for Whisper (audio buffers larger; shared memory may be load-bearing).
> 5. **Cross-platform spawn requirement** per Q6 — Windows + Jetson both supported; `if __name__ == "__main__":` guard in pipeline.py preserves correctness.
> 
> **Cumulative suite**: pending closure (+10 new pytest functions from D6 test file).
> 
> **Files touched (5 modified/new):** see Plan v1 §1.3 enumeration.

**§5.1 5-surface landing checklist:**

1. ✓ CLAUDE.md header — P0.R6 entry prepended above P0.R5 + NEW `### Pre-audit-quantifier-precision-refined-by-grep` doctrine added to Architectural Disciplines section
2. ✓ Parent complete-plan.md::P0.R6 status → `[CLOSED]` + closure note (+ P0.R6.X-Z follow-up specs filed as pending)
3. ✓ Subdir complete-plan.md::P0.R6 full closure narrative
4. ✓ to_be_checked.md 23rd deferred-canary entry
5. ✓ Architect memory files via post-closure handoff (`feedback_phase_0_zero_precision_items_at_auditor_review.md` 18 → 19; `MEMORY.md` index refresh + NEW doctrine elevation entry)

---

## §6 — Architect's diligent Pass-2 grep enumeration (auditor verification target)

| Grep pattern | Expected matches | Verification |
|---|---|---|
| `core/heavy_worker.py` file existence | 1 (NEW per D1) | A1 anchor target |
| `mp.get_context("spawn")` in `core/heavy_worker.py` | 1 match | A2 anchor target |
| Module-level `def adaface_embed_worker` in `core/heavy_worker.py` | 1 match | A3 anchor target |
| `hw.run_heavy("adaface_embed"` in `pipeline.py` | 4 matches (sites 2569 + 2663 + 6716 + 7112; line numbers may shift post-edit) | A4 anchor target — broadened per PI #1 |
| `embedder.embed(face_crop)` direct calls remaining in `pipeline.py` async functions | 0 matches in async-hot-path functions (`_background_vision_loop` + async background scan + async camera fallback); 2 matches in sync flows (3474 + 3551 — OUT-OF-SCOPE) | A4 anchor inverse check |
| `heavy_worker_status` field in `core/pipeline_state_store.py` | 1 match | A5 anchor target |
| `heavy_workers=degraded` substring in `core/health.py::format_health_line` | 1 match | A6 anchor target |
| Pool spawn line in `pipeline.py::run()` BEFORE vision task spawn | line-number AST ordering check | A7 anchor target |
| `hw.shutdown_all_pools(wait=True)` in `pipeline.py::run()` shutdown finally | 1 match | A8 anchor target |

**Auditor's independent re-grep target at Plan v1 verdict** (per `### Pass-2-grep-auditor-verified-before-Plan-v1-approval`): all 9 patterns above + cross-check that NO `embedder.embed(` direct sync call remains in async hot paths.

**Architect prediction (probabilistic per `Zero-precision-items-pre-closure-predictions-blocked` operational rule):** Plan v1 §1.3 + §6 enumeration is diligent post-PI #1 absorption; expecting clean auditor independent re-grep verification. If clean → 19th instance of `### Zero-precision-items-at-auditor-review` fires at Plan v1 surface + cycle proceeds to closure as 3-artifact OPTIONAL-Plan-v2 path TAKEN.

---

## §7 — Doctrine bump projection at closure (closure-conditional)

| Doctrine | Post-P0.R5 baseline | Post-P0.R6 closure projection |
|---|---|---|
| `### Phase-0-granular-decomposition-enables-accurate-estimates` | 18 | 19 IF closure-actual ∈ {9, 10, 11} |
| `### Zero-precision-items-at-auditor-review` | 18 (post-P0.R5 Plan v1) | 19 IF Plan v1 fires clean (0 PIs absorbed at this Plan v1 reconciliation) |
| `### Architect-reads-production-code-before-sign-off` | 17 | 18 at closure-audit (explicit X → Y line per `Implicit-doctrine-firings-not-narrative-tracked` 5-instance threshold + architect adoption) |
| `### Induction-surfaces-invariant-gaps` | 11 | 11 (stays unless in-flight detector-strengthening event) |
| OPTIONAL-Plan-v2 sub-rule proof cases | 8 (post-P0.R5) | 9 IF P0.R6 closure-actual ∈ {9, 10, 11} (Plan v1 absorbs PI cleanly; cycle proceeds as 3-artifact OPTIONAL-Plan-v2) |
| `Explicit-closure-honest-count-commitment` | 24 | 26 (25 MADE + 26 HONORED) |
| Strict-mode applications | 69 | 72 (3-artifact cycle) |
| Strict-mode closures | 20 | 21 |
| Spec-first review cycle | 78 | 81 (3 artifacts × +1) |
| `### Grep-baseline-before-drafting` | 36 | 39 |
| Cross-cycle-handoff transparency | 42 | 45 |
| Spec-time grep-verification | 46 | 49 |
| `Doctrine-prediction-precision-improving-over-arc` | 10+ cycle 0% streak | 11+ cycle 0% streak ONLY IF closure-actual = 10 exact |
| `Plan-v1-Pass-2-grep-undercount` | 7 (P0.R6 Phase 0 banked NEW PHASE-0-CATCHING-LAYER sub-shape) | stays 7 (no new instance at Plan v1 or closure) |
| `Pre-audit-quantifier-precision-refined-by-grep` | 5 (P0.R6 Phase 0 banked 5th + elevation candidacy activated) | stays 5 (no new instance at Plan v1 or closure) |
| **NEW `### Pre-audit-quantifier-precision-refined-by-grep` CLAUDE.md doctrine** | elevation candidacy active (Phase 0 verdict ratified) | **LANDS at P0.R6 closure-audit per locked precedent; doctrine library 7 → 8** |
| `### Twin-filename-pitfall-prevention` preventive events | 20 (P0.R6 Phase 0) | 21 at closure (no doctrine count bump per locked enumeration rule) |
| `Implicit-doctrine-firings-not-narrative-tracked` | 5 (P0.R5 closure-audit threshold reached) | stays 5 IF P0.R6 closure narrative explicitly includes X → Y line for `### Architect-reads-production-code-before-sign-off` (architect adopts the rule self-sustainingly); ELSE 6 |

---

## §8 — §8 row paste-template

```
| P0.R6 | Heavy-task worker foundation + AdaFace migration (P0.R6.X-Z follow-ups: Whisper + ECAPA + pyannote) | CLOSED 2026-05-24 | D1+D2+D3+D4+D5+D6 + 10 anchors + Plan v1 absorbed PI #1 D3 enumeration drift (Option α — expanded 2 → 4 async-hot-path sites; sync boot/enrollment OUT-OF-SCOPE); `Plan-v1-Pass-2-grep-undercount` 6 → 7 NEW PHASE-0-CATCHING-LAYER sub-shape; `Pre-audit-quantifier-precision-refined-by-grep` 4 → 5 + 5-INSTANCE ELEVATION THRESHOLD REACHED + NEW CLAUDE.md doctrine landed (library 7 → 8); Q1 decomposition LOCKED |
```

---

## §9 — Open questions for auditor at Plan v1: **0** (per OPTIONAL-Plan-v2 path candidacy)

All Q1-Q8 LOCKED per Phase 0 verdict 2026-05-24. PI #1 absorbed per Option α (auditor lean). Plan v1 introduces ZERO new open questions. Plan v1 RATIFIED-PENDING per auditor independent re-grep verification per `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` doctrine.

If auditor returns 0 PIs at Plan v1 review → 19th instance of `### Zero-precision-items-at-auditor-review` fires at Plan v1 surface + cycle proceeds to closure as 3-artifact OPTIONAL-Plan-v2 path TAKEN + 9th OPTIONAL-Plan-v2 proof case if closure-actual ON-TARGET.

---

## §10 — 4-phase implementation plan (developer handoff; ~3-4 hours SMALL-MEDIUM-band cycle)

**Phase 1 (~45 min) — Foundation:**
- Create NEW `core/heavy_worker.py` with `get_or_create_pool` + `run_heavy` + `shutdown_all_pools` + `_adaface_worker_init` + `adaface_embed_worker` per §2.1 + §2.2
- Use `mp.get_context("spawn")` explicitly for cross-platform
- Verify `python -c "import core.heavy_worker"` works on dev Windows

**Phase 2 (~60 min) — D3 migration (4 sites per PI #1 expansion):**
- Edit `pipeline.py:2569` — convert `loop.run_in_executor(None, embedder.embed, _crop)` → `hw.run_heavy("adaface_embed", hw.adaface_embed_worker, _crop.tobytes(), _crop.shape)`
- Edit `pipeline.py:2663` — same conversion
- Edit `pipeline.py:6716` — convert SYNC direct call `embedder.embed(face_crop)` → `await hw.run_heavy(...)` (NET-NEW async-non-blocking improvement)
- Edit `pipeline.py:7112` — same conversion as 6716
- Add `np.frombuffer(bytes, dtype=np.float32)` deserialization at each site
- Preserve P0.R1 D1 None-check fallback at all 4 sites

**Phase 3 (~45 min) — D4 + D5 wiring:**
- Add `heavy_worker_status: dict[str, str]` field + setter/peeker to PipelineStateStore
- Add `heavy_worker_status` field to HealthSnapshot + conditional emit + actionable alert
- Wire `core/heavy_worker.get_or_create_pool("adaface_embed")` warm-up at `pipeline.run()` startup BEFORE vision task spawn
- Wire `core/heavy_worker.shutdown_all_pools(wait=True)` at `pipeline.run()` shutdown finally

**Phase 4 (~60 min) — D6 test surface + deliberate-regression + closure:**
- Create `tests/test_p0_r6_heavy_worker_foundation.py` with 10 anchors per §3 (A4 BROADENED to 4 async sites)
- Run 6 deliberate-regression checks per §2.7 (note: (d) reverts site 6716 to fire A4 AST 4-site enforcement)
- Honor closure-actual count per §4 honest-count commitment table
- Apply Path C grep-verify reconciliation per `### Convention-drift-on-discipline-counts` discipline
- Land closure narrative per §5 paste-template across CLAUDE.md header + NEW `### Pre-audit-quantifier-precision-refined-by-grep` doctrine elevation under Architectural Disciplines section + parent + subdir complete-plan.md
- Update `to_be_checked.md` with 23rd deferred-canary entry
- Architect closure-audit handoff: memory file updates + CLAUDE.md doctrine elevation finalization

**Architect-handoff items for developer Phase 4 closure-narrative drafting:**
1. **NEW CLAUDE.md doctrine `### Pre-audit-quantifier-precision-refined-by-grep`** body verbatim per auditor Phase 0 verdict — lands under Architectural Disciplines section
2. **Explicit X → Y line for `### Architect-reads-production-code-before-sign-off`** per `Implicit-doctrine-firings-not-narrative-tracked` 5-instance threshold (P0.R5 closure-audit) — architect adopts the operational rule

**Expected total: ~3-4 hours** (SMALL-MEDIUM-band cycle preserved despite D3 expanded scope).

---

End of P0.R6 Plan v1.
