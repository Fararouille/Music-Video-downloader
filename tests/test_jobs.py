from __future__ import annotations

import time

import pytest

from crate.config import Settings
from crate.db import Store
from crate.downloader import (
    Cancelled,
    Downloaded,
    DownloadError,
    Progress,
)
from crate.jobs import JobManager
from crate.library import Library


class FakeDownloader:
    """Stands in for yt-dlp so the queue can be tested without the network."""

    def __init__(
        self,
        settings: Settings,
        *,
        fail: str | None = None,
        block: bool = False,
    ) -> None:
        self.settings = settings
        self.fail = fail
        self.block = block
        self.cleaned: list[str] = []
        self.progress: list[float] = []

    def download(self, job, on_progress, cancel) -> Downloaded:
        on_progress(Progress(0.4, "1.5 MiB/s", 12, "Track"))
        self.progress.append(0.4)
        if self.block:
            if not cancel.wait(timeout=10):
                raise DownloadError("cancel event never arrived")
            raise Cancelled("download cancelled")
        if self.fail:
            raise DownloadError(self.fail)
        path = self.settings.audio_dir / "Track [abc].mp3"
        path.write_bytes(b"audio-bytes")
        metadata = {
            "title": "Track",
            "artist": "Artist",
            "duration": 42.0,
            "source_id": "abc",
            "source_url": "https://example.com/watch?v=abc",
        }
        return Downloaded(path=path, metadata=metadata, thumbnail=None)

    def cleanup(self, job) -> None:
        self.cleaned.append(job["id"])


def make_manager(settings: Settings, store: Store, library: Library, **kwargs) -> JobManager:
    return JobManager(
        store,
        FakeDownloader(settings, **kwargs),  # type: ignore[arg-type]
        library,
        allow_private_urls=True,
    )


def wait_for(store: Store, job_id: str, statuses: set[str], timeout: float = 10.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = store.get_job(job_id)
        if job is not None and job["status"] in statuses:
            return job
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} stuck in {store.get_job(job_id)}")


def test_enqueue_rejects_unknown_kind(settings, store, library) -> None:
    manager = make_manager(settings, store, library)

    with pytest.raises(ValueError, match="kind"):
        manager.enqueue("http://127.0.0.1:9/x", "podcast", "192")


def test_enqueue_rejects_quality_for_the_wrong_kind(settings, store, library) -> None:
    manager = make_manager(settings, store, library)

    with pytest.raises(ValueError, match="quality"):
        manager.enqueue("http://127.0.0.1:9/x", "audio", "1080")


def test_enqueue_blocks_private_urls_unless_opted_in(settings, store, library) -> None:
    manager = JobManager(
        store,
        FakeDownloader(settings),  # type: ignore[arg-type]
        library,
        allow_private_urls=False,
    )

    with pytest.raises(ValueError, match="private or local"):
        manager.enqueue("http://127.0.0.1:9/x", "audio", "192")
    assert store.list_jobs() == []


def test_enqueue_stores_a_queued_job(settings, store, library) -> None:
    manager = make_manager(settings, store, library)

    job = manager.enqueue("http://127.0.0.1:9/x", "audio", "320")

    assert job["status"] == "queued"
    assert job["quality"] == "320"
    assert store.get_job(job["id"]) is not None


def test_worker_registers_downloaded_media(settings, store, library) -> None:
    manager = make_manager(settings, store, library)
    job = manager.enqueue("http://127.0.0.1:9/x", "audio", "192")
    manager.start()
    try:
        finished = wait_for(store, job["id"], {"done", "error"})
    finally:
        manager.stop()

    assert finished["status"] == "done"
    assert finished["progress"] == 1.0
    assert finished["speed"] is None
    assert finished["title"] == "Track"
    media = store.get_media(finished["media_id"])
    assert media is not None and media["title"] == "Track"
    assert media["artist"] == "Artist"
    assert media["path"] == "audio/Track [abc].mp3"


def test_worker_records_failures_and_cleans_up(settings, store, library) -> None:
    manager = make_manager(settings, store, library, fail="video unavailable")
    job = manager.enqueue("http://127.0.0.1:9/x", "audio", "192")
    manager.start()
    try:
        finished = wait_for(store, job["id"], {"done", "error"})
    finally:
        manager.stop()

    assert finished["status"] == "error"
    assert finished["error"] == "video unavailable"
    assert finished["finished_at"]
    downloader = manager.downloader
    assert job["id"] in downloader.cleaned  # type: ignore[attr-defined]


def test_cancel_queued_job(settings, store, library) -> None:
    manager = make_manager(settings, store, library)
    job = manager.enqueue("http://127.0.0.1:9/x", "audio", "192")

    assert manager.cancel(job["id"]) is True
    assert store.get_job(job["id"])["status"] == "canceled"
    assert manager.cancel(job["id"]) is False
    assert manager.retry(job["id"]) is True
    assert store.get_job(job["id"])["status"] == "queued"


def test_cancel_running_job(settings, store, library) -> None:
    manager = make_manager(settings, store, library, block=True)
    job = manager.enqueue("http://127.0.0.1:9/x", "audio", "192")
    manager.start()
    try:
        wait_for(store, job["id"], {"running"})
        assert manager.cancel(job["id"]) is True
        finished = wait_for(store, job["id"], {"canceled"})
    finally:
        manager.stop()

    assert finished["status"] == "canceled"


def test_retry_unknown_or_done_job_is_rejected(settings, store, library) -> None:
    manager = make_manager(settings, store, library)

    assert manager.retry("missing") is False
    job = manager.enqueue("http://127.0.0.1:9/x", "audio", "192")
    assert manager.retry(job["id"]) is False


def test_restart_marks_interrupted_jobs_as_errors(settings, store, library) -> None:
    job = store.create_job("http://127.0.0.1:9/x", "audio", "192")
    store.update_job(job["id"], status="running")

    manager = make_manager(settings, store, library)
    manager.start()
    try:
        recovered = wait_for(store, job["id"], {"error"})
    finally:
        manager.stop()

    assert "restart" in recovered["error"]


def test_delete_job_guard(settings, store) -> None:
    job = store.create_job("http://127.0.0.1:9/x", "audio", "192")
    store.update_job(job["id"], status="running")

    assert store.delete_job(job["id"]) is False

    store.update_job(job["id"], status="error")
    assert store.delete_job(job["id"]) is True
    assert store.get_job(job["id"]) is None


def test_cleanup_removes_partial_files(settings, library) -> None:
    from crate.downloader import Downloader

    settings.ensure_dirs()
    for name in ("a.mp3.part", "b.m4a.ytdl", "c.temp", "keep.mp3"):
        (settings.audio_dir / name).write_bytes(b"x")

    Downloader(settings).cleanup({"kind": "audio"})

    remaining = sorted(path.name for path in settings.audio_dir.iterdir())
    assert remaining == ["keep.mp3"]


def test_progress_updates_are_persisted(settings, store, library) -> None:
    manager = make_manager(settings, store, library)
    job = manager.enqueue("http://127.0.0.1:9/x", "audio", "192")

    manager._process(store.get_job(job["id"]))

    finished = store.get_job(job["id"])
    assert finished["status"] == "done"
    assert finished["progress"] == 1.0
    assert finished["media_id"] is not None
