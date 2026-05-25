# P0.R10 — Audio device failure resilience (Plan v1)

**Date**: 2026-05-25
**Author**: architect (Claude)
**Cycle shape**: SMALL-MEDIUM band, 3-artifact OPTIONAL-Plan-v2 path projected
**Phase 0 verdict**: ACCEPTED with 0 BLOCKING PIs + 2 non-blocking observations (LINE-REF-DRIFT §1.3 row 5 + closure-audit verdict cycle elision procedural)
**Q1-Q9**: all 9 RATIFIED at Phase 0 verdict
**Anchor count**: 9 RATIFIED at exact mid INCLUSIVE band [7.65, 10.35]

---

## §0 Phase 0 absorption + procedural commitments

Phase 0 audit ACCEPTED 2026-05-25. Two absorption events fold into Plan v1:

**(1) LINE-REF-DRIFT preventive re-verification of all line-ref claims** (auditor's Obs #2 absorption + Phase 0 LINE-REF-DRIFT prevention discipline): architect performed fresh grep-tool re-verification of every line ref in §1.1 + §1.3 + §1.4 at Plan v1 drafting time. **Minor drift caught at architect-side preventive grep**: Phase 0 §1.4 cited `pipeline.py:2411 (P0.R3 canonical reference)` but fresh grep shows `_vision_watchdog_loop` def at line 2412 + body `while True:` at line 2421 (drift +1 / +10). P0.R8 `_heavy_worker_watchdog_loop` def at 2439 + body `while True:` at 2475 (unchanged). Refreshed in §1 below. **Banking signal**: LINE-REF-DRIFT sub-shape's prevention mechanism (re-verify line refs at Plan v1 §1 refresh step) WORKED — caught preventively before auditor Pass-2 grep. **2nd preventive application of LINE-REF-DRIFT sub-shape** (1st was at P0.R10 Phase 0 drafting itself). Banked.

**(2) Closure-audit verdict cycle elision** (auditor's Obs #1 procedural absorption): at P0.R9 closure I performed architect closure-audit internally (catches + 6 fixes + bidirectional grep-verify round-trip) and went straight to "P0.R9 CLOSED" without surfacing the audit + my catches as a separate verdict-cycle for auditor ratification. Per auditor's Recommendation #6: forward closure-audit explicitly for ratification going forward to preserve the 4-step cycle integrity (Phase 0 verdict → Plan v1 verdict → closure-audit verdict → next-cycle Phase 0). §9 below explicitly commits to this; P0.R10 closure-audit will be forwarded to auditor for explicit ratification before cycle is declared CLOSED.

**Q1-Q9 ratifications applied to §2 D-decisions**: all 9 architect leans RATIFIED at Phase 0 verdict. §2 D-decision specifications LOCKED at architect's lean shapes; D-decision text unchanged from Phase 0.

**Cross-path discipline preventive commitment** (per `feedback_architect_reads_catches_phase_7_memory_file_omission.md` 4th sub-variant CROSS-PATH-SYNC-OMISSION + NEW DEFERRED-CANARY-ENTRY-OMISSION sibling class operational rule, locked at P0.R9 closure-audit): P0.R10 closure does NOT project new memory files (clean cycle if no observations surface). IF any memory-file edits are introduced at closure, architect MUST verify updates at BOTH the architect-memory path (`C--Users-jagan-dog-ai-dog-ai/memory/`) AND the auditor-facing memory path (`C--Users-jagan-dog-ai/memory/`); architect MUST also verify deferred-canary entry actually lands at `to_be_checked.md`. §6 below enumerates the cross-path verification steps explicitly + commits to bank `feedback_closure_audit_verdict_cycle_elision.md` at BOTH paths.

---

## §1 Grep findings (Pass-2 — Plan v1 refresh)

### §1.1 Audio device call surfaces (REFRESHED line refs per LINE-REF-DRIFT preventive)

| # | Surface | File:Line | Current behavior |
|---|---|---|---|
| 1 | `sd.InputStream(samplerate, channels=1, dtype='float32')` context manager in `record_until_silence` | `core/audio.py:382` (def at 337) | Context manager opens InputStream; reads via `stream.read(chunk_size)`; **unguarded against `sd.PortAudioError` / `OSError`** |
| 2 | `sd.stop()` + `sd.play(pcm, samplerate)` + `await loop.run_in_executor(None, sd.wait)` + `sd.stop()` cluster in `speak` | `core/audio.py:658-663` (async def at 637) | Synchronous-equivalent playback via blocking `sd.wait`; **unguarded against device errors mid-playback** |
| 3 | `sd.stop()` + `sd.play(pcm, samplerate=sr)` + `await loop.run_in_executor(None, sd.wait)` cluster in `speak_stream` | `core/audio.py:787-793` (async def at 737) | Per-sentence iteration with playback per chunk; **mid-stream failure decision needed** (Q2 (b) RATIFIED: abort-whole-stream + per-sentence count logging) |
| 4 | `sd.play(pcm, samplerate=sr)` in `play_filler` | `core/audio.py:320` (def at 293) | Low-stakes filler sound; **unguarded; failure can silently skip** |
| 5 | `sd.stop()` in `stop_audio` | `core/audio.py:823` (def at 819) | Already wrapped in `try/except: pass` with `# CLEANUP:` annotation at line 825 — **P0.4 silent-except policy LOAD-BEARING — must preserve verbatim** |

5 distinct call surfaces. 4 unguarded; 1 has existing CLEANUP-annotated swallow.

### §1.2 Production callers in pipeline.py (unchanged from Phase 0; all verified)

`listen_and_transcribe()` callers at pipeline.py:3548 + 3559 + 3566; `stop_audio()` callers at 2707 + 5675 + 5755 + 6076; `play_filler(text)` at 5272. ~10 total callers. P0.R10 D1+D2 mutations preserve existing semantic contracts (failure path returns empty/None or logs+swallows without raising).

### §1.3 Watchdog + HealthSnapshot existing infrastructure (REFRESHED + ALL line refs verified at Plan v1 drafting)

| # | Surface | File:Line | Pattern |
|---|---|---|---|
| 1 | `WatchdogAgent.report_heavy_worker_burst` | `core/brain_agent.py:6582` (P0.R8 D4) | Severity "warning"; metadata captures pool name + crash count + window |
| 2 | `WatchdogAgent.report_vram_budget_refusal` | `core/brain_agent.py:6621` (P0.R9 D5) | Severity "warning"; metadata captures task_name + cumulative_mb + ceiling_mb + estimate_mb |
| 3 | `BrainOrchestrator.report_heavy_worker_burst` passthrough | `core/brain_agent.py:7477` (P0.R8) | Mirror pattern |
| 4 | `BrainOrchestrator.report_vram_budget_refusal` passthrough | `core/brain_agent.py:7490` (P0.R9) | Mirror pattern |
| 5 | `HealthSnapshot.heavy_worker_status: dict[str, str]` | `core/health.py:70` (P0.R6 D4) | dict-keyed-by-pool-name pattern — P0.R10 reuses for `audio_degraded` |
| 6 | `HealthSnapshot.heavy_worker_crash_counts: dict[str, int]` | `core/health.py:76` (P0.R8 D5) | dict pattern |
| 7 | `HealthSnapshot.vram_budget: dict[str, list[str]]` | `core/health.py:95` (P0.R9 D6) | dict pattern (LINE-REF-DRIFT Obs #2 absorption: ✓ verified at Plan v1 drafting per auditor's recommendation) |
| 8 | `_record_pool_crash(task_name)` | `core/heavy_worker.py:69` (P0.R8 D1) | Module-level dict + threading.Lock + auto-prune at poll time |
| 9 | `count_recent_crashes(task_name, window_secs)` | `core/heavy_worker.py:87` (P0.R8 D1) | Auto-prune at poll time |
| 10 | `persist_crash_diagnostic(task_name, exc, traceback, count)` | `core/crash_logs.py:33` (P0.R11 D2) | Generic API per Q9 standalone-API framing |

All 10 surfaces grep-verified at Plan v1 drafting via fresh tool invocation.

### §1.4 Cross-spec interactions (Pass-2 refreshed)

| Spec | Interaction | Status | Verified line refs |
|---|---|---|---|
| P0.R1 D1 | None-return fallback contracts | LOAD-BEARING | Q3 (a) RATIFIED — mic D1 None sentinel maps to downstream None-handling |
| P0.R3 | Vision-loop watchdog pattern (bare `while True:`) | EXTENDS | `_vision_watchdog_loop` def at `pipeline.py:2412` + body `while True:` at `pipeline.py:2421` (REFRESHED from Phase 0's `:2411` — drift +1 caught at architect-side preventive grep; LINE-REF-DRIFT 2nd preventive application instance banked) |
| P0.R8 | Heavy-worker burst-detection | EXTENDS | `_record_pool_crash` at `core/heavy_worker.py:69` + `count_recent_crashes` at `:87` + `_heavy_worker_watchdog_loop` def at `pipeline.py:2439` + body `while True:` at `pipeline.py:2475` (all verified at Plan v1 drafting) |
| P0.R11 | `persist_crash_diagnostic` generic API | EXTENDS | Q4 (b) RATIFIED — integration at burst-threshold breach only; `crash_logs.py:33` |
| P0.4 silent-except | `stop_audio` CLEANUP annotation | LOAD-BEARING | `core/audio.py:825` `# CLEANUP:` annotation verified; D2 mutation must preserve verbatim |
| HealthSnapshot | dict-keyed field precedents | EXTENDS | Q1 (a) RATIFIED — `audio_degraded: dict[str, bool]` keyed by 'mic'/'speaker' |
| WatchdogAgent | burst-alert pattern | EXTENDS | New `report_audio_device_burst` method + Orchestrator passthrough mirroring `report_heavy_worker_burst` shape |
| ReSpeaker barge-in (CLAUDE.md Session 2) | `_vad_interrupt_listener` deferred until ReSpeaker 4-mic hardware | INTERACTION | Q9 (a) RATIFIED — D1 wrap is barge-in-neutral; module-level counter keyed by channel name |
| Cross-platform | `sd.PortAudioError` codes vary across Windows / Linux / Jetson | LOAD-BEARING | Q5 (a) RATIFIED — uniform catch |

### §1.5 P0.4 silent-except policy interaction (LOAD-BEARING; unchanged from Phase 0)

`stop_audio` at `core/audio.py:819-825` has the canonical P0.4 silent-except pattern with `# CLEANUP:` annotation. D2 mutation MUST preserve verbatim. The `interrupt flag still set` semantic is the existing contract.

### §1.6 ReSpeaker barge-in deferred-feature interaction (CLAUDE.md Session 2 banking; unchanged from Phase 0)

D1 `sd.InputStream` wrap must be barge-in-neutral. Module-level burst counter keyed by channel name supports future `_vad_interrupt_listener` re-introduction without modification.

### §1.7 NEW — Current `record_until_silence` body shape (verified at Plan v1 drafting per CODE-TEMPLATE-MISIDENTIFICATION preventive)

`record_until_silence` body (`core/audio.py:337-487`, partial):

```python
def record_until_silence(
    sample_rate: int = MIC_SAMPLE_RATE,
    ...
) -> np.ndarray:
    ...
    with sd.InputStream(samplerate=sample_rate, channels=1, dtype='float32') as stream:
        # existing chunked recording loop with VAD + smart-turn + silence detection
        ...
    # publish _last_speech_secs + return audio_buf
    ...
```

D1 mutation wraps the `with sd.InputStream(...) as stream:` context manager in try/except for `(sd.PortAudioError, OSError)` → returns None + records mic failure. Existing recording loop body unchanged.

---

## §2 D-decisions LOCKED (per Q1-Q9 ratifications)

### D1 — `record_until_silence` mic-channel wrap (Q3 (a) RATIFIED LOAD-BEARING)

`core/audio.py:337-487` — wrap the `with sd.InputStream(...) as stream:` context manager:

```python
def record_until_silence(
    sample_rate: int = MIC_SAMPLE_RATE,
    ...
) -> "np.ndarray | None":
    """... P0.R10 D1 RATIFIED Q3 (a): wraps sd.InputStream context manager
    in try/except for sd.PortAudioError + OSError; on failure: records event
    via _record_audio_failure('mic') + returns None (distinct sentinel — empty
    audio means 'user was silent', None means 'device failed'). Caller
    (listen_and_transcribe + pipeline.py callers) inspects None vs empty-array
    to route differently (silence vs device-error fallback).
    """
    ...
    try:
        with sd.InputStream(samplerate=sample_rate, channels=1, dtype='float32') as stream:
            # existing chunked recording loop unchanged
            ...
    except (sd.PortAudioError, OSError) as e:
        print(f"[Audio] WARN mic device failure during record_until_silence: {e!r}")
        _record_audio_failure("mic")
        return None  # P0.R10 D1 Q3 (a) — distinct sentinel for device failure
    # publish _last_speech_secs + return audio_buf
    return audio_buf
```

**Return type annotation update LOAD-BEARING**: `-> np.ndarray` → `-> "np.ndarray | None"` per Q3 (a) lock.

**§1.6 barge-in-neutrality**: D1 wrap does NOT introduce module-level singleton state; per-channel counter (`_AUDIO_FAILURE_HISTORY['mic']`) is shared cleanly with future `_vad_interrupt_listener` (Q9 (a) RATIFIED).

### D2 — Speaker-channel wraps with per-site asymmetric semantics (Q2 (b) RATIFIED LOAD-BEARING)

Per Q2 (b) RATIFIED — each call site gets explicit disposition:

**D2.a — `speak` (single-chunk synthesis+play; failure skips turn silently)** at `core/audio.py:637-663`:

```python
async def speak(text: str, language: str = "en"):
    ...
    loop = asyncio.get_running_loop()
    try:
        sd.stop()  # stop any filler or previous audio before starting response
        sd.play(pcm, samplerate=sample_rate)
        await loop.run_in_executor(None, sd.wait)
        sd.stop()
    except (sd.PortAudioError, OSError) as e:
        print(f"[Audio] WARN speaker device failure in speak: {e!r}")
        _record_audio_failure("speaker")
        return  # skip turn silently — caller's contract preserved
```

**D2.b — `speak_stream` (per-sentence iteration; mid-stream failure aborts stream)** at `core/audio.py:737-810`:

```python
async def speak_stream(sentences, language: str = "en"):
    ...
    _sentence_count = 0
    _sentence_total = 0  # populated as stream iterates (unknown upfront)
    for sentence in sentences:
        _sentence_total += 1
        try:
            ...
            sd.stop()
            sd.play(pcm, samplerate=sr)
            await loop.run_in_executor(None, sd.wait)
        except (sd.PortAudioError, OSError) as e:
            print(
                f"[Audio] WARN speaker device failure in speak_stream "
                f"(sentence {_sentence_count}/{_sentence_total}): {e!r}"
            )
            _record_audio_failure("speaker")
            return  # P0.R10 D2.b Q2 (b) — abort whole stream + log per-sentence count
        _sentence_count += 1
```

**Q2 (b) per-sentence count logging**: the `(sentence {_sentence_count}/{_sentence_total})` format is the diagnostic context the auditor RATIFIED. Operators see WHICH sentence of N-sentence stream failed.

**D2.c — `play_filler` (low-stakes ack; failure silently skips)** at `core/audio.py:293-323`:

```python
def play_filler(message: str = ""):
    ...
    try:
        sd.play(pcm, samplerate=sr)
    except (sd.PortAudioError, OSError) as e:
        print(f"[Audio] WARN speaker device failure in play_filler: {e!r}")
        _record_audio_failure("speaker")
        # no return needed — function falls through naturally
```

**D2.d — `stop_audio` (CLEANUP-pattern PRESERVED + extended)** at `core/audio.py:819-825`:

```python
def stop_audio():
    try:
        sd.stop()
    except (sd.PortAudioError, OSError):
        pass  # CLEANUP: sd.stop() raises if no active stream or device gone — interrupt flag still set
    except Exception:
        pass  # CLEANUP: defensive — preserves P0.4 silent-except policy
```

**LOAD-BEARING P0.4 verbatim preservation**: `# CLEANUP:` annotation comment at the `pass` line is the load-bearing marker for `test_no_unannotated_silent_excepts_in_production_code` — must NOT be removed. A5 anchor enforces.

### D3 — `core/audio.py` per-channel burst counter (Q1 (a) RATIFIED + mirror P0.R8 D1)

Insert at `core/audio.py` module-scope (after existing imports):

```python
import threading
import time as _time_mod

# ─────────────────────────────────────────────────────────────────────────────
# P0.R10 D3 — audio device failure tracking (mirror P0.R8 D1)
# ─────────────────────────────────────────────────────────────────────────────
#
# Module-level per-channel failure event tracking for the audio-device
# watchdog's burst-detection logic. Q1 (a) RATIFIED: per-channel keys ('mic',
# 'speaker') tracked independently — USB mic disconnect ≠ speaker driver crash;
# per-channel granularity meaningful operationally.
#
# Thread-safety: callers may be async (speak/speak_stream) OR sync (play_filler,
# stop_audio). threading.Lock guards mutation under concurrent access.
_AUDIO_FAILURE_HISTORY: "dict[str, list[float]]" = {}
_AUDIO_FAILURE_LOCK = threading.Lock()


def _record_audio_failure(channel: str, now: "float | None" = None) -> None:
    """Record an audio-device-failure event for burst detection. Mirrors
    P0.R8's _record_pool_crash shape. channel ∈ {'mic', 'speaker'}.
    """
    if now is None:
        now = _time_mod.time()
    with _AUDIO_FAILURE_LOCK:
        _AUDIO_FAILURE_HISTORY.setdefault(channel, []).append(now)


def count_recent_audio_failures(
    channel: str, window_secs: float, now: "float | None" = None
) -> int:
    """Count audio-device failures within rolling window. Mirrors P0.R8's
    count_recent_crashes shape; auto-prunes events older than window.
    """
    if now is None:
        now = _time_mod.time()
    cutoff = now - window_secs
    with _AUDIO_FAILURE_LOCK:
        events = _AUDIO_FAILURE_HISTORY.get(channel, [])
        events = [t for t in events if t >= cutoff]
        _AUDIO_FAILURE_HISTORY[channel] = events
        return len(events)


def peek_audio_failure_history(channel: str) -> "list[float]":
    """Read-only accessor for audio-failure history. Tests + observability."""
    with _AUDIO_FAILURE_LOCK:
        return list(_AUDIO_FAILURE_HISTORY.get(channel, []))
```

**Plus `pipeline.py` `_audio_device_watchdog_loop` watchdog (mirror P0.R3 + P0.R8 canonical reference at pipeline.py:2421 + :2475 bare `while True:`)**:

```python
# P0.R10 — audio device watchdog: bare `while True:` body matching P0.R3
# canonical reference at pipeline.py:2421 + P0.R8 mirror at :2475. Per
# CODE-TEMPLATE-MISIDENTIFICATION sub-shape lock (validated in BOTH modes at
# P0.R11 + P0.R9): bare `while True:` is the verified canonical reference shape.
_audio_device_watchdog_task: "asyncio.Task | None" = None
_audio_alert_armed: "dict[str, bool]" = {"mic": True, "speaker": True}


async def _audio_device_watchdog_loop() -> None:
    """Audio device watchdog. Polls per-channel burst counter; on threshold
    breach: dispatches WatchdogAgent.report_audio_device_burst alert + flips
    audio_degraded[channel] = True. Q4 (b) RATIFIED: crash_logs forensic
    capture via persist_crash_diagnostic only on burst-threshold breach.
    """
    import core.audio as _audio_mod  # noqa: PLC0415
    from core.config import (  # noqa: PLC0415
        AUDIO_DEVICE_WATCHDOG_INTERVAL_SECS,
        AUDIO_DEVICE_BURST_THRESHOLD,
        AUDIO_DEVICE_BURST_WINDOW_SECS,
    )
    while True:
        await asyncio.sleep(AUDIO_DEVICE_WATCHDOG_INTERVAL_SECS)
        for channel in ("mic", "speaker"):
            failure_count = _audio_mod.count_recent_audio_failures(
                channel, AUDIO_DEVICE_BURST_WINDOW_SECS
            )
            if failure_count >= AUDIO_DEVICE_BURST_THRESHOLD:
                if _audio_alert_armed.get(channel, True):
                    if _brain_orchestrator is not None:
                        _brain_orchestrator.report_audio_device_burst(
                            channel, failure_count, AUDIO_DEVICE_BURST_WINDOW_SECS
                        )
                        # Q4 (b) — persist forensic JSON on burst-threshold
                        # breach (not on every failure)
                        try:
                            from core.crash_logs import persist_crash_diagnostic  # noqa: PLC0415
                            _exc = RuntimeError(
                                f"Audio device '{channel}' burst threshold breached: "
                                f"{failure_count} failures in {AUDIO_DEVICE_BURST_WINDOW_SECS:.0f}s"
                            )
                            persist_crash_diagnostic(
                                f"audio_{channel}_device",
                                _exc,
                                f"audio device burst (channel={channel}, count={failure_count})",
                                failure_count,
                            )
                        except Exception:  # OPTIONAL: forensic capture failure
                            pass
                    _audio_alert_armed[channel] = False
            else:
                # Re-arm alert when failure rate drops back below threshold
                if not _audio_alert_armed.get(channel, True):
                    print(
                        f"[Audio-Watchdog] channel '{channel}' recovered "
                        f"(failure rate dropped below AUDIO_DEVICE_BURST_THRESHOLD)"
                    )
                    _audio_alert_armed[channel] = True
```

**Startup ordering (Q6 (a) RATIFIED)**: spawn AFTER `_heavy_worker_watchdog_task` (P0.R8) per consistent ORDERING with P0.R8 + P0.R3 precedents. **Shutdown ordering**: cancel BEFORE `_heavy_worker_watchdog_task` (reverse-order shutdown invariant).

### D4 — `WatchdogAgent.report_audio_device_burst` method (Q8 (a) RATIFIED)

`core/brain_agent.py` `WatchdogAgent` class after `report_vram_budget_refusal`:

```python
def report_audio_device_burst(
    self,
    channel: str,
    failure_count: int,
    window_secs: float,
) -> None:
    """Store an audio-device burst alert (P0.R10 D4). Q8 (a) RATIFIED:
    severity 'warning' (graceful degradation; caller's fallback fires; system
    continues running). Mirrors P0.R8 report_heavy_worker_burst shape.

    Q1 (a) RATIFIED per-channel granularity: channel ∈ {'mic', 'speaker'};
    alert key includes channel name for operator triage clarity.
    """
    self._db.store_alert(
        f"audio_device_burst_{channel}",
        "warning",
        f"Audio device '{channel}' failure burst — {failure_count} failures in "
        f"{window_secs:.0f}s window. Check device connection / driver / permissions. "
        f"Clears when failure rate drops below AUDIO_DEVICE_BURST_THRESHOLD.",
        {
            "channel": channel,
            "failure_count": failure_count,
            "window_secs": window_secs,
        },
    )
    print(
        f"[WatchdogAgent] audio_device_burst_{channel} alert stored "
        f"(count={failure_count}, window={window_secs:.0f}s)"
    )
```

Plus `BrainOrchestrator.report_audio_device_burst` passthrough mirroring `report_heavy_worker_burst` + `report_vram_budget_refusal` shape.

### D5 — `HealthSnapshot.audio_degraded` field + format extensions + config

**`core/health.py` — HealthSnapshot dataclass extension** (after `vram_budget` field at line 95):

```python
# P0.R10 D5 — audio device observability
audio_degraded: "dict[str, bool]" = field(default_factory=dict)
```

**`gather_health_snapshot` addition** (after existing vram_budget block):

```python
# P0.R10 D5 — audio device observability
audio_degraded: "dict[str, bool]" = {}
try:
    import core.audio as _audio_health  # noqa: PLC0415
    from core.config import (  # noqa: PLC0415
        AUDIO_DEVICE_BURST_THRESHOLD,
        AUDIO_DEVICE_BURST_WINDOW_SECS,
    )
    audio_degraded = {
        "mic": _audio_health.count_recent_audio_failures(
            "mic", AUDIO_DEVICE_BURST_WINDOW_SECS
        ) >= AUDIO_DEVICE_BURST_THRESHOLD,
        "speaker": _audio_health.count_recent_audio_failures(
            "speaker", AUDIO_DEVICE_BURST_WINDOW_SECS
        ) >= AUDIO_DEVICE_BURST_THRESHOLD,
    }
except Exception:  # OPTIONAL: audio module unavailable
    audio_degraded = {}
```

**`format_health_line` conditional emit**:

```python
# P0.R10 D5 — audio degraded conditional emit
_degraded_channels = [
    c for c, deg in (s.audio_degraded or {}).items() if deg
]
if _degraded_channels:
    parts.append(f"audio_degraded={','.join(_degraded_channels)}")
```

**`format_health_alerts` actionable alert with 5 verbatim substrings (anchored by A8)**:

```python
# P0.R10 D5 — audio device degraded alert
_degraded_channels = [
    c for c, deg in (s.audio_degraded or {}).items() if deg
]
if _degraded_channels:
    alerts.append(
        f"[Health-Alert] Audio device degraded — channels: "
        f"{', '.join(_degraded_channels)}. Check USB/audio device connection + "
        f"driver + permissions. Clears when failure rate drops below "
        f"AUDIO_DEVICE_BURST_THRESHOLD."
    )
```

Verbatim alert substrings (A8 anchored):
- `"Audio device degraded"`
- `"channels:"`
- `"USB/audio device connection"`
- `"driver"`
- `"AUDIO_DEVICE_BURST_THRESHOLD"`

**`core/config.py` — P0.R10 constants** (after VRAM_POOL_PRIORITY block at config.py:1428):

```python
# ── Audio device failure resilience (P0.R10) ─────────────────────────────────
# Per-channel burst detection for mic + speaker device failures. Q1 (a) RATIFIED:
# per-channel counter granularity (mic + speaker tracked independently). Q7 (a)
# RATIFIED: moderate defaults (3 failures in 60s); operator-tunable.
AUDIO_DEVICE_WATCHDOG_INTERVAL_SECS = 10.0  # poll cadence
AUDIO_DEVICE_BURST_THRESHOLD        = 3     # N failures in window → degraded
AUDIO_DEVICE_BURST_WINDOW_SECS      = 60.0  # 1 minute rolling window
```

---

## §3 Anchor enumeration (Q5 LOCKED = 9 anchors)

NEW `tests/test_p0_r10_audio_device_resilience.py` with 9 anchors:

| # | Anchor name | Surface | Type |
|---|---|---|---|
| A1 | `test_p0_r10_d1_record_until_silence_wraps_portaudio_error` | `core/audio.py:382` | **BEHAVIORAL** — monkeypatch `sd.InputStream` to raise `sd.PortAudioError` → assert `record_until_silence` returns None + `_record_audio_failure('mic')` called once |
| A2 | `test_p0_r10_d1_mic_failure_returns_none_not_empty_array` | `core/audio.py` | **BEHAVIORAL** — distinguishes Q3 (a) lock semantic: None ≠ empty `np.ndarray`; STT downstream routing contract preserved |
| A3 | `test_p0_r10_d2_speak_wraps_portaudio_error` | `core/audio.py:637` | **BEHAVIORAL** — monkeypatch `sd.play` to raise → assert `speak` returns cleanly (no exception propagates) + `_record_audio_failure('speaker')` called once |
| A4 | `test_p0_r10_d2_speak_stream_aborts_whole_stream_on_mid_stream_failure` | `core/audio.py:737` | **BEHAVIORAL Q2 (b) RATIFIED** — multi-sentence stream; monkeypatch `sd.play` to raise on 2nd sentence; assert: (a) stream aborts (3rd sentence NEVER synthesized), (b) `_record_audio_failure('speaker')` called once (NOT N times), (c) log message contains `(sentence 2/` per-sentence count format, (d) no exception propagates |
| A5 | `test_p0_r10_d2_stop_audio_preserves_cleanup_annotation` | `core/audio.py:819-825` | **SOURCE-INSPECTION P0.4 LOAD-BEARING** — verify `# CLEANUP:` annotation comment AT pass line + try/except shape preserved (catches `sd.PortAudioError + OSError` + bare `Exception` defensively). Defense against P0.4 silent-except policy regression |
| A6 | `test_p0_r10_d3_per_channel_burst_counter_independent` | `core/audio.py` | **BEHAVIORAL Q1 (a) RATIFIED** — record 5 mic failures + 2 speaker failures → `count_recent_audio_failures('mic') == 5` AND `('speaker') == 2`; per-channel granularity verified |
| A7 | `test_p0_r10_d4_watchdog_report_audio_device_burst_method` | `core/brain_agent.py` | SOURCE + behavioral — `WatchdogAgent.report_audio_device_burst` method exists + `_db.store_alert` called with `audio_device_burst_{channel}` key; severity 'warning' |
| A8 | `test_p0_r10_d5_health_snapshot_audio_degraded_field_and_alerts` | `core/health.py` | SOURCE + behavioral — `HealthSnapshot.audio_degraded` field exists + `format_health_line` emits `audio_degraded=mic,speaker` conditionally + `format_health_alerts` emits 5 verbatim substrings when degraded |
| A9 | `test_p0_r10_d5_config_constants_present` | `core/config.py` | SOURCE — 3 constants present with sanity values (`AUDIO_DEVICE_WATCHDOG_INTERVAL_SECS=10.0`, `AUDIO_DEVICE_BURST_THRESHOLD=3`, `AUDIO_DEVICE_BURST_WINDOW_SECS=60.0`) |

**Phase 0 absorption refinements absorbed**:
- A4 spec explicitly verifies Q2 (b) speak_stream abort-whole-stream + per-sentence count logging per auditor Recommendation #4
- A5 spec explicitly verifies `# CLEANUP:` annotation comment preservation per auditor Recommendation #3

---

## §4 Phase 4 deliberate-regression confirmation matrix

9 reverts (one per anchor) per `### Induction-surfaces-invariant-gaps` discipline:

| # | Revert action | Expected anchor failure |
|---|---|---|
| (a) | Drop try/except wrap from `record_until_silence` (restore unguarded `sd.InputStream`) | A1 fires (PortAudioError propagates instead of returning None) |
| (b) | Return empty `np.zeros(0)` from D1 failure path instead of None | A2 fires (Q3 (a) sentinel semantic broken — empty array conflates with user silence) |
| (c) | Drop try/except wrap from `speak` | A3 fires (PortAudioError propagates) |
| (d) | Continue loop on `speak_stream` mid-stream failure (do NOT abort stream) | A4 fires (3rd sentence synthesized; `_record_audio_failure` called N times instead of 1) |
| (e) | Remove `# CLEANUP:` annotation comment from `stop_audio` pass line | A5 fires (P0.4 silent-except policy regression caught at source inspection) |
| (f) | Use shared single counter instead of per-channel dict in `_record_audio_failure` | A6 fires (mic + speaker share counter; per-channel granularity broken) |
| (g) | Remove `WatchdogAgent.report_audio_device_burst` method | A7 fires (method missing) |
| (h) | Remove `audio_degraded` field from `HealthSnapshot` | A8 fires (TypeError or field-missing assertion) |
| (i) | Delete `AUDIO_DEVICE_WATCHDOG_INTERVAL_SECS` from `core/config.py` | A9 fires (constant missing) |

All 9 reverts MUST fire correctly + revert cleanly + suite green before closure narrative drafting.

---

## §5 Phase 5 implementation enumeration (explicit 7-step mutation per P0.R11 Observation 1 absorption pattern)

Per auditor's Recommendation #2 + P0.R11 Observation 1 absorption pattern (explicit mutation enumeration defends against missing-step silent-masking shape). D2's 4 call-site asymmetric mutations especially require explicit step enumeration to defend against per-site contract drift.

**Step 1 — `core/config.py` D5 constants (additive, no breakage)**:

- Step 1.1: Add `AUDIO_DEVICE_WATCHDOG_INTERVAL_SECS = 10.0` after `VRAM_POOL_PRIORITY` block (config.py:1428)
- Step 1.2: Add `AUDIO_DEVICE_BURST_THRESHOLD = 3` after Step 1.1
- Step 1.3: Add `AUDIO_DEVICE_BURST_WINDOW_SECS = 60.0` after Step 1.2

**Step 2 — `core/audio.py` D3 module-level state + burst-detection API (additive)**:

- Step 2.1: Add `import threading` + `import time as _time_mod` at top of file IF NOT ALREADY IMPORTED (verify at draft time: audio.py imports threading + time already? — Phase 5 grep-verify required before edit)
- Step 2.2: Add module-level `_AUDIO_FAILURE_HISTORY: dict[str, list[float]] = {}` + `_AUDIO_FAILURE_LOCK = threading.Lock()` near top of file (after existing module-level state)
- Step 2.3: Add `_record_audio_failure(channel, now=None)` function body
- Step 2.4: Add `count_recent_audio_failures(channel, window_secs, now=None)` function body
- Step 2.5: Add `peek_audio_failure_history(channel)` accessor

**Step 3 — `core/audio.py` D1 + D2.a-d (LOAD-BEARING mutations with asymmetric semantics)**:

- Step 3.1 (D1): Modify `record_until_silence` signature: `-> np.ndarray` → `-> "np.ndarray | None"`
- Step 3.2 (D1): Wrap `with sd.InputStream(...) as stream:` context manager in `try: ... except (sd.PortAudioError, OSError) as e: ... return None`
- Step 3.3 (D2.a): Wrap `speak` body's `sd.stop` + `sd.play` + `sd.wait` + `sd.stop` cluster in try/except `(sd.PortAudioError, OSError)` → log + record failure + return silently
- Step 3.4 (D2.b): Wrap `speak_stream` body's per-sentence `sd.stop` + `sd.play` + `sd.wait` cluster in try/except (inside `for sentence in sentences:` loop) → on failure, log per-sentence count + record failure + `return` to abort whole stream. Initialize `_sentence_count = 0` + `_sentence_total = 0` at function entry; bump `_sentence_total` at start of each iteration; bump `_sentence_count` at end of each successful iteration
- Step 3.5 (D2.c): Wrap `play_filler` body's `sd.play` in try/except `(sd.PortAudioError, OSError)` → log + record failure + fall through naturally (no return needed)
- Step 3.6 (D2.d LOAD-BEARING): Extend `stop_audio`'s existing `except Exception: pass` block. Add explicit `except (sd.PortAudioError, OSError): pass  # CLEANUP: sd.stop() raises if no active stream or device gone — interrupt flag still set` BEFORE the existing `except Exception:` clause. **MUST preserve `# CLEANUP:` annotation comment verbatim — P0.4 silent-except policy LOAD-BEARING (A5 anchor enforces)**

**Step 4 — `pipeline.py` D3 watchdog loop + startup/shutdown wiring**:

- Step 4.1: Add module-level `_audio_device_watchdog_task: "asyncio.Task | None" = None` + `_audio_alert_armed: dict[str, bool] = {"mic": True, "speaker": True}` near `_heavy_worker_watchdog_task` declaration at line 2409
- Step 4.2: Add `async def _audio_device_watchdog_loop()` body with bare `while True:` matching P0.R3 canonical reference at pipeline.py:2421 + P0.R8 mirror at :2475
- Step 4.3: Spawn watchdog at startup AFTER `_heavy_worker_watchdog_task = asyncio.create_task(_heavy_worker_watchdog_loop())` (currently at line 6677) per Q6 (a) RATIFIED — ordering: `_heavy_worker_watchdog_task` → `_audio_device_watchdog_task`
- Step 4.4: Cancel watchdog at shutdown BEFORE `_heavy_worker_watchdog_task.cancel()` per reverse-order shutdown invariant — explicit `.cancel()` + `asyncio.wait_for(..., timeout=1.0)` + `except (CancelledError, TimeoutError, Exception): pass`

**Step 5 — `core/brain_agent.py` D4 (additive)**:

- Step 5.1: Add `WatchdogAgent.report_audio_device_burst(channel, failure_count, window_secs)` method after `report_vram_budget_refusal` (currently at line 6621)
- Step 5.2: Add `BrainOrchestrator.report_audio_device_burst` passthrough mirroring `report_vram_budget_refusal` shape (currently at line 7490)

**Step 6 — `core/health.py` D5 (additive)**:

- Step 6.1: Add `audio_degraded: "dict[str, bool]" = field(default_factory=dict)` field to `HealthSnapshot` dataclass after `vram_budget` field (currently at line 95)
- Step 6.2: Add `audio_degraded` dict population block in `gather_health_snapshot` (after existing `vram_budget` population)
- Step 6.3: Add `format_health_line` conditional emit `audio_degraded={','.join(_degraded_channels)}` when channels degraded
- Step 6.4: Add `format_health_alerts` actionable alert with 5 verbatim substrings when channels degraded

**Step 7 — `tests/test_p0_r10_audio_device_resilience.py` NEW (9 anchors per §3)**:

- Step 7.1: Create file with A1-A9 test functions per §3 anchor enumeration
- Step 7.2: A1 + A2 + A3 + A4 + A6 require `sd.InputStream` / `sd.play` monkeypatching; use a shared `_mock_audio_device_failure(monkeypatch, fn_name)` helper inside the test module
- Step 7.3: A1 + A3 + A4 (and others touching async functions) require `@pytest.mark.asyncio` fixtures; pattern matches existing P0.R8 + P0.R11 + P0.R9 async tests
- Step 7.4: A5 source-inspection scans `core/audio.py::stop_audio` source via `inspect.getsource` + asserts `# CLEANUP:` annotation comment is AT the pass line (defense against P0.4 regression — auditor's Recommendation #3 absorbed)
- Step 7.5: A4 spec explicitly verifies (a) abort-whole-stream + (b) `_record_audio_failure` called exactly once + (c) per-sentence count format `(sentence 2/N)` in log message (auditor's Recommendation #4 absorbed)

**Step 8 — Phase 4 verify-on-revert pass (per §4 matrix)**:

- Step 8.1: Apply each of 9 reverts (a-i) in sequence via temporary Edit
- Step 8.2: After each revert, run the corresponding anchor test in isolation; verify it fires correctly
- Step 8.3: Revert the revert; verify suite green at end of each revert cycle
- Step 8.4: Bank reverts (a-i) in closure narrative `### Induction-surfaces-invariant-gaps` X → X+1 instance

**Mutation-step independence verification**: Steps 1-6 are independent and can land in any order. Step 7 must land last (depends on all prior implementation steps). Step 8 depends on Step 7. Per the P0.R11 Observation 1 absorption pattern — defends against missing-step silent-masking shape.

---

## §6 SCHEDULED memory-file work at closure (cross-path discipline preventive)

Per `feedback_architect_reads_catches_phase_7_memory_file_omission.md` operational rules locked at P0.R9 closure-audit:

P0.R10 closure may introduce 1 NEW memory file:

### §6.1 NEW `feedback_closure_audit_verdict_cycle_elision.md` (auditor's Obs #1 banking)

**File**: `feedback_closure_audit_verdict_cycle_elision.md` (NEW)
**Content**: 1st instance — P0.R9 closure-audit performed internally without auditor ratification verdict cycle. Watch criteria 3+ instances for sub-rule elevation under `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` family or as new operational discipline.

**Cross-path verification at closure** (per locked operational rule):

- Step 6.1.a: Create at architect-memory path `C:\Users\jagan\.claude\projects\C--Users-jagan-dog-ai-dog-ai\memory\feedback_closure_audit_verdict_cycle_elision.md`
- Step 6.1.b: Create at auditor-facing path `C:\Users\jagan\.claude\projects\C--Users-jagan-dog-ai\memory\feedback_closure_audit_verdict_cycle_elision.md`
- Step 6.1.c: Add MEMORY.md index entry at BOTH paths (1st instance + procedural-discipline framing)
- Step 6.1.d: Fresh Read at BOTH paths post-edit; verify entries land

### §6.2 NEW `feedback_line_ref_drift_preventive_application_at_plan_v1.md` (LINE-REF-DRIFT 2nd preventive instance banking)

**File**: `feedback_line_ref_drift_preventive_application_at_plan_v1.md` (NEW — may absorb into existing `feedback_pass_2_grep_caught_real_gap_subshape.md` if architect closure-audit deems consolidation preferable)
**Content**: 2nd preventive application of LINE-REF-DRIFT sub-shape; architect-side preventive grep at Plan v1 §1 refresh caught minor drift (`pipeline.py:2411 → 2412` for P0.R3 canonical reference). 1st preventive application was at P0.R10 Phase 0 drafting itself.

**Decision deferred to closure-audit**: whether to bank as NEW standalone memory file OR extend existing `feedback_pass_2_grep_caught_real_gap_subshape.md` with LINE-REF-DRIFT preventive-mode validation evidence (mirror CODE-TEMPLATE-MISIDENTIFICATION BOTH-modes maturation milestone pattern). Lean: extend existing file rather than create new file (avoids fragmenting sub-shape track record across multiple files).

**Cross-path verification at closure**: same protocol as §6.1.

### §6.3 MEMORY.md index updates at BOTH paths

Both MEMORY.md files need index-entry additions reflecting the new memory file(s):

- `feedback_closure_audit_verdict_cycle_elision.md` — entry for 1st instance
- `feedback_pass_2_grep_caught_real_gap_subshape.md` (if §6.2 absorbs into existing file) — entry refresh with LINE-REF-DRIFT BOTH-modes validation

**Closure-audit cross-path verification protocol** (per locked operational rule):

1. Apply all memory-file edits at BOTH paths
2. Apply MEMORY.md index updates at BOTH paths
3. Fresh Read both MEMORY.md files post-edit; verify entries land
4. Fresh Read all new/extended memory files post-edit; verify content lands
5. Bank cross-path discipline preventive-application instance under `feedback_architect_reads_catches_phase_7_memory_file_omission.md` (CROSS-PATH-SYNC-OMISSION sub-variant 3rd preventive instance after P0.R9 + P0.R10 Phase 0 commitment)

### §6.4 DEFERRED-CANARY-ENTRY-OMISSION grep-verify step commitment

Per P0.R9 closure-audit catch + locked operational rule from `feedback_architect_reads_catches_phase_7_memory_file_omission.md` sibling class:

At P0.R10 closure, architect MUST grep-verify `to_be_checked.md` actually contains the P0.R10 deferred-canary entry. NOT rely on closure-narrative claim alone. PowerShell fresh-disk read (NOT Grep tool — see P0.R9 closure-audit STALE-CACHED-VERIFICATION 2nd instance lesson) is the verification mechanism.

---

## §7 Closure-projection band table (Q5 LOCKED at 9)

| closure-actual | overage vs mid 9 | band | doctrine outcome |
|---|---|---|---|
| 7 | −22.2% | SLIGHT-DRIFT-DOWN | `### Phase-0-granular-decomposition` HOLDS at 25 |
| 8 | −11.1% | ON-TARGET | 25 → 26 supporting |
| 9 | 0% | ON-TARGET exact mid | 25 → 26 supporting + **5th consecutive 0%-streak rebuild instance** (P0.R6.Z + P0.R8 + P0.R11 + P0.R9 + P0.R10; **5+ watch criteria REACHED** — `Doctrine-prediction-precision-improving-over-arc` sub-observation extension WARRANTED at this closure) |
| 10 | +11.1% | ON-TARGET | 25 → 26 supporting |
| 11 | +22.2% | SLIGHT-DRIFT-UP | HOLDS at 25 |
| ≥12 OR ≤6 | beyond ±30% | FALSIFICATION TRIGGER | demotes back to architect-memory |

**Architect closure-actual projection (Plan v1 §7 honest-count commitment)**: 9 anchors at exact mid (per Q5 RATIFIED at Phase 0 verdict).

---

## §8 Doctrine-firing projections at closure

If P0.R10 closes cleanly with closure-actual = 9 anchors at exact mid:

- `### Phase-0-granular-decomposition-enables-accurate-estimates` 25 → 26 supporting
- `Doctrine-prediction-precision-improving-over-arc` **5th consecutive 0%-streak rebuild instance** → **5+ watch criteria REACHED** → sub-observation extension WARRANTED at this closure-audit
- `### Pre-audit-quantifier-precision-refined-by-grep` STAYS at 8 instances (4th consecutive clean-confirmation per operational rule 3)
- `### Phase-0-catches-wrong-premise` STAYS at 13 (premise correct)
- `### Zero-precision-items-at-auditor-review` 30 → 31 (Plan v1 if cycle clears cleanly with 0 BLOCKING PIs at this surface)
- `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` 13 → 14 consecutive cycle (clean-pass mode)
- OPTIONAL-Plan-v2 sub-rule track record 14 → 15 proof cases (if 3-artifact cycle ships)
- `### Architect-reads-production-code-before-sign-off` 25 → 26 at closure-audit (8th-cycle self-sustaining adoption)
- Strict-industry-standard mode 92 → 95 applications + 27 → 28 closures
- Spec-first review cycle 101 → 104-for-104 at closure
- `### Grep-baseline-before-drafting` 59 → 62 instances
- Cross-cycle-handoff transparency 62 → 65 successful
- Spec-time grep-verification 69 → 72 instances
- `### Twin-filename-pitfall-prevention` 26 → 27 preventive events
- Auditor-Q5-estimates-trail-grep 31 → 32 banked closures
- Deferred-canary strategy 29 → 30 applications (with locked Path C grep-verify per P0.R9 lesson)
- CODE-TEMPLATE-MISIDENTIFICATION sub-shape: 3rd preventive-application instance (P0.R8 caught + P0.R11 + P0.R9 + P0.R10 preventive = 1 caught + 3 preventive)
- LINE-REF-DRIFT sub-shape: 2nd preventive application banked at architect-side Plan v1 refresh (drift +1 caught + refreshed); possible sub-shape BOTH-modes maturation evidence
- MEMORY-FILE INDEX GAP family: track-record stays at 5 if no new instance fires + cross-path discipline applied preventively per locked operational rule
- DEFERRED-CANARY-ENTRY-OMISSION sibling class: track-record stays at 2 if entry actually lands at `to_be_checked.md` per locked Path C grep-verify step (PowerShell fresh-disk read mechanism)
- NEW `feedback_closure_audit_verdict_cycle_elision.md` 1st instance banked at architect-memory + auditor-facing paths (per §6.1)

---

## §9 Architect-handoff items for auditor Plan v1 verdict + closure-audit forwarding commitment

1. **Pass-2 grep verification** (per `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` — 13th consecutive cycle at this Plan v1 surface): auditor independent re-grep of §1.1 5-row + §1.3 10-row + §1.4 9-row tables. **LINE-REF-DRIFT preventive applied at Plan v1 drafting** caught minor drift (pipeline.py:2411 → 2412 for P0.R3 canonical reference); refresh banked at §1.4.

2. **Q1-Q9 already RATIFIED at Phase 0 verdict** — no Plan v1 adjudication needed. Plan v1 §2 D-decisions are LOCKED at Phase 0 architect leans.

3. **Phase 0 absorption verification**:
   - **LINE-REF-DRIFT preventive re-verification (Obs #2 absorption)**: all line-ref claims grep-verified at Plan v1 drafting; §1.3 row 5 (HealthSnapshot.vram_budget at health.py:95) ✓ verified; §1.4 P0.R3 watchdog body ref refreshed `pipeline.py:2411 → :2412` (drift +1 caught preventively)
   - **§5 explicit 7-step implementation enumeration** (Recommendation #2 absorption): mutation-step independence + D2 4-site asymmetric mutations enumerated explicitly per P0.R11 Observation 1 absorption pattern
   - **A5 spec verifies `# CLEANUP:` annotation preservation** (Recommendation #3 absorption): source-inspection anchor scans `core/audio.py::stop_audio` source via `inspect.getsource` + asserts annotation comment AT pass line
   - **A4 spec verifies Q2 (b) abort-whole-stream + per-sentence count logging** (Recommendation #4 absorption): behavioral anchor verifies abort + record-once + log-format `(sentence 2/N)`
   - **§6 cross-path memory-file work scheduled** (Recommendation #5 absorption): new memory-file projection enumerated + cross-path verification protocol explicit
   - **§9 closure-audit verdict forwarding commitment** (Recommendation #6 + Obs #1 absorption): COMMITTED below

4. **Closure-audit verdict forwarding commitment** (Recommendation #6 + Obs #1 absorption): at P0.R10 Phase 7 closure-audit, architect explicitly forwards the closure-audit findings + cross-path verification results + any caught gaps to auditor for explicit ratification verdict BEFORE declaring P0.R10 CLOSED. Preserves the 4-step cycle integrity (Phase 0 verdict → Plan v1 verdict → closure-audit verdict → next-cycle Phase 0). This is the architect-side procedural correction for the elision at P0.R9 closure.

5. **Cross-path discipline preventive commitment** (per locked operational rule): if P0.R10 closure introduces any NEW memory files (§6 projects 1-2), architect verifies updates at BOTH paths; architect verifies DEFERRED-CANARY entry lands at `to_be_checked.md` via PowerShell fresh-disk read per P0.R9 closure-audit STALE-CACHED-VERIFICATION 2nd instance lesson.

6. **5+ watch criteria approaching for `Doctrine-prediction-precision-improving-over-arc`**: if closure-actual = 9 at exact mid, P0.R10 is the 5th consecutive 0%-streak rebuild instance. Sub-observation extension WARRANTED at this closure-audit under `### Phase-0-granular-decomposition-enables-accurate-estimates` parent doctrine body.

---

**End of Plan v1.** Ready for auditor verdict.
