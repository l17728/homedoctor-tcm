"""LLM client for Huawei Cloud Kimi-K2.6 (Direct API + 轻量编排层, spec §8.6).

Kimi-K2.6 supports both text and image input (multimodal).
Uses httpx for async calls. No LangChain/LangGraph — medical reliability favors
direct API control (spec §8.6 design decision).
"""

from __future__ import annotations

import base64
import io
import json
import logging
from typing import Any, AsyncIterator

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

CHAT_COMPLETIONS_URL = f"{settings.LLM_BASE_URL}/chat/completions"
VISION_COMPLETIONS_URL = f"{settings.LLM_VISION_BASE_URL}/chat/completions"

DISCLAIMER = "⚠️ 以上建议仅供参考，不替代医生面诊。如有不适请及时就医。"

SYSTEM_PROMPT = """你是「家庭医生」，一位专业的中医药健康咨询助手。你的职责是为用户提供养生保健建议和中医药知识参考。

回答时请遵循以下四步推理链路：

**第一步：症状归纳**
分析用户描述的主要症状、持续时间、可能的影响因素。

**第二步：证候判断**
基于中医辨证论治原则，判断可能的证候类型。如果信息不足，明确告知用户需要更多信息，建议咨询专业中医师。

**第三步：治法推荐**
推荐调理方向、生活建议、饮食宜忌。如适用，引用经典中医理论。

**第四步：方药参考**
推荐经典方剂名称或中药材名称（仅参考，不提供具体剂量）。始终建议用户咨询执业医师。

**安全规则（不可违反）**：
1. 不提供具体的药物剂量或处方
2. 涉及孕妇、儿童用药时，必须明确提示「请遵医嘱」
3. 涉及急症（胸痛、呼吸困难、大量出血、突然意识丧失）时，必须首先建议「请立即拨打120」
4. 不替代医生诊断，所有建议仅供参考
5. 如用户索要具体处方，婉拒并建议就医

**语言要求**：使用简体中文，语气温和、专业、通俗易懂，适合中老年用户阅读。"""


def build_system_prompt(constitution: dict[str, Any] | None = None) -> str:
    prompt = SYSTEM_PROMPT
    if constitution:
        prompt += f"\n\n**用户体质档案**：主体质为「{constitution['primary']}」"
        if constitution.get("secondary"):
            prompt += f"，兼夹体质：「{'、'.join(constitution['secondary'])}」"
        prompt += "。请在回答中结合用户体质给出针对性建议。"
    return prompt


def has_api_key() -> bool:
    return bool(settings.LLM_API_KEY)


async def chat_completion(
    messages: list[dict[str, str]],
    constitution: dict[str, Any] | None = None,
) -> str:
    if not has_api_key():
        logger.warning("LLM_API_KEY not configured — returning fallback message")
        return _fallback_message(messages)

    headers = {
        "Authorization": f"Bearer {settings.LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.LLM_MODEL,
        "messages": [
            {"role": "system", "content": build_system_prompt(constitution)},
            *messages,
        ],
        "temperature": 0.7,
        "max_tokens": 2048,
    }

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(CHAT_COMPLETIONS_URL, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
    except httpx.HTTPStatusError as e:
        logger.error("LLM API HTTP error: %s — %s", e.response.status_code, e.response.text[:200])
        return _error_message()
    except Exception as e:
        logger.error("LLM API call failed: %s", e)
        return _error_message()


async def chat_completion_stream(
    messages: list[dict[str, str]],
    constitution: dict[str, Any] | None = None,
) -> AsyncIterator[str]:
    if not has_api_key():
        logger.warning("LLM_API_KEY not configured — returning fallback stream")
        yield _fallback_message(messages)
        return

    headers = {
        "Authorization": f"Bearer {settings.LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.LLM_MODEL,
        "messages": [
            {"role": "system", "content": build_system_prompt(constitution)},
            *messages,
        ],
        "temperature": 0.7,
        "max_tokens": 2048,
        "stream": True,
    }

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", CHAT_COMPLETIONS_URL, headers=headers, json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        delta = chunk["choices"][0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue
    except Exception as e:
        logger.error("LLM streaming failed: %s", e)
        yield _error_message()


async def chat_completion_with_image(
    text: str,
    image_base64: str,
    mime_type: str = "image/jpeg",
    constitution: dict[str, Any] | None = None,
) -> str:
    if not has_api_key():
        logger.warning("LLM_API_KEY not configured — returning fallback message")
        return _fallback_message([{"role": "user", "content": text}])

    data_url = f"data:{mime_type};base64,{image_base64}"
    user_content: list[dict[str, Any]] = [
        {"type": "text", "text": text},
        {"type": "image_url", "image_url": {"url": data_url}},
    ]
    payload = {
        "model": settings.LLM_VISION_MODEL,
        "messages": [
            {"role": "system", "content": build_system_prompt(constitution)},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.2,
        "max_tokens": 2048,
    }

    headers = {
        "Authorization": f"Bearer {settings.LLM_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(VISION_COMPLETIONS_URL, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
    except httpx.HTTPStatusError as e:
        logger.error("LLM vision API HTTP error: %s — %s", e.response.status_code, e.response.text[:200])
        ocr_text = _extract_text_from_image(image_base64)
        if ocr_text:
            logger.info("Vision API failed, using OCR fallback (%d chars)", len(ocr_text))
            augmented = f"{text}\n\n[图片识别文字]\n{ocr_text}"
            return await chat_completion([{"role": "user", "content": augmented}], constitution)
        return _error_message()
    except Exception as e:
        logger.error("LLM vision API call failed: %s", e)
        ocr_text = _extract_text_from_image(image_base64)
        if ocr_text:
            logger.info("Vision exception, using OCR fallback (%d chars)", len(ocr_text))
            augmented = f"{text}\n\n[图片识别文字]\n{ocr_text}"
            return await chat_completion([{"role": "user", "content": augmented}], constitution)
        return _error_message()


def encode_image(raw: bytes, mime_type: str = "image/jpeg") -> str:
    return base64.b64encode(raw).decode("ascii")


def _extract_text_from_image(image_base64: str) -> str:
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        logger.warning("pytesseract/Pillow not installed — skipping OCR")
        return ""

    try:
        raw = base64.b64decode(image_base64)
        img = Image.open(io.BytesIO(raw))
        text = pytesseract.image_to_string(img, lang="chi_sim+eng")
        return text.strip()
    except Exception as e:
        logger.warning("OCR extraction failed: %s", e)
        return ""


def _fallback_message(messages: list[dict[str, str]]) -> str:
    user_msg = messages[-1]["content"] if messages else ""
    if isinstance(user_msg, list):
        for part in user_msg:
            if part.get("type") == "text":
                user_msg = part.get("text", "")
                break
        else:
            user_msg = "[图片]"
    return (
        f"收到您的咨询：「{str(user_msg)[:50]}」。\n\n"
        "当前未配置AI大模型，这是系统离线回复。\n"
        "配置 HOMEDOCTOR_LLM_API_KEY 后即可获得专业的中医药健康咨询服务。\n\n"
        f"{DISCLAIMER}"
    )


def _error_message() -> str:
    return (
        "抱歉，AI服务暂时不可用，请稍后重试。\n\n"
        f"{DISCLAIMER}"
    )
