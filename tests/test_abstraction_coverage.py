# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors
"""100% coverage for core.abstraction — production-time PII abstraction for the graph classifier (coverage-to-100 campaign)."""

import pytest

import core.abstraction as ab
from core.abstraction import abstract_text, deabstract, _load_spacy


@pytest.fixture(autouse=True)
def _preserve_module_state():
    # _NLP / _NLP_LOAD_FAILED are module-level singletons; save + restore so a
    # test that forces a load failure can't poison a later real-spacy test.
    saved_nlp = ab._NLP
    saved_failed = ab._NLP_LOAD_FAILED
    yield
    ab._NLP = saved_nlp
    ab._NLP_LOAD_FAILED = saved_failed


# ── Deterministic fake-spacy scaffolding for the NER branch ─────────────────
class _FakeEnt:
    def __init__(self, text, label, start, end):
        self.text = text
        self.label_ = label
        self.start_char = start
        self.end_char = end


class _FakeDoc:
    def __init__(self, ents):
        self.ents = ents


class _FakeNlp:
    def __init__(self, ents):
        self._ents = ents

    def __call__(self, text):
        return _FakeDoc(self._ents)


class _RaisingNlp:
    def __call__(self, text):
        raise RuntimeError("boom")


# ── _load_spacy ─────────────────────────────────────────────────────────────
def test_load_spacy_short_circuits_after_prior_failure():
    # line 49: prior failure recorded -> return None without retrying import
    ab._NLP = None
    ab._NLP_LOAD_FAILED = True
    assert _load_spacy() is None


def test_load_spacy_handles_load_error_and_sets_flag(monkeypatch, capsys):
    # lines 54-58: spacy.load raises OSError -> logged, flag set, None returned
    import spacy

    ab._NLP = None
    ab._NLP_LOAD_FAILED = False

    def _raise(*a, **k):
        raise OSError("model not downloaded")

    monkeypatch.setattr(spacy, "load", _raise)
    assert _load_spacy() is None
    assert ab._NLP_LOAD_FAILED is True
    assert "spacy load failed" in capsys.readouterr().out
    # flag now persists: a second call short-circuits at line 49
    assert _load_spacy() is None


# ── abstract_text: early returns + registry pass ────────────────────────────
def test_abstract_empty_text_returns_empty_mapping():
    # lines 82-83: falsy text short-circuit
    assert abstract_text("") == ("", {})


def test_registry_skips_empty_and_whitespace_names(monkeypatch):
    # line 98: blank/whitespace names skipped; real name still mapped.
    # _load_spacy -> None also exercises the nlp-is-None return (line 119).
    monkeypatch.setattr(ab, "_load_spacy", lambda: None)
    out, mapping = abstract_text("hello there", persons_in_room=["", "   ", "Lexi"])
    assert mapping == {"{P1}": "Lexi"}
    assert out == "hello there"


def test_registry_deduplicates_case_insensitive_names(monkeypatch):
    # line 100: second (case-variant) occurrence of a known name is skipped
    monkeypatch.setattr(ab, "_load_spacy", lambda: None)
    out, mapping = abstract_text("Lexi met LEXI", persons_in_room=["Lexi", "LEXI"])
    assert mapping == {"{P1}": "Lexi"}
    assert out == "{P1} met {P1}"


def test_nlp_none_returns_registry_result(monkeypatch):
    # line 119: nlp is None -> return the registry-only result (system_name too)
    monkeypatch.setattr(ab, "_load_spacy", lambda: None)
    out, mapping = abstract_text("call me Kara", system_name="Kara")
    assert out == "call me {SYSTEM}"
    assert mapping == {"{SYSTEM}": "Kara"}


def test_no_alpha_after_registry_skips_ner(monkeypatch):
    # lines 123-124: nlp loaded but no [A-Za-z] remain -> early return, never
    # invokes nlp (the truthy sentinel is intentionally not callable).
    monkeypatch.setattr(ab, "_load_spacy", lambda: object())
    out, mapping = abstract_text("123 456 789")
    assert out == "123 456 789"
    assert mapping == {}


def test_spacy_parse_failure_returns_registry_result(monkeypatch, capsys):
    # lines 128-130: nlp(out) raises -> logged, registry-only result returned
    monkeypatch.setattr(ab, "_load_spacy", lambda: _RaisingNlp())
    out, mapping = abstract_text("hello world")
    assert out == "hello world"
    assert mapping == {}
    assert "spacy parse failed" in capsys.readouterr().out


# ── NER branch (PERSON + PLACE) ─────────────────────────────────────────────
def test_ner_person_new_and_placeholder_skips(monkeypatch):
    # lines 137-141 (person + placeholder skip), 149-153 (new person),
    # 154-157 (place branch placeholder skip).
    ents = [
        _FakeEnt("{P1}", "PERSON", 0, 4),    # already a placeholder -> skip (140-141)
        _FakeEnt("Bob", "PERSON", 0, 3),     # brand-new person       -> 149-153
        _FakeEnt("{LOC1}", "GPE", 0, 6),     # already a placeholder -> skip (157)
    ]
    monkeypatch.setattr(ab, "_load_spacy", lambda: _FakeNlp(ents))
    out, mapping = abstract_text("Bob went to town")
    assert mapping == {"{P1}": "Bob"}
    assert out == "{P1} went to town"


def test_ner_person_reuses_existing_placeholder(monkeypatch):
    # lines 144-148 with a match -> reuse placeholder, skip 149-152, hit 153.
    # Registry maps Bob->{P1}; the NER pass re-detects "Bob" and reuses {P1}.
    monkeypatch.setattr(ab, "_load_spacy", lambda: _FakeNlp([_FakeEnt("Bob", "PERSON", 0, 4)]))
    out, mapping = abstract_text("Bob", persons_in_room=["Bob"])
    assert mapping == {"{P1}": "Bob"}
    assert out == "{P1}"


def test_real_spacy_end_to_end_abstracts_person():
    # Integration anchor: exercise 137-153 through the real en_core_web_sm model,
    # proving the fake-nlp assumptions about doc.ents match reality.
    out, mapping = abstract_text("I talked to Sarah")
    assert "Sarah" not in out
    assert "Sarah" in mapping.values()
    assert "{P1}" in out


# ── deabstract ──────────────────────────────────────────────────────────────
def test_deabstract_empty_text_returns_input():
    # line 185-186: first operand of the `or` is true
    assert deabstract("", {"{P1}": "Lexi"}) == ""


def test_deabstract_empty_mapping_returns_input():
    # line 185-186: second operand of the `or` is true
    assert deabstract("hi {P1}", {}) == "hi {P1}"


def test_deabstract_substitutes_longest_placeholder_first():
    # lines 187-191: longest placeholder replaced first so {LOC10} isn't
    # clobbered by {LOC1} (would yield "Paris0" under naive ordering).
    out = deabstract("{LOC1} and {LOC10}", {"{LOC1}": "Paris", "{LOC10}": "Tokyo"})
    assert out == "Paris and Tokyo"
