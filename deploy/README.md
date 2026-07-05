# karaos deployment guide

Process supervisor manifests + installation procedures for the karaos cognitive runtime. Two supervisors are supported: **systemd** (Linux production target, Jetson AGX Orin, Ubuntu hosts) and **supervisord** (cross-platform; Linux + Windows dev). Both deliver the P0.R4 contract: auto-restart on crash, structured log integration, P0.S6 secrets discipline via external env file.

See `rule book/cycle-specs/p0_r4_process_supervisor_audit.md` + `p0_r4_process_supervisor_plan_v1.md` + `p0_r4_process_supervisor_plan_v2.md` for the architecture decisions behind this layout.

---

## section 1: systemd installation (production)

1. **Copy the unit file** to the system unit directory:

   ```bash
   sudo cp deploy/systemd/karaos.service /etc/systemd/system/karaos.service
   ```

2. **Create the `karaos` system user** (no login, group memberships for camera + GPU access):

   ```bash
   sudo useradd -r -s /bin/false karaos
   sudo usermod -a -G video,render karaos
   ```

   `video` grants `/dev/video*` access (camera); `render` grants `/dev/dri/*` access (GPU compute on Jetson + NVIDIA hosts).

3. **Create the env file** with chmod 0600 (P0.S6 secrets compliance, only `karaos` user can read):

   ```bash
   sudo install -d -m 0700 -o karaos -g karaos /etc/karaos
   sudo cp deploy/karaos.env.example /etc/karaos/karaos.env
   sudo chown karaos:karaos /etc/karaos/karaos.env
   sudo chmod 0600 /etc/karaos/karaos.env
   sudo nano /etc/karaos/karaos.env # fill in TOGETHER_API_KEY + any optional keys
   ```

4. **Reload systemd + enable + start** the service:

   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now karaos
   ```

5. **Verify the service is running**:

   ```bash
   sudo systemctl status karaos
   sudo journalctl -u karaos -f
   ```

---

## section 2: supervisord installation (cross-platform alternative)

1. **Install supervisord** (Python `supervisor` package or distro repo):

   ```bash
   # Option A: pip (in a venv that supervisord will run as)
   pip install supervisor

   # Option B: apt (Debian / Ubuntu)
   sudo apt install supervisor
   ```

2. **Copy the config** to supervisord's include directory (path varies by install, typical locations below):

   ```bash
   # apt install
   sudo cp deploy/supervisord/karaos.conf /etc/supervisor/conf.d/karaos.conf

   # pip install (custom location — adjust to your supervisord.conf includes)
   cp deploy/supervisord/karaos.conf /etc/supervisord.d/karaos.conf
   ```

3. **Set env vars in the parent shell** that launches supervisord (supervisord's `environment=` directive uses `%(ENV_X)s` interpolation from supervisord's own environment, see `core/config.py` for the full list; minimum is `TOGETHER_API_KEY`):

   ```bash
   export TOGETHER_API_KEY="sk-..."
   export HF_TOKEN="hf_..." # optional — inherited by supervisord children; NOT named in environment= (that would make it structurally required)
   export GROQ_API_KEY="gsk_..." # optional — alternate LLM provider
   export TAVILY_API_KEY="tvly-..." # load-bearing for search_web tool
   ```

4. **Reread + add the new program**:

   ```bash
   supervisorctl reread
   supervisorctl add karaos
   supervisorctl status karaos
   ```

---

## section 3: env file template usage

`deploy/karaos.env.example` is the canonical template. Copy it to the supervisor-appropriate location (`/etc/karaos/karaos.env` for systemd; parent shell env for supervisord) and fill in values.

**P0.S6 discipline:** the committed template has EMPTY values for all 4 secret-class env vars. The deployed copy MUST have chmod 0600 ownership restricted to the karaos user. NEVER commit a populated env file to git.

**All 4 secret-class env vars + runtime impact** (per Plan v2 section 2.3 minor note):

| Variable | Required? | Runtime impact when missing |
|---|---|---|
| `TOGETHER_API_KEY` | **Required** | Pipeline boot fails per `core/env_validation.py` (P0.S3). Together.ai is the primary LLM provider for chat + extraction + embeddings. |
| `HF_TOKEN` | Optional | pyannote diarization-3.1 falls back to ECAPA-valley legacy backend (Session 39 fallback path). Multi-speaker scenes degrade gracefully; single-speaker unaffected. |
| `GROQ_API_KEY` | Optional | Used by alternate LLM provider paths if configured; falls back to `TOGETHER_API_KEY` otherwise. No degradation when absent + Together is healthy. |
| `TAVILY_API_KEY` | Optional but load-bearing | `search_web` LLM tool returns auth-failure at runtime. Brain can't answer live-data queries ("weather today", "latest news"). Tool description (Session 30 lineage) instructs LLM to fall back to training knowledge OR honestly acknowledge the network failure. |

A8 programmatic enforcement (`tests/test_p0_r4_process_supervisor.py`) asserts every `os.getenv(...)` key in `core/config.py` appears in this template, future env-var additions automatically caught at CI.

---

## section 4: verification commands

```bash
# systemd
sudo systemctl status karaos
sudo journalctl -u karaos -f
sudo journalctl -u karaos --since "1 hour ago"

# supervisord
supervisorctl status karaos
supervisorctl tail -f karaos stdout
supervisorctl tail -f karaos stderr
```

Expected output on healthy boot: `[Pipeline] All systems ready. Watching...` within ~15s of service start.

---

## section 5: troubleshooting

**Common failure modes:**

- **Missing env file**: systemd reports `Failed at step EXEC` or `karaos.env: No such file`. Verify `/etc/karaos/karaos.env` exists + has correct ownership/mode.
- **Wrong permissions**: systemd reports `Permission denied` reading env file. Verify `chmod 0600` + `chown karaos:karaos`.
- **Camera access denied**: pipeline boot fails with `cv2.VideoCapture` error. Verify `karaos` user is in the `video` group + camera device exists (`ls -l /dev/video*`).
- **GPU access denied**: CUDA init fails. Verify `karaos` user is in the `render` group + NVIDIA driver loaded.
- **`StartLimitBurst` exceeded** (systemd): 5 restart attempts in 60s failed to service holds at `failed` state for operator intervention. Recovery:

   ```bash
   sudo systemctl reset-failed karaos
   sudo systemctl start karaos
   ```

- **TOGETHER_API_KEY invalid**: pipeline boot fails per P0.S3 env validation with actionable error. Verify the key at https://api.together.xyz/settings/api-keys.
- **HuggingFace gated-model 401** (pyannote): pipeline boots but logs `[Voice] pyannote unavailable` + falls back to ECAPA-valley. Accept the diarization-3.1 license at https://huggingface.co/pyannote/speaker-diarization-3.1.

---

## section 6: supervisor comparison table

| Aspect | systemd | supervisord |
|---|---|---|
| Platform | Linux only (most distros + Jetson) | Cross-platform (Linux + Windows + macOS via Python) |
| Auto-restart mechanism | **Bounded burst limit**, `Restart=on-failure` + `RestartSec=5s` + `StartLimitBurst=5` + `StartLimitIntervalSec=60s`. After 5 failures in 60s, service holds at `failed` state for operator intervention. | **Native exponential backoff**, `autorestart=true` + `startretries=10`. Delays grow on consecutive failures up to ~2 min. Caps at 10 attempts. |
| Log integration | journald (`journalctl -u karaos`) + console | Rotated text files (`/var/log/karaos/stdout.log` + `stderr.log`; 10MB × 5 backups) |
| Env file mechanism | `EnvironmentFile=/etc/karaos/karaos.env` (file-based, P0.S6 compliant) | `environment=` directive with `%(ENV_X)s` interpolation from parent shell |
| Graceful shutdown | SIGTERM to 90s timeout | SIGINT (`stopsignal=INT`) to 30s timeout (`stopwaitsecs=30`) for pipeline.py's SIGINT handler |
| Recommended for | Production Linux hosts + Jetson AGX Orin | Cross-platform dev environments + Windows hosts |

**On the backoff discrepancy (per Phase 0 Q3 verdict 2026-05-23):** systemd's bounded burst limit and supervisord's native exponential backoff differ as implementations but both honor the same spec contract, prevent thrashing on a permanently-failing process while still recovering from transient crashes. Each supervisor uses its native mechanism rather than re-implementing the other's. Documented honestly per `### Spec-contracts-not-implementations` discipline.
