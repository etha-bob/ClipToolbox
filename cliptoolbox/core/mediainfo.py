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
