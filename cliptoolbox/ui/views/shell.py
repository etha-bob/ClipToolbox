"""Window shell: custom Halo header (drag / minimize / maximize / close),
status strip, screen container, and footer legend bar."""
import time
import tkinter as tk

from cliptoolbox.constants import APP_NAME
from cliptoolbox.ui import chrome, skin, theme
from cliptoolbox.ui.theme import px
from cliptoolbox.ui.widgets import LegendBar

UI_VERSION = "2.0"


def build(app):
    root = app.root

    root.columnconfigure(0, weight=1)
    root.rowconfigure(2, weight=1)

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------
    header_h = px(theme.HEADER_H)
    header = tk.Canvas(root, height=header_h, highlightthickness=0, bd=0, bg=theme.BG_DEEP)
    header.grid(row=0, column=0, sticky="ew")
    app.header = header

    app.file_label_var = tk.StringVar(value="No video loaded")

    def redraw_header(event=None):
        w = header.winfo_width()
        if w <= 2:
            return
        header.delete("all")
        sk = skin.get_skin()
        bar_w = max(px(320), round(w * 0.62))
        header.create_image(0, 0, anchor="nw", image=sk.get(
            "bar", w=bar_w, h=header_h, skew_right=-px(theme.BAR_SKEW)))
        header.create_text(px(20), header_h // 2, text=APP_NAME.upper(),
                           font=theme.font_title(16), fill=theme.TEXT_BRIGHT, anchor="w")
        name = app.file_label_var.get()
        if name and name != "No video loaded":
            header.create_text(px(190), header_h // 2, text="▸  " + name,
                               font=theme.font_body(13), fill=theme.TEXT, anchor="w")

    header.bind("<Configure>", redraw_header)
    app.file_label_var.trace_add("write", lambda *a: redraw_header())

    # Drag to move + double-click to maximize (native snap keeps working
    # because WS_THICKFRAME is retained by the chrome).
    header.bind("<ButtonPress-1>", lambda e: chrome.begin_drag(root))
    header.bind("<Double-Button-1>", lambda e: chrome.toggle_maximize(root))

    # Window buttons.
    controls = tk.Frame(root, bg=theme.BG_DEEP)
    controls.place(in_=header, relx=1.0, rely=0, anchor="ne")

    def window_button(text, command, hover_bg):
        label = tk.Label(controls, text=text, font=theme.font_body(13),
                         bg=theme.BG_DEEP, fg=theme.TEXT, width=4, height=1, pady=px(6))
        label.pack(side=tk.LEFT)
        label.bind("<Enter>", lambda e: label.configure(bg=hover_bg, fg=theme.TEXT_BRIGHT))
        label.bind("<Leave>", lambda e: label.configure(bg=theme.BG_DEEP, fg=theme.TEXT))
        label.bind("<ButtonRelease-1>", lambda e: command())
        return label

    window_button("—", root.iconify, theme.PANEL_FILL_HI)
    window_button("□", lambda: chrome.toggle_maximize(root), theme.PANEL_FILL_HI)
    window_button("✕", lambda: app.on_close(), theme.MAROON)

    # ------------------------------------------------------------------
    # Status strip (the Cartographer-style build line + live status)
    # ------------------------------------------------------------------
    strip = tk.Frame(root, bg=theme.BG_DEEP)
    strip.grid(row=1, column=0, sticky="ew", padx=px(14), pady=(px(4), 0))
    strip.columnconfigure(1, weight=1)

    app.build_line_var = tk.StringVar(
        value=f"{APP_NAME} v{UI_VERSION} — Build {time.strftime('%b %d %Y')}  |  ffmpeg: ok")
    tk.Label(strip, textvariable=app.build_line_var, font=theme.font_mono(),
             bg=theme.BG_DEEP, fg=theme.TEXT_DIM, anchor="w").grid(row=0, column=0, sticky="w")

    app.status_var = tk.StringVar(value="Ready")

    # Long status lines (export paths) get middle-ellipsized so they never
    # spill over the build line on the left.
    status_display = tk.StringVar(value="Ready")

    def sync_status(*_):
        text = app.status_var.get()
        if len(text) > 88:
            text = text[:42] + " … " + text[-42:]
        status_display.set(text)

    app.status_var.trace_add("write", sync_status)
    tk.Label(strip, textvariable=status_display, font=theme.font_mono(),
             bg=theme.BG_DEEP, fg=theme.TEXT, anchor="e").grid(row=0, column=1, sticky="e")

    # ------------------------------------------------------------------
    # Screen container + legend
    # ------------------------------------------------------------------
    app.screen_container = tk.Frame(root, bg=theme.BG_DEEP)
    app.screen_container.grid(row=2, column=0, sticky="nsew")

    app.legend = LegendBar(root)
    app.legend.grid(row=3, column=0, sticky="ew")
    app.legend.set_hints([])
