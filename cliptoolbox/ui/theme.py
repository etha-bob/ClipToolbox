"""Halo 2 (2004) design tokens.

Palette and geometry are derived from the original game's pregame lobby and
Project Cartographer reference screenshots. All pixel metrics go through
px() so the skin renders crisply at any system DPI scale.
"""
from cliptoolbox.ui import dpi, fonts

# ------------------------------------------------------------------
# Palette
# ------------------------------------------------------------------

BG_DEEP = "#081420"        # window base
BG_DEEPER = "#050D16"      # vignette edges
PANEL_FILL = "#0F2740"     # panel interior
PANEL_FILL_HI = "#143352"  # hovered rows / raised surfaces
PANEL_BORDER = "#3E6E9E"
PANEL_BORDER_DIM = "#26496E"

BAR_HI = "#2E71A8"         # header/footer gradient top
BAR_LO = "#17456E"         # header/footer gradient bottom
BAR_EDGE = "#7FB8E0"       # 1px bright edge line on bars

TEXT = "#A8CBE8"
TEXT_BRIGHT = "#EAF7FF"
TEXT_DIM = "#4E7396"

ACCENT = "#7FC4EE"         # selection glow / focus
ACCENT_DEEP = "#3D89C4"
SELECT_FILL = "#1D4E79"    # selected menu item / hovered row fill

MAROON = "#7E2B3E"         # roster name bars; destructive actions
MAROON_HI = "#9A3A50"

OK_GREEN = "#35A854"
ERR_RED = "#C23B2E"
TRIM_IN = "#58C973"        # trim start bracket (was "green")
TRIM_OUT = "#E0556B"       # trim end bracket (was "red")

SEEK_TRACK = "#0C1E33"
SEEK_CELL = "#122B47"      # alternating frame cells on the zoomed timeline
ENTRY_FILL = "#0A1B2E"

# ------------------------------------------------------------------
# Geometry (unscaled; use px() everywhere)
# ------------------------------------------------------------------

CHAMFER = 10          # 45-degree corner cut on panels/cards
CHAMFER_SMALL = 6     # buttons, small controls
BAR_SKEW = 16         # horizontal slant of header/footer bar ends
HEADER_H = 40
FOOTER_H = 30
BTN_H = 34
BTN_PRIMARY_H = 44
MENU_ITEM_H = 46
CHECK_SIZE = 18
SLIDER_H = 22
SEEKBAR_H = 40  # scrubber occupies the upper band; keyframe diamonds the lower lane
ENTRY_H = 30

PAD = 12
GAP = 8


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
