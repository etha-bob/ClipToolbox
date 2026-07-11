"""Private (no-install) loading of the bundled Rajdhani fonts.

Rajdhani (OFL) is the closest free match to Conduit ITC, the typeface used by
Halo 2's menus. Fonts are registered process-private via AddFontResourceExW
so nothing is installed system-wide; if loading fails the UI falls back to
Segoe UI without shifting layout (metrics come from the theme, not the font).

A skin may prefer a system typeface instead (Reach -> Bahnschrift): the
preference only takes effect once verify_with_tk confirms the family really
exists, so a missing font degrades to Rajdhani rather than to Tk's silent
default-family substitution.
"""
import ctypes
import os
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

# Skin typeface preference (set by theme at import; resolved lazily).
_pref_tk_candidates: tuple[str, ...] = ()
_pref_tk_family: str | None = None      # candidate confirmed by verify_with_tk
_pref_pil_path: Path | None = None
_pref_pil_variations: dict[str, str] = {}


def set_skin_preference(tk_candidates, pil_file, pil_variations):
    """Record the active skin's preferred system typeface.

    Called by cliptoolbox.ui.theme during import, before any widget exists.
    The Tk side is confirmed later by verify_with_tk; the PIL side just needs
    the TTF to exist on disk.
    """
    global _pref_tk_candidates, _pref_pil_path, _pref_pil_variations

    _pref_tk_candidates = tuple(tk_candidates or ())
    _pref_pil_variations = dict(pil_variations or {})

    _pref_pil_path = None
    if pil_file:
        candidate = Path(pil_file)
        if not candidate.is_absolute():
            windir = os.environ.get("WINDIR", r"C:\Windows")
            candidate = Path(windir) / "Fonts" / candidate
        if candidate.exists():
            _pref_pil_path = candidate


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
    if _pref_tk_family is not None:
        return _pref_tk_family
    return FAMILY if _available else FALLBACK_FAMILY


def describe() -> str:
    """Human-readable credit line for the About section."""
    active = family()
    if active == FAMILY:
        return f"{FAMILY} (OFL)"
    return f"{active} (system)"


def verify_with_tk(root) -> bool:
    """Confirm Tk can actually see the expected families; downgrades on failure.

    Resolves the skin's preferred system family against Tk's list, and checks
    the bundled Rajdhani registration as before.
    """
    global _available, _pref_tk_family

    try:
        from tkinter import font as tkfont

        families = {f.lower() for f in tkfont.families(root)}
    except Exception:
        _available = False
        _pref_tk_family = None
        return False

    _pref_tk_family = next(
        (name for name in _pref_tk_candidates if name.lower() in families), None)

    if _available:
        _available = FAMILY.lower() in families

    return _available or _pref_tk_family is not None


def pil_font_path(weight: str = "Medium") -> Path | None:
    """TTF path for PIL text rendering (glow underlays, panel titles)."""
    for name in (f"{FAMILY}-{weight}", f"{FAMILY}-Regular"):
        if name in _font_files:
            return _font_files[name]

    for path in _font_files.values():
        return path

    return None


def pil_font(size: int, weight: str = "Medium"):
    """ImageFont honoring the skin's typeface preference; None if no TTF.

    The preferred file may be a variable font (Bahnschrift), so the weight is
    selected via its named instances; the bundled Rajdhani ships per-weight
    files instead.
    """
    from PIL import ImageFont

    if _pref_pil_path is not None:
        try:
            font = ImageFont.truetype(str(_pref_pil_path), size)
            variation = _pref_pil_variations.get(weight)
            if variation:
                try:
                    font.set_variation_by_name(variation)
                except Exception:
                    pass
            return font
        except Exception:
            pass

    path = pil_font_path(weight)
    if path is None:
        return None
    try:
        return ImageFont.truetype(str(path), size)
    except Exception:
        return None
