# P0.S6 — Secrets Management — Plan v1

**Date:** 2026-05-18
**Author:** architect
**Status:** Plan v1. Drafted against locked D1-D8 + auditor's 5 precision items from the Phase 0 audit + TruffleHog baseline (clean). Standing by for auditor review → Plan v2 (if needed) → joint sign-off → developer handoff.

**Phase 0 audit:** `tests/p0_s6_audit.md` (2026-05-18, premise reset documented — actual gaps are orphaned credentials + structural-invariant absence + history-scan absence, NOT the assumed log-leak surface).

**TruffleHog baseline pre-Plan-v1 sub-step (auditor precision item 2):** completed 2026-05-18. **Clean — 0 regex-matched findings, 17 entropy-based false positives (all explainable: 11 binary files, 2 git SHAs, 3 base64-ML-embeddings, 3 npm SRI hashes).** Disposition per category enumerated in §6 below.

---

## 1. Locked decision reference (D1-D8 + 5 precision items)

| ID | Locked at | Source |
|---|---|---|
| D1 | **D1.b** — structural invariants + CI history scan, no Vault | Phase 0 audit |
| D2 | **D2.b** — rotate credentials at provider + remove from `.env` and `.env.example` | Phase 0 audit |
| D3 | **D3.d** — all three: no-secret-in-prints + centralize env-reads + no-secret-fields-in-event-log-payloads | Phase 0 audit |
| D4 | **D4.a** — TruffleHog for CI history scan | Phase 0 audit |
| D5 | **D5.a** — pre-commit hook for secret detection on staged files | Phase 0 audit |
| D6 | Keep current skip-when-missing test pattern | Phase 0 audit |
| D7 | Colocate event-log invariant in `tests/test_event_log_invariants.py` | Phase 0 audit |
| D8 | Zero verified secrets in TruffleHog history scan | Phase 0 audit |
| **P1** | **D3.b scope: runtime vs offline-tool domain** — bootstrap/ + enroll.py treated as separate one-shot domain, NOT runtime. Document the exception in test docstring with rationale. | Auditor precision item 1 |
| **P2** | **TruffleHog local baseline scan is a PREREQUISITE**, completed before Plan v1 drafts. ✓ DONE 2026-05-18 — baseline clean, zero verified findings. | Auditor precision item 2 |
| **P3** | **Tool consistency: detect-secrets at pre-commit + TruffleHog at CI** (auditor's option a — two-tool shape). | Auditor precision item 3 |
| **P4** | **Unverified-findings disposition policy: rename / allowlist with rationale / rotation+surgery.** No silent ignore. Every finding gets one of the three dispositions in the closure report. | Auditor precision item 4 |
| **P5** | **Sub-pattern A — 3rd instance.** Bank as memory-note at P0.S6 closure (NOT earlier). 3+ instances threshold crossed (P0.10 + P0.S1 + P0.S6). Do NOT elevate to CLAUDE.md doctrine yet (5+ threshold). | Auditor precision item 5 |

Two non-D-decision items from the auditor flagged for closure-report completeness:

- **N1** — `terminal_output.md` + `terminal_output_*.md` archive files verified in `.gitignore` (one-line check at Phase 1).
- **N2** — CI workflow secret consumption (slow.yml `secrets.TOGETHER_API_KEY`) is covered transitively by D3.a + D3.b; no additional gate needed.

---

## 2. Architectural overview

P0.S6 establishes a **structural-defense-in-depth model** for secrets management, suitable for a solo-developer single-machine deployment that may eventually be partner-deployed (P1.A roadmap). The model has three layers:

```
┌──────────────────────────────────────────────────────────────────────┐
│  Pre-commit (D5 — detect-secrets)                                    │
│    Runs against staged files only. ~30 sec per commit.               │
│    Catches: developer accidentally staging .env / dumping a key.     │
└──────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼ (passes)
┌──────────────────────────────────────────────────────────────────────┐
│  CI structural invariants (D3 — three AST scans)                     │
│    D3.a no-secret-in-prints: AST scan rejects print()/log() that     │
│         interpolates a Name resolving to *_API_KEY / *_TOKEN / etc.  │
│    D3.b centralize env-reads: os.environ/getenv only in core/config.py│
│         + small explicit allowlist with rationale per entry.         │
│    D3.c no-secret-fields-in-event-log: PayloadV1 dataclasses         │
│         field names matched against forbidden regex.                 │
└──────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼ (passes)
┌──────────────────────────────────────────────────────────────────────┐
│  CI commit-history scan (D4 — TruffleHog)                            │
│    Runs against full git history each weekly + on PR.                │
│    Catches: secret ever committed (current OR historical snapshot).  │
│    Verified findings fail the build.                                 │
└──────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼ (passes)
┌──────────────────────────────────────────────────────────────────────┐
│  Production code (already hygienic per Phase 0 audit)                │
│    9 Authorization-header construction sites use f"Bearer {*_KEY}"   │
│    No print/log interpolates a secret value                          │
│    Event-log payloads have no secret-shaped fields                   │
└──────────────────────────────────────────────────────────────────────┘
```

The three layers are **complementary, not redundant**:
- Pre-commit catches the most common developer mistake (staging `.env`) fast and locally.
- CI structural invariants prevent the most common code-level regression (printing a secret).
- CI history scan catches the long-tail risk (something briefly committed years ago).

Production code is already in good shape; P0.S6 adds the *structural enforcement* that keeps it that way.

---

## 3. Orphan-credential rotation (D2.b)

Three credentials in `.env` with real values + zero production code references:

| Credential | Action | Provider |
|---|---|---|
| `GEMINI_API_KEY` | Rotate at provider console → invalidate | https://aistudio.google.com/app/apikey |
| `GEMINI_MODEL` | Not a secret per se (just a model identifier) — remove from `.env` for tidiness only | n/a |
| `SARVAM_API_KEY` | Rotate at provider console → invalidate | https://www.sarvam.ai/ |

**Procedure for closure-time execution:**

1. Log in to each provider's dashboard.
2. Find the API key matching what's in local `.env`.
3. Invalidate / delete / regenerate (provider-specific UI).
4. Verify the old key no longer authenticates (quick `curl` test against provider API).
5. Remove the three entries from local `.env` and `.env.example`.
6. Closure-report logs which keys were rotated + the rotation timestamps.

This step is **manual provider-side action**, not a pytest test. The follow-up D3.b structural invariant prevents the deleted env vars from being re-introduced as production reads in the future (any new `os.getenv("GEMINI_API_KEY")` in `core/*.py` would fail the centralize-env-reads scan).

---

## 4. Structural invariants (D3.d)

Three AST tests landing in a new file `tests/test_secrets_invariants.py`:

### 4.1 `test_no_secret_value_in_prints_or_logs` (D3.a)

**Property:** no production code interpolates a secret value into a print/log statement.

**Detection algorithm:**

1. Walk the AST of every `*.py` file under `core/` + `pipeline.py` + `enroll.py` (NOT under `tests/` or `bootstrap/`).
2. For each `Call` node where `func.id == "print"` OR `func.attr` matches `(?i)(log|debug|info|warn|warning|error|critical|exception)`:
   - Walk the call's arguments for `JoinedStr` (f-string), `BinOp` with `%` (printf-style), or `Call` with `.format(...)`.
   - For each interpolation slot, check if the value is a `Name` whose `id` matches the regex `(?i).*(_API_KEY|_TOKEN|_SECRET|_PASSWORD|_PASS|_AUTH|_CREDENTIAL).*` OR is a known-secret name from `_SECRET_NAMES` frozenset.
3. Assert zero matches.

**Allowlist:** none initially. Plan v1 ships with an empty allowlist; if a legitimate exception surfaces during code phase, add to a documented `_SECRET_LOG_ALLOWLIST` set with rationale per entry.

**Edge cases handled:**
- f-string with concatenation: `print("key=" + CHAT_API_KEY)` — caught via `BinOp` `+` with a `Name` resolving to a secret.
- `.format(...)` call: `print("key={}".format(CHAT_API_KEY))` — caught via `.format()` argument scan.
- Indirect: `s = f"key={CHAT_API_KEY}"; print(s)` — NOT caught (the f-string is in an assignment, not a print). This is a known limitation; the symmetric defense is D3.b (centralize env reads → secret variables only available in `core/config.py`, can't be referenced from elsewhere).

### 4.2 `test_env_var_reads_centralized` (D3.b — with auditor's P1 scoping)

**Property:** every `os.environ` / `os.getenv` / `environ[...]` read in **runtime** code is either in `core/config.py` or in an explicit allowlist with rationale.

**Scope (per auditor precision item 1 — P1):**
- **In scope (runtime):** `core/*.py`, `pipeline.py`.
- **Out of scope (offline / one-shot tools):** `bootstrap/`, `enroll.py`, `audit_person.py`, `delete_person.py`, `migrate_*.py`. These are CLI/offline scripts with different threat model — secrets passed explicitly at invocation time, not loaded at runtime startup.
- **Out of scope (tests):** `tests/` and root-level `test_*.py` files. Test fixtures may legitimately read env vars for skip-when-missing logic.

**Allowlist** (`_ENV_READ_ALLOWLIST: frozenset[tuple[str, str]]` — `(filepath, env_var_name)`):

| File | Env var | Rationale |
|---|---|---|
| `core/event_log/producer.py` | `EVENT_LOG_ENABLED` | P0.0.7 D5 toggle — module-level bool flag at import time; not a secret |
| `core/event_log/producer.py` | `EVENT_LOG_TESTING` | P0.0.7 test-mode flag — not a secret |
| `core/classifier_graph.py` | `CLASSIFIER_DB_PATH_OVERRIDE` | Test/dev path override — not a secret |
| `core/vision.py` | `INSIGHTFACE_LOG_LEVEL` (a write, not read) | Module-level `os.environ[...] = "ERROR"` to suppress InsightFace noise — config write, not credential read |
| `core/voice.py` | `HF_TOKEN` | Required for pyannote model download. Cannot be moved to config.py (config.py loads at import time before voice.py decides to load pyannote; lazy read is correct). Allowlisted with rationale; the read site is hygienic (verified at `voice.py:302-313`). |

**Detection algorithm:**

1. Walk AST of every in-scope file.
2. Find every `Call` to `os.environ.get(...)`, `os.getenv(...)`, or `Subscript` of `os.environ[...]`.
3. For each, check if `(filepath, env_var_literal)` is in `_ENV_READ_ALLOWLIST` OR the file is `core/config.py`.
4. Assert zero unallowlisted reads.

**Edge cases:**
- Non-literal env var name (`os.getenv(some_var)`): flagged for review. AST emits "non-literal env var arg at {file}:{line}, cannot statically determine" with the same opt-out pattern as P0.S1's `# noqa: P0S6-allow-non-literal-env: <rationale>`.

### 4.3 `test_event_log_payload_no_secret_fields` (D3.c — colocated per D7)

**Property:** no dataclass in `core/event_log/types.py` has a field name matching the forbidden regex.

**Detection algorithm:**

1. Parse `core/event_log/types.py` to AST.
2. Walk every `ClassDef` decorated with `@dataclass`.
3. For each field declaration (AnnAssign), extract the field name.
4. Match against `_FORBIDDEN_FIELD_PATTERN = re.compile(r"(?i).*(api_key|token|secret|password|auth|credential).*")`.
5. Assert zero matches.

**Test placement (per auditor D7):** colocated in `tests/test_event_log_invariants.py` alongside the existing D7 N=1 producer-uniqueness scan. Test name: `test_payload_fields_no_secret_shaped_names`.

Note that the existing `AudioInPayload.stt_text` (transcribed user speech) does NOT trigger this — `stt_text` doesn't match any of the forbidden substrings. Personal data is a separate privacy concern (Part XXV), out of P0.S6 scope.

---

## 5. CI workflows + pre-commit hook

### 5.1 Pre-commit hook (D5 + P3)

**Tool: `detect-secrets` (Yelp)** per P3 auditor lock — designed for staged-content pre-commit case, low FP friction on per-commit basis.

`.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.5.0
    hooks:
      - id: detect-secrets
        args: ['--baseline', '.secrets.baseline']
        exclude: |
          (?x)^(
            data/classifier_scenarios\.db|
            faces/.*|
            models/.*|
            tests/eval_bench_runs/.*\.json|
            dog-ai-dashboard/package-lock\.json|
            data/classifier_scenarios_seed\.jsonl|
            \.hypothesis/.*
          )$
```

Baseline file `.secrets.baseline` ships with the 4 categories of expected false positives enumerated from the Phase 0 TruffleHog scan (binary files, git SHAs, ML embeddings, npm SRI hashes).

Setup steps (one-time per dev machine):

```bash
python -m pip install pre-commit detect-secrets
pre-commit install
detect-secrets scan > .secrets.baseline
```

The baseline file IS committed (it's a small JSON file documenting the expected false positives + their hashes — not the secrets themselves). New findings get diff'd against the baseline; only NEW secret-shaped findings fail the commit.

### 5.2 CI history scan workflow (D4 + P3)

**Tool: TruffleHog v3** per P3 auditor lock — best-in-class for git history, signed-verification reduces FP rate.

New file `.github/workflows/trufflehog.yml`:

```yaml
name: trufflehog-history-scan

on:
  schedule:
    - cron: "0 4 * * 0"   # Sundays at 04:00 UTC (after slow.yml)
  workflow_dispatch:
  pull_request:
    branches: ["main"]

permissions:
  contents: read
  pull-requests: write

jobs:
  trufflehog:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      - name: Checkout (full history)
        uses: actions/checkout@v4
        with:
          fetch-depth: 0   # full history needed for TruffleHog

      - name: TruffleHog scan
        uses: trufflesecurity/trufflehog@main
        with:
          path: ./
          base: ${{ github.event.repository.default_branch }}
          head: HEAD
          extra_args: --results=verified --json
```

`--results=verified` filters out unverified entropy findings — TruffleHog calls each candidate's provider API to verify the credential is actually valid before flagging. Verified-only mode reduces noise to ~zero false positives. (Cost: a few seconds of API calls per scan; no impact on dev workflow.)

The scan runs:
- Every Sunday at 04:00 UTC (matches `security.yml` cadence)
- On every PR (catches new history additions)
- On-demand via `workflow_dispatch`

The job FAILS the build on any verified finding. This is stricter than the current `security.yml` which is initial-rollout posture (findings reported, build green). Reason: verified findings mean a real credential exists in the repo's history; that warrants immediate attention.

### 5.3 Existing `security.yml` updates (D8)

The existing workflow stays — `pip-audit` + `trivy-fs` continue running. **No changes to that workflow** in Plan v1. The new TruffleHog workflow is additive, not a replacement.

---

## 6. TruffleHog baseline disposition (auditor P4)

Per the auditor's precision item 4, every unverified finding gets one of three dispositions. Phase 0 sub-step ran TruffleHog v2 locally; results documented here.

**Total findings: 17.** All in **entropy class** (high-entropy strings); **zero regex-matched** API-key shapes.

**Disposition by category:**

| Category | Files | Disposition | Allowlist rationale |
|---|---|---|---|
| **Binary file formats** (high entropy by file structure) | `data/classifier_scenarios.db`, `faces/brain_graph`, `faces/faiss.index`, `models/adaface_ir101.onnx`, `models/antispoof_weights/*.pth` ×2, `models/kokoro-v1.0.onnx`, `models/scrfd_10g_bnkps.onnx`, `models/smart_turn.onnx`, `models/voices-v1.0.bin` | Allowlist entries in `.secrets.baseline` exclude pattern | "Binary file formats inherently have high entropy. SQLite DB, Kuzu graph, FAISS index, ONNX/PyTorch model weights. Not text-secret content." |
| **Git commit SHA hashes** (public repo metadata) | `tests/eval_bench_runs/20260507_091128.json`, `tests/eval_bench_runs/20260507_065217.json` | Allowlist | "40-char hex strings are SHA-1 git commit hashes captured in benchmark run metadata. Public repo state; not credentials." |
| **Base64-encoded ML embeddings** (1024-dim float32 → ~5464 base64 chars) | `data/classifier_scenarios_seed.jsonl` | Allowlist | "Pre-computed E5 embedding vectors serialized as base64. ML model artifact, not credentials." |
| **npm SRI integrity hashes** (Subresource Integrity, public package metadata) | `dog-ai-dashboard/package-lock.json` | Allowlist | "sha512 base64 SRI hashes from npm package-lock.json. Public package integrity metadata; not credentials." |

All four categories enter the `.secrets.baseline` file (D5 pre-commit) and the TruffleHog CI scan ignore patterns (D4). The 17 findings are **explainable false positives**; the closure-gate criterion (zero VERIFIED secrets) is satisfied.

**Rotation list (P4 verified column):** zero. No credential rotation required from the baseline scan (D2.b's GEMINI/SARVAM rotation is the separate orphan-credential cleanup, not a TruffleHog finding).

---

## 7. Implementation phases

Four phases, same shape as P0.S1's Phase 1-4. Each phase independently shippable with full-suite verification between phases.

### Phase 1 — Orphan rotation + structural invariants (~half-day)

**Manual provider-side actions (Jagan executes — not pytest tests):**
1. Rotate `GEMINI_API_KEY` at https://aistudio.google.com/app/apikey
2. Rotate `SARVAM_API_KEY` at https://www.sarvam.ai/
3. Verify each rotated key no longer authenticates (`curl` test)
4. Remove the three entries (`GEMINI_API_KEY`, `GEMINI_MODEL`, `SARVAM_API_KEY`) from local `.env` and from `.env.example`

**Code changes:**
- `tests/test_secrets_invariants.py` — new file with 3 AST tests (D3.a, D3.b, D3.c colocated in `test_event_log_invariants.py` per D7).
- `_SECRET_NAMES`, `_ENV_READ_ALLOWLIST`, `_FORBIDDEN_FIELD_PATTERN` frozensets/regexes alongside the tests.
- `.gitignore` — verify N1 (terminal_output.md + archives). If not already present, add. Closure report flags this even if already present.
- `.env.example` — drop GEMINI / SARVAM entries.

**Phase 1 deliverables (test surface):**
- 3 AST invariant tests (D3.a, D3.b, D3.c)
- 1 `.env.example` shape test (no orphan entries)
- 1 `.gitignore` verification test (terminal_output*.md excluded)
- 5 tests total. Full-suite green at +5 tests.

**Phase 1 closure report:**
- Confirms Jagan rotated 2 credentials with timestamps.
- Confirms `.env`/.env.example cleanup applied.
- Records the 5 invariant tests landed.

### Phase 2 — Pre-commit hook (~quarter-day)

**Code changes:**
- `.pre-commit-config.yaml` — detect-secrets hook configuration (per §5.1).
- `.secrets.baseline` — initial baseline file generated by `detect-secrets scan` against current repo state. Committed to git.
- Documentation update in `README.md` (one-line dev-onboarding mention: "after clone, run `pre-commit install`").

**Phase 2 deliverables (test surface):**
- 1 test asserting `.pre-commit-config.yaml` exists + contains `detect-secrets` (source-inspection)
- 1 test asserting `.secrets.baseline` exists + valid JSON structure
- 2 tests total.

### Phase 3 — CI TruffleHog workflow (~half-day)

**Code changes:**
- `.github/workflows/trufflehog.yml` — new workflow file (per §5.2).
- No production code changes; pure CI addition.

**Phase 3 deliverables (test surface):**
- 1 test asserting the workflow file exists + uses `--results=verified` + scans full history (`fetch-depth: 0`)
- 1 test (smoke) asserting TruffleHog CLI is reachable in the GitHub-actions environment (this test marked `@pytest.mark.slow` since it depends on the CI env)
- 2 tests total.

Phase 3 also validates the workflow by triggering `workflow_dispatch` manually once after the PR lands — confirms the action runs cleanly against the current history. Expected: 0 verified findings.

### Phase 4 — Deliberate-regression confirmations + closure (~quarter-day)

**Three deliberate-regression confirmations** (induction-surfaces-invariant-gaps discipline — same protocol as P0.S1 Phase 4):

1. **D3.a induction**: inject `print(f"key={CHAT_API_KEY}")` in `core/brain.py`. Run `test_no_secret_value_in_prints_or_logs`. Expected: test fires with informative message naming the file:line and the secret variable. Revert; suite green.

2. **D3.b induction**: inject `os.getenv("TOGETHER_API_KEY")` in `pipeline.py` (somewhere not in the allowlist). Run `test_env_var_reads_centralized`. Expected: test fires with the unallowlisted-read message. Revert; suite green.

3. **D3.c induction**: inject a new `auth_token: str` field on `AudioInPayload`. Run `test_payload_fields_no_secret_shaped_names`. Expected: test fires naming the field + the matched forbidden pattern. Revert; suite green.

**Closure report deliverables:**
- Sub-pattern A 3rd instance banked as memory-note per auditor P5.
- Discipline-count predictions evaluated.
- Final test count: pre-P0.S6 2302 → post-P0.S6 ~2311 (+9 tests; matches Plan v1 §11 math below).

---

## 8. Test plan summary

| Phase | Tests | Type |
|---|---|---|
| Phase 1 | 5 | 3 AST invariants (D3.a/b/c) + 1 .env.example shape + 1 .gitignore verification |
| Phase 2 | 2 | 1 pre-commit config presence + 1 baseline validity |
| Phase 3 | 2 | 1 workflow presence + 1 TruffleHog reachability (slow-marked) |
| Phase 4 | 0 | 3 deliberate-regression confirmations (closure-report items, NOT pytest cases) |

**Total new tests: 9.** No pre-existing tests need updating.

Suite delta: 2302 → ~2311.

---

## 9. Validation gate (P0.S6 closure criteria)

Per D8 + auditor P2 + the §6 disposition:

1. **TruffleHog verified-findings count: 0.** Baseline confirmed clean 2026-05-18. Re-confirmed by the CI workflow on first run after Phase 3 lands.
2. **All 17 unverified findings dispositioned** (allowlist with rationale per §6 category — 4 rationale entries cover 17 file findings).
3. **3/3 deliberate-regression confirmations pass** (Phase 4 induction protocol).
4. **All 9 new tests green** + full-suite green at 2311.
5. **Phase 1 closure report confirms rotation timestamps** + `.env`/.env.example cleanup applied.

Anything less = closure blocked; investigate before retrying.

---

## 10. Discipline-count predictions

Per the auditor's closure-gate predictions:

- **Spec-first review cycle: 7-for-7 → 8-for-8** on closure (P0.S6 lands the 8th multi-day spec-first cycle).
- **Tripwires-must-match-deferral-surface: stays 4-for-4** (D3's three invariants are forward-property tests, not deferral tripwires).
- **Developer-improves-on-spec: stays 6-for-6** unless code phase surfaces a mechanism improvement.
- **Induction-surfaces-invariant-gaps: candidate +1** if any of the 3 Phase 4 deliberate-regression checks surface a real gap (e.g. detector doesn't fire on injection). Routine confirmations don't bump per the strict read; gap-surfacing does.
- **Sub-pattern A — Phase 0 audit catches wrong premise: bank as memory-note** at closure (3rd instance: P0.10 + P0.S1 + P0.S6). Auditor P5 lock — do NOT elevate to CLAUDE.md doctrine yet (5+ threshold).

---

## 11. Architectural notes (for the closure-report draft)

These are notes the developer / architect should bank in the P0.S6 closure write-up, not action items:

- **Premise reset surfaced 3 actual gaps** (orphans + structural-invariant absence + history-scan absence) vs the naïve framing (production log leakage — already clean per Phase 0 audit).
- **TruffleHog v2 (Python) was used for the Phase 0 baseline scan**; the CI workflow uses TruffleHog v3 (Go binary via GitHub Actions). v3's signed-verification is the right CI tool; v2 was sufficient for the local entropy-baseline pre-Plan-v1 sub-step. This isn't a tool inconsistency; v3-via-Actions is the canonical CI shape and v2-via-pip is the canonical local-quick-scan shape.
- **17 unverified findings disposed as 4 rationale categories**, not 17 individual entries. The category-level rationale (binary files / git SHAs / ML embeddings / npm SRI) is more robust than per-finding rationale — future additions of the same shape automatically inherit the disposition rather than requiring fresh review.
- **The bootstrap/enroll.py runtime/offline-tool distinction (P1)** is structurally meaningful. Runtime code loads at process startup and serves user requests; secret reads at runtime go through `core/config.py`. Offline tools are invoked manually with explicit secrets in their environment; less centralization makes sense. Future P0.S work may revisit if the offline domain grows (e.g. a new bootstrap pipeline needs different secret-handling).

---

## 12. Open items / risks

1. **Pre-commit hook setup is per-developer.** Solo-dev setup is fine; if KaraOS gains a second developer (or partner integration), the README onboarding step matters more. Document in Phase 2's README touch.
2. **TruffleHog v3 GitHub Action signed verification calls provider APIs.** Each verification is a fast API call but uses Together.ai / Tavily / HuggingFace quotas. Should be negligible (<10 calls per scan); flagged for awareness.
3. **`.secrets.baseline` maintenance.** When the codebase legitimately adds a new high-entropy string (e.g. a new ML embedding file), the baseline needs regenerating. Document in Phase 2's setup notes: `detect-secrets scan --baseline .secrets.baseline --update` is the canonical update command.
4. **D3.b allowlist hardcoding.** `_ENV_READ_ALLOWLIST` is a static frozenset. Future env-var consumers must either move to config.py OR add an explicit allowlist entry via code review. This is intentional (forces design conversation); flagged so the developer knows it's a discipline, not a leaky abstraction.

---

## 13. Next steps

1. **Auditor reviews Plan v1.** Plan v2 (if needed) incorporates feedback.
2. **Joint sign-off** → user shares with developer.
3. **Developer executes Phase 1-4** with full-suite verification between phases (verification-before-completion).
4. **Phase 4 closure report** with deliberate-regression confirmations + discipline-count updates + memory-note for sub-pattern A.

---

## 14. Reference documents

- `tests/p0_s6_audit.md` — Phase 0 audit (premise reset + secret inventory + D1-D8)
- `tests/p0_s6_plan_v1.md` — this document
- `core/config.py:307,309,352` — env-var reads (TOGETHER, GROQ, TAVILY)
- `core/voice.py:302` — HF_TOKEN read for pyannote
- `core/event_log/types.py` — 12 payload dataclasses (D3.c target)
- `.github/workflows/security.yml` — existing CI security workflow (preserved)
- `.gitignore` — verify N1 (terminal_output*.md)
- `tests/test_event_log_invariants.py` — D3.c colocation target (per D7)
