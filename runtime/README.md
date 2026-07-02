# runtime/ — the engine/app seam

The middle layer of the P1.A1 decomposition of the former 9k-line `pipeline.py` monolith. **Layering direction (AST-enforced): `flows/` → `runtime/` → `core/` — nothing here imports `pipeline`.** `pipeline.py` re-exports these symbols so the historical import surface and the test suite stay byte-compatible.

| Module | What it holds (relocated VERBATIM from pipeline.py) |
|---|---|
| `wiring.py` | the shared mutable runtime state: store singletons, orchestrator/db references, module-level task handles |
| `session.py` | session lifecycle helpers (`_open_session`/`_close_session` machinery, `_is_disputed`, expiry) |
| `vision_loop.py` | the background vision loop (detect → track → recognize → stores) |
| `background_loops.py` | the supervised loops: watchdogs (vision, heavy-worker, audio-device), cloud retry, dream, health |
| `context_blocks.py` | prompt context assembly (scene/room/shared-context block builders) |
| `identity_cache.py` | best-friend + identity caches with invalidation hooks |
| `boot_checks.py` | startup assertions (privilege-table coverage, env validation ordering) |
| `state_enums.py` | `PipelineState` / `CloudState` |
| `text.py` | text utilities (NFKC helpers, gate predicates) |
| `log_capture.py` | terminal log capture/archive (spawn-safe, guarded from subprocess re-import) |

The relocation was mechanical-extraction-only (no behavior edits), locked by golden tests and the full suite at each step. `flows/companion/` builds on top of this layer; a future `flows/<profile>.py` per the SB.9 design selects choreography per deployment.
