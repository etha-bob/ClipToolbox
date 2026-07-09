"""Settings overlay — a modal Halo card over whichever screen is active."""
import tkinter as tk

from cliptoolbox.core.paths import FFMPEG_BIN_DIR, OUTPUTS_DIR, reveal_file
from cliptoolbox.ui import theme, widgets
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

        strip = tk.Frame(card, bg=theme.SELECT_FILL)
        strip.pack(fill=tk.X)
        tk.Frame(strip, bg=theme.ACCENT, width=px(4)).pack(side=tk.LEFT, fill=tk.Y)
        tk.Label(strip, text="SETTINGS", font=theme.font_title(14),
                 bg=theme.SELECT_FILL, fg=theme.TEXT_BRIGHT).pack(side=tk.LEFT, padx=px(10), pady=px(6))

        body = tk.Frame(card, bg=theme.PANEL_FILL)
        body.pack(fill=tk.BOTH, expand=True, padx=px(20), pady=px(14))

        def section(text):
            tk.Label(body, text=text.upper(), font=theme.font_title(12),
                     bg=theme.PANEL_FILL, fg=theme.ACCENT, anchor="w").pack(fill=tk.X, pady=(px(10), px(2)))

        # --- window ------------------------------------------------------
        section("Window")
        self.native_var = tk.BooleanVar(value=app.settings.native_titlebar)
        widgets.HaloCheckbox(
            body, text="Use the native Windows title bar (applies on next launch)",
            variable=self.native_var, behind=theme.PANEL_FILL,
        ).pack(anchor="w")

        self.remember_var = tk.BooleanVar(value=app.settings.remember_geometry)
        widgets.HaloCheckbox(
            body, text="Remember window size and position",
            variable=self.remember_var, behind=theme.PANEL_FILL,
        ).pack(anchor="w")

        # --- playback ----------------------------------------------------
        section("Playback")
        self.autoplay_var = tk.BooleanVar(value=app.auto_preview_after_load)
        widgets.HaloCheckbox(
            body, text="Play the preview automatically when a clip loads",
            variable=self.autoplay_var, behind=theme.PANEL_FILL,
        ).pack(anchor="w")

        # --- library -----------------------------------------------------
        section("Library")
        row = tk.Frame(body, bg=theme.PANEL_FILL)
        row.pack(fill=tk.X, pady=(px(2), 0))
        widgets.HaloButton(
            row, text="OPEN OUTPUTS FOLDER", behind=theme.PANEL_FILL,
            height=px(26), font=theme.font_small(12),
            command=self._open_outputs,
        ).pack(side=tk.LEFT)
        widgets.HaloButton(
            row, text="CLEAR RECENT CLIPS", behind=theme.PANEL_FILL,
            height=px(26), font=theme.font_small(12), variant="danger",
            command=self._clear_recents,
        ).pack(side=tk.LEFT, padx=(px(8), 0))

        # --- about -------------------------------------------------------
        section("About")
        for line in (
            f"ClipToolbox v{UI_VERSION} — Halo 2 interface",
            f"FFmpeg folder: {FFMPEG_BIN_DIR}",
            "Font: Rajdhani (OFL) · UI rendered by Pillow",
        ):
            tk.Label(body, text=line, font=theme.font_small(),
                     bg=theme.PANEL_FILL, fg=theme.TEXT_DIM, anchor="w",
                     wraplength=self._card_w - px(48), justify=tk.LEFT).pack(fill=tk.X)

        buttons = tk.Frame(card, bg=theme.PANEL_FILL)
        buttons.pack(fill=tk.X, padx=px(20), pady=(0, px(16)))
        widgets.HaloButton(buttons, text="DONE", variant="primary",
                           behind=theme.PANEL_FILL, width=px(110), height=px(30),
                           command=self.close).pack(side=tk.RIGHT)

        self.card_win.bind("<Return>", lambda e: self.close())
        self.card_win.bind("<Escape>", lambda e: self.close())

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
        self.app.recent_clips.clear()
        self.app.save_settings()
        if hasattr(self.app, "refresh_landing_detail"):
            self.app.refresh_landing_detail()

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

    def close(self):
        self.app.settings.native_titlebar = bool(self.native_var.get())
        self.app.settings.remember_geometry = bool(self.remember_var.get())
        self.app.auto_preview_after_load = bool(self.autoplay_var.get())
        self.app.save_settings()

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
