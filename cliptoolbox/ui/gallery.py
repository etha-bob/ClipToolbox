"""Widget/skin gallery — a development harness for iterating on the look.

    python -m cliptoolbox.ui.gallery
    python -m cliptoolbox.ui.gallery --screenshot out.png   (build, grab, exit)

Not part of the app itself; safe to run alongside it.
"""
import sys
import tkinter as tk

from cliptoolbox.ui import dialogs, dpi, fonts, skin, theme, widgets
from cliptoolbox.ui.seekbar import HaloSeekbar
from cliptoolbox.ui.theme import px
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
    w, h = px(960), px(700)
    root.title("ClipToolbox skin gallery")
    root.geometry(f"{w}x{h}")
    root.configure(bg=theme.BG_DEEP)

    sk = skin.get_skin()

    bg = tk.Canvas(root, highlightthickness=0, bd=0, bg=theme.BG_DEEP)
    bg.place(x=0, y=0, relwidth=1, relheight=1)
    bg.create_image(0, 0, image=sk.get("background", w=w, h=h), anchor="nw")
    bg.create_image(0, 0, image=sk.get("bar", w=px(560), h=px(40), skew_right=-px(22)), anchor="nw")
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
        row = tk.Frame(panel.body, bg=theme.MAROON)
        row.pack(fill=tk.X, pady=(0, px(6)))
        var = tk.BooleanVar(value=True)
        HaloCheckbox(row, text=name, variable=var, behind=theme.MAROON,
                     text_color=theme.TEXT_BRIGHT).pack(side=tk.LEFT, padx=px(6), pady=px(2))
        tk.Label(row, text=vol, font=theme.font_small(), bg=theme.MAROON,
                 fg=theme.TEXT_BRIGHT).pack(side=tk.RIGHT, padx=px(8))
        slider = HaloSlider(panel.body, from_=0.0, to=2.0, resolution=0.01,
                            length=px(320), behind=theme.PANEL_FILL)
        slider.set(1.0 if i == 0 else 0.4)
        slider.pack(fill=tk.X, pady=(0, px(8)))

    # --- seekbar + trim + keyframes -----------------------------------
    seek_var = tk.DoubleVar(value=42.0)
    seek = HaloSeekbar(root, to=120.0, variable=seek_var)
    seek.place(x=px(24), y=px(340), width=px(600))
    seek.set_trim(20.0, 90.0)
    seek.set_keyframes([12.0, 42.0, 68.0, 105.0])
    seek.set_fps(60.0)

    # Second seekbar: zoomed in far enough to show the per-frame grid.
    zoom_var = tk.DoubleVar(value=41.6)
    zoom_seek = HaloSeekbar(root, to=120.0, variable=zoom_var)
    zoom_seek.place(x=px(24), y=px(300), width=px(600))
    zoom_seek.set_fps(60.0)
    zoom_seek.set_keyframes([41.55, 41.7])
    zoom_seek.set_view(41.4, 41.9)  # ~0.5 s window → frames clearly separated
    tk.Label(root, text="zoomed (frame grid)", font=theme.font_small(),
             bg=theme.BG_DEEP, fg=theme.TEXT_DIM).place(x=px(636), y=px(306))

    kf_readout = tk.Label(root, text="0:42", font=theme.font_small(), bg=theme.BG_DEEP,
                          fg=theme.TEXT)
    kf_readout.place(x=px(636), y=px(346))
    seek.bind_keyframe_click(lambda i: kf_readout.config(text=f"click kf {i}"))
    seek.bind_keyframe_commit(lambda i, v: kf_readout.config(text=f"kf {i} -> {v:.1f}s"))

    # --- checkbox + entry + segmented row ------------------------------
    controls = tk.Frame(root, bg=theme.BG_DEEP)
    controls.place(x=px(24), y=px(384))
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
    log_frame.place(x=px(24), y=px(430), width=px(600), height=px(120))
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

    bg.create_image(px(24), px(560), image=sk.get("wordmark", text="CLIPTOOLBOX", size_px=px(30)), anchor="nw")

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
