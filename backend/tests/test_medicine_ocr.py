"""Tests for medicine OCR endpoints — 拍照识别药品 + 条形码校验 (spec §16.2 P1)."""

import io
import shutil

import pytest
from httpx import AsyncClient

from app.routers.medicine_ocr import (
    _parse_dosage_instructions,
    _parse_medicine_name,
    _parse_specification,
    _validate_ean13,
    _validate_ean8,
    _compute_confidence,
)


# ===========================================================================
# Unit tests: text parsing functions
# ===========================================================================

class TestParseMedicineName:
    def test_tablet(self):
        name, dtype = _parse_medicine_name("感冒清热片 每次2片 每日3次")
        assert name == "感冒清热片"
        assert dtype == "片剂"

    def test_capsule(self):
        name, dtype = _parse_medicine_name("藿香正气胶囊 0.3g")
        assert name == "藿香正气胶囊"
        assert dtype == "胶囊剂"

    def test_pill(self):
        name, dtype = _parse_medicine_name("六味地黄丸")
        assert name == "六味地黄丸"
        assert dtype == "丸剂"

    def test_granule(self):
        name, dtype = _parse_medicine_name("感冒清热颗粒")
        assert name == "感冒清热颗粒"
        assert dtype == "颗粒剂"

    def test_oral_liquid(self):
        name, dtype = _parse_medicine_name("蓝芩口服液")
        assert name == "蓝芩口服液"
        assert dtype == "口服液"

    def test_no_match(self):
        name, dtype = _parse_medicine_name("just some random text")
        assert name is None
        assert dtype is None


class TestParseSpecification:
    def test_grams(self):
        assert _parse_specification("规格：0.25g") == "0.25g"

    def test_milligrams(self):
        assert _parse_specification("10mg per tablet") == "10mg"

    def test_ml(self):
        result = _parse_specification("100ml bottle")
        assert result is not None
        assert "100ml" in result

    def test_with_count(self):
        result = _parse_specification("0.5g×24片")
        assert result is not None
        assert "0.5g" in result

    def test_no_match(self):
        assert _parse_specification("no spec here") is None


class TestParseDosageInstructions:
    def test_daily_frequency(self):
        result = _parse_dosage_instructions("每日3次 饭后服用")
        assert result is not None
        assert "每日3次" in result

    def test_per_dose(self):
        result = _parse_dosage_instructions("每次2片 温水送服")
        assert result is not None
        assert "每次2片" in result

    def test_combined(self):
        result = _parse_dosage_instructions("每日3次 每次2片")
        assert result is not None
        assert "每日3次" in result

    def test_no_match(self):
        assert _parse_dosage_instructions("no dosage info") is None


class TestComputeConfidence:
    def test_high(self):
        conf = _compute_confidence("感冒片", "片剂", "0.25g", "每日3次", 100)
        assert conf == "high"

    def test_low_short_text(self):
        conf = _compute_confidence("name", None, None, None, 5)
        assert conf == "low"

    def test_medium(self):
        conf = _compute_confidence("name", "片剂", None, None, 50)
        assert conf == "medium"


# ===========================================================================
# Unit tests: barcode validation
# ===========================================================================

class TestEAN13Validation:
    def test_valid_ean13(self):
        assert _validate_ean13("4006381333931") is True

    def test_invalid_ean13(self):
        assert _validate_ean13("4006381333932") is False

    def test_wrong_length(self):
        assert _validate_ean13("123") is False

    def test_non_digit(self):
        assert _validate_ean13("400638133393a") is False


class TestEAN8Validation:
    def test_valid_ean8(self):
        assert _validate_ean8("73513537") is True

    def test_invalid_ean8(self):
        assert _validate_ean8("73513530") is False

    def test_wrong_length(self):
        assert _validate_ean8("123") is False


# ===========================================================================
# Integration tests: POST /api/medicines/barcode-lookup
# ===========================================================================

@pytest.mark.asyncio
async def test_barcode_lookup_valid_ean13(client: AsyncClient, auth_headers: dict):
    """Valid EAN-13 barcode → valid=True."""
    resp = await client.post("/api/medicines/barcode-lookup", json={
        "barcode": "4006381333931",
    }, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is True
    assert data["barcode"] == "4006381333931"
    assert data["format"] == "EAN-13"


@pytest.mark.asyncio
async def test_barcode_lookup_valid_ean8(client: AsyncClient, auth_headers: dict):
    """Valid EAN-8 barcode → valid=True."""
    resp = await client.post("/api/medicines/barcode-lookup", json={
        "barcode": "73513537",
    }, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is True
    assert data["format"] == "EAN-8"


@pytest.mark.asyncio
async def test_barcode_lookup_invalid_checksum(client: AsyncClient, auth_headers: dict):
    """Invalid checksum → valid=False."""
    resp = await client.post("/api/medicines/barcode-lookup", json={
        "barcode": "4006381333932",
    }, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is False


@pytest.mark.asyncio
async def test_barcode_lookup_wrong_length(client: AsyncClient, auth_headers: dict):
    """Wrong length → valid=False."""
    resp = await client.post("/api/medicines/barcode-lookup", json={
        "barcode": "12345",
    }, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is False


@pytest.mark.asyncio
async def test_barcode_lookup_non_digit(client: AsyncClient, auth_headers: dict):
    """Non-digit barcode → valid=False."""
    resp = await client.post("/api/medicines/barcode-lookup", json={
        "barcode": "abc123",
    }, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["valid"] is False


@pytest.mark.asyncio
async def test_barcode_lookup_missing_field(client: AsyncClient, auth_headers: dict):
    """Missing barcode → 422."""
    resp = await client.post("/api/medicines/barcode-lookup", json={}, headers=auth_headers)
    assert resp.status_code == 422


# ===========================================================================
# Integration tests: POST /api/medicines/ocr-recognize
# ===========================================================================

@pytest.fixture
def sample_image_bytes() -> bytes:
    """Render a minimal PNG with ASCII text for OCR."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        pytest.skip("Pillow not available")
    img = Image.new("RGB", (400, 120), color="white")
    draw = ImageDraw.Draw(img)
    draw.text((10, 50), "Dosage 0.25g 10mg", fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.asyncio
async def test_ocr_recognize_accepts_image(client: AsyncClient, auth_headers: dict, sample_image_bytes):
    """OCR endpoint accepts an image and returns a response with confidence."""
    files = {"file": ("test.png", sample_image_bytes, "image/png")}
    resp = await client.post(
        "/api/medicines/ocr-recognize", files=files, headers=auth_headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "confidence" in data
    assert "raw_text" in data
    assert data["confidence"] in ("high", "medium", "low")


@pytest.mark.asyncio
async def test_ocr_recognize_unsupported_format(client: AsyncClient, auth_headers: dict):
    """Non-image file → 422."""
    files = {"file": ("test.txt", b"some text", "text/plain")}
    resp = await client.post(
        "/api/medicines/ocr-recognize", files=files, headers=auth_headers
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_ocr_recognize_requires_auth(client: AsyncClient, sample_image_bytes):
    """No auth → 401/403."""
    files = {"file": ("test.png", sample_image_bytes, "image/png")}
    resp = await client.post("/api/medicines/ocr-recognize", files=files)
    assert resp.status_code in (401, 403)
