"""P0.9 invariants — schema-migration foundation tests.

This file contains the structural invariants and behavioral tests for the
P0.9 versioned schema-migration ledger.  Grep target: "P0.9 invariants".

Behavioral tests cover the ledger lifecycle on in-memory SQLite DBs
(init → bootstrap → walk MIGRATIONS → apply, idempotent re-run).
Source-inspection (AST) tests enforce the Phase 1/2 structural invariants:

  - every `sqlite3.connect(...)` in core/*.py opens with
    `isolation_level="IMMEDIATE"` (Imp-1 — P0.9.1)
  - every "RACE: S65" rollback handler uses the tightened
    message-check pattern (Imp-2 — P0.9.1)
  - every MIGRATIONS entry across the 3 DBs is a 5-tuple of
    `(int, str, callable, callable, callable)` — every migration has
    BOTH verify companions (Item 1 — P0.9.2)
  - the runner uses BEGIN IMMEDIATE inside `apply_migrations`
  - bootstrap walks MIGRATIONS and stamps pre-existing artifacts with
    is_initial=1 (P0.9.2 — required for legacy production DBs)
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import ast
import inspect
import pathlib
import re
import sqlite3
import sys

import pytest

from core import schema_migrations as _sm


REPO = pathlib.Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fresh_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", isolation_level="IMMEDIATE")
    return conn


def _ledger_rows(conn: sqlite3.Connection) -> list[tuple]:
    return list(conn.execute(
        "SELECT version, description, is_initial FROM schema_migrations "
        "ORDER BY version"
    ))


# ---------------------------------------------------------------------------
# Group 1: behavioral — init_ledger creates the table at latest shape
# ---------------------------------------------------------------------------

class TestInitLedger:
    def test_fresh_db_creates_ledger_with_is_initial_column(self):
        conn = _fresh_conn()
        _sm.init_ledger(conn)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(schema_migrations)")}
        assert cols == {"version", "description", "applied_at", "is_initial"}
        # Ledger is empty on first init — no rows.
        assert conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 0

    def test_init_is_idempotent(self):
        conn = _fresh_conn()
        _sm.init_ledger(conn)
        _sm.init_ledger(conn)  # second call MUST NOT raise
        cols = {r[1] for r in conn.execute("PRAGMA table_info(schema_migrations)")}
        assert "is_initial" in cols

    def test_legacy_ledger_self_evolves_to_add_is_initial(self):
        """Pre-P0.9 ledger (Spec 1 / Session 122 classifier_scenarios.db
        shape) had no is_initial column.  init_ledger MUST add it via
        ALTER without losing existing rows."""
        conn = _fresh_conn()
        # Simulate the pre-P0.9 shape.
        conn.execute("""
            CREATE TABLE schema_migrations (
                version       INTEGER PRIMARY KEY,
                description   TEXT NOT NULL,
                applied_at    TEXT NOT NULL
            )
        """)
        conn.execute(
            "INSERT INTO schema_migrations (version, description, applied_at) "
            "VALUES (1, 'legacy v1', '2025-01-01T00:00:00')"
        )
        conn.execute(
            "INSERT INTO schema_migrations (version, description, applied_at) "
            "VALUES (2, 'legacy v2', '2025-01-02T00:00:00')"
        )
        conn.commit()

        _sm.init_ledger(conn)

        cols = {r[1] for r in conn.execute("PRAGMA table_info(schema_migrations)")}
        assert "is_initial" in cols, "is_initial column not added to legacy ledger"
        # Existing rows survive with is_initial=0 (DEFAULT — they were real
        # migrations, not bootstrap stamps).
        rows = _ledger_rows(conn)
        assert rows == [(1, "legacy v1", 0), (2, "legacy v2", 0)]


# ---------------------------------------------------------------------------
# Group 2: behavioral — bootstrap_ledger_if_unversioned
# ---------------------------------------------------------------------------

class TestBootstrapLedger:
    def test_legacy_db_with_baseline_tables_stamps_v1_is_initial_1(self):
        """A DB that had baseline tables BEFORE init_ledger ran gets
        v=1 stamped with is_initial=1 — marking it as pre-P0.9."""
        conn = _fresh_conn()
        # Simulate pre-existing baseline tables.
        conn.execute("CREATE TABLE persons (id TEXT PRIMARY KEY)")
        conn.execute("CREATE TABLE embeddings (id INTEGER PRIMARY KEY)")
        conn.commit()
        _sm.init_ledger(conn)
        inserted = _sm.bootstrap_ledger_if_unversioned(
            conn, baseline_description="faces.db initial baseline (pre-P0.9)"
        )
        assert inserted is True
        rows = _ledger_rows(conn)
        assert len(rows) == 1
        v, desc, is_init = rows[0]
        assert v == 1
        assert "pre-P0.9" in desc
        assert is_init == 1, "legacy DB must be flagged is_initial=1"

    def test_fresh_db_with_no_baseline_tables_stamps_is_initial_0(self):
        """A genuinely fresh DB (no tables apart from schema_migrations
        itself) gets v=1 stamped with is_initial=0."""
        conn = _fresh_conn()
        _sm.init_ledger(conn)
        inserted = _sm.bootstrap_ledger_if_unversioned(
            conn, baseline_description="fresh test DB"
        )
        assert inserted is True
        rows = _ledger_rows(conn)
        assert rows == [(1, "fresh test DB", 0)]

    def test_already_versioned_db_is_noop(self):
        """If the ledger already has rows (classifier_scenarios.db case),
        bootstrap MUST be a no-op."""
        conn = _fresh_conn()
        _sm.init_ledger(conn)
        conn.execute(
            "INSERT INTO schema_migrations "
            "(version, description, applied_at, is_initial) "
            "VALUES (1, 'pre-existing', '2025-01-01', 0)"
        )
        conn.commit()
        inserted = _sm.bootstrap_ledger_if_unversioned(
            conn, baseline_description="should not insert"
        )
        assert inserted is False
        rows = _ledger_rows(conn)
        assert rows == [(1, "pre-existing", 0)]


# ---------------------------------------------------------------------------
# Group 2.5 (P0.9.2): bootstrap walks MIGRATIONS and stamps pre-existing
# artifacts.  Without this, Phase 2's ~25 retrofitted migrations would
# crash on first boot against any legacy production DB.
# ---------------------------------------------------------------------------

def _make_fixture_migrations(n: int) -> list:
    """Build N test-fixture migrations.  Each creates table t{version} and
    has verify_post (asserts table exists) + verify_present (returns True
    iff table exists).  The verify_present semantic is the load-bearing
    bit — bootstrap calls it to decide whether the artifact is already
    on disk."""
    out = []
    for v in range(2, 2 + n):
        def make_apply(_v):
            def _apply(c): c.execute(f"CREATE TABLE t{_v} (id INTEGER)")
            return _apply

        def make_verify_post(_v):
            def _vp(c):
                assert any(
                    r[0] == f"t{_v}" for r in
                    c.execute("SELECT name FROM sqlite_master WHERE type='table'")
                ), f"t{_v} not present after apply"
            return _vp

        def make_verify_present(_v):
            def _vpr(c) -> bool:
                return any(
                    r[0] == f"t{_v}" for r in
                    c.execute("SELECT name FROM sqlite_master WHERE type='table'")
                )
            return _vpr

        out.append((v, f"create t{v}", make_apply(v), make_verify_post(v), make_verify_present(v)))
    return out


class TestBootstrapWalksMigrations:
    """The critical Phase 2 path: bootstrap must walk MIGRATIONS and stamp
    pre-existing artifacts with is_initial=1, so apply_migrations skips
    them.  Without this, legacy production DBs crash on first P0.9.2 boot
    with `OperationalError: duplicate column name` on every retrofitted
    ALTER TABLE."""

    def test_bootstrap_stamps_pre_existing_migrations_on_legacy_db(self):
        """All ~70 retrofit artifacts already exist on the legacy DB →
        bootstrap stamps ALL with is_initial=1 → apply_migrations runs
        zero migrations.

        This is the production-DB-on-first-P0.9.2-boot scenario.  Without
        the walk, runner crashes on every retrofitted ALTER."""
        conn = _fresh_conn()
        migrations = _make_fixture_migrations(5)

        # Pre-create the artifacts (simulating legacy DB state — they
        # were applied by the pre-P0.9 inline _migrate() before the
        # ledger existed).
        for version, _desc, apply_fn, _vp, _vpr in migrations:
            apply_fn(conn)
        conn.commit()

        _sm.init_ledger(conn)
        inserted = _sm.bootstrap_ledger_if_unversioned(
            conn,
            baseline_description="legacy DB",
            migrations=migrations,
        )
        assert inserted is True

        rows = _ledger_rows(conn)
        # v=1 baseline + 5 migration stamps = 6 rows total.
        assert len(rows) == 6
        # Baseline (v=1) stamped is_initial=1 because pre-existing tables found.
        assert rows[0] == (1, "legacy DB", 1)
        # All 5 migrations stamped is_initial=1.
        for i, v in enumerate(range(2, 7), start=1):
            assert rows[i][0] == v, f"row {i}: expected version {v}"
            assert rows[i][2] == 1, (
                f"v={v}: expected is_initial=1 (pre-existing), got "
                f"{rows[i][2]}"
            )

        # Runner now MUST be a no-op — all versions already in ledger.
        applied = _sm.apply_migrations(conn, migrations)
        assert applied == [], (
            "After bootstrap stamped all migrations, apply_migrations "
            "must not run any.  This is the production-safety invariant."
        )

    def test_bootstrap_leaves_unstamped_migrations_for_runner(self):
        """No artifacts pre-exist → bootstrap stamps only v=1 baseline →
        runner applies all migrations with is_initial=0.

        This is the fresh-DB scenario.  Bootstrap walk MUST NOT stamp
        migrations whose verify_present returns False."""
        conn = _fresh_conn()
        migrations = _make_fixture_migrations(5)

        _sm.init_ledger(conn)
        # NO pre-creation — DB is empty apart from the ledger.
        inserted = _sm.bootstrap_ledger_if_unversioned(
            conn,
            baseline_description="fresh DB",
            migrations=migrations,
        )
        assert inserted is True
        rows = _ledger_rows(conn)
        # Only baseline row, is_initial=0 (fresh).
        assert rows == [(1, "fresh DB", 0)]

        # Runner applies all 5; each gets is_initial=0 (real migration).
        applied = _sm.apply_migrations(conn, migrations)
        assert applied == [2, 3, 4, 5, 6]
        rows_after = _ledger_rows(conn)
        for i, v in enumerate(range(2, 7), start=1):
            assert rows_after[i][0] == v
            assert rows_after[i][2] == 0, (
                f"v={v}: runner-applied migration must have is_initial=0"
            )

    def test_bootstrap_partial_migration_state(self):
        """First 3 of 5 artifacts pre-exist → bootstrap stamps those 3 →
        runner applies the remaining 2.  Mixed legacy/forward DB
        scenario (e.g. operator applied some ALTERs manually before
        P0.9.2 landed)."""
        conn = _fresh_conn()
        migrations = _make_fixture_migrations(5)

        # Pre-create first 3 artifacts only.
        for version, _desc, apply_fn, _vp, _vpr in migrations[:3]:
            apply_fn(conn)
        conn.commit()

        _sm.init_ledger(conn)
        _sm.bootstrap_ledger_if_unversioned(
            conn,
            baseline_description="partial-state DB",
            migrations=migrations,
        )

        rows = _ledger_rows(conn)
        # v=1 baseline + 3 stamped pre-existing.
        assert len(rows) == 4
        # is_initial=1 for the baseline (pre-existing tables) AND the 3
        # pre-stamped migrations.
        assert rows[0] == (1, "partial-state DB", 1)
        for i, v in enumerate(range(2, 5), start=1):
            assert rows[i][0] == v
            assert rows[i][2] == 1, f"v={v}: expected is_initial=1"

        # Runner picks up v=5 and v=6 (the unstamped ones).
        applied = _sm.apply_migrations(conn, migrations)
        assert applied == [5, 6]
        rows_after = _ledger_rows(conn)
        assert len(rows_after) == 6
        # Runner-applied stamps are is_initial=0.
        v5_row = next(r for r in rows_after if r[0] == 5)
        v6_row = next(r for r in rows_after if r[0] == 6)
        assert v5_row[2] == 0 and v6_row[2] == 0


# ---------------------------------------------------------------------------
# M1: classifier-specific test — pre-existing v=1/v=2 ledger rows get
# is_initial=0 via init_ledger's self-evolving ALTER DEFAULT (they were
# real migrations, not bootstrap stamps).
# ---------------------------------------------------------------------------

class TestClassifierLedgerSelfEvolve:
    def test_classifier_ledger_self_evolve_preserves_existing_rows_as_real_migrations(self):
        """Pre-P0.9 classifier_scenarios.db has a `schema_migrations`
        table WITHOUT is_initial column (Spec 1 / Session 122 shape).
        init_ledger's self-evolving ALTER adds the column with DEFAULT 0,
        which is correct: those existing rows were REAL migrations
        applied by the pre-P0.9 `_run_migrations()`, not bootstrap stamps.

        If a future change set DEFAULT 1 (or backfilled them as 1), the
        runner would mistakenly think those migrations were never
        actually applied — which would re-run them on legacy DBs."""
        conn = _fresh_conn()
        # Simulate the Spec 1 classifier ledger shape.
        conn.execute("""
            CREATE TABLE schema_migrations (
                version       INTEGER PRIMARY KEY,
                description   TEXT NOT NULL,
                applied_at    TEXT NOT NULL
            )
        """)
        conn.execute(
            "INSERT INTO schema_migrations (version, description, applied_at) "
            "VALUES (1, 'initial schema (Spec 1)', '2025-01-01T00:00:00')"
        )
        conn.execute(
            "INSERT INTO schema_migrations (version, description, applied_at) "
            "VALUES (2, 'Spec 2: extracted_value column', '2025-02-01T00:00:00')"
        )
        conn.commit()

        _sm.init_ledger(conn)

        rows = _ledger_rows(conn)
        # Existing rows survived with is_initial=0 (real migrations).
        assert rows == [
            (1, "initial schema (Spec 1)", 0),
            (2, "Spec 2: extracted_value column", 0),
        ], (
            "Pre-P0.9 classifier ledger rows must be preserved with "
            "is_initial=0 (they were real migrations, not bootstrap stamps)"
        )


# ---------------------------------------------------------------------------
# Group 3: behavioral — apply_migrations runner
# ---------------------------------------------------------------------------

class TestApplyMigrations:
    def test_empty_migrations_is_noop(self):
        """Empty MIGRATIONS list is the Phase 1 default — runner must not
        raise, must not insert any ledger rows."""
        conn = _fresh_conn()
        _sm.init_ledger(conn)
        applied = _sm.apply_migrations(conn, [])
        assert applied == []
        assert conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 0

    def test_migration_fires_once_then_skips(self):
        """First call applies the migration; second call finds it in the
        ledger and skips."""
        conn = _fresh_conn()
        _sm.init_ledger(conn)

        ran_count = [0]
        verified_count = [0]

        def apply_fn(c):
            c.execute("CREATE TABLE foo (id INTEGER)")
            ran_count[0] += 1

        def verify_post(c):
            assert any(
                r[0] == "foo" for r in
                c.execute("SELECT name FROM sqlite_master WHERE type='table'")
            )
            verified_count[0] += 1

        def verify_present(c) -> bool:
            return any(
                r[0] == "foo" for r in
                c.execute("SELECT name FROM sqlite_master WHERE type='table'")
            )

        migrations = [(2, "create foo table", apply_fn, verify_post, verify_present)]

        applied1 = _sm.apply_migrations(conn, migrations)
        applied2 = _sm.apply_migrations(conn, migrations)

        assert applied1 == [2]
        assert applied2 == []
        assert ran_count[0] == 1
        assert verified_count[0] == 1

    def test_verify_failure_rolls_back_apply(self):
        """If verify_post_fn raises, the apply_fn's mutation MUST roll back
        AND the ledger row MUST NOT be inserted (atomic migrate-or-fail)."""
        conn = _fresh_conn()
        _sm.init_ledger(conn)

        def apply_fn(c):
            c.execute("CREATE TABLE bar (id INTEGER)")

        def verify_post(c):
            raise AssertionError("intentional verify failure")

        def verify_present(c) -> bool:
            return False

        with pytest.raises(AssertionError, match="intentional verify failure"):
            _sm.apply_migrations(
                conn, [(2, "create bar", apply_fn, verify_post, verify_present)],
            )

        # Table must NOT exist (rolled back).
        tables = {
            r[0] for r in
            conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert "bar" not in tables
        # Ledger row must NOT exist.
        rows = list(conn.execute("SELECT version FROM schema_migrations"))
        assert rows == []

    def test_migrations_apply_in_version_order(self):
        """Even if MIGRATIONS list is shuffled, apply order is sorted."""
        conn = _fresh_conn()
        _sm.init_ledger(conn)
        order: list[int] = []

        def make_apply(v):
            def _apply(c):
                order.append(v)
                c.execute(f"CREATE TABLE t{v} (id INTEGER)")
            return _apply

        def _verify_post(c):
            pass

        def _verify_present(c) -> bool:
            return False

        migrations = [
            (4, "t4", make_apply(4), _verify_post, _verify_present),
            (2, "t2", make_apply(2), _verify_post, _verify_present),
            (3, "t3", make_apply(3), _verify_post, _verify_present),
        ]
        applied = _sm.apply_migrations(conn, migrations)
        assert applied == [2, 3, 4]
        assert order == [2, 3, 4]


# ---------------------------------------------------------------------------
# Group 4: AST source-inspection — Imp-1 isolation_level=IMMEDIATE
# ---------------------------------------------------------------------------

def _iter_core_sqlite_connect_calls():
    """Yield (path, lineno, call_node) for every `sqlite3.connect(...)`
    call in `core/*.py` files that this runner is invoked against.
    Excludes `core/backup.py` which uses raw connections for one-shot
    file-level operations (no schema migrations)."""
    EXCLUDE = {"backup.py"}
    for path in (REPO / "core").rglob("*.py"):
        if path.name in EXCLUDE:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            if isinstance(f, ast.Attribute) and f.attr == "connect" \
                    and isinstance(f.value, ast.Name) and f.value.id == "sqlite3":
                yield path, node.lineno, node


class TestIsolationLevelImmediate:
    def test_every_core_sqlite_connect_uses_immediate_isolation(self):
        """Imp-1: every sqlite3.connect() in core/*.py MUST pass
        isolation_level="IMMEDIATE".  Excludes core/backup.py (one-shot
        file-level copy, no transaction discipline needed)."""
        violations: list[str] = []
        for path, lineno, call in _iter_core_sqlite_connect_calls():
            kw = next((k for k in call.keywords if k.arg == "isolation_level"), None)
            if kw is None:
                rel = path.relative_to(REPO).as_posix()
                violations.append(
                    f"{rel}:{lineno}: sqlite3.connect() missing "
                    "isolation_level=\"IMMEDIATE\" kwarg (Imp-1)"
                )
                continue
            if not (isinstance(kw.value, ast.Constant) and kw.value.value == "IMMEDIATE"):
                rel = path.relative_to(REPO).as_posix()
                violations.append(
                    f"{rel}:{lineno}: sqlite3.connect() isolation_level="
                    f"{ast.unparse(kw.value)} — must be literal \"IMMEDIATE\""
                )
        assert not violations, (
            "Imp-1 invariant violated.\n\n" + "\n".join(violations)
        )


# ---------------------------------------------------------------------------
# Group 5: AST source-inspection — Imp-2 tightened rollback
# ---------------------------------------------------------------------------

class TestTightenedRollback:
    """Every 'RACE: S65' rollback handler MUST use the tightened
    message-check pattern (re-raise unexpected OperationalErrors).  The
    bare `except Exception: pass` pattern is forbidden — it would silently
    swallow disk-full, lock-contention, and other operational errors that
    should be loud."""

    # Files where the rollback discipline is enforced.  These are the
    # transaction-wrapper sites identified during Phase 0 audit.
    TARGET_FILES = (
        "core/schema_migrations.py",
        "core/db.py",
        "core/brain_agent.py",
    )

    def test_no_bare_except_swallowing_rollback_in_target_files(self):
        """Scan each target file for `# RACE: S65` markers.  For every one
        found, the enclosing except clause MUST be sqlite3.OperationalError
        with a message-check that re-raises non-S65 errors — NOT a bare
        `except Exception: pass`."""
        violations: list[str] = []
        for rel in self.TARGET_FILES:
            path = REPO / rel
            src = path.read_text(encoding="utf-8")
            # Find every "RACE: S65" annotation.
            for m in re.finditer(r"RACE:\s*S65", src):
                # Look at the preceding ~600 chars for the surrounding handler.
                window_start = max(0, m.start() - 600)
                window = src[window_start:m.start() + 200]
                # The tightened pattern requires these two markers:
                ok_pattern = (
                    "sqlite3.OperationalError" in window
                    and "no transaction is active" in window
                    and "raise" in window
                )
                if not ok_pattern:
                    # Compute lineno for the diagnostic.
                    lineno = src[:m.start()].count("\n") + 1
                    violations.append(
                        f"{rel}:{lineno}: RACE: S65 site does not use the "
                        "tightened rollback pattern — must catch "
                        "sqlite3.OperationalError, check for \"no transaction "
                        "is active\" message, and re-raise unexpected errors."
                    )
        assert not violations, (
            "Imp-2 invariant violated.\n\n" + "\n".join(violations)
        )


# ---------------------------------------------------------------------------
# Group 6: AST — Item 1 (every migration entry is a 4-tuple)
# ---------------------------------------------------------------------------

class TestEveryMigrationHasVerifyCompanion:
    """Each entry in any `MIGRATIONS` class attribute must be a 4-element
    tuple shaped as (int_version, str_description, callable, callable).
    Verify companion is mandatory — Item 1 invariant from the auditor's
    plan v2."""

    def _migrations_lists(self) -> "list[tuple[str, list]]":
        """Return (qualified_name, MIGRATIONS_list) for every DB class
        that defines MIGRATIONS at module load time."""
        # Stub voice/audio before importing the DB modules so torchaudio
        # DLL crash on Windows doesn't kill collection.
        from tests.conftest import setup_pipeline_stubs as _stubs
        _stubs()
        from core.db import FaceDB
        from core.brain_agent import BrainDB
        from core.classifier_db import ClassifierDB
        return [
            ("FaceDB.MIGRATIONS",       FaceDB.MIGRATIONS),
            ("BrainDB.MIGRATIONS",      BrainDB.MIGRATIONS),
            ("ClassifierDB.MIGRATIONS", ClassifierDB.MIGRATIONS),
        ]

    def test_all_migrations_class_attrs_exist(self):
        """Sanity guard — each DB class MUST have a MIGRATIONS attribute,
        even if empty.  This is what the shared runner consumes."""
        for name, migrations in self._migrations_lists():
            assert isinstance(migrations, list), f"{name} must be a list"

    def test_every_entry_is_5_tuple_with_both_verify_companions(self):
        """P0.9.2: For every populated entry: (int_version, str_description,
        apply_callable, verify_post_callable, verify_present_callable).
        Phase 1 ships empty lists so this test passes trivially; Phase 2
        entries are enforced.

        Both verify functions are mandatory.  verify_post is the runner's
        post-condition assertion (raises if post-state wrong).
        verify_present is the bootstrap predicate (returns True if the
        artifact already exists on a legacy DB).  Conflating the two roles
        was the failure mode P0.9.2 was designed to prevent — both must
        exist as separate callables."""
        violations: list[str] = []
        for name, migrations in self._migrations_lists():
            for idx, entry in enumerate(migrations):
                if not isinstance(entry, tuple) or len(entry) != 5:
                    got_len = len(entry) if hasattr(entry, "__len__") else "n/a"
                    violations.append(
                        f"{name}[{idx}] is not a 5-tuple (got "
                        f"{type(entry).__name__} of length {got_len})"
                    )
                    continue
                version, description, apply_fn, verify_post, verify_present = entry
                if not isinstance(version, int):
                    violations.append(f"{name}[{idx}]: version is not int ({type(version).__name__})")
                if not isinstance(description, str):
                    violations.append(f"{name}[{idx}]: description is not str ({type(description).__name__})")
                if not callable(apply_fn):
                    violations.append(f"{name}[{idx}]: apply_fn is not callable")
                if not callable(verify_post):
                    violations.append(
                        f"{name}[{idx}]: verify_post is not callable — "
                        "every migration MUST carry a post-condition assertion (Item 1 invariant)"
                    )
                if not callable(verify_present):
                    violations.append(
                        f"{name}[{idx}]: verify_present is not callable — "
                        "every migration MUST carry a presence predicate for "
                        "bootstrap_ledger_if_unversioned (Item 1 invariant)"
                    )
        assert not violations, (
            "Item 1 invariant violated.\n\n" + "\n".join(violations)
        )


# ---------------------------------------------------------------------------
# Group 7: AST — apply_migrations uses BEGIN IMMEDIATE
# ---------------------------------------------------------------------------

class TestBootValidationLogLines:
    """P0.9.2 polish: observability log lines that Jagan's prod-DB
    validation gate consumes.  The exact phrasing is part of the contract
    — Phase 3 greenlight depends on Jagan grepping for these lines in
    his boot output.  Source-inspection + behavioral tests pin the format
    so future refactors can't silently change it."""

    def test_bootstrap_logs_legacy_db_with_stamped_count(self, capsys):
        """Legacy DB scenario — the production gate's primary signal:
        '[Schema] {label}: bootstrap stamped baseline v=1 + N
        pre-existing migration(s) as is_initial=1 (legacy DB)'."""
        conn = _fresh_conn()
        # Simulate legacy DB with 2 pre-existing artifacts.
        conn.execute("CREATE TABLE t2 (id INTEGER)")
        conn.execute("CREATE TABLE t3 (id INTEGER)")
        conn.commit()
        migrations = _make_fixture_migrations(3)  # v=2, v=3, v=4
        _sm.init_ledger(conn)
        capsys.readouterr()  # clear any prior output
        _sm.bootstrap_ledger_if_unversioned(
            conn, baseline_description="legacy DB",
            migrations=migrations, db_label="faces.db",
        )
        out = capsys.readouterr().out
        assert "[Schema] faces.db:" in out
        assert "bootstrap stamped baseline v=1" in out
        # Only 2 of 3 fixture artifacts were pre-created (t2, t3 — not t4).
        assert "2 pre-existing migration(s) as is_initial=1" in out
        assert "(legacy DB)" in out

    def test_bootstrap_logs_fresh_db(self, capsys):
        """Fresh DB scenario — distinct log phrasing so operator knows
        no migrations were pre-stamped."""
        conn = _fresh_conn()
        _sm.init_ledger(conn)
        capsys.readouterr()
        _sm.bootstrap_ledger_if_unversioned(
            conn, baseline_description="fresh DB", db_label="faces.db",
        )
        out = capsys.readouterr().out
        assert "[Schema] faces.db: bootstrap stamped baseline v=1" in out
        assert "(fresh DB, no pre-existing migrations to stamp)" in out

    def test_bootstrap_logs_already_versioned_noop(self, capsys):
        """Second-boot scenario — confirms idempotency.  Jagan's
        validation step requires this to fire on the second boot."""
        conn = _fresh_conn()
        _sm.init_ledger(conn)
        conn.execute(
            "INSERT INTO schema_migrations "
            "(version, description, applied_at, is_initial) "
            "VALUES (1, 'pre-existing', '2025-01-01', 0)"
        )
        conn.commit()
        capsys.readouterr()
        _sm.bootstrap_ledger_if_unversioned(
            conn, baseline_description="ignored", db_label="faces.db",
        )
        out = capsys.readouterr().out
        assert "[Schema] faces.db: ledger already versioned" in out
        assert "bootstrap skipped" in out

    def test_apply_migrations_logs_zero_pending(self, capsys):
        """Steady-state log — Jagan's primary success signal: the runner
        had nothing to do because bootstrap stamped everything."""
        conn = _fresh_conn()
        _sm.init_ledger(conn)
        migrations = _make_fixture_migrations(3)
        # Pre-stamp all migrations (simulating a fresh-boot post-bootstrap state).
        for v, desc, _a, _vp, _vpr in migrations:
            conn.execute(
                "INSERT INTO schema_migrations "
                "(version, description, applied_at, is_initial) "
                "VALUES (?, ?, '2025-01-01', 1)",
                (v, desc),
            )
        conn.commit()
        capsys.readouterr()
        _sm.apply_migrations(conn, migrations, db_label="faces.db")
        out = capsys.readouterr().out
        assert "[Schema] faces.db: apply_migrations ran 0 pending" in out
        assert "3 known migration(s) all up-to-date" in out

    def test_apply_migrations_logs_applied_versions(self, capsys):
        """When the runner DOES apply migrations, it lists the versions
        — Phase 3 cleanup MUST NOT see this line on a steady-state boot
        (would mean a previously-stamped migration got somehow re-run)."""
        conn = _fresh_conn()
        _sm.init_ledger(conn)
        migrations = _make_fixture_migrations(2)  # v=2, v=3
        capsys.readouterr()
        _sm.apply_migrations(conn, migrations, db_label="faces.db")
        out = capsys.readouterr().out
        assert "[Schema] faces.db: apply_migrations ran 2 migration(s)" in out
        assert "v=2,3" in out


class TestRunnerUsesBeginImmediate:
    def test_apply_migrations_body_uses_begin_immediate(self):
        """Source-inspection ratchet: the runner MUST use 'BEGIN IMMEDIATE'.
        A future refactor that drops this would let Python's auto-BEGIN use
        DEFERRED locks and reintroduce the conflict Imp-1 was supposed to
        prevent."""
        src = inspect.getsource(_sm.apply_migrations)
        assert "BEGIN IMMEDIATE" in src, (
            "apply_migrations must issue explicit BEGIN IMMEDIATE for its "
            "transaction; without it, lock-acquisition semantics regress."
        )


# ---------------------------------------------------------------------------
# P0.9.3 Phase 3 cleanup invariants — the safety-net inline ALTERs have been
# deleted; these tests structurally lock the post-cleanup state so a future
# refactor can't reintroduce the idempotency-via-try/except antipattern or
# add a stray ALTER outside the migration runner.
# ---------------------------------------------------------------------------

class TestNoIdempotencyTryExceptOutsideRunner:
    """Phase 3 invariant: no `try: ALTER/CREATE ...; except
    sqlite3.OperationalError: pass` idempotency-pattern lives in
    core/db.py or core/brain_agent.py.

    Rationale: pre-P0.9 these tried to add columns idempotently by
    swallowing 'duplicate column' errors.  Now the migration runner
    owns idempotency via the version-set check in apply_migrations and
    the PRAGMA-guarded checks inside `_m_*_apply` functions.  Re-
    introducing the bare try/except pattern outside the runner would
    silently swallow disk-full / lock-contention / schema-mismatch
    OperationalErrors — exactly the failure mode P0.4 was designed to
    prevent."""

    TARGET_FILES = (
        "core/db.py",
        "core/brain_agent.py",
    )

    def test_no_idempotency_alter_try_except_in_target_files(self):
        violations: list[str] = []
        for rel in self.TARGET_FILES:
            path = REPO / rel
            src = path.read_text(encoding="utf-8")
            tree = ast.parse(src)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Try):
                    continue
                # Does any handler catch sqlite3.OperationalError?
                catches_op = False
                for h in node.handlers:
                    if h.type is None:
                        continue
                    name = ast.unparse(h.type)
                    if "OperationalError" in name:
                        catches_op = True
                        break
                if not catches_op:
                    continue
                # Is the body a single ALTER/CREATE execute?
                if len(node.body) != 1:
                    continue
                body_stmt = node.body[0]
                if not isinstance(body_stmt, ast.Expr):
                    continue
                call = body_stmt.value
                if not isinstance(call, ast.Call):
                    continue
                # Check the SQL string.
                sql_arg = None
                if call.args:
                    a0 = call.args[0]
                    if isinstance(a0, ast.Constant) and isinstance(a0.value, str):
                        sql_arg = a0.value
                    elif isinstance(a0, ast.JoinedStr):
                        sql_arg = ast.unparse(a0)
                if sql_arg is None:
                    continue
                upper = sql_arg.upper()
                if "ALTER TABLE" in upper or "CREATE INDEX" in upper:
                    # Is the handler body just `pass` (the idempotency
                    # antipattern) — or does it re-raise / log+raise?
                    for h in node.handlers:
                        if "OperationalError" not in ast.unparse(h.type or ast.Name(id="")):
                            continue
                        if len(h.body) == 1 and isinstance(h.body[0], ast.Pass):
                            violations.append(
                                f"{rel}:{node.lineno}: try/except "
                                "sqlite3.OperationalError: pass wrapping an "
                                f"{('ALTER TABLE' if 'ALTER TABLE' in upper else 'CREATE INDEX')} "
                                "statement.  Idempotency belongs in the migration "
                                "runner; move this into a _m_NNNN_*_apply function "
                                "in core.{faces,brain}_db_migrations."
                            )
        assert not violations, (
            "P0.9.3 invariant violated.\n\n" + "\n".join(violations)
        )


class TestNoAlterTableOutsideMigrationModules:
    """Phase 3 invariant: ALTER TABLE statements live only in the
    migration modules (core/faces_db_migrations.py +
    core/brain_db_migrations.py) and the meta-migration in
    core/schema_migrations.py (which adds is_initial to pre-P0.9
    ledgers).  Any ALTER TABLE in core/db.py or core/brain_agent.py
    after Phase 3 cleanup is a regression."""

    TARGET_FILES = (
        "core/db.py",
        "core/brain_agent.py",
    )

    def test_no_alter_table_in_db_or_brain_agent(self):
        import re as _re
        violations: list[str] = []
        for rel in self.TARGET_FILES:
            path = REPO / rel
            src = path.read_text(encoding="utf-8")
            for m in _re.finditer(r"ALTER\s+TABLE", src, _re.IGNORECASE):
                # Skip comments / docstrings.  Quick heuristic: if the
                # line starts with `#` or is wholly inside a docstring,
                # it's prose.  We check the start of the source line.
                line_start = src.rfind("\n", 0, m.start()) + 1
                line_text = src[line_start:src.find("\n", m.start())]
                stripped = line_text.lstrip()
                if stripped.startswith("#"):
                    continue
                # Docstring detection: if the match's line is between
                # a """ that opens and closes, treat as prose.  Quick &
                # imperfect — count """ occurrences before the match.
                before = src[:m.start()]
                if before.count('"""') % 2 == 1:
                    continue
                lineno = before.count("\n") + 1
                violations.append(
                    f"{rel}:{lineno}: ALTER TABLE outside the migration "
                    "modules.  Move into a _m_NNNN_*_apply function in "
                    "core.{faces,brain}_db_migrations."
                )
        assert not violations, (
            "P0.9.3 invariant violated.\n\n" + "\n".join(violations)
        )


class TestNoDestructiveOpsInMigrationBodies:
    """Phase 3 invariant: no DROP TABLE / DROP COLUMN / ALTER TABLE ...
    RENAME inside `_m_*_apply` bodies in the migration modules.  Single
    documented exemption: `_m_0010_drop_conversation_memory_apply` in
    core/faces_db_migrations.py — the legacy S24 conversation_memory
    cleanup is the ONLY destructive op in the entire schema surface,
    explicitly enumerated as a migration so the ledger records it."""

    MIGRATION_MODULES = (
        "core/faces_db_migrations.py",
        "core/brain_db_migrations.py",
    )

    DOCUMENTED_EXEMPTIONS = {
        "_m_0010_drop_conversation_memory_apply",  # S24 legacy cleanup
    }

    def test_no_destructive_ops_in_apply_bodies(self):
        import re as _re
        violations: list[str] = []
        for rel in self.MIGRATION_MODULES:
            path = REPO / rel
            src = path.read_text(encoding="utf-8")
            tree = ast.parse(src)
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if not node.name.endswith("_apply"):
                    continue
                if node.name in self.DOCUMENTED_EXEMPTIONS:
                    continue
                body_src = ast.unparse(node)
                # Look for destructive patterns inside this function body.
                for pat, label in (
                    (r"DROP\s+TABLE", "DROP TABLE"),
                    (r"DROP\s+COLUMN", "DROP COLUMN"),
                    (r"ALTER\s+TABLE\s+\w+\s+RENAME", "ALTER TABLE ... RENAME"),
                ):
                    if _re.search(pat, body_src, _re.IGNORECASE):
                        violations.append(
                            f"{rel}: {node.name}() contains a {label} "
                            "operation.  Destructive schema changes need an "
                            "explicit exemption — add the function name to "
                            "DOCUMENTED_EXEMPTIONS in "
                            "tests/test_schema_migrations.py and document "
                            "the reason in the migration's docstring."
                        )
        assert not violations, (
            "P0.9.3 invariant violated.\n\n" + "\n".join(violations)
        )

    def test_documented_exemption_actually_uses_drop(self):
        """Sanity guard — the documented exemption MUST actually contain
        the destructive op it's exempted for.  Catches typos in the
        exemption set or accidental cleanup of the migration body."""
        path = REPO / "core/faces_db_migrations.py"
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and \
                    node.name == "_m_0010_drop_conversation_memory_apply":
                body_src = ast.unparse(node)
                assert "DROP TABLE IF EXISTS conversation_memory" in body_src, (
                    "_m_0010_drop_conversation_memory_apply must contain "
                    "DROP TABLE IF EXISTS conversation_memory — that's the "
                    "whole point of the exemption."
                )
                return
        pytest.fail("_m_0010_drop_conversation_memory_apply not found")
