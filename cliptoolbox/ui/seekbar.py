"""HaloSeekbar — the timeline strip: scrubber, filmstrip, waveforms, keyframes.

Grown from the original thin scrubber into the B1 multi-lane timeline while
keeping the tk.Scale behavioral subset the preview state machine relies on:

- linked DoubleVar: external .set() on the variable moves the playhead and
  invokes `command` (exactly like tk.Scale), which on_seek_drag ignores while
  `user_is_seeking` is False;
- `command(value_str)` during user drags;
- press/release hooks (bind_press/bind_release) replacing the old
  .bind("<ButtonPress-1>"/"<ButtonRelease-1>") wiring;
- .configure(to=duration).

Interaction bands: the ruler is a dedicated always-seek scrub lane; trim
brackets grab in the strip body below it (offset grab + drag threshold —
a plain click seeks to the trim time via bind_seek_request instead of
moving it); keyframes own the bottom lane.

Lane stack (top to bottom, logical px; total = theme.SEEKBAR_H):
    2   minimap — zoom position indicator
    14  ruler   — scrub track, elapsed fill, frame grid, mpv cache line
    44  filmstrip — clip thumbnails (grows over the audio band when no tracks)
    32  audio   — per-track waveform lanes
    12  keyframe lane — crop keyframe diamonds

Rendering is split into three tiers so the 10 Hz playback position updates
never touch PIL:

1. ``_base``   — a PIL image of everything static per view (lane wells,
   filmstrip tiles, tinted waveforms, frame grid). Cached one-deep, keyed on
   (size, view, data generation, fps); recomposed only on resize/zoom/data.
2. ``_display`` — the PhotoImage blitted each redraw (base + trim dimming).
3. ``_redraw`` — deletes/creates only cheap native canvas items on top:
   playhead, trim handles, diamonds, cache segments, minimap, overlays.
"""
import math
import tkinter as tk

from PIL import Image, ImageDraw, ImageEnhance, ImageTk

from cliptoolbox.ui import skin, theme
from cliptoolbox.ui.theme import px

# Lane heights (logical px; consumers scale through theme.px). The keyframe
# lane hangs from the bottom so the audio band absorbs any rounding slack.
LANE_MINIMAP_H = 2
LANE_RULER_H = 14
LANE_AUDIO_H = 32
LANE_KF_H = 12


class HaloSeekbar(tk.Canvas):
    def __init__(self, parent, from_=0.0, to=100.0, variable=None, command=None,
                 behind=theme.BG_DEEP):
        self.behind = behind
        self._from = float(from_)
        self._to = float(to)
        self._variable = variable or tk.DoubleVar(value=0.0)
        self._command = command
        self._state = tk.NORMAL
        self._dragging = False
        self._hover = False
        self._trim_start: float | None = None
        self._trim_end: float | None = None
        self._press_callbacks = []
        self._release_callbacks = []
        self._trim_change_callbacks = []
        self._trim_commit_callbacks = []
        self._trim_drag_kind: str | None = None
        self._trim_hover_kind: str | None = None
        self._trim_press_x: int | None = None
        self._trim_grab_dx = 0
        self._trim_moved = False
        self._seek_request_callbacks = []
        self._cursor = ""
        self._suspend_var_sync = False

        # Cached (instantly seekable) ranges, pushed by the mpv engine. Drawn
        # as a thin bright line under the track, like mpv's own cache bar.
        self._cache_ranges: list[tuple[float, float]] = []

        # Keyframe markers (crop/zoom). Times live in the same units as the
        # playhead; the controller owns the authoritative list and pushes it
        # back via set_keyframes after every edit.
        self._keyframes: list[float] = []
        self._kf_press_callbacks = []
        self._kf_drag_callbacks = []
        self._kf_commit_callbacks = []
        self._kf_click_callbacks = []
        self._kf_delete_callbacks = []
        self._kf_inert = False
        self._kf_drag_index: int | None = None
        self._kf_press_x: int | None = None
        self._kf_moved = False
        self._kf_hover_index: int | None = None

        # Zoomed view window (None = the full [_from, _to] range). All pixel
        # mapping goes through _view(), so trim brackets, keyframes and the
        # playhead inherit zoom automatically; drag CLAMPS stay on the full
        # data range. _fps enables the per-frame grid when zoomed far enough.
        self._view_from: float | None = None
        self._view_to: float | None = None
        self._fps: float | None = None

        # Export progress overlay: (percent, attempt, attempts_max) or None.
        self._export_progress: tuple[int, int, int] | None = None

        # Engine-STARTING scanner cue (M4/F13): the widget's only timer.
        self._starting = False
        self._starting_phase = 0
        self._starting_after_id: str | None = None

        # Lane data (pushed by the app; plain PIL images / state strings).
        # _data_gen bumps on every change so the composed base cache misses.
        self._filmstrip: Image.Image | None = None
        self._filmstrip_count = 0
        self._waveforms: list[Image.Image | None] = []
        self._wave_states: list[str] = []
        self._data_gen = 0

        # Three-tier render caches (see module docstring). The PhotoImage
        # reference must live on self — canvas items don't hold one.
        self._base_img: Image.Image | None = None
        self._base_key = None
        self._display_photo: ImageTk.PhotoImage | None = None
        self._display_key = None

        h = px(theme.SEEKBAR_H)
        super().__init__(parent, height=h, highlightthickness=0, bd=0, bg=behind)
        self._wpx, self._hpx = 100, h
        self._pad = px(10)

        self._variable.trace_add("write", self._on_var_write)

        self.bind("<Configure>", self._on_resize)
        self.bind("<Destroy>", self._on_destroy)
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<ButtonPress-3>", self._on_right_press)
        self.bind("<Motion>", self._on_motion)

    # ------------------------------------------------------------------
    # tk.Scale-compatible surface
    # ------------------------------------------------------------------

    def configure(self, **kwargs):
        if "to" in kwargs:
            self._to = max(1e-9, float(kwargs.pop("to")))
        if "from_" in kwargs:
            self._from = float(kwargs.pop("from_"))
        if "state" in kwargs:
            state = str(kwargs.pop("state"))
            self._state = tk.DISABLED if state == tk.DISABLED else tk.NORMAL
        if "command" in kwargs:
            self._command = kwargs.pop("command")
        if kwargs:
            super().configure(**kwargs)
        self._redraw()

    config = configure

    def bind_press(self, callback):
        self._press_callbacks.append(callback)

    def bind_release(self, callback):
        self._release_callbacks.append(callback)

    def bind_trim_change(self, callback):
        """callback(kind, value) fires continuously while a trim bracket is
        dragged; kind is "start" or "end"."""
        self._trim_change_callbacks.append(callback)

    def bind_trim_commit(self, callback):
        """callback(kind) fires once when a trim-bracket drag is released."""
        self._trim_commit_callbacks.append(callback)

    def bind_seek_request(self, callback):
        """callback(seconds) when the widget wants a full app-level seek on
        the user's behalf (e.g. clicking a trim bracket without dragging
        seeks to that trim time)."""
        self._seek_request_callbacks.append(callback)

    def set_trim(self, start: float | None, end: float | None):
        """Draw trim brackets; None hides that bracket."""
        self._trim_start = start
        self._trim_end = end
        self._redraw()

    def bind_keyframe_press(self, callback):
        """callback(index) when a keyframe diamond is grabbed."""
        self._kf_press_callbacks.append(callback)

    def bind_keyframe_drag(self, callback):
        """callback(index, value) fires continuously while a diamond is dragged."""
        self._kf_drag_callbacks.append(callback)

    def bind_keyframe_commit(self, callback):
        """callback(index, value) fires when a diamond drag (a real move) ends."""
        self._kf_commit_callbacks.append(callback)

    def bind_keyframe_click(self, callback):
        """callback(index) fires when a diamond is clicked without dragging."""
        self._kf_click_callbacks.append(callback)

    def set_cache_ranges(self, ranges):
        """Replace the cached-range segments ((start, end) pairs in seconds).
        Empty list hides the cache bar (e.g. the ffplay engine)."""
        self._cache_ranges = [(float(a), float(b)) for a, b in ranges]
        self._redraw()

    def set_keyframes(self, times, inert: bool = False):
        """Replace the keyframe markers. Empty list hides the lane markers.
        inert=True renders ghosted diamonds: keyframes that exist (and will
        persist with the session) but have no effect because crop is off —
        the structural fix for invisible restored crops (F6). They stay
        fully interactive (click seeks, drag retimes, right-click deletes)."""
        self._keyframes = sorted(float(t) for t in times)
        self._kf_inert = bool(inert)
        self._redraw()

    def bind_keyframe_delete(self, callback):
        """callback(index) fires when a diamond is right-clicked."""
        self._kf_delete_callbacks.append(callback)

    def set_filmstrip(self, strip, count: int = 0):
        """Push the filmstrip source: a PIL image of `count` equal-width
        tiles side by side, covering [_from, _to] evenly. None clears the
        lane back to an empty well."""
        self._filmstrip = strip
        self._filmstrip_count = int(count) if strip is not None else 0
        self._data_gen += 1
        self._redraw()

    def set_waveforms(self, waves):
        """Push the waveform sources in roster-row order: white-on-
        transparent PIL images spanning [_from, _to] (None entries render as
        empty lanes while their extraction is still running). An empty list
        collapses the audio band into the filmstrip."""
        self._waveforms = list(waves)
        if len(self._wave_states) != len(self._waveforms):
            self._wave_states = ["normal"] * len(self._waveforms)
        self._data_gen += 1
        self._redraw()

    def set_wave_states(self, states):
        """Mix-state tints in roster-row order: "normal" / "dim" / "solo"."""
        states = list(states)
        if states != self._wave_states:
            self._wave_states = states
            self._data_gen += 1
            self._redraw()

    def set_engine_starting(self, active: bool):
        """Animated scanner segment in the ruler band while the playback
        engine spins up (the STARTING state) — motion where the user's eye
        already is, replacing the static placeholder-only cue (F13). Runs
        the widget's only after() loop; idempotent and leak-free."""
        active = bool(active)
        if active == self._starting:
            return
        self._starting = active
        self._cancel_starting_timer()
        if active:
            self._starting_phase = 0
            self._tick_starting()
        else:
            self._redraw()

    def _cancel_starting_timer(self):
        if self._starting_after_id is not None:
            try:
                self.after_cancel(self._starting_after_id)
            except Exception:
                pass
            self._starting_after_id = None

    def _tick_starting(self):
        self._starting_after_id = None
        if not self._starting or not self.winfo_exists():
            return
        self._starting_phase += 1
        self._redraw()
        self._starting_after_id = self.after(80, self._tick_starting)

    def _on_destroy(self, _event=None):
        self._starting = False
        self._cancel_starting_timer()

    def set_export_progress(self, percent, attempt: int = 1, attempts_max: int = 1):
        """Paint export progress onto the strip (None clears). The fill
        sweeps the trimmed region only — the span actually being exported —
        and resets honestly at the start of every compression attempt."""
        if percent is None:
            new = None
        else:
            new = (max(0, min(100, int(percent))), int(attempt), int(attempts_max))
        if new != self._export_progress:
            self._export_progress = new
            self._redraw()

    # ------------------------------------------------------------------
    # Zoomed view window
    # ------------------------------------------------------------------

    ZOOM_STEP = 1.35  # span factor per wheel notch

    def set_fps(self, fps: float | None):
        """Frame rate for the zoomed-in frame grid (None hides it)."""
        self._fps = float(fps) if fps and fps > 0 else None
        self._redraw()

    def set_view(self, v0: float, v1: float):
        full0, full1 = self._from, self._to
        v0 = max(full0, min(float(v0), full1))
        v1 = max(v0 + 1e-6, min(float(v1), full1))
        if v1 - v0 >= (full1 - full0) - 1e-9:
            self.reset_view()
            return
        self._view_from, self._view_to = v0, v1
        self._redraw()

    def get_view(self) -> tuple[float, float]:
        return self._view()

    def reset_view(self):
        if self._view_from is None and self._view_to is None:
            return
        self._view_from = None
        self._view_to = None
        self._redraw()

    @property
    def zoomed(self) -> bool:
        return self._view_from is not None

    def zoom_at(self, steps: int, x_px: int):
        """Zoom the view by wheel notches, keeping the time under x_px fixed."""
        v0, v1 = self._view()
        span = v1 - v0
        full = max(1e-9, self._to - self._from)
        anchor = self._time_at(x_px)

        new_span = span * (self.ZOOM_STEP ** -steps)

        # Zoom-in floor: pointless past ~40 px per frame (0.25 s if fps unknown).
        x0, x1 = self._usable()
        usable_px = max(1, x1 - x0)
        if self._fps:
            min_span = max(0.05, usable_px / (40.0 * self._fps))
        else:
            min_span = 0.25
        new_span = max(min_span, new_span)

        if new_span >= full:
            self.reset_view()
            return

        frac = min(1.0, max(0.0, (x_px - x0) / usable_px))
        new_v0 = anchor - frac * new_span
        new_v1 = new_v0 + new_span
        if new_v0 < self._from:
            new_v0, new_v1 = self._from, self._from + new_span
        elif new_v1 > self._to:
            new_v0, new_v1 = self._to - new_span, self._to

        self._view_from, self._view_to = new_v0, new_v1
        self._redraw()

    def follow(self, seconds: float):
        """Auto-scroll a zoomed view so the playhead stays visible. No-op when
        not zoomed or while the user is dragging anything on the bar."""
        if self._view_from is None:
            return
        if self._dragging or self._trim_drag_kind is not None or self._kf_drag_index is not None:
            return
        v0, v1 = self._view()
        span = v1 - v0
        if seconds > v0 + 0.85 * span or seconds < v0:
            new_v0 = min(max(self._from, seconds - 0.15 * span), self._to - span)
            if abs(new_v0 - v0) > 1e-9:
                self._view_from = new_v0
                self._view_to = new_v0 + span
                self._redraw()

    # ------------------------------------------------------------------
    # Layout bands (see lane stack in the module docstring)
    # ------------------------------------------------------------------

    def _ruler_top(self) -> int:
        return px(LANE_MINIMAP_H)

    def _ruler_bot(self) -> int:
        return px(LANE_MINIMAP_H) + px(LANE_RULER_H)

    def _scrub_cy(self) -> int:
        """Vertical center of the ruler/scrubber band."""
        return self._ruler_top() + px(LANE_RULER_H) // 2

    def _film_top(self) -> int:
        return self._ruler_bot()

    def _film_bot(self) -> int:
        """Filmstrip bottom: absorbs the audio band when no waveforms."""
        if any(w is not None for w in self._waveforms):
            return self._audio_bot() - px(LANE_AUDIO_H)
        return self._audio_bot()

    def _audio_bot(self) -> int:
        return self._hpx - px(LANE_KF_H)

    def _kf_cy(self) -> int:
        """Vertical center of the keyframe lane (bottom band)."""
        return self._hpx - px(LANE_KF_H) // 2

    # ------------------------------------------------------------------
    # Geometry
    # ------------------------------------------------------------------

    def _usable(self) -> tuple[int, int]:
        return self._pad, max(self._pad + 1, self._wpx - self._pad)

    def _view(self) -> tuple[float, float]:
        """The visible time range: the zoom window, or the full range."""
        v0 = self._view_from if self._view_from is not None else self._from
        v1 = self._view_to if self._view_to is not None else self._to
        return v0, v1

    def _x_for(self, value: float) -> int:
        x0, x1 = self._usable()
        v0, v1 = self._view()
        span = max(1e-9, v1 - v0)
        frac = min(1.0, max(0.0, (value - v0) / span))
        return round(x0 + frac * (x1 - x0))

    def _time_at(self, x: int) -> float:
        """Un-rounded pixel→time mapping (zoom anchoring needs full precision)."""
        x0, x1 = self._usable()
        v0, v1 = self._view()
        frac = min(1.0, max(0.0, (x - x0) / max(1, x1 - x0)))
        return v0 + frac * (v1 - v0)

    def _value_at(self, x: int) -> float:
        return round(self._time_at(x), 2)  # matches the old resolution=0.01

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _on_resize(self, event):
        self._wpx = event.width
        self._hpx = event.height
        self._redraw()

    def _frame_grid_columns(self, x0: int, x1: int, v0: float, v1: float):
        """Frame-grid geometry when zoomed far enough to separate frames.

        Returns {"cells": [(x0, x1, even), ...], "hairlines": [x, ...],
        "seconds": [x, ...]} or None when frames are too dense / fps unknown.
        """
        if not self._fps:
            return None
        span = max(1e-9, v1 - v0)
        px_per_frame = (x1 - x0) / (span * self._fps)
        if px_per_frame < 6:
            return None

        cells = []
        hairlines = []
        seconds = []
        i0 = math.floor(v0 * self._fps)
        i1 = math.ceil(v1 * self._fps)
        second_step = max(1, round(self._fps))
        for i in range(i0, i1 + 1):
            t = i / self._fps
            fx = self._x_for(t)
            if x0 <= fx <= x1:
                if i % second_step == 0:
                    seconds.append(fx)
                else:
                    hairlines.append(fx)
            fx_next = self._x_for((i + 1) / self._fps)
            c0, c1 = max(x0, fx), min(x1, fx_next)
            if c1 > c0:
                cells.append((c0, c1, i % 2 == 0))
        return {"cells": cells, "hairlines": hairlines, "seconds": seconds}

    def _set_hover(self, value):
        self._hover = value
        if not value:
            self._kf_hover_index = None
            self._trim_hover_kind = None
        self._redraw()

    # -- tier 1: composed base (PIL, cached one-deep) -------------------

    def _base_cache_key(self):
        v0, v1 = self._view()
        return (self._wpx, self._hpx, round(v0, 6), round(v1, 6),
                self._data_gen, self._fps)

    def _ensure_base(self) -> Image.Image:
        key = self._base_cache_key()
        if key == self._base_key and self._base_img is not None:
            return self._base_img
        self._base_img = self._compose_base()
        self._base_key = key
        return self._base_img

    def _compose_base(self) -> Image.Image:
        """Everything static per view: lane wells, frame grid, (later:
        filmstrip tiles + tinted waveforms). Never called from the 10 Hz
        var-write path — only when the cache key changes."""
        img = Image.new("RGB", (self._wpx, self._hpx), self.behind)
        draw = ImageDraw.Draw(img)
        x0, x1 = self._usable()
        v0, v1 = self._view()
        ruler_top, ruler_bot = self._ruler_top(), self._ruler_bot()
        film_top, film_bot = self._film_top(), self._film_bot()
        audio_bot = self._audio_bot()

        # Ruler band: the scrub track.
        draw.rectangle([x0, ruler_top, x1, ruler_bot - 1],
                       fill=theme.SEEK_TRACK, outline=theme.PANEL_BORDER_DIM)

        # Filmstrip well + slotted tiles.
        draw.rectangle([x0, film_top + 1, x1, film_bot - 1],
                       fill=theme.WELL_FILL)
        if self._filmstrip is not None and self._filmstrip_count > 0:
            self._paste_filmstrip(img, x0, x1, film_top + 1, film_bot - 1)

        # Audio band: one tinted waveform lane per roster row (first four;
        # a "+N" tag marks the rest — informational, not interactive).
        if film_bot < audio_bot:
            draw.rectangle([x0, film_bot + 1, x1, audio_bot - 1],
                           fill=theme.SEEK_TRACK)
            self._paste_waveforms(img, draw, x0, x1, v0, v1,
                                  film_bot + 1, audio_bot - 1)

        # Keyframe-lane separator hairline.
        draw.line([(x0, audio_bot), (x1, audio_bot)],
                  fill=theme.PANEL_BORDER_DIM)

        # Zoomed-in frame grid: cells + hairlines live in the ruler band;
        # second-ticks extend down the strip as faint landmarks.
        frame_lines = self._frame_grid_columns(x0, x1, v0, v1)
        if frame_lines is not None:
            for fx0, fx1, even in frame_lines["cells"]:
                if even:
                    draw.rectangle([fx0, ruler_top + 1, fx1, ruler_bot - 2],
                                   fill=theme.SEEK_CELL)
            for fx in frame_lines["hairlines"]:
                draw.line([(fx, ruler_top + 1), (fx, ruler_bot - 2)],
                          fill=theme.PANEL_BORDER_DIM)
            for fx in frame_lines["seconds"]:
                draw.line([(fx, ruler_top), (fx, ruler_bot - 1)],
                          fill=theme.ACCENT_DEEP)
                draw.line([(fx, film_top), (fx, audio_bot)],
                          fill=theme.PANEL_BORDER_DIM)

        return img

    def _paste_filmstrip(self, img: Image.Image, x0: int, x1: int,
                         top: int, bot: int):
        """Slot-fill the filmstrip lane: walk the visible x-range in steps of
        one tile-aspect slot, pasting the nearest-in-time tile per slot.
        Never stretches — zooming just re-slots from the same tiles (past the
        tile temporal resolution neighbours repeat, under the frame grid)."""
        strip = self._filmstrip
        n = self._filmstrip_count
        lane_h = bot - top
        total = self._to - self._from
        if lane_h <= 2 or total <= 0:
            return
        tile_w_src = strip.width // n
        tile_h_src = strip.height
        if tile_w_src <= 0 or tile_h_src <= 0:
            return
        slot_w = max(px(8), round(lane_h * tile_w_src / tile_h_src))

        scaled_cache: dict[int, Image.Image] = {}
        sx = x0
        while sx < x1:
            t = self._time_at(sx + slot_w // 2)
            t = min(t, self._to - 1e-6)  # VFR tail-tile guard
            idx = min(n - 1, max(0, int((t - self._from) / total * n)))
            tile = scaled_cache.get(idx)
            if tile is None:
                tile = strip.crop((idx * tile_w_src, 0,
                                   (idx + 1) * tile_w_src, tile_h_src))
                tile = tile.convert("RGB").resize((slot_w, lane_h), Image.LANCZOS)
                scaled_cache[idx] = tile
            sw = min(slot_w, x1 - sx)
            if sw < slot_w:
                tile = tile.crop((0, 0, sw, lane_h))
            img.paste(tile, (sx, top))
            sx += slot_w

    _WAVE_TINTS = {
        # state -> (theme color attr, alpha multiplier)
        "normal": ("WAVE", 1.0),
        "dim": ("TEXT_DIM", 0.5),
        "solo": ("ACCENT", 1.0),
    }

    def _paste_waveforms(self, img: Image.Image, draw, x0: int, x1: int,
                         v0: float, v1: float, top: int, bot: int):
        """Divide the audio band among the first four rows and composite
        each row's waveform: crop the visible time-fraction of the wide
        white-on-transparent source, scale to the lane rect, and use its
        alpha as a mask for a mix-state colored fill."""
        total = self._to - self._from
        n = len(self._waveforms)
        if n <= 0 or total <= 0:
            return
        shown = min(n, 4)
        band_h = bot - top
        lane_h = band_h // shown
        if lane_h < 4:
            return
        src_x0 = (v0 - self._from) / total
        src_x1 = (v1 - self._from) / total

        for row in range(shown):
            wave = self._waveforms[row]
            lane_top = top + row * lane_h
            lane_bot = lane_top + lane_h - 1
            if row > 0:
                draw.line([(x0, lane_top), (x1, lane_top)],
                          fill=theme.PANEL_BORDER_DIM)
            if wave is None:
                continue
            state = (self._wave_states[row]
                     if row < len(self._wave_states) else "normal")
            color_attr, alpha_mul = self._WAVE_TINTS.get(
                state, self._WAVE_TINTS["normal"])
            color = getattr(theme, color_attr)

            cx0 = int(src_x0 * wave.width)
            cx1 = max(cx0 + 1, int(src_x1 * wave.width))
            crop = wave.crop((cx0, 0, cx1, wave.height))
            crop = crop.resize((max(1, x1 - x0), max(2, lane_bot - lane_top - 1)),
                               Image.BILINEAR)
            mask = crop.getchannel("A") if crop.mode == "RGBA" else None
            if mask is None:
                continue
            if alpha_mul < 1.0:
                mask = mask.point(lambda a: int(a * alpha_mul))
            fill = Image.new("RGB", crop.size, color)
            img.paste(fill, (x0, lane_top + 1), mask)

        if n > shown:
            draw.text((x1 - px(24), bot - px(10)), f"+{n - shown}",
                      fill=theme.TEXT_DIM)

    # -- tier 2: display PhotoImage (base + trim dimming, cached) --------

    def _trim_exclusion_ranges(self):
        """Pixel x-ranges cut away by trim, clipped to the strip. Empty
        tuple when trim is off (the whole strip is kept)."""
        if self._trim_start is None and self._trim_end is None:
            return ()
        x0, x1 = self._usable()
        tx0 = self._x_for(self._trim_start) if self._trim_start is not None else x0
        tx1 = self._x_for(self._trim_end) if self._trim_end is not None else x1
        ranges = []
        if tx0 > x0:
            ranges.append((x0, tx0))
        if tx1 < x1:
            ranges.append((tx1, x1))
        return tuple(ranges)

    def _ensure_display(self) -> ImageTk.PhotoImage:
        base = self._ensure_base()
        exclusions = self._trim_exclusion_ranges()
        key = (self._base_key, exclusions)
        if key == self._display_key and self._display_photo is not None:
            return self._display_photo
        if exclusions:
            img = base.copy()
            top, bot = self._ruler_top(), self._audio_bot()
            for rx0, rx1 in exclusions:
                if rx1 <= rx0:
                    continue
                box = (rx0, top, rx1, bot)
                region = img.crop(box)
                img.paste(ImageEnhance.Brightness(region).enhance(0.4), box)
        else:
            img = base
        self._display_photo = ImageTk.PhotoImage(img)
        self._display_key = key
        return self._display_photo

    # -- tier 3: dynamic items (the 10 Hz path — no PIL work) ------------

    def _redraw(self):
        if self._wpx <= 2:
            return
        self.delete("all")
        sk = skin.get_skin()
        cy = self._scrub_cy()
        x0, x1 = self._usable()
        ruler_top, ruler_bot = self._ruler_top(), self._ruler_bot()

        try:
            value = float(self._variable.get())
        except Exception:
            value = 0.0
        hx = self._x_for(value)

        v0, v1 = self._view()

        # Composed lanes + trim exclusion dimming (cached: no PIL work
        # unless view/size/data or the trim range changed).
        self.create_image(0, 0, image=self._ensure_display(), anchor="nw")

        # Elapsed fill across the ruler band.
        fill = theme.ACCENT_DEEP if self._state == tk.NORMAL else theme.TEXT_DIM
        self.create_rectangle(x0 + 1, ruler_top + 1, max(x0 + 1, hx), ruler_bot - 2,
                              fill=fill, width=0)

        # STARTING scanner: a bright segment ping-ponging around the
        # playhead in the ruler band while the engine spins up.
        if self._starting:
            span = px(40)
            seg = px(14)
            period = 20  # ticks per one-way pass
            ph = self._starting_phase % (2 * period)
            frac = ph / period
            if frac > 1.0:
                frac = 2.0 - frac
            cx = hx - span + round(2 * span * frac)
            sx0 = max(x0, cx - seg // 2)
            sx1 = min(x1, cx + seg // 2)
            if sx1 > sx0:
                self.create_rectangle(sx0, ruler_top + 1, sx1, ruler_bot - 2,
                                      fill=theme.ACCENT, width=0)

        # Cached-range bar: bright segments along the ruler's bottom edge
        # showing which parts seek instantly from the mpv RAM cache.
        if self._cache_ranges:
            cache_top = ruler_bot - px(2)
            for rs, re_ in self._cache_ranges:
                if re_ < v0 or rs > v1:
                    continue
                cx0 = self._x_for(max(rs, v0))
                cx1 = self._x_for(min(re_, v1))
                if cx1 > cx0:
                    self.create_rectangle(cx0, cache_top, cx1, ruler_bot - 1,
                                          fill=theme.BAR_EDGE, outline="")

        # Zoom view indicator: where the visible window sits in the full clip.
        if self._view_from is not None:
            full_span = max(1e-9, self._to - self._from)
            ix0 = round(x0 + (v0 - self._from) / full_span * (x1 - x0))
            ix1 = round(x0 + (v1 - self._from) / full_span * (x1 - x0))
            self.create_rectangle(x0, 0, x1, px(2), fill=theme.SEEK_TRACK, outline="")
            self.create_rectangle(ix0, 0, max(ix0 + px(2), ix1), px(2),
                                  fill=theme.ACCENT_DEEP, outline="")

        # Fat trim handles spanning the strip body BELOW the ruler (the ruler
        # is a dedicated scrub lane — grabs match, see _bracket_at), sitting
        # OUTSIDE the kept region (over the dimmed exclusion) so they never
        # cover kept frames. Culled outside a zoomed view — a clamped handle
        # at the edge would read as a handle AT the edge.
        handle_w = px(10)
        handle_h = self._audio_bot() - self._film_top()
        handle_cy = self._film_top() + handle_h // 2
        for kind, t, anchor in (("start", self._trim_start, "e"),
                                ("end", self._trim_end, "w")):
            if t is None or not (v0 <= t <= v1):
                continue
            if self._trim_drag_kind == kind:
                tstate = "drag"
            elif self._trim_hover_kind == kind:
                tstate = "hover"
            else:
                tstate = "normal"
            self.create_image(self._x_for(t), handle_cy,
                              image=sk.get("trim_handle", w=handle_w, h=handle_h,
                                           kind=kind, state=tstate, behind=self.behind),
                              anchor=anchor)

        # Playhead: full-height hairline over the strip + grab handle in the
        # ruler band (culled when scrolled out of a zoomed view).
        if v0 <= value <= v1:
            hstate = "disabled" if self._state == tk.DISABLED else (
                "drag" if self._dragging else ("hover" if self._hover else "normal"))
            line_fill = theme.ACCENT if self._state == tk.NORMAL else theme.TEXT_DIM
            self.create_line(hx, ruler_top, hx, self._hpx - px(1),
                             fill=line_fill, width=max(1, px(1)))
            self.create_image(hx, cy, image=sk.get(
                "handle", w=px(10), h=px(18), state=hstate, behind=self.behind))

        # Keyframe diamonds in the bottom lane (culled outside the view).
        if self._keyframes:
            kf_cy = self._kf_cy()
            kf_h = px(12)
            for i, t in enumerate(self._keyframes):
                if not (v0 <= t <= v1):
                    continue
                if i == self._kf_drag_index:
                    state = "drag"
                elif i == self._kf_hover_index:
                    state = "hover"
                elif self._kf_inert:
                    state = "inert"
                elif abs(self._x_for(t) - hx) <= px(3):
                    state = "active"
                else:
                    state = "normal"
                self.create_image(self._x_for(t), kf_cy,
                                  image=sk.get("keyframe", h=kf_h, state=state, behind=self.behind))

        # Export progress: fill sweeping the trimmed region in the ruler, a
        # bright full-height sweep line, and an honest per-attempt counter.
        # Drawn last so the counter text stays on top of every lane.
        if self._export_progress is not None:
            pct, attempt, attempts_max = self._export_progress
            r0 = self._trim_start if self._trim_start is not None else self._from
            r1 = self._trim_end if self._trim_end is not None else self._to
            if r1 > r0:
                sweep_t = r0 + (pct / 100.0) * (r1 - r0)
                fx0 = self._x_for(max(r0, v0))
                fx1 = self._x_for(min(sweep_t, v1))
                if sweep_t >= v0 and fx1 > fx0:
                    self.create_rectangle(fx0, ruler_top + 1, fx1, ruler_bot - 2,
                                          fill=theme.ACCENT_DEEP, width=0)
                if v0 <= sweep_t <= v1:
                    sx = self._x_for(sweep_t)
                    self.create_line(sx, ruler_top, sx, self._hpx - px(1),
                                     fill=theme.ACCENT, width=max(1, px(2)))
                    if attempts_max > 1:
                        label = f"ATTEMPT {attempt}/{attempts_max}"
                        text_y = (self._film_top() + self._film_bot()) // 2
                        # Flip sides near the right edge so it never clips.
                        if sx > (x0 + x1) // 2:
                            self.create_text(sx - px(8), text_y, text=label,
                                             anchor="e", font=theme.font_small(),
                                             fill=theme.TEXT_BRIGHT)
                        else:
                            self.create_text(sx + px(8), text_y, text=label,
                                             anchor="w", font=theme.font_small(),
                                             fill=theme.TEXT_BRIGHT)

    def _on_var_write(self, *_):
        if self._suspend_var_sync:
            return
        self._redraw()
        # tk.Scale invokes its command when the linked variable changes;
        # on_seek_drag ignores it unless the user is actively seeking.
        if self._command is not None:
            try:
                self._command(f"{float(self._variable.get())}")
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Interaction
    # ------------------------------------------------------------------

    def _apply_drag(self, x):
        value = self._value_at(x)
        self._suspend_var_sync = True
        try:
            self._variable.set(value)
        finally:
            self._suspend_var_sync = False
        self._redraw()
        if self._command is not None:
            self._command(f"{value}")

    def _bracket_at(self, x: int, y: int) -> str | None:
        """Which trim handle, if any, sits under (x, y) (within a grab
        margin). Returns "start"/"end"/None. Grabs live in the strip body
        only — the ruler band above is a dedicated always-seek scrub lane,
        and the keyframe lane below belongs to the diamonds — so clicking
        the ruler seeks precisely even on top of a bracket. Only set handles
        are grabbable; handles scrolled outside a zoomed view are not (they
        aren't drawn either)."""
        if not (self._ruler_bot() <= y < self._audio_bot() - px(2)):
            return None
        margin = px(12)
        v0, v1 = self._view()
        best_kind = None
        best_dist = margin + 1
        if self._trim_start is not None and v0 <= self._trim_start <= v1:
            d = abs(x - self._x_for(self._trim_start))
            if d < best_dist:
                best_kind, best_dist = "start", d
        if self._trim_end is not None and v0 <= self._trim_end <= v1:
            d = abs(x - self._x_for(self._trim_end))
            if d < best_dist:
                best_kind, best_dist = "end", d
        return best_kind

    def _keyframe_at(self, x: int, y: int) -> int | None:
        """Index of the keyframe diamond under (x, y), or None. Restricted to
        the bottom lane so it never competes with playhead/trim grabs above.
        Diamonds scrolled outside a zoomed view are not grabbable."""
        if not self._keyframes:
            return None
        if y < self._audio_bot() - px(2):
            return None
        margin = px(8)
        v0, v1 = self._view()
        best_index = None
        best_dist = margin + 1
        for i, t in enumerate(self._keyframes):
            if not (v0 <= t <= v1):
                continue
            d = abs(x - self._x_for(t))
            if d < best_dist:
                best_index, best_dist = i, d
        return best_index

    def _apply_keyframe_drag(self, x):
        index = self._kf_drag_index
        if index is None:
            return
        value = self._value_at(x)
        # Clamp between neighbours so a drag can't reorder the keyframes
        # (mirrors CropTrack.retime on the controller side).
        if index > 0:
            value = max(value, self._keyframes[index - 1] + 0.05)
        if index < len(self._keyframes) - 1:
            value = min(value, self._keyframes[index + 1] - 0.05)
        value = min(self._to, max(self._from, value))
        self._keyframes[index] = value
        self._redraw()
        for callback in self._kf_drag_callbacks:
            callback(index, value)

    def _apply_trim_drag(self, x):
        kind = self._trim_drag_kind
        value = self._value_at(x)

        # Keep start < end so the kept range never inverts.
        if kind == "start" and self._trim_end is not None:
            value = min(value, max(self._from, self._trim_end - 0.05))
        elif kind == "end" and self._trim_start is not None:
            value = max(value, min(self._to, self._trim_start + 0.05))
        value = min(self._to, max(self._from, value))

        if kind == "start":
            self._trim_start = value
        else:
            self._trim_end = value
        self._redraw()

        for callback in self._trim_change_callbacks:
            callback(kind, value)

    def _on_press(self, event):
        if self._state != tk.NORMAL:
            return

        # Grabbing a trim bracket takes priority over moving the playhead.
        # The grab records an offset instead of snapping the bracket to the
        # cursor — nothing moves until the drag passes a small threshold, so
        # a plain click can't shift the trim (it seeks to it on release).
        kind = self._bracket_at(event.x, event.y)
        if kind is not None:
            t = self._trim_start if kind == "start" else self._trim_end
            self._trim_drag_kind = kind
            self._trim_press_x = event.x
            self._trim_grab_dx = event.x - self._x_for(t)
            self._trim_moved = False
            self._redraw()
            return

        # Keyframe diamonds (lower lane) come next: grab to retime or click to
        # seek. They sit below the scrubber, so this only wins in that band.
        kf_index = self._keyframe_at(event.x, event.y)
        if kf_index is not None:
            self._kf_drag_index = kf_index
            self._kf_press_x = event.x
            self._kf_moved = False
            self._redraw()
            for callback in self._kf_press_callbacks:
                callback(kf_index)
            return

        # Press hooks run first so user_is_seeking is set before any value
        # updates fire the command (mirrors the old bind order).
        for callback in self._press_callbacks:
            callback(event)
        self._dragging = True
        self._apply_drag(event.x)

    def _on_right_press(self, event):
        if self._state != tk.NORMAL:
            return
        index = self._keyframe_at(event.x, event.y)
        if index is None:
            return
        for callback in self._kf_delete_callbacks:
            callback(index)

    def _on_motion(self, event):
        if self._state != tk.NORMAL or self._trim_drag_kind is not None or self._kf_drag_index is not None:
            return
        bracket = self._bracket_at(event.x, event.y)
        if bracket is not None:
            cursor = "sb_h_double_arrow"
        elif self._keyframe_at(event.x, event.y) is not None:
            cursor = "hand2"
        else:
            cursor = ""
        if bracket != self._trim_hover_kind:
            self._trim_hover_kind = bracket
            self._redraw()
        hover = self._keyframe_at(event.x, event.y)
        if hover != self._kf_hover_index:
            self._kf_hover_index = hover
            self._redraw()
        if cursor != self._cursor:
            self._cursor = cursor
            try:
                # Bypass the overridden configure (which redraws) — just set the
                # cursor on the underlying canvas.
                tk.Canvas.configure(self, cursor=cursor)
            except Exception:
                pass

    def _on_drag(self, event):
        if self._state != tk.NORMAL:
            return
        if self._trim_drag_kind is not None:
            if (not self._trim_moved and self._trim_press_x is not None
                    and abs(event.x - self._trim_press_x) > px(3)):
                self._trim_moved = True
            if self._trim_moved:
                self._apply_trim_drag(event.x - self._trim_grab_dx)
        elif self._kf_drag_index is not None:
            if self._kf_press_x is not None and abs(event.x - self._kf_press_x) > px(3):
                self._kf_moved = True
            if self._kf_moved:
                self._apply_keyframe_drag(event.x)
        elif self._dragging:
            self._apply_drag(event.x)

    def _on_release(self, event):
        if self._trim_drag_kind is not None:
            kind = self._trim_drag_kind
            moved = self._trim_moved
            self._trim_drag_kind = None
            self._trim_press_x = None
            self._trim_moved = False
            self._redraw()
            if moved:
                for callback in self._trim_commit_callbacks:
                    callback(kind)
            else:
                # Click without drag: seek the playhead to this trim time.
                t = self._trim_start if kind == "start" else self._trim_end
                if t is not None:
                    for callback in self._seek_request_callbacks:
                        callback(t)
            return
        if self._kf_drag_index is not None:
            index = self._kf_drag_index
            moved = self._kf_moved
            value = self._keyframes[index] if 0 <= index < len(self._keyframes) else 0.0
            self._kf_drag_index = None
            self._kf_press_x = None
            self._kf_moved = False
            self._redraw()
            if moved:
                for callback in self._kf_commit_callbacks:
                    callback(index, value)
            else:
                for callback in self._kf_click_callbacks:
                    callback(index)
            return
        if self._state != tk.NORMAL:
            self._dragging = False
            return
        self._dragging = False
        self._redraw()
        for callback in self._release_callbacks:
            callback(event)
