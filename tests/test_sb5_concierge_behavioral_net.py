"""SB.5 §4.b — concierge behavioral 3-leg net for the two-axis privacy gate.

Per `karaos-org-discussions/solidify-base/SB5-1-plan-v2.md` §2 (PI-B) + the
2026-06-21 architect ratification + `feedback_two_axis_gate_no_collapse_to_stricter`.
This is the BEHAVIORAL counterpart to the §4.a method-AGNOSTIC static scanner
(`test_sb5_retention_funnel_complete.py`): it actually DRIVES each of the 17
personal-data-table PRIMARY writers across three mode cells and asserts the
two axes (`enrollment_mode` / `retention_mode`) are GENUINELY INDEPENDENT —
NOT collapsed to "stricter wins".

The two nets are deliberately complementary, neither subsumes the other:
- §4.a (static) is the ONLY net that catches a SECONDARY writer this net is
  structurally blind to (e.g. `promote_shadow_to_confirmed`, which only fires on
  a mention→meet→face-confirm scenario the simulated encounter never exercises).
- §4.b (this file, behavioral) is the ONLY net that proves the gate consults the
  RIGHT axis. §4.a stays "consults SOME gate"; a writer wrongly retention-gated
  instead of enrollment-gated PASSES §4.a but FAILS §4.b's concierge leg. A
  biometric table wrongly retention-gated ships GREEN under companion
  (persistent/durable → both axes persist) AND under none (ephemeral → both
  axes purge) — the bug is invisible until a concierge deployment. The concierge
  leg is the cell that DISTINGUISHES the axes; without it "the distinction ships
  untested".

The three legs (LOCKED):
- Leg 1 — companion (persistent/durable): ALL 17 grow. The non-vacuity floor —
  proves every driver actually writes a row when both axes are permissive.
- Leg 2 — none/ephemeral: ALL 17 no-op. The full-purge floor — the `none`-mode
  "don't persist biometric" legal obligation is satisfied by the ENROLLMENT axis
  no-opping the recognition-template write directly (NOT by retention-gating it).
- Leg 3 — concierge (persistent/ephemeral): the 3 ENROLLMENT tables grow while
  the 14 RETENTION tables purge. THE distinguishing cell — a lobby robot that
  greets returning visitors by name (face/voice templates persist) while keeping
  zero conversation records (all derived data purges).

PRIMARY-writer-per-table: this net drives exactly ONE primary writer per personal
table (17 writers / 17 tables). `persons` has two writers (add_person + add_stranger);
add_person is the natural primary. The §4.a FORALL-INSERT scanner is the net that
proves no secondary writer escaped a gate.

Behavioral (not source-inspection): each spec snapshots the target table's row
count, drives the writer once, re-snapshots, and asserts grow/no-op per the leg's
cell — so a gate that is PRESENT but wired to the WRONG axis (the §4.a blind spot)
fails here.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import sqlite3
import time

import numpy as np
import pytest

import core.config as _config
from core.config import EMBEDDING_DIM
from core.db import FaceDB
from core.brain_agent.memory.store import BrainDB
from core.brain_agent.agents.extraction import Extraction

# --- The exhaustive PERSONAL partition (Plan v2 §1, Finding A) ----------------
# 3 ENROLLMENT (recognition-template) tables + 14 RETENTION (derived-data) tables
# = 17. Mirrors `PERSONAL_TABLES` in test_sb5_retention_funnel_complete.py (§4.a);
# kept as a local declaration here so a table rename in either net surfaces as a
# count/label drift in the other (the partition is the shared contract).
_ENROLLMENT_TABLES = frozenset({"persons", "embeddings", "voice_embeddings"})
_RETENTION_TABLES = frozenset(
    {
        # faces.db (4) — incl. the dotted ATTACH-alias archive move
        "conversation_log",
        "silent_observations",
        "visitor_log",
        "archive.conversation_log",
        # brain.db (10)
        "knowledge",
        "prompt_prefs",
        "household_facts",
        "inter_person_relationships",
        "shadow_persons",
        "social_mentions",
        "episodes",
        "room_summaries",
        "presence_log",
        "proactive_nudges",
    }
)


# --------------------------------------------------------------------------- #
# Construction + mode helpers
# --------------------------------------------------------------------------- #
def _set_modes(monkeypatch, *, enrollment: str, retention: str) -> None:
    """Both core/db.py and core/brain_agent/memory/store.py read `config.X_MODE`
    via live `from core import config` attribute access (the from-import-trap fix),
    so patching the module attribute reaches every gate in both files."""
    monkeypatch.setattr(_config, "ENROLLMENT_MODE", enrollment)
    monkeypatch.setattr(_config, "RETENTION_MODE", retention)


def _fresh_dbs(tmp_path):
    """Fresh FaceDB + BrainDB at tmp paths (NEVER production faces/ or data/).
    Modes MUST be set before construction (FaceDB.__init__ may consult config)."""
    fdb = FaceDB(
        db_path=str(tmp_path / "faces.db"),
        faiss_path=str(tmp_path / "faiss.index"),
    )
    bdb = BrainDB(path=tmp_path / "brain.db")
    return fdb, bdb


def _close(fdb, bdb) -> None:
    fdb._conn.close()
    bdb._conn.close()


def _count(conn, table: str) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def _count_archive(fdb) -> int:
    """archive.conversation_log lives in a SEPARATE companion DB file
    (`{stem}_conversation_archive.db`, table `conversation_log`). Read via a fresh
    short-lived connection. Defensive: 0 when the archive file/table is absent
    (legs 2/3 never trigger the archive move, so the file may not exist)."""
    apath = fdb._archive_db_path()
    if not apath.exists():
        return 0
    c = sqlite3.connect(str(apath))
    try:
        return c.execute("SELECT COUNT(*) FROM conversation_log").fetchone()[0]
    except sqlite3.OperationalError:
        return 0
    finally:
        c.close()


# --------------------------------------------------------------------------- #
# Vectors — galleries start empty, so the first insert always clears the
# diversity/centroid gates. Non-zero (FAISS NULL-vector guard skips zero vecs).
# --------------------------------------------------------------------------- #
def _face_vec():
    return np.ones(EMBEDDING_DIM, dtype=np.float32)  # add_embedding → FAISS, dim-locked


def _voice_vec():
    return np.ones(192, dtype=np.float32)  # ECAPA-TDNN dim; stored as BLOB (dim-flexible)


def _extraction():
    # Extraction(entity, entity_type, attribute, value, confidence, is_temporal,
    #            valid_for_hours[, privacy_level=PRIVACY_LEVEL_DEFAULT, person_id=None])
    return Extraction("Jagan", "person", "likes", "tea", 0.9, False, None)


# --------------------------------------------------------------------------- #
# The 17 (label, axis, count_fn, drive_fn) primary-writer specs.
# Ordered enrollment-first so `add_person` creates "p1" before the writers that
# reference it (faces.db/brain.db enforce no FK, but realistic ordering is safer).
# --------------------------------------------------------------------------- #
def _writer_specs():
    return [
        # ---- ENROLLMENT axis (3 recognition-template tables) ----
        (
            "persons",
            "enrollment",
            lambda f, b: _count(f._conn, "persons"),
            lambda f, b: f.add_person("p1", "Jagan"),
        ),
        (
            "embeddings",
            "enrollment",
            lambda f, b: _count(f._conn, "embeddings"),
            lambda f, b: f.add_embedding("p1", _face_vec(), "enrollment", anti_spoof_verdict=True),
        ),
        (
            "voice_embeddings",
            "enrollment",
            lambda f, b: _count(f._conn, "voice_embeddings"),
            lambda f, b: f.add_voice_embedding("p1", _voice_vec()),
        ),
        # ---- RETENTION axis (14 derived-data tables) — faces.db (4) ----
        (
            "conversation_log",
            "retention",
            lambda f, b: _count(f._conn, "conversation_log"),
            lambda f, b: f.log_turn("p1", "user", "hello, talk about tea"),
        ),
        (
            "silent_observations",
            "retention",
            lambda f, b: _count(f._conn, "silent_observations"),
            lambda f, b: f.update_silent_observation(_face_vec()),
        ),
        (
            "visitor_log",
            "retention",
            lambda f, b: _count(f._conn, "visitor_log"),
            lambda f, b: f.log_visitor_sighting("an unknown visitor"),
        ),
        (
            "archive.conversation_log",
            "retention",
            lambda f, b: _count_archive(f),
            # Self-contained: log a turn then sweep it to the archive DB. Under
            # durable both fire (archive grows); under ephemeral both no-op.
            lambda f, b: (
                f.log_turn("p1", "user", "archive me"),
                f.archive_old_conversation_log(cutoff_days=30, now=time.time() + 31 * 86400),
            ),
        ),
        # ---- RETENTION axis — brain.db (10) ----
        (
            "knowledge",
            "retention",
            lambda f, b: _count(b._conn, "knowledge"),
            lambda f, b: b.store_knowledge([_extraction()], 1, "p1", "extraction"),
        ),
        (
            "prompt_prefs",
            "retention",
            lambda f, b: _count(b._conn, "prompt_prefs"),
            lambda f, b: b.store_pref("p1", "brevity", "likes short answers"),
        ),
        (
            "household_facts",
            "retention",
            lambda f, b: _count(b._conn, "household_facts"),
            lambda f, b: b.store_household_fact("kitchen", "has", "kettle", "household", "p1", 0.9),
        ),
        (
            "inter_person_relationships",
            "retention",
            lambda f, b: _count(b._conn, "inter_person_relationships"),
            lambda f, b: b.store_relationship("p1", "knows", "p2", 0.9, "p1"),
        ),
        (
            "shadow_persons",
            "retention",
            lambda f, b: _count(b._conn, "shadow_persons"),
            lambda f, b: b.upsert_shadow_person("Anita", "p1", "colleague"),
        ),
        (
            "social_mentions",
            "retention",
            lambda f, b: _count(b._conn, "social_mentions"),
            lambda f, b: b.upsert_social_mention("p1", "Anita", "colleague", []),
        ),
        (
            "episodes",
            "retention",
            lambda f, b: _count(b._conn, "episodes"),
            lambda f, b: b.store_episode("p1", {"mood": "happy"}, 0.0, 1.0, 3),
        ),
        (
            "room_summaries",
            "retention",
            lambda f, b: _count(b._conn, "room_summaries"),
            lambda f, b: b.store_room_summary("room1", 0.0, 1.0, ["p1"], "talked about tea"),
        ),
        (
            "presence_log",
            "retention",
            lambda f, b: _count(b._conn, "presence_log"),
            lambda f, b: b.log_presence("p1", 0.0, 1.0),
        ),
        (
            "proactive_nudges",
            "retention",
            lambda f, b: _count(b._conn, "proactive_nudges"),
            lambda f, b: b.store_nudge("p1", "INTENTION_FOLLOWUP", "ask about thesis", 0.9, {}),
        ),
    ]


# --------------------------------------------------------------------------- #
# A0 — spec shape: the 17-table partition is well-formed (3 enrollment + 14
# retention), disjoint, and labels match the locked PERSONAL partition.
# --------------------------------------------------------------------------- #
def test_writer_specs_partition_well_formed() -> None:
    specs = _writer_specs()
    assert len(specs) == 17, "Plan v2 §1: 17 personal-table primary writers"
    enroll = {label for label, axis, _c, _d in specs if axis == "enrollment"}
    retain = {label for label, axis, _c, _d in specs if axis == "retention"}
    assert len(enroll) == 3, f"3 enrollment tables expected, got {sorted(enroll)}"
    assert len(retain) == 14, f"14 retention tables expected, got {sorted(retain)}"
    assert not (enroll & retain), "enrollment/retention axes must be disjoint"
    assert enroll == set(_ENROLLMENT_TABLES), f"enrollment label drift: {sorted(enroll)}"
    assert retain == set(_RETENTION_TABLES), f"retention label drift: {sorted(retain)}"
    # axis values are exhaustively {enrollment, retention} — no third axis slipped in
    assert {axis for _l, axis, _c, _d in specs} == {"enrollment", "retention"}


# --------------------------------------------------------------------------- #
# Leg 1 — companion (persistent/durable): ALL 17 grow (non-vacuity floor)
# --------------------------------------------------------------------------- #
def test_leg1_companion_all_seventeen_grow(tmp_path, monkeypatch) -> None:
    _set_modes(monkeypatch, enrollment="persistent", retention="durable")
    fdb, bdb = _fresh_dbs(tmp_path)
    try:
        for label, axis, count_fn, drive_fn in _writer_specs():
            before = count_fn(fdb, bdb)
            drive_fn(fdb, bdb)
            after = count_fn(fdb, bdb)
            assert after > before, (
                f"companion (persistent/durable): {label} ({axis}) did NOT write a row "
                f"({before} -> {after}) — the driver is vacuous or the gate over-blocks"
            )
    finally:
        _close(fdb, bdb)


# --------------------------------------------------------------------------- #
# Leg 2 — none/ephemeral: ALL 17 no-op (full-purge floor)
# --------------------------------------------------------------------------- #
def test_leg2_none_ephemeral_all_seventeen_purge(tmp_path, monkeypatch) -> None:
    _set_modes(monkeypatch, enrollment="none", retention="ephemeral")
    fdb, bdb = _fresh_dbs(tmp_path)
    try:
        for label, axis, count_fn, drive_fn in _writer_specs():
            before = count_fn(fdb, bdb)
            drive_fn(fdb, bdb)
            after = count_fn(fdb, bdb)
            assert after == before, (
                f"none/ephemeral: {label} ({axis}) wrote a row despite full purge "
                f"({before} -> {after}) — its gate did not fire"
            )
    finally:
        _close(fdb, bdb)


# --------------------------------------------------------------------------- #
# Leg 3 — concierge (persistent/ephemeral): THE distinguishing cell.
# 3 ENROLLMENT tables PERSIST (greet returning visitors by name) while 14
# RETENTION tables PURGE (zero conversation records). This is the leg the §4.a
# static scanner CANNOT prove — a biometric table wrongly retention-gated passes
# §4.a but fails HERE.
# --------------------------------------------------------------------------- #
def test_leg3_concierge_enrollment_persists_retention_purges(tmp_path, monkeypatch) -> None:
    _set_modes(monkeypatch, enrollment="persistent", retention="ephemeral")
    fdb, bdb = _fresh_dbs(tmp_path)
    try:
        grew: list[str] = []
        held: list[str] = []
        for label, axis, count_fn, drive_fn in _writer_specs():
            before = count_fn(fdb, bdb)
            drive_fn(fdb, bdb)
            after = count_fn(fdb, bdb)
            if axis == "enrollment":
                assert after > before, (
                    f"concierge (persistent/ephemeral): enrollment table {label} must PERSIST "
                    f"({before} -> {after}) — recognition template wrongly gated on retention?"
                )
                grew.append(label)
            else:
                assert after == before, (
                    f"concierge (persistent/ephemeral): retention table {label} must PURGE "
                    f"({before} -> {after}) — derived data wrongly gated on enrollment?"
                )
                held.append(label)
        # The distinction itself: exactly 3 persist, exactly 14 purge.
        assert sorted(grew) == sorted(_ENROLLMENT_TABLES), f"enrollment-persist set drift: {grew}"
        assert len(held) == 14, f"expected 14 retention tables to purge, got {len(held)}: {held}"
    finally:
        _close(fdb, bdb)
