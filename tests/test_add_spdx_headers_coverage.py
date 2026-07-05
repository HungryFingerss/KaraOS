# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors
"""100% line coverage for tools/add_spdx_headers.py — the SPDX header applier.

Part of the coverage-to-100 campaign. The module is a filesystem tool driven by
the module-level REPO_ROOT constant; every test monkeypatches REPO_ROOT onto a
pytest tmp_path so the real repo is never touched. External boundary (the tree)
is a temp fixture; nothing else is mocked. The one unreachable-via-real-ast
defensive branch (end_lineno is None) is exercised by monkeypatching ast.parse
to return a hand-built node, so no production pragma is needed.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

# ── side-load tools/add_spdx_headers.py (tools/ is a script dir, not a package) ──
_REPO_ROOT = Path(__file__).resolve().parent.parent
_MODULE_PATH = _REPO_ROOT / "tools" / "add_spdx_headers.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("add_spdx_headers_cli", _MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["add_spdx_headers_cli"] = module
    spec.loader.exec_module(module)  # runs lines 33-57 (imports + constants)
    return module


mod = _load_module()
L = mod.SPDX_LICENSE_LINE
C = mod.SPDX_COPYRIGHT_LINE


# ── helpers ──────────────────────────────────────────────────────────────────
def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # newline="\n" so Windows doesn't translate \n -> \r\n (matches the tool's writes).
    path.write_text(text, encoding="utf-8", newline="\n")


def _pyfile(*, headered: bool, has_doc: bool = True) -> str:
    if headered:
        if has_doc:
            return f'"""Doc."""\n\n{L}\n{C}\n\nimport os\n'
        return f'{L}\n{C}\n\nimport os\n'
    return '"""Doc."""\n\nimport os\n' if has_doc else "import os\n"


def _ymlfile(*, headered: bool) -> str:
    return f'{L}\n{C}\n\nname: CI\n' if headered else "name: CI\n"


def _build_repo(
    root: Path,
    *,
    with_bootstrap: bool = True,
    headered: bool = False,
    gitignore_whitelisted: bool = False,
    entry_points: tuple[str, ...] = ("pipeline.py", "enroll.py"),
) -> None:
    """Build a full in-scope tree. entry_points present => is_file True branch;
    the two names left out (delete_person.py / audit_person.py) => is_file False."""
    _write(root / "core" / "foo.py", _pyfile(headered=headered, has_doc=True))
    _write(root / "core" / "sub" / "bar.py", _pyfile(headered=headered, has_doc=False))
    _write(root / "core" / "_minifasnet" / "model.py", "x = 1\n")  # excluded (line 68 F)
    _write(root / "core" / "_florence2" / "flor.py", "y = 2\n")  # excluded (line 68 F)
    for name in entry_points:
        _write(root / name, _pyfile(headered=headered, has_doc=True))
    _write(root / "tools" / "helper.py", _pyfile(headered=headered, has_doc=True))
    (root / "tools" / "dirmatch.py").mkdir(parents=True, exist_ok=True)  # dir matches *.py -> is_file F
    if with_bootstrap:
        _write(root / "bootstrap" / "classifier" / "hand.py", _pyfile(headered=headered))
    _write(root / "tests" / "test_x.py", _pyfile(headered=headered, has_doc=True))
    _write(root / "tests" / "sub" / "test_y.py", _pyfile(headered=headered, has_doc=False))
    _write(root / ".github" / "workflows" / "fast.yml", _ymlfile(headered=headered))
    _write(root / ".github" / "workflows" / "slow.yml", _ymlfile(headered=headered))
    gi = "*.md\nvenv/\n"
    if gitignore_whitelisted:
        gi += "\n".join(mod.GITIGNORE_WHITELIST_LINES) + "\n"
    _write(root / ".gitignore", gi)


# ══════════════════════════════════════════════════════════════════════════════
# collect_in_scope / is_excluded / collect_excluded
# ══════════════════════════════════════════════════════════════════════════════
def test_collect_in_scope_full_tree(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    _build_repo(tmp_path)  # entry_points defaults => pipeline+enroll present, other 2 absent
    rels = {p.relative_to(tmp_path).as_posix() for p in mod.collect_in_scope()}
    # normal core files present; vendored dirs filtered (line 68 both sub-conditions)
    assert "core/foo.py" in rels and "core/sub/bar.py" in rels
    assert "core/_minifasnet/model.py" not in rels
    assert "core/_florence2/flor.py" not in rels
    # entry points: present (is_file True) vs absent (is_file False)
    assert "pipeline.py" in rels and "enroll.py" in rels
    assert "delete_person.py" not in rels and "audit_person.py" not in rels
    # tools file included, dir-matching-*.py excluded (line 78 is_file both sides)
    assert "tools/helper.py" in rels and "tools/dirmatch.py" not in rels
    # bootstrap exists branch (line 82 True -> 83)
    assert "bootstrap/classifier/hand.py" in rels
    assert "tests/test_x.py" in rels and "tests/sub/test_y.py" in rels
    assert ".github/workflows/fast.yml" in rels and ".github/workflows/slow.yml" in rels


def test_collect_in_scope_without_bootstrap(tmp_path, monkeypatch):
    """boot.exists() False branch (line 82 False -> skip 83)."""
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    _build_repo(tmp_path, with_bootstrap=False)
    rels = {p.relative_to(tmp_path).as_posix() for p in mod.collect_in_scope()}
    assert not any(r.startswith("bootstrap/") for r in rels)
    assert "core/foo.py" in rels  # rest of the collection still works


def test_is_excluded_true_and_false(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    minif = tmp_path / "core" / "_minifasnet" / "a.py"
    flor = tmp_path / "core" / "_florence2" / "b.py"
    normal = tmp_path / "core" / "normal.py"
    for p in (minif, flor, normal):
        _write(p, "z = 0\n")
    assert mod.is_excluded(minif) is True
    assert mod.is_excluded(flor) is True
    assert mod.is_excluded(normal) is False


def test_collect_excluded_returns_vendored(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    _write(tmp_path / "core" / "_minifasnet" / "model.py", "x = 1\n")
    _write(tmp_path / "core" / "_florence2" / "flor.py", "y = 2\n")
    _write(tmp_path / "core" / "normal.py", "z = 0\n")  # is_excluded False (line 103 F)
    excluded = {p.relative_to(tmp_path).as_posix() for p in mod.collect_excluded()}
    assert excluded == {"core/_minifasnet/model.py", "core/_florence2/flor.py"}


# ══════════════════════════════════════════════════════════════════════════════
# has_spdx_header
# ══════════════════════════════════════════════════════════════════════════════
def test_has_spdx_header_python_docstring_present():
    # docstring_end not None (line 124 False -> 127); header found -> True
    assert mod.has_spdx_header(_pyfile(headered=True, has_doc=True), is_python=True) is True


def test_has_spdx_header_python_docstring_absent():
    assert mod.has_spdx_header(_pyfile(headered=False, has_doc=True), is_python=True) is False


def test_has_spdx_header_python_no_docstring_present():
    # docstring_end None (line 124 True -> 125); header at top -> True
    assert mod.has_spdx_header(_pyfile(headered=True, has_doc=False), is_python=True) is True


def test_has_spdx_header_python_no_docstring_absent():
    assert mod.has_spdx_header(_pyfile(headered=False, has_doc=False), is_python=True) is False


def test_has_spdx_header_yaml_present():
    # is_python False -> line 129
    assert mod.has_spdx_header(_ymlfile(headered=True), is_python=False) is True


def test_has_spdx_header_yaml_absent():
    assert mod.has_spdx_header(_ymlfile(headered=False), is_python=False) is False


# ══════════════════════════════════════════════════════════════════════════════
# find_python_docstring_end
# ══════════════════════════════════════════════════════════════════════════════
def test_find_docstring_end_with_docstring():
    # returns the 1-based end line of the docstring (line 148)
    assert mod.find_python_docstring_end('"""doc\nline2"""\nimport os\n') == 2


def test_find_docstring_end_syntax_error():
    # ast.parse raises SyntaxError -> line 139
    assert mod.find_python_docstring_end("def f(:\n") is None


def test_find_docstring_end_empty_body():
    # no statements -> line 142
    assert mod.find_python_docstring_end("# only a comment\n") is None
    assert mod.find_python_docstring_end("") is None


def test_find_docstring_end_first_not_docstring():
    # first stmt is an import, not a str Constant Expr -> line 149
    assert mod.find_python_docstring_end("import os\n") is None


def test_find_docstring_end_end_lineno_none(monkeypatch):
    """Defensive line 147: end_lineno is None. Real ast always sets end_lineno,
    so we monkeypatch ast.parse to return a hand-built node with end_lineno=None."""

    def fake_parse(_content):
        const = ast.Constant(value="doc")
        const.end_lineno = None  # force the defensive branch
        return ast.Module(body=[ast.Expr(value=const)], type_ignores=[])

    monkeypatch.setattr(mod.ast, "parse", fake_parse)
    assert mod.find_python_docstring_end("anything") is None


# ══════════════════════════════════════════════════════════════════════════════
# insert_python_header
# ══════════════════════════════════════════════════════════════════════════════
def test_insert_python_docstring_no_trailing_blank():
    # docstring immediately followed by code: while-loop condition False (no body run)
    out = mod.insert_python_header('"""Doc."""\nimport os\n')
    assert mod.has_spdx_header(out, is_python=True) is True
    assert out.startswith('"""Doc."""')


def test_insert_python_docstring_with_trailing_blank():
    # blank line after docstring -> while-loop body executes (line 162)
    out = mod.insert_python_header('"""Doc."""\n\nimport os\n')
    assert mod.has_spdx_header(out, is_python=True) is True
    lines = out.split("\n")
    # SPDX lines land right after the docstring's blank line
    assert L in lines and C in lines and lines.index(L) < lines.index("import os")


def test_insert_python_no_docstring_no_shebang():
    # line 176
    out = mod.insert_python_header("import os\nY = 2\n")
    assert out.split("\n")[0] == L
    assert mod.has_spdx_header(out, is_python=True) is True


def test_insert_python_no_docstring_with_shebang():
    # line 174 — header goes after the shebang
    out = mod.insert_python_header("#!/usr/bin/env python\nimport os\n")
    lines = out.split("\n")
    assert lines[0] == "#!/usr/bin/env python"
    assert lines[1] == L and lines[2] == C
    assert mod.has_spdx_header(out, is_python=True) is True


# ══════════════════════════════════════════════════════════════════════════════
# insert_yaml_header
# ══════════════════════════════════════════════════════════════════════════════
def test_insert_yaml_no_shebang():
    out = mod.insert_yaml_header("name: CI\non: push\n")
    assert out.split("\n")[0] == L
    assert mod.has_spdx_header(out, is_python=False) is True


def test_insert_yaml_with_shebang():
    out = mod.insert_yaml_header("#!/bin/sh\necho hi\n")
    lines = out.split("\n")
    assert lines[0] == "#!/bin/sh" and lines[1] == L and lines[2] == C


# ══════════════════════════════════════════════════════════════════════════════
# update_gitignore
# ══════════════════════════════════════════════════════════════════════════════
def test_update_gitignore_adds_missing_no_trailing_newline(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    # no trailing newline -> line 200 executes
    (tmp_path / ".gitignore").write_text("*.md\nvenv/", encoding="utf-8", newline="\n")
    added = mod.update_gitignore()
    assert added == 3
    content = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    for line in mod.GITIGNORE_WHITELIST_LINES:
        assert line in content


def test_update_gitignore_all_present_returns_zero(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    gi = "*.md\n" + "\n".join(mod.GITIGNORE_WHITELIST_LINES) + "\n"
    (tmp_path / ".gitignore").write_text(gi, encoding="utf-8", newline="\n")
    assert mod.update_gitignore() == 0  # line 196 True -> 197


def test_update_gitignore_partial_with_trailing_newline(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    # one whitelist line already present; content ends with newline -> line 199 False
    gi = "*.md\n" + mod.GITIGNORE_WHITELIST_LINES[0] + "\n"
    (tmp_path / ".gitignore").write_text(gi, encoding="utf-8", newline="\n")
    added = mod.update_gitignore()
    assert added == 2  # the other 2 whitelist lines


def test_update_gitignore_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    (tmp_path / ".gitignore").write_text("*.md\n", encoding="utf-8", newline="\n")
    assert mod.update_gitignore() == 3
    assert mod.update_gitignore() == 0  # second run is a no-op


# ══════════════════════════════════════════════════════════════════════════════
# process_file
# ══════════════════════════════════════════════════════════════════════════════
def test_process_file_excluded(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    p = tmp_path / "core" / "_minifasnet" / "model.py"
    _write(p, "x = 1\n")
    assert mod.process_file(p, check_only=False) == "excluded"  # line 211


def test_process_file_unreadable_invalid_utf8(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    p = tmp_path / "core" / "bad.py"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"\xff\xfe\x00 not utf8")  # UnicodeDecodeError -> line 214-216
    assert mod.process_file(p, check_only=False) == "error"
    assert "cannot read" in capsys.readouterr().err


def test_process_file_unreadable_oserror(tmp_path, monkeypatch, capsys):
    """Nonexistent path -> FileNotFoundError (an OSError) hits the same arm."""
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    p = tmp_path / "core" / "ghost.py"  # never created
    assert mod.process_file(p, check_only=False) == "error"
    assert "cannot read" in capsys.readouterr().err


def test_process_file_already_headered(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    p = tmp_path / "core" / "done.py"
    _write(p, _pyfile(headered=True))
    assert mod.process_file(p, check_only=False) == "skipped"  # line 219


def test_process_file_check_only_would_add_does_not_write(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    p = tmp_path / "core" / "todo.py"
    original = _pyfile(headered=False)
    _write(p, original)
    assert mod.process_file(p, check_only=True) == "added"  # line 221 (would-add)
    assert p.read_text(encoding="utf-8") == original  # not modified


def test_process_file_apply_python(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    p = tmp_path / "core" / "apply.py"
    _write(p, _pyfile(headered=False))
    assert mod.process_file(p, check_only=False) == "added"  # lines 224, 230, 231
    assert mod.has_spdx_header(p.read_text(encoding="utf-8"), is_python=True) is True


def test_process_file_apply_yaml(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    p = tmp_path / ".github" / "workflows" / "ci.yml"
    _write(p, _ymlfile(headered=False))
    assert mod.process_file(p, check_only=False) == "added"  # lines 226, 230, 231
    assert mod.has_spdx_header(p.read_text(encoding="utf-8"), is_python=False) is True


def test_process_file_unknown_extension(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    p = tmp_path / "notes.txt"  # neither .py nor .yml
    _write(p, "hello\n")
    assert mod.process_file(p, check_only=False) == "error"  # lines 228-229
    assert "unknown extension" in capsys.readouterr().err


def test_process_file_write_error(tmp_path, monkeypatch, capsys):
    """insert_python_header raises -> except path (lines 232-235, incl. traceback)."""
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)

    def boom(_content):
        raise ValueError("synthetic insert failure")

    monkeypatch.setattr(mod, "insert_python_header", boom)
    p = tmp_path / "core" / "willfail.py"
    _write(p, _pyfile(headered=False))
    assert mod.process_file(p, check_only=False) == "error"
    err = capsys.readouterr().err
    assert "cannot write" in err and "ValueError" in err


# ══════════════════════════════════════════════════════════════════════════════
# main
# ══════════════════════════════════════════════════════════════════════════════
def test_main_apply_mode(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["add_spdx_headers.py"])  # apply mode
    _build_repo(tmp_path)  # unheadered tree, .gitignore without whitelist
    rc = mod.main()
    assert rc == 0  # line 276 else-branch (apply mode never returns 1)
    out = capsys.readouterr().out
    assert "ADDED" in out  # line 254 fired (line 253 True side)
    assert "Added: 10" in out
    # files actually headered now
    assert mod.has_spdx_header((tmp_path / "core" / "foo.py").read_text(encoding="utf-8"), is_python=True)
    # .gitignore updated (line 262)
    gi = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    for line in mod.GITIGNORE_WHITELIST_LINES:
        assert line in gi
    assert ".gitignore lines added: 3" in out


def test_main_check_mode_dirty_returns_one(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["add_spdx_headers.py", "--check"])
    _build_repo(tmp_path)  # unheadered -> would-add
    foo = tmp_path / "core" / "foo.py"
    before = foo.read_text(encoding="utf-8")
    rc = mod.main()
    assert rc == 1  # line 276 -> args.check True and stuff to add
    # check mode must not modify files (line 253 False side; 264-266 gitignore count)
    assert foo.read_text(encoding="utf-8") == before
    out = capsys.readouterr().out
    assert "WOULD-ADD" not in out  # line 253 False -> no per-file print in check mode
    assert ".gitignore lines added: 3" in out


def test_main_check_mode_clean_returns_zero(tmp_path, monkeypatch, capsys):
    """Apply first (headers everything + gitignore), then --check finds nothing."""
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    _build_repo(tmp_path)
    monkeypatch.setattr(sys, "argv", ["add_spdx_headers.py"])
    assert mod.main() == 0  # apply
    capsys.readouterr()  # drain
    monkeypatch.setattr(sys, "argv", ["add_spdx_headers.py", "--check"])
    rc = mod.main()  # everything headered + gitignore complete
    assert rc == 0  # line 276 -> check mode with nothing to add
    out = capsys.readouterr().out
    assert "Added: 0" in out and ".gitignore lines added: 0" in out


def test_main_prints_excluded(tmp_path, monkeypatch, capsys):
    """Cover the in-loop 'excluded' print (lines 251 True -> 252).
    collect_in_scope() normally filters excluded paths, so we inject one via a
    stubbed collect_in_scope to drive process_file down the excluded branch."""
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["add_spdx_headers.py"])
    excluded = tmp_path / "core" / "_minifasnet" / "model.py"
    _write(excluded, "x = 1\n")
    _write(tmp_path / ".gitignore", "*.md\n")
    monkeypatch.setattr(mod, "collect_in_scope", lambda: [excluded])
    rc = mod.main()
    assert rc == 0
    out = capsys.readouterr().out
    assert "EXCLUDED (vendored MIT): core/_minifasnet/model.py" in out
