# P0.R4 — Process supervisor (systemd unit + supervisord config + auto-restart + journald/log integration) — Phase 0 audit

**Status:** Phase 0 audit drafted 2026-05-23. APPROVED-AT-AUDITOR-REVIEW pending.

**Pre-audit framing (verbatim from parent `c:\Users\jagan\dog-ai\complete-plan.md::P0.R4`):**

> ### P0.R4 — No process supervisor
>
> **Fix:** `deploy/systemd/dog-ai.service` + `deploy/supervisord/dog-ai.conf`. Auto-restart with exponential backoff. journald / Event Log.

---

## §1 — Grep-verified findings (DILIGENT Pass-2 per formal rule extension PROMOTED at P0.R3 Plan v1 verdict 2026-05-23)

**§1.1 Existing deploy artifacts (greenfield-verified):**

| Pattern | Match count | Verification |
|---|---|---|
| `deploy/**` directory glob | 0 matches | NEW directory in P0.R4 ✓ |
| `**/*.service` | 0 matches | NEW systemd unit in P0.R4 ✓ |
| `**/supervisord*` | 0 matches | NEW supervisord conf in P0.R4 ✓ |
| `systemd|supervisord|nssm|Task Scheduler` keyword scan across project | Only 2 doc files (CLAUDE.md `Jetson deployment — ... systemd service` mention + everything_about_system.md passing reference) + parent complete-plan.md::P0.R4 spec text | NO existing code uses any supervisor ✓ |
| `tests/p0_r4*` files | 0 matches | NEW test artifacts in P0.R4 ✓ (Twin-filename pitfall 18th preventive event candidate honored at audit drafting) |

Pre-audit framing quantifier check: pre-audit says "No process supervisor" — accurate; zero pre-existing supervisor configs across project. Quantifier precise + scoped; NO `Pre-audit-quantifier-precision-refined-by-grep` instance to bank.

**§1.2 Cross-spec dependencies grep-verified:**

| Symbol | Source | Cross-spec relevance |
|---|---|---|
| `TOGETHER_API_KEY` | `core/config.py:313` via `os.getenv("TOGETHER_API_KEY", "")` | P0.S6 secrets discipline — must use `EnvironmentFile=` for systemd (NOT inline `Environment=` with values); supervisord uses `%(ENV_VAR)s` interpolation |
| `HF_TOKEN` | `core/config.py:324` via `os.getenv("HF_TOKEN", "")` | Same P0.S6 secrets concern; pyannote-gated optional env var |
| Other env vars | Various `os.getenv(...)` calls in `core/*.py` and `pipeline.py` | Documented in env file template; reviewer's `core/env_validation.py` is the runtime contract (P0.S3 lineage) |

P0.S6 secrets discipline imposes load-bearing constraint: systemd unit must NEVER inline `Environment="TOGETHER_API_KEY=sk-..."` with actual values; must reference an external `EnvironmentFile=` that's chmod 0600 + owned by the service user. supervisord uses `%(ENV_VAR)s` pattern to pull from process environment (set externally via shell or systemd-fronted supervisord).

**§1.3 Pre-audit framing quantifier check — "exponential backoff" semantic verification:**

Pre-audit says "Auto-restart with exponential backoff." Grep-verified supervisor semantic:

| Supervisor | Native exponential backoff? | Mechanism |
|---|---|---|
| **systemd** | NO | Bounded burst limit: `Restart=on-failure` + flat `RestartSec=5s` + `StartLimitBurst=5` + `StartLimitIntervalSec=60s` → 5 attempts in 60s window, then stops trying (no exponential growth between attempts) |
| **supervisord** | YES | Native exponential backoff between consecutive restart attempts (delays grow up to ~2 minutes); `startretries=10` caps consecutive attempts |

**Quantifier-precision observation candidate:** the pre-audit framing's "exponential backoff" is precise for supervisord but APPROXIMATE for systemd (bounded burst limit achieves the same goal — prevent thrashing — via a different mechanism). Honest disclosure: the contract's SPIRIT (prevent thrashing on persistent failure) is satisfied by both; the LITERAL mechanism differs. See Q3 for adjudication. **NEW `Pre-audit-quantifier-precision-refined-by-grep` 3rd instance candidate** if auditor adjudicates "spirit-satisfied" as the precise framing.

**§1.4 Twin-filename pitfall 18th preventive event (already honored at audit drafting):**

Zero pre-existing P0.R4 artifacts. Phase 0 audit lands cleanly at `tests/p0_r4_process_supervisor_audit.md`. 18th preventive event honored at audit drafting (no doctrine count bump per locked enumeration rule).

---

## §2 — Decomposed D-decisions (architect leans; auditor adjudication via Q1-Q7)

### D1 — systemd unit file

**Edit site:** NEW `deploy/systemd/dog-ai.service` (~30-40 LOC).

**Architect lean spec (Q1+Q3 ratification pending):**

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

**Contract:**
- `Restart=on-failure` + `RestartSec=5s` triggers auto-restart 5 seconds after crash
- `StartLimitBurst=5` + `StartLimitIntervalSec=60s` caps thrash at 5 attempts/minute (after which systemd holds state in `failed` for operator intervention)
- `EnvironmentFile=` references external env file (P0.S6 compliance — no inline secrets)
- `StandardOutput=journal+console` routes stdout to journald (Linux Event Log)
- `User=dog-ai` requires the operator creates a `dog-ai` system user during install (documented in D3 README)
- `WorkingDirectory=/opt/dog-ai` requires installation to `/opt/dog-ai/` (documented in D3)

### D2 — supervisord config

**Edit site:** NEW `deploy/supervisord/dog-ai.conf` (~30-40 LOC).

**Architect lean spec (Q3 ratification pending):**

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

**Contract:**
- `autorestart=true` + `startretries=10` triggers supervisord's native exponential backoff (delays grow on consecutive failures up to ~2 minutes)
- `startsecs=5` requires process runs ≥5s to count as successful start
- `stopsignal=INT` sends SIGINT (matches pipeline.py's graceful shutdown handler)
- `stopwaitsecs=30` allows up to 30s for graceful shutdown before SIGKILL
- `stdout_logfile` + `stderr_logfile` route logs to files with 10MB × 5 rotation (supervisord doesn't use journald)
- `environment=` uses `%(ENV_VAR)s` interpolation to pull from supervisord's parent environment (operator sets via shell or systemd-fronted supervisord)

### D3 — Installation README

**Edit site:** NEW `deploy/README.md` (~150-200 LOC).

**Contract:** README documents:
- **Section 1**: systemd installation (5-step procedure: copy unit → create user → create env file → enable service → verify status)
- **Section 2**: supervisord installation (4-step procedure: install supervisord → copy conf → set env vars → reload supervisord)
- **Section 3**: env file template usage + secrets discipline (chmod 0600 + EnvironmentFile= reference)
- **Section 4**: Verification commands (`systemctl status dog-ai` / `supervisorctl status dog-ai` / journald grep)
- **Section 5**: Troubleshooting (common failure modes: missing env file, wrong user permissions, camera access denied, StartLimitBurst exceeded)
- **Section 6**: Comparison table (systemd vs supervisord; when to use which)

### D4 — Env file template

**Edit site:** NEW `deploy/dog-ai.env.example` (~15-20 LOC).

**Architect lean spec (Q6 ratification pending):**

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

**Contract:**
- Values are EMPTY (operator fills in) — NO leaked secrets per P0.S6 discipline
- All env vars that `core/config.py` reads via `os.getenv(...)` are documented
- File NAME is `.env.example` (matches existing convention; `.env` is gitignored)

### D5 — Test surface

**Edit site:** NEW `tests/test_p0_r4_process_supervisor.py` with 9 anchors (per §6 decomposed table).

**Contract:** structural file tests using Python's `configparser` (cross-platform; runs on Windows dev + Linux CI). No systemd-analyze verify dependency (Linux-only would gate tests on Linux). Verifies STRUCTURE not SEMANTIC (i.e., verifies the unit file is well-formed + has required directives; doesn't verify systemd would actually start the service — that's deployment-time verification).

---

## §3 — Cross-spec impact analysis (OUT-OF-SCOPE explicit)

**IN-SCOPE (P0.R4):**
- systemd unit file at `deploy/systemd/dog-ai.service` (D1)
- supervisord config at `deploy/supervisord/dog-ai.conf` (D2)
- Installation README at `deploy/README.md` (D3)
- Env file template at `deploy/dog-ai.env.example` (D4)
- Structural test surface at `tests/test_p0_r4_process_supervisor.py` (D5)

**OUT-OF-SCOPE (deferred to follow-up specs or rejected):**

| Concern | Disposition |
|---|---|
| Windows dev supervisor (NSSM / Task Scheduler / PowerShell scheduled task) | **P0.R4.X** follow-up candidate IF dev environment needs supervisor-managed runs; current Windows dev runs `python pipeline.py` direct from terminal |
| Auto-update / deployment automation (apt repo, CI/CD pipeline, ansible playbook) | **OUT-OF-SCOPE** — operator-driven installation per D3 README is sufficient for current scale |
| Service mesh / k8s pod spec | **REJECTED** — overkill for single-process robot runtime; Jetson AGX Orin runs single instance |
| systemd timer / cron for periodic restarts | **REJECTED** — anti-pattern; restart on crash, not scheduled restart (scheduled restart masks underlying issues) |
| Log rotation policy beyond supervisord's defaults | **OUT-OF-SCOPE** — operator-driven via logrotate per D3 README's troubleshooting section |
| Process resource limits (LimitNOFILE, MemoryMax) | **P0.R4.X** follow-up candidate IF empirical evidence shows resource exhaustion |
| systemd socket activation / inetd-style on-demand startup | **REJECTED** — pipeline.py is always-on cognitive runtime, not request-driven service |
| `Type=notify` with sd_notify integration | **REJECTED** — `Type=simple` is sufficient; sd_notify would require Python systemd bindings + add coupling without clear benefit |
| Pre-/Post-start scripts (e.g., camera device probe before start) | **OUT-OF-SCOPE** — pipeline.py's own boot-time validation (P0.S3 env_validation) is the contract; pre-start probe would duplicate |

---

## §4 — Pre-mortem (10 failure modes + mitigation per mode)

| # | Failure mode | Mitigation |
|---|---|---|
| 1 | systemd unit installed but ExecStart path wrong (e.g., wrong Python venv path) | Service fails on first start → StartLimitBurst exceeded within 60s → state=failed → operator sees `systemctl status` failure + journald log; D3 README troubleshooting names this case |
| 2 | EnvironmentFile path missing or unreadable | systemd treats as warning + continues; env vars empty → pipeline.py's P0.S3 env_validation raises `RuntimeError` at boot → exits → restart loop hits StartLimitBurst → state=failed |
| 3 | supervisord conf installed but Python path wrong | Service crashes at command exec → `startretries=10` consecutive failures → supervisord stops trying → operator sees `supervisorctl status` failure + log files |
| 4 | `/opt/dog-ai/` path doesn't exist | systemd `WorkingDirectory=` check fails before ExecStart → service stays in failed state; D3 README requires `/opt/dog-ai/` creation as install step |
| 5 | `dog-ai` user doesn't exist | systemd refuses to start service → `User=dog-ai` validation fails; D3 README requires `useradd -r -s /bin/false dog-ai` as install step |
| 6 | Camera/GPU not available at startup (USB camera unplugged or driver issue) | pipeline.py crashes early (probably during FaceDetector init) → restart loop hits StartLimitBurst within 60s; P0.R3 vision watchdog handles in-process recovery once running, but cold-start camera-missing is a process-supervisor concern |
| 7 | journald log volume balloons (verbose logging) | systemd `journalctl --vacuum-size=500M` or systemd-journald.conf `SystemMaxUse=500M` mitigates; D3 README troubleshooting names this |
| 8 | StartLimitBurst exceeded (5 attempts in 60s) → systemd holds in failed state | Operator must run `systemctl reset-failed dog-ai && systemctl start dog-ai`; documented in D3 README; NO automatic recovery — by design (prevent endless thrashing) |
| 9 | systemd `User=dog-ai` user doesn't have permission to access camera (/dev/video0) or GPU (/dev/nvidia0) | Add `dog-ai` to `video` + `render` groups during install (D3 README install step) OR use `Group=video,render` directive in unit file |
| 10 | Race between systemd start and network-online.target (API calls fail at startup before DNS ready) | Mitigated by `After=network-online.target` + `Wants=network-online.target` directives in [Unit] section; ensures systemd waits for network before starting |

---

## §5 — Multi-direction invariant trace per D-decision

**D1 invariants:**
- ↑ Upstream: requires `/opt/dog-ai/` directory + `dog-ai` user + `/etc/dog-ai/dog-ai.env` file (all D3 README install prerequisites)
- → Same-level: D1's `EnvironmentFile=` references the same env file that D4 templates
- ↓ Downstream: pipeline.py boots normally + P0.S3 env_validation passes when env file is correct

**D2 invariants:**
- ↑ Upstream: requires supervisord installed via apt/pip + parent environment has env vars set
- → Same-level: D2's `environment=` directive depends on parent shell environment (operator's responsibility per D3 README)
- ↓ Downstream: supervisord exponential backoff prevents thrashing on persistent failures

**D3 invariants:**
- ↑ Upstream: README assumes operator has root/sudo access + apt-installable systemd or supervisord
- → Same-level: README documents both D1 + D2 + D4 install steps
- ↓ Downstream: operator successfully completes install + service starts cleanly

**D4 invariants:**
- ↑ Upstream: env file template is committed to repo; `.env` (actual values) is gitignored
- → Same-level: env file template values are EMPTY (regex `r"^(KEY)=\s*$"` per A9 anchor)
- ↓ Downstream: operator copies template + fills in values; chmod 0600 per P0.S6 discipline

**D5 invariants:**
- ↑ Upstream: pytest discovers `tests/test_p0_r4_process_supervisor.py` per existing pytest.ini config
- → Same-level: 9 anchors each verify one structural property of D1-D4 artifacts
- ↓ Downstream: CI/local pytest run catches regression if any deploy artifact is modified incorrectly

---

## §6 — Q5 baseline estimation (architect lean: 9 anchors at exact mid; inclusive ±15% band per locked methodology)

**Architect lean: 9 anchors at exact mid 9; inclusive ±15% band [7.65, 10.35] → 8/9/10 all qualify ON-TARGET per locked methodology from P0.S5/B5/R2/R3.**

**Decomposed anchor table:**

| # | D | Anchor name | Type |
|---|---|---|---|
| A1 | D1 | `test_p0_r4_d1_anchor_1_systemd_unit_exists` | source-inspection: file exists at `deploy/systemd/dog-ai.service` + non-empty + configparser-parseable |
| A2 | D1 | `test_p0_r4_d1_anchor_2_systemd_unit_has_required_sections` | source-inspection: [Unit] + [Service] + [Install] sections present |
| A3 | D1 | `test_p0_r4_d1_anchor_3_systemd_restart_directives_present` | source-inspection: [Service] section has `Restart=on-failure` + `RestartSec=` + `StartLimitBurst=` + `StartLimitIntervalSec=` |
| A4 | D1 | `test_p0_r4_d1_anchor_4_systemd_environment_file_reference` | source-inspection: [Service] has `EnvironmentFile=` (NOT inline `Environment=` with secrets — P0.S6 compliance) |
| A5 | D2 | `test_p0_r4_d2_anchor_1_supervisord_conf_exists` | source-inspection: file exists at `deploy/supervisord/dog-ai.conf` + configparser-parseable |
| A6 | D2 | `test_p0_r4_d2_anchor_2_supervisord_program_section_has_autorestart` | source-inspection: `[program:dog-ai]` section has `autorestart=true` + `startretries=` + `startsecs=` (native exponential backoff config) |
| A7 | D3 | `test_p0_r4_d3_anchor_1_readme_exists_and_covers_both_supervisors` | source-inspection: file exists at `deploy/README.md` + contains `systemd` + `supervisord` install section headers + `systemctl` + `supervisorctl` command examples |
| A8 | D4 | `test_p0_r4_d4_anchor_1_env_template_exists_with_required_keys` | source-inspection: file exists at `deploy/dog-ai.env.example` + contains `TOGETHER_API_KEY=` + `HF_TOKEN=` entries |
| A9 | D4 | `test_p0_r4_d4_anchor_2_env_template_values_are_empty_per_p0s6` | source-inspection: regex `r"^(TOGETHER_API_KEY|HF_TOKEN)=\s*$"` matches both entries (NO leaked secret values — P0.S6 compliance) |

**Total: 9 logical anchors. 1:1 pytest-function-to-anchor mapping (no parametrize fan-out expected).**

**Inclusive ±15% band table (per locked methodology):**

| Closure-actual | Overage | Band | Doctrine impact |
|---|---|---|---|
| 6 | −33.3% | ≥30% FALSIFICATION | Doctrine demotes |
| 7 | −22.2% | ±15-30% SLIGHT-DRIFT-DOWN | Doctrine holds (watch trajectory) |
| **8** | **−11.1%** | **±15% ON-TARGET** | **Doctrine bumps 16 → 17** |
| **9** | **0.0%** | **±15% ON-TARGET (exact mid)** | **Doctrine bumps 16 → 17; 9+ consecutive 0% streak extends** |
| **10** | **+11.1%** | **±15% ON-TARGET** | **Doctrine bumps 16 → 17** |
| 11 | +22.2% | ±15-30% SLIGHT-DRIFT-UP | Doctrine holds (watch trajectory) |
| ≥12 | ≥+33% | FALSIFICATION | Doctrine demotes |

**Honest closure projection: closure-actual ∈ {8, 9, 10} ON-TARGET expected; 9 most likely if Plan v1 mirrors architect's anchor decomposition without consolidation.**

---

## §7 — Q5 LOCK (per inclusive ±15% locked methodology)

`### Phase-0-granular-decomposition-enables-accurate-estimates` bump expected at closure for closure-actual ∈ {8, 9, 10}; falsification clause active if closure-actual ∉ [7, 11].

---

## §8 — Open questions for auditor (architect leans explicit per locked discipline)

**Q1 — Path convention for deploy artifacts:**
- **(a)** `deploy/systemd/dog-ai.service` + `deploy/supervisord/dog-ai.conf` (group by SUPERVISOR — architect's preferred convention; supervisord is cross-platform so platform-grouping would conflate concerns)
- **(b)** `deploy/linux/systemd/dog-ai.service` + `deploy/linux/supervisord/dog-ai.conf` (group by PLATFORM — but supervisord is cross-platform, so the linux/ wrapper is misleading)
- **Architect lean: (a) supervisor-grouped paths.** Clean separation of concerns; matches "supervisor type" as the primary differentiator.

**Q2 — User context (production vs dev):**
- **(a)** Document `dog-ai` system user as the canonical service user; D3 README's install steps include `useradd -r -s /bin/false dog-ai`
- **(b)** Use current user (`jagannivas` on dev / `jetson` on Jetson default) — simpler but less hardened
- **Architect lean: (a) dedicated `dog-ai` system user.** Standard hardening practice; D3 README documents the `useradd` step + group memberships (`video`, `render`) needed for camera/GPU access.

**Q3 — Exponential backoff framing for systemd:**
- **(a)** Accept the discrepancy — supervisord natively supports exponential backoff; systemd uses bounded burst limit (`RestartSec=5` + `StartLimitBurst=5` + `StartLimitIntervalSec=60`). Document the difference in D3 README. Both supervisors satisfy the SPIRIT of the contract (prevent thrashing) via different mechanisms
- **(b)** Add a wrapper script (`deploy/bin/run-with-backoff.sh`) with explicit exponential sleep; systemd `ExecStart=` runs the wrapper instead of python directly
- **(c)** Document that "exponential backoff" applies to supervisord only; systemd's flat RestartSec is acceptable because crash thrashing is bounded by StartLimitBurst
- **Architect lean: (a) accept discrepancy with honest documentation.** Adding a wrapper script (b) introduces shell dependency + complexity for limited benefit. Both supervisors prevent thrashing; the mechanism differs but the user-visible outcome (process stays down after persistent failure) is the same. If auditor adjudicates "spirit-satisfied" as the precise framing, this banks `Pre-audit-quantifier-precision-refined-by-grep` 3rd instance.

**Q4 — Windows dev supervisor (IN-scope or P0.R4.X follow-up?):**
- **(a)** OUT-OF-SCOPE; Windows dev runs `python pipeline.py` direct from terminal; production-only deployment via systemd/supervisord on Jetson Linux
- **(b)** INCLUDE Windows NSSM config (`deploy/nssm/dog-ai.cmd`) for Windows dev/test environments
- **(c)** INCLUDE Windows Task Scheduler XML config
- **Architect lean: (a) OUT-OF-SCOPE; defer to P0.R4.X if Windows dev environment ever needs supervisor-managed runs.** Current dev workflow doesn't require it; adding Windows supervisor without empirical need is scope creep.

**Q5 — Anchor count (Q5 baseline estimation):**
- **Architect lean: 9 anchors at exact mid 9; inclusive ±15% band [7.65, 10.35] → 8/9/10 all qualify ON-TARGET per locked methodology.** No precedent inconsistency to surface; locked methodology from P0.R2/R3 closure-audit applies directly.

**Q6 — Env file path convention:**
- **(a)** `/etc/dog-ai/dog-ai.env` for systemd `EnvironmentFile=` (system-wide; matches `/etc/` convention; chmod 0600 + owned by `dog-ai` user)
- **(b)** `/opt/dog-ai/.env` (app-local alongside pipeline.py; gitignored)
- **(c)** Both — systemd uses `/etc/dog-ai/dog-ai.env`; supervisord uses parent shell env (no file path)
- **Architect lean: (c) split convention.** systemd: `/etc/dog-ai/dog-ai.env` (matches systemd EnvironmentFile= convention + standard /etc/ placement). supervisord: parent shell env (operator sets via shell export before invoking supervisord). Reduces coupling; each supervisor uses its native env mechanism.

**Q7 — Test surface approach:**
- **(a)** Pure configparser-based structural tests (cross-platform; runs on Windows dev + Linux CI; verifies file structure not systemd semantic)
- **(b)** systemd-analyze verify subprocess call (Linux-only; verifies systemd would actually accept the unit file)
- **(c)** Hybrid — configparser tests by default + optional `@pytest.mark.linux_systemd` for systemd-analyze tests
- **Architect lean: (a) pure configparser.** Cross-platform discipline matters more than systemd-semantic verification at unit-test stage; systemd semantic is verified at deployment time on Jetson per D3 README. Adding (b) gates a test on Linux availability — out of scope for the unit-test layer.

---

## §9 — `### Zero-precision-items-at-auditor-review` doctrine forecast

Architect's pre-emption budget at Phase 0: 4 Q-leans (Q1-Q4) + 1 secondary Q-lean (Q6) + 1 Q-lean (Q7) + Q5 anchor-count lock. Q3 carries a small risk surface (auditor may prefer (b) wrapper script for cleaner "exponential backoff" semantic; architect lean is (a) accept-discrepancy). Honest forecast: clean ratification of all 7 Q-leans most likely → 14 → 15 at Phase 0 surface.

If Q3 auditor adjudicates (b) wrapper script → escalates to Plan v2 for absorption (architect's lean (a) rejected). If Q3 ratifies (a) or (c) → Phase 0 fires doctrine cleanly.

`Zero-precision-items-pre-closure-predictions-blocked` candidate stays at 1 candidate / 2 sub-events historical (P0.R2 broke 2-cycle pattern; P0.R3 extended to 3 consecutive clean cycles; counter at 0). If P0.R4 Phase 0 + Plan v1 both fire clean, pattern-broken streak extends to 5 cycles (P0.R2 Plan v1 + P0.R3 Phase 0 + P0.R3 Plan v1 + P0.R4 Phase 0 + P0.R4 Plan v1).

---

## §10 — Architect's pre-Plan-v1 prediction (probabilistic per `Zero-precision-items-pre-closure-predictions-blocked` operational rule + Pass-2 grep formal rule extension)

Per the operational rule banked at P0.R1 closure handoff + PROMOTED to formal rule at P0.R3 Plan v1 verdict 2026-05-23: architect's pre-Plan-v1-review prediction should be PROBABILISTIC, not CONFIDENT. Auditor's independent Pass-2 verification may surface PI architect missed at proactive Pass-2 enumeration. Formal rule applies: auditor MUST run independent re-grep of architect's §1 enumeration before Plan v1 approval.

**Architect prediction (probabilistic):** "Phase 0 + Plan v1 SUBMITTED for auditor cross-check; expecting clean review per formal-rule extension validation across P0.R2 + P0.R3 + (now) P0.R4. Q3 carries the most risk (exponential backoff framing); if auditor prefers wrapper script over accept-discrepancy, cycle escalates to Plan v2. Otherwise: if cycle clears clean → 8th OPTIONAL-Plan-v2 proof case + extends pattern-broken streak from 3 → 5 cycles + formal rule extension's empirical track-record grows."

---

## §11 — Files this audit touches (Phase 0 zero-production-code rule)

**Pure documentation; ZERO production code changes at Phase 0:**

- `c:\Users\jagan\dog-ai\dog-ai\tests\p0_r4_process_supervisor_audit.md` — THIS FILE (NEW)

**Phase 1+ shipping (PER PLAN v1 LOCK; NOT in Phase 0 scope):**

- `deploy/systemd/dog-ai.service` — D1 NEW systemd unit
- `deploy/supervisord/dog-ai.conf` — D2 NEW supervisord config
- `deploy/README.md` — D3 NEW installation README
- `deploy/dog-ai.env.example` — D4 NEW env file template
- `tests/test_p0_r4_process_supervisor.py` — NEW file with 9 anchors (per §6 decomposed table)

**ZERO production code changes:**

- NO edits to `core/*.py`
- NO edits to `pipeline.py`
- NO edits to existing `tests/*.py` files
- NO edits to `core/config.py` (env vars already read via `os.getenv`; new env file template documents the existing contract)

---

## §12 — Verdict request

Forwarding to auditor for Phase 0 verdict. Expected verdict items:
1. Q1 adjudication (path convention)
2. Q2 adjudication (user context)
3. Q3 adjudication (exponential backoff framing — most-risk Q-lean)
4. Q4 adjudication (Windows dev supervisor scope)
5. Q5 anchor count lock (architect lean: 9 inclusive ±15%)
6. Q6 adjudication (env file path convention)
7. Q7 adjudication (test surface approach)
8. PI surfacing (if any) + non-blocking observations (if any)

**Banking events expected at Phase 0 verdict (closure-conditional):**
- `### Zero-precision-items-at-auditor-review` 14 → 15 IF auditor returns 0 PIs
- Twin-filename pitfall 18th preventive event ALREADY honored at audit drafting
- `Pre-audit-quantifier-precision-refined-by-grep` MAY bump 2 → 3 IF auditor adjudicates Q3 (a) accept-discrepancy framing as the precise "exponential backoff" reading
- `Zero-precision-items-pre-closure-predictions-blocked` counter stays at 0 (pattern-broken streak from P0.R2 onward); architect's probabilistic prediction per formal-rule extension

Architect closure commitment per `Explicit-closure-honest-count-commitment` discipline (already at 20 instances post-P0.R3): closure narrative will honor closure-actual count at closure-audit regardless of where it lands within the band table (§6). Doctrine integrity preserved across all 7 possible closure outcomes.

**Spec context note:** P0.R4 is materially distinct from prior P0.R cycles — NO Python production code changes; deployment artifacts only. Test surface is structural file tests via configparser (cross-platform); no behavioral tests. Cycle shape resembles P0.0 (CI scaffold landing) more than P0.R3 (cognitive runtime supervision).

---

End of P0.R4 Phase 0 audit.
