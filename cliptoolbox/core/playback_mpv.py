"""Optional mpv-based playback engine (embedded via --wid, driven over JSON IPC).

An ADDITION to the ffplay PlaybackEngine, not a replacement: it duck-types the
same public surface and callback contract, so app.py and CropController drive
it unchanged. Selected in Settings; when mpv.exe is absent the factory falls
back to ffplay. Delete this module + mpv_ipc.py + the factory branch to rip it
out (see docs/BUILD_NOTES.md).

Why mpv: instant exact seeks with no pipeline respawn, reliable property-based
pause, and native frame painting while scrubbing (supports_live_scrub = True) —
much better for the constant pause/seek of crop keyframing.

Key facts validated by tools/spike_mpv.py:
  - mpv's lavfi-complex clock is absolute source PTS, so crop expressions are
    built with time_offset=0 (the provider is always queried with start=0.0).
  - stop keeps the process alive (--idle) for instant warm restarts.
  - the IPC pipe needs overlapped I/O (handled in mpv_ipc.py).

tkinter-free. The wid is resolved through a provider callable so this module
never imports tkinter; the app passes one that returns its render-host HWND.
"""
import os
import subprocess
import threading
import time
from collections import deque

from cliptoolbox.constants import CREATE_NO_WINDOW
from cliptoolbox.core import paths, win32
from cliptoolbox.core.mpv_ipc import MpvIpcClient, MpvIpcError
from cliptoolbox.core.playback import (
    IDLE,
    PAUSE_STILL_REQUEST,
    PAUSED,
    PLAYING,
    POSITION_EMIT_INTERVAL,
    STARTING,
    STILL_EXTRACT_TIMEOUT,
    STILL_KIND_BGRA,
    STILL_KIND_JPEG,
    WINDOW_POLL_INTERVAL,
    WINDOW_POLL_TIMEOUT,
    build_frame_extract_cmd,
    build_snapshot_cmd,
)

_GRAPH_COALESCE = 0.04  # seconds; batches live-volume graph rebuilds


# ---------------------------------------------------------------------------
# Pure builders (golden-checked in tools/dump_commands.py)
# ---------------------------------------------------------------------------
def build_mpv_lavfi(tracks: list[tuple[int, float]], video_chain: str | None) -> str:
    """mpv lavfi-complex graph: per-track volume + amix to [ao], video to [vo].

    The audio pads are mpv's 1-based, audio-relative labels ([aid1], [aid2]),
    which map to the track ROW order (== the file's audio-stream order) — NOT
    the stored global ffprobe stream index that core.filters uses. Video is
    always routed ([vid1]…[vo]) so mpv keeps displaying it; without a crop
    chain it passes through untouched.
    """
    n = len(tracks)
    segs = []
    if n == 1:
        segs.append(f"[aid1]volume={tracks[0][1]:.3f}[ao]")
    elif n > 1:
        for i, (_, vol) in enumerate(tracks):
            segs.append(f"[aid{i + 1}]volume={vol:.3f}[a{i}]")
        mix_in = "".join(f"[a{i}]" for i in range(n))
        segs.append(f"{mix_in}amix=inputs={n}:duration=longest:normalize=0[ao]")
    segs.append(f"[vid1]{video_chain}[vo]" if video_chain else "[vid1]null[vo]")
    return ";".join(segs)


def cache_split_mb(cache_mb: int) -> tuple[int, int]:
    """Split the user's single cache budget into mpv's forward/back demuxer
    buffers (2/3 ahead of the playhead, 1/3 behind for instant back-seeks)."""
    total = max(16, int(cache_mb))
    forward = max(8, total * 2 // 3)
    return forward, max(8, total - forward)


def build_mpv_cmd(mpv_path: str, wid: int, ipc_pipe: str,
                  cache_mb: int = 100) -> list[str]:
    forward_mb, back_mb = cache_split_mb(cache_mb)
    return [
        mpv_path,
        f"--wid={wid}",
        f"--input-ipc-server={ipc_pipe}",
        "--no-config",            # deterministic: ignore user mpv.conf/scripts
        "--idle=yes",             # survive `stop` for warm restarts
        "--force-window=yes",     # window exists from startup → stable child hwnd
        "--keep-open=yes",        # pause at EOF; eof-reached drives on_ended
        "--pause",                # spawn paused; play() unpauses
        "--hr-seek=yes",
        "--hr-seek-framedrop=yes",
        "--cache=yes",            # RAM demuxer cache even for local files
        "--demuxer-seekable-cache=yes",  # seeks inside cached ranges skip the disk
        f"--demuxer-max-bytes={forward_mb}MiB",
        f"--demuxer-max-back-bytes={back_mb}MiB",
        "--demuxer-readahead-secs=600",  # keep demuxing ahead up to the byte cap
        "--hwdec=no",             # parity with the ffmpeg pipeline; lavfi-safe
        "--no-osc",
        "--no-osd-bar",
        "--osd-level=0",
        "--no-input-default-bindings",
        "--input-vo-keyboard=no",
        "--no-input-cursor",
        "--cursor-autohide=no",
        "--no-border",
        "--no-taskbar-progress",
        "--msg-level=all=error",
    ]


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
class MpvPlaybackEngine:
    supports_live_scrub = True

    def __init__(self, callbacks, wid_provider, mpv_path: str, cache_mb: int = 100):
        self._cb = callbacks
        self._wid_provider = wid_provider
        self._mpv_path = mpv_path
        self._cache_mb = max(16, int(cache_mb))
        self._cache_ranges: list[tuple[float, float]] = []

        self._video_path: str | None = None
        self._duration: float | None = None

        self._state = IDLE
        self._generation = 0
        self._process: subprocess.Popen | None = None
        self._ipc: MpvIpcClient | None = None
        self._child_hwnd: int | None = None
        self._concealed = False
        self._loaded = False
        self._closing = False

        self._size = (960, 540)
        self._tracks: list[tuple[int, float]] = []
        self._video_chain_provider = None
        self._current_chain: str | None = None
        self._last_graph: str | None = None

        self._position = 0.0
        self._pause_position: float | None = None
        self._last_emit = 0.0
        self._stderr_tail: deque[str] = deque(maxlen=12)

        self._still_request_id = 0
        self._still_process: subprocess.Popen | None = None

        self._graph_lock = threading.Lock()
        self._graph_pending: str | None = None
        self._graph_event = threading.Event()
        threading.Thread(target=self._graph_writer_loop, name="mpv-graph", daemon=True).start()

    # ------------------------------------------------------------------
    # Properties (mirror PlaybackEngine)
    # ------------------------------------------------------------------
    @property
    def state(self) -> str:
        return self._state

    @property
    def hwnd(self) -> int | None:
        return self._child_hwnd

    @property
    def is_active(self) -> bool:
        return self._state != IDLE

    @property
    def has_pipeline(self) -> bool:
        return (self._process is not None and self._process.poll() is None
                and self._loaded)

    @property
    def concealed(self) -> bool:
        return self._concealed

    @property
    def live_mix_ok(self) -> bool:
        return bool(self._ipc and self._ipc.alive)

    @property
    def position(self) -> float:
        if self._state == PAUSED and self._pause_position is not None:
            value = self._pause_position
        else:
            value = self._position
        duration = self._duration or 0
        if duration:
            value = min(value, duration)
        return max(0.0, value)

    # ------------------------------------------------------------------
    # Media / lifecycle
    # ------------------------------------------------------------------
    def configure_media(self, path: str | None, duration: float | None):
        if path != self._video_path:
            self._loaded = False
        self._video_path = path
        self._duration = duration

    def set_video_chain_provider(self, provider):
        self._video_chain_provider = provider

    def _clamp(self, seconds: float) -> float:
        try:
            seconds = float(seconds)
        except Exception:
            seconds = 0.0
        duration = self._duration or 0
        if duration:
            seconds = min(seconds, duration)
        return max(0.0, seconds)

    def play(self, start_seconds: float, tracks, width: int, height: int):
        if not self._video_path:
            return
        if not tracks:
            raise ValueError("Please select at least one audio track.")

        start_seconds = self._clamp(start_seconds)
        self._generation += 1
        gen = self._generation
        self._size = (max(2, int(width)), max(2, int(height)))
        self._tracks = list(tracks)
        self._pause_position = None
        self._last_emit = 0.0
        self._set_state(STARTING)

        if self._process is not None and self._process.poll() is None and self.live_mix_ok:
            # Warm: no respawn — seek + unpause (the cheap crop-commit/loop path).
            self._reveal()
            self._apply_graph()
            if self._loaded:
                self._ipc.command_async("seek", f"{start_seconds:.3f}", "absolute+exact")
                self._ipc.set_property("pause", False)
                self._position = start_seconds
            else:
                self._cold_load(start_seconds)
            return

        wid = self._wid_provider() if self._wid_provider else None
        if not wid:
            self._set_state(IDLE)
            self._cb.on_error("Preview Error", "No render surface is available for mpv.")
            return
        threading.Thread(target=self._spawn_worker, args=(gen, start_seconds, int(wid)),
                         name="mpv-spawn", daemon=True).start()

    def _spawn_worker(self, gen: int, start_seconds: float, wid: int):
        if gen != self._generation:
            return
        pipe = rf"\\.\pipe\cliptoolbox-mpv-{os.getpid()}-{gen}"
        try:
            proc = subprocess.Popen(
                build_mpv_cmd(self._mpv_path, wid, pipe, self._cache_mb),
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                creationflags=CREATE_NO_WINDOW,
            )
        except Exception as exc:
            if gen == self._generation:
                self._set_state(IDLE)
                self._cb.on_error("Preview Error", f"mpv failed to start:\n\n{exc}")
            return
        win32.assign_process_to_cleanup_job(proc)
        self._process = proc
        threading.Thread(target=self._stderr_reader, args=(proc,), name="mpv-stderr",
                         daemon=True).start()

        ipc = MpvIpcClient(pipe, on_event=self._on_ipc_event,
                           on_disconnect=self._on_ipc_disconnect)
        if not ipc.connect(timeout=5.0) or gen != self._generation:
            ipc.close()
            if gen == self._generation:
                self._set_state(IDLE)
                self._cb.on_error("Preview Error", "mpv IPC pipe did not connect.")
            self._kill_process(proc)
            return
        self._ipc = ipc
        ipc.observe_property(1, "time-pos")
        ipc.observe_property(2, "eof-reached")
        ipc.observe_property(3, "demuxer-cache-state")

        self._apply_graph()
        self._cold_load(start_seconds)

        threading.Thread(target=self._window_poll, args=(gen, wid), name="mpv-winpoll",
                         daemon=True).start()

    def _cold_load(self, start_seconds: float):
        if not (self._ipc and self._ipc.alive):
            return
        self._emit_cache_ranges([])  # fresh file: drop the stale cache bar now
        self._ipc.set_property("start", f"{start_seconds:.3f}")
        self._ipc.command_async("loadfile", self._video_path, "replace")
        self._ipc.set_property("pause", False)
        self._loaded = True
        self._position = start_seconds

    def _window_poll(self, gen: int, wid: int):
        deadline = time.monotonic() + WINDOW_POLL_TIMEOUT
        while gen == self._generation and time.monotonic() < deadline:
            hwnd = win32.find_child_window_for_pid(wid, self._process.pid)
            if hwnd:
                self._child_hwnd = hwnd
                self._cb.on_window_ready(hwnd)
                return
            time.sleep(WINDOW_POLL_INTERVAL)
        if gen == self._generation:
            self._cb.on_embed_timeout()

    def _stderr_reader(self, proc: subprocess.Popen):
        try:
            for raw in iter(proc.stderr.readline, b""):
                line = raw.decode("utf-8", "replace").rstrip()
                if line:
                    self._stderr_tail.append(line)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Transport
    # ------------------------------------------------------------------
    def pause(self) -> bool:
        if self._state != PLAYING:
            return False
        self._pause_position = self.position
        if self._ipc and self._ipc.alive:
            try:
                self._ipc.set_property("pause", True)
                self._set_state(PAUSED)
                return True  # mpv keeps the frame on screen; no watchdog needed
            except MpvIpcError:
                pass
        self._kill_process(self._process)
        self._set_state(PAUSED)
        return False

    def resume(self):
        if self._state != PAUSED:
            return
        if (self._process is not None and self._process.poll() is None
                and self.live_mix_ok and self._loaded):
            self._reveal()
            self._ipc.set_property("pause", False)
            self._pause_position = None
            self._set_state(PLAYING)
            return
        self.play(self.position, self._tracks, *self._size)

    def seek_paused(self, seconds: float):
        if self._state != PAUSED:
            return
        self._pause_position = self._clamp(seconds)
        self._position = self._pause_position
        if self._loaded and self._ipc and self._ipc.alive:
            self._apply_graph()  # a crop edit may have changed the graph while paused
            self._ipc.command_async("seek", f"{self._pause_position:.3f}", "absolute+exact")

    def hold_paused_at(self, seconds: float):
        self._pause_position = self._clamp(seconds)
        self._position = self._pause_position
        if self._loaded and self._ipc and self._ipc.alive:
            self._ipc.command_async("seek", f"{self._pause_position:.3f}", "absolute+exact")
            self._ipc.set_property("pause", True)
        if self._state != PAUSED:
            self._set_state(PAUSED)

    def conceal(self) -> bool:
        if not self._child_hwnd or self._concealed:
            return False
        still = win32.capture_window_frame(self._child_hwnd)
        if still is not None:
            data, width, height = still
            self._cb.on_still_frame(STILL_KIND_BGRA, data, width, height, PAUSE_STILL_REQUEST)
        win32.hide_native_window(self._child_hwnd)
        self._concealed = True
        return still is not None

    def _reveal(self):
        if self._concealed and self._child_hwnd:
            win32.show_native_window(self._child_hwnd)
            self._concealed = False

    def stop(self):
        self._generation += 1
        if self._ipc and self._ipc.alive:
            try:
                self._ipc.command_async("stop")
            except MpvIpcError:
                pass
        self._loaded = False
        self._emit_cache_ranges([])
        self._reveal()
        self._kill_process(self._still_process)
        self._still_process = None
        self._still_request_id += 1
        self._set_state(IDLE)

    def shutdown(self):
        self._closing = True
        self._generation += 1
        if self._ipc:
            try:
                self._ipc.command_async("quit")
            except MpvIpcError:
                pass
        proc = self._process
        if proc is not None:
            try:
                proc.wait(timeout=0.5)
            except Exception:
                self._kill_process(proc)
        if self._ipc:
            self._ipc.close()
        self._graph_event.set()

    # ------------------------------------------------------------------
    # Audio graph
    # ------------------------------------------------------------------
    def set_track_volume(self, row: int, volume: float) -> bool:
        if 0 <= row < len(self._tracks):
            idx, _ = self._tracks[row]
            self._tracks[row] = (idx, volume)
        if not (self._loaded and self._ipc and self._ipc.alive):
            return True
        with self._graph_lock:
            self._graph_pending = build_mpv_lavfi(self._tracks, self._current_chain)
        self._graph_event.set()
        return self.live_mix_ok

    def _apply_graph(self):
        chain = None
        if self._video_chain_provider:
            try:
                # start=0.0: mpv's lavfi t is absolute source PTS (spike-verified).
                chain = self._video_chain_provider(0.0, *self._size)
            except Exception:
                chain = None
        self._current_chain = chain
        graph = build_mpv_lavfi(self._tracks, chain)
        if graph != self._last_graph and self._ipc and self._ipc.alive:
            try:
                self._ipc.set_property("lavfi-complex", graph)
                self._last_graph = graph
            except MpvIpcError:
                pass

    def _graph_writer_loop(self):
        while not self._closing:
            self._graph_event.wait()
            self._graph_event.clear()
            if self._closing:
                return
            time.sleep(_GRAPH_COALESCE)  # batch a burst of volume changes
            with self._graph_lock:
                graph = self._graph_pending
                self._graph_pending = None
            if graph and graph != self._last_graph and self._ipc and self._ipc.alive:
                try:
                    self._ipc.set_property("lavfi-complex", graph)
                    self._last_graph = graph
                except MpvIpcError:
                    pass

    # ------------------------------------------------------------------
    # Embedding (mpv is already parented via --wid; these keep it sized)
    # ------------------------------------------------------------------
    def embed(self, parent_hwnd: int, width: int, height: int) -> bool:
        self._size = (max(2, int(width)), max(2, int(height)))
        return self._child_hwnd is not None

    def re_anchor(self, width: int, height: int):
        self._size = (max(2, int(width)), max(2, int(height)))
        if self._child_hwnd and not self._concealed:
            win32.anchor_child_window(self._child_hwnd, width, height, show=True)

    def apply_size(self, width: int, height: int):
        self._size = (max(2, int(width)), max(2, int(height)))
        if self._child_hwnd:
            win32.anchor_child_window(self._child_hwnd, width, height, show=False)

    # ------------------------------------------------------------------
    # Stills / snapshots (own ffmpeg workers — pipeline-independent, reused
    # builders keep core/playback.py untouched)
    # ------------------------------------------------------------------
    def request_still(self, seconds: float, vf: str | None = None) -> int:
        self._still_request_id += 1
        request_id = self._still_request_id
        video_path = self._video_path
        if not video_path or not paths.FFMPEG:
            return request_id
        seconds = self._clamp(seconds)
        duration = self._duration or 0
        if duration:
            seconds = min(seconds, max(0.0, duration - 0.05))
        threading.Thread(target=self._still_worker, args=(request_id, video_path, seconds, vf),
                         name="mpv-still", daemon=True).start()
        return request_id

    def _still_worker(self, request_id, video_path, seconds, vf):
        import tempfile
        from pathlib import Path

        self._kill_process(self._still_process)
        frame_path = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg").name
        image_bytes = b""
        try:
            proc = subprocess.Popen(
                build_frame_extract_cmd(video_path, seconds, frame_path, vf),
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW,
            )
            win32.assign_process_to_cleanup_job(proc)
            self._still_process = proc
            try:
                rc = proc.wait(timeout=STILL_EXTRACT_TIMEOUT)
            except subprocess.TimeoutExpired:
                self._kill_process(proc)
                rc = -1
            if rc == 0 and Path(frame_path).exists():
                image_bytes = Path(frame_path).read_bytes()
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

    def save_frame(self, seconds: float, dest_path: str, on_done, vf: str | None = None):
        video_path = self._video_path
        if not video_path or not paths.FFMPEG:
            on_done(False, dest_path)
            return
        seconds = self._clamp(seconds)
        duration = self._duration or 0
        if duration:
            seconds = min(seconds, max(0.0, duration - 0.05))

        def worker():
            from pathlib import Path
            ok = False
            try:
                proc = subprocess.Popen(
                    build_snapshot_cmd(video_path, seconds, dest_path, vf),
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    creationflags=CREATE_NO_WINDOW,
                )
                win32.assign_process_to_cleanup_job(proc)
                try:
                    rc = proc.wait(timeout=STILL_EXTRACT_TIMEOUT)
                except subprocess.TimeoutExpired:
                    self._kill_process(proc)
                    rc = -1
                ok = rc == 0 and Path(dest_path).exists()
            except Exception:
                ok = False
            on_done(ok, dest_path)

        threading.Thread(target=worker, name="mpv-snapshot", daemon=True).start()

    # ------------------------------------------------------------------
    # Event handling (reader thread)
    # ------------------------------------------------------------------
    def _on_ipc_event(self, msg: dict):
        event = msg.get("event")
        if event == "property-change":
            name = msg.get("name")
            data = msg.get("data")
            if name == "time-pos":
                if data is not None:
                    self._position = float(data)
                    if self._state == PLAYING:
                        now = time.monotonic()
                        if now - self._last_emit >= POSITION_EMIT_INTERVAL:
                            self._last_emit = now
                            self._cb.on_position(self.position)
            elif name == "eof-reached" and data:
                self._on_eof()
            elif name == "demuxer-cache-state":
                self._on_cache_state(data)
        elif event == "playback-restart":
            # First frame after a load/seek: promote STARTING → PLAYING once.
            if self._state == STARTING:
                self._cb.on_first_frame()
                self._set_state(PLAYING)

    def _on_cache_state(self, data):
        """Observed demuxer-cache-state → seekbar cache bar. mpv rate-limits
        these events itself; we just dedupe on the rounded ranges."""
        ranges = []
        if isinstance(data, dict):
            for item in data.get("seekable-ranges") or []:
                try:
                    start = round(float(item["start"]), 1)
                    end = round(float(item["end"]), 1)
                except (KeyError, TypeError, ValueError):
                    continue
                if end > start:
                    ranges.append((start, end))
        ranges.sort()
        self._emit_cache_ranges(ranges)

    def _emit_cache_ranges(self, ranges: list[tuple[float, float]]):
        if ranges == self._cache_ranges:
            return
        self._cache_ranges = ranges
        self._cb.on_cache_ranges(list(ranges))

    def set_cache_size_mb(self, cache_mb: int):
        """Resize the demuxer cache; applies live when mpv is running and to
        the next spawn otherwise."""
        self._cache_mb = max(16, int(cache_mb))
        forward_mb, back_mb = cache_split_mb(self._cache_mb)
        if self._ipc and self._ipc.alive:
            try:
                self._ipc.set_property("demuxer-max-bytes", forward_mb * 1024 * 1024)
                self._ipc.set_property("demuxer-max-back-bytes", back_mb * 1024 * 1024)
            except MpvIpcError:
                pass

    def _on_eof(self):
        if self._state == IDLE:
            return
        at = self._duration or self._position
        self._pause_position = at
        self._set_state(IDLE)
        self._cb.on_ended(at)

    def _on_ipc_disconnect(self):
        if self._closing:
            return
        proc = self._process
        if proc is not None and proc.poll() is not None and self._state != IDLE:
            tail = "\n".join(self._stderr_tail)
            self._set_state(IDLE)
            self._cb.on_error(
                "Preview Error",
                "mpv stopped unexpectedly.\n\n"
                + (tail or "No mpv error output.")
                + "\n\nYou can switch back to the FFplay engine in Settings (Ctrl+,).",
            )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _set_state(self, state: str):
        if self._state == state:
            return
        self._state = state
        self._cb.on_state(state)

    @staticmethod
    def _kill_process(proc):
        if proc is None:
            return
        try:
            proc.kill()
        except Exception:
            pass
