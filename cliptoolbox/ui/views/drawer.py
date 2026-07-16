"""Right-side export drawer (roadmap B4).

The one export surface: destination + name pattern (with a live resolved
filename preview), the compression / watermark options (moved here from the
left column), START EXPORT + SAVE AS…, and the persistent job history.

Non-modal: it slides in over the editor's right column inside
``screen_container`` and playback keeps running. The EXPORT CLIP button,
Ctrl+E, and the palette toggle it; Esc closes it (unless an export is
running — Esc keeps meaning CANCEL EXPORT then).

Like the other views this module only builds widgets and assigns them onto
the app object under the attribute names the state machine expects — the
compression/watermark widgets keep their historical names, so ``set_busy``
and settings persistence are untouched by the move.
"""
import time
import tkinter as tk
from pathlib import Path

from cliptoolbox.constants import COMPRESSION_RESOLUTION_PRESETS, WINDOWS_MB_BYTES
from cliptoolbox.core import jobs as core_jobs
from cliptoolbox.ui import theme
from cliptoolbox.ui.theme import px
from cliptoolbox.ui.widgets import (
    HaloButton,
    HaloCheckbox,
    HaloEntry,
    HaloScrollbar,
    HaloSegmented,
    Tooltip,
)

DRAWER_W = 440  # logical px
_SLIDE_STEPS = 6

TOKEN_HINT = "{clip} {trim} {crop} {stamp} {size} {res} {date} {time}"


def _ellipsize_middle(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    half = (limit - 3) // 2
    return text[:half] + " … " + text[-half:]


_RAIL_COLORS = {
    core_jobs.RUNNING: theme.ACCENT,
    core_jobs.DONE: theme.OK_GREEN,
    core_jobs.FAILED: theme.ERR_RED,
    core_jobs.CANCELLED: theme.TEXT_DIM,
}


class JobRow(tk.Frame):
    """One export in the drawer's history: status rail, filename, honest
    per-attempt progress while running, size when done, and actions."""

    def __init__(self, parent, app, job):
        super().__init__(parent, bg=theme.PANEL_FILL_HI, highlightthickness=1,
                         highlightbackground=theme.PANEL_BORDER_DIM)
        self.app = app
        self.job_id = job.job_id
        self._percent = 0

        self.rail = tk.Frame(self, width=px(4), bg=theme.TEXT_DIM)
        self.rail.pack(side=tk.LEFT, fill=tk.Y)

        content = tk.Frame(self, bg=theme.PANEL_FILL_HI)
        content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True,
                     padx=px(8), pady=px(6))

        line1 = tk.Frame(content, bg=theme.PANEL_FILL_HI)
        line1.pack(fill=tk.X)
        self.stat_label = tk.Label(line1, text="", font=theme.font_title(11),
                                   bg=theme.PANEL_FILL_HI, fg=theme.TEXT_DIM)
        self.stat_label.pack(side=tk.RIGHT, padx=(px(8), 0))
        self.name_label = tk.Label(line1, text="", font=theme.font_small(),
                                   bg=theme.PANEL_FILL_HI, fg=theme.TEXT_BRIGHT,
                                   anchor="w")
        self.name_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Slim per-attempt progress bar; packed only while running.
        self.bar = tk.Canvas(content, height=px(5), bg=theme.WELL_FILL,
                             highlightthickness=0, bd=0)
        self.bar.bind("<Configure>", lambda e: self._draw_bar())

        self.meta_label = tk.Label(content, text="", font=theme.font_small(10),
                                   bg=theme.PANEL_FILL_HI, fg=theme.TEXT_DIM,
                                   anchor="w")
        self.meta_label.pack(fill=tk.X, pady=(px(2), 0))

        self.actions = tk.Frame(content, bg=theme.PANEL_FILL_HI)
        self.actions.pack(fill=tk.X, pady=(px(4), 0))

        def small_button(text, command, variant="secondary"):
            return HaloButton(self.actions, text=text, command=command,
                              variant=variant, behind=theme.PANEL_FILL_HI,
                              height=px(20), font=theme.font_small(10))

        self.open_button = small_button("OPEN", lambda: app.job_open(self.job_id))
        self.reveal_button = small_button("FOLDER", lambda: app.job_reveal(self.job_id))
        self.rerun_button = small_button("RE-RUN", lambda: app.job_rerun(self.job_id))
        self.cancel_button = small_button("CANCEL", app.cancel_export, variant="danger")

    def _draw_bar(self):
        self.bar.delete("all")
        width = self.bar.winfo_width()
        if width <= 2:
            return
        fill_w = round(width * max(0, min(100, self._percent)) / 100)
        if fill_w > 0:
            self.bar.create_rectangle(0, 0, fill_w, self.bar.winfo_height(),
                                      fill=theme.ACCENT, width=0)

    def _show_actions(self, buttons):
        for button in (self.open_button, self.reveal_button,
                       self.rerun_button, self.cancel_button):
            if button in buttons:
                if button.winfo_manager() == "":
                    button.pack(side=tk.LEFT, padx=(0, px(6)))
            elif button.winfo_manager() != "":
                button.pack_forget()

    def update(self, job):
        self._percent = job.percent
        self.rail.config(bg=_RAIL_COLORS.get(job.status, theme.TEXT_DIM))
        self.name_label.config(text=_ellipsize_middle(job.output_name, 34))

        when = time.strftime("%H:%M", time.localtime(job.finished_at or job.created_at))
        meta = f"{job.spec.clip_name} · {when}" if job.spec.clip_name else when

        if job.status == core_jobs.RUNNING:
            self.stat_label.config(
                text=f"ATTEMPT {job.attempt}/{job.attempts_max} · {job.percent}%",
                fg=theme.ACCENT)
            if self.bar.winfo_manager() == "":
                self.bar.pack(fill=tk.X, pady=(px(4), 0), before=self.meta_label)
            self._draw_bar()
            self._show_actions((self.cancel_button,))
        else:
            if self.bar.winfo_manager() != "":
                self.bar.pack_forget()
            if job.status == core_jobs.DONE:
                size = (f"{job.size_bytes / WINDOWS_MB_BYTES:.2f} MB"
                        if job.size_bytes else "DONE")
                self.stat_label.config(text=size, fg=theme.OK_GREEN)
            elif job.status == core_jobs.FAILED:
                self.stat_label.config(text="FAILED", fg=theme.ERR_RED)
                first_line = (job.error or "").strip().splitlines()
                if first_line:
                    meta = f"{meta} · {first_line[0][:60]}"
            else:
                self.stat_label.config(text="CANCELLED", fg=theme.TEXT_DIM)

            output_exists = Path(job.spec.output_path).exists()
            buttons = []
            if job.status == core_jobs.DONE and output_exists:
                buttons += [self.open_button, self.reveal_button]
            buttons.append(self.rerun_button)
            self._show_actions(tuple(buttons))
            rerun_ok = (not self.app.is_exporting
                        and Path(job.spec.input_path).exists())
            self.rerun_button.config(state=tk.NORMAL if rerun_ok else tk.DISABLED)

        self.meta_label.config(text=_ellipsize_middle(meta, 52))


class ExportDrawer:
    def __init__(self, app):
        self.app = app
        self.width = px(DRAWER_W)
        self.visible = False
        self._anim = None

        # 1px border on the exposed (left) edge via the outer frame's bg.
        self.frame = tk.Frame(app.screen_container, bg=theme.PANEL_BORDER)
        inner = tk.Frame(self.frame, bg=theme.PANEL_FILL)
        inner.pack(fill=tk.BOTH, expand=True, padx=(1, 0))

        # ---------------------------------------------------------- header
        strip = tk.Frame(inner, bg=theme.TITLE_FILL)
        strip.pack(fill=tk.X)
        tk.Frame(strip, bg=theme.ACCENT, width=px(4)).pack(side=tk.LEFT, fill=tk.Y)
        tk.Label(strip, text="EXPORT", font=theme.font_title(13),
                 bg=theme.TITLE_FILL, fg=theme.TITLE_TEXT).pack(
            side=tk.LEFT, padx=(px(10), 0), pady=px(6))
        close = tk.Label(strip, text="✕", font=theme.font_small(12),
                         bg=theme.TITLE_FILL, fg=theme.TEXT_DIM, cursor="hand2")
        close.pack(side=tk.RIGHT, padx=px(8))
        close.bind("<ButtonRelease-1>", lambda e: self.close())

        body = tk.Frame(inner, bg=theme.PANEL_FILL)
        body.pack(fill=tk.BOTH, expand=True, padx=px(12), pady=(px(4), px(10)))
        self.body = body

        # ---------------------------------------------------- destination
        self._section(body, "DESTINATION", first=True)

        dest_row = tk.Frame(body, bg=theme.PANEL_FILL)
        dest_row.pack(fill=tk.X)

        self.dest_label = tk.Label(dest_row, text="", font=theme.font_mono(),
                                   bg=theme.PANEL_FILL, fg=theme.TEXT, anchor="w")
        self.dest_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        app.export_browse_button = HaloButton(
            dest_row, text="BROWSE", command=app.browse_export_destination,
            behind=theme.PANEL_FILL, height=px(24), font=theme.font_small(11),
        )
        app.export_browse_button.pack(side=tk.RIGHT)

        app.export_dest_reset_button = HaloButton(
            dest_row, text="↺", command=app.reset_export_destination,
            behind=theme.PANEL_FILL, width=px(26), height=px(24),
            font=theme.font_small(11),
        )
        Tooltip(app.export_dest_reset_button, "Back to the default outputs folder")
        # Packed by refresh() only while a custom destination is set.

        # ------------------------------------------------------- filename
        self._section(body, "FILENAME")

        app.export_pattern_entry = HaloEntry(
            body, textvariable=app.export_name_pattern_var, justify="left",
        )
        app.export_pattern_entry.pack(fill=tk.X)
        Tooltip(app.export_pattern_entry,
                "Output name pattern. Conditional tokens vanish when their "
                "option is off, so one pattern covers every export.")

        self.name_preview = tk.Label(body, text="", font=theme.font_mono(),
                                     bg=theme.PANEL_FILL, fg=theme.ACCENT, anchor="w")
        self.name_preview.pack(fill=tk.X, pady=(px(4), 0))

        tk.Label(body, text=f"TOKENS  {TOKEN_HINT}", font=theme.font_small(10),
                 bg=theme.PANEL_FILL, fg=theme.TEXT_DIM, anchor="w").pack(fill=tk.X)

        # -------------------------------------------------------- options
        self._section(body, "OPTIONS")

        comp_row = tk.Frame(body, bg=theme.PANEL_FILL)
        comp_row.pack(fill=tk.X)
        app.compress_checkbox = HaloCheckbox(
            comp_row, text="COMPRESS TO TARGET SIZE", variable=app.compress_enabled_var,
            command=app.on_compression_toggle, behind=theme.PANEL_FILL,
            font=theme.font_body(13),
        )
        app.compress_checkbox.pack(side=tk.LEFT)

        # Indented option rows: on_compression_toggle packs the options frame
        # into this row (side=LEFT), exactly like it always has.
        comp_opts_row = tk.Frame(body, bg=theme.PANEL_FILL)
        comp_opts_row.pack(fill=tk.X, padx=(px(24), 0))

        app.compression_options_frame = tk.Frame(comp_opts_row, bg=theme.PANEL_FILL)

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

        app.compression_estimate_var = tk.StringVar(value="")
        tk.Label(body, textvariable=app.compression_estimate_var, font=theme.font_small(),
                 bg=theme.PANEL_FILL, fg=theme.TEXT_DIM, anchor="w").pack(
            fill=tk.X, pady=(px(4), 0))

        wm_row = tk.Frame(body, bg=theme.PANEL_FILL)
        wm_row.pack(fill=tk.X, pady=(px(6), 0))
        app.timestamp_watermark_checkbox = HaloCheckbox(
            wm_row, text="TIMESTAMP WATERMARK",
            variable=app.timestamp_watermark_enabled_var,
            command=app.on_timestamp_watermark_toggle, behind=theme.PANEL_FILL,
            font=theme.font_body(13),
        )
        app.timestamp_watermark_checkbox.pack(side=tk.LEFT)

        wm_opts_row = tk.Frame(body, bg=theme.PANEL_FILL)
        wm_opts_row.pack(fill=tk.X, padx=(px(24), 0))

        app.timestamp_watermark_options_frame = tk.Frame(wm_opts_row, bg=theme.PANEL_FILL)

        tk.Label(app.timestamp_watermark_options_frame, text="Fade out after:",
                 font=theme.font_small(), bg=theme.PANEL_FILL, fg=theme.TEXT).pack(side=tk.LEFT)
        app.timestamp_watermark_duration_entry = HaloEntry(
            app.timestamp_watermark_options_frame,
            textvariable=app.timestamp_watermark_duration_var, width=6,
        )
        app.timestamp_watermark_duration_entry.pack(side=tk.LEFT, padx=(px(6), px(4)))
        tk.Label(app.timestamp_watermark_options_frame, text="ms", font=theme.font_small(),
                 bg=theme.PANEL_FILL, fg=theme.TEXT_DIM).pack(side=tk.LEFT)

        # Per-export text override (M11): CONFIGURED (Settings' source),
        # CUSTOM (freetext below), or BOTH (stacked, configured on top).
        # Clip-scoped — app.reset_clip_state clears both back to CONFIGURED.
        wm_text_opts_row = tk.Frame(body, bg=theme.PANEL_FILL)
        wm_text_opts_row.pack(fill=tk.X, padx=(px(24), 0))

        app.watermark_text_options_frame = tk.Frame(wm_text_opts_row, bg=theme.PANEL_FILL)

        mode_row = tk.Frame(app.watermark_text_options_frame, bg=theme.PANEL_FILL)
        mode_row.pack(fill=tk.X, pady=(px(4), 0))
        tk.Label(mode_row, text="Text:", font=theme.font_small(),
                 bg=theme.PANEL_FILL, fg=theme.TEXT).pack(side=tk.LEFT)
        app.watermark_mode_seg = HaloSegmented(
            mode_row, ["CONFIGURED", "CUSTOM", "BOTH"], app.watermark_mode_var,
            command=app.on_watermark_mode_changed, behind=theme.PANEL_FILL,
        )
        app.watermark_mode_seg.pack(side=tk.LEFT, padx=(px(6), 0))

        app.watermark_custom_frame = tk.Frame(app.watermark_text_options_frame, bg=theme.PANEL_FILL)
        app.watermark_custom_entry = HaloEntry(
            app.watermark_custom_frame, textvariable=app.watermark_custom_text_var,
            justify="left",
        )
        app.watermark_custom_entry.pack(fill=tk.X)
        # Packed/forgotten by on_watermark_mode_changed (CUSTOM/BOTH only).

        for widget, tip in (
            (app.compression_target_entry, "Target size in MB (Windows/Discord MiB)"),
            (app.compression_resolution_combo, "Cap the compressed video resolution"),
            (app.timestamp_watermark_duration_entry,
             "How long the timestamp stays fully visible before fading (ms)"),
            (app.watermark_mode_seg,
             "CONFIGURED uses the Settings source; CUSTOM burns your own text for "
             "just this clip; BOTH stacks them, configured on top."),
            (app.watermark_custom_entry,
             "Custom watermark text for this clip only — not saved between clips."),
        ):
            Tooltip(widget, tip)

        # ------------------------------------------------------------- go
        go_row = tk.Frame(body, bg=theme.PANEL_FILL)
        go_row.pack(fill=tk.X, pady=(px(14), 0))

        app.export_go_button = HaloButton(
            go_row, text="START EXPORT", variant="primary",
            command=app.export_go, width=px(200), behind=theme.PANEL_FILL,
        )
        app.export_go_button.pack(side=tk.LEFT)

        app.export_saveas_button = HaloButton(
            go_row, text="SAVE AS…", command=app.export_save_as,
            behind=theme.PANEL_FILL, height=px(theme.BTN_PRIMARY_H),
        )
        app.export_saveas_button.pack(side=tk.LEFT, padx=(px(8), 0))
        Tooltip(app.export_saveas_button, "Pick the output file in a save dialog instead")

        # ---------------------------------------------------- job history
        self._section(body, "JOB HISTORY")

        jobs_grid = tk.Frame(body, bg=theme.PANEL_FILL)
        jobs_grid.pack(fill=tk.BOTH, expand=True)
        jobs_grid.columnconfigure(0, weight=1)
        jobs_grid.rowconfigure(0, weight=1)

        self.jobs_canvas = tk.Canvas(jobs_grid, highlightthickness=0, bd=0,
                                     bg=theme.PANEL_FILL)
        self.jobs_scrollbar = HaloScrollbar(jobs_grid, command=self.jobs_canvas.yview,
                                            behind=theme.PANEL_FILL)
        self.jobs_inner = tk.Frame(self.jobs_canvas, bg=theme.PANEL_FILL)
        self._jobs_window = self.jobs_canvas.create_window(
            (0, 0), window=self.jobs_inner, anchor="nw")

        def _sync_jobs_scrollregion(_event=None):
            self.jobs_canvas.configure(scrollregion=self.jobs_canvas.bbox("all"))
            self.jobs_canvas.itemconfigure(
                self._jobs_window, width=max(1, self.jobs_canvas.winfo_width()))

        self.jobs_inner.bind("<Configure>", _sync_jobs_scrollregion)
        self.jobs_canvas.bind(
            "<Configure>",
            lambda event: self.jobs_canvas.itemconfigure(self._jobs_window, width=event.width))
        self.jobs_canvas.configure(yscrollcommand=self.jobs_scrollbar.set)

        self.jobs_canvas.grid(row=0, column=0, sticky="nsew")
        self.jobs_scrollbar.grid(row=0, column=1, sticky="ns", padx=(px(2), 0))

        self._job_rows: dict[str, JobRow] = {}
        self._jobs_empty_label: tk.Label | None = None
        self.refresh_jobs()

        # Live filename preview whenever the pattern text changes, and the
        # live bitrate estimate while the target is typed (this trace moved
        # here with the compression card).
        app.export_name_pattern_var.trace_add("write", lambda *a: self.refresh())
        app.compression_target_var.trace_add(
            "write", lambda *a: app.update_compression_estimate())

    # ------------------------------------------------------------------

    def _section(self, parent, text, first=False):
        tk.Label(parent, text=text, font=theme.font_title(12), bg=theme.PANEL_FILL,
                 fg=theme.ACCENT, anchor="w").pack(
            fill=tk.X, pady=(px(2) if first else px(12), px(4)))

    # ------------------------------------------------------------------

    def refresh(self):
        """Sync destination/preview text and control states with the app.
        Cheap (labels + button states); callers invoke it freely."""
        app = self.app

        directory = str(app.resolved_export_dir())
        self.dest_label.config(text=_ellipsize_middle(directory, 40))
        # winfo_manager (not ismapped) so back-to-back refreshes before an
        # idle pass still see the pending pack.
        custom = app.export_destination is not None
        packed = app.export_dest_reset_button.winfo_manager() != ""
        if custom and not packed:
            app.export_dest_reset_button.pack(side=tk.RIGHT, padx=(px(4), px(6)))
        elif not custom and packed:
            app.export_dest_reset_button.pack_forget()

        if app.video_path:
            stem = app.resolved_export_stem()
            self.name_preview.config(
                text=_ellipsize_middle(f"→ {stem}.mp4", 52), fg=theme.ACCENT)
        else:
            self.name_preview.config(text="→ load a clip to export",
                                     fg=theme.TEXT_DIM)

        exporting = app.is_exporting
        loaded = bool(app.video_path)
        idle = tk.DISABLED if exporting else tk.NORMAL
        app.export_pattern_entry.config(state=idle)
        app.export_browse_button.config(state=idle)
        app.export_dest_reset_button.config(state=idle)
        ready = tk.NORMAL if (loaded and not exporting) else tk.DISABLED
        app.export_go_button.config(state=ready)
        app.export_saveas_button.config(state=ready)

    # ------------------------------------------------------------------

    def refresh_jobs(self):
        """Rebuild the job rows from the history (≤20 rows — cheap). The
        10 Hz progress path uses update_job instead."""
        for row in self._job_rows.values():
            row.destroy()
        self._job_rows = {}
        if self._jobs_empty_label is not None:
            self._jobs_empty_label.destroy()
            self._jobs_empty_label = None

        jobs = self.app.job_history.jobs
        if not jobs:
            self._jobs_empty_label = tk.Label(
                self.jobs_inner, text="No exports yet.", font=theme.font_small(),
                bg=theme.PANEL_FILL, fg=theme.TEXT_DIM, anchor="w")
            self._jobs_empty_label.pack(fill=tk.X)
            return

        for job in jobs:
            row = JobRow(self.jobs_inner, self.app, job)
            row.pack(fill=tk.X, pady=(0, px(6)))
            row.update(job)
            self._job_rows[job.job_id] = row

    def update_job(self, job):
        """In-place row update for the running job's progress ticks."""
        row = self._job_rows.get(job.job_id)
        if row is None:
            self.refresh_jobs()
        else:
            row.update(job)

    def scroll_jobs(self, steps: int):
        self.jobs_canvas.yview_scroll(-steps, "units")

    # ------------------------------------------------------------------

    def toggle(self):
        if self.visible:
            self.close()
        else:
            self.open()

    def open(self):
        if self.visible:
            self.frame.lift()
            return
        self.visible = True
        self.refresh()
        self._place(self.width)
        self.frame.lift()
        self._slide(0)
        self.app.update_legend()

    def close(self):
        if not self.visible:
            return
        self.visible = False
        self._slide(self.width, then_forget=True)
        self.app.update_legend()

    def hide(self):
        """Instant close (no animation) — e.g. the clip is being unloaded."""
        self.visible = False
        self._cancel_anim()
        self.frame.place_forget()
        self.app.update_legend()

    # ------------------------------------------------------------------

    def _place(self, x_offset: int):
        self.frame.place(relx=1.0, y=0, relheight=1.0, anchor="ne",
                         x=x_offset, width=self.width)

    def _cancel_anim(self):
        if self._anim is not None:
            try:
                self.frame.after_cancel(self._anim)
            except Exception:
                pass
            self._anim = None

    def _slide(self, to_x: int, then_forget: bool = False):
        self._cancel_anim()
        try:
            info = self.frame.place_info()
            from_x = int(info.get("x", self.width))
        except Exception:
            from_x = self.width
        delta = (to_x - from_x) / _SLIDE_STEPS

        def step(i=1):
            self._anim = None
            if not self.frame.winfo_exists():
                return
            self._place(round(from_x + delta * i))
            if i < _SLIDE_STEPS:
                self._anim = self.frame.after(16, lambda: step(i + 1))
            elif then_forget and not self.visible:
                self.frame.place_forget()

        step()
