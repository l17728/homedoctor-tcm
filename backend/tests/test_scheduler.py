"""Tests for the periodic feeder scheduler."""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.scheduler import (
    start_scheduler,
    stop_scheduler,
    _run_feeder_safe,
    _feeder_loop,
)


@pytest.mark.asyncio
async def test_run_feeder_safe_success():
    mock_db = MagicMock()
    with patch("app.scheduler.run_feeder_scan", new_callable=AsyncMock) as mock_scan:
        mock_scan.return_value = {"gaps_found": 0, "feeds_sent": 0}
        await _run_feeder_safe(mock_db)
        mock_scan.assert_called_once()


@pytest.mark.asyncio
async def test_run_feeder_safe_handles_error():
    mock_db = MagicMock()
    with patch("app.scheduler.run_feeder_scan", new_callable=AsyncMock) as mock_scan:
        mock_scan.side_effect = RuntimeError("LLM timeout")
        await _run_feeder_safe(mock_db)
        mock_scan.assert_called_once()


@pytest.mark.asyncio
async def test_feeder_loop_sleeps_between_runs():
    mock_db = MagicMock()
    call_count = 0

    async def mock_safe(db):
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            raise asyncio.CancelledError()

    with patch("app.scheduler._run_feeder_safe", side_effect=mock_safe):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(asyncio.CancelledError):
                await _feeder_loop(mock_db, interval_hours=1)


@pytest.mark.asyncio
async def test_start_stop_scheduler():
    mock_db = MagicMock()
    with patch("app.scheduler._feeder_loop", new_callable=AsyncMock) as mock_loop:
        async def fake_loop(db, interval):
            await asyncio.sleep(100)
        mock_loop.side_effect = fake_loop

        task = start_scheduler(mock_db, interval_hours=1)
        assert task is not None
        assert not task.done()

        await stop_scheduler(task)
        assert task.done() or task.cancelled()


@pytest.mark.asyncio
async def test_start_scheduler_returns_task():
    mock_db = MagicMock()
    task = start_scheduler(mock_db, interval_hours=999)
    assert hasattr(task, "cancel")
    await stop_scheduler(task)


@pytest.mark.asyncio
async def test_stop_scheduler_already_done():
    mock_db = MagicMock()

    async def quick_complete(db, interval):
        pass

    with patch("app.scheduler._feeder_loop", side_effect=quick_complete):
        task = start_scheduler(mock_db, interval_hours=1)
        await asyncio.sleep(0.1)
        await stop_scheduler(task)
