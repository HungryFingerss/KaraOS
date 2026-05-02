"""Tests for the new function-calling brain API."""
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


# ── Tests for TOOLS structure ─────────────────────────────────────────────────

def test_tools_are_valid_list():
    from core.brain import TOOLS
    assert isinstance(TOOLS, list)
    assert len(TOOLS) >= 4

def test_all_tools_have_required_fields():
    from core.brain import TOOLS
    for tool in TOOLS:
        assert tool["type"] == "function"
        fn = tool["function"]
        assert "name" in fn
        assert "description" in fn
        assert "parameters" in fn

def test_tool_names():
    from core.brain import TOOLS
    names = {t["function"]["name"] for t in TOOLS}
    expected = {
        "update_person_name", "update_system_name", "search_web",
        "shutdown",
    }
    assert expected.issubset(names)

def test_update_person_name_requires_name():
    from core.brain import TOOLS
    tool = next(t for t in TOOLS if t["function"]["name"] == "update_person_name")
    assert "name" in tool["function"]["parameters"]["required"]

def test_update_system_name_requires_name():
    from core.brain import TOOLS
    tool = next(t for t in TOOLS if t["function"]["name"] == "update_system_name")
    assert "name" in tool["function"]["parameters"]["required"]

def test_search_web_requires_query():
    from core.brain import TOOLS
    tool = next(t for t in TOOLS if t["function"]["name"] == "search_web")
    assert "query" in tool["function"]["parameters"]["required"]


# ── Tests for ping_together ───────────────────────────────────────────────────

async def test_ping_returns_false_when_no_api_key():
    with patch("core.brain.CHAT_API_KEY", ""):
        from core.brain import ping_together
        result = await ping_together()
        assert result is False

async def test_ping_returns_false_on_network_error():
    import httpx
    with patch("core.brain.CHAT_API_KEY", "fake-key"):
        with patch("core.brain._chat_http") as mock_http:
            mock_http.post = AsyncMock(side_effect=httpx.ConnectError("no network"))
            from core import brain
            result = await brain.ping_together()
            assert result is False


# ── Tests for ask_offline ─────────────────────────────────────────────────────

async def test_ask_offline_returns_string():
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "message": {"content": "Hello there!"}
    }
    with patch("core.brain._ollama_http") as mock_http:
        mock_http.post = AsyncMock(return_value=mock_response)
        from core.brain import ask_offline
        result = await ask_offline("hi", person_name="Jagan")
        assert isinstance(result, str)
        assert result == "Hello there!"

async def test_ask_offline_uses_recent_history_only():
    """ask_offline should only pass last 10 turns, not full history."""
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"message": {"content": "ok"}}

    long_history = [{"role": "user", "content": f"msg {i}"} for i in range(30)]
    long_history += [{"role": "assistant", "content": f"resp {i}"} for i in range(30)]

    call_args = {}
    async def capture_post(url, json=None):
        call_args["messages"] = json.get("messages", [])
        return mock_response

    with patch("core.brain._ollama_http") as mock_http:
        mock_http.post = capture_post
        from core.brain import ask_offline
        await ask_offline("new message", conversation_history=long_history)
        # Should have system prompt + at most 10 history turns + 1 user message
        assert len(call_args["messages"]) <= 12


# ── Tests for system prompt ───────────────────────────────────────────────────

def test_system_prompt_has_no_xml_tag_instructions():
    from core.brain import SYSTEM_PROMPT
    assert "<intent>" not in SYSTEM_PROMPT
    assert "<tone>" not in SYSTEM_PROMPT
    assert "<memory>" not in SYSTEM_PROMPT
    assert "intent must be exactly one of" not in SYSTEM_PROMPT

def test_system_prompt_has_no_search_signal_instruction():
    from core.brain import SYSTEM_PROMPT
    assert "[SEARCH:" not in SYSTEM_PROMPT

def test_build_system_prompt_injects_system_name():
    from core.brain import _build_system_prompt
    result = _build_system_prompt("Jagan", system_name="Kara")
    assert "Kara" in result

def test_build_system_prompt_no_system_name_when_default():
    from core.brain import _build_system_prompt
    result = _build_system_prompt("Jagan", system_name="Dog")
    # Should not inject "Dog" as system name (it's the default, uninstructed)
    assert "Your name (given" not in result


# ── B1: Apostrophe-safe bare-tool regex ──────────────────────────────────────

def test_bare_tool_regex_parses_apostrophe_in_double_quoted_arg():
    """B1: args with apostrophes inside double-quoted values must parse correctly."""
    import re
    from core.brain import _BARE_TOOL_RE
    # Simulate: update_person_name(name="O'Brien")
    text = "update_person_name(name=\"O'Brien\")"
    m = _BARE_TOOL_RE.search(text)
    assert m is not None, "bare tool regex should match"
    args_raw = m.group(2)
    args = {}
    for am in re.finditer(r'(\w+)\s*=\s*(?:"([^"]*)"|\'([^\']*)\')', args_raw):
        args[am.group(1)] = am.group(2) if am.group(2) is not None else am.group(3)
    assert args.get("name") == "O'Brien"

def test_bare_tool_regex_parses_single_quoted_arg():
    """B1: args wrapped in single quotes must also parse correctly."""
    import re
    from core.brain import _BARE_TOOL_RE
    text = "update_system_name(name='Kara')"
    m = _BARE_TOOL_RE.search(text)
    assert m is not None
    args_raw = m.group(2)
    args = {}
    for am in re.finditer(r'(\w+)\s*=\s*(?:"([^"]*)"|\'([^\']*)\')', args_raw):
        args[am.group(1)] = am.group(2) if am.group(2) is not None else am.group(3)
    assert args.get("name") == "Kara"


# ── B2: search_memory skipped in non-streaming path ──────────────────────────

async def test_ask_together_skips_search_memory_tool(capsys):
    """B2: _ask_together must NOT add search_memory to action_tools."""
    from unittest.mock import AsyncMock, MagicMock, patch
    from core import brain

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "choices": [{
            "message": {
                "content": "Let me check.",
                "tool_calls": [{
                    "id": "tc1",
                    "function": {
                        "name": "search_memory",
                        "arguments": '{"query": "Jagan project"}'
                    }
                }]
            }
        }]
    }

    with patch("core.brain.CHAT_API_KEY", "fake-key"), \
         patch("core.brain._chat_http.post", new=AsyncMock(return_value=mock_resp)):
        text, action_tools = await brain._ask_together(
            [{"role": "user", "content": "What do you know about my project?"}],
            person_name="Jagan",
        )

    # search_memory must NOT appear in action_tools
    names = [t["name"] for t in action_tools]
    assert "search_memory" not in names
    # And the skip must be logged
    captured = capsys.readouterr()
    assert "search_memory" in captured.out
    assert "skipped" in captured.out

async def test_ask_together_action_tool_passes_through(capsys):
    """B2: real action tools (non-search_memory) still reach action_tools list."""
    from unittest.mock import AsyncMock, MagicMock, patch
    from core import brain

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "choices": [{
            "message": {
                "content": "",
                "tool_calls": [{
                    "id": "tc2",
                    "function": {
                        "name": "update_system_name",
                        "arguments": '{"name": "Kara"}'
                    }
                }]
            }
        }]
    }

    with patch("core.brain.CHAT_API_KEY", "fake-key"), \
         patch("core.brain._chat_http.post", new=AsyncMock(return_value=mock_resp)):
        text, action_tools = await brain._ask_together(
            [{"role": "user", "content": "Call me Kara"}],
            person_name="Jagan",
        )

    names = [t["name"] for t in action_tools]
    assert "update_system_name" in names
