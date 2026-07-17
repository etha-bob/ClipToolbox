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

from cliptoolbox.core import commands, filters, motion, playback, playback_mpv
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

    dump_motion()
    dump_mpv()
    dump_silent()


def dump_mpv():
    """Optional mpv engine builders. Appended so the output above stays
    byte-identical whether or not mpv is installed."""
    dump(
        "mpv lavfi: single track @80%",
        playback_mpv.build_mpv_lavfi([(1, 0.8)], None),
    )
    dump(
        "mpv lavfi: 3 tracks (100/0/50%)",
        playback_mpv.build_mpv_lavfi([(1, 1.0), (2, 0.0), (3, 0.5)], None),
    )
    dump(
        "mpv lavfi: single track + crop chain",
        playback_mpv.build_mpv_lavfi([(1, 1.0)], "crop=1280:720:100:50,scale=1920:1080"),
    )
    cmd = playback_mpv.build_mpv_cmd("{MPV}", 123456, r"\\.\pipe\cliptoolbox-mpv-0-1")
    dump("mpv spawn cmd (wid 123456)", cmd)


def dump_silent():
    """Silent-video (L1) export builders: an empty filter_complex (no audio
    graph) drops the [aout] map and encodes -an. Appended so the output above
    stays byte-identical (every case above passes a real audio filter)."""
    dump(
        "SILENT standard export, stream-copy, trim 5->20, mp4 (-an)",
        mask(commands.build_standard_export_command(INPUT, "", OUTPUT_MP4, 5.0, 20.0)),
    )
    static = make_track((0.0, 100.0, 50.0, 1280.0, 720.0))
    crop_vf = motion.build_motion_chain(static, 1920, 1080, 1920, 1080) + ",setsar=1"
    dump(
        "SILENT standard export + crop video_filter, no trim, mp4 (NVENC, -an)",
        mask(commands.build_standard_export_command(INPUT, "", OUTPUT_MP4, None, None, crop_vf)),
    )
    prefilter = motion.build_motion_chain(static, 1920, 1080, 1280, 720)
    ccmd, *_ = commands.build_compressed_export_command(
        INPUT, "", OUTPUT_MP4, 4.2, 11.8, 9.99, 7.6, "720p", prefilter
    )
    dump("SILENT compressed export + crop prefilter, 9.99 MB @720p, mp4 (-an)", mask(ccmd))


def make_track(*keyframes: tuple) -> motion.CropTrack:
    track = motion.CropTrack()
    track.enabled = True
    for kf in keyframes:
        track.keyframes = track.keyframes + (motion.CropKeyframe(*kf),)
    track.keyframes = tuple(sorted(track.keyframes, key=lambda k: k.t))
    return track


def dump_motion():
    """Keyframed crop/zoom (motion) golden cases. Appended so the pre-existing
    output above stays byte-identical."""
    SRC_W, SRC_H = 1920, 1080

    identity = make_track((0.0, 0.0, 0.0, 1920.0, 1080.0))
    dump(
        "motion chain: identity full-frame -> None",
        motion.build_motion_chain(identity, SRC_W, SRC_H, 1920, 1080),
    )

    disabled = make_track((0.0, 100.0, 50.0, 640.0, 360.0))
    disabled.enabled = False
    dump(
        "motion chain: disabled track -> None",
        motion.build_motion_chain(disabled, SRC_W, SRC_H, 1920, 1080),
    )

    static = make_track((0.0, 100.0, 50.0, 1280.0, 720.0))
    dump(
        "motion chain: tier1 static crop, out 1920x1080",
        motion.build_motion_chain(static, SRC_W, SRC_H, 1920, 1080),
    )

    pan = make_track(
        (0.0, 0.0, 0.0, 640.0, 360.0),
        (5.0, 1280.0, 720.0, 640.0, 360.0),
    )
    dump(
        "motion chain: tier2 pan (constant size), out 1920x1080",
        motion.build_motion_chain(pan, SRC_W, SRC_H, 1920, 1080),
    )

    zoom = make_track(
        (0.0, 0.0, 0.0, 1920.0, 1080.0),
        (5.0, 0.0, 0.0, 640.0, 360.0),
        (9.0, 1280.0, 540.0, 640.0, 540.0),
    )
    dump(
        "motion chain: tier3 zoom/stretch, out 1920x1080, no offset",
        motion.build_motion_chain(zoom, SRC_W, SRC_H, 1920, 1080),
    )
    dump(
        "motion chain: tier3 zoom/stretch, preview fit 674x380, offset 3.0, bilinear",
        motion.build_motion_chain(zoom, SRC_W, SRC_H, 674, 380, time_offset=3.0, scale_flags="bilinear"),
    )

    dump(
        "motion rect_at zoom: t=-1 / 0 / 2.5 / 5 / 7 / 9 / 12",
        [zoom.rect_at(t) for t in (-1.0, 0.0, 2.5, 5.0, 7.0, 9.0, 12.0)],
    )

    dump(
        "still crop vf: rect (640.4, 270.6, 641.2, 451.9) src 1920x1080 out 1920x1080",
        motion.build_still_crop_vf((640.4, 270.6, 641.2, 451.9), SRC_W, SRC_H, 1920, 1080),
    )

    dump(
        "fit_size: 1920x1080 / 1080x1920 / 1280x719 into 676x380 box",
        [
            motion.fit_size(1920, 1080, 676, 380),
            motion.fit_size(1080, 1920, 676, 380),
            motion.fit_size(1280, 719, 676, 380),
        ],
    )
    dump(
        "clamp_rect: oversize / negative / min-size on 1920x1080, min 16",
        [
            motion.clamp_rect(-10.0, -10.0, 5000.0, 5000.0, 1920, 1080, 16),
            motion.clamp_rect(1900.0, 1070.0, 8.0, 8.0, 1920, 1080, 16),
        ],
    )

    audio = filters.build_audio_filter([(1, 1.0)])
    static_vf = motion.build_motion_chain(static, SRC_W, SRC_H, 1920, 1080) + ",setsar=1"
    dump(
        "standard export with crop video_filter, trim 5->20, mp4 (NVENC re-encode)",
        mask(commands.build_standard_export_command(INPUT, audio, OUTPUT_MP4, 5.0, 20.0, static_vf)),
    )
    dump(
        "standard export with crop video_filter, no trim, mkv (no hvc1 tag)",
        mask(commands.build_standard_export_command(INPUT, audio, OUTPUT_MKV, None, None, static_vf)),
    )
    prefilter = motion.build_motion_chain(static, SRC_W, SRC_H, 1920, 1080)
    ccmd, *_ = commands.build_compressed_export_command(
        INPUT, audio, OUTPUT_MP4, 4.2, 11.8, 9.99, 7.6, "720p", prefilter
    )
    dump("compressed export with crop video_prefilter, 9.99 MB @720p, mp4", mask(ccmd))

    preview_chain = motion.build_motion_chain(
        pan, SRC_W, SRC_H, 674, 380, time_offset=12.0, scale_flags="bilinear"
    )
    dump(
        "playback filter with crop video_chain (pan, fit 674x380, offset 12.0)",
        playback.build_playback_filter([(1, 1.0)], 674, 380, video_chain=preview_chain),
    )
    dump(
        "paused-frame extract cmd @8.0s with static crop vf",
        mask(playback.build_frame_extract_cmd(INPUT, 8.0, r"C:\temp\frame.jpg", static_vf)),
    )


if __name__ == "__main__":
    main()
