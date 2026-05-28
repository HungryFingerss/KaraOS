> **CHAPTER 03 — Async + Vision Basics** | Sourced from `everything_about_system.md` §16-29 (verbatim mechanical extraction per Plan v2 §1.6 section-number stability invariant).

---

## 16. Async Architecture and Concurrency Model

### 16.1 Single-threaded cooperative scheduling

All user code lives on one event loop. There are no `threading.Thread` instances in the pipeline proper (except the ones created internally by `sounddevice` for audio I/O and the ThreadPoolExecutor that `run_in_executor` uses).

The advantage: no data races on `_active_sessions`, `_persons_in_frame`, etc. A reader can iterate those dicts without worrying about mid-iteration mutation from another thread. (Of course an `await` *within* iteration could still cause trouble — iterating a dict and awaiting is a classic bug; we don't do that.)

### 16.2 Executor boundaries — the list

Every place we call `run_in_executor`:

- `transcribe(audio_buf)` → Whisper STT
- `synthesize(sentence, language)` → Kokoro/Piper TTS
- `sd.wait()` → waits for sounddevice playback completion without blocking the loop
- `voice_mod.identify(audio_buf, gallery, threshold)` → ECAPA-TDNN
- `voice_mod.diarize(audio_buf, gallery, threshold)` → within-utterance diarization
- `db.recognize(emb, threshold)` → FAISS search
- `db.add_embedding(...)` → SQLite insert
- `db.add_voice_embedding(...)` → SQLite insert + voice gallery rebuild
- `db.load_voice_profile_for(pid)` → read + mean pool
- `detector.detect(frame)` → RetinaFace (ONNX GPU)
- `embedder.embed(crops)` → AdaFace (ONNX GPU)

### 16.3 Task lifecycle management

- `_voice_tasks: set[asyncio.Task]` holds currently-running voice accumulation tasks. Each task is added on creation and removed via `add_done_callback(_voice_tasks.discard)`. On shutdown we `await asyncio.gather(*_voice_tasks, return_exceptions=True)` with a 2-second timeout.
- `_cloud_monitor_task` is spawned lazily when CloudState transitions to SICK. On shutdown it is explicitly cancelled.
- The BrainOrchestrator runs its own loop internally; `shutdown()` cancels and awaits.

### 16.4 What we explicitly don't do

- No `asyncio.Lock()` on shared state. The single-thread invariant makes locks useless.
- No `multiprocessing` fork. All our models need GPU; forking GPU processes is painful.
- No external message bus. `state.json` is the only IPC and it's one-way (pipeline → dashboard).

## 17. Scene Heartbeat

The "scene heartbeat" is the mechanism that keeps the brain's `<<<SCENE>>>` block and the dashboard's state view up to date with who is currently in the room.

### 17.1 Data sources

- `_persons_in_frame: dict[pid, {name, conf, last_seen, last_recognized_at, source}]`
- `source="face"` entries come from the background vision scan (face detection + recognition).
- `source="voice"` entries come from the per-turn voice ID (pipeline.py ~line 3304 after §Bug B).

### 17.2 Prune rule

Every vision scan (~1 Hz), entries older than `SCENE_STALE_SECS=5.0` are removed. Voice-source entries that expire while a session is still active emit the `[Voice] {name} no longer heard` log (Obs 4, post-review).

### 17.3 `[Vision]` heartbeat log

```python
if _det_count_bv == 0:
    _vis_report_now = "none"
else:
    _rnames = sorted(
        v["name"] for v in _persons_in_frame.values()
        if (_now_vr - v["last_seen"] < VOICE_ROUTING_FACE_STALE_SECS
            and v.get("source") != "voice")  # Bug B fix
    )
    # ... append "unrecognized", "Nx unrecognized" for camera-only hits
    _vis_report_now = ", ".join(_vr_parts) if _vr_parts else "none"

if _vis_report_now != _last_vision_report_str:
    print(f"[Vision] {_vis_report_now}")
```

The log only prints on change (Session 38 dedup) so a stationary scene doesn't spam. The typical log sequence during a conversation looks like:

```
[Vision] Jagan
[Vision] none
[Vision] Jagan
[Vision] none
[Vision] Jagan, Chloe
...
```

Each line indicates "what faces are currently visible on camera." Voice-only speakers are intentionally excluded.

### 17.4 `[Vision] Active (STATE) — names` heartbeat

Distinct from the above, the pipeline also emits a heartbeat every 30 seconds that includes the current state:

```
[Vision] Active (LISTENING) — Jagan, Chloe, visitor
```

This includes *voice-only* entries (to show them as in-session). The split between the two heartbeats is intentional — `[Vision] names` is about on-camera presence; `[Vision] Active (STATE) — names` is about session membership.

## 18. Background Vision Loop

`_background_vision_loop()` is the async task that drives the scene heartbeat. Every ~1 second, independent of the main loop, it:

1. Reads one frame from the camera via `camera.read()`.
2. Runs `FaceDetector.detect(frame)` → list of detections with bbox, landmarks, track_id.
3. For each detection with a valid track_id (SORT-confirmed, not jitter):
   - Crop the face, run V1 quality → if below threshold, skip.
   - Run V2 yaw estimation → if above 60°, skip.
   - Pass through V3 temporal buffer (mean-pool 5 frames) via `track_id`.
   - Run V4 adaptive threshold on the pooled embedding.
   - Call `db.recognize(emb, threshold)` → (pid, name, conf).
   - If recognised, update `_persons_in_frame[pid]` with `source="face"`.
   - If not recognised, record the track_id in `_unrecognized_tracks` and cache the embedding in `_unrecognized_embeddings[track_id]` for potential progressive enrollment later.
4. Prune stale entries from `_persons_in_frame` (>5s old).
5. Update `identity_evidence` for active sessions whose pid was just recognised (Session 61 Step 3).
6. Check the new-face-flag to trigger greetings.

### 18.1 Why every 1 second and not every frame

Running the whole pipeline on every frame (~30 Hz) would saturate the GPU and starve the main loop. Running it every 5th frame (via SORT_DETECT_EVERY=5) gives us ~6 Hz — enough to track smooth motion and detect new faces within ~150ms. The 1-second scene heartbeat is separate from the SORT-every-5-frames decision; it's the upper loop that pulls a frame and processes it.

### 18.2 The tradeoff we accepted

A person who enters the frame and *immediately* starts speaking may not be recognised fast enough to be attributed correctly on their first utterance. We rely on the voice ID path in `_resolve_actual_speaker` to catch this — if the face is still warming up, voice provides the identity. In practice this works well because by the second turn the face scan has caught up.

### 18.3 Anti-spoof call placement in the background loop

Historically we did not anti-spoof in the background scan because every scan hitting the GPU twice (embedding + anti-spoof) is wasteful. We only anti-spoof at three points:

1. **First-boot enrollment** — inside the capture loop, after V1+V2 passed.
2. **Regular enrollment** (`enrollment_flow`) — same placement.
3. **Greeting a known person** — in `_greet_if_ready(pid)` before we say hello, verify the face is live.

Self-update writes (`recognition_update` source) require `verify_live(...)` as of Session 51; this is the fourth anti-spoof site.

## 19. Ambient Listening

"Ambient listening" is the name for the pipeline's capacity to hear a voice when no one is on camera and no session is open. It is the mechanism by which a voice-only speaker (like Chloe sitting behind the laptop) can engage the system.

### 19.1 The flow

- WATCHING state, no active session.
- Mic captures speech. The audio module's VAD + Smart-Turn decide the turn boundary.
- Whisper transcribes.
- ECAPA-TDNN voice ID runs on the audio buffer.
- If voice matches a known person with confidence ≥ VOICE_SPEAKER_SWITCH_THRESHOLD (0.50), open a voice-started session for them.
- If voice does not match, open a *stranger* session with a fresh pid (`stranger_<uuid>`).
- Apply the engagement gate (stranger workflow, §65-67).
- Transition to LISTENING / THINKING as appropriate.

### 19.2 `_ambient_recognized_name` (removed)

We used to carry an `_ambient_recognized_name` through the flow as a shim. It was removed in Session 42 (Issue #26) because the same information is now carried through the structured `vision_state` and `voice_state` dicts passed to the brain.

### 19.3 Why the engagement gate matters for ambient

If we engaged every voice we heard, anyone walking past could wake the system by speaking. The gate — "you must say the system's name to get a response" — is what makes the system feel *chosen* rather than *triggering*.

The gate has a phonetic fallback (Session 41): Double Metaphone via `jellyfish` accepts phonetic variants. So "Kara", "Karah", "Cara" all engage the same gate.

---
---

# Part IV — Vision

## 20. RetinaFace Detection

### 20.1 Model and why we picked it

RetinaFace from the InsightFace buffalo_l bundle is our face detector. It is a multi-task network that outputs:
- Bounding boxes for each detected face,
- Confidence scores per box,
- Five facial landmarks per box (left eye, right eye, nose tip, left mouth, right mouth).

We picked it because:
- **State-of-the-art recall on small faces.** Our camera is 1280×720 and the user is often 1-2m away. Smaller faces are typical; many detectors degrade below 80×80 pixels. RetinaFace remains usable to 40×40.
- **The five landmarks are free.** We use them for yaw estimation in V2 quality gating and for face alignment in AdaFace preprocessing.
- **ONNX-runnable on GPU.** onnxruntime-gpu loads the network and keeps the GPU context warm.
- **Bundled with the buffalo_l pack.** One download gives us detection + landmarks + ArcFace embedding weights (we don't use the ArcFace part — we use AdaFace instead — but the convenience of a single model pack matters).

### 20.2 `FaceDetector.detect(frame) -> list[Detection]`

```python
class FaceDetector:
    def __init__(self):
        self._model = FaceAnalysis(name="buffalo_l", providers=["CUDAExecutionProvider"])
        self._model.prepare(ctx_id=0, det_size=(640, 640))

    def detect(self, frame: np.ndarray) -> list[Detection]:
        faces = self._model.get(frame)
        return [Detection.from_insightface(f) for f in faces]
```

The `Detection` dataclass carries `bbox`, `score`, `landmarks`, and (after SORT) `track_id`.

### 20.3 Confidence threshold

`DETECTION_CONFIDENCE=0.50` rejects faces below 50% confidence. We lowered this from 0.70 when we noticed that upward-angle camera setups (e.g., a laptop on a desk) produce detection scores in the 0.5-0.7 range for non-frontal faces — the old threshold was losing real faces.

### 20.4 Cost

One `detect()` call at 640×640 input size: ~15 ms on the dev GPU. Running it on every frame (30 FPS) would be 450 ms/s on the GPU, half our budget, and would choke the other models. Hence SORT-every-5-frames (§21).

## 21. SORT Tracking with Kalman Filter

### 21.1 What SORT is

SORT ("Simple Online and Realtime Tracking") is a lightweight tracker that maintains identity across frames by:
1. Predicting each existing track's bounding box in the next frame using a Kalman filter (constant velocity model).
2. Matching new detections to predictions via IoU (intersection over union).
3. Assigning matches using the Hungarian algorithm (linear_sum_assignment from scipy.optimize).
4. Creating new tracks for unmatched detections; killing tracks that go unmatched for SORT_MAX_AGE frames.

### 21.2 Why we need it

Face detection runs every 5th frame. Without tracking, we'd lose identity continuity between detections — a person could be "a new person" every 150ms. SORT extrapolates between detections using Kalman, so the same person gets the same `track_id` across the whole time they are in frame.

This matters for:
- **Progressive enrollment** — we need to accumulate V3 (temporal buffer) entries keyed by stable track_id.
- **Unrecognized-face caching** — `_unrecognized_embeddings[track_id]` caches the embedding of an unknown face so that if they later pass the engagement gate we can enroll their face. Track instability would lose the embedding.
- **Continuity heartbeat** — the `[Vision]` log's `N x unrecognized` count is stable over motion only because the track_ids are stable.

### 21.3 Our Hungarian-vs-greedy fix

Before Session 24 we used a greedy match: each detection claimed its best track. This caused races where a track could be multi-claimed in the same frame. We switched to `linear_sum_assignment` which guarantees a 1:1 optimal assignment. That fix is permanent; regression test guards it.

### 21.4 Parameters

- `SORT_DETECT_EVERY=5` — run RetinaFace every 5 frames; Kalman-predict in between.
- `SORT_MAX_AGE=30` — keep a track alive for 30 frames without a detection match (1 second at 30 FPS). Accommodates brief occlusion.
- `SORT_MIN_HITS=2` — a track must be matched on at least 2 detections before it's "confirmed". Filters out detection jitter.

## 22. AdaFace IR101 Embedding

### 22.1 Why AdaFace over ArcFace

ArcFace was the dominant face embedder for years. AdaFace improves on it specifically for open-set recognition with quality-varying inputs — which is exactly our situation (indoor lighting, varying poses, camera angle). In the 0.28-0.45 cosine-similarity region, AdaFace has a more stable EER (equal error rate) which means our threshold doesn't have to be painfully specific to avoid false positives.

We use the IR101 backbone (iResNet-101) trained on WebFace12M-42M. 512-dimensional embeddings, L2-normalised.

### 22.2 The embedder

```python
class FaceEmbedder:
    def __init__(self):
        sess_options = ort.SessionOptions()
        self._session = ort.InferenceSession(
            "models/adaface_ir101.onnx",
            sess_options=sess_options,
            providers=["CUDAExecutionProvider"],
        )

    def embed(self, face_crops: list[np.ndarray]) -> np.ndarray:
        # Preprocess: resize to 112x112, normalize, transpose to NCHW
        batch = preprocess(face_crops)
        # Run
        emb = self._session.run(None, {"input": batch})[0]
        # L2-normalize for cosine similarity
        emb = emb / np.linalg.norm(emb, axis=1, keepdims=True)
        return emb
```

### 22.3 Why L2-normalise at embedding time

Cosine similarity is dot product on unit vectors. If the embeddings are already unit-length, FAISS IndexFlatIP returns cosine similarity directly. This means we never have to call cosine similarity — a dot product suffices. Cheap.

### 22.4 Alignment via landmarks

AdaFace (like ArcFace) expects faces aligned to a canonical pose using the 5 landmarks. RetinaFace produces those landmarks; the embedder preprocesses each crop with a similarity transform that maps the landmarks onto reference positions. Without alignment, embeddings of the same face at different yaws cluster poorly and recognition fails.

## 23. Face Quality Gates V1 through V4

These are four progressively stronger gates that determine which face crops are "good enough" for different uses. All live in `core/vision.py`.

### 23.1 V1 — `face_quality_score(crop) -> float`

A heuristic quality score in [0.05, 1.0] combining:
- **Size factor** — normalised face bbox area.
- **Blur factor** — Laplacian variance indicates focus.
- **Brightness factor** — mean luminance relative to a target.

Each factor is in [0, 1] and the final score is their product (or a soft combination). The floor of 0.05 means "a face is detectably present even if it's terrible quality."

Four cut-off points:
- `FACE_QUALITY_PRESENCE=0.05` — face present.
- `FACE_QUALITY_RECOGNITION=0.20` — recognition viable.
- `FACE_QUALITY_ENROLLMENT=0.50` — clean enough to write to gallery.
- `FACE_QUALITY_SELF_UPDATE=0.70` — high-quality crop required for gallery self-update.

The gate used depends on the caller:
- Enrollment path uses 0.50.
- Recognition uses 0.20.
- `recognition_update` source uses 0.70.

### 23.2 V2 — `estimate_yaw_from_landmarks(landmarks) -> float`

Estimates yaw angle from the five facial landmarks using the relative positions of the eyes and nose. Returns degrees in roughly `[-90, 90]`.

Gate: enrollment rejects faces with `|yaw| > 60°`. Recognition accepts any yaw (we want to match even profile views).

### 23.3 V3 — `TemporalEmbeddingBuffer`

Mean-pools the last 5 frames of embeddings keyed by SORT `track_id`. Reduces noise from single-frame embedding fluctuation. Empty for new tracks; returns the current embedding unchanged when pool depth < 5; returns the mean when ≥ 5.

Used as the input to V4 for recognition. If the pool has fewer than 5 entries, the recognition threshold is bumped up by 0.05 to compensate for the extra uncertainty.

### 23.4 V4 — `adaptive_threshold(quality_score, base_threshold) -> float`

Scales `RECOGNITION_THRESHOLD=0.28` upward when quality is low. The idea: on a noisy crop, we want more margin before calling it a match; on a clean crop, the base threshold is fine.

```python
def adaptive_threshold(quality: float, base: float) -> float:
    # quality in [0.05, 1.0]; base = RECOGNITION_THRESHOLD
    if quality >= 1.0:
        return base
    # Linear scale: quality 1.0 -> base, quality 0.2 -> base+0.05
    adjustment = (1.0 - quality) * 0.05
    return min(base + adjustment, 0.45)  # cap at a reasonable upper
```

### 23.5 V1-V4 composed

The full recognition pipeline:

```
raw detection
  ↓ V1: face_quality_score -> q
  ↓    if q < FACE_QUALITY_RECOGNITION (0.20): drop
  ↓ V2: yaw check (recognition does not reject on yaw; enrollment does)
  ↓ V3: temporal buffer; mean-pool last 5 frames for this track_id
  ↓ V4: adaptive_threshold(q, RECOGNITION_THRESHOLD)
  ↓ db.recognize(emb, threshold)
```

## 24. Anti-Spoofing — MiniFASNet Ensemble

### 24.1 The threat

A photo of the best friend held up to the camera. A laptop screen showing a recorded video. A printed face on paper. All three should be rejected; only genuine live faces should pass.

### 24.2 The model

MiniFASNet from minivision-ai. We vendored the architecture (`core/_minifasnet/`) and use two pretrained weight files:
- `2.7_80x80_MiniFASNetV2.pth` — V2 backbone, trained at 2.7× bbox scale crop.
- `4_0_0_80x80_MiniFASNetV1SE.pth` — V1SE backbone, trained at 4.0× bbox scale crop.

Both output 3-class logits:
- Class 0: fake (print/photo)
- Class 1: live
- Class 2: replay (screen)

### 24.3 Ensemble inference

```python
def is_live(self, frame, bbox) -> tuple[bool, float]:
    probs_total = np.zeros(3)
    for model, scale in self._models:
        crop = crop_with_scale(frame, bbox, scale=scale)
        crop = resize(crop, (80, 80))
        tensor = torch.from_numpy(crop).permute(2, 0, 1).float().unsqueeze(0)
        # IMPORTANT: no .div(255.0) — upstream trained on raw [0,255] float.
        # Session 59 bug: dividing by 255 caused 100% false-reject.
        logits = model(tensor.to(self._device))
        probs = torch.softmax(logits, dim=1).cpu().numpy()[0]
        probs_total += probs
    probs_avg = probs_total / len(self._models)
    argmax = int(np.argmax(probs_avg))
    live_prob = float(probs_avg[1])
    return (argmax == 1 and live_prob >= ANTISPOOFING_THRESHOLD, live_prob)
```

Two crops at different scales, two models, softmax average, argmax decides. Threshold `ANTISPOOFING_THRESHOLD=0.5` was validated in Session 60 to give ≥ 0.95 live-prob on genuine faces and ~0.016 on photos.

### 24.4 `verify_live(frame, bbox, checker)` wrapper

The higher-level wrapper handles:
- `checker.available` check — if the models failed to load, returns True (fail-safe).
- Logging — the `[Anti-spoof]` line with probs or summary.
- Stats accumulation for the rolling-summary log.

Callers should always use `verify_live(...)`, not raw `is_live(...)`. Four call sites:
- `_greet_if_ready(pid)` — before greeting a known person.
- `first_boot_flow()` capture loop.
- `enrollment_flow()` capture loop.
- `add_embedding(source='recognition_update')` — anti-poisoning gate (Session 51).

### 24.5 Rolling summary log

Per-frame logs are noisy. `LOG_ANTISPOOF_SUMMARY=True` emits a compact summary every 100 calls:

```
[Anti-spoof] summary over last 100 frames: min=0.93 mean=0.97 max=1.00 rejects=0 thr=0.50
```

This gives drift visibility over time (camera aging, lighting changes) without spamming.

### 24.6 P0.S1 — Anti-Spoof on Every Face Match (the gap closure)

Session 52 stood up the MiniFASNet ensemble; Section 24.1-24.5 above describes how the checker itself works. P0.S1 closed the orthogonal question: **does every face match the system performs actually consume that checker, or are some paths quietly bypassing it?**

#### The premise-reset finding

Casual reading of pipeline.py suggested that `recognition_update` (the most poisoning-prone path — silently writes embeddings into a known person's gallery on every high-confidence match) was the only at-risk surface. **Phase 0 audit reset that premise.**

`recognition_update` at `pipeline.py:6469-6478` was already strictest-fail-closed gated: `verify_live` runs inline, exception swallowed → fail-closed reject, and on failure the code skips the embedding write entirely. Verified by code reading, not assumption. The narrative everyone carried in their head ("recognition_update is the dangerous path") was already the safe path.

The **actual gap** lived at `pipeline.py:7690` — the `progressive_enroll` site that fires when a stranger first says the system name and the engagement gate opens. That path read the face embedding straight out of `_track_store` (captured at scan time by `_background_vision_loop`) and called `db.add_embedding(_cur_pid, _gate_emb, "progressive_enroll")` **without any anti-spoof check at all**. A presentation attack against a stranger session could seed a face gallery from the very first turn.

Same shape as P0.10 Phase 0 audit's wrong-premise catch (legacy `_resolve_actual_speaker` was thought to be the correctness baseline; was actually the buggy path). Phase 0 saved Phase 1-3 from chasing the wrong target. Bank as sub-pattern A under Spec-First Review Cycle: Phase 0 audit catches wrong premise.

#### The four load-bearing properties

**a. Verdict-embedding co-temporality (C0)** — The verdict and the embedding must come from the *same frame*. `_background_vision_loop` captures the embedding via `embedder.embed(_crop)` where `_crop = frame[bbox]`; the SAME `frame` then goes to `_classify_anti_spoof_verdict(frame, _det.bbox, _anti_spoof_checker)`. Both results land in `TrackEntry` via a single `await _track_store.upsert_embedding_with_verdict(...)` call — atomic from any consumer's perspective. The consumer at progressive_enroll reads them together via `peek_anti_spoof_verdict(_gate_track)`. No cross-frame caching: a stranger who shows a real face once and then swaps to a photo cannot get the live verdict from the first frame attached to the photo embedding from the second.

The atomic upsert is enforced by `TrackStore.upsert_embedding_with_verdict` taking the lock once and writing all five fields (embedding, anti_spoof_live, anti_spoof_score, anti_spoof_reason, captured_at, bbox) under it. The structural test `test_track_store_upsert_with_verdict_is_atomically_observable` runs 1 writer + 50 readers in tight async loops and asserts zero torn-state observations (embedding set without verdict, or vice versa).

The C0 same-frame discipline at the call-site level is enforced by `# P0S1-C0:` marker comments + a structural test that asserts within K=25 lines following each marker, the `_crop = frame[...]` slice, the `embedder.embed(_crop)` call, and the `verify_live(frame, ...)` / `_classify_anti_spoof_verdict(frame, ...)` call all reference the same `frame` variable. Marker-comment route chosen over Plan v2's AST graph walk because `run_in_executor(None, embedder.embed, _crop)` makes `embedder.embed` a Name expression (not a Call node), defeating AST provenance walking — see §14b.2 below.

**b. Verdict-required-for-protected-source (D1 + D5)** — Hybrid enforcement. Every call site computes `verify_live` (or reuses an already-captured verdict) and passes `anti_spoof_verdict=` to `db.add_embedding`. The `add_embedding` function itself contains a catch-all gate at `core/db.py:588-625`: if `source` is in `ALLOWED_EMBEDDING_SOURCES_REQUIRING_ANTI_SPOOF` (== the full `VALID_EMBEDDING_SOURCES` set after D4 deleted `legacy_unknown`), then `anti_spoof_verdict` must be `True` or the write is refused with a `[FaceDB] add_embedding rejected for {pid} source={src} verdict={v!r} — anti-spoof gate blocks write (P0.S1 D1 catch-all)` log line. The hybrid is the safety net: per-call-site captures the verdict context (frame, score, reason); catch-all blocks any future caller that forgets the upstream gate.

The frozenset's deletion of `legacy_unknown` (D4) is the strongest possible enforcement — a runtime `AssertionError: add_embedding called with unknown source` catches developer mistakes BEFORE the code ships. AST scans add CI-time enforcement. Path 1b execution (architect's call during Phase 1) made `source` a required kwarg, eliminating the silent default backdoor.

**c. Fail-closed-on-unavailable (C1)** — Four reason codes, never collapsed:
- `ANTI_SPOOF_REASON_PASSED` — `verify_live` returned True.
- `ANTI_SPOOF_REASON_REJECTED` — `verify_live` returned False.
- `ANTI_SPOOF_REASON_UNAVAILABLE` — `checker.available` is False or checker is None (model failed to load, or anti-spoof disabled in config).
- `ANTI_SPOOF_REASON_NO_VERDICT` — no verdict was captured for the track (e.g. progressive_enroll fires with `_gate_live=None` because the verdict TTL aged out).

These flow end-to-end. `_classify_anti_spoof_verdict` returns the `(live, score, reason)` triple. `TrackEntry` stores all three. `peek_anti_spoof_verdict` returns them to progressive_enroll. The rejection-store records the reason. `WatchdogAgent.report_anti_spoof_rejection` stores the reason in alert metadata so dashboard / replay can branch on it. Operators distinguish hardware-down (`unavailable`) from active attack (`rejected`) at every layer, not just at the structural level.

`VisionFramePayload.anti_spoof_live` was widened from `bool` to `Optional[bool]` for the same reason. The P0.0.7 prerequisite locked 2-state. P0.S1 Phase 2 needed 3-state: True = at least one detection passed in this scan; False = at least one rejected; None = all detections produced no verdict (checker unavailable). Replay distinguishes hardware-down from active attack. The pre-existing P0.0.7 invariant test `test_vision_frame_payload_includes_anti_spoof_fields` was updated with explicit rationale documenting the deliberate widening — not a regression, a semantic upgrade.

**d. Exact-equality burst dedup (C2 + §14b.1)** — Per-track, not per-pid. The `AntiSpoofRejectionStore` records timestamps keyed on SORT `track_id` (because at progressive_enroll gate time, the pid may not exist yet — the track is the only stable correlation key). On every rejection, prune timestamps older than `ANTI_SPOOF_BURST_WINDOW_SECS=60.0`, then return the post-prune count. The pipeline-side dispatcher fires the burst alert **only at exact equality**:

```python
if _rej_count == ANTI_SPOOF_BURST_THRESHOLD:  # exact; NOT >= which would re-fire
    _brain_orchestrator.report_anti_spoof_burst(...)
```

`>=` would re-fire on every subsequent rejection in the window (4th, 5th, 6th, ...). Exact equality fires once per burst. The structural test `test_tripwire_burst_alert_dispatch_exact_equality` regex-scans `pipeline.py` and forbids `>=` / `>` upstream of any `report_anti_spoof_burst(` call site.

Per-track scope: a burst on track_A leaves track_B's count at 0. No cross-track lockout, no voice-channel lockout. The watchdog is for surfacing patterns, not for taking enforcement action against unrelated tracks.

#### AntiSpoofRejectionStore — why a Store subclass instead of a module-level dict

Plan v1 sketched `_anti_spoof_rejection_log: dict[str, list[float]]` at module scope in `pipeline.py`. Plan v2 MED 5 promoted it to a `Store` subclass at `core/anti_spoof_rejection_store.py`. Two reasons:

1. **P0.6 ratchet preservation.** The legacy-global-progress ratchet test `tests/test_p06_legacy_global_progress.py` is at cap=0 — adding a new module-level mutable dict at pipeline.py scope would trip the ratchet. Promoting to a `Store` subclass keeps the migration discipline intact: every piece of mutable global state in pipeline.py lives in a Store with `_lock: asyncio.Lock`, async mutators, sync `peek_*` reads, sync `reset()` for the autouse fixture.

2. **M2 coverage meta-test integration.** The autouse fixture in both `conftest.py` (root) and `tests/conftest.py` loops over `_STORE_NAMES` calling `.reset()` between every test. Adding `_anti_spoof_rejection_store` to the loop required only a 1-line addition to each conftest. Test isolation is structural; no test needs to remember to clear the rejection log.

The Store contract is exactly: `record_rejection(track_id, now, window_secs) -> int` (returns post-prune count), `peek_count(track_id, now, window_secs) -> int` (sync read), `pop(track_id) -> None` (called on session close + stale-prune), `reset() -> None` (autouse fixture).

#### D9 voice-only fallthrough — rejection closes face write but voice channel proceeds

The progressive_enroll branch reads the verdict from track-store. On block (verdict not True), it logs `BLOCKED progressive_enroll face write for {pid} track={tid} reason={reason} score={score}`, calls `_anti_spoof_rejection_store.record_rejection`, dispatches `report_anti_spoof_rejection` to watchdog, and fires the burst alert at exact equality. **What it does NOT do** is set `_face_captured = True`. The else-branch below — Session 64 Bug C's voice-only fallthrough — fires unchanged: bootstrap voice credits seed (`N_INITIAL_VOICE_BOOTSTRAP`), voice accumulation runs with `face_verified=False`, session opens.

The visitor can still speak. They just cannot poison a face gallery. The watchdog catches the pattern across multiple rejections (3 in 60s → burst alert) without blocking any single voice interaction.

D9 tripwire `test_tripwire_voice_only_fallthrough_branch_intact` asserts the rejection elif-branch NEVER sets `_face_captured = True` and DOES call `record_rejection` and `report_anti_spoof_rejection`. A future refactor that flips `_face_captured` on a blocked path would fire the tripwire.

#### D10.c — dashboard yes, TTS no (security UX)

The rejection log is silent to the speaker. No "I think you might be a photo" announcement. The dashboard sees `[Anti-Spoof] BLOCKED` lines + the watchdog alert feed. The principle: **never announce defenses to the attacker**. An attacker who knows the gate fired learns the threshold; an attacker who hears nothing learns nothing.

The watchdog alerts surface to the household-owner-facing dashboard. `report_anti_spoof_rejection` stores severity=`info` (single rejection is usually a transient false negative). `report_anti_spoof_burst` stores severity=`warning` (sustained pattern — investigate). The owner can review patterns at their convenience; the suspected attacker has no idea.

#### Cross-references

- `tests/p0_s1_audit.md` — Phase 0 audit. Threat model + 5 call-site enumeration with verdict-source per site. This is the document that surfaced the premise-reset finding.
- `tests/p0_s1_plan_v1.md` — Plan v1. Locked D1-D10 + C0-C3 contract clauses.
- `tests/p0_s1_plan_v2.md` — Plan v2. Auditor's 9 precision items (HIGH 1/2/3 + MED 4/5/6 + LOW 7/8/9) + §14b in-flight clarifications.
- `tests/test_p0_s1_phase1.py` + `tests/test_p0_s1_phase2.py` + `tests/test_p0_s1_phase3.py` + `tests/test_p0_s1_phase4.py` — 50 tests across the four phases.
- `tests/p0_s1_validation_runbook.md` — TBD. Live canary runbook per Plan v2 §9 (3 independent sessions; closure gate = 9 rejections + 3 negative-control passes + 1 deliberate burst reproduction).
- `complete-plan.md::P0.S1` — full closure summary including discipline-count bumps and bookmarks.

## 25. Lip Tracking

### 25.1 Why

When the user is mid-sentence and pauses briefly, we don't want to cut them off. Smart-Turn catches most cases but can miss pauses in thoughtful speech. Lip tracking gives an additional signal: "lips are still moving, so they probably have more to say."

### 25.2 How

`LipTracker` computes inter-frame pixel diff inside the mouth region (bounded by the mouth landmarks from RetinaFace). If the diff exceeds a threshold, lips are "active."

During recording, if Smart-Turn fires end-of-turn but the lip tracker says active, the recording is extended by up to `LIP_MAX_EXTENSION=2.0` seconds. The terminal log shows `[Audio] Turn end — N speech chunks, M lip extension(s)`.

### 25.3 When it fires

Only when the session holder's face is in view and the lip ROI is extractable. If the user is off-camera, lip tracking is skipped and only Smart-Turn + SILENCE_DURATION decide.

## 26. Camera Reconnection

`Camera` wraps `cv2.VideoCapture` with retry logic. If `read()` returns `(False, None)` for more than a threshold, we close and reopen. Handles:
- USB webcam being briefly disconnected and replugged.
- Camera permission issues on first launch.
- Driver glitches on Windows that sometimes return empty frames.

The backend is chosen by platform:
- Windows: `cv2.CAP_DSHOW` (DirectShow)
- Linux: `cv2.CAP_V4L2`

Set via `sys.platform` at construction time. No user-configurable option.

---
---

# Part V — Audio

## 27. Microphone Capture

`sounddevice.InputStream` is opened at 16 kHz mono float32. Chunks of 512 samples (32 ms) flow into a `asyncio.Queue`. The audio module consumes this queue in its VAD and capture loops.

We chose 16 kHz because Whisper was trained at that rate, Smart-Turn was trained at that rate, and ECAPA-TDNN processes at that rate. Mono because beamforming (which would use stereo) is a future feature (ReSpeaker barge-in). Float32 because that's what every downstream model wants and saving a byte per sample by using int16 isn't worth the conversion.

## 28. Voice Activity Detection — RMS vs Silero

### 28.1 RMS (default on laptop)

`VAD_SWITCH=False` selects RMS-based detection. For each 32ms chunk, we compute root-mean-square energy. Above `RMS_THRESHOLD=0.01` is "speech"; below is "silence."

Trivial implementation (~3 lines), zero model cost, tunable. Works well in a quiet indoor environment.

### 28.2 Silero (planned for Jetson)

`VAD_SWITCH=True` loads the Silero VAD ONNX model. Much better at rejecting non-speech audio (AC hum, keyboard clicks, distant traffic). We keep it off on the laptop because the GPU is already saturated by Whisper + RetinaFace.

### 28.3 The "silence detected" log

Once a speech streak ends and we've observed `SMART_TURN_SILENCE=0.5` seconds of silence, we emit `[Audio] Silence detected — waiting for end-of-turn...`. This can fire multiple times during a single long user turn if the user pauses mid-sentence — each resumed speech chunk resets the silence counter, and the next pause logs again.

Session 38 added a dedup flag to avoid spam; Session 49 bumped the reset threshold from 3 to 9 chunks (~288ms) to suppress micropause oscillation.

## 29. Pre-Roll Buffering

When speech is first detected, the first few hundred milliseconds of the utterance have already happened (the RMS cross was at chunk N but the actual speech began at N-k). We keep a rolling 1-second pre-roll buffer and prepend it to the speech chunks so the transcription includes the onset.

### 29.1 Echo skip

If the system just finished speaking (TTS playback), the first pre-roll chunks may contain the tail of our own audio echoing back from the mic. We skip the first `echo_skip` chunks of pre-roll based on the time since TTS playback ended.

```python
_tts_end_time = <timestamp when last TTS chunk finished>
elapsed_since_tts = now - _tts_end_time
echo_skip = min(max(0, int((ECHO_WINDOW - elapsed_since_tts) / CHUNK_DURATION)), len(pre_roll))
```

The `min(..., len(pre_roll))` cap is Session 36's Bug-15 fix — without it, a small pre-roll buffer could have echo_skip > len(pre_roll), which would have silently discarded the entire pre-roll. The log shows `[Audio] Echo skip: N/M pre-roll chunks trimmed`.

