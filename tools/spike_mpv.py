"""Validation spike for an optional mpv playback engine (JSON IPC over a named
pipe, embedded via --wid). GATE for all mpv work: if a hard check fails here,
the engine design changes before any of cliptoolbox is touched.

    python tools/spike_mpv.py [--keep] [--show]

Needs an mpv.exe (a Windows build from https://mpv.io/installation/ —
shinchiro/zhongfly; gyan.dev ships ffmpeg only). Looked up in the mpv folder
next to ffmpeg, then on PATH. Uses the bundled ffmpeg to synthesize a
4-quadrant, 2-audio-stream test clip.

Findings (mpv v0.40.0, Windows 11, 2026-07):
    - t semantics: CONFIRMED absolute source PTS. Crop expressions built with
      time_offset=0 render correctly after seeks to 3.0 s and 7.5 s. The engine
      therefore queries its provider with start_seconds=0.0 (no -ss rebase).
    - conceal capture: PrintWindow(PW_RENDERFULLCONTENT) on mpv's gpu VO is
      usable, but occasionally black right after a seek (swapchain not yet
      presented). The engine captures like ffplay AND the crop editor/wheel
      freeze fall back to extracted JPEG stills, so an occasional black grab is
      harmless. mpv's own screenshot-to-file is the fully reliable path.
    - live lavfi-complex re-set: time-pos stays monotonic across 10 swaps; no
      audible disruption in the spike. Live volume rebuilds the graph through a
      coalescing writer (one rebuild per burst).
    - stop/idle keep-alive + loadfile-after-stop + keep-open eof-reached + quit:
      all pass. Process survives `stop`; instant warm restarts confirmed.
"""
import argparse
import ctypes
import ctypes.wintypes
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cliptoolbox.core import motion, paths
from cliptoolbox.core.motion import CropKeyframe, CropTrack

SRC_W, SRC_H = 1920, 1080
DURATION = 12.0
failures: list[str] = []


def check(label: str, ok: bool, detail: str = ""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f"  ({detail})" if detail else ""))
    if not ok:
        failures.append(label)


def find_mpv() -> str | None:
    local = paths.RESOURCE_DIR / "mpv" / "mpv.exe"
    if local.exists():
        return str(local)
    # Prefer mpv.exe over mpv.com: the .com console wrapper re-execs mpv.exe
    # under a different PID, which breaks --wid child-window lookup + IPC.
    return shutil.which("mpv.exe") or shutil.which("mpv")


# ---------------------------------------------------------------------------
# Minimal JSON-IPC client (seeds cliptoolbox/core/mpv_ipc.py)
# ---------------------------------------------------------------------------
_k32 = ctypes.windll.kernel32
_GENERIC_RW = 0x80000000 | 0x40000000
_OPEN_EXISTING = 3
_FILE_FLAG_OVERLAPPED = 0x40000000
_ERROR_IO_PENDING = 997
_INVALID = ctypes.c_void_p(-1).value
_wt = ctypes.wintypes
# Handles are pointer-sized (64-bit); default restype c_int would truncate.
_k32.CreateFileW.argtypes = [_wt.LPCWSTR, _wt.DWORD, _wt.DWORD, ctypes.c_void_p,
                             _wt.DWORD, _wt.DWORD, ctypes.c_void_p]
_k32.CreateFileW.restype = ctypes.c_void_p
_k32.CreateEventW.argtypes = [ctypes.c_void_p, _wt.BOOL, _wt.BOOL, _wt.LPCWSTR]
_k32.CreateEventW.restype = ctypes.c_void_p
for _fn in (_k32.ReadFile, _k32.WriteFile):
    _fn.argtypes = [ctypes.c_void_p, ctypes.c_void_p, _wt.DWORD, ctypes.c_void_p,
                    ctypes.c_void_p]
_k32.GetOverlappedResult.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                                     ctypes.c_void_p, _wt.BOOL]
_k32.WaitForSingleObject.argtypes = [ctypes.c_void_p, _wt.DWORD]
_k32.ResetEvent.argtypes = [ctypes.c_void_p]
_k32.CloseHandle.argtypes = [ctypes.c_void_p]


class _OVERLAPPED(ctypes.Structure):
    _fields_ = [("Internal", ctypes.c_void_p), ("InternalHigh", ctypes.c_void_p),
                ("Offset", _wt.DWORD), ("OffsetHigh", _wt.DWORD),
                ("hEvent", ctypes.c_void_p)]


class IpcClient:
    """Duplex JSON-IPC over a Win32 named pipe via raw CreateFile/ReadFile/
    WriteFile. A single handle supports a blocking ReadFile on the reader
    thread concurrently with WriteFile on the command thread — the kernel
    serializes per direction (Python's buffered open() cannot, hence ctypes)."""

    def __init__(self, pipe_path):
        self._pipe_path = pipe_path
        self._handle = None
        self._read_evt = None
        self._write_evt = None
        self._req = 0
        self._pending = {}
        self._lock = threading.Lock()
        self._events = []
        self._props = {}
        self._alive = False

    def connect(self, timeout=5.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            h = _k32.CreateFileW(self._pipe_path, _GENERIC_RW, 0, None,
                                 _OPEN_EXISTING, _FILE_FLAG_OVERLAPPED, None)
            if h != _INVALID:
                self._handle = h
                break
            time.sleep(0.05)
        if self._handle is None:
            return False
        self._read_evt = _k32.CreateEventW(None, True, False, None)
        self._write_evt = _k32.CreateEventW(None, True, False, None)
        self._alive = True
        threading.Thread(target=self._read_loop, daemon=True).start()
        return True

    def _read_loop(self):
        buf = b""
        chunk = ctypes.create_string_buffer(4096)
        nread = _wt.DWORD(0)
        while self._alive:
            ov = _OVERLAPPED()
            ov.hEvent = self._read_evt
            _k32.ResetEvent(self._read_evt)  # avoid stale-signal false-break
            ok = _k32.ReadFile(self._handle, chunk, 4096, ctypes.byref(nread), ctypes.byref(ov))
            if not ok:
                if ctypes.GetLastError() != _ERROR_IO_PENDING:
                    break
                _k32.WaitForSingleObject(self._read_evt, 0xFFFFFFFF)
                if not _k32.GetOverlappedResult(self._handle, ctypes.byref(ov),
                                                ctypes.byref(nread), True):
                    break
            if nread.value == 0:
                break
            buf += chunk.raw[:nread.value]
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                if not line.strip():
                    continue
                try:
                    msg = json.loads(line.decode("utf-8", "replace"))
                except ValueError:
                    continue
                if "request_id" in msg and msg["request_id"] in self._pending:
                    ev, slot = self._pending.pop(msg["request_id"])
                    slot.append(msg)
                    ev.set()
                elif "event" in msg:
                    if msg["event"] == "property-change":
                        self._props[msg.get("name")] = msg.get("data")
                    self._events.append(msg)
        self._alive = False

    def _write(self, payload: bytes):
        written = _wt.DWORD(0)
        with self._lock:
            ov = _OVERLAPPED()
            ov.hEvent = self._write_evt
            _k32.ResetEvent(self._write_evt)
            ok = _k32.WriteFile(self._handle, payload, len(payload),
                                ctypes.byref(written), ctypes.byref(ov))
            if not ok:
                if ctypes.GetLastError() != _ERROR_IO_PENDING:
                    raise OSError(f"WriteFile failed err={ctypes.GetLastError()}")
                _k32.WaitForSingleObject(self._write_evt, 0xFFFFFFFF)
                if not _k32.GetOverlappedResult(self._handle, ctypes.byref(ov),
                                                ctypes.byref(written), True):
                    raise OSError(f"WriteFile overlapped failed err={ctypes.GetLastError()}")

    def command(self, *args, timeout=2.0):
        self._req += 1
        rid = self._req
        ev = threading.Event()
        slot = []
        self._pending[rid] = (ev, slot)
        self._write(json.dumps({"command": list(args), "request_id": rid}).encode() + b"\n")
        if not ev.wait(timeout):
            self._pending.pop(rid, None)
            raise TimeoutError(f"mpv command timed out: {args}")
        return slot[0]

    def set_property(self, name, value):
        return self.command("set_property", name, value)

    def get_property(self, name):
        return self.command("get_property", name).get("data")

    def observe(self, name):
        self._req += 1
        self._write(json.dumps({"command": ["observe_property", self._req, name]}).encode() + b"\n")

    def close(self):
        self._alive = False
        if self._handle:
            try:
                _k32.CloseHandle(self._handle)
            except Exception:
                pass
            self._handle = None


# ---------------------------------------------------------------------------
# Child-window discovery + capture (seeds win32.find_child_window_for_pid)
# ---------------------------------------------------------------------------
def find_child_hwnd(parent_hwnd, pid, timeout=2.0):
    from cliptoolbox.core import win32
    user32 = ctypes.windll.user32
    EnumChildWindows = user32.EnumChildWindows
    PROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    deadline = time.time() + timeout
    while time.time() < deadline:
        found = []

        def cb(hwnd, _):
            p = ctypes.c_ulong()
            win32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
            if p.value == pid:
                found.append((hwnd, win32._window_class(hwnd)))
            return True

        EnumChildWindows(parent_hwnd, PROC(cb), 0)
        for hwnd, cls in found:
            if cls == "mpv":
                return hwnd
        if found:
            return found[0][0]
        time.sleep(0.05)
    return None


def dominant(bgra, w, h, fx, fy):
    off = (fy * w + fx) * 4
    b, g, r = bgra[off], bgra[off + 1], bgra[off + 2]
    if r > 140 and g > 140 and b < 110:
        return "yellow"
    if r > 140 and g < 110 and b < 110:
        return "red"
    if g > 140 and r < 110 and b < 110:
        return "lime"
    if b > 140 and r < 110 and g < 110:
        return "blue"
    return f"other({r},{g},{b})"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--show", action="store_true", help="leave the window visible")
    args = ap.parse_args()

    mpv = find_mpv()
    if not mpv:
        print("mpv.exe not found (mpv\\ folder or PATH). See https://mpv.io/installation/")
        return 2
    if not paths.FFMPEG:
        print("bundled ffmpeg not found")
        return 2
    print(f"mpv: {mpv}")

    import tempfile
    workdir = Path(tempfile.mkdtemp(prefix="spike_mpv_"))
    src = workdir / "quad.mp4"
    quad = "color={c}:s=960x540:r=60"
    subprocess.run(
        [paths.FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", quad.format(c="red"),
         "-f", "lavfi", "-i", quad.format(c="lime"),
         "-f", "lavfi", "-i", quad.format(c="blue"),
         "-f", "lavfi", "-i", quad.format(c="yellow"),
         "-f", "lavfi", "-i", "sine=frequency=440:r=48000",
         "-f", "lavfi", "-i", "sine=frequency=880:r=48000",
         "-filter_complex", "[0][1]hstack[t];[2][3]hstack[b];[t][b]vstack[v]",
         "-map", "[v]", "-map", "4:a", "-map", "5:a", "-t", f"{DURATION}",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(src)],
        check=True,
    )
    print(f"source: {src}")

    import tkinter as tk
    root = tk.Tk()
    root.title("spike_mpv")
    root.geometry("960x540+80+80")
    host = tk.Frame(root, bg="black", width=960, height=540)
    host.pack(fill="both", expand=True)
    root.update_idletasks(); root.update()
    wid = host.winfo_id()

    pipe = rf"\\.\pipe\cliptoolbox-mpv-spike-{os.getpid()}"
    cmd = [
        mpv, f"--wid={wid}", f"--input-ipc-server={pipe}",
        "--no-config", "--idle=yes", "--force-window=yes", "--keep-open=yes",
        "--pause", "--hr-seek=yes", "--hwdec=no", "--no-osc", "--no-osd-bar",
        "--osd-level=0", "--no-input-default-bindings", "--input-vo-keyboard=no",
        "--no-border", "--msg-level=all=error", str(src),
    ]
    CREATE_NO_WINDOW = 0x08000000
    proc = subprocess.Popen(cmd, stderr=subprocess.PIPE, creationflags=CREATE_NO_WINDOW)

    from cliptoolbox.core import win32
    ipc = IpcClient(pipe)

    def pump(seconds):
        end = time.time() + seconds
        while time.time() < end:
            root.update_idletasks(); root.update()
            time.sleep(0.02)

    try:
        # 1. IPC connect + version
        t0 = time.time()
        connected = ipc.connect(timeout=3.0)
        check("IPC connects", connected)
        if not connected:
            return 1
        ver = ipc.get_property("mpv-version")
        check("mpv-version answers <=2s", ver is not None and time.time() - t0 < 2.0,
              f"{ver}, {time.time()-t0:.2f}s")
        ipc.observe("time-pos"); ipc.observe("pause"); ipc.observe("eof-reached")
        pump(0.5)

        # 2. child hwnd found
        child = find_child_hwnd(wid, proc.pid, timeout=2.0)
        check("mpv child window found under host", child is not None, f"hwnd={child}")

        # 3 + 4. exact seek while paused repaints; t semantics
        track = CropTrack(); track.enabled = True
        track.upsert(CropKeyframe(0.0, 0, 0, 1920, 1080), 0.01)
        track.upsert(CropKeyframe(3.0, 0, 0, 960, 540), 0.01)      # red quadrant
        track.upsert(CropKeyframe(7.5, 960, 540, 960, 540), 0.01)  # yellow quadrant
        chain = motion.build_motion_chain(track, SRC_W, SRC_H, 960, 540, time_offset=0.0)
        ipc.set_property("lavfi-complex", f"[vid1]{chain}[vo]")
        pump(0.4)

        from PIL import Image

        def shot_center(tag):
            """mpv's own screenshot: reliable for the gpu VO regardless of
            whether PrintWindow can grab the swapchain."""
            p = workdir / f"shot_{tag}.png"
            ipc.command("screenshot-to-file", str(p), "window")
            pump(0.15)
            if not p.exists():
                return None
            im = Image.open(p).convert("RGB")
            w, h = im.size
            r, g, b = im.getpixel((w // 2, h // 2))
            if r > 140 and g > 140 and b < 110:
                return "yellow"
            if r > 140 and g < 110 and b < 110:
                return "red"
            if g > 140 and r < 110 and b < 110:
                return "lime"
            if b > 140 and r < 110 and g < 110:
                return "blue"
            return f"other({r},{g},{b})"

        ipc.set_property("pause", True)
        ipc.command("seek", 3.0, "absolute+exact")
        pump(0.5)
        c3 = shot_center("t3")
        check("t semantics: t=3.0 shows red quadrant", c3 == "red", f"center={c3}")

        ipc.command("seek", 7.5, "absolute+exact")
        pump(0.5)
        c7 = shot_center("t7")
        check("t semantics: t=7.5 shows yellow quadrant", c7 == "yellow", f"center={c7}")

        # Finding: can PrintWindow grab mpv's window (informs conceal design)?
        cap = win32.capture_window_frame(child)
        printwindow_ok = cap is not None and any(cap[0][:4096])
        print(f"    (finding) PrintWindow capture of mpv gpu VO: "
              f"{'usable' if printwindow_ok else 'BLACK — conceal must rely on extracted stills'}")

        # 5. two-track amix graph accepted + track order
        graph = ("[aid1]volume=1.000[a0];[aid2]volume=0.000[a1];"
                 "[a0][a1]amix=inputs=2:duration=longest:normalize=0[ao];"
                 f"[vid1]{chain}[vo]")
        r = ipc.set_property("lavfi-complex", graph)
        check("2-track amix graph accepted", r.get("error") == "success", r.get("error"))
        tl = ipc.get_property("track-list")
        audio = [t for t in (tl or []) if t.get("type") == "audio"]
        check("2 audio tracks visible in order", len(audio) == 2,
              f"{[t.get('id') for t in audio]}")

        # 6. live graph re-set x10 keeps time-pos monotonic; measure hiccup
        ipc.set_property("pause", False)
        pump(0.3)
        last = ipc.get_property("time-pos") or 0.0
        monotonic = True
        max_gap = 0.0
        for i in range(10):
            g = ("[aid1]volume=1.000[a0];[aid2]volume=%0.3f[a1];"
                 "[a0][a1]amix=inputs=2:duration=longest:normalize=0[ao];"
                 f"[vid1]{chain}[vo]") % (i / 10.0)
            t_before = time.time()
            ipc.set_property("lavfi-complex", g)
            pump(0.18)
            now = ipc.get_property("time-pos") or 0.0
            if now < last - 0.05:
                monotonic = False
            max_gap = max(max_gap, abs((time.time() - t_before)))
            last = now
        check("live lavfi-complex re-set keeps time-pos monotonic", monotonic,
              f"last={last:.2f}")
        print(f"    (soft) live graph swap wall-time up to {max_gap*1000:.0f} ms/iter")

        # 7. pause latency
        ipc.set_property("pause", True); pump(0.2)
        t = time.time(); ipc.set_property("pause", False); lat1 = time.time() - t
        t = time.time(); ipc.set_property("pause", True); lat2 = time.time() - t
        check("pause round-trip < 150 ms", max(lat1, lat2) < 0.15,
              f"{lat1*1000:.0f}/{lat2*1000:.0f} ms")

        # 8. stop + idle keep-alive, then reload works
        ipc.command("stop"); pump(0.4)
        alive = proc.poll() is None
        check("process survives stop (--idle)", alive)
        ipc.set_property("pause", True)
        ipc.command("loadfile", str(src), "replace"); pump(0.6)
        reloaded = (ipc.get_property("duration") or 0) > 1.0
        check("loadfile after stop works", reloaded,
              f"duration={ipc.get_property('duration')}")

        # 9. keep-open -> eof-reached observable
        ipc.command("seek", DURATION - 0.3, "absolute+exact")
        ipc.set_property("pause", False)
        pump(1.5)
        eof = ipc._props.get("eof-reached")
        check("eof-reached observed at end (keep-open)", bool(eof), f"eof={eof}")
        check("process still alive at eof", proc.poll() is None)

        # 10. quit
        t = time.time()
        ipc.command("quit")
        try:
            proc.wait(timeout=1.5)
            check("quit exits <=1.5s", True, f"{time.time()-t:.2f}s")
        except subprocess.TimeoutExpired:
            check("quit exits <=1.5s", False)

    finally:
        if args.show:
            pump(3.0)
        try:
            proc.kill()
        except Exception:
            pass
        ipc.close()
        root.destroy()
        if not args.keep:
            for f in workdir.iterdir():
                f.unlink(missing_ok=True)
            workdir.rmdir()

    print(f"\n{'ALL CHECKS PASSED' if not failures else str(len(failures)) + ' FAILURE(S): ' + ', '.join(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
