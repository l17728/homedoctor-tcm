"""Tests for llm_unified.py — unified LLM caller."""
import asyncio
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.database import SqliteAdapter, init_db, seed_safety_rules, seed_test_data
from app.llm_unified import llm_chat, llm_collective_review, llm_collective_review_opencode
from app.model_registry import create_model, get_default_models, list_models, _select_consensus


@pytest_asyncio.fixture
async def llm_db():
    adapter = SqliteAdapter(":memory:")
    await adapter.connect()
    await init_db(adapter)
    await seed_safety_rules(adapter)
    await seed_test_data(adapter)
    yield adapter
    await adapter.close()


def _mock_model(name="test-model", model_id="test-1", api_key="sk-test-key"):
    return {"name": name, "model_id": model_id, "api_key": api_key,
            "api_endpoint": "https://test.example.com/v1/chat"}


class TestLlmChat:
    @pytest.mark.asyncio
    async def test_no_models_configured(self, llm_db):
        with patch("app.model_registry.get_default_models", new_callable=AsyncMock) as mock:
            mock.return_value = []
            result = await llm_chat(llm_db, [{"role": "user", "content": "hi"}])
            assert result == ""

    @pytest.mark.asyncio
    async def test_successful_call(self, llm_db):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"choices": [{"message": {"content": "test reply"}}]}

        with patch("app.model_registry.get_default_models", new_callable=AsyncMock) as mock_models, \
             patch("httpx.AsyncClient") as mock_client_cls:
            mock_models.return_value = [_mock_model()]
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            result = await llm_chat(llm_db, [{"role": "user", "content": "test"}])
            assert result == "test reply"

    @pytest.mark.asyncio
    async def test_masked_api_key(self, llm_db):
        with patch("app.model_registry.get_default_models", new_callable=AsyncMock) as mock:
            mock.return_value = [_mock_model(api_key="***masked***")]
            result = await llm_chat(llm_db, [{"role": "user", "content": "test"}])
            assert result == ""

    @pytest.mark.asyncio
    async def test_api_error_returns_empty(self, llm_db):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"

        with patch("app.model_registry.get_default_models", new_callable=AsyncMock) as mock_models, \
             patch("httpx.AsyncClient") as mock_client_cls:
            mock_models.return_value = [_mock_model()]
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            result = await llm_chat(llm_db, [{"role": "user", "content": "test"}])
            assert result == ""

    @pytest.mark.asyncio
    async def test_exception_returns_empty(self, llm_db):
        with patch("app.model_registry.get_default_models", new_callable=AsyncMock) as mock_models, \
             patch("httpx.AsyncClient", side_effect=RuntimeError("connection refused")):
            mock_models.return_value = [_mock_model()]
            result = await llm_chat(llm_db, [{"role": "user", "content": "test"}])
            assert result == ""


class TestLlmCollectiveReview:
    @pytest.mark.asyncio
    async def test_no_models(self, llm_db):
        with patch("app.model_registry.get_default_models", new_callable=AsyncMock) as mock:
            mock.return_value = []
            result = await llm_collective_review(llm_db, "test prompt")
            assert result["model_count"] == 0
            assert result["agreement"] == 0.0

    @pytest.mark.asyncio
    async def test_multiple_models_consensus(self, llm_db):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"choices": [{"message": {"content": "model reply"}}]}

        with patch("app.model_registry.get_default_models", new_callable=AsyncMock) as mock_models, \
             patch("httpx.AsyncClient") as mock_client_cls:
            mock_models.return_value = [_mock_model("m1"), _mock_model("m2"), _mock_model("m3")]
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            result = await llm_collective_review(llm_db, "test")
            assert result["model_count"] == 3
            assert result["valid_count"] == 3
            assert result["consensus_text"] == "model reply"
            assert result["agreement"] == 1.0

    @pytest.mark.asyncio
    async def test_partial_failure(self, llm_db):
        ok_resp = MagicMock()
        ok_resp.status_code = 200
        ok_resp.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
        err_resp = MagicMock()
        err_resp.status_code = 500
        err_resp.text = "error"

        with patch("app.model_registry.get_default_models", new_callable=AsyncMock) as mock_models, \
             patch("httpx.AsyncClient") as mock_client_cls:
            mock_models.return_value = [_mock_model("m1"), _mock_model("m2")]
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = AsyncMock(side_effect=[ok_resp, err_resp])
            mock_client_cls.return_value = mock_client

            result = await llm_collective_review(llm_db, "test")
            assert result["valid_count"] == 1
            assert result["agreement"] == 0.5

    @pytest.mark.asyncio
    async def test_all_fail(self, llm_db):
        err_resp = MagicMock()
        err_resp.status_code = 503
        err_resp.text = "unavailable"

        with patch("app.model_registry.get_default_models", new_callable=AsyncMock) as mock_models, \
             patch("httpx.AsyncClient") as mock_client_cls:
            mock_models.return_value = [_mock_model("m1"), _mock_model("m2")]
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = AsyncMock(return_value=err_resp)
            mock_client_cls.return_value = mock_client

            result = await llm_collective_review(llm_db, "test")
            assert result["valid_count"] == 0
            assert result["consensus_text"] == ""


class TestLlmCollectiveReviewOpencode:
    @pytest.mark.asyncio
    async def test_no_models(self):
        result = await llm_collective_review_opencode("test", models=[])
        assert result["model_count"] == 0

    @pytest.mark.asyncio
    async def test_timeout_handling(self, monkeypatch):
        from app.config import settings
        monkeypatch.setattr(settings, "ENABLE_OPENCODE_REVIEW", True)
        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_proc:
            mock_proc.side_effect = asyncio.TimeoutError()
            result = await llm_collective_review_opencode("test", models=["model-1"])
            assert result["valid_count"] == 0

    @pytest.mark.asyncio
    async def test_exception_handling(self, monkeypatch):
        from app.config import settings
        monkeypatch.setattr(settings, "ENABLE_OPENCODE_REVIEW", True)
        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_proc:
            mock_proc.side_effect = RuntimeError("not found")
            result = await llm_collective_review_opencode("test", models=["model-1"])
            assert result["valid_count"] == 0

    @pytest.mark.asyncio
    async def test_disabled_by_default_does_not_spawn_subprocess(self, monkeypatch):
        from app.config import settings
        monkeypatch.setattr(settings, "ENABLE_OPENCODE_REVIEW", False)
        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_proc:
            result = await llm_collective_review_opencode("untrusted prompt", models=["model-1"])
        mock_proc.assert_not_called()
        assert result["error"] == "opencode 评审未启用"


@pytest.mark.asyncio
async def test_model_api_key_is_encrypted_at_rest_and_masked(llm_db, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "SECRET_KEY", "test-encryption-key")
    raw_key = "sk-super-secret-123"
    model_id = await create_model(
        llm_db, name="test", provider="test", model_id="test-model",
        api_endpoint="https://example.test", api_key=raw_key,
        is_default=True, capabilities=["text"],
    )
    stored = await llm_db.query_one("SELECT api_key FROM ai_models WHERE id = ?", (model_id,))
    assert raw_key not in stored["api_key"]
    assert stored["api_key"].startswith("hde1:")
    public = next(row for row in await list_models(llm_db) if row["id"] == model_id)
    internal = next(row for row in await get_default_models(llm_db) if row["id"] == model_id)
    assert public["api_key"] == "sk-***"
    assert internal["api_key"] == raw_key


def test_consensus_uses_largest_similarity_cluster_not_longest_answer():
    chosen, agreement = _select_consensus(
        ["共同意见：注意休息并咨询医生。", "共同意见：注意休息并咨询医生，避免自行用药。", "完全不同的很长回答" * 30],
        total=3,
    )
    assert chosen.startswith("共同意见")
    assert agreement == pytest.approx(2 / 3)
