"""Command registry for the Ctrl+K command palette.

A single source of truth listing every user-facing action with its keyboard
hint and an availability predicate. The palette (``ui/views/palette.py``) renders
this list; unavailable commands are shown greyed with their shortcut still
visible so the palette doubles as an always-current cheat-sheet (roadmap B3,
absorbs usability finding F7 / obsoletes M2).

Every command's ``run`` calls an existing ``HaloApp`` method — no behaviour is
reimplemented here, so the palette can never drift from the real key bindings.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from cliptoolbox.core.paths import OUTPUTS_DIR, reveal_file


@dataclass
class Command:
    id: str
    label: str
    category: str
    run: Callable[[], None]
    keys: str = ""                                   # display hint, e.g. "Ctrl+E"
    enabled: Callable[[], bool] = field(default=lambda: True)
    keywords: str = ""                               # extra search synonyms

    def searchable(self) -> str:
        return f"{self.label} {self.category} {self.keywords}".lower()


def score(query: str, text: str) -> float | None:
    """Fuzzy match ``query`` against ``text`` (already lower-cased is fine).

    Returns a rank where **lower is better**, or ``None`` when the query is not
    even a subsequence of the text. An empty query keeps everything (0.0).
    Substring hits always outrank scattered subsequence hits.
    """
    q = query.lower().strip()
    if not q:
        return 0.0
    t = text.lower()

    idx = t.find(q)
    if idx != -1:
        boundary = 0.0 if idx == 0 or t[idx - 1] == " " else 0.3
        return idx * 0.01 + boundary

    # Subsequence fallback: every query char in order, penalise spread/gaps.
    pos: list[int] = []
    cursor = 0
    for ch in q:
        found = t.find(ch, cursor)
        if found == -1:
            return None
        pos.append(found)
        cursor = found + 1
    span = pos[-1] - pos[0]
    gaps = sum(1 for a, b in zip(pos, pos[1:]) if b - a > 1)
    return 5.0 + span * 0.05 + gaps * 0.5 + pos[0] * 0.02


def build_command_registry(app) -> list[Command]:
    """Build the ordered command list bound to a live ``HaloApp``."""

    def workspace_ready() -> bool:
        return (app.active_screen == "workspace"
                and bool(app.video_path)
                and not app.is_exporting)

    def crop_active() -> bool:
        return workspace_ready() and bool(app.crop_enabled_var.get())

    def toggle_loop():
        app.loop_enabled_var.set(not app.loop_enabled_var.get())
        app.on_loop_toggle()

    def jump_end():
        app.seek_absolute(app.total_duration_seconds or 0.0)

    return [
        # --- File --------------------------------------------------------
        Command("file.load", "Load clip", "File", app.load_video_dialog,
                keys="Ctrl+O", enabled=lambda: not app.is_exporting,
                keywords="open video import file"),
        Command("file.settings", "Settings", "File", app.open_settings,
                keys="Ctrl+,", enabled=lambda: not app.is_exporting,
                keywords="preferences options skin engine"),
        Command("file.outputs", "Open outputs folder", "File",
                lambda: (OUTPUTS_DIR.mkdir(exist_ok=True), reveal_file(str(OUTPUTS_DIR))),
                keywords="reveal explorer exports library"),
        Command("file.menu", "Back to menu", "File", app.show_landing,
                keys="Esc", enabled=lambda: app.active_screen == "workspace" and not app.is_exporting,
                keywords="landing home close clip"),
        Command("file.quit", "Quit ClipToolbox", "File", app.on_close,
                keywords="exit close"),

        # --- Playback ----------------------------------------------------
        Command("play.toggle", "Play / Pause", "Playback", app.toggle_preview,
                keys="Space", enabled=workspace_ready, keywords="preview resume"),
        Command("play.mute", "Toggle mute", "Playback", app.toggle_mute_preview,
                keys="M", enabled=workspace_ready, keywords="sound audio silence"),
        Command("play.loop", "Toggle loop", "Playback", toggle_loop,
                enabled=workspace_ready, keywords="repeat"),
        Command("play.start", "Jump to start", "Playback",
                lambda: app.seek_absolute(0.0), keys="Home",
                enabled=workspace_ready, keywords="beginning seek"),
        Command("play.end", "Jump to end", "Playback", jump_end,
                keys="End", enabled=workspace_ready, keywords="finish seek"),
        Command("play.prevframe", "Step back one frame", "Playback",
                lambda: app.step_frame(-1), keys=",",
                enabled=workspace_ready, keywords="previous scrub"),
        Command("play.nextframe", "Step forward one frame", "Playback",
                lambda: app.step_frame(1), keys=".",
                enabled=workspace_ready, keywords="next scrub"),
        Command("play.copytime", "Copy timestamp", "Playback", app.copy_timestamp,
                keys="Ctrl+Shift+C", enabled=workspace_ready,
                keywords="clipboard time position"),

        # --- Trim --------------------------------------------------------
        Command("trim.start", "Set trim start", "Trim", app.set_trim_start,
                keys="[", enabled=workspace_ready, keywords="in point mark"),
        Command("trim.end", "Set trim end", "Trim", app.set_trim_end,
                keys="]", enabled=workspace_ready, keywords="out point mark"),
        Command("trim.gotostart", "Jump to trim start", "Trim",
                lambda: app.jump_to_trim("start"), keys="Shift+Home",
                enabled=workspace_ready, keywords="in point seek"),
        Command("trim.gotoend", "Jump to trim end", "Trim",
                lambda: app.jump_to_trim("end"), keys="Shift+End",
                enabled=workspace_ready, keywords="out point seek"),
        Command("trim.clear", "Clear trim points", "Trim", app.clear_trim_points_action,
                enabled=workspace_ready, keywords="reset remove in out"),

        # --- Crop --------------------------------------------------------
        Command("crop.toggle", "Toggle crop mode", "Crop", app.toggle_crop_mode,
                keys="C", enabled=lambda: workspace_ready() and app.video_dimensions is not None,
                keywords="reframe pan zoom region"),
        Command("crop.preview", "Toggle crop preview", "Crop", app.on_crop_preview_toggle,
                enabled=crop_active, keywords="working view"),
        Command("crop.addkey", "Add crop keyframe", "Crop", app.on_crop_add_key,
                keys="K", enabled=crop_active, keywords="keyframe animate"),
        Command("crop.delkey", "Delete crop keyframe", "Crop", app.on_crop_delete_key,
                enabled=crop_active, keywords="remove keyframe"),
        Command("crop.prevkey", "Previous crop keyframe", "Crop", app.on_crop_prev_key,
                enabled=crop_active, keywords="back keyframe"),
        Command("crop.nextkey", "Next crop keyframe", "Crop", app.on_crop_next_key,
                enabled=crop_active, keywords="forward keyframe"),
        Command("crop.resetrect", "Reset crop rectangle", "Crop", app.on_crop_reset_rect,
                enabled=crop_active, keywords="full frame"),
        Command("crop.clearkeys", "Clear crop keyframes", "Crop", app.on_crop_clear_keys,
                enabled=crop_active, keywords="remove all animate"),

        # --- Export ------------------------------------------------------
        Command("export.run", "Export video", "Export", app.export_video_dialog,
                keys="Ctrl+E", enabled=workspace_ready, keywords="render save mp4 encode"),
        Command("export.cancel", "Cancel export", "Export", app.cancel_export,
                keys="Esc", enabled=lambda: app.is_exporting, keywords="stop abort"),

        # --- Frame -------------------------------------------------------
        Command("frame.save", "Save frame", "Frame",
                lambda: app.snapshot_frame("save"), enabled=workspace_ready,
                keywords="screenshot still png snapshot"),
        Command("frame.saveas", "Save frame as…", "Frame",
                lambda: app.snapshot_frame("saveas"), enabled=workspace_ready,
                keywords="screenshot still png snapshot dialog"),

        # --- View --------------------------------------------------------
        Command("view.resetzoom", "Reset timeline zoom", "View", app.reset_timeline_zoom,
                keys="Ctrl+0", enabled=workspace_ready, keywords="fit timeline"),
    ]
