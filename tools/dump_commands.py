"""Golden-command parity checker for the extracted core logic.

Prints the exact FFmpeg argv lists and filter graphs the core produces for a
fixed set of synthetic inputs, with the machine-specific ffmpeg path masked.
Run it before and after any refactor that is not supposed to change behavior;
the output must be identical.

    python tools/dump_commands.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cliptoolbox.core import commands, filters, playback
from cliptoolbox.core import paths

INPUT = r"C:\clips\example.mp4"
OUTPUT_MP4 = r"C:\clips\outputs\example_mixed_audio.mp4"
OUTPUT_MKV = r"C:\clips\outputs\example_mixed_audio.mkv"


def mask(argv: list[str]) -> list[str]:
    masked = []
    for arg in argv:
        if arg == paths.FFMPEG:
            masked.append("{FFMPEG}")
        elif arg == paths.FFPLAY:
            masked.append("{FFPLAY}")
        else:
            masked.append(arg)
    return masked


def dump(title: str, value):
    print(f"--- {title} ---")
    if isinstance(value, list):
        for item in value:
            print(f"  {item}")
    else:
        print(f"  {value}")
    print()


def main():
    dump(
        "audio filter: track 1 @100%, track 3 @37%",
        filters.build_audio_filter([(1, 1.0), (3, 0.37)]),
    )
    dump(
        "audio filter: single track 2 @150%",
        filters.build_audio_filter([(2, 1.5)]),
    )

    two_track_filter = filters.build_audio_filter([(1, 1.0), (2, 0.8)])

    dump(
        "standard export, no trim, mp4",
        mask(commands.build_standard_export_command(INPUT, two_track_filter, OUTPUT_MP4)),
    )
    dump(
        "standard export, trim 5.0->20.0, mp4",
        mask(commands.build_standard_export_command(INPUT, two_track_filter, OUTPUT_MP4, 5.0, 20.0)),
    )
    dump(
        "standard export, trim start-only 5.0, mkv",
        mask(commands.build_standard_export_command(INPUT, two_track_filter, OUTPUT_MKV, 5.0, None)),
    )
    dump(
        "standard export, trim end-only 20.0, mp4",
        mask(commands.build_standard_export_command(INPUT, two_track_filter, OUTPUT_MP4, None, 20.0)),
    )

    dump(
        "bitrates for 9.99 MB / 60.0 s",
        list(commands.compression_bitrates_for_budget(9.99, 60.0)),
    )
    dump(
        "bitrates for 25 MB / 12.5 s",
        list(commands.compression_bitrates_for_budget(25.0, 12.5)),
    )

    cmd, video_kbps, audio_kbps, total_kbps = commands.build_compressed_export_command(
        INPUT, two_track_filter, OUTPUT_MP4, 4.2, 11.8, 9.99, 7.6, "720p"
    )
    dump("compressed export, trim 4.2->11.8, 9.99 MB @720p, mp4", mask(cmd))
    dump("compressed export bitrates (video/audio/total kbps)", [video_kbps, audio_kbps, round(total_kbps, 3)])

    playback_filter = playback.build_playback_filter([(1, 1.0), (2, 0.8)], 676, 396)
    dump("playback filter: 2 tracks + scaled video", playback_filter)

    ffmpeg_cmd, ffplay_cmd = playback.build_playback_stream_cmds(
        INPUT, playback_filter, 30.0, 676, 396
    )
    dump("playback ffmpeg cmd from 0:30", mask(ffmpeg_cmd))
    dump("playback ffplay cmd 676x396", mask(ffplay_cmd))

    dump(
        "paused-frame extract cmd @12.34s",
        mask(playback.build_frame_extract_cmd(INPUT, 12.34, r"C:\temp\frame.jpg")),
    )

    dump("trim clamp: end<=start", list(commands.clamp_trim_points(10.0, 5.0, 60.0)))
    dump("trim clamp: clamped to duration", list(commands.clamp_trim_points(-2.0, 999.0, 60.0)))
    dump("progress duration: trim 5->20 of 60", commands.export_progress_duration(60.0, 5.0, 20.0))
    dump("progress duration: no trim of 60", commands.export_progress_duration(60.0))
    dump("parse target: '9,99 MB'", commands.parse_target_mb("9,99 MB"))
    dump("resolution limit: 720p", list(commands.resolve_resolution_limit("720p")))
    dump("resolution limit: invalid -> default", list(commands.resolve_resolution_limit("nope")))


if __name__ == "__main__":
    main()
