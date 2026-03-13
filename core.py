"""
core.py — Business logic for AdScreen Converter (no UI dependencies).
"""

import json
import os
import subprocess
import datetime
import logging
import shutil
import zipfile
import sys
from pathlib import Path
from dataclasses import dataclass, field

# ──────────────────────────────────────────────
# LOGGING
# ──────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# DIRECTORIES
# ──────────────────────────────────────────────

def get_base_dir() -> Path:
    """Return base directory — works in dev mode and when frozen by flet build."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


BASE_DIR     = get_base_dir()
TEMPLATE_DIR = BASE_DIR / "templates"
INPUT_DIR    = BASE_DIR / "input"
OUTPUT_DIR   = BASE_DIR / "output"
PREVIEW_DIR  = BASE_DIR / "previews"

for _d in (TEMPLATE_DIR, INPUT_DIR, OUTPUT_DIR, PREVIEW_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ──────────────────────────────────────────────
# DATA CLASSES
# ──────────────────────────────────────────────

@dataclass
class Template:
    name: str
    formats: list[tuple]
    description: str = ""
    tags: list[str] = field(default_factory=list)

    @property
    def primary_resolution(self) -> str:
        if self.formats:
            w, h = self.formats[0][0], self.formats[0][1]
            return f"{w}×{h}"
        return "—"

    @classmethod
    def from_file(cls, path: Path) -> "Template":
        with open(path) as f:
            data = json.load(f)
        # Each format entry is either [w, h] or [w, h, "Label"]
        formats = [tuple(fmt) for fmt in data["formats"]]
        return cls(
            name=data["name"],
            formats=formats,
            description=data.get("description", ""),
            tags=data.get("tags", []),
        )


@dataclass
class FormatPlan:
    """Pre-computed export plan for one target resolution."""
    width: int
    height: int
    crop_x: int = 0
    crop_y: int = 0
    label: str = ""  # per-format name; falls back to template name if empty


# ──────────────────────────────────────────────
# FFMPEG UTILITIES
# ──────────────────────────────────────────────

def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def probe_video(path: Path) -> tuple[int, int, float]:
    """Return (width, height, duration_seconds). Raises on failure."""
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,duration",
        "-of", "csv=s=x:p=0",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr}")
    parts = result.stdout.strip().split("x")
    w, h = int(parts[0]), int(parts[1])
    dur = float(parts[2]) if len(parts) > 2 and parts[2] else 0.0
    return w, h, dur


def image_to_video(src: Path, dst: Path, duration: int = 10) -> None:
    """Convert a still image to a looping MP4."""
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", str(src),
        "-t", str(duration),
        "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2,fps=25,format=yuv420p",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        str(dst),
    ]
    _run(cmd)


def generate_thumbnail(src: Path, dst: Path, timestamp: float = 0.5) -> None:
    """Extract a JPEG thumbnail from a video."""
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(timestamp),
        "-i", str(src),
        "-vframes", "1",
        "-q:v", "3",
        str(dst),
    ]
    _run(cmd, check=False)


def export_format(
    src: Path,
    dst: Path,
    width: int,
    height: int,
    crop_x: int,
    crop_y: int,
    crf: int = 18,
    preset: str = "slow",
) -> subprocess.CompletedProcess:
    """Crop-scale a video to the target resolution using a pre-validated crop origin."""
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height}:{crop_x}:{crop_y}"
    )
    cmd = [
        "ffmpeg", "-y",
        "-i", str(src),
        "-vf", vf,
        "-c:v", "libx264",
        "-crf", str(crf),
        "-preset", preset,
        "-movflags", "+faststart",
        str(dst),
    ]
    return _run(cmd)


def _run(cmd: list, check: bool = True) -> subprocess.CompletedProcess:
    log.info("Running: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if check and result.returncode != 0:
        log.error("stderr: %s", result.stderr)
        raise RuntimeError(result.stderr[-500:])
    return result


# ──────────────────────────────────────────────
# TEMPLATE LOADER
# ──────────────────────────────────────────────

def load_templates() -> dict[str, Template]:
    templates = {}
    for p in sorted(TEMPLATE_DIR.glob("*.json")):
        try:
            t = Template.from_file(p)
            display = f"{t.name}  —  {t.primary_resolution}  ({len(t.formats)} formats)"
            templates[display] = t
        except Exception as exc:
            log.warning("Skipping %s: %s", p.name, exc)
    return templates


def template_search_text(t: Template) -> str:
    """Return a single lowercase string of all searchable fields for a template."""
    res_strings = [f"{w}x{h}" for w, h in t.formats]
    return " ".join([
        t.name,
        t.description,
        " ".join(t.tags),
        " ".join(res_strings),
    ]).lower()


# ──────────────────────────────────────────────
# CROP / EXPORT PLANNING
# ──────────────────────────────────────────────

def plan_exports(
    template: Template,
    video_w: int,
    video_h: int,
    importance_boxes: list = None,
) -> list[FormatPlan]:
    """
    Build a crop plan for every format in the template.
    Pass pre-computed importance_boxes (from smart_crop.detect_importance_regions)
    to use smart crop. Falls back to centre-crop when boxes is None or empty.
    """
    plans = []
    for fmt in template.formats:
        target_w, target_h = fmt[0], fmt[1]
        label = fmt[2] if len(fmt) > 2 else ""
        if importance_boxes:
            from smart_crop import smart_crop_origin
            crop_x, crop_y = smart_crop_origin(
                video_w, video_h, target_w, target_h, importance_boxes
            )
        else:
            crop_x = max(0, (video_w - target_w) // 2)
            crop_y = max(0, (video_h - target_h) // 2)
        plans.append(FormatPlan(width=target_w, height=target_h, crop_x=crop_x, crop_y=crop_y, label=label))
    return plans


# ──────────────────────────────────────────────
# ZIP HELPER
# ──────────────────────────────────────────────

def zip_outputs(files: list[Path]) -> Path:
    zip_path = OUTPUT_DIR / f"export_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.write(f, f.name)
    return zip_path
