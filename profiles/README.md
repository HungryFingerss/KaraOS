# profiles/: deployment configuration (what KaraOS deploys AS)

A profile is pure data selecting how the engine deploys, no code, no behavior definitions. Select with the `KARAOS_PROFILE` env var (default: `companion`). Unknown profile id = loud load failure, never a silent fallback.

## Files
- `companion.yaml`, the default: the home-companion deployment (full agent set, cloud-primary LLM, `identity: known_faces` / `retention: persistent`, the `companion_dog` persona).
- `robotics.yaml`, the embodied/robotics profile (differs on hardware tier, identity/retention axes, persona = `robotics_placeholder`; exercised by its own CI leg in the nightly perception-bench matrix).
- `_schema.py`, fail-loud validation: unknown keys REJECTED (including a stray `system_name`, that trap class is structurally dead), types checked, referenced registries verified.
- `_registry.py` (the agent registry (SB.3): profiles select WHICH of the background agents run by name; an unselected agent is never constructed (object gone AND behavior gone) CI-proven per agent).
- `_blocks.py`, the prompt-block registry (SB.4): profiles select which prompt blocks render, against the `PROMPT_BLOCKS` harness.

## The axes a profile controls
agents on/off · prompt blocks · models + thresholds · **identity mode** (`known_faces` / `anonymous` / `none`) + **retention mode** (`persistent` / `session` / `ephemeral`), the SB.5 two-axis privacy enforcement · hardware tier · the persona pack reference (`persona: { persona_id: ... }`), identity text lives in `persona/`, never here.

## What a profile can NOT do
Disable the engine floors: anti-spoof, the reconciler's identity routing, memory privacy tiers, resilience watchdogs, the honesty contracts. Floors render/enforce for every profile, that split (floor vs flavor) is CI-locked.

Per the SB.9 design, profiles grow four selection axes at build time (`sensors:` / `renderers:` / `flow:` / `tools:`, lists of registered names) so a new deployment is a YAML file + thin adapter packages, zero core diffs.
