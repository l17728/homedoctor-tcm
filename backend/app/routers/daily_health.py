"""Daily Health Card router — today's personalized health card.

Returns: 当前节气, 体质建议, 药箱库存预警, 季节养生贴士.
"""

from __future__ import annotations


import logging

logger = logging.getLogger(__name__)
import json
from datetime import date, datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends

from app.auth import get_current_user
from app.database import DbAdapter, get_db
from app.repository import current_tenant_id
from app.solar_terms import get_next_term, get_season, get_solar_term

router = APIRouter(prefix="/api/daily-health", tags=["daily-health"])


# ---------------------------------------------------------------------------
# Hardcoded MVP data
# ---------------------------------------------------------------------------

# 体质养生建议 (hardcoded for MVP, will be AI-generated in v2)
CONSTITUTION_TIPS: dict[str, list[str]] = {
    "平和质": ["饮食均衡，不偏食", "适度运动，保持规律作息", "四季均可进行户外活动"],
    "气虚质": ["宜食益气健脾食物：黄芪、党参、山药", "避免过度劳累", "适合散步、太极等轻运动"],
    "阳虚质": ["宜食温热食物：生姜、羊肉、桂圆", "注意保暖，避免受寒", "适合艾灸、泡脚"],
    "阴虚质": ["宜食滋阴食物：百合、银耳、枸杞", "避免辛辣燥热食物", "保持充足睡眠"],
    "痰湿质": ["宜食健脾利湿食物：薏苡仁、冬瓜", "减少甜食和油腻", "加强体育锻炼"],
    "湿热质": ["宜食清热利湿食物：绿豆、苦瓜", "忌辛辣、酒类", "适合游泳、跑步"],
    "血瘀质": ["宜食活血食物：山楂、桃仁、红花", "保持心情舒畅", "适合有氧运动"],
    "气郁质": ["宜食疏肝理气食物：玫瑰花、佛手", "多参加社交活动", "听音乐、练习冥想"],
    "特禀质": ["避免过敏原", "增强体质，改善免疫功能", "注意饮食清淡"],
}

# 季节养生贴士
SEASON_ADVICE: dict[str, list[str]] = {
    "春": [
        "春季养生重在养肝，宜疏肝理气",
        "早睡早起，适当增加户外活动",
        "饮食宜清淡，多吃绿色蔬菜",
        "注意防范春季过敏和感冒",
    ],
    "夏": [
        "夏季养生重在养心，宜清心祛暑",
        "避免正午高温时段外出",
        "多饮水，适量食用苦味食物清热",
        "不宜过度贪凉，避免损伤脾胃",
    ],
    "秋": [
        "秋季养生重在养肺，宜润燥养阴",
        "早睡早起，收敛精神",
        "多食滋阴润燥食物：梨、银耳、蜂蜜",
        "注意保暖，预防秋燥咳嗽",
    ],
    "冬": [
        "冬季养生重在养肾，宜温补藏精",
        "早睡晚起，避寒保暖",
        "适量进补温热食物：羊肉、桂圆、核桃",
        "泡脚养生，温通经络",
    ],
}

# 节气对应的推荐中药材
TERM_SEASONAL_HERBS: dict[str, list[dict[str, str]]] = {
    "春": [
        {"name": "菊花", "reason": "春季养肝，菊花清肝明目"},
        {"name": "薄荷", "reason": "疏风散热，缓解春困"},
        {"name": "柴胡", "reason": "疏肝解郁，调和肝脾"},
    ],
    "夏": [
        {"name": "金银花", "reason": "清热解毒，夏季防暑"},
        {"name": "荷叶", "reason": "清暑利湿，解暑热"},
        {"name": "绿豆", "reason": "清热解毒，消暑止渴"},
    ],
    "秋": [
        {"name": "百合", "reason": "润肺止咳，秋季养阴"},
        {"name": "麦冬", "reason": "养阴生津，润肺清心"},
        {"name": "沙参", "reason": "养阴清肺，益胃生津"},
    ],
    "冬": [
        {"name": "黄芪", "reason": "补气升阳，冬季增强免疫力"},
        {"name": "当归", "reason": "补血活血，温通经脉"},
        {"name": "肉桂", "reason": "温肾壮阳，散寒止痛"},
    ],
}


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.get("")
async def get_daily_health_card(
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Return today's health card for the authenticated user."""
    today = date.today()
    solar_term = get_solar_term(today)
    season = get_season(solar_term)
    next_term_name, days_to_next = get_next_term(today)

    # Stock alerts: medicines expiring soon or low quantity
    tid = current_tenant_id.get()
    stock_alerts: list[dict[str, Any]] = []

    # Expiring medicines (within 30 days)
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

    # Already expired
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

    # Low stock
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
            "severity": "warning",
        })

    constitution_row = await db.query_one(
        "SELECT constitution_type FROM user_profiles WHERE user_id = ?",
        (current_user["id"],),
    )
    constitution_type = "平和质"
    if constitution_row and constitution_row.get("constitution_type"):
        constitution_type = constitution_row["constitution_type"]

    recent_consultations = await db.query(
        """SELECT title FROM conversations
           WHERE user_id = ? AND datetime(created_at) >= datetime('now', '-7 days')
           ORDER BY datetime(created_at) DESC LIMIT 5""",
        (current_user["id"],),
    )

    return {
        "date": today.isoformat(),
        "solar_term": solar_term,
        "season": season,
        "next_term": next_term_name,
        "days_to_next_term": days_to_next,
        "season_advice": SEASON_ADVICE.get(season, []),
        "constitution_tips": CONSTITUTION_TIPS.get(constitution_type, CONSTITUTION_TIPS["平和质"]),
        "stock_alerts": stock_alerts,
        "seasonal_herbs": TERM_SEASONAL_HERBS.get(season, []),
        "recent_consultations": {
            "period_days": 7,
            "count": len(recent_consultations),
            "topics": [
                str(row.get("title") or "未命名咨询")[:120]
                for row in recent_consultations
            ],
        },
    }
