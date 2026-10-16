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

# 匹配 _get/_post/_put/_delete[_authed](client, "..." 或 f"...")
_CALL_RE = re.compile(
    r'_(get|post|put|delete)(?:_authed)?\(\s*client\s*,\s*f?"([^"]+)"',
    re.S,
)


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
    """每个 API operation 都有专用命令或由 api:request 显式兜底。"""
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
    # Generic command accepts arbitrary OpenAPI method/path at runtime, so every
    # otherwise-unmapped operation is callable through: api:request METHOD PATH.
    uncovered = {route for route in missing if not route[1].startswith("/api/") or route[0] not in generic_methods}
    assert not uncovered, "未覆盖的 OpenAPI 路由:\n  " + "\n  ".join(
        f"{method} {path}" for method, path in sorted(uncovered)
    )


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
