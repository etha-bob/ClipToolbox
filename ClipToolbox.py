"""ClipToolbox entry point.

The application lives in the cliptoolbox package:
  - cliptoolbox/core/  — probing, ffmpeg command building, export/compression
                          tuning, preview pipelines (UI-free)
  - cliptoolbox/ui/    — the Halo 2 styled interface
  - cliptoolbox/app.py — the controller wiring them together

This shim keeps the historical PyInstaller entry command and Windows
"Open With" behavior working unchanged.
"""
from cliptoolbox.app import main

if __name__ == "__main__":
    main()
