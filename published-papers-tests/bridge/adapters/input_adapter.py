"""Source row → classifier inputs. Touches ONLY the 4 allowed fields.

ALLOWED fields (read freely):
  - target_speaker
  - all_speakers
  - context_turns
  - current_turn

FORBIDDEN fields (must NEVER be read here — would leak the answer):
  - decision
  - target_is_addressed
  - addressees_in_current
  - category
  - reason
  - confidence

If a future edit references any name in the FORBIDDEN list inside this
file, that's a code review red flag. The strict folder split exists to
make this easy to grep for.
"""
from __future__ import annotations


def build_classifier_inputs(sample: dict) -> tuple[str, list[dict]]:
    """Translate one source row into (user_text, conversation_history)
    matching the calling convention of `core.brain._classify_intent`.

    Returns
    -------
    user_text : str
        The current_turn["text"] — what the classifier judges. Raw
        text, no speaker prefix, no labels.
    conversation_history : list[dict]
        Standard chat-message list. First entry is a system message
        that establishes Kara-OS's identity as ``target_speaker`` and
        names the other participants — the classifier in production
        knows its own name and the room roster via face/voice
        recognition, so passing this is a fair scene-state hand-off,
        not a hint. Subsequent entries are ``{"role": "user",
        "content": "{speaker}: {text}"}`` for each context turn.
    """
    target_speaker = (sample["target_speaker"] or "").strip()
    all_speakers   = sample.get("all_speakers") or []
    context_turns  = sample.get("context_turns") or []
    current_turn   = sample.get("current_turn") or {}

    user_text = (current_turn.get("text") or "").strip()

    # Establish AI identity = target_speaker so the classifier's
    # "addressing_ai" intent maps cleanly to "target_speaker is being
    # addressed → SPEAK" in the output_mapper. Roster lists everyone
    # else in the room — the classifier in production has this same
    # info from face + voice recognition, so passing it is fair scene
    # state, not a hint about the answer.
    others = [
        s for s in all_speakers
        if (s or "").strip().lower() != target_speaker.lower()
    ]
    system_content = (
        f"You are {target_speaker}. "
        f"The other people in this room are: "
        f"{', '.join(others) if others else '(none)'}."
    )

    conversation_history: list[dict] = [
        {"role": "system", "content": system_content},
    ]
    for turn in context_turns:
        speaker = (turn.get("speaker") or "").strip()
        text    = (turn.get("text") or "").strip()
        if not text:
            continue
        conversation_history.append({
            "role":    "user",
            "content": f"{speaker}: {text}" if speaker else text,
        })

    return user_text, conversation_history
