import os
import re
from datetime import datetime
from pathlib import Path

from cliptoolbox.constants import IS_WINDOWS, TIMESTAMP_WATERMARK_FADE_MS


def extract_recording_datetime(filename: str) -> datetime | None:
    """Pull a recording timestamp out of a filename as a datetime.

    Matches six date/time parts (year, month, day, hour, minute, second)
    separated by spaces/underscores/dots/dashes, e.g. ``2025 04 06 02 06 50``.
    Returns the last valid match, else None.
    """
    pattern = re.compile(
        r"(?<!\d)((?:19|20)\d{2})[ _.-]+(\d{2})[ _.-]+(\d{2})"
        r"[ _.-]+(\d{2})[ _.-]+(\d{2})[ _.-]+(\d{2})(?!\d)"
    )

    for match in reversed(list(pattern.finditer(str(filename)))):
        try:
            return datetime(*map(int, match.groups()))
        except ValueError:
            continue

    return None


def extract_recording_timestamp(filename: str) -> str | None:
    """Legacy string form of extract_recording_datetime (Q9 behavior):
    ``YYYY-MM-DD HH:MM:SS`` or None."""
    recorded_at = extract_recording_datetime(filename)
    if recorded_at is None:
        return None
    return recorded_at.strftime("%Y-%m-%d %H:%M:%S")


# Watermark date-format presets (M11). Keys persist in config.json; the
# values are strftime date parts. The settings UI labels each option with
# a concrete example, so the ids never surface to the user.
WATERMARK_DATE_FORMATS = {
    "ymd": "%Y-%m-%d",
    "mdy": "%m/%d/%Y",
    "dmy": "%d.%m.%Y",
}


def format_watermark_datetime(recorded_at: datetime, date_format: str = "ymd",
                              include_time: bool = True) -> str:
    """Render a watermark timestamp per the M11 settings: a date-format
    preset plus an optional 24h time-of-day suffix. Unknown preset ids
    fall back to ISO (ymd)."""
    date_part = recorded_at.strftime(
        WATERMARK_DATE_FORMATS.get(date_format, WATERMARK_DATE_FORMATS["ymd"]))
    if include_time:
        return f"{date_part} {recorded_at.strftime('%H:%M:%S')}"
    return date_part


def resolve_watermark_text(video_path: str, source: str = "parsed",
                           date_format: str = "ymd",
                           include_time: bool = True) -> str:
    """Resolve the burned-in watermark text for a clip per the M11 settings.

    source: "parsed" (recording time parsed from the filename), "created"
    (the file's creation timestamp), or "filename" (the stem as literal
    text — date_format/include_time don't apply). Raises ValueError with a
    user-facing message when the source can't produce text."""
    stem = Path(video_path).stem
    if source == "filename":
        if not stem:
            raise ValueError("This file has no usable name for the watermark.")
        return stem
    if source == "created":
        try:
            recorded_at = datetime.fromtimestamp(os.path.getctime(video_path))
        except (OSError, ValueError, OverflowError) as exc:
            raise ValueError("Could not read this file's created-on date.") from exc
    else:
        recorded_at = extract_recording_datetime(stem)
        if recorded_at is None:
            raise ValueError(
                "No recording timestamp was found in the filename. Expected six "
                "date/time parts like 2025 04 06 02 06 50 — or switch the "
                "watermark text source in Settings."
            )
    return format_watermark_datetime(recorded_at, date_format, include_time)


def build_timestamp_watermark_filter(timestamp_text: str, duration_seconds: float) -> str:
    """drawtext filter that burns ``timestamp_text`` bottom-left and fades it out.

    The text ramps in, holds until ``duration_seconds``, then fades over
    ``TIMESTAMP_WATERMARK_FADE_MS`` (clamped so short durations still fade).
    """
    fade_out_after_seconds = max(0.001, float(duration_seconds))
    requested_fade_seconds = TIMESTAMP_WATERMARK_FADE_MS / 1000.0
    fade_seconds = min(requested_fade_seconds, max(0.05, fade_out_after_seconds / 2.0))
    fade_end_seconds = fade_out_after_seconds + fade_seconds

    fade_out_after_text = f"{fade_out_after_seconds:.3f}"
    fade_end_text = f"{fade_end_seconds:.3f}"
    fade_text = f"{fade_seconds:.3f}"
    escaped_text = str(timestamp_text).replace("\\", r"\\").replace(":", r"\:").replace("'", r"\'")

    alpha_expression = (
        f"if(lt(t,{fade_text}),t/{fade_text},"
        f"if(lt(t,{fade_out_after_text}),1,"
        f"if(lt(t,{fade_end_text}),({fade_end_text}-t)/{fade_text},0)))"
    )

    font_option = ""
    if IS_WINDOWS:
        windows_dir = Path(os.environ.get("WINDIR", r"C:\Windows"))
        font_path = windows_dir / "Fonts" / "segoeui.ttf"
        if font_path.exists():
            escaped_font_path = str(font_path).replace("\\", "/").replace(":", r"\:")
            font_option = f"fontfile='{escaped_font_path}':"

    return (
        f"drawtext={font_option}"
        f"text='{escaped_text}':"
        "x=20:y=h-th-20:fontsize=h/26:"
        "fontcolor=white:borderw=2:bordercolor=black@0.85:"
        f"alpha='{alpha_expression}':enable='between(t,0,{fade_end_text})'"
    )


def build_audio_filter(selected: list[tuple[int, float]]) -> str:
    if not selected:
        raise ValueError("Please select at least one audio track.")

    filters = []
    maps = []

    for i, (stream_index, volume) in enumerate(selected):
        volume_text = f"{volume:.3f}"
        filters.append(f"[0:{stream_index}]volume={volume_text}[a{i}]")
        maps.append(f"[a{i}]")

    amix_inputs = len(maps)

    amix = (
        f"{''.join(maps)}"
        f"amix=inputs={amix_inputs}:duration=longest:"
        f"dropout_transition=0:normalize=0[aout]"
    )

    return ";".join(filters + [amix])
