> **CHAPTER 04 — Audio + STT/TTS** | Sourced from `everything_about_system.md` §30-35 (verbatim mechanical extraction per Plan v2 §1.6 section-number stability invariant).

---

## 30. Smart-Turn Neural End-of-Turn

### 30.1 The problem

A fixed silence threshold is a blunt instrument. Too short and the system cuts off the user mid-sentence. Too long and the response feels laggy. Humans turn-take with a blend of syntax, prosody, and context — a short pause after "I was thinking..." is a continuation; the same short pause after "That's all." is a turn end.

### 30.2 The model

Smart-Turn (pipecat-ai/smart-turn) is an ~8MB ONNX classifier trained on conversational audio. Input: the most recent 2-4 seconds of audio. Output: probability that the turn has ended.

### 30.3 The trigger

After `SMART_TURN_SILENCE=0.5` seconds of silence following a speech streak, we call Smart-Turn on the last few seconds of audio. The return is a probability.

- `p >= SMART_TURN_THRESHOLD=0.80` → turn complete, with short grace window `SMART_TURN_ADDENDUM=0.5` (Session 10 tuning).
- `0.80 > p > 0.95` → adaptive grace window shrinks to 0.20s.
- `p < 0.80` → wait out the full `SILENCE_DURATION=1.5` hard fallback.

### 30.4 Why 0.80 and not 0.55

We started at 0.55. The model was triggering turn-end inside pauses mid-thought; the robot responded while the user was still formulating. We raised the threshold twice and settled at 0.80. The tradeoff is a slight latency increase on quick sentences (we wait for hard silence), but the improvement in "feels like it's actually listening" was large.

## 31. Echo Skip and Barge-In

### 31.1 Echo skip (current)

See §29.1.

### 31.2 Barge-in (disabled)

Prior to Session 2 we had a `_vad_interrupt_listener` that ran during TTS playback and triggered `stop_audio()` if the user started speaking. This is "barge-in" — the ability to interrupt the robot mid-sentence.

We removed it because:
- On the laptop mic, TTS output often echoes back into the input strongly enough to trigger the listener — so the system would interrupt itself.
- The acoustic echo cancellation needed for real barge-in requires either an array mic (ReSpeaker 4-mic) or aggressive DSP.

Barge-in will come back when we get the ReSpeaker hardware. It's on the roadmap; the code comment at the removal site says "Do NOT re-add `_vad_interrupt_listener`" to prevent someone re-enabling it naively.

## 32. Whisper STT

### 32.1 Model

faster-whisper large-v3-turbo, loaded with `float16` on GPU. The Turbo variant is ~3x faster than regular large-v3 with minimal quality loss. ~400-700 ms for a typical 3-5 second utterance on the dev GPU.

### 32.2 Configuration

- `language=SPEAKER_LANGUAGES[0]` — currently `"en"`. The `SPEAKER_LANGUAGES` list is the set of allowed auto-detect candidates; single-language forces English.
- `vad_filter=False` — we do our own VAD upstream; letting Whisper's VAD trim would double-process.
- `condition_on_previous_text=False` — each call is independent; we don't carry state across calls.
- Default beam size and temperature.

### 32.3 Transcribe call

```python
def transcribe(audio: np.ndarray) -> tuple[str, str]:
    global _last_stt_elapsed_ms
    start = time.monotonic()
    segments, _info = _whisper.transcribe(audio, language=SPEAKER_LANGUAGES[0], ...)
    text = "".join(seg.text for seg in segments).strip()
    _last_stt_elapsed_ms = int((time.monotonic() - start) * 1000)
    print(f"[STT] {_now_log_ts()} ({_last_stt_elapsed_ms}ms) '{_log_trunc(text)}'")
    return text, SPEAKER_LANGUAGES[0]
```

The elapsed_ms is stored in a module-level global so the pipeline can log it again in turn-start logs without re-measuring (Session 61 Step 1).

### 32.4 Repetition filter

Whisper occasionally hallucinates repetitions like "pizza pizza pizza" on certain inputs. A heuristic post-processor detects 3+ consecutive identical words and logs `[Audio] STT: (repetition filtered): '...'` — the transcript is returned but flagged. Downstream uses the text but knows to be suspicious.

## 33. Within-Utterance Diarization

### 33.1 The problem

Two people can speak in rapid succession inside what the VAD treats as one turn. "Kara, it'll be hot" from Jagan followed immediately by "yes, I saw the news" from Sweetie — same `listen()` call, two speakers. The brain needs to attribute the utterance correctly.

### 33.2 The approach

`voice_mod.diarize(audio, gallery, threshold)` runs ECAPA-TDNN with a sliding window (DIARIZE_WINDOW_SECS=0.50, DIARIZE_HOP_SECS=0.25). Computes an embedding per window, then detects speaker boundaries by checking cosine similarity between adjacent windows — below `DIARIZE_CHANGE_THRESH=0.70` is a boundary.

If exactly 2 segments are produced (a single speaker change), we re-transcribe each half separately with Whisper, attributing each half to the closest voice-gallery match.

### 33.3 Minimum length

`DIARIZE_MIN_SECS=2.00` — we only diarize utterances ≥ 2 seconds. Shorter ones don't have enough signal for reliable speaker-change detection.

### 33.4 Terminal log

```
[STT] [2 voices] Jagan: "Kara, it'll be hot" / Sweetie: "yes, I saw the news"
```

And the `multi_speaker` and `multi_speaker_speakers` fields in `voice_state` propagate to the brain, which sees a mic-status block noting 2 speakers. The brain can acknowledge both in its reply.

## 34. Kokoro TTS and Piper Fallback

### 34.1 Kokoro (primary)

Kokoro is an ONNX-runnable TTS from Facebook. We use the `af_heart` voice — a warm, friendly timbre appropriate for a companion. Streaming synthesis: we feed sentence-at-a-time and it produces audio in tens of milliseconds per sentence.

We call it via the Kokoro Python wrapper. Output is float32 samples at the TTS model's native rate (we resample if needed before feeding to sounddevice).

### 34.2 Piper (fallback)

If Kokoro fails to load or to synthesise a given sentence, we fall back to Piper with the `en_US-lessac-medium` voice. Piper is slightly more robotic but reliable.

Fallback happens at synth-call time, per-sentence. One failed Kokoro call doesn't disable Kokoro — we just retry with Piper and move on.

### 34.3 Text cleaning before TTS

`_clean_for_tts(text)` strips content that would sound bad when read aloud:
- Markdown: `**bold**`, `*italic*`, `` `code` ``, `# headers`
- List markers: `- `, `• `, `1. `
- Em dashes, link syntax `[text](url)` → `text`
- Stray symbols

This was Session 32 Issue 5 — the LLM occasionally emits markdown and we don't want the TTS reading "asterisk asterisk bold asterisk asterisk".

## 35. Sentence Streaming

### 35.1 The pipeline

Tokens arrive from the streaming LLM one at a time. If we waited for the full response before speaking, latency would be bad. If we spoke every token, prosody would be bad.

The sweet spot is sentence-level streaming: buffer tokens until a sentence boundary, then synth and play that sentence while the next is still being generated.

### 35.2 `_sentence_stream(token_gen)`

```python
async def _sentence_stream(token_gen):
    buf = ""
    async for tok in token_gen:
        buf += tok
        # Find the last sentence terminator in the buffer
        for i in range(len(buf) - 1, -1, -1):
            if buf[i] in ".!?" and (i == len(buf) - 1 or buf[i + 1].isspace()):
                yield buf[:i + 1].strip()
                buf = buf[i + 1:]
                break
    if buf.strip():
        yield buf.strip()
```

### 35.3 `speak_stream(sentence_stream, language)`

Runs two coroutines concurrently:
- `_synth_worker`: takes sentences, synthesises with Kokoro/Piper, puts audio buffers on a queue.
- `_play_worker`: takes audio buffers from the queue, plays via sounddevice, awaits playback completion.

The synth worker and play worker overlap — by the time one sentence is playing, the next is already being synthed. This is the key reason the robot feels responsive even on multi-sentence replies.

### 35.4 Sentinel for worker termination

The stream uses a sentinel value (typically `None`) on the queue to signal "no more sentences." The synth worker's try/finally guarantees the sentinel is put even on exceptions (Session 35 Bug-10 fix).

### 35.5 `stop_audio()`

`sd.stop()` immediately halts playback. Used when:
- A tool call fires mid-speech (we don't want the wrong text to finish playing).
- Stream truncation retry happens (don't overlap original and retry).
- User-requested shutdown during speech.

---
---

# Part VI — Identity and Recognition

