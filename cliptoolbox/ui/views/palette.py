"""Command palette — a searchable Ctrl+K overlay over the active screen.

Built on the same dim-overlay + card-Toplevel pattern as SettingsOverlay and
the Halo dialogs: an ``overrideredirect`` 45%-alpha scrim plus an opaque card
that grabs input. It lists the command registry (``ui/commands.py``); commands
that aren't currently runnable render greyed but still show their shortcut, so
the palette doubles as an always-current cheat-sheet (roadmap B3).
"""
import tkinter as tk

from cliptoolbox.ui import commands, theme, widgets
from cliptoolbox.ui.theme import px


class CommandPalette:
    def __init__(self, app):
        self.app = app
        root = app.root
        self.commands = commands.build_command_registry(app)

        self._card_w = px(540)
        self._list_h = px(300)
        self._rows: list[dict] = []       # {"cmd", "frame", "enabled"} in display order
        self._selectable: list[int] = []  # indices into _rows that are runnable
        self._sel = 0                     # position within _selectable

        # --- dim scrim ---------------------------------------------------
        self.overlay = tk.Toplevel(root)
        self.overlay.overrideredirect(True)
        self.overlay.configure(bg="#000000")
        try:
            self.overlay.attributes("-alpha", 0.45)
        except Exception:
            pass

        # --- card --------------------------------------------------------
        self.card_win = tk.Toplevel(root)
        self.card_win.overrideredirect(True)
        self.card_win.configure(bg=theme.PANEL_BORDER)

        card = tk.Frame(self.card_win, bg=theme.PANEL_FILL)
        card.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

        strip = tk.Frame(card, bg=theme.TITLE_FILL)
        strip.pack(fill=tk.X)
        tk.Frame(strip, bg=theme.ACCENT, width=px(4)).pack(side=tk.LEFT, fill=tk.Y)
        tk.Label(strip, text="COMMANDS", font=theme.font_title(13),
                 bg=theme.TITLE_FILL, fg=theme.ACCENT).pack(side=tk.LEFT, padx=(px(10), px(6)), pady=px(5))
        tk.Label(strip, text="CTRL+K", font=theme.font_small(11),
                 bg=theme.TITLE_FILL, fg=theme.TEXT_DIM).pack(side=tk.RIGHT, padx=px(10))

        body = tk.Frame(card, bg=theme.PANEL_FILL)
        body.pack(fill=tk.BOTH, expand=True, padx=px(16), pady=px(14))

        self.query_var = tk.StringVar()
        self.search = widgets.HaloEntry(
            body, textvariable=self.query_var, width=1,
            behind=theme.PANEL_FILL, justify="left", font=theme.font_body())
        self.search.pack(fill=tk.X)

        # --- results (canvas so the list can scroll) ---------------------
        list_wrap = tk.Frame(body, bg=theme.PANEL_FILL)
        list_wrap.pack(fill=tk.BOTH, expand=True, pady=(px(12), 0))
        self.canvas = tk.Canvas(list_wrap, bg=theme.PANEL_FILL, height=self._list_h,
                                highlightthickness=0, bd=0)
        self.scroll = widgets.HaloScrollbar(list_wrap, command=self.canvas.yview,
                                            behind=theme.PANEL_FILL)
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.rows_frame = tk.Frame(self.canvas, bg=theme.PANEL_FILL)
        self._rows_win = self.canvas.create_window(0, 0, anchor="nw", window=self.rows_frame)
        self.canvas.bind("<Configure>",
                         lambda e: self.canvas.itemconfig(self._rows_win, width=e.width))
        self.rows_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

        # --- keys --------------------------------------------------------
        entry = self.search.entry
        self.query_var.trace_add("write", lambda *a: self._refilter())
        entry.bind("<Down>", lambda e: self._move(1))
        entry.bind("<Up>", lambda e: self._move(-1))
        entry.bind("<Return>", lambda e: self._activate())
        entry.bind("<Escape>", lambda e: self.close())
        entry.bind("<Control-k>", lambda e: self.close())
        entry.bind("<Control-K>", lambda e: self.close())
        for target in (self.canvas, self.rows_frame):
            target.bind("<MouseWheel>", self._on_wheel)

        self._configure_bind = root.bind("<Configure>", self._reposition, add="+")
        self._refilter()
        self._reposition()

        self.overlay.lift(root)
        self.card_win.lift(self.overlay)
        try:
            self.card_win.grab_set()
        except Exception:
            pass
        entry.focus_force()

    # ------------------------------------------------------------------
    # Filtering / rendering
    # ------------------------------------------------------------------
    def _refilter(self):
        query = self.query_var.get()
        order = {c.id: i for i, c in enumerate(self.commands)}
        matched = []
        for cmd in self.commands:
            s = commands.score(query, cmd.searchable())
            if s is None:
                continue
            matched.append((cmd, cmd.enabled(), s))
        # Runnable commands first, then by fuzzy rank, then registry order.
        matched.sort(key=lambda m: (0 if m[1] else 1, m[2], order[m[0].id]))
        self._render(matched)

    def _render(self, matched):
        for child in self.rows_frame.winfo_children():
            child.destroy()
        self._rows = []
        self._selectable = []

        if not matched:
            tk.Label(self.rows_frame, text="No matching commands",
                     font=theme.font_body(), bg=theme.PANEL_FILL, fg=theme.TEXT_DIM,
                     anchor="w").pack(fill=tk.X, padx=px(6), pady=px(10))
            self._sel = 0
            return

        for cmd, enabled, _ in matched:
            row = tk.Frame(self.rows_frame, bg=theme.PANEL_FILL)
            row.pack(fill=tk.X)
            fg = theme.TEXT if enabled else theme.TEXT_DIM
            label = tk.Label(row, text=cmd.label, font=theme.font_body(),
                             bg=theme.PANEL_FILL, fg=fg, anchor="w")
            label.pack(side=tk.LEFT, padx=(px(8), px(6)), pady=px(5))
            cat = tk.Label(row, text=cmd.category.upper(), font=theme.font_small(10),
                           bg=theme.PANEL_FILL, fg=theme.TEXT_DIM, anchor="w")
            cat.pack(side=tk.LEFT)

            chip = None
            if cmd.keys:
                chip = tk.Label(row, text=cmd.keys, font=theme.font_small(11),
                                bg=theme.BG_DEEP, fg=theme.TEXT_DIM, padx=px(6), pady=px(1))
                chip.pack(side=tk.RIGHT, padx=(px(6), px(8)))

            entry = {"cmd": cmd, "frame": row, "enabled": enabled,
                     "labels": [w for w in (label, cat) ], "chip": chip}
            idx = len(self._rows)
            self._rows.append(entry)
            if enabled:
                self._selectable.append(idx)

            for w in (row, label, cat) + ((chip,) if chip else ()):
                w.bind("<MouseWheel>", self._on_wheel)
                if enabled:
                    w.bind("<Enter>", lambda e, i=idx: self._select_row(i))
                    w.bind("<ButtonRelease-1>", lambda e, c=cmd: self._run(c))

        self._sel = 0 if self._selectable else -1
        self._paint_selection()

    # ------------------------------------------------------------------
    # Selection / navigation
    # ------------------------------------------------------------------
    def _paint_selection(self):
        sel_row = self._selectable[self._sel] if 0 <= self._sel < len(self._selectable) else -1
        for i, entry in enumerate(self._rows):
            selected = (i == sel_row)
            bg = theme.SELECT_FILL if selected else theme.PANEL_FILL
            if selected:
                fg = theme.SELECT_TEXT
            else:
                fg = theme.TEXT if entry["enabled"] else theme.TEXT_DIM
            entry["frame"].configure(bg=bg)
            for w in entry["labels"]:
                w.configure(bg=bg, fg=(fg if w is entry["labels"][0] else
                                       (theme.SELECT_TEXT if selected else theme.TEXT_DIM)))
            if entry["chip"] is not None:
                entry["chip"].configure(bg=theme.BG_DEEP if not selected else theme.PANEL_FILL_HI)
        if sel_row >= 0:
            self._scroll_into_view(self._rows[sel_row]["frame"])

    def _select_row(self, row_index):
        """Point selection at a hovered enabled row."""
        if row_index in self._selectable:
            self._sel = self._selectable.index(row_index)
            self._paint_selection()

    def _move(self, delta):
        if not self._selectable:
            return "break"
        self._sel = (self._sel + delta) % len(self._selectable)
        self._paint_selection()
        return "break"

    def _scroll_into_view(self, row_frame):
        try:
            self.canvas.update_idletasks()
            view_h = self.canvas.winfo_height()
            if view_h <= 1:            # not mapped yet: fall back to configured height
                view_h = self._list_h
            total = max(1, self.rows_frame.winfo_reqheight())
            if total <= view_h:        # everything fits — keep the top in view
                self.canvas.yview_moveto(0.0)
                return
            top = row_frame.winfo_y()
            bottom = top + row_frame.winfo_height()
            view_top = self.canvas.canvasy(0)
            if top < view_top:
                self.canvas.yview_moveto(top / total)
            elif bottom > view_top + view_h:
                self.canvas.yview_moveto((bottom - view_h) / total)
        except Exception:
            pass

    def _on_wheel(self, event):
        self.canvas.yview_scroll(-1 * (event.delta // 120), "units")
        return "break"

    # ------------------------------------------------------------------
    # Activation
    # ------------------------------------------------------------------
    def _activate(self):
        if 0 <= self._sel < len(self._selectable):
            self._run(self._rows[self._selectable[self._sel]]["cmd"])
        return "break"

    def _run(self, cmd):
        if not cmd.enabled():
            return
        root = self.app.root
        self._teardown()
        # Run after the grab is fully released so actions that open their own
        # overlay (export dialog, settings) get a clean focus/grab state.
        root.after(1, cmd.run)

    # ------------------------------------------------------------------
    # Window plumbing
    # ------------------------------------------------------------------
    def _reposition(self, _event=None):
        try:
            root = self.app.root
            rx, ry = root.winfo_rootx(), root.winfo_rooty()
            rw, rh = root.winfo_width(), root.winfo_height()
            self.overlay.geometry(f"{rw}x{rh}+{rx}+{ry}")
            self.card_win.update_idletasks()
            ch = self.card_win.winfo_reqheight()
            cx = rx + (rw - self._card_w) // 2
            cy = ry + max(px(20), round(rh * 0.30) - ch // 2)
            self.card_win.geometry(f"{self._card_w}x{ch}+{cx}+{cy}")
        except Exception:
            pass

    def close(self):
        self._teardown()
        return "break"

    def _teardown(self):
        if getattr(self.app, "command_palette", None) is self:
            self.app.command_palette = None
        try:
            self.card_win.grab_release()
        except Exception:
            pass
        try:
            self.app.root.unbind("<Configure>", self._configure_bind)
        except Exception:
            pass
        for window in (self.card_win, self.overlay):
            try:
                window.destroy()
            except Exception:
                pass
        try:
            self.app.root.focus_set()
        except Exception:
            pass
