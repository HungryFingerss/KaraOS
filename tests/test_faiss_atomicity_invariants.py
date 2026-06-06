"""
P0.5 structural invariants — ordering-enforcing, DLL-safe, PR-blocking.

Each paired-write method in FaceDB must follow the EXACT structural pattern:

    with self._index_lock:                      # outer lock
        with self.transaction():                # 1. SQL transaction (sibling)
            ...                                 # SQL ops; NO FAISS calls inside
        # transaction exited — SQL durable
        try:                                    # 2. FAISS try/except (sibling, AFTER tx)
            self.index.add/remove_ids(...)
            self._save_faiss()
        except Exception:
            self._mark_faiss_dirty()
            raise

ORDERING is enforced. The FAISS try/except must be a SIBLING AFTER the
transaction with-block, NOT a descendant of it. FAISS-inside-transaction
is the regression class this test exists to catch.

Also checks:
  - Both FaceDB.transaction() and BrainDB.transaction() handle the S65
    ROLLBACK race (inner try/except around ROLLBACK).
  - Voice-gallery functions (operating on voice_embeddings) do NOT acquire
    _index_lock.

DLL-safe: AST scan; no pipeline import.

SCOPE LIMIT: This test checks the methods listed in PAIRED_WRITE_METHODS.
prune_old_strangers_async uses a delegation pattern (calls
prune_old_strangers_sql_only + rebuild_faiss_async). Its end-to-end
crash recovery + DB write-through correctness is covered by:
  - tests/test_faiss_sql_atomicity.py::test_prune_async_then_restart_recognizes_known_person
  - tests/test_faiss_sql_atomicity.py::test_prune_async_crash_mid_db_update_recovers_via_sentinel
(P0.B2 D5 closure 2026-05-21 — landed after the prior comment claimed
slow-tier coverage that did not exist; documentation-vs-reality drift
explicitly named here so it doesn't recur.)
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "core" / "db.py"
BRAIN_AGENT_PATH = REPO_ROOT / "core" / "brain_agent" / "memory" / "store.py"

# Sync paired-write methods that must follow the lock → transaction → FAISS pattern.
# prune_old_strangers_async excluded: delegates to sql_only + rebuild_faiss_async.
# prune_zero_value_stranger included: calls _rebuild_faiss() under _index_lock (same
# P0.5 pattern as delete_person). Discovered during P0.5 implementation; the inverse
# check test below is what would have caught this gap automatically.
PAIRED_WRITE_METHODS = (
    "add_embedding",
    "delete_person",
    "prune_old_strangers",
    "prune_zero_value_stranger",
    "prune_outlier_embeddings",
)

# Voice-gallery functions that must NOT acquire _index_lock.
VOICE_GALLERY_METHODS = (
    "add_voice_embedding",
    "load_voice_profile_for",
    "load_voice_profiles",
    "load_voice_profile_sizes",
    "count_voice_embeddings",
)


def _read_source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _find_method_in_class(tree, class_name: str, method_name: str):
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if child.name == method_name:
                        return child
    return None


def _has_index_lock_with_block(method) -> bool:
    for node in ast.walk(method):
        if isinstance(node, ast.With):
            for item in node.items:
                if "self._index_lock" in ast.unparse(item.context_expr):
                    return True
    return False


def _check_paired_write_ordering(method):
    """
    Enforce that the FAISS try/except is a SIBLING of the transaction
    with-block, AFTER it — NOT a descendant.

    Walks the body of the with self._index_lock: block. Looks for:
      1. A `with self.transaction():` child (must NOT contain FAISS calls).
      2. A try/except SIBLING AFTER it, where try contains
         index.add/remove_ids AND except contains _mark_faiss_dirty.

    Returns (ok: bool, reason: str | None).
    """
    for node in ast.walk(method):
        if not isinstance(node, ast.With):
            continue
        if not any("self._index_lock" in ast.unparse(item.context_expr)
                   for item in node.items):
            continue

        children = node.body
        transaction_idx = None

        for i, stmt in enumerate(children):
            if isinstance(stmt, ast.With) and any(
                "self.transaction()" in ast.unparse(item.context_expr)
                for item in stmt.items
            ):
                transaction_idx = i
                tx_src = ast.unparse(stmt)
                if "self.index.add(" in tx_src or "self.index.remove_ids(" in tx_src:
                    return (False,
                            "FAISS write inside transaction — SQL would roll back on FAISS failure")
                break

        if transaction_idx is None:
            return (False,
                    "no `with self.transaction():` block inside `with self._index_lock:`")

        _FAISS_OPS = ("self.index.add(", "self.index.remove_ids(", "self._rebuild_faiss(")
        for stmt in children[transaction_idx + 1:]:
            if isinstance(stmt, ast.Try):
                try_src = "\n".join(ast.unparse(s) for s in stmt.body)
                if any(op in try_src for op in _FAISS_OPS):
                    for handler in stmt.handlers:
                        handler_src = "\n".join(ast.unparse(s) for s in handler.body)
                        if "_mark_faiss_dirty(" in handler_src:
                            return (True, None)
                    return (False,
                            "FAISS try/except found but except missing _mark_faiss_dirty()")

        return (False, "no FAISS try/except found AFTER transaction context")

    return (False, "no `with self._index_lock:` block found in method")


def _scan_paired_write_method(source: str, method_name: str) -> list[str]:
    tree = ast.parse(source)
    method = _find_method_in_class(tree, "FaceDB", method_name)
    if method is None:
        return [f"FaceDB.{method_name}: method not found"]

    issues = []
    if not _has_index_lock_with_block(method):
        issues.append(f"FaceDB.{method_name}: missing `with self._index_lock:` block")

    ok, reason = _check_paired_write_ordering(method)
    if not ok:
        issues.append(f"FaceDB.{method_name}: ordering violation — {reason}")

    return issues


# ── paired-write invariant ────────────────────────────────────────────────────

@pytest.mark.parametrize("method_name", PAIRED_WRITE_METHODS)
def test_paired_write_method_follows_p05_pattern(method_name):
    """
    Each paired-write method must follow the lock → transaction → FAISS
    ordering. FAISS-inside-transaction and FAISS-before-SQL both fail.
    """
    source = _read_source(DB_PATH)
    issues = _scan_paired_write_method(source, method_name)
    assert not issues, (
        f"P0.5 structural invariant violated:\n"
        + "\n".join(f"  - {i}" for i in issues)
        + "\n\nExpected pattern:\n"
        "    with self._index_lock:\n"
        "        with self.transaction():\n"
        "            # SQL ops, NO FAISS calls\n"
        "        try:\n"
        "            self.index.add/remove_ids(...)\n"
        "            self._save_faiss()\n"
        "        except Exception:\n"
        "            self._mark_faiss_dirty()\n"
        "            raise"
    )


# ── inverse paired-write check ────────────────────────────────────────────────

# Methods excluded from the inverse scan:
# - _rebuild_faiss: the internal implementation; FAISS calls here ARE the rebuild.
# - _save_faiss: low-level persistence helper called by paired-write methods.
# - _load_faiss: boot reconciliation; calls _rebuild_faiss but is not a user-facing
#   paired-write method (no SQL transaction).
_INVERSE_SCAN_EXCLUDE = frozenset({
    "_rebuild_faiss",
    "_save_faiss",
    "_load_faiss",
})

_FAISS_CALL_MARKERS = (
    "self.index.add(",
    "self.index.remove_ids(",
    "self._rebuild_faiss(",
)

# P0.S9 D3 — extend inverse-check scan surface from `core/db.py` only to
# `core/*.py` top-level (not recursive). Vendored subdirs excluded:
# `core/_minifasnet/` (MiniFASNet upstream vendor) + `core/event_log/`
# (event-log producer package; no FAISS surface).
_SCAN_EXCLUDE = frozenset({
    "core/_minifasnet",
    "core/event_log",
})


def _scan_paths() -> list[Path]:
    """P0.S9 D3 — return `core/*.py` top-level files; skip vendored subdirs.

    Top-level glob (NOT recursive `**/*.py`) by design — vendored subdirs
    (`core/_minifasnet/` MiniFASNet upstream, `core/event_log/` producer
    package) don't have FAISS surface and shouldn't be scanned. Path
    comparison uses POSIX-style slashes for cross-platform consistency
    with `_SCAN_EXCLUDE` entries.
    """
    core_dir = REPO_ROOT / "core"
    paths = []
    for p in core_dir.glob("*.py"):
        rel = p.relative_to(REPO_ROOT).as_posix()
        if not any(rel.startswith(exc) for exc in _SCAN_EXCLUDE):
            paths.append(p)
    return paths


def _find_faiss_writing_methods(source: str) -> list[str]:
    """Return names of methods (across any class + module-level functions)
    that contain a FAISS write call, excluding internal helpers listed in
    _INVERSE_SCAN_EXCLUDE.

    P0.S9 D3: widened from FaceDB-class-only to ANY class + module-level
    functions across the scanned source. The original P0.5 invariant tracked
    FaceDB methods; D3 widens the surface so a future FAISS-writing method
    landed outside FaceDB (e.g. a helper function in `core/audit.py` or a
    different class) gets caught by the inverse check.
    """
    tree = ast.parse(source)
    hits = []
    # Module-level function definitions
    for child in tree.body:
        if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        name = child.name
        if name in _INVERSE_SCAN_EXCLUDE:
            continue
        src = ast.unparse(child)
        if any(marker in src for marker in _FAISS_CALL_MARKERS):
            hits.append(name)
    # All class methods (FaceDB + any other class containing FAISS calls)
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for child in node.body:
            if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            name = child.name
            if name in _INVERSE_SCAN_EXCLUDE:
                continue
            src = ast.unparse(child)
            if any(marker in src for marker in _FAISS_CALL_MARKERS):
                hits.append(name)
    return hits


def test_all_paired_write_sites_are_in_tuple():
    """Every method/function across `core/*.py` that calls a FAISS write op
    must be in PAIRED_WRITE_METHODS.

    This is the inverse of test_paired_write_method_follows_p05_pattern: that
    test verifies listed methods are correctly structured; this test verifies
    no FAISS-writing method was silently omitted from the list.

    Without this check, adding a new FAISS-writing method (e.g. prune_zero_value_stranger,
    or a helper function in `core/audit.py`) would bypass the P0.5 structural
    invariant entirely — the pattern test would never scan it.

    P0.S9 D3: scan surface widened from `core/db.py` only to `core/*.py`
    top-level glob (excluding vendored subdirs `core/_minifasnet/` and
    `core/event_log/` via `_SCAN_EXCLUDE`). The original `core.audit.repair_gallery`
    paired-write violation (deleted at P0.S9 D1 consolidation) would have been
    surfaced by this widened scan IF its FAISS calls had used `self.*` markers;
    historical violation used `db.*` external-reference shape which the markers
    don't catch by design (markers anchor on `self.` to scope to in-class state).
    The widened scan structurally protects against future violations that
    follow the in-class FaceDB-like pattern but land in another core/ file.
    """
    unlisted_total: list[tuple[Path, str]] = []
    for path in _scan_paths():
        source = path.read_text(encoding="utf-8")
        faiss_writers = _find_faiss_writing_methods(source)
        unlisted = [m for m in faiss_writers if m not in PAIRED_WRITE_METHODS]
        for m in unlisted:
            unlisted_total.append((path, m))
    assert not unlisted_total, (
        f"FAISS-writing methods across core/*.py not in PAIRED_WRITE_METHODS:\n"
        + "\n".join(f"  - {p.relative_to(REPO_ROOT).as_posix()}::{m}" for p, m in unlisted_total)
        + "\n\nAdd them to PAIRED_WRITE_METHODS so the P0.5 structural pattern "
        "test covers them, OR add them to _INVERSE_SCAN_EXCLUDE with a comment "
        "explaining why they are exempt."
    )


# ── transaction() ROLLBACK race structural test ───────────────────────────────

def _check_transaction_rollback_race(source: str, class_name: str) -> list[str]:
    """Check that class_name.transaction() has inner ROLLBACK try/except (S65)."""
    tree = ast.parse(source)
    method = _find_method_in_class(tree, class_name, "transaction")
    if method is None:
        return [f"{class_name}.transaction(): method not found"]

    src = ast.unparse(method)
    # Must have nested try/except around ROLLBACK:
    #   except Exception:
    #       try:
    #           self._conn.execute("ROLLBACK")
    #       except Exception:
    #           pass  # RACE: S65
    #       raise
    for node in ast.walk(method):
        if not isinstance(node, ast.ExceptHandler):
            continue
        # Look for a try inside this except handler whose body contains ROLLBACK
        for child in ast.walk(node):
            if not isinstance(child, ast.Try):
                continue
            inner_src = ast.unparse(child)
            if "ROLLBACK" in inner_src:
                return []  # found — correct

    return [
        f"{class_name}.transaction(): missing inner try/except around ROLLBACK "
        f"(S65 race: ROLLBACK raises if COMMIT auto-rolled back)"
    ]


def test_transaction_methods_handle_s65_rollback_race():
    """
    Both FaceDB.transaction() and BrainDB.transaction() must wrap the
    ROLLBACK call in an inner try/except so the S65 race doesn't mask
    the original exception.
    """
    db_source = _read_source(DB_PATH)
    brain_source = _read_source(BRAIN_AGENT_PATH)

    issues = []
    issues.extend(_check_transaction_rollback_race(db_source, "FaceDB"))
    issues.extend(_check_transaction_rollback_race(brain_source, "BrainDB"))

    assert not issues, (
        "S65 ROLLBACK race not handled:\n"
        + "\n".join(f"  - {i}" for i in issues)
        + "\n\nFix: wrap ROLLBACK in inner try/except:\n"
        "    except Exception:\n"
        "        try:\n"
        "            self._conn.execute('ROLLBACK')\n"
        "        except Exception:\n"
        "            pass  # RACE: S65\n"
        "        raise"
    )


# ── voice gallery isolation structural test ───────────────────────────────────

def test_voice_gallery_functions_do_not_acquire_index_lock():
    """
    Voice-gallery functions operate on voice_embeddings, not the FAISS
    face index. Acquiring _index_lock in a voice-gallery function creates
    spurious contention with face recognition. None may hold _index_lock.
    """
    source = _read_source(DB_PATH)
    tree = ast.parse(source)
    violations = []

    for method_name in VOICE_GALLERY_METHODS:
        method = _find_method_in_class(tree, "FaceDB", method_name)
        if method is None:
            continue
        if _has_index_lock_with_block(method):
            violations.append(
                f"FaceDB.{method_name}: acquires _index_lock — "
                f"voice-gallery functions must not hold the face-index lock"
            )

    assert not violations, (
        "Voice-gallery isolation violated:\n"
        + "\n".join(f"  - {v}" for v in violations)
    )


# ── detector self-tests ───────────────────────────────────────────────────────

@pytest.mark.parametrize("synthetic_method, expect_issues", [
    # 1. Correct shape — no issues.
    ("""
class FaceDB:
    def add_embedding(self, x):
        with self._index_lock:
            with self.transaction():
                self._conn.execute("INSERT ...")
            try:
                self.index.add(x)
                self._save_faiss()
            except Exception:
                self._mark_faiss_dirty()
                raise
""", False),

    # 2. Missing transaction wrap.
    ("""
class FaceDB:
    def add_embedding(self, x):
        with self._index_lock:
            self._conn.execute("INSERT ...")
            try:
                self.index.add(x)
            except Exception:
                self._mark_faiss_dirty()
""", True),

    # 3. Missing _mark_faiss_dirty in except.
    ("""
class FaceDB:
    def add_embedding(self, x):
        with self._index_lock:
            with self.transaction():
                self._conn.execute("INSERT ...")
            try:
                self.index.add(x)
            except Exception:
                pass
""", True),

    # 4. FAISS write outside try/except.
    ("""
class FaceDB:
    def add_embedding(self, x):
        with self._index_lock:
            with self.transaction():
                self._conn.execute("INSERT ...")
            self.index.add(x)
""", True),

    # 5. Missing _index_lock.
    ("""
class FaceDB:
    def add_embedding(self, x):
        with self.transaction():
            self._conn.execute("INSERT ...")
        try:
            self.index.add(x)
        except Exception:
            self._mark_faiss_dirty()
""", True),

    # 6. FAISS INSIDE transaction (ordering violation).
    # Architectural bug: SQL would roll back on FAISS failure.
    ("""
class FaceDB:
    def add_embedding(self, x):
        with self._index_lock:
            with self.transaction():
                self._conn.execute("INSERT ...")
                try:
                    self.index.add(x)
                    self._save_faiss()
                except Exception:
                    self._mark_faiss_dirty()
                    raise
""", True),

    # 7. FAISS BEFORE transaction (ordering violation).
    # Reverse order: FAISS already mutated when SQL commits.
    ("""
class FaceDB:
    def add_embedding(self, x):
        with self._index_lock:
            try:
                self.index.add(x)
                self._save_faiss()
            except Exception:
                self._mark_faiss_dirty()
                raise
            with self.transaction():
                self._conn.execute("INSERT ...")
""", True),

    # 8. delete_person variant (_rebuild_faiss instead of index.add).
    # IndexFlatIP has no selective remove; delete_person uses full rebuild.
    ("""
class FaceDB:
    def delete_person(self, pid):
        with self._index_lock:
            with self.transaction():
                self._conn.execute("DELETE ...")
            try:
                self._rebuild_faiss()
            except Exception:
                self._mark_faiss_dirty()
                raise
""", False),
])
def test_detector_against_synthetic_methods(synthetic_method, expect_issues):
    """
    Detector must catch the explicit ordering violations (cases 6 and 7)
    as well as missing components (cases 2-5). Cases 1 and 8 must pass.
    """
    method_name = (
        "delete_person" if "delete_person" in synthetic_method else "add_embedding"
    )
    issues = _scan_paired_write_method(synthetic_method, method_name)
    has_issues = len(issues) > 0
    assert has_issues == expect_issues, (
        f"Detector mismatch:\n{synthetic_method}\nissues={issues}"
    )
