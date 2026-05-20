# P0.S6 — Secrets Management — Phase 0 Audit

**Date:** 2026-05-18
**Author:** architect
**Status:** Phase 0 audit (pre-Plan-v1). Grep-verified findings + D1-D8 decisions surfaced for joint architect-auditor lock before Plan v1 is drafted. Zero production-code changes in this document.

---

## Premise check (load-bearing — same shape as P0.10 + P0.S1 audits)

The natural framing for "secrets management" is: **stop secrets from leaking through logs / error messages / accidental commits.** The audit reveals that framing is **partially wrong**.

**The production code is already hygienic about secrets.** Four production secrets (TOGETHER_API_KEY, TAVILY_API_KEY, HF_TOKEN, plus the unused-but-reserved GROQ_API_KEY) are correctly threaded into HTTP Authorization headers at the moment of use. None of them appear in any `print()` / log statement as a value-interpolation. None appear in error-handling response-text dumps (Together.ai 4xx response bodies don't echo the request's Authorization header back, verified). No payload class in `core/event_log/types.py` has a secret-shaped field.

**The actual gaps are three different surfaces the naïve framing would miss:**

1. **Dead-credential risk.** `.env` contains `GEMINI_API_KEY` and `SARVAM_API_KEY` set to real values, but **zero production code references either key.** Grep of `**/*.py` for `GEMINI` and `SARVAM` returns nothing. These are orphaned credentials — historical experiments left behind. If `.env` ever leaks (developer mistake, MCP integration spillage, accidental `git add -f .env`), credentials for **three services we don't use** spill alongside the two we do use. We wouldn't notice the leak until billing.

2. **No structural invariant pinning "secrets stay out of logs/payloads/event_log."** The codebase is clean today. Nothing structurally enforces it stays clean. A future contributor (or a future me) could add `print(f"Calling Together with key={CHAT_API_KEY}")` for debugging and forget to remove it. P0.S1's catch-all pattern — gate at the structural level, not just at human-review level — applies here.

3. **No commit-history scan.** The current CI (`.github/workflows/security.yml`) runs `pip-audit` (CVE in deps) + `trivy-fs` (Trivy filesystem scan for secrets in committed files). Trivy fs catches secrets in the current snapshot. **It does NOT scan git history.** If a secret was ever briefly committed (then `.gitignore`'d), it stays in history forever and is publicly visible if the repo is public. No automated check verifies history-cleanliness.

Same shape as P0.10's premise reset: the architect's natural framing pointed at the wrong surface. Phase 0 surfaces the actual gaps before any code phase starts.

---

## Complete secret inventory (grep-verified)

### A. Production-required secrets

| Env var | Used by | Read site | Purpose |
|---|---|---|---|
| `TOGETHER_API_KEY` | brain.py (chat) + brain_agent.py (extract/embed) + bootstrap/classifier | `core/config.py:307` | Primary LLM provider |
| `TAVILY_API_KEY` | brain.py (web search) | `core/config.py:352` | Web search |
| `HF_TOKEN` | voice.py (pyannote model download from gated repo) | `core/voice.py:302` | HuggingFace gated-repo auth |

### B. Reserved but unused secrets (no production code references — yet)

| Env var | Status | Read site | Notes |
|---|---|---|---|
| `GROQ_API_KEY` | Reserved future provider | `core/config.py:309` | Sourced but currently aliased into chat config only as a config-fallback — confirmed by grep, currently never the active provider |

### C. Orphaned secrets in `.env` (real values set, zero production references)

| Env var | In `.env`? | In `.env.example`? | Production refs (grep) |
|---|---|---|---|
| `GEMINI_API_KEY` | Yes (real value) | Yes (empty) | **0** |
| `GEMINI_MODEL` | Yes (real value) | Yes (empty) | **0** |
| `SARVAM_API_KEY` | Yes (real value) | Yes (empty) | **0** |

These three keys are historical experiment artifacts. Production code never reads them. They sit in `.env` and are part of the surface that leaks if `.env` ever leaves the development machine.

### D. Non-secret env-var reads (config / mode flags — not credentials)

| Env var | Read site | Purpose |
|---|---|---|
| `EVENT_LOG_ENABLED` | `core/event_log/producer.py:55` | P0.0.7 toggle |
| `EVENT_LOG_TESTING` | `core/event_log/producer.py:56` | P0.0.7 test mode |
| `CLASSIFIER_DB_PATH_OVERRIDE` | `core/classifier_graph.py:84` | Test/dev override |
| `INSIGHTFACE_LOG_LEVEL` | `core/vision.py:20` | Module-level config write (suppresses InsightFace noise) |
| `CHAT_API_KEY` | bootstrap/classifier/stage_3_classify.py:94 | Bootstrap-script fallback for offline pipelines |
| `CAMERA_INDEX`, `OLLAMA_MODEL`, `PYTHON_PATH` | various scripts | Non-secret config |

---

## Read-site enumeration (grep-verified, no missed paths)

### Authorization-header construction (the 9 places production secrets actually transit network)

```
core/brain.py:87       — _chat_http   = AsyncClient(headers={"Authorization": f"Bearer {CHAT_API_KEY}"})
core/brain.py:97       — _extract_http = AsyncClient(headers={"Authorization": f"Bearer {EXTRACT_API_KEY}"})
core/brain_agent.py:225   — _call_llm_chat header (per-request)
core/brain_agent.py:4194  — extraction agent header
core/brain_agent.py:4675  — prompt-pref-agent header
core/brain_agent.py:5040  — embedding agent header
core/brain_agent.py:5291  — household extraction header
core/brain_agent.py:5582  — social graph header
core/brain_agent.py:5650  — insight agent header
```

All 9 use the same pattern: `f"Bearer {EXTRACT_API_KEY}"` or `f"Bearer {EMBED_API_KEY}"`. No leaks at these sites — they construct the header object passed to httpx; httpx handles transport.

### HF_TOKEN

`core/voice.py:302` reads `os.getenv("HF_TOKEN")`. Line 304: `print("[Voice] HF_TOKEN missing — pyannote pipeline cannot load ...")` — names the env var, not the value. Line 313: passes `use_auth_token=hf_token` to pyannote `Pipeline.from_pretrained` — model loader handles internally. SAFE.

### Log-surface review (what gets printed when things fail?)

The risky surfaces are:

| Path | Line | Behavior | Verdict |
|---|---|---|---|
| `core/brain.py:81` | `print("[Brain] WARNING: CHAT_API_KEY is not set...")` | Names env var, not value | SAFE |
| `core/brain_agent.py:231` | `print(f"[{agent_name}] HTTP {status_code}: {resp.text[:200]}")` | Provider 4xx body doesn't echo Authorization header | SAFE |
| `core/brain_agent.py:4203` | Same pattern in ExtractionAgent | SAFE |
| `core/brain_agent.py:250` | `print(f"[{agent_name}] {type(e).__name__}: {detail}")` where `detail = str(e)` | httpx error str() doesn't include header content | SAFE |
| `bootstrap/classifier/stage_3_classify.py:96` | `print("[stage_3_classify] TOGETHER_API_KEY (or CHAT_API_KEY) not set")` | Names env var, not value | SAFE |

**Zero confirmed leak sites in production code today.** That's the good news. The bad news is that nothing **structurally prevents** a future leak.

### Event-log payload review (P0.0.7 surface)

All 12 PayloadV1 dataclasses in `core/event_log/types.py` reviewed by field-name inspection. None contain:
- `*_key`, `*_token`, `*_secret`, `auth*`, `credential*` fields.
- Free-form `metadata` / `extra` / `kwargs` fields that could absorb arbitrary data.

The closest field is `AudioInPayload.stt_text` (transcribed user speech) — not a secret but is personal data. P0 privacy work already addressed cross-person retrieval (`_visibility_clause`, Part XXV); replay-side privacy is its own concern but out of P0.S6 scope.

**Conclusion:** event_log payload surface is safe by current schema; no secret can land there via existing producer hooks. But there's no structural invariant pinning this property — a future PayloadV1 addition could introduce a secret-shaped field without surfacing the risk.

---

## CI security surface

Current `.github/workflows/security.yml`:

- **pip-audit** — scans `requirements.txt` for CVEs in transitive deps. Runs weekly + on requirements.txt change. Strict mode (`--strict`) currently set but with `|| true` swallow (initial-rollout posture — gather findings first before failing the build).
- **trivy-fs** — Trivy filesystem scan on the current snapshot. Severity `CRITICAL,HIGH`. Uploads SARIF to GitHub Security tab. **Does NOT fail the build** (`exit-code: 0`) — initial-rollout posture.

**What Trivy fs catches:** secrets in committed files (current snapshot only). Patterns include `(api_key|token|password) = "...."` shape literals.

**What Trivy fs does NOT catch:**
1. **Git history** — secrets briefly committed then `.gitignore`'d remain in `git log -p` output forever. Public repos make this exploitable.
2. **Pre-commit leakage** — if a developer does `git add -f .env` to force-add the env file, gitignore is bypassed. Trivy catches it post-commit in CI; pre-commit hook would catch pre-commit.
3. **Subtle environment leaks** — `print(os.environ)` would technically leak everything; Trivy would flag the print but only at filesystem scan time.

### CI workflow secret usage

- `.github/workflows/slow.yml` uses `secrets.TOGETHER_API_KEY` for network-tagged tests when the secret is present. Standard GitHub Actions pattern; secret stored encrypted, injected into env at job runtime. SAFE.
- `.github/workflows/fast.yml` and `security.yml` don't consume secrets.

---

## D1-D8 architectural decisions surfaced for joint lock

### D1 — P0.S6 scope

Three options for how broad P0.S6 reaches:

- **D1.a — Structural-invariant + tests + orphan cleanup only.** No CI workflow additions; no secrets manager migration. Smallest scope; protects against future regressions of "no secret in log / payload" properties + closes the orphaned-credentials surface today.
- **D1.b — D1.a + add commit-history secret scan to CI** (TruffleHog / gitleaks). Defense-in-depth covering both current and historical leaks.
- **D1.c — Migrate to structured secrets management (Vault, Doppler, AWS Secrets Manager, etc.).** Overkill for single-developer single-machine deployment; introduces operational burden + cloud dependency without proportionate threat-model justification.

**Architect's lean:** D1.b. Structural invariant + CI scan is the right combined surface — same architectural shape as P0.S1's hybrid (per-call-site + catch-all). D1.c is yak-shaving for a solo developer; revisit when a second developer joins or when KaraOS becomes partner-deployed (Part LI roadmap).

### D2 — Orphaned credentials (`GEMINI_API_KEY`, `SARVAM_API_KEY`)

Three options:

- **D2.a — Remove from `.env` + `.env.example`** (just delete the orphan keys, leave the credentials valid at the provider).
- **D2.b — Rotate (invalidate at provider) AND remove from `.env`/`.env.example`.** Closes both the local-surface risk and the credentials-valid-but-unused risk.
- **D2.c — Keep with comment "reserved for future work."** Adds confusion + maintains leakage surface for no benefit.

**Architect's lean:** D2.b. Rotation is free (~2 minutes per provider — invalidate the API key in the Gemini console + Sarvam console). The cost of leaving stale-but-valid credentials lying around is permanent; rotation closes that surface forever. D2.a is a half-measure (real credentials still valid at provider). D2.c is straightforwardly wrong.

### D3 — Structural invariants

Three candidate properties:

- **D3.a — AST scan rejecting any `print(...)` / `logger.*(...)` that interpolates a secret variable.** Pattern: detect `f"{X}"` / `% X` / `.format(X)` / concatenations where X resolves to `*_API_KEY` / `*_TOKEN` / `*_SECRET` / `_hf_token` / etc.
- **D3.b — AST scan centralizing env-var reads.** `os.environ` / `os.getenv` / `environ[...]` only allowed in `core/config.py` + a small explicit allowlist (event_log producer, voice.py, vision.py for non-secret config writes).
- **D3.c — AST scan on event_log payload definitions.** Reject any new `PayloadV1` dataclass with field name matching `(.*_key|.*_token|.*_secret|auth.*|credential.*)`. Future-proofs the event-log surface against secret-shaped fields.
- **D3.d — All three combined.**

**Architect's lean:** D3.d (all three). They're complementary — D3.a protects the immediate print/log surface, D3.b limits secret-read surface area (any new env-var consumer must go through config.py and surface in code review), D3.c protects the event_log surface specifically.

Cost of all three: ~3-5 AST tests, ~half-day to write + verify.

### D4 — Commit-history scan in CI

Four options:

- **D4.a — Add TruffleHog as a GitHub Actions workflow.** Industry-standard, good false-positive rate, integrates cleanly. Scans full history each run.
- **D4.b — Add `detect-secrets` (Yelp).** Baseline + diff approach; requires maintaining a `.secrets.baseline` file with known false positives. More maintenance overhead.
- **D4.c — Add `gitleaks`.** Rust-based, fast, good for monorepos. Comparable to TruffleHog.
- **D4.d — Don't add a history scan.** Rely on Trivy fs current-snapshot + manual diligence.

**Architect's lean:** D4.a (TruffleHog). Best-in-class for repos like this — clean GitHub Actions integration, signed-API verification (TruffleHog can verify a found credential is actually valid before flagging, reducing FP rate), no baseline file to maintain.

Phase 0 sub-step: run TruffleHog locally **before** Plan v1 commits to find any existing history leaks. If history is dirty, that becomes its own scope item (rotate the leaked credentials + commit-history surgery / acceptance).

### D5 — Pre-commit hook for secret detection

Two options:

- **D5.a — Add a `.pre-commit-config.yaml` running `detect-secrets` or equivalent on staged files.** Fail-fast: secret is caught at `git commit` time, not in CI.
- **D5.b — Don't add a pre-commit hook.** Rely on CI to catch.

**Architect's lean:** D5.a. Pre-commit is cheap (~30 sec per commit), runs only on staged content, catches the developer's most common mistake (forgot to add `.env` to gitignore in a fresh clone). For solo-dev workflow, the fast feedback loop is worth more than the negligible time cost.

### D6 — Test fixture posture

Current state: tests that need a real API key (`tests/smoke_privacy_classifier.py`) check `os.environ.get("TOGETHER_API_KEY")` and skip when missing. Other tests use `MagicMock()` patches.

**Decision:** keep current pattern. No structural invariant needed — pattern is already clean. Re-visit if a future test surfaces an anti-pattern.

### D7 — Event-log invariant alignment with D3.c

D3.c proposes structural rejection of secret-shaped field names in PayloadV1 dataclasses. This is also a load-bearing P0.0.7 contract property. **Action:** Plan v1 specifies that this invariant lives in `tests/test_event_log_invariants.py` alongside the existing D7 N=1 producer-uniqueness scan, not in a separate P0.S6-only test file. Keeps event-log invariants colocated. The test naming pattern continues to be `test_<event_log_property>_*`.

### D8 — Validation gate (P0.S6's canary equivalent)

P0.S1's canary was a live attack simulation. P0.S6's canary is structural: **run the full TruffleHog scan against git history as the closure gate.** Acceptance criteria:

- TruffleHog reports **zero verified secrets** in the full git history.
- Any *unverified* findings (high-entropy strings that look secret-shaped but aren't real keys) are reviewed + either fixed (rename the false-positive trigger) or added to a small documented allowlist.

If TruffleHog reports verified secrets in history: STOP. Rotate the leaked credentials at the provider, decide whether to perform git history surgery (BFG / git-filter-repo) versus accept-and-rotate. That decision becomes its own sub-decision; not pre-committed in Plan v1.

---

## What this audit is NOT claiming

To stay honest about scope:

- **NOT migrating to a secrets manager.** No Vault, no Doppler, no AWS Secrets Manager. `.env` + GitHub Actions encrypted secrets are sufficient for current threat model (solo dev, single machine, no production deploy-to-strangers).
- **NOT preventing all possible secret leakage.** A determined developer can still bypass any structural check via `eval()` / dynamic attribute access. Structural enforcement is defense-in-depth, not impenetrable.
- **NOT covering downstream provider-side risk.** If Together.ai's database leaks our API key, structural defense in our code helps zero. That's a provider-level threat; rotation discipline is the only defense.
- **NOT touching the personal-data privacy surface (Part XXV).** That's already P0.S6-adjacent but a separate concern — `_visibility_clause`, P0.0.7 event-log replay personal-data exposure, etc. Those have their own privacy invariants.

---

## Test-plan sketch (for Plan v1, after D-decisions lock)

Anticipating the test surface that will land in Plan v1:

| Test | Scope | Asserts |
|---|---|---|
| `test_secrets_no_value_interpolation_in_prints` | AST structural | No `f-string` / `%` / `.format()` / concat in any production `print()` / `logger.*()` includes a Name resolving to `*_API_KEY` / `*_TOKEN` / etc. (D3.a) |
| `test_secrets_env_reads_centralized` | AST structural | Every `os.environ` / `os.getenv` / `environ[...]` in `core/*.py` is in either `core/config.py` or the explicit allowlist (D3.b) |
| `test_event_log_payload_no_secret_fields` | AST structural | Every dataclass in `core/event_log/types.py` has zero fields matching `(.*_key|.*_token|.*_secret|auth.*|credential.*)` regex (D3.c) |
| `test_secrets_orphans_removed` | Source-inspection | `.env.example` contains only the production-required env vars (no `GEMINI_API_KEY` / `SARVAM_API_KEY` entries) (D2.b) |
| `test_trufflehog_history_scan_baseline` | Smoke / integration | The TruffleHog scan reports zero verified secrets across full git history (D4.a + D8) — runs in slow CI tier, not on every PR |
| `test_pre_commit_config_present` | Source-inspection | `.pre-commit-config.yaml` exists + lists detect-secrets or equivalent (D5.a) |

Approximately 6 tests. Plus the rotation of GEMINI + SARVAM credentials (D2.b, manual provider-side action — not a pytest test, but a closure-report checkbox).

---

## Estimated effort

Once D-decisions lock and Plan v1 is approved:

- **D3 AST invariants** (3 tests): ~half-day.
- **D2 orphan cleanup** (rotate + remove from .env / .env.example): ~30 minutes.
- **D4 TruffleHog CI workflow + Phase 0 sub-step running it locally first**: ~half-day (workflow add + baseline scan + triage any findings).
- **D5 pre-commit hook**: ~1 hour (add .pre-commit-config.yaml + verify locally).
- **D7 event-log invariant**: ~1 hour (small addition to existing test file).
- **Closure docs + verification pass**: ~1 hour.

**Total: ~1-1.5 days** if no historical secrets surface from D4 sub-step. If TruffleHog finds historical leaks, add 0.5-1 day for rotation + decision on history surgery vs accept.

---

## Pre-Plan-v1 sub-step (architect's recommendation)

**Run TruffleHog locally against the repo's git history before drafting Plan v1.** Reason: if history is dirty, that materially changes Plan v1's scope. We want to know what we're committing to before locking the spec.

Command shape (architect to run, no developer involvement needed):

```bash
# Run from a temp clone to avoid mutating the working tree
docker run --rm -v "$(pwd):/repo" trufflesecurity/trufflehog:latest git file:///repo --json --only-verified > trufflehog_baseline.json
```

If `trufflehog_baseline.json` reports zero verified secrets → clean baseline, Plan v1 proceeds with the locked D-decisions. If non-zero → Plan v1 expands scope to cover credential rotation + history-surgery decision.

This isn't a hard prerequisite — Plan v1 can proceed without it and learn about historical leaks during D4 work — but doing it now de-risks the spec.

---

## Next steps (waiting on auditor)

1. **Auditor reviews this Phase 0 audit document.**
2. **Auditor locks D1-D8** (or pushes back with alternatives).
3. **Architect drafts Plan v1** against the locked decisions. Target: same day as D-lock.
4. **Auditor reviews Plan v1.** Plan v2 (if needed) incorporates feedback.
5. **Joint sign-off → code phase starts.** Per the spec-first review cycle discipline (7-for-7).

---

## Reference documents

- `core/config.py:307,309,352` — env-var reads (TOGETHER, GROQ, TAVILY)
- `core/voice.py:302` — HF_TOKEN read for pyannote
- `core/brain.py:80-102` — httpx client construction with Authorization headers
- `core/brain_agent.py:225, 4194, 4675, 5040, 5291, 5582, 5650` — per-request Authorization header construction
- `core/event_log/types.py` — 12 payload dataclasses (none currently contain secret-shaped fields, but no structural invariant enforces this)
- `.github/workflows/security.yml` — current CI security workflow (pip-audit + trivy-fs)
- `.github/workflows/slow.yml` — uses `secrets.TOGETHER_API_KEY` for network-tagged tests
- `.env` — local config (gitignored; contains real values incl. the orphaned GEMINI/SARVAM keys)
- `.env.example` — committed template (all values empty)
