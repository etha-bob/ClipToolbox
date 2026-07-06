import os
import subprocess

from cliptoolbox.constants import CREATE_NO_WINDOW
from cliptoolbox.core import paths


def ffplay_start_env() -> dict:
    """
    Start FFplay's SDL window offscreen so Windows does not show the temporary
    white SDL window in the middle of the desktop before we re-parent it.
    """
    env = os.environ.copy()
    env["SDL_VIDEO_WINDOW_POS"] = "-32000,-32000"
    env["SDL_VIDEO_CENTERED"] = "0"
    return env


def build_preview_stream_cmds(
    input_path: str,
    filter_complex: str,
    start_seconds: float,
    width: int,
    height: int,
) -> tuple[list[str], list[str]]:
    ffmpeg_cmd = [
        paths.FFMPEG,
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{start_seconds:.3f}",
        "-i",
        input_path,
        "-filter_complex",
        filter_complex,
        "-map",
        "0:v:0?",
        "-map",
        "[aout]",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-f",
        "matroska",
        "pipe:1",
    ]

    ffplay_cmd = [
        paths.FFPLAY,
        "-autoexit",
        "-loglevel",
        "error",
        "-x",
        str(width),
        "-y",
        str(height),
        "-left",
        "-32000",
        "-top",
        "-32000",
        "-i",
        "pipe:0",
    ]

    return ffmpeg_cmd, ffplay_cmd


def spawn_preview_pipeline(
    ffmpeg_cmd: list[str],
    ffplay_cmd: list[str],
) -> tuple[subprocess.Popen, subprocess.Popen]:
    ffmpeg_process = subprocess.Popen(
        ffmpeg_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        creationflags=CREATE_NO_WINDOW,
    )

    ffplay_process = subprocess.Popen(
        ffplay_cmd,
        stdin=ffmpeg_process.stdout,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=CREATE_NO_WINDOW,
        env=ffplay_start_env(),
    )

    # Let ffplay own the pipe endpoint. This helps ffmpeg receive broken
    # pipe correctly if ffplay is stopped.
    if ffmpeg_process.stdout:
        try:
            ffmpeg_process.stdout.close()
        except Exception:
            pass

    return ffmpeg_process, ffplay_process


def build_frame_extract_cmd(
    input_path: str,
    seconds: float,
    frame_path: str,
) -> list[str]:
    return [
        paths.FFMPEG,
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{seconds:.3f}",
        "-i",
        input_path,
        "-map",
        "0:v:0",
        "-frames:v",
        "1",
        "-an",
        "-sn",
        "-dn",
        "-q:v",
        "2",
        "-y",
        frame_path,
    ]
