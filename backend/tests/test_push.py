"""Web Push configuration, persistence isolation, and endpoint validation."""

import json

import pytest


@pytest.mark.asyncio
async def test_push_config_exposes_public_key_only(client, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "PUSH_VAPID_PUBLIC_KEY", "public-key")
    monkeypatch.setattr(settings, "PUSH_VAPID_PRIVATE_KEY", "private-secret")
    response = await client.get("/api/push/config")
    assert response.status_code == 200
    assert response.json() == {"enabled": True, "public_key": "public-key"}
    assert "private" not in response.text


@pytest.mark.asyncio
async def test_push_subscription_is_user_scoped_and_unsubscribe_removes_it(
    client, db, auth_headers, monkeypatch
):
    from app.config import settings
    monkeypatch.setattr(settings, "PUSH_VAPID_PUBLIC_KEY", "test-public")
    monkeypatch.setattr(settings, "PUSH_VAPID_PRIVATE_KEY", "test-private")
    monkeypatch.setattr("app.routers.push.validate_external_url", lambda _: True)
    body = {
        "endpoint": "https://push.example.invalid/subscription/id",
        "keys": {"p256dh": "p" * 40, "auth": "a" * 16},
    }
    subscribed = await client.post("/api/push/subscriptions", json=body, headers=auth_headers)
    assert subscribed.status_code == 201
    user = await db.query_one("SELECT settings FROM users WHERE username = 'testuser'")
    settings_value = json.loads(user["settings"])
    assert settings_value["push_subscriptions"][0]["endpoint"] == body["endpoint"]

    removed = await client.request(
        "DELETE", "/api/push/subscriptions", json={"endpoint": body["endpoint"]}, headers=auth_headers
    )
    assert removed.status_code == 200
    updated = await db.query_one("SELECT settings FROM users WHERE username = 'testuser'")
    assert json.loads(updated["settings"])["push_subscriptions"] == []


@pytest.mark.asyncio
async def test_push_rejects_private_http_and_nondefault_port(client, auth_headers, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "PUSH_VAPID_PUBLIC_KEY", "test-public")
    monkeypatch.setattr(settings, "PUSH_VAPID_PRIVATE_KEY", "test-private")
    monkeypatch.setattr("app.routers.push.validate_external_url", lambda _: False)
    for endpoint in ("http://127.0.0.1/sub", "https://push.example.invalid:8443/sub"):
        response = await client.post("/api/push/subscriptions", json={
            "endpoint": endpoint,
            "keys": {"p256dh": "p" * 40, "auth": "a" * 16},
        }, headers=auth_headers)
        assert response.status_code in (422, 503)


@pytest.mark.asyncio
async def test_push_subscribe_requires_auth(raw_client):
    response = await raw_client.post("/api/push/subscriptions", json={})
    assert response.status_code in (401, 403)


def test_vapid_private_pem_converts_to_library_raw_format():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from app.push_service import _vapid_raw_private_key
    from py_vapid import Vapid

    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")
    encoded = _vapid_raw_private_key(pem)
    parsed = Vapid.from_string(encoded)
    assert parsed._private_key.private_numbers().private_value == key.private_numbers().private_value
