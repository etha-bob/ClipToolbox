"""Playback engine selection.

Constructs the ffplay PlaybackEngine (default) or the optional mpv engine by
name, falling back to ffplay when mpv is unavailable. The mpv branch imports
its module lazily so the whole feature rips out by deleting playback_mpv.py +
mpv_ipc.py and this branch — nothing else imports them.
"""
from typing import Protocol

from cliptoolbox.core import paths
from cliptoolbox.core import playback as core_playback

ENGINE_FFPLAY = "ffplay"
ENGINE_MPV = "mpv"


class PlaybackEngineLike(Protocol):
    """The surface app.py + CropController drive. Both engines conform
    structurally (no inheritance); this exists for type-checkers and as the
    single written record of the contract."""

    supports_live_scrub: bool
    supports_fast_stills: bool

    @property
    def state(self) -> str: ...
    @property
    def hwnd(self) -> int | None: ...
    @property
    def is_active(self) -> bool: ...
    @property
    def has_pipeline(self) -> bool: ...
    @property
    def concealed(self) -> bool: ...
    @property
    def live_mix_ok(self) -> bool: ...
    @property
    def position(self) -> float: ...

    def configure_media(self, path, duration): ...
    def set_video_chain_provider(self, provider): ...
    def play(self, start_seconds, tracks, width, height): ...
    def pause(self) -> bool: ...
    def resume(self): ...
    def conceal(self) -> bool: ...
    def seek_paused(self, seconds, exact=True): ...
    def hold_paused_at(self, seconds): ...
    def stop(self): ...
    def shutdown(self): ...
    def set_track_volume(self, row, volume) -> bool: ...
    def embed(self, parent_hwnd, width, height) -> bool: ...
    def re_anchor(self, width, height): ...
    def apply_size(self, width, height): ...
    def save_frame(self, seconds, dest_path, on_done, vf=None): ...
    def request_still(self, seconds, vf=None) -> int: ...


def available_engines() -> list[str]:
    engines = [ENGINE_FFPLAY]
    if paths.MPV:
        engines.append(ENGINE_MPV)
    return engines


def normalize_engine_name(name: str | None) -> str:
    return name if name in (ENGINE_FFPLAY, ENGINE_MPV) else ENGINE_FFPLAY


def create_engine(name: str | None, callbacks, wid_provider=None, mpv_cache_mb: int = 100):
    """Return (engine, actual_name). Falls back to ffplay when mpv is
    requested but mpv.exe is missing; actual_name reflects what was built."""
    name = normalize_engine_name(name)
    if name == ENGINE_MPV and paths.MPV:
        from cliptoolbox.core.playback_mpv import MpvPlaybackEngine
        return MpvPlaybackEngine(callbacks, wid_provider, paths.MPV,
                                 cache_mb=mpv_cache_mb), ENGINE_MPV
    return core_playback.PlaybackEngine(callbacks), ENGINE_FFPLAY
