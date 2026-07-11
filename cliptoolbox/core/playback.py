"""Streaming preview playback engine.

Replaces the old kill-and-respawn preview design (core/preview.py plus the
flag machine in app.py) with one persistent, stateful engine:

- The pipeline is still FFmpeg -> pipe -> FFplay, but FFmpeg now sends
  pre-scaled rawvideo + PCM audio in a NUT stream. Uncompressed video keeps
  FFplay's demux queue small (its 15 MB cap holds only a few hundred
  milliseconds of raw frames), so live audio commands become audible almost
  immediately instead of a second later.
- Pause uses FFplay's own pause toggle (a posted spacebar keystroke carrying
  a real scancode) instead of killing the pipeline; resume posts it again.
  Both directions are effectively instant, the frozen frame stays on screen
  in the live window, and FFplay handles the A/V clocks natively. FFmpeg
  pauses itself on pipe backpressure, so nothing burns CPU while paused.
  Nothing is ever suspended: NtSuspendProcess on the window-owning process
  froze Tk whenever an activation/z-order change sent that window a
  synchronous message (that is why the original suspend-pause "deadlocked
  after idling in the background"). A watchdog confirms each posted key by
  watching the stats clock and falls back to a kill-based pause/respawn.
- Track volumes/mutes are applied live through FFmpeg's runtime filter
  command interface over its stdin pipe (spawned with -stdin). The preview
  filter graph always contains every track (disabled rows at volume 0), which
  with amix normalize=0 is audibly identical to omitting them, so toggling a
  checkbox never needs a graph rebuild.
- Playback position comes from FFplay's own -stats master clock on stderr
  instead of a wall-clock guess.

The engine is tkinter-free. Events are delivered through PlaybackCallbacks;
see its docstring for the threading contract. All public methods must be
called from the UI thread.
"""
import os
import re
import subprocess
import tempfile
import threading
import time
from collections import deque
from pathlib import Path
from typing import Callable, Protocol

from cliptoolbox.constants import CREATE_NO_WINDOW, IS_WINDOWS
from cliptoolbox.core import filters as core_filters
from cliptoolbox.core import paths
from cliptoolbox.core import win32

# Engine states
IDLE = "idle"          # no pipeline, nothing paused
STARTING = "starting"  # pipeline spawned, first frame not yet on screen
PLAYING = "playing"
PAUSED = "paused"      # frozen; pipeline may be suspended or already gone

# Payload kinds for on_still_frame
STILL_KIND_JPEG = "jpeg"  # encoded image bytes (ffmpeg frame extract)
STILL_KIND_BGRA = "bgra"  # raw top-down 32-bit rows (pause-time window capture)

# The request id used for pause-time captures (always current by definition).
PAUSE_STILL_REQUEST = -1

WINDOW_POLL_INTERVAL = 0.01
WINDOW_POLL_TIMEOUT = 5.0
POSITION_EMIT_INTERVAL = 0.1
COMMAND_FLUSH_INTERVAL = 0.04
STILL_EXTRACT_TIMEOUT = 6.0

_STATS_CLOCK_RE = re.compile(rb"^\s*(\d+(?:\.\d+)?)\s")


class PlaybackCallbacks(Protocol):
    """Engine -> UI event surface.

    Threading contract: callbacks raised inside a public method call
    (pause/resume/stop emit on_state and on_still_frame this way) run
    synchronously on the calling UI thread. Everything else — on_position,
    on_first_frame, on_window_ready, on_ended, on_error, async still frames,
    and the state changes that follow spawn/exit — fires from engine worker
    threads, so the receiver must marshal onto the UI thread itself.
    """

    def on_state(self, state: str) -> None: ...

    def on_position(self, seconds: float) -> None: ...

    def on_window_ready(self, hwnd: int) -> None: ...

    def on_embed_timeout(self) -> None: ...

    def on_first_frame(self) -> None: ...

    def on_still_frame(
        self, kind: str, payload: bytes, width: int, height: int, request_id: int
    ) -> None: ...

    def on_still_failed(self, request_id: int) -> None: ...

    def on_pause_slipped(self) -> None: ...

    def on_cache_ranges(self, ranges: list[tuple[float, float]]) -> None:
        """Cached (instantly seekable) time ranges changed. Only the mpv
        engine emits this; ffplay has no cache. Fires from a worker thread."""
        ...

    def on_ended(self, at_seconds: float) -> None: ...

    def on_error(self, title: str, message: str) -> None: ...


def ffplay_start_env() -> dict:
    """
    Ask SDL to place FFplay's window far offscreen for the short gap between
    spawn and embed. Recent SDL builds create the window hidden at screen
    center and only apply this position at first show, so the embed path must
    still never make the window visible before SetParent.
    """
    env = os.environ.copy()
    env["SDL_VIDEO_WINDOW_POS"] = "-32000,-32000"
    env["SDL_VIDEO_CENTERED"] = "0"
    return env


def build_playback_filter(
    tracks: list[tuple[int, float]],
    width: int,
    height: int,
    video_chain: str | None = None,
) -> str:
    """
    Superset preview graph: every audio track (disabled rows arrive here with
    volume 0.0) through the standard build_audio_filter, plus a video scale to
    the preview size so the piped video can be rawvideo without flooding the
    pipe at source resolution.

    The audio chains come first so FFmpeg's auto-generated filter instance
    names line up with track rows: row i == Parsed_volume_i, which is what the
    live volume commands target.

    video_chain, when provided, replaces the default fit-scale entirely. A
    crop/zoom motion chain is built at the preview fit size (see core.motion),
    so it already produces the correct display geometry and there is nothing
    left to scale afterwards.
    """
    audio = core_filters.build_audio_filter(tracks)
    width = max(2, int(width))
    height = max(2, int(height))
    if video_chain:
        video = f"[0:v:0]{video_chain}[vout]"
    else:
        video = (
            f"[0:v:0]scale={width}:{height}:"
            f"force_original_aspect_ratio=decrease:force_divisible_by=2[vout]"
        )
    return f"{audio};{video}"


def build_playback_stream_cmds(
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
        "-stdin",
        "-ss",
        f"{start_seconds:.3f}",
        "-i",
        input_path,
        "-filter_complex",
        filter_complex,
        "-map",
        "[vout]",
        "-map",
        "[aout]",
        "-c:v",
        "rawvideo",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "pcm_s16le",
        "-f",
        "nut",
        "pipe:1",
    ]

    ffplay_cmd = [
        paths.FFPLAY,
        "-autoexit",
        "-loglevel",
        "info",
        "-stats",
        # The NUT header fully describes the streams, so probing needs no
        # decode time, and skipping input buffering shaves ~80 ms off
        # spawn-to-first-frame (measured 374 -> 292 ms median). If playback
        # start ever sounds off, dropping "-fflags nobuffer" is the first
        # thing to try.
        "-fflags",
        "nobuffer",
        "-analyzeduration",
        "0",
        "-x",
        str(max(2, int(width))),
        "-y",
        str(max(2, int(height))),
        "-left",
        "-32000",
        "-top",
        "-32000",
        "-i",
        "pipe:0",
    ]

    return ffmpeg_cmd, ffplay_cmd


def build_frame_extract_cmd(
    input_path: str,
    seconds: float,
    frame_path: str,
    vf: str | None = None,
) -> list[str]:
    cmd = [
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
    ]
    if vf:
        cmd.extend(["-vf", vf])
    cmd.extend(
        [
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
    )
    return cmd


def build_snapshot_cmd(
    input_path: str,
    seconds: float,
    dest_path: str,
    vf: str | None = None,
) -> list[str]:
    """Full-resolution single-frame extract. The output format follows the
    destination extension (PNG for lossless snapshots)."""
    cmd = [
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
    ]
    if vf:
        cmd.extend(["-vf", vf])
    cmd.extend(
        [
            "-frames:v",
            "1",
            "-an",
            "-sn",
            "-dn",
            "-y",
            dest_path,
        ]
    )
    return cmd


class _Pipeline:
    """One spawned ffmpeg->ffplay pair plus its diagnostic tails."""

    def __init__(self, generation: int, ffmpeg: subprocess.Popen, ffplay: subprocess.Popen):
        self.generation = generation
        self.ffmpeg = ffmpeg
        self.ffplay = ffplay
        self.ffplay_tail: deque[str] = deque(maxlen=12)
        self.ffmpeg_tail: deque[str] = deque(maxlen=12)


def _kill_process(process: subprocess.Popen | None):
    if process is None:
        return
    try:
        process.kill()
    except Exception:
        try:
            process.terminate()
        except Exception:
            pass


def _terminate_pipeline(ffmpeg: subprocess.Popen | None, ffplay: subprocess.Popen | None):
    # Kill order does not matter much; killing works on suspended processes.
    _kill_process(ffplay)
    _kill_process(ffmpeg)
    for process in (ffmpeg, ffplay):
        if process is None:
            continue
        try:
            process.wait(timeout=0.5)
        except Exception:
            _kill_process(process)


def _retire_pipeline(pipeline: "_Pipeline | None"):
    """Kill a superseded pipeline NOW (synchronously — kill() does not block),
    leaving only the wait/reap to a background thread. Killing must never be
    deferred to a daemon thread alone: at interpreter shutdown daemon threads
    are abandoned mid-flight, which orphans ffplay/ffmpeg."""
    if pipeline is None:
        return

    _kill_process(pipeline.ffplay)
    _kill_process(pipeline.ffmpeg)

    threading.Thread(
        target=_terminate_pipeline,
        args=(pipeline.ffmpeg, pipeline.ffplay),
        name="playback-reap",
        daemon=True,
    ).start()


class PlaybackEngine:
    """Owns the preview pipeline. Public methods: UI thread only."""

    # This engine extracts JPEG stills for paused scrubbing (no live seek).
    # An alternative engine (mpv) sets this True so the app scrubs with real
    # frames instead. Behavior-neutral for this class.
    supports_live_scrub = False
    supports_fast_stills = False  # stills spawn ffmpeg; throttle scrub requests

    def __init__(self, callbacks: PlaybackCallbacks):
        self._cb = callbacks
        self._lock = threading.RLock()

        self._video_path: str | None = None
        self._duration: float | None = None

        self._state = IDLE
        self._generation = 0
        self._pipeline: _Pipeline | None = None

        self._hwnd: int | None = None
        self._embedded = False
        self._native_paused = False
        self._concealed = False
        self._size = (960, 540)

        self._start_seconds = 0.0
        self._last_clock: float | None = None
        self._last_emit = 0.0
        self._first_frame_seen = False
        self._pause_position: float | None = None
        self._pause_clock: float | None = None
        self._resume_clock: float | None = None

        self._tracks: list[tuple[int, float]] = []
        self._live_mix_ok = True

        # Optional provider of a video filter chain, re-queried on every spawn
        # with the actual (start_seconds, width, height). Must be a pure,
        # thread-tolerant callable (spawns happen off the UI thread).
        self._video_chain_provider: "Callable[[float, int, int], str | None] | None" = None

        self._cmd_lock = threading.Lock()
        self._cmd_pending: dict[int, float] = {}
        self._cmd_event = threading.Event()
        self._closed = False
        threading.Thread(
            target=self._command_writer_loop, name="playback-cmd", daemon=True
        ).start()

        self._still_request_id = 0
        self._still_process: subprocess.Popen | None = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def state(self) -> str:
        return self._state

    @property
    def hwnd(self) -> int | None:
        return self._hwnd

    @property
    def is_active(self) -> bool:
        """True while there is anything to stop (starting, playing or paused)."""
        return self._state != IDLE

    @property
    def has_pipeline(self) -> bool:
        pipeline = self._pipeline
        return pipeline is not None and pipeline.ffplay.poll() is None

    @property
    def concealed(self) -> bool:
        return self._concealed

    @property
    def live_mix_ok(self) -> bool:
        return self._live_mix_ok

    @property
    def position(self) -> float:
        if self._state == PAUSED:
            value = self._pause_position
            if value is None:
                value = self._start_seconds
        elif self._last_clock is not None:
            value = self._start_seconds + self._last_clock
        else:
            value = self._start_seconds

        duration = self._duration or 0
        if duration:
            value = min(value, duration)
        return max(0.0, value)

    # ------------------------------------------------------------------
    # Media / lifecycle
    # ------------------------------------------------------------------

    def configure_media(self, path: str | None, duration: float | None):
        """Set the current file. Call stop() first when switching files."""
        self._video_path = path
        self._duration = duration

    def set_video_chain_provider(
        self, provider: "Callable[[float, int, int], str | None] | None"
    ):
        """Register a callable that returns the preview video filter chain for
        a given (start_seconds, width, height), or None for the default fit.

        Re-queried on every spawn so seeks, resume-respawns and loop restarts
        all pick up the current crop/zoom state at the right time offset. The
        provider runs on the spawning thread (not the UI thread), so it must be
        pure and must not touch tkinter."""
        self._video_chain_provider = provider

    def play(self, start_seconds: float, tracks: list[tuple[int, float]], width: int, height: int):
        """
        Start (or restart) the pipeline at start_seconds.

        tracks is the full superset in track-row order: (stream_index, volume)
        with disabled rows already mapped to volume 0.0.
        """
        if not self._video_path:
            return
        if not tracks:
            raise ValueError("Please select at least one audio track.")

        start_seconds = self._clamp_position(start_seconds)

        with self._lock:
            self._generation += 1
            generation = self._generation
            old_pipeline = self._pipeline
            self._pipeline = None
            self._hwnd = None
            self._embedded = False
            self._native_paused = False
            self._concealed = False
            self._first_frame_seen = False
            self._last_clock = None
            self._pause_position = None
            self._pause_clock = None
            self._resume_clock = None
            self._start_seconds = start_seconds
            self._size = (max(2, int(width)), max(2, int(height)))
            self._tracks = list(tracks)
            self._live_mix_ok = True

        with self._cmd_lock:
            self._cmd_pending.clear()

        _retire_pipeline(old_pipeline)

        video_chain = None
        if self._video_chain_provider is not None:
            try:
                video_chain = self._video_chain_provider(start_seconds, *self._size)
            except Exception:
                video_chain = None
        filter_complex = build_playback_filter(self._tracks, *self._size, video_chain=video_chain)

        self._set_state(STARTING)

        threading.Thread(
            target=self._spawn_worker,
            args=(generation, filter_complex, start_seconds),
            name="playback-spawn",
            daemon=True,
        ).start()

    def pause(self) -> bool:
        """
        Freeze playback via FFplay's own pause toggle (posted spacebar with a
        real scancode). FFplay keeps its window and message pump alive and
        handles all A/V clock bookkeeping across the pause; FFmpeg pauses
        itself moments later on pipe backpressure. No process is suspended —
        a suspended window-owning process freezes Tk as soon as any
        activation/z-order change sends its window a synchronous message.

        Returns True when the frozen frame stays visible in the live window
        (no overlay needed); False when the pipeline had to be dropped and
        the caller should display a still instead.
        """
        if self._state != PLAYING:
            return False

        pipeline = self._pipeline
        self._pause_position = self.position
        self._pause_clock = self._last_clock

        posted = pipeline is not None and win32.post_pause_key_to_window(self._hwnd)

        if not posted:
            self._drop_pipeline()
            self._set_state(PAUSED)
            return False

        self._native_paused = True
        self._set_state(PAUSED)
        # The posted key is fire-and-forget; confirm it took by watching the
        # stats clock, else fall back to a real (kill-based) pause.
        self._start_verify_timer(0.6, self._verify_pause_took)
        return True

    def _verify_pause_took(self, generation: int):
        if (
            generation != self._generation
            or self._state != PAUSED
            or not self._native_paused
        ):
            return

        clock = self._last_clock
        anchor = self._pause_clock
        if clock is not None and anchor is not None and clock - anchor > 0.35:
            # The pause key was ignored and audio kept playing. Make the
            # pause real by dropping the pipeline, and tell the UI to put up
            # a still for the frame we actually stopped at.
            self._pause_position = self._clamp_position(self._start_seconds + clock)
            self._native_paused = False
            self._drop_pipeline()
            self._cb.on_pause_slipped()

    def resume(self):
        """Continue from pause: native FFplay unpause when the pipeline is
        still alive, otherwise a respawn at the paused position."""
        if self._state != PAUSED:
            return

        position = self.position
        pipeline = self._pipeline

        if (
            pipeline is not None
            and self._native_paused
            and pipeline.ffplay.poll() is None
            and win32.post_pause_key_to_window(self._hwnd)
        ):
            self._native_paused = False
            if self._concealed:
                win32.show_native_window(self._hwnd)
                self._concealed = False
            self._pause_position = None
            self._resume_clock = self._last_clock
            self._set_state(PLAYING)
            self._start_verify_timer(0.7, self._verify_resume_took)
            return

        self.play(position, self._tracks, *self._size)

    def _verify_resume_took(self, generation: int):
        if generation != self._generation or self._state != PLAYING:
            return

        clock = self._last_clock
        anchor = self._resume_clock
        if clock is None or (anchor is not None and clock - anchor < 0.2):
            # The resume key was ignored and the clock is still frozen;
            # respawn at the stalled position. play() is safe from this timer
            # thread: it only mutates guarded state and spawns workers.
            self.play(self.position, self._tracks, *self._size)

    def conceal(self) -> bool:
        """
        Swap the live (paused) window for a captured still and hide it — used
        while scrubbing, because extracted preview frames are drawn in a Tk
        overlay that the native child window would otherwise paint over.
        Safe at any time: the window's thread keeps running.
        """
        if not self._embedded or not self._hwnd or self._concealed:
            return False

        still = win32.capture_window_frame(self._hwnd)
        if still is not None:
            data, width, height = still
            self._cb.on_still_frame(STILL_KIND_BGRA, data, width, height, PAUSE_STILL_REQUEST)

        win32.hide_native_window(self._hwnd)
        self._concealed = True
        return still is not None

    def _start_verify_timer(self, delay: float, callback):
        timer = threading.Timer(delay, callback, args=(self._generation,))
        timer.daemon = True
        timer.start()

    def seek_paused(self, seconds: float, exact: bool = True):
        """Move the paused position. The paused pipeline is dropped (it can
        only continue where it stopped); resume() will respawn at the new spot.
        `exact` is part of the engine contract (mpv snaps drag seeks to video
        keyframes); position bookkeeping here is exact either way."""
        if self._state != PAUSED:
            return
        self._drop_pipeline()
        self._pause_position = self._clamp_position(seconds)

    def hold_paused_at(self, seconds: float):
        """Enter PAUSED directly at a position with no pipeline (used when a
        seek lands while nothing is running)."""
        self._drop_pipeline()
        self._pause_position = self._clamp_position(seconds)
        if self._state != PAUSED:
            self._set_state(PAUSED)

    def stop(self):
        """Full teardown to IDLE."""
        with self._lock:
            self._generation += 1
            pipeline = self._pipeline
            self._pipeline = None
            self._hwnd = None
            self._embedded = False
            self._native_paused = False
            self._concealed = False
            self._pause_position = None
            self._pause_clock = None
            self._last_clock = None
            self._first_frame_seen = False

        _kill_process(self._still_process)
        self._still_process = None
        self._still_request_id += 1  # invalidate in-flight stills

        _retire_pipeline(pipeline)

        if self._state != IDLE:
            self._set_state(IDLE)

    def shutdown(self):
        self.stop()
        self._closed = True
        self._cmd_event.set()

    # ------------------------------------------------------------------
    # Live mix
    # ------------------------------------------------------------------

    def set_track_volume(self, row: int, volume: float) -> bool:
        """
        Apply a track volume (0.0 == muted/disabled) to the running pipeline
        via FFmpeg's runtime filter commands. Also updates the cached track
        list so any later respawn keeps the value. Returns False once the
        command channel has failed (callers should fall back to a respawn).
        """
        volume = max(0.0, float(volume))

        if 0 <= row < len(self._tracks):
            stream_index, _ = self._tracks[row]
            self._tracks[row] = (stream_index, volume)

        pipeline = self._pipeline
        if pipeline is None or pipeline.ffmpeg.poll() is not None:
            return True  # nothing running; cached value is all that matters

        with self._cmd_lock:
            self._cmd_pending[row] = volume
        self._cmd_event.set()
        return self._live_mix_ok

    def _command_writer_loop(self):
        while not self._closed:
            self._cmd_event.wait()
            self._cmd_event.clear()
            if self._closed:
                return

            while True:
                with self._cmd_lock:
                    items = list(self._cmd_pending.items())
                    self._cmd_pending.clear()
                if not items:
                    break

                pipeline = self._pipeline
                stdin = pipeline.ffmpeg.stdin if pipeline is not None else None
                if stdin is not None:
                    try:
                        for row, volume in items:
                            stdin.write(
                                f"cParsed_volume_{row} -1 volume {volume:.3f}\n".encode("ascii")
                            )
                        stdin.flush()
                    except Exception:
                        self._live_mix_ok = False

                # Coalesce bursts: FFmpeg consumes roughly one command per
                # transcode loop iteration, so drip at most ~25 batches/sec
                # and let newer values overwrite queued ones meanwhile.
                time.sleep(COMMAND_FLUSH_INTERVAL)

    # ------------------------------------------------------------------
    # Window management (UI thread)
    # ------------------------------------------------------------------

    def embed(self, parent_hwnd: int, width: int, height: int) -> bool:
        """Reparent the found FFplay window into the preview frame (hidden)."""
        if not self._hwnd:
            return False
        ok = win32.embed_external_window_hidden(self._hwnd, parent_hwnd, width, height)
        self._embedded = bool(ok)
        return self._embedded

    def re_anchor(self, width: int | None = None, height: int | None = None):
        """Snap the embedded window back to fill the frame (and show it).
        No-op while concealed — a scrub still is covering for the window."""
        if self._concealed or not self._embedded or not self._hwnd:
            return
        if width is None or height is None:
            width, height = self._size
        win32.anchor_child_window(self._hwnd, width, height, show=True)

    def apply_size(self, width: int, height: int):
        """Preview frame resized."""
        width = max(2, int(width))
        height = max(2, int(height))
        self._size = (width, height)
        if self._embedded and self._hwnd and not self._concealed:
            win32.anchor_child_window(self._hwnd, width, height, show=False)

    # ------------------------------------------------------------------
    # Still frames (pause fallback + scrubbing)
    # ------------------------------------------------------------------

    def save_frame(self, seconds: float, dest_path: str, on_done, vf: str | None = None):
        """Extract the full-resolution frame at `seconds` to dest_path on a
        worker thread. Calls on_done(success: bool, dest_path: str) when done
        (on the worker thread — the caller marshals to its UI thread).

        vf, when set, bakes a crop/zoom transform into the saved frame."""
        video_path = self._video_path
        if not video_path or not paths.FFMPEG:
            on_done(False, dest_path)
            return

        seconds = self._clamp_position(seconds)
        duration = self._duration or 0
        if duration:
            seconds = min(seconds, max(0.0, duration - 0.05))

        def worker():
            ok = False
            try:
                cmd = build_snapshot_cmd(video_path, seconds, dest_path, vf)
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=CREATE_NO_WINDOW,
                )
                win32.assign_process_to_cleanup_job(process)
                try:
                    rc = process.wait(timeout=STILL_EXTRACT_TIMEOUT)
                except subprocess.TimeoutExpired:
                    _kill_process(process)
                    rc = -1
                ok = rc == 0 and Path(dest_path).exists()
            except Exception:
                ok = False
            on_done(ok, dest_path)

        threading.Thread(target=worker, name="playback-snapshot", daemon=True).start()

    def request_still(self, seconds: float, vf: str | None = None) -> int:
        """Extract a single frame asynchronously; emits on_still_frame with the
        returned request id (stale ids should be ignored by the receiver).

        vf, when set, applies a video filter (e.g. a static crop) so the still
        matches what playback would show at that time."""
        self._still_request_id += 1
        request_id = self._still_request_id

        video_path = self._video_path
        if not video_path or not paths.FFMPEG:
            return request_id

        seconds = self._clamp_position(seconds)
        duration = self._duration or 0
        if duration:
            seconds = min(seconds, max(0.0, duration - 0.05))

        threading.Thread(
            target=self._still_worker,
            args=(request_id, video_path, seconds, vf),
            name="playback-still",
            daemon=True,
        ).start()
        return request_id

    def _still_worker(self, request_id: int, video_path: str, seconds: float, vf: str | None = None):
        _kill_process(self._still_process)

        frame_path = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg").name
        image_bytes = b""
        try:
            cmd = build_frame_extract_cmd(video_path, seconds, frame_path, vf)
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW,
            )
            win32.assign_process_to_cleanup_job(process)
            self._still_process = process

            try:
                return_code = process.wait(timeout=STILL_EXTRACT_TIMEOUT)
            except subprocess.TimeoutExpired:
                _kill_process(process)
                return_code = -1

            if return_code == 0 and Path(frame_path).exists():
                try:
                    image_bytes = Path(frame_path).read_bytes()
                except Exception:
                    image_bytes = b""
        except Exception:
            image_bytes = b""
        finally:
            self._still_process = None
            try:
                Path(frame_path).unlink(missing_ok=True)
            except Exception:
                pass

        if request_id != self._still_request_id:
            return
        if image_bytes:
            self._cb.on_still_frame(STILL_KIND_JPEG, image_bytes, 0, 0, request_id)
        else:
            self._cb.on_still_failed(request_id)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _set_state(self, state: str):
        if self._state == state:
            return
        self._state = state
        self._cb.on_state(state)

    def _clamp_position(self, seconds: float) -> float:
        try:
            seconds = float(seconds)
        except Exception:
            seconds = 0.0
        duration = self._duration or 0
        if duration:
            seconds = min(seconds, duration)
        return max(0.0, seconds)

    def _drop_pipeline(self):
        """Kill the current processes without changing engine state."""
        with self._lock:
            self._generation += 1
            pipeline = self._pipeline
            self._pipeline = None
            self._hwnd = None
            self._embedded = False
            self._native_paused = False
            self._concealed = False

        _retire_pipeline(pipeline)

    def _spawn_worker(self, generation: int, filter_complex: str, start_seconds: float):
        if generation != self._generation:
            return

        width, height = self._size
        ffmpeg_cmd, ffplay_cmd = build_playback_stream_cmds(
            self._video_path, filter_complex, start_seconds, width, height
        )

        try:
            ffmpeg = subprocess.Popen(
                ffmpeg_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=CREATE_NO_WINDOW,
            )
        except Exception as exc:
            if generation == self._generation:
                self._set_state(IDLE)
                self._cb.on_error("Preview Error", f"Preview failed to start:\n\n{exc}")
            return

        try:
            ffplay = subprocess.Popen(
                ffplay_cmd,
                stdin=ffmpeg.stdout,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                creationflags=CREATE_NO_WINDOW,
                env=ffplay_start_env(),
            )
        except Exception as exc:
            _kill_process(ffmpeg)
            if generation == self._generation:
                self._set_state(IDLE)
                self._cb.on_error("Preview Error", f"Preview failed to start:\n\n{exc}")
            return

        # Let ffplay own the pipe endpoint so ffmpeg sees broken-pipe cleanly.
        if ffmpeg.stdout:
            try:
                ffmpeg.stdout.close()
            except Exception:
                pass

        # If the app itself dies ungracefully, the OS reaps these with it.
        win32.assign_process_to_cleanup_job(ffmpeg)
        win32.assign_process_to_cleanup_job(ffplay)

        pipeline = _Pipeline(generation, ffmpeg, ffplay)

        with self._lock:
            if generation != self._generation:
                _terminate_pipeline(ffmpeg, ffplay)
                return
            self._pipeline = pipeline

        for target, name in (
            (self._stats_reader, "playback-stats"),
            (self._ffmpeg_stderr_reader, "playback-ffmpeg-log"),
            (self._window_poll, "playback-window"),
            (self._monitor, "playback-monitor"),
        ):
            threading.Thread(target=target, args=(pipeline,), name=name, daemon=True).start()

    def _window_poll(self, pipeline: _Pipeline):
        deadline = time.monotonic() + WINDOW_POLL_TIMEOUT

        while time.monotonic() < deadline:
            if pipeline.generation != self._generation:
                return
            if pipeline.ffplay.poll() is not None:
                return

            hwnd = win32.find_main_window_for_pid(pipeline.ffplay.pid)
            if hwnd:
                with self._lock:
                    if pipeline.generation != self._generation:
                        return
                    self._hwnd = hwnd
                self._cb.on_window_ready(hwnd)
                return

            time.sleep(WINDOW_POLL_INTERVAL)

        if pipeline.generation == self._generation:
            self._cb.on_embed_timeout()

    def _stats_reader(self, pipeline: _Pipeline):
        stream = pipeline.ffplay.stderr
        if stream is None:
            return
        fd = stream.fileno()
        buffer = b""

        while True:
            try:
                chunk = os.read(fd, 4096)
            except OSError:
                break
            if not chunk:
                break

            buffer += chunk
            *lines, buffer = re.split(rb"[\r\n]", buffer)

            for line in lines:
                if not line.strip():
                    continue

                match = _STATS_CLOCK_RE.match(line)
                if match is None:
                    try:
                        pipeline.ffplay_tail.append(line.decode("utf-8", "replace").strip())
                    except Exception:
                        pass
                    continue

                if pipeline.generation != self._generation:
                    continue

                self._on_clock(float(match.group(1)))

    def _on_clock(self, clock: float):
        now = time.monotonic()

        if not self._first_frame_seen:
            self._first_frame_seen = True
            self._cb.on_first_frame()
            if self._state == STARTING:
                self._set_state(PLAYING)

        self._last_clock = clock

        if self._state == PLAYING and now - self._last_emit >= POSITION_EMIT_INTERVAL:
            self._last_emit = now
            self._cb.on_position(self.position)

    def _ffmpeg_stderr_reader(self, pipeline: _Pipeline):
        stream = pipeline.ffmpeg.stderr
        if stream is None:
            return
        fd = stream.fileno()
        buffer = b""

        while True:
            try:
                chunk = os.read(fd, 4096)
            except OSError:
                break
            if not chunk:
                break

            buffer += chunk
            *lines, buffer = re.split(rb"[\r\n]", buffer)
            for line in lines:
                text = line.decode("utf-8", "replace").strip()
                if not text:
                    continue
                pipeline.ffmpeg_tail.append(text)
                # Live-command replies land here; a non-zero ret means the
                # command interface is not working (fall back to respawns).
                if text.startswith("Command reply") and "ret:0" not in text:
                    self._live_mix_ok = False

    def _monitor(self, pipeline: _Pipeline):
        pipeline.ffplay.wait()

        _kill_process(pipeline.ffmpeg)
        try:
            pipeline.ffmpeg.wait(timeout=1.0)
        except Exception:
            pass

        if pipeline.generation != self._generation:
            return  # superseded by a newer pipeline or an explicit stop

        ended_at = self.position

        with self._lock:
            if pipeline.generation != self._generation:
                return
            self._pipeline = None
            self._hwnd = None
            self._embedded = False
            self._native_paused = False
            self._concealed = False

        if self._first_frame_seen or pipeline.ffplay.returncode == 0:
            # Normal end of stream — including the near-instant EOF of a
            # pipeline started at the very end of the clip.
            self._set_state(IDLE)
            self._cb.on_ended(ended_at)
            return

        # Died before showing anything: surface the stderr tails.
        detail_lines = list(pipeline.ffmpeg_tail) + list(pipeline.ffplay_tail)
        detail = "\n".join(detail_lines[-8:]) or "The preview processes exited unexpectedly."
        self._set_state(IDLE)
        self._cb.on_error("Preview Error", f"Preview failed:\n\n{detail}")
