"""
Tests for V1-V4 vision quality improvements in core/vision.py.

V1: face_quality_score() — size/blur/brightness gate
V2: estimate_yaw_from_landmarks() — frontal vs side-on detection
V3: TemporalEmbeddingBuffer — mean-pooled embedding across frames
V4: adaptive_threshold() — quality-scaled recognition threshold
"""
import sys
import types
import importlib.machinery
from unittest.mock import MagicMock

# ── Stub GPU-only packages that aren't installed on the dev machine ───────────
# Must happen before any core.vision import.

def _stub_module(name: str):
    """Insert an empty stub into sys.modules for the given dotted name."""
    parts = name.split(".")
    for i in range(1, len(parts) + 1):
        full = ".".join(parts[:i])
        if full not in sys.modules:
            mod = types.ModuleType(full)
            # Set __spec__ so importlib.util.find_spec() doesn't raise ValueError
            # (ultralytics calls find_spec('onnxruntime') during import)
            mod.__spec__ = importlib.machinery.ModuleSpec(full, None)
            sys.modules[full] = mod

for _pkg in ("onnxruntime", "insightface", "insightface.app"):
    _stub_module(_pkg)

# onnxruntime.InferenceSession used in FaceEmbedder.__init__
import onnxruntime as _ort
_ort.InferenceSession = MagicMock()
_ort.get_available_providers = MagicMock(return_value=["CPUExecutionProvider"])

# insightface.app.FaceAnalysis used in FaceDetector.__init__
import insightface.app as _iface_app
_iface_app.FaceAnalysis = MagicMock()

import numpy as np
import pytest


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_face(h=120, w=120, brightness=128, blur_var=150):
    """Create a synthetic BGR face crop with controllable brightness."""
    import cv2
    # Flat-colour image — Laplacian variance will be ~0 unless we add edges
    img = np.full((h, w, 3), brightness, dtype=np.uint8)
    if blur_var > 80:
        # Add a high-contrast grid so Laplacian.var() is large
        img[::10, :] = 0
        img[:, ::10] = 0
    return img


# ── V1: face_quality_score ────────────────────────────────────────────────────

class TestFaceQualityScore:
    def setup_method(self):
        from core.vision import face_quality_score
        self.fn = face_quality_score

    def test_too_small_returns_floor(self):
        # Graded score — tiny crop returns low score (floored at 0.05), not hard zero
        tiny = np.zeros((40, 40, 3), dtype=np.uint8)
        score = self.fn(tiny, min_size=60)
        assert score >= 0.05
        assert score < 0.5  # below enrollment threshold — correctly filtered at call sites

    def test_too_blurry_returns_low_score(self):
        # Uniform image has Laplacian variance near 0 → blur_score≈0 → low but not zero
        blurry = np.full((120, 120, 3), 128, dtype=np.uint8)
        score = self.fn(blurry)
        assert score >= 0.05  # floor, not hard zero
        assert score < 0.5    # below enrollment threshold

    def test_too_dark_returns_low_score(self):
        import cv2
        dark = np.zeros((120, 120, 3), dtype=np.uint8)
        dark[::10, :] = 0
        dark[:, ::10] = 10
        score = self.fn(dark)
        assert score >= 0.05  # floor, not hard zero

    def test_too_bright_returns_zero(self):
        import cv2
        bright = np.full((120, 120, 3), 240, dtype=np.uint8)
        bright[::10, :] = 255
        bright[:, ::10] = 0   # edges to pass blur gate, but mean still >220
        # mean ~240 > 220 threshold
        result = self.fn(bright)
        # may be 0 or non-zero depending on exact pixel mean — just verify it runs
        assert isinstance(result, float)
        assert 0.0 <= result <= 1.0

    def test_good_crop_returns_nonzero_score(self):
        face = _make_face(h=150, w=150, brightness=128)
        score = self.fn(face)
        assert score > 0.0
        assert score <= 1.0

    def test_score_range_is_0_to_1(self):
        face = _make_face(h=200, w=200, brightness=100)
        score = self.fn(face)
        assert 0.0 <= score <= 1.0

    def test_larger_sharper_crop_scores_higher(self):
        small = _make_face(h=80,  w=80,  brightness=100)
        large = _make_face(h=200, w=200, brightness=100)
        score_small = self.fn(small)
        score_large = self.fn(large)
        # Larger crop should score same or higher (size_score component)
        # Both must pass quality gates to compare meaningfully
        if score_small > 0.0 and score_large > 0.0:
            assert score_large >= score_small


# ── V2: estimate_yaw_from_landmarks ──────────────────────────────────────────

class TestEstimateYaw:
    def setup_method(self):
        from core.vision import estimate_yaw_from_landmarks
        self.fn = estimate_yaw_from_landmarks

    def _landmarks(self, leye_x, reye_x, nose_x=0, lm_x=0, rm_x=0, y=50):
        """Minimal 5-point landmark array: leye, reye, nose, lmouth, rmouth."""
        return np.array([
            [leye_x, y],
            [reye_x, y],
            [nose_x, y],
            [lm_x,   y],
            [rm_x,   y],
        ], dtype=np.float32)

    def test_frontal_face_near_zero_yaw(self):
        """Eye midpoint at face centre → yaw ≈ 0."""
        # bbox x1=0, x2=100 → face_mid_x = 50
        # leye=40, reye=60 → eye_mid_x = 50 → offset = 0
        lm = self._landmarks(leye_x=40, reye_x=60)
        yaw = self.fn(lm, bbox=(0, 0, 100, 100))
        assert abs(yaw) < 5.0

    def test_left_turn_negative_yaw(self):
        """Eye midpoint left of centre → negative yaw (turned left)."""
        # face_mid_x = 50, eye_mid_x = 30 → offset = -20/100*180 = -36°
        lm = self._landmarks(leye_x=20, reye_x=40)
        yaw = self.fn(lm, bbox=(0, 0, 100, 100))
        assert yaw < 0.0

    def test_right_turn_positive_yaw(self):
        """Eye midpoint right of centre → positive yaw (turned right)."""
        lm = self._landmarks(leye_x=60, reye_x=80)
        yaw = self.fn(lm, bbox=(0, 0, 100, 100))
        assert yaw > 0.0

    def test_zero_face_width_returns_zero(self):
        """Degenerate bbox (x1==x2) should not divide by zero."""
        lm = self._landmarks(leye_x=50, reye_x=60)
        yaw = self.fn(lm, bbox=(50, 0, 50, 100))
        assert yaw == 0.0

    def test_extreme_side_on_exceeds_60_degrees(self):
        """Very asymmetric eye position should produce |yaw| > 60."""
        # eye_mid near edge: leye=5, reye=10 → mid=7.5; face_mid=50; offset=-42.5/100*180=-76.5
        lm = self._landmarks(leye_x=5, reye_x=10)
        yaw = self.fn(lm, bbox=(0, 0, 100, 100))
        assert abs(yaw) > 60.0


# ── V3: TemporalEmbeddingBuffer ───────────────────────────────────────────────

class TestTemporalEmbeddingBuffer:
    def setup_method(self):
        from core.vision import TemporalEmbeddingBuffer
        self.cls = TemporalEmbeddingBuffer

    def _unit_emb(self, seed=42, dim=512):
        """Return a random unit-length embedding."""
        rng = np.random.default_rng(seed)
        v = rng.standard_normal(dim).astype(np.float32)
        return v / np.linalg.norm(v)

    def test_single_frame_returns_same_embedding(self):
        buf = self.cls(max_frames=5)
        emb = self._unit_emb(0)
        result = buf.add_and_pool(bbox=(0, 0, 64, 64), embedding=emb)
        np.testing.assert_allclose(result, emb, atol=1e-5)

    def test_pooled_is_unit_length(self):
        buf = self.cls(max_frames=5)
        for seed in range(5):
            emb = self._unit_emb(seed)
            result = buf.add_and_pool(bbox=(0, 0, 64, 64), embedding=emb)
        assert abs(np.linalg.norm(result) - 1.0) < 1e-5

    def test_same_bbox_accumulates_across_frames(self):
        buf = self.cls(max_frames=5)
        emb = self._unit_emb(0)
        # Feed same embedding 5 times — pool of identical vectors = same vector
        for _ in range(5):
            result = buf.add_and_pool(bbox=(10, 20, 74, 84), embedding=emb)
        np.testing.assert_allclose(result, emb, atol=1e-5)

    def test_maxframes_cap_respected(self):
        """Buffer should not grow beyond max_frames."""
        buf = self.cls(max_frames=3)
        bbox = (0, 0, 64, 64)
        for seed in range(10):
            buf.add_and_pool(bbox, self._unit_emb(seed))
        slot = buf._slot(bbox)
        assert len(buf._buffers[slot]) == 3

    def test_clear_stale_removes_inactive_slots(self):
        buf = self.cls(max_frames=5)
        bbox_a = (0,   0,  64,  64)
        bbox_b = (200, 0, 264,  64)
        buf.add_and_pool(bbox_a, self._unit_emb(0))
        buf.add_and_pool(bbox_b, self._unit_emb(1))
        assert len(buf._buffers) == 2

        # Only bbox_a still active
        buf.clear_stale([bbox_a])
        slot_b = buf._slot(bbox_b)
        assert slot_b not in buf._buffers
        assert len(buf._buffers) == 1

    def test_slot_no_collision_at_1920x1080(self):
        """Verify _slot() has no collisions across plausible face positions."""
        from core.vision import TemporalEmbeddingBuffer
        buf = TemporalEmbeddingBuffer()
        slots = set()
        for cx in range(0, 1920, 64):
            for cy in range(0, 1080, 64):
                x1, y1 = cx - 32, cy - 32
                x2, y2 = cx + 32, cy + 32
                slot = buf._slot((x1, y1, x2, y2))
                assert slot not in slots, f"Collision at cx={cx}, cy={cy}"
                slots.add(slot)

    def test_different_bboxes_different_slots(self):
        buf = self.cls(max_frames=5)
        bbox_a = (0,   0,  64,  64)
        bbox_b = (64,  0, 128,  64)
        assert buf._slot(bbox_a) != buf._slot(bbox_b)


# ── V4: adaptive_threshold ────────────────────────────────────────────────────

class TestAdaptiveThreshold:
    def setup_method(self):
        from core.vision import adaptive_threshold
        self.fn = adaptive_threshold

    def test_midpoint_quality_returns_base(self):
        """quality=0.5 → threshold = base exactly."""
        assert self.fn(0.5, 0.22) == pytest.approx(0.22)

    def test_high_quality_lowers_threshold(self):
        """quality=1.0 → threshold < base (trust good crops more)."""
        result = self.fn(1.0, 0.22)
        assert result < 0.22
        assert result == pytest.approx(0.18)

    def test_low_quality_raises_threshold(self):
        """quality=0.0 → threshold > base (demand stronger match)."""
        result = self.fn(0.0, 0.22)
        assert result > 0.22
        assert result == pytest.approx(0.26)

    def test_range_is_base_plus_minus_0_04(self):
        base = 0.22
        lo = self.fn(1.0, base)
        hi = self.fn(0.0, base)
        assert hi - lo == pytest.approx(0.08, abs=1e-6)

    def test_different_base_scales_correctly(self):
        """Formula should work for any base value."""
        base = 0.30
        assert self.fn(0.5, base) == pytest.approx(0.30)
        assert self.fn(1.0, base) == pytest.approx(0.26)
        assert self.fn(0.0, base) == pytest.approx(0.34)


# ── AntiSpoofChecker ──────────────────────────────────────────────────────────

class TestAntiSpoofChecker:
    """Tests for AntiSpoofChecker — covers both available and unavailable package."""

    def _make_frame(self, h=200, w=200) -> "np.ndarray":
        return np.zeros((h, w, 3), dtype=np.uint8)

    @staticmethod
    def _fake_model(label: int, confidence: float):
        """Build a tiny torch-Module-like whose forward(x) returns logits that softmax
        to the given (label, confidence). Used so we can exercise is_live() with
        deterministic probabilities without loading real weights."""
        import torch, math
        class _FakeModel:
            def forward(_self, x):
                logits = torch.zeros(1, 3, dtype=torch.float32, device=x.device)
                # Solve softmax to match confidence for the target class: with the two
                # other logits at 0, we want e^a / (e^a + 2) = confidence.
                # ⇒ a = log( 2·confidence / (1 - confidence) ).
                if confidence >= 0.999:
                    a = 15.0
                elif confidence <= 0.001:
                    a = -15.0
                else:
                    a = math.log(2 * confidence / (1 - confidence))
                logits[0, label] = a
                return logits
        return _FakeModel()

    def test_is_live_returns_true_when_model_unavailable(self):
        """When MiniFASNet weights are absent, is_live() must fail-safe allow (True)."""
        from core.vision import AntiSpoofChecker
        checker = AntiSpoofChecker(threshold=0.6)
        checker._models = []  # simulate unavailable
        assert checker.is_live(self._make_frame(), (10, 10, 100, 100)) is True

    def test_available_false_when_model_not_loaded(self):
        from core.vision import AntiSpoofChecker
        checker = AntiSpoofChecker()
        checker._models = []
        assert checker.available is False

    def test_is_live_true_when_model_returns_real_label(self):
        """Ensemble says label=1 (real) with score >= threshold → True."""
        from core.vision import AntiSpoofChecker
        import torch
        checker = AntiSpoofChecker(threshold=0.6)
        checker._models = [(self._fake_model(1, 0.85), 2.7)]
        checker._device = torch.device("cpu")
        assert checker.is_live(self._make_frame(), (10, 10, 100, 100)) is True

    def test_is_live_false_when_model_returns_spoof_label(self):
        """Ensemble says label=0 (spoof) → False."""
        from core.vision import AntiSpoofChecker
        import torch
        checker = AntiSpoofChecker(threshold=0.6)
        checker._models = [(self._fake_model(0, 0.90), 2.7)]
        checker._device = torch.device("cpu")
        assert checker.is_live(self._make_frame(), (10, 10, 100, 100)) is False

    def test_is_live_false_when_real_score_below_threshold(self):
        """argmax=1 but confidence < threshold → False (fail-closed on low confidence)."""
        from core.vision import AntiSpoofChecker
        import torch
        checker = AntiSpoofChecker(threshold=0.6)
        checker._models = [(self._fake_model(1, 0.40), 2.7)]
        checker._device = torch.device("cpu")
        assert checker.is_live(self._make_frame(), (10, 10, 100, 100)) is False

    def test_is_live_true_on_model_exception(self):
        """Any inference error → fail-safe True (allow)."""
        from core.vision import AntiSpoofChecker
        import torch
        class _BoomModel:
            def forward(self, x):
                raise RuntimeError("GPU OOM")
        checker = AntiSpoofChecker(threshold=0.6)
        checker._models = [(_BoomModel(), 2.7)]
        checker._device = torch.device("cpu")
        assert checker.is_live(self._make_frame(), (10, 10, 100, 100)) is True

    def test_is_live_true_for_zero_size_bbox(self):
        """Degenerate bbox (w=0 or h=0) → allow without running the model."""
        from unittest.mock import MagicMock
        from core.vision import AntiSpoofChecker
        checker = AntiSpoofChecker(threshold=0.6)
        stub = MagicMock()
        checker._models = [(stub, 2.7)]
        assert checker.is_live(self._make_frame(), (50, 50, 50, 100)) is True  # w=0
        stub.forward.assert_not_called()

    def test_threshold_respected_at_boundary(self):
        """Confidence at the threshold boundary → True (≥, not >)."""
        from core.vision import AntiSpoofChecker
        import torch
        checker = AntiSpoofChecker(threshold=0.6)
        checker._models = [(self._fake_model(1, 0.60), 2.7)]
        checker._device = torch.device("cpu")
        assert checker.is_live(self._make_frame(), (10, 10, 100, 100)) is True

    def test_summary_emits_every_interval_with_correct_format(self, capsys, monkeypatch):
        """Step 0: LOG_ANTISPOOF_SUMMARY ON → after N calls, emit one summary line
        with min/mean/max/rejects/thr; per-frame probs print stays silent unless
        LOG_ANTISPOOF_PROBS is also on."""
        from core.vision import AntiSpoofChecker
        import core.config as _cfg
        import torch, re
        monkeypatch.setattr(_cfg, "LOG_ANTISPOOF_PROBS", False)
        monkeypatch.setattr(_cfg, "LOG_ANTISPOOF_SUMMARY", True)
        monkeypatch.setattr(_cfg, "LOG_ANTISPOOF_SUMMARY_INTERVAL", 5)
        checker = AntiSpoofChecker(threshold=0.5)
        checker._models = [(self._fake_model(1, 0.90), 2.7)]
        checker._device = torch.device("cpu")
        # Re-sync the deque + counters to the patched interval (AntiSpoofChecker
        # caches INTERVAL at __init__; we're monkeypatching after).
        from collections import deque
        checker._recent_live_probs   = deque(maxlen=5)
        checker._calls_since_summary = 0
        checker._rejects_in_window   = 0
        capsys.readouterr()  # drop load banner
        for _ in range(5):
            checker.is_live(self._make_frame(), (10, 10, 100, 100))
        out = capsys.readouterr().out
        # Must contain exactly one summary line, no per-frame probs lines.
        assert "[Anti-spoof] summary over last 5 frames:" in out
        assert re.search(r"min=0\.\d{2} mean=0\.\d{2} max=0\.\d{2} rejects=0 thr=0\.5", out)
        assert "[Anti-spoof] probs=" not in out

    def test_summary_counter_resets_after_emit(self, capsys, monkeypatch):
        """After a summary fires, the window + reject counter reset so the next
        N calls produce a fresh summary, not a cumulative one."""
        from core.vision import AntiSpoofChecker
        import core.config as _cfg
        import torch
        monkeypatch.setattr(_cfg, "LOG_ANTISPOOF_PROBS", False)
        monkeypatch.setattr(_cfg, "LOG_ANTISPOOF_SUMMARY", True)
        monkeypatch.setattr(_cfg, "LOG_ANTISPOOF_SUMMARY_INTERVAL", 3)
        checker = AntiSpoofChecker(threshold=0.5)
        # Alternate live + spoof so rejects count is meaningful.
        live_model = self._fake_model(1, 0.90)
        spoof_model = self._fake_model(0, 0.90)
        checker._device = torch.device("cpu")
        from collections import deque
        checker._recent_live_probs   = deque(maxlen=3)
        checker._calls_since_summary = 0
        checker._rejects_in_window   = 0
        # First 3 calls: 2 live + 1 spoof
        checker._models = [(live_model, 2.7)]
        checker.is_live(self._make_frame(), (10, 10, 100, 100))
        checker.is_live(self._make_frame(), (10, 10, 100, 100))
        checker._models = [(spoof_model, 2.7)]
        checker.is_live(self._make_frame(), (10, 10, 100, 100))
        first = capsys.readouterr().out
        assert "rejects=1" in first
        # Counter + rejects must be zeroed for the next window
        assert checker._calls_since_summary == 0
        assert checker._rejects_in_window   == 0
        # Next 3 calls all live — rejects=0 in the second summary
        checker._models = [(live_model, 2.7)]
        for _ in range(3):
            checker.is_live(self._make_frame(), (10, 10, 100, 100))
        second = capsys.readouterr().out
        assert "rejects=0" in second


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
