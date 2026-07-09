"""Native window chrome helpers.

ClipToolbox always uses the real Windows title bar now — a borderless
custom-header mode used to be an option here, but the drag/maximize
handling it needed (handing off to Win32's native modal move loop, or
subclassing the window to fix maximize-covers-taskbar) turned out to
crash reliably: those calls happen from inside an already-active Tcl
callback, and Win32's nested modal loop reenters Tcl/Python from within
that call frame, corrupting CPython's GIL/thread-state. Not worth it —
this module now only flips the native title bar dark to match the theme.
"""
import ctypes

from cliptoolbox.constants import IS_WINDOWS

DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_USE_IMMERSIVE_DARK_MODE_OLD = 19


def get_root_hwnd(root) -> int | None:
    if not IS_WINDOWS:
        return None
    try:
        root.update_idletasks()
        return ctypes.windll.user32.GetParent(root.winfo_id())
    except Exception:
        return None


def apply_dark_titlebar(root) -> bool:
    """Flip the native title bar dark via DWM to match the app theme."""
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
