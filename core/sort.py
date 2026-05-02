"""
core/sort.py — SORT (Simple Online and Realtime Tracking)

Vendored minimal implementation based on abewley/sort (MIT License).
Dependencies: numpy, scipy only — no filterpy, no lap package.
Fully ARM64/Jetson compatible.

Reference: Bewley et al., "Simple Online and Realtime Tracking", ICIP 2016

Architecture:
- KalmanBoxTracker: Kalman filter for a single bounding box
  State:  [cx, cy, s, r, dcx, dcy, ds]  (center x/y, scale, aspect ratio, velocities)
  Obs:    [cx, cy, s, r]
- Sort: manages N trackers with Hungarian assignment (scipy linear_sum_assignment)

Usage:
    tracker = Sort(max_age=10, min_hits=2, iou_threshold=0.3)
    detections = np.array([[x1,y1,x2,y2,score], ...])  # shape (N,5)
    tracks = tracker.update(detections)
    # tracks: np.array([[x1,y1,x2,y2,track_id], ...])

When there are no detections, pass np.empty((0,5)):
    tracks = tracker.update(np.empty((0, 5)))
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import linear_sum_assignment


# ── Kalman filter matrices (constant velocity model) ─────────────────────────

# State transition: assume constant velocity
_F = np.array([
    [1, 0, 0, 0, 1, 0, 0],
    [0, 1, 0, 0, 0, 1, 0],
    [0, 0, 1, 0, 0, 0, 1],
    [0, 0, 0, 1, 0, 0, 0],
    [0, 0, 0, 0, 1, 0, 0],
    [0, 0, 0, 0, 0, 1, 0],
    [0, 0, 0, 0, 0, 0, 1],
], dtype=np.float32)

# Measurement matrix: observe cx, cy, s, r
_H = np.array([
    [1, 0, 0, 0, 0, 0, 0],
    [0, 1, 0, 0, 0, 0, 0],
    [0, 0, 1, 0, 0, 0, 0],
    [0, 0, 0, 1, 0, 0, 0],
], dtype=np.float32)

# Process noise covariance
_Q = np.diag([1., 1., 1., 1., 0.01, 0.01, 0.0001]).astype(np.float32)

# Measurement noise covariance
_R = np.diag([1., 1., 10., 10.]).astype(np.float32)


def _bbox_to_z(bbox: np.ndarray) -> np.ndarray:
    """Convert [x1,y1,x2,y2] bbox to state observation [cx, cy, s, r]."""
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    cx = bbox[0] + w / 2.0
    cy = bbox[1] + h / 2.0
    s = w * h          # scale = area
    r = w / float(h) if h > 0 else 1.0  # aspect ratio
    return np.array([[cx], [cy], [s], [r]], dtype=np.float32)


def _z_to_bbox(x: np.ndarray) -> np.ndarray:
    """Convert state [cx, cy, s, r, ...] to [x1, y1, x2, y2]."""
    x = x.ravel()   # accept both (7,) and (7,1) Kalman state vectors
    cx, cy, s, r = float(x[0]), float(x[1]), float(x[2]), float(x[3])
    w = np.sqrt(max(s * r, 0.0))
    h = s / w if w > 0 else 0.0
    return np.array([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], dtype=np.float32)


def _iou_batch(bb_det: np.ndarray, bb_trk: np.ndarray) -> np.ndarray:
    """Compute IoU between all pairs of detections and tracks.

    Args:
        bb_det: (N, 4) — detection bboxes [x1,y1,x2,y2]
        bb_trk: (M, 4) — track bboxes [x1,y1,x2,y2]
    Returns:
        (N, M) IoU matrix
    """
    bb_det = np.expand_dims(bb_det, 1)   # (N,1,4)
    bb_trk = np.expand_dims(bb_trk, 0)  # (1,M,4)

    inter_x1 = np.maximum(bb_det[..., 0], bb_trk[..., 0])
    inter_y1 = np.maximum(bb_det[..., 1], bb_trk[..., 1])
    inter_x2 = np.minimum(bb_det[..., 2], bb_trk[..., 2])
    inter_y2 = np.minimum(bb_det[..., 3], bb_trk[..., 3])

    inter_area = np.maximum(inter_x2 - inter_x1, 0) * np.maximum(inter_y2 - inter_y1, 0)

    area_det = (bb_det[..., 2] - bb_det[..., 0]) * (bb_det[..., 3] - bb_det[..., 1])
    area_trk = (bb_trk[..., 2] - bb_trk[..., 0]) * (bb_trk[..., 3] - bb_trk[..., 1])

    union = area_det + area_trk - inter_area
    return np.where(union > 0, inter_area / union, 0.0)


class KalmanBoxTracker:
    """Kalman filter tracker for a single bounding box.

    State vector: [cx, cy, scale, aspect_ratio, dcx, dcy, dscale]
    """

    _count = 0  # global ID counter (class-level; reset by Sort.__init__)

    def __init__(self, bbox: np.ndarray) -> None:
        KalmanBoxTracker._count += 1
        self.id = KalmanBoxTracker._count

        # Kalman state and covariance
        self.x = np.zeros((7, 1), dtype=np.float32)
        z = _bbox_to_z(bbox)
        self.x[:4] = z
        self.P = np.eye(7, dtype=np.float32) * 10.0
        self.P[4:, 4:] *= 1000.0  # high initial uncertainty for velocities

        self.hits            = 1
        self.hit_streak      = 1
        self.age             = 0
        self.time_since_update = 0

    def predict(self) -> np.ndarray:
        """Advance state; return predicted bbox [x1,y1,x2,y2]."""
        # Clamp scale to avoid numerical blow-up
        if self.x[6] + self.x[2] <= 0:
            self.x[6] = 0.0
        self.x  = _F @ self.x
        self.P  = _F @ self.P @ _F.T + _Q
        self.age += 1
        self.time_since_update += 1
        return _z_to_bbox(self.x)

    def update(self, bbox: np.ndarray) -> None:
        """Update tracker with a matched detection bbox."""
        self.time_since_update = 0
        self.hits += 1
        self.hit_streak += 1

        z = _bbox_to_z(bbox)
        y = z - _H @ self.x                                   # innovation
        S = _H @ self.P @ _H.T + _R                          # innovation covariance
        K = self.P @ _H.T @ np.linalg.inv(S)                 # Kalman gain
        self.x = self.x + K @ y
        self.P = (np.eye(7, dtype=np.float32) - K @ _H) @ self.P

    def get_state(self) -> np.ndarray:
        """Return current bbox estimate [x1,y1,x2,y2]."""
        return _z_to_bbox(self.x)


def _associate_detections_to_trackers(
    detections: np.ndarray,
    trackers:   np.ndarray,
    iou_threshold: float = 0.3,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Match detections to existing trackers using Hungarian algorithm on IoU.

    Returns:
        matches:          (K, 2) int array of (det_idx, trk_idx) matched pairs
        unmatched_dets:   (U,) int array of unmatched detection indices
        unmatched_trks:   (V,) int array of unmatched tracker indices
    """
    if trackers.shape[0] == 0:
        return (
            np.empty((0, 2), dtype=int),
            np.arange(len(detections)),
            np.empty(0, dtype=int),
        )

    iou = _iou_batch(detections, trackers)         # (N, M)
    cost = 1.0 - iou

    row_ind, col_ind = linear_sum_assignment(cost)
    matched_indices = np.stack([row_ind, col_ind], axis=1)

    # Filter out matches below IoU threshold
    unmatched_dets = [d for d in range(len(detections)) if d not in row_ind]
    unmatched_trks = [t for t in range(len(trackers))  if t not in col_ind]

    matches = []
    for r, c in matched_indices:
        if iou[r, c] < iou_threshold:
            unmatched_dets.append(r)
            unmatched_trks.append(c)
        else:
            matches.append([r, c])

    matches_arr = np.array(matches, dtype=int).reshape(-1, 2) if matches else np.empty((0, 2), dtype=int)
    return matches_arr, np.array(unmatched_dets, dtype=int), np.array(unmatched_trks, dtype=int)


class Sort:
    """SORT multi-object tracker.

    Maintains a pool of KalmanBoxTrackers, one per active face track.
    Tracks are identified by stable integer IDs that persist across frames
    even during brief occlusions (up to max_age missed frames).

    Face detection (neural net) runs every Nth frame; SORT fills in positions
    for the N-1 intermediate frames using Kalman filter predictions.
    """

    def __init__(
        self,
        max_age:       int   = 10,
        min_hits:      int   = 2,
        iou_threshold: float = 0.3,
    ) -> None:
        self.max_age       = max_age
        self.min_hits      = min_hits
        self.iou_threshold = iou_threshold
        self.trackers:  list[KalmanBoxTracker] = []
        self.frame_count = 0
        KalmanBoxTracker._count = 0   # reset IDs when tracker is created

    def update(self, dets: np.ndarray) -> np.ndarray:
        """Run one SORT update step.

        Args:
            dets: (N, 5) array of [x1, y1, x2, y2, score], or np.empty((0,5))
                  on frames where detection is skipped (predict-only).

        Returns:
            (M, 5) array of [x1, y1, x2, y2, track_id] for confirmed tracks.
            Confirmed = hit_streak >= min_hits OR frame_count <= min_hits.
        """
        self.frame_count += 1

        # Predict new locations for all existing trackers
        predicted_bboxes = []
        for trk in self.trackers:
            predicted_bboxes.append(trk.predict())
        trk_arr = np.array(predicted_bboxes, dtype=np.float32).reshape(-1, 4) if predicted_bboxes else np.empty((0, 4), dtype=np.float32)

        # Only associate when we have actual detections
        if len(dets) > 0:
            det_bboxes = dets[:, :4]
            matched, unmatched_dets, unmatched_trks = _associate_detections_to_trackers(
                det_bboxes, trk_arr, self.iou_threshold
            )

            # Update matched trackers
            for d_idx, t_idx in matched:
                self.trackers[t_idx].update(dets[d_idx, :4])

            # Create new trackers for unmatched detections
            for d_idx in unmatched_dets:
                self.trackers.append(KalmanBoxTracker(dets[d_idx, :4]))

            # Mark unmatched trackers as missed (already done by predict())
            # They will be pruned below after max_age misses

        # Collect confirmed tracks and prune dead ones
        results   = []
        survivors = []
        for trk in self.trackers:
            state = trk.get_state()
            is_confirmed = (trk.hit_streak >= self.min_hits) or (self.frame_count <= self.min_hits)
            if trk.time_since_update <= self.max_age:
                survivors.append(trk)
                if is_confirmed and trk.time_since_update == 0:
                    # Only return track when it was updated this frame (matched detection)
                    results.append(np.append(state, [trk.id]))
                elif is_confirmed and len(dets) == 0:
                    # Predict-only frame: return predicted position for all confirmed tracks
                    results.append(np.append(state, [trk.id]))

        self.trackers = survivors

        return np.array(results, dtype=np.float32).reshape(-1, 5) if results else np.empty((0, 5), dtype=np.float32)
