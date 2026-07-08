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

Development extras:

- `python -m cliptoolbox.ui.gallery` shows every themed widget/state for UI work.
- `python tools\dump_commands.py` prints the exact FFmpeg commands the core produces for fixed inputs — run before/after refactors to prove the trim/compression logic is unchanged.
- Core logic (`cliptoolbox\core\`) never imports tkinter; UI changes should leave it untouched in diffs.
