"""Pointer-based mouse-wheel routing.

On Windows, Tk delivers <MouseWheel> to the widget with keyboard focus, not
the widget under the cursor. A single bind_all handler resolves the hovered
widget via winfo_containing and walks up the master chain through a
registration table, so wheel behavior follows the pointer like in every
other Windows app.

Shift+wheel dispatches with fine=True (smaller steps). Handlers receive
whole notches; high-resolution wheel deltas are accumulated until they add
up to a notch.
"""
import tkinter as tk

WHEEL_DELTA = 120


class WheelRouter:
    def __init__(self, root: tk.Misc):
        self._root = root
        self._targets: dict[tk.Misc, object] = {}
        self._ctrl_targets: dict[tk.Misc, object] = {}
        self._accumulator = 0
        self._accumulator_target = None
        self._ctrl_accumulator = 0
        self._ctrl_accumulator_target = None
        root.bind_all("<MouseWheel>", self._on_wheel, add="+")
        root.bind_all("<Shift-MouseWheel>", self._on_wheel_fine, add="+")
        # Tk fires only the most specific binding per tag, so registering
        # Control here keeps plain-wheel handlers from double-firing (the
        # same mechanism the Shift binding already relies on).
        root.bind_all("<Control-MouseWheel>", self._on_wheel_ctrl, add="+")

    def register(self, widget: tk.Misc, handler):
        """handler(steps: int, fine: bool) — steps > 0 means wheel up.
        Events on any descendant of `widget` route to it (nearest registered
        ancestor wins)."""
        self._targets[widget] = handler

    def register_ctrl(self, widget: tk.Misc, handler):
        """Ctrl+wheel handler(steps: int, x_widget_px: int) — steps > 0 means
        wheel up; x is the pointer position in the registered widget's own
        physical pixels (for zoom-at-cursor)."""
        self._ctrl_targets[widget] = handler

    def unregister(self, widget: tk.Misc):
        self._targets.pop(widget, None)
        self._ctrl_targets.pop(widget, None)

    def _resolve(self, targets: dict, x_root: int, y_root: int):
        try:
            widget = self._root.winfo_containing(x_root, y_root)
        except Exception:
            return None

        while widget is not None:
            handler = targets.get(widget)
            if handler is not None:
                return widget, handler
            widget = getattr(widget, "master", None)
        return None

    def _dispatch(self, event, fine: bool):
        resolved = self._resolve(self._targets, event.x_root, event.y_root)
        if resolved is None:
            return None
        _, handler = resolved

        # Accumulate sub-notch deltas (precision wheels/touchpads) per target.
        if handler is not self._accumulator_target:
            self._accumulator = 0
            self._accumulator_target = handler

        self._accumulator += event.delta
        steps = int(self._accumulator / WHEEL_DELTA)
        if steps == 0:
            return "break"
        self._accumulator -= steps * WHEEL_DELTA

        try:
            handler(steps, fine)
        except Exception:
            pass
        return "break"

    def _on_wheel(self, event):
        return self._dispatch(event, fine=False)

    def _on_wheel_fine(self, event):
        return self._dispatch(event, fine=True)

    def _on_wheel_ctrl(self, event):
        resolved = self._resolve(self._ctrl_targets, event.x_root, event.y_root)
        if resolved is None:
            return None
        widget, handler = resolved

        if handler is not self._ctrl_accumulator_target:
            self._ctrl_accumulator = 0
            self._ctrl_accumulator_target = handler

        self._ctrl_accumulator += event.delta
        steps = int(self._ctrl_accumulator / WHEEL_DELTA)
        if steps == 0:
            return "break"
        self._ctrl_accumulator -= steps * WHEEL_DELTA

        try:
            # event.x is relative to the focus widget, not the hovered one.
            x_widget = event.x_root - widget.winfo_rootx()
            handler(steps, x_widget)
        except Exception:
            pass
        return "break"
