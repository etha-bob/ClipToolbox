"""CropBoxCanvas — the interactive crop/zoom rectangle editor.

Sits over the preview frame while crop-edit mode is active. It shows the
(uncropped) still of the current frame and a draggable rectangle that maps to
source pixels. Because the live FFplay window paints over Tk, editing always
happens against a concealed paused still — the controller supplies that image
via set_image().

Coordinate spaces:
  - source pixels: what the crop rect is stored in and what the ffmpeg filter
    consumes; set via set_source()/set_rect().
  - canvas pixels: physical device pixels (the process is system-DPI aware, so
    Tk mouse events are already physical). A single contain-fit transform maps
    between the two; only handle/margin sizes go through px().

Corner drags keep the source aspect ratio by default (an undistorted zoom);
hold Shift to stretch freely. Edge handles always stretch a single axis.
"""
import tkinter as tk

from PIL import Image, ImageTk

from cliptoolbox.constants import CROP_MIN_SIZE
from cliptoolbox.core import motion
from cliptoolbox.ui import theme, widgets
from cliptoolbox.ui.theme import px

_CORNERS = ("nw", "ne", "se", "sw")
_EDGES = ("n", "e", "s", "w")

_CURSORS = {
    "nw": "size_nw_se", "se": "size_nw_se",
    "ne": "size_ne_sw", "sw": "size_ne_sw",
    "n": "size_ns", "s": "size_ns",
    "e": "size_we", "w": "size_we",
    "move": "fleur",
}


class CropBoxCanvas(tk.Canvas):
    def __init__(self, parent, behind="black"):
        super().__init__(parent, highlightthickness=0, bd=0, bg=behind)
        self.behind = behind

        self._src_w = 0
        self._src_h = 0
        self._rect = (0.0, 0.0, 0.0, 0.0)  # source px

        self._source_image: Image.Image | None = None
        self._backdrop_photo: ImageTk.PhotoImage | None = None
        self._backdrop_key: tuple | None = None

        # contain-fit transform (canvas px)
        self._scale = 1.0
        self._ox = 0
        self._oy = 0
        self._cw = 1
        self._ch = 1

        self._drag_handle: str | None = None
        self._press_rect = (0.0, 0.0, 0.0, 0.0)
        self._press_src = (0.0, 0.0)
        self._cursor = ""

        self._change_callbacks = []
        self._commit_callbacks = []

        self.bind("<Configure>", self._on_resize)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Motion>", self._on_motion)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def bind_change(self, callback):
        """callback(rect) fires continuously while the rect is edited."""
        self._change_callbacks.append(callback)

    def bind_commit(self, callback):
        """callback(rect) fires once when an edit drag is released."""
        self._commit_callbacks.append(callback)

    def set_source(self, src_w: int, src_h: int):
        self._src_w = max(1, int(src_w))
        self._src_h = max(1, int(src_h))
        self._recompute_layout()
        self._redraw()

    def set_image(self, image_bytes: bytes | None):
        """Set the backdrop still (JPEG/PNG bytes), or None to clear it."""
        if not image_bytes:
            self._source_image = None
        else:
            try:
                from io import BytesIO

                self._source_image = Image.open(BytesIO(image_bytes)).convert("RGB")
            except Exception:
                self._source_image = None
        self._backdrop_key = None  # force regen
        self._redraw()

    def set_rect(self, x: float, y: float, w: float, h: float):
        self._rect = motion.clamp_rect(x, y, w, h, self._src_w, self._src_h, CROP_MIN_SIZE)
        self._redraw()

    def get_rect(self) -> tuple[float, float, float, float]:
        return self._rect

    def full_frame_rect(self) -> tuple[float, float, float, float]:
        return (0.0, 0.0, float(self._src_w), float(self._src_h))

    # ------------------------------------------------------------------
    # Coordinate transform
    # ------------------------------------------------------------------

    def _recompute_layout(self):
        cw = max(1, self.winfo_width())
        ch = max(1, self.winfo_height())
        self._cw, self._ch = cw, ch
        if self._src_w <= 0 or self._src_h <= 0:
            self._scale, self._ox, self._oy = 1.0, 0, 0
            return
        scale = min(cw / self._src_w, ch / self._src_h)
        self._scale = scale
        dw = self._src_w * scale
        dh = self._src_h * scale
        self._ox = round((cw - dw) / 2)
        self._oy = round((ch - dh) / 2)

    def _to_canvas(self, sx: float, sy: float) -> tuple[int, int]:
        return round(self._ox + sx * self._scale), round(self._oy + sy * self._scale)

    def _to_source(self, cx: float, cy: float) -> tuple[float, float]:
        s = self._scale or 1.0
        return (cx - self._ox) / s, (cy - self._oy) / s

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _on_resize(self, event):
        self._recompute_layout()
        self._redraw()

    def _display_size(self) -> tuple[int, int]:
        return max(1, round(self._src_w * self._scale)), max(1, round(self._src_h * self._scale))

    def _ensure_backdrop(self):
        if self._source_image is None:
            self._backdrop_photo = None
            self._backdrop_key = None
            return
        dw, dh = self._display_size()
        key = (id(self._source_image), dw, dh)
        if key == self._backdrop_key and self._backdrop_photo is not None:
            return
        try:
            resized = self._source_image.resize((dw, dh), Image.LANCZOS)
            self._backdrop_photo = ImageTk.PhotoImage(resized)
            self._backdrop_key = key
        except Exception:
            self._backdrop_photo = None
            self._backdrop_key = None

    def _redraw(self):
        self.delete("all")
        if self._cw <= 2 or self._src_w <= 0:
            return

        self._ensure_backdrop()
        if self._backdrop_photo is not None:
            self.create_image(self._ox, self._oy, image=self._backdrop_photo, anchor="nw")

        rx, ry, rw, rh = self._rect
        cx0, cy0 = self._to_canvas(rx, ry)
        cx1, cy1 = self._to_canvas(rx + rw, ry + rh)

        # Dim everything outside the crop rect (within the displayed frame).
        dw, dh = self._display_size()
        ix0, iy0 = self._ox, self._oy
        ix1, iy1 = self._ox + dw, self._oy + dh
        for x0, y0, x1, y1 in (
            (ix0, iy0, ix1, cy0),   # top
            (ix0, cy1, ix1, iy1),   # bottom
            (ix0, cy0, cx0, cy1),   # left
            (cx1, cy0, ix1, cy1),   # right
        ):
            if x1 > x0 and y1 > y0:
                self.create_rectangle(x0, y0, x1, y1, fill="black", stipple="gray50", outline="")

        # Crop rectangle outline + thirds guides.
        self.create_rectangle(cx0, cy0, cx1, cy1, outline=theme.ACCENT, width=max(1, px(1)))
        for k in (1, 2):
            gx = cx0 + (cx1 - cx0) * k // 3
            gy = cy0 + (cy1 - cy0) * k // 3
            self.create_line(gx, cy0, gx, cy1, fill=theme.ACCENT_DEEP, width=1)
            self.create_line(cx0, gy, cx1, gy, fill=theme.ACCENT_DEEP, width=1)

        widgets.draw_corner_brackets(self, cx0, cy0, cx1, cy1, color=theme.TEXT_BRIGHT)

        # Edge handle ticks.
        for hx, hy in self._handle_points().values():
            r = px(3)
            self.create_rectangle(hx - r, hy - r, hx + r, hy + r,
                                  fill=theme.ACCENT, outline=theme.TEXT_BRIGHT)

        # Size readout.
        label = f"{int(round(rw))}×{int(round(rh))}"
        ty = cy0 - px(10)
        anchor = "sw"
        if ty < self._oy + px(4):
            ty = cy0 + px(10)
            anchor = "nw"
        self.create_text(cx0 + px(2), ty, text=label, anchor=anchor,
                         fill=theme.TEXT_BRIGHT, font=theme.font_small())

    def _handle_points(self) -> dict:
        rx, ry, rw, rh = self._rect
        x0, y0 = self._to_canvas(rx, ry)
        x1, y1 = self._to_canvas(rx + rw, ry + rh)
        mx, my = (x0 + x1) // 2, (y0 + y1) // 2
        return {
            "nw": (x0, y0), "ne": (x1, y0), "se": (x1, y1), "sw": (x0, y1),
            "n": (mx, y0), "e": (x1, my), "s": (mx, y1), "w": (x0, my),
        }

    # ------------------------------------------------------------------
    # Hit-testing
    # ------------------------------------------------------------------

    def _handle_at(self, x: int, y: int) -> str | None:
        margin = px(10)
        points = self._handle_points()
        # Corners take priority over edges (they overlap at the rect corners).
        best = None
        best_dist = margin + 1
        for name in _CORNERS + _EDGES:
            hx, hy = points[name]
            d = max(abs(x - hx), abs(y - hy))
            if d < best_dist:
                best, best_dist = name, d
        if best is not None:
            return best
        # Interior => move.
        rx, ry, rw, rh = self._rect
        x0, y0 = self._to_canvas(rx, ry)
        x1, y1 = self._to_canvas(rx + rw, ry + rh)
        if x0 <= x <= x1 and y0 <= y <= y1:
            return "move"
        return None

    # ------------------------------------------------------------------
    # Interaction
    # ------------------------------------------------------------------

    def _on_motion(self, event):
        if self._drag_handle is not None:
            return
        handle = self._handle_at(event.x, event.y)
        cursor = _CURSORS.get(handle, "")
        if cursor != self._cursor:
            self._cursor = cursor
            try:
                tk.Canvas.configure(self, cursor=cursor)
            except Exception:
                pass

    def _on_press(self, event):
        handle = self._handle_at(event.x, event.y)
        if handle is None:
            return
        self._drag_handle = handle
        self._press_rect = self._rect
        self._press_src = self._to_source(event.x, event.y)

    def _on_drag(self, event):
        if self._drag_handle is None:
            return
        shift = bool(event.state & 0x0001)
        mx, my = self._to_source(event.x, event.y)
        self._rect = self._compute_drag(self._drag_handle, mx, my, shift)
        self._redraw()
        for callback in self._change_callbacks:
            callback(self._rect)

    def _on_release(self, event):
        if self._drag_handle is None:
            return
        self._drag_handle = None
        for callback in self._commit_callbacks:
            callback(self._rect)

    def _compute_drag(self, handle, mx, my, shift):
        rx, ry, rw, rh = self._press_rect
        left, top, right, bottom = rx, ry, rx + rw, ry + rh

        if handle == "move":
            px0, py0 = self._press_src
            dx = mx - px0
            dy = my - py0
            return motion.clamp_rect(rx + dx, ry + dy, rw, rh,
                                     self._src_w, self._src_h, CROP_MIN_SIZE)

        if handle in _EDGES:
            if handle == "n":
                top = my
            elif handle == "s":
                bottom = my
            elif handle == "w":
                left = mx
            elif handle == "e":
                right = mx
            nx, ny = min(left, right), min(top, bottom)
            nw, nh = abs(right - left), abs(bottom - top)
            return motion.clamp_rect(nx, ny, nw, nh, self._src_w, self._src_h, CROP_MIN_SIZE)

        # Corner: opposite corner is the fixed anchor.
        anchors = {
            "nw": (right, bottom),
            "ne": (left, bottom),
            "se": (left, top),
            "sw": (right, top),
        }
        ax, ay = anchors[handle]
        w = abs(mx - ax)
        h = abs(my - ay)

        if not shift and self._src_h > 0:
            # Lock to the source aspect ratio so the zoom never distorts.
            ar = self._src_w / self._src_h
            if h <= 1e-6 or (w / max(h, 1e-6)) > ar:
                h = w / ar
            else:
                w = h * ar

        nx = ax - w if handle in ("nw", "sw") else ax
        ny = ay - h if handle in ("nw", "ne") else ay
        return motion.clamp_rect(nx, ny, w, h, self._src_w, self._src_h, CROP_MIN_SIZE)
