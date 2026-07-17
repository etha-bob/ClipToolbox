"""Export job history and output naming (roadmap B4).

Pure Python — no Tk. An ``ExportJobSpec`` snapshots the *exact* arguments a
``core.export.run_export_job`` call was made with, so RE-RUN replays the same
render verbatim — even in a later app session, with a different (or no) clip
loaded. ``JobHistory`` keeps the newest jobs in ``jobs.json`` next to
config.json (same atomic-write / AppData-fallback convention as settings.py).

Name patterns: the drawer's output filename is a token template. Conditional
tokens resolve to their historical suffix when the matching option is active
and to "" otherwise, so the default pattern reproduces the old save-dialog
name exactly. Unknown ``{tokens}`` are left literal — visible feedback beats
silent deletion when the user typos one.
"""
import json
import os
import re
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from cliptoolbox.constants import EXPORT_HISTORY_LIMIT
from cliptoolbox.core.paths import BASE_DIR

JOBS_NAME = "jobs.json"

RUNNING = "running"
DONE = "done"
FAILED = "failed"
CANCELLED = "cancelled"

_ILLEGAL_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def resolve_name_pattern(
    pattern: str,
    clip: str,
    *,
    trim: bool = False,
    crop: bool = False,
    stamp: bool = False,
    size_mb: float | None = None,
    res: str | None = None,
    when: time.struct_time | None = None,
) -> str:
    """Resolve a name pattern to a filename stem (no extension).

    ``{clip}`` is the source stem; ``{trim}``/``{crop}``/``{stamp}`` resolve
    to their suffix when active; ``{size}``/``{res}`` describe an active
    compression target; ``{date}``/``{time}`` are the wall clock.
    """
    when = when or time.localtime()
    tokens = {
        "{clip}": clip,
        "{trim}": "_trimmed" if trim else "",
        "{crop}": "_crop" if crop else "",
        "{stamp}": "_timestamp" if stamp else "",
        "{size}": f"_compressed_{size_mb:g}mb" if size_mb is not None else "",
        "{res}": f"_{res}" if (size_mb is not None and res) else "",
        "{date}": time.strftime("%Y-%m-%d", when),
        "{time}": time.strftime("%H%M%S", when),
    }
    name = pattern
    for token, value in tokens.items():
        name = name.replace(token, value)

    name = _ILLEGAL_FILENAME_CHARS.sub("_", name).strip(" .")
    return name or "export"


def unique_path(path: Path) -> Path:
    """Return ``path`` or the first ``stem_2``, ``stem_3``… that is free."""
    if not path.exists():
        return path
    for n in range(2, 1000):
        candidate = path.with_name(f"{path.stem}_{n}{path.suffix}")
        if not candidate.exists():
            return candidate
    return path


@dataclass
class ExportJobSpec:
    """The run_export_job argument snapshot plus display metadata."""

    input_path: str
    filter_complex: str
    output_path: str
    trim_start: float | None = None
    trim_end: float | None = None
    compression_target_mb: float | None = None
    compression_resolution_label: str | None = None
    total_duration_seconds: float | None = None
    video_filter: str | None = None
    video_prefilter: str | None = None
    clip_name: str = ""


@dataclass
class ExportJob:
    job_id: str
    spec: ExportJobSpec
    status: str = RUNNING
    percent: int = 0
    attempt: int = 1
    attempts_max: int = 1
    size_bytes: int | None = None
    error: str = ""
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    log: list[str] = field(default_factory=list)

    LOG_LIMIT = 200

    @property
    def output_name(self) -> str:
        return Path(self.spec.output_path).name

    @property
    def is_running(self) -> bool:
        return self.status == RUNNING

    def add_log(self, text: str):
        self.log.append(text)
        if len(self.log) > self.LOG_LIMIT:
            del self.log[: len(self.log) - self.LOG_LIMIT]

    def finish(self, status: str, *, size_bytes: int | None = None, error: str = ""):
        self.status = status
        self.size_bytes = size_bytes
        self.error = error
        self.finished_at = time.time()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ExportJob | None":
        try:
            spec_data = data.get("spec")
            if not isinstance(spec_data, dict) or not spec_data.get("input_path"):
                return None
            spec = ExportJobSpec(**{
                key: value for key, value in spec_data.items()
                if key in ExportJobSpec.__dataclass_fields__
            })
            job = cls(job_id=str(data.get("job_id") or ""), spec=spec)
            for key in ("status", "percent", "attempt", "attempts_max", "size_bytes",
                        "error", "created_at", "finished_at"):
                if key in data:
                    setattr(job, key, data[key])
            log = data.get("log")
            job.log = [str(line) for line in log][-cls.LOG_LIMIT:] if isinstance(log, list) else []
            if not job.job_id:
                return None
            # A job can't still be running in a fresh process: the export
            # thread died with the app that persisted it.
            if job.status == RUNNING:
                job.finish(CANCELLED, error="Interrupted — the app closed mid-export.")
            if job.status not in (DONE, FAILED, CANCELLED):
                job.status = FAILED
            return job
        except Exception:
            return None


def _appdata_dir() -> Path:
    root = os.environ.get("APPDATA")
    if root:
        return Path(root) / "ClipToolbox"
    return Path.home() / ".cliptoolbox"


def _candidates() -> list[Path]:
    return [BASE_DIR / JOBS_NAME, _appdata_dir() / JOBS_NAME]


class JobHistory:
    """Newest-first job list with jobs.json persistence (capped)."""

    def __init__(self, path: Path | None = None, limit: int = EXPORT_HISTORY_LIMIT):
        self._explicit_path = path
        self.limit = limit
        self.jobs: list[ExportJob] = []
        self._counter = 0
        self.load()

    # ---------------------------------------------------------- storage

    def _read_candidates(self) -> list[Path]:
        return [self._explicit_path] if self._explicit_path else _candidates()

    def load(self):
        for path in self._read_candidates():
            try:
                if not path.exists():
                    continue
                data = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(data, list):
                    continue
                jobs = [ExportJob.from_dict(item) for item in data if isinstance(item, dict)]
                self.jobs = [job for job in jobs if job is not None][: self.limit]
                return
            except Exception:
                continue
        self.jobs = []

    def save(self) -> Path | None:
        payload = json.dumps([job.to_dict() for job in self.jobs[: self.limit]], indent=2)
        for target in self._read_candidates():
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                fd, tmp_path = tempfile.mkstemp(
                    dir=str(target.parent), prefix=".jobs-", suffix=".tmp")
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as handle:
                        handle.write(payload)
                    os.replace(tmp_path, target)
                finally:
                    try:
                        Path(tmp_path).unlink(missing_ok=True)
                    except Exception:
                        pass
                return target
            except Exception:
                continue
        return None

    # ---------------------------------------------------------- jobs

    def new_job(self, spec: ExportJobSpec) -> ExportJob:
        self._counter += 1
        job = ExportJob(job_id=f"{int(time.time() * 1000)}-{self._counter}", spec=spec)
        self.jobs.insert(0, job)
        self._prune()
        return job

    def get(self, job_id: str) -> ExportJob | None:
        for job in self.jobs:
            if job.job_id == job_id:
                return job
        return None

    def _prune(self):
        """Cap the list, never evicting a running job."""
        if len(self.jobs) <= self.limit:
            return
        keep: list[ExportJob] = []
        overflow = len(self.jobs) - self.limit
        for job in reversed(self.jobs):  # oldest first
            if overflow > 0 and not job.is_running:
                overflow -= 1
                continue
            keep.append(job)
        keep.reverse()
        self.jobs = keep
