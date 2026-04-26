# KaraOS

**Cognitive runtime above GR00T**

---

## What it is

A companion AI for social robots. Built to be present, not just useful.

Most AI today answers questions. This one keeps you company.

Kara-OS is the cognitive layer for a robot companion — the part that recognizes who you are, remembers your conversations, reads the room, and knows when to speak and when to stay quiet. The hardware comes later. The mind comes first.

It's designed to feel less like a product and more like a presence.

---

## What it does

- **Recognizes everyone in the household.** Knows the difference between you, your family, your friends, and someone visiting for the first time.
- **Holds real conversations.** Remembers what you said yesterday, last week, last month. Brings it up naturally, not robotically.
- **Handles a room full of people.** Three or four people talking? It follows along, knows who's speaking to whom, and only joins in when it's actually being addressed.
- **Stays out of your way.** When two friends are catching up, it doesn't interrupt. It listens, learns, and waits.
- **Remembers visitors.** A friend stops by while you're out — when you come home, Kara-OS can tell you who came, what they wanted, and how they seemed.
- **Respects privacy by design.** Personal things stay personal. The owner (best friend) has full access to their own home. Visitors don't have their private moments shared without consent.
- **Surfaces what matters.** If a guest mentions something serious — something about their wellbeing — it knows the difference between gossip and a moment worth flagging.
- **Doesn't make things up.** When it doesn't know, it says so. No hallucinated memories, no invented relationships, no pretend recall.

---

## What makes it different

**Memory that actually means something.**
Most assistants reset every conversation. This one builds a real history with each person it knows. The longer you live with it, the more it understands you.

**Privacy as a foundation, not a feature.**
Kara-OS can know everything about your household and still keep secrets when keeping secrets is the right thing to do. Visitors are protected. Owners are trusted. The default is dignity.

**Presence over performance.**
It's not optimized to be impressive. It's optimized to be there. Quiet when you need quiet. Curious when you want to talk. Aware of mood, not just words.

---

## Status

The cognitive layer is real, working, and validated through 1,273 automated tests and live multi-person sessions. It runs locally — your home, your data. Hardware integration is the next chapter.

What you'd see in a live demo today: a robot that knows who's home, remembers what they care about, holds a conversation that actually goes somewhere, and handles a room of people without losing track.

---

## External validation

Tested against a published academic benchmark: *Speak or Stay Silent: Context-Aware Turn-Taking in Multi-Party Dialogue* ([Bhagtani et al. 2026, arXiv:2603.11409](https://arxiv.org/abs/2603.11409)). 1,287 multi-party conversations from the Friends corpus.

KaraOS scored **58.66% balanced accuracy** with no fine-tuning — competitive with **Gemini-3.1-Pro zero-shot (60.54%)** and ahead of every other zero-shot baseline the paper tested, including GPT-5.2, Llama-3.1-8B, Qwen2.5-7B, Mistral-7B, and GPT-OSS-20B. Fine-tuned models in the paper reach 65–72%, but require 120,000 labeled training examples — KaraOS gets there with prompt design alone.

What that 58.66% looks like in practice:

- **87.8% precision when speaking** — when KaraOS chimes in, it's right
- **2.4% false positive rate** — almost never barges into conversations it isn't part of
- **100% accuracy on bystander cases** — perfect at staying out of the way
- **97.6% silent-recall** — catches 98% of "stay quiet" moments

The model behind it is currently Llama-3.3-70B. KaraOS is model-agnostic by design — the same prompt and decision layer plug into any frontier LLM. Tomorrow's backbone could be Gemini, GPT-5, or anything else; the architecture is what makes the system, not the model.

Full results, comparison table, methodology, and reproducibility instructions: [`published-papers-tests/`](published-papers-tests/).

---

## The north star

Imagine three friends sitting down to dinner. Kara is in the corner, quiet. One friend asks the other how their week's been. Kara doesn't interrupt. Later, someone turns to Kara and asks what it thinks. It answers — warmly, briefly, like it's been listening the whole time. Because it has.

That's the goal. Not a smarter speaker. A companion.

---

## Get in touch

If you're building in this space — robotics, ambient AI, companion systems — and want to compare notes, reach out.

[www.linkedin.com/in/jaganniva001](https://www.linkedin.com/in/jaganniva001)
jagannivas.001@gmail.com
