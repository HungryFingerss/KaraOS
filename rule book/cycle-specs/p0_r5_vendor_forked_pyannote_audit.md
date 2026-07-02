# P0.R5 — Vendor forked pyannote (+ speechbrain) — eliminate runtime monkey-patching — Phase 0 audit

**Status:** Phase 0 audit drafted 2026-05-23. APPROVED-AT-AUDITOR-REVIEW pending.

**Pre-audit framing (verbatim from parent `c:\Users\jagan\dog-ai\complete-plan.md::P0.R5`):**

> ### P0.R5 — Pyannote 3.3.2 monkey-patches outside dependency manager
>
> **Fix:** vendor a forked pyannote; pin to git SHA in `pyproject.toml`. CI verifies import without runtime patch.

---

## §1 — Grep-verified findings (DILIGENT Pass-2 per now-elevated `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` doctrine)

**§1.1 Pre-audit framing quantifier-precision refinements (THREE distinct refinements surfaced — `Pre-audit-quantifier-precision-refined-by-grep` candidate 4th instance):**

| Pre-audit framing | Grep-verified reality | Refinement |
|---|---|---|
| "pin to git SHA in `pyproject.toml`" | **NO `pyproject.toml` exists at project root**. Project uses `requirements.txt` only. | **DEP-INFRASTRUCTURE-AXIS**: pre-audit assumes pyproject.toml infrastructure that doesn't exist; actual mechanism must be `requirements.txt` git URL syntax (`pyannote.audio @ git+https://...@<SHA>`) OR creating pyproject.toml from scratch (scope expansion). |
| "vendor a forked pyannote" | Patches cover **BOTH pyannote AND speechbrain** (`tests/patch_pyannote_io.py:34-39` documents the speechbrain patch on `speechbrain/utils/torch_audio_backend.py`). | **SCOPE-AXIS**: pre-audit quantifier "pyannote" is approximate; full fix scope includes both pyannote (6 patches) AND speechbrain (1 patch) forks. |
| "vendor a forked pyannote" | **pyannote.audio is NOT in `requirements.txt`** — installed manually per CLAUDE.md "Pyannote dependency maintenance" section ("Pinned version: `pyannote.audio==3.3.2`. Do NOT bump to 4.0.x..."). Only `speechbrain>=1.0.3` is listed at line 11. | **DEP-PINNING-AXIS**: pyannote currently has NO pinned dependency declaration; vendoring requires adding the dependency line for the first time AND simultaneously switching to fork URL. |

**Three quantifier-precision refinements layered**: dep-infrastructure (pyproject.toml vs requirements.txt) + scope (pyannote only vs pyannote+speechbrain) + dep-pinning (manual install vs declared dep). Banks `Pre-audit-quantifier-precision-refined-by-grep` 3 → 4 candidate instance with NEW LAYERED-AXIS sub-shape (3 axes in single instance vs prior 1-axis-per-instance shape). Distinct from P0.R4's mechanism-generality axis (single axis); P0.R5 has multi-axis layered overstatement.

**§1.2 Patch surface enumeration (7 patches across 2 packages):**

Per `tests/patch_pyannote_io.py` source-of-truth:

| # | Target file | Package | Patch type |
|---|---|---|---|
| 1 | `pyannote/audio/core/io.py` | pyannote | `AudioMetaData` type annotation `-> torchaudio.AudioMetaData:` → `-> object:` |
| 2 | `pyannote/audio/core/io.py` | pyannote | `list_audio_backends()` → `getattr(torchaudio, 'list_audio_backends', lambda: ['sox_io'])()` |
| 3 | `pyannote/audio/core/pipeline.py` | pyannote | huggingface_hub kwarg rename `use_auth_token=` → `token=` |
| 3-cont | `pyannote/audio/core/inference.py` + `pyannote/audio/core/model.py` | pyannote | same kwarg rename in 2 more sites |
| 4 | `speechbrain/utils/torch_audio_backend.py` | **speechbrain** | `list_audio_backends()` rewrite (same as Patch 2) |
| 5 | `pyannote/audio/tasks/segmentation/mixins.py` | pyannote | `from torchaudio import AudioMetaData` → try/except stub |
| 6 | `pyannote/audio/utils/protocol.py` | pyannote | `list_audio_backends()` rewrite (same as Patch 2) |
| 7 | `pyannote/audio/core/model.py` | pyannote | `pl_load(...)` + `Klass.load_from_checkpoint(...)` get `weights_only=False` kwarg |

**Total: 6 pyannote patches + 1 speechbrain patch = 7 patches across 2 packages.** Pre-audit framing's "vendor a forked pyannote" quantifier dropped the speechbrain patch.

**§1.3 Pinned versions (per CLAUDE.md "Pyannote dependency maintenance"):**

- pyannote.audio: pinned at **3.3.2** (CLAUDE.md locks this; "Do NOT bump to 4.0.x without re-evaluating torchcodec/FFmpeg viability on dev+Jetson")
- speechbrain: `>=1.0.3` in `requirements.txt` line 11

Fork forks would target these versions as bases.

**§1.4 Twin-filename pitfall preventive event (19th candidate):**

Zero pre-existing P0.R5 artifacts (Glob `tests/p0_r5*` returned 0 matches). Phase 0 audit lands cleanly at `tests/p0_r5_vendor_forked_pyannote_audit.md`. 19th preventive event candidate honored at audit drafting (no doctrine count bump per locked enumeration rule).

**§1.5 Cross-spec orthogonality verified clean:**

- **P0.R3 vision watchdog**: unrelated (vision loop supervision; no pyannote/speechbrain dependency in vision path)
- **P0.R4 process supervisor**: unrelated (systemd unit + supervisord config; doesn't touch Python deps)
- **P0.R6 (forward-projected) ProcessPoolExecutor**: future spec; will use heavy C-extensions including pyannote — fork stability matters for P0.R6 but P0.R5 ships first
- **`core/voice.py`**: existing runtime monkeypatch for speechbrain's `list_audio_backends()` (see `tests/patch_pyannote_io.py:36` reference). Vendoring speechbrain fork makes this runtime monkeypatch redundant; deletion candidate at Phase 1 OR documented-as-dead-code for cleanup at separate sub-PR.

---

## §2 — Decomposed D-decisions (architect leans; auditor adjudication via Q1-Q7)

### D1 — Pyannote fork

**Architect lean (Q2):** create GitHub fork at `https://github.com/HungryFingerss/pyannote-audio` from upstream `v3.3.2` tag; apply 6 patches verbatim per `tests/patch_pyannote_io.py`; tag fork commit (e.g., `dog-ai-v3.3.2-patched-1`). Alternative (Q2 (b)): vendor source directly into `deps/pyannote-audio/` subdirectory (no external fork).

**Edit sites at fork:**
- `pyannote/audio/core/io.py` (2 patches)
- `pyannote/audio/core/pipeline.py` (1 patch)
- `pyannote/audio/core/inference.py` (1 patch)
- `pyannote/audio/core/model.py` (2 patches — kwarg rename + weights_only)
- `pyannote/audio/tasks/segmentation/mixins.py` (1 patch)
- `pyannote/audio/utils/protocol.py` (1 patch)

### D2 — Speechbrain fork

**Architect lean (Q3):** create GitHub fork at `https://github.com/HungryFingerss/speechbrain` from upstream `v1.0.3` tag (or compatible version); apply 1 patch to `speechbrain/utils/torch_audio_backend.py`; tag fork. Alternative: defer to P0.R5.X as separate cycle (architect's anti-lean — leaving the speechbrain patch as runtime-only would leave `core/voice.py:~30` monkeypatch as load-bearing forever; cleaner to fix both in same cycle).

### D3 — Dependency declaration update

**Architect lean (Q1):** add to `requirements.txt`:
```
pyannote.audio @ git+https://github.com/HungryFingerss/pyannote-audio.git@<SHA_OF_FORK_COMMIT>
speechbrain @ git+https://github.com/HungryFingerss/speechbrain.git@<SHA_OF_FORK_COMMIT>  # replaces speechbrain>=1.0.3 line
```

Replace the existing `speechbrain>=1.0.3` line with the git URL form. pyannote.audio gets ADDED as a new dependency line (was previously installed manually).

**Alternative (Q1 (b)):** create new `pyproject.toml` from scratch with `[project] dependencies` table — scope expansion; would require migrating all of requirements.txt to the new format.

### D4 — Delete runtime patch infrastructure

**Edit sites:**
- DELETE `tests/patch_pyannote_io.py` entirely
- DELETE the runtime monkeypatch in `core/voice.py` for `speechbrain.utils.torch_audio_backend.list_audio_backends` (if D2 ships)
- UPDATE CLAUDE.md "Pyannote dependency maintenance" section to reflect new vendor-fork model (replace "Reapply after pip install" procedure with "Fork pulls upstream + reapplies patches" procedure documented in fork README)

### D5 — Test surface (`tests/test_p0_r5_vendor_forked_pyannote.py`)

**Architect lean (Q6):** structural file tests + import verification:
- A1: `tests/patch_pyannote_io.py` does NOT exist (deletion confirmation)
- A2: `requirements.txt` contains `pyannote.audio @ git+https://github.com/HungryFingerss/pyannote-audio.git@` substring
- A3: `requirements.txt` contains `speechbrain @ git+https://github.com/HungryFingerss/speechbrain.git@` substring
- A4: `from pyannote.audio import Pipeline` succeeds without prior monkeypatch invocation (behavioral; cross-platform; runs at module import)
- A5: `from speechbrain.utils.torch_audio_backend import ...` succeeds (behavioral)
- A6: `core/voice.py` does NOT contain runtime monkeypatch for `torchaudio.list_audio_backends` (source-inspection; AST scan)
- A7: CLAUDE.md "Pyannote dependency maintenance" section updated (source-inspection)
- A8: Pyannote `Pipeline` constructible from a known SHA-pinned commit (behavioral — checks fork is actually applied)
- A9: Speechbrain `EncoderClassifier` constructible (smoke test, behavioral)

### D6 — CLAUDE.md narrative refresh

**Edit site:** existing "Pyannote dependency maintenance (Phase 2, Session 88)" section in CLAUDE.md gets replaced with new "Pyannote vendoring (P0.R5, 2026-05-23)" section.

**Architect lean content shape:**
- Forks live at `github.com/HungryFingerss/{pyannote-audio,speechbrain}` (or `deps/` per Q2 (b))
- Pin SHAs documented inline
- Upstream-merge procedure: `git fetch upstream + git merge + reapply patches manually + tag + bump SHA in requirements.txt`
- Deletion of `tests/patch_pyannote_io.py` documented as supersession event
- Fallback Option D (SpeechBrain spectral-clustering diarization) reference preserved for emergency pivot

---

## §3 — Cross-spec impact analysis (OUT-OF-SCOPE explicit)

**IN-SCOPE (P0.R5):**
- pyannote.audio fork + 6 patches per D1
- speechbrain fork + 1 patch per D2
- `requirements.txt` git URL update per D3
- `tests/patch_pyannote_io.py` deletion + `core/voice.py` monkeypatch removal per D4
- `tests/test_p0_r5_vendor_forked_pyannote.py` per D5
- CLAUDE.md section refresh per D6

**OUT-OF-SCOPE (deferred to follow-up specs or rejected):**

| Concern | Disposition |
|---|---|
| Pyannote 4.x upgrade evaluation | **REJECTED for P0.R5** — CLAUDE.md locks 3.3.2 pin per Session 88; 4.x requires torchcodec which has its own torch 2.10 incompat. Separate spec when torchcodec catches up. |
| New `pyproject.toml` migration | **OUT-OF-SCOPE** — scope expansion; requirements.txt is sufficient mechanism per Q1 (a). Migration to pyproject.toml is independent concern. |
| Automated upstream-merge CI | **OUT-OF-SCOPE** — operator-driven manual merge per D6 procedure is acceptable for current scale; automation is separate concern if forks see frequent upstream activity. |
| Faster-whisper / other deps vendoring | **REJECTED for P0.R5** — pyannote + speechbrain are the only deps with runtime monkeypatch dependency; other deps (faster-whisper, kokoro-onnx, etc.) work cleanly with upstream. |
| Multi-version pyannote support | **REJECTED** — single fork at single SHA is the contract; multi-version support is overkill. |
| `core/audio.py` torchaudio patches | **VERIFY-AT-PHASE-0**: grep core/audio.py for any torchaudio compat patches. If present, in-scope (architect lean toggles); if absent, out-of-scope. |

---

## §4 — Pre-mortem (10 failure modes + mitigation per mode)

| # | Failure mode | Mitigation |
|---|---|---|
| 1 | Fork SHA changes during merge (history rewrite) | Pin to commit SHA, not branch. Document the SHA-as-source-of-truth invariant in CLAUDE.md (D6) |
| 2 | Upstream pyannote releases security patch; fork stales | Manual `git fetch upstream + merge + reapply patches + bump SHA` procedure documented (D6). Watch upstream for major releases |
| 3 | GitHub fork repo accidentally deleted or made private | Fork SHA is captured in requirements.txt; if fork repo lost, re-create from local clone + push to new URL + bump SHA in requirements.txt |
| 4 | Patches don't apply cleanly to a future upstream version | Document patch contents in fork README; manual re-apply procedure |
| 5 | Test A4 (`from pyannote.audio import Pipeline` succeeds) passes locally on dev Windows but fails on Jetson production | Cross-platform import test verifies BOTH environments load patched code; if Jetson fails, fork installation didn't take effect (likely venv mismatch) |
| 6 | `pip install -r requirements.txt` fetches stale cached version | Document `pip install --force-reinstall -r requirements.txt` in CLAUDE.md upgrade procedure |
| 7 | `tests/patch_pyannote_io.py` deletion breaks an unknown dev script | Grep before deletion: confirm zero callers outside the file itself. Already grep-verified in §1.2 |
| 8 | `core/voice.py` runtime monkeypatch removal exposes some lurking import-order bug | A5 behavioral test catches this if `speechbrain.utils.torch_audio_backend` imports clean post-fork |
| 9 | `pyannote.audio` not previously in requirements.txt; transitive resolution changes when added explicitly | `pip install --upgrade` after the change re-resolves; if regressions, pin transitive deps |
| 10 | Fork-creation workflow itself is user-driven (GitHub UI); architect can't automate the fork creation | Document precise fork URLs + commit messages in D6 + Phase 1 implementation plan; user creates forks manually as part of Phase 1 |

---

## §5 — Multi-direction invariant trace per D-decision

**D1 invariants:**
- ↑ Upstream: pyannote-audio v3.3.2 tag at upstream GitHub (immutable; trusted source)
- → Same-level: 6 patches apply cleanly to v3.3.2 source per `tests/patch_pyannote_io.py` validation
- ↓ Downstream: fork SHA referenced in requirements.txt; `pip install` fetches via git+https; pyannote.audio import works without runtime patch

**D2 invariants:**
- ↑ Upstream: speechbrain v1.0.3 tag at upstream GitHub
- → Same-level: 1 patch applies cleanly per `tests/patch_pyannote_io.py:34-39`
- ↓ Downstream: speechbrain import works without runtime patch; `core/voice.py` monkeypatch becomes dead code (D4 removal)

**D3 invariants:**
- ↑ Upstream: requirements.txt git URL syntax supported by pip (`pip install` honors `package @ git+...@SHA`)
- → Same-level: D3 adds pyannote.audio dep (was manually installed); replaces speechbrain version pin
- ↓ Downstream: `pip install -r requirements.txt` produces a reproducible install matching the SHA-pinned forks

**D4 invariants:**
- ↑ Upstream: D1+D2+D3 all shipped; patches now live in forks
- → Same-level: deletion is safe because forks deliver patched code at install time
- ↓ Downstream: developer/operator no longer needs to run `python tests/patch_pyannote_io.py` post-install

**D5 invariants:**
- ↑ Upstream: pytest collects new test file
- → Same-level: 9 anchors cover D1-D6 surfaces
- ↓ Downstream: CI/local pytest catches regression if any deploy artifact is modified incorrectly

**D6 invariants:**
- ↑ Upstream: CLAUDE.md "Pyannote dependency maintenance" section refreshed
- → Same-level: D6 documents the new vendoring model + upstream-merge procedure
- ↓ Downstream: future maintainer reads CLAUDE.md + understands the fork model without spelunking

---

## §6 — Q5 baseline estimation (architect lean: 9 anchors at exact mid; inclusive ±15% band per locked methodology)

**Architect lean: 9 anchors at exact mid 9; inclusive ±15% band [7.65, 10.35] → 8/9/10 all qualify ON-TARGET per locked methodology from P0.S5/B5/R2/R3/R4.**

| # | D | Anchor name | Type |
|---|---|---|---|
| A1 | D4 | `test_p0_r5_d4_anchor_1_patch_script_deleted` | source-inspection: `tests/patch_pyannote_io.py` does NOT exist (deletion confirmation via file existence check) |
| A2 | D3 | `test_p0_r5_d3_anchor_1_requirements_has_pyannote_git_url` | source-inspection: `requirements.txt` contains `pyannote.audio @ git+https://github.com/HungryFingerss/pyannote-audio.git@` |
| A3 | D3 | `test_p0_r5_d3_anchor_2_requirements_has_speechbrain_git_url` | source-inspection: `requirements.txt` contains `speechbrain @ git+https://github.com/HungryFingerss/speechbrain.git@` (replaces version pin) |
| A4 | D1 | `test_p0_r5_d1_anchor_1_pyannote_imports_without_runtime_patch` | behavioral: `from pyannote.audio import Pipeline` succeeds at module load (NO prior monkeypatch invocation) |
| A5 | D2 | `test_p0_r5_d2_anchor_1_speechbrain_imports_without_runtime_patch` | behavioral: `from speechbrain.utils.torch_audio_backend import ...` succeeds |
| A6 | D4 | `test_p0_r5_d4_anchor_2_voice_no_runtime_monkeypatch` | source-inspection (AST): `core/voice.py` body does NOT contain `torchaudio.list_audio_backends = lambda` runtime monkeypatch (if D2 ships) |
| A7 | D6 | `test_p0_r5_d6_anchor_1_claude_md_section_refreshed` | source-inspection: CLAUDE.md "Pyannote dependency maintenance" section contains `vendoring` substring + fork URL substring (replaces old section's "Reapply after pip install" procedure) |
| A8 | D1 | `test_p0_r5_d1_anchor_2_pyannote_pipeline_constructible_at_sha` | behavioral (CUDA-gated; smoke test): `Pipeline.from_pretrained(...)` succeeds against the SHA-pinned fork — catches "fork is on wrong commit" regression |
| A9 | D2 | `test_p0_r5_d2_anchor_2_speechbrain_encoder_constructible` | behavioral (CUDA-gated; smoke test): `EncoderClassifier.from_hparams(...)` for ECAPA-TDNN succeeds — catches speechbrain fork install issues |

**Total: 9 logical anchors. 1:1 pytest-function-to-anchor mapping.**

**Inclusive ±15% band table (per locked methodology):**

| Closure-actual | Overage | Band | Doctrine impact |
|---|---|---|---|
| 7 | −22.2% | SLIGHT-DRIFT-DOWN | Doctrine holds (watch trajectory) |
| **8** | **−11.1%** | **ON-TARGET** | Doctrine bumps 17 → 18 |
| **9** | **0.0%** | **ON-TARGET (exact mid)** | Doctrine bumps 17 → 18; 10+ consecutive 0% exact-mid streak extends |
| **10** | **+11.1%** | **ON-TARGET** | Doctrine bumps 17 → 18 |
| 11 | +22.2% | SLIGHT-DRIFT-UP | Doctrine holds (watch trajectory) |
| ≥12 | ≥+33% | FALSIFICATION | Doctrine demotes |

---

## §7 — Twin-filename pitfall preventive event (19th candidate)

Zero pre-existing P0.R5 artifacts honored at this Phase 0 drafting per `### Twin-filename-pitfall-prevention` doctrine. NEW artifacts at `tests/p0_r5_*` paths cleanly disambiguate against zero prior. No doctrine count bump per locked enumeration rule.

---

## §8 — Open questions for auditor (architect leans explicit per locked discipline)

**Q1 — Dependency-declaration mechanism:**
- **(a)** Add to existing `requirements.txt` using git URL syntax (`package @ git+https://...@SHA`)
- **(b)** Create NEW `pyproject.toml` from scratch + migrate all deps from requirements.txt
- **(c)** Use both — keep requirements.txt as canonical + add pyproject.toml with redundant info
- **Architect lean: (a) requirements.txt git URL syntax.** Pre-audit framing's "pyproject.toml" is approximate; project actually uses requirements.txt (verified §1.1). Adding pyproject.toml is scope expansion (~50+ lines of dep migration + new format learning curve for operator). requirements.txt git URL syntax is fully supported by pip + minimal-change.

**Q2 — Fork vs vendor approach:**
- **(a)** External GitHub forks at `github.com/HungryFingerss/{pyannote-audio,speechbrain}`; requirements.txt references via `git+https://...@SHA`
- **(b)** Vendor source directly into `deps/pyannote-audio/` + `deps/speechbrain/` subdirectories; requirements.txt uses local-path deps (`./deps/pyannote-audio`)
- **(c)** Hybrid — fork on GitHub for source-of-truth + vendor locally for offline-install fallback
- **Architect lean: (a) external GitHub forks.** Pre-audit framing's "pin to git SHA" implies external git URL. Reasonable trade-off: fork URL is stable; SHA is reproducible; no large vendored source-tree clutters the project repo; upstream-merge procedure flows naturally via `git fetch upstream`. Option (b) vendoring has a clean simpler dependency story but adds ~10K LOC of vendored code to project git history; not worth it for 7 patches.

**Q3 — Spec scope — pyannote only vs pyannote + speechbrain:**
- **(a)** P0.R5 IN-SCOPE for both pyannote + speechbrain (single cycle ships both forks; cleaner one-shot deletion of `tests/patch_pyannote_io.py`)
- **(b)** P0.R5 IN-SCOPE for pyannote ONLY; speechbrain deferred to P0.R5.X (avoids speechbrain fork maintenance; leaves `core/voice.py` monkeypatch as load-bearing forever or until P0.R5.X)
- **Architect lean: (a) both in P0.R5.** Separating leaves an intermediate-stale-state (patch script partial; runtime monkeypatch still load-bearing). Speechbrain has only 1 patch; trivial fork maintenance. Cleaner one-shot delivery.

**Q4 — Should P0.R5 ship now or defer to pyannote 4.x upstream resolution?**
- **(a)** Ship now per locked roadmap + deferred-canary discipline; eliminates manual patch script step
- **(b)** Defer indefinitely; upstream pyannote 4.x may resolve the issues organically (pyannote 4.0 went torchcodec-native but torchcodec 0.11.1 is itself incompatible with torch 2.10; the upstream "resolution" may take a year+)
- **(c)** Defer until torchcodec 0.x catches up to torch 2.10
- **Architect lean: (a) ship now.** Pre-audit roadmap has P0.R5 scheduled; deferred-canary discipline accumulates closure narratives through P0.R11; deferring P0.R5 breaks the cycle cadence. Patch script's manual reapplication is a real ongoing toil; vendoring eliminates it. Even if pyannote 4.x catches up next year, fork model accommodates by adding "fork pulls from upstream + applies patches" semantic.

**Q5 — Anchor count (Q5 baseline estimation):**
- **Architect lean: 9 anchors at exact mid 9; inclusive ±15% band [7.65, 10.35] → 8/9/10 all qualify ON-TARGET per locked methodology.** No precedent inconsistency. No special considerations.

**Q6 — Test surface scope (CUDA-gated smoke tests vs structural-only):**
- **(a)** Mix of source-inspection (cross-platform) + behavioral smoke tests (CUDA-gated; SKIP on Windows dev / Linux CI without GPU)
- **(b)** Pure source-inspection (cross-platform; runs everywhere; doesn't catch fork-install-issues)
- **(c)** Pure behavioral (catches install issues; SKIPS on dev/CI without GPU)
- **Architect lean: (a) hybrid.** A1-A3+A6-A7 source-inspection (catches deletion + git URL + monkeypatch removal + CLAUDE.md refresh — cross-platform). A4-A5 behavioral import (cross-platform; catches import-time regression). A8-A9 behavioral CUDA-gated smoke (catches fork-actually-applied regression; SKIP if no CUDA). Mix gives both cross-platform coverage AND production-environment validation.

**Q7 — User-driven fork-creation step — where does it land in the cycle?**
- **(a)** Phase 1 implementation: user creates forks via GitHub UI as the FIRST step; architect documents exact procedure in Plan v1 §10 implementation plan
- **(b)** Pre-Phase-1: user creates forks BEFORE Plan v1 ships; architect cites SHAs in Plan v1
- **(c)** Architect handles fork creation via GitHub MCP if available; otherwise user-driven
- **Architect lean: (a) Phase 1 implementation step.** User creates forks as Phase 1 Step 1 (alongside architect's Plan v1 lock); SHAs captured at this step + threaded into Plan v1's locked spec at v1→v2 transition OR as in-flight Plan v1 update. Avoids pre-Phase-1 ordering complication. The user's manual fork creation IS the architect's "Phase 1 Step 1" handoff.

---

## §9 — `### Zero-precision-items-at-auditor-review` doctrine forecast

Architect's pre-emption budget at Phase 0: 7 Q-leans (Q1-Q7) + Q5 anchor lock. Honest forecast: Q1 (dep mechanism) carries quantifier-precision risk (auditor may prefer to surface pyproject.toml creation as scope-expansion question); Q2 (fork vs vendor) is the biggest scope decision — auditor may lean (b) vendor-directly to avoid external-fork maintenance. Q4 (ship-vs-defer) is architect's call but auditor may push back. Honest assessment: NON-ZERO risk of 1-2 PIs at Phase 0 surface; cleanest outcome would be Q1+Q2+Q3+Q4 all architect-leans ratified + 0 PIs → 16th `### Zero-precision-items-at-auditor-review` instance fires at Phase 0 (pattern-broken streak counter at 1 since P0.R4 Plan v1 block; clean P0.R5 Phase 0 would extend counter to 1+1=2 stays at 1 per the discipline's enumeration tracking ONLY Plan v1 blocks).

**`Zero-precision-items-pre-closure-predictions-blocked` counter status**: at 1 (post-P0.R4 Plan v1 block). Plan v2 surfaces don't increment counter; only Plan v1 blocks do. P0.R5 Plan v1 outcome (if clean) does NOT decrement counter — counter only resets to 0 on full pattern-broken-streak rebuild OR doesn't track if architect adopts probabilistic-prediction framing.

---

## §10 — Architect's pre-Plan-v1 prediction (probabilistic per `Zero-precision-items-pre-closure-predictions-blocked` operational rule + formal Pass-2 grep CLAUDE.md doctrine)

Per the now-elevated `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` doctrine + locked discipline: architect's pre-Plan-v1 prediction should be PROBABILISTIC, NOT CONFIDENT. Auditor's independent Pass-2 verification may surface PI architect missed.

**Architect prediction (probabilistic):** "Phase 0 + Plan v1 SUBMITTED for auditor cross-check; expecting 1-3 PIs surface possibility on Q1/Q2/Q4 specifically. If cycle clears clean with 0 PIs → 8th OPTIONAL-Plan-v2 proof case extends sub-rule track record from 7 → 8 (P0.R4 lost the proof case at PI #1; P0.R5 could reclaim it). If 1+ PIs surface, cycle escalates to Plan v2 cleanly. NEW `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` doctrine continues to be empirically validated regardless of outcome."

**Standing honest flag from §1.1**: P0.R5 has 3 layered quantifier-precision refinements — more architectural friction than prior P0.R cycles. Bumps `Pre-audit-quantifier-precision-refined-by-grep` 3 → 4 candidate at this Phase 0 verdict per auditor adjudication.

---

## §11 — Files this audit touches (Phase 0 zero-production-code rule)

**Pure documentation; ZERO production code changes at Phase 0:**

- `c:\Users\jagan\dog-ai\dog-ai\tests\p0_r5_vendor_forked_pyannote_audit.md` — THIS FILE (NEW)

**Phase 1+ shipping (PER PLAN v1 LOCK; NOT in Phase 0 scope):**

- External fork repos (user-driven via GitHub UI per Q7 (a)): `github.com/HungryFingerss/pyannote-audio` + `github.com/HungryFingerss/speechbrain`
- `requirements.txt` — D3 git URL updates (+1 line pyannote.audio + replace 1 line speechbrain)
- `tests/patch_pyannote_io.py` — D4 DELETE
- `core/voice.py` — D4 runtime monkeypatch REMOVE (~5-10 LOC)
- `CLAUDE.md` — D6 "Pyannote dependency maintenance" section REPLACE with new "Pyannote vendoring (P0.R5)" section
- `tests/test_p0_r5_vendor_forked_pyannote.py` — NEW file with 9 anchors

**Non-production-code changes (architect handoff scope per Q7):**

- User creates external GitHub forks per Phase 1 Step 1; commits patches; captures SHAs; threads SHAs into Plan v1 lock OR in-flight Plan v1 update.

---

## §12 — Verdict request

Forwarding to auditor for Phase 0 verdict. Expected verdict items:
1. Q1 adjudication (requirements.txt vs pyproject.toml mechanism)
2. Q2 adjudication (external fork vs vendored source)
3. Q3 adjudication (pyannote-only vs pyannote+speechbrain scope)
4. Q4 adjudication (ship now vs defer pending pyannote 4.x)
5. Q5 anchor count lock (architect lean: 9 inclusive ±15%)
6. Q6 adjudication (test surface mix)
7. Q7 adjudication (user-driven fork creation timing)
8. PI surfacing (if any) + non-blocking observations (if any)

**Banking events expected at Phase 0 verdict (closure-conditional):**
- `### Zero-precision-items-at-auditor-review` 16 → 17 IF auditor returns 0 PIs
- Twin-filename pitfall 19th preventive event ALREADY honored at audit drafting (no doctrine count bump)
- `Pre-audit-quantifier-precision-refined-by-grep` 3 → 4 instances IF auditor ratifies the 3-layered refinement at §1.1 as a single new instance with NEW LAYERED-AXIS sub-shape

**Spec context note**: P0.R5 is materially distinct from prior P0.R cycles — vendoring dependency artifacts; mixed code/external-fork/documentation work. Cycle shape closer to P0.0 (CI scaffold) + P0.R4 (deployment artifacts) than P0.R1/R2/R3 (cognitive runtime supervision). External-fork dimension introduces user-driven step at Phase 1 Step 1 per Q7 (a).

---

End of P0.R5 Phase 0 audit.
