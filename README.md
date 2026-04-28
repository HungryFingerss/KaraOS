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

The cognitive layer is real, working, and validated through 1,314 automated tests and live multi-person sessions. It runs locally — your home, your data. Hardware integration is the next chapter.

What you'd see in a live demo today: a robot that knows who's home, remembers what they care about, holds a conversation that actually goes somewhere, and handles a room of people without losing track.

---

## External validation — and what it taught us

The first time I put KaraOS through a published academic benchmark — *Speak or Stay Silent: Context-Aware Turn-Taking in Multi-Party Dialogue* ([Bhagtani et al. 2026, arXiv:2603.11409](https://arxiv.org/abs/2603.11409)) — it scored **58.66% balanced accuracy** on 1,287 samples from the Friends corpus. That beat 7 of 8 zero-shot LLM baselines the paper tested. So I wrote the README claim *"KaraOS is model-agnostic by design."*

A skeptic could push back: *was it KaraOS, or was it the 70B model underneath?*

I ran the same classifier on Qwen2.5-7B (the smaller model the paper benchmarked at **55.00%** zero-shot). KaraOS scored **52.32%** — actually 2.68 percentage points **worse** than the vanilla baseline.

The 70B was carrying the win. The classifier prompt had been tuned over 30+ live-canary iterations on Llama-3.3-70B; the accumulated complexity overwhelmed the smaller model. The "model-agnostic" claim was rhetoric, not architecture.

So I redesigned it.

The new classifier is a deterministic graph operation — **zero LLM calls in the classification path**. About 2,000 abstracted dialogue scenarios (drawn from external corpora: Cornell Movie-Dialogs, DailyDialog, EmpatheticDialogues; the Friends test set was held out from training) live in a separate database that survives factory reset. When a turn arrives, the system embeds it, looks up the nearest similar scenarios via cosine similarity, and aggregates their labels by outcome-weighted vote. Names and places are abstracted out (`{P1}`, `{LOC}`) before storage so the scenario library is privacy-clean and portable across deployments. The classifier learns from production use: when a user corrects KaraOS — *"no, I was talking to Friend 2"* — the graph updates itself, no retraining required.

Re-running the same Friends benchmark with this architecture: **64.56% balanced accuracy**. That beats both prior LLM-classifier baselines (Llama-3.3-70B: 58.66%, Qwen2.5-7B: 52.32%) and sits just below the paper's lowest fine-tuned model (Qwen2.5-7B fine-tuned: 66.60%, Qwen3-4B-Instruct fine-tuned: 65.12%) — fine-tuned models that required 120,000 labeled training examples and gradient-descent on model weights to reach those numbers.

Critically: this score now **doesn't depend on which LLM is the conversation brain**. Llama-3.3-70B, GPT-5, Gemini, Qwen-7B — the classifier behaves identically because it doesn't call any of them. That's the architecture made empirically real.

### What "no fine-tuning" honestly means

KaraOS doesn't modify model weights. It doesn't run gradient descent on labeled examples. It doesn't produce LoRA adapters. But it does use ~2,000 labeled scenarios as a retrieval corpus. This is **non-parametric learning** — distinct from fine-tuning, but it IS labeled training data, and you should know that. The Friends test set was strictly held out from training; the test integrity is intact. Both KaraOS and the paper's fine-tuned approaches use labeled data — the paper used 120,000+ rows + LoRA training; KaraOS uses 2,000 + retrieval lookup. Different mechanisms. Different scales. Both legitimate.

### What 64.56% looks like in practice for a home companion

- **88.9% precision when speaking** — when KaraOS chimes in, it's right ~4 times out of 5
- **96.4% silent recall** — almost never barges into conversations it isn't part of
- **15.2% overall SPEAK recall** — KaraOS misses many "should speak" moments. By design.

The overall 15.2% breaks down into:
- **31.4% on directly-addressed cases** (`SPEAK_explicit` — the in-scope category for KaraOS's design)
- **1.9% on implicit-flow cases** (`SPEAK_implicit` — out of scope by design; KaraOS targets explicit name-vocative addressing, not turn-taking inference from conversational drift)

The gap between 31.4% and 1.9% is structural, not a defect. A robot living in your home should err toward silence, not interruption. Missing a chance to chime in is recoverable; barging into a private conversation isn't.

Full benchmark journey, all three result runs, comparison tables, methodology, honest caveats, and reproducibility: [`published-papers-tests/results/RESULTS.md`](published-papers-tests/results/RESULTS.md).

For a high-level walkthrough of how the system actually works — identity, memory, privacy, conversation, the new graph classifier, safety — see [`ARCHITECTURE.md`](ARCHITECTURE.md).

---

## The north star

Imagine three friends sitting down to dinner. Kara is in the corner, quiet. One friend asks the other how their week's been. Kara doesn't interrupt. Later, someone turns to Kara and asks what it thinks. It answers — warmly, briefly, like it's been listening the whole time. Because it has.

That's the goal. Not a smarter speaker. A companion.

---

## Get in touch

If you're building in this space — robotics, ambient AI, companion systems — and want to compare notes, reach out.

[www.linkedin.com/in/jaganniva001](https://www.linkedin.com/in/jaganniva001)
jagannivas.001@gmail.com
