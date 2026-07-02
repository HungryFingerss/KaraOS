# Live session logs

Raw terminal output captured from KaraOS during real live sessions. Nothing is hidden — every face seen, every word transcribed, every brain decision, every tool gated, every memory write.

These logs are the densest single-file representation of what KaraOS actually does in production. They're harder to read than the methodology docs in `published-papers-tests/`, but they're the closest thing to "watch the system run for an hour without me there to narrate it." A researcher who wants to verify what the architecture docs claim should read one of these end-to-end.

---

## Files

| File | Date | What's in it |
|---|---|---|
| [`2026_04_26_demo.md`](2026_04_26_demo.md) | 2026-04-25 | The first public demo — the same session that became the LinkedIn video. One person (Jagan), full conversation, identity flow, intent classification, room orchestration, memory writes. Best starting point for a first-time reader. |
| [`2026_05_01_multi_convo_canary.md`](2026_05_01_multi_convo_canary.md) | 2026-05-01 | A 5-person live canary covering ~50 minutes of multi-party conversation. Three real participants (Jagan, Lexi, John) — all of whom consented to publication of this log. Tests the system's hardest case: voice-only stranger entry, name promotion, cross-person inference (John as Lexi's brother), session switching across speakers, privacy filtering on cross-person retrievals, end-of-session synthesis. Also captured the 2026-04-29 "negative-cosine bug" being live-validated as fixed — Lexi's voice now correctly opens a new stranger session instead of being dropped silently. |

---

## How to use these

Two options:

**1. Read top-to-bottom.** Slow but instructive. Every log line carries semantic content — `[Vision]`, `[Audio]`, `[Voice]`, `[Brain]`, `[BrainAgent]`, `[Pipeline]`, `[Privacy]`, `[Reconciler-Shadow]`, `[Intent]`, `[Room]` are all distinct subsystems. Pattern-match the prefixes and you can reconstruct the architecture.

**2. Paste into an LLM and ask.** Copy the entire fenced log block into ChatGPT, Claude, Gemini, or any frontier model and ask things like:
- *"Walk me through what's happening in this session."*
- *"How does the system identify a new speaker?"*
- *"What does the privacy filter do?"*
- *"When does the brain decide to stay silent?"*

Modern LLMs can reconstruct the architecture from these logs alone, line by line. The 5-person canary in particular is dense enough that walking through it with an LLM is faster than reading the architecture docs.

---

## What you'll see in these logs

A non-exhaustive guide to log prefixes:

| Prefix | What it means |
|---|---|
| `[Pipeline]` | Top-level event-loop state (turn start/end, session open/close, listening/speaking transitions) |
| `[Vision]` | Camera frames, face detection, recognition, anti-spoofing |
| `[Audio]` | Mic listening, VAD, Smart-Turn neural end-of-turn detection, TTS playback |
| `[STT]` | Whisper transcription output |
| `[Voice]` | ECAPA-TDNN speaker recognition, voice gallery updates, pyannote diarization, routing decisions |
| `[Reconciler-Shadow]` | The voice/vision reconciler making routing decisions (Phase 4 cutover state) |
| `[Brain]` | LLM streaming, tool calls, system-prompt context built |
| `[BrainAgent]` | Background knowledge extraction, contradiction checks, schema normalization, dream-loop pruning |
| `[Privacy]` | Per-query privacy-tier classification and visibility filtering |
| `[Intent]` | Intent classifier output (LLM and graph-classifier shadow comparisons) |
| `[Room]` | Multi-party room session lifecycle |
| `[NudgeAgent]` | Cross-person inference, visitor alerts, proactive nudges |
| `[BrainDB]` | Knowledge graph mutations (entity migrations, shadow promotions, fact storage) |
| `[GraphDB]` | Kuzu graph rebuilds and edge writes |
| `[EmotionAgent]` | Per-person emotion classification (HuggingFace distilroberta) |

---

## Privacy and consent

Every participant in the logs above is either:
- The system's primary user (Jagan), whose conversations are documented as part of his own engineering work, or
- A consenting test participant (Lexi, John, etc.) who agreed to having a session published.

If you are a researcher wanting to use these logs as conversation data for your own work, please attribute them as KaraOS canary sessions and link to this repo. The logs are public; the underlying participants are real people who agreed to be part of system testing, not anonymous data subjects.
