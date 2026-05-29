"""P0.9 — uniform schema-migration runner for every SQLite DB in the project.

Generalizes the versioned-ledger pattern that `classifier_scenarios.db`
(Spec 1 / Session 122) shipped first.  Drops in to `faces.db` (FaceDB) and
`brain.db` (BrainDB), and harmonizes the existing classifier_scenarios.db
ledger via a self-evolving `init_ledger()` that idempotently adds the
`is_initial` column to pre-P0.9 ledgers.

Architectural invariants enforced (Phase 1):

  - Every migration is a 4-tuple `(version, description, apply_fn,
    verify_fn)`.  `apply_fn` mutates schema; `verify_fn` asserts the
    intended post-state.  Both run inside the same `BEGIN IMMEDIATE`
    transaction so a verify failure rolls back the apply (atomic
    migrate-or-fail).

  - Apply order is deterministic: sorted by version, applied
    sequentially.  Already-applied versions (present in ledger) are
    skipped — idempotent re-run.

  - Tightened rollback: ROLLBACK that fails with "no transaction is
    active" is suppressed (S65 race: SQLite auto-rolled the failed
    COMMIT before our explicit ROLLBACK).  Any OTHER OperationalError
    is logged and re-raised — never silently swallowed (Imp-2).

  - Bootstrap stamps `is_initial=1` on legacy DBs that pre-date the
    P0.9 ledger so future migrations don't try to re-apply the
    pre-existing baseline schema.

Connection convention (Imp-1): every sqlite3.connect() in core/*.py
that this runner is invoked against MUST be opened with
`isolation_level="IMMEDIATE"`.  Without it, Python's auto-begin uses
DEFERRED locks which conflict with the explicit BEGIN IMMEDIATE the
runner issues inside `apply_migrations()`.

Phase 1 ships the infrastructure with EMPTY `MIGRATIONS` lists per DB.
Phase 2 populates the lists with the retroactive migrations
enumerated by the P0.9 inventory.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import datetime
import sqlite3
from typing import Callable


# (version, description, apply_fn, verify_post_fn, verify_present_fn) —
# every migration carries TWO companions, each with a distinct role:
#
#   apply_fn(conn) -> None
#       The schema mutation itself.  Runs CREATE TABLE / ALTER TABLE ADD
#       COLUMN / CREATE INDEX / data backfill / etc.  Pure side-effect.
#
#   verify_post_fn(conn) -> None
#       Post-condition assertion.  Runs immediately after apply_fn inside
#       the same BEGIN IMMEDIATE transaction.  Raises AssertionError (or
#       any exception) if the post-state is wrong — that rolls back the
#       apply.  For schema migrations this typically asserts "column
#       exists"; for data-backfill migrations the post-condition is
#       stronger: "every legacy row populated, zero NULLs left."
#
#   verify_present_fn(conn) -> bool
#       Predicate.  Returns True iff the migration's artifact is ALREADY
#       present in the DB — used by bootstrap_ledger_if_unversioned to
#       stamp is_initial=1 on legacy DBs where the artifact was created
#       by the pre-P0.9 inline _migrate() before the ledger existed.
#
# Why two functions: a pure schema migration's verify_post and
# verify_present often resolve to the same SQL ("does this column
# exist?"), but their CONSUMER pattern differs (assertion vs predicate).
# For data-backfill migrations the two genuinely diverge — verify_post
# must check "is the backfill complete," verify_present must check "is
# the column there" (predates the backfill).  S107 P3A.6 and S95 3A.4
# in P0.9.2 are the canonical examples that motivated the split.
#
# Item 1 from the auditor's plan v2 is enforced structurally by the AST
# test in tests/test_schema_migrations.py — every entry MUST be a
# 5-tuple with both verify callables present.
Migration = tuple[
    int,                                       # version
    str,                                       # description
    Callable[[sqlite3.Connection], None],      # apply_fn
    Callable[[sqlite3.Connection], None],      # verify_post_fn (asserts post-state)
    Callable[[sqlite3.Connection], bool],      # verify_present_fn (True if artifact already exists)
]


def _now_iso() -> str:
    """UTC ISO-8601 timestamp for the ledger's applied_at column."""
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Ledger setup
# ---------------------------------------------------------------------------

def init_ledger(conn: sqlite3.Connection) -> None:
    """Create the `schema_migrations` table at its latest shape.

    Self-evolving: if a pre-P0.9 `schema_migrations` table exists (as in
    classifier_scenarios.db, which shipped with Spec 1 before P0.9 landed),
    this function adds the missing `is_initial` column via ALTER TABLE.
    The existing rows (real migrations that ran before P0.9) get
    is_initial=0 via the DEFAULT, which is the correct semantic — those
    migrations DID run, they weren't bootstrap stamps.

    Idempotent — safe to call at every DB open.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version     INTEGER PRIMARY KEY,
            description TEXT    NOT NULL,
            applied_at  TEXT    NOT NULL,
            is_initial  INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    cols = {r[1] for r in conn.execute("PRAGMA table_info(schema_migrations)")}
    if "is_initial" not in cols:
        # Pre-P0.9 ledger (classifier_scenarios.db ships this way from
        # Spec 1 / Session 122).  ALTER is additive + has DEFAULT, so the
        # existing rows get is_initial=0 (real migrations, not bootstrap
        # stamps).  Idempotent — guarded by the PRAGMA check.
        conn.execute(
            "ALTER TABLE schema_migrations ADD COLUMN is_initial INTEGER NOT NULL DEFAULT 0"
        )
    conn.commit()


def bootstrap_ledger_if_unversioned(
    conn: sqlite3.Connection,
    *,
    baseline_description: str,
    migrations: "list[Migration] | None" = None,
    db_label: str = "unknown",
) -> bool:
    """Stamp v=1 baseline on legacy DBs that pre-date the P0.9 ledger,
    then walk `migrations` (if given) and stamp any whose artifact is
    ALREADY present.

    No-op if `schema_migrations` already has rows (e.g. classifier's
    pre-existing Spec 1 ledger).  Otherwise:

      1. Insert a v=1 row marking the pre-P0.9 baseline schema:
         - `is_initial=1` if pre-existing tables found (legacy DB)
         - `is_initial=0` if no pre-existing tables (fresh DB)

      2. P0.9.2: walk `migrations` in version order.  For each
         `(version, description, _, _, verify_present)`, call
         `verify_present(conn)`.  If True, stamp the row with
         `is_initial=1` (the migration's artifact predates this
         bootstrap — typically from pre-P0.9 inline `_migrate()` paths
         that applied the ALTER before the ledger existed).  If False,
         leave unstamped so `apply_migrations()` runs it normally on the
         next boot step.

    Without the migration walk, a Phase-2-retrofitted production DB
    would crash on first boot: ledger has only v=1, runner tries v=2's
    ALTER TABLE ADD COLUMN, SQLite raises `OperationalError: duplicate
    column name`.  The walk pre-stamps those legacy artifacts so the
    runner skips them.

    Returns True iff this function inserted any rows.
    """
    ledger_count = conn.execute(
        "SELECT COUNT(*) FROM schema_migrations"
    ).fetchone()[0]
    if ledger_count > 0:
        # P0.9.2 polish: second-boot observability — confirms idempotency
        # to the operator (Jagan's prod-DB validation step needs this).
        print(
            f"[Schema] {db_label}: ledger already versioned "
            f"({ledger_count} row(s) present), bootstrap skipped"
        )
        return False

    existing_tables = {
        row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name != 'schema_migrations'"
        )
    }
    is_initial_baseline = 1 if existing_tables else 0
    conn.execute(
        "INSERT INTO schema_migrations "
        "(version, description, applied_at, is_initial) "
        "VALUES (?, ?, ?, ?)",
        (1, baseline_description, _now_iso(), is_initial_baseline),
    )

    # P0.9.2: stamp any post-baseline migrations whose artifacts already
    # exist (legacy DB had them from pre-P0.9 inline _migrate()).
    stamped_count = 0
    if migrations:
        for version, description, _apply, _vp, verify_present in sorted(
            migrations, key=lambda m: m[0]
        ):
            try:
                already_present = bool(verify_present(conn))
            except Exception as _vpe:
                # A misbehaving verify_present is loud — never silently
                # treat as "not present" because that would cause the
                # runner to re-apply on a legacy DB.
                print(
                    f"[Schema] verify_present(v{version}) raised "
                    f"{type(_vpe).__name__}: {_vpe!r} — leaving unstamped "
                    "(runner will attempt apply on next boot step)"
                )
                continue
            if already_present:
                # INSERT OR IGNORE defensively handles the edge case where
                # MIGRATIONS happens to include v=1 (which the baseline
                # stamp already wrote above).
                cur = conn.execute(
                    "INSERT OR IGNORE INTO schema_migrations "
                    "(version, description, applied_at, is_initial) "
                    "VALUES (?, ?, ?, 1)",
                    (version, description, _now_iso()),
                )
                if cur.rowcount:
                    stamped_count += 1
    conn.commit()
    # P0.9.2 polish: first-boot observability — surfaces "bootstrap
    # stamped N pre-existing migrations" so Jagan's prod-DB validation
    # gate can confirm the expected count.
    if is_initial_baseline:
        print(
            f"[Schema] {db_label}: bootstrap stamped baseline v=1 + "
            f"{stamped_count} pre-existing migration(s) as is_initial=1 "
            "(legacy DB)"
        )
    else:
        print(
            f"[Schema] {db_label}: bootstrap stamped baseline v=1 "
            f"(fresh DB, no pre-existing migrations to stamp)"
        )
    return True


# ---------------------------------------------------------------------------
# Migration runner
# ---------------------------------------------------------------------------

def apply_migrations(
    conn: sqlite3.Connection,
    migrations: "list[Migration]",
    *,
    db_label: str = "unknown",
) -> list[int]:
    """Apply each pending migration in version order under BEGIN IMMEDIATE.

    Each migration is (version, description, apply_fn, verify_fn):

      1. `apply_fn(conn)` runs the schema mutation (CREATE TABLE / ALTER
         TABLE ADD COLUMN / INSERT seed row / etc.).  Pure side-effect —
         no return value.
      2. `verify_fn(conn)` asserts the migration's intended post-state.
         Typically reads `PRAGMA table_info(...)` or `SELECT COUNT(*) FROM
         sqlite_master ...` and raises AssertionError if the post-state
         doesn't match expectations.

    Both run inside the same `BEGIN IMMEDIATE` transaction — a verify
    failure rolls back the apply.  After both succeed, the ledger row is
    inserted in the same transaction.

    Idempotency: versions already present in `schema_migrations` are
    skipped.  Safe to call at every DB open.

    Returns the list of version numbers actually applied this call (may
    be empty).

    NOTE: caller must ensure the connection was opened with
    `isolation_level="IMMEDIATE"` (Imp-1).  This runner temporarily sets
    `isolation_level=None` for the duration of each migration so the
    explicit BEGIN IMMEDIATE doesn't clash with Python's auto-BEGIN,
    then restores the previous value.
    """
    applied_versions = {
        row[0] for row in conn.execute(
            "SELECT version FROM schema_migrations"
        )
    }
    newly_applied: list[int] = []

    for version, description, apply_fn, verify_post_fn, _verify_present in sorted(
        migrations, key=lambda m: m[0]
    ):
        if version in applied_versions:
            continue

        prev_isolation = conn.isolation_level
        # Autocommit mode lets us issue explicit BEGIN/COMMIT without
        # Python's auto-BEGIN clashing (same pattern as FaceDB.transaction
        # / BrainDB.transaction in the existing codebase).
        conn.isolation_level = None
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                apply_fn(conn)
                verify_post_fn(conn)
                conn.execute(
                    "INSERT INTO schema_migrations "
                    "(version, description, applied_at, is_initial) "
                    "VALUES (?, ?, ?, 0)",
                    (version, description, _now_iso()),
                )
                conn.execute("COMMIT")
                newly_applied.append(version)
            except Exception:
                # Imp-2: tightened rollback — re-raise unexpected
                # OperationalErrors so they're never silently swallowed.
                # Only the S65 "no transaction is active" race is
                # suppressed (SQLite auto-rolled the failed COMMIT before
                # our explicit ROLLBACK could run).
                try:
                    conn.execute("ROLLBACK")
                except sqlite3.OperationalError as _rbe:
                    if "no transaction is active" not in str(_rbe).lower():
                        print(
                            f"[Schema] rollback failed unexpectedly during "
                            f"migration v{version}: {_rbe!r}"
                        )
                        raise
                    # else: # RACE: S65 — known race, suppress
                raise
        finally:
            conn.isolation_level = prev_isolation

    # P0.9.2 polish: every boot logs the runner outcome so Jagan's prod-DB
    # validation gate can confirm "apply_migrations ran 0 pending" — the
    # signal that bootstrap correctly stamped every pre-existing artifact.
    if newly_applied:
        print(
            f"[Schema] {db_label}: apply_migrations ran "
            f"{len(newly_applied)} migration(s): "
            f"v={','.join(str(v) for v in newly_applied)}"
        )
    else:
        print(
            f"[Schema] {db_label}: apply_migrations ran 0 pending "
            f"({len(migrations)} known migration(s) all up-to-date)"
        )
    return newly_applied
