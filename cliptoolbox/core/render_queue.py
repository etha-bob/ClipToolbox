"""Background render queue — a bounded worker pool for short-lived media jobs.

Pure Python: this module never imports or touches Tk. Results are handed back
to the Tk main thread by a caller-supplied ``marshal`` callable (in the app
that is ``HaloApp.ui``, which only does a thread-safe ``queue.put``). Workers
therefore only ever produce plain data; Tk resources (e.g. ``ImageTk.PhotoImage``)
must be built on the Tk thread inside the marshaled ``on_done`` callback.

Prerequisite infrastructure for the bold-track timeline (B1) and export drawer
(B4), which fan out many frame/waveform jobs. Replaces the ad-hoc
``threading.Thread`` per thumbnail the empty state used to spawn.

Features:
  * bounded concurrency (a fixed pool of daemon workers),
  * dedup/coalescing by ``key`` (identical in-flight work runs once; every
    caller's callbacks fan out on completion),
  * priority (min-heap; lower runs sooner — B1 can push on-screen frames ahead),
  * group cancellation (drop pending jobs and kill running subprocesses),
  * clean shutdown.
"""

import itertools
import queue
import threading


class CancelToken:
    """Handed to a job's ``work`` function so it can notice cancellation and
    register a subprocess to be killed if the job is cancelled mid-flight."""

    def __init__(self):
        self._cancelled = threading.Event()
        self._process = None
        self._lock = threading.Lock()

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    def attach_process(self, process):
        """Register the live subprocess for this job. If cancellation already
        happened, kill it immediately (the work function raced the cancel)."""
        with self._lock:
            self._process = process
            already = self._cancelled.is_set()
        if already:
            self._kill(process)

    def _cancel(self):
        with self._lock:
            self._cancelled.set()
            process = self._process
        if process is not None:
            self._kill(process)

    @staticmethod
    def _kill(process):
        try:
            process.terminate()
        except Exception:
            pass


class _Job:
    __slots__ = ("key", "work", "group", "callbacks", "token", "cancelled")

    def __init__(self, key, work, group):
        self.key = key
        self.work = work
        self.group = group
        # list of (on_done, on_error); coalesced across duplicate submits
        self.callbacks = []
        self.token = CancelToken()
        self.cancelled = False


class RenderQueue:
    """A bounded pool of daemon workers draining a priority queue.

    ``marshal(callback, *args)`` schedules ``callback`` on the Tk main thread.
    """

    def __init__(self, marshal, workers: int = 2):
        self._marshal = marshal
        self._pq: "queue.PriorityQueue" = queue.PriorityQueue()
        self._seq = itertools.count()  # FIFO tiebreaker for equal priorities
        self._jobs: dict = {}          # key -> _Job (queued or running)
        self._lock = threading.Lock()
        self._stopped = False
        self._threads = [
            threading.Thread(target=self._worker, name=f"render-{i}", daemon=True)
            for i in range(max(1, workers))
        ]
        for t in self._threads:
            t.start()

    # -- public API ---------------------------------------------------------

    def submit(self, key, work, on_done, *, group=None, priority: int = 0,
               on_error=None) -> None:
        """Queue ``work(token) -> result`` off the Tk thread.

        If a live job already shares ``key``, attach this call's callbacks to
        it instead of enqueuing a duplicate — ``work`` runs once and every
        waiter's ``on_done`` fires. ``on_done(result)`` and ``on_error(exc)``
        are marshaled to the Tk thread; a cancelled job fires neither.
        """
        with self._lock:
            if self._stopped:
                return
            existing = self._jobs.get(key)
            if existing is not None and not existing.cancelled:
                existing.callbacks.append((on_done, on_error))
                return
            job = _Job(key, work, group)
            job.callbacks.append((on_done, on_error))
            self._jobs[key] = job
        self._pq.put((priority, next(self._seq), job))

    def cancel_group(self, group) -> None:
        """Drop pending jobs in ``group`` and signal running ones to abort
        (killing their attached subprocess)."""
        with self._lock:
            jobs = [j for j in self._jobs.values() if j.group == group]
            for job in jobs:
                job.cancelled = True
                self._jobs.pop(job.key, None)
        for job in jobs:
            job.token._cancel()

    def shutdown(self) -> None:
        """Stop accepting work, cancel everything, and wake the workers so
        they exit. Workers are daemons, so we don't block on join."""
        with self._lock:
            self._stopped = True
            jobs = list(self._jobs.values())
            for job in jobs:
                job.cancelled = True
            self._jobs.clear()
        for job in jobs:
            job.token._cancel()
        for _ in self._threads:
            self._pq.put((0, next(self._seq), None))  # sentinel wakeups

    # -- worker -------------------------------------------------------------

    def _worker(self):
        while True:
            _priority, _seq, job = self._pq.get()
            if job is None:
                return  # shutdown sentinel
            if job.cancelled or job.token.cancelled:
                self._retire(job)
                continue
            try:
                result, exc = job.work(job.token), None
            except Exception as caught:
                result, exc = None, caught
            # Retiring snapshots the callbacks under the lock, so a submit()
            # that raced in after work() finished either landed before the pop
            # (its callback is in this snapshot) or after it (it saw no live
            # job and enqueued a fresh one) — never dropped.
            callbacks = self._retire(job)
            if job.cancelled or job.token.cancelled:
                continue
            self._fan_out(callbacks, result=result, exc=exc)

    def _retire(self, job):
        """Remove the job from the live registry once its work has run and
        return its coalesced callbacks (snapshotted under the lock)."""
        with self._lock:
            if self._jobs.get(job.key) is job:
                self._jobs.pop(job.key, None)
            return list(job.callbacks)

    def _fan_out(self, callbacks, *, result=None, exc=None):
        for on_done, on_error in callbacks:
            if exc is not None:
                if on_error is not None:
                    self._marshal(on_error, exc)
            else:
                self._marshal(on_done, result)
