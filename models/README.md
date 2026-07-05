# models/: bundled model weights (Git LFS)

The locally-bundled inference models, stored via **Git LFS** (~600MB total). A plain `git clone` gets LFS pointer files; run `git lfs pull` to fetch the real weights.

| File | Used by | Role |
|---|---|---|
| `scrfd_10g_bnkps.onnx` | `core/vision.py::FaceDetector` | face detection (SCRFD, 5-point landmarks) |
| `adaface_ir101.onnx` | `core/vision.py::FaceEmbedder` | face recognition embeddings (512-dim) |
| `kokoro-v1.0.onnx` + `voices-v1.0.bin` | `core/audio.py` | TTS (Kokoro; voice selected by the persona pack) |
| `smart_turn.onnx` | `core/audio.py` | neural end-of-turn detection (~8MB) |
| `antispoof_weights/2.7_80x80_MiniFASNetV2.pth` + `4_0_0_80x80_MiniFASNetV1SE.pth` | `core/vision.py::AntiSpoofChecker` (arch vendored at `core/_minifasnet/`) | liveness anti-spoofing ensemble |

## NOT stored here (downloaded at runtime from Hugging Face)
faster-whisper large-v3-turbo (STT) · SpeechBrain ECAPA-TDNN (speaker ID) · pyannote speaker-diarization-3.1 (needs `HF_TOKEN` + accepted gated-repo license; optional (ECAPA-valley fallback covers single/two-speaker without it) · Florence-2 (object detection) only if `OBJECT_DETECTION_ENABLED` is flipped on) · the distilroberta emotion classifier · multilingual-e5 embeddings (served via Together.ai API, not local).

All GPU inference on these runs in `core/heavy_worker.py` subprocess pools, the main event loop never blocks on a model call.
