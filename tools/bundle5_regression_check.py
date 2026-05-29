"""One-shot deliberate-regression harness for Pre-P1 Bundle 5 per Plan v1 §4.

For each anchor A1-A7: snapshot file → mutate (induce the violation) → run the
targeted anchor test → assert it FAILS → restore → re-run → assert it PASSES.

Per `### Induction-surfaces-invariant-gaps`: the induction IS the test of the
invariant. Bundle 3 Q1 (b) lesson applied — every scenario must fire correctly.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PYTEST_BIN = [sys.executable, "-m", "pytest", "-q", "--tb=line", "--no-header"]


def run_test(node_id: str) -> int:
    r = subprocess.run(PYTEST_BIN + [node_id], cwd=REPO_ROOT, capture_output=True, text=True)
    return r.returncode


def scenario(label: str, target: Path, old: bytes, new: bytes, anchor: str) -> bool:
    snapshot = target.read_bytes()
    if old not in snapshot:
        print(f"  {label} SETUP-FAIL: anchor string not found in {target.name}")
        return False
    if snapshot.count(old) != 1:
        print(f"  {label} SETUP-FAIL: anchor string not unique in {target.name} "
              f"({snapshot.count(old)} occurrences)")
        return False
    target.write_bytes(snapshot.replace(old, new, 1))
    try:
        fired = run_test(anchor) != 0
    finally:
        target.write_bytes(snapshot)
    restored = run_test(anchor) == 0
    status = "OK" if (fired and restored) else "FAIL"
    print(f"  {label} {status}: fired-on-mutation={fired} | restored-clean={restored}")
    return fired and restored


def main() -> int:
    VOICE = REPO_ROOT / "core" / "voice.py"
    VOICE_CHANNEL = REPO_ROOT / "core" / "voice_channel.py"
    RECONCILER = REPO_ROOT / "core" / "reconciler.py"
    EVENTLOG_TYPES = REPO_ROOT / "core" / "event_log" / "types.py"
    SESSION_STATE = REPO_ROOT / "core" / "session_state.py"

    A = "tests/test_bundle5_anchors.py"
    A6 = "tests/test_no_exact_equality_against_claim_confidence.py"
    A7 = "tests/test_session_snapshot_collection_fields_are_immutable.py"

    print("Deliberate-regression harness for Pre-P1 Bundle 5 (Contract Typing)\n")
    results = []

    # (A1) Remove the IdentityClaim.confidence_is_no_signal field → A1 fires.
    results.append(scenario(
        label="(A1) Remove confidence_is_no_signal field",
        target=VOICE_CHANNEL,
        old=b"    raw_segment_scores:   tuple[tuple[Optional[str], float], ...] = ()\n    confidence_is_no_signal: bool = False",
        new=b"    raw_segment_scores:   tuple[tuple[Optional[str], float], ...] = ()",
        anchor=f"{A}::test_a1_identity_claim_has_confidence_is_no_signal_field",
    ))

    # (A2) Revert voice.identify no-signal return to a 2-tuple → A2 fires.
    results.append(scenario(
        label="(A2) Revert identify no-signal return to 2-tuple",
        target=VOICE,
        old=b"        return None, 0.0, True\n",
        new=b"        return None, 0.0\n",
        anchor=f"{A}::test_a2_voice_identify_returns_3tuple_with_correct_flags",
    ))

    # (A3) Drop the flag at the audio-None by-construction site → A3 fires.
    results.append(scenario(
        label="(A3) Drop confidence_is_no_signal=True at audio-None site",
        target=VOICE_CHANNEL,
        old=b'            reasoning="audio_buf is None",\n            confidence_is_no_signal=True,\n',
        new=b'            reasoning="audio_buf is None",\n',
        anchor=f"{A}::test_a3_identify_speaker_sets_flag_behaviorally",
    ))

    # (A4) Drop the `< 0.0` half of the 628 migration → Session-119 canary fires.
    results.append(scenario(
        label="(A4) Drop `< 0.0` half of 628 (Session-119 load-bearing)",
        target=RECONCILER,
        old=b"            and (claim.confidence_is_no_signal or claim.confidence < 0.0)\n",
        new=b"            and claim.confidence_is_no_signal\n",
        anchor=f"{A}::test_a4_session_119_negative_cosine_canary_fires",
    ))

    # (A5) Drop the event-log decoder flag line → A5 round-trip fires.
    results.append(scenario(
        label="(A5) Drop event-log decoder flag line",
        target=EVENTLOG_TYPES,
        old=b'        raw_segment_scores=raw_tuples,\n        confidence_is_no_signal=bool(d.get("confidence_is_no_signal", False)),\n',
        new=b"        raw_segment_scores=raw_tuples,\n",
        anchor=f"{A}::test_a5_event_log_round_trip_preserves_flag",
    ))

    # (A6) Revert one migrated predicate to `!= 0.0` → D3 AST invariant fires.
    results.append(scenario(
        label="(A6) Revert one predicate to `!= 0.0`",
        target=RECONCILER,
        old=b"            and not claim.confidence_is_no_signal):\n",
        new=b"            and claim.confidence != 0.0):\n",
        anchor=f"{A6}::test_d3_reconciler_has_no_exact_equality_against_claim_confidence",
    ))

    # (A7) Revert a SessionSnapshot collection field to `list` → D5 AST invariant fires.
    results.append(scenario(
        label="(A7) Revert SessionSnapshot.recent_voice_confs to list",
        target=SESSION_STATE,
        old=b"    recent_voice_confs:     tuple          # Pre-P1 Bundle 5 MF8",
        new=b"    recent_voice_confs:     list           # Pre-P1 Bundle 5 MF8",
        anchor=f"{A7}::test_d5_snapshot_collection_fields_annotated_tuple",
    ))

    print()
    print(f"Summary: {sum(results)}/{len(results)} deliberate-regression scenarios passed.")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
