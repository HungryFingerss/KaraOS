"""One-shot deliberate-regression harness for Pre-P1 Bundle 1.

For each scenario (a)-(h):
    1. Snapshot the production file's bytes.
    2. Apply the regression mutation (string substitution).
    3. Run the targeted anchor test via pytest.
    4. Assert the targeted anchor fails (regression confirmed).
    5. Restore the file from snapshot.
    6. Run the targeted test again to confirm restoration is clean.

Prints a one-line summary per scenario; non-zero exit if any scenario didn't
fail-on-mutation or didn't restore cleanly.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PYTEST_BIN = [sys.executable, "-m", "pytest", "-q", "--tb=line", "--no-header"]


def run_test(node_id: str) -> tuple[int, str]:
    """Run a pytest test ID. Returns (returncode, last-200-chars-of-output)."""
    r = subprocess.run(
        PYTEST_BIN + [f"tests/test_pre_p1_bundle1_docs_ci.py::{node_id}"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    tail = (r.stdout + r.stderr)[-300:].replace("\n", " | ")
    return r.returncode, tail


def scenario(label: str, surface: Path, old: bytes, new: bytes, anchor: str) -> bool:
    snapshot = surface.read_bytes()
    if old not in snapshot:
        print(f"  {label} SETUP-FAIL: old-string not found in {surface.name}")
        return False
    surface.write_bytes(snapshot.replace(old, new, 1))
    try:
        rc, _tail = run_test(anchor)
        fail_on_mutation = rc != 0
    finally:
        surface.write_bytes(snapshot)
    rc_restore, _ = run_test(anchor)
    restored_clean = rc_restore == 0
    status = "OK" if (fail_on_mutation and restored_clean) else "FAIL"
    print(
        f"  {label} {status}: fired-on-mutation={fail_on_mutation} | restored-clean={restored_clean}"
    )
    return fail_on_mutation and restored_clean


def scenario_file_delete(label: str, target: Path, anchor: str) -> bool:
    snapshot = target.read_bytes()
    target.unlink()
    try:
        rc, _ = run_test(anchor)
        fail_on_mutation = rc != 0
    finally:
        target.write_bytes(snapshot)
    rc_restore, _ = run_test(anchor)
    restored_clean = rc_restore == 0
    status = "OK" if (fail_on_mutation and restored_clean) else "FAIL"
    print(
        f"  {label} {status}: fired-on-mutation={fail_on_mutation} | restored-clean={restored_clean}"
    )
    return fail_on_mutation and restored_clean


def main() -> int:
    CLAUDE_MD = REPO_ROOT / "CLAUDE.md"
    EVERYTHING = REPO_ROOT / "everything_about_system.md"
    GITIGNORE = REPO_ROOT / ".gitignore"
    SETUP_MD = REPO_ROOT / "SETUP.md"
    DOCS_ARCH = REPO_ROOT / "docs" / "architecture"

    print("Deliberate-regression harness for Pre-P1 Bundle 1\n")
    results = []

    # (a) D1: re-add stale P1.P1 — No CI config line in CLAUDE.md.
    # A1 contract = ZERO occurrences of the literal phrase.
    results.append(
        scenario(
            label="(a) D1 re-add stale P1.P1",
            surface=CLAUDE_MD,
            old=b"- **P0.0 CI scaffold live**",
            new=b"- **P1.P1 \xe2\x80\x94 No CI config**: no `.github/workflows/` directory exists.\n- **P0.0 CI scaffold live**",
            anchor="test_a1_no_stale_p1_p1_no_ci_config_in_claude_md",
        )
    )

    # (b) D2: drop "Layer D cognitive runtime middleware" from CLAUDE.md.
    results.append(
        scenario(
            label="(b) D2 drop Layer D lead",
            surface=CLAUDE_MD,
            old=b"KaraOS is the Layer D cognitive runtime middleware for embodied AI",
            new=b"KaraOS is a cognitive runtime for embodied AI",
            anchor="test_a3_d2_layer_d_lead_sentence_verbatim",
        )
    )

    # (c) D3.a: delete chapter file CHAPTER_13.
    results.append(
        scenario_file_delete(
            label="(c) D3.a delete CHAPTER_13",
            target=DOCS_ARCH / "CHAPTER_13_observability_evolution_plans_pyannote.md",
            anchor="test_a6_d3a_19_chapter_files_present",
        )
    )

    # (d) D3.b: balloon thin redirect past 50 lines.
    results.append(
        scenario(
            label="(d) D3.b balloon thin redirect",
            surface=EVERYTHING,
            old=b"# Kara-OS Complete System Documentation \xe2\x80\x94 Redirect",
            new=b"# Kara-OS Complete System Documentation \xe2\x80\x94 Redirect\n" + (b"\nfiller line for ballooning\n" * 60),
            anchor="test_a8_d3b_thin_redirect_shape",
        )
    )

    # (e) D3.c: revert .gitignore comment to pre-Bundle-1 stale form.
    results.append(
        scenario(
            label="(e) D3.c stale .gitignore comment",
            surface=GITIGNORE,
            old=b"#   - everything_about_system.md     \xe2\x86\x90 thin redirect (chapter split landed Pre-P1",
            new=b"#   - everything_about_system.md     \xe2\x86\x90 canonical system documentation     (stale-revert Pre-P1",
            anchor="test_a9_d3c_gitignore_reflects_split",
        )
    )

    # (f) D3.c: revert SETUP.md line 71 to stale Part XXXI reference.
    results.append(
        scenario(
            label="(f) D3.c stale SETUP.md L71",
            surface=SETUP_MD,
            old=b"- Apply the pyannote dependency patches (see `docs/architecture/CHAPTER_13_observability_evolution_plans_pyannote.md` \xc2\xa7194-\xc2\xa7197",
            new=b"- Apply the pyannote dependency patches (see `everything_about_system.md` Part XXXI",
            anchor="test_a10_d3c_setup_md_chapter_redirects",
        )
    )

    # (g) D3.d: inject broken §-level reference in CLAUDE.md.
    # A11 contract = ZERO `everything_about_system.md §N` patterns.
    results.append(
        scenario(
            label="(g) D3.d broken \u00a7-level ref",
            surface=CLAUDE_MD,
            old=b"## Project Overview",
            new=b"<!-- regression: stale ref everything_about_system.md \xc2\xa7999 -->\n## Project Overview",
            anchor="test_a11_d3d_no_stale_section_refs_in_claude_md",
        )
    )

    # (h) Plan v2 §1.6 LOAD-BEARING: duplicate §200 across two chapters.
    # A14 contract = every §NN in 1-340 appears in EXACTLY ONE chapter.
    ch14 = DOCS_ARCH / "CHAPTER_14_voice_vision_independence_pure_graph_classifier.md"
    snapshot_ch14 = ch14.read_bytes()
    # Inject a duplicate `## 200. ` header into CHAPTER_15 (where §200 doesn't live).
    ch15 = DOCS_ARCH / "CHAPTER_15_external_benchmarks_multilayer_architecture.md"
    snapshot_ch15 = ch15.read_bytes()
    # Append a duplicate-§200 entry to CHAPTER_15.
    ch15.write_bytes(snapshot_ch15 + b"\n## 200. Duplicate Regression Probe\nDuplicate entry for regression (h).\n")
    try:
        rc, _ = run_test("test_a14_section_stability_invariant[200]")
        h_fail = rc != 0
    finally:
        ch15.write_bytes(snapshot_ch15)
    rc_restore, _ = run_test("test_a14_section_stability_invariant[200]")
    h_restore = rc_restore == 0
    status = "OK" if (h_fail and h_restore) else "FAIL"
    print(
        f"  (h) A14 duplicate \u00a7200 {status}: fired-on-mutation={h_fail} | restored-clean={h_restore}"
    )
    results.append(h_fail and h_restore)

    print()
    print(f"Summary: {sum(results)}/{len(results)} scenarios passed both fail-on-mutation + restore.")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
