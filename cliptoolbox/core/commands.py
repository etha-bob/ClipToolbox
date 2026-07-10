from pathlib import Path

from cliptoolbox.constants import (
    COMPRESSION_DEFAULT_AUDIO_KBPS,
    COMPRESSION_RESOLUTION_PRESETS,
    CROP_EXPORT_CQ,
    DEFAULT_COMPRESSION_RESOLUTION,
    WINDOWS_MB_BYTES,
)
from cliptoolbox.core import paths


def parse_target_mb(raw_value: str) -> float:
    raw_value = raw_value.strip().lower().replace("mb", "").strip()
    raw_value = raw_value.replace(",", ".")

    try:
        target_mb = float(raw_value)
    except Exception as exc:
        raise ValueError("Compression target must be a number, like 9.99.") from exc

    if target_mb <= 0:
        raise ValueError("Compression target must be larger than 0 MB.")

    return target_mb


def resolve_resolution_limit(resolution_label: str | None = None) -> tuple[int, int, str]:
    label = resolution_label or DEFAULT_COMPRESSION_RESOLUTION
    if label not in COMPRESSION_RESOLUTION_PRESETS:
        label = DEFAULT_COMPRESSION_RESOLUTION
    width, height = COMPRESSION_RESOLUTION_PRESETS[label]
    return width, height, label


def clamp_trim_points(
    start: float | None,
    end: float | None,
    duration: float | None,
) -> tuple[float | None, float | None]:
    if duration:
        if start is not None:
            start = min(max(0.0, start), duration)
        if end is not None:
            end = min(max(0.0, end), duration)

    if start is not None and end is not None and end <= start:
        return None, None

    return start, end


def export_progress_duration(
    full_duration: float | None,
    trim_start: float | None = None,
    trim_end: float | None = None,
) -> float:
    full_duration = full_duration or 0

    if trim_start is not None or trim_end is not None:
        effective_start = trim_start or 0
        effective_end = trim_end or full_duration
        return max(0.0, effective_end - effective_start)

    return max(0.0, full_duration)


def add_export_input_args(
    cmd: list[str],
    input_path: str,
    trim_start: float | None = None,
    trim_end: float | None = None,
):
    # Fast stream-copy video trimming. Putting -ss before -i avoids
    # re-encoding in normal exports. Compression exports re-encode video,
    # but this still keeps seeking responsive on long files.
    if trim_start is not None and trim_start > 0:
        cmd.extend(["-ss", f"{trim_start:.3f}"])

    cmd.extend(["-i", input_path])

    if trim_end is not None:
        if trim_start is not None and trim_start > 0:
            trim_duration = max(0.001, trim_end - trim_start)
            cmd.extend(["-t", f"{trim_duration:.3f}"])
        else:
            cmd.extend(["-to", f"{trim_end:.3f}"])


def build_standard_export_command(
    input_path: str,
    filter_complex: str,
    output_path: str,
    trim_start: float | None = None,
    trim_end: float | None = None,
    video_filter: str | None = None,
) -> list[str]:
    cmd = [
        paths.FFMPEG,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
    ]

    add_export_input_args(cmd, input_path, trim_start, trim_end)

    is_mp4_like = Path(output_path).suffix.lower() in {".mp4", ".mov", ".m4v"}

    cmd.extend(
        [
            "-filter_complex",
            filter_complex,

            "-map",
            "0:v:0?",
            "-map",
            "[aout]",
        ]
    )

    if video_filter:
        # A crop/zoom transform cannot be stream-copied; re-encode the video
        # with NVENC constant-quality. Mirrors the compressed path's encoder
        # choice so both re-encode routes behave consistently on this GPU.
        cmd.extend(
            [
                "-vf",
                video_filter,
                "-c:v",
                "hevc_nvenc",
                "-preset",
                "slow",
                "-rc",
                "vbr",
                "-cq",
                str(CROP_EXPORT_CQ),
                "-b:v",
                "0",
                "-pix_fmt",
                "yuv420p",
            ]
        )
        if is_mp4_like:
            cmd.extend(["-tag:v", "hvc1"])
    else:
        cmd.extend(["-c:v", "copy"])

    cmd.extend(
        [
            "-c:a",
            "aac",
            "-b:a",
            "192k",
        ]
    )

    if is_mp4_like:
        cmd.extend(["-movflags", "+faststart"])

    cmd.extend(
        [
            "-nostats",
            "-progress",
            "pipe:1",
            output_path,
        ]
    )

    return cmd


def compression_bitrates_for_budget(
    budget_mb: float,
    duration_seconds: float,
) -> tuple[int, int, float]:
    if duration_seconds <= 0:
        raise ValueError("Cannot compress to a target size because the video duration is unknown.")

    budget_bytes = max(1, int(budget_mb * WINDOWS_MB_BYTES))
    total_kbps = (budget_bytes * 8) / duration_seconds / 1000

    # Reserve a little room for the MP4/MKV container and bitrate overshoot.
    overhead_kbps = max(10, int(total_kbps * 0.04))

    # Discord-sized exports need the bits more on video than audio. Keep
    # compressed audio fixed and predictable at 64 kbps so the remaining
    # target budget can be spent on video.
    audio_kbps = COMPRESSION_DEFAULT_AUDIO_KBPS

    video_kbps = int(total_kbps - audio_kbps - overhead_kbps)

    if video_kbps < 50:
        raise ValueError(
            "This target is too small for the clip length. Try a larger MB limit, "
            "a shorter trim, or a smaller source clip."
        )

    return video_kbps, audio_kbps, total_kbps


def build_compressed_export_command(
    input_path: str,
    filter_complex: str,
    output_path: str,
    trim_start: float | None,
    trim_end: float | None,
    budget_mb: float,
    duration_seconds: float,
    compression_resolution_label: str | None,
    video_prefilter: str | None = None,
) -> tuple[list[str], int, int, float]:
    video_kbps, audio_kbps, total_kbps = compression_bitrates_for_budget(
        budget_mb,
        duration_seconds,
    )
    max_width, max_height, _ = resolve_resolution_limit(compression_resolution_label)

    cmd = [
        paths.FFMPEG,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
    ]

    add_export_input_args(cmd, input_path, trim_start, trim_end)

    cmd.extend(
        [
            "-filter_complex",
            filter_complex,

            "-map",
            "0:v:0?",
            "-map",
            "[aout]",

            "-vf",
            (
                (f"{video_prefilter}," if video_prefilter else "")
                + f"scale=w='min({max_width},iw)':"
                f"h='min({max_height},ih)':"
                "force_original_aspect_ratio=decrease:"
                "force_divisible_by=2,setsar=1"
            ),

            "-c:v",
            "hevc_nvenc",
            "-preset",
            "slow",
            "-rc",
            "cbr",
            "-b:v",
            f"{video_kbps}k",
            "-maxrate",
            f"{video_kbps}k",
            "-bufsize",
            f"{max(video_kbps, 100)}k",
            "-pix_fmt",
            "yuv420p",

            "-c:a",
            "aac",
            "-b:a",
            f"{audio_kbps}k",
            "-ac",
            "2",
        ]
    )

    if Path(output_path).suffix.lower() in {".mp4", ".mov", ".m4v"}:
        cmd.extend(["-tag:v", "hvc1", "-movflags", "+faststart"])

    cmd.extend(
        [
            "-nostats",
            "-progress",
            "pipe:1",
            output_path,
        ]
    )

    return cmd, video_kbps, audio_kbps, total_kbps
