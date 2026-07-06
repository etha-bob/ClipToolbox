import ctypes
import subprocess

from cliptoolbox.constants import IS_WINDOWS

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
