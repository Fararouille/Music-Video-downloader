from __future__ import annotations

import threading
import time

from .db import Store, utcnow
from .downloader import AUDIO_QUALITIES, VIDEO_QUALITIES, Cancelled, Downloader, validate_url
from .library import Library


class JobManager:
    """One worker thread, a durable queue in SQLite, and progress written in place."""

    def __init__(
        self,
        store: Store,
        downloader: Downloader,
        library: Library,
        *,
        allow_private_urls: bool = False,
    ):
        self.store = store
        self.downloader = downloader
        self.library = library
        self.allow_private_urls = allow_private_urls
        self._cancel: dict[str, threading.Event] = {}
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ public

    def start(self) -> None:
        with self._lock:
            if self._thread is not None:
                return
            self.store.fail_interrupted_jobs()
            self._thread = threading.Thread(target=self._run, name="crate-downloader", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        for event in list(self._cancel.values()):
            event.set()
        self._wake.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=10)
            self._thread = None

    def enqueue(self, url: str, kind: str, quality: str) -> dict:
        if kind not in {"audio", "video"}:
            raise ValueError("kind must be audio or video")
        allowed = AUDIO_QUALITIES if kind == "audio" else VIDEO_QUALITIES
        if quality not in allowed:
            raise ValueError(f"quality must be one of {', '.join(allowed)}")
        clean = validate_url(url, allow_private=self.allow_private_urls)
        job = self.store.create_job(clean, kind, quality)
        self._wake.set()
        return job

    def cancel(self, job_id: str) -> bool:
        job = self.store.get_job(job_id)
        if job is None:
            return False
        if job["status"] == "queued":
            return self.store.cancel_job(job_id)
        if job["status"] == "running":
            event = self._cancel.get(job_id)
            if event is not None:
                event.set()
                return True
        return False

    def retry(self, job_id: str) -> bool:
        if not self.store.retry_job(job_id):
            return False
        self._wake.set()
        return True

    def is_running(self) -> bool:
        thread = self._thread
        return bool(thread and thread.is_alive())

    # ------------------------------------------------------------------ worker

    def _run(self) -> None:
        while not self._stop.is_set():
            job = self.store.next_queued_job()
            if job is None:
                self._wake.wait(1.0)
                self._wake.clear()
                continue
            current = self.store.get_job(job["id"])
            if current is None or current["status"] != "queued":
                continue
            self._process(current)

    def _process(self, job: dict) -> None:
        job_id = job["id"]
        event = threading.Event()
        self._cancel[job_id] = event
        self.store.update_job(
            job_id, status="running", started_at=utcnow(), error=None, progress=0.0
        )
        last_write = 0.0

        def on_progress(progress) -> None:
            nonlocal last_write
            now = time.monotonic()
            if now - last_write < 0.4 and progress.fraction < 0.98:
                return
            last_write = now
            self.store.update_job_progress(
                job_id,
                progress.fraction,
                speed=progress.speed,
                eta=progress.eta,
                title=progress.title,
            )

        try:
            downloaded = self.downloader.download(job, on_progress, event)
            media = self.library.register_download(
                downloaded.path, downloaded.metadata, downloaded.thumbnail
            )
        except Cancelled:
            self.downloader.cleanup(job)
            self.store.update_job(
                job_id,
                status="canceled",
                finished_at=utcnow(),
                speed=None,
                eta=None,
            )
        except Exception as exc:  # noqa: BLE001 - the message is the product
            self.downloader.cleanup(job)
            self.store.update_job(
                job_id,
                status="error",
                error=str(exc)[:800],
                finished_at=utcnow(),
                speed=None,
                eta=None,
            )
        else:
            self.store.update_job(
                job_id,
                status="done",
                progress=1.0,
                media_id=media["id"],
                title=media["title"],
                finished_at=utcnow(),
                speed=None,
                eta=None,
            )
        finally:
            self._cancel.pop(job_id, None)
