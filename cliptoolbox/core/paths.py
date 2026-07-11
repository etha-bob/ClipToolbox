import os
import shutil
import subprocess
import sys
from pathlib import Path

from cliptoolbox.constants import CREATE_NO_WINDOW, IS_WINDOWS


def get_base_dir() -> Path:
    """
    Development layout:
        project/
          app.py
          ffmpeg/
            bin/
              ffmpeg.exe
              ffprobe.exe
              ffplay.exe

    PyInstaller onedir layout:
        AudioTrackMerger/
          AudioTrackMerger.exe
          _internal/
          ffmpeg/
            bin/
              ffmpeg.exe
              ffprobe.exe
              ffplay.exe
          outputs/
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    # This module lives at cliptoolbox/core/paths.py; the project root is two
    # levels up, matching the old single-file layout.
    return Path(__file__).resolve().parent.parent.parent


BASE_DIR = get_base_dir()
INTERNAL_DIR = BASE_DIR / "_internal"


def get_resource_dir() -> Path:
    """
    Runtime resource layout:

    Development:
        resources live next to app.py

    PyInstaller --onefile:
        bundled resources are extracted to sys._MEIPASS at runtime
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)

    return BASE_DIR


RESOURCE_DIR = get_resource_dir()

FFMPEG_BIN_DIR = RESOURCE_DIR / "ffmpeg" / "bin"
OUTPUTS_DIR = BASE_DIR / "outputs"


def exe_name(name: str) -> str:
    return f"{name}.exe" if IS_WINDOWS else name


def find_tool(name: str) -> str | None:
    local_tool = FFMPEG_BIN_DIR / exe_name(name)

    if local_tool.exists():
        return str(local_tool)

    found = shutil.which(name)
    if found:
        return found

    return None


if FFMPEG_BIN_DIR.exists():
    os.environ["PATH"] = str(FFMPEG_BIN_DIR) + os.pathsep + os.environ.get("PATH", "")

FFMPEG = find_tool("ffmpeg")
FFPROBE = find_tool("ffprobe")
FFPLAY = find_tool("ffplay")

# Optional mpv playback backend. Bundled in an mpv/ folder next to ffmpeg/
# (same convention), or discovered on PATH. Prefer mpv.exe over mpv.com — the
# .com console wrapper re-execs mpv.exe under a different PID, which breaks the
# --wid child-window lookup and the IPC pipe.
MPV_DIR = RESOURCE_DIR / "mpv"


def find_mpv() -> str | None:
    local = MPV_DIR / exe_name("mpv")
    if local.exists():
        return str(local)
    if IS_WINDOWS:
        return shutil.which("mpv.exe") or shutil.which("mpv")
    return shutil.which("mpv")


MPV = find_mpv()


def reveal_file(path: str):
    try:
        if IS_WINDOWS:
            subprocess.run(
                ["explorer", "/select,", path],
                creationflags=CREATE_NO_WINDOW,
            )
        elif sys.platform == "darwin":
            subprocess.run(["open", "-R", path])
        else:
            subprocess.run(["xdg-open", str(Path(path).parent)])
    except Exception:
        pass
