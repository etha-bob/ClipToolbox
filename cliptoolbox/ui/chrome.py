"""Borderless window chrome.

Strips WS_CAPTION while keeping WS_THICKFRAME + min/max boxes, so the window
keeps native edge-resizing, Windows snap (drag-to-edge and Win+arrows),
taskbar presence, and minimize/restore — only the title bar goes away, and
the app draws its own Halo header.

Falls back to a DWM dark native title bar when stripping fails (or when the
user opts out via settings).
"""
import ctypes

from cliptoolbox.constants import IS_WINDOWS
from cliptoolbox.ui import theme

WM_NCLBUTTONDOWN = 0x00A1
HTCAPTION = 2

GWL_STYLE = -16
WS_CAPTION = 0x00C00000
WS_THICKFRAME = 0x00040000
WS_MINIMIZEBOX = 0x00020000
WS_MAXIMIZEBOX = 0x00010000
WS_SYSMENU = 0x00080000

SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_FRAMECHANGED = 0x0020

DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_USE_IMMERSIVE_DARK_MODE_OLD = 19
DWMWA_BORDER_COLOR = 34


def _user32():
    return ctypes.windll.user32


def get_root_hwnd(root) -> int | None:
    if not IS_WINDOWS:
        return None
    try:
        root.update_idletasks()
        return _user32().GetParent(root.winfo_id())
    except Exception:
        return None


def _colorref(hex_color: str) -> int:
    r = int(hex_color[1:3], 16)
    g = int(hex_color[3:5], 16)
    b = int(hex_color[5:7], 16)
    return (b << 16) | (g << 8) | r


def _strip_caption(hwnd: int) -> bool:
    user32 = _user32()
    if hasattr(user32, "GetWindowLongPtrW"):
        get_long, set_long = user32.GetWindowLongPtrW, user32.SetWindowLongPtrW
    else:
        get_long, set_long = user32.GetWindowLongW, user32.SetWindowLongW

    style = get_long(hwnd, GWL_STYLE)
    if not style:
        return False

    style &= ~WS_CAPTION
    style |= WS_THICKFRAME | WS_MINIMIZEBOX | WS_MAXIMIZEBOX | WS_SYSMENU
    set_long(hwnd, GWL_STYLE, style)
    user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0,
                        SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_FRAMECHANGED)
    return True


def _tint_native_border(hwnd: int):
    """Win11: color the residual 1px frame to match the theme. No-op on Win10."""
    try:
        color = ctypes.c_int(_colorref(theme.BG_DEEP))
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_BORDER_COLOR, ctypes.byref(color), ctypes.sizeof(color))
    except Exception:
        pass


def apply_borderless(root) -> bool:
    """Strip the native title bar. Returns False if it could not be applied
    (caller should fall back to apply_dark_titlebar)."""
    if not IS_WINDOWS:
        return False

    hwnd = get_root_hwnd(root)
    if not hwnd:
        return False

    try:
        if not _strip_caption(hwnd):
            return False
        _tint_native_border(hwnd)
    except Exception:
        return False

    # Some Tk builds re-apply WS_CAPTION when the window is restored from
    # the taskbar; re-strip on every map.
    def restrip(_event=None):
        try:
            h = get_root_hwnd(root)
            if h:
                _strip_caption(h)
        except Exception:
            pass

    root.bind("<Map>", restrip, add="+")
    return True


def apply_dark_titlebar(root) -> bool:
    """Fallback: keep the native title bar but flip it dark via DWM."""
    if not IS_WINDOWS:
        return False

    hwnd = get_root_hwnd(root)
    if not hwnd:
        return False

    value = ctypes.c_int(1)
    for attr in (DWMWA_USE_IMMERSIVE_DARK_MODE, DWMWA_USE_IMMERSIVE_DARK_MODE_OLD):
        try:
            result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, attr, ctypes.byref(value), ctypes.sizeof(value))
            if result == 0:
                return True
        except Exception:
            continue
    return False


def begin_drag(root):
    """Hand the drag off to Windows so snap/aero behaviors apply."""
    if not IS_WINDOWS:
        return
    hwnd = get_root_hwnd(root)
    if not hwnd:
        return
    try:
        _user32().ReleaseCapture()
        _user32().SendMessageW(hwnd, WM_NCLBUTTONDOWN, HTCAPTION, 0)
    except Exception:
        pass


def is_maximized(root) -> bool:
    try:
        return root.state() == "zoomed"
    except Exception:
        return False


def toggle_maximize(root):
    try:
        root.state("normal" if is_maximized(root) else "zoomed")
    except Exception:
        pass
