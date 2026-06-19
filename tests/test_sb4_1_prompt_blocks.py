# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors
"""SB.4.1 — the PROMPT_BLOCKS registry test battery (T1-T11).

Plan v1 §8. This file lands incrementally with the §11 build order:

- Step 2 (THIS commit): T1 (stable-prefix byte-golden, FINDING-D tri-state) +
  T2 (prefix-hash / cache-key) + T5 (phase partition). The stable builder
  (`render_session_stable_prefix`) is rewired to iterate the `stable` slice.
- Step 3: T1 (full prompt) + T9 (SCENE registry-controlled) + T10 (no
  double-render) once `_build_system_prompt` iterates the dynamic slice.
- Step 4: T3 (SAFETY closure) + T4 (clone-subset order) + the non-vacuity RED
  battery (T2 mis-tag, T10 double-render, T11 reverted-raw-append).

GOLDEN-TEST-FIRST (Plan v1 §8 / §9): T1 captures the rendered stable prefix of
the UNMODIFIED `render_session_stable_prefix` BEFORE the §3 builder-iterates
refactor, then asserts the post-refactor output is byte-identical. The refactor
is behavior-neutral — if any rendered byte or the prefix hash changes, the
registry indirection leaked.

REGENERATION (deliberate, never under pytest):
    python tests/test_sb4_1_prompt_blocks.py
regenerates the golden files from whatever `render_session_stable_prefix`
currently emits. Run it ONCE against pristine brain.py to capture the baseline,
then NEVER again for a behavior-neutral refactor — a post-refactor regen would
mask drift. (A deliberate prompt-CONTENT change in a future cycle — SB.4.2 —
regenerates intentionally.)

FINDING D (Plan v1 §8): the battery exercises ``system_name ∈ {None, DEFAULT
("Dog"), custom ("Kara")}`` so the byte-golden covers BOTH branches of the
``system_name_prose`` block AND the ``system_identity`` ``!= DEFAULT`` gate.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import ast
import contextlib
import datetime as _dt_mod
import hashlib
import sys
import time as _time_mod
from pathlib import Path

import pytest

# Run-as-script (regen) puts tests/ on sys.path[0], not the repo root; under
# pytest the repo root is already importable. Prepend defensively (no-op under
# pytest) so `from core import brain` resolves in both modes.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core import brain  # noqa: E402
from core.profile_loader import ProfileError, _resolve, _validate_block_closure  # noqa: E402
from profiles._blocks import BLOCK_BUNDLES, BLOCK_REGISTRY, MANDATORY_BLOCKS  # noqa: E402

_GOLDEN_DIR = Path(__file__).resolve().parent / "golden" / "sb41_stable"


# --- Fixtures: FINDING-D tri-state system_name + full stable-block coverage ---
#
# Each fixture is the full kwargs of render_session_stable_prefix. The three
# cover, across the 12 stable blocks, both the on AND off path of every gated /
# runtime-conditional block (the FORALL-on-fixtures discipline, Plan v1 §8 T1):
#
#   system_name_prose : None (no render) / "Dog" (DEFAULT else-branch)
#                       / "Kara" (custom if-branch)
#   system_identity   : off (None, ==DEFAULT) / on (custom != DEFAULT)
#   known_speaker     : off (person_name None / stranger) / on (known + bf)
#   stranger_identity : on (stranger, turns>=0) / off (known, bf)
#   cross_person_priv : non-owner branch / OWNER MODE (best_friend) branch
#   identity_disputed : off / on
#   core_memory       : absent / present (SAFETY-attr + uncertain-conf branches)
#
# The stable prefix has NO datetime (those are dynamic-phase) → deterministic
# given fixed kwargs + config flags, so the golden is reproducible.
FIXTURES: tuple[tuple[str, dict], ...] = (
    (
        "none_stranger_turns2",
        dict(
            system_name=None,
            session_person_type="stranger",
            session_user_turns=2,
            identity_disputed=False,
            person_name=None,
            disputed_claimed_name=None,
            core_memory=None,
        ),
    ),
    (
        "default_name_best_friend",
        dict(
            system_name="Dog",  # DEFAULT_SYSTEM_NAME → system_name_prose else-branch
            session_person_type="best_friend",
            session_user_turns=5,
            identity_disputed=False,
            person_name="Jagan",
            disputed_claimed_name=None,
            core_memory=None,
        ),
    ),
    (
        "custom_name_known_disputed_coremem",
        dict(
            system_name="Kara",  # custom != DEFAULT → prose if-branch + system_identity on
            session_person_type="known",
            session_user_turns=3,
            identity_disputed=True,
            person_name="Lexi",
            disputed_claimed_name="Sarah",
            core_memory=[
                {"attribute": "expressed_suicidal_thoughts", "value": "true", "confidence": 1.0},
                {"attribute": "favorite_food", "value": "pasta", "confidence": 0.5},
            ],
        ),
    ),
)

# The session-invariant fixture used for the T2 cache-key (prefix-hash) check.
_T2_FIXTURE_ID = "default_name_best_friend"


def _render_prefix(kwargs: dict) -> str:
    """Render the stable prefix for one fixture via the real builder."""
    return brain.render_session_stable_prefix(**kwargs)


def _golden_path(fixture_id: str) -> Path:
    return _GOLDEN_DIR / f"{fixture_id}.txt"


# ---------------------------------------------------------------------------
# T1 — stable-prefix byte-identical golden (behavior-neutral, FINDING D)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fixture_id,kwargs", FIXTURES, ids=[f[0] for f in FIXTURES])
def test_t1_stable_prefix_byte_golden(fixture_id: str, kwargs: dict) -> None:
    gp = _golden_path(fixture_id)
    assert gp.is_file(), (
        f"Golden missing for {fixture_id}: {gp}. "
        f"Capture against pristine brain.py with:  python {Path(__file__).name}"
    )
    expected = gp.read_text(encoding="utf-8")
    actual = _render_prefix(kwargs)
    assert actual == expected, (
        f"T1 byte-golden drift for fixture {fixture_id!r} — the SB.4.1 "
        f"registry refactor changed the rendered stable prefix (must be "
        f"behavior-neutral).\n--- expected (golden, {len(expected)}B) ---\n"
        f"{expected!r}\n--- actual ({len(actual)}B) ---\n{actual!r}"
    )


# ---------------------------------------------------------------------------
# T2 — prefix-hash / cache-key preserved (PI-B; the golden is blind to it)
# ---------------------------------------------------------------------------

def test_t2_stable_prefix_hash_preserved() -> None:
    """The Together.ai KV-cache prefix hash must survive the refactor.

    A dynamic-phase block mis-tagged ``stable`` would land turn-varying content
    in the cached prefix → identical full-prompt bytes but a thrashed cache;
    this hash assertion (computed over the SAME session-invariant golden T1
    pins) catches that. Plan v1 §5.2.
    """
    fixture_id = _T2_FIXTURE_ID
    kwargs = dict(FIXTURES)[fixture_id]
    gp = _golden_path(fixture_id)
    assert gp.is_file(), (
        f"Golden missing for {fixture_id}: {gp}. "
        f"Capture with:  python {Path(__file__).name}"
    )
    # read_text normalizes CRLF→LF so the hash is immune to on-disk line-ending
    # (Windows write / git autocrlf checkout); the live render is always LF.
    golden_hash = hashlib.sha256(gp.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
    live_hash = hashlib.sha256(_render_prefix(kwargs).encode("utf-8")).hexdigest()
    assert live_hash == golden_hash, (
        f"T2 prefix-hash drift for {fixture_id!r}: cache key changed "
        f"(golden={golden_hash[:12]} live={live_hash[:12]}). A dynamic block "
        f"mis-tagged stable thrashes the Wave-4 cached prefix."
    )


# ---------------------------------------------------------------------------
# T5 — phase partition (PI-B)
# ---------------------------------------------------------------------------

_EXPECTED_STABLE = (
    "persona",
    "tool_contributions",
    "hedged_naming",
    "system_name_prose",
    "system_identity",
    "known_speaker",
    "honesty_policy",
    "cross_person_privacy",
    "tool_access",
    "stranger_identity",
    "identity_disputed",
    "core_memory",
)


def test_t5a_every_block_has_valid_phase() -> None:
    """Every registry entry declares phase ∈ {stable, dynamic}."""
    bad = {
        name: entry.get("phase")
        for name, entry in BLOCK_REGISTRY.items()
        if entry.get("phase") not in ("stable", "dynamic")
    }
    assert not bad, f"blocks with invalid phase: {bad}"


def test_t5a_stable_slice_matches_expected_set() -> None:
    """The stable phase slice (in registry order) is exactly the 12 §2 blocks."""
    stable = tuple(n for n, e in BLOCK_REGISTRY.items() if e["phase"] == "stable")
    assert stable == _EXPECTED_STABLE, (
        f"stable slice drift:\n  expected {_EXPECTED_STABLE}\n  actual   {stable}"
    )


def test_t5b_stable_builder_invokes_exactly_the_stable_render_fns(monkeypatch) -> None:
    """``render_session_stable_prefix`` invokes EXACTLY the stable slice's
    render fns via ``_RENDER_BY_NAME`` — no dynamic-phase block leaks in, no
    stable block is skipped. Spying ``_RENDER_BY_NAME`` is the §8 T10 mechanism;
    here it proves the stable-half of the §5 phase partition.

    RED before the §3 refactor (no ``_RENDER_BY_NAME`` yet) → GREEN after. The
    dynamic-half (dynamic slice ⊆ ``_build_system_prompt``) lands at Step 3.
    """
    registry = getattr(brain, "_RENDER_BY_NAME", None)
    assert registry is not None, (
        "brain._RENDER_BY_NAME missing — §3 builder-iterates refactor not landed"
    )

    expected_fns = {BLOCK_REGISTRY[n]["render_fn"] for n in _EXPECTED_STABLE}
    invoked: list[str] = []
    for fn_name, fn in list(registry.items()):
        def _wrap(*a, _fn=fn, _name=fn_name, **kw):
            invoked.append(_name)
            return _fn(*a, **kw)
        monkeypatch.setitem(registry, fn_name, _wrap)

    # Render with the full-coverage fixture so every gated stable block's
    # render fn is at least invoked (gates decide what it RETURNS, not whether
    # the builder calls it — the loop calls every active block's fn).
    _render_prefix(dict(FIXTURES)["custom_name_known_disputed_coremem"])

    invoked_set = set(invoked)
    leaked_dynamic = {
        n for n in invoked_set
        if n in {e["render_fn"] for e in BLOCK_REGISTRY.values()}
        and n not in expected_fns
    }
    assert not leaked_dynamic, f"dynamic-phase render fns invoked by stable builder: {leaked_dynamic}"
    missing = expected_fns - invoked_set
    assert not missing, f"stable render fns NOT invoked by stable builder: {missing}"


# ===========================================================================
# SB.4.1 Step 3 — full-prompt (Sections 1+2+3) battery: T1-full byte-golden,
# T9 (SCENE registry-controlled), T10 (no double-render). `_build_system_prompt`
# is rewired to iterate the BLOCK_REGISTRY `dynamic` phase-slice via
# _RENDER_BY_NAME (mirrors render_session_stable_prefix). The full golden spans
# the WHOLE prompt — stable prefix + dynamic Section 3 — so it proves the
# combined output is byte-identical across the refactor.
#
# Section 3 has THREE time-dependent surfaces, frozen for a reproducible golden:
#   - datetime + time_anchor blocks call brain.datetime.now() → _FrozenDatetime
#   - identity_evidence block reads time.monotonic()          → _FROZEN_MONO
#   - recent_rooms block reads time.time()                    → _FROZEN_WALL
# The two local `import time as _time…` blocks inside Section 3 resolve their
# attributes off sys.modules['time'] at call time, so patching the stdlib
# module's monotonic/time covers every binding (module-level + both locals).
# ===========================================================================

_FROZEN_DT = _dt_mod.datetime(2026, 6, 17, 14, 23, 7)
_FROZEN_MONO = 100_000.0
_FROZEN_WALL = 1_750_000_000.0


class _FrozenDatetime(_dt_mod.datetime):
    """datetime subclass whose .now() is pinned so the datetime + time_anchor
    blocks render deterministically. brain uses `from datetime import datetime`,
    so patching brain.datetime swaps the class those blocks call."""

    @classmethod
    def now(cls, tz=None):  # noqa: D102 - mirrors datetime.now signature
        if tz is not None:
            return _FROZEN_DT.replace(tzinfo=tz)
        return _FROZEN_DT


@contextlib.contextmanager
def _frozen_clocks():
    _orig_dt = brain.datetime
    _orig_mono = _time_mod.monotonic
    _orig_wall = _time_mod.time
    brain.datetime = _FrozenDatetime
    _time_mod.monotonic = lambda: _FROZEN_MONO
    _time_mod.time = lambda: _FROZEN_WALL
    try:
        yield
    finally:
        brain.datetime = _orig_dt
        _time_mod.monotonic = _orig_mono
        _time_mod.time = _orig_wall


_FULL_GOLDEN_DIR = Path(__file__).resolve().parent / "golden" / "sb41_full"

# Each fixture is the full kwargs of _build_system_prompt. Across the three,
# every dynamic block hits both its on AND off path (FORALL-on-fixtures, T1),
# and system_name spans {None, DEFAULT ("Dog"), custom ("Kara")} per FINDING D
# so the golden covers BOTH branches of system_name_prose + the system_identity
# != DEFAULT gate. Identity-evidence + recent-rooms timestamps are stamped
# relative to the frozen clocks so the rendered durations are stable.
FULL_FIXTURES: tuple[tuple[str, dict], ...] = (
    (
        "none_stranger_minimal",
        dict(
            person_name=None,
            system_name=None,
            vision_state=None,        # → camera UNAVAILABLE
            voice_state=None,         # → mic UNAVAILABLE
            memory_context=None,
            object_context=None,
            emotion_context=None,
            prompt_addendum=None,
            scene_block=None,
        ),
    ),
    (
        "default_name_best_friend_mid",
        dict(
            person_name="Jagan",
            system_name="Dog",        # DEFAULT_SYSTEM_NAME → prose else-branch
            vision_state={
                "session_person_type": "best_friend",
                "session_user_turns": 5,
                "identity_disputed": False,
                "face_in_frame": True,
                "person_name": "Jagan",
                "recognition_conf": 0.82,
            },
            voice_state={
                "matched_name": "Jagan",
                "matched_id": "jagan_001",
                "voice_confidence": 0.74,
                "matches_active": True,
                "gallery_size": 3,
            },
            memory_context="Jagan lives in Tirupati. Likes the Mumbai Indians.",
            object_context=None,
            emotion_context="Jagan sounds upbeat this turn.",
            prompt_addendum="Prefers brief responses.",   # no [visitor_id:] → visitor_context off
            scene_block=None,
        ),
    ),
    (
        "custom_name_known_disputed_full",
        dict(
            person_name="Lexi",
            system_name="Kara",       # custom != DEFAULT → prose if-branch + system_identity on
            vision_state={
                "session_person_type": "known",
                "session_user_turns": 3,
                "identity_disputed": True,
                "disputed_claimed_name": "Sarah",
                "face_in_frame": True,
                "person_name": "Lexi",
                "recognition_conf": 0.31,
                "active_session_count": 2,
                "identity_evidence": {
                    "face_match_conf": 0.71,
                    "face_last_seen_ts": _FROZEN_MONO - 2.0,
                    "anti_spoof_live": True,
                    "anti_spoof_score": 0.93,
                    "voice_match_conf": 0.66,
                    "voice_sample_count": 12,
                    "voice_last_heard_ts": _FROZEN_MONO - 4.0,
                },
                "room_block": "<<<ROOM>>>\nActive: Lexi (known), Jagan (best_friend)\n<<<END ROOM>>>",
                "shared_context": "<<<SHARED CONTEXT>>>\n[2m ago] Jagan: cheese cookies recipe\n<<<END SHARED CONTEXT>>>",
                "recent_room_context": {
                    "summary": "Talked about the cheese cookies recipe.",
                    "ended_at": _FROZEN_WALL - 600.0,
                    "topic_tags": ["recipe", "cooking"],
                    "safety_flags": [
                        {"name": "Lexi", "attribute": "expressed_suicidal_thoughts"},
                    ],
                },
            },
            voice_state={
                "multi_speaker": True,
                "multi_speaker_speakers": ["Lexi", "Jagan"],
                "gallery_size": 5,
            },
            memory_context="Lexi is Jagan's classmate.",
            object_context="On the table: a book, a mug.",
            emotion_context="Lexi sounds anxious.",
            prompt_addendum="[visitor_id:lexi_001][visitor_name:Lexi] Visited earlier.",
            scene_block="<<<SCENE>>>\nHere now: Lexi (known)\n<<<END SCENE>>>",
        ),
    ),
)


def _render_full(kwargs: dict) -> str:
    """Render the complete system prompt (Sections 1+2+3) under frozen clocks."""
    with _frozen_clocks():
        return brain._build_system_prompt(**kwargs)


def _full_golden_path(fixture_id: str) -> Path:
    return _FULL_GOLDEN_DIR / f"{fixture_id}.txt"


_EXPECTED_DYNAMIC = (
    "datetime",
    "sensors",
    "identity_evidence",
    "visitor_context",
    "address_decision",
    "scene",
    "room",
    "shared_context",
    "recent_rooms",
    "memory_context",
    "object_context",
    "emotion_context",
    "prompt_addendum",
    "person_name_line",
    "time_anchor",
)


# ---------------------------------------------------------------------------
# T1-full — complete-prompt byte-identical golden (behavior-neutral, FINDING D)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "fixture_id,kwargs", FULL_FIXTURES, ids=[f[0] for f in FULL_FIXTURES]
)
def test_t1_full_prompt_byte_golden(fixture_id: str, kwargs: dict) -> None:
    gp = _full_golden_path(fixture_id)
    assert gp.is_file(), (
        f"Full golden missing for {fixture_id}: {gp}. "
        f"Capture against pristine brain.py with:  python {Path(__file__).name} full"
    )
    expected = gp.read_text(encoding="utf-8")
    actual = _render_full(kwargs)
    assert actual == expected, (
        f"T1-full byte-golden drift for fixture {fixture_id!r} — the SB.4.1 "
        f"step-3 dynamic-registry refactor changed the rendered full prompt "
        f"(must be behavior-neutral).\n--- expected ({len(expected)}B) ---\n"
        f"{expected!r}\n--- actual ({len(actual)}B) ---\n{actual!r}"
    )


# ---------------------------------------------------------------------------
# T5a (dynamic) — phase partition: dynamic slice IS the 15 §2 blocks, in order
# ---------------------------------------------------------------------------

def test_t5a_dynamic_slice_matches_expected_set() -> None:
    """The dynamic phase slice (in registry order) is exactly the 15 §2 blocks,
    with `scene` at slot 6 (FINDING B)."""
    dynamic = tuple(n for n, e in BLOCK_REGISTRY.items() if e["phase"] == "dynamic")
    assert dynamic == _EXPECTED_DYNAMIC, (
        f"dynamic slice drift:\n  expected {_EXPECTED_DYNAMIC}\n  actual   {dynamic}"
    )


# ---------------------------------------------------------------------------
# T9 — SCENE block is registry-controlled (ACTIVE_BLOCKS gate, PI-C)
# ---------------------------------------------------------------------------

def test_t9_scene_block_is_registry_controlled(monkeypatch) -> None:
    """Removing 'scene' from config.ACTIVE_BLOCKS suppresses the SCENE block in
    the dynamic builder — proving Section-3 emission is ACTIVE_BLOCKS-gated (the
    clone-subset / blocks:-axis control, PI-C).

    RED before the refactor (scene was a hardcoded ``if scene_block:`` with no
    ACTIVE_BLOCKS gate) → GREEN after. cached_prefix="" isolates Section 3.
    """
    from core import config

    kwargs = dict(dict(FULL_FIXTURES)["custom_name_known_disputed_full"])
    kwargs["cached_prefix"] = ""   # skip stable prefix build → isolate Section 3
    scene_marker = kwargs["scene_block"]

    with _frozen_clocks():
        with_scene = brain._build_system_prompt(**kwargs)
    assert scene_marker in with_scene, "control: scene block should render when 'scene' is active"

    monkeypatch.setattr(
        config, "ACTIVE_BLOCKS", frozenset(config.ACTIVE_BLOCKS) - {"scene"}
    )
    with _frozen_clocks():
        without_scene = brain._build_system_prompt(**kwargs)
    assert scene_marker not in without_scene, (
        "SCENE block still rendered after removing 'scene' from ACTIVE_BLOCKS — "
        "the dynamic builder is not registry-gated (T9 RED until §3 refactor lands)"
    )


# ---------------------------------------------------------------------------
# T10 — no double-render: dynamic builder invokes each dynamic fn at most once
# ---------------------------------------------------------------------------

def test_t10_dynamic_builder_invokes_each_dynamic_fn_at_most_once(monkeypatch) -> None:
    """``_build_system_prompt`` (Section 3) invokes EXACTLY the dynamic slice's
    render fns via ``_RENDER_BY_NAME``, each at most once, and leaks NO
    stable-phase fn. cached_prefix="" skips the stable prefix builder so the spy
    sees only Section-3 invocations.

    RED before the §3 refactor (Section 3 is inline, never touches
    ``_RENDER_BY_NAME``) → GREEN after. Proves the dynamic half of the §5 phase
    partition (the stable half is locked by T5b).
    """
    registry = getattr(brain, "_RENDER_BY_NAME", None)
    assert registry is not None, (
        "brain._RENDER_BY_NAME missing — §3 builder-iterates refactor not landed"
    )

    expected_fns = {BLOCK_REGISTRY[n]["render_fn"] for n in _EXPECTED_DYNAMIC}
    stable_fns = {
        e["render_fn"] for n, e in BLOCK_REGISTRY.items() if e["phase"] == "stable"
    }
    all_registry_fns = {e["render_fn"] for e in BLOCK_REGISTRY.values()}
    invoked: list[str] = []
    for fn_name, fn in list(registry.items()):
        def _wrap(*a, _fn=fn, _name=fn_name, **kw):
            invoked.append(_name)
            return _fn(*a, **kw)
        monkeypatch.setitem(registry, fn_name, _wrap)

    kwargs = dict(dict(FULL_FIXTURES)["custom_name_known_disputed_full"])
    kwargs["cached_prefix"] = ""   # isolate Section 3 (skip stable prefix build)
    with _frozen_clocks():
        brain._build_system_prompt(**kwargs)

    invoked_registry = [n for n in invoked if n in all_registry_fns]
    leaked_stable = {n for n in invoked_registry if n in stable_fns}
    assert not leaked_stable, (
        f"stable-phase render fns invoked by dynamic builder: {leaked_stable}"
    )
    dupes = {n for n in invoked_registry if invoked_registry.count(n) > 1}
    assert not dupes, f"dynamic render fns invoked more than once: {dupes}"
    # the full-coverage fixture activates every dynamic block → all 15 fns fire
    missing = expected_fns - set(invoked_registry)
    assert not missing, f"dynamic render fns NOT invoked by dynamic builder: {missing}"


# ===========================================================================
# SB.4.1 Step 4 — closure + integrity battery: T3 (SAFETY closure),
# T4 (clone-subset order preservation), T11 (no raw `prompt +=` outside the
# registry loop). The blocks-axis loader machinery (_validate_block_closure /
# _resolve) is the SB.3xSB.4 two-axis lock; T11's AST scan is scoped to the two
# builders per FINDING-C (registry-external per-turn system_notes are out of
# scope by design).
# ===========================================================================

# ---------------------------------------------------------------------------
# T3 — SAFETY closure: a clone's `blocks:` selection can NEVER drop a SAFETY
# block. _validate_block_closure fails LOUD at load (PI-A / MANDATORY_BLOCKS).
# ---------------------------------------------------------------------------

def test_t3_companion_full_set_passes_closure() -> None:
    """The companion full set contains all MANDATORY_BLOCKS → closure is a no-op."""
    _validate_block_closure(frozenset(BLOCK_REGISTRY))  # must not raise

def test_t3_mandatory_blocks_are_exactly_the_safety_class() -> None:
    """MANDATORY_BLOCKS is EXACTLY the SAFETY-class slice of the registry — no
    drift between the per-block `class` tag and the loader's mandatory floor."""
    safety = {n for n, e in BLOCK_REGISTRY.items() if e["class"] == "SAFETY"}
    assert set(MANDATORY_BLOCKS) == safety, (
        f"MANDATORY_BLOCKS / SAFETY-class drift:\n"
        f"  MANDATORY_BLOCKS {set(MANDATORY_BLOCKS)}\n  SAFETY class    {safety}"
    )

@pytest.mark.parametrize("dropped", MANDATORY_BLOCKS, ids=list(MANDATORY_BLOCKS))
def test_t3_dropping_any_mandatory_block_fails_closure(dropped: str) -> None:
    """Dropping ANY single SAFETY block from the active set raises ProfileError,
    naming the missing block (fail-loud — never silently ships without the floor)."""
    active = frozenset(BLOCK_REGISTRY) - {dropped}
    with pytest.raises(ProfileError) as ei:
        _validate_block_closure(active)
    assert dropped in str(ei.value), (
        f"closure error must name the dropped SAFETY block {dropped!r}; got: {ei.value}"
    )

def test_t3_resolve_companion_bundle_passes_closure() -> None:
    """End-to-end loader path: `blocks: companion` resolves to the full set + clears
    closure → out['ACTIVE_BLOCKS'] is the full registry."""
    out = _resolve({"blocks": "companion"})
    assert out["ACTIVE_BLOCKS"] == frozenset(BLOCK_BUNDLES["companion"])
    assert out["ACTIVE_BLOCKS"] == frozenset(BLOCK_REGISTRY)

def test_t3_resolve_rejects_clone_dropping_a_safety_block() -> None:
    """End-to-end loader path: a clone `blocks:` list that omits a SAFETY block
    fails LOUD at _resolve (via _validate_block_closure)."""
    subset = [n for n in BLOCK_REGISTRY if n != "tool_access"]  # drop a SAFETY block
    with pytest.raises(ProfileError):
        _resolve({"blocks": subset})

# ---------------------------------------------------------------------------
# T4 — clone-subset order preservation: a clone's `blocks:` selection renders in
# REGISTRY (companion) insertion order, NOT in the order the clone listed them.
# The loader stores ACTIVE_BLOCKS as a frozenset (order DROPPED); each builder's
# `for _name, _entry in BLOCK_REGISTRY.items()` loop is the SOLE order source
# (insertion order = assembly order, _blocks.py §26-31).
# ---------------------------------------------------------------------------

def test_t4_loader_stores_subset_as_unordered_frozenset() -> None:
    """The loader drops selection order: a scrambled `blocks:` list resolves to a
    frozenset (membership only). Order is re-imposed downstream by the builder."""
    # Reverse-order list, drop two OPTIONAL (non-SAFETY) blocks so it is a real
    # subset that still passes closure.
    scrambled = [
        n for n in reversed(list(BLOCK_REGISTRY))
        if n not in ("core_memory", "object_context")
    ]
    out = _resolve({"blocks": scrambled})
    assert isinstance(out["ACTIVE_BLOCKS"], frozenset)
    assert out["ACTIVE_BLOCKS"] == frozenset(scrambled)

def test_t4_clone_subset_renders_in_registry_order_not_selection_order(monkeypatch) -> None:
    """The stable builder emits the active subset in BLOCK_REGISTRY insertion order,
    independent of how the clone listed (or the frozenset iterates) them. Spying
    _RENDER_BY_NAME (the T5b/T10 mechanism) captures the actual invocation order."""
    from core import config

    registry = getattr(brain, "_RENDER_BY_NAME", None)
    assert registry is not None, (
        "brain._RENDER_BY_NAME missing — §3 builder-iterates refactor not landed"
    )

    # A legal stable subset (keeps the SAFETY blocks), constructed in REVERSE
    # registry order to prove selection-order is NOT the emit order.
    subset_names = [
        "core_memory", "identity_disputed", "tool_access", "cross_person_privacy",
        "honesty_policy", "system_identity", "persona",
    ]
    expected_fn_order = [
        BLOCK_REGISTRY[n]["render_fn"] for n in _EXPECTED_STABLE if n in subset_names
    ]
    subset_fns = set(expected_fn_order)

    monkeypatch.setattr(config, "ACTIVE_BLOCKS", frozenset(subset_names))

    invoked: list[str] = []
    for fn_name, fn in list(registry.items()):
        def _wrap(*a, _fn=fn, _name=fn_name, **kw):
            invoked.append(_name)
            return _fn(*a, **kw)
        monkeypatch.setitem(registry, fn_name, _wrap)

    _render_prefix(dict(FIXTURES)["custom_name_known_disputed_coremem"])

    invoked_subset = [n for n in invoked if n in subset_fns]
    assert invoked_subset == expected_fn_order, (
        f"clone-subset emit order drift:\n  expected (registry order) {expected_fn_order}\n"
        f"  actual                    {invoked_subset}\n"
        "the builder must emit the active subset in BLOCK_REGISTRY insertion order, "
        "NOT in the clone's selection / frozenset-iteration order (T4)"
    )

# ---------------------------------------------------------------------------
# T11 — no raw `prompt +=` outside the registry loop (FINDING-C; AST scan scoped
# to the two builders). Every block append MUST flow through the
# `for _name, _entry in BLOCK_REGISTRY.items()` loop; a raw append outside it is
# the exact regression the §3 builder-iterates refactor removed.
# ---------------------------------------------------------------------------

_T11_BUILDER_NAMES = ("render_session_stable_prefix", "_build_system_prompt")

def _t11_builder_func_nodes() -> dict:
    src = Path(brain.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    out: dict = {}
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name in _T11_BUILDER_NAMES
        ):
            out[node.name] = node
    return out

def _t11_is_prompt_augadd(node) -> bool:
    return (
        isinstance(node, ast.AugAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == "prompt"
        and isinstance(node.op, ast.Add)
    )

def _t11_registry_loop(func_node):
    """The `for _name, _entry in BLOCK_REGISTRY.items()` loop inside the builder."""
    for node in ast.walk(func_node):
        if isinstance(node, ast.For):
            it = node.iter
            if (
                isinstance(it, ast.Call)
                and isinstance(it.func, ast.Attribute)
                and it.func.attr == "items"
                and isinstance(it.func.value, ast.Name)
                and it.func.value.id == "BLOCK_REGISTRY"
            ):
                return node
    return None

def test_t11_no_raw_prompt_append_outside_registry_loop() -> None:
    funcs = _t11_builder_func_nodes()
    assert set(funcs) == set(_T11_BUILDER_NAMES), (
        f"builder functions not found in core/brain.py: "
        f"missing {set(_T11_BUILDER_NAMES) - set(funcs)}"
    )
    for name, func in funcs.items():
        loop = _t11_registry_loop(func)
        assert loop is not None, (
            f"{name}: no `for _name, _entry in BLOCK_REGISTRY.items()` loop found "
            f"— the §3 builder-iterates loop is the only sanctioned append path"
        )
        in_loop = {id(n) for n in ast.walk(loop) if _t11_is_prompt_augadd(n)}
        all_appends = [n for n in ast.walk(func) if _t11_is_prompt_augadd(n)]
        outside = [n for n in all_appends if id(n) not in in_loop]
        assert not outside, (
            f"{name}: raw `prompt += ...` outside the BLOCK_REGISTRY loop at "
            f"line(s) {[n.lineno for n in outside]} — every block append MUST flow "
            f"through the registry loop (FINDING-C / T11)"
        )
        # Non-vacuity: the loop itself must contain the canonical `prompt += _chunk`,
        # else the scan would pass trivially on a builder that never appends.
        assert in_loop, (
            f"{name}: registry loop has no `prompt += ...` — T11 scan would be vacuous"
        )

# ---------------------------------------------------------------------------
# Regeneration (deliberate; never runs under pytest)
# ---------------------------------------------------------------------------

def _regenerate_goldens() -> None:
    _GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    for fixture_id, kwargs in FIXTURES:
        text = _render_prefix(kwargs)
        # newline="" disables newline translation → LF-only golden on every
        # platform (no Windows \r\n), so the artifact is git-clean + byte-stable.
        _golden_path(fixture_id).write_text(text, encoding="utf-8", newline="")
        print(f"[regen] wrote {fixture_id}.txt ({len(text)}B)")
    print(f"[regen] {len(FIXTURES)} golden(s) written to {_GOLDEN_DIR}")


def _regenerate_full_goldens() -> None:
    _FULL_GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    for fixture_id, kwargs in FULL_FIXTURES:
        text = _render_full(kwargs)
        # newline="" → LF-only golden on every platform (no Windows \r\n).
        _full_golden_path(fixture_id).write_text(text, encoding="utf-8", newline="")
        print(f"[regen-full] wrote {fixture_id}.txt ({len(text)}B)")
    print(f"[regen-full] {len(FULL_FIXTURES)} golden(s) written to {_FULL_GOLDEN_DIR}")


if __name__ == "__main__":
    _which = sys.argv[1] if len(sys.argv) > 1 else "all"
    if _which in ("stable", "all"):
        _regenerate_goldens()
    if _which in ("full", "all"):
        _regenerate_full_goldens()
