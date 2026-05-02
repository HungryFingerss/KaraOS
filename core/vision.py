"""
core/vision.py — Face detection (RetinaFace) + recognition (AdaFace)
Runs on GPU via ONNX Runtime.
"""
import asyncio
import sys
from collections import deque
import cv2
import numpy as np
import onnxruntime as ort
from pathlib import Path
from dataclasses import dataclass
from typing import Optional
from core.config import (
    DETECTION_CONFIDENCE, EMBEDDING_DIM,
    FRAME_WIDTH, FRAME_HEIGHT,
    SORT_DETECT_EVERY, SORT_MAX_AGE, SORT_MIN_HITS,
)
import os
os.environ["INSIGHTFACE_LOG_LEVEL"] = "ERROR"

MODEL_DIR = Path(__file__).parent.parent / "models"


@dataclass
class Detection:
    bbox: tuple[int, int, int, int]   # x1, y1, x2, y2
    confidence: float
    embedding: Optional[np.ndarray]  = None
    person_id: Optional[str]         = None
    person_name: Optional[str]       = None
    recognition_conf: float          = 0.0
    landmarks: Optional[np.ndarray]  = None   # shape (5,2): leye,reye,nose,lmouth,rmouth
    track_id: Optional[int]          = None   # SORT track ID — stable across frames


# ── V1: Face quality gate ─────────────────────────────────────────────────────

def face_quality_score(face_crop: np.ndarray, min_size: int = 60) -> float:
    """Return a graded quality score in [0.05, 1.0] for a face crop.

    Never returns hard zero — callers decide their own minimum via
    FACE_QUALITY_* constants (PRESENCE=0.05, RECOGNITION=0.2,
    ENROLLMENT=0.5, SELF_UPDATE=0.7).
    """
    h, w = face_crop.shape[:2]
    gray = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
    blur = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    brightness = float(gray.mean())

    blur_score = min(blur / 500.0, 1.0)
    size_score = min(min(h, w) / 200.0, 1.0)

    if brightness < 30.0 or brightness > 220.0:
        bright_penalty = 0.3
    elif brightness < 50.0 or brightness > 200.0:
        bright_penalty = 0.7
    else:
        bright_penalty = 1.0

    score = (blur_score * 0.5 + size_score * 0.5) * bright_penalty
    return float(max(0.05, min(score, 1.0)))


# ── V2: Yaw estimation from 5-point landmarks ─────────────────────────────────

def estimate_yaw_from_landmarks(landmarks: np.ndarray, bbox: tuple) -> float:
    """Estimate horizontal face yaw in degrees from 5-point RetinaFace landmarks.

    Uses asymmetry of the eye midpoint relative to the face bounding-box centre.
    Returns values roughly in [-90, +90]; values beyond ±60 are considered
    too side-on for reliable embedding.
    """
    left_eye, right_eye = landmarks[0], landmarks[1]
    face_width = float(bbox[2] - bbox[0])
    if face_width <= 0:
        return 0.0
    eye_mid_x  = (left_eye[0] + right_eye[0]) / 2.0
    face_mid_x = (bbox[0] + bbox[2]) / 2.0
    return float((eye_mid_x - face_mid_x) / face_width * 180.0)


# ── V3: Temporal embedding buffer ─────────────────────────────────────────────

class TemporalEmbeddingBuffer:
    """Pool face embeddings across consecutive frames for stable recognition.

    Keyed by SORT track_id when available, otherwise falls back to a coarse
    64-px grid slot derived from bbox centre. track_id keying ensures the
    buffer stays associated with the same person even when they move between
    frames, improving recognition stability under motion/lighting changes.
    """

    def __init__(self, max_frames: int = 5):
        self._buffers: dict[int, deque] = {}
        self._max_frames = max_frames

    def _slot(self, bbox: tuple, track_id: Optional[int] = None) -> int:
        """Return a stable key: prefer track_id, fall back to bbox grid slot."""
        if track_id is not None:
            # Use negative track_id to avoid collision with positive bbox-slot keys
            return -track_id
        cx = (bbox[0] + bbox[2]) // 2
        cy = (bbox[1] + bbox[3]) // 2
        return (cx // 64) * 10000 + (cy // 64)

    def add_and_pool(
        self,
        bbox:      tuple,
        embedding: np.ndarray,
        track_id:  Optional[int] = None,
    ) -> np.ndarray:
        """Add embedding and return the mean-pooled result for this face track."""
        key = self._slot(bbox, track_id)
        if key not in self._buffers:
            self._buffers[key] = deque(maxlen=self._max_frames)
        self._buffers[key].append(embedding)
        stacked = np.stack(list(self._buffers[key]))
        pooled  = stacked.mean(axis=0)
        norm    = np.linalg.norm(pooled)
        return (pooled / norm).astype(np.float32) if norm > 0 else embedding

    def pool_depth(self, track_id: int) -> int:
        """Return how many frames are pooled for this track (0 if unseen)."""
        return len(self._buffers.get(-track_id, []))

    def clear_stale(
        self,
        active_bboxes: list[tuple],
        active_track_ids: Optional[list[int]] = None,
    ) -> None:
        """Evict slots whose face is no longer visible this frame.

        When track_ids are provided, uses them as the primary key for eviction.
        Bbox-slot keys are evicted based on active_bboxes as before.
        """
        active_keys: set[int] = set()
        if active_track_ids:
            active_keys.update(-tid for tid in active_track_ids)
        active_keys.update(
            (((bbox[0] + bbox[2]) // 2) // 64) * 10000 + (((bbox[1] + bbox[3]) // 2) // 64)
            for bbox in active_bboxes
        )
        for key in list(self._buffers):
            if key not in active_keys:
                del self._buffers[key]


# ── V4: Adaptive recognition threshold ───────────────────────────────────────

def adaptive_threshold(quality: float, base: float) -> float:
    """Scale the recognition threshold by face quality.

    High-quality crop (quality→1.0): lower threshold — trust the embedding.
    Low-quality crop (quality→0.0):  raise threshold — demand stronger match.
    Range: base ± 0.04  (e.g. base=0.28 → [0.24, 0.32])
    """
    return float(base - (quality - 0.5) * 0.08)


class FaceDetector:
    """RetinaFace-ResNet50 detector via InsightFace with SORT face tracking (Item 8).

    Runs the neural network every `detect_every` frames. Between detection frames,
    SORT's Kalman filter predicts bounding box positions and returns detections
    with stable track_ids but no embeddings (embedding=None). This reduces GPU
    usage on detection by ~80% while keeping track continuity at 30fps.
    """

    def __init__(self, detect_every: int = SORT_DETECT_EVERY):
        import sys, io, insightface
        from core.sort import Sort

        # FaceAnalysis uses the buffalo_l pack which includes RetinaFace detector
        # Auto-downloads on first run (~500MB) — best accuracy available
        # Suppress InsightFace/ONNX verbose stdout (Applied providers, model ignore, set det-size)
        _buf = io.StringIO()
        _old = sys.stdout
        try:
            sys.stdout = _buf
            self._app = insightface.app.FaceAnalysis(
                name='buffalo_l',
                allowed_modules=['detection'],
                providers=['CUDAExecutionProvider']
            )
            self._app.prepare(ctx_id=0, det_size=(640, 640))
        finally:
            sys.stdout = _old
        print(f"[Vision] RetinaFace (buffalo_l) loaded on GPU")

        self._detect_every = detect_every
        self._frame_count  = 0
        self._sort = Sort(
            max_age=SORT_MAX_AGE,
            min_hits=SORT_MIN_HITS,
            iou_threshold=0.3,
        )
        # Cache of last raw detections (with landmarks) for track→landmark lookup
        self._last_raw: dict[int, Detection] = {}   # track_id → detection

    def detect(self, frame: np.ndarray) -> list[Detection]:
        """Detect faces in frame, using SORT tracking to assign stable track IDs.

        On detect frames (every detect_every-th): runs RetinaFace + SORT update.
        On predict frames: runs SORT predict-only, returns tracks with no embeddings.
        """
        self._frame_count += 1
        h, w = frame.shape[:2]

        is_detect_frame = (self._frame_count % self._detect_every == 0)

        if is_detect_frame:
            dets_np, raw_detections = self._run_detection(frame, h, w)
        else:
            dets_np = np.empty((0, 5), dtype=np.float32)
            raw_detections = []

        tracks = self._sort.update(dets_np)

        # Evict _last_raw entries for tracks SORT no longer reports — prevents stale landmarks
        # from a dead/reassigned track_id being served on predict frames (N+1 to N+4 between
        # detect frames). Runs every frame; cost is O(n) where n ≤ SORT_MAX_AGE ≈ 10 tracks.
        active_ids = {int(t[4]) for t in tracks} if len(tracks) > 0 else set()
        self._last_raw = {tid: d for tid, d in self._last_raw.items() if tid in active_ids}

        if len(tracks) == 0:
            return []

        # Build track_id → raw detection mapping on detect frames
        if is_detect_frame and len(dets_np) > 0 and len(tracks) > 0:
            # Match each confirmed track back to its source detection by IoU
            self._last_raw = self._match_tracks_to_raws(tracks, raw_detections)

        # Build output Detection objects with track_ids
        results = []
        for t in tracks:
            x1 = max(0, int(t[0]))
            y1 = max(0, int(t[1]))
            x2 = max(0, min(int(t[2]), w))
            y2 = max(0, min(int(t[3]), h))
            track_id = int(t[4])

            if x2 <= x1 or y2 <= y1:
                continue

            raw = self._last_raw.get(track_id)
            results.append(Detection(
                bbox       = (x1, y1, x2, y2),
                confidence = raw.confidence if raw else 0.5,
                landmarks  = raw.landmarks  if raw else None,
                track_id   = track_id,
                # embedding is None — FaceEmbedder fills it in the pipeline
            ))

        return results

    def _run_detection(
        self, frame: np.ndarray, h: int, w: int
    ) -> tuple[np.ndarray, list[Detection]]:
        """Run RetinaFace on frame. Returns (dets_np for SORT, raw Detection list)."""
        faces = self._app.get(frame)
        dets_list = []
        raw_list  = []

        if not faces:
            return np.empty((0, 5), dtype=np.float32), []

        for face in faces:
            if face.det_score < DETECTION_CONFIDENCE:
                print(f"[Vision] Face det_score={face.det_score:.2f} below threshold {DETECTION_CONFIDENCE} — skipped")
                continue
            x1, y1, x2, y2 = face.bbox.astype(int)
            x1 = max(0, min(int(x1), w))
            y1 = max(0, min(int(y1), h))
            x2 = max(0, min(int(x2), w))
            y2 = max(0, min(int(y2), h))
            if x2 <= x1 or y2 <= y1:
                continue
            score = float(face.det_score)
            dets_list.append([x1, y1, x2, y2, score])
            raw_list.append(Detection(
                bbox      = (x1, y1, x2, y2),
                confidence = score,
                landmarks  = face.kps.astype(np.float32) if face.kps is not None else None,
            ))

        dets_np = np.array(dets_list, dtype=np.float32) if dets_list else np.empty((0, 5), dtype=np.float32)
        return dets_np, raw_list

    def _match_tracks_to_raws(
        self, tracks: np.ndarray, raw_detections: list[Detection]
    ) -> dict[int, Detection]:
        """Match confirmed tracks to raw detections using optimal Hungarian assignment.

        Uses linear_sum_assignment on the IoU cost matrix so each detection is
        assigned to at most one track (1:1), eliminating the greedy multi-claim bug
        where two tracks could steal the same detection.
        """
        from core.sort import _iou_batch
        from scipy.optimize import linear_sum_assignment
        if not raw_detections or len(tracks) == 0:
            return {}
        track_bboxes = tracks[:, :4]
        raw_bboxes   = np.array([list(r.bbox) for r in raw_detections], dtype=np.float32)
        iou          = _iou_batch(track_bboxes, raw_bboxes)   # (T, R)
        # Convert to cost matrix (lower = better) and solve optimally
        row_ind, col_ind = linear_sum_assignment(-iou)
        mapping: dict[int, Detection] = {}
        for t_idx, r_idx in zip(row_ind, col_ind):
            if iou[t_idx, r_idx] > 0.1:
                mapping[int(tracks[t_idx, 4])] = raw_detections[r_idx]
        return mapping

class FaceEmbedder:
    """AdaFace IR101 face embedder via ONNX Runtime."""

    def __init__(self, model_path: str = None):
        if model_path is None:
            model_path = str(MODEL_DIR / "adaface_ir101.onnx")

        available = ort.get_available_providers()
        if "CUDAExecutionProvider" not in available:
            raise RuntimeError(
                f"CUDAExecutionProvider not available (available: {available}). "
                "Install onnxruntime-gpu and ensure CUDA 12.x is installed."
            )
        self._session    = ort.InferenceSession(model_path, providers=["CUDAExecutionProvider"])
        self._input_name = self._session.get_inputs()[0].name
        print(f"[Vision] AdaFace loaded on GPU")

    def embed(self, face_crop: np.ndarray) -> np.ndarray:
        """Extract 512-dim embedding from a face crop."""
        img = self._preprocess(face_crop)
        output = self._session.run(None, {self._input_name: img})
        embedding = output[0].flatten()
        # L2 normalize
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm
        return embedding.astype(np.float32)

    def _preprocess(self, face_crop: np.ndarray) -> np.ndarray:
        img = cv2.resize(face_crop, (112, 112))
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img = img.astype(np.float32)
        img = (img - 127.5) / 128.0
        img = img.transpose(2, 0, 1)[np.newaxis]
        return img


class Camera:
    def __init__(self, index: int = 0, width: int = FRAME_WIDTH, height: int = FRAME_HEIGHT):
        if sys.platform == "win32":
            backend      = cv2.CAP_DSHOW
            backend_name = "DirectShow"
        else:
            backend      = getattr(cv2, "CAP_V4L2", cv2.CAP_ANY)
            backend_name = "V4L2"

        self._index   = index
        self._backend = backend
        self._width   = width
        self._height  = height

        self._cap = cv2.VideoCapture(index, backend)
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH,  width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self._cap.set(cv2.CAP_PROP_FPS,          30)
        if not self._cap.isOpened():
            raise RuntimeError(f"Cannot open camera {index}")
        print(f"[Vision] Camera {index} opened ({width}x{height}) via {backend_name}")

    def reconnect(self) -> bool:
        """Release and reopen the camera. Returns True if successfully reopened."""
        try:
            self._cap.release()
        except Exception:
            pass
        self._cap = cv2.VideoCapture(self._index, self._backend)
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH,  self._width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._height)
        self._cap.set(cv2.CAP_PROP_FPS, 30)
        return self._cap.isOpened()

    def read(self) -> Optional[np.ndarray]:
        ret, frame = self._cap.read()
        return frame if ret else None

    def capture_frames(self, n: int = 10, interval: float = 0.5) -> list[np.ndarray]:
        """Capture n frames for enrollment (synchronous — for use outside async contexts)."""
        import time
        frames = []
        for _ in range(n):
            frame = self.read()
            if frame is not None:
                frames.append(frame)
            time.sleep(interval)
        return frames

    async def capture_frames_async(
        self, n: int = 10, interval: float = 0.5,
        stop_event: asyncio.Event | None = None
    ) -> list[np.ndarray]:
        """Capture n frames for enrollment — async version.

        Uses asyncio.sleep between frames so the event loop stays responsive.
        stop_event: asyncio.Event — if set, capture exits early (for shutdown).
        """
        frames = []
        for _ in range(n):
            if stop_event is not None and stop_event.is_set():
                break
            frame = self.read()
            if frame is not None:
                frames.append(frame)
            await asyncio.sleep(interval)
        return frames

    @staticmethod
    def gui_available() -> bool:
        """Return True if OpenCV can open windows on the current display."""
        try:
            cv2.namedWindow("_probe", cv2.WINDOW_NORMAL)
            cv2.destroyWindow("_probe")
            return True
        except cv2.error:
            return False

    def capture_frames_with_preview(self, n: int = 10, interval: float = 0.5) -> list[np.ndarray]:
        """
        Show live preview window. Press SPACE to start capture, Q to quit.
        Green box drawn around detected region during capture.
        Falls back to headless capture when OpenCV has no GUI support.
        """
        import time

        if not Camera.gui_available():
            print("[Camera] GUI unavailable — falling back to headless capture")
            return self.capture_frames(n=n, interval=interval)

        print("[Camera] Preview window open. Press SPACE to capture, Q to quit.")
        cv2.namedWindow("DOG-AI Enrollment", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("DOG-AI Enrollment", 800, 450)

        # Wait for SPACE keypress
        while True:
            frame = self.read()
            if frame is None:
                continue

            display = frame.copy()
            cv2.putText(
                display,
                "Press SPACE to start capture | Q to quit",
                (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2
            )
            cv2.imshow("DOG-AI Enrollment", display)

            key = cv2.waitKey(1) & 0xFF
            if key == ord(' '):
                break
            elif key == ord('q'):
                cv2.destroyAllWindows()
                return []

        # Capture n frames with countdown shown on screen
        frames = []
        for i in range(n):
            frame = self.read()
            if frame is None:
                continue

            frames.append(frame)

            display = frame.copy()
            remaining = n - i
            cv2.putText(
                display,
                f"Capturing... {remaining} frames left",
                (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2
            )
            # Draw a green border to show capturing is active
            h, w = display.shape[:2]
            cv2.rectangle(display, (0, 0), (w-1, h-1), (0, 255, 0), 4)
            cv2.imshow("DOG-AI Enrollment", display)
            cv2.waitKey(1)
            time.sleep(interval)

        cv2.destroyAllWindows()
        print(f"[Camera] Captured {len(frames)} frames")
        return frames

    def release(self):
        self._cap.release()


class AntiSpoofChecker:
    """MiniFASNet liveness detection — vendored from minivision-ai/Silent-Face-Anti-Spoofing (MIT).

    Ensembles two models (MiniFASNetV2 at crop scale 2.7 and MiniFASNetV1SE at scale 4.0).
    Softmax probabilities are averaged; argmax==1 means live. Returns True for live faces
    and False for spoof. Gracefully no-ops (available=False) when weights are missing or
    torch isn't available.

    Weight files expected under ``models/antispoof_weights/``:
      - ``2.7_80x80_MiniFASNetV2.pth``
      - ``4_0_0_80x80_MiniFASNetV1SE.pth``

    Download once from the upstream repo's ``resources/anti_spoof_models/`` directory.
    """

    # Upstream predict input is the model's softmax [fake, live, spoof]; we also
    # enforce a minimum probability so borderline predictions fail-closed.
    def __init__(self, threshold: float = 0.6):
        from collections import deque
        from core.config import LOG_ANTISPOOF_SUMMARY_INTERVAL
        self._models: list[tuple[object, float]] = []  # [(nn.Module, crop_scale), ...]
        self._threshold = threshold
        self._device = None
        # Rolling live_prob samples for LOG_ANTISPOOF_SUMMARY. Deque of the last
        # INTERVAL frames; every INTERVAL calls we emit min/mean/max + rejects
        # and then clear. Gives passive drift detection (camera aging, lighting
        # changes) without logging every frame.
        self._recent_live_probs: deque[float] = deque(maxlen=LOG_ANTISPOOF_SUMMARY_INTERVAL)
        self._calls_since_summary: int = 0
        self._rejects_in_window:   int = 0
        try:
            import torch
            from core._minifasnet import load_pretrained
            from pathlib import Path
            w_dir = Path(__file__).resolve().parent.parent / "models" / "antispoof_weights"
            w_files = [
                w_dir / "2.7_80x80_MiniFASNetV2.pth",
                w_dir / "4_0_0_80x80_MiniFASNetV1SE.pth",
            ]
            missing = [p for p in w_files if not p.exists()]
            if missing:
                raise FileNotFoundError(
                    f"MiniFASNet weights missing: {[str(p) for p in missing]}. "
                    "Fetch from https://github.com/minivision-ai/Silent-Face-Anti-Spoofing"
                    "/tree/master/resources/anti_spoof_models"
                )
            self._device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            for wp in w_files:
                model, scale = load_pretrained(wp, self._device)
                self._models.append((model, scale))
            print(f"[Vision] MiniFASNet anti-spoofing loaded ({len(self._models)} models, device={self._device})")
        except Exception as e:
            print(f"[Vision] Anti-spoofing unavailable ({e}) — disabled")
            self._models = []

    @property
    def available(self) -> bool:
        return len(self._models) >= 1

    @staticmethod
    def _crop_face(img: np.ndarray, bbox: tuple, scale: float, out_w: int = 80, out_h: int = 80) -> np.ndarray:
        """Scaled face crop matching the upstream CropImage behavior.

        Expands the detection bbox by `scale` around its centre, clips to the image,
        then resizes to (out_w, out_h). BGR is preserved end-to-end — the models
        were trained on cv2-read images.
        """
        import cv2
        src_h, src_w = img.shape[:2]
        x1, y1, x2, y2 = [int(v) for v in bbox]
        box_w, box_h = x2 - x1, y2 - y1
        if box_w <= 0 or box_h <= 0:
            return cv2.resize(img, (out_w, out_h))
        effective = min((src_h - 1) / box_h, (src_w - 1) / box_w, scale)
        new_w, new_h = box_w * effective, box_h * effective
        cx, cy = x1 + box_w / 2, y1 + box_h / 2
        lx, ly = cx - new_w / 2, cy - new_h / 2
        rx, ry = cx + new_w / 2, cy + new_h / 2
        if lx < 0: rx -= lx; lx = 0
        if ly < 0: ry -= ly; ly = 0
        if rx > src_w - 1: lx -= rx - src_w + 1; rx = src_w - 1
        if ry > src_h - 1: ly -= ry - src_h + 1; ry = src_h - 1
        patch = img[int(ly):int(ry) + 1, int(lx):int(rx) + 1]
        return cv2.resize(patch, (out_w, out_h))

    def is_live(self, frame: np.ndarray, bbox: tuple) -> bool:
        """Return True if the ensemble scores the face as live, False for spoof.

        Fails-safe: returns True on any unexpected error so the system degrades
        gracefully. bbox: (x1, y1, x2, y2) in pixel coordinates.
        """
        if not self._models:
            return True
        try:
            import torch
            x1, y1, x2, y2 = [int(v) for v in bbox]
            if (x2 - x1) <= 0 or (y2 - y1) <= 0:
                return True
            total_probs = None
            for model, scale in self._models:
                patch = self._crop_face(frame, bbox, scale)
                # HWC → CHW, keep values in [0, 255] float range. MiniFASNet's
                # upstream ToTensor explicitly does NOT divide by 255 for numpy
                # inputs (see minivision-ai data_io/functional.py: `return
                # img.float()` after the `img.float().div(255)` line was
                # commented out by upstream contributor "zkx"). Dividing by 255
                # here fed the model values 255× smaller than its training
                # distribution and caused 100% class-2 (replay) rejection on
                # real faces. BGR order preserved — trained on cv2-read images.
                tensor = torch.from_numpy(patch.transpose(2, 0, 1)).float().unsqueeze(0).to(self._device)
                with torch.no_grad():
                    logits = model.forward(tensor)
                    probs  = torch.softmax(logits, dim=1).cpu().numpy()[0]
                total_probs = probs if total_probs is None else total_probs + probs
            from core.config import (
                LOG_ANTISPOOF_PROBS,
                LOG_ANTISPOOF_SUMMARY,
                LOG_ANTISPOOF_SUMMARY_INTERVAL,
            )
            avg = total_probs / len(self._models)
            label = int(avg.argmax())
            confidence = float(avg[label])
            # Label convention: 1 = live, 0/2 = spoof (consistent with upstream).
            verdict = label == 1 and confidence >= self._threshold
            live_prob = float(avg[1])
            # Per-frame diagnostic — gated behind LOG_ANTISPOOF_PROBS for acute
            # debugging only. Keeps the code path paid-for rather than
            # delete-and-reimplement-later when the next spoof puzzle arrives.
            if LOG_ANTISPOOF_PROBS:
                probs_str = "[" + ", ".join(f"{p:.3f}" for p in avg) + "]"
                print(
                    f"[Anti-spoof] probs={probs_str} argmax={label} "
                    f"live_prob={live_prob:.3f} thr={self._threshold} "
                    f"verdict={'LIVE' if verdict else 'SPOOF'}"
                )
            # Rolling summary — passive drift detection. Every INTERVAL calls,
            # emit one line with min/mean/max live_prob + reject count so a slow
            # sensor degradation shows up in logs without per-frame noise.
            if LOG_ANTISPOOF_SUMMARY:
                self._recent_live_probs.append(live_prob)
                self._calls_since_summary += 1
                if not verdict:
                    self._rejects_in_window += 1
                if self._calls_since_summary >= LOG_ANTISPOOF_SUMMARY_INTERVAL:
                    probs = list(self._recent_live_probs)
                    _min = min(probs)
                    _max = max(probs)
                    _mean = sum(probs) / len(probs)
                    print(
                        f"[Anti-spoof] summary over last {len(probs)} frames: "
                        f"min={_min:.2f} mean={_mean:.2f} max={_max:.2f} "
                        f"rejects={self._rejects_in_window} thr={self._threshold}"
                    )
                    self._calls_since_summary = 0
                    self._rejects_in_window   = 0
            return verdict
        except Exception as e:
            print(f"[Vision] Anti-spoof check error ({e}) — allowing")
            return True


def verify_live(
    frame: np.ndarray,
    bbox: tuple,
    checker: "AntiSpoofChecker | None",
) -> bool:
    """Liveness gate used at every engagement path.

    Fails-open: returns True when checker is None or model unavailable.
    Call this before granting any engagement right (wake, session open, alert).
    """
    if checker is None or not checker.available:
        return True
    return checker.is_live(frame, bbox)


class LipTracker:
    """
    Detects active lip motion using inter-frame pixel difference in the mouth region.

    Uses motion (change over time) not position — so anatomical variations like
    open bite or large teeth don't cause false positives. The resting motion level
    is calibrated per-person during their first appearance (WATCHING state).

    update_baseline() — call while person is at rest (system is speaking/greeting)
    update()          — call during LISTENING; returns True if lips are moving
    reset()           — call when a new person is recognized
    """

    _WINDOW         = 8     # frames for rolling mean (~267ms at 30fps)
    _BASELINE_N     = 25    # frames to establish resting baseline
    _STD_MULTIPLIER = 4.0   # threshold = mean + std × this
    _MIN_THRESHOLD  = 1.2   # absolute floor (pixel units)

    def __init__(self):
        self._prev_crop:  np.ndarray | None = None
        self._history:    deque[float]      = deque(maxlen=self._WINDOW)
        self._baseline:   list[float]       = []
        self._threshold:  float             = self._MIN_THRESHOLD
        self._calibrated: bool              = False

    def reset(self) -> None:
        """Call when a new person is recognized."""
        self._prev_crop  = None
        self._history.clear()
        self._baseline.clear()
        self._threshold  = self._MIN_THRESHOLD
        self._calibrated = False

    def update_baseline(self, frame: np.ndarray, bbox: tuple) -> None:
        """Feed frames during silence/greeting to establish resting motion level."""
        if self._calibrated:
            return
        crop = self._mouth_crop(frame, bbox)
        if crop is None:
            return
        score = self._diff_score(crop)
        if score > 0.0:
            self._baseline.append(score)
        if len(self._baseline) >= self._BASELINE_N:
            mean = float(np.mean(self._baseline))
            std  = float(np.std(self._baseline))
            self._threshold  = max(mean + std * self._STD_MULTIPLIER, self._MIN_THRESHOLD)
            self._calibrated = True
            print(f"[Vision] LipTracker calibrated: threshold={self._threshold:.2f} px")

    def update(self, frame: np.ndarray, bbox: tuple) -> bool:
        """Update with current frame. Returns True if lips are actively moving."""
        crop = self._mouth_crop(frame, bbox)
        if crop is None:
            return False
        score = self._diff_score(crop)
        self._history.append(score)
        if len(self._history) < 3:
            return False
        return float(np.mean(list(self._history))) > self._threshold

    def _mouth_crop(self, frame: np.ndarray, bbox: tuple) -> np.ndarray | None:
        x1, y1, x2, y2 = bbox
        h = y2 - y1
        if h < 20:
            return None
        my1 = y1 + int(h * 0.60)
        crop = frame[my1:y2, x1:x2]
        if crop.size == 0:
            return None
        return cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

    def _diff_score(self, crop: np.ndarray) -> float:
        prev = self._prev_crop
        self._prev_crop = crop
        if prev is None or prev.shape != crop.shape:
            return 0.0
        return float(cv2.absdiff(crop, prev).mean())
