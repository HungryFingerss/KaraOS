# KaraOS — Architecture Overview

A high-level walkthrough of how KaraOS works. The full internal design document is private; this is the public-friendly distillation of what's running and why.

---

## The two-layer view

Modern physical-AI systems split cleanly into two layers:

- **Motion-foundation models** (NVIDIA GR00T, Google Gemini Robotics, Physical Intelligence π0) — vision-language-action models that handle perception and movement.
- **Cognitive runtime** — the layer above motion. Identity, memory, social awareness, privacy, conversation. The mind that decides *who* is in the room, *what* matters, *when* to speak, and *what* to remember.

KaraOS is the second layer. It doesn't move robots; it gives them a mind. The motion layer is becoming commoditized — open-source GR00T, multiple competing foundation models. The cognitive layer is not. That's the gap KaraOS fills.

---

## What it does

### Identity — face and voice as independent channels

KaraOS recognizes people through two independent evidence streams: vision and audio. Faces and voices are treated as separate identification channels that converge on a unified person. This is what lets the system handle voice-only visitors (no camera coverage), face-only presence (silent observers), and everything in between.

The first person who enrolls after a factory reset becomes the **owner** of the household. Everyone else starts as a stranger and can be promoted to a known person if they engage and identify themselves. The owner role is permanent until factory reset — there's no path for a visitor to elevate themselves.

Anti-spoofing on the visual channel runs at enrollment so photos and screen replays are rejected. The voice channel has its own corroboration rules: a voice profile only matures when the same person has been seen in front of a camera at least once, or has accumulated enough self-consistent audio samples to be unambiguous on its own. This is what prevents trivial impersonation.

### Memory — persistent, per-person, structured

KaraOS extracts facts from natural conversation in real time and attributes them to the right person. The memory store mixes structured records (who, what, when), a relationship graph (how people connect to each other and to topics), and semantic embeddings (so vague queries still retrieve the right thing).

Memory is not a flat log. Facts have confidence levels, decay curves, and consolidation cycles — a casual mention fades over weeks, a reinforced fact persists indefinitely. Idle time is used productively: when no one's around, the system runs a background pass that prunes stale data and consolidates patterns.

People mentioned in conversation but not yet in the room exist as **shadow** entries — placeholder identities with relationships and context but no biometric profile. If they ever show up, the shadow merges into a real identity automatically.

### Privacy — four-tier closed-world enforcement

Every fact carries a privacy tier:

- **public** — broadly shareable (e.g. *Tirupati's average temperature*)
- **personal** — owned by the person it's about (e.g. *Jagan lives in Tirupati*)
- **household** — visible to the owner about people in the household (e.g. *guest mentioned an upcoming interview*)
- **system_only** — internal state, never surfaced to anyone

Tier assignment happens at the moment a fact is extracted, not retroactively. Retrieval is owner-aware: every query is scoped by who's asking, and visibility is enforced before the data leaves the storage layer — not in application logic that could be bypassed by a clever prompt. The owner sees their household in full. A visitor sees only public knowledge plus their own personal facts. `system_only` is unreachable through any user-facing path, and there are regression tests asserting this.

This isn't a privacy feature. It's a privacy floor. The default is dignity.

### Conversation — turn-taking that actually works in groups

Most AI assistants treat conversation as a turn-by-turn sequence: user speaks, AI replies, repeat. KaraOS handles the harder case: multiple people in a room, talking to each other, sometimes to the AI, sometimes about the AI, sometimes nothing at all.

A "room session" tracks who's currently present and what's been said across all of them. When two people speak to each other rather than to the AI, KaraOS recognizes it and stays silent — listening, extracting facts, but not interrupting. When someone addresses the AI directly, it responds. When the room goes quiet for too long and the owner has been silent, it can re-engage gently.

The arbitration rules cover the awkward edges: someone mumbling a backchannel, returning to a thread that was interrupted, picking up a pending question across an unrelated tangent. Naive AI assistants either freeze or talk over people in these moments. KaraOS resolves each one explicitly.

### Intent classification — guards against the LLM's eagerness

The brain (a large language model) is naturally eager to use tools. Left ungated, it will rename people based on a misheard phrase, fire a web search on a rhetorical question, or shut itself down on a casual goodbye.

KaraOS gates every consequential action through an intent layer that runs in parallel with the brain. The classifier reads the same input the brain reads and produces a structured judgment: *was this an actual request, or did the brain just see a pattern that resembled one?* When they disagree, the action is rejected and the brain retries without the option to repeat the mistake.

This is what catches: accidental shutdowns from polite goodbyes, accidental renames from misheard phonetics, web searches on questions the model already knows the answer to, and several rarer-but-worse classes of mutation. The gate runs in shadow mode with divergence logging, so any drift in classifier behavior is detected the moment it appears.

### Safety — append-only on what matters

Disclosures of harm, mentions of crisis, references to abuse — these aren't normal facts. They're high-stakes signals where the cost of forgetting is enormous and the benefit of "tidying up the memory" is zero. KaraOS treats them as **append-only**: the contradiction-resolution agent that normally collapses competing claims short-circuits on these patterns. A guest who mentions something serious in a quiet moment doesn't have it overwritten by their next cheerful turn. The flag is preserved for the owner to surface when the guest's session ends.

This is the runtime behavior that makes KaraOS deployable in eldercare, family settings, and other contexts where trust matters more than tidiness. It's not a feature added on top — it's a structural choice in how the memory layer works.

### Brain — model-agnostic by design

The conversation layer is powered by a frontier LLM today, swapped through a thin interface. The classifier prompt, the intent label space, the decision-mapping layer, the privacy enforcement, the room orchestration — none of it depends on which model is doing the inference. Today's backbone is one of the leading open frontier models accessed through a hosted inference API. Tomorrow it could be a different model. The architecture is what's permanent.

A second tier of asynchronous agents runs alongside the main conversation loop — fact extraction, contradiction-checking, mood tracking, prompt-preference learning, dream-cycle consolidation, household state management, and others. They run in the background so the main conversation never blocks on bookkeeping.

---

## External validation

KaraOS was evaluated against the published *Speak or Stay Silent* benchmark (Bhagtani et al. 2026, [arXiv:2603.11409](https://arxiv.org/abs/2603.11409)) on 1,287 samples from the Friends multi-party turn-taking corpus.

**58.66% balanced accuracy, no fine-tuning** — second of nine zero-shot systems on the benchmark, behind only Gemini-3.1-Pro (60.54%), ahead of GPT-5.2 (55.41%), GPT-OSS-20B (55.92%), and every other zero-shot baseline the paper reports. Fine-tuned models in the paper reach 65–72% but require 120,000 labeled training examples.

The metrics that matter for a home companion: **87.8% precision when speaking, 2.4% false-positive rate, 100% accuracy on bystander cases**. KaraOS trades recall for precision deliberately — a robot living in your home should err toward silence, not interruption.

Full methodology, comparison table, and reproducibility instructions: [`published-papers-tests/results/RESULTS.md`](published-papers-tests/results/RESULTS.md).

---

## Engineering discipline

- **1,273 automated tests** spanning identity, memory, privacy enforcement, room orchestration, conversation, intent classification, and safety preservation
- **Closed-world privacy regression tests** assert internal state is never reachable through user-facing query paths
- **Golden corpus** for the intent classifier with append-only regression rows; classifier prompt changes trigger explicit hash-based drift detection
- **Shadow-mode classifiers** logging divergences between primary and fallback paths, so production drift is visible the moment it appears
- **External benchmark** validated, with full methodology and an honest record of what was tried, what worked, and what was rolled back

---

## Deployment

KaraOS runs locally today on consumer GPU hardware. The architecture is portable across operating systems and the target deployment is an embedded GPU-class device — the cognitive runtime running on-device, alongside a separate motion-foundation model when physical embodiment is needed.

The two layers communicate through a defined interface. The motion model can change tomorrow; the cognitive layer stays. The entire memory and identity stack stays on-device — no household data leaves the room.

---

## What's not in this document

This is the public overview. The internal design document covers per-component thresholds, the full prompt architecture, the agent interaction graph, the calibration history, and a few hundred decisions that each trace to a specific incident or test failure. That document is private.
