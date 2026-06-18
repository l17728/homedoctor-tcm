"""Tests for expert_review_schedule() and _parse_review_json() in schedule_engine.

Covers (currently ZERO tests for these functions):
- _parse_review_json: valid JSON, markdown-wrapped, garbled, partial fields
- expert_review_schedule: no API key skip, 2/3 consensus pass, 1/3 fail, all-error fail

All LLM calls are mocked — no real API calls are made.
"""

from __future__ import annotations

import json
from unittest import mock

import pytest

from app.schedule_engine import _parse_review_json, expert_review_schedule


# ---------------------------------------------------------------------------
# Sample schedule / medications fixtures for expert_review_schedule
# ---------------------------------------------------------------------------

_SCHEDULE_INPUT = {
    "days": [
        {"day": "周一", "slots": [
            {"time": "08:00", "period": "早餐后",
             "medicines": [{"name": "黄芪", "dosage": "10g", "type": "中药"}]},
        ]},
    ],
    "conflicts_found": [],
    "synergies_found": [],
    "spacing_rules": [],
}

_MEDS_INPUT = [
    {"name": "黄芪", "type": "中药", "dosage": "10g", "frequency": "每日1次"},
]


# ---------------------------------------------------------------------------
# _parse_review_json — pure function tests
# ---------------------------------------------------------------------------

def test_parse_review_json_valid():
    """Well-formed JSON parses correctly with all fields populated."""
    raw = json.dumps({
        "safety_score": 5,
        "timing_score": 4,
        "dosage_score": 5,
        "completeness_score": 4,
        "overall_score": 5,
        "approved": True,
        "concerns": ["无重大安全风险"],
        "suggestions": ["建议餐后服用"],
    })
    result = _parse_review_json(raw)

    assert result["safety_score"] == 5
    assert result["timing_score"] == 4
    assert result["dosage_score"] == 5
    assert result["completeness_score"] == 4
    assert result["overall_score"] == 5
    assert result["approved"] is True
    assert result["concerns"] == ["无重大安全风险"]
    assert result["suggestions"] == ["建议餐后服用"]


def test_parse_review_json_markdown_wrapped():
    """JSON inside a ```json ... ``` markdown block still parses."""
    payload = {
        "safety_score": 4,
        "timing_score": 3,
        "dosage_score": 4,
        "completeness_score": 3,
        "overall_score": 4,
        "approved": True,
        "concerns": [],
        "suggestions": ["注意监测"],
    }
    raw = f"好的，以下是评审结果：\n```json\n{json.dumps(payload, ensure_ascii=False)}\n```\n谢谢！"
    result = _parse_review_json(raw)

    assert result["safety_score"] == 4
    assert result["overall_score"] == 4
    assert result["approved"] is True
    assert result["suggestions"] == ["注意监测"]


def test_parse_review_json_garbled_returns_defaults():
    """Completely garbled text (no parseable JSON) returns defaults, approved=False."""
    raw = "这是一段完全无法解析的文本，没有任何JSON结构。"
    result = _parse_review_json(raw)

    # Defaults: all scores 3
    assert result["safety_score"] == 3
    assert result["timing_score"] == 3
    assert result["dosage_score"] == 3
    assert result["completeness_score"] == 3
    assert result["overall_score"] == 3
    # No "通过"/"approve" keyword → approved False
    assert result["approved"] is False
    assert result["concerns"] == []
    assert result["suggestions"] == []


def test_parse_review_json_partial_fields():
    """JSON with missing fields defaults the missing scores to 3."""
    # Only approved + overall_score provided; others missing
    raw = json.dumps({"approved": True, "overall_score": 4})
    result = _parse_review_json(raw)

    # Provided fields preserved
    assert result["overall_score"] == 4
    assert result["approved"] is True
    # Missing fields default to 3
    assert result["safety_score"] == 3
    assert result["timing_score"] == 3
    assert result["dosage_score"] == 3
    assert result["completeness_score"] == 3
    # concerns/suggestions default to empty
    assert result["concerns"] == []
    assert result["suggestions"] == []


# ---------------------------------------------------------------------------
# expert_review_schedule — async function tests (LLM mocked)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_expert_review_no_api_key_skips():
    """Without LLM_API_KEY, review is skipped with consensus_pass=True."""
    with mock.patch("app.llm.settings") as mock_settings:
        mock_settings.LLM_API_KEY = ""
        result = await expert_review_schedule(_SCHEDULE_INPUT, _MEDS_INPUT)

    assert result["consensus_pass"] is True
    assert result["reviews"] == []
    # Note should mention skip / API key
    assert "跳过" in result["note"] or "API" in result["note"] or "密钥" in result["note"]


@pytest.mark.asyncio
async def test_expert_review_consensus_2_of_3():
    """When 2 of 3 models approve, consensus_pass=True (threshold = 2)."""
    # Models in source: ["Kimi-K2.6", "GLM-5", "qwen3-235b-a22b"]
    # Make Kimi-K2.6 and GLM-5 approve, qwen3 reject.

    async def fake_chat(messages, model, **kwargs):
        if model in ("Kimi-K2.6", "GLM-5"):
            return json.dumps({
                "safety_score": 5, "timing_score": 4, "dosage_score": 5,
                "completeness_score": 4, "overall_score": 5,
                "approved": True, "concerns": [], "suggestions": [],
            })
        # qwen3 rejects
        return json.dumps({
            "safety_score": 2, "timing_score": 2, "dosage_score": 2,
            "completeness_score": 2, "overall_score": 2,
            "approved": False, "concerns": ["剂量偏大"], "suggestions": ["减量"],
        })

    with mock.patch("app.llm.settings") as mock_settings, \
            mock.patch("app.llm.chat_completion", new=fake_chat):
        mock_settings.LLM_API_KEY = "test-key"
        result = await expert_review_schedule(_SCHEDULE_INPUT, _MEDS_INPUT)

    assert result["consensus_pass"] is True
    # approval_count should be "2/3"
    assert result["approval_count"] == "2/3"
    assert len(result["reviews"]) == 3
    # Each review tagged with its model name
    model_names = [r["model"] for r in result["reviews"]]
    assert "Kimi-K2.6" in model_names
    assert "GLM-5" in model_names
    assert "qwen3-235b-a22b" in model_names


@pytest.mark.asyncio
async def test_expert_review_consensus_1_of_3():
    """When only 1 of 3 models approves, consensus_pass=False."""
    async def fake_chat(messages, model, **kwargs):
        if model == "Kimi-K2.6":
            return json.dumps({
                "safety_score": 4, "overall_score": 4,
                "approved": True, "concerns": [], "suggestions": [],
            })
        # GLM-5 and qwen3 both reject
        return json.dumps({
            "safety_score": 2, "overall_score": 2,
            "approved": False, "concerns": ["风险"], "suggestions": ["停药"],
        })

    with mock.patch("app.llm.settings") as mock_settings, \
            mock.patch("app.llm.chat_completion", new=fake_chat):
        mock_settings.LLM_API_KEY = "test-key"
        result = await expert_review_schedule(_SCHEDULE_INPUT, _MEDS_INPUT)

    assert result["consensus_pass"] is False
    assert result["approval_count"] == "1/3"


@pytest.mark.asyncio
async def test_expert_review_all_fail_returns_errors():
    """When all 3 models raise exceptions, consensus_pass=False and each has error."""
    async def failing_chat(messages, model, **kwargs):
        raise RuntimeError(f"model {model} unavailable")

    with mock.patch("app.llm.settings") as mock_settings, \
            mock.patch("app.llm.chat_completion", new=failing_chat):
        mock_settings.LLM_API_KEY = "test-key"
        result = await expert_review_schedule(_SCHEDULE_INPUT, _MEDS_INPUT)

    assert result["consensus_pass"] is False
    assert result["approval_count"] == "0/3"
    # Each review should record the error and approved=False
    for review in result["reviews"]:
        assert review["approved"] is False
        assert "error" in review
        assert review["error"]  # non-empty error message
