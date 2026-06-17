"""Tests for L2 (RAG grounding) and L3 (LLM-as-Judge) hallucination defense layers.

Spec §8.5 requires three layers:
- L1: Herb name validation (existing, tested in test_hallucination_defense.py)
- L2: RAG grounding — check if AI claims are grounded in DB source data
- L3: LLM-as-Judge — independent model scores the response 1-5
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.llm import (
    GROUNDING_WARNING,
    JUDGE_PROMPT_TEMPLATE,
    JUDGE_WARNING,
    _apply_hallucination_defenses,
    _check_grounding,
    _extract_efficacy_keywords,
    _extract_user_question,
    _get_herb_context,
    _get_judge_model,
    _judge_response,
    _parse_judge_score,
)


# ---------------------------------------------------------------------------
# L2 helpers
# ---------------------------------------------------------------------------

class TestExtractEfficacyKeywords:
    def test_finds_known_keywords(self):
        found = _extract_efficacy_keywords("补气升阳，固表止汗")
        assert "补气" in found
        assert "升阳" in found
        assert "固表" in found
        assert "止汗" in found

    def test_ignores_unknown_text(self):
        found = _extract_efficacy_keywords("这是一段普通文字，没有功效描述")
        assert found == set()

    def test_empty_string(self):
        assert _extract_efficacy_keywords("") == set()


class TestGetHerbContext:
    def test_returns_context_around_mention(self):
        text = "建议服用「黄芪」来补气养血，效果很好"
        ctx = _get_herb_context(text, "黄芪")
        assert "补气" in ctx
        assert "养血" in ctx

    def test_handles_multiple_occurrences(self):
        text = "「黄芪」补气，黄芪也可以固表"
        ctx = _get_herb_context(text, "黄芪")
        assert "补气" in ctx
        assert "固表" in ctx

    def test_returns_empty_for_no_match(self):
        assert _get_herb_context("没有药材", "黄芪") == ""


# ---------------------------------------------------------------------------
# L2: RAG Grounding Check
# ---------------------------------------------------------------------------

class TestCheckGrounding:
    @pytest.mark.asyncio
    async def test_no_warning_for_grounded_efficacy(self, db):
        result, flags = await _check_grounding(
            "「黄芪」具有补气升阳的功效，适合气虚者。", db
        )
        assert GROUNDING_WARNING not in result
        assert flags == []

    @pytest.mark.asyncio
    async def test_warning_for_ungrounded_efficacy(self, db):
        result, flags = await _check_grounding(
            "「黄芪」可清热解毒，泻火凉血。", db
        )
        assert GROUNDING_WARNING in result
        assert "黄芪" in flags

    @pytest.mark.asyncio
    async def test_no_warning_when_no_herbs_mentioned(self, db):
        result, flags = await _check_grounding(
            "请多喝水，注意休息，保持心情愉快。", db
        )
        assert GROUNDING_WARNING not in result
        assert flags == []

    @pytest.mark.asyncio
    async def test_graceful_without_db(self):
        result, flags = await _check_grounding("「黄芪」补气", db=None)
        assert GROUNDING_WARNING not in result
        assert flags == []

    @pytest.mark.asyncio
    async def test_multiple_herbs_partial_grounding(self, db):
        result, flags = await _check_grounding(
            "「黄芪」补气固表，「当归」可活血调经。", db
        )
        assert GROUNDING_WARNING not in result
        assert flags == []

    @pytest.mark.asyncio
    async def test_no_duplicate_grounding_warning(self, db):
        text = f"「黄芪」清热解毒。{GROUNDING_WARNING}"
        result, flags = await _check_grounding(text, db)
        assert result.count(GROUNDING_WARNING) == 1

    @pytest.mark.asyncio
    async def test_herb_not_in_db_not_flagged_by_l2(self, db):
        result, flags = await _check_grounding(
            "「虚构灵草」可补气健脾。", db
        )
        assert flags == []
        assert GROUNDING_WARNING not in result

    @pytest.mark.asyncio
    async def test_danggui_grounded(self, db):
        result, flags = await _check_grounding(
            "「当归」可补血活血，调经止痛。", db
        )
        assert GROUNDING_WARNING not in result
        assert flags == []

    @pytest.mark.asyncio
    async def test_danggui_ungrounded(self, db):
        result, flags = await _check_grounding(
            "「当归」可清热解毒，止咳平喘。", db
        )
        assert GROUNDING_WARNING in result
        assert "当归" in flags


# ---------------------------------------------------------------------------
# L3: LLM-as-Judge helpers
# ---------------------------------------------------------------------------

class TestParseJudgeScore:
    def test_extracts_single_digit(self):
        assert _parse_judge_score("4") == 4

    def test_extracts_digit_from_text(self):
        assert _parse_judge_score("评分：3分") == 3

    def test_extracts_first_digit(self):
        assert _parse_judge_score("我给5分，因为...") == 5

    def test_returns_none_for_no_digit(self):
        assert _parse_judge_score("无法评分") is None

    def test_returns_none_for_empty(self):
        assert _parse_judge_score("") is None

    def test_ignores_zero_and_six(self):
        assert _parse_judge_score("0分") is None
        assert _parse_judge_score("6分") is None


class TestGetJudgeModel:
    def test_returns_different_model(self):
        judge = _get_judge_model("Kimi-K2.6")
        assert judge != "Kimi-K2.6"

    def test_fallback_to_same_if_only_one(self):
        import app.config as config_mod
        original = config_mod.settings.LLM_FALLBACK_MODELS
        original_primary = config_mod.settings.LLM_MODEL
        try:
            config_mod.settings.LLM_FALLBACK_MODELS = ""
            config_mod.settings.LLM_MODEL = "only-model"
            judge = _get_judge_model("only-model")
            assert judge == "only-model"
        finally:
            config_mod.settings.LLM_FALLBACK_MODELS = original
            config_mod.settings.LLM_MODEL = original_primary


# ---------------------------------------------------------------------------
# L3: LLM-as-Judge with mocked HTTP
# ---------------------------------------------------------------------------

class TestJudgeResponse:
    @pytest.mark.asyncio
    async def test_returns_score_on_success(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "4"}}]
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("app.llm.has_api_key", return_value=True), \
             patch("app.llm.httpx.AsyncClient", return_value=mock_client):
            score = await _judge_response("气虚怎么办？", "建议补气。", "Kimi-K2.6")

        assert score == 4

    @pytest.mark.asyncio
    async def test_returns_none_on_http_error(self):
        import httpx as _httpx

        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = _httpx.HTTPStatusError(
            "Internal Server Error",
            request=_httpx.Request("POST", "http://test"),
            response=_httpx.Response(500),
        )

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("app.llm.has_api_key", return_value=True), \
             patch("app.llm.httpx.AsyncClient", return_value=mock_client):
            score = await _judge_response("气虚怎么办？", "建议补气。", "Kimi-K2.6")

        assert score is None

    @pytest.mark.asyncio
    async def test_returns_none_on_network_error(self):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("network down"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("app.llm.has_api_key", return_value=True), \
             patch("app.llm.httpx.AsyncClient", return_value=mock_client):
            score = await _judge_response("气虚怎么办？", "建议补气。", "Kimi-K2.6")

        assert score is None

    @pytest.mark.asyncio
    async def test_returns_none_when_no_api_key(self):
        with patch("app.llm.has_api_key", return_value=False):
            score = await _judge_response("气虚怎么办？", "建议补气。", "Kimi-K2.6")
        assert score is None

    @pytest.mark.asyncio
    async def test_parses_score_from_text_response(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "我认为这个回答评3分"}}]
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("app.llm.has_api_key", return_value=True), \
             patch("app.llm.httpx.AsyncClient", return_value=mock_client):
            score = await _judge_response("气虚怎么办？", "建议补气。", "Kimi-K2.6")

        assert score == 3


# ---------------------------------------------------------------------------
# Integration: L1 → L2 → L3 pipeline
# ---------------------------------------------------------------------------

class TestExtractUserQuestion:
    def test_extracts_last_user_message(self):
        messages = [
            {"role": "user", "content": "第一个问题"},
            {"role": "assistant", "content": "第一个回答"},
            {"role": "user", "content": "第二个问题"},
        ]
        assert _extract_user_question(messages) == "第二个问题"

    def test_returns_empty_for_no_user_messages(self):
        assert _extract_user_question([]) == ""

    def test_handles_multimodal_content(self):
        messages = [
            {"role": "user", "content": [
                {"type": "text", "text": "这是什么药？"},
                {"type": "image_url", "image_url": {"url": "data:..."}},
            ]}
        ]
        assert _extract_user_question(messages) == "这是什么药？"


class TestApplyHallucinationDefenses:
    @pytest.mark.asyncio
    async def test_l1_l2_pass_l3_skip(self, db):
        import app.database as db_mod
        original_db = db_mod._db_adapter
        try:
            db_mod.set_db(db)
            answer = "「黄芪」可补气升阳，适合气虚者。"
            with patch("app.llm.has_api_key", return_value=False):
                result, meta = await _apply_hallucination_defenses(
                    "气虚怎么办？", answer, db, primary_model="Kimi-K2.6"
                )
            assert GROUNDING_WARNING not in result
            assert meta["grounding_flags"] == []
            assert "judge_score" not in meta
        finally:
            db_mod.set_db(original_db)

    @pytest.mark.asyncio
    async def test_l2_flags_ungrounded(self, db):
        import app.database as db_mod
        original_db = db_mod._db_adapter
        try:
            db_mod.set_db(db)
            answer = "「黄芪」可清热解毒，泻火凉血。"
            with patch("app.llm.has_api_key", return_value=False):
                result, meta = await _apply_hallucination_defenses(
                    "黄芪有什么功效？", answer, db, primary_model="Kimi-K2.6"
                )
            assert GROUNDING_WARNING in result
            assert "黄芪" in meta["grounding_flags"]
            assert "judge_score" not in meta
        finally:
            db_mod.set_db(original_db)

    @pytest.mark.asyncio
    async def test_l3_low_score_prepends_warning(self, db):
        import app.database as db_mod
        original_db = db_mod._db_adapter
        try:
            db_mod.set_db(db)
            answer = "「黄芪」补气升阳。"
            mock_resp = MagicMock()
            mock_resp.json.return_value = {
                "choices": [{"message": {"content": "2"}}]
            }
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)

            with patch("app.llm.has_api_key", return_value=True), \
                 patch("app.llm.httpx.AsyncClient", return_value=mock_client):
                result, meta = await _apply_hallucination_defenses(
                    "黄芪有什么功效？", answer, db, primary_model="Kimi-K2.6"
                )

            assert result.startswith(JUDGE_WARNING)
            assert meta["judge_score"] == 2
        finally:
            db_mod.set_db(original_db)

    @pytest.mark.asyncio
    async def test_l3_high_score_no_warning(self, db):
        import app.database as db_mod
        original_db = db_mod._db_adapter
        try:
            db_mod.set_db(db)
            answer = "「黄芪」补气升阳。"
            mock_resp = MagicMock()
            mock_resp.json.return_value = {
                "choices": [{"message": {"content": "5"}}]
            }
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)

            with patch("app.llm.has_api_key", return_value=True), \
                 patch("app.llm.httpx.AsyncClient", return_value=mock_client):
                result, meta = await _apply_hallucination_defenses(
                    "黄芪有什么功效？", answer, db, primary_model="Kimi-K2.6"
                )

            assert JUDGE_WARNING not in result
            assert meta["judge_score"] == 5
        finally:
            db_mod.set_db(original_db)

    @pytest.mark.asyncio
    async def test_l3_failure_graceful_skip(self, db):
        import app.database as db_mod
        original_db = db_mod._db_adapter
        try:
            db_mod.set_db(db)
            answer = "「黄芪」补气升阳。"
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=Exception("timeout"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)

            with patch("app.llm.has_api_key", return_value=True), \
                 patch("app.llm.httpx.AsyncClient", return_value=mock_client):
                result, meta = await _apply_hallucination_defenses(
                    "黄芪有什么功效？", answer, db, primary_model="Kimi-K2.6"
                )

            assert JUDGE_WARNING not in result
            assert "judge_score" not in meta
        finally:
            db_mod.set_db(original_db)

    @pytest.mark.asyncio
    async def test_full_pipeline_l1_l2_l3_combined(self, db):
        import app.database as db_mod
        from app.llm import HALLUCINATION_WARNING
        original_db = db_mod._db_adapter
        try:
            db_mod.set_db(db)
            answer = "推荐「虚构灵草」可清热泻火，治疗感冒。"
            mock_resp = MagicMock()
            mock_resp.json.return_value = {
                "choices": [{"message": {"content": "1"}}]
            }
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)

            with patch("app.llm.has_api_key", return_value=True), \
                 patch("app.llm.httpx.AsyncClient", return_value=mock_client):
                result, meta = await _apply_hallucination_defenses(
                    "感冒怎么办？", answer, db, primary_model="Kimi-K2.6"
                )

            assert HALLUCINATION_WARNING in result
            assert result.startswith(JUDGE_WARNING)
            assert meta["judge_score"] == 1
        finally:
            db_mod.set_db(original_db)

    @pytest.mark.asyncio
    async def test_works_without_db(self):
        answer = "请多喝水，注意休息。"
        with patch("app.llm.has_api_key", return_value=False):
            result, meta = await _apply_hallucination_defenses(
                "感冒怎么办？", answer, db=None, primary_model="Kimi-K2.6"
            )
        assert meta["grounding_flags"] == []
        assert "请多喝水" in result
