"""
Structural guard for pre-existing infrastructure-debt test failures.

Purpose: prevent new infra failures from silently joining the "known failures"
bucket without an explicit decision.  Any addition to INFRA_DEBT_FAILURES
must also update INFRA_DEBT_CAP — making the trade-off visible in the diff.

Remediation notes per entry tell the reviewer exactly what unblocks deletion.

**P0.0.2 disposition (2026-05-17):** every test in `INFRA_DEBT_FAILURES`
also carries `@pytest.mark.xfail(strict=False, reason=...)` so the slow
CI workflow shows the test as XFAIL instead of FAILED.  `strict=False`
means an unexpected PASS surfaces as XPASS (notable) without breaking
CI — the signal the infra debt was resolved.

The two artifacts are intentionally redundant:
  - The allowlist is the human-readable rationale registry (this file).
  - The xfail decorators control what pytest reports per test.
`test_xfail_decorators_align_with_allowlist` keeps them in sync.

To delete an entry after fixing:
  1. Remove the tuple from INFRA_DEBT_FAILURES.
  2. Decrement INFRA_DEBT_CAP.
  3. Remove the `@pytest.mark.xfail(...)` decorator from the test body.
  4. Confirm the test is now green in the full suite (passes, not xpasses).
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

INFRA_DEBT_FAILURES = frozenset({
    (
        "tests/test_pipeline_diarize_multispeaker.py::test_torchaudio_list_audio_backends_patch_applied_at_import",
        "torchaudio DLL missing on Windows dev machine; patch applied at "
        "core.voice import time but test imports in isolation. "
        "Remediation: include torchaudio wheel in dev venv or mark xfail.",
    ),
    (
        "tests/test_pipeline_diarize_multispeaker.py::test_speechbrain_logger_suppressed_at_import",
        "SpeechBrain logger suppression test requires the real SpeechBrain "
        "import chain, which triggers the torchaudio DLL crash on Windows dev. "
        "Remediation: fix torchaudio wheel (unblocks this + torchaudio test).",
    ),
    (
        "tests/test_pipeline_diarize_multispeaker.py::test_diarize_drops_segments_below_min_segment_secs",
        "pyannote.audio pipeline load fails: patched io.py not applied in "
        "this test's import context. Remediation: P0.R5 pyannote vendor patch.",
    ),
    (
        "tests/test_pipeline_diarize_multispeaker.py::test_diarize_short_segment_drops_attribution_keeps_label",
        "Same pyannote load failure as test_diarize_drops_segments_below_min_segment_secs.",
    ),
    (
        "tests/test_pipeline_diarize_multispeaker.py::test_diarize_three_speaker_returns_distinct_labels",
        "Same pyannote load failure as test_diarize_drops_segments_below_min_segment_secs.",
    ),
    (
        "tests/test_pipeline_diarize_multispeaker.py::test_diarize_empty_gallery_segments_still_have_speaker_label",
        "Same pyannote load failure as test_diarize_drops_segments_below_min_segment_secs.",
    ),
    (
        "tests/test_pipeline_diarize_multispeaker.py::test_diarize_speaker_id_attribution_via_ecapa_gallery",
        "Same pyannote load failure as test_diarize_drops_segments_below_min_segment_secs.",
    ),
    (
        "tests/test_pipeline_diarize_multispeaker.py::test_diarize_pyannote_error_falls_back_to_ecapa_and_bumps_counter",
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
        assert test_id.startswith("tests/test_pipeline_diarize_multispeaker.py::"), (
            f"test_id must be fully qualified 'file::name': {test_id!r}"
        )
        assert isinstance(rationale, str) and len(rationale) > 20, (
            f"Rationale too short (must explain WHY and HOW to fix): {rationale!r}"
        )


def test_xfail_decorators_align_with_allowlist():
    """P0.0.2 structural lock: every test in `INFRA_DEBT_FAILURES` must
    carry `@pytest.mark.xfail` so slow CI reports XFAIL instead of FAILED.

    Keeps the two artifacts in sync — if a future maintainer fixes one
    test, the cleanup steps (remove allowlist entry + remove xfail
    decorator) MUST happen together. Catching half-fixes here is what
    the structural-invariant pattern is for.

    AST-scans `test_pipeline.py` for each test function named in
    `INFRA_DEBT_FAILURES`; asserts each carries a `pytest.mark.xfail`
    decorator. Failure mode: a future maintainer removes the decorator
    without removing the allowlist entry (or vice versa).
    """
    import ast
    import pathlib

    # P1.A1 SP-1: the 8 infra-debt tests moved from root test_pipeline.py into
    # the split tests/test_pipeline_diarize_multispeaker.py (their xfail decorators
    # moved verbatim with them).
    src = pathlib.Path(__file__).resolve().parent / "test_pipeline_diarize_multispeaker.py"
    tree = ast.parse(src.read_text(encoding="utf-8"))

    # Build name -> function-node lookup.
    # P0.R6.Y D3 cascade: some legacy tests became `async def` during the
    # voice_mod migration. Treat both FunctionDef + AsyncFunctionDef as
    # function nodes — xfail decorators work on both shapes identically.
    funcs_by_name: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {
        n.name: n
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    for test_id, _rationale in INFRA_DEBT_FAILURES:
        # test_id is "test_pipeline.py::test_<name>"
        _, _, func_name = test_id.partition("::")
        assert func_name in funcs_by_name, (
            f"{test_id} is in INFRA_DEBT_FAILURES but the function "
            f"is missing from test_pipeline_diarize_multispeaker.py. Either the test was "
            f"renamed (update the allowlist) or deleted (remove the "
            f"allowlist entry + decrement INFRA_DEBT_CAP)."
        )

        func = funcs_by_name[func_name]
        has_xfail = any(
            (
                isinstance(deco, ast.Call)
                and isinstance(deco.func, ast.Attribute)
                and deco.func.attr == "xfail"
            )
            or (
                isinstance(deco, ast.Attribute)
                and deco.attr == "xfail"
            )
            for deco in func.decorator_list
        )
        assert has_xfail, (
            f"{test_id} is in INFRA_DEBT_FAILURES but the function "
            f"body lacks a @pytest.mark.xfail decorator. P0.0.2 disposition "
            f"requires both artifacts to stay in sync:\n"
            f"  - allowlist entry → declares the infra debt is accepted\n"
            f"  - xfail decorator → tells pytest to report XFAIL not FAILED\n"
            f"If the test is now genuinely fixed: remove from allowlist "
            f"AND decrement INFRA_DEBT_CAP AND remove the decorator (all "
            f"three steps). If the decorator was accidentally dropped: "
            f"restore it."
        )
