"""
enroll.py — Standalone enrollment script
Called by: python enroll.py --name "Jagan"
Also used by the dashboard /api/enroll endpoint.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

import argparse
import re
import sys
import uuid
import cv2
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

from core.vision import FaceDetector, FaceEmbedder, Camera, \
    face_quality_score, estimate_yaw_from_landmarks, AntiSpoofChecker, verify_live
from core.db     import FaceDB
from core.config import CAMERA_INDEX, FACES_DIR, ANTISPOOFING_ENABLED, ANTISPOOFING_THRESHOLD, FACE_QUALITY_ENROLLMENT


def enroll(name: str, n_frames: int = 10, headless: bool = False):
    print(f"[Enroll] Starting enrollment for: {name}")

    camera       = Camera(CAMERA_INDEX)
    detector     = FaceDetector()
    embedder     = FaceEmbedder()
    db           = FaceDB()
    anti_spoof   = AntiSpoofChecker(threshold=ANTISPOOFING_THRESHOLD) if ANTISPOOFING_ENABLED else None

    # Sanitize the filesystem component of person_id: [a-z0-9_] only, max 50 chars.
    safe = re.sub(r"[^a-z0-9_-]", "_", name.lower())
    safe = re.sub(r"_+", "_", safe).strip("_")[:50] or "unknown"
    person_id = f"{safe}_{uuid.uuid4().hex[:6]}"
    try:
        if headless or not Camera.gui_available():
            if not headless:
                print("[Enroll] GUI not available — switching to headless mode automatically")
            print("[Enroll] Headless mode — capturing directly")
            frames = camera.capture_frames(n=n_frames, interval=0.3)
        else:
            print("[Enroll] Opening camera preview — press SPACE to start capture, Q to quit")
            frames = camera.capture_frames_with_preview(n=n_frames, interval=0.5)

        pending_embeddings = []
        photo_frame        = None

        for i, frame in enumerate(frames):
            detections = detector.detect(frame)
            if not detections:
                print(f"[Enroll] Frame {i+1}: no face detected")
                continue

            # Take largest face
            det = max(detections, key=lambda d: (d.bbox[2]-d.bbox[0]) * (d.bbox[3]-d.bbox[1]))
            x1, y1, x2, y2 = det.bbox
            face_crop = frame[y1:y2, x1:x2]
            if face_crop.size == 0:
                continue

            # V1: skip blurry/tiny/dark crops
            if face_quality_score(face_crop) < FACE_QUALITY_ENROLLMENT:
                print(f"[Enroll] Frame {i+1}: low quality — skipped")
                continue

            # V2: skip side-on faces
            if det.landmarks is not None:
                yaw = estimate_yaw_from_landmarks(det.landmarks, det.bbox)
                if abs(yaw) > 60.0:
                    print(f"[Enroll] Frame {i+1}: yaw {yaw:.0f}° — skipped")
                    continue

            # Anti-spoofing: reject photo/screen attacks during enrollment.
            # P0.S1 D1 — capture verdict for the catch-all in add_embedding below.
            _en_verdict = verify_live(frame, det.bbox, anti_spoof)
            if not _en_verdict:
                print(f"[Enroll] Frame {i+1}: liveness check failed — skipped")
                continue

            embedding = embedder.embed(face_crop)
            # P0.R1 D1: embed() now returns None on cascading CUDA+CPU failure.
            if embedding is None:
                print("[Enroll] ERROR: face embedding failed (CUDA+CPU cascade); aborting")
                sys.exit(1)
            pending_embeddings.append((embedding, _en_verdict))
            if photo_frame is None:
                photo_frame = frame
            print(f"[Enroll] Frame {i+1}: good embedding ({len(pending_embeddings)} total)")

        if not pending_embeddings:
            print("[Enroll] ERROR: No usable face detected. Check camera, lighting, and face angle.")
            sys.exit(1)

        # M11: add_person before add_embedding to satisfy FK constraint
        photo_path = None
        if photo_frame is not None:
            photo_path = str(FACES_DIR / f"{person_id}.jpg")
            cv2.imwrite(photo_path, photo_frame)
        db.add_person(person_id, name, photo_path)
        for emb, _verdict in pending_embeddings:
            db.add_embedding(person_id, emb, "enrollment", anti_spoof_verdict=_verdict)
        print(f"[Enroll] ✓ Enrolled '{name}' as {person_id} with {len(pending_embeddings)} embeddings")
    finally:
        camera.release()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True, help="Person's name")
    parser.add_argument("--frames", type=int, default=10, help="Number of frames to capture")
    parser.add_argument("--headless", action="store_true", help="No GUI, capture directly")
    args = parser.parse_args()
    enroll(args.name, args.frames, args.headless)
