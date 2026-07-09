import ctypes

from cliptoolbox.constants import IS_WINDOWS

# ============================================================
# Windows native window helpers
# ============================================================

if IS_WINDOWS:
    import ctypes.wintypes

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

    SWP_NOZORDER = 0x0004
    SWP_NOACTIVATE = 0x0010
    SWP_FRAMECHANGED = 0x0020
    SWP_SHOWWINDOW = 0x0040

    PW_CLIENTONLY = 0x00000001
    PW_RENDERFULLCONTENT = 0x00000002

    PostMessageW = user32.PostMessageW
    PostMessageW.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint,
        ctypes.c_size_t,
        ctypes.c_ssize_t,
    ]

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


def anchor_child_window(hwnd: int | None, width: int, height: int):
    """
    Pins an embedded child window back to (0, 0) at the given size, showing it
    if needed. FFplay's video_open() repositions/resizes its SDL window when
    the first frame is ready, which can land after the embed; this snaps it
    back. Never call while the owning process is suspended.
    """
    if not IS_WINDOWS or not hwnd:
        return

    try:
        if not IsWindow(hwnd):
            return
        MoveWindow(hwnd, 0, 0, max(1, int(width)), max(1, int(height)), True)
        ShowWindow(hwnd, SW_SHOW)
        BringWindowToTop(hwnd)
        UpdateWindow(hwnd)
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


def hide_native_window(hwnd: int | None):
    if not IS_WINDOWS or not hwnd:
        return

    try:
        if IsWindow(hwnd):
            ShowWindow(hwnd, SW_HIDE)
    except Exception:
        pass
