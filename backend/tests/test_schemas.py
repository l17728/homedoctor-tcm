"""Tests for schemas endpoints: list, detail, field validation."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_schemas(client: AsyncClient, auth_headers: dict[str, str]):
    """GET /api/schemas returns list of available schema types."""
    response = await client.get("/api/schemas", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    types = [s["nodeType"] for s in data["items"]]
    assert "herb" in types
    assert "medicine" in types
    assert "formula" in types


@pytest.mark.asyncio
async def test_get_herb_schema(client: AsyncClient, auth_headers: dict[str, str]):
    """GET /api/schemas/herb returns herb schema with fields."""
    response = await client.get("/api/schemas/herb", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["nodeType"] == "herb"
    assert data["label"] == "中药"
    assert len(data["fields"]) > 0

    # Verify essential fields exist
    field_names = [f["name"] for f in data["fields"]]
    assert "name" in field_names
    assert "nature" in field_names
    assert "efficacy" in field_names
    assert "dosage_min_g" in field_names


@pytest.mark.asyncio
async def test_get_medicine_schema(client: AsyncClient, auth_headers: dict[str, str]):
    """GET /api/schemas/medicine returns medicine schema."""
    response = await client.get("/api/schemas/medicine", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["nodeType"] == "medicine"
    assert data["label"] == "药品"
    assert len(data["fields"]) > 0

    field_names = [f["name"] for f in data["fields"]]
    assert "name" in field_names
    assert "type" in field_names
    assert "quantity" in field_names
    assert "expiry_date" in field_names


@pytest.mark.asyncio
async def test_get_formula_schema(client: AsyncClient, auth_headers: dict[str, str]):
    """GET /api/schemas/formula returns formula schema."""
    response = await client.get("/api/schemas/formula", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["nodeType"] == "formula"
    assert data["label"] == "方剂"
    assert len(data["fields"]) > 0

    field_names = [f["name"] for f in data["fields"]]
    assert "name" in field_names
    assert "category" in field_names
    assert "efficacy" in field_names


@pytest.mark.asyncio
async def test_get_schema_not_found(client: AsyncClient, auth_headers: dict[str, str]):
    """GET /api/schemas/nonexistent returns 404."""
    response = await client.get("/api/schemas/nonexistent", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_schema_fields_have_correct_types(client: AsyncClient, auth_headers: dict[str, str]):
    """Schema fields have correct type values matching SchemaFieldType."""
    response = await client.get("/api/schemas/herb", headers=auth_headers)
    assert response.status_code == 200
    fields = response.json()["fields"]

    valid_types = {"string", "number", "enum", "boolean", "date", "text"}
    for field in fields:
        assert field["type"] in valid_types, f"Field {field['name']} has invalid type: {field['type']}"

    # Verify specific field types
    field_map = {f["name"]: f for f in fields}
    assert field_map["name"]["type"] == "string"
    assert field_map["nature"]["type"] == "enum"
    assert field_map["efficacy"]["type"] == "text"
    assert field_map["dosage_min_g"]["type"] == "number"


@pytest.mark.asyncio
async def test_required_fields_marked(client: AsyncClient, auth_headers: dict[str, str]):
    """Required fields have required=true in schema."""
    response = await client.get("/api/schemas/herb", headers=auth_headers)
    assert response.status_code == 200
    fields = response.json()["fields"]

    field_map = {f["name"]: f for f in fields}

    # name should be required
    assert field_map["name"]["required"] is True

    # Find at least one non-required field
    non_required = [f for f in fields if not f["required"]]
    assert len(non_required) > 0, "Expected at least one non-required field"


@pytest.mark.asyncio
async def test_enum_fields_have_values(client: AsyncClient, auth_headers: dict[str, str]):
    """Enum fields have enumValues populated."""
    response = await client.get("/api/schemas/herb", headers=auth_headers)
    assert response.status_code == 200
    fields = response.json()["fields"]

    field_map = {f["name"]: f for f in fields}
    nature_field = field_map["nature"]
    assert nature_field["type"] == "enum"
    assert "enumValues" in nature_field
    assert "寒" in nature_field["enumValues"]
    assert "热" in nature_field["enumValues"]
    assert "温" in nature_field["enumValues"]
    assert "凉" in nature_field["enumValues"]
    assert "平" in nature_field["enumValues"]


@pytest.mark.asyncio
async def test_fields_have_groups(client: AsyncClient, auth_headers: dict[str, str]):
    """All fields have a group for panel grouping."""
    response = await client.get("/api/schemas/herb", headers=auth_headers)
    assert response.status_code == 200
    fields = response.json()["fields"]

    groups = {f["group"] for f in fields}
    assert "基本信息" in groups
    assert "性味归经" in groups
    assert "功效主治" in groups
    assert "用药信息" in groups


@pytest.mark.asyncio
async def test_medicine_enum_fields(client: AsyncClient, auth_headers: dict[str, str]):
    """Medicine schema enum fields have Chinese enum values."""
    response = await client.get("/api/schemas/medicine", headers=auth_headers)
    assert response.status_code == 200
    fields = response.json()["fields"]

    field_map = {f["name"]: f for f in fields}
    type_field = field_map["type"]
    assert type_field["type"] == "enum"
    assert "西药" in type_field["enumValues"]
    assert "中药" in type_field["enumValues"]
    assert "中成药" in type_field["enumValues"]

    unit_field = field_map["unit"]
    assert unit_field["type"] == "enum"
    assert "盒" in unit_field["enumValues"]
    assert "瓶" in unit_field["enumValues"]


@pytest.mark.asyncio
async def test_formula_enum_fields(client: AsyncClient, auth_headers: dict[str, str]):
    """Formula schema category is an enum with Chinese values."""
    response = await client.get("/api/schemas/formula", headers=auth_headers)
    assert response.status_code == 200
    fields = response.json()["fields"]

    field_map = {f["name"]: f for f in fields}
    category_field = field_map["category"]
    assert category_field["type"] == "enum"
    assert "解表剂" in category_field["enumValues"]
    assert "补益剂" in category_field["enumValues"]
    assert "清热剂" in category_field["enumValues"]
