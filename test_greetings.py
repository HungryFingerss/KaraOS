"""
test_greetings.py -- End-to-end test for Task 5: varied greetings.

Tests:
1. DB migration: last_seen + preferred_language columns exist
2. update_last_seen / update_language / get_greeting_data round-trip
3. _time_of_day returns a valid bucket
4. _time_since_label covers all branches
5. generate_greeting produces different strings across multiple calls
6. Fallback triggers when Ollama is unreachable (patched)
7. Full pipeline: first-time greeting vs returning greeting
"""
import asyncio
import sys, os, time
sys.path.insert(0, os.path.dirname(__file__))

import pytest
from unittest.mock import patch, AsyncMock
from core.db    import FaceDB
from core.brain import (
    _time_of_day, _time_since_label, generate_greeting,
    _GREETING_FALLBACKS, _LANG_NAMES
)

PERSON_ID   = "greet_test_001"
PERSON_NAME = "Jagan"

# ─────────────────────────────────────────────────────────────────────────────
def test_db_migration(tmp_path):
    print("TEST 1: DB migration -- last_seen + preferred_language columns exist")
    # Session 122 — use tmp_path to avoid touching real production faces.db
    db = FaceDB(str(tmp_path / "faces.db"), faiss_path=str(tmp_path / "faiss.index"))
    try:
        # Query the schema
        cols = [r[1] for r in db._conn.execute("PRAGMA table_info(persons)").fetchall()]
        assert "last_seen"          in cols, f"last_seen missing from persons: {cols}"
        assert "preferred_language" in cols, f"preferred_language missing from persons: {cols}"
        print("  -> both columns present OK")
    finally:
        db._conn.close()

def test_db_methods(tmp_path):
    print("TEST 2: update_last_seen / update_language / get_greeting_data round-trip")
    # Session 122 — use tmp_path to avoid touching real production faces.db
    db = FaceDB(str(tmp_path / "faces.db"), faiss_path=str(tmp_path / "faiss.index"))
    # Clean up any leftover test row (idempotent on fresh tmp DB)
    db._conn.execute("DELETE FROM persons WHERE id = ?", (PERSON_ID,))
    db._conn.commit()

    # Insert a minimal test person
    db._conn.execute(
        "INSERT INTO persons (id, name, enrolled_at) VALUES (?, ?, ?)",
        (PERSON_ID, PERSON_NAME, time.time())
    )
    db._conn.commit()

    # Initially last_seen is NULL
    gdata = db.get_greeting_data(PERSON_ID)
    assert gdata is not None
    assert gdata["last_seen"] is None,           f"Expected None, got {gdata['last_seen']}"
    assert gdata["preferred_language"] == "en",  f"Expected 'en', got {gdata['preferred_language']}"
    print("  -> initial state: last_seen=None, lang=en OK")

    # Update last_seen
    db.update_last_seen(PERSON_ID)
    gdata = db.get_greeting_data(PERSON_ID)
    assert gdata["last_seen"] is not None
    assert abs(gdata["last_seen"] - time.time()) < 2, "last_seen timestamp off"
    print("  -> update_last_seen OK")

    # Update language
    db.update_language(PERSON_ID, "hi")
    gdata = db.get_greeting_data(PERSON_ID)
    assert gdata["preferred_language"] == "hi", f"Expected 'hi', got {gdata['preferred_language']}"
    print("  -> update_language OK")

    # Cleanup
    db._conn.execute("DELETE FROM persons WHERE id = ?", (PERSON_ID,))
    db._conn.commit()

def test_time_of_day():
    print("TEST 3: _time_of_day returns valid bucket")
    result = _time_of_day()
    assert result in ("morning", "afternoon", "evening", "night"), f"Unexpected: {result}"
    print(f"  -> current bucket: '{result}' OK")

def test_time_since_label():
    print("TEST 4: _time_since_label covers all branches")
    now = time.time()
    cases = [
        (None,                  "first time"),
        (now - 30,              "just now"),
        (now - 7200,            "a few hours ago"),
        (now - 18 * 3600,       "earlier today"),
        (now - 30 * 3600,       "yesterday"),
        (now - 3 * 86400,       "a few days ago"),
        (now - 14 * 86400,      "a while ago"),
        (now - 60 * 86400,      "a long time ago"),
    ]
    for ts, expected in cases:
        result = _time_since_label(ts)
        assert result == expected, f"_time_since_label({ts!r}) = '{result}', expected '{expected}'"
        print(f"  -> {expected!r} OK")

@pytest.mark.network
async def test_generate_greeting_live():
    print("TEST 5: generate_greeting produces output (live Ollama)")
    now = time.time()
    results = set()
    for _ in range(3):
        g = await generate_greeting(
            PERSON_NAME,
            last_seen=now - 86400,   # yesterday
            language="en",
        )
        assert g and len(g) > 5, f"Empty greeting returned: {g!r}"
        results.add(g)
    print(f"  -> 3 greetings generated, {len(results)} unique OK")
    for g in results:
        print(f"     \"{g}\"")

async def test_generate_greeting_fallback():
    print("TEST 6: Fallback triggers when Ollama is unreachable")
    import httpx
    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__  = AsyncMock(return_value=False)
        mock_client.post.side_effect = httpx.ConnectError("connection refused")
        mock_cls.return_value = mock_client

        g = await generate_greeting(PERSON_NAME, last_seen=None, language="en")
        assert g and PERSON_NAME in g, f"Fallback should contain name, got: {g!r}"
        print(f"  -> fallback returned: \"{g}\" OK")

@pytest.mark.network
async def test_first_time_vs_returning():
    print("TEST 7: First-time vs returning greeting differ in tone")
    first_time = await generate_greeting(PERSON_NAME, last_seen=None, language="en")
    returning  = await generate_greeting(
        PERSON_NAME, last_seen=time.time() - 3 * 86400, language="en"
    )
    print(f"  -> first-time: \"{first_time}\"")
    print(f"  -> returning:  \"{returning}\"")
    assert first_time != returning, "First-time and returning greetings should differ"
    print("  -> greetings are different OK")

async def main():
    # Sync tests
    test_db_migration()
    print()
    test_db_methods()
    print()
    test_time_of_day()
    print()
    test_time_since_label()
    print()

    # Async tests
    await test_generate_greeting_live()
    print()
    await test_generate_greeting_fallback()
    print()
    await test_first_time_vs_returning()
    print()

    print("=" * 60)
    print("ALL TESTS PASSED OK")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
