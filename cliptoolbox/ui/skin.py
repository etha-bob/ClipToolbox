"""Pillow-rendered Halo 2 chrome.

Tk's canvas cannot antialias, so every diagonal shape (chamfered panels,
slanted bars, glows) is rendered by Pillow at 3x supersample, downscaled with
LANCZOS, and served as a cached PhotoImage. Axis-aligned fills (progress
bars, slider tracks) stay native canvas rectangles — those are already crisp
and cheap to move every frame.

Rendering is composited against a known `behind` color rather than relying on
Tk alpha blending, which is unreliable across Tk builds. Widgets therefore
declare the color they sit on.

The PhotoImage cache doubles as the mandatory Tk image reference holder.
"""
import random
from collections import OrderedDict

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageTk

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
    "primary": (theme.BAR_HI, theme.BAR_LO, theme.PANEL_BORDER, theme.TEXT_BRIGHT),
    "secondary": (theme.PANEL_FILL_HI, theme.PANEL_FILL, theme.PANEL_BORDER_DIM, theme.TEXT),
    "danger": (theme.MAROON_HI, theme.MAROON, "#B06A78", theme.TEXT_BRIGHT),
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

    c = 3 * SS
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

    c = round(min(W, H) * 0.35)
    pts = chamfer_points(W, H, c, c, c, c)
    draw.polygon(pts, fill=rgb(fill), outline=rgb(theme.TEXT_BRIGHT), width=SS)

    return _finish(img, w, h)


def render_trim_flag(h: int, kind: str, behind: str = theme.BG_DEEP) -> Image.Image:
    """Trim bracket for the seekbar: [ for start (green), ] for end (red)."""
    w = max(6, round(h * 0.42))
    W, H = w * SS, h * SS
    img = Image.new("RGB", (W, H), rgb(behind))
    draw = ImageDraw.Draw(img)

    color = rgb(theme.TRIM_IN if kind == "start" else theme.TRIM_OUT)
    t = max(SS, round(1.6 * SS))  # stroke thickness

    if kind == "start":
        draw.rectangle([0, 0, t, H], fill=color)
        draw.rectangle([0, 0, W - 1, t], fill=color)
        draw.rectangle([0, H - t, W - 1, H], fill=color)
    else:
        draw.rectangle([W - 1 - t, 0, W - 1, H], fill=color)
        draw.rectangle([0, 0, W - 1, t], fill=color)
        draw.rectangle([0, H - t, W - 1, H], fill=color)

    return _finish(img, w, h)


def render_wordmark(text: str, size_px: int, behind: str = theme.BG_DEEP) -> Image.Image:
    """Big glowing display text (landing wordmark, panel headers)."""
    path = fonts.pil_font_path("Bold")
    W_pad = size_px  # generous padding for the glow
    try:
        font = ImageFont.truetype(str(path), size_px * SS) if path else ImageFont.load_default()
    except Exception:
        font = ImageFont.load_default()

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
    """Window background: vignette, faint scanline tick rows, dim glyph strips.

    The body is intentionally flat BG_DEEP (only the far edges darken) so that
    widgets composited against BG_DEEP blend in invisibly. Rendered at 1x —
    the texture is axis-aligned — and deterministic so re-renders don't
    shimmer.
    """
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
    path = fonts.pil_font_path("SemiBold")
    if path is not None and h > 200:
        try:
            gfont = ImageFont.truetype(str(path), px(15))
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


# ------------------------------------------------------------------
# PhotoImage cache
# ------------------------------------------------------------------

_RENDERERS = {
    "panel": render_panel,
    "bar": render_bar,
    "button": render_button,
    "check": render_check,
    "handle": render_handle,
    "trim_flag": render_trim_flag,
    "wordmark": render_wordmark,
    "background": render_background,
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
