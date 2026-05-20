# P0.S7.5.2 — Plan v2 (architect's response to Plan v1 review)

**Date:** 2026-05-20
**Author:** architect
**Status:** Plan v2 — 4 architect-anticipated + 2 auditor-additional precision items addressed. Plus verbatim doctrine text for closure-pre-approved `### Canary-surfaces-real-gaps` elevation. Standing by for joint sign-off.

**Strict-industry-standard mode**: 5th application. Per `feedback_strict_industry_standard_mode.md`.

**Preceding documents:**
- `tests/p0_s7_5_2_audit.md` — Phase 0 (APPROVED)
- `tests/p0_s7_5_2_plan_v1.md` — Plan v1 (APPROVED with 4+2 precision items)
- This document — Plan v2 (final code contract)

---

## 1. Summary — 6 precision items + 1 doctrine elevation prep

| Item | Severity | Disposition |
|---|---|---|
| Precision 1 — D2 `text` variable in-scope grep | LOW | ✓ GREP-VERIFIED §2 |
| Precision 2 — D3 centroid cache vs recompute | LOW | LOCKED recompute + bench rationale §3 |
| Precision 3 — D4 per-word allowlist coverage + expansion procedure | LOW | LOCKED §4 |
| Precision 4 + A1 — D5 anti-pattern NUMBERED CONTRAST shape | MEDIUM | LOCKED §5 |
| A2 — D3 log strategy | MEDIUM | LOCKED verbose-by-design for canary 4 §6 |
| Doctrine elevation prep — `### Canary-surfaces-real-gaps` verbatim text for closure | high | LOCKED §7 |

All Plan v1 D-decisions (D1-D5) retain their contracts; Plan v2 refines specifics. Nothing in Plan v1 reversed.

---

## 2. Precision 1 — D2 `text` variable in-scope grep verification

Grep-verified `text` is in scope at `pipeline.py:7499` (D2 EDIT SITE):

| Assignment site | Path | Variable |
|---|---|---|
| `pipeline.py:6949` | Ambient probe path: `text, audio_buf = _ambient_text, _ambient_audio` | `text` ← STT from ambient probe |
| `pipeline.py:6959` | Main listen path: `text, _, audio_buf = await listen_and_transcribe()` | `text` ← STT from main listen |
| `pipeline.py:7134` (conditional, multi-speaker only) | Multi-speaker emit: `text, _preview, _labels = _format_multispeaker_transcript(_named_pairs)` | `text` ← combined transcript with `[Name]:` prefixes; system-name substring still matches |

**All three paths assign `text` BEFORE the routing dispatch block at `pipeline.py:7460+`** (well before D2's edit site at line 7499). Variable lifecycle is per-turn inner-loop iteration — same scope as `_cur_pid`, `audio_buf`, etc.

**Lock**: D2 reference implementation at Plan v1 §4.2 uses `text` correctly. No code change from Plan v1's contract.

---

## 3. Precision 2 — D3 centroid: lock recompute (NOT cache) + bench rationale

### 3.1 Decision: recompute centroid per `add_voice_embedding` call

**Why recompute over cache** (documented rationale per auditor's request — "so future readers don't refactor it as 'obvious optimization'"):

| Trade-off | Recompute (LOCKED) | Cache |
|---|---|---|
| Cost per gallery write | O(N) where N ≤ MAX_VOICE_EMBEDDINGS=50 — ~50 cosine sums + L2-normalize. Bench estimate <5ms on dev CPU (FAISS embeddings are float32 vectors of size 192 for ECAPA-TDNN). | O(1) read + bookkeeping cost on every write site |
| Bookkeeping complexity | None — pure function of current gallery state | Cache-invalidation on every gallery write (add, delete, prune, person rename, factory reset) — 6+ invalidation sites |
| Failure mode | None — recompute always returns current truth | Stale cache if any invalidation site is missed — silent gallery drift |
| Correctness guarantee | Trivially correct | Requires inverse-check discipline (P0.5 pattern) — enumerate all gallery-write sites in a tuple + AST scan |

**Rationale (locked in code comment)**:
> Centroid computed per add via `np.mean(embeddings, axis=0)` then L2-normalize. O(N≤50) is <5ms on dev CPU; negligible relative to the ECAPA embedding cost (~50ms) that already happened upstream. Cache-invalidation would require enumerating 6+ gallery-write sites (add_voice_embedding, delete_person, prune_old_strangers, prune_zero_value_stranger, prune_stale_stranger_voice, factory reset paths) and AST-asserting every site invalidates the cache — same inverse-check discipline as P0.5's `PAIRED_WRITE_METHODS`. Not worth it for ~5ms saved on a rare event. If profiling later shows centroid-recompute as a hot spot, revisit with bench numbers.

### 3.2 Implementation detail update for §5.2 of Plan v1

In `core/db.py::add_voice_embedding` D3 edit, comment block above the centroid-distance gate must include the §3.1 rationale verbatim so future readers see WHY recompute was chosen.

---

## 4. Precision 3 — D4 per-word allowlist coverage + expansion procedure

### 4.1 Per-word test coverage lock

Plan v1 §6.8 test 1 (`test_stt_filters_1_word_noise_keeps_allowlist`) MUST cover EACH of the 10 imperatives with a positive case. Parametrized form:

```python
@pytest.mark.parametrize("word,expected_pass", [
    # All 10 imperatives — bare form, lowercased, no punctuation
    ("yes", True), ("no", True), ("stop", True), ("help", True),
    ("okay", True), ("ok", True), ("sure", True), ("yeah", True),
    ("yep", True), ("nope", True),
    # Case variants (case-insensitive match)
    ("Yes", True), ("YES", True), ("Stop", True),
    # Punctuation suffixes (terminated → pass regardless of allowlist)
    ("You.", True), ("You!", True), ("You?", True),
    # Whisper artifacts (NOT in allowlist, no punctuation)
    ("You", False), ("Yeah", True),  # "Yeah" IS in allowlist — gotcha! distinguish from "You"
    ("Thank", False), ("Indeed", False), ("Absolutely", False),
    # Multi-word baseline (no filter applies; passes unconditionally)
    ("Yes I will", True), ("I don't know", True),
])
def test_stt_filters_1_word_noise_keeps_allowlist(word, expected_pass):
    ...
```

20+ parametrized cases. Total Plan v2 test count for D4 stays at 2 logical tests (test 1 + test 2), but test 1's parametrize expands the case coverage matrix.

### 4.2 Allowlist expansion procedure (documented)

**Criteria for adding a new word to `STT_KNOWN_IMPERATIVES`**:

A word can be added to the allowlist only when ALL of:
1. **3+ canary instances** of the same word being legitimately spoken AND filtered (evidence: terminal_output.md grep + user confirmation that the word was spoken as a real response, not Whisper noise)
2. **No semantic ambiguity** — word must be unambiguously a confirmation, denial, imperative, or terminator. Multi-meaning words (e.g., "right" can be agreement OR direction) require punctuation discipline instead.
3. **Documented in CLAUDE.md** — closure narrative banks the addition with the 3-instance evidence trail

**Where the procedure lives**: `core/config.py` STT_KNOWN_IMPERATIVES constant gets a docstring referencing this procedure.

```python
STT_KNOWN_IMPERATIVES: frozenset[str] = frozenset({
    "yes", "no", "stop", "help", "okay", "ok", "sure", "yeah", "yep", "nope",
})
"""1-word Whisper-allowlist for legitimate confirmation/denial responses.

Expansion criteria (P0.S7.5.2 Plan v2 §4.2):
  - 3+ canary instances of the word being legitimately spoken AND filtered
  - No semantic ambiguity (multi-meaning words → require punctuation instead)
  - Documented in CLAUDE.md closure narrative with the 3-instance evidence trail
"""
```

---

## 5. Precision 4 + A1 — D5 NUMBERED CONTRAST anti-pattern block

### 5.1 Plan v1 §7.3 said (rejected for prompt-engineering reasons)

Plan v1 §7.3 inserted the anti-pattern as an appended paragraph BEFORE `<<<END STRANGER IDENTITY>>>`. Block reading order: (1) self-intro rule → (2) triggers → (3) anti-ack → [Plan v1 inserts here] (4) question-shape anti-pattern. Transition jarring per auditor A1.

### 5.2 Plan v2 LOCKED — restructure block as two numbered rules

The ENTIRE existing block content gets restructured into a contrastive two-rule shape that LLMs follow more reliably:

```python
prompt += (
    "\n\n<<<STRANGER IDENTITY>>>\n"
    "The current speaker is still an anonymous stranger in the "
    "system (person_type='stranger'). Two rules govern your "
    "interaction with them, distinguished by what they say:\n\n"

    "RULE 1 — STATEMENTS about their identity (CALL `update_person_name`):\n"
    "If they STATE their name — even casually, even as an aside — you "
    "MUST call `update_person_name` to promote them from stranger to a "
    "named person.\n\n"
    "Concrete triggers (CALL the tool):\n"
    "  - \"My name is Lexi\"\n"
    "  - \"My name is Lexi by the way\"\n"
    "  - \"I'm Lexi\"\n"
    "  - \"Call me Lexi\"\n"
    "  - \"Name's Lexi\"\n"
    "  - \"Oh, I'm Lexi\"\n\n"
    "DO NOT just acknowledge the name conversationally (\"Nice to "
    "meet you, Lexi\") and move on. Acknowledge AND call the tool "
    "in the same turn. Without the tool call, their voice profile, "
    "conversation turns, and extracted facts stay orphaned from "
    "their real name — the system accumulates dangling shadow data "
    "instead of recognizing them on future visits.\n\n"

    "RULE 2 — QUESTIONS about your knowledge of them (DO NOT call `report_identity_mismatch`):\n"
    "If they ASK a question about whether YOU know them — they are "
    "NOT denying their own identity. Examples:\n"
    "  - \"Do you know me?\"\n"
    "  - \"Do you remember me?\"\n"
    "  - \"I know you very well but I'm not sure if you know me\"\n"
    "  - \"Have we met before?\"\n"
    "  - \"Do you recognize me?\"\n\n"
    "DO NOT call `report_identity_mismatch` on these. That tool is "
    "ONLY for the current speaker denying their OWN identity (e.g. "
    "\"I'm not Jagan\"). Respond conversationally — ask the stranger "
    "for their name: \"I don't think we've met — what's your name?\" "
    "If they then state their name in their reply, THAT triggers "
    "RULE 1 (call `update_person_name`).\n"
    "<<<END STRANGER IDENTITY>>>"
)
```

### 5.3 Why the contrastive structure works better for LLMs

- **Bilateral framing**: "Two rules, distinguished by X" primes the LLM to look for the distinguishing feature (statement-vs-question) before generating output
- **Symmetric DO/DO-NOT pattern**: Rule 1 has DO + DO-NOT; Rule 2 has DO-NOT + DO. Mirror structure helps the LLM internalize the contrast
- **Concrete examples on BOTH sides**: 6 triggers for Rule 1, 5 question-shapes for Rule 2 — equal weight signals equal importance
- **Forward reference between rules**: Rule 2 ends with "THAT triggers RULE 1 (call `update_person_name`)" — explicit causal chain teaches the LLM how the rules interact

### 5.4 Test surface impact

Plan v1 §7.8 test 2 (`test_stranger_identity_block_contains_question_anti_pattern`) updates to assert the numbered contrast structure:
- Block contains literal `"RULE 1"` AND `"RULE 2"` substrings
- Both rules present with their respective tool-call directives
- Forward reference `"THAT triggers RULE 1"` present in Rule 2

Test count unchanged at 2 for D5.

---

## 6. A2 — D3 log strategy: verbose-by-design for canary 4

### 6.1 Decision: keep verbose per-skip logs

Per auditor's framing: "The default-verbose path is fine if canary 4 needs the diagnostic data; future cleanup PR can de-noise."

**Lock**: D3 skip logs at Plan v1 §5.2 stay verbose:
- `[Voice] Skipped accum for {pid}: short utterance {N:.2f}s < {THRESHOLD}s`
- `[Voice] Skipped accum for {pid}: centroid-distance {N:.3f} < {THRESHOLD}`

### 6.2 Rationale

- Canary 4 will validate D3's bench-vs-real behavior. Per-skip logs let architect/developer see EXACTLY which utterances got filtered + which centroids triggered the gate
- Bug 1 (Jagan's low-score turns) was diagnosed in canary 3 PRECISELY because the reconciler-shadow logs were verbose — same discipline applied to voice accumulation
- If canary 4 surfaces log-spam (N >> expected), file follow-up cleanup PR that converts to: (a) once-per-session rate-limit OR (b) session-end counter surfaced in `[Health]` log

### 6.3 Closure narrative banking

Phase 4 closure MUST note explicitly: "D3 logs are verbose-by-design for canary 4 diagnostic value. If canary 4 surfaces log-spam, file a follow-up cleanup PR with counter-based approach (criteria: > 10 skip events per session)."

---

## 7. Doctrine elevation prep — `### Canary-surfaces-real-gaps` verbatim text for closure

Per auditor's directive at closure-pre-approval: "Closure narrative must include the verbatim doctrine text per the `### Phase-0-catches-wrong-premise` elevation pattern (operational rules block + '5 instances + discipline-stability evidence' framing + future-accumulation clause)."

Plan v2 LOCKS the verbatim text NOW so Phase 4 closure can paste it directly:

```markdown
### Canary-surfaces-real-gaps

Live multi-person canaries are a structural test of the cognitive
runtime against realistic usage. They reliably surface gaps that
spec-time grep + Phase 0 audit cannot reach — bugs that only
manifest under composed real-world conditions (timing, multi-pid
interaction, model non-determinism, hardware variation). Canary-
surfaced gaps are treated as REAL architectural findings, not as
canary noise. 5 of the spec-cycles after the P0.S7 family ship
crossed this threshold — the doctrine is now numbered.

**Track record (batting 5-for-5):**
- **P0.S7.2** — Cross-session memory retrieval gap. 2026-05-18
  canary: Jagan returned to fresh session, asked about cheese
  cookies recipe from prior multi-person room, brain confidently
  denied. Two-part fix surfaced (γ prompt + κ extraction).
- **P0.S7.3** — KAIROS timing. Canary-surfaced; banked as the 2nd
  instance toward this doctrine.
- **P0.S7.5** — Bundled-queue canary 2026-05-19 cluster: visitor
  alert nudge one-shot consumed before owner asked; VISITOR CONTEXT
  block didn't fire; brain confabulated "No one was here." 5
  D-decisions shipped.
- **P0.S7.5.1** — Canary 2 (2026-05-19) marker/metadata asymmetry:
  `_run_visitor_alert` writes `[visitor_name:unknown]` but metadata
  has `visitor_name="visitor"`; `update_visitor_alert_for_promoted_
  person` literal-substring replace silently no-op'd. Single
  D-decision lambda-replacement fix.
- **P0.S7.5.2** — Canary 3 (2026-05-20) multi-subsystem cluster:
  5 independent root causes across reconciler / pipeline / voice
  gallery / audio / brain prompt-blocks. 5 D-decisions shipped.

**Discipline-stability evidence:**

The architect held the strict-read line across non-canary cycles
that could have inflated the count prematurely (P0.S7.D-B was
deferral-rationale-expires, not canary; P0.S7.D-D was wrong-premise,
not canary; P0.S7.D-E was partial-falsification, not canary). That
discipline-stability gives the 5th-instance lock its integrity —
matches the `### Phase-0-catches-wrong-premise` elevation cadence.

**Operational rules:**

1. **Canary findings are real, not noise.** When a live canary
   surfaces a behavior gap, file a follow-up spec under strict
   mode. Don't dismiss canary failures as "model non-determinism"
   without grep-verified root-cause investigation.
2. **Multi-agent parallel investigation for multi-subsystem
   failures.** When a canary surfaces failures spanning ≥3
   subsystems, dispatch parallel investigation agents (per
   `feedback_strict_industry_standard_mode.md` §1 pre-mortem
   discipline). Synthesize findings into a single Phase 0 audit.
3. **Production-canary diff at closure.** Every canary
   terminal_output.md gets diffed against the prior canary as
   part of closure-narrative banking. Distinguish "new failure
   mode" from "regression" from "same failure" — different
   responses.

**Future accumulation:**

Future canary-surfaced instances continue to be banked under
this doctrine. The instance enumeration grows as new examples
accumulate; no new memory-note creation needed. If discipline-
stability remains intact, the doctrine matures rather than
requiring re-elevation at higher thresholds.

> P0.S7.5.2 Plan v2 §7 banking: this doctrine text is verbatim-
> sourced from Plan v2. Any future edit MUST preserve (a) the
> operational rules block (3 rules); (b) the "5 instances +
> discipline-stability evidence" framing; (c) the multi-agent
> parallel investigation rule (P0.S7.5.2-specific addition);
> (d) the production-canary diff rule. Future CLAUDE.md
> compactions MUST NOT drift these anchors.
```

This is the canonical doctrine text. Phase 4 closure pastes it verbatim into CLAUDE.md Architectural Disciplines section.

---

## 8. Plan v2 deltas from Plan v1 — summary

| Section | Plan v1 | Plan v2 |
|---|---|---|
| D2 `text` in-scope | Anticipated (Plan v1 §11) | **GREP-VERIFIED** §2 — three assignment sites confirmed |
| D3 centroid implementation | "compute current centroid" (Plan v1 §5.2) | **LOCKED recompute + bench rationale in code comment** §3 |
| D4 test coverage | "test 1 covers various cases" (Plan v1 §6.8) | **LOCKED 20+ parametrize cases covering each allowlist word + expansion procedure** §4 |
| D5 block content | Anti-pattern appended after existing content (Plan v1 §7.3) | **RESTRUCTURED as numbered contrast (Rule 1 / Rule 2) for LLM prompt-engineering** §5 |
| D3 log strategy | "skip logs emitted" (Plan v1 §5.2) | **LOCKED verbose-by-design for canary 4 diagnostic value** §6 |
| Closure doctrine text | Mentioned ("verbatim required") | **LOCKED full doctrine text** §7 (ready to paste into CLAUDE.md at Phase 4) |
| Test count forecast | 14-15 | UNCHANGED 14-15 (test 1 D4 expands cases but stays 1 logical test; test 2 D5 unchanged) |
| Effort | ~1.5 days | UNCHANGED ~1.5 days |
| Suite delta forecast | 2427 → 2441-2442 | UNCHANGED 2427 → 2441-2442 |

All deltas are tightenings, additions, or documentation. Nothing reversed.

---

## 9. Strict-industry-standard mode discipline self-audit (Plan v2)

| Check | Plan v2 status |
|---|---|
| Pre-mortem section exists per D-decision | ✓ (Plan v1 §3.6/§4.6/§5.6/§6.6/§7.6 stands; Plan v2 adds no new D-decisions) |
| Multi-direction trace exists per D-decision | ✓ (Plan v1 §3.4/§4.4/§5.4/§6.4/§7.4 stands) |
| Quality-gate checklist | ✓ (Plan v1 §3.7/§4.7/§5.7/§6.7/§7.7 stands; Plan v2 doesn't change any gate status) |
| Cross-spec impact analysis | ✓ (Plan v1 §8 stands) |
| Closure-audit step scheduled | ✓ (Plan v1 §9.1 Phase 4 stands; Plan v2 §7 locks the doctrine elevation banking) |
| Honest engineering on auditor framing | ✓ Plan v2 §3 documents recompute-over-cache decision with bench-style rationale (per auditor's specific ask); Plan v2 §5 restructures block per auditor A1 reasoning |

**Discipline status: APPLIED.** 5th consecutive artifact under strict mode. Discipline stabilizing into routine (per auditor's note "4 consecutive artifacts under strict mode now — discipline is stabilizing into routine").

---

## 10. Discipline-count predictions (Plan v2 final)

Unchanged from Plan v1 §9.3:

| Discipline | Pre-P0.S7.5.2 | Post-closure |
|---|---|---|
| Spec-first review cycle | 16-for-16 | **17-for-17** |
| Sub-pattern A | 5 | stays at 5 |
| Canary-finding tracker | 4 | **5th + DOCTRINE ELEVATION** with verbatim text per Plan v2 §7 |
| Auditor-Q5 (architect-memory) | 5 | **6th instance ON-TARGET** (14-15 within auditor's 12-16 estimate) |
| Strict-mode (auto-memory) | 4 applications | **5th application** at Plan v2 |
| Tripwires / developer-improves / induction / partial-falsification / spec-time grep | various | stays pending Phase 1-3 |

---

## 11. Next steps

1. **Auditor reviews Plan v2.** If approved → joint sign-off cleared.
2. **No Plan v3 anticipated.** All 6 precision items locked + doctrine text ready.
3. **Developer handoff** with:
   - `tests/p0_s7_5_2_audit.md` (Phase 0)
   - `tests/p0_s7_5_2_plan_v1.md` (Plan v1)
   - This document → `tests/p0_s7_5_2_plan_v2.md` (final code contract)
   - `CLAUDE.md` + `complete-plan.md`
4. **Phase 1 ships** (~4-5h): D1.b + D2 + D5 + 8 tests
5. **Phase 2 ships** (~3-4h): D3 + D4 + 6 tests
6. **Phase 3 ships** (~1h): optional E2E + closure narrative including:
   - Production-canary diff (canary 3 markers vs canary 4 expected)
   - Known Limitations subsection (D3 existing contamination, D2 word-boundary, D4 allowlist completeness)
   - Verbatim doctrine text from Plan v2 §7 pasted into CLAUDE.md Architectural Disciplines
7. **Phase 4 ships** (~0.5h): 5 deliberate-regression confirmations + memory updates
8. **RE-CANARY 4 IMMEDIATELY** on closure.
9. **On RE-CANARY 4 PASS**: combined Stage 2 PR fires — **P0.S7 family arc closes definitively**.

---

## 12. Reference documents (Plan v2 additions)

- Plan v1 reference §11 → Plan v2 addresses all 4 anticipated items
- Auditor handoff additions A1 + A2 → addressed §5 + §6
- `pipeline.py:6949, 6959, 7134` — `text` variable assignment sites (D2 in-scope confirmation §2)
- Existing P0.S7 Pending Work clauses re: `### Canary-surfaces-real-gaps` doctrine — final text locked §7

---

**Standing by for auditor sign-off on Plan v2 → developer handoff → RE-CANARY 4 IMMEDIATELY on closure.**

Plan v2 strictly tightens Plan v1; nothing reversed. All 6 precision items adopted (4 architect + 2 auditor). Doctrine text locked for closure paste. **Strict-mode 5th consecutive application** — discipline routine confirmed.
