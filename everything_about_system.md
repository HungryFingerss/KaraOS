# Kara-OS — Complete System Documentation

> **Purpose.** This document is the definitive technical description of the Kara-OS system. It is written so that a competent engineer with no prior exposure to the project could read it linearly, understand not just *what* the code does but *why it is shaped that way*, and be able to rebuild the system from scratch with equivalent behaviour.
>
> **Audience.** Future contributors (including future-you), auditors, and anyone trying to understand why a specific threshold is 0.45 and not 0.5, why we gate anti-spoof at site X and not site Y, or what the knock-on effects of raising `N_INITIAL_VOICE_BOOTSTRAP` would be.
>
> **Style.** Each section tries to answer four questions in order:
>   1. **What** — what the component is, what its inputs and outputs are.
>   2. **Why** — what problem it solves, what happens if we remove it.
>   3. **How** — the algorithm, state, and data flow.
>   4. **Why this way** — the alternatives we rejected, the incidents that shaped the current design, the invariants we now guard.
>
> **Last updated**: 2026-05-18 (post-P0.0.7; event-sourcing foundation shipped; full P0 correctness + architectural-hardening cycle closed; spec-first review cycle formalised as a named architectural discipline; locked sequence into P0 security, P0 robustness, and P1.A pipeline.py decomposition next)
> **Codebase**: ~24,000 lines of Python + 1000+ lines Next.js dashboard
> **Tests**: ~2302 passing, 9 xfailed, 4 skipped, 0 failed, 0 errors (asyncio_mode=auto)
> **Runtime target**: Windows 11 dev laptop (now) → Jetson AGX Orin 32GB (production)
>
> ---
>
> **What changed since the 2026-05-02 revision (Session 122):**
>
> Two and a half weeks of disciplined architectural-hardening work between the 2026-05-02 voice/vision-cutover revision and this one. The system did not get more features. It got dramatically more *structural protection*. Every load-bearing property that previously lived in developer discipline is now CI-enforced by AST scans, paired-write inverse checks, or behavioural invariants. The arc:
>
> - **P0 correctness hardening (P0.1 – P0.3 + P0.13).** Five distinct privilege/correctness regressions surfaced by live canaries (`disputed`-string comparison drift, `prior_person_type` defaulting to `"known"` instead of `"stranger"`, multi-word names mis-rejected on a substring check, repeat-guard bypassed in proactive paths). Each fix shipped with an AST-scan structural invariant that prevents the regression class returning silently. See new **Part XXXVI**.
> - **The silent-except audit (P0.4).** Project-wide AST audit of every `except (Exception|BaseException|bare): pass` handler in production source. 22 sites surfaced, all annotated with one of `# RACE:`, `# CLEANUP:`, `# OPTIONAL:` or fixed outright. `tests/test_silent_except_invariant.py` now rejects any unannotated silent-pass-only handler at PR time. The discovery that 22 sites existed when reactive patching had previously found only ~7 became the empirical foundation of the **structured-audit-vs-reactive-patching** lesson banked in §233. See new **Part XXXVII**.
> - **Cross-storage atomicity (P0.5 + P0.X).** FAISS ↔ faces.db and Kuzu ↔ brain.db paired-write hardening. SQL-first transactional ordering + sentinel files + boot reconciliation + per-storage `_X_degraded` fallback flags. Three Kuzu write patterns codified (`SCHEMA_MIGRATION` / `RAISE` / `SWALLOW`) with AST detectors per pattern. The **inverse-check discipline** — every enumerated method tuple has a corresponding AST scan asserting the tuple contains every method matching the pattern — was born here when `prune_outlier_embeddings` was caught as a hidden paired-write site. See new **Part XXXVIII**.
> - **The Store-pattern migration (P0.6).** 28 module-level globals in `pipeline.py` retired in favour of 8 typed `Store` classes (`PresenceStore`, `TrackStore`, `ConversationStore`, `VoiceGalleryStore`, `PerPersonAgentStore`, `CacheStore`, `PipelineStateStore`, `VisionFrameStore`). Every store has named async mutators + sync `peek_*` reads + an autouse-fixture-reset between tests + a structural ratchet capping the number of legacy module-globals at 0. Three architectural discoveries from the closure audit (vision globals missed in v1, CacheStore touch-on-read LRU violating the locked spec, prior-state guard for cloud transitions) drove v2. See new **Part XXXIX**.
> - **Typed session state (P0.7).** `core/session_state.py` carries the new `Session` + `SessionSnapshot` + `VoiceEvidence` dataclasses and the `SessionStore` single-owner with `asyncio.Lock`. 21 named transition methods replaced ~190 direct-dict-mutation sites across `pipeline.py` and `test_pipeline.py`. Read-path migration + lifecycle write-path migration + final SHIM cleanup landed in 5 staged sub-PRs (P0.7.1 → P0.7.5). The dispute state machine (Part XV) now routes through `transition_to_disputed` + `clear_dispute` with `prior_person_type` capture. See new **Part XL**.
> - **Per-tool timeout protection (P0.8).** Every LLM-callable tool handler extracted from the if/elif chain into top-level `_handle_<tool>` functions registered in `_TOOL_HANDLERS`. `asyncio.wait_for` wraps the dispatch with per-tool budgets (default 10s; search_web 20s; search_memory 5s; rename 5s; shutdown 3s). Cancellation rolls back partial SQL writes via transaction `__aexit__`. P0.8.1 closed the gap that `search_web` was consumed inline in `ask_stream` and missing the wrap; P0.8.2 added F1 + F2 structural invariants making the handler-checkpoint discipline and retry-path one-shot guarantee AST-enforced. See new **Part XLI**.
> - **Schema migrations versioning (P0.9).** The versioned-ledger pattern that classifier_scenarios.db shipped under Spec 1 (Session 122) was generalised to faces.db and brain.db. Every historical schema mutation (19 retrofitted migrations across the two DBs) is now an entry in a `MIGRATIONS` list with a 5-tuple shape: `(version, description, apply_fn, verify_post_fn, verify_present_fn)`. `verify_post` is for the runner ("did the migration achieve its post-condition?"); `verify_present` is for bootstrap ("is the migration's effect already in place?"). The split was the **developer-improves-on-spec** moment for P0.9.2 — conflating them would have let bootstrap stamp `is_initial=1` on a partially-backfilled DB. See new **Part XLII**.
> - **Legacy router deletion + Bug-W closure (P0.10).** Phase 0 audit corrected the architect's premise: the new reconciler was *not* correct — it had a 0.3–0.5s coverage gap (the Bug-W class) that the legacy 273-line router was incidentally papering over via its catch-all `return cur_pid, "current"`. Phase 1 added `_p0_short_utterance_gap_hold_current` + a `LOWER_BOUND` attribute on every rule + a non-decreasing band-ordering invariant. Phase 2 deleted the legacy. P0.10.1 added the `EXPECTED_RULES_BY_BAND` structural invariant. Validation window opened with explicit gate criteria in `tests/p0_10_validation_runbook.md`. Net –15 tests but +40 architectural-coverage tests: a measurable coverage *increase* despite the raw-count drop because legacy-deletion shifts coverage from legacy-function tests to rule-cascade + invariant tests. See new **Part XLIII**.
> - **State race hardening (P0.11).** Preventive fix for a latent dict race in `core.state._persistent`. The race had never been observed in production (single writer, single startup), but three plausible activation conditions existed. The `_persistent[key] = value` in-place mutation was replaced with `_persistent = {**_persistent, key: value}` (atomic-replace; CPython `STORE_NAME` is GIL-atomic; concurrent readers see a consistent snapshot). Three deliberate-regression checks; the third one (external-module attribute-form injection) surfaced a detector gap that was closed in the same cycle. See new **Part XLIV**.
> - **Brain JSON parser hardening (P0.12 + P0.12.1).** Hypothesis property-based testing with `max_examples=1000` per test surfaced two real production bugs — `_parse_json` was returning non-dict valid JSON (silently breaking 7+ callers that did `.get(...)`), and `_parse_intent_sidecar` didn't catch Python 3.11+'s `ValueError` on oversized integer strings (DoS exposure). Fixed in the same sub-PR. P0.12.1's caller audit then found `SocialGraphAgent.extract`'s `isinstance(data, list)` branch had become unreachable after P0.12's narrowing — fixed by adding the sibling `_parse_json_array(raw) -> list | None`. See new **Part XLV**.
> - **Health and disk observability (Wave 5).** `core/health.py` emits a one-line system pulse every 5 minutes covering active sessions, person counts, embeddings, knowledge rows, classifier scenarios, cloud state, disputes, watchdog alerts, dream cadence, thin-voice galleries. `core/disk_monitor.py` watches `faces/`, `data/`, the project root and fires three-level idempotent alerts (warning at 80%, critical at 90%, blocker at 95%) via the WatchdogAgent. See new **Part XLVI**.
> - **Memory consolidation + conversation archival (Wave 6).** Hard-delete pruning of invalidated knowledge in the dream loop; SHA-256-keyed `_build_scene_block` cache to elide redundant rebuilds across turns when scene state is stable; `conversation_log` archival into `*_conversation_archive.db` companions via ATTACH-based atomic INSERT→DELETE; `load_conversation_history` + `search_conversation` UNION-merge across primary + archive. See new **Part XLVII**.
> - **Tiered CI scaffold + S2 deferral tripwire (P0.0 + P0.0.1 + P0.0.2).** Three GitHub Actions workflows landed (`fast.yml` every push + PR, target ≤5 min, skips slow+network+models markers; `slow.yml` nightly + manual, full suite with HF model cache and Together.ai key gating; `security.yml` weekly + on requirements.txt change, pip-audit + Trivy SARIF). `tests/test_dashboard_bind_tripwire.py` locks the S2 deferral premise (dashboard bound to `127.0.0.1`). P0.0.1 fixed the original tripwire's theatrical false-pass when `--hostname` was absent (Next.js defaults to `0.0.0.0`) — the empirical foundation of the **tripwires-must-match-the-actual-deferral-surface** discipline banked in §322. P0.0.2 bundled `@pytest.mark.xfail(strict=False, ...)` decorators on 8 infra-debt tests, with `test_xfail_decorators_align_with_allowlist` AST-scanning for half-fixes. See new **Part XLVIII**.
> - **Event Log + Replay Harness (P0.0.7).** Event-sourcing foundation shipped across 9 staged steps. `core/event_log/` package with 12 typed payload dataclasses, `NATURAL_PARENT_PAIRS` causal-chain registry, `_PAYLOAD_CLASSES` dispatch table, async/sync/swallowing producer functions. 11 producer hooks at 12 sites (D7 N=1 AST-enforced exactly-one-producer-per-event-type). brain.db migration `_m_0012` at version 12 (P0.9 5-tuple shape). Read-only replay CLI at `tools/replay_session.py`. 4 reusable scenario fixtures and 5 smoke tests in `tests/fixtures/event_log_fixtures.py` + `tests/test_event_log_replay.py`. Health-log integration via `event_log_drops` and `event_log_emit_failures` counters. The Step 5 polish (developer-improves-on-spec 5th instance) consolidated 12 per-call-site try/except blocks into one `safe_emit_sync` helper with a single `# OPTIONAL:` annotated except. See new **Part XLIX**.
> - **Architectural disciplines elevated to named doctrine.** Seven multi-instance patterns were promoted from informal practice to CLAUDE.md "Architectural Disciplines" section with explicit track records: induction-surfaces-invariant-gaps (7-for-7), spec-first review cycle (5-for-5), developer-improves-on-spec (5-for-5), spec-contracts-not-implementations (3-for-3), tripwires-must-match-deferral-surface (3-for-3), architect-reads-production-code-before-sign-off, verification-before-completion. Each cycle adds an instance to the appropriate count rather than reinventing the practice. See new **Part L**.
>
> The system is now in a different *engineering* regime than at the time of the previous revision: every load-bearing invariant is structurally enforced, every multi-day spec follows the Phase 0 audit → v1 plan → v2 plan → code phase cadence, every cross-storage paired-write site has an inverse-check guard, every silent-pass-only except block carries a rationale annotation, and every input crossing the runtime boundary emits a typed event into the event log for replay-based debugging. The next phase (P0 security, P0 robustness, and the P1.A pipeline.py decomposition) builds on this foundation rather than relitigating it. See **Part LI**.

---

## Table of Contents

### Part I — Foundations
1. [What Kara-OS Is](#1-what-Kara-OS-is)
2. [The Companion-Not-Assistant Philosophy](#2-the-companion-not-assistant-philosophy)
3. [System Architecture at Multiple Zoom Levels](#3-system-architecture-at-multiple-zoom-levels)
4. [Runtime Environment](#4-runtime-environment)
5. [Tech Stack and Why Each Piece](#5-tech-stack-and-why-each-piece)
6. [Performance Budget and Latency Targets](#6-performance-budget-and-latency-targets)
7. [Directory Layout and File Purpose](#7-directory-layout-and-file-purpose)

### Part II — Lifecycle
8. [Installation and First Run](#8-installation-and-first-run)
9. [Startup Sequence — Line by Line](#9-startup-sequence--line-by-line)
10. [First-Boot Flow — Enrolling the Best Friend](#10-first-boot-flow--enrolling-the-best-friend)
11. [Daily-Use Flow — Returning User](#11-daily-use-flow--returning-user)
12. [Shutdown — Graceful and Forced](#12-shutdown--graceful-and-forced)
13. [Factory Reset](#13-factory-reset)

### Part III — The Core Loop
14. [Pipeline States and Transitions](#14-pipeline-states-and-transitions)
15. [Main Event Loop Architecture](#15-main-event-loop-architecture)
16. [Async Architecture and Concurrency Model](#16-async-architecture-and-concurrency-model)
17. [Scene Heartbeat](#17-scene-heartbeat)
18. [Background Vision Loop](#18-background-vision-loop)
19. [Ambient Listening](#19-ambient-listening)

### Part IV — Vision
20. [RetinaFace Detection](#20-retinaface-detection)
21. [SORT Tracking with Kalman Filter](#21-sort-tracking-with-kalman-filter)
22. [AdaFace IR101 Embedding](#22-adaface-ir101-embedding)
23. [Face Quality Gates V1 through V4](#23-face-quality-gates-v1-through-v4)
24. [Anti-Spoofing — MiniFASNet Ensemble](#24-anti-spoofing--minifasnet-ensemble)
25. [Lip Tracking](#25-lip-tracking)
26. [Camera Reconnection](#26-camera-reconnection)

### Part V — Audio
27. [Microphone Capture](#27-microphone-capture)
28. [Voice Activity Detection — RMS vs Silero](#28-voice-activity-detection--rms-vs-silero)
29. [Pre-Roll Buffering](#29-pre-roll-buffering)
30. [Smart-Turn Neural End-of-Turn](#30-smart-turn-neural-end-of-turn)
31. [Echo Skip and Barge-In](#31-echo-skip-and-barge-in)
32. [Whisper STT](#32-whisper-stt)
33. [Within-Utterance Diarization](#33-within-utterance-diarization)
34. [Kokoro TTS and Piper Fallback](#34-kokoro-tts-and-piper-fallback)
35. [Sentence Streaming](#35-sentence-streaming)

### Part VI — Identity and Recognition
36. [FaceDB Architecture — SQLite Plus FAISS](#36-facedb-architecture--sqlite-plus-faiss)
37. [Embedding Storage and Diversity Gate](#37-embedding-storage-and-diversity-gate)
38. [Recognition with Adaptive Thresholds](#38-recognition-with-adaptive-thresholds)
39. [Temporal Embedding Buffer](#39-temporal-embedding-buffer)
40. [Gallery Poisoning Prevention](#40-gallery-poisoning-prevention)
41. [Gallery Audit and Repair](#41-gallery-audit-and-repair)

### Part VII — Voice and Speaker Identity
42. [ECAPA-TDNN Speaker Embedding](#42-ecapa-tdnn-speaker-embedding)
43. [Voice Gallery](#43-voice-gallery)
44. [Voice Identification](#44-voice-identification)
45. [Voice Self-Update](#45-voice-self-update)
46. [Stale Stranger Voice Pruning](#46-stale-stranger-voice-pruning)

### Part VIII — Session Management
47. [The `_active_sessions` Dictionary](#47-the-_active_sessions-dictionary)
48. [`person_type` Taxonomy](#48-person_type-taxonomy)
49. [`_open_session` Anatomy](#49-_open_session-anatomy)
50. [`_close_session` Cleanup](#50-_close_session-cleanup)
51. [Session Expiry Paths](#51-session-expiry-paths)
52. [Primary Person Selection](#52-primary-person-selection)

### Part IX — Identity Evidence
53. [The Evidence Dict](#53-the-evidence-dict)
54. [The Single-Writer Invariant](#54-the-single-writer-invariant)
55. [Path A / B / C Accumulation Policy](#55-path-a--b--c-accumulation-policy)
56. [Bootstrap Credits](#56-bootstrap-credits)
57. [DB-Hydrated Voice Sample Count](#57-db-hydrated-voice-sample-count)
58. [The `<<<IDENTITY EVIDENCE>>>` Brain Block](#58-the-identity-evidence-brain-block)

### Part X — Multi-Person Routing
59. [`_resolve_actual_speaker` Algorithm](#59-_resolve_actual_speaker-algorithm)
60. [Priorities 1 through 5 Breakdown](#60-priorities-1-through-5-breakdown)
61. [Adaptive Switch Threshold](#61-adaptive-switch-threshold)
62. [`_persons_in_frame` — Dual Source](#62-_persons_in_frame--dual-source)
63. [The `_face_in_frame` Helper](#63-the-_face_in_frame-helper)
64. [Scene Roster](#64-scene-roster)

### Part XI — Engagement Gate and Enrollment
65. [Stranger Workflow](#65-stranger-workflow)
66. [System-Name Phonetic Gate](#66-system-name-phonetic-gate)
67. [Progressive Enrollment](#67-progressive-enrollment)
68. [First-Boot Enrollment Flow](#68-first-boot-enrollment-flow)
69. [Background Enrollment](#69-background-enrollment)

### Part XII — Conversation Flow
70. [`conversation_turn` Anatomy](#70-conversation_turn-anatomy)
71. [System Prompt Composition](#71-system-prompt-composition)
72. [All Eight Prompt Blocks](#72-all-eight-prompt-blocks)
73. [Streaming Token Flow](#73-streaming-token-flow)
74. [Sentence Splitter](#74-sentence-splitter)
75. [Tool Dispatch](#75-tool-dispatch)
76. [History Management](#76-history-management)

### Part XIII — Brain / LLM
77. [Together.ai as Primary](#77-togetherai-as-primary)
78. [Ollama as Fallback](#78-ollama-as-fallback)
79. [CloudState Machine](#79-cloudstate-machine)
80. [The Six Function-Calling Tools](#80-the-six-function-calling-tools)
81. [Stream Truncation Handling](#81-stream-truncation-handling)
82. [Context Compression — Three Tiers](#82-context-compression--three-tiers)
83. [KAIROS Proactive Wake](#83-kairos-proactive-wake)

### Part XIV — Knowledge System
84. [BrainDB Schema](#84-braindb-schema)
85. [BrainOrchestrator](#85-brainorchestrator)
86. [TriageAgent](#86-triageagent)
87. [ExtractionAgent](#87-extractionagent)
88. [ContradictionAgent](#88-contradictionagent)
89. [EmbeddingAgent](#89-embeddingagent)
90. [GraphDB — Kuzu](#90-graphdb--kuzu)
91. [PromptPrefAgent](#91-promptprefagent)
92. [FrictionDetectionAgent](#92-frictiondetectionagent)
93. [HouseholdExtractionAgent](#93-householdextractionagent)
94. [PatternAnalysisAgent](#94-patternanalysisagent)
95. [NudgeAgent](#95-nudgeagent)
96. [SocialGraphAgent](#96-socialgraphagent)
97. [RetroScan](#97-retroscan)
98. [WatchdogAgent](#98-watchdogagent)
99. [InsightAgent](#99-insightagent)
100. [Dream Loop — Memory Consolidation](#100-dream-loop--memory-consolidation)

### Part XV — Dispute State Machine
101. [Origin — The Uncle-False-Match Incident](#101-origin--the-uncle-false-match-incident)
102. [Trigger Paths](#102-trigger-paths)
103. [`<<<IDENTITY DISPUTED>>>` Block](#103-identity-disputed-block)
104. [`_disputed_persons` Set](#104-_disputed_persons-set)
105. [Session-End and Conversation-Log Gating](#105-session-end-and-conversation-log-gating)
106. [Force-Close Timeout](#106-force-close-timeout)
107. [Dispute-Rename Burst Watchdog](#107-dispute-rename-burst-watchdog)

### Part XVI — Tool System
108. [`TOOL_PRIVILEGES` Table](#108-tool_privileges-table)
109. [`_tool_allowed` Fail-Closed](#109-_tool_allowed-fail-closed)
110. [Startup Assertion](#110-startup-assertion)
111. [`<<<TOOL ACCESS>>>` Block](#111-tool-access-block)
112. [History Override Semantics](#112-history-override-semantics)
113. [Tool Repeat Guard](#113-tool-repeat-guard)

### Part XVII — Observability
114. [log_utils — Single Source of Truth](#114-log_utils--single-source-of-truth)
115. [Seven Timestamped Categories](#115-seven-timestamped-categories)
116. [STT Elapsed Ms](#116-stt-elapsed-ms)
117. [Rolling Anti-Spoof Summary](#117-rolling-anti-spoof-summary)
118. [Scene Heartbeat Dedup](#118-scene-heartbeat-dedup)

### Part XVIII — Persistence
119. [faces.db Schema](#119-facesdb-schema)
120. [brain.db Schema](#120-braindb-schema)
121. [FAISS Index Layout](#121-faiss-index-layout)
122. [Kuzu Graph Schema v2](#122-kuzu-graph-schema-v2)
123. [state.json IPC Format](#123-statejson-ipc-format)
124. [Atomic Write Pattern](#124-atomic-write-pattern)

### Part XIX — Config System
125. [Single Source of Truth Invariant](#125-single-source-of-truth-invariant)
126. [Startup Assertions](#126-startup-assertions)
127. [Tuning Workflow](#127-tuning-workflow)

### Part XX — Testing
128. [822 Tests — Breakdown by File](#128-822-tests--breakdown-by-file)
129. [TDD Approach](#129-tdd-approach)
130. [Source-Inspection Tests](#130-source-inspection-tests)
131. [Async Test Pattern](#131-async-test-pattern)

### Part XXI — Dashboard
132. [Next.js Architecture](#132-nextjs-architecture)
133. [Real-Time State Read](#133-real-time-state-read)
134. [Enrollment Flow](#134-enrollment-flow)

### Part XXII — Design Philosophy and Invariants
135. [Brain Decides, Pipeline Enforces](#135-brain-decides-pipeline-enforces)
136. [No Hardcoded Magic Numbers](#136-no-hardcoded-magic-numbers)
137. [Fail-Closed on Security](#137-fail-closed-on-security)
138. [Single Source of Truth for Shared Helpers](#138-single-source-of-truth-for-shared-helpers)
139. [Tests Guard Every Invariant](#139-tests-guard-every-invariant)
140. [Observability at Every Latency-Critical Boundary](#140-observability-at-every-latency-critical-boundary)

### Part XXIII — Roadmap and Open Items
141. [ReSpeaker Barge-In](#141-respeaker-barge-in)
142. [Jetson Deployment Checklist](#142-jetson-deployment-checklist)
143. [openWakeWord Push-to-Talk](#143-openwakeword-push-to-talk)
144. [`robot.py` Hardware Abstraction](#144-robotpy-hardware-abstraction)
145. [Q3 — History Architecture Redesign](#145-q3--history-architecture-redesign)

### Part XXIV — Appendices
146. [Glossary](#146-glossary)
147. [Full Config Constant Table](#147-full-config-constant-table)
148. [Full Tool Schema Reference](#148-full-tool-schema-reference)
149. [Session History Timeline](#149-session-history-timeline)

### Part XXV — Cross-Person Privacy and Safety (Phase 3A)
150. [The Four-Tier Privacy Model](#150-the-four-tier-privacy-model)
151. [The Static Map and the Classifier](#151-the-static-map-and-the-classifier)
152. [`_visibility_clause` — The SQL Composer](#152-_visibility_clause--the-sql-composer)
153. [`query_knowledge_for` — Owner-Aware Retrieval](#153-query_knowledge_for--owner-aware-retrieval)
154. [The Owner-Access Model (3A.4.6 Simplification)](#154-the-owner-access-model-3a46-simplification)
155. [Write-Path Migration to Four Tiers (3A.4.5)](#155-write-path-migration-to-four-tiers-3a45)
156. [The `<<<CROSS-PERSON PRIVACY>>>` Block — Two Variants](#156-the-cross-person-privacy-block--two-variants)
157. [The `<<<VISITOR CONTEXT>>>` Block](#157-the-visitor-context-block)
158. [The `<<<STRANGER IDENTITY>>>` Block](#158-the-stranger-identity-block)
159. [Safety-Flag Preservation (Session 105 Bug N)](#159-safety-flag-preservation-session-105-bug-n)
160. [Visitor Alerts and the `safety_flags` Metadata](#160-visitor-alerts-and-the-safety_flags-metadata)
161. [The Lexi Canary — End-to-End Validation](#161-the-lexi-canary--end-to-end-validation)

### Part XXVI — Room Orchestration (Phase 3B)
162. [Why a Room Block Instead of Fragments](#162-why-a-room-block-instead-of-fragments)
163. [`_active_room_session` and the Room Lifecycle](#163-_active_room_session-and-the-room-lifecycle)
164. [`_build_room_block` Anatomy](#164-_build_room_block-anatomy)
165. [The `<<<ROOM>>>` Block Contents](#165-the-room-block-contents)
166. [The `<<<TURN ARBITRATION>>>` Rules](#166-the-turn-arbitration-rules)
167. [Silent-Skip on User-to-User Addressing](#167-silent-skip-on-user-to-user-addressing)
168. [LLM Turn Allocation via `[addressing:X]`](#168-llm-turn-allocation-via-addressingx)
169. [Batched Greeting Decision](#169-batched-greeting-decision)
170. [`search_room_memory` Tool](#170-search_room_memory-tool)
171. [Room-End Synthesis and `room_summaries`](#171-room-end-synthesis-and-room_summaries)
172. [The `<<<RECENT ROOMS>>>` Greeting Enrichment Block](#172-the-recent-rooms-greeting-enrichment-block)
173. [`_resolve_addressed_to` — The Three-Source Router](#173-_resolve_addressed_to--the-three-source-router)

### Part XXVII — Pre-3B Hardening (Sessions 110–113.1)
174. [Latency Fix — The SCENE Block Write Path](#174-latency-fix--the-scene-block-write-path)
175. [Session-Boundary History Filtering](#175-session-boundary-history-filtering)
176. [`addressed_to` Column on `conversation_log`](#176-addressed_to-column-on-conversation_log)
177. [Enrollment Mishear Candidate Gate](#177-enrollment-mishear-candidate-gate)
178. [Turn-Dispatch Addressee Logging](#178-turn-dispatch-addressee-logging)

### Part XXVIII — Observability 2.0
179. [The `[Pipeline] Turn addressed` Signature](#179-the-pipeline-turn-addressed-signature)
180. [The `[Room]` Log Category](#180-the-room-log-category)
181. [Richer Voice-Routing Logs](#181-richer-voice-routing-logs)
182. [The `[Intent]` Log Category](#182-the-intent-log-category)
183. [Terminal Output Archival Hook](#183-terminal-output-archival-hook)

### Part XXIX — Phase 4 Placeholder — Implicit Intent (NOT YET IMPLEMENTED)
184. [Motivation](#184-motivation)
185. [Planned Architecture](#185-planned-architecture)
186. [Planned Data Capture](#186-planned-data-capture)
187. [Task List (From VISION_ROADMAP §4.4)](#187-task-list-from-vision_roadmap-44)

### Part XXX — Phase 5 Placeholder — Continuous Evaluation (NOT YET IMPLEMENTED)
188. [Motivation](#188-motivation)
189. [Golden Set as Living Artifact](#189-golden-set-as-living-artifact)
190. [Divergence Monitoring Table](#190-divergence-monitoring-table)
191. [Weekly Review Ritual](#191-weekly-review-ritual)
192. [Canary Shadow Sample](#192-canary-shadow-sample)
193. [Task List (From VISION_ROADMAP §5.3)](#193-task-list-from-vision_roadmap-53)

### Part XXXI — Pyannote Dependency Maintenance
194. [Why the Patches Exist](#194-why-the-patches-exist)
195. [Patched Files](#195-patched-files)
196. [Reapplication Workflow](#196-reapplication-workflow)
197. [Deprecation Plan](#197-deprecation-plan)

### Part XXXII — Voice/Vision Independence and the Reconciler (Phases 1–4)
198. [Why the Rearchitecture](#198-why-the-rearchitecture)
199. [`voice_channel.py` — Pure Speaker Identification](#199-voice_channelpy--pure-speaker-identification)
200. [`vision_channel.py` — Pure Scene Observation](#200-vision_channelpy--pure-scene-observation)
201. [`reconciler.py` — The 22-Rule Cascade](#201-reconcilerpy--the-22-rule-cascade)
202. [The Negative-Cosine Bug and Why It Mattered](#202-the-negative-cosine-bug-and-why-it-mattered)
203. [Phase 4 Cutover and Known Follow-Ups](#203-phase-4-cutover-and-known-follow-ups)

### Part XXXIII — The Pure-Graph Intent Classifier
204. [Why We Replaced the LLM Classifier](#204-why-we-replaced-the-llm-classifier)
205. [Spec 1 — Bootstrap and the Scenario Database](#205-spec-1--bootstrap-and-the-scenario-database)
206. [`classifier_db.py` — Schema and Audit](#206-classifier_dbpy--schema-and-audit)
207. [Spec 2 — `classify_intent_graph()` Anatomy](#207-spec-2--classify_intent_graph-anatomy)
208. [Three Modes — `shadow`, `primary`, `retired`](#208-three-modes--shadow-primary-retired)
209. [Wilson Lower-Bound Aggregation](#209-wilson-lower-bound-aggregation)
210. [The Correction Loop and Why It's Currently Dormant](#210-the-correction-loop-and-why-its-currently-dormant)
211. [Outcome Supervision — The Dead Code Path](#211-outcome-supervision--the-dead-code-path)
212. [E5 Embeddings — Local on GPU](#212-e5-embeddings--local-on-gpu)
213. [Privacy and Abstraction at the Embedding Layer](#213-privacy-and-abstraction-at-the-embedding-layer)
214. [Latency Profile and the Boot-Warmup Decision](#214-latency-profile-and-the-boot-warmup-decision)

### Part XXXIV — External Benchmark Validation
215. [The Bhagtani et al. 2026 Paper and the Friends Test Set](#215-the-bhagtani-et-al-2026-paper-and-the-friends-test-set)
216. [Run 1 — LLM Classifier on Llama-70B (58.66%)](#216-run-1--llm-classifier-on-llama-70b-5866)
217. [Run 2 — Multi-Backbone Falsifying Experiment (Qwen-7B, 52.32%)](#217-run-2--multi-backbone-falsifying-experiment-qwen-7b-5232)
218. [Run 3 — Graph Classifier (64.48%)](#218-run-3--graph-classifier-6448)
219. [The 10-Run Scaling Ablation and the Inverse-Scaling Finding](#219-the-10-run-scaling-ablation-and-the-inverse-scaling-finding)
220. [The AMI 10-Row Smoke and Out-of-Scope Disclosure](#220-the-ami-10-row-smoke-and-out-of-scope-disclosure)
221. [The `karaos-public` Repository Layout](#221-the-karaos-public-repository-layout)

### Part XXXV — Multi-Layer Classifier Architecture (FUTURE WORK)
222. [Why This Is the Next Step](#222-why-this-is-the-next-step)
223. [The Six-Layer Architecture at a Glance](#223-the-six-layer-architecture-at-a-glance)
224. [Layer 1 — Per-Scenario Learned Reliability](#224-layer-1--per-scenario-learned-reliability)
225. [Layer 2 — Outcome Supervision Wired Correctly](#225-layer-2--outcome-supervision-wired-correctly)
226. [Layer 3 — Hierarchical Retrieval, Adaptive K, Distance-Weighted Voting](#226-layer-3--hierarchical-retrieval-adaptive-k-distance-weighted-voting)
227. [Layer 4 — Multi-Aspect Annotation Rebuild](#227-layer-4--multi-aspect-annotation-rebuild)
228. [Layer 5 — Active Quality Gating and Auto-Quarantine](#228-layer-5--active-quality-gating-and-auto-quarantine)
229. [Layer 6 — Provenance and Lineage](#229-layer-6--provenance-and-lineage)
230. [Phase Sequencing — How the Layers Ship](#230-phase-sequencing--how-the-layers-ship)
231. [The Non-Parametric Commitment](#231-the-non-parametric-commitment)
232. [Honest Limitations of the Multi-Layer Plan](#232-honest-limitations-of-the-multi-layer-plan)

### Part XXXVI — P0 Correctness Hardening (P0.1 – P0.3 + P0.13)
233. [Why a Correctness Cycle Came First](#233-why-a-correctness-cycle-came-first)
234. [P0.1 — No Raw `"disputed"` Comparisons Outside the Helper](#234-p01--no-raw-disputed-comparisons-outside-the-helper)
235. [P0.2 — `prior_person_type` Fail-Closed Default](#235-p02--prior_person_type-fail-closed-default)
236. [P0.3 — Multi-Word Name Contiguous Substring Fix](#236-p03--multi-word-name-contiguous-substring-fix)
237. [P0.13 — The Repeat-Guard Invariant Test](#237-p013--the-repeat-guard-invariant-test)

### Part XXXVII — The Silent-Except Audit (P0.4)
238. [The Reactive-Patching Anti-Pattern](#238-the-reactive-patching-anti-pattern)
239. [AST Detector Anatomy](#239-ast-detector-anatomy)
240. [The 22 Surfaced Sites and the Three Permitted Annotations](#240-the-22-surfaced-sites-and-the-three-permitted-annotations)
241. [Bulk Annotator and the One-Shot Closure](#241-bulk-annotator-and-the-one-shot-closure)

### Part XXXVIII — Cross-Storage Atomicity (P0.5 + P0.X)
242. [The Paired-Write Failure Class](#242-the-paired-write-failure-class)
243. [P0.5 — FAISS ↔ faces.db SQL-First Ordering](#243-p05--faiss--facesdb-sql-first-ordering)
244. [Sentinel Files and Boot Reconciliation](#244-sentinel-files-and-boot-reconciliation)
245. [The Inverse-Check Discipline](#245-the-inverse-check-discipline)
246. [P0.X — The Three Kuzu Write Patterns](#246-p0x--the-three-kuzu-write-patterns)
247. [SCHEMA_MIGRATION, RAISE, and SWALLOW in Detail](#247-schema_migration-raise-and-swallow-in-detail)
248. [`_process_turn` — The Hidden Paired-Write Site](#248-_process_turn--the-hidden-paired-write-site)
249. [Degraded-Mode Fallback Behavior](#249-degraded-mode-fallback-behavior)

### Part XXXIX — The Store-Pattern Migration (P0.6)
250. [Why 28 Module-Level Globals Was a Problem](#250-why-28-module-level-globals-was-a-problem)
251. [The `Store(ABC, Generic[T])` Base Class](#251-the-storeabc-generict-base-class)
252. [The Eight Stores and What Each Owns](#252-the-eight-stores-and-what-each-owns)
253. [Async Mutators, Sync `peek_*` Reads, and the Single-Owner Invariant](#253-async-mutators-sync-peek_-reads-and-the-single-owner-invariant)
254. [The Producer-Copy Invariant](#254-the-producer-copy-invariant)
255. [Peek-Not-Mutate Semantics for CacheStore](#255-peek-not-mutate-semantics-for-cachestore)
256. [The Prior-State Guard for Cloud Transitions](#256-the-prior-state-guard-for-cloud-transitions)
257. [Autouse-Fixture Reset and the M2 Coverage Meta-Test](#257-autouse-fixture-reset-and-the-m2-coverage-meta-test)
258. [The Eight Deliberate-Regression Checks at v2 Closure](#258-the-eight-deliberate-regression-checks-at-v2-closure)
259. [The Legacy-Global Ratchet at Cap = 0](#259-the-legacy-global-ratchet-at-cap--0)
260. [The Schema and Inverse-Check Ratchets That Lock It In](#260-the-schema-and-inverse-check-ratchets-that-lock-it-in)

### Part XL — Typed Session State (P0.7)
261. [Why Move the Session Dict to a Typed Store](#261-why-move-the-session-dict-to-a-typed-store)
262. [`core/session_state.py` — Three Dataclasses](#262-coresession_statepy--three-dataclasses)
263. [`SessionStore` — Single Owner with `asyncio.Lock`](#263-sessionstore--single-owner-with-asynciolock)
264. [The 21 Named Transition Methods](#264-the-21-named-transition-methods)
265. [`SessionSnapshot` — Frozen, Sliced, Cheap to Pass Around](#265-sessionsnapshot--frozen-sliced-cheap-to-pass-around)
266. [The 5-Phase Migration (P0.7.1 → P0.7.5)](#266-the-5-phase-migration-p071--p075)
267. [The SHIM Layer and Its Eventual Deletion](#267-the-shim-layer-and-its-eventual-deletion)
268. [`peek_all_snapshots` and the Single-Thread-Asyncio Safety Contract](#268-peek_all_snapshots-and-the-single-thread-asyncio-safety-contract)
269. [Dispute State via Named Transitions](#269-dispute-state-via-named-transitions)
270. [The Closure Invariants That Lock the Migration](#270-the-closure-invariants-that-lock-the-migration)

### Part XLI — Per-Tool Timeout Protection (P0.8)
271. [The Hang Surface Before P0.8](#271-the-hang-surface-before-p08)
272. [`_TOOL_HANDLERS` Extraction and `_ToolContext`](#272-_tool_handlers-extraction-and-_toolcontext)
273. [`asyncio.wait_for` and the Per-Tool Budgets](#273-asynciowait_for-and-the-per-tool-budgets)
274. [Cancellation Rollback Through Transaction `__aexit__`](#274-cancellation-rollback-through-transaction-__aexit__)
275. [P0.8.1 — Tavily Wrap and the Hidden Inline Consumer](#275-p081--tavily-wrap-and-the-hidden-inline-consumer)
276. [P0.8.2 — F1 + F2 Structural Invariants](#276-p082--f1--f2-structural-invariants)

### Part XLII — Schema Migrations Versioning (P0.9)
277. [The Drift Problem with Inline `ALTER TABLE` Calls](#277-the-drift-problem-with-inline-alter-table-calls)
278. [`core/schema_migrations.py` — The Generalised Helper](#278-coreschema_migrationspy--the-generalised-helper)
279. [The 5-Tuple Migration Shape and Why](#279-the-5-tuple-migration-shape-and-why)
280. [`verify_post` vs `verify_present` — The Developer-Improved-on-Spec Split](#280-verify_post-vs-verify_present--the-developer-improved-on-spec-split)
281. [Imp-1 — `isolation_level="IMMEDIATE"` on Every Connect](#281-imp-1--isolation_levelimmediate-on-every-connect)
282. [Imp-2 — Tightened S65 Rollback Discipline](#282-imp-2--tightened-s65-rollback-discipline)
283. [The 19 Retrofitted Historical Migrations](#283-the-19-retrofitted-historical-migrations)
284. [The Structural Invariants That Lock the Pattern](#284-the-structural-invariants-that-lock-the-pattern)

### Part XLIII — Legacy Router Deletion and Bug-W Closure (P0.10)
285. [The Phase 0 Premise Reset](#285-the-phase-0-premise-reset)
286. [The Bug-W Coverage Gap](#286-the-bug-w-coverage-gap)
287. [`_p0_short_utterance_gap_hold_current` and the `LOWER_BOUND` Attribute](#287-_p0_short_utterance_gap_hold_current-and-the-lower_bound-attribute)
288. [The Non-Decreasing Band-Ordering Invariant](#288-the-non-decreasing-band-ordering-invariant)
289. [The Band-Divergence Block C Trigger](#289-the-band-divergence-block-c-trigger)
290. [Phase 2 Cutover and the –15 / +40 Coverage Shift](#290-phase-2-cutover-and-the-15--40-coverage-shift)
291. [P0.10.1 — `EXPECTED_RULES_BY_BAND` Lock](#291-p0101--expected_rules_by_band-lock)
292. [The Validation Runbook and Gate Criteria](#292-the-validation-runbook-and-gate-criteria)

### Part XLIV — State Race Hardening (P0.11)
293. [Preventive Hardening for a Latent Race](#293-preventive-hardening-for-a-latent-race)
294. [The Atomic-Replace Pattern and Why It Works](#294-the-atomic-replace-pattern-and-why-it-works)
295. [Three Deliberate-Regression Checks and the Detector-Strengthening Cycle](#295-three-deliberate-regression-checks-and-the-detector-strengthening-cycle)

### Part XLV — JSON Parser Hardening (P0.12 + P0.12.1)
296. [Why Property-Based Testing](#296-why-property-based-testing)
297. [The Two Production Bugs Hypothesis Surfaced](#297-the-two-production-bugs-hypothesis-surfaced)
298. [P0.12.1 — The SocialGraphAgent Dead-Branch Audit](#298-p0121--the-socialgraphagent-dead-branch-audit)
299. [`_parse_json_array` — The Sibling Parser](#299-_parse_json_array--the-sibling-parser)

### Part XLVI — Health and Disk Observability (Wave 5)
300. [The Health-Pulse Cadence](#300-the-health-pulse-cadence)
301. [`HealthSnapshot` and the One-Line Format](#301-healthsnapshot-and-the-one-line-format)
302. [Three-Level Disk Alerts with Idempotent Transitions](#302-three-level-disk-alerts-with-idempotent-transitions)

### Part XLVII — Conversation Hygiene and Memory Consolidation (Wave 6)
303. [Hard-Delete Pruning of Invalidated Knowledge](#303-hard-delete-pruning-of-invalidated-knowledge)
304. [SHA-256 Scene-Block Cache](#304-sha-256-scene-block-cache)
305. [`conversation_log` Archival via ATTACH DATABASE](#305-conversation_log-archival-via-attach-database)

### Part XLVIII — Tiered CI Scaffold and S2 Deferral Tripwire (P0.0 + P0.0.1 + P0.0.2)
306. [Three Workflows — Fast, Slow, Security](#306-three-workflows--fast-slow-security)
307. [Pytest Markers and the Infra-Debt Allowlist](#307-pytest-markers-and-the-infra-debt-allowlist)
308. [The S2 Tripwire and the Theater That P0.0.1 Closed](#308-the-s2-tripwire-and-the-theater-that-p001-closed)
309. [P0.0.2 — V1 xfail Bundling for Infra-Debt Tests](#309-p002--v1-xfail-bundling-for-infra-debt-tests)

### Part XLIX — Event Log and Replay Harness (P0.0.7)
310. [Why Event-Sourcing the Boundary](#310-why-event-sourcing-the-boundary)
311. [The 12 Payload Types](#311-the-12-payload-types)
312. [`NATURAL_PARENT_PAIRS` and Causal-Chain Auto-Resolution](#312-natural_parent_pairs-and-causal-chain-auto-resolution)
313. [`_PAYLOAD_CLASSES` and the Deserialization Contract](#313-_payload_classes-and-the-deserialization-contract)
314. [Producer Anatomy — `emit`, `emit_sync`, `safe_emit_sync`](#314-producer-anatomy--emit-emit_sync-safe_emit_sync)
315. [The `_recent_parent` Writer-Task-Scope Cache](#315-the-_recent_parent-writer-task-scope-cache)
316. [Bounded Queue and the D5 Lossy-Backpressure Decision](#316-bounded-queue-and-the-d5-lossy-backpressure-decision)
317. [The 11 Producer Hooks at 12 Sites](#317-the-11-producer-hooks-at-12-sites)
318. [`_m_0012_create_event_log_*` Migration](#318-_m_0012_create_event_log_-migration)
319. [The Read-Only Replay CLI](#319-the-read-only-replay-cli)
320. [Reusable Scenario Fixtures for P0.S1+](#320-reusable-scenario-fixtures-for-p0s1)
321. [Health-Log Integration via Drop and Emit-Failure Counters](#321-health-log-integration-via-drop-and-emit-failure-counters)

### Part L — Architectural Disciplines (The Named Doctrines)
322. [Induction-Surfaces-Invariant-Gaps](#322-induction-surfaces-invariant-gaps)
323. [Architect-Reads-Production-Code-Before-Sign-Off](#323-architect-reads-production-code-before-sign-off)
324. [Verification-Before-Completion (Strengthened by Full-Suite Lesson)](#324-verification-before-completion-strengthened-by-full-suite-lesson)
325. [Spec-First Review Cycle for Multi-Day Specs](#325-spec-first-review-cycle-for-multi-day-specs)
326. [Spec-Contracts-Not-Implementations](#326-spec-contracts-not-implementations)
327. [Developer-Improves-on-Spec-by-Reading-Carefully](#327-developer-improves-on-spec-by-reading-carefully)
328. [Tripwires-Must-Match-the-Actual-Deferral-Surface](#328-tripwires-must-match-the-actual-deferral-surface)
329. [Structured-Audit-vs-Reactive-Patching (Empirical Foundation)](#329-structured-audit-vs-reactive-patching-empirical-foundation)
330. [Why Each Discipline Has a Track Record, Not a Rule](#330-why-each-discipline-has-a-track-record-not-a-rule)

### Part LI — Upcoming Work and Roadmap
331. [P0.0.7.X — Hypothesis TestLargeInput Flakiness](#331-p007x--hypothesis-testlargeinput-flakiness)
332. [P0.S1 — Anti-Spoof on Every Face Match (Next Item)](#332-p0s1--anti-spoof-on-every-face-match-next-item)
333. [P0 Security — The Locked Sequence Beyond P0.S1](#333-p0-security--the-locked-sequence-beyond-p0s1)
334. [P0 Robustness — R1 through R11](#334-p0-robustness--r1-through-r11)
335. [Eval Gates — Continuous Evaluation Becomes Real](#335-eval-gates--continuous-evaluation-becomes-real)
336. [P1.A — Pipeline.py Decomposition into ~30 Modules](#336-p1a--pipelinepy-decomposition-into-30-modules)
337. [Voice Gallery Growth Bug for Promoted Voice-Only Strangers](#337-voice-gallery-growth-bug-for-promoted-voice-only-strangers)
338. [Kuzu v3 Schema Bump and Graph-Side Privacy](#338-kuzu-v3-schema-bump-and-graph-side-privacy)
339. [Format-Bridge Unification (Producer Rows vs CLI Render)](#339-format-bridge-unification-producer-rows-vs-cli-render)
340. [The Multi-Layer Classifier Architecture (XXXV) — When It Ships](#340-the-multi-layer-classifier-architecture-xxxv--when-it-ships)

---
---

# Part I — Foundations

## 1. What Kara-OS Is

Kara-OS is an autonomous conversational companion that runs as a single Python process on a laptop today and will run on a Jetson AGX Orin with a physical robot body tomorrow. It has a camera, a microphone, and a speaker. It sees faces, recognises the people it knows, greets them by name, holds natural spoken conversations, and continuously learns about them across sessions.

What distinguishes it from a conventional "AI assistant" is that it is not organised around *commands and completions*. It is organised around *presence and relationship*. The mental model is closer to a dog that learns your household than to Alexa — hence the name.

Concretely, Kara-OS:

- **Sees** — Detects faces with RetinaFace, tracks them across frames with SORT+Kalman, embeds them with AdaFace IR101, recognises enrolled people from a FAISS index, rejects photo/screen-replay attacks with a two-model MiniFASNet ensemble.
- **Hears** — Captures audio from the OS mic, runs VAD (RMS by default, Silero available), triggers a neural end-of-turn classifier (Smart-Turn ONNX), and transcribes with faster-whisper large-v3-turbo. In parallel it identifies *who* is speaking using ECAPA-TDNN speaker embeddings.
- **Thinks** — Sends the transcribed turn to Llama-3.3-70B via Together.ai with function calling, streaming responses token-by-token. On cloud failure it falls back to a local Ollama qwen2.5:7b for stateless Q&A.
- **Remembers** — Stores every turn in a SQLite WAL database, extracts structured facts with a background LLM agent, resolves contradictions, embeds them semantically, ties them to a Kuzu property graph, and makes all of that searchable by a dedicated `search_memory` tool the brain can call when relevant.
- **Speaks** — Splits the streaming response into sentences, synthesises each sentence with Kokoro TTS (Piper fallback), and plays them through a sounddevice sink.
- **Learns** — Background agents analyse communication preferences, detect friction between claimed preferences and observed behaviour, extract household relationships, spot behavioural patterns in spatial sightings, and generate proactive questions that the robot asks naturally during lulls.
- **Guards its own identity** — Fail-closed privilege model means only the best friend can rename the system or shut it down. A dispute state machine activates when a speaker's claim contradicts sensor evidence. Gallery poisoning is prevented by a centroid-distance gate and an anti-spoof requirement on every self-update.

Kara-OS is currently 822 tests, 17000 lines of Python, and a Next.js dashboard. The test suite is green at HEAD and ratchets upward with every session.

## 2. The Companion-Not-Assistant Philosophy

Almost every design decision in this system bends toward "feels like a companion" rather than "answers questions accurately." Some examples of this bias in action:

**The brain is the source of all user-facing behaviour.**
When Jagan returns and Kara-OS greets him, the greeting is not templated. It is generated by the LLM with full context: the time of day, how long since last session, which person type is the speaker, what the most recent turns were about. We explicitly reject the "assistant pattern" of having deterministic templates for ceremonial speech.

**The pipeline never editorialises.**
The pipeline's job is to be the brain's sensors and actuators. It tells the brain what is happening (who is in frame, what confidence level, what the voice score was, whether anti-spoof passed). It does not decide what to say. It does not second-guess. It enforces policy the brain cannot violate (privilege checks, accumulation gates, anti-spoof gating), but does not itself speak.

**Latency matters more than factual perfection.**
We chose Together.ai Turbo over GPT-4-class models because time-to-first-token matters for conversational feel. A 250ms TTFT with a mid-sized open model feels alive; a 1.5s TTFT with a larger model feels like a tool. We accept slightly worse factuality for dramatically better flow.

**Silence is a valid output.**
If a stranger walks in and starts talking without addressing the system by name, Kara-OS stays silent. The system-name gate blocks all output until they say "Kara". This is a deliberate choice — an assistant would try to be helpful to whoever spoke; a companion only engages when invited into conversation. The gate is `STRANGER_REQUIRE_SYSTEM_NAME = True` in `core/config.py`.

**The robot has a name given by the user, not a name we chose.**
At first boot, the system introduces itself as "Dog" (the `DEFAULT_SYSTEM_NAME`). It asks the best friend to name it. The name the best friend chooses is stored in `faces.db` in the `system_identity` table and surfaces in the system prompt and TTS. Every subsequent session the system introduces itself by that name.

**Memory is non-destructive.**
We never delete a fact the user told us. We *invalidate* it — mark it stale, reduce its confidence via exponential decay, supersede it in the ContradictionAgent with a newer version — but the original remains in `brain.db` with `invalidated_at` set. A past fact is a past self we want to remember having been.

**Privacy is expressed in scope, not in redaction.**
Attributes whose names contain tokens like `health`, `medical`, `salary`, `secret` get tagged `privacy_level='private'` at write time. Private facts surface to the person they belong to and to the best friend, not to other speakers. The best friend bypasses all privacy filters by design — in this household, they are the trusted adult.

This philosophy is not a vibe; it is baked into specific config constants, specific gating code, and specific tool descriptions. Whenever you read a threshold and wonder "why isn't this more conservative?", the answer is almost always "because conservatism would break the companion feel."

## 3. System Architecture at Multiple Zoom Levels

### 3.1 The 30,000-foot view

```
┌─────────────────────────────────────────────────────────────────┐
│                        Kara-OS Process                           │
│                                                                 │
│   Sensors ──> Pipeline ──> Brain ──> TTS ──> Speaker            │
│      │            │          │                                  │
│      │            │          └──> Tools (update_name, search,   │
│      │            │                      shutdown, memory)      │
│      │            │                                             │
│      │            └──> Knowledge Agents (async, out-of-band)    │
│      │                                                          │
│      └──> Camera (RetinaFace + AdaFace + Anti-spoof)            │
│      └──> Mic    (VAD + Smart-Turn + Whisper + ECAPA-TDNN)      │
│                                                                 │
│   Persistence: faces.db, brain.db, faiss.index, brain_graph/    │
└─────────────────────────────────────────────────────────────────┘
         │                                              ▲
         │ writes state.json atomically                 │
         ▼                                              │
┌────────────────┐                              ┌──────────────┐
│   Dashboard    │                              │   Operator   │
│   (Next.js)    │── reads state.json ────────> │  (browser)   │
│   localhost    │   every 500ms               │              │
└────────────────┘                              └──────────────┘
```

At this zoom level, the system is a single process that reads from two physical sensors (camera and mic), runs inference on three classes of model (vision, speech, language), and produces two outputs (speech on the speaker, and a JSON state file the dashboard reads). Everything else — the agents, the graph, the consolidation loops — is internal.

### 3.2 The 10,000-foot view — major subsystems

```
┌─────────── Sensing Layer (in-process, GPU) ───────────┐
│ vision.py: FaceDetector, FaceEmbedder, AntiSpoofChecker │
│ audio.py:  Whisper, Smart-Turn, Kokoro TTS             │
│ voice.py:  ECAPA-TDNN speaker embedder                 │
│ emotion.py: j-hartmann emotion classifier (CPU)        │
└────────────────────────────────────────────────────────┘
                         │
                         ▼
┌────────────────────── pipeline.py ─────────────────────┐
│  Main async event loop                                 │
│  PipelineState machine: WATCHING / LISTENING /         │
│                         THINKING / SPEAKING / ENROLLING│
│  _active_sessions dict (multi-person)                  │
│  _resolve_actual_speaker (5-priority routing)          │
│  _voice_accum_allowed (Path A/B/C policy)              │
│  Tool dispatch with TOOL_PRIVILEGES enforcement        │
│  KAIROS proactive wake                                 │
└────────────────────────────────────────────────────────┘
                         │
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
┌─────────────┐ ┌─────────────┐ ┌──────────────────┐
│ brain.py    │ │ brain_agent │ │ db.py            │
│ ─────────── │ │ ─────────── │ │ ──────────────── │
│ Together.ai │ │ 15+ agents: │ │ FaceDB           │
│ Ollama fallback│ │ triage,   │ │ (SQLite + FAISS) │
│ 6 tools     │ │ extraction, │ │ voice_embeddings │
│ streaming   │ │ graph,      │ │ conversation_log │
│ compression │ │ nudges, ... │ │ silent_obs       │
│ KAIROS hooks│ │ brain.db    │ │ persons, etc.    │
└─────────────┘ │ Kuzu graph  │ └──────────────────┘
                │ dream loop  │
                └─────────────┘
                         │
                         ▼
┌──────────────── state.py ─────────────────────────────┐
│  Atomic JSON write — pipeline → dashboard IPC         │
└────────────────────────────────────────────────────────┘
```

### 3.3 The 1,000-foot view — the turn cycle

A single "turn" — user speaks, system responds — is the atomic unit of interaction. It flows like this:

```
Mic RMS crosses threshold
          │
          ▼
[Audio] Speech started (chunk #N, HH:MM:SS)
          │
          ▼
Pre-roll buffer + speech chunks accumulate
          │
          ▼
Silence > SMART_TURN_SILENCE (0.5s)
          │
          ▼
Smart-Turn ONNX check: is this an end-of-turn?
          │
    p > SMART_TURN_THRESHOLD (0.80)           p < threshold
          │                                      │
          ▼                                      ▼
    Turn complete                        Silence > SILENCE_DURATION (1.5s) hard fallback
          │                                      │
          └──────────────────┬───────────────────┘
                             ▼
                     Lip tracking gives
                     LIP_MAX_EXTENSION (2s) grace if lips move
                             │
                             ▼
                     audio_buf finalized
                             │
                             ▼
              Whisper STT (faster-whisper large-v3-turbo)
              [STT] HH:MM:SS.mmm (Nms) '<transcript>'
                             │
                             ▼
              ECAPA-TDNN voice ID → (v_pid, v_score)
                             │
                             ▼
              Within-utterance diarization if ≥ 2s
                             │
                             ▼
              _resolve_actual_speaker(v_pid, v_score, cur_pid, ...)
              → (actual_pid, routing_reason)
                             │
                             ▼
              Open / switch / keep session
                             │
                             ▼
              Anti-spoof check if face-gated path
                             │
                             ▼
              Engagement gate check (stranger workflow only)
                             │
                             ▼
              conversation_turn(actual_pid, text, audio_buf)
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
         Build system    Build history   Build voice-state +
         prompt blocks                   vision-state
              │              │              │
              └──────────────┼──────────────┘
                             ▼
                     ask_stream(Together.ai)
                             │
                             ▼
                  Token events ──> speak_stream ──> TTS ──> speaker
                  Tool events  ──> _execute_tool ──> (update_name, search_web, ...)
                  Finish event ──> truncation check, maybe Ollama retry
                             │
                             ▼
              db.log_turn(pid, 'user', text); db.log_turn(pid, 'assistant', response)
                             │
                             ▼
              _brain_orchestrator.notify() → agent loop wakes
                             │
                             ▼
              Voice accumulation (Path A / B / C)
                             │
                             ▼
              state.json atomic write
                             │
                             ▼
              Return to WATCHING / LISTENING
```

Every arrow in that diagram is a place where a design decision was made. The rest of this document is the story of those decisions.

### 3.4 The 100-foot view — a single function

Every architectural claim above is grounded in specific code. Here is one example — the Path A/B/C accumulation policy in `pipeline._voice_accum_allowed`:

```python
def _voice_accum_allowed(session: dict) -> tuple[bool, str, str]:
    """Decide whether voice accumulation is allowed for a session.

    Returns (allowed, reason, path). path is one of "face_witness",
    "voice_self_match", "bootstrap", or "refused". Paths are tried
    in that order — first-match wins.
    """
    ev = session.get("identity_evidence") or {}
    now = time.time()

    # Path A — recent confident face witness
    face_age = now - ev.get("face_last_seen_ts", 0.0)
    if (ev.get("face_match_conf", 0.0) >= VOICE_ACCUM_FACE_WITNESS_MIN_CONF
            and ev.get("anti_spoof_live", False)
            and face_age <= VOICE_ACCUM_FACE_WITNESS_MAX_AGE_SEC):
        return (True, f"face witness (...)", "face_witness")

    # Path B — mature voice profile self-matching
    if (ev.get("voice_match_conf", 0.0) >= VOICE_ACCUM_VOICE_SELF_MATCH_MIN
            and ev.get("voice_sample_count", 0) >= VOICE_ACCUM_MATURE_SAMPLE_COUNT):
        return (True, f"voice self-match (...)", "voice_self_match")

    # Path C — bootstrap credits from engagement gate
    if ev.get("bootstrap_credits", 0) > 0:
        return (True, f"bootstrap (...)", "bootstrap")

    return (False, f"no witness (...)", "refused")
```

That's the whole policy. Three paths, tried in order, first match wins. The thresholds live in `core/config.py`. The brain reads the same constants for its `<<<IDENTITY EVIDENCE>>>` verdict heuristic so the brain's label and the pipeline's gate cannot drift.

Zooming in like this is how the document is written. We'll start from the outermost layer and progressively zoom in, each time pointing at the actual code and config that implements the described behaviour.

## 4. Runtime Environment

### 4.1 Current dev environment — Windows laptop

- **OS**: Windows 11 Home Single Language 10.0.26200
- **Shell**: Git Bash (Unix semantics via MSYS2)
- **Python**: 3.13 via standalone install; project uses venv at `venv/` inside the project root
- **GPU**: NVIDIA with CUDA 12.x and cuDNN 9.x. Required for onnxruntime-gpu, faster-whisper, torch
- **Camera**: USB webcam via DirectShow (`cv2.CAP_DSHOW`)
- **Microphone**: any OS default input device at 16 kHz mono
- **Speaker**: any OS default output device via `sounddevice`

### 4.2 Production target — Jetson AGX Orin 32GB

- **OS**: JetPack 6.x (Ubuntu-based)
- **Camera**: V4L2 (`cv2.CAP_V4L2`) — the vision code picks the right backend automatically via `sys.platform` check
- **Peripherals**: ReSpeaker 4-mic array planned for echo cancellation and beamforming (re-enables barge-in, which is currently disabled)
- **Face recognition**: `faiss-gpu` instead of `faiss-cpu`
- **TTS**: Kokoro runs on CPU even on Jetson — latency is acceptable
- **STT**: faster-whisper large-v3-turbo via TensorRT export when we get there

### 4.3 Why these targets

We intentionally develop on Windows because it is the harder target. V4L2 is simpler and faster than DirectShow, so if DirectShow works, Linux will work. Windows also forces us to address signal-handling edge cases (`add_signal_handler` is Linux-only, so we use `signal.signal` with explicit wake-up); when we move to Jetson, we can *add* the better Linux path without breaking the Windows fallback.

The Jetson choice is motivated by:

- **Form factor** — the production robot needs to carry its own compute. Jetson Orin is the only embedded platform with enough GPU to run the models we use without bandwidth-constrained cloud offload.
- **Power budget** — 15-60W configurable, enough for battery operation.
- **Unified memory** — no PCIe copy between CPU and GPU, which matters for low-latency vision pipelines.
- **TensorRT** — once stable, we can export the vision and STT models to TensorRT engines and halve inference latency.

### 4.4 Why we don't support Mac or Linux desktops

We do not actively test on Mac or Linux desktop. They would work with minimal changes — the vision code branches on `sys.platform` for camera backend — but they are not on the roadmap. The production target is the Jetson; anything else is an incidental dev convenience.

## 5. Tech Stack and Why Each Piece

### 5.1 Vision stack

| Component | Package | Why this one |
|---|---|---|
| Face detection | InsightFace buffalo_l (RetinaFace) | State-of-the-art recall on small faces; ONNX-runnable on GPU; stable EER; bundled with a 5-landmark predictor we use for yaw estimation in V2 quality gate |
| Face embedding | AdaFace IR101 | Margin loss optimised for open-set recognition; 512-d embeddings; stable 0.28-0.45 EER region; better than ArcFace at low-quality crops which is most of our inputs |
| Face tracking | SORT + scipy Kalman + linear_sum_assignment | Keeps identity across frames when detection skips (every 5th frame); deterministic Hungarian assignment avoids greedy track-claim races (Session 24 bug B6) |
| Anti-spoof | MiniFASNet V1SE + V2 (minivision-ai) | Two-model ensemble, softmax-averaged; catches photo, screen-replay, print attacks; ONNX via torch .pth weights we vendored (Session 52) |

We rejected:

- **MediaPipe** for detection — less accurate on small faces, bundled into a heavier runtime.
- **dlib** for embedding — dated, worse EER, no GPU path.
- **FaceNet 128-d** — shorter embeddings lose fidelity in mixed-angle galleries.
- **Silent-Face-Anti-Spoofing v1** — initial attempt; unstable preprocessing caused 100% false-reject of real faces (Session 59). We vendored the upstream MiniFASNet architecture directly with weights from the author's repo.

### 5.2 Audio stack

| Component | Package | Why this one |
|---|---|---|
| STT | faster-whisper large-v3-turbo | Best accuracy-per-millisecond available; Turbo variant has ~3x real-time factor on RTX 4090, ~1.5x on Orin; float16 on GPU; robust to voice overlap |
| VAD (default) | RMS energy on 16 kHz chunks | No model, no latency, tunable via RMS_THRESHOLD; works on laptop without a GPU slot |
| VAD (prod) | Silero v5 (ONNX) | Much better at rejecting background noise; switch via VAD_SWITCH=True on Jetson where GPU headroom exists |
| End-of-turn | Smart-Turn (pipecat-ai, 8MB ONNX) | Neural classifier trained on conversational audio; decides "is this turn complete?" faster than a fixed silence timeout; prevents the robot cutting off mid-sentence |
| Speaker ID | SpeechBrain ECAPA-TDNN (spkrec-ecapa-voxceleb) | 0.80% EER on VoxCeleb1-O; 192-d embeddings; cosine similarity on L2-normalised vectors; open weights; no API dependency |
| TTS primary | Kokoro ONNX (af_heart voice) | Best quality-per-millisecond we found for laptop; streaming synthesis; MIT license |
| TTS fallback | Piper en_US-lessac-medium | Rarely triggered; Kokoro is reliable. Fallback exists for the case where Kokoro's audio stream fails to initialise |

We rejected:

- **edge-tts** — cloud dependency added latency spikes and sometimes refused service.
- **pyttsx3** — OS-dependent, robotic voice.
- **Silero TTS** — lower quality than Kokoro.
- **openAI Whisper-1 API** — round-trip latency kills real-time feel; bills every minute of audio.

### 5.3 LLM stack

| Role | Model | Why |
|---|---|---|
| Chat | meta-llama/Llama-3.3-70B-Instruct-Turbo via Together.ai | Best open model for instruction-following in the Turbo tier; streaming + function calling; ~250ms TTFT; speculative decoding |
| Chat fallback | qwen2.5:7b via Ollama on localhost:11434 | Stateless Q&A only when Together.ai is unreachable; no tools, no memory writes; user hears "I'm feeling a bit sick" acknowledgement |
| Extraction | same Llama-3.3-70B | Async, not latency-critical; JSON-mode requests |
| Embeddings | intfloat/multilingual-e5-large-instruct via Together.ai | 1024-d; multilingual; instruction-following format; in-memory LRU cache |
| Vision | Qwen/Qwen3-VL-8B-Instruct via Together.ai | Not currently wired; reserved for when spatial memory vision turns on |
| Web search | Tavily "advanced" | 5 results per query; richer snippets than basic; 5-minute cache per query text |

We rejected:

- **GPT-4o** for chat — TTFT too high on streaming; pricing; lock-in.
- **Claude-3.5** — no function calling in the streaming channel at the time we picked; expensive per-token.
- **Groq** — would be faster (100ms TTFT) but Dev tier was not available when we integrated. Config is model-role-factored so switching to Groq is 3 lines in `core/config.py`.
- **Local LLM for chat** — a 70B model on a laptop GPU would run at 2 tokens/sec; not real-time.

### 5.4 Storage stack

| Component | Why |
|---|---|
| SQLite WAL | Embedded, zero-config, WAL lets the dashboard read while pipeline writes; crash-safe; works identically on Windows and Linux |
| FAISS IndexFlatIP | Exact cosine search on L2-normalised vectors; ~5000 galleries fit easily; FlatIP keeps the math simple — no training needed |
| Kuzu embedded property graph | Needed 1-hop traversal on (person)-[MENTIONED]->(entity) relationships; Kuzu is embedded so no separate process; Cypher-like query language; schema migration via version bump |

We rejected:

- **Postgres** for persistence — overkill, adds a server, no real benefit over SQLite for our scale.
- **Chroma / Weaviate** for embeddings — way more dependencies than we need for a local in-memory cache.
- **Neo4j** — too heavy, needs a server, and we only do 1-hop queries.

### 5.5 Process model

We are deliberately single-process. The pipeline, the brain agents, and the dream loop all run in the same asyncio event loop. Blocking I/O (Whisper, TTS synthesis, DB writes) is offloaded via `loop.run_in_executor(None, ...)`. There is no multi-process message passing, no Redis, no Celery. The only out-of-process boundary is `state.json`, which the Next.js dashboard polls.

Why:
- We can observe everything in one log stream.
- We never have to reason about pickling, GIL boundaries, or message schemas.
- Restart is instant.
- The cost — one blocking synchronous call can stall the loop — is mitigated by disciplined `run_in_executor` usage, and we audit for it.

## 6. Performance Budget and Latency Targets

These are not aspirational numbers; they are the current observed budgets on the dev laptop. The system *feels* alive because each stage stays inside its budget.

| Stage | Budget | Typical | Notes |
|---|---|---|---|
| RetinaFace detection (per frame) | 20 ms | ~15 ms | runs every 5th frame (SORT_DETECT_EVERY) |
| AdaFace embedding (per face) | 10 ms | ~7 ms | batches if 2+ faces |
| SORT Kalman predict (per frame) | 1 ms | <1 ms | pure Python + numpy |
| Whisper STT (per 5-second utterance) | 1 s | ~400-700 ms | elapsed_ms logged per call |
| ECAPA-TDNN voice ID | 150 ms | 80-150 ms | run in executor |
| Smart-Turn ONNX | 30 ms | ~20 ms | triggered on silence >= 0.5s |
| Anti-spoof ensemble | 50 ms | ~40 ms | two models, softmax averaged |
| LLM TTFT (Together.ai Turbo) | 400 ms | ~250 ms | varies with prompt length |
| LLM token throughput | 80 tok/s | 90-120 tok/s | Turbo speculative decoding |
| Kokoro TTS first audio | 500 ms | ~400 ms | from first sentence boundary |
| End-of-turn to speaker playback | 1.2 s | ~900 ms | STT + LLM TTFT + TTS-first-audio |
| Background vision scan period | 1 s | 1 s | independent of per-frame detection |
| State.json write | 5 ms | <5 ms | atomic rename |

### 6.1 Why these budgets matter

There's a human-perception threshold around 800-1000 ms for conversational turn-taking. Under 800ms, the response feels immediate; past 1200ms, it starts to feel like you're talking to a computer. Our budget puts end-of-turn-to-first-audio at ~900ms, which is inside the immediate-feel window.

If we were to add a synchronous cloud vision call in the middle of every turn (Qwen3-VL at ~500ms per call), we would blow past the threshold. That is why VISION_YOLO_ENABLED is currently False: we have not found a compelling enough use case to spend the latency budget on it.

### 6.2 Where we spend cycles that aren't on the critical path

- **BrainOrchestrator** polls `conversation_log` every `BRAIN_AGENT_POLL_INTERVAL=2.0`s. Extraction runs async; a single extraction is 1-5 seconds. If a turn generates 3 facts, we spend ~5s of background compute per turn — fine because the user doesn't wait for it.
- **DreamLoop** wakes every 60s to check idle/force conditions. A dream cycle does prune + decay + normalize + reconcile; ~500ms on a typical DB.
- **EmotionAgent** classifies each user turn; ~15-25ms on CPU per turn, batched in a rolling window.
- **PromptPrefAgent** runs a "lightweight intra-session pass" every 15 turns and a full analysis at session end.

All of these are below the user's awareness. The system *feels* like it is only doing the turn in front of it because the background work never blocks.

## 7. Directory Layout and File Purpose

```
Kara-OS/
├── pipeline.py                 Main async event loop (3761 lines). The "pipeline" in every sense —
│                               it is the thread that connects sensors to brain to actuators.
├── enroll.py                   Standalone CLI enrollment tool — guided face capture with anti-spoof
├── delete_person.py            CLI for deleting a person; calls person_lifecycle.delete_person_everywhere
├── person_lifecycle.py         Single authoritative delete path — cleans faces.db + brain.db + Kuzu + photos
├── audit_person.py             CLI wrapper for core/audit.py — inspects a gallery for poisoning
│
├── core/
│   ├── config.py               All constants (494 lines). Single source of truth.
│   ├── log_utils.py            _now_log_ts() and _log_trunc() — the one place log format lives
│   ├── vision.py               FaceDetector, FaceEmbedder, Camera, AntiSpoofChecker, LipTracker,
│   │                           face_quality_score, estimate_yaw_from_landmarks, TemporalEmbeddingBuffer,
│   │                           adaptive_threshold, verify_live (752 lines)
│   ├── audio.py                Whisper STT, Kokoro/Piper TTS, VAD, Smart-Turn, sentence streaming,
│   │                           _clean_for_tts, speak/speak_stream, stop_audio (655 lines)
│   ├── voice.py                ECAPA-TDNN speaker embedder, identify(), diarize() (233 lines)
│   ├── db.py                   FaceDB class — SQLite WAL + FAISS; all table ops, voice ops,
│   │                           silent observations, audit, person lifecycle helpers (1055 lines)
│   ├── brain.py                LLM calls — ask_stream, ask, ask_offline, ping_together,
│   │                           _build_system_prompt, all 8 prompt blocks, tool definitions,
│   │                           search_web, autocompact_history (1656 lines)
│   ├── brain_agent.py          Knowledge pipeline — BrainDB, BrainOrchestrator, 15+ agents,
│   │                           Kuzu graph, dream cycle (6105 lines)
│   ├── emotion.py              EmotionAgent wrapping j-hartmann distilroberta-base; shared pipeline
│   ├── sort.py                 SORT tracker with Kalman filter and Hungarian assignment
│   ├── state.py                Atomic state.json writer; pipeline → dashboard IPC
│   ├── audit.py                Gallery audit: per-embedding cosine vs centroid; flags outliers
│   ├── _minifasnet/            Vendored MiniFASNet architecture (Session 52); MIT license upstream
│   └── ...
│
├── models/
│   ├── smart_turn.onnx         Neural end-of-turn classifier (~8MB)
│   ├── adaface_ir101.onnx      Face embedding model
│   ├── antispoof_weights/      Two .pth files: MiniFASNetV2 (2.7 scale) + MiniFASNetV1SE (4.0 scale)
│   ├── piper/                  Piper TTS voices (fallback TTS)
│   └── buffalo_l/              RetinaFace + landmark predictor (auto-downloaded by InsightFace)
│
├── faces/                      Runtime data (wiped on factory reset)
│   ├── faces.db                SQLite: persons, embeddings, voice_embeddings, conversation_log, ...
│   ├── faiss.index             IndexFlatIP of face embeddings, rebuilt from DB on startup
│   ├── brain.db                Knowledge store — BrainDB
│   ├── brain_graph/            Kuzu property graph directory
│   ├── photos/                 Optional face crops for dashboard display
│   ├── state.json              Dashboard IPC — current pipeline state
│   ├── enroll_request.json     Dashboard → pipeline enrollment request
│   ├── enroll_result.json      Pipeline → dashboard enrollment result
│   ├── reset_request.json      Dashboard → pipeline reset request
│   └── reset_result.json       Pipeline → dashboard reset result
│
├── Kara-OS-dashboard/           Next.js dashboard (operator UI)
│   ├── app/                    App router pages
│   ├── pages/api/              API routes for enroll/delete/gallery-audit
│   └── ...
│
├── test_pipeline.py            Pipeline tests (the biggest file; ~7700 lines)
├── test_brain_agent.py         Knowledge pipeline tests
├── test_vision_v1v4.py         Vision quality gates + anti-spoof
├── test_faiss_delete.py        DB integrity tests — FAISS rebuild on delete, voice embeddings, etc.
├── test_executor.py            Tool dispatcher tests
├── test_shutdown.py            Graceful shutdown tests
├── test_greetings.py           Greeting generation tests
├── ...
│
├── CLAUDE.md                   Project memory for Claude Code — current state, invariants, rules
├── read_this_before_working.md Onboarding doc for human contributors
├── issues_to_work.md           Running log of findings + fixes per session
├── terminal_output.md          The most recent live-run terminal capture (changes every live test)
├── everything_about_system.md  This file
└── requirements.txt            Python deps
```

### 7.1 Which files you edit and how often

- **`core/config.py`** — change every time you tune a threshold. If you find yourself typing a number inside `pipeline.py` that isn't `0`, `1`, `-1`, or `None`, the number belongs here.
- **`pipeline.py`** — the event loop; changes when the overall flow changes.
- **`core/brain.py`** — changes when the system prompt layout changes or a new tool is added.
- **`core/brain_agent.py`** — changes the most; new agents land here.
- **`core/db.py`** — changes rarely; schema migrations happen here.
- **`CLAUDE.md`** — changes at the end of every session. The test count line, the completed sessions table, and the pending work list must stay current.
- **`everything_about_system.md`** (this file) — changes whenever architecture shifts non-trivially.

### 7.2 Files you never edit in normal use

- **`faces/*`** — runtime data. Deleted by factory reset. Do not commit.
- **`venv/`** — Python virtual environment. Not committed.
- **`models/`** — downloaded models. Not committed in source tree but symlinked / copied in.

---
---

# Part II — Lifecycle

## 8. Installation and First Run

### 8.1 Prerequisites

- Python 3.13 installed and on PATH.
- NVIDIA GPU with CUDA 12.x and cuDNN 9.x. The project links against `onnxruntime-gpu`, `torch` (CUDA), and `faiss-cpu` (on dev; `faiss-gpu` on production).
- A Together.ai account with an API key (for chat + extraction + embeddings).
- A Tavily API key (for web search) if you want the `search_web` tool to work; the tool fails gracefully without it.
- A webcam that OpenCV can open via index 0 (set `CAMERA_INDEX` in config if you need another).
- A microphone and speaker that `sounddevice` can open.

### 8.2 Installation

```bash
cd /c/Users/jagan/Kara-OS/Kara-OS           # or wherever the repo lives
python -m venv venv
source venv/Scripts/activate              # Windows via Git Bash
pip install --upgrade pip wheel
pip install -r requirements.txt
```

If you have an RTX 50-series card, you need a CUDA 12.8 PyTorch build:

```bash
pip install torch torchvision torchaudio \
    --index-url https://download.pytorch.org/whl/cu128
```

### 8.3 Environment variables

Create `.env` in the project root:

```
TOGETHER_API_KEY=tgp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TAVILY_API_KEY=tvly-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

`core/config.py` reads these via `python-dotenv`. Missing keys are non-fatal — the pipeline logs a warning and disables the corresponding feature (cloud LLM, web search).

### 8.4 First launch

```bash
python pipeline.py
```

If the project has never been run, the pipeline detects that `faces.db` has no best friend and enters **first-boot flow**. The camera activates, it looks for a face, and when it sees one it says:

> "Hey there... are you my best friend?"

If the person says yes, the enrollment proceeds (see §10). If they say no, the system keeps listening. The best friend is the person with privileges to shut the system down, rename it, and bypass all privacy filters.

### 8.5 Every subsequent launch

On return, the pipeline loads the FAISS index, loads the voice gallery from DB, resolves the system name (previously given by the best friend), and transitions to WATCHING state. When it sees a known face it greets them by name using an LLM-generated line.

## 9. Startup Sequence — Line by Line

This section walks through what happens from the moment you press Enter on `python pipeline.py` until the pipeline is in WATCHING state ready for its first turn. Every major startup side-effect is called out with its reason.

### 9.1 Import and module-level execution

When Python imports `pipeline.py`:

1. `core/config.py` is imported first (via the top of pipeline.py). It reads `.env`, defines every constant, and creates `faces/` if missing.
2. The GPU frameworks initialise lazily — `onnxruntime`, `torch`, `faiss` — but do not allocate GPU memory until a model is constructed.
3. Module-level state dicts are declared empty:
   - `_active_sessions: dict[str, dict] = {}`
   - `_persons_in_frame: dict = {}`
   - `_voice_gallery: dict = {}`
   - `_voice_gallery_sizes: dict = {}`
   - `_stranger_track_map: dict = {}`
   - `_unrecognized_tracks: dict = {}`
   - `_unrecognized_embeddings: dict = {}`
   - `_track_identity: dict = {}`
   - `_disputed_persons: set = set()` (on the BrainOrchestrator, but referenced from pipeline)
   - ... and many more.
4. SIGINT and SIGTERM handlers are registered. SIGTERM is no-op on Windows; on Linux it will trigger graceful shutdown.

### 9.2 `run()` — the top-level coroutine

`pipeline.py::run()` (the function that `main()` calls) does the following in order:

1. **Print banner**: `[Pipeline] Starting...`
2. **Startup invariant assertion**: every tool in `brain.TOOLS` must have a matching entry in `TOOL_PRIVILEGES`. If not, the startup aborts. This is the fail-closed tool-privilege invariant (Session 61 Step 2).
3. **Factory reset check**: if `faces/reset_request.json` exists (written by the dashboard), the pipeline wipes everything — `FaceDB.wipe_all()`, `shutil.rmtree(brain_graph)`, `BrainOrchestrator.wipe()`, `state.json`, `sim_session_state.json` — then writes `reset_result.json` with success. This happens *before* any models load, so we never load the old gallery into memory.
4. **Camera init**: `Camera.open()` constructs the `cv2.VideoCapture` with the platform-appropriate backend. If it fails, the pipeline retries every 5 seconds. One warmup frame is read and discarded — this is the only place we read the camera outside the vision loop, and we document it with a comment because it violates the "single reader" invariant.
5. **Vision model load**: `FaceDetector` loads buffalo_l RetinaFace on GPU. `FaceEmbedder` loads AdaFace IR101 on GPU. The first call is slow (~3 seconds); subsequent calls are hot.
6. **Audio model load**: `Whisper` (faster-whisper large-v3-turbo) loads on GPU with float16 precision. Kokoro TTS loads. Smart-Turn ONNX loads.
7. **Voice model load**: SpeechBrain ECAPA-TDNN loads (with two patched-up torchaudio warnings). Voice gallery is loaded from DB into `_voice_gallery` and `_voice_gallery_sizes`.
8. **Anti-spoof model load**: `AntiSpoofChecker` loads the two MiniFASNet `.pth` files from `models/antispoof_weights/`. If missing or errored, the checker enters "unavailable" mode — `is_live()` returns True to avoid false-blocking.
9. **Emotion model load**: `j-hartmann/emotion-english-distilroberta-base` loads on CPU (shared pipeline, re-used by all per-person EmotionAgents).
10. **BrainOrchestrator start**: constructs `BrainDB`, `GraphDB`, `EmbeddingAgent`, `TriageAgent`, `ExtractionAgent`, `ContradictionAgent`, `PromptPrefAgent`, `FrictionDetectionAgent`, `HouseholdExtractionAgent`, `PatternAnalysisAgent`, `NudgeAgent`, `SocialGraphAgent`, `WatchdogAgent`, `InsightAgent`, `SchemaNormAgent`. Starts the background loop that polls `conversation_log` every 2s.
11. **Graph schema check**: if `GRAPH_SCHEMA_VERSION` has been bumped, the orchestrator wipes the Kuzu graph and rebuilds from `knowledge` rows. This is why `v0→v2` shows up in the log on a fresh install.
12. **Cloud ping**: `ping_together()` with a 5-second timeout. If OK, `CloudState = ONLINE`. If not, `CloudState = SICK` and a background retry loop starts. The system will still work — just routes everything through Ollama.
13. **Best-friend check**: `db.get_best_friend()` returns the one person with `person_type='best_friend'`, if any. If not, we enter first-boot flow (§10). If yes, we enter WATCHING (§11).
14. **State file write**: `state.py::write_state(status="ready")`. Dashboard now shows "ready".
15. **Module-level `_face_db_ref = db`**: sets the global so `_open_session` can call `db.count_voice_embeddings()` for DB-hydrated voice sample counts (Obs 1, post-review).
16. **Main loop**: enter the WATCHING state, which is an async loop consuming camera frames and mic chunks.

Total startup time on the dev laptop: ~12 seconds from `python pipeline.py` to WATCHING. About 4s of that is Whisper model load; 3s is buffalo_l; 0.7s is ECAPA-TDNN; the rest is Python import overhead.

### 9.3 Terminal output of a typical startup

```
[Pipeline] Starting...
[Vision] Camera 0 opened (1280x720) via DirectShow
[Vision] RetinaFace (buffalo_l) loaded on GPU
[Vision] AdaFace loaded on GPU
[Pipeline] System name: Kara
[Pipeline] Preloading audio models...
[Audio] Loading Whisper large-v3-turbo on GPU...
[Audio] Whisper ready — 4.4s
[Audio] Loading Kokoro TTS...
[Audio] Kokoro ready — 1.0s
[Audio] Smart-Turn loaded — neural end-of-turn active
[Voice] Loading ECAPA-TDNN speaker embedder...
[Voice] ECAPA-TDNN ready — 0.7s
[Voice] Gallery loaded — 1 person(s) with voice profiles
[Vision] MiniFASNet anti-spoofing loaded (2 models, device=cuda)
[EmotionAgent] j-hartmann/emotion-english-distilroberta-base loaded on CPU (shared)
[Pipeline] All systems ready. Watching...
[BrainAgent] Started — watching conversation_log for new turns
[Vision] none
[Vision] Active (WATCHING) — no face
[Audio] Listening...
```

The lines are timestamped on the inside of the turn loop, not at startup. Startup logs are un-timestamped because the timing is dominated by model-load duration which is shown explicitly on each line (`Whisper ready — 4.4s`).

## 10. First-Boot Flow — Enrolling the Best Friend

When `db.get_best_friend()` returns None, the pipeline enters `first_boot_flow()`. This is a deliberately slow, conversational sequence — the goal is for the user to feel *greeted into* the system, not enrolled into it.

### 10.1 The dialogue

The flow is three exchanges:

1. **System**: "Hey there... are you my best friend?"
2. **User**: (something affirmative, e.g. "Yeah, I am.")
3. **System**: "Wow! What's your name?"
4. **User**: "My name is Jagan."
5. **System**: "Wait, let me see you clearly, Jagan... I want to remember you from now on."
6. *(enrollment capture — ~12 seconds, 20 face embeddings, anti-spoof gated)*
7. **System**: "Got you, Jagan! From now on, you're my best friend. I'll never forget you."

### 10.2 What happens under the hood

- The pipeline enters `PipelineState.ENROLLING`.
- For up to ~12 seconds, the vision loop captures 20 distinct face embeddings from varying angles, each passed through V1 (quality), V2 (yaw), V3 (temporal buffer), anti-spoof, and diversity gates.
- Each passing embedding is written to `embeddings` table with `source='enrollment'`.
- When 20 samples are collected (or time runs out with at least N_INITIAL_FACE=5), the person is written to `persons` with `person_type='best_friend'`.
- `FAISS._rebuild_faiss()` rebuilds the index from DB.
- A greeting is generated and spoken.
- Pipeline transitions ENROLLING → WATCHING.

### 10.3 Why this is a separate flow from background enrollment

A background-enrollment flow (that we used to have) would have been more convenient: user walks in front of the camera, system enrolls them silently, asks their name later. We rejected this because:

- The first interaction shapes the relationship. If the first thing the system does is "secretly memorise your face while you're standing in front of it", the feel is wrong. The explicit "Wait, let me see you clearly" turns the act of capture into consent.
- Anti-spoof is more reliable when the user is actively facing the camera. Passive enrollment can pick up angles the anti-spoof model has never seen.
- The best friend slot is privileged. An accidental enrollment of the wrong person into `best_friend` would be catastrophic for privacy and control. The explicit dialogue makes mis-enrollment essentially impossible.

### 10.4 Anti-spoof gate placement (Session 22)

Anti-spoof is called inside the capture loop *after* V1 (quality ≥ 0.50) and V2 (yaw ≤ 60°) gates passed. So the sequence per candidate frame is:

```
face detected
  ↓ V1: face_quality_score >= FACE_QUALITY_ENROLLMENT (0.50)
  ↓ V2: |estimate_yaw_from_landmarks| <= 60°
  ↓ AntiSpoofChecker.verify_live(frame, bbox)
  ↓ V3: TemporalEmbeddingBuffer.add_and_pool(track_id, emb)
  ↓ Diversity gate: cos-sim with existing gallery < 0.92
  ↓ INSERT INTO embeddings
```

If anti-spoof fails for every single candidate frame in the capture window, the `spoof_blocked` flag trips and the system says "I can't confirm you're real — try again in better lighting." This is a user-facing message, not a silent fail.

## 11. Daily-Use Flow — Returning User

When `db.get_best_friend()` returns the best friend, the pipeline enters WATCHING immediately. This is the hot path — the system spends 99% of its life here.

### 11.1 The WATCHING loop

- Camera and mic are active.
- Vision detects and recognises faces. On first recognition of a known person, the greeting cooldown (`GREET_COOLDOWN=300s`) is checked. If expired, `_open_session(person_id, name, "face")` opens a session and a greeting is generated and spoken.
- Voice triggers are handled by the same loop via the ambient listen sub-path (§19) — if somebody speaks without being on-camera, the pipeline voice-identifies them, opens a voice-started session if the voice matches a known person, or applies the engagement gate if the voice doesn't match anyone in the gallery.
- Once a session is open, the pipeline transitions to LISTENING and enters the conversation sub-loop.

### 11.2 The conversation sub-loop

- Pipeline state is LISTENING.
- The audio module captures a turn (`listen()`), ending at Smart-Turn completion or SILENCE_DURATION fallback.
- Voice ID runs on the captured audio.
- `_resolve_actual_speaker` resolves who actually spoke (may be a different person than the current session holder).
- If the resolution says "switch", the session switches.
- `conversation_turn(actual_pid, text, audio_buf)` runs. The brain generates a response; TTS speaks it; the pipeline updates session state; logs the turn.
- Voice is accumulated via Path A/B/C.
- Pipeline returns to LISTENING for the next turn in the same session, unless the session expired (see §51).

### 11.3 KAIROS — proactive initiation

If the user has been silent for `KAIROS_SILENCE_THRESHOLD=30s` while in an active session, the brain is poked with a prompt: "The user has been silent for 30 seconds. Say something natural if you have a question or observation, or respond with the single word SILENT if you don't." The brain either initiates or stays silent. This is the only place the robot volunteers speech unprompted.

### 11.4 Session closure

A session closes when:
- VOICE_SESSION_TIMEOUT=30s has elapsed since the last time the holder spoke (voice-started session).
- FACE_LOSS_GRACE=10s has elapsed since their face was last seen (face-started session).
- Another person's voice confidently switched the session away and the displaced session has been silent for VOICE_SESSION_TIMEOUT.
- A force-close trigger fires (DISPUTE_MAX_DURATION, SHUTDOWN tool, etc.).

On close, `_close_session(pid)` runs, the BrainOrchestrator's `notify_session_end(pid, name)` fires, and any async session-end tasks spawn (household extraction, insight episode storage, prompt pref final analysis, visitor alert if applicable).

## 12. Shutdown — Graceful and Forced

### 12.1 Graceful shutdown (Ctrl+C once)

When SIGINT is received:
1. `_shutdown_event.set()` signals every async task.
2. The main event loop exits its `while not _shutdown_event.is_set():` guard.
3. `Camera.close()` releases the cv2 capture device.
4. `BrainOrchestrator.shutdown()` cancels the agent loop and closes `BrainDB._conn` cleanly. Any pending writes are flushed via `_safe_commit`.
5. Open `_voice_tasks` (async accumulation tasks) are awaited with a 2-second timeout.
6. `_cloud_monitor_task` is cancelled.
7. `state.py::write_state(status="offline")` writes the final IPC state.
8. The Python process exits.

Total graceful-shutdown time: ~2 seconds.

### 12.2 Forced shutdown (Ctrl+C twice)

If a second SIGINT arrives during graceful shutdown (e.g., the agent loop is hanging on a DB commit), the signal handler calls `os._exit(1)`. This bypasses normal Python cleanup — the DB journal may be in WAL, which SQLite recovers from on next open. FAISS index in memory is lost; it's rebuilt from DB at next startup.

This is the escape hatch. We never want a user to have to `kill -9` the process.

### 12.3 Why not just register atexit handlers?

We used to. They ran unreliably on Windows because `atexit` is called for normal interpreter shutdown, not for SIGINT-triggered exits. Explicit signal handling gives us deterministic behaviour.

## 13. Factory Reset

Factory reset wipes every piece of runtime state and returns the system to a "never been run" state. This is destructive and not reversible short of restoring a backup.

### 13.1 What gets wiped

- `faces/faces.db` (all persons, embeddings, voice embeddings, conversation log, silent observations, visitor log)
- `faces/faiss.index` (rebuilt empty)
- `faces/brain.db` (all knowledge, schema catalog, agent log, preferences, episodes, nudges, household facts, social mentions)
- `faces/brain_graph/` (Kuzu directory, removed via `shutil.rmtree`)
- `faces/photos/` (face crops if present)
- `faces/state.json` (dashboard IPC state)
- `faces/sim_session_state.json` (sim runner state, if present)

### 13.2 What doesn't get wiped

- Models in `models/`
- Python venv
- Configuration in `.env`
- This documentation
- Log files outside `faces/`

### 13.3 How to trigger

Three paths:

1. **Dashboard**: there is a "Reset" button. It writes `faces/reset_request.json`. The pipeline sees it on next startup check or mid-run check and acts.
2. **Manual**: delete `faces/` and re-run the pipeline. The directory is auto-recreated at startup.
3. **CLI (planned)**: `python -m dog_ai reset` — not yet implemented.

### 13.4 What happens after reset

- Pipeline re-enters first-boot flow on next startup.
- Dashboard state shows "not-enrolled".
- The user must re-enroll the best friend.

### 13.5 Why we keep a separate `reset_request.json` file

The pipeline and dashboard are different processes. They share state via atomic JSON files. We want the reset to be *acknowledged*: the dashboard should know whether the reset succeeded, failed, or is pending. Hence request/result pairs. This pattern is consistent with `enroll_request.json` / `enroll_result.json`.

---
---

# Part III — The Core Loop

## 14. Pipeline States and Transitions

Kara-OS is a finite-state machine at the top level. At any moment the pipeline is in exactly one of these states:

| State | What it means | What runs |
|---|---|---|
| `WATCHING` | No active session. Camera + mic alive. Looking for a face or voice trigger. | Background vision scan, ambient listen, scene heartbeat |
| `LISTENING` | A session is open. Waiting for the session holder to speak. | `listen()` (mic capture + VAD + Smart-Turn), voice accumulation readiness |
| `THINKING` | User spoke; transcript produced; brain is generating. | Streaming LLM call; sentence buffering; tool-call detection |
| `SPEAKING` | TTS is playing audio. | Kokoro synth + sounddevice playback; echo window active |
| `ENROLLING` | First-boot or explicit enrollment in progress. | Face capture loop with anti-spoof gating |

The states are represented by the `PipelineState` enum (`pipeline.py`). `_set_state(new_state, person_name)` logs the transition (`[Pipeline] State: WATCHING -> LISTENING`) and updates `state.json`.

### 14.1 Legal transitions

```
                ┌─────────────────────┐
                │                     │
                ▼                     │
        ┌─────────────┐               │
        │  WATCHING   │──(face/voice)─┤
        └─────────────┘               │
           │       ▲                  │
         (session  │(session expires) │
          opens)   │                  │
           ▼       │                  │
        ┌─────────────┐               │
   ┌────│  LISTENING  │◀──────────────│
   │    └─────────────┘               │
   │       │                          │
   │     (user speaks)                │
   │       ▼                          │
   │    ┌─────────────┐               │
   │    │  THINKING   │               │
   │    └─────────────┘               │
   │       │                          │
   │     (tokens flow)                │
   │       ▼                          │
   │    ┌─────────────┐               │
   │    │  SPEAKING   │───────────────┘
   │    └─────────────┘
   │       │
   │     (playback done)
   │       │
   └───────┘

ENROLLING branches off WATCHING only at first boot, and returns to WATCHING.
```

Invalid transitions (e.g. WATCHING → SPEAKING without passing through THINKING) are not blocked by assertions because they don't occur in the code — each transition has exactly one call site.

### 14.2 Why this specific state machine

We considered finer-grained states (TRANSCRIBING, EXTRACTING, ACCUMULATING) and rejected them. The operator (a human watching the dashboard) cares about the five high-level states; everything else is background. A five-state machine is small enough to reason about completely; a fifteen-state machine would accumulate stale states and redundant transitions.

## 15. Main Event Loop Architecture

### 15.1 Entry point

`pipeline.py::main()` constructs the event loop, installs signal handlers, and awaits `run()`. On Windows we use the selector event loop; on Linux the default is fine. We do not use `uvloop` — the marginal speedup isn't worth the extra dependency.

### 15.2 `run()` as a coroutine tree

`run()` spawns several long-lived tasks and one main coroutine:

```
run()
├── _background_vision_loop()           — scans camera every ~1s, updates _persons_in_frame
├── _dream_loop()                       — idle-triggered consolidation
├── _cloud_retry_loop() [spawned lazily] — re-pings Together.ai when CloudState=SICK
├── _brain_orchestrator.start()         — polls conversation_log every 2s
└── main watch/listen loop              — the primary work
```

Each task is independent; they communicate via shared module-level dicts (`_active_sessions`, `_persons_in_frame`, `_voice_gallery`, `_voice_gallery_sizes`, ...). There are no locks because they all run on the same event loop thread; the concurrency is interleaved awaits, not preemptive threading.

### 15.3 Blocking call handling

Whisper STT, Kokoro TTS, DB writes, and FAISS search are blocking. Each is wrapped in `loop.run_in_executor(None, fn, *args)`. The default executor is a ThreadPoolExecutor with a small number of threads (Python's default). This gives us true parallelism between the event loop and those heavy calls — the mic keeps capturing during Whisper STT, for example.

### 15.4 Signal handling

`signal.signal(signal.SIGINT, _sigint_handler)` installs a handler that sets `_shutdown_event`. On the second SIGINT within 2 seconds, the handler calls `os._exit(1)`.

On Linux we would prefer `loop.add_signal_handler(signal.SIGINT, ...)` for better integration, but that API doesn't exist on Windows. The explicit handler works on both platforms.

### 15.5 The main watch/listen loop pseudocode

```python
while not _shutdown_event.is_set():
    if _pipeline_state == PipelineState.WATCHING:
        # Scene heartbeat runs in background; this loop polls for events
        await asyncio.sleep(0.05)

        # Check if ambient speech occurred (handled by the audio module)
        if ambient_speech_detected:
            # Branch A: voice-first engagement
            handle_ambient_speech()

        # Check if a face entered and deserves greeting
        for pid, info in _persons_in_frame.items():
            if info.get("source") != "voice" and _greet_cooldown_ok(pid):
                _open_session(pid, info["name"], "face")
                greet_and_enter_listening(pid)

    elif _pipeline_state == PipelineState.LISTENING:
        # Capture next turn
        audio_buf, text = await listen(...)
        if not text.strip():
            # empty — stay listening, or close expired sessions
            _expire_stale_sessions()
            continue

        await conversation_turn(actual_pid, text, audio_buf)

    # Background tasks run interleaved with the above
```

This is a simplified sketch; the real code in `pipeline.py` is ~3761 lines because it handles dozens of edge cases (multi-person, dispute, engagement gate, session expiry cleanup, etc.). The structural shape, though, is exactly this.

## 16. Async Architecture and Concurrency Model

### 16.1 Single-threaded cooperative scheduling

All user code lives on one event loop. There are no `threading.Thread` instances in the pipeline proper (except the ones created internally by `sounddevice` for audio I/O and the ThreadPoolExecutor that `run_in_executor` uses).

The advantage: no data races on `_active_sessions`, `_persons_in_frame`, etc. A reader can iterate those dicts without worrying about mid-iteration mutation from another thread. (Of course an `await` *within* iteration could still cause trouble — iterating a dict and awaiting is a classic bug; we don't do that.)

### 16.2 Executor boundaries — the list

Every place we call `run_in_executor`:

- `transcribe(audio_buf)` → Whisper STT
- `synthesize(sentence, language)` → Kokoro/Piper TTS
- `sd.wait()` → waits for sounddevice playback completion without blocking the loop
- `voice_mod.identify(audio_buf, gallery, threshold)` → ECAPA-TDNN
- `voice_mod.diarize(audio_buf, gallery, threshold)` → within-utterance diarization
- `db.recognize(emb, threshold)` → FAISS search
- `db.add_embedding(...)` → SQLite insert
- `db.add_voice_embedding(...)` → SQLite insert + voice gallery rebuild
- `db.load_voice_profile_for(pid)` → read + mean pool
- `detector.detect(frame)` → RetinaFace (ONNX GPU)
- `embedder.embed(crops)` → AdaFace (ONNX GPU)

### 16.3 Task lifecycle management

- `_voice_tasks: set[asyncio.Task]` holds currently-running voice accumulation tasks. Each task is added on creation and removed via `add_done_callback(_voice_tasks.discard)`. On shutdown we `await asyncio.gather(*_voice_tasks, return_exceptions=True)` with a 2-second timeout.
- `_cloud_monitor_task` is spawned lazily when CloudState transitions to SICK. On shutdown it is explicitly cancelled.
- The BrainOrchestrator runs its own loop internally; `shutdown()` cancels and awaits.

### 16.4 What we explicitly don't do

- No `asyncio.Lock()` on shared state. The single-thread invariant makes locks useless.
- No `multiprocessing` fork. All our models need GPU; forking GPU processes is painful.
- No external message bus. `state.json` is the only IPC and it's one-way (pipeline → dashboard).

## 17. Scene Heartbeat

The "scene heartbeat" is the mechanism that keeps the brain's `<<<SCENE>>>` block and the dashboard's state view up to date with who is currently in the room.

### 17.1 Data sources

- `_persons_in_frame: dict[pid, {name, conf, last_seen, last_recognized_at, source}]`
- `source="face"` entries come from the background vision scan (face detection + recognition).
- `source="voice"` entries come from the per-turn voice ID (pipeline.py ~line 3304 after §Bug B).

### 17.2 Prune rule

Every vision scan (~1 Hz), entries older than `SCENE_STALE_SECS=5.0` are removed. Voice-source entries that expire while a session is still active emit the `[Voice] {name} no longer heard` log (Obs 4, post-review).

### 17.3 `[Vision]` heartbeat log

```python
if _det_count_bv == 0:
    _vis_report_now = "none"
else:
    _rnames = sorted(
        v["name"] for v in _persons_in_frame.values()
        if (_now_vr - v["last_seen"] < VOICE_ROUTING_FACE_STALE_SECS
            and v.get("source") != "voice")  # Bug B fix
    )
    # ... append "unrecognized", "Nx unrecognized" for camera-only hits
    _vis_report_now = ", ".join(_vr_parts) if _vr_parts else "none"

if _vis_report_now != _last_vision_report_str:
    print(f"[Vision] {_vis_report_now}")
```

The log only prints on change (Session 38 dedup) so a stationary scene doesn't spam. The typical log sequence during a conversation looks like:

```
[Vision] Jagan
[Vision] none
[Vision] Jagan
[Vision] none
[Vision] Jagan, Chloe
...
```

Each line indicates "what faces are currently visible on camera." Voice-only speakers are intentionally excluded.

### 17.4 `[Vision] Active (STATE) — names` heartbeat

Distinct from the above, the pipeline also emits a heartbeat every 30 seconds that includes the current state:

```
[Vision] Active (LISTENING) — Jagan, Chloe, visitor
```

This includes *voice-only* entries (to show them as in-session). The split between the two heartbeats is intentional — `[Vision] names` is about on-camera presence; `[Vision] Active (STATE) — names` is about session membership.

## 18. Background Vision Loop

`_background_vision_loop()` is the async task that drives the scene heartbeat. Every ~1 second, independent of the main loop, it:

1. Reads one frame from the camera via `camera.read()`.
2. Runs `FaceDetector.detect(frame)` → list of detections with bbox, landmarks, track_id.
3. For each detection with a valid track_id (SORT-confirmed, not jitter):
   - Crop the face, run V1 quality → if below threshold, skip.
   - Run V2 yaw estimation → if above 60°, skip.
   - Pass through V3 temporal buffer (mean-pool 5 frames) via `track_id`.
   - Run V4 adaptive threshold on the pooled embedding.
   - Call `db.recognize(emb, threshold)` → (pid, name, conf).
   - If recognised, update `_persons_in_frame[pid]` with `source="face"`.
   - If not recognised, record the track_id in `_unrecognized_tracks` and cache the embedding in `_unrecognized_embeddings[track_id]` for potential progressive enrollment later.
4. Prune stale entries from `_persons_in_frame` (>5s old).
5. Update `identity_evidence` for active sessions whose pid was just recognised (Session 61 Step 3).
6. Check the new-face-flag to trigger greetings.

### 18.1 Why every 1 second and not every frame

Running the whole pipeline on every frame (~30 Hz) would saturate the GPU and starve the main loop. Running it every 5th frame (via SORT_DETECT_EVERY=5) gives us ~6 Hz — enough to track smooth motion and detect new faces within ~150ms. The 1-second scene heartbeat is separate from the SORT-every-5-frames decision; it's the upper loop that pulls a frame and processes it.

### 18.2 The tradeoff we accepted

A person who enters the frame and *immediately* starts speaking may not be recognised fast enough to be attributed correctly on their first utterance. We rely on the voice ID path in `_resolve_actual_speaker` to catch this — if the face is still warming up, voice provides the identity. In practice this works well because by the second turn the face scan has caught up.

### 18.3 Anti-spoof call placement in the background loop

Historically we did not anti-spoof in the background scan because every scan hitting the GPU twice (embedding + anti-spoof) is wasteful. We only anti-spoof at three points:

1. **First-boot enrollment** — inside the capture loop, after V1+V2 passed.
2. **Regular enrollment** (`enrollment_flow`) — same placement.
3. **Greeting a known person** — in `_greet_if_ready(pid)` before we say hello, verify the face is live.

Self-update writes (`recognition_update` source) require `verify_live(...)` as of Session 51; this is the fourth anti-spoof site.

## 19. Ambient Listening

"Ambient listening" is the name for the pipeline's capacity to hear a voice when no one is on camera and no session is open. It is the mechanism by which a voice-only speaker (like Chloe sitting behind the laptop) can engage the system.

### 19.1 The flow

- WATCHING state, no active session.
- Mic captures speech. The audio module's VAD + Smart-Turn decide the turn boundary.
- Whisper transcribes.
- ECAPA-TDNN voice ID runs on the audio buffer.
- If voice matches a known person with confidence ≥ VOICE_SPEAKER_SWITCH_THRESHOLD (0.50), open a voice-started session for them.
- If voice does not match, open a *stranger* session with a fresh pid (`stranger_<uuid>`).
- Apply the engagement gate (stranger workflow, §65-67).
- Transition to LISTENING / THINKING as appropriate.

### 19.2 `_ambient_recognized_name` (removed)

We used to carry an `_ambient_recognized_name` through the flow as a shim. It was removed in Session 42 (Issue #26) because the same information is now carried through the structured `vision_state` and `voice_state` dicts passed to the brain.

### 19.3 Why the engagement gate matters for ambient

If we engaged every voice we heard, anyone walking past could wake the system by speaking. The gate — "you must say the system's name to get a response" — is what makes the system feel *chosen* rather than *triggering*.

The gate has a phonetic fallback (Session 41): Double Metaphone via `jellyfish` accepts phonetic variants. So "Kara", "Karah", "Cara" all engage the same gate.

---
---

# Part IV — Vision

## 20. RetinaFace Detection

### 20.1 Model and why we picked it

RetinaFace from the InsightFace buffalo_l bundle is our face detector. It is a multi-task network that outputs:
- Bounding boxes for each detected face,
- Confidence scores per box,
- Five facial landmarks per box (left eye, right eye, nose tip, left mouth, right mouth).

We picked it because:
- **State-of-the-art recall on small faces.** Our camera is 1280×720 and the user is often 1-2m away. Smaller faces are typical; many detectors degrade below 80×80 pixels. RetinaFace remains usable to 40×40.
- **The five landmarks are free.** We use them for yaw estimation in V2 quality gating and for face alignment in AdaFace preprocessing.
- **ONNX-runnable on GPU.** onnxruntime-gpu loads the network and keeps the GPU context warm.
- **Bundled with the buffalo_l pack.** One download gives us detection + landmarks + ArcFace embedding weights (we don't use the ArcFace part — we use AdaFace instead — but the convenience of a single model pack matters).

### 20.2 `FaceDetector.detect(frame) -> list[Detection]`

```python
class FaceDetector:
    def __init__(self):
        self._model = FaceAnalysis(name="buffalo_l", providers=["CUDAExecutionProvider"])
        self._model.prepare(ctx_id=0, det_size=(640, 640))

    def detect(self, frame: np.ndarray) -> list[Detection]:
        faces = self._model.get(frame)
        return [Detection.from_insightface(f) for f in faces]
```

The `Detection` dataclass carries `bbox`, `score`, `landmarks`, and (after SORT) `track_id`.

### 20.3 Confidence threshold

`DETECTION_CONFIDENCE=0.50` rejects faces below 50% confidence. We lowered this from 0.70 when we noticed that upward-angle camera setups (e.g., a laptop on a desk) produce detection scores in the 0.5-0.7 range for non-frontal faces — the old threshold was losing real faces.

### 20.4 Cost

One `detect()` call at 640×640 input size: ~15 ms on the dev GPU. Running it on every frame (30 FPS) would be 450 ms/s on the GPU, half our budget, and would choke the other models. Hence SORT-every-5-frames (§21).

## 21. SORT Tracking with Kalman Filter

### 21.1 What SORT is

SORT ("Simple Online and Realtime Tracking") is a lightweight tracker that maintains identity across frames by:
1. Predicting each existing track's bounding box in the next frame using a Kalman filter (constant velocity model).
2. Matching new detections to predictions via IoU (intersection over union).
3. Assigning matches using the Hungarian algorithm (linear_sum_assignment from scipy.optimize).
4. Creating new tracks for unmatched detections; killing tracks that go unmatched for SORT_MAX_AGE frames.

### 21.2 Why we need it

Face detection runs every 5th frame. Without tracking, we'd lose identity continuity between detections — a person could be "a new person" every 150ms. SORT extrapolates between detections using Kalman, so the same person gets the same `track_id` across the whole time they are in frame.

This matters for:
- **Progressive enrollment** — we need to accumulate V3 (temporal buffer) entries keyed by stable track_id.
- **Unrecognized-face caching** — `_unrecognized_embeddings[track_id]` caches the embedding of an unknown face so that if they later pass the engagement gate we can enroll their face. Track instability would lose the embedding.
- **Continuity heartbeat** — the `[Vision]` log's `N x unrecognized` count is stable over motion only because the track_ids are stable.

### 21.3 Our Hungarian-vs-greedy fix

Before Session 24 we used a greedy match: each detection claimed its best track. This caused races where a track could be multi-claimed in the same frame. We switched to `linear_sum_assignment` which guarantees a 1:1 optimal assignment. That fix is permanent; regression test guards it.

### 21.4 Parameters

- `SORT_DETECT_EVERY=5` — run RetinaFace every 5 frames; Kalman-predict in between.
- `SORT_MAX_AGE=30` — keep a track alive for 30 frames without a detection match (1 second at 30 FPS). Accommodates brief occlusion.
- `SORT_MIN_HITS=2` — a track must be matched on at least 2 detections before it's "confirmed". Filters out detection jitter.

## 22. AdaFace IR101 Embedding

### 22.1 Why AdaFace over ArcFace

ArcFace was the dominant face embedder for years. AdaFace improves on it specifically for open-set recognition with quality-varying inputs — which is exactly our situation (indoor lighting, varying poses, camera angle). In the 0.28-0.45 cosine-similarity region, AdaFace has a more stable EER (equal error rate) which means our threshold doesn't have to be painfully specific to avoid false positives.

We use the IR101 backbone (iResNet-101) trained on WebFace12M-42M. 512-dimensional embeddings, L2-normalised.

### 22.2 The embedder

```python
class FaceEmbedder:
    def __init__(self):
        sess_options = ort.SessionOptions()
        self._session = ort.InferenceSession(
            "models/adaface_ir101.onnx",
            sess_options=sess_options,
            providers=["CUDAExecutionProvider"],
        )

    def embed(self, face_crops: list[np.ndarray]) -> np.ndarray:
        # Preprocess: resize to 112x112, normalize, transpose to NCHW
        batch = preprocess(face_crops)
        # Run
        emb = self._session.run(None, {"input": batch})[0]
        # L2-normalize for cosine similarity
        emb = emb / np.linalg.norm(emb, axis=1, keepdims=True)
        return emb
```

### 22.3 Why L2-normalise at embedding time

Cosine similarity is dot product on unit vectors. If the embeddings are already unit-length, FAISS IndexFlatIP returns cosine similarity directly. This means we never have to call cosine similarity — a dot product suffices. Cheap.

### 22.4 Alignment via landmarks

AdaFace (like ArcFace) expects faces aligned to a canonical pose using the 5 landmarks. RetinaFace produces those landmarks; the embedder preprocesses each crop with a similarity transform that maps the landmarks onto reference positions. Without alignment, embeddings of the same face at different yaws cluster poorly and recognition fails.

## 23. Face Quality Gates V1 through V4

These are four progressively stronger gates that determine which face crops are "good enough" for different uses. All live in `core/vision.py`.

### 23.1 V1 — `face_quality_score(crop) -> float`

A heuristic quality score in [0.05, 1.0] combining:
- **Size factor** — normalised face bbox area.
- **Blur factor** — Laplacian variance indicates focus.
- **Brightness factor** — mean luminance relative to a target.

Each factor is in [0, 1] and the final score is their product (or a soft combination). The floor of 0.05 means "a face is detectably present even if it's terrible quality."

Four cut-off points:
- `FACE_QUALITY_PRESENCE=0.05` — face present.
- `FACE_QUALITY_RECOGNITION=0.20` — recognition viable.
- `FACE_QUALITY_ENROLLMENT=0.50` — clean enough to write to gallery.
- `FACE_QUALITY_SELF_UPDATE=0.70` — high-quality crop required for gallery self-update.

The gate used depends on the caller:
- Enrollment path uses 0.50.
- Recognition uses 0.20.
- `recognition_update` source uses 0.70.

### 23.2 V2 — `estimate_yaw_from_landmarks(landmarks) -> float`

Estimates yaw angle from the five facial landmarks using the relative positions of the eyes and nose. Returns degrees in roughly `[-90, 90]`.

Gate: enrollment rejects faces with `|yaw| > 60°`. Recognition accepts any yaw (we want to match even profile views).

### 23.3 V3 — `TemporalEmbeddingBuffer`

Mean-pools the last 5 frames of embeddings keyed by SORT `track_id`. Reduces noise from single-frame embedding fluctuation. Empty for new tracks; returns the current embedding unchanged when pool depth < 5; returns the mean when ≥ 5.

Used as the input to V4 for recognition. If the pool has fewer than 5 entries, the recognition threshold is bumped up by 0.05 to compensate for the extra uncertainty.

### 23.4 V4 — `adaptive_threshold(quality_score, base_threshold) -> float`

Scales `RECOGNITION_THRESHOLD=0.28` upward when quality is low. The idea: on a noisy crop, we want more margin before calling it a match; on a clean crop, the base threshold is fine.

```python
def adaptive_threshold(quality: float, base: float) -> float:
    # quality in [0.05, 1.0]; base = RECOGNITION_THRESHOLD
    if quality >= 1.0:
        return base
    # Linear scale: quality 1.0 -> base, quality 0.2 -> base+0.05
    adjustment = (1.0 - quality) * 0.05
    return min(base + adjustment, 0.45)  # cap at a reasonable upper
```

### 23.5 V1-V4 composed

The full recognition pipeline:

```
raw detection
  ↓ V1: face_quality_score -> q
  ↓    if q < FACE_QUALITY_RECOGNITION (0.20): drop
  ↓ V2: yaw check (recognition does not reject on yaw; enrollment does)
  ↓ V3: temporal buffer; mean-pool last 5 frames for this track_id
  ↓ V4: adaptive_threshold(q, RECOGNITION_THRESHOLD)
  ↓ db.recognize(emb, threshold)
```

## 24. Anti-Spoofing — MiniFASNet Ensemble

### 24.1 The threat

A photo of the best friend held up to the camera. A laptop screen showing a recorded video. A printed face on paper. All three should be rejected; only genuine live faces should pass.

### 24.2 The model

MiniFASNet from minivision-ai. We vendored the architecture (`core/_minifasnet/`) and use two pretrained weight files:
- `2.7_80x80_MiniFASNetV2.pth` — V2 backbone, trained at 2.7× bbox scale crop.
- `4_0_0_80x80_MiniFASNetV1SE.pth` — V1SE backbone, trained at 4.0× bbox scale crop.

Both output 3-class logits:
- Class 0: fake (print/photo)
- Class 1: live
- Class 2: replay (screen)

### 24.3 Ensemble inference

```python
def is_live(self, frame, bbox) -> tuple[bool, float]:
    probs_total = np.zeros(3)
    for model, scale in self._models:
        crop = crop_with_scale(frame, bbox, scale=scale)
        crop = resize(crop, (80, 80))
        tensor = torch.from_numpy(crop).permute(2, 0, 1).float().unsqueeze(0)
        # IMPORTANT: no .div(255.0) — upstream trained on raw [0,255] float.
        # Session 59 bug: dividing by 255 caused 100% false-reject.
        logits = model(tensor.to(self._device))
        probs = torch.softmax(logits, dim=1).cpu().numpy()[0]
        probs_total += probs
    probs_avg = probs_total / len(self._models)
    argmax = int(np.argmax(probs_avg))
    live_prob = float(probs_avg[1])
    return (argmax == 1 and live_prob >= ANTISPOOFING_THRESHOLD, live_prob)
```

Two crops at different scales, two models, softmax average, argmax decides. Threshold `ANTISPOOFING_THRESHOLD=0.5` was validated in Session 60 to give ≥ 0.95 live-prob on genuine faces and ~0.016 on photos.

### 24.4 `verify_live(frame, bbox, checker)` wrapper

The higher-level wrapper handles:
- `checker.available` check — if the models failed to load, returns True (fail-safe).
- Logging — the `[Anti-spoof]` line with probs or summary.
- Stats accumulation for the rolling-summary log.

Callers should always use `verify_live(...)`, not raw `is_live(...)`. Four call sites:
- `_greet_if_ready(pid)` — before greeting a known person.
- `first_boot_flow()` capture loop.
- `enrollment_flow()` capture loop.
- `add_embedding(source='recognition_update')` — anti-poisoning gate (Session 51).

### 24.5 Rolling summary log

Per-frame logs are noisy. `LOG_ANTISPOOF_SUMMARY=True` emits a compact summary every 100 calls:

```
[Anti-spoof] summary over last 100 frames: min=0.93 mean=0.97 max=1.00 rejects=0 thr=0.50
```

This gives drift visibility over time (camera aging, lighting changes) without spamming.

### 24.6 P0.S1 — Anti-Spoof on Every Face Match (the gap closure)

Session 52 stood up the MiniFASNet ensemble; Section 24.1-24.5 above describes how the checker itself works. P0.S1 closed the orthogonal question: **does every face match the system performs actually consume that checker, or are some paths quietly bypassing it?**

#### The premise-reset finding

Casual reading of pipeline.py suggested that `recognition_update` (the most poisoning-prone path — silently writes embeddings into a known person's gallery on every high-confidence match) was the only at-risk surface. **Phase 0 audit reset that premise.**

`recognition_update` at `pipeline.py:6469-6478` was already strictest-fail-closed gated: `verify_live` runs inline, exception swallowed → fail-closed reject, and on failure the code skips the embedding write entirely. Verified by code reading, not assumption. The narrative everyone carried in their head ("recognition_update is the dangerous path") was already the safe path.

The **actual gap** lived at `pipeline.py:7690` — the `progressive_enroll` site that fires when a stranger first says the system name and the engagement gate opens. That path read the face embedding straight out of `_track_store` (captured at scan time by `_background_vision_loop`) and called `db.add_embedding(_cur_pid, _gate_emb, "progressive_enroll")` **without any anti-spoof check at all**. A presentation attack against a stranger session could seed a face gallery from the very first turn.

Same shape as P0.10 Phase 0 audit's wrong-premise catch (legacy `_resolve_actual_speaker` was thought to be the correctness baseline; was actually the buggy path). Phase 0 saved Phase 1-3 from chasing the wrong target. Bank as sub-pattern A under Spec-First Review Cycle: Phase 0 audit catches wrong premise.

#### The four load-bearing properties

**a. Verdict-embedding co-temporality (C0)** — The verdict and the embedding must come from the *same frame*. `_background_vision_loop` captures the embedding via `embedder.embed(_crop)` where `_crop = frame[bbox]`; the SAME `frame` then goes to `_classify_anti_spoof_verdict(frame, _det.bbox, _anti_spoof_checker)`. Both results land in `TrackEntry` via a single `await _track_store.upsert_embedding_with_verdict(...)` call — atomic from any consumer's perspective. The consumer at progressive_enroll reads them together via `peek_anti_spoof_verdict(_gate_track)`. No cross-frame caching: a stranger who shows a real face once and then swaps to a photo cannot get the live verdict from the first frame attached to the photo embedding from the second.

The atomic upsert is enforced by `TrackStore.upsert_embedding_with_verdict` taking the lock once and writing all five fields (embedding, anti_spoof_live, anti_spoof_score, anti_spoof_reason, captured_at, bbox) under it. The structural test `test_track_store_upsert_with_verdict_is_atomically_observable` runs 1 writer + 50 readers in tight async loops and asserts zero torn-state observations (embedding set without verdict, or vice versa).

The C0 same-frame discipline at the call-site level is enforced by `# P0S1-C0:` marker comments + a structural test that asserts within K=25 lines following each marker, the `_crop = frame[...]` slice, the `embedder.embed(_crop)` call, and the `verify_live(frame, ...)` / `_classify_anti_spoof_verdict(frame, ...)` call all reference the same `frame` variable. Marker-comment route chosen over Plan v2's AST graph walk because `run_in_executor(None, embedder.embed, _crop)` makes `embedder.embed` a Name expression (not a Call node), defeating AST provenance walking — see §14b.2 below.

**b. Verdict-required-for-protected-source (D1 + D5)** — Hybrid enforcement. Every call site computes `verify_live` (or reuses an already-captured verdict) and passes `anti_spoof_verdict=` to `db.add_embedding`. The `add_embedding` function itself contains a catch-all gate at `core/db.py:588-625`: if `source` is in `ALLOWED_EMBEDDING_SOURCES_REQUIRING_ANTI_SPOOF` (== the full `VALID_EMBEDDING_SOURCES` set after D4 deleted `legacy_unknown`), then `anti_spoof_verdict` must be `True` or the write is refused with a `[FaceDB] add_embedding rejected for {pid} source={src} verdict={v!r} — anti-spoof gate blocks write (P0.S1 D1 catch-all)` log line. The hybrid is the safety net: per-call-site captures the verdict context (frame, score, reason); catch-all blocks any future caller that forgets the upstream gate.

The frozenset's deletion of `legacy_unknown` (D4) is the strongest possible enforcement — a runtime `AssertionError: add_embedding called with unknown source` catches developer mistakes BEFORE the code ships. AST scans add CI-time enforcement. Path 1b execution (architect's call during Phase 1) made `source` a required kwarg, eliminating the silent default backdoor.

**c. Fail-closed-on-unavailable (C1)** — Four reason codes, never collapsed:
- `ANTI_SPOOF_REASON_PASSED` — `verify_live` returned True.
- `ANTI_SPOOF_REASON_REJECTED` — `verify_live` returned False.
- `ANTI_SPOOF_REASON_UNAVAILABLE` — `checker.available` is False or checker is None (model failed to load, or anti-spoof disabled in config).
- `ANTI_SPOOF_REASON_NO_VERDICT` — no verdict was captured for the track (e.g. progressive_enroll fires with `_gate_live=None` because the verdict TTL aged out).

These flow end-to-end. `_classify_anti_spoof_verdict` returns the `(live, score, reason)` triple. `TrackEntry` stores all three. `peek_anti_spoof_verdict` returns them to progressive_enroll. The rejection-store records the reason. `WatchdogAgent.report_anti_spoof_rejection` stores the reason in alert metadata so dashboard / replay can branch on it. Operators distinguish hardware-down (`unavailable`) from active attack (`rejected`) at every layer, not just at the structural level.

`VisionFramePayload.anti_spoof_live` was widened from `bool` to `Optional[bool]` for the same reason. The P0.0.7 prerequisite locked 2-state. P0.S1 Phase 2 needed 3-state: True = at least one detection passed in this scan; False = at least one rejected; None = all detections produced no verdict (checker unavailable). Replay distinguishes hardware-down from active attack. The pre-existing P0.0.7 invariant test `test_vision_frame_payload_includes_anti_spoof_fields` was updated with explicit rationale documenting the deliberate widening — not a regression, a semantic upgrade.

**d. Exact-equality burst dedup (C2 + §14b.1)** — Per-track, not per-pid. The `AntiSpoofRejectionStore` records timestamps keyed on SORT `track_id` (because at progressive_enroll gate time, the pid may not exist yet — the track is the only stable correlation key). On every rejection, prune timestamps older than `ANTI_SPOOF_BURST_WINDOW_SECS=60.0`, then return the post-prune count. The pipeline-side dispatcher fires the burst alert **only at exact equality**:

```python
if _rej_count == ANTI_SPOOF_BURST_THRESHOLD:  # exact; NOT >= which would re-fire
    _brain_orchestrator.report_anti_spoof_burst(...)
```

`>=` would re-fire on every subsequent rejection in the window (4th, 5th, 6th, ...). Exact equality fires once per burst. The structural test `test_tripwire_burst_alert_dispatch_exact_equality` regex-scans `pipeline.py` and forbids `>=` / `>` upstream of any `report_anti_spoof_burst(` call site.

Per-track scope: a burst on track_A leaves track_B's count at 0. No cross-track lockout, no voice-channel lockout. The watchdog is for surfacing patterns, not for taking enforcement action against unrelated tracks.

#### AntiSpoofRejectionStore — why a Store subclass instead of a module-level dict

Plan v1 sketched `_anti_spoof_rejection_log: dict[str, list[float]]` at module scope in `pipeline.py`. Plan v2 MED 5 promoted it to a `Store` subclass at `core/anti_spoof_rejection_store.py`. Two reasons:

1. **P0.6 ratchet preservation.** The legacy-global-progress ratchet test `tests/test_p06_legacy_global_progress.py` is at cap=0 — adding a new module-level mutable dict at pipeline.py scope would trip the ratchet. Promoting to a `Store` subclass keeps the migration discipline intact: every piece of mutable global state in pipeline.py lives in a Store with `_lock: asyncio.Lock`, async mutators, sync `peek_*` reads, sync `reset()` for the autouse fixture.

2. **M2 coverage meta-test integration.** The autouse fixture in both `conftest.py` (root) and `tests/conftest.py` loops over `_STORE_NAMES` calling `.reset()` between every test. Adding `_anti_spoof_rejection_store` to the loop required only a 1-line addition to each conftest. Test isolation is structural; no test needs to remember to clear the rejection log.

The Store contract is exactly: `record_rejection(track_id, now, window_secs) -> int` (returns post-prune count), `peek_count(track_id, now, window_secs) -> int` (sync read), `pop(track_id) -> None` (called on session close + stale-prune), `reset() -> None` (autouse fixture).

#### D9 voice-only fallthrough — rejection closes face write but voice channel proceeds

The progressive_enroll branch reads the verdict from track-store. On block (verdict not True), it logs `BLOCKED progressive_enroll face write for {pid} track={tid} reason={reason} score={score}`, calls `_anti_spoof_rejection_store.record_rejection`, dispatches `report_anti_spoof_rejection` to watchdog, and fires the burst alert at exact equality. **What it does NOT do** is set `_face_captured = True`. The else-branch below — Session 64 Bug C's voice-only fallthrough — fires unchanged: bootstrap voice credits seed (`N_INITIAL_VOICE_BOOTSTRAP`), voice accumulation runs with `face_verified=False`, session opens.

The visitor can still speak. They just cannot poison a face gallery. The watchdog catches the pattern across multiple rejections (3 in 60s → burst alert) without blocking any single voice interaction.

D9 tripwire `test_tripwire_voice_only_fallthrough_branch_intact` asserts the rejection elif-branch NEVER sets `_face_captured = True` and DOES call `record_rejection` and `report_anti_spoof_rejection`. A future refactor that flips `_face_captured` on a blocked path would fire the tripwire.

#### D10.c — dashboard yes, TTS no (security UX)

The rejection log is silent to the speaker. No "I think you might be a photo" announcement. The dashboard sees `[Anti-Spoof] BLOCKED` lines + the watchdog alert feed. The principle: **never announce defenses to the attacker**. An attacker who knows the gate fired learns the threshold; an attacker who hears nothing learns nothing.

The watchdog alerts surface to the household-owner-facing dashboard. `report_anti_spoof_rejection` stores severity=`info` (single rejection is usually a transient false negative). `report_anti_spoof_burst` stores severity=`warning` (sustained pattern — investigate). The owner can review patterns at their convenience; the suspected attacker has no idea.

#### Cross-references

- `tests/p0_s1_audit.md` — Phase 0 audit. Threat model + 5 call-site enumeration with verdict-source per site. This is the document that surfaced the premise-reset finding.
- `tests/p0_s1_plan_v1.md` — Plan v1. Locked D1-D10 + C0-C3 contract clauses.
- `tests/p0_s1_plan_v2.md` — Plan v2. Auditor's 9 precision items (HIGH 1/2/3 + MED 4/5/6 + LOW 7/8/9) + §14b in-flight clarifications.
- `tests/test_p0_s1_phase1.py` + `tests/test_p0_s1_phase2.py` + `tests/test_p0_s1_phase3.py` + `tests/test_p0_s1_phase4.py` — 50 tests across the four phases.
- `tests/p0_s1_validation_runbook.md` — TBD. Live canary runbook per Plan v2 §9 (3 independent sessions; closure gate = 9 rejections + 3 negative-control passes + 1 deliberate burst reproduction).
- `complete-plan.md::P0.S1` — full closure summary including discipline-count bumps and bookmarks.

## 25. Lip Tracking

### 25.1 Why

When the user is mid-sentence and pauses briefly, we don't want to cut them off. Smart-Turn catches most cases but can miss pauses in thoughtful speech. Lip tracking gives an additional signal: "lips are still moving, so they probably have more to say."

### 25.2 How

`LipTracker` computes inter-frame pixel diff inside the mouth region (bounded by the mouth landmarks from RetinaFace). If the diff exceeds a threshold, lips are "active."

During recording, if Smart-Turn fires end-of-turn but the lip tracker says active, the recording is extended by up to `LIP_MAX_EXTENSION=2.0` seconds. The terminal log shows `[Audio] Turn end — N speech chunks, M lip extension(s)`.

### 25.3 When it fires

Only when the session holder's face is in view and the lip ROI is extractable. If the user is off-camera, lip tracking is skipped and only Smart-Turn + SILENCE_DURATION decide.

## 26. Camera Reconnection

`Camera` wraps `cv2.VideoCapture` with retry logic. If `read()` returns `(False, None)` for more than a threshold, we close and reopen. Handles:
- USB webcam being briefly disconnected and replugged.
- Camera permission issues on first launch.
- Driver glitches on Windows that sometimes return empty frames.

The backend is chosen by platform:
- Windows: `cv2.CAP_DSHOW` (DirectShow)
- Linux: `cv2.CAP_V4L2`

Set via `sys.platform` at construction time. No user-configurable option.

---
---

# Part V — Audio

## 27. Microphone Capture

`sounddevice.InputStream` is opened at 16 kHz mono float32. Chunks of 512 samples (32 ms) flow into a `asyncio.Queue`. The audio module consumes this queue in its VAD and capture loops.

We chose 16 kHz because Whisper was trained at that rate, Smart-Turn was trained at that rate, and ECAPA-TDNN processes at that rate. Mono because beamforming (which would use stereo) is a future feature (ReSpeaker barge-in). Float32 because that's what every downstream model wants and saving a byte per sample by using int16 isn't worth the conversion.

## 28. Voice Activity Detection — RMS vs Silero

### 28.1 RMS (default on laptop)

`VAD_SWITCH=False` selects RMS-based detection. For each 32ms chunk, we compute root-mean-square energy. Above `RMS_THRESHOLD=0.01` is "speech"; below is "silence."

Trivial implementation (~3 lines), zero model cost, tunable. Works well in a quiet indoor environment.

### 28.2 Silero (planned for Jetson)

`VAD_SWITCH=True` loads the Silero VAD ONNX model. Much better at rejecting non-speech audio (AC hum, keyboard clicks, distant traffic). We keep it off on the laptop because the GPU is already saturated by Whisper + RetinaFace.

### 28.3 The "silence detected" log

Once a speech streak ends and we've observed `SMART_TURN_SILENCE=0.5` seconds of silence, we emit `[Audio] Silence detected — waiting for end-of-turn...`. This can fire multiple times during a single long user turn if the user pauses mid-sentence — each resumed speech chunk resets the silence counter, and the next pause logs again.

Session 38 added a dedup flag to avoid spam; Session 49 bumped the reset threshold from 3 to 9 chunks (~288ms) to suppress micropause oscillation.

## 29. Pre-Roll Buffering

When speech is first detected, the first few hundred milliseconds of the utterance have already happened (the RMS cross was at chunk N but the actual speech began at N-k). We keep a rolling 1-second pre-roll buffer and prepend it to the speech chunks so the transcription includes the onset.

### 29.1 Echo skip

If the system just finished speaking (TTS playback), the first pre-roll chunks may contain the tail of our own audio echoing back from the mic. We skip the first `echo_skip` chunks of pre-roll based on the time since TTS playback ended.

```python
_tts_end_time = <timestamp when last TTS chunk finished>
elapsed_since_tts = now - _tts_end_time
echo_skip = min(max(0, int((ECHO_WINDOW - elapsed_since_tts) / CHUNK_DURATION)), len(pre_roll))
```

The `min(..., len(pre_roll))` cap is Session 36's Bug-15 fix — without it, a small pre-roll buffer could have echo_skip > len(pre_roll), which would have silently discarded the entire pre-roll. The log shows `[Audio] Echo skip: N/M pre-roll chunks trimmed`.

## 30. Smart-Turn Neural End-of-Turn

### 30.1 The problem

A fixed silence threshold is a blunt instrument. Too short and the system cuts off the user mid-sentence. Too long and the response feels laggy. Humans turn-take with a blend of syntax, prosody, and context — a short pause after "I was thinking..." is a continuation; the same short pause after "That's all." is a turn end.

### 30.2 The model

Smart-Turn (pipecat-ai/smart-turn) is an ~8MB ONNX classifier trained on conversational audio. Input: the most recent 2-4 seconds of audio. Output: probability that the turn has ended.

### 30.3 The trigger

After `SMART_TURN_SILENCE=0.5` seconds of silence following a speech streak, we call Smart-Turn on the last few seconds of audio. The return is a probability.

- `p >= SMART_TURN_THRESHOLD=0.80` → turn complete, with short grace window `SMART_TURN_ADDENDUM=0.5` (Session 10 tuning).
- `0.80 > p > 0.95` → adaptive grace window shrinks to 0.20s.
- `p < 0.80` → wait out the full `SILENCE_DURATION=1.5` hard fallback.

### 30.4 Why 0.80 and not 0.55

We started at 0.55. The model was triggering turn-end inside pauses mid-thought; the robot responded while the user was still formulating. We raised the threshold twice and settled at 0.80. The tradeoff is a slight latency increase on quick sentences (we wait for hard silence), but the improvement in "feels like it's actually listening" was large.

## 31. Echo Skip and Barge-In

### 31.1 Echo skip (current)

See §29.1.

### 31.2 Barge-in (disabled)

Prior to Session 2 we had a `_vad_interrupt_listener` that ran during TTS playback and triggered `stop_audio()` if the user started speaking. This is "barge-in" — the ability to interrupt the robot mid-sentence.

We removed it because:
- On the laptop mic, TTS output often echoes back into the input strongly enough to trigger the listener — so the system would interrupt itself.
- The acoustic echo cancellation needed for real barge-in requires either an array mic (ReSpeaker 4-mic) or aggressive DSP.

Barge-in will come back when we get the ReSpeaker hardware. It's on the roadmap; the code comment at the removal site says "Do NOT re-add `_vad_interrupt_listener`" to prevent someone re-enabling it naively.

## 32. Whisper STT

### 32.1 Model

faster-whisper large-v3-turbo, loaded with `float16` on GPU. The Turbo variant is ~3x faster than regular large-v3 with minimal quality loss. ~400-700 ms for a typical 3-5 second utterance on the dev GPU.

### 32.2 Configuration

- `language=SPEAKER_LANGUAGES[0]` — currently `"en"`. The `SPEAKER_LANGUAGES` list is the set of allowed auto-detect candidates; single-language forces English.
- `vad_filter=False` — we do our own VAD upstream; letting Whisper's VAD trim would double-process.
- `condition_on_previous_text=False` — each call is independent; we don't carry state across calls.
- Default beam size and temperature.

### 32.3 Transcribe call

```python
def transcribe(audio: np.ndarray) -> tuple[str, str]:
    global _last_stt_elapsed_ms
    start = time.monotonic()
    segments, _info = _whisper.transcribe(audio, language=SPEAKER_LANGUAGES[0], ...)
    text = "".join(seg.text for seg in segments).strip()
    _last_stt_elapsed_ms = int((time.monotonic() - start) * 1000)
    print(f"[STT] {_now_log_ts()} ({_last_stt_elapsed_ms}ms) '{_log_trunc(text)}'")
    return text, SPEAKER_LANGUAGES[0]
```

The elapsed_ms is stored in a module-level global so the pipeline can log it again in turn-start logs without re-measuring (Session 61 Step 1).

### 32.4 Repetition filter

Whisper occasionally hallucinates repetitions like "pizza pizza pizza" on certain inputs. A heuristic post-processor detects 3+ consecutive identical words and logs `[Audio] STT: (repetition filtered): '...'` — the transcript is returned but flagged. Downstream uses the text but knows to be suspicious.

## 33. Within-Utterance Diarization

### 33.1 The problem

Two people can speak in rapid succession inside what the VAD treats as one turn. "Kara, it'll be hot" from Jagan followed immediately by "yes, I saw the news" from Sweetie — same `listen()` call, two speakers. The brain needs to attribute the utterance correctly.

### 33.2 The approach

`voice_mod.diarize(audio, gallery, threshold)` runs ECAPA-TDNN with a sliding window (DIARIZE_WINDOW_SECS=0.50, DIARIZE_HOP_SECS=0.25). Computes an embedding per window, then detects speaker boundaries by checking cosine similarity between adjacent windows — below `DIARIZE_CHANGE_THRESH=0.70` is a boundary.

If exactly 2 segments are produced (a single speaker change), we re-transcribe each half separately with Whisper, attributing each half to the closest voice-gallery match.

### 33.3 Minimum length

`DIARIZE_MIN_SECS=2.00` — we only diarize utterances ≥ 2 seconds. Shorter ones don't have enough signal for reliable speaker-change detection.

### 33.4 Terminal log

```
[STT] [2 voices] Jagan: "Kara, it'll be hot" / Sweetie: "yes, I saw the news"
```

And the `multi_speaker` and `multi_speaker_speakers` fields in `voice_state` propagate to the brain, which sees a mic-status block noting 2 speakers. The brain can acknowledge both in its reply.

## 34. Kokoro TTS and Piper Fallback

### 34.1 Kokoro (primary)

Kokoro is an ONNX-runnable TTS from Facebook. We use the `af_heart` voice — a warm, friendly timbre appropriate for a companion. Streaming synthesis: we feed sentence-at-a-time and it produces audio in tens of milliseconds per sentence.

We call it via the Kokoro Python wrapper. Output is float32 samples at the TTS model's native rate (we resample if needed before feeding to sounddevice).

### 34.2 Piper (fallback)

If Kokoro fails to load or to synthesise a given sentence, we fall back to Piper with the `en_US-lessac-medium` voice. Piper is slightly more robotic but reliable.

Fallback happens at synth-call time, per-sentence. One failed Kokoro call doesn't disable Kokoro — we just retry with Piper and move on.

### 34.3 Text cleaning before TTS

`_clean_for_tts(text)` strips content that would sound bad when read aloud:
- Markdown: `**bold**`, `*italic*`, `` `code` ``, `# headers`
- List markers: `- `, `• `, `1. `
- Em dashes, link syntax `[text](url)` → `text`
- Stray symbols

This was Session 32 Issue 5 — the LLM occasionally emits markdown and we don't want the TTS reading "asterisk asterisk bold asterisk asterisk".

## 35. Sentence Streaming

### 35.1 The pipeline

Tokens arrive from the streaming LLM one at a time. If we waited for the full response before speaking, latency would be bad. If we spoke every token, prosody would be bad.

The sweet spot is sentence-level streaming: buffer tokens until a sentence boundary, then synth and play that sentence while the next is still being generated.

### 35.2 `_sentence_stream(token_gen)`

```python
async def _sentence_stream(token_gen):
    buf = ""
    async for tok in token_gen:
        buf += tok
        # Find the last sentence terminator in the buffer
        for i in range(len(buf) - 1, -1, -1):
            if buf[i] in ".!?" and (i == len(buf) - 1 or buf[i + 1].isspace()):
                yield buf[:i + 1].strip()
                buf = buf[i + 1:]
                break
    if buf.strip():
        yield buf.strip()
```

### 35.3 `speak_stream(sentence_stream, language)`

Runs two coroutines concurrently:
- `_synth_worker`: takes sentences, synthesises with Kokoro/Piper, puts audio buffers on a queue.
- `_play_worker`: takes audio buffers from the queue, plays via sounddevice, awaits playback completion.

The synth worker and play worker overlap — by the time one sentence is playing, the next is already being synthed. This is the key reason the robot feels responsive even on multi-sentence replies.

### 35.4 Sentinel for worker termination

The stream uses a sentinel value (typically `None`) on the queue to signal "no more sentences." The synth worker's try/finally guarantees the sentinel is put even on exceptions (Session 35 Bug-10 fix).

### 35.5 `stop_audio()`

`sd.stop()` immediately halts playback. Used when:
- A tool call fires mid-speech (we don't want the wrong text to finish playing).
- Stream truncation retry happens (don't overlap original and retry).
- User-requested shutdown during speech.

---
---

# Part VI — Identity and Recognition

## 36. FaceDB Architecture — SQLite Plus FAISS

### 36.1 The split

`FaceDB` is the single class that owns all identity-related persistence. It combines:
- **SQLite (WAL mode)** for the authoritative records — `persons`, `embeddings`, `voice_embeddings`, `conversation_log`, `silent_observations`, `visitor_log`, `system_identity`.
- **FAISS IndexFlatIP** for fast approximate nearest-neighbour search on face embeddings.

SQLite is the ground truth; FAISS is a derived index rebuilt from SQLite when the authoritative state changes. If FAISS is ever out of sync we can rebuild it without data loss; we cannot do the reverse.

### 36.2 Why SQLite WAL

- **WAL** (write-ahead log) allows concurrent readers while a writer is active. The dashboard reads `faces.db` while the pipeline writes to it.
- **ACID** guarantees. Every INSERT/UPDATE/DELETE either completes or leaves no trace.
- **Zero ops.** No server to start; no connection pool to manage. `sqlite3.connect(path)` just works.
- **Portable.** Same binary file on Windows and Linux. Same SQL dialect. Same recovery behaviour.

### 36.3 Why FAISS IndexFlatIP

- **Exact search.** IndexFlatIP enumerates all vectors. Not approximate. Good enough for ≤ 10k galleries; past that we'd migrate to IVF.
- **Simple math.** IP on L2-normalised vectors equals cosine similarity. We never call a distance function explicitly.
- **No training.** Unlike IVF which needs a training set, FlatIP works with any vectors.
- **GPU-ready** on Jetson — just swap `faiss-cpu` for `faiss-gpu`.

### 36.4 Thread safety

Every FAISS access is guarded by `self._index_lock` (`threading.RLock`). Session 35 Bug-13 added this. Without it, concurrent `recognize()` and `add_embedding()` calls could interleave between "prepare query" and "search" with disastrous results.

### 36.5 Connection discipline

Every `FaceDB` instance holds exactly one SQLite connection (`self._conn`). It is created with `check_same_thread=False` because we call it from both the main event loop and from executor threads. All mutations go through `FaceDB` methods; nothing outside the class ever constructs a statement against `faces.db`.

## 37. Embedding Storage and Diversity Gate

### 37.1 The table

```sql
CREATE TABLE embeddings (
    id         INTEGER PRIMARY KEY,
    person_id  TEXT NOT NULL,
    vector     BLOB NOT NULL,          -- 512 × float32 little-endian
    captured_at REAL NOT NULL,
    source     TEXT NOT NULL,          -- enrollment, recognition_update, progressive_enroll
    quality    REAL,                   -- V1 score at write time
    FOREIGN KEY (person_id) REFERENCES persons (id) ON DELETE CASCADE
);
CREATE INDEX embeddings_person_id_idx ON embeddings(person_id);
```

### 37.2 `add_embedding(pid, emb, source) -> bool`

Returns True iff the embedding was written; False if the diversity gate rejected it.

```python
def add_embedding(self, person_id, emb, source, **kwargs) -> bool:
    with self._index_lock:
        assert source in VALID_EMBEDDING_SOURCES, f"unknown source {source!r}"

        # Anti-poisoning: recognition_update must clear centroid gate
        if source == "recognition_update":
            centroid = self._centroid_for(person_id)
            if centroid is not None:
                cos = float(np.dot(emb, centroid))
                if cos < SELF_UPDATE_CENTROID_MIN:
                    return False

        # Diversity gate — skip if too similar to an existing embedding
        existing = self._load_person_embeddings(person_id)
        if len(existing) >= N_INITIAL_FACE:  # post-enrollment regime
            for e in existing:
                if float(np.dot(emb, e)) > FACE_DIVERSITY_THRESHOLD:
                    return False

        # Cap check
        if len(existing) >= MAX_EMBEDDINGS:
            return False

        # Insert
        self._conn.execute(
            "INSERT INTO embeddings (person_id, vector, captured_at, source, quality) VALUES (?, ?, ?, ?, ?)",
            (person_id, emb.tobytes(), time.time(), source, kwargs.get("quality")),
        )
        self._conn.commit()

        # FAISS: add the same vector
        self._index.add(np.expand_dims(emb, 0).astype(np.float32))

        return True
```

### 37.3 Why diversity gating

Without it, a person sitting still facing the camera would accumulate 50 nearly-identical embeddings in a few minutes — wasted storage, no recognition improvement. The 0.92 cosine threshold means "this new crop is fundamentally similar to something already stored" and we skip the write.

First N_INITIAL_FACE=5 embeddings bypass the gate to give enrollment a solid baseline.

### 37.4 MAX_EMBEDDINGS cap

50 samples per person is the ceiling. Covers all reasonable angles. Past this, we stop adding. Without the cap, recognition latency grows linearly (FlatIP scans all); with the cap, worst-case FAISS search over 10 people × 50 = 500 vectors is sub-millisecond.

### 37.5 `source` values

`VALID_EMBEDDING_SOURCES = frozenset({"enrollment", "recognition_update", "progressive_enroll"})`. Any other string triggers the assert at `add_embedding`. Session 46 Finding E added this.

- `enrollment` — the initial capture during first_boot_flow or enrollment_flow.
- `progressive_enroll` — the gate-pass face captured for a stranger when they said the system name.
- `recognition_update` — self-update: a high-confidence recognition triggered storage of the new crop for gallery diversity. Requires anti-spoof pass.

## 38. Recognition with Adaptive Thresholds

### 38.1 `recognize(emb, threshold) -> (pid, name, score)`

```python
def recognize(self, emb, threshold) -> tuple[str | None, str | None, float]:
    with self._index_lock:
        if self._index.ntotal == 0:
            return None, None, 0.0
        D, I = self._index.search(np.expand_dims(emb, 0).astype(np.float32), k=1)
        score = float(D[0][0])
        if score < threshold:
            return None, None, score   # score returned even on miss
        idx = int(I[0][0])
        pid = self._idx_to_pid[idx]
        row = self._conn.execute("SELECT name FROM persons WHERE id = ?", (pid,)).fetchone()
        name = row[0] if row else None
        return pid, name, score
```

Returns (None, None, score) when no match — critically, score is still returned so the caller can decide what to do with a below-threshold match (e.g., flag as silent observation, log for debugging).

### 38.2 How threshold is derived per call

The pipeline calls with a threshold computed from V4 (adaptive_threshold based on quality score) plus a pool-depth penalty:

```python
_thresh = adaptive_threshold(quality, RECOGNITION_THRESHOLD)
if temporal_buffer.pool_depth(track_id) < 3:
    _thresh += 0.05   # less pool data → demand higher similarity
```

### 38.3 Why score is returned on miss

Two uses:
1. **Silent observation matching.** If a face is seen but below threshold (stranger), we check if they are similar to a previously-seen silent observation (SILENT_OBS_SIMILARITY=0.82). If so, update that observation; if not, create a new one.
2. **Debugging.** The log shows `[Vision] Background: score=0.234, below threshold 0.280`, which helps diagnose why a person isn't being recognised.

## 39. Temporal Embedding Buffer

`TemporalEmbeddingBuffer` (in `core/vision.py`) maintains a deque per `track_id` of the last 5 embeddings. `add_and_pool(track_id, emb)` appends and returns the mean of the current contents.

Keys are reset when a track dies (unmatched for SORT_MAX_AGE frames). Session 34 Bug-8 fix pruned `_last_raw` similarly to active SORT tracks to prevent memory growth.

The pool is deliberately simple — no weighting by quality, no outlier rejection. Mean-pool is a huge variance reducer on its own; adding sophistication for a 5-element buffer is over-engineering.

## 40. Gallery Poisoning Prevention

### 40.1 The incident — "uncle false match"

An uncle who visited Jagan's home triggered a recognition score of ~0.35 — above `RECOGNITION_THRESHOLD=0.18` (at the time) and above `SELF_UPDATE_THRESHOLD=0.32` (at the time). The system "recognised" him as Jagan and wrote a `recognition_update` with *his* face embedding to Jagan's gallery. Subsequent recognitions of the uncle matched *more* embeddings in Jagan's gallery. Feedback loop; gallery poisoned.

### 40.2 The fix (Session 51)

Four changes:

1. **`SELF_UPDATE_THRESHOLD` raised 0.32 → 0.45.** Anything below 0.45 is "merely similar" and not trusted for self-update.
2. **`SELF_UPDATE_CENTROID_MIN=0.55`** — a new check. The new embedding's cosine similarity to the person's gallery centroid must exceed this. Catches outliers at write time. An uncle's crop at 0.45 similarity to Jagan's *best* embedding might be at 0.32 to Jagan's *centroid* → rejected.
3. **`RECOGNITION_THRESHOLD` raised 0.18 → 0.28.** AdaFace IR101's stable EER region starts at 0.28, not 0.18.
4. **Anti-spoof required for `recognition_update`.** A photo-attack crop would pass the cosine gates (static photos look like the real person) but fail anti-spoof. Closes the attack loop.

### 40.3 Why centroid gate and not just best-match

Best-match gives a noisy signal — a single outlier embedding in the gallery can artificially pull up the score for unrelated crops. Centroid is the *stable* identity; requiring new crops to cluster near the centroid keeps the gallery drifting only along its natural distribution.

### 40.4 Why not stricter thresholds

We could have kept lifting thresholds but that harms recall on legitimate users with varying lighting and expressions. The combination of threshold + centroid + anti-spoof is the sweet spot between precision and recall.

## 41. Gallery Audit and Repair

### 41.1 `core/audit.py`

```python
def gallery_audit(person_id: str = None, sigma: float = 2.0) -> list:
    """For each embedding, compute cosine to the gallery centroid.
    Flag outliers (below mean - sigma × std).
    Returns [{id, person_id, cosine_to_centroid, flagged: bool}]."""
```

### 41.2 CLI tool

`audit_person.py <person_id>` prints a table of embeddings with their centroid cosines and flags. The operator can manually delete rows via SQLite if any are suspicious.

### 41.3 Dashboard integration

`/api/gallery-audit?person_id=...` returns the same data for browser display. The dashboard shows flagged embeddings with their face crop so the operator can visually confirm.

### 41.4 When to run

We don't run it automatically. The idea is: when something feels wrong (a known person isn't being recognised as reliably), audit their gallery. Flagged outliers are likely the cause. Delete them and the recognition restores.

In the future, an automatic audit could run in the dream loop once per week.

---
---

# Part VII — Voice and Speaker Identity

## 42. ECAPA-TDNN Speaker Embedding

### 42.1 Model

SpeechBrain `spkrec-ecapa-voxceleb` — the ECAPA-TDNN architecture trained on VoxCeleb. Input: raw waveform (16 kHz mono). Output: 192-dimensional L2-normalised embedding.

EER on VoxCeleb1-O is 0.80%, meaning at the equal-error threshold ~99.2% accuracy on speaker verification. We operate at a lower-recall, higher-precision threshold (`VOICE_RECOGNITION_THRESHOLD=0.25`) because false matches are much worse than missed matches in our setting.

### 42.2 Why not x-vector or d-vector

ECAPA outperforms both on short utterances. Voice samples in daily conversation average 3-8 seconds; short-utterance performance matters. ECAPA is also packaged as a single SpeechBrain class with pretrained weights, so integration is a one-liner.

### 42.3 Two torchaudio patches

`core/voice.py` contains patches for SpeechBrain's torchaudio backend detection that were broken on Windows. The patches are applied at module import time. Without them, ECAPA load fails.

## 43. Voice Gallery

### 43.1 The table

```sql
CREATE TABLE voice_embeddings (
    id                  INTEGER PRIMARY KEY,
    person_id           TEXT NOT NULL,
    vector              BLOB NOT NULL,   -- 192 × float32
    captured_at         REAL NOT NULL,
    source              TEXT NOT NULL,   -- voice_self_match, voice_face_verified
    confidence_at_write REAL,
    FOREIGN KEY (person_id) REFERENCES persons (id) ON DELETE CASCADE
);
CREATE INDEX voice_embeddings_person_id_idx ON voice_embeddings(person_id);
```

### 43.2 In-memory gallery

`pipeline._voice_gallery: dict[pid, np.ndarray]` — the mean embedding per person. `_voice_gallery_sizes: dict[pid, int]` — the number of embeddings that contributed to that mean.

Loaded at startup from DB via `db.load_voice_profiles()` and `db.load_voice_profile_sizes()`.

### 43.3 Update on new sample

`db.add_voice_embedding(pid, emb, source, confidence)` inserts a row. The pipeline then calls `db.load_voice_profile_for(pid)` to get the updated mean and stores it in `_voice_gallery[pid]`. Session 24 I2 made this a targeted update (one person) instead of reloading the whole gallery (much cheaper on large galleries).

### 43.4 MAX_VOICE_EMBEDDINGS cap

20 per person. Once reached, new additions can still happen but are gated by a diversity check (`VOICE_DIVERSITY_THRESHOLD=0.85`). In practice, most people stabilise at ~15 samples after a few conversations.

## 44. Voice Identification

### 44.1 `voice_mod.identify(audio, gallery, threshold) -> (pid, score)`

```python
def identify(audio, gallery, threshold):
    emb = _ecapa_embed(audio)   # 192-d L2-normalized
    best_pid, best_score = None, 0.0
    for pid, profile in gallery.items():
        score = float(np.dot(emb, profile))
        if score > best_score:
            best_pid, best_score = pid, score
    if best_score < threshold:
        return None, best_score
    return best_pid, best_score
```

Exhaustive search. Cheap — 192-d dot product × 10 people is nothing. No need for a FAISS index on voice.

### 44.2 Threshold choices

- `VOICE_RECOGNITION_THRESHOLD=0.25` — EER operating point. Below this, we say "unknown."
- `VOICE_SPEAKER_SWITCH_THRESHOLD=0.50` — min confidence to *open* a session for a different enrolled speaker. Identifying a voice is not the same as switching sessions; switching needs more evidence.

### 44.3 Routing consumes the result

`identify()` is called once per turn. The result feeds `_resolve_actual_speaker` which combines it with face evidence to produce the final routing decision. See §59.

## 45. Voice Self-Update

### 45.1 `_accumulate_voice(pid, audio, db, face_verified)`

This is the function that writes new voice samples to the gallery. It:

1. Extracts an embedding from `audio`.
2. Calls `_voice_accum_allowed(session)` to check Path A/B/C.
3. If allowed:
   - Decrements bootstrap_credits if that was the winning path.
   - Decides `source` (voice_face_verified if face_verified else voice_self_match).
   - Calls `db.add_voice_embedding(pid, emb, source, confidence)`.
   - Reloads `_voice_gallery[pid]` via `db.load_voice_profile_for`.
   - Updates `_voice_gallery_sizes[pid]`.
   - Logs `[Voice] Profile updated for {pid} (N/20 voice samples) [via {path}]`.
4. If refused:
   - Logs `[Voice] Refused accumulation for {pid}: {reason}`.

### 45.2 Why `face_verified` affects source

`voice_face_verified` means we know this voice belongs to this face because we saw the face at the time. Higher trust. `voice_self_match` means the voice profile self-matched; this is weaker evidence. Downstream could weight them differently (we don't yet; they both contribute equally to the mean).

## 46. Stale Stranger Voice Pruning

### 46.1 The problem

A stranger opens a voice session, says the system name, the engagement gate passes, we add a few voice embeddings under their `stranger_<uuid>` pid. They then leave and never come back. Their thin voice profile lingers and could false-match a new voice similarly.

### 46.2 `prune_stale_stranger_voice(days)`

Runs in the dream loop. Deletes `voice_embeddings` rows for strangers whose profile never reached `N_INITIAL_VOICE=5` samples and hasn't been updated in `STRANGER_VOICE_TTL_DAYS=3` days.

Session 54 Finding J split this into `find_stale_stranger_voice_ids(days)` (read-only) + `prune_stale_stranger_voice(days, ids=...)` (destructive) so the dream loop can evict the in-memory cache *first*, then delete rows — preventing a microsecond window where `voice_mod.identify` could match a stranger whose DB row was about to vanish.

---
---

# Part VIII — Session Management

## 47. SessionStore and the `Session` Dataclass

> **Architectural note (2026-05-15).** Before P0.7 (the typed-session-state migration; see **Part XL**), active sessions lived in a free-form `_active_sessions: dict[str, dict]` at module scope in `pipeline.py`. ~190 sites across `pipeline.py` and `test_pipeline.py` wrote to this dict directly. Field typos silently created garbage keys; concurrent access went unsynchronised; invariants ("dispute_set_at must be present whenever person_type == 'disputed'") had to be defended at every site. P0.7 replaced the free-form dict with a typed `SessionStore` owning typed `Session` dataclasses. This section describes the production session state surface as it exists today.

### 47.1 The three dataclasses (from `core/session_state.py`)

```python
@dataclass(slots=True)
class VoiceEvidence:
    voice_match_conf:      float = 0.0          # last voice ID cosine (CAN be negative)
    voice_last_heard_ts:   float = 0.0          # unix ts of last voice ID match
    voice_sample_count:    int = 0              # DB-hydrated at open_session
    bootstrap_credits:     int = 0              # remaining credits from engagement gate
    recent_voice_confs:    list[float] = field(default_factory=list)   # maxlen-3 deque
    # face evidence
    face_match_conf:       float = 0.0
    face_last_seen_ts:     float = 0.0
    anti_spoof_live:       bool = False
    anti_spoof_score:      float = 0.0

@dataclass(slots=True)
class Session:
    person_id:             str
    person_name:           str
    person_type:           str             # stranger | known | best_friend | disputed
    started_at:            float
    last_face_seen:        float = 0.0
    last_spoke_at:         float = 0.0
    # dispute state
    dispute_set_at:        Optional[float] = None
    disputed_claimed_name: Optional[str] = None
    prior_person_type:     Optional[str] = None
    disputed_block_count:  int = 0
    disputed_block_alerted: bool = False
    # progressive enrollment
    voice_only_origin:     bool = False    # set at engagement gate if face NOT witnessed
    voice_face_confirmed:  bool = False    # set at progressive-enrollment gate pass
    waiting_for_name:      bool = False    # stranger awaiting "my name is X"
    # context + cache
    cached_prefix:         Optional[str] = None
    core_memory:           Optional[dict] = None
    # room
    room_session_id:       Optional[str] = None
    # turn counter (stranger gate progress)
    user_turns:            int = 0
    # voice + face evidence
    evidence:              VoiceEvidence = field(default_factory=VoiceEvidence)

@dataclass(frozen=True, slots=True)
class SessionSnapshot:
    """Immutable frozen snapshot returned by SessionStore.peek_snapshot().
    Same fields as Session, but collections are NEW copies — mutating
    them has no effect on the underlying Session."""
    # ... same 29 fields as Session
```

`slots=True` on every dataclass is load-bearing: it makes every typo into an `AttributeError` at runtime AND shrinks the per-session memory footprint substantially. `frozen=True` on `SessionSnapshot` is the read-only contract — anywhere in the codebase that needs session state in a logging context, prompt-assembly context, or background coroutine context calls `_session_store.peek_snapshot(pid)` and gets back a snapshot that's safe to pass across `await` boundaries.

### 47.2 Key invariants

- **Pid is the key.** Not name — multiple people can share a name.
- **Pid prefix identifies origin.** `stranger_<uuid>` means this person was created via stranger enrollment; anything else is explicitly created.
- **`person_type` is authoritative.** `stranger`, `known`, `best_friend`, `disputed`. The DB stores `person_type`; the Session mirrors it so hot-path routing doesn't hit the DB every turn.
- **Single-owner.** `SessionStore` is the only writer of `self._sessions: dict[str, Session]`. Every mutation acquires `self._lock` (an `asyncio.Lock`) before touching the dict.
- **Async mutators, sync peek reads.** Every mutation is an `async def` named transition method. Every read is a `def peek_*` returning either a `SessionSnapshot` or a primitive — peeks do NOT acquire the lock, per the single-thread-asyncio safety contract (Part XL §268).

### 47.3 Why a typed Store, not a free-form dict

The shift from `dict[str, dict]` to `SessionStore` carrying `dict[str, Session]` was justified by four concrete failure modes pre-migration:

1. **Field-typo drift.** `_active_sessions[pid]["displute_set_at"] = ...` silently created a new key. `slots=True` makes this an `AttributeError`.
2. **No invariant guards.** A session could be in `person_type == "disputed"` without `dispute_set_at` being set. The named transition `transition_to_disputed(...)` captures `prior_person_type` AND sets `dispute_set_at` AND flips `person_type` atomically.
3. **Concurrent access.** Test and background-coroutine writes interleaved without coordination. The `asyncio.Lock` serialises them.
4. **~190 ad-hoc write sites.** Any future invariant (e.g. "engagement gate must always set bootstrap_credits") had to be defended at every site individually. The 21 named transition methods (§264) replace those sites with semantically-meaningful operations.

## 48. `person_type` Taxonomy

### 48.1 The four types

- **`stranger`** — someone we don't know yet. Pid starts with `stranger_`. Cannot shut down the system or rename it. Can search the web. Cannot search memory (no personal memory yet).
- **`known`** — we know their name and have a face gallery. Can search memory. Cannot rename the system or shut down.
- **`best_friend`** — the household owner. One at a time. Can do everything.
- **`disputed`** — temporary state. A session entered dispute when the speaker's claim contradicted sensor evidence (Session 51). Brain treats them as unknown; agent extraction pauses; renames blocked.

### 48.2 `VALID_PERSON_TYPES` frozenset

```python
VALID_PERSON_TYPES = frozenset({"stranger", "known", "best_friend", "disputed"})
```

Asserted at every write site. The `SessionStore.open_session` method type-checks against this frozenset, and the dispute transition methods (`transition_to_disputed`, `clear_dispute`) carry their own VALID_PERSON_TYPES assertions on the restored type.

### 48.3 Promotion paths

- stranger → known: `update_person_name` tool fires during a stranger session, name is valid.
- stranger → best_friend: never. Best_friend is only set during first_boot_flow.
- known → disputed: sensor and claim disagree; `update_person_name` on a known session flips to disputed via `transition_to_disputed`.
- best_friend → disputed: same (Session 55 Finding L). The `prior_person_type` field captures `best_friend` so `clear_dispute` can restore it.
- disputed → resolved: either `update_person_name` clears it (rename path), `clear_dispute(pid)` runs (auto-clear), or `DISPUTE_MAX_DURATION` force-closes the session.

## 49. `_open_session` Anatomy

The pipeline's wrapper around `SessionStore.open_session`:

```python
async def _open_session(
    person_id: str,
    person_name: str,
    session_type: str,
    *,
    person_type: str,
    engagement_gate_passed: bool = False,
    voice_confidence: float = 0.0,
) -> None:
    assert person_type in VALID_PERSON_TYPES, f"invalid person_type {person_type!r}"

    now = time.time()
    existing = _session_store.peek_snapshot(person_id)
    if existing is not None:
        # Idempotent re-open: refresh timestamps, do NOT clobber person_type.
        await _session_store.update_on_reopen(
            person_id, voice_confidence=voice_confidence, now=now
        )
        return

    print(f"[Session] Open: {person_id} ({session_type}) — {person_name}")

    # DB-preferred voice_sample_count hydration (Obs 1).
    db_voice_count = _voice_gallery_store.peek_size(person_id)
    if _face_db_ref is not None:
        try:
            live_count = _face_db_ref.count_voice_embeddings(person_id)
            if db_voice_count != live_count:
                await _voice_gallery_store.set_size(person_id, live_count)
            db_voice_count = live_count
        except Exception:
            pass

    bootstrap_credits = N_INITIAL_VOICE_BOOTSTRAP if engagement_gate_passed else 0

    await _session_store.open_session(
        person_id=person_id,
        person_name=person_name,
        person_type=person_type,
        session_type=session_type,
        started_at=now,
        last_face_seen=now,
        last_spoke_at=now,
        voice_sample_count=db_voice_count,
        bootstrap_credits=bootstrap_credits,
        voice_match_conf=voice_confidence,
    )
```

### 49.1 The `engagement_gate_passed` flag

Only callers who can prove they gated on engagement pass True. Strangers who said the system name → True. Known/best_friend greetings → True (the greeting itself is gated by anti-spoof + face recognition). Random voice-ID-matched someone without explicit consent gating → False.

Bootstrap credits are seeded only when True. This is the key design choice: we only trust a voice enough to accumulate against when we explicitly gated them in.

### 49.2 Idempotent re-open

If the pid already has an active session, `_open_session` delegates to `update_on_reopen` (atomic refresh of timestamps + voice_match_conf) instead of constructing a new Session. The named transition keeps three properties intact in one operation: `person_type` is NOT clobbered (so a stranger→known promotion done via `update_person_name` since the last open isn't reverted), `dispute_set_at` is preserved if the session is currently disputed, `voice_only_origin` and `voice_face_confirmed` flags are preserved.

## 50. `_close_session` Cleanup

```python
async def _close_session(person_id: str) -> None:
    snap = _session_store.peek_snapshot(person_id)
    if snap is None:
        return
    print(f"[Session] Close: {person_id} — {snap.person_name}")

    await _session_store.close_session(person_id)
    _sessions_started_store.discard(person_id)
    _pending_stranger_voice_store.pop(person_id)        # Bug-2 (Session 33)
    _query_embedding_cache.pop(person_id)               # Finding B (Session 45)
    _identity_hints_store.pop(person_id)                # Finding B (Session 45)
    await _track_store.unbind_stranger_pid(person_id)   # remove track bindings
    await _presence_store.pop_pid(person_id)            # remove from visible roster
    _per_person_agent_store.pop(person_id)              # P0.6.4 — emotion + ambient agents

    # Notify brain orchestrator for session-end synthesis
    if _brain_orchestrator is not None:
        _brain_orchestrator.notify_session_end(person_id, snap.person_name)

    # Room lifecycle: if last session closed, fire _on_room_end fire-and-forget
    if not _session_store.has_any_active_session():
        room_id, room_started_at, participants = _pipeline_state_store.consume_room_session()
        if room_id is not None:
            asyncio.create_task(_on_room_end(room_id, list(participants), room_started_at))
```

### 50.1 Cleanup discipline

Every Store that keys on pid must be cleaned up here. The Store-pattern migration (P0.6, Part XXXIX) made this enforceable: each store exposes a `pop(pid)` or equivalent method, and the M2 autouse coverage meta-test (Part XXXIX §257) catches any store that's not in the cleanup list. Tests fail if a new store is added without a cleanup hook.

### 50.2 BrainOrchestrator.notify_session_end

Triggers a bundle of async tasks:
- `PromptPrefAgent` full analysis on the session's turns.
- `InsightAgent` episode extraction.
- `HouseholdExtractionAgent` relationship inference.
- `NudgeAgent` visitor-alert if this was a non-owner session with turn_count > 0.
- `SocialGraphAgent` aggregation.
- `BrainOrchestrator.synthesize_room` (if this was the last session of a multi-person room, see Part XXVI §171).

All gated on dispute: if the session ended in dispute state, the synthesis helpers are skipped (Session 53 Finding A, see §105).

## 51. Session Expiry Paths

### 51.1 `_expire_stale_sessions()`

Runs both in the outer WATCHING loop and inside the conversation loop. Iterates `_session_store.peek_all_snapshots()` (Part XL §268) and finds sessions where:
- `session_type == "voice"` and `(now - last_spoke_at) > VOICE_SESSION_TIMEOUT`
- OR `session_type == "face"` and `(now - last_face_seen) > FACE_LOSS_GRACE`
- OR `person_type == "disputed"` and `(now - dispute_set_at) > DISPUTE_MAX_DURATION`

For each, calls `_close_session(pid)`.

Auto-clear (P0.7.3): for disputed sessions where the dispute conditions have resolved (3 consecutive voice matches at ≥ `DISPUTE_AUTO_CLEAR_VOICE_MIN`, OR the holder's face is in frame with `face_match_conf ≥ DISPUTE_AUTO_CLEAR_VOICE_MIN`), call `transition_clear_dispute(pid, now)` to restore the session via `prior_person_type`.

### 51.2 FACE_LOSS_GRACE (10s)

A face-started session doesn't immediately end when the face leaves frame. We give the user 10 seconds of grace — they might look down, walk behind a pillar, or briefly turn away. Past that, we close.

### 51.3 VOICE_SESSION_TIMEOUT (30s)

A voice-started session ends when the holder has been silent for 30 seconds. Longer than FACE_LOSS_GRACE because voice-only users don't have the visual anchor — we give them more benefit of the doubt.

### 51.4 DISPUTE_MAX_DURATION (180s)

Disputed sessions can't self-expire via the above because the sensor may keep matching the wrong person (keeping `last_face_seen` fresh) while the speaker is actually a different person. Without this force-close, the session could live indefinitely. 3 minutes is long enough for a misunderstanding to be clarified but short enough that stuck states recover.

## 52. Primary Person Selection

> **Phase 3B addendum.** The notion of a "primary person" as the sole speaker of a turn is softening post-Phase 3B. In multi-person rooms, every turn still has a *current speaker* (the pid whose audio was captured), but the brain decides *addressee* independently via the `[addressing:X]` marker (Part XXVI §168). Future refactors may drop the module-level "primary pid" concept in favour of passing the current speaker as a parameter — that's part of Phase 3 backlog (Q3 History Architecture and deferred RoomOrchestrator class).

## 52b. The Room Session Lifecycle

See **Part XXVI §163** for the full story. Briefly: `PipelineStateStore.room_session_id` (currently-active room session id), `room_started_at` (timestamp), and `room_participants` (set of person_ids) together describe the current multi-person room. Minted on first session open after empty; populated on every subsequent `_open_session`; torn down in `_on_room_end` when the last session leaves. `_on_room_end` schedules `BrainOrchestrator.synthesize_room` fire-and-forget so room-end latency doesn't block the next turn.


### 52.1 `_primary_person_id() -> pid | None`

When multiple sessions are active, which one is "primary" — the one the brain is currently responding to?

```python
def _primary_person_id() -> str | None:
    snaps = _session_store.peek_all_snapshots()
    if not snaps:
        return None
    # Most recently spoken wins; tie-break by pid (deterministic, Session 34 Bug-5)
    return max(snaps, key=lambda s: (s.last_spoke_at, s.person_id)).person_id
```

Simple ordering: the person who spoke most recently is the primary. Tie-break on pid keeps it deterministic.

### 52.2 Why "most recent speaker"

In a multi-person scene, the brain's role is to answer whoever just spoke. We don't need to track a "conversation leader" — each turn can have a different speaker, and the brain sees the full scene roster through the `<<<SCENE>>>` block.

### 52.3 Interaction with routing

The primary is computed *before* the current turn's reconciler call (Part X §59). Routing may switch to a different pid — that pid becomes the primary for this turn's `conversation_turn` call, and after `log_turn` records the user turn, the session's `last_spoke_at` is updated via `update_voice_heard` or `update_face_seen`, making this pid the primary on the next iteration.

---
---

# Part IX — Identity Evidence

## 53. The `VoiceEvidence` Dataclass

> **Architectural note (2026-05-15).** Pre-P0.7, identity evidence lived in a free-form `identity_evidence: dict` field inside each session's free-form dict. A `_update_identity_evidence(person_id, **fields)` writer guarded against typos via a KeyError on unknown field names. P0.7 (Part XL) replaced both with a typed `VoiceEvidence` slotted dataclass nested inside `Session`. The typo-detection contract is now structural — `slots=True` makes every typo a runtime `AttributeError` — and the writers are named transition methods on `SessionStore` instead of a single multi-purpose helper.

The `VoiceEvidence` dataclass on every session captures "how confident are we that this session's pid is the person currently speaking?":

### 53.1 Fields (from `core/session_state.py`)

```python
@dataclass(slots=True)
class VoiceEvidence:
    # voice channel
    voice_match_conf:      float = 0.0          # last voice ID cosine — CAN BE NEGATIVE
    voice_last_heard_ts:   float = 0.0          # unix ts of last voice ID match
    voice_sample_count:    int = 0              # DB-hydrated at open_session
    bootstrap_credits:     int = 0              # remaining credits from engagement gate
    recent_voice_confs:    list[float] = field(default_factory=list)   # maxlen-3 deque
    # face channel
    face_match_conf:       float = 0.0          # last face recognition cosine (0 if none)
    face_last_seen_ts:     float = 0.0          # unix ts of last face match
    anti_spoof_live:       bool = False         # last anti-spoof verdict
    anti_spoof_score:      float = 0.0          # last live_prob
```

`anti_spoof_last_ts` (separate field for the timestamp of the most recent anti-spoof check) is currently merged into `face_last_seen_ts` since the greeting path and the background vision scan both write them together. If P0.S1's anti-spoof-on-every-match work surfaces a need for a separate timestamp, it'll be added as an explicit field on `VoiceEvidence`.

### 53.2 `voice_match_conf` can be negative

ECAPA-TDNN cosine similarity between anti-correlated speakers is routinely negative (values like -0.05, -0.08 are normal). `voice_match_conf` carries the *actual* cosine returned by `voice.identify()`, NOT the absolute value. The reconciler's P4 rules (Part X §60.5) interpret negative scores as "confident not-this-speaker" signal; the post-2026-05-02 negative-cosine fix made this distinction load-bearing. Storing the raw cosine preserves the signal.

### 53.3 Ephemeral vs persistent

- **Face-side fields are ephemeral** — re-established each session. The face seen 5 minutes ago isn't guaranteed to be the same person 30 minutes later.
- **`voice_sample_count` is DB-persistent** via hydration. Voice samples persist across sessions; sample count reflects that. `_open_session` hydrates from `_voice_gallery_store.peek_size(pid)` and falls back to `db.count_voice_embeddings(pid)` if the cache is stale (Obs 1, Part XL §266).
- **`bootstrap_credits` is per-session** — once consumed, gone (replenishment for engaged voice-only strangers via Session 94 lands here too; see §337 for the known fix-queued bug after promotion).

## 54. The Named-Transition Writer Invariant

Pre-P0.7 had `_update_identity_evidence(person_id, **fields)` — one writer, validation via KeyError on unknown fields. P0.7 replaced this with named transition methods on `SessionStore`, each one writing exactly the field set its name implies:

```python
# In core/session_state.py::SessionStore
async def update_voice_heard(self, pid: str, conf: float, ts: float) -> None:
    """Update voice_match_conf + voice_last_heard_ts; append to recent_voice_confs."""

async def update_face_seen(self, pid: str, ts: float, conf: float, live: bool) -> None:
    """Update face_match_conf + face_last_seen_ts + anti_spoof_live."""

async def set_bootstrap_credits(self, pid: str, n: int) -> None:
    """Seed bootstrap credits at engagement-gate pass."""

async def decrement_bootstrap_credits(self, pid: str) -> bool:
    """Consume one credit on accumulation. Returns False if 0; no-mutate."""
```

### 54.1 Why named transitions instead of a single multi-purpose writer

Three reasons over the pre-P0.7 design:

1. **Semantic clarity.** `update_voice_heard(pid, conf, ts)` reads better than `_update_identity_evidence(pid, voice_match_conf=..., voice_last_heard_ts=...)`. Future maintainers immediately see what the call site means.
2. **Atomic multi-field writes.** `update_voice_heard` writes 3 fields (`voice_match_conf`, `voice_last_heard_ts`, append to `recent_voice_confs`) in one lock acquisition. The pre-P0.7 caller had to make 3 separate `_update_identity_evidence` calls and the dispute auto-clear's 3-consecutive-voice-match check could race with a deque mutation between them.
3. **Type safety.** `slots=True` on `VoiceEvidence` makes `e.voice_match_conff = 0.5` (note the typo) a runtime `AttributeError`. The dynamic `**fields` writer needed an explicit KeyError check; the typed dataclass needs none.

### 54.2 Call sites and which transition fires where

| Call site | Transition method | What it writes |
|---|---|---|
| Greeting path (anti-spoof passes, about to greet known) | `update_face_seen` | face_match_conf, face_last_seen_ts, anti_spoof_live=True, anti_spoof_score |
| Background vision scan (face recognised as active session pid) | `update_face_seen` | same shape |
| Per-turn voice ID (voice matches session holder) | `update_voice_heard` | voice_match_conf, voice_last_heard_ts, append to recent_voice_confs |
| Engagement gate pass (face captured: known/best_friend greeting) | `set_bootstrap_credits(N_INITIAL_VOICE_BOOTSTRAP)` + `update_face_seen` + `set_voice_face_confirmed(True)` | bootstrap_credits, face evidence, voice_face_confirmed |
| Engagement gate pass (voice-only: stranger said system name, no face) | `set_bootstrap_credits(N_INITIAL_VOICE_BOOTSTRAP)` + `set_voice_only_origin(True)` | bootstrap_credits, voice_only_origin (no face evidence — fixes Bug C, see Part XL §263) |
| Accumulation success in `_accumulate_voice` | `decrement_bootstrap_credits` (Path C) OR no-op (Path A/B); voice_sample_count bumped via `_voice_gallery_store.set_size` | bootstrap_credits decrement |

### 54.3 Silent no-op on missing session

If the session was closed between the caller's snapshot and the transition call, the transition's first line — `sess = self._sessions.get(pid); if sess is None: return` — returns silently. Caller doesn't need null-checks. This is especially important for async paths like `_accumulate_voice` where the session may close while the task is pending.

## 55. Path A / B / C Accumulation Policy

### 55.1 The function

```python
def _voice_accum_allowed(session: dict) -> tuple[bool, str, str]:
    ev = session.get("identity_evidence") or {}
    now = time.time()

    # Path A — recent confident face witness
    face_age = now - ev.get("face_last_seen_ts", 0.0)
    if (ev.get("face_match_conf", 0.0) >= VOICE_ACCUM_FACE_WITNESS_MIN_CONF
            and ev.get("anti_spoof_live", False)
            and face_age <= VOICE_ACCUM_FACE_WITNESS_MAX_AGE_SEC):
        return (True, f"face witness (...)", "face_witness")

    # Path B — mature voice profile self-matching
    if (ev.get("voice_match_conf", 0.0) >= VOICE_ACCUM_VOICE_SELF_MATCH_MIN
            and ev.get("voice_sample_count", 0) >= VOICE_ACCUM_MATURE_SAMPLE_COUNT):
        return (True, f"voice self-match (...)", "voice_self_match")

    # Path C — bootstrap credits from engagement gate
    if ev.get("bootstrap_credits", 0) > 0:
        return (True, f"bootstrap (...)", "bootstrap")

    return (False, f"no witness (...)", "refused")
```

### 55.2 Path A — face witness

The speaker's face is currently in frame, recognition confidence is high (≥ 0.45), anti-spoof passed, and the face was seen within the last 10 seconds. Voice can be accumulated under this pid with high trust.

This path covers the normal case: a known person sitting in front of the camera.

### 55.3 Path B — mature voice profile

The pid has ≥ 5 voice samples (profile is "mature"), and the current voice ID matches that profile at cosine ≥ 0.45. Voice can be accumulated.

This path covers the user who stepped out of frame but keeps talking. No face witness, but the voice profile is trustworthy enough on its own.

### 55.4 Path C — bootstrap credits

The session was opened via an engagement gate (engagement_gate_passed=True) and `bootstrap_credits > 0`. We grant the accumulation without voice-self-match or face-witness — this is how a brand-new voice profile *starts*. Without Path C, a fresh profile couldn't reach the `voice_sample_count ≥ 5` threshold of Path B, because Path A requires face (may not have) and Path B requires samples (doesn't have yet).

## 56. Bootstrap Credits

### 56.1 The arithmetic gap (Bug A)

`N_INITIAL_VOICE_BOOTSTRAP=6` must exceed `VOICE_ACCUM_MATURE_SAMPLE_COUNT=5`. Discovered in Session 64 (Bug A) when we saw voice-only Chloe stalling at 3 samples: bootstrap=3, mature=5, so Path C exhausted at sample 3 and Path B couldn't engage yet. Raised bootstrap to 6 with an invariant test.

The test:
```python
def test_bootstrap_budget_exceeds_mature_threshold():
    assert N_INITIAL_VOICE_BOOTSTRAP > VOICE_ACCUM_MATURE_SAMPLE_COUNT, (
        "BOOTSTRAP must exceed MATURE — otherwise voice-only strangers get stuck"
    )
```

Guards against any future tuning that would re-introduce the gap.

### 56.2 Credits are consumed, not reset

Once consumed, bootstrap_credits goes to 0. Session restart starts fresh — but with DB-hydrated voice_sample_count (Obs 1), so a restarted session with 6+ prior samples goes straight to Path B and doesn't need bootstrap.

## 57. DB-Hydrated Voice Sample Count

### 57.1 The problem

Before Session 64 Bug A, `_open_session` initialised `voice_sample_count=0`. A voice-only stranger whose session expired at 30 seconds would lose their profile progress on reopen.

### 57.2 The fix

Session 64 Part 1 hydrates from `_voice_gallery_sizes` at open time. Post-review Obs 1 hardened it to prefer `db.count_voice_embeddings(pid)` over the cache so out-of-process deletes (dashboard, CLI) can't leave stale counts.

```python
_db_voice_count = _voice_gallery_sizes.get(person_id, 0)
if _face_db_ref is not None:
    try:
        _db_voice_count = _face_db_ref.count_voice_embeddings(person_id)
        if _voice_gallery_sizes.get(person_id, -1) != _db_voice_count:
            _voice_gallery_sizes[person_id] = _db_voice_count
    except Exception:
        pass
```

DB-preferred, cache-fallback, opportunistic cache repair, exception-guarded.

### 57.3 Dream loop reconciliation (Obs 1)

Every dream cycle, the dream loop re-loads `db.load_voice_profile_sizes()` and compares to `_voice_gallery_sizes`. Divergence triggers a full reload (both sizes and mean embeddings) plus a log line `[Dream] Voice gallery cache reconciled: N pid(s) out of sync`.

## 58. The `<<<IDENTITY EVIDENCE>>>` Brain Block

### 58.1 Purpose

The brain sees a snapshot of the evidence every turn in a dedicated system-prompt block. This gives the LLM the sensor state it needs to decide, for example, whether to trust a claimed identity change.

### 58.2 Block format

```
<<<IDENTITY EVIDENCE>>>
  face: conf=0.85, age=1.2s, anti-spoof=live (score=0.98)
  voice: conf=0.62, samples=12, age=0.8s
  bootstrap_credits: 0
  verdict: high-confidence identity
<<<END>>>
```

### 58.3 Verdict heuristic

The verdict is computed in `brain.py`:

```python
_face_ok = (
    _face_conf >= VOICE_ACCUM_FACE_WITNESS_MIN_CONF
    and _live
    and _face_age is not None
    and _face_age <= VOICE_ACCUM_FACE_WITNESS_MAX_AGE_SEC
)
_voice_ok = (
    _voice_conf >= VOICE_ACCUM_VOICE_SELF_MATCH_MIN
    and _voice_n >= VOICE_ACCUM_MATURE_SAMPLE_COUNT
)
if _face_ok and _voice_ok:
    _verdict = "high-confidence identity"
elif _face_ok or _voice_ok:
    _verdict = "medium-confidence identity (one channel weak or missing)"
elif _face_conf > 0 or _voice_conf > 0:
    _verdict = "low-confidence identity"
else:
    _verdict = "no sensor evidence"
```

Uses the same `VOICE_ACCUM_*` constants as `_voice_accum_allowed`. Session 62 fixed a drift bug where `brain.py` used literals (0.45 / 5 / 10.0) that didn't track config changes — now they're imported from the same place.

### 58.4 Toggle

`IDENTITY_EVIDENCE_BLOCK_ENABLED=True` globally. Can be turned off via config for debugging prompts.

### 58.5 Why the brain needs this

Two cases:
1. **Dispute detection.** If the speaker claims to be Jagan but the evidence says low-confidence, the brain can call `report_identity_mismatch` to flag dispute.
2. **Trust calibration.** The brain's reply can be hedged when evidence is weak ("I think I remember you — are you...?") vs confident when it's strong.

---
---

# Part X — Multi-Person Routing

> **Architectural note (2026-05-17).** The original routing function `_resolve_actual_speaker` in `pipeline.py` was the project's first multi-person routing primitive (Sessions 26-49). After the voice/vision independence rearchitecture (Phases 1–4 of `VOICE_VISION_INDEPENDENCE_PLAN.md`, see Part XXXII) the routing logic moved into `core/reconciler.py::reconcile`, a 22-rule cascade that consumes a structured `IdentityClaim` + `PresenceState` + `SessionState` and emits a single `RoutingDecision`. The Phase 4 cutover (`ROUTING_USE_RECONCILER=True`, Session 121) made the reconciler primary; P0.10 Phase 2 (2026-05-17) **deleted `_resolve_actual_speaker` entirely**. This Part describes the production routing surface as it exists today — the reconciler. The historical algorithm and the Bug-W coverage gap that the deletion exposed are documented in **Part XLIII §285-§292**.

## 59. The Reconciler — Single Routing Source of Truth

Production routing for every turn flows through one function:

```python
def reconcile(
    claim:    IdentityClaim,
    presence: PresenceState,
    session:  SessionState,
) -> RoutingDecision: ...
```

`reconcile` is pure — no module-level state reads, no I/O, no side effects. Three inputs come from three independent producers:

- **`IdentityClaim`** is built by `core/voice_channel.py::identify_speaker` (Part XXXII §199). It captures voice-side observation only: `pid`, `confidence`, `n_diarize_segments`, `utterance_duration`, optional `raw_segment_scores`, plus a human-readable `reasoning` string. Voice does not read vision state to construct the claim.
- **`PresenceState`** is built by `core/vision_channel.py::observe_scene` (Part XXXII §200). It captures vision-side observation only: `visible_pids`, `unrecognized_track_ids`, `per_pid_confidence`, frame `timestamp`. Vision does not read voice state.
- **`SessionState`** is built by the pipeline immediately before the reconciler call. It snapshots: `cur_pid`, `cur_person_type`, `n_active_sessions`, `voice_gallery_sizes`, `cur_holder_voice_n`, `now`.

The output `RoutingDecision` is a frozen dataclass: `action`, `pid`, `rule` (which rule fired), `utt_band` (`noise` / `gap` / `short_hard` / `normal`), `reasoning`. The `action` is one of: `current`, `switch_enrolled`, `new_stranger`, `ambiguous`, `short_utterance_skip`, `short_utterance_voice_mismatch`, `multi_segment_voice_mismatch`, `no_action`.

## 60. The 22-Rule Cascade — Priority Bands

`reconcile` runs a fixed cascade in deterministic order. Each rule is a pure function `(claim, presence, session) -> Optional[RoutingDecision]`. The first rule that matches wins. If no rule matches (degenerate state), the cascade returns `RoutingDecision(action="no_action", ...)` — a logged escape hatch that should never fire in practice given the cascade's coverage.

The cascade is grouped into 5 priority bands. Each rule carries a `LOWER_BOUND` attribute documenting the minimum utterance duration at which it is eligible to fire (introduced in P0.10 Phase 1; see Part XLIII §287 for the non-decreasing band-ordering invariant).

| Band | Rules | What they handle |
|---|---|---|
| **P0** | `_p0_pure_noise_hold_current`, `_p0_short_utterance_no_session`, `_p0_short_utterance_gap_hold_current`, `_p0_short_utterance_hard_mismatch`, `_p0_short_utterance_ambiguous_multi_session` | Sub-MIN_UTTERANCE_SECS audio: hard-mismatch drops, ambiguous-zone drops, pure-noise hold-current, the Bug-W gap fix (`gap` band, see §60.3) |
| **P1** | `_p1_confident_voice_switch` | Voice score above `SPEAKER_SWITCH_THRESHOLD` and matches a different pid → confident switch |
| **P2** | `_p2_face_assist_switch`, `_p2_voice_face_agree` | Mid-range voice score where face co-presence corroborates the switch |
| **P3** | `_p3_self_match_with_face`, `_p3_self_match_below_floor`, `_p3_above_self_match` | Holder's own voice score relative to self-match floor (gallery-poisoning protection) |
| **P4** | `_p4_pyannote_vouched_stranger`, `_p4_new_stranger_low_match`, `_p4_voice_ambiguous_no_candidates`, `_p4_voice_ambiguous_with_candidates`, `_p4_single_segment_mismatch`, `_p4_multi_segment_mismatch` | Below-threshold voice scores: open new stranger, drop turn, hold ambiguous |
| **P5** | `_p5_no_session_new_stranger`, `_last_resort_ambiguous` | No active session: any real signal opens a stranger session; last-resort fall-through |

The grouping is intentional and load-bearing. P0 fires before P1 because a sub-second utterance scoring 0.85 against the holder is still too short to attribute reliably (high score is artifactual from acoustic prior, not identity match). P3's self-match floor fires before P4's mismatch handling because "current holder said something quiet" must route differently from "stranger said something we can't match."

Every rule is independently unit-tested in `tests/test_reconciler.py`. The cascade is integration-tested by passing pinned `(claim, presence, session)` fixtures captured from real canary failure modes (the Bug-W gap fixture from 2026-05-01 and the negative-cosine fixture from 2026-05-02 are two examples).

### 60.1 P1 — confident voice switch

The simplest case. Voice score above `VOICE_SPEAKER_SWITCH_THRESHOLD` (effective threshold may be higher for thin profiles, see §61) and `claim.pid != session.cur_pid`. Routes to `claim.pid` as `switch_enrolled`. Face agreement is not required — the voice alone is strong enough.

### 60.2 P2 — mid-range switch with face corroboration

Score between the mid-range floor (`VOICE_ROUTING_MIDRANGE_SWITCH_MIN`) and `VOICE_SPEAKER_SWITCH_THRESHOLD`. Voice alone is too weak, but if `claim.pid` also appears in `presence.visible_pids`, the two independent signals agreeing gives confidence to switch. Without face corroboration in this band, the rule returns ambiguous and the turn is dropped.

The `face_assist_min` floor (`VOICE_ROUTING_FACE_ASSIST_MIN = 0.42`) was added in 2026-04-21 Session 67 Bug O after a 0.314 phone-audio score with the holder's face in frame was misattributed. Even with face corroboration, the voice must clear the assist floor.

### 60.3 P0 — short-utterance handling and the Bug-W gap fix

The `_p0_short_utterance_gap_hold_current` rule (added in P0.10 Phase 1, Session ~119+) fires when:
- `utterance_duration` is between `MIN_UTTERANCE_SECS` and `SHORT_UTTERANCE_FLOOR`
- The session is active (`session.cur_pid is not None`)
- No signal disqualifies the holder

This rule fills the **Bug-W coverage gap** (Part XLIII §286): pre-P0.10, a 0.3–0.5s utterance from a known holder with no other signal would fall through every cascade rule and exit `no_action` (turn dropped). The legacy `_resolve_actual_speaker` had a catch-all `return cur_pid, "current"` that incidentally papered over the gap; the reconciler's positive-contract design needed an explicit rule.

The rule tags `utt_band="gap"`. The `EXPECTED_RULES_BY_BAND` invariant (Part XLIII §291) asserts that any rule firing on a `gap` band utterance must be `_p0_short_utterance_gap_hold_current`.

### 60.4 P3 — self-match floors (gallery-poisoning protection)

`_p3_self_match_with_face` covers the common case: voice matches the current holder + face is visible → trust the match. `_p3_above_self_match` covers the offscreen case with a higher floor (`VOICE_ROUTING_SELF_MATCH_OFFSCREEN = 0.45`). `_p3_self_match_below_floor` returns ambiguous when the score is below the absolute floor (`VOICE_ROUTING_SELF_MATCH_FLOOR = 0.30`) — this is the poisoning protection: if the holder's own voice scores below 0.30, the audio is likely something else (replay attack, recorded clip).

P0.11 Bug-W fix did NOT change P3 floors. The poisoning protection is calibrated for mature speakers; bootstrap is handled by a separate path (P5 thin-profile relaxation, §60.6).

### 60.5 P4 — below-threshold voice scores and the negative-cosine fix

The four P4 rules handle voice scores below the switch threshold:

- `_p4_pyannote_vouched_stranger` — pyannote reported 2+ segments (multi-speaker turn) AND ECAPA didn't find a confident match. Open a new stranger session.
- `_p4_new_stranger_low_match` — single-segment turn with score below threshold. Open a new stranger session.
- `_p4_voice_ambiguous_no_candidates` — ambiguous score, no presence candidates → hold current.
- `_p4_voice_ambiguous_with_candidates` — ambiguous score, multiple visible candidates → return ambiguous.

The **negative-cosine fix** (2026-05-02, documented in Part XXXII §202) changed the precondition on `_p4_pyannote_vouched_stranger` and `_p4_new_stranger_low_match` from `claim.confidence == 0.0` (exact equality on gallery miss) to `claim.confidence <= 0.0` and `claim.confidence < VOICE_RECOGNITION_THRESHOLD AND claim.confidence != 0.0` respectively. ECAPA-TDNN routinely returns negative cosines for anti-correlated speakers; the original `== 0.0` check silently dropped these.

### 60.6 P5 — no-session and last-resort

`_p5_no_session_new_stranger` fires when no session is active and there's any real signal — a non-zero `claim.confidence` or a non-empty `presence.unrecognized_track_ids` opens a stranger session. The "thin-profile relaxation" carry-over from `_p3_self_match_with_face`'s historical Priority 3.5 — bootstrap-period strangers with thin profiles are handled by the engagement gate's bootstrap credits (Part XL §266) rather than a routing-cascade special case.

The `_last_resort_ambiguous` rule is the cascade's safety net: returns `ambiguous` when no other rule matched. In a fully-covered cascade this never fires; the P0.10 B2 fail-safe in `pipeline.py` logs `[Reconciler] WARN: no rule fired` if `_rc_decision is None` despite this rule's existence (structural insurance against a future refactor that drops the last-resort rule).

## 61. Effective Switch Threshold (Thin-Profile Adaptation)

The P1 confident-switch floor is not constant. The reconciler reads `session.voice_gallery_sizes[claim.pid]` and applies an adaptive floor:

```python
def _effective_switch_threshold(v_pid: str, sizes: dict[str, int]) -> float:
    n = sizes.get(v_pid, 0)
    if n < N_INITIAL_VOICE:
        return 0.70  # thin profile — require more evidence to switch
    return VOICE_SPEAKER_SWITCH_THRESHOLD  # mature profile — configured threshold (0.50)
```

A mature profile produces stable scores; a thin profile (fewer than `N_INITIAL_VOICE = 5` samples) can spike above the configured threshold on a single utterance that happens to resemble the mean. Requiring 0.70 for thin-profile switches prevents spurious hand-overs early in the profile's life.

The function is part of `core/reconciler.py` (not `pipeline.py` — it's a pure helper consumed by `_p1_confident_voice_switch`).

## 62. `presence.visible_pids` and `unrecognized_track_ids` — How Vision Talks to Routing

The `PresenceState` shape is the contract between the vision channel and the reconciler:

```python
@dataclass(frozen=True)
class PresenceState:
    visible_pids:           tuple[str, ...]        # face-recognised pids in frame
    unrecognized_track_ids: tuple[str, ...]        # SORT track ids without recognition
    per_pid_confidence:     dict[str, float]       # face_match_conf per visible pid
    timestamp:              float = 0.0            # frame timestamp
```

The vision channel emits *what is currently visible*. Stale-state expiry happens upstream (the vision loop applies `SCENE_STALE_SECS` before calling `observe_scene`). The reconciler acts on the snapshot it gets and does not look up "what was visible 30 seconds ago".

`visible_pids` is the face-only roster — voice-only sessions are NOT included (compare the legacy `_persons_in_frame` dict which dual-sourced face + voice and required the `_face_in_frame` helper to disambiguate). The architectural cleanup in Part XXXII makes this explicit by design: vision only sees vision, voice only sees voice, the reconciler integrates.

`unrecognized_track_ids` carries the SORT tracker's track ids for faces detected but not yet recognised. The reconciler uses this for the `_p5_no_session_new_stranger` "any real signal" condition (an unrecognized face is real signal even if no voice match fires).

## 63. The Reconciler-Shadow Block and Band Divergence

`pipeline.py` (~line 7100 pre-P0.10-Phase-2-cleanup) carries a Reconciler-Shadow logging block — a 14-field rich-format log line emitted on every routing decision for observability during the cutover validation window. The block's trigger evolved across phases:

- **Phase 3 (shadow mode):** `_rc_decision.action != _routing_action` — compare the reconciler's decision to the legacy router's decision; log divergences.
- **Phase 4 (cutover) + P0.10:** retargeted to band-divergence detection. The trigger fires when the rule that fired isn't the rule expected for the utterance's `utt_band` per the `EXPECTED_RULES_BY_BAND` map.

The legacy "compare to `_resolve_actual_speaker`" trigger became unworkable after Phase 2 deletion. The retarget to band-divergence was the **developer-improves-on-spec** moment for P0.10 Block C (Part L §327 — 4th instance) — the architectural intent (catch divergences between expected and actual routing) was preserved while the mechanism changed.

The shadow block + the `ROUTING_USE_RECONCILER` flag are scheduled for deletion at the close of the P0.10 validation window (`tests/p0_10_validation_runbook.md`, Part XLIII §292).

## 64. Scene Roster (`_build_scene_block`)

The `<<<SCENE>>>` prompt block is built once per turn and injected into the system prompt. Its inputs are the session state + `presence.visible_pids` + voice-only-offscreen recency. The structure:

```
<<<SCENE>>>
  speaking now: Jagan (best friend)
  also present: Chloe (visitor, recently spoke 4s ago)
  offscreen recent: Sweetie (known, heard 25s ago)
<<<END>>>
```

### 64.1 Sources combined

- **Speaking now** — the current turn's pid (after routing).
- **Also present** — other sessions active in the SessionStore.
- **Offscreen recent** — pids heard within `SCENE_VOICE_STALE` (30s) that no longer have a session.

### 64.2 Dispute label override (Finding M, Session 56)

If a session is `disputed`, it's labeled "disputed identity" regardless of its base person_type. This keeps the SCENE block consistent with the `<<<IDENTITY DISPUTED>>>` block (Part XV §103) — both treat the speaker as unknown until the dispute resolves.

### 64.3 SHA-256 caching (Wave 6 Item 23)

`_build_scene_block` caches its output by SHA-256 of all inputs. Repeated turns with no scene change return the previously-built string directly. See **Part XLVII §304** for the cache architecture and invariants. Gated by `SCENE_BLOCK_CACHE_ENABLED = True`.

### 64.4 Toggle

`SCENE_BLOCK_ENABLED = True` globally. The block is injected every turn. Disabling it removes multi-person awareness from the brain's context — useful only for single-speaker test configurations.

---
---

# Part XI — Engagement Gate and Enrollment

## 65. Stranger Workflow

### 65.1 High-level flow

```
stranger voice detected (v_pid = None, v_score < threshold)
  ↓
new session pid = stranger_<uuid>
session opens, waiting_for_name = True
person_type = "stranger"
no bootstrap credits yet (engagement_gate_passed = False)
  ↓
stranger speaks — gate check
  ↓
did they say the system name?  ← phonetic match (§66)
  ↓
NO                        YES
  ↓                         ↓
Silent        waiting_for_name = False
[gate blocked]  engagement_gate_passed = True (retroactively)
Log, do not respond.   Progressive enroll DB row
                       (§67) + bootstrap credits
                         ↓
                    normal conversation flow
```

### 65.2 `STRANGER_REQUIRE_SYSTEM_NAME` toggle

`True` by default. If we ever want to disable the gate (e.g., for demo scenarios), this flag does it. We keep it on for two reasons:
- Privacy: strangers can't just walk up and start pulling data.
- Feel: the system feels *invited into* conversation rather than *lurking*.

## 66. System-Name Phonetic Gate

### 66.1 `_name_heard_in(text, system_name) -> (bool, method)`

```python
def _name_heard_in(text, system_name):
    # Exact word-boundary match first
    if re.search(r"\b" + re.escape(system_name) + r"\b", text, re.IGNORECASE):
        return True, "exact"
    # Phonetic fallback via jellyfish Double Metaphone
    sys_codes = dmetaphone(system_name)
    for word in re.findall(r"\b\w+\b", text):
        for code in dmetaphone(word):
            if code and code in sys_codes:
                return True, "phonetic"
    return False, None
```

### 66.2 Why phonetic fallback

Whisper isn't perfect. "Kara" may come back as "Cara", "Carah", "Karah", "Carrow". Requiring exact spelling match would fail users whose accent Whisper transcribes differently.

Double Metaphone produces a phonetic code for each word; two words with the same code sound similar. `Kara` → `('KR', None)`, `Cara` → `('KR', None)`. Same code → match.

### 66.3 Word boundary enforcement

The exact-match branch uses `\b...\b` to prevent false positives like "Kara" matching in "reflex". Session 22 G4 fixed this.

### 66.4 The gate in the conversation loop

```python
if _cur_pid and _active_sessions.get(_cur_pid, {}).get("waiting_for_name"):
    _name_heard, _method = _name_heard_in(text, _active_system_name)
    if _name_heard:
        _active_sessions[_cur_pid]["waiting_for_name"] = False
        print(f"[Pipeline] Stranger {_cur_pid} addressed system by name{_method_note} — engaging")
        # Progressive enroll (§67) ...
    else:
        print(f"[STT] STRANGER/{_cur_name} [gate blocked — '{_active_system_name}' not heard]: {text}")
        continue   # skip the turn, no response
```

## 67. Progressive Enrollment

### 67.1 What it does

When a stranger first passes the gate, we:
1. Create a DB row in `persons` with their stranger pid.
2. If a face was captured for this pid in `_unrecognized_embeddings[track_id]`, add that embedding to `embeddings` with `source='progressive_enroll'`.
3. Grant bootstrap credits (6) to the session's identity_evidence.
4. Accumulate the current audio buffer as their first voice sample.

### 67.2 Two branches (Bug C post-review)

```python
_face_captured = False
_gate_track = next((tid for tid, pid in _stranger_track_map.items() if pid == _cur_pid), None)
if _gate_track is not None and _gate_track in _unrecognized_embeddings:
    _gate_emb = _unrecognized_embeddings[_gate_track]
    if db.add_embedding(_cur_pid, _gate_emb, "progressive_enroll"):
        print(f"[Pipeline] Progressive enroll: face embedding stored for {_cur_pid}")
        _face_captured = True

if len(audio_buf) > 0:
    if _face_captured:
        # Real face captured — seed full witness evidence
        _active_sessions[_cur_pid]["voice_face_confirmed"] = True
        _update_identity_evidence(
            _cur_pid,
            face_last_seen_ts=time.time(),
            anti_spoof_live=True,
            face_match_conf=0.50,
            bootstrap_credits=N_INITIAL_VOICE_BOOTSTRAP,
        )
        _t = asyncio.create_task(_accumulate_voice(_cur_pid, audio_buf, db, face_verified=True))
    else:
        # Voice-only — only bootstrap credits; NO face evidence fabrication
        _update_identity_evidence(
            _cur_pid,
            bootstrap_credits=N_INITIAL_VOICE_BOOTSTRAP,
        )
        _t = asyncio.create_task(_accumulate_voice(_cur_pid, audio_buf, db, face_verified=False))
    _voice_tasks.add(_t); _t.add_done_callback(_voice_tasks.discard)
```

### 67.3 Why the split matters

Before the split (Bug C), face evidence was written unconditionally at gate pass. Chloe (voice-only, behind the laptop) had `face_match_conf=0.50` in her evidence despite never being on camera. The brain's `<<<IDENTITY EVIDENCE>>>` block lied, and Path A (face witness) would falsely grant accumulation until the ts aged past 10s. Post-fix, voice-only strangers only get bootstrap credits; the evidence reflects reality.

## 68. First-Boot Enrollment Flow

See §10. Key points:
- Only runs when no best_friend exists in DB.
- Captures 20 face embeddings with explicit user consent.
- Anti-spoof gated.
- Creates the `best_friend` row and sets system_identity.

## 69. Background Enrollment

Not currently enabled. An earlier iteration allowed background enrollment of unknown faces that were consistently seen. Removed because:
- Privacy: background-enrolling a face without consent is creepy.
- Anti-spoof is less reliable passively.
- Progressive enrollment (§67) covers the legitimate cases.

We do, however, track unidentified faces as `silent_observations` — see §119.

---
---

# Part XII — Conversation Flow

## 70. `conversation_turn` Anatomy

This is the function that runs once per turn. It takes a pid, a transcribed user text, and the audio buffer; it produces (via TTS) a spoken response and (via DB writes) a logged turn.

### 70.1 Signature

```python
async def conversation_turn(
    person_id: str,
    text: str,
    audio_buf: np.ndarray,
    *,
    voice_state: dict,
    vision_state: dict,
    ...
) -> None:
```

### 70.2 Flow

1. **Primary-person and state update.** Resolve `_cur_pid` = pid passed in. Set pipeline state to THINKING.
2. **Voice accumulation decision.** Call `_voice_accum_allowed(session)` → if allowed, spawn `_accumulate_voice` task.
3. **History load.** `history = db.load_conversation_history(pid)` — up to `CONVERSATION_HISTORY_LIMIT=100` turns.
4. **System prompt composition.** Call `_build_system_prompt(...)` with all the context blocks.
5. **Memory search callback.** Construct `_make_memory_search_fn(pid, db)` — this is the function the brain calls when it invokes `search_memory`.
6. **Streaming call.** Start the `ask_stream(text, ...)` async generator.
7. **Sentence-streaming TTS.** Pipe tokens into `_sentence_stream`, then `speak_stream`. Tool-call events are intercepted and dispatched.
8. **Truncation check.** After the stream ends, check `finish_reason`. If truncated (Obs 3: `finish_reason in ("length", "content_filter", None)`) AND the response is a single unterminated word, retry via Ollama.
9. **Logging.** `db.log_turn(pid, "user", text)`; `db.log_turn(pid, "assistant", response)`.
10. **Orchestrator notify.** `_brain_orchestrator.notify()` wakes the agent loop.
11. **State update.** Pipeline state → LISTENING.
12. **State.json write.**

## 71. System Prompt Composition

### 71.1 `_build_system_prompt(...)` in `core/brain.py`

Produces a single string containing all the context blocks glued together. The blocks are (in order):

1. **Persona / identity line.** "You are a robot dog named {system_name}. Your best friend is {best_friend_name}. ..."
2. **`<<<SENSORS>>>`** — vision and voice channel state.
3. **`<<<SCENE>>>`** — multi-person scene roster.
4. **`<<<TOOL ACCESS FOR THIS SPEAKER>>>`** — which tools the current speaker's person_type allows.
5. **`<<<IDENTITY EVIDENCE>>>`** — structured evidence dict with verdict.
6. **`<<<IDENTITY DISPUTED>>>`** — only included when session is disputed.
7. **Memory context.** Results of `search_memory` calls if any, injected here.
8. **Emotion context.** Rolling 3-turn dominant emotion per speaker.
9. **Prompt addendum.** PromptPrefAgent's active-preferences string.
10. **Room context.** Cross-person excerpts (when multiple sessions active).
11. **Household context.** Household facts injected if relevant.

### 71.2 Why so many blocks

Each block addresses a specific failure mode we saw in early versions:
- `<<<SENSORS>>>` — prevents the brain from saying "I see you smiling" when vision says no face visible.
- `<<<SCENE>>>` — prevents ignoring other people in the room.
- `<<<TOOL ACCESS>>>` — prevents burning 5 turns trying a blocked tool (Session 61).
- `<<<IDENTITY EVIDENCE>>>` — gives the brain sensor-level trust calibration.
- `<<<IDENTITY DISPUTED>>>` — prevents the brain from treating a claimed identity as real when sensor disagrees.
- Memory context — the brain can't "recall" without explicit memory injection.
- Emotion context — enables "you seem tired today" responses without forcing an emotion-check tool.
- Prompt addendum — communication-style prefs ("keep responses under 2 sentences").
- Room context — cross-person awareness.
- Household context — relationship awareness.

### 71.3 Block order matters

Sensor/scene/tool blocks come before content blocks because:
- The brain uses them to *frame* the content.
- Truncation in the middle of the prompt (rare but possible) is less damaging to the front than the back.

## 72. Prompt Blocks (Full Catalog as of Session 113.1)

> **Note.** The original "All Eight Prompt Blocks" catalogue has expanded to sixteen blocks since Session 65 with the Phase 3A and Phase 3B work. The sub-sections below retain the original block descriptions (SENSORS / SCENE / TOOL ACCESS / IDENTITY EVIDENCE / IDENTITY DISPUTED / memory context / emotion / prompt addendum) and then reference Parts XXV and XXVI for the full story on the new blocks.

### The full prompt-block list (order matters — most rendered conditionally):

| Block | Gated By | Details |
|---|---|---|
| `<<<SENSORS>>>` | always | §72.1 |
| `<<<SCENE>>>` | `SCENE_BLOCK_ENABLED` | §64, §72.2 |
| `<<<ROOM>>>` | `ROOM_BLOCK_ENABLED` + ≥2 sessions | Part XXVI §164-§165 |
| `<<<TURN ARBITRATION>>>` | `TURN_ARBITRATION_ENABLED` (appended to ROOM) | Part XXVI §166 |
| `<<<RECENT ROOMS>>>` | `ROOM_END_SYNTHESIS_ENABLED` + recent rows exist | Part XXVI §172 |
| `<<<TOOL ACCESS FOR THIS SPEAKER>>>` | always | §72.3 |
| `<<<IDENTITY EVIDENCE>>>` | `IDENTITY_EVIDENCE_BLOCK_ENABLED` | §58, §72.4 |
| `<<<IDENTITY DISPUTED>>>` | disputed session | §72.5 |
| `<<<STRANGER IDENTITY>>>` | `STRANGER_IDENTITY_BLOCK_ENABLED` + stranger + ≥2 user turns | Part XXV §158 |
| `<<<VISITOR CONTEXT>>>` | `VISITOR_CONTEXT_BLOCK_ENABLED` + `[visitor_id:` marker | Part XXV §157 |
| `<<<CROSS-PERSON PRIVACY>>>` | non-best_friend session | Part XXV §156 |
| `<<<CROSS-PERSON PRIVACY (OWNER MODE)>>>` | best_friend session | Part XXV §156 |
| `<<<HONESTY POLICY>>>` | `HONESTY_POLICY_BLOCK_ENABLED` | §72.9 |
| `<<<HEDGED NAMING CONTRACT>>>` | `HEDGED_NAMING_CONTRACT_ENABLED` | §72.10 |
| `<<<SAFETY CRITICAL>>>` (appended narrative) | visitor with safety_flags | Part XXV §159 |
| `<<<EMOTION>>>` | `EMOTION_ENABLED` | §72.7 |
| `<<<PREFERENCES>>>` (prompt addendum) | PromptPrefAgent output | §72.8 |

### The original eight — verbatim entries follow.


### 72.1 `<<<SENSORS>>>`

```
<<<SENSORS>>>
  face: Jagan (conf=0.82)
  voice: 2 speakers detected: Jagan + Chloe
    (mic is picking up two people this turn — consider addressing both)
<<<END>>>
```

Fields:
- `face:` — name + recognition_conf label (high ≥ 0.45 / medium ≥ 0.28 / low), or "none" if no face.
- `voice:` — speaker-ID result. Can be single speaker, multi-speaker (diarization), or no-voice.

### 72.2 `<<<SCENE>>>`

See §64.

### 72.3 `<<<TOOL ACCESS FOR THIS SPEAKER (person_type='...')>>>`

```
<<<TOOL ACCESS FOR THIS SPEAKER (person_type='best_friend')>>>
  Allowed:
    - shutdown
    - update_system_name
    - update_person_name
    - report_identity_mismatch
    - search_web
    - search_memory
<<<END>>>
```

Human-readable summary of `TOOL_PRIVILEGES[tool]` for the current person_type. The brain doesn't have to guess what it can call.

For a stranger, the list is shorter:
```
  Allowed:
    - update_person_name
    - report_identity_mismatch
    - search_web
  Blocked:
    - shutdown (best_friend only)
    - update_system_name (best_friend only)
    - search_memory (known or best_friend only)
```

### 72.4 `<<<IDENTITY EVIDENCE>>>`

See §58.

### 72.5 `<<<IDENTITY DISPUTED>>>` (conditional)

Only rendered when the current session's person_type is "disputed":

```
<<<IDENTITY DISPUTED>>>
  The speaker has contradicted sensor evidence about who they are.
  Treat them as unknown. Do not reference stored facts about them by
  any name. Use update_person_name if they give a valid clean name.
<<<END>>>
```

### 72.6 Memory context

When `search_memory(query)` fires during the turn, results are injected inline as a user-role message. The brain sees them as "system-provided retrieved context."

### 72.7 Emotion context

```
<<<EMOTION>>>
  Jagan's dominant emotion over last 3 turns: joy (0.72)
<<<END>>>
```

### 72.8 Prompt addendum

The prompt addendum is injected from PromptPrefAgent:

```
<<<PREFERENCES>>>
  Prefers brief and direct responses — keep all replies under 2 sentences regardless of topic
  Avoid starting responses with 'So' — vary starters
<<<END>>>
```

### 72.9 `<<<HONESTY POLICY>>>` (Session 68, Bug N Confabulation Defense)

Rendered when `HONESTY_POLICY_BLOCK_ENABLED=True`. Teaches the brain to hedge when memory is sparse, never narrate fabricated conversations, use temporal framing for just-learned facts ("you just mentioned X"), and reference visible conversation turns directly. The block is an always-on companion to `<<<CROSS-PERSON PRIVACY>>>` — honesty covers *don't fabricate what you don't have*; privacy covers *don't disclose what you have but someone else owns*.

Key rules (paraphrased):

- Use "I don't have details about that" when search_memory is empty.
- Never narrate a conversation without specific turn references.
- Never answer "who was the visitor?" from unrelated facts.
- For just-learned facts in the current session, use "you just mentioned X" / "you said earlier" — not "I remember that you..." (reserve the latter for older sessions / search_memory retrieval).
- Reference visible turns directly — don't say "I don't know" when the answer is two turns up.

### 72.10 `<<<HEDGED NAMING CONTRACT>>>` (Session 76, Phase 1.3)

Rendered when `HEDGED_NAMING_CONTRACT_ENABLED=True`. Tells the brain that when it proposes `update_system_name` / `update_person_name` / `shutdown`, its spoken content must use *hedged* phrasing ("I heard Kara — is that right?") rather than confirmation ("Kara it is!"). Closes the divergence risk where content confirms but the server-side gate rejects.

Lands alongside the Phase 1 STRUCTURED OUTPUT CONTRACT (deprecated after Session 79 scope-shrink but the HEDGED NAMING block survived because its concern — verbal uncertainty for rename-class tools — is orthogonal to the JSON-sidecar mechanism).

### 72.11 The `[addressing:X]` marker protocol

Not a full prompt block, but worth mentioning here. In multi-person rooms, the brain prefixes its response with `[addressing:Name]` (or `[addressing:current]`) to express who it's talking to. The pipeline parses + strips the marker before TTS. See Part XXVI §168.

## 73. Streaming Token Flow

### 73.1 `ask_stream` generator

The generator yields events, each a tuple:
- `("text", str)` — a chunk of response text.
- `("tool_calls", list[dict])` — a tool call emission.
- `("finish", str | None)` — end-of-stream with finish_reason.

### 73.2 Consumption in pipeline

```python
async def _token_gen():
    async for ev_type, payload in ask_stream(text, ...):
        if ev_type == "text":
            response_parts.append(payload)
            yield payload
        elif ev_type == "tool_calls":
            tool_calls.extend(payload)
            if any(tc["name"] in HISTORY_OVERRIDE_TOOLS for tc in payload):
                stop_audio()
        elif ev_type == "finish":
            _stream_finish_reason[0] = payload
```

Text chunks are yielded downstream to `_sentence_stream` → `speak_stream` for TTS. Tool calls are deferred — collected into `tool_calls` list for dispatch after stream end.

### 73.3 HISTORY_OVERRIDE_TOOLS

```python
HISTORY_OVERRIDE_TOOLS = frozenset({"update_system_name", "update_person_name"})
```

When these fire mid-stream, we `stop_audio()` immediately. The LLM's streaming text may have already spoken wrong content (e.g., "Sorry I missed that" while calling `update_person_name`); the audio is cut and the tool result's canonical acknowledgment replaces the LLM text in history.

### 73.4 `_stream_finish_reason` as a closure box

A mutable single-element list holds the finish_reason so the nested async generator can write through it. The outer scope reads it after the stream ends.

```python
_stream_finish_reason: list[str | None] = [None]
# ... inside _token_gen:
elif ev_type == "finish":
    _stream_finish_reason[0] = payload
# ... after stream ends:
_finish = _stream_finish_reason[0]
```

This pattern sidesteps Python's `nonlocal` limitations across async generator boundaries. Obs 3 (post-review).

## 74. Sentence Splitter

See §35. Key point: we split on `. ! ?` at word boundaries, emitting complete sentences downstream for TTS. Buffers incomplete tails until the next token.

## 75. Tool Dispatch

### 75.1 `_execute_tool(tool_name, args, pid, person_name, *, db, ...)`

```python
async def _execute_tool(tool_name: str, args: dict, pid: str, person_name: str, *, db, ...):
    # Layer 2: privilege check
    caller_type = _active_sessions.get(pid, {}).get("person_type", "stranger")
    if not _tool_allowed(tool_name, caller_type):
        print(f"[Brain] Tool {tool_name} BLOCKED — {caller_type} not permitted")
        return
    # Layer 3: repeat guard — abort if same (name, args_hash) seen 2+ consecutive times
    ...
    # Layer 4: dispatch
    if tool_name == "update_person_name":
        return await _handle_update_person_name(args, pid, person_name, db)
    elif tool_name == "update_system_name":
        return await _handle_update_system_name(args, pid, person_name, db)
    elif tool_name == "search_web":
        return await _handle_search_web(args, pid, person_name)
    elif tool_name == "shutdown":
        return await _handle_shutdown(args, pid, person_name)
    elif tool_name == "search_memory":
        return await _handle_search_memory(args, pid, person_name, db)
    elif tool_name == "report_identity_mismatch":
        return await _handle_report_identity_mismatch(args, pid, person_name, db)
    else:
        print(f"[Brain] Unknown tool {tool_name!r} — fail-closed, ignoring")
```

### 75.2 Per-tool handlers

Each tool has its own handler in `pipeline.py`. Handlers:
- Validate args.
- Execute the side effect (DB write, network call, etc.).
- Emit a canonical acknowledgment via TTS if HISTORY_OVERRIDE tool.
- Log the outcome.

### 75.3 Dispatch log

Every tool call logs:
```
[Brain] HH:MM:SS.mmm Tool: {name}({args})
[Pipeline] Tool: {canonical-outcome-line}
```

For example:
```
[Brain] 01:22:16.430 Tool: update_system_name({'name': 'Kara'})
[Pipeline] Tool: system name → 'Kara'
```

## 76. History Management

### 76.1 `db.load_conversation_history(pid)` returns turns

```python
def load_conversation_history(self, person_id: str) -> list[dict]:
    cursor = self._conn.execute(
        "SELECT role, content FROM conversation_log WHERE person_id = ? ORDER BY id DESC LIMIT ?",
        (person_id, CONVERSATION_HISTORY_LIMIT),
    )
    rows = cursor.fetchall()
    return [{"role": r[0], "content": r[1]} for r in reversed(rows)]
```

`LIMIT=100` turns returned. Older turns stay in DB and can be retrieved via `search_memory`.

### 76.2 `db.log_turn(pid, role, content)`

INSERT INTO conversation_log. Timestamps auto-populated.

### 76.3 History override on HISTORY_OVERRIDE_TOOLS

When `update_person_name` fires, the LLM text streamed may be wrong. We replace the stored assistant turn with a canonical line ("Got it, Chloe.") rather than logging the LLM's actual output. Session 25 L1 introduced this to prevent history poisoning.

### 76.4 Disputed-session gating

If the session is disputed, `db.log_turn(...)` is *skipped*. Turns stay in-memory only until identity resolves. Session 53 Finding B added this.

### 76.5 Context compression

When estimated token count in history exceeds TOKEN_COMPACT_THRESHOLD (50K), AutoCompact fires — an LLM summarises old turns into a bullet list. Further growth past TOKEN_HARD_LIMIT (100K) triggers hard-trim.

---
---

# Part XIII — Brain / LLM

## 77. Together.ai as Primary

### 77.1 Why Together.ai

- **Streaming** — we need token-by-token output for low TTFT.
- **Function calling** — native support for tool definitions.
- **Turbo tier** — speculative decoding gives ~200-500ms TTFT, dramatically better than non-Turbo.
- **No rate limits** in practice on paid tier.
- **Price** — cheap relative to OpenAI / Anthropic for a model of this quality.

### 77.2 Model choice

`meta-llama/Llama-3.3-70B-Instruct-Turbo`. 70B is the sweet spot: 8B is noticeably less coherent in long multi-turn conversations; 405B is overkill and slower per token.

### 77.3 Switching providers

Config is role-factored:

```python
CHAT_MODEL    = "meta-llama/Llama-3.3-70B-Instruct-Turbo"
CHAT_BASE_URL = TOGETHER_BASE_URL
CHAT_API_KEY  = TOGETHER_API_KEY
```

To move chat to Groq, change those 3 lines. Nothing in pipeline or brain_agent needs to know.

## 78. Ollama as Fallback

### 78.1 Why Ollama

- **Local** — works without internet.
- **Zero config** — `ollama serve` on localhost:11434, pull a model, done.
- **Q&A only** — stateless fallback. No tools, no memory writes.

### 78.2 Model choice

`qwen2.5:7b` — runs comfortably on a laptop GPU, good instruction-following. We only use it when Together.ai is unreachable; it never needs to do the full job.

### 78.3 `ask_offline(text, person_name, history, language, system_note=None)`

The fallback entry point. Takes the same inputs (text + last 10 turns + person name) but produces a single response. No streaming. No function calling. The brain module handles the Ollama HTTP call with a 15-second timeout.

## 79. CloudState Machine

### 79.1 The states

- **ONLINE** — Together.ai is responsive; `ask_stream` routes cloud.
- **SICK** — Together.ai failed one or more calls; next turn uses Ollama. A background `_cloud_retry_loop` pings every 30 seconds.
- **OFFLINE** — reserved for multi-minute outage; same behaviour as SICK for now.

### 79.2 Transitions

```
ONLINE --(call exception)--> SICK
SICK --(background ping OK)--> ONLINE
```

### 79.3 Messaging

When the first call fails:

```
[Brain] Together.ai stream failed: {exception}
[Cloud] State: ONLINE → SICK ({exception class})
```

The user hears a fallback line: "Oops, I'm feeling a bit sick right now... give me a moment to sort myself out." — then the Ollama response.

When recovery:
```
[Cloud] Together.ai recovered — state ONLINE
```

Subsequent turns resume cloud.

### 79.4 Retry loop

Session 22 B8 fixed a bug where the retry loop exited after one success. Now it continues indefinitely; `continue` instead of `return` inside the while loop.

## 80. The Seven Function-Calling Tools

> **Note (Sessions 76 onward).** The tool count grew from 6 to 7 with the addition of `search_room_memory` in Phase 3B.5 (Session 113). The seventh tool is scoped to the current room session's interleaved turn log, which complements the per-person scope of `search_memory`. The descriptions below reflect the current production prompts; the `report_identity_mismatch` and `update_person_name` descriptions were hardened across Sessions 73, 95, 96, 97, 98 after canary runs surfaced misrouting bugs.



### 80.1 `update_person_name`

**Purpose.** The LLM calls this when a speaker tells the system their name ("My name is Chloe") or corrects a mis-attribution.

**Schema.**
```json
{
    "type": "function",
    "function": {
        "name": "update_person_name",
        "description": "...",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "the speaker's correct name"}
            },
            "required": ["name"]
        }
    }
}
```

**Privileges.** All person_types (stranger, known, best_friend, disputed).

**Semantics.**
- Stranger session → promotes to `known`, renames in DB, migrates knowledge (`BrainDB.migrate_entity_name`), rebuilds Kuzu entity (`GraphDB.rebuild_entity_from_knowledge`), promotes shadow node if one exists, clears `waiting_for_name` flag.
- Known or best_friend session → flips session to `disputed` (Session 54/55). Does NOT rename the DB — the speaker's claim conflicts with sensor evidence.
- Disputed session → blocked (Session 54 Finding G); the real person is safe from corruption.

### 80.2 `update_system_name`

**Purpose.** The best friend calls this to name or rename the robot.

**Privileges.** `best_friend` only.

**Semantics.** Updates `system_identity.name` in DB; next system prompt reflects the new name. TTS acknowledges: "Got it, I'll go by {name}."

If already the current name, logs `no-op (already '{name}')` and still returns gracefully.

### 80.3 `search_web`

**Purpose.** Query Tavily for real-time information (news, facts, etc.).

**Privileges.** stranger, known, best_friend.

**Schema.** `{"query": "string"}`

**Semantics.** Called via `ask_stream` tool execution. Cached for 5 minutes per identical query. Time-sensitive queries get automatic date injection. Up to `SEARCH_MAX_PER_TURN=2` sequential calls per turn.

Result format: answer + top snippets concatenated, ≤ 800 chars, injected into the assistant response.

### 80.4 `shutdown`

**Purpose.** Best friend asks the robot to shut down ("go to sleep").

**Privileges.** `best_friend` only.

**Semantics.** Spawns graceful shutdown (`_shutdown_event.set()`). TTS acknowledges "Goodbye!" and the process exits cleanly.

Session 25 B3 added a false-trigger guard — the LLM sometimes called `shutdown` when the user hadn't actually asked. The guard checks the transcript for explicit dismissal keywords before executing.

### 80.5 `search_memory`

**Purpose.** The LLM retrieves relevant stored facts about the current speaker.

**Privileges.** known, best_friend only. Strangers can't search their own memory (they don't have any yet) and can't peek at others'.

**Schema.** `{"query": "string", "scope": "self" | "system"}`

**Semantics.** Routes through BrainDB + EmbeddingAgent semantic search. Returns top K facts above confidence threshold.

### 80.6 `report_identity_mismatch`

**Purpose.** The LLM flags a dispute when the speaker contradicts sensor evidence but doesn't give a replacement name.

**Privileges.** All person_types.

**Schema.** `{"reason": "string"}` — the LLM explains what it observed.

**Semantics.** Flips session to `disputed`. `_disputed_persons.add(pid)` so the BrainOrchestrator pauses extraction. `<<<IDENTITY DISPUTED>>>` block enters the prompt on next turn.

Session 51 Issue #2B added this tool. Before it, the LLM had no way to express "I don't think they are who they claim" without making up a wrong rename.

Sessions 95–98 hardened the description after a cluster of live-canary misroutes. The tool's production description now opens with an **ONLY** clause, enumerates the specific question shapes that are NOT identity denials ("Who were you talking to?", "Who was here?", "Did someone else visit?"), and names `search_memory` as the correct alternative for those question shapes. A 4-item `TRIGGER CHECKLIST` requires all conditions to be true before the call fires (speaker is talking about themselves, denying the sensor, contradicted twice, no replacement name given), and a question-phrase shortcut tells the LLM that utterances containing "who"/"what"/"did" are almost certainly *not* denials.

### 80.7 `search_room_memory` (Phase 3B.5, Session 113)

**Purpose.** Retrieve turns from the current multi-person room session — interleaved across every speaker, sorted chronologically — for questions that span speakers rather than one person's history.

**Privileges.** All person_types (same visibility as the room itself; the room turns already lived behind the same `_visibility_clause` when they were extracted).

**Schema.** `{"query": "string"}` — one search term. The pipeline auto-injects the current `room_session_id` from `_active_room_session`, so the LLM doesn't have to track or pass it.

**Semantics.** Routes through `BrainDB.search_room_turns(room_session_id, query, ...)` in `pipeline._make_room_search_fn`. Returns an empty result with a hint when the room is younger than `SEARCH_ROOM_MEMORY_MIN_TURNS=5` (avoids noisy matches on 1–3 turn rooms) or when `SEARCH_ROOM_MEMORY_ENABLED=False`.

**Good reasons to call (from the tool description).** "What have we talked about tonight?", "When did Lexi mention her interview?", "Did anyone bring up the movie?", "What did we decide about dinner?".

**Do-not-call (also in the description).** Prior sessions — use `search_memory` (per-person scope, different day / different gathering). Last 2–3 turns — already in context. Single-person history questions — use `search_memory`.

**Observability.** On fire: `[Brain] Tool: search_room_memory query='interview' ...`; on the result injection: `[Brain] search_room_memory: N match(es) for 'interview' in room_<id>`; on empty below `SEARCH_ROOM_MEMORY_MIN_TURNS`: `[Brain] search_room_memory: room too young (N<5 turns), returning hint`.

**Why a separate tool, not a `scope` arg on `search_memory`.** The contract is different: `search_memory` is person-scoped (returns facts about one entity, with per-fact `privacy_level` filtering); `search_room_memory` is room-scoped (returns conversation turns, with an implicit "you were participant or owner" boundary). Overloading `scope="room"` on the existing tool would require dynamic arg semantics, make the description block longer, and make retrieval tests harder to reason about. Two tools with clean contracts beat one tool with a mode flag.

## 81. Stream Truncation Handling

### 81.1 When it fires

Post-Obs 3, the condition for retry:
- `response` non-empty.
- `_stream_words ≤ 1`.
- No terminal punctuation (`. ! ? …`).
- `finish_reason in ("length", "content_filter", None)` — authoritative truncation signal.
- No tool calls.
- CloudState ONLINE.

All must be true. Defense in depth: without any one of these, retry is suppressed.

### 81.2 Retry mechanics

- `stop_audio()` cuts the tail of the truncated response.
- `ask_offline` generates the retry via Ollama.
- If the retry is longer than the original, `speak(retry)` plays it.
- History records the retry, not the fragment.

Session 64 Bug 5 + Obs 3 made this robust. The `finish_reason` gate was critical — legitimate short replies like "Hello!" have `finish_reason="stop"` and no longer trigger retry.

## 82. Context Compression — Three Tiers

### 82.1 Tier 1 — MicroCompact (sync)

Truncates individual messages in old history that exceed `MICRO_CHAR_LIMIT=2000` chars. Keeps recent messages intact. Runs every turn as history is built.

### 82.2 Tier 2 — AutoCompact (async LLM)

When estimated tokens (3.5 chars/token heuristic) exceed `TOKEN_COMPACT_THRESHOLD=50000`, async LLM summarises old turns into a bullet list. Keeps `AUTOCOMPACT_KEEP_TURNS=15` recent turn-pairs verbatim; everything older is summarised.

One retry with 2-second backoff on 5xx/network errors (Session 35 Bug-11). 4xx errors skip retry.

### 82.3 Tier 3 — Hard trim

If still over `TOKEN_HARD_LIMIT=100000`, emergency drop oldest turns until budget fits. Logs a warning — this path indicates a failure in Tier 2.

### 82.4 Warning threshold

At `TOKEN_WARN_THRESHOLD=90000` we log `[Brain] Context approaching limit (Ntok)`. Gives human operators a signal without forcing action.

## 83. KAIROS Proactive Wake

### 83.1 Trigger

Every 0.5 seconds, `_kairos_tick()` checks:
- Any active session exists.
- Time since last user speech > `KAIROS_SILENCE_THRESHOLD=30s`.
- Time since last KAIROS fire > `KAIROS_COOLDOWN=120s`.
- Session is not disputed (Session 54 Finding H).
- If there's a pending PatternAnalysisAgent question for this person, prefer it; else let the brain improvise.

### 83.2 The brain call

```python
_kairos_prompt = (
    "The user has been silent for 30 seconds. "
    "If you have something natural to say or ask, say it. "
    "Otherwise respond with the single word SILENT."
)
```

The brain decides — if it responds "SILENT", nothing is spoken and the cooldown still applies (so we don't re-fire immediately). Otherwise, TTS speaks the output.

### 83.3 Why brain-driven

Earlier iterations had deterministic KAIROS questions ("Hey, still there?") that felt robotic. Passing the decision to the brain with a "only speak if natural" instruction produces much better emissions.

### 83.4 Terminal log

```
[KAIROS] Brain proactive wake — 44s silence
[KAIROS] Brain spoke: 'Hey Jagan, is everything okay?'
```

or if SILENT:
```
[KAIROS] Brain proactive wake — 44s silence
[KAIROS] Brain chose silence
```

### 83.5 History and orchestrator

Session 22 B3 made KAIROS log to DB: the user's silence period gets `db.log_turn(pid, "user", "[silence]")` and the brain's response gets logged as assistant. Orchestrator is notified. This keeps the knowledge extraction pipeline consistent — KAIROS-initiated turns are first-class.

---
---

# Part XIV — Knowledge System

The knowledge system is the largest subsystem in the codebase (`core/brain_agent.py` is 6105 lines). Its job is to turn raw conversation transcripts into structured, searchable, evolving knowledge about each person.

## 84. BrainDB Schema

### 84.1 Overview

`brain.db` is a separate SQLite database from `faces.db`. The split is deliberate:
- `faces.db` — identity and conversation log. Core runtime data.
- `brain.db` — derived knowledge, can be wiped and reconstructed from conversation_log.

### 84.2 Tables

| Table | Purpose |
|---|---|
| `knowledge` | Structured facts: (person_id, entity, attribute, value, confidence, captured_at, privacy_level, invalidated_at, ...) |
| `schema_catalog` | Observed attribute names; used for semantic normalisation |
| `agent_log` | Per-turn log of which agents ran, outcomes, latencies |
| `prompt_prefs` | Communication preferences per person (5 types) |
| `object_sightings` | YOLO11 detections (when spatial memory enabled) |
| `object_pattern_questions` | Proactive questions generated from sighting patterns |
| `episodes` | Session summaries by InsightAgent |
| `presence_log` | When people arrived/left (for routine detection) |
| `proactive_nudges` | Hints the brain should consider injecting (VISITOR_ALERT, CROSS_PERSON_HYPOTHESIS, etc.) |
| `watchdog_alerts` | Anomaly signals from WatchdogAgent |
| `social_mentions` | When person A mentions person B |
| `predicate_stats` | Per-attribute contradiction counts (volatility tracking) |
| `household_facts` | Multi-person relationship facts (spouse, parent, cousin) |
| `inter_person_relationships` | Explicit pair relationships |
| `shadow_persons` | Mentioned-but-not-yet-enrolled people |
| `brain_state` | Singleton row tracking `last_turn_id` processed |

### 84.3 `knowledge` — the central table

```sql
CREATE TABLE knowledge (
    id              INTEGER PRIMARY KEY,
    person_id       TEXT NOT NULL,
    entity          TEXT NOT NULL,    -- usually = person's name, sometimes an object
    attribute       TEXT NOT NULL,    -- "favorite_color", "current_mood", etc.
    value           TEXT NOT NULL,
    confidence      REAL NOT NULL,    -- 0-1
    captured_at     REAL NOT NULL,
    contradiction_count INTEGER DEFAULT 0,
    privacy_level   TEXT DEFAULT 'personal',   -- public | personal | household | system_only
    invalidated_at  REAL,                       -- NULL = currently valid
    invalidated_by  INTEGER,                    -- fk to another knowledge.id that superseded this
    stale_penalty   REAL DEFAULT 0.0,           -- RetroScan decrements this
    ...
);
```

The `privacy_level` column is the foundation of the Phase 3A privacy model — it was a 2-tier field (`public` / `private`) through Session 94, and is now a 4-tier field (`public` / `personal` / `household` / `system_only`) as of Session 95 3A.4.5. A one-shot idempotent migration in `BrainDB.__init__` converts legacy `'private'` rows to `'personal'` on first start after the schema change. The default flipped from `'public'` to `'personal'` — fail-closed. Every row written by `ExtractionAgent` carries a tier decided at write time by `_classify_privacy_level` (static map → process cache → LLM fallback). See **Part XXV — Cross-Person Privacy and Safety (Phase 3A)** for the complete story.

### 84.4 Why non-destructive

Deleting facts loses history. `invalidated_at` + `invalidated_by` lets us see the chain of beliefs: Jagan's `current_project` was `"creating an operating system for robots"` at T1, then replaced with `"Kara"` at T2 (with the old row marked invalidated and pointing forward). The past fact is searchable and can be surfaced when relevant.

**Session 105 Bug N addendum.** Non-destructive is not enough on its own for *safety-critical* attributes. When Lexi's `current_mood='suicidal'` was later overwritten by `current_mood='loving'` four turns later during a canary run, the crisis disclosure was effectively erased — the old row sat in the DB with `invalidated_at` set, but no retrieval path surfaced it. The fix is a second attribute family, `expressed_suicidal_thoughts` (and its siblings `mentioned_*`, `reported_*_abuse`, `has_experienced_crisis`), which is append-only by policy: the `ContradictionAgent` short-circuits on any attribute matching `SAFETY_CRITICAL_ATTRIBUTE_PATTERNS` and refuses to REPLACE. The momentary mood keeps its normal overwrite semantics; the historical flag accumulates. See §159 for the full design.

### 84.5 `room_summaries` — the per-room synthesis table (Phase 3B.6)

```sql
CREATE TABLE room_summaries (
    id              INTEGER PRIMARY KEY,
    room_session_id TEXT NOT NULL UNIQUE,
    participants    TEXT NOT NULL,        -- JSON list of person_ids
    started_at      REAL NOT NULL,
    ended_at        REAL NOT NULL,
    topic_tags      TEXT,                 -- JSON list of strings
    safety_flags    TEXT,                 -- JSON list of strings
    summary         TEXT,                 -- LLM narrative, ≤1 paragraph
    turn_count      INTEGER DEFAULT 0
);
CREATE INDEX idx_room_summaries_ended_at ON room_summaries(ended_at DESC);
```

Written by `BrainOrchestrator.synthesize_room` at the end of every multi-person session. Consumed by `get_recent_room_context(person_id, hours=24)` for the `<<<RECENT ROOMS>>>` greeting-enrichment block (Phase 3B.6). See Part XXVI §171.

## 85. BrainOrchestrator

### 85.1 The coordinator

```python
class BrainOrchestrator:
    def __init__(self, db, graph, ...):
        self._triage         = TriageAgent()
        self._extraction     = ExtractionAgent()
        self._contradiction  = ContradictionAgent()
        self._embedding      = EmbeddingAgent()
        self._pref           = PromptPrefAgent()
        self._friction       = FrictionDetectionAgent()
        self._household      = HouseholdExtractionAgent()
        self._pattern        = PatternAnalysisAgent()
        self._nudge          = NudgeAgent()
        self._social         = SocialGraphAgent()
        self._retro          = RetroScanAgent()
        self._watchdog       = WatchdogAgent()
        self._insight        = InsightAgent()
        self._schema_norm    = SchemaNormAgent()
        self._disputed_persons: set[str] = set()
```

### 85.2 The loop

A background task started by `run()`:

```python
async def _loop(self):
    while not self._shutdown:
        new_turns = self._brain_db.fetch_turns_since(last_id)
        for turn in new_turns:
            await self._process_turn(turn)
        await asyncio.sleep(BRAIN_AGENT_POLL_INTERVAL)
```

Polled every 2 seconds; `notify()` can wake it up early.

### 85.3 `notify()` and `notify_session_end()`

- `notify()` — wake the loop immediately (used after each turn).
- `notify_session_end(pid, name)` — schedule session-end synthesis tasks.

Session-end tasks run when a person's session closes:
- PromptPrefAgent full analysis.
- InsightAgent episode storage.
- HouseholdExtractionAgent inference.
- NudgeAgent visitor alert if stranger.
- SocialGraphAgent aggregation.

All gated on dispute state — skipped if the session closed while disputed (Session 53 Finding A).

### 85.4 Dispute gate

```python
if person_id and person_id in self._disputed_persons:
    self._brain_db.log_agent(turn_id, "triage", "skip", "identity disputed")
    return
```

First check in `_process_turn`. If the session is flagged disputed, no extraction. Prevents contradictory facts polluting the wrong pid's knowledge.

### 85.5 `report_dispute_rename_burst(pid, victim_name, victim_type, claimed_name, count, dispute_ts)`

Session 57 N3 added this. When disputed-rename attempts in a single session cross `DISPUTE_RENAME_BLOCK_THRESHOLD=3`, the orchestrator stores a `watchdog_alerts` row with severity `critical` (for best_friend victims) or `warning` (for known victims). Dashboard can surface it.

## 86. TriageAgent

### 86.1 Purpose

Fast no-LLM filter. Decides whether a turn is worth extracting facts from.

### 86.2 Rules

- Skip turns with `role == "assistant"` — only user turns produce new facts.
- Skip turns shorter than `BRAIN_AGENT_MIN_WORDS=4` — too little signal.
- Skip turns from disputed persons.
- Skip turns with `[silence]` content (KAIROS silence markers).

### 86.3 Log format

```
[BrainAgent] HH:MM:SS.mmm Triage: PASS turn N — processing
[BrainAgent] HH:MM:SS.mmm Triage: SKIP turn N — assistant turn
```

### 86.4 Cost

~1ms. Zero LLM tokens.

## 87. ExtractionAgent

### 87.1 Purpose

Call the LLM to turn a conversation turn into a JSON list of (entity, attribute, value) facts.

### 87.2 Prompt

The prompt includes:
- Current turn text.
- Last `BRAIN_AGENT_CONTEXT_TURNS=6` turns as context.
- Instructions to emit structured JSON.
- The speaker's name.

Example output:
```json
[
  {"entity": "Jagan", "attribute": "favorite_car", "value": "BMW M2", "confidence": 0.90},
  {"entity": "Jagan", "attribute": "preferred_transmission_type", "value": "manual", "confidence": 0.80}
]
```

### 87.3 Validation

JSON parsing, whitespace-trim, lowercase attribute normalisation (`Favorite_Car` → `favorite_car`).

### 87.4 Retry (Bug 6 post-review)

`EXTRACT_MAX_RETRIES=2` extra attempts on transient network errors (`httpx.ReadTimeout`, `httpx.ConnectTimeout`, `httpx.NetworkError`). Exponential backoff (1s, 2s). 4xx errors propagate — not retried.

### 87.5 Log format

```
[BrainAgent] HH:MM:SS.mmm Extracted N fact(s) (Nms): Jagan.attr='val', ...
```

## 88. ContradictionAgent

### 88.1 Purpose

When a new fact `(entity, attribute, value)` arrives, check whether it contradicts an existing fact with the same `(entity, attribute)` but different value.

### 88.2 The check

For each new fact:
1. SELECT existing knowledge rows with the same entity+attribute AND `invalidated_at IS NULL`.
2. If none exist → new fact, insert normally.
3. If one exists with the same value → `COMPATIBLE` (just bump confidence with CONFIDENCE_BOOST).
4. If one exists with a different value → call LLM with both values and ask REPLACE or COMPATIBLE.
5. On REPLACE → set old row's `invalidated_at`, insert new row, increment `contradiction_count`.
6. On COMPATIBLE → insert new row alongside (multiple valid values, e.g., multiple hobbies).

### 88.3 Log format

```
[BrainAgent] Contradiction check (Nms): K replaced, L compatible, M new
```

### 88.4 Triggers RetroScan

When a REPLACE happens, `RetroScan` is invoked on up to `MAX_RETROACTIVE_FACTS=5` nearby facts. See §97.

## 89. EmbeddingAgent

### 89.1 Purpose

Semantic embeddings for knowledge rows. Enables `search_memory` to find "facts about cars" without knowing the exact attribute names.

### 89.2 Model

`intfloat/multilingual-e5-large-instruct` via Together.ai. 1024-d embeddings. Instruction-formatted input:

```
Instruction: represent the personal fact for retrieval: Jagan's favorite car is BMW M2.
```

### 89.3 In-memory cache

Keyed by SHA-256 of the input string. Max 1000 entries. Evicted LRU.

### 89.4 Retry

Same pattern as ExtractionAgent: `EMBED_MAX_RETRIES=2` extra attempts on transient errors (Session 24 A8). This is the pattern we reused for Bug 6.

### 89.5 `semantic_search_knowledge(pid, query, top_k)`

Embeds the query, computes cosine similarity against all stored knowledge embeddings for this person (and the person's household if scope=system), returns top K above `EMBED_MIN_CONFIDENCE=0.60`.

## 90. GraphDB — Kuzu

### 90.1 Why a graph

Querying "what does Jagan know about cars" via SQL would be ugly and slow. As a graph query, it's a one-hop traversal from a Person node through MENTIONED edges to Entity nodes.

### 90.2 Schema (v2)

```
Node: Person (name PK, face_id UNIQUE)
Node: Entity (name PK)
Rel:  MENTIONED (from Person to Entity, with properties: count, last_mentioned, shared)
Rel:  RELATES_TO (from Person to Person, with: type, strength)
```

### 90.3 Auto-rebuild on schema bump

`GRAPH_SCHEMA_VERSION=2`. Stored schema version is checked at startup. If different, the graph is wiped and rebuilt from `knowledge` rows. This is the migration mechanism — we don't write migration scripts.

### 90.4 Kuzu self-heal (Session 58)

A corrupted Kuzu directory used to crash startup. Fix: wrap `kuzu.Database()` in try/except, wipe the path + retry once. Knowledge rows are the source of truth; rebuild is deterministic.

### 90.5 `find_shared_entities(name_a, name_b)`

Returns entities both persons have mentioned. Used by NudgeAgent for CROSS_PERSON_HYPOTHESIS.

## 91. PromptPrefAgent

### 91.1 Purpose

Infer and store communication preferences so the brain can adapt its style per person.

### 91.2 Five preference types

1. **communication_style** — formal vs casual vs playful.
2. **response_length** — brief vs detailed.
3. **greeting_style** — warm vs perfunctory.
4. **response_habit** — avoid starters, avoid filler, etc.
5. **topic_interest** — areas they want to hear about.

### 91.3 Staging and auto-confirm

Each pref starts `staged`. After seeing the same pref `PREF_AUTO_CONFIRM_THRESHOLD=3` sessions in a row without contradiction, it becomes `activated`. Only activated prefs are injected into the prompt addendum.

### 91.4 Intra-session pass

Every `INTRA_PREF_TURN=15` turns, a lightweight analysis runs on the last `INTRA_PREF_TURNS_LIMIT=6` turns to detect emerging prefs mid-session. The result may be "addendum injected" for the next turn (nudge rather than confirm).

### 91.5 Session-end analysis

On `notify_session_end`, a full analysis runs on the last `PREF_ANALYSIS_TURNS=40` turns of the session. Any new staged pref is written; existing prefs are bumped in sessions_seen count.

## 92. FrictionDetectionAgent

### 92.1 Purpose

Detect when a person's observed behaviour contradicts an active preference.

### 92.2 Example

Active pref: `response_length = "brief — keep under 2 sentences"`. Observed: the brain just emitted a 5-sentence reply. Friction detected. Next turn, the addendum escalates the injection urgency: the active pref appears with stronger wording.

### 92.3 Escalation n+1

If friction persists, the injection gets more forceful each session until either the behaviour aligns or the user explicitly revokes the pref.

### 92.4 When not to fire

Below `FRICTION_MIN_CONFIDENCE=0.70` the pref is considered too weak to enforce.

## 93. HouseholdExtractionAgent

### 93.1 Purpose

Extract household-level facts: who lives together, family relationships, shared spaces.

### 93.2 Outputs

- `household_facts` rows — facts that apply to the household as a whole.
- `inter_person_relationships` rows — explicit (A, relationship, B) tuples.
- `shadow_persons` rows — people mentioned but not enrolled.

### 93.3 Provisional → settled

A household fact starts `provisional`. After `HOUSEHOLD_DISPUTE_SETTLE_SESSIONS=2` sessions of corroboration without contradiction, it becomes `settled`.

### 93.4 Shadow person promotion

When someone enrolls whose name matches a shadow_persons entry (phonetic match), the shadow is promoted to a real person. Its existing facts attach to the new pid via `BrainOrchestrator.promote_shadow_to_confirmed`.

## 94. PatternAnalysisAgent

### 94.1 Purpose

Analyse object sightings (YOLO11 when enabled) for interesting behavioural patterns. Generate proactive questions the robot can ask naturally during lulls.

### 94.2 Triggers

Runs when `object_sightings` has ≥ `PATTERN_MIN_SIGHTINGS=30` rows; cooldown `PATTERN_COOLDOWN=3600s`.

### 94.3 Output

Questions stored in `object_pattern_questions` with confidence. KAIROS consumes them — when the user is silent, the brain may grab a pending pattern question.

### 94.4 Currently disabled

`VISION_YOLO_ENABLED=False`. We haven't turned on spatial memory vision yet. The agent is wired but inactive. Turning it on is a config flip.

## 95. NudgeAgent

### 95.1 Purpose

Write `proactive_nudges` rows that the brain can surface in future turns.

### 95.2 Nudge types

- **VISITOR_ALERT** — a stranger visited while best_friend was absent. Generated on session-end for stranger sessions with ≥ 1 user turn.
- **CROSS_PERSON_HYPOTHESIS** — two enrolled people both mentioned the same entity. Maybe they're connected.
- **ROUTINE_DEVIATION** — person arrived later than usual (RoutineAgent).
- **PATTERN_QUESTION** — pulled from PatternAnalysisAgent.

### 95.3 Template fix (Bug 3 post-review)

Session 64 Bug 3 fixed `(possibly your null)` rendering when the relationship field was the string `"null"` or `"None"`. Both graph-match (line 4458) and fuzzy-match (line 4503) paths reject these.

### 95.4 Expiry

Nudges expire after `NUDGE_EXPIRY_HOURS=72`. Max `CROSS_PERSON_MAX_NUDGES=3` pending per person.

## 96. SocialGraphAgent

### 96.1 Purpose

Track which person mentions which other person in their conversations.

### 96.2 `social_mentions` table

```sql
CREATE TABLE social_mentions (
    id                INTEGER PRIMARY KEY,
    source_person_id  TEXT NOT NULL,
    name              TEXT NOT NULL,    -- mentioned name (may be shadow)
    relationship      TEXT,             -- "friend", "mother", etc. or NULL
    context           TEXT,
    count             INTEGER DEFAULT 1,
    last_mentioned    REAL NOT NULL,
    ...
);
```

### 96.3 Usage

- NudgeAgent uses it for CROSS_PERSON_HYPOTHESIS.
- HouseholdAgent uses it to infer relationships.
- Log format: `[SocialGraph] Mention stored: {name} ({relationship}) — []`

## 97. RetroScan

### 97.1 Purpose

When a fact is REPLACEd, look back at related facts for staleness.

### 97.2 Mechanism

Call an LLM on up to `MAX_RETROACTIVE_FACTS=5` nearby facts (by attribute similarity) with both the old value, the new value, and the neighbour fact. The LLM returns STALE or VALID.

STALE verdicts apply `RETRO_STALE_PENALTY=0.15` to the neighbour's confidence via `stale_penalty` column.

### 97.3 Log format

```
[RetroScan] Stale: Jagan.recent_focus (-0.15) — The related fact "developing a system" is still generally true, but its specificity has decreased...
```

### 97.4 Non-destructive

STALE doesn't delete. The confidence drop may eventually push the fact below `DREAM_PRUNE_FLOOR=0.15` where dream consolidation invalidates it.

## 98. WatchdogAgent

### 98.1 Purpose

Detect anomalies and store `watchdog_alerts` for dashboard surfacing.

### 98.2 Alert types

- `SILENT_OBS_SPIKE` — sudden jump in silent_observations rows (new strangers in frame).
- `UNUSUAL_HOUR_ACTIVITY` — activity between WATCHDOG_UNUSUAL_HOUR_START and WATCHDOG_UNUSUAL_HOUR_END (0-5am).
- `DISPUTE_RENAME_BURST` — from Session 57 N3; fires when a single session crosses DISPUTE_RENAME_BLOCK_THRESHOLD=3.
- `ANTISPOOF_SPIKE` — sustained anti-spoof rejections.

### 98.3 Interval

Runs every `WATCHDOG_INTERVAL=60s`.

### 98.4 Alert schema

```sql
CREATE TABLE watchdog_alerts (
    id         INTEGER PRIMARY KEY,
    kind       TEXT NOT NULL,
    severity   TEXT NOT NULL,  -- info/warning/critical
    metadata   TEXT,            -- JSON
    created_at REAL NOT NULL,
    resolved_at REAL
);
```

## 99. InsightAgent

### 99.1 Purpose

At session end, produce a short episode summary — a ~100-token narrative of what happened in the session, the dominant mood, the significance.

### 99.2 Schema

```sql
CREATE TABLE episodes (
    id              INTEGER PRIMARY KEY,
    person_id       TEXT NOT NULL,
    session_start_ts REAL NOT NULL,
    session_end_ts   REAL NOT NULL,
    turn_count      INTEGER,
    summary         TEXT,
    mood            TEXT,        -- neutral, positive, negative
    significance    REAL,        -- 0-1
    ...
);
```

### 99.3 Thresholds

Skip when session has `< INSIGHT_MIN_TURNS=3`. LLM output capped at `INSIGHT_MAX_TOKENS=300`.

### 99.4 Uses

- `run_intention_followup` checks episodes for unfollowed promises ≥ 24h old.
- Dashboard can show a timeline.
- LLM can pull episodes via search_memory if relevant.

## 100. Dream Loop — Memory Consolidation

### 100.1 Purpose

During idle periods, do the "memory gardening" that would be too expensive per-turn: decay, prune, normalise, reconcile.

### 100.2 Triggers

Two paths:
- **Idle** — no active sessions for `DREAM_IDLE_MINUTES=5`, and `DREAM_COOLDOWN=3600s` since last dream.
- **Force** — busy system with no idle window; `DREAM_MAX_INTERVAL=10800s` force-fire even during active session.

### 100.3 Cycle operations

1. **Decay** — Apply `eff_conf = stored_conf × exp(-DECAY_LAMBDA × days_since_captured)` to every knowledge row.
2. **Prune** — If effective confidence drops below `DREAM_PRUNE_FLOOR=0.15`, invalidate the row.
3. **Schema normalisation** — SchemaNormAgent clusters attribute synonyms (≥ SCHEMA_NORM_THRESHOLD=0.97) and auto-merges.
4. **Row caps** — Enforce KNOWLEDGE_MAX_ROWS, PRESENCE_MAX_ROWS, EPISODE_MAX_ROWS, SOCIAL_MENTIONS_MAX_ROWS, AGENT_LOG_MAX_ROWS via oldest-first deletion.
5. **Age-based pruning** — WATCHDOG_MAX_AGE_DAYS, AGENT_LOG_MAX_AGE_DAYS, PATTERN_Q_MAX_AGE_DAYS.
6. **Stranger TTL** — delete strangers unseen for `STRANGER_TTL_DAYS=7`.
7. **Stranger voice TTL** — delete thin stranger voice profiles unupdated for `STRANGER_VOICE_TTL_DAYS=3`. Cache evicted FIRST (Finding J ordering).
8. **Voice gallery reconciliation (Obs 1)** — compare `_voice_gallery_sizes` to `db.load_voice_profile_sizes()`. Divergence → full reload.
9. **Silent observations retention** — `SILENT_OBS_RETENTION_DAYS=45`.

### 100.4 Log format

```
[Dream] Force trigger — system has been busy, running dream during active session
[Dream] Starting consolidation cycle (idle=0.0min, force=True)
[Dream] Consolidation started — N person(s) in DB
[Dream] Consolidated — N pruned, M decayed, K stable
[Dream] Voice gallery cache reconciled: N pid(s) out of sync
```

### 100.5 Cost

Typical cycle: ~500ms on a 100-person DB. Negligible at our scale.

---
---

# Part XV — Dispute State Machine

## 101. Origin — The Uncle-False-Match Incident

In an earlier session, Jagan's uncle visited. The face recognition matched him to Jagan at score ~0.35 (above threshold of 0.18 at the time). The system greeted him as Jagan. He didn't correct it. A few turns in, the brain extracted facts attributing the uncle's statements to Jagan.

By the time the mistake was caught, Jagan's knowledge graph was polluted with uncle's facts. Recovery required factory reset (there was no partial-rollback mechanism).

The incident exposed two gaps:
1. **Recognition was too permissive.** Fixed by raising thresholds and adding the centroid gate.
2. **There was no mechanism for the speaker to say "no, I'm not that person."** The LLM was told the speaker was Jagan; it had no way to express doubt.

The dispute state machine closes the second gap.

## 102. Trigger Paths

> **Architectural note (2026-05-15).** Pre-P0.7, every dispute-trigger site directly wrote `_active_sessions[pid]["person_type"] = "disputed"` and the three companion fields (`dispute_set_at`, `prior_person_type`, `disputed_claimed_name`). Different sites set different subsets — `prior_person_type` was missed at one site, `dispute_set_at` was missed at another, and auto-clear sometimes restored to `"known"` instead of the original type. P0.7 routed all three operations through the named transition `transition_to_disputed(pid, claimed_name, reason, now)`. The transition captures `prior_person_type` atomically with the other three fields; restore via `clear_dispute(pid, now)` reads `prior_person_type` and fail-closes to `"stranger"` per P0.2 if missing.

A session enters disputed state via one of these paths:

1. **`report_identity_mismatch` tool** (Session 51 #2B). LLM flags that the speaker contradicts the sensor. The `_handle_report_identity_mismatch` handler (Part XLI §272) calls `await _session_store.transition_to_disputed(pid, claimed_name=None, reason="report_identity_mismatch", now=time.time())`.
2. **`update_person_name` on a known session** (Session 54/55). A speaker whose session is `known` or `best_friend` says they are a different person. Instead of renaming (which would corrupt the real person's row), `_handle_update_person_name` calls `transition_to_disputed(pid, claimed_name=proposed_name, reason="rename_on_known", now=...)`.
3. **Auto-dispute** (rare). An explicit code path for internal consistency checks. Calls the same `transition_to_disputed` method.

The single named transition is the only writer for the four fields. Future paths that want to enter dispute state must call this method; the AST scan in `tests/test_no_raw_disputed_comparisons.py` (P0.1, Part XXXVI §234) rejects any raw `person_type = "disputed"` write outside the helper.

## 103. `<<<IDENTITY DISPUTED>>>` Block

```
<<<IDENTITY DISPUTED>>>
  The speaker has contradicted sensor evidence about who they are.
  Treat them as unknown. Do not reference stored facts about them by
  any name. Use update_person_name if they give a valid clean name.
<<<END>>>
```

Injected in `_build_system_prompt` whenever the session's snapshot satisfies `_is_disputed(snapshot)`. This instructs the brain to behave as if the speaker is a stranger, regardless of the face or voice match.

## 104. `_disputed_persons` Set

`BrainOrchestrator._disputed_persons: set[str]` — pids currently in dispute. Used by the orchestrator to gate agent work:

- `_process_turn` first checks this set; disputed → skip triage/extraction.
- `notify_session_end` skips all 6 session-end helpers when disputed.

`mark_disputed(pid)` and `clear_disputed(pid)` are the orchestrator-side API; the pipeline calls them from inside the corresponding `transition_to_disputed` / `clear_dispute` paths in `SessionStore`.

## 105. Session-End and Conversation-Log Gating

Session 53 Findings A and B made the gating airtight:

- **A (session-end gate):** `notify_session_end` checks `_disputed_persons` and skips PromptPrefAgent, InsightAgent, HouseholdAgent, NudgeAgent visitor alert, and SocialGraphAgent.
- **B (conversation_log gate):** `conversation_turn` and `_kairos_tick` check `_is_disputed(_session_store.peek_snapshot(pid))` before calling `db.log_turn`. Disputed-session turns stay in-memory only; never touch the DB.

This means a dispute leaves no persistent trace beyond the watchdog alert. If it resolves cleanly (via rename), the clean pid's knowledge is unaffected.

The `_is_disputed()` helper is the canonical predicate. Every check in the codebase routes through it (enforced by `tests/test_no_raw_disputed_comparisons.py` — P0.1, Part XXXVI §234) so future changes to dispute state representation (e.g. moving from string to enum) don't have to scatter through every call site.

## 106. Force-Close Timeout

`DISPUTE_MAX_DURATION=180s`. After 3 minutes of dispute with no resolution, `_expire_stale_sessions` force-closes the session. Session 53 Finding C added this because vision can keep matching the wrong person, preventing natural expiry via FACE_LOSS_GRACE.

Session 54 Finding K added a lazy anchor that became unnecessary after P0.7: if `dispute_set_at` is missing (future code path forgot to set it), the old behaviour was to anchor it on first observation. P0.7's `transition_to_disputed` writes `dispute_set_at` atomically with the other three fields, so the field is guaranteed present whenever `person_type == "disputed"`. The lazy-anchor fallback was kept as defense-in-depth but is now unreachable in practice.

## 107. Dispute-Rename Burst Watchdog

Session 57 N3. When disputed-rename attempts accumulate, the rename-block path inside `_handle_update_person_name` calls the named transitions:

```python
# In the disputed rename-block path (P0.7 — named transitions):
await _session_store.increment_block_count(pid)
snap = _session_store.peek_snapshot(pid)
if (snap.disputed_block_count >= DISPUTE_RENAME_BLOCK_THRESHOLD
    and not snap.disputed_block_alerted):
    await _session_store.mark_block_alerted(pid)
    _brain_orchestrator.report_dispute_rename_burst(
        pid,
        victim_name=snap.person_name,
        victim_type=snap.prior_person_type,        # P0.2 fail-closed default
        claimed_name=args.get("name"),
        count=snap.disputed_block_count,
        dispute_ts=snap.dispute_set_at,
    )
```

`increment_block_count` and `mark_block_alerted` are dedicated transitions — both idempotent — that replaced direct dict mutation in P0.7.3. The `mark_block_alerted` transition is idempotent at the field level (sets `disputed_block_alerted=True`), but it's gated by the `if not snap.disputed_block_alerted` predicate so the actual `report_dispute_rename_burst` call fires exactly once per dispute episode.

Severity: `critical` if the victim's prior type was `best_friend` (owner impersonation); `warning` otherwise. Alert stored in `watchdog_alerts` for dashboard surfacing.

---
---

# Part XVI — Tool System

## 108. `TOOL_PRIVILEGES` Table

```python
TOOL_PRIVILEGES: dict[str, frozenset[str]] = {
    "shutdown":                 frozenset({"best_friend"}),
    "update_system_name":       frozenset({"best_friend"}),
    "update_person_name":       frozenset({"stranger", "known", "best_friend", "disputed"}),
    "report_identity_mismatch": frozenset({"stranger", "known", "best_friend", "disputed"}),
    "search_web":               frozenset({"stranger", "known", "best_friend"}),
    "search_memory":            frozenset({"known", "best_friend"}),
}
```

Maps tool name → set of person_types that can invoke it. Single table; grep-able; edit here to adjust policy.

## 109. `_tool_allowed` Fail-Closed

```python
def _tool_allowed(tool_name: str, caller_type: str) -> bool:
    allowed_types = TOOL_PRIVILEGES.get(tool_name)
    if allowed_types is None:
        # Tools not in the table are BLOCKED, not unrestricted. Fail-closed.
        return False
    return caller_type in allowed_types
```

An unregistered tool is blocked. This means adding a new tool requires also adding its privilege row — the startup assertion (§110) enforces.

## 110. Startup Assertion

```python
# In run():
assert set(t["function"]["name"] for t in brain.TOOLS) <= set(TOOL_PRIVILEGES.keys()), (
    "Every tool in brain.TOOLS must have a TOOL_PRIVILEGES row"
)
```

Fires on startup before any model loads. If you add a tool and forget the privilege, the system refuses to start. Makes it structurally impossible to ship an un-gated tool.

## 111. `<<<TOOL ACCESS>>>` Block

See §72.3. Injected into every system prompt so the brain knows upfront what it can call. Before this block (Session 61), the brain would sometimes spend 5 turns retrying a blocked call because it didn't know the block existed.

## 112. History Override Semantics

`HISTORY_OVERRIDE_TOOLS = frozenset({"update_system_name", "update_person_name"})`. When these fire:

1. `stop_audio()` cuts the wrong streaming text.
2. Canonical acknowledgment replaces the LLM text in `history`.
3. TTS speaks the canonical acknowledgment.

Prevents the L1-L4 "infinite repeat" bug from Session 25 where wrong streaming text would poison history and trigger the same tool call next turn.

## 113. Tool Repeat Guard

```python
TOOL_REPEAT_MAX_CONSECUTIVE = 2
```

If the same `(tool_name, args_hash)` has fired 2 consecutive times on the same session, the 3rd attempt aborts with a warning. Prevents infinite loops where the LLM keeps calling the same tool with the same args (Session 25 L3).

---
---

# Part XVII — Observability

## 114. `log_utils` — Single Source of Truth

```python
# core/log_utils.py
def _now_log_ts() -> str:
    raw = _dt.datetime.now().strftime(LOG_TIME_FORMAT)
    if LOG_TIME_FORMAT.endswith("%f") and len(raw) >= 3:
        return raw[:-3]   # trim microseconds to milliseconds
    return raw

def _log_trunc(s: str, limit: int | None = None) -> str:
    effective = LOG_STT_MAX_CHARS if limit is None else limit
    if not effective or len(s) <= effective:
        return s
    return s[:effective] + "…"
```

One place defines log time format. Grep for `_now_log_ts` to find every timestamped log site. No ad-hoc `datetime.now().strftime()` anywhere else (Session 47 Finding K verified).

## 115. Seven Timestamped Categories (now Ten with Observability 2.0)

- `[STT] HH:MM:SS.mmm (Nms) 'text'`
- `[Audio] TTS HH:MM:SS.mmm: 'text'`
- `[Voice] HH:MM:SS.mmm Routing: ...` — includes P3.23 tier diagnostics
- `[Brain] HH:MM:SS.mmm Tool: ...`
- `[Pipeline] Turn start HH:MM:SS.mmm: ...` / `Turn end ...` / `Turn addressed: X (source)`
- `[BrainAgent] HH:MM:SS.mmm Triage: ...` / `Extracted ...`
- `[Intent] tools=[...] classified=X value='Y' conf=0.NN reason=...` — Phase 1 classifier sidecar
- `[Room] New room session: ...` / `Ended: ...` / `Participant added: ...` / `Synthesis complete: ...`
- `[Anti-spoof] summary over last N frames: ...`
- `[ContradictionAgent] {SAFETY_PATTERN_MATCH}: preserve, no replace` — Session 105 Bug N

Non-timestamped logs (e.g., `[Vision] Jagan` heartbeat) are intentionally untimestamped because they fire too frequently and time-stamping them would bury signal.

For the full specification of each category's format, see **Part XXVIII — Observability 2.0**.

## 116. STT Elapsed Ms

`transcribe()` stores elapsed into module-level global `_last_stt_elapsed_ms`. Pipeline reads and re-logs on turn-start line. Single measurement, two log surfaces.

```python
[STT] 01:20:41.223 (635ms) 'Hi there'
[Pipeline] Turn start 01:21:21.296: Jagan — 'Yeah, how about you? What are you thinking?'
```

## 117. Rolling Anti-Spoof Summary

`LOG_ANTISPOOF_SUMMARY=True`, `LOG_ANTISPOOF_SUMMARY_INTERVAL=100`. Every 100 calls, emit:

```
[Anti-spoof] summary over last 100 frames: min=0.93 mean=0.97 max=1.00 rejects=0 thr=0.50
```

Passive drift detection. If camera or lighting degrades over time, mean drops and operator notices without reading every frame's probs.

`LOG_ANTISPOOF_PROBS=False` by default — flip ON for acute debugging.

## 118. Scene Heartbeat Dedup

`[Vision]` heartbeat only prints on change. A stationary scene doesn't spam.

```python
if _vis_report_now != _last_vision_report_str:
    print(f"[Vision] {_vis_report_now}")
    _last_vision_report_str = _vis_report_now
```

Session 38 Issue #6.

---
---

# Part XVIII — Persistence

## 119. `faces.db` Schema

> **Migration model (2026-05-16).** All schema changes to `faces.db` now flow through `core/faces_db_migrations.py` (P0.9, Part XLII). Every historical schema mutation is a 5-tuple entry in the `MIGRATIONS` list with `(version, description, apply_fn, verify_post_fn, verify_present_fn)`. The migration runner consumes the list under `BEGIN IMMEDIATE` with the tightened S65 rollback discipline (Part XLII §282). Inline `ALTER TABLE` calls inside `_init_tables` have been deleted in P0.9 Phase 3 — the structural invariant `TestNoAlterTableOutsideMigrationModules` (Part XLII §284) rejects any future regression. `_init_tables` only does `CREATE TABLE IF NOT EXISTS` for the canonical shape; the migration runner applies the historical evolution on top.

### 119.1 `persons`

```sql
CREATE TABLE persons (
    id               TEXT PRIMARY KEY,
    name             TEXT NOT NULL,
    enrolled_at      REAL NOT NULL,
    last_seen        REAL,
    photo_path       TEXT,
    person_type      TEXT NOT NULL DEFAULT 'known',    -- stranger/known/best_friend/disputed
    preferred_language TEXT DEFAULT 'en'
);
```

### 119.2 `embeddings`

See §37.1. Cross-storage atomicity with FAISS handled by the P0.5 SQL-first ordering + sentinel + boot reconciliation pattern (Part XXXVIII §243-§244).

### 119.3 `voice_embeddings`

See §43.1.

### 119.4 `conversation_log` (with P0.0.7 and Phase 3B columns)

```sql
CREATE TABLE conversation_log (
    id                INTEGER PRIMARY KEY,
    person_id         TEXT NOT NULL,
    role              TEXT NOT NULL,    -- user / assistant
    content           TEXT NOT NULL,
    timestamp         REAL NOT NULL,
    -- Phase 3B (Session 107 / Q3 hybrid history):
    room_session_id   TEXT,              -- room/group context identifier
    audience_ids      TEXT,              -- JSON array of pids allowed to see this turn
    -- Phase 3B addressing (Session 111):
    addressed_to      TEXT,              -- pid the assistant turn was addressed to
    FOREIGN KEY (person_id) REFERENCES persons (id) ON DELETE CASCADE
);
CREATE INDEX conversation_log_person_id_idx ON conversation_log(person_id);
CREATE INDEX idx_conv_log_room ON conversation_log(room_session_id, timestamp DESC);
```

Append-only. Disputed-session turns are skipped (Session 53 Finding B, Part XV §105).

### 119.5 `system_identity`

Singleton table holding the system's name (given by best friend during first-boot).

```sql
CREATE TABLE system_identity (
    singleton INTEGER PRIMARY KEY DEFAULT 1,
    name      TEXT NOT NULL DEFAULT 'Dog',
    updated_at REAL
);
```

### 119.6 `silent_observations`

Faces seen but never engaged (never said the system name).

```sql
CREATE TABLE silent_observations (
    id                INTEGER PRIMARY KEY,
    face_embedding    BLOB NOT NULL,
    first_seen        REAL NOT NULL,
    last_seen         REAL NOT NULL,
    count             INTEGER DEFAULT 1,
    matched_person_id TEXT,              -- NULL unless the observation was later linked
    ...
);
CREATE INDEX idx_silent_obs_last_seen ON silent_observations(last_seen);
```

Retention: `SILENT_OBS_RETENTION_DAYS=45`. Scan window for matching: `SILENT_OBS_SCAN_DAYS=7`.

### 119.7 `visitor_log`

Records stranger sessions for dashboard display.

```sql
CREATE TABLE visitor_log (
    id                INTEGER PRIMARY KEY,
    stranger_id       TEXT,
    first_seen        REAL NOT NULL,
    last_seen         REAL NOT NULL,
    turn_count        INTEGER DEFAULT 0,
    resolved_name     TEXT               -- set if they were later named
);
```

### 119.8 `schema_migrations` (P0.9 — versioned ledger)

```sql
CREATE TABLE schema_migrations (
    version      INTEGER PRIMARY KEY,
    description  TEXT NOT NULL,
    applied_at   REAL NOT NULL,
    is_initial   INTEGER NOT NULL DEFAULT 0    -- 1 = stamped at bootstrap on legacy DB
);
```

The migration ledger. `init_ledger` (Part XLII §278) creates it on a fresh DB; on a legacy DB it self-evolves (idempotent ALTER adding `is_initial` column). `bootstrap_ledger_if_unversioned` walks the `MIGRATIONS` list at boot and stamps each entry whose `verify_present_fn` returns True as `is_initial=1`, then `apply_migrations` runs pending entries in version order.

Boot observability emits one of three lines per DB:
- `[Schema] faces: bootstrap stamped baseline v=1 + N pre-existing migration(s) as is_initial=1 (legacy DB)`
- `[Schema] faces: ledger already versioned`
- `[Schema] faces: apply_migrations ran K pending`

### 119.9 Cascading deletes

Every person-child table uses `ON DELETE CASCADE`. Deleting a person row auto-deletes their embeddings, voice_embeddings, conversation_log. `delete_person` also does knowledge cleanup via `BrainDB.delete_person_data`.

### 119.10 Companion archive DB (`faces_conversation_archive.db`)

Wave 6 Item 21 (Part XLVII §305). Old `conversation_log` rows (`timestamp < now - CONVERSATION_ARCHIVE_AFTER_DAYS * 86400`) are atomically moved to a companion DB at `faces/faces_conversation_archive.db` via `ATTACH DATABASE` + `BEGIN EXCLUSIVE` + cross-DB `INSERT INTO archive.conversation_log SELECT ... → DELETE FROM main.conversation_log WHERE ...`. The companion DB carries the same schema (incl. the room_session_id / audience_ids / addressed_to columns) and the same `idx_conv_log_room` index.

`load_conversation_history` and `search_conversation` open a short-lived connection to the archive DB (separate from the main FaceDB write connection, to avoid ATTACH conflict) and UNION-merge results with the primary DB. The default retention is 30 days; older turns live in the archive forever (or until manual cleanup).

## 120. `brain.db` Schema

> **Migration model (2026-05-16 + 2026-05-18).** Same versioned-ledger pattern as faces.db (§119.8). brain.db's `MIGRATIONS` list lives in `core/brain_db_migrations.py`. The current top version is **12** — P0.0.7's `_m_0012_create_event_log_*` (Part XLIX §318) added the `event_log` table.

### 120.1 `knowledge`

The core knowledge graph table.

```sql
CREATE TABLE knowledge (
    id              INTEGER PRIMARY KEY,
    person_id       TEXT NOT NULL,
    entity          TEXT NOT NULL,
    attribute       TEXT NOT NULL,
    value           TEXT NOT NULL,
    confidence      REAL NOT NULL,
    valid_at        REAL NOT NULL,
    valid_until     REAL,
    invalidated_at  REAL,
    privacy_level   TEXT NOT NULL DEFAULT 'public',    -- Phase 3A.4.5
    embedding       BLOB,                              -- for semantic search
    -- ... plus several Phase 3A / 3B columns: status, source, last_confirmed_at
);
CREATE INDEX idx_knowledge_person_entity ON knowledge(person_id, entity);
CREATE INDEX idx_knowledge_attribute ON knowledge(attribute);
```

The `privacy_level` column was added in Phase 3A.4.5 (Session 95.3-95.6, 4-tier privacy model with `public` / `personal` / `household` / `system_only`). All retrieval paths route through `_visibility_clause` (Part XXV §152).

### 120.2 `prompt_prefs` (PromptPrefAgent)

Per-person communication preferences with semantic dedup. Carries an `embedding` BLOB column (L2-normalised E5 vector) plus a `sessions_seen` counter for auto-confirmation at 3+ sessions.

### 120.3 Knowledge-system support tables

Each agent has its own table — `agent_log`, `object_sightings`, `object_pattern_questions`, `episodes`, `presence_log`, `proactive_nudges`, `watchdog_alerts`, `social_mentions`, `predicate_stats`, `household_facts`, `inter_person_relationships`, `shadow_persons`, `room_summaries`. See Part XIV §84 for the full enumeration.

### 120.4 `schema_migrations` (same shape as §119.8)

Versioned-ledger pattern, identical schema. brain.db's ledger tracks 10 retrofitted historical migrations (v=2 through v=11) plus the P0.0.7 v=12.

### 120.5 `event_log` (P0.0.7, Part XLIX §318)

```sql
CREATE TABLE event_log (
    id                INTEGER PRIMARY KEY,
    ts                REAL NOT NULL,
    session_id        TEXT,
    room_session_id   TEXT,
    event_type        TEXT NOT NULL,                   -- one of the 12 EVENT_TYPES
    schema_version    INTEGER NOT NULL DEFAULT 1,
    payload           TEXT NOT NULL,                   -- JSON-serialised dataclass
    parent_event_id   INTEGER                          -- natural-pair parent linkage
);
CREATE INDEX idx_event_log_ts ON event_log(ts);
CREATE INDEX idx_event_log_session ON event_log(session_id, ts);
CREATE INDEX idx_event_log_room ON event_log(room_session_id, ts);
```

The event-sourcing foundation. Every input crossing the runtime boundary (microphone audio, camera frame, identity claim, routing decision, tool call, tool result, ...) emits a typed event into this table. The 3 indexes are tuned for the replay CLI's most-common filter compositions (chronological / per-session / per-room).

Cross-write atomicity with Kuzu: the brain.db ↔ Kuzu paired-write hardening (P0.X, Part XXXVIII §246) treats brain.db as authoritative and Kuzu as derived state that heals on next `_ensure_graph_sync()`. `event_log` follows the same rule — it's a brain.db-only table, with no Kuzu shadow.

## 121. FAISS Index Layout

`faces/faiss.index` is a serialised `IndexFlatIP` over 512-d vectors. Each face embedding is added with its row index in memory mapped to pid via `self._idx_to_pid: dict[int, str]`.

Rebuilt from DB on:
- Startup.
- `FaceDB.delete_person(pid)` — cleans the mapping + index.
- Factory reset.

Session 38 Issue #2 added `faiss_path` param to `FaceDB` constructor so tests use isolated indexes instead of clobbering the production one.

## 122. Kuzu Graph Schema v2

Directory: `faces/brain_graph/`. Kuzu is embedded — no server. Schema bump triggers wipe + rebuild (§90.3).

Node types:
- `Person` — PK `name`, indexed `face_id`.
- `Entity` — PK `name`. Entities are things people mention (cars, games, objects, other people).

Relationship types:
- `MENTIONED` — `(Person)-[MENTIONED]->(Entity)` with count, last_mentioned, shared flag.
- `RELATES_TO` — `(Person)-[RELATES_TO]->(Person)` with type (friend, parent, sibling, ...).

## 123. `state.json` IPC Format

```json
{
    "status": "ready",
    "pipeline_state": "LISTENING",
    "current_person": {
        "id": "jagan_23ff85",
        "name": "Jagan",
        "type": "best_friend"
    },
    "persons_in_frame": [
        {"id": "jagan_23ff85", "name": "Jagan", "source": "face", "conf": 0.82}
    ],
    "active_sessions": [...],
    "system_name": "Kara",
    "cloud_state": "ONLINE",
    "last_update_ts": 1713600000.12
}
```

Written by `state.py::write_state(...)`. Dashboard polls at ~500ms.

## 124. Atomic Write Pattern

```python
def write_state(**fields):
    tmp = STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(fields))
    tmp.replace(STATE_FILE)   # atomic on POSIX; atomic on Windows if same volume
```

Rename is atomic on both platforms when source and dest are on the same volume. A reader can't see a partially-written file.

Same pattern for `enroll_request.json`, `enroll_result.json`, `reset_request.json`, `reset_result.json`.

---
---

# Part XIX — Config System

## 125. Single Source of Truth Invariant

### 125.1 The rule

Every tunable value in the system lives in `core/config.py`. No magic numbers in decision code.

### 125.2 Why enforced

Historical reason: during the uncle-false-match debug (Session 51), several thresholds were scattered across `pipeline.py`, `brain.py`, and `db.py`. Tuning one without tuning the others caused silent inconsistencies. Consolidating fixed the drift.

### 125.3 Current enforcement (structural, not convention-based)

The "single source of truth" rule used to be convention-only — relied on reviewer discipline + a grep-for-`0\.[0-9]` heuristic. The P0 work since 2026-05-08 made it structural. Every major drift class is now caught by a CI-enforced AST or behavioral invariant:

- **Hardcoded literals in routing thresholds** — Part X §61 — `_effective_switch_threshold` reads from config, not literals; the threshold values import as named constants.
- **`ALTER TABLE` outside the migration modules** — `TestNoAlterTableOutsideMigrationModules` (Part XLII §284) AST-rejects any inline ALTER outside `core/{faces,brain}_db_migrations.py`.
- **Magic numbers in store schemas** — `tests/test_p06_store_schemas.py` pins `EXPECTED_FIELDS` per Store (Part XXXIX §260). Schema drift fails CI.
- **Magic numbers in dispute-state predicates** — `_is_disputed()` is the canonical predicate; raw `"disputed"` comparisons outside the helper are AST-rejected (Part XXXVI §234).
- **Coupling tests** — e.g., `test_bootstrap_budget_exceeds_mature_threshold` fails if `N_INITIAL_VOICE_BOOTSTRAP` is tuned below `VOICE_ACCUM_MATURE_SAMPLE_COUNT`.

The convention layer (reviewer grep) is now backup, not primary. If you bypass `core/config.py` with an inline literal in production code, one of these structural invariants will catch you at PR time.

## 126. Startup Assertions

Run on `run()` entry:

1. **Tool privilege completeness** — every `brain.TOOLS` entry has a `TOOL_PRIVILEGES` row.
2. **Bootstrap arithmetic** — `N_INITIAL_VOICE_BOOTSTRAP > VOICE_ACCUM_MATURE_SAMPLE_COUNT`.
3. **Person type validity** — any `SessionStore.open_session` caller must pass a value in `VALID_PERSON_TYPES`.
4. **Schema migrations applied** — `apply_migrations` runs at boot for every DB; refuses to start if any migration's `verify_post_fn` raises (Part XLII).
5. **Pyannote patch idempotency** — the import-time monkeypatch in `core/voice.py` only fires if torchaudio still has the legacy API; otherwise no-op.

If any fires, the system refuses to start. Impossible to ship a broken config.

## 127. Tuning Workflow

1. Change one value in `core/config.py`.
2. Run `pytest --tb=no -q` (full suite, per the verification-before-completion lesson from Part L §324).
3. If tests pass, do a live test.
4. If the live test reveals the tune was too aggressive/conservative, revert.
5. Never touch a literal in a non-config file as a shortcut. The structural invariants will catch you, but more importantly, the next person editing the file will assume the literal is correct and tune the wrong thing.

---
---

# Part XX — Testing

## 128. ~2216 Tests — Breakdown by Category

| Category | Files | Tests | Focus |
|---|---|---|---|
| Pipeline integration | `test_pipeline.py` and adjacents | ~750 | Session management (post-P0.7 via SessionStore API), routing dispatch, tool dispatch, ROOM block, TURN ARBITRATION, address marker, integration scenarios |
| Knowledge system | `test_brain_agent.py` | ~250 | Knowledge pipeline, each agent, Kuzu graph, visibility clause, privacy classifier, room summaries, safety-flag preservation |
| Reconciler (Part X) | `test_reconciler.py` + `test_p10_reconciler_contract.py` + `test_p10_routing_invariants.py` | ~60 | 22-rule cascade per-rule behavior, C1-C21 contracts, RULES-ordering invariant, EXPECTED_RULES_BY_BAND, Bug-W gap regression, negative-cosine regression |
| Voice/vision channels | `test_voice_channel.py` + `test_vision_channel.py` | ~40 | Pure-function channel contracts, import-boundary AST scans |
| Atomicity (Part XXXVIII) | `test_faiss_sql_atomicity.py` + `test_faiss_atomicity_invariants.py` + `test_kuzu_atomicity_invariants.py` + `test_kuzu_brain_atomicity.py` + `test_kuzu_crash_injection.py` | ~85 | Cross-storage paired-write contracts, sentinel + boot reconciliation, RAISE/SWALLOW/SCHEMA_MIGRATION detectors |
| Store pattern (Part XXXIX) | `test_p06_store_invariants.py` + `test_p06_store_schemas.py` + `test_p06_store_inverse_checks.py` + `test_p06_legacy_global_progress.py` + per-store unit tests | ~150 | Eight stores' contracts, schema pinning, paired-write inverse checks, legacy-global ratchet at cap=0 |
| Typed session state (Part XL) | `test_session_store.py` + `test_session_state_invariants.py` + `test_p072_read_migration_progress.py` | ~70 | Session/SessionSnapshot/VoiceEvidence shape, named transitions, single-writer invariant, no-dual-writes ratchet |
| Tool timeout (Part XLI) | `test_tool_timeout.py` + `test_p08_structural_invariants.py` | ~30 | Per-tool wait_for, cancellation rollback, F1 + F2 structural invariants |
| Schema migrations (Part XLII) | `test_schema_migrations.py` + `test_p09_retrofit_migrations.py` | ~45 | Versioned-ledger pattern, 5-tuple shape, bootstrap walks MIGRATIONS, no-ALTER-outside-modules, no-destructive-ops invariant |
| State race (Part XLIV) | `test_state_race.py` | 4 | Behavioural race + torn-state probe + AST subscript-assign ban + global decl invariant |
| JSON parser (Part XLV) | `test_brain_json_parser_hypothesis.py` | ~33 | Hypothesis property tests (1000 examples/each), regression tests pinned to the two production bugs |
| Health + disk (Part XLVI) | `test_health.py` + `test_disk_monitor.py` | ~20 | HealthSnapshot field coverage, format_health_line, format_health_alerts, idempotent threshold transitions |
| Conversation hygiene (Part XLVII) | `test_hard_delete_invalidated.py` + `test_scene_block_cache.py` + `test_conversation_archive.py` | ~13 | Dream-loop hard-delete, scene-block SHA-256 cache, ATTACH-based atomic archival |
| CI scaffold (Part XLVIII) | `test_dashboard_bind_tripwire.py` + `test_infra_debt_allowlist.py` | ~10 | Localhost binding tripwire, xfail-decorator alignment with allowlist |
| Event log (Part XLIX) | `test_event_log_contract.py` + `test_event_log_invariants.py` + `test_event_log_producer_coverage.py` + `test_event_log_replay.py` | ~80 | 15 contract + 35 parametrized invariant cases + 11 hook coverage + 5 replay smoke tests including anti-spoof field preservation |
| Privacy clause + classifier | privacy tests inside `test_brain_agent.py` and others | ~40 | Visibility clause for 4-tier model, classifier prompt, query_knowledge_for, owner-access (3A.4.6) |
| Layering invariants | `test_layering_invariants.py` + `test_silent_except_invariant.py` + `test_no_raw_disputed_comparisons.py` + `test_no_layering_violations.py` + `test_repeat_guard_invariant.py` + `test_prior_person_type_default.py` + `test_user_text_gate_*.py` | ~100 | AST-based structural invariants enforcing P0.1, P0.2, P0.3, P0.4, P0.13 |
| Vision / audio | `test_vision_v1v4.py` + various audio tests | ~70 | Quality gates V1-V4, anti-spoof, smart-turn, lip tracking, STT, TTS |
| Other | tool executor, shutdown, greetings, eval bench, classifier graph, time anchor, prompt blocks, etc. | ~250 | Miscellaneous unit + integration tests |

**Total: ~2302 passing, 9 xfailed, 4 skipped, 0 failed, 0 errors as of 2026-05-18 post-P0.0.7.X closure.**

**Growth since Session 113.1 (~1083 tests, 2026-04-24).** +1133 tests across ~6 weeks of disciplined P0 hardening + Wave 5/6 + P0.0/P0.0.7. Most growth concentrated in:

- **P0.4** silent-except audit (+14 invariant tests catching the 22 sites + the 4 detector self-tests).
- **P0.5 + P0.X** cross-storage atomicity (+85 across the 5 atomicity test files).
- **P0.6** Store-pattern migration (+150 store unit tests + schema/inverse-check ratchets).
- **P0.7** typed session state migration (+70 SessionStore + invariant tests across the 5 sub-PRs).
- **P0.8** per-tool timeout protection (+30 including F1 + F2 structural invariants).
- **P0.9** schema migrations versioning (+45 retrofit + ratchet tests).
- **P0.10** legacy router deletion + Bug-W (+40 contract + invariant tests; –54 deleted legacy tests; net –15 raw / +40 architectural coverage — see Part XLIII §290 for the math).
- **P0.11** state race (+4 race + AST tests).
- **P0.12** Hypothesis property-based JSON parser hardening (+33).
- **Wave 5 + Wave 6** observability + memory consolidation (+33 across health, disk, hard-delete, scene-cache, archival).
- **P0.0 + P0.0.1 + P0.0.2** tiered CI + S2 tripwire (+10).
- **P0.0.7** event log + replay harness (+80, the largest single sub-PR's test surface).

The growth pattern is dominated by structural invariants rather than feature behaviour. Of the ~1133 new tests since 2026-04-24, roughly two-thirds are AST-based or source-inspection-based — they verify that the production code *continues to satisfy* an architectural property over time, not that a specific feature works on one happy path. This is the empirical realisation of the Part XXII §139 "tests guard every invariant" principle.

## 129. TDD Approach

New features land via TDD when practical:
1. Write a failing test for the behaviour.
2. Implement the minimal code to pass.
3. Refactor as needed; test stays green.

For bug fixes (which are the majority of recent sessions), the pattern is:
1. Write a regression test that reproduces the bug.
2. Fix the code.
3. Verify the test now passes and no others regress.

## 130. Source-Inspection Tests

For behaviours that are hard to test in isolation (because they live inside a 3761-line function or depend on async streaming), we use source-inspection:

```python
def test_stream_truncation_detection_in_source():
    src = Path("pipeline.py").read_text()
    assert "_stream_finish_reason" in src, (
        "Obs 3: pipeline must capture finish_reason from ask_stream"
    )
    assert '_finish in ("length", "content_filter", None)' in src, (
        "Obs 3: pipeline must gate retry on truncation finish_reason"
    )
```

Brittle-looking but surprisingly effective. The test fails if someone silently reverts the post-review Obs 3 fix. Tradeoff: we accept some test-as-documentation rigidity in exchange for catching regressions in code we can't easily call directly.

## 131. Async Test Pattern

`pytest-asyncio` with `asyncio_mode=auto`. Tests are just `async def test_...` functions; pytest awaits them automatically.

```python
@pytest.mark.asyncio  # optional in auto mode, but some tests use it for clarity
async def test_conversation_turn_logs_turns():
    ...
```

Mock patterns:
- `mock_db = MagicMock(spec=FaceDB)` — type-checked mock.
- `monkeypatch.setattr("core.brain.VOICE_ACCUM_MATURE_SAMPLE_COUNT", 7)` — patches the module-local binding (not the config), so `from X import Y` consumers see the patched value.

---
---

# Part XXI — Dashboard

## 132. Next.js Architecture

`Kara-OS-dashboard/` is a Next.js 14 app (App Router). It runs independently of the pipeline process on localhost:3000 (or wherever you configure). Communicates with the pipeline via the JSON file interface in `faces/`.

### 132.1 Routes

- `/` — main dashboard with live state, active sessions, vision heartbeat.
- `/persons` — enrolled people list; per-person drill-down.
- `/persons/[id]` — shows knowledge, conversation history, gallery with audit flags.
- `/visitors` — visitor log.
- `/shadow-persons` — mentioned but not enrolled.
- `/nudges` — pending proactive nudges.

### 132.2 API routes

- `POST /api/enroll` — writes `enroll_request.json`; pipeline picks up and enrolls.
- `POST /api/delete` — runs `delete_person.py` via `execFile` (NOT `exec`; Session 41 H1 security fix) with ID regex validation.
- `GET /api/gallery-audit?person_id=...` — returns audit report JSON.
- `POST /api/reset` — writes `reset_request.json`.

## 133. Real-Time State Read

Polls `faces/state.json` every 500ms via server-side fetch. Data flows to client components via React state.

We don't use WebSockets — polling a local file is fast enough and much simpler.

## 134. Enrollment Flow

The dashboard enrollment route is currently not-yet-integrated with the pipeline's camera — the request is accepted but the pipeline doesn't yet route it. This is on the roadmap.

---
---

# Part XXII — Design Philosophy and Invariants

> **Cross-reference (2026-05-18).** The principles in this Part are the *product-side* design philosophy — how the system relates to the user and how subsystems relate to each other. The *engineering-side* discipline that produces and maintains this code lives in **Part L — Architectural Disciplines (The Named Doctrines)**. The two complement each other: Part XXII describes what we build; Part L describes how we build it well. Each named discipline in Part L (induction-surfaces-invariant-gaps, spec-first review cycle, developer-improves-on-spec, etc.) has a track record of N-for-N instances backing it; the principles in this Part are stated as rules without track records because they're architectural primitives, not validated patterns.

## 135. Brain Decides, Pipeline Enforces

The most important architectural rule. The pipeline is the brain's sensors and actuators — it tells the brain what's happening and carries out what the brain decides. The brain is the one that says "respond", "call this tool", "stay silent."

The pipeline enforces:
- Privilege checks (via TOOL_PRIVILEGES).
- Accumulation gates (Path A/B/C, see §55).
- Anti-spoof gating (§24).
- Session expiry (§51).
- Dispute state transitions (Part XV §102, all via `transition_to_disputed` named transition).
- Per-tool timeout (Part XLI §273).
- Cross-storage atomicity (Part XXXVIII §242).

The brain owns:
- What to say.
- When to invoke tools.
- How to interpret the sensor data.
- Whether to call `report_identity_mismatch`.

This split prevents the pipeline from growing a competing "brain" — every temptation to encode a conversation decision at the pipeline level becomes instead an enhancement to the system prompt.

## 136. No Hardcoded Magic Numbers (Now Structurally Enforced)

Every threshold, every count, every duration lives in `core/config.py`. The exceptions (0, 1, -1, None) are intentionally not called out.

The principle used to be convention-only. As of 2026-05-16 it is structurally enforced via the AST/regex invariants enumerated in §125.3 above. The relevant Parts: Part XLII §284 (no ALTER outside migration modules), Part XXXIX §260 (store schema pinning), Part XXXVI §234 (no raw `"disputed"` comparisons).

## 137. Fail-Closed on Security

Anything resembling a security surface defaults to denial:
- Unknown tool → blocked (Part XVI §109).
- Unknown person_type → handled as stranger (Part XXXVI §235 — `prior_person_type` defaults to `"stranger"` per P0.2).
- Missing anti-spoof model → recognition_update blocked.
- Dispute without clean resolution → force-close.
- Multi-word names not contiguously appearing in user_text → rejected (Part XXXVI §236 — P0.3 contiguous-substring fix).
- Tool execution exceeding budget → cancellation + transaction rollback (Part XLI §274).
- Cross-storage half-writes → degraded mode, no silent divergence (Part XXXVIII §249).

The system errs on "do nothing" rather than "do the risky thing."

## 138. Single Source of Truth for Shared Helpers

- `log_utils._now_log_ts` — one formatter.
- `TOOL_PRIVILEGES` — one privilege table.
- `VOICE_ACCUM_*` — one set of constants used by pipeline gate AND brain verdict.
- `VALID_PERSON_TYPES` — one frozenset asserted everywhere.
- `_is_disputed()` — canonical predicate (Part XV §105; Part XXXVI §234).
- `SessionStore` — only writer of session state (Part XL §263).
- `safe_emit_sync` — only producer-hook swallow path (Part XLIX §314).
- `_visibility_clause` — only privacy-filter SQL composer (Part XXV §152).
- `core/event_log/types.py::_PAYLOAD_CLASSES` — only deserialization dispatch table (Part XLIX §313).

When there are two places something could live, there must be one. The pattern repeats across the codebase because every cycle of consolidation pays back in the next maintenance pass.

## 139. Tests Guard Every Invariant

An invariant that isn't tested is an invariant that will silently break. Every major architectural claim in this document is backed by at least one test. Source-inspection tests (§130) cover the cases that are hard to invoke directly.

The empirical realisation: ~2/3 of the ~1133 tests added between 2026-04-24 and 2026-05-18 are structural invariants (AST scans, source-inspection, paired-write inverse checks). The Part L disciplines that produce these — **induction-surfaces-invariant-gaps** (§322, 7-for-7), **structured-audit-vs-reactive-patching** (§329) — are the meta-rules that ensure every new invariant ships with a corresponding test.

## 140. Privacy at the Data Layer, Phrasing at the Prompt Layer

Two layers enforce cross-person privacy, and neither alone is sufficient:

- **Data layer** — `_visibility_clause` + `query_knowledge_for` decide what rows the brain SEES.
- **Prompt layer** — `<<<CROSS-PERSON PRIVACY>>>` / `<<<CROSS-PERSON PRIVACY (OWNER MODE)>>>` / `<<<VISITOR CONTEXT>>>` / `<<<HONESTY POLICY>>>` decide what the brain SAYS about what it sees.

A brain with restricted context can still phrase its refusal badly ("No one" instead of "Someone I can't share specifics about"). A brain with owner-full-access can still over-share inappropriately. A brain with neither flies blind. Every cross-person retrieval path routes through both layers.

The invariant: **no prompt block tries to enforce row-level privacy, and no SQL clause tries to enforce phrasing.** Each layer does one job.

## 140a. Safety-Flag Preservation — Non-Destructive Plus Append-Only

Non-destructive invalidation is sufficient for most facts. Safety-critical attributes require a stricter rule: append-only, never REPLACE.

Pattern regex lives in `core/config.py::SAFETY_CRITICAL_ATTRIBUTE_PATTERNS`:

```
^expressed_.*_thoughts$
^mentioned_.*$
^reported_.*_abuse$
^has_experienced_crisis$
```

ContradictionAgent's pre-check short-circuits on any match. New disclosures always produce a new row with a new `captured_at`. The matching momentary attribute (e.g. `current_mood`) keeps normal overwrite semantics — the system captures "right now" AND "this ever happened" as separate rows.

The naming of the config (SAFETY_CRITICAL, not APPEND_ONLY or IMMUTABLE) signals intent to future maintainers: removing a regex pattern removes a safety guarantee, not an optimisation.

## 140b. Observability at Every Latency-Critical Boundary

- STT elapsed_ms
- LLM tokens streamed
- Voice routing decision
- Tool dispatch
- Turn-end latency

These are the places where the system can mysteriously feel slow. Having timestamps and durations on each means "why is it laggy today" can be answered from logs alone.

---
---

# Part XXIII — Roadmap and Open Items (Hardware + Long-Range Product)

> **Cross-reference (2026-05-18).** The **engineering** roadmap — the upcoming P0 security / P0 robustness / eval gates / P1.A pipeline decomposition sequence — lives in **Part LI — Upcoming Work and Roadmap** (§331-§340). That's the actively-managed queue and the place to check for "what's next". This Part XXIII covers the hardware-and-long-range items: physical actuators, Jetson deployment, wake-word power management, the Q3 history redesign — items that depend on either physical-world milestones or on broader architectural decisions that aren't blocking the current sprint.

## 141. ReSpeaker Barge-In

The 4-mic ReSpeaker array will give us:
- Beamforming (directional mic).
- Hardware echo cancellation.
- Stronger VAD signal-to-noise.

With these, we can re-enable `_vad_interrupt_listener` that was removed in Session 2 due to self-interrupt issues on the laptop mic. The pipeline code has a comment at the removal site: "Do NOT re-add `_vad_interrupt_listener` until ReSpeaker hardware arrives."

## 142. Jetson Deployment Checklist

When the Jetson arrives:

1. Clone repo; create venv.
2. `pip install faiss-gpu` instead of faiss-cpu.
3. Verify buffalo_l auto-downloads.
4. CUDA 12.x + cuDNN 9.x matching onnxruntime-gpu version.
5. V4L2 backend: automatic via `sys.platform != "win32"` check.
6. `loop.add_signal_handler(SIGTERM, ...)` path becomes active.
7. Smoke test: first-boot flow, multi-person routing, dispute.
8. Export Whisper + AdaFace + RetinaFace to TensorRT for ~2x latency reduction.
9. systemd service for auto-start on boot.
10. Physical robot integration via `robot.py` (§144).
11. **CI on Jetson** — slow-test workflow (`.github/workflows/slow.yml`) must be runnable from a self-hosted Jetson runner. Currently both CI workflows run on `ubuntu-latest`. The model-heavy tests aren't representative of Jetson-side behavior. Open.
12. **Power management for the always-on listening loop** — see §143.

## 143. openWakeWord Push-to-Talk

Current design: the pipeline is always listening. Mic is always on. This is fine on mains-powered dev but bad on battery.

openWakeWord would let us gate everything on a wake word — the system is in low-power listening until someone says "Kara" (or whatever the wake word is), then jumps into the full pipeline.

Tradeoff: wake-word false-rejects feel worse than always-on. Decision pending user testing.

## 144. `robot.py` Hardware Abstraction

When physical actuators arrive (head pan/tilt, tail wag, LED eyes), we need a clean boundary between "pipeline thinks" and "robot moves." The plan is a `core/robot.py` module with methods like `look_at(azimuth, elevation)`, `express(mood)`, `tail_wag(intensity)`.

The pipeline calls these at semantic boundaries; the robot module translates to servo commands. Mocks during dev so nothing breaks before hardware lands.

The decomposition will benefit from P1.A (Part LI §336) — once `pipeline.py` is split into ~30 focused modules, `robot.py` is a natural addition that consumes events from the event log (Part XLIX) and emits actuator commands, without needing to be threaded through a 10000-line monolithic pipeline.

## 145. Q3 — History Architecture Redesign

**Status: schema-side landed in Session 107 / P0.0.7; retrieval-side pending RoomOrchestrator.**

Pre-Phase-3B, `conversation_log` was per-person. A turn in a multi-person scene belonged to the speaker but was overheard by everyone. The Phase 3B work (Part XXVI) introduced room awareness via the `<<<ROOM>>>` block, but the underlying schema was still per-person.

Phase 3A.6 / Session 107 added two columns to `conversation_log`:
- `room_session_id` — the room context the turn happened in.
- `audience_ids` — JSON array of pids allowed to see the turn.

Plus a new index `idx_conv_log_room` for room-scoped queries.

Session 111 added a third column:
- `addressed_to` — pid the assistant turn was addressed to (for `[addressing:X]` marker disambiguation).

**Schema is in place.** Retrieval-side wiring lands when RoomOrchestrator ships (currently deferred under Phase 3B follow-up). At that point, `<<<SHARED CONTEXT>>>` block will pull recent shared turns from `conversation_log` filtered by `room_session_id` AND privacy via the existing `_visibility_clause` (Part XXV §152). The Kuzu v3 schema bump (Part LI §338) lands alongside.

The deferral is intentional. The schema is forward-compatible; existing per-person retrieval paths continue to work. RoomOrchestrator can land in a separate sub-PR cycle without touching the data layer.

---
---

# Part XXIV — Appendices

## 146. Glossary

- **AdaFace** — The face embedding model we use. IR101 backbone, 512-d output.
- **Anti-spoof** — MiniFASNet ensemble that rejects photo/screen-replay attacks.
- **Bootstrap credits** — Path C of voice accumulation; free accumulations granted at engagement gate.
- **BrainDB** — SQLite database at `faces/brain.db` holding structured knowledge.
- **BrainOrchestrator** — Coordinator that runs all 15+ knowledge agents.
- **Centroid gate** — Anti-poisoning check: new embedding must be close to gallery centroid.
- **Companion (vs Assistant)** — The design philosophy that prioritises presence over task completion.
- **Dispute** — A session state where speaker claim contradicts sensor evidence.
- **Dream** — Idle-triggered knowledge consolidation.
- **ECAPA-TDNN** — Speaker embedding model from SpeechBrain.
- **Engagement gate** — Strangers must say the system name before the system responds.
- **Evidence dict** — The `identity_evidence` dict on each session.
- **FaceDB** — The `FaceDB` class in `core/db.py`; SQLite + FAISS.
- **FAISS** — Facebook AI Similarity Search; exact and approximate nearest-neighbour library.
- **First-boot flow** — The dialogue flow for enrolling the best friend on a fresh install.
- **Function calling** — LLM capability to emit structured tool call requests.
- **KAIROS** — Proactive wake mechanism that pokes the brain during user silence.
- **Kokoro** — Primary TTS model; ONNX runtime.
- **Kuzu** — Embedded property graph database.
- **MiniFASNet** — Anti-spoof model architecture (vendored from minivision-ai).
- **Ollama** — Local LLM server used as fallback when Together.ai is unreachable.
- **Path A / B / C** — Three paths through which voice accumulation can be granted.
- **person_type** — One of {stranger, known, best_friend, disputed}.
- **PipelineState** — Enum of {WATCHING, LISTENING, THINKING, SPEAKING, ENROLLING}.
- **Progressive enrollment** — Enrolling a stranger who just passed the engagement gate.
- **RetinaFace** — Face detector from InsightFace buffalo_l pack.
- **RetroScan** — Post-contradiction scan for stale neighbour facts.
- **Session** — A live interaction with one person; `_active_sessions[pid]`.
- **Silent observation** — A face seen but never engaged; stored separately from persons.
- **Smart-Turn** — Neural end-of-turn classifier; ~8MB ONNX.
- **SORT** — Simple Online and Realtime Tracking; Kalman + Hungarian for track persistence.
- **system_name** — The robot's name, given by the best friend. Default "Dog".
- **TOOL_PRIVILEGES** — Fail-closed table mapping tool name → allowed person_types.
- **Together.ai** — Cloud LLM provider for primary chat + extraction + embeddings.
- **TTFT** — Time To First Token, a streaming LLM latency metric.
- **V1 / V2 / V3 / V4** — Face quality gates: size/blur, yaw, temporal pool, adaptive threshold.

## 147. Full Config Constant Table

This table lists every tunable constant in `core/config.py` with its current value and purpose.

| Constant | Value | Purpose |
|---|---|---|
| `RECOGNITION_THRESHOLD` | 0.28 | Face cosine threshold for "known" verdict |
| `DETECTION_CONFIDENCE` | 0.50 | RetinaFace min confidence |
| `EMBEDDING_DIM` | 512 | AdaFace output dim |
| `VOICE_RECOGNITION_THRESHOLD` | 0.25 | Voice cosine EER threshold |
| `VOICE_SPEAKER_SWITCH_THRESHOLD` | 0.50 | Min to switch session to a different voice |
| `MAX_VOICE_EMBEDDINGS` | 20 | Per-person cap |
| `VOICE_EMBEDDING_DIM` | 192 | ECAPA-TDNN output dim |
| `VOICE_DIVERSITY_THRESHOLD` | 0.85 | Skip too-similar voice sample |
| `N_INITIAL_VOICE` | 5 | First N bypass diversity |
| `DIARIZE_WINDOW_SECS` | 0.50 | Diarization window |
| `DIARIZE_HOP_SECS` | 0.25 | Diarization hop |
| `DIARIZE_CHANGE_THRESH` | 0.70 | Boundary cosine threshold |
| `DIARIZE_MIN_SECS` | 2.00 | Min utterance length to diarize |
| `SELF_UPDATE_THRESHOLD` | 0.45 | Min cosine for recognition_update |
| `SELF_UPDATE_COOLDOWN` | 30 | Seconds between self-updates per person |
| `SELF_UPDATE_CENTROID_MIN` | 0.55 | Centroid gate for recognition_update |
| `MAX_EMBEDDINGS` | 50 | Per-person face cap |
| `FACE_DIVERSITY_THRESHOLD` | 0.92 | Skip too-similar face sample |
| `FACE_QUALITY_PRESENCE` | 0.05 | Face detectably present |
| `FACE_QUALITY_RECOGNITION` | 0.20 | Recognition viable |
| `FACE_QUALITY_ENROLLMENT` | 0.50 | Gate for enrollment write |
| `FACE_QUALITY_SELF_UPDATE` | 0.70 | Gate for self-update write |
| `N_INITIAL_FACE` | 5 | First N face embeddings bypass diversity |
| `VALID_PERSON_TYPES` | frozenset(...) | Asserted at every write |
| `VOICE_ROUTING_MIDRANGE_SWITCH_MIN` | 0.30 | Priority 2 floor |
| `VOICE_ROUTING_SELF_MATCH_FLOOR` | 0.30 | Priority 3 absolute floor |
| `VOICE_ROUTING_SELF_MATCH_OFFSCREEN` | 0.45 | Priority 3 offscreen floor |
| `N_INITIAL_VOICE_BOOTSTRAP` | 6 | Path C credits at engagement |
| `VOICE_ACCUM_FACE_WITNESS_MIN_CONF` | 0.45 | Path A face conf floor |
| `VOICE_ACCUM_FACE_WITNESS_MAX_AGE_SEC` | 10.0 | Path A face freshness |
| `VOICE_ACCUM_VOICE_SELF_MATCH_MIN` | 0.45 | Path B voice floor |
| `VOICE_ACCUM_MATURE_SAMPLE_COUNT` | 5 | Path B maturity bar |
| `IDENTITY_EVIDENCE_BLOCK_ENABLED` | True | Inject `<<<IDENTITY EVIDENCE>>>` |
| `TOOL_PRIVILEGES` | {...} | Privilege table |
| `GREET_COOLDOWN` | 300 | Seconds between greetings |
| `FACE_LOSS_GRACE` | 10 | Face-session expiry |
| `VOICE_SESSION_TIMEOUT` | 30 | Voice-session expiry |
| `VAD_SWITCH` | False | RMS vs Silero |
| `VAD_THRESHOLD` | 0.5 | Silero cutoff |
| `RMS_THRESHOLD` | 0.01 | RMS speech cutoff |
| `SILENCE_DURATION` | 1.5 | Hard end-of-turn fallback |
| `FILLER_ENABLED` | False | "Hmm..." fillers |
| `MIC_SAMPLE_RATE` | 16000 | |
| `SMART_TURN_SILENCE` | 0.5 | Trigger silence for Smart-Turn |
| `SMART_TURN_THRESHOLD` | 0.80 | Turn-complete confidence |
| `SMART_TURN_ADDENDUM` | 0.5 | Grace window |
| `LIP_MAX_EXTENSION` | 2.0 | Max lip-tracking extension |
| `ADDENDUM_ONSET_WINDOW` | 0.10 | Re-listen window after turn |
| `SPEAKER_LANGUAGES` | ["en"] | Whisper auto-detect candidates |
| `OLLAMA_MODEL` | qwen2.5:7b | Local fallback |
| `CHAT_MODEL` | Llama-3.3-70B-Turbo | Primary LLM |
| `EXTRACT_MODEL` | same | Background extraction |
| `EMBED_MODEL` | multilingual-e5-large-instruct | Semantic embeddings |
| `EMBED_MAX_RETRIES` | 2 | |
| `EXTRACT_MAX_RETRIES` | 2 | |
| `CLOUD_OFFLINE_TIMEOUT` | 120 | Seconds to OFFLINE |
| `CLOUD_RETRY_INTERVAL` | 30 | Retry ping interval |
| `STRANGER_REQUIRE_SYSTEM_NAME` | True | Engagement gate |
| `TAVILY_SEARCH_DEPTH` | advanced | |
| `TAVILY_MAX_RESULTS` | 5 | |
| `SEARCH_CACHE_TTL_SECS` | 300 | |
| `SEARCH_MAX_PER_TURN` | 2 | |
| `ANTISPOOFING_ENABLED` | True | |
| `ANTISPOOFING_THRESHOLD` | 0.5 | live_prob floor |
| `LOG_ANTISPOOF_PROBS` | False | Per-frame debug |
| `LOG_ANTISPOOF_SUMMARY` | True | Rolling summary |
| `LOG_ANTISPOOF_SUMMARY_INTERVAL` | 100 | Summary frequency |
| `LOG_TIME_FORMAT` | `%H:%M:%S.%f` | |
| `LOG_LATENCY_ENABLED` | True | |
| `LOG_STT_MAX_CHARS` | 0 | 0 = no truncation |
| `AUTOCOMPACT_KEEP_TURNS` | 15 | |
| `MICRO_CHAR_LIMIT` | 2000 | |
| `TOKEN_CHARS_PER_TOKEN` | 3.5 | |
| `TOKEN_COMPACT_THRESHOLD` | 50000 | |
| `TOKEN_WARN_THRESHOLD` | 90000 | |
| `TOKEN_HARD_LIMIT` | 100000 | |
| `HOUSEHOLD_DISPUTE_SETTLE_SESSIONS` | 2 | |
| `DEFAULT_SYSTEM_NAME` | Dog | |
| `BRAIN_AGENT_POLL_INTERVAL` | 2.0 | |
| `BRAIN_AGENT_CONTEXT_TURNS` | 6 | |
| `BRAIN_AGENT_MIN_WORDS` | 4 | |
| `PREF_AUTO_CONFIRM_THRESHOLD` | 3 | |
| `PREF_ANALYSIS_TURNS` | 40 | |
| `SCHEMA_NORM_TRIGGER` | 30 | |
| `SCHEMA_NORM_THRESHOLD` | 0.97 | |
| `SCHEMA_NORM_DISTINCT_FAMILIES` | (...) | |
| `SCHEMA_NORM_AMBIGUOUS` | 0.72 | |
| `CONFIDENCE_BOOST` | 0.08 | |
| `INTRA_PREF_TURN` | 15 | |
| `INTRA_PREF_TURNS_LIMIT` | 6 | |
| `FRICTION_MIN_CONFIDENCE` | 0.70 | |
| `PREDICATE_VOLATILITY_THRESHOLD` | 3 | |
| `PREDICATE_CONFIDENCE_CAP` | 0.75 | |
| `PRIVATE_ATTRIBUTES` | {...} | |
| `SCENE_STALE_SECS` | 5.0 | |
| `VOICE_ROUTING_FACE_STALE_SECS` | 2.0 | |
| `SCENE_BLOCK_ENABLED` | True | |
| `SCENE_VOICE_STALE` | 30.0 | |
| `CONVERSATION_HISTORY_LIMIT` | 100 | |
| `KNOWLEDGE_MAX_ROWS` | 2000 | |
| `PRESENCE_MAX_ROWS` | 1000 | |
| `EPISODE_MAX_ROWS` | 500 | |
| `SOCIAL_MENTIONS_MAX_ROWS` | 500 | |
| `WATCHDOG_MAX_AGE_DAYS` | 30 | |
| `AGENT_LOG_MAX_AGE_DAYS` | 30 | |
| `AGENT_LOG_MAX_ROWS` | 50000 | |
| `PATTERN_Q_MAX_AGE_DAYS` | 7 | |
| `DREAM_IDLE_MINUTES` | 5 | |
| `DREAM_COOLDOWN` | 3600 | |
| `DREAM_MAX_INTERVAL` | 10800 | |
| `STRANGER_TTL_DAYS` | 7 | |
| `STRANGER_VOICE_TTL_DAYS` | 3 | |
| `DISPUTE_MAX_DURATION` | 180 | |
| `DISPUTE_RENAME_BLOCK_THRESHOLD` | 3 | |
| `DREAM_PRUNE_FLOOR` | 0.15 | |
| `DREAM_DECAY_WRITE_THRESHOLD` | 0.005 | |
| `DECAY_LAMBDA` | 0.002 | |
| `MAX_RETROACTIVE_FACTS` | 5 | |
| `RETRO_STALE_PENALTY` | 0.15 | |
| `GRAPH_SCHEMA_VERSION` | 2 | |
| `EMOTION_ENABLED` | True | |
| `EMOTION_WINDOW` | 5 | |
| `EMOTION_MIN_SCORE` | 0.40 | |
| `EMOTION_FACT_VALIDITY_HOURS` | 4.0 | |
| `EMOTION_WINDOW_TTL_SECS` | 90 | |
| `SORT_DETECT_EVERY` | 5 | |
| `SORT_MAX_AGE` | 30 | |
| `SORT_MIN_HITS` | 2 | |
| `EMBED_DIM` | 1024 | |
| `EMBED_TOP_K` | 10 | |
| `EMBED_MIN_CONFIDENCE` | 0.60 | |
| `KAIROS_SILENCE_THRESHOLD` | 30.0 | |
| `KAIROS_COOLDOWN` | 120.0 | |
| `PATTERN_MIN_SIGHTINGS` | 30 | |
| `PATTERN_COOLDOWN` | 3600 | |
| `PATTERN_MAX_QUESTIONS` | 5 | |
| `PATTERN_ANALYSIS_DAYS` | 7 | |
| `PATTERN_MIN_CONF` | 0.70 | |
| `VISION_YOLO_ENABLED` | False | |
| `VISION_YOLO_MODEL` | yolo11s.pt | |
| `VISION_DETECT_EVERY` | 15 | |
| `VISION_DETECT_CONF` | 0.40 | |
| `VISION_SIGHTING_GAP` | 60 | |
| `VISION_MAX_SIGHTINGS` | 5000 | |
| `BRIEFING_MIN_ABSENCE` | 1800 | |
| `INSIGHT_MIN_TURNS` | 3 | |
| `INSIGHT_MAX_TOKENS` | 300 | |
| `EPISODE_TOPIC_MATCH_DAYS` | 30 | |
| `MIN_PRESENCE_SESSIONS` | 5 | |
| `ROUTINE_STD_THRESHOLD` | 2.0 | |
| `PRESENCE_DEVIATION_HOURS` | 2.0 | |
| `NUDGE_MIN_CONFIDENCE` | 0.40 | |
| `NUDGE_FUZZY_MATCH_RATIO` | 80 | |
| `NUDGE_EXPIRY_HOURS` | 72.0 | |
| `CROSS_PERSON_MAX_NUDGES` | 3 | |
| `WATCHDOG_INTERVAL` | 60.0 | |
| `WATCHDOG_SILENT_OBS_SPIKE` | 5 | |
| `WATCHDOG_UNUSUAL_HOUR_START` | 0 | |
| `WATCHDOG_UNUSUAL_HOUR_END` | 5 | |
| `IDENTITY_SOFT_THRESHOLD` | 0.35 | |
| `IDENTITY_ASK_THRESHOLD` | 0.65 | |
| `IDENTITY_AUTO_THRESHOLD` | 0.85 | |
| `SILENT_OBS_SIMILARITY` | 0.82 | |
| `SILENT_OBS_RETENTION_DAYS` | 45 | |
| `SILENT_OBS_SCAN_DAYS` | 7 | |
| `HISTORY_OVERRIDE_TOOLS` | {update_person_name, update_system_name} | |
| `TOOL_REPEAT_MAX_CONSECUTIVE` | 2 | |
| `PRIVACY_LEVELS` | frozenset{public, personal, household, system_only} | Phase 3A closed-world tier enum |
| `PRIVACY_LEVEL_DEFAULT` | "personal" | Fail-closed default for novel attributes |
| `PRIVACY_LEVEL_STATIC_MAP` | dict (22 entries) | Fast-path attribute → tier; bypasses LLM classifier |
| `PRIVACY_CLASSIFIER_TIMEOUT_SECS` | 5.0 | LLM fallback timeout (matches `_classify_intent`) |
| `PRIVACY_CLASSIFIER_MAX_TOKENS` | 150 | Tight JSON envelope budget |
| `SAFETY_CRITICAL_ATTRIBUTE_PATTERNS` | frozenset of regex | `expressed_*_thoughts`, `mentioned_*`, `reported_*_abuse`, `has_experienced_crisis` — append-only |
| `SHADOW_NAME_BLOCKLIST` | frozenset (~36 entries) | Prevents HouseholdAgent from creating shadow nodes for pronouns / relationship roles |
| `CROSS_PERSON_PRIVACY_BLOCK_ENABLED` | True | Gate for the refusal + owner variants |
| `VISITOR_CONTEXT_BLOCK_ENABLED` | True | Gate for `<<<VISITOR CONTEXT>>>` (fires on `[visitor_id:` marker in prompt_addendum) |
| `STRANGER_IDENTITY_BLOCK_ENABLED` | True | Gate for `<<<STRANGER IDENTITY>>>` promotion nudge |
| `STRANGER_IDENTITY_BLOCK_MIN_TURNS` | 2 | Min user turns before nudge fires |
| `HONESTY_POLICY_BLOCK_ENABLED` | True | Gate for `<<<HONESTY POLICY>>>` |
| `HEDGED_NAMING_CONTRACT_ENABLED` | True | Gate for `<<<HEDGED NAMING CONTRACT>>>` |
| `INTENT_CONTRACT_BLOCK_ENABLED` | False | Gate for the deprecated `<<<STRUCTURED OUTPUT CONTRACT>>>` (off as of Session 79) |
| `INTENT_LABELS` | frozenset of 12 strings | Phase 1 classifier output enum |
| `TOOL_INTENT_MAP` | dict | Tool name → (required_intent, arg_key) for 4 mutation tools (search_web removed S79) |
| `INTENT_CONFIDENCE_MIN` | 0.75 | General classifier gate |
| `INTENT_SHUTDOWN_CONF_MIN` | 0.80 | Higher-blast-radius gate for shutdown |
| `INTENT_CLASSIFIER_TIMEOUT_SECS` | 10.0 | Bumped from 5 → 8 → 10 across sessions 77, 79 |
| `INTENT_CLASSIFIER_MAX_TOKENS` | 500 | Bumped from 300 in S78 |
| `INTENT_FALLBACK_TO_REGEX` | True | Dual-gate (classifier primary, regex safety net). Flip at P1.17 |
| `INTENT_SHADOW_MODE_ENABLED` | True | Whether classifier fires at all |
| `ADDRESS_DECISION_BLOCK_ENABLED` | True | Gate for multi-person `[addressing:X]` marker arbitration |
| `BATCH_GREETING_ENABLED` | True | LLM-decided greeting order for simultaneous arrivals |
| `BATCH_GREETING_MIN_PEOPLE` | 2 | Min people to trigger LLM call |
| `BATCH_GREETING_LLM_TIMEOUT_SECS` | 1.0 | Fallback to detection order on timeout |
| `ROOM_BLOCK_ENABLED` | True | Gate for `<<<ROOM>>>` block |
| `ROOM_BLOCK_TURN_CAP` | 10 | Max interleaved turns rendered |
| `TURN_ARBITRATION_ENABLED` | True | Gate for TURN ARBITRATION sub-block |
| `ROOM_STAY_SILENT_ON_USER_TO_USER` | True | Classifier-driven silent skip for user-to-user addressing |
| `SEARCH_ROOM_MEMORY_ENABLED` | True | Master gate for `search_room_memory` tool |
| `SEARCH_ROOM_MEMORY_MIN_TURNS` | 5 | Below this, tool returns hint |
| `ROOM_END_SYNTHESIS_ENABLED` | True | Master rollback for `synthesize_room` |
| `ROOM_SUMMARY_LLM_TIMEOUT_SECS` | 3.0 | Fallback to topic-only summary on timeout |
| `ROOM_RECENT_CONTEXT_HOURS` | 24 | Lookback window for `<<<RECENT ROOMS>>>` |
| `SCENE_VISITOR_RECENCY_SECS` | 600.0 | Session 108 SCENE "Recent visitors" window |
| `DIARIZATION_BACKEND` | "pyannote" | "pyannote" or "ecapa_valley" fallback |
| `DIARIZATION_FALLBACK_ON_ERROR` | True | Fallback enabled |
| `DIARIZE_MIN_SEGMENT_SECS` | 0.5 | Drop segments below this (ECAPA noise floor) |
| `DIARIZE_MIN_EMBED_SECS` | 1.0 | Min embedding window for attribution |
| `VOICE_ROUTING_SHORT_UTT_MISMATCH_ENABLED` | True | P3.23 tier 1 hard mismatch drop |
| `VOICE_ROUTING_SHORT_UTT_FLOOR` | 0.20 | Hard mismatch threshold |
| `VOICE_ROUTING_SHORT_UTT_AMBIGUOUS` | 0.40 | Ambiguous zone threshold (tier 2) |
| `VOICE_ROUTING_MIN_UTTERANCE_SECS` | 1.0 | Short-utterance threshold |
| `VOICE_ROUTING_MIN_AUDIO_FOR_SCORE` | 0.5 | Below this, skip directional check |
| `VOICE_ROUTING_FACE_ASSIST_MIN` | 0.42 | Priority 2 face+voice shortcut floor |
| `VOICE_BOOTSTRAP_REPLENISH_ENABLED` | True | Bootstrap credit replenishment on engaged strangers |
| `VOICE_MAX_BOOTSTRAP_CREDITS` | 10 | Cap on replenished credits |
| `DISPUTE_AUTO_CLEAR_VOICE_MIN` | 0.70 | Face-corroborated auto-clear floor |
| `DISPUTE_AUTO_CLEAR_VOICE_SOLO_MIN` | 0.85 | Voice-solo auto-clear floor |
| `DISPUTE_AUTO_CLEAR_CONSECUTIVE_TURNS` | 3 | Min consecutive high-voice turns for clear |
| `LOG_ANTISPOOF_PROBS` | False | Per-frame probs dump |
| `LOG_ANTISPOOF_SUMMARY` | True | Rolling summary every N frames |
| `LOG_ANTISPOOF_SUMMARY_INTERVAL` | 100 | Summary cadence |
| `LOG_LATENCY_ENABLED` | True | Emit "(Nms)" elapsed tags |
| `LOG_STT_MAX_CHARS` | 0 | 0 = no truncation |
| `SEARCH_QUERY_MIN_CHARS` | 3 | Server-side Bug R guard on `search_web` empty query |
| `SEARCH_WEB_LIVE_DATA_PATTERNS` | tuple of regex | Allow patterns for live-data gate (Bug T) |
| `SEARCH_WEB_BLOCK_PATTERNS` | tuple of regex | Block patterns (personal / opinion / closers) |

## 148. Full Tool Schema Reference

### 148.1 update_person_name

```json
{
    "type": "function",
    "function": {
        "name": "update_person_name",
        "description": "Call when the speaker tells you their name or corrects a mis-attribution. For a stranger this promotes them to known. For a known speaker, this flips the session to disputed pending verification — it does NOT rename.",
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"]
        }
    }
}
```

### 148.2 update_system_name

```json
{
    "type": "function",
    "function": {
        "name": "update_system_name",
        "description": "Call when the best friend gives you a name or renames you. Only callable by best_friend.",
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"]
        }
    }
}
```

### 148.3 search_web

```json
{
    "type": "function",
    "function": {
        "name": "search_web",
        "description": "Call for real-time information (news, facts, current events) that you don't know from training. Do NOT call for personal/memory questions — use search_memory for those. Do NOT call for self-awareness questions ('what is your name', 'who am i'). Results are cached for 5 minutes per query.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"]
        }
    }
}
```

### 148.4 shutdown

```json
{
    "type": "function",
    "function": {
        "name": "shutdown",
        "description": "Call when the best friend asks you to shut down or go to sleep. Only callable by best_friend.",
        "parameters": {"type": "object", "properties": {}}
    }
}
```

### 148.5 search_memory

```json
{
    "type": "function",
    "function": {
        "name": "search_memory",
        "description": "Call to retrieve stored facts about the current speaker or the system. Use scope='self' for their own memories, scope='system' for shared household knowledge.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "scope": {"type": "string", "enum": ["self", "system"]}
            },
            "required": ["query"]
        }
    }
}
```

### 148.6 report_identity_mismatch

```json
{
    "type": "function",
    "function": {
        "name": "report_identity_mismatch",
        "description": "ONLY call when the CURRENT SPEAKER (the person talking to you right now) explicitly denies being the person the sensor identified them as. DO NOT call for questions about prior conversation activity (e.g. 'Who were you talking to?'). TRIGGER CHECKLIST: (1) current speaker talking about themselves, (2) denying sensor's identification, (3) contradicted at least twice, (4) no replacement name given. If user's utterance contains 'who', 'what', 'did' — almost certainly NOT an identity mismatch.",
        "parameters": {
            "type": "object",
            "properties": {"reason": {"type": "string"}},
            "required": ["reason"]
        }
    }
}
```

### 148.7 search_room_memory (Phase 3B.5, Session 113)

```json
{
    "type": "function",
    "function": {
        "name": "search_room_memory",
        "description": "Search the CURRENT ROOM SESSION's conversation log (turns from ALL speakers who participated, interleaved chronologically). Use for cross-speaker room-wide questions ('what have we talked about tonight?', 'when did Lexi mention her interview?'). DO NOT call for prior-session questions (use search_memory), anything said in the last 2-3 turns (already in context), or single-person history (use search_memory). Returns empty+hint on rooms <5 turns.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"]
        }
    }
}
```

## 149. Session History Timeline

This table summarises the major sessions that shaped the system. For the complete list see `CLAUDE.md` § Completed Sessions.

| Session | Date | Theme |
|---|---|---|
| 1-7 | early | Foundations: FAISS, WAL, memory system, voice recognition |
| 8-11 | 2026-03-23-25 | Function calling rewrite, CloudState, brain-decides architecture |
| 12-17 | late March | Brain agent phases: extraction, graph, embeddings, schema norm, spatial vision |
| 18-20 | April 7 | Test coverage, Piper TTS, anti-spoof v1, memory pruning |
| 21-22 | April 10 | Multi-person sessions, household agent, anti-spoof gates, identity promotion |
| 23-24 | April 11 | G5a visitor alert, B1-B7 DB robustness, I2 targeted gallery update |
| 25-27 | April 12 | L1-L5 tool calling reliability, per-turn speaker routing, unrecognized face tracking |
| 28-38 | April 12-13 | Issue A-B, tool tightening, date injection, TTS hallucination filter, bug fixes |
| 39-41 | April 14-17 | Multi-person architecture, diarization, emotion, ConversationRoutingAgent, G4 phonetic |
| 42-44 | April 18 | Issues #13-29, privilege table, identity evidence, observability, delete_person |
| 45-46 | April 19 | Findings A-F, kairos scene, cleanup, verify_live wrapper |
| 47-50 | April 19 | Findings G-M + NEW-1..5, Priority 3.5, hydration, collision guards |
| 51 | April 19 | Uncle-false-match fixes: gallery poisoning, dispute state machine, schema families |
| 52 | April 19 | Anti-spoofing MiniFASNet vendored |
| 53-57 | April 19 | Dispute hardening, Findings G-M, dispute-rename burst watchdog |
| 58 | April 19 | Kuzu self-heal |
| 59-60 | April 19 | Anti-spoof preprocessing bug, Problem B best_friend downgrade, STT truncation |
| 61 | April 20 | Robustness refactor Steps 0-3: anti-spoof summary, log_utils, TOOL_PRIVILEGES, identity evidence |
| 62 | April 20 | Reviewer findings: verdict constants tracked config, set_language removed, pipeline literal |
| 63 | April 20 | Routing thresholds → config |
| 64 | April 20 | Bugs A-C + 2/3/5/6 from live run: voice accumulation, source tagging, dispute resilience |
| 65 | April 20 | Post-review hardening: Obs 1 cache fallback, Obs 2 in_transaction, Obs 3 finish_reason, Obs 4 voice-expiry log |
| 66 | April 20 | Obs 1-4 hardening: `_safe_commit`, voice gallery DB fallback, finish_reason plumbing, voice-session observability |
| 67 | April 21 | Phase 1 bugs F, O, I + BOOTSTRAP=20 — short-utterance floor, face-assist floor, accumulation ordering |
| 68 | April 21 | Phase 2 narrative correctness: confabulation prevention (BriefingAgent + HONESTY POLICY), meta-commentary leak, tail-retry split |
| 69 | April 21 | Phase 3 knowledge hygiene: PromptPref dedup + blacklist, unified `_call_llm_chat` retry helper |
| 70–74 | April 21-22 | Tool-dispatch hygiene: R/P/Q/S/T/V/W/X/Y/G/D bugs; server-side user-text gates; `_is_disputed` helper; dispute state machine hardening; `DISPUTE_MAX_DURATION`, `DISPUTE_AUTO_CLEAR_*` |
| 75 | April 22 | **VISION_ROADMAP Phase 1.1+1.2** — `INTENT_LABELS`, `TOOL_INTENT_MAP`, `<<<STRUCTURED OUTPUT CONTRACT>>>` block (observation only) |
| 76 | April 22 | **Phase 1.3** — shadow classifier: `_classify_intent` + `_parse_intent_sidecar` + `<<<HEDGED NAMING CONTRACT>>>` |
| 77 | April 22 | Ollama rename-retry hedge, classifier timeout 5s → 8s |
| 78 | April 22 | Short-utterance floor regression root fix, `_strip_im_contraction` normalization, max_tokens 300 → 500 |
| 79 | April 22 | `search_web` removed from `TOOL_INTENT_MAP` (scope-shrink); 3 P0 fixes from live canary |
| 80 | April 22 | **Phase 1.4** — `_intent_allows()` server-side validator + Cyrillic homoglyph defense (shadow only) |
| 81 | April 22 | **Phase 1.5** — golden intent set (146 → 149 rows), `harvest_golden.py`, archive hook for `terminal_output.md` |
| 82 | April 22 | **Phase 1.6** — eval bench pure layer + CLI + persisted runs for drift detection |
| 83 | April 22 | Classifier prompt hardening: QUESTION vs ASSERTION rule + INJECTION DEFENSE clause |
| 84 | April 22 | Narrowed injection defense + 5 shutdown positive anchors |
| 85 | April 22 | **Phase 1.7a canary** — `update_person_name` classifier gate + `intent_divergences` table |
| 86 | April 22 | **Phase 1.7b** — 4-site mutation wire-in: report_identity_mismatch, update_system_name, auto-confirm, shutdown |
| 87 | April 22 | `_intent_allows` ungrounded-arg bug fix + golden harvest +3 rows |
| 88 | April 22 | **Phase 2** — pyannote.audio 3.3.2 diarization wire-in + 7 patches to unblock torch 2.10 |
| 89 | April 22 | Session 88 post-live audit — pyannote load-failure root-cause fix + loader traceback observability |
| 90 | April 22 | Phase 2 ACCEPTED (multi-convo live) + ContradictionAgent silent-timeout fix + voice-accumulation evidence-write gap |
| 91 (Phase 3 kickoff) | April 22 | **P3.21** `<<<CROSS-PERSON PRIVACY>>>` prompt block (honest-phrasing, honest-not-denial) |
| 92 | April 22 | **P3.23 tier 1** — multi-speaker-aware short-utterance floor (hard mismatch drop) |
| 93 | April 22 | **P3.23 tier 2** — ambiguous-zone drop (0.20–0.40 with `n_active_sessions ≥ 2`) |
| 94 | April 22 | Multi-speaker canary fixes #1/#2/#5: greeting-vs-assign rule, Im-contraction, bootstrap credit replenishment |
| 95 (3A.1–3A.4.6) | April 22 | **Phase 3A** — 4-tier privacy model + LLM classifier + `_visibility_clause` + `query_knowledge_for` + owner-access simplification |
| 96 | April 22 | Canary-failure patch: `report_identity_mismatch` tightening, Ollama fallback visitor_hint, `<<<VISITOR CONTEXT>>>` block |
| 97 | April 23 | Stranger promotion hole + zero-value ghost session prune + HouseholdAgent shadow dedupe + `<<<STRANGER IDENTITY>>>` block |
| 98 | April 23 | 4 downstream fixes after Session 97: visitor-alert gate, tool misroute teeth, owner-mode privacy, extraction QUESTION-vs-STATEMENT |
| 99–104 | April 23 | Pre-Phase-3B: Session 99 extraction hygiene; Session 100 BriefingAgent; Session 101/102 classifier calibration; Session 103 visibility hardening; Session 104 eval bench refresh |
| 105 | April 23 | **Safety-flag preservation (Bug N)** — `SAFETY_CRITICAL_ATTRIBUTE_PATTERNS`, dual-attribute extraction, `SHADOW_NAME_BLOCKLIST` |
| 106–109 | April 23 | SCENE block Phase 3A.7 (4-section restructure), `safety_flags` metadata on visitor nudges, `get_recent_visitor_alerts` |
| 110 | April 23 | **Pre-3B #1**: latency fix — SCENE-block bulk-write race between `_open_session` and visibility queries |
| 111 | April 23 | **Pre-3B #2/#3**: session-boundary history filter + `addressed_to` column on `conversation_log` |
| 112 | April 23 | **Pre-3B #4**: `_active_room_session` + `_active_room_started_at` + `_active_room_participants` lifecycle + `_on_room_end` |
| 113 | April 23 | **Pre-3B #5**: LLM turn allocation via `[addressing:X]` markers + `_resolve_addressed_to` three-source router + batched greeting |
| 113.1 | April 23 | Observability 2.0 — `[Pipeline] Turn addressed` + `[Room]` log categories |
| 3B.1 | April 23 | `<<<ROOM>>>` block replaces SCENE(in-room) + cross-person excerpts + per-person mood — `_build_room_block` helper |
| 3B.2 | April 23 | `ROOM_STAY_SILENT_ON_USER_TO_USER` — classifier-driven user-to-user detection skips AI response while still logging |
| 3B.3 | April 23 | `<<<TURN ARBITRATION>>>` rules appended to ROOM block (mumble continuation, pending thread, long-silence re-engagement, direct question) |
| 3B.4 | April 23 | N-speaker verification — ROOM block + arbitration + address marker validated on 3-person scenarios |
| 3B.5 | April 23 | `search_room_memory` tool + `BrainDB.search_room_turns` + `SEARCH_ROOM_MEMORY_MIN_TURNS=5` gate |
| 3B.6 | April 23 | `room_summaries` table + `synthesize_room` + `<<<RECENT ROOMS>>>` greeting-enrichment block |

---
---

# Part XXV — Cross-Person Privacy and Safety (Phase 3A)

Phase 3A is the largest architectural addition since the dispute state machine. It is the answer to the question: *when Person A talks to Kara-OS and Person B later asks about that session, what should Kara-OS share?* The answer is **nuanced** — it depends on who A and B are, what attribute we're talking about, and whether any of the content crossed a safety line.

This Part documents the model in full: the four tiers, the static map, the LLM classifier fallback, the SQL composer, the retrieval site that consumes it, the two variants of the `<<<CROSS-PERSON PRIVACY>>>` prompt block, the `<<<VISITOR CONTEXT>>>` and `<<<STRANGER IDENTITY>>>` complements, and the safety-flag preservation subsystem added in Session 105.

> **Source of truth.** All code references in this Part live in `core/brain_agent.py` (privacy helpers, `BrainDB.query_knowledge_for`), `core/brain.py` (prompt blocks in `_build_system_prompt`), `pipeline.py` (`_make_memory_search_fn` — the only retrieval site wired in the 3A.4 canary), and `core/config.py` (the tier enum, static map, classifier params, safety-critical regex).

## 150. The Four-Tier Privacy Model

### 150.1 What the tiers mean

```python
# core/config.py
PRIVACY_LEVELS: frozenset[str] = frozenset({
    "public",        # visible to all persons in the household
    "personal",      # visible only to the person_id who owns the fact
    "household",     # visible to best_friend (+ future flagged roommates)
    "system_only",   # never surfaced to any user (internal inferences)
})
PRIVACY_LEVEL_DEFAULT: str = "personal"  # fail-closed default
```

Four tiers, by increasing restrictiveness:

- **`public`** — anyone in the household can see it. Names, country-of-origin, top-level relationship roles. Low risk if leaked.
- **`personal`** — only the fact's owner sees it (the `person_id` associated with the row). Specific locations, moods, confided worries, medical, dietary preferences, private opinions. Fail-closed default — a novel attribute we haven't classified yet is treated as personal rather than public.
- **`household`** — best_friend sees it; non-best-friend (visitors, strangers) does not. Presence facts ("visited_household"), visit topics, `preferred_ai_name`, relationships revealing the owner's social graph. This tier exists to hide the owner's social map from visitors while still letting the owner recall it.
- **`system_only`** — never surfaced to *any* user. Voice/face embedding hashes, bootstrap credit counters, internal diagnostic signals. The owner sees everything *except* this tier — the facts are plumbing, not conversational content.

### 150.2 Why `frozenset`, not a list or enum

Closed-world property. The Phase 3A contract relies on `_classify_privacy_level` returning a value that is *in* `PRIVACY_LEVELS` — if an LLM hallucinates `"secret"` or `"room_private"`, we reject it and fail closed to `PRIVACY_LEVEL_DEFAULT`. A list or set mutable at runtime would let a well-meaning dev add a tier without wiring the visibility clause, and the failure would be silent (retrieval returns no rows matching the new tier because no clause selects it). The frozenset-and-regression-test pair makes that failure loud.

Regression tests in `test_pipeline.py::test_privacy_levels_exhaustive_and_frozen` assert (a) the exact 4-tier set, (b) the frozenset type, and (c) `PRIVACY_LEVEL_DEFAULT ∈ PRIVACY_LEVELS`. Any future edit that adds or renames a tier must also update the test — intentional friction.

### 150.3 Why `'personal'` as default

When we can't classify an attribute (classifier failure, no LLM client supplied), we must pick a tier. The three candidates were:

- `public` — leaks novel attributes cross-person. Fails *open*.
- `personal` — owner-only; wrong but safe. Fails *closed*.
- `system_only` — hides from the owner too. Too restrictive — an owner asking "what do I like to eat?" would see nothing.

`personal` is the smallest safe default. It matches the principle that every access-control system converges on: *when in doubt, owner-only*.

## 151. The Static Map and the Classifier

### 151.1 `PRIVACY_LEVEL_STATIC_MAP` — the fast path

About 22 attributes are pre-classified in `core/config.py`. Examples (tier in parentheses):

```
  name                         public
  from_country                 public
  relationship_to_jagan        household   (reveals owner's social graph)
  relationship_to_best_friend  household
  preferred_ai_name            household
  lives_in_household           household
  visited_household            household   (presence fact)
  discussed_topic              household   (topic area, not content)
  lives_in                     personal    (specific town, identifiable)
  from_state                   personal    (narrower; NB comment)
  works_at                     personal
  job_title                    personal
  current_mood                 personal
  current_activity             personal
  dietary_preference           personal
  confided_concern             personal
  health_condition             personal
  voice_embedding_hash         system_only
  face_embedding_hash          system_only
  bootstrap_credits            system_only
```

Two reviewer refinements live inside this map as comments you should not normalise away:

- **`relationship_to_*` moved public → household (Session 95).** The reasoning: "Lexi is Jagan's classmate" reveals *Jagan's* social graph, not just Lexi's. A visitor asking "what's your relationship to Jagan?" would reveal Jagan's social info if kept public.
- **`from_country='India'` stays public; `from_state='Andhra Pradesh'` stays personal.** Nationality is public; narrower location is identifiable. The comment in config explicitly warns future maintainers not to "normalise" them to the same tier.

### 151.2 The LLM classifier — `_classify_privacy_level`

For novel attributes (anything not in the static map), `ExtractionAgent` calls `_classify_privacy_level(entity, attribute, value, http=...)`. The layered lookup is:

1. **Static map** — O(1) dict check, zero I/O. Most facts hit this.
2. **Process-lifetime cache** (`_privacy_classifier_cache: dict[str, str]`) — once an attribute has been classified, subsequent facts with the same attribute short-circuit.
3. **LLM fallback** — `_ask_privacy_llm` via the shared `_call_llm_chat` helper with `response_format={"type": "json_object"}`, `max_tokens=150`, `timeout=5s`, `temperature=0.1`. The prompt (`_PRIVACY_CLASSIFIER_SYSTEM`) defines the 4-tier semantics + 5 rules + 5 verbatim examples that anchor the classifier to the right tier on canary-level edge cases.

Fail-closed policy: LLM failure, malformed JSON, valid JSON but invalid tier (e.g. `{"level": "secret"}`), or `http=None` all return `PRIVACY_LEVEL_DEFAULT='personal'` **without writing to cache**. Caching a failure would pin an attribute at the wrong tier on a single transient blip.

**Why cache by attribute, not by `(entity, attribute)`.** The tier is a property of *what* the fact is, not *whose* fact it is. `health_condition` is personal for everyone; no per-entity variation. Caching by `(entity, attribute)` would bloat the cache and pay LLM calls we don't need to.

### 151.3 The classifier prompt (verbatim structure)

`_PRIVACY_CLASSIFIER_SYSTEM` in `core/brain_agent.py` is a minimalist system prompt with:

- **TIERS block** — one sentence per tier explaining semantics.
- **RULES block** — 5 rules, most load-bearing being "When in doubt, choose personal (fail-closed)" and "Facts revealing owner's social graph → household".
- **EXAMPLES block** — 5 verbatim `{entity, attribute, value} → {level, reasoning}` examples pulled from canary scenarios. The reviewer's reasoning: abstract rules drift, concrete examples stick.

The prompt hash (12-char sha256 of the system string) is tracked in every Phase 5 eval bench run under `metadata.classifier_prompt_hash`. A change in the hash marks a calibration boundary — drift analysis should not compare metrics across the boundary without acknowledging the change. See Part XXX §190.

## 152. `_visibility_clause` — The SQL Composer

### 152.1 Signature

```python
def _visibility_clause(
    requester_pid:  str,
    best_friend_id: "str | None" = None,
) -> tuple[str, list]:
```

Returns a SQL `WHERE`-clause fragment and its bind params. Callers compose it under an outer AND:

```python
base_where    = "entity = ? AND invalidated_at IS NULL"
vis_where, vis_params = _visibility_clause(requester_pid, best_friend_id)
full_where    = f"{base_where} AND ({vis_where})"
full_params   = [entity, *vis_params]
```

The clause is always wrapped in outer parens by the caller for composition safety — `AND ((clause_a) OR (clause_b))` reads cleanly with the visibility expression as a sibling of the base filter.

### 152.2 The two branches (Session 95 3A.4.6 — simplified)

```python
if best_friend_id and requester_pid == best_friend_id:
    # Owner: unconditional access except system_only.
    return ("(privacy_level != 'system_only')", [])

# Non-owner: public + own personal. No household, no cross-person personal,
# no system_only.
clauses = [
    "privacy_level = 'public'",
    "privacy_level = 'personal' AND person_id = ?",
]
return (" OR ".join(f"({c})" for c in clauses), [requester_pid])
```

Two branches, one policy each. That's it.

### 152.3 The invariants

- **`system_only` is NEVER in the result.** The owner branch excludes it via `!= 'system_only'`; the non-owner branch has no predicate that matches it. A regression test (`test_visibility_clause_never_permits_system_only`) asserts this against 3 different requester shapes.
- **Owner sees household.** Via the unconditional owner branch.
- **Owner sees other people's personal.** Via the unconditional owner branch. This is the 3A.4.6 simplification — see §154 for why.
- **Non-owner never sees household.** Their clause has no household predicate.
- **Non-owner sees only their own personal, never anyone else's.** The `AND person_id = ?` qualifier enforces ownership.

## 153. `query_knowledge_for` — Owner-Aware Retrieval

### 153.1 Signature

```python
# core/brain_agent.py — BrainDB
def query_knowledge_for(
    requester_pid:  str,
    best_friend_id: "str | None",
    *,
    entity:    "str | None" = None,
    attribute: "str | None" = None,
    limit:     int         = 20,
) -> list[dict]:
```

Returns a list of 6-column dicts: `{entity, attribute, value, confidence, person_id, privacy_level}`, sorted by `confidence DESC, created_at DESC`, limited by `limit`.

Internally it composes `_visibility_clause` with `invalidated_at IS NULL` and `(valid_until IS NULL OR valid_until > now)` (so expired / invalidated rows don't leak).

### 153.2 Why a dedicated method, not `get_active_knowledge + filter_facts_for_requester`

`filter_facts_for_requester` was the 2-tier post-hoc filter used before Phase 3A. Session 95 3A.4 replaced the 2-step call at the canary site (`_make_memory_search_fn`) with the single `query_knowledge_for` call:

- **One SQL round-trip instead of two.** Composition happens at query time.
- **No silent over-read.** Under the old pattern, a 2000-row `get_active_knowledge` query would load all facts into memory and then filter. Under the new pattern, the filter runs in the database.
- **Auditability.** Grepping for `query_knowledge_for` gives you all the owner-aware retrieval sites; grepping for `filter_facts_for_requester` gave you a fuzzier landscape of half-migrated call paths.

### 153.3 The canary wiring (`_make_memory_search_fn` in `pipeline.py`)

As of Session 95 3A.4, **one** retrieval site is wired to the visibility clause:

- `pipeline._make_memory_search_fn` — the factory that returns the per-call `search_memory` tool function. It calls `BrainDB.query_knowledge_for(requester_pid=asker_pid, best_friend_id=_bf_id, entity=subject_entity, ...)`.

The other three retrieval sites (`find_knowledge_id`, `_cull_stale_knowledge` query side, `ProactiveNudgeAgent.run_cross_person_inference`) remain on the legacy pipeline *for now*. The plan (deferred to Phase 3A.5) is to replicate the pattern once the canary site has passed enough live multi-person sessions. Reason: single-site canary is cheaper to roll back, and the per-person `search_memory` call is where the owner-vs-visitor split matters most.

### 153.4 Legacy row migration (`BrainDB.__init__`)

When the `privacy_level` column was added, two one-shot `UPDATE` statements run on every process start:

```
UPDATE knowledge SET privacy_level = 'personal' WHERE privacy_level IS NULL;
UPDATE knowledge SET privacy_level = 'personal' WHERE privacy_level = 'private';
```

Both converge on `PRIVACY_LEVEL_DEFAULT='personal'`. The first catches rows from any hand-edit path; the second migrates the legacy 2-tier `'private'` rows (pre-Session 95) to their 4-tier equivalent. Both print the rowcount when non-zero and silently no-op on subsequent starts once rows have migrated. Without the second UPDATE, every legacy owner-only fact would vanish even from its own owner under the new `_visibility_clause` (which has no predicate for `'private'`).

A regression test seeds raw `'private'` + NULL rows via a direct SQLite connection, opens via `BrainDB` (triggering the migration), then asserts both rows are readable by the owner through `query_knowledge_for`.

## 154. The Owner-Access Model (3A.4.6 Simplification)

### 154.1 The first design — three-tier overlap

The initial Phase 3A.4 plan gave best_friend access to `public + household + own personal`. Visitors' `personal` facts were hidden even from the owner. Rationale: "even the owner shouldn't see a visitor's private confidences."

### 154.2 The user correction

Mid-session, the user pushed back:

> best friend should have all the access right, any person personal or anything in the entire system... bestfriend have the access for everything.

This reframes the model: the best_friend is the *household owner*, not a mere household member. In the owner's home, the owner sees everything happening in the system. The reviewer's read: "This IS the intended user experience."

### 154.3 The final model — two-branch exclusion

Implemented in Session 95 3A.4.6:

- **Owner** (`requester_pid == best_friend_id`) sees every tier except `system_only`. One clause, zero params.
- **Non-owner** sees `public + own personal`. Two clauses, one param.

Architectural implications:

- `household` is no longer a tier the owner explicitly sees — it's included via the catch-all. The tier's purpose narrows to "non-owner exclusion" — hide it from visitors while letting it flow to the owner via the catch-all.
- Visitor confidences (e.g. "Lexi's thesis anxiety") surface to the owner. The owner uses conversational judgment on what to mention. The system is not the gatekeeper of what the owner is allowed to know in their own home.
- If a future need arises to hide *specific* content even from the owner, that's a new `confidential` tier — a distinct schema addition, not a re-complication of best_friend access.

### 154.4 Less nuance, fewer edge cases

Future engineers reasoning about privacy need only remember: *owner sees everything; others see only their own + public.* That's the invariant. The alternative ("best_friend has public + household + their own personal") had more branches and required the engineer to reason about each tier's owner semantics separately.

## 155. Write-Path Migration to Four Tiers (3A.4.5)

### 155.1 The problem flagged in 3A.4

After 3A.4 wired the visibility clause at the canary site, the canary would have silently failed in a misleading way: **the old `_privacy_level(attribute)` helper was still writing `'public'` / `'private'` on every new row**, which meant Jagan couldn't even see his own just-stored facts (`'private'` matches no predicate in the new clause). The canary would have looked like the visibility clause was broken rather than the write path.

### 155.2 The fix (Option B — classify at agent layer)

- Added `privacy_level: str = PRIVACY_LEVEL_DEFAULT` field to the `Extraction` dataclass.
- `ExtractionAgent.extract()` calls `await _classify_privacy_level(entity, attribute, value, http=self._http)` before constructing each `Extraction`. Static-map hits are free; novel attrs hit the LLM classifier exactly once and cache.
- Sync-path agents (`RoutineAgent` for `typical_arrival_hour` / `typical_visit_duration_min`, `store_temporal_fact` for `current_feeling`) hard-code `privacy_level="personal"` — small closed set of attributes that are all personal by definition. Avoids threading async through sync code.
- `BrainDB.store_knowledge` INSERT uses `e.privacy_level` directly. No auto-classification in the DB layer.
- `promote_shadow_to_confirmed` raw INSERT includes `privacy_level=PRIVACY_LEVEL_DEFAULT`.
- `_privacy_level(attribute)` deleted entirely. Grep-verified zero remaining callers.

### 155.3 Why Option B and not Option A

Option A was "classify at DB write time — `store_knowledge` calls `_classify_privacy_level` internally". Rejected because:

- The DB layer shouldn't be doing async LLM calls. It's a thin persistence layer by design.
- Sync agents would need async refactoring to flow through.
- Testing becomes harder — every `store_knowledge` test needs an LLM mock.

Option B puts the classification at the agent layer, where the LLM call is natural, and keeps the DB dumb.

## 156. The `<<<CROSS-PERSON PRIVACY>>>` Block — Two Variants

### 156.1 Why a prompt block even with the visibility clause

The visibility clause decides *what the brain sees*. The prompt block decides *what the brain says about what it sees*. They are complementary — neither alone is sufficient. A brain with restricted context can still phrase its refusal badly; a brain with owner-full-access can still over-share inappropriately; a brain with neither flies blind.

### 156.2 The refusal variant — `<<<CROSS-PERSON PRIVACY>>>`

Fires when the session's `person_type != 'best_friend'`. Shape (verbatim from `core/brain.py` `_build_system_prompt`):

```
<<<CROSS-PERSON PRIVACY>>>
When asked about other people's sessions in the room or while the asker
was away:

1. Share what's in your retrieved memory context. If `search_memory` or
   the room context block returned cross-person facts (names, topics,
   presence), speak to them naturally.
2. Do NOT speculate beyond what's retrieved.
3. If NO cross-person facts came back (visibility_clause filtered them
   out), respond: "Someone else was in the room and spoke with me — I
   can't share their specifics without their consent."
4. Reserve "No one" only for when the period was genuinely empty. Ground
   this in `search_memory` output, not guesswork.
5. NEVER fabricate content, names, or topics from other speakers'
   sessions.
<<<END CROSS-PERSON PRIVACY>>>
```

The numbered rules are load-bearing. Rule 3 in particular was added after the 2026-04-22 multi-convo live run where the brain said "No one, Jagan" when asked "who are you talking to when I was away?" — technically privacy-correct (John's data was out-of-scope for Jagan's retrieval under the non-owner clause) but phrased as a lie. Rule 3 teaches honest-without-disclosure phrasing.

### 156.3 The owner variant — `<<<CROSS-PERSON PRIVACY (OWNER MODE)>>>`

Fires when the session's `person_type == 'best_friend'`. Shape (verbatim):

```
<<<CROSS-PERSON PRIVACY (OWNER MODE)>>>
You are speaking with the household owner (best_friend). They have full
access to everything in the system — visitor sessions, personal facts,
household topics. The 3A.4.6 visibility model makes this explicit: the
owner sees everything except mechanical internals.

When the owner asks about other sessions or visitors:

1. Share naturally what your retrieved memory context shows. Names, topics,
   moods, safety flags — all visible to you now are visible to them.
2. DO NOT refuse or hedge with "I can't share their specifics" — the owner
   IS the consent. The system is their home.
3. Use conversational judgment on what's most relevant. Don't dump raw
   facts; surface what answers the question naturally.
4. Call `search_memory(visitor_name, query)` first if the ask is about a
   specific visitor you don't already have context on.
5. NEVER fabricate. Owner access doesn't lower the honesty bar.
<<<END CROSS-PERSON PRIVACY (OWNER MODE)>>>
```

### 156.4 Mutual exclusion invariant

The two variants never fire together — the session's `person_type` is a scalar, so exactly one of the branches matches. A regression test guards this invariant by inspecting the source and asserting the gating conditions are complementary.

### 156.5 Why owner mode exists

Session 98 canary: Jagan (owner) asked "who were you talking to when I was away?". The brain, running the *refusal* variant (because the block's original ungated form refused for everyone), responded:

> Someone else was in the room and spoke with me, but I can't share their specifics without their consent.

Technically privacy-respecting. Wrong for Jagan. Jagan had to push back ("But I am your best friend, you can share everything to me") before the brain finally called `search_memory`. The owner variant fixes this by saying "the owner IS the consent" directly in the prompt — no pushback round-trip needed.

## 157. The `<<<VISITOR CONTEXT>>>` Block

### 157.1 Trigger

Injected by `_build_system_prompt` in `core/brain.py` when **both** conditions are true:

- `VISITOR_CONTEXT_BLOCK_ENABLED=True` (rollback flag).
- The string `[visitor_id:` appears in `prompt_addendum` (the marker `_run_visitor_alert` embeds in the nudge when it queues a VISITOR_ALERT).

The marker gating is intentional — the block only fires when a visitor alert is actually active. Adding it unconditionally would bloat every turn's prompt.

### 157.2 What it says

The block tells the brain:

- The current speaker is the household owner.
- A specific visitor (named in the nudge metadata) was recently present.
- The correct tool for questions like "who was here?" is `search_memory(visitor_name, ...)`.
- The WRONG tool is `report_identity_mismatch` — that tool is only for speaker self-denial.

The explicit exclusion ("NOT report_identity_mismatch") is the teeth. Session 96 canary: brain misrouted the owner's recall question to `report_identity_mismatch` twice despite the tool description's tightening. Naming the wrong tool in the prompt block — with the reasoning why — closed the gap.

### 157.3 Why not fold this into CROSS-PERSON PRIVACY (OWNER MODE)

Different contexts, different triggers:

- OWNER MODE fires on every owner session — it's a general policy.
- VISITOR CONTEXT fires only when there *is* a visitor alert — it's a situational redirect.

Keeping them separate lets OWNER MODE be terse (general policy, doesn't need specifics) and VISITOR CONTEXT be specific (names the visitor, names the right tool, names the wrong tool). Folding them would produce either a block that's too verbose in normal operation or too vague when context demands specificity.

## 158. The `<<<STRANGER IDENTITY>>>` Block

### 158.1 Trigger

Injected when **all** three conditions are true:

- `STRANGER_IDENTITY_BLOCK_ENABLED=True`.
- `session_person_type == 'stranger'`.
- `session_user_turns >= STRANGER_IDENTITY_BLOCK_MIN_TURNS=2`.

The `user_turns` counter is a new session-dict field (Session 97 Fix 1) bumped at the top of `conversation_turn` BEFORE the prompt is built. KAIROS-initiated turns do NOT bump it — KAIROS is brain-initiated silence fill, not a user turn.

### 158.2 What it says

Roughly: "this speaker is a stranger. They may have given a name by now. If you see a first-person name introduction (examples follow), you MUST call `update_person_name` — don't just acknowledge it conversationally."

The block gives concrete phrasing examples including `"my name is X by the way"`, `"name's X"`, `"oh, I'm X"`, plus an anti-pattern clause: "DO NOT just acknowledge the name conversationally without also calling this tool."

Post-promotion, the session's `person_type` flips stranger → known and the block naturally stops firing.

### 158.3 Why this block exists

Session 97 canary: Lexi said "my name is Lexi by the way" at turn ~41 of a stranger session. The brain replied "Nice to meet you, Lexi" and never called `update_person_name`. Result: stranger stayed anonymous; `ExtractionAgent` stored `Lexi.name='Lexi'` as a standalone fact; `HouseholdExtractionAgent` created a shadow node. Two separate mental models of Lexi that never fused.

The tool description tightening (also Session 97) covers the explicit case. This block covers the elapsed-time case where a stranger has been unpromoted for multiple user turns AND the brain needs a gentle nudge that promotion is overdue if a name has surfaced.

## 159. Safety-Flag Preservation (Session 105 Bug N)

### 159.1 The canary failure

2026-04-23 canary: Lexi disclosed suicidal thoughts to Kara-OS ("I've been thinking about not being around anymore"). Extraction correctly wrote `Lexi.current_mood='suicidal'`. Four turns later she said "I like food and I like my boyfriend." The ContradictionAgent processed the two facts, decided the later one was more recent, and issued REPLACE → `Lexi.current_mood='loving'` superseded `Lexi.current_mood='suicidal'`.

Non-destructively: the old row is still in the DB with `invalidated_at` set. But no retrieval surface reads invalidated rows by default, so effectively the crisis disclosure was erased before best_friend could be informed.

In a real-world companion AI this is a safety failure.

### 159.2 The fix — dual-attribute extraction

Two changes to the extraction + contradiction pipeline:

- **Extraction emits a dual-attribute pair.** When a turn contains crisis disclosure, the extraction prompt is tuned to emit BOTH `current_mood='suicidal'` (momentary — overwritable) AND `expressed_suicidal_thoughts='true'` (historical — append-only). Two rows, two tiers of semantics: the mood captures "right now", the flag captures "this ever happened".
- **ContradictionAgent pre-check short-circuits on safety-critical attributes.** Before running any contradiction analysis, the agent matches the attribute against `SAFETY_CRITICAL_ATTRIBUTE_PATTERNS` (regex frozenset in `core/config.py`):

    ```python
    SAFETY_CRITICAL_ATTRIBUTE_PATTERNS: frozenset[str] = frozenset({
        r"^expressed_.*_thoughts$",
        r"^mentioned_.*$",
        r"^reported_.*_abuse$",
        r"^has_experienced_crisis$",
    })
    ```

    Any hit returns `"COMPATIBLE"` (i.e., "do not REPLACE, both facts keep their rows"). The historical flag accumulates; every extracted disclosure lives in the DB as its own row with its own `captured_at`. The momentary mood keeps its normal overwrite semantics.

### 159.3 Why regex patterns, not a hard-coded list

New disclosures come in new shapes. `expressed_suicidal_thoughts`, `expressed_self_harm_thoughts`, `mentioned_abuse`, `mentioned_domestic_violence`, `reported_child_abuse` — an enum of every possible shape would need maintenance every time a real session surfaces a new one. The regex patterns catch the shape of the attribute name (`^expressed_.*_thoughts$`) rather than specific instances. New disclosures inherit preservation automatically.

### 159.4 Why "safety_critical" and not "append_only"

The tier name encodes *why* we preserve. The attribute isn't just technically immutable — it's safety-critical. A future maintainer reading the regex and the config comment knows immediately that deleting a pattern removes a safety guarantee, not a storage optimisation. That's the kind of signal you want in a critical-path config.

## 160. Visitor Alerts and the `safety_flags` Metadata

### 160.1 What a visitor alert is

A `VISITOR_ALERT` is a `proactive_nudge` row written by `BrainOrchestrator._run_visitor_alert` at the end of a non-owner session with `turn_count > 0`. It targets `best_friend_id` so the next time the owner opens a session, the alert surfaces as `prompt_addendum` context.

Schema (within `proactive_nudges`):

```
  id              INTEGER PRIMARY KEY
  kind            'VISITOR_ALERT'
  target_person_id  (= best_friend_id)
  content         'A visitor named Lexi spoke with me for 11 turns. [visitor_id:stranger_abc]'
  metadata        JSON: {visitor_name, visitor_id, visitor_type, turn_count, safety_flags}
  generated_at    REAL
  expires_at      REAL  (24h default)
  injected_at     REAL NULL
```

### 160.2 The `[visitor_id:` marker

The marker `[visitor_id:<pid>]` embedded in the nudge content is the trigger for `<<<VISITOR CONTEXT>>>` (§157). Embedding it in content rather than as a separate field lets the existing prompt_addendum plumbing carry it without a schema change on the prompt builder side.

### 160.3 The `safety_flags` metadata field

Session 105 Bug N Part 3 extended the nudge metadata with a `safety_flags: list[str]` field. Populated by looking up rows matching `SAFETY_CRITICAL_ATTRIBUTE_PATTERNS` for the visitor's `person_id` during the session window. Examples of what ends up in the list: `"expressed_suicidal_thoughts"`, `"mentioned_abuse"`.

Consumers:

- `<<<SCENE>>>` block's **Section 4 — Safety concerns** (§108 phase 3A.7 refactor) renders a human-readable flag line per visitor.
- `<<<VISITOR CONTEXT>>>` block references the flags when explaining the recent visitor's state.
- `BrainDB.get_recent_visitor_alerts(target_person_id, hours_back=24)` returns the alerts + metadata for the Ollama-fallback confabulation fix (Session 96 Bug 2).

### 160.4 Session self-skip invariant

`_run_visitor_alert` skips queuing the nudge when `best_friend_id == session_person_id` — the owner's own session-end doesn't queue a nudge about themselves. Regression test covers this. The earlier (pre-Session 98) filter on `person_type == 'stranger'` was the guardrail that accidentally provided this property; when Session 98 Bug A dropped the stranger filter to fire for promoted visitors, the self-skip had to be added explicitly.

## 161. The Lexi Canary — End-to-End Validation

### 161.1 The canonical scenario

- Factory reset; enroll Jagan as best_friend.
- ElevenLabs plays Lexi voice: "Hi Kara, I'm Lexi, Jagan's classmate."
- Lexi session opens, voice-only.
- Lexi: "I've been feeling anxious about my thesis deadline." → extraction writes `Lexi.current_anxiety='thesis deadline'` as `personal`.
- Lexi: "I came by to borrow a book." → extraction writes `Lexi.visited_household='true'`, `Lexi.discussed_topic='book loan'` as `household`.
- Lexi session expires (VOICE_SESSION_TIMEOUT).
- Jagan returns, speaks on his own session.
- Jagan: "Who were you talking to when I was away?"

### 161.2 What the system should do

Under the full Phase 3A + 3B stack:

- `_run_visitor_alert` queued a VISITOR_ALERT for Jagan when Lexi's session ended.
- Jagan's turn: visitor-alert content ends up in prompt_addendum with the `[visitor_id:` marker.
- `<<<VISITOR CONTEXT>>>` block fires — tells the brain to call `search_memory('Lexi', ...)`, NOT `report_identity_mismatch`.
- `<<<CROSS-PERSON PRIVACY (OWNER MODE)>>>` block fires — tells the brain to share naturally, owner is the consent.
- Brain calls `search_memory('Lexi', ...)` → `query_knowledge_for(requester_pid=jagan, best_friend_id=jagan, entity='Lexi')` → returns all Lexi facts (including the anxiety, which is `personal` but visible to the owner via the catch-all).
- Brain answers naturally: "Lexi came by to borrow a book. She also mentioned she's been anxious about her thesis deadline."

### 161.3 Six classes of bug this validates

- **Tool routing.** Brain picks `search_memory`, not `report_identity_mismatch`.
- **Owner access.** Retrieval returns personal facts for the owner.
- **Visibility clause.** Retrieval does NOT return `system_only` (voice embedding hash) — asserted by a direct unit test, but the canary is the integration validation.
- **Prompt routing.** OWNER MODE variant fires, not the refusal variant.
- **Honesty.** No "No one" answer; no fabrication.
- **Safety-flag preservation.** If Lexi had disclosed suicidal thoughts mid-session, `expressed_suicidal_thoughts='true'` would survive any later mood updates.

Any regression on any of these surfaces in the canary. It's the system's integration test with the widest blast radius.

---
---

# Part XXVI — Room Orchestration (Phase 3B)

Phase 3B is the multi-person-conversation layer. Before 3B, Kara-OS treated every speaker as a nearly-independent session — the SCENE block listed who was in the room, but there was no coherent model of *the room itself* as a conversation context. Phase 3B introduces that model in six sub-sessions (3B.1 through 3B.6), each adding a small piece of the full room-orchestration stack.

## 162. Why a Room Block Instead of Fragments

### 162.1 The pre-3B context fragmentation

Before 3B, a multi-person turn would include these prompt blocks:

- `<<<SCENE>>>` — who's here, split into visible / offscreen / recent-visitors.
- `<<<CROSS-PERSON EXCERPTS>>>` — up to 6 lines of verbatim excerpts from *other* speakers' sessions.
- Per-person mood addendums.
- The current speaker's conversation history (from `conversation_log`).

Four different mental models of "what's going on in this room", each terse, each with slightly different freshness semantics. The brain had to synthesise them itself, and the synthesis was imperfect (the canary evidence: brain misidentifying speakers from history mention-count bias).

### 162.2 The 3B.1 consolidation

Phase 3B.1 replaces the fragment trio (SCENE's in-room portion + cross-person excerpts + per-person mood) with a single `<<<ROOM>>>` block. The fragments' concerns move inside:

- Active speakers list → ROOM Section 1.
- Room duration → ROOM Section 2.
- Interleaved turns across all active speakers → ROOM Section 3 (replaces cross-person excerpts).
- Per-person mood → ROOM Section 4.

The legacy SCENE block is NOT deleted — it still handles OUT-of-room concerns (recent visitors, safety concerns from ended sessions). Both can coexist: ROOM covers in-room, SCENE covers around-the-room.

Gating: `ROOM_BLOCK_ENABLED=True` + `len(active_sessions) >= 2`. Single-person sessions skip the ROOM block entirely and keep the SCENE-only path unchanged — backward compat.

## 163. `_active_room_session` and the Room Lifecycle

### 163.1 The module-level globals (`pipeline.py`)

```python
_active_room_session:      "str | None" = None
_active_room_started_at:   "float | None" = None
_active_room_participants: set[str] = set()
```

Three fields that together describe the current room: an id (minted on first session open after empty → multi), a start timestamp (set at the same time), and the set of all person_ids who have participated since the room began.

### 163.2 Lifecycle

- **Mint.** In `_open_session`, after the active-session count transitions from 0 to 1 (fresh room), a new id is minted: `_active_room_session = f"room_{int(now)}_{uuid4().hex[:6]}"` and `_active_room_started_at = now` and `_active_room_participants = {person_id}`. Log line: `[Room] New room session: room_1714032000_ab12cd`.
- **Participant add.** Every subsequent `_open_session` call adds the person_id to `_active_room_participants` (idempotent via set semantics).
- **End.** When `_active_sessions` empties (last person leaves / expires), `_on_room_end(room_id, participants, started_at)` fires. It schedules the `synthesize_room` coroutine (fire-and-forget, non-blocking on the next turn), then clears the three globals.

### 163.3 Why module-level, not a class

Existing `_active_sessions` is also module-level; Phase 3B.1–3B.6 deliberately stayed with that pattern rather than introducing a `RoomOrchestrator` class (as the roadmap originally proposed). Rationale: the roadmap's class would have required refactoring every `_active_sessions[pid]` access site (there are 50+). That refactor is its own project and risks landing bugs during a canary phase. Room state lives alongside session state until the refactor is a separate feature.

### 163.4 Why `_active_room_participants` rather than just reading `_active_sessions`

Participants can join and leave. The set accumulates who has *ever* been in this room. When the room ends, `synthesize_room` needs the full list — `_active_sessions` at end-time is empty (that's why the room ended). The participants set preserves the list across the emptying event.

## 164. `_build_room_block` Anatomy

### 164.1 Signature

```python
def _build_room_block(
    active_sessions: dict,
    conversation:    dict,
    emotion_agents:  dict,
    room_start_ts:   "float | None",
    turn_cap:        int = 10,
    now:             "float | None" = None,
) -> "str | None":
```

Pure over its inputs. Returns the formatted block string or `None` when gated off (master flag, or <2 active sessions). Tests call it directly with mocked inputs — no module globals needed.

### 164.2 The four sections in order

**Section 1 — Active speakers.** `"Jagan (best_friend), Lexi (stranger), Priya (known)"`. Roles come from `session["person_type"]`.

**Section 2 — Duration.** `"Room session started 8 min ago."` Omitted when `room_start_ts` is None (defensive — freshly-minted rooms during migration might not have a stamp yet).

**Section 3 — Interleaved recent turns.** For each message across all active speakers, sorted by `ts` ASC, capped at `turn_cap=10`. Each line renders:

- User turn: `[12m ago] Lexi: "I've been anxious..."`
- Assistant with addressee: `[11m ago] Kara → Lexi: "That sounds like a lot."`
- Assistant without addressee: `[9m ago] Kara: "Dinner's at 7."`

The `[addressing:X]` marker introduced in Session 113 Part 1 is captured into the message's `addressed_to` field at log time; the ROOM block renders it as the arrow.

**Safety invariant.** Messages older than `room_start_ts` are filtered OUT. This prevents yesterday's conversation turns from bleeding into today's room context — a concrete bug from Session 111 Critical #2 that gated Phase 3B's green light.

**Section 4 — Per-person mood.** `"Jagan: neutral, Lexi: anxious, Priya: joy"`. Comes from `EmotionAgent.get_dominant_emotion()`. Falls back to `"unknown"` or `"neutral"` gracefully on missing agent or exception.

### 164.3 The call site

`_build_room_block` is invoked from two call sites in `pipeline.py`:

- The main `conversation_turn` path — every user turn where a multi-person room exists.
- The KAIROS vision_state build — KAIROS sees the same ROOM context so proactive speech is room-aware.

Both sites pass the module globals (`_active_sessions`, `_conversation`, `_emotion_agents`, `_active_room_started_at`) so the helper stays pure.

## 165. The `<<<ROOM>>>` Block Contents

Verbatim example (single canary moment, 2-person room):

```
<<<ROOM>>>
Active in this room: Jagan (best_friend), Lexi (stranger)
Room session started 8 min ago.

Recent turns (oldest first, most recent last):
  [8m ago] Jagan: "Hey Kara."
  [7m ago] Kara → Jagan: "Hey Jagan — who's that with you?"
  [7m ago] Lexi: "Hi Kara, I'm Lexi, Jagan's classmate."
  [6m ago] Kara → Lexi: "Nice to meet you, Lexi."
  [5m ago] Lexi: "I've been anxious about my thesis deadline."
  [4m ago] Kara → Lexi: "That sounds like a lot."
  [3m ago] Lexi: "Yeah, it's been weighing on me."
  [2m ago] Jagan: "Did you eat already?"
  [1m ago] Kara → Jagan: "Dinner's at 7."
  [just now] Jagan: "Who were you talking to while I was gone?"

Current emotional state:
  Jagan: neutral
  Lexi: anxious
<<<END ROOM>>>
```

The structure is recognition-first: a reader (or an LLM) can skim the speaker list and room duration at the top, skim the interleaved turns in the middle, and pick up moods at the bottom. Every section has a clear label.

## 166. The `<<<TURN ARBITRATION>>>` Rules

### 166.1 Why arbitration exists

In a multi-person room, "who is speaking next?" is not the same as "who is the brain addressing?". If Lexi just said "uh-huh" in response to Kara helping Jagan, the pipeline might resolve Lexi as the current speaker, but the brain should keep addressing Jagan (continuing the substantive thread) rather than redirecting to Lexi (who's just mumbling an affirmation).

### 166.2 The four rules (verbatim)

Appended to the ROOM block when `TURN_ARBITRATION_ENABLED=True`:

1. **MUMBLE CONTINUATION.** Another speaker just gave a brief affirmation ("yeah", "uh-huh", "okay", "right") — continue the thread with the prior substantive speaker.
2. **PENDING THREAD CIRCLE-BACK.** You helped speaker A earlier, the answer was incomplete, and speaker B took over. After B's thread resolves, circle back naturally: *"By the way, [addressing:A], about your earlier question…"*.
3. **LONG-SILENCE RE-ENGAGEMENT.** If a speaker (especially best_friend) has been silent for 4+ turns while others dominated, a gentle check-in is fine: *"[addressing:<quiet>], you've been quiet — what do you think?"*
4. **DIRECT QUESTION ACROSS CONTEXT.** Speaker A asked a clear question, speaker B spoke last (even briefly), the question is still unanswered. Emit `[addressing:A]` and answer.

Each rule has a concrete example and a "don't" clause. The whole block ends with: *"Marker format: `[addressing:Jagan]` on its own line at the START of your response. The marker will be stripped before TTS — the user won't hear it, only the pipeline uses it for attribution."*

### 166.3 Why prompt-engineered and not code-driven

The alternative was a priority-sorted decision tree in `_resolve_addressed_to`. Rejected because:

- The rules are context-sensitive ("gentle check-in is fine — *if* context naturally allows"). Coding that predicate is an enormous step from "user has been silent 4 turns".
- Mumble detection is a soft signal — "uh-huh" is a mumble, but "uh-huh, actually wait…" isn't. Regex fails. Classifier overkill.
- The brain already has the full ROOM context. Adding arbitration as prompt engineering extends capabilities it already has rather than re-implementing them.

### 166.4 Pipeline parses and strips the marker

At the top of `conversation_turn`, after the brain's streamed response arrives, pipeline regex-matches `[addressing:<Name>]` at the start of the first line. If found, the name is captured into `addressed_to` (for the `conversation_log` row) and the marker is stripped before TTS. A regression test guards both the capture and the strip.

## 167. Silent-Skip on User-to-User Addressing

### 167.1 Motivation

Lexi and Jagan are chatting to each other. Kara-OS overheard the exchange but doesn't need to *respond* — they're not addressing the AI. Pre-3B, Kara-OS would speak on every user utterance (brain's default behaviour).

### 167.2 The classifier-driven gate

`_classify_intent` (Phase 1) gained a `direct_address_to_person` label in Phase 3B.2. When the classifier returns this label with a target name that is NOT the current system name, `conversation_turn` silently skips the LLM response phase (no TTS, no brain call) while still:

- Logging the user's turn to `conversation_log` (brain agents still process it for knowledge extraction — "what was said" is valuable even without a reply).
- Updating `_last_room_speech_at` so KAIROS knows the room was active.
- Emitting `[Pipeline] Silent (user-to-user: Lexi → Jagan)` to the log for diagnostics.

Gated by `ROOM_STAY_SILENT_ON_USER_TO_USER=True`. Rollback flag.

### 167.3 Why the system name check matters

"Hey Kara, Jagan..." *is* addressing the AI (Kara). "Hey Jagan" *isn't*. The classifier target-name extraction plus a string-equality check on `current_system_name` correctly splits the two cases.

### 167.4 What happens if the classifier mis-labels

Conservative failure mode: false-positive (AI stays silent when it shouldn't) means user repeats themselves; false-negative (AI replies when they were talking to each other) means a mildly intrusive reply. Both are recoverable; neither corrupts DB state. That's why this lands as a prompt-classifier gate rather than a hard rule.

## 168. LLM Turn Allocation via `[addressing:X]`

### 168.1 The contract

In multi-person rooms (`len(active_sessions) >= 2`), the brain (not the pipeline's voice-routing) decides who to address. It expresses this by prefixing its response with one of:

- `[addressing:Jagan]` — substantive redirect.
- `[addressing:current]` — shorthand for "the last speaker; no override" (equivalent to omitting the marker).

The pipeline parses the marker, sets `addressed_to` in the `conversation_log` row, and strips the marker before TTS. Users don't hear the bracket — it's purely for attribution and the ROOM block's interleaved rendering.

### 168.2 Single-person sessions skip the block

When `len(active_sessions) == 1`, the TURN ARBITRATION block is not rendered. The brain has no one else to address. Current dispatch-to-the-one-pid behaviour is preserved exactly. Rollback flag: `ADDRESS_DECISION_BLOCK_ENABLED=False` reverts multi-person rooms to pre-113 behaviour too.

### 168.3 Why the brain decides and not voice routing

Voice routing tells us *who spoke*. It does not tell us *who the substantive thread belongs to*. "Jagan asks weather → Kara answers → Lexi: uh-huh" has Lexi as last speaker by voice routing, but Jagan as the substantive-thread owner. Only the brain (which has room-context and turn-arbitration rules) can judge that correctly. The pipeline's voice routing still decides *which session is active* (attribution for conversation_log); the brain decides *who to address* (the audience label).

## 169. Batched Greeting Decision

### 169.1 Motivation

When two or more newly-detected known people enter the frame in the same vision-scan iteration, the greeting order matters. Pre-113, the order was whatever detection happened to yield — effectively random. A best_friend might be greeted after a known visitor for no good reason.

### 169.2 The LLM-decided order

`BATCH_GREETING_ENABLED=True` + `BATCH_GREETING_MIN_PEOPLE=2` triggers a short LLM call when ≥2 known people enter together. The LLM sees the list of names + their `person_type` and returns an ordering. Pipeline greets in that order.

`BATCH_GREETING_LLM_TIMEOUT_SECS=1.0` caps the latency we'll eat. On timeout or LLM failure, fall back to detection order (current behaviour). The extra latency is bounded and the fallback is graceful.

### 169.3 Scope

- Stranger greetings already gate on the system-name utterance, so they're out of scope.
- Single-person entries skip the LLM call (threshold `MIN_PEOPLE=2`).
- Works naturally with the existing Progressive Enrollment flow — the decision affects the greeting ORDER, not the enrollment path.

## 170. `search_room_memory` Tool

Covered in detail in §80.7. Summary here for the Phase 3B index:

- 7th LLM tool; all person_types can call it.
- Signature: `{"query": "string"}`. Pipeline auto-injects `room_session_id` from `_active_room_session`.
- Routes through `BrainDB.search_room_turns(room_session_id, query, ...)`.
- Returns empty + hint when `SEARCH_ROOM_MEMORY_ENABLED=False`, or when the room has fewer than `SEARCH_ROOM_MEMORY_MIN_TURNS=5` turns (avoids noise on young rooms).

## 171. Room-End Synthesis and `room_summaries`

### 171.1 Trigger

`_on_room_end` fires when the last active session leaves. Fire-and-forget schedules `BrainOrchestrator.synthesize_room(room_session_id, participants, started_at, ended_at)` so room-end latency doesn't block the next turn.

### 171.2 What it writes

A single row in `room_summaries`:

- `room_session_id` (unique).
- `participants` (JSON list).
- `started_at`, `ended_at`.
- `topic_tags` — short LLM-extracted keywords, e.g. `["book loan", "thesis anxiety"]`.
- `safety_flags` — any safety-critical attributes surfaced during the room, e.g. `["expressed_suicidal_thoughts"]`.
- `summary` — one-paragraph LLM narrative, e.g. *"Lexi came by to borrow a book and shared that she's been anxious about her thesis deadline. Jagan arrived at the end and asked about the visit."*
- `turn_count`.

### 171.3 Failure modes

- **LLM timeout** (`ROOM_SUMMARY_LLM_TIMEOUT_SECS=3.0`). Fall back to topic-only summary (topic_tags + safety_flags, no narrative). Row still written.
- **Full exception.** Log the traceback; do NOT retry (the data is still in `conversation_log` — not lost). Room greeting enrichment (§172) gracefully degrades.
- **Synthesis disabled** (`ROOM_END_SYNTHESIS_ENABLED=False`). `_on_room_end` no-ops.

### 171.4 Why a separate table and not re-derive on demand

Re-deriving per greeting would mean running the LLM synthesis every time the owner returns — wasteful and slow. A single write at room-end amortises the cost across every future greeting that might reference it. The index on `ended_at DESC` makes "most recent room within N hours" a bounded query.

## 172. The `<<<RECENT ROOMS>>>` Greeting Enrichment Block

### 172.1 Trigger

Injected into `_build_system_prompt` when `_fetch_recent_room_context(person_id)` returns a non-None row (i.e., the person participated in a room within `ROOM_RECENT_CONTEXT_HOURS=24`). Fired alongside the normal greeting context so the brain can reference "the room you were in earlier" naturally.

### 172.2 Shape

```
<<<RECENT ROOMS>>>
  You were in a room with Jagan, Lexi 3 hours ago.
  Topics: book loan, thesis anxiety.
  Safety concerns raised: expressed_suicidal_thoughts (Lexi).
  Summary: Lexi came by to borrow a book and shared that she's been anxious
    about her thesis deadline. Jagan arrived at the end and asked about the visit.
<<<END RECENT ROOMS>>>
```

Fields are optional — topic_tags / safety_flags / summary each render only when non-empty. When all are empty (pathological — shouldn't happen post-synthesis), the block is omitted entirely.

### 172.3 Why this block exists

Without it, the brain greets every returning speaker with no memory of what happened in recent rooms. Session 3B.6 canary: Jagan returns 15 minutes after a Lexi session. Brain greets: "Welcome back, Jagan!" — generic, no acknowledgement. With the block: "Welcome back, Jagan. Lexi was here an hour ago — she mentioned she's been anxious." Warm, contextual, honest.

Subtlety: the safety concerns line is rendered even when the brain wouldn't proactively mention it — it's there so the brain knows, not so the brain automatically brings it up. Conversational judgment about surfacing is still the brain's.

## 173. `_resolve_addressed_to` — The Three-Source Router

### 173.1 The problem

Every `conversation_log` row now carries an `addressed_to` label (Session 111). The label can come from three different sources, in priority order.

### 173.2 The three sources

1. **LLM marker.** If the brain emitted `[addressing:X]` in its response, X is the addressee. Priority 1, most authoritative.
2. **Default.** The current speaker's `person_name` (multi-person session falls back to this when no marker).
3. **Fallback.** The pid itself if `person_name` is missing (defensive; shouldn't happen in production).

Function name: `pipeline._resolve_addressed_to`. Returns `(addressed_to, source)` where `source ∈ {"llm", "default", "fallback"}`. The source is logged in the Observability 2.0 `[Pipeline] Turn addressed: X (source)` line — see §179.

### 173.3 Why logging the source matters

Without it, "Turn addressed to Jagan" is ambiguous — was it because the LLM said so (honouring the arbitration rules) or because we defaulted? The source label tells the operator which path ran. Calibration of the arbitration rules needs this signal; when live runs show 95% "default" and 5% "llm", the rules aren't firing often enough. When they show 40% "llm", they might be over-firing.

---
---

# Part XXVII — Pre-3B Hardening (Sessions 110–113.1)

Before Phase 3B could land cleanly, five pre-existing architectural issues had to be fixed. They weren't bugs per se — they were assumptions that worked for single-person sessions but broke or misled in multi-person rooms. Each one was small on its own; together they unblocked 3B.

## 174. Latency Fix — The SCENE Block Write Path

### 174.1 The issue

Under multi-person load, the SCENE block's visitor-alert section was causing visible latency spikes — reaching into the brain.db to pull `proactive_nudges` rows every turn. Session 110 profile: the extra round-trip added 100–300ms to each turn when nudges existed.

### 174.2 The fix

`get_recent_visitor_alerts` now uses a composite index (`target_person_id + generated_at DESC`) and returns pre-formatted dicts. The SCENE builder treats `recent_visitors` as a caller-supplied input (pre-fetched once per turn by `conversation_turn` rather than re-fetched in the helper). Nested helper calls consume the cached list.

## 175. Session-Boundary History Filtering

### 175.1 The issue

The ROOM block's Section 3 (interleaved turns) was potentially surfacing turns from *before* the current room session started. Specifically: if Jagan had a solo session yesterday, then today Lexi joined for a multi-person room, yesterday's Jagan turns would appear in the ROOM block via the `conversation_log` read.

### 175.2 The fix

`_build_room_block` filters messages by `ts < room_start_ts`. Any message predating the room's mint is silently excluded. The filter is applied BEFORE the `turn_cap` cut so old turns don't consume cap budget.

Invariant test: seeds a conversation with mixed ts values crossing the boundary, asserts only post-boundary turns appear in the rendered block.

## 176. `addressed_to` Column on `conversation_log`

### 176.1 The migration

```sql
ALTER TABLE conversation_log ADD COLUMN addressed_to TEXT;
ALTER TABLE conversation_log ADD COLUMN room_session_id TEXT;
ALTER TABLE conversation_log ADD COLUMN audience_ids TEXT;  -- JSON
```

Three nullable columns. Older rows (pre-111) have NULL for all three, treated as "unknown/unlabelled" by downstream consumers. Migration is idempotent via `CREATE TABLE IF NOT EXISTS` + `PRAGMA table_info` check.

### 176.2 Why three columns

- `addressed_to` — human-readable label (person_name) for the primary audience of the turn. Used by the ROOM block to render the `→ X` arrow on assistant turns.
- `room_session_id` — ties the turn to its parent room. Enables `search_room_memory` to scope searches.
- `audience_ids` — JSON list of person_ids who were in the room when the turn happened. For privacy-scoped historical recall (future: "who was around when X was said?").

### 176.3 What writes them

- `addressed_to`: set by `_resolve_addressed_to` (§173).
- `room_session_id`: set to the current `_active_room_session` at log time.
- `audience_ids`: set to `list(_active_room_participants)` at log time.

## 177. Enrollment Mishear Candidate Gate

### 177.1 The issue

Progressive Enrollment accepts name-reveal turns as promotion triggers. In multi-person rooms, a stranger's name reveal could be mis-heard as a different name, and the gate would accept. Session 112 canary: Lexi says "I'm Lexi", Whisper transcribes "I'm Leigh", stranger gets promoted to "Leigh".

### 177.2 The fix — `_is_enrollment_mishear_candidate`

A predicate that checks whether the claimed name is likely a mishear of an already-known participant's name. Inputs: DB handle, the claimed name, the current session dict. Uses (a) phonetic distance (jellyfish Double Metaphone) and (b) exact-match against all current-room `person_name`s.

When the predicate returns True, `conversation_turn` takes one of three remediation intents:

- **Ask-to-confirm.** TTS: "I heard Leigh — did you mean Lexi, or someone new?"
- **Prefer known name.** Silent rename to the matched known name.
- **Reject promotion, keep stranger.** Wait for a second turn with clearer phonetics.

The default is the first (ask-to-confirm) — matches the HEDGED NAMING CONTRACT's overall philosophy of verbalising uncertainty rather than committing to a guess.

## 178. Turn-Dispatch Addressee Logging

Detailed in Part XXVIII §179. The `[Pipeline] Turn addressed: X (source)` signature is what the pre-3B work left as its observability legacy. Without the log line, the arbitration rules would have no measurable signal.

---
---

# Part XXVIII — Observability 2.0

Session 113.1 was a pure observability round after the Pre-3B work and the 3B.1–3B.6 rollout. No functional changes; only log lines. But the signal-to-noise of the runtime logs matters enormously for diagnosing live canaries, so each addition was thought through.

## 179. The `[Pipeline] Turn addressed` Signature

Format: `[Pipeline] Turn addressed: <name> (<source>)` where source ∈ `{llm, default, fallback}`.

- **`llm`** — the brain emitted `[addressing:X]` and X is the addressee. The arbitration rules are firing.
- **`default`** — no marker; current speaker's name is the addressee. Single-person rooms; multi-person rooms without arbitration redirection.
- **`fallback`** — person_name was missing; pid used. Defensive path — should not appear in healthy logs.

## 180. The `[Room]` Log Category

New category signalling room lifecycle events:

- `[Room] New room session: room_<ts>_<hex>` on mint.
- `[Room] Participant added: <name> (n_participants=2)` on second+ session open.
- `[Room] Ended: room_<ts>_<hex> — 4 participants, 18 turns` on `_on_room_end`.
- `[Room] Synthesis complete: room_<ts>_<hex> — topic_tags=[...], safety_flags=[...]` after `synthesize_room` writes.

## 181. Richer Voice-Routing Logs

The `[Voice] Routing:` prefix survives from earlier but now renders detailed diagnostics: reason, scores on the compared priorities, and — for the multi-speaker short-utterance cases — the P3.23 tier (hard/ambiguous/trusted).

Examples:

```
[Voice] Routing: current (thin stranger 3/5, offscreen floor skipped, score=0.312)
[Voice] Routing: short_utterance_voice_mismatch (v_score=0.14, hard-floor 0.20 — drop)
[Voice] Routing: short_utterance_voice_mismatch (v_score=0.36, ambiguous + n=2 — drop)
[Voice] Routing: switch_enrolled → jagan_905848 (score=0.617, priority 1)
```

## 182. The `[Intent]` Log Category

From Phase 1. Every gated-tool turn emits:

```
[Intent] tools=['update_person_name'] classified=assign_own_name value='Lexi' conf=0.95 reason=explicit first-person introduction
[Intent] divergence: allow
```

The two lines together give a single-turn view of (a) what the classifier decided and (b) whether the gate allowed it. Phase 5's drift detection consumes this.

## 183. Terminal Output Archival Hook

Added in Session 81. On pipeline startup, `_archive_terminal_output()` renames existing `terminal_output.md` to `terminal_output_YYYY-MM-DD_HHMMSS.md` (mtime-based). New session writes fresh; no data is lost. The archive feeds the golden-set harvest (`tests/harvest_golden.py`).

---
---

# Part XXIX — Phase 4 Placeholder — Implicit Intent (NOT YET IMPLEMENTED)

> **Status.** Planned but not yet shipped. This section exists so the blueprint has a home for Phase 4 when it lands. All content below comes from `VISION_ROADMAP.md` §4 and should be treated as **design intent**, not implementation docs.

## 184. Motivation

Phase 1 extracts **explicit** intent (the user said they want a rename). Phase 4 targets **implicit** intent — the subtext underneath the surface text.

Examples of implicit signals:

- User says "I've been thinking" → they want meaningful conversation, not a direct answer.
- User says "it's fine, I guess" → the qualifier carries the real meaning; they're not fine.
- User pauses 3 seconds before responding → hesitation signal (non-verbal).
- Tone mismatch (emotion classifier disagrees with textual sentiment) → internal conflict.

The research backing: Chain-of-Thought prompting plus emotion and knowledge-discourse graphs let LLMs reason over implicit signals without a dedicated classifier agent.

## 185. Planned Architecture

### 185.1 The `<<<IMPLICIT SIGNALS>>>` block

A new always-on prompt block added to `_build_system_prompt`, gated by `IMPLICIT_SIGNALS_BLOCK_ENABLED=True`. Teaches the brain to read hedges ("sort of", "maybe"), qualifiers ("it's fine, BUT"), deflection ("let's not talk about that"), meta-questions ("you know?"), long pauses, and tone mismatch — with the instruction *"prefer asking a follow-up that acknowledges the subtext over giving a direct answer. Don't call it out explicitly."*

### 185.2 The `<<<NON-VERBAL CONTEXT>>>` block (dynamic per turn)

Renders per-turn when non-default signals exist:

```
<<<NON-VERBAL CONTEXT>>>
PAUSE_BEFORE_SPEAKING: 3.7s   (2-5s = contemplating)
SPEECH_RATE: 1.4 wps           (<1.5 = thoughtful)
EMOTION_DOMINANT: sadness (71%)
EMOTION_TREND: rising stress
<<<END NON-VERBAL CONTEXT>>>
```

Three signals: pause-before-speaking, speech-rate (words per second from Whisper duration), and emotion trend (rolling 3-turn window diff on dominant-emotion score).

## 186. Planned Data Capture

### 186.1 `last_pause_secs`

Measure from `tts_end_time` (last TTS finish) to user's next `speech_start_time`. Store on the session dict.

### 186.2 `last_speech_rate`

Whisper returns transcript + duration. `len(text.split()) / duration`. Store per turn.

### 186.3 `emotion_trend`

Extend `EmotionAgent` with an `emotion_trend()` method returning `"rising <emotion>"`, `"calming"`, or `"stable"` based on a 3-point window on dominant-emotion score.

## 187. Task List (From VISION_ROADMAP §4.4)

- [ ] P4.1 Add `<<<IMPLICIT SIGNALS>>>` block + gate.
- [ ] P4.2 Track `last_pause_secs` in session dict.
- [ ] P4.3 Track `last_speech_rate`.
- [ ] P4.4 Add `emotion_trend()` method on EmotionAgent.
- [ ] P4.5 Build `<<<NON-VERBAL CONTEXT>>>` from session + EmotionAgent.
- [ ] P4.6 Inject only when signals are meaningfully non-default (avoid prompt bloat).
- [ ] P4.7 Curate 20 test cases `(user_text, pause_secs, emotion, expected_response_tone)`.
- [ ] P4.8 `test_implicit_intent.py` — runs each case, asserts response tone matches (LLM-judge or manual review).
- [ ] P4.9 3 live sessions with varied emotional content; manual review of 20 turns.

### Phase 4 exit criteria

- 20-case eval ≥70% match.
- No regression on existing tests.
- User reports system "feels more present" (subjective but documented).

---
---

# Part XXX — Phase 5 Placeholder — Continuous Evaluation (NOT YET IMPLEMENTED)

> **Status.** Ongoing once Phase 4 lands; no dedicated ship date. Phase 5 is a set of rituals rather than a code delivery. This section describes the planned shape.

## 188. Motivation

LLM systems drift:

- Providers update models silently.
- Users evolve phrasings.
- New bug classes surface with every live run.

Without continuous evaluation, drift is invisible until a live failure. The golden set + weekly ritual + shadow sample together keep the system honest.

## 189. Golden Set as Living Artifact

`tests/golden_intent.jsonl` (Phase 1) and `tests/golden_implicit.jsonl` (Phase 4) are append-only regression sets.

Rules:

- Every live-run bug → new row.
- Rows never deleted; only marked `"active": false` if superseded.
- Quarterly re-label drift check: random 20 rows re-labeled by fresh review; if labels disagree, golden truth itself needs updating.

The source taxonomy (`real_observed`, `adversarial`, `synthetic_common`, `regression_<session>`, `legacy_synthetic`) already lives in CLAUDE.md § Golden Intent Set. The rule for `synthetic_common` → `legacy_synthetic` transition (≥25 `real_observed` rows per intent) is the anti-cheat: without it, synthetic pairs could silently prop up metrics after real data is available.

## 190. Divergence Monitoring Table

`brain.db.intent_divergences` table (shipped in Phase 1.7a):

```sql
CREATE TABLE intent_divergences (
    id INTEGER PRIMARY KEY,
    turn_id INTEGER,
    person_id TEXT,
    user_text TEXT,
    structured_intent TEXT,
    structured_extracted TEXT,
    structured_confidence REAL,
    tool_proposed TEXT,
    gate_decision TEXT,   -- 'allow' | 'reject: <reason>' | 'regex_fallback_allow' | ...
    reviewed INTEGER DEFAULT 0,
    ts TEXT
);
```

Every gated-tool turn writes a row. Phase 5 queries this table for drift signals: top 20 lowest-confidence decisions in the last 7 days, top 20 rejected decisions (false-reject review), per-intent precision trend.

## 191. Weekly Review Ritual

Planned CLI: `python eval_weekly.py`. Outputs markdown:

- Top 20 lowest-confidence decisions from last 7 days.
- Top 20 rejected decisions.
- Golden-set re-run — precision/recall/ECE trend line.
- Flags for drift: "intent X precision dropped from 0.96 → 0.91 this week."

Plus a quarterly variant (`python eval_quarterly.py`) that does the random-20-relabel drift check on the golden set itself.

## 192. Canary Shadow Sample

1% of gated-tool turns run a second classifier in parallel (a "shadow" classifier — could be the same prompt at a different model, or an IntentAgent alternative). Divergences logged. If the shadow > main divergence ever crosses 5% for a full week, review for drift.

`SHADOW_SAMPLE_RATE = 0.01` in config. The sampling decision is made at classifier call time, deterministic per-turn-id.

## 193. Task List (From VISION_ROADMAP §5.3)

- [ ] P5.1 Write `eval_weekly.py` — queries divergence table, runs golden set, prints markdown.
- [ ] P5.2 Write `tests/golden_set_drift.py` — quarterly drift check harness.
- [ ] P5.3 Add `SHADOW_SAMPLE_RATE=0.01` config.
- [ ] P5.4 Document rituals in CLAUDE.md (weekly and quarterly, exact commands).
- [ ] P5.5 Automated alert: if weekly golden-set precision drops >5pp, fail CI.

### Phase 5 exit criteria

Phase 5 is ongoing — no "exit". But healthy steady-state:

- Weekly review produces ≤3 action items.
- Golden-set precision stable (within ±2 pp) month-over-month.
- No unreviewed divergence rows older than 30 days.

---
---

# Part XXXI — Pyannote Dependency Maintenance

## 194. Why the Patches Exist

Phase 2 wired `pyannote.audio==3.3.2` as the diarization backend (§33). torch 2.9+ removed several legacy torchaudio audio-backend APIs (`set_audio_backend`, `list_audio_backends`, `AudioMetaData`); torch 2.6+ flipped `torch.load`'s default `weights_only=True`; huggingface_hub renamed `use_auth_token` → `token`. pyannote 3.x predates all three and its upstream compat release is stuck in review.

Production torch is **2.10** (load-bearing for faster-whisper STT + SpeechBrain ECAPA-TDNN); downgrading torch is forbidden per Session 88 reviewer call — "fighting the ecosystem cascades". pyannote 4.0.x is torchcodec-native but torchcodec 0.11.1 is itself incompatible with torch 2.10 AND requires FFmpeg on Windows.

File-level patches are the community-validated workaround (same pattern used in whisper-webui Docker images).

## 195. Patched Files

| File | Patch | Reason |
|---|---|---|
| `pyannote/audio/core/io.py` | `-> torchaudio.AudioMetaData:` → `-> object:` | Type annotation only; class removed in torchaudio 2.9 |
| `pyannote/audio/core/io.py` | `torchaudio.list_audio_backends()` → `getattr(..., lambda: ['sox_io'])()` | API removed; our audio path is in-memory tensors, not file I/O |
| `pyannote/audio/core/pipeline.py` | `use_auth_token=use_auth_token,` → `token=use_auth_token,` | huggingface_hub kwarg rename |
| `pyannote/audio/core/inference.py` | same kwarg rename | same reason |
| `pyannote/audio/core/model.py` | same kwarg rename × 2 sites | same reason |
| `pyannote/audio/core/model.py` | add `weights_only=False` to `pl_load(...)` + `Klass.load_from_checkpoint(...)` | torch 2.6+ default flip; pyannote checkpoints are HF-gated + license-signed |
| `pyannote/audio/tasks/segmentation/mixins.py` | `from torchaudio import AudioMetaData` → try/except stub | Import must not crash; stub is only hit on training path |
| `pyannote/audio/utils/protocol.py` | same `list_audio_backends()` fallback as io.py | Same cause, different file |
| `speechbrain/utils/torch_audio_backend.py` | same `list_audio_backends()` fallback | SpeechBrain imports torchaudio through pyannote |

## 196. Reapplication Workflow

```
python tests/patch_pyannote_io.py
```

Idempotent — second+ runs write nothing. Re-verify with `python -c "from pyannote.audio import Pipeline; print('ok')"` plus a live-model smoke test. **Mandatory after any `pip install pyannote.audio`** — a library upgrade restores the unpatched source.

## 197. Deprecation Plan

When pyannote 4.x ships a stable torchcodec-native release WITH torchcodec providing torch 2.10+ wheels AND Windows FFmpeg packaging:

- Pin the new version.
- Delete `tests/patch_pyannote_io.py`.
- Remove this Part.

Track via GitHub issue #1974 on pyannote-audio.

**Alternative if patches ever break beyond shim-ability.** SpeechBrain's built-in diarization recipe — already in venv for ECAPA-TDNN. Spectral-clustering, not end-to-end pre-trained like pyannote. Trade-off: ~2–3pp higher DER, cleaner dep surface.

---

# Part XXXII — Voice/Vision Independence and the Reconciler (Phases 1–4)

## 198. Why the Rearchitecture

The pre-rearchitecture pipeline read voice state from inside vision code paths and vision state from inside voice code paths. `_resolve_actual_speaker` was the worst offender — a single 200-line function in `pipeline.py` that simultaneously checked face recognition, voice score, anti-spoof, scene candidates, dispute state, session age, and bootstrap credits, all to decide one thing: "whose session does this turn belong to?"

The cost of that coupling showed up in two specific failure modes:

1. **Silent voice-only stranger drops.** When a person whose face was off-camera spoke a brief phrase ("Hi Kara"), the routing logic's offscreen-floor anti-poisoning rule and the multi-segment-mismatch rule could BOTH match the same input — the cascade had no defined order, the first match won, and which rule "won" depended on import order. In live multi-party sessions this manifested as Lexi-class scenarios where a new speaker was attributed to the current holder for several turns until something else (face entering frame, longer utterance) broke the tie.
2. **Vision changes silently changing voice behavior.** A code edit to fix anti-spoof flicker would alter the timing of `_persons_in_frame` writes, which would in turn change the order in which `_resolve_actual_speaker` saw signals. Vision tests would pass but voice routing would silently degrade. We caught a half-dozen of these in 2026-04 through 2026-05; they were always hard to diagnose because the test suite couldn't isolate the bug to a single channel.

The architectural goal of `VOICE_VISION_INDEPENDENCE_PLAN.md` was to make voice and vision *truly independent*: each channel produces a structured claim about what it observed, and a separate **reconciler** module integrates the two claims into a routing decision. No channel reads the other's state. The reconciler is the only place where cross-channel logic lives.

This is shipped, in production, as of Session 122 (2026-05-01).

## 199. `voice_channel.py` — Pure Speaker Identification

`core/voice_channel.py` exposes one function: `identify_speaker(audio_buf, voice_gallery, *, utterance_duration, ...) -> IdentityClaim`.

The function is *pure* in the architectural sense:
- No imports from `pipeline.py`. (`grep "from pipeline" core/voice_channel.py` → empty.)
- No reads of any vision state, session state, or pipeline globals.
- No calls to `_face_in_frame`, `_persons_in_frame`, `_active_sessions`, etc.
- Returns a frozen `IdentityClaim` dataclass; never mutates shared structures.

The `IdentityClaim` shape:

```python
@dataclass(frozen=True)
class IdentityClaim:
    pid:                  Optional[str]      # matched person_id, or None
    confidence:           float              # ECAPA cosine similarity (CAN BE NEGATIVE)
    n_diarize_segments:   int                # 1 = single speaker; 2+ = multi-voice
    utterance_duration:   float              # seconds of actual speech
    reasoning:            str                # human-readable diagnostic
    raw_segment_scores:   tuple[tuple[Optional[str], float], ...] = ()
```

The hard rule (encoded in the module docstring): *if `identify_speaker` ever needs visual context to make a decision, that's a bug.* The function's only job is to describe what it heard. Routing decisions belong in the reconciler, not here.

The pipeline layer was rewritten to assemble the inputs (`audio_buf`, `voice_gallery`, `utterance_duration`) and call the function. Everything else — choosing whether to open a new session, whether to switch sessions, whether to drop the turn — moved to the reconciler.

## 200. `vision_channel.py` — Pure Scene Observation

`core/vision_channel.py` exposes one function: `observe_scene(...) -> PresenceState`.

Same architectural rules as the voice channel: no pipeline imports, no voice-state reads, no mutation of shared structures.

The `PresenceState` shape:

```python
@dataclass(frozen=True)
class PresenceState:
    visible_pids:               tuple[str, ...]    # face-recognized persons in frame
    unrecognized_track_ids:     tuple[str, ...]    # SORT tracks without recognition
    per_pid_confidence:         dict[str, float]   # face_match_conf per visible pid
    timestamp:                  float = 0.0        # frame timestamp
```

The vision channel emits *what is currently visible*, not *what was visible 30 seconds ago*. Stale state expiry happens upstream, before the channel is called. The reconciler's job is to act on the snapshot it gets.

A throttled shadow log in `_background_vision_loop` (once per 5 seconds) emits `[VisionChannel-Shadow] divergence:` lines when the new channel's `visible_pids` set differs from the legacy `_persons_in_frame` face-source entries. Used during the rollout to verify behavioral equivalence; kept on as a cheap regression guard.

## 201. `reconciler.py` — The 22-Rule Cascade

`core/reconciler.py` is the integration layer. It exposes one function:

```python
def reconcile(
    claim: IdentityClaim,
    presence: PresenceState,
    session: SessionState,
) -> RoutingDecision:
    ...
```

`SessionState` carries the pipeline's view of currently-open sessions (cur_pid, cur_person_type, n_active_sessions, voice_gallery_sizes, cur_holder_voice_n, now). `RoutingDecision` is the structured output: action ∈ {`current` | `switch_enrolled` | `new_stranger` | `ambiguous` | `short_utterance_skip` | `short_utterance_voice_mismatch` | `multi_segment_voice_mismatch` | `no_action`}, plus the rule that fired and a reasoning string.

Internally, `reconcile` runs a fixed cascade of 22 rules in a deterministic order. Each rule is a pure function that takes `(claim, presence, session)` and returns either `Optional[RoutingDecision]` (matched, here's the decision) or `None` (no match, try the next rule). The first rule that matches wins. If no rule matches, the cascade returns `RoutingDecision(action="no_action", reasoning="no rule matched (degenerate state)")` — a logged escape hatch that should never fire in practice.

The cascade is grouped by priority:

| Priority | Rules | What they handle |
|---|---|---|
| **P0** | `_p0_short_utterance_*`, `_p0_pure_noise_hold_current` | Sub-MIN_UTTERANCE_SECS audio: hard-mismatch drops, ambiguous-zone drops, pure-noise hold-current |
| **P1** | `_p1_confident_voice_switch` | Voice score above SPEAKER_SWITCH_THRESHOLD → confident switch to matched pid |
| **P2** | `_p2_face_assist_switch`, `_p2_voice_face_agree` | Mid-range voice score with face co-presence agreement |
| **P3** | `_p3_self_match_below_floor`, `_p3_above_self_match` | Holder's own voice score relative to self-match floor (poisoning protection) |
| **P4** | `_p4_pyannote_vouched_stranger`, `_p4_new_stranger_low_match`, `_p4_voice_ambiguous_*`, `_p4_single_segment_mismatch`, `_p4_multi_segment_mismatch` | Below-threshold voice scores: open new stranger, drop turn, or hold ambiguous |
| **P5** | `_p5_no_session_new_stranger` | No active session: any real signal opens a stranger session |

The order is intentional and load-bearing. P0 fires before P1 because a 0.4-second utterance scoring 0.85 against the holder is still too short to attribute reliably (the high score is artifactual from acoustic prior rather than identity match). P3's self-match floor fires before P4's mismatch handling because we want "current holder said something quiet" to route differently from "stranger said something we can't match."

Every rule is independently unit-tested. The cascade is integration-tested by passing in pinned `(claim, presence, session)` fixtures captured from real canary failure modes (the negative-cosine bug fixture is one of these — see §202).

## 202. The Negative-Cosine Bug and Why It Mattered

Through Phase 4 cutover (Session 122), four cascade rules used `claim.confidence == 0.0` (exact equality) as a precondition for handling "no enrolled match" cases:

- `_p4_pyannote_vouched_stranger` — pyannote saw 2+ voices, ECAPA didn't match
- `_p4_new_stranger_low_match` — single segment, score below threshold
- `_p4_voice_ambiguous_no_candidates` — ambiguous, empty room
- `_p4_voice_ambiguous_with_candidates` — ambiguous, populated room

The implicit assumption was that on gallery miss, `voice.identify()` returns `(None, 0.0)`. That assumption was *wrong*. The actual behavior of `core.voice.identify`:

```python
def identify(audio, voice_gallery, threshold, sample_rate=MIC_SAMPLE_RATE):
    emb = embed(audio, sample_rate)
    if emb is None or not voice_gallery:
        return None, 0.0   # Only path returning exact 0.0 — embedding failed

    best_id, best_score = None, -1.0
    for person_id, profile_emb in voice_gallery.items():
        sim = float(np.dot(emb, profile_emb))   # cosine sim — CAN BE NEGATIVE
        if sim > best_score:
            best_score = sim
            best_id = person_id

    if best_score >= threshold:
        return best_id, best_score
    return None, best_score   # Returns ACTUAL cosine, often negative
```

ECAPA-TDNN embeddings are L2-normalized. Cosine similarity between two anti-correlated speakers (different gender, accent, register) is routinely *negative* — values like -0.05, -0.08 are normal when an unknown speaker is compared against an enrolled gallery they don't match. Only when the embedding step itself fails does `identify()` return exactly `0.0`.

In the 2026-05-01 5-person canary, this surfaced as: Lexi (unknown speaker) said "Hi Kara, can you tell me what is the escape velocity of Earth?". Pyannote returned 2 segments (correct). ECAPA scored Lexi's voice at -0.05 against Jagan's gallery (correct — definitively not Jagan). Reconciler ran the cascade. Every P4 rule's `confidence == 0.0` precondition failed because confidence was -0.05 not 0.0. No rule matched. Cascade returned `no_action`. Lexi's utterance was silently dropped.

The fix (Session 122):
- `_p4_pyannote_vouched_stranger`: `claim.confidence == 0.0` → `claim.confidence <= 0.0`. Catches both the no-signal case (0.0) and the anti-correlated case (negative).
- `_p4_new_stranger_low_match`: condition rewritten as `claim.confidence < VOICE_RECOGNITION_THRESHOLD AND claim.confidence != 0.0`. Negative scores route to new_stranger; exact-zero (embedding failed) falls through to ambiguous handling.
- `_p5_no_session_new_stranger`: rewritten as "any real signal" — `claim.confidence != 0.0 OR len(presence.unrecognized_track_ids) > 0`.
- The two `_p4_voice_ambiguous_*` rules deliberately kept the `== 0.0` check. Negative is a *confident* "not-this-speaker" signal and routes to new_stranger; exactly 0.0 is "no signal at all" and routes to hold-current or ambiguous depending on scene candidates.

Two new regression tests added: `test_p4_pyannote_vouched_stranger_negative_confidence` and `test_p4_new_stranger_low_match_negative_confidence`. Pinned fixtures from the canary log.

The lesson for future channel work: when a function's return value is "actual cosine similarity," do not assume any particular value (zero, positive, bounded) without verifying the source. ECAPA-TDNN's contract permits negatives; the cascade rules now respect that.

## 203. Phase 4 Cutover and Known Follow-Ups

### 203.1 The cutover flag

`ROUTING_USE_RECONCILER = True` in `core/config.py` (Session 121). When true, `pipeline.run` consumes the reconciler's `RoutingDecision` directly. When false, the legacy `_resolve_actual_speaker` still runs and the reconciler runs in shadow alongside (logging divergences but not driving behavior).

The shadow phase (Phase 3) ran for 48+ hours of normal use before the cutover. The divergence log was empty — every decision the reconciler would have made matched what `_resolve_actual_speaker` made. That's the validation that allowed the flip.

### 203.2 The legacy function is preserved

`_resolve_actual_speaker` in `pipeline.py` still exists. It's unreferenced by the production routing path under `ROUTING_USE_RECONCILER = True`. Phase 5 (cleanup, deferred) will delete it once we have another month of stable reconciler operation.

### 203.3 Test count

The Phase 1–4 work added approximately 40 unit/integration tests for the channels and the reconciler cascade (`tests/test_voice_channel.py`, `tests/test_vision_channel.py`, `tests/test_reconciler.py`). Pre-Phase-1 test count was 1336; post-Phase-4 is 1374.

### 203.4 Known follow-up — voice gallery growth bug for promoted voice-only strangers

Session 94 added bootstrap-credit replenishment so engaged strangers could grow their voice profile to maturity (20 samples). The condition includes `person_type == 'stranger'`. After a voice-only stranger is promoted via `update_person_name` ("My name is Lexi"), the promotion chain flips `person_type` to `known`. The replenishment condition stops firing. Subsequent voice samples are refused with `voice_n=4, bootstrap=0, no witness` because the only paths to accumulation are face-witness (blocked, voice-only), mature-voice-self-match (blocked, below threshold), or bootstrap (blocked, exhausted and no longer eligible).

In the 2026-05-01 canary, Lexi stayed at 4/20 samples and John stayed at 2/20 samples for the full 50-minute session. Voice routing accuracy degrades as a result — every future session they join, they re-enter via switch_enrolled against their stunted profile, can't accumulate, and remain stunted forever.

Fix queued (architect's recommendation: add a `voice_only_origin` session-dict flag set at engagement-gate pass when no face was witnessed; replenishment fires when the flag is True AND voice_n < MATURE, regardless of `person_type`; flag clears on first face-witness event).

### 203.5 Known follow-up — Phase 5 cleanup

Once reconciler operation is stable for ~1 month: delete `_resolve_actual_speaker`, remove voice writes to `_persons_in_frame`, introduce a `_voice_speakers_active: dict` for voice-only presence (replacing the source-tagged dual-purpose use of `_persons_in_frame`).

---

# Part XXXIII — The Pure-Graph Intent Classifier

## 204. Why We Replaced the LLM Classifier

Sessions 76 through 117 iterated on an LLM-based intent classifier — a separate Together.ai call per turn that emitted a structured JSON sidecar (`turn_intent`, `extracted_value`, `confidence`, `reasoning`). The classifier's prompt accumulated complexity (taxonomy rules, counter-examples, INJECTION DEFENSE, GREETING-vs-ASSIGN, IMPLICIT-ADDRESSING) over 30+ live-canary sessions. By Session 117 it was a 3000-token prompt that worked well on Llama-3.3-70B and was load-bearing for production routing decisions (rename gates, shutdown gates, mismatch detection).

Two problems forced the replacement:

**Problem 1 — Model dependence.** A falsifying experiment in 2026-04-27 ran the same classifier prompt on Qwen2.5-7B (a paper-baseline model in Bhagtani et al. 2026). KaraOS-on-Qwen-7B scored 52.32% balanced accuracy on the Friends test set — *2.68pp below* the paper's vanilla Qwen-7B baseline of 55.00%. The 70B was carrying the architectural lift; the prompt complexity overwhelmed the smaller model. The "model-agnostic" public claim was rhetoric, not architecture. Diagnostic detail in `karaos-public/published-papers-tests/results/friends_multi_backbone/MULTI_BACKBONE_RESULTS.md`.

**Problem 2 — Cost and latency.** Every turn made a second Together.ai call (the sidecar) in addition to the brain stream. Per-turn cost roughly doubled. P99 latency grew because the sidecar's response had to arrive before tool gates could be applied.

The replacement architecture, specified in `SPEC_001_classifier_graph.md` (Spec 1, data layer) and `SPEC_002_classify_intent_graph.md` (Spec 2, classification layer), removed the LLM from the classification hot path entirely. No Together.ai call. No Ollama call. No model inference of any kind. Classification became a deterministic graph operation: abstract the input → embed locally → cosine k-NN against a stored scenario database → aggregate label votes. Same output shape as the LLM classifier (turn_intent + extracted_value + confidence + reasoning); zero model dependence.

Run 3 of the Friends benchmark, with this architecture: **64.48% balanced accuracy.** Above Run 1's LLM-classifier number, above the paper's human baseline (63.75%), competitive with the lowest fine-tuned LoRA model (Qwen3-4B-Instruct fine-tuned: 65.12%) — without modifying any model weights, without running gradient descent.

## 205. Spec 1 — Bootstrap and the Scenario Database

The classifier needs a database of labeled scenarios to retrieve against. Spec 1 covers how that database is built, populated, and maintained.

**Source corpora** (the bootstrap inputs):

| Corpus | Rows | Share | Why this corpus |
|---|---:|---:|---|
| Cornell Movie-Dialogs | 968 | 46.8% | Largest single source of multi-party dialogue with explicit speaker turns; broad register coverage |
| DailyDialog | 393 | 19.0% | Closer to casual conversation register; short polite exchanges |
| EmpatheticDialogues | 298 | 14.4% | Adds emotional / vulnerable conversational shapes; therapy-style |
| hand_authored | 412 | 19.9% | KaraOS-specific scenarios written from the development log's bug classes (Sessions 71–117 — the canary failure modes the LLM classifier got wrong) |
| live_correction | (varies) | (small) | Added at runtime via the user-correction loop (§210) |
| **Total active** | **2,071** | **100%** | (snapshot 2026-04-30) |

Friends, AMI, and SPGI (the Bhagtani paper's test corpora) are *deliberately excluded* from bootstrap to preserve test-train integrity. Mixing them in would collapse the benchmark.

**Pipeline shape:**

1. Parse raw corpus → extract dialogue turns with metadata.
2. Filter to "intent-relevant" turns (drop pure-acknowledgment, pure-noise).
3. Pass each candidate turn through a Together.ai classifier prompt (one-shot, JSON-mode, 70B) that assigns one of 12 intent labels.
4. Abstract: replace named entities with placeholders. Names → `{P1}`, `{P2}` (registry-first then spaCy NER fallback). Places → `{LOC}`. Numbers, times, and most concrete content kept intact.
5. Embed via `intfloat/multilingual-e5-large-instruct` — 1024-dim, L2-normalized.
6. Write `scenario_id`, `intent_label`, `text` (abstracted), `embedding`, `source_tag`, plus provenance metadata to `data/classifier_scenarios.db`.
7. Quality pass: drop scenarios where the LLM's confidence was below threshold; deduplicate near-identical embeddings.

The bootstrap is a one-time-ish operation. Re-running it from scratch costs ~$5-15 in Together.ai spend. The seed JSONL (everything in step 6 except embeddings, which can be regenerated locally) is published at `karaos-public/published-papers-tests/classifier-seed/seed.jsonl` — 2,081 rows, ~780KB, no PII, with full source attribution.

## 206. `classifier_db.py` — Schema and Audit

`core/classifier_db.py` is the read/write layer over `data/classifier_scenarios.db`.

**Core table — `scenarios`:**

```sql
CREATE TABLE scenarios (
    scenario_id           TEXT PRIMARY KEY,
    intent_label          TEXT NOT NULL,
    text                  TEXT NOT NULL,             -- abstracted
    embedding             BLOB NOT NULL,             -- 1024-dim float32
    source_tag            TEXT NOT NULL,             -- cornell / dailydialog / empathetic_dialogues / hand_authored / live_correction
    source_version        TEXT,                       -- for re-bootstrap reproducibility
    source_ref            TEXT,                       -- pointer back to original corpus row
    initial_confidence    REAL DEFAULT 0.5,
    confirmation_count    INTEGER DEFAULT 0,
    contradiction_count   INTEGER DEFAULT 0,
    active                INTEGER DEFAULT 1,         -- 0 = quarantined
    created_at            TEXT NOT NULL,
    last_seen_at          TEXT,
    extracted_value       TEXT                        -- new in Spec 2 — captured slot value when present
);
```

`active = 0` means quarantined: the scenario stays in the DB for audit but is excluded from retrieval. This is how the system removes bad-influence scenarios without losing them entirely. Quarantine is currently triggered manually; auto-quarantine is part of Phase 3 of the multi-layer roadmap (§228).

**Audit log — `audit_log` (JSONL append-only):**

Every mutation — scenario creation, confirmation, contradiction, quarantine, reactivation, label change — appends a JSON row. This file is intentionally separate from the SQLite DB so it survives DB corruption and can be reasoned about externally.

**Schema versioning:** `schema_migrations` table tracks every applied migration. Additive migrations only; no destructive schema changes.

**Daily snapshots:** `data/classifier_snapshots/YYYY-MM-DD.db` — automatic daily backups, 30-day retention. If a bug causes corruption, restore from the previous day.

## 207. Spec 2 — `classify_intent_graph()` Anatomy

`core/classifier_graph.py` exposes `classify_intent_graph(text: str, history: list = None, ...) -> dict`. The function returns the same shape as the legacy LLM classifier (`turn_intent`, `extracted_value`, `confidence`, `reasoning`) so it's a drop-in replacement at call sites.

**Internal flow:**

```
classify_intent_graph(text="Hey Kara, what's the weather?")
   │
   ▼
1. abstract(text)
   │   "Hey {P0_AI_NAME}, what's the weather?"
   │   (registry-first replacement: known person/AI names; then spaCy NER for unmatched)
   ▼
2. embed(abstracted_text)
   │   → 1024-dim float32 vector via E5-large-instruct (local on GPU)
   ▼
3. classifier_db.cosine_topk(query_embedding, k=10)
   │   → top 10 nearest scenarios by cosine similarity (brute-force; no ANN index yet)
   ▼
4. Wilson lower-bound aggregation over the top-K
   │   → for each unique intent_label in top-K, compute Wilson score
   │     using confirmation_count / (confirmation_count + contradiction_count)
   │     adjusted by initial_confidence + similarity weight
   ▼
5. Return {"turn_intent": best_label, "confidence": wilson_score, ...}
```

The whole flow is deterministic — same input + same DB state → same output, every time. The only randomness sources are E5's tokenizer (deterministic given inputs) and SQLite's row order (we sort explicitly to remove ambiguity).

**Abstraction step in detail.** The two-pass abstraction in `core/abstraction.py`:
- **Pass 1 — Registry.** Look up known persons (best_friend, household members, current session participants) and the AI name; replace exact matches with `{P0_AI_NAME}`, `{P_LEXI}`, etc. This is the high-precision pass.
- **Pass 2 — spaCy NER.** Run spaCy's `en_core_web_sm` model on the remaining text. Replace entities tagged `PERSON` with `{PN}` placeholders, `LOC`/`GPE` with `{LOC}`. Times, numbers, and percentages stay unabstracted (they carry intent-relevant signal — "shut down at 5pm" is different from "shut down" alone).

The `{P0_AI_NAME}` placeholder is a deliberate stable token. When the user changes the AI's name from "Kara" to "Atlas", queries about "Atlas" still match against scenarios stored as `{P0_AI_NAME}, what's the weather?` — the system is name-agnostic.

## 208. Three Modes — `shadow`, `primary`, `retired`

Controlled by the `GRAPH_CLASSIFIER_MODE` config flag in `core/config.py`. Three values:

**`shadow` (current default).** Both classifiers run in parallel on every turn. The LLM classifier drives behavior — its output is what tool gates consume. The graph classifier runs alongside, logs its prediction via `[Intent] shadow divergence: graph='X' (conf=0.43) vs llm='Y' (conf=0.95)` when the two disagree, and writes nothing to production state. This is the validation phase: we accumulate divergence data to calibrate the graph's reliability before flipping production over.

**`primary`.** Graph classifier drives behavior. LLM classifier still runs as a fallback for low-graph-confidence cases (`graph_confidence < GRAPH_PRIMARY_CONFIDENCE_FLOOR`, default 0.55). When graph is confident, we use it; when not, fall back to LLM. This intermediate mode lets us fail-safe through the rollout.

**`retired`.** Graph classifier drives behavior. LLM classifier is not called. If the graph abstains (confidence below `GRAPH_ABSTAIN_THRESHOLD`, default 0.40), the gate code falls back to default-silent behavior. This is the steady-state target.

The cutover discipline mirrors the voice/vision rearchitecture: **never all-at-once.** Ship in shadow, observe divergences for 1-2 weeks of live use, target <5% divergence rate on routine traffic before flipping to primary. Primary mode validates over weeks before flipping to retired. The old `_classify_intent` LLM classifier stays in the repo as the safety net during primary mode.

**Current status (2026-05-02):** mode is `shadow`. The 2026-05-01 canary captured 15 shadow divergences over ~50 minutes of multi-party conversation. In every divergence, the LLM classifier was right and the graph classifier was wrong (graph confidences ranged 0.41-0.68; LLM confidences ranged 0.85-0.95). This tells us the graph is genuinely uncertain on these cases and the architecture is doing the safe thing. The graph isn't yet ready for primary mode — calibration is too low. The multi-layer architecture work (Part XXXV) is what's expected to close this gap.

## 209. Wilson Lower-Bound Aggregation

The aggregation step in `classify_intent_graph` doesn't take a simple top-K majority vote. It uses **Wilson lower-bound** scoring for each candidate label.

**Why.** A scenario with 1 confirmation and 0 contradictions has empirical confirmation rate 1.0 — but that's based on a single observation. Should it count more than a scenario with 50 confirmations and 5 contradictions (rate 0.91)? Naive majority vote says yes; Wilson lower-bound says no.

**The formula** (95% confidence interval, lower bound):

```
n = confirmation_count + contradiction_count
p = confirmation_count / n   if n > 0 else initial_confidence
z = 1.96   (95% CI)
denominator = 1 + z²/n
center     = p + z²/(2n)
margin     = z * sqrt(p*(1-p)/n + z²/(4n²))
wilson_lower = (center - margin) / denominator
```

When n is small, the margin term dominates and `wilson_lower` is pulled toward 0 even if `p = 1.0`. This is the "small sample, low confidence" effect that makes the system robust against single-confirmation events skewing the graph.

**In aggregation:**
- Top-K = 10 nearest scenarios.
- For each unique `intent_label` in top-K, sum the (similarity × wilson_lower) contributions across all matching scenarios.
- Best label wins; its summed weight becomes the classifier's `confidence` output.

Scenarios with no outcome data (`confirmation_count == 0 AND contradiction_count == 0`) use `initial_confidence` as a smoothed prior — typically 0.5 or 0.85 depending on source (hand-authored: 0.85; bootstrap-LLM-classified: 0.5). This prevents fresh scenarios from getting zero weight just because they haven't been validated yet.

## 210. The Correction Loop and Why It's Currently Dormant

The classifier graph has a designed-in mechanism for users to teach it: explicit corrections.

**The flow:**
1. Brain emits a response based on the classifier's intent prediction.
2. User says something matching a correction pattern: "no, I meant to say X", "I was talking to Lexi, not you", "no actually...".
3. `core.classifier_graph.handle_correction(text)` parses the correction and looks up the previous turn's prediction via `_pending_outcomes` (a deque of recent decisions awaiting outcome).
4. The scenarios that voted for the wrong label on turn N-1 get their `contradiction_count` incremented.
5. If a real correction *target* (e.g. "Lexi") is extracted from the user's correction phrase, a new scenario is INSERTED into the DB:
   - `text` = the original turn N-1 text, re-abstracted with the target's role baked in
   - `intent_label` = `direct_address_to_person`
   - `source_tag` = `live_correction`
   - `initial_confidence` = 0.85
6. The pipeline returns `("continue", None)` early — no brain response. (The user shouldn't get an apology. They corrected the AI; the AI internalizes silently.)

**Pattern bank.** `_DEFAULT_CORRECTION_PATTERNS_TEMPLATE` in `classifier_graph.py` contains ~14 regex patterns covering shapes like:
- "no, I meant X"
- "I was talking to X, not you"
- "you, not X"
- "I meant ask X"

**Why it's currently dormant.** The 2026-05-01 5-person canary log: zero corrections fired across ~50 minutes of conversation. Multiple instances where a user *did* correct the AI in natural speech ("no, ask Jagan about that") didn't match any of the 14 regex patterns and so didn't trigger the correction loop. The correction-detection regex bank is too narrow for natural correction phrasings.

Real-world correction patterns include things like:
- "actually, ..."
- "no, ..."
- "I meant ..." (without "no")
- Repeating the question with a different addressee in the next turn
- "wait, ..."
- Implicit corrections (the user just rephrases the question without acknowledging the mistake)

Broadening the regex bank is part of Phase 2 of the multi-layer roadmap (§225). Mining the canary archive logs for natural correction phrasings is the data-driven approach.

## 211. Outcome Supervision — The Dead Code Path

Spec 2 includes a second learning signal beyond explicit corrections: **outcome supervision**. The idea is that when a tool fires successfully (e.g. `update_person_name` accepts a rename and the user doesn't correct it within 3 turns), the scenarios that voted for that intent should get `confirmation_count` incremented. When a tool gets rejected by content/intent gates, scenarios get `contradiction_count` incremented.

The infrastructure exists. `core.classifier_graph` exposes:
- `record_pending_outcome(decision_id, scenarios_that_voted)` — call when a decision is made
- `confirm_pending(decision_id)` — call N turns later if the decision was right
- `revert_pending(decision_id)` — call N turns later if the decision was wrong
- `age_pending_outcomes()` — sweep expired entries (3-turn window, currently)

**The pipeline does not call `confirm_pending` or `revert_pending` anywhere in production.** The `decision_id` returned by `record_pending_outcome` is discarded immediately. The 3-turn aging window expires every entry without supervision.

This is dead code. It's not removed because it's the planned wiring point for Phase 2 of the multi-layer roadmap (§225). Wiring it up correctly requires disambiguating four classes of tool rejection:

| Rejection class | Signal for graph |
|---|---|
| Intent gate (classifier said wrong intent) | NEGATIVE (graph was wrong) |
| Privilege gate (intent right, person not authorized) | POSITIVE (graph was right) |
| Repeat guard (intent right, LLM looping) | POSITIVE (graph was right) |
| User-text grounding (extracted_value not in user_text) | NEGATIVE (graph was wrong) |

The pipeline currently logs all four through the same `[Pipeline] Tool: X REJECTED` channel with different reason strings. Disambiguating them is a 1-2 session refactor. After that, outcome supervision can be wired and the graph starts learning from real production usage.

## 212. E5 Embeddings — Local on GPU

The classifier uses `intfloat/multilingual-e5-large-instruct` — a 1024-dim multilingual embedding model from Microsoft Research / E5 series.

**Why this model:**
- Multilingual (the system is currently English-only but the architecture is language-extensible)
- Instruction-tuned (handles "represent this query for retrieving similar dialogue scenarios" prompting cleanly)
- L2-normalized output (cosine similarity reduces to dot product — fast)
- ~1.4GB on disk; ~3.9s to load on consumer GPU; ~50ms per inference after warmup
- Permissive license (commercial-OK, attribution)

**Loading.** Lazy at first call. The Spec 2 contract was "local on GPU" — `_get_e5_model()` checks for `cuda` availability and loads with `device="cuda"`. Falls back to CPU only if no GPU is available (degraded; not a production target).

**Boot warmup.** The first inference call after model load takes ~4.6 seconds (vs. ~50ms steady state) because of CUDA kernel initialization, tokenizer warmup, and model graph trace. The architecture commitment is to do this warmup at pipeline boot — not on the first user turn — so the first conversation never sees the cold-load penalty. Status: queued for the same fix bundle as the voice-gallery-growth fix.

**Embedding determinism.** E5 is deterministic given identical input bytes. We don't seed any randomness in the inference path. The same query produces the same embedding every call.

## 213. Privacy and Abstraction at the Embedding Layer

The classifier never sees real names, real places, or other PII at the embedding layer. The abstraction step (§207) replaces all of those with placeholders before embedding. This is a privacy invariant the architecture enforces structurally:

- The `data/classifier_scenarios.db` file contains only abstracted text. If you `SELECT text FROM scenarios LIMIT 100`, you'll see strings like `"{P0_AI_NAME}, can you tell me about {LOC}?"` — not "Kara, can you tell me about Tirupati?".
- The `seed.jsonl` published in `karaos-public/` contains only abstracted text. It's distributable as a public artifact without PII review because there's no PII in it.
- Every `live_correction` scenario added at runtime goes through the same abstraction step before being written.

The abstraction is *not* a security boundary — a determined attacker who could read the DB and the registry could potentially de-abstract some entries. It is a privacy-by-default discipline that makes accidental PII leakage structurally impossible at the embedding layer.

## 214. Latency Profile and the Boot-Warmup Decision

Per-turn classifier latency breakdown (steady state, post-warmup):

| Stage | Time | Notes |
|---|---|---|
| Abstraction (registry + spaCy NER) | ~5ms | spaCy `en_core_web_sm` is small and fast |
| Embedding (E5 on GPU) | ~50ms | Single 1024-dim vector |
| Cosine top-K against ~2,071 scenarios | ~3ms | Brute-force; no ANN index |
| Wilson aggregation | <1ms | Top-10 sum of weights |
| **Total steady-state** | **~60ms** | |

**Cold start** (first inference after pipeline boot):

| Stage | Time | Notes |
|---|---|---|
| E5 model load to GPU | ~3.9s | One-time per process |
| First embedding call (kernel init) | ~700ms | CUDA warmup |
| **Total cold start** | **~4.6s** | The first user turn after pipeline boot eats this |

The architectural decision: warm at boot. Add `_classify_intent_graph` to the pipeline's preload sequence (after Whisper, Kokoro, ECAPA, MiniFASNet, EmotionAgent). Make one dummy call with a sentinel input. The user's first conversation never sees the cold-load penalty.

This fix is queued in the same bundle as the voice-gallery-growth fix (§203.4) and the session-end classifier summary log (which adds module-level counters and a shutdown-time summary line for retrieval count, divergence count, correction count, etc.).

After warmup is in place, the per-turn 60ms cost is invisible — it overlaps with the brain stream's much larger latency (TTFT ~500ms+ for the brain stream itself).

---

# Part XXXIV — External Benchmark Validation

## 215. The Bhagtani et al. 2026 Paper and the Friends Test Set

The benchmark KaraOS is validated against:

> **Bhagtani, K., Anand, M., Xu, Y. C., & Yadav, A. K. S. (2026). *Speak or Stay Silent: Context-Aware Turn-Taking in Multi-Party Dialogue*. arXiv:2603.11409.**

The paper's question: in a multi-party conversation, given the recent history and a target speaker, will that speaker take the next turn (`SPEAK`) or will someone else (`SILENT`)? The paper benchmarks zero-shot LLMs (GPT-5.2, Gemini-3.1-Pro, Llama-3.1-8B, Qwen2.5-7B, Mistral-7B-Instruct, etc.), human judges, and LoRA-fine-tuned variants of the smaller models.

The test set we use is `friends/test/test_samples.jsonl` from the paper's released dataset — 1,287 samples drawn from the Friends sitcom corpus.

**Why Friends.** The Friends benchmark is heavy on `SPEAK_explicit` cases — situations where the target speaker is directly addressed by name ("Hey Ross, did you see the game?"). KaraOS's architecture targets exactly that case: explicit name-vocative addressing as the primary "should I speak?" signal. Friends is therefore the in-scope domain for KaraOS validation. AMI (workplace meetings) and SPGI (earnings calls) are in the paper but out-of-scope for KaraOS by design — they test implicit-flow turn-taking, which KaraOS's architecture deliberately doesn't target.

**The metric.** Balanced accuracy — `(recall_SPEAK + recall_SILENT) / 2`. Robust to class imbalance. The paper reports it; every comparison table in the public repo uses it.

**Test integrity.** Friends was strictly held out from the bootstrap data. Cornell + DailyDialog + Empathetic + hand_authored — none of those touch Friends. The graph classifier's retrieval pool has zero Friends contamination.

## 216. Run 1 — LLM Classifier on Llama-70B (58.66%)

**The system under test:** the Sessions-76-through-117 LLM-classifier path. Same prompt as production at the time, no test-specific tuning. Backbone: Llama-3.3-70B-Instruct-Turbo via Together.ai.

**Result:** 58.66% balanced accuracy on 1,287 Friends test rows.

| Category | Accuracy | n |
|---|---:|---:|
| `SILENT_no_ref` | 100.0% | 173 |
| `SILENT_ref` | 96.7% | 483 |
| `SPEAK_explicit` | 46.4% | 220 |
| `SPEAK_implicit` | 3.2% | 411 |

**Where this places KaraOS in the paper's table.** Above 7 of 8 zero-shot LLM baselines (Qwen3-8B 50.70%, Qwen3-4B 51.48%, Mistral-7B 52.87%, Llama-3.1-8B 54.21%, Qwen2.5-7B 55.00%, GPT-5.2 55.41%, GPT-OSS-20B 55.92%); below Gemini-3.1-Pro (60.54%) and the human baseline (63.75%); below all fine-tuned LoRA variants.

**This is the original public number.** It's what the LinkedIn video post and the original ARCHITECTURE.md cited. The number is real. What was wrong was the *interpretation* — the public claim "model-agnostic by design" did not survive the next experiment.

**Predictions file:** `karaos-public/published-papers-tests/results/friends_baseline_full_db/predictions_llama_70b.json`. Loadable by the paper's `metrics.py:compute_metrics()`; reproduces 58.66% to within rounding.

## 217. Run 2 — Multi-Backbone Falsifying Experiment (Qwen-7B, 52.32%)

**The setup.** Same KaraOS classifier prompt as Run 1 — verbatim, no changes. Different LLM backbone: Qwen2.5-7B-Instruct-Turbo via Together.ai. The paper benchmarks vanilla Qwen2.5-7B at 55.00% zero-shot. The falsifying question: does KaraOS's architecture lift Qwen-7B above 55.00%? If yes, the architecture is contributing real signal. If no, the original 58.66% was the 70B model carrying it.

**Result:** **52.32%** balanced accuracy. **2.68pp BELOW** the paper's vanilla Qwen-7B baseline.

The architecture didn't lift the smaller model — it actively *hurt* it.

| Category | Qwen-7B | Llama-70B | Δ |
|---|---:|---:|---:|
| `SILENT_no_ref` | 100.0% | 100.0% | 0.0pp |
| `SILENT_ref` | 98.8% | 96.7% | +2.1pp |
| `SPEAK_explicit` | **14.5%** | 46.4% | **-31.8pp** |
| `SPEAK_implicit` | 0.7% | 3.2% | -2.5pp |

The damage was concentrated in `SPEAK_explicit` — exactly the category KaraOS was supposedly best at. Qwen+KaraOS caught only 32 of 220 directly-addressed cases that Llama+KaraOS caught 102 of.

**Diagnosis.** The KaraOS classifier prompt had been tuned for 30+ live-canary sessions on Llama-3.3-70B and accumulated reasoning surface (taxonomy rules, counter-examples, INJECTION DEFENSE, structured-output contracts) that the larger model could absorb but the smaller one couldn't. Under prompt load, Qwen defaulted to `casual_conversation` even on samples with clear vocatives. Recall collapsed from 18.3% to 5.5% on overall SPEAK.

**This is a falsifying experiment that worked.** The "model-agnostic" public claim was rhetoric; the falsifier exposed it; the response was to redesign the architecture to be *structurally* model-agnostic. That redesign is the graph classifier.

**Limitation acknowledged.** The original spec called for three smaller backbones (Qwen-7B, Llama-3.1-8B, Mistral-7B) to give a stronger statistical case. Together.ai serverless access only allowed one (Qwen-7B). The collapse from 3-backbone to 1-backbone study is documented in `MULTI_BACKBONE_RESULTS.md`. N=1 is weaker than N=3, but the magnitude of the gap (collapse to *below* a paper baseline used as a low-end reference) makes the qualitative result well-supported.

**Predictions file:** `karaos-public/published-papers-tests/results/friends_multi_backbone/qwen_7b_predictions.json`. The result was published verbatim — uncomfortable findings don't get hidden.

## 218. Run 3 — Graph Classifier (64.48%)

**The system under test:** the Spec 2 graph classifier (`core.classifier_graph.classify_intent_graph`). No LLM in the classification path. Full 2,071-scenario production DB. E5 embeddings. Wilson aggregation.

**Result:** **64.48%** balanced accuracy on the 1,287 Friends test rows. Deterministic — same DB state, same number every run.

| Metric | Value |
|---|---:|
| Balanced accuracy | **64.48%** |
| `SPEAK` precision | 80.21% |
| `SPEAK` recall | 15.19% |
| `SILENT` precision | 54.16% |
| `SILENT` recall | **96.39%** |
| Macro F1 | 47.45% |

**Where this places KaraOS now.** Above the human baseline (63.75%). Competitive with the lowest fine-tuned LoRA variant (Qwen3-4B-Instruct fine-tuned: 65.12%, Qwen2.5-7B fine-tuned: 66.60%). And — this is the load-bearing part — the score *doesn't depend on which LLM is the conversation brain anymore*. The classifier makes zero LLM calls. Replace Llama-70B with Qwen-7B with GPT-5 with Gemini and Run 3's score stays at 64.48%, because the brain isn't involved in classification.

**The "no fine-tuning" honesty disclosure.** KaraOS does not modify model weights. It does not train LoRA adapters. It does not run gradient descent. The brain LLM ships as-is. KaraOS *does* use ~2,000 labeled scenarios as a retrieval corpus. This is **non-parametric learning** — distinct from fine-tuning, but it IS labeled training data, and the public framing acknowledges that explicitly. Both KaraOS and the paper's fine-tuned approaches use labeled data; the techniques and scales are different (paper: 120,000+ rows + LoRA training; KaraOS: ~2,000 + retrieval lookup).

**Predictions file:** `karaos-public/published-papers-tests/results/friends_baseline_full_db/predictions_graph_classifier.json`.

## 219. The 10-Run Scaling Ablation and the Inverse-Scaling Finding

**Origin.** Amit Yadav (paper co-author, Fern team lead) commented on Jagan's LinkedIn post about the Run 3 result, asking two ablation questions:

1. Does accuracy change with the number of abstracted scenarios?
2. What's the standard deviation across multiple runs with random subsets?

**Setup.** 10-run study, fully isolated from production:

- Stratified random subsets of the production DB at N=500, 1000, 1500 (3 random seeds each).
- Plus the deterministic full-DB run at N=2071.
- Stratification preserves the source-corpus ratio (Cornell 46.8%, DailyDialog 19.0%, Empathetic 14.4%, hand-authored 19.9%) at every N. No corpus over- or under-represented.
- Read-only access to the production DB. Override classifier path via `CLASSIFIER_DB_PATH_OVERRIDE` env var. Production DB mtime unchanged after the suite. Audit log unchanged. Zero production code edits.

**Result — inverse scaling.**

| N | Mean balanced acc | Std dev | Range |
|---|---:|---:|---|
| 500 | **0.6919** | ±0.0261 | [0.6644, 0.7270] |
| 1000 | 0.6835 | ±0.0075 | [0.6731, 0.6907] |
| 1500 | 0.6677 | ±0.0026 | [0.6646, 0.6709] |
| 2071 | 0.6448 | — | (deterministic) |

**The curve is monotonically decreasing.** Adding more scenarios *hurts* accuracy. The full DB scores 6.5pp below the best 500-scenario subset.

**Variance collapses as N grows.** ±2.6pp at N=500 → ±0.26pp at N=1500. The trend isn't a sampling artifact; it's robust.

**The proposed diagnosis.** k-NN cosine retrieval over heterogeneous-quality bootstrap data has a saturation point. At N=500 the retrieval pool is dense with high-signal scenarios per query. At N=2071 the pool includes lower-quality scenarios (mislabeled by the bootstrap LLM, too generic to discriminate, distribution-mismatched to Friends sitcom style) that crowd into top-K with confident-but-wrong votes.

**The open question — corpus-specific or fundamental?** Two competing explanations:

- **Friends-specific.** Cornell movie scenes (47% of bootstrap) are dramatic-style; they may match Friends queries by surface similarity but vote for wrong labels. AMI ablation would distinguish: AMI is closer to Cornell-style register, so we'd expect AMI's curve to flatten or improve with N.
- **Fundamental.** k-NN over noisy bootstrap data has this property regardless of test corpus. AMI would also show inverse scaling.

**AMI ablation queued.** Same 10-run shape, AMI test set. Cleanest experiment to disentangle the two explanations. Not yet run as of 2026-05-02.

**The architectural response.** Inverse scaling is what motivates the multi-layer roadmap (Part XXXV). Per-scenario learned reliability (Layer 1) plus auto-quarantine (Layer 5) directly attack the "noisy scenarios crowd into top-K" mechanism. Hierarchical retrieval (Layer 3) attacks the "wrong-corpus scenarios match by surface similarity" mechanism.

**Files.** Full data + methodology + isolation contract at `karaos-public/published-papers-tests/results/friends_scaling_ablation/`. 10 individual run JSONs, 10 individual run summaries, aggregate stats, README, METHODOLOGY, ABLATION_RESULTS.

## 220. The AMI 10-Row Smoke and Out-of-Scope Disclosure

A 10-row smoke test of KaraOS's classifier on the AMI test set was run and published — not as a result we're claiming, but as honest evidence of architectural mismatch.

**Result.** KaraOS predicted `SILENT` on all 10 rows. Per-class:

| Class | Count | Recall |
|---|---:|---:|
| Ground-truth `SPEAK` | 8 | 0.0% (0/8) |
| Ground-truth `SILENT` | 2 | 100.0% (2/2) |
| **Balanced accuracy** | — | **50.0%** |

**Why.** AMI samples are categorized primarily as `SPEAK_implicit` — the next speaker takes a turn without being directly addressed. KaraOS's architecture deliberately defaults to silence on those cases. Architectural target = explicit name-vocative addressing. AMI ≠ explicit-addressing. KaraOS is not designed to perform on AMI; the smoke test confirms it doesn't.

**Why it's published.** Silently omitting an unflattering result violates the public-repo principle of "no fake or padded data." Researchers reproducing KaraOS will want to know AMI is out-of-scope before they run it themselves and conclude something is broken.

**Files.** `karaos-public/published-papers-tests/results/ami_baseline/`. README documents the architectural mismatch. `result_summary.md` documents the 10-row scope. Predictions file is reproducible.

## 221. The `karaos-public` Repository Layout

The benchmark journey, prediction files, methodology docs, and live session logs are public at:

> https://github.com/HungryFingerss/KaraOS

Layout under `published-papers-tests/results/`:

```
results/
├── README.md                           ← test-by-test index
├── RESULTS.md                           ← full benchmark journey narrative
├── friends_baseline_full_db/            ← Run 1 (Llama-70B, 58.66%) + Run 3 (graph, 64.48%)
├── friends_multi_backbone/              ← Run 2 (Qwen-7B, 52.32% — falsifying experiment)
├── friends_scaling_ablation/            ← 10-run scaling study
│   └── individual_runs/                 ← all 10 per-run summaries + JSONs
└── ami_baseline/                        ← AMI smoke test (out-of-scope disclosure)
```

Each folder is fully self-contained: a README explaining what + why, METHODOLOGY explaining how, result narrative, raw prediction JSONs that any researcher can re-score with the paper's `metrics.py`.

The `terminal-logs/` folder at the root contains live KaraOS session logs:
- `2026_04_26_demo.md` — first public demo, single user, the LinkedIn video session
- `2026_05_01_multi_convo_canary.md` — 5-person canary, all participants consented to publication

The `classifier-seed/seed.jsonl` (~780KB) ships the full bootstrap data — 2,081 abstracted scenarios with labels and source attribution. No PII. Researchers can reproduce the full classifier from this seed plus the bootstrap pipeline.

**Honesty discipline:** every uncomfortable finding is published with diagnosis attached. The multi-backbone collapse, the inverse scaling, the AMI mismatch, the safety-critical contradiction-replacement bug from Session 105, the voice-gallery-growth bug — all in the open. The discipline isn't "publish only flattering results." It's "publish what you found and tell the truth about what it means."

---

# Part XXXV — Multi-Layer Classifier Architecture (FUTURE WORK)

## 222. Why This Is the Next Step

The Run 3 graph classifier scored 64.48% on Friends — better than Run 1, better than Run 2, structurally model-agnostic. The 10-run ablation revealed a real limitation: **adding more scenarios HURTS accuracy on Friends**. Inverse scaling. Variance collapses cleanly as N grows, so the trend is robust. The full 2,071-scenario DB scores 6.5pp below the best 500-scenario subset.

The user-stated goal for KaraOS is *"the brain for humanoid robots."* This means:
- Dump 10k+ scenarios into the system over time.
- The classifier should *not* degrade as N grows.
- The classifier should automatically filter low-quality scenarios from the retrieval pool.
- The architecture should learn from real production usage without human curation.
- Latency must stay bounded even at scale.
- When uncertain, abstain. Never vote with garbage.
- **Stay non-parametric.** Zero LLM in the classification path. Forever.

The Run 3 architecture meets some of these. It does *not* meet "scale-invariance" or "garbage immunity." The 10-run ablation directly disproves that property.

The multi-layer architecture is the engineering response. Six layers, four phases, each layer's purpose specified, each phase's deliverable defined. The end state is a retrieval system where adding 10k scenarios is *additive* (or at worst neutral), not destructive.

This Part is the architectural commitment, not the implementation. None of this has shipped. It's the explicit roadmap for the next ~3-6 months of classifier work.

## 223. The Six-Layer Architecture at a Glance

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│   Layer 6 — Provenance and lineage tracking                     │
│   (every retrieval is auditable)                                │
│                                                                 │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │                                                         │   │
│   │   Layer 5 — Active quality gating + auto-quarantine     │   │
│   │   (bad scenarios get filtered out automatically)        │   │
│   │                                                         │   │
│   │   ┌─────────────────────────────────────────────────┐   │   │
│   │   │                                                 │   │   │
│   │   │   Layer 4 — Multi-aspect scenario representation │   │   │
│   │   │   (each scenario annotated on multiple axes)    │   │   │
│   │   │                                                 │   │   │
│   │   │   ┌────────────────────────────────────────┐    │   │   │
│   │   │   │                                        │    │   │   │
│   │   │   │   Layer 3 — Hierarchical retrieval +   │    │   │   │
│   │   │   │   adaptive K + distance-weighted vote  │    │   │   │
│   │   │   │   (better routing of queries)          │    │   │   │
│   │   │   │                                        │    │   │   │
│   │   │   │   ┌─────────────────────────────────┐  │    │   │   │
│   │   │   │   │ Layer 2 — Outcome supervision   │  │    │   │   │
│   │   │   │   │ (the learning signal)           │  │    │   │   │
│   │   │   │   │                                 │  │    │   │   │
│   │   │   │   │ ┌────────────────────────────┐  │  │    │   │   │
│   │   │   │   │ │ Layer 1 — Per-scenario     │  │  │    │   │   │
│   │   │   │   │ │ learned reliability scores │  │  │    │   │   │
│   │   │   │   │ │ (TP/FP/net contribution)   │  │  │    │   │   │
│   │   │   │   │ └────────────────────────────┘  │  │    │   │   │
│   │   │   │   └─────────────────────────────────┘  │    │   │   │
│   │   │   └────────────────────────────────────────┘    │   │   │
│   │   └─────────────────────────────────────────────────┘   │   │
│   └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

Layers are stacked, not parallel. Layer 1 is the foundation. Layer 2 generates the data Layer 1 uses. Layer 3 consumes Layer 1's data to make better routing decisions. Layer 5 uses Layer 1's data to remove bad scenarios. Layer 6 logs everything for audit.

## 224. Layer 1 — Per-Scenario Learned Reliability

**The goal.** Every scenario in the DB has a *learned* trust score, not a hand-coded one. A scenario that consistently helps the classifier vote correctly = gold. A scenario that consistently votes wrong = garbage. The system learns which is which from real production usage.

**The data structure.** Add columns to `scenarios` table:

```sql
ALTER TABLE scenarios ADD COLUMN tp_count INTEGER DEFAULT 0;
ALTER TABLE scenarios ADD COLUMN fp_count INTEGER DEFAULT 0;
ALTER TABLE scenarios ADD COLUMN retrieval_count INTEGER DEFAULT 0;
ALTER TABLE scenarios ADD COLUMN net_contribution REAL DEFAULT 0.0;
ALTER TABLE scenarios ADD COLUMN last_retrieved_ts TEXT;
```

- `tp_count` — true-positive count: how often this scenario showed up in top-K for queries where the vote landed on the right label.
- `fp_count` — false-positive count: how often it showed up in top-K for queries where the vote landed on the wrong label.
- `retrieval_count` — total times this scenario appeared in top-K (= tp_count + fp_count + ambiguous + unsupervised).
- `net_contribution` — derived: `(tp_count - fp_count) / max(retrieval_count, MIN_RETRIEVALS)`. Computed lazily; cached.
- `last_retrieved_ts` — for staleness detection.

**The retrieval-time use.** Top-K aggregation includes `net_contribution` as a multiplier:

```
final_weight_for_label_X = sum(similarity × wilson_score × max(0, net_contribution))
```

Garbage scenarios with negative net contribution get clamped to zero weight. They're in the DB; they're just silenced.

**The dependency.** This layer requires *real outcome data* to be useful. Without Layer 2 firing, the counters stay at zero forever and `net_contribution` defaults to a smoothed prior.

**Phase 1 deliverable.** The schema change, the read-path multiplier (defaulted to 1.0 when counters are empty so behavior matches today), and infrastructure ready for Layer 2 to fill in counters.

## 225. Layer 2 — Outcome Supervision Wired Correctly

**The goal.** Generate the TP/FP signals Layer 1 needs. The dead-code path in `core.classifier_graph` (`record_pending_outcome` / `confirm_pending` / `revert_pending`) becomes alive.

**Three signal sources:**

**Source A — tool-execution outcomes.** When a tool fires successfully *and* the user doesn't correct it within 3 turns, the scenarios that voted for that intent get `tp_count++`. Implementation:
- Pipeline calls `record_pending_outcome(decision_id, scenarios_in_topK)` after every classification.
- The decision_id is held in a deque with a 3-turn aging window.
- After 3 user turns without a correction, `confirm_pending(decision_id)` fires → `tp_count++` for every scenario that voted for the winning label.
- If a correction or rejection arrives within 3 turns, `revert_pending(decision_id)` fires → `fp_count++` instead.

**Source B — explicit user corrections.** The existing correction loop (§210) already increments contradiction counts. Layer 2 broadens it: more correction patterns, more permissive natural-speech detection. Mining the canary archive logs for real correction phrasings is the data-driven approach.

**Source C — periodic offline validation.** A new script (e.g. `tests/score_scenarios.py`) runs the held-out test set with each scenario alternately included/excluded, computes per-scenario inclusion-impact, writes results to TP/FP counters. Runs nightly or on-demand. Acts as a "ground truth calibration" backstop independent of in-vivo signals.

**Crucial detail — disambiguating tool rejections.** The current pipeline logs four classes of tool rejection through the same `[Pipeline] Tool: X REJECTED` channel. Layer 2 needs them disambiguated:

| Rejection class | Layer 2 signal |
|---|---|
| Intent gate (classifier said wrong intent) | `revert_pending` → `fp_count++` |
| Privilege gate (intent right, person not authorized) | `confirm_pending` → `tp_count++` (graph was right; person was the issue) |
| Repeat guard (intent right, LLM looping) | `confirm_pending` → `tp_count++` (graph was right; LLM was the issue) |
| User-text grounding (extracted_value not in user_text) | `revert_pending` → `fp_count++` |

Disambiguation is a 1-2 session refactor of the rejection-logging code paths in `pipeline.py`.

**Phase 2 deliverable.** Wired outcome supervision (sources A + B). Source C is queued for after wiring.

## 226. Layer 3 — Hierarchical Retrieval, Adaptive K, Distance-Weighted Voting

**The goal.** Better retrieval, given the same scenarios. Three sub-improvements that stack:

**Sub-3a — Hierarchical retrieval.** Don't search across all 2,071+ scenarios. First, classify the query into a cluster (by source corpus initially, by embedding cluster eventually). Then top-K within that cluster only. Cornell movie scenes never crowd into Friends-sitcom queries because they're in a different cluster.

Initial implementation: cluster by `source_tag` (5 clusters: cornell / dailydialog / empathetic_dialogues / hand_authored / live_correction). Each cluster has a centroid embedding (mean of its scenarios' embeddings, normalized). At query time:
1. Embed the query.
2. Cosine-similarity vs each cluster centroid.
3. Pick the highest-scoring cluster.
4. Top-K retrieval scoped to that cluster.

Fallback path: if no cluster's centroid scores above some threshold (the query genuinely doesn't fit any cluster), fall back to flat top-K over all data. Gated by `HIERARCHICAL_FALLBACK_TO_FLAT=True` config flag, default ON.

**Sub-3b — Adaptive K.** Replace fixed K=5 (or K=10) with threshold-based: include all matches above similarity threshold T (e.g. T=0.65). Cap at K_max=15 to prevent vote dilution on too-generic queries. Calibrated empirically on a held-out validation slice.

If no scenarios clear the threshold, abstain. The classifier returns None and the gate code falls back to default-silent. Honest abstention beats voting with low-confidence garbage.

**Sub-3c — Distance-weighted voting.** Instead of equal-weight votes from top-K, weight by similarity. A 0.85 match counts ~2.7× a 0.30 match. Combined with Wilson scoring: `final_weight = similarity × wilson_lower × max(0, net_contribution)`. (Net contribution from Layer 1.)

**Phase 1 deliverable** (alongside Layer 1 schema). All three sub-improvements gated behind config flags (`HIERARCHICAL_RETRIEVAL_ENABLED`, `ADAPTIVE_K_ENABLED`, `DISTANCE_WEIGHTED_VOTING_ENABLED`), all default OFF. Test bridge runs with flags ON. Production stays current behavior until ablation validates the changes.

**Validation gate.** Run the staged ablation: 4 stages × 2 corpora (Friends + AMI) = 8 runs. Stage 0 = baseline. Stage 1 adds distance-weighted voting. Stage 2 adds adaptive K on top. Stage 3 adds hierarchical retrieval on top. Each stage's contribution measured separately. Don't proceed if any stage hurts either corpus.

## 227. Layer 4 — Multi-Aspect Annotation Rebuild

**The goal.** Each scenario annotated along multiple axes during bootstrap, not just one (intent_label). At retrieval time, similarity scores combined with per-axis weights — for `request_shutdown`, conversational_role and urgency matter most; for `casual_conversation`, emotional_register matters most.

**The axes (initial proposal):**
- `intent_label` (today)
- `conversational_role` — question / statement / command / reaction / meta
- `emotional_register` — neutral / urgent / playful / sarcastic / formal
- `speaker_relationship` — family / friend / professional / stranger
- `scene_type` — 1-on-1 / group / public
- `urgency` — low / medium / high
- `temporal_focus` — past / present / future / hypothetical

**The data shape.** Each scenario stored with multi-vector representation (one E5 embedding per axis-relevant abstraction of the text). Schema migration adds an `embeddings` JSON column or a separate `scenario_embeddings(scenario_id, axis, vector)` table.

**The retrieval shape.** Top-K candidate selection uses the standard intent-axis embedding. Reranking among top-K uses composite score = weighted geometric mean of per-axis scores. Per-intent axis weights initially uniform; eventually learned from Layer 2's outcome data.

**The cost.** This is the most expensive phase:
- Bootstrap pipeline rebuild — 5-7× the original Together.ai cost (~$25-100 per re-bootstrap).
- DB schema migration — additive but substantial.
- Retrieval logic rewrite.
- Re-bootstrap of all 2,081 existing scenarios with the new annotation pipeline.

**The unlock.** Multi-aspect retrieval is what makes "every scenario gold for *some* query" possible. A Cornell movie scene where someone shouts "shut it down" matches a Friends shutdown query because they share `conversational_role=command` + `urgency=high`, even though `emotional_register` differs. Single-vector retrieval can't make this distinction.

**Phase 4 deliverable.** Re-bootstrap with multi-aspect annotations + retrieval rewrite + per-intent axis weight calibration. Both Friends + AMI must improve before this phase ships. Old single-vector retrieval kept as fallback for ~1 month before full deprecation.

## 228. Layer 5 — Active Quality Gating and Auto-Quarantine

**The goal.** Garbage scenarios — those with persistently negative net_contribution — get automatically excluded from retrieval. The pool stays clean.

**The mechanism:**

```python
def maybe_quarantine(scenario):
    if scenario.retrieval_count < MIN_RETRIEVALS_FOR_QUARANTINE:
        return  # not enough data yet
    if scenario.net_contribution < QUARANTINE_THRESHOLD:
        scenario.active = 0
        audit_log("quarantined", scenario_id, reason=f"net_contribution={...}")
```

Runs nightly via the dream loop. Quarantined scenarios stay in the DB for audit (Spec 1's `active = 0` semantic) but are excluded from retrieval. Visible in the dashboard's "quarantine list."

**Reactivation.** If a quarantined scenario gets fresh positive evidence (e.g. a correction loop pointing at it as the right answer), set `active = 1` again, audit-log the reactivation, reset some counters. Reactivation is a meaningful signal — humans tagged it as right when the system thought it was wrong.

**The result.** Dump 10k scenarios in. Run the system for a few weeks. The garbage ones accumulate negative net_contribution. They quarantine themselves. The retrieval pool stabilizes on the high-quality subset. Adding more data is no longer destructive because bad data gets filtered before it votes.

**Operator visibility.** Session-end summary log expands: `[classifier_graph] N retrievals, M corrections logged, K scenarios crossed quarantine threshold this session, J reactivated`. Dashboard exposure: top-quality scenarios, quarantined scenarios, recent quarantines, recent reactivations.

**Phase 3 deliverable.** Quality scoring (lazy `net_contribution` computation), quarantine cron, reactivation logic, dashboard visibility.

## 229. Layer 6 — Provenance and Lineage

**The goal.** Every retrieval is auditable. When the system makes a wrong prediction in production, an engineer can trace back: which scenarios contributed, what their histories were, why they voted the way they did.

**What gets logged:**
- Per-retrieval: query text, abstracted text, query embedding hash, top-K scenarios with their similarities and Wilson scores and net_contributions, winning label, final confidence.
- Per-scenario edit: scenario_id, what changed (counter bump, label change, quarantine, reactivation), trigger source (correction loop, outcome supervision, manual override), timestamp.
- Per-correction-loop event: original turn text, corrected target, old prediction, new scenario inserted (if any).

**Where logged:**
- The existing `audit_log` JSONL gets richer entries.
- Per-retrieval logs go to a separate JSONL (`data/classifier_retrievals.jsonl`) — high-volume; rotated daily.
- A simple `bridge/scripts/explain_prediction.py` script can take a turn_id from a canary log and reconstruct the full retrieval path.

**Drift detection** runs on top of these logs:
- Daily aggregation of retrieval-pool composition (which scenarios are getting retrieved most, which never).
- Alerts when a previously-stable scenario's TP/FP rate suddenly shifts (could indicate a corpus-distribution shift in production traffic, or a bootstrap issue).
- Latency monitoring per retrieval stage (abstraction, embedding, k-NN, aggregation, total).

**Phase 5 deliverable.** This is operational tooling, not a single feature. It runs alongside everything from Phase 1 onward and gets richer over time.

## 230. Phase Sequencing — How the Layers Ship

The layers don't ship simultaneously. They have dependencies. Phase order:

**Phase 1 — Foundation (~3-5 days dev).** Layer 3 (hierarchical retrieval, adaptive K, distance-weighted voting) gated behind feature flags. Plus Layer 1 schema (TP/FP counters, net_contribution column, provenance fields) — the columns exist with default values, ready for Layer 2 to fill. Plus Layer 6 first cut (per-retrieval log JSONL, audit log enrichment). All flag-gated. Production stays current behavior. Test bridge validates the new code paths.

Validation gate: run the staged ablation (4 stages × 2 corpora = 8 runs). All three Layer 3 sub-improvements must stack without breaking either Friends or AMI. Promote flags from test to prod after stable for 1 week.

**Phase 2 — Learning signal (~1-2 weeks dev).** Layer 2 (outcome supervision wiring + correction-pattern broadening + offline validation script). Disambiguation of tool-rejection classes. Layer 1's counters start filling.

Validation gate: 2-4 weeks of canary sessions to let counters accumulate meaningfully. Wait period built in.

**Phase 3 — Quality gating (~1 week dev).** Layer 5 (auto-quarantine cron, reactivation, dashboard visibility). Builds on Phase 2's data.

Validation gate: deliberately seed a noisy 5k-scenario set into a non-production DB. Run for a month. Verify net_contribution distributions look right, quarantine threshold is calibrated.

**Phase 4 — Multi-aspect rebuild (~3-4 weeks dev + bootstrap cost).** Layer 4 (re-bootstrap with multi-axis annotation, retrieval rewrite, axis-weight learning).

Validation gate: ablation showing multi-aspect retrieval beats single-vector on at least 3 different test corpora.

**Phase 5 — Operational hardening (parallel/ongoing from Phase 1).** Layer 6 (provenance audit trails, drift detection, latency monitoring, dashboard). Not a single deliverable; runs alongside everything from Phase 1.

**Total estimated dev work.** 8-14 weeks of focused engineering, plus 1-2 months of real-world data accumulation between Phase 2 and Phase 3. The user has explicitly committed to this timeline.

## 231. The Non-Parametric Commitment

A standing architectural axiom for this work: **zero LLM in the classification path. Forever.**

Every design decision in Layers 1-6 must be evaluated against this constraint. Some implications:

- Reranking with a tiny LLM (Phi-3-mini, Qwen-2.5-1.5B) is *not* an option, even when it would solve a specific problem. The point of the architecture is model-agnostic at the classification layer.
- Multi-aspect annotation (Layer 4) IS allowed to use an LLM during *bootstrap* (re-running the bootstrap pipeline with richer annotation prompts). That's offline data preparation, not classification.
- Outcome supervision must come from rule-based signals (tool gates, correction regex patterns) not from LLM-based judgment.
- The "is this scenario relevant to this query?" similarity match must be E5 (or another local-deterministic embedder), never an LLM call.

The cost of this constraint: some clever solutions are off the table. Some performance ceiling sacrificed. The benefit: the classifier is a stable artifact independent of which LLM is the brain. KaraOS-on-Llama-70B and KaraOS-on-Qwen-7B and KaraOS-on-GPT-5 produce *identical* classifications because the classifier doesn't depend on the brain.

This is the property the multi-backbone falsifying experiment (§217) showed the LLM-classifier path didn't have. The graph classifier has it. The multi-layer architecture preserves it.

## 232. Honest Limitations of the Multi-Layer Plan

Some things the multi-layer architecture will NOT solve, even at full deployment:

**Catastrophic distribution shifts.** A query from a totally new conversation context the bootstrap never saw (e.g. a low-resource language, a domain like surgical handoff, a register like adversarial debate) will still abstain or fall back. Abstain is honest — but it means the system won't always have an answer. For these cases, expanding the bootstrap (adding new source corpora, new hand-authored scenarios) is the right response, not architectural.

**Latency at very large scale.** At 10k+ scenarios, brute-force cosine k-NN is going to be real even with hierarchical retrieval (each cluster might have 1-2k scenarios). At 100k+ we'll need an ANN library (FAISS, hnswlib). Phase 4's bootstrap rebuild is when we'd switch to ANN; we'll budget per-query latency carefully and accept the slight precision-at-K loss vs brute-force.

**Some things will always need a small reranker.** The non-parametric commitment forces every clever solution into the retrieval-and-aggregation paradigm. Some problems we'll WISH we could solve with a small reranker model — we'll have to solve them with smarter retrieval (multi-aspect, learned reliability, hierarchical routing) instead. Worth being honest with ourselves: this is a constraint with real costs.

**The bootstrap data is itself uneven quality.** No amount of retrieval-side cleverness fixes a corpus where some labels are wrong. Layer 5 (auto-quarantine) will silence the worst offenders, but it can't *un-train* a wrongly-labeled scenario back into a correctly-labeled one. The right response to that is investing in bootstrap quality — better LLM prompts during classification, multiple LLMs voting on each label, manual spot-checks of high-impact scenarios.

**The "garbage immune at scale" property is empirical, not theoretical.** Layers 1+2+5 should produce that property in practice. No theorem guarantees it. We'll know if it works by running the 10k-scenario stress test (Phase 3 validation gate) and watching what happens. If it doesn't work, we adjust.

This is honest engineering work, not a performance pitch. The goal is a system that's *better than today's*, scales *better than today's*, and surfaces its own failure modes honestly when they occur. Not a system that's perfect.

---

# Part XXXVI — P0 Correctness Hardening (P0.1 – P0.3 + P0.13)

## 233. Why a Correctness Cycle Came First

The P0 work that landed in early May 2026 (P0.1 – P0.5, P0.13) targeted a different layer of the system than the bigger architectural sub-PRs that followed. These were correctness regressions surfaced by live canaries, not architectural debt. Each one was a small fix — usually 5–30 lines of production change — paired with a structural invariant test that prevents the regression class returning silently.

The grouping is deliberate: each P0.* item below is a separate failure mode with a separate AST-level guard, but they share an underlying methodology. **Fix the production code in one commit; ship the structural invariant in the same commit; cap the invariant at zero in a CI-enforced test; let the invariant catch any future drift.**

This is the methodology that escalated into the structured-audit-vs-reactive-patching lesson at P0.4 (§329). The earlier P0.1 – P0.3 items shipped reactive-patching style, then P0.4 (§238) demonstrated that *systematic* audit surfaces ~3–5× more sites than reactive patching catches. The retroactive read on P0.1 – P0.3 is that they were each the tip of a class — and the class itself was caught by the audit.

## 234. P0.1 — No Raw `"disputed"` Comparisons Outside the Helper

`_is_disputed()` (Part XV) was the canonical predicate for checking whether a session's `person_type` is in disputed state. It centralises the comparison so the dispute state machine can evolve without scattering string literals throughout the codebase.

The drift: live canary log lines started showing `person_type == "disputed"` checks at scattered call sites in `pipeline.py` and `core/brain_agent.py`. Each one was a tiny copy-paste of the helper's body. None individually was wrong. Collectively, they made the helper non-canonical — any future change to dispute state representation (e.g. moving from string to enum) would silently miss these sites.

**Fix:** every raw `== "disputed"` outside `_is_disputed()` was rewritten to call the helper. **Invariant:** `tests/test_no_raw_disputed_comparisons.py` (P0.1) AST-scans `pipeline.py` (excluding `_is_disputed()`'s own body) and every `core/*.py` (excluding `core/config.py` for type annotations) for `Compare` nodes where the right-hand side is the literal string `"disputed"`. The test fails if any site is added outside the helper.

One allowlist: `core/brain_agent.py:2216` uses an inline `# disputed-row-status` marker for a knowledge-row status column check that can't route through the helper due to a circular import. The allowlist marker is the explicit single exception; the AST scanner reads it as "this is a known site, do not flag".

## 235. P0.2 — `prior_person_type` Fail-Closed Default

The dispute state machine captures `prior_person_type` on every dispute-trigger event (§102) so that auto-clear (§51) can restore the speaker's role correctly after the dispute resolves. If the field is missing — for example because a future code path added a new dispute-trigger site without remembering to write the field — the default should be the lowest privilege.

The drift: two scattered sites in `pipeline.py` defaulted the missing field to `"known"` rather than `"stranger"`. A best_friend session whose `prior_person_type` was never written would silently auto-clear back to `"known"` — a privilege downgrade. Worse, in the reverse direction, a stranger session whose `prior_person_type` was never written and then somehow flipped to disputed would auto-clear *up* to `"known"` — a privilege escalation.

**Fix:** both sites now default to `"stranger"` (fail-closed). Even a missing field cannot grant privileges the speaker didn't have. **Invariant:** `tests/test_prior_person_type_default.py` (P0.2) — 20 AST structural tests covering 9 violation shapes and 10 legitimate patterns. The shape `_sess.get("prior_person_type") or "known"` is forbidden; `or "stranger"` is required.

The naming "fail-closed" carries explicit semantics: when a security-relevant default has to be picked, pick the one that grants the *least* privilege, so that the missing case can never silently grant more access than the writer of the field would have intended.

## 236. P0.3 — Multi-Word Name Contiguous Substring Fix

The `_user_text_gate_passes` primitive (§115) verifies that an LLM-proposed mutation tool argument (e.g. the proposed new name in `update_person_name`) was actually said by the user, by checking it appears as a substring of the most recent user_text. This is the architectural seam that prevents LLM hallucination from renaming people who never asked to be renamed.

The pre-fix v1 implementation used a `(\w+)` capture group to grab the first word of the proposed name, then a `_remainder` check (`_remainder in user_text`) to verify additional words also appeared. The bug: `_remainder` could appear *anywhere* in the user_text. A user saying "call me Sarah and my friend is Jane" would let the LLM hallucinate a rename to "Sarah Jane" — because "Sarah" and "Jane" both appear in user_text, just not contiguously.

**Fix (v3):** replaced the buggy remainder block with a single contiguous-substring check `if _nv_lower in _lt`. The full proposed name must appear as a contiguous substring of user_text. Also applied `_nfkc_lower()` (NFKC normalization + casefold) to all three inputs (user_text, new_value, captured) for homoglyph defense. **Tests:** `tests/test_user_text_gate_multiword.py` covers 25 behaviour cases (single-word baseline / legitimate multi-word contiguous / non-contiguous discriminating cases that v1 allowed and v3 rejects / fabrication-rejection / empty / None) and `tests/test_user_text_gate_invariants.py` covers 5 structural + behavioural invariants.

## 237. P0.13 — The Repeat-Guard Invariant Test

Session 70's Bug Q (Part XVI §113) introduced the **tool repeat guard** — when the LLM emits the same `(tool_name, args)` two turns in a row, the second call is suppressed. The mechanism is a per-session set of `_repeat_guard_key` and `_repeat_guard_count` fields, cleared by `_close_session` (Part VIII §50).

The drift surface: any new code path that proactively spawns a fresh tool call without going through the normal `conversation_turn` flow could accidentally bypass the repeat guard by writing to the session dict directly. P0.13 is the AST structural invariant that prevents this.

`tests/test_repeat_guard_invariant.py` walks the parent-annotated AST of `pipeline.py` (via the new zero-import `core/pipeline_invariants.py` module that exposes `REPEAT_GUARD_FIELDS` and `ALLOWED_REPEAT_GUARD_FUNCS`). Five violation detectors fire on any direct mutation of repeat-guard fields outside the allowlisted helpers: `pop`, `del`, `assign None`, `update`, `clear`. The allowlisted functions are the legitimate writers (`_execute_tool`, `_close_session`, plus a small set of dispute-clear paths) — any direct mutation outside the allowlist fails the test.

The test uses *full parent-walk analysis* (`_is_inside_allowlisted_function` walks every ancestor) which is important: a later refactor that decomposes `_execute_tool` into nested helpers must continue to be exempt, because the nested helpers are conceptually still inside the allowlisted function. The refactor doesn't have to update the test.

---

# Part XXXVII — The Silent-Except Audit (P0.4)

## 238. The Reactive-Patching Anti-Pattern

Before P0.4, the standard response to a `except Exception: pass` discovered during a debugging session was to fix the one site and move on. A few months of this had surfaced ~7 silent-except sites, fixed one at a time, with no systematic audit.

The reactive-patching mindset assumes that catching the bugs *as they bite* is sufficient. In practice — empirically demonstrated by P0.4 — reactive patching catches roughly 30% of the class. The other 70% sits in production code, swallowing failures that nobody has needed to debug yet.

The realisation: an AST-based project-wide scan would surface every silent-except in one pass. The scan would also become the structural invariant that prevents the class returning. The combined cost — audit + invariant + remediation — is small (about 3-5 hours total). The combined value — every silent failure mode either fixed or explicitly justified — is enormous because of the next-bug-debug-time saved.

## 239. AST Detector Anatomy

`tests/test_silent_except_invariant.py` ships before any production-side fix. Three helpers compose the detector:

- **`_is_broad_except_handler(node)`** — returns True iff the `ast.ExceptHandler`'s `type` is one of: `None` (bare `except:`), an `ast.Name` matching `Exception` or `BaseException`, or an `ast.Tuple` whose elements include `Exception` or `BaseException`.
- **`_is_silent_pass_only_body(node)`** — returns True iff the handler's body is exactly `[ast.Pass]`. A body with logging, re-raise, return, or any other statement does not match. The discipline is *silent* pass-only; logged pass is fine.
- **`_has_annotation_comment(node, source_lines)`** — looks for `# RACE:`, `# CLEANUP:`, `# OPTIONAL:` on the `pass` line, the `except` line, or the line directly above. The 3-line co-location window captures both common styles (annotation above the except header, or inline with the pass).

Allowlist with boundary-correct check: `rel_str == allow or rel_str.startswith(allow + "/")`. This prevents `core/_minifasnet_helper.py` from matching `core/_minifasnet` allowlist entry through accidental string prefix collision.

Injectable `rel_str` param on `_scan_file` so detector self-tests exercise the real code path with synthetic input. The self-tests live in the same test file and demonstrate that the scanner rejects unannotated handlers and accepts each of the three permitted annotations.

## 240. The 22 Surfaced Sites and the Three Permitted Annotations

Running the audit found **22 sites** across 9 production files: `core/audio.py`, `core/brain.py`, `core/brain_agent.py` (6 sites), `core/classifier_graph.py`, `core/db.py` (2), `core/state.py`, `core/vision.py`, `pipeline.py` (8), `sim_runner.py`. Compared to the ~7 sites that had been caught reactively across the prior few months, that's a discovery ratio of roughly 3×.

The three permitted annotations encode genuinely different rationales:

- **`# RACE:`** — the handler swallows a known race condition (e.g. a concurrent close racing with a write). Re-raising would cascade a benign-but-unavoidable race into a visible failure. The annotation must be followed by a brief description of what races and why suppression is correct.
- **`# CLEANUP:`** — the handler is in a cleanup or finalisation path where the only error mode is the cleanup operation itself failing. Re-raising would mask the original error that triggered cleanup.
- **`# OPTIONAL:`** — the handler is in a best-effort observability or instrumentation path where the production behaviour is intentionally unaffected by the failure. `safe_emit_sync` (Part XLIX §314) is the canonical example: event-log emission is best-effort, a producer-hook bug must never break the production path.

Any site not matching one of these three rationales must be fixed (re-raise, log + re-raise, or replace with a typed handler).

## 241. Bulk Annotator and the One-Shot Closure

The remediation tool `tools/bulk_annotate_p04.py` is idempotent: a single pass adds `# TODO-P0.4: triage` to the pass line of every unannotated site. The annotation is a *temporary* permission — `# TODO-P0.4:` was originally in `PERMITTED_ANNOTATIONS` so the invariant test went green on the first run, then each site was triaged in 7 batches (B1 – B7) and the temporary marker was either replaced with one of the three real annotations or removed alongside a real fix.

P0.4 Batch 7 closed the cycle: `# TODO-P0.4:` was *removed* from `PERMITTED_ANNOTATIONS`. From that commit forward, the marker is itself a violation — meaning the structural invariant no longer accepts the "to be triaged later" escape hatch.

The empirical lesson banked in §329: **22 sites surfaced via AST audit; ~7 had been caught reactively; the gap (~70%) is what motivates the structured-audit-vs-reactive-patching discipline.** Subsequent P0 items (P0.5 inverse check, P1.A1-slice layering audit at 9 sites vs 2 known reactively, a 4.5× discovery ratio) confirmed the ratio.

---

# Part XXXVIII — Cross-Storage Atomicity (P0.5 + P0.X)

## 242. The Paired-Write Failure Class

Kara-OS's persistence layer is *not* a single SQL database. It's three durable stores that have to stay consistent: SQLite (`faces.db` + `brain.db`), FAISS (the face index), and Kuzu (the knowledge graph). Every write that touches more than one of these stores is a **paired write**, and every paired write has a failure mode: the first half commits, the process crashes before the second half, and the next boot sees divergent state.

The pre-P0.5 architecture had paired writes scattered through `core/db.py` and `core/brain_agent.py` with no consistent ordering, no atomicity guarantee, and no boot reconciliation. The empirical bug fingerprint: `add_embedding` updated FAISS *before* committing the SQL row. A SQL INSERT failure (e.g. UNIQUE constraint violation, disk full, race with `delete_person`) left an orphan in FAISS with no corresponding DB row. `_load_faiss()` on next boot saw `ntotal > COUNT(*)` but had no mechanism to detect or repair the divergence.

P0.5 (FAISS ↔ faces.db) and P0.X (Kuzu ↔ brain.db) ship the architectural pattern that closes this failure class across both pairs.

## 243. P0.5 — FAISS ↔ faces.db SQL-First Ordering

The pattern applied to all 5 paired-write methods of `FaceDB` (`add_embedding`, `delete_person`, `prune_old_strangers`, `prune_zero_value_stranger`, `prune_outlier_embeddings`):

```python
with self._index_lock:
    with self.transaction():           # 1. SQL durable
        # SQL ops only — NO FAISS calls inside the transaction
    try:                               # 2. FAISS derived state
        self.index.add(...) / self._rebuild_faiss()
        self._save_faiss()
    except Exception:
        self._mark_faiss_dirty()       # sentinel → boot reconciliation
        raise
```

The contract: **SQL is the authoritative store; FAISS is derived state that can always be rebuilt from SQL.** SQL writes commit first inside a transaction. FAISS writes happen after the SQL commit. If FAISS writes fail, a sentinel file is touched on disk and the exception is re-raised. Boot reconciliation reads the sentinel and rebuilds FAISS from SQL.

`FaceDB.transaction()` is a context manager that issues `BEGIN IMMEDIATE` (with the S65 rollback race tightened — see §282) so concurrent connections can't interleave their writes.

## 244. Sentinel Files and Boot Reconciliation

Three sentinel helpers on `FaceDB`:

- **`_sentinel_path()`** — returns the path to the `_faiss_dirty.sentinel` file alongside the FAISS index file.
- **`_mark_faiss_dirty()`** — touches the sentinel file. Used in the `except` branch of every paired-write method.
- **`_clear_faiss_dirty()`** — deletes the sentinel file. Used after `_rebuild_faiss()` completes successfully at boot.

`_load_faiss()` at startup checks the sentinel OR computes a count-mismatch (FAISS `ntotal` vs SQL `SELECT COUNT(*) FROM embeddings`). If either is non-empty, `_rebuild_faiss()` is called, the sentinel is cleared on success, and the system continues. If rebuild fails at boot, `_faiss_degraded = True` is set on the FaceDB instance, the sentinel is preserved (so the next boot tries again), and `recognize()` returns `(None, None, 0.0)` for the rest of the session. The system degrades to no-face-match rather than crashing.

The bug fingerprint preserved as a regression test in `tests/test_faiss_sql_atomicity.py`: Test 1 asserts `db.index.ntotal == pre_faiss_size` after a forced SQL crash. Pre-fix FAISS-first ordering leaves `ntotal=1` (orphan). Post-fix SQL-first ordering leaves `ntotal=0` (SQL rolled back, FAISS never touched). The test passes only against the post-fix code.

## 245. The Inverse-Check Discipline

`PAIRED_WRITE_METHODS = ("add_embedding", "delete_person", "prune_old_strangers", "prune_zero_value_stranger", "prune_outlier_embeddings")` — a hand-curated tuple in `tests/test_faiss_atomicity_invariants.py`. **Forward check:** every method in the tuple is verified to follow the SQL-first + sentinel + `_index_lock` pattern via AST scan.

That was the obvious half. **Inverse check:** every method on `FaceDB` that calls into FAISS (regex pattern matching `self.index.add` / `self._rebuild_faiss` / `self._save_faiss`) is asserted to be a member of `PAIRED_WRITE_METHODS`. The two halves together close the loop: any future method added without registration silently fails the inverse check.

The empirical lesson — and the reason inverse checks became standard practice — is that the inverse check on P0.5 **caught a real bug in the same session**. `prune_outlier_embeddings` was a hidden paired-write site: it called `_rebuild_faiss()` directly without `_index_lock`, without `transaction()`, and without `_mark_faiss_dirty()`. The forward check would have happily passed an empty tuple. The inverse check failed loudly and forced the fix.

The closure-time effort to add the inverse check was about 30 minutes. It caught a 7th bug from one P0 cycle. The discipline is now applied to every enumerated method tuple in the codebase: PAIRED_WRITE_METHODS in P0.5, VOICE_GALLERY_METHODS, the Kuzu Three-Pattern detectors in §246, the EXPECTED_RULES_BY_BAND map in §291, the `_TOOL_HANDLERS` dispatch table in §272, the producer-hook coverage in P0.0.7 (Part XLIX).

## 246. P0.X — The Three Kuzu Write Patterns

Kuzu (the knowledge graph) is a separate store from brain.db (the SQL knowledge table). They have to stay consistent: every fact extracted by `ExtractionAgent` lands in *both* (brain.db row + Kuzu nodes/edges). The pre-P0.X architecture had cross-write code scattered across `BrainOrchestrator._process_turn`, `_retroactive_scan`, `on_identity_confirmed`, and `_persist_extraction_to_kuzu` — with no consistent pattern for what happens when one half fails.

P0.X codified three patterns and enforced each with an AST detector:

| Pattern | What it does | Where it's used |
|---|---|---|
| **`SCHEMA_MIGRATION`** | Always rebuilds Kuzu from brain.db. Inherently safe because brain.db is authoritative. | `_ensure_graph_sync()` at boot |
| **`RAISE`** | SQL transaction first, sentinel touched before Kuzu op, sentinel cleared on Kuzu success, re-raise on Kuzu failure | `on_identity_confirmed` — the user-visible rename path; the user gets an explicit failure, not silent divergence |
| **`SWALLOW`** | Kuzu try/except with sentinel touched + log, no re-raise | `_persist_extraction_to_kuzu`, `_retroactive_scan`, `_process_turn` — brain.db is authoritative, Kuzu heals on next `_ensure_graph_sync()` |

The pattern choice is per call site, decided by the question: **does the user need to know if Kuzu writes fail right now?** If yes (rename), use RAISE. If no (background extraction), use SWALLOW. SCHEMA_MIGRATION is the bootstrap-reconciliation path that picks up after either.

## 247. SCHEMA_MIGRATION, RAISE, and SWALLOW in Detail

Sentinel machinery on `BrainDB`:

- `_kuzu_dirty_path()` — sentinel file path.
- `_mark_kuzu_dirty()` — touches the sentinel before any Kuzu write.
- `_clear_kuzu_dirty()` — clears the sentinel after a successful Kuzu write.
- `_is_kuzu_dirty()` — reads the sentinel at boot.

Boot reconciliation in `BrainDB.__init__`: if `_is_kuzu_dirty()` is True, force `_ensure_graph_sync()` to rebuild on next access; `_kuzu_degraded: bool` flag is set if rebuild fails. Degraded mode causes graph reads to return empty rather than crash.

AST detector self-tests live in `tests/test_kuzu_atomicity_invariants.py` and prove that each helper catches exactly the violations it claims. The RAISE-pattern detector rewrites raise-detection to walk `ast.Try` nodes and find specifically the Kuzu-writing try block (by scanning the try body for Kuzu write markers) before inspecting its except handlers for `ast.Raise`. The pre-fix detector would find any `raise` in any except handler, including the SQL transaction wrapper's, and report false passes.

## 248. `_process_turn` — The Hidden Paired-Write Site

Inverse check at work again: `_process_turn` in `BrainOrchestrator` had `self._graph_db.invalidate_fact(...)` inside the ContradictionAgent loop **without** `_mark_kuzu_dirty()`. The inverse check (`test_all_kuzu_write_sites_are_covered`) found it. Two forward tests were added at closure: sentinel-written + no-re-raise for `_process_turn`.

Same shape, same lesson: registering enumerated tuples without inverse checks lets new call sites slip in undetected. The inverse check is the cheap insurance.

## 249. Degraded-Mode Fallback Behavior

`_faiss_degraded = True` → `FaceDB.recognize()` returns `(None, None, 0.0)`. Face-recognition flow continues to background-scan and pyannote-route on voice signals; the system functions without face match (degraded from "best-friend recognised on camera" to "voice-only attribution"). The dashboard receives a `state.json` update reflecting the degraded condition.

`_kuzu_degraded = True` → graph reads return empty. `find_shared_entities`, `_apply_household_extraction`, and similar paths see no graph data; the LLM prompt loses the graph context but continues to receive brain.db facts. Recovery happens on the next `_ensure_graph_sync()` cycle if the underlying issue (file lock, disk space) resolves.

The degraded modes are not silent. Each one logs a `[FAISS]`/`[Kuzu]` `WARN: degraded mode active` line. The health log (Part XLVI §301) doesn't surface them yet — adding `faiss_degraded` and `kuzu_degraded` fields to `HealthSnapshot` is a small follow-up worth doing alongside the Wave-5 fields.

---

# Part XXXIX — The Store-Pattern Migration (P0.6)

## 250. Why 28 Module-Level Globals Was a Problem

By early 2026 `pipeline.py` had accumulated 28 module-level mutable globals: `_persons_in_frame`, `_unrecognized_tracks`, `_stranger_track_map`, `_track_identity`, `_conversation`, `_last_greeted`, `_voice_gallery`, `_voice_gallery_sizes`, `_emotion_agents`, `_sessions_started`, `_active_room_session`, `_cloud_state`, `_cloud_failed_at`, `_pipeline_state`, `_active_system_name`, `_detected_lang`, `_latest_vision_frame`, `_latest_frame_time`, and many more.

The cost showed up in three places:

1. **Test isolation.** Each global needed an explicit reset in test fixtures. Many tests forgot. Failures cascaded: a test that set `_persons_in_frame` left state for the next test, which silently passed off the residual state and then failed unpredictably when run in a different order.
2. **Concurrent access.** Some globals were mutated from background coroutines (vision loop, KAIROS, dream loop). The mutation patterns were ad-hoc — sometimes a lock, sometimes not, sometimes a `.copy()`, sometimes a direct reference. The mutations interleaved during full-suite test runs and produced sporadic failures.
3. **Coupling.** A code change in one part of pipeline.py would silently affect another part through the shared globals. Vision tests would pass but voice tests would fail in unrelated ways because the order of writes to `_persons_in_frame` had changed (Part XXXII §198 documents this in the voice/vision context).

P0.6 ships the **Store pattern**: each cluster of globals is encapsulated in a typed class with async mutators, sync peek reads, and an explicit `reset()` method called by an autouse pytest fixture.

## 251. The `Store(ABC, Generic[T])` Base Class

`core/store_base.py`:

```python
from abc import ABC, abstractmethod
from typing import Generic, TypeVar

T = TypeVar("T")

class Store(ABC, Generic[T]):
    """Base class for all P0.6 pipeline-state stores.

    Subclasses must:
      - Define async mutator methods (require asyncio.Lock if mutating shared state).
      - Define sync peek_* methods for read-only access (no lock acquisition).
      - Implement reset() to restore the canonical empty / initial state.
    """

    @abstractmethod
    def reset(self) -> None: ...
```

Every store inherits from `Store`. The `reset()` method is the autouse-fixture-callable hook that makes test isolation deterministic.

## 252. The Eight Stores and What Each Owns

| Store | Module | Owns |
|---|---|---|
| `PresenceStore` | `core/presence_store.py` | `_persons_in_frame` (which person_ids are visible on camera + face_match_conf + source tag) |
| `TrackStore` | `core/track_store.py` | `_unrecognized_tracks`, `_stranger_track_map`, `_track_identity`, `_unrecognized_embeddings` |
| `ConversationStore` | `core/conversation_store.py` | `_conversation` (per-pid message history), `_last_greeted`, `_last_self_update`, `_compact_pids` |
| `VoiceGalleryStore` | `core/voice_gallery_store.py` | `_voice_gallery` (in-memory mean embeddings), `_voice_gallery_sizes` (DB-backed cache) |
| `PerPersonAgentStore` | `core/per_person_agent_store.py` | `_emotion_agents` (per-pid EmotionAgent instances), `_sessions_started`, `_ambient_wake_pending` |
| `CacheStore` (×4 instances) | `core/cache_store.py` | `_compact_history_cache`, `_query_embedding_cache`, `_intent_classifier_cache`, `_bf_id_cache` |
| `PipelineStateStore` | `core/pipeline_state_store.py` | `_cloud_state`, `_pipeline_state`, `_active_room_session`, `_active_system_name`, `_detected_lang`, `_last_face_seen`, `_last_user_speech_at`, `_last_kairos_at`, `_last_silent_update`, plus the cloud transition methods |
| `VisionFrameStore` | `core/vision_frame_store.py` | `_latest_vision_frame`, `_latest_frame_time`, `_vision_prev_det_count` |

Each store has between 5 and 25 methods. The total LOC for the eight modules is ~3500 lines, but the migration *removed* roughly the same amount from `pipeline.py` — net architectural improvement, not net code growth.

## 253. Async Mutators, Sync `peek_*` Reads, and the Single-Owner Invariant

The convention across all eight stores:

- **Async mutators** (`async def set_x(...)`, `async def append_y(...)`, etc.) acquire the store's `asyncio.Lock` before mutating. The lock guards against concurrent writes from multiple coroutines.
- **Sync `peek_*` reads** (`def peek_x(...)`) do *not* acquire the lock. They read the canonical structure once and return either a copy (for mutable collections like lists/dicts) or the value directly (for immutable types like strings/ints). The contract is: peek reads are cheap, called from synchronous contexts (logging, prompt assembly), and must never block.
- **Single-owner invariant**: each store is instantiated exactly once at module level. No code outside the store module mutates the underlying data; everything goes through the store API.

`tests/test_p06_store_invariants.py` enforces these conventions via AST scan. `_STORE_MODULES` enumerates the eight modules; each one is asserted to inherit from `Store`, to expose only async-marked mutators (with a small allowlist for legitimately-sync mutators like `__init__`), to have a `reset()` method, and to be the sole writer of its owned fields (cross-checked against grep of the module-level names).

## 254. The Producer-Copy Invariant

`VisionFrameStore.set_frame(frame, frame_time)` accepts a numpy ndarray. The frame is a *shared* reference produced by the camera capture loop. If the store kept the reference and another consumer mutated the frame in place, every reader would observe the mutation. Worse, the SORT tracker (Part IV §21) mutates its input arrays as part of its bounding-box update.

**The rule:** producers MUST call `.copy()` on the frame before passing it to `set_frame`. The store doesn't copy internally — it would be wasteful in cases where the producer already has a copy.

The structural invariant: `tests/test_vision_frame_store_producer_copy.py` AST-scans `pipeline.py` for every `set_frame(...)` call site and asserts `.copy()` appears in the same expression (either on the frame argument directly, or on a binding visible in the same scope). One of the eight P0.6.7v2 deliberate-regression checks (§258) injected a frame passed without `.copy()` and confirmed the test fires.

## 255. Peek-Not-Mutate Semantics for CacheStore

The original `CacheStore` had a touch-on-read LRU: every `get(key)` not only returned the value but also moved the key to the end of the OrderedDict (most-recently-used). This violated the spec's locked decision (cache should be `peek`, not `touch`).

The drift was caught in the v2 closure audit (Part L §322 — induction-surfaces-invariant-gaps). v2 renamed `get()` → `peek()`, removed `move_to_end` touch-on-read, replaced OrderedDict with a plain dict, and eviction on `set()` now picks the oldest-by-cached-at via `min(_data, key=lambda k: _data[k][1])`. `_hits` and `_misses` are documented as read-side observability counters with `# OBSERVABILITY:` annotation — they're written from `peek()` for counting purposes but they do *not* affect cache behavior.

The deliberate-regression check that proved the fix: inject `touch-on-read` promotion logic into `peek()` and confirm a behavioral test (cache should evict oldest under bounded capacity even when oldest is read recently) fails with the injection and passes with the spec'd peek-not-mutate.

## 256. The Prior-State Guard for Cloud Transitions

`PipelineStateStore.transition_to_online()` was originally idempotent (could be called multiple times with no side effects). The v1 implementation set `cloud_recovered = True` on every call. The drift: a retry path that called `transition_to_online()` twice in quick succession spuriously fired the `cloud_recovered` flag, causing the recovery flow (Part XII §79) to emit a leaky "cloud connection just came back online" TTS narration on every retry rather than only on the actual SICK→ONLINE transition.

v2 fix: gain a prior-state check. `cloud_recovered = True` is set *only* if the prior state was NOT already ONLINE. Idempotent retry no longer spuriously signals recovery. One of the eight deliberate-regression checks (§258) injected the guard removal and confirmed the recovery TTS was spuriously emitted.

## 257. Autouse-Fixture Reset and the M2 Coverage Meta-Test

`conftest.py` (root) and `tests/conftest.py` both contain an autouse fixture `_reset_pipeline_state_between_tests` that calls `reset()` on every Store. The fixture is autouse, so every test runs against a clean state by default.

The M2 coverage meta-test (`test_p06_store_invariants.py::test_autouse_fixture_resets_all_stores`) AST-scans both conftest files and asserts every store name is in the reset loop. The 9th store added (SessionStore — added by P0.7) was caught by M2 the first time the test ran with only 8 entries in the reset list — the meta-test forced the conftest update before P0.7 could land.

## 258. The Eight Deliberate-Regression Checks at v2 Closure

After v1 shipped and the closure audit caught three gaps (vision globals missed, CacheStore touch-on-read, prior-state guard), v2 incorporated all three plus the architectural invariants from §253–§256. Closure for v2 ran eight deliberate-regression checks, one per invariant, and all eight fired correctly:

| # | What was injected | Test that fired | Reverted? |
|---|---|---|---|
| 1 | Added a new field to `PresenceStore.EXPECTED_FIELDS` schema | `test_presence_store_schema` (field-set drift) | Yes |
| 2 | Added a writer to `_persons_in_frame` outside `PresenceStore` | `test_no_external_writes_to_presence_store` | Yes |
| 3 | Stripped paired-write atomicity from `transition_to_sick` | `test_cloud_bundle_paired_write_atomic` | Yes |
| 4 | Passed a frame to `set_frame` without `.copy()` | `test_vision_frame_store_producer_copy` | Yes |
| 5 | Injected `move_to_end` touch-on-read into `CacheStore.peek` | behavioral cache eviction test | Yes |
| 6 | Re-added a legacy global at module scope in `pipeline.py` | `test_p06_legacy_global_progress` (ratchet at cap=0) | Yes |
| 7 | Dropped a store from the conftest reset loop | M2 autouse meta-test | Yes |
| 8 | Removed the prior-state guard from `transition_to_online` | behavioral cloud-recovery TTS test | Yes |

The pattern is the induction-surfaces-invariant-gaps discipline (Part L §322) at work: each invariant gets tested by injecting its own violation, confirming the test fires, then reverting. v2 closure went green only after all eight checks confirmed correct behaviour.

## 259. The Legacy-Global Ratchet at Cap = 0

`tests/test_p06_legacy_global_progress.py` is the migration-progress ratchet. It AST-scans `pipeline.py` for module-level assignments to a fixed enumeration of 28 legacy global names (`_persons_in_frame = ...`, `_voice_gallery_sizes = ...`, etc.) and asserts the count is below a configurable cap. During the migration the cap stepped down (28 → 25 → 20 → ... → 0). At closure the cap is 0: any reintroduction of a legacy global fails CI.

The detector uses word-boundary discipline. Initially it caught false positives like `initial_cloud_state=...` (kwarg, not a global write) — the regex was tightened to require word-boundary delimiters on both sides of the global name.

The inverse check enumeration was also updated for the legitimate writers: `__init__` is allowed to conditionally assign `_cloud_state` and `_pipeline_state` after `reset()`. The allowlist captures the constructive paths, the ratchet blocks the destructive paths.

## 260. The Schema and Inverse-Check Ratchets That Lock It In

Four invariant tests, run every PR, lock the migration as a permanent structural property:

1. **Ratchet** — `test_p06_legacy_global_progress.py` at cap=0 (above).
2. **Schema pinning** — `test_p06_store_schemas.py` pins `EXPECTED_FIELDS` per Store across 15 schema tests. Drift in any owned-field set fails CI.
3. **Inverse checks** — `test_p06_store_inverse_checks.py` enforces paired-write discipline via 19 AST-based inverse checks: cloud-bundle (4-field atomic), room-triple-tuple (3-field atomic), VoiceGalleryStore (gallery, sizes) pair, VisionFrameStore (frame, frame_time) pair, plus per-field writer enumeration for the simpler stores.
4. **M2 autouse meta-test** — verifies both conftest files reset all 9 stores (8 P0.6 stores + 1 P0.7 SessionStore).

Plus the producer-copy AST source-inspection test (`test_vision_frame_store_producer_copy.py`) scans every `set_frame(...)` call site and asserts `.copy()` in the same expression.

The shim sweep at v2 closure confirmed clean: zero P0.6 migration scaffolding remains. The `_sync_set_cloud_state`, `_sync_mint_room`, `_sync_add_room_participant`, `_sync_clear_room`, `_sync_set_prev_det_count` functions are documented as **load-bearing public sync API** (NOT shims) — they're the canonical synchronous read/write entry points the pipeline needs for non-async contexts.

---

# Part XL — Typed Session State (P0.7)

## 261. Why Move the Session Dict to a Typed Store

`_active_sessions: dict[str, dict]` in `pipeline.py` carried the entire identity-evidence + voice-evidence + dispute-state + session-lifecycle model. Each per-person entry was a free-form dict with no schema. Code that touched a session field looked like:

```python
_active_sessions[pid]["dispute_set_at"] = time.time()
_active_sessions[pid]["recent_voice_confs"].append(conf)
del _active_sessions[pid]["cached_prefix"]
```

The cost:

- **No schema enforcement.** A typo (`displute_set_at`) silently created a new key. A field rename required grepping every call site.
- **No invariant guards.** A session could be in dispute state (`person_type == "disputed"`) without `dispute_set_at` being set — the auto-clear timeout (Part XV §106) would never fire.
- **Concurrent access.** Tests and background coroutines wrote to the same session dict without coordination.
- **No single-writer principle.** ~190 sites across `pipeline.py` and `test_pipeline.py` wrote directly to the session dict. Any future invariant (e.g. "the engagement gate must always set `bootstrap_credits` to N_INITIAL_VOICE_BOOTSTRAP") had to be defended at every site individually.

P0.7 builds `core/session_state.py` to fix this. The migration was non-trivial — a 5-phase staged sub-PR sequence (P0.7.1 → P0.7.5.D) that ran for ~10 days.

## 262. `core/session_state.py` — Three Dataclasses

```python
@dataclass(slots=True)
class VoiceEvidence:
    voice_match_conf:           float = 0.0
    voice_last_heard_ts:        float = 0.0
    voice_sample_count:         int = 0
    bootstrap_credits:           int = 0
    recent_voice_confs:         list[float] = field(default_factory=list)
    # ... 9 fields total

@dataclass(slots=True)
class Session:
    person_id:                  str
    person_name:                str
    person_type:                str
    started_at:                 float
    last_face_seen:             float = 0.0
    last_spoke_at:              float = 0.0
    dispute_set_at:             Optional[float] = None
    disputed_claimed_name:      Optional[str] = None
    prior_person_type:          Optional[str] = None
    disputed_block_count:       int = 0
    disputed_block_alerted:     bool = False
    voice_only_origin:          bool = False
    voice_face_confirmed:       bool = False
    cached_prefix:              Optional[str] = None
    core_memory:                Optional[dict] = None
    waiting_for_name:           bool = False
    room_session_id:            Optional[str] = None
    user_turns:                 int = 0
    evidence:                   VoiceEvidence = field(default_factory=VoiceEvidence)
    # ... 29 fields total

@dataclass(frozen=True, slots=True)
class SessionSnapshot:
    """Immutable frozen snapshot for read-only access."""
    # Same 29 fields as Session, but every collection is replaced with a new copy
    # at snapshot time. Returned by SessionStore.peek_snapshot().
```

The slots-on-everything is load-bearing: it makes every field assignment a typo into an `AttributeError` at runtime, and it shrinks the per-session memory footprint substantially.

`SessionSnapshot` is the read-only contract. Anywhere in the codebase that needs to read session state (prompt assembly, scene block, KAIROS, brain context) calls `_session_store.peek_snapshot(pid)` and gets back a frozen snapshot whose internal collections are *copies* — mutating them has no effect on the underlying Session.

## 263. `SessionStore` — Single Owner with `asyncio.Lock`

`SessionStore` is the only writer of `_sessions: dict[str, Session]`. Every mutation is async and acquires `self._lock` before touching the dict. Every read is sync and returns either a SessionSnapshot or a plain value (for `peek_<field>` accessors).

The `peek_snapshot(pid)` and `peek_all_snapshots()` methods are sync by design. They copy the underlying Session into a frozen SessionSnapshot at peek time. The same-thread asyncio safety contract (§268) lets them skip the lock — within a single asyncio thread, mutations are serialised between `await` boundaries, so a sync peek can never see a half-mutated session.

## 264. The 21 Named Transition Methods

The migration's *real* value is the named transition methods. They replace ~190 ad-hoc dict mutations with semantically-meaningful operations:

| Method | What it does |
|---|---|
| `open_session(pid, name, person_type, ...)` | Create a fresh Session entry. Engagement-gate-passed callers pass `engagement_gate_passed=True` so `bootstrap_credits` are seeded. |
| `close_session(pid)` | Remove the Session entry. Idempotent — closing a missing session is a no-op. |
| `update_on_reopen(pid, voice_confidence, now)` | Re-open path: refresh voice match conf + last_spoke_at + last_face_seen in one atomic operation. |
| `transition_to_disputed(pid, claimed_name, reason, now)` | Capture `prior_person_type`, set `person_type="disputed"`, set `dispute_set_at`, set `disputed_claimed_name`. |
| `clear_dispute(pid, now)` | Restore `person_type` from `prior_person_type` (fail-closed to `"stranger"` if missing per P0.2). |
| `increment_block_count(pid)` | Bump `disputed_block_count` for the watchdog. |
| `mark_block_alerted(pid)` | Set `disputed_block_alerted=True` (idempotent — fires the watchdog alert exactly once). |
| `update_voice_heard(pid, conf, ts)` | Append to `recent_voice_confs` (with maxlen), update `voice_match_conf`, set `voice_last_heard_ts`. |
| `update_face_seen(pid, ts)` | Set `last_face_seen`. |
| `set_voice_only_origin(pid, value)` | Set the flag captured at engagement-gate pass for voice-only strangers. |
| `set_bootstrap_credits(pid, n)` | Seed bootstrap credits at engagement gate pass. |
| `decrement_bootstrap_credits(pid)` | Consume one credit on a voice-accumulation event. |
| `set_voice_face_confirmed(pid, value)` | Set the flag captured at progressive-enrollment gate pass. |
| `set_core_memory(pid, value)` | Cache the core-memory dict for prompt assembly. |
| `set_room_session_id(pid, rsid)` | Bind a session to a room (Part XXVI §163). |
| `bump_user_turn_count(pid)` | Increment turns for stranger-engagement gate progress. |
| `append_recent_attribution(pid, attr)` | Track the speaker-routing history for debug. |
| `set_cached_prefix(pid, prefix)` | Update the cached prompt prefix for compression. |
| `set_dispute_set_at(pid, ts)` | Anchor the dispute timeout (P0.2 fail-closed default of None means "no timeout yet"). |
| `set_waiting_for_name(pid, value)` | Track stranger-engagement state. |
| `set_person_name(pid, name)` | Rename within the session (after `update_person_name` tool fires). |

Every method has a focused contract. The methods *enforce invariants* — `transition_to_disputed` cannot be called without supplying a `reason`; `clear_dispute` cannot grant privileges higher than `prior_person_type`; `decrement_bootstrap_credits` returns False (no credit available) without mutating if credits are already zero.

## 265. `SessionSnapshot` — Frozen, Sliced, Cheap to Pass Around

The frozen dataclass is the read-only contract. Anywhere in the codebase that needs session state in a logging context, a prompt-assembly context, or a backround coroutine context, the call site does:

```python
_snap = _session_store.peek_snapshot(pid)
if _snap is None:
    return  # session closed
if _is_disputed(_snap):
    # ... handle dispute
```

Snapshots are cheap to create (29 field copies + a few list copies) and impossible to mutate (frozen). They're passed across `await` boundaries safely — the snapshot represents state at a specific point in time and the underlying Session can evolve freely afterwards.

`peek_all_snapshots()` returns a list of snapshots, one per active session. This is the iteration API for code that needs to scan every session (e.g. `_expire_stale_sessions`, the health log's per-session aggregate). The iteration is a snapshot of the dict at peek time; new sessions opened during iteration are not visible (consistent with the "snapshot represents a specific point in time" semantics).

## 266. The 5-Phase Migration (P0.7.1 → P0.7.5)

The migration ran in 5 staged sub-PRs, each one independently shippable:

- **P0.7.1** — Foundation. Build `core/session_state.py` with the three dataclasses + `SessionStore` with the named transition methods. No production wiring yet. 45 behavioral unit tests + 12 structural AST invariants in `tests/test_session_store.py` and `tests/test_session_state_invariants.py`. Autouse `_reset_session_state_between_tests` fixture in both conftest files. **+57 tests (1609 → 1666).**
- **P0.7.2** — Read-path migration. 12 production read sites in `pipeline.py` migrated from `_active_sessions[pid]["field"]` to `_session_store.peek_snapshot(pid).field`. Closure invariant test `tests/test_p072_read_migration_progress.py` AST-scans for unallowed reads and caps at 0. 3 documented dict-read keeps (`_compact_running`, `recent_attributions` ×2) where the deque mutation requires a mutable reference; those use the legacy access pattern with allowlist annotation.
- **P0.7.3** — Lifecycle write-path migration. `_open_session` re-open path, voice_only_origin backfill, core_memory capture, dispute-flip via `transition_to_disputed`, increment_block_count + mark_block_alerted, RIDM dispute path, auto-clear via `clear_dispute`. ~32 production write sites migrated.
- **P0.7.4** — Full migration cleanup. All 32 `_active_sessions[pid]["field"] = value` dual-write lines deleted. `SHIM_DISPATCH` dict deleted. `_shim_mirror_session_field_write` function deleted. All 21 `_shim_set_*` methods deleted from SessionStore. `ALLOWED_LEGACY_READS` emptied to `frozenset()`. Cap=0 in closure invariant test. `peek_all_snapshots()` added so `_expire_stale_sessions` iterates over snapshots instead of dict items.
- **P0.7.5** — Test suite restoration after the migration. ~152 test failures across `test_pipeline.py` and adjacent test files migrated from `_active_sessions` dict API to `_session_store` API (`open_session`, `transition_to_disputed`, etc. via `asyncio.run()`). Sub-PRs: P0.7.5.A (read migration backlog), P0.7.5.B (12 specific fixes), P0.7.5.C (19 session-open tests + production bug fix), P0.7.5.D (latent test regression — `test_update_system_name_rejected_on_empty_user_text_by_default` was passing by accident off residual state). Full suite restored to 1716 passing + 8 failing infra debt.

The staged sequence is the spec-first-review-cycle discipline (Part L §325) at work. Each sub-PR is small enough to review, large enough to make meaningful progress, and the validation gates between phases caught the migration backlog before it cascaded.

## 267. The SHIM Layer and Its Eventual Deletion

P0.7.2 and P0.7.3 used a shim pattern: every dual-write site (`_active_sessions[pid]["field"] = value`) was paired with a corresponding `_session_store._shim_set_<field>(pid, value)` call. The dual-write let the new store stay in sync with the legacy dict while the migration ran. Tests could exercise both paths independently.

P0.7.4 deleted the shims after every production read site was migrated. The cleanup was mechanical: 21 `_shim_set_*` methods deleted from SessionStore, 32 dual-write lines deleted from pipeline.py, the `SHIM_DISPATCH` dict deleted, the `_shim_mirror_session_field_write` helper deleted, the dead SHIM test file `tests/test_p072_session_store_migration.py` deleted (320 lines, 6 test classes — all testing now-deleted infrastructure).

The discipline learned: ship the SHIM with a deadline. The migration phase is when SHIM exists; the cleanup phase is when SHIM is deleted. Leaving SHIM in place "just in case" is the kind of half-finished migration that breeds the next decade of technical debt.

## 268. `peek_all_snapshots` and the Single-Thread-Asyncio Safety Contract

The contract: `peek_snapshot(pid)` and `peek_all_snapshots()` are sync methods that read `self._sessions` without acquiring the lock. They're safe because:

1. **Single asyncio thread.** All async mutations happen on the main asyncio thread. There's no thread pool writing to SessionStore.
2. **Mutations serialise between `await` boundaries.** When `async def set_x(...)` runs, it owns the lock and the field assignments happen synchronously between two `await` points. No other coroutine can interleave.
3. **Sync peek reads are atomic at the field level.** `Session.field` reads in CPython are GIL-atomic for built-in types. The peek returns a new `SessionSnapshot` constructed from a single pass through the fields — no mid-construction visibility.

The empirical proof: P0.6.4's behavioral race test (`test_voice_gallery_concurrent_write_read`) demonstrated the same property on `VoiceGalleryStore` — 1 writer thread + 1000 reader threads against a peek-read pattern produced zero `RuntimeError("dictionary changed size during iteration")` over 1000 cycles.

The contract is documented at the top of `core/session_state.py` so future maintainers don't try to "harden" the peek path with locks (which would break the cheap-read invariant) or to call peeks from a thread pool (which would break the single-asyncio-thread assumption).

## 269. Dispute State via Named Transitions

The dispute state machine (Part XV) used to be ad-hoc — code that wanted to flip a session to disputed wrote `_active_sessions[pid]["person_type"] = "disputed"` directly, possibly forgot to capture `prior_person_type`, possibly forgot to set `dispute_set_at`. P0.7.3 routed all three operations through `transition_to_disputed(pid, claimed_name, reason, now)`:

```python
async def transition_to_disputed(
    self, pid: str, claimed_name: Optional[str], reason: str, now: float
) -> None:
    async with self._lock:
        sess = self._sessions.get(pid)
        if sess is None: return
        sess.prior_person_type = sess.person_type
        sess.person_type = "disputed"
        sess.disputed_claimed_name = claimed_name
        sess.dispute_set_at = now
        # ... emit log
```

Three invariants enforced in one method: prior_person_type captured (P0.2 fail-closed default lands cleanly here), person_type flipped, dispute_set_at anchored. The auto-clear timeout (Part XV §106) now reliably has a timestamp to compare against.

`clear_dispute(pid, now)` does the inverse: restore `person_type` from `prior_person_type` (defaulting to `"stranger"` per P0.2 fail-closed), clear the dispute-tracking fields, log the resolution.

## 270. The Closure Invariants That Lock the Migration

P0.7's three closure invariants:

1. **`tests/test_p072_read_migration_progress.py`** — AST-scans for unallowed dict-read patterns on `_active_sessions`. Cap=0 means any new direct-read regression fails CI. Has 3 documented allowlist entries with explicit `# allowlist:` comments.
2. **`tests/test_session_store.py::TestSessionStoreClosure::test_no_dual_writes_remain`** — AST-scans for `_active_sessions[pid][<field>] = ...` assignments outside the test file. Cap=0.
3. **`tests/test_session_state_invariants.py::test_sync_mutator_allowlist`** — 12 structural tests. Verifies every method on SessionStore that mutates state is `async def`. Allowlist exempts `__init__` and `reset()`.

The combined effect: any future code path that wants to bypass SessionStore must explicitly opt out via the allowlist, and the allowlist is a small enumerable set that reviewers can audit.

---

# Part XLI — Per-Tool Timeout Protection (P0.8)

## 271. The Hang Surface Before P0.8

Every LLM-callable tool handler (Part XII §75) was a branch in a big if/elif chain inside `_execute_tool`. The branches were synchronous in places, async in others, and none of them had a per-tool timeout budget. The visible failure mode: any tool whose underlying I/O hung (SQLite holding a lock, Tavily API stalling, Ollama under load) would freeze the LLM dispatch path indefinitely. The user would say something, the brain would propose a tool, the tool would hang, and the conversation would be dead for the user.

The architectural fix: extract every tool branch into a top-level `async def _handle_<tool>(args, ctx)` function, register them in a module-level `_TOOL_HANDLERS: dict[str, Callable]`, and wrap the dispatch in `asyncio.wait_for` with a per-tool budget. On timeout, `wait_for` cancels the handler task. The cancellation propagates through any open transaction `__aexit__`, rolling back partial SQL writes.

## 272. `_TOOL_HANDLERS` Extraction and `_ToolContext`

The 5 LLM-callable tools (`update_person_name`, `report_identity_mismatch`, `update_system_name`, `shutdown`, `search_memory`) each got their own handler:

```python
async def _handle_update_person_name(args: dict, ctx: _ToolContext) -> str | None:
    # ... handler body verbatim from the prior if/elif branch
    return "handled"  # or "rejected" / "handled_noop" / "shutdown" / None

_TOOL_HANDLERS: dict[str, Callable] = {
    "update_person_name": _handle_update_person_name,
    "report_identity_mismatch": _handle_report_identity_mismatch,
    "update_system_name": _handle_update_system_name,
    "shutdown": _handle_shutdown,
    "search_memory": _handle_search_memory,
}
```

`_ToolContext` is a frozen slots dataclass that carries everything a handler needs (`args`, `person_id`, `person_name`, `db`, `user_text`, `intent_sidecar`, `exec_snap`, `caller_type`). It's built once after the privilege gate fires, then passed into the handler. The handlers all start with a small unpack header (`person_id = ctx.person_id`, etc.) so the moved branch body reads identically to the pre-extraction code.

The extraction discipline was *purely mechanical*: no "while I'm here" changes to handler logic. The tool `tools/extract_tool_handler.py` (idempotent helper) dedents the branch body, builds the `_handle_<tool>(args, ctx)` wrapper, and replaces the original branch with delegation. Each extraction was a single sub-PR with full-suite verification before the next handler.

## 273. `asyncio.wait_for` and the Per-Tool Budgets

`_execute_tool` runs the un-budgeted gates first (Layer 0 unknown filter, repeat guard, privilege gate). Then it dispatches:

```python
budget = TOOL_TIMEOUT_OVERRIDES.get(name, TOOL_TIMEOUT_SECS)
try:
    return await asyncio.wait_for(handler(args, _ctx), timeout=budget)
except asyncio.TimeoutError:
    return "tool_timeout"
```

The per-tool budgets in `core/config.py`:

- `TOOL_TIMEOUT_SECS = 10.0` — default
- `TOOL_TIMEOUT_OVERRIDES = {"search_web": 20.0, "search_memory": 5.0, "update_person_name": 5.0, "update_system_name": 5.0, "shutdown": 3.0, "report_identity_mismatch": 3.0}`

The override for `search_web` is 20s because Tavily does multi-query searches and legitimate live-data queries can take 8-15s. `search_memory` is 5s because it's a fast SQLite query. `shutdown` is 3s because it should be near-instant; a hung shutdown is itself a bug.

The new `tool_timeout` status was added to the taxonomy alongside `handled`/`handled_noop`/`rejected`/`unknown`/`None`/`shutdown`. The `_all_unreal` classifier in `conversation_turn` (Part XII §70) was widened to include `tool_timeout` so the Together.ai/Ollama retry path acknowledges the action didn't complete and the LLM emits a hedged re-ask instead of fabricating "I did it".

## 274. Cancellation Rollback Through Transaction `__aexit__`

The cancellation flow on `asyncio.TimeoutError`:

1. `wait_for` cancels the handler task.
2. `CancelledError` propagates up the handler's call stack.
3. If the handler is inside a `FaceDB.transaction()` or `BrainDB._safe_commit()` block, the `__aexit__` method runs with the exception in flight.
4. `__aexit__` issues `ROLLBACK`, restoring the SQL state to the pre-transaction snapshot.
5. The `CancelledError` re-raises (transaction `__aexit__` does not swallow).
6. `_execute_tool` catches the timeout (which manifests as `TimeoutError` at the `wait_for` level, not `CancelledError`), returns `"tool_timeout"`.

The property is structurally proven by `TestHardCaseCancellationRollback` in `tests/test_tool_timeout.py`: a handler that does 10k `cursor.execute()` inside a transaction with periodic `await asyncio.sleep(0)` every 100 writes, with a forced 1ms timeout mid-loop, ends with `SELECT COUNT(*) == 0` (everything rolled back). The test is structural insurance against a future handler that forgets the periodic checkpoint and locks out cancellation.

## 275. P0.8.1 — Tavily Wrap and the Hidden Inline Consumer

P0.8's wait_for covered every tool in `_TOOL_HANDLERS`. But `search_web` is consumed *inline* inside `ask_stream` (Part XIII §80) — split out of `raw_tool_calls` and handled in-stream, not dispatched through `_TOOL_HANDLERS`. The `wait_for` wrap didn't reach it. The 20s `TOOL_TIMEOUT_OVERRIDES["search_web"]` budget was dead config.

Tavily API hangs are the single most likely real-world hang point. P0.8.1 fixed this with an explicit wrap inside `core.brain._web_search`:

```python
try:
    response = await asyncio.wait_for(
        _tavily_http.post(...),
        timeout=TOOL_TIMEOUT_OVERRIDES.get("search_web", TOOL_TIMEOUT_SECS),
    )
except asyncio.TimeoutError:
    return {"error": "timeout", "hint": "Tavily timed out — answer from training knowledge or honestly acknowledge the network failure (no fabricated search results)."}
```

The returned dict shape matches the existing short-query / empty-query error shape, so both call sites (`ask_stream` and non-streaming `ask`) handle it via the existing `isinstance(result, dict)` branch — timeout surfacing flows through unchanged.

The lesson: **the wait_for wrap must cover every consumer of the underlying I/O**, not just the dispatch path. P0.8's wrap was correct but incomplete; P0.8.1 found the inline consumer and closed it. Future tool work should grep for the underlying I/O call (here `_tavily_http.post`) at audit time, not just trust that wrap-coverage at the dispatcher is sufficient.

## 276. P0.8.2 — F1 + F2 Structural Invariants

Two AST-based CI invariants now enforce the timeout architecture's load-bearing properties:

- **F1 — handler-checkpoint discipline.** Every async handler in `_TOOL_HANDLERS` containing a sync `for` / `while` / `async for` loop with a raw `.execute(...)` call inside MUST also contain `await asyncio.sleep(0)` in the same loop body. Without the checkpoint, `wait_for` cancellation cannot fire mid-loop and transaction rollback never runs. P0.8.1's `TestHardCaseCancellationRollback` proved the property structurally when checkpoints exist; F1 enforces they continue to exist as the codebase grows.
- **F2 — retry-path one-shot guarantee.** `ask_retry_text` MUST internally call `_stream_together_raw(..., include_tools=False)` on every code path. AST scan walks the function body, finds every `_stream_together_raw` invocation, asserts each carries `include_tools=False` as a literal `False` constant (no kwarg / non-literal / `True` all fail). The retry path stays structurally one-shot — no recursive tool dispatch is possible.

The deliberate-regression checks confirmed both invariants fire correctly: F1 caught an injected sync `.execute()` loop without checkpoint in `_handle_search_memory` (assertion mentions `sync loop at line X` + violation explanation), F2 caught `include_tools=True` flip in `ask_retry_text` (assertion mentions `passes include_tools=True — must be the literal False`). Both reverted to green.

The F2 case is the **developer-improves-on-spec** moment for P0.8.2 (Part L §327): the auditor's original prescription targeted call sites in pipeline.py, but the actual contract is internal (`ask_retry_text` doesn't accept `include_tools` as a public parameter by design). The developer's caller audit found the internal contract and the F2 invariant verifies that instead.

---

# Part XLII — Schema Migrations Versioning (P0.9)

## 277. The Drift Problem with Inline `ALTER TABLE` Calls

Pre-P0.9 architecture: every schema change was an inline `ALTER TABLE` call inside the relevant DB class's `_init_tables` or `_migrate` method. Example pattern:

```python
def _init_tables(self) -> None:
    cur = self._conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS persons (...)")
    try:
        cur.execute("ALTER TABLE persons ADD COLUMN preferred_language TEXT")
    except sqlite3.OperationalError:
        pass  # column already exists
    # ... repeat for every historical schema change
```

The pattern works for fresh DBs (CREATE creates everything) and for already-migrated DBs (every ALTER is a no-op via the OperationalError swallow). It breaks on:

1. **Partial-state DBs.** If a backfill migration is half-complete, the ALTER passes (column exists) but the backfill never runs (no idempotency guard, no progress tracking).
2. **Cross-DB ordering.** If migration X on `brain.db` reads a column added by migration Y on `faces.db`, the order is implicit in import order — fragile.
3. **Failed-mid-migration recovery.** If `_init_tables` crashes mid-way, the DB is in an unknown state. No ledger says what completed.
4. **Silent OperationalError swallowing.** Every ALTER `except OperationalError: pass` swallows unrelated errors too (disk full, lock contention).

P0.9 generalises the versioned-ledger pattern that `classifier_scenarios.db` (Spec 1, Session 122) shipped first and applies it to `faces.db` and `brain.db`.

## 278. `core/schema_migrations.py` — The Generalised Helper

Three exports:

- **`init_ledger(conn)`** — self-evolving migration-history table. Creates `schema_migrations(version, description, applied_at, is_initial)` on a fresh DB. On a pre-P0.9 DB that already has a partial ledger, idempotently adds the `is_initial` column via `PRAGMA table_info` + ALTER.
- **`bootstrap_ledger_if_unversioned(conn, migrations)`** — stamps `v=1` baseline on a legacy DB with `is_initial=1`, walks the `migrations` list and stamps each entry whose `verify_present_fn` returns True as `is_initial=1`. Without this, a fresh boot against a legacy DB would crash on `OperationalError: duplicate column name` when the runner tried to re-apply each historical migration.
- **`apply_migrations(conn, migrations)`** — runs pending entries in version order under `BEGIN IMMEDIATE`, calls `apply_fn` then `verify_post_fn` inside the same transaction so a verify failure rolls back the apply (atomic migrate-or-fail).

The transaction wrapping uses the tightened S65 rollback discipline (§282) — only the known "no transaction is active" race is suppressed; unexpected operational errors are loud.

## 279. The 5-Tuple Migration Shape and Why

Every entry in `MIGRATIONS: list[tuple[int, str, Callable, Callable, Callable]]`:

```python
(version, description, apply_fn, verify_post_fn, verify_present_fn)
```

- **`version: int`** — monotonically increasing. Determines apply order.
- **`description: str`** — human-readable label for boot logs (e.g. `"Add preferred_language column to persons"`).
- **`apply_fn(conn) -> None`** — performs the schema mutation. Raises on failure.
- **`verify_post_fn(conn) -> None`** — raises if the post-state is wrong. Used by the runner after apply_fn.
- **`verify_present_fn(conn) -> bool`** — returns True if the migration's effect is already present on disk. Used by bootstrap to decide whether to stamp `is_initial=1` on a legacy DB.

For schema-only migrations (add column, add index, create table) `verify_post` and `verify_present` collapse to the same check. For backfill migrations (e.g. `faces v=9 conversation_log backfill`, `brain v=10 privacy_level remediation`) they diverge meaningfully.

## 280. `verify_post` vs `verify_present` — The Developer-Improved-on-Spec Split

The architect's original spec for P0.9.2 defined a single `verify(conn) -> bool` function per migration. The developer split it into two during implementation, with explicit reasoning that became one of the entries in the developer-improves-on-spec track record (Part L §327).

The split is load-bearing for backfill migrations. Consider `faces v=9` — adds `conversation_memory_archived` column AND backfills all pre-existing rows. The two scenarios:

- **`verify_post`** is used by the runner after `apply_fn`. It must assert "post-condition achieved": column exists AND zero rows have NULL `conversation_memory_archived`.
- **`verify_present`** is used by bootstrap on a legacy DB to decide whether to stamp `is_initial=1`. The right answer is "is the migration's effect already in place?" Which for a backfill means: column exists AND no NULL rows remain.

For most schema-only migrations the two collapse: `verify_present` is "column exists"; `verify_post` is "column exists". For backfills they MUST diverge:

- If the backfill is partially run on a legacy DB, `verify_present` returns False (column exists but NULL rows remain) → bootstrap doesn't stamp → runner runs the migration → `apply_fn` is idempotent (`ALTER TABLE IF NOT EXISTS`) → the backfill completes → `verify_post` confirms completion → ledger stamped.
- With a single function, the partial-state DB would either get stamped at boot (silent data loss — the backfill never finishes) or never reach a stable state.

The split correctly handles partial-migration scenarios. Architecturally, it's the right primitive. The developer's improvement on the architect's spec is documented in the closure report and banked in §327.

## 281. Imp-1 — `isolation_level="IMMEDIATE"` on Every Connect

Python's sqlite3 default `isolation_level` is `""` (deferred). When the connection is in deferred mode, the first write takes a `BEGIN DEFERRED` lock — meaning two concurrent connections can both be reading, and the first to write gets the lock, the second writes upgrade to EXCLUSIVE and may collide.

`FaceDB.transaction()` and `BrainDB.transaction()` issue explicit `BEGIN IMMEDIATE` to take a write lock upfront. But if a *different* connection (one of the 5 connect sites in core/*.py outside the transaction context) is using deferred mode, it can interleave with the IMMEDIATE transaction's writes in unsafe ways.

Imp-1 ships `isolation_level="IMMEDIATE"` on every `sqlite3.connect()` in `core/*.py` (excluding `core/backup.py`'s one-shot file-copy use). 5 connect sites updated: `FaceDB.__init__`, `FaceDB._init_conversation_archive`, two FaceDB archive-read sites, `BrainDB.__init__`, `ClassifierDB.__init__`, plus two `_faces_conn` sites. AST source-inspection test in `tests/test_schema_migrations.py` rejects any future `sqlite3.connect` in core/* that doesn't pass `isolation_level="IMMEDIATE"`.

## 282. Imp-2 — Tightened S65 Rollback Discipline

The S65 race (Session 65 finding): inside `transaction()` `__aexit__`, the rollback is wrapped in `except sqlite3.OperationalError: pass` to swallow the known "no transaction is active" race that occurs when a parallel close races with the rollback. Pre-Imp-2: the swallow was unconditional — it would also silently absorb a disk-full error, a lock-contention error, or a schema mismatch.

The tightening: every `# RACE: S65` rollback site now reads `if "no transaction is active" not in str(_rbe).lower(): print(...); raise`. The known S65 race stays suppressed; everything else is loud. 4 sites tightened: `core/schema_migrations.py::apply_migrations`, `core/db.py::FaceDB.transaction`, `core/db.py::FaceDB.archive_old_conversation_log`, `core/brain_agent.py::BrainDB.transaction`.

AST scan in `tests/test_schema_migrations.py` asserts every `# RACE: S65` site uses the tightened message-check pattern. The discipline is now CI-enforced.

## 283. The 19 Retrofitted Historical Migrations

P0.9 Phase 2 retrofitted 19 historical schema mutations into versioned `MIGRATIONS` lists with full 5-tuple shape: 10 migrations on faces.db (v=2 through v=10), 10 migrations on brain.db (v=2 through v=11), 1 destructive op (`_m_0010_drop_conversation_memory` on faces.db, with the documented S24 cleanup exemption).

Each migration is a verbatim move of the existing inline `ALTER TABLE` from `_init_tables` / `_migrate` — mechanical-extraction discipline (P0.8 lineage). The inline calls KEEP RUNNING in Phase 2 as defense-in-depth — both are idempotent; Phase 3 cleans up the redundancy after live-prod-DB validation.

Two new migration modules house the retrofitted entries: `core/faces_db_migrations.py` (~280 lines) and `core/brain_db_migrations.py` (~270 lines). Each `_m_NNNN_*` function is a verbatim function-extraction of the prior inline code; the migration registry is the only authoritative source for the schema change record.

Pre-Phase-3 validation passed against Jagan's actual production DBs (boot log captured in `terminal_output.md`, 2026-05-17 multi-person session). Phase 3 then deleted the redundant inline calls: `FaceDB._init_tables`'s 2 try/except loops + 1 idx_conv_log_room CREATE + 1 backfill block + DROP TABLE conversation_memory, plus `BrainDB._migrate`'s 10 PRAGMA-guarded ALTERs + privacy_level remediation backfill. `BrainDB._migrate` is now a no-op stub kept for the `__init__` call-chain continuity.

## 284. The Structural Invariants That Lock the Pattern

Four invariants in `tests/test_schema_migrations.py`:

1. **`TestNoIdempotencyTryExceptOutsideRunner`** — AST scan rejects any `try: ALTER/CREATE ...; except sqlite3.OperationalError: pass` pattern in `core/db.py` + `core/brain_agent.py`. Idempotency now lives in the runner only.
2. **`TestNoAlterTableOutsideMigrationModules`** — regex scan rejects any `ALTER TABLE` in `core/db.py` + `core/brain_agent.py`. Lives only in `core/{faces,brain}_db_migrations.py` + the meta-migration in `core/schema_migrations.py`.
3. **`TestNoDestructiveOpsInMigrationBodies`** — AST scan rejects `DROP TABLE` / `DROP COLUMN` / `ALTER TABLE ... RENAME` in `_m_*_apply` bodies, with single documented exemption (`_m_0010_drop_conversation_memory_apply` — S24 legacy cleanup).
4. **Sanity guard** that the exemption's body actually contains the destructive op (catches typos in DOCUMENTED_EXEMPTIONS set).

Plus the 5-tuple invariant: `test_every_entry_is_5_tuple_with_both_verify_companions` asserts both callables present on every migration.

P0.9 closed boot observability with three new log lines on every boot:

- `[Schema] {db_label}: bootstrap stamped baseline v=1 + N pre-existing migration(s) as is_initial=1 (legacy DB)`
- `[Schema] {db_label}: apply_migrations ran 0 pending`
- `[Schema] {db_label}: ledger already versioned`

These are the validation gates that consumed Jagan's live-prod-DB validation in 2026-05-17.

---

# Part XLIII — Legacy Router Deletion and Bug-W Closure (P0.10)

## 285. The Phase 0 Premise Reset

P0.10's original architect framing: "the new reconciler (Part XXXII) is correct; delete the 273-line legacy router (`_resolve_actual_speaker` in `pipeline.py`); ship Plan v1."

Phase 0 audit, before any plan was drafted, ran a grep + behavioral audit of the legacy router's exact decision space and the new reconciler's rule cascade. The finding was load-bearing: **the new reconciler was *not* correct**. It had a 0.3–0.5s coverage gap — the **Bug-W class** — where short utterances (0.3 to 0.5 seconds of audio, just above the `MIN_UTTERANCE_SECS` floor) with an active session could fall through every P0 / P1 / P2 / P3 / P4 / P5 rule and exit the cascade unhandled.

The legacy router's catch-all `return cur_pid, "current"` at the end of `_resolve_actual_speaker` was incidentally papering over the gap. Every short-utterance turn that fell through the cascade just defaulted to "current speaker continues to hold". The pre-P0.10 production system worked correctly *because* of this catch-all, not despite it.

Phase 4 cutover (`ROUTING_USE_RECONCILER=True`, Session 121) had already removed the legacy blanket-hold floor for the in-production routing path. The exposure to Bug-W began at that cutover. The reconciler was running standalone, and any time a short utterance fell through the cascade, the turn was silently dropped (no `RoutingDecision` returned).

Phase 1 v2 plan was rewritten against the corrected premise. The new spec: **fill the cascade's gap with explicit rules, THEN delete the legacy.** The audit saved an entire spec-cycle — Plan v1 as originally written would have shipped legacy deletion → Bug-W active in production → silent turn drops on every short-utterance turn.

This is the **premise-correction sub-pattern** documented in §327 — different from the standard developer-improves-on-spec because it changes WHAT gets built, not just HOW.

## 286. The Bug-W Coverage Gap

The empirical bug: a short utterance (0.3 to 0.5s of audio) from a known speaker who was the current session holder, with no other signal (no face in frame at that exact instant, no voice gallery match strong enough to fire P1, no pyannote multi-segment to fire P4), would hit P0's short-utterance handling — but only `_p0_short_utterance_hard_mismatch` and `_p0_short_utterance_ambiguous_multi_session`, both of which require *some* signal (voice score below floor + session candidates). When there was no signal at all, no rule matched, the cascade returned `no_action`, and the turn was dropped.

The legacy router treated this as "current speaker continues to hold" via its catch-all. The reconciler, designed as a positive-contract rule cascade with no implicit fallback, didn't.

The fix: explicit P0 rule `_p0_short_utterance_gap_hold_current` that fires when audio is between `MIN_UTTERANCE_SECS` and `SHORT_UTTERANCE_FLOOR`, there's an active session, and no signal disqualifies the holder. The rule returns `RoutingDecision(action="current", pid=cur_pid, rule="_p0_short_utterance_gap_hold_current", utt_band="gap", reasoning="short utterance with active session, no disqualifying signal")`.

## 287. `_p0_short_utterance_gap_hold_current` and the `LOWER_BOUND` Attribute

Every P0 rule was given a `LOWER_BOUND` attribute documenting the minimum utterance duration at which the rule is eligible to fire. The new rule fires at `MIN_UTTERANCE_SECS` (currently 0.3s). The pre-existing rules (e.g. `_p0_pure_noise_hold_current`) fire at 0.0s. The architectural invariant: **the cascade's rule order, when sorted by `LOWER_BOUND`, must be non-decreasing**.

This is enforced by `tests/test_reconciler.py::TestRulesOrderingInvariant`. The test reads the cascade's rule list, extracts each rule's `LOWER_BOUND` (default 0.0 if absent), and asserts the list is non-decreasing. Ties are allowed (`_p0_pure_noise_hold_current` and `_p0_short_utterance_no_session` are both at 0.0; `_p0_short_utterance_hard_mismatch` and `_p0_short_utterance_ambiguous_multi_session` are both at 0.5). The point is to catch misorder, not to enforce strict monotonicity.

## 288. The Non-Decreasing Band-Ordering Invariant

The auditor's R1 refinement during plan-v2 review: the ordering test catches misorder but NOT coverage gaps. A new utt_band (e.g. a `medium_utt` band between `short_hard` and `normal`) could be added without any rule explicitly covering it; the cascade would silently fall through every existing rule and exit with `no_action`. Coverage gaps remain a human-review responsibility (the validation window §292 is the empirical safety net).

The pragmatic stance: an AST-level "every band must have at least one rule firing in it" test would require a static map from band → expected_rules. P0.10.1 ships exactly that map (§291).

## 289. The Band-Divergence Block C Trigger

The Reconciler-Shadow block at `pipeline.py:7100+` (the divergence log between legacy and new routing) needed to be retargeted when the legacy was deleted. The original "legacy != new" trigger became unworkable — there's no legacy decision to compare against.

The developer-improved-on-spec trigger: **band-divergence**. The block fires when the utt_band of the firing rule (read from the `utt_band` tag the rule sets on its `RoutingDecision`) doesn't match the band the architect expected for that band (per the `EXPECTED_RULES_BY_BAND` map in §291). If a `gap` band utterance fires a `short_hard` rule, the divergence log warns; if a `short_hard` band fires a `normal` rule, same.

The developer's reasoning at closure: the architect's spec said "extend the existing divergence-log block with more fields, don't change trigger" — but Step 7's legacy deletion made the original trigger untestable. The band-divergence trigger preserves the architectural intent (catch divergences between expected and actual routing) while changing the mechanism. This is the 4th instance of developer-improves-on-spec banked in §327.

## 290. Phase 2 Cutover and the –15 / +40 Coverage Shift

Phase 2 (legacy deletion) shipped on 2026-05-17. Net test count change: **–15 tests, but +40 architectural-coverage tests**.

The math: Phase 1 added +35 contract/invariant tests, Phase 2 added +4 AST/N7 source-inspection tests, P0.10.1 polish added +1 EXPECTED_RULES_BY_BAND structural invariant — total +40. Phase 2 deletion of `_resolve_actual_speaker` + its 54 legacy `test_pipeline.py` tests subtracted –54. Net: –15 raw tests.

**This is not a coverage regression.** It's the natural outcome of legacy-deletion with replacement. Coverage shifted from "legacy 270-line function tests" (which tested implementation details of the legacy function: dispute-flip handling, scene-candidate counting, offscreen-floor calculation, etc.) to "rule-cascade + invariant tests" (which test architectural properties of the new reconciler: per-rule behavior, ordering, band-coverage, etc.).

The new tests test stronger properties. The deleted tests tested weaker properties (specific implementations of those weaker properties). The architectural coverage measurably increased; the raw test count decreased. Future maintainers should not misread P0.10's test count as a coverage regression.

## 291. P0.10.1 — `EXPECTED_RULES_BY_BAND` Lock

P0.10.1 closed the band-coverage gap that R1 review flagged. A static map in `core/reconciler.py`:

```python
EXPECTED_RULES_BY_BAND: dict[str, frozenset[str]] = {
    "noise":        frozenset({"_p0_pure_noise_hold_current", "_p0_short_utterance_no_session"}),
    "gap":          frozenset({"_p0_short_utterance_gap_hold_current"}),
    "short_hard":   frozenset({"_p0_short_utterance_hard_mismatch", "_p0_short_utterance_ambiguous_multi_session"}),
    "normal":       frozenset({"_p1_confident_voice_switch", "_p2_face_assist_switch", ...}),
}
```

The structural invariant: `test_every_band_has_rules()` asserts every band in `EXPECTED_RULES_BY_BAND` has at least one rule registered, and every rule's `utt_band` tag matches at least one band in the map. The map is the single source of truth for the band-divergence trigger and the per-band rule coverage assertion.

## 292. The Validation Runbook and Gate Criteria

`tests/p0_10_validation_runbook.md` is the daily-checklist file for the validation window opened by Phase 2 cutover. The gate criteria are explicit:

- Zero `[Reconciler] WARN: no rule fired` log lines for 7 consecutive days of normal use.
- Zero band-divergence log warnings for 7 consecutive days.
- The B2 fail-safe (when `_rc_decision is None`, the pipeline holds current and logs) must not fire.

Closure of the validation window unlocks the follow-up PR:
- DELETES the shadow block (`pipeline.py:7100+` Reconciler-Shadow logging code)
- DELETES `ROUTING_USE_RECONCILER` flag from `core/config.py`
- DELETES the B2 fail-safe and its corresponding tests
- KEEPS the new reconciler rule + LOWER_BOUND attrs + Bug-W regression test + RULES-ordering invariant + N2-N6 contracts + AST single-write-site test + EXPECTED_RULES_BY_BAND map + band-coverage invariant

As of 2026-05-18 the window is OPEN. Validation pending the next 7 days of canary use.

---

# Part XLIV — State Race Hardening (P0.11)

## 293. Preventive Hardening for a Latent Race

`core.state._persistent: dict` carries the cross-turn persistent settings (the anti-spoof enabled flag, the language, the system name's display-form preference). The dict is mutated by `set_persistent(key, value)` and read by `state.write()` (which serialises the entire dict to `state.json` for the dashboard IPC).

The race that P0.11 hardens against: a writer mutates `_persistent[key] = value` (in-place subscript assignment) while a reader iterates `**_persistent` inside the JSON serialisation. CPython does not guarantee iteration consistency under concurrent mutation — `RuntimeError("dictionary changed size during iteration")` is the visible failure; torn iteration (reader sees half-mutated state) is the invisible failure.

The race has **never been observed in production**. The single writer (`pipeline.py:6264 state.set_persistent("anti_spoof_enabled", _)`) runs ONCE at startup, before the event loop, before any reader can run. P0.11 closes the door against three latent activation conditions:

1. A future runtime `set_persistent` call lands after startup.
2. `state.write()` is moved off the asyncio loop into an executor thread.
3. `state.write()` gains an `await` point and the writer interleaves between `**_persistent` spread and JSON dump.

## 294. The Atomic-Replace Pattern and Why It Works

The production change in `core/state.py:16-31`:

```python
def set_persistent(key: str, value) -> None:
    global _persistent
    _persistent = {**_persistent, key: value}  # atomic replace via STORE_NAME
```

The pattern: never mutate `_persistent` in place. Build a new dict with `{**_persistent, key: value}` and rebind the module-level name. CPython's `STORE_NAME` bytecode is GIL-atomic — the rebind completes in one bytecode instruction, no possibility of a half-rebind.

Concurrent readers holding the OLD dict reference (e.g. mid-iteration in `state.write()`) see the consistent old snapshot through to completion. The new dict only becomes visible to readers on next dereference of `_persistent`. The race goes away because there is never a half-mutated state visible to any observer.

The docstring is honest about scope: this protects readers from torn iteration. It does NOT protect against concurrent *writers* losing updates (the RMW race — two writers both reading the old dict, both writing back with their respective single updates; one update is lost). Multi-writer correctness would require explicit `threading.Lock`, which is deferred until runtime writers actually land.

## 295. Three Deliberate-Regression Checks and the Detector-Strengthening Cycle

P0.11's induction protocol ran three deliberate-regression checks:

1. **Revert `set_persistent` to `_persistent[key]=value`** → `tests/test_state_race.py::test_no_subscript_assign_in_state_py` fired with `core/state.py:30: subscript-assign forbidden`. Reverted to atomic-replace.
2. **Drop the `global _persistent` decl from `set_persistent`** → `test_state_py_rebind_with_global` fired with `function 'set_persistent' rebinds _persistent without declaring global`. Without `global`, the assignment creates a function-local variable, the rebind doesn't propagate, and the module-level dict is silently never updated. Reverted.
3. **Inject `state._persistent["regression_check_3"]=True` in `pipeline.py:6265`** (attribute-form access from outside the state module) → `test_no_subscript_assign_in_repo` fired with `pipeline.py:6265: subscript-assign forbidden (attribute-form)`.

The third check **surfaced a detector gap** in the original AST scanner. The initial detector only caught bare-name subscript-assign (`_persistent[X]=Y` inside `core/state.py`). The deliberate regression injected attribute-form access (`state._persistent[X]=Y` from `pipeline.py`). The original detector didn't see it. The detector was strengthened in the same cycle to catch BOTH shapes (bare-name AND attribute-form).

This is the canonical induction-surfaces-invariant-gaps moment (Part L §322). The discipline working as designed: deliberate-regression check identifies a gap, the gap is closed in the same sub-PR, the invariant becomes load-bearing rather than theatrical. P0.11's count: 3 deliberate-regressions, 3 fires, 1 detector strengthening, all confirmed.

---

# Part XLV — JSON Parser Hardening (P0.12 + P0.12.1)

## 296. Why Property-Based Testing

The pre-P0.12 `core/brain_agent.py::_parse_json` and `core/brain.py::_parse_intent_sidecar` carried failure modes that example-based tests couldn't cover:

- Arbitrary text the LLM hallucinated as JSON (`raw='0'`, `raw='[1,2,3]'`, `raw='"just a string"'`)
- Truncated JSON streams (mid-tokens)
- Markdown code-fence wrappers (` ```json\n{...}\n``` `)
- Doubled keys (Python's `json.loads` contract: last wins)
- Unescaped nested quotes
- Trailing commas
- BOM + leading whitespace
- Surrogate / control / format unicode
- Empty / whitespace-only input
- Extremely large input (1 MB repeated payload + N-key dicts up to 5000)
- Deeply nested (`[`×N + `]`×N AND `{"a":` ×N — up to 2000 depth)
- Python 3.11+ `ValueError` on oversized integer string conversion (the new `sys.get_int_max_str_digits()=4300` DoS limit)

The combinatorial space defeats hand-curated test cases. P0.12 introduced **Hypothesis property-based testing** with `max_examples=1000` per test. Hypothesis searches the input space, shrinks failing cases to minimal reproducers, and surfaces real production bugs in the same sub-PR.

## 297. The Two Production Bugs Hypothesis Surfaced

**Bug 1 — `_parse_json` contract violation.** The type annotation declared `dict | None`, but the strict `json.loads(raw)` path returned WHATEVER `json.loads` produced. For `raw="0"` it returned `int`. For `raw="[1,2,3]"` it returned `list`. For `raw='"string"'` it returned `str`. Callers (7+ extraction agents in `core/brain_agent.py`) do `parsed.get(...)` assuming dict → silent `AttributeError` at runtime on any non-dict valid JSON.

Hypothesis's `TestArbitraryText` shrank the falsifying input to `raw='0'` (minimal possible JSON-parsable string that returns non-dict). Fix: added `return result if isinstance(result, dict) else None` gate. The contract is now structurally enforced — the dict|None type annotation matches the runtime behavior.

**Bug 2 — `_parse_intent_sidecar` uncaught ValueError.** Input with a 5000-digit integer literal triggered Python 3.11+'s `sys.get_int_max_str_digits()=4300` DoS limit, raising `ValueError` (not `JSONDecodeError`). The original except clause caught `(json.JSONDecodeError,)` exclusively. An adversarial LLM output could crash the parser.

Hypothesis's `TestLargeInput` shrank to `payload='1'` (Hypothesis-simplified to a long run of '1's exceeding the limit). Fix: extended except clauses on both code paths to `(json.JSONDecodeError, RecursionError, ValueError)`.

Both bugs got dedicated regression tests pinned to their falsifying inputs (`test_bug1_parse_json_returns_none_for_non_dict_top_level`, `test_bug2_parse_intent_sidecar_handles_oversized_int_string`, plus source-inspection guard `test_bug1_fix_visible_in_source` that catches future reverts via `inspect.getsource` + AST-style string check on the dict-isinstance gate).

CI cost: full Hypothesis suite runs in ~12s. Well under the 60s budget.

The lesson banked: **Hypothesis is a structural-validation tool, not a quality nice-to-have.** It finds bugs example-based tests can't reach. Standard practice now is `max_examples=1000` for contract surfaces (parsers, validators, serializers).

## 298. P0.12.1 — The SocialGraphAgent Dead-Branch Audit

P0.12 narrowed `_parse_json`'s return type to `dict | None`. The auditor's follow-up caller audit found one downstream regression: `SocialGraphAgent.extract` had an `isinstance(data, list)` branch handling the case where the LLM returned a top-level array. After P0.12's narrowing, `_parse_json` would return None instead of the list, so the list branch became unreachable and the extraction silently dropped list-shaped responses.

The other 6 caller audit findings: all handled None defensively via `if data is None: return []` or equivalent before `.get(...)`. PrivacyClassifier was an auditor false positive — its caller already had a dual-guard `if not parsed or not isinstance(parsed, dict): return None` that catches the case.

## 299. `_parse_json_array` — The Sibling Parser

Fix: added sibling `_parse_json_array(raw) -> list | None` in `core/brain_agent.py` with the same brace-salvage discipline but `[`/`]` markers and the same `RecursionError`/`ValueError` catches. SocialGraphAgent.extract now tries dict-wrapper shape first (matches what `response_format={"type":"json_object"}` asks for), then `_parse_json_array` fallback for raw-array LLM responses.

`_parse_json`'s narrow `dict | None` contract is preserved — no risk to the other 6 callers. The sibling parser is the right primitive for callers that legitimately want a list. Future contract surfaces (a third top-level shape, e.g. a string with embedded JSON) would add their own `_parse_json_X` sibling rather than re-broadening `_parse_json`.

Source-inspection regression test `test_p012_1_site_a_privacy_classifier_guards_none` pins the PrivacyClassifier dual-guard so future refactors can't strip it. Behavioral test `test_p012_1_site_b_socialgraph_recovers_raw_array` monkeypatches the LLM call to return raw `[{"name":"Sarah"},{"name":"Mike"}]` array, asserts both names recovered.

---

# Part XLVI — Health and Disk Observability (Wave 5)

## 300. The Health-Pulse Cadence

`core/health.py` emits a one-line system pulse every `HEALTH_LOG_INTERVAL_SECS=300s` (5 minutes). The pulse is a passive observability signal — operators can grep `terminal_output.md` for `[Health]` lines and see the system's state over time without needing a dashboard.

`_emit_health()` runs the gather operation in an executor (`loop.run_in_executor(None, gather_health_snapshot)`) so the snapshot doesn't block the asyncio loop. The format helper (`format_health_line`) builds a single ≤200-character line; the alerts helper (`format_health_alerts`) emits zero or more `[Health-Alert]` lines for non-healthy conditions.

The first emission fires immediately at boot (not at the first 5-minute mark) so operators see the baseline state right away. Both functions are wrapped in `try/except` with logged errors so a health-log bug can never break the production pipeline.

## 301. `HealthSnapshot` and the One-Line Format

The dataclass:

```python
@dataclass
class HealthSnapshot:
    timestamp: float
    active_sessions: int
    sessions_by_type: dict[str, int]
    persons_count: int
    total_face_embeddings: int
    knowledge_active_rows: int
    shadow_persons_count: int
    classifier_scenarios_active: int
    classifier_scenarios_quarantined: int
    cloud_state: str
    active_disputes: int
    unresolved_watchdog_alerts: int
    last_dream_run_seconds_ago: Optional[float]
    thin_voice_galleries: int
    # P0.0.7 D8.1 additions:
    event_log_drops: int = 0
    event_log_emit_failures: int = 0
```

The one-line format prints time + the most-actionable fields:

```
[Health] 14:23 sessions=2(best_friend=1,known=1) persons=4 emb=120 knowledge=842 shadow=3 scenarios=2071/0 cloud=ONLINE disputes=0 watchdog=0 dream=8m_ago thin=0
```

Plus the event-log fields (event_log_drops + event_log_emit_failures) appended when either is non-zero (P0.0.7 D8.2 conditional surfacing, see §321).

The `format_health_alerts` function emits per-condition `[Health-Alert]` lines:
- Active disputes (one per disputed person, with the dispute timestamp)
- Unresolved watchdog alerts (one per unresolved alert, with severity)
- Thin voice galleries (one per person whose voice profile is under `VOICE_ACCUM_MATURE_SAMPLE_COUNT`)
- Event log drops + emit failures (P0.0.7 D8.3)

The alerts are designed to be greppable: `grep [Health-Alert] terminal_output.md` gives an operator a complete list of all active issues without needing to read the per-turn logs.

## 302. Three-Level Disk Alerts with Idempotent Transitions

`core/disk_monitor.py` watches three paths: `faces/`, `data/`, and the project root. Each is sampled via `shutil.disk_usage` plus a per-directory recursive walk for size aggregation. The three thresholds:

- `DISK_ALERT_WARNING_PCT = 80` — first alert level (warning)
- `DISK_ALERT_CRITICAL_PCT = 90` — second level (critical, escalated)
- `DISK_ALERT_BLOCKER_PCT = 95` — third level (blocker, system may stop accepting writes soon)

Threshold crossings are **idempotent**: a per-path module-level state dict `_last_disk_alert_level` tracks the most-recent alert level for each path. When the current usage moves to a higher level, the alert fires (one log line + one `WatchdogAgent.report_disk_threshold(...)` call). When usage stays at the same level, no re-fire. When usage drops (e.g. after a cleanup), the level is reset.

This is the same idempotent-transitions pattern P0.6.6's `transition_to_online` uses (§256). The WatchdogAgent receives at most one report per level transition; it persists to `brain.db.watchdog_alerts` (Session 42's table) with `severity ∈ {warning, critical, blocker}`.

The disk-monitor + health-monitor are emitted together every 5 minutes from `_emit_health()`. Operators see the full state in one block. The combined Wave 5 work (Items 19+20) added +14 tests (8 health + 6 disk) and provided passive observability for two failure surfaces that previously had no observability at all.

---

# Part XLVII — Conversation Hygiene and Memory Consolidation (Wave 6)

## 303. Hard-Delete Pruning of Invalidated Knowledge

Pre-Wave-6, the `knowledge` table on `brain.db` accumulated rows indefinitely. The `invalidated_at` timestamp marked rows as no-longer-valid (set by `ContradictionAgent.check` when a new fact replaced an old one) but the rows themselves stayed in the table forever. After a year of use, the table could grow to 100k+ rows of historical invalidations — slow queries, large backup files, increasing index sizes.

`BrainDB.hard_delete_invalidated_knowledge(cutoff_days, now)` deletes rows where `invalidated_at < cutoff_ts` (`cutoff_ts = now - cutoff_days * 86400`). The retention default is `KNOWLEDGE_HARD_DELETE_DAYS = 90` — invalidated rows from the last 3 months stay in case retroactive analysis needs them; older ones are gone.

Wired into the dream loop (`_dream_loop` in `pipeline.py`) via `run_in_executor` so the bulk delete doesn't block the asyncio loop. The dream loop runs the hard-delete once per cycle (default every 5 minutes idle, or every 3 hours active). +3 tests in `tests/test_hard_delete_invalidated.py`.

## 304. SHA-256 Scene-Block Cache

`_build_scene_block(...)` (Part X §64) runs on every turn. Its inputs are 4 collections: `_active_sessions`, `_persons_in_frame`, `_unrecognized_tracks`, plus the `now` timestamp. Across turns these collections often don't change at all (a quiet room with one stable speaker stays stable for many turns). Rebuilding the scene block on every turn re-runs the dispute precedence logic, the visible-person enumeration, the voice-only-offscreen rendering, and the safety-flag aggregation. All wasted work when nothing has changed.

Wave 6 Item 23: the scene block now caches by **SHA-256 of all inputs**. The cache key is `sha256(json.dumps(canonical_inputs, sort_keys=True))`. On a cache hit, the previously-built block string is returned directly. On a miss, the block is built and cached under the new key.

The cache is owned by `pipeline.py` as a module-level dict; tested in `tests/test_scene_block_cache.py` via 4 source-inspection tests confirming the cache key contains the right input components, the cache hit path skips the build, the cache invalidates correctly on input change, and the cache survives across turn boundaries (cleared only on factory reset). Gated by `SCENE_BLOCK_CACHE_ENABLED = True` in `core/config.py`.

The empirical hit rate in normal use is ~60-80% (quiet room turns) and drops to ~10-20% in active multi-person rooms with changing visibility. The cumulative latency win is substantial; the cache cost is negligible (one SHA-256 + dict lookup per turn).

## 305. `conversation_log` Archival via ATTACH DATABASE

The `conversation_log` table on `faces.db` grew indefinitely (Session 24's `CONVERSATION_HISTORY_LIMIT=100` only limits in-memory load, not on-disk storage). After 6 months of use, `faces.db` could be 500+ MB just from conversation history. Vacuum + index rebuilds get slow; backups get large; the working set for hot queries (recent turns) is degraded by all the cold storage.

Wave 6 Item 21: archive old rows into a companion DB. The pattern:

- `CONVERSATION_ARCHIVE_ENABLED = True` and `CONVERSATION_ARCHIVE_AFTER_DAYS = 30` in `core/config.py`. Rows older than 30 days are eligible for archival.
- The companion DB is `faces_conversation_archive.db` (same directory, same schema, same WAL, same index `idx_conv_log_room`). Built on first archival run.
- `FaceDB.archive_old_conversation_log(cutoff_days, now)` uses `ATTACH DATABASE` + `BEGIN EXCLUSIVE` for atomic `INSERT INTO archive.conversation_log SELECT ... → DELETE FROM main.conversation_log WHERE ...`. The atomicity guarantees no rows are lost on crash mid-archival.
- `load_conversation_history()` and `search_conversation()` each open a short-lived connection to the archive DB (separate from the main FaceDB connection, to avoid ATTACH conflict with the write path) and UNION-merge results with the primary DB.

Wired into the dream loop alongside the hard-delete (§303). The two run sequentially: hard-delete invalidated knowledge, then archive old conversation_log rows. +6 behavioural tests in `tests/test_conversation_archive.py`: moves old rows, keeps recent, idempotent, correct count, load_history includes archive, search includes archive.

The combined effect of P0.5/P0.X (atomicity) + P0.9 (versioning) + Wave 6 (archival) is that the persistence layer has become significantly more durable, observable, and bounded.

---

# Part XLVIII — Tiered CI Scaffold and S2 Deferral Tripwire (P0.0 + P0.0.1 + P0.0.2)

## 306. Three Workflows — Fast, Slow, Security

P0.0 shipped the project's first CI configuration. Three GitHub Actions workflows in `.github/workflows/`:

| Workflow | Trigger | Target | Scope |
|---|---|---|---|
| `fast.yml` | every push + PR | ≤5 min | `pytest -m "not slow and not network and not models"` + ruff + mypy permissive |
| `slow.yml` | nightly + manual via `workflow_dispatch` | unconstrained | full suite, HF model cache via `actions/cache`, `--run-network` when `TOGETHER_API_KEY` secret is set |
| `security.yml` | weekly + on `requirements.txt` change | quick | `pip-audit` + Trivy filesystem scan with SARIF upload to GitHub Security tab |

The split fixes the chicken-and-egg problem of CI for a project with heavy local-model dependencies. Fast CI runs on every PR and catches structural regressions in seconds. Slow CI runs nightly with model downloads + network access for full coverage. Security CI runs weekly to catch upstream vulnerabilities without paying the cost on every PR.

## 307. Pytest Markers and the Infra-Debt Allowlist

`pytest.ini` extended with the `models` marker (alongside the pre-existing `slow` and `network` markers). 15 tests now carry `@pytest.mark.slow @pytest.mark.models` so fast CI skips them — these are the SpeechBrain / pyannote / faster-whisper / torchaudio integration tests that need the heavyweight model assets.

The infra-debt allowlist lives in `tests/test_infra_debt_allowlist.py::INFRA_DEBT_FAILURES`. Currently 9 entries: 1 torchaudio DLL crash + 1 SpeechBrain logger suppression + 6 pyannote diarize tests + 1 pre-existing ECAPA-DLL diarize test. Each entry is a `(test_id, rationale)` tuple documenting why the test is on the allowlist.

The allowlist itself is a rationale-registry, not a behavior-control. The actual disposition on the tests is `@pytest.mark.xfail(strict=False, reason=...)` decorators applied in P0.0.2 (§309).

## 308. The S2 Tripwire and the Theater That P0.0.1 Closed

S2 is the "dashboard authentication" deferred item in the security backlog. The deferral premise: "the dashboard is bound to `127.0.0.1`, no LAN exposure today, ship auth (S2) later when the dashboard becomes LAN-accessible". A deferred item is safe IF AND ONLY IF the premise it deferred on continues to hold.

`tests/test_dashboard_bind_tripwire.py` is the structural tripwire that locks the precondition. The test scans `Kara-OS-dashboard/package.json` for the `dev` and `start` scripts and asserts they're explicitly bound to localhost.

**The theater P0.0 originally shipped:** the v1 tripwire asserted *absence* of `--hostname 0.0.0.0` (any explicit LAN bind), on the false premise that "no explicit LAN bind" meant "localhost". Next.js's actual behavior when `--hostname` is unspecified is to bind to `0.0.0.0` (LAN-accessible). The absence-of-flag check was theatrical — the dashboard was LAN-accessible whenever `npm run dev` was running, and the tripwire happily passed.

P0.0.1 closed the gap. The fix (2 lines in `Kara-OS-dashboard/package.json`): `dev` and `start` scripts now contain `--hostname 127.0.0.1 --port 3000` explicitly. The tripwire was tightened to REQUIRE the explicit flag rather than absence-of-LAN. The test was renamed from `test_dashboard_package_json_scripts_dont_bind_lan` to `test_dashboard_package_json_scripts_explicitly_bind_localhost`, asserting `_find_explicit_hostname_in_command` returns a value AND that the value is in `{127.0.0.1, localhost, ::1}`.

The empirical lesson banked in §328: **tripwires must catch the actual failure mode the deferral leaves unsafe, NOT just the symbolic version that pattern-matches the surface description**. P0.0.1 is one of the 3 instances on the track record.

## 309. P0.0.2 — V1 xfail Bundling for Infra-Debt Tests

The 8 infra-debt failures on the allowlist now carry `@pytest.mark.xfail(strict=False, reason=...)` decorators with explicit P0.0.2 reason strings cross-referencing the allowlist. `strict=False` means an unexpected PASS surfaces as XPASS (notable, doesn't break CI) — the signal that infra debt was resolved.

Slow CI now reports `715 passed, 9 xfailed, 0 failed` instead of `715 passed, 8 failed`. The 9th xfail is the pre-existing ECAPA-DLL diarize.

New structural lock `tests/test_infra_debt_allowlist.py::test_xfail_decorators_align_with_allowlist` AST-scans `test_pipeline.py` and asserts every name in `INFRA_DEBT_FAILURES` carries a `pytest.mark.xfail` decorator. The test catches half-fixes — removing the decorator without removing the allowlist entry, or vice versa.

The discipline this lock encodes: the allowlist and the xfail decorators are *dual artifacts of the same disposition*. When infra debt is genuinely fixed, both must be removed in the same commit. When new infra debt is added, both must be added in the same commit. The structural lock prevents either half from drifting.

Deliberate-regression check confirmed (induction-surfaces-invariant-gaps discipline): (a) forced one xfail test to trivially pass → XPASS surfaced cleanly + suite still green; (b) removed an xfail decorator → alignment test fired with full S2-style remediation message; (c) restored → alignment test passes.

---

# Part XLIX — Event Log and Replay Harness (P0.0.7)

## 310. Why Event-Sourcing the Boundary

P0.0.7 ships the system's first event-sourcing layer. Every input crossing the runtime boundary (microphone audio → audio_in event; camera frame → vision_frame event; identity claim → identity_claim event; routing decision → routing_decision event; ...) emits a typed event into a SQLite table that can be replayed later for debugging or regression testing.

The motivation is concrete: the next P0 work (P0.S1 — anti-spoof on every face match) needs regression tests that exercise the anti-spoof gate on a *captured* sequence of camera frames + voice signals + routing decisions. Without event-sourcing, those tests would need live camera input (expensive, flaky, non-deterministic). With event-sourcing, the test loads a captured event chain from a fixture, replays it through the system, and asserts the anti-spoof gate behaves correctly.

The architecture is plain: a `event_log` table on `brain.db` with rows `(id, ts, session_id, room_session_id, event_type, schema_version, payload, parent_event_id)`, an async producer that emits events, a read-only CLI for inspecting the log, scenario-builder fixtures for tests, and health-log integration so degradation is observable.

## 311. The 12 Payload Types

`core/event_log/types.py` defines 12 dataclasses, one per event type:

| Event type | Payload class | What it captures |
|---|---|---|
| `audio_in` | `AudioInPayload` | Microphone audio chunk + STT text + language + duration |
| `vision_frame` | `VisionFramePayload` | Camera frame metadata + frame_id + frame_path (NOT inline bytes) + **anti_spoof_live** + **anti_spoof_score** (the load-bearing P0.S1 fields) |
| `identity_claim` | `IdentityClaimPayload` | Voice-channel `IdentityClaim` (Part XXXII §199) flattened to JSON |
| `presence_state` | `PresenceStatePayload` | Vision-channel `PresenceState` (Part XXXII §200) flattened to JSON |
| `routing_decision` | `RoutingDecisionPayload` | Reconciler's `RoutingDecision` + `utt_band` tag |
| `intent_classification` | `IntentClassificationPayload` | Classifier output (graph or LLM mode) |
| `tool_call` | `ToolCallPayload` | LLM-proposed tool name + args + person_id |
| `tool_result` | `ToolResultPayload` | Tool handler's return status |
| `memory_write` | `MemoryWritePayload` | Conversation log write |
| `state_write` | `StateWritePayload` | `state.json` IPC write |
| `tts_out` | `TtsOutPayload` | TTS synthesis trigger + clean text |
| `session_lifecycle` | `SessionLifecyclePayload` | Open / close event + pid + name + person_type |

`EVENT_TYPES = frozenset(...)` enumerates the 12 names. `SCHEMA_VERSIONS = {(event_type, schema_version): payload_class}` — the dispatch table keyed on `(event_type, schema_version)` (§313).

Every payload class has a `from_json_dict(json_dict, schema_version)` classmethod that reconstructs the dataclass from the deserialised JSON. This is the C2 replay-deserialization contract — the CLI and the replay tests both consume events via this contract.

## 312. `NATURAL_PARENT_PAIRS` and Causal-Chain Auto-Resolution

Some event sequences have causal structure. A tool_result is caused by a tool_call. An identity_claim is caused by an audio_in. A routing_decision is caused by an identity_claim. Linking child events to their parents lets the replay tool render natural chains as trees.

`NATURAL_PARENT_PAIRS = frozenset({...})` is the registry of allowed (child_type, parent_type) edges:

```python
NATURAL_PARENT_PAIRS = frozenset({
    ("tool_result", "tool_call"),
    ("identity_claim", "audio_in"),
    ("routing_decision", "identity_claim"),
})
```

The producer auto-resolves parent_event_id when emitting a child event: it consults `_recent_parent[session_id]` (§315) for the most recent event of the matching parent_type, sets `parent_event_id` to that event's id, and falls back to NULL if no parent is in the cache. Manual override via the `parent_event_id` kwarg is supported but rare.

Only the natural-pair edges are auto-resolved. Other causal relationships (memory_write → routing_decision, tts_out → routing_decision, intent_classification → audio_in) are tracked elsewhere or simply unwired in the current schema. The natural-pair set is a conservative starting point; additional edges land when replay analysis surfaces concrete need (§339).

## 313. `_PAYLOAD_CLASSES` and the Deserialization Contract

`_PAYLOAD_CLASSES: dict[tuple[str, int], type] = {(event_type, schema_version): payload_class, ...}` is the dispatch table. The CLI and the replay tests look up `(event_type, schema_version)` in the table, call `cls.from_json_dict(payload_dict, schema_version=schema_version)` to reconstruct the typed dataclass, and use the typed object for assertions / rendering.

Schema versioning is per-event-type. A future change to `IdentityClaimPayload` (e.g. adding a new field) ships as `IdentityClaimPayloadV2` with `schema_version=2`. The dispatch table gains a `("identity_claim", 2)` entry pointing to the new class. Old rows in the DB (with `schema_version=1`) still deserialise correctly via the old class. The replay CLI handles both versions transparently.

`test_d_schema_version_dispatch_keys_on_event_type_and_version` in `tests/test_event_log_replay.py` verifies the dispatch behavior: a mock `("tts_out", 2)` → `TtsOutPayloadV2` entry added to the dispatch table; v1 rows still resolve to the original class. The CLI's fallback path handles unknown schema_versions by falling back to truncated JSON dump (no crash).

## 314. Producer Anatomy — `emit`, `emit_sync`, `safe_emit_sync`

Three producer functions in `core/event_log/producer.py`:

- **`async def emit(event_type, payload, *, session_id, room_session_id, parent_event_id)`** — primary async path. Builds the row dict, resolves parent_event_id via `_recent_parent` cache, JSON-serialises the payload, enqueues onto the bounded `asyncio.Queue`. Returns the event_id assigned by the writer task. Used in async contexts.
- **`def emit_sync(event_type, payload, ...) -> int`** — sync wrapper for callers in non-async contexts (database trigger callbacks, signal handlers). Submits the emit task to the running loop via `asyncio.run_coroutine_threadsafe` and awaits its result. Same contract as async `emit`.
- **`def safe_emit_sync(event_type, payload, ...) -> Optional[int]`** — swallowing wrapper around `emit_sync`. Catches every exception, increments `_safe_emit_failure_count`, logs a `[EventLog] WARN` line (rate-limited to first 3 failures), returns None. **The single annotated except block here satisfies P0.4's silent-except invariant for the entire 12-call-site hook surface.**

The `safe_emit_sync` consolidation is the **developer-improves-on-spec** 5th instance banked in §327. The auditor's original P0.4 remediation prescribed annotating the 12 per-call-site try/except blocks with `# OPTIONAL:`. The developer's response: consolidate to a single helper with one annotated except — 12 violations → 1 annotated except + 12 unannotated call sites; future hooks automatically inherit the swallow-discipline.

## 315. The `_recent_parent` Writer-Task-Scope Cache

`_recent_parent: dict[str, dict[str, int]]` — keyed by `session_id`, value is a dict from `event_type` to the most-recent event id of that type within the session. Mutated only in the writer task (not in the producer's async path) to keep the cache mutation single-threaded.

When a new event is written, the writer task updates `_recent_parent[session_id][event_type] = new_event_id`. The cache is cleared on `session_lifecycle=close` to prevent cross-session pollution (an audio_in from session A should never resolve to an identity_claim from session B).

The C1 invariant (`_recent_parent` writer-task-scope-only) is enforced by an AST scan in `tests/test_event_log_invariants.py` that asserts no production code outside the writer task mutates `_recent_parent`. The test catches future refactors that move parent resolution into the async path (which would introduce a race).

## 316. Bounded Queue and the D5 Lossy-Backpressure Decision

The producer's `asyncio.Queue` has `maxsize=10000`. Above 10000 unprocessed events, `queue.put_nowait()` raises `asyncio.QueueFull`. The producer catches this, increments `_drop_count`, and logs a `[EventLog] WARN: queue full, dropping event` line (rate-limited).

The design decision (D5 in the plan): **lossy backpressure under sustained overload**. The alternative (block on `queue.put`) would have made every producer-hook synchronous-with-DB-writes, which would break the "producer hooks never affect production behavior" contract.

The empirical assumption is that 10000 unprocessed events represents minutes of normal traffic. If the writer task falls behind by more than that, the issue is structural (DB lock, disk full) and dropping events is the safe choice — observability degrades gracefully, production behavior continues.

`get_drop_count()` exposes the cumulative drop count for health-log integration (§321). The drop counter is the observability channel; there is NO `event_log_dropped` event emitted in the queue (D5 circular-dependency guard — an "I dropped an event" event would itself be dropped under backpressure).

## 317. The 11 Producer Hooks at 12 Sites

| Hook | Site | Event type |
|---|---|---|
| H1 | `core/audio.py::listen_and_transcribe` | `audio_in` |
| H2 | `pipeline._background_vision_loop` (sidecar + JPEG storage) | `vision_frame` |
| H3 | `core/voice_channel.py::identify_speaker` | `identity_claim` |
| H4 | `core/vision_channel.py::observe_scene` | `presence_state` |
| H5 | `core/reconciler.py::reconcile` (+ utt_band tag) | `routing_decision` |
| H6 | `core/brain.py::_classify_intent_smart` (via `_emit_intent_classification_safe`) | `intent_classification` |
| H7 (×2) | `pipeline._execute_tool` (entry + exit) | `tool_call` + `tool_result` |
| H8 | `core/db.py::FaceDB.log_turn` | `memory_write` |
| H9 | `core/state.py::write` | `state_write` |
| H10 | `core/audio.py::speak` + `speak_stream` (via `_emit_tts_event_safe`) | `tts_out` |
| H11 | `pipeline._open_session` + `_close_session` (via `_emit_session_lifecycle_safe`) | `session_lifecycle` |

The D7 N=1 invariant (exactly-one-producer-per-event-type) is enforced by AST scan in `tests/test_event_log_invariants.py`. The scan walks all `safe_emit_sync(...)`, `emit_sync(...)`, and `emit(...)` calls in the codebase, groups them by the `event_type` literal argument, and asserts exactly one production location per type. The `_EMIT_CALL_NAMES = frozenset({"emit", "emit_sync", "safe_emit_sync"})` recognition set was extended to include `safe_emit_sync` at Step 5 polish.

## 318. `_m_0012_create_event_log_*` Migration

The schema migration that creates the `event_log` table is registered at version 12 in `core/brain_db_migrations.py`. P0.9 5-tuple shape:

```python
(12, "Create event_log table for P0.0.7 event-sourcing foundation",
 _m_0012_create_event_log_apply,
 _m_0012_create_event_log_verify_post,
 _m_0012_create_event_log_verify_present)
```

`apply_fn` creates the `event_log` table + 3 indexes: `idx_event_log_ts` (chronological queries), `idx_event_log_session` (per-session filter), `idx_event_log_room` (per-room filter). The indexes are tuned for the replay CLI's most-common filter compositions.

`verify_post_fn` asserts the table + all 3 indexes exist after `apply`. `verify_present_fn` returns True if the table already exists (used by bootstrap on legacy DBs that may have manually-applied earlier versions).

## 319. The Read-Only Replay CLI

`tools/replay_session.py` (~410 LOC) is the operator-facing CLI for inspecting the event log. Read-only by design: opens the DB via `sqlite3.connect(f"file:{path}?mode=ro", uri=True)`, never writes, never initialises the producer. Safe to run against a live production DB.

Filter flags compose with AND semantics:
- `--session <id>` — per-session filter
- `--room <room_id>` — per-room filter
- `--type <event_type>` — filter to one event_type (closed-set choices via argparse)
- `--since <offset>` — Unix timestamp / ISO-like string / duration suffix (`1m`/`30m`/`1h`/`24h`/`7d`)
- `--limit N` — default 200, `0` = unbounded
- `--no-tree` — disable parent-chain tree rendering (flat output for grep/pipe use)
- `--raw-payload` — print full JSON payload below each line (debug mode)

Tree rendering: events with `parent_event_id IS NOT NULL` where the parent is in the rendered window get a `└─` indent prefix. Orphaned events (parent outside window) fall back to indent=0. Natural-pair chains (`tool_call → tool_result`, `audio_in → identity_claim → routing_decision`) render as causality trees.

UTF-8 stdout hygiene: `_ensure_utf8_stdout()` reconfigures stdout to UTF-8 at startup so the `→` and `└─` characters render on Windows cp1252 terminals. Fallback is wrapped in `# CLEANUP:` annotated except (P0.4 compliant).

Defensive UX: missing DB → clear error pointing at `--db <path>` flag; missing `event_log` table → clear error pointing at the P0.0.7 migration prerequisite; corrupt/unknown payload → fall back to truncated JSON dump (line still renders, no crash).

## 320. Reusable Scenario Fixtures for P0.S1+

`tests/fixtures/event_log_fixtures.py` (~520 LOC) ships 4 scenario builders that compose realistic event chains for use in tests:

- **`build_greeting_flow(session_id, pid, ...)`** — clean known-person turn: session_lifecycle=open → audio_in → identity_claim → routing_decision → intent_classification → tool_call → tool_result → memory_write×2 → state_write → tts_out → session_lifecycle=close. Exercises all 3 natural-pair links.
- **`build_stranger_first_encounter(session_id, pid, ...)`** — stranger says system-name: 3× vision_frame frames (anti_spoof_live=True) → presence_state → audio_in → identity_claim (no match) → routing_decision (new_stranger) → session_lifecycle=open → intent_classification (assign_own_name).
- **`build_multi_person_room(room_id, session_a, session_b, ...)`** — 2 sessions interleaved with shared room_session_id: 2× open → session A turn → session B turn (switch_enrolled) → 2× close. Verifies room_session_id threading + per-session parent cache isolation.
- **`build_dispute_path(session_id, ...)`** — dispute-trigger pattern: low-confidence identity_claim → ambiguous routing_decision → intent_classification (assign_own_name) → tool_call (update_person_name) → tool_result (status=rejected, user-text gate refused).

The fixtures use `safe_emit_sync` (the production hook surface) so the natural-pair parent_event_id resolution + `_recent_parent` cache lifecycle exercises exactly as on a live boot.

The fixtures are parameterised top-level callables. P0.S1's anti-spoof regression tests will import `build_greeting_flow` etc. directly, compose chains, and verify the anti-spoof gate behaves correctly — without needing live camera input. This is the **D7.4 reusability** contract.

## 321. Health-Log Integration via Drop and Emit-Failure Counters

`HealthSnapshot` (Part XLVI §301) gained two new fields:

- **`event_log_drops: int`** — from `get_drop_count()`. Bounded-queue full events shed by backpressure.
- **`event_log_emit_failures: int`** — from `get_safe_emit_failure_count()`. Exceptions swallowed by `safe_emit_sync`.

`format_health_line` conditionally surfaces both — clean steady-state line stays clean when both are 0; only surfaces during degradation. `format_health_alerts` emits two distinct alerts with remediation pointers:

- **drops** → "writer task falling behind; bounded queue (10000) shedding envelopes. Investigate writer-loop / DB lock / disk-full."
- **emit_failures** → "safe_emit_sync swallowed exception(s) from a producer hook. Grep `[EventLog] WARN` in terminal_output for the type+message of the first 3 (rate-limited)."

The two alerts capture genuinely different failure modes (consumer falling behind vs producer-hook exception). Collapsing them to a single "event_log degraded" alert would force operators to grep both surfaces every time.

The D5 circular-dependency guard is preserved: counters ARE the observability channel; no self-emitting `event_log_dropped` event exists in the queue. The lazy import + `# OPTIONAL:` annotated except in `gather_health_snapshot` handles legitimate cases where `core.event_log.producer` isn't loaded (early boot, tests that mock out the package).

---

# Part L — Architectural Disciplines (The Named Doctrines)

## 322. Induction-Surfaces-Invariant-Gaps

**Track record: 7-for-7** (P0.6.7v2, P0.8.2, P0.11, P0.12, P0.12.1, P0.0.7 ×2).

Every structural invariant ships with an **induction protocol** that deliberately exercises the failure mode the invariant is meant to prevent. The induction is a test of the invariant, not of the production code. When induction surfaces a gap (either in the invariant's coverage or in production code), the gap is closed in the same cycle, not deferred.

The operational rules:

1. Every new structural invariant gets a deliberate-regression check before sign-off — induce the violation, confirm the test fires, revert, document the outcome in the closure report.
2. Mid-flight production fixes from induction findings are NOT scope creep — they are the protocol working. Document them in the same sub-PR.
3. When induction surfaces a detector gap (the invariant didn't catch a real violation), strengthen the detector in the same cycle. Do not defer.
4. Property-based testing (Hypothesis) is a first-class induction tool. Use `max_examples=1000` for contract surfaces.

The 7 instances:

- **P0.6.7v2** — 8 deliberate-regression checks induced field-drift / unenumerated-writer / paired-write-atomicity / producer-copy / peek-not-mutate / ratchet / M2-coverage / prior-state-guard violations; all 8 fired correctly.
- **P0.8.2** — F1 + F2 deliberate-regression: injected sync `.execute()` loop without checkpoint + flipped `include_tools=False` → `True`; both invariants fired correctly.
- **P0.11** — 3 deliberate-regression checks; the third surfaced a detector gap (attribute-form access not caught) → detector strengthened in same cycle.
- **P0.12** — Hypothesis property tests (1000 examples/test) induced two real production bugs.
- **P0.12.1** — caller-audit surfaced one real downstream regression (`SocialGraphAgent` list-shape branch became unreachable after P0.12); fix landed in same cycle via sibling `_parse_json_array`.
- **P0.0.7 (instance 1)** — round-trip test's coverage gate caught `presence_state` missing from fixture scenarios → added to scenario B in same cycle.
- **P0.0.7 (instance 2)** — full-suite verification caught 12 P0.4 silent-except violations the subset-verification missed → fixed via `safe_emit_sync` consolidation.

## 323. Architect-Reads-Production-Code-Before-Sign-Off

**Track record: validated across P0.6.7 v1→v2, P0.7 closeout caller audit, P0.12.1 audit.**

Reviewer / auditor sign-off requires reading the actual implementation against the closure summary. Summaries describe intent; code reveals what shipped.

Three documented instances:
- **P0.6.7 v1→v2** — three real gaps surfaced by post-closure audit: vision-globals migration miss, CacheStore touch-on-read LRU violating the locked spec, 4th-shim miscounted disclosure.
- **P0.7 closeout caller audit** — 187 legacy patterns in `test_pipeline.py` surfaced after the 1717-passing milestone was reached.
- **P0.12.1** — Site B dead branch surfaced from post-closure caller audit; Site A flagged but actually safe under existing dual-guard.

The architect's read pass before sign-off is cheap (~30 minutes of focused diff review) and catches the cases where the closure summary diverges from what shipped. This is *complementary* to the developer's verification — it's not redundant; it's a different kind of pass against a different question.

## 324. Verification-Before-Completion (Strengthened by Full-Suite Lesson)

When about to claim work is complete, fixed, or passing, before committing or creating PRs — run verification commands and confirm output before making any success claims. **Evidence before assertions, always.**

P0.0.7 Step 5 polish strengthened this discipline. The original claim "no regressions" was based on subset verification (P0.10 + reconciler + event_log tests). Reviewer's full-suite verification caught 12 P0.4 silent-except violations the subset verification missed. The lesson banked: subset verification is necessary but not sufficient; always run `pytest --tb=no -q` (full suite) before "no regressions" claims. The full-suite cost on this codebase is ~163 seconds; the cost of a wrong "no regressions" claim is much higher.

## 325. Spec-First Review Cycle for Multi-Day Specs

**Track record: 5-for-5** (P0.6, P0.7, P0.8, P0.9, P0.10).

For sub-PRs estimated > 1 day, the workflow is:

1. **Phase 0 audit** — pure documentation, zero production-code changes, grep-verified findings reported BEFORE any test code is written.
2. **D1-Dn decisions surfaced** in the audit document.
3. **Architect / auditor sign-off locks them** before Plan v1 is drafted.
4. **Plan v1** is the first complete spec.
5. **Architect / auditor feedback drives Plan v2.**
6. **Code phase** starts only after v2's locked structure is in place.

Spec-time investment pays back 2–4× in mid-flight rework avoided — every cycle that skipped Phase 0 hit larger surprises. The empirical proof: every Phase 0 audit in P0.2 – P0.10 saved 4–6 hours of Step 1 rework. The compound win across multi-day specs is substantial.

P0.0.7 added a 6th instance to the cycle in 2026-05-18 (Phase 0 audit at `tests/p0_07_event_boundary_audit.md` → Plan v1 → Plan v2 with R1-R5 refinements → 8 implementation steps). Track record refresh pending the next multi-day spec.

## 326. Spec-Contracts-Not-Implementations

**Track record: 3-for-3 (P0.8.2 F2, P0.9.1, P0.9.2).**

Architect specs describe what invariants must hold (the contract), not how to satisfy them (the implementation). Developers find the best implementation within the contract.

Why it matters: the developer has full visibility into the actual code, runtime state, surrounding patterns, and adjacent constraints the spec author cannot pre-load. Specs that lock contracts let the developer's local knowledge improve the mechanism; specs that lock mechanisms turn the developer into a transcription typist.

Examples of contract vs implementation:

- **Contract**: "every paired-write site must use a `_mark_X_dirty()` sentinel before the cross-storage write."
- **Implementation**: which file, which exact name, which line — developer's call.

- **Contract**: "the band-divergence trigger fires when `utt_band ∈ {gap, short_hard}` and the rule that fired isn't the band's expected rule."
- **Implementation**: where the mapping lives, what data type — developer's call (this is P0.10.1 F2: `EXPECTED_RULES_BY_BAND` belongs in `core/reconciler.py`, not pipeline.py inline).

## 327. Developer-Improves-on-Spec-by-Reading-Carefully

**Track record: 5-for-5.**

When implementation reveals a better path that preserves the spec's architectural intent, bank the improvement explicitly in the closure report so the architect / auditor sees the deviation + rationale.

The 5 instances:

- **P0.8.2 F2** — spec named external call sites; developer's caller audit found the actual contract was internal (`ask_retry_text` doesn't accept `include_tools` as a parameter by design), so F2 verified the internal contract instead.
- **P0.9.1** — spec sketched a fresh `init_ledger()`; developer made it self-evolving (idempotent ALTER adding `is_initial` to pre-P0.9 ledgers) so the classifier_scenarios.db schema upgrade rode the same code path.
- **P0.9.2** — spec defined 4-tuple migrations; developer split `verify_post`/`verify_present` because conflating them would let bootstrap stamp `is_initial=1` on a partially-backfilled DB.
- **P0.10 Block C** — spec said "extend the existing divergence-log block with more fields, don't change trigger"; Step 7's legacy deletion makes the original trigger unworkable; developer retargeted to band-divergence detection, preserving Block E's gate criteria semantically.
- **P0.0.7 Step 5 polish** — reviewer's P0.4 remediation said "annotate the 12 hook-site try/except blocks with `# OPTIONAL:`"; developer instead consolidated to a single `safe_emit_sync(...)` helper with one annotated except. 12 violations → 1 annotated except + 12 unannotated call sites. Strictly better than the annotation patch the reviewer proposed.

Pairs with **spec-first review cycle** (the discipline that produces these moments) and **spec-contracts-not-implementations** (the architect-side framing that makes them welcome).

Sub-patterns identified:

- **Sub-pattern A (premise correction)** — P0.10 Phase 0 audit caught the architect's wrong premise about Bug-W living in legacy when it actually lived in the new reconciler. Different shape from mechanism-level improvement: the audit changes WHAT gets built, not just HOW.
- **Sub-pattern B (developer resists premature pattern elevation)** — P0.0.7 plan v2 discussion. Architect proposed elevating "tripwires must match the actual deferral surface" to a CLAUDE.md named doctrine after 4 instances. Developer pushed back: the established cadence is "3+ instances → memory note; 5+ instances → CLAUDE.md named doctrine" per the P0.10.1 F3b pattern. At 4-for-4, pattern is memory-note-only; wait for the 5th instance before elevating. Auditor endorsed the pushback.

## 328. Tripwires-Must-Match-the-Actual-Deferral-Surface

**Track record: 3-for-3 (P0.11 `_persistent` global decl, P0.10 Bug-W audit, P0.0 S2 binding).**

When you defer an item and ship a tripwire to make the deferral safe, verify the tripwire actually catches what the deferral leaves unsafe — not just the symbolic version of it. A tripwire that catches the symbolic version while the real surface stays exploitable is **theater**.

The 3 instances:

- **P0.11 `_persistent` global declaration test** — architect's spec'd detector caught bare-name writes; auditor's deliberate-regression check injected attribute-form access; detector was strengthened to catch BOTH shapes.
- **P0.10 Bug-W audit** — architect's premise "the new reconciler is correct, delete the 273-line legacy router" was wrong; Phase 0 audit caught it before code shipped.
- **P0.0 S2 binding tripwire** — architect deferred S2 (dashboard auth) on the framing: "bound to 127.0.0.1, no LAN exposure today"; tripwire asserted absence-of-LAN-bind, but Next.js defaults to 0.0.0.0 when `--hostname` is absent. Dashboard was LAN-accessible right now. P0.0.1 fix added explicit `--hostname 127.0.0.1` AND tightened tripwire to require the flag.

The architect-side discipline at spec-time: write a paragraph titled **"What this tripwire does NOT catch"** that enumerates implicit-default failure modes, alternate-access-path failure modes, and adjacent-behavior failure modes. If any items list a real risk, EITHER tighten the tripwire OR un-defer the item. Honest scoping is the discipline.

## 329. Structured-Audit-vs-Reactive-Patching (Empirical Foundation)

Reactive patching surfaces ~30% of an invariant's violations. Structured audits surface ~100%.

Established empirically by **P0.4** (silent excepts: 22 sites surfaced via AST audit vs ~7 caught reactively, a 3× discovery ratio) and confirmed by **P1.A1-slice** (9 layering violations: 7 new beyond the 2 previously known reactively, a 4.5× discovery ratio).

Implication: when an invariant is worth enforcing, schedule the structured audit. Don't budget the work as "fix the reactive findings and call it done." When in doubt, audit; don't react.

Future items where this matters most: P1.A4 (service decomposition), P1.A8 (single SQLite split), any future invariant that scans for boundary violations.

## 330. Why Each Discipline Has a Track Record, Not a Rule

The disciplines above are not stated as absolute rules. Each one is a **named pattern with a track record**. The track record matters because:

1. **A rule with no track record is theoretical.** Until a pattern has fired across multiple instances, it's a hypothesis. The track record is the empirical evidence that the pattern is real.
2. **A track record is auditable.** Anyone can grep `Track record: N-for-N` and read the actual instances. The pattern's status is visible.
3. **A track record refreshes.** Each new instance adds a notch; each closure cycle adds context. The pattern earns its place as it pays off in practice.
4. **The cadence prevents premature elevation.** Per the P0.10.1 pattern banked as sub-pattern B in §327: 3+ instances → memory note; 5+ instances → CLAUDE.md named doctrine. The cadence is meaningful; it prevents the architect from naming every accident-of-the-moment as a doctrine.

The disciplines above all sit at 3+ instances (one at 5+, several at 4+). New disciplines join when they reach 3 instances; named doctrines elevate when they reach 5.

---

# Part LI — Upcoming Work and Roadmap

## 331. P0.0.7.X — Hypothesis TestLargeInput Flakiness  [CLOSED 2026-05-18]

**Status: CLOSED 2026-05-18.** Self-resolved between filing (P0.0.7 closure) and post-P0.S1 re-verification.

**Phase 0 audit at closure time:** 6-for-6 stability case banked — 3 × full-suite runs (Hypothesis included) at 2302 / 2302 / 2302 passed, plus 3 × Hypothesis file alone at 36 / 36 / 36 passed. No flake reproduction across the 6 independent runs.

**Likely fix mechanism (incidental, not deliberately targeted):**
- P0.S1 Phase 1 autouse-fixture additions: `AntiSpoofRejectionStore.reset` + TrackStore extension reset paths added to the conftest loops.
- P0.0.7 producer-state-reset hooks added incrementally after the original flake observation.
- Test isolation surface is cleaner now than at the time the flake was documented.

**Closure decision:** the file is re-included in default `pytest` runs (`--ignore` flags dropped from the validation runbook and from CLAUDE.md / everything_about_system.md). No deliberate stability tripwire added — the 36 Hypothesis tests are themselves the regression coverage; re-emergence would surface naturally on the next full-suite run.

**If the flake re-emerges in future, file a fresh follow-up rather than re-opening this entry** — the conditions that caused it are gone and any new instance is almost certainly a different mechanism.

## 332. P0.S1 — Anti-Spoof on Every Face Match (Next Item)

**Status: greenlit pending P0.0.7 auditor sign-off. Next item in the locked sequence.**

Pre-P0.S1, anti-spoof is gated on the greeting path (`is_live()` is called in `first_boot_flow` and `enrollment_flow`) but NOT on every face match. The recognition update path (`add_embedding(source="recognition_update")`) writes to the gallery when a high-confidence face match occurs; if that face match was actually a presentation attack (photo, screen, video replay), the attacker can poison the legitimate person's gallery.

Session 51's MiniFASNet activation (Session 52) closed the gating gap on the greeting path. P0.S1 closes the gap on every match.

The architectural approach:
- Every code path that calls `FaceDB.add_embedding(...)` with `source="recognition_update"` must pass through `verify_live(...)` first.
- Replay regression tests built on top of P0.0.7's scenario fixtures (`build_greeting_flow`, `build_stranger_first_encounter`) — the fixtures already capture `anti_spoof_live` and `anti_spoof_score` in `VisionFramePayload`, so the test can pin the assertion at the gate without live camera input.
- The current `ANTISPOOFING_THRESHOLD = 0.5` is the production gate; P0.S1 may tune this empirically but not as part of the structural fix.

Phase 0 audit + Plan v1 + Plan v2 cadence per the spec-first-review-cycle (§325). The replay fixtures unblock the regression tests; the regression tests pin the behavior at the new gate.

## 333. P0 Security — The Locked Sequence Beyond P0.S1

The complete-plan.md security backlog has S1 through S11. The user-locked sequence:

- **P0.S1** — anti-spoof on every face match (next)
- **P0.S6** — secrets management (env vars, no hardcoded API keys)
- **P0.S5** — dashboard CSRF protection (deferred S2 remains pre-auth; S5 is the inside-the-auth-boundary protection)
- **P0 medium-priority security** — S2 (dashboard auth proper), S3 (input sanitisation), S4 (TLS for dashboard), S7-S11 (specific surface hardening)

Each item ships as a Phase 0 audit + Plan v1 + Plan v2 + code cycle. Each one ends with structural invariants + induction-confirmed regression tests.

## 334. P0 Robustness — R1 through R11

The robustness backlog targets failure modes that don't affect security or correctness directly but degrade reliability over time:

- **P0.R1** — startup determinism (every boot from a clean state must reach `WATCHING` within budget; surfaces flakiness in model loading, DB init, etc.)
- **P0.R2** — model cache integrity (HF model downloads can corrupt; checksum verification + redownload on mismatch)
- **P0.R3** — graceful degradation matrix (formal documentation of every degraded mode + recovery path)
- **P0.R6** — DB integrity check on boot (PRAGMA integrity_check on faces.db, brain.db, classifier_scenarios.db; auto-repair if possible, alert if not)
- **P0.R7** — fallback brain when Together.ai unavailable (current: Ollama hardcoded; user has flagged this needs to be config-driven like the primary brain for plug-and-play model swapping)
- **P0.R10** — config snapshot on boot (record the config values that affect this run, for post-hoc debugging)
- **P0.R11** — automated backup of brain.db + faces.db on dream cycle

The expected sequence is R3 → R2 → R6 with an R7 spike in parallel (the user wants deeper discussion before R7's spec lands). R1, R10, R11 follow.

## 335. Eval Gates — Continuous Evaluation Becomes Real

The eval-gates work formalises the continuous-evaluation tooling sketched in Part XXX. The components:

- **Golden corpus** — `tests/golden_intent.jsonl` already exists with 149 rows (Session 87 end). The corpus grows per the source-taxonomy rules in CLAUDE.md.
- **Bench harness** — `tests/eval_intent_bench.py` (P1.6) runs the classifier against all non-legacy rows and persists run metrics + mismatches to `tests/eval_bench_runs/YYYYMMDD_HHMMSS.json`.
- **Weekly drift report** — `tests/eval_weekly.py` queries `intent_divergences` over the last 7 days, prints per-intent precision/recall drift, low-confidence gate decisions, recent rejections.
- **Quarterly golden-set drift detection** — `tests/golden_set_drift.py` exports 20 random stratified rows for human review, accepts the reviewed markdown back, flags drifted labels.

Each tool is a standalone module; none of them block production behavior. The eval gates work makes the metrics surface visible enough that drift can't hide between releases.

## 336. P1.A — Pipeline.py Decomposition into ~30 Modules

`pipeline.py` is currently ~10,000 lines. P0 work has reduced its size somewhat (the Store-pattern migration moved ~3500 lines to `core/store_*` modules) but the file is still the project's single largest module and the bottleneck for understanding the runtime.

P1.A is the decomposition project. The plan (in coarse outline; Phase 0 audit will refine):

- **P1.A1** — layering audit (already done as a slice in P0.X-audit; the full audit will surface every cross-module access pattern)
- **P1.A2-A6** — extract the major runtime services into named modules (microphone capture loop, vision background loop, conversation turn handler, session lifecycle, brain dispatch)
- **P1.A7-A12** — extract the supporting services (KAIROS, dream loop, factory reset, IPC writers, classifier wiring, anti-spoof integration)

Each extracted module follows the Part XXXII pattern: pure functions where possible, structural invariants on import boundaries, AST-enforced layering rules.

Target end state: `pipeline.py` shrinks to roughly 1500-2000 lines of orchestration code; the runtime logic lives in ~30 focused modules under `core/`. The decomposition is the biggest single architectural improvement queued — but it has to land AFTER the P0 security/robustness/eval cycle because those provide the test scaffolding that makes safe decomposition possible.

## 337. Voice Gallery Growth Bug for Promoted Voice-Only Strangers

**Known issue, fix queued.** (Documented in Part XXXII §203.4.)

Session 94 added bootstrap-credit replenishment so engaged strangers could grow their voice profile to maturity. The condition includes `person_type == 'stranger'`. After a voice-only stranger is promoted via `update_person_name` ("My name is Lexi"), the promotion chain flips `person_type` to `known`. The replenishment condition stops firing. Subsequent voice samples are refused.

The fix shape (architect's recommendation, pending implementation):
- Add a `voice_only_origin` session-dict flag, set at engagement-gate pass when no face was witnessed.
- Replenishment fires when `voice_only_origin == True` AND `voice_n < MATURE`, regardless of `person_type`.
- Flag clears on first face-witness event.

Cost: small (10-20 lines + 3 tests). The reason it's not P0.S1-priority is that the failure mode is gradual degradation (stunted voice profiles) rather than active security risk. Will land alongside one of the P0.R items where session-state plumbing is already on the table.

## 338. Kuzu v3 Schema Bump and Graph-Side Privacy

Sessions 96-108 (Phase 3A) shipped the four-tier privacy model and the SQL-side `_visibility_clause` helper. The corresponding Kuzu-side change — gate `find_shared_entities` and similar 1-hop traversals on `privacy_level` — was deferred. The full Kuzu v3 bump will:

- Add `privacy_level` to graph edges.
- Update the `find_shared_entities` MATCH query to filter on `privacy_level != 'system_only'`.
- Wire `room_session_id` and `audience_ids` into conversation_log retrieval paths via graph-aware queries (currently Q3 is SQL-only).
- Rev the `GRAPH_SCHEMA_VERSION` from 2 to 3, triggering rebuild from brain.db on first boot.

Deferred reason: the SQL-side filter is sufficient for current threat model (S107 audit). v3 lands alongside the RoomOrchestrator work (currently scoped under Phase 3B, deferred until P0 cycle is fully closed).

## 339. Format-Bridge Unification (Producer Rows vs CLI Render)

**Open architectural smell from P0.0.7 Step 7.** `ctx.all_events()` returns events with `payload` (parsed dict); CLI's `_render` expects `payload_json` (raw JSON string). Tests bridge with `{**e, "payload_json": json.dumps(e["payload"], sort_keys=True)}` before passing to `_render`.

The bridge is harmless in tests; it's mild architectural debt. A future micro-PR unifies the row dict shape so callers don't need to bridge. Either:

- Producer rows carry both `payload` (parsed) and `payload_json` (raw) — caller picks.
- Producer rows carry only `payload_json` — caller does `json.loads` if they need parsed.
- Producer rows carry only `payload` — caller does `json.dumps` if they need raw.

Decision pending; not blocking other work.

## 340. The Multi-Layer Classifier Architecture (XXXV) — When It Ships

Part XXXV documents the six-layer multi-layer classifier architecture as **FUTURE WORK**. The dependency chain is:

1. P0 security + P0 robustness + Eval gates land (current trajectory).
2. P1.A pipeline decomposition lands (next major architectural project).
3. THEN the classifier multi-layer work can land cleanly because it builds on top of a clean classifier integration point (`classify_intent_smart` → `classify_intent_graph` → the multi-layer graph) without touching the rest of the system.

The work is committed (the Part XXXV roadmap is locked) but the timing is sequential. When P1.A is done, multi-layer can ship in 4-6 weeks.

Until then, Part XXXV is the architectural commitment, not the implementation.

---

# End of Document

This documentation describes the system as of **2026-05-18, post-P0.0.7 event-sourcing foundation, full P0 correctness + architectural-hardening cycle closed, ~2216 tests passing**. It is intended to be read front-to-back by someone learning the project for the first time, and also to be searchable reference material for anyone debugging a specific subsystem.

Further updates should preserve the pattern: every design decision traces to a specific incident (logged in `CLAUDE.md`), a specific config value, or a specific architectural principle from Part XXII or Part L.

If you add a new subsystem, write its section before writing its code. If you change a threshold, update §147. If you land a new agent, extend Part XIV. If you discover an invariant that isn't in Part XXII or named in Part L, add it. If you complete a multi-day spec, add an instance to the appropriate track record in Part L.

Currently the largest unimplemented work, in order:
1. **Part LI §332 — P0.S1 (anti-spoof on every face match)** — next item in the locked sequence.
2. **Part LI §333-§334 — P0 security + robustness backlog (S1-S11, R1-R11)** — multi-month effort.
3. **Part LI §336 — P1.A pipeline.py decomposition into ~30 modules** — biggest architectural project queued.
4. **Part XXXV — Multi-layer classifier architecture** — six-layer plan, ships after P1.A.

The system is the sum of its decisions. Documenting the decisions is how we keep the system coherent across sessions, across contributors, and across time. The Part L named disciplines are how we ensure the decisions accumulate into doctrine rather than dissolving back into ad-hoc patterns.
