"""Tests for classics (经典读诵) endpoints — TCM bookshelf + annotations + AI Q&A.

The LLM calls are mocked via ``monkeypatch`` to ensure deterministic results.
"""

from __future__ import annotations

import sys
import os
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import AsyncClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from scripts.seed_classics import CLASSICS_SEED  # noqa: E402

from app.database import DbAdapter  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures — seed classics into the test DB
# ---------------------------------------------------------------------------

async def _seed_classics(db: DbAdapter) -> None:
    for classic in CLASSICS_SEED:
        await db.execute(
            """INSERT OR IGNORE INTO classics
               (id, title, author, dynasty, category, description,
                cover_color, total_chapters)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                classic["id"], classic["title"], classic.get("author"),
                classic.get("dynasty"), classic.get("category"),
                classic.get("description"), classic.get("cover_color", "#1890ff"),
                len(classic["chapters"]),
            ),
        )
        for ch in classic["chapters"]:
            await db.execute(
                """INSERT OR IGNORE INTO classic_chapters
                   (id, classic_id, chapter_number, title, original_text,
                    translation, translator_notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    ch["id"], classic["id"], ch["chapter_number"], ch["title"],
                    ch["original_text"], ch.get("translation"),
                    ch.get("translator_notes"),
                ),
            )


@pytest_asyncio.fixture(autouse=True)
async def _seed_classics_data(db: DbAdapter):
    await _seed_classics(db)
    yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CLASSIC_ID = "classic-hdnj-suwen"
CHAPTER_ID = "hdnj-ch1"


def _mock_llm(reply: str):
    m = AsyncMock()
    m.return_value = reply
    return m


# ---------------------------------------------------------------------------
# Bookshelf
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_classics_returns_5_plus(client: AsyncClient):
    """GET /api/classics returns all 5+ classics (no auth needed)."""
    resp = await client.get("/api/classics")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 5
    titles = [c["title"] for c in data["items"]]
    assert "黄帝内经·素问" in titles
    assert "伤寒论" in titles


@pytest.mark.asyncio
async def test_list_classics_filter_by_category(client: AsyncClient):
    """GET /api/classics?category=医经 filters by category."""
    resp = await client.get("/api/classics?category=医经")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    for c in data["items"]:
        assert c["category"] == "医经"


@pytest.mark.asyncio
async def test_get_classic_detail_with_chapters(client: AsyncClient):
    """GET /api/classics/{id} returns classic detail with chapter list."""
    resp = await client.get(f"/api/classics/{CLASSIC_ID}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "黄帝内经·素问"
    assert data["author"] == "黄帝、岐伯"
    assert data["dynasty"] == "战国"
    assert len(data["chapters"]) == 3
    assert data["chapters"][0]["title"] == "上古天真论篇第一"
    assert data["chapters"][0]["chapter_number"] == 1
    assert data["chapters"][0]["text_length"] > 0


@pytest.mark.asyncio
async def test_get_classic_not_found(client: AsyncClient):
    """GET /api/classics/{invalid_id} returns 404."""
    resp = await client.get("/api/classics/nonexistent-classic")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Chapter reading
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_chapter_returns_text(client: AsyncClient, auth_headers: dict):
    """GET chapter returns original text + classic title."""
    resp = await client.get(
        f"/api/classics/{CLASSIC_ID}/chapters/{CHAPTER_ID}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "上古天真论篇第一"
    assert "上古之人" in data["original_text"]
    assert data["classic_title"] == "黄帝内经·素问"
    assert "annotations" in data
    assert isinstance(data["annotations"], list)


@pytest.mark.asyncio
async def test_get_chapter_not_found(client: AsyncClient, auth_headers: dict):
    """GET nonexistent chapter returns 404."""
    resp = await client.get(
        f"/api/classics/{CLASSIC_ID}/chapters/nonexistent-chapter",
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_chapter_requires_auth(raw_client: AsyncClient):
    """GET chapter without auth returns 401/403."""
    resp = await raw_client.get(
        f"/api/classics/{CLASSIC_ID}/chapters/{CHAPTER_ID}"
    )
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Annotations CRUD
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_annotation(client: AsyncClient, auth_headers: dict):
    """POST annotation creates an annotation (auth required)."""
    resp = await client.post(
        f"/api/classics/{CLASSIC_ID}/chapters/{CHAPTER_ID}/annotations",
        json={
            "start_offset": 0,
            "end_offset": 10,
            "selected_text": "昔在黄帝，生而神灵",
            "content": "此句开宗明义，言黄帝天生神异。",
            "note_type": "annotation",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["selected_text"] == "昔在黄帝，生而神灵"
    assert data["content"] == "此句开宗明义，言黄帝天生神异。"
    assert data["note_type"] == "annotation"
    assert data["id"]


@pytest.mark.asyncio
async def test_create_annotation_invalid_offset(client: AsyncClient, auth_headers: dict):
    """POST annotation with invalid offsets is rejected."""
    resp = await client.post(
        f"/api/classics/{CLASSIC_ID}/chapters/{CHAPTER_ID}/annotations",
        json={
            "start_offset": 99999,
            "end_offset": 99998,
            "selected_text": "x",
            "content": "x",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_annotation_invalid_note_type(
    client: AsyncClient, auth_headers: dict
):
    """POST annotation with invalid note_type is rejected."""
    resp = await client.post(
        f"/api/classics/{CLASSIC_ID}/chapters/{CHAPTER_ID}/annotations",
        json={
            "start_offset": 0,
            "end_offset": 5,
            "selected_text": "昔在黄帝",
            "content": "x",
            "note_type": "invalid_type",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_annotation_requires_auth(raw_client: AsyncClient):
    """POST annotation without auth returns 401/403."""
    resp = await raw_client.post(
        f"/api/classics/{CLASSIC_ID}/chapters/{CHAPTER_ID}/annotations",
        json={
            "start_offset": 0, "end_offset": 5,
            "selected_text": "x", "content": "x",
        },
    )
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_update_annotation(client: AsyncClient, auth_headers: dict):
    """PUT annotation updates content."""
    create = await client.post(
        f"/api/classics/{CLASSIC_ID}/chapters/{CHAPTER_ID}/annotations",
        json={
            "start_offset": 0, "end_offset": 10,
            "selected_text": "昔在黄帝，生而神灵",
            "content": "原始批注",
        },
        headers=auth_headers,
    )
    ann_id = create.json()["id"]

    resp = await client.put(
        f"/api/classics/annotations/{ann_id}",
        json={"content": "更新后的批注"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["content"] == "更新后的批注"


@pytest.mark.asyncio
async def test_delete_annotation(client: AsyncClient, auth_headers: dict):
    """DELETE annotation removes it."""
    create = await client.post(
        f"/api/classics/{CLASSIC_ID}/chapters/{CHAPTER_ID}/annotations",
        json={
            "start_offset": 0, "end_offset": 5,
            "selected_text": "昔在黄帝",
            "content": "待删除",
        },
        headers=auth_headers,
    )
    ann_id = create.json()["id"]

    resp = await client.delete(
        f"/api/classics/annotations/{ann_id}", headers=auth_headers
    )
    assert resp.status_code == 200

    resp = await client.get(
        f"/api/classics/{CLASSIC_ID}/chapters/{CHAPTER_ID}/annotations",
        headers=auth_headers,
    )
    items = resp.json()["items"]
    assert all(a["id"] != ann_id for a in items)


@pytest.mark.asyncio
async def test_delete_annotation_not_found(client: AsyncClient, auth_headers: dict):
    """DELETE nonexistent annotation returns 404."""
    resp = await client.delete(
        "/api/classics/annotations/nonexistent-id", headers=auth_headers
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_annotations_by_chapter(client: AsyncClient, auth_headers: dict):
    """GET annotations for a chapter returns user's annotations sorted by offset."""
    for i, (start, end, text) in enumerate([
        (10, 20, "弱而能言"),
        (0, 5, "昔在黄帝"),
        (30, 40, "成而登天"),
    ]):
        await client.post(
            f"/api/classics/{CLASSIC_ID}/chapters/{CHAPTER_ID}/annotations",
            json={
                "start_offset": start, "end_offset": end,
                "selected_text": text, "content": f"批注{i}",
            },
            headers=auth_headers,
        )

    resp = await client.get(
        f"/api/classics/{CLASSIC_ID}/chapters/{CHAPTER_ID}/annotations",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    offsets = [a["start_offset"] for a in data["items"]]
    assert offsets == sorted(offsets)
    assert offsets[0] == 0


@pytest.mark.asyncio
async def test_list_annotations_filter_note_type(
    client: AsyncClient, auth_headers: dict
):
    """GET annotations?note_type=qa_card filters by type."""
    await client.post(
        f"/api/classics/{CLASSIC_ID}/chapters/{CHAPTER_ID}/annotations",
        json={
            "start_offset": 0, "end_offset": 5,
            "selected_text": "昔在黄帝", "content": "普通批注",
            "note_type": "annotation",
        },
        headers=auth_headers,
    )
    await client.post(
        f"/api/classics/{CLASSIC_ID}/chapters/{CHAPTER_ID}/annotations",
        json={
            "start_offset": 10, "end_offset": 15,
            "selected_text": "弱而能言", "content": "QA卡",
            "note_type": "qa_card",
        },
        headers=auth_headers,
    )

    resp = await client.get(
        f"/api/classics/{CLASSIC_ID}/chapters/{CHAPTER_ID}/annotations?note_type=qa_card",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["note_type"] == "qa_card"


@pytest.mark.asyncio
async def test_annotation_user_isolation(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict
):
    """User A's annotations are invisible to User B."""
    await client.post(
        f"/api/classics/{CLASSIC_ID}/chapters/{CHAPTER_ID}/annotations",
        json={
            "start_offset": 0, "end_offset": 5,
            "selected_text": "昔在黄帝", "content": "用户A的批注",
        },
        headers=auth_headers,
    )
    resp = await client.get(
        f"/api/classics/{CLASSIC_ID}/chapters/{CHAPTER_ID}/annotations",
        headers=second_user_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


# ---------------------------------------------------------------------------
# Save translation (manual)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_save_translation(client: AsyncClient, auth_headers: dict):
    """PUT translation saves a manual/AI-reviewed translation."""
    resp = await client.put(
        f"/api/classics/{CLASSIC_ID}/chapters/{CHAPTER_ID}/translation",
        json={
            "translation": "从前有个黄帝，生下来就神异聪灵。",
            "translator_notes": "白话文翻译",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "从前有个黄帝" in data["translation"]
    assert data["translator_notes"] == "白话文翻译"


# ---------------------------------------------------------------------------
# AI Q&A (mocked)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ask_about_chapter_with_mock_llm(
    client: AsyncClient, auth_headers: dict, monkeypatch
):
    """POST ask sends proper prompt and returns AI answer."""
    captured_messages: list = []

    async def _fake_chat(messages, constitution=None):
        captured_messages.append(messages)
        return "「生而神灵」意指黄帝天性聪慧超凡。"

    monkeypatch.setattr("app.routers.classics.chat_completion", _fake_chat)
    monkeypatch.setattr("app.routers.classics.has_api_key", lambda: True)

    resp = await client.post(
        f"/api/classics/{CLASSIC_ID}/chapters/{CHAPTER_ID}/ask",
        json={
            "selected_text": "生而神灵",
            "question": "「生而神灵」是什么意思？",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "生而神灵" in data["answer"]
    assert data["model_used"]

    assert len(captured_messages) == 1
    prompt = captured_messages[0][0]["content"]
    assert "《黄帝内经·素问》" in prompt
    assert "上古天真论篇第一" in prompt
    assert "生而神灵" in prompt
    assert "请结合中医理论回答" in prompt


@pytest.mark.asyncio
async def test_ask_auto_save_qa_card(
    client: AsyncClient, auth_headers: dict, monkeypatch
):
    """POST ask with auto_save=true stores a qa_card annotation."""
    monkeypatch.setattr(
        "app.routers.classics.chat_completion",
        _mock_llm("这是AI的回答。"),
    )
    monkeypatch.setattr("app.routers.classics.has_api_key", lambda: True)

    resp = await client.post(
        f"/api/classics/{CLASSIC_ID}/chapters/{CHAPTER_ID}/ask",
        json={
            "selected_text": "昔在黄帝",
            "question": "黄帝是谁？",
            "auto_save": True,
            "start_offset": 0,
            "end_offset": 4,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["annotation_id"]

    listing = await client.get(
        f"/api/classics/{CLASSIC_ID}/chapters/{CHAPTER_ID}/annotations?note_type=qa_card",
        headers=auth_headers,
    )
    assert listing.json()["total"] == 1


@pytest.mark.asyncio
async def test_ask_missing_fields(client: AsyncClient, auth_headers: dict):
    """POST ask without required fields returns 422."""
    resp = await client.post(
        f"/api/classics/{CLASSIC_ID}/chapters/{CHAPTER_ID}/ask",
        json={"selected_text": "x"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# AI Translation (mocked)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_translate_chapter_with_mock_llm(
    client: AsyncClient, auth_headers: dict, monkeypatch
):
    """POST translate returns AI translation without auto-saving."""
    captured_messages: list = []

    async def _fake_chat(messages, constitution=None):
        captured_messages.append(messages)
        return "从前，黄帝生来神异聪灵……"

    monkeypatch.setattr("app.routers.classics.chat_completion", _fake_chat)
    monkeypatch.setattr("app.routers.classics.has_api_key", lambda: True)

    resp = await client.post(
        f"/api/classics/{CLASSIC_ID}/chapters/{CHAPTER_ID}/translate",
        json={},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "黄帝" in data["translation"]
    assert data["model_used"]

    prompt = captured_messages[0][0]["content"]
    assert "翻译为现代白话文" in prompt
    assert "中医术语准确" in prompt

    chapter = await client.get(
        f"/api/classics/{CLASSIC_ID}/chapters/{CHAPTER_ID}",
        headers=auth_headers,
    )
    assert chapter.json()["translation"] is None


@pytest.mark.asyncio
async def test_translate_requires_auth(raw_client: AsyncClient):
    """POST translate without auth returns 401/403."""
    resp = await raw_client.post(
        f"/api/classics/{CLASSIC_ID}/chapters/{CHAPTER_ID}/translate"
    )
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Study notes
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_save_and_load_study_notes(client: AsyncClient, auth_headers: dict):
    """PUT then GET study notes round-trips Markdown content."""
    save = await client.put(
        f"/api/classics/{CLASSIC_ID}/chapters/{CHAPTER_ID}/study-notes",
        json={"content": "# 学习笔记\n\n- 上古之人法于阴阳\n- 今时之人半百而衰"},
        headers=auth_headers,
    )
    assert save.status_code == 200
    assert "上古之人" in save.json()["content"]

    resp = await client.get(
        f"/api/classics/{CLASSIC_ID}/study-notes?chapter_id={CHAPTER_ID}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert "上古之人" in data["items"][0]["content"]


@pytest.mark.asyncio
async def test_study_notes_idempotent_update(
    client: AsyncClient, auth_headers: dict
):
    """Saving study notes twice for the same chapter updates in place."""
    for content in ("第一版", "第二版"):
        resp = await client.put(
            f"/api/classics/{CLASSIC_ID}/chapters/{CHAPTER_ID}/study-notes",
            json={"content": content},
            headers=auth_headers,
        )
        assert resp.status_code == 200

    listing = await client.get(
        f"/api/classics/{CLASSIC_ID}/study-notes",
        headers=auth_headers,
    )
    assert listing.json()["total"] == 1
    assert listing.json()["items"][0]["content"] == "第二版"


@pytest.mark.asyncio
async def test_study_notes_requires_auth(raw_client: AsyncClient):
    """GET/PUT study notes without auth returns 401/403."""
    r1 = await raw_client.get(f"/api/classics/{CLASSIC_ID}/study-notes")
    assert r1.status_code in (401, 403)
    r2 = await raw_client.put(
        f"/api/classics/{CLASSIC_ID}/chapters/{CHAPTER_ID}/study-notes",
        json={"content": "x"},
    )
    assert r2.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Summarize (mocked LLM)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_summarize_classic_with_mock_llm(
    client: AsyncClient, auth_headers: dict, monkeypatch
):
    """POST summarize aggregates annotations + QA cards into FAQ."""
    await client.post(
        f"/api/classics/{CLASSIC_ID}/chapters/{CHAPTER_ID}/annotations",
        json={
            "start_offset": 0, "end_offset": 5,
            "selected_text": "昔在黄帝", "content": "批注一",
            "note_type": "annotation",
        },
        headers=auth_headers,
    )
    await client.post(
        f"/api/classics/{CLASSIC_ID}/chapters/{CHAPTER_ID}/annotations",
        json={
            "start_offset": 10, "end_offset": 15,
            "selected_text": "弱而能言", "content": "Q: 黄帝为什么能言？ A: 神异。",
            "note_type": "qa_card",
        },
        headers=auth_headers,
    )

    monkeypatch.setattr(
        "app.routers.classics.chat_completion",
        _mock_llm("## FAQ\n\nQ1: 什么是「法于阴阳」？\nA: 遵循天地阴阳之道。"),
    )
    monkeypatch.setattr("app.routers.classics.has_api_key", lambda: True)

    resp = await client.post(
        f"/api/classics/{CLASSIC_ID}/summarize",
        json={"include_annotations": True, "include_cards": True},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "FAQ" in data["summary_markdown"]
    assert data["records_count"] == 2


@pytest.mark.asyncio
async def test_summarize_empty_returns_404(
    client: AsyncClient, auth_headers: dict, monkeypatch
):
    """POST summarize with no annotations returns 404."""
    monkeypatch.setattr(
        "app.routers.classics.chat_completion", _mock_llm("x")
    )
    resp = await client.post(
        f"/api/classics/{CLASSIC_ID}/summarize",
        json={},
        headers=auth_headers,
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Unauthorized access (general)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_all_protected_endpoints_require_auth(raw_client: AsyncClient):
    """All write/annotation/AI endpoints return 401/403 without auth."""
    cases = [
        ("post", f"/api/classics/{CLASSIC_ID}/chapters/{CHAPTER_ID}/annotations"),
        ("put", "/api/classics/annotations/some-id"),
        ("delete", "/api/classics/annotations/some-id"),
        ("put", f"/api/classics/{CLASSIC_ID}/chapters/{CHAPTER_ID}/translation"),
        ("post", f"/api/classics/{CLASSIC_ID}/chapters/{CHAPTER_ID}/ask"),
        ("post", f"/api/classics/{CLASSIC_ID}/chapters/{CHAPTER_ID}/translate"),
        ("put", f"/api/classics/{CLASSIC_ID}/chapters/{CHAPTER_ID}/study-notes"),
        ("post", f"/api/classics/{CLASSIC_ID}/summarize"),
    ]
    for method, url in cases:
        if method == "get":
            r = await raw_client.get(url)
        elif method == "post":
            r = await raw_client.post(url, json={})
        elif method == "put":
            r = await raw_client.put(url, json={})
        else:
            r = await raw_client.delete(url)
        assert r.status_code in (401, 403), f"{method.upper()} {url} returned {r.status_code}"
