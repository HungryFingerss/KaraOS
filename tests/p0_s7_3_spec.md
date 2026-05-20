# P0.S7.3 — KAIROS silence baseline fix + configurable threshold

**Date:** 2026-05-18
**Author:** architect
**Status:** Direct-to-developer (tight bug fix, no spec-first cycle needed). Standing by for developer implementation → user runs a short canary → architect verifies from logs.

**Surfaced by:** Jagan, post-P0.S7.1 canary observation (2026-05-18).

---

## 1. Bug

KAIROS proactive question fires immediately after a long brain response, instead of waiting for actual user silence. Example: brain gives a 3-minute TTS response; the moment TTS finishes, KAIROS fires "How's the rest of your day?" — feels intrusive, no breathing room for the user to respond naturally.

**Root cause:** pipeline.py:3223 computes:
```python
_silence_elapsed = now - _pipeline_state_store.peek_last_user_speech_at()
```

`_last_user_speech_at` is the timestamp of the user's LAST utterance. During a 3-minute brain response, the user hasn't spoken, so `_silence_elapsed` accumulates from BEFORE the brain started speaking. By the time TTS finishes, `_silence_elapsed` is already > `KAIROS_SILENCE_THRESHOLD=30s`, so KAIROS fires on the very next tick.

The silence countdown should reset when the brain finishes speaking, not when the user last spoke.

---

## 2. Fix

Two coordinated changes:

### 2.1 Baseline calculation change (pipeline.py:3223)

```python
# OLD
_silence_elapsed = now - _pipeline_state_store.peek_last_user_speech_at()

# NEW — silence starts counting from the LATEST of:
#   - user's last utterance (existing behavior)
#   - KAIROS's own last firing (cooldown, existing behavior at line 3224)
#   - brain's last TTS playback end (NEW — fixes Bug 2)
import core.audio as _audio_mod  # already imported elsewhere in pipeline.py; reuse the binding
_last_tts_end = float(getattr(_audio_mod, "_tts_end_time", 0.0))
_silence_baseline = max(
    _pipeline_state_store.peek_last_user_speech_at(),
    _last_tts_end,
)
_silence_elapsed = now - _silence_baseline
```

The `_last_kairos_at` value continues to drive the cooldown check at line 3224 (independent of silence calculation). Only the silence baseline changes.

### 2.2 Configurable threshold (core/config.py)

Bump default from 30s to 120s (2 minutes) per user direction. Make it explicit and configurable.

```python
# OLD
KAIROS_SILENCE_THRESHOLD = 30  # seconds

# NEW
# P0.S7.3 — silence countdown begins from max(last_user_speech_at, _tts_end_time),
# so brain-speaking time doesn't accumulate as "silence." 120s (2 min) gives the
# user comfortable breathing room after a brain response before KAIROS proactively
# re-engages. Adjustable per user preference.
KAIROS_SILENCE_THRESHOLD_SECS: float = 120.0
```

Rename the constant to `_SECS` suffix for unit clarity (matches `ANTI_SPOOF_BURST_WINDOW_SECS`, `ENROLLMENT_RENAME_GRACE_SECS` naming pattern). All callers in pipeline.py update accordingly.

### 2.3 Observability (small extension)

Extend the existing KAIROS log line to include the new baseline source:

```python
# Existing log at firing site (line 3262 area):
print(f"[KAIROS] Brain proactive wake — {_silence_elapsed:.0f}s silence")

# NEW
_baseline_source = "tts_end" if _last_tts_end >= _pipeline_state_store.peek_last_user_speech_at() else "user_speech"
print(f"[KAIROS] Brain proactive wake — {_silence_elapsed:.0f}s silence (baseline={_baseline_source})")
```

This lets the canary log surface which baseline drove the firing (TTS end vs user speech). Helps with future debugging.

---

## 3. Tests

`tests/test_p0_s7_3_kairos_baseline.py` (new) — 3 tests:

1. **test_kairos_silence_baseline_uses_max_of_user_speech_and_tts_end**
   - Set `_tts_end_time = now - 10` (TTS ended 10s ago)
   - Set `_last_user_speech_at = now - 200` (user spoke 200s ago — would normally fire KAIROS)
   - Assert silence_elapsed computed as 10s (the max — TTS is more recent)
   - Assert KAIROS does NOT fire (10s < 120s threshold)

2. **test_kairos_fires_after_threshold_from_tts_end**
   - Set `_tts_end_time = now - 121` (TTS ended 121s ago)
   - Set `_last_user_speech_at = now - 200`
   - Assert silence_elapsed = 121s (max)
   - Assert KAIROS fires (121s > 120s threshold)

3. **test_kairos_threshold_constant_is_configurable_float**
   - Source-inspection: assert `KAIROS_SILENCE_THRESHOLD_SECS` exists in `core/config.py`, is a float, value ≥ 60 (lower-bound safety).

---

## 4. Validation

- All 3 new tests green; full suite green.
- Short canary by user: have a long brain response (ask brain to "tell me about the history of cookies" or similar verbose prompt), then stay quiet for 30s. Confirm KAIROS does NOT fire during those 30s. Then stay quiet for another 90s (total 2 min of silence post-TTS); confirm KAIROS fires at ~120s.

---

## 5. Suite delta

Forecast: 2346 → 2349 (+3).

---

## 6. Estimated effort

~30 min (3-line core change + config rename + 3 unit tests).

---

## 7. Reference

- `pipeline.py:3203-3226` — `_kairos_tick` function (silence calculation site)
- `pipeline.py:3262` (approx) — `[KAIROS]` log line
- `core/audio.py:123, 645, 775` — `_tts_end_time` module-level state (already updated on TTS completion)
- `core/config.py` — `KAIROS_SILENCE_THRESHOLD` constant (to rename + bump)
- Canary log: `terminal_output.md` lines 552, 574, 601 (3 of the 4 KAIROS firings in the 2026-05-18 canary — at least one fired immediately after a long brain response per user's report).
