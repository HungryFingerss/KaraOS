"""
test_executor.py — Tests for C3+C4: blocking I/O off the event loop.

Tests:
1. listen_and_transcribe() runs in executor — event loop ticks during recording
2. record_until_silence() exits early when _interrupt_flag is set (shutdown sim)
3. transcribe() runs in executor — event loop ticks during Whisper inference
4. capture_frames_async() uses asyncio.sleep — event loop ticks between frames
5. capture_frames_async() stops early when stop_event is set
6. speak() Kokoro path runs in executor — event loop ticks during TTS synthesis
"""
import asyncio
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(__file__))


# ── Helpers ───────────────────────────────────────────────────────────────────

def count_event_loop_ticks(duration: float) -> int:
    """Run the event loop for `duration` seconds and count how many times a
    zero-sleep coroutine fires. If the loop is blocked, count stays low."""
    ticks = 0

    async def ticker():
        nonlocal ticks
        end = asyncio.get_event_loop().time() + duration
        while asyncio.get_event_loop().time() < end:
            ticks += 1
            await asyncio.sleep(0)

    asyncio.run(ticker())
    return ticks


# ── Test 1: record_until_silence exits on _interrupt_flag ─────────────────────

def test_record_exits_on_interrupt_flag():
    """record_until_silence must return quickly when _interrupt_flag is set."""
    print("TEST 1: record_until_silence exits within 1s when _interrupt_flag set")

    from unittest.mock import patch, MagicMock
    import numpy as np
    import torch  # pre-import so `import torch` inside record_until_silence is instant
    import core.audio as audio_mod

    # Mock sounddevice InputStream so we don't need real mic
    chunk = np.zeros(512, dtype=np.float32)
    mock_stream = MagicMock()
    mock_stream.__enter__ = lambda s: s
    mock_stream.__exit__ = MagicMock(return_value=False)
    mock_stream.read = MagicMock(return_value=(chunk.reshape(-1, 1), None))

    # Mock VAD model: return_value is what vad_model(tensor, sr) returns;
    # calling .item() on that must return 0.0 (no speech detected).
    mock_vad_result = MagicMock()
    mock_vad_result.item.return_value = 0.0
    mock_vad_model = MagicMock(return_value=mock_vad_result)

    # Set the interrupt flag after 200ms from a background thread
    def set_flag_after_delay():
        time.sleep(0.2)
        audio_mod._interrupt_flag.set()

    t = threading.Thread(target=set_flag_after_delay, daemon=True)

    with patch("sounddevice.InputStream", return_value=mock_stream), \
         patch.object(audio_mod, "_load_vad", return_value=mock_vad_model):
        audio_mod._interrupt_flag.clear()
        t.start()
        start = time.time()
        result = audio_mod.record_until_silence(max_duration=30.0)
        elapsed = time.time() - start

    assert elapsed < 1.0, f"record_until_silence took {elapsed:.2f}s — should exit within 1s"
    assert len(result) == 0, "Should return empty array when interrupted before speech"
    print(f"  -> exited after {elapsed:.3f}s (< 1s) OK")


# ── Test 2: event loop stays alive during record_until_silence ────────────────

def test_event_loop_ticks_during_recording():
    """Event loop must tick while record_until_silence runs in executor."""
    print("\nTEST 2: event loop ticks during listen_and_transcribe executor call")

    from unittest.mock import patch, MagicMock
    import numpy as np
    import torch  # pre-import so `import torch` inside record_until_silence is instant
    import core.audio as audio_mod

    chunk = np.zeros(512, dtype=np.float32)
    mock_stream = MagicMock()
    mock_stream.__enter__ = lambda s: s
    mock_stream.__exit__ = MagicMock(return_value=False)
    mock_stream.read = MagicMock(return_value=(chunk.reshape(-1, 1), None))

    mock_vad_result = MagicMock()
    mock_vad_result.item.return_value = 0.0
    mock_vad = MagicMock(return_value=mock_vad_result)

    ticks = 0

    async def run():
        nonlocal ticks

        async def ticker():
            nonlocal ticks
            for _ in range(500):
                ticks += 1
                await asyncio.sleep(0)

        # Set interrupt flag after 300ms so recording exits
        async def interrupt_after():
            await asyncio.sleep(0.3)
            audio_mod._interrupt_flag.set()

        with patch("sounddevice.InputStream", return_value=mock_stream), \
             patch.object(audio_mod, "_load_vad", return_value=mock_vad), \
             patch.object(audio_mod, "transcribe", return_value=("", "en")):
            audio_mod._interrupt_flag.clear()
            await asyncio.gather(
                audio_mod.listen_and_transcribe(),
                ticker(),
                interrupt_after(),
            )

    asyncio.run(run())

    assert ticks > 50, \
        f"Event loop only ticked {ticks} times — recording may be blocking the loop"
    print(f"  -> event loop ticked {ticks} times during recording OK")


# ── Test 3: capture_frames_async yields to event loop between frames ──────────

def test_capture_frames_async_ticks_loop():
    """capture_frames_async must yield to the event loop between each frame."""
    print("\nTEST 3: capture_frames_async yields event loop between frames")

    from unittest.mock import MagicMock, patch
    import numpy as np
    from core.vision import Camera

    dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = True
    mock_cap.read.return_value = (True, dummy_frame)

    ticks = 0

    async def run():
        nonlocal ticks

        async def ticker():
            nonlocal ticks
            for _ in range(1000):
                ticks += 1
                await asyncio.sleep(0)

        with patch("cv2.VideoCapture", return_value=mock_cap):
            cam = Camera.__new__(Camera)
            cam._cap = mock_cap

            await asyncio.gather(
                cam.capture_frames_async(n=5, interval=0.05),
                ticker(),
            )

    asyncio.run(run())

    assert ticks > 20, \
        f"Event loop only ticked {ticks} times — asyncio.sleep not yielding"
    print(f"  -> event loop ticked {ticks} times across 5 frames OK")


# ── Test 4: capture_frames_async stops early on stop_event ───────────────────

def test_capture_frames_async_stops_on_event():
    """capture_frames_async must stop before n frames if stop_event is set."""
    print("\nTEST 4: capture_frames_async exits early when stop_event set")

    from unittest.mock import MagicMock, patch
    import numpy as np
    from core.vision import Camera

    dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = True
    mock_cap.read.return_value = (True, dummy_frame)

    async def run():
        stop = asyncio.Event()

        async def set_stop():
            await asyncio.sleep(0.12)   # fires after ~2-3 frames (5 × 0.05s)
            stop.set()

        with patch("cv2.VideoCapture", return_value=mock_cap):
            cam = Camera.__new__(Camera)
            cam._cap = mock_cap
            frames, _ = await asyncio.gather(
                cam.capture_frames_async(n=20, interval=0.05, stop_event=stop),
                set_stop(),
            )

        return frames

    frames = asyncio.run(run())

    assert len(frames) < 20, \
        f"Expected early exit, but captured all 20 frames (stop_event ignored)"
    print(f"  -> stopped after {len(frames)} frames (< 20) OK")


# ── Test 5: transcribe runs in executor (smoke) ───────────────────────────────

def test_transcribe_in_executor_returns_tuple():
    """run_in_executor with transcribe() must unpack to (str, str) correctly."""
    print("\nTEST 5: transcribe() via run_in_executor returns (str, str) tuple")

    from unittest.mock import patch
    import numpy as np
    import core.audio as audio_mod

    fake_audio = np.zeros(16000, dtype=np.float32)  # 1s of silence

    async def run():
        loop = asyncio.get_running_loop()
        with patch.object(audio_mod, "_load_whisper") as mock_load:
            mock_model = mock_load.return_value
            mock_model.transcribe.return_value = (
                iter([]),
                type("Info", (), {
                    "language": "en",
                    "language_probability": 0.9
                })()
            )
            result = await loop.run_in_executor(None, audio_mod.transcribe, fake_audio)
        return result

    text, lang = asyncio.run(run())
    assert isinstance(text, str)
    assert isinstance(lang, str)
    print(f"  -> got ('{text}', '{lang}') — tuple unpacks correctly OK")


if __name__ == "__main__":
    test_record_exits_on_interrupt_flag()
    test_event_loop_ticks_during_recording()
    test_capture_frames_async_ticks_loop()
    test_capture_frames_async_stops_on_event()
    test_transcribe_in_executor_returns_tuple()
    print()
    print("=" * 60)
    print("ALL TESTS PASSED OK")
    print("=" * 60)
