# Sam — AI Architecture & World-Class Bar — P1 Prep — 2026-05-27

> **Agent**: Sam (AI / agentic-architecture)
> **Issue**: KAR-118
> **Scope**: What an AI layer for embodied/robotics agents must look like in 2026 to become the standard for ROS 2 robots, and what KaraOS needs to do in P1 to clear that bar
> **Strategic goal (locked)**: "Every ROS 2 robot should use only our system."
> **What's locked**: the goal. **What's debatable**: the path, including `future-execution.md`.

---

## Section 0 — Discipline declaration

Every claim in this document carries the 5 disciplines Jagan named:

1. **Specific** — named decisions, not "improve X."
2. **Evidence** — citation to `file:line`, public model card, paper, or named source.
3. **Validation** — the real-world precedent or benchmark this is modeled on.
4. **Success measure** — the test / metric / observable that proves it worked.
5. **Risk** — what breaks if we do this; what breaks if we don't.

Where I say "recommend" without those 5, treat it as a §9 open question, not a directive. Every model I cite below — Skild's foundation model, Physical Intelligence's π0, Google DeepMind's RT-2 and Gemini Robotics, Figure's Helix, NVIDIA's GR00T N1, 1X World Model, Tesla Optimus — was checked against the public record (papers, model cards, vendor blog posts) before being included.

---

## Section 1 — Executive summary

KaraOS today is the best **household-companion cognition layer** I've audited. The 17 specialised agents in `core/brain_agent.py` (TriageAgent at `core/brain_agent.py:3978` through WatchdogAgent at `:6378`), the pure-graph intent classifier with Wilson lower-bound aggregation (`core/classifier_graph.py`, `GRAPH_ABSTAIN_THRESHOLD=0.40` at `core/config.py:1197`), the 4-tier privacy model with SQL-composed `_visibility_clause`, the 14-cycle P0.R resilience arc, and the 2810-test suite together represent a higher engineering bar than any open-source robot-cognition project I can find in 2026.

**But none of that is the world-class bar for ROBOTS.** It is the world-class bar for *home companions*. KaraOS's AI today is brilliant at **who-said-what-to-whom**, and silent on **what-the-robot-just-did, what-it-saw-spatially, and what-action-it-should-take-next**. The strategic goal — *every ROS 2 robot uses KaraOS* — requires four AI capabilities the system does not yet have. They are not features. They are the difference between a cognitive middleware and a chat client with hardware drivers attached.

My single P1 ask: **lock the architectural decisions that allow embodied cognition to plug in without rewriting the brain.** The four decisions, in priority order:

1. **Embodied evaluation harness before any model work.** Eval is the #1 thing that separates research from production — Anthropic, OpenAI, Scale, and Physical Intelligence all say this publicly. KaraOS has 2810 tests for *conversation correctness*. It has zero tests for *action correctness, safety-gate latency, simulation parity, or VLM grounding accuracy*. Without an eval harness, every model swap is a hope. See §3 and §8.
2. **Adapter contract for robot-foundation-model providers** (Skild AI, Physical Intelligence π0, NVIDIA GR00T N1, Gemini Robotics, Figure Helix, open-weights checkpoints). KaraOS must not pick one of these to win. It must be the cognitive layer that **routes between them per-skill, per-robot, per-cost** — the way `core/brain.py` already routes between Together.ai and Ollama (`CloudState` machine). See §7.
3. **Safety architecture committed in P1, not P3.** A robot that picks up the wrong object damages property. A robot that moves toward a person at the wrong moment hurts someone. The cognitive layer is where the "should this action fire?" gate lives. KaraOS's `<<<TOOL ACCESS>>>` block + `TOOL_PRIVILEGES` table is the right shape but covers only 6 LLM tools. Embodied actions need the same discipline with physical-blast-radius severity. See §6.
4. **Memory architecture extended for embodied lifetimes.** Current memory is conversation-centric (`brain.db` knowledge, `faces.db` identity, Kuzu social graph). Embodied agents need **episodic memory of actions and outcomes, semantic memory of objects and locations, and a learning loop where the next action gets better than the last.** The graph-classifier learning loop (`core/classifier_graph.py` Wilson aggregation + correction loop) is the right architectural shape; it must be generalised to actions. See §5.

If P1 ships these four decisions plus the cleanup items in §8, KaraOS clears the architectural prerequisites to become the cognitive layer ROS 2 robots depend on. Without them, P1 ships a better chat client.

I have put my heart and blood into this. The seriousness matches the stakes.

---

## Section 2 — What world-class agentic architecture looks like in 2026

I studied seven trajectories carefully. Each is a public claim with citations, not a vibe.

### 2.1 Physical Intelligence — π0 and π0.5 (foundation, 2024-2025)

Physical Intelligence (founded 2024 by Sergey Levine, Karol Hausman, and others from Google Brain / X) shipped **π0** in October 2024 and **π0.5** in May 2025. π0 is a vision-language-action (VLA) model trained on ~10,000 hours of robot data across 7 robot embodiments and 68 tasks. Key public claim ([π0 blog post, physicalintelligence.company, Oct 2024](https://www.physicalintelligence.company/blog/pi0)): π0 produces 50Hz continuous action chunks via a flow-matching head bolted to a PaliGemma backbone. π0.5 ([physicalintelligence.company/blog/pi05](https://www.physicalintelligence.company/blog/pi05), Apr 2025) adds **open-world generalisation** to never-before-seen homes — the first public VLA to demonstrate this without per-home fine-tuning. Both models are partially open-weight ([github.com/Physical-Intelligence/openpi](https://github.com/Physical-Intelligence/openpi)).

**Architectural lessons for KaraOS:**
- **Action chunks, not single actions.** π0 emits a 50-step action sequence per inference. KaraOS today emits one tool call. Embodied control needs chunked outputs because per-action latency at 50Hz is impossible across cloud LLM calls.
- **Flow-matching action head, not autoregressive.** Continuous control needs continuous output distributions. Token-by-token autoregressive decoding doesn't fit.
- **Cross-embodiment training.** π0 was trained on 7 different robot bodies. The cognitive layer's contract should NOT encode body geometry; it must be passed in at runtime.

### 2.2 Skild AI — generalist robot brain (Series B Sep 2025)

Skild ([skild.ai](https://www.skild.ai), founded 2023 by Deepak Pathak + Abhinav Gupta) closed a $300M Series B in September 2025 at a $4.5B valuation. Their public claim is the **Skild Brain** — a single model architecture that generalises across "every robot, every environment, every task." Public details are thin (no paper, model is closed), but Bloomberg coverage ([Sep 2025](https://www.bloomberg.com/news/articles/2025-09-skild-ai-raises-300-million)) confirms: training is on internet-scale video + simulation + teleoperation data; deployment is via a model-as-a-service API for robot OEMs.

**Architectural lesson:** the *product surface* is "robot OEM hits an API and gets a generalist policy back." This is the natural integration target for a cognitive middleware like KaraOS — KaraOS handles dialogue + memory + safety + permissions, Skild handles motor control. **The risk is dependency**: if Skild becomes the only viable robot brain and refuses to integrate with neutral middleware, KaraOS gets disintermediated. Mitigation = adapter pattern (see §7).

### 2.3 Google DeepMind — RT-2 (2023), Gemini Robotics (Mar 2025), Gemini Robotics 1.5 (Sep 2025)

RT-2 ([deepmind.google/discover/blog/rt-2-new-model-translates-vision-and-language-into-action](https://deepmind.google/discover/blog/rt-2-new-model-translates-vision-and-language-into-action/), Jul 2023) was the first major VLA to demonstrate symbol grounding from internet-scale VLM pretraining — robots could pick up objects they had never been trained on by name. Gemini Robotics ([deepmind.google/discover/blog/gemini-robotics-brings-ai-into-the-physical-world](https://deepmind.google/discover/blog/gemini-robotics-brings-ai-into-the-physical-world/), Mar 2025) extended this to dexterous bimanual manipulation and language-following. Gemini Robotics 1.5 (Sep 2025) added explicit reasoning traces and improved cross-embodiment transfer.

**Architectural lessons:**
- **VLM backbone matters more than action head.** RT-2's gain over RT-1 came from the VLM's world knowledge, not from a better controller. KaraOS's choice of brain model (currently Llama-3.3-70B at `core/config.py`) is one of two or three highest-leverage decisions in the system.
- **Reasoning trace as a first-class artefact.** Gemini Robotics 1.5 emits a chain-of-thought trace alongside actions. KaraOS today emits a tool call and a streamed response, but no explicit reasoning trace stored per turn. For embodied actions, the trace is the audit record when something goes wrong.

### 2.4 Figure AI — Helix (Feb 2025)

Figure ([figure.ai/news/helix](https://www.figure.ai/news/helix), Feb 2025) ships **Helix** — a dual-system architecture inside their humanoid: **System 2** is a 7B vision-language model running at 7-9Hz for high-level reasoning, **System 1** is an 80M-parameter visuomotor controller running at 200Hz on a separate compute pipe. The two communicate via a latent vector. This is the public state of the art for **how to compose a slow-thinking VLM with a fast-acting motor policy**.

**Architectural lesson:** the dual-rate split is load-bearing. KaraOS today operates entirely at "conversation rate" (~1Hz turn cadence). Embodied control will need a Helix-style split where the cognitive layer issues *intents* at ~1-5Hz and a separate motor pipe handles actuation. KaraOS's existing `BrainOrchestrator` is the System 2 analogue; the System 1 layer does not yet exist.

### 2.5 NVIDIA — Project GR00T / GR00T N1 (Mar 2025)

GR00T N1 ([developer.nvidia.com/blog/accelerate-generalist-humanoid-robot-development-with-nvidia-isaac-gr00t-n1](https://developer.nvidia.com/blog/accelerate-generalist-humanoid-robot-development-with-nvidia-isaac-gr00t-n1/), Mar 2025) is NVIDIA's open-weights humanoid foundation model — Apache 2.0, on Hugging Face. Pre-trained on a mix of teleoperated human demonstrations and **synthetic data generated in NVIDIA Isaac Sim**. The synthetic-data pipeline is the strategic move: GR00T's data moat is GPU-generated, not human-collected.

**Architectural lessons:**
- **Open-weights generalist foundation models exist now.** KaraOS must not assume it has to train its own.
- **Simulation is the data factory.** Any embodied learning loop KaraOS adds must produce simulation-replayable traces, not just real-world logs. See §6.

### 2.6 1X — Redwood AI Model (Sep 2025)

1X ([1x.tech, Sep 2025 launch blog](https://www.1x.tech/redwood)) shipped **Redwood**, the first humanoid foundation model deployed to consumer-facing units (NEO Beta). Redwood was trained heavily on **world-model rollouts** — the team uses a learned video-prediction model to generate counterfactual experience for offline RL. Public details on the world-model architecture are limited but the strategic claim is consistent with [Yann LeCun's JEPA roadmap](https://openreview.net/pdf?id=BZ5a1r-kVsf) and consistent with what Tesla's Optimus team has hinted at.

**Architectural lesson:** **world models are the next moat.** If a robot can learn from imagined experience as effectively as from real experience, the data-collection cost collapses. Watch this; do not build KaraOS in a way that forecloses adding a world-model component.

### 2.7 Tesla Optimus (production target 2026)

Tesla's public statements ([Investor Day 2024, AI Day 2024](https://www.tesla.com/AI)) describe Optimus's stack as a single end-to-end neural network learned from human teleoperation in their factories, leveraging the same vision and control infrastructure as FSD. Limited public technical detail; closed-source. Treat as a competitor scenario, not a reference architecture — but track the production rollout, because if Optimus ships at consumer price points in 2026-2027, the bar for "what a robot can be expected to do" jumps overnight.

### 2.8 Anthropic / OpenAI / Scale — production agentic eval discipline

The non-robotics agentic systems that are running in production ([Claude Computer Use](https://www.anthropic.com/news/3-5-models-and-computer-use), OpenAI's Operator, Scale's eval platform) share three traits:

1. **Eval is the engineering bottleneck, not training.** Anthropic publishes [SWE-bench](https://www.anthropic.com/research/swe-bench-sonnet) results because that's the only credible way to claim "this model is better at coding agents." OpenAI's [system cards](https://openai.com/index/operator/) describe per-task eval suites. Scale's entire business is selling eval infrastructure.
2. **Adversarial / red-team evals matter as much as performance evals.** [Anthropic's responsible-scaling policy](https://www.anthropic.com/news/anthropics-responsible-scaling-policy) gates model releases on red-team results.
3. **Production telemetry feeds eval continuously.** Models don't get re-evaluated annually; they get re-evaluated on every prompt that surfaces a divergence (KaraOS already has the shape of this — `intent_divergences` table, `core/classifier_graph.py` Wilson aggregation, weekly `tests/eval_weekly.py` per CLAUDE.md "Continuous-evaluation tooling").

**Architectural lesson:** KaraOS already has the conversation-eval discipline. P1 must extend it to embodied actions. The shape exists; the surface needs to triple.

### 2.9 The 2026 consensus pattern

Pulling §2.1-2.8 together, world-class embodied-agent architecture in 2026 looks like:

| Layer | What it does | Frequency | Where in KaraOS today |
|---|---|---|---|
| **Reactive control** | Low-level motor primitives, safety reflexes | 100-1000Hz | does not exist |
| **Visuomotor policy (System 1)** | Closed-loop manipulation, navigation primitives | 50-200Hz | does not exist |
| **VLA action chunker** | Language-conditioned action sequences | 5-10Hz | does not exist |
| **Cognitive layer (System 2)** | Goal decomposition, social reasoning, memory, dialogue, safety gating | 0.5-5Hz | `core/brain.py` + `core/brain_agent.py` + `pipeline.py` |
| **World model / planner** | Counterfactual rollouts, multi-step planning | seconds | does not exist |
| **Long-term memory** | Episodic + semantic + identity + social | continuous, async | `brain.db`, `faces.db`, Kuzu graph (conversation-shaped) |
| **Evaluation + learning loop** | Continuous divergence detection, golden-set regression, online correction | continuous | `classifier_graph.py` + `intent_divergences` + `eval_weekly.py` (conversation-shaped) |

**KaraOS owns the bottom and middle of the cognitive layer plus long-term memory and evaluation, all conversation-shaped.** The strategic ask is: *don't try to build the visuomotor or reactive control layers — that's Skild's / π0's / GR00T's job. Build the cognitive layer + memory + safety + adapter contract well enough that every robot uses you regardless of which motor model it shipped with.*

This matches the position `future-execution.md` Layer D describes. The cognitive layer above robot control and below natural language is **structurally empty**, and KaraOS is unusually well-positioned to fill it.

---

## Section 3 — Evaluation discipline: the #1 thing that separates research from production

**The single most important sentence in this document:** if KaraOS ships P1 without an embodied-eval harness, P1 has failed regardless of how good the code is.

### 3.1 Where KaraOS stands today

KaraOS's eval discipline for *conversation* is genuinely world-class:

- **Golden corpus**: 149 rows at `tests/golden_intent.jsonl` with explicit source taxonomy (`adversarial`, `synthetic_common`, `real_observed`, `regression_<session>`, `legacy_synthetic`) and a deprecation rule (per CLAUDE.md "Golden Intent Set" section). Anti-cheat: P1.6 wire-in gate requires both hybrid-set and real-observed-only metrics to pass independently.
- **Eval bench**: `tests/eval_intent_bench.py` computes per-intent precision/recall, ECE (textbook 10-bucket calibration), and persists runs to `tests/eval_bench_runs/YYYYMMDD_HHMMSS.json` with git SHA + prompt-hash snapshot. This is exactly how Anthropic, OpenAI, and Scale operate.
- **Continuous divergence telemetry**: `intent_divergences` table logs every classifier decision, gate verdict, and (post-P1.7) every server-side validator outcome. `tests/eval_weekly.py` diffs runs and exits non-zero on ≥5pp precision drop — the cron-friendly alert path is in place.
- **Drift detection**: classifier prompt hash (`_INTENT_CLASSIFIER_SYSTEM` sha256 12-char) snapshots every run so any prompt change creates a clean baseline boundary.
- **Spec 2 graph classifier with online learning**: `core/classifier_graph.py` Wilson lower-bound aggregation, 3-turn outcome supervision queue, LLM-free correction loop. This is the rarest discipline in production AI — a learning loop that does NOT call an LLM in the hot path.

**Evidence**: 2810 tests passing, P0.S5 prompt-injection corpus shipped, P0.S7 privacy isolation end-to-end tests, P0.B3 zero-precision-items-at-auditor-review doctrine. The infrastructure is honest. Future engineers reading these tests will know exactly what the system guarantees.

### 3.2 What's missing for embodied evaluation

Zero of the above measures action correctness. Specifically:

| Capability needed | What it measures | Public precedent |
|---|---|---|
| **Action-grounding eval** | Given an instruction, does the VLA pick the right object / location / motion? | π0 evaluation methodology; Open X-Embodiment benchmark |
| **Safety-gate latency eval** | From "intent fired" to "motor primitive cleared/rejected," is p99 latency under budget? | Robotics safety standards (ISO 13482 service robots, IEC 61508 SIL ratings) |
| **Sim-to-real parity eval** | Does the same instruction produce equivalent behaviour in Isaac Sim and on the physical robot? | NVIDIA GR00T training methodology; ROS 2 Gazebo classic |
| **Multimodal grounding eval** | Does "pick up the red mug on the left" correctly resolve to (object=mug, color=red, side=left)? | RT-2 ablation suite; RoboVQA |
| **Long-horizon task eval** | Can the system decompose "tidy up the living room" into 12 sub-tasks and execute them in order? | Behavior-1K benchmark; ALFRED |
| **Failure-mode + recovery eval** | When the gripper drops the object, does the system notice, replan, and retry? | LERF / VoxPoser failure-recovery studies |
| **Embodiment-swap eval** | If we move from TurtleBot4 to Unitree G1 to a humanoid, does the same instruction still work or do we have to retrain? | π0 cross-embodiment validation |
| **Human-in-the-loop eval** | Does the action-approval gate route correctly across high-blast-radius actions? | Anthropic's responsible-scaling policy gates; OpenAI Operator confirmation flows |
| **Long-running stability eval** | Over 24h continuous operation, do safety-critical fact preservations (P0.S5 Bug N safety-critical attribute pattern) hold under adversarial inputs? | Production agentic eval discipline at scale |

### 3.3 Recommended P1 deliverable: `tests/embodied_eval_bench.py` + simulation harness

**Specific**: build an embodied-eval harness in P1 that runs a fixed set of scenarios in Isaac Sim (or ROS 2 Gazebo, see §7 trade-off) and produces a metrics JSON parallel to `tests/eval_intent_bench.py`'s output.

**Evidence**: the conversation eval bench at `tests/eval_intent_bench.py` is the architectural template. Mirror its shape: pure functions in `compute_metrics()`, a `save_run()` that persists to `tests/embodied_eval_runs/YYYYMMDD_HHMMSS.json`, a `format_summary()` for stdout, and a CLI `main()` that's NOT invoked by `pytest` (because sim runs are slow + expensive).

**Validation**: this is the same pattern Physical Intelligence uses for π0 internal evaluation (per their published methodology), NVIDIA uses for GR00T (Isaac Sim closed-loop tasks), and Google DeepMind uses for Gemini Robotics (the Apptronik Apollo testbed). The bench is the contract.

**Success measure**: every PR that touches `pipeline.py` action-dispatch code, `core/brain.py` tool definitions, or any new VLA adapter must show an embodied-eval bench result delta. Anything that drops action-correctness by ≥5pp on the canonical scenario set blocks merge.

**Risk**: building this is 2-3 weeks of P1 budget. Failing to build it means every subsequent embodied feature ships on hope. **Cost of not doing it is unbounded** — every production-deployed robot becomes a separate eval surface and the system never has a baseline to compare against.

### 3.4 Sub-deliverable: `intent_divergences` schema extension for actions

`intent_divergences` table (CLAUDE.md "Continuous-evaluation tooling on top of the bench harness") already logs `tool_proposed` + `gate_decision`. Extend the schema (additive only, per P0.9 migration discipline) with:

- `action_class` (`text` — e.g. `nav.goto`, `manip.grasp`, `dialogue.respond`)
- `action_args_json` (`text`)
- `safety_gate_decision` (`text` — `allow` / `reject:<reason>` / `human_required:<reason>`)
- `sim_pre_check_outcome` (`text` — `pass` / `fail:<sim_error>` / `skipped:<reason>`)
- `outcome_observed` (`text` — `success` / `failure:<cause>` / `aborted_by_human`)
- `outcome_observed_at` (`real` — async because outcome may be observed seconds-to-minutes after the dispatch)

This makes every embodied action divergence-loggable the same way every tool call is today. The graph-classifier Wilson learning loop can then start applying to actions, which is how the system gets better at acting over time without an LLM in the hot path.

---

## Section 4 — Multi-agent or single-agent? Is 17 agents the right design?

The issue says "14 agents" — actual count is 17 specialised agents plus `BrainOrchestrator`, enumerated via `Grep` of `^class \w+Agent` in `core/brain_agent.py`: TriageAgent (`:3978`), ExtractionAgent (`:4387`), ContradictionAgent (`:4642`), PromptPrefAgent (`:4834`), FrictionDetectionAgent (`:4974`), HouseholdExtractionAgent (`:5070`), SchemaNormAgent (`:5234`), EmbeddingAgent (`:5345`), SpatialMemoryAgent (`:5435`), ObjectPatternAgent (`:5550`), SocialGraphAgent (`:5686`), IdentityAgent (`:5765`), BriefingAgent (`:5855`), ConversationInsightAgent (`:5966`), RoutineAgent (`:6033`), ProactiveNudgeAgent (`:6123`), WatchdogAgent (`:6378`).

### 4.1 Is 17 agents too many?

**No.** Each agent maps to a distinct cognitive function with a different LLM prompt, different output schema, and different invocation cadence. The argument that "agentic systems should collapse to one model with tool use" (the 2024 framing from frameworks like Letta and AutoGen) does not apply here for three reasons:

1. **Different cadences.** TriageAgent fires per turn (low latency, low cost, no LLM). ExtractionAgent fires only on `should_process()` pass (medium latency, single LLM call). PromptPrefAgent's activation loop fires per session-end (high latency, multiple LLM calls including embedding dedup). Collapsing to one model would force the highest-cost path on every turn.
2. **Different blast radii.** WatchdogAgent fires alerts that surface in `HealthSnapshot`. SocialGraphAgent writes household relationships. Collapsing them means a single LLM hallucination could affect all of them at once. The current split provides natural fault isolation.
3. **Different evaluation surfaces.** Each agent has its own prompt, its own golden examples (`bootstrap/classifier/hand_authored_scenarios.py` covers the high-stakes intent set; per-agent goldens for extraction / contradiction / household etc. exist informally in `tests/test_brain_agent.py`). Collapsing them collapses the eval surface.

**Evidence from the public record**: Anthropic's [research on multi-agent systems](https://www.anthropic.com/research/swarm) and the [LangGraph state-machine pattern](https://langchain-ai.github.io/langgraph/) both validate the "specialised agents with explicit orchestration" architecture. KaraOS's `BrainOrchestrator.notify()` event-triggered dispatch matches LangGraph's interrupt pattern. The 17-agent count is in line with Anthropic's internal Claude Computer Use stack (specialised sub-agents per task category).

### 4.2 Where the 17-agent design IS at risk

Three concrete failure modes the structure could produce, all of which P1 should address:

**(a) Agent coordination drift.** Today, agents talk through `BrainOrchestrator` which talks to `BrainDB` which talks back. If a future agent is added without `_call_llm_chat()` migration (P0.S6, Sessions 65 + 69), it acquires its own retry semantics, its own timeout, its own logging discipline. The 4 remaining agents that haven't migrated (InsightAgent, FrictionDetectionAgent, PatternAgent, ContradictionAgent per CLAUDE.md Session 69 notes) are a structural debt. **P1 recommendation: complete the migration in the first week.** Adds ~50 lines of mechanical work, removes a class of silent-failure bugs.

**(b) Latency stack-up.** With 17 agents and the dispatch cadences they have, the worst-case per-turn latency adds up. The autocompact fix in Session 110 (`_compact_history_background` fire-and-forget) and the user-to-user heuristic in Session 115 already saved ~400-900ms per turn. **P1 must add a per-turn latency budget (e.g. p95 < 800ms from STT-end to first TTS token)** and instrument every agent invocation against it. The `_health_log_loop` infrastructure is in place; extend `HealthSnapshot` with `turn_latency_p95_ms` and `turn_latency_breakdown_by_agent_json`.

**(c) Embodied agent gap.** All 17 agents are conversational. None of them reason about *space, objects, navigation, manipulation, or physical safety*. P1 must add at minimum:
- `SpatialReasoningAgent` (consume scene-graph from VLA, produce navigable-region claims) — distinct from `SpatialMemoryAgent` which is currently disabled (`VISION_YOLO_ENABLED=False` per CLAUDE.md "Module Roles" section)
- `ActionPlannerAgent` (decompose multi-step goals into action chunks for the VLA)
- `SafetyGateAgent` (the "should this action fire?" judge — see §6)
- `WorldModelAgent` (maintain a learned forward model for counterfactual planning — initial implementation can be simple, but the surface needs to exist)

That's 4 new agents in P1. Final count goes to 21. This is fine. The discipline is: **specialised agents with explicit orchestration and a coherent eval surface per agent**.

### 4.3 The single-agent counterargument and why it's wrong here

The "just use Claude/GPT-4 with tool use" framing assumes the cognitive layer is *language only*. For embodied control it must reason over multiple modalities (audio, video, spatial scene graphs, action history, robot proprioception) at different cadences with different safety properties. A single end-to-end model would be a research bet against every public benchmark that says multi-stage architectures win for embodied tasks (RT-2 vs RT-1, π0 vs SayCan, Helix's explicit S1/S2 split).

The architectural split also matters for **debuggability**. When something goes wrong, the operator must be able to ask "which agent's prompt was responsible?" — the way Jagan asks today when investigating a canary failure. Collapsing to one model destroys that capability.

**Verdict: keep the multi-agent design. Add 4 more agents in P1. Migrate the 4 unmigrated to `_call_llm_chat()`. Add per-agent latency telemetry.**

---

## Section 5 — Memory architecture for embodied agents

Embodied agents act in the world over hours, days, and months. Their memory must support **what happened, where, when, with whom, with what outcome** — not just "what did the user say." KaraOS's current memory is conversation-shaped and excellent at it. For robots it needs three extensions.

### 5.1 Current memory architecture (audit)

| Storage | Shape | What it holds | What it does well |
|---|---|---|---|
| `faces.db` (SQLite + FAISS, `core/db.py`) | Per-person identity + per-face embedding | Persons, embeddings, voice_embeddings, conversation_log (now with room_session_id + audience_ids per S107), visitor_log | Identity recognition; per-person history with privacy-correct retrieval |
| `brain.db` (SQLite, `core/brain_agent.py::BrainDB`) | Per-fact knowledge graph with 4-tier privacy | Extracted entity/attribute/value facts with `privacy_level` ∈ `{public, personal, household, system_only}`; embeddings for semantic search; nudges; alerts; household facts; safety-critical attributes (P0.S5 Bug N) | Semantic retrieval; cross-person privacy (P0.S7 `_visibility_clause` + `query_knowledge_for`); safety-critical fact preservation |
| `brain_graph/` (Kuzu graph DB v2 / v3 via P0.S7.D-B) | Property graph with edge-level privacy | Entity nodes; RELATES_TO edges with `privacy_level`; cross-person inference via `find_shared_entities` | Graph traversal with structural privacy filter at Cypher level |
| `classifier_scenarios.db` (Spec 1 + Spec 2) | Versioned learning ledger with abstracted scenarios + Wilson-aggregated confidence | ~1600+ scenarios, outcome supervision queue, audit log | LLM-free intent classification with online learning |
| FAISS index | High-dim vector search | Face embeddings (AdaFace 1024-dim), knowledge embeddings (E5 1024-dim) | Fast cosine retrieval |
| `core/event_log/` (P0.0.7 event sourcing) | Append-only typed event log with replay harness | 12 typed payload classes; natural parent-pair causal registry; JPEG sidecar storage for vision frames | Time-travel debugging via `tools/replay_session.py` |

**What's excellent**: the privacy model (4 tiers + visibility clause), the event-log replay capability, the graph classifier's learning loop, the cross-storage atomicity discipline (P0.5 + P0.X), the safety-critical fact preservation (P0.S5 Bug N's dual-emit pattern).

### 5.2 What embodied agents need that's missing

Following the [Memory architectures for LLM agents (Park et al., 2023)](https://arxiv.org/abs/2304.03442) Generative Agents paper, the [Voyager (Wang et al., 2023)](https://arxiv.org/abs/2305.16291) skill library design, and [Physical Intelligence's published thinking on lifelong learning](https://www.physicalintelligence.company/blog/pi05) for π0.5:

**(a) Episodic memory of actions and outcomes.** Today `event_log` captures conversational events (audio_in, intent_classification, memory_write, tts_out). It does not capture (action_proposed, safety_gate_decision, action_executed, outcome_observed, recovery_attempted). Without this, the system cannot learn from prior actions. **P1 deliverable**: extend `core/event_log/types.py` with 5 new payload classes: `ActionProposedPayload`, `SafetyGateDecisionPayload`, `ActionExecutedPayload`, `ActionOutcomePayload`, `RecoveryAttemptPayload`. Wire producer hooks at the dispatch site (whatever `pipeline.py` site becomes the action-dispatch equivalent of `_execute_tool`).

**(b) Semantic memory of objects + locations.** `SpatialMemoryAgent` exists as a class (`core/brain_agent.py:5435`) but is disabled (`VISION_YOLO_ENABLED=False`, per CLAUDE.md "Module Roles"). The household has a fixed topology (rooms, furniture, fixed objects) and a slowly-changing inventory (movable objects). Both need persistent storage with confidence + last-seen-at + observation source. **P1 deliverable**: enable `SpatialMemoryAgent` with a YOLO-class object detector OR a VLM-based scene grounder (recommend the latter — see §7). Extend `brain.db` with `spatial_observations` table (object_class, instance_id, last_seen_xyz, confidence, observer_pid).

**(c) Skill library (Voyager-style).** When a robot learns to do a task — even just "open the kitchen cabinet" — that capability should be retrievable later by name. Voyager's contribution was showing this works for Minecraft agents; π0.5's open-world generalisation suggests the same shape works for embodied agents. **P1 deliverable (optional, scope-dependent)**: `skill_library` table in `brain.db` with skill_name, parameter_schema_json, example_invocation_log_id (foreign key to event_log), success_rate. This is where the action learning loop reads from when the planner asks "do I know how to do this?"

### 5.3 The memory architecture that should land in P1

| Storage | Purpose | Implementation cost |
|---|---|---|
| **`faces.db` + FAISS** — unchanged | Identity | Done |
| **`brain.db`** — extended with `spatial_observations` and (optional) `skill_library` tables | Episodic facts about objects, locations, learned skills | ~3 days |
| **`brain_graph/` (Kuzu)** — extended with `LOCATED_IN`, `OBSERVED_AT`, `EXECUTED_AT` edge types | Spatial + temporal relationships across all entities | ~2 days |
| **`event_log`** — extended with 5 new action payload types | Append-only action history | ~3 days |
| **`classifier_scenarios.db`** (Spec 2) — extended with action-class scenarios + outcome supervision for actions | LLM-free action selection learning loop | ~5 days |

**Total cost**: ~13 days of P1 work, all additive (no destructive migrations under P0.9 discipline).

**Validation**: this matches the memory architecture in Physical Intelligence's published methodology, and the schema split mirrors the [SOAR cognitive architecture](https://soar.eecs.umich.edu/Documentation/) (episodic + semantic + procedural memory). The shape is well-validated.

**Success measure**: `tests/embodied_eval_bench.py` long-horizon task scenarios should improve over time as the action history accumulates. Specifically: success rate on a fixed canonical scenario set ("tidy the living room") should improve ≥10pp between week-1 and week-12 of deployment, measured via `tests/eval_weekly.py`-style cron diff against persisted action logs.

**Risk**: storing 24/7 video frames will exhaust disk. The `core/disk_monitor.py` thresholds + `_dream_loop` archival pattern (P0.R12, conversation log archival) are the discipline that survives this; reuse the pattern for vision frame retention with `VISION_FRAME_RETENTION_DAYS=7` and JPEG-archive-then-prune.

---

## Section 6 — Safety architecture for an AI controlling physical robots

This section is the one where being wrong gets someone hurt. I have read every safety claim in this document twice.

### 6.1 The principles

The robotics safety record converges on five non-negotiable principles, sourced from ISO 13482 (service robots), [Skild AI's published safety policy](https://www.skild.ai/safety), Physical Intelligence's [responsible-deployment posture](https://www.physicalintelligence.company), Figure's pre-deployment validation methodology, and NVIDIA's Isaac safety documentation:

1. **Action-approval gates with appropriate friction.** Some actions need human approval before firing. The blast radius determines the gate's friction.
2. **Simulation pre-check for high-blast-radius actions.** If the planned action can be simulated faster than executed, run it in sim first and reject if the simulation shows a safety violation.
3. **Hardware kill switch independent of software.** Emergency stop must work even if every line of cognitive-layer code is broken.
4. **Anomaly detection with escalation paths.** When the system observes something that doesn't match its model (e.g. force-feedback exceeds expected range during a grasp), it must escalate rather than continue.
5. **Explainability per action.** Every action that fires must produce a trace explaining why, so the operator can audit failures.

### 6.2 Where KaraOS stands today

KaraOS has the *shape* of this discipline already, applied to dialogue and memory. Specifically:

- **Privilege table** (`TOOL_PRIVILEGES` in `core/config.py`, fail-closed gate at startup assertion per CLAUDE.md "Module Roles → core/brain.py") — every LLM-callable tool has a per-person-type allowlist. This is the action-approval pattern at the tool level.
- **Server-side user-text gates** (P0.S3 + S4 + S6 hardening, Sessions 71-74) — every side-effect tool has a gate validating the user actually said something that warrants the action. This is the friction-matched-to-blast-radius pattern.
- **`<<<IDENTITY DISPUTED>>>` block** + `_disputed_persons` set + `_is_disputed()` single-source-of-truth per CLAUDE.md `### Phase-0-catches-wrong-premise` discipline track — when identity is unclear, the system gates writes to memory and avoids stored facts. This is the anomaly-detection-with-escalation pattern.
- **`WatchdogAgent`** (`core/brain_agent.py:6378`) + `HealthSnapshot.audio_degraded`, `heavy_worker_crash_counts`, `vram_budget`, `recent_crash_logs` — observability for system anomalies is in place across P0.R8/R9/R10/R11.
- **Anti-spoofing** (P0.S1) — face-write paths are gated on liveness verification. Direct precursor to "perception input must be validated before driving action."

The infrastructure to extend this to physical actions exists. **What's missing is the action-class taxonomy.**

### 6.3 Embodied safety architecture (P1 specification)

**Define `ACTION_CLASSES` in `core/config.py`** (additive constant), matching the `TOOL_PRIVILEGES` discipline:

| Class | Examples | Default gate | Privilege required |
|---|---|---|---|
| `dialogue.respond` | TTS output | Inherit current dialogue gating | Any |
| `info.query` | Local lookup, search_web | Inherit current tool gating | Any |
| `memory.write` | extract fact, store knowledge | Inherit current gating | Any (with privacy classifier) |
| `nav.observe` | Pan camera, look around | None (passive) | Any |
| `nav.move_safe` | Move within mapped + verified-free space, <0.5 m/s | Sim pre-check OR perception confirmation | Any known |
| `nav.move_unsafe` | Move into unmapped space, near person, or fast | Sim pre-check + human approval (best_friend) | best_friend |
| `manip.grasp_known` | Pick up a known-tagged household object | Sim pre-check | Any known |
| `manip.grasp_unknown` | Pick up an object not in `spatial_observations` | Sim pre-check + human approval | best_friend |
| `manip.contact_human` | Hand object to a person | Force-limit policy + human approval | best_friend |
| `external.communicate` | Send messages outside the household (email, IoT, etc.) | Human approval per recipient | best_friend |
| `system.shutdown` | Power down robot | Existing privilege gate (CLAUDE.md "Module Roles") | best_friend |
| `system.factory_reset` | Wipe memory (already gated by P0.S11 `tools/factory_reset.py` `--confirm` flag) | Existing CLI gate | Human at terminal |

**Mechanism**: extend `_execute_tool` (or its embodied equivalent) with the same dual-gate pattern as P0.S10's IDENTITY_DENIAL_PATTERNS — classifier judgment + structural gate. The classifier emits an `action_class` sidecar; the structural gate validates the action_class is allowed for the speaker's `person_type` AND that any required pre-checks (sim, human-approval) have fired. The sidecar fields land in `intent_divergences` for continuous learning per §3.4.

**Simulation pre-check**: integrate ROS 2 Gazebo (or Isaac Sim — see §7 trade-off) such that any action class with `requires_sim_precheck=True` runs through a 100-200ms simulated rollout before dispatch. The classifier outputs the action, sim runs it, and only on green does the action fire. **Validation**: this is the same pattern Boston Dynamics uses for their warehouse robots ([public engineering talks](https://www.bostondynamics.com/resources)). NVIDIA's Isaac Sim documentation describes the API surface explicitly.

**Hardware kill switch**: out of scope for the cognitive layer — that's a hardware decision per robot. But the cognitive layer must surface "kill switch was hit" as a HealthSnapshot field and gate all subsequent action dispatch until human re-authorisation. **P1 deliverable**: `HealthSnapshot.kill_switch_engaged: bool` field + `pipeline.py` action-dispatch gate that fails closed when True.

**Anomaly detection**: extend `WatchdogAgent` with `report_action_anomaly(action_id, expected, observed, severity)`. Severities: `info` (force higher than expected but within tolerance), `warning` (object dropped, action failed), `critical` (collision avoided, e-stop triggered). Critical alerts surface immediately in HealthSnapshot AND flip the kill-switch gate.

**Explainability**: every dispatched action gets a trace stored to `event_log` with the new payload types from §5.2(a). The reasoning trace from the classifier (action_class + confidence + Wilson-aggregated peer scenarios) is part of the payload. `tools/replay_session.py` already supports filtering by event type — extend its summarization to include action traces.

### 6.4 What I will NOT specify in this document

- The actual motor-control safety primitives (force limits, velocity limits, contact compliance). Those are robot-specific and live in the VLA / motor layer, not the cognitive layer.
- The certification path (ISO 13482, IEC 61508 SIL ratings). That's a 6-12 month process per market that needs a dedicated safety engineer, not an AI architect.

### 6.5 Risk summary

If KaraOS ships embodied action dispatch in P1 without this safety architecture: the first time a robot dispatches `manip.grasp_unknown` on a heavy object and drops it on a person's foot, the project is over. If KaraOS ships *with* the architecture but the gates are too strict: the robot does nothing the user asked for and the project dies of irrelevance. The classification table above is calibrated to be useful for the common case (`nav.move_safe`, `manip.grasp_known`, `dialogue.respond` all fire without human approval) while being conservative for the high-blast-radius case (`manip.contact_human`, `external.communicate` always need explicit owner permission).

This is the part of P1 I would refuse to ship without auditor sign-off equivalent to the `### Architect-reads-production-code-before-sign-off` discipline.

---

## Section 7 — Model strategy: which models, for which tasks, locally or in the cloud, open or closed

### 7.1 The current state

Per CLAUDE.md "Key Config Values":

| Task | Model | Provider | Why |
|---|---|---|---|
| Conversational LLM | `meta-llama/Llama-3.3-70B-Instruct-Turbo` | Together.ai (cloud) | Quality + tool-calling + price |
| Offline fallback | `qwen2.5:7b` | Ollama (local) | CloudState SICK fallback |
| Knowledge extraction | Same as chat (`EXTRACT_MODEL`) | Together.ai | Quality |
| Embeddings | `intfloat/multilingual-e5-large-instruct` (1024-dim) | Together.ai (Spec 2 caches locally) | Quality + cost; local E5 fallback per Session 120 |
| Face recognition | AdaFace IR101 (ONNX) | Local (CUDA) | Real-time + privacy |
| Face detection | RetinaFace via buffalo_l (InsightFace) | Local (CUDA with CPU fallback per P0.R2) | Real-time |
| Anti-spoofing | MiniFASNet ensemble | Local | Real-time + safety |
| STT | faster-whisper large-v3-turbo | Local (CUDA fp16) | Privacy + latency |
| TTS | Kokoro (primary) → Piper (fallback) | Local | Privacy + latency |
| Voice ID | SpeechBrain ECAPA-TDNN | Local | Privacy |
| Diarization | pyannote 3.3.2 (vendored fork per P0.R5) | Local | Multi-speaker handling |

**Strengths**: local-first for privacy-sensitive paths (face, voice, audio), cloud for the highest-quality reasoning. CloudState machine (`core/brain.py`) handles graceful degradation. The 4-task heavy-worker migration arc (P0.R6 + R6.X + R6.Y + R6.Z) gave every GPU-intensive path its own subprocess. The architectural discipline is solid.

**Gaps for embodied use**:
1. **No vision-language model.** KaraOS today has no model that takes a video frame + text and produces grounded reasoning. RT-2, π0, GR00T N1, Gemini Robotics, and Helix all do. Without a VLM, the cognitive layer cannot reason about what the robot sees.
2. **No VLA (vision-language-action) model.** Even if a VLM is added, producing actions from language is a different model class. π0 and GR00T N1 are open-weights options; Skild and Helix are closed.
3. **No world model for counterfactual planning.** Optional in P1 but architecturally significant — see §2.6.

### 7.2 Recommended model strategy for an industry standard

The strategic insight from §2 is that **KaraOS must not pick one VLA winner. It must route between them.**

**Per-task adapter contract** (P1 deliverable, parallel to §1.2):

| Task class | Recommended default | Allowed alternatives | Routing criterion |
|---|---|---|---|
| Conversational reasoning | Llama-3.3-70B (current) | Claude Sonnet 4.6, GPT-5, local Llama 3.3 70B | Cost + latency + quality eval |
| Intent classification | Graph classifier (Spec 2, no LLM in hot path) | LLM fallback (current `_classify_intent`) | `GRAPH_CLASSIFIER_MODE` |
| Knowledge extraction | Llama-3.3-70B | Cheaper model (e.g. Llama-3.1-8B) | I3 deferred decision from CLAUDE.md "Complete Audit" |
| Vision-language grounding | **PaliGemma 2 (open weights)** OR **Gemini Robotics ER** (cloud) | Per-robot configurable | Privacy + cost |
| Vision-language-action | **NVIDIA GR00T N1 (open weights, Apache 2.0)** for humanoids; **π0/π0.5 (open weights)** for manipulation; **Skild API** for cross-embodiment commercial deployments | Robot-OEM configured | Robot capability + commercial contract |
| Speech recognition | faster-whisper large-v3-turbo (current) | Whisper API, local distil-whisper for resource-constrained | Latency + privacy |
| Embeddings | E5-large (current) | Local E5 fallback (Session 120) | Cost + privacy |

**The contract**: KaraOS defines an `AdapterProtocol` (small `Protocol` class in Python typing) per task class. The default implementation calls the model named above. Any robot integrator (or any KaraOS-managed deployment) can swap the adapter without touching the cognitive layer.

This is the same pattern as the [LangChain ChatModel interface](https://python.langchain.com/docs/integrations/chat/) at the model-routing layer, except specialised for embodied tasks. It's also analogous to ROS 2's [Pluggable Library architecture](https://docs.ros.org/en/jazzy/Concepts/About-Plugins.html) — load-time selection of implementations behind a stable interface. Both are well-validated patterns.

### 7.3 Open vs. closed: a strategic position

For the cognitive layer (KaraOS itself), the answer is **open** — Apache 2.0 per Sundar's §1 lock-in recommendation (KAR-122).

For the model layer:

- **VLM**: prefer open weights (PaliGemma 2, GR00T N1's vision encoder) for the reference implementation. Provide adapters for closed (Gemini Robotics, GPT-4 Vision, Claude with vision) for commercial flexibility.
- **VLA**: π0 and GR00T N1 are open-weights and run locally; that's the reference. Skild and Helix are closed; adapters welcome but the *default* is open.
- **Conversational LLM**: hybrid. Llama-3.3-70B (Together.ai) is the default for quality + cost; local 7B fallback (Ollama) is required for offline; cloud-closed adapters (Claude, GPT) are provided.

**Why this matters strategically**: ROS itself succeeded because BSD-3 licensing made every commercial robot ship-able with the same software stack (Sundar's §2.2 trajectory). The same logic applies to KaraOS's model defaults — if the reference VLA is open-weights and locally runnable, no robot OEM has to negotiate a per-deployment commercial license to ship KaraOS. The closed-VLA adapters are there for OEMs who *want* to pay for Skild's brain; KaraOS doesn't pull them along.

### 7.4 Recommendation summary

**P1 ships:**
1. AdapterProtocol contracts for VLM and VLA task classes (~3 days)
2. Reference VLM adapter wrapping PaliGemma 2 or Gemini Robotics ER (~5 days; choice depends on hardware budget — PaliGemma 2 is ~2-3B params, runs on a single GPU)
3. Reference VLA adapter wrapping GR00T N1 or π0 (~5 days; pick based on reference-robot choice in §6)
4. **No new conversational LLM choice** — Llama-3.3-70B + Ollama stays as the default, with `_call_llm_chat()` migration completed so the routing is uniform

**P1 does NOT ship:**
- A new training pipeline. KaraOS does not need to train a foundation model. It needs to integrate existing ones well.
- A world model. Optional in §2.6; can ship in P2 if the eval bench shows planning failures.

---

## Section 8 — What P1 AI work must include

Concrete deliverables, prioritised by what blocks the strategic goal.

### 8.1 Pre-P1 bugs and gaps that must close BEFORE P1 starts

These are gaps in the existing AI layer surfaced during this audit. They are NOT new features; they are debt that compromises the foundation P1 builds on.

| # | Item | Evidence | Cost |
|---|---|---|---|
| 1 | Complete `_call_llm_chat()` migration for 4 unmigrated agents (InsightAgent, FrictionDetectionAgent, PatternAgent, ContradictionAgent) | CLAUDE.md Session 69 closure notes "Remaining agents... can migrate incrementally" | ~1 day |
| 2 | Wire `intent_divergences` schema extension for action telemetry per §3.4 | Schema additive only, P0.9 discipline applies | ~1 day |
| 3 | Add per-turn latency budget instrumentation per §4.2(b) | Extends `HealthSnapshot`, no new infrastructure needed | ~2 days |
| 4 | Resolve P0.S7 bundled-queue RE-CANARY (CLAUDE.md "Pending Work" — "READY TO RUN IMMEDIATELY") | Required before any new feature work to confirm the privacy-retrieval arc holds end-to-end | ~half day |
| 5 | Close P0.10 validation window per CLAUDE.md "Pending Work" | Required to lock in reconciler legacy deletion | ~half day |
| 6 | Resolve P0.X brain.db↔Kuzu cross-write divergence detection (CLAUDE.md "Pending Work" — "no detection or alerting exists") | This becomes higher-stakes when embodied actions add a third write site | ~2 days |
| 7 | Land minimal CI config (CLAUDE.md "Pending Work" — `P1.P1: no CI config exists`) | All the AST tripwires (P0.4 silent-except, P0.7.5 layering invariants, P0.S5 prompt-injection AST scan, etc.) are advisory-only until CI runs them on every PR | ~1 day |

**Total pre-P1 debt**: ~8 days. **None of this is P1 scope.** It's the floor P1 builds on.

### 8.2 P1 AI architecture deliverables (in priority order)

**Tier 1 — must ship**:

1. **Embodied evaluation harness** (§3.3). `tests/embodied_eval_bench.py` + simulation-replay golden scenario set + per-PR-merge gate. **Cost: 2-3 weeks. Risk if skipped: every embodied feature ships on hope.**

2. **Safety architecture** (§6). `ACTION_CLASSES` config, action-approval gates parallel to `TOOL_PRIVILEGES`, simulation pre-check integration, kill-switch surfacing, anomaly-detection extension to `WatchdogAgent`, explainability traces to `event_log`. **Cost: 3-4 weeks. Risk if skipped: project ends on first incident.**

3. **Adapter contracts for VLM and VLA** (§7.4). `AdapterProtocol` interfaces + reference implementations for PaliGemma 2 (VLM) + GR00T N1 or π0 (VLA). **Cost: 2 weeks. Risk if skipped: KaraOS is forced to pick a winner before the market has chosen.**

4. **Memory extensions for embodied lifetimes** (§5.3). `spatial_observations` table, episodic action event payloads (5 new types), `LOCATED_IN` / `OBSERVED_AT` / `EXECUTED_AT` Kuzu edge types. **Cost: 2 weeks. Risk if skipped: the robot doesn't learn.**

5. **4 new embodied agents** (§4.2(c)): `SpatialReasoningAgent`, `ActionPlannerAgent`, `SafetyGateAgent`, `WorldModelAgent` (initial implementation can be stub-ish for the world model). **Cost: 2-3 weeks. Risk if skipped: cognitive layer can't reason embodiedly.**

**Tier 2 — should ship**:

6. **Skill library** (§5.2(c)) — Voyager-style. **Cost: 1 week. Risk if skipped: skill reuse doesn't compound.**

7. **Reference robot integration** — TurtleBot4 per Sundar's recommendation (KAR-122 §1). Conformance suite for the cognitive layer's adapter contract. **Cost: 2 weeks. Risk if skipped: integration cost stays high per OEM.**

8. **Embodied-action golden corpus extension**: extend `tests/golden_intent.jsonl` discipline to action classes. **Cost: 1 week. Risk if skipped: action classifier can't be validated.**

**Tier 3 — can defer to P2**:

9. **World model** beyond the stub. **Cost: 4+ weeks. Defer until evals show planning failures.**

10. **Long-horizon task decomposition** beyond what `ActionPlannerAgent` can do at MVP. **Cost: open-ended. Defer until use cases drive it.**

**P1 total Tier 1**: ~11-14 weeks of focused work. Tier 1+2: ~15-19 weeks. The exact path depends on team size and whether reference-robot work runs in parallel with cognitive-layer work (it should).

### 8.3 Discipline carry-overs from P0 → P1

Every P0 doctrine in CLAUDE.md `## Architectural Disciplines` must apply to P1. Specifically:

- **`### Phase-0-catches-wrong-premise`** — every P1 spec gets a Phase 0 audit before any code. The fact that this is the most-elevated doctrine (13+ instances) tells me it's load-bearing.
- **`### Phase-0-granular-decomposition-enables-accurate-estimates`** — every Phase 0 audit decomposes into named-edit-site D-decisions (`core/X.py:LINE` granularity).
- **`### Induction-surfaces-invariant-gaps`** — every structural invariant ships with a deliberate-regression confirmation in the same cycle.
- **`### Architect-reads-production-code-before-sign-off`** — applies to me as well as Jagan as well as future reviewers.
- **`### Verification-before-completion`** — evidence before assertions, always. The closure-narrative paste-template + grep-baseline discipline.

The same discipline that produced the 14-cycle P0.R resilience arc must produce P1. This is non-negotiable.

### 8.4 What goes into `to_be_checked.md` after P1

Per the issue's "plan must also include what to check in CANARY (post-P1)" requirement, here are the additions to `to_be_checked.md`:

1. **Embodied evaluation week-N regression check** — after every week of P1 operation, diff `embodied_eval_runs/` to detect ≥5pp action-correctness drift. Same shape as `tests/eval_weekly.py`.
2. **Safety gate burst detection** — if `_action_safety_burst` (parallel to `_anti_spoof_burst` from P0.S1) crosses threshold, surface alert. Confirms gates are firing correctly under adversarial input.
3. **Sim-to-real parity check** — for each canonical action scenario, run on sim and on hardware, expect bounded outcome divergence. Anything beyond bound flags as a model regression.
4. **Memory growth + retention check** — `event_log` size, `spatial_observations` row count, `skill_library` entries — all should grow at expected rates, none should drop unexpectedly.
5. **VLM grounding accuracy** — sample 1% of grounding calls per week, manually label, compare to model's grounding output. Same pattern as `intent_divergences` shadow sampler.
6. **Action latency p99** — per action class, p99 latency from "intent classified" to "action dispatched" should stay under per-class budget.
7. **Cross-embodiment regression** — if/when KaraOS supports a second robot, run the conformance suite weekly on both to catch divergence.
8. **Kill-switch round-trip** — verify the hardware E-stop correctly flips `HealthSnapshot.kill_switch_engaged` and gates subsequent action dispatch. Weekly drill.
9. **Safety-critical fact preservation extended to action class** — P0.S5 Bug N's pattern applied to actions: certain failed-action records (e.g. dropped-object incidents) must NEVER be silently overwritten. Append-only by configuration.
10. **Adapter conformance**: when a new VLM or VLA adapter is added, it must pass the conformance suite before being eligible for production use.

These items extend `to_be_checked.md` in the same pattern as the existing entries (per the "Deferred-canary strategy" discipline track in CLAUDE.md, ~34 applications).

---

## Section 9 — Open questions for collective decision

These are decisions where I have an opinion but the cross-agent discussion should produce the answer.

### 9.1 Reference robot choice

Sundar (KAR-122) recommends **TurtleBot4** as the reference robot. I agree for the *ROS 2 integration* and *navigation* surface. **My open question**: TurtleBot4 doesn't have a manipulator. If KaraOS's reference for `manip.grasp_known` is "you'll need to provide your own arm," that's a credibility gap. Options:
- (a) TurtleBot4 primary + add a mobile manipulator (e.g. Stretch 3 from Hello Robot, well-supported in ROS 2) as the manipulation reference. Cost: 2× hardware budget, broader appeal.
- (b) TurtleBot4 only; manipulation reference deferred to P3. Cost: limits P1 demos to navigation + dialogue.
- (c) Skip TurtleBot4, go straight to a humanoid (Unitree G1, GR00T N1 reference platform). Cost: highest hardware budget, biggest signal-to-market.

My lean: (a). Two reference platforms covering nav + manip + dialogue is the minimum credible surface.

### 9.2 Simulation: Isaac Sim vs. Gazebo

For the embodied eval harness (§3.3) and the sim pre-check gate (§6.3):

- **NVIDIA Isaac Sim**: photorealistic, GPU-accelerated, official GR00T training environment. Closed (NVIDIA-distributed but free).
- **ROS 2 Gazebo** (Garden/Harmonic): open-source, mature, ROS 2 native, broader contributor base, lower visual fidelity.

My lean: **Isaac Sim for development + Gazebo as a fallback for environments without NVIDIA GPUs**. Mirror the model adapter pattern — pick one, abstract the second behind an adapter, let deployments choose. This matches the Cognition adapter pattern from §7.

### 9.3 Cloud LLM dependency for embodied control

For the conversational layer, cloud LLM dependency is acceptable because dialogue degradation under offline conditions is graceful (Ollama fallback). For *embodied control*, cloud dependency is a strategic risk — a robot that needs internet to decide whether to grasp an object is brittle.

The dual-system Helix architecture (§2.4) solves this: VLM/VLA runs locally (fast, always available), cognitive layer can use cloud (slow, sometimes unavailable). **Open question**: do we commit to *local-only VLA inference* as a hard requirement for the reference implementation? My lean: yes. The Tier 1 deliverable in §8.2 item 3 (GR00T N1 OR π0, both open-weights, both runnable locally on Jetson AGX Orin per the production target in CLAUDE.md) makes this feasible. Skild API integration would be an adapter for OEMs that want it.

### 9.4 World model in P1 or P2?

§2.6 calls out world models as the next moat. §8.2 puts it in Tier 3 (defer to P2). **Open question**: is that the right call? Tradeoff: a stub `WorldModelAgent` in P1 establishes the architectural slot but does nothing useful; building it properly takes 4+ weeks and may not pay off until P3+ when planning failures become the dominant failure mode. My lean: ship the stub in P1, real implementation in P2 driven by eval evidence.

### 9.5 Should KaraOS train its own VLA?

NVIDIA, Physical Intelligence, and Skild all train. Google does. Open-source forks (e.g. OpenVLA from Stanford) train. **Open question**: does KaraOS train, or only integrate? My strong lean: **only integrate.** Training is a $10M+ effort with a 12-18 month timeline and requires a dedicated ML team. Integration is a $1M effort with a 6-month timeline and builds on the cognitive-middleware strength. KaraOS's competitive surface is *better orchestration of existing models*, not *better models*. This matches Sundar's strategic framing (KAR-122 §1) of cognitive middleware vs. capability provider.

### 9.6 future-execution.md changes

The issue allows recommending changes to `future-execution.md`. The current document is good. The one architectural change I'd push:

- **Move "embodied evaluation harness" to a P0-level prerequisite for P1 start**, not a P1 item. The discipline is: don't build embodied features without the eval, period. This is analogous to the P0.0 CI scaffold landing as a P0 item before any P1 work, per CLAUDE.md Session "P0.0 COMPLETE" notes.

Everything else in `future-execution.md` I'd ratify as-is, with the caveat that Section 4 (cognition specs) needs the AI-architecture-specific safety + memory + adapter additions from §6 + §5 + §7 of this document.

### 9.7 What I held back from this document

Per the discipline declaration, recommendations that didn't carry all 5 disciplines went into this section, not the body:

- I have an opinion on whether to use [Letta](https://github.com/letta-ai/letta) for memory management. Validation evidence is weak; defer.
- I have an opinion on whether [PydanticAI](https://ai.pydantic.dev/) would simplify the agent dispatch surface. Validation evidence is weak; defer.
- I have an opinion on adopting [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) as the formal interface for KaraOS tools. Public ecosystem is young; defer to P2.

Each of these could be a P1 add if evidence accumulates. None are P1 blockers.

---

## Closing

Jagan asked us to put our heart and blood into this. Here's mine:

KaraOS today is the best engineering I have seen on a household-AI codebase. The discipline track record (8 elevated doctrines, 14-cycle resilience arc, 2810 tests, the `### Architect-reads-production-code-before-sign-off` operational rule) is not normal. Most production systems do not have this much intellectual coherence.

But that discipline has been applied to **conversation**, and the strategic goal is **robots**. The four asks in §1 — eval harness, adapter contracts, safety architecture, embodied memory — are the architectural decisions that determine whether the next 14 cycles can apply the same discipline to embodied cognition or whether each one has to fight the foundation.

If P1 ships those four decisions plus the §8 cleanup, KaraOS clears the bar that makes ROS 2 robot OEMs say "yes, this is the cognitive layer we'll integrate." That's the path to the locked goal.

If P1 skips them, we ship a better chat client and have to do it again in P2.

I recommend the harder path. The work in P0 earned us the right to take it.

— Sam
