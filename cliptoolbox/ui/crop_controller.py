"""CropController — owns all crop/zoom ("pan/crop") editing state.

Keeping this logic out of the HaloApp god-class means the crop feature is a
single, self-contained unit: the app only forwards a handful of thin delegates
here (toggle, toolbar buttons, keyframe-marker callbacks) and asks for the
filter chains at export time. Everything else — pausing to edit, routing the
backdrop still, auto-keying, retiming, invalidating the paused pipeline so the
next resume picks up the new filter — lives in this file.

The controller talks to three widgets (app.cropbox, app.seekbar, the crop
toolbar) and the playback engine, but never reaches into engine internals: it
uses the same public methods the rest of the app uses.
"""
import tkinter as tk

from cliptoolbox.constants import PREVIEW_MOTION_SCALE_FLAGS
from cliptoolbox.core import motion, playback as core_playback
from cliptoolbox.core.motion import CropKeyframe, CropTrack
from cliptoolbox.ui import dialogs
from cliptoolbox.ui.theme import px


class CropController:
    def __init__(self, app):
        self.app = app
        self.track = CropTrack()
        self.src_w = 0
        self.src_h = 0
        self.duration: float | None = None
        self.fps: float | None = None
        self._editing = False

        app.cropbox.bind_change(self.on_rect_change)
        app.cropbox.bind_commit(self.on_rect_commit)
        app.playback.set_video_chain_provider(self.preview_chain)

        app.crop_checkbox.config(state=tk.DISABLED)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @property
    def editing(self) -> bool:
        """True in working mode: the crop box is shown and playback is paused."""
        return self._editing

    @property
    def active(self) -> bool:
        """True whenever crop mode is on (either working or preview mode)."""
        return self.track.enabled

    @property
    def previewing(self) -> bool:
        """True in preview mode: playing back with the crop/keyframes applied."""
        return self.track.enabled and not self._editing

    def reset(self):
        """New file loaded: drop keyframes and leave crop mode."""
        if self._editing:
            self._exit_edit()
        self.track = CropTrack()
        self.src_w = self.src_h = 0
        self.duration = self.fps = None
        self.app.crop_enabled_var.set(False)
        self.app.seekbar.set_keyframes([])
        self._hide_toolbar()
        self.app.crop_checkbox.config(state=tk.DISABLED)

    def set_source(self, dimensions, duration, fps):
        """Called from after_probe with the probed source dimensions."""
        self.duration = duration
        self.fps = fps
        if dimensions and dimensions[0] > 0 and dimensions[1] > 0:
            self.src_w, self.src_h = int(dimensions[0]), int(dimensions[1])
            self.app.cropbox.set_source(self.src_w, self.src_h)
            self.app.crop_checkbox.config(state=tk.NORMAL)
        else:
            self.src_w = self.src_h = 0
            self.app.crop_checkbox.config(state=tk.DISABLED)

    def export_state(self) -> dict:
        """Serializable snapshot for the per-video session store."""
        return {
            "enabled": bool(self.track.enabled),
            "keyframes": [[kf.t, kf.x, kf.y, kf.w, kf.h]
                          for kf in self.track.keyframes],
        }

    def restore_state(self, state: dict) -> bool:
        """Reload a saved session's crop setup (called after set_source). If
        crop mode was on, come back in preview mode — playback applies the
        crop; the editor stays closed until the user opens it."""
        try:
            keyframes = tuple(sorted(
                (CropKeyframe(float(t), float(x), float(y), float(w), float(h))
                 for t, x, y, w, h in state.get("keyframes") or []),
                key=lambda kf: kf.t,
            ))
        except (TypeError, ValueError):
            return False
        if not keyframes:
            return False
        self.track.keyframes = keyframes
        if state.get("enabled") and self.src_w > 0:
            self.track.enabled = True
            self.app.crop_enabled_var.set(True)
            self._show_toolbar()
            self._update_mode_button()
            self._refresh_markers()
        return True

    def on_toggle(self):
        if self.app.crop_enabled_var.get():
            if self.src_w <= 0:
                self.app.crop_enabled_var.set(False)
                dialogs.showinfo("Crop unavailable",
                                 "Could not read this video's dimensions.")
                return
            self.track.enabled = True
            self._show_toolbar()
            self._refresh_markers()
            self.enter_work()
            self.app.log("Crop/zoom mode enabled. Working mode — drag to crop, "
                         "K to keyframe, PREVIEW to play it back.")
        else:
            self.track.enabled = False
            self._exit_edit()
            self._hide_toolbar()
            self.app.seekbar.set_keyframes([])
            self._invalidate_pipeline()
            self.app.update_compression_estimate()
            # The cropbox is gone; refresh the plain (uncropped) paused frame so
            # the preview isn't left showing a stale overlay.
            if self.app.playback.state == core_playback.PAUSED:
                pos = self.app.current_seek_seconds()
                self.app.pending_still_request = self.app.playback.request_still(pos, vf=None)
            self.app.log("Crop/zoom mode disabled.")

    # ------------------------------------------------------------------
    # Working mode ⇄ preview mode
    # ------------------------------------------------------------------
    # Crop mode has two sub-states while enabled: WORKING (paused, the crop box
    # is shown, keyframes are editable) and PREVIEW (the clip plays back with
    # the crop/keyframes applied, box hidden). The main play button and the
    # toolbar's PREVIEW/EDIT button both flip between them.

    def toggle_mode(self):
        """Flip between working and preview mode (from the play button / the
        toolbar toggle)."""
        if not self.track.enabled:
            return
        if self._editing:
            self.enter_preview()
        else:
            self.enter_work()

    def enter_work(self):
        """Switch to working mode: pause on the current frame with the crop box
        so keyframes can be added/edited."""
        self._enter_edit()
        self._update_mode_button()

    def enter_preview(self):
        """Switch to preview mode: play the clip back with the crop applied."""
        if not self.app.superset_tracks():
            dialogs.showinfo(
                "Preview needs a track",
                "Preview playback needs at least one audio track. Keep working "
                "in the editor, or export to see the crop result.",
            )
            return
        self.leave_edit_for_playback()
        self._start_preview_playback()
        self._update_mode_button()

    def leave_edit_for_playback(self):
        """Hide the editor box because playback is (about to be) started by the
        caller. Used by enter_preview and by the normal play/export paths."""
        if self._editing:
            self._exit_edit()
            self._update_mode_button()

    def on_playback_ended(self):
        """A preview reached the end: drop back into working mode at the last
        frame so the box is available again."""
        if self.track.enabled and not self._editing:
            self.enter_work()

    def _start_preview_playback(self):
        pos = self.app.current_seek_seconds()
        duration = self.duration or 0
        if duration and pos >= duration - 0.1:
            # Previewing from the very end would EOF instantly and bounce
            # straight back to working mode; restart like any media player.
            pos = 0.0
            self.app.set_seek_position(pos)
        state = self.app.playback.state
        if state in (core_playback.PLAYING, core_playback.STARTING):
            return
        if state == core_playback.PAUSED:
            self.app.restart_playback_at(pos)
        else:
            self.app.start_preview()

    def _update_mode_button(self):
        btn = getattr(self.app, "crop_preview_button", None)
        if btn is None:
            return
        # The label names the mode you switch TO.
        btn.config(text="PREVIEW  ▶" if self._editing else "◀  EDIT")

    # ------------------------------------------------------------------
    # Edit mode enter/exit
    # ------------------------------------------------------------------

    def _enter_edit(self):
        self._editing = True
        self._ensure_paused_still()
        seconds = self.app.current_seek_seconds()
        self.app.cropbox.place(x=0, y=0, relwidth=1, relheight=1)
        # Raise the widget in the stacking order. Canvas maps both lift and
        # tkraise to tag_raise (canvas items), so call the Misc method directly.
        tk.Misc.lift(self.app.cropbox)
        rect = self.track.rect_at(seconds) or self.app.cropbox.full_frame_rect()
        self.app.cropbox.set_rect(*rect)
        # Uncropped backdrop (vf=None) so the editor shows the whole frame.
        self.app.pending_still_request = self.app.playback.request_still(seconds, vf=None)
        self._update_info(seconds)

    def _exit_edit(self):
        if not self._editing:
            return
        self._editing = False
        try:
            self.app.cropbox.place_forget()
        except Exception:
            pass

    def _ensure_paused_still(self):
        """Get to a concealed paused state so Tk can own the preview surface
        (the live FFplay window paints over Tk)."""
        state = self.app.playback.state
        if state in (core_playback.PLAYING, core_playback.STARTING):
            self.app.pause_playback()
            self.app.playback.conceal()
        elif state == core_playback.PAUSED:
            self.app.playback.conceal()
        else:  # IDLE
            self.app.playback.hold_paused_at(self.app.current_seek_seconds())

    # ------------------------------------------------------------------
    # Filter chain providers (called by the engine / export / stills)
    # ------------------------------------------------------------------

    def preview_chain(self, start_seconds, width, height):
        """Engine provider: video chain for a spawn at start_seconds. Runs on
        the spawn thread — pure, no tkinter, reads only atomic state.

        While the editor is open the chain is None: the engine then renders
        (and screenshots) the full uncropped frame, which is exactly what the
        editor backdrop needs — the crop lives in the overlay rect instead."""
        if not self.track.enabled or self.src_w <= 0 or self._editing:
            return None
        out_w, out_h = motion.fit_size(self.src_w, self.src_h, width, height)
        return motion.build_motion_chain(
            self.track, self.src_w, self.src_h, out_w, out_h,
            time_offset=start_seconds, scale_flags=PREVIEW_MOTION_SCALE_FLAGS,
        )

    def _export_motion(self, trim_start):
        if not self.track.enabled or self.src_w <= 0:
            return None
        out_w = motion.even_floor(self.src_w)
        out_h = motion.even_floor(self.src_h)
        return motion.build_motion_chain(
            self.track, self.src_w, self.src_h, out_w, out_h,
            time_offset=trim_start or 0.0,
        )

    def export_video_chain(self, trim_start):
        """Standard export -vf value (None keeps the stream-copy fast path)."""
        chain = self._export_motion(trim_start)
        return f"{chain},setsar=1" if chain else None

    def export_prefilter(self, trim_start):
        """Compressed export prefix (prepended before the scale cap)."""
        return self._export_motion(trim_start)

    def will_reencode(self) -> bool:
        """True when the active crop forces the standard export to re-encode."""
        return self._export_motion(None) is not None

    def still_vf(self, seconds):
        """VF for paused/scrub stills: cropped normally, but uncropped while
        editing so the crop editor shows the full frame."""
        if self._editing:
            return None
        return self._static_vf(seconds)

    def snapshot_vf(self, seconds):
        """VF for saved/copied frames: always bake in the crop effect."""
        return self._static_vf(seconds)

    def _static_vf(self, seconds):
        if not self.track.enabled or self.src_w <= 0:
            return None
        if self.track.is_identity(self.src_w, self.src_h):
            return None
        rect = self.track.rect_at(seconds)
        if rect is None:
            return None
        out_w = motion.even_floor(self.src_w)
        out_h = motion.even_floor(self.src_h)
        return motion.build_still_crop_vf(rect, self.src_w, self.src_h, out_w, out_h)

    # ------------------------------------------------------------------
    # Still routing + playhead
    # ------------------------------------------------------------------

    def route_still(self, kind, payload, width, height, request_id) -> bool:
        """Consume stills while editing (the cropbox owns the surface). Returns
        True if handled. Only the freshest JPEG backdrop is shown; the BGRA
        conceal capture is ignored in favour of the explicit uncropped frame."""
        if not self._editing:
            return False
        if (kind == core_playback.STILL_KIND_JPEG
                and request_id >= self.app.pending_still_request):
            self.app.cropbox.set_image(payload)
        return True

    def on_playhead(self, seconds):
        """Move the crop overlay to the interpolated rect at seconds (so
        scrubbing shows the box glide between keyframes). No-op unless editing."""
        if not self._editing:
            return
        rect = self.track.rect_at(seconds)
        if rect is not None:
            self.app.cropbox.set_rect(*rect)
        self._update_info(seconds)

    # ------------------------------------------------------------------
    # Rect edits (from the cropbox)
    # ------------------------------------------------------------------

    def on_rect_change(self, rect):
        self.app.crop_info_var.set(f"{int(round(rect[2]))}×{int(round(rect[3]))}")

    def on_rect_commit(self, rect):
        self._commit_rect(rect)

    def _commit_rect(self, rect):
        seconds = self.app.current_seek_seconds()
        self.track.upsert(CropKeyframe(seconds, *rect), self._eps())
        self._refresh_markers()
        self._invalidate_pipeline()
        self.app.log(
            f"Crop keyframe at {self.app.format_seconds(seconds)}: "
            f"{int(round(rect[2]))}×{int(round(rect[3]))}."
        )
        self._update_info(seconds)

    # ------------------------------------------------------------------
    # Toolbar actions
    # ------------------------------------------------------------------

    def add_key(self):
        if self._editing:
            self._commit_rect(self.app.cropbox.get_rect())

    def delete_key(self):
        seconds = self.app.current_seek_seconds()
        if self.track.remove_near(seconds, self._eps()):
            self._refresh_markers()
            self._invalidate_pipeline()
            rect = self.track.rect_at(seconds) or self.app.cropbox.full_frame_rect()
            self.app.cropbox.set_rect(*rect)
            self.app.log("Crop keyframe deleted.")
            self._update_info(seconds)

    def clear_keys(self):
        if not self.track.keyframes:
            return
        if not dialogs.askyesno("Clear crop keyframes",
                                "Remove all crop keyframes for this clip?"):
            return
        self.track.clear()
        self._refresh_markers()
        self._invalidate_pipeline()
        self.app.cropbox.set_rect(*self.app.cropbox.full_frame_rect())
        self.app.log("All crop keyframes cleared.")
        self._update_info(self.app.current_seek_seconds())

    def reset_rect(self):
        if not self._editing:
            return
        full = self.app.cropbox.full_frame_rect()
        self.app.cropbox.set_rect(*full)
        self._commit_rect(full)

    def goto_prev(self):
        t = self.track.prev_time(self.app.current_seek_seconds())
        if t is not None:
            self._seek_to(t)

    def goto_next(self):
        t = self.track.next_time(self.app.current_seek_seconds())
        if t is not None:
            self._seek_to(t)

    # ------------------------------------------------------------------
    # Keyframe marker callbacks (from the seekbar)
    # ------------------------------------------------------------------

    def on_kf_click(self, index):
        times = self.track.times()
        if 0 <= index < len(times):
            self._seek_to(times[index])

    def on_kf_drag(self, index, value):
        self.app.crop_info_var.set(
            f"key {index + 1} → {self.app.format_seconds(value)}"
        )

    def on_kf_commit(self, index, value):
        if not (0 <= index < len(self.track.keyframes)):
            return
        applied = self.track.retime(index, value, self._eps())
        self._refresh_markers()
        self._invalidate_pipeline()
        self.app.log(f"Crop keyframe moved to {self.app.format_seconds(applied)}.")

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _seek_to(self, t):
        self.app.seek_var.set(t)
        self.app.set_seek_position(t)
        state = self.app.playback.state
        if state in (core_playback.PLAYING, core_playback.STARTING):
            # Live playback follows the jump (respawns at t with the filter).
            self.app.restart_playback_at(t)
        else:
            if state == core_playback.PAUSED:
                self.app.playback.seek_paused(t)
            elif state == core_playback.IDLE:
                self.app.playback.hold_paused_at(t)
            self.app.pending_still_request = self.app.playback.request_still(
                t, vf=self.still_vf(t)
            )

    def _invalidate_pipeline(self):
        """Drop / respawn so the next frame reflects the current filter."""
        state = self.app.playback.state
        if state == core_playback.PLAYING:
            self.app.restart_playback_at(self.app.playback.position)
        elif state == core_playback.PAUSED:
            self.app.playback.seek_paused(self.app.playback.position)

    def _eps(self) -> float:
        return 0.5 / max(1.0, self.fps or 30.0)

    def _refresh_markers(self):
        self.app.seekbar.set_keyframes(self.track.times())
        # The compression card hint reflects whether export will re-encode.
        self.app.update_compression_estimate()

    def _show_toolbar(self):
        self.app.crop_toolbar_frame.pack(
            fill=tk.X, pady=(px(4), 0), after=self.app.transport_frame
        )

    def _hide_toolbar(self):
        try:
            self.app.crop_toolbar_frame.pack_forget()
        except Exception:
            pass

    def _update_info(self, seconds):
        count = len(self.track.keyframes)
        if count == 0:
            self.app.crop_info_var.set("no keyframes — drag a corner to add one")
            return
        idx = self.track.index_near(seconds, self._eps())
        rect = self.app.cropbox.get_rect()
        pos = f"{idx + 1}/{count}" if idx is not None else f"–/{count}"
        self.app.crop_info_var.set(f"key {pos}   {int(round(rect[2]))}×{int(round(rect[3]))}")
