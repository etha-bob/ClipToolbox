"""In-window Halo-styled dialogs and toasts.

Drop-in equivalents for the tkinter.messagebox calls the app used:

    dialogs.showinfo(title, message)      (non-blocking OK dialog)
    dialogs.showerror(title, message)
    dialogs.showwarning(title, message)
    dialogs.askyesno(title, message) -> bool   (blocking, like messagebox)

Dialogs render as a true 45%-alpha dim overlay (a borderless Toplevel — Tk
widgets are opaque, so in-window dimming is impossible) plus an opaque card
Toplevel holding the Halo-styled panel. Input is grabbed by the card, giving
real modality while the workspace stays visible underneath.

Toasts are non-blocking notifications for success paths (export complete)
with an optional action button (OPEN FOLDER).

Call attach(root) once after the root window exists. All functions must run
on the Tk thread — the app already marshals via ui()/root.after.
"""
import tkinter as tk

from cliptoolbox.ui import theme, widgets
from cliptoolbox.ui.theme import px

_root: tk.Misc | None = None
_open_dialog = None
_queue: list[tuple] = []
_toasts: list[tk.Frame] = []
_toast_margin_bottom = 46  # keeps clear of the legend bar; set_toast_offset overrides

_KIND_COLORS = {
    "info": theme.ACCENT,
    "warning": "#D8A03C",
    "error": theme.ERR_RED,
    "success": theme.OK_GREEN,
    "question": theme.ACCENT,
}

_KIND_TAGS = {
    "info": "NOTICE",
    "warning": "WARNING",
    "error": "ERROR",
    "success": "COMPLETE",
    "question": "CONFIRM",
}


def attach(root: tk.Misc):
    global _root
    _root = root


def set_toast_offset(pixels: int):
    global _toast_margin_bottom
    _toast_margin_bottom = pixels


def a_modal_is_open() -> bool:
    """True while a Halo dialog (info/error/confirm) is grabbing input.

    Lets callers avoid stacking another overlay (e.g. the command palette)
    on top of a modal. Settings uses its own grab, which already blocks
    root key bindings, so it needs no separate flag here."""
    return _open_dialog is not None


# ----------------------------------------------------------------------
# Dialogs
# ----------------------------------------------------------------------


class _DialogWindow:
    def __init__(self, root, kind, title, message, buttons, result_var=None):
        self.root = root
        self.result_var = result_var

        # 45%-alpha dim over the app's client area.
        self.overlay = tk.Toplevel(root)
        self.overlay.overrideredirect(True)
        self.overlay.configure(bg="#000000")
        try:
            self.overlay.attributes("-alpha", 0.45)
        except Exception:
            pass

        # Opaque card window.
        self.card_win = tk.Toplevel(root)
        self.card_win.overrideredirect(True)
        self.card_win.configure(bg=theme.PANEL_BORDER)

        card_w = px(430)
        card = tk.Frame(self.card_win, bg=theme.PANEL_FILL)
        card.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)  # 1px border via bg

        accent = _KIND_COLORS.get(kind, theme.ACCENT)

        strip = tk.Frame(card, bg=theme.TITLE_FILL)
        strip.pack(fill=tk.X)
        tk.Frame(strip, bg=accent, width=px(4)).pack(side=tk.LEFT, fill=tk.Y)
        tk.Label(strip, text=_KIND_TAGS.get(kind, "NOTICE"), font=theme.font_title(12),
                 bg=theme.TITLE_FILL, fg=accent).pack(side=tk.LEFT, padx=(px(10), px(6)), pady=px(5))
        tk.Label(strip, text=title.upper(), font=theme.font_title(13),
                 bg=theme.TITLE_FILL, fg=theme.TITLE_TEXT).pack(side=tk.LEFT, pady=px(5))

        body = tk.Label(card, text=message, font=theme.font_body(),
                        bg=theme.PANEL_FILL, fg=theme.TEXT, justify=tk.LEFT,
                        wraplength=card_w - px(48), anchor="w")
        body.pack(fill=tk.X, padx=px(20), pady=(px(14), px(10)))

        row = tk.Frame(card, bg=theme.PANEL_FILL)
        row.pack(fill=tk.X, padx=px(20), pady=(0, px(16)))

        self._default_value = True
        for i, (label, value, variant) in enumerate(buttons):
            button = widgets.HaloButton(
                row, text=label, variant=variant, behind=theme.PANEL_FILL,
                width=px(110), height=px(30),
                command=lambda v=value: self.close(v),
            )
            button.pack(side=tk.RIGHT, padx=(px(8), 0))
            if i == 0:
                self._default_value = value

        self.card_win.bind("<Return>", lambda e: self.close(self._default_value))
        self.card_win.bind("<Escape>", lambda e: self.close(False if self.result_var is not None else self._default_value))

        self._configure_bind = root.bind("<Configure>", self._reposition, add="+")
        self._card_w = card_w
        self._reposition()

        self.overlay.lift(root)
        self.card_win.lift(self.overlay)
        try:
            self.card_win.grab_set()
        except Exception:
            pass
        self.card_win.focus_force()

    def _reposition(self, _event=None):
        try:
            rx, ry = self.root.winfo_rootx(), self.root.winfo_rooty()
            rw, rh = self.root.winfo_width(), self.root.winfo_height()
            self.overlay.geometry(f"{rw}x{rh}+{rx}+{ry}")
            self.card_win.update_idletasks()
            ch = self.card_win.winfo_reqheight()
            cx = rx + (rw - self._card_w) // 2
            cy = ry + max(0, round(rh * 0.42) - ch // 2)
            self.card_win.geometry(f"{self._card_w}x{ch}+{cx}+{cy}")
        except Exception:
            pass

    def close(self, value):
        global _open_dialog
        try:
            self.card_win.grab_release()
        except Exception:
            pass
        try:
            self.root.unbind("<Configure>", self._configure_bind)
        except Exception:
            pass
        for window in (self.card_win, self.overlay):
            try:
                window.destroy()
            except Exception:
                pass
        if self.result_var is not None:
            self.result_var.set(1 if value else 0)
        _open_dialog = None
        _show_next()


def _show_next():
    global _open_dialog
    if _open_dialog is not None or not _queue:
        return
    kind, title, message, buttons, result_var = _queue.pop(0)
    _open_dialog = _DialogWindow(_root, kind, title, message, buttons, result_var)


def _enqueue(kind, title, message, buttons, result_var=None):
    if _root is None:
        return
    _queue.append((kind, title, message, buttons, result_var))
    _show_next()


def showinfo(title, message):
    _enqueue("info", title, message, [("OK", True, "primary")])


def showerror(title, message):
    _enqueue("error", title, message, [("OK", True, "primary")])


def showwarning(title, message):
    _enqueue("warning", title, message, [("OK", True, "primary")])


def askyesno(title, message) -> bool:
    """Blocking yes/no, mirroring messagebox.askyesno semantics."""
    if _root is None:
        return False
    result = tk.IntVar(master=_root, value=-1)
    _enqueue("question", title, message,
             [("YES", True, "primary"), ("NO", False, "secondary")], result)
    _root.wait_variable(result)
    return bool(result.get())


# ----------------------------------------------------------------------
# Toasts
# ----------------------------------------------------------------------


def toast(title, message=None, kind="info", action_label=None, action=None,
          duration_ms=6000, tag=None):
    if _root is None:
        return

    accent = _KIND_COLORS.get(kind, theme.ACCENT)

    frame = tk.Frame(_root, bg=theme.PANEL_FILL_HI,
                     highlightthickness=1, highlightbackground=theme.PANEL_BORDER)
    # Optional grouping label so callers can supersede their own stale toasts
    # (e.g. a new export dismissing a lingering "Export complete").
    frame._toast_tag = tag
    tk.Frame(frame, bg=accent, width=px(4)).pack(side=tk.LEFT, fill=tk.Y)

    content = tk.Frame(frame, bg=theme.PANEL_FILL_HI)
    content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=px(12), pady=px(8))

    header = tk.Frame(content, bg=theme.PANEL_FILL_HI)
    header.pack(fill=tk.X)
    tk.Label(header, text=_KIND_TAGS.get(kind, "NOTICE"), font=theme.font_title(11),
             bg=theme.PANEL_FILL_HI, fg=accent).pack(side=tk.LEFT)
    tk.Label(header, text=title, font=theme.font_title(12),
             bg=theme.PANEL_FILL_HI, fg=theme.TEXT_BRIGHT).pack(side=tk.LEFT, padx=(px(8), 0))

    if message:
        tk.Label(content, text=message, font=theme.font_small(),
                 bg=theme.PANEL_FILL_HI, fg=theme.TEXT, justify=tk.LEFT,
                 wraplength=px(280), anchor="w").pack(fill=tk.X, pady=(px(2), 0))

    if action_label and action is not None:
        def run_action():
            try:
                action()
            finally:
                _dismiss(frame)

        widgets.HaloButton(content, text=action_label, variant="secondary",
                           behind=theme.PANEL_FILL_HI, height=px(24), width=px(120),
                           font=theme.font_small(11), command=run_action).pack(anchor="e", pady=(px(6), 0))

    close = tk.Label(frame, text="✕", font=theme.font_small(11),
                     bg=theme.PANEL_FILL_HI, fg=theme.TEXT_DIM, cursor="hand2")
    close.pack(side=tk.RIGHT, anchor="ne", padx=px(6), pady=px(4))
    close.bind("<ButtonRelease-1>", lambda e: _dismiss(frame))

    _toasts.append(frame)
    _layout_toasts(animate_last=True)

    if duration_ms:
        frame.after(duration_ms, lambda: _dismiss(frame))


def dismiss_tagged(tag):
    """Dismiss every live toast created with this tag. Safe on the Tk thread."""
    for frame in list(_toasts):
        if getattr(frame, "_toast_tag", None) == tag:
            _dismiss(frame)


def _dismiss(frame):
    if frame in _toasts:
        _toasts.remove(frame)
    try:
        frame.destroy()
    except Exception:
        pass
    _layout_toasts()


def _layout_toasts(animate_last=False):
    y = -px(_toast_margin_bottom)
    for i, frame in enumerate(reversed(_toasts)):
        frame.update_idletasks()
        target_x = -px(14)
        is_newest = animate_last and i == 0
        frame.place(relx=1.0, rely=1.0, x=px(320) if is_newest else target_x,
                    y=y, anchor="se")
        if is_newest:
            _slide(frame, px(320), target_x, y, steps=7)
        y -= frame.winfo_reqheight() + px(8)


def _slide(frame, from_x, to_x, y, steps):
    delta = (to_x - from_x) / steps

    def step(i=1):
        if not frame.winfo_exists():
            return
        frame.place(relx=1.0, rely=1.0, x=round(from_x + delta * i), y=y, anchor="se")
        if i < steps:
            frame.after(16, lambda: step(i + 1))

    step()
