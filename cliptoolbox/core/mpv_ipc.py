"""JSON-IPC client for mpv over a Windows named pipe.

mpv exposes a line-oriented JSON protocol on the pipe named by
--input-ipc-server. Each request is one JSON object per line
({"command": [...], "request_id": n}); replies carry the same request_id;
asynchronous events (including observed property changes) arrive as
{"event": ...} lines.

The pipe is opened with FILE_FLAG_OVERLAPPED and driven with overlapped
ReadFile/WriteFile. This is required, not cosmetic: on a synchronous
(non-overlapped) pipe handle the kernel serializes every I/O operation on the
handle, so the reader thread's blocking ReadFile would stall the command
thread's WriteFile. Overlapped I/O lets both directions proceed independently.

tkinter-free. Events are dispatched on the reader thread; callers marshal to
their UI thread as needed (matching the PlaybackCallbacks contract).
"""
import ctypes
import ctypes.wintypes
import json
import threading
import time

from cliptoolbox.constants import IS_WINDOWS

if IS_WINDOWS:
    _k32 = ctypes.windll.kernel32
    _wt = ctypes.wintypes
    _GENERIC_RW = 0x80000000 | 0x40000000
    _OPEN_EXISTING = 3
    _FILE_FLAG_OVERLAPPED = 0x40000000
    _ERROR_IO_PENDING = 997
    _INFINITE = 0xFFFFFFFF
    _INVALID = ctypes.c_void_p(-1).value

    # Handles are pointer-sized; the default c_int restype would truncate them.
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


class MpvIpcError(Exception):
    pass


class MpvIpcClient:
    def __init__(self, pipe_path: str, on_event=None, on_disconnect=None):
        self._pipe_path = pipe_path
        self._on_event = on_event
        self._on_disconnect = on_disconnect
        self._handle = None
        self._read_evt = None
        self._write_evt = None
        self._req = 0
        self._req_lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._pending: dict[int, tuple] = {}
        self._alive = False
        self._disconnect_fired = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def connect(self, timeout: float = 5.0) -> bool:
        if not IS_WINDOWS:
            return False
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
        threading.Thread(target=self._read_loop, name="mpv-ipc-read", daemon=True).start()
        return True

    @property
    def alive(self) -> bool:
        return self._alive

    def close(self) -> None:
        self._alive = False
        for h in (self._handle, self._read_evt, self._write_evt):
            if h:
                try:
                    _k32.CloseHandle(h)
                except Exception:
                    pass
        self._handle = self._read_evt = self._write_evt = None

    def _mark_dead(self):
        self._alive = False
        if not self._disconnect_fired:
            self._disconnect_fired = True
            # Unblock any pending waiters.
            for ev, slot in list(self._pending.values()):
                ev.set()
            if self._on_disconnect:
                try:
                    self._on_disconnect()
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # I/O
    # ------------------------------------------------------------------

    def _read_loop(self):
        buf = b""
        chunk = ctypes.create_string_buffer(8192)
        nread = _wt.DWORD(0)
        while self._alive:
            ov = _OVERLAPPED()
            ov.hEvent = self._read_evt
            # Reset first: a manual-reset event stays signaled from the prior
            # completed read, which would make GetOverlappedResult below return
            # on stale state and false-break the loop.
            _k32.ResetEvent(self._read_evt)
            ok = _k32.ReadFile(self._handle, chunk, 8192, ctypes.byref(nread), ctypes.byref(ov))
            if not ok:
                if ctypes.GetLastError() != _ERROR_IO_PENDING:
                    break  # pipe error (e.g. 109 ERROR_BROKEN_PIPE on mpv quit)
                _k32.WaitForSingleObject(self._read_evt, _INFINITE)
                if not _k32.GetOverlappedResult(self._handle, ctypes.byref(ov),
                                                ctypes.byref(nread), True):
                    break
            if nread.value == 0:
                break  # pipe closed by mpv
            buf += chunk.raw[:nread.value]
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                if line.strip():
                    self._handle_line(line)
        self._mark_dead()

    def _handle_line(self, line: bytes):
        try:
            msg = json.loads(line.decode("utf-8", "replace"))
        except ValueError:
            return
        rid = msg.get("request_id")
        if rid is not None and rid in self._pending:
            ev, slot = self._pending.pop(rid)
            slot.append(msg)
            ev.set()
        elif "event" in msg and self._on_event:
            try:
                self._on_event(msg)
            except Exception:
                pass

    def _write(self, obj: dict):
        payload = (json.dumps(obj) + "\n").encode("utf-8")
        written = _wt.DWORD(0)
        with self._write_lock:
            if not self._alive or not self._handle:
                raise MpvIpcError("pipe closed")
            ov = _OVERLAPPED()
            ov.hEvent = self._write_evt
            _k32.ResetEvent(self._write_evt)
            ok = _k32.WriteFile(self._handle, payload, len(payload),
                                ctypes.byref(written), ctypes.byref(ov))
            if not ok:
                if ctypes.GetLastError() != _ERROR_IO_PENDING:
                    self._mark_dead()
                    raise MpvIpcError("WriteFile failed")
                _k32.WaitForSingleObject(self._write_evt, _INFINITE)
                if not _k32.GetOverlappedResult(self._handle, ctypes.byref(ov),
                                                ctypes.byref(written), True):
                    self._mark_dead()
                    raise MpvIpcError("WriteFile overlapped failed")

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def command(self, *args, timeout: float = 2.0):
        """Send a command and wait for its reply. Returns the reply's data or
        raises MpvIpcError on failure/timeout."""
        with self._req_lock:
            self._req += 1
            rid = self._req
        ev = threading.Event()
        slot: list = []
        self._pending[rid] = (ev, slot)
        try:
            self._write({"command": list(args), "request_id": rid})
        except MpvIpcError:
            self._pending.pop(rid, None)
            raise
        if not ev.wait(timeout):
            self._pending.pop(rid, None)
            raise MpvIpcError(f"mpv command timed out: {args}")
        if not self._alive:
            raise MpvIpcError("pipe closed")
        reply = slot[0]
        if reply.get("error") not in (None, "success"):
            raise MpvIpcError(f"mpv error: {reply.get('error')} for {args}")
        return reply.get("data")

    def command_async(self, *args) -> None:
        """Fire-and-forget: the reply comes back with a request_id we never
        registered, so _handle_line simply drops it. (No "async" field — mpv's
        async flag changes reply semantics and is unnecessary here.)"""
        with self._req_lock:
            self._req += 1
            rid = self._req
        try:
            self._write({"command": list(args), "request_id": rid})
        except MpvIpcError:
            pass

    def get_property(self, name: str, timeout: float = 2.0):
        return self.command("get_property", name, timeout=timeout)

    def set_property(self, name: str, value) -> None:
        self.command_async("set_property", name, value)

    def observe_property(self, obs_id: int, name: str) -> None:
        try:
            self._write({"command": ["observe_property", obs_id, name]})
        except MpvIpcError:
            pass
