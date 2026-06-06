"""
P0.4 silent-except structural invariant (DLL-safe) + #123 falsy-return extension.

Every broad except (`Exception`/`BaseException`/bare) in production code whose body is a
SILENT SWALLOW must carry a co-located triage annotation. Two swallow shapes are detected —
#123 extended the original pass-only invariant to the falsy-return class that hid the
Canary-#3 ECAPA embed bug:
  - pass-only:    body is exactly `[ast.Pass]`
  - falsy-return: body's LAST statement returns a falsy value (bare `return` / None / "" /
                  [] / {} / () / 0 / False / empty set()/dict()/list()/tuple()/frozenset())
                  with NO logging call and NO raise anywhere in the body.

A handler that LOGS the failure (print / logger.{warning,error,info,debug,exception,
critical,warn}) before returning is NOT a silent swallow — logging IS the triage.

Permitted annotations (PERMITTED_ANNOTATIONS), found anywhere in the handler's full span
(except_lineno-1 through the last body line — #123 D2b, safe because every detected shape
is a SHORT handler; see _has_annotation_comment caveat):
  # RACE:      — expected concurrency race, swallowing is intentional (Bucket B)
  # CLEANUP:   — benign best-effort teardown, failure is irrelevant (Bucket A)
  # OPTIONAL:  — genuinely optional operation, failure is acceptable (Bucket A)

D1.0 (#123): BOTH the production scan (`_scan_file`) and the synthetic self-tests
(`_detect_in_source`) route through the single `_handler_is_violation` / `_violations_in_source`
decision, so a self-test can never validate a different detector than production scans (the
B1 `_build_and_insert` / #129 C2 single-source discipline; an INV test pins the route-through).

Scans `core/**/*.py` (recursive — #123 D2) + 7 root files, allowlists `core/_minifasnet`.
DOES NOT IMPORT pipeline or any production module. Reads source via ast.parse(). No Windows
DLL side-effects.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

import ast
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

SCANNED_DIRS: list[Path] = [REPO_ROOT / "core", REPO_ROOT / "runtime"]  # runtime/ = P1.A1 SP-4 engine package

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


# #123 D1 — falsy-return swallow shape (the Canary-#3 embed-bug class).
_LOG_METHOD_NAMES: frozenset[str] = frozenset(
    {"warning", "error", "info", "debug", "exception", "critical", "warn"}
)
_LOG_FUNC_NAMES: frozenset[str] = frozenset({"print", "log"})


def _is_falsy_return(node: ast.Return) -> bool:
    """True when a Return returns a statically-falsy value: bare `return`, None, "", 0,
    0.0, False, an empty [] / {} / () literal, or an empty
    set()/dict()/list()/tuple()/frozenset() constructor call."""
    v = node.value
    if v is None:                        # bare `return`
        return True
    if isinstance(v, ast.Constant):      # None / "" / 0 / 0.0 / False / b""
        return not v.value
    if isinstance(v, ast.List) and not v.elts:
        return True
    if isinstance(v, ast.Tuple) and not v.elts:
        return True
    if isinstance(v, ast.Dict) and not v.keys:
        return True
    if (isinstance(v, ast.Call) and isinstance(v.func, ast.Name)
            and v.func.id in ("set", "dict", "list", "tuple", "frozenset")
            and not v.args and not v.keywords):
        return True
    return False


def _body_has_logging_or_raise(body: list) -> bool:
    """True if the handler body logs the failure (print / log / logger.<level>) OR raises
    anywhere — either makes the swallow non-silent, so it is NOT a violation. Walked
    recursively so a log/raise nested in an `if` inside the handler still counts."""
    for stmt in body:
        for n in ast.walk(stmt):
            if isinstance(n, ast.Raise):
                return True
            if isinstance(n, ast.Call):
                f = n.func
                if isinstance(f, ast.Name) and f.id in _LOG_FUNC_NAMES:
                    return True
                if isinstance(f, ast.Attribute) and f.attr in _LOG_METHOD_NAMES:
                    return True
    return False


def _is_silent_falsy_return_body(body: list) -> bool:
    """#123 D1 — True when the body's LAST statement is a falsy Return AND the body contains
    no logging call and no raise (a silent falsy-return swallow — the Canary-#3 ECAPA
    embed-bug class the pass-only detector was blind to). NOTE: scoped to except-handler
    bodies by the caller; guard-clause / function-body falsy returns are never reached
    because _handler_is_violation only ever passes `node.body` of an ast.ExceptHandler."""
    if not body:
        return False
    last = body[-1]
    if not (isinstance(last, ast.Return) and _is_falsy_return(last)):
        return False
    return not _body_has_logging_or_raise(body)


def _has_annotation_comment(source: str, except_lineno: int, end_lineno: int) -> bool:
    """
    Return True if any line in the handler's FULL SPAN carries a PERMITTED_ANNOTATIONS marker.

    #123 D2b — the window scans every 0-based index from `except_lineno - 2` (the line
    immediately above the except keyword) through `end_lineno - 1` (the last body line),
    inclusive — not just the original 3-line set {except_lineno-2, except_lineno-1,
    end_lineno-1}. Required by D2: otherwise it false-positives on the `producer.py`
    `# CLEANUP:` shape, whose annotation sits between the `except:` line (carrying a
    `# pragma: no cover`) and the `pass`, outside the 3-line set.

    CAVEAT (auditor Q2 scoping) — the full-span scan is safe ONLY because every #123-detected
    shape is a SHORT handler (pass-only / single-falsy-return), so an annotation anywhere in
    the span is unambiguously about THIS swallow. If a future body-shape adds LONG handlers,
    the full-span scan could FALSE-NEGATIVE (an unrelated annotation deep in a long handler
    would clear a real violation). Do NOT extend the detector to long-handler shapes without
    re-scoping this window.
    """
    lines = source.splitlines()
    start_idx = except_lineno - 2   # line immediately above the except keyword (0-based)
    end_idx = end_lineno - 1        # last line of the handler body (0-based)
    for idx in range(start_idx, end_idx + 1):
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


# ── #123 D1.0 — the single shared decision (production scan + self-tests both route here) ──

def _handler_is_violation(node: ast.ExceptHandler, source: str) -> bool:
    """Single source of truth for the silent-except decision — BOTH _scan_file (production
    scan) and _detect_in_source (synthetic self-tests) go through this, so a self-test can
    never validate a DIFFERENT detector than the one scanning production (the B1
    _build_and_insert / #129 C2 single-source discipline; the Canary-#3 conftest-stub vacuity
    class). A broad except whose body is a silent pass-only OR silent falsy-return swallow,
    with no permitted annotation in the handler's full span, is a violation."""
    return (
        _is_broad_except_handler(node)
        and (_is_silent_pass_only_body(node.body)
             or _is_silent_falsy_return_body(node.body))
        and not _has_annotation_comment(source, node.lineno, node.end_lineno)
    )


def _violations_in_source(source: str, label: str) -> list[str]:
    """The ONE ast.walk + decide + violation-string build. No walk/decide logic lives outside
    this path — _scan_file (label=rel_str) and _detect_in_source (label='<test>') both
    delegate here so the two entry points cannot re-fork (#123 D1.0)."""
    tree = ast.parse(source, filename=label)
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and _handler_is_violation(node, source):
            violations.append(
                f"  {label}:{node.lineno} — unannotated broad silent except"
            )
    return violations


def _collect_production_files() -> list[tuple[Path, str]]:
    """Return (file_path, rel_str) pairs for every production file to scan."""
    results: list[tuple[Path, str]] = []
    for d in SCANNED_DIRS:
        # #123 D2 — recursive rglob closes the nested-core/ blind spot
        # (core/vision/, core/event_log/, core/*_migrations.py, …). The
        # core/_minifasnet boundary-correct allowlist still skips the vendored fork.
        for fp in sorted(d.rglob("*.py")):
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
    # #123 D1.0 — delegate to the shared decision; no walk/decide logic here.
    return _violations_in_source(source, rel_str)


# ── main invariant ─────────────────────────────────────────────────────────────

def test_no_unannotated_silent_excepts_in_production_code():
    """
    Whole-file scan. Every broad silent except must carry a triage annotation.
    If this fails, manually add a triage annotation (# RACE:, # CLEANUP:, or
    # OPTIONAL:) to each offending site named in the failure output, then triage.
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
    """Run detector on raw source string — no file I/O, exercises real logic.

    #123 D1.0 — delegates to the SAME _violations_in_source the production scan uses, so a
    self-test can never validate a different detector than _scan_file (route-through pinned
    by test_both_entry_points_route_through_shared_helper)."""
    src = textwrap.dedent(src).strip()
    return _violations_in_source(src, "<test>")


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

    # ── #123 falsy-return CAUGHT cases (D1 + D4) ─────────────────────────────
    # 12. except Exception: return None — no log, no annotation
    ("""
    def f():
        try:
            x()
        except Exception:
            return None
    """, 1),
    # 13. bare except: return (bare falsy return)
    ("""
    def f():
        try:
            x()
        except:
            return
    """, 1),
    # 14. return [] — empty list
    ("""
    def f():
        try:
            x()
        except Exception:
            return []
    """, 1),
    # 15. return {} — empty dict
    ("""
    def f():
        try:
            x()
        except Exception:
            return {}
    """, 1),
    # 16. return False
    ("""
    def f():
        try:
            x()
        except Exception:
            return False
    """, 1),
    # 17. return "" — empty string
    ("""
    def f():
        try:
            x()
        except Exception:
            return ""
    """, 1),
    # 18. return set() — empty constructor
    ("""
    def f():
        try:
            x()
        except Exception:
            return set()
    """, 1),

    # ── #123 falsy-return ALLOWED (not caught) cases ─────────────────────────
    # 19. logged-then-return None — logging IS the triage, not silent
    ("""
    def f():
        try:
            x()
        except Exception as e:
            print(f"failed: {e!r}")
            return None
    """, 0),
    # 20. annotated falsy-return — # OPTIONAL: between except and return (D2b span)
    ("""
    def f():
        try:
            x()
        except Exception:
            # OPTIONAL: genuinely optional
            return None
    """, 0),
    # 21. narrow except falsy-return — not broad, never caught
    ("""
    def f():
        try:
            x()
        except OSError:
            return None
    """, 0),
    # 22. truthy return — not a falsy swallow
    ("""
    def f():
        try:
            x()
        except Exception:
            return True
    """, 0),
    # 23. raise in handler body — propagates, not silent (even w/ trailing falsy return)
    ("""
    def f():
        try:
            x()
        except Exception as e:
            if e:
                raise
            return None
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


# ── #123 D4: guard-clause scoping, D2b gap, D1.0 route-through ───────────────────

def test_guard_clause_falsy_return_not_flagged_only_except_is():
    """PI-2 (#123) — a falsy `return` in a GUARD CLAUSE (function body, outside any except)
    is NOT a violation; only the `except: return None` is. Mirrors heavy_worker's :676
    (`return []` empty-audio guard) + :679 (`return None` pipeline-None guard) vs the :687
    except. Pins the except-scoping so a future refactor can't over-flag legitimate guard
    returns."""
    src = """
    def f(x):
        if x is None:
            return None          # guard clause — NOT an except body
        if x < 0:
            return []            # guard clause — NOT an except body
        try:
            y = compute(x)
        except Exception:
            return None          # THE violation
        return y
    """
    violations = _detect_in_source(src)
    assert len(violations) == 1, (
        f"only the except: return None must be flagged, not the two guard clauses; "
        f"got {violations}"
    )


def test_d2b_annotation_between_except_and_body_clears_violation():
    """#123 D2b — an annotation BETWEEN the except: line and the swallow body (outside the
    original 3-line set) clears the violation under the full-span window. This is the
    producer.py shape: `# CLEANUP:` on its own line between `except:  # pragma` and `pass`.
    Under the OLD 3-line window {except-2, except-1, end-1} this annotation was missed."""
    src = """
    def f():
        try:
            x()
        except Exception:  # pragma: no cover
            # CLEANUP: best-effort, failure irrelevant
            pass
    """
    assert _detect_in_source(src) == [], (
        "full-span window (D2b) must find the annotation between except: and the body"
    )


def test_both_entry_points_route_through_shared_helper():
    """#123 D1.0 — BOTH _scan_file and _detect_in_source route through the single
    _violations_in_source / _handler_is_violation decision, so a self-test can never validate
    a different detector than the production scan (the B1 _build_and_insert / #129 C2
    discipline). Source-check: neither entry point has its own ast.walk/decide loop; both
    delegate; the shared path is the only caller of _handler_is_violation."""
    import inspect
    for name, fn in (("_scan_file", _scan_file), ("_detect_in_source", _detect_in_source)):
        src = inspect.getsource(fn)
        assert "_violations_in_source(" in src, (
            f"{name} must delegate to _violations_in_source (D1.0 single-source discipline)"
        )
        assert "ast.walk(" not in src, (
            f"{name} must NOT carry its own ast.walk loop — that re-forks the detector"
        )
    viol_src = inspect.getsource(_violations_in_source)
    assert "_handler_is_violation(" in viol_src, (
        "_violations_in_source must invoke the shared _handler_is_violation decision"
    )
