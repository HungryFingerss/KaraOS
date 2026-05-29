"""
P0.4 Batch 0 — broad-silent-except structural invariant (DLL-safe).

Every `except (Exception|BaseException|bare): pass` in production code MUST
carry a co-located triage annotation on one of the three candidate lines:
  - the pass / last-body line  (end_lineno - 1, 0-based)
  - the except: line itself    (except_lineno - 1, 0-based)
  - the line immediately above (except_lineno - 2, 0-based)

Permitted annotations (PERMITTED_ANNOTATIONS):
  # RACE:      — expected concurrency race, swallowing is intentional (Bucket B)
  # CLEANUP:   — benign best-effort teardown, failure is irrelevant (Bucket A)
  # OPTIONAL:  — genuinely optional operation, failure is acceptable (Bucket A)

DOES NOT IMPORT pipeline or any production module.
Reads source files via ast.parse(). No Windows DLL side-effects.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

import ast
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

SCANNED_DIRS: list[Path] = [REPO_ROOT / "core"]

SCANNED_ROOT_FILES: list[str] = [
    "pipeline.py",
    "enroll.py",
    "delete_person.py",
    "person_lifecycle.py",
    "audit_person.py",
    "repair_gallery.py",
    "sim_runner.py",
]

# Paths (relative to REPO_ROOT, forward-slash) whose broad-silent excepts are
# intentionally benign and pre-approved. Boundary-correct: uses trailing-slash
# prefix check so 'core/_minifasnet_helper.py' is NOT covered by 'core/_minifasnet'.
ALLOWLIST_PATHS: frozenset[str] = frozenset({"core/_minifasnet"})

PERMITTED_ANNOTATIONS: tuple[str, ...] = (
    "# RACE:",
    "# CLEANUP:",
    "# OPTIONAL:",
)


# ── detectors ─────────────────────────────────────────────────────────────────

def _is_broad_except_handler(node: ast.ExceptHandler) -> bool:
    """True for bare except, except Exception, or except BaseException."""
    if node.type is None:
        return True
    if isinstance(node.type, ast.Name) and node.type.id in ("Exception", "BaseException"):
        return True
    if isinstance(node.type, ast.Attribute) and node.type.attr in ("Exception", "BaseException"):
        return True
    return False


def _is_silent_pass_only_body(body: list) -> bool:
    """True when handler body is exactly one Pass statement."""
    return len(body) == 1 and isinstance(body[0], ast.Pass)


def _has_annotation_comment(source: str, except_lineno: int, end_lineno: int) -> bool:
    """
    Return True if any candidate line carries a PERMITTED_ANNOTATIONS marker.

    Candidate indices (0-based):
      end_lineno - 1   : pass line (or last line of handler body)
      except_lineno - 1: the 'except:' line itself
      except_lineno - 2: the line immediately above the except keyword
    """
    lines = source.splitlines()
    candidate_indices = {end_lineno - 1, except_lineno - 1, except_lineno - 2}
    for idx in candidate_indices:
        if idx < 0 or idx >= len(lines):
            continue
        line_text = lines[idx]
        for ann in PERMITTED_ANNOTATIONS:
            if ann in line_text:
                return True
    return False


def _is_in_allowlist(rel_str: str) -> bool:
    """
    True if rel_str equals or is a child of an allowlisted path.

    Boundary-correct check prevents prefix collision:
      'core/_minifasnet' does NOT match 'core/_minifasnet_helper.py'
      because '_minifasnet_helper.py' does not start with '_minifasnet/'
    """
    for allow in ALLOWLIST_PATHS:
        if rel_str == allow or rel_str.startswith(allow + "/"):
            return True
    return False


def _collect_production_files() -> list[tuple[Path, str]]:
    """Return (file_path, rel_str) pairs for every production file to scan."""
    results: list[tuple[Path, str]] = []
    for d in SCANNED_DIRS:
        for fp in sorted(d.glob("*.py")):
            rel_str = fp.relative_to(REPO_ROOT).as_posix()
            if not _is_in_allowlist(rel_str):
                results.append((fp, rel_str))
    for name in SCANNED_ROOT_FILES:
        fp = REPO_ROOT / name
        if fp.exists():
            results.append((fp, name))
    return results


def _scan_file(file_path: Path, *, rel_str: str | None = None) -> list[str]:
    """
    Return human-readable violation strings. Empty list = no violations.

    rel_str is injectable: tests can pass a synthetic path string so the real
    allowlist + detection code is exercised without touching the filesystem.
    """
    if rel_str is None:
        rel_str = file_path.relative_to(REPO_ROOT).as_posix()

    if _is_in_allowlist(rel_str):
        return []

    source = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=rel_str)

    violations: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        if not _is_broad_except_handler(node):
            continue
        if not _is_silent_pass_only_body(node.body):
            continue
        if _has_annotation_comment(source, node.lineno, node.end_lineno):
            continue
        violations.append(
            f"  {rel_str}:{node.lineno} — unannotated broad silent except"
        )
    return violations


# ── main invariant ─────────────────────────────────────────────────────────────

def test_no_unannotated_silent_excepts_in_production_code():
    """
    Whole-file scan. Every broad silent except must carry a triage annotation.
    If this fails, run:  python tools/bulk_annotate_p04.py
    That adds TODO-P0.4 markers so this test passes; triage each site afterward.
    """
    all_violations: list[str] = []
    for fp, rel_str in _collect_production_files():
        all_violations.extend(_scan_file(fp, rel_str=rel_str))

    assert not all_violations, (
        f"{len(all_violations)} unannotated broad silent except(s) found.\n"
        + "\n".join(all_violations)
        + "\n\nAnnotate each site with # RACE:, # CLEANUP:, or # OPTIONAL: per the P0.4 spec,\n"
        "or remove the swallow and add proper error handling."
    )


# ── detector self-tests ────────────────────────────────────────────────────────

def _detect_in_source(src: str) -> list[str]:
    """Run detector on raw source string — no file I/O, exercises real logic."""
    src = textwrap.dedent(src).strip()
    tree = ast.parse(src)
    violations: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        if not _is_broad_except_handler(node):
            continue
        if not _is_silent_pass_only_body(node.body):
            continue
        if _has_annotation_comment(src, node.lineno, node.end_lineno):
            continue
        violations.append(f"<test>:{node.lineno}")
    return violations


@pytest.mark.parametrize("src,expected_count", [
    # ── CAUGHT: must produce violations ──────────────────────────────────────
    # 1. except Exception: pass — no annotation
    ("""
    def f():
        try:
            x()
        except Exception:
            pass
    """, 1),
    # 2. except BaseException: pass — no annotation
    ("""
    def f():
        try:
            x()
        except BaseException:
            pass
    """, 1),
    # 3. bare except: pass — no annotation
    ("""
    def f():
        try:
            x()
        except:
            pass
    """, 1),
    # 4. Two broad silent excepts — both caught
    ("""
    def f():
        try:
            a()
        except Exception:
            pass
        try:
            b()
        except Exception:
            pass
    """, 2),

    # ── ALLOWED: annotation present, must produce zero violations ─────────────
    # 5. TODO-P0.4 on the pass line — transitional marker removed in Batch 7, must now be CAUGHT
    ("""
    def f():
        try:
            x()
        except Exception:
            pass  # TODO-P0.4: triage
    """, 1),
    # 6. TODO-P0.4 on the except: line — must now be CAUGHT
    ("""
    def f():
        try:
            x()
        except Exception:  # TODO-P0.4: triage
            pass
    """, 1),
    # 7. TODO-P0.4 on the line immediately above — must now be CAUGHT
    ("""
    def f():
        try:
            x()
        # TODO-P0.4: triage
        except Exception:
            pass
    """, 1),
    # 8. Narrow except — not broad, never caught
    ("""
    def f():
        try:
            x()
        except OSError:
            pass
    """, 0),
    # 9. RACE annotation on pass line
    ("""
    def f():
        try:
            x()
        except Exception:
            pass  # RACE: file may vanish between check and open
    """, 0),
    # 10. CLEANUP annotation on pass line
    ("""
    def f():
        try:
            x()
        except Exception:
            pass  # CLEANUP: best-effort teardown, failure irrelevant
    """, 0),
    # 11. Non-pass body — not silent, not caught
    ("""
    def f():
        try:
            x()
        except Exception as e:
            logger.warning(e)
    """, 0),
])
def test_detector_against_synthetic_sources(src, expected_count):
    violations = _detect_in_source(src)
    assert len(violations) == expected_count, (
        f"Expected {expected_count} violation(s), got {len(violations)}.\n"
        f"Violations: {violations}\n"
        f"Source:\n{textwrap.dedent(src)}"
    )


# ── allowlist boundary tests ───────────────────────────────────────────────────

def test_allowlist_matches_exact_path():
    """Files inside an allowlisted directory must be skipped."""
    assert _is_in_allowlist("core/_minifasnet/model.py") is True
    assert _is_in_allowlist("core/_minifasnet/__init__.py") is True


def test_allowlist_does_not_match_prefix_collisions():
    """
    'core/_minifasnet' must NOT cover 'core/_minifasnet_helper.py'.
    A bare startswith without trailing '/' would create a false skip.
    """
    assert _is_in_allowlist("core/_minifasnet_helper.py") is False
    assert _is_in_allowlist("core/_minifasnet_v2.py") is False
