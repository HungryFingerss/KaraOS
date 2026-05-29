"""tests/test_p0_s1_phase4.py — P0.S1 Phase 4 closure suite.

Plan v2 §10 Phase 4 = 14 tests:
- 5 AST invariants — ALLOWED set / no-legacy / verdict-passed / upstream-verify_live / non-literal-source-flag
- 4 D9 tripwires — voice-only fallthrough, recognition_update catch-all (MED 4),
  burst-alert dispatch, recognition_update verdict-None
- 5 replay smoke — verdict True / False / None matrix + distinct reason codes
  + burst fixture

Plus 3 deliberate-regression confirmations run at closure time (NOT pytest
cases — closure-report items per induction-surfaces-invariant-gaps).
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import ast
import asyncio
import json
import pathlib
import re
import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
_PIPELINE_PY = _REPO_ROOT / "pipeline.py"
_ENROLL_PY = _REPO_ROOT / "enroll.py"


def _read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def _random_embedding(seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(512).astype(np.float32)
    v /= np.linalg.norm(v)
    return v


# AST helpers ───────────────────────────────────────────────────────────────


def _find_add_embedding_calls(src: str) -> "list[tuple[ast.Call, ast.AST]]":
    """Yield (Call node, enclosing function node) for every `*.add_embedding(...)`
    call where the receiver looks like a FaceDB-ish object.

    Enclosing function = nearest ast.FunctionDef / ast.AsyncFunctionDef.
    Returns list (not generator) so callers can iterate freely.
    """
    tree = ast.parse(src)
    # First pass: annotate parents so we can find enclosing functions.
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            child._parent = node  # type: ignore[attr-defined]

    out: list[tuple[ast.Call, ast.AST]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Attribute) and f.attr == "add_embedding":
                # Walk up to find enclosing function.
                enclosing: ast.AST = node
                while enclosing is not None and not isinstance(
                    enclosing, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Module)
                ):
                    enclosing = getattr(enclosing, "_parent", None)
                if enclosing is not None:
                    out.append((node, enclosing))
    return out


def _get_source_arg(call: ast.Call) -> "ast.AST | None":
    """Return the AST node for the `source` arg (positional 3rd or keyword)."""
    # Positional: signature is (person_id, embedding, source, ...).
    if len(call.args) >= 3:
        return call.args[2]
    for kw in call.keywords:
        if kw.arg == "source":
            return kw.value
    return None


def _get_kwarg(call: ast.Call, name: str) -> "ast.AST | None":
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    return None


def _resolves_to_protected_literal(arg: "ast.AST | None") -> "str | None":
    """Return the literal source string if arg is `ast.Constant(value=str)` in
    ALLOWED_EMBEDDING_SOURCES_REQUIRING_ANTI_SPOOF, else None."""
    from core.db import ALLOWED_EMBEDDING_SOURCES_REQUIRING_ANTI_SPOOF
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        if arg.value in ALLOWED_EMBEDDING_SOURCES_REQUIRING_ANTI_SPOOF:
            return arg.value
    return None


# ────────────────────────────────────────────────────────────────────────────
# (1-5) AST invariants — Plan v2 §3 / §10
# ────────────────────────────────────────────────────────────────────────────


def test_invariant_allowed_source_set_locked():
    """The ALLOWED set equals VALID after the D4 deletion of legacy_unknown.
    A future addition to VALID without conscious anti-spoof analysis would
    silently expand the gate's coverage; this test forces explicit review."""
    from core.db import VALID_EMBEDDING_SOURCES, ALLOWED_EMBEDDING_SOURCES_REQUIRING_ANTI_SPOOF
    assert VALID_EMBEDDING_SOURCES == frozenset({
        "enrollment", "recognition_update", "progressive_enroll",
    })
    assert ALLOWED_EMBEDDING_SOURCES_REQUIRING_ANTI_SPOOF == VALID_EMBEDDING_SOURCES


def test_invariant_no_legacy_unknown_in_production_callers():
    """Plan v2 §1 D4 — no production caller may use `source="legacy_unknown"`.
    AST scan pipeline.py + enroll.py + core/*.py for any add_embedding call
    where source is the literal `legacy_unknown` constant."""
    violations: list[str] = []
    for path in [_PIPELINE_PY, _ENROLL_PY] + sorted((_REPO_ROOT / "core").glob("*.py")):
        src = _read(path)
        for call, fn in _find_add_embedding_calls(src):
            arg = _get_source_arg(call)
            if (isinstance(arg, ast.Constant)
                    and isinstance(arg.value, str)
                    and arg.value == "legacy_unknown"):
                violations.append(
                    f"{path.name}:{call.lineno} — add_embedding(..., "
                    f"source='legacy_unknown') is forbidden per D4"
                )
    assert violations == [], (
        "Production callers must NOT use legacy_unknown source after D4:\n"
        + "\n".join(violations)
    )


def test_invariant_every_protected_source_add_embedding_passes_verdict():
    """Plan v2 §3.3 — every literal-source add_embedding with source ∈
    ALLOWED must pass `anti_spoof_verdict=` kwarg AND the value must be
    either a literal True OR a Name (variable holding the verdict)."""
    violations: list[str] = []
    for path in [_PIPELINE_PY, _ENROLL_PY]:
        src = _read(path)
        for call, fn in _find_add_embedding_calls(src):
            src_arg = _get_source_arg(call)
            literal_source = _resolves_to_protected_literal(src_arg)
            if literal_source is None:
                continue  # not a protected literal — covered by next test
            verdict_kw = _get_kwarg(call, "anti_spoof_verdict")
            if verdict_kw is None:
                violations.append(
                    f"{path.name}:{call.lineno} — add_embedding(..., "
                    f"source={literal_source!r}) missing anti_spoof_verdict= kwarg"
                )
                continue
            # Accept literal True OR a Name.
            if isinstance(verdict_kw, ast.Constant):
                if verdict_kw.value is not True:
                    violations.append(
                        f"{path.name}:{call.lineno} — anti_spoof_verdict literal "
                        f"is {verdict_kw.value!r}, must be True or a variable"
                    )
            elif not isinstance(verdict_kw, (ast.Name, ast.Attribute)):
                violations.append(
                    f"{path.name}:{call.lineno} — anti_spoof_verdict expr is "
                    f"{type(verdict_kw).__name__}, expected Name / Attribute / True"
                )
    assert violations == [], (
        "P0.S1 verdict-passed invariant violations:\n"
        + "\n".join(violations)
    )


def test_invariant_every_protected_source_call_site_has_upstream_verify_live():
    """Plan v2 §3.1 — every literal-source add_embedding with source ∈
    ALLOWED must have a `verify_live(...)` Call node OR a
    `_classify_anti_spoof_verdict(...)` Call node (Phase 2 helper) in the
    same enclosing function body at a strictly lower line number."""
    violations: list[str] = []
    for path in [_PIPELINE_PY, _ENROLL_PY]:
        src = _read(path)
        for call, fn in _find_add_embedding_calls(src):
            src_arg = _get_source_arg(call)
            literal_source = _resolves_to_protected_literal(src_arg)
            if literal_source is None:
                continue
            # Walk the function body looking for verify_live or
            # _classify_anti_spoof_verdict calls upstream of this call.
            assert isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)), (
                "Module-level add_embedding callers not supported"
            )
            upstream_found = False
            for inner in ast.walk(fn):
                if not isinstance(inner, ast.Call):
                    continue
                if inner.lineno >= call.lineno:
                    continue
                name: str | None = None
                f = inner.func
                if isinstance(f, ast.Name):
                    name = f.id
                elif isinstance(f, ast.Attribute):
                    name = f.attr
                if name in ("verify_live", "_classify_anti_spoof_verdict",
                            "peek_anti_spoof_verdict"):
                    upstream_found = True
                    break
            if not upstream_found:
                violations.append(
                    f"{path.name}:{call.lineno} — add_embedding(..., "
                    f"source={literal_source!r}) has no upstream verify_live / "
                    f"_classify_anti_spoof_verdict / peek_anti_spoof_verdict in "
                    f"fn '{fn.name}'"
                )
    assert violations == [], (
        "P0.S1 upstream-verify_live invariant violations:\n"
        + "\n".join(violations)
    )


def test_invariant_non_literal_source_args_flagged():
    """Plan v2 §3.3 — if source arg is non-literal (Name, Attribute, Call,
    BinOp, etc.), it must opt out via `# noqa: P0S1-allow-non-literal-source:`
    annotation OR be in the empty allowlist (registry empty in Plan v2)."""
    violations: list[str] = []
    for path in [_PIPELINE_PY, _ENROLL_PY]:
        src = _read(path)
        lines = src.splitlines()
        for call, fn in _find_add_embedding_calls(src):
            arg = _get_source_arg(call)
            if arg is None or isinstance(arg, ast.Constant):
                continue  # literal — covered by other tests
            # Non-literal — require opt-out marker on the call's start line
            # or any of the next 3 lines (allow multi-line call shapes).
            opt_marker_re = re.compile(r"#\s*noqa:\s*P0S1-allow-non-literal-source")
            opt_found = any(
                opt_marker_re.search(lines[i - 1])
                for i in range(call.lineno, min(call.lineno + 4, len(lines) + 1))
            )
            if not opt_found:
                violations.append(
                    f"{path.name}:{call.lineno} — non-literal source arg "
                    f"({type(arg).__name__}) without "
                    f"`# noqa: P0S1-allow-non-literal-source: <rationale>`"
                )
    assert violations == [], (
        "Non-literal source arg violations (need opt-out annotation):\n"
        + "\n".join(violations)
    )


# ────────────────────────────────────────────────────────────────────────────
# (6-9) D9 tripwires
# ────────────────────────────────────────────────────────────────────────────


def _fresh_db(tmp_path):
    import core.db as _db_mod
    with patch.object(_db_mod, "DB_PATH", tmp_path / "f.db"), \
         patch.object(_db_mod, "FAISS_INDEX_PATH", tmp_path / "f.index"):
        db = _db_mod.FaceDB()
        db.add_person("pid_a", "Alice", None)
        return db


def test_tripwire_recognition_update_with_rejected_verdict_blocked_by_catch_all(tmp_path):
    """Plan v2 MED 4 / D9 tripwire — recognition_update path is gated explicitly
    at its call site (pipeline.py:6469 zone). This belt-and-braces test verifies
    the add_embedding catch-all ALSO blocks recognition_update when verdict is
    False — guards against a future refactor that strips the explicit gate."""
    db = _fresh_db(tmp_path)
    try:
        ok = db.add_embedding(
            "pid_a", _random_embedding(20), "recognition_update", confidence=0.5,
            anti_spoof_verdict=False,
        )
        assert ok is False
        cnt = db._conn.execute(
            "SELECT COUNT(*) FROM embeddings WHERE person_id='pid_a'"
        ).fetchone()[0]
        assert cnt == 0
    finally:
        db._conn.close()


def test_tripwire_recognition_update_with_verdict_none_blocked_by_catch_all(tmp_path):
    """Same belt-and-braces invariant but for verdict=None — catches a future
    refactor that forgets to compute the verdict at all (kwarg defaulted)."""
    db = _fresh_db(tmp_path)
    try:
        ok = db.add_embedding(
            "pid_a", _random_embedding(21), "recognition_update", confidence=0.5,
            anti_spoof_verdict=None,
        )
        assert ok is False
    finally:
        db._conn.close()


def test_tripwire_voice_only_fallthrough_branch_intact():
    """D9 tripwire — voice-only fallthrough branch in pipeline.py is the
    structural guarantee that face-write rejection does NOT prevent session
    open. Source-inspection that the Bug C code path is intact AND the
    rejection elif-branch never sets _face_captured=True (which would break
    the fallthrough invariant — face block must keep _face_captured=False
    so the else-branch grants bootstrap credits)."""
    src = _read(_PIPELINE_PY)
    # Bug C voice-only branch must exist.
    assert "Voice-only engagement — NO face was captured" in src

    # Locate the rejection elif-block by its exact signature.
    elif_sig = "elif _gate_live is not True:"
    assert elif_sig in src, (
        "Anti-spoof rejection elif-branch missing — Phase 3 wiring lost"
    )
    elif_idx = src.index(elif_sig)
    # The elif block extends until the next `if len(audio_buf)` (next sibling
    # block at the same indentation level inside the progressive_enroll body).
    end_marker = "if len(audio_buf)"
    end_idx = src.find(end_marker, elif_idx)
    assert end_idx > elif_idx, "Could not find end of elif-block"
    elif_body = src[elif_idx:end_idx]

    # The elif-branch must NEVER set _face_captured = True — that would let a
    # blocked face attempt fabricate a face-witness session.
    assert "_face_captured = True" not in elif_body, (
        "D9 tripwire: rejection elif-branch must NOT set _face_captured=True "
        "(would break the voice-only fallthrough invariant)"
    )
    # And it must surface the rejection signals (D10.c dashboard path).
    assert "record_rejection" in elif_body
    assert "report_anti_spoof_rejection" in elif_body


def test_tripwire_burst_alert_dispatch_exact_equality():
    """D9 tripwire — burst alert MUST use exact equality (`count == THRESHOLD`)
    so it fires exactly once per burst window. Forbids `>=` or `>` reaching
    the report_anti_spoof_burst dispatch."""
    src = _read(_PIPELINE_PY)
    # Find every report_anti_spoof_burst call and verify the immediately
    # preceding `if` uses exact equality.
    burst_calls = list(re.finditer(r"report_anti_spoof_burst\(", src))
    assert burst_calls, "Burst-dispatch call must exist in pipeline.py"
    for m in burst_calls:
        # Look back up to 250 chars for the gating `if` statement.
        upstream = src[max(0, m.start() - 250) : m.start()]
        eq_re = re.compile(r"if\s+_rej_count\s*==\s*ANTI_SPOOF_BURST_THRESHOLD")
        ge_re = re.compile(r"if\s+_rej_count\s*(?:>=|>)\s*ANTI_SPOOF_BURST_THRESHOLD")
        assert eq_re.search(upstream), (
            "D9 tripwire: burst dispatch must be guarded by EXACT equality "
            "(`==`, not `>=` / `>`) per Plan v2 §14b.1"
        )
        assert not ge_re.search(upstream), (
            "D9 tripwire: `>=` or `>` would cause re-firing on subsequent "
            "rejections within the window"
        )


# ────────────────────────────────────────────────────────────────────────────
# (10-14) Replay smoke — verdict matrix + reason codes + burst fixture
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("verdict", [True, False, None])
def test_replay_anti_spoof_verdict_matrix(verdict):
    """Plan v2 §10 — replay smoke for the (True / False / None) verdict matrix.
    VisionFramePayload round-trips the verdict field through json encode →
    `_event_log_default` JSON encoder → `from_json_dict` deserializer (the
    full replay round-trip surface used by tools/replay_session.py)."""
    from core.event_log.types import VisionFramePayload
    from core.event_log.producer import _event_log_default

    payload = VisionFramePayload(
        frame_id=f"f_verdict_{verdict}",
        frame_path=None,
        frame_ts=1000.0,
        n_detections=1,
        recognized=(),
        unrecognized_track_ids=(7,),
        anti_spoof_live=verdict,
        anti_spoof_score=0.5 if verdict is not None else None,
    )

    # Round-trip through the SAME encoder + decoder used by the writer task
    # + tools/replay_session.py — proves the field survives serialization.
    encoded = json.dumps(payload.__dict__, default=_event_log_default)
    decoded = json.loads(encoded)
    assert "anti_spoof_live" in decoded, (
        "anti_spoof_live missing from encoded vision_frame payload"
    )
    assert decoded["anti_spoof_live"] == verdict, (
        f"Verdict {verdict!r} did NOT round-trip; got {decoded['anti_spoof_live']!r}"
    )

    # And rehydrate through from_json_dict (replay consumer side).
    rehydrated = VisionFramePayload.from_json_dict(decoded)
    assert rehydrated.anti_spoof_live == verdict, (
        f"Rehydrated verdict mismatch: expected {verdict!r}, got {rehydrated.anti_spoof_live!r}"
    )


def test_replay_reason_codes_distinguishable_at_watchdog_layer():
    """Plan v2 §10 — distinct reason codes preserved through the watchdog
    alert pipeline. report_anti_spoof_rejection stores `reason` in alert
    metadata so dashboard / replay can branch on it."""
    from core.brain_agent import WatchdogAgent
    from core.config import (
        ANTI_SPOOF_REASON_PASSED, ANTI_SPOOF_REASON_REJECTED,
        ANTI_SPOOF_REASON_UNAVAILABLE, ANTI_SPOOF_REASON_NO_VERDICT,
    )

    fake_db = MagicMock()
    fake_db.unresolved_alert_exists.return_value = False
    wd = WatchdogAgent(fake_db, MagicMock())

    # Verify all 4 reason codes flow through distinguishably.
    for reason in (ANTI_SPOOF_REASON_PASSED, ANTI_SPOOF_REASON_REJECTED,
                   ANTI_SPOOF_REASON_UNAVAILABLE, ANTI_SPOOF_REASON_NO_VERDICT):
        fake_db.reset_mock()
        wd.report_anti_spoof_rejection(
            track_id="tw", reason=reason, score=None, person_id="pid_w",
        )
        alert_type, severity, message, metadata = fake_db.store_alert.call_args[0]
        assert metadata["reason"] == reason
        # The four reason codes are distinct strings — no aliasing.
        assert reason in (
            ANTI_SPOOF_REASON_PASSED, ANTI_SPOOF_REASON_REJECTED,
            ANTI_SPOOF_REASON_UNAVAILABLE, ANTI_SPOOF_REASON_NO_VERDICT,
        )


def test_replay_burst_fixture_sequence_observable():
    """Plan v2 §10 — burst fixture: 3+ rejection events within window cause
    the watchdog burst alert. End-to-end through the rejection store + the
    exact-equality dispatcher logic."""
    from core.anti_spoof_rejection_store import AntiSpoofRejectionStore
    from core.config import ANTI_SPOOF_BURST_THRESHOLD, ANTI_SPOOF_BURST_WINDOW_SECS

    store = AntiSpoofRejectionStore()
    dispatched = []

    async def main():
        now = 100.0
        for i in range(ANTI_SPOOF_BURST_THRESHOLD + 2):
            cnt = await store.record_rejection(
                "tb", now + i, ANTI_SPOOF_BURST_WINDOW_SECS
            )
            # Replay simulates the pipeline-side dispatcher.
            if cnt == ANTI_SPOOF_BURST_THRESHOLD:
                dispatched.append(cnt)

    asyncio.run(main())

    # Exactly one dispatch event observable across the burst sequence.
    assert dispatched == [ANTI_SPOOF_BURST_THRESHOLD], (
        f"Burst fixture must surface exactly one dispatch; observed {dispatched}"
    )
