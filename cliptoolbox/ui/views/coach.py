"""First-run coach marks overlay (roadmap B6 — the cold-start half of F7).

A one-time dim overlay pointing at the load-bearing editor controls with
their key hints: timeline gestures, transport/toolbar keys, the export
drawer, the roster's zero-affordance gestures, and the palette/focus keys.
Re-invocable from the command palette (``help.coach``).

Construction: the SettingsOverlay two-layer pattern, extended — an alpha
scrim Toplevel dims the whole window, and a second Toplevel above it uses
Windows' ``-transparentcolor`` so only the callout cards and connector
lines paint (the magic key is near-black, so the chamfer's anti-aliased
fringe pixels read as dark card edges instead of halos). Everything
repositions on ``<Configure>``; Esc, any click, or GOT IT dismisses.

``draw_callout`` is a standalone renderer so the gallery can demo the card
per skin without building the overlay.
"""
import tkinter as tk
import tkinter.font as tkfont

from cliptoolbox.ui import skin, theme
from cliptoolbox.ui.theme import px
from cliptoolbox.ui.widgets import HaloButton

MAGIC = "#010101"  # transparentcolor key — near-black so AA fringes stay dark

_PAD = 14        # logical card padding
_LINE_H = 22     # logical hint-line height
_KEY_H = 16      # logical keycap height


def _fonts(widget):
    return (
        tkfont.Font(root=widget, font=theme.font_title(13)),
        tkfont.Font(root=widget, font=theme.font_small(11)),
        tkfont.Font(root=widget, font=theme.font_small(12)),
    )


def _line_width(line, key_font, text_font):
    w = 0
    for kind, text in line:
        if kind == "k":
            w += key_font.measure(text) + px(10) + px(6)
        else:
            w += text_font.measure(text) + px(10)
    return w


def measure_callout(canvas, title, lines) -> tuple[int, int]:
    title_font, key_font, text_font = _fonts(canvas)
    w = max([title_font.measure(title)] +
            [_line_width(line, key_font, text_font) for line in lines])
    w += 2 * px(_PAD)
    h = 2 * px(_PAD) + px(20) + len(lines) * px(_LINE_H)
    return w, h


def draw_callout(canvas, x, y, title, lines, behind=MAGIC, tags="coach"):
    """Draw one chamfered callout card at (x, y); returns (w, h).

    ``lines`` is a list of hint lines; each line is a list of
    ``("k", "CTRL+E")`` keycap or ``("t", "EXPORT")`` plain-text segments.
    """
    title_font, key_font, text_font = _fonts(canvas)
    w, h = measure_callout(canvas, title, lines)

    canvas.create_image(x, y, anchor="nw", tags=tags, image=skin.get_skin().get(
        "panel", w=w, h=h, behind=behind, fill=theme.PANEL_FILL,
        border=theme.PANEL_BORDER))

    canvas.create_text(x + px(_PAD), y + px(_PAD) + px(8), text=title,
                       anchor="w", font=theme.font_title(13),
                       fill=theme.ACCENT, tags=tags)

    ly = y + px(_PAD) + px(20) + px(_LINE_H) // 2
    for line in lines:
        lx = x + px(_PAD)
        for kind, text in line:
            if kind == "k":
                kw = key_font.measure(text) + px(10)
                canvas.create_rectangle(lx, ly - px(_KEY_H) // 2,
                                        lx + kw, ly + px(_KEY_H) // 2,
                                        fill=theme.BG_DEEP,
                                        outline=theme.BAR_EDGE, tags=tags)
                canvas.create_text(lx + kw // 2, ly, text=text,
                                   font=theme.font_small(11),
                                   fill=theme.ACCENT, tags=tags)
                lx += kw + px(6)
            else:
                canvas.create_text(lx, ly, text=text, anchor="w",
                                   font=theme.font_small(12),
                                   fill=theme.TEXT_BRIGHT, tags=tags)
                lx += text_font.measure(text) + px(10)
        ly += px(_LINE_H)

    return w, h


def _callout_specs(app):
    """(target getter, side, anchor fraction along the target, title, lines).
    Targets are today's surfaces — the audit's list predates B2/B4/B5."""
    return [
        (lambda: app.seekbar, "above", 0.26, "TIMELINE", [
            [("k", "DRAG"), ("t", "SCRUB"), ("k", "WHEEL"), ("t", "SEEK")],
            [("k", "CTRL+WHEEL"), ("t", "ZOOM"), ("k", "[ ]"), ("t", "TRIM")],
        ]),
        (lambda: app.transport_frame, "below", 0.32, "PLAYBACK & TOOLS", [
            [("k", "SPACE"), ("t", "PLAY"), ("k", ", ."), ("t", "FRAME STEP")],
            [("t", "TRIM & CROP open their toolbars")],
            [("k", "C"), ("t", "CROP"), ("k", "K"), ("t", "KEYFRAME")],
        ]),
        (lambda: app.export_button, "right", 0.5, "EXPORT", [
            [("k", "CTRL+E"), ("t", "EXPORT DRAWER")],
            [("t", "naming · compression · job history")],
        ]),
        (lambda: app.track_canvas, "below", 0.5, "AUDIO MIX", [
            [("k", "R-CLICK"), ("t", "SOLO"), ("k", "2×CLICK"), ("t", "RESET")],
            [("k", "WHEEL"), ("t", "VOLUME OVER A ROW")],
        ]),
        (lambda: app.legend, "above", 0.80, "EVERYTHING ELSE", [
            [("k", "CTRL+K"), ("t", "ALL COMMANDS")],
            [("k", "TAB"), ("t", "FOCUS MODE")],
        ]),
    ]


class CoachMarks:
    def __init__(self, app, on_dismiss=None):
        self.app = app
        self._on_dismiss = on_dismiss
        self.dismissed = False
        root = app.root

        self.scrim = tk.Toplevel(root)
        self.scrim.overrideredirect(True)
        self.scrim.configure(bg="#000000")
        try:
            self.scrim.attributes("-alpha", 0.45)
        except Exception:
            pass

        self.overlay = tk.Toplevel(root)
        self.overlay.overrideredirect(True)
        self.overlay.configure(bg=MAGIC)
        try:
            self.overlay.attributes("-transparentcolor", MAGIC)
        except Exception:
            pass  # degraded: opaque near-black backdrop; still fully usable

        self.canvas = tk.Canvas(self.overlay, bg=MAGIC, highlightthickness=0, bd=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.got_it = HaloButton(self.canvas, text="GOT IT", variant="primary",
                                 behind=theme.PANEL_FILL, width=px(150),
                                 command=self.dismiss)
        self._got_it_window = None

        for widget in (self.overlay, self.canvas, self.scrim):
            widget.bind("<Button-1>", lambda e: self.dismiss())
            widget.bind("<Escape>", lambda e: self.dismiss())
            widget.bind("<Return>", lambda e: self.dismiss())

        self._configure_bind = root.bind("<Configure>", self._reposition, add="+")
        self._reposition()

        self.scrim.lift(root)
        self.overlay.lift(self.scrim)
        try:
            self.overlay.grab_set()
        except Exception:
            pass
        self.overlay.focus_force()

    # ------------------------------------------------------------------

    def _rect(self, widget):
        root = self.app.root
        return (widget.winfo_rootx() - root.winfo_rootx(),
                widget.winfo_rooty() - root.winfo_rooty(),
                widget.winfo_width(), widget.winfo_height())

    def _reposition(self, _event=None):
        try:
            root = self.app.root
            rx, ry = root.winfo_rootx(), root.winfo_rooty()
            rw, rh = root.winfo_width(), root.winfo_height()
            self.scrim.geometry(f"{rw}x{rh}+{rx}+{ry}")
            self.overlay.geometry(f"{rw}x{rh}+{rx}+{ry}")
            self._redraw(rw, rh)
        except Exception:
            pass

    def _redraw(self, rw, rh):
        c = self.canvas
        c.delete("coach")
        gap = px(16)

        for target_of, side, frac, title, lines in _callout_specs(self.app):
            try:
                target = target_of()
                if not target.winfo_ismapped():
                    continue
                tx, ty, tw, th = self._rect(target)
            except Exception:
                continue

            w, h = measure_callout(c, title, lines)
            ax = tx + round(tw * frac)  # connector anchor on the target

            if side == "above":
                x, y = ax - w // 2, ty - gap - h
            elif side == "below":
                x, y = ax - w // 2, ty + th + gap
            else:  # right
                x, y = tx + tw + gap, ty + th // 2 - h // 2

            # Clamp onto the window, then run the connector from the card
            # edge nearest the anchor (diagonal when clamping shifted it).
            x = max(px(8), min(x, rw - w - px(8)))
            y = max(px(8), min(y, rh - h - px(8)))

            draw_callout(c, x, y, title, lines)
            if side == "above":
                start = (max(x + px(6), min(ax, x + w - px(6))), y + h)
                line_to = (ax, ty - px(2))
            elif side == "below":
                start = (max(x + px(6), min(ax, x + w - px(6))), y)
                line_to = (ax, ty + th + px(2))
            else:
                start = (x, y + h // 2)
                line_to = (tx + tw + px(2), ty + th // 2)
            c.create_line(start[0], start[1], line_to[0], line_to[1],
                          fill=theme.ACCENT, width=px(2), tags="coach")
            r = px(4)
            c.create_polygon(line_to[0], line_to[1] - r, line_to[0] + r, line_to[1],
                             line_to[0], line_to[1] + r, line_to[0] - r, line_to[1],
                             fill=theme.ACCENT, outline="", tags="coach")

        # GOT IT card: centered over the preview area.
        cap = "Shows once — reopen anytime from the CTRL+K palette"
        cap_font = tkfont.Font(root=c, font=theme.font_small(12))
        card_w = max(px(180), cap_font.measure(cap) + 2 * px(_PAD))
        card_h = px(96)
        x = (rw - card_w) // 2
        y = round(rh * 0.40) - card_h // 2
        c.create_image(x, y, anchor="nw", tags="coach", image=skin.get_skin().get(
            "panel", w=card_w, h=card_h, behind=MAGIC, fill=theme.PANEL_FILL,
            border=theme.ACCENT_DEEP))
        c.create_text(x + card_w // 2, y + px(20), text=cap,
                      font=theme.font_small(12), fill=theme.TEXT, tags="coach")
        if self._got_it_window is not None:
            c.delete(self._got_it_window)
        self._got_it_window = c.create_window(
            x + card_w // 2, y + card_h - px(30), window=self.got_it)

    # ------------------------------------------------------------------

    def dismiss(self):
        if self.dismissed:
            return
        self.dismissed = True
        try:
            self.overlay.grab_release()
        except Exception:
            pass
        try:
            self.app.root.unbind("<Configure>", self._configure_bind)
        except Exception:
            pass
        for window in (self.overlay, self.scrim):
            try:
                window.destroy()
            except Exception:
                pass
        if self._on_dismiss is not None:
            self._on_dismiss()
