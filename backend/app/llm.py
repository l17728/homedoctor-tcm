"""LLM client for Huawei Cloud Kimi-K2.6 (Direct API + 轻量编排层, spec §8.6).

Features:
- Model fallback chain: Kimi-K2.6 → GLM-5 → Qwen3-235B → DeepSeek-V3
- Hallucination defense: validates herb/formula names against DB (spec §8.5)
- Multimodal: text + image via Qwen2.5-VL-72B with OCR fallback
- SSE streaming for real-time response display
"""

from __future__ import annotations

import base64
import io
import json
import logging
import re
from typing import Any, AsyncIterator

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

CHAT_COMPLETIONS_URL = f"{settings.LLM_BASE_URL}/chat/completions"
VISION_COMPLETIONS_URL = f"{settings.LLM_VISION_BASE_URL}/chat/completions"

DISCLAIMER = "⚠️ 以上建议仅供参考，不替代医生面诊。如有不适请及时就医。"

HALLUCINATION_WARNING = (
    "\n\n⚠️ **安全提示**：以上回复中提到的部分药材名称未经系统知识库验证，"
    "请务必咨询执业中医师确认其真实性与适用性。"
)

# L2: RAG grounding — appended when AI claims efficacy that doesn't match DB
GROUNDING_WARNING = (
    "\n\n⚠️ 以上回复中关于部分药材功效的描述未经知识库验证（待验证），"
    "请咨询专业医师确认。"
)

# L3: LLM-as-Judge — prepended when judge model scores < 3
JUDGE_WARNING = "⚠️ 本回答可能存在不准确之处，请咨询专业医师确认。\n\n"

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


def _get_model_chain() -> list[str]:
    """Return ordered list of models to try: primary first, then fallbacks."""
    models = [settings.LLM_MODEL]
    fallbacks = [m.strip() for m in settings.LLM_FALLBACK_MODELS.split(",") if m.strip()]
    for m in fallbacks:
        if m not in models:
            models.append(m)
    return models


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
    base_payload = {
        "messages": [
            {"role": "system", "content": build_system_prompt(constitution)},
            *messages,
        ],
        "temperature": 0.7,
        "max_tokens": 2048,
    }

    model_chain = _get_model_chain()
    last_error: str = ""

    for i, model in enumerate(model_chain):
        payload = {**base_payload, "model": model}
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(CHAT_COMPLETIONS_URL, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                if i > 0:
                    logger.info("LLM fallback succeeded with model: %s", model)
                question = _extract_user_question(messages)
                validated, _meta = await _apply_hallucination_defenses(
                    question, content, primary_model=model
                )
                return validated
        except httpx.HTTPStatusError as e:
            last_error = f"{e.response.status_code}: {e.response.text[:200]}"
            logger.warning("LLM model %s failed (HTTP %s), trying next fallback", model, e.response.status_code)
        except Exception as e:
            last_error = str(e)
            logger.warning("LLM model %s failed (%s), trying next fallback", model, e)

    logger.error("All %d models in fallback chain failed. Last error: %s", len(model_chain), last_error)
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
            content = data["choices"][0]["message"]["content"]
            validated = await _validate_and_augment(content)
            return validated
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


async def _validate_and_augment(content: str) -> str:
    """Hallucination defense — validate herb/formula names against DB (spec §8.5).

    Extracts Chinese herb names from LLM output and cross-checks against the
    herbs table. If unknown names are found, appends a safety warning.
    """
    try:
        mentioned = _extract_herb_names(content)
        if not mentioned:
            return content

        unknown = await _check_herbs_exist(mentioned)
        if unknown:
            logger.warning("Hallucination defense: unknown herbs in LLM output: %s", unknown)
            if HALLUCINATION_WARNING not in content:
                return content + HALLUCINATION_WARNING
        return content
    except Exception as e:
        logger.debug("Hallucination validation skipped: %s", e)
        return content


# ---------------------------------------------------------------------------
# L2: RAG Grounding Check — verify AI claims match DB efficacy (spec §8.5)
# ---------------------------------------------------------------------------

_EFFICACY_KEYWORDS = frozenset({
    "补气", "补血", "补阴", "补阳", "滋阴", "温阳", "益气", "养血",
    "生津", "健脾", "益胃", "补脾", "补肾", "养心", "益肺", "润肺",
    "清热", "解毒", "凉血", "退热", "泻火", "燥湿", "除烦",
    "活血", "化瘀", "理气", "行气", "行滞", "通痹", "通络", "化积",
    "安神", "平肝", "潜阳", "熄风", "明目", "开窍", "醒神",
    "固表", "敛肺", "涩肠", "涩精", "缩尿", "固精", "止汗", "止血",
    "利水", "祛湿", "化痰", "止咳", "平喘", "消肿", "祛风", "散寒",
    "温中", "化湿", "祛痰", "缓急", "和中",
    "调经", "止痛", "通便", "润肠", "排脓", "托毒", "敛疮", "生肌",
    "升阳", "解表", "透疹", "降逆", "止呕", "利尿", "发汗",
    "消食", "驱虫", "杀虫", "调和",
})


def _extract_efficacy_keywords(text: str) -> set[str]:
    """Return the subset of known TCM efficacy keywords found in *text*."""
    return {kw for kw in _EFFICACY_KEYWORDS if kw in text}


def _get_herb_context(text: str, herb_name: str, window: int = 40) -> str:
    """Concatenate text windows (±window chars) around every occurrence of *herb_name*."""
    parts: list[str] = []
    idx = 0
    while True:
        pos = text.find(herb_name, idx)
        if pos == -1:
            break
        start = max(0, pos - window)
        end = min(len(text), pos + len(herb_name) + window)
        parts.append(text[start:end])
        idx = pos + len(herb_name)
    return " ".join(parts)


async def _check_grounding(
    content: str,
    db: Any = None,
) -> tuple[str, list[str]]:
    """L2: RAG grounding check (spec §8.5).

    For each herb mentioned that exists in the DB, extract efficacy keywords
    from the surrounding text and compare against the herb's DB ``efficacy``
    field.  If the AI makes efficacy claims with **zero** overlap, the herb is
    flagged as ungrounded and a ``待验证`` warning is appended.

    Returns ``(possibly_augmented_content, list_of_ungrounded_herb_names)``.
    """
    ungrounded: list[str] = []

    if db is None:
        try:
            from app.database import get_db
            db = get_db()
        except RuntimeError:
            return content, ungrounded

    try:
        mentioned = _extract_herb_names(content)
        if not mentioned:
            return content, ungrounded

        for name in mentioned:
            row = await db.query_one(
                "SELECT efficacy FROM herbs WHERE name = ? OR aliases LIKE ? LIMIT 1",
                (name, f"%{name}%"),
            )
            if not row or not row.get("efficacy"):
                continue

            db_keywords = _extract_efficacy_keywords(row["efficacy"])
            if not db_keywords:
                continue

            context = _get_herb_context(content, name)
            claimed_keywords = _extract_efficacy_keywords(context)

            if claimed_keywords and not (claimed_keywords & db_keywords):
                ungrounded.append(name)
    except Exception as e:
        logger.debug("Grounding check skipped: %s", e)
        return content, ungrounded

    if ungrounded and GROUNDING_WARNING not in content:
        content = content + GROUNDING_WARNING

    return content, ungrounded


# ---------------------------------------------------------------------------
# L3: LLM-as-Judge — independent model scores response accuracy (spec §8.5)
# ---------------------------------------------------------------------------

JUDGE_PROMPT_TEMPLATE = (
    "请评分以下中医健康问答的准确性（1-5分）：\n"
    "问题：{question}\n"
    "回答：{answer}\n"
    "评分标准：5=完全准确，4=基本准确，3=部分准确，2=存在错误，1=严重错误\n"
    "只返回数字。"
)


def _get_judge_model(primary_model: str) -> str:
    """Return a *different* model from the fallback chain for cross-evaluation."""
    for m in _get_model_chain():
        if m != primary_model:
            return m
    return primary_model


def _parse_judge_score(response: str) -> int | None:
    """Extract the first digit 1-5 from the judge response text."""
    match = re.search(r"[1-5]", response)
    return int(match.group()) if match else None


async def _judge_response(
    question: str,
    answer: str,
    primary_model: str,
) -> int | None:
    """L3: LLM-as-Judge (spec §8.5).

    Sends the question + answer to a **different** model for an independent
    accuracy score (1-5).  Returns the score, or ``None`` on failure so the
    caller can gracefully degrade without blocking the response.
    """
    if not has_api_key():
        return None

    judge_model = _get_judge_model(primary_model)
    prompt = JUDGE_PROMPT_TEMPLATE.format(
        question=str(question)[:500],
        answer=str(answer)[:2000],
    )

    headers = {
        "Authorization": f"Bearer {settings.LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": judge_model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
        "max_tokens": 16,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(CHAT_COMPLETIONS_URL, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            judge_text = data["choices"][0]["message"]["content"]
            score = _parse_judge_score(judge_text)
            if score is not None:
                logger.info("L3 judge score=%d (model=%s)", score, judge_model)
            return score
    except Exception as e:
        logger.warning("L3 judge failed — graceful skip: %s", e)
        return None


# ---------------------------------------------------------------------------
# Unified hallucination defense pipeline (L1 → L2 → L3)
# ---------------------------------------------------------------------------

def _extract_user_question(messages: list[dict[str, str]]) -> str:
    """Extract the most recent user message text from the messages list."""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg["content"]
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        return part.get("text", "")
                return ""
            return str(content)
    return ""


async def _apply_hallucination_defenses(
    question: str,
    answer: str,
    db: Any = None,
    primary_model: str = "",
) -> tuple[str, dict[str, Any]]:
    """Apply all three hallucination defense layers (spec §8.5).

    L1: Herb name validation (existing ``_validate_and_augment``).
    L2: RAG grounding check (``_check_grounding``).
    L3: LLM-as-Judge (``_judge_response``).

    Returns ``(augmented_answer, metadata_dict)``.
    """
    metadata: dict[str, Any] = {}

    answer = await _validate_and_augment(answer)

    answer, l2_flags = await _check_grounding(answer, db)
    metadata["grounding_flags"] = l2_flags

    score = await _judge_response(question, answer, primary_model)
    if score is not None:
        metadata["judge_score"] = score
        if score < 3:
            answer = JUDGE_WARNING + answer

    return answer, metadata


_TCM_CONCEPT_TERMS = frozenset({
    "气虚", "阳虚", "阴虚", "痰湿", "湿热", "血瘀", "气郁", "特禀", "平和",
    "气虚质", "阳虚质", "阴虚质", "痰湿质", "湿热质", "血瘀质", "气郁质", "特禀质", "平和质",
    "风寒", "风热", "暑湿", "燥邪", "火邪", "寒邪", "湿邪",
    "风寒感冒", "风热感冒", "阴虚火旺", "阳虚火旺", "肝阳上亢", "脾胃虚弱", "脾虚",
    "气虚乏力", "气血两虚", "肝肾不足", "肺气虚", "心气虚", "肾阳虚", "肾阴虚",
    "补气", "补血", "滋阴", "温阳", "清热", "解毒", "活血", "化瘀", "理气",
    "健脾", "益胃", "润肺", "安神", "平肝", "潜阳", "固表", "利水", "祛湿",
    "补气之长", "补肺健脾", "实卫敛汗", "托毒生肌", "利水消肿",
    "表实", "表虚", "实证", "虚证", "热证", "寒证", "里证",
})

_CJK_PATTERN = re.compile(r"^[\u4e00-\u9fff]+$")


def _extract_herb_names(text: str) -> list[str]:
    """Extract potential Chinese herb names from LLM output text.

    Conservative extraction — only flags names that:
    - Are 2-4 pure CJK characters (typical herb name length)
    - Are NOT common TCM diagnostic/concept terms
    """
    candidates: set[str] = set()

    for m in re.finditer(r"[「【《]([^」】》]+)[」】》]", text):
        name = m.group(1).strip()
        if _is_potential_herb_name(name):
            candidates.add(name)

    return list(candidates)


def _is_potential_herb_name(name: str) -> bool:
    """Check if a string looks like a herb name, not a TCM concept."""
    if not name or not _CJK_PATTERN.match(name):
        return False
    if not (2 <= len(name) <= 4):
        return False
    if name in _TCM_CONCEPT_TERMS:
        return False
    for term in _TCM_CONCEPT_TERMS:
        if term in name or name in term:
            return False
    return True


async def _check_herbs_exist(names: list[str]) -> list[str]:
    """Check which names do NOT exist in the herbs table. Returns list of unknowns."""
    from app.database import get_db

    try:
        db = get_db()
    except RuntimeError:
        return []

    unknown: list[str] = []
    for name in names:
        row = await db.query_one(
            "SELECT id FROM herbs WHERE name = ? OR aliases LIKE ? LIMIT 1",
            (name, f"%{name}%"),
        )
        if not row:
            formula_row = await db.query_one(
                "SELECT id FROM formulas WHERE name = ? LIMIT 1",
                (name,),
            )
            if not formula_row:
                unknown.append(name)

    return unknown


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
