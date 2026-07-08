"""Widget/skin gallery — a development harness for iterating on the look.

    python -m cliptoolbox.ui.gallery

Not part of the app itself; safe to run alongside it.
"""
import tkinter as tk

from cliptoolbox.ui import dpi, fonts, skin, theme
from cliptoolbox.ui.theme import px


def main():
    dpi.init()
    fonts.load_private_fonts()

    root = tk.Tk()
    root.title("ClipToolbox skin gallery")
    w, h = px(940), px(660)
    root.geometry(f"{w}x{h}")
    root.configure(bg=theme.BG_DEEP)

    fonts.verify_with_tk(root)

    sk = skin.get_skin()

    canvas = tk.Canvas(root, width=w, height=h, highlightthickness=0, bd=0, bg=theme.BG_DEEP)
    canvas.pack(fill=tk.BOTH, expand=True)

    canvas.create_image(0, 0, image=sk.get("background", w=w, h=h), anchor="nw")

    # Header + footer bars
    canvas.create_image(0, 0, image=sk.get("bar", w=px(560), h=px(40), skew_right=-px(22)), anchor="nw")
    canvas.create_text(px(36), px(20), text="SKIN GALLERY", font=theme.font_title(16),
                       fill=theme.TEXT_BRIGHT, anchor="w")
    canvas.create_image(w, h, image=sk.get("bar", w=px(520), h=px(30), skew_left=-px(22)), anchor="se")
    canvas.create_text(w - px(24), h - px(15), text=f"FONT: {fonts.family().upper()}    SCALE: {dpi.scale()}",
                       font=theme.font_small(), fill=theme.TEXT_BRIGHT, anchor="e")

    y = px(70)
    for i, (variant, state) in enumerate([
        ("primary", "normal"), ("primary", "hover"), ("primary", "pressed"),
        ("secondary", "normal"), ("secondary", "hover"),
        ("danger", "normal"), ("secondary", "disabled"),
    ]):
        bw, bh = (px(150), px(44)) if variant == "primary" else (px(130), px(34))
        x = px(24) + (i % 4) * px(170)
        yy = y + (i // 4) * px(56)
        canvas.create_image(x, yy, image=sk.get("button", w=bw, h=bh, variant=variant, state=state), anchor="nw")
        canvas.create_text(x + bw // 2, yy + bh // 2, text=f"{variant.upper()}",
                           font=theme.font_title(), fill=theme.TEXT_BRIGHT if state != "disabled" else theme.TEXT_DIM)

    # Panel + roster row + checks
    py = px(200)
    canvas.create_image(px(24), py, image=sk.get("panel", w=px(300), h=px(180)), anchor="nw")
    canvas.create_text(px(40), py + px(18), text="2 TRACK(S) IN MIX", font=theme.font_title(),
                       fill=theme.TEXT, anchor="w")
    canvas.create_rectangle(px(40), py + px(36), px(304), py + px(62), fill=theme.MAROON, width=0)
    canvas.create_image(px(46), py + px(40), image=sk.get("check", size=px(18), checked=True, state="normal", behind=theme.MAROON), anchor="nw")
    canvas.create_text(px(72), py + px(49), text="Track 1 - eng / AAC / 2 ch", font=theme.font_body(),
                       fill=theme.TEXT_BRIGHT, anchor="w")

    canvas.create_image(px(46), py + px(80), image=sk.get("check", size=px(18), checked=False, state="normal", behind=theme.PANEL_FILL), anchor="nw")
    canvas.create_image(px(74), py + px(80), image=sk.get("check", size=px(18), checked=True, state="hover", behind=theme.PANEL_FILL), anchor="nw")

    # Handles + trim flags on a fake track
    ty = py + px(130)
    canvas.create_rectangle(px(40), ty + px(9), px(300), ty + px(13), fill=theme.SEEK_TRACK,
                            outline=theme.PANEL_BORDER_DIM)
    canvas.create_rectangle(px(40), ty + px(9), px(160), ty + px(13), fill=theme.ACCENT_DEEP, width=0)
    canvas.create_image(px(160), ty, image=sk.get("handle", w=px(12), h=px(22), state="normal", behind=theme.PANEL_FILL), anchor="n")
    canvas.create_image(px(200), ty, image=sk.get("trim_flag", h=px(22), kind="start", behind=theme.PANEL_FILL), anchor="nw")
    canvas.create_image(px(260), ty, image=sk.get("trim_flag", h=px(22), kind="end", behind=theme.PANEL_FILL), anchor="nw")

    # Preview bezel panel
    canvas.create_image(px(360), py, image=sk.get("panel", w=px(420), h=px(240), fill="#0A1626", border=theme.PANEL_BORDER), anchor="nw")
    canvas.create_text(px(570), py + px(120), text="PREVIEW BEZEL", font=theme.font_title(),
                       fill=theme.TEXT_DIM)

    # Wordmark
    canvas.create_image(px(24), px(430), image=sk.get("wordmark", text="CLIPTOOLBOX", size_px=px(42)), anchor="nw")

    # Text ramp in the loaded font
    ty = px(540)
    canvas.create_text(px(24), ty, text="Body text — the quick brown fox 0123456789", font=theme.font_body(), fill=theme.TEXT, anchor="w")
    canvas.create_text(px(24), ty + px(22), text="Dim text — the quick brown fox", font=theme.font_small(), fill=theme.TEXT_DIM, anchor="w")
    canvas.create_text(px(24), ty + px(44), text="BRIGHT SELECTED TEXT", font=theme.font_menu(), fill=theme.TEXT_BRIGHT, anchor="w")

    root.mainloop()


if __name__ == "__main__":
    main()
