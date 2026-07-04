# ClipToolbox

ClipToolbox is a small Windows desktop tool for previewing, mixing, trimming, exporting, and Discord-size-compressing video clips.

## Features

- Load a video file
- Detect audio tracks
- Enable/disable tracks and adjust track volume
- Live preview with mixed audio
- Trim start/end before export
- Export video with merged audio
- Optional Discord-size compression using NVIDIA HEVC NVENC
- Optional max compression resolution: 1080p, 720p, or 600p
- Activity log inside the app

## Requirements

- Windows 10/11
- Python 3.11 or newer
- FFmpeg, FFprobe, and FFplay executables
- NVIDIA GPU and NVIDIA driver if you want Discord compression mode

Python packages are listed in `requirements.txt`:

```txt
pillow
tkinterdnd2
```

For building an EXE, install the extra build package listed in `requirements-build.txt`:

```txt
pyinstaller
```

## Folder layout

The app expects FFmpeg tools here:

```txt
ClipToolbox/
  ClipToolbox.py
  requirements.txt
  ffmpeg/
    bin/
      ffmpeg.exe
      ffprobe.exe
      ffplay.exe
```

This source package includes the folder structure, but not the FFmpeg executable files. Put your own FFmpeg files into `ffmpeg/bin/`.

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

## Build an EXE manually

First install the runtime and build dependencies:

```bat
python -m pip install -r requirements.txt
python -m pip install -r requirements-build.txt
```

Then build the app:

```bat
python -m PyInstaller --onedir --noconsole --name ClipToolbox --collect-all tkinterdnd2 ClipToolbox.py
```

After the build finishes, copy the local `ffmpeg` folder next to the EXE:

```txt
dist\ClipToolbox\
  ClipToolbox.exe
  ffmpeg\
    bin\
      ffmpeg.exe
      ffprobe.exe
      ffplay.exe
```

Run the built app from:

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
