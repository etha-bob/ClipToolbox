"""Auxiliary media probing that is not part of the trim/compression pipeline.

Kept separate from core/probe.py so that file stays byte-identical for the
diff-verifiability contract (probe.py is one of the frozen core modules).
"""
import subprocess

from cliptoolbox.constants import CREATE_NO_WINDOW
from cliptoolbox.core import paths

DEFAULT_FRAME_RATE = 30.0


def probe_frame_rate(filepath: str) -> float | None:
    """Return the video's average frame rate in fps, or None if unknown.

    Used for frame-accurate stepping. Prefers avg_frame_rate and falls back to
    r_frame_rate; both come back as a "num/den" rational from ffprobe.
    """
    cmd = [
        paths.FFPROBE,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=avg_frame_rate,r_frame_rate",
        "-of",
        "default=noprint_wrappers=1",
        filepath,
    ]

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
            creationflags=CREATE_NO_WINDOW,
        )
    except Exception:
        return None

    values: dict[str, str] = {}
    for line in result.stdout.splitlines():
        key, sep, value = line.partition("=")
        if sep:
            values[key.strip()] = value.strip()

    for key in ("avg_frame_rate", "r_frame_rate"):
        fps = _parse_rational(values.get(key))
        if fps and fps > 0:
            return fps

    return None


def probe_video_dimensions(filepath: str) -> tuple[int, int] | None:
    """Return the video's display (width, height) in pixels, or None if unknown.

    Used to map crop rectangles to source pixels. The dimensions are reported
    as they appear after ffmpeg's automatic rotation: if the stream carries a
    90/270-degree display rotation, ffmpeg inserts a transpose ahead of any
    user filter, so the crop editor and crop filter see already-uprighted
    frames. We swap width/height here to match, reading the rotation from
    either the legacy tag or the display-matrix side data.
    """
    cmd = [
        paths.FFPROBE,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height:stream_tags=rotate:stream_side_data=rotation",
        "-of",
        "default=noprint_wrappers=1",
        filepath,
    ]

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
            creationflags=CREATE_NO_WINDOW,
        )
    except Exception:
        return None

    values: dict[str, str] = {}
    for line in result.stdout.splitlines():
        key, sep, value = line.partition("=")
        if sep:
            values[key.strip().lower()] = value.strip()

    try:
        width = int(values.get("width", ""))
        height = int(values.get("height", ""))
    except (TypeError, ValueError):
        return None

    if width <= 0 or height <= 0:
        return None

    rotation = values.get("rotation") or values.get("tag:rotate") or values.get("rotate")
    try:
        degrees = int(round(float(rotation))) if rotation else 0
    except (TypeError, ValueError):
        degrees = 0

    if degrees % 180 != 0:
        width, height = height, width

    return (width, height)


def _parse_rational(text: str | None) -> float | None:
    if not text:
        return None
    text = text.strip()
    try:
        if "/" in text:
            num, _, den = text.partition("/")
            den_value = float(den)
            if den_value == 0:
                return None
            return float(num) / den_value
        return float(text)
    except Exception:
        return None
