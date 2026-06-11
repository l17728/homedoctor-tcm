"""Dashboard Stats router — aggregated statistics.

Returns: herb_count, formula_count, medicine_count, safety_alert_count,
         recent_searches, stock_alerts.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.auth import get_current_user
from app.database import DbAdapter, get_db
from app.repository import current_tenant_id

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/stats")
async def get_dashboard_stats(
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Return aggregated dashboard statistics.

    - herb_count, formula_count: global knowledge base counts
    - medicine_count: user's own medicines (auth required)
    - safety_alert_count: total enabled safety rules
    - stock_alerts: user's expiring/low-stock medicines
    - recent_searches: placeholder for MVP
    """
    # Global counts
    herb_row = await db.query_one("SELECT COUNT(*) as cnt FROM herbs")
    herb_count = herb_row["cnt"] if herb_row else 0

    formula_row = await db.query_one("SELECT COUNT(*) as cnt FROM formulas")
    formula_count = formula_row["cnt"] if formula_row else 0

    # Safety alert count (enabled rules)
    safety_row = await db.query_one(
        "SELECT COUNT(*) as cnt FROM safety_rules WHERE enabled = 1"
    )
    safety_alert_count = safety_row["cnt"] if safety_row else 0

    # User's medicines count (tenant-scoped)
    tid = current_tenant_id.get()
    med_row = await db.query_one(
        "SELECT COUNT(*) as cnt FROM medicines WHERE tenant_id = ?",
        (tid,),
    )
    medicine_count = med_row["cnt"] if med_row else 0

    # Stock alerts: expiring within 30 days + expired + low stock
    stock_alerts: list[dict[str, Any]] = []

    expired_rows = await db.query(
        """SELECT name, expiry_date, quantity FROM medicines
           WHERE tenant_id = ? AND expiry_date IS NOT NULL
           AND date(expiry_date) < date('now')
           ORDER BY expiry_date ASC""",
        (tid,),
    )
    for row in expired_rows:
        stock_alerts.append({
            "type": "已过期",
            "name": row["name"],
            "detail": f"过期日期：{row['expiry_date']}",
            "severity": "critical",
        })

    expiring_rows = await db.query(
        """SELECT name, expiry_date, quantity FROM medicines
           WHERE tenant_id = ? AND expiry_date IS NOT NULL
           AND date(expiry_date) <= date('now', '+30 days')
           AND date(expiry_date) >= date('now')
           ORDER BY expiry_date ASC""",
        (tid,),
    )
    for row in expiring_rows:
        stock_alerts.append({
            "type": "即将过期",
            "name": row["name"],
            "detail": f"过期日期：{row['expiry_date']}",
            "severity": "warning",
        })

    low_stock_rows = await db.query(
        """SELECT name, quantity FROM medicines
           WHERE tenant_id = ? AND quantity <= 3
           ORDER BY quantity ASC""",
        (tid,),
    )
    for row in low_stock_rows:
        stock_alerts.append({
            "type": "库存不足",
            "name": row["name"],
            "detail": f"当前库存：{row['quantity']}",
            "severity": "info",
        })

    # Recent searches: placeholder for MVP (would come from search_logs table in v2)
    recent_searches: list[str] = []

    return {
        "herb_count": herb_count,
        "formula_count": formula_count,
        "medicine_count": medicine_count,
        "safety_alert_count": safety_alert_count,
        "recent_searches": recent_searches,
        "stock_alerts": stock_alerts,
    }
