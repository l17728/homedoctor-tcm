"""Tests for json_extractor + url_validator + category_classifier + knowledge_browse."""

import pytest
import pytest_asyncio
from app.database import SqliteAdapter, init_db, seed_safety_rules, seed_test_data


@pytest_asyncio.fixture
async def qa_db():
    adapter = SqliteAdapter(":memory:")
    await adapter.connect()
    await init_db(adapter)
    await seed_safety_rules(adapter)
    await seed_test_data(adapter)
    await adapter.execute(
        """INSERT INTO knowledge_entities
           (id, entity_type, source_table, source_id, title, summary,
            keywords, tags, category, properties, source_type, status)
           VALUES ('ke-qa-1', 'herb', 'test', 'qa1', '测试药材',
                   '功效', '[]', '[]', '补虚药', '{"nature":"温"}', 'system', 'active')"""
    )
    yield adapter
    await adapter.close()


class TestJsonExtractor:
    def test_simple_object(self):
        from app.json_extractor import extract_json
        result = extract_json('some text {"key": "value"} more text')
        assert result == {"key": "value"}

    def test_nested_object(self):
        from app.json_extractor import extract_json
        result = extract_json('{"outer": {"inner": {"deep": 1}}}')
        assert result == {"outer": {"inner": {"deep": 1}}}

    def test_array(self):
        from app.json_extractor import extract_json
        text = 'prefix [1, 2, {"x": "y"}] suffix'
        result = extract_json(text)
        assert result is not None
        assert len(result) == 3

    def test_string_with_braces(self):
        from app.json_extractor import extract_json
        result = extract_json('{"text": "has } brace"}')
        assert result == {"text": "has } brace"}

    def test_no_json(self):
        from app.json_extractor import extract_json
        assert extract_json("no json here") is None
        assert extract_json("") is None

    def test_escaped_quotes(self):
        from app.json_extractor import extract_json
        result = extract_json(r'{"msg": "say \"hello\""}')
        assert result == {"msg": 'say "hello"'}


class TestUrlValidator:
    def test_valid_https(self):
        from app.url_validator import validate_external_url
        assert validate_external_url("https://example.com/page") is True

    def test_valid_http(self):
        from app.url_validator import validate_external_url
        assert validate_external_url("http://example.com") is True

    def test_block_localhost(self):
        from app.url_validator import validate_external_url
        assert validate_external_url("http://localhost:8080") is False

    def test_block_private_ip(self):
        from app.url_validator import validate_external_url
        assert validate_external_url("http://192.168.1.1") is False
        assert validate_external_url("http://10.0.0.1") is False

    def test_block_metadata_endpoint(self):
        from app.url_validator import validate_external_url
        assert validate_external_url("http://169.254.169.254/latest/meta-data/") is False

    def test_block_file_scheme(self):
        from app.url_validator import validate_external_url
        assert validate_external_url("file:///etc/passwd") is False

    def test_block_empty(self):
        from app.url_validator import validate_external_url
        assert validate_external_url("") is False
        assert validate_external_url("   ") is False


class TestCategoryClassifier:
    def test_guess_existing_category(self):
        from app.category_classifier import _guess_category
        cats = ['静功', '动功', '内家拳法', '导引功法']
        assert _guess_category('太极拳', '内家拳法', cats) == '内家拳法'
        assert _guess_category('八段锦', '导引', cats) == '导引功法'

    def test_new_category_qigong(self):
        from app.category_classifier import _guess_category
        cats = ['静功', '动功']
        result = _guess_category('真气运行法', '真气运行培补元气', cats)
        assert result == '气功功法'

    def test_fallback_to_first(self):
        from app.category_classifier import _guess_category
        cats = ['其他分类']
        result = _guess_category('完全无关的内容', '没有匹配关键词', cats)
        assert result == '其他分类'

    @pytest.mark.asyncio
    async def test_classify_with_db(self, qa_db):
        from app.category_classifier import classify_category
        result = await classify_category(qa_db, '测试新功法', '一种新的静功修炼方法', 'health_practice')
        assert 'category' in result
        assert isinstance(result.get('is_new'), bool)


class TestKnowledgeBrowse:
    @pytest.mark.asyncio
    async def test_categories(self, client, db):
        await db.execute(
            """INSERT INTO knowledge_entities
               (id, entity_type, source_table, source_id, title, summary,
                keywords, tags, category, properties, source_type, status)
               VALUES ('ke-cat-test', 'herb', 'test', 'c1', '分类测试药',
                       '测试', '[]', '[]', '补虚药', '{}', 'system', 'active')"""
        )
        resp = await client.get("/api/knowledge/categories")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["types"]) > 0

    @pytest.mark.asyncio
    async def test_browse_herbs(self, client, db):
        await db.execute(
            """INSERT INTO knowledge_entities
               (id, entity_type, source_table, source_id, title, summary,
                keywords, tags, category, properties, source_type, status)
               VALUES ('ke-browse-test', 'herb', 'test', 'b1', '浏览测试药',
                       '测试', '[]', '[]', '补虚药', '{}', 'system', 'active')"""
        )
        resp = await client.get("/api/knowledge/browse?type=herb&page_size=5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] > 0
        assert len(data["items"]) <= 5

    @pytest.mark.asyncio
    async def test_browse_with_search(self, client):
        resp = await client.get("/api/knowledge/browse?type=herb&q=黄芪")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_browse_invalid_type(self, client):
        resp = await client.get("/api/knowledge/browse?type=nonexistent")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    @pytest.mark.asyncio
    async def test_note_save_and_get(self, client, db):
        await db.execute(
            """INSERT INTO knowledge_entities
               (id, entity_type, source_table, source_id, title, summary,
                keywords, tags, category, properties, source_type, status)
               VALUES ('ke-note-test', 'herb', 'test', 'n1', '笔记测试药',
                       '测试', '[]', '[]', '测试', '{}', 'system', 'active')"""
        )
        resp = await client.put("/api/knowledge/ke-note-test/note", json={
            "content": "这是我的笔记## 标题\n- 要点1"
        })
        assert resp.status_code == 200

        resp2 = await client.get("/api/knowledge/ke-note-test/note")
        assert resp2.status_code == 200
        assert "笔记" in resp2.json()["content"]

    @pytest.mark.asyncio
    async def test_note_clear(self, client, db):
        await db.execute(
            """INSERT INTO knowledge_entities
               (id, entity_type, source_table, source_id, title, summary,
                keywords, tags, category, properties, source_type, status)
               VALUES ('ke-note-clear', 'herb', 'test', 'n2', '清除笔记测试',
                       '测试', '[]', '[]', '测试', '{}', 'system', 'active')"""
        )
        await client.put("/api/knowledge/ke-note-clear/note", json={"content": "临时笔记"})
        resp = await client.put("/api/knowledge/ke-note-clear/note", json={"content": "  "})
        assert resp.status_code == 200
        resp2 = await client.get("/api/knowledge/ke-note-clear/note")
        assert resp2.json()["content"] == ""

    @pytest.mark.asyncio
    async def test_append_nonexistent(self, client):
        resp = await client.post("/api/knowledge/nonexistent-id/append", json={
            "instruction": "添加内容"
        })
        assert resp.status_code == 404
