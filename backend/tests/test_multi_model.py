"""Tests for multi-model voting + aggregation (spec §8.3 / §13.2 V2 P0 / §10.4).

Covers:
- Response aggregation: consensus herb detection, confidence scoring, best-answer
  selection by quality score.
- Single-model query helper: success / HTTP error / network error / no-api-key.
- Voting orchestration: parallel querying, history forwarding, custom models,
  graceful degradation (1-of-3 timeout, all-fail).
- Quality scorer: monotonicity and range.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.llm import (
    DEFAULT_VOTING_MODELS,
    DISCLAIMER,
    _aggregate_responses,
    _get_voting_models,
    _query_single_model,
    _score_response,
    chat_completion_voting,
)


# ---------------------------------------------------------------------------
# _get_voting_models
# ---------------------------------------------------------------------------

class TestGetVotingModels:
    def test_defaults_to_three_distinct_models(self):
        models = _get_voting_models(None)
        assert len(models) == 3
        assert len(models) == len(set(models))

    def test_primary_model_present_by_default(self):
        models = _get_voting_models(None)
        assert "Kimi-K2.6" in models

    def test_respects_explicit_list(self):
        models = _get_voting_models(["ModelA", "ModelB"])
        assert models == ["ModelA", "ModelB"]

    def test_respects_single_explicit_model(self):
        assert _get_voting_models(["OnlyOne"]) == ["OnlyOne"]

    def test_falls_back_to_defaults_when_chain_empty(self):
        import app.config as config_mod
        original_primary = config_mod.settings.LLM_MODEL
        original_fallback = config_mod.settings.LLM_FALLBACK_MODELS
        try:
            config_mod.settings.LLM_MODEL = ""
            config_mod.settings.LLM_FALLBACK_MODELS = ""
            models = _get_voting_models(None)
            assert models == list(DEFAULT_VOTING_MODELS)
        finally:
            config_mod.settings.LLM_MODEL = original_primary
            config_mod.settings.LLM_FALLBACK_MODELS = original_fallback


# ---------------------------------------------------------------------------
# _score_response
# ---------------------------------------------------------------------------

class TestScoreResponse:
    def test_empty_returns_zero(self):
        assert _score_response("") == 0.0

    def test_score_in_unit_range(self):
        for txt in ["", "短", "a" * 1000, "仅供参考克mg毫升", "普通文字" * 50]:
            s = _score_response(txt)
            assert 0.0 <= s <= 1.0

    def test_longer_scores_higher_than_short(self):
        assert _score_response("详细回答" * 100) > _score_response("短")

    def test_safety_disclaimers_boost_score(self):
        base = "建议服用中药调理身体注意休息保持心情愉快" * 8
        with_safety = base + "仅供参考不替代医生面诊请咨询就医遵医嘱"
        assert _score_response(with_safety) > _score_response(base)

    def test_specificity_terms_boost_score(self):
        base = "建议服用中药调理身体注意休息保持心情愉快" * 8
        with_spec = base + "每日3次每次5克2片1袋10毫升"
        assert _score_response(with_spec) > _score_response(base)

    def test_equal_length_safety_beats_plain(self):
        plain = "建议多喝水注意休息保持心情愉快" * 10
        safe = ("建议多喝水注意休息保持心情愉快仅供参考" * 8)[: len(plain)]
        assert _score_response(safe) > _score_response(plain)


# ---------------------------------------------------------------------------
# _query_single_model
# ---------------------------------------------------------------------------

def _make_mock_client(content: str | None = None, *, exc=None, http_error=None):
    mock_resp = MagicMock()
    if http_error is not None:
        mock_resp.raise_for_status.side_effect = http_error
    else:
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": content or ""}}]
        }
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(
        return_value=mock_resp if exc is None else None,
        side_effect=exc if exc is not None else None,
    )
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    return mock_client


class TestQuerySingleModel:
    @pytest.mark.asyncio
    async def test_success_returns_answer(self):
        mock_client = _make_mock_client("hello from model")
        with patch("app.llm.has_api_key", return_value=True), \
             patch("app.llm.httpx.AsyncClient", return_value=mock_client):
            result = await _query_single_model(
                "Kimi-K2.6", [{"role": "user", "content": "hi"}]
            )
        assert result["answer"] == "hello from model"
        assert result["error"] is None
        assert result["model"] == "Kimi-K2.6"

    @pytest.mark.asyncio
    async def test_http_error_captured_not_raised(self):
        http_err = httpx.HTTPStatusError(
            "Internal Server Error",
            request=httpx.Request("POST", "http://test"),
            response=httpx.Response(500),
        )
        mock_client = _make_mock_client(http_error=http_err)
        with patch("app.llm.has_api_key", return_value=True), \
             patch("app.llm.httpx.AsyncClient", return_value=mock_client):
            result = await _query_single_model(
                "GLM-5", [{"role": "user", "content": "hi"}]
            )
        assert result["answer"] == ""
        assert "500" in result["error"]

    @pytest.mark.asyncio
    async def test_network_error_captured_not_raised(self):
        mock_client = _make_mock_client(exc=httpx.ConnectTimeout("timeout"))
        with patch("app.llm.has_api_key", return_value=True), \
             patch("app.llm.httpx.AsyncClient", return_value=mock_client):
            result = await _query_single_model(
                "GLM-5", [{"role": "user", "content": "hi"}]
            )
        assert result["answer"] == ""
        assert result["error"] is not None

    @pytest.mark.asyncio
    async def test_generic_exception_captured(self):
        mock_client = _make_mock_client(exc=Exception("boom"))
        with patch("app.llm.has_api_key", return_value=True), \
             patch("app.llm.httpx.AsyncClient", return_value=mock_client):
            result = await _query_single_model(
                "GLM-5", [{"role": "user", "content": "hi"}]
            )
        assert result["answer"] == ""
        assert "boom" in result["error"]

    @pytest.mark.asyncio
    async def test_no_api_key_returns_error_marker(self):
        with patch("app.llm.has_api_key", return_value=False):
            result = await _query_single_model(
                "Kimi-K2.6", [{"role": "user", "content": "hi"}]
            )
        assert result["answer"] == ""
        assert result["error"] is not None

    @pytest.mark.asyncio
    async def test_constitution_forwarded_to_system_prompt(self):
        mock_client = _make_mock_client("ok")
        with patch("app.llm.has_api_key", return_value=True), \
             patch("app.llm.httpx.AsyncClient", return_value=mock_client):
            await _query_single_model(
                "Kimi-K2.6",
                [{"role": "user", "content": "hi"}],
                constitution={"primary": "气虚质", "secondary": []},
            )
        posted_payload = mock_client.post.call_args.kwargs["json"]
        system_msg = posted_payload["messages"][0]
        assert "气虚质" in system_msg["content"]


# ---------------------------------------------------------------------------
# _aggregate_responses
# ---------------------------------------------------------------------------

class TestAggregateResponses:
    @pytest.mark.asyncio
    async def test_three_identical_responses_high_confidence(self):
        answer = "建议服用「黄芪」补气升阳。仅供参考，请咨询医生面诊。"
        responses = [
            {"model": "Kimi-K2.6", "answer": answer, "error": None},
            {"model": "GLM-5", "answer": answer, "error": None},
            {"model": "qwen3-235b-a22b", "answer": answer, "error": None},
        ]
        result = await _aggregate_responses(responses)

        assert result["confidence_score"] >= 0.9
        assert "黄芪" in result["consensus_herbs"]
        assert "黄芪" in result["metadata"]["high_confidence_herbs"]
        assert result["metadata"]["medium_confidence_herbs"] == []
        assert len(result["model_votes"]) == 3
        assert result["metadata"]["responded"] == 3
        assert result["metadata"]["requested"] == 3

    @pytest.mark.asyncio
    async def test_two_of_three_agree_medium_confidence(self):
        responses = [
            {"model": "Kimi-K2.6", "answer": "推荐「黄芪」补气。", "error": None},
            {"model": "GLM-5", "answer": "推荐「黄芪」补气。", "error": None},
            {"model": "qwen3-235b-a22b", "answer": "推荐「当归」补血。", "error": None},
        ]
        result = await _aggregate_responses(responses)

        assert 0.6 <= result["confidence_score"] < 0.9
        assert "黄芪" in result["consensus_herbs"]
        assert "黄芪" in result["metadata"]["high_confidence_herbs"]
        assert "当归" not in result["consensus_herbs"]
        assert "当归" in result["metadata"]["medium_confidence_herbs"]

    @pytest.mark.asyncio
    async def test_three_divergent_picks_best_by_score(self):
        short = "推荐黄芪。"
        long = (
            "推荐「黄芪」补气升阳，固表止汗，托毒生肌。"
            "每日可煎服3-5克，分2次温服。"
            "仅供参考，不替代医生面诊，请咨询执业医师遵医嘱。"
        )
        other = "试试枸杞泡水喝。"
        responses = [
            {"model": "Kimi-K2.6", "answer": short, "error": None},
            {"model": "GLM-5", "answer": long, "error": None},
            {"model": "qwen3-235b-a22b", "answer": other, "error": None},
        ]
        result = await _aggregate_responses(responses)

        assert result["answer"] == long
        assert result["confidence_score"] < 0.6
        assert result["metadata"]["best_model"] == "GLM-5"
        assert result["metadata"]["high_confidence_herbs"] == []

    @pytest.mark.asyncio
    async def test_single_response_graceful_no_voting(self):
        responses = [
            {"model": "Kimi-K2.6", "answer": "建议服用「黄芪」补气。", "error": None},
            {"model": "GLM-5", "answer": "", "error": "timeout"},
            {"model": "qwen3-235b-a22b", "answer": "", "error": "HTTP 500"},
        ]
        result = await _aggregate_responses(responses)

        assert "黄芪" in result["answer"]
        assert result["confidence_score"] == 0.5
        assert result["metadata"]["reason"] == "single_model_no_voting"
        assert result["metadata"]["responded"] == 1

    @pytest.mark.asyncio
    async def test_all_fail_returns_error_message(self):
        responses = [
            {"model": "Kimi-K2.6", "answer": "", "error": "timeout"},
            {"model": "GLM-5", "answer": "", "error": "HTTP 500"},
            {"model": "qwen3-235b-a22b", "answer": "", "error": "network down"},
        ]
        result = await _aggregate_responses(responses)

        assert "暂时不可用" in result["answer"]
        assert result["confidence_score"] == 0.0
        assert result["consensus_herbs"] == []
        assert result["metadata"]["reason"] == "all_models_failed"
        assert result["metadata"]["responded"] == 0
        assert len(result["model_votes"]) == 3
        for vote in result["model_votes"]:
            assert vote["error"] is not None

    @pytest.mark.asyncio
    async def test_empty_input_list(self):
        result = await _aggregate_responses([])
        assert result["confidence_score"] == 0.0
        assert result["metadata"]["reason"] == "all_models_failed"

    @pytest.mark.asyncio
    async def test_two_models_both_share_herb(self):
        responses = [
            {"model": "Kimi-K2.6", "answer": "「黄芪」补气。", "error": None},
            {"model": "GLM-5", "answer": "「黄芪」固表。", "error": None},
        ]
        result = await _aggregate_responses(responses)

        assert "黄芪" in result["consensus_herbs"]
        assert result["confidence_score"] == 0.7

    @pytest.mark.asyncio
    async def test_two_models_no_overlap(self):
        responses = [
            {"model": "Kimi-K2.6", "answer": "「黄芪」补气。", "error": None},
            {"model": "GLM-5", "answer": "「当归」补血。", "error": None},
        ]
        result = await _aggregate_responses(responses)

        assert result["consensus_herbs"] == []
        assert result["confidence_score"] == 0.5

    @pytest.mark.asyncio
    async def test_model_votes_include_scores(self):
        responses = [
            {"model": "Kimi-K2.6", "answer": "短回答", "error": None},
            {
                "model": "GLM-5",
                "answer": "这是一个非常详细的回答，包含了具体建议仅供参考请咨询医生每日3次。",
                "error": None,
            },
        ]
        result = await _aggregate_responses(responses)
        for vote in result["model_votes"]:
            assert "score" in vote
            assert 0.0 <= vote["score"] <= 1.0
            assert "confidence" in vote

    @pytest.mark.asyncio
    async def test_metadata_includes_required_fields(self):
        responses = [
            {"model": "A", "answer": "「黄芪」补气。", "error": None},
            {"model": "B", "answer": "「黄芪」补气。", "error": None},
        ]
        result = await _aggregate_responses(responses)
        meta = result["metadata"]
        for key in (
            "high_confidence_herbs",
            "medium_confidence_herbs",
            "best_score",
            "best_model",
            "responded",
            "requested",
            "reason",
        ):
            assert key in meta, f"missing metadata key: {key}"


# ---------------------------------------------------------------------------
# chat_completion_voting (orchestration with mocked _query_single_model)
# ---------------------------------------------------------------------------

class TestChatCompletionVoting:
    @pytest.mark.asyncio
    async def test_queries_three_models_in_parallel(self):
        call_count = 0

        async def fake_query(model, messages, constitution=None):
            nonlocal call_count
            call_count += 1
            return {
                "model": model,
                "answer": f"answer from {model}「黄芪」仅供参考请咨询医生",
                "error": None,
            }

        with patch("app.llm._query_single_model", side_effect=fake_query):
            result = await chat_completion_voting("气虚怎么办？")

        assert call_count == 3
        assert len(result["model_votes"]) == 3
        assert "黄芪" in result["consensus_herbs"]
        assert result["confidence_score"] >= 0.9

    @pytest.mark.asyncio
    async def test_one_model_timeout_uses_others(self):
        async def fake_query(model, messages, constitution=None):
            if model == "GLM-5":
                return {"model": model, "answer": "", "error": "timeout"}
            return {
                "model": model,
                "answer": f"「黄芪」补气 from {model}。",
                "error": None,
            }

        with patch("app.llm._query_single_model", side_effect=fake_query):
            result = await chat_completion_voting("气虚？")

        assert result["answer"]
        assert "黄芪" in result["consensus_herbs"]
        assert result["metadata"]["responded"] == 2

    @pytest.mark.asyncio
    async def test_all_models_fail_returns_error(self):
        async def fake_query(model, messages, constitution=None):
            return {"model": model, "answer": "", "error": "network down"}

        with patch("app.llm._query_single_model", side_effect=fake_query):
            result = await chat_completion_voting("气虚？")

        assert "暂时不可用" in result["answer"]
        assert result["confidence_score"] == 0.0
        assert result["consensus_herbs"] == []
        assert result["metadata"]["reason"] == "all_models_failed"

    @pytest.mark.asyncio
    async def test_custom_models_used(self):
        used_models: list[str] = []

        async def fake_query(model, messages, constitution=None):
            used_models.append(model)
            return {"model": model, "answer": "回答", "error": None}

        with patch("app.llm._query_single_model", side_effect=fake_query):
            await chat_completion_voting("?", models=["ModelA", "ModelB"])

        assert used_models == ["ModelA", "ModelB"]

    @pytest.mark.asyncio
    async def test_history_appended_to_messages(self):
        captured: list[list[dict]] = []

        async def fake_query(model, messages, constitution=None):
            captured.append(list(messages))
            return {"model": model, "answer": "ok", "error": None}

        history = [
            {"role": "user", "content": "previous question"},
            {"role": "assistant", "content": "previous answer"},
        ]
        with patch("app.llm._query_single_model", side_effect=fake_query):
            await chat_completion_voting("new question", history=history)

        for msgs in captured:
            assert msgs[-1] == {"role": "user", "content": "new question"}
            assert msgs[0] == {"role": "user", "content": "previous question"}
            assert msgs[1] == {"role": "assistant", "content": "previous answer"}

    @pytest.mark.asyncio
    async def test_no_history_works(self):
        captured: list[list[dict]] = []

        async def fake_query(model, messages, constitution=None):
            captured.append(list(messages))
            return {"model": model, "answer": "ok", "error": None}

        with patch("app.llm._query_single_model", side_effect=fake_query):
            await chat_completion_voting("just a question")

        for msgs in captured:
            assert len(msgs) == 1
            assert msgs[0] == {"role": "user", "content": "just a question"}

    @pytest.mark.asyncio
    async def test_constitution_forwarded(self):
        received_constitutions: list = []

        async def fake_query(model, messages, constitution=None):
            received_constitutions.append(constitution)
            return {"model": model, "answer": "ok", "error": None}

        with patch("app.llm._query_single_model", side_effect=fake_query):
            await chat_completion_voting(
                "?", constitution={"primary": "阳虚质", "secondary": []}
            )

        assert all(c == {"primary": "阳虚质", "secondary": []} for c in received_constitutions)

    @pytest.mark.asyncio
    async def test_return_shape(self):
        async def fake_query(model, messages, constitution=None):
            return {"model": model, "answer": "「黄芪」补气。", "error": None}

        with patch("app.llm._query_single_model", side_effect=fake_query):
            result = await chat_completion_voting("?")

        for key in ("answer", "model_votes", "consensus_herbs", "confidence_score", "metadata"):
            assert key in result, f"missing top-level key: {key}"

    @pytest.mark.asyncio
    async def test_divergent_picks_most_detailed(self):
        async def fake_query(model, messages, constitution=None):
            if model == "GLM-5":
                return {
                    "model": model,
                    "answer": (
                        "推荐「黄芪」补气升阳固表止汗，每日3次每次5克。"
                        "仅供参考，不替代医生面诊，请咨询执业医师遵医嘱。"
                    ),
                    "error": None,
                }
            if model == "Kimi-K2.6":
                return {"model": model, "answer": "短", "error": None}
            return {"model": model, "answer": "枸杞泡水。", "error": None}

        with patch("app.llm._query_single_model", side_effect=fake_query):
            result = await chat_completion_voting("气虚？")

        assert result["metadata"]["best_model"] == "GLM-5"
        assert "黄芪" in result["answer"]


# ---------------------------------------------------------------------------
# Integration: parallel querying through the real httpx path (mocked transport)
# ---------------------------------------------------------------------------

class TestVotingParallelIntegration:
    @pytest.mark.asyncio
    async def test_parallel_gather_with_mocked_httpx(self):
        def make_client_for(content: str):
            mock_resp = MagicMock()
            mock_resp.raise_for_status.return_value = None
            mock_resp.json.return_value = {
                "choices": [{"message": {"content": content}}]
            }
            client = AsyncMock()
            client.post = AsyncMock(return_value=mock_resp)
            client.__aenter__ = AsyncMock(return_value=client)
            client.__aexit__ = AsyncMock(return_value=None)
            return client

        # All three models return the same consensus herb.
        shared = "建议「黄芪」补气。仅供参考请咨询医生。"
        clients = [make_client_for(shared) for _ in range(3)]
        client_iter = iter(clients)

        with patch("app.llm.has_api_key", return_value=True), \
             patch("app.llm.httpx.AsyncClient", side_effect=lambda *a, **kw: next(client_iter)):
            result = await chat_completion_voting("气虚怎么办？")

        assert result["confidence_score"] >= 0.9
        assert "黄芪" in result["consensus_herbs"]
        assert result["metadata"]["responded"] == 3

    @pytest.mark.asyncio
    async def test_sequential_fallback_chain_unchanged(self):
        """Regression guard: existing chat_completion fallback chain still works."""
        from app.llm import _get_model_chain

        chain = _get_model_chain()
        assert chain[0] == "Kimi-K2.6"
        assert "GLM-5" in chain
        assert len(chain) == len(set(chain))
