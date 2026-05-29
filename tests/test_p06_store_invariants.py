"""P0.6 structural invariants — permanent regression guards.

These tests enforce the Store-pattern architecture across all P0.6 Stores.
They grow as sub-PRs land new Stores; at P0.6.7 they become the permanent
ratchet that prevents architectural regression.

At P0.6.1: only the Store base class exists. Tests that scan core/*_store.py
for subclasses currently collect zero concrete Stores — they pass trivially.
Each subsequent sub-PR adds a Store file; these tests auto-pick them up.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import ast
import importlib
import inspect
import pathlib
import re
import sys
import types

import pytest

REPO_ROOT   = pathlib.Path(__file__).parent.parent
CORE_DIR    = REPO_ROOT / "core"
TESTS_DIR   = REPO_ROOT / "tests"
CONFTEST_ROOT  = REPO_ROOT / "conftest.py"
CONFTEST_TESTS = TESTS_DIR / "conftest.py"

# Store module names (snake_case) added by each sub-PR.
# P0.6.1: only store_base. Sub-PRs add their store here AND in conftest.
_STORE_MODULES: list[str] = [
    "presence_store",           # P0.6.2
    "track_store",              # P0.6.2
    "conversation_store",       # P0.6.3
    "voice_gallery_store",      # P0.6.4
    "per_person_agent_store",   # P0.6.4
    "cache_store",             # P0.6.5
    "pipeline_state_store",   # P0.6.6
    "vision_frame_store",     # P0.6.7v2
    "anti_spoof_rejection_store",  # P0.S1 MED 5
]

# Mapping: store module → pipeline attribute name expected in conftest loop.
# Updated in lock-step with _STORE_MODULES by each sub-PR.
_STORE_PIPELINE_ATTR: dict[str, str] = {
    "presence_store":           "_presence_store",
    "track_store":              "_track_store",
    "conversation_store":       "_conversation_store",
    "voice_gallery_store":      "_voice_gallery_store",
    "per_person_agent_store":   "_per_person_agent_store",
    "cache_store_identity_hints":    "_identity_hints_store",     # P0.6.5
    "cache_store_query_embedding":   "_query_embedding_store",    # P0.6.5
    "cache_store_scene_block":       "_scene_block_store",        # P0.6.5
    "cache_store_classifier":        "_classifier_cache_store",   # P0.6.5
    "pipeline_state_store":   "_pipeline_state_store",
    "vision_frame_store":     "_vision_frame_store",
    "anti_spoof_rejection_store": "_anti_spoof_rejection_store",  # P0.S1 MED 5
}

# Sync-method allowlist: Store methods that ARE allowed to be sync
# (peek_*, reset, __init__, __repr__, __str__, __len__, __contains__,
#  dunder methods, is_* predicate helpers).
_SYNC_ALLOWLIST_RE = re.compile(
    r"^(?:reset|get|peek|peek_.+|is_.+|get_.+|__\w+__)$"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _iter_store_classes() -> list[tuple[str, type]]:
    """Return list of (module_name, StoreClass) for all registered Store modules."""
    from core.store_base import Store
    results = []
    for mod_name in _STORE_MODULES:
        mod = importlib.import_module(f"core.{mod_name}")
        for _, obj in inspect.getmembers(mod, inspect.isclass):
            if issubclass(obj, Store) and obj is not Store:
                results.append((mod_name, obj))
    return results


def _get_conftest_autouse_body(conftest_path: pathlib.Path) -> str:
    src = conftest_path.read_text(encoding="utf-8")
    return src


# ---------------------------------------------------------------------------
# Store base class tests
# ---------------------------------------------------------------------------

class TestStorBaseClass:
    def test_store_base_module_exists(self) -> None:
        from core import store_base  # noqa: F401

    def test_store_base_exports_store(self) -> None:
        from core.store_base import Store
        assert inspect.isclass(Store)

    def test_store_is_abstract(self) -> None:
        from core.store_base import Store
        import abc
        assert isinstance(Store, abc.ABCMeta)

    def test_store_reset_is_abstract(self) -> None:
        from core.store_base import Store
        assert "reset" in Store.__abstractmethods__

    def test_store_lock_initialized_on_concrete_subclass(self) -> None:
        import asyncio
        from core.store_base import Store

        class _Concrete(Store):
            def reset(self) -> None: pass

        obj = _Concrete()
        assert isinstance(obj._lock, asyncio.Lock)


# ---------------------------------------------------------------------------
# Per-Store structural invariants
# (these become non-trivial as sub-PRs land stores)
# ---------------------------------------------------------------------------

class TestAllStoresInheritFromBase:
    def test_all_registered_stores_inherit_from_store_base(self) -> None:
        from core.store_base import Store
        for mod_name, cls in _iter_store_classes():
            assert issubclass(cls, Store), (
                f"core.{mod_name}.{cls.__name__} does not inherit from Store. "
                "P0.6 architectural invariant: every Store must subclass Store."
            )


class TestAllStoresHaveReset:
    def test_all_registered_stores_have_reset(self) -> None:
        for mod_name, cls in _iter_store_classes():
            assert hasattr(cls, "reset") and callable(cls.reset), (
                f"core.{mod_name}.{cls.__name__} is missing a reset() method."
            )

    def test_all_registered_stores_reset_is_sync(self) -> None:
        for mod_name, cls in _iter_store_classes():
            method = getattr(cls, "reset", None)
            assert method is not None
            assert not inspect.iscoroutinefunction(method), (
                f"core.{mod_name}.{cls.__name__}.reset() must be sync "
                "(called from pytest fixture outside event loop)."
            )


class TestNoSyncMutatorsOnAnyStore:
    """No sync def methods except those on the allowlist (peek_*, reset, etc.).

    Sync mutators would bypass the lock and create race conditions.
    """
    def test_no_sync_mutators(self) -> None:
        violations: list[str] = []
        for mod_name, cls in _iter_store_classes():
            for name, method in inspect.getmembers(cls, predicate=inspect.isfunction):
                if name.startswith("_") and not name.startswith("__"):
                    continue  # skip private helpers
                if _SYNC_ALLOWLIST_RE.match(name):
                    continue  # allowed sync methods
                if inspect.iscoroutinefunction(method):
                    continue  # async — OK
                violations.append(
                    f"core.{mod_name}.{cls.__name__}.{name}() is sync but "
                    "not on the allowlist. Add 'async' or prefix with 'peek_'."
                )
        assert not violations, "\n".join(violations)


# ---------------------------------------------------------------------------
# M2 — autouse fixture coverage meta-test
#
# For each registered Store module, verifies that both conftest.py files
# contain the corresponding _<attr_name> store reset in their autouse fixture.
# Catches the "added an 8th Store and forgot to update conftest" failure mode.
# ---------------------------------------------------------------------------

class TestAutouseFixtureCoversEveryStore:
    @pytest.mark.parametrize("mod_name,attr_name", list(_STORE_PIPELINE_ATTR.items()))
    def test_root_conftest_covers_store(
        self, mod_name: str, attr_name: str
    ) -> None:
        body = _get_conftest_autouse_body(CONFTEST_ROOT)
        assert f'"{attr_name}"' in body or f"'{attr_name}'" in body, (
            f"Root conftest.py autouse fixture does not cover '{attr_name}' "
            f"(from core.{mod_name}). Add it to the _STORE_NAMES loop in "
            f"conftest.py._reset_pipeline_state_between_tests."
        )

    @pytest.mark.parametrize("mod_name,attr_name", list(_STORE_PIPELINE_ATTR.items()))
    def test_tests_conftest_covers_store(
        self, mod_name: str, attr_name: str
    ) -> None:
        body = _get_conftest_autouse_body(CONFTEST_TESTS)
        assert f'"{attr_name}"' in body or f"'{attr_name}'" in body, (
            f"tests/conftest.py autouse fixture does not cover '{attr_name}' "
            f"(from core.{mod_name}). Add it to the _STORE_NAMES loop in "
            f"tests/conftest.py._reset_pipeline_state_between_tests."
        )


# ---------------------------------------------------------------------------
# P0.6.7 closure: no legacy global declarations in pipeline.py
# (Activated at P0.6.7 — currently no-op because list is empty)
# ---------------------------------------------------------------------------

# Globals to be deleted by P0.6.7. Each sub-PR adds its globals here.
_LEGACY_GLOBALS_TO_DELETE: list[str] = [
    # Populated by P0.6.7 once all sub-PRs are complete.
    # "_persons_in_frame", "_unrecognized_tracks", ...
]


class TestNoLegacyGlobalsInPipeline:
    @pytest.mark.parametrize("global_name", _LEGACY_GLOBALS_TO_DELETE)
    def test_legacy_global_deleted(self, global_name: str) -> None:
        """P0.6 permanent invariant: legacy global must not be declared at module level."""
        source = (REPO_ROOT / "pipeline.py").read_text(encoding="utf-8")
        pattern = rf"^{re.escape(global_name)}\s*[:=]"
        matches = re.findall(pattern, source, re.MULTILINE)
        assert not matches, (
            f"P0.6.7 invariant violation: legacy global '{global_name}' is "
            f"still declared at module level in pipeline.py. "
            f"It must be deleted as part of P0.6.7 closure."
        )
