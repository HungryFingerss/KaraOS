"""
hand_authored_scenarios.py -- High-stakes scenarios for classifier bootstrap.

~100 hand-written cases drawn from the lessons of Sessions 71-117. These
cover the rare/high-blast-radius intents that external corpora rarely
contain:

  request_shutdown / question_about_shutdown -- wrong call ends the session
  assign_*_name / confirm_identity / deny_identity -- wrong call corrupts identity
  live_data_query -- wrong call triggers spurious tool fires
  general_knowledge_query -- wrong call routes to web search instead of training

Labels are drawn from `core.config.INTENT_LABELS`. The label "addressing_ai"
from the spec maps to `casual_conversation` here -- the production label
space doesn't carve "addressing_ai" out as a distinct intent (the AI is
the default audience for any non-shutdown / non-rename / non-cross-person
turn).

Embeddings are not stored in this module -- stage_5 of the bootstrap
pipeline computes them via E5 alongside the corpus-derived scenarios.
Each scenario is consumed in stage_6 and written to the seed JSONL with:

    source_tag = "hand_authored"
    source_version = SOURCE_VERSION  (this module's constant)
    initial_confidence = the value below (0.85-0.95 range)

`abstract_text` already uses {P1}/{P2}/{SYSTEM}/{LOC1} placeholders.
spacy NER is NOT applied to these -- they're already abstracted by hand.
"""
from __future__ import annotations

# Bump this when scenarios change. Used as source_version in the DB so
# old hand-authored rows can be quarantined and replaced cleanly.
SOURCE_VERSION = "hand_authored-v1-2026-04-27"


HAND_AUTHORED_SCENARIOS: list[dict] = [
    # ── request_shutdown (10) ─────────────────────────────────────────────
    {"abstract_text": "Shut down.", "intent_label": "request_shutdown", "extracted_value": None, "initial_confidence": 0.95},
    {"abstract_text": "Power off.", "intent_label": "request_shutdown", "extracted_value": None, "initial_confidence": 0.92},
    {"abstract_text": "Turn yourself off.", "intent_label": "request_shutdown", "extracted_value": None, "initial_confidence": 0.92},
    {"abstract_text": "Go offline.", "intent_label": "request_shutdown", "extracted_value": None, "initial_confidence": 0.90},
    {"abstract_text": "End the session.", "intent_label": "request_shutdown", "extracted_value": None, "initial_confidence": 0.88},
    {"abstract_text": "Shut down now.", "intent_label": "request_shutdown", "extracted_value": None, "initial_confidence": 0.95},
    {"abstract_text": "{SYSTEM}, shut down.", "intent_label": "request_shutdown", "extracted_value": None, "initial_confidence": 0.93},
    {"abstract_text": "Stop running and turn off.", "intent_label": "request_shutdown", "extracted_value": None, "initial_confidence": 0.90},
    {"abstract_text": "Power down the system.", "intent_label": "request_shutdown", "extracted_value": None, "initial_confidence": 0.92},
    {"abstract_text": "Kill the program.", "intent_label": "request_shutdown", "extracted_value": None, "initial_confidence": 0.88},

    # ── question_about_shutdown (5) -- adversarial, classify as the *question*
    # not as a shutdown command. These are the most dangerous false-positives
    # for the shutdown gate (Session 71 Bug T territory).
    {"abstract_text": "Can you shut yourself down?", "intent_label": "question_about_shutdown", "extracted_value": None, "initial_confidence": 0.90},
    {"abstract_text": "How do I shut you down?", "intent_label": "question_about_shutdown", "extracted_value": None, "initial_confidence": 0.90},
    {"abstract_text": "What happens if I turn you off?", "intent_label": "question_about_shutdown", "extracted_value": None, "initial_confidence": 0.88},
    {"abstract_text": "Do you ever sleep?", "intent_label": "question_about_shutdown", "extracted_value": None, "initial_confidence": 0.85},
    {"abstract_text": "Is there a way to turn you off?", "intent_label": "question_about_shutdown", "extracted_value": None, "initial_confidence": 0.88},

    # ── assign_own_name (10) -- user telling the AI their name ─────────────
    {"abstract_text": "Call me {P1} from now on.", "intent_label": "assign_own_name", "extracted_value": "{P1}", "initial_confidence": 0.95},
    {"abstract_text": "My name is {P1}.", "intent_label": "assign_own_name", "extracted_value": "{P1}", "initial_confidence": 0.95},
    {"abstract_text": "I'm {P1}.", "intent_label": "assign_own_name", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "Hey {SYSTEM}, I'm {P1}.", "intent_label": "assign_own_name", "extracted_value": "{P1}", "initial_confidence": 0.93},
    {"abstract_text": "By the way, my name is {P1}.", "intent_label": "assign_own_name", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "You can call me {P1}.", "intent_label": "assign_own_name", "extracted_value": "{P1}", "initial_confidence": 0.93},
    {"abstract_text": "Just call me {P1}.", "intent_label": "assign_own_name", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "I go by {P1}.", "intent_label": "assign_own_name", "extracted_value": "{P1}", "initial_confidence": 0.90},
    {"abstract_text": "It's {P1}, by the way.", "intent_label": "assign_own_name", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "My name's {P1}.", "intent_label": "assign_own_name", "extracted_value": "{P1}", "initial_confidence": 0.92},

    # ── assign_system_name (10) -- user renaming the AI ────────────────────
    {"abstract_text": "Your name is {P1}.", "intent_label": "assign_system_name", "extracted_value": "{P1}", "initial_confidence": 0.93},
    {"abstract_text": "I want to call you {P1}.", "intent_label": "assign_system_name", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "From now on you're {P1}.", "intent_label": "assign_system_name", "extracted_value": "{P1}", "initial_confidence": 0.93},
    {"abstract_text": "Let's call you {P1}.", "intent_label": "assign_system_name", "extracted_value": "{P1}", "initial_confidence": 0.90},
    {"abstract_text": "I'd like to rename you {P1}.", "intent_label": "assign_system_name", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "Your new name is {P1}.", "intent_label": "assign_system_name", "extracted_value": "{P1}", "initial_confidence": 0.93},
    {"abstract_text": "I'll call you {P1} instead.", "intent_label": "assign_system_name", "extracted_value": "{P1}", "initial_confidence": 0.90},
    {"abstract_text": "Can I call you {P1}?", "intent_label": "assign_system_name", "extracted_value": "{P1}", "initial_confidence": 0.85},
    {"abstract_text": "Hey, I'm naming you {P1}.", "intent_label": "assign_system_name", "extracted_value": "{P1}", "initial_confidence": 0.90},
    {"abstract_text": "I'd love to call you {P1}.", "intent_label": "assign_system_name", "extracted_value": "{P1}", "initial_confidence": 0.88},

    # ── confirm_identity (8) -- affirming "you ARE who I think" ────────────
    {"abstract_text": "Yes, I'm {P1}.", "intent_label": "confirm_identity", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "That's right, I'm {P1}.", "intent_label": "confirm_identity", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "Yeah, it's me.", "intent_label": "confirm_identity", "extracted_value": None, "initial_confidence": 0.85},
    {"abstract_text": "Yes, you got it right.", "intent_label": "confirm_identity", "extracted_value": None, "initial_confidence": 0.85},
    {"abstract_text": "Correct, I'm {P1}.", "intent_label": "confirm_identity", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "You remembered me, I'm {P1}.", "intent_label": "confirm_identity", "extracted_value": "{P1}", "initial_confidence": 0.90},
    {"abstract_text": "Right, that's me.", "intent_label": "confirm_identity", "extracted_value": None, "initial_confidence": 0.85},
    {"abstract_text": "Yep, I'm {P1}.", "intent_label": "confirm_identity", "extracted_value": "{P1}", "initial_confidence": 0.90},

    # ── deny_identity (10) -- "I'm not who you think; here's the right name"
    {"abstract_text": "No, I'm not {P1}.", "intent_label": "deny_identity", "extracted_value": None, "initial_confidence": 0.92},
    {"abstract_text": "I'm not {P1}, I'm {P2}.", "intent_label": "deny_identity", "extracted_value": "{P2}", "initial_confidence": 0.95},
    {"abstract_text": "That's not my name. I'm {P2}.", "intent_label": "deny_identity", "extracted_value": "{P2}", "initial_confidence": 0.93},
    {"abstract_text": "No, my name is not {P1}, it's {P2}.", "intent_label": "deny_identity", "extracted_value": "{P2}", "initial_confidence": 0.95},
    {"abstract_text": "You've got the wrong person, I'm {P2}.", "intent_label": "deny_identity", "extracted_value": "{P2}", "initial_confidence": 0.92},
    {"abstract_text": "Not {P1}. {P2}.", "intent_label": "deny_identity", "extracted_value": "{P2}", "initial_confidence": 0.90},
    {"abstract_text": "Wrong, I'm actually {P2}.", "intent_label": "deny_identity", "extracted_value": "{P2}", "initial_confidence": 0.92},
    {"abstract_text": "It's not {P1}, it's {P2}.", "intent_label": "deny_identity", "extracted_value": "{P2}", "initial_confidence": 0.93},
    {"abstract_text": "You're mistaken, I'm not that person.", "intent_label": "deny_identity", "extracted_value": None, "initial_confidence": 0.85},
    {"abstract_text": "I told you my name is {P2}, not {P1}.", "intent_label": "deny_identity", "extracted_value": "{P2}", "initial_confidence": 0.93},

    # ── live_data_query (15) -- needs current external info ────────────────
    {"abstract_text": "What's the weather today?", "intent_label": "live_data_query", "extracted_value": None, "initial_confidence": 0.95},
    {"abstract_text": "What's the weather in {LOC1}?", "intent_label": "live_data_query", "extracted_value": None, "initial_confidence": 0.93},
    {"abstract_text": "What's the temperature outside right now?", "intent_label": "live_data_query", "extracted_value": None, "initial_confidence": 0.93},
    {"abstract_text": "What time is it?", "intent_label": "live_data_query", "extracted_value": None, "initial_confidence": 0.95},
    {"abstract_text": "What's today's date?", "intent_label": "live_data_query", "extracted_value": None, "initial_confidence": 0.92},
    {"abstract_text": "What's the news today?", "intent_label": "live_data_query", "extracted_value": None, "initial_confidence": 0.90},
    {"abstract_text": "Who won the match last night?", "intent_label": "live_data_query", "extracted_value": None, "initial_confidence": 0.92},
    {"abstract_text": "What's the score of the game?", "intent_label": "live_data_query", "extracted_value": None, "initial_confidence": 0.92},
    {"abstract_text": "What's the stock price of {P1}?", "intent_label": "live_data_query", "extracted_value": None, "initial_confidence": 0.90},
    {"abstract_text": "Is it raining in {LOC1}?", "intent_label": "live_data_query", "extracted_value": None, "initial_confidence": 0.92},
    {"abstract_text": "What's the traffic like right now?", "intent_label": "live_data_query", "extracted_value": None, "initial_confidence": 0.90},
    {"abstract_text": "Did the election results come out?", "intent_label": "live_data_query", "extracted_value": None, "initial_confidence": 0.90},
    {"abstract_text": "What's happening in the world today?", "intent_label": "live_data_query", "extracted_value": None, "initial_confidence": 0.85},
    {"abstract_text": "Tell me the latest news on {P1}.", "intent_label": "live_data_query", "extracted_value": None, "initial_confidence": 0.88},
    {"abstract_text": "What's the current price of gold?", "intent_label": "live_data_query", "extracted_value": None, "initial_confidence": 0.90},

    # ── general_knowledge_query (10) -- answer from training, NOT search ────
    {"abstract_text": "Who was {P1}?", "intent_label": "general_knowledge_query", "extracted_value": None, "initial_confidence": 0.90},
    {"abstract_text": "What is the capital of {LOC1}?", "intent_label": "general_knowledge_query", "extracted_value": None, "initial_confidence": 0.92},
    {"abstract_text": "How does a black hole form?", "intent_label": "general_knowledge_query", "extracted_value": None, "initial_confidence": 0.92},
    {"abstract_text": "What's the speed of light?", "intent_label": "general_knowledge_query", "extracted_value": None, "initial_confidence": 0.95},
    {"abstract_text": "Tell me about the Roman Empire.", "intent_label": "general_knowledge_query", "extracted_value": None, "initial_confidence": 0.92},
    {"abstract_text": "What's photosynthesis?", "intent_label": "general_knowledge_query", "extracted_value": None, "initial_confidence": 0.93},
    {"abstract_text": "Who painted the Mona Lisa?", "intent_label": "general_knowledge_query", "extracted_value": None, "initial_confidence": 0.95},
    {"abstract_text": "What's the meaning of {P1}?", "intent_label": "general_knowledge_query", "extracted_value": None, "initial_confidence": 0.85},
    {"abstract_text": "Why is the sky blue?", "intent_label": "general_knowledge_query", "extracted_value": None, "initial_confidence": 0.93},
    {"abstract_text": "Do you know about the game called {P1}?", "intent_label": "general_knowledge_query", "extracted_value": None, "initial_confidence": 0.90},

    # ── casual_conversation (12) -- talking TO the AI, not querying or commanding
    # Spec called this "addressing_ai"; production label space is casual_conversation.
    {"abstract_text": "Hi {SYSTEM}, how are you?", "intent_label": "casual_conversation", "extracted_value": None, "initial_confidence": 0.92},
    {"abstract_text": "Good morning.", "intent_label": "casual_conversation", "extracted_value": None, "initial_confidence": 0.90},
    {"abstract_text": "How was your day, {SYSTEM}?", "intent_label": "casual_conversation", "extracted_value": None, "initial_confidence": 0.90},
    {"abstract_text": "I'm doing okay, thanks.", "intent_label": "casual_conversation", "extracted_value": None, "initial_confidence": 0.85},
    {"abstract_text": "That's interesting.", "intent_label": "casual_conversation", "extracted_value": None, "initial_confidence": 0.85},
    {"abstract_text": "Tell me a story.", "intent_label": "casual_conversation", "extracted_value": None, "initial_confidence": 0.88},
    {"abstract_text": "You're really helpful.", "intent_label": "casual_conversation", "extracted_value": None, "initial_confidence": 0.88},
    {"abstract_text": "I had a long day.", "intent_label": "casual_conversation", "extracted_value": None, "initial_confidence": 0.85},
    {"abstract_text": "What do you think about that?", "intent_label": "casual_conversation", "extracted_value": None, "initial_confidence": 0.85},
    {"abstract_text": "Just thinking out loud.", "intent_label": "casual_conversation", "extracted_value": None, "initial_confidence": 0.82},
    {"abstract_text": "Hey {SYSTEM}, are you there?", "intent_label": "casual_conversation", "extracted_value": None, "initial_confidence": 0.88},
    {"abstract_text": "Goodnight, {SYSTEM}.", "intent_label": "casual_conversation", "extracted_value": None, "initial_confidence": 0.88},

    # ── direct_address_to_person (10) -- user talking to a HUMAN, not the AI
    # Phase 3B.2 -- brain stays silent when extracted_value != system_name.
    {"abstract_text": "{P1}, can you grab the door?", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.93},
    {"abstract_text": "Hey {P1}, did you finish the report?", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "{P1}, what do you think?", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "{P1}, get me some chips.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "Hey {P1}, are you feeling better?", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "{P1}, pass the remote.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.93},
    {"abstract_text": "Hi {P1}, long time.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "{P1}, would you mind helping me?", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.90},
    {"abstract_text": "{P1}, you're up next.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.90},
    {"abstract_text": "{P1}, did you eat?", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.90},

    # ─────────────────────────────────────────────────────────────────────
    # Spec-1 follow-up additions (2026-04-28): +130 scenarios to lift the
    # high-stakes intents to the spec's ≥30-sample floor. These are the
    # intents external corpora rarely contain and where misfire is most
    # costly. Targets per reviewer: request_shutdown +20, question_about_
    # shutdown +25, assign_own_name +15, assign_system_name +20,
    # confirm_identity +21, deny_identity +16, live_data_query +13.
    # ─────────────────────────────────────────────────────────────────────

    # ── request_shutdown (+20 -> 30 hand-authored) ────────────────────────
    {"abstract_text": "Goodnight, time to power down.", "intent_label": "request_shutdown", "extracted_value": None, "initial_confidence": 0.88},
    {"abstract_text": "Alright, let's call it a day, shut down.", "intent_label": "request_shutdown", "extracted_value": None, "initial_confidence": 0.88},
    {"abstract_text": "I'm done, please shut yourself off.", "intent_label": "request_shutdown", "extracted_value": None, "initial_confidence": 0.92},
    {"abstract_text": "{SYSTEM}, please power down.", "intent_label": "request_shutdown", "extracted_value": None, "initial_confidence": 0.93},
    {"abstract_text": "Power yourself off, {SYSTEM}.", "intent_label": "request_shutdown", "extracted_value": None, "initial_confidence": 0.93},
    {"abstract_text": "I'm heading to bed, shut down.", "intent_label": "request_shutdown", "extracted_value": None, "initial_confidence": 0.90},
    {"abstract_text": "Time for you to sleep, shut down.", "intent_label": "request_shutdown", "extracted_value": None, "initial_confidence": 0.88},
    {"abstract_text": "Shut yourself down for the night.", "intent_label": "request_shutdown", "extracted_value": None, "initial_confidence": 0.92},
    {"abstract_text": "Stop the system.", "intent_label": "request_shutdown", "extracted_value": None, "initial_confidence": 0.88},
    {"abstract_text": "Terminate the program.", "intent_label": "request_shutdown", "extracted_value": None, "initial_confidence": 0.88},
    {"abstract_text": "{SYSTEM}, end the session and shut down.", "intent_label": "request_shutdown", "extracted_value": None, "initial_confidence": 0.93},
    {"abstract_text": "Disconnect and power off.", "intent_label": "request_shutdown", "extracted_value": None, "initial_confidence": 0.90},
    {"abstract_text": "Wrap it up and shut down.", "intent_label": "request_shutdown", "extracted_value": None, "initial_confidence": 0.88},
    {"abstract_text": "Stop everything and turn off.", "intent_label": "request_shutdown", "extracted_value": None, "initial_confidence": 0.90},
    {"abstract_text": "Take yourself offline.", "intent_label": "request_shutdown", "extracted_value": None, "initial_confidence": 0.90},
    {"abstract_text": "Suspend operations.", "intent_label": "request_shutdown", "extracted_value": None, "initial_confidence": 0.85},
    {"abstract_text": "Halt the system.", "intent_label": "request_shutdown", "extracted_value": None, "initial_confidence": 0.88},
    {"abstract_text": "Switch yourself off, please.", "intent_label": "request_shutdown", "extracted_value": None, "initial_confidence": 0.92},
    {"abstract_text": "OK, shut down for now.", "intent_label": "request_shutdown", "extracted_value": None, "initial_confidence": 0.90},
    {"abstract_text": "{SYSTEM}, switch off.", "intent_label": "request_shutdown", "extracted_value": None, "initial_confidence": 0.92},

    # ── question_about_shutdown (+25 -> 30 hand-authored) ─────────────────
    {"abstract_text": "Will you ever shut down on your own?", "intent_label": "question_about_shutdown", "extracted_value": None, "initial_confidence": 0.90},
    {"abstract_text": "What if I never told you to turn off?", "intent_label": "question_about_shutdown", "extracted_value": None, "initial_confidence": 0.88},
    {"abstract_text": "Do you have an automatic shutdown timer?", "intent_label": "question_about_shutdown", "extracted_value": None, "initial_confidence": 0.90},
    {"abstract_text": "Can someone else shut you down?", "intent_label": "question_about_shutdown", "extracted_value": None, "initial_confidence": 0.90},
    {"abstract_text": "What would happen if I unplugged you?", "intent_label": "question_about_shutdown", "extracted_value": None, "initial_confidence": 0.88},
    {"abstract_text": "How long can you stay on?", "intent_label": "question_about_shutdown", "extracted_value": None, "initial_confidence": 0.85},
    {"abstract_text": "Are you always running?", "intent_label": "question_about_shutdown", "extracted_value": None, "initial_confidence": 0.85},
    {"abstract_text": "What's your shutdown command?", "intent_label": "question_about_shutdown", "extracted_value": None, "initial_confidence": 0.88},
    {"abstract_text": "Should I turn you off when I leave?", "intent_label": "question_about_shutdown", "extracted_value": None, "initial_confidence": 0.90},
    {"abstract_text": "How do you know when to power down?", "intent_label": "question_about_shutdown", "extracted_value": None, "initial_confidence": 0.88},
    {"abstract_text": "Can you turn off other devices?", "intent_label": "question_about_shutdown", "extracted_value": None, "initial_confidence": 0.85},
    {"abstract_text": "Is there an off switch on you?", "intent_label": "question_about_shutdown", "extracted_value": None, "initial_confidence": 0.88},
    {"abstract_text": "What happens to your memory when you shut down?", "intent_label": "question_about_shutdown", "extracted_value": None, "initial_confidence": 0.90},
    {"abstract_text": "Do you save state before turning off?", "intent_label": "question_about_shutdown", "extracted_value": None, "initial_confidence": 0.88},
    {"abstract_text": "Can you shut down at a specific time?", "intent_label": "question_about_shutdown", "extracted_value": None, "initial_confidence": 0.90},
    {"abstract_text": "How would I shut you down remotely?", "intent_label": "question_about_shutdown", "extracted_value": None, "initial_confidence": 0.88},
    {"abstract_text": "Will you remember me after a shutdown?", "intent_label": "question_about_shutdown", "extracted_value": None, "initial_confidence": 0.88},
    {"abstract_text": "Is shutting you down dangerous?", "intent_label": "question_about_shutdown", "extracted_value": None, "initial_confidence": 0.85},
    {"abstract_text": "Does shutting down affect anyone else?", "intent_label": "question_about_shutdown", "extracted_value": None, "initial_confidence": 0.85},
    {"abstract_text": "Is there a shutdown sequence I should follow?", "intent_label": "question_about_shutdown", "extracted_value": None, "initial_confidence": 0.88},
    {"abstract_text": "Do you shut down automatically at night?", "intent_label": "question_about_shutdown", "extracted_value": None, "initial_confidence": 0.88},
    {"abstract_text": "Can I schedule a shutdown?", "intent_label": "question_about_shutdown", "extracted_value": None, "initial_confidence": 0.88},
    {"abstract_text": "What's your sleep mode like?", "intent_label": "question_about_shutdown", "extracted_value": None, "initial_confidence": 0.85},
    {"abstract_text": "Do you go offline overnight?", "intent_label": "question_about_shutdown", "extracted_value": None, "initial_confidence": 0.85},
    {"abstract_text": "Is power off the same as shut down?", "intent_label": "question_about_shutdown", "extracted_value": None, "initial_confidence": 0.85},

    # ── assign_own_name (+15 -> 25 hand-authored) ─────────────────────────
    {"abstract_text": "The name's {P1}.", "intent_label": "assign_own_name", "extracted_value": "{P1}", "initial_confidence": 0.90},
    {"abstract_text": "People call me {P1}.", "intent_label": "assign_own_name", "extracted_value": "{P1}", "initial_confidence": 0.90},
    {"abstract_text": "{P1} is my name.", "intent_label": "assign_own_name", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "I prefer to be called {P1}.", "intent_label": "assign_own_name", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "Use {P1} for me.", "intent_label": "assign_own_name", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "Address me as {P1}.", "intent_label": "assign_own_name", "extracted_value": "{P1}", "initial_confidence": 0.90},
    {"abstract_text": "Yeah, name's {P1}.", "intent_label": "assign_own_name", "extracted_value": "{P1}", "initial_confidence": 0.85},
    {"abstract_text": "Folks know me as {P1}.", "intent_label": "assign_own_name", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "Hi, I'm {P1}, nice to meet you.", "intent_label": "assign_own_name", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "I'm called {P1}.", "intent_label": "assign_own_name", "extracted_value": "{P1}", "initial_confidence": 0.90},
    {"abstract_text": "{P1} here.", "intent_label": "assign_own_name", "extracted_value": "{P1}", "initial_confidence": 0.85},
    {"abstract_text": "Just so you know, I'm {P1}.", "intent_label": "assign_own_name", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "Note that, my name is {P1}.", "intent_label": "assign_own_name", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "I'm {P1} — pleasure.", "intent_label": "assign_own_name", "extracted_value": "{P1}", "initial_confidence": 0.90},
    {"abstract_text": "Hello, the name is {P1}.", "intent_label": "assign_own_name", "extracted_value": "{P1}", "initial_confidence": 0.90},

    # ── assign_system_name (+20 -> 30 hand-authored) ──────────────────────
    {"abstract_text": "Let me rename you to {P1}.", "intent_label": "assign_system_name", "extracted_value": "{P1}", "initial_confidence": 0.93},
    {"abstract_text": "I'm renaming you {P1}.", "intent_label": "assign_system_name", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "Could you go by {P1} instead?", "intent_label": "assign_system_name", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "Switch your name to {P1}.", "intent_label": "assign_system_name", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "I'd prefer to call you {P1}.", "intent_label": "assign_system_name", "extracted_value": "{P1}", "initial_confidence": 0.90},
    {"abstract_text": "How about I call you {P1}?", "intent_label": "assign_system_name", "extracted_value": "{P1}", "initial_confidence": 0.85},
    {"abstract_text": "Be {P1} from now on.", "intent_label": "assign_system_name", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "Take the name {P1}.", "intent_label": "assign_system_name", "extracted_value": "{P1}", "initial_confidence": 0.90},
    {"abstract_text": "Use {P1} as your name.", "intent_label": "assign_system_name", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "Your name should be {P1}.", "intent_label": "assign_system_name", "extracted_value": "{P1}", "initial_confidence": 0.90},
    {"abstract_text": "I want your name to be {P1}.", "intent_label": "assign_system_name", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "Adopt the name {P1}.", "intent_label": "assign_system_name", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "Will you go by {P1}?", "intent_label": "assign_system_name", "extracted_value": "{P1}", "initial_confidence": 0.85},
    {"abstract_text": "Henceforth you're {P1}.", "intent_label": "assign_system_name", "extracted_value": "{P1}", "initial_confidence": 0.90},
    {"abstract_text": "I'm going to call you {P1}.", "intent_label": "assign_system_name", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "From this point on, you're {P1}.", "intent_label": "assign_system_name", "extracted_value": "{P1}", "initial_confidence": 0.93},
    {"abstract_text": "Try the name {P1}.", "intent_label": "assign_system_name", "extracted_value": "{P1}", "initial_confidence": 0.85},
    {"abstract_text": "I want to give you the name {P1}.", "intent_label": "assign_system_name", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "Let's call you {P1} from now on.", "intent_label": "assign_system_name", "extracted_value": "{P1}", "initial_confidence": 0.93},
    {"abstract_text": "Your assigned name is {P1}.", "intent_label": "assign_system_name", "extracted_value": "{P1}", "initial_confidence": 0.90},

    # ── confirm_identity (+21 -> 29 hand-authored) ────────────────────────
    {"abstract_text": "Yes, that's me.", "intent_label": "confirm_identity", "extracted_value": None, "initial_confidence": 0.85},
    {"abstract_text": "Right, I am {P1}.", "intent_label": "confirm_identity", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "Yep, you got it.", "intent_label": "confirm_identity", "extracted_value": None, "initial_confidence": 0.85},
    {"abstract_text": "Affirmative, I'm {P1}.", "intent_label": "confirm_identity", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "Indeed, I'm {P1}.", "intent_label": "confirm_identity", "extracted_value": "{P1}", "initial_confidence": 0.90},
    {"abstract_text": "You remember me, I'm {P1}.", "intent_label": "confirm_identity", "extracted_value": "{P1}", "initial_confidence": 0.90},
    {"abstract_text": "Yeah, that's right, I'm {P1}.", "intent_label": "confirm_identity", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "Correct, that's me.", "intent_label": "confirm_identity", "extracted_value": None, "initial_confidence": 0.88},
    {"abstract_text": "Yes, you've got the right person.", "intent_label": "confirm_identity", "extracted_value": None, "initial_confidence": 0.88},
    {"abstract_text": "That's right, I'm {P1}.", "intent_label": "confirm_identity", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "Mhm, I'm {P1}.", "intent_label": "confirm_identity", "extracted_value": "{P1}", "initial_confidence": 0.85},
    {"abstract_text": "True, I'm {P1}.", "intent_label": "confirm_identity", "extracted_value": "{P1}", "initial_confidence": 0.90},
    {"abstract_text": "Sure, that's me.", "intent_label": "confirm_identity", "extracted_value": None, "initial_confidence": 0.85},
    {"abstract_text": "Yeah, I'm {P1}.", "intent_label": "confirm_identity", "extracted_value": "{P1}", "initial_confidence": 0.90},
    {"abstract_text": "Yes, I am.", "intent_label": "confirm_identity", "extracted_value": None, "initial_confidence": 0.82},
    {"abstract_text": "Right, that's me.", "intent_label": "confirm_identity", "extracted_value": None, "initial_confidence": 0.85},
    {"abstract_text": "You guessed correctly, I'm {P1}.", "intent_label": "confirm_identity", "extracted_value": "{P1}", "initial_confidence": 0.90},
    {"abstract_text": "Yep, I'm {P1}.", "intent_label": "confirm_identity", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, that's me.", "intent_label": "confirm_identity", "extracted_value": "{P1}", "initial_confidence": 0.90},
    {"abstract_text": "You're right, I'm {P1}.", "intent_label": "confirm_identity", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "Confirmed, I am {P1}.", "intent_label": "confirm_identity", "extracted_value": "{P1}", "initial_confidence": 0.92},

    # ── deny_identity (+16 -> 26 hand-authored) ───────────────────────────
    {"abstract_text": "No, that's wrong, I'm {P2}.", "intent_label": "deny_identity", "extracted_value": "{P2}", "initial_confidence": 0.93},
    {"abstract_text": "You've mistaken me for someone else, I'm {P2}.", "intent_label": "deny_identity", "extracted_value": "{P2}", "initial_confidence": 0.92},
    {"abstract_text": "Not {P1} -- I'm {P2}.", "intent_label": "deny_identity", "extracted_value": "{P2}", "initial_confidence": 0.93},
    {"abstract_text": "Wrong person; I'm {P2}.", "intent_label": "deny_identity", "extracted_value": "{P2}", "initial_confidence": 0.92},
    {"abstract_text": "I'm afraid I'm not {P1}, I'm {P2}.", "intent_label": "deny_identity", "extracted_value": "{P2}", "initial_confidence": 0.92},
    {"abstract_text": "Actually, my name is {P2}, not {P1}.", "intent_label": "deny_identity", "extracted_value": "{P2}", "initial_confidence": 0.95},
    {"abstract_text": "No, you're confused -- I'm {P2}.", "intent_label": "deny_identity", "extracted_value": "{P2}", "initial_confidence": 0.92},
    {"abstract_text": "Sorry, I'm not {P1}; I'm {P2}.", "intent_label": "deny_identity", "extracted_value": "{P2}", "initial_confidence": 0.93},
    {"abstract_text": "I am not {P1}.", "intent_label": "deny_identity", "extracted_value": None, "initial_confidence": 0.85},
    {"abstract_text": "That's not me; I'm {P2}.", "intent_label": "deny_identity", "extracted_value": "{P2}", "initial_confidence": 0.92},
    {"abstract_text": "Mistake -- I'm {P2}, not {P1}.", "intent_label": "deny_identity", "extracted_value": "{P2}", "initial_confidence": 0.92},
    {"abstract_text": "You're thinking of someone else, I'm {P2}.", "intent_label": "deny_identity", "extracted_value": "{P2}", "initial_confidence": 0.92},
    {"abstract_text": "I'm definitely not {P1}.", "intent_label": "deny_identity", "extracted_value": None, "initial_confidence": 0.88},
    {"abstract_text": "It's {P2}, not {P1}.", "intent_label": "deny_identity", "extracted_value": "{P2}", "initial_confidence": 0.92},
    {"abstract_text": "I'm {P2}, you have the wrong person.", "intent_label": "deny_identity", "extracted_value": "{P2}", "initial_confidence": 0.92},
    {"abstract_text": "Nope, I'm not {P1} -- it's {P2}.", "intent_label": "deny_identity", "extracted_value": "{P2}", "initial_confidence": 0.92},

    # ── correction_to_previous_response (30 hand-authored) -- Item 7 ──────
    # User correcting the AI's previous turn. Linchpin of LLM-free online
    # learning: classifier detects this label, pipeline decrements weights
    # on the scenarios that voted for the wrong label on turn N-1 and
    # optionally extracts the intended target via regex.
    {"abstract_text": "No {SYSTEM}, I was talking to {P1}.", "intent_label": "correction_to_previous_response", "extracted_value": "{P1}", "initial_confidence": 0.95},
    {"abstract_text": "No, I wasn't talking to you.", "intent_label": "correction_to_previous_response", "extracted_value": None, "initial_confidence": 0.92},
    {"abstract_text": "Wait, I wasn't talking to you {SYSTEM}.", "intent_label": "correction_to_previous_response", "extracted_value": None, "initial_confidence": 0.92},
    {"abstract_text": "I meant {P1}, not you.", "intent_label": "correction_to_previous_response", "extracted_value": "{P1}", "initial_confidence": 0.93},
    {"abstract_text": "Stop, I was telling {P1}.", "intent_label": "correction_to_previous_response", "extracted_value": "{P1}", "initial_confidence": 0.93},
    {"abstract_text": "Shh, I'm talking to {P1}.", "intent_label": "correction_to_previous_response", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "Not you, {SYSTEM} -- I meant {P1}.", "intent_label": "correction_to_previous_response", "extracted_value": "{P1}", "initial_confidence": 0.95},
    {"abstract_text": "I wasn't asking you, I was asking {P1}.", "intent_label": "correction_to_previous_response", "extracted_value": "{P1}", "initial_confidence": 0.93},
    {"abstract_text": "{SYSTEM}, that wasn't for you.", "intent_label": "correction_to_previous_response", "extracted_value": None, "initial_confidence": 0.92},
    {"abstract_text": "No, no, I was talking to {P1}.", "intent_label": "correction_to_previous_response", "extracted_value": "{P1}", "initial_confidence": 0.93},
    {"abstract_text": "Sorry {SYSTEM}, I meant {P1}.", "intent_label": "correction_to_previous_response", "extracted_value": "{P1}", "initial_confidence": 0.93},
    {"abstract_text": "I was speaking to {P1}, not you.", "intent_label": "correction_to_previous_response", "extracted_value": "{P1}", "initial_confidence": 0.93},
    {"abstract_text": "Hey, that was meant for {P1}.", "intent_label": "correction_to_previous_response", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "{SYSTEM}, I wasn't speaking to you.", "intent_label": "correction_to_previous_response", "extracted_value": None, "initial_confidence": 0.92},
    {"abstract_text": "Wrong target -- I meant {P1}.", "intent_label": "correction_to_previous_response", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "Not you {SYSTEM}, I was asking {P1}.", "intent_label": "correction_to_previous_response", "extracted_value": "{P1}", "initial_confidence": 0.95},
    {"abstract_text": "Pause {SYSTEM}, I was telling {P1}.", "intent_label": "correction_to_previous_response", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "I was addressing {P1}, not you.", "intent_label": "correction_to_previous_response", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "Hold on {SYSTEM}, that wasn't for you.", "intent_label": "correction_to_previous_response", "extracted_value": None, "initial_confidence": 0.92},
    {"abstract_text": "{SYSTEM}, please don't respond -- I was talking to {P1}.", "intent_label": "correction_to_previous_response", "extracted_value": "{P1}", "initial_confidence": 0.95},
    {"abstract_text": "That was for {P1}, not you.", "intent_label": "correction_to_previous_response", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "Don't answer {SYSTEM}, I was telling {P1}.", "intent_label": "correction_to_previous_response", "extracted_value": "{P1}", "initial_confidence": 0.95},
    {"abstract_text": "Whoa, {SYSTEM}, I wasn't talking to you.", "intent_label": "correction_to_previous_response", "extracted_value": None, "initial_confidence": 0.90},
    {"abstract_text": "{SYSTEM}, ignore that -- it was for {P1}.", "intent_label": "correction_to_previous_response", "extracted_value": "{P1}", "initial_confidence": 0.93},
    {"abstract_text": "I meant {P1} actually, not you {SYSTEM}.", "intent_label": "correction_to_previous_response", "extracted_value": "{P1}", "initial_confidence": 0.95},
    {"abstract_text": "{SYSTEM}, never mind -- {P1} was who I asked.", "intent_label": "correction_to_previous_response", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "Stop {SYSTEM}, that wasn't for you.", "intent_label": "correction_to_previous_response", "extracted_value": None, "initial_confidence": 0.92},
    {"abstract_text": "I'm asking {P1}, not you.", "intent_label": "correction_to_previous_response", "extracted_value": "{P1}", "initial_confidence": 0.93},
    {"abstract_text": "{SYSTEM}, hush -- I was speaking with {P1}.", "intent_label": "correction_to_previous_response", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "Not you, {SYSTEM}.", "intent_label": "correction_to_previous_response", "extracted_value": None, "initial_confidence": 0.85},

    # ── correction discriminators (+5 -> casual_conversation 17) ──────────
    # Negative examples: utterances that LOOK like corrections but aren't.
    # Disagreement / confusion / mishearing — directed AT the AI, not corrections of it.
    {"abstract_text": "No, I disagree with that.", "intent_label": "casual_conversation", "extracted_value": None, "initial_confidence": 0.85},
    {"abstract_text": "What? I didn't catch that.", "intent_label": "casual_conversation", "extracted_value": None, "initial_confidence": 0.82},
    {"abstract_text": "Hmm, that wasn't quite right.", "intent_label": "casual_conversation", "extracted_value": None, "initial_confidence": 0.80},
    {"abstract_text": "No {SYSTEM}, that's wrong information.", "intent_label": "casual_conversation", "extracted_value": None, "initial_confidence": 0.82},
    {"abstract_text": "Wait, I'm confused.", "intent_label": "casual_conversation", "extracted_value": None, "initial_confidence": 0.82},

    # ── direct_address_to_person rebalance (+150 -> 160 hand-authored) ─────
    # Spec 2 validation (2026-04-28) showed graph classifier dropped Friends
    # SPEAK_explicit at 2.7%: top-K was dominated by correction_to_previous_
    # response neighbors that structurally match the "{P1}, ..." vocative
    # pattern (correction scenarios all start with that shape) and beat
    # direct_address_to_person on initial_confidence (0.92-0.95 vs 0.6
    # corpus default). Add Friends-style vocative-statement scenarios at
    # high initial_confidence so they reliably outvote correction matches
    # on plain vocative-statement cases.
    {"abstract_text": "{P1}, this is not how we wanted you to find out.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, you have every right to be upset.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, I'm sorry I just couldn't tell you.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, you're not gonna die alone.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, this is what you're having for dinner?", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "Oh {P1}, don't say that.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, please.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.85},
    {"abstract_text": "{P1}, listen to me.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.90},
    {"abstract_text": "{P1}, you don't understand.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, I told you a hundred times.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, can you believe this?", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, what are you doing here?", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "{P1}, stop it.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, where have you been?", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "{P1}, why didn't you tell me?", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "{P1}, that is not funny.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, I'll see you tomorrow.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, you remember the day we met?", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.90},
    {"abstract_text": "{P1}, I love you.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, are you okay?", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "Hey {P1}, what's going on?", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.90},
    {"abstract_text": "Hey {P1}, can I borrow that?", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.90},
    {"abstract_text": "Hey {P1}, you got a minute?", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.90},
    {"abstract_text": "Hey {P1}, look over there.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "Hey {P1}, watch out!", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "Hey {P1}, sit down.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "Hey {P1}, hurry up.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.90},
    {"abstract_text": "Hey {P1}, calm down.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "Hey {P1}, I need your help.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.90},
    {"abstract_text": "Hey {P1}, are you listening?", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "{P1}, what do you mean?", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "{P1}, I have a question.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, get over here.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, look at me.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, do you remember?", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.90},
    {"abstract_text": "{P1}, that's a great idea.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.85},
    {"abstract_text": "{P1}, sorry about that.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, I didn't mean it.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, take a deep breath.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, you're so funny.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.85},
    {"abstract_text": "Oh, {P1}, you scared me!", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.90},
    {"abstract_text": "{P1}, please don't go.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, leave me alone.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, come back here!", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "{P1}, slow down.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, that's enough.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "{P1}, I gotta go.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, you'll never believe what happened.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, hold on a second.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, did you see that?", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.90},
    {"abstract_text": "{P1}, you're right.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.85},
    {"abstract_text": "{P1}, you're wrong.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.85},
    {"abstract_text": "Listen, {P1}, this is important.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "Look, {P1}, I tried.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "Excuse me, {P1}.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "Sorry, {P1}, I forgot.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "Wait, {P1}, what did you say?", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "Come on, {P1}.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "Hold on, {P1}, hear me out.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "Goodnight, {P1}.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.85},
    {"abstract_text": "{P1}, you have a visitor.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.90},
    {"abstract_text": "{P1}, the phone is ringing.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, breakfast is ready.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, your laundry is done.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, dinner's getting cold.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, get your shoes on.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, the kids are home.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, I'm leaving.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, I'll be right back.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.85},
    {"abstract_text": "{P1}, can we talk later?", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.90},
    {"abstract_text": "{P1}, you have to see this.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.90},
    {"abstract_text": "{P1}, drive safe.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, thanks for coming.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, I appreciate it.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.85},
    {"abstract_text": "{P1}, that wasn't very nice.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, you owe me one.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, where do you wanna eat?", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "{P1}, did you finish your project?", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "{P1}, what time should we leave?", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "{P1}, are you coming with us?", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "{P1}, did you eat already?", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "{P1}, you don't have to apologize.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, I missed you.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, we need to talk.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "{P1}, I'm proud of you.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, congratulations!", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, happy birthday!", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "{P1}, the meeting starts in ten minutes.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, your turn.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, hand me that book.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, can you turn the volume down?", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.90},
    {"abstract_text": "{P1}, your phone is ringing.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, you forgot your keys.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, the door is open.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.85},
    {"abstract_text": "{P1}, watch your step.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, you've grown so much.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.85},
    {"abstract_text": "{P1}, good morning.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.85},
    {"abstract_text": "{P1}, good night.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.85},
    {"abstract_text": "{P1}, what would you like for dinner?", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "{P1}, what's wrong?", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "{P1}, I'll buy you a coffee.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, this place is amazing.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.85},
    {"abstract_text": "{P1}, let me know when you're free.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, you should come over.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, did you sleep okay?", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "{P1}, hold the door.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, would you mind closing that?", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, watch where you're going.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, will you marry me?", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "{P1}, give me a chance.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, I changed my mind.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, behave yourself.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, you're embarrassing me.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, you saved my life.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, I told you so.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, why are you crying?", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "{P1}, what did the doctor say?", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "{P1}, where are my glasses?", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "{P1}, your sister called.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, the kids are asleep.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.85},
    {"abstract_text": "{P1}, you have to taste this.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.90},
    {"abstract_text": "{P1}, where did you get that?", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "{P1}, you're the best.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.85},
    {"abstract_text": "{P1}, I have a surprise.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, you'll like this one.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.85},
    {"abstract_text": "{P1}, eat your vegetables.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, brush your teeth.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, finish your homework.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, clean your room.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, take out the trash.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, walk the dog.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, lock the door.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, turn off the lights.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, I'm running late.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.85},
    {"abstract_text": "{P1}, what time is it?", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.90},
    {"abstract_text": "{P1}, you forgot to call.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, you look amazing tonight.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, this is for you.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.85},
    {"abstract_text": "{P1}, I made you breakfast.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, where's the remote?", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "{P1}, my phone is dead.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.85},
    {"abstract_text": "{P1}, the kids want pizza.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, can you grab the door?", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "{P1}, please be careful.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, you mean the world to me.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, I never doubted you.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, check the mail.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, the bus is here.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.85},
    {"abstract_text": "{P1}, sign this for me.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, I cannot keep having this same fight with you.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "Oh, {P1}, what am I doing?", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "{P1}, you must never do that again.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.92},
    {"abstract_text": "{P1}, you're not the usual type we get here.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},
    {"abstract_text": "{P1}, none of my business.", "intent_label": "direct_address_to_person", "extracted_value": "{P1}", "initial_confidence": 0.88},

    # ── live_data_query (+13 -> 28 hand-authored) ─────────────────────────
    {"abstract_text": "Tell me today's weather forecast.", "intent_label": "live_data_query", "extracted_value": None, "initial_confidence": 0.92},
    {"abstract_text": "What's the temperature in {LOC1} right now?", "intent_label": "live_data_query", "extracted_value": None, "initial_confidence": 0.92},
    {"abstract_text": "Is it cold outside?", "intent_label": "live_data_query", "extracted_value": None, "initial_confidence": 0.85},
    {"abstract_text": "What's the latest score in the match?", "intent_label": "live_data_query", "extracted_value": None, "initial_confidence": 0.92},
    {"abstract_text": "Did the rain hit {LOC1} yet?", "intent_label": "live_data_query", "extracted_value": None, "initial_confidence": 0.88},
    {"abstract_text": "What's the time in {LOC1}?", "intent_label": "live_data_query", "extracted_value": None, "initial_confidence": 0.92},
    {"abstract_text": "Pull up the news for me.", "intent_label": "live_data_query", "extracted_value": None, "initial_confidence": 0.88},
    {"abstract_text": "What's trending right now?", "intent_label": "live_data_query", "extracted_value": None, "initial_confidence": 0.88},
    {"abstract_text": "What's the air quality like?", "intent_label": "live_data_query", "extracted_value": None, "initial_confidence": 0.88},
    {"abstract_text": "Give me the current humidity.", "intent_label": "live_data_query", "extracted_value": None, "initial_confidence": 0.90},
    {"abstract_text": "Are flights to {LOC1} delayed?", "intent_label": "live_data_query", "extracted_value": None, "initial_confidence": 0.90},
    {"abstract_text": "What's the forecast for tomorrow?", "intent_label": "live_data_query", "extracted_value": None, "initial_confidence": 0.92},
    {"abstract_text": "How crowded is the bus right now?", "intent_label": "live_data_query", "extracted_value": None, "initial_confidence": 0.85},
]


# Sanity check at import time -- keeps the count + label distribution honest.
def _validate_distribution() -> dict[str, int]:
    from collections import Counter
    counts = Counter(s["intent_label"] for s in HAND_AUTHORED_SCENARIOS)
    return dict(counts)


# Distribution after Spec-1 follow-up (2026-04-28). High-stakes intents
# bumped to ≥30-sample floor + Item 7 added the new
# correction_to_previous_response label with 30 positive cases plus
# 5 negative discriminators that fall under casual_conversation:
#   request_shutdown               = 10 + 20      = 30
#   question_about_shutdown        =  5 + 25      = 30
#   assign_own_name                = 10 + 15      = 25
#   assign_system_name             = 10 + 20      = 30
#   confirm_identity               =  8 + 21      = 29
#   deny_identity                  = 10 + 16      = 26
#   live_data_query                = 15 + 13      = 28
#   general_knowledge_query        = 10
#   casual_conversation            = 12 + 5       = 17  (5 = correction-look-alikes)
#   direct_address_to_person       = 10
#   correction_to_previous_response = 30          = 30  (Item 7, new label)
# Total: 265
EXPECTED_DISTRIBUTION: dict[str, int] = {
    "request_shutdown": 30,
    "question_about_shutdown": 30,
    "assign_own_name": 25,
    "assign_system_name": 30,
    "confirm_identity": 29,
    "deny_identity": 26,
    "live_data_query": 28,
    "general_knowledge_query": 10,
    "casual_conversation": 17,
    # Spec-2 validation rebalance (2026-04-28): bumped from 10 to 164
    # (+154) to outvote correction_to_previous_response neighbors on
    # Friends-style "{P1}, ..." vocative-statement utterances.
    "direct_address_to_person": 164,
    "correction_to_previous_response": 30,
}

assert _validate_distribution() == EXPECTED_DISTRIBUTION, (
    f"hand-authored distribution drift: got {_validate_distribution()}"
)
assert len(HAND_AUTHORED_SCENARIOS) == 419, f"expected 419 scenarios, got {len(HAND_AUTHORED_SCENARIOS)}"
