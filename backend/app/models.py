"""Pydantic models for all entities."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


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
    disclaimer: str
    checked_herbs: list[str] = Field(default_factory=list)
    checked_medicines: list[str] = Field(default_factory=list)
    unknown_herbs: list[str] = Field(default_factory=list)
    unknown_medicines: list[str] = Field(default_factory=list)
