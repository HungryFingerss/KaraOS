# P0.R4 — Process supervisor (systemd unit + supervisord config + auto-restart + journald/log integration) — Plan v1

**Status:** Plan v1 drafted 2026-05-23 with Q1-Q7 locked per P0.R4 Phase 0 verdict. APPROVED-AT-AUDITOR-REVIEW pending.

**Parent audit:** `tests/p0_r4_process_supervisor_audit.md` (Phase 0 ACCEPTED with 0 BLOCKING PIs + 0 non-blocking observations + 1 ratified banking event for `Pre-audit-quantifier-precision-refined-by-grep` 2 → 3 instances).

---

## §1 — Phase 0 reconciliation

**§1.1 Q1-Q7 lock summary per auditor verdict 2026-05-23:**

| Q | Decision | Lock |
|---|---|---|
| Q1 | Path convention | **(a) supervisor-grouped** — `deploy/systemd/dog-ai.service` + `deploy/supervisord/dog-ai.conf`. supervisord cross-platform; platform-grouping conflates concerns. |
| Q2 | User context | **(a) dedicated `dog-ai` system user** — D3 README documents `useradd -r -s /bin/false dog-ai` + group memberships (`video`, `render`). |
| Q3 | Exponential backoff framing | **(a) accept discrepancy with honest documentation** per `### Spec-contracts-not-implementations`. systemd uses bounded burst limit (`Restart=on-failure` + `RestartSec=5s` + `StartLimitBurst=5` + `StartLimitIntervalSec=60s`); supervisord uses native exponential backoff. Both honor spec contract (prevent thrashing) via different implementations. Banks `Pre-audit-quantifier-precision-refined-by-grep` 3rd instance (NEW MECHANISM-GENERALITY sub-shape vs prior 2 COUNT-axis instances). |
| Q4 | Windows dev supervisor scope | **(a) OUT-OF-SCOPE** — P0.R4.X follow-up if dev environment needs supervisor-managed runs. |
| Q5 | Anchor count | **9 anchors at exact mid 9; inclusive ±15% band [7.65, 10.35]** — 8/9/10 all qualify ON-TARGET per locked methodology from P0.S5/B5/R2/R3. |
| Q6 | Env file path convention | **(c) split** — systemd uses `/etc/dog-ai/dog-ai.env` (matches systemd EnvironmentFile= + /etc/ convention); supervisord uses parent shell env (operator sets via shell export). Each supervisor uses its native env mechanism. |
| Q7 | Test surface approach | **(a) pure configparser** — cross-platform; runs on Windows dev + Linux CI; verifies file structure not systemd semantic. systemd semantic verified at deployment time per D3 README. |

**§1.2 Diligent Pass-2 grep enumeration (per formal rule extension PROMOTED at P0.R3 Plan v1 verdict 2026-05-23; auditor verification target):**

P0.R4 ships 5 NEW deployment artifacts + 1 NEW test file. ZERO Python production code changes. Exhaustive enumeration:

| Path | Edit type | Lines | D-decision |
|---|---|---|---|
| `deploy/systemd/dog-ai.service` | NEW file | ~30-40 LOC | D1 |
| `deploy/supervisord/dog-ai.conf` | NEW file | ~30-40 LOC | D2 |
| `deploy/README.md` | NEW file | ~150-200 LOC | D3 |
| `deploy/dog-ai.env.example` | NEW file | ~15-20 LOC | D4 |
| `tests/test_p0_r4_process_supervisor.py` | NEW file | ~100-150 LOC | D5 (9 anchors) |

**Greenfield verification status (re-verified at Plan v1 drafting):**

- `deploy/` directory: ZERO pre-existing — NEW per P0.R4
- `*.service` files: ZERO pre-existing — NEW per P0.R4
- `supervisord*` files: ZERO pre-existing — NEW per P0.R4
- `tests/p0_r4*` test files: ONLY Phase 0 audit + this Plan v1 md exist (NEW test py file pending Phase 1)
- `systemd|supervisord|nssm|Task Scheduler` keyword matches: 4 files (CLAUDE.md passing mention + everything_about_system.md passing reference + Phase 0 audit md + this Plan v1 md; all expected at architect-side)

NO twin-filename collision; clean greenfield landing at all 5 paths.

**§1.3 P0.R4 vs prior P0.R cycles — cycle shape distinction (banking-worthy):**

| Cycle | Code changes | Test surface | Cycle shape |
|---|---|---|---|
| P0.R1 | `core/vision.py::FaceEmbedder.embed()` wrap | behavioral + AST | cognitive runtime supervision |
| P0.R2 | `core/vision.py` D1+D2+D3 + NEW `core/vision_provider_state.py` + `core/health.py` + `pipeline.py` + `core/config.py` | behavioral + AST + parametrize | cognitive runtime supervision |
| P0.R3 | `core/pipeline_state_store.py` + `core/health.py` + `pipeline.py` + `core/config.py` | behavioral + AST + parametrize | cognitive runtime supervision |
| **P0.R4** | **ZERO Python production code changes; 5 NEW deployment artifacts under `deploy/`** | **structural file tests via configparser (cross-platform)** | **deployment artifacts** |

P0.R4 is materially distinct. Cycle resembles P0.0 (CI scaffold landing) more than P0.R1/R2/R3 (cognitive runtime supervision). This distinction validates the formal Pass-2 grep operational rule extension's empirical basis across DISTINCT cycle shapes — banked per auditor's Phase 0 verdict meta-observation. If P0.R4 Plan v1 also fires clean (5th consecutive validation), CLAUDE.md doctrine elevation candidacy activated.

**§1.4 Cross-spec orthogonality verified clean:**

- **P0.S6 secrets management**: D1 systemd unit uses `EnvironmentFile=/etc/dog-ai/dog-ai.env` (NOT inline `Environment=` with values); D2 supervisord uses `%(ENV_VAR)s` interpolation from parent shell env; D4 env file template values are EMPTY (regex `r"^KEY=\s*$"` enforces). P0.S6 discipline honored.
- **P0.S3 env validation**: existing `core/env_validation.py` runtime contract is the boot-time check; P0.R4 is the deployment-time complement. No code overlap.
- **P0.R3 vision watchdog**: in-process watchdog supervises `_background_vision_loop` task; P0.R4 process supervisor supervises the whole `pipeline.py` process. Complement; no overlap.
- **Wave 5 health log**: persistent process crashes hit systemd `StartLimitBurst`; service stays down + health log stops emitting; operator monitoring via journald + `systemctl status`.

**§1.5 Twin-filename pitfall 18th preventive event already honored at Phase 0 audit drafting** (no doctrine count bump per locked enumeration rule).

---

## §2 — D-decision contracts (LOCKED per Q1-Q7 verdicts)

### §2.1 D1 — systemd unit file (`deploy/systemd/dog-ai.service`)

**LOCKED spec:**

```ini
[Unit]
Description=dog-ai cognitive runtime
Documentation=https://github.com/HungryFingerss/Cognitive-System
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=dog-ai
WorkingDirectory=/opt/dog-ai
ExecStart=/opt/dog-ai/venv/bin/python /opt/dog-ai/pipeline.py
EnvironmentFile=/etc/dog-ai/dog-ai.env
Restart=on-failure
RestartSec=5s
StartLimitBurst=5
StartLimitIntervalSec=60s
StandardOutput=journal+console
StandardError=journal+console

[Install]
WantedBy=multi-user.target
```

**Contract:** restart-on-failure with bounded burst limit (5 attempts in 60s window); after burst exhausted, systemd holds state=failed for operator intervention. `EnvironmentFile=` references external env file (P0.S6 compliance). journald log integration via `StandardOutput=journal+console` + `StandardError=journal+console`.

### §2.2 D2 — supervisord config (`deploy/supervisord/dog-ai.conf`)

**LOCKED spec:**

```ini
[program:dog-ai]
command=/opt/dog-ai/venv/bin/python /opt/dog-ai/pipeline.py
directory=/opt/dog-ai
user=dog-ai
autostart=true
autorestart=true
startsecs=5
startretries=10
stopwaitsecs=30
stopsignal=INT
stdout_logfile=/var/log/dog-ai/stdout.log
stdout_logfile_maxbytes=10MB
stdout_logfile_backups=5
stderr_logfile=/var/log/dog-ai/stderr.log
stderr_logfile_maxbytes=10MB
stderr_logfile_backups=5
environment=TOGETHER_API_KEY="%(ENV_TOGETHER_API_KEY)s",HF_TOKEN="%(ENV_HF_TOKEN)s"
```

**Contract:** native exponential backoff via supervisord (delays grow on consecutive failures up to ~2 minutes); `startretries=10` caps consecutive attempts. `stopsignal=INT` triggers pipeline.py's SIGINT graceful shutdown handler with 30s budget. Log rotation 10MB × 5 backups.

### §2.3 D3 — Installation README (`deploy/README.md`)

**LOCKED content shape:**

1. **§1 systemd installation** — 5-step procedure: copy unit → create `dog-ai` user (with `video`+`render` groups) → create `/etc/dog-ai/dog-ai.env` (chmod 0600) → `systemctl daemon-reload` + `systemctl enable --now dog-ai` → verify via `systemctl status dog-ai`
2. **§2 supervisord installation** — 4-step procedure: install supervisord (`pip install supervisor` OR apt) → copy conf → set env vars in parent shell → `supervisorctl reread && supervisorctl add dog-ai`
3. **§3 env file template usage** — chmod 0600 + EnvironmentFile= reference + P0.S6 secrets discipline note
4. **§4 verification commands** — `systemctl status dog-ai` / `supervisorctl status dog-ai` / `journalctl -u dog-ai -f`
5. **§5 troubleshooting** — common failure modes: missing env file, wrong permissions, camera access denied, `StartLimitBurst` exceeded → `systemctl reset-failed dog-ai && systemctl start dog-ai`
6. **§6 supervisor comparison table** — when to use systemd vs supervisord; document Q3 backoff mechanism discrepancy honestly (systemd bounded burst limit vs supervisord native exponential backoff; both prevent thrashing)

### §2.4 D4 — Env file template (`deploy/dog-ai.env.example`)

**LOCKED spec:**

```bash
# dog-ai cognitive runtime — environment variables
#
# Copy this file to /etc/dog-ai/dog-ai.env (chmod 0600, owned by dog-ai user)
# OR set as supervisord environment via shell export
#
# Required:
TOGETHER_API_KEY=
#
# Optional (pyannote diarization-3.1 — accept HuggingFace license first):
HF_TOKEN=
#
# Optional overrides (defaults documented in core/config.py):
# DASHBOARD_BIND=127.0.0.1
# DASHBOARD_BIND_ALLOW_ANY=
```

**Contract:** values EMPTY (operator fills in). NO leaked secrets per P0.S6 discipline. All env vars that `core/config.py` reads via `os.getenv(...)` are documented. File NAME is `.env.example` (matches existing convention; `.env` is gitignored).

### §2.5 D5 — Test surface (`tests/test_p0_r4_process_supervisor.py`)

**LOCKED contract:** 9 logical anchors per §3 decomposition. Cross-platform via configparser (no systemd-analyze dependency). 1:1 pytest-function-to-anchor mapping.

### §2.6 Deliberate-regression protocol (induction-surfaces-invariant-gaps; 6 reverts)

Before declaring closure, developer runs 6 deliberate-regression checks. Each fires the named anchor when reverted. If any check fails to fire, anchor needs strengthening (per `### Induction-surfaces-invariant-gaps` operational rule 3).

| Revert | Removed contract | Expected fire |
|---|---|---|
| **(a)** Drop `Restart=on-failure` from systemd `[Service]` section | D1 restart directive gone | A3 source-inspection fires (Restart= substring missing) |
| **(b)** Replace `EnvironmentFile=` with inline `Environment="TOGETHER_API_KEY=sk-..."` | D1 P0.S6 compliance violated | A4 source-inspection fires (EnvironmentFile= substring missing / inline Environment with sk- detected) |
| **(c)** Drop `autorestart=true` from supervisord `[program:dog-ai]` | D2 native exponential backoff gone | A6 source-inspection fires (autorestart=true substring missing) |
| **(d)** Drop `supervisorctl` references from D3 README | D3 supervisord install section gone | A7 source-inspection fires (supervisorctl substring missing) |
| **(e)** Add value `TOGETHER_API_KEY=sk-real-secret` to D4 env template | D4 P0.S6 compliance violated | A9 regex `r"^TOGETHER_API_KEY=\s*$"` fails to match (non-empty value) |
| **(f)** Drop `[Install]` section from D1 systemd unit | D1 well-formedness violated | A2 configparser-section-check fires ([Install] section missing) |

Phase 5 closure narrative includes deliberate-regression confirmation outcomes per locked discipline.

---

## §3 — Anchor decomposition LOCK (9 anchors at exact mid 9 inclusive ±15%)

| # | D | Anchor name | Type | Coverage |
|---|---|---|---|---|
| A1 | D1 | `test_p0_r4_d1_anchor_1_systemd_unit_exists` | source-inspection | File exists at `deploy/systemd/dog-ai.service` + non-empty + configparser-parseable |
| A2 | D1 | `test_p0_r4_d1_anchor_2_systemd_unit_has_required_sections` | source-inspection | [Unit] + [Service] + [Install] sections present |
| A3 | D1 | `test_p0_r4_d1_anchor_3_systemd_restart_directives_present` | source-inspection | [Service] has `Restart=on-failure` + `RestartSec=` + `StartLimitBurst=` + `StartLimitIntervalSec=` |
| A4 | D1 | `test_p0_r4_d1_anchor_4_systemd_environment_file_reference` | source-inspection | [Service] has `EnvironmentFile=` (NOT inline `Environment=` with secret-looking values — P0.S6 compliance) |
| A5 | D2 | `test_p0_r4_d2_anchor_1_supervisord_conf_exists` | source-inspection | File exists at `deploy/supervisord/dog-ai.conf` + configparser-parseable |
| A6 | D2 | `test_p0_r4_d2_anchor_2_supervisord_program_section_has_autorestart` | source-inspection | `[program:dog-ai]` has `autorestart=true` + `startretries=` + `startsecs=` |
| A7 | D3 | `test_p0_r4_d3_anchor_1_readme_exists_and_covers_both_supervisors` | source-inspection | File exists at `deploy/README.md` + contains `systemd` + `supervisord` install section headers + `systemctl` + `supervisorctl` command examples |
| A8 | D4 | `test_p0_r4_d4_anchor_1_env_template_exists_with_required_keys` | source-inspection | File exists at `deploy/dog-ai.env.example` + contains `TOGETHER_API_KEY=` + `HF_TOKEN=` entries |
| A9 | D4 | `test_p0_r4_d4_anchor_2_env_template_values_are_empty_per_p0s6` | source-inspection | Regex `r"^(TOGETHER_API_KEY|HF_TOKEN)=\s*$"` matches both entries (NO leaked secret values — P0.S6 compliance) |

**Total: 9 logical anchors. 1:1 pytest-function-to-anchor mapping (no parametrize fan-out). Mid 9 exact match to Phase 0 §6 lock.**

---

## §4 — Honest-count commitment table (inclusive ±15% per locked methodology)

| Closure-actual | Overage | Band | Doctrine impact + commitment |
|---|---|---|---|
| 6 | −33.3% | ≥30% FALSIFICATION | Doctrine demotes; architect commits to honoring this outcome at closure-audit |
| 7 | −22.2% | ±15-30% SLIGHT-DRIFT-DOWN | Doctrine holds (watch trajectory); architect commits to honoring |
| **8** | **−11.1%** | **±15% ON-TARGET** | **Doctrine bumps 16 → 17**; architect commits |
| **9** | **0.0%** | **±15% ON-TARGET (exact mid)** | **Doctrine bumps 16 → 17; 9+ consecutive 0% exact-mid streak extends per `Doctrine-prediction-precision-improving-over-arc`**; architect commits |
| **10** | **+11.1%** | **±15% ON-TARGET** | **Doctrine bumps 16 → 17**; architect commits |
| 11 | +22.2% | ±15-30% SLIGHT-DRIFT-UP | Doctrine holds (watch trajectory); architect commits to honoring |
| ≥12 | ≥+33% | FALSIFICATION | Doctrine demotes; architect commits to honoring this outcome at closure-audit |

**`Explicit-closure-honest-count-commitment` 20 → 22 (21st MADE at Plan v1 §4 + 22nd HONORED at closure per STRICT separation).**

---

## §5 — Closure-narrative paste-template

(Architect's pre-draft; subject to closure-actual reconciliation + Path C grep-verify of doctrine counts.)

**P0.R4 closure note:**

> ## P0.R4 — Process supervisor (systemd unit + supervisord config + auto-restart + journald/log integration) — D1+D2+D3+D4+D5 + 9 anchors + 6 deliberate-regression checks + 8th OPTIONAL-Plan-v2 proof case + pattern-broken streak extends to 5 cycles + formal Pass-2 grep rule reaches CLAUDE.md doctrine elevation candidacy threshold  [CLOSED 2026-05-23]
> 
> **Sub-PR sequence:** Phase 0 audit (`tests/p0_r4_process_supervisor_audit.md`, APPROVED with 0 BLOCKING PIs + 0 non-blocking observations + 1 ratified banking event — **15th instance of `### Zero-precision-items-at-auditor-review` at Phase 0 surface**; 4th consecutive clean review in pattern-broken streak; banks `Pre-audit-quantifier-precision-refined-by-grep` 2 → 3 instances per Q3 mechanism-generality refinement) → Plan v1 (`tests/p0_r4_process_supervisor_plan_v1.md`, RATIFIED with 0 PIs at Plan v1 surface — **16th instance of doctrine** firing at Plan v1 review; **pattern-broken streak extends from 4 → 5 cycles**; **8th OPTIONAL-Plan-v2 path proof case** under absorbed sub-rule track record P0.S3 + P0.B3 + P0.B5 + P0.B6 + P0.S8 + P0.R2 + P0.R3 + P0.R4; **formal Pass-2 grep rule reaches 5+ consecutive validations** → CLAUDE.md doctrine elevation candidacy evaluation at architect closure-audit) → Phase 1-5 implementation.
> 
> **Cycle shape distinction**: P0.R4 is materially distinct from prior P0.R cycles — ZERO Python production code changes; deployment artifacts only. Cycle resembles P0.0 (CI scaffold landing). Test surface is structural file tests via configparser (cross-platform; runs on Windows dev + Linux CI; no systemd-analyze dependency).
> 
> **What shipped:** 5 NEW deployment artifacts: `deploy/systemd/dog-ai.service` (D1) + `deploy/supervisord/dog-ai.conf` (D2) + `deploy/README.md` (D3) + `deploy/dog-ai.env.example` (D4) + `tests/test_p0_r4_process_supervisor.py` (D5).
> 
> **D1 (systemd unit)**: bounded burst limit auto-restart per Q3 (a) — `Restart=on-failure` + `RestartSec=5s` + `StartLimitBurst=5` + `StartLimitIntervalSec=60s`. journald integration via `StandardOutput=journal+console`. P0.S6 compliance via `EnvironmentFile=/etc/dog-ai/dog-ai.env`.
> 
> **D2 (supervisord conf)**: native exponential backoff per Q3 (a) — `autorestart=true` + `startretries=10` + `startsecs=5`. SIGINT graceful shutdown with 30s budget. Log rotation 10MB × 5 backups.
> 
> **D3 (installation README)**: 6-section documentation covering systemd install + supervisord install + env file usage + verification commands + troubleshooting + supervisor comparison table.
> 
> **D4 (env file template)**: P0.S6 compliant — values EMPTY (operator fills in); regex enforcement at A9.
> 
> **D5 (test surface)**: 9 logical anchors via configparser-based structural tests (cross-platform).
> 
> **Total P0.R4 LOGICAL ANCHORS: 9** (Plan v1 §3 LOCK EXACT MATCH at exact mid 9 inclusive ±15% band [7.65, 10.35]).
> 
> **Q5 closure under MID-RANGE methodology**: auditor mid 9, Plan v1 lock 9, **closure actual {{N}}** ({{0%|−11.1%|+11.1%}}; {{exact mid|ON-TARGET}}). Doctrine `### Phase-0-granular-decomposition-enables-accurate-estimates` **BUMPS 16 → 17 SUPPORTING INSTANCES** per inclusive ±15% band table.
> 
> **Plan v1 §4 honest-count commitment HONORED — 22nd instance of `Explicit-closure-honest-count-commitment` discipline** (21st MADE + 22nd HONORED per STRICT separation).
> 
> **6/6 deliberate-regression confirmations PASSED** (a/b/c/d/e/f per §2.6). All reverts restored cleanly.
> 
> **`### Zero-precision-items-at-auditor-review` doctrine 14 → 16 instances** (Phase 0 15th + Plan v1 16th). **OPTIONAL-Plan-v2 path TAKEN — 8th proof case** banked under absorbed sub-rule. **Pattern-broken streak extends from 3 → 5 cycles** (P0.R2 Plan v1 + P0.R3 Phase 0 + P0.R3 Plan v1 + P0.R4 Phase 0 + P0.R4 Plan v1).
> 
> **`Pre-audit-quantifier-precision-refined-by-grep` 2 → 3 instances** banked at Phase 0 verdict (NEW MECHANISM-GENERALITY sub-shape; "exponential backoff" precise for supervisord, approximate for systemd which uses bounded burst limit).
> 
> **Formal Pass-2 grep operational-rule extension reaches 5+ consecutive validations** (P0.R2 Plan v1 + P0.R3 Phase 0 + P0.R3 Plan v1 + P0.R4 Phase 0 + P0.R4 Plan v1) → **CLAUDE.md doctrine elevation candidacy ACTIVATED at architect closure-audit**. Per auditor handoff: 4-criteria ratification (instance enumeration + discipline-stability + cross-reference integrity + falsification clause integrity) evaluation at closure-audit determines whether elevation is warranted.
> 
> **Strict-mode 62 → 65 applications + 18 → 19 closures** (3-artifact OPTIONAL-Plan-v2 cycle: Phase 0 + Plan v1 + closure). **Discipline counts (3-artifact cycle)**: spec-first review cycle 72 → **75-for-75 at closure**. **`### Grep-baseline-before-drafting` 29 → 32 instances** (3 artifacts). **Cross-cycle-handoff transparency precedent 35 → 38 successful** (3 artifacts). **Spec-time grep-verification 39 → 42 instances** (3 artifacts; Phase 0 §1 Pass-1 + Plan v1 §1.2 DILIGENT Pass-2 per formal rule + closure-narrative drafting Pass-3 baseline).
> 
> **`### Twin-filename-pitfall-prevention` 18th preventive event already honored at Phase 0** (no doctrine count bump per locked enumeration rule).
> 
> **Auditor-Q5-estimates-trail-grep 22 → 23 banked closures** at 0% ON-TARGET reading (if closure-actual = 9 exact). Trajectory: 8th consecutive 0% reading extends per `Doctrine-prediction-precision-improving-over-arc`.
> 
> **Deferred-canary strategy 21st application** — entry pasted verbatim into `c:\Users\jagan\dog-ai\to_be_checked.md`.
> 
> **Known Limitations (P0.R4 closure)**:
> 
> 1. **systemd bounded burst limit vs "exponential backoff"** — pre-audit quantifier framing was approximate for systemd; D3 README honest documentation explains the mechanism distinction (bounded burst limit vs native exponential backoff). Both satisfy the spec contract (prevent thrashing).
> 2. **Windows dev supervisor OUT-OF-SCOPE per Q4** — P0.R4.X follow-up candidate if dev environment ever needs supervisor-managed runs.
> 3. **`StartLimitBurst` exceeded requires manual `reset-failed`** — no automatic recovery beyond 5 attempts in 60s; prevents thrashing by design. D3 README troubleshooting documents the operator recovery procedure.
> 4. **Camera/GPU device permissions** — `dog-ai` user must be in `video` + `render` groups; D3 README install step documents this.
> 5. **Test surface verifies STRUCTURE not SEMANTIC** — configparser-based tests catch malformed unit files but don't verify systemd would actually start the service (deployment-time verification per D3 README).
> 
> **Cumulative suite**: pending closure (+~9 new pytest functions from D5 test file; ZERO Python production code changes).
> 
> **Files touched (5 NEW files; 0 modified):** see §1.2 enumeration.

**§5.1 5-surface landing checklist (developer Phase 5 closure):**

1. ✓ `c:\Users\jagan\dog-ai\dog-ai\CLAUDE.md` — header P0.R4 entry prepended above P0.R3
2. ✓ `c:\Users\jagan\dog-ai\complete-plan.md::P0.R4` (parent) — status (no status pre-existed) → `[CLOSED]` + closure note
3. ✓ `c:\Users\jagan\dog-ai\dog-ai\complete-plan.md::P0.R4` (subdir) — full closure narrative
4. ✓ `c:\Users\jagan\dog-ai\to_be_checked.md` — 21st deferred-canary entry + coverage matrix row
5. ✓ Architect memory files via post-closure handoff (`feedback_phase_0_zero_precision_items_at_auditor_review.md` 15 → 16; `MEMORY.md` index refresh; potential CLAUDE.md doctrine elevation per 5+ consecutive Pass-2 grep validations)

---

## §6 — Architect's diligent Pass-2 grep enumeration (auditor verification target per formal rule extension)

**Verification-target query patterns + expected outcomes:**

| Grep pattern | Expected matches | Verification |
|---|---|---|
| `deploy/` directory glob | 5 NEW files (3 supervisor configs + README + env template) | NEW per P0.R4 |
| `*.service` files | 1 NEW file (`deploy/systemd/dog-ai.service`) | NEW per D1 |
| `supervisord*` files | 1 NEW file (`deploy/supervisord/dog-ai.conf`) | NEW per D2 |
| `*.env.example` files | 1 NEW file (`deploy/dog-ai.env.example`) — note: pre-existing `.env.example` files at repo root may exist (developer to verify at Phase 1 against `core/config.py` env var consumers) | NEW per D4 |
| `tests/test_p0_r4*` files | 1 NEW file (`tests/test_p0_r4_process_supervisor.py`) | NEW per D5 |
| `EnvironmentFile=` substring in `deploy/systemd/dog-ai.service` | 1 match | NEW per D1 + P0.S6 compliance |
| `autorestart=true` substring in `deploy/supervisord/dog-ai.conf` | 1 match | NEW per D2 |
| `Restart=on-failure` substring in `deploy/systemd/dog-ai.service` | 1 match | NEW per D1 |
| `useradd` substring in `deploy/README.md` | 1+ match (install step) | NEW per D3 |
| Empty-value regex `r"^(TOGETHER_API_KEY|HF_TOKEN)=\s*$"` in `deploy/dog-ai.env.example` | 2 matches | NEW per D4 + P0.S6 compliance |

**Auditor's independent re-grep target:** all 10 patterns above + cross-check NO twin filename collision + NO inline secret-looking values in any of the 5 NEW files.

**Architect prediction (probabilistic per `Zero-precision-items-pre-closure-predictions-blocked` operational rule + formal Pass-2 grep rule):** Plan v1 §1.2 + §6 enumeration is diligent; expecting clean auditor independent re-grep verification per the formal rule extension. If clean (5th consecutive validation: P0.R2 Plan v1 + P0.R3 Phase 0 + P0.R3 Plan v1 + P0.R4 Phase 0 + P0.R4 Plan v1) → pattern-broken streak extends to 5 cycles + CLAUDE.md doctrine elevation candidacy activated at architect closure-audit per 5-instance elevation precedent.

---

## §7 — Doctrine bump projection at closure (closure-conditional per inclusive ±15% band)

| Doctrine | Pre-P0.R4 baseline | Closure projection |
|---|---|---|
| `### Phase-0-granular-decomposition-enables-accurate-estimates` | 16 (post-P0.R3 closure) | 17 IF closure-actual ∈ {8, 9, 10} |
| `### Zero-precision-items-at-auditor-review` | 15 (post-P0.R4 Phase 0) | 16 IF Plan v1 fires clean (0 PIs) |
| `### Induction-surfaces-invariant-gaps` | 11 (post-P0.R3 closure) | 11 (stays unless in-flight detector-strengthening event) |
| `### Architect-reads-production-code-before-sign-off` | 15 (post-P0.R3 closure-audit) | 16 IF architect closure-audit fires at P0.R4 closure |
| OPTIONAL-Plan-v2 sub-rule proof cases | 7 (post-P0.R3 closure) | 8 IF closure-actual ∈ {8, 9, 10} |
| `Explicit-closure-honest-count-commitment` | 20 (post-P0.R3 closure) | 22 (21 MADE at Plan v1 §4 + 22 HONORED at closure) |
| Strict-mode applications | 62 (post-P0.R3 closure) | 65 (3-artifact cycle: Phase 0 + Plan v1 + closure) |
| Strict-mode closures | 18 (post-P0.R3 closure) | 19 |
| Spec-first review cycle | 72 (post-P0.R3 closure) | 75 (3 artifacts × +1) |
| `### Grep-baseline-before-drafting` | 29 (post-P0.R3 closure) | 32 (3 artifacts) |
| Cross-cycle-handoff transparency | 35 (post-P0.R3 closure) | 38 (3 artifacts) |
| Spec-time grep-verification | 39 (post-P0.R3 closure) | 42 (3 artifacts) |
| `Doctrine-prediction-precision-improving-over-arc` | 8+ cycle 0% streak (post-P0.R3 closure) | 9+ cycle 0% streak ONLY IF closure-actual = 9 exact |
| `Pre-audit-quantifier-precision-refined-by-grep` | 3 (post-P0.R4 Phase 0) | stays 3 (no new instance at Plan v1) |
| **Formal Pass-2 grep rule validations** | **4 (post-P0.R4 Phase 0)** | **5 IF Plan v1 fires clean → CLAUDE.md doctrine elevation candidacy ACTIVATED at closure-audit** |
| `### Twin-filename-pitfall-prevention` preventive events | 18 (post-P0.R4 Phase 0) | 19 at closure (no doctrine count bump per locked enumeration rule) |

**Closure-conditional banks pending; locked at architect closure-audit per `Convention-drift-on-discipline-counts` + Path C grep-verify reconciliation discipline.**

---

## §8 — §8 row paste-template (for parent + subdir complete-plan.md + CLAUDE.md header)

```
| P0.R4 | Process supervisor (systemd + supervisord + auto-restart + journald) | CLOSED 2026-05-23 | D1+D2+D3+D4+D5 + 9 anchors at exact mid 9 inclusive ±15%; 8th OPTIONAL-Plan-v2 proof case; pattern-broken streak extends to 5 cycles; formal Pass-2 grep rule reaches CLAUDE.md doctrine elevation candidacy at 5+ consecutive validations; ZERO Python production code changes (deployment artifacts only) |
```

---

## §9 — Open questions for auditor at Plan v1: **0** (per OPTIONAL-Plan-v2 path candidacy)

All Q1-Q7 LOCKED per Phase 0 verdict 2026-05-23. Plan v1 introduces ZERO new open questions. Plan v1 is RATIFIED-PENDING per auditor independent re-grep verification.

If auditor returns 0 PIs at Plan v1 review → 16th instance of `### Zero-precision-items-at-auditor-review` doctrine fires at Plan v1 surface + 8th OPTIONAL-Plan-v2 proof case unlocked + pattern-broken streak extends to 5 cycles + formal Pass-2 grep rule reaches 5+ validations → CLAUDE.md doctrine elevation candidacy evaluation activated at architect closure-audit.

---

## §10 — 4-phase implementation plan (developer handoff; ~2-3 hours SMALL-band cycle)

**Phase 1 (~30 min) — Foundation (5 NEW deployment artifacts):**
- Create `deploy/` directory
- Create `deploy/systemd/dog-ai.service` per §2.1 verbatim
- Create `deploy/supervisord/dog-ai.conf` per §2.2 verbatim
- Create `deploy/dog-ai.env.example` per §2.4 verbatim
- Verify all 4 files parse via configparser locally (sanity check)

**Phase 2 (~45 min) — D3 README documentation:**
- Create `deploy/README.md` per §2.3 6-section structure
- Include systemd install (5 steps) + supervisord install (4 steps) + env file usage + verification + troubleshooting + supervisor comparison
- Document Q3 honest mechanism distinction (systemd bounded burst limit vs supervisord native exponential backoff; both prevent thrashing per `### Spec-contracts-not-implementations`)

**Phase 3 (~45 min) — D5 test surface:**
- Create `tests/test_p0_r4_process_supervisor.py` with 9 anchors per §3
- 1:1 pytest-function-to-anchor mapping
- Use `configparser` for D1+D2 INI-style parsing
- Use regex for A9 P0.S6 empty-value enforcement
- Run tests in isolation; confirm all 9 PASS

**Phase 4 (~30 min) — Deliberate-regression confirmations + closure narrative:**
- Run 6 deliberate-regression checks per §2.6; confirm each fires expected anchor; revert each
- Honor closure-actual count per §4 honest-count commitment table
- Apply Path C grep-verify reconciliation per `Convention-drift-on-discipline-counts` discipline
- Land closure narrative per §5 paste-template across CLAUDE.md header + parent + subdir complete-plan.md
- Update `to_be_checked.md` with 21st deferred-canary entry + coverage matrix row
- Architect closure-audit handoff: memory file updates + potential CLAUDE.md doctrine elevation evaluation for formal Pass-2 grep rule

**Expected total: ~2.5 hours** (SMALL-band cycle; ZERO Python production code changes makes implementation faster than prior P0.R cycles).

---

End of P0.R4 Plan v1.
