"""Halo: Reach (2010) skin.

Palette and shapes follow the game's main menu / Armory screens: desaturated
slate-teal fields with a fine diamond-plate texture, rectangular panels with
thin steel borders, and the signature pale-silver selection band with dark
ink text. The party roster rows go military green (the MY PARTY player bar);
destructive actions keep a muted brick red.

Typeface: Bahnschrift (the DIN 1451 revival that ships with Windows 10+) is
the closest system match to Reach's condensed grotesque; when it is missing
the skin silently falls back to the bundled Rajdhani.
"""

SKIN_ID = "reach"
SKIN_LABEL = "Halo Reach"

# ------------------------------------------------------------------
# Palette
# ------------------------------------------------------------------

BG_DEEP = "#0D161E"        # window base — deep slate-teal
BG_DEEPER = "#060B10"      # vignette edges
PANEL_FILL = "#131F29"     # panel interior
PANEL_FILL_HI = "#1B2A35"  # hovered rows / raised surfaces
PANEL_BORDER = "#62798A"
PANEL_BORDER_DIM = "#31434F"

BAR_HI = "#25313B"         # header/footer gradient top (smoked steel)
BAR_LO = "#131C24"
BAR_EDGE = "#9AB0BE"       # thin pale rule above the legend strip

TEXT = "#BFCBD3"
TEXT_BRIGHT = "#EDF3F6"
TEXT_DIM = "#5C6E7A"

ACCENT = "#A6C8DB"         # ice-blue glow / focus (visor tint)
ACCENT_DEEP = "#4F7590"
SELECT_FILL = "#C4CFD7"    # pale-silver selection band
SELECT_TEXT = "#111A21"    # dark ink on the silver band

TITLE_FILL = "#192530"     # dialog / settings header strip (MY PARTY bar)
TITLE_TEXT = TEXT_BRIGHT

MAROON = "#7B362E"         # destructive actions — muted brick
MAROON_HI = "#97473D"
ROSTER = "#3E5943"         # party roster green (player name bars)

OK_GREEN = "#4FA56A"
ERR_RED = "#C44A3C"
TRIM_IN = "#6FC287"        # trim start bracket
TRIM_OUT = "#DB6470"       # trim end bracket

SEEK_TRACK = "#0A1219"
SEEK_CELL = "#16222B"      # alternating frame cells on the zoomed timeline
WAVE = "#5E8298"           # timeline waveform lanes (normal mix state)
ENTRY_FILL = "#0C161E"
WELL_FILL = "#0A1117"      # thumbnail letterbox wells
DISABLED_FILL = "#152028"  # disabled entry / segmented cells

BTN_PRIMARY_HI = "#DAE2E7"     # primary buttons are the silver band
BTN_PRIMARY_LO = "#9CADB9"
BTN_PRIMARY_BORDER = "#E9EFF2"
BTN_PRIMARY_TEXT = "#10181F"
BTN_DANGER_BORDER = "#B9827A"

# ------------------------------------------------------------------
# Geometry — Reach chrome is rectangular: no chamfers, no skew.
# ------------------------------------------------------------------

CHAMFER = 0
CHAMFER_SMALL = 0
CHECK_CHAMFER = 0
HANDLE_CHAMFER = 0.12
BAR_SKEW = 0
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
# Style switches
# ------------------------------------------------------------------

BACKDROP_STYLE = "reach"      # diamond-plate weave + soft glow + vignette
MENU_SELECT_STYLE = "reach"   # silver band fading out to the right
HOVER_BRACKETS = False        # Reach highlights by value, not reticles

# ------------------------------------------------------------------
# Typeface
# ------------------------------------------------------------------

FONT_TK_CANDIDATES: tuple[str, ...] = ("Bahnschrift",)
FONT_PIL_FILE = "bahnschrift.ttf"   # resolved under the system font dir
FONT_PIL_VARIATIONS: dict[str, str] = {
    "Bold": "Bold",
    "SemiBold": "SemiBold",
    "Medium": "Regular",
}
