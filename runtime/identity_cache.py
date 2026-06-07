# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors
"""runtime/identity_cache.py — the best-friend identity cache (P1.A1 SP-6.2).

The process-lifetime best-friend cache (_cached_bf_row / _cached_bf_db_id) + its
accessor (_get_best_friend_cached) + invalidator (_invalidate_bf_cache), relocated
VERBATIM from pipeline.py. Cross-cutting identity infra (NOT tool-dispatch-owned):
_invalidate_bf_cache is called from the relocated rename handler (flows.companion
.tools) AND stays-in-pipeline sites (conversation_turn/run); co-locating the mutable
cache globals with their accessor/invalidator in ONE module keeps reads+writes
coherent through this module's __dict__ (the SP-6.1 __globals__ lesson). Both
pipeline.py and flows.companion.tools import from here -> one shared cache.
"""
from __future__ import annotations




# Session 115 Fix 2 — best_friend row cache. db.get_best_friend() returns
# the same row every call until update_person_name fires (rare). Cached
# value short-circuits ~10ms per turn × 5+ call sites. Invalidated on
# rename success and factory reset paths. id(db) tracked so a fresh
# DB instance (test fixture) can't pick up a stale row.
_cached_bf_row: "dict | None" = None
_cached_bf_db_id: "int | None" = None
def _get_best_friend_cached(db) -> "dict | None":
    """Session 115 Fix 2 — cached `db.get_best_friend()` lookup. Same row
    every session unless update_person_name fires; cache invalidated by
    `_invalidate_bf_cache()` from the rename + factory-reset paths.

    Multi-instance safety: cached row is keyed by ``id(db)`` so a fresh
    test fixture or a post-factory-reset DB instance won't match the
    stale id and will re-query. ``None`` db → ``None`` (pre-init paths).
    """
    global _cached_bf_row, _cached_bf_db_id
    if db is None:
        return None
    db_id = id(db)
    if _cached_bf_row is not None and _cached_bf_db_id == db_id:
        return _cached_bf_row
    _cached_bf_row = db.get_best_friend()
    _cached_bf_db_id = db_id
    return _cached_bf_row
def _invalidate_bf_cache() -> None:
    """Drop the cached best_friend row. Call after update_person_name
    succeeds, after factory reset, and after first_boot_flow completes."""
    global _cached_bf_row, _cached_bf_db_id
    _cached_bf_row = None
    _cached_bf_db_id = None
