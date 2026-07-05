# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors
"""100% line coverage for runtime.text — pure text/name/intent-gating helpers.
Part of the coverage-to-100 campaign (see COVERAGE.md).

Targets the previously-uncovered lines 103 (no-capture-group ``continue`` in
``_user_text_gate_passes``) and 286-288 (the ``no`` / ``unclear`` branches of
``_detect_yes_no``), plus comprehensive regression coverage of every helper.
These are pure functions — ``core.sanitize`` (re + unicodedata) and
``core.config`` (os + pathlib + dotenv) import headless with no GPU / camera /
network / model downloads, so nothing needs mocking.
"""

import pytest

from runtime.text import (
    sanitize_name,
    _user_text_gate_passes,
    _nfkc_lower,
    _strip_im_contraction,
    _intent_allows,
    _detect_yes_no,
)


# ─────────────────────────────────────────────────────────────────────────────
# sanitize_name
# ─────────────────────────────────────────────────────────────────────────────

def test_sanitize_name_extracts_from_call_me_phrase():
    # _NAME_EXTRACT_RE matches "call me Jagan" anywhere; first word taken.
    display, safe = sanitize_name("People call me Jagan")
    assert display == "Jagan"
    assert safe == "jagan"


def test_sanitize_name_extracts_first_word_of_multiword():
    # "Sarah Jane" -> first word "Sarah" (len >= 2 keeps the first word).
    display, safe = sanitize_name("my name is Sarah Jane")
    assert display == "Sarah"
    assert safe == "sarah"


def test_sanitize_name_keeps_multiword_when_first_word_single_char():
    # first word "A" has len 1 (< 2) -> line 45 else-branch keeps full extracted.
    display, safe = sanitize_name("call me A B")
    assert display == "A B"
    assert safe == "a_b"


def test_sanitize_name_fallback_no_extract_pattern_bare_name():
    # "Rex" matches neither _NAME_EXTRACT_RE nor a _PHRASE_PREFIXES prefix ->
    # else fallback (lines 47-50) keeps it verbatim.
    display, safe = sanitize_name("Rex")
    assert display == "Rex"
    assert safe == "rex"


def test_sanitize_name_fallback_strips_its_prefix():
    # "It's Bob": _NAME_EXTRACT_RE has no "it's" alternative, so search() fails
    # and the fallback strips the _PHRASE_PREFIXES "it's " head.
    display, safe = sanitize_name("It's Bob")
    assert display == "Bob"
    assert safe == "bob"


def test_sanitize_name_fallback_single_char_kept():
    # fallback path with a 1-char stripped result -> line 50 else keeps stripped,
    # line 51 else-branch falls through to `text`.
    display, safe = sanitize_name("a")
    assert display == "a"
    assert safe == "a"


def test_sanitize_name_empty_yields_unknown_safe():
    # Empty input -> display "" and safe collapses to the "unknown" fallback
    # (lines 51 else-branch, 54-55).
    display, safe = sanitize_name("   ")
    assert display == ""
    assert safe == "unknown"


def test_sanitize_name_collapses_and_strips_special_chars():
    # Interior "." specials -> "_" then collapsed to single "_" and stripped.
    display, safe = sanitize_name("call me Bob..Smith")
    assert display == "Bob..Smith"
    assert safe == "bob_smith"


def test_sanitize_name_truncates_to_50_chars():
    long = "call me " + "z" * 80
    display, safe = sanitize_name(long)
    assert len(display) <= 50
    assert len(safe) <= 50


# ─────────────────────────────────────────────────────────────────────────────
# _nfkc_lower
# ─────────────────────────────────────────────────────────────────────────────

def test_nfkc_lower_none_returns_empty():
    assert _nfkc_lower(None) == ""


def test_nfkc_lower_casefolds():
    assert _nfkc_lower("HELLO") == "hello"


def test_nfkc_lower_normalizes_fullwidth_then_casefolds():
    # U+FF21 FULLWIDTH LATIN A -> "A" (NFKC) -> "a" (casefold).
    assert _nfkc_lower("Ａbc") == "abc"


# ─────────────────────────────────────────────────────────────────────────────
# _strip_im_contraction
# ─────────────────────────────────────────────────────────────────────────────

def test_strip_im_contraction_compressed_no_space():
    # Whisper's "Imlexi" (no space, lowercase name) -> "lexi".
    assert _strip_im_contraction("Imlexi") == "lexi"


def test_strip_im_contraction_unicode_apostrophe():
    assert _strip_im_contraction("I’mkara") == "kara"


def test_strip_im_contraction_ascii_apostrophe_no_space():
    assert _strip_im_contraction("I'mbob") == "bob"


def test_strip_im_contraction_spaced_form_unchanged():
    # "I'm Bob" has a space after 'm -> the [a-zA-Z] requirement fails, so the
    # input is returned unchanged (that clean form already grounds fine).
    assert _strip_im_contraction("I'm Bob") == "I'm Bob"


def test_strip_im_contraction_non_match_unchanged():
    assert _strip_im_contraction("Bob") == "Bob"


def test_strip_im_contraction_empty_returns_empty():
    assert _strip_im_contraction("") == ""


def test_strip_im_contraction_none_returns_empty():
    assert _strip_im_contraction(None) == ""


# ─────────────────────────────────────────────────────────────────────────────
# _user_text_gate_passes
# ─────────────────────────────────────────────────────────────────────────────

def test_gate_empty_user_text_rejected_by_default():
    assert _user_text_gate_passes("", "bob", (r"x",)) is False


def test_gate_empty_user_text_allowed_when_reject_disabled():
    assert _user_text_gate_passes(
        "   ", "bob", (r"x",), reject_on_empty_user_text=False
    ) is True


def test_gate_denial_signal_mode_match_alone_passes():
    # new_value=None -> denial-signal gate; any pattern match suffices (line 101).
    assert _user_text_gate_passes("wrong person here", None, (r"wrong person",)) is True


def test_gate_denial_signal_mode_no_match_fails():
    assert _user_text_gate_passes("all good", None, (r"wrong person",)) is False


def test_gate_name_verify_exact_match_passes():
    assert _user_text_gate_passes("call me bob", "bob", (r"call me (\w+)",)) is True


def test_gate_name_verify_multiword_contiguous_passes():
    # captured "sarah" != "sarah jane" but proposal startswith it AND appears
    # contiguously in user_text (lines 115-117).
    assert _user_text_gate_passes(
        "call me sarah jane", "sarah jane", (r"call me (\w+)",)
    ) is True


def test_gate_name_verify_noncontiguous_rejected():
    # proposal words scattered across the utterance -> contiguous check fails.
    assert _user_text_gate_passes(
        "call me sarah and my name is jane", "sarah jane", (r"call me (\w+)",)
    ) is False


def test_gate_name_verify_wrong_name_rejected():
    # captured "alice" != "bob" and "bob" does not start with "alice" (line 118).
    assert _user_text_gate_passes("call me alice", "bob", (r"call me (\w+)",)) is False


def test_gate_pattern_without_capture_group_continues_then_fails():
    # LINE 103: a pattern matches, new_value is a real str (not the denial gate),
    # but the pattern has NO capture group -> `not m.groups()` -> continue.
    # No further pattern -> loop exits -> return False.
    assert _user_text_gate_passes("please rename me now", "bob", (r"rename",)) is False


def test_gate_no_group_pattern_then_grouped_pattern_still_evaluated():
    # The no-group pattern hits line 103 `continue`; a subsequent grouped
    # pattern that DOES verify then passes — proves `continue` advances the loop
    # rather than short-circuiting the whole gate.
    assert _user_text_gate_passes(
        "please rename, call me bob",
        "bob",
        (r"rename", r"call me (\w+)"),
    ) is True


# ─────────────────────────────────────────────────────────────────────────────
# _intent_allows
# ─────────────────────────────────────────────────────────────────────────────

def test_intent_allows_tool_not_gated_passes():
    ok, reason = _intent_allows("search_web", "whatever", 0.9, None, "hi", {})
    assert ok is True
    assert reason == "tool not gated"


def test_intent_allows_intent_mismatch_rejected():
    ok, reason = _intent_allows(
        "update_person_name", "assign_system_name", 0.95, "bob",
        "call me bob", {"name": "bob"},
    )
    assert ok is False
    assert "intent=assign_system_name" in reason
    assert "expected=assign_own_name" in reason


def test_intent_allows_confidence_below_general_floor_rejected():
    ok, reason = _intent_allows(
        "update_person_name", "assign_own_name", 0.50, "bob",
        "call me bob", {"name": "bob"},
    )
    assert ok is False
    assert "confidence 0.50" in reason


def test_intent_allows_shutdown_uses_higher_floor():
    # 0.78 clears the general floor (0.75) but NOT the shutdown floor (0.80).
    ok, reason = _intent_allows(
        "shutdown", "request_shutdown", 0.78, None, "shut down now", {},
    )
    assert ok is False
    assert "0.78" in reason


def test_intent_allows_shutdown_passes_above_floor():
    ok, reason = _intent_allows(
        "shutdown", "request_shutdown", 0.82, None, "shut down now", {},
    )
    assert ok is True
    assert reason == "intent match"


def test_intent_allows_grounded_rename_passes():
    ok, reason = _intent_allows(
        "update_person_name", "assign_own_name", 0.95, "Bob",
        "please call me Bob", {"name": "Bob"},
    )
    assert ok is True
    assert reason == "intent match"


def test_intent_allows_extracted_value_not_grounded_rejected():
    ok, reason = _intent_allows(
        "update_person_name", "assign_own_name", 0.95, "Kara",
        "hello there", {"name": "Kara"},
    )
    assert ok is False
    assert "not grounded" in reason


def test_intent_allows_arg_cross_check_mismatch_rejected():
    # extracted "Bob" grounded, but the LLM's tool arg says "Alice".
    ok, reason = _intent_allows(
        "update_person_name", "assign_own_name", 0.95, "Bob",
        "call me Bob", {"name": "Alice"},
    )
    assert ok is False
    assert "!= user said" in reason


def test_intent_allows_im_contraction_stripped_before_grounding():
    # Session 94 Fix #2: classifier value "Imlexi" grounds against clean STT
    # "I'm Lexi" once both are stripped to "lexi".
    ok, reason = _intent_allows(
        "update_person_name", "assign_own_name", 0.95, "Imlexi",
        "I'm Lexi", {"name": "Imlexi"},
    )
    assert ok is True
    assert reason == "intent match"


def test_intent_allows_elif_hallucinated_arg_grounded_passes():
    # classifier abstained (extracted_value=None) but the LLM proposed a
    # grounded arg -> elif branch (lines 235-255) accepts it.
    ok, reason = _intent_allows(
        "update_person_name", "assign_own_name", 0.80, None,
        "call me Bob", {"name": "Bob"},
    )
    assert ok is True
    assert reason == "intent match"


def test_intent_allows_elif_hallucinated_arg_ungrounded_rejected():
    # classifier abstained AND the proposed arg is NOT in user_text -> the
    # Session 87 silent-hallucination guard rejects it.
    ok, reason = _intent_allows(
        "update_person_name", "assign_own_name", 0.80, None,
        "hello there", {"name": "Kara"},
    )
    assert ok is False
    assert "not grounded (classifier extracted no value)" in reason


def test_intent_allows_report_mismatch_with_identity_denial_passes():
    # "I'm not Jagan" matches IDENTITY_DENIAL_PATTERNS pattern 1 -> structural
    # gate satisfied -> intent match.
    ok, reason = _intent_allows(
        "report_identity_mismatch", "deny_identity", 0.95, None,
        "I'm not Jagan", {},
    )
    assert ok is True
    assert reason == "intent match"


def test_intent_allows_report_mismatch_topic_denial_rejected():
    # P0.S10 D3 canary: topic-denial "I don't have any job" is NOT an identity
    # denial -> no pattern matches -> structural gate rejects.
    ok, reason = _intent_allows(
        "report_identity_mismatch", "deny_identity", 0.95, None,
        "I don't have any job", {},
    )
    assert ok is False
    assert "identity-rejection" in reason
    assert "P0.S10 D3" in reason


# ─────────────────────────────────────────────────────────────────────────────
# _detect_yes_no
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text", ["yes please", "Yeah", "of course", "i am", "that's me"])
def test_detect_yes_no_yes_variants(text):
    assert _detect_yes_no(text) == "yes"


@pytest.mark.parametrize("text", ["no", "Nope", "nah", "never", "i'm not"])
def test_detect_yes_no_no_variants(text):
    # LINES 286-287: the "no" family match + return "no".
    assert _detect_yes_no(text) == "no"


@pytest.mark.parametrize("text", ["maybe", "", "hmm", "i guess"])
def test_detect_yes_no_unclear(text):
    # LINE 288: neither yes nor no family matches -> "unclear".
    assert _detect_yes_no(text) == "unclear"
