# P0.R4 — Process supervisor (systemd unit + supervisord config + auto-restart + journald/log integration) — Plan v2

**Status:** Plan v2 drafted 2026-05-23 absorbing PI #1 from P0.R4 Plan v1 verdict (D4 env template incompleteness — `Plan-v1-Pass-2-grep-undercount` 6th instance). APPROVED-AT-AUDITOR-REVIEW pending.

**Parent artifacts:**
- Phase 0 audit: `tests/p0_r4_process_supervisor_audit.md` (APPROVED with 0 BLOCKING PIs)
- Plan v1: `tests/p0_r4_process_supervisor_plan_v1.md` (1 PI surfaced — D4 env template incomplete)

---

## §1 — Plan v1 verdict reconciliation

**§1.1 PI #1 absorbed per Option (b) — programmatic A8 enforcement (auditor's lean):**

Plan v1 §2.4 D4 spec contract stated "all env vars that `core/config.py` reads via `os.getenv(...)` are documented" but the implementation template listed only TOGETHER_API_KEY + HF_TOKEN. Auditor's independent re-grep of `core/config.py` surfaced 4 secret-class env vars; 2 missing:

| Env var | `core/config.py:line` | In v1 template? | In v2 template? |
|---|---|---|---|
| TOGETHER_API_KEY | 313 | ✓ Yes (required) | ✓ Yes (required) |
| HF_TOKEN | 324 | ✓ Yes (optional) | ✓ Yes (optional) |
| **GROQ_API_KEY** | **325** | **✗ Missing** | **✓ Yes (optional) — NEW per Plan v2 §2.4** |
| **TAVILY_API_KEY** | **368** | **✗ Missing** | **✓ Yes (load-bearing for `search_web` tool — Session 30 lineage) — NEW per Plan v2 §2.4** |

**Architect adjudication: Option (b) ADOPTED per auditor lean.** A8 anchor REPLACED with programmatic enforcement that regex-extracts every `os.getenv(...)` key from `core/config.py` + asserts each appears in the template. Future env vars automatically caught without requiring template re-spec. Matches `### Induction-surfaces-invariant-gaps` discipline — structural invariants beat hardcoded enumerations.

**Banking events at this Plan v1 verdict (locked):**
- `Plan-v1-Pass-2-grep-undercount` 5 → 6 instances (NEW contract-vs-implementation MECHANISM-AXIS sub-shape vs prior 5 edit-surface enumeration sub-shapes)
- `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` parent rule RATIFIED FOR ###-DOCTRINE ELEVATION (5 applications: 4 clean + 1 caught-real-gap; 4-criteria adjudication passed; doctrine library 6 → 7 at next CLAUDE.md edit cycle)
- `### Zero-precision-items-at-auditor-review` doctrine does NOT fire at P0.R4 Plan v1 surface (stays at 15; only fires at Plan v2 if v2 clears clean per Plan-vN enumeration rule)
- `Zero-precision-items-pre-closure-predictions-blocked` counter 0 → 1 (P0.R4 Plan v1 = 1st blocked-by-PI in new accumulation; pattern-broken streak from P0.R2 onward interrupted at 4 cycles)

**§1.2 §5 paste-template + §7 doctrine projection corrections (per auditor's standing observations):**

- §5 closure-narrative paste-template (from Plan v1) projected "16th instance of doctrine firing at Plan v1 review" + "pattern-broken streak extends from 4 → 5 cycles" — both based on clean-Plan-v1 prediction. **Corrected at Plan v2 §5**: doctrine fires only at Phase 0 (15th) + Plan v2 if clean (16th); pattern-broken streak interrupted at 4 cycles + new counter starts at 1.
- §7 doctrine bump projection table line "Formal Pass-2 grep rule validations 4 → 5" — the 5th application caught a real gap, which IS the rule working as designed but doesn't count as a "clean validation". **Corrected at Plan v2 §7**: elevation candidacy was activated at Phase 0 (4 validations); ELEVATION RATIFIED at this Plan v1 verdict per 4-criteria adjudication; doctrine library 6 → 7 at next CLAUDE.md edit cycle.

**§1.3 Diligent Pass-2 grep re-enumeration at Plan v2 drafting (per now-elevated `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` doctrine):**

Files affected by P0.R4 implementation (NO change from Plan v1 §1.2; all 5 NEW files preserved):

| Path | Edit type | D-decision |
|---|---|---|
| `deploy/systemd/dog-ai.service` | NEW file | D1 |
| `deploy/supervisord/dog-ai.conf` | NEW file | D2 |
| `deploy/README.md` | NEW file | D3 |
| `deploy/dog-ai.env.example` | NEW file (EXPANDED per Plan v2) | D4 |
| `tests/test_p0_r4_process_supervisor.py` | NEW file (A8 anchor PROGRAMMATIC per Plan v2) | D5 |

Auditor verification target: `os.getenv(...)` keys in `core/config.py` (4 matches at lines 313, 324, 325, 368) + each appears in `deploy/dog-ai.env.example` per Plan v2 §2.4 expansion + A8 programmatic enforcement asserts the contract.

---

## §2 — D-decision contracts (LOCKED; D1+D2+D3+D5 UNCHANGED from Plan v1; D4 EXPANDED per Plan v2 §1.1)

### §2.1 D1 — systemd unit file (UNCHANGED from Plan v1 §2.1)

LOCKED spec unchanged. See Plan v1 §2.1.

### §2.2 D2 — supervisord config (UNCHANGED from Plan v1 §2.2)

LOCKED spec unchanged. See Plan v1 §2.2.

### §2.3 D3 — Installation README (UNCHANGED from Plan v1 §2.3)

LOCKED content shape unchanged. See Plan v1 §2.3.

**Minor note**: D3 README §3 "env file template usage" should document ALL 4 secret-class env vars + their runtime impact (TOGETHER_API_KEY required; HF_TOKEN optional for pyannote; GROQ_API_KEY optional for alternate LLM; TAVILY_API_KEY load-bearing for `search_web` tool functionality).

### §2.4 D4 — Env file template (EXPANDED per Plan v2 §1.1 absorption)

**LOCKED spec (Plan v2):**

```bash
# dog-ai cognitive runtime — environment variables
#
# Copy this file to /etc/dog-ai/dog-ai.env (chmod 0600, owned by dog-ai user)
# OR set as supervisord environment via shell export
#
# All keys correspond to os.getenv(...) calls in core/config.py.
# Programmatic enforcement at tests/test_p0_r4_process_supervisor.py::A8.
#
# === Required ===
TOGETHER_API_KEY=
#
# === Optional ===
#
# pyannote diarization-3.1 — accept HuggingFace license first:
HF_TOKEN=
#
# Alternate LLM provider (used if configured; falls back to TOGETHER_API_KEY otherwise):
GROQ_API_KEY=
#
# Web search tool — load-bearing for search_web functionality (Session 30 lineage).
# Without this, the `search_web` LLM tool returns auth-failure at runtime:
TAVILY_API_KEY=
#
# === Optional overrides (defaults documented in core/config.py) ===
# DASHBOARD_BIND=127.0.0.1
# DASHBOARD_BIND_ALLOW_ANY=
```

**Contract (Plan v2 LOCKED):**
- All 4 secret-class env vars from `core/config.py` documented with EMPTY values (operator fills in)
- P0.S6 compliance per A9 regex enforcement (`r"^(TOGETHER_API_KEY|HF_TOKEN|GROQ_API_KEY|TAVILY_API_KEY)=\s*$"` — extended secret-class list)
- A8 programmatic enforcement guarantees template stays in sync with `core/config.py` as future env vars are added
- Inline comments document each var's runtime impact for operator clarity

### §2.5 D5 — Test surface (A8 anchor REPLACED per Plan v2 §1.1 absorption)

**LOCKED contract (Plan v2):**
- 9 logical anchors preserved (Q5 LOCK at exact mid 9 inclusive ±15% from Plan v1)
- A8 anchor REPLACED: programmatic enforcement (NOT hardcoded enumeration)
- A9 anchor expanded: regex covers all 4 secret-class env vars

**A8 (Plan v2 LOCKED) — Programmatic enforcement spec:**

```python
def test_p0_r4_d4_anchor_1_env_template_documents_all_config_env_vars():
    """A8 (Plan v2) — programmatic enforcement: every os.getenv(...) key in
    core/config.py MUST appear in deploy/dog-ai.env.example.
    
    Replaces Plan v1's hardcoded TOGETHER_API_KEY + HF_TOKEN check with
    programmatic extraction. Future env vars automatically caught.
    
    Per `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` doctrine
    (elevated at P0.R4 Plan v1 verdict 2026-05-23) — child enforcement at
    test surface backs the architect-side Pass-2 grep discipline.
    """
    import re
    import inspect
    from pathlib import Path
    import core.config as cfg
    
    config_source = inspect.getsource(cfg)
    # Extract os.getenv("KEY", ...) keys — case-insensitive A-Z + 0-9 + _
    env_keys = set(re.findall(
        r'''os\.getenv\(["']([A-Z_][A-Z0-9_]*)["']''',
        config_source,
    ))
    
    template_path = Path(__file__).parent.parent / "deploy" / "dog-ai.env.example"
    assert template_path.exists(), f"D4 env template missing at {template_path}"
    template_content = template_path.read_text()
    
    missing = set()
    for key in env_keys:
        # Accept either uncommented (`KEY=`) or commented (`# KEY=...`) form
        if not re.search(rf'^(?:#\s*)?{re.escape(key)}=', template_content, re.MULTILINE):
            missing.add(key)
    
    assert not missing, (
        f"D4 env template at {template_path} is missing keys from core/config.py: "
        f"{sorted(missing)}. Per Plan v2 §2.4 contract, every os.getenv(...) key "
        f"in core/config.py must appear in the template (either as uncommented "
        f"required entry or commented optional override). Current config.py keys: "
        f"{sorted(env_keys)}."
    )
```

**A9 (Plan v2 LOCKED) — P0.S6 empty-value enforcement (expanded secret-class list):**

```python
def test_p0_r4_d4_anchor_2_env_template_values_are_empty_per_p0s6():
    """A9 (Plan v2) — P0.S6 compliance: secret-class env vars in
    deploy/dog-ai.env.example MUST have EMPTY values (no leaked secrets).
    
    Expanded from Plan v1 to cover all 4 secret-class keys from core/config.py:
    TOGETHER_API_KEY + HF_TOKEN + GROQ_API_KEY + TAVILY_API_KEY.
    """
    import re
    from pathlib import Path
    
    # Secret-class allowlist (extended at Plan v2 absorption; future cycles
    # update this set when new secret-class env vars are added to core/config.py)
    _SECRET_CLASS_ENV_VARS = frozenset({
        "TOGETHER_API_KEY",
        "HF_TOKEN",
        "GROQ_API_KEY",
        "TAVILY_API_KEY",
    })
    
    template_path = Path(__file__).parent.parent / "deploy" / "dog-ai.env.example"
    template_content = template_path.read_text()
    
    violations = {}
    for key in _SECRET_CLASS_ENV_VARS:
        # Look for KEY=value (uncommented; non-empty value = violation)
        match = re.search(
            rf'^{re.escape(key)}=(.+)$',
            template_content,
            re.MULTILINE,
        )
        if match and match.group(1).strip():
            violations[key] = match.group(1).strip()
    
    assert not violations, (
        f"D4 env template at {template_path} has non-empty values for "
        f"secret-class env vars (P0.S6 compliance violation): {violations}. "
        f"All secret-class keys ({sorted(_SECRET_CLASS_ENV_VARS)}) must have "
        f"EMPTY values in the template; operator fills in actual values when "
        f"deploying. Per P0.S6 discipline + Plan v2 §2.4 contract."
    )
```

### §2.6 Deliberate-regression protocol (UPDATED for Plan v2 A8 + A9 changes)

| Revert | Removed contract | Expected fire |
|---|---|---|
| **(a)** Drop `Restart=on-failure` from systemd `[Service]` section | D1 restart directive gone | A3 source-inspection fires |
| **(b)** Replace `EnvironmentFile=` with inline `Environment="TOGETHER_API_KEY=sk-..."` | D1 P0.S6 compliance violated | A4 source-inspection fires |
| **(c)** Drop `autorestart=true` from supervisord `[program:dog-ai]` | D2 native exponential backoff gone | A6 source-inspection fires |
| **(d)** Drop `supervisorctl` references from D3 README | D3 supervisord install section gone | A7 source-inspection fires |
| **(e)** Drop `TAVILY_API_KEY=` line from D4 template | D4 enumeration drift (PI #1 regression) | **A8 programmatic enforcement fires** (asserts TAVILY_API_KEY from core/config.py:368 missing from template) |
| **(f)** Add value `TOGETHER_API_KEY=sk-real-secret` to D4 env template | D4 P0.S6 compliance violated | A9 regex `r"^TOGETHER_API_KEY=\s*$"` fails to match (non-empty value) |

**Plan v2 deliberate-regression (e) is UPDATED from Plan v1's `[Install]` section revert** — the new (e) directly exercises the PI #1 fix. Reverting Plan v2's TAVILY_API_KEY addition should fire A8 programmatically + demonstrates the operational-rule extension's preventive purpose at the test surface.

---

## §3 — Anchor decomposition LOCK (UNCHANGED: 9 anchors at exact mid 9 inclusive ±15%)

| # | D | Anchor name | Type | Plan v2 status |
|---|---|---|---|---|
| A1 | D1 | `test_p0_r4_d1_anchor_1_systemd_unit_exists` | source-inspection | UNCHANGED |
| A2 | D1 | `test_p0_r4_d1_anchor_2_systemd_unit_has_required_sections` | source-inspection | UNCHANGED |
| A3 | D1 | `test_p0_r4_d1_anchor_3_systemd_restart_directives_present` | source-inspection | UNCHANGED |
| A4 | D1 | `test_p0_r4_d1_anchor_4_systemd_environment_file_reference` | source-inspection | UNCHANGED |
| A5 | D2 | `test_p0_r4_d2_anchor_1_supervisord_conf_exists` | source-inspection | UNCHANGED |
| A6 | D2 | `test_p0_r4_d2_anchor_2_supervisord_program_section_has_autorestart` | source-inspection | UNCHANGED |
| A7 | D3 | `test_p0_r4_d3_anchor_1_readme_exists_and_covers_both_supervisors` | source-inspection | UNCHANGED |
| **A8** | **D4** | **`test_p0_r4_d4_anchor_1_env_template_documents_all_config_env_vars`** | **PROGRAMMATIC (Plan v2)** | **REPLACED — regex extracts os.getenv keys from core/config.py + asserts each in template** |
| **A9** | **D4** | **`test_p0_r4_d4_anchor_2_env_template_values_are_empty_per_p0s6`** | **source-inspection (Plan v2)** | **EXPANDED — regex covers all 4 secret-class keys (was 2)** |

**Total: 9 logical anchors preserved. Mid 9 LOCK preserved per Plan v1 §3 / Phase 0 §6.**

---

## §4 — Honest-count commitment table (UNCHANGED from Plan v1 §4; inclusive ±15% per locked methodology)

See Plan v1 §4. No changes.

**`Explicit-closure-honest-count-commitment` 20 → 22** (21st MADE at Plan v1 §4 + Plan v2 §4 reaffirmation + 22nd HONORED at closure per STRICT separation). Plan v2 reaffirmation does NOT count as a separate MADE per STRICT enumeration; only the Plan v1 MADE + closure HONORED count per STRICT separation.

---

## §5 — Closure-narrative paste-template (CORRECTED per Plan v1 verdict)

(Architect's pre-draft; subject to closure-actual reconciliation + Path C grep-verify of doctrine counts.)

**P0.R4 closure note (CORRECTED for Plan v2 absorption):**

> ## P0.R4 — Process supervisor (systemd unit + supervisord config + auto-restart + journald/log integration) — D1+D2+D3+D4+D5 + 9 anchors + 6 deliberate-regression checks + Plan v2 absorption of D4 env template incompleteness + NEW `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` doctrine elevation event  [CLOSED 2026-05-23]
> 
> **Sub-PR sequence:** Phase 0 audit (APPROVED with 0 BLOCKING PIs — **15th instance of `### Zero-precision-items-at-auditor-review` at Phase 0 surface**; 4th consecutive clean review in pattern-broken streak; banks `Pre-audit-quantifier-precision-refined-by-grep` 2 → 3 instances per Q3 mechanism-generality refinement) → Plan v1 (1 PI surfaced — D4 env template incomplete vs stated contract "all os.getenv keys documented"; missing GROQ_API_KEY + TAVILY_API_KEY; **`Plan-v1-Pass-2-grep-undercount` 5 → 6 instances**; pattern-broken streak interrupted at 4 cycles + `Zero-precision-items-pre-closure-predictions-blocked` counter 0 → 1) → Plan v2 (RATIFIED with 0 PIs — D4 expanded to include all 4 secret-class env vars + A8 anchor REPLACED with programmatic enforcement; **16th instance of `### Zero-precision-items-at-auditor-review` at Plan v2 surface** if clean — extends Plan-vN enumeration rule precedent) → Phase 1-4 implementation.
> 
> **NEW CLAUDE.md DOCTRINE ELEVATED at P0.R4 Plan v1 verdict 2026-05-23**: `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` per 4-criteria adjudication (5 applications: 4 clean P0.R2-R3 + 1 caught-real-gap P0.R4 Plan v1; both modes validate the rule's preventive purpose). Doctrine library expands from 6 → 7 numbered doctrines at this closure-audit. Same elevation shape as `### Twin-filename-pitfall-prevention` + `### Phase-0-granular-decomposition-enables-accurate-estimates` + `### Grep-baseline-before-drafting` + `### Zero-precision-items-at-auditor-review` (all elevated at 5-6 instances with discipline-stability evidence).
> 
> **Cycle shape distinction**: P0.R4 is materially distinct from prior P0.R cycles — ZERO Python production code changes; deployment artifacts only. Cycle resembles P0.0 (CI scaffold landing). Test surface is structural file tests via configparser (cross-platform; runs on Windows dev + Linux CI; no systemd-analyze dependency). The PI #1 surface at Plan v1 + the formal rule elevation at this verdict validates the operational discipline ACROSS cycle shapes — code-change cycles (P0.R2/R3) + deployment-artifact cycles (P0.R4) BOTH exercise the rule effectively.
> 
> **What shipped:** 5 NEW deployment artifacts: `deploy/systemd/dog-ai.service` (D1) + `deploy/supervisord/dog-ai.conf` (D2) + `deploy/README.md` (D3) + `deploy/dog-ai.env.example` (D4 — 4 secret-class env vars per Plan v2) + `tests/test_p0_r4_process_supervisor.py` (D5 — 9 anchors with A8 PROGRAMMATIC + A9 expanded per Plan v2).
> 
> [... D-decision summaries from Plan v1 §5 preserved unchanged ...]
> 
> **Total P0.R4 LOGICAL ANCHORS: 9** (Plan v2 §3 LOCK EXACT MATCH at exact mid 9 inclusive ±15% band [7.65, 10.35]).
> 
> **Q5 closure under MID-RANGE methodology**: auditor mid 9, Plan v2 lock 9, **closure actual {{N}}** ({{0%|−11.1%|+11.1%}}; {{exact mid|ON-TARGET}}). Doctrine `### Phase-0-granular-decomposition-enables-accurate-estimates` **BUMPS 16 → 17 SUPPORTING INSTANCES**.
> 
> **Plan v2 §4 honest-count commitment HONORED — 22nd instance** (21st MADE at Plan v1 §4 + 22nd HONORED at closure).
> 
> **6/6 deliberate-regression confirmations PASSED** (a/b/c/d/e/f per §2.6 with Plan v2 (e) update — TAVILY_API_KEY revert fires A8 programmatically).
> 
> **`### Zero-precision-items-at-auditor-review` doctrine 15 → 16 instances** (Phase 0 15th + Plan v2 16th — Plan v1 surface BLOCKED by PI #1). Pattern-broken streak INTERRUPTED at 4 cycles (P0.R2 Plan v1 + P0.R3 Phase 0 + P0.R3 Plan v1 + P0.R4 Phase 0) + new counter starts at 1 (P0.R4 Plan v1 blocked). OPTIONAL-Plan-v2 path NOT TAKEN at this cycle (Plan v2 needed to absorb PI #1; 8th proof case BLOCKED; sub-rule track record stays at 7 proof cases per the doctrine's enumeration rule for OPTIONAL-Plan-v2 sub-rule — only cycles that ship WITHOUT Plan v2 count as proof cases).
> 
> **`Plan-v1-Pass-2-grep-undercount` 5 → 6 instances** (P0.R4 D4 env template contract-vs-implementation enumeration undercount; NEW MECHANISM-AXIS sub-shape).
> 
> **`Pre-audit-quantifier-precision-refined-by-grep` 2 → 3 instances** banked at Phase 0 verdict.
> 
> **NEW CLAUDE.md DOCTRINE LANDED**: `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` per 4-criteria adjudication at P0.R4 Plan v1 verdict; lands at this closure-audit. Doctrine library 6 → 7.
> 
> **Strict-mode 62 → 66 applications + 18 → 19 closures** (4-artifact cycle: Phase 0 + Plan v1 + Plan v2 + closure). **Discipline counts (4-artifact cycle)**: spec-first review cycle 72 → **76-for-76 at closure** (4 artifacts × +1). **`### Grep-baseline-before-drafting` 29 → 33 instances** (4 artifacts). **Cross-cycle-handoff transparency precedent 35 → 39 successful** (4 artifacts). **Spec-time grep-verification 39 → 43 instances** (4 artifacts; Phase 0 §1 Pass-1 + Plan v1 §1.2 Pass-2 + Plan v2 §1.3 Pass-3 + closure-narrative drafting Pass-4 baseline).
> 
> **`### Twin-filename-pitfall-prevention` 18 → 19 preventive events** honored at Phase 0 (no doctrine count bump per locked enumeration rule).
> 
> **Auditor-Q5-estimates-trail-grep 22 → 23 banked closures** at 0% ON-TARGET reading (if closure-actual = 9 exact). Trajectory: 9th consecutive 0% reading extends per `Doctrine-prediction-precision-improving-over-arc`.
> 
> **Deferred-canary strategy 21st application** — entry pasted verbatim into `c:\Users\jagan\dog-ai\to_be_checked.md`.
> 
> **Known Limitations (P0.R4 closure)**: same 5 from Plan v1 §5 + 1 NEW:
> 
> 6. **Plan v1 D4 env template incompleteness caught at auditor Plan v1 review** per `Plan-v1-Pass-2-grep-undercount` 6th instance; absorbed at Plan v2 with programmatic A8 enforcement. The caught-real-gap surface validates the formal Pass-2 grep operational-rule extension's preventive purpose + reinforces doctrine elevation candidacy ratification.
> 
> **Cumulative suite**: pending closure (+9 new pytest functions from D5 test file; ZERO Python production code changes).
> 
> **Files touched (5 NEW files; 0 modified production code):** see Plan v2 §1.3 enumeration.

**§5.1 5-surface landing checklist (UNCHANGED from Plan v1 §5.1):**

1. ✓ CLAUDE.md header — P0.R4 entry prepended above P0.R3 + NEW `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` doctrine added to Architectural Disciplines section
2. ✓ Parent complete-plan.md::P0.R4 status → [CLOSED] + closure note
3. ✓ Subdir complete-plan.md::P0.R4 full closure narrative
4. ✓ to_be_checked.md 21st deferred-canary entry
5. ✓ Architect memory files refresh + MEMORY.md index

---

## §6 — Architect's diligent Pass-2 grep re-enumeration at Plan v2 (auditor verification target per now-elevated `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` doctrine)

| Grep pattern | Expected matches | Verification |
|---|---|---|
| `os\.getenv\(["\']([A-Z_]+)["\']` in `core/config.py` | 4 matches at lines 313, 324, 325, 368 (TOGETHER_API_KEY + HF_TOKEN + GROQ_API_KEY + TAVILY_API_KEY) | A8 programmatic enforcement target |
| Each of 4 keys in `deploy/dog-ai.env.example` | 4 matches (one per key) | Plan v2 §2.4 expansion landed |
| Empty-value regex `r"^(TOGETHER_API_KEY\|HF_TOKEN\|GROQ_API_KEY\|TAVILY_API_KEY)=\s*$"` in `deploy/dog-ai.env.example` | 4 matches (all secret-class values empty) | A9 P0.S6 compliance enforcement |
| Plus Plan v1 §6 grep patterns (deploy/, *.service, supervisord*, tests/test_p0_r4*, EnvironmentFile=, autorestart=true, Restart=on-failure, useradd in README) | unchanged from Plan v1 | Plan v1 patterns preserved at Plan v2 |

**Auditor's independent re-grep target at Plan v2 verdict:** all 4 new env-var keys + Plan v1 patterns + cross-check NO inline secret-looking values in any of the 5 NEW files.

**Architect prediction (probabilistic per `Zero-precision-items-pre-closure-predictions-blocked` operational rule + formal Pass-2 grep doctrine):** Plan v2 §1.1 + §2.4 + §2.5 expansion absorbs PI #1 cleanly; expecting clean Plan v2 review per the now-elevated `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` doctrine. If clean (6th total validation: P0.R2 + P0.R3 + P0.R3 + P0.R4 Phase 0 + P0.R4 Plan v1 + P0.R4 Plan v2 — 5 clean + 1 caught-gap; doctrine's preventive purpose continues to be empirically validated in both modes).

---

## §7 — Doctrine bump projection at closure (CORRECTED per Plan v1 verdict)

| Doctrine | Pre-P0.R4 baseline | Post-P0.R4 closure (corrected) |
|---|---|---|
| `### Phase-0-granular-decomposition-enables-accurate-estimates` | 16 (post-P0.R3 closure) | 17 IF closure-actual ∈ {8, 9, 10} |
| `### Zero-precision-items-at-auditor-review` | 15 (post-P0.R4 Phase 0 — Plan v1 BLOCKED by PI; doctrine did NOT fire at Plan v1) | 16 IF Plan v2 fires clean (extends Plan-vN enumeration rule precedent) |
| `### Induction-surfaces-invariant-gaps` | 11 (post-P0.R3 closure) | 11 (stays unless in-flight detector-strengthening event) |
| `### Architect-reads-production-code-before-sign-off` | 15 (post-P0.R3 closure-audit) | 16 IF architect closure-audit fires at P0.R4 closure |
| OPTIONAL-Plan-v2 sub-rule proof cases | 7 (post-P0.R3 closure) | stays 7 — P0.R4 cycle ESCALATED to Plan v2 per PI #1; NOT a proof case |
| `Explicit-closure-honest-count-commitment` | 20 (post-P0.R3 closure) | 22 (21 MADE at Plan v1 §4 + 22 HONORED at closure) |
| Strict-mode applications | 62 (post-P0.R3 closure) | 66 (4-artifact cycle: Phase 0 + Plan v1 + Plan v2 + closure) |
| Strict-mode closures | 18 (post-P0.R3 closure) | 19 |
| Spec-first review cycle | 72 (post-P0.R3 closure) | 76 (4 artifacts × +1) |
| `### Grep-baseline-before-drafting` | 29 (post-P0.R3 closure) | 33 (4 artifacts) |
| Cross-cycle-handoff transparency | 35 (post-P0.R3 closure) | 39 (4 artifacts) |
| Spec-time grep-verification | 39 (post-P0.R3 closure) | 43 (4 artifacts) |
| `Doctrine-prediction-precision-improving-over-arc` | 8+ cycle 0% streak (post-P0.R3 closure) | 9+ cycle 0% streak ONLY IF closure-actual = 9 exact |
| `Pre-audit-quantifier-precision-refined-by-grep` | 3 (post-P0.R4 Phase 0) | stays 3 (no new instance at Plan v1 or v2) |
| `Plan-v1-Pass-2-grep-undercount` | 5 (post-P0.R1 closure) | **6** (P0.R4 Plan v1 — NEW MECHANISM-AXIS sub-shape) |
| **`### Pass-2-grep-auditor-verified-before-Plan-v1-approval`** | **operational rule extension; elevation candidacy** | **CLAUDE.md numbered doctrine 7th elevation** at P0.R4 closure-audit |
| `Zero-precision-items-pre-closure-predictions-blocked` counter | 0 (post-P0.R3 closure) | 1 (P0.R4 Plan v1 blocked-by-PI; new accumulation starts) |
| `### Twin-filename-pitfall-prevention` preventive events | 18 (post-P0.R4 Phase 0) | 19 at closure |

**Closure-conditional banks pending; locked at architect closure-audit per `Convention-drift-on-discipline-counts` + Path C grep-verify reconciliation discipline.**

---

## §8 — §8 row paste-template (CORRECTED for Plan v2 absorption)

```
| P0.R4 | Process supervisor (systemd + supervisord + auto-restart + journald) | CLOSED 2026-05-23 | D1+D2+D3+D4+D5 + 9 anchors + 4-artifact cycle (Phase 0 + Plan v1 + Plan v2 + closure); Plan v2 absorbed PI #1 (D4 env template incompleteness — 4 secret-class env vars now documented; A8 programmatic enforcement); `Plan-v1-Pass-2-grep-undercount` 5 → 6 instances; NEW `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` doctrine elevation at this closure (doctrine library 6 → 7); ZERO Python production code changes (deployment artifacts only) |
```

---

## §9 — Open questions for auditor at Plan v2: **0**

All PI #1 absorbed per Option (b) programmatic A8 enforcement. Plan v2 introduces ZERO new open questions. Plan v2 RATIFIED-PENDING per auditor independent re-grep verification.

If auditor returns 0 PIs at Plan v2 review → 16th instance of `### Zero-precision-items-at-auditor-review` doctrine fires at Plan v2 surface (extends Plan-vN enumeration rule precedent from P0.S9 + P0.R1) + closure proceeds with NEW `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` doctrine elevation event at closure-audit.

---

## §10 — 4-phase implementation plan (UPDATED from Plan v1 §10 with Plan v2 D4 + A8 + A9 changes)

**Phase 1 (~30 min) — Foundation (5 NEW deployment artifacts):**
- Create `deploy/` directory
- Create `deploy/systemd/dog-ai.service` per Plan v1 §2.1 verbatim
- Create `deploy/supervisord/dog-ai.conf` per Plan v1 §2.2 verbatim
- Create `deploy/dog-ai.env.example` per **Plan v2 §2.4 EXPANDED spec** (4 secret-class env vars + commented optional overrides)

**Phase 2 (~45 min) — D3 README documentation:**
- Create `deploy/README.md` per Plan v1 §2.3 6-section structure
- §3 documents ALL 4 secret-class env vars + runtime impact per Plan v2 §2.3 note

**Phase 3 (~45 min) — D5 test surface (Plan v2 anchors):**
- Create `tests/test_p0_r4_process_supervisor.py` with 9 anchors per Plan v2 §3
- A8 is PROGRAMMATIC per Plan v2 §2.5 (regex extracts `os.getenv` keys from `core/config.py` + asserts each in template)
- A9 covers all 4 secret-class keys per Plan v2 §2.5
- Run tests in isolation; confirm all 9 PASS

**Phase 4 (~30 min) — Deliberate-regression confirmations + closure narrative:**
- Run 6 deliberate-regression checks per Plan v2 §2.6 (note: (e) is UPDATED to TAVILY_API_KEY revert per Plan v2 absorption)
- Honor closure-actual count per §4 honest-count commitment table
- Apply Path C grep-verify reconciliation per `Convention-drift-on-discipline-counts` discipline
- Land closure narrative per Plan v2 §5 paste-template across CLAUDE.md header (INCLUDING NEW doctrine elevation under Architectural Disciplines section) + parent + subdir complete-plan.md
- Update `to_be_checked.md` with 21st deferred-canary entry + coverage matrix row
- Architect closure-audit handoff: memory file updates + LAND CLAUDE.md doctrine elevation per ratified text

**Expected total: ~2.5-3 hours** (SMALL-band cycle preserved; minor expansion at D4 + A8 + A9; closure narrative slightly longer due to new doctrine elevation event).

---

End of P0.R4 Plan v2.
