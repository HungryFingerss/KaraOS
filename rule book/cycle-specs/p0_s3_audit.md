# P0.S3 — Required env vars not validated at startup — Phase 0 Audit

**Spec:** P0.S3 (complete-plan.md:593-599) — Required env vars not validated at startup
**Track:** P0 — Security vulnerabilities (`[OPEN]` `[VERIFY]`)
**Mode:** Strict industry-standard (locked 2026-05-19) + deferred-canary (locked 2026-05-20)
**Predecessor closures:** P0.S2 (2026-05-20). Strict-mode now at 9 consecutive applications + 3 closures (P0.S7.5.1 + P0.S7.5.2 + P0.S2).

---

## 0. Pre-audit hypothesis vs grep evidence

**Pre-audit framing (architect mental model):** "Add `_validate_env()` at top of `run()`. Check TOGETHER_API_KEY is non-empty. Decide HF_TOKEN disposition (refuse-to-start vs disable-diarization-with-banner). Done."

**Phase 0 grep-verified findings:**

| Surface | File:Line | Current state |
|---|---|---|
| Primary API key (load-bearing — every brain call) | `core/config.py:307` | `TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY", "")` — defaults to empty string. ZERO validation. Empty key → every chat/extract/embed call 401s silently at runtime (each agent's retry loop swallows then moves on; pipeline keeps running with no brain). |
| Aliased keys (all collapse to TOGETHER_API_KEY) | `core/config.py:322, 327, 332, 342` | `CHAT_API_KEY`, `EXTRACT_API_KEY`, `EMBED_API_KEY`, `VISION_API_KEY` all = `TOGETHER_API_KEY`. **Single validation point sufficient.** |
| Optional provider key (Groq dev tier — not yet on) | `core/config.py:309` | `GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")` — used only when `CHAT_BASE_URL == GROQ_BASE_URL`. Currently config.py:321 has `CHAT_BASE_URL = TOGETHER_BASE_URL`, so Groq path is dormant. Optional — don't validate. |
| Optional search key (Tavily web search) | `core/config.py:352` | `TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")` — `_web_search` already returns structured `{error, hint}` dict when key is missing (Session 79 Fix E). Graceful degradation already shipped. Optional. |
| Pyannote gated-model token (already handled) | `core/voice.py:302-306` | `hf_token = os.getenv("HF_TOKEN")`. If missing: logs `[Voice] HF_TOKEN missing — pyannote pipeline cannot load (gated-model auth). Falling back to ECAPA-valley backend.` + returns None. **The "disable diarization with banner" disposition is ALREADY implemented** — lazy-load discovers it at first diarize call (~10s into pipeline boot, not at startup). |
| `_validate_env` function | (nowhere) | Does NOT exist. Brand-new function. |
| P0.S6 env-read invariant | `tests/test_secrets_invariants.py:13-15, 93-310` | `test_env_var_reads_centralized` AST scan flags any `os.getenv` / `os.environ` access outside `core/config.py` or `_ENV_VAR_ACCESS_ALLOWLIST`. `_validate_env()` MUST read from config.py module attrs (already-centralized), not call `os.getenv()` directly — otherwise the P0.S6 invariant fires. |
| `_ENV_VAR_ACCESS_ALLOWLIST` entries (P0.S6 reference) | `tests/test_secrets_invariants.py:93` | Allowlist exists with documented per-entry rationale. HF_TOKEN's `core/voice.py:302` read IS in the allowlist (otherwise P0.S6 wouldn't have closed green). |

**Pre-audit framing held within ~10% of actual scope.** Five refinements surfaced:

1. **HF_TOKEN is ALREADY handled** at the right level (graceful degradation in voice.py). The P0.S3 spec's "disable diarization with banner" disposition is already shipped — what P0.S3 ADDS is SURFACING the banner at startup (early diagnostic) instead of only at first diarize call (~10s in).
2. **TOGETHER_API_KEY is the only HARD-required key.** Empty TOGETHER_API_KEY means no brain → no useful pipeline. This is the load-bearing validation.
3. **GROQ + TAVILY are intentionally optional.** Both have graceful runtime paths. P0.S3 must NOT validate them at startup (would break valid no-Groq / no-Tavily configurations).
4. **`_validate_env()` reads through config.py.** Centralization-friendly: `if not config.TOGETHER_API_KEY: raise ...`. Does NOT call `os.getenv()` directly. Preserves the P0.S6 invariant.
5. **Early-banner-for-HF_TOKEN is genuinely a separate D-decision** — refuse-to-start (strict) vs early-banner (banner at startup AND degradation at runtime, no double-effort) vs status-quo (only at first diarize call). Architect-recommendation locked at D2 below.

**No sub-pattern A wrong-premise.** Phase 0 confirms scope ≈ pre-audit, with the 5 refinements above. Banking as ON-TARGET instance — NOT a 6th `Phase-0-catches-wrong-premise` instance.

**Scope-expansion check (informal observation):** Pre-audit estimated "1-2 D-decisions, ~4-8 tests." Phase 0 surfaces **2 D-decisions** (D1 TOGETHER required + D2 HF early-banner). Within pre-audit range. Not a `### Phase-0-catches-scope-expansion` instance.

---

## 1. Cross-spec impact analysis

### Upstream dependencies

- **P0.S6 (Secrets management, closed 2026-05-08)** — `test_env_var_reads_centralized` invariant is the STRUCTURAL CONSTRAINT P0.S3 must respect. `_validate_env()` reads from `config.TOGETHER_API_KEY` (not `os.getenv("TOGETHER_API_KEY")`). If P0.S3 violates this, the P0.S6 invariant fires immediately in CI.
- **P0.S2 (Dashboard auth, closed 2026-05-20)** — pipeline.py `run()` now starts with `_ensure_dashboard_token(FACES_DIR)` as the FIRST line. P0.S3's `_validate_env()` should land IMMEDIATELY AFTER that call. Order matters: dashboard token must be generated even if env validation fails (so user has the auth URL to recover after fixing env vars).

### Downstream dependents

- **No specs explicitly depend on P0.S3.** It's a defensive startup check — surfaces config errors that would otherwise silently degrade.
- **P0.R1 / P0.R2 (ONNX session.run wrapping + CPU fallback)** — independent surface. No interaction.

### Sideways (parallel code paths)

- **`core/voice.py::_load_pyannote_pipeline()`** — keeps its current graceful degradation logic (logs HF_TOKEN missing + returns None). P0.S3 ADDS a startup banner that surfaces the same condition earlier. Both paths can coexist; they observe the same `os.getenv("HF_TOKEN")` value at different lifecycle points (boot vs first-diarize).
- **Pipeline-side `_ensure_dashboard_token()`** — runs BEFORE `_validate_env()`. Dashboard auth surface is independent of env-var state.

### Lifecycle trace

- **T=0 (pipeline import):** `core/config.py` module-level `os.getenv(...)` calls happen here. TOGETHER_API_KEY etc. land in module attrs.
- **T=1 (pipeline.run() entry):** `_ensure_dashboard_token(FACES_DIR)` writes/verifies auth token (P0.S2).
- **T=2 (P0.S3 lands):** `_validate_env()` reads `config.TOGETHER_API_KEY`; if empty → raise `RuntimeError` with actionable message. If HF_TOKEN missing → log banner (does NOT raise).
- **T=3 (privilege-table check):** existing assertion in pipeline.py.
- **T=4 (rest of boot):** model loading, vision worker, etc.

All 4 axes traced. No gaps.

---

## 2. D-decisions enumerated

### D1 — TOGETHER_API_KEY required at startup (P0 CORRECTNESS)

**Question:** What happens when `TOGETHER_API_KEY` is empty / missing?

**Current behavior:** Silent runtime degradation. `EmbeddingAgent`, `ExtractionAgent`, `BrainOrchestrator` all hit HTTP 401 from Together.ai on every call. Each agent's retry loop logs the failure and moves on. Pipeline keeps running with no brain. User sees no errors at boot; conversation just doesn't work.

**Locked design:**

```python
# core/env_validation.py (NEW)
"""P0.S3 — startup env-var validation.

Reads from config.py module attrs (centralized per P0.S6 invariant); does
NOT call os.getenv directly so the test_env_var_reads_centralized scan
stays green.

Public entry point: validate_required_env() — called once at pipeline.run()
top. Raises RuntimeError on missing required keys with operator-actionable
message. Logs banner for optional-with-degradation keys (HF_TOKEN).
"""
from __future__ import annotations
import sys
from core import config


def _validate_together_api_key() -> None:
    """TOGETHER_API_KEY is HARD-required. Empty → refuse to start.

    Reads from config.TOGETHER_API_KEY (P0.S6-compliant; the env-read
    happens at config.py module load, this just inspects the resolved value).
    """
    if not config.TOGETHER_API_KEY:
        raise RuntimeError(
            "[EnvCheck] TOGETHER_API_KEY is empty.\n"
            "[EnvCheck] The brain (Llama-3.3 via Together.ai) is the load-bearing\n"
            "[EnvCheck] dependency — every conversation, extraction, and embedding\n"
            "[EnvCheck] call routes through this key. Pipeline cannot run without it.\n"
            "[EnvCheck] Fix: set TOGETHER_API_KEY in your shell or .env file:\n"
            "[EnvCheck]   export TOGETHER_API_KEY='your-key-here'  (POSIX)\n"
            "[EnvCheck]   $env:TOGETHER_API_KEY = 'your-key-here'  (PowerShell)\n"
            "[EnvCheck] Then restart the pipeline."
        )


def _surface_hf_token_banner() -> None:
    """HF_TOKEN missing → log early banner.

    Pyannote diarization gracefully degrades to ECAPA-valley backend when
    HF_TOKEN is absent (core/voice.py:302-306 handles this at first
    diarize call, ~10s into boot). P0.S3 adds an EARLY banner at boot
    so the operator knows BEFORE the first diarize event that
    multi-speaker diarization will use the fallback backend.

    Does NOT raise — diarization fallback is acceptable for single-speaker
    sessions and the ECAPA-valley path returns sensible results for 2
    speakers (the canary scenario today).
    """
    import os
    # Allowlist exception: this single read is intentional; banking the
    # boot-time surface for HF_TOKEN status. The pyannote loader will
    # re-read at first diarize call regardless. P0.S6 _ENV_VAR_ACCESS_ALLOWLIST
    # gets a new entry for env_validation.py.
    if not os.getenv("HF_TOKEN"):
        print(
            "[EnvCheck] HF_TOKEN not set — pyannote speaker-diarization-3.1 "
            "(gated HF model) cannot load. Multi-speaker scenarios will use "
            "the ECAPA-valley fallback backend (binary-split only; less "
            "accurate on 3+ speakers). For diarization-3.1, register at "
            "https://huggingface.co/pyannote/speaker-diarization-3.1 + "
            "set HF_TOKEN.",
            flush=True,
        )


def validate_required_env() -> None:
    """P0.S3 entry point — called once at pipeline.run() top.

    Order: required-checks first (may raise), then optional-banners
    (only print). If required check raises, optional banners don't run.
    """
    _validate_together_api_key()
    _surface_hf_token_banner()
```

**Edit sites:**
- `core/env_validation.py` (NEW) — ~80 LOC
- `pipeline.py::run()` — call `validate_required_env()` immediately after `_ensure_dashboard_token(FACES_DIR)`, before the privilege-table check
- `tests/test_secrets_invariants.py::_ENV_VAR_ACCESS_ALLOWLIST` — add entry for `core/env_validation.py` HF_TOKEN read

**Invariants established:**
- Empty `TOGETHER_API_KEY` → `RuntimeError` at startup with operator-actionable message naming the env var + fix instructions for POSIX and PowerShell.
- `validate_required_env()` reads through `config` module attr (P0.S6-compliant for TOGETHER); single allowlisted `os.getenv("HF_TOKEN")` direct read for the early-banner check.

**Invariants preserved:**
- P0.S6 `test_env_var_reads_centralized` — passes with the new allowlist entry.
- P0.S2 `_ensure_dashboard_token()` ordering — dashboard token generation happens BEFORE env validation (user can recover auth even if env vars need fixing).
- Pyannote graceful-degradation path in `voice.py` — unchanged.

**Invariants NOT touched:**
- GROQ_API_KEY validation (deliberately not required; Groq path dormant).
- TAVILY_API_KEY validation (deliberately not required; Session 79 graceful degradation already ships).
- HF_TOKEN refuse-to-start (D2 below: locked at banner-not-refuse).

---

### D2 — HF_TOKEN disposition: refuse-to-start vs early-banner vs status-quo

**Question:** What happens when `HF_TOKEN` is empty / missing?

**Three options:**

| Option | Pro | Con |
|---|---|---|
| **A. Refuse to start** | Strictest correctness; operator can't accidentally run with degraded diarization | Breaks single-user / single-speaker workflows that never need pyannote; hostile UX for the common case |
| **B. Early banner + runtime fallback** (LOCKED) | Operator sees the missing-token surface at boot (early diagnostic) AND single-speaker workflows continue working | One extra log line at every boot for users without HF_TOKEN |
| **C. Status quo (only at first diarize)** | Zero new code | Operator doesn't know about the fallback until ~10s into the first multi-person scene |

**Recommendation locked: Option B (early-banner + runtime fallback).**

Why:
1. **Single-user workflows MUST work without HF_TOKEN.** Jagan-only sessions don't need diarization; refusing to start would break the dev workflow + the common case.
2. **Multi-speaker scenarios degrade meaningfully but acceptably.** ECAPA-valley backend returns sensible 2-speaker results; quality loss is real but bounded.
3. **Early banner closes the observability gap.** Operator who SHOULD have HF_TOKEN set (because they care about 3+ speaker diarization) sees the missing-token surface BEFORE the first multi-person canary. Catches misconfiguration at boot, not at "why does my 3-speaker scene split badly" debug time.
4. **Refusing to start would break Jagan's current dev machine** — HF_TOKEN may not be set; pipeline must boot for the existing single-user testing workflow.

**Invariants established:**
- HF_TOKEN missing → ONE log line at boot naming the consequence + the fix path (HF model URL + env var).
- Pyannote loader's existing graceful-degradation path is UNCHANGED — only the surface-time of the diagnostic moves earlier.

**Invariants NOT touched:**
- Refuse-to-start semantics for HF_TOKEN (Option A explicitly rejected).
- Pyannote loader's lazy-init logic (still runs at first diarize call regardless of boot-time banner).

---

### D3 — Test surface

**Locked test list (Plan v1 will refine; Phase 0 forecasts):**

**D1 tests:**
1. `test_validate_env_raises_on_empty_together_api_key` — monkeypatch `config.TOGETHER_API_KEY` to `""`, call `validate_required_env()`, assert `RuntimeError` with body naming `TOGETHER_API_KEY` + fix instructions for both POSIX and PowerShell.
2. `test_validate_env_accepts_non_empty_together_api_key` — monkeypatch to a non-empty string, assert no raise.
3. `test_validate_env_reads_from_config_not_os_getenv` — AST source-inspection of `core/env_validation.py::_validate_together_api_key`; assert it references `config.TOGETHER_API_KEY` AND does NOT call `os.getenv("TOGETHER_API_KEY")` directly (P0.S6 invariant compliance).
4. `test_pipeline_run_calls_validate_env_after_dashboard_token` — AST source-inspection of `pipeline.py::run`; assert `validate_required_env()` call appears AFTER `_ensure_dashboard_token(FACES_DIR)` AND BEFORE the privilege-table assertion (ordering invariant per D1 rationale).

**D2 tests:**
5. `test_surface_hf_token_banner_when_missing` — monkeypatch `os.environ` to remove HF_TOKEN, call `_surface_hf_token_banner()`, capture stdout, assert banner present + names "HF_TOKEN" + "ECAPA-valley fallback" + HF model URL.
6. `test_surface_hf_token_banner_silent_when_set` — monkeypatch to set HF_TOKEN to a dummy value, call `_surface_hf_token_banner()`, capture stdout, assert NO output (silent on the happy path).
7. `test_validate_env_calls_hf_token_banner_after_together_check` — AST source-inspection of `validate_required_env`; assert `_surface_hf_token_banner()` call appears AFTER `_validate_together_api_key()` (required-first, optional-second ordering).

**P0.S6 invariant interaction:**
8. `test_env_validation_module_in_allowlist` — verify `tests/test_secrets_invariants.py::_ENV_VAR_ACCESS_ALLOWLIST` has the new entry for `core/env_validation.py` HF_TOKEN read (defensive: catches future allowlist removal).

**Forecast:** **8 tests** across the 2 D-decisions. Plan v1 will lock exact count.

---

## 3. Pre-mortem — failure modes

Per strict-mode discipline §1. Enumerated 7 failure modes (above the 5-10 floor).

### §3.1 — Validation raises but dashboard auth URL never generated

**Failure:** P0.S3's `validate_required_env()` raises on empty TOGETHER_API_KEY. User has never run pipeline before; `.dashboard_token` doesn't exist yet; the raise kills pipeline before token generation runs. User sets the env var, restarts — but they have no idea what auth URL they need to click.

**Mitigation:** D1 ORDERING — `_ensure_dashboard_token(FACES_DIR)` runs BEFORE `validate_required_env()`. Even if env validation raises, the dashboard token + auth URL files are already on disk. User fixes env, restarts, pipeline boots cleanly, dashboard auth works.

**Test:** D3 test 4 enforces this ordering structurally.

### §3.2 — User has a typo-key (non-empty but invalid)

**Failure:** `TOGETHER_API_KEY="invalid-typo"` is non-empty. Validation passes. Pipeline boots. Every API call 401s at runtime. Pipeline keeps running with no brain. Same silent-runtime-failure problem the spec is meant to fix.

**Mitigation:** Out of scope for P0.S3. Real-time API-key validation would require a startup ping to Together.ai (~500ms latency, additional dependency on cloud reachability at boot). Banking as known-limitation in Plan v1.

**Forward-tracked S3.X follow-up:** Optional `--validate-keys-live` flag that does a 5s ping to Together.ai at boot. Trigger condition: if typo-key class becomes a real support issue in production.

### §3.3 — User sets TOGETHER_API_KEY with leading/trailing whitespace

**Failure:** `TOGETHER_API_KEY=" abc "` (env var with whitespace). `config.py` does `os.getenv("TOGETHER_API_KEY", "")` which preserves the whitespace. Validation passes (non-empty). Together.ai 401s on the whitespace-padded key.

**Mitigation:** Document in Plan v1 known-limitations. Trim is debatable — some keys legitimately contain leading/trailing characters (unlikely but theoretical). Banking accepted-with-rationale.

### §3.4 — HF_TOKEN banner spams every boot for legitimate single-user workflows

**Failure:** Jagan (single-user workflow) doesn't set HF_TOKEN. Every pipeline boot prints the banner. After 100 boots, banner is noise.

**Mitigation:** Single log line per boot (not repeated). Banner explains the trade-off succinctly (1 line). Acceptable noise level — same shape as other boot diagnostics like `[Cloud] cloud check passed` etc.

If banner becomes objectionable, can be gated behind a config flag in S3.X. Not pre-emptively gated.

### §3.5 — P0.S6 invariant fires on new `os.getenv` call

**Failure:** `_surface_hf_token_banner()` calls `os.getenv("HF_TOKEN")` directly. `test_env_var_reads_centralized` AST scan flags it as an unallowlisted env-read. CI fails.

**Mitigation:** D3 test 8 — add `core/env_validation.py` HF_TOKEN read to `_ENV_VAR_ACCESS_ALLOWLIST` with documented rationale. Same shape as existing allowlist entries.

### §3.6 — Validation order breaks future addition of cloud-state startup probe

**Failure:** Future spec adds a "ping Together.ai at startup to confirm cloud is reachable" check. This needs TOGETHER_API_KEY to be non-empty AND the cloud ping to succeed. If the ping runs BEFORE validation, it hits a misleading network error instead of the actionable "key is empty" message.

**Mitigation:** Ordering convention locked: `validate_required_env()` runs FIRST (before any cloud probe). Future specs adding cloud probes add them AFTER env validation.

### §3.7 — User has multiple Together.ai accounts; env var points to wrong one

**Failure:** User has personal + work TOGETHER_API_KEY. Pipeline reads the work key, hits the work account's rate limits.

**Mitigation:** Out of scope for P0.S3. Account-selection UX is a different problem. Banking as known-limitation.

---

## 4. Multi-direction invariant trace

### Forward (downstream consumers)

- **`pipeline.py::run()`** — gains one validate_required_env() call after dashboard token gen. No other consumer needs to change.
- **Future S3.X follow-ups** (typo-key live validation, account selection) — extend `_validate_together_api_key()` with more rigor; surface stays the same.

### Backward (upstream producers)

- **`core/config.py:307`** — single env-read site. P0.S3 doesn't add a new read; it consumes the already-resolved value.
- **`tests/test_secrets_invariants.py:_ENV_VAR_ACCESS_ALLOWLIST`** — gains one new entry for the HF_TOKEN read in env_validation.py.

### Sideways (parallel code paths)

- **`core/voice.py:302`** HF_TOKEN read — runs at first diarize call (lazy). P0.S3's HF_TOKEN read at boot is the OTHER reader of the same env var. Both reads observe the same value (env vars are immutable during a process lifetime). No race.

### Lifecycle

- **T=0:** `core/config.py` module load reads `TOGETHER_API_KEY` once.
- **T=1:** `pipeline.run()` calls `_ensure_dashboard_token` (P0.S2).
- **T=2:** P0.S3 — `validate_required_env()` checks `config.TOGETHER_API_KEY` (raise if empty); checks `os.getenv("HF_TOKEN")` (log banner if empty).
- **T=3:** Pipeline continues to model loading, etc.
- **T=10+:** First multi-speaker scene → `_load_pyannote_pipeline()` re-reads `os.getenv("HF_TOKEN")`. Sees the same value as boot-time. Falls back to ECAPA-valley if missing (existing behavior).

All 4 axes traced. No gaps.

---

## 5. 11-gate quality checklist

| Gate | Status | Notes |
|---|---|---|
| Correctness — 4-axis trace | ✓ APPLIES | §4 above |
| Security — attack surface | ✓ APPLIES | No new attack surface. Validation runs in-process; error messages don't leak the env-var value (don't echo what the user set, only that it's empty). |
| Privacy — tier classification | ✓ APPLIES | Env vars are system_only-tier secrets. NEVER logged. Error message names the var BY NAME but not value. |
| Performance — hot-path cost | ✓ APPLIES | Boot-time only; one string-check + one os.getenv call. <1μs. |
| Observability — log per D-decision | ✓ APPLIES | D1: RuntimeError message (actionable, names POSIX + PowerShell fix). D2: one banner line on HF_TOKEN missing. |
| Test pyramid | ✓ APPLIES | §2.D3 — 8 tests across unit-behavioral + AST source-inspection. |
| Regression guards | ✓ APPLIES | D1 test 1 IS the motivating-failure regression guard ("empty key → silent runtime failure"). |
| Pre-mortem | ✓ APPLIES | §3 — 7 failure modes; 4 mitigated + 3 banked accepted-with-rationale. |
| Multi-direction trace | ✓ APPLIES | §4. |
| Backward compat | ✓ APPLIES | Existing dev machines with valid TOGETHER_API_KEY: zero behavior change. Machines without it: previously degraded silently; now refuse-to-start with actionable message. **This IS a behavior change for misconfigured environments — surfacing the failure earlier is the intent.** No migration path needed (the misconfiguration was already broken; pipeline just lied about it). |
| Doc updates | ✓ APPLIES | CLAUDE.md Session entry + complete-plan.md P0.S3 status flip + to_be_checked.md entry at closure. |

All 11 gates APPLY — no N/A.

---

## 6. Deferred-canary `to_be_checked.md` plan

Per the deferred-canary strategy locked 2026-05-20: no live canary fires for P0.S3. At closure, an entry is added to `c:\Users\jagan\dog-ai\to_be_checked.md` covering:

- **PASS signals:** boot with empty TOGETHER_API_KEY → process exits with actionable RuntimeError; boot with valid key + missing HF_TOKEN → one banner line + pipeline continues; boot with both keys set → no env-validation output at all.
- **FAIL signals:** silent boot with empty TOGETHER_API_KEY (validation didn't run); HF_TOKEN banner appears on EVERY scene transition (not just at boot); RuntimeError message lacks POSIX or PowerShell fix instructions.
- **Test scenario:** 4-step sequence covering empty + valid + missing-HF + both-missing.
- **Cross-spec composition:** Composes with P0.S2 (dashboard token generated before env validation runs).

Plan v2 will lock the entry verbatim per the discipline.

---

## 7. Auditor-Q5 trigger watch

Per memory file `feedback_auditor_q5_estimates_trail_grep.md`: **P0.S3 is the trigger-watch cycle for Q5-B re-baseline.**

- **Auditor pre-spec estimate (not yet provided):** Phase 0 forecasts 8 tests.
- **Trigger condition:** if P0.S3 lands HIGH-BY-≥30% non-DiD from auditor upper bound → discipline RENAMES from `Auditor-Q5-estimates-trail-grep` to `Auditor-Q5-systematic-under-estimate`.
- **Current trajectory:** 0% → 20% → 7% → 18% (P0.S2 closure). Upward but bounded.

**Architect-side calibration:** scope is genuinely small. Auditor's estimate range likely 6-10. If actual lands at 8-10, on-target. If Plan v2 adds defense-in-depth, those are exempt. Cycle is well-positioned to keep trajectory under 30%.

## 8. `### Phase-0-granular-decomposition-enables-accurate-estimates` pre-drafting

Per auditor's P0.S2 closure-audit guidance: at the next on-target instance (the 5th supporting instance), the doctrine elevates. P0.S3 IS the 5th supporting candidate (decomposed Phase 0 with named edit sites: `core/env_validation.py` NEW + `pipeline.py::run()` modification + `tests/test_secrets_invariants.py:_ENV_VAR_ACCESS_ALLOWLIST` addition).

**Verbatim doctrine text pre-drafted for Plan v2 §X (to be applied at closure if P0.S3 lands ON-TARGET):**

> ### Phase-0-granular-decomposition-enables-accurate-estimates
>
> Phase 0 audits that decompose the spec into concrete D-decisions with
> named edit sites (`core/X.py:LINE`) produce auditor Q5 estimates that
> land ON-TARGET (within tolerance). Phase 0 audits that aggregate into
> high-level surface counts ("7 helpers," "3 components") produce
> estimates that drift wildly in either direction.
>
> **Track record (5 supporting instances + 3 contrary instances):**
>
> Supporting (decomposed → ON-TARGET):
> - P0.S7.5 — 5 D-decisions × named edit sites → ON-TARGET (mid-range)
> - P0.S7.5.1 — 1 D-decision × named edit site → ON-TARGET (+ Plan v2 defense-in-depth +1)
> - P0.S7.5.2 — 5 D-decisions × named edit sites (multi-subsystem) → ON-TARGET (+ parametrize fan-out)
> - P0.S2 — 7 D-decisions × named edit sites (cross-language) → ON-TARGET (non-DiD 18% within tolerance)
> - **P0.S3 — [5th supporting instance, locked at closure if on-target]**
>
> Contrary (aggregated → DRIFT):
> - D-B — "8 surfaces" → HIGH 40%
> - D-D — "7 helpers" → LOW 4×
> - D-E — "single targeted helper" → LOW 60%
>
> **Discipline-stability evidence:** the granularity correlation holds
> across 4 scales (mini-spec ~3h, single-D-decision specs ~5h, 5-D-decision
> specs ~9h, 7-D-decision multi-language specs ~12h) AND across multiple
> subsystem counts (1, 5, 7). The correlation is independent of spec size
> and subsystem fan-out.
>
> **Operational rules:**
> 1. Phase 0 audits MUST decompose into explicit D-decisions with named
>    edit sites at `core/X.py:LINE` granularity.
> 2. Aggregate framings ("7 helpers," "3 components") are rejected at
>    Phase 0 review — re-decompose before locking the audit.
> 3. The improvement is incidental — the primary benefit of granular
>    Phase 0 is for the developer reading the spec; downstream estimate
>    accuracy is a side effect that nonetheless surfaces as a useful
>    forecast signal.
>
> **Future accumulation:** continue tracking. The doctrine matures
> rather than re-elevating at higher thresholds. The contrary instances
> (D-B / D-D / D-E) stay banked as falsification-resistance evidence —
> if a future decomposed-Phase-0 instance drifts ≥30%, it FALSIFIES the
> correlation and the doctrine demotes back to architect-memory.

This text is LOCKED for Plan v2 §X (closure-elevation hook). If P0.S3 closes ON-TARGET, the doctrine elevates verbatim. If P0.S3 misses, the pre-draft stays as architect-memory only.

---

## 9. Strict-mode operational test (Phase 0)

- [x] Pre-mortem section exists (§3 — 7 failure modes)
- [x] Multi-direction invariant trace exists (§4 — 4 axes)
- [x] Quality-gate checklist named (§5 — 11/11 APPLIES)
- [x] Cross-spec impact analysis exists (§1)
- [x] Closure-audit step scheduled (implicit — discipline floor)

All 5 strict-mode tests pass at Phase 0. **10th consecutive application** banked.

---

## 10. Discipline counts at Phase 0 close

- **Spec-first review cycle:** 19-for-19 → **20-for-20** at Phase 0 land
- **Sub-pattern A (`Phase-0-catches-wrong-premise`):** stays at **5** (no wrong-premise; P0.S3 was ON-TARGET premise with 5 refinements)
- **Strict-industry-standard mode:** **10th consecutive application**
- **Deferred-canary strategy:** in-flight (3rd application at closure)
- **Auditor-Q5:** 7 banked closures + 1 in-flight (P0.S3 — trigger-watch)
- **Phase 0 granular-decomposition (informal):** 4 supporting → **5 supporting candidate** (locks at closure if on-target)

---

## 11. Plan v1 forecast

Plan v1 will lock:
- Exact `RuntimeError` message text (POSIX + PowerShell fix instructions verbatim)
- HF_TOKEN banner exact wording (1 line vs multi-line)
- `_ENV_VAR_ACCESS_ALLOWLIST` entry shape
- Test count (Phase 0 forecasts 8)
- Module placement (`core/env_validation.py` as new module vs inlined into pipeline.py — Phase 0 leans toward new module for testability + future S3.X extensibility)

Plan v1 will likely surface 2-3 architect-anticipated precision items.

---

**End of Phase 0 audit.**

Ready to share with auditor. Same sequence: this audit → auditor review → Plan v1 with refinements → auditor review → Plan v2 → joint sign-off → developer implementation → closure.
