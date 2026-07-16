import subprocess
import sys

# ============================================================
# App constants / runtime helpers
# ============================================================

APP_NAME = "ClipToolbox"
APP_VERSION = ""

# ============================================================
# USER EDIT ME: window / layout sizing
# ============================================================
# These are the main dimensions to tweak while testing the app layout.
# Start by changing WINDOW_START_WIDTH. If the window will not get as
# narrow as you want, lower WINDOW_MIN_WIDTH too.
WINDOW_START_WIDTH = 740
WINDOW_START_HEIGHT = 900
WINDOW_MIN_WIDTH = 700
WINDOW_MIN_HEIGHT = 760

# When audio tracks load, the app recalculates height. This keeps that
# auto-height behavior while still respecting your chosen window width.
WINDOW_AUTO_HEIGHT_BASE = 760

# Preview frame sizing.
# Larger inset = narrower preview inside the same app window.
# Height scale lets you fine-tune the preview box aspect ratio.
# 1.05 means 5% taller than strict 16:9.
PREVIEW_WIDTH_INSET = 64
PREVIEW_HEIGHT_SCALE = 0.965  # B1: reclaim pure letterbox for the timeline strip

# These can also limit how narrow the app feels. Lower them only if the
# audio slider area is forcing the window wider than you want.
AUDIO_SLIDER_MIN_WIDTH = 360
AUDIO_SLIDER_PIXEL_LENGTH = 420

DEFAULT_WINDOW_WIDTH = WINDOW_START_WIDTH
DEFAULT_WINDOW_HEIGHT = WINDOW_START_HEIGHT
MIN_WINDOW_WIDTH = WINDOW_MIN_WIDTH
MIN_WINDOW_HEIGHT = WINDOW_MIN_HEIGHT

PREVIEW_WIDTH = max(320, WINDOW_START_WIDTH - PREVIEW_WIDTH_INSET)
PREVIEW_HEIGHT = int(PREVIEW_WIDTH * 9 / 16 * PREVIEW_HEIGHT_SCALE)

DEFAULT_COMPRESSION_TARGET_MB = 9.99
# Treat the compression target like Windows Explorer / Discord-visible MB.
# Windows labels MiB as MB, so 9.99 MB here means 9.99 * 1024 * 1024 bytes by default.
WINDOWS_MB_BYTES = 1024 * 1024
DECIMAL_MB_BYTES = 1000 * 1000
COMPRESSION_RETRY_STEP_MB = 0.3
MIN_COMPRESSION_BUDGET_MB = 1.0
COMPRESSION_MAX_ATTEMPTS = 8
COMPRESSION_TARGET_FILL_RATIO = 0.995
COMPRESSION_BUDGET_EPSILON_MB = 0.05
COMPRESSION_DEFAULT_AUDIO_KBPS = 64
DEFAULT_COMPRESSION_RESOLUTION = "1080p"

# Timestamp watermark: pulls the recording time out of the source filename and
# burns it bottom-left, fading out after a chosen visible duration.
DEFAULT_TIMESTAMP_WATERMARK_DURATION_MS = 3000
TIMESTAMP_WATERMARK_FADE_MS = 500

# Keyframed crop/zoom ("pan/crop"). A crop transform forces a video
# re-encode (the standard export path is otherwise stream-copy), so the
# standard path switches to NVENC constant-quality when a motion filter is
# present. Lower CQ = higher quality / larger file.
CROP_EXPORT_CQ = 19
# Smallest crop rect the editor allows, in source pixels (clamped to the
# source dimension for tiny videos).
CROP_MIN_SIZE = 16
# scale flags for the live preview motion chain; bilinear keeps the animated
# zoom cheap enough for real-time playback (export uses ffmpeg's default).
PREVIEW_MOTION_SCALE_FLAGS = "bilinear"
COMPRESSION_RESOLUTION_PRESETS = {
    "1080p": (1920, 1080),
    "720p": (1280, 720),
    "600p": (1066, 600),
}


def format_windows_discord_size(size_bytes: int | float | None) -> str:
    """Return filesize using Windows/Discord-style MB first, plus decimal MB for sanity checks."""
    try:
        size_bytes = max(0, int(size_bytes or 0))
    except Exception:
        size_bytes = 0

    windows_mb = size_bytes / WINDOWS_MB_BYTES
    decimal_mb = size_bytes / DECIMAL_MB_BYTES
    return f"{windows_mb:.2f} MB in Windows/Discord ({decimal_mb:.2f} decimal MB)"


IS_WINDOWS = sys.platform == "win32"
CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0


def format_seconds(seconds: float | None) -> str:
    if seconds is None:
        return "0:00"

    seconds = int(max(0, seconds))
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"

    return f"{minutes}:{secs:02d}"
