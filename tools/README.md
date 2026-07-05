# tools/: operator & maintenance CLIs

Standalone scripts run by a human, never imported by the pipeline.

| Tool | What it does | Safety shape |
|---|---|---|
| `factory_reset.py` | Standalone factory reset: wipes faces.db / brain.db / FAISS / Kuzu / photos, prints a verified post-wipe summary (probes what was ACTUALLY deleted, not what was attempted) | **Dry-run by default**, lists targets without acting; `--confirm` to wipe; preserves the dashboard auth token unless `--include-dashboard-token`; refuses to run while the pipeline is live (state.json heartbeat check, `--force` to override). Exit codes 0/1/2/3 |
| `replay_session.py` | Read-only replay of the append-only event log (`python tools/replay_session.py --session X --type tool_call --since ... --limit N`), renders events with parent-chain trees for post-mortem debugging | Opens the DB in read-only URI mode; zero side effects on a live pipeline |
| `add_spdx_headers.py` | Idempotent SPDX license-header applier (AST-position-aware, inserts after module docstrings; vendored trees excluded via `EXCLUDED_PATHS`) | Re-running reports `Added: 0` when clean; the exclusion set is CI-locked |

Related but living elsewhere: `enroll.py`, `delete_person.py`, `audit_person.py`, `repair_gallery.py` at repo root (person lifecycle CLIs); `bench/perception` (the eval harness); `tests/eval_weekly.py` (classifier drift report).
