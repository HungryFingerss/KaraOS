> **CHAPTER 12 — Privacy + Rooms + Recent Work** | Sourced from `everything_about_system.md` §150-176 (verbatim mechanical extraction per Plan v2 §1.6 section-number stability invariant).

---

## 150. The Four-Tier Privacy Model

### 150.1 What the tiers mean

```python
# core/config.py
PRIVACY_LEVELS: frozenset[str] = frozenset({
    "public",        # visible to all persons in the household
    "personal",      # visible only to the person_id who owns the fact
    "household",     # visible to best_friend (+ future flagged roommates)
    "system_only",   # never surfaced to any user (internal inferences)
})
PRIVACY_LEVEL_DEFAULT: str = "personal"  # fail-closed default
```

Four tiers, by increasing restrictiveness:

- **`public`** — anyone in the household can see it. Names, country-of-origin, top-level relationship roles. Low risk if leaked.
- **`personal`** — only the fact's owner sees it (the `person_id` associated with the row). Specific locations, moods, confided worries, medical, dietary preferences, private opinions. Fail-closed default — a novel attribute we haven't classified yet is treated as personal rather than public.
- **`household`** — best_friend sees it; non-best-friend (visitors, strangers) does not. Presence facts ("visited_household"), visit topics, `preferred_ai_name`, relationships revealing the owner's social graph. This tier exists to hide the owner's social map from visitors while still letting the owner recall it.
- **`system_only`** — never surfaced to *any* user. Voice/face embedding hashes, bootstrap credit counters, internal diagnostic signals. The owner sees everything *except* this tier — the facts are plumbing, not conversational content.

### 150.2 Why `frozenset`, not a list or enum

Closed-world property. The Phase 3A contract relies on `_classify_privacy_level` returning a value that is *in* `PRIVACY_LEVELS` — if an LLM hallucinates `"secret"` or `"room_private"`, we reject it and fail closed to `PRIVACY_LEVEL_DEFAULT`. A list or set mutable at runtime would let a well-meaning dev add a tier without wiring the visibility clause, and the failure would be silent (retrieval returns no rows matching the new tier because no clause selects it). The frozenset-and-regression-test pair makes that failure loud.

Regression tests in `test_pipeline.py::test_privacy_levels_exhaustive_and_frozen` assert (a) the exact 4-tier set, (b) the frozenset type, and (c) `PRIVACY_LEVEL_DEFAULT ∈ PRIVACY_LEVELS`. Any future edit that adds or renames a tier must also update the test — intentional friction.

### 150.3 Why `'personal'` as default

When we can't classify an attribute (classifier failure, no LLM client supplied), we must pick a tier. The three candidates were:

- `public` — leaks novel attributes cross-person. Fails *open*.
- `personal` — owner-only; wrong but safe. Fails *closed*.
- `system_only` — hides from the owner too. Too restrictive — an owner asking "what do I like to eat?" would see nothing.

`personal` is the smallest safe default. It matches the principle that every access-control system converges on: *when in doubt, owner-only*.

## 151. The Static Map and the Classifier

### 151.1 `PRIVACY_LEVEL_STATIC_MAP` — the fast path

About 22 attributes are pre-classified in `core/config.py`. Examples (tier in parentheses):

```
  name                         public
  from_country                 public
  relationship_to_jagan        household   (reveals owner's social graph)
  relationship_to_best_friend  household
  preferred_ai_name            household
  lives_in_household           household
  visited_household            household   (presence fact)
  discussed_topic              household   (topic area, not content)
  lives_in                     personal    (specific town, identifiable)
  from_state                   personal    (narrower; NB comment)
  works_at                     personal
  job_title                    personal
  current_mood                 personal
  current_activity             personal
  dietary_preference           personal
  confided_concern             personal
  health_condition             personal
  voice_embedding_hash         system_only
  face_embedding_hash          system_only
  bootstrap_credits            system_only
```

Two reviewer refinements live inside this map as comments you should not normalise away:

- **`relationship_to_*` moved public → household (Session 95).** The reasoning: "Lexi is Jagan's classmate" reveals *Jagan's* social graph, not just Lexi's. A visitor asking "what's your relationship to Jagan?" would reveal Jagan's social info if kept public.
- **`from_country='India'` stays public; `from_state='Andhra Pradesh'` stays personal.** Nationality is public; narrower location is identifiable. The comment in config explicitly warns future maintainers not to "normalise" them to the same tier.

### 151.2 The LLM classifier — `_classify_privacy_level`

For novel attributes (anything not in the static map), `ExtractionAgent` calls `_classify_privacy_level(entity, attribute, value, http=...)`. The layered lookup is:

1. **Static map** — O(1) dict check, zero I/O. Most facts hit this.
2. **Process-lifetime cache** (`_privacy_classifier_cache: dict[str, str]`) — once an attribute has been classified, subsequent facts with the same attribute short-circuit.
3. **LLM fallback** — `_ask_privacy_llm` via the shared `_call_llm_chat` helper with `response_format={"type": "json_object"}`, `max_tokens=150`, `timeout=5s`, `temperature=0.1`. The prompt (`_PRIVACY_CLASSIFIER_SYSTEM`) defines the 4-tier semantics + 5 rules + 5 verbatim examples that anchor the classifier to the right tier on canary-level edge cases.

Fail-closed policy: LLM failure, malformed JSON, valid JSON but invalid tier (e.g. `{"level": "secret"}`), or `http=None` all return `PRIVACY_LEVEL_DEFAULT='personal'` **without writing to cache**. Caching a failure would pin an attribute at the wrong tier on a single transient blip.

**Why cache by attribute, not by `(entity, attribute)`.** The tier is a property of *what* the fact is, not *whose* fact it is. `health_condition` is personal for everyone; no per-entity variation. Caching by `(entity, attribute)` would bloat the cache and pay LLM calls we don't need to.

### 151.3 The classifier prompt (verbatim structure)

`_PRIVACY_CLASSIFIER_SYSTEM` in `core/brain_agent.py` is a minimalist system prompt with:

- **TIERS block** — one sentence per tier explaining semantics.
- **RULES block** — 5 rules, most load-bearing being "When in doubt, choose personal (fail-closed)" and "Facts revealing owner's social graph → household".
- **EXAMPLES block** — 5 verbatim `{entity, attribute, value} → {level, reasoning}` examples pulled from canary scenarios. The reviewer's reasoning: abstract rules drift, concrete examples stick.

The prompt hash (12-char sha256 of the system string) is tracked in every Phase 5 eval bench run under `metadata.classifier_prompt_hash`. A change in the hash marks a calibration boundary — drift analysis should not compare metrics across the boundary without acknowledging the change. See Part XXX §190.

## 152. `_visibility_clause` — The SQL Composer

### 152.1 Signature

```python
def _visibility_clause(
    requester_pid:  str,
    best_friend_id: "str | None" = None,
) -> tuple[str, list]:
```

Returns a SQL `WHERE`-clause fragment and its bind params. Callers compose it under an outer AND:

```python
base_where    = "entity = ? AND invalidated_at IS NULL"
vis_where, vis_params = _visibility_clause(requester_pid, best_friend_id)
full_where    = f"{base_where} AND ({vis_where})"
full_params   = [entity, *vis_params]
```

The clause is always wrapped in outer parens by the caller for composition safety — `AND ((clause_a) OR (clause_b))` reads cleanly with the visibility expression as a sibling of the base filter.

### 152.2 The two branches (Session 95 3A.4.6 — simplified)

```python
if best_friend_id and requester_pid == best_friend_id:
    # Owner: unconditional access except system_only.
    return ("(privacy_level != 'system_only')", [])

# Non-owner: public + own personal. No household, no cross-person personal,
# no system_only.
clauses = [
    "privacy_level = 'public'",
    "privacy_level = 'personal' AND person_id = ?",
]
return (" OR ".join(f"({c})" for c in clauses), [requester_pid])
```

Two branches, one policy each. That's it.

### 152.3 The invariants

- **`system_only` is NEVER in the result.** The owner branch excludes it via `!= 'system_only'`; the non-owner branch has no predicate that matches it. A regression test (`test_visibility_clause_never_permits_system_only`) asserts this against 3 different requester shapes.
- **Owner sees household.** Via the unconditional owner branch.
- **Owner sees other people's personal.** Via the unconditional owner branch. This is the 3A.4.6 simplification — see §154 for why.
- **Non-owner never sees household.** Their clause has no household predicate.
- **Non-owner sees only their own personal, never anyone else's.** The `AND person_id = ?` qualifier enforces ownership.

## 153. `query_knowledge_for` — Owner-Aware Retrieval

### 153.1 Signature

```python
# core/brain_agent.py — BrainDB
def query_knowledge_for(
    requester_pid:  str,
    best_friend_id: "str | None",
    *,
    entity:    "str | None" = None,
    attribute: "str | None" = None,
    limit:     int         = 20,
) -> list[dict]:
```

Returns a list of 6-column dicts: `{entity, attribute, value, confidence, person_id, privacy_level}`, sorted by `confidence DESC, created_at DESC`, limited by `limit`.

Internally it composes `_visibility_clause` with `invalidated_at IS NULL` and `(valid_until IS NULL OR valid_until > now)` (so expired / invalidated rows don't leak).

### 153.2 Why a dedicated method, not `get_active_knowledge + filter_facts_for_requester`

`filter_facts_for_requester` was the 2-tier post-hoc filter used before Phase 3A. Session 95 3A.4 replaced the 2-step call at the canary site (`_make_memory_search_fn`) with the single `query_knowledge_for` call:

- **One SQL round-trip instead of two.** Composition happens at query time.
- **No silent over-read.** Under the old pattern, a 2000-row `get_active_knowledge` query would load all facts into memory and then filter. Under the new pattern, the filter runs in the database.
- **Auditability.** Grepping for `query_knowledge_for` gives you all the owner-aware retrieval sites; grepping for `filter_facts_for_requester` gave you a fuzzier landscape of half-migrated call paths.

### 153.3 The canary wiring (`_make_memory_search_fn` in `pipeline.py`)

As of Session 95 3A.4, **one** retrieval site is wired to the visibility clause:

- `pipeline._make_memory_search_fn` — the factory that returns the per-call `search_memory` tool function. It calls `BrainDB.query_knowledge_for(requester_pid=asker_pid, best_friend_id=_bf_id, entity=subject_entity, ...)`.

The other three retrieval sites (`find_knowledge_id`, `_cull_stale_knowledge` query side, `ProactiveNudgeAgent.run_cross_person_inference`) remain on the legacy pipeline *for now*. The plan (deferred to Phase 3A.5) is to replicate the pattern once the canary site has passed enough live multi-person sessions. Reason: single-site canary is cheaper to roll back, and the per-person `search_memory` call is where the owner-vs-visitor split matters most.

### 153.4 Legacy row migration (`BrainDB.__init__`)

When the `privacy_level` column was added, two one-shot `UPDATE` statements run on every process start:

```
UPDATE knowledge SET privacy_level = 'personal' WHERE privacy_level IS NULL;
UPDATE knowledge SET privacy_level = 'personal' WHERE privacy_level = 'private';
```

Both converge on `PRIVACY_LEVEL_DEFAULT='personal'`. The first catches rows from any hand-edit path; the second migrates the legacy 2-tier `'private'` rows (pre-Session 95) to their 4-tier equivalent. Both print the rowcount when non-zero and silently no-op on subsequent starts once rows have migrated. Without the second UPDATE, every legacy owner-only fact would vanish even from its own owner under the new `_visibility_clause` (which has no predicate for `'private'`).

A regression test seeds raw `'private'` + NULL rows via a direct SQLite connection, opens via `BrainDB` (triggering the migration), then asserts both rows are readable by the owner through `query_knowledge_for`.

## 154. The Owner-Access Model (3A.4.6 Simplification)

### 154.1 The first design — three-tier overlap

The initial Phase 3A.4 plan gave best_friend access to `public + household + own personal`. Visitors' `personal` facts were hidden even from the owner. Rationale: "even the owner shouldn't see a visitor's private confidences."

### 154.2 The user correction

Mid-session, the user pushed back:

> best friend should have all the access right, any person personal or anything in the entire system... bestfriend have the access for everything.

This reframes the model: the best_friend is the *household owner*, not a mere household member. In the owner's home, the owner sees everything happening in the system. The reviewer's read: "This IS the intended user experience."

### 154.3 The final model — two-branch exclusion

Implemented in Session 95 3A.4.6:

- **Owner** (`requester_pid == best_friend_id`) sees every tier except `system_only`. One clause, zero params.
- **Non-owner** sees `public + own personal`. Two clauses, one param.

Architectural implications:

- `household` is no longer a tier the owner explicitly sees — it's included via the catch-all. The tier's purpose narrows to "non-owner exclusion" — hide it from visitors while letting it flow to the owner via the catch-all.
- Visitor confidences (e.g. "Lexi's thesis anxiety") surface to the owner. The owner uses conversational judgment on what to mention. The system is not the gatekeeper of what the owner is allowed to know in their own home.
- If a future need arises to hide *specific* content even from the owner, that's a new `confidential` tier — a distinct schema addition, not a re-complication of best_friend access.

### 154.4 Less nuance, fewer edge cases

Future engineers reasoning about privacy need only remember: *owner sees everything; others see only their own + public.* That's the invariant. The alternative ("best_friend has public + household + their own personal") had more branches and required the engineer to reason about each tier's owner semantics separately.

## 155. Write-Path Migration to Four Tiers (3A.4.5)

### 155.1 The problem flagged in 3A.4

After 3A.4 wired the visibility clause at the canary site, the canary would have silently failed in a misleading way: **the old `_privacy_level(attribute)` helper was still writing `'public'` / `'private'` on every new row**, which meant Jagan couldn't even see his own just-stored facts (`'private'` matches no predicate in the new clause). The canary would have looked like the visibility clause was broken rather than the write path.

### 155.2 The fix (Option B — classify at agent layer)

- Added `privacy_level: str = PRIVACY_LEVEL_DEFAULT` field to the `Extraction` dataclass.
- `ExtractionAgent.extract()` calls `await _classify_privacy_level(entity, attribute, value, http=self._http)` before constructing each `Extraction`. Static-map hits are free; novel attrs hit the LLM classifier exactly once and cache.
- Sync-path agents (`RoutineAgent` for `typical_arrival_hour` / `typical_visit_duration_min`, `store_temporal_fact` for `current_feeling`) hard-code `privacy_level="personal"` — small closed set of attributes that are all personal by definition. Avoids threading async through sync code.
- `BrainDB.store_knowledge` INSERT uses `e.privacy_level` directly. No auto-classification in the DB layer.
- `promote_shadow_to_confirmed` raw INSERT includes `privacy_level=PRIVACY_LEVEL_DEFAULT`.
- `_privacy_level(attribute)` deleted entirely. Grep-verified zero remaining callers.

### 155.3 Why Option B and not Option A

Option A was "classify at DB write time — `store_knowledge` calls `_classify_privacy_level` internally". Rejected because:

- The DB layer shouldn't be doing async LLM calls. It's a thin persistence layer by design.
- Sync agents would need async refactoring to flow through.
- Testing becomes harder — every `store_knowledge` test needs an LLM mock.

Option B puts the classification at the agent layer, where the LLM call is natural, and keeps the DB dumb.

## 156. The `<<<CROSS-PERSON PRIVACY>>>` Block — Two Variants

### 156.1 Why a prompt block even with the visibility clause

The visibility clause decides *what the brain sees*. The prompt block decides *what the brain says about what it sees*. They are complementary — neither alone is sufficient. A brain with restricted context can still phrase its refusal badly; a brain with owner-full-access can still over-share inappropriately; a brain with neither flies blind.

### 156.2 The refusal variant — `<<<CROSS-PERSON PRIVACY>>>`

Fires when the session's `person_type != 'best_friend'`. Shape (verbatim from `core/brain.py` `_build_system_prompt`):

```
<<<CROSS-PERSON PRIVACY>>>
When asked about other people's sessions in the room or while the asker
was away:

1. Share what's in your retrieved memory context. If `search_memory` or
   the room context block returned cross-person facts (names, topics,
   presence), speak to them naturally.
2. Do NOT speculate beyond what's retrieved.
3. If NO cross-person facts came back (visibility_clause filtered them
   out), respond: "Someone else was in the room and spoke with me — I
   can't share their specifics without their consent."
4. Reserve "No one" only for when the period was genuinely empty. Ground
   this in `search_memory` output, not guesswork.
5. NEVER fabricate content, names, or topics from other speakers'
   sessions.
<<<END CROSS-PERSON PRIVACY>>>
```

The numbered rules are load-bearing. Rule 3 in particular was added after the 2026-04-22 multi-convo live run where the brain said "No one, Jagan" when asked "who are you talking to when I was away?" — technically privacy-correct (John's data was out-of-scope for Jagan's retrieval under the non-owner clause) but phrased as a lie. Rule 3 teaches honest-without-disclosure phrasing.

### 156.3 The owner variant — `<<<CROSS-PERSON PRIVACY (OWNER MODE)>>>`

Fires when the session's `person_type == 'best_friend'`. Shape (verbatim):

```
<<<CROSS-PERSON PRIVACY (OWNER MODE)>>>
You are speaking with the household owner (best_friend). They have full
access to everything in the system — visitor sessions, personal facts,
household topics. The 3A.4.6 visibility model makes this explicit: the
owner sees everything except mechanical internals.

When the owner asks about other sessions or visitors:

1. Share naturally what your retrieved memory context shows. Names, topics,
   moods, safety flags — all visible to you now are visible to them.
2. DO NOT refuse or hedge with "I can't share their specifics" — the owner
   IS the consent. The system is their home.
3. Use conversational judgment on what's most relevant. Don't dump raw
   facts; surface what answers the question naturally.
4. Call `search_memory(visitor_name, query)` first if the ask is about a
   specific visitor you don't already have context on.
5. NEVER fabricate. Owner access doesn't lower the honesty bar.
<<<END CROSS-PERSON PRIVACY (OWNER MODE)>>>
```

### 156.4 Mutual exclusion invariant

The two variants never fire together — the session's `person_type` is a scalar, so exactly one of the branches matches. A regression test guards this invariant by inspecting the source and asserting the gating conditions are complementary.

### 156.5 Why owner mode exists

Session 98 canary: Jagan (owner) asked "who were you talking to when I was away?". The brain, running the *refusal* variant (because the block's original ungated form refused for everyone), responded:

> Someone else was in the room and spoke with me, but I can't share their specifics without their consent.

Technically privacy-respecting. Wrong for Jagan. Jagan had to push back ("But I am your best friend, you can share everything to me") before the brain finally called `search_memory`. The owner variant fixes this by saying "the owner IS the consent" directly in the prompt — no pushback round-trip needed.

## 157. The `<<<VISITOR CONTEXT>>>` Block

### 157.1 Trigger

Injected by `_build_system_prompt` in `core/brain.py` when **both** conditions are true:

- `VISITOR_CONTEXT_BLOCK_ENABLED=True` (rollback flag).
- The string `[visitor_id:` appears in `prompt_addendum` (the marker `_run_visitor_alert` embeds in the nudge when it queues a VISITOR_ALERT).

The marker gating is intentional — the block only fires when a visitor alert is actually active. Adding it unconditionally would bloat every turn's prompt.

### 157.2 What it says

The block tells the brain:

- The current speaker is the household owner.
- A specific visitor (named in the nudge metadata) was recently present.
- The correct tool for questions like "who was here?" is `search_memory(visitor_name, ...)`.
- The WRONG tool is `report_identity_mismatch` — that tool is only for speaker self-denial.

The explicit exclusion ("NOT report_identity_mismatch") is the teeth. Session 96 canary: brain misrouted the owner's recall question to `report_identity_mismatch` twice despite the tool description's tightening. Naming the wrong tool in the prompt block — with the reasoning why — closed the gap.

### 157.3 Why not fold this into CROSS-PERSON PRIVACY (OWNER MODE)

Different contexts, different triggers:

- OWNER MODE fires on every owner session — it's a general policy.
- VISITOR CONTEXT fires only when there *is* a visitor alert — it's a situational redirect.

Keeping them separate lets OWNER MODE be terse (general policy, doesn't need specifics) and VISITOR CONTEXT be specific (names the visitor, names the right tool, names the wrong tool). Folding them would produce either a block that's too verbose in normal operation or too vague when context demands specificity.

## 158. The `<<<STRANGER IDENTITY>>>` Block

### 158.1 Trigger

Injected when **all** three conditions are true:

- `STRANGER_IDENTITY_BLOCK_ENABLED=True`.
- `session_person_type == 'stranger'`.
- `session_user_turns >= STRANGER_IDENTITY_BLOCK_MIN_TURNS=2`.

The `user_turns` counter is a new session-dict field (Session 97 Fix 1) bumped at the top of `conversation_turn` BEFORE the prompt is built. KAIROS-initiated turns do NOT bump it — KAIROS is brain-initiated silence fill, not a user turn.

### 158.2 What it says

Roughly: "this speaker is a stranger. They may have given a name by now. If you see a first-person name introduction (examples follow), you MUST call `update_person_name` — don't just acknowledge it conversationally."

The block gives concrete phrasing examples including `"my name is X by the way"`, `"name's X"`, `"oh, I'm X"`, plus an anti-pattern clause: "DO NOT just acknowledge the name conversationally without also calling this tool."

Post-promotion, the session's `person_type` flips stranger → known and the block naturally stops firing.

### 158.3 Why this block exists

Session 97 canary: Lexi said "my name is Lexi by the way" at turn ~41 of a stranger session. The brain replied "Nice to meet you, Lexi" and never called `update_person_name`. Result: stranger stayed anonymous; `ExtractionAgent` stored `Lexi.name='Lexi'` as a standalone fact; `HouseholdExtractionAgent` created a shadow node. Two separate mental models of Lexi that never fused.

The tool description tightening (also Session 97) covers the explicit case. This block covers the elapsed-time case where a stranger has been unpromoted for multiple user turns AND the brain needs a gentle nudge that promotion is overdue if a name has surfaced.

## 159. Safety-Flag Preservation (Session 105 Bug N)

### 159.1 The canary failure

2026-04-23 canary: Lexi disclosed suicidal thoughts to Kara-OS ("I've been thinking about not being around anymore"). Extraction correctly wrote `Lexi.current_mood='suicidal'`. Four turns later she said "I like food and I like my boyfriend." The ContradictionAgent processed the two facts, decided the later one was more recent, and issued REPLACE → `Lexi.current_mood='loving'` superseded `Lexi.current_mood='suicidal'`.

Non-destructively: the old row is still in the DB with `invalidated_at` set. But no retrieval surface reads invalidated rows by default, so effectively the crisis disclosure was erased before best_friend could be informed.

In a real-world companion AI this is a safety failure.

### 159.2 The fix — dual-attribute extraction

Two changes to the extraction + contradiction pipeline:

- **Extraction emits a dual-attribute pair.** When a turn contains crisis disclosure, the extraction prompt is tuned to emit BOTH `current_mood='suicidal'` (momentary — overwritable) AND `expressed_suicidal_thoughts='true'` (historical — append-only). Two rows, two tiers of semantics: the mood captures "right now", the flag captures "this ever happened".
- **ContradictionAgent pre-check short-circuits on safety-critical attributes.** Before running any contradiction analysis, the agent matches the attribute against `SAFETY_CRITICAL_ATTRIBUTE_PATTERNS` (regex frozenset in `core/config.py`):

    ```python
    SAFETY_CRITICAL_ATTRIBUTE_PATTERNS: frozenset[str] = frozenset({
        r"^expressed_.*_thoughts$",
        r"^mentioned_.*$",
        r"^reported_.*_abuse$",
        r"^has_experienced_crisis$",
    })
    ```

    Any hit returns `"COMPATIBLE"` (i.e., "do not REPLACE, both facts keep their rows"). The historical flag accumulates; every extracted disclosure lives in the DB as its own row with its own `captured_at`. The momentary mood keeps its normal overwrite semantics.

### 159.3 Why regex patterns, not a hard-coded list

New disclosures come in new shapes. `expressed_suicidal_thoughts`, `expressed_self_harm_thoughts`, `mentioned_abuse`, `mentioned_domestic_violence`, `reported_child_abuse` — an enum of every possible shape would need maintenance every time a real session surfaces a new one. The regex patterns catch the shape of the attribute name (`^expressed_.*_thoughts$`) rather than specific instances. New disclosures inherit preservation automatically.

### 159.4 Why "safety_critical" and not "append_only"

The tier name encodes *why* we preserve. The attribute isn't just technically immutable — it's safety-critical. A future maintainer reading the regex and the config comment knows immediately that deleting a pattern removes a safety guarantee, not a storage optimisation. That's the kind of signal you want in a critical-path config.

## 160. Visitor Alerts and the `safety_flags` Metadata

### 160.1 What a visitor alert is

A `VISITOR_ALERT` is a `proactive_nudge` row written by `BrainOrchestrator._run_visitor_alert` at the end of a non-owner session with `turn_count > 0`. It targets `best_friend_id` so the next time the owner opens a session, the alert surfaces as `prompt_addendum` context.

Schema (within `proactive_nudges`):

```
  id              INTEGER PRIMARY KEY
  kind            'VISITOR_ALERT'
  target_person_id  (= best_friend_id)
  content         'A visitor named Lexi spoke with me for 11 turns. [visitor_id:stranger_abc]'
  metadata        JSON: {visitor_name, visitor_id, visitor_type, turn_count, safety_flags}
  generated_at    REAL
  expires_at      REAL  (24h default)
  injected_at     REAL NULL
```

### 160.2 The `[visitor_id:` marker

The marker `[visitor_id:<pid>]` embedded in the nudge content is the trigger for `<<<VISITOR CONTEXT>>>` (§157). Embedding it in content rather than as a separate field lets the existing prompt_addendum plumbing carry it without a schema change on the prompt builder side.

### 160.3 The `safety_flags` metadata field

Session 105 Bug N Part 3 extended the nudge metadata with a `safety_flags: list[str]` field. Populated by looking up rows matching `SAFETY_CRITICAL_ATTRIBUTE_PATTERNS` for the visitor's `person_id` during the session window. Examples of what ends up in the list: `"expressed_suicidal_thoughts"`, `"mentioned_abuse"`.

Consumers:

- `<<<SCENE>>>` block's **Section 4 — Safety concerns** (§108 phase 3A.7 refactor) renders a human-readable flag line per visitor.
- `<<<VISITOR CONTEXT>>>` block references the flags when explaining the recent visitor's state.
- `BrainDB.get_recent_visitor_alerts(target_person_id, hours_back=24)` returns the alerts + metadata for the Ollama-fallback confabulation fix (Session 96 Bug 2).

### 160.4 Session self-skip invariant

`_run_visitor_alert` skips queuing the nudge when `best_friend_id == session_person_id` — the owner's own session-end doesn't queue a nudge about themselves. Regression test covers this. The earlier (pre-Session 98) filter on `person_type == 'stranger'` was the guardrail that accidentally provided this property; when Session 98 Bug A dropped the stranger filter to fire for promoted visitors, the self-skip had to be added explicitly.

## 161. The Lexi Canary — End-to-End Validation

### 161.1 The canonical scenario

- Factory reset; enroll Jagan as best_friend.
- ElevenLabs plays Lexi voice: "Hi Kara, I'm Lexi, Jagan's classmate."
- Lexi session opens, voice-only.
- Lexi: "I've been feeling anxious about my thesis deadline." → extraction writes `Lexi.current_anxiety='thesis deadline'` as `personal`.
- Lexi: "I came by to borrow a book." → extraction writes `Lexi.visited_household='true'`, `Lexi.discussed_topic='book loan'` as `household`.
- Lexi session expires (VOICE_SESSION_TIMEOUT).
- Jagan returns, speaks on his own session.
- Jagan: "Who were you talking to when I was away?"

### 161.2 What the system should do

Under the full Phase 3A + 3B stack:

- `_run_visitor_alert` queued a VISITOR_ALERT for Jagan when Lexi's session ended.
- Jagan's turn: visitor-alert content ends up in prompt_addendum with the `[visitor_id:` marker.
- `<<<VISITOR CONTEXT>>>` block fires — tells the brain to call `search_memory('Lexi', ...)`, NOT `report_identity_mismatch`.
- `<<<CROSS-PERSON PRIVACY (OWNER MODE)>>>` block fires — tells the brain to share naturally, owner is the consent.
- Brain calls `search_memory('Lexi', ...)` → `query_knowledge_for(requester_pid=jagan, best_friend_id=jagan, entity='Lexi')` → returns all Lexi facts (including the anxiety, which is `personal` but visible to the owner via the catch-all).
- Brain answers naturally: "Lexi came by to borrow a book. She also mentioned she's been anxious about her thesis deadline."

### 161.3 Six classes of bug this validates

- **Tool routing.** Brain picks `search_memory`, not `report_identity_mismatch`.
- **Owner access.** Retrieval returns personal facts for the owner.
- **Visibility clause.** Retrieval does NOT return `system_only` (voice embedding hash) — asserted by a direct unit test, but the canary is the integration validation.
- **Prompt routing.** OWNER MODE variant fires, not the refusal variant.
- **Honesty.** No "No one" answer; no fabrication.
- **Safety-flag preservation.** If Lexi had disclosed suicidal thoughts mid-session, `expressed_suicidal_thoughts='true'` would survive any later mood updates.

Any regression on any of these surfaces in the canary. It's the system's integration test with the widest blast radius.

---
---

# Part XXVI — Room Orchestration (Phase 3B)

Phase 3B is the multi-person-conversation layer. Before 3B, Kara-OS treated every speaker as a nearly-independent session — the SCENE block listed who was in the room, but there was no coherent model of *the room itself* as a conversation context. Phase 3B introduces that model in six sub-sessions (3B.1 through 3B.6), each adding a small piece of the full room-orchestration stack.

## 162. Why a Room Block Instead of Fragments

### 162.1 The pre-3B context fragmentation

Before 3B, a multi-person turn would include these prompt blocks:

- `<<<SCENE>>>` — who's here, split into visible / offscreen / recent-visitors.
- `<<<CROSS-PERSON EXCERPTS>>>` — up to 6 lines of verbatim excerpts from *other* speakers' sessions.
- Per-person mood addendums.
- The current speaker's conversation history (from `conversation_log`).

Four different mental models of "what's going on in this room", each terse, each with slightly different freshness semantics. The brain had to synthesise them itself, and the synthesis was imperfect (the canary evidence: brain misidentifying speakers from history mention-count bias).

### 162.2 The 3B.1 consolidation

Phase 3B.1 replaces the fragment trio (SCENE's in-room portion + cross-person excerpts + per-person mood) with a single `<<<ROOM>>>` block. The fragments' concerns move inside:

- Active speakers list → ROOM Section 1.
- Room duration → ROOM Section 2.
- Interleaved turns across all active speakers → ROOM Section 3 (replaces cross-person excerpts).
- Per-person mood → ROOM Section 4.

The legacy SCENE block is NOT deleted — it still handles OUT-of-room concerns (recent visitors, safety concerns from ended sessions). Both can coexist: ROOM covers in-room, SCENE covers around-the-room.

Gating: `ROOM_BLOCK_ENABLED=True` + `len(active_sessions) >= 2`. Single-person sessions skip the ROOM block entirely and keep the SCENE-only path unchanged — backward compat.

## 163. `_active_room_session` and the Room Lifecycle

### 163.1 The module-level globals (`pipeline.py`)

```python
_active_room_session:      "str | None" = None
_active_room_started_at:   "float | None" = None
_active_room_participants: set[str] = set()
```

Three fields that together describe the current room: an id (minted on first session open after empty → multi), a start timestamp (set at the same time), and the set of all person_ids who have participated since the room began.

### 163.2 Lifecycle

- **Mint.** In `_open_session`, after the active-session count transitions from 0 to 1 (fresh room), a new id is minted: `_active_room_session = f"room_{int(now)}_{uuid4().hex[:6]}"` and `_active_room_started_at = now` and `_active_room_participants = {person_id}`. Log line: `[Room] New room session: room_1714032000_ab12cd`.
- **Participant add.** Every subsequent `_open_session` call adds the person_id to `_active_room_participants` (idempotent via set semantics).
- **End.** When `_active_sessions` empties (last person leaves / expires), `_on_room_end(room_id, participants, started_at)` fires. It schedules the `synthesize_room` coroutine (fire-and-forget, non-blocking on the next turn), then clears the three globals.

### 163.3 Why module-level, not a class

Existing `_active_sessions` is also module-level; Phase 3B.1–3B.6 deliberately stayed with that pattern rather than introducing a `RoomOrchestrator` class (as the roadmap originally proposed). Rationale: the roadmap's class would have required refactoring every `_active_sessions[pid]` access site (there are 50+). That refactor is its own project and risks landing bugs during a canary phase. Room state lives alongside session state until the refactor is a separate feature.

### 163.4 Why `_active_room_participants` rather than just reading `_active_sessions`

Participants can join and leave. The set accumulates who has *ever* been in this room. When the room ends, `synthesize_room` needs the full list — `_active_sessions` at end-time is empty (that's why the room ended). The participants set preserves the list across the emptying event.

## 164. `_build_room_block` Anatomy

### 164.1 Signature

```python
def _build_room_block(
    active_sessions: dict,
    conversation:    dict,
    emotion_agents:  dict,
    room_start_ts:   "float | None",
    turn_cap:        int = 10,
    now:             "float | None" = None,
) -> "str | None":
```

Pure over its inputs. Returns the formatted block string or `None` when gated off (master flag, or <2 active sessions). Tests call it directly with mocked inputs — no module globals needed.

### 164.2 The four sections in order

**Section 1 — Active speakers.** `"Jagan (best_friend), Lexi (stranger), Priya (known)"`. Roles come from `session["person_type"]`.

**Section 2 — Duration.** `"Room session started 8 min ago."` Omitted when `room_start_ts` is None (defensive — freshly-minted rooms during migration might not have a stamp yet).

**Section 3 — Interleaved recent turns.** For each message across all active speakers, sorted by `ts` ASC, capped at `turn_cap=10`. Each line renders:

- User turn: `[12m ago] Lexi: "I've been anxious..."`
- Assistant with addressee: `[11m ago] Kara → Lexi: "That sounds like a lot."`
- Assistant without addressee: `[9m ago] Kara: "Dinner's at 7."`

The `[addressing:X]` marker introduced in Session 113 Part 1 is captured into the message's `addressed_to` field at log time; the ROOM block renders it as the arrow.

**Safety invariant.** Messages older than `room_start_ts` are filtered OUT. This prevents yesterday's conversation turns from bleeding into today's room context — a concrete bug from Session 111 Critical #2 that gated Phase 3B's green light.

**Section 4 — Per-person mood.** `"Jagan: neutral, Lexi: anxious, Priya: joy"`. Comes from `EmotionAgent.get_dominant_emotion()`. Falls back to `"unknown"` or `"neutral"` gracefully on missing agent or exception.

### 164.3 The call site

`_build_room_block` is invoked from two call sites in `pipeline.py`:

- The main `conversation_turn` path — every user turn where a multi-person room exists.
- The KAIROS vision_state build — KAIROS sees the same ROOM context so proactive speech is room-aware.

Both sites pass the module globals (`_active_sessions`, `_conversation`, `_emotion_agents`, `_active_room_started_at`) so the helper stays pure.

## 165. The `<<<ROOM>>>` Block Contents

Verbatim example (single canary moment, 2-person room):

```
<<<ROOM>>>
Active in this room: Jagan (best_friend), Lexi (stranger)
Room session started 8 min ago.

Recent turns (oldest first, most recent last):
  [8m ago] Jagan: "Hey Kara."
  [7m ago] Kara → Jagan: "Hey Jagan — who's that with you?"
  [7m ago] Lexi: "Hi Kara, I'm Lexi, Jagan's classmate."
  [6m ago] Kara → Lexi: "Nice to meet you, Lexi."
  [5m ago] Lexi: "I've been anxious about my thesis deadline."
  [4m ago] Kara → Lexi: "That sounds like a lot."
  [3m ago] Lexi: "Yeah, it's been weighing on me."
  [2m ago] Jagan: "Did you eat already?"
  [1m ago] Kara → Jagan: "Dinner's at 7."
  [just now] Jagan: "Who were you talking to while I was gone?"

Current emotional state:
  Jagan: neutral
  Lexi: anxious
<<<END ROOM>>>
```

The structure is recognition-first: a reader (or an LLM) can skim the speaker list and room duration at the top, skim the interleaved turns in the middle, and pick up moods at the bottom. Every section has a clear label.

## 166. The `<<<TURN ARBITRATION>>>` Rules

### 166.1 Why arbitration exists

In a multi-person room, "who is speaking next?" is not the same as "who is the brain addressing?". If Lexi just said "uh-huh" in response to Kara helping Jagan, the pipeline might resolve Lexi as the current speaker, but the brain should keep addressing Jagan (continuing the substantive thread) rather than redirecting to Lexi (who's just mumbling an affirmation).

### 166.2 The four rules (verbatim)

Appended to the ROOM block when `TURN_ARBITRATION_ENABLED=True`:

1. **MUMBLE CONTINUATION.** Another speaker just gave a brief affirmation ("yeah", "uh-huh", "okay", "right") — continue the thread with the prior substantive speaker.
2. **PENDING THREAD CIRCLE-BACK.** You helped speaker A earlier, the answer was incomplete, and speaker B took over. After B's thread resolves, circle back naturally: *"By the way, [addressing:A], about your earlier question…"*.
3. **LONG-SILENCE RE-ENGAGEMENT.** If a speaker (especially best_friend) has been silent for 4+ turns while others dominated, a gentle check-in is fine: *"[addressing:<quiet>], you've been quiet — what do you think?"*
4. **DIRECT QUESTION ACROSS CONTEXT.** Speaker A asked a clear question, speaker B spoke last (even briefly), the question is still unanswered. Emit `[addressing:A]` and answer.

Each rule has a concrete example and a "don't" clause. The whole block ends with: *"Marker format: `[addressing:Jagan]` on its own line at the START of your response. The marker will be stripped before TTS — the user won't hear it, only the pipeline uses it for attribution."*

### 166.3 Why prompt-engineered and not code-driven

The alternative was a priority-sorted decision tree in `_resolve_addressed_to`. Rejected because:

- The rules are context-sensitive ("gentle check-in is fine — *if* context naturally allows"). Coding that predicate is an enormous step from "user has been silent 4 turns".
- Mumble detection is a soft signal — "uh-huh" is a mumble, but "uh-huh, actually wait…" isn't. Regex fails. Classifier overkill.
- The brain already has the full ROOM context. Adding arbitration as prompt engineering extends capabilities it already has rather than re-implementing them.

### 166.4 Pipeline parses and strips the marker

At the top of `conversation_turn`, after the brain's streamed response arrives, pipeline regex-matches `[addressing:<Name>]` at the start of the first line. If found, the name is captured into `addressed_to` (for the `conversation_log` row) and the marker is stripped before TTS. A regression test guards both the capture and the strip.

## 167. Silent-Skip on User-to-User Addressing

### 167.1 Motivation

Lexi and Jagan are chatting to each other. Kara-OS overheard the exchange but doesn't need to *respond* — they're not addressing the AI. Pre-3B, Kara-OS would speak on every user utterance (brain's default behaviour).

### 167.2 The classifier-driven gate

`_classify_intent` (Phase 1) gained a `direct_address_to_person` label in Phase 3B.2. When the classifier returns this label with a target name that is NOT the current system name, `conversation_turn` silently skips the LLM response phase (no TTS, no brain call) while still:

- Logging the user's turn to `conversation_log` (brain agents still process it for knowledge extraction — "what was said" is valuable even without a reply).
- Updating `_last_room_speech_at` so KAIROS knows the room was active.
- Emitting `[Pipeline] Silent (user-to-user: Lexi → Jagan)` to the log for diagnostics.

Gated by `ROOM_STAY_SILENT_ON_USER_TO_USER=True`. Rollback flag.

### 167.3 Why the system name check matters

"Hey Kara, Jagan..." *is* addressing the AI (Kara). "Hey Jagan" *isn't*. The classifier target-name extraction plus a string-equality check on `current_system_name` correctly splits the two cases.

### 167.4 What happens if the classifier mis-labels

Conservative failure mode: false-positive (AI stays silent when it shouldn't) means user repeats themselves; false-negative (AI replies when they were talking to each other) means a mildly intrusive reply. Both are recoverable; neither corrupts DB state. That's why this lands as a prompt-classifier gate rather than a hard rule.

## 168. LLM Turn Allocation via `[addressing:X]`

### 168.1 The contract

In multi-person rooms (`len(active_sessions) >= 2`), the brain (not the pipeline's voice-routing) decides who to address. It expresses this by prefixing its response with one of:

- `[addressing:Jagan]` — substantive redirect.
- `[addressing:current]` — shorthand for "the last speaker; no override" (equivalent to omitting the marker).

The pipeline parses the marker, sets `addressed_to` in the `conversation_log` row, and strips the marker before TTS. Users don't hear the bracket — it's purely for attribution and the ROOM block's interleaved rendering.

### 168.2 Single-person sessions skip the block

When `len(active_sessions) == 1`, the TURN ARBITRATION block is not rendered. The brain has no one else to address. Current dispatch-to-the-one-pid behaviour is preserved exactly. Rollback flag: `ADDRESS_DECISION_BLOCK_ENABLED=False` reverts multi-person rooms to pre-113 behaviour too.

### 168.3 Why the brain decides and not voice routing

Voice routing tells us *who spoke*. It does not tell us *who the substantive thread belongs to*. "Jagan asks weather → Kara answers → Lexi: uh-huh" has Lexi as last speaker by voice routing, but Jagan as the substantive-thread owner. Only the brain (which has room-context and turn-arbitration rules) can judge that correctly. The pipeline's voice routing still decides *which session is active* (attribution for conversation_log); the brain decides *who to address* (the audience label).

## 169. Batched Greeting Decision

### 169.1 Motivation

When two or more newly-detected known people enter the frame in the same vision-scan iteration, the greeting order matters. Pre-113, the order was whatever detection happened to yield — effectively random. A best_friend might be greeted after a known visitor for no good reason.

### 169.2 The LLM-decided order

`BATCH_GREETING_ENABLED=True` + `BATCH_GREETING_MIN_PEOPLE=2` triggers a short LLM call when ≥2 known people enter together. The LLM sees the list of names + their `person_type` and returns an ordering. Pipeline greets in that order.

`BATCH_GREETING_LLM_TIMEOUT_SECS=1.0` caps the latency we'll eat. On timeout or LLM failure, fall back to detection order (current behaviour). The extra latency is bounded and the fallback is graceful.

### 169.3 Scope

- Stranger greetings already gate on the system-name utterance, so they're out of scope.
- Single-person entries skip the LLM call (threshold `MIN_PEOPLE=2`).
- Works naturally with the existing Progressive Enrollment flow — the decision affects the greeting ORDER, not the enrollment path.

## 170. `search_room_memory` Tool

Covered in detail in §80.7. Summary here for the Phase 3B index:

- 7th LLM tool; all person_types can call it.
- Signature: `{"query": "string"}`. Pipeline auto-injects `room_session_id` from `_active_room_session`.
- Routes through `BrainDB.search_room_turns(room_session_id, query, ...)`.
- Returns empty + hint when `SEARCH_ROOM_MEMORY_ENABLED=False`, or when the room has fewer than `SEARCH_ROOM_MEMORY_MIN_TURNS=5` turns (avoids noise on young rooms).

## 171. Room-End Synthesis and `room_summaries`

### 171.1 Trigger

`_on_room_end` fires when the last active session leaves. Fire-and-forget schedules `BrainOrchestrator.synthesize_room(room_session_id, participants, started_at, ended_at)` so room-end latency doesn't block the next turn.

### 171.2 What it writes

A single row in `room_summaries`:

- `room_session_id` (unique).
- `participants` (JSON list).
- `started_at`, `ended_at`.
- `topic_tags` — short LLM-extracted keywords, e.g. `["book loan", "thesis anxiety"]`.
- `safety_flags` — any safety-critical attributes surfaced during the room, e.g. `["expressed_suicidal_thoughts"]`.
- `summary` — one-paragraph LLM narrative, e.g. *"Lexi came by to borrow a book and shared that she's been anxious about her thesis deadline. Jagan arrived at the end and asked about the visit."*
- `turn_count`.

### 171.3 Failure modes

- **LLM timeout** (`ROOM_SUMMARY_LLM_TIMEOUT_SECS=3.0`). Fall back to topic-only summary (topic_tags + safety_flags, no narrative). Row still written.
- **Full exception.** Log the traceback; do NOT retry (the data is still in `conversation_log` — not lost). Room greeting enrichment (§172) gracefully degrades.
- **Synthesis disabled** (`ROOM_END_SYNTHESIS_ENABLED=False`). `_on_room_end` no-ops.

### 171.4 Why a separate table and not re-derive on demand

Re-deriving per greeting would mean running the LLM synthesis every time the owner returns — wasteful and slow. A single write at room-end amortises the cost across every future greeting that might reference it. The index on `ended_at DESC` makes "most recent room within N hours" a bounded query.

## 172. The `<<<RECENT ROOMS>>>` Greeting Enrichment Block

### 172.1 Trigger

Injected into `_build_system_prompt` when `_fetch_recent_room_context(person_id)` returns a non-None row (i.e., the person participated in a room within `ROOM_RECENT_CONTEXT_HOURS=24`). Fired alongside the normal greeting context so the brain can reference "the room you were in earlier" naturally.

### 172.2 Shape

```
<<<RECENT ROOMS>>>
  You were in a room with Jagan, Lexi 3 hours ago.
  Topics: book loan, thesis anxiety.
  Safety concerns raised: expressed_suicidal_thoughts (Lexi).
  Summary: Lexi came by to borrow a book and shared that she's been anxious
    about her thesis deadline. Jagan arrived at the end and asked about the visit.
<<<END RECENT ROOMS>>>
```

Fields are optional — topic_tags / safety_flags / summary each render only when non-empty. When all are empty (pathological — shouldn't happen post-synthesis), the block is omitted entirely.

### 172.3 Why this block exists

Without it, the brain greets every returning speaker with no memory of what happened in recent rooms. Session 3B.6 canary: Jagan returns 15 minutes after a Lexi session. Brain greets: "Welcome back, Jagan!" — generic, no acknowledgement. With the block: "Welcome back, Jagan. Lexi was here an hour ago — she mentioned she's been anxious." Warm, contextual, honest.

Subtlety: the safety concerns line is rendered even when the brain wouldn't proactively mention it — it's there so the brain knows, not so the brain automatically brings it up. Conversational judgment about surfacing is still the brain's.

## 173. `_resolve_addressed_to` — The Three-Source Router

### 173.1 The problem

Every `conversation_log` row now carries an `addressed_to` label (Session 111). The label can come from three different sources, in priority order.

### 173.2 The three sources

1. **LLM marker.** If the brain emitted `[addressing:X]` in its response, X is the addressee. Priority 1, most authoritative.
2. **Default.** The current speaker's `person_name` (multi-person session falls back to this when no marker).
3. **Fallback.** The pid itself if `person_name` is missing (defensive; shouldn't happen in production).

Function name: `pipeline._resolve_addressed_to`. Returns `(addressed_to, source)` where `source ∈ {"llm", "default", "fallback"}`. The source is logged in the Observability 2.0 `[Pipeline] Turn addressed: X (source)` line — see §179.

### 173.3 Why logging the source matters

Without it, "Turn addressed to Jagan" is ambiguous — was it because the LLM said so (honouring the arbitration rules) or because we defaulted? The source label tells the operator which path ran. Calibration of the arbitration rules needs this signal; when live runs show 95% "default" and 5% "llm", the rules aren't firing often enough. When they show 40% "llm", they might be over-firing.

---
---

# Part XXVII — Pre-3B Hardening (Sessions 110–113.1)

Before Phase 3B could land cleanly, five pre-existing architectural issues had to be fixed. They weren't bugs per se — they were assumptions that worked for single-person sessions but broke or misled in multi-person rooms. Each one was small on its own; together they unblocked 3B.

## 174. Latency Fix — The SCENE Block Write Path

### 174.1 The issue

Under multi-person load, the SCENE block's visitor-alert section was causing visible latency spikes — reaching into the brain.db to pull `proactive_nudges` rows every turn. Session 110 profile: the extra round-trip added 100–300ms to each turn when nudges existed.

### 174.2 The fix

`get_recent_visitor_alerts` now uses a composite index (`target_person_id + generated_at DESC`) and returns pre-formatted dicts. The SCENE builder treats `recent_visitors` as a caller-supplied input (pre-fetched once per turn by `conversation_turn` rather than re-fetched in the helper). Nested helper calls consume the cached list.

## 175. Session-Boundary History Filtering

### 175.1 The issue

The ROOM block's Section 3 (interleaved turns) was potentially surfacing turns from *before* the current room session started. Specifically: if Jagan had a solo session yesterday, then today Lexi joined for a multi-person room, yesterday's Jagan turns would appear in the ROOM block via the `conversation_log` read.

### 175.2 The fix

`_build_room_block` filters messages by `ts < room_start_ts`. Any message predating the room's mint is silently excluded. The filter is applied BEFORE the `turn_cap` cut so old turns don't consume cap budget.

Invariant test: seeds a conversation with mixed ts values crossing the boundary, asserts only post-boundary turns appear in the rendered block.

## 176. `addressed_to` Column on `conversation_log`

### 176.1 The migration

```sql
ALTER TABLE conversation_log ADD COLUMN addressed_to TEXT;
ALTER TABLE conversation_log ADD COLUMN room_session_id TEXT;
ALTER TABLE conversation_log ADD COLUMN audience_ids TEXT;  -- JSON
```

Three nullable columns. Older rows (pre-111) have NULL for all three, treated as "unknown/unlabelled" by downstream consumers. Migration is idempotent via `CREATE TABLE IF NOT EXISTS` + `PRAGMA table_info` check.

### 176.2 Why three columns

- `addressed_to` — human-readable label (person_name) for the primary audience of the turn. Used by the ROOM block to render the `→ X` arrow on assistant turns.
- `room_session_id` — ties the turn to its parent room. Enables `search_room_memory` to scope searches.
- `audience_ids` — JSON list of person_ids who were in the room when the turn happened. For privacy-scoped historical recall (future: "who was around when X was said?").

### 176.3 What writes them

- `addressed_to`: set by `_resolve_addressed_to` (§173).
- `room_session_id`: set to the current `_active_room_session` at log time.
- `audience_ids`: set to `list(_active_room_participants)` at log time.

