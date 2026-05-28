# Kara-OS Architecture Reference

This directory contains the full architecture reference for Kara-OS, split into 19 chapters that match the original `everything_about_system.md` section numbering.

> **Stability invariant** (Pre-P1 Bundle 1 Plan v2 §1.6): every H2 section `§NN` (1 ≤ N ≤ 340) lives in exactly one chapter file. A reader following `docs/architecture/CHAPTER_NN §59` finds the same content as the original `everything_about_system.md §59`. Mechanical-extraction split — section bodies are byte-identical to the source.

The root `everything_about_system.md` file is now a thin redirect; do not write content there.

---

## Chapters

| # | File | Sections | Topic |
|---|---|---|---|
| 01 | [CHAPTER_01_introduction_and_tech_stack.md](CHAPTER_01_introduction_and_tech_stack.md) | §1-§9 | What Kara-OS is, philosophy, system architecture, runtime environment, tech stack, performance budget, directory layout |
| 02 | [CHAPTER_02_lifecycle_and_pipeline_states.md](CHAPTER_02_lifecycle_and_pipeline_states.md) | §10-§15 | First boot, daily flow, shutdown, factory reset, pipeline states, main event loop |
| 03 | [CHAPTER_03_async_and_vision_basics.md](CHAPTER_03_async_and_vision_basics.md) | §16-§29 | Async architecture, scene heartbeat, RetinaFace, SORT, AdaFace, face quality gates, anti-spoof, lip tracking, mic, VAD |
| 04 | [CHAPTER_04_audio_and_stt_tts.md](CHAPTER_04_audio_and_stt_tts.md) | §30-§35 | Smart-Turn, echo skip, Whisper, within-utterance diarization, Kokoro/Piper, sentence streaming |
| 05 | [CHAPTER_05_face_voice_galleries.md](CHAPTER_05_face_voice_galleries.md) | §36-§46 | FaceDB + FAISS, recognition, ECAPA-TDNN, voice gallery, self-update, pruning |
| 06 | [CHAPTER_06_sessions_and_evidence.md](CHAPTER_06_sessions_and_evidence.md) | §47-§58 | `_active_sessions`, `person_type`, open/close, expiry, primary selection, evidence dataclass, single-writer invariant |
| 07 | [CHAPTER_07_reconciler_and_conversation_turn.md](CHAPTER_07_reconciler_and_conversation_turn.md) | §59-§71 | Reconciler cascade, routing thresholds, scene block, stranger workflow, conversation_turn anatomy |
| 08 | [CHAPTER_08_prompt_blocks_and_brain_agents.md](CHAPTER_08_prompt_blocks_and_brain_agents.md) | §72-§99 | Eight prompt blocks, brain.db schema, 14 agents, dream loop |
| 09 | [CHAPTER_09_dispute_tool_privileges_logging.md](CHAPTER_09_dispute_tool_privileges_logging.md) | §100-§118 | Uncle incident, disputed state, `TOOL_PRIVILEGES`, `log_utils`, anti-spoof summary |
| 10 | [CHAPTER_10_schemas_tests_dashboard.md](CHAPTER_10_schemas_tests_dashboard.md) | §119-§140b | faces.db schema, brain.db schema, FAISS layout, Kuzu schema, state.json IPC, tests, dashboard architecture |
| 11 | [CHAPTER_11_future_work_reference_tables.md](CHAPTER_11_future_work_reference_tables.md) | §141-§149 | ReSpeaker, Jetson, openWakeWord, `robot.py`, glossary, config table, tool schemas, session history |
| 12 | [CHAPTER_12_privacy_rooms_recent_work.md](CHAPTER_12_privacy_rooms_recent_work.md) | §150-§176 | Four-tier privacy model, visibility clause, owner access model, room block, turn arbitration, session-end synthesis |
| 13 | [CHAPTER_13_observability_evolution_plans_pyannote.md](CHAPTER_13_observability_evolution_plans_pyannote.md) | §177-§197 | Observability 2.0, pre-3B hardening, Phase 4/5 placeholders, pyannote dependency maintenance |
| 14 | [CHAPTER_14_voice_vision_independence_pure_graph_classifier.md](CHAPTER_14_voice_vision_independence_pure_graph_classifier.md) | §198-§214 | `voice_channel.py`/`vision_channel.py` split, 22-rule reconciler, pure-graph intent classifier (Specs 1+2) |
| 15 | [CHAPTER_15_external_benchmarks_multilayer_architecture.md](CHAPTER_15_external_benchmarks_multilayer_architecture.md) | §215-§232 | Friends benchmark, Bhagtani et al. paper, multi-backbone falsifying experiment, six-layer classifier architecture plan |
| 16 | [CHAPTER_16_p0_correctness_store_session_migrations.md](CHAPTER_16_p0_correctness_store_session_migrations.md) | §233-§270 | P0.1-P0.X correctness hardening, silent-except audit, cross-storage atomicity, Store-pattern migration, typed session state |
| 17 | [CHAPTER_17_p0_timeout_schema_router_concurrency_property.md](CHAPTER_17_p0_timeout_schema_router_concurrency_property.md) | §271-§299 | P0.8 per-tool timeout, P0.9 schema migrations versioning, P0.10 legacy router deletion, P0.11 state race, P0.12 JSON parser hardening |
| 18 | [CHAPTER_18_observability_ci_event_log.md](CHAPTER_18_observability_ci_event_log.md) | §300-§321 | Health and disk observability, memory consolidation, tiered CI scaffold, event log + replay harness |
| 19 | [CHAPTER_19_architectural_disciplines_upcoming_work.md](CHAPTER_19_architectural_disciplines_upcoming_work.md) | §322-§340 | Named architectural disciplines (induction, architect-reads-production-code, etc.) plus upcoming work and roadmap |

---

## Cross-section navigation

| §NN range | Chapter |
|---|---|
| §1-§9 | [01](CHAPTER_01_introduction_and_tech_stack.md) |
| §10-§15 | [02](CHAPTER_02_lifecycle_and_pipeline_states.md) |
| §16-§29 | [03](CHAPTER_03_async_and_vision_basics.md) |
| §30-§35 | [04](CHAPTER_04_audio_and_stt_tts.md) |
| §36-§46 | [05](CHAPTER_05_face_voice_galleries.md) |
| §47-§58 | [06](CHAPTER_06_sessions_and_evidence.md) |
| §59-§71 | [07](CHAPTER_07_reconciler_and_conversation_turn.md) |
| §72-§99 | [08](CHAPTER_08_prompt_blocks_and_brain_agents.md) |
| §100-§118 | [09](CHAPTER_09_dispute_tool_privileges_logging.md) |
| §119-§140b | [10](CHAPTER_10_schemas_tests_dashboard.md) |
| §141-§149 | [11](CHAPTER_11_future_work_reference_tables.md) |
| §150-§176 | [12](CHAPTER_12_privacy_rooms_recent_work.md) |
| §177-§197 | [13](CHAPTER_13_observability_evolution_plans_pyannote.md) |
| §198-§214 | [14](CHAPTER_14_voice_vision_independence_pure_graph_classifier.md) |
| §215-§232 | [15](CHAPTER_15_external_benchmarks_multilayer_architecture.md) |
| §233-§270 | [16](CHAPTER_16_p0_correctness_store_session_migrations.md) |
| §271-§299 | [17](CHAPTER_17_p0_timeout_schema_router_concurrency_property.md) |
| §300-§321 | [18](CHAPTER_18_observability_ci_event_log.md) |
| §322-§340 | [19](CHAPTER_19_architectural_disciplines_upcoming_work.md) |

If you need to update the architecture documentation, edit the appropriate chapter file directly. Do not write to `everything_about_system.md` (it is a thin redirect now).
