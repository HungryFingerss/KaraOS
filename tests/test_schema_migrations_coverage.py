"""Branch-coverage tests for core/schema_migrations.py rollback + verify_present error paths."""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import sqlite3

import pytest

from core import schema_migrations as _sm

# ---------------------------------------------------------------------------
# Helpers (mirror tests/test_schema_migrations.py conventions)
# ---------------------------------------------------------------------------

def _fresh_conn() -> sqlite3.Connection:
    return sqlite3.connect(":memory:", isolation_level="IMMEDIATE")

def _ledger_versions(conn: sqlite3.Connection) -> list[int]:
    return [r[0] for r in conn.execute(
        "SELECT version FROM schema_migrations ORDER BY version"
    )]

class _RollbackFailingConn:
    """Wraps a real sqlite3 connection; when the runner issues ROLLBACK,
    this proxy rolls the real transaction back cleanly (so the underlying
    connection is left usable) but then raises a *simulated*
    sqlite3.OperationalError.  That drives the `except
    sqlite3.OperationalError` branch in apply_migrations with a message
    that does NOT match the S65 "no transaction is active" suppression
    guard — the only way to exercise the unexpected-rollback-error path,
    since a genuine ROLLBACK can never fail with an arbitrary message."""

    def __init__(self, real: sqlite3.Connection, rollback_error: Exception):
        self._real = real
        self._rollback_error = rollback_error

    def execute(self, sql, *args, **kwargs):
        if isinstance(sql, str) and sql.strip().upper().startswith("ROLLBACK"):
            # Leave the real connection clean before raising the simulated
            # error, so the runner's finally-block isolation_level restore
            # and the test's later close() don't trip over an open txn.
            try:
                self._real.execute("ROLLBACK")
            except sqlite3.OperationalError:
                pass
            raise self._rollback_error
        return self._real.execute(sql, *args, **kwargs)

    @property
    def isolation_level(self):
        return self._real.isolation_level

    @isolation_level.setter
    def isolation_level(self, value):
        self._real.isolation_level = value

    def __getattr__(self, name):
        return getattr(self._real, name)

# ---------------------------------------------------------------------------
# Region 1 — bootstrap_ledger_if_unversioned: verify_present raises (205-214)
# ---------------------------------------------------------------------------

class TestBootstrapVerifyPresentRaises:
    def test_verify_present_raising_leaves_migration_unstamped_and_continues(self, capsys):
        """A misbehaving verify_present during the bootstrap walk must NOT
        silently be treated as 'not present' — the except handler logs a
        loud diagnostic and continues, leaving the migration unstamped so
        the runner attempts the apply on the next boot step."""
        conn = _fresh_conn()
        # Pre-existing baseline table → legacy-DB path (is_initial_baseline=1),
        # which is exactly where a raising verify_present is a real hazard.
        conn.execute("CREATE TABLE persons (id TEXT PRIMARY KEY)")
        conn.commit()
        _sm.init_ledger(conn)

        calls: list[int] = []

        def apply_fn(c):  # never reached during bootstrap walk
            c.execute("CREATE TABLE tX (id INTEGER)")

        def verify_post(c):
            pass

        def boom_verify_present(c):
            calls.append(1)
            raise RuntimeError("verify_present exploded")

        migrations = [(2, "boom migration", apply_fn, verify_post, boom_verify_present)]

        capsys.readouterr()  # clear prior output
        inserted = _sm.bootstrap_ledger_if_unversioned(
            conn,
            baseline_description="legacy DB",
            migrations=migrations,
            db_label="faces.db",
        )

        assert inserted is True
        assert calls == [1], "verify_present must have been invoked (and raised)"
        # Only the v=1 baseline was stamped — v=2 was left unstamped.
        assert _ledger_versions(conn) == [1]

        out = capsys.readouterr().out
        assert "verify_present(v2) raised" in out
        assert "RuntimeError" in out
        assert "leaving unstamped" in out

    def test_verify_present_raising_still_stamps_other_migrations(self, capsys):
        """The continue must not abort the whole walk: a later migration
        whose verify_present returns True is still stamped."""
        conn = _fresh_conn()
        conn.execute("CREATE TABLE persons (id TEXT PRIMARY KEY)")
        # v=3's artifact already exists on the legacy DB.
        conn.execute("CREATE TABLE t3 (id INTEGER)")
        conn.commit()
        _sm.init_ledger(conn)

        def apply_fn(c):
            pass

        def verify_post(c):
            pass

        def raising_present(c):
            raise ValueError("kaboom")

        def t3_present(c) -> bool:
            return any(
                r[0] == "t3" for r in
                c.execute("SELECT name FROM sqlite_master WHERE type='table'")
            )

        migrations = [
            (2, "raises", apply_fn, verify_post, raising_present),
            (3, "t3 exists", apply_fn, verify_post, t3_present),
        ]

        _sm.bootstrap_ledger_if_unversioned(
            conn,
            baseline_description="legacy DB",
            migrations=migrations,
            db_label="faces.db",
        )

        # v=2 skipped (raised → unstamped), v=3 stamped (present) + v=1 baseline.
        assert _ledger_versions(conn) == [1, 3]
        out = capsys.readouterr().out
        assert "verify_present(v2) raised" in out
        assert "ValueError" in out

# ---------------------------------------------------------------------------
# Region 2 — apply_migrations rollback handler (322-328) + S65 suppress branch
# ---------------------------------------------------------------------------

class TestApplyMigrationsRollbackHandler:
    def test_unexpected_rollback_error_is_logged_and_reraised(self, capsys):
        """If ROLLBACK itself fails with an OperationalError that is NOT the
        S65 'no transaction is active' race, the runner MUST log it and
        re-raise it (never silently swallow — Imp-2)."""
        real = _fresh_conn()
        _sm.init_ledger(real)
        proxy = _RollbackFailingConn(
            real, sqlite3.OperationalError("disk I/O error")
        )

        def apply_fn(c):
            raise RuntimeError("apply boom")

        def verify_post(c):
            pass

        def verify_present(c) -> bool:
            return False

        migrations = [(2, "boom", apply_fn, verify_post, verify_present)]

        capsys.readouterr()
        with pytest.raises(sqlite3.OperationalError, match="disk"):
            _sm.apply_migrations(proxy, migrations, db_label="faces.db")

        out = capsys.readouterr().out
        assert "rollback failed unexpectedly during migration v2" in out
        assert "disk I/O error" in out
        # Nothing was committed to the ledger.
        assert _ledger_versions(real) == []
        real.close()

    def test_s65_race_rollback_error_is_suppressed_and_original_reraised(self, capsys):
        """The genuine S65 race: apply_fn ends the runner's transaction
        (COMMIT) then raises, so the runner's explicit ROLLBACK fails with
        'no transaction is active'.  That specific error is suppressed and
        the ORIGINAL exception propagates — never masked by the rollback
        error, and never logged as an unexpected failure."""
        conn = _fresh_conn()
        _sm.init_ledger(conn)

        def apply_fn(c):
            c.execute("CREATE TABLE zzz (id INTEGER)")
            c.execute("COMMIT")  # ends the runner's BEGIN IMMEDIATE txn
            raise RuntimeError("boom after commit")

        def verify_post(c):
            pass

        def verify_present(c) -> bool:
            return False

        migrations = [(2, "commit-then-raise", apply_fn, verify_post, verify_present)]

        capsys.readouterr()
        with pytest.raises(RuntimeError, match="boom after commit"):
            _sm.apply_migrations(conn, migrations, db_label="faces.db")

        out = capsys.readouterr().out
        # The S65 suppress branch was taken — the unexpected-error log MUST
        # NOT fire (that would mean the message check misclassified it).
        assert "rollback failed unexpectedly" not in out
        # Proof we hit the "no transaction is active" path: the COMMIT ran
        # so the table survived, and the ledger row was never inserted.
        tables = {
            r[0] for r in
            conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert "zzz" in tables
        assert _ledger_versions(conn) == []
