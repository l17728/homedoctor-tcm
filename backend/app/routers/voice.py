"""Voice router — speech-to-text (ASR), text-to-speech (TTS), and full voice
Q&A pipeline for elderly users who can't type (spec §13.2 V2, US-7a).

Design — graceful degradation (spec §13.2 降级方案):
    Backend ASR/TTS models (FunASR / CosyVoice2 / Whisper / pyttsx3) are
    *optional*. When absent, every endpoint returns a structured error telling
    the frontend to fall back to the browser's native Web Speech API
    (useSpeechRecognition / useSpeechSynthesis hooks). This keeps the backend
    deployable on CPU-only / lightweight hosts while the heavy models land in V2.

Endpoints:
    POST /api/voice/transcribe  — ASR: audio file → text
    POST /api/voice/synthesize  — TTS: text → audio
    POST /api/voice/qa          — full pipeline: audio → transcript → AI reply → audio
"""

from __future__ import annotations

import base64
import io
import logging
import os
import tempfile
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.auth import get_current_user
from app.upload_utils import read_upload_limited
from app.database import DbAdapter, get_db
from app.routers.chat import ChatRequest, chat as chat_endpoint

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/voice", tags=["voice"])


# ---------------------------------------------------------------------------
# Limits & accepted formats
# ---------------------------------------------------------------------------

#: Max accepted audio upload (25 MB — covers a minute of compressed speech).
MAX_AUDIO_SIZE = 25 * 1024 * 1024

#: Audio MIME types we are willing to accept for transcription.
ALLOWED_AUDIO_TYPES = {
    "audio/wav",
    "audio/x-wav",
    "audio/wave",
    "audio/mpeg",
    "audio/mp3",
    "audio/mp4",
    "audio/x-m4a",
    "audio/m4a",
    "audio/ogg",
    "audio/webm",
    "audio/x-webm",
    "audio/flac",
    "audio/x-flac",
    # Browsers sometimes send an empty/generic content-type for recorded blobs.
    "application/octet-stream",
    "",
}


# ---------------------------------------------------------------------------
# Engine detection helpers (lazy import — keeps models optional)
# ---------------------------------------------------------------------------

def _load_whisper():  # type: ignore[no-untyped-def]
    """Lazily import openai-whisper. Returns the module or None."""
    try:
        import whisper  # type: ignore[import-untyped]

        return whisper
    except Exception:  # pragma: no cover — exercised only when installed
        return None


def _load_pyttsx3():  # type: ignore[no-untyped-def]
    """Lazily import pyttsx3 (offline TTS). Returns the module or None."""
    try:
        import pyttsx3  # type: ignore[import-untyped]

        return pyttsx3
    except Exception:  # pragma: no cover — exercised only when installed
        return None


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class SynthesizeRequest(BaseModel):
    """TTS request — text plus optional rate / voice overrides."""

    text: str = Field(min_length=1, max_length=4000)
    rate: float = Field(default=1.0, ge=0.5, le=2.0)
    voice: str | None = None


# ---------------------------------------------------------------------------
# Shared upload validation
# ---------------------------------------------------------------------------

async def _read_audio(audio: UploadFile) -> bytes:
    """Validate and read an uploaded audio file. Raises HTTPException on error."""
    if audio.content_type and audio.content_type not in ALLOWED_AUDIO_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"不支持的音频格式：{audio.content_type or '未知'}。"
                "请上传 WAV/MP3/M4A/OGG/WebM/FLAC。"
            ),
        )

    raw = await read_upload_limited(
        audio, MAX_AUDIO_SIZE,
        f"音频大小不能超过 {MAX_AUDIO_SIZE // (1024 * 1024)}MB。",
    )
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="音频文件为空，请重新录制。",
        )
    return raw


def _detect_extension(filename: str | None, content_type: str | None) -> str:
    """Best-effort file extension for whisper tempfile."""
    if filename and "." in filename:
        return filename.rsplit(".", 1)[-1].lower() or "wav"
    ct = (content_type or "").lower()
    mapping = {
        "audio/wav": "wav", "audio/x-wav": "wav", "audio/wave": "wav",
        "audio/mpeg": "mp3", "audio/mp3": "mp3",
        "audio/mp4": "m4a", "audio/x-m4a": "m4a", "audio/m4a": "m4a",
        "audio/ogg": "ogg",
        "audio/webm": "webm", "audio/x-webm": "webm",
        "audio/flac": "flac", "audio/x-flac": "flac",
    }
    return mapping.get(ct, "wav")


def _asr_unavailable_response() -> JSONResponse:
    """Structured ASR-unavailable payload (HTTP 200 graceful degradation)."""
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "transcript": None,
            "available": False,
            "error": "ASR not available, please use browser speech input",
            "error_zh": "服务端语音识别暂未启用，请使用浏览器语音输入。",
            "engine": None,
        },
    )


def _tts_unavailable_response(detail: str | None = None) -> JSONResponse:
    """Structured TTS-unavailable payload (HTTP 200 graceful degradation)."""
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "available": False,
            "error": "TTS not available, please use browser speech synthesis",
            "error_zh": "服务端语音合成暂未启用，请使用浏览器语音播报。",
            "engine": None,
            "detail": detail,
        },
    )


# ---------------------------------------------------------------------------
# ASR — POST /api/voice/transcribe
# ---------------------------------------------------------------------------

@router.post("/transcribe")
async def transcribe(
    audio: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """Transcribe an uploaded audio clip to text (ASR).

    Uses ``openai-whisper`` when installed; otherwise returns a graceful
    degradation payload so the frontend can fall back to the browser's
    Web Speech API (spec §13.2 降级方案).
    """
    raw = await _read_audio(audio)

    whisper = _load_whisper()
    if whisper is None:
        logger.info("ASR requested but whisper not installed — returning fallback")
        return _asr_unavailable_response()

    # whisper.transcribe() needs a path on disk.
    ext = _detect_extension(audio.filename, audio.content_type)
    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
            tmp.write(raw)
            tmp_path = tmp.name

        model = _get_whisper_model(whisper)
        result = model.transcribe(tmp_path)  # pragma: no cover
        text = (result.get("text") if isinstance(result, dict) else result) or ""
        text = text.strip()  # pragma: no cover
        language = (
            result.get("language") if isinstance(result, dict) else None
        )  # pragma: no cover
    except Exception as exc:  # pragma: no cover
        logger.exception("Whisper transcription failed")
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "transcript": None,
                "available": True,
                "engine": "whisper",
                "error": "语音识别失败，请重试或使用浏览器语音输入。",
                "detail": str(exc),
            },
        )
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    return {  # pragma: no cover
        "transcript": text,
        "available": True,
        "engine": "whisper",
        "language": language,
    }


# Whisper model cache (loading is expensive) — module-level singleton.
_WHISPER_MODEL = None
_WHISPER_MODEL_NAME = os.environ.get("HOMEDOCTOR_ASR_MODEL", "base")


def _get_whisper_model(whisper_module):  # type: ignore[no-untyped-def]
    """Load (and cache) the whisper model. Only called when whisper exists."""
    global _WHISPER_MODEL
    if _WHISPER_MODEL is None:  # pragma: no cover
        _WHISPER_MODEL = whisper_module.load_model(_WHISPER_MODEL_NAME)
    return _WHISPER_MODEL


# ---------------------------------------------------------------------------
# TTS — POST /api/voice/synthesize
# ---------------------------------------------------------------------------

@router.post("/synthesize")
async def synthesize(
    body: SynthesizeRequest,
    current_user: dict = Depends(get_current_user),
):
    """Synthesize speech from text (TTS).

    Uses ``pyttsx3`` (offline) when installed; otherwise returns a graceful
    degradation payload so the frontend can fall back to the browser's
    SpeechSynthesis API (spec §13.2 降级方案).
    """
    pyttsx3 = _load_pyttsx3()
    if pyttsx3 is None:
        logger.info("TTS requested but pyttsx3 not installed — returning fallback")
        return _tts_unavailable_response()

    buffer = io.BytesIO()
    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name

        # pyttsx3 is synchronous and driver-bound; run inline (MVP).
        engine = pyttsx3.init()  # pragma: no cover
        if body.voice:
            try:  # pragma: no cover
                engine.setProperty("voice", body.voice)
            except Exception:  # pragma: no cover
                logger.debug("TTS voice '%s' not available", body.voice)
        try:  # pragma: no cover
            rate = engine.getProperty("rate")
            engine.setProperty("rate", int(rate * body.rate))
        except Exception:  # pragma: no cover
            pass
        engine.save_to_file(body.text, tmp_path)  # pragma: no cover
        engine.runAndWait()  # pragma: no cover

        with open(tmp_path, "rb") as fh:  # pragma: no cover
            wav_bytes = fh.read()
    except Exception as exc:  # pragma: no cover
        logger.exception("pyttsx3 synthesis failed")
        return _tts_unavailable_response(detail=str(exc))
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    if not wav_bytes:  # pragma: no cover
        return _tts_unavailable_response(detail="empty audio produced")

    buffer.write(wav_bytes)
    audio_b64 = base64.b64encode(buffer.getvalue()).decode("ascii")
    return {
        "available": True,
        "engine": "pyttsx3",
        "format": "wav",
        "audio_base64": audio_b64,
    }  # pragma: no cover


# ---------------------------------------------------------------------------
# Full voice pipeline — POST /api/voice/qa
# ---------------------------------------------------------------------------

@router.post("/qa")
async def voice_qa(
    audio: UploadFile = File(...),
    history: str = Form(default="[]"),
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """One-button elderly voice experience (spec US-7a).

    Pipeline: ``audio → ASR → /api/chat → TTS``.

    - If ASR is unavailable, returns a transcript=null + ASR fallback marker so
      the frontend knows to retry via the browser speech input.
    - The AI reply is always produced (reuses the chat endpoint logic, which
      applies safety-keyword interception + constitution context + disclaimer).
    - TTS is best-effort: if unavailable, ``audio_base64`` is omitted and the
      frontend uses its own SpeechSynthesis hook.
    """
    import json

    raw = await _read_audio(audio)

    # ---- 1. ASR ----------------------------------------------------------
    transcript: str | None = None
    asr_available = False
    asr_engine: str | None = None

    whisper = _load_whisper()
    if whisper is not None:
        ext = _detect_extension(audio.filename, audio.content_type)
        tmp_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
                tmp.write(raw)
                tmp_path = tmp.name
            model = _get_whisper_model(whisper)
            result = model.transcribe(tmp_path)  # pragma: no cover
            transcript = (
                (result.get("text") if isinstance(result, dict) else result) or ""
            ).strip()  # pragma: no cover
            asr_available = True  # pragma: no cover
            asr_engine = "whisper"  # pragma: no cover
        except Exception as exc:  # pragma: no cover
            logger.exception("Whisper transcription failed in /qa")
            asr_available = True
            asr_engine = "whisper"
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "transcript": None,
                    "reply": None,
                    "audio_base64": None,
                    "asr": {"available": True, "engine": "whisper",
                            "error": "语音识别失败，请重试。",
                            "detail": str(exc)},
                    "tts": {"available": False, "engine": None},
                },
            )
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    if not transcript:
        # ASR engine absent or produced nothing — graceful degradation.
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "transcript": None,
                "reply": None,
                "audio_base64": None,
                "asr": {
                    "available": asr_available,
                    "engine": asr_engine,
                    "error": "ASR not available, please use browser speech input",
                    "error_zh": "服务端语音识别暂未启用，请使用浏览器语音输入。",
                },
                "tts": {"available": False, "engine": None},
            },
        )

    # ---- 2. Chat (reuse the exact /api/chat logic) -----------------------
    try:
        parsed_history: list[dict[str, Any]] = []
        if history:
            parsed_history = json.loads(history)
            if not isinstance(parsed_history, list):
                parsed_history = []
    except (json.JSONDecodeError, TypeError):
        parsed_history = []

    chat_result = await chat_endpoint(
        ChatRequest(message=transcript, history=parsed_history),
        db=db,
        current_user=current_user,
    )
    reply_text: str = chat_result.get("reply", "") if isinstance(chat_result, dict) else ""

    # ---- 3. TTS (best-effort) -------------------------------------------
    tts_available = False
    tts_engine: str | None = None
    audio_b64: str | None = None

    pyttsx3 = _load_pyttsx3()
    if pyttsx3 is not None and reply_text:
        tmp_path2: str | None = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_path2 = tmp.name
            engine = pyttsx3.init()  # pragma: no cover
            engine.save_to_file(reply_text, tmp_path2)  # pragma: no cover
            engine.runAndWait()  # pragma: no cover
            with open(tmp_path2, "rb") as fh:  # pragma: no cover
                wav_bytes = fh.read()
            if wav_bytes:  # pragma: no cover
                audio_b64 = base64.b64encode(wav_bytes).decode("ascii")
                tts_available = True
                tts_engine = "pyttsx3"
        except Exception:  # pragma: no cover
            logger.exception("pyttsx3 synthesis failed in /qa")
        finally:
            if tmp_path2 and os.path.exists(tmp_path2):
                try:
                    os.unlink(tmp_path2)
                except OSError:
                    pass

    return {
        "transcript": transcript,
        "reply": reply_text,
        "audio_base64": audio_b64,
        "asr": {"available": asr_available, "engine": asr_engine},
        "tts": {"available": tts_available, "engine": tts_engine},
        "model_used": chat_result.get("model_used") if isinstance(chat_result, dict) else None,
        "safety_warning": chat_result.get("safety_warning") if isinstance(chat_result, dict) else None,
    }
