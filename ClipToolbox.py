import ctypes
import json
import os
import shutil
import subprocess
import sys
import tempfile
from io import BytesIO
import threading
import time
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except Exception:
    Image = None
    ImageTk = None
    PIL_AVAILABLE = False


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
PREVIEW_HEIGHT_SCALE = 1.042

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

    return Path(__file__).resolve().parent


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


def ffplay_start_env() -> dict:
    """
    Start FFplay's SDL window offscreen so Windows does not show the temporary
    white SDL window in the middle of the desktop before we re-parent it.
    """
    env = os.environ.copy()
    env["SDL_VIDEO_WINDOW_POS"] = "-32000,-32000"
    env["SDL_VIDEO_CENTERED"] = "0"
    return env


if FFMPEG_BIN_DIR.exists():
    os.environ["PATH"] = str(FFMPEG_BIN_DIR) + os.pathsep + os.environ.get("PATH", "")

FFMPEG = find_tool("ffmpeg")
FFPROBE = find_tool("ffprobe")
FFPLAY = find_tool("ffplay")


# ============================================================
# tkinterdnd2 setup
# ============================================================

TKDND_CANDIDATE_DIRS = [
    RESOURCE_DIR / "tkdnd2.8",
    RESOURCE_DIR / "tkinterdnd2" / "tkdnd",
    RESOURCE_DIR / "tkinterdnd2" / "tkdnd2.8",
    BASE_DIR / "tkdnd2.8",
    INTERNAL_DIR / "tkinterdnd2" / "tkdnd",
    INTERNAL_DIR / "tkinterdnd2" / "tkdnd2.8",
    INTERNAL_DIR / "tkdnd2.8",
]

for possible_tkdnd_dir in TKDND_CANDIDATE_DIRS:
    if possible_tkdnd_dir.exists():
        os.environ["TKDND_LIBRARY"] = str(possible_tkdnd_dir)
        break

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES

    DND_AVAILABLE = True
except Exception:
    TkinterDnD = None
    DND_FILES = None
    DND_AVAILABLE = False


# ============================================================
# Windows native window helpers
# ============================================================

if IS_WINDOWS:
    user32 = ctypes.windll.user32

    EnumWindows = user32.EnumWindows
    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    IsWindow = user32.IsWindow
    IsWindowVisible = user32.IsWindowVisible
    GetWindowThreadProcessId = user32.GetWindowThreadProcessId
    GetParent = user32.GetParent
    GetWindowTextLengthW = user32.GetWindowTextLengthW
    GetWindowTextW = user32.GetWindowTextW
    GetClassNameW = user32.GetClassNameW

    SetParent = user32.SetParent
    MoveWindow = user32.MoveWindow
    ShowWindow = user32.ShowWindow
    BringWindowToTop = user32.BringWindowToTop
    UpdateWindow = user32.UpdateWindow
    SetFocus = user32.SetFocus

    if hasattr(user32, "GetWindowLongPtrW"):
        GetWindowLongPtrW = user32.GetWindowLongPtrW
        SetWindowLongPtrW = user32.SetWindowLongPtrW
    else:
        GetWindowLongPtrW = user32.GetWindowLongW
        SetWindowLongPtrW = user32.SetWindowLongW

    SetWindowPos = user32.SetWindowPos
    PostMessageW = user32.PostMessageW

    GWL_STYLE = -16
    GWL_EXSTYLE = -20

    WS_CHILD = 0x40000000
    WS_VISIBLE = 0x10000000
    WS_CAPTION = 0x00C00000
    WS_THICKFRAME = 0x00040000
    WS_MINIMIZEBOX = 0x00020000
    WS_MAXIMIZEBOX = 0x00010000
    WS_SYSMENU = 0x00080000
    WS_POPUP = 0x80000000
    WS_CLIPSIBLINGS = 0x04000000
    WS_CLIPCHILDREN = 0x02000000

    WS_EX_APPWINDOW = 0x00040000
    WS_EX_TOOLWINDOW = 0x00000080

    SW_HIDE = 0
    SW_SHOW = 5
    SW_RESTORE = 9

    SWP_NOZORDER = 0x0004
    SWP_NOACTIVATE = 0x0010
    SWP_FRAMECHANGED = 0x0020
    SWP_SHOWWINDOW = 0x0040

    WM_KEYDOWN = 0x0100
    WM_KEYUP = 0x0101
    VK_SPACE = 0x20

    kernel32 = ctypes.windll.kernel32
    ntdll = ctypes.windll.ntdll

    PROCESS_SUSPEND_RESUME = 0x0800
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

    OpenProcess = kernel32.OpenProcess
    OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_bool, ctypes.c_ulong]
    OpenProcess.restype = ctypes.c_void_p

    CloseHandle = kernel32.CloseHandle
    CloseHandle.argtypes = [ctypes.c_void_p]
    CloseHandle.restype = ctypes.c_bool

    NtSuspendProcess = ntdll.NtSuspendProcess
    NtSuspendProcess.argtypes = [ctypes.c_void_p]
    NtSuspendProcess.restype = ctypes.c_long

    NtResumeProcess = ntdll.NtResumeProcess
    NtResumeProcess.argtypes = [ctypes.c_void_p]
    NtResumeProcess.restype = ctypes.c_long


def _window_text(hwnd: int) -> str:
    if not IS_WINDOWS:
        return ""

    length = GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""

    buf = ctypes.create_unicode_buffer(length + 1)
    GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def _window_class(hwnd: int) -> str:
    if not IS_WINDOWS:
        return ""

    buf = ctypes.create_unicode_buffer(256)
    GetClassNameW(hwnd, buf, 256)
    return buf.value


def find_main_window_for_pid(pid: int) -> int | None:
    """
    Finds the top-level SDL/FFplay window owned by a process ID.

    This avoids fragile title matching and fixes the issue where FFplay opens
    as a separate window instead of being embedded into the Tk preview frame.
    """
    if not IS_WINDOWS:
        return None

    candidates: list[tuple[int, str, str]] = []

    def callback(hwnd, _):
        if not IsWindow(hwnd):
            return True

        found_pid = ctypes.c_ulong()
        GetWindowThreadProcessId(hwnd, ctypes.byref(found_pid))

        if found_pid.value != pid:
            return True

        # Only top-level windows.
        if GetParent(hwnd):
            return True

        class_name = _window_class(hwnd)
        title = _window_text(hwnd)
        visible = bool(IsWindowVisible(hwnd))

        # FFplay uses SDL windows. Prefer visible SDL windows, but collect any
        # top-level pid-owned window so we can still embed if the window is not
        # marked visible yet.
        if visible or "SDL" in class_name or title:
            candidates.append((hwnd, class_name, title))

        return True

    EnumWindows(EnumWindowsProc(callback), 0)

    if not candidates:
        return None

    # Prefer SDL windows first.
    for hwnd, class_name, title in candidates:
        if "SDL" in class_name:
            return hwnd

    return candidates[0][0]


def embed_external_window(child_hwnd: int, parent_hwnd: int, width: int, height: int):
    """
    Re-parents an external native window into a Tkinter frame.

    Important: this uses GetWindowLongPtr/SetWindowLongPtr instead of
    GetWindowLong/SetWindowLong. On 64-bit Windows the old functions can fail
    to update styles correctly, which is a common reason FFplay stays outside
    the app.
    """
    if not IS_WINDOWS or not child_hwnd or not parent_hwnd:
        return False

    if not IsWindow(child_hwnd):
        return False

    width = max(1, int(width))
    height = max(1, int(height))

    ShowWindow(child_hwnd, SW_HIDE)

    style = GetWindowLongPtrW(child_hwnd, GWL_STYLE)
    ex_style = GetWindowLongPtrW(child_hwnd, GWL_EXSTYLE)

    style &= ~WS_POPUP
    style &= ~WS_CAPTION
    style &= ~WS_THICKFRAME
    style &= ~WS_MINIMIZEBOX
    style &= ~WS_MAXIMIZEBOX
    style &= ~WS_SYSMENU

    style |= WS_CHILD
    style |= WS_VISIBLE
    style |= WS_CLIPSIBLINGS
    style |= WS_CLIPCHILDREN

    ex_style &= ~WS_EX_APPWINDOW
    ex_style |= WS_EX_TOOLWINDOW

    SetWindowLongPtrW(child_hwnd, GWL_STYLE, style)
    SetWindowLongPtrW(child_hwnd, GWL_EXSTYLE, ex_style)

    old_parent = SetParent(child_hwnd, parent_hwnd)

    SetWindowPos(
        child_hwnd,
        0,
        0,
        0,
        width,
        height,
        SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED | SWP_SHOWWINDOW,
    )

    MoveWindow(child_hwnd, 0, 0, width, height, True)
    ShowWindow(child_hwnd, SW_SHOW)
    BringWindowToTop(child_hwnd)
    UpdateWindow(child_hwnd)

    return True


def send_space_to_window(hwnd: int):
    """
    Toggles FFplay pause/play by sending Space to its embedded SDL window.

    This is kept as a fallback only. Some SDL/FFplay builds ignore posted
    keyboard messages after the window has been re-parented into Tk.
    """
    if not IS_WINDOWS or not hwnd:
        return

    try:
        SetFocus(hwnd)
        PostMessageW(hwnd, WM_KEYDOWN, VK_SPACE, 0)
        PostMessageW(hwnd, WM_KEYUP, VK_SPACE, 0)
    except Exception:
        pass


def set_process_suspended(process: subprocess.Popen | None, suspended: bool) -> bool:
    """Pause/resume FFplay by suspending/resuming its process on Windows."""
    if not IS_WINDOWS or process is None or process.poll() is not None:
        return False

    access = PROCESS_SUSPEND_RESUME | PROCESS_QUERY_LIMITED_INFORMATION
    handle = OpenProcess(access, False, process.pid)

    if not handle:
        return False

    try:
        result = NtSuspendProcess(handle) if suspended else NtResumeProcess(handle)
        return result == 0
    except Exception:
        return False
    finally:
        try:
            CloseHandle(handle)
        except Exception:
            pass


def hide_native_window(hwnd: int | None):
    if not IS_WINDOWS or not hwnd:
        return

    try:
        if IsWindow(hwnd):
            ShowWindow(hwnd, SW_HIDE)
    except Exception:
        pass


# ============================================================
# Main app
# ============================================================

class AudioTrackMergerApp:
    def __init__(self, root: tk.Tk):
        self.root = root

        self.video_path: str | None = None
        self.audio_metadata: list[dict] = []
        self.track_controls: list[tuple[int, tk.BooleanVar, ttk.Scale]] = []

        self.total_duration_seconds: float | None = None

        self.trim_enabled_var = tk.BooleanVar(value=False)
        self.trim_start_seconds: float | None = None
        self.trim_end_seconds: float | None = None

        self.compress_enabled_var = tk.BooleanVar(value=False)
        self.compression_target_var = tk.StringVar(value=f"{DEFAULT_COMPRESSION_TARGET_MB:g}")
        self.compression_resolution_var = tk.StringVar(value=DEFAULT_COMPRESSION_RESOLUTION)
        self.volume_log_after_ids: dict[int, str] = {}

        self.preview_thread: threading.Thread | None = None
        self.export_thread: threading.Thread | None = None

        self.preview_process: subprocess.Popen | None = None
        self.preview_generation_process: subprocess.Popen | None = None
        self.export_process: subprocess.Popen | None = None

        self.preview_stop_requested = False
        self.preview_session_id = 0
        self.preview_temp_path: str | None = None
        self.preview_temp_is_ready = False
        self.preview_filter_signature: str | None = None
        self.preview_refresh_after_id: str | None = None
        self.preview_refresh_pending = False

        self.preview_hwnd: int | None = None
        self.preview_start_position = 0.0
        self.preview_started_at_monotonic: float | None = None

        self.preview_paused = False
        self.pause_started_at_monotonic: float | None = None
        self.total_pause_seconds = 0.0
        self.preview_should_resume_paused = False
        self.paused_seek_without_process = False
        self.paused_frame_process: subprocess.Popen | None = None
        self.paused_frame_image = None
        self.paused_frame_label: tk.Label | None = None
        self.scrub_frame_after_id = None
        self.scrub_frame_request_id = 0
        self.last_scrub_frame_seconds: float | None = None

        self.user_is_seeking = False
        self.is_exporting = False
        self.is_generating_preview = False
        self.auto_preview_after_load = True
        self.preview_width = PREVIEW_WIDTH
        self.preview_height = PREVIEW_HEIGHT

        self.build_ui()
        self.enable_drag_and_drop()
        self.startup_checks()

    # ========================================================
    # Thread-safe UI helpers
    # ========================================================

    def ui(self, callback, *args, **kwargs):
        self.root.after(0, lambda: callback(*args, **kwargs))

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

        # Legacy hidden pause button is kept only so older code paths can safely
        # call .config() on it while the visible UI uses one playback button.
        if hasattr(self, "play_pause_button"):
            self.play_pause_button.config(state=tk.DISABLED)

        # Keep audio sliders live while previewing so users can adjust the mix
        # and let the debounced preview refresh pick up the new levels. During
        # export, however, controls stay locked to avoid changing an in-flight
        # render.
        keep_sliders_live = (
            busy
            and not self.is_exporting
            and (
                self.preview_process is not None
                or self.preview_generation_process is not None
                or self.is_generating_preview
            )
        )

        slider_state = tk.NORMAL if keep_sliders_live else state

        for _, _, slider in self.track_controls:
            slider.config(state=slider_state)

    def refresh_playback_button_state(self):
        """Keep the single visible playback button in sync with preview state."""
        if not hasattr(self, "preview_button"):
            return

        if self.is_exporting:
            self.preview_button.config(text="Play", state=tk.DISABLED)
            return

        if self.paused_seek_without_process or self.preview_paused:
            self.preview_button.config(text="Play", state=tk.NORMAL)
            return

        preview_starting_or_seeking = (
            self.is_generating_preview
            or self.preview_generation_process is not None
            or (self.preview_process is not None and self.preview_hwnd is None)
        )

        if preview_starting_or_seeking:
            self.preview_button.config(text="Loading...", state=tk.DISABLED)
            return

        if self.preview_process is not None and self.preview_hwnd is not None:
            self.preview_button.config(text="Pause", state=tk.NORMAL)
            return

        if self.video_path:
            self.preview_button.config(text="Play", state=tk.NORMAL)
        else:
            self.preview_button.config(text="Play", state=tk.DISABLED)

    # ========================================================
    # UI construction
    # ========================================================

    def setup_styles(self):
        """
        Use a slimmer seekbar thumb than the default Windows ttk scale.

        ttk scale styling is theme-dependent, so this keeps the rest of the app
        native while only shrinking the horizontal Scale slider element used by
        the timeline seekbar.
        """
        try:
            style = ttk.Style(self.root)

            # Clone the current horizontal scale layout but use a smaller
            # slider element when the active theme supports element_create.
            style.configure(
                "Slim.Horizontal.TScale",
                sliderlength=10,
                sliderthickness=8,
                troughrelief="flat",
            )
        except Exception:
            pass

    def build_ui(self):
        self.root.title(f"{APP_NAME} - {APP_VERSION}" if APP_VERSION else APP_NAME)
        self.root.geometry(f"{DEFAULT_WINDOW_WIDTH}x{DEFAULT_WINDOW_HEIGHT}")
        self.root.minsize(MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT)

        self.setup_styles()

        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)

        top = ttk.Frame(outer)
        top.pack(fill=tk.X)

        self.load_button = ttk.Button(
            top,
            text="Load Video File",
            command=self.load_video_dialog,
        )
        self.load_button.pack(side=tk.LEFT)

        self.file_label_var = tk.StringVar(value="No video loaded")
        self.file_label = ttk.Label(top, textvariable=self.file_label_var)
        self.file_label.pack(side=tk.LEFT, padx=12, fill=tk.X, expand=True)

        self.track_container = ttk.LabelFrame(outer, text="Audio tracks")
        self.track_container.pack(fill=tk.X, expand=False, pady=(12, 8))
        self.track_container.columnconfigure(0, weight=1)

        self.track_canvas = tk.Canvas(self.track_container, highlightthickness=0, height=76)
        self.track_scrollbar = ttk.Scrollbar(
            self.track_container,
            orient=tk.VERTICAL,
            command=self.track_canvas.yview,
        )
        self.track_frame = ttk.Frame(self.track_canvas)
        self.track_frame.columnconfigure(0, weight=1)

        self.track_window = self.track_canvas.create_window(
            (0, 0),
            window=self.track_frame,
            anchor="nw",
        )

        def _sync_track_scrollregion(event=None):
            self.track_canvas.configure(scrollregion=self.track_canvas.bbox("all"))
            self.track_canvas.itemconfigure(
                self.track_window,
                width=max(1, self.track_canvas.winfo_width()),
            )

        self.track_frame.bind("<Configure>", _sync_track_scrollregion)

        self.track_canvas.bind(
            "<Configure>",
            lambda event: self.track_canvas.itemconfigure(
                self.track_window,
                width=event.width,
            ),
        )

        self.track_canvas.configure(yscrollcommand=self.track_scrollbar.set)

        self.track_canvas.grid(row=0, column=0, sticky="ew")
        self.track_scrollbar.grid(row=0, column=1, sticky="ns")
        self.track_scrollbar.grid_remove()

        self.preview_container = ttk.LabelFrame(outer, text="Video preview")
        self.preview_container.pack(fill=tk.X, expand=False, pady=(8, 8))

        # The preview is intentionally 16:9-ish and narrower than the original
        # layout. Most target videos are 16:9, and keeping this frame fixed
        # prevents the window from becoming unnecessarily wide.
        self.preview_frame = tk.Frame(self.preview_container, bg="black", width=PREVIEW_WIDTH, height=PREVIEW_HEIGHT)
        self.preview_frame.pack(fill=tk.X, expand=False, padx=4, pady=4)
        self.preview_frame.pack_propagate(False)

        self.preview_placeholder_var = tk.StringVar(
            value="Load a video, choose tracks, then click Preview."
        )
        self.preview_placeholder = tk.Label(
            self.preview_frame,
            textvariable=self.preview_placeholder_var,
            fg="white",
            bg="black",
            borderwidth=0,
            highlightthickness=0,
        )
        self.preview_placeholder.place(relx=0.5, rely=0.5, anchor="center")

        self.paused_frame_label = tk.Label(
            self.preview_frame,
            bg="black",
            borderwidth=0,
            highlightthickness=0,
        )
        self.paused_frame_label.place_forget()

        self.preview_frame.bind("<Configure>", self.on_preview_frame_resize)

        timeline = ttk.Frame(outer)
        timeline.pack(fill=tk.X, pady=(9, 6))

        self.time_left_var = tk.StringVar(value="0:00")
        self.time_right_var = tk.StringVar(value="0:00")

        self.time_left_label = ttk.Label(timeline, textvariable=self.time_left_var, width=8)
        self.time_left_label.pack(side=tk.LEFT)

        self.seek_var = tk.DoubleVar(value=0)

        # Use tk.Scale instead of ttk.Scale for the seekbar because Windows
        # ttk themes ignore sliderlength/sliderthickness. tk.Scale gives us
        # real control over the blue handle size.
        self.seekbar = tk.Scale(
            timeline,
            from_=0,
            to=100,
            orient=tk.HORIZONTAL,
            variable=self.seek_var,
            command=self.on_seek_drag,
            showvalue=False,
            sliderlength=14,
            width=16,
            borderwidth=0,
            highlightthickness=0,
            resolution=0.01,
        )
        self.seekbar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)

        # Visible trim indicators are overlaid on the seekbar so trim points
        # are obvious while scrubbing.
        self.seekbar.bind("<Configure>", lambda event: self.update_trim_markers())
        self.seekbar.bind("<Map>", lambda event: self.update_trim_markers())

        self.time_right_label = ttk.Label(timeline, textvariable=self.time_right_var, width=8)
        self.time_right_label.pack(side=tk.RIGHT)

        self.seekbar.bind("<ButtonPress-1>", self.on_seek_press)
        self.seekbar.bind("<ButtonRelease-1>", self.on_seek_release)

        # Hidden legacy canvas placeholder. Earlier versions drew a trim range
        # line here, but it could get re-packed near the bottom of the window.
        # Markers are now drawn only as overlay widgets above the seekbar.
        self.trim_marker_layer = tk.Canvas(
            outer,
            height=0,
            highlightthickness=0,
            borderwidth=0,
        )

        trim_controls = ttk.Frame(outer)
        trim_controls.pack(fill=tk.X, pady=(0, 6))

        self.trim_checkbox = ttk.Checkbutton(
            trim_controls,
            text="Trim video",
            variable=self.trim_enabled_var,
            command=self.on_trim_toggle,
        )
        self.trim_checkbox.pack(side=tk.LEFT)

        self.trim_buttons_frame = ttk.Frame(trim_controls)
        self.trim_buttons_frame.pack(side=tk.LEFT, padx=(10, 0))

        self.trim_start_button = ttk.Button(
            self.trim_buttons_frame,
            text="Trim Start",
            command=self.set_trim_start,
        )
        self.trim_start_button.pack(side=tk.LEFT)

        self.trim_end_button = ttk.Button(
            self.trim_buttons_frame,
            text="Trim End",
            command=self.set_trim_end,
        )
        self.trim_end_button.pack(side=tk.LEFT, padx=(6, 0))

        self.clear_trim_button = ttk.Button(
            self.trim_buttons_frame,
            text="Clear Trim",
            command=self.clear_trim_points,
        )
        self.clear_trim_button.pack(side=tk.LEFT, padx=(6, 0))

        self.trim_info_var = tk.StringVar(value="")
        self.trim_info_label = ttk.Label(trim_controls, textvariable=self.trim_info_var)
        self.trim_info_label.pack(side=tk.LEFT, padx=(10, 0))

        self.trim_buttons_frame.pack_forget()
        self.trim_marker_layer.pack_forget()

        compression_controls = ttk.Frame(outer)
        compression_controls.pack(fill=tk.X, pady=(0, 6))

        self.compress_checkbox = ttk.Checkbutton(
            compression_controls,
            text="Compress video",
            variable=self.compress_enabled_var,
            command=self.on_compression_toggle,
        )
        self.compress_checkbox.pack(side=tk.LEFT)

        self.compression_options_frame = ttk.Frame(compression_controls)
        self.compression_options_frame.pack(side=tk.LEFT, padx=(10, 0))

        ttk.Label(self.compression_options_frame, text="Target size:").pack(side=tk.LEFT)
        self.compression_target_entry = ttk.Entry(
            self.compression_options_frame,
            textvariable=self.compression_target_var,
            width=6,
        )
        self.compression_target_entry.pack(side=tk.LEFT, padx=(6, 4))
        ttk.Label(self.compression_options_frame, text="MB max (Windows/Discord)").pack(side=tk.LEFT)

        ttk.Label(self.compression_options_frame, text="Max res:").pack(side=tk.LEFT, padx=(12, 4))
        self.compression_resolution_combo = ttk.Combobox(
            self.compression_options_frame,
            textvariable=self.compression_resolution_var,
            values=list(COMPRESSION_RESOLUTION_PRESETS.keys()),
            width=7,
            state="readonly",
        )
        self.compression_resolution_combo.pack(side=tk.LEFT)
        self.compression_resolution_combo.bind("<<ComboboxSelected>>", self.on_compression_resolution_changed)

        self.compression_options_frame.pack_forget()

        controls = ttk.Frame(outer)
        controls.pack(fill=tk.X, pady=(4, 8))

        self.preview_button = ttk.Button(
            controls,
            text="Play",
            command=self.toggle_preview,
            state=tk.DISABLED,
        )
        self.preview_button.pack(side=tk.LEFT)

        # Hidden compatibility placeholder. Playback now uses the single visible
        # Play/Pause button above, but older internal code paths still reference
        # play_pause_button for state cleanup. Do not pack this widget.
        self.play_pause_button = ttk.Button(
            controls,
            text="Pause",
            command=self.toggle_play_pause,
            state=tk.DISABLED,
        )

        self.export_button = ttk.Button(
            controls,
            text="Export Merged Video",
            command=self.export_video_dialog,
        )
        self.export_button.pack(side=tk.LEFT, padx=8)

        # Export cancellation is intentionally not exposed in the UI.
        # Keep a disabled placeholder attribute so existing export state code
        # can safely call .config(...) without special cases.
        self.stop_export_button = ttk.Button(
            controls,
            text="Cancel Export",
            command=self.cancel_export,
            state=tk.DISABLED,
        )

        self.status_var = tk.StringVar(value="Ready")
        self.status_label = ttk.Label(outer, textvariable=self.status_var, anchor="w")
        self.status_label.pack(fill=tk.X)

        self.log_container = ttk.LabelFrame(outer, text="Activity log")
        self.log_container.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        self.log_container.columnconfigure(0, weight=1)
        self.log_container.rowconfigure(0, weight=1)

        self.log_text = tk.Text(
            self.log_container,
            height=5,
            wrap=tk.WORD,
            state=tk.DISABLED,
            borderwidth=0,
            highlightthickness=0,
        )
        self.log_scrollbar = ttk.Scrollbar(
            self.log_container,
            orient=tk.VERTICAL,
            command=self.log_text.yview,
        )
        self.log_text.configure(yscrollcommand=self.log_scrollbar.set)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        self.log_scrollbar.grid(row=0, column=1, sticky="ns")

        # Keep the variable for error reporting, but do not show the old
        # drag/drop/open-with hint at the bottom of the app.
        self.dnd_hint_var = tk.StringVar(value="")
        self.dnd_hint_label = ttk.Label(outer, textvariable=self.dnd_hint_var, anchor="w")

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.refresh_playback_button_state()

    def enable_drag_and_drop(self):
        if not DND_AVAILABLE:
            return

        try:
            self.root.drop_target_register(DND_FILES)
            self.root.dnd_bind("<<Drop>>", self.drop_video)
        except Exception as exc:
            self.dnd_hint_var.set(f"Drag and drop failed to initialize: {exc}")

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

    # ========================================================
    # Loading files
    # ========================================================

    def load_video_dialog(self):
        path = filedialog.askopenfilename(
            title="Select video file",
            filetypes=[
                ("Video files", "*.mp4 *.mov *.mkv *.avi *.webm *.m4v"),
                ("All files", "*.*"),
            ],
        )

        if path:
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

        self.stop_preview()
        self.cleanup_preview_temp_file()

        self.video_path = str(path_obj)
        self.file_label_var.set(path_obj.name)
        self.clear_tracks()
        self.set_seek_range(0)
        self.clear_trim_points(silent=True)
        self.preview_placeholder_var.set("Preparing file...")
        self.preview_placeholder.place(relx=0.5, rely=0.5, anchor="center")
        self.play_pause_button.config(state=tk.DISABLED, text="Pause")
        self.refresh_playback_button_state()
        self.set_status("Reading audio streams...")
        self.log(f"Loaded video: {path_obj.name}")
        self.log("Reading audio streams and duration...")

        def worker():
            streams = self.get_audio_streams(str(path_obj))
            duration = self.get_media_duration(str(path_obj))
            self.ui(self.after_probe, streams, duration)

        threading.Thread(target=worker, daemon=True).start()

    def after_probe(self, streams: list[dict], duration: float | None):
        self.audio_metadata = streams
        self.total_duration_seconds = duration
        self.set_seek_range(duration)
        self.update_trim_controls()

        self.clear_tracks()

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

        duration_text = self.format_seconds(duration) if duration else "unknown duration"
        self.preview_placeholder_var.set("Starting preview...")
        self.preview_placeholder.place(relx=0.5, rely=0.5, anchor="center")
        self.set_status(f"Loaded {len(streams)} audio track(s), {duration_text}. Starting preview...")
        self.log(f"Found {len(streams)} audio track(s). Duration: {duration_text}.")

        for info in streams:
            self.log(f"Audio stream available: {info['label']}")

        if self.auto_preview_after_load:
            self.root.after(300, self.start_preview)

    def clear_tracks(self):
        self.track_controls.clear()

        for widget in self.track_frame.winfo_children():
            widget.destroy()

        self.update_track_area_height(0)

    def update_track_area_height(self, track_count: int):
        # Keep the track list only as tall as the rows it actually needs.
        # The canvas must not vertically expand, otherwise a 2-track file leaves
        # a large blank area and pushes the preview controls off-screen.
        visible_rows = min(max(track_count, 1), 4)
        row_height = 34
        canvas_height = 8 + (visible_rows * row_height)

        self.track_canvas.configure(height=canvas_height)
        self.track_container.configure(height=canvas_height + 24)

        if track_count > 4:
            if not self.track_scrollbar.winfo_ismapped():
                self.track_scrollbar.grid()
        else:
            if self.track_scrollbar.winfo_ismapped():
                self.track_scrollbar.grid_remove()

        # Recompute a practical initial window height. It grows for 3-4 tracks,
        # but stops growing after that because the list scrolls.
        target_height = WINDOW_AUTO_HEIGHT_BASE + canvas_height
        current_width = DEFAULT_WINDOW_WIDTH
        self.root.geometry(f"{current_width}x{target_height}")
        self.root.update_idletasks()
        self.track_canvas.itemconfigure(
            self.track_window,
            width=max(1, self.track_canvas.winfo_width()),
        )

    def add_track_row(self, row_number: int, info: dict):
        row = ttk.Frame(self.track_frame, padding=(8, 2))
        row.grid(row=row_number, column=0, sticky="ew")
        row.columnconfigure(1, weight=1, minsize=AUDIO_SLIDER_MIN_WIDTH)

        var = tk.BooleanVar(value=True)
        var.trace_add("write", lambda *args: self.invalidate_preview())

        checkbox = ttk.Checkbutton(row, text=info["label"], variable=var)
        checkbox.grid(row=0, column=0, sticky="w", padx=(0, 8))

        volume_label_var = tk.StringVar(value="100%")

        slider = tk.Scale(
            row,
            from_=0.0,
            to=2.0,
            orient=tk.HORIZONTAL,
            length=AUDIO_SLIDER_PIXEL_LENGTH,
            showvalue=False,
            sliderlength=14,
            width=16,
            borderwidth=0,
            highlightthickness=0,
            resolution=0.01,
        )
        slider.set(1.0)

        def on_volume_change(value, label_var=volume_label_var):
            try:
                percentage = int(float(value) * 100)
                label_var.set(f"{percentage}%")
            except Exception:
                label_var.set("100%")

            try:
                self.schedule_volume_log(info["index"], info["label"], percentage)
            except Exception:
                pass

            self.invalidate_preview()

        slider.config(command=on_volume_change)
        slider.grid(row=0, column=1, sticky="ew", padx=(4, 8))

        volume_label = ttk.Label(row, textvariable=volume_label_var, width=6)
        volume_label.grid(row=0, column=2, sticky="e")

        self.track_controls.append((info["index"], var, slider))

    # ========================================================
    # ffprobe
    # ========================================================

    def get_audio_streams(self, filepath: str) -> list[dict]:
        cmd = [
            FFPROBE,
            "-v",
            "error",
            "-select_streams",
            "a",
            "-show_entries",
            "stream=index,codec_name,channels:stream_tags=language,title,handler_name",
            "-of",
            "json",
            filepath,
        ]

        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
                creationflags=CREATE_NO_WINDOW,
            )

            data = json.loads(result.stdout)

        except Exception as exc:
            self.ui(
                messagebox.showerror,
                "FFprobe Error",
                f"ffprobe failed:\n\n{exc}",
            )
            return []

        streams = data.get("streams", [])
        output = []

        for display_index, stream in enumerate(streams):
            tags = stream.get("tags", {}) or {}

            stream_index = stream.get("index")
            codec = stream.get("codec_name", "unknown")
            channels = stream.get("channels")

            language = tags.get("language")
            title = tags.get("title")
            handler = tags.get("handler_name")

            details = []

            if language:
                details.append(language)

            if title:
                details.append(title)
            elif handler:
                details.append(handler)

            if codec:
                details.append(codec.upper())

            if channels:
                details.append(f"{channels} ch")

            if details:
                label = f"Track {display_index + 1} - " + " / ".join(details)
            else:
                label = f"Track {display_index + 1}"

            if stream_index is not None:
                output.append(
                    {
                        "index": stream_index,
                        "label": label,
                    }
                )

        return output

    def get_media_duration(self, filepath: str) -> float | None:
        cmd = [
            FFPROBE,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            filepath,
        ]

        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
                creationflags=CREATE_NO_WINDOW,
            )

            return float(result.stdout.strip())

        except Exception:
            return None

    # ========================================================
    # Seekbar
    # ========================================================

    def set_seek_range(self, duration: float | None):
        duration = duration or 0

        self.seekbar.configure(to=max(duration, 1))
        self.time_right_var.set(self.format_seconds(duration))
        self.time_left_var.set("0:00")
        self.seek_var.set(0)
        self.update_trim_markers()

    def set_seek_position(self, seconds: float):
        seconds = max(0, float(seconds))

        duration = self.total_duration_seconds or 0
        if duration:
            seconds = min(seconds, duration)

        if not self.user_is_seeking:
            self.seek_var.set(seconds)

        self.time_left_var.set(self.format_seconds(seconds))

    def on_seek_press(self, event=None):
        self.user_is_seeking = True

        if self.preview_paused or self.paused_seek_without_process:
            self.preview_should_resume_paused = True
            self.paused_seek_without_process = True

    def on_seek_drag(self, value):
        if self.user_is_seeking:
            try:
                seconds = float(value)
                self.time_left_var.set(self.format_seconds(seconds))

                if self.preview_paused or self.paused_seek_without_process:
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

        if self.preview_process is not None or self.preview_generation_process is not None:
            if self.preview_paused:
                self.pause_preview_at_seek_position(target_seconds)
            else:
                self.preview_should_resume_paused = False
                self.restart_preview_at(target_seconds)
        elif self.paused_seek_without_process or self.preview_paused:
            # Already paused with no FFplay process running. Keep the app paused
            # at the dropped position and make sure the frame shown matches it.
            self.paused_seek_without_process = True
            self.preview_paused = True
            self.preview_should_resume_paused = True
            self.preview_start_position = max(0.0, float(target_seconds))
            self.preview_button.config(text="Play", state=tk.NORMAL)
            self.play_pause_button.config(text="Play", state=tk.NORMAL)
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

        # Avoid requesting almost-identical frames repeatedly.
        if (
            self.last_scrub_frame_seconds is not None
            and abs(seconds - self.last_scrub_frame_seconds) < 0.08
        ):
            return

        self.last_scrub_frame_seconds = seconds

        if self.scrub_frame_after_id is not None:
            try:
                self.root.after_cancel(self.scrub_frame_after_id)
            except Exception:
                pass

        self.scrub_frame_after_id = self.root.after(
            90,
            lambda s=seconds: self.request_scrub_frame(s),
        )

    def request_scrub_frame(self, seconds: float):
        self.scrub_frame_after_id = None
        self.scrub_frame_request_id += 1
        request_id = self.scrub_frame_request_id

        self.paused_seek_without_process = True
        self.preview_paused = True
        self.preview_should_resume_paused = True

        self.generate_paused_frame_at(seconds, request_id=request_id, quiet=True)


    # ========================================================
    # Trim controls
    # ========================================================

    def on_trim_toggle(self):
        self.update_trim_controls()
        self.log("Trim controls enabled." if self.trim_enabled_var.get() else "Trim controls disabled.")

    def update_trim_controls(self):
        if not hasattr(self, "trim_buttons_frame"):
            return

        if self.trim_enabled_var.get():
            self.trim_buttons_frame.pack(side=tk.LEFT, padx=(10, 0))
        else:
            self.trim_buttons_frame.pack_forget()

        self.trim_marker_layer.pack_forget()

        self.update_trim_info()
        self.update_trim_markers()
        self.root.after(50, self.update_trim_markers)

    def on_compression_toggle(self):
        if not hasattr(self, "compression_options_frame"):
            return

        if self.compress_enabled_var.get():
            self.compression_options_frame.pack(side=tk.LEFT, padx=(10, 0))
            self.log(
                f"Compression enabled. Target size: {self.compression_target_var.get().strip() or f'{DEFAULT_COMPRESSION_TARGET_MB:g}'} MB "
                f"(Windows/Explorer/Discord), max resolution {self.get_compression_resolution_label()}."
            )
        else:
            self.compression_options_frame.pack_forget()
            self.log("Compression disabled.")

    def on_compression_resolution_changed(self, event=None):
        if self.compress_enabled_var.get():
            self.log(f"Compression max resolution set to {self.get_compression_resolution_label()}.")

    def get_compression_resolution_label(self) -> str:
        selected = self.compression_resolution_var.get().strip()
        if selected not in COMPRESSION_RESOLUTION_PRESETS:
            selected = DEFAULT_COMPRESSION_RESOLUTION
            self.compression_resolution_var.set(selected)
        return selected

    def get_compression_resolution_limit(self, resolution_label: str | None = None) -> tuple[int, int, str]:
        label = resolution_label or self.get_compression_resolution_label()
        if label not in COMPRESSION_RESOLUTION_PRESETS:
            label = DEFAULT_COMPRESSION_RESOLUTION
        width, height = COMPRESSION_RESOLUTION_PRESETS[label]
        return width, height, label

    def get_compression_target_mb(self) -> float | None:
        if not self.compress_enabled_var.get():
            return None

        raw_value = self.compression_target_var.get().strip().lower().replace("mb", "").strip()
        raw_value = raw_value.replace(",", ".")

        try:
            target_mb = float(raw_value)
        except Exception as exc:
            raise ValueError("Compression target must be a number, like 9.99.") from exc

        if target_mb <= 0:
            raise ValueError("Compression target must be larger than 0 MB.")

        return target_mb

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
        if hasattr(self, "trim_marker_layer"):
            self.update_trim_markers()

        if not silent:
            self.set_status("Trim points cleared.")
            self.log("Trim points cleared.")

    def get_active_trim_points(self) -> tuple[float | None, float | None]:
        if not self.trim_enabled_var.get():
            return None, None

        start = self.trim_start_seconds
        end = self.trim_end_seconds
        duration = self.total_duration_seconds

        if duration:
            if start is not None:
                start = min(max(0.0, start), duration)
            if end is not None:
                end = min(max(0.0, end), duration)

        if start is not None and end is not None and end <= start:
            return None, None

        return start, end

    def update_trim_info(self):
        if not hasattr(self, "trim_info_var"):
            return

        if not self.trim_enabled_var.get():
            self.trim_info_var.set("")
            return

        start, end = self.get_active_trim_points()

        if start is None and end is None:
            self.trim_info_var.set("No trim points set")
        elif start is not None and end is not None:
            self.trim_info_var.set(
                f"Export trim: {self.format_seconds(start)} to {self.format_seconds(end)}"
            )
        elif start is not None:
            self.trim_info_var.set(f"Export trim: from {self.format_seconds(start)}")
        else:
            self.trim_info_var.set(f"Export trim: until {self.format_seconds(end)}")

    def seekbar_screen_bounds(self) -> tuple[int, int, int, int] | None:
        """
        Returns seekbar bounds relative to the root window.

        The markers are placed as tiny overlay labels directly on the seekbar
        track area instead of only drawing below it.
        """
        if not hasattr(self, "seekbar"):
            return None

        try:
            root_x = self.root.winfo_rootx()
            root_y = self.root.winfo_rooty()
            x = self.seekbar.winfo_rootx() - root_x
            y = self.seekbar.winfo_rooty() - root_y
            width = self.seekbar.winfo_width()
            height = self.seekbar.winfo_height()
        except Exception:
            return None

        if width <= 1 or height <= 1:
            return None

        return x, y, width, height

    def ensure_seekbar_marker_widgets(self):
        if hasattr(self, "trim_start_seek_marker"):
            return

        # Bright markers are intentionally regular tk.Label widgets. ttk
        # widgets follow system theming too closely and can disappear on the
        # scale background.
        marker_bg = self.root.cget("bg")

        self.trim_start_seek_marker = tk.Label(
            self.root,
            text="▼",
            fg="green",
            bg=marker_bg,
            font=("Segoe UI", 12, "bold"),
            padx=0,
            pady=0,
            borderwidth=0,
            highlightthickness=0,
            relief=tk.FLAT,
        )
        self.trim_end_seek_marker = tk.Label(
            self.root,
            text="▼",
            fg="red",
            bg=marker_bg,
            font=("Segoe UI", 12, "bold"),
            padx=0,
            pady=0,
            borderwidth=0,
            highlightthickness=0,
            relief=tk.FLAT,
        )

    def hide_seekbar_marker_widgets(self):
        for attr in ("trim_start_seek_marker", "trim_end_seek_marker"):
            widget = getattr(self, attr, None)
            if widget is not None:
                try:
                    widget.place_forget()
                except Exception:
                    pass

    def update_trim_markers(self):
        if not hasattr(self, "seekbar"):
            return

        if not self.trim_enabled_var.get():
            self.hide_seekbar_marker_widgets()
            return

        duration = self.total_duration_seconds or 0
        if duration <= 0:
            self.hide_seekbar_marker_widgets()
            return

        start, end = self.get_active_trim_points()

        if start is None and end is None:
            self.hide_seekbar_marker_widgets()
            return

        self.ensure_seekbar_marker_widgets()
        bounds = self.seekbar_screen_bounds()
        if bounds is None:
            self.hide_seekbar_marker_widgets()
            return

        seek_x, seek_y, seek_width, seek_height = bounds

        def x_for_time(seconds: float, target_width: int) -> int:
            return int((seconds / duration) * target_width)

        # Slight inset keeps markers aligned with the usable scale track rather
        # than the full widget border.
        usable_x = seek_x + 8
        usable_width = max(1, seek_width - 16)

        # Put the triangle labels directly above the seekbar track.
        marker_y = max(0, seek_y - 24)

        if start is not None:
            marker_x = usable_x + x_for_time(start, usable_width)
            self.trim_start_seek_marker.place(
                x=max(0, marker_x - 7),
                y=marker_y,
            )
            self.trim_start_seek_marker.lift()
        else:
            self.trim_start_seek_marker.place_forget()

        if end is not None:
            marker_x = usable_x + x_for_time(end, usable_width)
            self.trim_end_seek_marker.place(
                x=max(0, marker_x - 7),
                y=marker_y,
            )
            self.trim_end_seek_marker.lift()
        else:
            self.trim_end_seek_marker.place_forget()


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
        selected = self.selected_tracks()

        if not selected:
            raise ValueError("Please select at least one audio track.")

        filters = []
        maps = []

        for i, (stream_index, volume) in enumerate(selected):
            volume_text = f"{volume:.3f}"
            filters.append(f"[0:{stream_index}]volume={volume_text}[a{i}]")
            maps.append(f"[a{i}]")

        amix_inputs = len(maps)

        amix = (
            f"{''.join(maps)}"
            f"amix=inputs={amix_inputs}:duration=longest:"
            f"dropout_transition=0:normalize=0[aout]"
        )

        return ";".join(filters + [amix])

    def invalidate_preview(self):
        preview_is_active = (
            self.preview_process is not None
            or self.preview_generation_process is not None
            or self.is_generating_preview
        )

        if preview_is_active and not self.is_exporting:
            self.schedule_preview_refresh()
            return

        if self.preview_temp_is_ready:
            self.stop_preview()
            self.cleanup_preview_temp_file()
            self.preview_filter_signature = None
            self.preview_placeholder_var.set("Preview settings changed. Click Preview again.")
            self.preview_placeholder.place(relx=0.5, rely=0.5, anchor="center")
            self.set_status("Preview settings changed. Click Preview again.")

    def current_preview_position(self) -> float:
        try:
            fallback_position = float(self.seek_var.get())
        except Exception:
            fallback_position = 0.0

        if self.preview_started_at_monotonic is None:
            return fallback_position

        if self.preview_paused:
            return fallback_position

        elapsed = (
            time.monotonic()
            - self.preview_started_at_monotonic
            - self.total_pause_seconds
        )
        position = self.preview_start_position + elapsed

        duration = self.total_duration_seconds or 0
        if duration:
            position = min(position, duration)

        return max(0.0, position)

    def schedule_preview_refresh(self, delay_ms: int = 700):
        if not self.video_path or self.is_exporting:
            return

        self.preview_refresh_pending = True

        if self.preview_refresh_after_id is not None:
            try:
                self.root.after_cancel(self.preview_refresh_after_id)
            except Exception:
                pass

        self.set_status("Preview settings changed. Refreshing shortly...")
        self.preview_refresh_after_id = self.root.after(delay_ms, self.refresh_preview_from_current_settings)

    def refresh_preview_from_current_settings(self):
        self.preview_refresh_after_id = None

        if not self.preview_refresh_pending or self.is_exporting:
            return

        self.preview_refresh_pending = False

        if not self.video_path:
            return

        target_seconds = self.current_preview_position()

        try:
            self.build_audio_filter()
        except ValueError as exc:
            self.stop_preview()
            self.cleanup_preview_temp_file()
            self.preview_filter_signature = None
            self.preview_placeholder_var.set(str(exc))
            self.preview_placeholder.place(relx=0.5, rely=0.5, anchor="center")
            self.set_status(str(exc))
            return

        self.preview_filter_signature = None
        self.set_seek_position(target_seconds)

        # If the preview is paused, changing audio levels should not start
        # playback. Keep the app paused at the same timestamp; the new slider
        # settings will apply when the user clicks Play/export.
        if self.preview_paused or self.paused_seek_without_process:
            self.preview_session_id += 1
            self.preview_stop_requested = True
            self.preview_should_resume_paused = True
            self.paused_seek_without_process = True
            self.preview_paused = True

            self.kill_preview_pipeline()

            self.preview_start_position = max(0.0, float(target_seconds))
            self.preview_button.config(text="Play", state=tk.NORMAL)
            self.play_pause_button.config(text="Play", state=tk.NORMAL)
            self.preview_placeholder_var.set("Loading paused frame...")
            self.preview_placeholder.place(relx=0.5, rely=0.5, anchor="center")
            self.set_busy(False)
            self.play_pause_button.config(text="Play", state=tk.NORMAL)
            self.set_status(
                f"Preview paused at {self.format_seconds(target_seconds)}. Audio changes will apply when you play/export."
            )
            self.generate_paused_frame_at(target_seconds)
            return

        self.stop_preview()
        self.preview_filter_signature = None
        self.set_seek_position(target_seconds)
        self.preview_placeholder_var.set("Refreshing mixed preview...")
        self.preview_placeholder.place(relx=0.5, rely=0.5, anchor="center")

        # Give the old FFplay/FFmpeg process a short moment to exit before
        # starting the next render. This avoids stale worker threads racing the
        # new preview session.
        self.root.after(250, self.start_preview)

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

    def show_paused_frame_from_bytes(self, image_bytes: bytes):
        if not PIL_AVAILABLE or self.paused_frame_label is None:
            self.preview_placeholder_var.set("Paused. Click Play to resume preview.")
            return

        try:
            image = Image.open(BytesIO(image_bytes))
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
            self.set_status("Paused frame loaded. Click Play to resume.")
        except Exception:
            self.preview_placeholder_var.set("Paused. Click Play to resume preview.")
            self.preview_placeholder.place(relx=0.5, rely=0.5, anchor="center")

    def generate_paused_frame_at(self, seconds: float, request_id: int | None = None, quiet: bool = False):
        if not self.video_path or not FFMPEG or not PIL_AVAILABLE:
            self.preview_placeholder_var.set("Paused. Click Play to resume preview.")
            return

        if self.paused_frame_process is not None:
            try:
                self.paused_frame_process.kill()
            except Exception:
                pass
            self.paused_frame_process = None

        seconds = max(0.0, float(seconds))
        duration = self.total_duration_seconds or 0
        if duration:
            seconds = min(seconds, max(0.0, duration - 0.05))

        if request_id is None:
            self.scrub_frame_request_id += 1
            request_id = self.scrub_frame_request_id

        session_id = self.preview_session_id
        frame_path = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg").name

        def worker():
            try:
                cmd = [
                    FFMPEG,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-ss",
                    f"{seconds:.3f}",
                    "-i",
                    self.video_path,
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

                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=CREATE_NO_WINDOW,
                )
                self.paused_frame_process = process

                try:
                    return_code = process.wait(timeout=6)
                except subprocess.TimeoutExpired:
                    try:
                        process.kill()
                    except Exception:
                        pass
                    return_code = -1

                self.paused_frame_process = None

                image_bytes = b""
                if return_code == 0 and Path(frame_path).exists():
                    try:
                        image_bytes = Path(frame_path).read_bytes()
                    except Exception:
                        image_bytes = b""

                if (
                    image_bytes
                    and session_id == self.preview_session_id
                    and request_id == self.scrub_frame_request_id
                    and self.paused_seek_without_process
                ):
                    self.ui(self.show_paused_frame_from_bytes, image_bytes)
                elif (
                    not quiet
                    and session_id == self.preview_session_id
                    and request_id == self.scrub_frame_request_id
                    and self.paused_seek_without_process
                ):
                    self.ui(
                        self.preview_placeholder_var.set,
                        "Paused. Click Play to resume preview.",
                    )

            except Exception:
                if (
                    not quiet
                    and session_id == self.preview_session_id
                    and request_id == self.scrub_frame_request_id
                    and self.paused_seek_without_process
                ):
                    self.ui(
                        self.preview_placeholder_var.set,
                        "Paused. Click Play to resume preview.",
                    )
            finally:
                self.paused_frame_process = None
                try:
                    Path(frame_path).unlink(missing_ok=True)
                except Exception:
                    pass

        threading.Thread(target=worker, daemon=True).start()


    # ========================================================
    # Embedded preview
    # ========================================================

    def toggle_preview(self):
        # The visible control is now a media-style Play/Pause button. Stopping
        # the FFmpeg/FFplay pipeline still exists internally for file changes,
        # export, close, seek, and preview refreshes.
        if self.is_exporting:
            return

        if self.paused_seek_without_process or self.preview_paused:
            self.toggle_play_pause()
            return

        if self.preview_process is not None and self.preview_hwnd is not None:
            self.toggle_play_pause()
            return

        if self.preview_generation_process is not None or self.is_generating_preview:
            return

        self.start_preview()

    def start_preview(self):
        if not self.video_path:
            messagebox.showwarning("No video loaded", "Please load a video file first.")
            return

        if not FFMPEG:
            messagebox.showerror("Missing ffmpeg", "ffmpeg was not found.")
            return

        if not FFPLAY:
            messagebox.showerror(
                "Missing ffplay",
                "ffplay was not found. Video preview requires ffplay.exe.",
            )
            return

        if not IS_WINDOWS:
            messagebox.showerror(
                "Embedded preview unsupported",
                "Embedded preview in the app window is currently implemented for Windows.",
            )
            return

        try:
            filter_complex = self.build_audio_filter()
        except ValueError as exc:
            messagebox.showwarning("No tracks selected", str(exc))
            return

        try:
            start_seconds = float(self.seek_var.get())
        except Exception:
            start_seconds = 0.0

        self.preview_session_id += 1
        session_id = self.preview_session_id

        self.hide_paused_frame()
        self.hide_paused_frame()
        self.preview_stop_requested = False
        self.preview_should_resume_paused = False
        self.paused_seek_without_process = False
        self.preview_paused = False
        self.pause_started_at_monotonic = None
        self.total_pause_seconds = 0.0
        self.preview_filter_signature = filter_complex
        self.is_generating_preview = True

        self.preview_button.config(text="Loading...", state=tk.DISABLED)
        self.play_pause_button.config(text="Pause", state=tk.DISABLED)
        self.set_busy(True)
        self.refresh_playback_button_state()

        self.preview_placeholder.place_forget()
        self.set_status("Starting streaming preview...")
        self.log(f"Starting preview at {self.format_seconds(start_seconds)}.")

        self.preview_thread = threading.Thread(
            target=self.preview_worker,
            args=(filter_complex, start_seconds, session_id),
            daemon=True,
        )
        self.preview_thread.start()

    def preview_worker(self, filter_complex: str, start_seconds: float, session_id: int):
        """
        Start preview as a streaming FFmpeg -> FFplay pipeline.

        The old implementation rendered a full mixed temporary video before
        playback, which made Preview wait several seconds on longer files.
        This version starts FFplay immediately and feeds it remuxed/mixed bytes
        from FFmpeg over a pipe.
        """
        self.is_generating_preview = True

        try:
            self.play_preview_stream(filter_complex, start_seconds, session_id)

        except Exception as exc:
            # Stopping/restarting preview intentionally tears down processes.
            # Do not show stale worker errors after Stop Preview or seek/refresh.
            if not self.preview_stop_requested and session_id == self.preview_session_id:
                self.ui(
                    messagebox.showerror,
                    "Preview Error",
                    f"Preview failed:\n\n{exc}",
                )

        finally:
            if session_id == self.preview_session_id:
                self.preview_generation_process = None
                self.preview_process = None
                self.preview_hwnd = None
                self.preview_started_at_monotonic = None

                if not self.paused_seek_without_process:
                    self.preview_stop_requested = False
                    self.preview_paused = False
                    self.pause_started_at_monotonic = None
                    self.total_pause_seconds = 0.0
                    self.ui(self.preview_button.config, text="Play")
                    self.ui(self.play_pause_button.config, text="Pause", state=tk.DISABLED)
                    self.ui(self.refresh_playback_button_state)
                    self.ui(self.set_status, "Ready.")

                self.is_generating_preview = False
                self.preview_temp_is_ready = False
                self.ui(self.set_busy, False)

    def play_preview_stream(self, filter_complex: str, start_seconds: float, session_id: int):
        if not self.video_path:
            return

        start_seconds = max(0.0, float(start_seconds))

        duration = self.total_duration_seconds or 0
        if duration:
            start_seconds = min(start_seconds, duration)

        should_start_paused = bool(self.preview_should_resume_paused)

        self.preview_start_position = start_seconds
        self.preview_started_at_monotonic = time.monotonic()
        self.preview_hwnd = None

        self.preview_paused = False
        self.pause_started_at_monotonic = None
        self.total_pause_seconds = 0.0

        self.ui(self.hide_paused_frame)
        self.ui(self.preview_placeholder.place_forget)

        # Use cached preview dimensions. Avoid blocking worker threads on
        # root.update_idletasks(), which can contribute to "Not Responding"
        # when preview is being restarted repeatedly.
        width = max(320, int(getattr(self, "preview_width", 960)))
        height = max(180, int(getattr(self, "preview_height", 540)))

        ffmpeg_cmd = [
            FFMPEG,
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{start_seconds:.3f}",
            "-i",
            self.video_path,
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
            FFPLAY,
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

        self.preview_generation_process = ffmpeg_process
        self.preview_process = ffplay_process

        self.ui(self.set_busy, True)
        self.ui(self.set_status, "Playing preview...")

        self.ui(self.embed_preview_window_when_ready, ffplay_process.pid, session_id)

        if should_start_paused:
            # Pause no longer uses suspended FFplay/FFmpeg processes. If this
            # path is reached, stop the fresh pipeline and show a still frame.
            self.preview_stop_requested = True
            try:
                ffplay_process.kill()
            except Exception:
                pass
            try:
                ffmpeg_process.kill()
            except Exception:
                pass

            self.paused_seek_without_process = True
            self.preview_paused = True
            self.ui(self.set_seek_position, start_seconds)
            self.ui(self.preview_button.config, text="Play", state=tk.NORMAL)
            self.ui(self.play_pause_button.config, text="Play", state=tk.NORMAL)
            self.ui(self.refresh_playback_button_state)
            self.ui(self.generate_paused_frame_at, start_seconds)
            return


        while ffplay_process.poll() is None:
            if self.preview_stop_requested or session_id != self.preview_session_id:
                try:
                    ffplay_process.terminate()
                except Exception:
                    pass
                try:
                    ffmpeg_process.terminate()
                except Exception:
                    pass
                break

            if self.preview_started_at_monotonic is not None and not self.preview_paused:
                elapsed = (
                    time.monotonic()
                    - self.preview_started_at_monotonic
                    - self.total_pause_seconds
                )
                current_position = self.preview_start_position + elapsed

                if duration:
                    current_position = min(current_position, duration)

                self.ui(self.set_seek_position, current_position)

            time.sleep(0.25)

        # Clean up both sides of the streaming pipeline.
        if session_id == self.preview_session_id:
            self.ui(hide_native_window, self.preview_hwnd)

        for proc in (ffplay_process, ffmpeg_process):
            if proc is not None and proc.poll() is None:
                try:
                    proc.terminate()
                except Exception:
                    pass

        if ffmpeg_process.poll() is None:
            try:
                ffmpeg_process.wait(timeout=0.5)
            except Exception:
                try:
                    ffmpeg_process.kill()
                except Exception:
                    pass

        if ffplay_process.poll() is None:
            try:
                ffplay_process.wait(timeout=0.5)
            except Exception:
                try:
                    ffplay_process.kill()
                except Exception:
                    pass

    def embed_preview_window_when_ready(self, pid: int, session_id: int | None = None):
        """
        Finds the FFplay/SDL window by process ID and embeds it into preview_frame.
        This version uses WindowLongPtr and retries aggressively until the native
        SDL window exists, then hides/reparents/restyles it.
        """
        if not IS_WINDOWS:
            return

        parent_hwnd = self.preview_frame.winfo_id()
        attempts = {"count": 0}

        def try_embed():
            if session_id is not None and session_id != self.preview_session_id:
                return

            preview_process = self.preview_process
            if preview_process is None or preview_process.poll() is not None:
                return

            hwnd = find_main_window_for_pid(pid)

            if hwnd:
                hide_native_window(hwnd)
                self.preview_hwnd = hwnd

                width = max(1, self.preview_frame.winfo_width())
                height = max(1, self.preview_frame.winfo_height())

                ok = embed_external_window(hwnd, parent_hwnd, width, height)

                if ok:
                    self.preview_button.config(state=tk.NORMAL, text="Pause")
                    self.play_pause_button.config(state=tk.DISABLED, text="Pause")
                    self.set_status("Playing preview...")
                else:
                    self.set_status("Found preview window, but embedding failed.")
                return

            attempts["count"] += 1
            if attempts["count"] < 200:
                self.root.after(25, try_embed)
            else:
                self.set_status("Preview is playing, but the video window could not be embedded.")

        self.root.after(25, try_embed)

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

        self.update_trim_markers()

        if not IS_WINDOWS:
            return

        if self.preview_hwnd and IsWindow(self.preview_hwnd):
            width = max(1, self.preview_width)
            height = max(1, self.preview_height)
            try:
                MoveWindow(self.preview_hwnd, 0, 0, width, height, True)
                UpdateWindow(self.preview_hwnd)
            except Exception:
                pass

    def restart_preview_at(self, target_seconds: float, show_placeholder: bool = True):
        if not self.video_path:
            return

        was_paused = bool(self.preview_paused)
        self.preview_should_resume_paused = was_paused

        self.kill_preview_pipeline()

        self.preview_session_id += 1
        session_id = self.preview_session_id

        try:
            filter_complex = self.build_audio_filter()
        except ValueError as exc:
            self.stop_preview()
            self.preview_placeholder_var.set(str(exc))
            self.preview_placeholder.place(relx=0.5, rely=0.5, anchor="center")
            self.set_status(str(exc))
            return

        self.preview_filter_signature = filter_complex
        self.preview_stop_requested = False
        self.preview_process = None
        self.preview_generation_process = None
        self.preview_hwnd = None
        self.preview_paused = False
        self.pause_started_at_monotonic = None
        self.total_pause_seconds = 0.0
        self.is_generating_preview = True

        self.preview_button.config(text="Loading...", state=tk.DISABLED)
        self.play_pause_button.config(text="Play" if was_paused else "Pause", state=tk.DISABLED)

        self.preview_placeholder.place_forget()

        self.set_busy(True)
        self.set_status("Seeking preview...")

        def worker():
            try:
                self.preview_worker(filter_complex, target_seconds, session_id)
            except Exception:
                # Stale seek/restart errors are expected when processes are torn
                # down rapidly. Do not show modal popups for these.
                pass

        threading.Thread(target=worker, daemon=True).start()

    def kill_preview_pipeline(self):
        """
        Tear down preview processes without process suspension.

        Suspending FFmpeg/FFplay on Windows while they own pipe handles can
        deadlock Tkinter after the app idles in the background. Pause is now
        represented by a still frame plus no running preview process.
        """
        hide_native_window(self.preview_hwnd)

        generation_process = self.preview_generation_process
        preview_process = self.preview_process

        for proc in (preview_process, generation_process):
            if proc is not None:
                try:
                    proc.kill()
                except Exception:
                    try:
                        proc.terminate()
                    except Exception:
                        pass

        self.preview_generation_process = None
        self.preview_process = None
        self.preview_hwnd = None
        self.preview_started_at_monotonic = None
        self.pause_started_at_monotonic = None
        self.total_pause_seconds = 0.0

    def toggle_play_pause(self):
        # Resume from still-frame paused state.
        if self.paused_seek_without_process:
            resume_seconds = self.current_seek_seconds()
            self.hide_paused_frame()
            self.preview_placeholder.place_forget()
            self.paused_seek_without_process = False
            self.preview_paused = False
            self.preview_should_resume_paused = False
            self.preview_button.config(text="Loading...", state=tk.DISABLED)
            self.play_pause_button.config(text="Pause", state=tk.DISABLED)
            self.restart_preview_at(resume_seconds, show_placeholder=False)
            return

        if self.preview_process is None:
            return

        # Pause by stopping preview processes and showing a still frame.
        # Do NOT suspend FFplay/FFmpeg; that caused idle crashes.
        paused_at = self.current_preview_position()
        self.preview_session_id += 1
        self.preview_stop_requested = True
        self.preview_should_resume_paused = True
        self.paused_seek_without_process = True
        self.preview_paused = True

        self.kill_preview_pipeline()

        self.set_seek_position(paused_at)
        self.preview_start_position = max(0.0, float(paused_at))

        self.preview_button.config(text="Play", state=tk.NORMAL)
        self.play_pause_button.config(text="Play", state=tk.NORMAL)
        self.preview_placeholder_var.set("Loading paused frame...")
        self.preview_placeholder.place(relx=0.5, rely=0.5, anchor="center")
        self.set_busy(False)
        self.preview_button.config(text="Play", state=tk.NORMAL)
        self.play_pause_button.config(text="Play", state=tk.NORMAL)
        self.set_status(f"Preview paused at {self.format_seconds(paused_at)}. Click Play to resume.")
        self.generate_paused_frame_at(paused_at)

    def stop_preview(self):
        had_active_preview = (
            self.preview_process is not None
            or self.preview_generation_process is not None
            or self.paused_seek_without_process
        )

        self.preview_stop_requested = True
        self.preview_session_id += 1

        if self.preview_refresh_after_id is not None:
            try:
                self.root.after_cancel(self.preview_refresh_after_id)
            except Exception:
                pass
            self.preview_refresh_after_id = None

        if self.scrub_frame_after_id is not None:
            try:
                self.root.after_cancel(self.scrub_frame_after_id)
            except Exception:
                pass
            self.scrub_frame_after_id = None

        self.preview_refresh_pending = False
        self.preview_should_resume_paused = False
        self.paused_seek_without_process = False
        self.hide_paused_frame()

        if self.paused_frame_process is not None:
            try:
                self.paused_frame_process.kill()
            except Exception:
                pass
            self.paused_frame_process = None

        self.kill_preview_pipeline()

        self.preview_paused = False

        self.preview_button.config(text="Play")
        self.play_pause_button.config(text="Pause", state=tk.DISABLED)
        self.refresh_playback_button_state()

        if not self.is_exporting:
            self.set_busy(False)
            self.set_status("Preview stopped.")
            if had_active_preview:
                self.log("Preview stopped.")

    def cleanup_preview_temp_file(self):
        try:
            if self.preview_temp_path and Path(self.preview_temp_path).exists():
                Path(self.preview_temp_path).unlink()
        except Exception:
            pass

        self.preview_temp_path = None
        self.preview_temp_is_ready = False
        self.preview_hwnd = None

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
        trim_suffix = "_trimmed" if (trim_start is not None or trim_end is not None) else ""
        compression_suffix = (
            f"_compressed_{compression_target_mb:g}mb_{compression_resolution_label}"
            if compression_target_mb is not None
            else ""
        )
        default_output = OUTPUTS_DIR / f"{source.stem}_mixed_audio{trim_suffix}{compression_suffix}.mp4"

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

        self.stop_preview()

        self.update_trim_info()

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
            target=self.export_worker,
            args=(filter_complex, str(output_path_obj), trim_start, trim_end, compression_target_mb, compression_resolution_label),
            daemon=True,
        )
        self.export_thread.start()

    def export_progress_duration(
        self,
        trim_start: float | None = None,
        trim_end: float | None = None,
    ) -> float:
        full_duration = self.total_duration_seconds or 0

        if trim_start is not None or trim_end is not None:
            effective_start = trim_start or 0
            effective_end = trim_end or full_duration
            return max(0.0, effective_end - effective_start)

        return max(0.0, full_duration)

    def add_export_input_args(
        self,
        cmd: list[str],
        trim_start: float | None = None,
        trim_end: float | None = None,
    ):
        # Fast stream-copy video trimming. Putting -ss before -i avoids
        # re-encoding in normal exports. Compression exports re-encode video,
        # but this still keeps seeking responsive on long files.
        if trim_start is not None and trim_start > 0:
            cmd.extend(["-ss", f"{trim_start:.3f}"])

        cmd.extend(["-i", self.video_path])

        if trim_end is not None:
            if trim_start is not None and trim_start > 0:
                trim_duration = max(0.001, trim_end - trim_start)
                cmd.extend(["-t", f"{trim_duration:.3f}"])
            else:
                cmd.extend(["-to", f"{trim_end:.3f}"])

    def build_standard_export_command(
        self,
        filter_complex: str,
        output_path: str,
        trim_start: float | None = None,
        trim_end: float | None = None,
    ) -> list[str]:
        cmd = [
            FFMPEG,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
        ]

        self.add_export_input_args(cmd, trim_start, trim_end)

        cmd.extend(
            [
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
            ]
        )

        if Path(output_path).suffix.lower() in {".mp4", ".mov", ".m4v"}:
            cmd.extend(["-movflags", "+faststart"])

        cmd.extend(
            [
                "-nostats",
                "-progress",
                "pipe:1",
                output_path,
            ]
        )

        return cmd

    def compression_bitrates_for_budget(
        self,
        budget_mb: float,
        duration_seconds: float,
    ) -> tuple[int, int, float]:
        if duration_seconds <= 0:
            raise ValueError("Cannot compress to a target size because the video duration is unknown.")

        budget_bytes = max(1, int(budget_mb * WINDOWS_MB_BYTES))
        total_kbps = (budget_bytes * 8) / duration_seconds / 1000

        # Reserve a little room for the MP4/MKV container and bitrate overshoot.
        overhead_kbps = max(10, int(total_kbps * 0.04))

        # Discord-sized exports need the bits more on video than audio. Keep
        # compressed audio fixed and predictable at 64 kbps so the remaining
        # target budget can be spent on video.
        audio_kbps = COMPRESSION_DEFAULT_AUDIO_KBPS

        video_kbps = int(total_kbps - audio_kbps - overhead_kbps)

        if video_kbps < 50:
            raise ValueError(
                "This target is too small for the clip length. Try a larger MB limit, "
                "a shorter trim, or a smaller source clip."
            )

        return video_kbps, audio_kbps, total_kbps

    def build_compressed_export_command(
        self,
        filter_complex: str,
        output_path: str,
        trim_start: float | None,
        trim_end: float | None,
        budget_mb: float,
        duration_seconds: float,
        compression_resolution_label: str | None,
    ) -> tuple[list[str], int, int, float]:
        video_kbps, audio_kbps, total_kbps = self.compression_bitrates_for_budget(
            budget_mb,
            duration_seconds,
        )
        max_width, max_height, _ = self.get_compression_resolution_limit(compression_resolution_label)

        cmd = [
            FFMPEG,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
        ]

        self.add_export_input_args(cmd, trim_start, trim_end)

        cmd.extend(
            [
                "-filter_complex",
                filter_complex,

                "-map",
                "0:v:0?",
                "-map",
                "[aout]",

                "-vf",
                (
                    f"scale=w='min({max_width},iw)':"
                    f"h='min({max_height},ih)':"
                    "force_original_aspect_ratio=decrease:"
                    "force_divisible_by=2,setsar=1"
                ),

                "-c:v",
                "hevc_nvenc",
                "-preset",
                "slow",
                "-rc",
                "cbr",
                "-b:v",
                f"{video_kbps}k",
                "-maxrate",
                f"{video_kbps}k",
                "-bufsize",
                f"{max(video_kbps, 100)}k",
                "-pix_fmt",
                "yuv420p",

                "-c:a",
                "aac",
                "-b:a",
                f"{audio_kbps}k",
                "-ac",
                "2",
            ]
        )

        if Path(output_path).suffix.lower() in {".mp4", ".mov", ".m4v"}:
            cmd.extend(["-tag:v", "hvc1", "-movflags", "+faststart"])

        cmd.extend(
            [
                "-nostats",
                "-progress",
                "pipe:1",
                output_path,
            ]
        )

        return cmd, video_kbps, audio_kbps, total_kbps

    def run_export_command(
        self,
        cmd: list[str],
        progress_duration: float,
        progress_label: str,
    ) -> tuple[int, str]:
        self.export_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=CREATE_NO_WINDOW,
        )

        last_percentage = -1

        if self.export_process.stdout:
            for line in self.export_process.stdout:
                line = line.strip()

                if line.startswith("out_time_ms=") and progress_duration > 0:
                    try:
                        out_time_ms = int(line.split("=", 1)[1])
                        current_seconds = out_time_ms / 1_000_000
                        percentage = int((current_seconds / progress_duration) * 100)
                        percentage = max(0, min(100, percentage))

                        if percentage != last_percentage:
                            last_percentage = percentage
                            self.ui(self.set_status, f"{progress_label} {percentage}%")
                    except Exception:
                        pass

                elif line == "progress=end":
                    full_duration = self.total_duration_seconds or 0
                    if full_duration:
                        self.ui(self.set_seek_position, full_duration)

        return_code = self.export_process.wait()

        stderr_text = ""
        if self.export_process.stderr:
            stderr_text = self.export_process.stderr.read()

        self.export_process = None
        return return_code, stderr_text

    def export_worker(
        self,
        filter_complex: str,
        output_path: str,
        trim_start: float | None = None,
        trim_end: float | None = None,
        compression_target_mb: float | None = None,
        compression_resolution_label: str | None = None,
    ):
        try:
            progress_duration = self.export_progress_duration(trim_start, trim_end)
            full_duration = self.total_duration_seconds or 0

            if compression_target_mb is None:
                cmd = self.build_standard_export_command(
                    filter_complex,
                    output_path,
                    trim_start,
                    trim_end,
                )

                self.ui(self.log, "Starting standard export: video copy + AAC mixed audio.")
                return_code, stderr_text = self.run_export_command(
                    cmd,
                    progress_duration,
                    "Exporting...",
                )

                if return_code != 0:
                    if self.is_exporting:
                        self.ui(
                            messagebox.showerror,
                            "Export Error",
                            "FFmpeg export failed.\n\n"
                            + (stderr_text[-3000:] if stderr_text else "No FFmpeg error output."),
                        )
                    return

                if full_duration:
                    self.ui(self.set_seek_position, trim_end or full_duration)

                self.ui(self.set_status, f"Export complete: {output_path}")
                self.ui(self.log, f"Export complete: {output_path}")
                self.ui(
                    messagebox.showinfo,
                    "Export complete",
                    f"Saved:\n\n{output_path}",
                )
                self.ui(self.reveal_file, output_path)
                return

            if progress_duration <= 0:
                raise ValueError("Cannot compress to a target size because the video duration is unknown.")

            _, _, compression_resolution_label = self.get_compression_resolution_limit(compression_resolution_label)

            target_limit_bytes = int(compression_target_mb * WINDOWS_MB_BYTES)
            target_fill_bytes = int(target_limit_bytes * COMPRESSION_TARGET_FILL_RATIO)
            target_limit_mb = target_limit_bytes / WINDOWS_MB_BYTES

            budget_mb = float(compression_target_mb)
            lower_budget_mb: float | None = None
            upper_budget_mb: float | None = None

            last_error = ""
            stop_reason = ""
            final_size_bytes = 0
            best_size_bytes = 0
            best_temp_path: str | None = None
            temp_paths: list[str] = []

            self.ui(
                self.log,
                (
                    f"Compression tuning target: keep the best file under {target_limit_mb:.2f} MB in Windows/Discord "
                    f"and retry if it lands below {target_fill_bytes / WINDOWS_MB_BYTES:.2f} MB in Windows/Discord."
                ),
            )

            try:
                for attempt in range(1, COMPRESSION_MAX_ATTEMPTS + 1):
                    if not self.is_exporting:
                        self.ui(self.log, "Export cancelled.")
                        return

                    if budget_mb < MIN_COMPRESSION_BUDGET_MB:
                        stop_reason = "The bitrate budget became too small to continue."
                        self.ui(self.log, f"Compression stopped: {stop_reason}")
                        break

                    suffix = Path(output_path).suffix or ".mp4"
                    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
                    temp_output_path = temp_file.name
                    temp_file.close()
                    temp_paths.append(temp_output_path)

                    try:
                        cmd, video_kbps, audio_kbps, total_kbps = self.build_compressed_export_command(
                            filter_complex,
                            temp_output_path,
                            trim_start,
                            trim_end,
                            budget_mb,
                            progress_duration,
                            compression_resolution_label,
                        )
                    except ValueError as exc:
                        stop_reason = str(exc)
                        self.ui(self.log, f"Compression stopped: {stop_reason}")
                        break

                    self.ui(
                        self.log,
                        (
                            f"Compression attempt {attempt}/{COMPRESSION_MAX_ATTEMPTS}: "
                            f"encode budget {budget_mb:.2f} MB internal, video {video_kbps} kbps, "
                            f"audio {audio_kbps} kbps. Video is capped to {compression_resolution_label} if needed; FPS is preserved."
                        ),
                    )

                    return_code, stderr_text = self.run_export_command(
                        cmd,
                        progress_duration,
                        f"Compressing attempt {attempt}...",
                    )

                    if not self.is_exporting:
                        self.ui(self.log, "Export cancelled.")
                        return

                    if return_code != 0:
                        last_error = stderr_text[-3000:] if stderr_text else "No FFmpeg error output."
                        break

                    try:
                        final_size_bytes = Path(temp_output_path).stat().st_size
                    except Exception:
                        final_size_bytes = 0

                    final_size_mb = final_size_bytes / WINDOWS_MB_BYTES if final_size_bytes else 0
                    final_size_text = format_windows_discord_size(final_size_bytes)

                    self.ui(
                        self.log,
                        f"Compression attempt {attempt} finished at {final_size_text}. Limit is {target_limit_mb:.2f} MB in Windows/Discord.",
                    )

                    if final_size_bytes and final_size_bytes <= target_limit_bytes:
                        lower_budget_mb = budget_mb

                        if final_size_bytes > best_size_bytes:
                            if best_temp_path and best_temp_path != temp_output_path:
                                try:
                                    Path(best_temp_path).unlink(missing_ok=True)
                                except Exception:
                                    pass
                            best_size_bytes = final_size_bytes
                            best_temp_path = temp_output_path
                        else:
                            try:
                                Path(temp_output_path).unlink(missing_ok=True)
                            except Exception:
                                pass

                        if final_size_bytes >= target_fill_bytes:
                            shutil.copy2(best_temp_path, output_path)

                            if full_duration:
                                self.ui(self.set_seek_position, trim_end or full_duration)

                            best_size_text = format_windows_discord_size(best_size_bytes)
                            self.ui(
                                self.set_status,
                                f"Export complete: {output_path} ({best_size_text})",
                            )
                            self.ui(
                                self.log,
                                (
                                    f"Compression succeeded at {best_size_text} after {attempt} attempt(s), "
                                    f"using the closest successful file under {target_limit_mb:.2f} MB in Windows/Discord."
                                ),
                            )
                            self.ui(
                                messagebox.showinfo,
                                "Export complete",
                                f"Saved:\n\n{output_path}\n\nSize: {best_size_text}",
                            )
                            self.ui(self.reveal_file, output_path)
                            return

                        if upper_budget_mb is not None:
                            next_budget_mb = (budget_mb + upper_budget_mb) / 2
                        else:
                            desired_bytes = max(target_fill_bytes, int(target_limit_bytes * 0.99))
                            ratio = desired_bytes / final_size_bytes if final_size_bytes else 1.0
                            next_budget_mb = budget_mb * ratio

                        next_budget_mb = max(budget_mb + COMPRESSION_BUDGET_EPSILON_MB, next_budget_mb)
                        self.ui(
                            self.log,
                            (
                                f"File is under the limit but leaves room unused. "
                                f"Retrying with a {next_budget_mb:.2f} MB internal encode budget."
                            ),
                        )

                    else:
                        upper_budget_mb = budget_mb

                        if lower_budget_mb is not None:
                            next_budget_mb = (lower_budget_mb + budget_mb) / 2
                        else:
                            if final_size_bytes:
                                ratio = target_fill_bytes / final_size_bytes
                                next_budget_mb = budget_mb * ratio
                            else:
                                next_budget_mb = budget_mb - COMPRESSION_RETRY_STEP_MB

                            next_budget_mb = min(next_budget_mb, budget_mb - COMPRESSION_BUDGET_EPSILON_MB)

                        self.ui(
                            self.log,
                            (
                                f"File is too large. Retrying with a {next_budget_mb:.2f} MB internal encode budget "
                                f"while keeping the best previous under-limit file."
                            ),
                        )

                    if abs(next_budget_mb - budget_mb) < COMPRESSION_BUDGET_EPSILON_MB:
                        stop_reason = "Further bitrate tuning would barely change the result."
                        self.ui(self.log, f"Compression stopped: {stop_reason}")
                        break

                    budget_mb = next_budget_mb

                if best_temp_path and best_size_bytes:
                    shutil.copy2(best_temp_path, output_path)

                    if full_duration:
                        self.ui(self.set_seek_position, trim_end or full_duration)

                    best_size_text = format_windows_discord_size(best_size_bytes)
                    self.ui(
                        self.set_status,
                        f"Export complete: {output_path} ({best_size_text})",
                    )
                    self.ui(
                        self.log,
                        (
                            f"Compression finished using the best successful attempt: {best_size_text} "
                            f"under the {target_limit_mb:.2f} MB in Windows/Discord limit."
                        ),
                    )
                    self.ui(
                        messagebox.showinfo,
                        "Export complete",
                        f"Saved:\n\n{output_path}\n\nSize: {best_size_text}",
                    )
                    self.ui(self.reveal_file, output_path)
                    return

            finally:
                for temp_path in temp_paths:
                    if temp_path != best_temp_path:
                        try:
                            Path(temp_path).unlink(missing_ok=True)
                        except Exception:
                            pass
                if best_temp_path:
                    try:
                        Path(best_temp_path).unlink(missing_ok=True)
                    except Exception:
                        pass

            if last_error:
                self.ui(
                    messagebox.showerror,
                    "Compression Error",
                    "FFmpeg compression failed.\n\n"
                    "This usually means hevc_nvenc is unavailable, the NVIDIA driver/GPU does not support it, "
                    "or FFmpeg rejected the NVENC settings.\n\n"
                    + last_error,
                )
            else:
                final_size_text = format_windows_discord_size(final_size_bytes)
                extra_reason = f"\n\nReason: {stop_reason}" if stop_reason else ""
                self.ui(
                    messagebox.showerror,
                    "Compression Target Not Reached",
                    f"The output could not be compressed below {compression_target_mb:g} MB in Windows/Discord.\n\n"
                    f"Last size: {final_size_text}"
                    f"{extra_reason}\n\n"
                    "Try trimming the clip shorter or using a larger MB target.",
                )

        except Exception as exc:
            self.ui(
                messagebox.showerror,
                "Export Error",
                f"Export failed:\n\n{exc}",
            )
            self.ui(self.log, f"Export failed: {exc}")

        finally:
            self.export_process = None
            self.is_exporting = False
            self.ui(self.stop_export_button.config, state=tk.DISABLED)
            self.ui(self.set_busy, False)

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

    # ========================================================
    # Closing
    # ========================================================

    def on_close(self):
        self.hide_seekbar_marker_widgets()
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

        self.cleanup_preview_temp_file()
        self.root.destroy()

    # ========================================================
    # Utility
    # ========================================================

    @staticmethod
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


# ============================================================
# Command-line / Open With support
# ============================================================

def get_startup_file_from_args() -> str | None:
    """
    Windows "Open with" passes the selected file as sys.argv[1].

    Example:
        AudioTrackMerger.exe "C:\\Videos\\movie.mp4"
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
        return tk.Tk()

    try:
        return TkinterDnD.Tk()

    except Exception as exc:
        DND_AVAILABLE = False

        root = tk.Tk()
        root.withdraw()

        messagebox.showerror(
            "Drag and drop failed",
            "Drag and drop could not start because the tkdnd library could not be loaded.\n\n"
            "This usually means tkinterdnd2 was not packaged correctly.\n\n"
            "Rebuild with:\n"
            "pyinstaller --collect-all tkinterdnd2 ...\n\n"
            f"Details:\n{exc}",
        )

        root.deiconify()
        return root


def main():
    startup_file = get_startup_file_from_args()

    root = create_root_window()
    app = AudioTrackMergerApp(root)

    if startup_file:
        root.after(250, lambda: app.load_video(startup_file))

    root.mainloop()


if __name__ == "__main__":
    main()
