"""Tests for prescriptions PDF endpoints (spec §21)."""

import pytest
from httpx import AsyncClient


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extract text from PDF bytes using PyMuPDF (fitz)."""
    import fitz

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    text = "".join(page.get_text() for page in doc)
    doc.close()
    return text


# ---------------------------------------------------------------------------
# POST /api/prescriptions/generate
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_prescription_returns_pdf(client: AsyncClient, auth_headers: dict):
    """POST /api/prescriptions/generate returns a valid PDF file."""
    response = await client.post(
        "/api/prescriptions/generate",
        json={
            "formula_id": "formula-001",
            "patient_name": "张三",
            "patient_age": "45",
            "patient_gender": "男",
            "prescriber": "李医生",
            "notes": "饭后温服，忌生冷",
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    content = response.content
    assert len(content) > 1000
    assert content[:4] == b"%PDF"


@pytest.mark.asyncio
async def test_generate_prescription_content_disposition(client: AsyncClient, auth_headers: dict):
    """Response includes Content-Disposition with formula name."""
    response = await client.post(
        "/api/prescriptions/generate",
        json={"formula_id": "formula-001"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    cd = response.headers.get("content-disposition", "")
    assert "attachment" in cd
    assert ".pdf" in cd


@pytest.mark.asyncio
async def test_generate_prescription_404_invalid_formula(client: AsyncClient, auth_headers: dict):
    """POST /api/prescriptions/generate with invalid formula_id returns 404."""
    response = await client.post(
        "/api/prescriptions/generate",
        json={"formula_id": "nonexistent-formula"},
        headers=auth_headers,
    )
    assert response.status_code == 404
    assert "未找到该方剂" in response.json()["detail"]


@pytest.mark.asyncio
async def test_generate_prescription_requires_auth(client: AsyncClient):
    """POST /api/prescriptions/generate without auth returns 401."""
    response = await client.post(
        "/api/prescriptions/generate",
        json={"formula_id": "formula-001"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_generate_prescription_second_formula(client: AsyncClient, auth_headers: dict):
    """Can generate PDF for formula-002 (四物汤)."""
    response = await client.post(
        "/api/prescriptions/generate",
        json={
            "formula_id": "formula-002",
            "patient_name": "李四",
            "patient_gender": "女",
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content[:4] == b"%PDF"


@pytest.mark.asyncio
async def test_generate_prescription_with_usage(client: AsyncClient, auth_headers: dict):
    """PDF generation works with usage_instructions field."""
    response = await client.post(
        "/api/prescriptions/generate",
        json={
            "formula_id": "formula-001",
            "usage_instructions": "水煎服，每日一剂，分两次温服",
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.content[:4] == b"%PDF"


@pytest.mark.asyncio
async def test_generate_prescription_missing_formula_id(client: AsyncClient, auth_headers: dict):
    """POST without formula_id returns 422 validation error."""
    response = await client.post(
        "/api/prescriptions/generate",
        json={"patient_name": "测试"},
        headers=auth_headers,
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/prescriptions/health-report
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_health_report_returns_pdf(client: AsyncClient, auth_headers: dict):
    """POST /api/prescriptions/health-report returns a valid PDF."""
    response = await client.post(
        "/api/prescriptions/health-report",
        json={"report_type": "summary"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content[:4] == b"%PDF"
    assert len(response.content) > 500


@pytest.mark.asyncio
async def test_health_report_content_disposition(client: AsyncClient, auth_headers: dict):
    """Health report response includes Content-Disposition."""
    response = await client.post(
        "/api/prescriptions/health-report",
        json={},
        headers=auth_headers,
    )
    assert response.status_code == 200
    cd = response.headers.get("content-disposition", "")
    assert "attachment" in cd
    assert ".pdf" in cd


@pytest.mark.asyncio
async def test_health_report_requires_auth(client: AsyncClient):
    """POST /api/prescriptions/health-report without auth returns 401."""
    response = await client.post(
        "/api/prescriptions/health-report",
        json={},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_health_report_404_invalid_member(client: AsyncClient, auth_headers: dict):
    """Health report with invalid member_id returns 404."""
    response = await client.post(
        "/api/prescriptions/health-report",
        json={"member_id": "nonexistent-member"},
        headers=auth_headers,
    )
    assert response.status_code == 404
    assert "未找到该成员" in response.json()["detail"]


@pytest.mark.asyncio
async def test_health_report_with_member(client: AsyncClient, auth_headers: dict):
    """Health report works when a valid family member exists."""
    # First create a family member
    create_resp = await client.post(
        "/api/family-members",
        json={"name": "王阿姨", "relation": "母亲", "gender": "女"},
        headers=auth_headers,
    )
    assert create_resp.status_code == 201
    member_id = create_resp.json()["id"]

    # Then generate health report for that member
    response = await client.post(
        "/api/prescriptions/health-report",
        json={"member_id": member_id, "report_type": "summary"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content[:4] == b"%PDF"


# ---------------------------------------------------------------------------
# PDF generator unit tests (direct function calls)
# ---------------------------------------------------------------------------

def test_pdf_generator_prescription_basic():
    """generate_prescription_pdf produces valid PDF bytes from formula dict."""
    from app.pdf_generator import generate_prescription_pdf

    formula = {
        "name": "四君子汤",
        "source": "《太平惠民和剂局方》",
        "category": "补益剂",
        "efficacy": "益气健脾",
        "indications": "脾胃气虚证",
        "composition": [
            {"name": "人参", "dose": "9g", "role": "君"},
            {"name": "白术", "dose": "9g", "role": "臣"},
            {"name": "茯苓", "dose": "9g", "role": "佐"},
            {"name": "甘草", "dose": "6g", "role": "使"},
        ],
        "properties": {},
    }
    pdf = generate_prescription_pdf(
        formula=formula,
        patient_name="测试患者",
        patient_gender="男",
        patient_age="50",
        prescriber="张医生",
        notes="忌辛辣",
    )
    assert isinstance(pdf, bytes)
    assert pdf[:4] == b"%PDF"
    assert b"%%EOF" in pdf[-1024:]


def test_pdf_generator_health_report_basic():
    """generate_health_report_pdf produces valid PDF bytes."""
    from app.pdf_generator import generate_health_report_pdf

    pdf = generate_health_report_pdf(
        member={"name": "测试", "gender": "男"},
        profile={"constitution_type": "气虚质"},
        constitution={"primary_type": "气虚质"},
        medicines=[{"name": "参苓白术散", "type": "中成药", "specification": "6g/袋", "quantity": 20}],
        reminders=[{"title": "早服参苓白术散", "times": ["07:00"], "dosage": "6g", "enabled": 1}],
    )
    assert isinstance(pdf, bytes)
    assert pdf[:4] == b"%PDF"
    assert b"%%EOF" in pdf[-1024:]


def test_pdf_generator_empty_formula():
    """PDF generation handles empty/minimal formula gracefully."""
    from app.pdf_generator import generate_prescription_pdf

    pdf = generate_prescription_pdf(formula={"name": "测试方"})
    assert pdf[:4] == b"%PDF"


# ---------------------------------------------------------------------------
# PDF content correctness — verify rendered text, not just the file header
# (audit gap P1.3). Uses PyMuPDF to extract Chinese text from the CID font.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pdf_contains_formula_name_and_herbs(
    client: AsyncClient, auth_headers: dict
):
    """The generated prescription PDF must contain the formula name and its herb names.

    formula-001 (四君子汤) composition: 人参, 白术, 茯苓, 甘草. Extracting the
    PDF text confirms these are actually rendered — not just that bytes exist.
    """
    response = await client.post(
        "/api/prescriptions/generate",
        json={
            "formula_id": "formula-001",
            "patient_name": "张三",
            "patient_gender": "男",
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    text = _extract_pdf_text(response.content)
    assert "四君子汤" in text
    for herb in ("人参", "白术", "茯苓", "甘草"):
        assert herb in text, f"herb {herb} missing from prescription PDF text"


@pytest.mark.asyncio
async def test_pdf_contains_disclaimer(client: AsyncClient, auth_headers: dict):
    """Every prescription PDF must carry a disclaimer (仅供参考 / 咨询)."""
    response = await client.post(
        "/api/prescriptions/generate",
        json={"formula_id": "formula-001"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    text = _extract_pdf_text(response.content)
    assert "仅供参考" in text or "咨询" in text, (
        "prescription PDF missing required disclaimer text"
    )
