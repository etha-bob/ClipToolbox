"""Halo 2 (2004) skin — the original ClipToolbox look.

Palette and geometry are derived from the original game's pregame lobby and
Project Cartographer reference screenshots. This module is the token schema
of record: every skin must define the same UPPERCASE names (enforced by
cliptoolbox.ui.skins.get).
"""

SKIN_ID = "halo2"
SKIN_LABEL = "Halo 2"

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
SELECT_TEXT = TEXT_BRIGHT  # text sitting on SELECT_FILL

TITLE_FILL = SELECT_FILL   # dialog / settings header strip
TITLE_TEXT = TEXT_BRIGHT

MAROON = "#7E2B3E"         # destructive actions
MAROON_HI = "#9A3A50"
ROSTER = MAROON            # lobby player-bar rows (H2 keeps them maroon)

OK_GREEN = "#35A854"
ERR_RED = "#C23B2E"
TRIM_IN = "#58C973"        # trim start bracket (was "green")
TRIM_OUT = "#E0556B"       # trim end bracket (was "red")

SEEK_TRACK = "#0C1E33"
SEEK_CELL = "#122B47"      # alternating frame cells on the zoomed timeline
WAVE = "#2E71A8"           # timeline waveform lanes (normal mix state)
ENTRY_FILL = "#0A1B2E"
WELL_FILL = "#0A1626"      # thumbnail letterbox wells
DISABLED_FILL = "#0B1B2C"  # disabled entry / segmented cells

BTN_PRIMARY_HI = BAR_HI
BTN_PRIMARY_LO = BAR_LO
BTN_PRIMARY_BORDER = PANEL_BORDER
BTN_PRIMARY_TEXT = TEXT_BRIGHT
BTN_DANGER_BORDER = "#B06A78"

# ------------------------------------------------------------------
# Geometry (unscaled; consumers go through theme.px)
# ------------------------------------------------------------------

CHAMFER = 10          # 45-degree corner cut on panels/cards
CHAMFER_SMALL = 6     # buttons, small controls
CHECK_CHAMFER = 3     # checkbox corner cut (supersample units, not DPI-scaled)
HANDLE_CHAMFER = 0.35  # slider handle corner cut as a fraction of its size
BAR_SKEW = 16         # horizontal slant of header/footer bar ends
HEADER_H = 40
FOOTER_H = 30
BTN_H = 34
BTN_PRIMARY_H = 44
MENU_ITEM_H = 46
CHECK_SIZE = 18
SLIDER_H = 22
SEEKBAR_H = 104  # timeline strip: minimap/ruler/filmstrip/audio/keyframe lanes
ENTRY_H = 30

PAD = 12
GAP = 8

# ------------------------------------------------------------------
# Style switches (which renderer variants the chrome uses)
# ------------------------------------------------------------------

BACKDROP_STYLE = "halo2"      # window background: tick rows + glyph strips
MENU_SELECT_STYLE = "halo2"   # landing menu hover: fill bar + accent strip
HOVER_BRACKETS = True         # H2 corner-bracket selection reticle

# ------------------------------------------------------------------
# Typeface — None keeps the bundled Rajdhani (closest free Conduit match).
# ------------------------------------------------------------------

FONT_TK_CANDIDATES: tuple[str, ...] = ()
FONT_PIL_FILE = None          # filename under the system font dir, or None
FONT_PIL_VARIATIONS: dict[str, str] = {}
