"""Tests for the periodic feeder scheduler."""
import asyncio
import time
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from app.scheduler import (
    start_scheduler,
    stop_scheduler,
    _run_feeder_safe,
    _feeder_loop,
    _seconds_until_next_sunday_evening,
)


@pytest.mark.asyncio
async def test_weekly_digest_contains_recent_consultation_summary(db, client):
    from app.scheduler import _generate_weekly_digests

    sharer = (await client.get("/api/auth/me")).json()
    viewer_response = await client.post("/api/auth/register", json={
        "username": "digest-viewer", "password": "viewerpass123",
        "consent_privacy": True, "consent_health_data": True,
    })
    assert viewer_response.status_code == 201
    viewer = (await client.get("/api/auth/me", headers={
        "Authorization": f"Bearer {viewer_response.json()['access_token']}"
    })).json()
    await db.execute(
        "INSERT INTO family_shares (id, sharer_id, viewer_id, status) VALUES (?, ?, ?, 'active')",
        ("share-digest", sharer["id"], viewer["id"]),
    )
    await db.execute(
        "INSERT INTO conversations (id, user_id, title, created_at) VALUES (?, ?, ?, datetime('now'))",
        ("digest-conv", sharer["id"], "睡眠与作息"),
    )

    assert await _generate_weekly_digests(db) == 1
    notification = await db.query_one(
        "SELECT changes FROM audit_log WHERE user_id = ? AND entity_type = 'notification' ORDER BY rowid DESC LIMIT 1",
        (viewer["id"],),
    )
    import json
    changes = json.loads(notification["changes"])
    assert changes["consultation_count"] == 1
    assert changes["recent_topics"] == ["睡眠与作息"]
    assert "过去7天有1次" in changes["summary"]


def test_weekly_digest_uses_china_timezone_for_naive_input():
    now = datetime(2026, 10, 18, 19, 0, 0)  # Sunday 19:00 in China
    assert _seconds_until_next_sunday_evening(now) == 3600


def test_weekly_digest_converts_aware_utc_input_to_china_timezone():
    now = datetime(2026, 10, 18, 11, 0, 0, tzinfo=timezone.utc)
    assert _seconds_until_next_sunday_evening(now) == 3600


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


@pytest.mark.asyncio
async def test_feeder_retry_backoff_and_alert_after_three_failures(monkeypatch):
    import app.scheduler as scheduler

    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) == 4:
            raise asyncio.CancelledError()

    monkeypatch.setattr(scheduler.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(scheduler, "_run_feeder_safe", AsyncMock(return_value=False))
    notify = AsyncMock()
    monkeypatch.setattr(scheduler, "send_notify", notify)
    with pytest.raises(asyncio.CancelledError):
        await _feeder_loop(MagicMock(), interval_hours=24)
    assert sleeps == [60, 3600, 14400, 14400]
    notify.assert_awaited_once()


@pytest.mark.asyncio
async def test_disk_watermark_warns_above_threshold(monkeypatch, tmp_path):
    import app.scheduler as scheduler

    monkeypatch.setattr(scheduler.shutil, "disk_usage", lambda _: type("Usage", (), {"used": 90, "total": 100})())
    notify = AsyncMock()
    monkeypatch.setattr(scheduler, "send_notify", notify)
    assert await scheduler._check_disk_watermark(tmp_path) is False
    notify.assert_awaited_once()


@pytest.mark.asyncio
async def test_backup_freshness_warns_when_stale(monkeypatch, tmp_path):
    import os
    import app.scheduler as scheduler

    backup = tmp_path / "backup_old.db"
    backup.write_bytes(b"db")
    old = time.time() - 49 * 3600
    os.utime(backup, (old, old))
    notify = AsyncMock()
    monkeypatch.setattr(scheduler, "send_notify", notify)
    assert await scheduler._check_backup_freshness(tmp_path) is False
    notify.assert_awaited_once()


@pytest.mark.asyncio
async def test_backup_freshness_checks_configured_backup_volume(monkeypatch, tmp_path):
    import app.scheduler as scheduler

    backup_dir = tmp_path / "mounted-backups"
    backup_dir.mkdir()
    (backup_dir / "backup_recent.db.enc").write_bytes(b"encrypted")
    monkeypatch.setenv("HOMEDOCTOR_BACKUP_DIR", str(backup_dir))
    notify = AsyncMock()
    monkeypatch.setattr(scheduler, "send_notify", notify)

    assert await scheduler._check_backup_freshness(tmp_path / "database") is True
    notify.assert_not_awaited()


@pytest.mark.asyncio
async def test_conversation_ttl_deletes_old_rows_only(db):
    import app.scheduler as scheduler

    await db.execute(
        "INSERT INTO conversations (id, user_id, title, created_at) VALUES (?, ?, ?, datetime('now', '-31 days'))",
        ("old-conversation", "ttl-test-user", "old"),
    )
    await db.execute(
        "INSERT INTO conversations (id, user_id, title) VALUES (?, ?, ?)",
        ("new-conversation", "ttl-test-user", "new"),
    )
    assert await scheduler._cleanup_conversation_ttl(db, days=30) == 1
    assert await db.query_one("SELECT id FROM conversations WHERE id = ?", ("old-conversation",)) is None
    assert await db.query_one("SELECT id FROM conversations WHERE id = ?", ("new-conversation",)) is not None
