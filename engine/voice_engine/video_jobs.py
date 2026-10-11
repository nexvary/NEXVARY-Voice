"""Single-worker private video-dubbing queue with upload size and retention limits.

Does not expose the user's file name in paths; all transient uploads are removed
after the retention window on later API access or explicit deletion. No shared DB.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from .dubbing import dub_video, probe_streams, cancellable_runner
from .speech import PiperTTS, WhisperASR, cached_asr
from .translator import ArgosTranslator

MAX_UPLOAD_BYTES = 80 * 1024 * 1024
MAX_ACTIVE_JOBS = 4
MAX_RETAINED_JOBS = 20
RETENTION_SECONDS = 3600


@dataclass
class Job:
    job_id: str
    workdir: Path
    source: str
    target: str
    created_at: float
    status: str = "queued"
    finished_at: float | None = None
    error: str = ""
    output: Path | None = None
    cancel_requested: threading.Event = field(default_factory=threading.Event)
    phase: str = 'queued'
    completed_segments: int = 0
    total_segments: int | None = None

    def view(self) -> dict:
        return {"job_id": self.job_id, "status": self.status, "phase":self.phase,
                "completed_segments":self.completed_segments, "total_segments":self.total_segments,
                "error": self.error, "source_language": self.source,
                "target_language": self.target,
                "download_ready": self.status == "complete" and
                                  self.output is not None and self.output.is_file()}


class JobQueue:
    def __init__(self, parent: Path | None = None):
        self.parent = parent
        self._guard = threading.RLock()
        self._jobs: dict[str, Job] = {}
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="nexvary-video")

    def expire(self) -> None:
        now = time.time()
        with self._guard:
            for name, job in list(self._jobs.items()):
                if job.status not in {"complete", "failed", "cancelled"}:
                    continue
                if job.finished_at is None or now - job.finished_at < RETENTION_SECONDS:
                    continue
                shutil.rmtree(job.workdir, ignore_errors=True)
                del self._jobs[name]

    def allocate(self, source: str, target: str) -> Job:
        self.expire()
        with self._guard:
            if len(self._jobs) >= MAX_RETAINED_JOBS:
                raise RuntimeError("Video job quota reached; delete finished jobs")
            active = sum(1 for j in self._jobs.values() if j.status in ("queued", "running"))
            if active >= MAX_ACTIVE_JOBS:
                raise RuntimeError("Queue capacity reached; retry after running jobs finish")
            identifier = str(uuid.uuid4())
            work = Path(tempfile.mkdtemp(prefix="nexvary-video-", dir=self.parent))
            os.chmod(work, 0o700)
            task = Job(identifier, work, source, target, time.time())
            self._jobs[identifier] = task
            return task

    def start(self, job: Job) -> None:
        self._pool.submit(self._execute, job.job_id)

    def get(self, identifier: str) -> Job | None:
        self.expire()
        with self._guard:
            return self._jobs.get(identifier)

    def delete(self, identifier: str) -> bool:
        with self._guard:
            job = self._jobs.get(identifier)
            if job is None:
                return False
            if job.status in {"queued", "running"}:
                raise RuntimeError("Cannot delete a running video job")
            self._jobs.pop(identifier)
        shutil.rmtree(job.workdir, ignore_errors=True)
        return True

    def fail_upload(self, identifier: str) -> None:
        with self._guard:
            job = self._jobs.pop(identifier, None)
        if job:
            shutil.rmtree(job.workdir, ignore_errors=True)

    def cancel(self, identifier: str) -> bool:
        with self._guard:
            job = self._jobs.get(identifier)
            if job is None: return False
            if job.status not in {'queued','running'}: return True
            job.cancel_requested.set()
            if job.status == 'queued':
                job.status = 'cancelled'; job.finished_at = time.time()
            return True

    def _execute(self, identifier: str) -> None:
        with self._guard:
            job = self._jobs.get(identifier)
            if job is None or job.cancel_requested.is_set():
                return
            job.status = "running"
        self._context = getattr(self, "_context", threading.local())
        self._context.job = job
        try:
            result_path = job.workdir / "dubbed.mp4"
            self._perform(job.workdir / "source.mp4", result_path, job.source, job.target)
            with self._guard:
                if job.cancel_requested.is_set(): raise RuntimeError("تم إلغاء الدبلجة.")
                job.output = result_path
                job.status = "complete"
                job.finished_at = time.time()
        except Exception as exc:
            with self._guard:
                job.error = f"{type(exc).__name__}: {str(exc)[:180]}"
                job.status = "cancelled" if job.cancel_requested.is_set() else "failed"
                job.finished_at = time.time()

    def _perform(self, input_path: Path, output_path: Path,
                 source: str, target: str) -> None:
        from .workload import exclusive
        job = self._context.job
        def progress(phase,done,total):
            with self._guard:
                job.phase = phase; job.completed_segments = done; job.total_segments = total
        with exclusive('video'):
            asr = cached_asr(os.getenv('NEXVARY_WHISPER_MODEL','base'),os.getenv('NEXVARY_ASR_DEVICE','cpu'))
            dub_video(input_path,output_path,source,target,asr,ArgosTranslator(),PiperTTS(),
                      runner=cancellable_runner(job.cancel_requested.is_set),
                      cancelled=job.cancel_requested.is_set, progress=progress, output_probe=probe_streams)


_default_queue: JobQueue | None = None
_default_guard = threading.Lock()


def get_job_queue() -> JobQueue:
    global _default_queue
    with _default_guard:
        if _default_queue is None:
            _default_queue = JobQueue()
        return _default_queue
