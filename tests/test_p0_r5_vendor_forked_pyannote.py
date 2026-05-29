"""P0.R5 — Vendor forked pyannote + speechbrain (9 logical anchors).

Validates that pyannote-audio + speechbrain are installed from the vendored
forks (eliminating the runtime monkey-patching that previously lived in
``tests/patch_pyannote_io.py``). Hybrid test surface per Q6 (a):
source-inspection anchors (A1-A3 + A6-A7) always run; behavioral import
anchors (A4-A5) always run; CUDA-gated smoke anchors (A8-A9) skip when
hardware/credentials unavailable.

Per Plan v1 §3 LOCK: 9 anchors at exact mid 9 inclusive ±15% band
[7.65, 10.35].
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import ast
import inspect
import os
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parent.parent
_REQUIREMENTS = _REPO_ROOT / "requirements.txt"
_CLAUDE_MD = _REPO_ROOT / "CLAUDE.md"
_VOICE_PY = _REPO_ROOT / "core" / "voice.py"
_PATCH_SCRIPT = _REPO_ROOT / "tests" / "patch_pyannote_io.py"


def _cuda_available() -> bool:
    """Best-effort CUDA detection without importing torch at module scope."""
    try:
        import torch  # noqa: PLC0415

        return bool(torch.cuda.is_available())
    except Exception:
        return False


def _require_hf_token_or_skip() -> None:
    """Behavioral smoke tests requiring HF_TOKEN skip cleanly without one."""
    if not os.getenv("HF_TOKEN"):
        pytest.skip("HF_TOKEN not set — skipping pyannote-pinned smoke test")


def _require_real_voice_module_or_skip() -> None:
    """A8/A9 smoke tests need the REAL core.voice (not the conftest MagicMock
    stub). Conftest's ``setup_pipeline_stubs()`` installs a stub when
    core.voice isn't in sys.modules at autouse-fixture time — that path
    can't actually load ECAPA-TDNN. Skip cleanly when the stub is detected
    so the integration test only runs in environments where the real
    module is reachable (typically: `pytest tests/test_voice.py` first,
    then `pytest tests/test_p0_r5_vendor_forked_pyannote.py`, or a direct
    `python -c "import core.voice; core.voice.load_speaker_embedder()"`).
    """
    import sys

    from unittest.mock import MagicMock

    voice = sys.modules.get("core.voice")
    if voice is None:
        return  # Nothing imported yet — real import path will fire.
    if isinstance(getattr(voice, "load_speaker_embedder", None), MagicMock):
        pytest.skip(
            "core.voice is the conftest MagicMock stub — A8/A9 smoke tests "
            "need the real module. Run with the real voice module preloaded "
            "(e.g. pytest tests/test_voice.py first, or invoke standalone)."
        )


# ---------------------------------------------------------------------------
# A1 (D4) — patch script deleted
# ---------------------------------------------------------------------------


def test_p0_r5_d4_anchor_1_patch_script_deleted() -> None:
    """A1 — tests/patch_pyannote_io.py MUST NOT exist (deleted at P0.R5 Phase 3).

    Per Plan v1 §2.4 + §2.6 (a) deliberate-regression: re-adding the patch
    script must fire this anchor.
    """
    assert not _PATCH_SCRIPT.exists(), (
        f"D4 regression: tests/patch_pyannote_io.py reappeared at "
        f"{_PATCH_SCRIPT}. Per P0.R5 Plan v1 §2.4, this script was deleted "
        f"because the vendored forks now carry the patches at install time. "
        f"If a patch needs to be re-applied, add it to the fork commit "
        f"rather than restoring runtime patching."
    )


# ---------------------------------------------------------------------------
# A2 + A3 (D3) — requirements.txt has both git URLs
# ---------------------------------------------------------------------------


def test_p0_r5_d3_anchor_1_requirements_has_pyannote_git_url() -> None:
    """A2 — requirements.txt MUST contain the pyannote-audio fork git URL.

    Per Plan v1 §2.3 + §2.6 (b) deliberate-regression: removing the pyannote
    git URL line must fire this anchor.
    """
    content = _REQUIREMENTS.read_text(encoding="utf-8")
    needle = "pyannote.audio @ git+https://github.com/HungryFingerss/pyannote-audio.git@"
    assert needle in content, (
        f"D3 regression: requirements.txt missing pyannote.audio git URL. "
        f"Expected substring {needle!r}. Per Plan v1 §2.3, P0.R5 installs "
        f"pyannote.audio from the vendored fork @ pinned SHA."
    )


def test_p0_r5_d3_anchor_2_requirements_has_speechbrain_git_url() -> None:
    """A3 — requirements.txt MUST contain the speechbrain fork git URL AND
    NOT the legacy ``speechbrain>=1.0.3`` version-pin line.

    Per Plan v1 §2.3 + §2.6 (c) deliberate-regression: restoring the old
    speechbrain>=1.0.3 line must fire this anchor.
    """
    content = _REQUIREMENTS.read_text(encoding="utf-8")
    git_url = "speechbrain @ git+https://github.com/HungryFingerss/speechbrain.git@"
    assert git_url in content, (
        f"D3 regression: requirements.txt missing speechbrain git URL. "
        f"Expected substring {git_url!r}."
    )
    legacy_pin = "speechbrain>=1.0.3"
    assert legacy_pin not in content, (
        f"D3 regression: requirements.txt still contains legacy "
        f"{legacy_pin!r} line. Per Plan v1 §2.3, this line was REPLACED "
        f"by the git URL form at P0.R5."
    )


# ---------------------------------------------------------------------------
# A4 + A5 (D1 + D2) — behavioral import without runtime patch
# ---------------------------------------------------------------------------


def test_p0_r5_d1_anchor_1_pyannote_imports_without_runtime_patch() -> None:
    """A4 — ``from pyannote.audio import Pipeline`` succeeds WITHOUT the
    deleted runtime patch script. Confirms the fork's in-tree patches are
    active.
    """
    # Pre-P1 Bundle 5: skip (not fail) when the vendored fork isn't installed
    # (e.g., Windows dev box). The fork is a git-URL install in requirements.txt;
    # the PyPI build would wrongly fail the source-inspection below, so importorskip
    # is the correct gate — validate fork-correctness when present, skip when absent.
    pytest.importorskip("pyannote.audio")
    # If the patches weren't applied, importing this module would raise
    # AttributeError on AudioMetaData or list_audio_backends at module load.
    from pyannote.audio import Pipeline  # noqa: F401

    # Defense-in-depth: inspect a known-patched source location to confirm
    # the fork is actually serving the patched bytes.
    from pyannote.audio.core import io as _io

    src = inspect.getsource(_io)
    assert "-> object:" in src, (
        "D1 regression: pyannote/audio/core/io.py source no longer contains "
        "Patch 1's '-> object:' return annotation. Either the fork was "
        "reverted or pip pulled a different (upstream) revision."
    )
    assert "getattr(torchaudio, 'list_audio_backends'" in src, (
        "D1 regression: pyannote/audio/core/io.py source no longer contains "
        "Patch 2's getattr-with-fallback list_audio_backends call."
    )


def test_p0_r5_d2_anchor_1_speechbrain_imports_without_runtime_patch() -> None:
    """A5 — ``from speechbrain.utils.torch_audio_backend import ...``
    succeeds WITHOUT the deleted runtime patch script.
    """
    # Pre-P1 Bundle 5: skip when the vendored fork isn't installed (see d1 rationale).
    pytest.importorskip("speechbrain.utils.torch_audio_backend")
    from speechbrain.utils import torch_audio_backend  # noqa: F401

    src = inspect.getsource(torch_audio_backend)
    assert "getattr(torchaudio, 'list_audio_backends'" in src, (
        "D2 regression: speechbrain/utils/torch_audio_backend.py source no "
        "longer contains Patch 4's getattr-with-fallback list_audio_backends "
        "call. Either the fork was reverted or pip pulled upstream."
    )


# ---------------------------------------------------------------------------
# A6 (D4) — core/voice.py contains zero runtime monkeypatch sites
# ---------------------------------------------------------------------------


def test_p0_r5_d4_anchor_2_voice_no_runtime_monkeypatch() -> None:
    """A6 — AST scan of core/voice.py MUST find zero ``_ta.list_audio_backends
    = lambda`` (or equivalent) assignment sites.

    Covers BOTH old line 51 (module-load patch) AND old line 95 (inside
    ``load_speaker_embedder()`` guard) per non-blocking observation #1.

    Per Plan v1 §2.4 + §2.6 (d) deliberate-regression: re-adding either
    monkeypatch site must fire this anchor.
    """
    source = _VOICE_PY.read_text(encoding="utf-8")
    tree = ast.parse(source)

    violations: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        # Pattern: <ANY>.list_audio_backends = <lambda>
        for target in node.targets:
            if not isinstance(target, ast.Attribute):
                continue
            if target.attr != "list_audio_backends":
                continue
            if not isinstance(node.value, ast.Lambda):
                continue
            violations.append(
                f"line {node.lineno}: {ast.unparse(target)} = lambda (...)"
            )

    assert not violations, (
        f"D4 regression: core/voice.py contains runtime monkeypatch "
        f"site(s): {violations}. Per Plan v1 §2.4 + non-blocking "
        f"observation #1, BOTH old monkeypatch sites (module-load at "
        f"~line 51 + load_speaker_embedder guard at ~line 95) MUST stay "
        f"deleted now that the patches live in the vendored forks."
    )


# ---------------------------------------------------------------------------
# A7 (D6) — CLAUDE.md narrative refreshed
# ---------------------------------------------------------------------------


def test_p0_r5_d6_anchor_1_claude_md_section_refreshed() -> None:
    """A7 — CLAUDE.md MUST contain the new ``## Pyannote vendoring (P0.R5``
    section header AND its github-availability assumption documentation
    (per non-blocking observation #1) AND the fork URL substring.

    Per Plan v1 §2.6 (e) deliberate-regression: replacing the new section
    with the old ``## Pyannote dependency maintenance (Phase 2, Session 88)``
    section must fire this anchor.
    """
    content = _CLAUDE_MD.read_text(encoding="utf-8")
    content_lower = content.lower()
    required = [
        ("## Pyannote vendoring (P0.R5",
            "D6 regression: CLAUDE.md missing new P0.R5 vendoring section header.",
            content),
        ("git+https://github.com/HungryFingerss/pyannote-audio.git",
            "D6 regression: CLAUDE.md missing pyannote-audio fork URL.",
            content),
        # Case-insensitive match — Plan v1 §2.6 LOCKED D6 content uses
        # "GitHub-availability" (proper-noun capitalization in bold header)
        # but Plan v1 §6 grep table uses lowercase "github-availability".
        # Lowering the haystack here resolves the spec-internal capitalization
        # mismatch (banked as Phase 5 architect-handoff observation #3).
        ("github-availability assumption",
            "D6 regression: CLAUDE.md missing github-availability assumption "
            "documentation (required per non-blocking observation #1).",
            content_lower),
    ]
    for needle, msg, haystack in required:
        assert needle in haystack, msg


# ---------------------------------------------------------------------------
# A8 + A9 (D1 + D2) — CUDA-gated smoke tests
# ---------------------------------------------------------------------------


def test_p0_r5_d1_anchor_2_pyannote_pipeline_constructible_at_sha() -> None:
    """A8 — ``Pipeline.from_pretrained(...)`` succeeds against the SHA-pinned
    fork. Smoke test — proves the patched fork can actually construct a
    pipeline end-to-end (not just import the module).

    SKIPs cleanly if no CUDA OR HF_TOKEN missing.
    """
    if not _cuda_available():
        pytest.skip("CUDA unavailable — skipping pyannote pipeline smoke test")
    _require_hf_token_or_skip()
    _require_real_voice_module_or_skip()

    from pyannote.audio import Pipeline

    pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1",
        use_auth_token=os.getenv("HF_TOKEN"),
    )
    assert pipeline is not None, (
        "D1 smoke: Pipeline.from_pretrained returned None. The fork's "
        "Patch 3 (huggingface_hub kwarg rename) or Patch 7 (weights_only) "
        "may be silently broken."
    )


def test_p0_r5_d2_anchor_2_speechbrain_encoder_constructible() -> None:
    """A9 — ECAPA-TDNN encoder construction succeeds via the production path
    in ``core.voice.load_speaker_embedder()`` against the vendored
    speechbrain fork.

    Routes through ``core.voice.load_speaker_embedder()`` rather than
    ``EncoderClassifier.from_hparams(...)`` directly because the production
    helper carries the runtime ``hf_hub_download`` ``use_auth_token`` kwarg
    wrapper that is OUT OF SCOPE for P0.R5 (the fork only carries the
    ``list_audio_backends`` patch per Plan v1 §2.2). Banked as Known
    Limitation in P0.R5 closure narrative — future cycle may move the
    huggingface_hub wrapper into the speechbrain fork.

    SKIPs cleanly if no CUDA.
    """
    if not _cuda_available():
        pytest.skip("CUDA unavailable — skipping speechbrain encoder smoke test")
    _require_real_voice_module_or_skip()

    import core.voice as voice

    # Reset singleton so the test exercises a real load rather than a
    # warm-cache no-op.
    voice._embedder = None  # type: ignore[attr-defined]
    voice.load_speaker_embedder(device="cuda")
    assert voice._embedder is not None, (  # type: ignore[attr-defined]
        "D2 smoke: load_speaker_embedder left _embedder=None after a real "
        "load attempt. The fork's Patch 4 (list_audio_backends rewrite) "
        "may be silently broken at encoder-construction time, OR the "
        "production hf_hub_download wrapper drifted."
    )
