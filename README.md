# ClipToolbox

ClipToolbox is a small Windows desktop tool for previewing, mixing, trimming, exporting, and Discord-size-compressing video clips — wearing a Halo 2 (2004) menu interface.

![UI style: deep navy panels, chamfered corners, slanted gradient bars, Rajdhani type]()

## Features

- Halo 2 styled interface: main-menu landing screen, pregame-lobby workspace, custom borderless window chrome (native snap/resize still work)
- Load a video file (dialog, drag-and-drop anywhere, Windows "Open With", or recent-clips list)
- Detect audio tracks; enable/disable tracks and adjust per-track volume (0–200%), with mute-all (`M`), right-click solo, a RESET button, and double-click a slider to reset it to 100%
- Live preview with mixed audio, embedded in the window; pause/resume are instant and frame-exact, track toggles and volume changes apply to the running preview without interrupting it, and scrubbing shows frames as you drag
- Frame-step (`,` / `.`), number-key seeking (`0`–`9` → 0–90%), and a LOOP toggle that loops the trim region (or the whole clip)
- Trim start/end before export, with green/red trim brackets on the timeline you can drag directly, plus editable IN/OUT timecode fields and jump-to-trim (`Shift+Home`/`Shift+End`)
- Save the current frame as a PNG, or copy it straight to the clipboard
- Export video with merged audio (video stream copy, AAC mix)
- Optional Discord-size compression using NVIDIA HEVC NVENC with automatic bitrate tuning (keeps the best file under your MB target)
- Optional max compression resolution: 1080p, 720p, or 600p, plus a live bitrate estimate
- Keyboard shortcuts with a contextual legend bar: `Space` play/pause, `←`/`→` seek (Shift = fine), `[` `]` set trim, `Ctrl+O` load, `Ctrl+E` export, `Esc` back/cancel
- Scroll wheel: seek over the timeline (±5 s per notch, `Shift` = ±1 s) and adjust a track's volume over its roster row (±5%, `Shift` = ±1%); the roster and activity log scroll under the wheel too
- Recent clips show thumbnails on the landing screen (right-click to reveal or remove); right-click the header to reveal the loaded clip; `Ctrl+,` opens Settings; `Ctrl+Shift+C` copies the current timestamp; hover tooltips on the less-obvious controls
- Export-complete toast with an OPEN FOLDER button; in-window Halo dialogs instead of native message boxes
- Activity log inside the app
- Settings persist between sessions (window position, compression defaults, recent clips) in a portable `config.json`

## Requirements

- Windows 10/11
- Python 3.11 or newer
- FFmpeg, FFprobe, and FFplay executables
- NVIDIA GPU and NVIDIA driver if you want Discord compression mode

Python packages are listed in `requirements.txt` (unchanged — the UI is rendered with Pillow):

```txt
pillow
tkinterdnd2
```

For building an EXE, install the extra build package listed in `requirements-build.txt`:

```txt
pyinstaller
```

## Folder layout

```txt
ClipToolbox/
  ClipToolbox.py          entry point (thin shim)
  cliptoolbox/
    core/                 probing, ffmpeg command building, export/compression
                          tuning, preview pipelines — UI-free logic
    ui/                   Halo 2 interface (theme, Pillow skin, widgets, views)
    app.py                controller wiring core and UI together
    settings.py           config.json persistence
  assets/
    fonts/                Rajdhani (OFL) — loaded privately, never installed
  ffmpeg/
    bin/                  put ffmpeg.exe, ffprobe.exe, ffplay.exe here
  outputs/                default export folder (auto-created)
```

The UI/logic split is deliberate: everything that touches FFmpeg lives under `cliptoolbox/core/` and does not import tkinter, so diffs to the interface never touch trimming/compression logic. `tools/dump_commands.py` prints the exact FFmpeg commands the core generates for fixed inputs, to verify parity across refactors.

This source package includes the folder structure, but not the FFmpeg executable files. Put your own FFmpeg files into `ffmpeg/bin/` (with them missing, the app also looks on PATH).

## First-time setup from source

Open Command Prompt in the `ClipToolbox` folder.

Install the Python dependencies:

```bat
python -m pip install -r requirements.txt
```

Put these files into `ffmpeg\bin\`:

```txt
ffmpeg.exe
ffprobe.exe
ffplay.exe
```

Run the app:

```bat
python ClipToolbox.py
```

To iterate on the interface there is also a widget gallery:

```bat
python -m cliptoolbox.ui.gallery
```

## Build an EXE manually

First install the runtime and build dependencies:

```bat
python -m pip install -r requirements.txt
python -m pip install -r requirements-build.txt
```

### Single-file EXE with bundled assets and FFmpeg

This build keeps the app self-contained in one EXE, including the icon, bundled fonts, and the local `ffmpeg` tree:

```bat
python -m PyInstaller --onefile --noconsole --name ClipToolbox --icon "assets\ClipToolbox.ico" --collect-all tkinterdnd2 --add-data "assets;assets" --add-data "ffmpeg;ffmpeg" ClipToolbox.py
```

The finished file is written to:

```txt
dist\ClipToolbox.exe
```

### Folder-based EXE

If you prefer a folder-based build instead of a single EXE, use:

```bat
python -m PyInstaller --onedir --noconsole --name ClipToolbox --icon "assets\ClipToolbox.ico" --collect-all tkinterdnd2 --add-data "assets;assets" --add-data "ffmpeg;ffmpeg" ClipToolbox.py
```

After the build finishes, the app can be run from:

```txt
dist\ClipToolbox\ClipToolbox.exe
```

## NVENC check

To confirm your FFmpeg build supports NVIDIA HEVC compression, run this from the `ClipToolbox` folder:

```bat
ffmpeg\bin\ffmpeg.exe -hide_banner -encoders | findstr nvenc
```

You want to see:

```txt
h264_nvenc
hevc_nvenc
```

If `hevc_nvenc` is missing, normal merging/export can still work, but Discord compression will fail.

## Notes

- The target MB field is treated as Windows/Discord-style MB, meaning MiB internally.
- Default compression target is 9.99 MB.
- Compressed audio is encoded at 64 kbps AAC.
- Compression keeps the largest successful output under the selected limit.
- Settings are stored in `config.json` next to the app (or `%APPDATA%\ClipToolbox` if that folder is not writable). Delete it to reset.
- The custom borderless chrome can be swapped for the native title bar in SETTINGS (applies on next launch).
- Rajdhani is bundled under the SIL Open Font License (see `assets/fonts/OFL.txt`) and is registered process-private at runtime — nothing is installed system-wide.
