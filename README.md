# ClipToolbox

ClipToolbox is a small Windows desktop tool for previewing, mixing, trimming, cropping/zooming, watermarking, exporting, and Discord-size-compressing video clips — wearing a Halo 2 (2004) menu interface, with an optional Halo: Reach skin selectable in Settings.

## Features

### Interface

- Halo 2 (2004) styled interface rendered entirely with Pillow (no ttk): custom borderless window chrome (native snap/resize still work), the silver selection band, chamfered panels
- Optional **Halo: Reach** skin (SETTINGS → Interface, applies on next launch): desaturated slate-and-steel palette, rectangular chrome, party-roster green track bars, and Bahnschrift type (Windows' DIN — falls back to Rajdhani if missing)
- **One adaptive screen**: the editor *is* the workspace, and a full-body empty state — wordmark, drop zone, and a grid of recent-clip thumbnails — lifts over it whenever no clip is loaded (there's no separate landing menu)
- **Command palette** (`Ctrl+K`): a searchable list of every action with its key hint — doubles as the keyboard cheat-sheet
- **First-run coach marks**: a one-time guided overlay points out the timeline gestures, transport, crop, audio mix, and export the first time a clip loads (re-openable from the palette)
- In-window Halo dialogs and toasts instead of native message boxes, an activity log inside the app, and hover tooltips on the less-obvious controls

### Loading clips

- Open a video by dialog, drag-and-drop anywhere on the window, Windows "Open With", or the recent-clips grid (right-click a card to reveal or remove it)
- Reopening a clip **restores its saved setup** — trim points, crop keyframes, and track mix — with a toast that offers to reset to defaults
- **Silent / video-only clips** (screen recordings, muted game clips) are fully supported — no audio track required to preview or export

### Preview & playback

- Live in-window preview with mixed audio; pause/resume is instant and frame-exact, and track toggles / volume changes apply to the running preview without interrupting it
- Two preview engines (SETTINGS → Playback): the lightweight built-in **FFplay** (default), or an optional **mpv** engine (drop `mpv.exe` in an `mpv\` folder — see `docs/BUILD_NOTES.md`) that adds live-frame scrubbing and smoother pause/seek for crop keyframing
- Scrub by dragging the playhead (frames update as you drag), frame-step (`,` / `.`), number-key seeking (`0`–`9` → 0–90%), and a LOOP toggle that loops the trim region (or the whole clip)
- **Preview mouse gestures**: hold left-click to play at 2× while held, double-click to toggle focus mode, right-click to play/pause
- **Focus mode** (`Tab`): collapse everything around the video into a distraction-free view with translucent HUD chips (clip name, timecode) over the letterbox; the timeline strip stays live beneath it and crop editing keeps working
- Save the current frame as a PNG, or copy it straight to the clipboard

### Timeline — trim, crop, navigation

- A multi-lane timeline strip: clip **filmstrip** thumbnails, per-track **waveforms** (tinted by mix state), fat draggable **trim brackets**, an always-visible **keyframe lane**, and export progress painted right on the strip
- **Trim** start/end before export — drag the green/red brackets, type into the IN/OUT timecode fields, or use `[` / `]`; jump to a bracket with `Shift+Home` / `Shift+End`. The ruler is a dedicated scrub lane, so clicking near a bracket seeks precisely instead of nudging the trim, and a single click on a bracket seeks the playhead to it
- **Crop / zoom with keyframes** (`CROP`, `C`): drag the corners of a box over the frame (aspect-locked; `Shift` to stretch), set keyframes at different times (`K`), and export interpolates between them for animated punch-in zooms, pans, and stretches — re-encoded with NVENC only when a crop is active. Two sub-modes: **working mode** (paused, edit the box/keyframes) and **preview mode** (plays the crop back); `Space` or PREVIEW/EDIT flips between them. Keyframe diamonds on the timeline can be dragged to retime or right-clicked to delete
- **Zoom & navigate**: `Ctrl`+scroll zooms the timeline anchored at the cursor (`Ctrl+0` resets), with per-frame ticks once frames are far enough apart. When zoomed, a navigator scrollbar rides the top of the strip (drag to pan, click to jump), middle-drag pans the strip directly, and dragging a bracket / keyframe / playhead to the edge auto-scrolls the view
- **Single-level undo / redo** (`Ctrl+Z`, press again to redo): reverts the last edit — trim, crop keyframes, or track mix

### Audio mixing

- Detects audio tracks and lists them as a roster; enable/disable tracks and adjust per-track volume (0–200%)
- Mute-all (`M`), right-click a row to solo, a RESET button, double-click a slider to snap to 100%, and scroll-wheel over a row to adjust its volume (±5%, `Shift` = ±1%)

### Export & compression

- An **export drawer** (`Ctrl+E` / EXPORT CLIP): pick the destination folder and a filename **pattern** (`{clip} {trim} {crop} {stamp} {size} {res} {date} {time}` tokens with a live resolved-name preview), then START EXPORT straight to disk or SAVE AS… via a dialog
- Export with merged audio — a fast stream copy when nothing needs re-encoding, or an NVENC re-encode when a crop or watermark is active; silent clips export video-only
- Optional **Discord-size compression** with NVIDIA HEVC NVENC and automatic bitrate tuning (keeps the best file under your MB target); optional resolution cap (1080p / 720p / 600p) with a live bitrate estimate
- A persistent **job history** in the drawer: per-job progress and attempt count, final size, and OPEN / FOLDER / RE-RUN (replays a past export verbatim, even after a restart). Export progress also shows on the Windows **taskbar button** and as a completion toast

### Timestamp watermark

- Optionally burn a timestamp/caption bottom-left with a fade-out. SETTINGS control the **text source** (recording time parsed from the filename, the file's creation date, or the full filename), the **date format** (ISO, US, EU, or long "January 5th, 2026"), and whether to include the time of day
- Per export you can override the text: use the configured watermark, your own **custom text** (a freetext field), or **both** stacked (configured on top, custom below)

### Shortcuts & persistence

- Contextual legend bar and full keyboard control: `Space` play/pause, `←`/`→` seek (`Shift` = fine), `[` `]` trim, `Tab` focus, `Ctrl+K` commands, `Ctrl+Z` undo, `Ctrl+E` export, `Ctrl+O` load, `Ctrl+W` close clip, `Ctrl+,` settings, `Ctrl+Shift+C` copy timestamp, `Esc` cancel/close; the scroll wheel seeks over the timeline (±5 s per notch, `Shift` = ±1 s) and the roster/log scroll under it
- Settings persist between sessions (window position, compression + watermark defaults, recent clips, interface skin, playback engine) in a portable `config.json`; each clip's setup persists in `sessions.json` and the export history in `jobs.json`

## Requirements

- Windows 10/11
- Python 3.11 or newer
- FFmpeg, FFprobe, and FFplay executables
- Optional `mpv.exe` for the MPV playback engine (put in `mpv\` next to `ffmpeg\`, or install it on PATH)
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
    core/                 probing, media info, ffmpeg command building, export/
                          compression tuning, crop/zoom motion, the FFplay + optional
                          mpv playback engines, and a background render queue — UI-free
    ui/                   Halo interface (theme, Pillow skins, widgets, commands)
    ui/views/             screen surfaces (workspace, empty state, export drawer,
                          command palette, focus HUD, coach marks, settings)
    ui/skins/             skin token modules (halo2, reach) + registry
    app.py                controller wiring core and UI together
    settings.py           config.json persistence
    sessions.py           per-clip trim/crop/mix restore (sessions.json)
  assets/
    fonts/                Rajdhani (OFL) — loaded privately, never installed
  docs/                   ROADMAP.md (living plan), USABILITY_REPORT.md, BUILD_NOTES.md
  ffmpeg/
    bin/                  put ffmpeg.exe, ffprobe.exe, ffplay.exe here
  mpv/                    optional: put mpv.exe here to bundle the optional MPV playback engine
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
python -m cliptoolbox.ui.gallery --skin reach
```

(`--skin` — or the `CLIPTOOLBOX_SKIN` environment variable, which also works for the app itself — overrides the configured skin for that run.)

## Build an EXE manually

First install the runtime and build dependencies:

```bat
python -m pip install -r requirements.txt
python -m pip install -r requirements-build.txt
```

### Single-file EXE with bundled assets, FFmpeg, and optional mpv

This build keeps the app self-contained in one EXE, including the icon, bundled fonts, the local `ffmpeg` tree, and the optional `mpv` engine when present:

```bat
python -m PyInstaller --onefile --noconsole --name ClipToolbox --icon "assets\ClipToolbox.ico" --collect-all tkinterdnd2 --add-data "assets;assets" --add-data "ffmpeg;ffmpeg" --add-data "mpv;mpv" ClipToolbox.py
```

The finished file is written to:

```txt
dist\ClipToolbox.exe
```

### Folder-based EXE

If you prefer a folder-based build instead of a single EXE, use:

```bat
python -m PyInstaller --onefile --noconsole --name ClipToolbox --icon "assets\ClipToolbox.ico" --collect-all tkinterdnd2 --add-data "assets;assets" --add-data "ffmpeg;ffmpeg" --add-data "mpv;mpv" ClipToolbox.py
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
- Undo is a single level: `Ctrl+Z` reverts the last edit and pressing it again redoes it; the undo state does not carry across clips.
- Settings are stored in `config.json` next to the app (or `%APPDATA%\ClipToolbox` if that folder is not writable); per-clip setups live in `sessions.json` and export history in `jobs.json` alongside it. Delete them to reset.
- The custom borderless chrome can be swapped for the native title bar in SETTINGS (applies on next launch).
- Rajdhani is bundled under the SIL Open Font License (see `assets/fonts/OFL.txt`) and is registered process-private at runtime — nothing is installed system-wide.
