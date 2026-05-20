# P0.S6 — Secrets Management — Plan v2

**Date:** 2026-05-18
**Author:** architect
**Status:** Plan v2. Drafted against locked D1-D8 + auditor's 5 precision items from Plan v1 review. Plan v1 retained at `tests/p0_s6_plan_v1.md` for delta visibility. Standing by for auditor's Plan v2 review → joint sign-off → developer handoff.

**Phase 0 audit:** `tests/p0_s6_audit.md` (2026-05-18, premise reset).
**TruffleHog baseline:** completed 2026-05-18 — clean, 0 verified findings, 17 entropy-only false positives dispositioned across 4 categories.

**Delta from Plan v1:**
- **MEDIUM 1** — D3.a `_SECRET_NAMES` frozenset enumerated explicitly. Belt-and-braces with the regex pattern (regex catches future *_API_KEY shapes; frozenset catches known names that don't match the regex like lowercase `hf_token`).
- **MEDIUM 2** — D3.b detection algorithm disambiguates `ast.Load` (read) vs `ast.Store` (write). Auditor's option (b) locked: flag both reads and writes for defense-in-depth; INSIGHTFACE_LOG_LEVEL kept in allowlist as a documented write-context exception.
- **MEDIUM 3** — TruffleHog workflow split into two jobs: PR diff scan (base/head) + scheduled full-history scan (no base/head; scans entire repo). Conditional configuration via `if: github.event_name`.
- **LOW 4** — Phase 3 second test clarified as YAML structure check (testable locally, not GH-Actions-dependent). `@pytest.mark.slow` marker dropped; the test runs in the fast tier alongside other AST/source-inspection tests.
- **LOW 5** — Allowlist operational maintenance flow documented in §12 open items.

Locked D-decisions and Plan v1 contract clauses unchanged.

---

## 1. Locked decision reference (unchanged from Plan v1)

| ID | Locked at |
|---|---|
| D1 Scope | D1.b — structural + CI history scan, no Vault |
| D2 Orphan credentials | D2.b — rotate + remove |
| D3 Structural invariants | D3.d — all three (no-secret-in-prints + centralize env reads + no-secret-fields in payloads) |
| D4 CI history scan | D4.a — TruffleHog |
| D5 Pre-commit hook | D5.a — add (detect-secrets) |
| D6 Test fixtures | Keep current skip-when-missing pattern |
| D7 Event-log invariant placement | Colocate in tests/test_event_log_invariants.py |
| D8 Validation gate | Zero verified secrets in TruffleHog history scan |
| P1 D3.b scope | Runtime in scope; bootstrap/enroll.py/audit_person.py/delete_person.py/migrate_* explicitly out |
| P2 TruffleHog prereq | DONE 2026-05-18, baseline clean |
| P3 Tool consistency | detect-secrets at pre-commit + TruffleHog v3 at CI |
| P4 Unverified disposition | Rename / allowlist with rationale / rotation+surgery. No silent ignore |
| P5 Sub-pattern A | Bank as memory-note at closure (3rd instance). Do NOT elevate to CLAUDE.md doctrine |

---

## 2. `_SECRET_NAMES` explicit enumeration (MEDIUM 1)

Plan v1 §4.1 referenced `_SECRET_NAMES` alongside the regex pattern without enumerating. Plan v2 locks the explicit set.

**Location:** top of `tests/test_secrets_invariants.py` alongside the test code.

```python
# P0.S6 D3.a — explicit secret-variable names for the no-secret-in-prints scan.
#
# This frozenset is BELT-AND-BRACES with the regex pattern below:
#
#   _SECRET_NAME_PATTERN = re.compile(
#       r"(?i).*(_api_key|_token|_secret|_password|_pass|_auth|_credential).*"
#   )
#
# The regex catches future-introduced variables matching the *_API_KEY / *_TOKEN /
# etc. naming convention. The frozenset catches CURRENT names that the regex MAY
# miss — specifically `hf_token` (lowercase local variable at core/voice.py:302
# which doesn't match `_TOKEN` requiring leading underscore/word boundary in
# common regex setups).
#
# Both layers fire on every `print(...)` / `log.*(...)` interpolation; a match
# from EITHER counts as a violation. Adding a new secret variable in production
# requires either matching the regex pattern OR adding to this frozenset.
_SECRET_NAMES: frozenset[str] = frozenset({
    # Active production secrets (read via os.getenv in core/config.py + core/voice.py)
    "CHAT_API_KEY",          # core/brain.py line 87 — Authorization header for chat LLM
    "EXTRACT_API_KEY",       # core/brain_agent.py multiple sites — Authorization header
    "EMBED_API_KEY",         # core/brain_agent.py line 5040 — embeddings
    "VISION_API_KEY",        # core/config.py line 342 — vision (currently disabled, alias to TOGETHER)
    "TOGETHER_API_KEY",      # core/config.py line 307 — root provider key
    "TAVILY_API_KEY",        # core/config.py line 352 — web search
    "GROQ_API_KEY",          # core/config.py line 309 — reserved future provider
    "HF_TOKEN",              # core/voice.py line 302 — pyannote gated-repo access (uppercase env var name)
    "hf_token",              # core/voice.py line 302 — lowercase local variable holding HF_TOKEN value
    # Rotated-but-kept-for-blocking — D2.b rotated these at provider; frozenset
    # entry blocks re-introduction in production code via prints/logs.
    "GEMINI_API_KEY",
    "SARVAM_API_KEY",
})

_SECRET_NAME_PATTERN = re.compile(
    r"(?i).*(_api_key|_token|_secret|_password|_pass|_auth|_credential).*"
)


def _is_secret_name(name: str) -> bool:
    """Return True if `name` is a known secret variable OR matches the secret-name
    regex pattern. Belt-and-braces — both layers fire independently."""
    return name in _SECRET_NAMES or bool(_SECRET_NAME_PATTERN.match(name))
```

**Why this shape:**
- **The frozenset is the explicit list.** Auditable — every entry has a rationale comment. Adding a new secret in production code requires explicitly adding to this frozenset OR matching the regex shape.
- **The regex catches the long tail.** Future-introduced env vars like `BETTERSTACK_API_KEY` match without needing frozenset edit. The regex pattern is conservative — requires a known secret-suffix anywhere in the name. False positives possible (e.g. a variable named `auth_flow_step` would match `_auth`) — handled by the no-secret-in-prints scan returning explicit error messages, allowing the developer to either rename the false-positive variable OR add an explicit allowlist for the specific call site.

**Rotation note:** `GEMINI_API_KEY` and `SARVAM_API_KEY` are KEPT in the frozenset post-D2.b rotation. The credentials themselves are invalidated at provider; the frozenset entry blocks any future code path from re-introducing the variable name in a `print()` interpolation. If someone (intentionally or accidentally) adds back GEMINI integration in the future, the structural test fires and forces explicit design conversation rather than silent re-introduction.

---

## 3. D3.b detection — Load vs Store disambiguation (MEDIUM 2)

Plan v1 §4.2 didn't specify whether the algorithm distinguishes read context (`ast.Load`) from write context (`ast.Store`). Auditor's option (b) locked: **flag both reads and writes for defense-in-depth.**

**Reasoning for option (b):**
- Writes to `os.environ` are rare in production code (single instance: `core/vision.py:20` setting `INSIGHTFACE_LOG_LEVEL` to suppress InsightFace's noisy logger).
- A new write (e.g. `os.environ["TOGETHER_API_KEY"] = "..."`) would be a real architectural concern — it overrides the env var loaded at startup, potentially with a hardcoded value. Surface for review.
- Option (a) — read-only scan — would silently accept any future write. Defense-in-depth scope chooses (b).

**Detection algorithm (locked Plan v2 spec):**

```python
def _scan_env_var_access(tree: ast.AST, filepath: str) -> list[tuple[int, str, str]]:
    """Scan an AST for env-var access via os.environ / os.getenv.

    Returns list of (line_number, env_var_name, access_type) tuples.
    `access_type` is "read" / "write" / "non_literal" / "indirect" / "unknown".

    Detection covers:
      - `os.environ.get("VAR")` and `os.environ.get("VAR", default)`         → read
      - `os.getenv("VAR")` and `os.getenv("VAR", default)`                   → read
      - `os.environ["VAR"]` (Subscript, ast.Load context)                    → read
      - `os.environ["VAR"] = value` (Subscript, ast.Store context)           → write
      - `os.environ.pop("VAR")` / `os.environ.setdefault("VAR", ...)`        → write (mutating method)
      - `os.environ.get(some_var)` where arg is ast.Name (not Constant)      → non_literal
      - `os.environ` reference without subscript (e.g., dict copy)           → indirect

    The function returns ALL access types. The test asserts that every (filepath,
    env_var_name) tuple is either in `_ENV_READ_ALLOWLIST` (with documented
    rationale) OR the filepath is `core/config.py`. The access_type is included
    in the assertion error message so reviewers see "read" / "write" / "indirect"
    explicitly.
    """
    ...
```

**Allowlist** (locked Plan v2 — `_ENV_VAR_ACCESS_ALLOWLIST`):

| File | Env var | Context | Rationale |
|---|---|---|---|
| `core/event_log/producer.py:55` | `EVENT_LOG_ENABLED` | read | P0.0.7 D5 toggle — module-level bool at import time; not a secret |
| `core/event_log/producer.py:56` | `EVENT_LOG_TESTING` | read | P0.0.7 test-mode flag — not a secret |
| `core/classifier_graph.py:84` | `CLASSIFIER_DB_PATH_OVERRIDE` | read | Test/dev path override — not a secret |
| `core/vision.py:20` | `INSIGHTFACE_LOG_LEVEL` | **write** | Module-level `os.environ[...] = "ERROR"` to suppress InsightFace's chatty logger. Documented as a write-context exception per Plan v2 MED 2: writes are flagged by default; this one is explicitly allowed with rationale. |
| `core/voice.py:302` | `HF_TOKEN` | read | Required for pyannote model download. Cannot move to config.py (config.py loads at import time; voice.py lazily decides whether to load pyannote). Lazy read is correct. Read site is hygienic (line 302-313, verified Phase 0). |

**Indirect / non-literal handling:**

The algorithm separately flags non-literal env-var names (`os.getenv(some_var)`) and indirect access (passing `os.environ` itself as an argument). Both fire the structural test with an informative message. Plan v2 ships with empty allowlists for these two access types; if a legitimate case surfaces during code phase, add to a documented `_ENV_INDIRECT_ALLOWLIST` set with rationale.

**Edge case: `os.environ.pop` / `setdefault` / `update`.** These mutating methods change `os.environ` state. The algorithm classifies them as writes. None of these are currently called in production code (verified by grep at Plan v2 drafting). If any future code legitimately needs to mutate the env (e.g., a test-fixture setup), it must be in `tests/` (out of scope) or carry an explicit allowlist entry.

---

## 4. TruffleHog workflow — PR vs scheduled job split (MEDIUM 3)

Plan v1 §5.2 used a single configuration:

```yaml
base: ${{ github.event.repository.default_branch }}
head: HEAD
```

The auditor caught: on scheduled runs (cron Sundays at 04:00 UTC), `HEAD == main` after the scheduled checkout, so `base == head` → empty diff → scans nothing. The "Sundays at 04:00 UTC full-history scan" stated intent doesn't match the actual behavior.

**Plan v2 lock — two-job workflow** with `github.event_name` gating:

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
  # PR job — diff scan on commits introduced by the PR.
  # Catches new secrets added in the PR's commits without scanning all history.
  # Fast (~30 sec); runs on every PR.
  trufflehog-pr-diff:
    if: github.event_name == 'pull_request'
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - name: Checkout (full history for diff context)
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: TruffleHog diff scan (PR commits only)
        uses: trufflesecurity/trufflehog@main
        with:
          path: ./
          base: ${{ github.event.pull_request.base.sha }}
          head: ${{ github.event.pull_request.head.sha }}
          extra_args: --results=verified --json

  # Full-history job — runs Sunday 04:00 UTC + manual dispatch.
  # Scans the ENTIRE repo history for any secret ever committed. Slower (~5 min);
  # catches the long-tail risk (something briefly committed years ago).
  trufflehog-full-history:
    if: github.event_name == 'schedule' || github.event_name == 'workflow_dispatch'
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      - name: Checkout (full history)
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: TruffleHog full-history scan
        uses: trufflesecurity/trufflehog@main
        with:
          path: ./
          # No base/head args — full repo scan.
          extra_args: --results=verified --json
```

**Why two jobs (not one with conditional steps):** the auditor recommended either shape, but two jobs are cleaner because:
1. Different timeout budgets (~10 min for PR diff, ~20 min for full history).
2. Different parallelism characteristics — PR job runs on every PR (potentially many in flight), full-history job runs once weekly.
3. Easier debugging — each job's logs cover one scan type; no conditional log-noise.

The `if:` guards ensure exactly one job runs per trigger. No empty-diff edge case possible.

**Edge case: PRs from forks.** `github.event.pull_request.head.sha` is the fork's HEAD SHA, which is checked out by `actions/checkout@v4`. TruffleHog scans the diff between the fork's commits and the target branch — correct behavior. For solo-dev workflow there are no forks, but the configuration is forward-compatible.

---

## 5. Phase 3 second test — YAML structure check (LOW 4)

Plan v1 §11/§7 described a `TruffleHog reachability test` marked `@pytest.mark.slow`. The semantic was unclear — pytest runs locally, not in GitHub Actions.

**Plan v2 lock — YAML structure check** (auditor's option (a)):

The test parses `.github/workflows/trufflehog.yml` and asserts:
1. File exists at the expected path.
2. YAML parses without error.
3. Triggers include `schedule` + `workflow_dispatch` + `pull_request` (the three intended triggers per Plan v2 §4).
4. Two jobs present: `trufflehog-pr-diff` (with `if: github.event_name == 'pull_request'`) + `trufflehog-full-history` (with `if: github.event_name == 'schedule' || github.event_name == 'workflow_dispatch'`).
5. Both jobs reference `trufflesecurity/trufflehog@main` action.
6. Both jobs use `--results=verified` in extra_args (matches the closure-gate criterion from D8 — verified-only mode reduces false-positive noise).
7. Full-history job has no `base:` / `head:` keys (full repo scan).
8. PR job has `base: ${{ github.event.pull_request.base.sha }}` + `head: ${{ github.event.pull_request.head.sha }}`.

**Marker:** no `@pytest.mark.slow`. Runs in the fast tier alongside other AST/source-inspection tests. Cost: ~milliseconds (small YAML parse + dict lookups).

**Why YAML structure check instead of reachability:** reachability of the GitHub Action is GitHub's concern; we test that OUR workflow file's structural correctness matches Plan v2 §4. If `trufflesecurity/trufflehog@main` is renamed upstream, the action lookup will fail at GitHub Actions runtime — which is the right time to discover that. Locally testing the action's existence would add network dependency to the fast test tier; not worth the friction.

---

## 6. Allowlist operational maintenance flow (LOW 5)

Plan v1 §12 open item #3 mentioned the `.secrets.baseline` regeneration command. Plan v2 §12 extends with the explicit operational flow for adding new high-entropy assets matching existing categories.

**Locked Plan v2 maintenance contract:**

When a new high-entropy file lands that matches an existing disposition category (e.g., a new ML model under `models/`, a new benchmark log under `tests/eval_bench_runs/`, a new pre-computed embedding seed):

1. **Identify the category.** Match the new file against one of the 4 rationale categories: binary file format / git SHA metadata / base64 ML artifact / npm SRI hash.
2. **Extend the `.pre-commit-config.yaml` exclude pattern** to include the new path. Examples:
   - New ONNX model → add `|models/<new_model>\.onnx` to the binary-files exclude group.
   - New benchmark run → no change needed (`tests/eval_bench_runs/.*\.json` already matches).
   - New JSONL seed → no change needed (`data/classifier_scenarios_seed\.jsonl` is path-specific; if a new seed lands under a different filename, add it explicitly).
3. **Regenerate the detect-secrets baseline:**
   ```
   detect-secrets scan --baseline .secrets.baseline --update
   ```
   This updates the baseline to include the new file's entropy hashes. The diff against the prior baseline file should show only the new entries (review for surprises before committing).
4. **Re-run the local TruffleHog v2 scan** to confirm the new findings are entropy-class only (no regex matches). The command writes to a relative path under the repo root so it's platform-portable across Windows + Linux + macOS without depending on a system `/tmp` mount:
   ```
   mkdir -p ./tmp
   trufflehog --repo_path . --regex --entropy=True --json "https://example.com/dummy" 2>/dev/null > ./tmp/trufflehog_check.json
   python -c "import json; print(sum(1 for l in open('./tmp/trufflehog_check.json') if l.strip().startswith('{')))"
   ```
   Note: `./tmp/` is a one-shot scratch path; delete after the scan completes or add `tmp/` to `.gitignore` if it doesn't already match (current `.gitignore` covers binary artifacts + caches but not a bare `tmp/` dir).
5. **Commit** with a message documenting which category the new file falls under (e.g., "Add models/new_classifier.onnx — binary model weights, category 'ML model artifact'").

**The principle:** the **rationale category is the design pattern**; the **exclude pattern is the operational enforcement**. Both must stay in sync. The rationale lives in `tests/p0_s6_plan_v2.md` §6 (Plan v1's disposition table); the exclude lives in `.pre-commit-config.yaml` and TruffleHog workflow config.

**When in doubt:** if a new file's category isn't obvious from inspection, run TruffleHog v2 against it in isolation:

```
trufflehog --repo_path . --regex --entropy=True --json "https://example.com/dummy" 2>/dev/null | grep '<new_file_path>'
```

A finding tagged `"reason": "Generic API Key"` or any other regex class is a **real candidate** — investigate before disposing. Only `"reason": "High Entropy"` findings belong in the false-positive allowlist.

---

## 7. Architectural overview (unchanged from Plan v1)

Three-layer defense-in-depth from Plan v1 §2 stands as-is. The Plan v2 precision items refine the implementation specifications without changing the architecture.

---

## 8. Orphan-credential rotation (D2.b, unchanged from Plan v1 §3)

Manual provider-side actions on Phase 1:

1. Rotate `GEMINI_API_KEY` at https://aistudio.google.com/app/apikey
2. Rotate `SARVAM_API_KEY` at https://www.sarvam.ai/
3. Verify each rotated key no longer authenticates (curl test).
4. Remove `GEMINI_API_KEY`, `GEMINI_MODEL`, `SARVAM_API_KEY` from local `.env` and from `.env.example`.

Closure report logs rotation timestamps.

**Plan v2 addition:** the rotated env var names (`GEMINI_API_KEY`, `SARVAM_API_KEY`) are kept in `_SECRET_NAMES` frozenset (§2). Any future code path that interpolates these names into a `print()` or `log()` would fail D3.a even though the credentials no longer exist — structural block on re-introduction.

---

## 9. Structural invariants (D3.d) — final spec

Three AST tests landing in `tests/test_secrets_invariants.py` (D3.a, D3.b) + `tests/test_event_log_invariants.py` (D3.c colocated per D7).

### 9.1 `test_no_secret_value_in_prints_or_logs` (D3.a — with MED 1)

Detection algorithm (final):

1. Walk AST of every `*.py` under `core/` + `pipeline.py` + `enroll.py`.
2. For each `Call` node where `func.id == "print"` OR `func.attr` matches `(?i)(log|debug|info|warn|warning|error|critical|exception)`:
   - Walk arguments for `JoinedStr` (f-string), `BinOp(op=Mod)` with `%`, `Call(func.attr=="format")`.
   - For each interpolation slot: check if value is a `Name` whose `id` satisfies `_is_secret_name(...)` (§2 helper — frozenset OR regex match).
3. Assert zero matches.

**`_SECRET_NAMES` frozenset enumerated per §2.** Belt-and-braces with `_SECRET_NAME_PATTERN` regex.

### 9.2 `test_env_var_reads_centralized` (D3.b — with MED 2 + P1)

Detection algorithm per §3 above. Flag both reads AND writes. Allowlist enumerated in §3.

**Scope per P1:** runtime (`core/*.py`, `pipeline.py`); out-of-scope: `bootstrap/`, `enroll.py`, `audit_person.py`, `delete_person.py`, `migrate_*.py`, `tests/`.

### 9.3 `test_payload_fields_no_secret_shaped_names` (D3.c, colocated)

In `tests/test_event_log_invariants.py`. Detection algorithm unchanged from Plan v1 §4.3: AST walk of dataclass field declarations; match against `_FORBIDDEN_FIELD_PATTERN`. `_FORBIDDEN_FIELD_PATTERN` reuses the same regex shape as `_SECRET_NAME_PATTERN` (§2) for consistency:

```python
_FORBIDDEN_FIELD_PATTERN = re.compile(
    r"(?i).*(api_key|token|secret|password|auth|credential).*"
)
```

Note: the regex differs from §2's `_SECRET_NAME_PATTERN` by NOT requiring a leading underscore — payload fields use camelCase or snake_case without the `_API_KEY` convention. `auth_token` would match here; `auth_flow_step` would also match (acceptable conservative false positive — payload field naming should avoid `auth` substring anyway).

---

## 10. CI workflows + pre-commit hook (with MED 3)

### 10.1 Pre-commit hook (D5 + P3, unchanged from Plan v1)

`.pre-commit-config.yaml` with detect-secrets, exclude patterns per Plan v1 §5.1.

### 10.2 CI history scan (D4 + P3 + MED 3) — two-job split per §4

The locked workflow shape per §4 above.

### 10.3 Existing security.yml — no changes (unchanged from Plan v1)

---

## 11. Implementation phases (unchanged from Plan v1 §7, test counts revised)

Four phases. Test counts revised for clarity:

### Phase 1 — Orphan rotation + structural invariants (~half-day)

- Manual rotation of GEMINI + SARVAM (Jagan, ~30 min)
- `tests/test_secrets_invariants.py` (new) — 2 tests (D3.a + D3.b)
- `tests/test_event_log_invariants.py` extension — 1 test (D3.c, colocated)
- `.env.example` cleanup — 1 shape test
- `.gitignore` verification for terminal_output*.md — 1 test (N1)

**Phase 1 tests:** 5 total.

### Phase 2 — Pre-commit hook (~quarter-day)

- `.pre-commit-config.yaml` + `.secrets.baseline` generation
- README.md onboarding line
- 1 config-presence test + 1 baseline-validity test

**Phase 2 tests:** 2 total.

### Phase 3 — CI TruffleHog workflow (~half-day)

- `.github/workflows/trufflehog.yml` per §4 two-job shape
- 1 YAML structure check per §5 — runs in fast tier, NOT slow-marked

**Phase 3 tests:** 1 total (reduced from 2 in Plan v1 — the slow-marked reachability test removed per LOW 4).

### Phase 4 — Deliberate-regression confirmations + closure (~quarter-day)

- 3 deliberate-regression confirmations per Plan v1 §7 Phase 4 (D3.a / D3.b / D3.c)
- Closure-report banking (sub-pattern A 3rd instance → memory note)

**Phase 4 tests:** 0 (deliberate-regressions are closure-report items, not pytest cases).

**Net new tests: 8** (5 + 2 + 1 + 0). Down from Plan v1's 9 — the slow-marked reachability test was the unit removed per LOW 4.

**Suite delta: 2302 → ~2310.**

---

## 12. Open items / risks (extended per LOW 5)

1. **Pre-commit hook setup is per-developer.** Solo-dev fine; document for future partner deployment.
2. **TruffleHog v3 signed verification uses provider quotas** (~10 calls per scan, negligible).
3. **`.secrets.baseline` maintenance** — operational maintenance flow locked per Plan v2 §6 above.
4. **D3.b allowlist hardcoding** — static frozenset forces design conversation for new env consumers. Intentional.
5. **NEW (Plan v2 — MED 2)** — `os.environ` writes are flagged by default per D3.b. The single legitimate write (`INSIGHTFACE_LOG_LEVEL` at `core/vision.py:20`) is allowlisted. Any new write requires explicit allowlist entry + rationale.
6. **NEW (Plan v2 — MED 3)** — TruffleHog workflow has two jobs. If GitHub Actions changes behavior of `if: github.event_name == ...` gating, both jobs could trigger on the same event. Test guards against this (§5 — asserts both jobs have their `if:` conditions intact). Belt-and-braces.

---

## 13. Validation gate (unchanged from Plan v1 §9)

1. TruffleHog verified-findings count: 0
2. All 17 unverified findings dispositioned via 4-category allowlists
3. 3/3 deliberate-regression confirmations pass
4. 8 new tests green + full-suite green at ~2310
5. Phase 1 closure report confirms rotation timestamps + .env cleanup

---

## 14. Discipline-count predictions (unchanged from Plan v1)

Per auditor adjudication:

- Spec-first review cycle: **7-for-7 → 8-for-8** on closure
- Tripwires-must-match-deferral-surface: **stays 4-for-4** (D3 invariants are forward-property, not deferral tripwires)
- Developer-improves-on-spec: **stays 6-for-6** (unless code phase surfaces a mechanism improvement)
- Induction-surfaces-invariant-gaps: **candidate +1** if Phase 4 deliberate-regression surfaces a real gap (gap-surfacing only; routine confirmations don't bump per strict read)
- Sub-pattern A — Phase 0 audit catches wrong premise: **bank as memory-note at closure** (3rd instance: P0.10 + P0.S1 + P0.S6). Do NOT elevate to CLAUDE.md doctrine (5+ threshold)

---

## 15. Next steps

1. **Auditor reviews Plan v2.** Plan v3 (if needed) incorporates feedback.
2. **Joint sign-off** → user shares with developer.
3. **Developer executes Phase 1-4** with full-suite verification between phases.
4. **Closure report** with deliberate-regression confirmations + discipline-count updates + memory-note for sub-pattern A.

---

## 16. Reference documents

- `tests/p0_s6_audit.md` — Phase 0 audit
- `tests/p0_s6_plan_v1.md` — Plan v1 (retained for delta visibility)
- `tests/p0_s6_plan_v2.md` — this document (the code contract)
- `core/config.py:307,309,352` — env-var reads (TOGETHER, GROQ, TAVILY)
- `core/voice.py:302` — HF_TOKEN read for pyannote
- `core/event_log/types.py` — 12 payload dataclasses (D3.c target)
- `.github/workflows/security.yml` — existing CI security workflow (preserved)
- `.gitignore` — verify N1 terminal_output*.md
- `tests/test_event_log_invariants.py` — D3.c colocation target (per D7)
