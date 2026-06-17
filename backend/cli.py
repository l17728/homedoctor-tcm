"""Family Doctor CLI — typer + httpx HTTP client."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

import typer
import httpx

app = typer.Typer(name="homedoctor", help="家庭医生 CLI — 通过 HTTP API 与服务交互")

BASE_URL = "http://localhost:8000"


def _get(client: httpx.Client, path: str, params: dict | None = None) -> dict:
    """GET request with error handling."""
    try:
        r = client.get(f"{BASE_URL}{path}", params=params)
        r.raise_for_status()
        return r.json()
    except httpx.ConnectError:
        typer.echo("❌ 无法连接到服务，请确认服务已启动 (python -m uvicorn app.main:app)")
        raise typer.Exit(1)
    except httpx.HTTPStatusError as e:
        typer.echo(f"❌ 请求失败: {e.response.status_code} {e.response.text}")
        raise typer.Exit(1)


def _post(client: httpx.Client, path: str, data: dict | None = None) -> dict:
    """POST request with error handling."""
    try:
        r = client.post(f"{BASE_URL}{path}", json=data)
        r.raise_for_status()
        return r.json()
    except httpx.ConnectError:
        typer.echo("❌ 无法连接到服务，请确认服务已启动")
        raise typer.Exit(1)
    except httpx.HTTPStatusError as e:
        typer.echo(f"❌ 请求失败: {e.response.status_code} {e.response.text}")
        raise typer.Exit(1)


def _get_authed(client: httpx.Client, path: str, token: str, params: dict | None = None) -> dict:
    """GET request with Bearer token."""
    try:
        r = client.get(f"{BASE_URL}{path}", params=params, headers={"Authorization": f"Bearer {token}"})
        r.raise_for_status()
        return r.json()
    except httpx.ConnectError:
        typer.echo("❌ 无法连接到服务，请确认服务已启动")
        raise typer.Exit(1)
    except httpx.HTTPStatusError as e:
        typer.echo(f"❌ 请求失败: {e.response.status_code} {e.response.text}")
        raise typer.Exit(1)


def _post_authed(client: httpx.Client, path: str, token: str, data: dict | None = None) -> dict:
    """POST request with Bearer token."""
    try:
        r = client.post(f"{BASE_URL}{path}", json=data, headers={"Authorization": f"Bearer {token}"})
        r.raise_for_status()
        return r.json()
    except httpx.ConnectError:
        typer.echo("❌ 无法连接到服务，请确认服务已启动")
        raise typer.Exit(1)
    except httpx.HTTPStatusError as e:
        typer.echo(f"❌ 请求失败: {e.response.status_code} {e.response.text}")
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.command("health")
def health():
    """检查服务健康状态。"""
    with httpx.Client() as client:
        result = _get(client, "/api/health")
    typer.echo(f"✅ 服务状态: {result['status']} | 版本: {result['version']}")


# ---------------------------------------------------------------------------
# Herbs
# ---------------------------------------------------------------------------

@app.command("herbs:list")
def herbs_list(
    category: Optional[str] = typer.Option(None, "--category", "-c", help="按分类筛选"),
    page: int = typer.Option(1, "--page", "-p", help="页码"),
):
    """列出中药。"""
    params: dict = {"page": page, "pageSize": 20}
    if category:
        params["category"] = category
    with httpx.Client() as client:
        result = _get(client, "/api/herbs", params=params)
    items = result.get("items", [])
    typer.echo(f"共 {result['total']} 味中药 (第 {page}/{result['totalPages']} 页)")
    for herb in items:
        typer.echo(f"  [{herb['id']}] {herb['name']} — {herb.get('category', '')} | {herb.get('efficacy', '')[:30]}")


@app.command("herbs:search")
def herbs_search(query: str = typer.Argument(..., help="搜索关键词")):
    """全文搜索中药。"""
    with httpx.Client() as client:
        result = _get(client, "/api/herbs/search", params={"q": query})
    items = result.get("items", [])
    typer.echo(f"找到 {len(items)} 条结果")
    for herb in items:
        typer.echo(f"  [{herb['id']}] {herb['name']} — {herb.get('efficacy', '')[:40]}")


@app.command("herbs:detail")
def herbs_detail(herb_id: str = typer.Argument(..., help="中药ID")):
    """查看中药详情。"""
    with httpx.Client() as client:
        result = _get(client, f"/api/herbs/{herb_id}")
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# Formulas
# ---------------------------------------------------------------------------

@app.command("formulas:list")
def formulas_list(
    page: int = typer.Option(1, "--page", "-p", help="页码"),
):
    """列出方剂。"""
    with httpx.Client() as client:
        result = _get(client, "/api/formulas", params={"page": page, "pageSize": 20})
    items = result.get("items", [])
    typer.echo(f"共 {result['total']} 首方剂 (第 {page}/{result['totalPages']} 页)")
    for formula in items:
        typer.echo(f"  [{formula['id']}] {formula['name']} — {formula.get('category', '')} | {formula.get('efficacy', '')[:30]}")


@app.command("formulas:detail")
def formulas_detail(formula_id: str = typer.Argument(..., help="方剂ID")):
    """查看方剂详情。"""
    with httpx.Client() as client:
        result = _get(client, f"/api/formulas/{formula_id}")
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# Medicines
# ---------------------------------------------------------------------------

@app.command("medicines:list")
def medicines_list():
    """列出家庭药箱药品。"""
    with httpx.Client() as client:
        result = _get(client, "/api/medicines")
    items = result.get("items", [])
    typer.echo(f"共 {result['total']} 种药品")
    for med in items:
        typer.echo(f"  [{med['id']}] {med['name']} ({med.get('type', '')}) — 库存: {med.get('quantity', 0)}")


@app.command("medicines:add")
def medicines_add(
    name: str = typer.Option(..., "--name", "-n", help="药品名称"),
    type: str = typer.Option("western", "--type", "-t", help="类型"),
):
    """添加药品到家庭药箱。"""
    with httpx.Client() as client:
        result = _post(client, "/api/medicines", data={"name": name, "type": type})
    typer.echo(f"✅ 已添加: {result['name']} (ID: {result['id']})")


# ---------------------------------------------------------------------------
# Safety
# ---------------------------------------------------------------------------

@app.command("safety:check")
def safety_check(
    herbs: str = typer.Option("", "--herbs", "-h", help="中药列表，逗号分隔"),
    medicines: str = typer.Option("", "--medicines", "-m", help="西药列表，逗号分隔"),
):
    """检查药物配伍安全性。"""
    herb_list = [h.strip() for h in herbs.split(",") if h.strip()]
    med_list = [m.strip() for m in medicines.split(",") if m.strip()]

    with httpx.Client() as client:
        result = _post(client, "/api/safety/check", data={
            "herbs": herb_list,
            "medicines": med_list,
        })

    if result["safe"]:
        typer.echo("✅ 未发现配伍禁忌")
    else:
        typer.echo(f"⚠️ 发现 {len(result['warnings'])} 条警告:")
        for w in result["warnings"]:
            severity = "🔴" if w["severity"] == "critical" else "🟡"
            typer.echo(f"  {severity} {w['drug_a']} + {w['drug_b']}: {w['mechanism']}")

    typer.echo(f"\n{result.get('disclaimer', '')}")


# ---------------------------------------------------------------------------
# Data Export (PIPL)
# ---------------------------------------------------------------------------

@app.command("export:user")
def export_user(
    username: str = typer.Option(..., "--username", "-u", help="用户名"),
    password: str = typer.Option(..., "--password", "-p", help="密码"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="输出文件路径"),
):
    """导出用户全部数据（PIPL 合规）。"""
    with httpx.Client() as client:
        login = _post(client, "/api/auth/login", data={"username": username, "password": password})
        token = login["access_token"]
        result = _get_authed(client, "/api/export", token=token)

    data_section = result.get("data", {})
    typer.echo(f"✅ 导出成功 (导出时间: {result.get('export_date')})")
    typer.echo(f"用户: {result.get('user', {}).get('username')}")
    for key, val in data_section.items():
        if isinstance(val, list):
            typer.echo(f"  {key}: {len(val)} 条")
        elif val:
            typer.echo(f"  {key}: 1 条")
        else:
            typer.echo(f"  {key}: 0 条")

    filename = output or f"export_{username}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    typer.echo(f"💾 已保存到 {filename}")


# ---------------------------------------------------------------------------
# Backup / Restore
# ---------------------------------------------------------------------------

@app.command("backup:create")
def backup_create(
    username: str = typer.Option(..., "--username", "-u", help="用户名"),
    password: str = typer.Option(..., "--password", "-p", help="密码"),
):
    """创建数据库备份。"""
    with httpx.Client() as client:
        login = _post(client, "/api/auth/login", data={"username": username, "password": password})
        result = _post_authed(client, "/api/backup", token=login["access_token"])
    typer.echo(f"✅ 备份成功: {result['filename']} ({result['size_bytes']} bytes)")


@app.command("backup:list")
def backup_list(
    username: str = typer.Option(..., "--username", "-u", help="用户名"),
    password: str = typer.Option(..., "--password", "-p", help="密码"),
):
    """列出可用备份。"""
    with httpx.Client() as client:
        login = _post(client, "/api/auth/login", data={"username": username, "password": password})
        result = _get_authed(client, "/api/backup/list", token=login["access_token"])
    backups = result.get("backups", [])
    if not backups:
        typer.echo("暂无备份")
        return
    typer.echo(f"共 {len(backups)} 个备份:")
    for b in backups:
        typer.echo(f"  📦 {b['filename']} — {b['size']} bytes ({b['created_at']})")


@app.command("backup:restore")
def backup_restore(
    filename: str = typer.Argument(..., help="备份文件名"),
    username: str = typer.Option(..., "--username", "-u", help="用户名"),
    password: str = typer.Option(..., "--password", "-p", help="密码"),
):
    """从备份恢复（重启后生效）。"""
    with httpx.Client() as client:
        login = _post(client, "/api/auth/login", data={"username": username, "password": password})
        result = _post_authed(
            client, "/api/restore", token=login["access_token"], data={"filename": filename}
        )
    typer.echo(f"✅ {result['message']} (文件: {result.get('filename', filename)})")


# ---------------------------------------------------------------------------
# Reminders (spec §20)
# ---------------------------------------------------------------------------

@app.command("reminders:list")
def reminders_list(
    username: str = typer.Option(..., "--username", "-u"),
    password: str = typer.Option(..., "--password", "-p"),
):
    """列出全部吃药提醒。"""
    with httpx.Client() as client:
        login = _post(client, "/api/auth/login", data={"username": username, "password": password})
        result = _get_authed(client, "/api/reminders", token=login["access_token"])
    items = result.get("items", [])
    typer.echo(f"共 {result['total']} 条提醒")
    for r in items:
        status = "✅" if r.get("enabled") else "⏸️"
        times = ", ".join(r.get("times", []))
        typer.echo(f"  {status} [{r['id'][:8]}] {r['title']} — {times}")


@app.command("reminders:today")
def reminders_today(
    username: str = typer.Option(..., "--username", "-u"),
    password: str = typer.Option(..., "--password", "-p"),
):
    """今日提醒时间轴。"""
    with httpx.Client() as client:
        login = _post(client, "/api/auth/login", data={"username": username, "password": password})
        result = _get_authed(client, "/api/reminders/today", token=login["access_token"])
    slots = result.get("items", [])
    typer.echo(f"📅 {result['date']} — 共 {result['total']} 个时间槽")
    for s in slots:
        icon = {"待服": "⏰", "已服": "✅", "漏服": "❌"}.get(s["status"], "•")
        typer.echo(f"  {icon} {s['time']} {s['title']} [{s['status']}]")


@app.command("reminders:add")
def reminders_add(
    title: str = typer.Option(..., "--title", "-t", help="提醒标题"),
    times: str = typer.Option("08:00", "--times", help="时间，逗号分隔"),
    start_date: str = typer.Option("", "--start", help="开始日期 YYYY-MM-DD"),
    username: str = typer.Option(..., "--username", "-u"),
    password: str = typer.Option(..., "--password", "-p"),
):
    """创建吃药提醒。"""
    from datetime import datetime as dt
    sd = start_date or dt.now().strftime("%Y-%m-%d")
    with httpx.Client() as client:
        login = _post(client, "/api/auth/login", data={"username": username, "password": password})
        result = _post_authed(client, "/api/reminders", token=login["access_token"], data={
            "title": title,
            "times": [t.strip() for t in times.split(",")],
            "start_date": sd,
            "frequency": "daily",
        })
    typer.echo(f"✅ 已创建: {result['title']} (ID: {result['id'][:8]})")


@app.command("reminders:toggle")
def reminders_toggle(
    reminder_id: str = typer.Argument(..., help="提醒ID"),
    username: str = typer.Option(..., "--username", "-u"),
    password: str = typer.Option(..., "--password", "-p"),
):
    """启用/暂停提醒。"""
    with httpx.Client() as client:
        login = _post(client, "/api/auth/login", data={"username": username, "password": password})
        token = login["access_token"]
        result = _post_authed(client, f"/api/reminders/{reminder_id}/toggle", token=token, data={})
    state = "启用" if result["enabled"] else "暂停"
    typer.echo(f"✅ {result['title']} 已{state}")


@app.command("reminders:delete")
def reminders_delete(
    reminder_id: str = typer.Argument(..., help="提醒ID"),
    username: str = typer.Option(..., "--username", "-u"),
    password: str = typer.Option(..., "--password", "-p"),
):
    """删除提醒。"""
    with httpx.Client() as client:
        login = _post(client, "/api/auth/login", data={"username": username, "password": password})
        _delete_authed(client, f"/api/reminders/{reminder_id}", token=login["access_token"])
    typer.echo(f"✅ 已删除提醒 {reminder_id[:8]}")


# ---------------------------------------------------------------------------
# Constitution (spec §4.2)
# ---------------------------------------------------------------------------

@app.command("constitution:questionnaire")
def constitution_questionnaire():
    """获取体质自测问卷。"""
    with httpx.Client() as client:
        result = _get(client, "/api/constitution/questionnaire")
    questions = result.get("questions", [])
    typer.echo(f"📋 共 {len(questions)} 题")
    for q in questions[:5]:
        typer.echo(f"  Q{q['id']}: {q['text']}")
    typer.echo(f"  ... (使用 API 查看完整问卷)")


@app.command("constitution:latest")
def constitution_latest(
    username: str = typer.Option(..., "--username", "-u"),
    password: str = typer.Option(..., "--password", "-p"),
):
    """查看最近体质评估结果。"""
    with httpx.Client() as client:
        login = _post(client, "/api/auth/login", data={"username": username, "password": password})
        result = _get_authed(client, "/api/constitution/latest", token=login["access_token"])
    if not result:
        typer.echo("暂无评估记录")
        return
    typer.echo(f"🧬 主体质: {result.get('primary_type', '未知')}")
    secondary = result.get("secondary_types", [])
    if secondary:
        typer.echo(f"   兼夹: {', '.join(secondary)}")
    scores = result.get("results", {})
    typer.echo(f"   评分: {json.dumps(scores, ensure_ascii=False)}")


# ---------------------------------------------------------------------------
# Profile (spec §4.2)
# ---------------------------------------------------------------------------

@app.command("profile:get")
def profile_get(
    username: str = typer.Option(..., "--username", "-u"),
    password: str = typer.Option(..., "--password", "-p"),
):
    """查看健康档案。"""
    with httpx.Client() as client:
        login = _post(client, "/api/auth/login", data={"username": username, "password": password})
        result = _get_authed(client, "/api/profile", token=login["access_token"])
    typer.echo(f"👤 {result.get('display_name', '未设置')}")
    typer.echo(f"   性别: {result.get('gender', '未设置')}")
    typer.echo(f"   体质: {result.get('constitution_type', '未评估')}")
    allergies = result.get("allergies", [])
    if allergies:
        typer.echo(f"   过敏: {', '.join(allergies)}")
    conditions = result.get("health_conditions", [])
    if conditions:
        typer.echo(f"   健康问题: {', '.join(conditions)}")


@app.command("profile:update")
def profile_update(
    username: str = typer.Option(..., "--username", "-u"),
    password: str = typer.Option(..., "--password", "-p"),
    display_name: Optional[str] = typer.Option(None, "--name"),
    gender: Optional[str] = typer.Option(None, "--gender"),
    birth_year: Optional[int] = typer.Option(None, "--birth-year"),
    constitution: Optional[str] = typer.Option(None, "--constitution"),
):
    """更新健康档案。"""
    data: dict = {}
    if display_name:
        data["display_name"] = display_name
    if gender:
        data["gender"] = gender
    if birth_year:
        data["birth_year"] = birth_year
    if constitution:
        data["constitution_type"] = constitution
    if not data:
        typer.echo("⚠️ 请至少指定一个要更新的字段")
        raise typer.Exit(1)
    with httpx.Client() as client:
        login = _post(client, "/api/auth/login", data={"username": username, "password": password})
        _put_authed(client, "/api/profile", token=login["access_token"], data=data)
    typer.echo("✅ 档案已更新")


# ---------------------------------------------------------------------------
# Chat (spec §8)
# ---------------------------------------------------------------------------

@app.command("chat:send")
def chat_send(
    message: str = typer.Argument(..., help="咨询内容"),
    username: str = typer.Option(..., "--username", "-u"),
    password: str = typer.Option(..., "--password", "-p"),
):
    """向AI助手发送咨询。"""
    with httpx.Client(timeout=120.0) as client:
        login = _post(client, "/api/auth/login", data={"username": username, "password": password})
        result = _post_authed(client, "/api/chat", token=login["access_token"], data={
            "message": message,
            "history": [],
        })
    typer.echo(f"🤖 {result['reply']}")
    if result.get("safety_warning"):
        typer.echo(f"\n⚠️ {result['safety_warning']}")


@app.command("chat:history")
def chat_history(
    username: str = typer.Option(..., "--username", "-u"),
    password: str = typer.Option(..., "--password", "-p"),
    page: int = typer.Option(1, "--page", "-p"),
):
    """查看对话历史。"""
    with httpx.Client() as client:
        login = _post(client, "/api/auth/login", data={"username": username, "password": password})
        result = _get_authed(client, "/api/chat/history", token=login["access_token"],
                             params={"page": page})
    items = result.get("items", [])
    typer.echo(f"共 {result['total']} 条对话")
    for conv in items:
        typer.echo(f"  [{conv['id'][:8]}] {conv.get('title', '无标题')} ({conv.get('updated_at', '')})")


# ---------------------------------------------------------------------------
# Daily Health (spec §5.4)
# ---------------------------------------------------------------------------

@app.command("daily-health")
def daily_health(
    username: str = typer.Option(..., "--username", "-u"),
    password: str = typer.Option(..., "--password", "-p"),
):
    """查看今日养生卡。"""
    with httpx.Client() as client:
        login = _post(client, "/api/auth/login", data={"username": username, "password": password})
        result = _get_authed(client, "/api/daily-health", token=login["access_token"])
    typer.echo(f"📅 {result.get('date', '')} — {result.get('solar_term', {}).get('name', '')}")
    typer.echo(f"🌡️ {result.get('solar_term', {}).get('description', '')}")
    tips = result.get("tips", [])
    if tips:
        typer.echo("\n💡 养生建议:")
        for tip in tips:
            typer.echo(f"  • {tip}")


def _put_authed(client: httpx.Client, path: str, token: str, data: dict | None = None) -> dict:
    try:
        r = client.put(f"{BASE_URL}{path}", json=data, headers={"Authorization": f"Bearer {token}"})
        r.raise_for_status()
        return r.json()
    except httpx.ConnectError:
        typer.echo("❌ 无法连接到服务")
        raise typer.Exit(1)
    except httpx.HTTPStatusError as e:
        typer.echo(f"❌ 请求失败: {e.response.status_code} {e.response.text}")
        raise typer.Exit(1)


def _delete_authed(client: httpx.Client, path: str, token: str) -> dict:
    try:
        r = client.delete(f"{BASE_URL}{path}", headers={"Authorization": f"Bearer {token}"})
        r.raise_for_status()
        return r.json()
    except httpx.ConnectError:
        typer.echo("❌ 无法连接到服务")
        raise typer.Exit(1)
    except httpx.HTTPStatusError as e:
        typer.echo(f"❌ 请求失败: {e.response.status_code} {e.response.text}")
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# Safety V2 — Five-layer safety check (spec §15.3)
# ---------------------------------------------------------------------------

@app.command("safety:check-v2")
def safety_check_v2(
    herbs: list[str] = typer.Option([], "--herbs", "-h", help="中药名称（可多次指定）"),
    medicines: list[str] = typer.Option([], "--medicines", "-m", help="西药/中成药名称（可多次指定）"),
    pregnant: bool = typer.Option(False, "--pregnant", help="孕期标记"),
    age: Optional[int] = typer.Option(None, "--age", help="年龄"),
    weight: Optional[float] = typer.Option(None, "--weight", help="体重(kg)"),
):
    """五层安全检查（中药配伍/中西药交互/剂量/特殊人群/免责声明）。"""
    profile: dict = {}
    if pregnant:
        profile["is_pregnant"] = True
    if age is not None:
        profile["age"] = age
    if weight is not None:
        profile["weight_kg"] = weight

    with httpx.Client() as client:
        result = _post(client, "/api/safety/check-v2", data={
            "herbs": herbs,
            "medicines": medicines,
            "user_profile": profile or None,
        })

    if result["safe"]:
        typer.echo("✅ 未发现配伍禁忌")
    else:
        typer.echo(f"⚠️ 发现 {len(result['warnings'])} 条警告:")
        for w in result["warnings"]:
            sev = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🔵"}.get(w["severity"], "•")
            typer.echo(f"  {sev} [L{w['layer']}] {w['title']}: {w['detail']}")
            if w.get("action"):
                typer.echo(f"     建议: {w['action']}")

    if result.get("interactions"):
        typer.echo("\n💊 中西药交互:")
        for inter in result["interactions"]:
            typer.echo(f"  • {inter}")

    unknown_herbs = result.get("unknown_herbs", [])
    if unknown_herbs:
        typer.echo(f"\n❓ 未知中药: {', '.join(unknown_herbs)}")
    unknown_meds = result.get("unknown_medicines", [])
    if unknown_meds:
        typer.echo(f"❓ 未知药品: {', '.join(unknown_meds)}")

    typer.echo(f"\n{result.get('disclaimer', '')}")


# ---------------------------------------------------------------------------
# Favorites (spec §10 — knowledge collection)
# ---------------------------------------------------------------------------

@app.command("favorites:list")
def favorites_list(
    username: str = typer.Option(..., "--username", "-u"),
    password: str = typer.Option(..., "--password", "-p"),
    entry_type: Optional[str] = typer.Option(None, "--type", "-t", help="按类型筛选 (herb/formula/knowledge_card/medicine)"),
):
    """列出我的收藏。"""
    with httpx.Client() as client:
        login = _post(client, "/api/auth/login", data={"username": username, "password": password})
        params = {"entry_type": entry_type} if entry_type else None
        result = _get_authed(client, "/api/favorites", token=login["access_token"], params=params)
    items = result.get("items", [])
    typer.echo(f"共 {result['total']} 条收藏")
    for item in items:
        star = "⭐" if item.get("is_starred") else "  "
        typer.echo(f"  {star} [{item['id'][:8]}] ({item.get('entry_type', '')}) {item.get('title', '')}")


@app.command("favorites:add")
def favorites_add(
    entry_type: str = typer.Option(..., "--type", "-t", help="类型 (herb/formula/knowledge_card/medicine)"),
    title: str = typer.Option(..., "--title", help="标题"),
    content: Optional[str] = typer.Option(None, "--content", help="内容"),
    summary: Optional[str] = typer.Option(None, "--summary", help="摘要"),
    source_url: Optional[str] = typer.Option(None, "--source-url", help="来源URL"),
    username: str = typer.Option(..., "--username", "-u"),
    password: str = typer.Option(..., "--password", "-p"),
):
    """添加收藏。"""
    data: dict = {"entry_type": entry_type, "title": title}
    if content:
        data["content"] = content
    if summary:
        data["summary"] = summary
    if source_url:
        data["source_url"] = source_url
    with httpx.Client() as client:
        login = _post(client, "/api/auth/login", data={"username": username, "password": password})
        result = _post_authed(client, "/api/favorites", token=login["access_token"], data=data)
    typer.echo(f"✅ 已收藏: {result['title']} (ID: {result['id'][:8]}, 类型: {result.get('entry_type', '')})")


@app.command("favorites:delete")
def favorites_delete(
    entry_id: str = typer.Argument(..., help="收藏ID"),
    username: str = typer.Option(..., "--username", "-u"),
    password: str = typer.Option(..., "--password", "-p"),
):
    """删除收藏。"""
    with httpx.Client() as client:
        login = _post(client, "/api/auth/login", data={"username": username, "password": password})
        _delete_authed(client, f"/api/favorites/{entry_id}", token=login["access_token"])
    typer.echo(f"✅ 已删除收藏 {entry_id[:8]}")


# ---------------------------------------------------------------------------
# Family Members (spec §3.1 — multi-member family)
# ---------------------------------------------------------------------------

@app.command("family-members:list")
def family_members_list(
    username: str = typer.Option(..., "--username", "-u"),
    password: str = typer.Option(..., "--password", "-p"),
):
    """列出家庭成员。"""
    with httpx.Client() as client:
        login = _post(client, "/api/auth/login", data={"username": username, "password": password})
        result = _get_authed(client, "/api/family-members", token=login["access_token"])
    items = result.get("items", [])
    typer.echo(f"共 {result['total']} 位家庭成员")
    for m in items:
        typer.echo(f"  [{m['id'][:8]}] {m.get('name', '')} — {m.get('relation', '')} ({m.get('gender', '未设置')})")


@app.command("family-members:add")
def family_members_add(
    name: str = typer.Option(..., "--name", "-n", help="成员姓名"),
    relation: str = typer.Option(..., "--relation", "-r", help="关系 (父亲/母亲/配偶/儿子/女儿/自己/其他)"),
    gender: Optional[str] = typer.Option(None, "--gender", "-g", help="性别 (男/女)"),
    birth_date: Optional[str] = typer.Option(None, "--birth-date", help="出生日期 YYYY-MM-DD"),
    username: str = typer.Option(..., "--username", "-u"),
    password: str = typer.Option(..., "--password", "-p"),
):
    """添加家庭成员。"""
    data: dict = {"name": name, "relation": relation}
    if gender:
        data["gender"] = gender
    if birth_date:
        data["birth_date"] = birth_date
    with httpx.Client() as client:
        login = _post(client, "/api/auth/login", data={"username": username, "password": password})
        result = _post_authed(client, "/api/family-members", token=login["access_token"], data=data)
    typer.echo(f"✅ 已添加: {result['name']} — {result.get('relation', '')} (ID: {result['id'][:8]})")


@app.command("family-members:switch")
def family_members_switch(
    member_id: str = typer.Argument(..., help="成员ID"),
    username: str = typer.Option(..., "--username", "-u"),
    password: str = typer.Option(..., "--password", "-p"),
):
    """切换当前活跃家庭成员。"""
    with httpx.Client() as client:
        login = _post(client, "/api/auth/login", data={"username": username, "password": password})
        result = _post_authed(client, f"/api/family-members/{member_id}/switch", token=login["access_token"])
    member = result.get("member", {})
    typer.echo(f"✅ 已切换到: {member.get('name', '')} — {member.get('relation', '')} (ID: {member.get('id', '')[:8]})")


# ---------------------------------------------------------------------------
# Triage — Child emergency triage (spec §23.1, no auth required)
# ---------------------------------------------------------------------------

@app.command("triage:questionnaire")
def triage_questionnaire(
    age_months: int = typer.Option(..., "--age-months", help="月龄 (0-168)"),
):
    """获取儿童分诊问卷（按月龄）。"""
    with httpx.Client() as client:
        result = _get(client, "/api/triage/questionnaire", params={"age_months": age_months})
    typer.echo(f"👶 年龄组: {result.get('age_group', '')} (月龄 {result.get('age_months')})")
    questions = result.get("questions", [])
    typer.echo(f"📋 问卷共 {result.get('question_count', len(questions))} 题")
    for q in questions:
        typer.echo(f"  Q{q.get('id', '')}: {q.get('text', '')}")
    red_flags = result.get("red_flags", [])
    if red_flags:
        typer.echo(f"\n🚩 红旗症状清单 ({len(red_flags)} 项):")
        for rf in red_flags[:10]:
            typer.echo(f"  [{rf.get('id', '')}] {rf.get('symptom', '')}")
        if len(red_flags) > 10:
            typer.echo(f"  ... (共 {len(red_flags)} 项)")
    typer.echo(f"\n⚠️ {result.get('disclaimer', '')}")


@app.command("triage:assess")
def triage_assess(
    age_months: int = typer.Option(..., "--age-months", help="月龄 (0-168)"),
    symptoms: str = typer.Option("", "--symptoms", "-s", help="红旗症状ID列表，逗号分隔 (如 RF01,RF03)"),
    answers: Optional[str] = typer.Option(None, "--answers", help="问卷答案JSON (如 '{\"Q01\":38.5}')"),
    age_days: Optional[int] = typer.Option(None, "--age-days", help="日龄（新生儿精确度）"),
):
    """儿童急症分诊评估。"""
    body: dict = {"age_months": age_months}
    if age_days is not None:
        body["age_days"] = age_days

    red_flag_ids = [s.strip() for s in symptoms.split(",") if s.strip()]
    if red_flag_ids:
        body["red_flags"] = red_flag_ids

    if answers:
        try:
            import json as _json
            parsed = _json.loads(answers)
            body["answers"] = [{"id": k, "value": v} for k, v in parsed.items()]
        except (ValueError, json.JSONDecodeError):
            typer.echo("⚠️ --answers 格式错误，请提供有效 JSON")
            raise typer.Exit(1)

    with httpx.Client() as client:
        result = _post(client, "/api/triage/assess", data=body)

    level = result.get("level", "")
    level_icon = {"紧急": "🔴", "急诊": "🟠", "常规": "🟡", "居家护理": "🟢"}.get(level, "•")
    typer.echo(f"{level_icon} 分诊级别: {level}")
    if result.get("action"):
        typer.echo(f"📋 建议: {result['action']}")

    warnings = result.get("warnings", [])
    if warnings:
        typer.echo(f"\n⚠️ 警告 ({len(warnings)} 项):")
        for w in warnings:
            typer.echo(f"  • {w}")

    recommendations = result.get("recommendations", [])
    if recommendations:
        typer.echo("\n💡 建议:")
        for rec in recommendations:
            typer.echo(f"  • {rec}")

    typer.echo(f"\n⚠️ {result.get('disclaimer', '')}")


# ---------------------------------------------------------------------------
# Account — PIPL compliance (spec §12.2)
# ---------------------------------------------------------------------------

@app.command("account:preview")
def account_preview(
    username: str = typer.Option(..., "--username", "-u"),
    password: str = typer.Option(..., "--password", "-p"),
):
    """预览账户删除将清除的数据。"""
    with httpx.Client() as client:
        login = _post(client, "/api/auth/login", data={"username": username, "password": password})
        result = _get_authed(client, "/api/account/preview", token=login["access_token"])
    typer.echo(f"👤 用户: {result.get('username', '')}")
    counts = result.get("data_counts", {})
    typer.echo(f"📊 数据统计 (共 {result.get('total_records', 0)} 条记录):")
    for table, count in counts.items():
        typer.echo(f"  {table}: {count} 条")


@app.command("account:delete")
def account_delete(
    username: str = typer.Option(..., "--username", "-u"),
    password: str = typer.Option(..., "--password", "-p"),
    confirm: bool = typer.Option(False, "--confirm", help="跳过确认提示，直接删除"),
):
    """永久删除账户及全部数据（PIPL §47，不可逆）。"""
    if not confirm:
        typer.echo("⚠️  警告：此操作将永久删除您的账户及所有关联数据，不可恢复！")
        typer.echo(f"   用户: {username}")
        typer.echo("   如需继续，请输入 DELETE 确认，或使用 --confirm 跳过此提示")
        typed = typer.prompt("请输入 DELETE 确认删除", default="")
        if typed.strip() != "DELETE":
            typer.echo("❌ 已取消")
            raise typer.Exit(0)

    with httpx.Client() as client:
        login = _post(client, "/api/auth/login", data={"username": username, "password": password})
        result = _delete_authed(client, "/api/account", token=login["access_token"])
    typer.echo(f"✅ {result.get('message', '账户已删除')}")
    typer.echo(f"   时间: {result.get('timestamp', '')}")


# ---------------------------------------------------------------------------
# Schemas — JSON schema definitions (no auth required)
# ---------------------------------------------------------------------------

@app.command("schemas:list")
def schemas_list():
    """列出所有可用的实体 Schema 定义。"""
    with httpx.Client() as client:
        result = _get(client, "/api/schemas")
    items = result.get("items", [])
    typer.echo(f"共 {len(items)} 个 Schema:")
    for item in items:
        typer.echo(f"  [{item.get('node_type', item.get('type', ''))}] {item.get('display_name', item.get('name', ''))} — {item.get('description', '')[:50]}")


@app.command("schemas:get")
def schemas_get(
    node_type: str = typer.Argument(..., help="实体类型 (如 herb/medicine/formula)"),
):
    """查看指定实体的 Schema 定义。"""
    with httpx.Client() as client:
        result = _get(client, f"/api/schemas/{node_type}")
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    app()
