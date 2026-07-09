import json
import subprocess

from cliptoolbox.constants import CREATE_NO_WINDOW
from cliptoolbox.core import paths


class ProbeError(RuntimeError):
    pass


def probe_audio_streams(filepath: str) -> list[dict]:
    cmd = [
        paths.FFPROBE,
        "-v",
        "error",
        "-select_streams",
        "a",
        "-show_entries",
        "stream=index,codec_name,channels:stream_tags=language,title,handler_name",
        "-of",
        "json",
        filepath,
    ]

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
            creationflags=CREATE_NO_WINDOW,
        )

        data = json.loads(result.stdout)

    except Exception as exc:
        raise ProbeError(f"ffprobe failed:\n\n{exc}") from exc

    streams = data.get("streams", [])
    output = []

    for display_index, stream in enumerate(streams):
        tags = stream.get("tags", {}) or {}

        stream_index = stream.get("index")
        codec = stream.get("codec_name", "unknown")
        channels = stream.get("channels")

        language = tags.get("language")
        title = tags.get("title")
        handler = tags.get("handler_name")

        details = []

        if language:
            details.append(language)

        if title:
            details.append(title)
        elif handler:
            details.append(handler)

        if codec:
            details.append(codec.upper())

        if channels:
            details.append(f"{channels} ch")

        if details:
            label = f"Track {display_index + 1} - " + " / ".join(details)
        else:
            label = f"Track {display_index + 1}"

        if stream_index is not None:
            output.append(
                {
                    "index": stream_index,
                    "label": label,
                }
            )

    return output


def probe_duration(filepath: str) -> float | None:
    cmd = [
        paths.FFPROBE,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        filepath,
    ]

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
            creationflags=CREATE_NO_WINDOW,
        )

        return float(result.stdout.strip())

    except Exception:
        return None
