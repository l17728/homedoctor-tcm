"""Family Doctor CLI — typer + httpx HTTP client."""

from __future__ import annotations

import json
from contextlib import ExitStack
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


def _get_with_params(path: str, params: dict | None = None) -> dict:
    """Convenience GET for grouped domain commands."""
    with httpx.Client() as client:
        return _get(client, path, {k: v for k, v in (params or {}).items() if v is not None})


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


def _get_authed(
    client: httpx.Client,
    path: str,
    token: str,
    params: dict | None = None,
    *,
    raw: bool = False,
) -> dict | bytes:
    """GET request with Bearer token."""
    try:
        r = client.get(f"{BASE_URL}{path}", params=params, headers={"Authorization": f"Bearer {token}"})
        r.raise_for_status()
        if raw:
            return r.content
        return r.json()
    except httpx.ConnectError:
        typer.echo("❌ 无法连接到服务，请确认服务已启动")
        raise typer.Exit(1)
    except httpx.HTTPStatusError as e:
        typer.echo(f"❌ 请求失败: {e.response.status_code} {e.response.text}")
        raise typer.Exit(1)


def _post_authed(client: httpx.Client, path: str, token: str, data: dict | None = None, *, raw: bool = False) -> dict | bytes:
    """POST request with Bearer token."""
    try:
        r = client.post(f"{BASE_URL}{path}", json=data, headers={"Authorization": f"Bearer {token}"})
        r.raise_for_status()
        if raw:
            return r.content
        return r.json()
    except httpx.ConnectError:
        typer.echo("❌ 无法连接到服务，请确认服务已启动")
        raise typer.Exit(1)


def _put_authed(client: httpx.Client, path: str, token: str, data: dict | None = None) -> dict:
    try:
        r = client.put(f"{BASE_URL}{path}", json=data, headers={"Authorization": f"Bearer {token}"})
        r.raise_for_status()
        return r.json()
    except httpx.HTTPError as e:
        typer.echo(f"❌ 请求失败: {e}")
        raise typer.Exit(1)


def _delete_authed(client: httpx.Client, path: str, token: str) -> dict:
    try:
        r = client.delete(f"{BASE_URL}{path}", headers={"Authorization": f"Bearer {token}"})
        r.raise_for_status()
        return r.json()
    except httpx.HTTPError as e:
        typer.echo(f"❌ 请求失败: {e}")
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
# Notifications
# ---------------------------------------------------------------------------

@app.command("notifications:list")
def notifications_list(token: str = typer.Option(..., "--token")):
    """列出当前用户通知。"""
    with httpx.Client() as client:
        result = _get_authed(client, "/api/notifications", token)
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


@app.command("notifications:read")
def notifications_read(notification_id: str = typer.Argument(...), token: str = typer.Option(..., "--token")):
    """将通知标记为已读。"""
    with httpx.Client() as client:
        result = _post_authed(client, f"/api/notifications/{notification_id}/read", token)
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


@app.command("auth:logout")
def auth_logout(token: str = typer.Option(..., "--token", help="当前访问令牌")):
    """撤销当前访问令牌。"""
    with httpx.Client() as client:
        result = _post_authed(client, "/api/auth/logout", token)
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# Additional high-frequency commands
# ---------------------------------------------------------------------------
@app.command("auth:me")
def auth_me(token: str = typer.Option(..., "--token")):
    """鏌ョ湅褰撳墠璁よ瘉鐢ㄦ埛銆"""
    with httpx.Client() as client:
        result = _get_authed(client, "/api/auth/me", token)
    _print_json(result)


@app.command("auth:consent-status")
def auth_consent_status(token: str = typer.Option(..., "--token")):
    """鏌ョ湅褰撳墠璐﹀彿鐨勫悓鎰忕姸鎬併"""
    with httpx.Client() as client:
        result = _get_authed(client, "/api/auth/consent-status", token)
    _print_json(result)


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


@app.command("herbs:formulas")
def herbs_formulas(herb_id: str = typer.Argument(..., help="中药ID")):
    """列出包含指定中药的方剂。"""
    with httpx.Client() as client:
        result = _get(client, f"/api/herbs/{herb_id}/formulas")
    _print_json(result)


@app.command("herbs:compare")
def herbs_compare(
    herb_a: str = typer.Argument(..., help="第一味中药ID"),
    herb_b: str = typer.Argument(..., help="第二味中药ID"),
):
    """对比两味中药的属性和配伍信息。"""
    with httpx.Client() as client:
        result = _get(client, f"/api/comparisons/herbs/{herb_a}/{herb_b}")
    _print_json(result)


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


@app.command("formulas:tree")
def formulas_tree(formula_id: str = typer.Argument(..., help="方剂ID")):
    """查看方剂的演化关系树。"""
    with httpx.Client() as client:
        result = _get(client, f"/api/formulas/{formula_id}/tree")
    _print_json(result)


@app.command("formulas:roles")
def formulas_roles(formula_id: str = typer.Argument(..., help="方剂ID")):
    """查看方剂中药味的君臣佐使分类。"""
    with httpx.Client() as client:
        result = _get(client, f"/api/formulas/{formula_id}/roles")
    _print_json(result)


@app.command("formulas:safety")
def formulas_safety(
    formula_id: str = typer.Argument(..., help="方剂ID"),
    token: str = typer.Option(..., "--token", help="当前访问令牌"),
):
    """检查方剂安全性并输出适合语音播报的摘要。"""
    with httpx.Client() as client:
        check = _get_authed(client, f"/api/formulas/{formula_id}/safety-check", token)
        speech = _get_authed(client, f"/api/formulas/{formula_id}/safety-text", token, raw=True)
    _print_json({"safety_check": check})
    typer.echo(speech.decode("utf-8"))


@app.command("formulas:compare")
def formulas_compare(formula_ids: str = typer.Argument(..., help="至少两个方剂ID，以逗号分隔")):
    """对比多首方剂的组成、功效和安全信息。"""
    ids = [value.strip() for value in formula_ids.split(",") if value.strip()]
    if len(ids) < 2:
        typer.echo("至少需要两个方剂ID")
        raise typer.Exit(2)
    with httpx.Client() as client:
        result = _post(client, "/api/comparisons/formulas", data={"formula_ids": ids})
    _print_json(result)


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
# Additional medicine operations
@app.command("medicines:detail")
def medicines_detail(medicine_id: str = typer.Argument(...)):
    """鏌ョ湅瀹跺涵鑽涓殑鑽搧璇︽儏銆"""
    with httpx.Client() as client:
        result = _get(client, f"/api/medicines/{medicine_id}")
    _print_json(result)


@app.command("medicines:update")
def medicines_update(
    medicine_id: str = typer.Argument(...),
    payload: str = typer.Argument(..., help="瑕佹洿鏂扮殑 JSON 瀛楁瀵硅薄"),
    token: str = typer.Option(..., "--token"),
):
    """鏇存柊瀹跺涵鑽涓殑鑽搧淇℃伅銆"""
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        typer.echo(f"JSON 鏃犳晥: {exc}")
        raise typer.Exit(2) from exc
    if not isinstance(data, dict):
        typer.echo("payload 蹇呴』鏄 JSON 瀵硅薄")
        raise typer.Exit(2)
    with httpx.Client() as client:
        result = _put_authed(client, f"/api/medicines/{medicine_id}", token, data)
    _print_json(result)


@app.command("medicines:delete")
def medicines_delete(medicine_id: str = typer.Argument(...), token: str = typer.Option(..., "--token")):
    """鍒犻櫎瀹跺涵鑽涓殑鑽搧銆"""
    with httpx.Client() as client:
        result = _delete_authed(client, f"/api/medicines/{medicine_id}", token)
    _print_json(result)


@app.command("medicines:alerts")
def medicines_alerts(token: str = typer.Option(..., "--token")):
    """汇总药品质量、临期、过期和低库存提醒。"""
    with httpx.Client() as client:
        quality = _get_authed(client, "/api/medicines/quality-alerts", token)
        stock = _get_authed(client, "/api/medicines/alerts/expiring", token)
    _print_json({"quality_alerts": quality, "stock_and_expiry_alerts": stock})


@app.command("medicines:quality")
def medicines_quality(
    medicine_id: str = typer.Argument(...),
    token: str = typer.Option(..., "--token"),
):
    """检查单个药品的质量与保质期状态。"""
    with httpx.Client() as client:
        result = _get_authed(client, f"/api/medicines/{medicine_id}/quality", token)
    _print_json(result)


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
            client, "/api/backup/restore", token=login["access_token"], data={"filename": filename}
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


@app.command("reminders:history")
def reminders_history(
    username: str = typer.Option(..., "--username", "-u"),
    password: str = typer.Option(..., "--password", "-p"),
    days: int = typer.Option(30, "--days", min=1, max=365),
):
    """鏌ョ湅鎻愰啋鎵ц鍘嗗彶銆"""
    with httpx.Client() as client:
        login = _post(client, "/api/auth/login", data={"username": username, "password": password})
        result = _get_authed(client, "/api/reminders/history", login["access_token"], {"days": days})
    _print_json(result)


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
        result = _put_authed(client, f"/api/reminders/{reminder_id}/toggle", token=token)
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

@app.command("constitution:history")
def constitution_history(
    username: str = typer.Option(..., "--username", "-u"),
    password: str = typer.Option(..., "--password", "-p"),
):
    """查看体质测评历史记录。"""
    with httpx.Client() as client:
        login = _post(client, "/api/auth/login", data={"username": username, "password": password})
        result = _get_authed(client, "/api/constitution/history", login["access_token"])
    _print_json(result)


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

@app.command("seasonal-health")
def seasonal_health(
    token: str = typer.Option(..., "--token"),
    term: Optional[str] = typer.Option(None, "--term", help="节气名称；省略时查询当前节气"),
):
    """查看当前或指定节气的养生建议。"""
    params = {"term": term} if term else None
    with httpx.Client() as client:
        result = _get_authed(client, "/api/seasonal-health", token, params)
    _print_json(result)


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


@app.command("family-members:current")
def family_members_current(token: str = typer.Option(..., "--token")):
    """查看当前选中的家庭成员。"""
    with httpx.Client() as client:
        result = _get_authed(client, "/api/family-members/current", token)
    _print_json(result)


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


@app.command("triage:reference")
def triage_reference():
    """查看分诊年龄分组和需要立即就医的危险信号。"""
    with httpx.Client() as client:
        age_groups = _get(client, "/api/triage/age-groups")
        red_flags = _get(client, "/api/triage/red-flags")
    _print_json({"age_groups": age_groups, "red_flags": red_flags})


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


# ---------------------------------------------------------------------------
# Additional API domains (small HTTP-only commands for agent workflows)
# ---------------------------------------------------------------------------

def _print_json(value: dict) -> None:
    typer.echo(json.dumps(value, ensure_ascii=False, indent=2))


@app.command("knowledge:list")
def knowledge_list(
    entity_type: str = typer.Argument(..., help="herbs/formulas/symptoms/meridians/acupoints/therapies"),
    query: Optional[str] = typer.Option(None, "--query", "-q"),
    category: Optional[str] = typer.Option(None, "--category", "-c"),
    meridian: Optional[str] = typer.Option(None, "--meridian"),
    page: int = typer.Option(1, "--page", min=1),
    page_size: int = typer.Option(20, "--page-size", min=1, max=100),
):
    """按实体类型分页浏览结构化中医知识。"""
    params = {"q": query, "category": category, "page": page, "page_size": page_size}
    if meridian:
        params["meridian"] = meridian
    if entity_type == "herbs":
        result = _get_with_params("/api/knowledge/herbs", params)
    elif entity_type == "formulas":
        result = _get_with_params("/api/knowledge/formulas", params)
    elif entity_type == "symptoms":
        result = _get_with_params("/api/knowledge/symptoms", params)
    elif entity_type == "meridians":
        result = _get_with_params("/api/knowledge/meridians", params)
    elif entity_type == "acupoints":
        result = _get_with_params("/api/knowledge/acupoints", params)
    elif entity_type == "therapies":
        result = _get_with_params("/api/knowledge/therapies", params)
    else:
        typer.echo("entity_type 可选值: herbs/formulas/symptoms/meridians/acupoints/therapies")
        raise typer.Exit(2)
    _print_json(result)


@app.command("knowledge:detail")
def knowledge_detail(
    entity_type: str = typer.Argument(..., help="herbs/formulas/meridians/acupoints/therapies"),
    entity_id: str = typer.Argument(...),
):
    """按类型和 ID 查看中医知识实体详情。"""
    if entity_type == "herbs":
        result = _get_with_params(f"/api/knowledge/herbs/{entity_id}", None)
    elif entity_type == "formulas":
        result = _get_with_params(f"/api/knowledge/formulas/{entity_id}", None)
    elif entity_type == "meridians":
        result = _get_with_params(f"/api/knowledge/meridians/{entity_id}", None)
    elif entity_type == "acupoints":
        result = _get_with_params(f"/api/knowledge/acupoints/{entity_id}", None)
    elif entity_type == "therapies":
        result = _get_with_params(f"/api/knowledge/therapies/{entity_id}", None)
    else:
        typer.echo("entity_type 可选值: herbs/formulas/meridians/acupoints/therapies")
        raise typer.Exit(2)
    _print_json(result)


@app.command("knowledge:search")
def knowledge_search(
    query: str = typer.Argument(..., help="搜索关键词"),
    entity_type: Optional[str] = typer.Option(None, "--type"),
    page: int = typer.Option(1, "--page", min=1),
    page_size: int = typer.Option(20, "--page-size", min=1, max=100),
):
    """搜索中医知识实体。"""
    result = _get_with_params("/api/knowledge/search", {
        "q": query, "type": entity_type, "page": page, "page_size": page_size,
    })
    _print_json(result)


@app.command("knowledge:categories")
def knowledge_categories():
    """列出知识实体类型和分类。"""
    _print_json(_get_with_params("/api/knowledge/categories", None))


@app.command("knowledge:browse")
def knowledge_browse(
    entity_type: str = typer.Argument(..., help="实体类型"),
    category: Optional[str] = typer.Option(None, "--category", "-c"),
    query: Optional[str] = typer.Option(None, "--query", "-q"),
    page: int = typer.Option(1, "--page", min=1),
    page_size: int = typer.Option(20, "--page-size", min=1, max=100),
):
    """按实体类型、分类或关键词浏览知识库。"""
    result = _get_with_params("/api/knowledge/browse", {
        "type": entity_type, "category": category, "q": query,
        "page": page, "page_size": page_size,
    })
    _print_json(result)


@app.command("knowledge-hub:search")
def knowledge_hub_search(
    query: Optional[str] = typer.Option(None, "--query", "-q"),
    entity_type: Optional[str] = typer.Option(None, "--type"),
    category: Optional[str] = typer.Option(None, "--category"),
    tag: Optional[str] = typer.Option(None, "--tag"),
    page: int = typer.Option(1, "--page", min=1),
    page_size: int = typer.Option(20, "--page-size", min=1, max=100),
):
    """搜索知识工作台实体。"""
    result = _get_with_params("/api/knowledge-hub/search", {
        "q": query, "type": entity_type, "category": category, "tag": tag,
        "page": page, "page_size": page_size,
    })
    _print_json(result)


@app.command("knowledge-hub:catalog")
def knowledge_hub_catalog(limit: int = typer.Option(10, "--limit", min=1, max=100)):
    """查看知识工作台类型、关系类型、近期和热门实体。"""
    _print_json({
        "types": _get_with_params("/api/knowledge-hub/types", None),
        "relationship_types": _get_with_params("/api/knowledge-hub/relationship-types", None),
        "recent": _get_with_params("/api/knowledge-hub/recent", {"limit": limit}),
        "popular": _get_with_params("/api/knowledge-hub/popular", {"limit": limit}),
    })


@app.command("knowledge-hub:entity")
def knowledge_hub_entity(
    entity_id: str = typer.Argument(...),
    direction: str = typer.Option("both", "--direction"),
):
    """查看知识工作台实体及其关系。"""
    _print_json({
        "entity": _get_with_params(f"/api/knowledge-hub/entities/{entity_id}", None),
        "relationships": _get_with_params(
            f"/api/knowledge-hub/entities/{entity_id}/relationships", {"direction": direction}
        ),
    })


@app.command("rag:search")
def rag_search(query: str = typer.Argument(...), top_k: int = typer.Option(10, "--top-k", min=1, max=100)):
    """执行知识库 RAG 检索。"""
    _print_json(_get_with_params("/api/rag/search", {"q": query, "top_k": top_k}))


@app.command("rag:intent")
def rag_intent(query: str = typer.Argument(...)):
    """识别知识检索意图。"""
    _print_json(_get_with_params("/api/rag/intent", {"q": query}))


@app.command("rag:index-status")
def rag_index_status():
    """查看知识索引状态。"""
    _print_json(_get_with_params("/api/rag/index/status", None))


@app.command("api:request")
def api_request(
    method: str = typer.Argument(..., help="HTTP 方法：GET/POST/PUT/PATCH/DELETE"),
    path: str = typer.Argument(..., help="带真实资源 ID 的 API 路径，例如 /api/auth/me"),
    token: Optional[str] = typer.Option(None, "--token", help="可选 Bearer token"),
    query: Optional[str] = typer.Option(None, "--query", help="查询参数 JSON 对象"),
    body: Optional[str] = typer.Option(None, "--body", help="请求体 JSON"),
    form: Optional[str] = typer.Option(None, "--form", help="表单字段 JSON 对象（可与 --file 同用）"),
    file_paths: list[str] = typer.Option([], "--file", help="上传文件路径；多文件接口可重复传入"),
    file_field: str = typer.Option("file", "--file-field", help="上传文件的表单字段名"),
    output: Optional[str] = typer.Option(None, "--output", help="将非 JSON 响应保存到文件"),
):
    """调用任意已公开的 API 路由，覆盖专用命令尚未封装的端点。"""
    method = method.upper()
    if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
        typer.echo("HTTP 方法必须为 GET、POST、PUT、PATCH 或 DELETE")
        raise typer.Exit(2)
    if not path.startswith("/api/") or ".." in path.split("/"):
        typer.echo("路径必须是 /api/ 下的站内 API 路径")
        raise typer.Exit(2)
    try:
        params = json.loads(query) if query else None
        payload = json.loads(body) if body else None
        form_data = json.loads(form) if form else None
    except json.JSONDecodeError as exc:
        typer.echo(f"JSON 参数无效: {exc}")
        raise typer.Exit(2) from exc
    if params is not None and not isinstance(params, dict):
        typer.echo("--query 必须是 JSON 对象")
        raise typer.Exit(2)
    if form_data is not None and not isinstance(form_data, dict):
        typer.echo("--form 必须是 JSON 对象")
        raise typer.Exit(2)
    if form_data is not None and payload is not None:
        typer.echo("--form 与 --body 不能同时使用")
        raise typer.Exit(2)

    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        with httpx.Client() as client:
            request_options = {"params": params, "headers": headers}
            if file_paths:
                with ExitStack() as stack:
                    uploads = [stack.enter_context(open(file_name, "rb")) for file_name in file_paths]
                    request_options["data"] = form_data or {}
                    request_options["files"] = [
                        (file_field, (upload.name, upload)) for upload in uploads
                    ]
                    response = client.request(method, f"{BASE_URL}{path}", **request_options)
            elif form_data is not None:
                request_options["data"] = form_data
                response = client.request(method, f"{BASE_URL}{path}", **request_options)
            else:
                request_options["json"] = payload
                response = client.request(method, f"{BASE_URL}{path}", **request_options)
            response.raise_for_status()
    except httpx.ConnectError:
        typer.echo("无法连接到服务，请确认服务已启动 (python -m uvicorn app.main:app)")
        raise typer.Exit(1)
    except httpx.HTTPStatusError as exc:
        typer.echo(f"请求失败: {exc.response.status_code} {exc.response.text}")
        raise typer.Exit(1)

    if output:
        with open(output, "wb") as file:
            file.write(response.content)
        typer.echo(f"响应已保存到 {output}")
        return
    try:
        typer.echo(json.dumps(response.json(), ensure_ascii=False, indent=2))
    except ValueError:
        typer.echo(response.text)


@app.command("medication-plans:list")
def medication_plans_list(token: str = typer.Option(..., "--token")):
    with httpx.Client() as client:
        result = _get_authed(client, "/api/medication-plans", token)
    _print_json(result)


@app.command("medication-plans:create")
def medication_plans_create(payload: str = typer.Argument(..., help="JSON 请求体"), token: str = typer.Option(..., "--token")):
    with httpx.Client() as client:
        result = _post_authed(client, "/api/medication-plans", token, json.loads(payload))
    _print_json(result)


@app.command("medication-plans:detail")
def medication_plans_detail(plan_id: str = typer.Argument(...), token: str = typer.Option(..., "--token")):
    with httpx.Client() as client:
        result = _get_authed(client, f"/api/medication-plans/{plan_id}", token)
    _print_json(result)


@app.command("health-logs:list")
def health_logs_list(token: str = typer.Option(..., "--token")):
    with httpx.Client() as client:
        result = _get_authed(client, "/api/health-logs", token)
    _print_json(result)


@app.command("health-logs:create")
def health_logs_create(payload: str = typer.Argument(..., help="JSON 请求体"), token: str = typer.Option(..., "--token")):
    with httpx.Client() as client:
        result = _post_authed(client, "/api/health-logs", token, json.loads(payload))
    _print_json(result)


@app.command("health-logs:latest")
def health_logs_latest(token: str = typer.Option(..., "--token")):
    with httpx.Client() as client:
        result = _get_authed(client, "/api/health-logs/latest", token)
    _print_json(result)


@app.command("medical-visits:list")
def medical_visits_list(token: str = typer.Option(..., "--token")):
    with httpx.Client() as client:
        result = _get_authed(client, "/api/visits", token)
    _print_json(result)


@app.command("medical-visits:detail")
def medical_visits_detail(visit_id: str = typer.Argument(...), token: str = typer.Option(..., "--token")):
    with httpx.Client() as client:
        result = _get_authed(client, f"/api/visits/{visit_id}", token)
    _print_json(result)


@app.command("reports:list")
def reports_list(
    token: str = typer.Option(..., "--token"),
    period: str = typer.Option("30d", "--period", help="统计周期：7d、30d 或 90d"),
):
    with httpx.Client() as client:
        result = _get_authed(client, "/api/reports/health-trend", token, {"period": period})
    _print_json(result)


@app.command("reports:constitution")
def reports_constitution(token: str = typer.Option(..., "--token")):
    """生成体质调理报告。"""
    with httpx.Client() as client:
        result = _get_authed(client, "/api/reports/constitution", token)
    _print_json(result)


@app.command("reports:pre-visit")
def reports_pre_visit(token: str = typer.Option(..., "--token")):
    """生成就诊准备摘要。"""
    with httpx.Client() as client:
        result = _get_authed(client, "/api/reports/pre-visit", token)
    _print_json(result)


@app.command("reports:generate")
def reports_generate(payload: str = typer.Argument(..., help="JSON 请求体"), output: str = typer.Option("health-report.pdf", "--output"), token: str = typer.Option(..., "--token")):
    with httpx.Client() as client:
        result = _post_authed(client, "/api/reports/generate-pdf", token, json.loads(payload), raw=True)
    with open(output, "wb") as file:
        file.write(result)
    typer.echo(f"已保存 PDF：{output}")


@app.command("prescriptions:generate")
def prescriptions_generate(payload: str = typer.Argument(..., help="JSON 请求体"), output: str = typer.Option("prescription.pdf", "--output"), token: str = typer.Option(..., "--token")):
    with httpx.Client() as client:
        result = _post_authed(client, "/api/prescriptions/generate", token, json.loads(payload), raw=True)
    with open(output, "wb") as file:
        file.write(result)
    typer.echo(f"已保存 PDF：{output}")


@app.command("prescriptions:health-report")
def prescriptions_health_report(payload: str = typer.Argument(..., help="JSON 请求体"), output: str = typer.Option("health-summary.pdf", "--output"), token: str = typer.Option(..., "--token")):
    with httpx.Client() as client:
        result = _post_authed(client, "/api/prescriptions/health-report", token, json.loads(payload), raw=True)
    with open(output, "wb") as file:
        file.write(result)
    typer.echo(f"已保存 PDF：{output}")


@app.command("share-cards:list")
def share_cards_list(token: str = typer.Option(..., "--token")):
    with httpx.Client() as client:
        result = _get_authed(client, "/api/share-cards/list", token)
    _print_json(result)


@app.command("share-cards:detail")
def share_cards_detail(card_id: str = typer.Argument(...), token: str = typer.Option(..., "--token")):
    with httpx.Client() as client:
        result = _get_authed(client, f"/api/share-cards/{card_id}", token)
    _print_json(result)


@app.command("remote-assist:invite")
def remote_assist_invite(payload: str = typer.Argument(..., help="JSON 请求体"), token: str = typer.Option(..., "--token")):
    with httpx.Client() as client:
        result = _post_authed(client, "/api/remote-assist/invite", token, json.loads(payload))
    _print_json(result)


@app.command("remote-assist:summary")
def remote_assist_summary(user_id: str = typer.Argument(...), token: str = typer.Option(..., "--token")):
    with httpx.Client() as client:
        result = _get_authed(client, f"/api/remote-assist/{user_id}/summary", token)
    _print_json(result)


@app.command("remote-assist:weekly-report")
def remote_assist_weekly_report(user_id: str = typer.Argument(...), token: str = typer.Option(..., "--token")):
    with httpx.Client() as client:
        result = _get_authed(client, f"/api/remote-assist/{user_id}/weekly-report", token)
    _print_json(result)


@app.command("therapies:list")
def therapies_list(token: str = typer.Option(..., "--token")):
    with httpx.Client() as client:
        result = _get_authed(client, "/api/therapies", token)
    _print_json(result)


@app.command("therapies:categories")
def therapies_categories():
    """列出外治理疗分类。"""
    with httpx.Client() as client:
        result = _get(client, "/api/therapies/categories")
    _print_json(result)


@app.command("therapies:search")
def therapies_search(
    query: str = typer.Argument(..., help="搜索关键词"),
    category: Optional[str] = typer.Option(None, "--category", "-c"),
):
    """按关键词查找外治理疗，并可按分类筛选。"""
    params = {"q": query}
    if category:
        params["category"] = category
    with httpx.Client() as client:
        result = _get(client, "/api/therapies/search", params=params)
    _print_json(result)


@app.command("therapies:detail")
def therapies_detail(therapy_id: str = typer.Argument(...), token: str = typer.Option(..., "--token")):
    with httpx.Client() as client:
        result = _get_authed(client, f"/api/therapies/{therapy_id}", token)
    _print_json(result)


@app.command("therapies:safety")
def therapies_safety(therapy_id: str = typer.Argument(...), token: str = typer.Option(..., "--token")):
    with httpx.Client() as client:
        result = _get_authed(client, f"/api/therapies/{therapy_id}/safety", token)
    _print_json(result)


@app.command("classics:list")
def classics_list():
    with httpx.Client() as client:
        result = _get(client, "/api/classics")
    _print_json(result)


@app.command("classics:detail")
def classics_detail(classic_id: str = typer.Argument(...)):
    with httpx.Client() as client:
        result = _get(client, f"/api/classics/{classic_id}")
    _print_json(result)


@app.command("bookmarks:list")
def bookmarks_list(token: str = typer.Option(..., "--token")):
    with httpx.Client() as client:
        result = _get_authed(client, "/api/bookmarks", token)
    _print_json(result)


@app.command("bookmarks:add")
def bookmarks_add(payload: str = typer.Argument(..., help="JSON 请求体"), token: str = typer.Option(..., "--token")):
    with httpx.Client() as client:
        result = _post_authed(client, "/api/bookmarks", token, json.loads(payload))
    _print_json(result)


@app.command("bookmarks:detail")
def bookmarks_detail(bookmark_id: str = typer.Argument(...), token: str = typer.Option(..., "--token")):
    with httpx.Client() as client:
        result = _get_authed(client, f"/api/bookmarks/{bookmark_id}", token)
    _print_json(result)


@app.command("formulations:recommend")
def formulations_recommend(payload: str = typer.Argument(..., help="JSON 请求体"), token: str = typer.Option(..., "--token")):
    with httpx.Client() as client:
        result = _post_authed(client, "/api/formulations/recommend", token, json.loads(payload))
    _print_json(result)


@app.command("formulations:from-inventory")
def formulations_from_inventory(payload: str = typer.Argument(..., help="JSON 请求体"), token: str = typer.Option(..., "--token")):
    with httpx.Client() as client:
        result = _post_authed(client, "/api/formulations/from-inventory", token, json.loads(payload))
    _print_json(result)


@app.command("favorites:list")
def favorites_list(token: str = typer.Option(..., "--token")):
    with httpx.Client() as client:
        result = _get_authed(client, "/api/favorites", token)
    _print_json(result)


@app.command("favorites:add")
def favorites_add(payload: str = typer.Argument(..., help="JSON 请求体"), token: str = typer.Option(..., "--token")):
    with httpx.Client() as client:
        result = _post_authed(client, "/api/favorites", token, json.loads(payload))
    _print_json(result)


@app.command("favorites:detail")
def favorites_detail(entry_id: str = typer.Argument(...), token: str = typer.Option(..., "--token")):
    with httpx.Client() as client:
        result = _get_authed(client, f"/api/favorites/{entry_id}", token)
    _print_json(result)


@app.command("favorites:check")
def favorites_check(
    entry_type: str = typer.Argument(...),
    source_id: str = typer.Argument(...),
    token: str = typer.Option(..., "--token"),
):
    """检查知识条目是否已加入收藏。"""
    with httpx.Client() as client:
        result = _post_authed(client, "/api/favorites/check", token, {
            "entry_type": entry_type, "source_id": source_id,
        })
    _print_json(result)


@app.command("knowledge-import:recent")
def knowledge_import_recent(token: str = typer.Option(..., "--token")):
    with httpx.Client() as client:
        result = _get_authed(client, "/api/knowledge-import/recent", token)
    _print_json(result)


@app.command("knowledge-import:url")
def knowledge_import_url(url: str = typer.Argument(..., help="要导入的网页地址"), token: str = typer.Option(..., "--token")):
    with httpx.Client() as client:
        result = _post_authed(client, "/api/knowledge-hub/import-url", token, {"url": url})
    _print_json(result)


@app.command("knowledge-import:delete")
def knowledge_import_delete(entry_id: str = typer.Argument(...), token: str = typer.Option(..., "--token")):
    with httpx.Client() as client:
        result = _delete_authed(client, f"/api/knowledge-import/{entry_id}", token)
    _print_json(result)


@app.command("extractor:auto-extract")
def extractor_auto_extract(payload: str = typer.Argument(..., help="JSON 请求体"), token: str = typer.Option(..., "--token")):
    with httpx.Client() as client:
        result = _post_authed(client, "/api/extractor/auto-extract", token, json.loads(payload))
    _print_json(result)


@app.command("extractor:recent")
def extractor_recent(token: str = typer.Option(..., "--token")):
    with httpx.Client() as client:
        result = _get_authed(client, "/api/extractor/recent", token)
    _print_json(result)


@app.command("dashboard:get")
def dashboard_get(token: str = typer.Option(..., "--token")):
    with httpx.Client() as client:
        result = _get_authed(client, "/api/dashboard/stats", token)
    _print_json(result)


if __name__ == "__main__":
    app()
