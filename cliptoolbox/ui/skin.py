"""Pillow-rendered Halo chrome (all skins).

Tk's canvas cannot antialias, so every diagonal shape (chamfered panels,
slanted bars, glows) is rendered by Pillow at 3x supersample, downscaled with
LANCZOS, and served as a cached PhotoImage. Axis-aligned fills (progress
bars, slider tracks) stay native canvas rectangles — those are already crisp
and cheap to move every frame.

Skin differences flow in through theme tokens: colors and chamfer/skew
geometry parameterize the shared renderers (Reach zeroes the cuts for its
rectangular chrome), while the few genuinely different treatments (window
backdrop, menu selection band) dispatch on the theme's style switches.

Rendering is composited against a known `behind` color rather than relying on
Tk alpha blending, which is unreliable across Tk builds. Widgets therefore
declare the color they sit on.

The PhotoImage cache doubles as the mandatory Tk image reference holder.
"""
import random
from collections import OrderedDict

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageTk

from cliptoolbox.ui import fonts, theme
from cliptoolbox.ui.theme import px

SS = 3  # supersample factor

# ------------------------------------------------------------------
# Color helpers
# ------------------------------------------------------------------


def rgb(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return tuple(int(color[i : i + 2], 16) for i in (0, 2, 4))


def mix(c1: str, c2: str, t: float) -> tuple[int, int, int]:
    a, b = rgb(c1), rgb(c2)
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def lighten(color: str, t: float) -> tuple[int, int, int]:
    return mix(color, "#FFFFFF", t)


def darken(color: str, t: float) -> tuple[int, int, int]:
    return mix(color, "#000000", t)


# ------------------------------------------------------------------
# Shape helpers (all coordinates at supersampled resolution)
# ------------------------------------------------------------------


def chamfer_points(w: int, h: int, tl: int, tr: int, br: int, bl: int) -> list[tuple[int, int]]:
    """Polygon for a rectangle with 45-degree cut corners."""
    pts: list[tuple[int, int]] = []
    if tl:
        pts += [(0, tl), (tl, 0)]
    else:
        pts += [(0, 0)]
    if tr:
        pts += [(w - tr, 0), (w, tr)]
    else:
        pts += [(w, 0)]
    if br:
        pts += [(w, h - br), (w - br, h)]
    else:
        pts += [(w, h)]
    if bl:
        pts += [(bl, h), (0, h - bl)]
    else:
        pts += [(0, h)]
    return pts


def skew_points(w: int, h: int, skew_left: int, skew_right: int) -> list[tuple[int, int]]:
    """Parallelogram-ish bar. Positive skew slants that end outward at the top."""
    return [
        (abs(skew_left) if skew_left < 0 else 0, 0),
        (w - (skew_right if skew_right > 0 else 0), 0),
        (w - (abs(skew_right) if skew_right < 0 else 0), h),
        (skew_left if skew_left > 0 else 0, h),
    ]


def _vgradient(size: tuple[int, int], top: str, bottom: str) -> Image.Image:
    w, h = size
    img = Image.new("RGB", (w, h))
    draw = ImageDraw.Draw(img)
    t_rgb, b_rgb = rgb(top), rgb(bottom)
    for y in range(h):
        t = y / max(1, h - 1)
        row = tuple(round(t_rgb[i] + (b_rgb[i] - t_rgb[i]) * t) for i in range(3))
        draw.line([(0, y), (w, y)], fill=row)
    return img


def _polygon_layer(size: tuple[int, int], points, fill=None, outline=None, width: int = 1) -> Image.Image:
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    draw.polygon(points, fill=fill, outline=outline, width=width)
    return layer


def _finish(img: Image.Image, w: int, h: int) -> Image.Image:
    return img.resize((w, h), Image.LANCZOS)


# ------------------------------------------------------------------
# Renderers (return PIL RGB images sized w x h)
# ------------------------------------------------------------------


def render_panel(
    w: int,
    h: int,
    behind: str = theme.BG_DEEP,
    fill: str = theme.PANEL_FILL,
    border: str = theme.PANEL_BORDER_DIM,
    cuts: tuple[int, int, int, int] | None = None,
    border_w: float = 1.2,
) -> Image.Image:
    """Chamfered panel: TL + BR cut corners like the Halo 2 game-variant cards."""
    if cuts is None:
        c = px(theme.CHAMFER)
        cuts = (c, 0, c, 0)

    W, H = w * SS, h * SS
    img = Image.new("RGB", (W, H), rgb(behind))
    pts = chamfer_points(W, H, *(c * SS for c in cuts))

    base = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bd = ImageDraw.Draw(base)
    # Subtle vertical sheen inside the fill.
    fill_img = _vgradient((W, H), "#%02x%02x%02x" % lighten(fill, 0.05), fill)
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).polygon(pts, fill=255)
    img.paste(fill_img, (0, 0), mask)

    outline = ImageDraw.Draw(img)
    outline.polygon(pts, outline=rgb(border), width=max(1, round(border_w * SS)))

    return _finish(img, w, h)


def render_bar(
    w: int,
    h: int,
    behind: str = theme.BG_DEEP,
    skew_left: int = 0,
    skew_right: int = 0,
    top: str = theme.BAR_HI,
    bottom: str = theme.BAR_LO,
    edge: str = theme.BAR_EDGE,
) -> Image.Image:
    """Slanted gradient bar (header / footer / legend)."""
    W, H = w * SS, h * SS
    img = Image.new("RGB", (W, H), rgb(behind))
    pts = skew_points(W, H, skew_left * SS, skew_right * SS)

    grad = _vgradient((W, H), top, bottom)
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).polygon(pts, fill=255)
    img.paste(grad, (0, 0), mask)

    draw = ImageDraw.Draw(img)
    # Bright top edge line, characteristic of the H2 header bars.
    draw.line([pts[0], pts[1]], fill=rgb(edge), width=SS)
    # Soft darker bottom edge.
    draw.line([pts[3], pts[2]], fill=darken(bottom, 0.35), width=SS)

    return _finish(img, w, h)


_BUTTON_STYLES = {
    # variant: (fill_top, fill_bottom, border, text_color)
    "primary": (theme.BTN_PRIMARY_HI, theme.BTN_PRIMARY_LO, theme.BTN_PRIMARY_BORDER, theme.BTN_PRIMARY_TEXT),
    "secondary": (theme.PANEL_FILL_HI, theme.PANEL_FILL, theme.PANEL_BORDER_DIM, theme.TEXT),
    "danger": (theme.MAROON_HI, theme.MAROON, theme.BTN_DANGER_BORDER, theme.TEXT_BRIGHT),
}


def render_button(
    w: int,
    h: int,
    variant: str = "secondary",
    state: str = "normal",
    behind: str = theme.BG_DEEP,
) -> Image.Image:
    """Chamfered button chrome. States: normal, hover, pressed, disabled."""
    top, bottom, border, _ = _BUTTON_STYLES.get(variant, _BUTTON_STYLES["secondary"])

    if state == "hover":
        top = "#%02x%02x%02x" % lighten(top, 0.16)
        bottom = "#%02x%02x%02x" % lighten(bottom, 0.12)
        border = theme.ACCENT
    elif state == "pressed":
        top = "#%02x%02x%02x" % darken(top, 0.18)
        bottom = "#%02x%02x%02x" % darken(bottom, 0.22)
        border = theme.ACCENT_DEEP
    elif state == "disabled":
        top = "#%02x%02x%02x" % mix(top, theme.BG_DEEP, 0.62)
        bottom = "#%02x%02x%02x" % mix(bottom, theme.BG_DEEP, 0.62)
        border = "#%02x%02x%02x" % mix(border, theme.BG_DEEP, 0.62)

    c = px(theme.CHAMFER_SMALL)
    W, H = w * SS, h * SS
    img = Image.new("RGB", (W, H), rgb(behind))
    pts = chamfer_points(W, H, c * SS, 0, c * SS, 0)

    if state == "hover":
        # Soft cyan glow around the outline.
        glow = _polygon_layer((W, H), pts, outline=rgb(theme.ACCENT) + (210,), width=3 * SS)
        glow = glow.filter(ImageFilter.GaussianBlur(3 * SS))
        img.paste(glow, (0, 0), glow)

    grad = _vgradient((W, H), top, bottom)
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).polygon(pts, fill=255)
    img.paste(grad, (0, 0), mask)

    draw = ImageDraw.Draw(img)
    draw.polygon(pts, outline=rgb(border), width=max(1, round(1.3 * SS)))
    # Bright inner top edge for the "lit" look.
    if state != "disabled":
        draw.line([pts[1] if len(pts) > 1 else (0, 0), pts[2] if len(pts) > 2 else (W, 0)], fill=lighten(top, 0.25), width=SS)

    return _finish(img, w, h)


def render_check(size: int, checked: bool, state: str = "normal", behind: str = theme.PANEL_FILL) -> Image.Image:
    W = size * SS
    img = Image.new("RGB", (W, W), rgb(behind))
    draw = ImageDraw.Draw(img)

    border = theme.PANEL_BORDER if state != "disabled" else theme.PANEL_BORDER_DIM
    if state == "hover":
        border = theme.ACCENT

    c = theme.CHECK_CHAMFER * SS
    pts = chamfer_points(W, W, c, 0, c, 0)
    draw.polygon(pts, fill=rgb(theme.ENTRY_FILL), outline=rgb(border), width=max(1, round(1.2 * SS)))

    if checked:
        inset = round(W * 0.24)
        inner = chamfer_points(W - 2 * inset, W - 2 * inset, c, 0, c, 0)
        inner = [(x + inset, y + inset) for x, y in inner]
        fill = theme.ACCENT if state != "disabled" else theme.TEXT_DIM
        draw.polygon(inner, fill=rgb(fill))

    return _finish(img, size, size)


def render_handle(w: int, h: int, state: str = "normal", behind: str = theme.BG_DEEP) -> Image.Image:
    """Slider / seekbar drag handle: a chamfered lozenge."""
    W, H = w * SS, h * SS
    img = Image.new("RGB", (W, H), rgb(behind))
    draw = ImageDraw.Draw(img)

    fill = theme.ACCENT if state in ("hover", "drag") else theme.ACCENT_DEEP
    if state == "disabled":
        fill = theme.TEXT_DIM

    c = round(min(W, H) * theme.HANDLE_CHAMFER)
    pts = chamfer_points(W, H, c, c, c, c)
    draw.polygon(pts, fill=rgb(fill), outline=rgb(theme.TEXT_BRIGHT), width=SS)

    return _finish(img, w, h)


def render_trim_handle(w: int, h: int, kind: str, state: str = "normal",
                       behind: str = theme.BG_DEEP) -> Image.Image:
    """Fat timeline trim handle: a full-lane-height grab bar with grip
    notches. kind: "start" (green, notches face right) / "end" (red, faces
    left). states: normal / hover / drag."""
    W, H = w * SS, h * SS
    img = Image.new("RGB", (W, H), rgb(behind))
    draw = ImageDraw.Draw(img)

    color = theme.TRIM_IN if kind == "start" else theme.TRIM_OUT
    if state in ("hover", "drag"):
        fill = lighten(color, 0.25 if state == "hover" else 0.45)
        outline = rgb(theme.TEXT_BRIGHT)
    else:
        fill = rgb(color)
        outline = lighten(color, 0.35)

    # Body: a slim vertical bar with a small chamfer on the outward corners
    # (zeroed on rectangular skins via HANDLE_CHAMFER = 0).
    c = round(W * theme.HANDLE_CHAMFER * 0.5)
    if kind == "start":
        pts = chamfer_points(W, H, c, 0, 0, c)
    else:
        pts = chamfer_points(W, H, 0, c, c, 0)
    draw.polygon(pts, fill=fill, outline=outline, width=SS)

    # Grip notches: three short horizontal slots around the vertical center.
    slot_w = round(W * 0.42)
    slot_h = max(SS, round(1.2 * SS))
    slot_x = round((W - slot_w) / 2)
    gap = round(H * 0.055)
    for i in (-1, 0, 1):
        cy = H // 2 + i * gap
        draw.rectangle([slot_x, cy - slot_h // 2, slot_x + slot_w, cy + slot_h // 2],
                       fill=darken(color, 0.45))

    return _finish(img, w, h)


def render_keyframe(h: int, state: str = "normal", behind: str = theme.BG_DEEP) -> Image.Image:
    """Keyframe marker for the seekbar: a small chamfered diamond.

    states: normal / hover / drag / active (playhead sitting on it) /
    inert (keyframes exist but crop is off — visible, ghosted)."""
    w = h
    W, H = w * SS, h * SS
    img = Image.new("RGB", (W, H), rgb(behind))
    draw = ImageDraw.Draw(img)

    if state == "active":
        fill = theme.ACCENT
        outline = theme.TEXT_BRIGHT
    elif state in ("hover", "drag"):
        fill = theme.ACCENT
        outline = theme.ACCENT_DEEP
    elif state == "inert":
        fill = theme.DISABLED_FILL
        outline = theme.TEXT_DIM
    else:
        fill = theme.ACCENT_DEEP
        outline = theme.ACCENT

    inset = round(1.4 * SS)
    cx, cy = W / 2, H / 2
    diamond = [
        (cx, inset),
        (W - inset, cy),
        (cx, H - inset),
        (inset, cy),
    ]
    draw.polygon(diamond, fill=rgb(fill), outline=rgb(outline), width=max(1, round(1.4 * SS)))

    return _finish(img, w, h)


def render_wordmark(text: str, size_px: int, behind: str = theme.BG_DEEP) -> Image.Image:
    """Big glowing display text (landing wordmark, panel headers)."""
    W_pad = size_px  # generous padding for the glow
    font = fonts.pil_font(size_px * SS, "Bold") or ImageFont.load_default()

    probe = Image.new("RGB", (8, 8))
    tw, th = ImageDraw.Draw(probe).textbbox((0, 0), text, font=font)[2:]

    W, H = tw + W_pad * SS, th + W_pad * SS
    img = Image.new("RGB", (W, H), rgb(behind))

    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    origin = (W_pad * SS // 2, W_pad * SS // 2)
    gd.text(origin, text, font=font, fill=rgb(theme.ACCENT) + (170,))
    glow = glow.filter(ImageFilter.GaussianBlur(4 * SS))
    img.paste(glow, (0, 0), glow)

    draw = ImageDraw.Draw(img)
    draw.text(origin, text, font=font, fill=rgb(theme.TEXT_BRIGHT))

    return _finish(img, W // SS, H // SS)


_GLYPHS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


def render_background(w: int, h: int) -> Image.Image:
    """Window background, dispatched on the skin's backdrop style.

    Both variants keep the body effectively flat BG_DEEP (only the far edges
    darken or texture) so that widgets composited against BG_DEEP blend in
    invisibly. Rendered at 1x — the textures are line-based — and
    deterministic so re-renders don't shimmer.
    """
    if theme.BACKDROP_STYLE == "reach":
        return _render_background_reach(w, h)
    return _render_background_halo2(w, h)


def _render_background_halo2(w: int, h: int) -> Image.Image:
    """H2 backdrop: vignette, faint scanline tick rows, dim glyph strips."""
    h = max(1, h)
    img = Image.new("RGB", (w, h), rgb(theme.BG_DEEP))
    draw = ImageDraw.Draw(img)

    rng = random.Random(2552)  # fixed seed: no shimmer across re-renders

    # Pre-mixed solid colors: PIL's alpha-ink text blending is unreliable, so
    # texture colors are computed against BG_DEEP directly.
    tick_color = mix(theme.BG_DEEP, theme.ACCENT, 0.06)
    glyph_color = mix(theme.BG_DEEP, theme.ACCENT, 0.05)

    # Horizontal tick rows (the faint dashed strips in the H2 background).
    row_gap = px(46)
    y = row_gap
    while y < h:
        x = -rng.randint(0, 24)
        while x < w:
            seg = rng.randint(6, 26)
            if rng.random() < 0.62:
                draw.line([(x, y), (x + seg, y)], fill=tick_color)
            x += seg + rng.randint(4, 14)
        y += row_gap

    # Two dim "data" glyph strips, like the faded text bands in the menus.
    if h > 200:
        try:
            gfont = fonts.pil_font(px(15), "SemiBold")
            if gfont is not None:
                for band_frac in (0.30, 0.64):
                    by = round(h * band_frac)
                    text = " ".join(
                        "".join(rng.choice(_GLYPHS) for _ in range(rng.randint(2, 6)))
                        for _ in range(max(8, w // 60))
                    )
                    draw.text((-rng.randint(0, 40), by), text, font=gfont, fill=glyph_color)
        except Exception:
            pass

    # Edge vignette, kept away from the center so content areas stay flat.
    vignette = Image.new("L", (w, h), 0)
    vd = ImageDraw.Draw(vignette)
    vd.rectangle([0, 0, w, h], fill=48)
    inset_w, inset_h = round(w * 0.07), round(h * 0.07)
    vd.rectangle([inset_w, inset_h, w - inset_w, h - inset_h], fill=0)
    vignette = vignette.filter(ImageFilter.GaussianBlur(max(24, w // 24)))
    dark = Image.new("RGB", (w, h), rgb(theme.BG_DEEPER))
    img = Image.composite(dark, img, vignette)

    return img


def _render_background_reach(w: int, h: int) -> Image.Image:
    """Reach backdrop: diamond-plate weave at the edges, deep vignette.

    The weave fades to nothing toward the center — the flat frames that sit
    over the canvas (menu, wordmark, detail panel) must never show seams —
    matching the Armory screens where the pattern lives in the corners.
    """
    h = max(1, h)
    img = Image.new("RGB", (w, h), rgb(theme.BG_DEEP))

    # 45-degree weave both ways, premixed against BG_DEEP.
    weave = Image.new("RGB", (w, h), rgb(theme.BG_DEEP))
    wd = ImageDraw.Draw(weave)
    line_color = mix(theme.BG_DEEP, theme.ACCENT, 0.10)
    step = max(8, px(24))
    for x in range(-h, w + h, step):
        wd.line([(x, 0), (x + h, h)], fill=line_color)
        wd.line([(x + h, 0), (x, h)], fill=line_color)

    # Edge-weighted mask: full weave at the borders, zero in the middle.
    edge_mask = Image.new("L", (w, h), 200)
    md = ImageDraw.Draw(edge_mask)
    inset_w, inset_h = round(w * 0.18), round(h * 0.18)
    md.rectangle([inset_w, inset_h, w - inset_w, h - inset_h], fill=0)
    edge_mask = edge_mask.filter(ImageFilter.GaussianBlur(max(40, w // 14)))
    img = Image.composite(weave, img, edge_mask)

    # Deep vignette — Reach menus sink to near-black at the frame.
    vignette = Image.new("L", (w, h), 0)
    vd = ImageDraw.Draw(vignette)
    vd.rectangle([0, 0, w, h], fill=96)
    inset_w, inset_h = round(w * 0.08), round(h * 0.08)
    vd.rectangle([inset_w, inset_h, w - inset_w, h - inset_h], fill=0)
    vignette = vignette.filter(ImageFilter.GaussianBlur(max(24, w // 20)))
    dark = Image.new("RGB", (w, h), rgb(theme.BG_DEEPER))
    img = Image.composite(dark, img, vignette)

    return img


def render_hud_chip(w: int, h: int, behind: str = "#000000") -> Image.Image:
    """Focus-mode HUD chip (B5): a scanline panel pre-blended toward black.

    Tk can't alpha-composite widgets over the embedded video window, but the
    chips sit on the preview's black letterbox — blending the skin's panel
    colors toward that black reads as translucency. Scanlines are drawn at
    1x after the downscale so they stay 1px-crisp, CRT-HUD style. Per-skin
    look flows from the existing tokens (Reach's zero CHAMFER_SMALL makes a
    straight-edged chip; the accent edge line picks up each skin's color).
    """
    c = px(theme.CHAMFER_SMALL)
    W, H = w * SS, h * SS
    img = Image.new("RGB", (W, H), rgb(behind))
    pts = chamfer_points(W, H, c * SS, 0, c * SS, 0)

    grad = _vgradient(
        (W, H),
        "#%02x%02x%02x" % mix(theme.PANEL_FILL_HI, behind, 0.45),
        "#%02x%02x%02x" % mix(theme.PANEL_FILL, behind, 0.60),
    )
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).polygon(pts, fill=255)
    img.paste(grad, (0, 0), mask)

    draw = ImageDraw.Draw(img)
    draw.polygon(pts, outline=mix(theme.PANEL_BORDER, behind, 0.25),
                 width=max(1, round(1.2 * SS)))
    # The lit HUD edge along the top face.
    draw.line([pts[1 if c else 0], pts[2 if c else 1]],
              fill=mix(theme.ACCENT, behind, 0.30), width=SS)

    img = _finish(img, w, h)

    # 1x scanlines, clipped to the chip body.
    scan = Image.new("L", (w, h), 0)
    sd = ImageDraw.Draw(scan)
    for y in range(2, h - 1, 3):
        sd.line([(0, y), (w, y)], fill=64)
    scan = ImageChops.multiply(scan, mask.resize((w, h), Image.LANCZOS))
    img = Image.composite(Image.new("RGB", (w, h), rgb(behind)), img, scan)

    return img


def render_menu_band(w: int, h: int, behind: str = theme.BG_DEEP) -> Image.Image:
    """Reach menu selection: pale silver band, solid left, fading out right."""
    W, H = w * SS, h * SS
    img = Image.new("RGB", (W, H), rgb(behind))

    # Vertical sheen through the band itself.
    silver = _vgradient(
        (W, H),
        "#%02x%02x%02x" % lighten(theme.SELECT_FILL, 0.22),
        "#%02x%02x%02x" % darken(theme.SELECT_FILL, 0.08),
    )

    # Horizontal alpha ramp: solid for the text stretch, then a soft falloff.
    band = Image.new("L", (W, H), 0)
    bd = ImageDraw.Draw(band)
    pad = round(H * 0.09)
    solid_until = 0.58
    for x in range(W):
        t = x / max(1, W - 1)
        if t <= solid_until:
            alpha = 235
        else:
            fall = (t - solid_until) / (1.0 - solid_until)
            alpha = round(235 * (1.0 - fall) ** 1.7)
        if alpha:
            bd.line([(x, pad), (x, H - pad)], fill=alpha)

    img.paste(silver, (0, 0), band)
    return _finish(img, w, h)


# ------------------------------------------------------------------
# PhotoImage cache
# ------------------------------------------------------------------

_RENDERERS = {
    "panel": render_panel,
    "bar": render_bar,
    "button": render_button,
    "check": render_check,
    "handle": render_handle,
    "trim_handle": render_trim_handle,
    "keyframe": render_keyframe,
    "wordmark": render_wordmark,
    "background": render_background,
    "menu_band": render_menu_band,
    "hud_chip": render_hud_chip,
}


class Skin:
    """LRU cache of rendered PhotoImages. Create after the Tk root exists."""

    def __init__(self, capacity: int = 256):
        self.capacity = capacity
        self._cache: OrderedDict[tuple, ImageTk.PhotoImage] = OrderedDict()

    def get(self, renderer: str, **params) -> ImageTk.PhotoImage:
        key = (renderer, tuple(sorted(params.items())))

        cached = self._cache.get(key)
        if cached is not None:
            self._cache.move_to_end(key)
            return cached

        image = _RENDERERS[renderer](**params)
        photo = ImageTk.PhotoImage(image)

        self._cache[key] = photo
        if len(self._cache) > self.capacity:
            self._cache.popitem(last=False)

        return photo


_skin: Skin | None = None


def get_skin() -> Skin:
    global _skin
    if _skin is None:
        _skin = Skin()
    return _skin
