# KaraOS Competitive Positioning

**Document type:** living intelligence document. Updated quarterly minimum.
**Last refresh:** 2026-05-16 (initial draft, post `future-execution.md` v2)
**Next scheduled refresh:** 2026-08-16
**Owner:** KaraOS architect (rotates if team grows)
**Source companion:** `future-execution.md` Section 2.4 (this file expands that section)

---

## 0. Purpose, Cadence, and Confidence Levels

### 0.1 Purpose

This document exists to answer four questions, repeatedly, as the market changes:

1. **Where exactly does KaraOS sit in the embodied-AI stack?**
2. **Who is in adjacent layers, and what do they cover that KaraOS doesn't?**
3. **What is the defensible gap KaraOS uniquely fills, and is that gap still real?**
4. **What strategic moves by competitors would force KaraOS to re-scope?**

The robotics market in 2026 is moving fast. A position that's defensible today can collapse in 6 months if a competitor ships the wrong feature. This doc is the canonical reference that prevents the team from drifting into either (a) over-confident "no one is doing this" framing or (b) panicked "they're already doing everything" reactivity.

### 0.2 Refresh cadence

| Trigger | Action |
|---|---|
| Quarterly (every 3 months) | Full refresh — re-verify every competitor's stated features, check for new entrants |
| Major announcement from a Layer-A / Layer-C / Layer-F competitor | Targeted update, same week as announcement |
| Before any phase kickoff in `future-execution.md` | Quick review — has the competitive picture changed since last refresh? |
| Before any partner / investor pitch | Verify all claims in pitch deck match this doc's current state |

### 0.3 Confidence levels for claims

Every claim in this doc carries an implicit confidence level. The convention:

- **[Verified-2026-05]** — confirmed via primary source (company website, GitHub, arxiv paper, official announcement) at the dated month
- **[Reported-2026-05]** — appears in reputable secondary source (RobotReport, TechCrunch, Reuters, etc.) but not directly verified against primary
- **[Inferred]** — analysis or deduction from observed evidence, not a directly stated fact
- **[Estimated]** — best guess given context, e.g. revenue, headcount, deployment scale
- **[Stale-since-DATE]** — claim was true at DATE but hasn't been re-verified since

When updating: do NOT silently re-date claims. If you re-verify a claim and it's still true, bump the date. If you can't re-verify, mark `[Stale-since-DATE]` and note in the changelog.

---

## 1. Methodology

### 1.1 What sources we use

**Tier 1 (primary):**
- Company websites (especially "about", "research", "blog", "docs" pages)
- Official GitHub repos and their READMEs
- arxiv preprints by the company / project
- Official conference announcements (CES, GTC, NeurIPS, CoRL, ICRA, RSS)
- SEC filings, official funding announcements
- Conformance suite results from competitors that publish them

**Tier 2 (reputable secondary):**
- The Robot Report, IEEE Spectrum, RoboticsBusinessReview
- TechCrunch, The Verge, Wired, CNBC, Bloomberg (for funding/strategy)
- DeepMind blog, Nvidia developer blog (for foundation models)
- Hacker News discussions (read with skepticism, but signal-rich)

**Tier 3 (signal, not source):**
- Twitter/X announcements (must verify against Tier 1 before claiming)
- Forum posts (ROS Discourse, r/robotics)
- Substack posts by industry analysts

**Reject:**
- Press releases without verifiable demos
- Sponsored content / advertorials
- LinkedIn posts without external corroboration

### 1.2 How we evaluate each competitor

For each competitor, we answer eight questions:

1. **Layer** — which of the six layers does this company / project occupy?
2. **Maturity** — research / pre-alpha / alpha / beta / production / shipping at scale?
3. **Open or closed?** — source code, model weights, conformance suite available?
4. **Capability overlap with KaraOS** — what features of KaraOS does this competitor already provide?
5. **Capability gaps vs KaraOS** — what features does this competitor lack that KaraOS plans?
6. **Strategic threat level** — could they extend into KaraOS's lane?
7. **Strategic dependency** — does KaraOS depend on this competitor in any way?
8. **Last verified date** — when was this analysis last reconfirmed?

### 1.3 Anti-bias rules

- **Don't dismiss competitors.** Every "they don't do X yet" claim assumes their roadmap doesn't include X. Check their public roadmap before claiming a gap.
- **Don't oversell KaraOS.** Every "no one else does Y" claim must survive a focused 30-minute search. If it doesn't, soften the claim.
- **Update when wrong.** If a refresh shows a previous claim was wrong, note it in the changelog (Section 11). Don't silently revise.
- **Cite sources.** Every factual claim links to a source in Section 12.

---

## 2. The Six-Layer Stack

KaraOS operates in a stack with six distinct layers. Each layer has different players, different economics, different defensibility shapes. The chart:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ LAYER F — Consumer / home humanoid hardware                              │
│ Examples: 1X NEO, Figure (industrial first), Tesla Optimus, Unitree G1   │
│ Economics: hardware sales + service subscriptions                        │
│ KaraOS relationship: target customer (Unitree G1 our reference)          │
├──────────────────────────────────────────────────────────────────────────┤
│ LAYER E — Industrial process orchestration (different vertical)          │
│ Examples: Intrinsic Flowstate (now Google), Apex.Grace (automotive)      │
│ Economics: enterprise licenses, factory integration consulting           │
│ KaraOS relationship: NOT a target market (different vertical)            │
├──────────────────────────────────────────────────────────────────────────┤
│ LAYER D — Cognitive middleware / durable orchestration ★ KARAOS ★        │
│ Examples: KaraOS (us), partial: 1X internal Chores backend              │
│ Economics: open-core SDK + paid enterprise features (proposed)           │
│ KaraOS relationship: this is our home                                    │
├──────────────────────────────────────────────────────────────────────────┤
│ LAYER C — LLM-to-robot single-turn executive                             │
│ Examples: ROSClaw, ROSA (NASA-JPL), ros-mcp-server family, AutoRT       │
│ Economics: open-source mostly; research outputs                          │
│ KaraOS relationship: adjacent; we sit above them or complement them      │
├──────────────────────────────────────────────────────────────────────────┤
│ LAYER B — Reactive control / SLAM / motion planning                      │
│ Examples: Nav2, MoveIt 2, custom per-platform controllers                │
│ Economics: open-source ecosystem; vendor-specific paid                   │
│ KaraOS relationship: KaraOS depends on these; never competes             │
├──────────────────────────────────────────────────────────────────────────┤
│ LAYER A — Motion / Vision-Language-Action models                         │
│ Examples: Physical Intelligence π, GR00T, Skild, Figure Helix, Gemini-R  │
│ Economics: $400M-$14B raised; research + enterprise licensing            │
│ KaraOS relationship: KaraOS depends on these; never competes             │
└──────────────────────────────────────────────────────────────────────────┘
```

**Why layer separation matters:** if KaraOS ever drifts into Layer A or B, we are fighting a multi-billion-dollar fight we cannot win. If we drift into Layer F, we are competing with hardware companies and need to make robots. Layer D is the only layer where one solo developer + a small team can build something defensible.

---

## 3. Layer-by-Layer Deep Dive

### 3.1 Layer A — Motion / Vision-Language-Action models

**What this layer does:** generates joint commands, motion trajectories, or skill primitives from natural language and/or sensor input. Outputs feed directly into the robot's motor controllers.

**Key economics:** foundation-model scale. Training requires millions of robot trajectory hours or human-video equivalents. Compute spend is in the tens of millions per training run. Defensibility comes from data moat, model scale, and partnerships with robot manufacturers.

**Players (2026-05):**

| Player | What they ship | Maturity | Open? |
|---|---|---|---|
| **Physical Intelligence (π)** | π-0, π-0.5 — VLA model, joint commands at 50Hz, openpi GitHub | Production (deployed on 7 robot platforms) | **Open weights** [Verified-2026-05] |
| **Nvidia Isaac GR00T N1** | Open humanoid foundation model, System 1/2 architecture | Production / partner-shipping | **Open** (with Nvidia ecosystem lock-in) [Verified-2026-05] |
| **Skild AI** | "Omni-bodied" robot brain across humanoid/quadruped/arm/mobile manipulator | Production deployments (security, inspection, delivery, warehouses) | Closed [Verified-2026-05] |
| **Figure Helix-02** | System 0/1/2: kHz balance + perception→motion + reasoning | Production (8-hour autonomous shifts demonstrated 2026-05) | Closed, Figure-only [Verified-2026-05] |
| **Google Gemini Robotics** | Foundation model, Boston Dynamics Atlas partnership, on-device variant | Shipping to Atlas in 2026, Hyundai 2028 | Closed [Verified-2026-05] |
| **OpenVLA, Octo, RT-2** | Open-source / academic VLA models | Research / experimental | **Open** |
| **Tesla Optimus** | Proprietary neural motion controller | Factory pilot only | Closed |

**KaraOS strategic relationship to Layer A:**
- ✅ KaraOS depends on at least ONE of these per supported robot platform
- ✅ KaraOS becomes more valuable as Layer A improves (better motion primitives = better commitment execution)
- ✅ KaraOS is platform-agnostic across Layer A providers (a partner could use π, GR00T, or Skild and KaraOS doesn't care)
- ❌ KaraOS does NOT compete here; this is decided
- ⚠️ Layer A players occasionally extend upward into Layer D (e.g., GR00T blueprint includes some orchestration scaffolding). Monitor.

### 3.2 Layer B — Reactive control / SLAM / motion planning

**What this layer does:** runs control loops at 100Hz-10kHz; SLAM for localization; path planning; collision avoidance; motion trajectory generation for arms.

**Players (2026-05):**
- **Nav2** (open ROS 2 stack) — navigation, path planning, obstacle avoidance
- **MoveIt 2** (open) — motion planning for manipulator arms
- **Apex.Grace** (commercial, ISO 26262 ASIL D) — safety-certified ROS 2 for automotive
- **Robot-specific custom stacks** — every humanoid vendor has their own balance/locomotion controllers

**KaraOS strategic relationship to Layer B:**
- ✅ KaraOS depends on these for actual robot motion
- ✅ KaraOS skill primitives map to these controllers via the adapter
- ❌ KaraOS does NOT replace them

### 3.3 Layer C — LLM-to-robot single-turn executive (closest competitive layer)

**What this layer does:** translates one natural-language command into one or more robot actions, with some safety validation and audit. Operates per-turn, no persistent state across conversations.

**Players (2026-05):**

#### ROSClaw — the closest direct competitor

**Status [Verified-2026-05]:** Pre-Alpha v0.1. arxiv preprint published 2026. Active development.
**Self-description:** "AUTOSAR + Android for Embodied AI."
**Repo:** `github.com/ros-claw/rosclaw`
**Funding/team:** Unknown — appears to be a research/open-source project.

**What ROSClaw does:**
- Affordance Manifest (capability registry, ROS 2 introspection-driven)
- Observation Normalizer (canonical sensor representation, supports native multimodal or VLM-bridged perception)
- Validator (pre-execution gating: velocity bounds `‖v‖ ≤ v_max ∧ |ω_z| ≤ ω_max`, interface allowlists)
- Audit Log (append-only structured logging)
- Three transport modes: local DDS (<1ms), rosbridge WebSocket (5-10ms), WebRTC P2P (20-100ms)
- Model-agnostic via OpenClaw agent platform (tested with Claude Opus 4.6, GPT-5.2, Gemini 3.1 Pro, Llama 4 Maverick)
- Multi-platform tested: TurtleBot3 Waffle Pi, Unitree Go2 Pro, Unitree G1
- **Digital Twin Firewall (MuJoCo)** — pre-validates motions before execution. KaraOS adopted this concept as Decision 3.14.

**What ROSClaw explicitly LACKS (their own admission in the arxiv paper):**
- ❌ Reactive control (1-3s LLM latency per turn confines it to deliberative planning)
- ❌ Formal safety certificates ("enforced invariants, not certificates")
- ❌ Loop-breaking / replan circuit breaker (planned future work)
- ❌ Dynamic safety policy adjustment (config-time only, not runtime-adaptive)
- ❌ Authorization via discovery (capability discovery is informational only)
- ❌ Durable commitments — STRICTLY per-turn deliberative
- ❌ Scheduling — NO "do this in 45 minutes"
- ❌ Per-skill verifier registry with abstention protocol
- ❌ Published partner SDK with conformance suite
- ❌ Multi-step state across turns
- ❌ Multi-user contention
- ❌ Cost ledger
- ❌ Offline degradation handling

**Threat level: HIGH.**
Their architecture is in the right shape to extend into KaraOS's lane. Adding SQLite-backed commitments + scheduler is conceptually 2-3 weeks of work for a focused team. If they ship v0.2 with commitment storage, KaraOS's "no one combines durable + verified + audited cognitive middleware" claim weakens significantly.

**Monitoring:** GitHub releases at `ros-claw/rosclaw`, arxiv paper version bumps.

**Strategic response:**
1. Ship Phase 1 within 8-10 weeks of `complete-plan.md` close, claim "durable cognitive middleware" framing first.
2. Adopt their digital-twin-firewall concept (already done as Decision 3.14).
3. Consider whether to **fork ROSClaw and extend** vs **build from scratch alongside** — see Section 10 below.
4. Position KaraOS as the multi-turn / durable / verifiable layer; let ROSClaw own single-turn deliberative.

#### ROSA (NASA-JPL)

**Status [Verified-2026-05]:** Open-source, published. Maintained by NASA's Jet Propulsion Laboratory.
**Repo:** `github.com/nasa-jpl/rosa`
**arxiv:** "Enabling Novel Mission Operations and Interactions with ROSA"

**What ROSA does:**
- AI agent for interacting with ROS 1/2 systems via natural language
- Built on LangChain framework
- Designed for inspecting, diagnosing, understanding, and operating robots
- Supports speech integration, visual perception
- Custom-agent extensibility — inherit from ROSA class or create custom instances

**What ROSA is for:** spacecraft / rover / lab-bench operational queries. "Tell me the joint state." "What sensors are active?" "Diagnose this fault."

**What ROSA is NOT for:** durable user commitments, scheduled execution, policy-gated skill execution at consumer scale.

**Threat level: LOW.**
Different use case. They are operations-focused; KaraOS is task-execution-focused. Could potentially cross-pollinate ideas but unlikely to extend into KaraOS's lane.

#### ros-mcp-server family (multiple projects)

**Status [Verified-2026-05]:** Multiple open-source MCP servers exposing ROS topics/services/actions to LLM clients via Anthropic's Model Context Protocol.

**Projects:**
- `github.com/robotmcp/ros-mcp-server` — bidirectional Claude/GPT/Gemini ↔ ROS
- `github.com/kakimochi/ros2-mcp-server` — Python-based, FastMCP, publishes /cmd_vel
- `github.com/TakanariShimbo/rosbridge-mcp-server` — rosbridge WebSocket
- `github.com/gtoff/moveit-mcp-server` — MoveIt 2 motion planning
- Robot Developer Extension for ROS 2 (Ranch Hand Robotics) — preview MCP feature
- `github.com/Auromix/ROS-LLM` — 10-minute integration framework

**What they do:** one-shot LLM-to-ROS translation. Publish to topics, call services, set parameters, read sensor data, monitor state.

**What they lack:** state persistence, scheduling, policy gating, audit, verification, multi-step orchestration.

**Threat level: MEDIUM (collectively).**
Not individually threatening, but the **standardization wave** is threatening: if MCP becomes the lingua franca for robot LLM integration, KaraOS must be MCP-native or fight the protocol. Decision 3.13 addresses this — KaraOS exposes itself as an MCP server, treating MCP as adoption channel rather than competitor.

**Strategic response:** ship KaraOS's MCP server interface in Phase 4. Be the durable cognitive backend that the MCP-server family doesn't provide.

#### Google AutoRT

**Status [Verified-2026-05]:** Research framework, deployed at scale internally. arxiv: "AutoRT: Embodied Foundation Models for Large Scale Orchestration of Robotic Agents."

**What AutoRT does:**
- VLM for scene understanding + grounding
- LLM for proposing diverse novel instructions to a fleet
- Tested with 20+ robots simultaneously, up to 52 unique robots total
- 77,000 real-world robotic trials, 6,650 unique tasks, 7 months
- **"Robot Constitution"** — Asimov-inspired safety prompts: foundational + safety + embodiment categories
- Safety guardrails include force-threshold auto-stop and line-of-sight human supervision

**What AutoRT is for:** **fleet-scale autonomous data collection** for training Layer-A models. Robots propose their own goals and act. 1 human supervises 3-5 mobile manipulators.

**What AutoRT is NOT for:** user-driven commitments, durable schedules, partner middleware.

**Threat level: LOW-MEDIUM.**
Different orientation. Google's interest is data collection at scale for foundation model training, not building a partner middleware product. But Google **could** productize AutoRT-style orchestration if they wanted to. Boston Dynamics + Gemini Robotics partnership (CES 2026) opens a path here.

**Important takeaway:** Google's "Robot Constitution" prompts are conceptually similar to KaraOS's policy engine. The framing is comparable. KaraOS's policy engine is more structured (YAML rules with conditions/actions vs natural-language constitution prompts). Both are valid; KaraOS's structure is more deterministic and auditable.

### 3.4 Layer D — Cognitive middleware / durable orchestration (KaraOS's home)

**What this layer does:** persists user commitments across restarts, schedules future execution, policy-gates every skill call, validates motions physically (digital twin), verifies world-state outcomes, audits every state transition, exposes a partner-extensible adapter SDK with conformance suite.

**Players (2026-05):**

| Player | Status |
|---|---|
| **KaraOS (us)** | Spec'd in `future-execution.md` v2. Phase 0 not yet started. |
| **1X (internal Chores backend)** | Production, but **proprietary to 1X NEO hardware only**. Not partner middleware. See Layer F profile below. |
| **Generic durable agent frameworks** | LangGraph checkpointing, Cloudflare Durable Objects, Temporal, Inngest, AWS Step Functions — these provide the *persistence primitive*, but NONE are bound to a robot capability registry. |

**Critically: no horizontal partner middleware exists in this layer.** This is the defensible gap. See Section 5.

### 3.5 Layer E — Industrial process orchestration (different vertical, not direct competitor)

**Players (2026-05):**

#### Intrinsic Flowstate (Alphabet → Google)

**Status [Verified-2026-05]:** Joined Google formally Feb 2026 (was Alphabet "moonshot" since 2021). Foxconn JV announced Nov 2025 for US factory orchestration.

**What Flowstate does:**
- Drag-and-drop industrial robot app builder
- Hardware-agnostic
- AI-powered (now leveraging Gemini via Google integration)
- Vision model integration (IVM = Intrinsic Vision Model)
- Targeted at manufacturers building industrial robotic applications

**Why this is a different vertical:**
- Industrial factories, not consumer/home
- Pre-programmed sequences with vision-guided adaptation, not natural-language commitments
- B2B enterprise sales motion, not partner-developer ecosystem

**Threat level: LOW (different vertical).**
But — Google ownership means resources to extend. If Google decides "consumer/home robot orchestration" is a market, they have everything they need to enter Layer D.

#### Apex.Grace (Apex.AI)

**Status [Verified-2026-05]:** ISO 26262 ASIL D certified ROS 2 SDK for automotive. Used in ADAS, adaptive cruise control, automatic emergency braking, powertrain, cockpit telematics.

**Why this matters to KaraOS:**
- Proves the market for safety-certified ROS 2 layers
- Their certification path is a model KaraOS could follow eventually (Phase 10+)
- They are NOT direct competitors — different vertical (automotive)

**Threat level: LOW.**

### 3.6 Layer F — Consumer / home humanoid hardware

This is KaraOS's **target customer layer**, NOT a competitor layer. KaraOS is the cognitive middleware that COULD be installed on these robots — but most ship with their own (proprietary) cognitive stack.

**Players (2026-05):**

#### 1X NEO

**Status [Verified-2026-05]:** Consumer humanoid, $20k early access OR $499/month subscription. Pre-orders open. First consumer deliveries 2026.

**What NEO does:**
- Built-in large language model
- **"Chores" feature** — owners can assign, schedule, track tasks via voice or app
- "1X Expert" remote teaching for new tasks
- Tidies rooms, folds laundry, organizes shelves

**Why this matters:**
- **Closest user-facing UX competitor to KaraOS** — "schedule chores, track completion, voice/app interface" is exactly the UX KaraOS plans
- But: PROPRIETARY to 1X hardware. Not extensible. Not licensable. Not partner middleware.
- 1X is vertically integrated (hardware + cognitive layer). They are NOT in the middleware market.

**Threat level: LOW-MEDIUM.**
If 1X decided to license their cognitive stack as middleware, KaraOS's user-facing UX claim weakens. **Probability low** — it's their differentiator. But monitor.

**Strategic positioning:** KaraOS is the **open partner middleware** alternative for robot makers who don't want to license 1X's stack and don't want to build their own from scratch.

#### Figure (Figure 02 + Helix-02 brain)

**Status [Verified-2026-05]:** Industrial first; "Helix-02" announced January 2026; demonstrated 8-hour autonomous package-sorting shifts May 2026.

**What Figure ships:**
- Figure 02 humanoid hardware
- Helix-02 AI brain (proprietary, three-tier System 0/1/2)
- Targeted at industrial labor (factories, warehouses) first; consumer roadmap unclear

**Threat level: LOW for KaraOS (different segment).**
Figure is industrial. KaraOS's primary play is consumer/home + open partner middleware. Could converge eventually, but not in the next 12-18 months.

#### Tesla Optimus

**Status [Verified-2026-05]:** Factory pilot only. No public consumer ship date.

**Threat level: NEGLIGIBLE in the partner-middleware market.**
Tesla is vertically integrated to the extreme; will not partner with external middleware.

#### Boston Dynamics Atlas (production-ready 2026)

**Status [Verified-2026-05]:** CES 2026 announcement: production-ready Atlas + Google DeepMind partnership for Gemini Robotics integration. All 2026 units committed to RMAC + Google DeepMind; additional customers planned for 2027. Hyundai car plants 2028.

**Threat level: LOW for KaraOS.**
Industrial focus. Google partnership locks them into Gemini Robotics for cognition. Not a candidate for KaraOS adoption.

#### Unitree G1

**Status [Verified-2026-05]:** $16k retail. Open URDF. Strong ROS 2 community. Hardware only — no consumer cognitive stack.

**Why this matters: this is KaraOS's reference adapter target.**
- Cheapest humanoid on the market by an order of magnitude
- Open enough for partner integration
- Ships sit/stand/walk primitives in the SDK
- Active in research community

**Threat level: NONE. Strategic ALLY.**
Unitree wants robots adopted. KaraOS makes their robots more useful. Win-win.

#### Apptronik, Sanctuary, Agility Robotics

**Status [Verified-2026-05]:** Each ships proprietary cognitive stacks. Industrial focus mostly.

**Threat level: LOW.**
Possibility: any of them could license KaraOS rather than build orchestration in-house. Sales target.

---

## 4. Per-Competitor Strategic Profiles

This section is the long-form reference. Each profile answers the eight questions from Section 1.2.

### 4.1 ROSClaw — full strategic profile

| Question | Answer |
|---|---|
| **Layer** | C (single-turn LLM-to-robot executive). Could extend into D. |
| **Maturity** | Pre-Alpha v0.1 [Verified-2026-05] |
| **Open or closed?** | Open source (GitHub: `ros-claw/rosclaw`) |
| **Capability overlap with KaraOS** | Affordance manifest (≈ KaraOS capability registry), observation normalizer (≈ KaraOS sensor capabilities), validator (≈ partial KaraOS policy engine), audit log (≈ KaraOS audit), digital twin firewall (KaraOS adopted as Decision 3.14), multi-platform support |
| **Capability gaps vs KaraOS** | No durable commitments, no scheduling, no per-skill verifier registry with abstention, no published SDK with conformance suite, no multi-user contention, no cost ledger, no offline degradation, no multi-step state, no MCP server |
| **Strategic threat level** | **HIGH** — closest architectural shape; moving fast |
| **Strategic dependency** | None directly. Could become an alternative our partners choose. |
| **Last verified** | 2026-05-16 |

**Detailed strategic analysis:**

ROSClaw is the single most important competitor to track. Their architecture overlaps with KaraOS's at the Layer C boundary, and they have the foundation in place to extend upward. Specifically:

1. **They have audit logs.** Adding durable commitments on top of an audit log is conceptually a 2-3 week extension.
2. **They have a model-agnostic agent runtime** (OpenClaw). Adding a scheduler that fires LLM-driven actions on a timer is a known pattern.
3. **They have multi-platform conformance** (TurtleBot3, Go2, G1). Adding a published SDK is a documentation + packaging exercise.

**What KaraOS does that ROSClaw doesn't (and can't trivially add):**

1. **Three-gate safety model** (policy + digital twin + verifier). ROSClaw has gates 1 (partial) and 2 (digital twin firewall). They lack gate 3 (per-skill verifier registry with abstention). Adding gate 3 is non-trivial — it requires the per-skill verifier mapping, the abstention protocol, the calibration discipline.
2. **Conformance suite as a partner contract.** ROSClaw's abstraction is internal; KaraOS's is meant to be partner-certifiable. This is a packaging + documentation difference but a strategic moat.
3. **Two-process architecture.** ROSClaw is single-process. KaraOS's durable + interactive split is a deployment architecture that scales to fleet-of-robots + central durable layer.

**Decision points:**

- **Should KaraOS fork ROSClaw and extend?** Pros: 50% time savings on Layer-C scaffolding. Cons: inherit their pre-alpha bugs; their architectural choices may not match ours. **Recommendation: do not fork. Build alongside, study their patterns, give credit in docs.**
- **Should KaraOS contribute to ROSClaw?** Possibly — small PRs that benefit both projects (e.g., capability ontology v1.0 if we open-source it). Builds goodwill and influences their direction toward complementary positioning.
- **Should KaraOS reach out to ROSClaw maintainers?** Yes, in Phase 7 when the SDK is public. Position as complementary: "ROSClaw is great for single-turn deliberative; KaraOS is the durable layer that can wrap it."

**Monitoring playbook for ROSClaw:**
- Weekly check on `github.com/ros-claw/rosclaw` releases and milestone tags
- Quarterly re-read of their arxiv paper for updates
- Watch for their v0.2.0 announcement — that's the trigger for re-evaluating positioning

### 4.2 ROSA (NASA-JPL) — strategic profile

| Question | Answer |
|---|---|
| **Layer** | C (LLM-to-ROS interaction) |
| **Maturity** | Production (deployed in NASA contexts) [Verified-2026-05] |
| **Open or closed?** | Open source (NASA-JPL) |
| **Capability overlap with KaraOS** | NL→ROS interaction. Custom-agent extensibility. Audit. |
| **Capability gaps vs KaraOS** | No commitments, no scheduling, no policy gate, no verifier registry. Operational/diagnostic focus, not task execution. |
| **Strategic threat level** | LOW |
| **Strategic dependency** | None |
| **Last verified** | 2026-05-16 |

**Strategic note:** ROSA is built on LangChain, designed for operating/inspecting robots in research contexts (spacecraft, rovers). Their use case is "tell me what's wrong with this robot" not "do my chores at home." KaraOS could borrow their LangChain integration patterns, but the products serve different markets.

### 4.3 ros-mcp-server family — collective profile

| Question | Answer |
|---|---|
| **Layer** | C (one-shot LLM↔ROS translation via MCP) |
| **Maturity** | Multiple projects, alpha-to-beta [Verified-2026-05] |
| **Open or closed?** | All open source |
| **Capability overlap with KaraOS** | NL→ROS topic publish/subscribe; tool exposure to MCP clients |
| **Capability gaps vs KaraOS** | No state, scheduling, policy, audit, verification, multi-step orchestration. Single-turn only. |
| **Strategic threat level** | MEDIUM (collectively — the MCP standardization wave is the real threat) |
| **Strategic dependency** | KaraOS adopts MCP server interface (Decision 3.13) to ride this wave |
| **Last verified** | 2026-05-16 |

**Strategic positioning:** these projects are **not competitors** when KaraOS is MCP-native (Decision 3.13). They are potential **integration partners**: a deployment could run ros-mcp-server (for tactical robot interaction) + KaraOS-MCP (for durable commitments). KaraOS does NOT need to replace them.

### 4.4 Google AutoRT — strategic profile

| Question | Answer |
|---|---|
| **Layer** | C/D research |
| **Maturity** | Research framework deployed internally; not productized [Verified-2026-05] |
| **Open or closed?** | Research published; not open code |
| **Capability overlap with KaraOS** | Robot Constitution safety prompts (≈ policy engine but NL-based); fleet orchestration; autonomous goal proposal |
| **Capability gaps vs KaraOS** | No user-driven commitments; no scheduling; no partner SDK. Designed for data collection at scale. |
| **Strategic threat level** | LOW-MEDIUM (could be productized) |
| **Strategic dependency** | None directly |
| **Last verified** | 2026-05-16 |

### 4.5 1X NEO — strategic profile

| Question | Answer |
|---|---|
| **Layer** | F (consumer hardware) + internal Layer D (Chores backend) |
| **Maturity** | Pre-order, ships 2026 [Verified-2026-05] |
| **Open or closed?** | Hardware orderable; cognitive stack proprietary |
| **Capability overlap with KaraOS** | Voice/app task scheduling, task tracking (closest UX competitor) |
| **Capability gaps vs KaraOS** | Proprietary to 1X hardware; no partner middleware; no SDK; closed cognitive stack |
| **Strategic threat level** | MEDIUM (UX overlap on their hardware; not a partner-middleware threat unless they pivot) |
| **Strategic dependency** | None |
| **Last verified** | 2026-05-16 |

**Strategic positioning:** 1X is the **proof-of-concept** that consumer-facing scheduled-task UX is a real product. KaraOS is the **open partner middleware** version of what 1X built internally. The pitch to other humanoid makers: "1X built theirs in-house and locked it to their robot. You can use KaraOS instead and not have that engineering burden."

### 4.6 Physical Intelligence (π) — strategic profile

| Question | Answer |
|---|---|
| **Layer** | A (VLA / motion foundation model) |
| **Maturity** | Production VLA model, 7 robot platforms, 68 tasks [Verified-2026-05] |
| **Open or closed?** | **Open weights** (openpi GitHub) |
| **Capability overlap with KaraOS** | None — different layer |
| **Capability gaps vs KaraOS** | Different layer — they don't do orchestration |
| **Strategic threat level** | LOW (different layer) — actually a strategic enabler |
| **Strategic dependency** | KaraOS could use π models in adapters; π models provide better motion primitives |
| **Last verified** | 2026-05-16 |

**Strategic note:** π's openpi release is a **gift to the ecosystem**. KaraOS's reference adapters could call into π for motion primitives. This is the layer KaraOS depends on, not competes with.

### 4.7 Nvidia GR00T N1 — strategic profile

| Question | Answer |
|---|---|
| **Layer** | A (motion foundation model) + ecosystem |
| **Maturity** | Production, open foundation model [Verified-2026-05] |
| **Open or closed?** | Open foundation model + Nvidia ecosystem (Isaac Lab, Isaac Sim, Omniverse, Newton physics) |
| **Capability overlap with KaraOS** | None directly — different layer. BUT Nvidia could add orchestration above GR00T. |
| **Capability gaps vs KaraOS** | No commitment/policy/verification layer (yet) |
| **Strategic threat level** | MEDIUM-HIGH if Nvidia extends upward |
| **Strategic dependency** | KaraOS could use GR00T as the motion primitive layer |
| **Last verified** | 2026-05-16 |

**Strategic threat analysis:** Nvidia has the engineering resources, partner relationships (ABB, Universal Robots, Skild, Disney, Google DeepMind), and ecosystem (Isaac Lab, Isaac Sim) to ship an "Isaac Orchestrate" layer above GR00T. If they do, KaraOS faces a serious challenge — Nvidia's brand + bundled stack is a powerful competitor.

**Counter-strategy:** KaraOS is the **open ROS-2-native alternative** to Nvidia's vertical-lock pattern. Robot makers who don't want CUDA/Omniverse lock-in choose KaraOS. This positioning only works if KaraOS is genuinely platform-agnostic (Decision 3.1 + 3.2 + 3.3 must hold structurally).

### 4.8 Skild AI — strategic profile

| Question | Answer |
|---|---|
| **Layer** | A (foundation model) |
| **Maturity** | Production deployments [Verified-2026-05] |
| **Open or closed?** | Closed |
| **Capability overlap with KaraOS** | None — different layer |
| **Capability gaps vs KaraOS** | Different layer |
| **Strategic threat level** | LOW (different layer) |
| **Strategic dependency** | Skild model could be the motion layer in a partner's adapter |
| **Last verified** | 2026-05-16 |

**Strategic note:** $1.4B raised at $14B valuation (Jan 2026) means Skild has resources to extend in any direction. Monitor for orchestration-layer announcements.

### 4.9 Figure Helix-02 — strategic profile

| Question | Answer |
|---|---|
| **Layer** | A (motion brain) + F (hardware) |
| **Maturity** | Production in industrial deployments, 8-hour autonomous shifts demonstrated 2026-05 [Verified-2026-05] |
| **Open or closed?** | Closed, Figure-only |
| **Capability overlap with KaraOS** | None directly (vertically integrated) |
| **Capability gaps vs KaraOS** | Not partner middleware |
| **Strategic threat level** | LOW (vertical lock-in by design) |
| **Last verified** | 2026-05-16 |

### 4.10 Google Gemini Robotics — strategic profile

| Question | Answer |
|---|---|
| **Layer** | A (foundation model) — powering Atlas via Boston Dynamics partnership |
| **Maturity** | Production rollout 2026; partner deployment 2027+; Hyundai 2028 [Verified-2026-05] |
| **Open or closed?** | Closed (Google) |
| **Capability overlap with KaraOS** | None directly |
| **Capability gaps vs KaraOS** | Different layer |
| **Strategic threat level** | MEDIUM (Google could extend to Layer D) |
| **Last verified** | 2026-05-16 |

### 4.11 Intrinsic Flowstate — strategic profile

| Question | Answer |
|---|---|
| **Layer** | E (industrial orchestration) |
| **Maturity** | Production, Foxconn JV active [Verified-2026-05] |
| **Open or closed?** | Commercial product |
| **Capability overlap with KaraOS** | Drag-and-drop process definition; vision integration; hardware-agnostic claim |
| **Capability gaps vs KaraOS** | Industrial only; not natural-language commitments; not consumer/home |
| **Strategic threat level** | LOW (different vertical) — but Google could redirect |
| **Last verified** | 2026-05-16 |

### 4.12 Apex.AI (Apex.Grace) — strategic profile

| Question | Answer |
|---|---|
| **Layer** | B (real-time/safety-certified ROS 2 layer) |
| **Maturity** | Production, ISO 26262 ASIL D certified [Verified-2026-05] |
| **Open or closed?** | Commercial SDK |
| **Capability overlap with KaraOS** | None — different layer (real-time control, not orchestration) |
| **Capability gaps vs KaraOS** | Different layer |
| **Strategic threat level** | NONE |
| **Strategic dependency** | Possible long-term: KaraOS could run on top of Apex.Grace for safety-certified deployments |
| **Last verified** | 2026-05-16 |

---

## 5. The Defensible Gap — What Only KaraOS Owns

Restated from `future-execution.md` Section 2.4.2, expanded with reasoning:

### Gap 5.1 — Durable scheduled commitments bound to robot capability registry

**What it is:** user says "feed the dog at 6pm tomorrow"; commitment persists across restarts; fires at due time; passes through capability matching; declines if no capable adapter is present.

**Who else does this:**
- LangGraph checkpointing — persistence primitive, NOT bound to robots
- Cloudflare Durable Objects — same — generic durable agents
- Temporal, Inngest — same — generic workflow engines
- 1X NEO Chores — does this, but proprietary to 1X hardware

**Why no one else combines persistence + robot capability:** the persistence side and the robotics side are in different developer communities. Generic agent frameworks don't know about ROS 2 capabilities; robotics frameworks (ROSClaw, ROSA, MCP servers) don't have durable persistence.

**Defensibility:** medium — anyone could combine these in 2-4 weeks if they decided to. KaraOS's moat is being there first with the discipline of "this is the canonical way."

### Gap 5.2 — Per-skill verifier registry with sim-ground-truth + abstention protocol

**What it is:** every skill has a registered verifier; verifier reads cheapest reliable sensor for that skill's world-state question; verifier can abstain when uncertain; abstention escalates to human.

**Who else does this:**
- Academic: "closed-loop state feedback for grounded LLM planning" — research, not runtime
- Industrial: per-vendor pre-canned verification (e.g., barcode scan = success) but not as a registry pattern
- No partner middleware ships this

**Why no one else does this:** verifier registry is conceptually a quality discipline, not a feature. Most projects ship "if adapter says success, mark complete." KaraOS's "no fake completion" claim hinges on this discipline.

**Defensibility:** HIGH — this is a process/discipline moat, not a feature. Hard to copy quickly.

### Gap 5.3 — Capability-typed adapter SDK with published conformance suite

**What it is:** `karaos-adapter-sdk` as a separately-published package; partners receive SDK + conformance suite + reference adapter; `karaos-conformance --adapter X` outputs pass/fail.

**Who else does this:**
- ROSClaw — has the abstraction internally; **does not publish a partner SDK with conformance contract**
- Generic robot middleware — none

**Why no one else does this:** publishing a conformance suite is a strategic commitment. It says "we are stable enough to be a contract." Most projects aren't there yet. KaraOS commits to this in Phase 7.

**Defensibility:** HIGH — "passes KaraOS conformance v1.0" becomes an industry checkbox. Network effects: more adapters → more value → more adapters.

### Gap 5.4 — Three-gate safety model (policy + digital twin + verifier)

**What it is:** every skill execution passes through three gates: policy rules (deterministic, rule-engine), digital twin physics validation (MuJoCo), verifier outcome check (per-skill registry).

**Who else does this:**
- ROSClaw — has gate 1 (partial: velocity bounds) + gate 2 (digital twin firewall). Missing gate 3.
- AutoRT — has gate 1 (constitution prompts). No digital twin. No outcome verifier.
- Generic agent frameworks — none

**Why no one else does this:** combining three gates requires three different engineering disciplines (rule engines, physics simulation, sensor-based verification). Each is non-trivial.

**Defensibility:** HIGH — three-gate is a structural claim that takes time to assemble and is hard to handwave.

### Gap 5.5 — Multi-user commitment contention with audit-trail-driven authority

**What it is:** two household members give conflicting commitments; system detects conflict; resolution rule applied (newer wins same-user, ask for resolution cross-user); per-user authority levels configurable.

**Who else does this:**
- Generic agent frameworks — usually single-user
- 1X NEO — single-user assumed in current product
- No robotics middleware ships this

**Why no one else does this:** multi-user is rare in robotics; most robots have one operator. KaraOS targets HOUSEHOLDS (multiple users) which makes this load-bearing.

**Defensibility:** MEDIUM — feature gap. Could be copied in a few weeks.

### Gap 5.6 — Cost-aware degradation + offline cognitive fallback

**What it is:** every LLM call tracked in cost ledger; per-user daily cap; degrade to local-only when cap hit; degraded mode when local LLM unavailable; durable layer keeps working offline.

**Who else does this:**
- Generic agent frameworks — some have cost tracking (LangSmith, Helicone)
- Robotics middleware — none ship this explicitly
- Existing dog-ai cloud_failed state machine — KaraOS extends this pattern to embodied

**Why no one else does this:** unit economics aren't on most robotics projects' radar yet. Will become important when consumer humanoids hit 100k+ household scale.

**Defensibility:** MEDIUM — anyone can add cost tracking. Discipline matters more than the feature.

### Gap 5.7 — Verifier-vs-adapter disagreement protocol

**What it is:** adapter reports success, verifier disagrees → task = `failed_verification`, NOT `completed`. User notified. Retry policy applied. Audit captures both signals.

**Who else does this:**
- Nobody ships this explicitly as a named protocol.

**Defensibility:** HIGH — this is the structural mechanism that makes "no fake completion" true. Hard to add as an afterthought.

---

## 6. Strategic Risk Register

For each risk: severity, monitoring signal, mitigation, current status.

### Risk R1 — ROSClaw ships v0.2 with commitment storage

| Field | Value |
|---|---|
| Severity | **HIGH** |
| Probability | Medium (50% within 6 months) |
| Time horizon | 3-9 months |
| Monitoring signal | GitHub releases tag at `ros-claw/rosclaw`; arxiv paper version bumps; ROSClaw README roadmap section |
| Trigger | Any mention of "scheduling", "commitment", "future execution", or "persistent state" in their roadmap or release notes |
| Mitigation | Ship KaraOS Phase 1 within 8-10 weeks; announce publicly to claim "durable cognitive middleware" framing first; differentiate on conformance suite + three-gate model |
| Current status | Open. Not triggered yet (as of 2026-05-16) |

### Risk R2 — Nvidia ships Isaac Orchestrate layer above GR00T

| Field | Value |
|---|---|
| Severity | **HIGH** |
| Probability | Medium (40% within 12 months) |
| Time horizon | 6-18 months |
| Monitoring signal | Nvidia GTC announcements; Isaac Lab roadmap; GR00T blueprint additions; partnership announcements with humanoid makers |
| Trigger | Any Nvidia announcement of "orchestration", "task management", or "scheduling" features above GR00T |
| Mitigation | Position as open ROS-2-native alternative; avoid CUDA/Omniverse dependencies; emphasize multi-vendor adapter support |
| Current status | Open. GR00T blueprint exists but is data-generation-focused, not orchestration. |

### Risk R3 — Google productizes AutoRT-style orchestration via Gemini Robotics

| Field | Value |
|---|---|
| Severity | MEDIUM |
| Probability | Low-medium (25% within 12 months) |
| Time horizon | 6-18 months |
| Monitoring signal | Google DeepMind blog; Gemini Robotics announcements; Boston Dynamics + Google joint announcements |
| Trigger | Any productization signal beyond research papers |
| Mitigation | Open-source positioning; partner with humanoid makers Google doesn't directly serve; emphasize home/consumer (Google's focus is industrial via Atlas) |
| Current status | Open. AutoRT remains research. Google + BD focus is industrial. |

### Risk R4 — 1X opens NEO cognitive stack as licensable middleware

| Field | Value |
|---|---|
| Severity | MEDIUM |
| Probability | Low (15% within 12 months) |
| Time horizon | 12-24 months |
| Monitoring signal | 1X press releases; SDK announcements; partner announcements |
| Trigger | Any "platform" / "SDK" / "developer" framing from 1X |
| Mitigation | KaraOS is open by design; 1X is closed by their business model; positioning is robustly different. Convert robot makers who don't want vertical lock-in |
| Current status | Open. 1X remains vertically integrated. |

### Risk R5 — MCP-for-robots standardization wave fragments before KaraOS rides it

| Field | Value |
|---|---|
| Severity | MEDIUM |
| Probability | Medium (40% within 12 months) |
| Time horizon | 6-12 months |
| Monitoring signal | New MCP-server-for-ROS GitHub repos; Anthropic MCP spec changes; competing protocol announcements |
| Trigger | Anthropic deprecates MCP, OR a competing protocol gets meaningful adoption |
| Mitigation | KaraOS's MCP server is one channel, not the only one. gRPC IPC remains the primary path (Decision 3.11). If MCP fragments, KaraOS survives via gRPC. |
| Current status | Open. MCP momentum is strong as of 2026-05. |

### Risk R6 — Boston Dynamics + Google ships consumer cognitive stack

| Field | Value |
|---|---|
| Severity | LOW |
| Probability | Low (10% within 18 months) |
| Time horizon | 18+ months |
| Monitoring signal | CES 2027; Boston Dynamics consumer announcements |
| Trigger | Any "Atlas at home" / "consumer Atlas" framing |
| Mitigation | Stay consumer/multi-robot-maker focused; BD focus is industrial |
| Current status | Open. BD industrial-focused. |

### Risk R7 — Apex.AI extends from automotive to home robotics safety certification

| Field | Value |
|---|---|
| Severity | LOW |
| Probability | Very low (5%) |
| Time horizon | 24+ months |
| Mitigation | KaraOS aligns with ISO standards from spec time (Section 26); Apex would be an enabler if anything, not a competitor |
| Current status | Open. Apex remains automotive. |

---

## 7. Monitoring Playbook — How to Refresh This Doc

### 7.1 Weekly cadence (architect, 15 minutes)

- Check GitHub releases for: `ros-claw/rosclaw`, `nasa-jpl/rosa`, `robotmcp/ros-mcp-server`, `Physical-Intelligence/openpi`
- Skim Robot Report headlines, IEEE Spectrum robotics tag
- Note any anomalies in a running scratch file; full update at quarterly refresh

### 7.2 Monthly cadence (architect, 60 minutes)

- Read latest Boston Dynamics, Figure, 1X, Tesla Optimus, Apptronik, Agility press
- Check Nvidia developer blog for GR00T / Isaac updates
- Check Google DeepMind blog for Gemini Robotics updates
- Update "Last verified" dates on any reconfirmed claims

### 7.3 Quarterly cadence (architect + outside review if available, 4 hours)

- Full re-read of this doc
- For each competitor profile: re-verify the 8 questions
- Update funding figures, deployment counts, latest version numbers
- Re-rank risk severities based on new evidence
- Add any new entrants
- Mark stale claims explicitly with `[Stale-since-DATE]`
- Update Section 11 changelog

### 7.4 Event-triggered (any time)

If any of these happen, do a targeted update within 7 days:

- Major funding announcement by any Layer-A or Layer-D player
- ROSClaw v0.2 or beyond release
- Nvidia GR00T N2 or successor announcement
- 1X NEO platform/SDK announcement
- Boston Dynamics + Google productization announcement
- New entrant publishing arxiv preprint in robot cognitive middleware space

---

## 8. KaraOS Mandatory Differentiators

These MUST be demonstrable at Phase 7 close. They are the substantive claims that justify KaraOS's positioning. If ANY is not true at Phase 7, positioning must be re-examined honestly before any partner pitch.

| # | Differentiator | Demonstrable how | Verified by |
|---|---|---|---|
| 1 | Durable scheduled commitments | Demo 8: kill process, restart, task fires at original due time | Phase 1 acceptance |
| 2 | Per-skill verifier registry with abstention | Demo 9 + Section 12.5 tests | Phase 5 acceptance |
| 3 | Adapter SDK + conformance suite published | `pip install karaos-adapter-sdk`; `karaos-conformance --adapter X` | Phase 7 acceptance |
| 4 | Reference Unitree G1 adapter in Gazebo demonstrable | Demo 2 + 7; recorded video | Phase 4 acceptance |
| 5 | 3+ mock adapters demonstrating capability-based skill rejection | Demo 7 | Phase 3 acceptance |
| 6 | KaraOS exposed as MCP server (Decision 3.13) | Claude Desktop drives KaraOS via MCP tools | Phase 4 acceptance |
| 7 | Digital twin pre-execution validator (Decision 3.14) | Demo of motion blocked before publishing to adapter | Phase 4.5 acceptance |

**If any differentiator fails to land:**

- **#1 fails:** ROSClaw or generic agent frameworks own the positioning. KaraOS positioning collapses to "another LLM-to-ROS bridge." Re-evaluate the entire project.
- **#2 fails:** "No fake completion" claim becomes marketing. Verifier discipline is what makes the safety story credible. Re-evaluate Phase 5 scope.
- **#3 fails:** Partner story collapses. Conformance suite is the moat. Without it, every partner integration is a snowflake.
- **#4 fails:** No reference implementation. Partners have no template. Re-evaluate Phase 4 scope.
- **#5 fails:** "Multi-body" claim becomes vaporware. Reduce claims to single-robot positioning.
- **#6 fails:** KaraOS fights MCP wave instead of riding it. Re-evaluate Decision 3.13.
- **#7 fails:** ROSClaw has a safety gate KaraOS doesn't. Reduce safety claims accordingly.

---

## 9. Recent Timeline (Important Events 2025-2026)

Curated list of events that shaped (or could shape) KaraOS's competitive landscape. Add new events as they happen.

| Date | Event | KaraOS impact |
|---|---|---|
| 2024-2025 | Anthropic introduces Model Context Protocol (MCP) | Triggered the MCP-for-robots wave; KaraOS Decision 3.13 |
| 2025 | Physical Intelligence raises $400M, releases π-0 then opens weights (openpi) | Enabled open-source motion layer for KaraOS adapters |
| 2025 (March) | Nvidia announces Isaac GR00T N1, opens foundation model | Strengthens open motion layer; raises threat of Nvidia extending into Layer D |
| 2025 (Oct) | 1X launches NEO pre-orders ($20k / $499/mo subscription) | First consumer humanoid with "Chores" UX — proves KaraOS market |
| 2025 (Nov) | Intrinsic + Foxconn JV announced for US factory orchestration | Establishes industrial-orchestration market; Layer E precedent |
| 2026 (Jan) | Boston Dynamics + Google DeepMind partnership announced at CES 2026; Atlas production-ready | Industrial Layer A+F competitor; Gemini Robotics threat to monitor |
| 2026 (Jan) | Skild AI raises $1.4B at $14B valuation | Massive Layer A funding; threat of vertical extension |
| 2026 (Jan) | 1X NEO production units ship to consumers | UX competitor goes live; monitor for SDK announcements |
| 2026 (Jan) | Anthropic Claude constitution v2 published | Constitutional AI evolution; relevant to KaraOS policy engine framing |
| 2026 (Feb) | Intrinsic formally joins Google | Industrial orchestration absorbed into Google; resources to extend |
| 2026 (Feb) | 1X NEO Fortune coverage: $20k humanoid still needs help | UX competitor's gap exposed: human teaching still required |
| 2026 (March) | Skild AI partnership with ABB Robotics, Universal Robots, Nvidia | Layer A consolidation; Skild + Nvidia alliance |
| 2026 (May) | Figure Helix-02 demonstrates 8-hour autonomous package-sorting shifts | Proves long-horizon autonomous capability at industrial level |
| 2026 (May) | ROSClaw arxiv preprint published; Pre-Alpha v0.1 on GitHub | **Direct architectural competitor identified**; triggered this doc |
| 2026 (May) | KaraOS `future-execution.md` v2 with competitive positioning | Strategic response: lock differentiators, ship Phase 1 fast |

---

## 10. Open Research Questions for Next Refresh

Questions this doc cannot answer yet. Researcher should investigate before next quarterly refresh.

### Q10.1 — Has anyone published a robotic-task workflow durability standard?

LangGraph, Temporal, AWS Step Functions all have durable workflow patterns. Is there a robotics-specific equivalent emerging? If yes, KaraOS should align.

### Q10.2 — What is the actual adoption curve of ROSClaw?

Count: stars, forks, contributors, downstream dependents. Trajectory matters more than current state.

### Q10.3 — What does the 1X NEO "1X Expert" remote teaching actually do?

Is this teleop? RLHF? Demonstration data collection? Understanding their teaching loop tells us how mature their cognitive stack actually is.

### Q10.4 — Is Apex.AI working on a non-automotive vertical?

Their certification expertise transferable to home robotics would be a major shift in the Layer-B competitive picture.

### Q10.5 — What's the cost-per-commitment unit economics across competitors?

KaraOS plans to use local LLMs by default. Are competitors doing the same? Cost-per-task is going to be a competitive axis once the market matures.

### Q10.6 — Are there any non-US / non-Chinese players in the cognitive middleware space?

Europe (Bosch?), Japan (Toyota Research Institute? Honda?), Israel — easy to overlook. Worth searching.

### Q10.7 — How does Nvidia's "physical AI" framing extend to home consumer?

Nvidia consistently frames their robotics work as enterprise / industrial. If they pivot to home consumer (à la "robot for every home" Jensen quotes), KaraOS landscape changes.

### Q10.8 — Is there evidence of any LLM-foundation company (OpenAI, Anthropic, Google) building their own robot adapter SDK?

Anthropic's MCP is universal-tool, not robot-specific. Could they (or OpenAI) ship a robot-specific MCP variant?

### Q10.9 — What's the open-source momentum in robotic foundation models?

OpenVLA, Octo, openpi are open. Skild + Figure are closed. Does open-source momentum matter for KaraOS's positioning (we're open-friendly), or is closed-source winning?

### Q10.10 — Is there a "robot constitution" standard emerging?

AutoRT introduced the concept. Google has it. Anthropic has Constitutional AI. Is there an opportunity for KaraOS to propose / contribute to a "robot constitution" standard that wraps policy + safety norms?

---

## 11. Changelog

Track every refresh, every claim adjustment, every position update.

### 2026-05-16 — Initial draft

- Created document from `future-execution.md` Section 2.4
- Full six-layer landscape mapped
- 12 competitors profiled at strategic-level detail
- 7 strategic risks registered with monitoring playbooks
- 10 open research questions for next refresh
- Differentiators list (7 mandatory items) locked

### (future entries go here, with date and changes)

---

## 12. Sources (rolling)

Primary sources cited in this document (verified as of 2026-05-16 unless noted otherwise):

### ROSClaw
- arxiv: `https://arxiv.org/html/2603.26997`
- GitHub: `https://github.com/ros-claw/rosclaw`
- Labellerr analysis: `https://www.labellerr.com/blog/how-rosclaw-connects-ai-models-to-robots/`

### ROSA (NASA-JPL)
- GitHub: `https://github.com/nasa-jpl/rosa`
- arxiv: `https://arxiv.org/html/2410.06472v1`
- NASA Software Catalog: `https://software.nasa.gov/software/NPO-53120-1`

### Nvidia GR00T N1
- Announcement: `https://nvidianews.nvidia.com/news/nvidia-isaac-gr00t-n1-open-humanoid-robot-foundation-model-simulation-frameworks`
- arxiv: `https://arxiv.org/abs/2503.14734`
- Research page: `https://research.nvidia.com/publication/2025-03_nvidia-isaac-gr00t-n1-open-foundation-model-humanoid-robots`

### Physical Intelligence (π)
- Company: `https://www.pi.website/`
- π-0 blog: `https://www.pi.website/blog/pi0`
- Robot Report: `https://www.therobotreport.com/physical-intelligence-open-sources-pi0-robotics-foundation-model/`
- arxiv: `https://arxiv.org/html/2410.24164v1`
- GitHub: `https://github.com/Physical-Intelligence/openpi`

### Skild AI
- Company: `https://www.skild.ai/`
- Funding: `https://www.therobotreport.com/skild-ai-raises-1-4b-building-omni-bodied-robot-skild-brain/`
- Nvidia case study: `https://www.nvidia.com/en-gb/case-studies/skild-ai/`

### Figure Helix
- Helix: `https://www.figure.ai/helix`
- Helix-02: `https://www.figure.ai/news/helix-02`
- 8-hour shift demo: `https://www.techtimes.com/articles/316632/20260514/figure-ais-helix-02-robots-complete-full-8-hour-autonomous-shifts-humanoid-race-intensifies.htm`

### Google Gemini Robotics / Boston Dynamics
- Gemini Robotics: `https://deepmind.google/models/gemini-robotics/`
- BD + Google partnership: `https://bostondynamics.com/blog/boston-dynamics-google-deepmind-form-new-ai-partnership/`
- TechCrunch: `https://techcrunch.com/2026/01/05/boston-dynamicss-next-gen-humanoid-robot-will-have-google-deepmind-dna/`

### Google AutoRT
- DeepMind publication: `https://deepmind.google/research/publications/48151/`
- arxiv: `https://arxiv.org/html/2401.12963v1`
- Robot Constitution coverage: `https://technology.inquirer.net/131070/robot-constitution-google`

### 1X NEO
- Product: `https://www.1x.tech/discover/neo-home-robot`
- Launch: `https://www.businesswire.com/news/home/20251027434628/en/1X-Launches-NEO-The-Robot-Redefining-Life-at-Home`
- Fortune $20k coverage: `https://fortune.com/2026/02/26/humanoid-robot-that-will-do-chores-for-you-robotics-company-1x/`

### Intrinsic
- Joining Google: `https://www.cnbc.com/2026/02/25/alphabet-robotics-software-intrinsic-google-ai.html`
- TechCrunch: `https://techcrunch.com/2026/02/25/alphabet-owned-robotics-software-company-intrinsic-joins-google/`
- Integration details: `https://theaiinsider.tech/2026/02/26/alphabets-intrinsic-joins-google-to-make-industrial-robotics-platform-more-accessible-to-manufacturers/`

### Apex.AI
- Apex.Grace: `https://www.apex.ai/apexgrace`
- ISO 26262 certification: `https://openadx.eclipse.org/resources/Apex.AI_How-Apex.AI-Certified-ROS-2-According-to-ISO-26262-ASIL-D_(AWF-TSC-April-2021).pdf`

### MCP servers (ROS family)
- ros-mcp-server: `https://github.com/robotmcp/ros-mcp-server`
- ros2-mcp-server: `https://github.com/kakimochi/ros2-mcp-server`
- moveit-mcp-server: `https://github.com/gtoff/moveit-mcp-server`
- rosbridge-mcp-server: `https://github.com/TakanariShimbo/rosbridge-mcp-server`
- Auromix ROS-LLM: `https://github.com/Auromix/ROS-LLM`

### Anthropic Constitutional AI
- Research: `https://www.anthropic.com/research/constitutional-ai-harmlessness-from-ai-feedback`
- Constitutional Classifiers: `https://www.anthropic.com/research/constitutional-classifiers`

### Academic references
- SayCan: `https://say-can.github.io/`
- VoxPoser: `https://voxposer.github.io/`
- GroundedPlanBench: `https://www.microsoft.com/en-us/research/blog/groundedplanbench-spatially-grounded-long-horizon-task-planning-for-robot-manipulation/`
- Awesome LLM Robotics: `https://github.com/GT-RIPL/Awesome-LLM-Robotics`

---

**End of competitive positioning document.**

*Next refresh due: 2026-08-16. If past due, the architect should treat all claims as potentially stale and re-verify before using.*
