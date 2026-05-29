"""tests/test_p0_s7_5_2.py — P0.S7.5.2 canary-3 multi-subsystem fixes.

5 D-decisions ship together as one bundle. Phase 1 covers D1 + D2 + D5
(8 tests); Phase 2 covers D3 + D4 (6 tests). See `tests/p0_s7_5_2_plan_v2.md`
for the locked code contract.

D1 (P0 CORRECTNESS) — `_rs_pif_view` producer at `pipeline.py:7234` must
    include `last_recognized_at` field sourced from PresenceSnapshot. The
    reconciler's offscreen-floor predicate reads this key; without it the
    .get(..., 0) default fires erroneous offscreen-floor decisions on
    legitimately-recognized speakers (canary 3 Jagan failure mode).

D2 (P0 CORRECTNESS) — voice-routing new_stranger at `pipeline.py:7496+`
    mirrors the ambient-gate engagement semantics when STT contains the
    active system name (NFKC-lowercased substring match). Without this,
    sessions opened via voice-routing stay gate-blocked at
    `waiting_for_name=True` with `bootstrap_credits=0` forever
    (canary 3 Lexi failure mode).

D5 (MEDIUM) — STRANGER_IDENTITY_BLOCK_MIN_TURNS = 0 + restructure block
    as NUMBERED CONTRAST (Rule 1 statements → call update_person_name;
    Rule 2 questions → DO NOT call report_identity_mismatch). Without
    the contrast, the brain misroutes canary-3-shape questions to
    report_identity_mismatch on turn 0/1.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import ast
import asyncio
import inspect
import time
from unittest.mock import MagicMock, patch

import pytest


# ───────────────────────────────────────────────────────────────────────
# D1 — `_rs_pif_view` producer key fix
# ───────────────────────────────────────────────────────────────────────


def test_rs_pif_view_includes_last_recognized_at():
    """D1 AST forward-property — `_rs_pif_view` producer at pipeline.py:7234
    builds a per-pid dict containing the `last_recognized_at` field
    sourced from `PresenceSnapshot.last_recognized_at`.

    Locates the producer dict-comprehension AST node, walks its keys,
    asserts `last_recognized_at` literal key is present. Without this,
    the reconciler at `core/reconciler.py:120/130` reads the .get default
    (0) and the offscreen-floor predicate fires on any face that was
    legitimately recognized within FACE_STALE_SECS (canary 3 Jagan).
    """
    import pipeline as _pl

    src = inspect.getsource(_pl)
    tree = ast.parse(src)

    # Find the `_rs_pif_view = { ... }` assignment whose value is a DictComp
    found = False
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and any(
                isinstance(t, ast.Name) and t.id == "_rs_pif_view" for t in node.targets
            )
            and isinstance(node.value, ast.DictComp)
        ):
            # Walk the value expression — should be a Dict literal with
            # `"last_recognized_at"` as a string key.
            value = node.value.value
            assert isinstance(value, ast.Dict), (
                "_rs_pif_view's DictComp must produce dict literals; got "
                f"{type(value).__name__}"
            )
            keys = [
                k.value
                for k in value.keys
                if isinstance(k, ast.Constant) and isinstance(k.value, str)
            ]
            assert "last_recognized_at" in keys, (
                "_rs_pif_view producer MUST include 'last_recognized_at' "
                "field. Without this, reconciler.py:120/130 falls back to "
                ".get(..., 0) and the offscreen-floor predicate fires on "
                "legitimately-recognized speakers. Canary 3 Jagan failure "
                "mode. Actual keys: " + repr(keys)
            )
            # Find the value paired with the last_recognized_at key — must be
            # an Attribute access on the snapshot variable `s.last_recognized_at`.
            for k, v in zip(value.keys, value.values):
                if isinstance(k, ast.Constant) and k.value == "last_recognized_at":
                    assert isinstance(v, ast.Attribute), (
                        "last_recognized_at value MUST be an attribute "
                        "access on the snapshot variable (e.g. s.last_recognized_at), "
                        f"got {type(v).__name__}"
                    )
                    assert v.attr == "last_recognized_at", (
                        f"value attribute name MUST be 'last_recognized_at', "
                        f"got {v.attr!r}"
                    )
                    break
            found = True
            break

    assert found, (
        "_rs_pif_view assignment with DictComp value not found in pipeline.py — "
        "edit site may have moved; update this test's locator"
    )


def test_presence_snapshot_schema_has_last_recognized_at():
    """D1 schema invariant — PresenceSnapshot dataclass MUST carry
    `last_recognized_at` as a distinct field. Catches future schema
    refactor that drops the field; D1's producer fix depends on it.
    """
    from core.presence_store import PresenceSnapshot
    from dataclasses import fields

    field_names = {f.name for f in fields(PresenceSnapshot)}
    assert "last_recognized_at" in field_names, (
        "PresenceSnapshot.last_recognized_at field MUST exist — D1 reads "
        f"it via peek_all_snapshots. Actual fields: {sorted(field_names)}"
    )
    assert "last_seen" in field_names, (
        "PresenceSnapshot.last_seen MUST coexist as distinct field "
        "(semantic: any-source touch vs face-recognized time)"
    )


def test_rs_pif_view_roundtrips_last_recognized_at_from_presence_store():
    """D1 behavioral — seed a PresenceStore via the real API, build a view
    matching the producer shape, assert the dict carries `last_recognized_at`
    from the snapshot. Regression guard: if `peek_all_snapshots` returns
    snapshots WITHOUT the field due to migration, the producer comprehension
    raises AttributeError — this test catches that early.
    """
    from core.presence_store import PresenceStore

    store = PresenceStore()
    now = time.time()

    async def _seed():
        await store.upsert_face_recognition(
            person_id="jagan_001",
            name="Jagan",
            conf=0.85,
            now=now,
        )

    asyncio.run(_seed())

    # Mirror the producer comprehension at pipeline.py:7234.
    view = {
        s.person_id: {
            "last_seen": s.last_seen,
            "last_recognized_at": s.last_recognized_at,
            "name": s.name,
            "conf": s.conf,
            "source": s.source,
        }
        for s in store.peek_all_snapshots()
    }

    assert "jagan_001" in view
    entry = view["jagan_001"]
    assert entry["last_recognized_at"] == pytest.approx(now), (
        "Face-recognition path MUST set last_recognized_at=now; D1 producer "
        "must surface that value verbatim to the reconciler"
    )
    assert entry["source"] == "face"


# ───────────────────────────────────────────────────────────────────────
# D2 — Voice-routing engagement-gate parity
# ───────────────────────────────────────────────────────────────────────


def test_voice_routing_new_stranger_block_has_engagement_gate_logic():
    """D2 AST forward-property — voice-routing new_stranger branch at
    pipeline.py:7496+ MUST contain the engagement-gate detection logic:
      (1) `peek_active_system_name` call
      (2) `_nfkc_lower(...) in _nfkc_lower(text)` substring check
      (3) `engagement_gate_passed=` keyword on `_open_session` (NOT
          hardcoded False)

    Without this AST shape, the canary 3 Lexi failure recurs.
    """
    import pipeline as _pl

    src = inspect.getsource(_pl)

    # Locate the `[Voice] Unrecognized speaker → new session` log line
    # as a stable landmark for the D2 branch.
    landmark = '[Voice] Unrecognized speaker'
    idx = src.find(landmark)
    assert idx > 0, "D2 landmark log line not found; edit site may have moved"

    # Look backwards from the landmark to find the enclosing branch body.
    # Anchor on the preceding `_open_session(_sid, ...` call — D2 wraps this.
    snippet = src[max(0, idx - 4000) : idx + 200]

    assert "peek_active_system_name" in snippet, (
        "D2 voice-routing branch MUST call peek_active_system_name to read "
        "current system name. Without this the engagement-gate detection "
        "cannot fire."
    )
    assert "_nfkc_lower" in snippet, (
        "D2 MUST use _nfkc_lower for substring match (matches ambient-gate "
        "pattern + provides Cyrillic homoglyph defense per P0.3)"
    )
    assert "engagement_gate_passed=_engagement_passed" in snippet, (
        "D2 MUST pass _engagement_passed conditionally to _open_session "
        "(NOT hardcoded False). Plan v2 §4.2 locked shape."
    )


def test_voice_routing_branch_logs_when_engagement_passes():
    """D2 AST — branch must conditionally emit the
    `[Pipeline] Stranger engaged (voice-only, system addressed)` log
    when engagement passes. Matches the ambient-gate log so canary diff
    can compare event-pattern frequency before/after.
    """
    import pipeline as _pl

    src = inspect.getsource(_pl)
    # The D2 branch should contain BOTH the engaged log AND the legacy log.
    assert "Stranger engaged (voice-only, system addressed)" in src, (
        "D2 branch MUST emit '[Pipeline] Stranger engaged (voice-only, "
        "system addressed)' log when engagement passes; mirrors ambient-gate "
        "log at pipeline.py:6857"
    )


def test_d2_uses_nfkc_lower_substring_match_not_word_boundary():
    """D2 contract — Plan v2 Precision 1 locked NFKC-lowercased substring
    match (NOT word-boundary regex). Matches existing engagement-gate
    detection pattern at the ambient path. If future refactor switches
    to word-boundary, fix BOTH paths symmetrically per §13.2 of Plan v1.
    """
    import pipeline as _pl

    src = inspect.getsource(_pl)
    landmark = "[Voice] Unrecognized speaker"
    idx = src.find(landmark)
    snippet = src[max(0, idx - 4000) : idx + 200]

    # The D2 block must NOT use a word-boundary regex.
    # Check the engagement-gate computation uses `in` substring operator.
    assert "_nfkc_lower(_system_name) in _nfkc_lower(text)" in snippet, (
        "D2 engagement-gate check MUST use NFKC-lowercased substring `in` "
        "operator (matches ambient-gate pattern at pipeline.py:6800 area). "
        "Word-boundary regex would create asymmetry between voice-routing "
        "and ambient-gate paths — both must change together if word-boundary "
        "tightening proves load-bearing later."
    )
    # Negative: ensure we didn't accidentally introduce \b word-boundary regex
    # specifically in this branch (other regex elsewhere is fine).
    assert "\\bre.search" not in snippet, "no word-boundary regex in D2 branch"


# ───────────────────────────────────────────────────────────────────────
# D5 — STRANGER IDENTITY block restructure + MIN_TURNS=0
# ───────────────────────────────────────────────────────────────────────


def test_stranger_identity_block_min_turns_is_zero():
    """D5 config — STRANGER_IDENTITY_BLOCK_MIN_TURNS dropped from 2 to 0.
    Block now fires on every stranger turn so canary-3-shape questions
    hit the Rule 2 anti-pattern immediately on turn 0/1.
    """
    from core.config import STRANGER_IDENTITY_BLOCK_MIN_TURNS

    assert STRANGER_IDENTITY_BLOCK_MIN_TURNS == 0, (
        f"STRANGER_IDENTITY_BLOCK_MIN_TURNS MUST be 0 (was 2 pre-P0.S7.5.2 D5); "
        f"got {STRANGER_IDENTITY_BLOCK_MIN_TURNS}. Canary 3 (2026-05-20) "
        "showed Lexi turn 1 mistooled to report_identity_mismatch because "
        "the block didn't fire until turn 2 under the old threshold."
    )


def test_stranger_identity_block_uses_numbered_contrast_shape():
    """D5 prompt-content — Plan v2 §5.2 restructure the block as two
    numbered rules with symmetric DO/DO-NOT structure:
      RULE 1 — STATEMENTS → CALL update_person_name
      RULE 2 — QUESTIONS → DO NOT call report_identity_mismatch

    Asserts:
      (a) Block label + RULE 1 + RULE 2 substrings present
      (b) Both tool-call directives present (update_person_name + DO NOT
          call report_identity_mismatch)
      (c) Concrete examples on BOTH sides (self-intro triggers + question
          shapes)
      (d) Forward reference from Rule 2 → Rule 1 (`THAT triggers RULE 1`)
      (e) Lexi canary-3 question shape named explicitly

    Source-inspection with adjacent-string-literal normalizer per
    feedback_adjacent_string_literal_normalizer.md (4th instance).
    """
    import re
    from core import brain

    raw_src = inspect.getsource(brain.render_session_stable_prefix)
    src = re.sub(r'"\s+"', "", raw_src)
    src = re.sub(r"'\s+'", "", src)

    # (a) numbered contrast structure
    assert "<<<STRANGER IDENTITY>>>" in src, "block label still present"
    assert "RULE 1" in src, (
        "Plan v2 §5.2 contrast — Rule 1 label required for LLM to "
        "internalize the bilateral framing"
    )
    assert "RULE 2" in src, (
        "Plan v2 §5.2 contrast — Rule 2 label required; without it the "
        "anti-pattern degenerates to a soft bullet the LLM can ignore"
    )

    # (b) symmetric tool-call directives
    assert "CALL `update_person_name`" in src, (
        "Rule 1 MUST name update_person_name as the CALL action"
    )
    assert (
        "DO NOT call `report_identity_mismatch`" in src
        or "DO NOT call\n            `report_identity_mismatch`" in src
    ), (
        "Rule 2 MUST name report_identity_mismatch as the DO-NOT-CALL "
        "anti-pattern (canary 3 Lexi mis-tooling target)"
    )

    # (c) concrete examples both sides
    assert "Call me Lexi" in src, "Rule 1 self-intro example preserved"
    assert "Do you know me?" in src, "Rule 2 question example required"
    assert "Have we met before?" in src, "Rule 2 second question example required"

    # (d) forward reference
    assert "THAT triggers RULE 1" in src, (
        "Rule 2 MUST forward-reference Rule 1 — explicit causal chain "
        "teaches LLM how the rules interact (Plan v2 §5.3 prompt-engineering "
        "rationale)"
    )

    # (e) Lexi canary-3 question shape (exact)
    assert "I know you very well but I'm not sure if you know me" in src, (
        "Canary-3 evidence phrasing MUST appear verbatim as a Rule 2 "
        "example — without it the regression guard fades when the LLM "
        "encounters variant phrasings"
    )


# ───────────────────────────────────────────────────────────────────────
# D3 — Voice gallery accumulation gates (Phase 2)
# ───────────────────────────────────────────────────────────────────────


def test_d3_voice_gallery_constants_present():
    """D3 config invariant — 3 new constants land in core/config.py at
    documented values per Plan v2 §3 + §5.3.
    """
    from core import config

    assert hasattr(config, "MIN_VOICE_ACCUM_DURATION_SECS"), (
        "MIN_VOICE_ACCUM_DURATION_SECS MUST be defined in config.py"
    )
    assert config.MIN_VOICE_ACCUM_DURATION_SECS == pytest.approx(1.5), (
        "duration floor MUST match ECAPA min reliable length (1.5s per "
        f"core/voice.py:147); got {config.MIN_VOICE_ACCUM_DURATION_SECS}"
    )

    assert hasattr(config, "VOICE_SELF_UPDATE_CENTROID_MIN"), (
        "VOICE_SELF_UPDATE_CENTROID_MIN MUST be defined in config.py"
    )
    assert config.VOICE_SELF_UPDATE_CENTROID_MIN == pytest.approx(0.55), (
        "centroid floor MUST mirror face gallery SELF_UPDATE_CENTROID_MIN "
        f"(Session 51); got {config.VOICE_SELF_UPDATE_CENTROID_MIN}"
    )

    assert hasattr(config, "VOICE_CENTROID_GATE_MIN_SAMPLES"), (
        "VOICE_CENTROID_GATE_MIN_SAMPLES MUST be defined in config.py"
    )
    assert config.VOICE_CENTROID_GATE_MIN_SAMPLES == 5, (
        "bootstrap-safe min samples MUST be 5 (gate inactive until ≥5 "
        f"samples); got {config.VOICE_CENTROID_GATE_MIN_SAMPLES}"
    )


def test_d3_add_voice_embedding_rejects_centroid_outlier_after_bootstrap(tmp_path):
    """D3 behavioral — once gallery has ≥5 samples, an outlier embedding
    (cosine to centroid below VOICE_SELF_UPDATE_CENTROID_MIN=0.55) MUST be
    rejected with the skip log. Reproduces canary 3's contamination
    vector at the gate level.

    Seeds are clustered around a shared axis but distinct enough to pass
    the diversity filter (`VOICE_DIVERSITY_THRESHOLD=0.85`); the on-axis
    "ok_sample" carries its own distinguishing feature so diversity
    accepts it AND centroid accepts it (cosine to centroid above 0.55).
    """
    import numpy as np
    from core import db as _db_mod

    _db_mod.DB_PATH = tmp_path / "faces.db"
    _db_mod.FAISS_INDEX_PATH = tmp_path / "faiss.index"
    db = _db_mod.FaceDB(tmp_path / "faces.db", faiss_path=tmp_path / "faiss.index")
    try:
        pid = "jagan_001"
        db.add_person(pid, "Jagan", "best_friend")

        # Seed 5 normalized embeddings sharing direction [idx 0] but each
        # with a distinct distinguishing feature → pairwise cosine ~0.74
        # (passes VOICE_DIVERSITY_THRESHOLD=0.85).
        def make_clustered(distinguishing_idx: int) -> np.ndarray:
            s = np.zeros(192, dtype=np.float32)
            s[0] = 1.0
            s[distinguishing_idx] = 0.6
            s /= np.linalg.norm(s)
            return s

        for i in range(5):
            db.add_voice_embedding(pid, make_clustered(10 + i),
                                   source="voice_self_match")

        # Outlier: orthogonal to the shared direction → cosine to centroid ~0.
        outlier = np.zeros(192, dtype=np.float32)
        outlier[100] = 1.0
        added = db.add_voice_embedding(pid, outlier, source="voice_self_match")
        assert added is False, (
            "centroid-distance gate MUST reject orthogonal outlier once "
            "gallery has ≥5 samples; canary 3 centroid contamination "
            "comes from accepting these"
        )

        # On-axis but distinct sample → passes diversity (new distinguishing
        # feature) + passes centroid (cosine to centroid ~0.83).
        ok_sample = make_clustered(50)
        added = db.add_voice_embedding(pid, ok_sample, source="voice_self_match")
        assert added is True, (
            "centroid-distance gate MUST accept on-axis sample with novel "
            "distinguishing feature; gate must not be over-restrictive "
            "against legitimate centroid-aligned embeddings"
        )
    finally:
        db._conn.close()


def test_d3_add_voice_embedding_bootstrap_safe_below_five_samples(tmp_path):
    """D3 behavioral — during bootstrap (<5 samples), centroid gate is
    INACTIVE; even an orthogonal embedding gets accepted. Mirrors face
    gallery's bootstrap-safe design.
    """
    import numpy as np
    from core import db as _db_mod

    _db_mod.DB_PATH = tmp_path / "faces.db"
    _db_mod.FAISS_INDEX_PATH = tmp_path / "faiss.index"
    db = _db_mod.FaceDB(tmp_path / "faces.db", faiss_path=tmp_path / "faiss.index")
    try:
        pid = "lexi_001"
        db.add_person(pid, "Lexi", "stranger")

        # Seed only 2 samples — well below VOICE_CENTROID_GATE_MIN_SAMPLES=5.
        base = np.zeros(192, dtype=np.float32)
        base[0] = 1.0
        for i in range(2):
            sample = base.copy()
            sample[1 + i] = 0.01
            sample /= np.linalg.norm(sample)
            db.add_voice_embedding(pid, sample, source="voice_self_match")

        # Orthogonal embedding — would be rejected after bootstrap.
        outlier = np.zeros(192, dtype=np.float32)
        outlier[100] = 1.0
        added = db.add_voice_embedding(pid, outlier, source="voice_self_match")
        assert added is True, (
            "centroid gate MUST be INACTIVE during bootstrap (count<5) — "
            "otherwise early enrollment is blocked. Plan v2 §3 + Session 51 "
            "face-gallery design pattern."
        )
    finally:
        db._conn.close()


def test_d3_pipeline_call_site_filters_short_utterance():
    """D3 AST — `_accumulate_voice` MUST contain the duration-filter guard
    that returns early when audio length < MIN_VOICE_ACCUM_DURATION_SECS.
    """
    import pipeline as _pl

    src = inspect.getsource(_pl._accumulate_voice)
    assert "MIN_VOICE_ACCUM_DURATION_SECS" in src, (
        "_accumulate_voice MUST reference MIN_VOICE_ACCUM_DURATION_SECS "
        "config to gate short utterances; Plan v2 §5.2 contract"
    )
    assert "len(audio)" in src and "MIC_SAMPLE_RATE" in src, (
        "duration computation MUST use len(audio) / MIC_SAMPLE_RATE; "
        "without this the gate cannot fire"
    )
    assert "short utterance" in src.lower(), (
        "skip log MUST surface 'short utterance' label for canary 4 "
        "diagnostic value per Plan v2 §6 verbose-by-design"
    )


# ───────────────────────────────────────────────────────────────────────
# D4 — STT 1-word artifact filter + Smart-Turn debounce (Phase 2)
# ───────────────────────────────────────────────────────────────────────


def test_d4_stt_constants_present():
    """D4 config invariant — MIN_STT_WORD_COUNT and STT_KNOWN_IMPERATIVES
    are defined in core/config.py at documented values per Plan v2 §4.
    """
    from core import config

    assert hasattr(config, "MIN_STT_WORD_COUNT")
    assert config.MIN_STT_WORD_COUNT == 2

    assert hasattr(config, "STT_KNOWN_IMPERATIVES")
    assert isinstance(config.STT_KNOWN_IMPERATIVES, frozenset)
    # 10 imperatives per Plan v2 §4.2
    expected = {"yes", "no", "stop", "help", "okay", "ok", "sure", "yeah", "yep", "nope"}
    assert config.STT_KNOWN_IMPERATIVES == expected, (
        f"STT_KNOWN_IMPERATIVES MUST be exactly the 10-word allowlist; "
        f"got {sorted(config.STT_KNOWN_IMPERATIVES)}"
    )


@pytest.mark.parametrize("word,expected_pass", [
    # All 10 imperatives — bare form, lowercased, no punctuation
    ("yes", True), ("no", True), ("stop", True), ("help", True),
    ("okay", True), ("ok", True), ("sure", True), ("yeah", True),
    ("yep", True), ("nope", True),
    # Case variants (case-insensitive match via .lower())
    ("Yes", True), ("YES", True), ("Stop", True),
    # Punctuation suffixes (terminated → pass regardless of allowlist)
    ("You.", True), ("You!", True), ("You?", True),
    # Whisper artifacts (NOT in allowlist, no punctuation) — REJECT
    ("You", False), ("Thank", False), ("Indeed", False), ("Absolutely", False),
    # "Yeah" IS in allowlist — gotcha! Distinguish from "You"
    ("Yeah", True),
    # Multi-word baseline (≥ MIN_STT_WORD_COUNT, filter doesn't apply)
    ("Yes I will", True), ("I don't know", True), ("Hi Kara", True),
])
def test_d4_stt_filter_logic(word, expected_pass):
    """D4 unit — mirror the filter logic exactly so per-word coverage is
    pinned. Plan v2 §4.1 parametrize-table verbatim.

    Filter passes WHEN: len(words) >= MIN_STT_WORD_COUNT
                     OR terminated with .!?
                     OR lowercased (stripped of punctuation) in allowlist.
    """
    from core.config import MIN_STT_WORD_COUNT, STT_KNOWN_IMPERATIVES

    text = word.strip()
    raw_words = text.split()
    if len(raw_words) >= MIN_STT_WORD_COUNT:
        passed = True
    else:
        terminated = text.endswith(('.', '!', '?'))
        word_lower = text.lower().rstrip('.!?,;:')
        allowed = word_lower in STT_KNOWN_IMPERATIVES
        passed = terminated or allowed

    assert passed is expected_pass, (
        f"D4 filter mismatch for {word!r}: expected pass={expected_pass}, "
        f"got pass={passed}"
    )


def _read_audio_module_source() -> str:
    """Helper to read core/audio.py source verbatim from disk.

    `inspect.getsource(core.audio)` fails on Windows under torch's
    package_importer monkeypatch ("built-in module") for any module that
    transitively imports torch. Read the file directly to bypass.
    """
    from pathlib import Path
    repo_root = Path(__file__).resolve().parent.parent
    return (repo_root / "core" / "audio.py").read_text(encoding="utf-8")


def test_d4_transcribe_filters_one_word_artifact_in_source():
    """D4 source-inspection on `core/audio.py` — the transcribe function
    body MUST contain the 1-word artifact filter that returns ("", "en")
    on un-allowlisted bare 1-word transcripts.
    """
    src = _read_audio_module_source()
    # Locate the filter block.
    assert "STT_KNOWN_IMPERATIVES" in src, (
        "core/audio.py MUST import STT_KNOWN_IMPERATIVES to gate 1-word "
        "filter; without it the filter cannot reference the allowlist"
    )
    assert "MIN_STT_WORD_COUNT" in src, (
        "core/audio.py MUST reference MIN_STT_WORD_COUNT to gate the filter"
    )
    assert "1-word artifact filtered" in src, (
        "filter MUST emit a '[Audio] STT: (1-word artifact filtered)' log "
        "line for canary 4 diagnostic value"
    )


def test_d4_smart_turn_debounce_uses_greater_or_equal_with_flag_guard():
    """D4 Smart-Turn debounce — AST/source-inspection assertion that the
    Smart-Turn invocation gate uses `silent_streak >= smart_turn_count`
    (NOT `==`) combined with `not smart_turn_fired` so a missed boundary
    chunk doesn't skip the whole streak while still firing at most once.
    """
    src = _read_audio_module_source()
    # The post-D4 logic uses >= and the flag guard together
    assert "silent_streak >= smart_turn_count" in src, (
        "Smart-Turn guard MUST use `silent_streak >= smart_turn_count` per "
        "Plan v2 §6.2 — broadens the firing condition so race-conditions "
        "around the boundary chunk don't drop Smart-Turn calls"
    )
    # Debounce flag still present
    assert "not smart_turn_fired" in src, (
        "Smart-Turn debounce flag `not smart_turn_fired` MUST gate the "
        "invocation — invariant 'fires at most once per silence streak' "
        "depends on it"
    )
    # And the reset path is still present on resumed speech
    assert "smart_turn_fired = False" in src, (
        "Smart-Turn reset path MUST clear `smart_turn_fired` when speech "
        "resumes (line ~418); without it the flag pins True and the next "
        "silence streak gets no Smart-Turn check"
    )
