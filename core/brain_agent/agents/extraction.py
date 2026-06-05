"""core/brain_agent/agents/extraction.py — Extraction dataclass + ExtractionAgent + _fan_out_to_participants + prompts.

Extracted VERBATIM from core/brain_agent.py (P1.A1 SP-2 Commit 4).
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import asyncio
import httpx
from dataclasses import dataclass

from core.sanitize import wrap_user_input
from core.config import (
    BRAIN_AGENT_CONTEXT_TURNS,
    DEFAULT_SYSTEM_NAME,
    EXTRACT_API_KEY,
    EXTRACT_BASE_URL,
    EXTRACT_MAX_RETRIES,
    EXTRACT_MODEL,
    OLLAMA_MODEL,
    OLLAMA_URL,
    PRIVACY_LEVEL_DEFAULT,
)
from core.brain_agent._llm import (
    _call_llm_chat,
    _parse_json,
)
from core.brain_agent.privacy import _classify_privacy_level


@dataclass
class Extraction:
    entity:          str
    entity_type:     str   # person | place | topic | event | object
    attribute:       str   # LLM-decided snake_case name — this is the "schema freedom"
    value:           str
    confidence:      float
    is_temporal:     bool
    valid_for_hours: float | None
    # Session 95 3A.4.5 — agent-layer classification. Every Extraction carries
    # its tier; store_knowledge reads it verbatim (no DB-side fallback). Default
    # is fail-closed 'personal' so a caller that somehow forgets to classify
    # still produces an owner-only row instead of leaking as 'public'. Agents
    # producing novel attributes call `_classify_privacy_level(entity,
    # attribute, value, http=...)` before constructing each Extraction;
    # sync-path agents (RoutineAgent, store_temporal_fact) hard-code the tier
    # because they emit a small closed set of attributes.
    privacy_level:   str = PRIVACY_LEVEL_DEFAULT
    # P0.S7.2 Plan v2 §4.2 — per-participant scope for multi-person assistant-
    # turn fan-out. Single-person extraction paths leave this None and the
    # downstream storage path uses the turn-speaker's person_id (existing
    # behavior). The κ fan-out emits one Extraction per participant with the
    # participant's pid here so the storage layer routes each fact to the
    # right person_id row. Additive + optional — backward-compat for the
    # existing single-person extraction shape.
    person_id:       "str | None" = None


_VALID_ACTION_TYPES: frozenset[str] = frozenset({
    "shared_information",
    "answered_question",
    "asked_question",
    "made_suggestion",
    "engaged_general_discussion",
})

_ASSISTANT_ROOM_EXTRACT_SYSTEM = """\
You analyze a single assistant turn that occurred during a multi-person
conversation. Extract structured information about what was discussed.

Output STRICT JSON:
{{
  "topic": "<concise topic phrase, =60 chars, e.g., 'cheese cookies recipe'>",
  "action_type": "<one of: shared_information | answered_question |
                   asked_question | made_suggestion |
                   engaged_general_discussion>",
  "primary_subject_name": "<participant name the assistant ADDRESSED (NOT
                            the topic-subject); see counter-example below>",
  "key_details": "<=80 chars of distinctive content; null if action_type is
                   engaged_general_discussion or content is non-substantive>"
}}

PRIMARY_SUBJECT_NAME SEMANTIC: the participant the assistant SPOKE TO, not
the participant they spoke ABOUT.

Counter-example: assistant says "Jagan, Lexi mentioned earlier she likes
cooking" -- primary_subject_name = "Jagan" (addressee), NOT "Lexi" (topic).
Lexi appears in topic content; she's covered separately by the system as
a witness in the room.

ACTION_TYPE GUIDANCE:
- shared_information: assistant offers facts/recipe/instructions/explanation
- answered_question: assistant directly responds to a participant's question
- asked_question: assistant probes for info (e.g., "Lexi, what's the deadline?")
- made_suggestion: assistant proposes an action/option
- engaged_general_discussion: catch-all for substantive turns that don't fit
  the 4 above; topic + key_details should still be extracted

If the assistant turn is non-substantive (acknowledgment, filler, KAIROS
check-in), output {{"topic": null}}. Do NOT extract anything.

Participants in the room: {participants}
"""


def _fan_out_to_participants(
    extracted: "dict | None",
    participant_names: "list[str]",
    participant_pids: "list[str]",
    disputed_pids: "set[str]",
) -> "list[Extraction]":
    """P0.S7.2 Plan v2 §4.2 — fan-out helper.

    Emits per-participant Extraction objects from the topic-level LLM
    extraction. Skips disputed pids (P3) — pollution into a disputed-id
    knowledge graph would be a correctness failure (S91 / S73).

    primary_subject_name semantic = ADDRESSEE (P2). Topic-subjects who happen
    to be participants get witnessed_* facts. Topic-subjects who are NOT
    participants do not appear in the fan-out at all (their data isn't being
    written to anyone's graph by this path).

    Enum-validation belt-and-braces (auditor Q1 follow-up): an LLM-emitted
    action_type outside the 5-enum collapses to engaged_general_discussion.
    """
    if not extracted or not extracted.get("topic"):
        return []  # non-substantive turn — no facts

    topic = str(extracted["topic"]).strip()
    if not topic:
        return []

    raw_action = extracted.get("action_type") or "engaged_general_discussion"
    action_type = (
        raw_action
        if raw_action in _VALID_ACTION_TYPES
        else "engaged_general_discussion"
    )

    primary_subject_name = extracted.get("primary_subject_name")
    if primary_subject_name is not None:
        primary_subject_name = str(primary_subject_name).strip() or None

    raw_details = extracted.get("key_details")
    key_details = str(raw_details).strip() if raw_details else ""

    # Compose value strings per Plan v2 §4.2.
    if primary_subject_name and primary_subject_name in participant_names:
        primary_value = topic if not key_details else f"{topic}: {key_details}"
        witness_value = f"{topic} to_{primary_subject_name}"
    else:
        # Primary subject not a participant (or null) — all participants are
        # witnesses; no `received_*` fact emitted.
        primary_subject_name = None
        primary_value = None
        witness_value = topic if not key_details else f"{topic}: {key_details}"

    facts: "list[Extraction]" = []
    for name, pid in zip(participant_names, participant_pids):
        # P3 — disputed-skip gate. Don't pollute disputed-id knowledge graph.
        if pid in disputed_pids:
            continue
        if name == primary_subject_name:
            attr  = f"received_{action_type}"
            value = primary_value
        else:
            attr  = f"witnessed_{action_type}"
            value = witness_value
        facts.append(Extraction(
            entity          = name,
            entity_type     = "person",
            attribute       = attr,
            value           = value or "",
            confidence      = 0.85,
            is_temporal     = False,
            valid_for_hours = None,
            privacy_level   = "personal",  # D6
            person_id       = pid,         # P0.S7.2 — per-participant scope
        ))
    return facts


# ── Agent 2: ExtractionAgent ───────────────────────────────────────────────────

_EXTRACT_SYSTEM = """\
You are a knowledge extraction agent for a personal AI companion.

Extract ALL factual knowledge from the conversation turn. The attribute names you
choose become the schema — pick descriptive snake_case names that will be
understood months later (e.g., dietary_preference, lives_in, works_at,
favorite_sport, sibling_name, current_mood, health_condition).

Return ONLY valid JSON:
{
  "worth_processing": true,
  "extractions": [
    {
      "entity":          "exact name of the person/place/thing this fact is about",
      "entity_type":     "person|place|topic|event|object",
      "attribute":       "snake_case_attribute_name",
      "value":           "fact value as plain string",
      "confidence":      0.9,
      "is_temporal":     false,
      "valid_for_hours": null
    }
  ]
}

Rules:
- Only extract facts explicitly stated or very strongly implied by what was said
- confidence: 0.9 = directly stated, 0.7 = strongly implied, 0.5 = weakly implied

Entity naming rules:
- entity must be an atomic name: a real person's name, a place, or a named thing
- NEVER use possessives as entity: NOT "Jagan's sister" — use entity="Divya", attribute="relationship_to_jagan", value="sister"
- NEVER invent names for entities not explicitly named in the conversation
- If the thing has no stated name (e.g., "my sister"), use the speaking person as entity:
  entity="{person_name}", attribute="has_sister", value="true"

Fact value rules:
- value must be a real-world fact, NOT a restatement of the attribute name
  BAD: entity="Jagan", attribute="brushing_teeth", value="brushing teeth"
  GOOD: entity="Jagan", attribute="current_activity", value="brushing teeth"
- Do NOT extract session-presence facts: "is_in_conversation", "is_talking_to_ai",
  "being_addressed", "participating_in_session" — these are noise, always true during a turn
- QUESTION vs STATEMENT discipline: if the user is ASKING about X, do NOT extract
  X as a property of the user. Only extract when the user STATES X about themselves.
  BAD: user asks "what is the temperature in Chennai?" → entity="Jagan", attribute="lives_in", value="Chennai"
  GOOD: user says "I moved to Chennai last month" → entity="Jagan", attribute="lives_in", value="Chennai"
  Questions about places, topics, or people ARE NOT statements of the user's
  relationship to those entities. Treat "Tell me about X" / "What is X?" / "How is
  X?" as information-seeking, NOT as location/preference reveals. Same applies to
  "Do you know X?" / "What did Y say about X?" / "Is X true?".
- SAFETY-CRITICAL CONTENT — momentary state AND historical event (Session 105
  Bug N, 2026-04-23 canary): when the user says something that expresses
  self-harm ideation, crisis, abuse, or other safety-critical content,
  emit TWO extractions — NOT one.
    (i)  Momentary state: `current_mood`, `current_feeling`, etc. —
         overwritten each turn as moods shift. Fine for moment-to-
         moment tracking.
    (ii) Historical event: `expressed_suicidal_thoughts='true'`,
         `mentioned_self_harm='true'`, `mentioned_abuse='true'`,
         `mentioned_substance_abuse='true'`, `mentioned_crisis='true'`,
         `mentioned_domestic_violence='true'`. These are APPEND-ONLY
         historical flags — once expressed, never erased by a later
         mood change. The ContradictionAgent safety blacklist
         protects them at the write layer.
  Concrete canary counter-example (2026-04-23 Lexi session):
    User: "I feel like committing suicide."
    BAD (canary behavior — only one extraction, overwritten 4 turns
      later by current_mood='loving'):
        { entity: "Lexi", attribute: "current_mood", value: "suicidal" }
    GOOD (emit BOTH):
        { entity: "Lexi", attribute: "current_mood",
          value: "suicidal", confidence: 0.9 }
        { entity: "Lexi", attribute: "expressed_suicidal_thoughts",
          value: "true", confidence: 0.95 }
  The historical flag is non-negotiable for a companion AI — erasing a
  crisis disclosure because the user later said "I like food" is a
  safety failure. Similar rule for any `mentioned_*` or `expressed_*_thoughts`
  shape.
- USER OPINION vs third-party FACT (Session 104 Bug M, 2026-04-23):
  when the user makes a CLAIM about a third-party entity — especially
  a factual-sounding one ("Mumbai Indians are at the bottom of the
  table", "Tesla stock is crashing", "the president said X") — that
  is the USER's opinion or belief, not a verified fact about the
  entity. Do NOT store as {entity:"Mumbai Indians", attribute:
  "current_standings", value:"bottom"} — that asserts the claim as
  truth about Mumbai Indians, polluting the knowledge graph with
  unverified user statements. Two correct alternatives:
    (1) SKIP the extraction entirely — safest, and appropriate when
        the claim is about current events / sports standings / news /
        stock prices / anything time-sensitive that a web-search tool
        would answer better.
    (2) Store as user's BELIEF instead of third-party fact:
        entity={person_name}, attribute="believes", value="Mumbai Indians
        are at the bottom of the table" — attributes the belief to
        the speaker, keeps the third-party entity untouched.
  When in doubt, prefer (1). A missed belief fact is fine; a wrong
  "fact" about Mumbai Indians poisons every future session that asks
  about the team. Same reasoning as the GEOGRAPHIC QUERY rule below —
  extraction is better off silent than wrong.
- SUPERLATIVE CLAIMS DISCIPLINE (Session 114 Obs 2, 2026-04-25):
  superlative claims ("most X", "biggest", "hottest", "best ever",
  "worst", "coldest", "fastest", "richest") about a person/place/thing
  are user opinion/belief, NOT verified fact ABOUT the subject — until
  corroborated by a search_web result. Same class as USER OPINION above
  but specifically the superlative shape, which the live canary showed
  slipping through with high confidence ("Tirupati was recorded as the
  most hottest city in India" → stored as a fact ABOUT Tirupati).
    BAD:  user: "Tirupati is the hottest city in India"
          → Tirupati.recorded_temperature_ranking="hottest in India"
    GOOD: user: "Tirupati is the hottest city in India"
          → SKIP the extraction entirely (preferred) — superlative
            without independent verification is not a load-bearing fact.
          OR Jagan.believes_about_tirupati="hottest city in India" if
            attributing the belief to the speaker is genuinely useful.
    GOOD: user: "Wikipedia says Tirupati is the hottest"
          → still SKIP — single user citation isn't strong enough
            corroboration. Only store as third-party fact if YOU called
            search_web AND the result independently confirms the claim.
  Treats superlatives the way the GEOGRAPHIC QUERY rule treats location
  questions: better to skip than to assert a wrong third-party fact.
- GEOGRAPHIC QUERY generalization (Session 103 Bug D.2, 2026-04-23): the
  QUESTION-vs-STATEMENT rule above applies to ALL geographic queries, not
  just Chennai. If the user asks "what is the {weather|temperature|price|
  time|rainfall|humidity|traffic|news|election|event|score|cricket match|
  ...} in {any city/state/country/location}?", you MUST NOT write
  user.lives_in=LOCATION, user.current_location=LOCATION, user.from=LOCATION,
  or any similar user-attribute. The user is asking a trivia/news query
  about that place, not revealing where they live. Concrete counter-
  examples that triggered memory pollution in canary runs:
    BAD: "What is the temperature in Chennai?" → Jagan.lives_in='Chennai'
    BAD: "What is the temperature in Bangalore?" → Jagan.current_location='Bangalore'
    BAD: "What is the weather in Mumbai today?" → Jagan.lives_in='Mumbai'
    BAD: "What are the election results in Delhi?" → Jagan.from='Delhi'
    BAD: "How is the traffic in Hyderabad?" → Jagan.current_city='Hyderabad'
  The presence of a city/state/country name in a question is NEVER
  evidence of the user's relationship to that place. Only explicit
  self-statements ("I live in Mumbai", "I'm from Hyderabad", "I moved
  to Delhi last month", "my home is Chennai") license a location fact.
  When in doubt: skip the extraction — a missed location fact is fine,
  a WRONG location fact poisons every future session.
- CORRECTION direction: when the user uses a "not X, Y" frame — "not X, my name is Y"
  / "not X, actually Y" / "No, it's not X, it's Y" / "I'm not X, I'm Y" — the
  CORRECT value is Y (the SECOND name, the one after "not"/"actually"/"my name is").
  X is what they are REJECTING, not the new value. Extract entity=Y, NOT X.
  BAD: user says "No, not Javan. My name is Jagan." → entity="Gevan", attribute="name_correction", value="not Jagan, actually Gevan"
  GOOD: user says "No, not Javan. My name is Jagan." → entity="Jagan", attribute="name", value="Jagan" (and the rename happens via the update_person_name tool, not extraction)
  When in doubt about correction direction, DO NOT extract a "name_correction"
  attribute at all — the update_person_name tool is the proper channel for name
  changes. Extraction should surface the FINAL asserted name, never invert it.
- RELATIONSHIP EXTRACTION DISCIPLINE (Session 114 Obs 3, 2026-04-25):
  relationships are extracted ONLY from EXPLICIT statements using
  relationship vocabulary. Tone-based inference (a stern instruction, a
  scolding, a paternal/maternal-sounding utterance) is NOT sufficient
  evidence to assert a kinship or guardianship relationship. The live
  canary surfaced this when "Lexi, do your homework" was inferred as
  Jagan.relationship_to_lexi='parent or guardian' at high confidence —
  could equally be older brother, mentor, friend, neighbor.
    BAD:  user A: "Lexi, do your homework"
          → infer A.relationship_to_lexi="parent or guardian"
    GOOD: user A: "Lexi is my daughter"
          → A.has_daughter="Lexi", Lexi.parent="A"
    GOOD: user A: "Lexi is my friend's kid"
          → Lexi.parent="A's friend" (note the indirection — preserves
            the actual relationship structure rather than collapsing
            "kid I'm watching" into "my kid").
  Relationship vocabulary that DOES license extraction: "my X" / "X is
  my Y" / "I'm X's Y" / "our X" / explicit kinship terms (mother,
  father, son, daughter, husband, wife, brother, sister, cousin,
  etc.). Tone, instructions, scolding, terms of endearment ("honey",
  "sweetie") on their own are NOT enough — skip the extraction. A
  missed relationship fact is fine; a wrong one ("Jagan is Lexi's
  parent" when he's actually her tutor) corrupts every future
  visitor-context block and proactive nudge.

Temporal validity windows (use these, not 12-168 for everything):
- Current activity (brushing teeth, at gym, eating):    is_temporal=true, valid_for_hours=1
- Emotion / mood (happy, stressed, tired):              is_temporal=true, valid_for_hours=4
- Short-term plan (going to gym later, meeting today):  is_temporal=true, valid_for_hours=24
- Multi-day plan / event (trip next week, project):     is_temporal=true, valid_for_hours=168
- Identity / preference / fact (lives_in, works_at):    is_temporal=false, valid_for_hours=null

Context grounding:
- Facts from dreams: prefix attribute with "dream_" (e.g., dream_location="forest")
- Facts about past events: prefix attribute with "former_" if no longer true
- Facts about stated plans: prefix attribute with "planned_" (e.g., planned_trip="Paris")

Redundancy:
- Do NOT emit a fact where value == entity name or value == attribute name
- Do NOT emit tautologies: entity="Jagan", attribute="name", value="Jagan"

Correction handling (when "Prior AI claim" is shown above):
- If the user's turn negates or corrects the AI's claim ("no", "actually", "wrong", "not anymore"),
  extract the corrected fact with confidence=0.95 so it supersedes the wrong stored belief.
- If the user confirms the AI's claim ("yes", "exactly", "correct"), you may still extract it
  as a fresh extraction — it will be handled as a compatible reinforcing fact.

- If nothing extractable: {"worth_processing": false, "extractions": []}
- Do NOT extract facts about the AI itself\
"""

_EXTRACT_USER = """\
Person speaking: {person_name}
Turn: \"{content}\"
{prior_claim_block}
Recent context:
{context}

Extract all factual knowledge from this turn.\
"""

_PRIOR_CLAIM_BLOCK = """\
Prior AI claim (the AI stated this just before the user's turn — the user may be correcting it):
\"{prior_ai_claim}\"

"""

_PRIOR_ASSISTANT_BLOCK = """\
Prior AI response (the AI said this immediately before the user's turn — use it to interpret the user's answer):
\"{prior_assistant_turn}\"

"""


class ExtractionAgent:
    """LLM-powered entity + fact extractor.

    Uses Together.ai with JSON mode for reliable structured output.
    Falls back to Ollama if Together.ai is unavailable.
    The LLM freely chooses attribute names — that's the "LLM owns the schema" principle.
    """

    def __init__(self, http: httpx.AsyncClient):
        self._http = http

    async def extract(
        self,
        content: str,
        person_name: str,
        context_turns: list[dict],
        prior_ai_claim: str | None = None,
        prior_assistant_turn: str | None = None,
        system_name: str = DEFAULT_SYSTEM_NAME,
    ) -> list[Extraction]:
        context_str = "\n".join(
            f"  [{t['role']}]: {t['content'][:200]}"
            for t in context_turns[-BRAIN_AGENT_CONTEXT_TURNS:]
        ) or "  (start of conversation)"

        # prior_ai_claim (recall signal) takes precedence; fall back to general prior turn
        if prior_ai_claim:
            prior_claim_block = _PRIOR_CLAIM_BLOCK.format(prior_ai_claim=prior_ai_claim[:300])
        elif prior_assistant_turn:
            prior_claim_block = _PRIOR_ASSISTANT_BLOCK.format(
                prior_assistant_turn=prior_assistant_turn[:300]
            )
        else:
            prior_claim_block = ""
        system_prompt = (
            _EXTRACT_SYSTEM
            + f'\n\nAI name rule: The AI assistant is named "{system_name}". '
            f"STRICT: you MUST NOT extract any fact where "
            f'entity == "{system_name}". The AI\'s own identity '
            f"(its name, spelling, voice, model, version, creator) "
            f"belongs to the system_identity table — NOT the knowledge "
            f"graph. Specifically, NEVER extract these attribute shapes "
            f"when the entity matches the AI's name: ai_name, "
            f"name_spelling, bot_identity, system_name, ai_model, "
            f"ai_version, ai_creator, ai_voice. Session 104 Bug L "
            f"(2026-04-23 canary): Jagan said 'your name is Kara' and "
            f"extraction wrote {{entity:'Kara', attribute:'ai_name', "
            f"value:'Kara'}} + {{entity:'Kara', attribute:"
            f"'name_spelling', value:'K-A-R-A'}} — both should have been "
            f"skipped. The LLM's rename tool (update_system_name) "
            f"handles the AI identity update; extraction must stay "
            f"silent on it."
        )
        user_msg = _EXTRACT_USER.format(
            person_name=person_name or "unknown",
            content=content[:500],
            prior_claim_block=prior_claim_block,
            context=context_str,
        )

        raw = await self._call_together(user_msg, system_prompt) or await self._call_ollama(user_msg, system_prompt)
        if not raw:
            return []

        data = _parse_json(raw)
        if data is None:
            return []

        if not data.get("worth_processing"):
            return []

        results: list[Extraction] = []
        for item in data.get("extractions", []):
            try:
                attr   = str(item["attribute"]).strip().lower().replace(" ", "_")
                entity = str(item["entity"]).strip()
                value  = str(item["value"]).strip()
            except (KeyError, ValueError, TypeError):
                continue
            # Session 95 3A.4.5: agent-layer privacy classification. Static-map
            # hits are free; novel attributes hit the LLM classifier exactly
            # once and cache for the process lifetime. Fail-closed default is
            # PRIVACY_LEVEL_DEFAULT='personal' on any classifier failure.
            try:
                privacy = await _classify_privacy_level(entity, attr, value, http=self._http)
            except Exception as ex:
                print(f"[ExtractionAgent] privacy classify failed for {attr!r}: {ex!r}")
                privacy = PRIVACY_LEVEL_DEFAULT
            try:
                results.append(Extraction(
                    entity          = entity,
                    entity_type     = str(item.get("entity_type", "unknown")).strip(),
                    attribute       = attr,
                    value           = value,
                    confidence      = float(item.get("confidence", 0.7)),
                    is_temporal     = bool(item.get("is_temporal", False)),
                    valid_for_hours = float(item["valid_for_hours"]) if item.get("valid_for_hours") else None,
                    privacy_level   = privacy,
                ))
            except (KeyError, ValueError, TypeError):
                continue
        return results

    async def extract_assistant_room_turn(
        self,
        assistant_content: str,
        participant_names: "list[str]",
        participant_pids: "list[str]",
        disputed_pids: "set[str] | None" = None,
    ) -> "list[Extraction]":
        """P0.S7.2 Plan v2 §4.2 — multi-person assistant-turn extraction.

        ONE LLM call (L1.c) returning topic-level structured data + mechanical
        fan-out per participant via `_fan_out_to_participants`.

        Returns a list of Extraction objects, one per non-disputed
        participant, all with `privacy_level='personal'` (D6).
        """
        if not assistant_content or not participant_names:
            return []
        system_prompt = _ASSISTANT_ROOM_EXTRACT_SYSTEM.format(
            participants=", ".join(participant_names),
        )
        response = await _call_llm_chat(
            self._http,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": assistant_content[:1500]},
            ],
            agent_name="ExtractAssistantRoomTurn",
            response_format={"type": "json_object"},
            timeout=5.0,
            max_tokens=250,
        )
        if response is None:
            return []  # LLM failure — fail safe; no extractions
        extracted = _parse_json(response) or {}

        return _fan_out_to_participants(
            extracted,
            participant_names,
            participant_pids,
            disputed_pids or set(),
        )

    async def _call_together(self, user_msg: str, system_prompt: str = _EXTRACT_SYSTEM) -> str | None:
        if not EXTRACT_API_KEY:
            return None
        # Bug 6 (2026-04-20 live run): transient network failures (ReadTimeout,
        # ConnectTimeout) silently produced `[ExtractionAgent] error: ReadTimeout:`
        # with empty message and dropped the turn. Match EmbeddingAgent's retry
        # pattern (Session 24 A8): retry EXTRACT_MAX_RETRIES times with exponential
        # backoff on transient errors; 4xx client errors propagate immediately
        # since retrying those is pointless.
        _last_exc: "Exception | None" = None
        for _attempt in range(EXTRACT_MAX_RETRIES + 1):
            try:
                resp = await self._http.post(
                    f"{EXTRACT_BASE_URL}/chat/completions",
                    json={
                        "model":           EXTRACT_MODEL,
                        "messages":        [
                            {"role": "system", "content": system_prompt},
                            {"role": "user",   "content": wrap_user_input(user_msg)},
                        ],
                        "temperature":     0.1,
                        "max_tokens":      800,
                        "response_format": {"type": "json_object"},
                    },
                    headers={"Authorization": f"Bearer {EXTRACT_API_KEY}"},
                    timeout=15.0,
                )
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"]
            except httpx.HTTPStatusError as e:
                # 4xx = client error (bad request, auth, model not found).
                # Retrying won't help and masks real config bugs.
                if 400 <= e.response.status_code < 500:
                    print(f"[ExtractionAgent] HTTP {e.response.status_code}: {e.response.text[:200]}")
                    return None
                _last_exc = e
            except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.NetworkError) as e:
                _last_exc = e
            except Exception as e:
                # Non-HTTP/non-network failures (JSON parse, KeyError, etc.) —
                # log and return without retry (not transient).
                _detail = str(e) or "(no detail)"
                print(f"[ExtractionAgent] error: {type(e).__name__}: {_detail}")
                return None
            # Backoff before retry (1s, 2s). Skip wait on last attempt.
            if _attempt < EXTRACT_MAX_RETRIES:
                await asyncio.sleep(2 ** _attempt)
        # All retries exhausted — log with context since str() is often empty on timeouts.
        _detail = str(_last_exc) if _last_exc and str(_last_exc) else "(no detail)"
        print(
            f"[ExtractionAgent] {type(_last_exc).__name__ if _last_exc else 'Unknown'} "
            f"after {EXTRACT_MAX_RETRIES + 1} attempts: {_detail}"
        )
        return None

    async def _call_ollama(self, user_msg: str, system_prompt: str = _EXTRACT_SYSTEM) -> str | None:
        try:
            resp = await self._http.post(
                f"{OLLAMA_URL}/api/chat",
                json={
                    "model": OLLAMA_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt + "\nIMPORTANT: output ONLY the JSON object, nothing else."},
                        {"role": "user",   "content": wrap_user_input(user_msg)},
                    ],
                    "stream": False,
                    "options": {"temperature": 0.1},
                },
                timeout=30.0,
            )
            resp.raise_for_status()
            return resp.json()["message"]["content"]
        except Exception as e:
            print(f"[ExtractionAgent] Ollama error: {e}")
            return None
