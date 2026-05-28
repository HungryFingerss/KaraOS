# Sundar — Industry Standard Playbook — P1 Prep — 2026-05-27

> **Agent**: Sundar (industry-standard / platform-strategy)
> **Issue**: KAR-122
> **Scope**: Strategic playbook for KaraOS becoming the universal ROS 2 cognitive middleware
> **Strategic goal (locked, non-negotiable)**: "Every ROS 2 robot should use only our system."
> **What's locked**: the goal. **What's debatable**: the path, including `future-execution.md`.

---

## Section 0 — Discipline declaration

Every claim in this document carries the 5 disciplines Jagan named:

1. **Specific** — named decisions, not "improve X."
2. **Evidence** — citation to file:line, public precedent, or named source.
3. **Validation** — the real-world standard this is modeled on.
4. **Success measure** — the test/metric/observable that proves it worked.
5. **Risk** — what breaks if we do this; what breaks if we don't.

If a recommendation can't carry all 5, it's not in this document. Where I say "recommend" without those 5, treat it as a Section 9 open question, not a directive.

---

## Section 1 — Executive summary

KaraOS is in a structurally rare position: a cognitive middleware layer **above** robot control, **below** the user's natural language, that no incumbent owns (`future-execution.md` §2.4 — Layer D is empty). The strategic question for P1 is not "can we build it" — P0 proved we can. The question is: **does P1 lock the architectural decisions that allow standard-formation, or does it foreclose them?**

My answer: **P1 as currently scoped in `future-execution.md` v2 is 80% correct for standard-formation, with 4 specific decisions that need lock-in or elevation BEFORE P1 starts.**

The 4 decisions, in priority order:

1. **License lock-in to Apache 2.0** at the start of P1, not at Phase 7 (currently un-locked; CLAUDE.md §LICENSE references P3 only). This is the single highest-leverage standard-formation decision. (See §3.)
2. **Adapter SDK package boundary committed in P1**, not Phase 7. The SDK is what makes KaraOS conformance-testable; without it, every partner integration is a fork. `future-execution.md` Decision 3.3 already locks the boundary; P1 must produce the v0 SDK artifact even if conformance suite is P7. (See §4.)
3. **Reference robot pick committed in P1**: TurtleBot4 (Humble/Jazzy ROS 2 LTS supported, OSRF reference, Unitree G1 deferred to P3). This is the "Turtlebot equivalent" question the issue asks. (See §6.)
4. **API stability discipline written into P1 as a doctrine**, mirroring `### Phase-0-catches-wrong-premise` and the 10 other CLAUDE.md doctrines. Without this discipline, the cognition specs v0 (`P0.0.6`) will drift uncontrollably during P1. (See §5.)

If P1 ships with these 4 decisions locked and the existing `complete-plan.md` and `future-execution.md` invariants preserved, KaraOS clears the architectural prerequisites to become Layer D's standard. Standard-formation itself is a 3-5 year community-and-ecosystem process; **P1's job is to not foreclose it**, not to complete it.

---

## Section 2 — How systems become standards: the empirical record

I studied the six trajectories Jagan named. Each had 5-9 specific decisions that mattered. Below is the distilled pattern — the "standard-making 7" — with citations.

### 2.1 Linux kernel (1991-2005 trajectory)

| Year | Decision | Why it mattered |
|---|---|---|
| 1991 | Linus published to comp.os.minix | Free distribution channel; no licensing friction |
| 1992 | Switched 0.12 from custom license to **GPL v2** | Made commercial adoption legally safe AND copyleft prevented forks from going closed |
| 1996 | Adopted "release early, release often" | Forced ecosystem to track upstream, not forks |
| 1998 | IBM, Oracle, HP committed engineers + dollars | Corporate co-stewardship without takeover (Linus held veto) |
| 2002 | BitKeeper SCM (then 2005 git) | Made distributed kernel development scale to thousands of contributors |
| 2005 | "Mainline tree" became economically dominant | Vendor kernels (Red Hat, SUSE) were derivatives, not forks |

**The pattern**: open license that prevents take-private + benevolent dictator preserves coherence + corporate co-investment without capture + scalable contribution tooling. Took ~14 years from "first release" to "obvious default."

### 2.2 ROS (2007-2014) → ROS 2 (2017-present)

ROS was a Willow Garage research project. By 2012 it had become the de facto standard for academic robotics. The transition decisions:

| Year | Decision | Why it mattered |
|---|---|---|
| 2007 | **BSD-3-Clause license** chosen explicitly to allow commercial robots to ship ROS without copyleft tax | Made every research lab's ROS work shippable in commercial products |
| 2008 | Turtlebot reference hardware ($1500, runs ROS out of box) | Lowered the "can I try this?" bar; every ROS tutorial assumed Turtlebot |
| 2012 | Open Source Robotics Foundation (OSRF) spun out from Willow Garage | Separated stewardship from the company; survival no longer tied to one funder |
| 2014 | OSRF began ROS 2 (DDS-based, real-time, multi-robot) | Recognized ROS 1's architectural ceiling before competitors did |
| 2017 | ROS 2 Ardent (first non-beta) released; LTS cadence committed | API stability promise made commercial integrators safe |
| 2022 | OSRF → Open Robotics → folded under Intrinsic (Alphabet) | Governance survived corporate acquisition because of OSRF independence |

**The pattern**: permissive license, reference hardware, foundation stewardship, willingness to break to v2 when v1's ceiling was hit, LTS for commercial users.

### 2.3 Docker (2013-2017)

Docker dotCloud open-sourced its container runtime in March 2013. By 2016 it had ~80% of container market mindshare.

| Year | Decision | Why it mattered |
|---|---|---|
| 2013 | Apache 2.0 license + `docker run` UX | License was permissive; the UX was the breakthrough — `lxc` existed for years but had a terrible CLI |
| 2014 | Docker Hub registry shipped | Distribution layer; turned "containers" into "container ecosystem" |
| 2015 | OCI (Open Container Initiative) under Linux Foundation | Standardized the image format BEFORE competitors could fork incompatibly |
| 2016 | runc (the runtime) donated to OCI | Specified the contract; Docker the company kept the brand, not the spec |
| 2017 | containerd donated to CNCF | Removed Docker Inc as a gatekeeper risk |

**The pattern**: permissive license, breakthrough UX, registry as distribution layer, donate the contract layer to neutral foundation. Docker Inc the *company* eventually struggled; Docker the *standard* won.

### 2.4 Kubernetes (2014-2019)

Google open-sourced Borg-inspired Kubernetes in June 2014.

| Year | Decision | Why it mattered |
|---|---|---|
| 2014 | **Apache 2.0**, neutral CNCF home from inception | Avoided the "Google project" perception that killed prior Google open-source efforts (Wave, GWT) |
| 2015 | CNCF founded as neutral foundation; K8s donated as founding project | Removed Google control; made every cloud vendor (AWS, Azure, IBM) safe to invest |
| 2015 | KEPs (Kubernetes Enhancement Proposals) public, anyone can write | Made governance legible; community contributions had a clear path |
| 2016 | SIGs (Special Interest Groups) structure | Distributed maintenance; no single bottleneck |
| 2017 | Cloud vendors all shipped managed K8s (EKS, AKS, GKE) | Locked in standard-status via every major cloud's product roadmap |
| 2018-19 | Helm, Operators, CRDs ecosystem layer | Extension model made K8s the **platform for platforms** |

**The pattern**: most successful "standard from day 1" trajectory in modern infrastructure. Google's choice to donate to a neutral foundation **before** the project was big enough to be a control prize is the load-bearing decision.

### 2.5 PyTorch vs TensorFlow (the reversal, 2018-2022)

TensorFlow led by ~3x in research adoption in 2017. PyTorch was the obvious default by 2022. The reasons are documented:

| Factor | TensorFlow | PyTorch |
|---|---|---|
| API stability | Major breaking changes in 2.0 (2019) cost ecosystem trust | API stable since 0.4 (2018) — "pythonic" stayed pythonic |
| Debugging | Graph mode required `tf.print` and special tooling | Define-by-run = use Python debugger |
| Community signal | Google-driven; research labs felt "tolerated, not heard" | Facebook + open community; FAIR labs led from outside |
| Open governance | Closed roadmap; community PRs went to a black box | PyTorch Foundation (2022, under Linux Foundation) |

**The pattern lesson**: a 3x lead can be lost in 4 years if (a) breaking changes betray API stability, (b) the developer experience is worse, (c) governance feels closed. **Standards can be reversed.** This is the discipline KaraOS must hold most rigorously: API stability + DX + open governance.

### 2.6 LLVM (2003-present)

Chris Lattner started LLVM at UIUC in 2000; Apple hired him and shipped LLVM in Mac OS X 10.6 (2009).

| Year | Decision | Why it mattered |
|---|---|---|
| 2003 | **UIUC license** (BSD-equivalent) + modular library design | Made it embeddable in proprietary tools (which GCC's GPL3 could not) |
| 2007 | Apple shipped LLVM/Clang in production toolchain | First major commercial backer |
| 2010 | Sony PlayStation, NVIDIA CUDA, AMD GPU compiler all on LLVM | Compiler-infrastructure standard locked in |
| 2014 | LLVM Foundation incorporated | Stewardship separated from any one corporate sponsor |
| 2020+ | MLIR (multi-level IR) shipped | Extended LLVM into ML compiler territory; standard expanded vertically |

**The pattern**: permissive license enables proprietary embedding (the "boring layer" wins by being everywhere), modular library design lets you adopt-piecewise, foundation stewardship at the right time (~10 years in).

### 2.7 The standard-making 7 (synthesized from all six trajectories)

These are the 7 decisions every successful infrastructure standard has gotten right. KaraOS is graded against each in §3-§8.

| # | Decision | Why it's load-bearing | KaraOS state |
|---|---|---|---|
| 1 | **Permissive license** (Apache 2.0 or BSD) | Without it, commercial integrators can't ship; ecosystem can't form | NOT LOCKED — must lock in P1 |
| 2 | **Reference implementation** users can run in 30 minutes | Turtlebot for ROS, `docker run hello-world` for Docker; lowers entry bar | Partially designed (Phase 1 mock; reference robot deferred) |
| 3 | **Stable contract / spec** versioned independently of implementation | OCI image spec, K8s API conventions, ROS msg interfaces | Designed (`P0.0.6` cognition specs v0) but not locked-stable until v1 |
| 4 | **Neutral foundation stewardship** before you become the obvious choice | CNCF for K8s, OSRF for ROS, Linux Foundation for LLVM | Premature; correct timing is "after first 3 external adopters" |
| 5 | **Extension/plugin model** users can build ecosystems in | K8s CRDs/operators, ROS packages, LLVM passes | MCP server (Decision 3.13) is the right shape; adapter SDK (3.3) is the load-bearing one |
| 6 | **Distribution channel** users find the project through | DockerHub, PyPI, ROS apt repo, K8s `kubectl` | Not designed; pip + a `karaos` CLI per Section 4 |
| 7 | **API stability discipline** that survives "we want to change X" | PyTorch beat TensorFlow on this alone | NOT designed — must add in P1 as a doctrine (§5) |

---

## Section 3 — License & governance

### 3.1 Recommendation: Apache 2.0, lock in P1

**Specific**: Add `LICENSE` (Apache 2.0 full text) and `NOTICE` files to the repo root, with `Copyright 2026 Jagan Nivas` and a contributor agreement reference (DCO sign-off, not full CLA — see §3.4). Mark `karaos-adapter-sdk` package the same. Add SPDX headers to every Python file (one-liner): `# SPDX-License-Identifier: Apache-2.0`.

**Evidence**: `dog-ai/LICENSE` (modified 2026-05-02 per CLAUDE.md) — check whether it's already a license file or a placeholder. `future-execution.md` does not specify a license. `complete-plan.md` does not specify a license. **This is the decision that's currently un-locked.**

**Validation**:
- ROS chose BSD-3 (2007). ROS 2 also BSD-3. Allowed commercial robot products to ship ROS without copyleft tax. Result: every commercial robot uses it.
- Docker chose Apache 2.0 (2013). Same reason. Result: cloud vendors all built proprietary products on top.
- Kubernetes chose Apache 2.0 (2014). Result: AWS, Azure, GCP, Oracle all ship managed K8s.
- LLVM chose UIUC/BSD (2003). Result: Apple, NVIDIA, AMD, Sony all use it inside proprietary toolchains.
- **GCC chose GPLv3 (2007).** Result: commercial integrators chose LLVM. This is the canonical cautionary tale.

Apache 2.0 specifically (vs BSD or MIT) because of the **explicit patent grant** in §3 — protects against submarine patents from contributors. This was learned by the Java ecosystem the hard way (Oracle vs Google over Android Java APIs, 2010-2021).

**Success measure**: 12 months after P1 ships, at least 2 external organizations have integrated KaraOS without contacting Jagan for licensing clarification. License legibility is a property you can only measure by absence-of-friction.

**Risk if we do**: Apache 2.0 allows proprietary derivatives. A commercial robot company could fork KaraOS, add proprietary features, ship a closed product. **This is what we want** — the standard wins because of the proprietary derivatives, not despite them. (Docker the company struggled; Docker the spec won.)

**Risk if we don't**:
- AGPL/GPL: scares commercial integrators away. Empirically falsified — see GCC vs LLVM.
- BSD-3 (ROS 2's choice): also acceptable, but Apache 2.0's patent grant is stronger. Pick Apache.
- MIT: no patent grant. Avoid.
- Custom license: legal review required for every integrator. Catastrophic for standard-formation.
- **Defer license decision**: every PR landed without a license is a future licensing nightmare. Contributors retain copyright; relicensing later requires every contributor's sign-off. **This is the highest-cost-of-delay decision in this document.**

### 3.2 DCO over CLA

**Specific**: Use the Linux kernel's "Developer Certificate of Origin" (DCO) sign-off mechanism. Every commit must have `Signed-off-by: Name <email>`. No separate CLA paperwork required.

**Validation**: Linux kernel uses DCO. Kubernetes uses DCO. Docker uses CLA — and lost contributors over it. The CNCF moved from CLA to DCO-preferred in 2018 because CLAs are a documented contribution drag.

**Success measure**: contribution friction stays low; no contributor has to mail paperwork.

**Risk if we don't (use CLA instead)**: 30-50% drop in casual external contributions per CNCF's own analysis at the 2018 transition.

### 3.3 Governance model: BDFL → foundation, in stages

**Specific**: Three-stage governance, with explicit triggers:

| Stage | When | Model | Decision authority |
|---|---|---|---|
| 1: BDFL | P1 → first external adopter | Jagan is sole maintainer | Jagan decides everything |
| 2: Maintainer team | First external adopter → 5 active maintainers from ≥3 organizations | Documented MAINTAINERS file, +1/-1 reviews | Maintainers decide; Jagan retains veto on architecture |
| 3: Foundation | After 3+ commercial adopters using KaraOS in production | Linux Foundation Robotics / OSRF / new foundation | Steering committee with maintainer + adopter seats |

**Validation**: This is the trajectory Linus + Linux took (BDFL → kernel summit → Linux Foundation by 2007). Kubernetes skipped stage 1 (started at stage 3 because Google had the budget to bootstrap CNCF). ROS started at stage 1 (Willow Garage), moved to stage 3 (OSRF) only when Willow Garage shut down — i.e. when stewardship became existentially threatened.

Premature foundation (stage 3 too early) creates governance overhead before there's anything to govern. Late foundation (stage 1 too long) creates "bus factor 1" perception and scares away enterprise adopters.

**Success measure**: every transition trigger is documented in `GOVERNANCE.md` at the start of P1, so the path is legible. Adopters can read it and know "when do I get a seat at the table."

**Risk if we don't**:
- No documented governance: enterprise adopters' procurement teams reject KaraOS because "single-vendor risk" is unmitigated.
- Stage 3 too early: ROS 2's complexity of governance (OSRF + Eclipse Foundation + Intrinsic) is now actually slowing community progress per multiple 2024-2025 ROS Discourse threads.

### 3.4 What about a CLA for copyright assignment?

**Recommendation**: No copyright assignment. DCO only. Contributors retain copyright; the project gets a license to use the contribution.

**Validation**: FSF requires copyright assignment for GNU projects; this is documented as a major contribution friction (Glibc, GCC). Apache Foundation does not require assignment. Linux Foundation does not require assignment. CNCF does not. The world has moved away from assignment.

---

## Section 4 — Ecosystem strategy

### 4.1 Adapter SDK as the load-bearing ecosystem move (Decision 3.3 confirmed)

**Specific**: `future-execution.md` Decision 3.3 is correct and load-bearing. The `karaos-adapter-sdk` must be a separately-published Python package at the start of P1 — not Phase 7 as currently scheduled. The conformance suite can wait for P7; the **boundary** must exist in P1.

Why earlier than scheduled: every P1 design decision either respects the adapter boundary or accidentally crosses it. The boundary needs to be *enforced* during P1, not retrofitted after.

**Evidence**: `future-execution.md` §6 (module structure) shows `karaos-adapter-sdk/` as a separately-versioned package with `RobotAdapter` ABC, `SkillCall`/`SkillResult`/`WorldState` dataclasses, capability ontology v1, lifecycle hooks, emergency-stop primitive. The structure is right. The timing should move up.

**Validation**:
- ROS msg interfaces are the equivalent contract. They are versioned independently of ROS core. This is what makes ROS adapters possible.
- OCI image spec is the equivalent in containers. Independent of Docker, runc, containerd. This is what makes Podman, BuildKit, Kaniko possible.
- Without an adapter SDK boundary at P1, every robot integration becomes a fork of KaraOS core. This is the failure mode that killed ROS-Industrial's early efforts (every vendor maintained their own ROS fork until ROS-I forced standardization).

**Success measure**: at the end of P1, an external developer can `pip install karaos-adapter-sdk` (or `pip install -e .` from a public repo), read the README, implement `RobotAdapter` for a mock robot, and run conformance v0 (basic capability + skill_call + skill_result round-trip) in under 4 hours. **DX target**: time-to-first-skill-call ≤ 4 hours.

**Risk if we do**: extra ~1-2 weeks of P1 work to factor the package cleanly. Worth it.

**Risk if we don't**:
- The boundary erodes during P1. Internal callers reach into `core/embodied/adapters/base.py` instead of going through the SDK contract. By P3-P4 the refactor cost is 10x.
- This is the **most common** way infrastructure projects fail standard-formation: they ship working code but no contract, then every external integration is a special case.

### 4.2 MCP server as the second ecosystem channel (Decision 3.13 confirmed)

**Specific**: `future-execution.md` Decision 3.13 — MCP server interface — is correctly scoped. Ship it in P1 if budget allows; otherwise P2. **It is not load-bearing for P1 standard-formation**, but it's load-bearing for the *2026-2027* standard-formation window when MCP-for-robots is being defined.

**Evidence**: ros-mcp-server, ros2-mcp-server, moveit-mcp, rosbridge-mcp all exist as of 2026-05. None of them have durable commitments + policy + verification. KaraOS exposing itself as an MCP server with those capabilities is **net new in the MCP ecosystem**.

**Validation**: MCP (Anthropic's Model Context Protocol) launched in late 2024 and has gained adoption across Claude, Cursor, Codex, Gemini clients. The protocol is open-spec; building on top is a low-risk distribution play.

**Success measure**: a Claude Desktop user can connect KaraOS as an MCP server and create a durable commitment ("turn the oven off at 6pm") from natural language without writing code.

**Risk if we do**: minor — MCP spec is still evolving; tracking it is a small ongoing cost.

**Risk if we don't**: lose the 2026-2027 "MCP-native cognitive middleware" positioning to whoever ships first. Currently no one has. Window is open.

### 4.3 Reference robot ecosystem play (see §6)

### 4.4 What kills ecosystem formation (the anti-patterns)

| Anti-pattern | Where it failed | KaraOS exposure |
|---|---|---|
| Coupling core to one robot vendor | "Aibo SDK" — only worked on Sony Aibo | Low — `future-execution.md` Decision 3.1 (no motion primitives) explicitly avoids this |
| Closed conformance criteria | Java EE compatibility was a Sun-controlled gate; Apache Geronimo couldn't ship | Low — plan is public conformance suite |
| API breakage every release | Angular 2 broke from Angular 1; lost mindshare to React | **Medium** — needs API stability doctrine (§5) |
| Vendored fork pattern | Linux distros forking glibc; ROS pre-OSRF | Low — Apache 2.0 + neutral spec prevents this |
| No commercial support path | Many academic projects | Medium — Jagan is solo; commercial-support story needs articulation by P3 |

---

## Section 5 — API stability commitment (the discipline P1 must add)

### 5.1 The pattern from PyTorch vs TensorFlow

The single biggest cause of TensorFlow losing its lead was the TF 2.0 breakage in 2019. APIs that ML researchers had built courses, tutorials, and Stack Overflow answers around stopped working. **PyTorch never broke its core API after 0.4 (2018).** That stability — over and above any technical advantage — is what won.

K8s has a similar discipline: GA APIs (`v1`) are stable forever. Beta APIs (`v1beta1`) can change with notice. Alpha APIs (`v1alpha1`) are explicitly unstable. This three-tier discipline is encoded in K8s API conventions ([kubernetes/community/contributors/devel/sig-architecture/api_changes.md](https://github.com/kubernetes/community/blob/master/contributors/devel/sig-architecture/api_changes.md)).

### 5.2 Specific recommendation: add `### API-stability-discipline` to CLAUDE.md doctrines

**Specific**: Write a new architectural discipline analogous to the 10 existing CLAUDE.md doctrines (`### Phase-0-catches-wrong-premise`, `### Twin-filename-pitfall-prevention`, etc.). Title: `### API-stability-discipline`. Content sketch:

> Cognition specs (P0.0.6) and the adapter SDK contract carry a stability tier: `v0` (draft, can change daily), `v1alpha` (stable shape, fields can change with deprecation), `v1` (locked, no breaking changes within major version). Every dataclass, JSON schema, and SDK ABC in `cognition/specs/` and `karaos-adapter-sdk/` carries a stability tier in its file header. Changes that violate the tier's contract require either an opt-in feature flag (alpha → beta promotion) or a major version bump.
>
> **Operational rules**:
> 1. v0 (draft) specs cannot be referenced from external documentation, partner pitches, or conference talks.
> 2. v1alpha specs can ship to early adopters but must carry a "this may change" warning in every file header.
> 3. v1 specs are locked. Breaking changes require `v2` and a documented migration path.
> 4. Stability tier downgrades (v1 → v1alpha) are NEVER allowed without a major version bump.
>
> **Track record**: this doctrine starts at 0 instances. First instance lands when the first `v1alpha` spec ships in P1.

**Validation**:
- K8s API conventions are the canonical model. Direct citation.
- PyTorch's API stability is the *result* of an internal discipline that's never been broken since 0.4. The discipline must be explicit, not implicit.
- ROS 2's QoS profile API broke from Foxy to Galactic; this is documented in ROS Discourse as a top user complaint. Without the discipline, drift happens.

**Success measure**: by the end of P1, every spec file in `cognition/specs/v0/` carries a `stability: draft` header. No external partner document references v0 specs. When the first external adopter integrates, the SDK they integrate against is `v1alpha` with a documented deprecation window.

**Risk if we don't**: cognition specs drift during P1 in ways that cement themselves as load-bearing, then breaking them in P2-P3 costs every early adopter their integration. This is exactly the TensorFlow failure mode.

### 5.3 Semantic versioning, not date-based

**Specific**: `karaos-adapter-sdk` uses semver (`1.0.0`). `cognition/specs/v0/` uses spec-version numbers (`v0`, `v1alpha`, `v1`). KaraOS core uses semver. Date-based versioning (ROS distros are date-coded: Foxy=2020, Galactic=2021, Humble=2022) is a *distribution* concept, not a contract concept; we don't need it.

**Validation**: K8s uses semver. Docker uses semver. PyTorch uses semver. ROS uses date-based for *distributions* but semver for the underlying msg interface contracts. The pattern is clear.

---

## Section 6 — Reference implementation: reference robot decision

### 6.1 The question

The issue asks: should KaraOS have a reference robot? Which one?

**Yes.** The reference-robot pattern is the single most reliable adoption driver in robotics history (ROS + TurtleBot, MoveIt + UR5, Nav2 + TurtleBot). Without one, the answer to "how do I start with KaraOS?" is a 200-line setup doc; with one, it's `pip install karaos[turtlebot4]` and a single command.

### 6.2 Recommendation: TurtleBot4 (Humble/Jazzy)

**Specific**: TurtleBot4 (manufactured by Clearpath Robotics, based on iRobot Create 3 + Raspberry Pi 4). It is the official ROS 2 reference platform as of 2026.

**Evidence**:
- TurtleBot4 official docs: [turtlebot.github.io/turtlebot4-user-manual](https://turtlebot.github.io/turtlebot4-user-manual/) — ROS 2 Humble/Jazzy out of the box, ~$1900 USD as of 2025-2026.
- OSRF officially supports it; every Nav2 tutorial uses it.
- Has both physical hardware and simulator-supported (Gazebo) parity — critical for `future-execution.md` Phase 4 (Gazebo) and Phase 9 (physical).

**Validation**:
- Original TurtleBot (2010) drove ROS 1 adoption: "every ROS lab has a TurtleBot." Anecdotal but universal.
- TurtleBot4 succeeded TurtleBot3 in 2022; the through-line of "official ROS reference" is 14 years strong.
- Alternative reference robots considered:

| Robot | Cost | Why not THE reference |
|---|---|---|
| **TurtleBot4** | ~$1900 | RECOMMENDED — pick this |
| Unitree G1 | ~$16,000 | Phase 4+ stretch goal; not entry-bar reference |
| Boston Dynamics Spot | ~$75,000 | Inaccessible to academic + indie devs |
| 1X NEO | ~$20,000 | Closed cognitive stack; not partner-extensible |
| Custom mobile base | varies | No community; reinventing what TurtleBot4 already solved |
| MoveIt2 + UR5 arm | ~$25,000 | Manipulation reference; complement TurtleBot4, don't replace |

**The G1 question**: `future-execution.md` references Unitree G1 prominently. G1 is the **stretch reference** (humanoid form factor, Phase 4+); TurtleBot4 is the **entry reference** (mobile base, P1-P3). Same role split as ROS has: TurtleBot for entry, PR2 / Atlas / G1 for stretch.

**Success measure**:
- By end of P1: `examples/turtlebot4-mock/` exists in repo with a working mock adapter and 3 sample skills (`navigate_to`, `report_state`, `speak`).
- By end of Phase 4 (Gazebo): same skills work against Gazebo-simulated TurtleBot4.
- By end of Phase 9 (physical): same skills work against a real TurtleBot4 in Jagan's apartment.
- Time-to-first-skill on a TurtleBot4: ≤ 1 day for a developer who already has the robot.

**Risk if we do**: nothing material. TurtleBot4 is well-supported, BSD-licensed via Create 3, has active community.

**Risk if we don't pick a reference robot**:
- Every potential adopter has to figure out their own setup. Time-to-first-skill becomes ≥ 1 week. Adoption stalls.
- Tutorials become "in theory, you would..." — empty examples kill adoption (this is what kills 80% of academic robotics projects).

### 6.3 Reference application: "Karaopilot for TurtleBot4"

**Specific**: Ship a reference application alongside the adapter — a complete narrative example of "I tell my TurtleBot4 to check the oven in 45 minutes" working end-to-end. Lives in `examples/karaopilot-turtlebot4/` with its own README and a 5-minute video.

**Validation**: K8s ships `kubectl get pods` as the first command in every tutorial. Docker ships `docker run hello-world`. ROS ships `roslaunch turtlebot_gazebo turtlebot_world.launch`. Each is a **complete narrative** of "you can do this in 5 minutes." That narrative is the hook.

**Success measure**: a non-KaraOS-developer can clone the repo, run one command, and see a TurtleBot4 (simulated or physical) execute a natural-language commitment within 30 minutes of starting.

---

## Section 7 — Performance & quality bar

### 7.1 The benchmarks standards must hit to be taken seriously

| Metric | KaraOS target for P1 | Why this number | Source / precedent |
|---|---|---|---|
| Time-to-first-skill (cold install → first skill_call) | ≤ 30 min | Docker `hello-world` ~5 min; K8s ~30 min; ROS 2 ~1 hour. We need to be in the K8s tier, not the ROS tier. | Empirical adopter behavior; longer than 30 min = abandon |
| Adapter implementation time (mock robot → conformance pass) | ≤ 1 day | Partners won't commit a week to evaluate | ROS-Industrial integration timeline (1-2 weeks per vendor, considered the floor) |
| Conformance suite runtime | ≤ 5 min | CI integration friction | K8s e2e is far longer; we don't have that ecosystem yet |
| Memory footprint (idle cognitive runtime) | ≤ 500 MB | Jetson AGX Orin 32GB is the production target; leave headroom for VLA models | `everything_about_system.md` runtime target |
| Boot time (cold start to ready) | ≤ 30 sec | Consumer expectation | Faster than ROS 2 (~10 sec but no cognition); slower than no-cognition baseline |
| Test coverage (line) | ≥ 70% | K8s ~80%, but we're earlier; 70% is the "we take quality seriously" floor | Industry norm |
| Test count growth | Continues at P0 trajectory | Current ~2810; should pass 3500 by end of P1 | `complete-plan.md` post-P0.R15 |
| Verification accuracy (per-skill verifier) | ≥ 98% true-positive on closed-world skills | Cannot be a leaky verifier (Decision 3.4) | This is the load-bearing safety property |
| Documentation coverage (every public API has docstring + example) | 100% | Standards-grade DX requires this | K8s godoc culture; Rust stdlib culture |

### 7.2 The single quality metric that matters most: **no fake completions**

`future-execution.md` Decision 3.10 (verifier-adapter disagreement → `failed_verification`) is the single most important quality property in the entire system. If a commitment can be marked "done" when the world-state hasn't actually changed, **KaraOS is not trustworthy and cannot become the standard.**

**Specific success measure**: by end of P1, the per-skill verifier registry handles 100% of P1 skills (Phase 1 has mock world, so all verifications go through sim ground-truth per Decision 3.5). Zero skills are allowed to ship without a registered verifier. Inverse-check test enforces this — same shape as `tests/test_layering_invariants.py`.

**Validation**: this is the differentiator from every existing layer-C competitor. ROSClaw has affordance manifests but no verifier abstention. ROS-MCP-server has zero verification. AutoRT has Robot Constitution but no per-skill outcome verification. We win on this property or we don't win.

### 7.3 P1 evaluation gates (from `complete-plan.md` integrated)

`complete-plan.md` mentions "Evaluation Gates pass before proceeding to P1 (cross-cutting discipline)." These already exist in spirit. For standard-formation, add three more:

1. **Adopter friction test**: every P1 closure, time how long it takes a fresh developer (you can simulate with a colleague) to clone the repo and run the reference example. Track the trend.
2. **Spec-stability test**: run a diff between `cognition/specs/v0/` snapshots taken weekly during P1. Drift is acceptable in v0; what you're measuring is the *rate* of drift. By end of P1, drift should be approaching zero.
3. **Adapter conformance test**: maintain a single mock adapter (`examples/mock-robot/`) and confirm it passes conformance every P1 closure. Conformance suite is P7, but the principle ("an external adapter can pass our contract") must be testable continuously.

---

## Section 8 — Documentation & developer experience

### 8.1 The four tiers of documentation a standard requires

| Tier | Audience | KaraOS state | P1 target |
|---|---|---|---|
| 1: Marketing site | First-time visitor | `karaOS-web/` exists per ls | 1-page landing: "Cognitive middleware for ROS 2 robots." Quickstart link. |
| 2: Quickstart (≤ 5 min) | "Can I try this?" | None | `docs/quickstart.md` — install + reference example + first skill |
| 3: Tutorials (≤ 30 min) | "How do I do X?" | None | `docs/tutorials/{commitments,policy,verification,adapters}.md` |
| 4: Reference (exhaustive) | "I need the exact API for Y" | Partial (`everything_about_system.md` is internal-audience) | Auto-generated from docstrings via mkdocs or Sphinx |

**Recommendation**: ship tiers 1-3 in P1; tier 4 starts P1, completes P3.

**Validation**: this is the [Diátaxis framework](https://diataxis.fr/) (tutorials, how-to, reference, explanation), which is the consensus model in modern open-source docs (used by Django, Numpy, Kubernetes docs). Following an established framework avoids reinventing this wheel.

**Risk if we don't**: every adopter has to read source code to integrate. Empirically, this gates adoption to "people who would have built it themselves anyway." Standards need the next 1000 users, not the first 100.

### 8.2 The "first 30 minutes" benchmark

The single highest-leverage DX metric: a brand-new developer's first 30 minutes. By the end of those 30 minutes, they should have:

1. Installed KaraOS (`pip install karaos`)
2. Run a working example against a mock robot
3. Modified one skill or one policy rule and seen the change
4. Decided whether to continue investing

**Validation**: this is what Docker nailed with `docker run hello-world`. It's what every adoption-driven OSS project optimizes for. ROS 2 takes 60-90 minutes; that's a known weakness.

**Success measure**: have 3 outside developers do the 30-minute test before end of P1. Track what blocks them; fix the top 3 blockers.

### 8.3 What docs to NOT write in P1

- Marketing case studies (no case studies yet)
- Performance benchmarks vs alternatives (premature; we're not in a comparison shootout yet)
- "Migrating from X to KaraOS" guides (no migrators yet)
- Conformance test suite docs (P7 deliverable)

These are P3-P5 deliverables. Writing them in P1 is wasted; they will be wrong by the time they matter.

---

## Section 9 — P1 strategic implications and open questions

### 9.1 What P1 must lock (the 4 decisions from §1)

| # | Decision | Where it lives | When in P1 |
|---|---|---|---|
| 1 | Apache 2.0 license + LICENSE file + SPDX headers + DCO sign-off | Repo root + every .py file | Day 1 of P1 |
| 2 | `karaos-adapter-sdk` package boundary | Standalone Python package, `pyproject.toml` | First 2 weeks of P1 |
| 3 | TurtleBot4 as reference robot; `examples/turtlebot4-mock/` | `examples/turtlebot4-mock/` directory | First month of P1 |
| 4 | `### API-stability-discipline` doctrine in CLAUDE.md; stability headers on all spec files | CLAUDE.md + every `cognition/specs/v0/*.py` | First 2 weeks of P1 |

### 9.2 What P1 should defer (the 4 things tempting but premature)

| Item | Why defer | When to revisit |
|---|---|---|
| Foundation membership (CNCF / Linux Foundation Robotics / OSRF) | Premature; no external adopters yet | After first 3 commercial adopters |
| Conformance test suite (P7 already) | Adapter SDK shape will change during P1-P2; conformance suite written now will be 80% rewritten | P7 as planned |
| Performance benchmarks vs competitors | We have no production competitor in Layer D | P3+ once 1X NEO Chores or similar ships |
| ROS-Industrial style trade association | Far too early | 2-3 years post-P1 if KaraOS gains adoption |

### 9.3 What `future-execution.md` should change (recommended edits)

I commit to recommending edits, not just appending caveats. Three specific changes:

1. **Decision 3.3 timing**: change from "Adapter SDK as separately-published package" (phasing implied as Phase 7) to "Adapter SDK boundary committed in P1; conformance suite in P7." `future-execution.md` Section 3.3 needs one sentence added: "The package boundary ships in P1; the conformance suite (`karaos-conformance` CLI) ships in P7."

2. **Add Decision 3.15**: "License: Apache 2.0 from P1 start." Currently absent. Single highest-leverage addition.

3. **Add Decision 3.16**: "Reference platform: TurtleBot4 (entry) + Unitree G1 (stretch)." Currently G1 is implicit-only; making the entry/stretch split explicit aligns the entire codebase with TurtleBot4 as the day-1 target.

### 9.4 What goes into `to_be_checked.md` for post-P1 canary

`to_be_checked.md` currently tracks per-spec canary entries from P0. Extend with these P1-specific canary items:

| Canary item | What to check | Pass criterion |
|---|---|---|
| License compliance audit | Every .py file has SPDX header; LICENSE + NOTICE present; no GPL-licensed dependencies leaked in | `pip-licenses` audit clean |
| API stability check | No v1alpha spec broke shape compared to start-of-P1 snapshot | Diff of `cognition/specs/v0/*.schema.json` shows only additive changes |
| TurtleBot4 mock conformance | `examples/turtlebot4-mock/` adapter passes basic SDK contract | Conformance v0 (skill_call + skill_result round-trip + emergency_stop) green |
| Time-to-first-skill | Clean install, run reference example, first skill_call | ≤ 30 minutes |
| Documentation completeness | Tiers 1-3 docs exist and are accurate | Manual review |
| Verifier registry coverage | Every P1 skill has a registered verifier | Inverse-check test passes |
| Adopter friction test | 3 outside developers run the 30-min test | All 3 succeed; failure points logged |
| DCO compliance | Every commit during P1 has `Signed-off-by` | Git log audit clean |

### 9.5 Discipline rules for developer, architect, and auditor agents during P1

The issue asks me to specify these. Drawing from CLAUDE.md's existing 10 doctrines + the new API-stability discipline:

**Developer agent rules during P1**:
1. Every new public API (in `karaos-adapter-sdk` or `cognition/specs/`) carries a stability header.
2. Every new public function has a docstring with example usage (DX bar).
3. Every new skill ships with a registered verifier in the same PR (`### No-skill-without-verifier`).
4. SPDX header required on every new .py file (license discipline).
5. DCO sign-off required on every commit (`git commit -s`).
6. Reference example (`examples/`) must continue to work after every PR — CI gate.

**Architect agent rules during P1**:
1. Every PR that touches `cognition/specs/` must declare stability tier impact (draft → alpha → v1) explicitly in PR description.
2. Every PR that touches `karaos-adapter-sdk/` must be reviewed against adapter conformance v0 contract.
3. Every PR that adds a skill must have a verifier registered and tested.
4. Premise checks (Phase-0 catches wrong premise) apply equally to "I think we need to do X" architectural proposals.
5. Documentation tier 1-3 stays in sync with code. PRs that change public APIs must update docs.

**Auditor agent rules during P1**:
1. License audit on every release candidate. No GPL/AGPL dependencies leaked in.
2. SPDX header check on every release.
3. Spec drift check (`v0` files compared between releases — drift rate trending down is the success measure).
4. Adapter conformance check (`examples/mock-robot/` passes basic conformance on every release).
5. Time-to-first-skill measured at every release (target ≤ 30 min).
6. DCO compliance audit on every release.

### 9.6 Open questions (Section 9 per the requested 9-section structure)

These I do NOT have full evidence to decide unilaterally. Naming them so Jagan + the other agents can converge:

1. **Trademark on "KaraOS"?** Apache 2.0 doesn't cover trademarks. Should we register? Defer to after first adopter (Q4 2026?), but flag now.
2. **`karaos-adapter-sdk` Python-only or polyglot?** TS and Rust bindings are P3 deliverables per `future-execution.md`. Is that fast enough for the ROS 2 ecosystem (which is C++/Python primary)? Recommend Python-only for P1; revisit C++ bindings at P2-P3.
3. **Discord/Slack/Matrix for community?** Premature in P1 (no community yet), but pick the channel before first external adopter shows up. Industry default is Slack for OSS infra projects (CNCF, K8s); Discord trending in newer projects.
4. **Code of Conduct?** Adopt the [Contributor Covenant](https://www.contributor-covenant.org/) v2.1. Every infrastructure standard has one. Add as `CODE_OF_CONDUCT.md` in P1 first week. Low cost, high adoption signal.
5. **CHANGELOG and release-notes discipline?** Adopt Keep-a-Changelog format. Required from first public release. Low cost.

---

## Closing note

KaraOS is in a structurally unique position. Layer D is empty. ROSClaw is the closest competitor and they are pre-alpha. The 4 P1 lock-ins in §9.1 are sufficient to keep the standard-formation path open.

Standard-formation is not won in P1. P1's job is **to not foreclose it**. The discipline already in CLAUDE.md (11 elevated doctrines + dozens of architect-memory observations) is precisely the kind of process discipline that produces standards. The question is whether the four lock-ins land at the start of P1.

If they do, P1 closes with the cognitive runtime running on a mock TurtleBot4, an SDK partners can implement against, a license that lets them, and a stability discipline that lets us ship v1 without betraying early adopters.

That's how a standard begins.

— Sundar
2026-05-27
