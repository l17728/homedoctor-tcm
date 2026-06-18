"""Security-focused input validation tests.

Verifies that potentially malicious / unusual user input is handled safely:
- SQL injection payloads do not break queries or leak data
- XSS payloads are stored faithfully (server does not execute/strip them;
  escaping is the frontend's job) and round-trip intact
- Emoji and special characters survive a write→read round-trip
- HTML in chat messages does not cause server errors

These are BLACK-BOX behavioural tests: they hit real endpoints and assert
the server neither crashes nor silently mutates the payload.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest
from httpx import AsyncClient

from app.database import DbAdapter

CST = timezone(timedelta(hours=8))


def _today_str() -> str:
    return datetime.now(CST).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# SQL injection — safety check endpoints
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_safety_check_sql_injection_herb_name(
    client: AsyncClient, auth_headers: dict
):
    """A classic SQL-injection payload as a herb name must not break /safety/check-v2.

    The endpoint must return a normal 200 response (not 500), and the payload
    must not cause the safety_rules table to leak unrelated rules.
    """
    payload = "黄芪'; DROP TABLE safety_rules; --"
    response = await client.post(
        "/api/safety/check-v2",
        headers=auth_headers,
        json={"herbs": [payload], "medicines": []},
    )
    # Must NOT be a 500 (server crash) — parameterised queries prevent injection
    assert response.status_code == 200
    data = response.json()
    # The injected "herb" is unknown → listed in unknown_herbs
    assert payload in data.get("unknown_herbs", [])
    # No real safety warnings should fire for a non-existent herb
    assert data["warnings"] == []
    # The safety_rules table must still exist & be queryable afterwards
    resp2 = await client.post(
        "/api/safety/check-v2",
        headers=auth_headers,
        json={"herbs": ["甘草"], "medicines": []},
    )
    assert resp2.status_code == 200


@pytest.mark.asyncio
async def test_safety_check_sql_injection_medicine_name(
    client: AsyncClient, auth_headers: dict
):
    """SQL-injection in medicine name must not leak safety rules or crash."""
    payload = "阿司匹林' OR '1'='1"
    response = await client.post(
        "/api/safety/check-v2",
        headers=auth_headers,
        json={"herbs": ["当归"], "medicines": [payload]},
    )
    assert response.status_code == 200
    data = response.json()
    # The injected medicine is unknown → no interaction rules should match it.
    # Crucially, the "' OR '1'='1" must NOT cause every rule to match.
    for w in data["warnings"]:
        # No warning should reference the injection payload as a real drug
        assert payload not in w.get("detail", "")
    # unknown_medicines should contain the payload (it's not a real medicine)
    assert payload in data.get("unknown_medicines", [])


# ---------------------------------------------------------------------------
# XSS — classics annotation stores payload faithfully
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_classics_annotation_xss(
    client: AsyncClient, auth_headers: dict, db: DbAdapter
):
    """A <script> tag in an annotation's content is stored verbatim, not executed.

    The server is a JSON API — it must never execute HTML/JS. It should store
    the raw string and return it unchanged on read, leaving escaping to the
    frontend. This guards against accidental server-side stripping/injection.
    """
    # Seed a minimal classic + chapter so the annotation endpoint has a target.
    classic_id = "sec-test-classic"
    chapter_id = "sec-test-chapter"
    original_text = "上古天真论篇第一"  # 8 chars
    await db.execute(
        """INSERT OR IGNORE INTO classics
           (id, title, author, dynasty, category, description, cover_color, total_chapters)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (classic_id, "安全测试典籍", "佚名", "汉", "医经", "测试用", "#abc", 1),
    )
    await db.execute(
        """INSERT OR IGNORE INTO classic_chapters
           (id, classic_id, chapter_number, title, original_text, translation, translator_notes)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (chapter_id, classic_id, 1, "测试章节", original_text, None, None),
    )

    xss_payload = '<script>alert("xss")</script>'
    response = await client.post(
        f"/api/classics/{classic_id}/chapters/{chapter_id}/annotations",
        headers=auth_headers,
        json={
            "start_offset": 0,
            "end_offset": 2,
            "selected_text": "上古",
            "content": xss_payload,
            "note_type": "annotation",
        },
    )
    assert response.status_code == 201
    created = response.json()
    # The payload must be stored verbatim (no execution, no stripping)
    assert created["content"] == xss_payload
    ann_id = created["id"]

    # Read it back — must still be the verbatim payload
    get_resp = await client.get(
        f"/api/classics/{classic_id}/chapters/{chapter_id}/annotations",
        headers=auth_headers,
    )
    assert get_resp.status_code == 200
    items = get_resp.json()["items"]
    matched = [a for a in items if a["id"] == ann_id]
    assert len(matched) == 1
    assert matched[0]["content"] == xss_payload


# ---------------------------------------------------------------------------
# Emoji round-trip — medicine name
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_medicine_name_with_emoji(client: AsyncClient, auth_headers: dict):
    """Emoji in a medicine name round-trips correctly through create→get."""
    emoji_name = "维生素C片💊每日服用"
    create_resp = await client.post(
        "/api/medicines",
        headers=auth_headers,
        json={"name": emoji_name, "type": "supplement", "quantity": 30},
    )
    assert create_resp.status_code == 201
    med_id = create_resp.json()["id"]
    assert create_resp.json()["name"] == emoji_name

    # Read back
    get_resp = await client.get(f"/api/medicines/{med_id}", headers=auth_headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == emoji_name

    # Also visible in the list
    list_resp = await client.get("/api/medicines", headers=auth_headers)
    assert list_resp.status_code == 200
    names = [m["name"] for m in list_resp.json()["items"]]
    assert emoji_name in names


# ---------------------------------------------------------------------------
# SQL chars in reminder title — stored safely
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reminder_title_with_sql_chars(client: AsyncClient, auth_headers: dict):
    """Quotes / semicolons / comment markers in a reminder title are stored safely."""
    tricky_title = "服用'; DROP TABLE reminders; -- \"抗氧化\"药"
    response = await client.post(
        "/api/reminders",
        headers=auth_headers,
        json={
            "title": tricky_title,
            "frequency": "daily",
            "times": ["08:00"],
            "start_date": _today_str(),
        },
    )
    assert response.status_code == 201
    data = response.json()
    # Title must be stored verbatim (parameterised query neutralises the payload)
    assert data["title"] == tricky_title
    rem_id = data["id"]

    # The reminders table must still be intact and queryable
    list_resp = await client.get("/api/reminders", headers=auth_headers)
    assert list_resp.status_code == 200
    titles = [r["title"] for r in list_resp.json()["items"]]
    assert tricky_title in titles

    # Individual fetch also returns the verbatim title
    one_resp = await client.get(f"/api/reminders/{rem_id}", headers=auth_headers)
    assert one_resp.status_code == 200
    assert one_resp.json()["title"] == tricky_title


# ---------------------------------------------------------------------------
# HTML tags in chat message — no server error
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chat_message_with_html_tags(client: AsyncClient, auth_headers: dict):
    """HTML tags in a chat message must not cause a server error.

    The message is echoed back inside the mock reply; the server must not
    attempt to parse or execute the HTML.
    """
    html_message = '<b>黄芪</b>有什么功效？<img src=x onerror=alert(1)>'
    response = await client.post(
        "/api/chat",
        headers=auth_headers,
        json={"message": html_message, "history": []},
    )
    assert response.status_code == 200
    data = response.json()
    # The reply must be a plain string (mock reply echoes the message)
    assert isinstance(data["reply"], str)
    # The raw HTML payload should appear verbatim in the echoed message
    # (mock reply format: 收到您的咨询：「{message}」)
    assert html_message in data["reply"]
    # No safety warning triggered (HTML is not an emergency keyword)
    assert data["safety_warning"] is None
