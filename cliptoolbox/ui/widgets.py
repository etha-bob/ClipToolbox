"""Interactive Halo 2 styled widgets.

Design constraints:
- Everything visual comes from the skin (PIL-rendered, cached); axis-aligned
  dynamic fills are native canvas rects so hover/drag never re-renders PIL.
- Widgets that replace ttk controls keep the .config(text=, state=) subset the
  existing state-machine code uses, so ported logic drives them unchanged.
- Each widget declares the color it sits on (`behind`) for seamless
  compositing.
"""
import tkinter as tk

from cliptoolbox.ui import skin, theme
from cliptoolbox.ui.theme import px

NORMAL = tk.NORMAL
DISABLED = tk.DISABLED


class _NullWidget:
    """Stand-in for legacy hidden widgets (play_pause_button et al.) so ported
    state-machine code can call .config() safely."""

    def config(self, **kwargs):
        pass

    configure = config

    def pack(self, **kwargs):
        pass

    def grid(self, **kwargs):
        pass

    def place(self, **kwargs):
        pass


def draw_corner_brackets(canvas: tk.Canvas, x0: int, y0: int, x1: int, y1: int,
                         color: str = theme.TEXT_BRIGHT, tag: str = "brackets"):
    """White corner-bracket focus frame, like the H2 selection reticle."""
    L = px(9)
    t = max(1, px(2) // 1)
    for cx, cy, dx, dy in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x1, y1, -1, -1), (x0, y1, 1, -1)):
        canvas.create_line(cx, cy, cx + dx * L, cy, fill=color, width=t, tags=tag)
        canvas.create_line(cx, cy, cx, cy + dy * L, fill=color, width=t, tags=tag)


class HaloButton(tk.Canvas):
    def __init__(self, parent, text="", command=None, variant="secondary",
                 width=None, height=None, behind=theme.BG_DEEP, font=None):
        self.variant = variant
        self.behind = behind
        self._text = text
        self._command = command
        self._state = NORMAL
        self._visual = "normal"
        self._font = font or (theme.font_title() if variant == "primary" else theme.font_title(13))

        h = height or px(theme.BTN_PRIMARY_H if variant == "primary" else theme.BTN_H)
        w = width or (px(40) + self._measure_text(parent, text))

        super().__init__(parent, width=w, height=h, highlightthickness=0, bd=0, bg=behind)
        self._wpx, self._hpx = w, h

        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)

        self._redraw()

    def _measure_text(self, parent, text):
        probe = tk.font.Font(root=parent, font=self._font) if hasattr(tk, "font") else None
        try:
            from tkinter import font as tkfont
            f = tkfont.Font(root=parent, font=self._font)
            return f.measure(text or " ")
        except Exception:
            return px(10) * max(1, len(text))

    def _redraw(self):
        self.delete("all")
        sk = skin.get_skin()
        self.create_image(0, 0, anchor="nw", image=sk.get(
            "button", w=self._wpx, h=self._hpx, variant=self.variant,
            state=self._visual, behind=self.behind,
        ))

        if self._state == DISABLED:
            text_color = theme.TEXT_DIM
        elif self.variant == "secondary" and self._visual not in ("hover", "pressed"):
            text_color = theme.TEXT
        else:
            text_color = theme.TEXT_BRIGHT

        self.create_text(self._wpx // 2, self._hpx // 2 + (px(1) if self._visual == "pressed" else 0),
                         text=self._text, font=self._font, fill=text_color)

        if self._visual == "hover":
            draw_corner_brackets(self, px(2), px(2), self._wpx - px(3), self._hpx - px(3))

    # --- ttk.Button-compatible surface -------------------------------
    def config(self, **kwargs):
        if "text" in kwargs:
            self._text = kwargs.pop("text")
        if "command" in kwargs:
            self._command = kwargs.pop("command")
        if "state" in kwargs:
            state = kwargs.pop("state")
            self._state = DISABLED if str(state) == DISABLED else NORMAL
            if self._state == DISABLED:
                self._visual = "disabled"
            elif self._visual == "disabled":
                self._visual = "normal"
        if kwargs:
            super().configure(**kwargs)
        self._redraw()

    configure = config

    def set_width(self, w):
        self._wpx = w
        super().configure(width=w)
        self._redraw()

    # --- interaction --------------------------------------------------
    def _on_enter(self, _):
        if self._state == NORMAL:
            self._visual = "hover"
            self._redraw()

    def _on_leave(self, _):
        if self._state == NORMAL:
            self._visual = "normal"
            self._redraw()

    def _on_press(self, _):
        if self._state == NORMAL:
            self._visual = "pressed"
            self._redraw()

    def _on_release(self, event):
        if self._state != NORMAL:
            return
        inside = 0 <= event.x <= self._wpx and 0 <= event.y <= self._hpx
        self._visual = "hover" if inside else "normal"
        self._redraw()
        if inside and self._command is not None:
            self._command()


class HaloCheckbox(tk.Canvas):
    """Checkbox with H2 styling. Supports text, variable (BooleanVar), command,
    and .config(state=...)."""

    def __init__(self, parent, text="", variable=None, command=None,
                 behind=theme.BG_DEEP, font=None, text_color=None):
        self.behind = behind
        self._text = text
        self._variable = variable or tk.BooleanVar(value=False)
        self._command = command
        self._state = NORMAL
        self._hover = False
        self._font = font or theme.font_body()
        self._text_color = text_color

        self._size = px(theme.CHECK_SIZE)
        from tkinter import font as tkfont
        f = tkfont.Font(root=parent, font=self._font)
        w = self._size + px(8) + f.measure(text or "") + px(4)
        h = max(self._size + px(6), f.metrics("linespace") + px(6))

        super().__init__(parent, width=w, height=h, highlightthickness=0, bd=0, bg=behind)
        self._wpx, self._hpx = w, h

        self._trace = self._variable.trace_add("write", lambda *a: self._redraw())

        self.bind("<Enter>", self._set_hover(True))
        self.bind("<Leave>", self._set_hover(False))
        self.bind("<ButtonRelease-1>", self._on_click)

        self._redraw()

    def _set_hover(self, value):
        def handler(_):
            self._hover = value
            self._redraw()
        return handler

    def _redraw(self):
        self.delete("all")
        sk = skin.get_skin()
        state = "disabled" if self._state == DISABLED else ("hover" if self._hover else "normal")
        checked = bool(self._variable.get())
        cy = self._hpx // 2
        self.create_image(0, cy - self._size // 2, anchor="nw", image=sk.get(
            "check", size=self._size, checked=checked, state=state, behind=self.behind,
        ))
        if self._state == DISABLED:
            color = theme.TEXT_DIM
        elif self._text_color:
            color = self._text_color
        else:
            color = theme.TEXT_BRIGHT if (self._hover or checked) else theme.TEXT
        self.create_text(self._size + px(8), cy, text=self._text, font=self._font,
                         fill=color, anchor="w")

    def _on_click(self, event):
        if self._state != NORMAL:
            return
        if not (0 <= event.x <= self._wpx and 0 <= event.y <= self._hpx):
            return
        self._variable.set(not self._variable.get())
        if self._command is not None:
            self._command()

    def config(self, **kwargs):
        if "state" in kwargs:
            state = kwargs.pop("state")
            self._state = DISABLED if str(state) == DISABLED else NORMAL
        if "text" in kwargs:
            self._text = kwargs.pop("text")
        if kwargs:
            super().configure(**kwargs)
        self._redraw()

    configure = config


class HaloSlider(tk.Canvas):
    """tk.Scale-compatible subset: get/set, config(state=), command(str)."""

    HANDLE_W = 12
    HANDLE_H = 20

    def __init__(self, parent, from_=0.0, to=1.0, resolution=0.01, command=None,
                 length=200, behind=theme.PANEL_FILL):
        self.behind = behind
        self._from = float(from_)
        self._to = float(to)
        self._resolution = resolution
        self._command = command
        self._value = self._from
        self._state = NORMAL
        self._dragging = False
        self._hover = False

        h = px(theme.SLIDER_H)
        super().__init__(parent, width=length, height=h, highlightthickness=0, bd=0, bg=behind)
        self._wpx, self._hpx = length, h
        self._pad = px(self.HANDLE_W // 2 + 2)

        self.bind("<Configure>", self._on_resize)
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)

        self._redraw()

    def _on_resize(self, event):
        self._wpx = event.width
        self._redraw()

    def _set_hover(self, value):
        self._hover = value
        self._redraw()

    def _track_x(self, value: float) -> int:
        span = max(1e-9, self._to - self._from)
        frac = (value - self._from) / span
        usable = self._wpx - 2 * self._pad
        return self._pad + round(frac * usable)

    def _value_at(self, x: int) -> float:
        usable = max(1, self._wpx - 2 * self._pad)
        frac = min(1.0, max(0.0, (x - self._pad) / usable))
        value = self._from + frac * (self._to - self._from)
        if self._resolution:
            steps = round((value - self._from) / self._resolution)
            value = self._from + steps * self._resolution
        return min(self._to, max(self._from, value))

    def _redraw(self):
        self.delete("all")
        sk = skin.get_skin()
        cy = self._hpx // 2
        th = px(4)

        x0, x1 = self._pad, self._wpx - self._pad
        hx = self._track_x(self._value)

        self.create_rectangle(x0, cy - th // 2, x1, cy + th // 2,
                              fill=theme.SEEK_TRACK, outline=theme.PANEL_BORDER_DIM)
        fill = theme.ACCENT_DEEP if self._state == NORMAL else theme.TEXT_DIM
        self.create_rectangle(x0, cy - th // 2 + 1, hx, cy + th // 2 - 1, fill=fill, width=0)

        hstate = "disabled" if self._state == DISABLED else (
            "drag" if self._dragging else ("hover" if self._hover else "normal"))
        hw, hh = px(self.HANDLE_W), px(self.HANDLE_H)
        self.create_image(hx, cy, image=sk.get(
            "handle", w=hw, h=hh, state=hstate, behind=self.behind))

    # --- tk.Scale-compatible surface ---------------------------------
    def get(self) -> float:
        return self._value

    def set(self, value):
        self._value = min(self._to, max(self._from, float(value)))
        self._redraw()

    def config(self, **kwargs):
        if "state" in kwargs:
            state = kwargs.pop("state")
            self._state = DISABLED if str(state) == DISABLED else NORMAL
        if "command" in kwargs:
            self._command = kwargs.pop("command")
        if "to" in kwargs:
            self._to = float(kwargs.pop("to"))
            self._value = min(self._to, self._value)
        if "from_" in kwargs:
            self._from = float(kwargs.pop("from_"))
        if kwargs:
            super().configure(**kwargs)
        self._redraw()

    configure = config

    # --- interaction --------------------------------------------------
    def _apply_drag(self, x):
        value = self._value_at(x)
        if value != self._value:
            self._value = value
            self._redraw()
            if self._command is not None:
                self._command(f"{value}")

    def _on_press(self, event):
        if self._state != NORMAL:
            return
        self._dragging = True
        self._apply_drag(event.x)

    def _on_drag(self, event):
        if self._dragging and self._state == NORMAL:
            self._apply_drag(event.x)

    def _on_release(self, _):
        self._dragging = False
        self._redraw()


class HaloEntry(tk.Frame):
    """Dark recessed entry. Wraps a real tk.Entry for full text editing."""

    def __init__(self, parent, textvariable=None, width=8, behind=theme.PANEL_FILL,
                 font=None, justify="center"):
        super().__init__(parent, bg=theme.PANEL_BORDER_DIM, padx=1, pady=1)
        self.entry = tk.Entry(
            self,
            textvariable=textvariable,
            width=width,
            font=font or theme.font_body(),
            justify=justify,
            bg=theme.ENTRY_FILL,
            fg=theme.TEXT_BRIGHT,
            insertbackground=theme.ACCENT,
            disabledbackground="#0B1B2C",
            disabledforeground=theme.TEXT_DIM,
            relief=tk.FLAT,
            highlightthickness=0,
            bd=px(4),
        )
        self.entry.pack(fill=tk.BOTH, expand=True)
        self.entry.bind("<FocusIn>", lambda e: super(HaloEntry, self).configure(bg=theme.ACCENT))
        self.entry.bind("<FocusOut>", lambda e: super(HaloEntry, self).configure(bg=theme.PANEL_BORDER_DIM))

    def config(self, **kwargs):
        if "state" in kwargs:
            state = kwargs.pop("state")
            self.entry.configure(state=tk.NORMAL if str(state) not in (DISABLED,) else tk.DISABLED)
        if kwargs:
            self.entry.configure(**kwargs)

    configure = config


class HaloSegmented(tk.Frame):
    """Segmented selector (replaces the readonly resolution Combobox)."""

    def __init__(self, parent, values, textvariable, command=None, behind=theme.PANEL_FILL):
        super().__init__(parent, bg=behind)
        self.behind = behind
        self._values = list(values)
        self._variable = textvariable
        self._command = command
        self._state = NORMAL
        self._buttons: list[tk.Label] = []

        for value in self._values:
            label = tk.Label(
                self, text=value, font=theme.font_small(),
                fg=theme.TEXT, bg=theme.ENTRY_FILL,
                padx=px(10), pady=px(4),
            )
            label.pack(side=tk.LEFT, padx=(0, px(2)))
            label.bind("<ButtonRelease-1>", lambda e, v=value: self._choose(v))
            label.bind("<Enter>", lambda e, l=label: self._hover(l, True))
            label.bind("<Leave>", lambda e, l=label: self._hover(l, False))
            self._buttons.append(label)

        self._variable.trace_add("write", lambda *a: self._sync())
        self._sync()

    def _hover(self, label, on):
        if self._state == DISABLED:
            return
        if label.cget("text") != self._variable.get():
            label.configure(bg=theme.PANEL_FILL_HI if on else theme.ENTRY_FILL,
                            fg=theme.TEXT_BRIGHT if on else theme.TEXT)

    def _choose(self, value):
        if self._state == DISABLED:
            return
        self._variable.set(value)
        if self._command is not None:
            self._command()

    def _sync(self):
        selected = self._variable.get()
        for label in self._buttons:
            active = label.cget("text") == selected
            if self._state == DISABLED:
                label.configure(bg="#0B1B2C", fg=theme.TEXT_DIM)
            elif active:
                label.configure(bg=theme.SELECT_FILL, fg=theme.TEXT_BRIGHT)
            else:
                label.configure(bg=theme.ENTRY_FILL, fg=theme.TEXT)

    def config(self, **kwargs):
        if "state" in kwargs:
            state = str(kwargs.pop("state"))
            # "readonly" (the old Combobox live state) counts as enabled.
            self._state = DISABLED if state == DISABLED else NORMAL
            self._sync()
        if kwargs:
            super().configure(**kwargs)

    configure = config


class HaloPanel(tk.Frame):
    """Chamfered panel with an optional uppercase title strip.

    Children pack/grid into `.body` (a flat PANEL_FILL frame). The chamfered
    chrome is a canvas image behind it, re-rendered (debounced) on resize.
    """

    def __init__(self, parent, title=None, behind=theme.BG_DEEP, fill=theme.PANEL_FILL,
                 border=theme.PANEL_BORDER_DIM, pad=None):
        super().__init__(parent, bg=behind)
        self.behind = behind
        self.fill = fill
        self.border = border
        self._title = title
        self._resize_job = None

        self.canvas = tk.Canvas(self, highlightthickness=0, bd=0, bg=behind)
        self.canvas.place(x=0, y=0, relwidth=1, relheight=1)

        pad = pad if pad is not None else px(theme.PAD)
        title_h = px(26) if title else 0
        self.body = tk.Frame(self, bg=fill)
        self.body.pack(fill=tk.BOTH, expand=True,
                       padx=pad, pady=(pad + title_h, pad))

        self.bind("<Configure>", self._on_resize)

    def _on_resize(self, event):
        if self._resize_job is not None:
            try:
                self.after_cancel(self._resize_job)
            except Exception:
                pass
        self._resize_job = self.after(60, lambda: self._render(event.width, event.height))

    def _render(self, w, h):
        self._resize_job = None
        if w <= 2 or h <= 2:
            return
        sk = skin.get_skin()
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=sk.get(
            "panel", w=w, h=h, behind=self.behind, fill=self.fill, border=self.border))
        if self._title:
            self.canvas.create_text(
                px(theme.PAD) + px(4), px(theme.PAD) + px(2),
                text=self._title.upper(), font=theme.font_title(13),
                fill=theme.ACCENT, anchor="nw",
            )
            y = px(theme.PAD) + px(22)
            self.canvas.create_line(px(theme.PAD), y, w - px(theme.PAD), y,
                                    fill=theme.PANEL_BORDER_DIM)


class LegendBar(tk.Canvas):
    """Footer legend bar — the A SELECT / B BACK homage, with key hints."""

    def __init__(self, parent, height=None, behind=theme.BG_DEEP):
        h = height or px(theme.FOOTER_H)
        super().__init__(parent, height=h, highlightthickness=0, bd=0, bg=behind)
        self.behind = behind
        self._hpx = h
        self._hints: list[tuple[str, str]] = []
        self._status = ""
        self.bind("<Configure>", lambda e: self._redraw(e.width))

    def set_hints(self, hints: list[tuple[str, str]]):
        self._hints = hints
        self._redraw(self.winfo_width())

    def _redraw(self, w):
        if w <= 2:
            return
        self.delete("all")
        sk = skin.get_skin()
        bar_w = min(w, px(210) + sum(px(26) + self._measure(k, v) for k, v in self._hints))
        self.create_image(w - bar_w, 0, anchor="nw", image=sk.get(
            "bar", w=bar_w, h=self._hpx, skew_left=-px(theme.BAR_SKEW), behind=self.behind))

        x = w - px(18)
        for key, label in reversed(self._hints):
            x -= self._measure_label(label)
            self.create_text(x, self._hpx // 2, text=label, font=theme.font_small(),
                             fill=theme.TEXT_BRIGHT, anchor="w")
            x -= px(6)
            kw = self._measure_key(key)
            x -= kw + px(10)
            self.create_rectangle(x, self._hpx // 2 - px(9), x + kw + px(10), self._hpx // 2 + px(9),
                                  fill=theme.BG_DEEP, outline=theme.BAR_EDGE)
            self.create_text(x + (kw + px(10)) // 2, self._hpx // 2, text=key,
                             font=theme.font_small(11), fill=theme.ACCENT)
            x -= px(16)

    def _measure(self, key, label):
        return self._measure_key(key) + self._measure_label(label)

    def _measure_key(self, key):
        from tkinter import font as tkfont
        return tkfont.Font(root=self, font=theme.font_small(11)).measure(key)

    def _measure_label(self, label):
        from tkinter import font as tkfont
        return tkfont.Font(root=self, font=theme.font_small()).measure(label)


class HaloMenuItem(tk.Canvas):
    """Big landing-menu item: dim idle, bright + fill bar + brackets on hover."""

    def __init__(self, parent, text, command=None, width=None, behind=theme.BG_DEEP):
        self._text = text
        self._command = command
        self._hover = False
        self._state = NORMAL
        self.behind = behind

        h = px(theme.MENU_ITEM_H)
        w = width or px(340)
        super().__init__(parent, width=w, height=h, highlightthickness=0, bd=0, bg=behind)
        self._wpx, self._hpx = w, h

        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<ButtonRelease-1>", self._on_click)
        self.bind("<Configure>", self._on_resize)
        self._redraw()

    def _on_resize(self, event):
        self._wpx = event.width
        self._redraw()

    def _set_hover(self, value):
        self._hover = value and self._state == NORMAL
        self._redraw()

    def set_state(self, state):
        self._state = state
        self._redraw()

    def _redraw(self):
        self.delete("all")
        if self._hover:
            self.create_rectangle(0, px(4), self._wpx, self._hpx - px(4),
                                  fill=theme.SELECT_FILL, width=0)
            self.create_rectangle(0, px(4), px(4), self._hpx - px(4),
                                  fill=theme.ACCENT, width=0)
            draw_corner_brackets(self, px(2), px(4), self._wpx - px(3), self._hpx - px(5))

        if self._state == DISABLED:
            color = theme.TEXT_DIM
        else:
            color = theme.TEXT_BRIGHT if self._hover else theme.TEXT
        self.create_text(px(24), self._hpx // 2, text=self._text, font=theme.font_menu(),
                         fill=color, anchor="w")

    def _on_click(self, event):
        if self._state != NORMAL:
            return
        if 0 <= event.x <= self._wpx and 0 <= event.y <= self._hpx and self._command:
            self._command()


class HaloScrollbar(tk.Canvas):
    """Slim themed scrollbar (native Windows scrollbars ignore color options).
    Supports the yscrollcommand/yview protocol."""

    def __init__(self, parent, command=None, behind=theme.ENTRY_FILL):
        self._track_w = px(10)
        super().__init__(parent, width=self._track_w, highlightthickness=0, bd=0, bg=behind)
        self._command = command
        self._first, self._last = 0.0, 1.0
        self._drag_anchor = None
        self._hover = False

        self.bind("<Configure>", lambda e: self._redraw())
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", lambda e: setattr(self, "_drag_anchor", None))

    def set(self, first, last):
        self._first, self._last = float(first), float(last)
        self._redraw()

    def _set_hover(self, value):
        self._hover = value
        self._redraw()

    def _thumb_bounds(self):
        h = self.winfo_height()
        y0 = round(self._first * h)
        y1 = max(y0 + px(20), round(self._last * h))
        return y0, min(y1, h)

    def _redraw(self):
        self.delete("all")
        if self._first <= 0.0 and self._last >= 1.0:
            return  # content fits; hide the thumb entirely
        y0, y1 = self._thumb_bounds()
        color = theme.SELECT_FILL if not self._hover else theme.ACCENT_DEEP
        self.create_rectangle(px(2), y0 + px(2), self._track_w - px(2), y1 - px(2),
                              fill=color, width=0)

    def _on_press(self, event):
        y0, y1 = self._thumb_bounds()
        if y0 <= event.y <= y1:
            self._drag_anchor = event.y - y0
        else:
            self._drag_anchor = (y1 - y0) // 2
            self._on_drag(event)

    def _on_drag(self, event):
        if self._drag_anchor is None or self._command is None:
            return
        h = max(1, self.winfo_height())
        frac = (event.y - self._drag_anchor) / h
        self._command("moveto", max(0.0, min(1.0, frac)))


def make_log(parent, behind=theme.PANEL_FILL) -> tuple[tk.Frame, tk.Text]:
    """Styled readonly activity log. Returns (frame, text_widget); the text
    widget keeps the tk.Text API the existing log() method uses."""
    frame = tk.Frame(parent, bg=behind)
    frame.columnconfigure(0, weight=1)
    frame.rowconfigure(0, weight=1)

    text = tk.Text(
        frame,
        height=5,
        wrap=tk.WORD,
        state=tk.DISABLED,
        bg=theme.ENTRY_FILL,
        fg=theme.TEXT,
        insertbackground=theme.ACCENT,
        selectbackground=theme.SELECT_FILL,
        selectforeground=theme.TEXT_BRIGHT,
        font=theme.font_mono(12),
        relief=tk.FLAT,
        borderwidth=0,
        highlightthickness=1,
        highlightbackground=theme.PANEL_BORDER_DIM,
        highlightcolor=theme.PANEL_BORDER_DIM,
        padx=px(8),
        pady=px(6),
    )

    scrollbar = HaloScrollbar(frame, command=text.yview, behind=theme.ENTRY_FILL)
    text.configure(yscrollcommand=scrollbar.set)

    text.grid(row=0, column=0, sticky="nsew")
    scrollbar.grid(row=0, column=1, sticky="ns", padx=(px(2), 0))

    return frame, text
