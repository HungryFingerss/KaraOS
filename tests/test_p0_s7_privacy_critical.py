"""tests/test_p0_s7_privacy_critical.py — P0.S7 D4 enumeration tripwire.

Four AST-based structural tests that enforce the privacy_critical marker
placement contract locked at Plan v1 §1.1-§1.3 + Plan v2 §1.

D4 §5.1 — `test_known_privacy_critical_classes_all_tagged`
D4 §5.2 — `test_known_privacy_critical_files_all_module_tagged`
D4 §5.3 — `test_known_privacy_critical_standalone_functions_all_tagged`
D4 §5.4 — `test_no_unexpected_privacy_critical_marker_outside_anchor_lists`
          (inverse drift detector; scope locked at Plan v2 §1
           `_INVERSE_WALK_PATHS`).

Spec: tests/p0_s7_privacy_critical_audit.md + _plan_v1.md + _plan_v2.md.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parent.parent


# ─────────────────────────────────────────────────────────────────────────
# Anchor lists (LOCKED at Plan v1 §1.1-§1.3 + Plan v2 §1)
# ─────────────────────────────────────────────────────────────────────────


# 4 classes in test_brain_agent.py with class-level @pytest.mark.privacy_critical
_KNOWN_PRIVACY_CRITICAL_CLASSES: tuple[tuple[str, str], ...] = (
    ("test_brain_agent.py", "TestPrivacyFilter"),
    ("test_brain_agent.py", "TestBrainDBQueryKnowledgeFor"),
    ("test_brain_agent.py", "TestPrivacyIsolationE2E"),
    ("test_brain_agent.py", "TestVisitorAlert"),
)


# 8 files with module-level `pytestmark = pytest.mark.privacy_critical`
_KNOWN_PRIVACY_CRITICAL_FILES: tuple[str, ...] = (
    "tests/test_p0_s4_privacy_level_invariants.py",
    "tests/test_p0_s7_phase2.py",
    "tests/test_p0_s7_phase3.py",
    "tests/test_p0_s7_db.py",
    "tests/test_p0_s7_5.py",
    "tests/test_p0_s7_1_observability.py",
    "tests/test_p0_s7_2_phase1.py",
    "tests/test_p0_s7_2_phase2.py",
)


# 30 standalone functions/methods (24 in test_pipeline.py + 3 method-level
# in test_brain_agent.py non-anchored classes + 3 in test_core_memory.py).
# Tuple shape: (file_path, parent_class_name_or_None, function_name).
_KNOWN_PRIVACY_CRITICAL_STANDALONE: tuple[tuple[str, str | None, str], ...] = (
    # ── test_pipeline.py (24 entries) ──────────────────────────────────────
    ("test_pipeline.py", None, "test_privacy_levels_exhaustive_and_frozen"),
    ("test_pipeline.py", None, "test_privacy_default_is_personal_fail_closed"),
    ("test_pipeline.py", None, "test_privacy_static_map_values_valid"),
    ("test_pipeline.py", None, "test_visibility_clause_best_friend_excludes_only_system_only"),
    ("test_pipeline.py", None, "test_visibility_clause_non_best_friend_sees_public_own_personal_not_household"),
    ("test_pipeline.py", None, "test_visibility_clause_no_best_friend_id_acts_as_non_privileged"),
    ("test_pipeline.py", None, "test_visibility_clause_never_permits_system_only"),
    ("test_pipeline.py", None, "test_visibility_clause_composes_cleanly_with_and"),
    ("test_pipeline.py", None, "test_visibility_clause_params_align_with_placeholders"),
    ("test_pipeline.py", None, "test_search_memory_description_covers_cross_person_recall"),
    ("test_pipeline.py", None, "test_cross_person_excerpts_disputed_best_friend_labeled_disputed"),
    ("test_pipeline.py", None, "test_build_cross_person_excerpts_renamed"),
    ("test_pipeline.py", None, "test_p0_s7_dc_cross_person_excerpts_enabled_flag_defaults_false"),
    ("test_pipeline.py", None, "test_p0_s7_dc_build_cross_person_excerpts_call_site_guarded_by_flag"),
    ("test_pipeline.py", None, "test_p0_s7_dc_build_room_block_section1_renders_disputed_identity"),
    ("test_pipeline.py", None, "test_p0_s7_dc_build_room_block_section1_renders_best_friend_role"),
    ("test_pipeline.py", None, "test_p0_s7_dc_brain_context_summary_room_field_repointed_to_active_sessions"),
    ("test_pipeline.py", None, "test_p0_s7_dc_no_room_context_prepending_when_flag_off"),
    ("test_pipeline.py", None, "test_s114_visitor_alert_dedup_updates_promoted_alerts"),
    ("test_pipeline.py", None, "test_s114_visitor_alert_dedup_skips_unrelated_alerts"),
    ("test_pipeline.py", None, "test_s116_query_knowledge_for_emits_privacy_audit_log"),
    ("test_pipeline.py", None, "test_s116_classify_privacy_level_logs_static_map_path"),
    ("test_pipeline.py", None, "test_s111_cross_person_excerpts_filter_by_session_boundary"),
    ("test_pipeline.py", None, "test_s111_cross_person_excerpts_render_addressee_and_age"),
    # ── test_brain_agent.py method-level (3 entries inside non-anchored classes) ──
    ("test_brain_agent.py", "TestExtractionAgent", "test_extract_system_prompt_emits_dual_attribute_for_safety_critical"),
    ("test_brain_agent.py", "TestContradictionAgent", "test_safety_critical_attribute_never_replaces"),
    ("test_brain_agent.py", "TestContradictionAgent", "test_safety_critical_various_mentioned_attributes_blocked"),
    # ── tests/test_core_memory.py (3 entries) ──────────────────────────────
    ("tests/test_core_memory.py", None, "test_get_core_memory_for_privacy_cross_person_blocked"),
    ("tests/test_core_memory.py", None, "test_get_core_memory_for_best_friend_sees_personal"),
    ("tests/test_core_memory.py", None, "test_get_core_memory_for_attribute_whitelist"),
)


# Plan v2 §1.1 locked scope for the inverse-drift walker.
# Paths NOT scanned (with documented rationale):
#   - dog-ai-dashboard/        Node.js — no Python tests possible
#   - node_modules/            third-party — not our drift surface
#   - .github/                 CI config — not test files
#   - bootstrap/               one-shot offline pipeline — tests under tests/
#   - tools/                   helper scripts — tests under tests/
_INVERSE_WALK_PATHS: tuple[str, ...] = (
    "test_pipeline.py",       # top-level mixed-purpose
    "test_brain_agent.py",    # top-level mixed-purpose
    "tests/",                 # all Python-side test files
)


# ─────────────────────────────────────────────────────────────────────────
# AST helpers
# ─────────────────────────────────────────────────────────────────────────


def _decorator_is_privacy_critical(dec: ast.expr) -> bool:
    """Detect ``@pytest.mark.privacy_critical`` decorator (Attribute or Call form)."""
    # Plain attribute access (no call): @pytest.mark.privacy_critical
    node = dec
    # If it's @pytest.mark.privacy_critical(...), strip the Call
    if isinstance(node, ast.Call):
        node = node.func
    if not isinstance(node, ast.Attribute):
        return False
    if node.attr != "privacy_critical":
        return False
    # node.value should be Attribute(value=Name('pytest'), attr='mark')
    inner = node.value
    if not isinstance(inner, ast.Attribute):
        return False
    if inner.attr != "mark":
        return False
    if not isinstance(inner.value, ast.Name):
        return False
    return inner.value.id == "pytest"


def _has_privacy_critical_decorator(decorators: list[ast.expr]) -> bool:
    return any(_decorator_is_privacy_critical(d) for d in decorators)


def _module_has_privacy_critical_pytestmark(tree: ast.Module) -> bool:
    """Detect ``pytestmark = pytest.mark.privacy_critical`` at module scope.

    Also accepts a list/tuple containing the mark when a file has multiple
    module-level marks.
    """
    for node in tree.body:
        # AnnAssign or Assign
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "pytestmark":
            value = node.value
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "pytestmark":
            value = node.value
        else:
            continue
        if value is None:
            continue
        # Single mark: pytestmark = pytest.mark.privacy_critical
        if _decorator_is_privacy_critical(value):
            return True
        # List/tuple of marks: pytestmark = [..., pytest.mark.privacy_critical, ...]
        if isinstance(value, (ast.List, ast.Tuple)):
            for elt in value.elts:
                if _decorator_is_privacy_critical(elt):
                    return True
    return False


def _parse(file_path: Path) -> ast.Module:
    return ast.parse(file_path.read_text(encoding="utf-8"))


def _find_class(tree: ast.Module, class_name: str) -> ast.ClassDef | None:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return node
    return None


def _find_function(tree: ast.Module, parent_class: str | None, fn_name: str) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    """Locate a function/async-function definition.

    If ``parent_class`` is None, search at module scope.
    Otherwise, search inside the named class body.
    """
    if parent_class is None:
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == fn_name:
                return node
        return None
    cls = _find_class(tree, parent_class)
    if cls is None:
        return None
    for node in cls.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == fn_name:
            return node
    return None


# ─────────────────────────────────────────────────────────────────────────
# §5.1 — Known privacy_critical classes all tagged
# ─────────────────────────────────────────────────────────────────────────


def test_known_privacy_critical_classes_all_tagged():
    """D4 §5.1 — every class in `_KNOWN_PRIVACY_CRITICAL_CLASSES` carries the
    class-level ``@pytest.mark.privacy_critical`` decorator. Drift detected
    at AST-collection time."""
    violations: list[tuple[str, str]] = []
    for file_path, class_name in _KNOWN_PRIVACY_CRITICAL_CLASSES:
        tree = _parse(_REPO_ROOT / file_path)
        cls = _find_class(tree, class_name)
        assert cls is not None, (
            f"D4 §5.1: class {class_name} not found in {file_path}. "
            f"Either the class was renamed (update anchor list) or removed "
            f"(remove from anchor list with rationale)."
        )
        if not _has_privacy_critical_decorator(cls.decorator_list):
            violations.append((file_path, class_name))
    assert not violations, (
        f"D4 §5.1 FAILED: classes in the privacy_critical anchor list are "
        f"missing the class-level @pytest.mark.privacy_critical decorator:\n"
        + "\n".join(f"  {f}::{cls}" for f, cls in violations)
        + "\n\nFix: add @pytest.mark.privacy_critical above each class OR "
        "remove the entry from _KNOWN_PRIVACY_CRITICAL_CLASSES with rationale."
    )


# ─────────────────────────────────────────────────────────────────────────
# §5.2 — Known privacy_critical files all module-tagged
# ─────────────────────────────────────────────────────────────────────────


def test_known_privacy_critical_files_all_module_tagged():
    """D4 §5.2 — every file in `_KNOWN_PRIVACY_CRITICAL_FILES` carries a
    module-level ``pytestmark = pytest.mark.privacy_critical`` binding (or
    a list/tuple containing the mark when the file declares multiple
    module-level marks)."""
    violations: list[str] = []
    for file_path in _KNOWN_PRIVACY_CRITICAL_FILES:
        path = _REPO_ROOT / file_path
        assert path.exists(), (
            f"D4 §5.2: anchor-list file {file_path} not found. Either the "
            f"file was renamed/moved (update anchor list) or removed."
        )
        tree = _parse(path)
        if not _module_has_privacy_critical_pytestmark(tree):
            violations.append(file_path)
    assert not violations, (
        f"D4 §5.2 FAILED: files in the privacy_critical anchor list are "
        f"missing module-level pytestmark:\n"
        + "\n".join(f"  {f}" for f in violations)
        + "\n\nFix: add `pytestmark = pytest.mark.privacy_critical` at file top "
        "OR include `pytest.mark.privacy_critical` in the pytestmark list."
    )


# ─────────────────────────────────────────────────────────────────────────
# §5.3 — Known privacy_critical standalone functions all tagged
# ─────────────────────────────────────────────────────────────────────────


def test_known_privacy_critical_standalone_functions_all_tagged():
    """D4 §5.3 — every (file, class_or_None, function) tuple in
    `_KNOWN_PRIVACY_CRITICAL_STANDALONE` carries a function-level
    ``@pytest.mark.privacy_critical`` decorator."""
    violations: list[tuple[str, str | None, str]] = []
    not_found: list[tuple[str, str | None, str]] = []
    for file_path, parent_class, fn_name in _KNOWN_PRIVACY_CRITICAL_STANDALONE:
        tree = _parse(_REPO_ROOT / file_path)
        fn = _find_function(tree, parent_class, fn_name)
        if fn is None:
            not_found.append((file_path, parent_class, fn_name))
            continue
        if not _has_privacy_critical_decorator(fn.decorator_list):
            violations.append((file_path, parent_class, fn_name))
    assert not not_found, (
        f"D4 §5.3 anchor-list integrity FAILED — functions not found in source:\n"
        + "\n".join(
            f"  {f}::{cls or '<module>'}::{fn}"
            for f, cls, fn in not_found
        )
        + "\n\nFix: either the function was renamed (update anchor list) or "
        "removed (remove from anchor list with rationale)."
    )
    assert not violations, (
        f"D4 §5.3 FAILED: functions in the privacy_critical anchor list are "
        f"missing the function-level @pytest.mark.privacy_critical decorator:\n"
        + "\n".join(
            f"  {f}::{cls or '<module>'}::{fn}"
            for f, cls, fn in violations
        )
        + "\n\nFix: add @pytest.mark.privacy_critical above each function "
        "OR remove the entry from _KNOWN_PRIVACY_CRITICAL_STANDALONE."
    )


# ─────────────────────────────────────────────────────────────────────────
# §5.4 — Inverse drift detector
# ─────────────────────────────────────────────────────────────────────────


def _iter_walk_files() -> list[Path]:
    files: list[Path] = []
    for entry in _INVERSE_WALK_PATHS:
        target = _REPO_ROOT / entry
        if target.is_file():
            files.append(target)
        elif target.is_dir():
            # Recurse — pick up every *.py under the directory
            files.extend(sorted(target.rglob("test_*.py")))
            files.extend(sorted(target.rglob("*_test.py")))
    return files


def _in_anchor_list(file_rel: str, parent_class: str | None, fn_name: str) -> bool:
    # Class-level anchor coverage
    if parent_class is not None:
        for f, cls in _KNOWN_PRIVACY_CRITICAL_CLASSES:
            if f == file_rel and cls == parent_class:
                return True  # method inherits class-level mark
    # Standalone-function anchor coverage
    for f, cls, fn in _KNOWN_PRIVACY_CRITICAL_STANDALONE:
        if f == file_rel and cls == parent_class and fn == fn_name:
            return True
    return False


def test_no_unexpected_privacy_critical_marker_outside_anchor_lists():
    """D4 §5.4 — inverse drift detector. AST-walks every test file under
    `_INVERSE_WALK_PATHS`. For each `@pytest.mark.privacy_critical` decorator
    found, verify the (file, class_or_None, function) is in one of the
    anchor lists §5.1/§5.2/§5.3 OR the file/class IS module-/class-tagged
    in §5.2/§5.1. Catches the 'developer tagged a non-privacy test by
    mistake / by copy-paste' class."""
    unexpected: list[tuple[str, str | None, str]] = []
    files_known_module_tagged: set[str] = set(_KNOWN_PRIVACY_CRITICAL_FILES)
    for path in _iter_walk_files():
        file_rel = str(path.relative_to(_REPO_ROOT)).replace("\\", "/")
        # Skip the inverse-walker test file itself (we DON'T mark our own tests)
        if file_rel == "tests/test_p0_s7_privacy_critical.py":
            continue
        # If file is module-tagged, all function-level + class-level marks
        # inside are accepted (the module-level pytestmark applies anyway).
        if file_rel in files_known_module_tagged:
            continue
        tree = _parse(path)
        # Walk module-level functions
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if _has_privacy_critical_decorator(node.decorator_list):
                    if not _in_anchor_list(file_rel, None, node.name):
                        unexpected.append((file_rel, None, node.name))
            elif isinstance(node, ast.ClassDef):
                class_tagged = _has_privacy_critical_decorator(node.decorator_list)
                # If class is in anchor list §5.1, all its methods are OK
                class_in_anchor = (file_rel, node.name) in _KNOWN_PRIVACY_CRITICAL_CLASSES
                if class_tagged and not class_in_anchor:
                    unexpected.append((file_rel, None, f"class {node.name}"))
                # Walk class methods
                for inner in node.body:
                    if isinstance(inner, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if _has_privacy_critical_decorator(inner.decorator_list):
                            # If class is in anchor list (class-level mark applies)
                            # then method-level marks inside are accepted as
                            # redundant-but-harmless documentation
                            if class_in_anchor:
                                continue
                            if not _in_anchor_list(file_rel, node.name, inner.name):
                                unexpected.append((file_rel, node.name, inner.name))
    assert not unexpected, (
        f"D4 §5.4 FAILED: unexpected @pytest.mark.privacy_critical marker(s) "
        f"outside the anchor lists:\n"
        + "\n".join(
            f"  {f}::{cls or '<module>'}::{fn}"
            for f, cls, fn in unexpected
        )
        + "\n\nFix: either (a) add to the appropriate anchor list in "
        "tests/test_p0_s7_privacy_critical.py if intentional, OR (b) remove "
        "the marker if accidental (privacy_critical is a structural CI "
        "discipline, not a generic 'this test is important' tag)."
    )


# ─────────────────────────────────────────────────────────────────────────
# D1 — pytest.ini marker registration
# ─────────────────────────────────────────────────────────────────────────


def test_d1_privacy_critical_marker_registered_in_pytest_ini():
    """D1 — `privacy_critical` marker is registered in `pytest.ini`.

    `--strict-markers` (used in fast.yml Step B) errors at collection if a
    referenced marker isn't registered. Without this assertion, accidental
    removal of the registration would surface ONLY at CI time; this test
    catches it at every local pytest run."""
    ini = (_REPO_ROOT / "pytest.ini").read_text(encoding="utf-8")
    assert "privacy_critical:" in ini, (
        "D1: `privacy_critical:` marker registration missing from pytest.ini. "
        "Add the marker line with docstring naming CI enforcement clause."
    )


def test_d1_privacy_critical_marker_docstring_names_spec_anchor():
    """D1 — `privacy_critical` marker registration in `pytest.ini`
    references the P0.S7 spec for grep-discoverability per Plan v1 §3.7."""
    ini = (_REPO_ROOT / "pytest.ini").read_text(encoding="utf-8")
    # The marker line should mention the spec file for future maintainers
    # grepping pytest.ini to find the discipline-anchor.
    privacy_line_idx = ini.find("privacy_critical:")
    assert privacy_line_idx != -1
    # Look at the privacy_critical block (next ~500 chars should include spec ref)
    window = ini[privacy_line_idx:privacy_line_idx + 800]
    assert "p0_s7_privacy_critical_plan_v1.md" in window, (
        "D1: privacy_critical marker docstring must reference the spec anchor "
        "tests/p0_s7_privacy_critical_plan_v1.md (Plan v1 §3.7 grep-discoverability)."
    )


# ─────────────────────────────────────────────────────────────────────────
# D3 — fast.yml dual-step CI integrity
# ─────────────────────────────────────────────────────────────────────────


def _fast_yml() -> str:
    return (_REPO_ROOT / ".github" / "workflows" / "fast.yml").read_text(encoding="utf-8")


def test_d3_fast_yml_privacy_critical_step_present():
    """D3 — fast.yml Step B (dedicated privacy_critical run) exists per
    Plan v1 §2 dual-step lock."""
    src = _fast_yml()
    assert "privacy_critical" in src, (
        "D3: fast.yml is missing the privacy_critical step. Per Plan v1 §2, "
        "Step B must run `pytest tests/ -m privacy_critical ...` as a "
        "dedicated CI signal."
    )


def test_d3_fast_yml_uses_strict_markers():
    """D3 — Step B uses `--strict-markers` to reject typos like
    `privacy_crit` at collection time (Plan v1 §2 dual-step contract)."""
    src = _fast_yml()
    assert "--strict-markers" in src, (
        "D3: fast.yml privacy_critical step must use `--strict-markers` to "
        "catch typo markers (e.g., `privacy_crit` instead of "
        "`privacy_critical`) at pytest collection time."
    )


def test_d3_fast_yml_fail_on_skip_grep_present():
    """D3 — Step B uses `-rs` to report skips + post-pytest grep on
    `^SKIPPED` + `exit 1` to treat skipped privacy tests as CI failures
    (Plan v1 §3 P3 lock — zero-dependency fail-on-skip mechanism)."""
    src = _fast_yml()
    assert "-rs" in src, "D3: fast.yml privacy_critical step must use `-rs` to surface skips"
    assert 'grep -q "^SKIPPED"' in src, (
        "D3: fast.yml privacy_critical step must post-grep for `^SKIPPED` "
        "lines and exit 1 on match (Plan v1 §3 P3 fail-on-skip lock)."
    )
    assert "exit 1" in src, (
        "D3: fast.yml privacy_critical step must `exit 1` when a privacy "
        "test was skipped (treating skip as failure)."
    )


def test_d3_fast_yml_step_a_excludes_privacy_critical():
    """D3 — Step A (default fast subset) excludes `privacy_critical` so
    tests don't double-run across steps (Plan v1 §2 dual-step contract)."""
    src = _fast_yml()
    assert "not privacy_critical" in src, (
        "D3: fast.yml Step A (default fast subset) must extend its `-m` "
        "clause with `and not privacy_critical` so privacy tests run ONLY "
        "in the dedicated Step B (Plan v1 §2 dual-step + each-test-runs-once "
        "guarantee)."
    )


# ─────────────────────────────────────────────────────────────────────────
# Cross-cutting — anchor lists wired consistently with Plan v2 §1
# ─────────────────────────────────────────────────────────────────────────


def test_inverse_walk_paths_locked_per_plan_v2():
    """Plan v2 §1.1 LOCK — `_INVERSE_WALK_PATHS` is exactly the 3-entry
    tuple covering Python-side test files. Adding a path requires a Plan
    v3 spec OR P0.S7.X follow-up (mirrors P0.S6 `_REGISTRY_ALLOWLIST`
    discipline). Catches accidental scope-creep / scope-shrinkage."""
    expected = ("test_pipeline.py", "test_brain_agent.py", "tests/")
    assert _INVERSE_WALK_PATHS == expected, (
        f"_INVERSE_WALK_PATHS drifted from Plan v2 §1.1 lock. "
        f"Expected {expected}; got {_INVERSE_WALK_PATHS}. "
        f"To extend the scope, update Plan v2 §1.1 first (add rationale comment "
        f"per `_REGISTRY_ALLOWLIST` discipline)."
    )
