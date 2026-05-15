"""Regression tests for Wave 4 follow-up F2 — voice bootstrap replenishment fix.

Root cause (F2 bug):
  known/best_friend sessions are opened without a 'waiting_for_name' key in the
  session dict (that key is only set on stranger sessions). The old replenishment
  condition used ``session.get("waiting_for_name", True)`` — when the key is absent
  the default True made ``not True = False``, causing the outer gate to always skip
  replenishment for every non-stranger voice-only session. Lexi-class persons (promoted
  stranger → known, voice_only_origin=True, gallery stuck at voice_n=4) could never
  grow their gallery past the initial 4 samples because replenishment never ran.

Fix (1-char change in pipeline._accumulate_voice):
  session.get("waiting_for_name", True) → session.get("waiting_for_name", False)

Source-inspection tests (not behavioural) — reads pipeline.py as raw text to avoid
the torchaudio DLL import issue on the Windows dev machine (same DLL crash that
affects test_pipeline_latency.py and any test that does ``import pipeline``).

Three regression tests:
  1. test_f2_waiting_for_name_default_is_false
     The replenishment condition must use default=False, not default=True.

  2. test_f2_replenishment_gated_on_voice_only_origin
     The gate must use the voice_only_origin flag (S120 widened from
     person_type=='stranger' so promoted persons keep getting replenishment).

  3. test_f2_replenishment_not_gated_on_person_type_stranger
     The replenishment block must NOT gate on person_type=='stranger' — that
     was the S94 design that broke on promotion. S120 replaced it with the flag.
"""
import pathlib
import re

# ---------------------------------------------------------------------------
# Read pipeline.py once at module load — no import, no DLL issue.
# ---------------------------------------------------------------------------

_PIPELINE_PATH = pathlib.Path(__file__).parent.parent / "pipeline.py"
_PIPELINE_SRC = _PIPELINE_PATH.read_text(encoding="utf-8")


def _extract_accumulate_voice_src() -> str:
    """Return the full source text of _accumulate_voice from pipeline.py."""
    match = re.search(
        r"(async def _accumulate_voice\b.*?)(?=\nasync def |\ndef |\nclass |\Z)",
        _PIPELINE_SRC,
        re.DOTALL,
    )
    assert match is not None, (
        "_accumulate_voice not found in pipeline.py — function was renamed or removed?"
    )
    return match.group(1)


# ---------------------------------------------------------------------------
# Test 1: waiting_for_name default must be False
# ---------------------------------------------------------------------------

def test_f2_waiting_for_name_default_is_false():
    """The replenishment condition must NOT use True as the None-fallback for waiting_for_name.

    F2 root cause: the old dict pattern session.get("waiting_for_name", True) meant
    known/best_friend sessions (no key) always defaulted to True → not True = False →
    replenishment never fired. After P0.7.5.C migration the code uses snapshot attribute
    access: not (_acc_snap.waiting_for_name if _acc_snap is not None else False).
    The 'else False' preserves the F2 fix.
    """
    src = _extract_accumulate_voice_src()
    # After P0.7.5.C migration: dict .get() replaced with snapshot attribute access.
    assert 'waiting_for_name' in src, (
        "F2: waiting_for_name must be present in _accumulate_voice replenishment gate"
    )
    # Anti-regression: the None-fallback for waiting_for_name must be False, not True.
    # Locate the waiting_for_name reference and check nearby context for 'else True'.
    wfn_idx = src.find('waiting_for_name')
    wfn_window = src[wfn_idx:wfn_idx + 100] if wfn_idx != -1 else ''
    assert 'else True' not in wfn_window, (
        "F2 regression: waiting_for_name fallback must be 'else False', not 'else True' — "
        "'else True' causes the replenishment gate to always skip for known/best_friend sessions"
    )


# ---------------------------------------------------------------------------
# Test 2: replenishment must be gated on voice_only_origin
# ---------------------------------------------------------------------------

def test_f2_replenishment_gated_on_voice_only_origin():
    """Replenishment gate must use the voice_only_origin session flag.

    S120 widened the gate from person_type=='stranger' to voice_only_origin so
    that promoted strangers (person_type='known', voice_only_origin=True) still
    receive replenishment after promotion. Without this flag the gallery of
    Lexi-class persons would freeze at the voice_n they had at promotion time.
    """
    src = _extract_accumulate_voice_src()
    assert "voice_only_origin" in src, (
        "F2/S120 regression: _accumulate_voice replenishment gate must check "
        "voice_only_origin. Promoted strangers have person_type='known' but still "
        "need replenishment — only the flag survives the promotion rename."
    )


# ---------------------------------------------------------------------------
# Test 3: replenishment must NOT gate on person_type == 'stranger'
# ---------------------------------------------------------------------------

def test_f2_replenishment_not_gated_on_person_type_stranger():
    """Replenishment block must not gate on person_type == 'stranger'.

    S120 removed the old person_type=='stranger' check because update_person_name
    flips person_type to 'known' the moment a stranger introduces themselves —
    the old gate then permanently blocked replenishment for every promoted person.
    If this guard is re-introduced, Lexi-class persons will be frozen at voice_n=4
    after promotion.
    """
    src = _extract_accumulate_voice_src()

    # Isolate just the replenishment block (between VOICE_BOOTSTRAP_REPLENISH_ENABLED
    # and the _voice_accum_allowed call that follows it).
    block_match = re.search(
        r"VOICE_BOOTSTRAP_REPLENISH_ENABLED.*?(?=\n\s+allowed,\s+reason,\s+path)",
        src,
        re.DOTALL,
    )
    assert block_match is not None, (
        "Could not locate the replenishment block in _accumulate_voice — "
        "the code structure may have changed."
    )
    block = block_match.group(0)

    assert 'person_type == "stranger"' not in block, (
        'S120/F2 regression: replenishment block must not gate on '
        'person_type == "stranger". Use voice_only_origin flag instead.'
    )
    assert "person_type == 'stranger'" not in block, (
        "S120/F2 regression: replenishment block must not gate on "
        "person_type == 'stranger'. Use voice_only_origin flag instead."
    )
