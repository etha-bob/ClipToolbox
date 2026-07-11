"""Per-video session persistence.

Remembers each clip's editing setup (trim points, crop keyframes, track
mix, playhead) so reopening the same file restores where you left off.
Stored as sessions.json next to config.json, with the same appdata
fallback and atomic-write rules as settings. Entries are keyed by the
resolved path and validated against the file's current size, so a
re-rendered clip at the same path doesn't inherit stale times. Clips
left at pure defaults never get an entry; the store is LRU-capped.
"""
import json
import os
import tempfile
import time
from pathlib import Path

from cliptoolbox.core.paths import BASE_DIR
from cliptoolbox.settings import _appdata_dir

SESSIONS_NAME = "sessions.json"
MAX_SESSIONS = 40


def _candidates() -> list[Path]:
    return [BASE_DIR / SESSIONS_NAME, _appdata_dir() / SESSIONS_NAME]


def _key(video_path: str) -> str:
    try:
        return str(Path(video_path).resolve()).casefold()
    except Exception:
        return str(video_path).casefold()


def _file_size(video_path: str) -> int | None:
    try:
        return Path(video_path).stat().st_size
    except Exception:
        return None


def _read_all() -> dict:
    for path in _candidates():
        try:
            if not path.exists():
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            sessions = data.get("sessions") if isinstance(data, dict) else None
            if isinstance(sessions, dict):
                return sessions
        except Exception:
            continue
    return {}


def _write_all(sessions: dict) -> None:
    payload = json.dumps({"version": 1, "sessions": sessions}, indent=2)

    for target in _candidates():
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(
                dir=str(target.parent), prefix=".sessions-", suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(payload)
                os.replace(tmp_path, target)
            finally:
                try:
                    Path(tmp_path).unlink(missing_ok=True)
                except Exception:
                    pass
            return
        except Exception:
            continue


def is_default_state(state: dict) -> bool:
    """True when the setup matches a freshly loaded clip (nothing worth
    remembering — playhead position alone doesn't earn an entry)."""
    trim = state.get("trim") or {}
    if trim.get("enabled") or trim.get("start") is not None or trim.get("end") is not None:
        return False
    crop = state.get("crop") or {}
    if crop.get("enabled") or crop.get("keyframes"):
        return False
    for track in state.get("tracks") or []:
        try:
            volume = float(track.get("volume", 1.0))
        except (TypeError, ValueError):
            volume = 1.0
        if not track.get("enabled", True) or abs(volume - 1.0) > 1e-6:
            return False
    return True


def load(video_path: str) -> dict | None:
    """The saved state for this clip, or None if absent or stale."""
    entry = _read_all().get(_key(video_path))
    if not isinstance(entry, dict):
        return None
    size = _file_size(video_path)
    if size is not None and entry.get("size") is not None and entry.get("size") != size:
        return None
    state = entry.get("state")
    return state if isinstance(state, dict) else None


def save(video_path: str, state: dict) -> None:
    """Write (or clear) this clip's saved state. A default state removes any
    existing entry — the user deliberately cleared their setup."""
    sessions = _read_all()
    key = _key(video_path)

    if is_default_state(state):
        if key not in sessions:
            return
        sessions.pop(key, None)
    else:
        sessions[key] = {
            "path": str(video_path),
            "size": _file_size(video_path),
            "saved_at": time.time(),
            "state": state,
        }
        if len(sessions) > MAX_SESSIONS:
            def age(item):
                entry = item[1]
                saved = entry.get("saved_at") if isinstance(entry, dict) else None
                return saved if isinstance(saved, (int, float)) else 0.0
            newest = sorted(sessions.items(), key=age, reverse=True)[:MAX_SESSIONS]
            sessions = dict(newest)

    _write_all(sessions)
