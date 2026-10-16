"""通知出口 — 运维告警 webhook 推送（ServerChan / Bark 二选一）。

磁盘水位、备份新鲜度、巡检 Agent 连续失败等调度器告警统一经
``send_notify`` 推送给管理员；未配置 webhook 时仅 ``logger.warning``，
不影响主流程（本地部署无推送服务也可用）。

配置（环境变量，可选）::

    HOMEDOCTOR_NOTIFY_WEBHOOK=https://sctapi.ftqq.com/<SENDKEY>.send   # ServerChan
    HOMEDOCTOR_NOTIFY_WEBHOOK=https://api.day.app/<DEVICE_KEY>          # Bark

按 URL 特征自动识别渠道：
  - ServerChan（sctapi.ftqq.com / ftqq.com / 以 /send 结尾）
    → POST JSON ``{"title": ..., "desp": ...}``
  - Bark（api.day.app / URL 含 bark）
    → GET ``/{key}/{title}/{body}``（路径段 URL 编码）

不引入新依赖：httpx 已在 requirements.txt（CLI/LLM 均使用）。
"""

from __future__ import annotations

import logging
import os
from urllib.parse import quote

logger = logging.getLogger(__name__)

WEBHOOK_ENV = "HOMEDOCTOR_NOTIFY_WEBHOOK"
_TIMEOUT_SECONDS = 10.0


def _detect_provider(url: str) -> str:
    """按 URL 特征识别推送渠道：'serverchan' 或 'bark'。"""
    lowered = url.lower().rstrip("/")
    if "sctapi.ftqq.com" in lowered or "ftqq.com" in lowered or lowered.endswith("/send"):
        return "serverchan"
    if "day.app" in lowered or "bark" in lowered:
        return "bark"
    # 未知服务默认按 ServerChan 的 {title, desp} JSON 约定（最通用）
    return "serverchan"


async def send_notify(title: str, body: str = "") -> bool:
    """推送一条告警。返回 True=已发送；False=未配置或发送失败（不抛异常）。"""
    url = (os.environ.get(WEBHOOK_ENV) or "").strip()
    if not url:
        logger.warning("告警（未配置 %s，仅日志）: %s — %s", WEBHOOK_ENV, title, body)
        return False

    provider = _detect_provider(url)
    try:
        import httpx
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            if provider == "bark":
                get_url = f"{url.rstrip('/')}/{quote(title)}/{quote(body)}"
                resp = await client.get(get_url)
            else:
                resp = await client.post(url, json={"title": title, "desp": body})
        if resp.status_code >= 400:
            logger.warning(
                "告警推送失败: %s 响应 HTTP %s（title=%s）", provider, resp.status_code, title
            )
            return False
        return True
    except Exception as exc:  # 网络/解析失败不应波及调度主流程
        logger.warning("告警推送异常（%s）: %s（title=%s）", provider, exc, title)
        return False
