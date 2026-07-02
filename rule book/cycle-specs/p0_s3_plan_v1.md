# P0.S3 — Required env vars not validated at startup — Plan v1

**Predecessor:** `tests/p0_s3_audit.md` (Phase 0)
**Status:** Plan v1 — auditor's 4 precision items addressed inline
**Mode:** Strict industry-standard + deferred-canary (3rd application)

Plan v1 absorbs the 4 Phase 0 precision items and locks the implementation contract. Per the locked principle ("Plan version count is governed by spec complexity, NOT by ritual" — strict-mode §8 sub-rule), Plan v2 is OPTIONAL — only fires if auditor v1 review surfaces real precision items. If auditor returns "APPROVED with 0 precision items," ship straight to developer.

---

## §1. Auditor Phase 0 precision items (4 — addressed)

### P1 — Whitespace disposition: strip at config.py module load + WARNING at env_validation

**Auditor's catch:** Phase 0 §3.3 banked whitespace as "accepted-with-rationale," calling trim "debatable." Reality: Together.ai key format is `tgp_v1_<base64>`-shape URL-safe strings; whitespace in the env var is almost certainly copy-paste artifact. The "unlikely but theoretical" risk of legitimate trailing whitespace is genuinely small; user-impact of NOT stripping is exactly the silent-runtime-401 failure mode that motivated the spec.

**Auditor lean:** Option (a) — strip at config.py module load (single source of truth).

**Locked design (refined to a 3-way: strip at config + raw exposed + env_validation WARNs):**

```python
# core/config.py:307-309 (REPLACES the existing line)

# P0.S3 — strip whitespace at module load (single source of truth).
# Empty default is preserved; .strip("") == "". Consumers (CHAT_API_KEY etc.)
# see the stripped value, so an httpx Authorization: Bearer header is never
# whitespace-padded. env_validation.py reads BOTH _RAW (for the diagnostic
# WARNING) and the stripped value (for the empty-check).
_TOGETHER_API_KEY_RAW = os.getenv("TOGETHER_API_KEY", "")
TOGETHER_API_KEY      = _TOGETHER_API_KEY_RAW.strip()
```

**Why dual-attr (RAW + stripped):**

- Consumers (`CHAT_API_KEY`, `EXTRACT_API_KEY`, etc. on lines 322/327/332/342) read `TOGETHER_API_KEY` — stripped value, used in `Authorization: Bearer` header construction. No whitespace-padded keys reach Together.ai.
- `env_validation.py::_validate_together_api_key()` reads BOTH:
  - `_TOGETHER_API_KEY_RAW` for the WHITESPACE-DETECTED diagnostic
  - `TOGETHER_API_KEY` (stripped) for the EMPTY check
- Strip is idempotent: if RAW is already clean, `stripped == raw`, no WARNING fires.

**`_validate_together_api_key()` implementation refined:**

```python
def _validate_together_api_key() -> None:
    """TOGETHER_API_KEY is HARD-required. Empty → refuse to start.

    Reads from config.TOGETHER_API_KEY (stripped) for the empty-check,
    and from config._TOGETHER_API_KEY_RAW for the whitespace-detection
    diagnostic. Both reads stay through config.* — P0.S6 invariant
    preserved.
    """
    if not config.TOGETHER_API_KEY:
        raise RuntimeError(...)

    # Whitespace diagnostic (P0.S3 Plan v1 §1.P1)
    if config._TOGETHER_API_KEY_RAW != config.TOGETHER_API_KEY:
        print(
            "[EnvCheck] WARNING: TOGETHER_API_KEY had leading/trailing "
            "whitespace; stripping for use. Set the env var without "
            "surrounding spaces to silence this WARNING.",
            flush=True,
        )
```

**Invariants preserved:**

- Empty key → `RuntimeError` (D1 motivating-failure regression guard intact)
- Stripped-by-default → no whitespace-401 silent failures (closes the §3.3 gap honestly)
- P0.S6 invariant preserved (both reads go through `config.*` attrs)

**Invariants NOT touched:**

- GROQ_API_KEY whitespace handling — out of scope (Groq path dormant)
- TAVILY_API_KEY whitespace handling — out of scope (graceful degradation already ships)
- HF_TOKEN whitespace handling — see §1.P4 below

### P2 — Exact substring assertions (test concreteness)

**Auditor's catch:** Phase 0 §2.D3 tests 1 + 5 said "body names X + Y" — too loose. If error-message text drifts (e.g., model name change), tests should catch it.

**Locked exact substrings (Plan v1):**

**Test 1 (`test_validate_env_raises_on_empty_together_api_key`):**

Assert these literal substrings appear in `RuntimeError` body (case-sensitive):
- `"TOGETHER_API_KEY"` — names the env var
- `"export TOGETHER_API_KEY"` — POSIX fix instruction
- `"$env:TOGETHER_API_KEY"` — PowerShell fix instruction

**Test 5 (`test_surface_hf_token_banner_when_missing`):**

Assert these literal substrings appear in stdout banner:
- `"HF_TOKEN"` — names the env var
- `"ECAPA-valley"` — names the fallback backend (operator can grep for this term in voice.py to understand the trade-off)
- `"huggingface.co/pyannote/speaker-diarization-3.1"` — the model URL (operator-actionable fix path; if model name drifts, test catches it)

**New test added (P0.S3 Plan v1 §1.P1 whitespace handling):**

**Test 9 — `test_validate_env_warns_on_whitespace_in_together_api_key`** — monkeypatch `config._TOGETHER_API_KEY_RAW = "  abc123  "` AND `config.TOGETHER_API_KEY = "abc123"` (the stripped form); call `validate_required_env()`; capture stdout; assert WARNING line contains `"TOGETHER_API_KEY"` + `"whitespace"` + `"stripping for use"`.

**Test 10 — `test_validate_env_silent_when_no_whitespace`** — clean key, no WARNING fires (negative regression guard).

**Updated test surface: 8 → 10 tests.** Plan v1 forecast.

### P3 — Ordering convention as inline code comment

**Auditor's catch:** Phase 0 §3.6 captured the ordering rule in the audit doc only. For the convention to survive future maintainers, it must live at the call site.

**Locked code shape (pipeline.py::run() top):**

```python
async def run():
    """Main pipeline loop."""
    global _shutdown_event, _brain_orchestrator, _yolo_frame_counter, \
           _latest_yolo_detections, _yolo_last_ran, _vision_last_heartbeat, \
           _vision_face_scan_last

    # ── P0.S2 dashboard auth token (FIRST line — before any other boot work) ──
    # [existing P0.S2 comment block stays as-is]
    from core.dashboard_token import _ensure_dashboard_token
    _ensure_dashboard_token(FACES_DIR)  # P0.S2 — must run first (token recovery path)

    # ── P0.S3 env-var validation ──────────────────────────────────────────────
    # ORDERING INVARIANT: validate_required_env() MUST run BEFORE any cloud or
    # network probe. Future specs adding network reachability checks (e.g.,
    # Together.ai ping at startup) MUST land AFTER this call so misleading
    # network errors don't mask the actionable "key is empty" message.
    #
    # ORDERING vs P0.S2: validate_required_env() runs AFTER _ensure_dashboard_token
    # so that even if env validation raises, the dashboard token + auth URL files
    # are already on disk. User fixes env, restarts, dashboard auth works.
    from core.env_validation import validate_required_env
    validate_required_env()

    # ── Privilege-table integrity check ───────────────────────────────────────
    # [existing P0.S2 privilege-table check stays]
```

**Locked comment block doubles as the doctrine anchor.** Future spec-time grep for "ORDERING INVARIANT" surfaces P0.S3's lock; future cloud-probe spec can grep for it and verify the new probe lands AFTER `validate_required_env()`.

### P4 — HF_TOKEN access path: centralize via config.py

**Auditor's catch:** Architect's design had `_surface_hf_token_banner()` calling `os.getenv("HF_TOKEN")` directly + adding a new allowlist entry. Auditor lean: option (b) centralize via config.py for consistency with TOGETHER_API_KEY pattern.

**Locked design (Plan v1 picks option (b1) per auditor's framing):**

```python
# core/config.py (NEW LINE — directly after the TOGETHER_API_KEY block)

# P0.S3 — HF_TOKEN centralized at module load for consistency with
# TOGETHER_API_KEY pattern. env_validation.py reads config.HF_TOKEN
# (not os.getenv) so the P0.S6 test_env_var_reads_centralized invariant
# stays green without adding a new allowlist entry.
#
# core/voice.py:302 still reads os.getenv("HF_TOKEN") at lazy-load time
# (per the existing P0.S6 allowlist entry); migrating voice.py to
# config.HF_TOKEN is S3.X scope, not P0.S3. Same value read twice during
# process lifetime is harmless (env vars are immutable during a Python
# process).
HF_TOKEN = os.getenv("HF_TOKEN", "")
```

**`_surface_hf_token_banner()` implementation refined:**

```python
def _surface_hf_token_banner() -> None:
    """HF_TOKEN missing → log early banner.

    Reads from config.HF_TOKEN (P0.S3 Plan v1 §1.P4 — centralized via
    config.py for consistency with TOGETHER_API_KEY pattern). No
    allowlist exception needed for env_validation.py.

    Does NOT raise — diarization fallback (ECAPA-valley) is acceptable
    for single-speaker sessions, and core/voice.py:302 still handles
    the lazy-load fallback at first diarize call.
    """
    if not config.HF_TOKEN:
        print(
            "[EnvCheck] HF_TOKEN not set — pyannote speaker-diarization-3.1 "
            "(gated HF model) cannot load. Multi-speaker scenarios will use "
            "the ECAPA-valley fallback backend (binary-split only; less "
            "accurate on 3+ speakers). For diarization-3.1, register at "
            "https://huggingface.co/pyannote/speaker-diarization-3.1 + "
            "set HF_TOKEN.",
            flush=True,
        )
```

**Allowlist impact:**

- `tests/test_secrets_invariants.py::_ENV_VAR_ACCESS_ALLOWLIST` stays AS-IS — `core/voice.py` entry for HF_TOKEN is preserved (voice.py's lazy-load read is unchanged).
- NO new allowlist entry for `core/env_validation.py` — env_validation reads `config.HF_TOKEN` (module attr), not `os.getenv` directly.

**Test surface impact:**

- D3 test 8 (`test_env_validation_module_in_allowlist`) is REMOVED — no allowlist entry to verify.
- D3 test 7 (`test_validate_env_calls_hf_token_banner_after_together_check`) keeps its source-inspection check.

**Plan v1 test surface revised: 10 → 9 tests** (test 8 deleted per P4 simplification; tests 9 + 10 added per P1).

**Architectural notes (auditor's P4 trade-off considered):**

- **Option (a) — direct read + allowlist exception:** rejected. Adds asymmetry between TOGETHER_API_KEY (centralized) and HF_TOKEN (allowlisted). Operational cost of inconsistency is small but real over multi-year codebase evolution.
- **Option (b1) — centralize at config.py, leave voice.py alone:** LOCKED. Consistency with TOGETHER_API_KEY pattern + no migration risk to voice.py's diarization path.
- **Option (b2) — centralize + migrate voice.py:** correct direction long-term but OUT OF P0.S3 SCOPE. Banking as S3.X follow-up: "migrate core/voice.py:302 HF_TOKEN read to config.HF_TOKEN" — pure refactor, zero behavior change, removes the last HF_TOKEN allowlist entry.

---

## §2. Test surface — locked counts (Plan v1)

Phase 0 forecast 8 tests. After 4 precision items: **9 tests** (test 8 removed per P4, tests 9 + 10 added per P1, net +1).

### D1 — TOGETHER_API_KEY validation (4 tests)

1. **`test_validate_env_raises_on_empty_together_api_key`** — monkeypatch `config.TOGETHER_API_KEY = ""` AND `config._TOGETHER_API_KEY_RAW = ""`; call `validate_required_env()`; assert `RuntimeError` raised; assert message body contains EXACT substrings: `"TOGETHER_API_KEY"`, `"export TOGETHER_API_KEY"`, `"$env:TOGETHER_API_KEY"`.

2. **`test_validate_env_accepts_non_empty_together_api_key`** — monkeypatch to clean non-empty values; assert no raise + no WARNING output.

3. **`test_validate_env_reads_from_config_not_os_getenv`** — AST source-inspection of `core/env_validation.py::_validate_together_api_key`; assert `config.TOGETHER_API_KEY` reference present AND no `os.getenv("TOGETHER_API_KEY"` call in the function body.

4. **`test_pipeline_run_calls_validate_env_after_dashboard_token`** — AST source-inspection of `pipeline.py::run`; assert `validate_required_env()` call appears AFTER `_ensure_dashboard_token(FACES_DIR)` AND BEFORE the privilege-table assertion.

### D2 — HF_TOKEN banner (3 tests)

5. **`test_surface_hf_token_banner_when_missing`** — monkeypatch `config.HF_TOKEN = ""`; capture stdout; assert banner contains EXACT substrings: `"HF_TOKEN"`, `"ECAPA-valley"`, `"huggingface.co/pyannote/speaker-diarization-3.1"`.

6. **`test_surface_hf_token_banner_silent_when_set`** — monkeypatch `config.HF_TOKEN = "fake-hf-token"`; capture stdout; assert NO banner output (silent on happy path).

7. **`test_validate_env_calls_hf_token_banner_after_together_check`** — AST source-inspection of `validate_required_env`; assert `_surface_hf_token_banner()` call appears AFTER `_validate_together_api_key()` (required-first, optional-second ordering preserved).

### P1 Whitespace handling (2 tests, NEW per Plan v1)

8. **`test_validate_env_warns_on_whitespace_in_together_api_key`** — monkeypatch `config._TOGETHER_API_KEY_RAW = "  abc123  "` AND `config.TOGETHER_API_KEY = "abc123"`; capture stdout; assert WARNING line contains substrings: `"TOGETHER_API_KEY"`, `"whitespace"`, `"stripping for use"`.

9. **`test_validate_env_silent_when_no_whitespace`** — monkeypatch RAW + stripped to same clean value; assert no WARNING (negative regression guard — silent on happy path).

### Removed per P4

~~Test 8: `test_env_validation_module_in_allowlist`~~ — REMOVED. No allowlist entry needed; HF_TOKEN centralized at config.py.

**Total locked count: 9 tests.** Auditor pre-spec estimate was 6-10; 9 lands at the upper end of mid-range. Well within tolerance.

**Q5-B trigger watch (per the locked rule):**
- Auditor upper bound: 10 tests
- Plan v1 lock: 9 tests
- Current overage: (9 - 10) / 10 = **−10% (UNDER the upper bound)** — NOT a HIGH-BY scenario
- Trigger DOES NOT activate. Discipline name `Auditor-Q5-estimates-trail-grep` stays.
- If closure adds any defense-in-depth tests, those are exempt per the operational definition locked at P0.S2 closure.

---

## §3. Edit-site enumeration (locked)

### Pipeline-side (Python)

| File | Change | Lines (approx) |
|---|---|---|
| `core/env_validation.py` | NEW — `_validate_together_api_key()`, `_surface_hf_token_banner()`, `validate_required_env()` | ~80 LOC new file |
| `core/config.py:307-310` | MODIFY — split TOGETHER_API_KEY into RAW + stripped; add HF_TOKEN module attr | ~3 line changes + 1 new line |
| `pipeline.py::run()` | INSERT — ordering-invariant comment block + `validate_required_env()` call after `_ensure_dashboard_token(FACES_DIR)` | ~10 lines inserted |

### Tests

| File | Change | Tests |
|---|---|---|
| `tests/test_env_validation.py` | NEW — all 9 tests (D1 ×4 + D2 ×3 + whitespace ×2) | 9 tests |

**No changes to:**
- `core/voice.py` — HF_TOKEN read at line 302 unchanged
- `tests/test_secrets_invariants.py::_ENV_VAR_ACCESS_ALLOWLIST` — no new entries
- All other 5 consumer call sites of `TOGETHER_API_KEY` (CHAT_API_KEY, EXTRACT_API_KEY, EMBED_API_KEY, VISION_API_KEY) — they read `config.TOGETHER_API_KEY` (stripped value) automatically per the dual-attr design

**Total new files: 2 (env_validation.py + test_env_validation.py). Modified: 2 (config.py + pipeline.py).**

---

## §4. Pre-mortem updated count

Phase 0 listed 7 failure modes. Plan v1 modifies one (§3.3 promoted from "accepted-with-rationale" to "stripped at config.py module load + WARNING") + adds 1 new (§3.8 below).

### §3.3 (REVISED per P1)

**Failure:** User sets `TOGETHER_API_KEY=" abc "` (whitespace-padded). Pre-Plan-v1: silent runtime 401 because the whitespace-padded key reaches httpx headers. Plan v1: stripped at config.py module load + WARNING printed by env_validation. Authentication uses clean key; user sees actionable diagnostic.

### §3.8 — Stripping equivalence collides two distinct keys (NEW)

**Failure:** User A sets `TOGETHER_API_KEY="abc "` (trailing space). User B legitimately has key `"abc"` (no space). The strip equivalence relation `"abc " ~ "abc"` would treat them as the same key when both happen to be valid. **Precision note (auditor v1 review 2026-05-20):** this is a stripping equivalence collision, NOT a prefix collision — User B's key is the exact stripped form of User A's, not a string prefix. Phrasing corrected.

**Mitigation:** Accepted-with-rationale. Together.ai's key format is `tgp_v1_<base64>` (~43 chars URL-safe alphabet, ~256-bit entropy). The probability of two legitimate keys differing only in trailing/leading whitespace is operationally zero — no two real users would have keys where one is the literal stripped form of the other. WARNING fires so the user with whitespace knows their env var had a copy-paste artifact.

**Total pre-mortem at Plan v1: 8 failure modes.** Above strict-mode floor (5-10). All mitigated or accepted-with-rationale.

---

## §5. 11-gate quality checklist (re-affirmed for Plan v1)

| Gate | Status | Notes |
|---|---|---|
| Correctness — 4-axis trace | ✓ APPLIES | Phase 0 §4 holds; no new surface |
| Security — attack surface | ✓ APPLIES | No new attack surface. RuntimeError body names the env var BY NAME but not value (no key-value leakage in error message) |
| Privacy — tier classification | ✓ APPLIES | TOGETHER_API_KEY + HF_TOKEN are system_only-tier; NEVER logged. WARNING about whitespace does NOT echo the key value (only states "whitespace detected") |
| Performance — hot-path cost | ✓ APPLIES | Boot-time only; one string-strip + one truthiness check per env var. <1μs |
| Observability — logs per D-decision | ✓ APPLIES | D1: RuntimeError on empty (refuses to start) + WARNING on whitespace (continues). D2: banner on missing HF_TOKEN (continues) |
| Test pyramid | ✓ APPLIES | §2 — 9 tests: 4 behavioral + 2 AST + 2 whitespace-WARNING + 1 negative regression |
| Regression guards | ✓ APPLIES | Test 1 IS the motivating-failure guard (empty key → silent runtime failure prevented) |
| Pre-mortem | ✓ APPLIES | §4 — 8 failure modes |
| Multi-direction trace | ✓ APPLIES | Phase 0 §4 holds; whitespace handling adds the strip-at-config writer surface but no new consumer side |
| Backward compat | ✓ APPLIES | Existing valid configs: unchanged behavior. Misconfigured envs (empty): now refuse-to-start with actionable message (intent). Whitespace-padded envs: now strip + WARN (was silent-401 before; behavior changed but improves) |
| Doc updates | ✓ APPLIES | CLAUDE.md Session entry + complete-plan.md P0.S3 status flip + to_be_checked.md entry at closure (deferred-canary 3rd application) |

All 11 gates APPLY. No N/A.

---

## §6. Deferred-canary `to_be_checked.md` entry (locked verbatim for closure paste)

```markdown
## P0.S3 — Required env vars not validated at startup (closed YYYY-MM-DD)

Surfaces shipped:
- core/env_validation.py (NEW ~80 LOC): _validate_together_api_key,
  _surface_hf_token_banner, validate_required_env
- core/config.py: TOGETHER_API_KEY split into _RAW + stripped; HF_TOKEN
  centralized
- pipeline.py::run(): ordering-invariant comment block + validate_required_env()
  call after _ensure_dashboard_token(FACES_DIR)

PASS signals (canary log should show):
- Empty TOGETHER_API_KEY (`export TOGETHER_API_KEY=""` then start pipeline)
  → process exits with non-zero + stderr contains "TOGETHER_API_KEY" +
  "export TOGETHER_API_KEY" (POSIX) + "$env:TOGETHER_API_KEY" (PowerShell)
- Whitespace-padded TOGETHER_API_KEY (`export TOGETHER_API_KEY="  abc  "`)
  → pipeline boots; stderr contains "WARNING" + "TOGETHER_API_KEY" +
  "whitespace" + "stripping for use"; pipeline reaches model loading
- Missing HF_TOKEN (`unset HF_TOKEN`) → pipeline boots; stdout banner
  contains "HF_TOKEN" + "ECAPA-valley" + "huggingface.co/pyannote/speaker-
  diarization-3.1"; multi-speaker scenes use fallback backend
- All keys set cleanly → no env-validation output; silent happy path
- Ordering: dashboard token + auth URL files exist even when env validation
  raises (P0.S2 ordering invariant preserved — verifiable by `ls faces/`
  after a deliberately-empty TOGETHER_API_KEY boot attempt)

FAIL signals (regressions; investigate):
- Empty TOGETHER_API_KEY → pipeline boots silently with broken brain
- Whitespace-padded TOGETHER_API_KEY → silent 401s in brain agents (no
  WARNING surfaced)
- RuntimeError message lacks POSIX or PowerShell fix instructions
- HF_TOKEN missing → multi-speaker session uses pyannote-fallback path
  without the boot-time banner (regression in observability)
- Future cloud-state probe added BEFORE validate_required_env() → masks
  the empty-key error with a misleading network error

Test scenario:
1. Stop pipeline. `export TOGETHER_API_KEY=""` → start pipeline → expect
   immediate RuntimeError + POSIX + PowerShell fix instructions
2. Confirm faces/.dashboard_token + faces/.dashboard_auth_url still exist
   (P0.S2 ordering invariant — dashboard auth survives env validation
   failure)
3. `export TOGETHER_API_KEY="  abc123  "` → start pipeline → expect
   WARNING about whitespace + pipeline continues to model loading
4. Set valid TOGETHER_API_KEY + `unset HF_TOKEN` → start pipeline → expect
   HF_TOKEN banner + pipeline boots successfully
5. Set both keys cleanly → start pipeline → expect NO env-validation output
6. Future-spec ordering check: when P0.R7 (state-blind Ollama fallback)
   or any cloud probe ships, verify it lands AFTER validate_required_env()
   in pipeline.py::run()

Dependencies on other specs:
- Composes with P0.S2 (dashboard token gen runs BEFORE env validation —
  recovery path preserved on env failure)
- Constrained by P0.S6 (test_env_var_reads_centralized invariant — both
  TOGETHER_API_KEY and HF_TOKEN go through config.py module attrs)

Known limitations (banked accepted-with-rationale):
- Typo-key (non-empty but invalid) — validation passes; 401 surfaces at
  first API call. Forward-tracked S3.X follow-up: optional
  `--validate-keys-live` flag with 5s Together.ai ping at boot. Trigger
  condition: if typo-key class becomes a real support issue.
- Multi-account TOGETHER_API_KEY selection — out of scope. Account-UX is
  a different problem.
- HF_TOKEN whitespace handling — NOT stripped (HF tokens are sensitive
  to format; auditor recommended P0.S3 only handle TOGETHER_API_KEY
  whitespace). If HF_TOKEN whitespace becomes a real issue, file S3.X.
- core/voice.py:302 still reads os.getenv("HF_TOKEN") at lazy-load (via
  P0.S6 allowlist entry); migrating to config.HF_TOKEN is S3.X scope.
  Same value read twice during process lifetime — harmless.
```

Auditor cross-check at closure: verify entry lands verbatim. Drift in wording = discipline failure flag.

---

## §7. Strict-mode operational test (Plan v1)

- [x] Pre-mortem section extended (§4 — 8 failure modes; was 7 at Phase 0)
- [x] Multi-direction trace held from Phase 0 §4 (no new surfaces)
- [x] Quality-gate checklist re-affirmed (§5 — 11/11 APPLIES)
- [x] Cross-spec impact analysis re-verified (Phase 0 §1 still holds)
- [x] Closure-audit scheduled (implicit — executes per discipline)

**Strict-mode 11th consecutive application.** Cross-spec generalization continues to hold.

---

## §8. `### Phase-0-granular-decomposition-enables-accurate-estimates` doctrine elevation prep

Pre-drafted verbatim doctrine text from Phase 0 §8 carries forward unchanged. If P0.S3 closes ON-TARGET (test count ≤13 = under Q5-B 30% trigger), the doctrine elevates at closure per the canonical P0.S7.5.2 §7 pattern.

Plan v1 added 1 test net (9 vs Phase 0 forecast 8) per P1 whitespace handling. Q5-B trigger math at Plan v1 lock:
- Auditor upper bound: 10
- Plan v1 actual: 9
- Overage: (9 - 10) / 10 = **−10%** (UNDER upper bound)
- Trigger DOES NOT activate

If closure actual = Plan v1 lock (9 tests) → ON-TARGET → doctrine elevates verbatim per Phase 0 §8.

If closure adds defense-in-depth tests beyond Plan v1 (Plan v2 in flight, or developer-added per `### Developer-improves-on-spec`) → those tests are exempt from Q5-B trigger math per operational definition locked at P0.S2 closure.

---

## §9. Discipline counts at Plan v1 close

- **Spec-first review cycle:** 20-for-20 → **21-for-21** at Plan v1 land
- **Sub-pattern A (`Phase-0-catches-wrong-premise`):** stays at **5** (no wrong-premise at Plan v1; precision items resolved cleanly)
- **Strict-industry-standard mode:** **11th consecutive application**
- **Deferred-canary strategy:** 3rd application in flight
- **Auditor-Q5:** 7 banked + 1 in-flight (Plan v1 lock −10% UNDER upper bound, trigger does NOT activate at lock; closure result locks the band)
- **Auditor-precision-item-misframe (auditor-side):** stays at **2** (no misframe at Phase 0 → Plan v1 transition)
- **Phase 0 granular-decomposition (informal):** 4 supporting → **5 supporting candidate** (locks at closure if ON-TARGET per §8 pre-draft)

---

## §10. Plan v2 contingency

Per the strict-mode §8 sub-rule locked 2026-05-20: **Plan v2 is OPTIONAL.** Only fires if auditor's Plan v1 review surfaces real precision items.

**Architect-side prediction:** Plan v1 absorbs all 4 Phase 0 precision items cleanly. Quality-gate checklist is full APPLIES with no borderline items. Test surface is auditor-spec-bounded (mid-range). Cross-spec interactions are well-traced. **Expectation: auditor v1 verdict = "APPROVED with 0 precision items" → skip to developer.**

**If auditor surfaces real items at v1:** draft Plan v2 absorbing them. Continue iterating until 0 items returned. Per the locked discipline.

**If auditor surfaces NO items at v1:** ship straight to developer with Phase 0 + Plan v1 as the implementation contract. Estimated developer effort: ~3-4 hours.

---

## §11. Developer handoff (conditional on auditor v1 verdict)

If auditor returns "APPROVED 0 precision items":

Developer reads:
- `tests/p0_s3_audit.md` — Phase 0 audit (D-decision rationale + multi-direction trace)
- `tests/p0_s3_plan_v1.md` — Plan v1 (THIS file; locked implementation contract + 4 precision items addressed)

### Implementation order (~3-4 hours)

**Phase 1 — config.py refactor (~30 min):**
- `core/config.py:307-309` — split TOGETHER_API_KEY into RAW + stripped; add HF_TOKEN
- Verify CHAT_API_KEY / EXTRACT_API_KEY / EMBED_API_KEY / VISION_API_KEY consumers automatically see the stripped value (no consumer changes needed)

**Phase 2 — env_validation.py module (~1 hour):**
- `core/env_validation.py` NEW (~80 LOC):
  - `_validate_together_api_key()` with RAW vs stripped diagnostic
  - `_surface_hf_token_banner()` reading config.HF_TOKEN
  - `validate_required_env()` entry point (required-first, optional-second ordering)

**Phase 3 — pipeline.py wiring (~15 min):**
- `pipeline.py::run()` — insert ordering-invariant comment block + `validate_required_env()` call AFTER `_ensure_dashboard_token(FACES_DIR)` AND BEFORE the privilege-table check

**Phase 4 — tests (~1-1.5 hours):**
- `tests/test_env_validation.py` NEW — 9 tests per §2
- Full suite green check; verify no regression in P0.S6 invariants (test_env_var_reads_centralized must stay green)

**Phase 5 — closure (~30 min):**
- CLAUDE.md Session entry
- complete-plan.md parent-path status flip `[OPEN]` `[VERIFY]` → `[CLOSED]` (closed YYYY-MM-DD) + closure-note block per the twin-filename pitfall checklist (strict-mode §9 sub-observation)
- complete-plan.md subdir closure narrative
- `to_be_checked.md` paste verbatim per §6
- Memory file: bank Q5 closure result + Phase 0 granular-decomposition doctrine elevation result

**Total estimated effort:** ~3-4 hours of focused work.

---

**End of Plan v1.**

Ready to share with auditor for v1 review. Per the locked strict-mode §8 sub-rule:
- If auditor returns "APPROVED 0 precision items" → ship to developer with this Plan v1 as the contract.
- If auditor surfaces real items → Plan v2 absorbs them, iterate until clean.

Either path preserves the industry-standard quality floor.
