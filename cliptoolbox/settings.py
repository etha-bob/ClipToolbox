"""Persistent app settings.

Stored as config.json next to the executable (matching the portable
outputs/ convention); falls back to %APPDATA%/ClipToolbox when the install
directory is not writable. Atomic writes; corrupt or missing files load as
defaults.
"""
import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

from cliptoolbox.core.paths import BASE_DIR

CONFIG_NAME = "config.json"


def _appdata_dir() -> Path:
    root = os.environ.get("APPDATA")
    if root:
        return Path(root) / "ClipToolbox"
    return Path.home() / ".cliptoolbox"


@dataclass
class AppSettings:
    window_geometry: str | None = None
    window_maximized: bool = False
    remember_geometry: bool = True
    compress_enabled: bool = False
    compression_target_mb: str = "9.99"
    compression_resolution: str = "1080p"
    auto_preview_after_load: bool = True
    playback_engine: str = "ffplay"  # "ffplay" (default) or "mpv" (optional)
    mpv_cache_mb: int = 100  # RAM demuxer cache for the mpv engine (instant seeks)
    recent_clips: list[str] = field(default_factory=list)
    last_open_dir: str | None = None


def _candidates() -> list[Path]:
    return [BASE_DIR / CONFIG_NAME, _appdata_dir() / CONFIG_NAME]


def load() -> AppSettings:
    for path in _candidates():
        try:
            if not path.exists():
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                continue
            settings = AppSettings()
            for key, value in data.items():
                if hasattr(settings, key):
                    setattr(settings, key, value)
            if not isinstance(settings.recent_clips, list):
                settings.recent_clips = []
            settings.recent_clips = [str(p) for p in settings.recent_clips][:8]
            return settings
        except Exception:
            continue
    return AppSettings()


def save(settings: AppSettings) -> Path | None:
    payload = json.dumps(asdict(settings), indent=2)

    for target in _candidates():
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(
                dir=str(target.parent), prefix=".config-", suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(payload)
                os.replace(tmp_path, target)
            finally:
                try:
                    Path(tmp_path).unlink(missing_ok=True)
                except Exception:
                    pass
            return target
        except Exception:
            continue

    return None
