"""Coverage-to-100 campaign: exercises the uncovered lines of
core/brain_agent/_llm.py — _parse_json nested-salvage-failure (47-48),
the full _parse_json_array body (71-83), and the two _call_llm_chat guard
branches (130 no-API-key, 167 5xx HTTPStatusError). The only mock is the
httpx.AsyncClient boundary; everything else runs real and headless."""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

import httpx

import core.brain_agent._llm as _llm
from core.brain_agent._llm import _parse_json, _parse_json_array, _call_llm_chat

# ── _parse_json ────────────────────────────────────────────────────────────
def test_parse_json_salvage_success():
    # outer json.loads fails, brace-salvage recovers the {...} block
    assert _parse_json('noise {"a": 1} trailing') == {"a": 1}

def test_parse_json_salvage_still_fails_returns_none():
    # lines 47-48: outer parse fails, braces are present, but the salvaged
    # substring {invalid json here} is ALSO not valid JSON -> nested except.
    assert _parse_json("prefix {invalid json here} suffix") is None

def test_parse_json_no_braces_returns_none():
    # outer parse fails and no '{' present -> else -> None
    assert _parse_json("no object at all") is None

def test_parse_json_non_dict_top_level_returns_none():
    # line 51 isinstance(result, dict) False for scalar and array
    assert _parse_json("0") is None
    assert _parse_json("[1, 2, 3]") is None

def test_parse_json_plain_dict_success():
    assert _parse_json('{"x": true}') == {"x": True}

# ── _parse_json_array ──────────────────────────────────────────────────────
def test_parse_json_array_direct_list():
    # line 72 (direct parse success) + line 83 isinstance(result, list) True
    assert _parse_json_array("[1, 2, 3]") == [1, 2, 3]

def test_parse_json_array_non_list_top_level_returns_none():
    # line 83 isinstance False for a dict and for a scalar
    assert _parse_json_array('{"a": 1}') is None
    assert _parse_json_array("42") is None

def test_parse_json_array_salvage_success():
    # lines 73-78: outer parse fails, bracket-salvage recovers [ ... ]
    assert _parse_json_array("noise [1, 2] tail") == [1, 2]

def test_parse_json_array_salvage_still_fails_returns_none():
    # lines 79-80: outer parse fails, brackets present, salvaged
    # substring [bad array] is ALSO not valid JSON -> nested except.
    assert _parse_json_array("x [bad array] y") is None

def test_parse_json_array_no_brackets_returns_none():
    # lines 81-82: outer parse fails and no '[' present -> else -> None
    assert _parse_json_array("no brackets at all") is None

# ── _call_llm_chat: httpx boundary mocked, everything else real ────────────
class _FakeResp:
    """Minimal stand-in for an httpx.Response the code path touches."""

    def __init__(self, status_code, *, raise_status=False, json_data=None, text=""):
        self.status_code = status_code
        self._raise = raise_status
        self._json = json_data if json_data is not None else {}
        self.text = text

    def raise_for_status(self):
        if self._raise:
            req = httpx.Request("POST", "https://example.test/chat/completions")
            resp = httpx.Response(self.status_code, request=req)
            raise httpx.HTTPStatusError("status", request=req, response=resp)

    def json(self):
        return self._json

class _FakeClient:
    """Async-boundary fake for httpx.AsyncClient.post."""

    def __init__(self, resp=None):
        self._resp = resp
        self.calls = 0

    async def post(self, *args, **kwargs):
        self.calls += 1
        return self._resp

async def test_call_llm_chat_no_api_key_returns_none(monkeypatch):
    # line 130: `if not EXTRACT_API_KEY: return None` — http must never be hit
    monkeypatch.setattr(_llm, "EXTRACT_API_KEY", "")
    client = _FakeClient()
    out = await _call_llm_chat(
        client, [{"role": "user", "content": "hi"}], agent_name="CovAgent"
    )
    assert out is None
    assert client.calls == 0

async def test_call_llm_chat_5xx_httpstatuserror_returns_none(monkeypatch):
    # line 167: 5xx -> resp.raise_for_status() raises httpx.HTTPStatusError,
    # caught as `last_exc = e`; with max_retries=0 the loop exhausts and the
    # helper logs + returns None (no real sleep incurred).
    monkeypatch.setattr(_llm, "EXTRACT_API_KEY", "test-key")
    client = _FakeClient(resp=_FakeResp(500, raise_status=True, text="server error"))
    out = await _call_llm_chat(
        client,
        [{"role": "user", "content": "hi"}],
        agent_name="CovAgent",
        max_retries=0,
    )
    assert out is None
    assert client.calls == 1

async def test_call_llm_chat_success_returns_content(monkeypatch):
    # Real happy path through the mocked boundary — anchors that the 5xx and
    # no-key branches are genuine deviations, not the only reachable shape.
    monkeypatch.setattr(_llm, "EXTRACT_API_KEY", "test-key")
    good = _FakeResp(
        200,
        json_data={"choices": [{"message": {"content": "hello"}}]},
    )
    client = _FakeClient(resp=good)
    out = await _call_llm_chat(
        client,
        [{"role": "user", "content": "hi"}],
        agent_name="CovAgent",
        max_retries=0,
    )
    assert out == "hello"
    assert client.calls == 1
