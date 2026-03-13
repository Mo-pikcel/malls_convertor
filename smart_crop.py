"""
smart_crop.py — Content-aware crop planning.

Detection tiers (each layer adds more accuracy):
  Tier 1 — OpenCV only (works immediately, no extra installs)
            • Haar cascade face + body detection
            • MSER text-region detection
            • Edge-density saliency
  Tier 2 — ultralytics  (optional, auto-used if installed)
            • YOLOv8 nano — people, products, packshots, objects
  Tier 3 — easyocr      (optional, auto-used if installed)
            • Deep-learning text detection
"""

import logging
import math
import os
from pathlib import Path

log = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# LAZY OPTIONAL IMPORTS
# ──────────────────────────────────────────────

_yolo_model = None
_ocr_reader  = None


def _try_yolo():
    global _yolo_model
    if _yolo_model is None:
        try:
            from ultralytics import YOLO
            _yolo_model = YOLO("yolov8n.pt")
            log.info("smart_crop: YOLOv8 loaded")
        except Exception as exc:
            log.debug("smart_crop: YOLOv8 unavailable (%s)", exc)
            _yolo_model = False
    return _yolo_model or None


def _try_ocr():
    global _ocr_reader
    if _ocr_reader is None:
        try:
            import easyocr
            _ocr_reader = easyocr.Reader(["en"], gpu=False, verbose=False)
            log.info("smart_crop: EasyOCR loaded")
        except Exception as exc:
            log.debug("smart_crop: EasyOCR unavailable (%s)", exc)
            _ocr_reader = False
    return _ocr_reader or None


# ──────────────────────────────────────────────
# KEYFRAME EXTRACTION
# ──────────────────────────────────────────────

def extract_keyframes(video_path: Path, n: int = 3):
    """
    Extract n evenly-spaced frames from the video (at ~10%, 50%, 90%).
    Returns a list of numpy arrays (BGR). Falls back gracefully on error.
    """
    import cv2

    frames = []
    try:
        cap = cv2.VideoCapture(str(video_path))
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total <= 0:
            log.warning("smart_crop: cannot determine frame count for %s", video_path.name)
            cap.release()
            return frames

        positions = [max(0, int(total * p)) for p in _sample_positions(n)]
        for pos in positions:
            cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
            ok, frame = cap.read()
            if ok and frame is not None:
                frames.append(frame)
        cap.release()
    except Exception as exc:
        log.warning("smart_crop: keyframe extraction failed: %s", exc)

    log.info("smart_crop: extracted %d keyframes from %s", len(frames), video_path.name)
    return frames


def _sample_positions(n: int):
    if n == 1:
        return [0.5]
    return [0.1 + (0.8 / (n - 1)) * i for i in range(n)]


# ──────────────────────────────────────────────
# TIER 1 — OPENCV DETECTION (always runs)
# ──────────────────────────────────────────────

def _cascade_path(name: str) -> str:
    import cv2
    return os.path.join(os.path.dirname(cv2.__file__), "data", name)


def _detect_faces_bodies(frame):
    """Return bounding boxes for faces and bodies using Haar cascades."""
    import cv2

    boxes = []
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)

    for cascade_name, scale, neighbors in [
        ("haarcascade_frontalface_default.xml", 1.1, 4),
        ("haarcascade_profileface.xml",         1.1, 4),
        ("haarcascade_upperbody.xml",            1.05, 3),
        ("haarcascade_fullbody.xml",             1.05, 2),
    ]:
        path = _cascade_path(cascade_name)
        if not os.path.exists(path):
            continue
        clf = cv2.CascadeClassifier(path)
        detections = clf.detectMultiScale(gray, scaleFactor=scale, minNeighbors=neighbors,
                                          minSize=(40, 40))
        if len(detections):
            for (x, y, w, h) in detections:
                boxes.append((int(x), int(y), int(w), int(h)))
                log.debug("cascade %s: box (%d,%d,%d,%d)", cascade_name, x, y, w, h)

    return boxes


def _detect_text_regions(frame):
    """
    Use MSER to find stable regions (text blobs, logos, high-contrast areas).
    Returns bounding boxes of clusters of detected regions.
    """
    import cv2
    import numpy as np

    boxes = []
    try:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        mser = cv2.MSER_create(_delta=5, _min_area=100, _max_area=14400)
        regions, _ = mser.detectRegions(gray)
        if not len(regions):
            return boxes

        # Convert point sets to bounding rects
        rects = []
        for pts in regions:
            x, y, w, h = cv2.boundingRect(pts.reshape(-1, 1, 2))
            # Filter out near-full-frame detections
            if w < frame.shape[1] * 0.8 and h < frame.shape[0] * 0.8:
                rects.append((x, y, w, h))

        if not rects:
            return boxes

        # Cluster nearby rects into groups using a simple dilation-merge
        mask = np.zeros(gray.shape, dtype=np.uint8)
        for (x, y, w, h) in rects:
            mask[y:y+h, x:x+w] = 255

        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (30, 10))
        dilated = cv2.dilate(mask, kernel, iterations=3)
        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            area_ratio = (w * h) / (frame.shape[1] * frame.shape[0])
            # Only include regions that are meaningfully sized but not the whole frame
            if 0.002 < area_ratio < 0.5:
                boxes.append((x, y, w, h))
                log.debug("MSER cluster: (%d,%d,%d,%d)", x, y, w, h)

    except Exception as exc:
        log.debug("smart_crop: MSER text detection failed: %s", exc)

    return boxes


def _detect_salient_region(frame):
    """
    Fall back: find the most visually prominent region using edge density.
    Divides the frame into a grid and scores each cell by edge density.
    Returns a bounding box around the highest-scoring region.
    """
    import cv2
    import numpy as np

    h, w = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)

    # 4x4 grid scoring
    grid_r, grid_c = 4, 4
    cell_h, cell_w = h // grid_r, w // grid_c
    scores = np.zeros((grid_r, grid_c))
    for r in range(grid_r):
        for c in range(grid_c):
            cell = edges[r*cell_h:(r+1)*cell_h, c*cell_w:(c+1)*cell_w]
            scores[r, c] = cell.sum()

    # Find best 2x2 block
    best_score, best_r, best_c = 0, 0, 0
    for r in range(grid_r - 1):
        for c in range(grid_c - 1):
            s = scores[r, c] + scores[r+1, c] + scores[r, c+1] + scores[r+1, c+1]
            if s > best_score:
                best_score, best_r, best_c = s, r, c

    bx = best_c * cell_w
    by = best_r * cell_h
    bw = cell_w * 2
    bh = cell_h * 2
    return [(bx, by, bw, bh)]


# ──────────────────────────────────────────────
# TIER 2 — YOLO (optional)
# ──────────────────────────────────────────────

_IMPORTANT_CLASSES = {
    "person", "bottle", "cup", "bowl", "book", "cell phone",
    "laptop", "tv", "monitor", "clock", "vase",
    "handbag", "backpack", "suitcase", "sports ball",
    "umbrella", "tie", "pizza", "donut", "cake",
    "sandwich", "hot dog", "banana", "apple", "orange",
}


def _detect_yolo(frames):
    model = _try_yolo()
    if model is None:
        return []

    boxes = []
    try:
        results = model(frames, conf=0.35, verbose=False)
        for result in results:
            for box in result.boxes:
                cls_name = result.names[int(box.cls)]
                if cls_name not in _IMPORTANT_CLASSES:
                    continue
                x1, y1, x2, y2 = (int(v) for v in box.xyxy[0].tolist())
                boxes.append((x1, y1, x2 - x1, y2 - y1))
    except Exception as exc:
        log.warning("smart_crop: YOLO inference failed: %s", exc)

    return boxes


# ──────────────────────────────────────────────
# TIER 3 — EasyOCR (optional)
# ──────────────────────────────────────────────

def _detect_easyocr(frames):
    reader = _try_ocr()
    if reader is None:
        return []

    import cv2
    boxes = []
    try:
        for frame in frames:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            for (bbox_pts, text, conf) in reader.readtext(rgb, detail=1):
                if conf < 0.4 or not text.strip():
                    continue
                xs = [int(p[0]) for p in bbox_pts]
                ys = [int(p[1]) for p in bbox_pts]
                x, y = min(xs), min(ys)
                w, h = max(xs) - x, max(ys) - y
                boxes.append((x, y, w, h))
    except Exception as exc:
        log.warning("smart_crop: EasyOCR inference failed: %s", exc)

    return boxes


# ──────────────────────────────────────────────
# COMBINED DETECTION ENTRY POINT
# ──────────────────────────────────────────────

def detect_importance_regions(frames) -> list[tuple[int, int, int, int]]:
    """
    Run all available detectors and return combined bounding boxes.
    Always uses OpenCV (Tier 1). Upgrades automatically when
    ultralytics or easyocr are installed.
    """
    if not frames:
        return []

    boxes = []

    # Tier 1: OpenCV (always)
    for frame in frames:
        boxes.extend(_detect_faces_bodies(frame))
        boxes.extend(_detect_text_regions(frame))

    # Tier 2: YOLO (if available)
    yolo_boxes = _detect_yolo(frames)
    if yolo_boxes:
        boxes.extend(yolo_boxes)
        log.info("smart_crop: YOLO added %d boxes", len(yolo_boxes))

    # Tier 3: EasyOCR (if available)
    ocr_boxes = _detect_easyocr(frames)
    if ocr_boxes:
        boxes.extend(ocr_boxes)
        log.info("smart_crop: EasyOCR added %d boxes", len(ocr_boxes))

    # If nothing detected at all, use edge-saliency fallback
    if not boxes:
        log.info("smart_crop: no regions detected, using saliency fallback")
        for frame in frames:
            boxes.extend(_detect_salient_region(frame))

    log.info("smart_crop: %d total importance regions detected", len(boxes))
    return boxes


# ──────────────────────────────────────────────
# CROP OPTIMISATION
# ──────────────────────────────────────────────

def smart_crop_origin(
    video_w: int,
    video_h: int,
    target_w: int,
    target_h: int,
    importance_boxes: list[tuple[int, int, int, int]],
) -> tuple[int, int]:
    """
    Find (crop_x, crop_y) in the post-scale coordinate space that best
    centres the crop window on detected important content.
    Falls back to centre-crop when no boxes are provided.
    """
    if not importance_boxes:
        return max(0, (video_w - target_w) // 2), max(0, (video_h - target_h) // 2)

    scaled_w, scaled_h = _scaled_dims(video_w, video_h, target_w, target_h)
    sx = scaled_w / video_w
    sy = scaled_h / video_h

    # Union of all importance boxes
    ix1 = min(b[0] for b in importance_boxes)
    iy1 = min(b[1] for b in importance_boxes)
    ix2 = max(b[0] + b[2] for b in importance_boxes)
    iy2 = max(b[1] + b[3] for b in importance_boxes)

    # Map to scaled coords and centre crop on the importance centroid
    center_x = ((ix1 + ix2) / 2) * sx
    center_y = ((iy1 + iy2) / 2) * sy

    crop_x = int(center_x - target_w / 2)
    crop_y = int(center_y - target_h / 2)

    crop_x = max(0, min(crop_x, scaled_w - target_w))
    crop_y = max(0, min(crop_y, scaled_h - target_h))

    log.info(
        "smart_crop: %dx%d→%dx%d  crop=(%d,%d)  content_centre=(%.0f,%.0f)",
        video_w, video_h, target_w, target_h, crop_x, crop_y, center_x, center_y,
    )
    return crop_x, crop_y


def _scaled_dims(video_w, video_h, target_w, target_h):
    scale = max(target_w / video_w, target_h / video_h)
    sw = math.ceil(video_w * scale)
    sh = math.ceil(video_h * scale)
    sw += sw % 2
    sh += sh % 2
    return sw, sh


# ──────────────────────────────────────────────
# PREVIEW OVERLAY
# ──────────────────────────────────────────────

def draw_detections(image_path: Path, boxes: list[tuple[int, int, int, int]], out_path: Path) -> bool:
    """Draw green bounding boxes on the thumbnail and save to out_path."""
    try:
        import cv2
        img = cv2.imread(str(image_path))
        if img is None:
            return False
        for (x, y, w, h) in boxes:
            cv2.rectangle(img, (x, y), (x + w, y + h), (0, 200, 80), 2)
        cv2.imwrite(str(out_path), img)
        return True
    except Exception as exc:
        log.warning("smart_crop: draw_detections failed: %s", exc)
        return False
