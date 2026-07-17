"""Timeline strip asset extraction (filmstrip tiles + per-track waveforms).

Pure and Tk-free, shaped for core.render_queue: each ``*_work`` factory
returns a ``work(token)`` callable that runs on a queue worker, spawns the
bundled ffmpeg, attaches the process to the token (so ``cancel_group`` can
kill it mid-decode), and returns the cache path. Any PIL composition for
display happens on the Tk thread in the caller's ``on_done``.

Cache files live beside the config (mirroring the recents-thumbs layout) and
are keyed on path + mtime + physical size, so a re-recorded file or a DPI
change naturally misses and re-extracts.
"""
import hashlib
import os
import subprocess
from pathlib import Path

from cliptoolbox.constants import CREATE_NO_WINDOW
from cliptoolbox.core.paths import FFMPEG
from cliptoolbox.core.win32 import assign_process_to_cleanup_job

# One tile per ~0.5 s so short clips don't repeat frames across slots, capped
# at 40 (the usability-report budget: one whole-clip decode per load).
FILMSTRIP_MAX_TILES = 40
FILMSTRIP_MIN_TILES = 4

# A hung ffmpeg must not hold a queue worker hostage forever; a whole-clip
# decode of a long recording is slow but nowhere near this.
EXTRACT_TIMEOUT_S = 300

# Waveform source resolution: wide enough that a zoomed view crops rather
# than runs out of pixels immediately; rendered white-on-transparent so the
# UI can tint per skin + mix state without invalidating the disk cache.
WAVEFORM_WIDTH = 2048


def cache_dir() -> Path:
    """`%APPDATA%/ClipToolbox/timeline` (sibling of the recents `thumbs`)."""
    base = os.environ.get("APPDATA")
    root = Path(base) / "ClipToolbox" if base else Path.home() / ".cliptoolbox"
    return root / "timeline"


def filmstrip_tile_count(duration: float) -> int:
    return min(FILMSTRIP_MAX_TILES, max(FILMSTRIP_MIN_TILES, int(duration / 0.5)))


def _cache_key(video_path: str, *parts) -> str:
    try:
        mtime = int(Path(video_path).stat().st_mtime)
    except Exception:
        mtime = 0
    raw = "|".join([video_path, str(mtime), *map(str, parts)])
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def filmstrip_cache_path(video_path: str, h_phys: int, n: int) -> Path:
    return cache_dir() / f"{_cache_key(video_path, 'strip', h_phys, n)}.png"


def filmstrip_work(video_path: str, cache_path: Path, h_phys: int, n: int,
                   duration: float):
    """One ffmpeg pass: n frames evenly across the clip, tiled into a single
    n x 1 strip PNG at h_phys pixels tall (width follows aspect)."""

    def work(token):
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        vf = f"fps={n}/{duration:.6f},scale=-2:{h_phys},tile={n}x1"
        cmd = [
            FFMPEG, "-hide_banner", "-loglevel", "error",
            "-i", video_path,
            "-vf", vf, "-frames:v", "1",
            "-y", str(cache_path),
        ]
        process = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW,
        )
        token.attach_process(process)  # cancel_group kills mid-decode
        assign_process_to_cleanup_job(process)  # app exit kills too
        try:
            process.wait(timeout=EXTRACT_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            process.kill()
        return cache_path

    return work


def waveform_cache_path(video_path: str, stream_index: int, w: int, h: int) -> Path:
    return cache_dir() / f"{_cache_key(video_path, 'wave', stream_index, w, h)}.png"


def waveform_work(video_path: str, cache_path: Path, stream_index: int,
                  w: int, h: int):
    """One ffmpeg pass per audio stream: a white-on-transparent peak
    waveform PNG. stream_index is the ABSOLUTE ffmpeg stream index from the
    probe (mapped as [0:{index}]), not the audio-relative position."""

    def work(token):
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        graph = (f"[0:{stream_index}]aformat=channel_layouts=mono,"
                 f"showwavespic=s={w}x{h}:filter=peak:colors=white[w]")
        cmd = [
            FFMPEG, "-hide_banner", "-loglevel", "error",
            "-i", video_path,
            "-filter_complex", graph, "-map", "[w]", "-frames:v", "1",
            "-y", str(cache_path),
        ]
        process = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW,
        )
        token.attach_process(process)
        assign_process_to_cleanup_job(process)
        try:
            process.wait(timeout=EXTRACT_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            process.kill()
        return cache_path

    return work
