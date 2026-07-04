# KaraOS Roadmap

Where this project is going after the current cognitive-layer hardening cycle closes. This document is forward-looking — nothing in sections 2 through 5 is shipped today unless explicitly noted. Section 6 names the limits honestly.

For where the project is *today*, read [`README.md`](README.md). For the engineering process that produced what's there, read [`BUILT_WITH_AI.md`](BUILT_WITH_AI.md). For the system architecture as it currently runs, read [`ARCHITECTURE.md`](ARCHITECTURE.md).

This roadmap distills the strategic decisions and phased plan from a longer internal spec. The internal version covers implementation detail (test plans, module structures, IPC protocols, acceptance criteria) that is useful for the developer building the thing but not for understanding direction. This file covers direction.

---

## 1. Where we are

KaraOS is a working cognitive layer for AI companions. It recognizes who is in the household across face and voice, remembers each person across sessions, handles a room of multiple speakers without losing track of who's talking to whom, and enforces a four-tier privacy model on every memory write and retrieval. The intent classifier graduated from LLM-prompted to pure-graph (zero LLM calls in the classification hot path); on a published academic benchmark (multi-party turn-taking on the Friends corpus), it sits competitively with fine-tuned models that required 120,000+ labeled training examples while using ~2,000 retrieval scenarios and no gradient descent.

4,237 automated tests (0 failed) cover identity, memory, privacy enforcement, room orchestration, conversation, intent classification, schema migrations, atomic cross-storage writes, and tool execution safety. ~30 structural invariants are CI-enforced via AST-based ratchets that make the discipline durable across future contributors.

The current correctness arc is closing. The cognitive layer is stable. The next chapter is embodied integration — making the same cognitive runtime work as the brain for robot bodies.

---

## 2. Where this is going

The one-line product positioning:

> **KaraOS is durable cognitive middleware for ROS 2 robots — the trustable layer that turns natural-language commitments into scheduled, policy-checked, verifiable robot skill execution, on top of motion primitives the robot platform owns.**

This is what KaraOS is built to become. It is not what KaraOS is today. The cognitive layer that exists is the foundation; the embodied integration is the work ahead.

### 2.1 What KaraOS IS (today and going forward)

- A durable commitment store that survives process restart
- A scheduler that fires user commitments at their due time with late-policy semantics if missed
- A policy engine that gates every consequential action against rule-based YAML / JSON policy
- A planner that decomposes natural-language commands into structured skill sequences
- A verifier registry that confirms world-state changes through sensor data or platform APIs (not just trusting that the command was sent)
- An audit log that records every state transition with replayable detail
- A robot-agnostic API: same KaraOS source runs across mock, simulated, and real robots without core code change
- The cognitive runtime: multi-person identity, structured memory, privacy-tier visibility, conversation orchestration, safety preservation — all of which exists today

### 2.2 What KaraOS IS NOT (and won't be)

- **Not a motion controller.** It does not generate joint trajectories, compute inverse kinematics, or run whole-body control. Those are the robot platform's responsibility. The sim-to-real gap for embodied motion is an active multi-billion-dollar research problem at Boston Dynamics, Figure, 1X, Tesla Optimus, Nvidia GR00T. KaraOS does not enter that fight.
- **Not a perception system.** It does not run object detection, SLAM, or grasp detection. It consumes the outputs of those systems through a capability layer.
- **Not a ROS 2 replacement.** It depends on ROS 2 for transport. It is a layer above, not a fork.
- **Not a robotics simulator.** It uses Gazebo / MuJoCo / Isaac as a backend. It does not build a physics engine.
- **Not an LLM agent framework.** It does not generate code or arbitrary Python at runtime. The LLM proposes structured plans; KaraOS executes from a fixed capability registry.
- **Not a humanoid hardware company.** Not building robots.
- **Not a chatbot demo.** The conversational layer exists in service of durable, verifiable embodied actions.

### 2.3 The brutal scope rule

KaraOS v1 will claim only this:

> A simulation-tested, ROS 2-ready embodied execution runtime that converts natural-language commitments into durable, policy-checked, verifiable robot skill execution, against any robot platform that implements the KaraOS Adapter SDK and passes the conformance suite.

Allowed claims before physical-robot testing:

- works with mock robot adapters
- works with simulator adapters
- can issue ROS 2 actions through a controlled adapter
- survives restart for scheduled commitments
- blocks unsafe instructions by policy
- logs and replays execution
- verifies simulated world state before claiming completion
- supports multiple body types through capability contracts
- ships with a published Adapter SDK + conformance suite

Forbidden claims before physical-robot testing:

- proven safe on real humanoids
- production hardware safety certified
- works on all robots in the real world
- replaces ROS 2
- controls any humanoid without robot-specific motion primitives
- guarantees physical manipulation reliability
- solved sim-to-real for locomotion or manipulation

The discipline is to not overclaim. Robotics is a field where overclaiming has destroyed credibility for many otherwise-promising projects.

---

## 3. The architectural bet

Six locked architectural decisions distinguish KaraOS from the typical "LLM + robot = robotics demo" approach. These are the load-bearing choices the rest of the system is built around. Each one is a deliberate scope cut — what KaraOS does *not* do is as important as what it does.

### 3.1 KaraOS does not own motion primitives

Motion primitives (`sit`, `walk_forward`, `grasp`, `touch_head`) are provided by the robot platform. Whoever ships the robot — Unitree, Boston Dynamics, Figure, 1X, Nvidia GR00T-trained policies, MoveIt 2 motion planners — provides the primitives. KaraOS calls them as opaque capabilities through an adapter.

The sim-to-real gap for embodied motion is the active research problem in robotics. Solving it requires actuator modeling, contact physics calibration, domain randomization, and platform-specific tuning — months to years per robot platform. KaraOS depends on whoever wins that fight. Trying to own the motion layer would be entering a fight with companies that have raised hundreds of millions of dollars; it would also fail at distinguishing what KaraOS uniquely offers (orchestration / memory / policy / audit) from what is commodity.

### 3.2 Capability-typed sensor abstractions, not sensor-model-typed

KaraOS defines a small fixed set of sensor capability abstractions: `Rangefinder`, `PoseEstimator`, `VisualSensor`, `ContactDetector`, `OrientationEstimator`, `AudioSensor`, `HealthSensor`, `ApplianceState`. Concrete sensors — lidar, sonar, depth camera, time-of-flight, IMU, smart plug, weight sensor — map *into* these capabilities through small per-sensor drivers. Skills consume capabilities, not concrete sensors.

Without this abstraction, "KaraOS works on any robot" becomes an N×M problem: every skill needs an integration for every sensor type. With this abstraction, ~10 capability interpreters cover the space, and a new concrete sensor needs only one small driver to plug into every existing skill.

### 3.3 Adapter SDK as a separately-published package, with a conformance suite

The KaraOS Adapter SDK ships as a standalone Python package, installable independently of the KaraOS core runtime. Robot platforms (Unitree, Figure, hypothetical future partners) implement an adapter against the SDK; a conformance test suite verifies the adapter satisfies the architectural contract before the platform can claim "KaraOS compatible."

Without this packaging, every partner integration is bespoke — a snowflake fork of the codebase. With it, "passes the KaraOS conformance suite v1.0" becomes a verifiable checkbox like "supports OpenXR" or "supports OAuth 2.0." Network effects accumulate: more conformant adapters → more value to deployers → more incentive for new platforms to conform.

### 3.4 Per-skill verifier registry, not a universal verifier

Each skill has at least one registered verifier. Verifiers use the cheapest reliable sensor for the world-state question being asked. Examples:

- Oven on / off → smart plug power-draw measurement
- Robot reached zone → pose estimator + zone polygon check
- Dog bowl food level → weight sensor or vision delta
- Generic visual state → local 2B-parameter VLM (Moondream2 or Qwen2-VL-2B) as last resort

Generic frontier-VLM verification is explicitly *not* the default. Universal VLM verifiers hallucinate, cost money per call, and add cloud dependencies. Per-skill verifiers using the cheapest reliable sensor are honest, cheap, and reliable — and the local 2B VLM fallback is reserved for the cases where no proxy sensor exists.

### 3.5 Three-gate safety model

Every skill execution passes through three independent gates before being marked complete:

1. **Policy engine** (pre-skill, rule-based): "is this action allowed in this context?" — YAML / JSON rule engine with deterministic decisions
2. **Digital twin validator** (pre-skill, physics-based): "will this motion cause self-collision, joint-limit violation, workspace breach, or balance loss?" — MuJoCo-based pre-execution simulation
3. **Verifier registry** (post-skill, outcome-based): "did the world actually change as expected?" — per-skill verifier reading sensor data or platform API

A skill is only marked complete when all three gates pass. Failing any gate transitions the task to a corresponding failure state with audit. The three gates protect against different failure modes: policy catches "shouldn't do this," digital twin catches "would break the robot," verifier catches "thought we did it but didn't."

### 3.6 The LLM never calls the adapter directly

The LLM proposes structured commitments. The KaraOS runtime stores them. The policy engine gates them. The digital twin validates them. The skill runtime executes them through the adapter. There is no execution path from LLM output to adapter call that bypasses the gates. This is enforced structurally — an AST-based CI test scans the codebase to ensure no future refactor accidentally short-circuits the chain.

LLMs are not safety controllers. Treating them as one is the failure mode that produces "AI shut down my house" demo videos. The structural invariant exists because human discipline alone is not reliable enough at scale.

---

## 4. Capability ontology v1.0 (preview)

The locked vocabulary every robot adapter implements and every skill consumes. Versioned (v1.0); additions go through a v1.1 review with explicit criteria.

### 4.1 Actuator capabilities (the skills a robot may declare it can perform)

| Skill | Required body capabilities | Risk |
|---|---|---|
| `sit` | base, balance | low |
| `stand` | base, balance | low |
| `walk_forward` | locomotion | medium |
| `walk_to` | locomotion, localization | medium |
| `rotate_in_place` | locomotion | low |
| `look_at` | head articulation | low |
| `point_at` | arm articulation | low |
| `raise_hand` | arm articulation | low |
| `touch_link` | arm articulation, self-proprioception | low (self) / medium (other) |
| `grasp_object` | gripper, vision, manipulation | high |
| `place_object` | gripper, manipulation | high |
| `press_button` | end-effector | medium |
| `turn_knob` | end-effector | medium |
| `open_door` | end-effector, manipulation | high |
| `speak` | audio output | low |
| `report_state` | reporting | low |
| `emergency_stop` | safety override | always-allowed |

Each skill has a full YAML spec with preconditions, parameters, postconditions, expected duration, failure modes, verification capability, and policy tags. Adding a new skill is a v1.1 review.

### 4.2 Sensor capabilities (the abstractions skills consume)

| Capability | What it provides |
|---|---|
| `Rangefinder` | Latest distances and bearings (lidar, sonar, depth camera, ToF) |
| `PoseEstimator` | 6-DOF pose with uncertainty (odometry, AMCL, VIO, AR-tag) |
| `VisualSensor` | RGB / mono frames with intrinsics (camera) |
| `ContactDetector` | Contact magnitude per link (limit switch, FSR, tactile array) |
| `OrientationEstimator` | Quaternion + angular velocity (IMU) |
| `AudioSensor` | Waveform + direction-of-arrival (microphone array) |
| `HealthSensor` | Per-metric scalars with units (battery, current, thermal) |
| `ApplianceState` | Discrete state per appliance ID (smart home APIs) |

A new sensor model is integrated by writing one driver that maps its native data to the appropriate capability interface. All existing skills consuming that capability immediately work on robots with that sensor.

This is the architecture that lets "KaraOS works on any robot" be a checkable claim instead of marketing.

---

## 5. Phased roadmap

Nine phases. Each phase has explicit deliverables and exit criteria; this section names intent, not detail.

### Phase 0 — Foundation and design lock (~1 week)

Architecture documents, capability ontology v1.0, adapter SDK skeleton, schemas, structural invariant tests scaffolded but skipped. The "spec everything before code" phase that pays back in mid-flight rework avoided.

### Phase 1 — Pure Python embodied runtime (~3 weeks)

The strictest minimal viable embodied system. No ROS 2. No Gazebo. No voice integration. CLI input only. Single process.

What ships: commitment storage in SQLite with crash-atomic writes, append-only audit log, durable scheduler that survives restart, YAML rule-based policy engine, planner driven by local 7B-14B LLM, runtime orchestrator, verifier registry reading mock-world ground truth, mock robot adapter, in-memory household mock world (oven, dog bowl, kitchen zone, blocked path).

The first investor-grade demo: typed command "turn off the oven in 45 minutes and feed the dog after that" → durable commitment → restart-resilient scheduling → mock execution → audit trail. No robot needed. The cognitive value (durability, policy, verification, audit) is provable before any motion is involved.

### Phase 2 — Dashboard view and LLM eval discipline (~1.5 weeks)

Embodied runtime view in the existing Next.js dashboard: active commitments, scheduled tasks, robot adapter status, world state, policy decisions, execution timeline, verifier results, audit log viewer.

LLM eval framework: golden sets per LLM-prompted component (commitment parser, policy decision, verifier reasoning), drift detection via monthly cron, regression thresholds. Cost ledger tracking per-call LLM token usage.

Two-process split: durable layer (commitment DB + scheduler + audit) separated from interactive layer (conversation + voice + dashboard) via local gRPC IPC. Either process can restart without losing the other's state.

### Phase 3 — Multi-body capability test (~1.5 weeks)

Three additional mock adapters (humanoid, quadruped, arm-only) declaring different capability subsets. Same KaraOS commitment runs against all of them where capability matches; adapters reject skills they don't support with honest explanations ("I can't pick things up — I have legs but no hands").

Validates the "KaraOS runs on any compliant adapter" claim against multiple mock bodies before the real ROS 2 work begins.

### Phase 4 — ROS 2 bridge and Gazebo (~3 weeks)

WSL2 Ubuntu + ROS 2 Jazzy installed. ROS 2 bridge package implementing the adapter SDK contract over local gRPC. Gazebo Sim scene with a Unitree G1 humanoid (open URDF, ~$16k retail — the cheapest humanoid on the market). Capability interpreters wired up: Rangefinder, PoseEstimator, VisualSensor, ContactDetector, OrientationEstimator.

First simulator demo: KaraOS commitment → policy gate → digital twin validation → ROS 2 action on simulated Unitree G1 → verifier reads sim ground truth → audit trail. The first time the system controls something visibly robotic.

### Phase 4.5 — Digital twin pre-execution validator (~1.5 weeks)

The third safety gate fully landed. MuJoCo digital twin of the active robot, motion validated before any ROS 2 command is published. Self-collision detection, joint-limit checks, workspace bounds, balance verification for legged robots.

### Phase 5 — Verification design fully realized (~2 weeks)

Every skill in the ontology has at least one registered verifier. Local 2B VLM verifier (Moondream2 or Qwen2-VL-2B) integrated and calibrated for the fallback path. Verifier abstention protocol implemented — verifiers can return "uncertain" instead of being forced to a binary pass/fail.

### Phase 6 — Adversarial and safety hardening (~2 weeks)

Prompt injection resistance, multi-user contention handling, cost ceiling enforcement, offline degradation modes, crash injection across state transitions. The threat model from the internal spec becomes a tested test suite.

### Phase 7 — Adapter SDK published and conformance suite (~2 weeks)

`karaos-adapter-sdk` released as a separately-installable Python package. Conformance test suite published — partners run `karaos-conformance --adapter their_adapter` and either pass or get an actionable failure list. Migration guide for partner integration. Reference adapters (Unitree G1, mock humanoid, mock quadruped, mock arm, mock mobile manipulator) all pass conformance.

This is the moment KaraOS becomes a partner-extensible platform rather than a single-user demo.

### Phase 8 — Investor / partner proof pack (~1 week)

Recorded demos for all phases. Architecture diagram. Standards alignment matrix (ISO/TS 15066, OWASP LLM, NIST AI RMF). Test report. Limitations document. One-page product brief.

### Phase 9 — Physical robot readiness (~3 weeks, gated on hardware availability)

Hardware adapter checklist, ROS 2 robot onboarding guide, emergency stop physical interface, physical safety preflight protocol, hardware-in-the-loop test plan. First physical adapter (Unitree G1 hardware if available, or a borrowed alternative).

---

## 6. What this isn't yet

A few honest limitations:

- **The roadmap above is forward-looking.** As of the date of this file, the embodied integration phases (1 through 9) have not started. The cognitive layer in [`README.md`](README.md) is what exists.

- **No robot has been controlled by KaraOS.** Not in a simulator, not in hardware. The architectural decisions in section 3 are made; the work of executing them is ahead.

- **The Adapter SDK does not exist yet.** Designed, not implemented. The "any compliant robot" claim is conditional on Phase 7 landing.

- **Timelines in section 5 are weeks of focused solo development.** Not calendar weeks. Calendar time will be longer due to ordinary life and the parallel work of the cognitive layer hardening cycle.

- **The robot platform owns motion.** This is a deliberate scope choice, not a limitation we plan to remove. Any future claim about KaraOS "controlling" a robot is really a claim about KaraOS calling the robot platform's existing motion primitives at the right time with the right safety checks. That distinction is load-bearing for honest positioning.

- **No commercial partner has signed on.** The partner-extensible architecture exists in the design; partners themselves come later. Phase 7 is the first concrete partner-facing artifact, and partner adoption (if any) is downstream of that.

- **Sim-to-real is not solved by KaraOS.** When a real robot's `sit` primitive works on real hardware, it's because the robot manufacturer did the months of sim-to-real engineering for their platform. KaraOS rides on that work.

These limits are deliberate. They define what KaraOS is responsible for and what other parts of the embodied AI ecosystem are responsible for. Misreading them — claiming KaraOS does motion, or perception, or sim-to-real — is the failure mode this roadmap is designed to prevent.

---

## Where to read next

- For the system as it runs today: [`README.md`](README.md), [`ARCHITECTURE.md`](ARCHITECTURE.md)
- For the engineering process: [`BUILT_WITH_AI.md`](BUILT_WITH_AI.md)
- For the published-benchmark validation: [`published-papers-tests/results/RESULTS.md`](published-papers-tests/results/RESULTS.md)
- For live system traces: [`terminal-logs/`](terminal-logs/)

For the internal spec that this roadmap distills from — covering implementation detail, test plans, IPC contracts, eval discipline, and open decisions per phase — contact me directly. The internal version is working strategy, not portfolio material. This roadmap is the public-facing version.
