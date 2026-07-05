# persona/: persona packs (who the deployment IS)

A persona pack is data-only YAML carrying the deployment's *character*: the identity paragraph and character text that fill the two slots in the system-prompt template (`core/brain.py::_SYSTEM_PROMPT_TEMPLATE`), the TTS voice, and the default self-name. Externalized in SB.8, before that, the robot-dog personality was welded into the engine prompt.

## Files
- `companion_dog.yaml`, the reference persona: the companion dog (default name "Dog", Kokoro voice `af_heart`, the dog-companion identity/character text). Recomposes the pre-externalization system prompt **byte-identically** (golden-locked at 13,640 bytes).
- `robotics_placeholder.yaml`, a deliberately different pack on all four axes (name "Unit", voice `am_adam`, platform-style identity/character), exists to prove the differential: two packs, one engine, different characters.
- `_schema.py`, fail-loud validation; `SLOT_KEYS` locked; unknown persona id crashes (no companion fallback, a kiosk silently booting as a dog is the failure this prevents).

## The floor/flavor split (the load-bearing rule)
Packs carry **flavor** (identity, character, voice, name). The engine keeps the **floors**, the 10 engine prompt contracts (honesty policy, memory discipline, identity-evidence handling, tool rules, privacy…) render for EVERY persona; a pack cannot remove or override them. Slot filling uses brace-safe replacement (`str.replace`, not `.format`) so pack text can never inject into template keys, and slot content is closed-channel (no nested expansion).

Loaded by `core/persona_loader.py`; selected by the profile's `persona: { persona_id: ... }` reference. Known limitation (banked): a handful of dog-flavored phrases still live inside two engine contract blocks (the D1 coarse-cut leak), surgically separable in a future slice; tracked, not hidden.
