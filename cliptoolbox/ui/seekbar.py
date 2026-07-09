"""HaloSeekbar — the timeline scrubber with integrated trim brackets.

Replaces the old tk.Scale + overlay-label ▼ markers. Keeps the tk.Scale
behavioral subset the preview state machine relies on:

- linked DoubleVar: external .set() on the variable moves the playhead and
  invokes `command` (exactly like tk.Scale), which on_seek_drag ignores while
  `user_is_seeking` is False;
- `command(value_str)` during user drags;
- press/release hooks (bind_press/bind_release) replacing the old
  .bind("<ButtonPress-1>"/"<ButtonRelease-1>") wiring;
- .configure(to=duration).

Trim points render as green/red brackets with the kept range brightened.
"""
import tkinter as tk

from cliptoolbox.ui import skin, theme
from cliptoolbox.ui.theme import px


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

    # ------------------------------------------------------------------
    # Geometry
    # ------------------------------------------------------------------

    def _usable(self) -> tuple[int, int]:
        return self._pad, max(self._pad + 1, self._wpx - self._pad)

    def _x_for(self, value: float) -> int:
        x0, x1 = self._usable()
        span = max(1e-9, self._to - self._from)
        frac = min(1.0, max(0.0, (value - self._from) / span))
        return round(x0 + frac * (x1 - x0))

    def _value_at(self, x: int) -> float:
        x0, x1 = self._usable()
        frac = min(1.0, max(0.0, (x - x0) / max(1, x1 - x0)))
        value = self._from + frac * (self._to - self._from)
        return round(value, 2)  # matches the old resolution=0.01

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _on_resize(self, event):
        self._wpx = event.width
        self._redraw()

    def _set_hover(self, value):
        self._hover = value
        self._redraw()

    def _redraw(self):
        if self._wpx <= 2:
            return
        self.delete("all")
        sk = skin.get_skin()
        cy = self._hpx // 2
        th = px(5)
        x0, x1 = self._usable()

        try:
            value = float(self._variable.get())
        except Exception:
            value = 0.0
        hx = self._x_for(value)

        # Track + elapsed fill (axis-aligned: native rects stay crisp).
        self.create_rectangle(x0, cy - th // 2, x1, cy + th // 2,
                              fill=theme.SEEK_TRACK, outline=theme.PANEL_BORDER_DIM)

        # Kept trim range brightens the track between the brackets.
        if self._trim_start is not None or self._trim_end is not None:
            tx0 = self._x_for(self._trim_start) if self._trim_start is not None else x0
            tx1 = self._x_for(self._trim_end) if self._trim_end is not None else x1
            if tx1 > tx0:
                self.create_rectangle(tx0, cy - th // 2 - px(2), tx1, cy + th // 2 + px(2),
                                      fill="#16405F", outline="")

        fill = theme.ACCENT_DEEP if self._state == tk.NORMAL else theme.TEXT_DIM
        self.create_rectangle(x0, cy - th // 2 + 1, max(x0, hx), cy + th // 2 - 1,
                              fill=fill, width=0)

        # Trim brackets.
        bracket_h = px(22)
        if self._trim_start is not None:
            self.create_image(self._x_for(self._trim_start), cy,
                              image=sk.get("trim_flag", h=bracket_h, kind="start", behind=self.behind),
                              anchor="w")
        if self._trim_end is not None:
            self.create_image(self._x_for(self._trim_end), cy,
                              image=sk.get("trim_flag", h=bracket_h, kind="end", behind=self.behind),
                              anchor="e")

        # Playhead handle.
        hstate = "disabled" if self._state == tk.DISABLED else (
            "drag" if self._dragging else ("hover" if self._hover else "normal"))
        self.create_image(hx, cy, image=sk.get(
            "handle", w=px(10), h=px(22), state=hstate, behind=self.behind))

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
        Returns "start"/"end"/None. Only set brackets are grabbable."""
        margin = px(9)
        best_kind = None
        best_dist = margin + 1
        if self._trim_start is not None:
            d = abs(x - self._x_for(self._trim_start))
            if d < best_dist:
                best_kind, best_dist = "start", d
        if self._trim_end is not None:
            d = abs(x - self._x_for(self._trim_end))
            if d < best_dist:
                best_kind, best_dist = "end", d
        return best_kind

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

        # Press hooks run first so user_is_seeking is set before any value
        # updates fire the command (mirrors the old bind order).
        for callback in self._press_callbacks:
            callback(event)
        self._dragging = True
        self._apply_drag(event.x)

    def _on_motion(self, event):
        if self._state != tk.NORMAL or self._trim_drag_kind is not None:
            return
        cursor = "sb_h_double_arrow" if self._bracket_at(event.x) else ""
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
        if self._state != tk.NORMAL:
            self._dragging = False
            return
        self._dragging = False
        self._redraw()
        for callback in self._release_callbacks:
            callback(event)
