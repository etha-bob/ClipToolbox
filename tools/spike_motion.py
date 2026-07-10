"""Validation spike for the keyframed crop/zoom filter chain.

Proves, against the bundled ffmpeg build, that the tier-3 "zoom/stretch"
chain — per-frame scale (eval=frame) followed by a constant-size crop with
animated x/y — produces a constant-resolution output whose content tracks
the interpolated crop rect over time, and measures throughput for both the
preview-sized graph and a full NVENC export.

The source is four solid color quadrants (red / lime over blue / yellow),
so every extracted frame can be verified programmatically: solid-color
frames when the rect sits inside one quadrant, and quadrant-boundary
positions computed from the same interpolation math otherwise.

    python tools/spike_motion.py [--keep] [--workdir DIR]

Exit code 0 = all checks passed. If the tier-3 chain ever fails here, the
planned fallback is sendcmd driving crop's runtime w/h/x/y commands; build
that variant in this script before touching cliptoolbox/core/motion.py.
"""
import argparse
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image

from cliptoolbox.core import paths

SRC_W, SRC_H = 1920, 1080
FPS = 60
DURATION = 10.0

# (time, (x, y, w, h)) in source pixels.
# 0s: full frame -> 5s: rect inside the red quadrant (2x zoom + pan)
# -> 9s: stretched rect inside the yellow quadrant.
KEYFRAMES = [
    (0.0, (0.0, 0.0, 1920.0, 1080.0)),
    (5.0, (0.0, 0.0, 640.0, 360.0)),
    (9.0, (1280.0, 540.0, 640.0, 540.0)),
]

BOUNDARY_SRC_X = 960.0  # red|lime and blue|yellow vertical boundary
BOUNDARY_SRC_Y = 540.0  # red|blue and lime|yellow horizontal boundary
MARGIN = 25  # px each side of an expected boundary when sampling colors

failures: list[str] = []


def check(label: str, ok: bool, detail: str = ""):
    status = "PASS" if ok else "FAIL"
    suffix = f"  ({detail})" if detail else ""
    print(f"  [{status}] {label}{suffix}")
    if not ok:
        failures.append(label)


def fmt(v: float) -> str:
    return f"{v:.4f}"


def fmt_slope(v: float) -> str:
    return f"{v:.6f}"


def piecewise(points: list[tuple[float, float]], offset: float) -> str:
    """Nested-if piecewise-linear expression of t, holding outside the ends."""
    times = [t - offset for t, _ in points]
    values = [v for _, v in points]
    if len(values) == 1:
        return fmt(values[0])
    expr = fmt(values[-1])
    for i in range(len(times) - 2, -1, -1):
        t0, t1 = times[i], times[i + 1]
        slope = (values[i + 1] - values[i]) / (t1 - t0)
        seg = f"({fmt(values[i])}+{fmt_slope(slope)}*(t-{fmt(t0)}))"
        expr = f"if(lt(t,{fmt(t1)}),{seg},{expr})"
    return f"if(lt(t,{fmt(times[0])}),{fmt(values[0])},{expr})"


def build_tier3_chain(out_w: int, out_h: int, offset: float, flags: str | None) -> str:
    px = piecewise([(t, r[0]) for t, r in KEYFRAMES], offset)
    py = piecewise([(t, r[1]) for t, r in KEYFRAMES], offset)
    pw = piecewise([(t, r[2]) for t, r in KEYFRAMES], offset)
    ph = piecewise([(t, r[3]) for t, r in KEYFRAMES], offset)
    flag_part = f":flags={flags}" if flags else ""
    return (
        f"scale=w='({out_w}*iw)/({pw})':h='({out_h}*ih)/({ph})':eval=frame{flag_part},"
        f"crop={out_w}:{out_h}:x='({out_w}*({px}))/({pw})':y='({out_h}*({py}))/({ph})'"
    )


def rect_at(t: float) -> tuple[float, float, float, float]:
    if t <= KEYFRAMES[0][0]:
        return KEYFRAMES[0][1]
    if t >= KEYFRAMES[-1][0]:
        return KEYFRAMES[-1][1]
    for (t0, r0), (t1, r1) in zip(KEYFRAMES, KEYFRAMES[1:]):
        if t < t1:
            u = (t - t0) / (t1 - t0)
            return tuple(a + (b - a) * u for a, b in zip(r0, r1))
    return KEYFRAMES[-1][1]


def run(cmd: list[str], label: str) -> tuple[float, subprocess.CompletedProcess]:
    start = time.perf_counter()
    proc = subprocess.run(cmd, capture_output=True, text=True)
    elapsed = time.perf_counter() - start
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-8:])
        print(f"  ffmpeg stderr tail for {label}:\n{tail}")
    return elapsed, proc


def dominant(pixel) -> str:
    r, g, b = pixel[:3]
    if r > 150 and g > 150 and b < 100:
        return "yellow"
    if r > 150 and g < 100 and b < 100:
        return "red"
    if g > 150 and r < 100 and b < 100:
        return "lime"
    if b > 150 and r < 100 and g < 100:
        return "blue"
    return f"other({r},{g},{b})"


def extract_frame(video: Path, t: float, dest: Path) -> Image.Image | None:
    _, proc = run(
        [paths.FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
         "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1", str(dest)],
        f"extract@{t}",
    )
    if proc.returncode != 0 or not dest.exists():
        return None
    return Image.open(dest).convert("RGB")


def check_solid(img: Image.Image, color: str, label: str):
    w, h = img.size
    points = [(24, 24), (w - 24, 24), (24, h - 24), (w - 24, h - 24), (w // 2, h // 2)]
    got = [dominant(img.getpixel(p)) for p in points]
    check(label, all(c == color for c in got), f"expected solid {color}, corners+center = {got}")


def check_boundaries(img: Image.Image, clip_t: float, label: str):
    """Verify quadrant boundaries sit where the interpolated rect predicts."""
    w, h = img.size
    rx, ry, rw, rh = rect_at(clip_t)
    xb = (BOUNDARY_SRC_X - rx) / rw * w
    yb = (BOUNDARY_SRC_Y - ry) / rh * h
    ok, details = True, []
    if MARGIN < xb < w - MARGIN:
        left = dominant(img.getpixel((int(xb) - MARGIN, 12)))
        right = dominant(img.getpixel((int(xb) + MARGIN, 12)))
        if (left, right) != ("red", "lime"):
            ok = False
        details.append(f"x-boundary@{xb:.0f}: {left}|{right}")
    if MARGIN < yb < h - MARGIN:
        above = dominant(img.getpixel((12, int(yb) - MARGIN)))
        below = dominant(img.getpixel((12, int(yb) + MARGIN)))
        if (above, below) != ("red", "blue"):
            ok = False
        details.append(f"y-boundary@{yb:.0f}: {above}|{below}")
    check(label, ok, "; ".join(details))


def probe_stream(video: Path) -> dict[str, str]:
    proc = subprocess.run(
        [paths.FFPROBE, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,avg_frame_rate,nb_frames",
         "-of", "default=noprint_wrappers=1", str(video)],
        capture_output=True, text=True,
    )
    info = {}
    for line in proc.stdout.splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            info[key.strip()] = value.strip()
    return info


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workdir", type=Path, default=None)
    parser.add_argument("--keep", action="store_true", help="keep work files")
    args = parser.parse_args()

    if not paths.FFMPEG or not paths.FFPROBE:
        print("ffmpeg/ffprobe not found")
        return 2

    workdir = args.workdir or Path(tempfile.mkdtemp(prefix="spike_motion_"))
    workdir.mkdir(parents=True, exist_ok=True)
    print(f"workdir: {workdir}")

    src = workdir / "spike_src.mp4"
    print("\n== generate quadrant source (1080p60, 10s) ==")
    quad = "color={c}:s=960x540:r=60"
    _, proc = run(
        [paths.FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", quad.format(c="red"),
         "-f", "lavfi", "-i", quad.format(c="lime"),
         "-f", "lavfi", "-i", quad.format(c="blue"),
         "-f", "lavfi", "-i", quad.format(c="yellow"),
         "-filter_complex", "[0][1]hstack[top];[2][3]hstack[bot];[top][bot]vstack[v]",
         "-map", "[v]", "-t", f"{DURATION}",
         "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", str(src)],
        "source",
    )
    check("source generated", proc.returncode == 0 and src.exists())
    if failures:
        return 1

    print("\n== tier-3 export: full res + hevc_nvenc (cq 19) ==")
    out = workdir / "spike_out.mp4"
    chain = build_tier3_chain(SRC_W, SRC_H, 0.0, None) + ",setsar=1"
    print(f"  chain: {chain[:120]}...")
    elapsed, proc = run(
        [paths.FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
         "-i", str(src), "-vf", chain,
         "-c:v", "hevc_nvenc", "-preset", "slow", "-rc", "vbr",
         "-cq", "19", "-b:v", "0", "-pix_fmt", "yuv420p", str(out)],
        "export",
    )
    check("export exit 0", proc.returncode == 0)
    if proc.returncode == 0:
        info = probe_stream(out)
        check("constant 1920x1080", info.get("width") == "1920" and info.get("height") == "1080",
              f"{info.get('width')}x{info.get('height')}")
        check("60 fps kept", info.get("avg_frame_rate") == "60/1", info.get("avg_frame_rate", "?"))
        nb = int(info.get("nb_frames", "0") or 0)
        check("frame count ~600", abs(nb - 600) <= 5, f"nb_frames={nb}")
        check(f"export throughput >= 0.5x realtime", elapsed <= DURATION * 2,
              f"{elapsed:.1f}s for {DURATION:.0f}s of video ({DURATION / elapsed:.2f}x)")

        print("\n== content checks against interpolation math ==")
        for t in (0.02, 2.5, 7.0):
            img = extract_frame(out, t, workdir / f"frame_{t}.png")
            if img is None:
                check(f"frame @ {t}s extracted", False)
                continue
            check_boundaries(img, t, f"boundaries @ t={t}s")
        img = extract_frame(out, 5.0, workdir / "frame_5.png")
        if img:
            check_solid(img, "red", "solid red @ t=5s (rect inside red quadrant)")
        img = extract_frame(out, 9.5, workdir / "frame_9.5.png")
        if img:
            check_solid(img, "yellow", "solid yellow @ t=9.5s (hold after last keyframe)")

    print("\n== trim-offset export: -ss 3 with time_offset=3 ==")
    out_trim = workdir / "spike_trim.mp4"
    chain_trim = build_tier3_chain(SRC_W, SRC_H, 3.0, None) + ",setsar=1"
    _, proc = run(
        [paths.FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
         "-ss", "3.0", "-i", str(src), "-vf", chain_trim,
         "-c:v", "hevc_nvenc", "-preset", "slow", "-rc", "vbr",
         "-cq", "19", "-b:v", "0", "-pix_fmt", "yuv420p", str(out_trim)],
        "trim export",
    )
    check("trim export exit 0", proc.returncode == 0)
    if proc.returncode == 0:
        img = extract_frame(out_trim, 2.0, workdir / "frame_trim_2.png")
        if img:
            check_solid(img, "red", "output t=2s == clip t=5s (solid red)")
        img = extract_frame(out_trim, 4.0, workdir / "frame_trim_4.png")
        if img:
            check_boundaries(img, 7.0, "output t=4s == clip t=7s boundaries")

    print("\n== preview-sized throughput (fit 676x380, bilinear, null sink) ==")
    fit_w, fit_h = 676, 380
    chain_prev = build_tier3_chain(fit_w, fit_h, 0.0, "bilinear")
    elapsed, proc = run(
        [paths.FFMPEG, "-hide_banner", "-loglevel", "error",
         "-i", str(src), "-filter_complex", f"[0:v:0]{chain_prev}[vout]",
         "-map", "[vout]", "-f", "null", "-"],
        "preview",
    )
    check("preview graph exit 0", proc.returncode == 0)
    check("preview throughput >= 1x realtime", elapsed <= DURATION * 1.05,
          f"{elapsed:.1f}s for {DURATION:.0f}s of video ({DURATION / elapsed:.2f}x)")

    print(f"\n{'ALL CHECKS PASSED' if not failures else f'{len(failures)} FAILURE(S): ' + ', '.join(failures)}")
    if not args.keep and not failures:
        for f in workdir.iterdir():
            f.unlink(missing_ok=True)
        workdir.rmdir()
    else:
        print(f"artifacts kept in {workdir}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
