"""Private (no-install) loading of the bundled Rajdhani fonts.

Rajdhani (OFL) is the closest free match to Conduit ITC, the typeface used by
Halo 2's menus. Fonts are registered process-private via AddFontResourceExW
so nothing is installed system-wide; if loading fails the UI falls back to
Segoe UI without shifting layout (metrics come from the theme, not the font).
"""
import ctypes
from pathlib import Path

from cliptoolbox.constants import IS_WINDOWS
from cliptoolbox.core.paths import BASE_DIR, INTERNAL_DIR, RESOURCE_DIR

FR_PRIVATE = 0x10

FAMILY = "Rajdhani"
FALLBACK_FAMILY = "Segoe UI"

# Mirrors the tkdnd candidate probing: PyInstaller 5/6 differ on whether
# bundled data lands next to the exe or under _internal/.
ASSET_DIR_CANDIDATES = [
    RESOURCE_DIR / "assets",
    BASE_DIR / "assets",
    INTERNAL_DIR / "assets",
]

_loaded = False
_available = False
_font_files: dict[str, Path] = {}


def assets_dir() -> Path | None:
    for candidate in ASSET_DIR_CANDIDATES:
        if candidate.exists():
            return candidate
    return None


def load_private_fonts() -> bool:
    """Register bundled TTFs for this process. Safe to call more than once."""
    global _loaded, _available

    if _loaded:
        return _available

    _loaded = True

    root = assets_dir()
    if root is None:
        return _available

    font_dir = root / "fonts"
    if not font_dir.exists():
        return _available

    loaded_any = False

    for ttf in sorted(font_dir.glob("*.ttf")):
        _font_files[ttf.stem] = ttf

        if IS_WINDOWS:
            try:
                added = ctypes.windll.gdi32.AddFontResourceExW(str(ttf), FR_PRIVATE, 0)
                if added > 0:
                    loaded_any = True
            except Exception:
                pass

    _available = loaded_any
    return _available


def family() -> str:
    """Primary UI family; call after load_private_fonts()."""
    return FAMILY if _available else FALLBACK_FAMILY


def verify_with_tk(root) -> bool:
    """Confirm Tk can actually see the private family; downgrades on failure."""
    global _available

    if not _available:
        return False

    try:
        from tkinter import font as tkfont

        families = {f.lower() for f in tkfont.families(root)}
        _available = FAMILY.lower() in families
    except Exception:
        _available = False

    return _available


def pil_font_path(weight: str = "Medium") -> Path | None:
    """TTF path for PIL text rendering (glow underlays, panel titles)."""
    for name in (f"{FAMILY}-{weight}", f"{FAMILY}-Regular"):
        if name in _font_files:
            return _font_files[name]

    for path in _font_files.values():
        return path

    return None
