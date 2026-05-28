> **CHAPTER 02 — Lifecycle + Pipeline States** | Sourced from `everything_about_system.md` §10-15 (verbatim mechanical extraction per Plan v2 §1.6 section-number stability invariant).

---

## 10. First-Boot Flow — Enrolling the Best Friend

When `db.get_best_friend()` returns None, the pipeline enters `first_boot_flow()`. This is a deliberately slow, conversational sequence — the goal is for the user to feel *greeted into* the system, not enrolled into it.

### 10.1 The dialogue

The flow is three exchanges:

1. **System**: "Hey there... are you my best friend?"
2. **User**: (something affirmative, e.g. "Yeah, I am.")
3. **System**: "Wow! What's your name?"
4. **User**: "My name is Jagan."
5. **System**: "Wait, let me see you clearly, Jagan... I want to remember you from now on."
6. *(enrollment capture — ~12 seconds, 20 face embeddings, anti-spoof gated)*
7. **System**: "Got you, Jagan! From now on, you're my best friend. I'll never forget you."

### 10.2 What happens under the hood

- The pipeline enters `PipelineState.ENROLLING`.
- For up to ~12 seconds, the vision loop captures 20 distinct face embeddings from varying angles, each passed through V1 (quality), V2 (yaw), V3 (temporal buffer), anti-spoof, and diversity gates.
- Each passing embedding is written to `embeddings` table with `source='enrollment'`.
- When 20 samples are collected (or time runs out with at least N_INITIAL_FACE=5), the person is written to `persons` with `person_type='best_friend'`.
- `FAISS._rebuild_faiss()` rebuilds the index from DB.
- A greeting is generated and spoken.
- Pipeline transitions ENROLLING → WATCHING.

### 10.3 Why this is a separate flow from background enrollment

A background-enrollment flow (that we used to have) would have been more convenient: user walks in front of the camera, system enrolls them silently, asks their name later. We rejected this because:

- The first interaction shapes the relationship. If the first thing the system does is "secretly memorise your face while you're standing in front of it", the feel is wrong. The explicit "Wait, let me see you clearly" turns the act of capture into consent.
- Anti-spoof is more reliable when the user is actively facing the camera. Passive enrollment can pick up angles the anti-spoof model has never seen.
- The best friend slot is privileged. An accidental enrollment of the wrong person into `best_friend` would be catastrophic for privacy and control. The explicit dialogue makes mis-enrollment essentially impossible.

### 10.4 Anti-spoof gate placement (Session 22)

Anti-spoof is called inside the capture loop *after* V1 (quality ≥ 0.50) and V2 (yaw ≤ 60°) gates passed. So the sequence per candidate frame is:

```
face detected
  ↓ V1: face_quality_score >= FACE_QUALITY_ENROLLMENT (0.50)
  ↓ V2: |estimate_yaw_from_landmarks| <= 60°
  ↓ AntiSpoofChecker.verify_live(frame, bbox)
  ↓ V3: TemporalEmbeddingBuffer.add_and_pool(track_id, emb)
  ↓ Diversity gate: cos-sim with existing gallery < 0.92
  ↓ INSERT INTO embeddings
```

If anti-spoof fails for every single candidate frame in the capture window, the `spoof_blocked` flag trips and the system says "I can't confirm you're real — try again in better lighting." This is a user-facing message, not a silent fail.

## 11. Daily-Use Flow — Returning User

When `db.get_best_friend()` returns the best friend, the pipeline enters WATCHING immediately. This is the hot path — the system spends 99% of its life here.

### 11.1 The WATCHING loop

- Camera and mic are active.
- Vision detects and recognises faces. On first recognition of a known person, the greeting cooldown (`GREET_COOLDOWN=300s`) is checked. If expired, `_open_session(person_id, name, "face")` opens a session and a greeting is generated and spoken.
- Voice triggers are handled by the same loop via the ambient listen sub-path (§19) — if somebody speaks without being on-camera, the pipeline voice-identifies them, opens a voice-started session if the voice matches a known person, or applies the engagement gate if the voice doesn't match anyone in the gallery.
- Once a session is open, the pipeline transitions to LISTENING and enters the conversation sub-loop.

### 11.2 The conversation sub-loop

- Pipeline state is LISTENING.
- The audio module captures a turn (`listen()`), ending at Smart-Turn completion or SILENCE_DURATION fallback.
- Voice ID runs on the captured audio.
- `_resolve_actual_speaker` resolves who actually spoke (may be a different person than the current session holder).
- If the resolution says "switch", the session switches.
- `conversation_turn(actual_pid, text, audio_buf)` runs. The brain generates a response; TTS speaks it; the pipeline updates session state; logs the turn.
- Voice is accumulated via Path A/B/C.
- Pipeline returns to LISTENING for the next turn in the same session, unless the session expired (see §51).

### 11.3 KAIROS — proactive initiation

If the user has been silent for `KAIROS_SILENCE_THRESHOLD=30s` while in an active session, the brain is poked with a prompt: "The user has been silent for 30 seconds. Say something natural if you have a question or observation, or respond with the single word SILENT if you don't." The brain either initiates or stays silent. This is the only place the robot volunteers speech unprompted.

### 11.4 Session closure

A session closes when:
- VOICE_SESSION_TIMEOUT=30s has elapsed since the last time the holder spoke (voice-started session).
- FACE_LOSS_GRACE=10s has elapsed since their face was last seen (face-started session).
- Another person's voice confidently switched the session away and the displaced session has been silent for VOICE_SESSION_TIMEOUT.
- A force-close trigger fires (DISPUTE_MAX_DURATION, SHUTDOWN tool, etc.).

On close, `_close_session(pid)` runs, the BrainOrchestrator's `notify_session_end(pid, name)` fires, and any async session-end tasks spawn (household extraction, insight episode storage, prompt pref final analysis, visitor alert if applicable).

## 12. Shutdown — Graceful and Forced

### 12.1 Graceful shutdown (Ctrl+C once)

When SIGINT is received:
1. `_shutdown_event.set()` signals every async task.
2. The main event loop exits its `while not _shutdown_event.is_set():` guard.
3. `Camera.close()` releases the cv2 capture device.
4. `BrainOrchestrator.shutdown()` cancels the agent loop and closes `BrainDB._conn` cleanly. Any pending writes are flushed via `_safe_commit`.
5. Open `_voice_tasks` (async accumulation tasks) are awaited with a 2-second timeout.
6. `_cloud_monitor_task` is cancelled.
7. `state.py::write_state(status="offline")` writes the final IPC state.
8. The Python process exits.

Total graceful-shutdown time: ~2 seconds.

### 12.2 Forced shutdown (Ctrl+C twice)

If a second SIGINT arrives during graceful shutdown (e.g., the agent loop is hanging on a DB commit), the signal handler calls `os._exit(1)`. This bypasses normal Python cleanup — the DB journal may be in WAL, which SQLite recovers from on next open. FAISS index in memory is lost; it's rebuilt from DB at next startup.

This is the escape hatch. We never want a user to have to `kill -9` the process.

### 12.3 Why not just register atexit handlers?

We used to. They ran unreliably on Windows because `atexit` is called for normal interpreter shutdown, not for SIGINT-triggered exits. Explicit signal handling gives us deterministic behaviour.

## 13. Factory Reset

Factory reset wipes every piece of runtime state and returns the system to a "never been run" state. This is destructive and not reversible short of restoring a backup.

### 13.1 What gets wiped

- `faces/faces.db` (all persons, embeddings, voice embeddings, conversation log, silent observations, visitor log)
- `faces/faiss.index` (rebuilt empty)
- `faces/brain.db` (all knowledge, schema catalog, agent log, preferences, episodes, nudges, household facts, social mentions)
- `faces/brain_graph/` (Kuzu directory, removed via `shutil.rmtree`)
- `faces/photos/` (face crops if present)
- `faces/state.json` (dashboard IPC state)
- `faces/sim_session_state.json` (sim runner state, if present)

### 13.2 What doesn't get wiped

- Models in `models/`
- Python venv
- Configuration in `.env`
- This documentation
- Log files outside `faces/`

### 13.3 How to trigger

Three paths:

1. **Dashboard**: there is a "Reset" button. It writes `faces/reset_request.json`. The pipeline sees it on next startup check or mid-run check and acts.
2. **Manual**: delete `faces/` and re-run the pipeline. The directory is auto-recreated at startup.
3. **CLI (planned)**: `python -m dog_ai reset` — not yet implemented.

### 13.4 What happens after reset

- Pipeline re-enters first-boot flow on next startup.
- Dashboard state shows "not-enrolled".
- The user must re-enroll the best friend.

### 13.5 Why we keep a separate `reset_request.json` file

The pipeline and dashboard are different processes. They share state via atomic JSON files. We want the reset to be *acknowledged*: the dashboard should know whether the reset succeeded, failed, or is pending. Hence request/result pairs. This pattern is consistent with `enroll_request.json` / `enroll_result.json`.

---
---

# Part III — The Core Loop

## 14. Pipeline States and Transitions

Kara-OS is a finite-state machine at the top level. At any moment the pipeline is in exactly one of these states:

| State | What it means | What runs |
|---|---|---|
| `WATCHING` | No active session. Camera + mic alive. Looking for a face or voice trigger. | Background vision scan, ambient listen, scene heartbeat |
| `LISTENING` | A session is open. Waiting for the session holder to speak. | `listen()` (mic capture + VAD + Smart-Turn), voice accumulation readiness |
| `THINKING` | User spoke; transcript produced; brain is generating. | Streaming LLM call; sentence buffering; tool-call detection |
| `SPEAKING` | TTS is playing audio. | Kokoro synth + sounddevice playback; echo window active |
| `ENROLLING` | First-boot or explicit enrollment in progress. | Face capture loop with anti-spoof gating |

The states are represented by the `PipelineState` enum (`pipeline.py`). `_set_state(new_state, person_name)` logs the transition (`[Pipeline] State: WATCHING -> LISTENING`) and updates `state.json`.

### 14.1 Legal transitions

```
                ┌─────────────────────┐
                │                     │
                ▼                     │
        ┌─────────────┐               │
        │  WATCHING   │──(face/voice)─┤
        └─────────────┘               │
           │       ▲                  │
         (session  │(session expires) │
          opens)   │                  │
           ▼       │                  │
        ┌─────────────┐               │
   ┌────│  LISTENING  │◀──────────────│
   │    └─────────────┘               │
   │       │                          │
   │     (user speaks)                │
   │       ▼                          │
   │    ┌─────────────┐               │
   │    │  THINKING   │               │
   │    └─────────────┘               │
   │       │                          │
   │     (tokens flow)                │
   │       ▼                          │
   │    ┌─────────────┐               │
   │    │  SPEAKING   │───────────────┘
   │    └─────────────┘
   │       │
   │     (playback done)
   │       │
   └───────┘

ENROLLING branches off WATCHING only at first boot, and returns to WATCHING.
```

Invalid transitions (e.g. WATCHING → SPEAKING without passing through THINKING) are not blocked by assertions because they don't occur in the code — each transition has exactly one call site.

### 14.2 Why this specific state machine

We considered finer-grained states (TRANSCRIBING, EXTRACTING, ACCUMULATING) and rejected them. The operator (a human watching the dashboard) cares about the five high-level states; everything else is background. A five-state machine is small enough to reason about completely; a fifteen-state machine would accumulate stale states and redundant transitions.

## 15. Main Event Loop Architecture

### 15.1 Entry point

`pipeline.py::main()` constructs the event loop, installs signal handlers, and awaits `run()`. On Windows we use the selector event loop; on Linux the default is fine. We do not use `uvloop` — the marginal speedup isn't worth the extra dependency.

### 15.2 `run()` as a coroutine tree

`run()` spawns several long-lived tasks and one main coroutine:

```
run()
├── _background_vision_loop()           — scans camera every ~1s, updates _persons_in_frame
├── _dream_loop()                       — idle-triggered consolidation
├── _cloud_retry_loop() [spawned lazily] — re-pings Together.ai when CloudState=SICK
├── _brain_orchestrator.start()         — polls conversation_log every 2s
└── main watch/listen loop              — the primary work
```

Each task is independent; they communicate via shared module-level dicts (`_active_sessions`, `_persons_in_frame`, `_voice_gallery`, `_voice_gallery_sizes`, ...). There are no locks because they all run on the same event loop thread; the concurrency is interleaved awaits, not preemptive threading.

### 15.3 Blocking call handling

Whisper STT, Kokoro TTS, DB writes, and FAISS search are blocking. Each is wrapped in `loop.run_in_executor(None, fn, *args)`. The default executor is a ThreadPoolExecutor with a small number of threads (Python's default). This gives us true parallelism between the event loop and those heavy calls — the mic keeps capturing during Whisper STT, for example.

### 15.4 Signal handling

`signal.signal(signal.SIGINT, _sigint_handler)` installs a handler that sets `_shutdown_event`. On the second SIGINT within 2 seconds, the handler calls `os._exit(1)`.

On Linux we would prefer `loop.add_signal_handler(signal.SIGINT, ...)` for better integration, but that API doesn't exist on Windows. The explicit handler works on both platforms.

### 15.5 The main watch/listen loop pseudocode

```python
while not _shutdown_event.is_set():
    if _pipeline_state == PipelineState.WATCHING:
        # Scene heartbeat runs in background; this loop polls for events
        await asyncio.sleep(0.05)

        # Check if ambient speech occurred (handled by the audio module)
        if ambient_speech_detected:
            # Branch A: voice-first engagement
            handle_ambient_speech()

        # Check if a face entered and deserves greeting
        for pid, info in _persons_in_frame.items():
            if info.get("source") != "voice" and _greet_cooldown_ok(pid):
                _open_session(pid, info["name"], "face")
                greet_and_enter_listening(pid)

    elif _pipeline_state == PipelineState.LISTENING:
        # Capture next turn
        audio_buf, text = await listen(...)
        if not text.strip():
            # empty — stay listening, or close expired sessions
            _expire_stale_sessions()
            continue

        await conversation_turn(actual_pid, text, audio_buf)

    # Background tasks run interleaved with the above
```

This is a simplified sketch; the real code in `pipeline.py` is ~3761 lines because it handles dozens of edge cases (multi-person, dispute, engagement gate, session expiry cleanup, etc.). The structural shape, though, is exactly this.

