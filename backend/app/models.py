"""Pydantic models for all entities."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class UserRegister(BaseModel):
    username: str = Field(min_length=2, max_length=50)
    password: str = Field(min_length=6, max_length=100)
    display_name: str | None = None


class UserLogin(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: str
    username: str
    display_name: str | None = None
    family_id: str | None = None
    created_at: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------

class PaginatedResponse(BaseModel):
    items: list[dict[str, Any]]
    total: int
    page: int
    pageSize: int
    totalPages: int


# ---------------------------------------------------------------------------
# Herbs
# ---------------------------------------------------------------------------

class HerbOut(BaseModel):
    id: str
    name: str
    aliases: str | None = None
    nature: str | None = None
    flavor: str | None = None
    meridians: str | None = None
    efficacy: str | None = None
    indications: str | None = None
    contraindications: str | None = None
    dosage_min_g: float | None = None
    dosage_max_g: float | None = None
    toxicity: str | None = None
    category: str | None = None
    properties: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Formulas
# ---------------------------------------------------------------------------

class FormulaOut(BaseModel):
    id: str
    name: str
    source: str | None = None
    category: str | None = None
    composition: list[dict[str, Any]] | None = None
    efficacy: str | None = None
    indications: str | None = None
    modifications: list[dict[str, Any]] | None = None
    properties: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Medicines (family drug cabinet)
# ---------------------------------------------------------------------------

class MedicineCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    brand: str | None = None
    type: str = Field(description="western/chinese_patent/supplement/herbal_tea/herbal")
    specification: str | None = None
    unit: str | None = None
    quantity: int = 0
    production_date: str | None = None
    expiry_date: str | None = None
    opened_date: str | None = None
    shelf_life_after_open: str | None = None
    dosage_instructions: str | None = None
    contraindications: str | None = None
    barcode: str | None = None
    drug_class: str | None = None
    active_ingredients: list[str] | None = None
    herbal_fields: dict[str, Any] | None = None


class MedicineUpdate(BaseModel):
    name: str | None = None
    brand: str | None = None
    type: str | None = None
    specification: str | None = None
    unit: str | None = None
    quantity: int | None = None
    production_date: str | None = None
    expiry_date: str | None = None
    opened_date: str | None = None
    shelf_life_after_open: str | None = None
    dosage_instructions: str | None = None
    contraindications: str | None = None
    barcode: str | None = None
    drug_class: str | None = None
    active_ingredients: list[str] | None = None
    herbal_fields: dict[str, Any] | None = None


class MedicineOut(BaseModel):
    id: str
    tenant_id: str
    family_member_id: str | None = None
    name: str
    brand: str | None = None
    type: str
    specification: str | None = None
    unit: str | None = None
    quantity: int = 0
    production_date: str | None = None
    expiry_date: str | None = None
    opened_date: str | None = None
    shelf_life_after_open: str | None = None
    dosage_instructions: str | None = None
    contraindications: str | None = None
    barcode: str | None = None
    drug_class: str | None = None
    active_ingredients: list[str] | None = None
    herbal_fields: dict[str, Any] | None = None
    properties: dict[str, Any] | None = None
    created_at: str | None = None
    updated_at: str | None = None


# ---------------------------------------------------------------------------
# Safety
# ---------------------------------------------------------------------------

class SafetyCheckRequest(BaseModel):
    herbs: list[str] = Field(default_factory=list, description="List of herb names")
    medicines: list[str] = Field(default_factory=list, description="List of medicine/drug names")


class SafetyWarning(BaseModel):
    severity: str  # "critical" or "warning"
    rule_type: str
    drug_a: str
    drug_b: str
    mechanism: str
    action: str
    source: str


class SafetyCheckResponse(BaseModel):
    safe: bool
    warnings: list[SafetyWarning]
    disclaimer: str = (
        "⚠️ 以上安全检查结果由系统硬编码规则匹配生成，仅供参考。"
        "请务必在调整任何用药方案前咨询执业医师或药师。"
    )


# ---------------------------------------------------------------------------
# Safety V2 — Five-layer safety check (spec §15.3)
# ---------------------------------------------------------------------------

class SafetyCheckRequestV2(BaseModel):
    herbs: list[str] = Field(default_factory=list, description="List of herb names")
    medicines: list[str] = Field(default_factory=list, description="List of medicine/drug names")
    user_profile: dict[str, Any] | None = Field(
        default=None,
        description="User profile: is_pregnant, age, weight_kg, constitution",
    )
    dosages: dict[str, float] | None = Field(
        default=None,
        description="Map of herb_name → dosage in grams",
    )


class SafetyWarningV2(BaseModel):
    layer: int = Field(description="Safety check layer 1-5")
    severity: str = Field(description="critical | high | medium | low")
    title: str
    detail: str
    herbs: list[str] = Field(default_factory=list)
    action: str = Field(description="禁止 | 谨慎 | 告知医生")
    source: str


class SafetyCheckResponseV2(BaseModel):
    safe: bool
    warnings: list[SafetyWarningV2]
    interactions: list[str] = Field(default_factory=list, description="中西药交互提示列表")
    disclaimer: str
    checked_herbs: list[str] = Field(default_factory=list)
    checked_medicines: list[str] = Field(default_factory=list)
    unknown_herbs: list[str] = Field(default_factory=list)
    unknown_medicines: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Constitution Assessment (spec §2.3 / §4.2)
# ---------------------------------------------------------------------------

class ConstitutionAssessRequest(BaseModel):
    answers: dict[str, int] = Field(
        description='Mapping of question_id → score (0-4). e.g. {"q1": 3}',
    )


class UserProfileUpdate(BaseModel):
    display_name: str | None = None
    birth_year: int | None = None
    gender: str | None = None
    height_cm: float | None = None
    weight_kg: float | None = None
    allergies: list[str] | None = None
    health_conditions: list[str] | None = None
    is_pregnant: bool | None = None
    blood_type: str | None = None
    notes: str | None = None


# ---------------------------------------------------------------------------
# Reminders (吃药提醒, spec §20)
# ---------------------------------------------------------------------------

VALID_FREQUENCIES = {"daily", "weekly", "custom"}


def _validate_time_str(value: str) -> str:
    parts = value.split(":")
    if len(parts) != 2:
        raise ValueError(f"时间格式应为 HH:MM，收到 {value!r}")
    hh, mm = parts
    if not (hh.isdigit() and mm.isdigit()):
        raise ValueError(f"时间格式应为 HH:MM，收到 {value!r}")
    h, m = int(hh), int(mm)
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError(f"时间超出有效范围 (00:00-23:59)，收到 {value!r}")
    return f"{h:02d}:{m:02d}"


class ReminderCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    herb_name: str | None = None
    formula_name: str | None = None
    medicine_name: str | None = None
    dosage: str | None = None
    frequency: str = "daily"
    times: list[str]
    start_date: str
    end_date: str | None = None
    notes: str | None = None
    enabled: bool = True

    @field_validator("frequency")
    @classmethod
    def validate_frequency(cls, v: str) -> str:
        if v not in VALID_FREQUENCIES:
            raise ValueError(f"频率必须是 {VALID_FREQUENCIES} 之一，收到 {v!r}")
        return v

    @field_validator("times")
    @classmethod
    def validate_times(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("至少需要一个提醒时间")
        return [_validate_time_str(t) for t in v]

    @model_validator(mode="after")
    def validate_dates(self):
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("结束日期不能早于开始日期")
        return self


class ReminderUpdate(BaseModel):
    title: str | None = None
    dosage: str | None = None
    frequency: str | None = None
    times: list[str] | None = None
    end_date: str | None = None
    notes: str | None = None
    enabled: bool | None = None

    @field_validator("frequency")
    @classmethod
    def validate_frequency(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_FREQUENCIES:
            raise ValueError(f"频率必须是 {VALID_FREQUENCIES} 之一，收到 {v!r}")
        return v

    @field_validator("times")
    @classmethod
    def validate_times(cls, v: list[str] | None) -> list[str] | None:
        if v is not None:
            if not v:
                raise ValueError("至少需要一个提醒时间")
            return [_validate_time_str(t) for t in v]
        return v


class ReminderResponse(BaseModel):
    id: str
    user_id: str
    title: str
    herb_name: str | None = None
    formula_name: str | None = None
    medicine_name: str | None = None
    dosage: str | None = None
    frequency: str
    times: list[str]
    start_date: str
    end_date: str | None = None
    notes: str | None = None
    enabled: bool
    created_at: str
    updated_at: str


# ---------------------------------------------------------------------------
# 用药套餐 (Medication Plans, spec §20.5)
# ---------------------------------------------------------------------------

VALID_PLAN_STATUSES = {"active", "paused", "completed"}


class PlanItemCreate(BaseModel):
    medicine_name: str = Field(min_length=1, max_length=200)
    dosage: str | None = None
    frequency: str = "daily"
    times: list[str]
    notes: str | None = None
    sort_order: int = 0

    @field_validator("times")
    @classmethod
    def validate_times(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("至少需要一个提醒时间")
        return [_validate_time_str(t) for t in v]


class PlanItemUpdate(BaseModel):
    medicine_name: str | None = None
    dosage: str | None = None
    frequency: str | None = None
    times: list[str] | None = None
    notes: str | None = None
    sort_order: int | None = None

    @field_validator("times")
    @classmethod
    def validate_times(cls, v: list[str] | None) -> list[str] | None:
        if v is not None:
            if not v:
                raise ValueError("至少需要一个提醒时间")
            return [_validate_time_str(t) for t in v]
        return v


class PlanItemOut(BaseModel):
    id: str
    plan_id: str
    medicine_name: str
    dosage: str | None = None
    frequency: str | None = None
    times: list[str] = []
    notes: str | None = None
    sort_order: int = 0
    reminder_id: str | None = None


class MedicationPlanCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    family_member_id: str | None = None
    status: str = "active"
    start_date: str | None = None
    end_date: str | None = None
    items: list[PlanItemCreate] = Field(min_length=1)

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in VALID_PLAN_STATUSES:
            raise ValueError(f"状态必须是 {VALID_PLAN_STATUSES} 之一，收到 {v!r}")
        return v

    @model_validator(mode="after")
    def validate_dates(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("结束日期不能早于开始日期")
        return self


class MedicationPlanUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    status: str | None = None
    start_date: str | None = None
    end_date: str | None = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_PLAN_STATUSES:
            raise ValueError(f"状态必须是 {VALID_PLAN_STATUSES} 之一，收到 {v!r}")
        return v


class MedicationPlanOut(BaseModel):
    id: str
    user_id: str
    family_member_id: str | None = None
    name: str
    description: str | None = None
    status: str
    start_date: str | None = None
    end_date: str | None = None
    created_at: str
    updated_at: str
    items: list[PlanItemOut] = []


# ---------------------------------------------------------------------------
# Favorites / 知识收藏
# ---------------------------------------------------------------------------

class FavoriteCreate(BaseModel):
    entry_type: str
    title: str
    content: str | None = None
    summary: str | None = None
    tags: list[str] = []
    source_type: str | None = None
    source_url: str | None = None


class FavoriteUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    summary: str | None = None
    tags: list[str] | None = None
    is_starred: bool | None = None


# ---------------------------------------------------------------------------
# Family Members (家庭成员)
# ---------------------------------------------------------------------------

VALID_RELATIONS = {"父亲", "母亲", "配偶", "儿子", "女儿", "自己", "其他"}
VALID_GENDERS = {"男", "女"}


class FamilyMemberCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    relation: str
    birth_date: str | None = None
    gender: str | None = None

    @field_validator("relation")
    @classmethod
    def validate_relation(cls, v: str) -> str:
        if v not in VALID_RELATIONS:
            raise ValueError(f"关系必须是 {VALID_RELATIONS} 之一，收到 {v!r}")
        return v

    @field_validator("gender")
    @classmethod
    def validate_gender(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_GENDERS:
            raise ValueError(f"性别必须是 {VALID_GENDERS} 之一，收到 {v!r}")
        return v


class FamilyMemberUpdate(BaseModel):
    name: str | None = None
    relation: str | None = None
    birth_date: str | None = None
    gender: str | None = None

    @field_validator("relation")
    @classmethod
    def validate_relation(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_RELATIONS:
            raise ValueError(f"关系必须是 {VALID_RELATIONS} 之一，收到 {v!r}")
        return v

    @field_validator("gender")
    @classmethod
    def validate_gender(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_GENDERS:
            raise ValueError(f"性别必须是 {VALID_GENDERS} 之一，收到 {v!r}")
        return v


# ---------------------------------------------------------------------------
# Prescription / Health Report PDF (spec §21)
# ---------------------------------------------------------------------------

class PrescriptionRequest(BaseModel):
    formula_id: str = Field(min_length=1, max_length=200)
    patient_name: str = Field(default="—", max_length=100)
    patient_age: str | None = Field(default=None, max_length=20)
    patient_gender: str | None = Field(default=None, max_length=10)
    prescriber: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=2000)
    usage_instructions: str | None = Field(default=None, max_length=1000)


class HealthReportRequest(BaseModel):
    member_id: str | None = Field(default=None, max_length=200)
    report_type: str = Field(default="summary", max_length=50)
