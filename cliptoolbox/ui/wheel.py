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
        self._accumulator = 0
        self._accumulator_target = None
        root.bind_all("<MouseWheel>", self._on_wheel, add="+")
        root.bind_all("<Shift-MouseWheel>", self._on_wheel_fine, add="+")

    def register(self, widget: tk.Misc, handler):
        """handler(steps: int, fine: bool) — steps > 0 means wheel up.
        Events on any descendant of `widget` route to it (nearest registered
        ancestor wins)."""
        self._targets[widget] = handler

    def unregister(self, widget: tk.Misc):
        self._targets.pop(widget, None)

    def _resolve(self, x_root: int, y_root: int):
        try:
            widget = self._root.winfo_containing(x_root, y_root)
        except Exception:
            return None

        while widget is not None:
            handler = self._targets.get(widget)
            if handler is not None:
                return handler
            widget = getattr(widget, "master", None)
        return None

    def _dispatch(self, event, fine: bool):
        handler = self._resolve(event.x_root, event.y_root)
        if handler is None:
            return None

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
