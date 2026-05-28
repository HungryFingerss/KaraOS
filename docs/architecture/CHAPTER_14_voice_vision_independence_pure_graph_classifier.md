> **CHAPTER 14 — Voice/Vision Independence + Pure-Graph Classifier** | Sourced from `everything_about_system.md` §198-214 (verbatim mechanical extraction per Plan v2 §1.6 section-number stability invariant).

---

## 198. Why the Rearchitecture

The pre-rearchitecture pipeline read voice state from inside vision code paths and vision state from inside voice code paths. `_resolve_actual_speaker` was the worst offender — a single 200-line function in `pipeline.py` that simultaneously checked face recognition, voice score, anti-spoof, scene candidates, dispute state, session age, and bootstrap credits, all to decide one thing: "whose session does this turn belong to?"

The cost of that coupling showed up in two specific failure modes:

1. **Silent voice-only stranger drops.** When a person whose face was off-camera spoke a brief phrase ("Hi Kara"), the routing logic's offscreen-floor anti-poisoning rule and the multi-segment-mismatch rule could BOTH match the same input — the cascade had no defined order, the first match won, and which rule "won" depended on import order. In live multi-party sessions this manifested as Lexi-class scenarios where a new speaker was attributed to the current holder for several turns until something else (face entering frame, longer utterance) broke the tie.
2. **Vision changes silently changing voice behavior.** A code edit to fix anti-spoof flicker would alter the timing of `_persons_in_frame` writes, which would in turn change the order in which `_resolve_actual_speaker` saw signals. Vision tests would pass but voice routing would silently degrade. We caught a half-dozen of these in 2026-04 through 2026-05; they were always hard to diagnose because the test suite couldn't isolate the bug to a single channel.

The architectural goal of `VOICE_VISION_INDEPENDENCE_PLAN.md` was to make voice and vision *truly independent*: each channel produces a structured claim about what it observed, and a separate **reconciler** module integrates the two claims into a routing decision. No channel reads the other's state. The reconciler is the only place where cross-channel logic lives.

This is shipped, in production, as of Session 122 (2026-05-01).

## 199. `voice_channel.py` — Pure Speaker Identification

`core/voice_channel.py` exposes one function: `identify_speaker(audio_buf, voice_gallery, *, utterance_duration, ...) -> IdentityClaim`.

The function is *pure* in the architectural sense:
- No imports from `pipeline.py`. (`grep "from pipeline" core/voice_channel.py` → empty.)
- No reads of any vision state, session state, or pipeline globals.
- No calls to `_face_in_frame`, `_persons_in_frame`, `_active_sessions`, etc.
- Returns a frozen `IdentityClaim` dataclass; never mutates shared structures.

The `IdentityClaim` shape:

```python
@dataclass(frozen=True)
class IdentityClaim:
    pid:                  Optional[str]      # matched person_id, or None
    confidence:           float              # ECAPA cosine similarity (CAN BE NEGATIVE)
    n_diarize_segments:   int                # 1 = single speaker; 2+ = multi-voice
    utterance_duration:   float              # seconds of actual speech
    reasoning:            str                # human-readable diagnostic
    raw_segment_scores:   tuple[tuple[Optional[str], float], ...] = ()
```

The hard rule (encoded in the module docstring): *if `identify_speaker` ever needs visual context to make a decision, that's a bug.* The function's only job is to describe what it heard. Routing decisions belong in the reconciler, not here.

The pipeline layer was rewritten to assemble the inputs (`audio_buf`, `voice_gallery`, `utterance_duration`) and call the function. Everything else — choosing whether to open a new session, whether to switch sessions, whether to drop the turn — moved to the reconciler.

## 200. `vision_channel.py` — Pure Scene Observation

`core/vision_channel.py` exposes one function: `observe_scene(...) -> PresenceState`.

Same architectural rules as the voice channel: no pipeline imports, no voice-state reads, no mutation of shared structures.

The `PresenceState` shape:

```python
@dataclass(frozen=True)
class PresenceState:
    visible_pids:               tuple[str, ...]    # face-recognized persons in frame
    unrecognized_track_ids:     tuple[str, ...]    # SORT tracks without recognition
    per_pid_confidence:         dict[str, float]   # face_match_conf per visible pid
    timestamp:                  float = 0.0        # frame timestamp
```

The vision channel emits *what is currently visible*, not *what was visible 30 seconds ago*. Stale state expiry happens upstream, before the channel is called. The reconciler's job is to act on the snapshot it gets.

A throttled shadow log in `_background_vision_loop` (once per 5 seconds) emits `[VisionChannel-Shadow] divergence:` lines when the new channel's `visible_pids` set differs from the legacy `_persons_in_frame` face-source entries. Used during the rollout to verify behavioral equivalence; kept on as a cheap regression guard.

## 201. `reconciler.py` — The 22-Rule Cascade

`core/reconciler.py` is the integration layer. It exposes one function:

```python
def reconcile(
    claim: IdentityClaim,
    presence: PresenceState,
    session: SessionState,
) -> RoutingDecision:
    ...
```

`SessionState` carries the pipeline's view of currently-open sessions (cur_pid, cur_person_type, n_active_sessions, voice_gallery_sizes, cur_holder_voice_n, now). `RoutingDecision` is the structured output: action ∈ {`current` | `switch_enrolled` | `new_stranger` | `ambiguous` | `short_utterance_skip` | `short_utterance_voice_mismatch` | `multi_segment_voice_mismatch` | `no_action`}, plus the rule that fired and a reasoning string.

Internally, `reconcile` runs a fixed cascade of 22 rules in a deterministic order. Each rule is a pure function that takes `(claim, presence, session)` and returns either `Optional[RoutingDecision]` (matched, here's the decision) or `None` (no match, try the next rule). The first rule that matches wins. If no rule matches, the cascade returns `RoutingDecision(action="no_action", reasoning="no rule matched (degenerate state)")` — a logged escape hatch that should never fire in practice.

The cascade is grouped by priority:

| Priority | Rules | What they handle |
|---|---|---|
| **P0** | `_p0_short_utterance_*`, `_p0_pure_noise_hold_current` | Sub-MIN_UTTERANCE_SECS audio: hard-mismatch drops, ambiguous-zone drops, pure-noise hold-current |
| **P1** | `_p1_confident_voice_switch` | Voice score above SPEAKER_SWITCH_THRESHOLD → confident switch to matched pid |
| **P2** | `_p2_face_assist_switch`, `_p2_voice_face_agree` | Mid-range voice score with face co-presence agreement |
| **P3** | `_p3_self_match_below_floor`, `_p3_above_self_match` | Holder's own voice score relative to self-match floor (poisoning protection) |
| **P4** | `_p4_pyannote_vouched_stranger`, `_p4_new_stranger_low_match`, `_p4_voice_ambiguous_*`, `_p4_single_segment_mismatch`, `_p4_multi_segment_mismatch` | Below-threshold voice scores: open new stranger, drop turn, or hold ambiguous |
| **P5** | `_p5_no_session_new_stranger` | No active session: any real signal opens a stranger session |

The order is intentional and load-bearing. P0 fires before P1 because a 0.4-second utterance scoring 0.85 against the holder is still too short to attribute reliably (the high score is artifactual from acoustic prior rather than identity match). P3's self-match floor fires before P4's mismatch handling because we want "current holder said something quiet" to route differently from "stranger said something we can't match."

Every rule is independently unit-tested. The cascade is integration-tested by passing in pinned `(claim, presence, session)` fixtures captured from real canary failure modes (the negative-cosine bug fixture is one of these — see §202).

## 202. The Negative-Cosine Bug and Why It Mattered

Through Phase 4 cutover (Session 122), four cascade rules used `claim.confidence == 0.0` (exact equality) as a precondition for handling "no enrolled match" cases:

- `_p4_pyannote_vouched_stranger` — pyannote saw 2+ voices, ECAPA didn't match
- `_p4_new_stranger_low_match` — single segment, score below threshold
- `_p4_voice_ambiguous_no_candidates` — ambiguous, empty room
- `_p4_voice_ambiguous_with_candidates` — ambiguous, populated room

The implicit assumption was that on gallery miss, `voice.identify()` returns `(None, 0.0)`. That assumption was *wrong*. The actual behavior of `core.voice.identify`:

```python
def identify(audio, voice_gallery, threshold, sample_rate=MIC_SAMPLE_RATE):
    emb = embed(audio, sample_rate)
    if emb is None or not voice_gallery:
        return None, 0.0   # Only path returning exact 0.0 — embedding failed

    best_id, best_score = None, -1.0
    for person_id, profile_emb in voice_gallery.items():
        sim = float(np.dot(emb, profile_emb))   # cosine sim — CAN BE NEGATIVE
        if sim > best_score:
            best_score = sim
            best_id = person_id

    if best_score >= threshold:
        return best_id, best_score
    return None, best_score   # Returns ACTUAL cosine, often negative
```

ECAPA-TDNN embeddings are L2-normalized. Cosine similarity between two anti-correlated speakers (different gender, accent, register) is routinely *negative* — values like -0.05, -0.08 are normal when an unknown speaker is compared against an enrolled gallery they don't match. Only when the embedding step itself fails does `identify()` return exactly `0.0`.

In the 2026-05-01 5-person canary, this surfaced as: Lexi (unknown speaker) said "Hi Kara, can you tell me what is the escape velocity of Earth?". Pyannote returned 2 segments (correct). ECAPA scored Lexi's voice at -0.05 against Jagan's gallery (correct — definitively not Jagan). Reconciler ran the cascade. Every P4 rule's `confidence == 0.0` precondition failed because confidence was -0.05 not 0.0. No rule matched. Cascade returned `no_action`. Lexi's utterance was silently dropped.

The fix (Session 122):
- `_p4_pyannote_vouched_stranger`: `claim.confidence == 0.0` → `claim.confidence <= 0.0`. Catches both the no-signal case (0.0) and the anti-correlated case (negative).
- `_p4_new_stranger_low_match`: condition rewritten as `claim.confidence < VOICE_RECOGNITION_THRESHOLD AND claim.confidence != 0.0`. Negative scores route to new_stranger; exact-zero (embedding failed) falls through to ambiguous handling.
- `_p5_no_session_new_stranger`: rewritten as "any real signal" — `claim.confidence != 0.0 OR len(presence.unrecognized_track_ids) > 0`.
- The two `_p4_voice_ambiguous_*` rules deliberately kept the `== 0.0` check. Negative is a *confident* "not-this-speaker" signal and routes to new_stranger; exactly 0.0 is "no signal at all" and routes to hold-current or ambiguous depending on scene candidates.

Two new regression tests added: `test_p4_pyannote_vouched_stranger_negative_confidence` and `test_p4_new_stranger_low_match_negative_confidence`. Pinned fixtures from the canary log.

The lesson for future channel work: when a function's return value is "actual cosine similarity," do not assume any particular value (zero, positive, bounded) without verifying the source. ECAPA-TDNN's contract permits negatives; the cascade rules now respect that.

## 203. Phase 4 Cutover and Known Follow-Ups

### 203.1 The cutover flag

`ROUTING_USE_RECONCILER = True` in `core/config.py` (Session 121). When true, `pipeline.run` consumes the reconciler's `RoutingDecision` directly. When false, the legacy `_resolve_actual_speaker` still runs and the reconciler runs in shadow alongside (logging divergences but not driving behavior).

The shadow phase (Phase 3) ran for 48+ hours of normal use before the cutover. The divergence log was empty — every decision the reconciler would have made matched what `_resolve_actual_speaker` made. That's the validation that allowed the flip.

### 203.2 The legacy function is preserved

`_resolve_actual_speaker` in `pipeline.py` still exists. It's unreferenced by the production routing path under `ROUTING_USE_RECONCILER = True`. Phase 5 (cleanup, deferred) will delete it once we have another month of stable reconciler operation.

### 203.3 Test count

The Phase 1–4 work added approximately 40 unit/integration tests for the channels and the reconciler cascade (`tests/test_voice_channel.py`, `tests/test_vision_channel.py`, `tests/test_reconciler.py`). Pre-Phase-1 test count was 1336; post-Phase-4 is 1374.

### 203.4 Known follow-up — voice gallery growth bug for promoted voice-only strangers

Session 94 added bootstrap-credit replenishment so engaged strangers could grow their voice profile to maturity (20 samples). The condition includes `person_type == 'stranger'`. After a voice-only stranger is promoted via `update_person_name` ("My name is Lexi"), the promotion chain flips `person_type` to `known`. The replenishment condition stops firing. Subsequent voice samples are refused with `voice_n=4, bootstrap=0, no witness` because the only paths to accumulation are face-witness (blocked, voice-only), mature-voice-self-match (blocked, below threshold), or bootstrap (blocked, exhausted and no longer eligible).

In the 2026-05-01 canary, Lexi stayed at 4/20 samples and John stayed at 2/20 samples for the full 50-minute session. Voice routing accuracy degrades as a result — every future session they join, they re-enter via switch_enrolled against their stunted profile, can't accumulate, and remain stunted forever.

Fix queued (architect's recommendation: add a `voice_only_origin` session-dict flag set at engagement-gate pass when no face was witnessed; replenishment fires when the flag is True AND voice_n < MATURE, regardless of `person_type`; flag clears on first face-witness event).

### 203.5 Known follow-up — Phase 5 cleanup

Once reconciler operation is stable for ~1 month: delete `_resolve_actual_speaker`, remove voice writes to `_persons_in_frame`, introduce a `_voice_speakers_active: dict` for voice-only presence (replacing the source-tagged dual-purpose use of `_persons_in_frame`).

---

# Part XXXIII — The Pure-Graph Intent Classifier

## 204. Why We Replaced the LLM Classifier

Sessions 76 through 117 iterated on an LLM-based intent classifier — a separate Together.ai call per turn that emitted a structured JSON sidecar (`turn_intent`, `extracted_value`, `confidence`, `reasoning`). The classifier's prompt accumulated complexity (taxonomy rules, counter-examples, INJECTION DEFENSE, GREETING-vs-ASSIGN, IMPLICIT-ADDRESSING) over 30+ live-canary sessions. By Session 117 it was a 3000-token prompt that worked well on Llama-3.3-70B and was load-bearing for production routing decisions (rename gates, shutdown gates, mismatch detection).

Two problems forced the replacement:

**Problem 1 — Model dependence.** A falsifying experiment in 2026-04-27 ran the same classifier prompt on Qwen2.5-7B (a paper-baseline model in Bhagtani et al. 2026). KaraOS-on-Qwen-7B scored 52.32% balanced accuracy on the Friends test set — *2.68pp below* the paper's vanilla Qwen-7B baseline of 55.00%. The 70B was carrying the architectural lift; the prompt complexity overwhelmed the smaller model. The "model-agnostic" public claim was rhetoric, not architecture. Diagnostic detail in `karaos-public/published-papers-tests/results/friends_multi_backbone/MULTI_BACKBONE_RESULTS.md`.

**Problem 2 — Cost and latency.** Every turn made a second Together.ai call (the sidecar) in addition to the brain stream. Per-turn cost roughly doubled. P99 latency grew because the sidecar's response had to arrive before tool gates could be applied.

The replacement architecture, specified in `SPEC_001_classifier_graph.md` (Spec 1, data layer) and `SPEC_002_classify_intent_graph.md` (Spec 2, classification layer), removed the LLM from the classification hot path entirely. No Together.ai call. No Ollama call. No model inference of any kind. Classification became a deterministic graph operation: abstract the input → embed locally → cosine k-NN against a stored scenario database → aggregate label votes. Same output shape as the LLM classifier (turn_intent + extracted_value + confidence + reasoning); zero model dependence.

Run 3 of the Friends benchmark, with this architecture: **64.48% balanced accuracy.** Above Run 1's LLM-classifier number, above the paper's human baseline (63.75%), competitive with the lowest fine-tuned LoRA model (Qwen3-4B-Instruct fine-tuned: 65.12%) — without modifying any model weights, without running gradient descent.

## 205. Spec 1 — Bootstrap and the Scenario Database

The classifier needs a database of labeled scenarios to retrieve against. Spec 1 covers how that database is built, populated, and maintained.

**Source corpora** (the bootstrap inputs):

| Corpus | Rows | Share | Why this corpus |
|---|---:|---:|---|
| Cornell Movie-Dialogs | 968 | 46.8% | Largest single source of multi-party dialogue with explicit speaker turns; broad register coverage |
| DailyDialog | 393 | 19.0% | Closer to casual conversation register; short polite exchanges |
| EmpatheticDialogues | 298 | 14.4% | Adds emotional / vulnerable conversational shapes; therapy-style |
| hand_authored | 412 | 19.9% | KaraOS-specific scenarios written from the development log's bug classes (Sessions 71–117 — the canary failure modes the LLM classifier got wrong) |
| live_correction | (varies) | (small) | Added at runtime via the user-correction loop (§210) |
| **Total active** | **2,071** | **100%** | (snapshot 2026-04-30) |

Friends, AMI, and SPGI (the Bhagtani paper's test corpora) are *deliberately excluded* from bootstrap to preserve test-train integrity. Mixing them in would collapse the benchmark.

**Pipeline shape:**

1. Parse raw corpus → extract dialogue turns with metadata.
2. Filter to "intent-relevant" turns (drop pure-acknowledgment, pure-noise).
3. Pass each candidate turn through a Together.ai classifier prompt (one-shot, JSON-mode, 70B) that assigns one of 12 intent labels.
4. Abstract: replace named entities with placeholders. Names → `{P1}`, `{P2}` (registry-first then spaCy NER fallback). Places → `{LOC}`. Numbers, times, and most concrete content kept intact.
5. Embed via `intfloat/multilingual-e5-large-instruct` — 1024-dim, L2-normalized.
6. Write `scenario_id`, `intent_label`, `text` (abstracted), `embedding`, `source_tag`, plus provenance metadata to `data/classifier_scenarios.db`.
7. Quality pass: drop scenarios where the LLM's confidence was below threshold; deduplicate near-identical embeddings.

The bootstrap is a one-time-ish operation. Re-running it from scratch costs ~$5-15 in Together.ai spend. The seed JSONL (everything in step 6 except embeddings, which can be regenerated locally) is published at `karaos-public/published-papers-tests/classifier-seed/seed.jsonl` — 2,081 rows, ~780KB, no PII, with full source attribution.

## 206. `classifier_db.py` — Schema and Audit

`core/classifier_db.py` is the read/write layer over `data/classifier_scenarios.db`.

**Core table — `scenarios`:**

```sql
CREATE TABLE scenarios (
    scenario_id           TEXT PRIMARY KEY,
    intent_label          TEXT NOT NULL,
    text                  TEXT NOT NULL,             -- abstracted
    embedding             BLOB NOT NULL,             -- 1024-dim float32
    source_tag            TEXT NOT NULL,             -- cornell / dailydialog / empathetic_dialogues / hand_authored / live_correction
    source_version        TEXT,                       -- for re-bootstrap reproducibility
    source_ref            TEXT,                       -- pointer back to original corpus row
    initial_confidence    REAL DEFAULT 0.5,
    confirmation_count    INTEGER DEFAULT 0,
    contradiction_count   INTEGER DEFAULT 0,
    active                INTEGER DEFAULT 1,         -- 0 = quarantined
    created_at            TEXT NOT NULL,
    last_seen_at          TEXT,
    extracted_value       TEXT                        -- new in Spec 2 — captured slot value when present
);
```

`active = 0` means quarantined: the scenario stays in the DB for audit but is excluded from retrieval. This is how the system removes bad-influence scenarios without losing them entirely. Quarantine is currently triggered manually; auto-quarantine is part of Phase 3 of the multi-layer roadmap (§228).

**Audit log — `audit_log` (JSONL append-only):**

Every mutation — scenario creation, confirmation, contradiction, quarantine, reactivation, label change — appends a JSON row. This file is intentionally separate from the SQLite DB so it survives DB corruption and can be reasoned about externally.

**Schema versioning:** `schema_migrations` table tracks every applied migration. Additive migrations only; no destructive schema changes.

**Daily snapshots:** `data/classifier_snapshots/YYYY-MM-DD.db` — automatic daily backups, 30-day retention. If a bug causes corruption, restore from the previous day.

## 207. Spec 2 — `classify_intent_graph()` Anatomy

`core/classifier_graph.py` exposes `classify_intent_graph(text: str, history: list = None, ...) -> dict`. The function returns the same shape as the legacy LLM classifier (`turn_intent`, `extracted_value`, `confidence`, `reasoning`) so it's a drop-in replacement at call sites.

**Internal flow:**

```
classify_intent_graph(text="Hey Kara, what's the weather?")
   │
   ▼
1. abstract(text)
   │   "Hey {P0_AI_NAME}, what's the weather?"
   │   (registry-first replacement: known person/AI names; then spaCy NER for unmatched)
   ▼
2. embed(abstracted_text)
   │   → 1024-dim float32 vector via E5-large-instruct (local on GPU)
   ▼
3. classifier_db.cosine_topk(query_embedding, k=10)
   │   → top 10 nearest scenarios by cosine similarity (brute-force; no ANN index yet)
   ▼
4. Wilson lower-bound aggregation over the top-K
   │   → for each unique intent_label in top-K, compute Wilson score
   │     using confirmation_count / (confirmation_count + contradiction_count)
   │     adjusted by initial_confidence + similarity weight
   ▼
5. Return {"turn_intent": best_label, "confidence": wilson_score, ...}
```

The whole flow is deterministic — same input + same DB state → same output, every time. The only randomness sources are E5's tokenizer (deterministic given inputs) and SQLite's row order (we sort explicitly to remove ambiguity).

**Abstraction step in detail.** The two-pass abstraction in `core/abstraction.py`:
- **Pass 1 — Registry.** Look up known persons (best_friend, household members, current session participants) and the AI name; replace exact matches with `{P0_AI_NAME}`, `{P_LEXI}`, etc. This is the high-precision pass.
- **Pass 2 — spaCy NER.** Run spaCy's `en_core_web_sm` model on the remaining text. Replace entities tagged `PERSON` with `{PN}` placeholders, `LOC`/`GPE` with `{LOC}`. Times, numbers, and percentages stay unabstracted (they carry intent-relevant signal — "shut down at 5pm" is different from "shut down" alone).

The `{P0_AI_NAME}` placeholder is a deliberate stable token. When the user changes the AI's name from "Kara" to "Atlas", queries about "Atlas" still match against scenarios stored as `{P0_AI_NAME}, what's the weather?` — the system is name-agnostic.

## 208. Three Modes — `shadow`, `primary`, `retired`

Controlled by the `GRAPH_CLASSIFIER_MODE` config flag in `core/config.py`. Three values:

**`shadow` (current default).** Both classifiers run in parallel on every turn. The LLM classifier drives behavior — its output is what tool gates consume. The graph classifier runs alongside, logs its prediction via `[Intent] shadow divergence: graph='X' (conf=0.43) vs llm='Y' (conf=0.95)` when the two disagree, and writes nothing to production state. This is the validation phase: we accumulate divergence data to calibrate the graph's reliability before flipping production over.

**`primary`.** Graph classifier drives behavior. LLM classifier still runs as a fallback for low-graph-confidence cases (`graph_confidence < GRAPH_PRIMARY_CONFIDENCE_FLOOR`, default 0.55). When graph is confident, we use it; when not, fall back to LLM. This intermediate mode lets us fail-safe through the rollout.

**`retired`.** Graph classifier drives behavior. LLM classifier is not called. If the graph abstains (confidence below `GRAPH_ABSTAIN_THRESHOLD`, default 0.40), the gate code falls back to default-silent behavior. This is the steady-state target.

The cutover discipline mirrors the voice/vision rearchitecture: **never all-at-once.** Ship in shadow, observe divergences for 1-2 weeks of live use, target <5% divergence rate on routine traffic before flipping to primary. Primary mode validates over weeks before flipping to retired. The old `_classify_intent` LLM classifier stays in the repo as the safety net during primary mode.

**Current status (2026-05-02):** mode is `shadow`. The 2026-05-01 canary captured 15 shadow divergences over ~50 minutes of multi-party conversation. In every divergence, the LLM classifier was right and the graph classifier was wrong (graph confidences ranged 0.41-0.68; LLM confidences ranged 0.85-0.95). This tells us the graph is genuinely uncertain on these cases and the architecture is doing the safe thing. The graph isn't yet ready for primary mode — calibration is too low. The multi-layer architecture work (Part XXXV) is what's expected to close this gap.

## 209. Wilson Lower-Bound Aggregation

The aggregation step in `classify_intent_graph` doesn't take a simple top-K majority vote. It uses **Wilson lower-bound** scoring for each candidate label.

**Why.** A scenario with 1 confirmation and 0 contradictions has empirical confirmation rate 1.0 — but that's based on a single observation. Should it count more than a scenario with 50 confirmations and 5 contradictions (rate 0.91)? Naive majority vote says yes; Wilson lower-bound says no.

**The formula** (95% confidence interval, lower bound):

```
n = confirmation_count + contradiction_count
p = confirmation_count / n   if n > 0 else initial_confidence
z = 1.96   (95% CI)
denominator = 1 + z²/n
center     = p + z²/(2n)
margin     = z * sqrt(p*(1-p)/n + z²/(4n²))
wilson_lower = (center - margin) / denominator
```

When n is small, the margin term dominates and `wilson_lower` is pulled toward 0 even if `p = 1.0`. This is the "small sample, low confidence" effect that makes the system robust against single-confirmation events skewing the graph.

**In aggregation:**
- Top-K = 10 nearest scenarios.
- For each unique `intent_label` in top-K, sum the (similarity × wilson_lower) contributions across all matching scenarios.
- Best label wins; its summed weight becomes the classifier's `confidence` output.

Scenarios with no outcome data (`confirmation_count == 0 AND contradiction_count == 0`) use `initial_confidence` as a smoothed prior — typically 0.5 or 0.85 depending on source (hand-authored: 0.85; bootstrap-LLM-classified: 0.5). This prevents fresh scenarios from getting zero weight just because they haven't been validated yet.

## 210. The Correction Loop and Why It's Currently Dormant

The classifier graph has a designed-in mechanism for users to teach it: explicit corrections.

**The flow:**
1. Brain emits a response based on the classifier's intent prediction.
2. User says something matching a correction pattern: "no, I meant to say X", "I was talking to Lexi, not you", "no actually...".
3. `core.classifier_graph.handle_correction(text)` parses the correction and looks up the previous turn's prediction via `_pending_outcomes` (a deque of recent decisions awaiting outcome).
4. The scenarios that voted for the wrong label on turn N-1 get their `contradiction_count` incremented.
5. If a real correction *target* (e.g. "Lexi") is extracted from the user's correction phrase, a new scenario is INSERTED into the DB:
   - `text` = the original turn N-1 text, re-abstracted with the target's role baked in
   - `intent_label` = `direct_address_to_person`
   - `source_tag` = `live_correction`
   - `initial_confidence` = 0.85
6. The pipeline returns `("continue", None)` early — no brain response. (The user shouldn't get an apology. They corrected the AI; the AI internalizes silently.)

**Pattern bank.** `_DEFAULT_CORRECTION_PATTERNS_TEMPLATE` in `classifier_graph.py` contains ~14 regex patterns covering shapes like:
- "no, I meant X"
- "I was talking to X, not you"
- "you, not X"
- "I meant ask X"

**Why it's currently dormant.** The 2026-05-01 5-person canary log: zero corrections fired across ~50 minutes of conversation. Multiple instances where a user *did* correct the AI in natural speech ("no, ask Jagan about that") didn't match any of the 14 regex patterns and so didn't trigger the correction loop. The correction-detection regex bank is too narrow for natural correction phrasings.

Real-world correction patterns include things like:
- "actually, ..."
- "no, ..."
- "I meant ..." (without "no")
- Repeating the question with a different addressee in the next turn
- "wait, ..."
- Implicit corrections (the user just rephrases the question without acknowledging the mistake)

Broadening the regex bank is part of Phase 2 of the multi-layer roadmap (§225). Mining the canary archive logs for natural correction phrasings is the data-driven approach.

## 211. Outcome Supervision — The Dead Code Path

Spec 2 includes a second learning signal beyond explicit corrections: **outcome supervision**. The idea is that when a tool fires successfully (e.g. `update_person_name` accepts a rename and the user doesn't correct it within 3 turns), the scenarios that voted for that intent should get `confirmation_count` incremented. When a tool gets rejected by content/intent gates, scenarios get `contradiction_count` incremented.

The infrastructure exists. `core.classifier_graph` exposes:
- `record_pending_outcome(decision_id, scenarios_that_voted)` — call when a decision is made
- `confirm_pending(decision_id)` — call N turns later if the decision was right
- `revert_pending(decision_id)` — call N turns later if the decision was wrong
- `age_pending_outcomes()` — sweep expired entries (3-turn window, currently)

**The pipeline does not call `confirm_pending` or `revert_pending` anywhere in production.** The `decision_id` returned by `record_pending_outcome` is discarded immediately. The 3-turn aging window expires every entry without supervision.

This is dead code. It's not removed because it's the planned wiring point for Phase 2 of the multi-layer roadmap (§225). Wiring it up correctly requires disambiguating four classes of tool rejection:

| Rejection class | Signal for graph |
|---|---|
| Intent gate (classifier said wrong intent) | NEGATIVE (graph was wrong) |
| Privilege gate (intent right, person not authorized) | POSITIVE (graph was right) |
| Repeat guard (intent right, LLM looping) | POSITIVE (graph was right) |
| User-text grounding (extracted_value not in user_text) | NEGATIVE (graph was wrong) |

The pipeline currently logs all four through the same `[Pipeline] Tool: X REJECTED` channel with different reason strings. Disambiguating them is a 1-2 session refactor. After that, outcome supervision can be wired and the graph starts learning from real production usage.

## 212. E5 Embeddings — Local on GPU

The classifier uses `intfloat/multilingual-e5-large-instruct` — a 1024-dim multilingual embedding model from Microsoft Research / E5 series.

**Why this model:**
- Multilingual (the system is currently English-only but the architecture is language-extensible)
- Instruction-tuned (handles "represent this query for retrieving similar dialogue scenarios" prompting cleanly)
- L2-normalized output (cosine similarity reduces to dot product — fast)
- ~1.4GB on disk; ~3.9s to load on consumer GPU; ~50ms per inference after warmup
- Permissive license (commercial-OK, attribution)

**Loading.** Lazy at first call. The Spec 2 contract was "local on GPU" — `_get_e5_model()` checks for `cuda` availability and loads with `device="cuda"`. Falls back to CPU only if no GPU is available (degraded; not a production target).

**Boot warmup.** The first inference call after model load takes ~4.6 seconds (vs. ~50ms steady state) because of CUDA kernel initialization, tokenizer warmup, and model graph trace. The architecture commitment is to do this warmup at pipeline boot — not on the first user turn — so the first conversation never sees the cold-load penalty. Status: queued for the same fix bundle as the voice-gallery-growth fix.

**Embedding determinism.** E5 is deterministic given identical input bytes. We don't seed any randomness in the inference path. The same query produces the same embedding every call.

## 213. Privacy and Abstraction at the Embedding Layer

The classifier never sees real names, real places, or other PII at the embedding layer. The abstraction step (§207) replaces all of those with placeholders before embedding. This is a privacy invariant the architecture enforces structurally:

- The `data/classifier_scenarios.db` file contains only abstracted text. If you `SELECT text FROM scenarios LIMIT 100`, you'll see strings like `"{P0_AI_NAME}, can you tell me about {LOC}?"` — not "Kara, can you tell me about Tirupati?".
- The `seed.jsonl` published in `karaos-public/` contains only abstracted text. It's distributable as a public artifact without PII review because there's no PII in it.
- Every `live_correction` scenario added at runtime goes through the same abstraction step before being written.

The abstraction is *not* a security boundary — a determined attacker who could read the DB and the registry could potentially de-abstract some entries. It is a privacy-by-default discipline that makes accidental PII leakage structurally impossible at the embedding layer.

## 214. Latency Profile and the Boot-Warmup Decision

Per-turn classifier latency breakdown (steady state, post-warmup):

| Stage | Time | Notes |
|---|---|---|
| Abstraction (registry + spaCy NER) | ~5ms | spaCy `en_core_web_sm` is small and fast |
| Embedding (E5 on GPU) | ~50ms | Single 1024-dim vector |
| Cosine top-K against ~2,071 scenarios | ~3ms | Brute-force; no ANN index |
| Wilson aggregation | <1ms | Top-10 sum of weights |
| **Total steady-state** | **~60ms** | |

**Cold start** (first inference after pipeline boot):

| Stage | Time | Notes |
|---|---|---|
| E5 model load to GPU | ~3.9s | One-time per process |
| First embedding call (kernel init) | ~700ms | CUDA warmup |
| **Total cold start** | **~4.6s** | The first user turn after pipeline boot eats this |

The architectural decision: warm at boot. Add `_classify_intent_graph` to the pipeline's preload sequence (after Whisper, Kokoro, ECAPA, MiniFASNet, EmotionAgent). Make one dummy call with a sentinel input. The user's first conversation never sees the cold-load penalty.

This fix is queued in the same bundle as the voice-gallery-growth fix (§203.4) and the session-end classifier summary log (which adds module-level counters and a shutdown-time summary line for retrieval count, divergence count, correction count, etc.).

After warmup is in place, the per-turn 60ms cost is invisible — it overlaps with the brain stream's much larger latency (TTFT ~500ms+ for the brain stream itself).

---

# Part XXXIV — External Benchmark Validation

