"""ClipToolbox application controller.

Owns all runtime state and the preview/export state machine. The state
machine is ported from the original AudioTrackMergerApp with its logic
intact — the Halo widgets deliberately keep the tk/ttk .config()/get/set
surface the old code drives. Core media logic lives in cliptoolbox.core and
is not defined here.
"""
import hashlib
import os
import queue
import re
import subprocess
import sys
import tempfile
import threading
import time
from io import BytesIO
from pathlib import Path

import tkinter as tk
from tkinter import filedialog
from tkinter import messagebox as tk_messagebox  # bootstrap errors only

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except Exception:
    Image = None
    ImageTk = None
    PIL_AVAILABLE = False

from cliptoolbox.constants import (
    APP_NAME,
    APP_VERSION,
    CREATE_NO_WINDOW,
    DEFAULT_COMPRESSION_RESOLUTION,
    DEFAULT_COMPRESSION_TARGET_MB,
    IS_WINDOWS,
    PREVIEW_HEIGHT,
    PREVIEW_WIDTH,
    format_seconds as core_format_seconds,
    format_windows_discord_size,
)
from cliptoolbox.core import commands as core_commands
from cliptoolbox.core import export as core_export
from cliptoolbox.core import filters as core_filters
from cliptoolbox.core import engine_factory
from cliptoolbox.core import mediainfo as core_mediainfo
from cliptoolbox.core import playback as core_playback
from cliptoolbox.core import probe as core_probe
from cliptoolbox.core.paths import (
    FFMPEG,
    FFMPEG_BIN_DIR,
    FFPLAY,
    FFPROBE,
    OUTPUTS_DIR,
    exe_name,
    reveal_file as core_reveal_file,
)
from cliptoolbox.core.win32 import (
    assign_process_to_cleanup_job,
    flash_taskbar,
    is_foreground_process,
    set_clipboard_dib,
)
from cliptoolbox.dnd import DND_AVAILABLE, DND_FILES, TkinterDnD
from cliptoolbox import settings as app_settings
from cliptoolbox import sessions as video_sessions
from cliptoolbox.ui import chrome, dialogs, dpi, fonts, theme
from cliptoolbox.ui.crop_controller import CropController
from cliptoolbox.ui.wheel import WheelRouter
from cliptoolbox.ui import dialogs as messagebox  # ported call sites unchanged
from cliptoolbox.ui.theme import px
from cliptoolbox.ui.views import landing, shell, workspace
from cliptoolbox.ui.views.settings import SettingsOverlay


def get_app_icon_path() -> str | None:
    """Return the app icon path for development and bundled builds."""
    candidates = []

    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        candidates.append(Path(sys._MEIPASS) / "assets" / "ClipToolbox.ico")

    candidates.extend(
        [
            Path(__file__).resolve().parent.parent / "assets" / "ClipToolbox.ico",
            Path(__file__).resolve().parent / "assets" / "ClipToolbox.ico",
        ]
    )

    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    return None


class HaloApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.settings = app_settings.load()

        # Background threads (playback callbacks, workers) must never touch
        # Tk directly — Tcl is not thread-safe, and calling it from a
        # non-main thread while the main thread is inside a Win32 nested
        # modal loop (window drag/resize) corrupts the interpreter and
        # crashes with a fatal GIL error. All cross-thread UI work is
        # queued here and drained only by the main thread's own after()
        # loop, so Tk is exclusively driven by the thread that owns it.
        self._ui_queue: queue.Queue = queue.Queue()
        self.root.after(15, self._pump_ui_queue)

        self.video_path: str | None = None
        # Saved per-video setup for the clip being loaded; applied in
        # after_probe (and read by add_track_row) once probing finishes.
        self._session_to_restore: dict | None = None
        self.audio_metadata: list[dict] = []
        self.track_controls: list[tuple[int, tk.BooleanVar, object]] = []

        self.total_duration_seconds: float | None = None

        self.trim_enabled_var = tk.BooleanVar(value=False)
        self.trim_start_seconds: float | None = None
        self.trim_end_seconds: float | None = None

        self.video_fps: float | None = None
        self.video_dimensions: tuple[int, int] | None = None
        self.loop_enabled_var = tk.BooleanVar(value=False)
        self.show_remaining = False

        self.preview_muted = False
        self.solo_row: int | None = None
        self.track_state_strips: dict[int, tk.Frame] = {}

        self.crop_enabled_var = tk.BooleanVar(value=False)
        self.crop = None  # CropController, constructed after build_ui

        self.compress_enabled_var = tk.BooleanVar(value=bool(self.settings.compress_enabled))
        self.compression_target_var = tk.StringVar(
            value=self.settings.compression_target_mb or f"{DEFAULT_COMPRESSION_TARGET_MB:g}")
        self.compression_resolution_var = tk.StringVar(
            value=self.settings.compression_resolution or DEFAULT_COMPRESSION_RESOLUTION)
        self.volume_log_after_ids: dict[int, str] = {}

        self.export_thread: threading.Thread | None = None
        self.export_process: subprocess.Popen | None = None

        # All preview process/state management lives in the playback engine;
        # the app only keeps UI-side bookkeeping here. The engine is chosen by
        # settings (ffplay default; mpv optional), falling back to ffplay when
        # mpv.exe is missing.
        self.playback, self.playback_engine_name = engine_factory.create_engine(
            self.settings.playback_engine, self.make_playback_callbacks(),
            wid_provider=self._mpv_wid, mpv_cache_mb=self.settings.mpv_cache_mb,
        )

        self.paused_frame_image = None
        self.paused_frame_label: tk.Label | None = None
        self.scrub_frame_after_id = None
        self.last_scrub_frame_seconds: float | None = None
        self.pending_still_request = 0
        self.scrub_resume_pending = False
        self.anchor_after_ids: list[str] = []
        self.live_mix_fallback_after_id: str | None = None
        self.wheel_seek_after_id: str | None = None
        self.wheel_seek_resume = False

        self.user_is_seeking = False
        self.is_exporting = False
        self.auto_preview_after_load = bool(self.settings.auto_preview_after_load)
        self.preview_width = px(PREVIEW_WIDTH)
        self.preview_height = px(PREVIEW_HEIGHT)

        self.recent_clips: list[str] = list(self.settings.recent_clips)
        self.last_open_dir: str | None = self.settings.last_open_dir
        self.thumbnail_cache: dict = {}  # cache-path -> ImageTk.PhotoImage (ref holder)
        self.active_screen = "landing"

        self.build_ui()
        self.crop = CropController(self)
        self.enable_drag_and_drop()
        self.startup_checks()

    # ========================================================
    # UI construction (delegated to view modules)
    # ========================================================

    def build_ui(self):
        self.root.title(f"{APP_NAME} - {APP_VERSION}" if APP_VERSION else APP_NAME)
        self.root.configure(bg=theme.BG_DEEP)
        self.root.geometry(f"{px(1150)}x{px(780)}")
        self.root.minsize(px(980), px(700))

        chrome.apply_dark_titlebar(self.root)

        self.restore_geometry()

        dialogs.attach(self.root)

        shell.build(self)      # header, status strip, legend, screen container
        workspace.build(self)  # the lobby screen
        landing.build(self)    # the main-menu screen

        self.wheel = WheelRouter(self.root)
        self.wheel.register(self.seekbar, self.on_wheel_seek)
        self.wheel.register_ctrl(self.seekbar, self.on_wheel_zoom)
        self.wheel.register(self.track_canvas, self.on_wheel_roster)
        self.wheel.register(self.track_scrollbar, self.on_wheel_roster)
        self.wheel.register(
            self.trim_in_entry,
            lambda steps, fine: self.on_wheel_trim_entry("start", steps, fine),
        )
        self.wheel.register(
            self.trim_out_entry,
            lambda steps, fine: self.on_wheel_trim_entry("end", steps, fine),
        )
        self.wheel.register(
            self.log_text,
            lambda steps, fine: self.log_text.yview_scroll(-steps * 2, "units"),
        )

        dialogs.set_toast_offset(px(theme.FOOTER_H + 16))

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.bind_shortcuts()
        self.refresh_playback_button_state()

        # Restore persisted compression state without the toggle log lines.
        if self.compress_enabled_var.get() and hasattr(self, "compression_options_frame"):
            self.compression_options_frame.pack(side=tk.LEFT, padx=(px(10), 0))

        self.update_compression_estimate()
        self.show_landing()

    # ========================================================
    # Settings persistence
    # ========================================================

    def restore_geometry(self):
        if not self.settings.remember_geometry or not self.settings.window_geometry:
            return
        try:
            geometry = self.settings.window_geometry
            # Clamp the saved position back onto the virtual screen so the
            # window never restores fully off-screen.
            size, _, rest = geometry.partition("+")
            if rest:
                x_str, _, y_str = rest.partition("+")
                x = min(max(-px(40), int(x_str)), max(0, self.root.winfo_screenwidth() - px(200)))
                y = min(max(0, int(y_str)), max(0, self.root.winfo_screenheight() - px(200)))
                geometry = f"{size}+{x}+{y}"
            self.root.geometry(geometry)
            if self.settings.window_maximized:
                self.root.state("zoomed")
        except Exception:
            pass

    def save_settings(self):
        s = self.settings
        try:
            if chrome.is_maximized(self.root):
                s.window_maximized = True
            else:
                s.window_maximized = False
                s.window_geometry = self.root.winfo_geometry()
        except Exception:
            pass
        s.compress_enabled = bool(self.compress_enabled_var.get())
        s.compression_target_mb = self.compression_target_var.get().strip() or s.compression_target_mb
        s.compression_resolution = self.get_compression_resolution_label()
        s.auto_preview_after_load = bool(self.auto_preview_after_load)
        s.recent_clips = list(self.recent_clips)
        s.last_open_dir = self.last_open_dir
        app_settings.save(s)

    def open_settings(self):
        SettingsOverlay(self)

    # ========================================================
    # Screen routing
    # ========================================================

    def show_landing(self):
        self.stop_preview()
        self.landing_frame.lift()
        self.active_screen = "landing"
        self.set_status("Ready.")
        if hasattr(self, "refresh_landing_detail"):
            self.refresh_landing_detail()
        self.update_legend()

    def show_workspace(self):
        self.workspace_frame.lift()
        self.active_screen = "workspace"
        self.update_legend()

    def update_legend(self):
        if not hasattr(self, "legend"):
            return

        if self.is_exporting:
            hints = [("ESC", "CANCEL EXPORT")]
        elif self.active_screen == "landing":
            hints = [("CTRL+O", "OPEN CLIP"), ("DROP", "LOAD FILE")]
        elif self.video_path:
            hints = [
                ("SPACE", "PLAY/PAUSE"),
                ("← →", "SEEK"),
                ("WHEEL", "SEEK · VOLUME"),
                ("[ ]", "TRIM"),
                ("CTRL+E", "EXPORT"),
                ("ESC", "MENU"),
            ]
        else:
            hints = [("CTRL+O", "OPEN CLIP"), ("ESC", "MENU")]

        self.legend.set_hints(hints)

    # ========================================================
    # Keyboard shortcuts
    # ========================================================

    def bind_shortcuts(self):
        root = self.root
        root.bind("<space>", lambda e: self.shortcut(self.toggle_preview))
        root.bind("<Key-bracketleft>", lambda e: self.shortcut(self.set_trim_start))
        root.bind("<Key-bracketright>", lambda e: self.shortcut(self.set_trim_end))
        root.bind("<Left>", lambda e: self.shortcut(lambda: self.seek_relative(-5.0)))
        root.bind("<Right>", lambda e: self.shortcut(lambda: self.seek_relative(5.0)))
        root.bind("<Shift-Left>", lambda e: self.shortcut(lambda: self.seek_relative(-1.0)))
        root.bind("<Shift-Right>", lambda e: self.shortcut(lambda: self.seek_relative(1.0)))
        root.bind("<Home>", lambda e: self.shortcut(lambda: self.seek_absolute(0.0)))
        root.bind("<End>", lambda e: self.shortcut(
            lambda: self.seek_absolute(self.total_duration_seconds or 0.0)))
        root.bind("<Shift-Home>", lambda e: self.shortcut(lambda: self.jump_to_trim("start")))
        root.bind("<Shift-End>", lambda e: self.shortcut(lambda: self.jump_to_trim("end")))
        root.bind("<comma>", lambda e: self.shortcut(lambda: self.step_frame(-1)))
        root.bind("<period>", lambda e: self.shortcut(lambda: self.step_frame(1)))
        root.bind("<Key-m>", lambda e: self.shortcut(self.toggle_mute_preview))
        root.bind("<Key-M>", lambda e: self.shortcut(self.toggle_mute_preview))
        root.bind("<Key-c>", lambda e: self.shortcut(self.toggle_crop_mode))
        root.bind("<Key-C>", lambda e: self.shortcut(self.toggle_crop_mode))
        root.bind("<Key-k>", lambda e: self.shortcut(self.on_crop_add_key))
        root.bind("<Key-K>", lambda e: self.shortcut(self.on_crop_add_key))
        root.bind("<Control-Key-0>", lambda e: self.shortcut(self.reset_timeline_zoom))
        for digit in range(10):
            root.bind(f"<Key-{digit}>",
                      lambda e, n=digit: self.shortcut(lambda: self.seek_to_fraction(n / 10.0)))
        root.bind("<Control-o>", lambda e: self.shortcut_load())
        root.bind("<Control-e>", lambda e: self.shortcut(self.export_video_dialog))
        root.bind("<Control-comma>", lambda e: self.shortcut_settings())
        root.bind("<Control-C>", lambda e: self.shortcut(self.copy_timestamp))
        root.bind("<Escape>", lambda e: self.shortcut_escape())

    def _typing_in_entry(self) -> bool:
        try:
            focus = self.root.focus_get()
        except Exception:
            focus = None
        return isinstance(focus, (tk.Entry, tk.Text))

    def shortcut(self, action):
        """Workspace shortcut with the standard guards."""
        if self.active_screen != "workspace" or self.is_exporting:
            return "break" if self.is_exporting else None
        if self._typing_in_entry():
            return None
        if not self.video_path:
            return None
        action()
        return "break"

    def shortcut_load(self):
        if self.is_exporting or self._typing_in_entry():
            return "break"
        self.load_video_dialog()
        return "break"

    def shortcut_settings(self):
        if self.is_exporting or self._typing_in_entry():
            return "break"
        self.open_settings()
        return "break"

    def copy_timestamp(self):
        text = self.format_timecode(self.current_seek_seconds())
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
        except Exception:
            return
        self.set_status(f"Copied timestamp {text} to clipboard.")
        self.log(f"Copied timestamp {text}.")

    def shortcut_escape(self):
        if self.is_exporting:
            self.cancel_export()
            return "break"
        if self._typing_in_entry():
            self.root.focus_set()
            return "break"
        if self.active_screen == "workspace":
            self.show_landing()
            return "break"
        return None

    def seek_relative(self, delta: float):
        duration = self.total_duration_seconds or 0
        target = self.current_seek_seconds() + delta
        if duration:
            target = min(max(0.0, target), duration)
        else:
            target = max(0.0, target)
        self.seek_absolute(target)

    def seek_absolute(self, seconds: float):
        # Route through the same press/release path as a mouse seek so
        # play/pause semantics match exactly.
        self.on_seek_press()
        self.seek_var.set(seconds)
        self.on_seek_release()

    def seek_to_fraction(self, fraction: float):
        duration = self.total_duration_seconds or 0
        if duration <= 0:
            return
        self.seek_absolute(min(max(0.0, fraction), 1.0) * duration)

    def step_frame(self, direction: int):
        """Nudge the playhead by one frame. If playing, pause on the current
        frame first (the paused scrub-still path renders each stepped frame)."""
        if not self.video_path:
            return

        if self.playback.state in (core_playback.PLAYING, core_playback.STARTING):
            self.pause_playback()

        fps = self.video_fps or core_mediainfo.DEFAULT_FRAME_RATE
        step = 1.0 / max(1.0, fps)
        self.seek_relative(direction * step)

    # ========================================================
    # Mouse wheel
    # ========================================================

    def on_wheel_zoom(self, steps: int, x_px: int):
        """Ctrl+wheel over the seekbar: zoom the timeline view, anchored at
        the cursor (Vegas/LosslessCut-style)."""
        if self.active_screen != "workspace" or not self.video_path:
            return
        self.seekbar.zoom_at(steps, x_px)

    def reset_timeline_zoom(self):
        self.seekbar.reset_view()

    def on_wheel_seek(self, steps: int, fine: bool):
        """Wheel over the seekbar: ±5 s per notch (Shift = ±1 s). Notches
        move the handle and scrub-still immediately; the pipeline respawn
        commits shortly after the last notch so spinning the wheel doesn't
        spawn a pipeline per click."""
        if self.is_exporting or not self.video_path or self.user_is_seeking:
            return
        if self.active_screen != "workspace":
            return

        state = self.playback.state

        if self.wheel_seek_after_id is None:
            # First notch of a burst: freeze a playing preview in place,
            # exactly like pressing the seekbar. Conceal only on the still
            # path — mpv paints seeked frames live, and concealing would
            # knock it off the fast live-scrub path.
            if state == core_playback.PLAYING:
                self.wheel_seek_resume = True
                self.pause_playback()
                if not self._live_scrub_active():
                    self.playback.conceal()
            elif state == core_playback.STARTING:
                self.wheel_seek_resume = True
            else:
                self.wheel_seek_resume = False
                if state == core_playback.PAUSED and not self._live_scrub_active():
                    self.playback.conceal()
        else:
            try:
                self.root.after_cancel(self.wheel_seek_after_id)
            except Exception:
                pass

        step = 1.0 if fine else 5.0
        duration = self.total_duration_seconds or 0
        target = self.current_seek_seconds() + steps * step
        target = min(max(0.0, target), duration) if duration else max(0.0, target)

        self.set_seek_position(target)

        if self.playback.state == core_playback.PAUSED:
            self.schedule_scrub_frame(target)

        self.wheel_seek_after_id = self.root.after(250, self.commit_wheel_seek)

    def commit_wheel_seek(self):
        self.wheel_seek_after_id = None

        target = self.current_seek_seconds()
        resume = self.wheel_seek_resume
        self.wheel_seek_resume = False
        state = self.playback.state

        if resume or state in (core_playback.STARTING, core_playback.PLAYING):
            self.restart_playback_at(target)
        elif state == core_playback.PAUSED:
            self.playback.seek_paused(target)
            self.refresh_playback_button_state()
            self.set_status(
                f"Preview paused at {self.format_seconds(target)}. Click Play to resume."
            )
            self.request_scrub_frame(target)
        # IDLE: the start position simply moved.

    def on_wheel_roster(self, steps: int, fine: bool):
        if self.track_scrollbar.winfo_ismapped():
            self.track_canvas.yview_scroll(-steps, "units")

    def remember_recent_clip(self, path: str | None):
        if not path:
            return
        path = str(path)
        if path in self.recent_clips:
            self.recent_clips.remove(path)
        self.recent_clips.insert(0, path)
        del self.recent_clips[8:]
        if hasattr(self, "refresh_landing_detail"):
            self.refresh_landing_detail()
        self.save_settings()

    def remove_recent_clip(self, path: str):
        if path in self.recent_clips:
            self.recent_clips.remove(path)
            self.save_settings()
            if hasattr(self, "refresh_landing_detail"):
                self.refresh_landing_detail()

    # ------------------------------------------------------------------
    # Recent-clip thumbnails (cached beside the config)
    # ------------------------------------------------------------------

    def _thumb_dir(self) -> Path:
        base = os.environ.get("APPDATA")
        root = Path(base) / "ClipToolbox" if base else Path.home() / ".cliptoolbox"
        return root / "thumbs"

    THUMBNAIL_HEIGHT = 36  # logical px; landing sizes its holder to match

    def _thumb_cache_path(self, path: str) -> Path:
        try:
            mtime = int(Path(path).stat().st_mtime)
        except Exception:
            mtime = 0
        height = px(self.THUMBNAIL_HEIGHT)
        key = hashlib.md5(f"{path}|{mtime}|{height}".encode("utf-8")).hexdigest()
        return self._thumb_dir() / f"{key}.png"

    def _load_thumbnail(self, cache_path: Path):
        key = str(cache_path)
        cached = self.thumbnail_cache.get(key)
        if cached is not None:
            return cached
        if not PIL_AVAILABLE or not cache_path.exists():
            return None
        try:
            image = Image.open(cache_path)
            image.load()
            photo = ImageTk.PhotoImage(image)
            self.thumbnail_cache[key] = photo  # hold a reference
            return photo
        except Exception:
            return None

    def get_recent_thumbnail(self, path: str, on_ready):
        """Deliver a cached PhotoImage for a recent clip (or None). Extraction
        runs on a worker and calls on_ready on the Tk thread when done."""
        if not PIL_AVAILABLE or not FFMPEG or not Path(path).exists():
            on_ready(None)
            return

        cache_path = self._thumb_cache_path(path)
        existing = self._load_thumbnail(cache_path)
        if existing is not None:
            on_ready(existing)
            return

        def worker():
            try:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cmd = [
                    FFMPEG, "-hide_banner", "-loglevel", "error",
                    "-ss", "1", "-i", path,
                    "-vf", f"scale=-2:{px(self.THUMBNAIL_HEIGHT)}", "-frames:v", "1",
                    "-y", str(cache_path),
                ]
                process = subprocess.Popen(
                    cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    creationflags=CREATE_NO_WINDOW,
                )
                assign_process_to_cleanup_job(process)
                try:
                    process.wait(timeout=6)
                except subprocess.TimeoutExpired:
                    process.kill()
            except Exception:
                pass
            self.ui(lambda: on_ready(self._load_thumbnail(cache_path)))

        threading.Thread(target=worker, daemon=True).start()

    def enable_drag_and_drop(self):
        if not DND_AVAILABLE:
            return

        try:
            self.root.drop_target_register(DND_FILES)
            self.root.dnd_bind("<<Drop>>", self.drop_video)
        except Exception as exc:
            self.dnd_hint_var.set(f"Drag and drop failed to initialize: {exc}")

    # ========================================================
    # Thread-safe UI helpers
    # ========================================================

    def ui(self, callback, *args, **kwargs):
        """Thread-safe: queue a callback to run on the Tk main thread.

        Never calls into Tk from the caller's thread — only pure-Python
        queue operations, which are safe to call from any thread even
        while the main thread is blocked inside a native modal loop.
        """
        self._ui_queue.put((callback, args, kwargs))

    def _pump_ui_queue(self):
        while True:
            try:
                callback, args, kwargs = self._ui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                callback(*args, **kwargs)
            except Exception:
                import traceback
                traceback.print_exc()
        self.root.after(15, self._pump_ui_queue)

    def set_status(self, text: str):
        self.status_var.set(text)

    def log(self, text: str):
        if threading.current_thread() is not threading.main_thread():
            self.ui(self.log, text)
            return

        if not hasattr(self, "log_text"):
            return

        timestamp = time.strftime("%H:%M:%S")
        line = f"[{timestamp}] {text}\n"

        try:
            self.log_text.config(state=tk.NORMAL)
            self.log_text.insert(tk.END, line)
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)
        except Exception:
            pass

    def schedule_volume_log(self, stream_index: int, track_label: str, percentage: int):
        previous_after_id = self.volume_log_after_ids.get(stream_index)

        if previous_after_id is not None:
            try:
                self.root.after_cancel(previous_after_id)
            except Exception:
                pass

        def write_log():
            self.volume_log_after_ids.pop(stream_index, None)
            self.log(f"{track_label} volume set to {percentage}%.")

        self.volume_log_after_ids[stream_index] = self.root.after(450, write_log)

    def set_busy(self, busy: bool):
        state = tk.DISABLED if busy else tk.NORMAL

        self.load_button.config(state=state)
        if hasattr(self, "back_button"):
            self.back_button.config(state=tk.DISABLED if self.is_exporting else tk.NORMAL)

        # Compression settings only affect export, so keep them editable during
        # preview/playback. Lock them only while an export is actually running.
        export_state = tk.DISABLED if self.is_exporting else tk.NORMAL

        if hasattr(self, "compress_checkbox"):
            self.compress_checkbox.config(state=export_state)
        if hasattr(self, "compression_target_entry"):
            self.compression_target_entry.config(state=export_state)
        if hasattr(self, "compression_resolution_combo"):
            self.compression_resolution_combo.config(state="readonly" if not self.is_exporting else tk.DISABLED)

        if self.is_exporting:
            self.export_button.config(state=tk.DISABLED)
        else:
            self.export_button.config(state=tk.NORMAL)

        self.refresh_playback_button_state()

        # Keep audio sliders live while previewing so users can adjust the mix
        # (changes apply to the running pipeline immediately). During export,
        # however, controls stay locked to avoid changing an in-flight render.
        keep_sliders_live = busy and not self.is_exporting and self.playback.is_active

        slider_state = tk.NORMAL if keep_sliders_live else state

        for _, _, slider in self.track_controls:
            slider.config(state=slider_state)

        self.update_export_actions()
        self.update_legend()

    def update_export_actions(self):
        """Show the maroon CANCEL EXPORT button only while exporting."""
        if not hasattr(self, "stop_export_button"):
            return
        if self.is_exporting:
            if not self.stop_export_button.winfo_ismapped():
                self.stop_export_button.pack(side=tk.LEFT, padx=(px(8), 0))
        else:
            if self.stop_export_button.winfo_ismapped():
                self.stop_export_button.pack_forget()

    def refresh_playback_button_state(self):
        """Keep the single visible playback button in sync with engine state."""
        if not hasattr(self, "preview_button"):
            return

        if self.is_exporting:
            self.preview_button.config(text="PLAY", state=tk.DISABLED)
            return

        state = self.playback.state

        if state == core_playback.PAUSED:
            if self.scrub_resume_pending:
                # Mid-scrub freeze of a playing preview: it resumes on release,
                # so keep the button reading as playback rather than flashing.
                self.preview_button.config(text="PAUSE", state=tk.DISABLED)
            else:
                self.preview_button.config(text="PLAY", state=tk.NORMAL)
            return

        if state == core_playback.STARTING:
            self.preview_button.config(text="LOADING...", state=tk.DISABLED)
            return

        if state == core_playback.PLAYING:
            self.preview_button.config(text="PAUSE", state=tk.NORMAL)
            return

        if self.video_path:
            self.preview_button.config(text="PLAY", state=tk.NORMAL)
        else:
            self.preview_button.config(text="PLAY", state=tk.DISABLED)

    # ========================================================
    # Startup checks
    # ========================================================

    def startup_checks(self):
        missing = []

        if not FFMPEG:
            missing.append("ffmpeg")
        if not FFPROBE:
            missing.append("ffprobe")
        if not FFPLAY:
            missing.append("ffplay")

        if missing:
            self.set_status("Missing required FFmpeg tools.")
            self.build_line_var.set(f"{APP_NAME} v2.0  |  ffmpeg: MISSING")
            self.log("Missing required FFmpeg tools: " + ", ".join(missing))
            messagebox.showwarning(
                "FFmpeg tools missing",
                "The app could not find these tools:\n\n"
                + "\n".join(f"- {tool}" for tool in missing)
                + "\n\nExpected folder:\n"
                + str(FFMPEG_BIN_DIR)
                + "\n\nRequired files:\n"
                + str(FFMPEG_BIN_DIR / exe_name("ffmpeg"))
                + "\n"
                + str(FFMPEG_BIN_DIR / exe_name("ffprobe"))
                + "\n"
                + str(FFMPEG_BIN_DIR / exe_name("ffplay")),
            )
        else:
            version_text = f"Ready ({APP_VERSION})." if APP_VERSION else "Ready."
            self.set_status(f"{version_text} FFmpeg folder: {FFMPEG_BIN_DIR}")
            self.log(f"{version_text} FFmpeg folder: {FFMPEG_BIN_DIR}")

        self.log(f"Playback engine: {self.playback_engine_name.upper()}.")
        if (self.settings.playback_engine == engine_factory.ENGINE_MPV
                and self.playback_engine_name != engine_factory.ENGINE_MPV):
            self.log("mpv.exe not found — fell back to FFplay. Put an mpv build "
                     "in the mpv folder next to ffmpeg (see BUILD_NOTES).")

    # ========================================================
    # Loading files
    # ========================================================

    def load_video_dialog(self):
        path = filedialog.askopenfilename(
            title="Select video file",
            initialdir=self.last_open_dir or None,
            filetypes=[
                ("Video files", "*.mp4 *.mov *.mkv *.avi *.webm *.m4v"),
                ("All files", "*.*"),
            ],
        )

        if path:
            self.last_open_dir = str(Path(path).parent)
            self.load_video(path)

    def drop_video(self, event):
        try:
            paths = self.root.tk.splitlist(event.data)
            if paths:
                self.load_video(paths[0])
        except Exception:
            fallback_path = str(event.data).strip("{}")
            if fallback_path:
                self.load_video(fallback_path)

    def load_video(self, path: str):
        if not FFPROBE:
            messagebox.showerror("Missing ffprobe", "ffprobe was not found.")
            return

        path_obj = Path(path).resolve()

        if not path_obj.exists():
            messagebox.showerror("File not found", str(path_obj))
            return

        self.show_workspace()

        self.stop_preview()

        # Persist the outgoing clip's setup, then look up a saved session for
        # the incoming one (applied in after_probe, once the probe results and
        # track rows exist).
        self.persist_video_session()
        self._session_to_restore = video_sessions.load(str(path_obj))

        self.video_path = str(path_obj)
        self.video_fps = None
        self.video_dimensions = None
        self.playback.configure_media(self.video_path, None)
        self.file_label_var.set(path_obj.name)
        self.clear_tracks()
        self.set_seek_range(0)
        self.clear_trim_points(silent=True)
        if self.crop:
            self.crop.reset()
        self.preview_placeholder_var.set("Preparing file...")
        self.preview_placeholder.place(relx=0.5, rely=0.5, anchor="center")
        self.refresh_playback_button_state()
        self.set_status("Reading audio streams...")
        self.log(f"Loaded video: {path_obj.name}")
        self.log("Reading audio streams and duration...")

        def worker():
            streams = self.get_audio_streams(str(path_obj))
            duration = self.get_media_duration(str(path_obj))
            fps = core_mediainfo.probe_frame_rate(str(path_obj))
            dimensions = core_mediainfo.probe_video_dimensions(str(path_obj))
            self.ui(self.after_probe, streams, duration, fps, dimensions)

        threading.Thread(target=worker, daemon=True).start()

    def after_probe(self, streams: list[dict], duration: float | None,
                    fps: float | None = None,
                    dimensions: tuple[int, int] | None = None):
        self.audio_metadata = streams
        self.total_duration_seconds = duration
        self.video_fps = fps
        self.video_dimensions = dimensions
        self.playback.configure_media(self.video_path, duration)
        self.set_seek_range(duration)
        self.seekbar.set_fps(fps)  # enables the zoomed-in frame grid
        self.update_trim_controls()
        if self.crop:
            self.crop.set_source(dimensions, duration, fps)

        self.clear_tracks()
        self.restore_video_session()

        if not streams:
            self.set_status("No audio tracks found.")
            self.preview_placeholder_var.set("No audio tracks found.")
            messagebox.showinfo(
                "No audio tracks",
                "No audio streams were found in this file.",
            )
            self.refresh_playback_button_state()
            return

        for row_number, info in enumerate(streams):
            self.add_track_row(row_number, info)

        self.update_track_area_height(len(streams))
        # A restored session may start rows disabled; tint their strips now.
        self.update_track_row_styles()
        self.remember_recent_clip(self.video_path)
        self.update_legend()

        duration_text = self.format_seconds(duration) if duration else "unknown duration"
        self.preview_placeholder_var.set("Starting preview...")
        self.preview_placeholder.place(relx=0.5, rely=0.5, anchor="center")
        self.set_status(f"Loaded {len(streams)} audio track(s), {duration_text}. Starting preview...")
        self.log(f"Found {len(streams)} audio track(s). Duration: {duration_text}.")

        for info in streams:
            self.log(f"Audio stream available: {info['label']}")

        self.update_compression_estimate()

        if self.auto_preview_after_load:
            self.root.after(300, self.start_preview)

    def clear_tracks(self):
        self.track_controls.clear()
        self.track_state_strips.clear()
        self.preview_muted = False
        self.solo_row = None

        for widget in self.track_frame.winfo_children():
            self.wheel.unregister(widget)
            widget.destroy()

        self.update_track_area_height(0)

    # ========================================================
    # Per-video sessions (trim / crop keyframes / track mix)
    # ========================================================

    def capture_video_session(self) -> dict:
        state = {
            "trim": {
                "enabled": bool(self.trim_enabled_var.get()),
                "start": self.trim_start_seconds,
                "end": self.trim_end_seconds,
            },
            "tracks": [
                {"index": stream_index, "enabled": bool(var.get()),
                 "volume": float(slider.get())}
                for stream_index, var, slider in self.track_controls
            ],
            "position": self.current_seek_seconds(),
        }
        if self.crop:
            state["crop"] = self.crop.export_state()
        return state

    def persist_video_session(self):
        """Save the current clip's setup so reopening it restores everything."""
        if not self.video_path:
            return
        try:
            video_sessions.save(self.video_path, self.capture_video_session())
        except Exception:
            pass

    def session_track_state(self, stream_index: int) -> tuple[bool, float]:
        """Saved (enabled, volume) for a stream in the session being restored,
        or the fresh-row defaults."""
        state = self._session_to_restore or {}
        for track in state.get("tracks") or []:
            if track.get("index") == stream_index:
                try:
                    volume = min(2.0, max(0.0, float(track.get("volume", 1.0))))
                except (TypeError, ValueError):
                    volume = 1.0
                return bool(track.get("enabled", True)), volume
        return True, 1.0

    def restore_video_session(self):
        """Re-apply a saved session (looked up in load_video). Track rows pull
        their part via session_track_state; this handles trim, crop keyframes,
        and the playhead."""
        state = self._session_to_restore
        if not state:
            return
        duration = self.total_duration_seconds or 0

        def saved_time(value):
            try:
                seconds = float(value)
            except (TypeError, ValueError):
                return None
            if seconds < 0:
                return None
            return min(seconds, duration) if duration else seconds

        restored = []

        trim = state.get("trim") or {}
        start = saved_time(trim.get("start"))
        end = saved_time(trim.get("end"))
        if start is not None or end is not None:
            self.trim_start_seconds = start
            self.trim_end_seconds = end
            self.trim_enabled_var.set(bool(trim.get("enabled")))
            self.update_trim_controls()
            restored.append("trim")

        crop_state = state.get("crop") or {}
        if self.crop and crop_state.get("keyframes"):
            if self.crop.restore_state(crop_state):
                count = len(crop_state["keyframes"])
                restored.append(f"{count} crop keyframe(s)")

        if any(not track.get("enabled", True) or track.get("volume") not in (None, 1.0, 1)
               for track in state.get("tracks") or []):
            restored.append("track mix")

        # Resume near where the clip was left, unless that would start a
        # preview right at EOF.
        position = saved_time(state.get("position"))
        if position and (not duration or position < duration - 0.5):
            self.set_seek_position(position)

        if restored:
            self.log("Restored saved setup: " + ", ".join(restored) + ".")

    def update_track_area_height(self, track_count: int):
        # Keep the roster only as tall as the rows it actually needs; beyond
        # four tracks the list scrolls instead of growing.
        visible_rows = min(max(track_count, 1), 4)
        row_height = px(58)
        canvas_height = px(4) + (visible_rows * row_height)

        self.track_canvas.configure(height=canvas_height)

        if track_count > 4:
            if not self.track_scrollbar.winfo_ismapped():
                self.track_scrollbar.grid()
        else:
            if self.track_scrollbar.winfo_ismapped():
                self.track_scrollbar.grid_remove()

        self.roster_title_var.set(f"{track_count} TRACK(S) IN MIX")
        self.track_canvas.itemconfigure(
            self.track_window,
            width=max(1, self.track_canvas.winfo_width()),
        )

    def add_track_row(self, row_number: int, info: dict):
        from cliptoolbox.ui.widgets import HaloCheckbox, HaloSlider

        row = tk.Frame(self.track_frame, bg=theme.PANEL_FILL)
        row.grid(row=row_number, column=0, sticky="ew", pady=(0, px(8)))
        row.columnconfigure(0, weight=1)

        # Fresh rows default to enabled at 100%; a restored session overrides.
        initial_enabled, initial_volume = self.session_track_state(info["index"])

        var = tk.BooleanVar(value=initial_enabled)
        var.trace_add(
            "write",
            lambda *args, row=row_number: self.apply_track_volume(row),
        )

        # Roster-style row: the lobby player name bar (maroon in H2, party
        # green in Reach) + slider.
        name_bar = tk.Frame(row, bg=theme.ROSTER)
        name_bar.grid(row=0, column=0, sticky="ew")

        # Left indicator strip — tinted for solo (accent) / silenced (dim).
        state_strip = tk.Frame(name_bar, bg=theme.ROSTER, width=px(4))
        state_strip.pack(side=tk.LEFT, fill=tk.Y)
        self.track_state_strips[row_number] = state_strip

        checkbox = HaloCheckbox(
            name_bar, text=info["label"], variable=var,
            behind=theme.ROSTER, text_color=theme.TEXT_BRIGHT,
            font=theme.font_body(13),
        )
        checkbox.pack(side=tk.LEFT, padx=px(6), pady=px(2))

        volume_label_var = tk.StringVar(value=f"{int(round(initial_volume * 100))}%")
        tk.Label(name_bar, textvariable=volume_label_var, font=theme.font_small(),
                 bg=theme.ROSTER, fg=theme.TEXT_BRIGHT).pack(side=tk.RIGHT, padx=px(8))

        slider = HaloSlider(row, from_=0.0, to=2.0, resolution=0.01,
                            behind=theme.PANEL_FILL)
        slider.set(initial_volume)

        def on_volume_change(value, label_var=volume_label_var, row=row_number):
            try:
                percentage = int(float(value) * 100)
                label_var.set(f"{percentage}%")
            except Exception:
                label_var.set("100%")

            try:
                self.schedule_volume_log(info["index"], info["label"], percentage)
            except Exception:
                pass

            self.apply_track_volume(row)

        slider.config(command=on_volume_change)
        slider.grid(row=1, column=0, sticky="ew", pady=(px(2), 0))

        # Double-click the slider snaps it back to 100%.
        def reset_volume(_event=None, row=row_number):
            slider.set(1.0)
            on_volume_change(1.0)
            return "break"

        slider.bind("<Double-Button-1>", reset_volume)

        # Right-click anywhere on the row toggles solo for this track.
        def solo(_event=None, row=row_number):
            self.toggle_solo(row)
            return "break"

        for widget in (row, name_bar, checkbox):
            widget.bind("<Button-3>", solo)

        def on_wheel(steps, fine):
            # Wheel anywhere over the row adjusts this track: ±5% per notch,
            # Shift = ±1%. Runs through the same path as a slider drag.
            if self.is_exporting:
                return
            step = 0.01 if fine else 0.05
            current = float(slider.get())
            value = min(2.0, max(0.0, round(current + steps * step, 2)))
            if value != current:
                slider.set(value)
                on_volume_change(value)

        self.wheel.register(row, on_wheel)

        self.track_controls.append((info["index"], var, slider))

    # ========================================================
    # ffprobe
    # ========================================================

    def get_audio_streams(self, filepath: str) -> list[dict]:
        try:
            return core_probe.probe_audio_streams(filepath)
        except core_probe.ProbeError as exc:
            self.ui(
                messagebox.showerror,
                "FFprobe Error",
                str(exc),
            )
            return []

    def get_media_duration(self, filepath: str) -> float | None:
        return core_probe.probe_duration(filepath)

    # ========================================================
    # Seekbar
    # ========================================================

    def set_seek_range(self, duration: float | None):
        duration = duration or 0

        self.seekbar.configure(to=max(duration, 1))
        self.seekbar.reset_view()  # a new clip starts fully zoomed out
        self.seekbar.set_cache_ranges([])
        self.time_left_var.set("0:00")
        self.seek_var.set(0)
        self.update_time_right(0)
        self.update_trim_markers()

    def set_seek_position(self, seconds: float):
        seconds = max(0, float(seconds))

        duration = self.total_duration_seconds or 0
        if duration:
            seconds = min(seconds, duration)

        if not self.user_is_seeking:
            self.seek_var.set(seconds)

        self.time_left_var.set(self.format_seconds(seconds))
        self.update_time_right(seconds)
        self.seekbar.follow(seconds)  # auto-scroll a zoomed view to the playhead

        if self.crop:
            self.crop.on_playhead(seconds)

    def on_playback_cache_ranges(self, ranges):
        """mpv's in-RAM cache grew/shrank: repaint the seekbar's cache bar."""
        if hasattr(self, "seekbar"):
            self.seekbar.set_cache_ranges(ranges)

    def update_time_right(self, position: float):
        """Right-hand time label: total duration, or count-down remaining when
        toggled (click the label). Left label always shows elapsed."""
        duration = self.total_duration_seconds or 0
        if self.show_remaining and duration:
            remaining = max(0.0, duration - max(0.0, position))
            self.time_right_var.set("-" + self.format_seconds(remaining))
        else:
            self.time_right_var.set(self.format_seconds(duration))

    def toggle_time_display(self, _event=None):
        self.show_remaining = not self.show_remaining
        try:
            position = float(self.seek_var.get())
        except Exception:
            position = 0.0
        self.update_time_right(position)

    def on_seek_press(self, event=None):
        self.user_is_seeking = True

        state = self.playback.state

        if state == core_playback.PLAYING:
            # Freeze in place: the exact current frame stays on screen while
            # the user drags, and release resumes playback at the target.
            self.scrub_resume_pending = True
            self.pause_playback()
            # ffplay: swap the live window for a captured still, because drag
            # previews render in a Tk overlay the native window would paint
            # over. mpv paints the seeked frame itself, so leave it visible.
            if not self._live_scrub_active():
                self.playback.conceal()
        elif state == core_playback.STARTING:
            self.scrub_resume_pending = True
        else:
            self.scrub_resume_pending = False
            if state == core_playback.PAUSED and not self._live_scrub_active():
                self.playback.conceal()

    def on_seek_drag(self, value):
        if self.user_is_seeking:
            try:
                seconds = float(value)
                self.time_left_var.set(self.format_seconds(seconds))

                if self.playback.state == core_playback.PAUSED:
                    self.schedule_scrub_frame(seconds)
            except Exception:
                pass

    def on_seek_release(self, event=None):
        self.user_is_seeking = False

        try:
            target_seconds = float(self.seek_var.get())
        except Exception:
            target_seconds = 0.0

        self.set_seek_position(target_seconds)
        self.update_trim_markers()

        resume = self.scrub_resume_pending
        self.scrub_resume_pending = False
        state = self.playback.state

        if state in (core_playback.STARTING, core_playback.PLAYING) or (
            state == core_playback.PAUSED and resume
        ):
            # The frozen frame (or last still) stays visible until the new
            # pipeline's first frame arrives.
            self.restart_playback_at(target_seconds)
        elif state == core_playback.PAUSED:
            # Stay paused at the dropped position with a matching frame.
            self.playback.seek_paused(target_seconds)
            self.refresh_playback_button_state()
            self.set_status(f"Preview paused at {self.format_seconds(target_seconds)}. Click Play to resume.")
            self.request_scrub_frame(target_seconds)

    def schedule_scrub_frame(self, seconds: float):
        """
        Show frame previews while dragging in paused mode.

        FFmpeg frame extraction is not fast enough to request every single
        video frame, so this throttles requests while still feeling like media
        player scrubbing.
        """
        if not self.video_path or not FFMPEG or not PIL_AVAILABLE:
            return

        duration = self.total_duration_seconds or 0
        if duration:
            seconds = min(max(0.0, float(seconds)), duration)
        else:
            seconds = max(0.0, float(seconds))

        if self._live_scrub_active():
            # mpv paints the real frame directly. Keyframe-snap seeks while
            # the drag is in flight (instant, like mpv's own seekbar); the
            # release/commit seek is exact.
            if (self.last_scrub_frame_seconds is not None
                    and abs(seconds - self.last_scrub_frame_seconds) < 0.02):
                return
            self.last_scrub_frame_seconds = seconds
            self.playback.seek_paused(seconds, exact=False)
            return

        # Still-based scrub (ffplay, or the crop editor backdrop). mpv serves
        # stills from its warm process, so it can afford a much tighter cadence
        # than the spawn-ffmpeg-per-frame path.
        fast = getattr(self.playback, "supports_fast_stills", False)
        min_delta, debounce_ms = (0.03, 30) if fast else (0.08, 90)

        # Avoid requesting almost-identical frames repeatedly.
        if (
            self.last_scrub_frame_seconds is not None
            and abs(seconds - self.last_scrub_frame_seconds) < min_delta
        ):
            return

        self.last_scrub_frame_seconds = seconds

        if self.scrub_frame_after_id is not None:
            try:
                self.root.after_cancel(self.scrub_frame_after_id)
            except Exception:
                pass

        self.scrub_frame_after_id = self.root.after(
            debounce_ms,
            lambda s=seconds: self.request_scrub_frame(s),
        )

    def request_scrub_frame(self, seconds: float):
        self.scrub_frame_after_id = None

        if self.playback.state != core_playback.PAUSED:
            return

        if self._live_scrub_active():
            # The live window already shows the seeked frame; no still overlay.
            self.playback.seek_paused(seconds)
            return

        self.pending_still_request = self.playback.request_still(
            seconds, vf=self._crop_still_vf(seconds))

    def _crop_still_vf(self, seconds: float):
        """Static crop VF for a still at `seconds`, or None (no crop / editing)."""
        return self.crop.still_vf(seconds) if self.crop else None

    # ========================================================
    # Trim controls
    # ========================================================

    def on_trim_toggle(self):
        self.update_trim_controls()
        self.log("Trim controls enabled." if self.trim_enabled_var.get() else "Trim controls disabled.")

    # ---- Crop / keyframe delegates (logic lives in CropController) ----

    def on_crop_toggle(self):
        self.crop.on_toggle()

    def on_crop_preview_toggle(self):
        self.crop.toggle_mode()

    def toggle_crop_mode(self):
        """Keyboard 'C': flip crop mode when the clip has known dimensions."""
        if not self.video_dimensions:
            return
        self.crop_enabled_var.set(not self.crop_enabled_var.get())
        self.on_crop_toggle()

    def on_crop_add_key(self):
        self.crop.add_key()

    def on_crop_delete_key(self):
        self.crop.delete_key()

    def on_crop_prev_key(self):
        self.crop.goto_prev()

    def on_crop_next_key(self):
        self.crop.goto_next()

    def on_crop_reset_rect(self):
        self.crop.reset_rect()

    def on_crop_clear_keys(self):
        self.crop.clear_keys()

    def on_keyframe_click(self, index):
        self.crop.on_kf_click(index)

    def on_keyframe_drag(self, index, value):
        self.crop.on_kf_drag(index, value)

    def on_keyframe_commit(self, index, value):
        self.crop.on_kf_commit(index, value)

    def on_loop_toggle(self):
        if self.loop_enabled_var.get():
            bounds = self.loop_bounds()
            if bounds is not None:
                start, end = bounds
                self.log(f"Loop enabled ({self.format_seconds(start)} → {self.format_seconds(end)}).")
            else:
                self.log("Loop enabled.")
        else:
            self.log("Loop disabled.")

    def update_trim_controls(self):
        if not hasattr(self, "trim_buttons_frame"):
            return

        if self.trim_enabled_var.get():
            self.trim_buttons_frame.pack(side=tk.LEFT, padx=(px(10), 0))
        else:
            self.trim_buttons_frame.pack_forget()

        self.update_trim_info()
        self.update_trim_markers()
        self.update_compression_estimate()

    def on_compression_toggle(self):
        if not hasattr(self, "compression_options_frame"):
            return

        if self.compress_enabled_var.get():
            self.compression_options_frame.pack(side=tk.LEFT, padx=(px(10), 0))
            self.log(
                f"Compression enabled. Target size: {self.compression_target_var.get().strip() or f'{DEFAULT_COMPRESSION_TARGET_MB:g}'} MB "
                f"(Windows/Explorer/Discord), max resolution {self.get_compression_resolution_label()}."
            )
        else:
            self.compression_options_frame.pack_forget()
            self.log("Compression disabled.")

        self.update_compression_estimate()

    def on_compression_resolution_changed(self, event=None):
        if self.compress_enabled_var.get():
            self.log(f"Compression max resolution set to {self.get_compression_resolution_label()}.")

    def get_compression_resolution_label(self) -> str:
        from cliptoolbox.constants import COMPRESSION_RESOLUTION_PRESETS

        selected = self.compression_resolution_var.get().strip()
        if selected not in COMPRESSION_RESOLUTION_PRESETS:
            selected = DEFAULT_COMPRESSION_RESOLUTION
            self.compression_resolution_var.set(selected)
        return selected

    def get_compression_target_mb(self) -> float | None:
        if not self.compress_enabled_var.get():
            return None

        return core_commands.parse_target_mb(self.compression_target_var.get())

    def update_compression_estimate(self):
        """Live bitrate estimate on the compression card (reuses core math)."""
        if not hasattr(self, "compression_estimate_var"):
            return

        if not self.compress_enabled_var.get():
            if self.crop and self.crop.will_reencode():
                self.compression_estimate_var.set("Crop/zoom re-encode (H.265 NVENC)")
            else:
                self.compression_estimate_var.set("Stream-copy export (no re-encode)")
            return

        try:
            target_mb = core_commands.parse_target_mb(self.compression_target_var.get())
        except ValueError:
            self.compression_estimate_var.set("Enter a target like 9.99")
            return

        trim_start, trim_end = self.get_active_trim_points()
        duration = core_commands.export_progress_duration(
            self.total_duration_seconds, trim_start, trim_end)

        if duration <= 0:
            self.compression_estimate_var.set("Estimate appears once a clip is loaded")
            return

        try:
            video_kbps, audio_kbps, _ = core_commands.compression_bitrates_for_budget(
                target_mb, duration)
        except ValueError:
            self.compression_estimate_var.set("Target too small for this clip length")
            return

        self.compression_estimate_var.set(
            f"≈ {video_kbps} kbps video + {audio_kbps} kbps audio over {self.format_seconds(duration)}"
        )

    def current_seek_seconds(self) -> float:
        try:
            value = float(self.seek_var.get())
        except Exception:
            value = 0.0

        duration = self.total_duration_seconds or 0
        if duration:
            value = min(max(0.0, value), duration)

        return max(0.0, value)

    def set_trim_start(self):
        self.trim_start_seconds = self.current_seek_seconds()

        if (
            self.trim_end_seconds is not None
            and self.trim_start_seconds >= self.trim_end_seconds
        ):
            self.trim_end_seconds = None

        self.trim_enabled_var.set(True)
        self.update_trim_controls()
        self.set_status(f"Trim start set to {self.format_seconds(self.trim_start_seconds)}.")
        self.log(f"Trim start set to {self.format_seconds(self.trim_start_seconds)}.")

    def set_trim_end(self):
        self.trim_end_seconds = self.current_seek_seconds()

        if (
            self.trim_start_seconds is not None
            and self.trim_end_seconds <= self.trim_start_seconds
        ):
            self.trim_start_seconds = None

        self.trim_enabled_var.set(True)
        self.update_trim_controls()
        self.set_status(f"Trim end set to {self.format_seconds(self.trim_end_seconds)}.")
        self.log(f"Trim end set to {self.format_seconds(self.trim_end_seconds)}.")

    def clear_trim_points(self, silent: bool = False):
        self.trim_start_seconds = None
        self.trim_end_seconds = None

        if hasattr(self, "trim_info_var"):
            self.update_trim_info()
        if hasattr(self, "seekbar"):
            self.update_trim_markers()

        if not silent:
            self.set_status("Trim points cleared.")
            self.log("Trim points cleared.")

    def get_active_trim_points(self) -> tuple[float | None, float | None]:
        if not self.trim_enabled_var.get():
            return None, None

        return core_commands.clamp_trim_points(
            self.trim_start_seconds,
            self.trim_end_seconds,
            self.total_duration_seconds,
        )

    def update_trim_info(self):
        if not hasattr(self, "trim_info_var"):
            return

        # Endpoints show in the IN/OUT fields; this is just a compact length.
        if not self.trim_enabled_var.get():
            self.trim_info_var.set("")
            return

        start, end = self.get_active_trim_points()
        if start is not None and end is not None:
            self.trim_info_var.set(f"· {self.format_seconds(end - start)}")
        else:
            self.trim_info_var.set("")

    def update_trim_markers(self):
        """Trim brackets are drawn by the seekbar itself now."""
        if not hasattr(self, "seekbar"):
            return

        self.sync_trim_entries()

        duration = self.total_duration_seconds or 0
        if not self.trim_enabled_var.get() or duration <= 0:
            self.seekbar.set_trim(None, None)
            return

        start, end = self.get_active_trim_points()
        self.seekbar.set_trim(start, end)

    # ------------------------------------------------------------------
    # Timecodes + exact trim entry / bracket dragging
    # ------------------------------------------------------------------

    @staticmethod
    def format_timecode(seconds: float | None) -> str:
        """m:ss.cs — the precision the inline trim fields use."""
        if seconds is None:
            return ""
        seconds = max(0.0, float(seconds))
        minutes = int(seconds // 60)
        rest = seconds - minutes * 60
        return f"{minutes}:{rest:05.2f}"

    @staticmethod
    def parse_timecode(text: str) -> float | None:
        """Accept 'm:ss.cs', 'ss.cs', or raw seconds; return seconds or None."""
        text = (text or "").strip()
        if not text:
            return None
        try:
            if ":" in text:
                mins, _, secs = text.rpartition(":")
                return max(0.0, int(mins or 0) * 60 + float(secs))
            return max(0.0, float(text))
        except Exception:
            return None

    def sync_trim_entries(self):
        """Reflect the current trim values in the inline in/out fields, unless
        the user is typing in one of them. Unset bounds default to the clip's
        start (0:00) and end (full duration)."""
        if not hasattr(self, "trim_in_var"):
            return
        focus = None
        try:
            focus = self.root.focus_get()
        except Exception:
            pass
        duration = self.total_duration_seconds or 0.0
        in_inner = getattr(self.trim_in_entry, "entry", None)
        out_inner = getattr(self.trim_out_entry, "entry", None)
        if focus is not in_inner:
            start = self.trim_start_seconds if self.trim_start_seconds is not None else 0.0
            self.trim_in_var.set(self.format_timecode(start))
        if focus is not out_inner:
            end = self.trim_end_seconds if self.trim_end_seconds is not None else duration
            self.trim_out_var.set(self.format_timecode(end))

    _TIMECODE_KEY_RE = re.compile(r"^[0-9]*(:[0-9]{0,2})?(\.[0-9]*)?$")

    def validate_timecode_key(self, proposed: str) -> bool:
        """<Entry validate="key"> filter: only digits, one ':', one '.'."""
        if proposed == "":
            return True
        if proposed.count(":") > 1 or proposed.count(".") > 1:
            return False
        return bool(self._TIMECODE_KEY_RE.match(proposed))

    def set_trim_value(self, kind: str, seconds: float | None, enable: bool = True):
        """Shared setter for the inline entries and bracket dragging."""
        duration = self.total_duration_seconds or 0
        if seconds is not None:
            seconds = max(0.0, float(seconds))
            if duration:
                seconds = min(seconds, duration)

        if kind == "start":
            self.trim_start_seconds = seconds
            if (seconds is not None and self.trim_end_seconds is not None
                    and seconds >= self.trim_end_seconds):
                self.trim_end_seconds = None
        else:
            self.trim_end_seconds = seconds
            if (seconds is not None and self.trim_start_seconds is not None
                    and seconds <= self.trim_start_seconds):
                self.trim_start_seconds = None

        if enable:
            self.trim_enabled_var.set(True)
        self.update_trim_controls()

    def commit_trim_entry(self, kind: str, unfocus: bool = False):
        var = self.trim_in_var if kind == "start" else self.trim_out_var
        seconds = self.parse_timecode(var.get())
        if seconds is None and var.get().strip():
            # Unparseable — restore the displayed value.
            self.sync_trim_entries()
        else:
            self.set_trim_value(kind, seconds)
            if seconds is not None:
                label = "start" if kind == "start" else "end"
                self.log(f"Trim {label} set to {self.format_seconds(seconds)}.")
        if unfocus:
            self.root.focus_set()

    def on_wheel_trim_entry(self, kind: str, steps: int, fine: bool):
        """Wheel over an IN/OUT field: ±1 s per notch (Shift = ±0.1 s)."""
        step = 0.1 if fine else 1.0
        duration = self.total_duration_seconds or 0.0
        current = self.trim_start_seconds if kind == "start" else self.trim_end_seconds
        if current is None:
            current = 0.0 if kind == "start" else duration
        target = current + steps * step
        target = min(max(0.0, target), duration) if duration else max(0.0, target)
        self.set_trim_value(kind, target)
        # Refresh the field even if it currently has focus (a wheel notch is
        # a discrete action, not free-form typing that should be left alone).
        var = self.trim_in_var if kind == "start" else self.trim_out_var
        var.set(self.format_timecode(target))

    def on_trim_bracket_drag(self, kind: str, value: float):
        """Live update while a bracket is dragged on the seekbar."""
        if kind == "start":
            self.trim_start_seconds = float(value)
        else:
            self.trim_end_seconds = float(value)
        self.update_trim_info()
        # Show the frame at the dragged edge when paused (matches scrubbing).
        if self.playback.state == core_playback.PAUSED:
            self.set_seek_position(value)
            self.schedule_scrub_frame(value)

    def on_trim_bracket_commit(self, kind: str):
        self.update_trim_controls()
        seconds = self.trim_start_seconds if kind == "start" else self.trim_end_seconds
        if seconds is not None:
            label = "start" if kind == "start" else "end"
            self.set_status(f"Trim {label} set to {self.format_seconds(seconds)}.")
            self.log(f"Trim {label} set to {self.format_seconds(seconds)}.")

    def jump_to_trim(self, kind: str):
        if kind == "start":
            target = self.trim_start_seconds if self.trim_start_seconds is not None else 0.0
        else:
            target = (self.trim_end_seconds if self.trim_end_seconds is not None
                      else (self.total_duration_seconds or 0.0))
        self.seek_absolute(target)

    # ========================================================
    # FFmpeg filter building
    # ========================================================

    def selected_tracks(self) -> list[tuple[int, float]]:
        selected = []

        for stream_index, var, slider in self.track_controls:
            if var.get():
                selected.append((stream_index, float(slider.get())))

        return selected

    def build_audio_filter(self) -> str:
        return core_filters.build_audio_filter(self.selected_tracks())

    def effective_volume(self, row: int) -> float:
        """The volume a track actually contributes to the preview, folding in
        its slider, its enable checkbox, the global mute, and any solo. A
        single source of truth for the live mix, the preview graph, and every
        live update."""
        if not (0 <= row < len(self.track_controls)):
            return 0.0
        _, var, slider = self.track_controls[row]
        if self.preview_muted:
            return 0.0
        if self.solo_row is not None and self.solo_row != row:
            return 0.0
        if not var.get():
            return 0.0
        return float(slider.get())

    def superset_tracks(self) -> list[tuple[int, float]]:
        """
        Every track in row order for the preview graph, disabled/muted/
        non-soloed rows at volume 0.0. With amix normalize=0 this sounds
        identical to omitting them, and it lets checkbox toggles and slider
        drags apply to the running pipeline live instead of restarting it.
        Export still uses selected_tracks() with only the enabled rows.
        """
        return [
            (stream_index, self.effective_volume(row))
            for row, (stream_index, _, _) in enumerate(self.track_controls)
        ]

    def apply_track_volume(self, row: int):
        """Push one row's effective volume to the engine."""
        if not (0 <= row < len(self.track_controls)):
            return

        if not self.playback.set_track_volume(row, self.effective_volume(row)):
            # The live command channel failed; fall back to one seamless
            # respawn that bakes the current mix into a fresh pipeline.
            self.schedule_live_mix_fallback()

    def apply_all_track_volumes(self):
        """Re-push every row's effective volume (mute/solo/reset changes)."""
        for row in range(len(self.track_controls)):
            if not self.playback.set_track_volume(row, self.effective_volume(row)):
                self.schedule_live_mix_fallback()
                return

    # ------------------------------------------------------------------
    # Mute / solo / reset
    # ------------------------------------------------------------------

    def toggle_mute_preview(self):
        if not self.track_controls or self.is_exporting:
            return
        self.preview_muted = not self.preview_muted
        self.apply_all_track_volumes()
        self.update_track_row_styles()
        self.set_status("Preview muted." if self.preview_muted else "Preview unmuted.")
        self.log("Preview muted." if self.preview_muted else "Preview unmuted.")

    def toggle_solo(self, row: int):
        if self.is_exporting or not (0 <= row < len(self.track_controls)):
            return
        self.solo_row = None if self.solo_row == row else row
        self.apply_all_track_volumes()
        self.update_track_row_styles()
        if self.solo_row is None:
            self.log("Solo cleared.")
        else:
            _, _, _ = self.track_controls[row]
            self.log(f"Soloed track {row + 1}.")

    def reset_all_volumes(self):
        if not self.track_controls or self.is_exporting:
            return
        self.preview_muted = False
        self.solo_row = None
        for _, var, slider in self.track_controls:
            var.set(True)
            slider.set(1.0)
        self.apply_all_track_volumes()
        self.update_track_row_styles()
        self.set_status("All track volumes reset to 100%.")
        self.log("All track volumes reset to 100%.")

    def update_track_row_styles(self):
        """Recolor each row's left indicator strip: accent when soloed, dim
        when silenced (muted, or not the soloed row), roster color otherwise."""
        for row in range(len(self.track_controls)):
            strip = self.track_state_strips.get(row)
            if strip is None:
                continue
            if self.solo_row == row:
                color = theme.ACCENT
            elif self.effective_volume(row) <= 0.0:
                color = theme.TEXT_DIM
            else:
                color = theme.ROSTER
            try:
                strip.configure(bg=color)
            except Exception:
                pass

    def schedule_live_mix_fallback(self, delay_ms: int = 400):
        if self.live_mix_fallback_after_id is not None:
            try:
                self.root.after_cancel(self.live_mix_fallback_after_id)
            except Exception:
                pass

        self.live_mix_fallback_after_id = self.root.after(
            delay_ms, self.run_live_mix_fallback
        )

    def run_live_mix_fallback(self):
        self.live_mix_fallback_after_id = None

        state = self.playback.state
        if state in (core_playback.STARTING, core_playback.PLAYING):
            self.restart_playback_at(self.playback.position)
        elif state == core_playback.PAUSED and self.playback.has_pipeline:
            # Drop the paused pipeline (its mix is stale); resume will
            # respawn with the cached track volumes.
            self.playback.seek_paused(self.playback.position)

    # ========================================================
    # Paused still-frame preview
    # ========================================================

    def hide_paused_frame(self):
        try:
            if self.paused_frame_label is not None:
                self.paused_frame_label.place_forget()
                self.paused_frame_label.config(image="")
            self.paused_frame_image = None
        except Exception:
            pass

    def hide_preview_placeholder(self):
        try:
            self.preview_placeholder.place_forget()
        except Exception:
            pass

    def _display_paused_frame(self, image):
        image.thumbnail(
            (
                max(320, int(getattr(self, "preview_width", 960))),
                max(180, int(getattr(self, "preview_height", 540))),
            ),
            Image.LANCZOS,
        )
        self.paused_frame_image = ImageTk.PhotoImage(image)
        self.paused_frame_label.config(image=self.paused_frame_image, bg="black")
        self.paused_frame_label.place(relx=0.5, rely=0.5, anchor="center")
        self.paused_frame_label.lift()
        self.preview_placeholder.place_forget()

    def show_paused_frame_from_bytes(self, image_bytes: bytes):
        if not PIL_AVAILABLE or self.paused_frame_label is None:
            self.preview_placeholder_var.set("Paused. Click Play to resume preview.")
            return

        try:
            self._display_paused_frame(Image.open(BytesIO(image_bytes)))
        except Exception:
            self.preview_placeholder_var.set("Paused. Click Play to resume preview.")
            self.preview_placeholder.place(relx=0.5, rely=0.5, anchor="center")

    def show_paused_frame_raw(self, bgra: bytes, width: int, height: int):
        """Pause-time window capture: raw BGRA rows straight from PrintWindow."""
        if not PIL_AVAILABLE or self.paused_frame_label is None:
            self.preview_placeholder_var.set("Paused. Click Play to resume preview.")
            return

        try:
            image = Image.frombuffer(
                "RGBA", (width, height), bgra, "raw", "BGRA", 0, 1
            ).convert("RGB")
            self._display_paused_frame(image)
            # Flush the redraw now: the engine hides the live video window
            # right after this callback returns, and the frozen frame must
            # already be painted underneath to avoid a blank flicker.
            self.paused_frame_label.update_idletasks()
        except Exception:
            self.preview_placeholder_var.set("Paused. Click Play to resume preview.")
            self.preview_placeholder.place(relx=0.5, rely=0.5, anchor="center")

    # ========================================================
    # Embedded preview
    # ========================================================

    def toggle_preview(self):
        if self.is_exporting:
            return

        if self.crop and self.crop.active:
            # While cropping, play/pause flips working ⇄ preview mode: pausing
            # returns to the editor (box + keyframes), playing shows the result.
            if self.playback.state == core_playback.STARTING:
                return  # same debounce as the normal path below
            self.crop.toggle_mode()
            return

        state = self.playback.state

        if state == core_playback.PLAYING:
            self.pause_playback()
        elif state == core_playback.PAUSED:
            self.resume_playback()
        elif state == core_playback.STARTING:
            return
        else:
            self.start_preview()

    def start_preview(self):
        if not self.video_path:
            messagebox.showwarning("No video loaded", "Please load a video file first.")
            return

        if self.crop and self.crop.editing:
            self.crop.leave_edit_for_playback()

        if not FFMPEG:
            messagebox.showerror("Missing ffmpeg", "ffmpeg was not found.")
            return

        if self.playback_engine_name == engine_factory.ENGINE_FFPLAY and not FFPLAY:
            messagebox.showerror(
                "Missing ffplay",
                "ffplay was not found. The FFplay preview engine requires ffplay.exe.",
            )
            return

        if not IS_WINDOWS:
            messagebox.showerror(
                "Embedded preview unsupported",
                "Embedded preview in the app window is currently implemented for Windows.",
            )
            return

        tracks = self.superset_tracks()
        if not tracks:
            messagebox.showwarning(
                "No tracks selected", "Please select at least one audio track."
            )
            return

        start_seconds = self.current_seek_seconds()
        duration = self.total_duration_seconds or 0
        if duration and start_seconds >= duration - 0.1:
            # Playing from the very end restarts from the beginning, like any
            # media player (the seekbar parks at the end after EOF/export).
            start_seconds = 0.0

        self.hide_paused_frame()
        self.preview_placeholder.place_forget()
        self.set_status("Starting streaming preview...")
        self.log(f"Starting preview at {self.format_seconds(start_seconds)}.")

        self.playback.configure_media(self.video_path, self.total_duration_seconds)
        self.playback.play(start_seconds, tracks, self.preview_width, self.preview_height)

    def restart_playback_at(self, target_seconds: float):
        """Respawn the pipeline at a new position (seek commits, live-mix
        fallback). Whatever frame is on screen stays until the first new one."""
        if not self.video_path:
            return

        tracks = self.superset_tracks()
        if not tracks:
            return

        self.set_status("Seeking preview...")
        self.playback.play(target_seconds, tracks, self.preview_width, self.preview_height)

    def pause_playback(self):
        frame_stays_visible = self.playback.pause()

        if self.playback.state != core_playback.PAUSED:
            return

        position = self.playback.position
        self.set_seek_position(position)

        if frame_stays_visible:
            # FFplay itself is displaying the frozen frame; make sure no
            # stale overlay covers it.
            self.hide_paused_frame()
        else:
            # Pipeline had to be dropped; fetch a real frame for the overlay.
            self.preview_placeholder_var.set("Loading paused frame...")
            self.preview_placeholder.place(relx=0.5, rely=0.5, anchor="center")
            self.pending_still_request = self.playback.request_still(
                position, vf=self._crop_still_vf(position))

    def resume_playback(self):
        if self.crop and self.crop.editing:
            # Leaving the crop editor for live playback: drop the overlay so
            # the respawn shows the animated crop through the engine.
            self.crop.leave_edit_for_playback()

        self.playback.resume()

    def _mpv_wid(self):
        """HWND for the mpv engine to embed into (resolved at play time, on the
        UI thread). None before the workspace is built."""
        frame = getattr(self, "mpv_host_frame", None)
        return frame.winfo_id() if frame is not None else None

    def _live_scrub_active(self) -> bool:
        """True when the active engine can paint real frames during a paused
        scrub (mpv), so the app skips the ffmpeg still-extraction path. Never
        during crop editing (the editor draws Tk over a concealed window)."""
        return (
            self.playback.supports_live_scrub
            and self.playback.has_pipeline
            and not self.playback.concealed
            and not (self.crop and self.crop.editing)
        )

    def switch_playback_engine(self, name: str):
        """Tear down the current engine and build another (from Settings)."""
        name = engine_factory.normalize_engine_name(name)
        if name == self.playback_engine_name:
            return
        self.stop_preview()
        try:
            self.playback.shutdown()
        except Exception:
            pass
        self.playback, self.playback_engine_name = engine_factory.create_engine(
            name, self.make_playback_callbacks(), wid_provider=self._mpv_wid,
            mpv_cache_mb=self.settings.mpv_cache_mb,
        )
        self.seekbar.set_cache_ranges([])  # ffplay never emits; mpv repopulates
        if self.crop:
            self.playback.set_video_chain_provider(self.crop.preview_chain)
        if self.video_path:
            self.playback.configure_media(self.video_path, self.total_duration_seconds)
        self.refresh_playback_button_state()
        self.log(f"Playback engine: {self.playback_engine_name.upper()}.")

        if self.playback.state == core_playback.PLAYING:
            # In-place resume: the live window is already showing again.
            self.hide_paused_frame()
            self.preview_placeholder.place_forget()
        # Otherwise the engine respawned (long pause / dropped pipeline) and
        # the current still stays visible until the first new frame.

    def apply_mpv_cache_size(self, cache_mb: int):
        """Push a Settings cache-size change into a live mpv engine; a future
        engine build picks it up from settings via create_engine."""
        if hasattr(self.playback, "set_cache_size_mb"):
            self.playback.set_cache_size_mb(cache_mb)

    def make_playback_callbacks(self):
        """Bridges engine events onto the Tk thread. Synchronous events (the
        ones the engine raises from inside pause/resume/stop calls) run
        directly so the UI updates before the engine's next win32 step."""
        app = self

        class TkPlaybackCallbacks:
            def on_state(self, state: str) -> None:
                app.on_ui_thread(app.on_playback_state, state)

            def on_position(self, seconds: float) -> None:
                app.ui(app.on_playback_position, seconds)

            def on_window_ready(self, hwnd: int) -> None:
                app.ui(app.on_preview_window_ready)

            def on_embed_timeout(self) -> None:
                app.ui(
                    app.set_status,
                    "Preview is playing, but the video window could not be embedded.",
                )

            def on_first_frame(self) -> None:
                app.ui(app.on_preview_first_frame)

            def on_still_frame(self, kind, payload, width, height, request_id) -> None:
                app.on_ui_thread(
                    app.on_playback_still, kind, payload, width, height, request_id
                )

            def on_still_failed(self, request_id: int) -> None:
                app.ui(app.on_playback_still_failed, request_id)

            def on_pause_slipped(self) -> None:
                app.ui(app.on_pause_slipped)

            def on_cache_ranges(self, ranges) -> None:
                app.ui(app.on_playback_cache_ranges, ranges)

            def on_ended(self, at_seconds: float) -> None:
                app.ui(app.on_playback_ended, at_seconds)

            def on_error(self, title: str, message: str) -> None:
                app.ui(app.on_playback_error, title, message)

        return TkPlaybackCallbacks()

    def on_ui_thread(self, callback, *args):
        """Run now when already on the Tk thread, else marshal via after()."""
        if threading.current_thread() is threading.main_thread():
            callback(*args)
        else:
            self.ui(callback, *args)

    def on_playback_state(self, state: str):
        self.refresh_playback_button_state()

        if self.is_exporting:
            return

        if state == core_playback.STARTING:
            self.set_busy(True)
        elif state == core_playback.PLAYING:
            self.set_busy(True)
            self.set_status("Playing preview...")
        elif state == core_playback.PAUSED:
            self.set_busy(False)
            if not self.user_is_seeking:
                self.set_status(
                    f"Preview paused at {self.format_seconds(self.playback.position)}. Click Play to resume."
                )
        else:  # IDLE
            self.set_busy(False)

    def on_preview_window_ready(self):
        if not IS_WINDOWS:
            return

        parent_hwnd = self.preview_frame.winfo_id()
        width = max(1, self.preview_frame.winfo_width())
        height = max(1, self.preview_frame.winfo_height())

        if not self.playback.embed(parent_hwnd, width, height):
            if self.playback.is_active:
                self.set_status("Found preview window, but embedding failed.")

    def on_preview_first_frame(self):
        """First decoded frame is on screen: drop any held still and pin the
        window in place (FFplay repositions it once at first-frame time)."""
        self.hide_paused_frame()
        self.preview_placeholder.place_forget()
        self.schedule_anchor_burst()
        self.refresh_playback_button_state()

    def schedule_anchor_burst(self):
        for after_id in self.anchor_after_ids:
            try:
                self.root.after_cancel(after_id)
            except Exception:
                pass
        self.anchor_after_ids = []

        def anchor():
            width = max(1, self.preview_frame.winfo_width())
            height = max(1, self.preview_frame.winfo_height())
            self.playback.re_anchor(width, height)

        anchor()
        # FFplay's own first-frame reposition can land just after this event;
        # a couple of delayed re-anchors win that race without polling.
        for delay in (120, 400):
            self.anchor_after_ids.append(self.root.after(delay, anchor))

    def on_playback_still(self, kind, payload, width, height, request_id):
        if self.crop and self.crop.route_still(kind, payload, width, height, request_id):
            return

        if request_id == core_playback.PAUSE_STILL_REQUEST:
            # Synchronous pause capture: always show (the engine hides the
            # live window immediately after this returns).
            self.show_paused_frame_raw(payload, width, height)
            return

        # Async extracts: only the newest request while still paused matters.
        if request_id < self.pending_still_request:
            return
        if self.playback.state != core_playback.PAUSED:
            return

        if kind == core_playback.STILL_KIND_BGRA:
            self.show_paused_frame_raw(payload, width, height)
        else:
            self.show_paused_frame_from_bytes(payload)

    def on_playback_still_failed(self, request_id):
        if request_id < self.pending_still_request:
            return
        if self.playback.state != core_playback.PAUSED:
            return

        self.preview_placeholder_var.set("Paused. Click Play to resume preview.")
        self.preview_placeholder.place(relx=0.5, rely=0.5, anchor="center")

    def on_pause_slipped(self):
        """FFplay ignored the pause key; the engine dropped the pipeline at
        the position it actually stopped. Show a matching still."""
        if self.playback.state != core_playback.PAUSED:
            return

        position = self.playback.position
        self.set_seek_position(position)
        self.preview_placeholder_var.set("Loading paused frame...")
        self.preview_placeholder.place(relx=0.5, rely=0.5, anchor="center")
        self.pending_still_request = self.playback.request_still(
            position, vf=self._crop_still_vf(position))

    def loop_bounds(self) -> tuple[float, float] | None:
        """Return (start, end) of the active loop region, or None if looping
        is off. Loops the trim region when trim is set, else the whole clip."""
        if not self.loop_enabled_var.get():
            return None

        duration = self.total_duration_seconds or 0
        if duration <= 0:
            return None

        start, end = self.get_active_trim_points()
        start = start if start is not None else 0.0
        end = end if end is not None else duration
        if end - start < 0.05:
            return None
        return start, end

    def on_playback_position(self, seconds: float):
        bounds = self.loop_bounds()
        if bounds is not None and self.playback.state == core_playback.PLAYING:
            start, end = bounds
            # Small lead so the restart fires before the tail plays past the
            # out point (position callbacks arrive ~10 Hz).
            if seconds >= end - 0.08:
                self.set_seek_position(start)
                self.restart_playback_at(start)
                return
        self.set_seek_position(seconds)

    def on_playback_ended(self, at_seconds: float):
        bounds = self.loop_bounds()
        if bounds is not None and not self.is_exporting:
            start, _ = bounds
            self.set_seek_position(start)
            self.restart_playback_at(start)
            return

        self.set_seek_position(at_seconds)

        if not self.is_exporting and self.crop and self.crop.previewing:
            # A crop preview ran to the end — return to the editor so the box
            # is available again instead of leaving a box-less last frame.
            self.crop.on_playback_ended()
            self.set_busy(False)
            return

        self.refresh_playback_button_state()
        if not self.is_exporting:
            self.set_busy(False)
            self.set_status("Ready.")

    def on_playback_error(self, title: str, message: str):
        self.refresh_playback_button_state()
        if not self.is_exporting:
            self.set_busy(False)
        messagebox.showerror(title, message)

    def on_preview_frame_resize(self, event=None):
        try:
            if event is not None:
                self.preview_width = max(320, int(event.width))
                self.preview_height = max(180, int(event.height))
            else:
                self.preview_width = max(320, self.preview_frame.winfo_width())
                self.preview_height = max(180, self.preview_frame.winfo_height())
        except Exception:
            pass

        if not IS_WINDOWS:
            return

        self.playback.apply_size(self.preview_width, self.preview_height)

    def stop_preview(self):
        had_active_preview = self.playback.is_active

        if self.scrub_frame_after_id is not None:
            try:
                self.root.after_cancel(self.scrub_frame_after_id)
            except Exception:
                pass
            self.scrub_frame_after_id = None

        if self.live_mix_fallback_after_id is not None:
            try:
                self.root.after_cancel(self.live_mix_fallback_after_id)
            except Exception:
                pass
            self.live_mix_fallback_after_id = None

        if self.wheel_seek_after_id is not None:
            try:
                self.root.after_cancel(self.wheel_seek_after_id)
            except Exception:
                pass
            self.wheel_seek_after_id = None
        self.wheel_seek_resume = False

        for after_id in self.anchor_after_ids:
            try:
                self.root.after_cancel(after_id)
            except Exception:
                pass
        self.anchor_after_ids = []

        self.scrub_resume_pending = False
        self.last_scrub_frame_seconds = None
        self.hide_paused_frame()

        self.playback.stop()

        self.refresh_playback_button_state()

        if not self.is_exporting:
            self.set_busy(False)
            self.set_status("Preview stopped.")
            if had_active_preview:
                self.log("Preview stopped.")

    # ========================================================
    # Export
    # ========================================================

    def export_video_dialog(self):
        if not self.video_path:
            messagebox.showwarning("No video loaded", "Please load a video file first.")
            return

        if not FFMPEG:
            messagebox.showerror("Missing ffmpeg", "ffmpeg was not found.")
            return

        try:
            filter_complex = self.build_audio_filter()
        except ValueError as exc:
            messagebox.showwarning("No tracks selected", str(exc))
            return

        try:
            compression_target_mb = self.get_compression_target_mb()
        except ValueError as exc:
            messagebox.showwarning("Invalid compression target", str(exc))
            return

        compression_resolution_label = (
            self.get_compression_resolution_label()
            if compression_target_mb is not None
            else None
        )

        source = Path(self.video_path)

        OUTPUTS_DIR.mkdir(exist_ok=True)

        trim_start, trim_end = self.get_active_trim_points()

        crop_video_filter = self.crop.export_video_chain(trim_start) if self.crop else None
        crop_prefilter = self.crop.export_prefilter(trim_start) if self.crop else None
        crop_active = crop_video_filter is not None or crop_prefilter is not None

        trim_suffix = "_trimmed" if (trim_start is not None or trim_end is not None) else ""
        crop_suffix = "_crop" if crop_active else ""
        compression_suffix = (
            f"_compressed_{compression_target_mb:g}mb_{compression_resolution_label}"
            if compression_target_mb is not None
            else ""
        )
        default_output = OUTPUTS_DIR / f"{source.stem}_mixed_audio{trim_suffix}{crop_suffix}{compression_suffix}.mp4"

        output_path = filedialog.asksaveasfilename(
            title="Save merged video as",
            initialdir=str(OUTPUTS_DIR),
            initialfile=default_output.name,
            defaultextension=".mp4",
            filetypes=[
                ("MP4 video", "*.mp4"),
                ("MKV video", "*.mkv"),
                ("All files", "*.*"),
            ],
        )

        if not output_path:
            return

        output_path_obj = Path(output_path).resolve()

        if output_path_obj == source:
            messagebox.showerror(
                "Invalid output",
                "The output file cannot be the same as the source video.",
            )
            return

        if self.crop and self.crop.editing:
            self.crop.leave_edit_for_playback()

        self.stop_preview()

        self.update_trim_info()

        if crop_active:
            self.log(
                "Crop/zoom keyframes active: video will be re-encoded with "
                "H.265 NVENC (constant quality)."
            )

        self.is_exporting = True
        self.stop_export_button.config(state=tk.NORMAL)
        self.set_busy(True)

        if compression_target_mb is not None:
            self.set_status(f"Compressing merged video to under {compression_target_mb:g} MB (Windows/Explorer/Discord)...")
            self.log(
                f"Export requested with compression target under {compression_target_mb:g} MB "
                f"(Windows/Explorer/Discord) using H.265 NVENC, {compression_resolution_label} max resolution, "
                f"preserved FPS, and 64 kbps AAC audio."
            )
        elif trim_start is not None or trim_end is not None:
            self.set_status("Exporting trimmed merged video...")
            self.log("Export requested with trim enabled.")
        else:
            self.set_status("Exporting merged video...")
            self.log("Export requested.")

        if trim_start is not None or trim_end is not None:
            trim_start_text = self.format_seconds(trim_start) if trim_start is not None else "start"
            trim_end_text = self.format_seconds(trim_end) if trim_end is not None else "end"
            self.log(f"Trim range: {trim_start_text} to {trim_end_text}.")

        self.log(f"Output path: {output_path_obj}")

        self.export_thread = threading.Thread(
            target=core_export.run_export_job,
            args=(
                self.video_path,
                filter_complex,
                str(output_path_obj),
                trim_start,
                trim_end,
                compression_target_mb,
                compression_resolution_label,
                self.total_duration_seconds,
                self.make_export_callbacks(),
                lambda: not self.is_exporting,
                self.register_export_process,
                crop_video_filter,
                crop_prefilter,
            ),
            daemon=True,
        )
        self.export_thread.start()

    # ========================================================
    # Export execution (core) bridge
    # ========================================================

    def notify_export_attention(self):
        """Flashes the taskbar button when an export ends while the app is in
        the background, so a tabbed-away user knows to come back. Windows
        stops the flash on its own the moment the app is focused.

        Tk thread only (fetches the root HWND) — callers marshal via ui().
        """
        if not self.settings.notify_flash_taskbar or is_foreground_process():
            return
        flash_taskbar(chrome.get_root_hwnd(self.root), until_focused=True)

    def make_export_callbacks(self):
        """Bridges core export events onto the Tk thread with the same
        messages/dialogs the app has always shown."""
        app = self

        class TkExportCallbacks:
            def on_status(self, text: str) -> None:
                app.ui(app.set_status, text)

            def on_log(self, text: str) -> None:
                app.ui(app.log, text)

            def on_seek_to(self, seconds: float) -> None:
                app.ui(app.set_seek_position, seconds)

            def on_error(self, title: str, message: str) -> None:
                app.ui(app.notify_export_attention)
                app.ui(messagebox.showerror, title, message)

            def on_complete(self, output_path: str, size_bytes: int | None) -> None:
                app.ui(app.notify_export_attention)
                # Success is a toast with an action, not a modal — and the
                # folder opens on request instead of automatically.
                name = Path(output_path).name
                if size_bytes is None:
                    message = name
                else:
                    message = f"{name}\n{format_windows_discord_size(size_bytes)}"
                app.ui(
                    dialogs.toast,
                    "Export complete",
                    message,
                    "success",
                    "OPEN FOLDER",
                    lambda: app.reveal_file(output_path),
                    12000,
                )

            def on_finished(self) -> None:
                app.is_exporting = False
                app.ui(app.stop_export_button.config, state=tk.DISABLED)
                app.ui(app.set_busy, False)

        return TkExportCallbacks()

    def register_export_process(self, process: subprocess.Popen | None):
        self.export_process = process
        assign_process_to_cleanup_job(process)

    def cancel_export(self):
        if self.export_process is not None:
            try:
                self.export_process.terminate()
            except Exception:
                pass

        self.is_exporting = False
        self.stop_export_button.config(state=tk.DISABLED)
        self.set_status("Export cancelled.")

    def reveal_file(self, path: str):
        core_reveal_file(path)

    # ========================================================
    # Frame snapshot (save / save as / copy)
    # ========================================================

    def filename_timecode(self, seconds: float) -> str:
        seconds = max(0.0, float(seconds))
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        centis = int(round((seconds - int(seconds)) * 100)) % 100
        return f"{minutes:02d}m{secs:02d}s{centis:02d}"

    def snapshot_frame(self, mode: str):
        """mode: 'save' (outputs/ + toast), 'saveas' (dialog), 'copy' (clipboard)."""
        if not self.video_path or not FFMPEG:
            messagebox.showwarning("No clip", "Load a clip before saving a frame.")
            return

        seconds = self.current_seek_seconds()

        if mode == "saveas":
            stem = Path(self.video_path).stem
            dest = filedialog.asksaveasfilename(
                title="Save frame as",
                initialdir=str(OUTPUTS_DIR),
                initialfile=f"{stem}_frame_{self.filename_timecode(seconds)}.png",
                defaultextension=".png",
                filetypes=[("PNG image", "*.png"), ("JPEG image", "*.jpg"), ("All files", "*.*")],
            )
            if not dest:
                return
        elif mode == "save":
            OUTPUTS_DIR.mkdir(exist_ok=True)
            stem = Path(self.video_path).stem
            dest = str(OUTPUTS_DIR / f"{stem}_frame_{self.filename_timecode(seconds)}.png")
        else:  # copy
            dest = tempfile.NamedTemporaryFile(delete=False, suffix=".png").name

        self.set_status("Saving frame...")
        self.playback.save_frame(
            seconds, dest,
            lambda ok, path, mode=mode: self.ui(self.on_snapshot_done, ok, path, mode),
            vf=self.crop.snapshot_vf(seconds) if self.crop else None,
        )

    def on_snapshot_done(self, ok: bool, path: str, mode: str):
        if not ok:
            self.set_status("Frame capture failed.")
            messagebox.showerror("Frame capture failed",
                                 "FFmpeg could not extract the current frame.")
            return

        if mode == "copy":
            copied = self.copy_image_to_clipboard(path)
            try:
                Path(path).unlink(missing_ok=True)
            except Exception:
                pass
            if copied:
                self.set_status("Frame copied to clipboard.")
                self.log("Frame copied to clipboard.")
                dialogs.toast("Frame copied", "Paste it anywhere (e.g. Discord).", "success")
            else:
                self.set_status("Could not copy frame to clipboard.")
                messagebox.showerror("Clipboard error", "Could not copy the frame to the clipboard.")
            return

        # save / saveas
        name = Path(path).name
        self.set_status(f"Frame saved: {name}")
        self.log(f"Frame saved: {path}")
        dialogs.toast("Frame saved", name, "success", "OPEN FOLDER",
                      lambda p=path: self.reveal_file(p), 8000)

    def copy_image_to_clipboard(self, image_path: str) -> bool:
        if not PIL_AVAILABLE:
            return False
        try:
            image = Image.open(image_path).convert("RGB")
            buffer = BytesIO()
            image.save(buffer, "BMP")
            # Strip the 14-byte BITMAPFILEHEADER to get a CF_DIB payload.
            return set_clipboard_dib(buffer.getvalue()[14:])
        except Exception:
            return False

    # ========================================================
    # Closing
    # ========================================================

    def on_close(self):
        self.stop_preview()

        if self.export_process is not None:
            should_quit = messagebox.askyesno(
                "Export in progress",
                "An export is still running. Quit anyway?",
            )

            if not should_quit:
                return

            try:
                self.export_process.terminate()
            except Exception:
                pass

        self.persist_video_session()
        self.save_settings()
        self.playback.shutdown()
        self.root.destroy()

    # ========================================================
    # Utility
    # ========================================================

    format_seconds = staticmethod(core_format_seconds)


# ============================================================
# Command-line / Open With support
# ============================================================

def get_startup_file_from_args() -> str | None:
    """
    Windows "Open with" passes the selected file as sys.argv[1].

    Example:
        ClipToolbox.exe "C:\\Videos\\movie.mp4"
    """
    if len(sys.argv) <= 1:
        return None

    possible_file = Path(sys.argv[1]).resolve()

    if possible_file.exists() and possible_file.is_file():
        return str(possible_file)

    return None


def create_root_window():
    global DND_AVAILABLE

    if not DND_AVAILABLE:
        root = tk.Tk()
    else:
        try:
            root = TkinterDnD.Tk()
        except Exception as exc:
            DND_AVAILABLE = False

            root = tk.Tk()
            root.withdraw()

            tk_messagebox.showerror(
                "Drag and drop failed",
                "Drag and drop could not start because the tkdnd library could not be loaded.\n\n"
                "This usually means tkinterdnd2 was not packaged correctly.\n\n"
                "Rebuild with:\n"
                "pyinstaller --collect-all tkinterdnd2 ...\n\n"
                f"Details:\n{exc}",
            )

            root.deiconify()

    icon_path = get_app_icon_path()
    if icon_path and IS_WINDOWS:
        try:
            root.iconbitmap(default=icon_path)
        except Exception:
            pass

    return root


def main():
    startup_file = get_startup_file_from_args()

    dpi.init()
    fonts.load_private_fonts()

    root = create_root_window()
    fonts.verify_with_tk(root)

    app = HaloApp(root)

    if startup_file:
        root.after(250, lambda: app.load_video(startup_file))

    root.mainloop()


if __name__ == "__main__":
    main()


def main():
    startup_file = get_startup_file_from_args()

    dpi.init()
    fonts.load_private_fonts()

    root = create_root_window()
    fonts.verify_with_tk(root)

    app = HaloApp(root)

    if startup_file:
        root.after(250, lambda: app.load_video(startup_file))

    root.mainloop()


if __name__ == "__main__":
    main()
