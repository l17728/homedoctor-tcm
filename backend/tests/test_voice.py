"""Tests for the voice router (spec §13.2 V2 — 语音问答全链路).

These tests exercise graceful degradation (no ASR/TTS engines installed) and
the full /qa pipeline (ASR-unavailable → fallback, ASR-mocked → chat chaining).
Auth is required for every endpoint.
"""

from __future__ import annotations

import io
import json
from unittest import mock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

WAV_MAGIC = b"RIFF\x24\x00\x00\x00WAVE"


def _audio_file(data: bytes = WAV_MAGIC, filename: str = "clip.wav",
                content_type: str = "audio/wav"):
    """Build a multipart file tuple for httpx: (filename, fileobj, content_type)."""
    return (filename, io.BytesIO(data), content_type)


# ---------------------------------------------------------------------------
# Auth — every voice endpoint requires a valid token
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_transcribe_requires_auth(client):
    resp = await client.post("/api/voice/transcribe", files={"audio": ("c.wav", io.BytesIO(b"x"), "audio/wav")})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_synthesize_requires_auth(client):
    resp = await client.post("/api/voice/synthesize", json={"text": "你好"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_qa_requires_auth(client):
    resp = await client.post("/api/voice/qa", files={"audio": ("c.wav", io.BytesIO(b"x"), "audio/wav")})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# ASR — POST /api/voice/transcribe
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_transcribe_graceful_degradation(client, auth_headers):
    """No whisper installed → structured fallback telling the FE to use browser ASR."""
    resp = await client.post(
        "/api/voice/transcribe",
        files={"audio": _audio_file()},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["transcript"] is None
    assert body["available"] is False
    assert "browser speech input" in body["error"]


@pytest.mark.asyncio
async def test_transcribe_rejects_unsupported_type(client, auth_headers):
    resp = await client.post(
        "/api/voice/transcribe",
        files={"audio": ("file.txt", io.BytesIO(b"hello"), "text/plain")},
        headers=auth_headers,
    )
    assert resp.status_code == 415


@pytest.mark.asyncio
async def test_transcribe_rejects_empty_file(client, auth_headers):
    resp = await client.post(
        "/api/voice/transcribe",
        files={"audio": ("empty.wav", io.BytesIO(b""), "audio/wav")},
        headers=auth_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_transcribe_accepts_generic_octet_stream(client, auth_headers):
    """Browsers sometimes send application/octet-stream for recorded blobs."""
    resp = await client.post(
        "/api/voice/transcribe",
        files={"audio": ("blob", io.BytesIO(WAV_MAGIC), "application/octet-stream")},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["available"] is False  # graceful degradation


@pytest.mark.asyncio
async def test_transcribe_with_mock_whisper(client, auth_headers):
    """When a fake whisper module is present, transcribe returns real text."""
    fake_whisper = mock.MagicMock()

    class _FakeModel:
        def transcribe(self, path):  # noqa: ANN001
            return {"text": " 黄芪有什么功效 ", "language": "zh"}

    fake_whisper.load_model.return_value = _FakeModel()

    with mock.patch("app.routers.voice._load_whisper", return_value=fake_whisper), \
            mock.patch("app.routers.voice._get_whisper_model", return_value=_FakeModel()):
        resp = await client.post(
            "/api/voice/transcribe",
            files={"audio": _audio_file()},
            headers=auth_headers,
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["transcript"] == "黄芪有什么功效"  # stripped
    assert body["available"] is True
    assert body["engine"] == "whisper"
    assert body["language"] == "zh"


# ---------------------------------------------------------------------------
# TTS — POST /api/voice/synthesize
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_synthesize_graceful_degradation(client, auth_headers):
    """No pyttsx3 installed → structured fallback telling the FE to use browser TTS."""
    resp = await client.post(
        "/api/voice/synthesize",
        json={"text": "这是一段测试语音"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is False
    assert "browser speech synthesis" in body["error"]


@pytest.mark.asyncio
async def test_synthesize_validates_text_required(client, auth_headers):
    resp = await client.post(
        "/api/voice/synthesize",
        json={"text": ""},
        headers=auth_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_synthesize_rate_bounds(client, auth_headers):
    resp = await client.post(
        "/api/voice/synthesize",
        json={"text": "测试", "rate": 5.0},
        headers=auth_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_synthesize_with_mock_pyttsx3(client, auth_headers, tmp_path):
    """When a fake pyttsx3 is present, synthesize returns base64 audio."""
    fake_pyttsx3 = mock.MagicMock()

    class _FakeEngine:
        def __init__(self) -> None:
            self._props = {"rate": 200}

        def init(self):  # noqa: ANN001
            return self

        def getProperty(self, name):  # noqa: ANN001
            return self._props.get(name)

        def setProperty(self, name, value):  # noqa: ANN001
            self._props[name] = value

        def save_to_file(self, text, path):  # noqa: ANN001
            with open(path, "wb") as fh:
                fh.write(b"RIFFFAKEWAVE")

        def runAndWait(self):  # noqa: ANN001
            pass

    engine = _FakeEngine()
    fake_pyttsx3.init.return_value = engine

    with mock.patch("app.routers.voice._load_pyttsx3", return_value=fake_pyttsx3):
        resp = await client.post(
            "/api/voice/synthesize",
            json={"text": "你好世界", "rate": 1.2, "voice": "zh"},
            headers=auth_headers,
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is True
    assert body["engine"] == "pyttsx3"
    assert body["format"] == "wav"
    assert isinstance(body["audio_base64"], str)
    assert len(body["audio_base64"]) > 0


# ---------------------------------------------------------------------------
# Full pipeline — POST /api/voice/qa
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_qa_asr_unavailable_returns_fallback(client, auth_headers):
    """No ASR engine → QA returns transcript=None with the ASR fallback marker."""
    resp = await client.post(
        "/api/voice/qa",
        files={"audio": _audio_file()},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["transcript"] is None
    assert body["reply"] is None
    assert body["audio_base64"] is None
    assert body["asr"]["available"] is False
    assert "browser speech input" in body["asr"]["error"]


@pytest.mark.asyncio
async def test_qa_chains_transcribe_chat_synthesize(client, auth_headers):
    """With a mocked ASR + TTS, QA returns transcript + AI reply + audio."""
    fake_whisper = mock.MagicMock()

    class _FakeModel:
        def transcribe(self, path):  # noqa: ANN001
            return {"text": "感冒了怎么办", "language": "zh"}

    fake_pyttsx3 = mock.MagicMock()

    class _FakeEngine:
        def init(self):  # noqa: ANN001
            return self

        def getProperty(self, name):  # noqa: ANN001
            return 200

        def setProperty(self, name, value):  # noqa: ANN001
            pass

        def save_to_file(self, text, path):  # noqa: ANN001
            with open(path, "wb") as fh:
                fh.write(b"RIFFQAUDIO")

        def runAndWait(self):  # noqa: ANN001
            pass

    engine = _FakeEngine()
    fake_pyttsx3.init.return_value = engine

    with mock.patch("app.routers.voice._load_whisper", return_value=fake_whisper), \
            mock.patch("app.routers.voice._get_whisper_model", return_value=_FakeModel()), \
            mock.patch("app.routers.voice._load_pyttsx3", return_value=fake_pyttsx3):
        resp = await client.post(
            "/api/voice/qa",
            files={"audio": _audio_file()},
            data={"history": "[]"},
            headers=auth_headers,
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["transcript"] == "感冒了怎么办"
    # The chat endpoint returns a reply (mock or real LLM) — never empty.
    assert isinstance(body["reply"], str) and len(body["reply"]) > 0
    assert body["asr"]["available"] is True
    assert body["asr"]["engine"] == "whisper"
    assert body["tts"]["available"] is True
    assert body["tts"]["engine"] == "pyttsx3"
    assert isinstance(body["audio_base64"], str) and len(body["audio_base64"]) > 0


@pytest.mark.asyncio
async def test_qa_chains_transcribe_chat_without_tts(client, auth_headers):
    """ASR mocked, TTS absent → QA still returns transcript + reply (no audio)."""
    fake_whisper = mock.MagicMock()

    class _FakeModel:
        def transcribe(self, path):  # noqa: ANN001
            return {"text": "黄芪补气吗", "language": "zh"}

    with mock.patch("app.routers.voice._load_whisper", return_value=fake_whisper), \
            mock.patch("app.routers.voice._get_whisper_model", return_value=_FakeModel()), \
            mock.patch("app.routers.voice._load_pyttsx3", return_value=None):
        resp = await client.post(
            "/api/voice/qa",
            files={"audio": _audio_file()},
            headers=auth_headers,
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["transcript"] == "黄芪补气吗"
    assert isinstance(body["reply"], str) and len(body["reply"]) > 0
    assert body["asr"]["available"] is True
    assert body["tts"]["available"] is False
    assert body["audio_base64"] is None


@pytest.mark.asyncio
async def test_qa_passes_history_to_chat(client, auth_headers):
    """The optional history form field is forwarded to the chat endpoint."""
    fake_whisper = mock.MagicMock()

    class _FakeModel:
        def transcribe(self, path):  # noqa: ANN001
            return {"text": "再详细说说", "language": "zh"}

    with mock.patch("app.routers.voice._load_whisper", return_value=fake_whisper), \
            mock.patch("app.routers.voice._get_whisper_model", return_value=_FakeModel()):
        resp = await client.post(
            "/api/voice/qa",
            files={"audio": _audio_file()},
            data={"history": json.dumps([{"role": "user", "content": "感冒了"}])},
            headers=auth_headers,
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["transcript"] == "再详细说说"
    assert isinstance(body["reply"], str) and len(body["reply"]) > 0


@pytest.mark.asyncio
async def test_qa_rejects_unsupported_audio(client, auth_headers):
    resp = await client.post(
        "/api/voice/qa",
        files={"audio": ("f.txt", io.BytesIO(b"hi"), "text/plain")},
        headers=auth_headers,
    )
    assert resp.status_code == 415


@pytest.mark.asyncio
async def test_qa_safety_keyword_interception(client, auth_headers):
    """When ASR transcribes an emergency keyword, the chat layer must intercept.

    '胸痛' is in the 29 emergency keywords → reply == EMERGENCY_WARNING, not AI text.
    """
    from app.safety_keywords import EMERGENCY_WARNING

    fake_whisper = mock.MagicMock()

    class _FakeModel:
        def transcribe(self, path):  # noqa: ANN001
            return {"text": "我突然胸痛", "language": "zh"}

    with mock.patch("app.routers.voice._load_whisper", return_value=fake_whisper), \
            mock.patch("app.routers.voice._get_whisper_model", return_value=_FakeModel()):
        resp = await client.post(
            "/api/voice/qa",
            files={"audio": _audio_file()},
            headers=auth_headers,
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["transcript"] == "我突然胸痛"
    assert body["reply"] == EMERGENCY_WARNING
    assert body["safety_warning"] == EMERGENCY_WARNING


# ---------------------------------------------------------------------------
# OpenAPI / router registration smoke test
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_voice_endpoints_in_openapi(client):
    """All three voice endpoints are registered and documented."""
    resp = await client.get("/openapi.json")
    assert resp.status_code == 200
    paths = resp.json()["paths"]
    assert "/api/voice/transcribe" in paths
    assert "/api/voice/synthesize" in paths
    assert "/api/voice/qa" in paths
