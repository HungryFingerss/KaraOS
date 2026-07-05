# Coverage Campaign to 100%

Goal (Jagan 2026-07-05): **100% real coverage of the production codebase**, defined
as every line either exercised by a real test or carrying an inline
`# pragma: no cover` with a written reason. No padding, no lowered bars.

- **Scope:** all production `.py` (core/, runtime/, flows/, profiles/, persona/,
  tools/, pipeline.py + the root CLIs). **Excluded** (see `.coveragerc`): vendored
  `core/_florence2` + `core/_minifasnet`, one-shot `bootstrap/`, and tests.
- **Baseline (2026-07-05):** ~68% on the in-scope code (~4,700 lines to cover).
- **Ratchet:** as each module reaches 100%, it joins the enforced `--cov=` set in
  `slow.yml` and the floor bumps toward 100. Locked so nothing regresses. (The
  slow.yml floor bump is a dedicated step, done once a critical mass is locked.)

**Progress — 2026-07-05 session: 18 modules to 100%** (~140 new tests, 3 batches
committed): sort, log_utils, sanitize, voice_channel, vision_provider_state,
vision_frame_store, config, env_validation, session_state, embedding, triage,
privacy, routine, turn_flows, persona_loader, boot_checks, conversation_store,
pipeline_state_store. Justified pragmas: config (2 fail-loud guards on hardcoded
constants), routine (2 unreachable StatisticsError handlers).

Measure locally:
```
venv/Scripts/python.exe -m pytest --ignore=tests/test_brain_json_parser_hypothesis.py \
  --cov=<module> --cov-report=term-missing -q -p no:cacheprovider
```

## Status by module (baseline %; ✅ = 100% + in the enforced floor)

### Already at 100% (lock into the floor as we ratchet)
reconciler · reconciler_state · cache_store · presence · track_store · voice_gallery ·
per_person_agent · anti_spoof_rejection · store_base · pipeline_invariants · audit ·
event_log/types · event_log/__init__ · brain_agent/{__init__,context} · memory/__init__ ·
persona/{__init__,_schema} · profiles/{__init__,_schema,_blocks,_registry} ·
runtime/{__init__,identity_cache,state_enums,wiring} · flows/{__init__,companion/__init__}

### Quick closes (1-16 lines from 100%, pure logic)
| module | base | miss | status |
|---|---|---|---|
| core/config.py | 99% | 2 | ✅ 100% (2 fail-loud guards on hardcoded constants pragma'd) |
| core/sanitize.py | 94% | 1 | ✅ 100% (test_sanitize_coverage.py) |
| core/log_utils.py | 92% | 1 | ✅ 100% (test_log_utils.py) |
| core/env_validation.py | 92% | 1 | ✅ 100% (test_env_validation_coverage.py) |
| core/session_state.py | 97% | 9 | ✅ 100% (test_session_state_setters_coverage.py) |
| brain_agent/agents/embedding.py | 98% | 1 | ✅ 100% (test_agents_embedding_triage_coverage.py) |
| brain_agent/agents/triage.py | 96% | 1 | ✅ 100% (same file) |
| brain_agent/privacy.py | 94% | 3 | ✅ 100% (test_privacy_coverage.py) |
| brain_agent/agents/routine.py | 86% | 6 | ✅ 100% (test_routine_coverage.py; 2 unreachable StatisticsError handlers pragma'd) |
| flows/companion/turn_flows.py | 98% | 1 | ✅ 100% (test_turn_flows_coverage.py) |
| runtime/text.py | 96% | 4 | |
| core/vision_provider_state.py | 86% | 7 | ✅ 100% (test_vision_provider_state_coverage.py) |
| core/voice_channel.py | 90% | 5 | ✅ 100% (test_voice_channel_coverage.py) |
| core/vision_frame_store.py | 85% | 5 | ✅ 100% (test_vision_frame_store_coverage.py) |
| core/schema_migrations.py | 90% | 7 | (next: 205-214 testable; 322-328 defensive rollback re-raise) |
| core/persona_loader.py | 87% | 6 | ✅ 100% (test_persona_loader_coverage.py) |
| core/conversation_store.py | 83% | 14 | ✅ 100% (test_conversation_store_coverage.py) |
| core/pipeline_state_store.py | 90% | 16 | ✅ 100% (test_pipeline_state_store_coverage.py) |

### Pure-logic long poles (0% / low, no hardware — high value)
| module | base | miss | status |
|---|---|---|---|
| **core/sort.py** | **0%** | 118 | ✅ 100% (test_sort.py, 25 tests) |
| runtime/boot_checks.py | 0% | 37 | ✅ 100% (test_boot_checks_coverage.py) |
| core/classifier_graph.py | 62% | 143 | |
| core/abstraction.py | 68% | 29 | |

### Hardware-mockable (mock the device boundary, pragma the device call)
| module | base | miss | status |
|---|---|---|---|
| core/vision.py | 51% | 225 | |
| core/voice.py | 51% | 74 | |
| core/audio.py | 49% | 228 | |
| core/heavy_worker.py | 45% | 150 | |
| runtime/vision_loop.py | 56% | 158 | |
| enroll.py | 15% | 67 | (camera CLI) |

### Mid-range (real tests, some mocking)
brain.py 69% · orchestrator.py 69% · db.py 84% · memory/store.py 84% ·
health.py 76% · classifier_db.py 79% · dashboard_token.py 69% · producer.py 73% ·
runtime/session.py 84% · runtime/background_loops.py 61% · runtime/log_capture.py 59% ·
runtime/context_blocks.py 85% · room_orchestrator.py 91% · flows/companion/tools.py 84% ·
{brain,faces}_db_migrations 84-85% · crash_logs 79% · emotion 77% · state 74% ·
disk_monitor 74% · object_detection 73% · _llm 77% · backup 84% · profile_loader 83% ·
vision_channel 82% · graph 89% · agents/{briefing 25%, social 31%, nudge 41%,
household 62%, contradiction 61%, prefs 67%, schema 77%, extraction 78%, watchdog 65%}

### The monolith (sequence AFTER P1.A1 decomposition — flag before touching)
| module | base | miss |
|---|---|---|
| pipeline.py | 35% | 1,272 |

### Tools (lower priority)
tools/add_spdx_headers.py 0% · tools/replay_session.py 59% · tools/factory_reset.py 85%
