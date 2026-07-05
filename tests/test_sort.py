"""100% coverage for core.sort — the SORT tracker (Kalman filter + Hungarian
assignment). Pure numpy/scipy logic, no hardware, so every path is directly
testable. Part of the coverage-to-100 campaign (see COVERAGE.md)."""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

import numpy as np
import pytest

from core.sort import (
    Sort,
    KalmanBoxTracker,
    _bbox_to_z,
    _z_to_bbox,
    _iou_batch,
    _associate_detections_to_trackers,
)

# ── _bbox_to_z / _z_to_bbox ──────────────────────────────────────────────────

def test_bbox_to_z_computes_center_scale_ratio():
    z = _bbox_to_z(np.array([10, 20, 50, 60], dtype=np.float32))  # w=40, h=40
    assert z.shape == (4, 1)
    cx, cy, s, r = z.ravel()
    assert cx == pytest.approx(30) and cy == pytest.approx(40)
    assert s == pytest.approx(1600) and r == pytest.approx(1.0)

def test_bbox_to_z_zero_height_defaults_aspect_ratio():
    z = _bbox_to_z(np.array([10, 20, 50, 20], dtype=np.float32))  # h == 0 branch
    assert z.ravel()[3] == pytest.approx(1.0)

def test_z_to_bbox_roundtrip_from_row_vector():
    bb = _z_to_bbox(np.array([30, 40, 1600, 1, 0, 0, 0], dtype=np.float32))
    assert bb == pytest.approx([10, 20, 50, 60], abs=1e-3)

def test_z_to_bbox_accepts_column_vector():
    x = np.array([[30], [40], [1600], [1], [0], [0], [0]], dtype=np.float32)
    assert _z_to_bbox(x).shape == (4,)

def test_z_to_bbox_zero_scale_collapses_box():
    bb = _z_to_bbox(np.array([30, 40, 0, 1, 0, 0, 0], dtype=np.float32))  # w==0 branch
    assert bb[0] == pytest.approx(bb[2]) and bb[1] == pytest.approx(bb[3])

def test_z_to_bbox_negative_scale_ratio_is_clamped_finite():
    bb = _z_to_bbox(np.array([30, 40, -5, 1, 0, 0, 0], dtype=np.float32))  # max(s*r,0)
    assert np.all(np.isfinite(bb))

# ── _iou_batch ───────────────────────────────────────────────────────────────

def test_iou_identical_boxes_is_one():
    a = np.array([[0, 0, 10, 10]], dtype=np.float32)
    assert _iou_batch(a, a)[0, 0] == pytest.approx(1.0)

def test_iou_disjoint_boxes_is_zero():
    a = np.array([[0, 0, 10, 10]], dtype=np.float32)
    b = np.array([[100, 100, 110, 110]], dtype=np.float32)
    assert _iou_batch(a, b)[0, 0] == pytest.approx(0.0)

def test_iou_degenerate_zero_area_union_zero_branch():
    p = np.array([[5, 5, 5, 5]], dtype=np.float32)  # zero area -> union==0 -> where->0.0
    assert _iou_batch(p, p)[0, 0] == pytest.approx(0.0)

def test_iou_partial_overlap_between_zero_and_one():
    a = np.array([[0, 0, 10, 10]], dtype=np.float32)
    b = np.array([[5, 5, 15, 15]], dtype=np.float32)
    v = _iou_batch(a, b)[0, 0]
    assert 0.0 < v < 1.0

# ── KalmanBoxTracker ─────────────────────────────────────────────────────────

def test_kalman_init_state_and_counters():
    t = KalmanBoxTracker(np.array([10, 20, 50, 60], dtype=np.float32))
    assert t.get_state() == pytest.approx([10, 20, 50, 60], abs=1e-2)
    assert t.hits == 1 and t.hit_streak == 1 and t.age == 0 and t.time_since_update == 0

def test_kalman_predict_advances_age_and_time_since_update():
    t = KalmanBoxTracker(np.array([10, 20, 50, 60], dtype=np.float32))
    t.predict()
    assert t.age == 1 and t.time_since_update == 1

def test_kalman_predict_scale_clamp_branch():
    t = KalmanBoxTracker(np.array([10, 20, 50, 60], dtype=np.float32))
    t.x[2] = 1.0
    t.x[6] = -5.0  # x[6] + x[2] = -4 <= 0 -> clamp fires
    t.predict()
    assert float(t.x[6, 0]) == pytest.approx(0.0)

def test_kalman_update_resets_time_since_update_and_bumps_hits():
    t = KalmanBoxTracker(np.array([10, 20, 50, 60], dtype=np.float32))
    t.predict()
    t.update(np.array([12, 22, 52, 62], dtype=np.float32))
    assert t.time_since_update == 0 and t.hits == 2 and t.hit_streak == 2

# ── _associate_detections_to_trackers ────────────────────────────────────────

def test_associate_no_trackers_returns_all_dets_unmatched():
    dets = np.array([[0, 0, 10, 10]], dtype=np.float32)
    m, ud, ut = _associate_detections_to_trackers(dets, np.empty((0, 4), dtype=np.float32))
    assert m.shape == (0, 2) and list(ud) == [0] and ut.size == 0

def test_associate_matches_overlapping_pair():
    dets = np.array([[0, 0, 10, 10]], dtype=np.float32)
    trks = np.array([[0, 0, 10, 10]], dtype=np.float32)
    m, ud, ut = _associate_detections_to_trackers(dets, trks, 0.3)
    assert m.tolist() == [[0, 0]] and ud.size == 0 and ut.size == 0

def test_associate_below_threshold_pair_is_unmatched():
    dets = np.array([[0, 0, 10, 10]], dtype=np.float32)
    trks = np.array([[100, 100, 110, 110]], dtype=np.float32)  # IoU 0 < 0.3
    m, ud, ut = _associate_detections_to_trackers(dets, trks, 0.3)
    assert m.shape == (0, 2) and 0 in ud and 0 in ut

def test_associate_extra_detection_is_unmatched():
    dets = np.array([[0, 0, 10, 10], [200, 200, 210, 210]], dtype=np.float32)
    trks = np.array([[0, 0, 10, 10]], dtype=np.float32)
    m, ud, ut = _associate_detections_to_trackers(dets, trks, 0.3)
    assert m.tolist() == [[0, 0]] and 1 in ud

# ── Sort end-to-end ──────────────────────────────────────────────────────────

def test_sort_init_resets_global_id_counter():
    KalmanBoxTracker._count = 99
    Sort()
    assert KalmanBoxTracker._count == 0

def test_sort_first_frame_confirms_within_min_hits():
    s = Sort(max_age=10, min_hits=2, iou_threshold=0.3)
    out = s.update(np.array([[10, 20, 50, 60, 0.9]], dtype=np.float32))
    assert out.shape == (1, 5)  # frame_count(1) <= min_hits(2) -> confirmed + matched

def test_sort_stable_id_across_frames():
    s = Sort(max_age=10, min_hits=1, iou_threshold=0.3)
    o1 = s.update(np.array([[10, 20, 50, 60, 0.9]], dtype=np.float32))
    o2 = s.update(np.array([[11, 21, 51, 61, 0.9]], dtype=np.float32))
    assert o1[0, 4] == o2[0, 4]

def test_sort_predict_only_frame_returns_confirmed_track():
    s = Sort(max_age=10, min_hits=1, iou_threshold=0.3)
    s.update(np.array([[10, 20, 50, 60, 0.9]], dtype=np.float32))
    out = s.update(np.empty((0, 5), dtype=np.float32))  # len(dets)==0 branch
    assert out.shape[0] == 1

def test_sort_prunes_track_after_max_age():
    s = Sort(max_age=2, min_hits=1, iou_threshold=0.3)
    s.update(np.array([[10, 20, 50, 60, 0.9]], dtype=np.float32))
    for _ in range(5):
        s.update(np.empty((0, 5), dtype=np.float32))
    assert len(s.trackers) == 0

def test_sort_unmatched_detection_creates_new_tracker():
    s = Sort(max_age=10, min_hits=1, iou_threshold=0.3)
    s.update(np.array([[10, 20, 50, 60, 0.9]], dtype=np.float32))
    s.update(np.array([[10, 20, 50, 60, 0.9], [300, 300, 340, 340, 0.9]], dtype=np.float32))
    assert len(s.trackers) == 2

def test_sort_empty_first_frame_returns_empty():
    s = Sort()
    assert s.update(np.empty((0, 5), dtype=np.float32)).shape == (0, 5)
