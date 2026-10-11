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
from dataclasses import dataclass
from pathlib import Path

from .dubbing import dub_video
from .speech import PiperTTS, WhisperASR
from .translator import ArgosTranslator

MAX_UPLOAD_BYTES = 80 * 1024 * 1024
MAX_ACTIVE_JOBS = 4
RETENTION_SECONDS = 3600


@dataclass
class Job:
    job_id: str
    workdir: Path
    source: str
    target: str
    created_at: float
    status: str = "queued"
    error: str = ""
    output: Path | None = None

    def view(self) -> dict:
        return {"job_id": self.job_id, "status": self.status,
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
                if job.status not in {"complete", "failed"}:
                    continue
                if now - job.created_at < RETENTION_SECONDS:
                    continue
                shutil.rmtree(job.workdir, ignore_errors=True)
                del self._jobs[name]

    def allocate(self, source: str, target: str) -> Job:
        self.expire()
        with self._guard:
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

    def _execute(self, identifier: str) -> None:
        with self._guard:
            job = self._jobs.get(identifier)
            if job is None:
                return
            job.status = "running"
        try:
            result_path = job.workdir / "dubbed.mp4"
            self._perform(job.workdir / "source.mp4", result_path, job.source, job.target)
            with self._guard:
                job.output = result_path
                job.status = "complete"
        except Exception as exc:
            with self._guard:
                job.error = f"{type(exc).__name__}: {str(exc)[:180]}"
                job.status = "failed"

    def _perform(self, input_path: Path, output_path: Path,
                 source: str, target: str) -> None:
        asr = WhisperASR(
            os.getenv("NEXVARY_WHISPER_MODEL", "small"),
            allow_download=False,
            device=os.getenv("NEXVARY_ASR_DEVICE", "cpu")
        )
        dub_video(input_path, output_path, source, target, asr,
                  ArgosTranslator(), PiperTTS())


_default_queue: JobQueue | None = None
_default_guard = threading.Lock()


def get_job_queue() -> JobQueue:
    global _default_queue
    with _default_guard:
        if _default_queue is None:
            _default_queue = JobQueue()
        return _default_queue
