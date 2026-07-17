"""Widget/skin gallery — a development harness for iterating on the look.

    python -m cliptoolbox.ui.gallery
    python -m cliptoolbox.ui.gallery --skin reach            (any registered skin)
    python -m cliptoolbox.ui.gallery --screenshot out.png   (build, grab, exit)

Not part of the app itself; safe to run alongside it.
"""
import os
import sys

# --skin must take effect before the first cliptoolbox.ui import: the theme
# resolves the active skin once, at import time.
if "--skin" in sys.argv[:-1]:
    os.environ["CLIPTOOLBOX_SKIN"] = sys.argv[sys.argv.index("--skin") + 1]

import tkinter as tk

from cliptoolbox.ui import dialogs, dpi, fonts, skin, theme, widgets
from cliptoolbox.ui.seekbar import HaloSeekbar
from cliptoolbox.ui.theme import px
from cliptoolbox.ui.views.empty_state import RecentsGrid
from cliptoolbox.ui.widgets import (
    HaloButton,
    HaloCheckbox,
    HaloEntry,
    HaloMenuItem,
    HaloPanel,
    HaloSegmented,
    HaloSlider,
    LegendBar,
    make_log,
)


def build(root: tk.Tk) -> None:
    w, h = px(960), px(985)
    root.title("ClipToolbox skin gallery")
    root.geometry(f"{w}x{h}")
    root.configure(bg=theme.BG_DEEP)

    sk = skin.get_skin()

    bg = tk.Canvas(root, highlightthickness=0, bd=0, bg=theme.BG_DEEP)
    bg.place(x=0, y=0, relwidth=1, relheight=1)
    bg.create_image(0, 0, image=sk.get("background", w=w, h=h), anchor="nw")
    header_skew = -px(22) if theme.BAR_SKEW else 0  # straight bar on skew-less skins
    bg.create_image(0, 0, image=sk.get("bar", w=px(560), h=px(40), skew_right=header_skew), anchor="nw")
    bg.create_text(px(36), px(20), text="SKIN GALLERY", font=theme.font_title(16),
                   fill=theme.TEXT_BRIGHT, anchor="w")

    # --- buttons ------------------------------------------------------
    y = px(64)
    HaloButton(root, "EXPORT CLIP", variant="primary",
               command=lambda: dialogs.toast("Export complete", "9.87 MB in Windows/Discord",
                                             kind="success", action_label="OPEN FOLDER",
                                             action=lambda: None)).place(x=px(24), y=y)
    HaloButton(root, "BACK TO MENU", variant="secondary",
               command=lambda: dialogs.showinfo("Notice", "Secondary pressed.")).place(x=px(214), y=y + px(5))
    HaloButton(root, "CANCEL EXPORT", variant="danger",
               command=lambda: dialogs.showerror("Export Error", "FFmpeg export failed.\n\nExample error output.")).place(x=px(390), y=y + px(5))
    disabled = HaloButton(root, "DISABLED", variant="secondary")
    disabled.config(state=tk.DISABLED)
    disabled.place(x=px(575), y=y + px(5))
    HaloButton(root, "ASK", variant="secondary",
               command=lambda: dialogs.toast("Answer", f"askyesno -> {dialogs.askyesno('Export in progress', 'An export is still running. Quit anyway?')}")).place(x=px(700), y=y + px(5))

    # --- roster panel -------------------------------------------------
    panel = HaloPanel(root, title="2 track(s) in mix")
    panel.place(x=px(24), y=px(130), width=px(360), height=px(190))

    for i, (name, vol) in enumerate((("Track 1 - eng / AAC / 2 ch", "100%"), ("Track 2 - spa / AAC / 2 ch", "40%"))):
        row = tk.Frame(panel.body, bg=theme.ROSTER)
        row.pack(fill=tk.X, pady=(0, px(6)))
        var = tk.BooleanVar(value=True)
        HaloCheckbox(row, text=name, variable=var, behind=theme.ROSTER,
                     text_color=theme.TEXT_BRIGHT).pack(side=tk.LEFT, padx=px(6), pady=px(2))
        tk.Label(row, text=vol, font=theme.font_small(), bg=theme.ROSTER,
                 fg=theme.TEXT_BRIGHT).pack(side=tk.RIGHT, padx=px(8))
        slider = HaloSlider(panel.body, from_=0.0, to=2.0, resolution=0.01,
                            length=px(320), behind=theme.PANEL_FILL)
        slider.set(1.0 if i == 0 else 0.4)
        slider.pack(fill=tk.X, pady=(0, px(8)))

    # --- timeline strips (side by side: full demo + zoomed frame grid) --
    # Synthetic lane feeds keep the gallery a pure look-iteration harness:
    # no ffmpeg, no media files.
    def demo_filmstrip(n=24, tile_w=32, tile_h=44):
        from PIL import Image as PILImage
        strip = PILImage.new("RGB", (n * tile_w, tile_h))
        for i in range(n):
            hue = int(i / n * 255)
            for x in range(tile_w):
                shade = 90 + int(110 * x / tile_w)
                for y in range(tile_h):
                    strip.putpixel((i * tile_w + x, y),
                                   (shade, (hue + 40) % 255, 160))
        return strip, n

    def demo_waveform(w=1024, h=32, beats=9.0, quiet=1.0):
        import math as _math
        from PIL import Image as PILImage
        wave = PILImage.new("RGBA", (w, h), (0, 0, 0, 0))
        for x in range(w):
            env = abs(_math.sin(x / w * beats * _math.pi)) * quiet
            half = max(1, int(env * (h // 2)))
            for y in range(h // 2 - half, h // 2 + half):
                wave.putpixel((x, y), (255, 255, 255, 255))
        return wave

    seek_var = tk.DoubleVar(value=42.0)
    seek = HaloSeekbar(root, to=120.0, variable=seek_var)
    seek.place(x=px(24), y=px(330), width=px(450))
    seek.set_trim(20.0, 90.0)
    seek.set_keyframes([12.0, 42.0, 68.0, 105.0])
    seek.set_fps(60.0)
    seek.set_filmstrip(*demo_filmstrip())
    seek.set_waveforms([demo_waveform(), demo_waveform(beats=23.0, quiet=0.45)])
    seek.set_wave_states(["solo", "dim"])

    # Second strip: zoomed to the per-frame grid, with ghosted (inert)
    # keyframes and the export sweep + attempt counter.
    zoom_var = tk.DoubleVar(value=74.3)
    zoom_seek = HaloSeekbar(root, to=120.0, variable=zoom_var)
    zoom_seek.place(x=px(486), y=px(330), width=px(450))
    zoom_seek.set_fps(60.0)
    zoom_seek.set_keyframes([74.25, 74.5], inert=True)
    # ~0.5 s window → frames clearly separated; 62% of 0..120 = 74.4 s, so
    # the export sweep line + attempt counter land inside the view.
    zoom_seek.set_view(74.15, 74.65)
    zoom_seek.set_export_progress(62, attempt=3, attempts_max=8)
    tk.Label(root, text="zoomed (frame grid · inert keys · export sweep)",
             font=theme.font_small(),
             bg=theme.BG_DEEP, fg=theme.TEXT_DIM).place(x=px(486), y=px(438))

    kf_readout = tk.Label(root, text="0:42", font=theme.font_small(), bg=theme.BG_DEEP,
                          fg=theme.TEXT)
    kf_readout.place(x=px(24), y=px(438))
    seek.bind_keyframe_click(lambda i: kf_readout.config(text=f"click kf {i}"))
    seek.bind_keyframe_commit(lambda i, v: kf_readout.config(text=f"kf {i} -> {v:.1f}s"))

    # --- checkbox + entry + segmented row ------------------------------
    controls = tk.Frame(root, bg=theme.BG_DEEP)
    controls.place(x=px(24), y=px(462))
    compress_var = tk.BooleanVar(value=True)
    HaloCheckbox(controls, text="Compress", variable=compress_var,
                 behind=theme.BG_DEEP).pack(side=tk.LEFT)
    tk.Label(controls, text="Target:", font=theme.font_body(), bg=theme.BG_DEEP,
             fg=theme.TEXT).pack(side=tk.LEFT, padx=(px(16), px(6)))
    target_var = tk.StringVar(value="9.99")
    HaloEntry(controls, textvariable=target_var, width=6, behind=theme.BG_DEEP).pack(side=tk.LEFT)
    tk.Label(controls, text="MB", font=theme.font_body(), bg=theme.BG_DEEP,
             fg=theme.TEXT_DIM).pack(side=tk.LEFT, padx=(px(6), px(16)))
    res_var = tk.StringVar(value="1080p")
    HaloSegmented(controls, ["1080p", "720p", "600p"], res_var,
                  behind=theme.BG_DEEP).pack(side=tk.LEFT)

    # --- menu items -----------------------------------------------------
    menu = tk.Frame(root, bg=theme.BG_DEEP)
    menu.place(x=px(620), y=px(130))
    for label in ("LOAD CLIP", "RECENT CLIPS", "SETTINGS", "QUIT"):
        HaloMenuItem(menu, label, width=px(300)).pack(pady=px(1))

    # --- log ------------------------------------------------------------
    log_frame, log_text = make_log(root, behind=theme.BG_DEEP)
    log_frame.place(x=px(24), y=px(500), width=px(600), height=px(110))
    log_text.config(state=tk.NORMAL)
    log_text.insert(tk.END, "[13:11:04] Loaded video: test_clip.mp4\n")
    log_text.insert(tk.END, "[13:11:04] Found 2 audio track(s). Duration: 0:12.\n")
    log_text.insert(tk.END, "[13:11:20] Compression attempt 1/8: encode budget 3.00 MB internal, video 1950 kbps, audio 64 kbps.\n")
    log_text.config(state=tk.DISABLED)

    # --- crop box editor ------------------------------------------------
    from io import BytesIO

    from PIL import Image

    from cliptoolbox.ui.cropbox import CropBoxCanvas

    grad = Image.new("RGB", (320, 180))
    for gy in range(180):
        for gx in range(0, 320, 4):
            grad.putpixel((gx, gy), (int(gx / 320 * 255), int(gy / 180 * 255), 140))
    grad = grad.resize((640, 360))
    buf = BytesIO()
    grad.save(buf, format="PNG")

    crop = CropBoxCanvas(root, behind=theme.BG_DEEP)
    crop.place(x=px(660), y=px(470), width=px(280), height=px(160))
    crop.set_source(1920, 1080)
    crop.set_image(buf.getvalue())
    crop.set_rect(480, 270, 960, 540)

    bg.create_image(px(660), px(432), image=sk.get("wordmark", text="CLIPTOOLBOX", size_px=px(24)), anchor="nw")

    # --- recents grid (B2 empty state) ----------------------------------
    recents = RecentsGrid(
        root, thumb_provider=lambda p, cb: cb(None),
        on_open=lambda p: dialogs.toast("Open", p),
        on_remove=lambda p: None, on_reveal=lambda p: None,
        behind=theme.BG_DEEP,
    )
    recents.set_entries([
        {"path": "a", "name": "raid_night_finale.mp4", "exists": True, "has_session": True},
        {"path": "b", "name": "double_kill_close_call_extended.mp4", "exists": True, "has_session": False},
        {"path": "c", "name": "deleted_scrim.mp4", "exists": False, "has_session": False},
        {"path": "d", "name": "clutch.mp4", "exists": True, "has_session": False},
    ])
    recents.select_index(0)
    recents.place(x=px(24), y=px(636))
    tk.Label(root, text="recents grid (selected · session dot · missing)",
             font=theme.font_small(), bg=theme.BG_DEEP,
             fg=theme.TEXT_DIM).place(x=px(620), y=px(640))

    # --- export-drawer job rows (B4) -------------------------------------
    # Synthetic jobs + a duck-typed app: the rows are pure look, no ffmpeg.
    import tempfile
    import types
    from pathlib import Path

    from cliptoolbox.core import jobs as core_jobs
    from cliptoolbox.ui.views.drawer import JobRow

    demo_out = Path(tempfile.gettempdir()) / "raid_night_finale_mixed_audio.mp4"
    demo_out.touch()  # existing output => the DONE row shows OPEN/FOLDER
    fake_app = types.SimpleNamespace(
        is_exporting=False, cancel_export=lambda: None,
        job_open=lambda job_id: None, job_reveal=lambda job_id: None,
        job_rerun=lambda job_id: None)
    demo_spec = core_jobs.ExportJobSpec(
        input_path=str(demo_out), filter_complex="", output_path=str(demo_out),
        clip_name="raid_night_finale.mp4")

    running = core_jobs.ExportJob("g-running", demo_spec)
    running.percent, running.attempt, running.attempts_max = 62, 3, 8
    done = core_jobs.ExportJob("g-done", demo_spec)
    done.finish(core_jobs.DONE, size_bytes=10_470_000)

    tk.Label(root, text="export job rows (running · done)",
             font=theme.font_small(), bg=theme.BG_DEEP,
             fg=theme.TEXT_DIM).place(x=px(620), y=px(658))
    for i, job in enumerate((running, done)):
        row = JobRow(root, fake_app, job)
        row.place(x=px(620), y=px(676) + i * px(78), width=px(320))
        row.update(job)

    # --- focus HUD chips (B5) --------------------------------------------
    # Rendered on a black band standing in for the preview letterbox — the
    # chips fake translucency by pre-blending the panel colors toward it.
    hud_band = tk.Canvas(root, bg="black", highlightthickness=0, bd=0)
    hud_band.place(x=px(24), y=px(770), width=px(560), height=px(58))
    chip_h = px(30)
    name_w = px(250)
    hud_band.create_image(px(12), px(14), anchor="nw",
                          image=sk.get("hud_chip", w=name_w, h=chip_h))
    hud_band.create_text(px(12) + px(14), px(14) + chip_h // 2,
                         text="raid_night_finale.mp4", anchor="w",
                         font=theme.font_title(12), fill=theme.TEXT_BRIGHT)
    tr_w = px(150)
    tr_x = px(560) - px(12) - tr_w
    hud_band.create_image(tr_x, px(14), anchor="nw",
                          image=sk.get("hud_chip", w=tr_w, h=chip_h))
    gx, gcy, gs = tr_x + px(14), px(14) + chip_h // 2, px(6)
    hud_band.create_polygon(gx, gcy - gs, gx + round(gs * 1.6), gcy, gx, gcy + gs,
                            fill=theme.ACCENT, outline="")
    hud_band.create_text(gx + px(24), gcy, text="0:42 / 2:10", anchor="w",
                         font=theme.font_mono(12), fill=theme.TEXT)
    tk.Label(root, text="focus HUD chips (letterbox-blended scanline)",
             font=theme.font_small(), bg=theme.BG_DEEP,
             fg=theme.TEXT_DIM).place(x=px(24), y=px(831))

    # --- coach mark callout (B6) -----------------------------------------
    from cliptoolbox.ui.views.coach import draw_callout

    coach_canvas = tk.Canvas(root, bg=theme.BG_DEEP, highlightthickness=0, bd=0)
    coach_canvas.place(x=px(24), y=px(862), width=px(400), height=px(100))
    draw_callout(coach_canvas, px(4), px(2), "EXPORT", [
        [("k", "CTRL+E"), ("t", "EXPORT DRAWER")],
        [("t", "naming · compression · job history")],
    ], behind=theme.BG_DEEP)
    tk.Label(root, text="coach mark callout (keycaps · chamfered card)",
             font=theme.font_small(), bg=theme.BG_DEEP,
             fg=theme.TEXT_DIM).place(x=px(620), y=px(880))

    legend = LegendBar(root)
    legend.pack(side=tk.BOTTOM, fill=tk.X)
    legend.set_hints([("SPACE", "PLAY/PAUSE"), ("[ ]", "SET TRIM"), ("CTRL+E", "EXPORT")])

    dialogs.attach(root)
    dialogs.set_toast_offset(px(46))


def main():
    screenshot = None
    if "--screenshot" in sys.argv:
        screenshot = sys.argv[sys.argv.index("--screenshot") + 1]

    dpi.init()
    fonts.load_private_fonts()

    root = tk.Tk()
    fonts.verify_with_tk(root)
    build(root)

    if screenshot:
        # ImageGrab captures the physical screen region, so the window must
        # actually be frontmost for the instant of the grab.
        root.attributes("-topmost", True)
        root.update_idletasks()
        root.update()
        root.lift()
        root.focus_force()

        def grab():
            from PIL import ImageGrab
            x, y = root.winfo_rootx(), root.winfo_rooty()
            w, h = root.winfo_width(), root.winfo_height()
            ImageGrab.grab(bbox=(x, y, x + w, y + h)).save(screenshot)
            print("saved", screenshot)
            root.destroy()

        root.after(500, grab)

    root.mainloop()


if __name__ == "__main__":
    main()
