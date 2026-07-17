"""Keyframed crop/zoom ("pan/crop") data model and ffmpeg filter builders.

The model follows Vegas Pro's pan/crop semantics: each keyframe stores a crop
rect in source pixels at an absolute clip time, the rect interpolates
piecewise-linearly between keyframes (holding before the first and after the
last), and at any time the interpolated rect fills the whole output frame.
Output resolution stays constant; a rect whose aspect differs from the
output's stretches by design.

Filter construction picks the cheapest chain that can express the track:

  tier 1  static rect          crop=W:H:X:Y,scale=OW:OH        (plain numbers)
  tier 2  animated position    crop=W:H:x='e(t)':y='e(t)',scale=OW:OH
  tier 3  animated size        scale=w='e(t)':h='e(t)':eval=frame,
                               crop=OW:OH:x='e(t)':y='e(t)'

The split exists because ffmpeg's crop filter evaluates its w/h expressions
only at (re)configuration time while x/y are evaluated per frame, so animated
zoom must come from a per-frame scale (eval=frame) feeding a constant-size
crop. Expression time is the filter clock, which starts at 0 after an input
-ss, so keyframe times are shifted by a caller-supplied offset (trim start
for export, spawn position for preview). Frames with an unknown timestamp
(t = NaN) make every lt() comparison false, which deterministically holds the
last keyframe's value.

This module is tkinter-free and must stay that way. CropTrack mutators
replace the keyframes tuple wholesale instead of mutating it, so the playback
engine's spawn path may safely read a track from a non-UI thread.
"""
from dataclasses import dataclass

MIN_KEYFRAME_GAP = 1e-4  # seconds; upsert/retime keep neighbors at least this far apart

_EXPR_SAFE_CHARS = frozenset("0123456789abcdefghijklmnopqrstuvwxyz(),.*/+-")


@dataclass(frozen=True)
class CropKeyframe:
    t: float
    x: float
    y: float
    w: float
    h: float
    rot: float = 0.0  # degrees; reserved for a future rotation phase, keep 0.0

    def rect(self) -> tuple[float, float, float, float]:
        return (self.x, self.y, self.w, self.h)


class CropTrack:
    """A sorted, immutable-tuple collection of crop keyframes.

    Every mutator builds a fresh tuple and swaps the reference atomically;
    readers snapshot ``self.keyframes`` once and work from the local.
    """

    def __init__(self):
        self.keyframes: tuple[CropKeyframe, ...] = ()
        self.enabled: bool = False

    def upsert(self, kf: CropKeyframe, eps: float) -> int:
        """Replace the keyframe within eps of kf.t, else insert sorted.

        Returns the index of the written keyframe.
        """
        keyframes = [k for k in self.keyframes if abs(k.t - kf.t) > eps]
        keyframes.append(kf)
        keyframes.sort(key=lambda k: k.t)
        self.keyframes = tuple(keyframes)
        return self.keyframes.index(kf)

    def remove_near(self, t: float, eps: float) -> bool:
        index = self.index_near(t, eps)
        if index is None:
            return False
        keyframes = list(self.keyframes)
        del keyframes[index]
        self.keyframes = tuple(keyframes)
        return True

    def retime(self, index: int, new_t: float, eps: float) -> float:
        """Move keyframes[index] to new_t, clamped between its neighbors.

        Returns the time actually applied.
        """
        keyframes = list(self.keyframes)
        low = keyframes[index - 1].t + max(eps, MIN_KEYFRAME_GAP) if index > 0 else 0.0
        high = (
            keyframes[index + 1].t - max(eps, MIN_KEYFRAME_GAP)
            if index + 1 < len(keyframes)
            else float("inf")
        )
        applied = min(max(new_t, low), high)
        applied = max(0.0, applied)
        old = keyframes[index]
        keyframes[index] = CropKeyframe(applied, old.x, old.y, old.w, old.h, old.rot)
        self.keyframes = tuple(keyframes)
        return applied

    def clear(self) -> None:
        self.keyframes = ()

    def index_near(self, t: float, eps: float) -> int | None:
        best: int | None = None
        best_gap = eps
        for i, kf in enumerate(self.keyframes):
            gap = abs(kf.t - t)
            if gap <= best_gap:
                best = i
                best_gap = gap
        return best

    def prev_time(self, t: float, eps: float = 1e-6) -> float | None:
        earlier = [kf.t for kf in self.keyframes if kf.t < t - eps]
        return earlier[-1] if earlier else None

    def next_time(self, t: float, eps: float = 1e-6) -> float | None:
        later = [kf.t for kf in self.keyframes if kf.t > t + eps]
        return later[0] if later else None

    def times(self) -> list[float]:
        return [kf.t for kf in self.keyframes]

    def rect_at(self, t: float) -> tuple[float, float, float, float] | None:
        """Interpolated rect at t; holds outside the keyframe range."""
        keyframes = self.keyframes
        if not keyframes:
            return None
        if t <= keyframes[0].t:
            return keyframes[0].rect()
        if t >= keyframes[-1].t:
            return keyframes[-1].rect()
        for kf0, kf1 in zip(keyframes, keyframes[1:]):
            if t < kf1.t:
                u = (t - kf0.t) / (kf1.t - kf0.t)
                return tuple(a + (b - a) * u for a, b in zip(kf0.rect(), kf1.rect()))
        return keyframes[-1].rect()

    def is_static(self, eps: float = 0.01) -> bool:
        keyframes = self.keyframes
        if len(keyframes) <= 1:
            return True
        first = keyframes[0].rect()
        return all(
            all(abs(a - b) <= eps for a, b in zip(kf.rect(), first)) for kf in keyframes[1:]
        )

    def is_identity(self, src_w: int, src_h: int, eps: float = 0.5) -> bool:
        keyframes = self.keyframes
        if not keyframes:
            return True
        if not self.is_static(eps):
            return False
        x, y, w, h = keyframes[0].rect()
        return (
            abs(x) <= eps and abs(y) <= eps and abs(w - src_w) <= eps and abs(h - src_h) <= eps
        )

    def has_size_animation(self, eps: float = 0.01) -> bool:
        keyframes = self.keyframes
        if len(keyframes) <= 1:
            return False
        return any(
            abs(kf.w - keyframes[0].w) > eps or abs(kf.h - keyframes[0].h) > eps
            for kf in keyframes[1:]
        )


# ============================================================
# Geometry helpers (shared with the crop-editing UI)
# ============================================================

def even_floor(value: int) -> int:
    """Largest even int <= value, floored at 2 (yuv420p-safe dimension)."""
    return max(2, int(value) - (int(value) % 2))


def fit_size(src_w: int, src_h: int, box_w: int, box_h: int) -> tuple[int, int]:
    """Contain-fit src into box keeping aspect, even dims.

    Mirrors scale=W:H:force_original_aspect_ratio=decrease:force_divisible_by=2,
    so a chain built at this size replaces the default preview fit-scale
    without changing the displayed geometry.
    """
    scale = min(box_w / src_w, box_h / src_h)
    return even_floor(int(src_w * scale)), even_floor(int(src_h * scale))


def cap_size(src_w: int, src_h: int, box_w: int, box_h: int) -> tuple[int, int]:
    """Like fit_size but never upscales: src dims scaled DOWN to fit the box,
    or left as-is when already smaller. Matches the compressed export's
    scale=min(box,iw) cap, so building a motion chain at this size and then
    running that cap is a no-op instead of a second resample."""
    scale = min(1.0, box_w / src_w, box_h / src_h)
    return even_floor(int(src_w * scale)), even_floor(int(src_h * scale))


def clamp_rect(
    x: float,
    y: float,
    w: float,
    h: float,
    src_w: int,
    src_h: int,
    min_size: float,
) -> tuple[float, float, float, float]:
    """Clamp a rect inside the source bounds with a minimum size."""
    min_w = min(float(min_size), float(src_w))
    min_h = min(float(min_size), float(src_h))
    w = min(max(float(w), min_w), float(src_w))
    h = min(max(float(h), min_h), float(src_h))
    x = min(max(float(x), 0.0), float(src_w) - w)
    y = min(max(float(y), 0.0), float(src_h) - h)
    return (x, y, w, h)


def _int_rect(
    rect: tuple[float, float, float, float], src_w: int, src_h: int
) -> tuple[int, int, int, int]:
    """Round a rect to ints that still sit inside the source."""
    x, y, w, h = rect
    wi = min(max(1, round(w)), src_w)
    hi = min(max(1, round(h)), src_h)
    xi = min(max(0, round(x)), src_w - wi)
    yi = min(max(0, round(y)), src_h - hi)
    return (xi, yi, wi, hi)


# ============================================================
# ffmpeg expression / chain builders
# ============================================================

# Per-side ceiling for the animated-zoom scale filter's intermediate frame.
# The tier-3 chain scales the whole frame up by out_dim/crop_dim before
# cropping, so a heavily zoomed rect (crop 234px on a 3840px source at 4K
# output) asks scale for a ~63000px-wide frame — ffmpeg rejects anything
# past ~INT_MAX pixels ("Picture size ... is invalid") and OOMs trying to
# allocate it. 32000 keeps each side inside ffmpeg's dimension limit and the
# worst-case area (~1.0 Gpx) under INT_MAX, while still allowing ~16x zoom at
# a 1080p export target — see _clamp_export_zoom.
MAX_SCALE_DIM = 32000


def _clamp_export_zoom(
    keyframes: tuple[CropKeyframe, ...],
    src_w: int,
    src_h: int,
    out_w: int,
    out_h: int,
    max_dim: int = MAX_SCALE_DIM,
) -> tuple[CropKeyframe, ...]:
    """Bump up any crop rect that would make the animated-size scale filter
    exceed max_dim on a side, re-centred and clamped inside the source.

    The intermediate frame is (out_w*src_w/pw) x (out_h*src_h/ph); holding
    each side <= max_dim means pw >= out_w*src_w/max_dim and likewise ph, so
    that's the per-keyframe minimum. Enforced per dimension (not on area) so
    a thin rect can't sneak a tiny width past an adequate area. Rects at a
    sane zoom are untouched; only over-zoom (or a stray near-degenerate
    keyframe) is nudged, trading a hair of zoom for an export that runs."""
    min_w = min(float(src_w), out_w * src_w / max_dim)
    min_h = min(float(src_h), out_h * src_h / max_dim)
    if min_w <= 1.0 and min_h <= 1.0:
        return keyframes
    adjusted = []
    for kf in keyframes:
        w = min(float(src_w), max(kf.w, min_w))
        h = min(float(src_h), max(kf.h, min_h))
        if w == kf.w and h == kf.h:
            adjusted.append(kf)
            continue
        cx, cy = kf.x + kf.w / 2, kf.y + kf.h / 2
        x = min(max(0.0, cx - w / 2), src_w - w)
        y = min(max(0.0, cy - h / 2), src_h - h)
        adjusted.append(CropKeyframe(kf.t, x, y, w, h, kf.rot))
    return tuple(adjusted)


def _fmt(value: float) -> str:
    return f"{value:.4f}"


def _fmt_slope(value: float) -> str:
    return f"{value:.6f}"


def _guard_expr(expr: str) -> str:
    """The quoting convention ('expr' inside one argv element) only survives
    if expressions never contain quotes or option/filter separators."""
    bad = set(expr) - _EXPR_SAFE_CHARS
    if bad:
        raise ValueError(f"unsafe characters in ffmpeg expression: {sorted(bad)!r}")
    return expr


def piecewise_expr(times: list[float], values: list[float], offset: float = 0.0) -> str:
    """Piecewise-linear expression of the filter clock t.

    Keyframe times are shifted by offset (the input -ss); thresholds that go
    negative are harmless because lt(t, negative) is never true for t >= 0
    and the segment formulas remain correct. Holds the first value before the
    first keyframe and the last value after the last (including t = NaN,
    where every lt() is false).
    """
    if len(times) != len(values) or not times:
        raise ValueError("times and values must be equal-length and non-empty")
    shifted = [t - offset for t in times]
    if len(values) == 1:
        return _guard_expr(_fmt(values[0]))
    expr = _fmt(values[-1])
    for i in range(len(shifted) - 2, -1, -1):
        t0, t1 = shifted[i], shifted[i + 1]
        if t1 - t0 <= 0:
            raise ValueError("keyframe times must be strictly increasing")
        slope = (values[i + 1] - values[i]) / (t1 - t0)
        segment = f"({_fmt(values[i])}+{_fmt_slope(slope)}*(t-{_fmt(t0)}))"
        expr = f"if(lt(t,{_fmt(t1)}),{segment},{expr})"
    return _guard_expr(f"if(lt(t,{_fmt(shifted[0])}),{_fmt(values[0])},{expr})")


def build_still_crop_vf(
    rect: tuple[float, float, float, float],
    src_w: int,
    src_h: int,
    out_w: int,
    out_h: int,
) -> str:
    """Static crop chain (plain numbers) for single-frame extracts."""
    x, y, w, h = _int_rect(rect, src_w, src_h)
    return f"crop={w}:{h}:{x}:{y},scale={out_w}:{out_h}"


def build_motion_chain(
    track: CropTrack,
    src_w: int,
    src_h: int,
    out_w: int,
    out_h: int,
    time_offset: float = 0.0,
    scale_flags: str | None = None,
) -> str | None:
    """Video filter chain for the track, or None when nothing needs doing.

    None means "no video filtering required" (track disabled, no keyframes,
    or an identity rect) so callers can keep their unfiltered fast paths —
    including stream-copy export.
    """
    if not track.enabled:
        return None
    keyframes = track.keyframes
    if not keyframes:
        return None
    if track.is_identity(src_w, src_h):
        return None

    if track.is_static():
        x, y, w, h = _int_rect(keyframes[0].rect(), src_w, src_h)
        return f"crop={w}:{h}:{x}:{y},scale={out_w}:{out_h}"

    times = [kf.t for kf in keyframes]

    if not track.has_size_animation():
        # Constant crop size, animated position: crop x/y evaluate per frame.
        # crop-then-scale, so the intermediate never exceeds the source — no
        # zoom clamp needed here.
        px = piecewise_expr(times, [kf.x for kf in keyframes], time_offset)
        py = piecewise_expr(times, [kf.y for kf in keyframes], time_offset)
        _, _, w, h = _int_rect(keyframes[0].rect(), src_w, src_h)
        return f"crop={w}:{h}:x='{px}':y='{py}',scale={out_w}:{out_h}"

    # Animated size: per-frame scale so the rect always maps onto a
    # constant-size crop window. This scales the WHOLE frame up before
    # cropping, so guard against an over-zoomed rect blowing the intermediate
    # past ffmpeg's limits (see _clamp_export_zoom / MAX_SCALE_DIM). Every
    # expression below derives from the clamped set so positions stay
    # consistent with the adjusted sizes.
    keyframes = _clamp_export_zoom(keyframes, src_w, src_h, out_w, out_h)
    times = [kf.t for kf in keyframes]
    px = piecewise_expr(times, [kf.x for kf in keyframes], time_offset)
    py = piecewise_expr(times, [kf.y for kf in keyframes], time_offset)
    # Crop's x/y are derived analytically from the scale factor (out_w*px/pw)
    # rather than from iw/ih, because crop freezes in_w/in_h at configuration
    # time and does not refresh them when scale's eval=frame changes the frame
    # size mid-stream -- reading iw there lands the window in the wrong place
    # for any nonzero pan (verified by tools/spike_motion.py). The analytic
    # form leaves at most a 1 px slack from scale's integer rounding, which
    # crop clamps into range.
    pw = piecewise_expr(times, [kf.w for kf in keyframes], time_offset)
    ph = piecewise_expr(times, [kf.h for kf in keyframes], time_offset)
    flags = f":flags={scale_flags}" if scale_flags else ""
    return (
        f"scale=w='({out_w}*iw)/({pw})':h='({out_h}*ih)/({ph})':eval=frame{flags},"
        f"crop={out_w}:{out_h}:x='({out_w}*({px}))/({pw})':y='({out_h}*({py}))/({ph})'"
    )
