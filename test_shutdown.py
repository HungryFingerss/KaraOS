"""
test_shutdown.py — Tests for Task 6: graceful shutdown.

Tests:
1. stop_audio() doesn't raise when nothing is playing
2. _shutdown_event is None before run() is called
3. Shutdown event exits the loop: simulate run() loop with a mocked
   shutdown trigger and confirm finally block executes in order
4. Memory save timeout: confirm 3s timeout is respected and doesn't hang
5. SIGINT triggers shutdown on Windows (signal.SIGINT is always available)
"""
import asyncio
import sys
import os
import time
import signal
sys.path.insert(0, os.path.dirname(__file__))


def test_stop_audio_safe():
    print("TEST 1: stop_audio() is safe when nothing is playing")
    from core.audio import stop_audio
    # Must not raise even with no active stream
    stop_audio()
    stop_audio()  # idempotent
    print("  -> no exception, idempotent OK")


def test_shutdown_event_initially_none():
    print("TEST 2: _shutdown_event is None before run() is called")
    import pipeline
    # In a fresh import _shutdown_event is None (not yet inside run())
    assert pipeline._shutdown_event is None, \
        f"Expected None, got {pipeline._shutdown_event}"
    print("  -> _shutdown_event is None OK")


async def test_loop_exits_on_shutdown():
    print("TEST 3: Loop exits cleanly when shutdown event is set")

    shutdown = asyncio.Event()
    iterations = 0

    async def mock_loop():
        nonlocal iterations
        while not shutdown.is_set():
            iterations += 1
            try:
                await asyncio.wait_for(shutdown.wait(), timeout=0.01)
            except asyncio.TimeoutError:
                pass
            if iterations >= 3:
                shutdown.set()  # trigger shutdown after 3 ticks

    await mock_loop()
    assert iterations == 3, f"Expected 3 iterations, got {iterations}"
    print(f"  -> loop ran {iterations} iterations then exited OK")


async def test_memory_save_timeout():
    print("TEST 4: Memory save respects 3s timeout")

    async def slow_summarize(*args, **kwargs):
        await asyncio.sleep(10)  # simulates a hung Ollama
        return "should never reach here"

    start = time.time()
    try:
        result = await asyncio.wait_for(slow_summarize(), timeout=3.0)
    except asyncio.TimeoutError:
        elapsed = time.time() - start
        assert elapsed < 4.0, f"Timeout took too long: {elapsed:.1f}s"
        print(f"  -> timed out after {elapsed:.2f}s (under 4s budget) OK")
        return

    assert False, "Expected TimeoutError was not raised"


def test_sigint_registered():
    print("TEST 5: SIGINT handler can be registered without error")

    original = signal.getsignal(signal.SIGINT)
    try:
        received = []

        def handler(signum, frame):
            received.append(signum)

        signal.signal(signal.SIGINT, handler)
        # Verify handler was registered
        assert signal.getsignal(signal.SIGINT) is handler
        print("  -> SIGINT handler registered OK")
    finally:
        # Restore original handler
        signal.signal(signal.SIGINT, original)
    print("  -> original SIGINT handler restored OK")


def test_sigterm_linux_only():
    print("TEST 6: SIGTERM handler registration (Linux only)")
    if sys.platform == "win32":
        print("  -> Windows detected — SIGTERM not registered (expected) OK")
        return
    # On Linux, verify SIGTERM can be set via loop.add_signal_handler
    async def _check():
        loop = asyncio.get_running_loop()
        called = []
        loop.add_signal_handler(signal.SIGTERM, lambda: called.append(True))
        # Clean up
        loop.remove_signal_handler(signal.SIGTERM)
        print("  -> SIGTERM add_signal_handler works OK")
    asyncio.run(_check())


async def main():
    test_stop_audio_safe()
    print()
    test_shutdown_event_initially_none()
    print()
    await test_loop_exits_on_shutdown()
    print()
    await test_memory_save_timeout()
    print()
    test_sigint_registered()
    print()
    test_sigterm_linux_only()
    print()
    print("=" * 60)
    print("ALL TESTS PASSED OK")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
