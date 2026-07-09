"""The landing screen — ClipToolbox's take on the Halo 2 main menu.

Big wordmark, a vertical menu (LOAD CLIP / RECENT CLIPS / SETTINGS / QUIT),
and a right-side detail panel that follows the hovered item, like the
CURRENT MAP box in the game's setup screens. The whole window stays a drop
target; dropping a clip jumps straight into the workspace.
"""
import tkinter as tk
from pathlib import Path

from cliptoolbox.ui import skin, theme
from cliptoolbox.ui.theme import px
from cliptoolbox.ui.widgets import HaloMenuItem

SUPPORTED_LINE = "MP4 · MOV · MKV · AVI · WebM · M4V"


def _add_recent_row(app, parent, path):
    """One recent-clip entry: thumbnail (lazy) + name, clickable to load, with
    a right-click menu to reveal or remove."""
    name = Path(path).name
    exists = Path(path).exists()

    row = tk.Frame(parent, bg=theme.PANEL_FILL, cursor="hand2" if exists else "arrow")
    row.pack(fill=tk.X, pady=px(2))

    # Fixed 16:9 holder so the row height is stable before the thumb loads.
    thumb_h = px(app.THUMBNAIL_HEIGHT)
    thumb_holder = tk.Frame(row, bg="#0A1626", width=round(thumb_h * 16 / 9), height=thumb_h)
    thumb_holder.pack(side=tk.LEFT, padx=(0, px(8)))
    thumb_holder.pack_propagate(False)
    thumb = tk.Label(thumb_holder, bg="#0A1626", bd=0)
    thumb.pack(fill=tk.BOTH, expand=True)

    name_label = tk.Label(
        row, text=("▸ " if exists else "✕ ") + name,
        font=theme.font_body(13), bg=theme.PANEL_FILL,
        fg=theme.TEXT if exists else theme.TEXT_DIM, anchor="w",
    )
    name_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

    hover_widgets = (row, thumb_holder, thumb, name_label)

    def set_bg(color, fg):
        for w in (row, name_label):
            w.configure(bg=color)
        name_label.configure(fg=fg)

    if exists:
        for w in hover_widgets:
            w.bind("<Enter>", lambda e: set_bg(theme.SELECT_FILL, theme.TEXT_BRIGHT))
            w.bind("<Leave>", lambda e: set_bg(theme.PANEL_FILL, theme.TEXT))
            w.bind("<ButtonRelease-1>", lambda e, p=path: app.load_video(p))

        def on_ready(photo, lbl=thumb):
            if photo is not None:
                try:
                    lbl.configure(image=photo)
                    lbl.image = photo
                except Exception:
                    pass

        app.get_recent_thumbnail(path, on_ready)

    def show_menu(event, p=path):
        menu = tk.Menu(app.root, tearoff=0)
        if exists:
            menu.add_command(label="Reveal in folder", command=lambda: app.reveal_file(p))
        menu.add_command(label="Remove from list", command=lambda: app.remove_recent_clip(p))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    for w in hover_widgets:
        w.bind("<Button-3>", show_menu)

DETAILS = {
    "load": (
        "LOAD CLIP",
        "Open a video file to trim, mix its audio tracks,\n"
        "and export — optionally compressed to a target\n"
        "size for Discord.\n\n"
        f"Supported: {SUPPORTED_LINE}\n\n"
        "You can also drop a file anywhere in this window.",
    ),
    "recent": ("RECENT CLIPS", ""),  # body built dynamically
    "settings": (
        "SETTINGS",
        "Window chrome, library shortcuts, and info.\n\n"
        "Compression target, resolution and the rest of\n"
        "your workspace state are remembered\n"
        "automatically between sessions.",
    ),
    "quit": ("QUIT", "Exit ClipToolbox."),
}


def build(app):
    frame = tk.Frame(app.screen_container, bg=theme.BG_DEEP)
    frame.place(x=0, y=0, relwidth=1.0, relheight=1.0)
    app.landing_frame = frame

    canvas = tk.Canvas(frame, highlightthickness=0, bd=0, bg=theme.BG_DEEP)
    canvas.pack(fill=tk.BOTH, expand=True)

    state = {"resize_job": None, "detail_key": "load"}

    # --- right detail panel (a plain frame; the canvas draws its chrome) ---
    detail = tk.Frame(canvas, bg=theme.PANEL_FILL)
    detail_title = tk.Label(detail, text="", font=theme.font_title(14),
                            bg=theme.PANEL_FILL, fg=theme.ACCENT, anchor="w")
    detail_title.pack(fill=tk.X, padx=px(16), pady=(px(12), px(4)))
    detail_body = tk.Frame(detail, bg=theme.PANEL_FILL)
    detail_body.pack(fill=tk.BOTH, expand=True, padx=px(16), pady=(0, px(12)))

    def clear_detail_body():
        for child in detail_body.winfo_children():
            child.destroy()

    def show_detail(key):
        state["detail_key"] = key
        title, body = DETAILS[key]
        detail_title.configure(text=title)
        clear_detail_body()

        if key == "recent":
            recents = [p for p in app.recent_clips]
            if not recents:
                tk.Label(detail_body, text="No recent clips yet.",
                         font=theme.font_body(), bg=theme.PANEL_FILL,
                         fg=theme.TEXT_DIM, anchor="w", justify=tk.LEFT).pack(fill=tk.X)
            for path in recents[:6]:
                _add_recent_row(app, detail_body, path)
        else:
            tk.Label(detail_body, text=body, font=theme.font_body(),
                     bg=theme.PANEL_FILL, fg=theme.TEXT,
                     anchor="nw", justify=tk.LEFT).pack(fill=tk.BOTH, expand=True)

    app.refresh_landing_detail = lambda: show_detail(state["detail_key"])
    app.show_landing_detail = show_detail

    # --- menu ----------------------------------------------------------
    menu = tk.Frame(canvas, bg=theme.BG_DEEP)

    items = [
        ("LOAD CLIP", app.load_video_dialog, "load"),
        ("RECENT CLIPS", lambda: show_detail("recent"), "recent"),
        ("SETTINGS", app.open_settings, "settings"),
        ("QUIT", app.on_close, "quit"),
    ]

    app.landing_menu_items = []
    for text, command, key in items:
        item = HaloMenuItem(menu, text, command=command, width=px(320),
                            hover_command=lambda k=key: show_detail(k))
        item.pack(pady=px(2))
        app.landing_menu_items.append(item)

    # --- layout / background -------------------------------------------
    def render(width, height):
        canvas.delete("all")
        sk = skin.get_skin()
        canvas.create_image(0, 0, anchor="nw", image=sk.get("background", w=width, h=height))

        wm_size = max(px(34), min(px(56), width // 16))
        canvas.create_image(round(width * 0.5), round(height * 0.20),
                            image=sk.get("wordmark", text="CLIPTOOLBOX", size_px=wm_size),
                            anchor="center")
        canvas.create_text(round(width * 0.5), round(height * 0.20) + wm_size,
                           text="TRIM  ·  MIX  ·  COMPRESS",
                           font=theme.font_title(13), fill=theme.TEXT_DIM, anchor="center")

        menu_x = round(width * 0.30)
        canvas.create_window(menu_x, round(height * 0.56), window=menu, anchor="center")

        panel_w, panel_h = px(360), px(300)
        panel_x = round(width * 0.66)
        panel_y = round(height * 0.56) - panel_h // 2
        canvas.create_image(panel_x - px(12), panel_y - px(12), anchor="nw", image=sk.get(
            "panel", w=panel_w + px(24), h=panel_h + px(24)))
        canvas.create_window(panel_x, panel_y, window=detail, anchor="nw",
                             width=panel_w, height=panel_h)

    def on_resize(event):
        if state["resize_job"] is not None:
            try:
                frame.after_cancel(state["resize_job"])
            except Exception:
                pass
        state["resize_job"] = frame.after(
            80, lambda: render(max(2, canvas.winfo_width()), max(2, canvas.winfo_height())))

    canvas.bind("<Configure>", on_resize)
    show_detail("load")
