# flows/ — the app layer (use-case choreography)

The top layer of the architecture: **`flows/` → `runtime/` → `core/`** (never imports `pipeline`; the boundary is AST-enforced). A flow owns the *choreography* of a deployment — which tools are in play, the turn sequence, the use-case state machine. The engine floors (perception, identity routing, memory gating, safety, honesty) run underneath every flow and cannot be bypassed from here.

## Today
- `companion/tools.py` — the companion's LLM-tool dispatch surface, relocated verbatim from pipeline.py (P1.A1 SP-6.2): `_execute_tool`, the 5 identity/action handlers (`update_person_name`, `report_identity_mismatch`, `update_system_name`, `shutdown`, `search_memory`), the `_TOOL_HANDLERS` registry, `_ToolContext`, and the server-side gates (`_tool_allowed`, user-text grounding, enrollment-mishear escape hatch). `pipeline.py` re-exports everything for compatibility.
- `companion/turn_flows.py` — companion turn choreography helpers.

## Where this is going (designed, not yet built)
The SB.9 adapter-seam design (`rule book/cycle-specs/` archive + the SB design docs) makes flows a **profile-selectable package**: `flow: store_checkout` in a profile loads `flows/store_checkout.py`, which registers its own tools and drives the loop through a small hook surface (`on_boot`, `on_person_recognized`, `on_turn`, `on_session_end`, `on_idle_tick`) — with the 7 engine floors (privilege, safety-gate, perception, memory, identity/retention, resilience, honesty) enforced by construction. The build lands with the supermarket wedge.
