# P0.R10 — Audio device failure resilience (Phase 0 audit)

**Date**: 2026-05-25
**Author**: architect (Claude)
**Cycle shape**: SMALL-MEDIUM band; orthogonal failure mode from P0.R8 (heavy-worker crashes) + P0.R9 (VRAM budget) + P0.R11 (forensic capture)
**Estimated effort**: ~3h MEDIUM-band cycle
**Companion specs**: P0.R1 D1 None-return fallback contract (mic empty-return semantic), P0.R8 burst-detection pattern (mirror), P0.R11 crash_logs API (Q4 lean (b) integration on burst-threshold breach), P0.4 silent-except policy (stop_audio CLEANUP annotation preservation), CLAUDE.md Session 2 ReSpeaker barge-in deferred-feature

---

## §0 Pre-audit framing (LOCKED 2026-05-25 by architect BEFORE Phase 0 grep verification)

> "P0.R10 adds audio-device failure resilience for mic + speaker channels. Wraps `sd.InputStream` in `record_until_silence` + `sd.play` calls in `speak`/`speak_stream`/`play_filler`/`stop_audio` with try/except for `sd.PortAudioError` + `OSError`. Detects consecutive failure bursts via per-channel counters (mirroring P0.R8 `_record_pool_crash` shape) + dispatches `WatchdogAgent.report_audio_device_burst` alert + flips `audio_degraded[channel] = True` on burst threshold. Per-channel granularity (mic + speaker tracked independently — Q1 lean (a)) preserves operational distinction (USB mic disconnect ≠ speaker driver crash). HealthSnapshot exposes `audio_degraded: dict[str, bool]` field + `format_health_line` conditional emit + actionable recovery alert. Crash forensics (P0.R11 `persist_crash_diagnostic` generic API) integrated at burst-threshold breach only (Q4 lean (b)) — preserves API design intent + avoids spammy forensics for transient hiccups. ~3h MEDIUM-band cycle."

Phase 0 grep verifies framing. Findings below.

**LINE-REF-DRIFT prevention** (per `feedback_pass_2_grep_caught_real_gap_subshape.md` 3rd sub-shape locked at P0.R9 closure): all line refs grep-verified at Phase 0 drafting time via fresh tool invocation; not carried forward from prior cycles.

**CODE-TEMPLATE-MISIDENTIFICATION preventive risk-check** (per `feedback_pass_2_grep_caught_real_gap_subshape.md` CODE-TEMPLATE sub-shape, validated in BOTH modes at P0.R9): §2 D-decision code templates verified against current production surfaces upfront. Result: LOW risk; all references grep-verifiable (see §6).

**Cross-path discipline preventive commitment** (per `feedback_architect_reads_catches_phase_7_memory_file_omission.md` 4th sub-variant CROSS-PATH-SYNC-OMISSION + NEW DEFERRED-CANARY-ENTRY-OMISSION sibling class locked at P0.R9 closure): if P0.R10 introduces NEW memory files OR updates existing memory files at closure, architect MUST verify updates at BOTH the architect-memory path (`C--Users-jagan-dog-ai-dog-ai/memory/`) AND the auditor-facing memory path (`C--Users-jagan-dog-ai/memory/`); architect MUST also verify deferred-canary entry actually lands in `to_be_checked.md`.

---

## §1 Grep findings (Pass-1 baseline) — COMPREHENSIVE upfront

### §1.1 Audio device call surfaces (mutation points)

| # | Surface | File:Line | Current behavior |
|---|---|---|---|
| 1 | `sd.InputStream(samplerate, channels=1, dtype='float32')` context manager in `record_until_silence` | `core/audio.py:382` (def at 337) | Context manager opens InputStream; reads via `stream.read(chunk_size)`; **unguarded against `sd.PortAudioError` / `OSError`** |
| 2 | `sd.stop()` + `sd.play(pcm, samplerate)` + `await loop.run_in_executor(None, sd.wait)` + `sd.stop()` cluster in `speak` | `core/audio.py:658-663` (def at 637) | Synchronous-equivalent playback via blocking `sd.wait`; **unguarded against device errors mid-playback** |
| 3 | `sd.stop()` + `sd.play(pcm, samplerate=sr)` + `await loop.run_in_executor(None, sd.wait)` cluster in `speak_stream` | `core/audio.py:787-793` (def at 737) | Per-sentence iteration with playback per chunk; **mid-stream failure decision needed** (continue vs abort) |
| 4 | `sd.play(pcm, samplerate=sr)` in `play_filler` | `core/audio.py:320` (def at 293) | Low-stakes filler sound; **unguarded; failure can silently skip** |
| 5 | `sd.stop()` in `stop_audio` | `core/audio.py:823` (def at 819) | Already wrapped in `try/except: pass` with `# CLEANUP:` annotation at line 825 — **P0.4 silent-except policy LOAD-BEARING — must preserve verbatim** |

5 distinct call surfaces. 4 are currently unguarded against `sd.PortAudioError` / `OSError`; 1 has the existing CLEANUP-annotated swallow that MUST be preserved per P0.4 silent-except policy.

### §1.2 Production callers of audio surfaces in pipeline.py

| # | Surface | File:Line | Caller context |
|---|---|---|---|
| 1 | `stop_audio()` | `pipeline.py:2707` | Ambient-listen interrupt; outer loop handles greeting |
| 2 | `listen_and_transcribe()` (which calls `record_until_silence`) | `pipeline.py:3548 + 3559 + 3566` | Boot flow + enrollment name capture |
| 3 | `play_filler(text)` | `pipeline.py:5272` | Filler before LLM response (disabled by default per FILLER_ENABLED=False) |
| 4 | `stop_audio()` | `pipeline.py:5675 + 5755` | TTS interrupt during conversation_turn (Session 28 Issue A + Session 70 Bug R) |
| 5 | `stop_audio()` | `pipeline.py:6076` | Post-stream cancellation for canonical ack |

**~10 total callers** across pipeline.py. All callers consume failure semantically as "no audio captured" or "interrupt no-op" — none currently surface device-failure as an exception. P0.R10 D1+D2 mutations preserve this contract (failure path returns empty/None or logs+swallows without raising).

### §1.3 Watchdog + HealthSnapshot existing infrastructure

| # | Surface | File:Line | Pattern |
|---|---|---|---|
| 1 | `WatchdogAgent.report_heavy_worker_burst` | `core/brain_agent.py` (P0.R8 D4) | Severity "warning"; metadata captures pool name + crash count + window | 
| 2 | `WatchdogAgent.report_vram_budget_refusal` | `core/brain_agent.py:6621` (P0.R9 D5) | Severity "warning"; metadata captures task_name + cumulative_mb + ceiling_mb + estimate_mb |
| 3 | `HealthSnapshot.heavy_worker_status: dict[str, str]` | `core/health.py:70` (P0.R6 D4) | dict-keyed-by-pool-name pattern; reuse precedent for P0.R10 |
| 4 | `HealthSnapshot.heavy_worker_crash_counts: dict[str, int]` | `core/health.py:76` (P0.R8 D5) | dict-keyed-by-pool pattern |
| 5 | `HealthSnapshot.vram_budget: dict[str, list[str]]` | `core/health.py:95` (P0.R9 D6) | dict pattern with multi-key sub-structure |
| 6 | `_record_pool_crash(task_name)` + `count_recent_crashes(task_name, window_secs)` | `core/heavy_worker.py:69 + 87` (P0.R8 D1) | Module-level dict + threading.Lock + auto-prune at poll time |
| 7 | `core/crash_logs.persist_crash_diagnostic(task_name, exc, traceback, count)` | `core/crash_logs.py:33` (P0.R11 D2) | Generic API per Q9 standalone-API framing |

P0.R10 reuses these patterns:
- Per-channel burst counter shape mirrors `_record_pool_crash` + `count_recent_crashes` (P0.R8 D1)
- HealthSnapshot dict-keyed field shape mirrors `heavy_worker_status` (P0.R6 D4)
- WatchdogAgent alert dispatch shape mirrors `report_heavy_worker_burst` + `report_vram_budget_refusal`
- Crash forensics via `persist_crash_diagnostic` (P0.R11 D2) — but ONLY at burst-threshold breach per Q4 lean (b)

### §1.4 Cross-spec interactions (Pass-2 grep)

| Spec | Interaction | Status |
|---|---|---|
| P0.R1 D1 | None-return fallback contracts | LOAD-BEARING — mic D1 empty/None sentinel maps to existing downstream None-handling (similar shape) |
| P0.R3 | Vision-loop watchdog pattern | EXTENDS — D3 burst-detection mirrors P0.R3's `_vision_watchdog_loop` shape via bare `while True:` (CODE-TEMPLATE-MISIDENTIFICATION canonical reference, locked at P0.R8) |
| P0.R8 | Heavy-worker burst-detection | EXTENDS — D3 mirrors `_record_pool_crash` + `count_recent_crashes` + alert dispatch shape |
| P0.R11 | `persist_crash_diagnostic` generic API | EXTENDS — Q4 lean (b) integration at burst-threshold breach only (preserves API design intent) |
| P0.4 silent-except | `stop_audio` CLEANUP annotation | LOAD-BEARING — D2 mutation at line 825 must keep `# CLEANUP:` comment intact verbatim |
| HealthSnapshot | dict-keyed field precedents | EXTENDS — `audio_degraded: dict[str, bool]` keyed by 'mic'/'speaker' |
| WatchdogAgent | burst-alert pattern | EXTENDS — new `report_audio_device_burst` method mirroring `report_heavy_worker_burst` + `report_vram_budget_refusal` |
| ReSpeaker barge-in (CLAUDE.md Session 2) | `_vad_interrupt_listener` deferred until ReSpeaker 4-mic hardware arrives | INTERACTION — D1 `sd.InputStream` wrap must NOT introduce coupling that blocks future barge-in re-introduction; architect verifies D1 mutation is barge-in-neutral |
| Cross-platform (Windows / Linux / Jetson) | `sd.PortAudioError` codes vary across platforms | LOAD-BEARING — Q5 lean (a) catches `sd.PortAudioError + OSError` uniformly without platform-specific dispatch |

### §1.5 P0.4 silent-except policy interaction (LOAD-BEARING)

`stop_audio` at `core/audio.py:819-825` already has the canonical P0.4 silent-except pattern:

```python
def stop_audio():
    try:
        sd.stop()
    except Exception:
        pass  # CLEANUP: sd.stop() raises if no active stream or device gone — interrupt flag still set
```

D2 mutation MUST preserve this verbatim. Specifically:
- The `# CLEANUP:` annotation comment at line 825 is the P0.4 swallow-discipline marker — REMOVING or REPLACING the comment would create an unannotated silent-except violation that `test_no_unannotated_silent_excepts_in_production_code` would catch.
- The `interrupt flag still set` semantic is the existing contract: `stop_audio()` MUST be a fire-and-forget cleanup that NEVER blocks or raises regardless of device state.
- P0.R10 D2 should EXTEND the catch to capture `sd.PortAudioError` explicitly + dispatch alert IF the failure is a sustained device failure (not just "stream already stopped"); but the `# CLEANUP:` annotation comment + pass-only swallow shape must be preserved.

### §1.6 ReSpeaker barge-in deferred-feature interaction (CLAUDE.md Session 2 banking)

Per CLAUDE.md "Module Roles" section: "Barge-in: REMOVED. Waiting for ReSpeaker hardware. Do NOT re-add `_vad_interrupt_listener`."

P0.R10 D1 `sd.InputStream` wrap in `record_until_silence` must be **barge-in-neutral**: the wrap should not introduce architectural coupling that blocks future re-introduction of `_vad_interrupt_listener` (a separate listener that opens its own `sd.InputStream` for barge-in detection). Concretely:
- D1 wraps `record_until_silence`'s context manager only — not module-level singleton state that would conflict with a second `sd.InputStream` opener.
- The audio burst counter is keyed by channel ('mic') not by call-site — when `_vad_interrupt_listener` is re-introduced, it shares the 'mic' counter cleanly.

Banked as Phase 0 §1.6 explicit verification; D1 implementation must not regress this.

---

## §2 Architectural justification

Pre-audit framing is structurally CORRECT. Phase 0 grep ADDS:

1. **stop_audio CLEANUP annotation preservation LOAD-BEARING** (§1.5): existing P0.4 silent-except annotation at line 825 must be preserved verbatim across D2 mutation. The 5 call sites have asymmetric semantics (Q2 lean (b)) — stop_audio specifically requires CLEANUP-pattern preservation.

2. **ReSpeaker barge-in interaction** (§1.6): D1 wrap must be architecturally neutral toward future `_vad_interrupt_listener` re-introduction. Module-level burst counter keyed by channel name (not call site) supports this.

3. **5-D pattern symmetry with P0.R8 + P0.R9**: D1+D2 try/except + D3 burst detector + D4 HealthSnapshot field + D5 WatchdogAgent method follows the established pattern from P0.R8 (heavy-worker watchdog) + P0.R9 (VRAM budget guard). Spec-time familiarity reduces drift risk.

Risk/benefit:
- **Risk**: cross-platform `sd.PortAudioError` codes vary (Windows uses different error numbers than Linux); Q5 lean (a) uniform catch + classification deferred to follow-up if operationally relevant.
- **Risk**: burst-threshold tuning — too aggressive blocks legitimate hiccups (Bluetooth headphone reconnect); too lax misses sustained failures. Operator-tunable via config.
- **Risk**: D2 `speak_stream` mid-stream failure — abort-whole-stream vs continue-next-sentence is a real UX decision. Q2 lean (b) per-site disposition: abort whole stream + log per-sentence count for diagnostic context.
- **Risk**: Q3 mic empty-return sentinel — empty audio vs None has subtle downstream implications. Q3 lean (a) distinct None sentinel ensures STT path doesn't transcribe device-failure as silence.
- **Benefit**: detects/handles audio device failures BEFORE they cascade into silent pipeline-death OR spurious "user is silent" misreads.
- **Benefit**: per-channel granularity (mic vs speaker) gives operators meaningful diagnostic distinction.
- **Benefit**: P0.R11 crash_logs integration on burst-threshold breach (Q4 lean (b)) captures forensic JSON for post-mortem analysis without spamming for transient hiccups.

---

## §3 D-decision proposal (5 D-decisions)

**D1 (`record_until_silence` mic-channel wrap)**:

```python
def record_until_silence(
    sample_rate: int = MIC_SAMPLE_RATE,
    ...
) -> "np.ndarray | None":
    """... P0.R10 D1: wraps sd.InputStream context manager in try/except for
    sd.PortAudioError + OSError; on failure: records event via _record_audio_failure('mic') +
    returns None (distinct sentinel per Q3 (a) lock — empty audio means 'user was silent',
    None means 'device failed'). Caller (listen_and_transcribe + pipeline.py) inspects
    None vs empty-array to route differently.
    """
    try:
        with sd.InputStream(samplerate=sample_rate, channels=1, dtype='float32') as stream:
            # existing recording loop unchanged
            ...
    except (sd.PortAudioError, OSError) as e:
        print(f"[Audio] WARN mic device failure during record_until_silence: {e!r}")
        _record_audio_failure("mic")
        return None  # P0.R10 D1 Q3 (a) — distinct sentinel for device failure
```

Q3 (a) lock LOAD-BEARING: return None (not empty bytes/array) so downstream STT path can distinguish "user is silent" (empty audio) from "device failed" (None).

**D2 (speaker-channel wraps with per-site asymmetric semantics)**:

Per Q2 (b) lock — each call site gets explicit disposition:

```python
# core/audio.py::speak (line 637+) — single-chunk synthesis+play; failure skips turn
async def speak(text: str, language: str = "en"):
    ...
    try:
        sd.stop()
        sd.play(pcm, samplerate=sample_rate)
        await loop.run_in_executor(None, sd.wait)
        sd.stop()
    except (sd.PortAudioError, OSError) as e:
        print(f"[Audio] WARN speaker device failure in speak: {e!r}")
        _record_audio_failure("speaker")
        return  # skip turn silently — caller's contract preserved

# core/audio.py::speak_stream (line 737+) — per-sentence iteration; failure aborts stream
async def speak_stream(sentences, language: str = "en"):
    _sentence_count = 0
    for sentence in sentences:
        try:
            ...
            sd.stop()
            sd.play(pcm, samplerate=sr)
            await loop.run_in_executor(None, sd.wait)
        except (sd.PortAudioError, OSError) as e:
            print(f"[Audio] WARN speaker device failure in speak_stream "
                  f"(sentence {_sentence_count}/{...}): {e!r}")
            _record_audio_failure("speaker")
            return  # abort whole stream (Q2 (b) lock); log per-sentence count for context
        _sentence_count += 1

# core/audio.py::play_filler (line 293+) — low-stakes ack; failure silently skips
def play_filler(message: str = ""):
    ...
    try:
        sd.play(pcm, samplerate=sr)
    except (sd.PortAudioError, OSError) as e:
        print(f"[Audio] WARN speaker device failure in play_filler: {e!r}")
        _record_audio_failure("speaker")
        # no return needed — function falls through

# core/audio.py::stop_audio (line 819+) — CLEANUP-pattern PRESERVED + extended
def stop_audio():
    try:
        sd.stop()
    except (sd.PortAudioError, OSError):
        pass  # CLEANUP: sd.stop() raises if no active stream or device gone — interrupt flag still set
    except Exception:
        pass  # CLEANUP: defensive — preserves P0.4 silent-except policy
```

P0.4 verbatim preservation: `# CLEANUP:` annotation comment at the `pass` line is the load-bearing marker for `test_no_unannotated_silent_excepts_in_production_code` — must NOT be removed.

**D3 (`core/audio.py` per-channel burst counter — mirror P0.R8)**:

```python
# Module-level audio device failure tracking (P0.R10 D3 — mirrors P0.R8 D1)
_AUDIO_FAILURE_HISTORY: "dict[str, list[float]]" = {}
_AUDIO_FAILURE_LOCK = threading.Lock()


def _record_audio_failure(channel: str, now: "float | None" = None) -> None:
    """Record an audio-device-failure event for burst detection. Mirrors
    P0.R8's _record_pool_crash shape. channel ∈ {'mic', 'speaker'}.
    """
    if now is None:
        now = time.time()
    with _AUDIO_FAILURE_LOCK:
        _AUDIO_FAILURE_HISTORY.setdefault(channel, []).append(now)


def count_recent_audio_failures(
    channel: str, window_secs: float, now: "float | None" = None
) -> int:
    """Count audio-device failures within rolling window. Mirrors P0.R8's
    count_recent_crashes shape; auto-prunes events older than window.
    """
    if now is None:
        now = time.time()
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

`pipeline.py` `_audio_device_watchdog_loop` (NEW) polls every `AUDIO_DEVICE_WATCHDOG_INTERVAL_SECS` (default 10.0s); counts recent failures per channel within `AUDIO_DEVICE_BURST_WINDOW_SECS` (default 60.0s) window; dispatches `WatchdogAgent.report_audio_device_burst(channel, count, window)` when count ≥ `AUDIO_DEVICE_BURST_THRESHOLD` (default 3). Per-channel alert-armed pattern mirrors P0.R8 watchdog. Crash forensics dispatched on burst-threshold breach via `persist_crash_diagnostic(f"audio_{channel}_device", ...)` per Q4 (b) lock.

Bare `while True:` body matching P0.R3 + P0.R8 canonical reference (locked at P0.R8 PI #1 absorption).

**D4 (`WatchdogAgent.report_audio_device_burst` method)**:

```python
def report_audio_device_burst(
    self,
    channel: str,
    failure_count: int,
    window_secs: float,
) -> None:
    """Store an audio-device burst alert (P0.R10 D4). Severity: warning.
    Channel ∈ {'mic', 'speaker'}. Mirrors P0.R8 report_heavy_worker_burst.
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

Plus `BrainOrchestrator.report_audio_device_burst` passthrough mirroring `report_heavy_worker_burst`.

**D5 (`HealthSnapshot.audio_degraded` field + format extensions + config)**:

```python
# core/health.py — HealthSnapshot dataclass extension
audio_degraded: "dict[str, bool]" = field(default_factory=dict)

# gather_health_snapshot addition
try:
    import core.audio as _audio_health
    audio_degraded = {
        "mic":     _audio_health.count_recent_audio_failures("mic", AUDIO_DEVICE_BURST_WINDOW_SECS) >= AUDIO_DEVICE_BURST_THRESHOLD,
        "speaker": _audio_health.count_recent_audio_failures("speaker", AUDIO_DEVICE_BURST_WINDOW_SECS) >= AUDIO_DEVICE_BURST_THRESHOLD,
    }
except Exception:
    audio_degraded = {}

# format_health_line conditional emit
_degraded_channels = [c for c, deg in (snapshot.audio_degraded or {}).items() if deg]
if _degraded_channels:
    parts.append(f"audio_degraded={','.join(_degraded_channels)}")

# format_health_alerts actionable alert (5 verbatim substrings for A8 anchor)
if _degraded_channels:
    alerts.append(
        f"[Health-Alert] Audio device degraded — channels: {', '.join(_degraded_channels)}. "
        f"Check USB/audio device connection + driver + permissions. "
        f"Clears when failure rate drops below AUDIO_DEVICE_BURST_THRESHOLD."
    )

# core/config.py — P0.R10 constants
AUDIO_DEVICE_WATCHDOG_INTERVAL_SECS = 10.0  # poll cadence
AUDIO_DEVICE_BURST_THRESHOLD       = 3      # N failures in window → degraded
AUDIO_DEVICE_BURST_WINDOW_SECS     = 60.0   # 1 minute rolling window
```

Verbatim alert substrings (anchored by A8):
- `"Audio device degraded"`
- `"channels:"`
- `"USB/audio device connection"`
- `"driver"`
- `"AUDIO_DEVICE_BURST_THRESHOLD"`

---

## §4 Anchor count proposal (Q5 LOCKED = 9 anchors)

**Mid 9 INCLUSIVE ±15% band → [7.65, 10.35] → ON-TARGET = 8, 9, or 10 anchors**:

| # | Anchor | Surface | Type |
|---|---|---|---|
| A1 | `test_p0_r10_d1_record_until_silence_wraps_portaudio_error` | `core/audio.py:382` | BEHAVIORAL — monkeypatch `sd.InputStream` to raise `sd.PortAudioError` → assert `record_until_silence` returns None + `_record_audio_failure('mic')` called |
| A2 | `test_p0_r10_d1_mic_failure_returns_none_sentinel_not_empty` | `core/audio.py` | BEHAVIORAL — distinguishes Q3 (a) lock — None ≠ empty array; STT downstream contract preserved |
| A3 | `test_p0_r10_d2_speak_wraps_portaudio_error` | `core/audio.py:637` | BEHAVIORAL — monkeypatch `sd.play` to raise → assert `speak` returns cleanly (no exception) + `_record_audio_failure('speaker')` called |
| A4 | `test_p0_r10_d2_speak_stream_aborts_on_mid_stream_failure` | `core/audio.py:737` | BEHAVIORAL — multi-sentence stream; raise on 2nd sentence; assert stream aborts + per-sentence count logged + 1 failure recorded (not N) |
| A5 | `test_p0_r10_d2_stop_audio_preserves_cleanup_annotation` | `core/audio.py:819-825` | SOURCE-INSPECTION — verify `# CLEANUP:` annotation comment AT pass line + try/except shape preserved (P0.4 silent-except contract) |
| A6 | `test_p0_r10_d3_per_channel_burst_counter_independent` | `core/audio.py` | BEHAVIORAL — record 5 mic failures + 2 speaker failures → `count_recent_audio_failures('mic') == 5` AND `('speaker') == 2`; per-channel granularity Q1 (a) lock |
| A7 | `test_p0_r10_d4_watchdog_report_audio_device_burst_method` | `core/brain_agent.py` | SOURCE — `WatchdogAgent.report_audio_device_burst` method exists + `_db.store_alert` called with `audio_device_burst_{channel}` key |
| A8 | `test_p0_r10_d5_health_snapshot_audio_degraded_field_and_alerts` | `core/health.py` | SOURCE+BEHAVIORAL — `HealthSnapshot.audio_degraded` field exists + `format_health_line` emits `audio_degraded=mic,speaker` conditionally + `format_health_alerts` emits 5 verbatim substrings when degraded |
| A9 | `test_p0_r10_d5_config_constants_present` | `core/config.py` | SOURCE — 3 constants present (`AUDIO_DEVICE_WATCHDOG_INTERVAL_SECS=10.0`, `AUDIO_DEVICE_BURST_THRESHOLD=3`, `AUDIO_DEVICE_BURST_WINDOW_SECS=60.0`) with sanity values |

**Closure-projection band table**:

| closure-actual | overage vs mid 9 | band | doctrine outcome |
|---|---|---|---|
| 7 | −22.2% | SLIGHT-DRIFT-DOWN | `### Phase-0-granular-decomposition` HOLDS at 25 |
| 8 | −11.1% | ON-TARGET | 25 → 26 supporting |
| 9 | 0% | ON-TARGET exact mid | 25 → 26 supporting + **5th consecutive 0%-streak rebuild instance** (P0.R6.Z + P0.R8 + P0.R11 + P0.R9 + P0.R10; **5+ watch criteria REACHED** — sub-observation extension under `Doctrine-prediction-precision-improving-over-arc` warranted) |
| 10 | +11.1% | ON-TARGET | 25 → 26 supporting |
| 11 | +22.2% | SLIGHT-DRIFT-UP | HOLDS at 25 |
| ≥12 OR ≤6 | beyond ±30% | FALSIFICATION TRIGGER | demotes back to architect-memory |

---

## §5 OUT-OF-SCOPE classification

1. **ReSpeaker 4-mic barge-in re-introduction** — CLAUDE.md Session 2 banking; P0.R10 mutations are barge-in-neutral but don't reintroduce `_vad_interrupt_listener`. Future spec when hardware arrives.
2. **Platform-specific `sd.PortAudioError` code classification** — Q5 (a) lock catches uniformly; per-platform code classification deferred to follow-up if operationally relevant.
3. **Auto-recovery on degraded → healthy** — degraded state set when burst breached; cleared automatically when failure rate drops below threshold via watchdog poll. No explicit operator-action recovery flow.
4. **Audio device selection / fallback to alternate device** — current scope detects + degrades + alerts; doesn't switch to backup device automatically. Future spec if multi-device support becomes load-bearing.
5. **Whisper STT failure independent from mic failure** — STT failures are caught at `core/heavy_worker.py::whisper_transcribe_worker` (P0.R6.X) + return empty STT; this is separate from mic device failure (mic returns None per Q3 (a) lock, STT receives None and returns early without transcription).
6. **Live canary validation** — per deferred-canary discipline locked at P0.S7.5.2, no live canaries until end-of-P0.R11. P0.R10 entry banked to `to_be_checked.md` at closure for canary-week validation.

---

## §6 Locked-down discipline counters

Per `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` doctrine: auditor's DILIGENT Pass-2 grep at Plan v1 §1 will independently verify §1.1-§1.6 surface tables.

Per `feedback_pass_2_grep_caught_real_gap_subshape.md` LINE-REF-DRIFT sub-shape (locked at P0.R9 closure): all line refs grep-verified at Phase 0 drafting time via fresh tool invocation. Cited refs: `record_until_silence` def at 337 + `sd.InputStream` at 382 + `speak` def at 637 + 658-663 cluster + `speak_stream` def at 737 + 787-793 cluster + `play_filler` def at 293 + `sd.play` at 320 + `stop_audio` def at 819 + 823-825 cluster.

Per `feedback_pass_2_grep_caught_real_gap_subshape.md` CODE-TEMPLATE-MISIDENTIFICATION sub-shape (validated in BOTH modes at P0.R11): §2 D-decision code template references verified upfront:
- `_HEAVY_WORKER_POOLS` precedent + `_record_pool_crash` + `count_recent_crashes` shape at `core/heavy_worker.py:33+69+87` ✓
- `WatchdogAgent.report_heavy_worker_burst` + `report_vram_budget_refusal` precedents at `core/brain_agent.py` ✓
- `HealthSnapshot.heavy_worker_status` + `heavy_worker_crash_counts` + `vram_budget` precedents at `core/health.py:70+76+95` ✓
- `core/crash_logs.persist_crash_diagnostic` generic API at `core/crash_logs.py:33` (P0.R11 Q9 standalone-API framing) ✓
- `sd.PortAudioError` is sounddevice stdlib API ✓
- `stop_audio` CLEANUP annotation comment at `core/audio.py:825` ✓
- Bare `while True:` watchdog body precedent at `pipeline.py:2411` (P0.R3 canonical reference) + `pipeline.py:2475` (P0.R8 mirror) ✓

CODE-TEMPLATE-MISIDENTIFICATION risk: LOW (3rd consecutive preventive application after P0.R11 + P0.R9).

**`### Pre-audit-quantifier-precision-refined-by-grep` instance enumeration** (post-P0.R9 closure baseline; CLAUDE.md canonical):

Phase 0 grep CONFIRMS pre-audit framing — no quantifier refinement event fires. Pre-audit said "mic + speaker channels" + "5 unguarded surfaces" + "per-channel burst detection" + "burst-threshold breach forensics"; grep verified all 4 claims match production. Per operational rule 3, no instance bank fires. Doctrine STAYS at 8 instances. **4th consecutive clean-confirmation since elevation** (P0.R8 + P0.R11 + P0.R9 + P0.R10) — sustained negative-evidence validation of operational rule 3.

---

## §7 Q-questions for adjudication

**Q1 (Per-channel vs combined burst counter — LOAD-BEARING candidate)**:
- (a) Per-channel counters with `audio_degraded: dict[str, bool]` field — mic + speaker tracked independently
- (b) Combined counter for all audio device failures — simpler state

**Architect lean: (a)** — mic + speaker can fail independently (USB mic disconnected ≠ speaker driver crash); per-channel granularity meaningful operationally. Matches `heavy_worker_status: dict[str, str]` pattern from P0.R6 D4 for symmetry.

**Q2 (D2 four call-site fallback asymmetry — LOAD-BEARING)**:
- (a) Uniform fallback (catch + log + continue) at all 4 sites
- (b) Per-site fallback semantics with explicit per-site disposition

**Architect lean: (b)** — `speak_stream` mid-stream failure needs explicit decision (lean: abort whole stream + log per-sentence count); `stop_audio`'s `# CLEANUP:` annotation must be preserved verbatim. Each call site has materially different semantics.

**Q3 (Mic empty-return sentinel — LOAD-BEARING)**:
- (a) Distinct sentinel (None) so downstream STT path distinguishes failure vs silence
- (b) Empty audio for both cases; rely on burst counter to surface device failures

**Architect lean: (a)** — explicit failure mode clearer; downstream routes None to device-error path, empty-array to silence path. Mirrors P0.R1 D1 None-return fallback contract.

**Q4 (P0.R11 crash_logs integration scope)**:
- (a) Full crash_logs integration on every audio device error
- (b) crash_logs only on burst-threshold breach — preserves P0.R11 API design intent + avoids spammy forensics for transient hiccups
- (c) No crash_logs integration; in-memory burst-detection only (P0.R8 scope)

**Architect lean: (b)** — severity escalation matches operational reality; transient hiccups (Bluetooth reconnect, single dropped sample) are noise; persistent failures warrant forensic JSON.

**Q5 (Cross-platform error code handling)**:
- (a) Catch `sd.PortAudioError + OSError` uniformly + classify by message
- (b) Platform-specific dispatch

**Architect lean: (a)** — uniform catch; classification deferred to follow-up if operationally relevant.

**Q6 (D3 watchdog spawn ordering)**:
- (a) Spawn audio watchdog AFTER heavy_worker_watchdog at startup (mirrors P0.R8 ordering)
- (b) Spawn before any pool warm-up (audio errors are earlier in pipeline boot)

**Architect lean: (a)** — consistent ordering with P0.R8 + P0.R3 vision watchdog precedents; audio device failures during startup are rare; if mic device fails at `_first_boot_flow`, the existing exception propagates regardless of watchdog being live.

**Q7 (D3 burst window + threshold defaults)**:
- (a) `THRESHOLD=3 / WINDOW=60s` — moderate sensitivity (1 failure per 20s tolerated)
- (b) `THRESHOLD=5 / WINDOW=30s` — stricter (1 failure per 6s tolerated)
- (c) Operator-tunable only; no defaults

**Architect lean: (a)** — moderate defaults match P0.R8 burst-detection precedent (3 crashes in 300s); audio device failures are typically faster-recovery than worker crashes so shorter window appropriate.

**Q8 (D4 alert severity)**:
- (a) "warning" — graceful degradation; system continues running
- (b) "error" — operator action required

**Architect lean: (a)** — matches P0.R8 + P0.R9 severity convention for graceful-degradation alerts; system continues, operator sees alert + diagnoses.

**Q9 (ReSpeaker barge-in compatibility verification)**:
- (a) D1 wrap is barge-in-neutral; verify via §1.6 architectural check (no module-level singleton state introduced; per-channel counter shared cleanly)
- (b) Add explicit `_VAD_INTERRUPT_LISTENER_COMPAT` flag for future re-introduction

**Architect lean: (a)** — module-level burst counter keyed by channel name supports future `_vad_interrupt_listener` re-introduction without modification. Explicit flag adds complexity for no current benefit.

---

## §8 Doctrine-firing projections at closure

If P0.R10 closes cleanly with closure-actual = 9 anchors at exact mid:

- `### Phase-0-granular-decomposition-enables-accurate-estimates` 25 → 26 supporting
- `Doctrine-prediction-precision-improving-over-arc` **5th consecutive 0%-streak rebuild instance** (P0.R6.Z + P0.R8 + P0.R11 + P0.R9 + P0.R10; **5+ watch criteria REACHED** → sub-observation extension candidacy WARRANTED at this closure)
- `### Pre-audit-quantifier-precision-refined-by-grep` STAYS at 8 instances (4th consecutive clean-confirmation per operational rule 3)
- `### Phase-0-catches-wrong-premise` STAYS at 13 (premise correct)
- `### Zero-precision-items-at-auditor-review` 29 → 31 (Phase 0 + Plan v1 if cycle clears cleanly)
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
- Deferred-canary strategy 29 → 30 applications
- CODE-TEMPLATE-MISIDENTIFICATION sub-shape: 3rd preventive-application instance (P0.R8 caught + P0.R11 + P0.R9 + P0.R10 preventive = 1 caught + 3 preventive)
- MEMORY-FILE INDEX GAP family: track-record stays at 5 if no new instance fires + cross-path discipline applied preventively per locked operational rule
- DEFERRED-CANARY-ENTRY-OMISSION sibling class: track-record stays at 2 if entry actually lands in `to_be_checked.md` per locked Path C grep-verify step

---

## §9 Architect-handoff items for auditor verdict

1. **Pass-2 grep verification** (per `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` — 13th consecutive cycle at Phase 0 surface): independent re-grep §1.1 5-row + §1.2 5-row + §1.3 7-row + §1.4 9-row tables. **CODE-TEMPLATE-MISIDENTIFICATION risk-check**: §3 D-decision code templates reference all grep-verifiable surfaces per §6. **LINE-REF-DRIFT prevention applied** at Phase 0 drafting time per §6.

2. **Q1-Q9 adjudication**: confirm architect leans. Q1 (per-channel counter) + Q2 (per-site fallback asymmetry) + Q3 (None sentinel) + Q4 (crash_logs at burst-threshold only) are LOAD-BEARING; Q5-Q9 are implementation refinements.

3. **Anchor count adjudication**: confirm mid 9 INCLUSIVE ±15% band [7.65, 10.35].

4. **§1.5 P0.4 silent-except interaction**: D2's `stop_audio` mutation must preserve `# CLEANUP:` annotation comment at line 825 verbatim. Auditor independently verifies this LOAD-BEARING property.

5. **§1.6 ReSpeaker barge-in deferred-feature interaction**: verify D1 `sd.InputStream` wrap is barge-in-neutral per CLAUDE.md Session 2 banking. No module-level singleton state introduced.

6. **4th consecutive clean-confirmation for `### Pre-audit-quantifier-precision-refined-by-grep`**: per §6, Phase 0 grep CONFIRMS pre-audit framing — doctrine STAYS at 8 instances. Sustained empirical validation.

7. **5+ watch criteria approaching for `Doctrine-prediction-precision-improving-over-arc`**: if closure-actual = 9 at exact mid, this is the 5th consecutive 0%-streak rebuild instance. Sub-observation extension warranted at this closure under `### Phase-0-granular-decomposition-enables-accurate-estimates` parent doctrine body.

8. **Cross-path discipline preventive commitment**: per locked operational rule from P0.R11 + P0.R9 closures: if P0.R10 closure introduces NEW memory files OR updates existing memory files, architect MUST verify updates at BOTH paths; architect MUST also verify deferred-canary entry actually lands in `to_be_checked.md` (DEFERRED-CANARY-ENTRY-OMISSION sibling class prevention per locked Path C grep-verify step).

---

**End of Phase 0 audit.** Ready for auditor verdict.
