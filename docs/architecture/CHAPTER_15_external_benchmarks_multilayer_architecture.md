> **CHAPTER 15 — External Benchmarks + Multi-Layer Architecture** | Sourced from `everything_about_system.md` §215-232 (verbatim mechanical extraction per Plan v2 §1.6 section-number stability invariant).

---

## 215. The Bhagtani et al. 2026 Paper and the Friends Test Set

The benchmark KaraOS is validated against:

> **Bhagtani, K., Anand, M., Xu, Y. C., & Yadav, A. K. S. (2026). *Speak or Stay Silent: Context-Aware Turn-Taking in Multi-Party Dialogue*. arXiv:2603.11409.**

The paper's question: in a multi-party conversation, given the recent history and a target speaker, will that speaker take the next turn (`SPEAK`) or will someone else (`SILENT`)? The paper benchmarks zero-shot LLMs (GPT-5.2, Gemini-3.1-Pro, Llama-3.1-8B, Qwen2.5-7B, Mistral-7B-Instruct, etc.), human judges, and LoRA-fine-tuned variants of the smaller models.

The test set we use is `friends/test/test_samples.jsonl` from the paper's released dataset — 1,287 samples drawn from the Friends sitcom corpus.

**Why Friends.** The Friends benchmark is heavy on `SPEAK_explicit` cases — situations where the target speaker is directly addressed by name ("Hey Ross, did you see the game?"). KaraOS's architecture targets exactly that case: explicit name-vocative addressing as the primary "should I speak?" signal. Friends is therefore the in-scope domain for KaraOS validation. AMI (workplace meetings) and SPGI (earnings calls) are in the paper but out-of-scope for KaraOS by design — they test implicit-flow turn-taking, which KaraOS's architecture deliberately doesn't target.

**The metric.** Balanced accuracy — `(recall_SPEAK + recall_SILENT) / 2`. Robust to class imbalance. The paper reports it; every comparison table in the public repo uses it.

**Test integrity.** Friends was strictly held out from the bootstrap data. Cornell + DailyDialog + Empathetic + hand_authored — none of those touch Friends. The graph classifier's retrieval pool has zero Friends contamination.

## 216. Run 1 — LLM Classifier on Llama-70B (58.66%)

**The system under test:** the Sessions-76-through-117 LLM-classifier path. Same prompt as production at the time, no test-specific tuning. Backbone: Llama-3.3-70B-Instruct-Turbo via Together.ai.

**Result:** 58.66% balanced accuracy on 1,287 Friends test rows.

| Category | Accuracy | n |
|---|---:|---:|
| `SILENT_no_ref` | 100.0% | 173 |
| `SILENT_ref` | 96.7% | 483 |
| `SPEAK_explicit` | 46.4% | 220 |
| `SPEAK_implicit` | 3.2% | 411 |

**Where this places KaraOS in the paper's table.** Above 7 of 8 zero-shot LLM baselines (Qwen3-8B 50.70%, Qwen3-4B 51.48%, Mistral-7B 52.87%, Llama-3.1-8B 54.21%, Qwen2.5-7B 55.00%, GPT-5.2 55.41%, GPT-OSS-20B 55.92%); below Gemini-3.1-Pro (60.54%) and the human baseline (63.75%); below all fine-tuned LoRA variants.

**This is the original public number.** It's what the LinkedIn video post and the original ARCHITECTURE.md cited. The number is real. What was wrong was the *interpretation* — the public claim "model-agnostic by design" did not survive the next experiment.

**Predictions file:** `karaos-public/published-papers-tests/results/friends_baseline_full_db/predictions_llama_70b.json`. Loadable by the paper's `metrics.py:compute_metrics()`; reproduces 58.66% to within rounding.

## 217. Run 2 — Multi-Backbone Falsifying Experiment (Qwen-7B, 52.32%)

**The setup.** Same KaraOS classifier prompt as Run 1 — verbatim, no changes. Different LLM backbone: Qwen2.5-7B-Instruct-Turbo via Together.ai. The paper benchmarks vanilla Qwen2.5-7B at 55.00% zero-shot. The falsifying question: does KaraOS's architecture lift Qwen-7B above 55.00%? If yes, the architecture is contributing real signal. If no, the original 58.66% was the 70B model carrying it.

**Result:** **52.32%** balanced accuracy. **2.68pp BELOW** the paper's vanilla Qwen-7B baseline.

The architecture didn't lift the smaller model — it actively *hurt* it.

| Category | Qwen-7B | Llama-70B | Δ |
|---|---:|---:|---:|
| `SILENT_no_ref` | 100.0% | 100.0% | 0.0pp |
| `SILENT_ref` | 98.8% | 96.7% | +2.1pp |
| `SPEAK_explicit` | **14.5%** | 46.4% | **-31.8pp** |
| `SPEAK_implicit` | 0.7% | 3.2% | -2.5pp |

The damage was concentrated in `SPEAK_explicit` — exactly the category KaraOS was supposedly best at. Qwen+KaraOS caught only 32 of 220 directly-addressed cases that Llama+KaraOS caught 102 of.

**Diagnosis.** The KaraOS classifier prompt had been tuned for 30+ live-canary sessions on Llama-3.3-70B and accumulated reasoning surface (taxonomy rules, counter-examples, INJECTION DEFENSE, structured-output contracts) that the larger model could absorb but the smaller one couldn't. Under prompt load, Qwen defaulted to `casual_conversation` even on samples with clear vocatives. Recall collapsed from 18.3% to 5.5% on overall SPEAK.

**This is a falsifying experiment that worked.** The "model-agnostic" public claim was rhetoric; the falsifier exposed it; the response was to redesign the architecture to be *structurally* model-agnostic. That redesign is the graph classifier.

**Limitation acknowledged.** The original spec called for three smaller backbones (Qwen-7B, Llama-3.1-8B, Mistral-7B) to give a stronger statistical case. Together.ai serverless access only allowed one (Qwen-7B). The collapse from 3-backbone to 1-backbone study is documented in `MULTI_BACKBONE_RESULTS.md`. N=1 is weaker than N=3, but the magnitude of the gap (collapse to *below* a paper baseline used as a low-end reference) makes the qualitative result well-supported.

**Predictions file:** `karaos-public/published-papers-tests/results/friends_multi_backbone/qwen_7b_predictions.json`. The result was published verbatim — uncomfortable findings don't get hidden.

## 218. Run 3 — Graph Classifier (64.48%)

**The system under test:** the Spec 2 graph classifier (`core.classifier_graph.classify_intent_graph`). No LLM in the classification path. Full 2,071-scenario production DB. E5 embeddings. Wilson aggregation.

**Result:** **64.48%** balanced accuracy on the 1,287 Friends test rows. Deterministic — same DB state, same number every run.

| Metric | Value |
|---|---:|
| Balanced accuracy | **64.48%** |
| `SPEAK` precision | 80.21% |
| `SPEAK` recall | 15.19% |
| `SILENT` precision | 54.16% |
| `SILENT` recall | **96.39%** |
| Macro F1 | 47.45% |

**Where this places KaraOS now.** Above the human baseline (63.75%). Competitive with the lowest fine-tuned LoRA variant (Qwen3-4B-Instruct fine-tuned: 65.12%, Qwen2.5-7B fine-tuned: 66.60%). And — this is the load-bearing part — the score *doesn't depend on which LLM is the conversation brain anymore*. The classifier makes zero LLM calls. Replace Llama-70B with Qwen-7B with GPT-5 with Gemini and Run 3's score stays at 64.48%, because the brain isn't involved in classification.

**The "no fine-tuning" honesty disclosure.** KaraOS does not modify model weights. It does not train LoRA adapters. It does not run gradient descent. The brain LLM ships as-is. KaraOS *does* use ~2,000 labeled scenarios as a retrieval corpus. This is **non-parametric learning** — distinct from fine-tuning, but it IS labeled training data, and the public framing acknowledges that explicitly. Both KaraOS and the paper's fine-tuned approaches use labeled data; the techniques and scales are different (paper: 120,000+ rows + LoRA training; KaraOS: ~2,000 + retrieval lookup).

**Predictions file:** `karaos-public/published-papers-tests/results/friends_baseline_full_db/predictions_graph_classifier.json`.

## 219. The 10-Run Scaling Ablation and the Inverse-Scaling Finding

**Origin.** Amit Yadav (paper co-author, Fern team lead) commented on Jagan's LinkedIn post about the Run 3 result, asking two ablation questions:

1. Does accuracy change with the number of abstracted scenarios?
2. What's the standard deviation across multiple runs with random subsets?

**Setup.** 10-run study, fully isolated from production:

- Stratified random subsets of the production DB at N=500, 1000, 1500 (3 random seeds each).
- Plus the deterministic full-DB run at N=2071.
- Stratification preserves the source-corpus ratio (Cornell 46.8%, DailyDialog 19.0%, Empathetic 14.4%, hand-authored 19.9%) at every N. No corpus over- or under-represented.
- Read-only access to the production DB. Override classifier path via `CLASSIFIER_DB_PATH_OVERRIDE` env var. Production DB mtime unchanged after the suite. Audit log unchanged. Zero production code edits.

**Result — inverse scaling.**

| N | Mean balanced acc | Std dev | Range |
|---|---:|---:|---|
| 500 | **0.6919** | ±0.0261 | [0.6644, 0.7270] |
| 1000 | 0.6835 | ±0.0075 | [0.6731, 0.6907] |
| 1500 | 0.6677 | ±0.0026 | [0.6646, 0.6709] |
| 2071 | 0.6448 | — | (deterministic) |

**The curve is monotonically decreasing.** Adding more scenarios *hurts* accuracy. The full DB scores 6.5pp below the best 500-scenario subset.

**Variance collapses as N grows.** ±2.6pp at N=500 → ±0.26pp at N=1500. The trend isn't a sampling artifact; it's robust.

**The proposed diagnosis.** k-NN cosine retrieval over heterogeneous-quality bootstrap data has a saturation point. At N=500 the retrieval pool is dense with high-signal scenarios per query. At N=2071 the pool includes lower-quality scenarios (mislabeled by the bootstrap LLM, too generic to discriminate, distribution-mismatched to Friends sitcom style) that crowd into top-K with confident-but-wrong votes.

**The open question — corpus-specific or fundamental?** Two competing explanations:

- **Friends-specific.** Cornell movie scenes (47% of bootstrap) are dramatic-style; they may match Friends queries by surface similarity but vote for wrong labels. AMI ablation would distinguish: AMI is closer to Cornell-style register, so we'd expect AMI's curve to flatten or improve with N.
- **Fundamental.** k-NN over noisy bootstrap data has this property regardless of test corpus. AMI would also show inverse scaling.

**AMI ablation queued.** Same 10-run shape, AMI test set. Cleanest experiment to disentangle the two explanations. Not yet run as of 2026-05-02.

**The architectural response.** Inverse scaling is what motivates the multi-layer roadmap (Part XXXV). Per-scenario learned reliability (Layer 1) plus auto-quarantine (Layer 5) directly attack the "noisy scenarios crowd into top-K" mechanism. Hierarchical retrieval (Layer 3) attacks the "wrong-corpus scenarios match by surface similarity" mechanism.

**Files.** Full data + methodology + isolation contract at `karaos-public/published-papers-tests/results/friends_scaling_ablation/`. 10 individual run JSONs, 10 individual run summaries, aggregate stats, README, METHODOLOGY, ABLATION_RESULTS.

## 220. The AMI 10-Row Smoke and Out-of-Scope Disclosure

A 10-row smoke test of KaraOS's classifier on the AMI test set was run and published — not as a result we're claiming, but as honest evidence of architectural mismatch.

**Result.** KaraOS predicted `SILENT` on all 10 rows. Per-class:

| Class | Count | Recall |
|---|---:|---:|
| Ground-truth `SPEAK` | 8 | 0.0% (0/8) |
| Ground-truth `SILENT` | 2 | 100.0% (2/2) |
| **Balanced accuracy** | — | **50.0%** |

**Why.** AMI samples are categorized primarily as `SPEAK_implicit` — the next speaker takes a turn without being directly addressed. KaraOS's architecture deliberately defaults to silence on those cases. Architectural target = explicit name-vocative addressing. AMI ≠ explicit-addressing. KaraOS is not designed to perform on AMI; the smoke test confirms it doesn't.

**Why it's published.** Silently omitting an unflattering result violates the public-repo principle of "no fake or padded data." Researchers reproducing KaraOS will want to know AMI is out-of-scope before they run it themselves and conclude something is broken.

**Files.** `karaos-public/published-papers-tests/results/ami_baseline/`. README documents the architectural mismatch. `result_summary.md` documents the 10-row scope. Predictions file is reproducible.

## 221. The `karaos-public` Repository Layout

The benchmark journey, prediction files, methodology docs, and live session logs are public at:

> https://github.com/HungryFingerss/KaraOS

Layout under `published-papers-tests/results/`:

```
results/
├── README.md                           ← test-by-test index
├── RESULTS.md                           ← full benchmark journey narrative
├── friends_baseline_full_db/            ← Run 1 (Llama-70B, 58.66%) + Run 3 (graph, 64.48%)
├── friends_multi_backbone/              ← Run 2 (Qwen-7B, 52.32% — falsifying experiment)
├── friends_scaling_ablation/            ← 10-run scaling study
│   └── individual_runs/                 ← all 10 per-run summaries + JSONs
└── ami_baseline/                        ← AMI smoke test (out-of-scope disclosure)
```

Each folder is fully self-contained: a README explaining what + why, METHODOLOGY explaining how, result narrative, raw prediction JSONs that any researcher can re-score with the paper's `metrics.py`.

The `terminal-logs/` folder at the root contains live KaraOS session logs:
- `2026_04_26_demo.md` — first public demo, single user, the LinkedIn video session
- `2026_05_01_multi_convo_canary.md` — 5-person canary, all participants consented to publication

The `classifier-seed/seed.jsonl` (~780KB) ships the full bootstrap data — 2,081 abstracted scenarios with labels and source attribution. No PII. Researchers can reproduce the full classifier from this seed plus the bootstrap pipeline.

**Honesty discipline:** every uncomfortable finding is published with diagnosis attached. The multi-backbone collapse, the inverse scaling, the AMI mismatch, the safety-critical contradiction-replacement bug from Session 105, the voice-gallery-growth bug — all in the open. The discipline isn't "publish only flattering results." It's "publish what you found and tell the truth about what it means."

---

# Part XXXV — Multi-Layer Classifier Architecture (FUTURE WORK)

## 222. Why This Is the Next Step

The Run 3 graph classifier scored 64.48% on Friends — better than Run 1, better than Run 2, structurally model-agnostic. The 10-run ablation revealed a real limitation: **adding more scenarios HURTS accuracy on Friends**. Inverse scaling. Variance collapses cleanly as N grows, so the trend is robust. The full 2,071-scenario DB scores 6.5pp below the best 500-scenario subset.

The user-stated goal for KaraOS is *"the brain for humanoid robots."* This means:
- Dump 10k+ scenarios into the system over time.
- The classifier should *not* degrade as N grows.
- The classifier should automatically filter low-quality scenarios from the retrieval pool.
- The architecture should learn from real production usage without human curation.
- Latency must stay bounded even at scale.
- When uncertain, abstain. Never vote with garbage.
- **Stay non-parametric.** Zero LLM in the classification path. Forever.

The Run 3 architecture meets some of these. It does *not* meet "scale-invariance" or "garbage immunity." The 10-run ablation directly disproves that property.

The multi-layer architecture is the engineering response. Six layers, four phases, each layer's purpose specified, each phase's deliverable defined. The end state is a retrieval system where adding 10k scenarios is *additive* (or at worst neutral), not destructive.

This Part is the architectural commitment, not the implementation. None of this has shipped. It's the explicit roadmap for the next ~3-6 months of classifier work.

## 223. The Six-Layer Architecture at a Glance

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│   Layer 6 — Provenance and lineage tracking                     │
│   (every retrieval is auditable)                                │
│                                                                 │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │                                                         │   │
│   │   Layer 5 — Active quality gating + auto-quarantine     │   │
│   │   (bad scenarios get filtered out automatically)        │   │
│   │                                                         │   │
│   │   ┌─────────────────────────────────────────────────┐   │   │
│   │   │                                                 │   │   │
│   │   │   Layer 4 — Multi-aspect scenario representation │   │   │
│   │   │   (each scenario annotated on multiple axes)    │   │   │
│   │   │                                                 │   │   │
│   │   │   ┌────────────────────────────────────────┐    │   │   │
│   │   │   │                                        │    │   │   │
│   │   │   │   Layer 3 — Hierarchical retrieval +   │    │   │   │
│   │   │   │   adaptive K + distance-weighted vote  │    │   │   │
│   │   │   │   (better routing of queries)          │    │   │   │
│   │   │   │                                        │    │   │   │
│   │   │   │   ┌─────────────────────────────────┐  │    │   │   │
│   │   │   │   │ Layer 2 — Outcome supervision   │  │    │   │   │
│   │   │   │   │ (the learning signal)           │  │    │   │   │
│   │   │   │   │                                 │  │    │   │   │
│   │   │   │   │ ┌────────────────────────────┐  │  │    │   │   │
│   │   │   │   │ │ Layer 1 — Per-scenario     │  │  │    │   │   │
│   │   │   │   │ │ learned reliability scores │  │  │    │   │   │
│   │   │   │   │ │ (TP/FP/net contribution)   │  │  │    │   │   │
│   │   │   │   │ └────────────────────────────┘  │  │    │   │   │
│   │   │   │   └─────────────────────────────────┘  │    │   │   │
│   │   │   └────────────────────────────────────────┘    │   │   │
│   │   └─────────────────────────────────────────────────┘   │   │
│   └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

Layers are stacked, not parallel. Layer 1 is the foundation. Layer 2 generates the data Layer 1 uses. Layer 3 consumes Layer 1's data to make better routing decisions. Layer 5 uses Layer 1's data to remove bad scenarios. Layer 6 logs everything for audit.

## 224. Layer 1 — Per-Scenario Learned Reliability

**The goal.** Every scenario in the DB has a *learned* trust score, not a hand-coded one. A scenario that consistently helps the classifier vote correctly = gold. A scenario that consistently votes wrong = garbage. The system learns which is which from real production usage.

**The data structure.** Add columns to `scenarios` table:

```sql
ALTER TABLE scenarios ADD COLUMN tp_count INTEGER DEFAULT 0;
ALTER TABLE scenarios ADD COLUMN fp_count INTEGER DEFAULT 0;
ALTER TABLE scenarios ADD COLUMN retrieval_count INTEGER DEFAULT 0;
ALTER TABLE scenarios ADD COLUMN net_contribution REAL DEFAULT 0.0;
ALTER TABLE scenarios ADD COLUMN last_retrieved_ts TEXT;
```

- `tp_count` — true-positive count: how often this scenario showed up in top-K for queries where the vote landed on the right label.
- `fp_count` — false-positive count: how often it showed up in top-K for queries where the vote landed on the wrong label.
- `retrieval_count` — total times this scenario appeared in top-K (= tp_count + fp_count + ambiguous + unsupervised).
- `net_contribution` — derived: `(tp_count - fp_count) / max(retrieval_count, MIN_RETRIEVALS)`. Computed lazily; cached.
- `last_retrieved_ts` — for staleness detection.

**The retrieval-time use.** Top-K aggregation includes `net_contribution` as a multiplier:

```
final_weight_for_label_X = sum(similarity × wilson_score × max(0, net_contribution))
```

Garbage scenarios with negative net contribution get clamped to zero weight. They're in the DB; they're just silenced.

**The dependency.** This layer requires *real outcome data* to be useful. Without Layer 2 firing, the counters stay at zero forever and `net_contribution` defaults to a smoothed prior.

**Phase 1 deliverable.** The schema change, the read-path multiplier (defaulted to 1.0 when counters are empty so behavior matches today), and infrastructure ready for Layer 2 to fill in counters.

## 225. Layer 2 — Outcome Supervision Wired Correctly

**The goal.** Generate the TP/FP signals Layer 1 needs. The dead-code path in `core.classifier_graph` (`record_pending_outcome` / `confirm_pending` / `revert_pending`) becomes alive.

**Three signal sources:**

**Source A — tool-execution outcomes.** When a tool fires successfully *and* the user doesn't correct it within 3 turns, the scenarios that voted for that intent get `tp_count++`. Implementation:
- Pipeline calls `record_pending_outcome(decision_id, scenarios_in_topK)` after every classification.
- The decision_id is held in a deque with a 3-turn aging window.
- After 3 user turns without a correction, `confirm_pending(decision_id)` fires → `tp_count++` for every scenario that voted for the winning label.
- If a correction or rejection arrives within 3 turns, `revert_pending(decision_id)` fires → `fp_count++` instead.

**Source B — explicit user corrections.** The existing correction loop (§210) already increments contradiction counts. Layer 2 broadens it: more correction patterns, more permissive natural-speech detection. Mining the canary archive logs for real correction phrasings is the data-driven approach.

**Source C — periodic offline validation.** A new script (e.g. `tests/score_scenarios.py`) runs the held-out test set with each scenario alternately included/excluded, computes per-scenario inclusion-impact, writes results to TP/FP counters. Runs nightly or on-demand. Acts as a "ground truth calibration" backstop independent of in-vivo signals.

**Crucial detail — disambiguating tool rejections.** The current pipeline logs four classes of tool rejection through the same `[Pipeline] Tool: X REJECTED` channel. Layer 2 needs them disambiguated:

| Rejection class | Layer 2 signal |
|---|---|
| Intent gate (classifier said wrong intent) | `revert_pending` → `fp_count++` |
| Privilege gate (intent right, person not authorized) | `confirm_pending` → `tp_count++` (graph was right; person was the issue) |
| Repeat guard (intent right, LLM looping) | `confirm_pending` → `tp_count++` (graph was right; LLM was the issue) |
| User-text grounding (extracted_value not in user_text) | `revert_pending` → `fp_count++` |

Disambiguation is a 1-2 session refactor of the rejection-logging code paths in `pipeline.py`.

**Phase 2 deliverable.** Wired outcome supervision (sources A + B). Source C is queued for after wiring.

## 226. Layer 3 — Hierarchical Retrieval, Adaptive K, Distance-Weighted Voting

**The goal.** Better retrieval, given the same scenarios. Three sub-improvements that stack:

**Sub-3a — Hierarchical retrieval.** Don't search across all 2,071+ scenarios. First, classify the query into a cluster (by source corpus initially, by embedding cluster eventually). Then top-K within that cluster only. Cornell movie scenes never crowd into Friends-sitcom queries because they're in a different cluster.

Initial implementation: cluster by `source_tag` (5 clusters: cornell / dailydialog / empathetic_dialogues / hand_authored / live_correction). Each cluster has a centroid embedding (mean of its scenarios' embeddings, normalized). At query time:
1. Embed the query.
2. Cosine-similarity vs each cluster centroid.
3. Pick the highest-scoring cluster.
4. Top-K retrieval scoped to that cluster.

Fallback path: if no cluster's centroid scores above some threshold (the query genuinely doesn't fit any cluster), fall back to flat top-K over all data. Gated by `HIERARCHICAL_FALLBACK_TO_FLAT=True` config flag, default ON.

**Sub-3b — Adaptive K.** Replace fixed K=5 (or K=10) with threshold-based: include all matches above similarity threshold T (e.g. T=0.65). Cap at K_max=15 to prevent vote dilution on too-generic queries. Calibrated empirically on a held-out validation slice.

If no scenarios clear the threshold, abstain. The classifier returns None and the gate code falls back to default-silent. Honest abstention beats voting with low-confidence garbage.

**Sub-3c — Distance-weighted voting.** Instead of equal-weight votes from top-K, weight by similarity. A 0.85 match counts ~2.7× a 0.30 match. Combined with Wilson scoring: `final_weight = similarity × wilson_lower × max(0, net_contribution)`. (Net contribution from Layer 1.)

**Phase 1 deliverable** (alongside Layer 1 schema). All three sub-improvements gated behind config flags (`HIERARCHICAL_RETRIEVAL_ENABLED`, `ADAPTIVE_K_ENABLED`, `DISTANCE_WEIGHTED_VOTING_ENABLED`), all default OFF. Test bridge runs with flags ON. Production stays current behavior until ablation validates the changes.

**Validation gate.** Run the staged ablation: 4 stages × 2 corpora (Friends + AMI) = 8 runs. Stage 0 = baseline. Stage 1 adds distance-weighted voting. Stage 2 adds adaptive K on top. Stage 3 adds hierarchical retrieval on top. Each stage's contribution measured separately. Don't proceed if any stage hurts either corpus.

## 227. Layer 4 — Multi-Aspect Annotation Rebuild

**The goal.** Each scenario annotated along multiple axes during bootstrap, not just one (intent_label). At retrieval time, similarity scores combined with per-axis weights — for `request_shutdown`, conversational_role and urgency matter most; for `casual_conversation`, emotional_register matters most.

**The axes (initial proposal):**
- `intent_label` (today)
- `conversational_role` — question / statement / command / reaction / meta
- `emotional_register` — neutral / urgent / playful / sarcastic / formal
- `speaker_relationship` — family / friend / professional / stranger
- `scene_type` — 1-on-1 / group / public
- `urgency` — low / medium / high
- `temporal_focus` — past / present / future / hypothetical

**The data shape.** Each scenario stored with multi-vector representation (one E5 embedding per axis-relevant abstraction of the text). Schema migration adds an `embeddings` JSON column or a separate `scenario_embeddings(scenario_id, axis, vector)` table.

**The retrieval shape.** Top-K candidate selection uses the standard intent-axis embedding. Reranking among top-K uses composite score = weighted geometric mean of per-axis scores. Per-intent axis weights initially uniform; eventually learned from Layer 2's outcome data.

**The cost.** This is the most expensive phase:
- Bootstrap pipeline rebuild — 5-7× the original Together.ai cost (~$25-100 per re-bootstrap).
- DB schema migration — additive but substantial.
- Retrieval logic rewrite.
- Re-bootstrap of all 2,081 existing scenarios with the new annotation pipeline.

**The unlock.** Multi-aspect retrieval is what makes "every scenario gold for *some* query" possible. A Cornell movie scene where someone shouts "shut it down" matches a Friends shutdown query because they share `conversational_role=command` + `urgency=high`, even though `emotional_register` differs. Single-vector retrieval can't make this distinction.

**Phase 4 deliverable.** Re-bootstrap with multi-aspect annotations + retrieval rewrite + per-intent axis weight calibration. Both Friends + AMI must improve before this phase ships. Old single-vector retrieval kept as fallback for ~1 month before full deprecation.

## 228. Layer 5 — Active Quality Gating and Auto-Quarantine

**The goal.** Garbage scenarios — those with persistently negative net_contribution — get automatically excluded from retrieval. The pool stays clean.

**The mechanism:**

```python
def maybe_quarantine(scenario):
    if scenario.retrieval_count < MIN_RETRIEVALS_FOR_QUARANTINE:
        return  # not enough data yet
    if scenario.net_contribution < QUARANTINE_THRESHOLD:
        scenario.active = 0
        audit_log("quarantined", scenario_id, reason=f"net_contribution={...}")
```

Runs nightly via the dream loop. Quarantined scenarios stay in the DB for audit (Spec 1's `active = 0` semantic) but are excluded from retrieval. Visible in the dashboard's "quarantine list."

**Reactivation.** If a quarantined scenario gets fresh positive evidence (e.g. a correction loop pointing at it as the right answer), set `active = 1` again, audit-log the reactivation, reset some counters. Reactivation is a meaningful signal — humans tagged it as right when the system thought it was wrong.

**The result.** Dump 10k scenarios in. Run the system for a few weeks. The garbage ones accumulate negative net_contribution. They quarantine themselves. The retrieval pool stabilizes on the high-quality subset. Adding more data is no longer destructive because bad data gets filtered before it votes.

**Operator visibility.** Session-end summary log expands: `[classifier_graph] N retrievals, M corrections logged, K scenarios crossed quarantine threshold this session, J reactivated`. Dashboard exposure: top-quality scenarios, quarantined scenarios, recent quarantines, recent reactivations.

**Phase 3 deliverable.** Quality scoring (lazy `net_contribution` computation), quarantine cron, reactivation logic, dashboard visibility.

## 229. Layer 6 — Provenance and Lineage

**The goal.** Every retrieval is auditable. When the system makes a wrong prediction in production, an engineer can trace back: which scenarios contributed, what their histories were, why they voted the way they did.

**What gets logged:**
- Per-retrieval: query text, abstracted text, query embedding hash, top-K scenarios with their similarities and Wilson scores and net_contributions, winning label, final confidence.
- Per-scenario edit: scenario_id, what changed (counter bump, label change, quarantine, reactivation), trigger source (correction loop, outcome supervision, manual override), timestamp.
- Per-correction-loop event: original turn text, corrected target, old prediction, new scenario inserted (if any).

**Where logged:**
- The existing `audit_log` JSONL gets richer entries.
- Per-retrieval logs go to a separate JSONL (`data/classifier_retrievals.jsonl`) — high-volume; rotated daily.
- A simple `bridge/scripts/explain_prediction.py` script can take a turn_id from a canary log and reconstruct the full retrieval path.

**Drift detection** runs on top of these logs:
- Daily aggregation of retrieval-pool composition (which scenarios are getting retrieved most, which never).
- Alerts when a previously-stable scenario's TP/FP rate suddenly shifts (could indicate a corpus-distribution shift in production traffic, or a bootstrap issue).
- Latency monitoring per retrieval stage (abstraction, embedding, k-NN, aggregation, total).

**Phase 5 deliverable.** This is operational tooling, not a single feature. It runs alongside everything from Phase 1 onward and gets richer over time.

## 230. Phase Sequencing — How the Layers Ship

The layers don't ship simultaneously. They have dependencies. Phase order:

**Phase 1 — Foundation (~3-5 days dev).** Layer 3 (hierarchical retrieval, adaptive K, distance-weighted voting) gated behind feature flags. Plus Layer 1 schema (TP/FP counters, net_contribution column, provenance fields) — the columns exist with default values, ready for Layer 2 to fill. Plus Layer 6 first cut (per-retrieval log JSONL, audit log enrichment). All flag-gated. Production stays current behavior. Test bridge validates the new code paths.

Validation gate: run the staged ablation (4 stages × 2 corpora = 8 runs). All three Layer 3 sub-improvements must stack without breaking either Friends or AMI. Promote flags from test to prod after stable for 1 week.

**Phase 2 — Learning signal (~1-2 weeks dev).** Layer 2 (outcome supervision wiring + correction-pattern broadening + offline validation script). Disambiguation of tool-rejection classes. Layer 1's counters start filling.

Validation gate: 2-4 weeks of canary sessions to let counters accumulate meaningfully. Wait period built in.

**Phase 3 — Quality gating (~1 week dev).** Layer 5 (auto-quarantine cron, reactivation, dashboard visibility). Builds on Phase 2's data.

Validation gate: deliberately seed a noisy 5k-scenario set into a non-production DB. Run for a month. Verify net_contribution distributions look right, quarantine threshold is calibrated.

**Phase 4 — Multi-aspect rebuild (~3-4 weeks dev + bootstrap cost).** Layer 4 (re-bootstrap with multi-axis annotation, retrieval rewrite, axis-weight learning).

Validation gate: ablation showing multi-aspect retrieval beats single-vector on at least 3 different test corpora.

**Phase 5 — Operational hardening (parallel/ongoing from Phase 1).** Layer 6 (provenance audit trails, drift detection, latency monitoring, dashboard). Not a single deliverable; runs alongside everything from Phase 1.

**Total estimated dev work.** 8-14 weeks of focused engineering, plus 1-2 months of real-world data accumulation between Phase 2 and Phase 3. The user has explicitly committed to this timeline.

## 231. The Non-Parametric Commitment

A standing architectural axiom for this work: **zero LLM in the classification path. Forever.**

Every design decision in Layers 1-6 must be evaluated against this constraint. Some implications:

- Reranking with a tiny LLM (Phi-3-mini, Qwen-2.5-1.5B) is *not* an option, even when it would solve a specific problem. The point of the architecture is model-agnostic at the classification layer.
- Multi-aspect annotation (Layer 4) IS allowed to use an LLM during *bootstrap* (re-running the bootstrap pipeline with richer annotation prompts). That's offline data preparation, not classification.
- Outcome supervision must come from rule-based signals (tool gates, correction regex patterns) not from LLM-based judgment.
- The "is this scenario relevant to this query?" similarity match must be E5 (or another local-deterministic embedder), never an LLM call.

The cost of this constraint: some clever solutions are off the table. Some performance ceiling sacrificed. The benefit: the classifier is a stable artifact independent of which LLM is the brain. KaraOS-on-Llama-70B and KaraOS-on-Qwen-7B and KaraOS-on-GPT-5 produce *identical* classifications because the classifier doesn't depend on the brain.

This is the property the multi-backbone falsifying experiment (§217) showed the LLM-classifier path didn't have. The graph classifier has it. The multi-layer architecture preserves it.

## 232. Honest Limitations of the Multi-Layer Plan

Some things the multi-layer architecture will NOT solve, even at full deployment:

**Catastrophic distribution shifts.** A query from a totally new conversation context the bootstrap never saw (e.g. a low-resource language, a domain like surgical handoff, a register like adversarial debate) will still abstain or fall back. Abstain is honest — but it means the system won't always have an answer. For these cases, expanding the bootstrap (adding new source corpora, new hand-authored scenarios) is the right response, not architectural.

**Latency at very large scale.** At 10k+ scenarios, brute-force cosine k-NN is going to be real even with hierarchical retrieval (each cluster might have 1-2k scenarios). At 100k+ we'll need an ANN library (FAISS, hnswlib). Phase 4's bootstrap rebuild is when we'd switch to ANN; we'll budget per-query latency carefully and accept the slight precision-at-K loss vs brute-force.

**Some things will always need a small reranker.** The non-parametric commitment forces every clever solution into the retrieval-and-aggregation paradigm. Some problems we'll WISH we could solve with a small reranker model — we'll have to solve them with smarter retrieval (multi-aspect, learned reliability, hierarchical routing) instead. Worth being honest with ourselves: this is a constraint with real costs.

**The bootstrap data is itself uneven quality.** No amount of retrieval-side cleverness fixes a corpus where some labels are wrong. Layer 5 (auto-quarantine) will silence the worst offenders, but it can't *un-train* a wrongly-labeled scenario back into a correctly-labeled one. The right response to that is investing in bootstrap quality — better LLM prompts during classification, multiple LLMs voting on each label, manual spot-checks of high-impact scenarios.

**The "garbage immune at scale" property is empirical, not theoretical.** Layers 1+2+5 should produce that property in practice. No theorem guarantees it. We'll know if it works by running the 10k-scenario stress test (Phase 3 validation gate) and watching what happens. If it doesn't work, we adjust.

This is honest engineering work, not a performance pitch. The goal is a system that's *better than today's*, scales *better than today's*, and surfaces its own failure modes honestly when they occur. Not a system that's perfect.

---

# Part XXXVI — P0 Correctness Hardening (P0.1 – P0.3 + P0.13)

