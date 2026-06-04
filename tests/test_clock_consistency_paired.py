"""Canary #2 clock spec — auto-deriving paired-clock CONSISTENCY invariant (Direction B).

The strengthened DEADLINE-MATH AST invariant (test_no_walltime_deadline_math.py) catches
Direction A (`time.time()` *inside* the elapsed subtraction, incl. the variable-hop). It
CANNOT see Direction B: a store field written with one clock (`set_X(time.time())`) and
read against another (`time.monotonic() - peek_X()`) — there is no `time.time()` in the
subtraction; it's in the store *write*.

This invariant AUTO-DERIVES its field registry from source (Auditor PI-1 — load-bearing,
NOT a hand-list, which would inherit the exact recall-bounded completeness hole that
caused the bug). Architect-ratified design (2026-05-30):

  1. Build a receiver→class map from module-level store globals
     (`_session_store: SessionStore = SessionStore()` etc.).
  2. Parse every store class. A method that writes `<obj>.<attr> = <param>` is a SETTER
     for `(class, attr)` (param-fed clock; MULTI-FIELD — `upsert_face_recognition` sets
     both last_seen + last_recognized_at, record each). `<obj>.<attr> = time.<clock>()`
     is a DIRECT write (clock known at def). `return <obj>.<attr>` (incl. `.get(...)` /
     `IfExp`) is a GETTER for `(class, attr)`.
  3. Scan ALL call sites. For a setter call `RECV.method(arg…)` where RECV→class, resolve
     the clock of the arg bound to each written field's param (bare `time.<clock>()` OR a
     local assigned from one — the scope-local variable hop). For a getter used as a `-`
     operand whose other operand is a clock, record the read clock — the getter may be a
     direct call (`now - peek_X()`) OR a scope-local assigned from one (`x = peek_X(); now
     - x`, the GETTER-side variable hop, symmetric to the clock-side hop above; without it
     the `PresenceStore.last_seen` mono read at pipeline.py:574-575 was silently invisible).
  4. Gate PER (class, attr): write-clock(s) == read-clock(s), one consistent clock. A
     field seen with two clocks (and not in the tracked-deferred allowlist) FAILS. A
     consistent-all-wall field PASSES (e.g. `last_spoke_at` — its reads are snapshot-attr,
     its writes all wall; deferred fabric, not a live bug).

KNOWN BLIND SPOT (architect-acknowledged 2026-05-30): this invariant only sees reads via
`peek_*` getter calls on store globals + writes via setter calls. It is **blind to
dict-mediated reads** — e.g. presence timestamps copied into `persons_in_frame` dicts
(pipeline.py:3000/3418/8095) and consumed against `now` in the reconciler
(reconciler.py:126/136 vs wall `_rc_now`). So "make this invariant green" is NOT a safe
proxy for migrating a dict-woven field (presence/routing). Those fields are deferred to
the "SessionSnapshot / now-var timestamp fabric migration" follow-up and allowlisted
below; the fabric follow-up owns the dict-mediated surface. This invariant guards the
store-getter-mediated class (the #2-#6/#4 fixes + future store-mediated mismatches).

Run standalone to inspect:  python tests/test_clock_consistency_paired.py
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _in_scope_files() -> list[Path]:
    files: list[Path] = [REPO_ROOT / "pipeline.py"]
    for p in sorted((REPO_ROOT / "core").rglob("*.py")):
        if "_minifasnet" not in p.parts:
            files.append(p)
    return files


def _iter_scope_local(scope: ast.AST):
    """Yield every descendant of `scope` in its OWN lexical scope (not descending into
    nested function/class/lambda scopes). Local copy to avoid a cross-test-module import."""
    stack: list[ast.AST] = list(getattr(scope, "body", []) or [])
    _NESTED = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)
    while stack:
        node = stack.pop()
        yield node
        if isinstance(node, _NESTED):
            continue
        stack.extend(ast.iter_child_nodes(node))


def _clock_of_call(node: ast.AST) -> str | None:
    """'wall' for time.time(), 'mono' for time.monotonic(), else None."""
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "time"
        and not node.args
        and not node.keywords
    ):
        return {"time": "wall", "monotonic": "mono"}.get(node.func.attr)
    return None


def _build_receiver_class_map(files: list[Path]) -> dict[str, str]:
    """Map module-global store var name → class name (from `_x = ClassName()` /
    `_x: ClassName = ClassName()`)."""
    out: dict[str, str] = {}
    for path in files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in tree.body:  # module level only
            target = value = None
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                target, value = node.targets[0].id, node.value
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
                target, value = node.target.id, node.value
            if target and isinstance(value, ast.Call) and isinstance(value.func, ast.Name):
                out[target] = value.func.id
    return out


class _StoreModel:
    """Per (class, attr): setter methods (+param index), getter methods, direct clocks."""

    def __init__(self) -> None:
        # method_name -> list of (class, field, param_index_including_self_or_None, param_name)
        # param_index is None for keyword-only params (no stable positional index; §5.4 fix —
        # they are resolved by NAME against node.keywords at the call site).
        self.setters: dict[str, list[tuple[str, str, int | None, str]]] = {}
        # method_name -> list of (class, field)
        self.getters: dict[str, list[tuple[str, str]]] = {}
        # (class, field) -> {clocks} written directly at def-site
        self.direct: dict[tuple[str, str], set[str]] = {}
        self.fields: set[tuple[str, str]] = set()

    def build(self, files: list[Path]) -> None:
        for path in files:
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for cls in (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)):
                for m in (x for x in cls.body if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef))):
                    self._scan_method(cls.name, m)

    def _scan_method(self, cls: str, method: ast.AST) -> None:
        a = method.args  # type: ignore[attr-defined]
        # Positional params (posonly + regular, self at index 0) — resolved by call-position.
        positional = [p.arg for p in (list(getattr(a, "posonlyargs", [])) + list(a.args))]
        # Keyword-only params have NO stable positional index (§5.4 kwonly blind-spot fix):
        # they arrive in node.keywords at the call site, never in node.args. The setter model
        # MUST also store the param NAME so the call-site side can resolve them by name.
        param_names = set(positional) | {p.arg for p in a.kwonlyargs}
        for node in ast.walk(method):
            if isinstance(node, ast.Assign):
                for tgt in node.targets:
                    if not isinstance(tgt, ast.Attribute):
                        continue
                    field = tgt.attr
                    val = node.value
                    direct = _clock_of_call(val)
                    if direct is not None:
                        self.direct.setdefault((cls, field), set()).add(direct)
                        self.fields.add((cls, field))
                    elif isinstance(val, ast.Name) and val.id in param_names:
                        pidx = positional.index(val.id) if val.id in positional else None
                        self.setters.setdefault(method.name, []).append((cls, field, pidx, val.id))
                        self.fields.add((cls, field))
            elif isinstance(node, ast.Return) and node.value is not None:
                v = node.value
                attr = None
                if isinstance(v, ast.Attribute):
                    attr = v.attr
                elif isinstance(v, ast.Call) and isinstance(v.func, ast.Attribute) \
                        and isinstance(v.func.value, ast.Attribute) and v.func.attr == "get":
                    attr = v.func.value.attr  # return self._d.get(...)
                elif isinstance(v, ast.IfExp) and isinstance(v.body, ast.Attribute):
                    attr = v.body.attr        # return e._x if e else default
                if attr is not None:
                    self.getters.setdefault(method.name, []).append((cls, attr))
                    self.fields.add((cls, attr))


def _local_clock_map(scope: ast.AST) -> dict[str, str]:
    out: dict[str, str] = {}
    for node in _iter_scope_local(scope):
        if isinstance(node, ast.Assign):
            c = _clock_of_call(node.value)
            if c is not None:
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        out[t.id] = c
    return out


def _local_getter_map(
    scope: ast.AST, recv_map: dict[str, str], getters: dict[str, list[tuple[str, str]]]
) -> dict[str, list[tuple[str, str]]]:
    """Map local var name → [(class, field), …] for `var = RECV.getter(...)` assignments.

    This is the GETTER-side variable-hop, symmetric to `_local_clock_map`'s clock-side hop.
    Without it, `x = store.peek_X(); now - x` is invisible to the read-side scan (the
    subtraction operand is a Name, not a getter Call) — which silently hid the
    `PresenceStore.last_seen` wall-write/mono-read divergence (read at pipeline.py:574-575).
    """
    out: dict[str, list[tuple[str, str]]] = {}
    for node in _iter_scope_local(scope):
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and isinstance(node.value.func.value, ast.Name)
        ):
            cls = recv_map.get(node.value.func.value.id)
            fields = [(c, f) for c, f in getters.get(node.value.func.attr, []) if c == cls]
            if cls and fields:
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        out.setdefault(t.id, []).extend(fields)
    return out


def _arg_clock(arg: ast.AST, locals_map: dict[str, str]) -> str | None:
    direct = _clock_of_call(arg)
    if direct is not None:
        return direct
    if isinstance(arg, ast.Name):
        return locals_map.get(arg.id)
    return None


def _recv_class(call: ast.Call, recv_map: dict[str, str]) -> str | None:
    """Class of the receiver of `RECV.method(...)`, if RECV is a known store global."""
    if isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name):
        return recv_map.get(call.func.value.id)
    return None


def find_clock_mismatches(files: list[Path]) -> dict[str, dict]:
    """Return {`Class.attr`: {writes,reads,sites}} for fields with >1 distinct clock."""
    recv_map = _build_receiver_class_map(files)
    model = _StoreModel()
    model.build(files)

    writes: dict[tuple[str, str], set[str]] = {k: set(v) for k, v in model.direct.items()}
    reads: dict[tuple[str, str], set[str]] = {}
    sites: dict[tuple[str, str], list[str]] = {}

    def add(d, key, clock, where):
        d.setdefault(key, set()).add(clock)
        sites.setdefault(key, []).append(f"{clock}@{where}")

    for path in files:
        rel = path.relative_to(REPO_ROOT).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        scopes = [tree] + [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        for scope in scopes:
            locals_map = _local_clock_map(scope)
            getter_locals = _local_getter_map(scope, recv_map, model.getters)
            for node in _iter_scope_local(scope):
                # WRITE — setter call RECV.method(args)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    cls = _recv_class(node, recv_map)
                    if cls and node.func.attr in model.setters:
                        for s_cls, field, pidx, pname in model.setters[node.func.attr]:
                            if s_cls != cls:
                                continue
                            c = None
                            # Positional resolution (drop self). pidx is None for kwonly params.
                            if pidx is not None:
                                call_pos = pidx - 1
                                if 0 <= call_pos < len(node.args):
                                    c = _arg_clock(node.args[call_pos], locals_map)
                            # By-name resolution — the param may be passed as a keyword (ALWAYS
                            # for keyword-only params, which never land in node.args). §5.4 fix:
                            # without this a `ts=time.time()` kwarg is never resolved even though
                            # Part 1 registered the kwonly param. _arg_clock already resolves the
                            # time.time() literal + the scope-local hop, so this is pure dispatch.
                            if c is None:
                                for kw in node.keywords:
                                    if kw.arg == pname:
                                        c = _arg_clock(kw.value, locals_map)
                                        break
                            if c is not None:
                                add(writes, (cls, field), c, f"{rel}:{node.lineno}")
                # READ — subtraction with a getter call operand + a clock other-operand
                if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Sub):
                    left, right = node.left, node.right
                    for operand, other in ((left, right), (right, left)):
                        oc = _arg_clock(other, locals_map)
                        if oc is None:
                            continue
                        if isinstance(operand, ast.Call):
                            cls = _recv_class(operand, recv_map)
                            if cls and operand.func.attr in model.getters:  # type: ignore[union-attr]
                                for g_cls, field in model.getters[operand.func.attr]:
                                    if g_cls == cls:
                                        add(reads, (cls, field), oc, f"{rel}:{node.lineno}")
                        elif isinstance(operand, ast.Name) and operand.id in getter_locals:
                            # GETTER-side variable-hop: `x = store.peek_X(); now - x`
                            for g_cls, field in getter_locals[operand.id]:
                                add(reads, (g_cls, field), oc, f"{rel}:{node.lineno}")

    out: dict[str, dict] = {}
    for key in set(writes) | set(reads):
        w, r = writes.get(key, set()), reads.get(key, set())
        if w and r and len(w | r) > 1:
            out[f"{key[0]}.{key[1]}"] = {
                "writes": sorted(w), "reads": sorted(r), "sites": sorted(set(sites.get(key, [])))
            }
        elif len(w) > 1:  # write-side divergence alone is a mismatch (e.g. session last_face_seen)
            out[f"{key[0]}.{key[1]}"] = {
                "writes": sorted(w), "reads": sorted(r), "sites": sorted(set(sites.get(key, [])))
            }
    return out


# ── Tracked-deferred allowlist (architect ruling 2026-05-30) ──────────────────
# NOT a `# WALLCLOCK:` lie ("needs wall-clock forever"); this means "known mismatch,
# migrating in a tracked follow-up". Cleared by the follow-up's acceptance.
#
# EMPTY as of #5 Slice B (2026-06-04). The SessionSnapshot/now-var timestamp-fabric
# migration is complete on the store-getter-mediated surface: §5.4 strengthened this
# detector to see keyword-only setter args, and Slice B flipped every remaining wall
# writer/read of the presence/session/dispute fabric to monotonic (or split persisted
# fields with a `# WALLCLOCK:`-annotated wall companion). The four fields that carried
# transient entries across the arc — PresenceStore.last_recognized_at, SessionStore.
# last_spoke_at, SessionStore.last_face_seen, TrackStore.captured_at — are all now
# single-clock monotonic, so the inverse test (test_deferred_allowlist_entries_are_real
# _mismatches) forces them OUT. The dict-mediated reconciler read this detector is blind
# to stays guarded by tests/test_reconciler_clock_provenance.py (§5.2). Add a new entry
# only for a genuinely-deferred future cross-slice transient.
_DEFERRED_ALLOWLIST: dict[str, str] = {}


def test_clock_consistency_paired_invariant() -> None:
    """HARD GATE — every store timestamp field used in elapsed-math has ONE clock on its
    write(s) and all its read(s). A field with two clocks is a Direction-B mismatch."""
    mismatches = {
        f: info for f, info in find_clock_mismatches(_in_scope_files()).items()
        if f not in _DEFERRED_ALLOWLIST
    }
    assert not mismatches, (
        "Paired-clock CONSISTENCY violations (write-clock != read-clock per (class, field)):\n"
        + "\n".join(
            f"  {f}: writes={i['writes']} reads={i['reads']}\n    sites: {i['sites']}"
            for f, i in mismatches.items()
        )
        + "\n\nFix: migrate the field's write(s) + read(s) to ONE clock (monotonic for "
        "elapsed-math; wall + `# WALLCLOCK:` only if persisted/cross-process/displayed). "
        "If it's the deferred SessionSnapshot/now-var fabric, add a _DEFERRED_ALLOWLIST entry."
    )


def test_deferred_allowlist_entries_are_real_mismatches() -> None:
    """Inverse — every allowlist entry must STILL be a real detected mismatch. When the
    fabric follow-up migrates a field, its mismatch disappears and the stale allowlist
    entry must be removed (prevents dead allowlist config)."""
    detected = set(find_clock_mismatches(_in_scope_files()).keys())
    stale = [k for k in _DEFERRED_ALLOWLIST if k not in detected]
    assert not stale, (
        f"_DEFERRED_ALLOWLIST has stale entries no longer detected as mismatches: {stale}. "
        "The fabric follow-up resolved them — remove the allowlist entry."
    )


# ── §5.4 kwonly-setter detector self-tests (non-vacuity per §8) ───────────────
# The §5.4 fix taught find_clock_mismatches to resolve keyword-only setter args by NAME
# (Part 1 registers the kwonly param + its name; Part 2 resolves it from node.keywords).
# These self-tests prove BOTH halves are live + non-vacuous, on synthetic store modules so
# they cannot drift with production: a kwonly WALL write against a mono read is flagged, a
# kwonly MONO write is not, and a plain positional setter still resolves (no regression).

_KWONLY_WALL_SRC = '''
import time
class S:
    def set_a(self, pid, *, ts):
        self._d[pid].a = ts
    def peek_a(self, pid):
        return self._d[pid].a
_store = S()
def use():
    _store.set_a("p", ts=time.time())        # kwonly WALL write
    now = time.monotonic()
    return now - _store.peek_a("p")           # mono read
'''

_KWONLY_MONO_SRC = '''
import time
class S:
    def set_a(self, pid, *, ts):
        self._d[pid].a = ts
    def peek_a(self, pid):
        return self._d[pid].a
_store = S()
def use():
    _store.set_a("p", ts=time.monotonic())   # kwonly MONO write
    now = time.monotonic()
    return now - _store.peek_a("p")           # mono read
'''

_POSITIONAL_SRC = '''
import time
class S:
    def set_b(self, pid, ts):
        self._d[pid].b = ts
    def peek_b(self, pid):
        return self._d[pid].b
_store = S()
def use():
    _store.set_b("p", time.time())           # positional WALL write
    now = time.monotonic()
    return now - _store.peek_b("p")           # mono read
'''


def _detect_synth(monkeypatch, tmp_path, source: str) -> dict:
    """Write `source` as a synthetic store module under a fake repo root and run the
    paired-clock detector against it (monkeypatch REPO_ROOT so relative_to works)."""
    import sys
    monkeypatch.setattr(sys.modules[__name__], "REPO_ROOT", tmp_path)
    p = tmp_path / "synth_store_mod.py"
    p.write_text(source, encoding="utf-8")
    return find_clock_mismatches([p])


def test_p5_4_kwonly_wall_write_is_flagged(monkeypatch, tmp_path) -> None:
    ms = _detect_synth(monkeypatch, tmp_path, _KWONLY_WALL_SRC)
    assert "S.a" in ms, f"§5.4: kwonly wall-write vs mono-read MUST be flagged; got {ms}"
    assert "wall" in ms["S.a"]["writes"] and "mono" in ms["S.a"]["reads"]


def test_p5_4_kwonly_mono_write_not_flagged(monkeypatch, tmp_path) -> None:
    ms = _detect_synth(monkeypatch, tmp_path, _KWONLY_MONO_SRC)
    assert "S.a" not in ms, f"§5.4: kwonly mono-write + mono-read is single-clock; MUST NOT flag; got {ms}"


def test_p5_4_positional_setter_still_resolves(monkeypatch, tmp_path) -> None:
    ms = _detect_synth(monkeypatch, tmp_path, _POSITIONAL_SRC)
    assert "S.b" in ms, f"§5.4: positional wall-write vs mono-read MUST still flag (no regression); got {ms}"
    assert "wall" in ms["S.b"]["writes"] and "mono" in ms["S.b"]["reads"]


if __name__ == "__main__":
    import json
    ms = find_clock_mismatches(_in_scope_files())
    print(f"{len(ms)} field(s) with clock mismatch:")
    print(json.dumps(ms, indent=2))
