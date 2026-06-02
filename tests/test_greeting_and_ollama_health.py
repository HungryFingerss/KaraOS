"""Latency D5 (Canary #2) — greeting tools-removal + Ollama boot health-check.

D5b: `generate_greeting`'s cloud call must NOT pass tools/tool_choice (a tool-call
returns empty content → silent fallthrough to a dead Ollama → hardcoded template).
D5a: a boot health-check probes Ollama and warns LOUDLY if unreachable.

Spec: tests/pipeline_latency_fix_spec.md §2 D5 + §3 Layer 1.

NOTE (D5b honesty flag): the one-shot repro confirming the raw cloud `choices[0].message`
tool-call inference requires a live CHAT_API_KEY cloud call — deferred to the Layer-4
canary (the added empty-content log surfaces it there). The tools-removal is safe
regardless (a greeting never needs a tool), per the spec.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import ast
import asyncio
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _func_src(file_rel: str, name: str) -> str:
    src = (REPO_ROOT / file_rel).read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(src, node) or ""
    raise AssertionError(f"{name} not found in {file_rel}")


# --- D5b source ---

def test_d5b_greeting_cloud_call_drops_tools():
    """generate_greeting's cloud POST `json=` dict has no `tools`/`tool_choice` KEY.

    AST-precise (not a substring grep) so it ignores the explanatory comment and only
    inspects the actual request payload dict.
    """
    src = (REPO_ROOT / "core" / "brain.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "generate_greeting"
    )
    # Collect the string keys of every dict literal passed as a `json=` kwarg.
    json_dict_keys: set[str] = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg == "json" and isinstance(kw.value, ast.Dict):
                    for k in kw.value.keys:
                        if isinstance(k, ast.Constant) and isinstance(k.value, str):
                            json_dict_keys.add(k.value)
    assert "tools" not in json_dict_keys, (
        "generate_greeting's cloud request must NOT include a `tools` key — a tool-call "
        "returns empty content → silent fallthrough (canary #2 D5b)."
    )
    assert "tool_choice" not in json_dict_keys, (
        "generate_greeting's cloud request must NOT include a `tool_choice` key"
    )


def test_d5b_empty_cloud_content_is_logged_not_silent():
    """An empty cloud greeting is a logged failure, not a silent fallthrough."""
    body = _func_src("core/brain.py", "generate_greeting")
    assert "returned empty content" in body, (
        "empty cloud content must be logged (not a silent fallthrough to Ollama)"
    )


# --- D5b behavioral ---

class _FakeResp:
    def __init__(self, status: int, payload: dict):
        self.status_code = status
        self._payload = payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class _FakeHttp:
    def __init__(self, resp=None, raises=None):
        self._resp = resp
        self._raises = raises

    async def post(self, *a, **k):
        if self._raises:
            raise self._raises
        return self._resp

    async def get(self, *a, **k):
        if self._raises:
            raise self._raises
        return self._resp


def test_d5b_greeting_returns_cloud_content(monkeypatch):
    """With a non-empty cloud response, generate_greeting returns it (no fallthrough)."""
    import core.brain as brain

    monkeypatch.setattr(brain, "CHAT_API_KEY", "test-key", raising=False)
    payload = {"choices": [{"message": {"content": "Hey Jagan! Good to see you."}}]}
    monkeypatch.setattr(brain, "_chat_http", _FakeHttp(resp=_FakeResp(200, payload)), raising=False)

    out = asyncio.run(brain.generate_greeting("Jagan", None))
    assert out == "Hey Jagan! Good to see you.", (
        f"greeting should return the cloud content verbatim, got {out!r}"
    )


# --- D5a source ---

def test_d5a_ping_ollama_exists_and_probes_url():
    """brain.ping_ollama probes OLLAMA_URL (the /api/tags health endpoint)."""
    body = _func_src("core/brain.py", "ping_ollama")
    assert "OLLAMA_URL" in body and "/api/tags" in body, (
        "ping_ollama must probe {OLLAMA_URL}/api/tags"
    )


def test_d5a_boot_healthcheck_warns_on_unreachable_ollama():
    """run() calls ping_ollama at boot and prints a loud 'Ollama unreachable' warning."""
    run_src = _func_src("pipeline.py", "run")
    assert "ping_ollama()" in run_src, "run() must call ping_ollama() at boot"
    assert "Ollama unreachable" in run_src, "boot must print a loud Ollama-unreachable warning"
    # Non-fatal: the probe is wrapped so it never blocks boot.
    assert "non-fatal" in run_src.lower() or "skipped" in run_src.lower()


# --- D5a behavioral ---

def test_d5a_ping_ollama_false_when_unreachable(monkeypatch):
    """ping_ollama returns False (no raise) when the HTTP client errors."""
    import core.brain as brain

    monkeypatch.setattr(
        brain, "_ollama_http", _FakeHttp(raises=ConnectionError("refused")), raising=False
    )
    assert asyncio.run(brain.ping_ollama()) is False


def test_d5a_ping_ollama_true_when_reachable(monkeypatch):
    """ping_ollama returns True on a 200 from /api/tags."""
    import core.brain as brain

    monkeypatch.setattr(
        brain, "_ollama_http", _FakeHttp(resp=_FakeResp(200, {"models": []})), raising=False
    )
    assert asyncio.run(brain.ping_ollama()) is True
