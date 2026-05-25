# P0.R5 — Vendor forked pyannote (+ speechbrain) — eliminate runtime monkey-patching — Plan v1

**Status:** Plan v1 drafted 2026-05-23 with Q1-Q7 locked per P0.R5 Phase 0 verdict + 2 non-blocking observations absorbed. APPROVED-AT-AUDITOR-REVIEW pending.

**Parent audit:** `tests/p0_r5_vendor_forked_pyannote_audit.md` (Phase 0 ACCEPTED with 0 BLOCKING PIs + 2 non-blocking observations on Q2 + Q7).

---

## §1 — Phase 0 reconciliation

**§1.1 Q1-Q7 lock summary per auditor verdict 2026-05-23:**

| Q | Decision | Lock |
|---|---|---|
| Q1 | Dependency declaration mechanism | **(a) requirements.txt git URL syntax** — pre-audit's pyproject.toml was DEP-INFRASTRUCTURE-AXIS quantifier-precision approximation. |
| Q2 | Fork vs vendor approach | **(a) external GitHub forks** at `github.com/HungryFingerss/pyannote-audio` + `github.com/HungryFingerss/speechbrain`. Non-blocking observation #1: github-availability assumption documented in D6 CLAUDE.md narrative + pre-mortem §4 #3 mitigation. |
| Q3 | Spec scope | **(a) BOTH pyannote + speechbrain** in P0.R5 (cleaner one-shot deletion of `tests/patch_pyannote_io.py` + monkeypatches). |
| Q4 | Ship now vs defer | **(a) ship now** per locked roadmap; eliminates real ongoing toil. |
| Q5 | Anchor count | **9 anchors at exact mid 9; inclusive ±15% band [7.65, 10.35]** — 8/9/10 all qualify ON-TARGET per locked methodology. |
| Q6 | Test surface scope | **(a) hybrid** source-inspection + CUDA-gated behavioral. |
| Q7 | Fork creation timing | **(a) Phase 1 Step 1 user-driven via GitHub UI**. Non-blocking observation #2: option (α) — Plan v1 uses placeholder `@<SHA>` syntax + Phase 1 fills in concrete SHAs (vs (β) Plan v1 mid-flight update; (α) is structurally cleaner per `### Spec-contracts-not-implementations`). |

**§1.2 Diligent Pass-2 grep enumeration (per now-elevated `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` CLAUDE.md doctrine + formal rule extension):**

Files affected by P0.R5 implementation (6 D-decisions):

| Path | Edit type | D-decision | Notes |
|---|---|---|---|
| `requirements.txt` | +1 line (pyannote.audio git URL) + replace 1 line (speechbrain version pin → git URL) | D3 | Both use `@<SHA>` placeholder per Q7 option (α); concrete SHAs filled at Phase 1 Step 1 |
| External fork: `github.com/HungryFingerss/pyannote-audio` | NEW fork from pyannote v3.3.2 + 6 patches applied (Phase 1 Step 1, user-driven) | D1 | 6 patches per `tests/patch_pyannote_io.py:108-180` |
| External fork: `github.com/HungryFingerss/speechbrain` | NEW fork from speechbrain v1.0.3 + 1 patch applied (Phase 1 Step 1, user-driven) | D2 | 1 patch per `tests/patch_pyannote_io.py:34-39` lineage |
| `tests/patch_pyannote_io.py` | DELETE entirely | D4 | Architect-handoff: pre-deletion grep-verify zero callers outside the file itself |
| `core/voice.py` (lines 51 + 95) | DELETE 2 monkeypatch sites (per non-blocking observation #1) | D4 | BOTH sites: `_ta.list_audio_backends = lambda: ["sox_io"]` — 1st at module-load patch (line 51); 2nd at `load_speaker_embedder()` guard (line 95) |
| `CLAUDE.md` | REPLACE "Pyannote dependency maintenance" section with NEW "Pyannote vendoring (P0.R5)" section | D6 | Documents fork URLs + SHA-pin model + upstream-merge procedure + github-availability assumption (per non-blocking observation #1) |
| `tests/test_p0_r5_vendor_forked_pyannote.py` | NEW file (9 anchors) | D5 | A1-A9 per §3 |

**Auditor's independent re-grep target:** all 7 files/surfaces above + cross-check 2 monkeypatch sites in core/voice.py (lines 51 + 95).

**§1.3 Cross-spec orthogonality verified clean (no change from Phase 0 §1.5):**

- P0.R3 + P0.R4: unrelated
- `core/voice.py` runtime monkeypatch: dependency captured at §1.2 (BOTH sites enumerated per non-blocking observation #1)
- P0.R6 (forward-projected ProcessPoolExecutor): future spec will benefit from fork stability

**§1.4 Twin-filename pitfall 19th preventive event already honored at Phase 0 audit drafting** (no doctrine count bump per locked enumeration rule).

---

## §2 — D-decision contracts (LOCKED per Q1-Q7 verdicts + 2 non-blocking observations absorbed)

### §2.1 D1 — Pyannote fork

**Edit site:** NEW external GitHub fork at `https://github.com/HungryFingerss/pyannote-audio` from upstream `v3.3.2` tag.

**Patches applied (6 from `tests/patch_pyannote_io.py`):**
- Patch 1+2 at `pyannote/audio/core/io.py` (AudioMetaData annotation + list_audio_backends rewrite)
- Patch 3 at `pyannote/audio/core/pipeline.py` (huggingface_hub kwarg rename)
- Patch 3-cont at `pyannote/audio/core/inference.py` + `pyannote/audio/core/model.py` (same kwarg rename)
- Patch 5 at `pyannote/audio/tasks/segmentation/mixins.py` (AudioMetaData import shim)
- Patch 6 at `pyannote/audio/utils/protocol.py` (list_audio_backends rewrite)
- Patch 7 at `pyannote/audio/core/model.py` (weights_only=False)

**Phase 1 Step 1 (user-driven)**: user creates fork via GitHub UI, applies 6 patches verbatim via diff or manual edit, commits as single `dog-ai v3.3.2 patches` commit, captures SHA, threads SHA into Plan v1 §2.3 placeholder.

### §2.2 D2 — Speechbrain fork

**Edit site:** NEW external GitHub fork at `https://github.com/HungryFingerss/speechbrain` from upstream `v1.0.3` tag (or compatible version).

**Patch applied (1 from `tests/patch_pyannote_io.py:34-39`):**
- `speechbrain/utils/torch_audio_backend.py`: `list_audio_backends()` → `getattr(torchaudio, 'list_audio_backends', lambda: ['sox_io'])()` rewrite

**Phase 1 Step 1 (user-driven)**: same procedure as D1 — fork + patch + single commit + capture SHA + thread.

### §2.3 D3 — Dependency declaration update (`requirements.txt`)

**Edit site:** `requirements.txt`

**Current state (relevant lines):**
- Line 11: `speechbrain>=1.0.3        # ECAPA-TDNN speaker verification (spkrec-ecapa-voxceleb)`
- pyannote.audio is NOT in requirements.txt (currently installed manually per CLAUDE.md)

**Plan v1 LOCKED spec (placeholder SHAs per Q7 option (α)):**

```
# Voice recognition (P0.R5 — vendored forks)
speechbrain @ git+https://github.com/HungryFingerss/speechbrain.git@<SHA_SPEECHBRAIN_FORK>  # ECAPA-TDNN + 1 P0.R5 patch (torch_audio_backend list_audio_backends rewrite)
pyannote.audio @ git+https://github.com/HungryFingerss/pyannote-audio.git@<SHA_PYANNOTE_FORK>  # 3.3.2 + 6 P0.R5 patches (torchaudio 2.9+ compat + huggingface_hub kwarg + weights_only)
```

**Contract:**
- `<SHA_SPEECHBRAIN_FORK>` placeholder filled at Phase 1 Step 1 (concrete SHA captured by user after fork creation)
- `<SHA_PYANNOTE_FORK>` placeholder filled at Phase 1 Step 1 (same)
- Both git URLs use pip's `package @ git+https://...@SHA` syntax (fully supported by `pip install -r requirements.txt`)
- Old `speechbrain>=1.0.3` line REPLACED with new git URL form
- pyannote.audio line ADDED (was not previously in file)

**Anchor coverage:** A2 + A3 source-inspection on `git+https://github.com/HungryFingerss/` substring (auditor verifies SHA placeholder OR concrete SHA — both match).

### §2.4 D4 — Delete runtime patch infrastructure (per non-blocking observation #1 — BOTH `core/voice.py` sites enumerated)

**Edit sites (3 surfaces; LOCKED with explicit enumeration per non-blocking observation #1):**

1. **DELETE `tests/patch_pyannote_io.py` entirely** — pre-deletion grep-verify confirms zero callers outside the file itself.
2. **DELETE `core/voice.py:51` monkeypatch site** — first occurrence of `_ta.list_audio_backends = lambda: ["sox_io"]` (module-load pattern).
3. **DELETE `core/voice.py:95` monkeypatch site** — second occurrence of `_ta.list_audio_backends = lambda: ["sox_io"]` (inside `load_speaker_embedder()` guard).

**Contract:**
- All 3 sites are deletion (no replacement code; fork-vendored code handles the patches at install time)
- `core/voice.py` lines 51 + 95 deletions must NOT break the surrounding module structure (verify with `python -c "import core.voice"` after edit)
- `tests/patch_pyannote_io.py` deletion includes its docstring reference removal from CLAUDE.md (handled at D6)

**Anchor coverage:** A1 (patch script deletion) + A6 (core/voice.py monkeypatch absence — AST scan covering BOTH sites).

### §2.5 D5 — Test surface (`tests/test_p0_r5_vendor_forked_pyannote.py`)

**Edit site:** NEW file at `tests/test_p0_r5_vendor_forked_pyannote.py`.

**LOCKED contract:** 9 logical anchors per §3 decomposition. Hybrid source-inspection + CUDA-gated behavioral per Q6 (a). 1:1 pytest-function-to-anchor mapping.

### §2.6 D6 — CLAUDE.md narrative refresh (per non-blocking observation #1 — github-availability assumption)

**Edit site:** `CLAUDE.md` "Pyannote dependency maintenance (Phase 2, Session 88)" section (currently ~25-30 lines).

**LOCKED replacement content (architect's pre-draft; subject to Phase 4 closure-narrative reconciliation):**

```markdown
## Pyannote vendoring (P0.R5, 2026-05-23)

Pyannote 3.3.2 + speechbrain 1.0.3 ship as forked git repos under
the `HungryFingerss` GitHub organization. The 7 patches that previously
required runtime application via `tests/patch_pyannote_io.py` (deleted
at P0.R5 closure) now live directly in the fork commits.

**Forks:**
- `github.com/HungryFingerss/pyannote-audio` @ `<SHA_PYANNOTE_FORK>`
  (3.3.2 base + 6 patches: torchaudio 2.9+ compat + huggingface_hub kwarg + weights_only)
- `github.com/HungryFingerss/speechbrain` @ `<SHA_SPEECHBRAIN_FORK>`
  (1.0.3 base + 1 patch: torch_audio_backend list_audio_backends rewrite)

**Dependency declarations** (in `requirements.txt`):

    pyannote.audio @ git+https://github.com/HungryFingerss/pyannote-audio.git@<SHA_PYANNOTE_FORK>
    speechbrain @ git+https://github.com/HungryFingerss/speechbrain.git@<SHA_SPEECHBRAIN_FORK>

**Upstream-merge procedure** (when pyannote or speechbrain releases new version):
1. `git fetch upstream` in fork repo
2. `git merge upstream/main` (or target tag)
3. Manually re-apply the dog-ai patches (rebase onto upstream changes)
4. Commit + tag the new patched commit
5. Bump SHA in `requirements.txt`
6. Run `pip install --force-reinstall -r requirements.txt`
7. Verify `from pyannote.audio import Pipeline` works without runtime patch

**GitHub-availability assumption + operator mitigation:**

External forks create a deployment dependency on github.com availability +
fork-repo persistence. If GitHub goes down or a fork is accidentally deleted
or made private, `pip install -r requirements.txt` will fail with a git
clone error.

Mitigation: operator should maintain a local clone of each fork on the
production host. If a fork repo is lost, re-create from local clone +
push to new URL + bump SHA in `requirements.txt`. For multi-host
deployments, consider mirroring forks to a self-hosted git server or
vendoring source directly (future P0.R5.X follow-up if pattern recurs).

**Fallback (if forks stale + patches don't apply to a new upstream):**

SpeechBrain's built-in spectral-clustering diarization recipe is the
Option D fallback per Session 88. SpeechBrain is already in our venv
for ECAPA-TDNN; the recipe trades off ~2-3 percentage points of DER
worse than pyannote but eliminates the upstream-compat brittleness.
```

**Anchor coverage:** A7 source-inspection on CLAUDE.md section structure.

---

## §3 — Anchor decomposition LOCK (9 anchors at exact mid 9 inclusive ±15%)

| # | D | Anchor name | Type | Coverage |
|---|---|---|---|---|
| A1 | D4 | `test_p0_r5_d4_anchor_1_patch_script_deleted` | source-inspection | `tests/patch_pyannote_io.py` does NOT exist (Path-based file existence check) |
| A2 | D3 | `test_p0_r5_d3_anchor_1_requirements_has_pyannote_git_url` | source-inspection | `requirements.txt` contains `pyannote.audio @ git+https://github.com/HungryFingerss/pyannote-audio.git@` substring |
| A3 | D3 | `test_p0_r5_d3_anchor_2_requirements_has_speechbrain_git_url` | source-inspection | `requirements.txt` contains `speechbrain @ git+https://github.com/HungryFingerss/speechbrain.git@` substring (NOT the old `speechbrain>=1.0.3` line) |
| A4 | D1 | `test_p0_r5_d1_anchor_1_pyannote_imports_without_runtime_patch` | behavioral (import-level) | `from pyannote.audio import Pipeline` succeeds at module load WITHOUT prior monkeypatch invocation; cross-platform |
| A5 | D2 | `test_p0_r5_d2_anchor_1_speechbrain_imports_without_runtime_patch` | behavioral (import-level) | `from speechbrain.utils.torch_audio_backend import ...` succeeds; cross-platform |
| A6 | D4 | `test_p0_r5_d4_anchor_2_voice_no_runtime_monkeypatch` | source-inspection (AST scan) | `core/voice.py` body does NOT contain `_ta.list_audio_backends = lambda` assignment at ANY site (covers BOTH old line 51 + line 95 per non-blocking observation #1) |
| A7 | D6 | `test_p0_r5_d6_anchor_1_claude_md_section_refreshed` | source-inspection | CLAUDE.md contains `## Pyannote vendoring (P0.R5` substring + `git+https://github.com/HungryFingerss/pyannote-audio.git` substring + `github-availability assumption` substring (per non-blocking observation #1 documentation requirement) |
| A8 | D1 | `test_p0_r5_d1_anchor_2_pyannote_pipeline_constructible_at_sha` | behavioral (CUDA-gated; smoke test) | `Pipeline.from_pretrained(...)` succeeds against the SHA-pinned fork; SKIP if no CUDA OR HF_TOKEN missing |
| A9 | D2 | `test_p0_r5_d2_anchor_2_speechbrain_encoder_constructible` | behavioral (CUDA-gated; smoke test) | `EncoderClassifier.from_hparams(...)` for ECAPA-TDNN succeeds; SKIP if no CUDA |

**Total: 9 logical anchors. 1:1 pytest-function-to-anchor mapping. Mid 9 exact match to Phase 0 §6 lock.**

---

## §4 — Honest-count commitment table (inclusive ±15% per locked methodology)

| Closure-actual | Overage | Band | Doctrine impact + commitment |
|---|---|---|---|
| 7 | −22.2% | ±15-30% SLIGHT-DRIFT-DOWN | Doctrine holds (watch trajectory); architect commits to honoring |
| **8** | **−11.1%** | **±15% ON-TARGET** | **Doctrine bumps 17 → 18**; architect commits |
| **9** | **0.0%** | **±15% ON-TARGET (exact mid)** | **Doctrine bumps 17 → 18; 10+ consecutive 0% exact-mid streak extends per `Doctrine-prediction-precision-improving-over-arc`**; architect commits |
| **10** | **+11.1%** | **±15% ON-TARGET** | **Doctrine bumps 17 → 18**; architect commits |
| 11 | +22.2% | ±15-30% SLIGHT-DRIFT-UP | Doctrine holds (watch trajectory); architect commits to honoring |
| ≥12 | ≥+33% | FALSIFICATION | Doctrine demotes; architect commits to honoring this outcome at closure-audit |

**`Explicit-closure-honest-count-commitment` 22 → 24** (23rd MADE at Plan v1 §4 + 24th HONORED at closure per STRICT separation).

---

## §5 — Closure-narrative paste-template

(Architect's pre-draft; subject to closure-actual reconciliation + Path C grep-verify of doctrine counts.)

**P0.R5 closure note:**

> ## P0.R5 — Vendor forked pyannote (+ speechbrain) — eliminate runtime monkey-patching — D1+D2+D3+D4+D5+D6 + 9 anchors at exact mid 9 inclusive ±15% + 6 deliberate-regression checks + closure-conditional 8th OPTIONAL-Plan-v2 proof case  [CLOSED 2026-05-23]
> 
> **Sub-PR sequence:** Phase 0 audit (`tests/p0_r5_vendor_forked_pyannote_audit.md`, APPROVED with 0 BLOCKING PIs + 2 non-blocking observations absorbed at Plan v1 — **17th instance of `### Zero-precision-items-at-auditor-review` at Phase 0 surface**; `Pre-audit-quantifier-precision-refined-by-grep` 3 → 4 NEW LAYERED-AXIS sub-shape; 3 layered quantifier-precision refinements: DEP-INFRASTRUCTURE + SCOPE + DEP-PINNING) → Plan v1 (`tests/p0_r5_vendor_forked_pyannote_plan_v1.md`, RATIFIED with 0 PIs at Plan v1 surface — **18th instance of doctrine** firing at Plan v1 review; **8th OPTIONAL-Plan-v2 path proof case** under absorbed sub-rule track record P0.S3 + P0.B3 + P0.B5 + P0.B6 + P0.S8 + P0.R2 + P0.R3 + P0.R5) → Phase 1-5 implementation.
> 
> **OPTIONAL-Plan-v2 path SUCCESS** — reclaims the 8th proof case lost at P0.R4 Plan v1 (PI #1 D4 enumeration undercount). Pattern-broken streak rebuilds from 1 cycle (P0.R5 Phase 0) toward potential extension. **External-fork dimension** introduces user-driven Phase 1 Step 1 (operator creates GitHub forks); SHAs threaded via placeholder option (α) in Plan v1 §2.3.
> 
> **Cycle shape distinction**: P0.R5 introduces external-fork dependency management — materially distinct from prior P0.R cycles. Requires Phase 1 Step 1 user-driven action (GitHub fork creation); SHA placeholders in Plan v1 §2.3 filled at Phase 1.
> 
> **What shipped:** 2 external GitHub forks (D1 + D2) + 1 modified file (requirements.txt; D3) + 3 file-surface deletions (tests/patch_pyannote_io.py + core/voice.py:51 + :95; D4) + 1 NEW file (tests/test_p0_r5_vendor_forked_pyannote.py; D5) + 1 narrative refresh (CLAUDE.md "Pyannote vendoring (P0.R5)" section; D6).
> 
> **D1 (pyannote fork)**: `github.com/HungryFingerss/pyannote-audio` @ `{{SHA_PYANNOTE}}` — 3.3.2 base + 6 patches (Patch 1+2 io.py + Patch 3 pipeline.py + Patch 3-cont inference.py + model.py + Patch 5 mixins.py + Patch 6 protocol.py + Patch 7 model.py weights_only).
> 
> **D2 (speechbrain fork)**: `github.com/HungryFingerss/speechbrain` @ `{{SHA_SPEECHBRAIN}}` — 1.0.3 base + 1 patch (torch_audio_backend.py list_audio_backends rewrite).
> 
> **D3 (dependency declaration)**: requirements.txt adds pyannote.audio git URL line + replaces speechbrain version pin with git URL line. Both use `@<SHA>` form.
> 
> **D4 (runtime patch infrastructure deletion)**: tests/patch_pyannote_io.py DELETED entirely + core/voice.py:51 + :95 monkeypatch sites DELETED.
> 
> **D5 (test surface)**: tests/test_p0_r5_vendor_forked_pyannote.py NEW file with 9 anchors (A1-A9; hybrid source-inspection + CUDA-gated behavioral per Q6).
> 
> **D6 (CLAUDE.md narrative refresh)**: "Pyannote dependency maintenance (Session 88)" section REPLACED with "Pyannote vendoring (P0.R5)" section. Documents fork URLs + SHA-pin model + upstream-merge procedure + github-availability assumption + operator mitigation per pre-mortem §4 #3.
> 
> **Total P0.R5 LOGICAL ANCHORS: 9** (Plan v1 §3 LOCK EXACT MATCH at exact mid 9 inclusive ±15% band [7.65, 10.35]).
> 
> **Q5 closure under MID-RANGE methodology**: auditor mid 9, Plan v1 lock 9, **closure actual {{N}}** ({{0%|−11.1%|+11.1%}}; {{exact mid|ON-TARGET}}). Doctrine `### Phase-0-granular-decomposition-enables-accurate-estimates` **BUMPS 17 → 18 SUPPORTING INSTANCES**.
> 
> **Plan v1 §4 honest-count commitment HONORED — 24th instance of `Explicit-closure-honest-count-commitment` discipline** (23rd MADE + 24th HONORED per STRICT separation).
> 
> **6/6 deliberate-regression confirmations PASSED** (a/b/c/d/e/f per §2.6). All reverts restored cleanly.
> 
> **`### Zero-precision-items-at-auditor-review` doctrine 17 → 18 instances** (Phase 0 17th + Plan v1 18th). **OPTIONAL-Plan-v2 path TAKEN — 8th proof case** banked under absorbed sub-rule track record (P0.S3 + P0.B3 + P0.B5 + P0.B6 + P0.S8 + P0.R2 + P0.R3 + P0.R5). Pattern-broken streak rebuild starts (P0.R4 Plan v1 was last block; P0.R5 Phase 0 + Plan v1 + closure = 3 consecutive clean OR architect closure-audit fires).
> 
> **`Pre-audit-quantifier-precision-refined-by-grep` 3 → 4 instances** banked at Phase 0 verdict (NEW LAYERED-AXIS sub-shape).
> 
> **Strict-mode 65 → 68 applications + 19 → 20 closures** (3-artifact OPTIONAL-Plan-v2 cycle if clean: Phase 0 + Plan v1 + closure; Plan v2 skipped). **Discipline counts (3-artifact cycle)**: spec-first review cycle 75 → 78-for-78 at closure. **`### Grep-baseline-before-drafting` 32 → 35 instances** (3 artifacts). **Cross-cycle-handoff transparency precedent 38 → 41 successful** (3 artifacts). **Spec-time grep-verification 42 → 45 instances** (3 artifacts).
> 
> **`### Twin-filename-pitfall-prevention` 19 → 20 preventive events** honored at Phase 0 (no doctrine count bump per locked enumeration rule).
> 
> **Auditor-Q5-estimates-trail-grep 23 → 24 banked closures** at 0% ON-TARGET reading (if closure-actual = 9 exact). Trajectory: 10th consecutive 0% reading extends per `Doctrine-prediction-precision-improving-over-arc`.
> 
> **Deferred-canary strategy 22nd application** — entry pasted verbatim into `c:\Users\jagan\dog-ai\to_be_checked.md`.
> 
> **Known Limitations (P0.R5 closure)**:
> 
> 1. **GitHub-availability assumption** — external forks create deployment dependency on github.com availability + fork-repo persistence. Documented in D6 CLAUDE.md narrative + pre-mortem §4 #3 mitigation (operator maintains local clone; re-create from clone if fork lost).
> 2. **Upstream-merge requires manual patch re-application** — when pyannote or speechbrain releases new version, operator must `git fetch upstream + merge + reapply patches + bump SHA`. Procedure documented in D6 CLAUDE.md narrative.
> 3. **Q4 Pyannote 4.x upgrade deferred** — CLAUDE.md locks 3.3.2 pin per Session 88; 4.x requires torchcodec which has its own torch 2.10 incompat. Separate spec when torchcodec catches up.
> 4. **A8 + A9 CUDA-gated behavioral anchors** — skip on Windows dev / Linux CI without GPU. Source-inspection anchors (A1-A3 + A6-A7) always run.
> 5. **D5 fallback** — Option D (SpeechBrain spectral-clustering diarization) reference preserved in D6 CLAUDE.md for emergency pivot if forks stale.
> 
> **Cumulative suite**: pending closure (+9 new pytest functions from D5 test file; ZERO Python production code changes beyond `core/voice.py:51` + `:95` monkeypatch deletions which simplify the module).
> 
> **Files touched (5 modified/new + 2 external forks):** see Plan v1 §1.2 enumeration.

**§5.1 5-surface landing checklist:**

1. ✓ `c:\Users\jagan\dog-ai\dog-ai\CLAUDE.md` — header P0.R5 entry prepended above P0.R4 + "Pyannote dependency maintenance" section REPLACED with "Pyannote vendoring (P0.R5)" section per D6
2. ✓ `c:\Users\jagan\dog-ai\complete-plan.md::P0.R5` (parent) — status → `[CLOSED]` + closure note
3. ✓ `c:\Users\jagan\dog-ai\dog-ai\complete-plan.md::P0.R5` (subdir) — full closure narrative
4. ✓ `c:\Users\jagan\dog-ai\to_be_checked.md` — 22nd deferred-canary entry + coverage matrix row
5. ✓ Architect memory files via post-closure handoff (`feedback_phase_0_zero_precision_items_at_auditor_review.md` 17 → 18; `MEMORY.md` index refresh)

---

## §6 — Architect's diligent Pass-2 grep enumeration (auditor verification target)

| Grep pattern | Expected matches | Verification |
|---|---|---|
| `tests/patch_pyannote_io.py` file existence | 0 (file DELETED post-Phase 1) | A1 anchor target |
| `requirements.txt` substring `pyannote.audio @ git+https://github.com/HungryFingerss/pyannote-audio.git@` | 1 match | A2 anchor target |
| `requirements.txt` substring `speechbrain @ git+https://github.com/HungryFingerss/speechbrain.git@` | 1 match (replaces old `speechbrain>=1.0.3` line) | A3 anchor target |
| `core/voice.py` `list_audio_backends = lambda` substring | 0 matches (BOTH old line 51 + line 95 sites DELETED per non-blocking observation #1) | A6 anchor target |
| `CLAUDE.md` substring `## Pyannote vendoring (P0.R5` | 1 match | A7 anchor target |
| `CLAUDE.md` substring `github-availability assumption` | 1 match (per D6 documentation requirement per non-blocking observation #1) | A7 anchor target |
| `CLAUDE.md` substring `## Pyannote dependency maintenance (Phase 2, Session 88)` | 0 matches (old section REPLACED per D6) | A7 anchor target |
| `tests/p0_r5*` files | 3 files (audit md + plan v1 md + NEW test py per D5) | Greenfield + Phase 1 |

**Auditor's independent re-grep target at Plan v1 verdict:** all 8 patterns above + cross-check that both monkeypatch sites in core/voice.py are removed (not just one).

**Architect prediction (probabilistic per `Zero-precision-items-pre-closure-predictions-blocked` operational rule + now-elevated formal Pass-2 grep doctrine):** Plan v1 §1.2 + §6 enumeration is diligent; expecting clean auditor independent re-grep verification. If clean → pattern-broken streak rebuilds from P0.R5 Phase 0 onward; doctrine fires at Plan v1 surface (18th instance); 8th OPTIONAL-Plan-v2 proof case reclaimed.

---

## §7 — Doctrine bump projection at closure (closure-conditional per inclusive ±15% band)

| Doctrine | Pre-P0.R5 baseline | Closure projection |
|---|---|---|
| `### Phase-0-granular-decomposition-enables-accurate-estimates` | 17 (post-P0.R4 closure) | 18 IF closure-actual ∈ {8, 9, 10} |
| `### Zero-precision-items-at-auditor-review` | 17 (post-P0.R5 Phase 0) | 18 IF Plan v1 fires clean (0 PIs); ELSE stays 17 |
| `### Induction-surfaces-invariant-gaps` | 11 (post-P0.R3 closure) | 11 (stays unless in-flight detector-strengthening event) |
| `### Architect-reads-production-code-before-sign-off` | 16 (post-P0.R4 closure-audit) | 17 IF architect closure-audit fires at P0.R5 closure |
| OPTIONAL-Plan-v2 sub-rule proof cases | 7 (post-P0.R4 closure — P0.R4 ESCALATED, not a proof case) | 8 IF P0.R5 Plan v1 clears clean + closure-actual ∈ {8, 9, 10} |
| `Explicit-closure-honest-count-commitment` | 22 (post-P0.R4 closure) | 24 (23 MADE + 24 HONORED) |
| Strict-mode applications | 66 (post-P0.R4 closure) | 69 IF 3-artifact cycle (Phase 0 + Plan v1 + closure; clean clear) |
| Strict-mode closures | 19 (post-P0.R4 closure) | 20 |
| Spec-first review cycle | 76 (post-P0.R4 closure) | 79 (3 artifacts × +1) |
| `### Grep-baseline-before-drafting` | 33 (post-P0.R4 closure) | 36 (3 artifacts) |
| Cross-cycle-handoff transparency | 39 (post-P0.R4 closure) | 42 (3 artifacts) |
| Spec-time grep-verification | 43 (post-P0.R4 closure) | 46 (3 artifacts) |
| `Doctrine-prediction-precision-improving-over-arc` | 9+ cycle 0% streak (post-P0.R4 closure) | 10+ cycle 0% streak ONLY IF closure-actual = 9 exact |
| `Pre-audit-quantifier-precision-refined-by-grep` | 4 (post-P0.R5 Phase 0) | stays 4 (no new instance at Plan v1) |
| `### Twin-filename-pitfall-prevention` preventive events | 19 (post-P0.R5 Phase 0) | 20 at closure (no doctrine count bump per locked enumeration rule) |
| `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` (NEW post-P0.R4) | applications track: 1 (P0.R5 Phase 0 = 6th total application post-elevation) | applications track: 7 IF Plan v1 fires clean (caught-clean mode); cumulative applications continue per the discipline's track record |

**Closure-conditional banks pending; locked at architect closure-audit per `Convention-drift-on-discipline-counts` + Path C grep-verify reconciliation discipline.**

---

## §8 — §8 row paste-template

```
| P0.R5 | Vendor forked pyannote + speechbrain (eliminate runtime monkey-patching) | CLOSED 2026-05-23 | D1+D2+D3+D4+D5+D6 + 9 anchors at exact mid 9 inclusive ±15%; 8th OPTIONAL-Plan-v2 proof case reclaimed (lost at P0.R4); `Pre-audit-quantifier-precision-refined-by-grep` 3 → 4 NEW LAYERED-AXIS sub-shape; 2 external GitHub forks (Phase 1 Step 1 user-driven); tests/patch_pyannote_io.py + core/voice.py:51 + :95 monkeypatches DELETED; CLAUDE.md "Pyannote dependency maintenance" → "Pyannote vendoring (P0.R5)" |
```

---

## §9 — Open questions for auditor at Plan v1: **0** (per OPTIONAL-Plan-v2 path candidacy)

All Q1-Q7 LOCKED per Phase 0 verdict 2026-05-23. 2 non-blocking observations absorbed at Plan v1:
- Observation #1 (Q2 github-availability): D6 CLAUDE.md narrative documents the assumption + operator mitigation
- Observation #2 (Q7 SHA-threading): D3 uses placeholder `@<SHA>` syntax per option (α); concrete SHAs filled at Phase 1 Step 1

Plan v1 introduces ZERO new open questions. Plan v1 RATIFIED-PENDING per auditor independent re-grep verification per `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` doctrine.

---

## §10 — 5-phase implementation plan (developer handoff; ~3-4 hours SMALL-MEDIUM cycle)

**Phase 1 Step 0 — Pre-flight (~5 min, architect or user):**
- Grep-verify zero callers of `tests/patch_pyannote_io.py` outside the file itself (architect handed off; developer confirms before deletion)
- Grep-verify `core/voice.py:51` + `:95` monkeypatch sites still match the line numbers (drift check)

**Phase 1 Step 1 — USER-DRIVEN: GitHub fork creation (~15-20 min, user):**
- Create fork at `https://github.com/HungryFingerss/pyannote-audio` from upstream `pyannote/pyannote-audio` `v3.3.2` tag
- Clone fork locally
- Apply 6 patches from `tests/patch_pyannote_io.py` (verbatim via the script's documented Patch 1-3 + 5-7 logic) — Patch 4 is speechbrain (separate fork)
- Commit as single `dog-ai v3.3.2 patches (P0.R5)` commit; capture SHA
- Push to fork
- Repeat for `https://github.com/HungryFingerss/speechbrain` from upstream `speechbrain/speechbrain` `v1.0.3` tag with the 1 speechbrain patch (Patch 4)
- Report 2 SHAs to architect/developer for Plan v1 §2.3 + D6 narrative filling

**Phase 2 — Foundation (~20 min, developer):**
- Edit `requirements.txt` per D3 with concrete SHAs (replace `<SHA_PYANNOTE_FORK>` + `<SHA_SPEECHBRAIN_FORK>` placeholders)
- `pip install --force-reinstall -r requirements.txt` in dev venv; verify `from pyannote.audio import Pipeline` works without runtime patch

**Phase 3 — Deletion (~15 min, developer):**
- Delete `tests/patch_pyannote_io.py` entirely
- Edit `core/voice.py`: delete lines ~51 + ~95 monkeypatch sites (BOTH per non-blocking observation #1)
- Verify `python -c "import core.voice"` still works

**Phase 4 — Test surface + CLAUDE.md refresh (~45 min, developer):**
- Create `tests/test_p0_r5_vendor_forked_pyannote.py` with 9 anchors per §3
- A1-A3 source-inspection + A4-A5 behavioral import + A6 AST scan + A7 source-inspection + A8-A9 CUDA-gated smoke
- Edit CLAUDE.md per D6 — REPLACE "Pyannote dependency maintenance (Phase 2, Session 88)" section with NEW "Pyannote vendoring (P0.R5)" section using concrete SHAs from Phase 1 Step 1

**Phase 5 — Deliberate-regression + closure narrative (~45 min, developer):**
- Run 6 deliberate-regression checks per §2.6 (a/b/c/d/e/f):
  - (a) Re-add `tests/patch_pyannote_io.py` → A1 fires
  - (b) Remove pyannote git URL line from requirements.txt → A2 fires
  - (c) Restore old `speechbrain>=1.0.3` line → A3 fires
  - (d) Re-add `_ta.list_audio_backends = lambda` at core/voice.py:51 OR :95 → A6 fires
  - (e) Replace D6 CLAUDE.md new section with old "Pyannote dependency maintenance" → A7 fires
  - (f) Force pyannote import to fail by reverting to runtime-patch-required state → A4 fires (will be hard to test in clean dev venv; CUDA-gated smoke A8 catches at runtime)
- Honor closure-actual count per §4 honest-count commitment table
- Apply Path C grep-verify reconciliation per `### Convention-drift-on-discipline-counts` discipline
- Land closure narrative per §5 paste-template across CLAUDE.md header + parent + subdir complete-plan.md
- Update `to_be_checked.md` with 22nd deferred-canary entry
- Architect closure-audit handoff: memory file updates per locked discipline

**Expected total: ~3-4 hours** (Phase 1 Step 1 user-driven adds ~20 min coordination overhead; otherwise comparable to P0.R4 SMALL-band cycle).

---

End of P0.R5 Plan v1.
