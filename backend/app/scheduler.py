from __future__ import annotations

import asyncio
import logging

from app.database import DbAdapter
from app.knowledge_feeder import run_feeder_scan

logger = logging.getLogger(__name__)

_feeder_lock = asyncio.Lock()


async def _run_feeder_safe(db: DbAdapter) -> None:
    async with _feeder_lock:
        try:
            result = await run_feeder_scan(db, max_feeds=10)
            logger.info("feeder scan complete: %s", result)
        except Exception:
            logger.exception("feeder scan failed")


async def _feeder_loop(db: DbAdapter, interval_hours: float) -> None:
    while True:
        await asyncio.sleep(interval_hours * 3600)
        await _run_feeder_safe(db)


def start_scheduler(db: DbAdapter, interval_hours: float = 24) -> asyncio.Task:
    task = asyncio.create_task(_feeder_loop(db, interval_hours))
    logger.info("scheduler started: feeder scan every %s hours", interval_hours)
    return task


async def stop_scheduler(task: asyncio.Task) -> None:
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    logger.info("scheduler stopped")
