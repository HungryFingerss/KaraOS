"""
Structural guard for pre-existing infrastructure-debt test failures.

Purpose: prevent new infra failures from silently joining the "known failures"
bucket without an explicit decision.  Any addition to INFRA_DEBT_FAILURES
must also update INFRA_DEBT_CAP — making the trade-off visible in the diff.

Remediation notes per entry tell the reviewer exactly what unblocks deletion.

To delete an entry after fixing:
  1. Remove the tuple from INFRA_DEBT_FAILURES.
  2. Decrement INFRA_DEBT_CAP.
  3. Confirm the test is now green in the full suite.
"""

INFRA_DEBT_FAILURES = frozenset({
    (
        "test_pipeline.py::test_torchaudio_list_audio_backends_patch_applied_at_import",
        "torchaudio DLL missing on Windows dev machine; patch applied at "
        "core.voice import time but test imports in isolation. "
        "Remediation: include torchaudio wheel in dev venv or mark xfail.",
    ),
    (
        "test_pipeline.py::test_speechbrain_logger_suppressed_at_import",
        "SpeechBrain logger suppression test requires the real SpeechBrain "
        "import chain, which triggers the torchaudio DLL crash on Windows dev. "
        "Remediation: fix torchaudio wheel (unblocks this + torchaudio test).",
    ),
    (
        "test_pipeline.py::test_diarize_drops_segments_below_min_segment_secs",
        "pyannote.audio pipeline load fails: patched io.py not applied in "
        "this test's import context. Remediation: P0.R5 pyannote vendor patch.",
    ),
    (
        "test_pipeline.py::test_diarize_short_segment_drops_attribution_keeps_label",
        "Same pyannote load failure as test_diarize_drops_segments_below_min_segment_secs.",
    ),
    (
        "test_pipeline.py::test_diarize_three_speaker_returns_distinct_labels",
        "Same pyannote load failure as test_diarize_drops_segments_below_min_segment_secs.",
    ),
    (
        "test_pipeline.py::test_diarize_empty_gallery_segments_still_have_speaker_label",
        "Same pyannote load failure as test_diarize_drops_segments_below_min_segment_secs.",
    ),
    (
        "test_pipeline.py::test_diarize_speaker_id_attribution_via_ecapa_gallery",
        "Same pyannote load failure as test_diarize_drops_segments_below_min_segment_secs.",
    ),
    (
        "test_pipeline.py::test_diarize_pyannote_error_falls_back_to_ecapa_and_bumps_counter",
        "Same pyannote load failure as test_diarize_drops_segments_below_min_segment_secs.",
    ),
})

# Cap: update this when an entry is deleted (fixed) or added (new debt accepted).
# If you bump the cap UP without a corresponding P0/remediation plan, that is
# an explicit acknowledgment that new infra debt is being accepted.
INFRA_DEBT_CAP = 8


def test_infra_debt_cap_matches_allowlist():
    """Allowlist and cap must be in sync — catches both silent growth and
    forgotten cleanup after a fix."""
    assert len(INFRA_DEBT_FAILURES) == INFRA_DEBT_CAP, (
        f"INFRA_DEBT_FAILURES has {len(INFRA_DEBT_FAILURES)} entries "
        f"but INFRA_DEBT_CAP is {INFRA_DEBT_CAP}. "
        "If you fixed a test: remove its entry and decrement the cap. "
        "If you're adding new debt: add the entry and increment the cap "
        "with a remediation note."
    )


def test_infra_debt_no_duplicate_test_names():
    """Each test name must appear at most once — frozenset of tuples allows
    (name, different_rationale) duplicates without catching them at construction."""
    names = [entry[0] for entry in INFRA_DEBT_FAILURES]
    assert len(names) == len(set(names)), (
        "Duplicate test name in INFRA_DEBT_FAILURES: "
        + str([n for n in names if names.count(n) > 1])
    )


def test_infra_debt_entries_have_rationale():
    """Every entry must be a 2-tuple with a non-empty rationale string."""
    for entry in INFRA_DEBT_FAILURES:
        assert isinstance(entry, tuple) and len(entry) == 2, (
            f"Entry must be a 2-tuple (test_id, rationale): {entry!r}"
        )
        test_id, rationale = entry
        assert test_id.startswith("test_pipeline.py::"), (
            f"test_id must be fully qualified 'file::name': {test_id!r}"
        )
        assert isinstance(rationale, str) and len(rationale) > 20, (
            f"Rationale too short (must explain WHY and HOW to fix): {rationale!r}"
        )
