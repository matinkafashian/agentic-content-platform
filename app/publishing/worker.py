import asyncio
import logging
from contextlib import suppress
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from app.publishing.adapters import PlatformAdapter
from app.publishing.repository import PublishingRepository
from app.publishing.service import PublishingPaused, PublishingService

logger = logging.getLogger(__name__)


class PublishingWorker:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        upload_root: Path,
        adapters: dict[str, PlatformAdapter],
        *,
        poll_seconds: float,
    ) -> None:
        self.session_factory = session_factory
        self.upload_root = upload_root
        self.adapters = adapters
        self.poll_seconds = poll_seconds

    def run_once(self) -> int:
        with self.session_factory() as session:
            service = PublishingService(
                PublishingRepository(session), self.upload_root, self.adapters
            )
            try:
                return len(service.run_due())
            except PublishingPaused:
                return 0

    async def run_forever(self) -> None:
        while True:
            try:
                await asyncio.to_thread(self.run_once)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("publishing worker iteration failed")
            await asyncio.sleep(self.poll_seconds)


async def stop_worker(task: asyncio.Task[None] | None) -> None:
    if task is None:
        return
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task

