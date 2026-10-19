"""Tests for medicines CRUD endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_medicine(client: AsyncClient, auth_headers: dict):
    """POST /api/medicines creates a new medicine."""
    response = await client.post("/api/medicines", headers=auth_headers, json={
        "name": "布洛芬",
        "type": "western",
        "specification": "0.2g×20粒/盒",
        "unit": "粒",
        "quantity": 20,
        "barcode": "4006381333931",
        "dosage_instructions": "每次1-2粒，每日3次",
    })
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "布洛芬"
    assert data["type"] == "western"
    assert data["quantity"] == 20
    assert data["barcode"] == "4006381333931"
    assert "id" in data


@pytest.mark.asyncio
async def test_list_medicines(client: AsyncClient, auth_headers: dict):
    """GET /api/medicines returns user's medicines."""
    # Create first
    await client.post("/api/medicines", headers=auth_headers, json={
        "name": "阿莫西林",
        "type": "western",
    })
    # List
    response = await client.get("/api/medicines", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert any(m["name"] == "阿莫西林" for m in data["items"])


@pytest.mark.asyncio
async def test_get_medicine_detail(client: AsyncClient, auth_headers: dict):
    """GET /api/medicines/{id} returns medicine detail."""
    # Create
    create_resp = await client.post("/api/medicines", headers=auth_headers, json={
        "name": "维生素C",
        "type": "supplement",
        "quantity": 100,
    })
    medicine_id = create_resp.json()["id"]

    # Get
    response = await client.get(f"/api/medicines/{medicine_id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "维生素C"
    assert data["quantity"] == 100


@pytest.mark.asyncio
async def test_update_medicine(client: AsyncClient, auth_headers: dict):
    """PUT /api/medicines/{id} updates medicine."""
    # Create
    create_resp = await client.post("/api/medicines", headers=auth_headers, json={
        "name": "感冒灵",
        "type": "chinese_patent",
        "quantity": 10,
    })
    medicine_id = create_resp.json()["id"]

    # Update
    response = await client.put(
        f"/api/medicines/{medicine_id}",
        headers=auth_headers,
        json={"quantity": 5, "dosage_instructions": "每次1包，每日3次"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["quantity"] == 5
    assert data["dosage_instructions"] == "每次1包，每日3次"


@pytest.mark.asyncio
async def test_delete_medicine(client: AsyncClient, auth_headers: dict):
    """DELETE /api/medicines/{id} deletes medicine."""
    # Create
    create_resp = await client.post("/api/medicines", headers=auth_headers, json={
        "name": "板蓝根",
        "type": "chinese_patent",
    })
    medicine_id = create_resp.json()["id"]

    # Delete
    response = await client.delete(
        f"/api/medicines/{medicine_id}",
        headers=auth_headers,
    )
    assert response.status_code == 200

    # Verify deleted
    get_resp = await client.get(f"/api/medicines/{medicine_id}", headers=auth_headers)
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_medicines_require_auth(raw_client: AsyncClient):
    """GET /api/medicines without auth returns 401."""
    response = await raw_client.get("/api/medicines")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_tenant_isolation(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict
):
    """User A cannot see User B's medicines."""
    # User A creates medicine
    await client.post("/api/medicines", headers=auth_headers, json={
        "name": "用户A的药",
        "type": "western",
    })

    # User B should not see it
    response = await client.get("/api/medicines", headers=second_user_headers)
    assert response.status_code == 200
    data = response.json()
    names = [m["name"] for m in data["items"]]
    assert "用户A的药" not in names
