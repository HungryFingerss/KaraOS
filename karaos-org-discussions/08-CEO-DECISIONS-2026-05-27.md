# CEO STRATEGIC DECISIONS — 2026-05-27

**Context**: Following the 7-perspective external audit (`karaos-org-discussions/00-07-*.md`), Jagan (CEO) reviewed the synthesized recommendations and locked the following strategic decisions before pre-P1 work begins.

---

## ACCEPTED

### 1. Strategic reframing
P1 = embodied runtime landing, NOT pipeline.py decomposition.
Layer D cognitive middleware (above motor control, below natural language) is the project's architectural positioning.

### 2. Layer D middleware claim
Accepted with 3-5 year market-defining horizon.
Embodied runtime ships these components in P1:
- Commitment store (per-task ACID state machine)
- Scheduler (async loop with priority + preemption)
- Policy engine (safety gates + abstention)
- Verifier registry (action grounding + completion check)
- Adapter SDK (robot-agnostic motor interface)
- MCP server (model-context-protocol surface for external LLMs)

### 3. Strategic clock — 8 to 10 weeks
Competitive pressure window confirmed:
- ROSClaw v0.2 (open-source ROS 2 orchestration)
- NVIDIA Isaac Orchestrate (proprietary, but rapidly evolving)
- MCP-for-robots (Anthropic-driven standard, fast-moving)

P1 cycle compresses to 8-10 weeks total. Pre-P1 fixes ~4-6 architect days, then 5 parallel P1 tracks.

### 4. Reference robot
TurtleBot4 in Gazebo (open-source ROS 2 simulator).
$200 hardware exists; P1 ships simulation-only.
Unitree G1 ($16K) deferred — unjustifiable risk for a first embodied canary.

### 5. Governance prerequisites
Apache 2.0 LICENSE + GOVERNANCE.md + SPDX headers land before any P1 spec references open-source positioning.
Pre-P1 Bundle 2 owns this work.

---

## DEFERRED

### 6. Agent consolidation
Audit recommended 18 agents → 4-6.
**Decision: DEFER to P2 / hardware migration.**

**Rationale (Jagan, 2026-05-27)**:
Under 2-stack architecture (companion stack on laptop + robotics stack in Gazebo), the 18 agents live on the companion stack and are NEVER in the embodied runtime's hot path. Robot latency budgets are not blocked by agent latency. Consolidation only becomes load-bearing if/when:
- A robot action requires synchronous agent decision (e.g., friction agent in policy gate)
- Real hardware tightens latency budget (<100ms reaction)
- Agents need to run ON the robot's compute (memory/power constraints)

None of these apply in P1's 2-stack scope. Revisit at P2 with real latency data.

**Discipline to enforce at P1**: embodied runtime's policy gate **MUST NOT** synchronously call an agent. All agent signals flow async: agent → brain.db → policy reads pre-computed values. Same separation pattern as today's `_brain_orchestrator` from the conversation hot path.

### 7. pipeline.py decomposition
Audit's P1.A1 → service decomposition.
**Decision: DEFER to P2.**

Audit's call: pipeline.py decomp is not P1's strategic question — embodied runtime landing is. Architect (Claude) had recommended P1.A1 at P0.S10 closure based on closure-narrative momentum. External audit overrode. Architect concurs at this CEO review.

### 8. Canary timing
**Decision: DEFER** until pre-P1 fixes complete.
Re-evaluate against 8-10 week clock once pre-P1 lands.

---

## SEQUENCING

### Pre-P1 must-fix bundle — Path A (5 bundled cycles, ~4-6 architect days)

| # | Bundle | Items | Effort |
|---|---|---|---|
| 1 | Docs+CI | MF1 + MF3 + MF10 | ~1d |
| 2 | Governance | MF2 | ~1d |
| 3 | Critical bugs | MF4 + MF5 | ~1.5d |
| 4 | Observability+concurrency | MF6 + MF9 | ~0.5d |
| 5 | Contract typing | MF7 + MF8 | ~1d |

Each bundle follows full strict-mode: Phase 0 audit → Plan v1 → auditor review → implementation → closure-audit.
Bundle 1 starts immediately.

### P1 cycle structure — 8-10 weeks, 5 parallel tracks

| Track | Scope | Owner-domain |
|---|---|---|
| P1.A | Architecture pre-work (interface seams, no pipeline.py decomp) | Architecture |
| P1.E | Embodied runtime (commitment store + scheduler + policy + verifier) — load-bearing | Robotics |
| P1.S | Adapter SDK (robot-agnostic motor interface) | Robotics |
| P1.M | MCP server (external LLM surface) | Integration |
| P1.R | TurtleBot4 reference adapter + Gazebo bring-up | Robotics |

Eval harness (`tests/embodied_eval_bench.py`) ships first in P1.E.0 — gates every subsequent track.

---

## ROLE ACKNOWLEDGEMENT

**Architect (Claude) error owned**: recommended pipeline.py decomposition at P0.S10 closure based on closure-narrative momentum (high-confidence completion of P0.S* arc, multi-discipline preventive convergence reached 6 instances, strong forward signal). That was an INTERNAL signal, not an EXTERNAL strategic one.

External audit caught the misframe: pipeline.py is P2 cleanup work; the strategic question is whether KaraOS becomes the Layer D middleware standard before competitors close the window.

**Discipline lesson banked**: closure-narrative momentum is NOT a strategic signal. Future P1+ cycles MUST reference external strategic analysis before locking direction. Architect's role is to execute decisions, not to lock strategy from internal arc momentum.

---

Signed: Jagannivas (CEO), 2026-05-27
Witnessed by: Architect (Claude), Auditor (external)
