"""The workspace's empty state — what the single adaptive screen shows when
no clip is loaded (B2; replaces the old landing menu).

Full-body hero: wordmark, a drop-zone line (drag-and-drop promoted from a
hidden path to THE primary path), and a RECENT CLIPS thumbnail grid placed
roughly where the preview bezel sits in the editor, so loading a clip feels
like the grid becoming the video.

``RecentsGrid`` is deliberately self-contained — every dependency is
injected — so the widget gallery can render it without an app instance.
"""
import tkinter as tk
from pathlib import Path

from cliptoolbox import sessions as video_sessions
from cliptoolbox.ui import skin, theme
from cliptoolbox.ui.theme import px
from cliptoolbox.ui.widgets import Tooltip

SUPPORTED_LINE = "MP4 · MOV · MKV · AVI · WebM · M4V"

GRID_THUMB_HEIGHT = 72   # logical px; 16:9 holders derive their width
GRID_COLUMNS = 4
GRID_MAX = 8             # matches the recent_clips settings cap

_CAPTION_MAX = 20


def _ellipsize(name: str) -> str:
    if len(name) <= _CAPTION_MAX:
        return name
    return name[:9] + "…" + name[-9:]


class RecentsGrid(tk.Frame):
    """Keyboard-navigable grid of recent-clip cards.

    entries: list of {path, name, exists, has_session} dicts (max GRID_MAX).
    Selection is one shared highlight driven by both hover and arrow keys;
    Enter/click opens, Delete/context-menu removes.
    """

    def __init__(self, parent, thumb_provider, on_open, on_remove, on_reveal,
                 behind=theme.PANEL_FILL, columns=GRID_COLUMNS):
        super().__init__(parent, bg=behind)
        self._thumb_provider = thumb_provider
        self._on_open = on_open
        self._on_remove = on_remove
        self._on_reveal = on_reveal
        self._behind = behind
        self._columns = max(1, columns)
        self._entries: list[dict] = []
        self._cards: list[dict] = []
        self._selected: int | None = None

    # ------------------------------------------------------------ state

    def has_entries(self) -> bool:
        return bool(self._entries)

    @property
    def selection_index(self):
        return self._selected

    def selected_entry(self) -> dict | None:
        if self._selected is None or self._selected >= len(self._entries):
            return None
        return self._entries[self._selected]

    def set_entries(self, entries: list[dict]):
        old_path = (self.selected_entry() or {}).get("path")
        old_index = self._selected

        for child in self.winfo_children():
            child.destroy()
        self._entries = list(entries[:GRID_MAX])
        self._cards = []
        self._selected = None

        if not self._entries:
            tk.Label(self, text="No recent clips yet — drop a video to get started.",
                     font=theme.font_body(12), bg=self._behind,
                     fg=theme.TEXT_DIM).grid(row=0, column=0,
                                             padx=px(24), pady=px(20))
            return

        for index, entry in enumerate(self._entries):
            self._add_card(index, entry)

        # Keep the selection through a rebuild: same path if still present,
        # else the same slot clamped (the Delete-key flow lands here).
        if old_path is not None or old_index is not None:
            for index, entry in enumerate(self._entries):
                if entry["path"] == old_path:
                    self.select_index(index)
                    return
            if old_index is not None:
                self.select_index(min(old_index, len(self._entries) - 1))

    # ------------------------------------------------------------ cards

    def _add_card(self, index: int, entry: dict):
        exists = entry.get("exists", True)

        card = tk.Frame(
            self, bg=self._behind,
            highlightthickness=px(2),
            highlightbackground=theme.PANEL_BORDER_DIM,
            highlightcolor=theme.PANEL_BORDER_DIM,
            cursor="hand2" if exists else "arrow",
        )
        card.grid(row=index // self._columns, column=index % self._columns,
                  padx=px(4), pady=px(4))

        # Fixed 16:9 holder so the card is stable before the thumb arrives.
        thumb_h = px(GRID_THUMB_HEIGHT)
        holder = tk.Frame(card, bg=theme.WELL_FILL,
                          width=round(thumb_h * 16 / 9), height=thumb_h)
        holder.pack(padx=px(4), pady=(px(4), px(2)))
        holder.pack_propagate(False)
        thumb = tk.Label(holder, bg=theme.WELL_FILL, bd=0)
        thumb.pack(fill=tk.BOTH, expand=True)

        dot = None
        if entry.get("has_session") and exists:
            dot = tk.Label(holder, text="●", font=theme.font_small(11),
                           bg=theme.WELL_FILL, fg=theme.ACCENT, bd=0)
            dot.place(relx=1.0, y=px(1), x=-px(4), anchor="ne")
            Tooltip(dot, "Saved setup — trim/crop/mix restore on load")

        caption = tk.Label(
            card, text=("" if exists else "✕ ") + _ellipsize(entry.get("name", "")),
            font=theme.font_small(11), bg=self._behind,
            fg=theme.TEXT if exists else theme.TEXT_DIM, anchor="center",
        )
        caption.pack(fill=tk.X, padx=px(4), pady=(0, px(3)))

        record = {"frame": card, "holder": holder, "thumb": thumb,
                  "caption": caption, "dot": dot, "entry": entry}
        self._cards.append(record)

        targets = [card, holder, thumb, caption] + ([dot] if dot is not None else [])
        for w in targets:
            w.bind("<Enter>", lambda e, i=index: self.select_index(i))
            w.bind("<Button-3>", lambda e, i=index: self._show_menu(e, i))
            if exists:
                w.bind("<ButtonRelease-1>",
                       lambda e, p=entry["path"]: self._on_open(p))

        if exists:
            def on_ready(photo, label=thumb):
                if photo is None:
                    return
                try:
                    if label.winfo_exists():
                        label.configure(image=photo)
                        label.image = photo
                except tk.TclError:
                    pass  # card rebuilt while the worker extracted the thumb

            self._thumb_provider(entry["path"], on_ready)

    def _show_menu(self, event, index: int):
        entry = self._entries[index]
        menu = tk.Menu(self, tearoff=0)
        if entry.get("exists", True):
            menu.add_command(label="Reveal in folder",
                             command=lambda: self._on_reveal(entry["path"]))
        menu.add_command(label="Remove from list",
                         command=lambda: self._on_remove(entry["path"]))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _paint(self, index: int):
        record = self._cards[index]
        entry = record["entry"]
        selected = index == self._selected
        ring = theme.ACCENT if selected else theme.PANEL_BORDER_DIM
        bg = theme.SELECT_FILL if selected else self._behind
        fg = (theme.SELECT_TEXT if selected
              else theme.TEXT if entry.get("exists", True) else theme.TEXT_DIM)
        record["frame"].configure(highlightbackground=ring, highlightcolor=ring, bg=bg)
        record["caption"].configure(bg=bg, fg=fg)

    # ------------------------------------------------------- selection

    def select_index(self, index: int | None):
        if index is not None and not (0 <= index < len(self._entries)):
            index = None
        previous, self._selected = self._selected, index
        if previous is not None and previous < len(self._cards):
            self._paint(previous)
        if index is not None:
            self._paint(index)

    def move_selection(self, d_col: int = 0, d_row: int = 0) -> bool:
        count = len(self._entries)
        if not count:
            return False
        if self._selected is None:
            self.select_index(0)
            return True
        index = self._selected + d_col + d_row * self._columns
        self.select_index(min(max(index, 0), count - 1))
        return True

    def activate_selected(self) -> str | None:
        entry = self.selected_entry()
        if entry is None:
            return None
        if not entry.get("exists", True):
            return "missing"
        self._on_open(entry["path"])
        return "opened"

    def remove_selected(self) -> str | None:
        entry = self.selected_entry()
        if entry is None:
            return None
        self._on_remove(entry["path"])
        return entry["path"]


# ---------------------------------------------------------------------------
# The hero screen itself (app-wired half; the gallery only uses RecentsGrid)
# ---------------------------------------------------------------------------

def build(app):
    frame = tk.Frame(app.screen_container, bg=theme.BG_DEEP)
    frame.place(x=0, y=0, relwidth=1.0, relheight=1.0)
    app.empty_state_frame = frame

    canvas = tk.Canvas(frame, highlightthickness=0, bd=0, bg=theme.BG_DEEP)
    canvas.pack(fill=tk.BOTH, expand=True)

    state = {"resize_job": None}

    # DnD failure hint (written by enable_drag_and_drop); the hero renders it
    # in place of the drop line, since the drop line would be a lie then.
    if not hasattr(app, "dnd_hint_var"):
        app.dnd_hint_var = tk.StringVar(value="")

    # --- RECENT CLIPS panel (a frame the canvas windows in) --------------
    panel = tk.Frame(canvas, bg=theme.PANEL_FILL)
    tk.Label(panel, text="RECENT CLIPS", font=theme.font_title(14),
             bg=theme.PANEL_FILL, fg=theme.ACCENT, anchor="w").pack(
        fill=tk.X, padx=px(14), pady=(px(10), px(2)))

    grid = RecentsGrid(
        panel,
        thumb_provider=lambda p, cb: app.get_recent_thumbnail(
            p, cb, height=GRID_THUMB_HEIGHT),
        on_open=app.load_video,
        on_remove=app.remove_recent_clip,
        on_reveal=app.reveal_file,
    )
    grid.pack(padx=px(14), pady=(px(2), px(12)))
    app.recents_grid = grid

    build_label = tk.Label(canvas, textvariable=app.build_line_var,
                           font=theme.font_mono(), bg=theme.BG_DEEP,
                           fg=theme.TEXT_DIM)

    # --- layout / background ---------------------------------------------
    def render(width, height):
        canvas.delete("all")
        sk = skin.get_skin()
        canvas.create_image(0, 0, anchor="nw",
                            image=sk.get("background", w=width, h=height))

        wm_size = max(px(34), min(px(56), width // 16))
        wm_y = round(height * 0.15)
        canvas.create_image(round(width * 0.5), wm_y,
                            image=sk.get("wordmark", text="CLIPTOOLBOX",
                                         size_px=wm_size),
                            anchor="center")
        canvas.create_text(round(width * 0.5), wm_y + wm_size,
                           text="TRIM  ·  MIX  ·  COMPRESS",
                           font=theme.font_title(13), fill=theme.TEXT_DIM,
                           anchor="center")

        drop_y = round(height * 0.31)
        hint = app.dnd_hint_var.get()
        if hint:
            canvas.create_text(round(width * 0.5), drop_y, text=hint,
                               font=theme.font_body(12), fill=theme.ERR_RED,
                               anchor="center")
            canvas.create_text(round(width * 0.5), drop_y + px(24),
                               text="DOUBLE-CLICK OR CTRL+O TO BROWSE",
                               font=theme.font_title(15), fill=theme.TEXT,
                               anchor="center")
        else:
            canvas.create_text(round(width * 0.5), drop_y,
                               text="DROP A VIDEO  ·  DOUBLE-CLICK  ·  CTRL+O TO BROWSE",
                               font=theme.font_title(15), fill=theme.TEXT,
                               anchor="center")
            canvas.create_text(round(width * 0.5), drop_y + px(26),
                               text=SUPPORTED_LINE,
                               font=theme.font_small(12), fill=theme.TEXT_DIM,
                               anchor="center")

        # Panel sits where the editor's preview bezel lives, so the load
        # transition reads as the grid becoming the video.
        panel.update_idletasks()
        panel_w = panel.winfo_reqwidth()
        panel_y = round(height * 0.40)
        panel_x = round(width * 0.5)
        canvas.create_image(panel_x - panel_w // 2 - px(12), panel_y - px(12),
                            anchor="nw",
                            image=sk.get("panel", w=panel_w + px(24),
                                         h=panel.winfo_reqheight() + px(24)))
        canvas.create_window(panel_x, panel_y, window=panel, anchor="n")

        canvas.create_window(px(14), height - px(8), window=build_label,
                             anchor="sw")

    def schedule_render(*_):
        if state["resize_job"] is not None:
            try:
                frame.after_cancel(state["resize_job"])
            except Exception:
                pass
        state["resize_job"] = frame.after(
            80, lambda: render(max(2, canvas.winfo_width()),
                               max(2, canvas.winfo_height())))

    canvas.bind("<Configure>", schedule_render)
    # Double-clicking the hero background opens the file browser (the cards
    # windowed onto the canvas handle their own single-click load, so this
    # only fires on the empty backdrop / drop-zone text).
    canvas.bind("<Double-Button-1>", lambda e: app.load_video_dialog())
    app.dnd_hint_var.trace_add("write", schedule_render)

    def refresh():
        recents = list(app.recent_clips[:GRID_MAX])
        saved = video_sessions.paths_with_sessions(recents)
        grid.set_entries([
            {"path": p, "name": Path(p).name, "exists": Path(p).exists(),
             "has_session": p in saved}
            for p in recents
        ])
        schedule_render()  # the panel resizes with its contents
        app.update_legend()  # grid-nav hints appear/disappear with entries

    app.refresh_recents_grid = refresh
    refresh()
