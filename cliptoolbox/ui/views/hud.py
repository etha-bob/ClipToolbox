"""Focus-mode HUD chips (roadmap B5).

Two small canvases placed over the preview letterbox while focus mode is
active: the clip name (top-left) and a transport readout (bottom-right —
playback-state glyph + current/total timecode). Backdrops come from
``skin.render_hud_chip`` (a scanline panel pre-blended toward the letterbox
black); the glyph is drawn with native canvas shapes so no font-glyph
roulette, and the timecode rides the app's existing ``time_left_var`` /
``time_right_var`` traces as a cheap native text update — no PIL work on the
10 Hz position path.

Like the other view modules this only builds widgets; mode state lives on
the app (``enter_focus_mode`` / ``exit_focus_mode`` call ``show``/``hide``).
"""
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path

from cliptoolbox.core import playback as core_playback
from cliptoolbox.core.win32 import raise_window_to_top
from cliptoolbox.ui import skin, theme
from cliptoolbox.ui.theme import px

CHIP_H = 30      # logical
CHIP_PAD = 14    # logical text inset
EDGE = 12        # logical gap to the preview edge


def _ellipsize_middle(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    half = (limit - 3) // 2
    return text[:half] + " … " + text[-half:]


class FocusHud:
    def __init__(self, app):
        self.app = app
        self.active = False
        self._h = px(CHIP_H)
        self._transport_w = 0
        self._last_state = None
        self._raise_after_ids: list[str] = []

        self.name_chip = tk.Canvas(app.preview_frame, highlightthickness=0,
                                   bd=0, bg="black", height=self._h)
        self.transport_chip = tk.Canvas(app.preview_frame, highlightthickness=0,
                                        bd=0, bg="black", height=self._h)

        self._title_font = tkfont.Font(root=app.root, font=theme.font_title(12))
        self._mono_font = tkfont.Font(root=app.root, font=theme.font_mono(12))

        # Trace-driven updates: the vars tick anyway (position loop, clip
        # swaps) — the callbacks are no-ops while the HUD is hidden.
        app.time_left_var.trace_add("write", lambda *a: self.refresh())
        app.time_right_var.trace_add("write", lambda *a: self.refresh())
        app.file_label_var.trace_add("write", lambda *a: self._render_name())

    # ------------------------------------------------------------------

    def show(self):
        self.active = True
        self._render_name()
        self.refresh()
        self.name_chip.place(x=px(EDGE), y=px(EDGE))
        self.transport_chip.place(relx=1.0, rely=1.0, x=-px(EDGE), y=-px(EDGE),
                                  anchor="se")
        self._assert_above_player()

    def hide(self):
        if not self.active:
            return
        self.active = False
        for after_id in self._raise_after_ids:
            try:
                self.app.root.after_cancel(after_id)
            except Exception:
                pass
        self._raise_after_ids = []
        self.name_chip.place_forget()
        self.transport_chip.place_forget()

    # ------------------------------------------------------------------

    def _assert_above_player(self):
        """Out-stack the embedded player window. anchor_child_window raises
        the player to HWND_TOP on each first-frame reveal, which lands
        asynchronously after the PLAYING transition — so re-assert now and
        again shortly after every state change (posted, cheap no-ops when
        the order is already right)."""
        for after_id in self._raise_after_ids:
            try:
                self.app.root.after_cancel(after_id)
            except Exception:
                pass

        def raise_chips():
            if not self.active:
                return
            raise_window_to_top(self.name_chip.winfo_id())
            raise_window_to_top(self.transport_chip.winfo_id())

        raise_chips()
        self._raise_after_ids = [
            self.app.root.after(delay, raise_chips) for delay in (120, 450)
        ]

    # ------------------------------------------------------------------

    def _render_name(self):
        if not self.active:
            return
        name = Path(self.app.video_path).name if self.app.video_path else ""
        name = _ellipsize_middle(name, 44)
        w = self._title_font.measure(name) + 2 * px(CHIP_PAD)
        c = self.name_chip
        c.config(width=w)
        c.delete("all")
        c.create_image(0, 0, anchor="nw",
                       image=skin.get_skin().get("hud_chip", w=w, h=self._h))
        c.create_text(px(CHIP_PAD), self._h // 2, text=name, anchor="w",
                      font=theme.font_title(12), fill=theme.TEXT_BRIGHT)

    def refresh(self):
        """Sync the transport chip (glyph + timecode) with playback state."""
        if not self.active:
            return
        app = self.app
        text = f"{app.time_left_var.get()} / {app.time_right_var.get()}"

        glyph_zone = px(24)
        w = glyph_zone + self._mono_font.measure(text) + 2 * px(CHIP_PAD)
        w = -(-w // px(8)) * px(8)  # bucket widths so the backdrop cache hits

        c = self.transport_chip
        if w != self._transport_w:
            self._transport_w = w
            c.config(width=w)
            c.delete("backdrop")
            c.create_image(0, 0, anchor="nw", tags="backdrop",
                           image=skin.get_skin().get("hud_chip", w=w, h=self._h))
            c.tag_lower("backdrop")

        c.delete("text")
        c.create_text(px(CHIP_PAD) + glyph_zone, self._h // 2, text=text,
                      anchor="w", font=theme.font_mono(12), fill=theme.TEXT,
                      tags="text")
        self._draw_glyph()

        state = self.app.playback.state
        if state != self._last_state:
            self._last_state = state
            self._assert_above_player()

    def _draw_glyph(self):
        """Native-shape playback glyph: ▶ / pause bars / starting dots /
        stopped square. Canvas shapes, so it renders identically on every
        skin font."""
        c = self.transport_chip
        c.delete("glyph")
        x = px(CHIP_PAD)
        cy = self._h // 2
        s = px(6)
        state = self.app.playback.state

        if state == core_playback.PLAYING:
            c.create_polygon(x, cy - s, x + round(s * 1.6), cy, x, cy + s,
                             fill=theme.ACCENT, outline="", tags="glyph")
        elif state == core_playback.PAUSED:
            bw = px(3)
            for dx in (0, bw + px(3)):
                c.create_rectangle(x + dx, cy - s, x + dx + bw, cy + s,
                                   fill=theme.TEXT_BRIGHT, outline="",
                                   tags="glyph")
        elif state == core_playback.STARTING:
            r = px(2)
            for i in range(3):
                dx = i * px(6)
                c.create_oval(x + dx, cy - r, x + dx + 2 * r, cy + r,
                              fill=theme.ACCENT, outline="", tags="glyph")
        else:
            c.create_rectangle(x, cy - s + px(1), x + 2 * s - px(2),
                               cy + s - px(1), fill=theme.TEXT_DIM,
                               outline="", tags="glyph")
