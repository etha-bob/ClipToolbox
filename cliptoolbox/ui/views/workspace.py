"""The workspace screen — ClipToolbox's take on the Halo 2 pregame lobby.

Left column: action buttons (START GAME position), preview bezel, timeline,
transport/trim controls, and the compression quick-options card. Right
column: the audio-track roster (styled like the lobby player list) and the
activity log (the lobby chat box position).

This module only builds widgets and assigns them onto the app object under
the attribute names the ported state machine expects.
"""
import tkinter as tk

from cliptoolbox.constants import COMPRESSION_RESOLUTION_PRESETS, PREVIEW_HEIGHT
from cliptoolbox.ui import theme
from cliptoolbox.ui.seekbar import HaloSeekbar
from cliptoolbox.ui.theme import px
from cliptoolbox.ui.widgets import (
    HaloButton,
    HaloCheckbox,
    HaloEntry,
    HaloPanel,
    HaloScrollbar,
    HaloSegmented,
    make_log,
)

PREVIEW_BEZEL_FILL = "#0A1626"


def build(app):
    # Screens stack in the container; show_landing/show_workspace lift them.
    app.workspace_frame = tk.Frame(app.screen_container, bg=theme.BG_DEEP)
    app.workspace_frame.place(x=0, y=0, relwidth=1.0, relheight=1.0)

    frame = tk.Frame(app.workspace_frame, bg=theme.BG_DEEP)
    frame.pack(fill=tk.BOTH, expand=True, padx=px(14), pady=px(8))

    frame.columnconfigure(0, weight=3)
    frame.columnconfigure(1, weight=2, minsize=px(360))
    frame.rowconfigure(0, weight=1)

    left = tk.Frame(frame, bg=theme.BG_DEEP)
    left.grid(row=0, column=0, sticky="nsew", padx=(0, px(12)))
    right = tk.Frame(frame, bg=theme.BG_DEEP)
    right.grid(row=0, column=1, sticky="nsew")
    right.columnconfigure(0, weight=1)
    right.rowconfigure(1, weight=1)

    # ------------------------------------------------------------------
    # Left: actions (START GAME homage)
    # ------------------------------------------------------------------
    actions = tk.Frame(left, bg=theme.BG_DEEP)
    actions.pack(fill=tk.X, pady=(0, px(8)))

    app.export_button = HaloButton(
        actions, text="EXPORT CLIP", variant="primary",
        command=app.export_video_dialog, width=px(190),
    )
    app.export_button.pack(side=tk.LEFT)

    app.stop_export_button = HaloButton(
        actions, text="CANCEL EXPORT", variant="danger",
        command=app.cancel_export, height=px(theme.BTN_PRIMARY_H),
    )
    # Packed by update_export_actions() only while an export runs.

    app.back_button = HaloButton(
        actions, text="◂ MENU", command=app.show_landing,
    )
    app.back_button.pack(side=tk.RIGHT)

    app.load_button = HaloButton(
        actions, text="LOAD CLIP", command=app.load_video_dialog,
    )
    app.load_button.pack(side=tk.RIGHT, padx=(0, px(8)))

    # ------------------------------------------------------------------
    # Left: preview bezel with the real embed target frame
    # ------------------------------------------------------------------
    bezel = HaloPanel(left, fill=PREVIEW_BEZEL_FILL, border=theme.PANEL_BORDER, pad=px(8))
    bezel.pack(fill=tk.X)

    app.preview_frame = tk.Frame(
        bezel.body, bg="black", height=px(PREVIEW_HEIGHT),
    )
    app.preview_frame.pack(fill=tk.X, expand=False)
    app.preview_frame.pack_propagate(False)

    app.preview_placeholder_var = tk.StringVar(
        value="Load a video, choose tracks, then click Preview."
    )
    app.preview_placeholder = tk.Label(
        app.preview_frame,
        textvariable=app.preview_placeholder_var,
        fg=theme.TEXT,
        bg="black",
        font=theme.font_body(),
        borderwidth=0,
        highlightthickness=0,
    )
    app.preview_placeholder.place(relx=0.5, rely=0.5, anchor="center")

    app.paused_frame_label = tk.Label(
        app.preview_frame,
        bg="black",
        borderwidth=0,
        highlightthickness=0,
    )
    app.paused_frame_label.place_forget()

    app.preview_frame.bind("<Configure>", app.on_preview_frame_resize)

    # ------------------------------------------------------------------
    # Left: timeline
    # ------------------------------------------------------------------
    timeline = tk.Frame(left, bg=theme.BG_DEEP)
    timeline.pack(fill=tk.X, pady=(px(6), 0))

    app.time_left_var = tk.StringVar(value="0:00")
    app.time_right_var = tk.StringVar(value="0:00")

    tk.Label(timeline, textvariable=app.time_left_var, font=theme.font_small(),
             bg=theme.BG_DEEP, fg=theme.TEXT, width=7, anchor="w").pack(side=tk.LEFT)

    app.seek_var = tk.DoubleVar(value=0)
    app.seekbar = HaloSeekbar(
        timeline, from_=0, to=100, variable=app.seek_var,
        command=app.on_seek_drag, behind=theme.BG_DEEP,
    )
    app.seekbar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=px(6))
    app.seekbar.bind_press(app.on_seek_press)
    app.seekbar.bind_release(app.on_seek_release)

    tk.Label(timeline, textvariable=app.time_right_var, font=theme.font_small(),
             bg=theme.BG_DEEP, fg=theme.TEXT, width=7, anchor="e").pack(side=tk.RIGHT)

    # ------------------------------------------------------------------
    # Left: transport + trim
    # ------------------------------------------------------------------
    transport = tk.Frame(left, bg=theme.BG_DEEP)
    transport.pack(fill=tk.X, pady=(px(4), 0))

    app.preview_button = HaloButton(
        transport, text="PLAY", command=app.toggle_preview, width=px(110),
    )
    app.preview_button.config(state=tk.DISABLED)
    app.preview_button.pack(side=tk.LEFT)

    app.trim_checkbox = HaloCheckbox(
        transport, text="TRIM", variable=app.trim_enabled_var,
        command=app.on_trim_toggle, behind=theme.BG_DEEP,
        font=theme.font_title(13),
    )
    app.trim_checkbox.pack(side=tk.LEFT, padx=(px(16), 0))

    app.trim_buttons_frame = tk.Frame(transport, bg=theme.BG_DEEP)
    app.trim_buttons_frame.pack(side=tk.LEFT, padx=(px(10), 0))

    app.trim_start_button = HaloButton(
        app.trim_buttons_frame, text="SET START  [", command=app.set_trim_start,
        height=px(28), font=theme.font_small(12),
    )
    app.trim_start_button.pack(side=tk.LEFT)

    app.trim_end_button = HaloButton(
        app.trim_buttons_frame, text="]  SET END", command=app.set_trim_end,
        height=px(28), font=theme.font_small(12),
    )
    app.trim_end_button.pack(side=tk.LEFT, padx=(px(6), 0))

    app.clear_trim_button = HaloButton(
        app.trim_buttons_frame, text="CLEAR", command=app.clear_trim_points,
        variant="danger", height=px(28), font=theme.font_small(12),
    )
    app.clear_trim_button.pack(side=tk.LEFT, padx=(px(6), 0))

    app.trim_info_var = tk.StringVar(value="")
    tk.Label(transport, textvariable=app.trim_info_var, font=theme.font_small(),
             bg=theme.BG_DEEP, fg=theme.ACCENT).pack(side=tk.LEFT, padx=(px(10), 0))

    app.trim_buttons_frame.pack_forget()

    # ------------------------------------------------------------------
    # Left: compression quick-options card
    # ------------------------------------------------------------------
    card = HaloPanel(left, title="Compression")
    card.pack(fill=tk.X, pady=(px(10), 0))

    comp_row = tk.Frame(card.body, bg=theme.PANEL_FILL)
    comp_row.pack(fill=tk.X)

    app.compress_checkbox = HaloCheckbox(
        comp_row, text="COMPRESS TO TARGET SIZE", variable=app.compress_enabled_var,
        command=app.on_compression_toggle, behind=theme.PANEL_FILL,
        font=theme.font_body(13),
    )
    app.compress_checkbox.pack(side=tk.LEFT)

    app.compression_options_frame = tk.Frame(comp_row, bg=theme.PANEL_FILL)
    app.compression_options_frame.pack(side=tk.LEFT, padx=(px(10), 0))

    tk.Label(app.compression_options_frame, text="Target:", font=theme.font_small(),
             bg=theme.PANEL_FILL, fg=theme.TEXT).pack(side=tk.LEFT)
    app.compression_target_entry = HaloEntry(
        app.compression_options_frame, textvariable=app.compression_target_var, width=6,
    )
    app.compression_target_entry.pack(side=tk.LEFT, padx=(px(6), px(4)))
    tk.Label(app.compression_options_frame, text="MB", font=theme.font_small(),
             bg=theme.PANEL_FILL, fg=theme.TEXT_DIM).pack(side=tk.LEFT)

    tk.Label(app.compression_options_frame, text="Max res:", font=theme.font_small(),
             bg=theme.PANEL_FILL, fg=theme.TEXT).pack(side=tk.LEFT, padx=(px(14), px(4)))
    app.compression_resolution_combo = HaloSegmented(
        app.compression_options_frame,
        list(COMPRESSION_RESOLUTION_PRESETS.keys()),
        app.compression_resolution_var,
        command=app.on_compression_resolution_changed,
    )
    app.compression_resolution_combo.pack(side=tk.LEFT)

    app.compression_options_frame.pack_forget()

    app.compression_estimate_var = tk.StringVar(value="")
    tk.Label(card.body, textvariable=app.compression_estimate_var, font=theme.font_small(),
             bg=theme.PANEL_FILL, fg=theme.TEXT_DIM, anchor="w").pack(fill=tk.X, pady=(px(6), 0))

    app.compression_target_var.trace_add("write", lambda *a: app.update_compression_estimate())

    # ------------------------------------------------------------------
    # Right: audio-track roster (lobby player list)
    # ------------------------------------------------------------------
    roster = HaloPanel(right)
    roster.grid(row=0, column=0, sticky="new")

    app.roster_title_var = tk.StringVar(value="0 TRACK(S) IN MIX")
    tk.Label(roster.body, textvariable=app.roster_title_var, font=theme.font_title(13),
             bg=theme.PANEL_FILL, fg=theme.ACCENT, anchor="w").pack(fill=tk.X, pady=(0, px(6)))

    roster_grid = tk.Frame(roster.body, bg=theme.PANEL_FILL)
    roster_grid.pack(fill=tk.BOTH, expand=True)
    roster_grid.columnconfigure(0, weight=1)

    app.track_canvas = tk.Canvas(roster_grid, highlightthickness=0, bd=0,
                                 bg=theme.PANEL_FILL, height=px(62))
    app.track_scrollbar = HaloScrollbar(roster_grid, command=app.track_canvas.yview,
                                        behind=theme.PANEL_FILL)
    app.track_frame = tk.Frame(app.track_canvas, bg=theme.PANEL_FILL)
    app.track_frame.columnconfigure(0, weight=1)

    app.track_window = app.track_canvas.create_window(
        (0, 0), window=app.track_frame, anchor="nw",
    )

    def _sync_track_scrollregion(event=None):
        app.track_canvas.configure(scrollregion=app.track_canvas.bbox("all"))
        app.track_canvas.itemconfigure(
            app.track_window,
            width=max(1, app.track_canvas.winfo_width()),
        )

    app.track_frame.bind("<Configure>", _sync_track_scrollregion)

    app.track_canvas.bind(
        "<Configure>",
        lambda event: app.track_canvas.itemconfigure(app.track_window, width=event.width),
    )

    app.track_canvas.configure(yscrollcommand=app.track_scrollbar.set)

    app.track_canvas.grid(row=0, column=0, sticky="ew")
    app.track_scrollbar.grid(row=0, column=1, sticky="ns", padx=(px(2), 0))
    app.track_scrollbar.grid_remove()

    # ------------------------------------------------------------------
    # Right: activity log (lobby chat box)
    # ------------------------------------------------------------------
    log_panel = HaloPanel(right, title="Activity log")
    log_panel.grid(row=1, column=0, sticky="nsew", pady=(px(10), 0))

    log_frame, app.log_text = make_log(log_panel.body)
    log_frame.pack(fill=tk.BOTH, expand=True)

    # Misc compatibility vars.
    app.dnd_hint_var = tk.StringVar(value="")
