"""Covers core.persona_loader validation raises: bad persona_id, YAML parse
error, non-mapping top level, non-string field, non-dict greeting_fallbacks
(SB.8 fail-loud loader). Part of the coverage-to-100 campaign."""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

import pytest

import core.persona_loader as pl
from core.persona_loader import load_persona, _validate, PersonaError
from persona._schema import REQUIRED_KEYS, TIME_OF_DAY_KEYS

def _valid_pack(pid="testpersona"):
    pack = {}
    for k in REQUIRED_KEYS:
        if k == "greeting_fallbacks":
            pack[k] = {tod: ["hi there"] for tod in TIME_OF_DAY_KEYS}
        elif k == "persona_id":
            pack[k] = pid
        else:
            pack[k] = "nonempty"
    return pack

def test_valid_pack_validates_clean():
    _validate(_valid_pack(), "testpersona", "x.yaml")  # no raise (positive control)

def test_load_persona_rejects_non_string_id():
    with pytest.raises(PersonaError, match="non-empty string"):
        load_persona("")

def test_validate_rejects_non_string_field():
    pack = _valid_pack()
    pack["voice_id"] = 123  # not a string -> line 91
    with pytest.raises(PersonaError, match="voice_id must be a non-empty string"):
        _validate(pack, "testpersona", "x.yaml")

def test_validate_rejects_non_dict_greeting_fallbacks():
    pack = _valid_pack()
    pack["greeting_fallbacks"] = "not a mapping"  # -> line 102
    with pytest.raises(PersonaError, match="greeting_fallbacks must be a mapping"):
        _validate(pack, "testpersona", "x.yaml")

def test_load_persona_rejects_invalid_yaml(tmp_path, monkeypatch):
    monkeypatch.setattr(pl, "_PERSONA_DIR", tmp_path)
    (tmp_path / "badyaml.yaml").write_text("foo: [1, 2, 3", encoding="utf-8")  # unclosed
    with pytest.raises(PersonaError, match="not valid YAML"):
        load_persona("badyaml")

def test_load_persona_rejects_non_mapping_top_level(tmp_path, monkeypatch):
    monkeypatch.setattr(pl, "_PERSONA_DIR", tmp_path)
    (tmp_path / "listtop.yaml").write_text("- a\n- b\n", encoding="utf-8")  # a list
    with pytest.raises(PersonaError, match="must be a YAML mapping"):
        load_persona("listtop")
