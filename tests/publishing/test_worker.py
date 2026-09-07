import asyncio
import logging
from contextlib import suppress
from unittest.mock import MagicMock

from app.publishing.service import PublishingPaused
from app.publishing.worker import PublishingWorker, stop_worker


def _worker(tmp_path) -> PublishingWorker:
    session_context = MagicMock()
    session_context.__enter__.return_value = object()
    return PublishingWorker(
        MagicMock(return_value=session_context),
        tmp_path,
        {},
        poll_seconds=0.01,
    )


def test_worker_processes_due_publications(monkeypatch, tmp_path):
    worker = _worker(tmp_path)

    class SuccessfulService:
        def __init__(self, repository, upload_root, adapters):
            pass

        def run_due(self):
            return [object(), object()]

    monkeypatch.setattr("app.publishing.worker.PublishingService", SuccessfulService)

    assert worker.run_once() == 2


def test_worker_treats_paused_publishing_as_no_work(monkeypatch, tmp_path):
    worker = _worker(tmp_path)

    class PausedService:
        def __init__(self, repository, upload_root, adapters):
            pass

        def run_due(self):
            raise PublishingPaused

    monkeypatch.setattr("app.publishing.worker.PublishingService", PausedService)

    assert worker.run_once() == 0


def test_worker_logs_iteration_failure_and_keeps_loop_alive(monkeypatch, tmp_path, caplog):
    worker = _worker(tmp_path)
    monkeypatch.setattr(worker, "run_once", MagicMock(side_effect=RuntimeError("temporary")))

    async def stop_after_iteration(_seconds):
        raise asyncio.CancelledError

    monkeypatch.setattr("app.publishing.worker.asyncio.sleep", stop_after_iteration)

    with caplog.at_level(logging.ERROR), suppress(asyncio.CancelledError):
        asyncio.run(worker.run_forever())

    assert "publishing worker iteration failed" in caplog.text


def test_stop_worker_accepts_none_and_cancels_running_task():
    async def scenario():
        await stop_worker(None)
        started = asyncio.Event()

        async def wait_forever():
            started.set()
            await asyncio.Event().wait()

        task = asyncio.create_task(wait_forever())
        await started.wait()
        await stop_worker(task)
        return task.cancelled()

    assert asyncio.run(scenario()) is True
