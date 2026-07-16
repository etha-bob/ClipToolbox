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

from PIL import Image, ImageDraw, ImageTk

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
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)
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

    def set_keyframes(self, times):
        """Replace the keyframe markers. Empty list hides the lane markers."""
        self._keyframes = sorted(float(t) for t in times)
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

        # Filmstrip well (tiles pasted here from S3 on).
        draw.rectangle([x0, film_top + 1, x1, film_bot - 1],
                       fill=theme.WELL_FILL)

        # Audio band well (waveform lanes from S4 on).
        if film_bot < audio_bot:
            draw.rectangle([x0, film_bot + 1, x1, audio_bot - 1],
                           fill=theme.SEEK_TRACK)

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

    # -- tier 2: display PhotoImage (base + trim dimming, cached) --------

    def _display_cache_key(self):
        return (self._base_key,)

    def _ensure_display(self) -> ImageTk.PhotoImage:
        base = self._ensure_base()
        key = self._display_cache_key()
        if key == self._display_key and self._display_photo is not None:
            return self._display_photo
        self._display_photo = ImageTk.PhotoImage(base)
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

        # Composed lanes (cached: no PIL work unless view/size/data changed).
        self.create_image(0, 0, image=self._ensure_display(), anchor="nw")

        # Kept trim range brightens the ruler between the brackets (interim
        # until S2 swaps it for exclusion-zone dimming in the display tier).
        if self._trim_start is not None or self._trim_end is not None:
            tx0 = self._x_for(self._trim_start) if self._trim_start is not None else x0
            tx1 = self._x_for(self._trim_end) if self._trim_end is not None else x1
            if tx1 > tx0:
                self.create_rectangle(tx0, ruler_top + 1, tx1, ruler_bot - 2,
                                      fill=theme.TRIM_KEEP, outline="")

        # Elapsed fill across the ruler band.
        fill = theme.ACCENT_DEEP if self._state == tk.NORMAL else theme.TEXT_DIM
        self.create_rectangle(x0 + 1, ruler_top + 1, max(x0 + 1, hx), ruler_bot - 2,
                              fill=fill, width=0)

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

        # Trim brackets (culled outside a zoomed view — a clamped flag at the
        # edge would read as a bracket AT the edge).
        bracket_h = px(20)
        if self._trim_start is not None and v0 <= self._trim_start <= v1:
            self.create_image(self._x_for(self._trim_start), cy,
                              image=sk.get("trim_flag", h=bracket_h, kind="start", behind=self.behind),
                              anchor="w")
        if self._trim_end is not None and v0 <= self._trim_end <= v1:
            self.create_image(self._x_for(self._trim_end), cy,
                              image=sk.get("trim_flag", h=bracket_h, kind="end", behind=self.behind),
                              anchor="e")

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
                elif abs(self._x_for(t) - hx) <= px(3):
                    state = "active"
                elif i == self._kf_hover_index:
                    state = "hover"
                else:
                    state = "normal"
                self.create_image(self._x_for(t), kf_cy,
                                  image=sk.get("keyframe", h=kf_h, state=state, behind=self.behind))

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

    def _bracket_at(self, x: int) -> str | None:
        """Which trim bracket, if any, sits under x (within a grab margin).
        Returns "start"/"end"/None. Only set brackets are grabbable; brackets
        scrolled outside a zoomed view are not (they aren't drawn either)."""
        margin = px(9)
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
        kind = self._bracket_at(event.x)
        if kind is not None:
            self._trim_drag_kind = kind
            self._apply_trim_drag(event.x)
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

    def _on_motion(self, event):
        if self._state != tk.NORMAL or self._trim_drag_kind is not None or self._kf_drag_index is not None:
            return
        if self._bracket_at(event.x) is not None:
            cursor = "sb_h_double_arrow"
        elif self._keyframe_at(event.x, event.y) is not None:
            cursor = "hand2"
        else:
            cursor = ""
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
            self._apply_trim_drag(event.x)
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
            self._trim_drag_kind = None
            self._redraw()
            for callback in self._trim_commit_callbacks:
                callback(kind)
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
