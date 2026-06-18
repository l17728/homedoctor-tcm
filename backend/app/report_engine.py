"""健康报告生成引擎 — 报告中心 (spec §7 / §13.3 V3 P0).

Three report types, each aggregating from existing structured data sources:

* **体质报告 (Constitution Report)** — latest assessment, score trends,
  personalized recommendations, seasonal advice, dietary & exercise guidance.
* **健康趋势报告 (Health Trend Report)** — medication adherence over
  7/30/90 days, reminder completion, medicine cabinet changes, chat
  interaction frequency, safety check history.
* **就诊准备报告 (Pre-Visit Report)** — current medications, allergies,
  constitution summary, recent chat questions, safety check results, and
  auto-generated questions for the doctor.

All reports share a common envelope: ``generated_at``, ``data_period``,
``disclaimer``. Domain language is Chinese throughout (spec §1.7).

Data flows (spec §1.4 — 结构化是权威):
    SQLite (nodes/tables) → report_engine (read-only aggregation) → report dict

No writes go through this module; reports are derived views.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.constitution_data import CONSTITUTION_DESCRIPTIONS, NINE_CONSTITUTION_TYPES
from app.database import DbAdapter
from app.solar_terms import get_solar_term, get_season

# China Standard Time — all user-facing dates are CST
CST = timezone(timedelta(hours=8))

# Universal disclaimer appended to every report (spec §15 第5层)
DISCLAIMER = (
    "⚠ 本报告由家庭医生系统根据您的健康数据自动生成，仅供个人健康管理参考，"
    "不构成医疗诊断或处方建议。如有不适或用药疑问，请咨询您的主治医师或执业药师。"
)


# ---------------------------------------------------------------------------
# Per-constitution recommendations (diet / exercise / lifestyle)
# ---------------------------------------------------------------------------

CONSTITUTION_DIET: dict[str, dict[str, list[str]]] = {
    "平和质": {
        "宜食": ["饮食均衡，五谷为养", "时令蔬果", "适量优质蛋白"],
        "忌食": ["偏食挑食", "暴饮暴食"],
    },
    "气虚质": {
        "宜食": ["黄芪、党参、山药补气", "红枣、小米健脾", "鸡肉、牛肉益气"],
        "忌食": ["生冷寒凉耗气之品", "过度油腻", "萝卜破气"],
    },
    "阳虚质": {
        "宜食": ["羊肉、鹿肉温补阳气", "生姜、肉桂、韭菜温阳", "核桃、板栗补肾阳"],
        "忌食": ["冷饮冰品", "西瓜、苦瓜等寒凉食物", "绿豆清热败火"],
    },
    "阴虚质": {
        "宜食": ["银耳、百合、沙参滋阴", "梨、蜂蜜润燥", "鸭肉、甲鱼养阴"],
        "忌食": ["辛辣燥热：辣椒、花椒", "烧烤油炸", "羊肉、鹿肉温热伤阴"],
    },
    "痰湿质": {
        "宜食": ["薏苡仁、赤小豆利湿", "冬瓜、萝卜化痰", "陈皮、荷叶理气化湿"],
        "忌食": ["肥甘厚腻", "甜食生痰", "酒类助湿"],
    },
    "湿热质": {
        "宜食": ["绿豆、苦瓜清热", "薏苡仁、冬瓜利湿", "绿茶、菊花茶清利"],
        "忌食": ["辛辣刺激", "煎炸烧烤", "酒类、甜食助湿热"],
    },
    "血瘀质": {
        "宜食": ["山楂、桃仁活血化瘀", "黑木耳、茄子散瘀", "玫瑰花、藏红花行血"],
        "忌食": ["寒凉收引之品", "高脂油腻阻碍血行"],
    },
    "气郁质": {
        "宜食": ["柑橘、佛手理气解郁", "玫瑰花茶疏肝", "荞麦、刀豆调畅气机"],
        "忌食": ["咖啡浓茶过度兴奋", "收涩酸敛之品"],
    },
    "特禀质": {
        "宜食": ["黄芪、防风益气固表", "清淡均衡饮食", "新鲜蔬果增强免疫"],
        "忌食": ["已知过敏食物", "海鲜、蚕豆等易致敏食物", "酒类、辛辣刺激"],
    },
}

CONSTITUTION_EXERCISE: dict[str, list[str]] = {
    "平和质": ["快走、慢跑、游泳等有氧运动", "每周3-5次，每次30-45分钟", "可参加各类球类运动"],
    "气虚质": ["太极拳、八段锦柔和运动", "散步为主，循序渐进", "避免大汗淋漓耗气"],
    "阳虚质": ["春夏晨练晒太阳", "慢跑、跳绳鼓舞阳气", "避免冬泳等过度寒冷运动"],
    "阴虚质": ["游泳、太极拳等中小强度", "避免剧烈出汗运动", "瑜伽拉伸养阴安神"],
    "痰湿质": ["有氧运动为主：慢跑、骑车", "持续时间宜长以化痰湿", "球类、武术皆宜"],
    "湿热质": ["中长跑、游泳、爬山", "大运动量、高强度有氧", "运动后及时补充水分"],
    "血瘀质": ["健美操、舞蹈、太极剑", "按摩推拿促进血行", "保健按摩阿是穴"],
    "气郁质": ["群体运动：球类、登山", "跑步、游泳发泄郁结", "瑜伽冥想调节情志"],
    "特禀质": ["室内运动为主避免花粉", "游泳、瑜伽增强体质", "循序渐进增强免疫"],
}

CONSTITUTION_LIFESTYLE: dict[str, list[str]] = {
    "平和质": ["规律作息，劳逸结合", "保持积极乐观心态"],
    "气虚质": ["充足睡眠，避免熬夜", "劳逸结合，避免过度劳累", "注意保暖防感冒"],
    "阳虚质": ["注意保暖，尤其是腰腹足部", "避免空调直吹", "温水泡脚暖下元"],
    "阴虚质": ["中午小憩养阴", "避免熬夜伤阴", "保持环境湿润"],
    "痰湿质": ["避免潮湿居住环境", "控制体重", "规律作息忌嗜卧少动"],
    "湿热质": ["戒烟限酒", "保持二便通畅", "居住环境干燥通风"],
    "血瘀质": ["保持气血通畅，多活动", "注意保暖避免寒凝", "调节情绪防气滞血瘀"],
    "气郁质": ["积极参加群体活动", "培养兴趣爱好", "学会倾诉和情绪疏导"],
    "特禀质": ["远离过敏源", "保持居室清洁通风", "季节交替注意防护"],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_cst() -> datetime:
    """Current time in China Standard Time."""
    return datetime.now(CST)


def _parse_json(val: Any, default: Any) -> Any:
    """Parse a JSON-encoded DB field, returning ``default`` on failure."""
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return default
    if val is None:
        return default
    return val


def _base_envelope(report_type: str, period: str) -> dict[str, Any]:
    """Common envelope fields shared by all report types."""
    return {
        "report_type": report_type,
        "generated_at": _now_cst().isoformat(),
        "data_period": period,
        "disclaimer": DISCLAIMER,
    }


# ---------------------------------------------------------------------------
# Constitution Report (体质报告)
# ---------------------------------------------------------------------------

async def _fetch_constitution_history(
    db: DbAdapter, user_id: str
) -> list[dict[str, Any]]:
    """Fetch all constitution assessments ordered oldest→newest for trend."""
    rows = await db.query(
        """SELECT id, assessed_at, results, primary_type, secondary_types
           FROM constitution_assessments
           WHERE user_id = ?
           ORDER BY assessed_at ASC""",
        (user_id,),
    )
    parsed: list[dict[str, Any]] = []
    for r in rows:
        parsed.append({
            "id": r["id"],
            "assessed_at": r["assessed_at"],
            "primary_type": r["primary_type"],
            "secondary_types": _parse_json(r.get("secondary_types"), []),
            "results": _parse_json(r.get("results"), {}),
        })
    return parsed


async def _fetch_profile_constitution(
    db: DbAdapter, user_id: str
) -> dict[str, Any]:
    """Fetch constitution info from user_profiles (fallback if no assessment)."""
    row = await db.query_one(
        "SELECT constitution_type, constitution_secondary FROM user_profiles WHERE user_id = ?",
        (user_id,),
    )
    if not row:
        return {"primary": None, "secondary": []}
    return {
        "primary": row.get("constitution_type"),
        "secondary": _parse_json(row.get("constitution_secondary"), []),
    }


async def generate_constitution_report(
    db: DbAdapter, user_id: str
) -> dict[str, Any]:
    """体质报告 — assessment results, trends, recommendations, seasonal advice.

    Aggregates from:
        - constitution_assessments (history for trends)
        - user_profiles (fallback constitution_type)
        - solar_terms (current 节气)
        - CONSTITUTION_DIET / CONSTITUTION_EXERCISE / CONSTITUTION_LIFESTYLE

    Returns a report dict with the common envelope plus ``assessment``,
    ``trend``, ``recommendations``, ``seasonal_advice`` sections.
    """
    history = await _fetch_constitution_history(db, user_id)
    latest = history[-1] if history else None
    profile_const = await _fetch_profile_constitution(db, user_id)

    # Determine effective primary type (latest assessment > profile > None)
    primary_type = (
        latest["primary_type"] if latest and latest.get("primary_type")
        else profile_const.get("primary")
    )
    secondary_types = (
        latest["secondary_types"] if latest and latest.get("secondary_types")
        else profile_const.get("secondary", [])
    )

    # --- Assessment summary ---
    assessment: dict[str, Any] = {
        "has_data": primary_type is not None,
        "primary_type": primary_type,
        "secondary_types": secondary_types or [],
        "description": CONSTITUTION_DESCRIPTIONS.get(primary_type, "") if primary_type else "",
        "latest_scores": latest["results"] if latest else {},
        "assessed_at": latest["assessed_at"] if latest else None,
    }

    # --- Score trend (map each assessment to primary_type score + all-type scores) ---
    trend_points: list[dict[str, Any]] = []
    for h in history:
        scores = h.get("results", {})
        trend_points.append({
            "assessed_at": h["assessed_at"],
            "primary_type": h["primary_type"],
            "primary_score": scores.get(h["primary_type"], 0.0) if h.get("primary_type") else 0.0,
            "all_scores": {t: scores.get(t, 0.0) for t in NINE_CONSTITUTION_TYPES},
        })

    # --- Recommendations (only if we know the constitution type) ---
    recommendations: dict[str, Any] = {
        "diet": CONSTITUTION_DIET.get(primary_type, {"宜食": [], "忌食": []}) if primary_type else {"宜食": [], "忌食": []},
        "exercise": CONSTITUTION_EXERCISE.get(primary_type, []) if primary_type else [],
        "lifestyle": CONSTITUTION_LIFESTYLE.get(primary_type, []) if primary_type else [],
        "description": CONSTITUTION_DESCRIPTIONS.get(primary_type, "") if primary_type else "",
    }

    # --- Seasonal advice (current solar term) ---
    today = _now_cst().date()
    current_term = get_solar_term(today)
    season = get_season(current_term)
    # Defer import to avoid circular dependency with seasonal_health router
    try:
        from app.routers.seasonal_health import TERM_DETAIL
        term_info = TERM_DETAIL.get(current_term, {})
        seasonal_advice = {
            "current_term": current_term,
            "season": season,
            "principle": term_info.get("principle", ""),
            "diet": term_info.get("diet", []),
            "lifestyle": term_info.get("lifestyle", []),
            "exercise": term_info.get("exercise", []),
            "recommended_herbs": term_info.get("herbs", []),
            "recommended_formulas": term_info.get("formulas", []),
        }
    except Exception:
        seasonal_advice = {
            "current_term": current_term,
            "season": season,
            "principle": "",
            "diet": [],
            "lifestyle": [],
            "exercise": [],
            "recommended_herbs": [],
            "recommended_formulas": [],
        }

    period = (
        f"首次评估{history[0]['assessed_at'][:10]}至最新评估{latest['assessed_at'][:10]}"
        if history and latest
        else "暂无评估数据"
    )

    report = _base_envelope("体质报告", period)
    report.update({
        "assessment": assessment,
        "trend": {
            "total_assessments": len(history),
            "points": trend_points,
        },
        "recommendations": recommendations,
        "seasonal_advice": seasonal_advice,
    })
    return report


# ---------------------------------------------------------------------------
# Health Trend Report (健康趋势报告)
# ---------------------------------------------------------------------------

_PERIOD_DAYS = {"7d": 7, "30d": 30, "90d": 90}


async def _compute_adherence(
    db: DbAdapter, user_id: str, days: int
) -> dict[str, Any]:
    """Medication adherence rate over the past N days (spec §20)."""
    rows = await db.query(
        """SELECT taken, date FROM medication_logs
           WHERE family_member_id = ? AND date >= date('now', ?)""",
        (user_id, f"-{days} days"),
    )
    total = len(rows)
    taken = sum(1 for r in rows if r.get("taken"))
    rate = round(taken / total * 100, 1) if total > 0 else 0.0
    return {
        "period_days": days,
        "total_logs": total,
        "taken_count": taken,
        "skipped_count": total - taken,
        "adherence_rate": rate,
    }


async def _compute_reminder_trends(
    db: DbAdapter, user_id: str, days: int
) -> dict[str, Any]:
    """Reminder completion trends over the past N days."""
    # Enabled reminders count
    enabled_rows = await db.query(
        "SELECT COUNT(*) AS cnt FROM reminders WHERE user_id = ? AND enabled = 1",
        (user_id,),
    )
    enabled_count = enabled_rows[0]["cnt"] if enabled_rows else 0

    # Total reminders (enabled + disabled)
    total_rows = await db.query(
        "SELECT COUNT(*) AS cnt FROM reminders WHERE user_id = ?",
        (user_id,),
    )
    total_count = total_rows[0]["cnt"] if total_rows else 0

    # Medication logs serve as reminder completion proxy
    log_rows = await db.query(
        """SELECT date, COUNT(*) AS day_count FROM medication_logs
           WHERE family_member_id = ? AND date >= date('now', ?)
           GROUP BY date ORDER BY date ASC""",
        (user_id, f"-{days} days"),
    )
    daily_completion = [
        {"date": r["date"], "count": r["day_count"]} for r in log_rows
    ]

    return {
        "total_reminders": total_count,
        "enabled_reminders": enabled_count,
        "disabled_reminders": total_count - enabled_count,
        "daily_completion": daily_completion,
        "active_days": len(daily_completion),
    }


async def _compute_medicine_cabinet_changes(
    db: DbAdapter, tenant_id: str, days: int
) -> dict[str, Any]:
    """Medicine cabinet changes: additions, deletions, expirations (audit_log)."""
    cutoff = f"-{days} days"
    additions = await db.query(
        """SELECT entity_id, changes, created_at FROM audit_log
           WHERE tenant_id = ? AND action = 'create' AND entity_type = 'medicine'
           AND date(created_at) >= date('now', ?)
           ORDER BY created_at DESC""",
        (tenant_id, cutoff),
    )
    deletions = await db.query(
        """SELECT entity_id, changes, created_at FROM audit_log
           WHERE tenant_id = ? AND action = 'delete' AND entity_type = 'medicine'
           AND date(created_at) >= date('now', ?)
           ORDER BY created_at DESC""",
        (tenant_id, cutoff),
    )

    # Expirations: medicines whose expiry_date has passed within the window
    expired = await db.query(
        """SELECT name, expiry_date FROM medicines
           WHERE tenant_id = ? AND expiry_date IS NOT NULL
           AND date(expiry_date) < date('now')
           AND date(expiry_date) >= date('now', ?)
           ORDER BY expiry_date ASC""",
        (tenant_id, cutoff),
    )

    # Currently expiring soon (within 30 days)
    expiring_soon = await db.query(
        """SELECT name, expiry_date, quantity FROM medicines
           WHERE tenant_id = ? AND expiry_date IS NOT NULL
           AND date(expiry_date) >= date('now')
           AND date(expiry_date) <= date('now', '+30 days')
           ORDER BY expiry_date ASC""",
        (tenant_id,),
    )

    return {
        "additions_count": len(additions),
        "deletions_count": len(deletions),
        "expired_count": len(expired),
        "expiring_soon_count": len(expiring_soon),
        "expired": [{"name": r["name"], "expiry_date": r["expiry_date"]} for r in expired],
        "expiring_soon": [{"name": r["name"], "expiry_date": r["expiry_date"], "quantity": r["quantity"]} for r in expiring_soon],
    }


async def _compute_chat_frequency(
    db: DbAdapter, user_id: str, days: int
) -> dict[str, Any]:
    """Chat interaction frequency over the past N days."""
    cutoff = f"-{days} days"
    rows = await db.query(
        """SELECT date(created_at) AS day, COUNT(*) AS cnt
           FROM conversations
           WHERE user_id = ? AND date(created_at) >= date('now', ?)
           GROUP BY date(created_at)
           ORDER BY date(created_at) ASC""",
        (user_id, cutoff),
    )
    daily = [{"date": r["day"], "count": r["cnt"]} for r in rows]
    total = sum(r["cnt"] for r in rows)
    return {
        "total_conversations": total,
        "active_days": len(daily),
        "daily_breakdown": daily,
    }


async def _compute_safety_history(
    db: DbAdapter, tenant_id: str, days: int
) -> dict[str, Any]:
    """Safety check history summary from audit_log."""
    cutoff = f"-{days} days"
    rows = await db.query(
        """SELECT action, entity_type, changes, created_at FROM audit_log
           WHERE tenant_id = ? AND action = 'safety_check'
           AND date(created_at) >= date('now', ?)
           ORDER BY created_at DESC""",
        (tenant_id, cutoff),
    )
    total = len(rows)
    # Parse changes to count warnings/critical
    warning_count = 0
    critical_count = 0
    for r in rows:
        changes = _parse_json(r.get("changes"), {})
        if isinstance(changes, dict):
            warnings = changes.get("warnings", [])
            for w in warnings:
                severity = w.get("severity", "warning") if isinstance(w, dict) else "warning"
                if severity == "critical":
                    critical_count += 1
                else:
                    warning_count += 1
    return {
        "total_checks": total,
        "warning_count": warning_count,
        "critical_count": critical_count,
    }


async def generate_health_trend_report(
    db: DbAdapter, user_id: str, tenant_id: str, period: str = "30d"
) -> dict[str, Any]:
    """健康趋势报告 — adherence, reminders, cabinet changes, chat, safety.

    Parameters:
        db: database adapter
        user_id: current user id
        tenant_id: family/tenant id for medicine filtering
        period: ``"7d"``, ``"30d"``, or ``"90d"`` (default ``"30d"``)

    Aggregates from:
        - medication_logs (adherence)
        - reminders (completion trends)
        - audit_log (cabinet changes + safety checks)
        - medicines (expirations)
        - conversations (chat frequency)
    """
    days = _PERIOD_DAYS.get(period, 30)
    period_label = f"近{days}天"

    adherence = await _compute_adherence(db, user_id, days)
    reminder_trends = await _compute_reminder_trends(db, user_id, days)
    cabinet = await _compute_medicine_cabinet_changes(db, tenant_id, days)
    chat_freq = await _compute_chat_frequency(db, user_id, days)
    safety = await _compute_safety_history(db, tenant_id, days)

    report = _base_envelope("健康趋势报告", period_label)
    report.update({
        "period": period,
        "period_days": days,
        "medication_adherence": adherence,
        "reminder_trends": reminder_trends,
        "medicine_cabinet_changes": cabinet,
        "chat_interaction": chat_freq,
        "safety_check_history": safety,
    })
    return report


# ---------------------------------------------------------------------------
# Pre-Visit Report (就诊准备报告)
# ---------------------------------------------------------------------------

# Keyword categories used to auto-generate doctor questions from chat topics
_SYMPTOM_KEYWORDS = [
    "咳嗽", "头痛", "失眠", "胃痛", "腹泻", "便秘", "乏力", "头晕",
    "胸闷", "心悸", "腰痛", "关节痛", "皮疹", "水肿", "发热", "咳嗽",
    "气短", "恶心", "呕吐", "月经",
]
_TOPIC_KEYWORDS = [
    "血压", "血糖", "血脂", "尿酸", "肝功能", "肾功能",
    "中药", "西药", "副作用", "相互作用", "剂量",
]


def _extract_chat_topics(conversations: list[dict[str, Any]]) -> list[str]:
    """Extract user questions/topics from recent chat conversations.

    Returns a list of user message contents (truncated) for the pre-visit report.
    """
    topics: list[str] = []
    for conv in conversations:
        messages = conv.get("messages", [])
        if not isinstance(messages, list):
            continue
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            if msg.get("role") == "user":
                content = str(msg.get("content", "")).strip()
                if content and len(content) > 2:
                    # Truncate long messages for readability
                    topics.append(content[:120])
    return topics


def _generate_doctor_questions(
    chat_topics: list[str], primary_type: str | None
) -> list[str]:
    """Auto-generate questions to ask the doctor based on recent chat topics.

    Scans chat topics for symptom/health keywords and produces structured
    questions. Always includes constitution-related and medication questions
    as a baseline.
    """
    questions: list[str] = []
    seen_keywords: set[str] = set()

    combined = " ".join(chat_topics)

    for kw in _SYMPTOM_KEYWORDS:
        if kw in combined and kw not in seen_keywords:
            questions.append(f"我最近有「{kw}」的症状，请问可能是什么原因？需要做什么检查？")
            seen_keywords.add(kw)

    for kw in _TOPIC_KEYWORDS:
        if kw in combined and kw not in seen_keywords:
            questions.append(f"我想了解一下我的「{kw}」情况是否正常，需要调整吗？")
            seen_keywords.add(kw)

    # Baseline questions
    if primary_type:
        questions.append(
            f"我的中医体质属于「{primary_type}」，请问日常调理有什么建议？"
        )
    questions.append("我目前服用的这些药物，有没有需要调整或停用的？")
    questions.append("根据我的健康状况，还需要做哪些检查或复查？")

    return questions


async def generate_pre_visit_report(
    db: DbAdapter, user_id: str, tenant_id: str
) -> dict[str, Any]:
    """就诊准备报告 — medications, allergies, constitution, questions.

    Aggregates from:
        - medicines (current medications)
        - user_profiles (allergies, health conditions)
        - constitution_assessments (constitution summary)
        - conversations (recent symptoms/questions)
        - audit_log (safety check results)
    """
    # --- Current medications ---
    med_rows = await db.query(
        """SELECT name, type, specification, dosage_instructions, quantity,
                  expiry_date, brand, drug_class
           FROM medicines
           WHERE tenant_id = ?
           ORDER BY name ASC""",
        (tenant_id,),
    )
    medications = [
        {
            "name": r["name"],
            "type": r["type"],
            "specification": r["specification"],
            "dosage": r["dosage_instructions"],
            "quantity": r["quantity"],
            "expiry_date": r["expiry_date"],
            "brand": r["brand"],
            "drug_class": r["drug_class"],
        }
        for r in med_rows
    ]

    # --- Profile: allergies, conditions, pregnancy ---
    profile_row = await db.query_one(
        """SELECT display_name, gender, birth_year, constitution_type,
                  constitution_secondary, allergies, health_conditions,
                  is_pregnant, blood_type, height_cm, weight_kg
           FROM user_profiles WHERE user_id = ?""",
        (user_id,),
    )
    allergies: list[str] = []
    health_conditions: list[str] = []
    profile_summary: dict[str, Any] = {}
    if profile_row:
        allergies = _parse_json(profile_row.get("allergies"), [])
        if not isinstance(allergies, list):
            allergies = [str(allergies)] if allergies else []
        health_conditions = _parse_json(profile_row.get("health_conditions"), [])
        if not isinstance(health_conditions, list):
            health_conditions = [str(health_conditions)] if health_conditions else []
        profile_summary = {
            "display_name": profile_row.get("display_name"),
            "gender": profile_row.get("gender"),
            "birth_year": profile_row.get("birth_year"),
            "height_cm": profile_row.get("height_cm"),
            "weight_kg": profile_row.get("weight_kg"),
            "blood_type": profile_row.get("blood_type"),
            "is_pregnant": bool(profile_row.get("is_pregnant", 0)),
        }

    # --- Constitution summary ---
    latest = await db.query_one(
        """SELECT primary_type, secondary_types, results, assessed_at
           FROM constitution_assessments
           WHERE user_id = ? ORDER BY assessed_at DESC LIMIT 1""",
        (user_id,),
    )
    if latest:
        constitution_summary = {
            "primary_type": latest["primary_type"],
            "secondary_types": _parse_json(latest.get("secondary_types"), []),
            "description": CONSTITUTION_DESCRIPTIONS.get(latest["primary_type"], ""),
            "assessed_at": latest["assessed_at"],
        }
        primary_for_questions = latest["primary_type"]
    else:
        constitution_summary = {
            "primary_type": profile_row.get("constitution_type") if profile_row else None,
            "secondary_types": _parse_json(profile_row.get("constitution_secondary"), []) if profile_row else [],
            "description": CONSTITUTION_DESCRIPTIONS.get(
                profile_row.get("constitution_type"), ""
            ) if profile_row and profile_row.get("constitution_type") else "",
            "assessed_at": None,
        }
        primary_for_questions = (
            profile_row.get("constitution_type") if profile_row else None
        )

    # --- Recent chat topics (last 30 days) ---
    conv_rows = await db.query(
        """SELECT id, title, messages, created_at FROM conversations
           WHERE user_id = ? AND date(created_at) >= date('now', '-30 days')
           ORDER BY created_at DESC LIMIT 20""",
        (user_id,),
    )
    conversations = []
    for r in conv_rows:
        conversations.append({
            "id": r["id"],
            "title": r["title"],
            "messages": _parse_json(r.get("messages"), []),
            "created_at": r["created_at"],
        })
    chat_topics = _extract_chat_topics(conversations)

    # --- Safety check results (last 30 days) ---
    safety_rows = await db.query(
        """SELECT changes, created_at FROM audit_log
           WHERE tenant_id = ? AND action = 'safety_check'
           AND date(created_at) >= date('now', '-30 days')
           ORDER BY created_at DESC""",
        (tenant_id,),
    )
    safety_results: list[dict[str, Any]] = []
    for r in safety_rows:
        changes = _parse_json(r.get("changes"), {})
        warnings = changes.get("warnings", []) if isinstance(changes, dict) else []
        safety_results.append({
            "created_at": r["created_at"],
            "safe": changes.get("safe", True) if isinstance(changes, dict) else True,
            "warning_count": len(warnings),
            "warnings": warnings[:5],  # top 5 warnings
        })

    # --- Auto-generated questions for the doctor ---
    doctor_questions = _generate_doctor_questions(chat_topics, primary_for_questions)

    today = _now_cst().strftime("%Y-%m-%d")
    report = _base_envelope("就诊准备报告", f"截至{today}")
    report.update({
        "patient_info": profile_summary,
        "medications": medications,
        "medication_count": len(medications),
        "allergies": allergies,
        "health_conditions": health_conditions,
        "constitution": constitution_summary,
        "recent_chat_topics": chat_topics[:10],  # top 10 recent topics
        "safety_check_results": safety_results,
        "questions_for_doctor": doctor_questions,
    })
    return report


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

async def generate_report(
    db: DbAdapter,
    user_id: str,
    tenant_id: str,
    report_type: str,
    period: str = "30d",
) -> dict[str, Any]:
    """Dispatch to the appropriate report generator.

    Args:
        report_type: ``"constitution"``, ``"health-trend"``, or ``"pre-visit"``.
    """
    if report_type == "constitution":
        return await generate_constitution_report(db, user_id)
    if report_type == "health-trend":
        return await generate_health_trend_report(db, user_id, tenant_id, period)
    if report_type == "pre-visit":
        return await generate_pre_visit_report(db, user_id, tenant_id)
    raise ValueError(f"未知的报告类型：{report_type}")
