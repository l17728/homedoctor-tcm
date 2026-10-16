"""PDF generation utility for prescription sheets and health reports (spec §21).

Uses reportlab with the built-in CJK CID font ``STSong-Light`` (Adobe-GB1
character collection) so **no external TTF/OTF font files are required**.
The CMap data is bundled inside the reportlab package; modern PDF viewers
(Adobe Reader, Foxit, Chrome, Edge, macOS Preview) render the glyphs
correctly via their CJK font fallback.

Public API::

    from app.pdf_generator import generate_prescription_pdf, generate_health_report_pdf

Both functions accept plain ``dict`` data and return ``bytes`` — a complete
PDF document ready to be sent as an ``application/pdf`` response body.
"""

from __future__ import annotations


import logging

logger = logging.getLogger(__name__)
import io
import json
from datetime import datetime, timezone, timedelta
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
    Paragraph,
    HRFlowable,
)

# ---------------------------------------------------------------------------
# Font registration — STSong-Light is a standard Adobe CJK CID font.
# reportlab bundles the CMap; viewers provide the glyph outlines.
# ---------------------------------------------------------------------------

_FONT_REGISTERED = False


def _ensure_font() -> str:
    """Register the CJK CID font once and return its registered name."""
    global _FONT_REGISTERED
    if not _FONT_REGISTERED:
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        _FONT_REGISTERED = True
    return "STSong-Light"


# CST = UTC+8 (China Standard Time)
_CST = timezone(timedelta(hours=8))

# Color palette — calm, professional medical tones
_PRIMARY = colors.HexColor("#2c5f7c")   # deep teal-blue
_ACCENT = colors.HexColor("#e8b441")    # warm gold
_LIGHT_BG = colors.HexColor("#f0f5f9")  # very light blue-grey
_BORDER = colors.HexColor("#c5d3de")    # soft border
_TEXT_DARK = colors.HexColor("#1a1a2e")
_TEXT_MUTED = colors.HexColor("#6b7280")
_WARN_BG = colors.HexColor("#fef3cd")   # light amber for disclaimer


# ---------------------------------------------------------------------------
# Paragraph styles
# ---------------------------------------------------------------------------

def _build_styles(font: str) -> dict[str, ParagraphStyle]:
    """Build all paragraph styles using the registered CJK font."""
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "PrescTitle", parent=base["Title"],
            fontName=font, fontSize=22, leading=28,
            alignment=1,  # center
            textColor=_PRIMARY, spaceAfter=4,
        ),
        "subtitle": ParagraphStyle(
            "PrescSubtitle", parent=base["Normal"],
            fontName=font, fontSize=11, leading=15,
            alignment=1, textColor=_TEXT_MUTED, spaceAfter=2,
        ),
        "section": ParagraphStyle(
            "Section", parent=base["Heading2"],
            fontName=font, fontSize=13, leading=18,
            textColor=_PRIMARY, spaceBefore=10, spaceAfter=6,
            borderPadding=(0, 0, 2, 6),
            leftIndent=6,
        ),
        "body": ParagraphStyle(
            "Body", parent=base["Normal"],
            fontName=font, fontSize=10.5, leading=16,
            textColor=_TEXT_DARK, spaceAfter=4,
        ),
        "body_small": ParagraphStyle(
            "BodySmall", parent=base["Normal"],
            fontName=font, fontSize=9, leading=13,
            textColor=_TEXT_MUTED,
        ),
        "disclaimer": ParagraphStyle(
            "Disclaimer", parent=base["Normal"],
            fontName=font, fontSize=9.5, leading=14,
            textColor=colors.HexColor("#856404"),  # dark amber
            backColor=_WARN_BG, borderPadding=8,
            borderRadius=4, spaceBefore=8,
        ),
        "footer": ParagraphStyle(
            "Footer", parent=base["Normal"],
            fontName=font, fontSize=8.5, leading=12,
            textColor=_TEXT_MUTED, alignment=1,
        ),
        "signature": ParagraphStyle(
            "Signature", parent=base["Normal"],
            fontName=font, fontSize=10.5, leading=16,
            textColor=_TEXT_DARK, alignment=2,  # right
        ),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_text(val: Any, default: str = "—") -> str:
    """Return a display-safe string, falling back to ``default``."""
    if val is None:
        return default
    s = str(val).strip()
    return s if s else default


def _parse_json_field(val: Any, default: Any) -> Any:
    """Parse a JSON-encoded DB field, returning ``default`` on failure."""
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return default
    if val is None:
        return default
    return val


def _format_date(dt: datetime | None = None) -> str:
    """Format a datetime as ``YYYY年MM月DD日`` in CST."""
    if dt is None:
        dt = datetime.now(_CST)
    return f"{dt.year}年{dt.month:02d}月{dt.day:02d}日"


def _hr(color: colors.Color = _BORDER, thickness: float = 0.8) -> HRFlowable:
    """Horizontal rule flowable spanning full content width."""
    return HRFlowable(
        width="100%", thickness=thickness, color=color,
        spaceBefore=4, spaceAfter=4,
    )


def _info_row(label: str, value: str, styles: dict[str, ParagraphStyle]) -> Table:
    """A two-column label/value table row used in patient info blocks."""
    label_style = ParagraphStyle(
        "InfoLabel", parent=styles["body"],
        textColor=_PRIMARY, fontSize=10.5,
    )
    return Table(
        [[Paragraph(label, label_style), Paragraph(value, styles["body"])]],
        colWidths=[80 * mm, 90 * mm],
        style=TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 1),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ]),
    )


# ---------------------------------------------------------------------------
# Prescription PDF (处方单)
# ---------------------------------------------------------------------------

def generate_prescription_pdf(
    *,
    formula: dict[str, Any],
    patient_name: str = "—",
    patient_age: str | None = None,
    patient_gender: str | None = None,
    patient_contact: str | None = None,
    constitution: str | None = None,
    stock_items: list[dict[str, Any]] | None = None,
    prescriber: str | None = None,
    notes: str | None = None,
    usage_instructions: str | None = None,
) -> bytes:
    """Generate a prescription sheet PDF for a TCM formula.

    Parameters mirror spec §21.3 layout:

    * **formula** — parsed formula dict (must contain ``name``, ideally
      ``composition``, ``efficacy``, ``indications``, ``source``).
    * **patient_name / patient_age / patient_gender** — patient block.
    * **prescriber** — name shown on the signature line.
    * **notes** — free-text 医嘱 / 注意事项.
    * **usage_instructions** — how to prepare / take (用法用量).

    Returns the full PDF as ``bytes``.
    """
    font = _ensure_font()
    styles = _build_styles(font)
    buf = io.BytesIO()

    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
        title=f"处方单 - {_safe_text(formula.get('name'))}",
    )

    story: list[Any] = []

    # --- Header ---
    story.append(Paragraph("处 方 笺", styles["title"]))
    story.append(Paragraph("家庭医生 · 您的养生助手", styles["subtitle"]))
    story.append(Spacer(1, 4))
    story.append(_hr(_PRIMARY, 1.5))
    story.append(Spacer(1, 6))

    # --- Patient info ---
    patient_line = f"姓名：{_safe_text(patient_name)}"
    if patient_gender:
        patient_line += f"    性别：{_safe_text(patient_gender)}"
    if patient_age:
        patient_line += f"    年龄：{_safe_text(patient_age)}岁"
    if patient_contact:
        patient_line += f"    联系方式：{_safe_text(patient_contact)}"
    patient_line += f"    日期：{_format_date()}"
    story.append(Paragraph(patient_line, styles["body"]))
    if constitution:
        story.append(Paragraph(f"体质：{_safe_text(constitution)}", styles["body"]))
    story.append(Spacer(1, 4))

    # --- Formula section ---
    story.append(Paragraph("▎ 方剂信息", styles["section"]))
    formula_name = _safe_text(formula.get("name"))
    source = _safe_text(formula.get("source"))
    category = _safe_text(formula.get("category"))
    story.append(_info_row("方名", formula_name, styles))
    if source != "—":
        story.append(_info_row("出处", source, styles))
    if category != "—":
        story.append(_info_row("分类", category, styles))

    efficacy = _safe_text(formula.get("efficacy"))
    if efficacy != "—":
        story.append(_info_row("功效", efficacy, styles))

    indications = _safe_text(formula.get("indications"))
    if indications != "—":
        story.append(_info_row("主治", indications, styles))

    story.append(Spacer(1, 4))

    # --- Herb table (君臣佐使 + dosage) ---
    composition = _parse_json_field(formula.get("composition"), [])
    if isinstance(composition, list) and composition:
        story.append(Paragraph("▎ 组方明细", styles["section"]))

        header = [
            Paragraph("<b>药材</b>", styles["body_small"]),
            Paragraph("<b>角色</b>", styles["body_small"]),
            Paragraph("<b>用量</b>", styles["body_small"]),
        ]
        rows = [header]
        for item in composition:
            if isinstance(item, dict):
                name = _safe_text(item.get("name"))
                role = _safe_text(item.get("role"))
                dose = _safe_text(item.get("dose"))
            elif isinstance(item, str):
                name, role, dose = item.strip(), "—", "—"
            else:
                continue
            rows.append([
                Paragraph(name, styles["body"]),
                Paragraph(role, styles["body"]),
                Paragraph(dose, styles["body"]),
            ])

        herb_table = Table(
            rows, colWidths=[60 * mm, 50 * mm, 60 * mm],
            repeatRows=1,
            style=TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), _PRIMARY),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), font),
                ("FONTSIZE", (0, 0), (-1, 0), 9),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (1, 0), (-1, -1), "CENTER"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _LIGHT_BG]),
                ("GRID", (0, 0), (-1, -1), 0.5, _BORDER),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]),
        )
        story.append(herb_table)
        story.append(Spacer(1, 6))

    # --- Usage instructions ---
    usage = usage_instructions or _safe_text(
        _parse_json_field(formula.get("properties"), {}).get("用法")
    )
    if usage and usage != "—":
        story.append(Paragraph("▎ 用法用量", styles["section"]))
        story.append(Paragraph(usage, styles["body"]))
        story.append(Spacer(1, 4))

    # --- Notes / 医嘱 ---
    if notes:
        story.append(Paragraph("▎ 医嘱 / 注意事项", styles["section"]))
        story.append(Paragraph(notes, styles["body"]))
        story.append(Spacer(1, 4))

    if stock_items:
        story.append(Paragraph("▎ 相关药品库存", styles["section"]))
        for item in stock_items:
            name = _safe_text(item.get("name"))
            quantity = _safe_text(item.get("quantity"))
            unit = _safe_text(item.get("unit"))
            story.append(Paragraph(f"{name}：{quantity}{unit}", styles["body"]))
        story.append(Spacer(1, 4))

    # --- Disclaimer ---
    story.append(Spacer(1, 8))
    story.append(_hr(_BORDER, 0.5))
    story.append(Paragraph(
        "⚠ 本处方单为养生调理参考，不构成医疗诊断或处方。"
        "如需用药，请咨询您的主治医师或执业中药师。",
        styles["disclaimer"],
    ))

    # --- Signature line ---
    story.append(Spacer(1, 16))
    prescriber_text = f"开方人：{_safe_text(prescriber, '_______________')}"
    story.append(Paragraph(prescriber_text, styles["signature"]))

    # --- Footer ---
    story.append(Spacer(1, 10))
    story.append(_hr(_BORDER, 0.3))
    story.append(Paragraph(
        f"打印于 {_format_date()}　·　家庭医生 v2.0",
        styles["footer"],
    ))

    doc.build(story)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Health report PDF (健康摘要单)
# ---------------------------------------------------------------------------

def generate_health_report_pdf(
    *,
    member: dict[str, Any] | None = None,
    profile: dict[str, Any] | None = None,
    constitution: dict[str, Any] | None = None,
    medicines: list[dict[str, Any]] | None = None,
    reminders: list[dict[str, Any]] | None = None,
    report_type: str = "summary",
) -> bytes:
    """Generate a health summary PDF (体质 + 用药 + 提醒).

    Parameters mirror spec §21.2 "健康摘要单" template:

    * **member** — family_members row (name, gender, date_of_birth …).
    * **profile** — user_profiles row (constitution_type, allergies …).
    * **constitution** — latest constitution_assessments row.
    * **medicines** — list of medicines rows.
    * **reminders** — list of reminders rows.
    * **report_type** — ``"summary"`` (default) or custom label.

    Returns the full PDF as ``bytes``.
    """
    font = _ensure_font()
    styles = _build_styles(font)
    buf = io.BytesIO()

    member = member or {}
    profile = profile or {}
    constitution = constitution or {}
    medicines = medicines or []
    reminders = reminders or []

    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
        title="健康摘要单",
    )

    story: list[Any] = []

    # --- Header ---
    story.append(Paragraph("健 康 摘 要 单", styles["title"]))
    story.append(Paragraph("家庭医生 · 您的养生助手", styles["subtitle"]))
    story.append(Spacer(1, 4))
    story.append(_hr(_PRIMARY, 1.5))
    story.append(Spacer(1, 6))

    # --- Patient info ---
    name = _safe_text(member.get("name") or profile.get("display_name"))
    gender = _safe_text(member.get("gender") or profile.get("gender"))
    dob = _safe_text(member.get("date_of_birth") or profile.get("birth_year"), "")
    patient_line = f"姓名：{name}"
    if gender != "—":
        patient_line += f"    性别：{gender}"
    if dob and dob != "—":
        patient_line += f"    出生：{dob}"
    patient_line += f"    日期：{_format_date()}"
    story.append(Paragraph(patient_line, styles["body"]))
    story.append(Spacer(1, 4))

    # --- Constitution section ---
    const_type = (
        constitution.get("primary_type")
        or profile.get("constitution_type")
    )
    const_secondary = _parse_json_field(
        profile.get("constitution_secondary")
        or constitution.get("secondary_types"), []
    )
    story.append(Paragraph("▎ 体质信息", styles["section"]))
    if const_type:
        story.append(_info_row("主体质", _safe_text(const_type), styles))
    if isinstance(const_secondary, list) and const_secondary:
        story.append(_info_row("兼夹体质", "、".join(str(s) for s in const_secondary), styles))
    if not const_type and not const_secondary:
        story.append(Paragraph("暂无体质评估记录。", styles["body_small"]))
    story.append(Spacer(1, 4))

    # --- Allergies & health conditions ---
    allergies = _parse_json_field(profile.get("allergies"), [])
    conditions = _parse_json_field(profile.get("health_conditions"), [])
    if allergies or conditions:
        story.append(Paragraph("▎ 健康档案", styles["section"]))
        if isinstance(allergies, list) and allergies:
            story.append(_info_row("过敏史", "、".join(str(a) for a in allergies), styles))
        if isinstance(conditions, list) and conditions:
            story.append(_info_row("健康问题", "、".join(str(c) for c in conditions), styles))
        story.append(Spacer(1, 4))

    # --- Medicines table ---
    if medicines:
        story.append(Paragraph("▎ 当前用药", styles["section"]))
        header = [
            Paragraph("<b>药品名称</b>", styles["body_small"]),
            Paragraph("<b>类型</b>", styles["body_small"]),
            Paragraph("<b>规格</b>", styles["body_small"]),
            Paragraph("<b>数量</b>", styles["body_small"]),
        ]
        rows = [header]
        for med in medicines:
            rows.append([
                Paragraph(_safe_text(med.get("name")), styles["body"]),
                Paragraph(_safe_text(med.get("type")), styles["body"]),
                Paragraph(_safe_text(med.get("specification")), styles["body"]),
                Paragraph(_safe_text(med.get("quantity")), styles["body"]),
            ])
        med_table = Table(
            rows, colWidths=[55 * mm, 35 * mm, 50 * mm, 30 * mm],
            repeatRows=1,
            style=TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), _PRIMARY),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), font),
                ("FONTSIZE", (0, 0), (-1, 0), 9),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (2, 0), (-1, -1), "CENTER"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _LIGHT_BG]),
                ("GRID", (0, 0), (-1, -1), 0.5, _BORDER),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]),
        )
        story.append(med_table)
        story.append(Spacer(1, 6))

    # --- Reminders ---
    active_reminders = [
        r for r in reminders
        if r.get("enabled") in (1, True, "1", "true")
    ] if reminders else []
    if active_reminders:
        story.append(Paragraph("▎ 用药提醒", styles["section"]))
        for r in active_reminders:
            title = _safe_text(r.get("title") or r.get("medicine_name") or r.get("formula_name"))
            times = _parse_json_field(r.get("times"), [])
            times_str = "、".join(str(t) for t in times) if isinstance(times, list) else _safe_text(times)
            dosage = _safe_text(r.get("dosage"), "")
            line = f"· {title}"
            if times_str and times_str != "—":
                line += f"（{times_str}）"
            if dosage and dosage != "—":
                line += f" — {dosage}"
            story.append(Paragraph(line, styles["body"]))
        story.append(Spacer(1, 4))

    # --- Disclaimer ---
    story.append(Spacer(1, 8))
    story.append(_hr(_BORDER, 0.5))
    story.append(Paragraph(
        "⚠ 本健康摘要仅供个人健康管理参考，不构成医疗诊断。"
        "如有不适，请及时就医。",
        styles["disclaimer"],
    ))

    # --- Footer ---
    story.append(Spacer(1, 10))
    story.append(_hr(_BORDER, 0.3))
    story.append(Paragraph(
        f"打印于 {_format_date()}　·　家庭医生 v2.0",
        styles["footer"],
    ))

    doc.build(story)
    return buf.getvalue()
