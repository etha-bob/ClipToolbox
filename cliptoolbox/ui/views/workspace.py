"""The workspace screen — ClipToolbox's take on the Halo 2 pregame lobby.

Left column: action buttons (START GAME position), preview bezel, timeline,
transport/trim controls, and the pinned EXPORT row. Right column: the
audio-track roster (styled like the lobby player list) and the activity log
(the lobby chat box position). Export options live in the drawer (B4).

This module only builds widgets and assigns them onto the app object under
the attribute names the ported state machine expects.
"""
import tkinter as tk

from cliptoolbox.constants import PREVIEW_HEIGHT
from cliptoolbox.ui import theme
from cliptoolbox.ui.cropbox import CropBoxCanvas
from cliptoolbox.ui.seekbar import HaloSeekbar
from cliptoolbox.ui.theme import px
from cliptoolbox.ui.widgets import (
    HaloButton,
    HaloCheckbox,
    HaloEntry,
    HaloPanel,
    HaloScrollbar,
    Tooltip,
    make_log,
)

PLACEHOLDER_DEFAULT = "Load a video, choose tracks, then click Preview."


def build(app):
    # Screens stack in the container; show_empty_state/show_editor lift them.
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

    # Focus/HUD mode (B5) collapses the chrome around the preview and needs
    # handles on the containers it hides/regrows.
    app.workspace_grid = frame
    app.workspace_left = left
    app.workspace_right = right

    # ------------------------------------------------------------------
    # Left: EXPORT — the terminal action, pinned to the bottom of the
    # column right under the compression settings it depends on. Packed
    # FIRST: pack gives earlier slaves their space first, so when the
    # column overflows a short window the middle content clips instead
    # of the export button silently vanishing.
    # ------------------------------------------------------------------
    export_row = tk.Frame(left, bg=theme.BG_DEEP)
    export_row.pack(side=tk.BOTTOM, fill=tk.X, pady=(px(12), 0))
    app.export_row = export_row  # hidden in focus mode

    app.export_button = HaloButton(
        export_row, text="EXPORT CLIP", variant="primary",
        command=app.toggle_export_drawer, width=px(200),
    )
    app.export_button.pack(side=tk.LEFT)
    Tooltip(app.export_button, "Open the export drawer (Ctrl+E)")

    app.stop_export_button = HaloButton(
        export_row, text="CANCEL EXPORT", variant="danger",
        command=app.cancel_export, height=px(theme.BTN_PRIMARY_H),
    )
    # Packed beside EXPORT by update_export_actions() only while exporting.

    # ------------------------------------------------------------------
    # Left: preview bezel with the real embed target frame
    # (LOAD/EXPORT/CANCEL live in the shell's command strip since B2.)
    # ------------------------------------------------------------------
    bezel = HaloPanel(left, fill=theme.WELL_FILL, border=theme.PANEL_BORDER, pad=px(8))
    bezel.pack(fill=tk.X)
    app.preview_bezel = bezel  # regrown to fill the column in focus mode

    app.preview_frame = tk.Frame(
        bezel.body, bg="black", height=px(PREVIEW_HEIGHT),
    )
    app.preview_frame.pack(fill=tk.X, expand=False)
    app.preview_frame.pack_propagate(False)

    # mpv render host: the mpv engine parents its --wid video window into this
    # frame's HWND. Created first (lowest sibling) so the placeholder, paused
    # still, and crop editor all stack above it; inert when ffplay is active.
    app.mpv_host_frame = tk.Frame(app.preview_frame, bg="black")
    app.mpv_host_frame.place(x=0, y=0, relwidth=1.0, relheight=1.0)

    app.preview_placeholder_var = tk.StringVar(value=PLACEHOLDER_DEFAULT)
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

    # Crop/zoom editing surface: covers the preview frame while crop-edit mode
    # is active (the controller places/forgets it).
    app.cropbox = CropBoxCanvas(app.preview_frame, behind="black")
    app.cropbox.place_forget()

    app.preview_frame.bind("<Configure>", app.on_preview_frame_resize)

    # ------------------------------------------------------------------
    # Left: timeline
    # ------------------------------------------------------------------
    timeline = tk.Frame(left, bg=theme.BG_DEEP)
    timeline.pack(fill=tk.X, pady=(px(4), 0))
    app.timeline_row = timeline  # the re-pack anchor when focus mode exits

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
    app.seekbar.bind_trim_change(app.on_trim_bracket_drag)
    app.seekbar.bind_trim_commit(app.on_trim_bracket_commit)
    app.seekbar.bind_keyframe_click(app.on_keyframe_click)
    app.seekbar.bind_keyframe_drag(app.on_keyframe_drag)
    app.seekbar.bind_keyframe_commit(app.on_keyframe_commit)
    app.seekbar.bind_keyframe_delete(app.on_keyframe_delete)

    time_right_label = tk.Label(
        timeline, textvariable=app.time_right_var, font=theme.font_small(),
        bg=theme.BG_DEEP, fg=theme.TEXT, width=7, anchor="e", cursor="hand2",
    )
    time_right_label.pack(side=tk.RIGHT)
    # Click to toggle total duration <-> remaining (count-down).
    time_right_label.bind("<Button-1>", app.toggle_time_display)

    # ------------------------------------------------------------------
    # Left: transport + trim
    # ------------------------------------------------------------------
    transport = tk.Frame(left, bg=theme.BG_DEEP)
    transport.pack(fill=tk.X, pady=(px(4), 0))
    app.transport_frame = transport  # crop toolbar re-packs after this row

    app.preview_button = HaloButton(
        transport, text="PLAY", command=app.toggle_preview, width=px(110),
    )
    app.preview_button.config(state=tk.DISABLED)
    app.preview_button.pack(side=tk.LEFT)

    app.loop_checkbox = HaloCheckbox(
        transport, text="LOOP", variable=app.loop_enabled_var,
        command=app.on_loop_toggle, behind=theme.BG_DEEP,
        font=theme.font_title(13),
    )
    app.loop_checkbox.pack(side=tk.LEFT, padx=(px(12), 0))

    app.trim_checkbox = HaloCheckbox(
        transport, text="TRIM", variable=app.trim_enabled_var,
        command=app.on_trim_toggle, behind=theme.BG_DEEP,
        font=theme.font_title(13),
    )
    app.trim_checkbox.pack(side=tk.LEFT, padx=(px(16), 0))

    app.crop_checkbox = HaloCheckbox(
        transport, text="CROP", variable=app.crop_enabled_var,
        command=app.on_crop_toggle, behind=theme.BG_DEEP,
        font=theme.font_title(13),
    )
    app.crop_checkbox.pack(side=tk.LEFT, padx=(px(16), 0))
    Tooltip(app.crop_checkbox, "Crop / zoom with keyframes (re-encodes on export)")

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

    # Inline editable in/out timecodes (type exact boundaries).
    app.trim_in_var = tk.StringVar(value="")
    app.trim_out_var = tk.StringVar(value="")
    tk.Label(app.trim_buttons_frame, text="IN", font=theme.font_small(11),
             bg=theme.BG_DEEP, fg=theme.TEXT_DIM).pack(side=tk.LEFT, padx=(px(10), px(2)))
    app.trim_in_entry = HaloEntry(app.trim_buttons_frame, textvariable=app.trim_in_var, width=7)
    app.trim_in_entry.pack(side=tk.LEFT)
    tk.Label(app.trim_buttons_frame, text="OUT", font=theme.font_small(11),
             bg=theme.BG_DEEP, fg=theme.TEXT_DIM).pack(side=tk.LEFT, padx=(px(6), px(2)))
    app.trim_out_entry = HaloEntry(app.trim_buttons_frame, textvariable=app.trim_out_var, width=7)
    app.trim_out_entry.pack(side=tk.LEFT)

    trim_vcmd = (app.root.register(app.validate_timecode_key), "%P")
    for entry, kind in ((app.trim_in_entry, "start"), (app.trim_out_entry, "end")):
        entry.entry.configure(validate="key", validatecommand=trim_vcmd)
        entry.entry.bind("<Return>", lambda e, k=kind: app.commit_trim_entry(k, unfocus=True))
        # add="+" so this doesn't clobber HaloEntry's own FocusOut handler
        # (which resets the entry's highlight background).
        entry.entry.bind("<FocusOut>", lambda e, k=kind: app.commit_trim_entry(k), add="+")

    app.clear_trim_button = HaloButton(
        app.trim_buttons_frame, text="CLEAR", command=app.clear_trim_points_action,
        variant="danger", height=px(28), font=theme.font_small(12),
    )
    app.clear_trim_button.pack(side=tk.LEFT, padx=(px(8), 0))

    # Compact trimmed-length readout (endpoints live in the IN/OUT fields).
    # Fixed width for the same reason as the crop readout: it updates live
    # during trim-bracket drags and must not re-measure the left column.
    app.trim_info_var = tk.StringVar(value="")
    tk.Label(app.trim_buttons_frame, textvariable=app.trim_info_var, font=theme.font_small(),
             bg=theme.BG_DEEP, fg=theme.ACCENT, width=10, anchor="w").pack(side=tk.LEFT, padx=(px(8), 0))

    app.trim_buttons_frame.pack_forget()

    # ------------------------------------------------------------------
    # Left: crop / keyframe toolbar (shown while CROP is enabled)
    # ------------------------------------------------------------------
    app.crop_toolbar_frame = tk.Frame(left, bg=theme.BG_DEEP)
    app.crop_toolbar_frame.pack(fill=tk.X, pady=(px(4), 0))

    # Working ⇄ preview toggle. Fixed width so the label swap doesn't resize it.
    app.crop_preview_button = HaloButton(
        app.crop_toolbar_frame, text="PREVIEW  ▶", command=app.on_crop_preview_toggle,
        variant="primary", width=px(128), height=px(28), font=theme.font_small(12),
    )
    app.crop_preview_button.pack(side=tk.LEFT, padx=(0, px(10)))
    Tooltip(app.crop_preview_button,
            "Switch between working mode (edit the crop box) and preview mode "
            "(play it back). Space also toggles this while cropping.")

    app.crop_addkey_button = HaloButton(
        app.crop_toolbar_frame, text="ADD KEY", command=app.on_crop_add_key,
        height=px(28), font=theme.font_small(12),
    )
    app.crop_addkey_button.pack(side=tk.LEFT)
    Tooltip(app.crop_addkey_button, "Set a crop keyframe at the playhead (K)")

    app.crop_delkey_button = HaloButton(
        app.crop_toolbar_frame, text="DELETE", command=app.on_crop_delete_key,
        height=px(28), font=theme.font_small(12),
    )
    app.crop_delkey_button.pack(side=tk.LEFT, padx=(px(6), 0))
    Tooltip(app.crop_delkey_button, "Delete the keyframe at the playhead")

    app.crop_prevkey_button = HaloButton(
        app.crop_toolbar_frame, text="◂ KEY", command=app.on_crop_prev_key,
        height=px(28), font=theme.font_small(12),
    )
    app.crop_prevkey_button.pack(side=tk.LEFT, padx=(px(6), 0))

    app.crop_nextkey_button = HaloButton(
        app.crop_toolbar_frame, text="KEY ▸", command=app.on_crop_next_key,
        height=px(28), font=theme.font_small(12),
    )
    app.crop_nextkey_button.pack(side=tk.LEFT, padx=(px(6), 0))

    app.crop_reset_button = HaloButton(
        app.crop_toolbar_frame, text="RESET", command=app.on_crop_reset_rect,
        height=px(28), font=theme.font_small(12),
    )
    app.crop_reset_button.pack(side=tk.LEFT, padx=(px(6), 0))
    Tooltip(app.crop_reset_button, "Reset the crop rectangle to the full frame")

    app.crop_clear_button = HaloButton(
        app.crop_toolbar_frame, text="CLEAR", command=app.on_crop_clear_keys,
        variant="danger", height=px(28), font=theme.font_small(12),
    )
    app.crop_clear_button.pack(side=tk.LEFT, padx=(px(8), 0))
    Tooltip(app.crop_clear_button, "Remove all crop keyframes")

    app.crop_info_var = tk.StringVar(value="")
    # Fixed width: this text changes on every crop-drag motion event, and a
    # variable-width label would re-measure the left grid column, resizing the
    # preview (and the crop editor's letterbox transform) mid-drag.
    tk.Label(app.crop_toolbar_frame, textvariable=app.crop_info_var, font=theme.font_small(),
             bg=theme.BG_DEEP, fg=theme.ACCENT, width=42, anchor="w").pack(side=tk.LEFT, padx=(px(8), 0))

    app.crop_toolbar_frame.pack_forget()

    # ------------------------------------------------------------------
    # Left: frame snapshot actions
    # ------------------------------------------------------------------
    frame_row = tk.Frame(left, bg=theme.BG_DEEP)
    frame_row.pack(fill=tk.X, pady=(px(4), 0))
    app.frame_row = frame_row  # hidden in focus mode

    tk.Label(frame_row, text="FRAME", font=theme.font_title(12),
             bg=theme.BG_DEEP, fg=theme.TEXT_DIM).pack(side=tk.LEFT, padx=(0, px(8)))

    app.frame_save_button = HaloButton(
        frame_row, text="SAVE", command=lambda: app.snapshot_frame("save"),
        height=px(26), font=theme.font_small(12),
    )
    app.frame_save_button.pack(side=tk.LEFT)

    app.frame_saveas_button = HaloButton(
        frame_row, text="SAVE AS…", command=lambda: app.snapshot_frame("saveas"),
        height=px(26), font=theme.font_small(12),
    )
    app.frame_saveas_button.pack(side=tk.LEFT, padx=(px(6), 0))

    app.frame_copy_button = HaloButton(
        frame_row, text="COPY", command=lambda: app.snapshot_frame("copy"),
        height=px(26), font=theme.font_small(12),
    )
    app.frame_copy_button.pack(side=tk.LEFT, padx=(px(6), 0))

    # (The compression + timestamp-watermark cards moved into the export
    # drawer with B4 — they're export-only options, and the move frees
    # left-column height, the M5 pressure point.)

    # ------------------------------------------------------------------
    # Right: audio-track roster (lobby player list)
    # ------------------------------------------------------------------
    roster = HaloPanel(right)
    roster.grid(row=0, column=0, sticky="new")

    roster_header = tk.Frame(roster.body, bg=theme.PANEL_FILL)
    roster_header.pack(fill=tk.X, pady=(0, px(6)))

    app.roster_title_var = tk.StringVar(value="0 TRACK(S) IN MIX")
    tk.Label(roster_header, textvariable=app.roster_title_var, font=theme.font_title(13),
             bg=theme.PANEL_FILL, fg=theme.ACCENT, anchor="w").pack(side=tk.LEFT)

    app.reset_volumes_button = HaloButton(
        roster_header, text="RESET", command=app.reset_all_volumes,
        behind=theme.PANEL_FILL, height=px(24), font=theme.font_small(11),
    )
    app.reset_volumes_button.pack(side=tk.RIGHT)

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

    # ------------------------------------------------------------------
    # Hover tooltips on the less-obvious controls
    # ------------------------------------------------------------------
    for widget, tip in (
        (app.loop_checkbox, "Loop the trim region (or whole clip) during preview"),
        (app.trim_checkbox, "Enable trimming — set an in and out point"),
        (app.trim_start_button, "Set trim start to the playhead ( [ )"),
        (app.trim_end_button, "Set trim end to the playhead ( ] )"),
        (app.trim_in_entry, "Type an exact in point (m:ss.cs)"),
        (app.trim_out_entry, "Type an exact out point (m:ss.cs)"),
        (app.clear_trim_button, "Clear both trim points"),
        (app.frame_save_button, "Save the current frame as a PNG in outputs/"),
        (app.frame_saveas_button, "Save the current frame to a chosen location"),
        (app.frame_copy_button, "Copy the current frame to the clipboard"),
        (app.reset_volumes_button, "Reset every track to 100% and clear mute/solo"),
    ):
        Tooltip(widget, tip)
