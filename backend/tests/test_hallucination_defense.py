"""Tests for LLM hallucination defense (spec §8.5) and model fallback chain."""

from __future__ import annotations

import pytest

from app.llm import (
    _extract_herb_names,
    _validate_and_augment,
    _get_model_chain,
    HALLUCINATION_WARNING,
    DISCLAIMER,
)


class TestExtractHerbNames:
    def test_extracts_bracket_names(self):
        text = "建议使用「黄芪」和「当归」煲汤"
        names = _extract_herb_names(text)
        assert "黄芪" in names
        assert "当归" in names

    def test_extracts_book_title_names(self):
        text = "《伤寒论》中的「桂枝汤」可以参考"
        names = _extract_herb_names(text)
        assert "桂枝汤" in names

    def test_extracts_square_bracket_names(self):
        text = "推荐【板蓝根】冲剂"
        names = _extract_herb_names(text)
        assert "板蓝根" in names

    def test_returns_empty_for_no_herbs(self):
        text = "请多喝水，注意休息"
        names = _extract_herb_names(text)
        assert names == []

    def test_deduplicates_names(self):
        text = "「黄芪」很好，「黄芪」确实好"
        names = _extract_herb_names(text)
        assert names.count("黄芪") == 1


class TestModelFallbackChain:
    def test_primary_model_first(self):
        chain = _get_model_chain()
        assert chain[0] == "Kimi-K2.6"

    def test_includes_fallback_models(self):
        import app.config as config_mod
        original = config_mod.settings.LLM_FALLBACK_MODELS
        try:
            config_mod.settings.LLM_FALLBACK_MODELS = "GLM-5,qwen3-235b-a22b"
            chain = _get_model_chain()
            assert "GLM-5" in chain
            assert "qwen3-235b-a22b" in chain
            assert chain[0] == config_mod.settings.LLM_MODEL
        finally:
            config_mod.settings.LLM_FALLBACK_MODELS = original

    def test_no_duplicates(self):
        chain = _get_model_chain()
        assert len(chain) == len(set(chain))


class TestValidateAndAugment:
    @pytest.mark.asyncio
    async def test_no_warning_for_clean_text(self):
        text = "请多喝水，注意休息，保持心情愉快。"
        result = await _validate_and_augment(text)
        assert HALLUCINATION_WARNING not in result
        assert result == text

    @pytest.mark.asyncio
    async def test_no_warning_for_known_herb(self, db):
        import app.database as db_mod
        original_db = db_mod._db_adapter
        try:
            db_mod.set_db(db)
            text = "「黄芪」是常用补气药"
            result = await _validate_and_augment(text)
            assert HALLUCINATION_WARNING not in result
        finally:
            db_mod.set_db(original_db)

    @pytest.mark.asyncio
    async def test_warning_for_unknown_herb(self, db):
        import app.database as db_mod
        original_db = db_mod._db_adapter
        try:
            db_mod.set_db(db)
            text = "推荐「虚构灵草」治疗感冒"
            result = await _validate_and_augment(text)
            assert HALLUCINATION_WARNING in result
        finally:
            db_mod.set_db(original_db)

    @pytest.mark.asyncio
    async def test_no_duplicate_warning(self, db):
        import app.database as db_mod
        original_db = db_mod._db_adapter
        try:
            db_mod.set_db(db)
            text = f"推荐「虚构灵草」{HALLUCINATION_WARNING}"
            result = await _validate_and_augment(text)
            assert result.count(HALLUCINATION_WARNING) == 1
        finally:
            db_mod.set_db(original_db)

    @pytest.mark.asyncio
    async def test_graceful_without_db(self):
        import app.database as db_mod
        original_db = db_mod._db_adapter
        try:
            db_mod._db_adapter = None
            text = "「黄芪」是补气药"
            result = await _validate_and_augment(text)
            assert result == text
        finally:
            db_mod._db_adapter = original_db
