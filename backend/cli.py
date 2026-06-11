"""Family Doctor CLI — typer + httpx HTTP client."""

from __future__ import annotations

import json
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


if __name__ == "__main__":
    app()
