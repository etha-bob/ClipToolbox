"""Design tokens, resolved from the active skin.

The skin (Halo 2, Halo Reach, ...) is chosen once, at import time — before
any widget module captures a token in a default argument — from, in order:
the CLIPTOOLBOX_SKIN environment variable, the ui_skin key in config.json,
then the Halo 2 default. Everything else in the UI keeps reading `theme.X`;
switching skins at runtime is deliberately unsupported (cached PhotoImages
and constructed widgets would all go stale), which is why the settings UI
labels the choice "applies after restart".

All pixel metrics go through px() so the skin renders crisply at any system
DPI scale.
"""
import os

from cliptoolbox.ui import dpi, fonts, skins


def _resolve_skin_id() -> str:
    env = os.environ.get("CLIPTOOLBOX_SKIN")
    if env:
        return skins.normalize(env)
    try:
        from cliptoolbox import settings as app_settings

        return skins.normalize(app_settings.load().ui_skin)
    except Exception:
        return skins.DEFAULT


_ACTIVE = skins.get(_resolve_skin_id())

SKIN_ID = _ACTIVE.SKIN_ID
SKIN_LABEL = _ACTIVE.SKIN_LABEL

# ------------------------------------------------------------------
# Palette
# ------------------------------------------------------------------

BG_DEEP = _ACTIVE.BG_DEEP
BG_DEEPER = _ACTIVE.BG_DEEPER
PANEL_FILL = _ACTIVE.PANEL_FILL
PANEL_FILL_HI = _ACTIVE.PANEL_FILL_HI
PANEL_BORDER = _ACTIVE.PANEL_BORDER
PANEL_BORDER_DIM = _ACTIVE.PANEL_BORDER_DIM

BAR_HI = _ACTIVE.BAR_HI
BAR_LO = _ACTIVE.BAR_LO
BAR_EDGE = _ACTIVE.BAR_EDGE

TEXT = _ACTIVE.TEXT
TEXT_BRIGHT = _ACTIVE.TEXT_BRIGHT
TEXT_DIM = _ACTIVE.TEXT_DIM

ACCENT = _ACTIVE.ACCENT
ACCENT_DEEP = _ACTIVE.ACCENT_DEEP
SELECT_FILL = _ACTIVE.SELECT_FILL
SELECT_TEXT = _ACTIVE.SELECT_TEXT

TITLE_FILL = _ACTIVE.TITLE_FILL
TITLE_TEXT = _ACTIVE.TITLE_TEXT

MAROON = _ACTIVE.MAROON
MAROON_HI = _ACTIVE.MAROON_HI
ROSTER = _ACTIVE.ROSTER

OK_GREEN = _ACTIVE.OK_GREEN
ERR_RED = _ACTIVE.ERR_RED
TRIM_IN = _ACTIVE.TRIM_IN
TRIM_OUT = _ACTIVE.TRIM_OUT
TRIM_KEEP = _ACTIVE.TRIM_KEEP

SEEK_TRACK = _ACTIVE.SEEK_TRACK
SEEK_CELL = _ACTIVE.SEEK_CELL
WAVE = _ACTIVE.WAVE
ENTRY_FILL = _ACTIVE.ENTRY_FILL
WELL_FILL = _ACTIVE.WELL_FILL
DISABLED_FILL = _ACTIVE.DISABLED_FILL

BTN_PRIMARY_HI = _ACTIVE.BTN_PRIMARY_HI
BTN_PRIMARY_LO = _ACTIVE.BTN_PRIMARY_LO
BTN_PRIMARY_BORDER = _ACTIVE.BTN_PRIMARY_BORDER
BTN_PRIMARY_TEXT = _ACTIVE.BTN_PRIMARY_TEXT
BTN_DANGER_BORDER = _ACTIVE.BTN_DANGER_BORDER

# ------------------------------------------------------------------
# Geometry (unscaled; use px() everywhere)
# ------------------------------------------------------------------

CHAMFER = _ACTIVE.CHAMFER
CHAMFER_SMALL = _ACTIVE.CHAMFER_SMALL
CHECK_CHAMFER = _ACTIVE.CHECK_CHAMFER
HANDLE_CHAMFER = _ACTIVE.HANDLE_CHAMFER
BAR_SKEW = _ACTIVE.BAR_SKEW
HEADER_H = _ACTIVE.HEADER_H
FOOTER_H = _ACTIVE.FOOTER_H
BTN_H = _ACTIVE.BTN_H
BTN_PRIMARY_H = _ACTIVE.BTN_PRIMARY_H
MENU_ITEM_H = _ACTIVE.MENU_ITEM_H
CHECK_SIZE = _ACTIVE.CHECK_SIZE
SLIDER_H = _ACTIVE.SLIDER_H
SEEKBAR_H = _ACTIVE.SEEKBAR_H
ENTRY_H = _ACTIVE.ENTRY_H

PAD = _ACTIVE.PAD
GAP = _ACTIVE.GAP

# ------------------------------------------------------------------
# Style switches (renderer variants)
# ------------------------------------------------------------------

BACKDROP_STYLE = _ACTIVE.BACKDROP_STYLE
MENU_SELECT_STYLE = _ACTIVE.MENU_SELECT_STYLE
HOVER_BRACKETS = _ACTIVE.HOVER_BRACKETS

# The skin may prefer a system typeface (Reach -> Bahnschrift); fonts falls
# back to the bundled Rajdhani when it is not installed.
fonts.set_skin_preference(
    _ACTIVE.FONT_TK_CANDIDATES, _ACTIVE.FONT_PIL_FILE, _ACTIVE.FONT_PIL_VARIATIONS)


def px(value: float) -> int:
    return max(1, round(value * dpi.scale()))


def spx(value: float) -> int:
    """Scaled px that may be zero (for offsets)."""
    return round(value * dpi.scale())


# ------------------------------------------------------------------
# Fonts — negative sizes are pixel sizes in Tk, matching PIL px math.
# ------------------------------------------------------------------

def font_display(size: int = 30) -> tuple:
    return (fonts.family(), -px(size), "bold")


def font_menu(size: int = 19) -> tuple:
    return (fonts.family(), -px(size), "bold")


def font_title(size: int = 14) -> tuple:
    return (fonts.family(), -px(size), "bold")


def font_body(size: int = 14) -> tuple:
    return (fonts.family(), -px(size))


def font_small(size: int = 12) -> tuple:
    return (fonts.family(), -px(size))


def font_mono(size: int = 11) -> tuple:
    return ("Consolas", -px(size))
