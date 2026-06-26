"""SB.6 Step 6 — gated-off object memory + SB.5 privacy extension (D1/PI-3/PI-4).

Focused unit net for the two new `BrainDB` surfaces — the retention-gated writer
`store_object_sighting` and the privacy-scoped reader `get_object_context` — plus
the `_m_0013` migration that adds `object_sightings.person_id` + `.privacy_level`.

The two §4 nets (`test_sb5_retention_funnel_complete.py` static partition +
`test_sb5_concierge_behavioral_net.py` behavioral 3-leg) prove `object_sightings`
is correctly classified PERSONAL and retention-gated *as a member of the partition*.
This file proves the surface's own contract in isolation:

  * D1 — the writer's TWO gates (the SB.6 `OBJECT_MEMORY_ENABLED` master flag,
    DEFAULT OFF; the SB.5 `RETENTION_MODE` ephemeral gate).
  * PI-3 — the migration columns are present on a fresh BrainDB (the §4.a
    partition scanner needs the table to be a real PERSONAL INSERT target).
  * PI-4 / no-leak — the reader composes `_visibility_clause`, so a visitor can
    never read another person's owner-only sightings.

Discipline: BrainDB is built at `tmp_path` and config is monkeypatched — NEVER the
production `data/` paths or live `core.config` module state.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import pytest

from core import config as _config
from core.config import PRIVACY_LEVEL_DEFAULT
from core.brain_agent.memory.store import BrainDB


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _fresh_brain(tmp_path) -> BrainDB:
    """Fresh BrainDB at a tmp path (NEVER production data/). The `_m_0013`
    migration runs at construction, so the returned DB already carries the
    `object_sightings.person_id` + `.privacy_level` columns."""
    return BrainDB(path=tmp_path / "brain.db")


def _enable(monkeypatch, *, retention: str) -> None:
    """Flip the SB.6 master flag ON and pin RETENTION_MODE. Both gates read
    `config.X` via live attribute access, so the monkeypatch reaches them."""
    monkeypatch.setattr(_config, "OBJECT_MEMORY_ENABLED", True)
    monkeypatch.setattr(_config, "RETENTION_MODE", retention)


def _count(bdb: BrainDB) -> int:
    return bdb._conn.execute("SELECT COUNT(*) FROM object_sightings").fetchone()[0]


def _store(bdb: BrainDB, *, person_id: str = "owner_p1") -> bool:
    """Drive one sighting for `person_id`. Returns the writer's bool result."""
    return bdb.store_object_sighting(
        "watch", 0.9, "left", 10.0, 20.0, person_id, person_context="held",
    )


# --------------------------------------------------------------------------- #
# PI-3 — migration: the columns the partition scanner depends on are present.
# --------------------------------------------------------------------------- #
def test_migration_adds_person_id_and_privacy_level(tmp_path) -> None:
    bdb = _fresh_brain(tmp_path)
    try:
        cols = {row[1] for row in bdb._conn.execute(
            "PRAGMA table_info(object_sightings)"
        ).fetchall()}
        assert "person_id" in cols, f"_m_0013 missing person_id: {sorted(cols)}"
        assert "privacy_level" in cols, f"_m_0013 missing privacy_level: {sorted(cols)}"
    finally:
        bdb._conn.close()


# --------------------------------------------------------------------------- #
# D1 — writer gate 1: the SB.6 master flag (DEFAULT OFF).
# --------------------------------------------------------------------------- #
def test_writer_noop_when_feature_disabled(tmp_path, monkeypatch) -> None:
    # Master flag OFF (the gated-off default) but retention durable: still a no-op.
    monkeypatch.setattr(_config, "OBJECT_MEMORY_ENABLED", False)
    monkeypatch.setattr(_config, "RETENTION_MODE", "durable")
    bdb = _fresh_brain(tmp_path)
    try:
        assert _store(bdb) is False, "OBJECT_MEMORY_ENABLED=False must no-op"
        assert _count(bdb) == 0, "gated-off feature must never touch the DB"
    finally:
        bdb._conn.close()


# --------------------------------------------------------------------------- #
# D1 — writer gate 2: the SB.5 retention gate (ephemeral purges).
# --------------------------------------------------------------------------- #
def test_writer_noop_when_retention_ephemeral(tmp_path, monkeypatch) -> None:
    # Master flag ON but retention ephemeral: the SB.5 gate short-circuits.
    _enable(monkeypatch, retention="ephemeral")
    bdb = _fresh_brain(tmp_path)
    try:
        assert _store(bdb) is False, "ephemeral retention must no-op the writer"
        assert _count(bdb) == 0, "no object capture under ephemeral retention"
    finally:
        bdb._conn.close()


# --------------------------------------------------------------------------- #
# D1 — writer happy path: both gates permissive (flag ON + durable) → grows.
# --------------------------------------------------------------------------- #
def test_writer_grows_when_enabled_and_durable(tmp_path, monkeypatch) -> None:
    _enable(monkeypatch, retention="durable")
    bdb = _fresh_brain(tmp_path)
    try:
        assert _store(bdb) is True, "flag on + durable must INSERT"
        assert _count(bdb) == 1, "exactly one sighting written"
    finally:
        bdb._conn.close()


# --------------------------------------------------------------------------- #
# D1 — the stored row carries the owner-only stamp the no-leak reader relies on.
# --------------------------------------------------------------------------- #
def test_stored_row_is_personal_tier_and_owner_scoped(tmp_path, monkeypatch) -> None:
    _enable(monkeypatch, retention="durable")
    bdb = _fresh_brain(tmp_path)
    try:
        _store(bdb, person_id="owner_p1")
        row = bdb._conn.execute(
            "SELECT person_id, privacy_level FROM object_sightings"
        ).fetchone()
        assert row[0] == "owner_p1", "writer must stamp person_id = the session owner"
        assert row[1] == PRIVACY_LEVEL_DEFAULT, (
            "writer must stamp the owner-only default tier so visitors can't read it"
        )
    finally:
        bdb._conn.close()


# --------------------------------------------------------------------------- #
# PI-4 — reader visibility: owner + best_friend see; visitor sees NONE (no-leak).
# --------------------------------------------------------------------------- #
def test_reader_owner_and_best_friend_see_visitor_does_not(tmp_path, monkeypatch) -> None:
    _enable(monkeypatch, retention="durable")
    bdb = _fresh_brain(tmp_path)
    try:
        _store(bdb, person_id="owner_p1")

        # best_friend (household owner) — unconditional access except system_only.
        bf = bdb.get_object_context("owner_p1", best_friend_id="owner_p1")
        assert len(bf) == 1, "best_friend must see the owner-only sighting"
        assert bf[0]["object_class"] == "watch"
        assert bf[0]["person_id"] == "owner_p1"

        # owner reading their OWN personal row as a non-best-friend (person_id match).
        own = bdb.get_object_context("owner_p1", best_friend_id=None)
        assert len(own) == 1, "owner must see their own personal sighting"

        # visitor — non-best-friend, NOT the owner: the no-leak invariant.
        visitor = bdb.get_object_context("visitor_x", best_friend_id="owner_p1")
        assert visitor == [], (
            "a visitor must NOT read another person's owner-only sightings (no-leak)"
        )
    finally:
        bdb._conn.close()


# --------------------------------------------------------------------------- #
# Reader: empty (gated-off default) table → [] for any requester; object_class filter.
# --------------------------------------------------------------------------- #
def test_reader_empty_table_returns_nothing(tmp_path) -> None:
    bdb = _fresh_brain(tmp_path)  # never wrote anything (feature off by default)
    try:
        assert bdb.get_object_context("owner_p1", best_friend_id="owner_p1") == []
    finally:
        bdb._conn.close()


def test_reader_object_class_filter_narrows(tmp_path, monkeypatch) -> None:
    _enable(monkeypatch, retention="durable")
    bdb = _fresh_brain(tmp_path)
    try:
        bdb.store_object_sighting("watch", 0.9, "left", 10.0, 20.0, "owner_p1")
        bdb.store_object_sighting("mug", 0.8, "right", 30.0, 40.0, "owner_p1")
        watches = bdb.get_object_context(
            "owner_p1", best_friend_id="owner_p1", object_class="watch"
        )
        assert len(watches) == 1, "object_class filter must narrow to the watch"
        assert watches[0]["object_class"] == "watch"
    finally:
        bdb._conn.close()
