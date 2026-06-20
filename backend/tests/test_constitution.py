"""Tests for constitution assessment + user profile endpoints (spec §2.3 / §4.2)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.constitution_data import CONSTITUTION_QUESTIONS, NINE_CONSTITUTION_TYPES
from app.routers.constitution import calculate_scores, determine_primary_secondary


def _answers_for_type(ctype: str, score: int = 4, others: int = 0) -> dict[str, int]:
    """Build an answer dict: all questions of `ctype` get `score`, rest get `others`."""
    answers: dict[str, int] = {}
    for q in CONSTITUTION_QUESTIONS:
        answers[q["id"]] = score if q["type"] == ctype else others
    return answers


# ---------------------------------------------------------------------------
# Questionnaire endpoint
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_questionnaire(client: AsyncClient, auth_headers: dict):
    """GET /api/constitution/questionnaire returns 66 questions across 9 types."""
    response = await client.get("/api/constitution/questionnaire", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total_questions"] == 66
    assert len(data["questions"]) == 66
    assert len(data["types"]) == 9
    assert set(data["types"]) == set(NINE_CONSTITUTION_TYPES)
    assert "平和质" in data["grouped"]
    assert len(data["grouped"]["平和质"]) == 8
    assert len(data["score_options"]) == 5
    assert "descriptions" in data


# ---------------------------------------------------------------------------
# Score calculation correctness (unit tests)
# ---------------------------------------------------------------------------

def test_calculate_scores_all_max():
    """All answers = 4 for 气虚质 → 气虚质 score = 100."""
    answers = _answers_for_type("气虚质", score=4, others=0)
    scores = calculate_scores(answers)
    assert scores["气虚质"] == 100.0


def test_calculate_scores_partial():
    """气虚质 8 questions all = 2 (有时) → score = 50.0."""
    answers = _answers_for_type("气虚质", score=2, others=0)
    scores = calculate_scores(answers)
    assert scores["气虚质"] == 50.0


def test_calculate_scores_reverse_q60():
    """q60 (你容易忘事吗？) is reverse-scored for 平和质: raw=4 → effective=0."""
    answers = {q["id"]: 0 for q in CONSTITUTION_QUESTIONS}
    answers["q60"] = 4
    scores = calculate_scores(answers)
    assert scores["平和质"] == 0.0

    answers["q60"] = 0
    scores2 = calculate_scores(answers)
    assert scores2["平和质"] == pytest.approx(12.5, abs=0.1)

    answers["q60"] = 4
    answers["q59"] = 4
    scores3 = calculate_scores(answers)
    assert scores3["平和质"] == pytest.approx(12.5, abs=0.1)


# ---------------------------------------------------------------------------
# Primary/secondary determination
# ---------------------------------------------------------------------------

def test_determine_balanced_constitution():
    """平和质 score >= 60 and all others < 40 → 平和质, no secondary."""
    scores = {t: 10.0 for t in NINE_CONSTITUTION_TYPES}
    scores["平和质"] = 80.0
    primary, secondary = determine_primary_secondary(scores)
    assert primary == "平和质"
    assert secondary == []


def test_determine_biased_primary():
    """Highest biased type >= 40 → that type is primary."""
    scores = {t: 10.0 for t in NINE_CONSTITUTION_TYPES}
    scores["气虚质"] = 70.0
    scores["阳虚质"] = 30.0
    primary, secondary = determine_primary_secondary(scores)
    assert primary == "气虚质"
    assert secondary == []


def test_determine_with_secondary_types():
    """Two biased types >= 40 → highest is primary, other is secondary."""
    scores = {t: 10.0 for t in NINE_CONSTITUTION_TYPES}
    scores["气虚质"] = 70.0
    scores["阴虚质"] = 55.0
    scores["阳虚质"] = 30.0
    primary, secondary = determine_primary_secondary(scores)
    assert primary == "气虚质"
    assert "阴虚质" in secondary
    assert "阳虚质" not in secondary


# ---------------------------------------------------------------------------
# POST /assess — integration tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_assess_all_qi_deficiency(client: AsyncClient, auth_headers: dict):
    """Submit answers favoring 气虚质 → primary_type is 气虚质."""
    answers = _answers_for_type("气虚质", score=4, others=0)
    response = await client.post(
        "/api/constitution/assess", headers=auth_headers, json={"answers": answers}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["primary_type"] == "气虚质"
    assert data["results"]["气虚质"] == 100.0
    assert "id" in data
    assert "description" in data


@pytest.mark.asyncio
async def test_assess_all_balanced(client: AsyncClient, auth_headers: dict):
    """Submit answers favoring 平和质 (all positive = 4, reverse q60 = 0) → 平和质."""
    answers: dict[str, int] = {}
    for q in CONSTITUTION_QUESTIONS:
        if q["type"] == "平和质":
            answers[q["id"]] = 0 if q.get("reverse") else 4
        else:
            answers[q["id"]] = 0
    response = await client.post(
        "/api/constitution/assess", headers=auth_headers, json={"answers": answers}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["primary_type"] == "平和质"
    assert data["secondary_types"] == []


@pytest.mark.asyncio
async def test_assess_mixed_with_secondary(client: AsyncClient, auth_headers: dict):
    """Submit mixed answers → correct primary + secondary detection."""
    answers: dict[str, int] = {}
    for q in CONSTITUTION_QUESTIONS:
        if q["type"] == "气虚质":
            answers[q["id"]] = 4
        elif q["type"] == "阳虚质":
            answers[q["id"]] = 3
        else:
            answers[q["id"]] = 0
    response = await client.post(
        "/api/constitution/assess", headers=auth_headers, json={"answers": answers}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["primary_type"] == "气虚质"
    assert "阳虚质" in data["secondary_types"]


@pytest.mark.asyncio
async def test_assess_saved_to_db(client: AsyncClient, auth_headers: dict):
    """Assessment is persisted — appears in history."""
    answers = _answers_for_type("阴虚质", score=4, others=0)
    resp = await client.post(
        "/api/constitution/assess", headers=auth_headers, json={"answers": answers}
    )
    assert resp.status_code == 201
    aid = resp.json()["id"]

    hist = await client.get("/api/constitution/history", headers=auth_headers)
    assert hist.status_code == 200
    items = hist.json()["items"]
    assert any(i["id"] == aid for i in items)
    assert hist.json()["total"] >= 1


@pytest.mark.asyncio
async def test_assess_empty_answers_returns_422(client: AsyncClient, auth_headers: dict):
    """Empty answers dict → 422."""
    response = await client.post(
        "/api/constitution/assess", headers=auth_headers, json={"answers": {}}
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_assess_missing_answers_key_returns_422(
    client: AsyncClient, auth_headers: dict
):
    """Missing 'answers' key → 422."""
    response = await client.post(
        "/api/constitution/assess", headers=auth_headers, json={}
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_assess_unauthorized(raw_client: AsyncClient):
    """POST /assess without auth → 401."""
    response = await raw_client.post(
        "/api/constitution/assess", json={"answers": {"q1": 3}}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_assess_partial_answers(client: AsyncClient, auth_headers: dict):
    """Only some questions answered → still works (missing = 0)."""
    response = await client.post(
        "/api/constitution/assess",
        headers=auth_headers,
        json={"answers": {"q1": 4, "q2": 4, "q3": 4}},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["results"]["气虚质"] > 0


@pytest.mark.asyncio
async def test_assess_clamps_invalid_scores(client: AsyncClient, auth_headers: dict):
    """Scores outside 0-4 are clamped."""
    response = await client.post(
        "/api/constitution/assess",
        headers=auth_headers,
        json={"answers": {"q1": 99, "q2": -5}},
    )
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_score_boundary_exactly_40(client: AsyncClient, auth_headers: dict):
    """A biased type scoring exactly 40 is treated as active (>= threshold)."""
    answers: dict[str, int] = {}
    for q in CONSTITUTION_QUESTIONS:
        if q["type"] == "湿热质":
            answers[q["id"]] = 2
        else:
            answers[q["id"]] = 0
    scores = calculate_scores(answers)
    assert scores["湿热质"] == pytest.approx(50.0, abs=0.1)
    primary, _ = determine_primary_secondary(scores)
    assert primary == "湿热质"


# ---------------------------------------------------------------------------
# GET /history and GET /latest
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_history_multiple(client: AsyncClient, auth_headers: dict):
    """Multiple assessments appear in history."""
    for ctype in ("气虚质", "阳虚质", "阴虚质"):
        answers = _answers_for_type(ctype, score=4, others=0)
        await client.post(
            "/api/constitution/assess", headers=auth_headers, json={"answers": answers}
        )
    response = await client.get("/api/constitution/history", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 3


@pytest.mark.asyncio
async def test_get_latest(client: AsyncClient, auth_headers: dict):
    """GET /latest returns the most recent assessment."""
    answers1 = _answers_for_type("气虚质", score=4, others=0)
    await client.post(
        "/api/constitution/assess", headers=auth_headers, json={"answers": answers1}
    )
    import asyncio
    await asyncio.sleep(0.05)

    answers2 = _answers_for_type("阳虚质", score=4, others=0)
    resp2 = await client.post(
        "/api/constitution/assess", headers=auth_headers, json={"answers": answers2}
    )
    latest_id = resp2.json()["id"]

    response = await client.get("/api/constitution/latest", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["id"] == latest_id


@pytest.mark.asyncio
async def test_latest_not_found(client: AsyncClient, auth_headers: dict):
    """GET /latest with no assessments → 404."""
    response = await client.get("/api/constitution/latest", headers=auth_headers)
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# User isolation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_user_isolation_history(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict
):
    """User A's assessments are not visible to User B."""
    answers = _answers_for_type("气虚质", score=4, others=0)
    await client.post(
        "/api/constitution/assess", headers=auth_headers, json={"answers": answers}
    )
    response = await client.get(
        "/api/constitution/history", headers=second_user_headers
    )
    assert response.status_code == 200
    assert response.json()["total"] == 0


# ---------------------------------------------------------------------------
# Profile sync after assessment
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_profile_synced_after_assessment(
    client: AsyncClient, auth_headers: dict
):
    """After assessment, user_profiles.constitution_type is updated."""
    answers = _answers_for_type("气虚质", score=4, others=0)
    await client.post(
        "/api/constitution/assess", headers=auth_headers, json={"answers": answers}
    )
    profile = await client.get("/api/profile", headers=auth_headers)
    assert profile.status_code == 200
    assert profile.json()["constitution_type"] == "气虚质"


# ---------------------------------------------------------------------------
# Profile CRUD
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_profile_empty(client: AsyncClient, auth_headers: dict):
    """GET /api/profile for new user returns empty profile."""
    response = await client.get("/api/profile", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["display_name"] is None
    assert data["allergies"] == []
    assert data["health_conditions"] == []
    assert data["is_pregnant"] is False


@pytest.mark.asyncio
async def test_update_profile_basic(client: AsyncClient, auth_headers: dict):
    """PUT /api/profile updates display_name, gender, etc."""
    response = await client.put(
        "/api/profile",
        headers=auth_headers,
        json={
            "display_name": "王阿姨",
            "gender": "女",
            "birth_year": 1960,
            "height_cm": 158.0,
            "weight_kg": 60.0,
            "blood_type": "A",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["display_name"] == "王阿姨"
    assert data["gender"] == "女"
    assert data["birth_year"] == 1960
    assert data["blood_type"] == "A"


@pytest.mark.asyncio
async def test_update_profile_arrays(client: AsyncClient, auth_headers: dict):
    """PUT /api/profile updates allergies and health_conditions arrays."""
    response = await client.put(
        "/api/profile",
        headers=auth_headers,
        json={
            "allergies": ["青霉素", "海鲜"],
            "health_conditions": ["高血压", "糖尿病"],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["allergies"] == ["青霉素", "海鲜"]
    assert data["health_conditions"] == ["高血压", "糖尿病"]


@pytest.mark.asyncio
async def test_update_profile_pregnant_flag(client: AsyncClient, auth_headers: dict):
    """PUT /api/profile with is_pregnant=True sets the flag."""
    response = await client.put(
        "/api/profile",
        headers=auth_headers,
        json={"is_pregnant": True},
    )
    assert response.status_code == 200
    assert response.json()["is_pregnant"] is True

    resp2 = await client.get("/api/profile", headers=auth_headers)
    assert resp2.json()["is_pregnant"] is True


@pytest.mark.asyncio
async def test_update_profile_persists(client: AsyncClient, auth_headers: dict):
    """Profile updates persist across requests."""
    await client.put(
        "/api/profile",
        headers=auth_headers,
        json={"display_name": "李芳", "notes": "需注意血压"},
    )
    response = await client.get("/api/profile", headers=auth_headers)
    assert response.json()["display_name"] == "李芳"
    assert response.json()["notes"] == "需注意血压"


@pytest.mark.asyncio
async def test_profile_unauthorized(raw_client: AsyncClient):
    """GET /api/profile without auth → 401."""
    response = await raw_client.get("/api/profile")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_profile_isolation(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict
):
    """User A's profile is not visible to User B."""
    await client.put(
        "/api/profile",
        headers=auth_headers,
        json={"display_name": "用户A"},
    )
    resp_b = await client.get("/api/profile", headers=second_user_headers)
    assert resp_b.status_code == 200
    assert resp_b.json()["display_name"] is None


# ---------------------------------------------------------------------------
# Secondary types detection (2+ 兼夹体质)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_two_secondary_types(client: AsyncClient, auth_headers: dict):
    """When 3 biased types are active, highest is primary, other 2 are secondary."""
    answers: dict[str, int] = {}
    for q in CONSTITUTION_QUESTIONS:
        if q["type"] == "气虚质":
            answers[q["id"]] = 4
        elif q["type"] == "阳虚质":
            answers[q["id"]] = 3
        elif q["type"] == "阴虚质":
            answers[q["id"]] = 3
        else:
            answers[q["id"]] = 0
    response = await client.post(
        "/api/constitution/assess", headers=auth_headers, json={"answers": answers}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["primary_type"] == "气虚质"
    assert "阳虚质" in data["secondary_types"]
    assert "阴虚质" in data["secondary_types"]
    assert len(data["secondary_types"]) == 2
