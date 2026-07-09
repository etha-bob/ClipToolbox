"""System-DPI awareness for crisp rendering.

Must be initialized BEFORE the Tk root window is created. Per-monitor DPI is
deliberately not attempted: Tk 8.6 cannot handle WM_DPICHANGED, so system-DPI
awareness gives crisp rendering on the primary monitor and OS scaling
elsewhere.
"""
import ctypes

from cliptoolbox.constants import IS_WINDOWS

_scale: float | None = None


def init() -> float:
    """Enable DPI awareness and return the UI scale factor (1.0, 1.25, ...)."""
    global _scale

    if _scale is not None:
        return _scale

    _scale = 1.0

    if not IS_WINDOWS:
        return _scale

    try:
        # PROCESS_SYSTEM_DPI_AWARE = 1
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    dpi = 96.0
    try:
        dpi = float(ctypes.windll.user32.GetDpiForSystem())
    except Exception:
        try:
            hdc = ctypes.windll.user32.GetDC(0)
            LOGPIXELSX = 88
            dpi = float(ctypes.windll.gdi32.GetDeviceCaps(hdc, LOGPIXELSX))
            ctypes.windll.user32.ReleaseDC(0, hdc)
        except Exception:
            pass

    # Quarter steps keep pixel math clean (1.0, 1.25, 1.5, 1.75, 2.0).
    _scale = max(1.0, round((dpi / 96.0) * 4) / 4)
    return _scale


def scale() -> float:
    return _scale if _scale is not None else 1.0
