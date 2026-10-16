import json

import pytest

from app.safety_engine import run_safety_check


async def _add_medicine(db, name: str, ingredients: list[str], drug_class: str = ""):
    await db.execute(
        """INSERT INTO medicines
           (id, tenant_id, name, type, drug_class, active_ingredients, properties)
           VALUES (?, 'default', ?, 'western', ?, ?, '{}')""",
        (f"logic-{name}", name, drug_class, json.dumps(ingredients, ensure_ascii=False)),
    )


@pytest.mark.asyncio
async def test_safety_warns_for_two_nsaids_in_selected_medicines(db):
    await _add_medicine(db, "布洛芬", [])
    await _add_medicine(db, "双氯芬酸", [])
    result = await run_safety_check(db, [], ["布洛芬", "双氯芬酸"])
    warning = next(w for w in result.warnings if w.title == "重复使用非甾体抗炎药")
    assert warning.layer == 1
    assert warning.severity == "high"
    assert result.safe is False


@pytest.mark.asyncio
async def test_safety_warns_for_repeated_active_ingredient(db):
    await _add_medicine(db, "感冒药甲", ["对乙酰氨基酚"])
    await _add_medicine(db, "感冒药乙", ["对乙酰氨基酚"])
    result = await run_safety_check(db, [], ["感冒药甲", "感冒药乙"])
    warnings = [w for w in result.warnings if w.title.startswith("有效成分重复用药")]
    assert len(warnings) == 1
    assert "对乙酰氨基酚" in warnings[0].detail
    assert "累计日剂量" in warnings[0].detail


@pytest.mark.asyncio
async def test_child_dose_uses_spec_weight_formula_as_reference(db):
    await db.execute(
        """INSERT INTO herbs
           (id, name, dosage_min_g, dosage_max_g, properties)
           VALUES ('child-dose-test', '测试药材', 2, 10, '{}')"""
    )
    result = await run_safety_check(
        db, ["测试药材"], user_profile={"age": 8, "weight_kg": 20}
    )
    warning = next(w for w in result.warnings if w.title == "儿童剂量需专业确认")
    assert "Young's" in warning.detail
    assert "3.20g" in warning.detail
    assert "不构成儿童用药建议" in warning.detail
