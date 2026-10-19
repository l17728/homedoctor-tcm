"""CLI ↔ 路由防回归冒烟测试。

从 cli.py 的 typer 注册表提取每个命令回调内的 HTTP 调用（method + path），
逐一断言 app.main 的 openapi.json 中存在匹配的路由模板。

历史上踩过的坑（本测试永久锁死）：
  - reminders:toggle 用 POST，路由实际是 PUT /api/reminders/{id}/toggle
  - backup:restore 调 /api/restore，路由实际是 POST /api/backup/restore
"""

from __future__ import annotations

import inspect
import json
import re

import pytest
from httpx import ASGITransport, AsyncClient

import cli
import app.main as main_mod
from typer.testing import CliRunner


METHOD_BY_HELPER = {"get": "GET", "post": "POST", "put": "PUT", "delete": "DELETE"}
# Exact OpenAPI operations intentionally exposed through api:request only.
# Each entry is explicit: newly-added routes fail the audit until curated here or
# given a domain command. Reasons explain why a dedicated CLI is deferred.
GENERIC_ONLY_ROUTE_EXCEPTIONS: dict[str, set[tuple[str, str]]] = {
    # Privileged maintenance and agent administration lacks a safe, curated operator workflow.
    "admin": {
    ("DELETE", "/api/admin/agent/memories/{}"),
    ("DELETE", "/api/admin/deletion-exempt/{}"),
    ("GET", "/api/admin/agent/config"),
    ("GET", "/api/admin/agent/conversations"),
    ("GET", "/api/admin/agent/memories"),
    ("GET", "/api/admin/deletion-exemptions"),
    ("GET", "/api/admin/deletion-recommendations"),
    ("GET", "/api/admin/freshness-stats"),
    ("GET", "/api/admin/index-stats"),
    ("GET", "/api/admin/url-health-stats"),
    ("GET", "/api/agent/logs"),
    ("GET", "/api/agent/logs/{}"),
    ("POST", "/api/admin/agent/memories"),
    ("POST", "/api/admin/agent/optimize-prompt"),
    ("POST", "/api/admin/community-consensus-scan"),
    ("POST", "/api/admin/deletion-execute"),
    ("POST", "/api/admin/deletion-exempt"),
    ("POST", "/api/admin/feeder/scan"),
    ("POST", "/api/admin/freshness-check"),
    ("POST", "/api/admin/knowledge/scan-all"),
    ("POST", "/api/admin/translate-check"),
    ("POST", "/api/admin/url-health-check"),
    ("POST", "/api/agent/process"),
    ("PUT", "/api/admin/agent/config"),
    ("PUT", "/api/agent/logs/{}/review"),
    },
    # Knowledge graph, index, curation, and ingestion workflows have specialized payloads and side effects.
    "knowledge": {
    ("GET", "/api/kg/graph"),
    ("GET", "/api/kg/node/{}"),
    ("GET", "/api/kg/snapshot/{}/{}"),
    ("GET", "/api/knowledge/graph/{}"),
    ("GET", "/api/knowledge/{}/append/history"),
    ("GET", "/api/knowledge/{}/feedback"),
    ("GET", "/api/knowledge/{}/note"),
    ("POST", "/api/ai-classify/auto-tag"),
    ("POST", "/api/ai-classify/duplicates"),
    ("POST", "/api/ai-classify/merge"),
    ("POST", "/api/ai-classify/suggest"),
    ("POST", "/api/extractor/extract"),
    ("POST", "/api/kg/rebuild"),
    ("POST", "/api/knowledge-hub/entities/{}/relationships"),
    ("POST", "/api/knowledge-hub/entities/{}/view"),
    ("POST", "/api/knowledge-hub/import"),
    ("POST", "/api/knowledge-hub/import-file"),
    ("POST", "/api/knowledge-hub/import-video-url"),
    ("POST", "/api/knowledge/{}/append"),
    ("POST", "/api/knowledge/{}/feedback"),
    ("POST", "/api/rag/index/rebuild"),
    ("POST", "/api/smart-search/expand"),
    ("POST", "/api/smart-search/import"),
    ("PUT", "/api/knowledge-hub/entities/{}"),
    ("PUT", "/api/knowledge/{}/note"),
    },
    # Less common content annotation and collection workflows remain available through the generic HTTP command.
    "content": {
    ("DELETE", "/api/bookmarks/collections/{}"),
    ("DELETE", "/api/bookmarks/collections/{}/items/{}"),
    ("DELETE", "/api/bookmarks/{}"),
    ("DELETE", "/api/classics/annotations/{}"),
    ("DELETE", "/api/share-cards/{}"),
    ("GET", "/api/bookmarks/collections"),
    ("GET", "/api/bookmarks/collections/{}"),
    ("GET", "/api/classics/{}/chapters/{}"),
    ("GET", "/api/classics/{}/chapters/{}/annotations"),
    ("GET", "/api/classics/{}/study-notes"),
    ("GET", "/api/share-cards/monthly-report/latest"),
    ("POST", "/api/bookmarks/check"),
    ("POST", "/api/bookmarks/collections"),
    ("POST", "/api/bookmarks/collections/{}/items"),
    ("POST", "/api/classics/{}/chapters/{}/annotations"),
    ("POST", "/api/classics/{}/chapters/{}/ask"),
    ("POST", "/api/classics/{}/chapters/{}/translate"),
    ("POST", "/api/classics/{}/summarize"),
    ("POST", "/api/share-cards/generate"),
    ("POST", "/api/share-cards/monthly-report"),
    ("PUT", "/api/bookmarks/{}"),
    ("PUT", "/api/classics/annotations/{}"),
    ("PUT", "/api/classics/{}/chapters/{}/study-notes"),
    ("PUT", "/api/classics/{}/chapters/{}/translation"),
    ("PUT", "/api/favorites/{}"),
    },
    # Device, upload, push, and streaming workflows need specialized interaction or payload handling.
    "media": {
    ("DELETE", "/api/push/subscriptions"),
    ("GET", "/api/push/config"),
    ("POST", "/api/chat/image"),
    ("POST", "/api/chat/stream"),
    ("POST", "/api/knowledge-import/upload"),
    ("POST", "/api/knowledge-import/upload-batch"),
    ("POST", "/api/medicines/barcode-lookup"),
    ("POST", "/api/medicines/ocr-recognize"),
    ("POST", "/api/push/subscriptions"),
    ("POST", "/api/voice/qa"),
    ("POST", "/api/voice/synthesize"),
    ("POST", "/api/voice/transcribe"),
    },
    # Specialized clinical/reporting workflows have domain-specific payloads and safety implications.
    "clinical": {
    ("DELETE", "/api/health-logs/{}"),
    ("DELETE", "/api/medication-plans/{}"),
    ("DELETE", "/api/visits/{}"),
    ("GET", "/api/health-logs/{}"),
    ("POST", "/api/comparisons/herbs"),
    ("POST", "/api/formulations/joint-recommend"),
    ("POST", "/api/formulations/tea-recipe"),
    ("POST", "/api/medication-plans/auto-schedule"),
    ("POST", "/api/medication-plans/auto-schedule/expert-review"),
    ("POST", "/api/medication-plans/auto-schedule/verify"),
    ("POST", "/api/medication-plans/{}/pause"),
    ("POST", "/api/medication-plans/{}/resume"),
    ("POST", "/api/visits"),
    ("POST", "/api/visits/ocr"),
    ("PUT", "/api/health-logs/{}"),
    ("PUT", "/api/medication-plans/{}"),
    ("PUT", "/api/visits/{}"),
    },
    # Secondary account, family, and sharing workflows remain callable through the generic HTTP command.
    "account": {
    ("DELETE", "/api/family-members/{}"),
    ("DELETE", "/api/personal/edges/{}"),
    ("DELETE", "/api/remote-assist/invite/{}"),
    ("GET", "/api/personal/edges"),
    ("GET", "/api/personal/graph"),
    ("GET", "/api/personal/symptoms"),
    ("GET", "/api/remote-assist/consent"),
    ("GET", "/api/remote-assist/shared-with-me"),
    ("GET", "/api/remote-assist/{}/alerts"),
    ("GET", "/api/remote-assist/{}/missed-alerts"),
    ("GET", "/api/user/interests"),
    ("POST", "/api/auth/register"),
    ("POST", "/api/family-members/clear-switch"),
    ("POST", "/api/personal/edges"),
    ("POST", "/api/personal/symptoms"),
    ("POST", "/api/remote-assist/{}/alert"),
    ("PUT", "/api/family-members/{}"),
    ("PUT", "/api/remote-assist/consent"),
    },
    # Low-frequency auxiliary operations remain callable through the generic HTTP command.
    "miscellaneous": {
    ("DELETE", "/api/models/{}"),
    ("GET", "/api/models"),
    ("GET", "/api/reminders/{}"),
    ("GET", "/api/smart-search"),
    ("PATCH", "/api/herbs/{}/aliases"),
    ("POST", "/api/chat/conversations"),
    ("POST", "/api/chat/save-card"),
    ("POST", "/api/chat/{}/summarize"),
    ("POST", "/api/constitution/assess"),
    ("POST", "/api/models"),
    ("POST", "/api/models/vote"),
    ("POST", "/api/reminders/{}/check-in"),
    ("PUT", "/api/models/{}"),
    ("PUT", "/api/reminders/{}"),
    },
}
GENERIC_ONLY_ROUTE_REASONS = {
    "admin": "Privileged maintenance and agent administration lacks a safe, curated operator workflow.",
    "knowledge": "Knowledge graph, index, curation, and ingestion workflows have specialized payloads and side effects.",
    "content": "Less common content annotation and collection workflows remain available through the generic HTTP command.",
    "media": "Device, upload, push, and streaming workflows need specialized interaction or payload handling.",
    "clinical": "Specialized clinical/reporting workflows have domain-specific payloads and safety implications.",
    "account": "Secondary account, family, and sharing workflows remain callable through the generic HTTP command.",
    "miscellaneous": "Low-frequency auxiliary operations remain callable through the generic HTTP command."
}


# 匹配 _get/_post/_put/_delete[_authed](client, "..." 或 f"...")
_CALL_RE = re.compile(
    r'_(get|post|put|delete)(?:_authed)?\(\s*client\s*,\s*f?"([^"]+)"',
    re.S,
)
_GROUPED_GET_RE = re.compile(r'_get_with_params\(\s*f?"([^"]+)"', re.S)


def _normalize(path: str) -> str:
    """把 {herb_id}/{reminder_id} 等路径参数归一化为 {}，只比较模板结构。"""
    return re.sub(r"\{[^}]+\}", "{}", path)


def _extract_cli_calls() -> list[tuple[str, str, str]]:
    """遍历 typer 注册命令，从回调源码提取 (command, METHOD, path)。"""
    result: list[tuple[str, str, str]] = []
    for info in cli.app.registered_commands:
        callback = info.callback
        name = info.name or callback.__name__.replace("_", "-")
        source = inspect.getsource(callback)
        for match in _CALL_RE.finditer(source):
            verb, path = match.group(1), match.group(2)
            result.append((name, METHOD_BY_HELPER[verb], _normalize(path)))
        for match in _GROUPED_GET_RE.finditer(source):
            result.append((name, "GET", _normalize(match.group(1))))
        # api:request is the discoverable HTTP-only fallback for routes that do
        # not yet have a domain-specific command. Its method and /api/ path are
        # runtime arguments, so represent its declared coverage explicitly.
        if name == "api:request" and "client.request(" in source:
            result.append((name, "*", "/api/*"))
    return result


@pytest.fixture
def openapi_routes() -> set[tuple[str, str]]:
    """(METHOD, 模板path) 集合，直接从 FastAPI 生成 openapi 规范。"""
    spec = main_mod.app.openapi()
    routes: set[tuple[str, str]] = set()
    for path, ops in spec["paths"].items():
        for method in ops:
            if method.upper() in ("GET", "POST", "PUT", "DELETE", "PATCH"):
                routes.add((method.upper(), _normalize(path)))
    return routes


@pytest.mark.asyncio
async def test_openapi_served_over_http():
    """GET /openapi.json 可访问（CLI 冒烟测试依赖的路由权威源）。"""
    transport = ASGITransport(app=main_mod.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/openapi.json")
    assert resp.status_code == 200
    assert len(resp.json()["paths"]) > 50


def test_every_cli_command_makes_http_calls():
    """每个注册命令都必须提取出至少一个 HTTP 调用（防止提取逻辑静默漏命令）。"""
    calls = _extract_cli_calls()
    commands_with_calls = {name for name, _, _ in calls}
    all_commands = {
        (i.name or i.callback.__name__.replace("_", "-"))
        for i in cli.app.registered_commands
    }
    assert len(all_commands) >= 35, f"CLI 命令数异常: {sorted(all_commands)}"
    missing = all_commands - commands_with_calls
    assert not missing, f"以下 CLI 命令未提取到 HTTP 调用: {sorted(missing)}"


def test_cli_calls_match_openapi(openapi_routes: set[tuple[str, str]]):
    """CLI 每个 (method, path) 都必须命中 openapi 中的真实路由模板。"""
    calls = _extract_cli_calls()
    assert len(calls) >= 45, "提取到的 HTTP 调用数量异常，提取逻辑可能失效"
    mismatches = [
        f"{name}: {method} {path}"
        for name, method, path in calls
        if method != "*" and (method, path) not in openapi_routes
    ]
    assert not mismatches, "CLI 命令与后端路由不匹配:\n  " + "\n  ".join(mismatches)


def test_every_openapi_api_route_has_a_cli_command(openapi_routes: set[tuple[str, str]]):
    """Every operation has a domain command or an exact, explained fallback exception."""
    api_routes = {(method, path) for method, path in openapi_routes if path.startswith("/api/")}
    assert api_routes == openapi_routes, "OpenAPI 新增了未纳入覆盖审计的非 /api 路由"

    calls = _extract_cli_calls()
    explicit = {(method, path) for _, method, path in calls if method != "*"}
    generic = [(method, path) for _, method, path in calls if method == "*"]
    assert generic == [("*", "/api/*")], "api:request 通用覆盖命令缺失或被意外改动"

    missing = api_routes - explicit
    callback = next(i.callback for i in cli.app.registered_commands if i.name == "api:request")
    source = inspect.getsource(callback)
    generic_methods = {"GET", "POST", "PUT", "PATCH", "DELETE"}
    assert all(f'"{method}"' in source for method in generic_methods), "通用命令未支持所有 OpenAPI HTTP 方法"
    # Generic request is a fallback, not evidence that domain coverage is done.
    # Require a committed, exact method+path exception for every fallback use.
    exceptions = {
        route: group
        for group, routes in GENERIC_ONLY_ROUTE_EXCEPTIONS.items()
        for route in routes
    }
    assert len(exceptions) == sum(map(len, GENERIC_ONLY_ROUTE_EXCEPTIONS.values())), (
        "generic-only exception is duplicated across rationale groups"
    )
    assert (len(api_routes), len(explicit), len(missing)) == (262, 126, 136), (
        "CLI coverage inventory changed: "
        f"OpenAPI operations={len(api_routes)}, domain-command operations={len(explicit)}, "
        f"generic-only operations={len(missing)}. Review the route diff and update the exact "
        "exception inventory or add domain commands."
    )
    unexpected = missing - exceptions.keys()
    stale = exceptions.keys() - missing
    details = [
        f"{method} {path}: no rationale (add a domain CLI command or reviewed exception)"
        for method, path in sorted(unexpected)
    ] + [
        f"{method} {path}: stale exception; route now has a domain CLI command or was removed"
        for method, path in sorted(stale)
    ]
    assert not details, "OpenAPI CLI coverage drift:\n  " + "\n  ".join(details)
    assert set(exceptions.values()) <= GENERIC_ONLY_ROUTE_REASONS.keys()


def test_high_frequency_cli_commands_cover_routes(openapi_routes: set[tuple[str, str]]):
    calls = {(name, method, path) for name, method, path in _extract_cli_calls()}
    expected = {
        ("auth:me", "GET", "/api/auth/me"),
        ("auth:consent-status", "GET", "/api/auth/consent-status"),
        ("herbs:formulas", "GET", "/api/herbs/{}/formulas"),
        ("herbs:compare", "GET", "/api/comparisons/herbs/{}/{}"),
        ("formulas:tree", "GET", "/api/formulas/{}/tree"),
        ("formulas:roles", "GET", "/api/formulas/{}/roles"),
        ("formulas:safety", "GET", "/api/formulas/{}/safety-check"),
        ("formulas:safety", "GET", "/api/formulas/{}/safety-text"),
        ("formulas:compare", "POST", "/api/comparisons/formulas"),
        ("medicines:detail", "GET", "/api/medicines/{}"),
        ("medicines:update", "PUT", "/api/medicines/{}"),
        ("medicines:delete", "DELETE", "/api/medicines/{}"),
        ("medicines:alerts", "GET", "/api/medicines/quality-alerts"),
        ("medicines:alerts", "GET", "/api/medicines/alerts/expiring"),
        ("medicines:quality", "GET", "/api/medicines/{}/quality"),
        ("reminders:history", "GET", "/api/reminders/history"),
        ("constitution:history", "GET", "/api/constitution/history"),
        ("family-members:current", "GET", "/api/family-members/current"),
        ("triage:reference", "GET", "/api/triage/age-groups"),
        ("triage:reference", "GET", "/api/triage/red-flags"),
        ("therapies:categories", "GET", "/api/therapies/categories"),
        ("therapies:search", "GET", "/api/therapies/search"),
        ("reports:constitution", "GET", "/api/reports/constitution"),
        ("reports:pre-visit", "GET", "/api/reports/pre-visit"),
        ("seasonal-health", "GET", "/api/seasonal-health"),
        ("favorites:check", "POST", "/api/favorites/check"),
        ("knowledge:list", "GET", "/api/knowledge/herbs"),
        ("knowledge:list", "GET", "/api/knowledge/formulas"),
        ("knowledge:list", "GET", "/api/knowledge/symptoms"),
        ("knowledge:list", "GET", "/api/knowledge/meridians"),
        ("knowledge:list", "GET", "/api/knowledge/acupoints"),
        ("knowledge:list", "GET", "/api/knowledge/therapies"),
        ("knowledge:detail", "GET", "/api/knowledge/herbs/{}"),
        ("knowledge:detail", "GET", "/api/knowledge/formulas/{}"),
        ("knowledge:detail", "GET", "/api/knowledge/meridians/{}"),
        ("knowledge:detail", "GET", "/api/knowledge/acupoints/{}"),
        ("knowledge:detail", "GET", "/api/knowledge/therapies/{}"),
        ("knowledge:search", "GET", "/api/knowledge/search"),
        ("knowledge:categories", "GET", "/api/knowledge/categories"),
        ("knowledge:browse", "GET", "/api/knowledge/browse"),
        ("knowledge-hub:search", "GET", "/api/knowledge-hub/search"),
        ("knowledge-hub:catalog", "GET", "/api/knowledge-hub/types"),
        ("knowledge-hub:catalog", "GET", "/api/knowledge-hub/relationship-types"),
        ("knowledge-hub:catalog", "GET", "/api/knowledge-hub/recent"),
        ("knowledge-hub:catalog", "GET", "/api/knowledge-hub/popular"),
        ("knowledge-hub:entity", "GET", "/api/knowledge-hub/entities/{}"),
        ("knowledge-hub:entity", "GET", "/api/knowledge-hub/entities/{}/relationships"),
        ("rag:search", "GET", "/api/rag/search"),
        ("rag:intent", "GET", "/api/rag/intent"),
        ("rag:index-status", "GET", "/api/rag/index/status"),
    }
    assert all((method, path) in openapi_routes for _, method, path in expected)
    assert expected <= calls


def test_generic_api_command_dispatches_arbitrary_route(monkeypatch):
    captured = {}

    class FakeResponse:
        content = b'{"ok":true}'
        text = '{"ok":true}'

        def raise_for_status(self):
            return None

        def json(self):
            return {"ok": True}

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def request(self, method, url, **kwargs):
            captured.update(method=method, url=url, kwargs=kwargs)
            return FakeResponse()

    monkeypatch.setattr(cli.httpx, "Client", FakeClient)
    result = CliRunner().invoke(
        cli.app,
        ["api:request", "PATCH", "/api/models/model-1", "--token", "test-token",
         "--query", '{"verbose":true}', "--body", '{"enabled":false}'],
    )
    assert result.exit_code == 0, result.output
    assert captured["method"] == "PATCH"
    assert captured["url"] == f"{cli.BASE_URL}/api/models/model-1"
    assert captured["kwargs"]["headers"] == {"Authorization": "Bearer test-token"}
    assert captured["kwargs"]["params"] == {"verbose": True}
    assert captured["kwargs"]["json"] == {"enabled": False}
    assert json.loads(result.output) == {"ok": True}


def test_known_regressions_pinned(openapi_routes: set[tuple[str, str]]):
    """锁死两个历史 bug：toggle 用 PUT；restore 走 /api/backup/restore。"""
    assert ("PUT", "/api/reminders/{}/toggle") in openapi_routes
    assert ("POST", "/api/backup/restore") in openapi_routes

    calls = {(name, method, path) for name, method, path in _extract_cli_calls()}
    assert ("reminders:toggle", "PUT", "/api/reminders/{}/toggle") in calls
    assert ("backup:restore", "POST", "/api/backup/restore") in calls
