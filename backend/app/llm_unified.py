"""Unified LLM caller — single source of truth for all AI model access.

Two modes:
  Normal: direct API call (fast, single model) — for chat/search/analysis
  Enhanced: opencode collective decision (slow, multi-model) — for review/conflict/quality

Model config comes from ai_models table (UI-configurable), NOT env vars.

Usage:
    from app.llm_unified import llm_chat, llm_collective_review

    # Normal mode (fast)
    reply = await llm_chat(db, "分析这段中医内容...")

    # Enhanced mode (multi-model collective)
    result = await llm_collective_review(db, "评审此知识的医学准确性...", content)
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from app.database import DbAdapter

logger = logging.getLogger(__name__)

HUAWEI_ENDPOINT = "https://api.modelarts-maas.com/openai/v1/chat/completions"


async def llm_chat(
    db: DbAdapter,
    messages: list[dict[str, str]],
    temperature: float = 0.3,
    max_tokens: int = 2048,
) -> str:
    """Single-model direct API call. Uses default model from ai_models table."""
    import httpx
    from app.model_registry import get_default_models

    models = await get_default_models(db, "text")
    if not models:
        logger.warning("llm_unified: no models configured")
        return ""

    model = models[0]
    api_key = model.get("api_key", "")
    endpoint = model.get("api_endpoint", "") or HUAWEI_ENDPOINT

    if not api_key or "***" in api_key:
        logger.warning("llm_unified: api_key missing or masked")
        return ""

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                endpoint,
                json={
                    "model": model["model_id"],
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "stream": False,
                },
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            )
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
            else:
                for fallback_model in models[1:3]:
                    fb_key = fallback_model.get("api_key", "")
                    fb_endpoint = fallback_model.get("api_endpoint", "") or HUAWEI_ENDPOINT
                    if not fb_key or "***" in fb_key:
                        continue
                    resp2 = await client.post(
                        fb_endpoint,
                        json={"model": fallback_model["model_id"], "messages": messages,
                              "temperature": temperature, "max_tokens": max_tokens, "stream": False},
                        headers={"Authorization": f"Bearer {fb_key}", "Content-Type": "application/json"},
                    )
                    if resp2.status_code == 200:
                        return resp2.json()["choices"][0]["message"]["content"]
                logger.error("llm_unified: all models failed. Last: %s %s", resp.status_code, resp.text[:200])
                return ""
    except Exception as exc:
        logger.warning("llm_unified: call failed: %s", exc)
        return ""


async def llm_collective_review(
    db: DbAdapter,
    prompt: str,
    num_models: int = 4,
) -> dict[str, Any]:
    """Enhanced mode: multi-model collective decision via direct API.

    Sends same prompt to N different models in parallel, collects responses,
    returns consensus result.

    Returns: {responses, model_count, consensus_text, agreement}
    """
    import httpx
    from app.model_registry import get_default_models

    models = await get_default_models(db, "text")
    if not models:
        return {"responses": [], "model_count": 0, "consensus_text": "", "agreement": 0.0}

    selected = models[:num_models]
    messages = [{"role": "user", "content": prompt}]

    async def _call_one(model: dict) -> dict[str, Any]:
        api_key = model.get("api_key", "")
        endpoint = model.get("api_endpoint", "") or HUAWEI_ENDPOINT
        if not api_key or "***" in api_key:
            return {"model": model["name"], "text": "", "error": "no_key"}
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    endpoint,
                    json={"model": model["model_id"], "messages": messages,
                          "temperature": 0.3, "max_tokens": 2048, "stream": False},
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                )
                if resp.status_code == 200:
                    text = resp.json()["choices"][0]["message"]["content"]
                    return {"model": model["name"], "text": text}
                return {"model": model["name"], "text": "", "error": f"{resp.status_code}"}
        except Exception as exc:
            return {"model": model["name"], "text": "", "error": str(exc)[:100]}

    tasks = [_call_one(m) for m in selected]
    results = await asyncio.gather(*tasks)

    valid_texts = [r["text"] for r in results if r.get("text")]
    consensus = max(valid_texts, key=len) if valid_texts else ""
    agreement = len(valid_texts) / len(selected) if selected else 0.0

    return {
        "responses": results,
        "model_count": len(selected),
        "valid_count": len(valid_texts),
        "consensus_text": consensus,
        "agreement": round(agreement, 2),
    }


async def llm_collective_review_opencode(
    prompt: str,
    models: list[str] | None = None,
    timeout: int = 120,
) -> dict[str, Any]:
    """Enhanced mode via opencode subprocess — for coding plan models.

    Spawns N opencode CLI instances, each with a different model,
    sends same prompt, collects results.

    Models format: ["huawei_cloud/Kimi-K2.6", "huawei_cloud/GLM-5", ...]
    If None, reads from opencode config.
    """
    if models is None:
        models = _read_opencode_models()

    if not models:
        return {"responses": [], "model_count": 0, "consensus_text": ""}

    async def _run_opencode(model_id: str) -> dict[str, Any]:
        try:
            proc = await asyncio.create_subprocess_exec(
                "opencode", "-p", prompt, "--model", model_id,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            text = stdout.decode().strip()
            return {"model": model_id, "text": text}
        except asyncio.TimeoutError:
            return {"model": model_id, "text": "", "error": "timeout"}
        except Exception as exc:
            return {"model": model_id, "text": "", "error": str(exc)[:100]}

    tasks = [_run_opencode(m) for m in models]
    results = await asyncio.gather(*tasks)

    valid_texts = [r["text"] for r in results if r.get("text")]
    consensus = max(valid_texts, key=len) if valid_texts else ""

    return {
        "responses": results,
        "model_count": len(models),
        "valid_count": len(valid_texts),
        "consensus_text": consensus,
        "agreement": round(len(valid_texts) / len(models), 2) if models else 0,
    }


def _read_opencode_models() -> list[str]:
    """Read available models from opencode config."""
    import os
    config_path = os.path.expanduser("~/.config/opencode/opencode.json")
    if not os.path.exists(config_path):
        return []

    try:
        with open(config_path) as f:
            config = json.load(f)

        models: list[str] = []
        for provider_name, provider in config.get("provider", {}).items():
            for model_id in provider.get("models", {}):
                models.append(f"{provider_name}/{model_id}")

        return models[:10]
    except Exception:
        return []
