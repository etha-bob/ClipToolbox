# Build notes

Recommended development flow:

1. Install Python 3.11 or newer with **Add Python to PATH** enabled.
2. Open Command Prompt in the `ClipToolbox` folder.
3. Install runtime dependencies:

```bat
python -m pip install -r requirements.txt
```

4. Put `ffmpeg.exe`, `ffprobe.exe`, and `ffplay.exe` into `ffmpeg\bin\`.
5. Test from source:

```bat
python ClipToolbox.py
```

6. Install build dependencies only when you are ready to make an EXE:

```bat
python -m pip install -r requirements-build.txt
```

7. Build with PyInstaller (`--add-data` bundles the Rajdhani fonts the UI loads):

```bat
python -m PyInstaller --onedir --noconsole --name ClipToolbox --collect-all tkinterdnd2 --add-data "assets;assets" ClipToolbox.py
```

8. Copy the local `ffmpeg` folder into `dist\ClipToolbox\` so it sits next to `ClipToolbox.exe`.

The app supports PyInstaller onedir layout. The `ffmpeg` folder should live next to the EXE after building; the `assets` folder is looked up both next to the EXE and inside `_internal\` (PyInstaller 5/6 differ).

## Optional: mpv playback engine

ClipToolbox ships with the lightweight FFplay preview engine by default. An optional **mpv** engine gives smoother pausing and live-frame scrubbing, which helps a lot when placing crop keyframes. It is entirely optional — the app falls back to FFplay when mpv is absent, and Settings → Playback → Engine greys out the MPV choice.

To enable it:

1. Download a Windows mpv build from https://mpv.io/installation/ (the shinchiro or zhongfly builds — gyan.dev ships ffmpeg only, no mpv). Use `mpv.exe`, not the `mpv.com` console wrapper.
2. Create an `mpv\` folder next to `ffmpeg\` and drop `mpv.exe` into it (so `mpv\mpv.exe`). It is also found on PATH.
3. Validate the build: `python tools\spike_mpv.py` — all checks must pass.
4. Pick it in Settings → Playback → Engine (or set `playback_engine` to `mpv` in `config.json`).

`ClipToolbox.spec` bundles the `mpv\` folder automatically **only if it exists** at build time, so builds without mpv still succeed. To rip mpv out entirely, delete `cliptoolbox\core\playback_mpv.py`, `cliptoolbox\core\mpv_ipc.py`, and `tools\spike_mpv.py`, then remove the mpv branch from `cliptoolbox\core\engine_factory.py` — nothing else imports them.

Development extras:

- `python -m cliptoolbox.ui.gallery` shows every themed widget/state for UI work.
- `python tools\dump_commands.py` prints the exact FFmpeg commands the core produces for fixed inputs — run before/after refactors to prove the trim/compression logic is unchanged.
- Core logic (`cliptoolbox\core\`) never imports tkinter; UI changes should leave it untouched in diffs.
- `cliptoolbox\core\playback.py` owns the preview pipeline (FFmpeg → pre-scaled rawvideo/PCM over a NUT pipe → embedded FFplay). Pause/resume post FFplay's own pause key; track volumes go through FFmpeg runtime filter commands on stdin. Two hard-won rules: never suspend the FFplay process (a suspended window freezes Tk on the next activation/z-order change), and never show the SDL window before `SetParent` (that is the white-flash race).
