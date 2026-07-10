"""健康分享卡 & 月度家庭健康报告 — spec §13.3 V3.

Two sharing artefacts, both read-only aggregations over existing structured
SQLite data (spec §1.4 — 结构化是权威):

* **健康分享卡 (Health Sharing Card)** — a visually appealing one-page
  summary for a single family member.  Three flavours:
    - ``summary``     : name + age + constitution + key meds + adherence + reminders
    - ``seasonal``    : current solar term + constitution + seasonal advice
    - ``constitution``: constitution type + score + personalised recommendations

* **月度家庭健康报告 (Monthly Family Health Report)** — per-member metrics
  (adherence, missed reminders, new/expired medicines, constitution, chat &
  safety counts) plus a family-level summary with alerts and recommendations.

All domain language is Chinese (spec §1.7).  Card data is structured JSON so
the frontend can render it without any backend-specific knowledge.

Data flows:
    SQLite (structured tables) → share_card (read-only) → card dict → (optional) PDF
"""

from __future__ import annotations

import logging
logger = logging.getLogger(__name__)

import json
from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.constitution_data import CONSTITUTION_DESCRIPTIONS
from app.database import DbAdapter
from app.solar_terms import get_season, get_solar_term

CST = timezone(timedelta(hours=8))

CARD_TYPES = ("summary", "seasonal", "constitution")

CARD_DISCLAIMER = "本卡仅供家庭健康参考，不构成医疗诊断或处方建议。如有不适请咨询医师。"

MONTHLY_DISCLAIMER = (
    "⚠ 本报告由家庭医生系统根据您的健康数据自动生成，仅供家庭健康管理参考，"
    "不构成医疗诊断或处方建议。如有不适请咨询您的主治医师。"
)

_ENCOURAGEMENT_QUOTES = [
    "坚持规律用药，健康每一天",
    "用心呵护家人，从关注健康开始",
    "养生贵在坚持，健康源于日常",
    "合理用药，科学养生，远离疾病",
    "家人的健康，是最好的礼物",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_cst() -> datetime:
    return datetime.now(CST)


def _parse_json(val: Any, default: Any) -> Any:
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return default
    if val is None:
        return default
    return val


def _compute_age(date_of_birth: str | None) -> int | None:
    if not date_of_birth:
        return None
    try:
        dob = datetime.strptime(date_of_birth[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None
    today = _now_cst().date()
    age = today.year - dob.year
    if (today.month, today.day) < (dob.month, dob.day):
        age -= 1
    return age if age >= 0 else None


def _adherence_color(rate: float) -> str:
    if rate >= 80:
        return "green"
    if rate >= 60:
        return "orange"
    return "red"


def _pick_quote() -> str:
    today = _now_cst().date()
    return _ENCOURAGEMENT_QUOTES[today.toordinal() % len(_ENCOURAGEMENT_QUOTES)]


async def _resolve_member(
    db: DbAdapter, member_id: str | None, user_id: str
) -> dict[str, Any]:
    """Resolve display info for the card subject.

    Priority: ``member_id`` (family_members row) → user_profiles → minimal fallback.
    Returns ``{name, age, gender, data_key}`` where ``data_key`` is the id used
    to query medication_logs / reminders (falls back to ``user_id``).
    """
    if member_id:
        row = await db.query_one(
            "SELECT id, name, relation, gender, date_of_birth, "
            "constitution_type, constitution_sub "
            "FROM family_members WHERE id = ? AND user_id = ?",
            (member_id, user_id),
        )
        if row:
            return {
                "name": row.get("name") or "家庭成员",
                "age": _compute_age(row.get("date_of_birth")),
                "gender": row.get("gender"),
                "relation": row.get("relation"),
                "constitution_type": row.get("constitution_type"),
                "constitution_sub": _parse_json(row.get("constitution_sub"), []),
                "data_key": member_id,
                "member_id": member_id,
            }

    profile = await db.query_one(
        "SELECT display_name, gender, birth_year, constitution_type, "
        "constitution_secondary FROM user_profiles WHERE user_id = ?",
        (user_id,),
    )
    if profile:
        name = profile.get("display_name") or "我"
        age = None
        if profile.get("birth_year"):
            try:
                age = _now_cst().year - int(profile["birth_year"])
            except (ValueError, TypeError):
                pass
        return {
            "name": name,
            "age": age,
            "gender": profile.get("gender"),
            "relation": None,
            "constitution_type": profile.get("constitution_type"),
            "constitution_sub": _parse_json(profile.get("constitution_secondary"), []),
            "data_key": user_id,
            "member_id": None,
        }

    return {
        "name": "家庭成员",
        "age": None,
        "gender": None,
        "relation": None,
        "constitution_type": None,
        "constitution_sub": [],
        "data_key": user_id,
        "member_id": None,
    }


async def _latest_constitution(
    db: DbAdapter, user_id: str
) -> dict[str, Any] | None:
    row = await db.query_one(
        "SELECT primary_type, secondary_types, results, assessed_at "
        "FROM constitution_assessments WHERE user_id = ? "
        "ORDER BY assessed_at DESC LIMIT 1",
        (user_id,),
    )
    if not row:
        return None
    return {
        "primary_type": row["primary_type"],
        "secondary_types": _parse_json(row.get("secondary_types"), []),
        "results": _parse_json(row.get("results"), {}),
        "assessed_at": row["assessed_at"],
    }


async def _adherence_rate(
    db: DbAdapter, data_key: str, *, days: int = 30
) -> dict[str, Any]:
    rows = await db.query(
        "SELECT taken FROM medication_logs "
        "WHERE family_member_id = ? AND date >= date('now', ?)",
        (data_key, f"-{days} days"),
    )
    total = len(rows)
    taken = sum(1 for r in rows if r.get("taken"))
    rate = round(taken / total * 100, 1) if total > 0 else 0.0
    return {
        "total": total,
        "taken": taken,
        "missed": total - taken,
        "rate": rate,
        "days": days,
    }


async def _today_reminder_stats(
    db: DbAdapter, data_key: str, user_id: str
) -> dict[str, Any]:
    enabled = await db.query(
        "SELECT id, times FROM reminders "
        "WHERE user_id = ? AND (family_member_id = ? OR family_member_id IS NULL) "
        "AND enabled = 1",
        (user_id, data_key),
    )
    total_slots = 0
    for r in enabled:
        times = _parse_json(r.get("times"), [])
        if isinstance(times, list):
            total_slots += len(times)
        elif isinstance(times, str) and times:
            total_slots += 1

    today = _now_cst().strftime("%Y-%m-%d")
    done_rows = await db.query(
        "SELECT COUNT(*) AS cnt FROM medication_logs "
        "WHERE family_member_id = ? AND date = ? AND taken = 1",
        (data_key, today),
    )
    done = done_rows[0]["cnt"] if done_rows else 0
    return {"total": total_slots, "done": done}


async def _key_medicines(
    db: DbAdapter, tenant_id: str, member_id: str | None
) -> list[dict[str, Any]]:
    if member_id:
        rows = await db.query(
            "SELECT name, type, drug_class, quantity, expiry_date "
            "FROM medicines WHERE tenant_id = ? AND family_member_id = ? "
            "ORDER BY name ASC LIMIT 5",
            (tenant_id, member_id),
        )
    else:
        rows = await db.query(
            "SELECT name, type, drug_class, quantity, expiry_date "
            "FROM medicines WHERE tenant_id = ? "
            "ORDER BY name ASC LIMIT 5",
            (tenant_id,),
        )
    return [
        {
            "name": r["name"],
            "type": r["type"],
            "drug_class": r.get("drug_class"),
            "quantity": r.get("quantity"),
            "expiry_date": r.get("expiry_date"),
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Card generators
# ---------------------------------------------------------------------------

async def generate_summary_card(
    db: DbAdapter,
    member_id: str | None,
    user_id: str,
    tenant_id: str,
) -> dict[str, Any]:
    member = await _resolve_member(db, member_id, user_id)
    data_key = member["data_key"]
    const = await _latest_constitution(db, user_id)
    primary_type = (
        const["primary_type"] if const and const.get("primary_type")
        else member.get("constitution_type")
    )
    adherence = await _adherence_rate(db, data_key, days=30)
    reminders = await _today_reminder_stats(db, data_key, user_id)
    meds = await _key_medicines(db, tenant_id, member.get("member_id"))

    sections: list[dict[str, Any]] = []
    if member.get("age") is not None:
        sections.append({"label": "年龄", "value": f"{member['age']}岁", "icon": "user"})
    if primary_type:
        sections.append({
            "label": "体质",
            "value": primary_type,
            "icon": "heart",
            "advice": CONSTITUTION_DESCRIPTIONS.get(primary_type, "")[:40],
        })
    sections.append({
        "label": "用药依从性",
        "value": f"{adherence['rate']:.0f}%",
        "color": _adherence_color(adherence["rate"]),
        "detail": f"近30天 {adherence['taken']}/{adherence['total']} 次",
    })
    sections.append({
        "label": "今日提醒",
        "value": f"{reminders['done']}/{reminders['total']} 已完成",
        "color": "blue" if reminders["done"] < reminders["total"] else "green",
    })
    if meds:
        sections.append({
            "label": "常用药",
            "value": "、".join(m["name"] for m in meds[:3]),
            "icon": "medicine",
        })
    today = _now_cst()
    current_term = get_solar_term(today.date())
    sections.append({
        "label": "当前节气",
        "value": current_term,
        "advice": _term_brief_advice(current_term),
    })

    return {
        "card_type": "summary",
        "member_name": member["name"],
        "generated_at": today.strftime("%Y-%m-%d"),
        "sections": sections,
        "quote": _pick_quote(),
        "disclaimer": CARD_DISCLAIMER,
    }


def _term_brief_advice(term: str) -> str:
    try:
        from app.routers.seasonal_health import TERM_DETAIL

        info = TERM_DETAIL.get(term, {})
        diet = info.get("diet", [])
        if diet and isinstance(diet, list):
            return str(diet[0])
    except Exception as exc:
        logger.warning("diet lookup failed: %s", exc)
    season = get_season(term)
    return f"{season}季养生，注意起居调摄"


async def generate_seasonal_card(
    db: DbAdapter,
    member_id: str | None,
    user_id: str,
    tenant_id: str,
) -> dict[str, Any]:
    member = await _resolve_member(db, member_id, user_id)
    const = await _latest_constitution(db, user_id)
    primary_type = (
        const["primary_type"] if const and const.get("primary_type")
        else member.get("constitution_type")
    )
    today = _now_cst()
    current_term = get_solar_term(today.date())
    season = get_season(current_term)

    term_info: dict[str, Any] = {}
    try:
        from app.routers.seasonal_health import TERM_DETAIL

        term_info = TERM_DETAIL.get(current_term, {})
    except Exception as exc:
        logger.warning("seasonal term detail lookup failed: %s", exc)

    from app.report_engine import (
        CONSTITUTION_DIET,
        CONSTITUTION_EXERCISE,
    )

    const_diet = CONSTITUTION_DIET.get(primary_type, {"宜食": [], "忌食": []}) if primary_type else {"宜食": [], "忌食": []}
    const_exercise = CONSTITUTION_EXERCISE.get(primary_type, []) if primary_type else []

    sections: list[dict[str, Any]] = [
        {"label": "当前节气", "value": current_term, "icon": "calendar"},
        {"label": "时令", "value": f"{season}季", "icon": "leaf"},
    ]
    if primary_type:
        sections.append({"label": "体质", "value": primary_type, "icon": "heart"})

    principle = term_info.get("principle", "")
    if principle:
        sections.append({"label": "养生原则", "value": principle, "icon": "book"})

    term_diet = term_info.get("diet", [])
    if term_diet:
        sections.append({
            "label": "时令饮食",
            "value": "；".join(str(d) for d in term_diet[:2]),
            "icon": "coffee",
        })
    elif const_diet.get("宜食"):
        sections.append({
            "label": "宜食",
            "value": "；".join(const_diet["宜食"][:2]),
            "icon": "coffee",
        })

    term_exercise = term_info.get("exercise", [])
    if term_exercise:
        sections.append({
            "label": "推荐运动",
            "value": "；".join(str(e) for e in term_exercise[:2]),
            "icon": "thunderbolt",
        })
    elif const_exercise:
        sections.append({
            "label": "推荐运动",
            "value": const_exercise[0],
            "icon": "thunderbolt",
        })

    return {
        "card_type": "seasonal",
        "member_name": member["name"],
        "generated_at": today.strftime("%Y-%m-%d"),
        "sections": sections,
        "quote": _pick_quote(),
        "disclaimer": CARD_DISCLAIMER,
    }


async def generate_constitution_card(
    db: DbAdapter,
    member_id: str | None,
    user_id: str,
    tenant_id: str,
) -> dict[str, Any]:
    member = await _resolve_member(db, member_id, user_id)
    const = await _latest_constitution(db, user_id)
    primary_type = (
        const["primary_type"] if const and const.get("primary_type")
        else member.get("constitution_type")
    )
    today = _now_cst()

    from app.report_engine import (
        CONSTITUTION_DIET,
        CONSTITUTION_EXERCISE,
        CONSTITUTION_LIFESTYLE,
    )

    sections: list[dict[str, Any]] = []
    if primary_type:
        sections.append({
            "label": "主体质",
            "value": primary_type,
            "icon": "heart",
        })
        description = CONSTITUTION_DESCRIPTIONS.get(primary_type, "")
        if description:
            sections.append({"label": "体质特征", "value": description, "icon": "profile"})

        if const and const.get("results"):
            score = const["results"].get(primary_type)
            if score is not None:
                sections.append({
                    "label": "体质得分",
                    "value": f"{score:.0f}分",
                    "color": "green" if score < 40 else ("orange" if score < 70 else "red"),
                })

        secondary = (
            const.get("secondary_types") if const
            else member.get("constitution_sub", [])
        )
        if secondary:
            sections.append({
                "label": "兼夹体质",
                "value": "、".join(secondary),
                "icon": "fork",
            })

        diet = CONSTITUTION_DIET.get(primary_type, {"宜食": [], "忌食": []})
        if diet.get("宜食"):
            sections.append({
                "label": "饮食宜",
                "value": "；".join(diet["宜食"][:2]),
                "icon": "coffee",
            })
        if diet.get("忌食"):
            sections.append({
                "label": "饮食忌",
                "value": "；".join(diet["忌食"][:2]),
                "icon": "stop",
                "color": "red",
            })
        exercise = CONSTITUTION_EXERCISE.get(primary_type, [])
        if exercise:
            sections.append({
                "label": "运动建议",
                "value": exercise[0],
                "icon": "thunderbolt",
            })
        lifestyle = CONSTITUTION_LIFESTYLE.get(primary_type, [])
        if lifestyle:
            sections.append({
                "label": "起居调摄",
                "value": lifestyle[0],
                "icon": "home",
            })
    else:
        sections.append({
            "label": "体质",
            "value": "尚未评估",
            "advice": "请先完成体质自测问卷",
            "color": "orange",
        })

    return {
        "card_type": "constitution",
        "member_name": member["name"],
        "generated_at": today.strftime("%Y-%m-%d"),
        "sections": sections,
        "quote": _pick_quote(),
        "disclaimer": CARD_DISCLAIMER,
    }


async def generate_share_card(
    db: DbAdapter,
    member_id: str | None,
    user_id: str,
    tenant_id: str,
    card_type: str,
) -> dict[str, Any]:
    if card_type == "summary":
        return await generate_summary_card(db, member_id, user_id, tenant_id)
    if card_type == "seasonal":
        return await generate_seasonal_card(db, member_id, user_id, tenant_id)
    if card_type == "constitution":
        return await generate_constitution_card(db, member_id, user_id, tenant_id)
    raise ValueError(f"未知的卡片类型：{card_type}")


# ---------------------------------------------------------------------------
# Monthly Family Health Report (月度家庭健康报告)
# ---------------------------------------------------------------------------

def _month_range(month: str) -> tuple[str, str]:
    """Return (start_date, end_date) ISO strings for a YYYY-MM month string.

    If the month is the current month, the end is today (partial month).
    """
    try:
        y, m = month.split("-")
        year, mon = int(y), int(m)
    except (ValueError, AttributeError):
        today = _now_cst().date()
        year, mon = today.year, today.month
        month = f"{year:04d}-{mon:02d}"
    start = date(year, mon, 1)
    if mon == 12:
        next_start = date(year + 1, 1, 1)
    else:
        next_start = date(year, mon + 1, 1)
    today = _now_cst().date()
    end = min(next_start - timedelta(days=1), today)
    if end < start:
        end = start
    return start.isoformat(), end.isoformat()


async def _member_monthly_metrics(
    db: DbAdapter,
    member: dict[str, Any],
    user_id: str,
    tenant_id: str,
    start: str,
    end: str,
) -> dict[str, Any]:
    data_key = member.get("data_key") or user_id
    member_id = member.get("member_id")

    # Medication adherence in the month
    logs = await db.query(
        "SELECT taken FROM medication_logs "
        "WHERE family_member_id = ? AND date >= ? AND date <= ?",
        (data_key, start, end),
    )
    total = len(logs)
    taken = sum(1 for r in logs if r.get("taken"))
    rate = round(taken / total * 100, 1) if total > 0 else 0.0
    missed = total - taken

    # New medicines added this month (audit_log create events)
    if member_id:
        new_meds_rows = await db.query(
            "SELECT COUNT(*) AS cnt FROM audit_log "
            "WHERE tenant_id = ? AND action = 'create' AND entity_type = 'medicine' "
            "AND date(created_at) >= ? AND date(created_at) <= ? "
            "AND changes LIKE ?",
            (tenant_id, start, end, f'%"{member_id}"%'),
        )
    else:
        new_meds_rows = await db.query(
            "SELECT COUNT(*) AS cnt FROM audit_log "
            "WHERE tenant_id = ? AND action = 'create' AND entity_type = 'medicine' "
            "AND date(created_at) >= ? AND date(created_at) <= ?",
            (tenant_id, start, end),
        )
    new_meds = new_meds_rows[0]["cnt"] if new_meds_rows else 0

    # Expired / expiring medicines
    if member_id:
        expired_rows = await db.query(
            "SELECT name, expiry_date FROM medicines "
            "WHERE tenant_id = ? AND family_member_id = ? "
            "AND expiry_date IS NOT NULL AND date(expiry_date) < date('now')",
            (tenant_id, member_id),
        )
        expiring_rows = await db.query(
            "SELECT name, expiry_date FROM medicines "
            "WHERE tenant_id = ? AND family_member_id = ? "
            "AND expiry_date IS NOT NULL "
            "AND date(expiry_date) >= date('now') "
            "AND date(expiry_date) <= date('now', '+30 days')",
            (tenant_id, member_id),
        )
    else:
        expired_rows = await db.query(
            "SELECT name, expiry_date FROM medicines "
            "WHERE tenant_id = ? "
            "AND expiry_date IS NOT NULL AND date(expiry_date) < date('now')",
            (tenant_id,),
        )
        expiring_rows = await db.query(
            "SELECT name, expiry_date FROM medicines "
            "WHERE tenant_id = ? "
            "AND expiry_date IS NOT NULL "
            "AND date(expiry_date) >= date('now') "
            "AND date(expiry_date) <= date('now', '+30 days')",
            (tenant_id,),
        )

    # Constitution summary
    const = await _latest_constitution(db, user_id)
    primary_type = (
        const["primary_type"] if const and const.get("primary_type")
        else member.get("constitution_type")
    )

    # Chat interaction count (member-level falls back to user-level)
    chat_rows = await db.query(
        "SELECT COUNT(*) AS cnt FROM conversations "
        "WHERE user_id = ? AND date(created_at) >= ? AND date(created_at) <= ?",
        (user_id, start, end),
    )
    chat_count = chat_rows[0]["cnt"] if chat_rows else 0

    # Safety check count (tenant-level; member-level not tracked)
    safety_rows = await db.query(
        "SELECT COUNT(*) AS cnt FROM audit_log "
        "WHERE tenant_id = ? AND action = 'safety_check' "
        "AND date(created_at) >= ? AND date(created_at) <= ?",
        (tenant_id, start, end),
    )
    safety_count = safety_rows[0]["cnt"] if safety_rows else 0

    return {
        "member_id": member_id,
        "member_name": member.get("name"),
        "relation": member.get("relation"),
        "constitution_type": primary_type,
        "medication_adherence": {
            "rate": rate,
            "taken": taken,
            "total": total,
            "missed": missed,
        },
        "missed_reminders": missed,
        "new_medicines": new_meds,
        "expired_medicines": [
            {"name": r["name"], "expiry_date": r["expiry_date"]} for r in expired_rows
        ],
        "expiring_medicines": [
            {"name": r["name"], "expiry_date": r["expiry_date"]} for r in expiring_rows
        ],
        "chat_interaction_count": chat_count,
        "safety_check_count": safety_count,
    }


async def generate_monthly_report(
    db: DbAdapter,
    member_ids: list[str] | None,
    user_id: str,
    tenant_id: str,
    month: str | None = None,
) -> dict[str, Any]:
    today = _now_cst()
    if not month:
        month = today.strftime("%Y-%m")
    start, end = _month_range(month)

    # Resolve members
    if member_ids:
        members: list[dict[str, Any]] = []
        for mid in member_ids:
            m = await _resolve_member(db, mid, user_id)
            members.append(m)
    else:
        rows = await db.query(
            "SELECT id, name, relation, gender, date_of_birth, "
            "constitution_type, constitution_sub "
            "FROM family_members WHERE user_id = ? ORDER BY created_at ASC",
            (user_id,),
        )
        if rows:
            members = [
                {
                    "name": r.get("name") or "家庭成员",
                    "age": _compute_age(r.get("date_of_birth")),
                    "gender": r.get("gender"),
                    "relation": r.get("relation"),
                    "constitution_type": r.get("constitution_type"),
                    "constitution_sub": _parse_json(r.get("constitution_sub"), []),
                    "data_key": r["id"],
                    "member_id": r["id"],
                }
                for r in rows
            ]
        else:
            members = [await _resolve_member(db, None, user_id)]

    per_member = [
        await _member_monthly_metrics(db, m, user_id, tenant_id, start, end)
        for m in members
    ]

    # Family-level aggregate
    total_logs = sum(m["medication_adherence"]["total"] for m in per_member)
    total_taken = sum(m["medication_adherence"]["taken"] for m in per_member)
    family_rate = (
        round(total_taken / total_logs * 100, 1) if total_logs > 0 else 0.0
    )

    alerts: list[dict[str, Any]] = []
    for m in per_member:
        for exp in m["expired_medicines"]:
            alerts.append({
                "severity": "critical",
                "type": "药品过期",
                "member": m["member_name"],
                "detail": f"{exp['name']} 已过期（{exp['expiry_date']}）",
            })
        if m["missed_reminders"] > 3:
            alerts.append({
                "severity": "warning",
                "type": "漏服较多",
                "member": m["member_name"],
                "detail": f"本月漏服 {m['missed_reminders']} 次用药",
            })

    recommendations: list[str] = []
    if family_rate < 60:
        recommendations.append("家庭整体用药依从性偏低，建议设置更多提醒并督促按时服药。")
    if any(a["severity"] == "critical" for a in alerts):
        recommendations.append("存在过期药品，请及时清理药箱并补充新药。")
    if not recommendations:
        recommendations.append("家庭成员健康状况良好，请继续保持规律作息和合理用药。")
    recommendations.append("建议定期进行体质复测，及时调整养生方案。")

    return {
        "report_type": "月度家庭健康报告",
        "month": month,
        "data_period": f"{start} 至 {end}",
        "generated_at": today.isoformat(),
        "disclaimer": MONTHLY_DISCLAIMER,
        "family_summary": {
            "member_count": len(per_member),
            "total_adherence_rate": family_rate,
            "total_taken": total_taken,
            "total_logs": total_logs,
            "total_missed": total_logs - total_taken,
            "alert_count": len(alerts),
        },
        "health_alerts": alerts,
        "recommendations": recommendations,
        "members": per_member,
    }
