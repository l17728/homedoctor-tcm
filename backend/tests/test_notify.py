from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.notify import send_notify


@pytest.mark.asyncio
async def test_serverchan_webhook_posts_json(monkeypatch):
    monkeypatch.setenv("HOMEDOCTOR_NOTIFY_WEBHOOK", "https://sctapi.ftqq.com/key.send")
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.__aexit__.return_value = None
    client.post.return_value = SimpleNamespace(status_code=200)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_: client)

    assert await send_notify("告警标题", "告警内容") is True
    client.post.assert_awaited_once_with(
        "https://sctapi.ftqq.com/key.send",
        json={"title": "告警标题", "desp": "告警内容"},
    )


@pytest.mark.asyncio
async def test_unconfigured_webhook_only_logs(monkeypatch, caplog):
    monkeypatch.delenv("HOMEDOCTOR_NOTIFY_WEBHOOK", raising=False)
    assert await send_notify("本地告警", "仅写日志") is False
    assert "HOMEDOCTOR_NOTIFY_WEBHOOK" in caplog.text
