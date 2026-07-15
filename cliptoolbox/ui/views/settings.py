"""Settings overlay — a modal Halo card over whichever screen is active."""
import tkinter as tk

from cliptoolbox.core import engine_factory
from cliptoolbox.core.paths import FFMPEG_BIN_DIR, OUTPUTS_DIR, reveal_file
from cliptoolbox.ui import dialogs, fonts, skins, theme, widgets
from cliptoolbox.ui.theme import px
from cliptoolbox.ui.views.shell import UI_VERSION


class SettingsOverlay:
    def __init__(self, app):
        self.app = app
        root = app.root

        self.overlay = tk.Toplevel(root)
        self.overlay.overrideredirect(True)
        self.overlay.configure(bg="#000000")
        try:
            self.overlay.attributes("-alpha", 0.45)
        except Exception:
            pass

        self.card_win = tk.Toplevel(root)
        self.card_win.overrideredirect(True)
        self.card_win.configure(bg=theme.PANEL_BORDER)

        self._card_w = px(470)
        card = tk.Frame(self.card_win, bg=theme.PANEL_FILL)
        card.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

        strip = tk.Frame(card, bg=theme.TITLE_FILL)
        strip.pack(fill=tk.X)
        tk.Frame(strip, bg=theme.ACCENT, width=px(4)).pack(side=tk.LEFT, fill=tk.Y)
        tk.Label(strip, text="SETTINGS", font=theme.font_title(14),
                 bg=theme.TITLE_FILL, fg=theme.TITLE_TEXT).pack(side=tk.LEFT, padx=px(10), pady=px(6))

        body = tk.Frame(card, bg=theme.PANEL_FILL)
        body.pack(fill=tk.BOTH, expand=True, padx=px(20), pady=px(14))

        def section(text):
            tk.Label(body, text=text.upper(), font=theme.font_title(12),
                     bg=theme.PANEL_FILL, fg=theme.ACCENT, anchor="w").pack(fill=tk.X, pady=(px(10), px(2)))

        # --- interface ---------------------------------------------------
        section("Interface")
        skin_row = tk.Frame(body, bg=theme.PANEL_FILL)
        skin_row.pack(fill=tk.X)
        tk.Label(skin_row, text="Skin", font=theme.font_body(),
                 bg=theme.PANEL_FILL, fg=theme.TEXT).pack(side=tk.LEFT)
        # id <-> segmented label, driven by the registry so new skins appear
        # here without touching this view.
        self._skin_labels = {sid: label.upper() for sid, label in skins.available()}
        self._skin_ids = {label: sid for sid, label in self._skin_labels.items()}
        current = skins.normalize(app.settings.ui_skin)
        self.skin_var = tk.StringVar(value=self._skin_labels[current])
        widgets.HaloSegmented(
            skin_row, list(self._skin_labels.values()), self.skin_var,
            behind=theme.PANEL_FILL,
        ).pack(side=tk.LEFT, padx=(px(12), 0))
        tk.Label(body, text="Skin changes apply the next time ClipToolbox starts.",
                 font=theme.font_small(), bg=theme.PANEL_FILL, fg=theme.TEXT_DIM,
                 anchor="w", wraplength=self._card_w - px(48),
                 justify=tk.LEFT).pack(fill=tk.X, pady=(px(2), 0))

        # --- window ------------------------------------------------------
        section("Window")
        self.remember_var = tk.BooleanVar(value=app.settings.remember_geometry)
        widgets.HaloCheckbox(
            body, text="Remember window size and position",
            variable=self.remember_var, behind=theme.PANEL_FILL,
        ).pack(anchor="w")

        self.flash_var = tk.BooleanVar(value=app.settings.notify_flash_taskbar)
        widgets.HaloCheckbox(
            body, text="Flash the taskbar when exports finish in background",
            variable=self.flash_var, behind=theme.PANEL_FILL,
        ).pack(anchor="w")

        # --- playback ----------------------------------------------------
        section("Playback")
        self.autoplay_var = tk.BooleanVar(value=app.auto_preview_after_load)
        widgets.HaloCheckbox(
            body, text="Play the preview automatically when a clip loads",
            variable=self.autoplay_var, behind=theme.PANEL_FILL,
        ).pack(anchor="w")

        engine_row = tk.Frame(body, bg=theme.PANEL_FILL)
        engine_row.pack(fill=tk.X, pady=(px(8), 0))
        tk.Label(engine_row, text="Engine", font=theme.font_body(),
                 bg=theme.PANEL_FILL, fg=theme.TEXT).pack(side=tk.LEFT)
        self._mpv_available = engine_factory.ENGINE_MPV in engine_factory.available_engines()
        self.engine_var = tk.StringVar(
            value="MPV" if app.playback_engine_name == engine_factory.ENGINE_MPV else "FFPLAY")
        self.engine_combo = widgets.HaloSegmented(
            engine_row, ["FFPLAY", "MPV"], self.engine_var, behind=theme.PANEL_FILL)
        self.engine_combo.pack(side=tk.LEFT, padx=(px(12), 0))
        if not self._mpv_available:
            self.engine_var.set("FFPLAY")
            self.engine_combo.config(state=tk.DISABLED)
            tk.Label(body, text="mpv.exe not found — put an mpv build in the mpv "
                     "folder next to ffmpeg (see BUILD_NOTES) to enable it.",
                     font=theme.font_small(), bg=theme.PANEL_FILL, fg=theme.TEXT_DIM,
                     anchor="w", wraplength=self._card_w - px(48),
                     justify=tk.LEFT).pack(fill=tk.X, pady=(px(2), 0))
        else:
            tk.Label(body, text="mpv gives smoother pausing and live-frame "
                     "scrubbing for crop keyframing. FFplay is the lightweight default.",
                     font=theme.font_small(), bg=theme.PANEL_FILL, fg=theme.TEXT_DIM,
                     anchor="w", wraplength=self._card_w - px(48),
                     justify=tk.LEFT).pack(fill=tk.X, pady=(px(2), 0))

        cache_row = tk.Frame(body, bg=theme.PANEL_FILL)
        cache_row.pack(fill=tk.X, pady=(px(8), 0))
        tk.Label(cache_row, text="Seek cache (mpv)", font=theme.font_body(),
                 bg=theme.PANEL_FILL, fg=theme.TEXT).pack(side=tk.LEFT)
        self.cache_var = tk.StringVar(value=str(app.settings.mpv_cache_mb))
        self.cache_entry = widgets.HaloEntry(cache_row, textvariable=self.cache_var, width=6)
        self.cache_entry.pack(side=tk.LEFT, padx=(px(12), 0))
        tk.Label(cache_row, text="MB", font=theme.font_body(),
                 bg=theme.PANEL_FILL, fg=theme.TEXT_DIM).pack(side=tk.LEFT, padx=(px(6), 0))
        if not self._mpv_available:
            self.cache_entry.config(state=tk.DISABLED)
        else:
            tk.Label(body, text="RAM buffer for instant seeking — the bright line "
                     "under the seekbar shows what's cached. Bigger covers longer clips.",
                     font=theme.font_small(), bg=theme.PANEL_FILL, fg=theme.TEXT_DIM,
                     anchor="w", wraplength=self._card_w - px(48),
                     justify=tk.LEFT).pack(fill=tk.X, pady=(px(2), 0))

        # --- library -----------------------------------------------------
        section("Library")
        row = tk.Frame(body, bg=theme.PANEL_FILL)
        row.pack(fill=tk.X, pady=(px(2), 0))
        widgets.HaloButton(
            row, text="OPEN OUTPUTS FOLDER", behind=theme.PANEL_FILL,
            height=px(26), font=theme.font_small(12),
            command=self._open_outputs,
        ).pack(side=tk.LEFT)
        self._clear_recents_btn = widgets.HaloButton(
            row, text="CLEAR RECENT CLIPS", behind=theme.PANEL_FILL,
            height=px(26), font=theme.font_small(12), variant="danger",
            command=self._clear_recents,
        )
        self._clear_recents_btn.pack(side=tk.LEFT, padx=(px(8), 0))
        self._cleared_recents_backup = None

        # --- about -------------------------------------------------------
        section("About")
        for line in (
            f"ClipToolbox v{UI_VERSION} — {theme.SKIN_LABEL} interface",
            f"FFmpeg folder: {FFMPEG_BIN_DIR}",
            f"Font: {fonts.describe()} · UI rendered by Pillow",
        ):
            tk.Label(body, text=line, font=theme.font_small(),
                     bg=theme.PANEL_FILL, fg=theme.TEXT_DIM, anchor="w",
                     wraplength=self._card_w - px(48), justify=tk.LEFT).pack(fill=tk.X)

        buttons = tk.Frame(card, bg=theme.PANEL_FILL)
        buttons.pack(fill=tk.X, padx=px(20), pady=(0, px(16)))
        widgets.HaloButton(buttons, text="DONE", variant="primary",
                           behind=theme.PANEL_FILL, width=px(110), height=px(30),
                           command=self.save_and_close).pack(side=tk.RIGHT)

        self.card_win.bind("<Return>", lambda e: self.save_and_close())
        self.card_win.bind("<Escape>", lambda e: self.cancel())

        self._configure_bind = root.bind("<Configure>", self._reposition, add="+")
        self._reposition()

        self.overlay.lift(root)
        self.card_win.lift(self.overlay)
        try:
            self.card_win.grab_set()
        except Exception:
            pass
        self.card_win.focus_force()

    def _open_outputs(self):
        OUTPUTS_DIR.mkdir(exist_ok=True)
        reveal_file(str(OUTPUTS_DIR))

    def _clear_recents(self):
        # A toast's UNDO button would be unclickable behind this overlay's grab,
        # so the button flips to UNDO CLEAR in place instead (roadmap Q5).
        if not self.app.recent_clips:
            return
        self._cleared_recents_backup = list(self.app.recent_clips)
        self.app.recent_clips.clear()
        self.app.save_settings()
        if hasattr(self.app, "refresh_recents_grid"):
            self.app.refresh_recents_grid()
        self._clear_recents_btn.config(text="UNDO CLEAR", command=self._undo_clear_recents)

    def _undo_clear_recents(self):
        if self._cleared_recents_backup is None:
            return
        self.app.recent_clips[:] = self._cleared_recents_backup
        self._cleared_recents_backup = None
        self.app.save_settings()
        if hasattr(self.app, "refresh_recents_grid"):
            self.app.refresh_recents_grid()
        self._clear_recents_btn.config(text="CLEAR RECENT CLIPS", command=self._clear_recents)

    def _reposition(self, _event=None):
        try:
            root = self.app.root
            rx, ry = root.winfo_rootx(), root.winfo_rooty()
            rw, rh = root.winfo_width(), root.winfo_height()
            self.overlay.geometry(f"{rw}x{rh}+{rx}+{ry}")
            self.card_win.update_idletasks()
            ch = self.card_win.winfo_reqheight()
            cx = rx + (rw - self._card_w) // 2
            cy = ry + max(0, round(rh * 0.44) - ch // 2)
            self.card_win.geometry(f"{self._card_w}x{ch}+{cx}+{cy}")
        except Exception:
            pass

    def cancel(self):
        """Esc: discard every pending choice — nothing here applies until
        DONE. (The Library buttons act immediately and are not undone.)"""
        self._teardown()

    def save_and_close(self):
        self.app.settings.remember_geometry = bool(self.remember_var.get())
        self.app.settings.notify_flash_taskbar = bool(self.flash_var.get())
        self.app.auto_preview_after_load = bool(self.autoplay_var.get())
        selected_skin = self._skin_ids.get(self.skin_var.get(), self.app.settings.ui_skin)
        skin_changed = selected_skin != skins.normalize(self.app.settings.ui_skin)
        if skin_changed:
            self.app.settings.ui_skin = selected_skin
        # Only act on the engine choice when mpv is actually available, so a
        # stored "mpv" preference is preserved even while mpv.exe is missing.
        if self._mpv_available:
            selected = (engine_factory.ENGINE_MPV if self.engine_var.get() == "MPV"
                        else engine_factory.ENGINE_FFPLAY)
            if selected != self.app.settings.playback_engine:
                self.app.settings.playback_engine = selected
                self.app.switch_playback_engine(selected)
            try:
                cache_mb = int(float(self.cache_var.get().strip().replace(",", ".")))
            except (TypeError, ValueError):
                cache_mb = self.app.settings.mpv_cache_mb
            cache_mb = max(16, min(4096, cache_mb))
            if cache_mb != self.app.settings.mpv_cache_mb:
                self.app.settings.mpv_cache_mb = cache_mb
                self.app.apply_mpv_cache_size(cache_mb)
        self.app.save_settings()

        self._teardown()

        if skin_changed:
            label = dict(skins.available()).get(selected_skin, selected_skin)
            dialogs.toast(
                "Skin saved",
                f"{label} loads the next time ClipToolbox starts.",
                kind="info",
            )

    def _teardown(self):
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
