import ctypes
import os

from cliptoolbox.constants import IS_WINDOWS

# ============================================================
# Windows native window helpers
# ============================================================

if IS_WINDOWS:
    import ctypes.wintypes

    user32 = ctypes.windll.user32

    EnumWindows = user32.EnumWindows
    EnumChildWindows = user32.EnumChildWindows
    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    IsWindow = user32.IsWindow
    IsWindowVisible = user32.IsWindowVisible
    IsIconic = user32.IsIconic
    IsIconic.argtypes = [ctypes.c_void_p]
    IsIconic.restype = ctypes.c_bool
    GetWindowThreadProcessId = user32.GetWindowThreadProcessId
    GetParent = user32.GetParent
    GetWindowTextLengthW = user32.GetWindowTextLengthW
    GetWindowTextW = user32.GetWindowTextW
    GetClassNameW = user32.GetClassNameW

    SetParent = user32.SetParent
    EnableWindow = user32.EnableWindow
    EnableWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
    MoveWindow = user32.MoveWindow
    ShowWindow = user32.ShowWindow
    BringWindowToTop = user32.BringWindowToTop
    UpdateWindow = user32.UpdateWindow

    if hasattr(user32, "GetWindowLongPtrW"):
        GetWindowLongPtrW = user32.GetWindowLongPtrW
        SetWindowLongPtrW = user32.SetWindowLongPtrW
    else:
        GetWindowLongPtrW = user32.GetWindowLongW
        SetWindowLongPtrW = user32.SetWindowLongW

    # LONG_PTR signatures. Without these, a style value with bit 31 set
    # (WS_POPUP) overflows ctypes' default 32-bit int conversion and the call
    # raises instead of updating the style.
    GetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int]
    GetWindowLongPtrW.restype = ctypes.c_ssize_t
    SetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
    SetWindowLongPtrW.restype = ctypes.c_ssize_t

    SetParent.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    SetParent.restype = ctypes.c_void_p

    SetWindowPos = user32.SetWindowPos

    GetClientRect = user32.GetClientRect
    GetClientRect.argtypes = [ctypes.c_void_p, ctypes.c_void_p]

    GetDC = user32.GetDC
    GetDC.argtypes = [ctypes.c_void_p]
    GetDC.restype = ctypes.c_void_p

    ReleaseDC = user32.ReleaseDC
    ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]

    PrintWindow = user32.PrintWindow
    PrintWindow.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint]

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

    HWND_TOP = 0

    SWP_NOSIZE = 0x0001
    SWP_NOMOVE = 0x0002
    SWP_NOZORDER = 0x0004
    SWP_NOACTIVATE = 0x0010
    SWP_FRAMECHANGED = 0x0020
    SWP_SHOWWINDOW = 0x0040
    # Post the reposition to the target window's own thread instead of sending
    # it synchronously, so a cross-process reposition never blocks the caller
    # on the target's (FFplay's) message pump.
    SWP_ASYNCWINDOWPOS = 0x4000

    SetWindowPos.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint,
    ]
    SetWindowPos.restype = ctypes.c_bool

    PW_CLIENTONLY = 0x00000001
    PW_RENDERFULLCONTENT = 0x00000002

    PostMessageW = user32.PostMessageW
    PostMessageW.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint,
        ctypes.c_size_t,
        ctypes.c_ssize_t,
    ]

    GetForegroundWindow = user32.GetForegroundWindow
    GetForegroundWindow.argtypes = []
    GetForegroundWindow.restype = ctypes.c_void_p

    class _FLASHWINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", ctypes.c_uint),
            ("hwnd", ctypes.c_void_p),
            ("dwFlags", ctypes.c_uint),
            ("uCount", ctypes.c_uint),
            ("dwTimeout", ctypes.c_uint),
        ]

    FlashWindowEx = user32.FlashWindowEx
    FlashWindowEx.argtypes = [ctypes.POINTER(_FLASHWINFO)]
    FlashWindowEx.restype = ctypes.c_bool

    FLASHW_STOP = 0
    FLASHW_ALL = 0x00000003
    FLASHW_TIMERNOFG = 0x0000000C

    WM_KEYDOWN = 0x0100
    WM_KEYUP = 0x0101
    VK_SPACE = 0x20
    # lParam with the spacebar's scancode (0x39) in bits 16-23; key-up adds
    # the previous-state and transition bits.
    SPACE_LPARAM_DOWN = 0x00390001
    SPACE_LPARAM_UP = -(0x100000000 - 0xC0390001)

    gdi32 = ctypes.windll.gdi32

    class _BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", ctypes.c_uint32),
            ("biWidth", ctypes.c_int32),
            ("biHeight", ctypes.c_int32),
            ("biPlanes", ctypes.c_uint16),
            ("biBitCount", ctypes.c_uint16),
            ("biCompression", ctypes.c_uint32),
            ("biSizeImage", ctypes.c_uint32),
            ("biXPelsPerMeter", ctypes.c_int32),
            ("biYPelsPerMeter", ctypes.c_int32),
            ("biClrUsed", ctypes.c_uint32),
            ("biClrImportant", ctypes.c_uint32),
        ]

    class _BITMAPINFO(ctypes.Structure):
        _fields_ = [
            ("bmiHeader", _BITMAPINFOHEADER),
            ("bmiColors", ctypes.c_uint32 * 3),
        ]

    CreateCompatibleDC = gdi32.CreateCompatibleDC
    CreateCompatibleDC.argtypes = [ctypes.c_void_p]
    CreateCompatibleDC.restype = ctypes.c_void_p

    CreateDIBSection = gdi32.CreateDIBSection
    CreateDIBSection.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(_BITMAPINFO),
        ctypes.c_uint,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_void_p,
        ctypes.c_uint32,
    ]
    CreateDIBSection.restype = ctypes.c_void_p

    SelectObject = gdi32.SelectObject
    SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    SelectObject.restype = ctypes.c_void_p

    DeleteObject = gdi32.DeleteObject
    DeleteObject.argtypes = [ctypes.c_void_p]

    DeleteDC = gdi32.DeleteDC
    DeleteDC.argtypes = [ctypes.c_void_p]

    kernel32 = ctypes.windll.kernel32

    class _IO_COUNTERS(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint64) for name in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
        )]

    class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", ctypes.c_uint32),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", ctypes.c_uint32),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", ctypes.c_uint32),
            ("SchedulingClass", ctypes.c_uint32),
        ]

    class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", _IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    JobObjectExtendedLimitInformation = 9
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000

    CreateJobObjectW = kernel32.CreateJobObjectW
    CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
    CreateJobObjectW.restype = ctypes.c_void_p

    SetInformationJobObject = kernel32.SetInformationJobObject
    SetInformationJobObject.argtypes = [
        ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32
    ]

    AssignProcessToJobObject = kernel32.AssignProcessToJobObject
    AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]

    _cleanup_job = None
else:
    # Non-Windows stubs so importing modules never fails. Every caller is
    # already guarded by IS_WINDOWS before touching these.
    IsWindow = None
    MoveWindow = None
    UpdateWindow = None


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


def find_child_window_for_pid(parent_hwnd: int, pid: int) -> int | None:
    """First descendant window of parent_hwnd owned by `pid`, or None.

    mpv launched with --wid=<parent> creates its video window as a CHILD of
    the given HWND, which find_main_window_for_pid (top-level only) cannot see.
    Prefers the window whose class is "mpv".
    """
    if not IS_WINDOWS or not parent_hwnd:
        return None

    candidates: list[int] = []

    def callback(hwnd, _):
        found_pid = ctypes.c_ulong()
        GetWindowThreadProcessId(hwnd, ctypes.byref(found_pid))
        if found_pid.value == pid:
            candidates.append(hwnd)
        return True

    try:
        EnumChildWindows(parent_hwnd, EnumWindowsProc(callback), 0)
    except Exception:
        return None

    for hwnd in candidates:
        if _window_class(hwnd) == "mpv":
            return hwnd
    return candidates[0] if candidates else None


def embed_external_window_hidden(child_hwnd: int, parent_hwnd: int, width: int, height: int):
    """
    Re-parents an external native window into a Tkinter frame WITHOUT showing it.

    The window stays hidden through the whole restyle/SetParent/position
    sequence; FFplay's own first-frame ShowWindow then reveals it when it is
    already a child of the preview frame. Setting WS_VISIBLE before SetParent
    (as the previous embed helper did) let the unpainted SDL window flash at
    its spawn position in the middle of the desktop.

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
    style |= WS_CLIPSIBLINGS
    style |= WS_CLIPCHILDREN

    ex_style &= ~WS_EX_APPWINDOW
    ex_style |= WS_EX_TOOLWINDOW

    SetWindowLongPtrW(child_hwnd, GWL_STYLE, style)
    SetWindowLongPtrW(child_hwnd, GWL_EXSTYLE, ex_style)

    SetParent(child_hwnd, parent_hwnd)

    # Input-transparent embed (M10): a disabled child window is skipped by
    # the system's mouse routing, so clicks over live video fall through to
    # the Tk preview frame underneath (which owns the preview gestures) and
    # FFplay's own built-in mouse seeking/fullscreen can never fire. Posted
    # messages (the pause spacebar) still reach a disabled window's wndproc,
    # and it can no longer steal keyboard focus from Tk.
    disable_window_input(child_hwnd)

    SetWindowPos(
        child_hwnd,
        0,
        0,
        0,
        width,
        height,
        SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
    )

    MoveWindow(child_hwnd, 0, 0, width, height, True)

    return True


def anchor_child_window(hwnd: int | None, width: int, height: int, show: bool = True):
    """
    Pins an embedded child window back to (0, 0) at the given size. FFplay's
    video_open() repositions/resizes its SDL window when the first frame is
    ready, which can land after the embed; this snaps it back.

    Uses SetWindowPos with SWP_ASYNCWINDOWPOS: the reposition is POSTED to
    FFplay's own thread rather than sent synchronously, so this never blocks
    the Tk thread on FFplay's message pump. That matters because this runs on
    the resize path (on_preview_frame_resize -> apply_size), which Tk can
    dispatch *inside* Windows' modal move/size loop — an edge-resize or a
    header drag that Aero-snaps. A synchronous MoveWindow/UpdateWindow there
    waits on FFplay and stalls the whole drag loop (the "freeze on resizing").
    FFplay repaints itself on its next frame, so no forced UpdateWindow is
    needed. Never call while the owning process is suspended.

    show=True reveals the window and raises it to the top of the preview frame
    (first-frame reveal); show=False keeps the current visibility and z-order
    (live resize).
    """
    if not IS_WINDOWS or not hwnd:
        return

    try:
        if not IsWindow(hwnd):
            return
        flags = SWP_NOACTIVATE | SWP_ASYNCWINDOWPOS
        flags |= SWP_SHOWWINDOW if show else SWP_NOZORDER
        SetWindowPos(hwnd, HWND_TOP, 0, 0, max(1, int(width)), max(1, int(height)), flags)
    except Exception:
        pass


def raise_window_to_top(hwnd: int | None):
    """
    Posts an async raise-to-top for a child window (no move/size/focus).

    The focus HUD chips (B5) sit over the live video and must out-stack the
    embedded player window, which anchor_child_window re-raises to HWND_TOP
    on every first-frame reveal. Async for the same reason as
    anchor_child_window: never block the Tk thread on another window's
    message pump.
    """
    if not IS_WINDOWS or not hwnd:
        return

    try:
        if IsWindow(hwnd):
            SetWindowPos(hwnd, HWND_TOP, 0, 0, 0, 0,
                         SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_ASYNCWINDOWPOS)
    except Exception:
        pass


def disable_window_input(hwnd: int | None):
    """Make an embedded child window input-transparent: the system skips
    disabled windows when routing mouse input, so clicks land on the Tk
    parent instead. Posted messages still arrive at its wndproc."""
    if not IS_WINDOWS or not hwnd:
        return
    try:
        if IsWindow(hwnd):
            EnableWindow(hwnd, 0)
    except Exception:
        pass


def show_native_window(hwnd: int | None):
    if not IS_WINDOWS or not hwnd:
        return

    try:
        if IsWindow(hwnd):
            ShowWindow(hwnd, SW_SHOW)
    except Exception:
        pass


def post_pause_key_to_window(hwnd: int | None) -> bool:
    """
    Toggles FFplay's own pause by posting a spacebar press to its SDL window.

    Unlike the old attempt at this, the posted messages carry a real scancode
    in lParam (SDL derives its key events from the scancode bits, so lParam=0
    gets dropped) and no cross-thread SetFocus is involved (which silently
    fails without AttachThreadInput). Verified working on FFmpeg 8.0's SDL
    build, including while embedded.

    FFplay handles all A/V clock bookkeeping across its native pause, so no
    process suspension is needed anywhere — which matters, because suspending
    a process that owns a window in (or ever attached to) our window tree
    freezes Tk the moment any activation/z-order/geometry change sends that
    window a synchronous message.
    """
    if not IS_WINDOWS or not hwnd:
        return False

    try:
        if not IsWindow(hwnd):
            return False

        PostMessageW(hwnd, WM_KEYDOWN, VK_SPACE, SPACE_LPARAM_DOWN)
        PostMessageW(hwnd, WM_KEYUP, VK_SPACE, SPACE_LPARAM_UP)
        return True
    except Exception:
        return False


def is_foreground_process() -> bool:
    """
    True when the window the user is working in belongs to this process.

    Embedded player windows are WS_CHILD after SetParent and can never hold
    foreground themselves — activation lands on their top-level ancestor (the
    Tk root) — so comparing the foreground window's process id against our own
    covers the main window, dialog/settings toplevels, and embedded previews.

    A minimized window can still be reported as the foreground window (Windows
    leaves foreground on it after a programmatic or button minimize until the
    user activates something else), so iconic counts as "not looking at it".
    """
    if not IS_WINDOWS:
        return True

    try:
        hwnd = GetForegroundWindow()
        if not hwnd:
            return False
        if IsIconic(hwnd):
            return False

        pid = ctypes.wintypes.DWORD(0)
        GetWindowThreadProcessId(ctypes.c_void_p(hwnd), ctypes.byref(pid))
        return pid.value == os.getpid()
    except Exception:
        # Fail toward "focused" so callers never flash spuriously.
        return True


def flash_taskbar(hwnd: int | None, until_focused: bool = True) -> bool:
    """
    Flashes the window's caption and taskbar button to request attention.

    With until_focused, Windows keeps the taskbar button lit until the user
    brings the window to the foreground and then stops it on its own
    (FLASHW_TIMERNOFG) — no stop bookkeeping needed here. Returns the previous
    flash state (True if the window was already flashing).
    """
    if not IS_WINDOWS or not hwnd:
        return False

    try:
        if not IsWindow(hwnd):
            return False

        info = _FLASHWINFO()
        info.cbSize = ctypes.sizeof(_FLASHWINFO)
        info.hwnd = hwnd
        info.dwFlags = (FLASHW_ALL | FLASHW_TIMERNOFG) if until_focused else FLASHW_ALL
        info.uCount = 0
        info.dwTimeout = 0
        return bool(FlashWindowEx(ctypes.byref(info)))
    except Exception:
        return False


# ============================================================
# Taskbar progress (ITaskbarList3) — roadmap L2
# ============================================================

if IS_WINDOWS:
    ole32 = ctypes.windll.ole32

    class _GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", ctypes.c_uint32),
            ("Data2", ctypes.c_uint16),
            ("Data3", ctypes.c_uint16),
            ("Data4", ctypes.c_ubyte * 8),
        ]

    def _make_guid(d1, d2, d3, tail):
        g = _GUID()
        g.Data1, g.Data2, g.Data3 = d1, d2, d3
        for i, b in enumerate(tail):
            g.Data4[i] = b
        return g

    # CLSID_TaskbarList {56FDF344-FD6D-11D0-958A-006097C9A090}
    _CLSID_TaskbarList = _make_guid(
        0x56FDF344, 0xFD6D, 0x11D0,
        (0x95, 0x8A, 0x00, 0x60, 0x97, 0xC9, 0xA0, 0x90))
    # IID_ITaskbarList3 {EA1AFB91-9E28-4B86-90E9-9E9F8A5EEFAF}
    _IID_ITaskbarList3 = _make_guid(
        0xEA1AFB91, 0x9E28, 0x4B86,
        (0x90, 0xE9, 0x9E, 0x9F, 0x8A, 0x5E, 0xEF, 0xAF))

    _CLSCTX_INPROC_SERVER = 0x1
    _COINIT_APARTMENTTHREADED = 0x2

# TBPFLAG progress states (defined on every OS; only used on Windows).
TBPF_NOPROGRESS = 0x0
TBPF_INDETERMINATE = 0x1
TBPF_NORMAL = 0x2
TBPF_ERROR = 0x4


class TaskbarProgress:
    """ITaskbarList3 taskbar-button progress (L2), hand-rolled over the COM
    vtable with ctypes (no comtypes/pywin32 dependency).

    Per-export lifecycle: begin() lazily creates a fresh COM object, and
    clear()/shutdown() release it. Recreating each run sidesteps the pointer
    invalidation an Explorer restart causes on a long-lived object, and any
    failed vtable call resets the pointer so the next begin() rebuilds it.
    All methods must run on the STA (Tk main) thread — callers marshal via
    app.ui(). Every method is a silent no-op off Windows or if COM is
    unavailable, so wiring never needs its own guards.
    """

    def __init__(self):
        self._ptr = None
        self._co_init = False
        self._set_value = None
        self._set_state = None
        self._release = None

    def _ensure(self) -> bool:
        if not IS_WINDOWS:
            return False
        if self._ptr is not None:
            return True
        try:
            if not self._co_init:
                # S_OK / S_FALSE (already STA) are fine; RPC_E_CHANGED_MODE
                # (already MTA) is returned, not raised, by windll — COM is
                # still usable, so proceed either way.
                ole32.CoInitializeEx(None, _COINIT_APARTMENTTHREADED)
                self._co_init = True
            ptr = ctypes.c_void_p()
            hr = ole32.CoCreateInstance(
                ctypes.byref(_CLSID_TaskbarList), None, _CLSCTX_INPROC_SERVER,
                ctypes.byref(_IID_ITaskbarList3), ctypes.byref(ptr))
            if hr != 0 or not ptr.value:
                return False
            vtbl = ctypes.cast(ptr, ctypes.POINTER(ctypes.c_void_p))[0]
            fns = ctypes.cast(vtbl, ctypes.POINTER(ctypes.c_void_p))
            hres = ctypes.c_long
            self._release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(fns[2])
            # ITaskbarList3 vtable ordinals: SetProgressValue=9, SetProgressState=10.
            self._set_value = ctypes.WINFUNCTYPE(
                hres, ctypes.c_void_p, ctypes.c_void_p,
                ctypes.c_ulonglong, ctypes.c_ulonglong)(fns[9])
            self._set_state = ctypes.WINFUNCTYPE(
                hres, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int)(fns[10])
            self._ptr = ptr
            hr_init = ctypes.WINFUNCTYPE(hres, ctypes.c_void_p)(fns[3])  # HrInit
            if hr_init(ptr) != 0:
                self._reset()
                return False
            return True
        except Exception:
            self._reset()
            return False

    def _reset(self):
        ptr, rel = self._ptr, self._release
        self._ptr = self._set_value = self._set_state = self._release = None
        if ptr is not None and rel is not None:
            try:
                rel(ptr)
            except Exception:
                pass

    def begin(self, hwnd, indeterminate: bool = False):
        """Start showing progress on the taskbar button. Indeterminate is the
        marquee used for the compression tuner (per-attempt resets map poorly
        to a determinate bar); otherwise a green 0% bar ready for value()."""
        if not hwnd or not self._ensure():
            return
        try:
            if indeterminate:
                self._set_state(self._ptr, hwnd, TBPF_INDETERMINATE)
            else:
                self._set_state(self._ptr, hwnd, TBPF_NORMAL)
                self._set_value(self._ptr, hwnd, 0, 100)
        except Exception:
            self._reset()

    def value(self, hwnd, percent: int):
        """Update the determinate bar (ignored while no object is live, e.g.
        an indeterminate compression run never calls this)."""
        if not hwnd or self._ptr is None:
            return
        try:
            pct = max(0, min(100, int(percent)))
            self._set_value(self._ptr, hwnd, pct, 100)
        except Exception:
            self._reset()

    def clear(self, hwnd):
        """Remove the progress state and release the object."""
        if self._ptr is None:
            return
        try:
            if hwnd:
                self._set_state(self._ptr, hwnd, TBPF_NOPROGRESS)
        except Exception:
            pass
        self._reset()

    def shutdown(self):
        """Release any live object (app close)."""
        self._reset()


def capture_window_frame(hwnd: int | None) -> tuple[bytes, int, int] | None:
    """
    Snapshots the client area of a window as raw top-down BGRA bytes.

    Used to freeze the exact on-screen frame at pause time, before the FFplay
    window is hidden and its process suspended. PW_RENDERFULLCONTENT makes DWM
    include hardware-rendered (D3D/SDL) content that plain GDI blits miss.

    Only call while the window's owning thread is running: PrintWindow
    delivers a synchronous message to that thread, so a suspended target
    would deadlock the caller.
    """
    if not IS_WINDOWS or not hwnd:
        return None

    try:
        if not IsWindow(hwnd):
            return None

        rect = ctypes.wintypes.RECT()
        if not GetClientRect(hwnd, ctypes.byref(rect)):
            return None

        width = int(rect.right - rect.left)
        height = int(rect.bottom - rect.top)
        if width <= 0 or height <= 0:
            return None

        screen_dc = GetDC(None)
        if not screen_dc:
            return None

        mem_dc = None
        bitmap = None
        try:
            mem_dc = CreateCompatibleDC(screen_dc)
            if not mem_dc:
                return None

            bmi = _BITMAPINFO()
            bmi.bmiHeader.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
            bmi.bmiHeader.biWidth = width
            bmi.bmiHeader.biHeight = -height  # negative = top-down rows
            bmi.bmiHeader.biPlanes = 1
            bmi.bmiHeader.biBitCount = 32
            bmi.bmiHeader.biCompression = 0  # BI_RGB

            bits = ctypes.c_void_p()
            bitmap = CreateDIBSection(
                mem_dc, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0
            )
            if not bitmap or not bits:
                return None

            previous = SelectObject(mem_dc, bitmap)
            ok = PrintWindow(hwnd, mem_dc, PW_CLIENTONLY | PW_RENDERFULLCONTENT)
            data = ctypes.string_at(bits, width * height * 4) if ok else None
            SelectObject(mem_dc, previous)
        finally:
            if bitmap:
                DeleteObject(bitmap)
            if mem_dc:
                DeleteDC(mem_dc)
            ReleaseDC(None, screen_dc)

        if not data:
            return None

        # An all-zero capture means PrintWindow gave us nothing usable; let the
        # caller fall back to a real frame extract instead of a black card.
        if not any(data[::491]):
            return None

        return data, width, height
    except Exception:
        return None


def assign_process_to_cleanup_job(process) -> bool:
    """
    Ties a child process's lifetime to ours via a kill-on-close job object:
    if this app exits for ANY reason (including Task Manager or a crash), the
    OS closes our job handle and terminates every process assigned to it. Our
    graceful teardown paths still kill children explicitly; this is the
    backstop for the ungraceful ones, so ffplay/ffmpeg can never be orphaned.
    """
    if not IS_WINDOWS or process is None:
        return False

    global _cleanup_job

    try:
        if _cleanup_job is None:
            job = CreateJobObjectW(None, None)
            if not job:
                return False
            info = _JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
            info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not SetInformationJobObject(
                job,
                JobObjectExtendedLimitInformation,
                ctypes.byref(info),
                ctypes.sizeof(info),
            ):
                return False
            _cleanup_job = job

        handle = getattr(process, "_handle", None)
        if not handle:
            return False
        return bool(AssignProcessToJobObject(_cleanup_job, handle))
    except Exception:
        return False


def set_clipboard_dib(dib_bytes: bytes) -> bool:
    """Put a device-independent bitmap on the Windows clipboard as CF_DIB.

    `dib_bytes` is a BMP file's contents with the 14-byte BITMAPFILEHEADER
    stripped (i.e. starting at the BITMAPINFOHEADER) — the caller builds this
    from PIL. Tk's own clipboard can't carry images, hence the raw Win32 path.
    """
    if not IS_WINDOWS or not dib_bytes:
        return False

    CF_DIB = 8
    GMEM_MOVEABLE = 0x0002

    GlobalAlloc = kernel32.GlobalAlloc
    GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
    GlobalAlloc.restype = ctypes.c_void_p
    GlobalLock = kernel32.GlobalLock
    GlobalLock.argtypes = [ctypes.c_void_p]
    GlobalLock.restype = ctypes.c_void_p
    GlobalUnlock = kernel32.GlobalUnlock
    GlobalUnlock.argtypes = [ctypes.c_void_p]

    OpenClipboard = user32.OpenClipboard
    OpenClipboard.argtypes = [ctypes.c_void_p]
    EmptyClipboard = user32.EmptyClipboard
    SetClipboardData = user32.SetClipboardData
    SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
    SetClipboardData.restype = ctypes.c_void_p
    CloseClipboard = user32.CloseClipboard

    handle = GlobalAlloc(GMEM_MOVEABLE, len(dib_bytes))
    if not handle:
        return False

    locked = GlobalLock(handle)
    if not locked:
        return False
    ctypes.memmove(locked, dib_bytes, len(dib_bytes))
    GlobalUnlock(handle)

    if not OpenClipboard(None):
        return False
    try:
        EmptyClipboard()
        if not SetClipboardData(CF_DIB, handle):
            return False
        # Ownership of the handle passed to the clipboard on success.
        return True
    finally:
        CloseClipboard()


def hide_native_window(hwnd: int | None):
    if not IS_WINDOWS or not hwnd:
        return

    try:
        if IsWindow(hwnd):
            ShowWindow(hwnd, SW_HIDE)
    except Exception:
        pass
