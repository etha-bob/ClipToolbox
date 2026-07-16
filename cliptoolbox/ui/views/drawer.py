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
import tkinter as tk

from cliptoolbox.constants import COMPRESSION_RESOLUTION_PRESETS
from cliptoolbox.ui import theme
from cliptoolbox.ui.theme import px
from cliptoolbox.ui.widgets import (
    HaloButton,
    HaloCheckbox,
    HaloEntry,
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

        for widget, tip in (
            (app.compression_target_entry, "Target size in MB (Windows/Discord MiB)"),
            (app.compression_resolution_combo, "Cap the compressed video resolution"),
            (app.timestamp_watermark_duration_entry,
             "How long the timestamp stays fully visible before fading (ms)"),
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

        # Job history rows land here in the next stage.
        self.jobs_host = tk.Frame(body, bg=theme.PANEL_FILL)
        self.jobs_host.pack(fill=tk.BOTH, expand=True, pady=(px(12), 0))

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

        stem = app.resolved_export_stem()
        self.name_preview.config(text=_ellipsize_middle(f"→ {stem}.mp4", 52))

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
