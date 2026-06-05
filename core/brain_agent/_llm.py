"""core/brain_agent/_llm.py — shared LLM-call + JSON-parse helpers.

Extracted VERBATIM from core/brain_agent.py (P1.A1 SP-2). Behavior-neutral;
core/brain_agent.py re-exports these symbols so all importers are unchanged.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import asyncio
import json

import httpx

from core.config import (
    EXTRACT_API_KEY,
    EXTRACT_BASE_URL,
    EXTRACT_MODEL,
    EXTRACT_MAX_RETRIES,
)


def _parse_json(raw: str) -> dict | None:
    """Parse JSON with automatic salvage of the first {…} block on failure.

    Returns a dict on success, or None on any failure.  P0.12: also returns
    None when `json.loads` succeeds but produces a non-dict JSON value
    (e.g. raw input `"0"`, `"[1,2,3]"`, `"true"`).  Type annotation said
    `dict | None` but the pre-P0.12 implementation returned whatever
    json.loads returned — Hypothesis surfaced the contract violation
    (falsifying input: `raw="0"` → returned `int(0)`).  Callers do
    `parsed.get(...)` assuming dict; a non-dict return would raise
    AttributeError at runtime.

    Also catches `RecursionError` from pathological deeply-nested JSON.
    """
    try:
        result = json.loads(raw)
    except (json.JSONDecodeError, RecursionError, ValueError):
        start = raw.find("{")
        end   = raw.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                result = json.loads(raw[start:end])
            except (json.JSONDecodeError, RecursionError, ValueError):
                return None
        else:
            return None
    return result if isinstance(result, dict) else None


def _parse_json_array(raw: str) -> list | None:
    """Parse JSON expecting a top-level array.  Returns list OR None.

    Sibling to ``_parse_json`` (P0.12.1 follow-up): some agent prompts
    legitimately expect a top-level JSON array (e.g. SocialGraphAgent's
    "list of person mentions") even when ``response_format={"type":
    "json_object"}`` is set — practical LLMs occasionally ignore the
    object-only constraint and return a raw array.  Pre-P0.12, the
    permissive ``_parse_json`` returned the list and the caller's
    ``isinstance(data, list)`` branch caught it.  P0.12 narrowed
    ``_parse_json`` to ``dict | None`` for type-contract correctness;
    this sibling restores explicit list-shape parsing for the small set
    of call sites that need it WITHOUT re-broadening the main parser.

    Same brace-salvage discipline but with ``[``/``]`` markers.  Catches
    the same DoS exceptions as ``_parse_json``.
    """
    try:
        result = json.loads(raw)
    except (json.JSONDecodeError, RecursionError, ValueError):
        start = raw.find("[")
        end   = raw.rfind("]") + 1
        if start >= 0 and end > start:
            try:
                result = json.loads(raw[start:end])
            except (json.JSONDecodeError, RecursionError, ValueError):
                return None
        else:
            return None
    return result if isinstance(result, list) else None


def _valid_until(is_temporal: bool, valid_for_hours: float | None, now: float) -> float | None:
    """Compute expiry timestamp for a temporal fact, or None if permanent."""
    if is_temporal and valid_for_hours:
        return now + valid_for_hours * 3600
    return None


# ── Bugs J + M (2026-04-20 live run) — unified LLM retry helper ───────────────
async def _call_llm_chat(
    http:          "httpx.AsyncClient",
    messages:      list[dict],
    *,
    agent_name:    str,
    max_tokens:    int             = 400,
    temperature:   float           = 0.1,
    response_format: dict | None   = None,
    timeout:       float           = 15.0,
    max_retries:   int | None      = None,
    turn_id:       int | None      = None,
) -> str | None:
    """Shared LLM chat call with retry + diagnostic logging.

    Session 69 (Bugs J + M): several agents (PromptPref, SocialGraph,
    Household, Insight, FrictionDetection, Pattern) used ad-hoc
    ``try/except Exception:`` wrappers around ``http.post``. Two failure
    modes leaked through:

      * **Bug M** (silent ReadTimeout): ``str(httpx.ReadTimeout)`` is often
        empty, producing ``[AgentName] error: ReadTimeout:`` with no detail.
      * **Bug J** (KeyError on 'choices'): provider error-shaped JSON lacks
        ``choices``, the agent catches the KeyError silently, and the turn
        is dropped without anyone noticing.

    This helper unifies the pattern from ``ExtractionAgent`` (Session 65) and
    ``EmbeddingAgent`` (Session 24 A8): retry transient errors with
    exponential backoff, propagate 4xx without retry (masks real config bugs
    if we retry), validate the response shape explicitly, and always log with
    enough detail to diagnose.

    Returns the ``choices[0].message.content`` string on success, or ``None``
    on any failure (already logged). Callers decide whether ``None`` is
    recoverable for their domain.
    """
    if not EXTRACT_API_KEY:
        return None
    retries = EXTRACT_MAX_RETRIES if max_retries is None else max_retries
    body: dict = {
        "model":       EXTRACT_MODEL,
        "messages":    messages,
        "temperature": temperature,
        "max_tokens":  max_tokens,
    }
    if response_format is not None:
        body["response_format"] = response_format
    _ctx  = f" (turn {turn_id})" if turn_id is not None else ""
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = await http.post(
                f"{EXTRACT_BASE_URL}/chat/completions",
                json=body,
                headers={"Authorization": f"Bearer {EXTRACT_API_KEY}"},
                timeout=timeout,
            )
            if 400 <= resp.status_code < 500 and resp.status_code != 429:
                # 4xx (except 429): not transient, retrying wastes budget and
                # hides real config bugs. Log and propagate None.
                print(f"[{agent_name}] HTTP {resp.status_code}{_ctx}: {resp.text[:200]}")
                return None
            resp.raise_for_status()
            data = resp.json()
            # Bug J: provider error-shaped responses lack 'choices'. Don't let
            # the KeyError become a silent except — surface it.
            if "choices" not in data or not data["choices"]:
                print(f"[{agent_name}] LLM response missing 'choices'{_ctx}: {str(data)[:200]}")
                return None
            return data["choices"][0]["message"]["content"]
        except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.NetworkError) as e:
            last_exc = e
        except httpx.HTTPStatusError as e:
            # 5xx — transient on the provider side; retry.
            last_exc = e
        except Exception as e:
            # Non-HTTP / non-network (JSON parse, unexpected shape). Not
            # retryable — log with context and bail.
            detail = str(e) or "(no detail)"
            print(f"[{agent_name}] {type(e).__name__}{_ctx}: {detail}")
            return None
        if attempt < retries:
            await asyncio.sleep(2 ** attempt)
    # All retries exhausted — log with context since str(ReadTimeout) is often blank.
    detail = str(last_exc) if last_exc and str(last_exc) else "(no detail)"
    print(
        f"[{agent_name}] {type(last_exc).__name__ if last_exc else 'Unknown'} after "
        f"{retries + 1} attempts{_ctx}: {detail}"
    )
    return None
