"""Window shell: command strip, screen container, and footer legend bar.

Uses the native Windows title bar for drag/minimize/maximize/close —
ClipToolbox no longer draws its own header (see cliptoolbox.ui.chrome for
why the custom-titlebar drag/maximize handling was dropped).

The command strip (B2) is the one persistent action bar across the empty
state and the editor: LOAD · EXPORT · CANCEL | filename + ✕ | status ·
SETTINGS. The old landing menu's QUIT collapsed into the native titlebar
and the palette."""
import time
import tkinter as tk

from cliptoolbox.constants import APP_NAME
from cliptoolbox.ui import theme
from cliptoolbox.ui.theme import px
from cliptoolbox.ui.widgets import HaloButton, LegendBar, Tooltip

UI_VERSION = "2.0"


def build(app):
    root = app.root

    root.columnconfigure(0, weight=1)
    root.rowconfigure(1, weight=1)

    # Set by app.py when a clip loads (and reset by reset_clip_state);
    # rendered as the command strip's middle cluster below.
    app.file_label_var = tk.StringVar(value="No video loaded")

    # The version/build line is still written by startup_checks, but it
    # renders on the empty-state hero now — the strip hosts actions instead.
    app.build_line_var = tk.StringVar(
        value=f"{APP_NAME} v{UI_VERSION} — Build {time.strftime('%b %d %Y')}  |  ffmpeg: ok")

    # ------------------------------------------------------------------
    # Command strip
    # ------------------------------------------------------------------
    strip = tk.Frame(root, bg=theme.BG_DEEP)
    strip.grid(row=0, column=0, sticky="ew", padx=px(14), pady=(px(6), px(2)))
    strip.columnconfigure(1, weight=1)

    actions = tk.Frame(strip, bg=theme.BG_DEEP)
    actions.grid(row=0, column=0, sticky="w")

    app.load_button = HaloButton(
        actions, text="LOAD CLIP", command=app.load_video_dialog,
        height=px(theme.BTN_H),
    )
    app.load_button.pack(side=tk.LEFT)

    app.export_button = HaloButton(
        actions, text="EXPORT CLIP", variant="primary",
        command=app.export_video_dialog, width=px(170), height=px(theme.BTN_H),
    )
    app.export_button.pack(side=tk.LEFT, padx=(px(8), 0))

    app.stop_export_button = HaloButton(
        actions, text="CANCEL EXPORT", variant="danger",
        command=app.cancel_export, height=px(theme.BTN_H),
    )
    # Packed by update_export_actions() only while an export runs.

    # Middle cluster: the loaded clip's name, middle-ellipsized like the
    # status line so long names never crowd their neighbours, + the ✕ chip.
    file_cluster = tk.Frame(strip, bg=theme.BG_DEEP)
    file_cluster.grid(row=0, column=1)  # no sticky: stays centered

    file_display = tk.StringVar()

    def sync_file_label(*_):
        text = app.file_label_var.get()
        if len(text) > 48:
            text = text[:22] + " … " + text[-22:]
        file_display.set(text)

    app.file_label_var.trace_add("write", sync_file_label)
    sync_file_label()
    tk.Label(file_cluster, textvariable=file_display, font=theme.font_mono(),
             bg=theme.BG_DEEP, fg=theme.TEXT_DIM).pack(side=tk.LEFT)

    app.close_clip_button = HaloButton(
        file_cluster, text="✕", command=app.close_clip,
        width=px(26), height=px(24), font=theme.font_small(12),
    )
    Tooltip(app.close_clip_button, "Close clip (Ctrl+W)")
    # Packed by update_file_strip() only while a clip is loaded.

    # Right cluster: live status + SETTINGS. Long status lines (export
    # paths) get middle-ellipsized so they never spill over the buttons.
    tail = tk.Frame(strip, bg=theme.BG_DEEP)
    tail.grid(row=0, column=2, sticky="e")

    app.status_var = tk.StringVar(value="Ready")
    status_display = tk.StringVar(value="Ready")

    def sync_status(*_):
        text = app.status_var.get()
        if len(text) > 64:
            text = text[:30] + " … " + text[-30:]
        status_display.set(text)

    app.status_var.trace_add("write", sync_status)
    tk.Label(tail, textvariable=status_display, font=theme.font_mono(),
             bg=theme.BG_DEEP, fg=theme.TEXT, anchor="e").pack(
        side=tk.LEFT, padx=(0, px(10)))

    app.settings_button = HaloButton(
        tail, text="SETTINGS", command=app.open_settings,
        height=px(theme.BTN_H),
    )
    app.settings_button.pack(side=tk.LEFT)

    # ------------------------------------------------------------------
    # Screen container + legend
    # ------------------------------------------------------------------
    app.screen_container = tk.Frame(root, bg=theme.BG_DEEP)
    app.screen_container.grid(row=1, column=0, sticky="nsew")

    app.legend = LegendBar(root)
    app.legend.grid(row=2, column=0, sticky="ew")
    app.legend.set_hints([])
