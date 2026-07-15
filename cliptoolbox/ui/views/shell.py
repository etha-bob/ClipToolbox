"""Window shell: status strip, screen container, and footer legend bar.

Uses the native Windows title bar for drag/minimize/maximize/close —
ClipToolbox no longer draws its own header (see cliptoolbox.ui.chrome for
why the custom-titlebar drag/maximize handling was dropped)."""
import time
import tkinter as tk

from cliptoolbox.constants import APP_NAME
from cliptoolbox.ui import theme
from cliptoolbox.ui.theme import px
from cliptoolbox.ui.widgets import LegendBar

UI_VERSION = "2.0"


def build(app):
    root = app.root

    root.columnconfigure(0, weight=1)
    root.rowconfigure(1, weight=1)

    # Set by app.py when a clip loads (and reset on show_landing); rendered
    # as the status strip's middle column below.
    app.file_label_var = tk.StringVar(value="No video loaded")

    # ------------------------------------------------------------------
    # Status strip (the Cartographer-style build line + live status)
    # ------------------------------------------------------------------
    strip = tk.Frame(root, bg=theme.BG_DEEP)
    strip.grid(row=0, column=0, sticky="ew", padx=px(14), pady=(px(4), 0))
    strip.columnconfigure(1, weight=1)

    app.build_line_var = tk.StringVar(
        value=f"{APP_NAME} v{UI_VERSION} — Build {time.strftime('%b %d %Y')}  |  ffmpeg: ok")
    tk.Label(strip, textvariable=app.build_line_var, font=theme.font_mono(),
             bg=theme.BG_DEEP, fg=theme.TEXT_DIM, anchor="w").grid(row=0, column=0, sticky="w")

    # Middle column: the loaded clip's name, middle-ellipsized like the
    # status line so long names never crowd their neighbours.
    file_display = tk.StringVar()

    def sync_file_label(*_):
        text = app.file_label_var.get()
        if len(text) > 48:
            text = text[:22] + " … " + text[-22:]
        file_display.set(text)

    app.file_label_var.trace_add("write", sync_file_label)
    sync_file_label()
    tk.Label(strip, textvariable=file_display, font=theme.font_mono(),
             bg=theme.BG_DEEP, fg=theme.TEXT_DIM, anchor="center").grid(
                 row=0, column=1, sticky="ew", padx=px(16))

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
             bg=theme.BG_DEEP, fg=theme.TEXT, anchor="e").grid(row=0, column=2, sticky="e")

    # ------------------------------------------------------------------
    # Screen container + legend
    # ------------------------------------------------------------------
    app.screen_container = tk.Frame(root, bg=theme.BG_DEEP)
    app.screen_container.grid(row=1, column=0, sticky="nsew")

    app.legend = LegendBar(root)
    app.legend.grid(row=2, column=0, sticky="ew")
    app.legend.set_hints([])
