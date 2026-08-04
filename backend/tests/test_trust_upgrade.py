"""Tests for trust upgrade mechanism (B→A→S auto-promotion)."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.trust_engine import (
    check_trust_upgrade,
    auto_upgrade_eligible_entities,
    LEVEL_S,
    LEVEL_A,
    LEVEL_B,
    LEVEL_C,
    UPGRADE_THRESHOLDS,
)


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.query = AsyncMock()
    db.query_one = AsyncMock()
    db.execute = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_upgrade_thresholds_exist():
    assert LEVEL_B in UPGRADE_THRESHOLDS
    assert LEVEL_A in UPGRADE_THRESHOLDS
    assert LEVEL_S not in UPGRADE_THRESHOLDS
    assert LEVEL_C not in UPGRADE_THRESHOLDS


@pytest.mark.asyncio
async def test_s_level_not_upgradable(mock_db):
    with patch("app.trust_engine.get_trust_level", new_callable=AsyncMock) as mock_tl:
        mock_tl.return_value = LEVEL_S
        result = await check_trust_upgrade(mock_db, "ke-s-level")
        assert result["eligible"] is False


@pytest.mark.asyncio
async def test_b_level_not_enough_helpful(mock_db):
    with patch("app.trust_engine.get_trust_level", new_callable=AsyncMock) as mock_tl:
        mock_tl.return_value = LEVEL_B
        mock_db.query_one = AsyncMock(side_effect=[
            {"c": 3},
            {"c": 0},
            {"age_days": 30},
        ])
        result = await check_trust_upgrade(mock_db, "ke-test")
        assert result["eligible"] is False
        assert "好评" in result["reason"]


@pytest.mark.asyncio
async def test_b_level_has_negative(mock_db):
    with patch("app.trust_engine.get_trust_level", new_callable=AsyncMock) as mock_tl:
        mock_tl.return_value = LEVEL_B
        mock_db.query_one = AsyncMock(side_effect=[
            {"c": 10},
            {"c": 1},
            {"age_days": 30},
        ])
        result = await check_trust_upgrade(mock_db, "ke-test")
        assert result["eligible"] is False
        assert "差评" in result["reason"]


@pytest.mark.asyncio
async def test_b_level_too_new(mock_db):
    with patch("app.trust_engine.get_trust_level", new_callable=AsyncMock) as mock_tl:
        mock_tl.return_value = LEVEL_B
        mock_db.query_one = AsyncMock(side_effect=[
            {"c": 10},
            {"c": 0},
            {"age_days": 3},
        ])
        result = await check_trust_upgrade(mock_db, "ke-test")
        assert result["eligible"] is False
        assert "天" in result["reason"]


@pytest.mark.asyncio
async def test_b_level_eligible_upgrade_to_a(mock_db):
    with patch("app.trust_engine.get_trust_level", new_callable=AsyncMock) as mock_tl, \
         patch("app.trust_engine.update_trust_level", new_callable=AsyncMock) as mock_ut:
        mock_tl.return_value = LEVEL_B
        mock_db.query_one = AsyncMock(side_effect=[
            {"c": 5},
            {"c": 0},
            {"age_days": 10},
        ])
        result = await check_trust_upgrade(mock_db, "ke-test")
        assert result["eligible"] is True
        assert result["new_level"] == LEVEL_A
        mock_ut.assert_called_once()


@pytest.mark.asyncio
async def test_a_level_eligible_upgrade_to_s(mock_db):
    with patch("app.trust_engine.get_trust_level", new_callable=AsyncMock) as mock_tl, \
         patch("app.trust_engine.update_trust_level", new_callable=AsyncMock) as mock_ut:
        mock_tl.return_value = LEVEL_A
        mock_db.query_one = AsyncMock(side_effect=[
            {"c": 10},
            {"c": 0},
            {"age_days": 35},
        ])
        result = await check_trust_upgrade(mock_db, "ke-test")
        assert result["eligible"] is True
        assert result["new_level"] == LEVEL_S


@pytest.mark.asyncio
async def test_auto_upgrade_scans_entities(mock_db):
    mock_db.query = AsyncMock(return_value=[
        {"id": "ke-1"},
        {"id": "ke-2"},
    ])

    original_check = check_trust_upgrade

    async def mock_check(db, entity_id):
        if entity_id == "ke-1":
            return {"eligible": True, "new_level": "A", "reason": "test"}
        return {"eligible": False, "new_level": "B", "reason": "not enough"}

    import app.trust_engine as te
    te.check_trust_upgrade = mock_check
    try:
        result = await auto_upgrade_eligible_entities(mock_db)
        assert len(result) == 1
        assert result[0]["entity_id"] == "ke-1"
    finally:
        te.check_trust_upgrade = original_check


@pytest.mark.asyncio
async def test_auto_upgrade_empty(mock_db):
    mock_db.query = AsyncMock(return_value=[])
    result = await auto_upgrade_eligible_entities(mock_db)
    assert result == []
