"""Tests for multimedia knowledge import — URL / video-link / audio / video.

Covers (spec §18 extension):
- URL import: httpx fetch + HTML text extraction
- YouTube URL parsing (youtube-transcript-api mocked)
- Bilibili URL → falls back to page text
- Audio file parsing (whisper mocked / graceful degradation when absent)
- Video file parsing (ffmpeg + whisper; both mocked / graceful degradation)
- HTTP endpoints: /import-url, /import-video-url, /import-file with .mp3/.mp4
- Existing file types still work (txt/pdf regression)
- Invalid URL handling
- Legacy /api/knowledge-import/upload still REJECTS multimedia (security boundary)

All external calls (httpx, whisper, youtube API) are mocked so the suite
runs offline without network access or heavy model downloads.
"""

from __future__ import annotations

import io
import os
import shutil
import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.knowledge_parser import (
    ALLOWED_EXTENSIONS,
    DOCUMENT_EXTENSIONS,
    MULTIMEDIA_EXTENSIONS,
    ParseResult,
    detect_file_type,
    is_video_url,
    parse_audio,
    parse_file,
    parse_url,
    parse_video_file,
    parse_video_url,
)


# ---------------------------------------------------------------------------
# is_video_url + extension constants
# ---------------------------------------------------------------------------

class TestIsVideoUrl:
    def test_youtube_com(self):
        assert is_video_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ") is True

    def test_youtu_be(self):
        assert is_video_url("https://youtu.be/dQw4w9WgXcQ") is True

    def test_bilibili(self):
        assert is_video_url("https://www.bilibili.com/video/BV1xx411c7mD") is True

    def test_b23_tv(self):
        assert is_video_url("https://b23.tv/abc123") is True

    def test_plain_article(self):
        assert is_video_url("https://example.com/article.html") is False

    def test_empty(self):
        assert is_video_url("") is False


class TestExtensionConstants:
    def test_multimedia_in_allowed(self):
        for ext in (".mp3", ".mp4", ".wav", ".m4a"):
            assert ext in ALLOWED_EXTENSIONS

    def test_documents_in_allowed(self):
        for ext in (".pdf", ".docx", ".txt"):
            assert ext in ALLOWED_EXTENSIONS

    def test_document_only_excludes_multimedia(self):
        for ext in MULTIMEDIA_EXTENSIONS:
            assert ext not in DOCUMENT_EXTENSIONS

    def test_allowed_is_superset(self):
        assert ALLOWED_EXTENSIONS >= DOCUMENT_EXTENSIONS
        assert ALLOWED_EXTENSIONS >= MULTIMEDIA_EXTENSIONS


class TestDetectFileTypeMultimedia:
    def test_mp3(self):
        assert detect_file_type("recording.mp3") == "audio"

    def test_wav(self):
        assert detect_file_type("recording.wav") == "audio"

    def test_m4a(self):
        assert detect_file_type("recording.m4a") == "audio"

    def test_mp4(self):
        assert detect_file_type("clip.mp4") == "video"

    def test_uppercase_mp3(self):
        assert detect_file_type("RECORDING.MP3") == "audio"


# ---------------------------------------------------------------------------
# parse_url — web page fetch + text extraction (httpx mocked)
# ---------------------------------------------------------------------------

SAMPLE_HTML = """\
<html>
<head><title>  黄芪的功效与作用  </title></head>
<body>
<header>导航栏 网站Logo</header>
<nav>首页 中药 方剂</nav>
<script>alert('x');</script>
<style>body { color: red; }</style>
<main>
<h1>黄芪</h1>
<p>黄芪，中药名。具有补气升阳，固表止汗，利水消肿，生津养血等功效。</p>
<p>常用剂量为 9-30g，水煎服。</p>
</main>
<footer>版权所有 © 2024</footer>
</body>
</html>"""


class _MockResponse:
    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


@pytest.mark.asyncio
async def test_parse_url_extracts_title_and_text():
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.get = AsyncMock(return_value=_MockResponse(SAMPLE_HTML))

    with patch("app.knowledge_parser.httpx.AsyncClient", return_value=mock_client):
        result = await parse_url("https://example.com/huangqi")

    assert result.type == "url"
    assert result.error is None
    assert result.metadata["source_url"] == "https://example.com/huangqi"
    assert "黄芪的功效与作用" in result.metadata["title"]
    full = result.full_text
    assert "补气升阳" in full
    assert "9-30g" in full
    assert "alert" not in full  # script stripped
    assert "color: red" not in full  # style stripped
    assert "导航栏" not in full  # nav stripped
    assert "版权所有" not in full  # footer stripped


@pytest.mark.asyncio
async def test_parse_url_truncates_long_text():
    long_html = "<html><head><title>长文</title></head><body><p>" + ("黄芪补气" * 5000) + "</p></body></html>"
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.get = AsyncMock(return_value=_MockResponse(long_html))

    with patch("app.knowledge_parser.httpx.AsyncClient", return_value=mock_client):
        result = await parse_url("https://example.com/long")

    assert result.error is None
    assert len(result.full_text) <= 10100  # 10000 + "..."


@pytest.mark.asyncio
async def test_parse_url_fetch_failure_returns_error():
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.get = AsyncMock(side_effect=Exception("Connection refused"))

    with patch("app.knowledge_parser.httpx.AsyncClient", return_value=mock_client):
        result = await parse_url("https://example.com/fail")

    assert result.type == "url"
    assert result.error is not None
    assert "网页抓取失败" in result.error


@pytest.mark.asyncio
async def test_parse_url_http_error_returns_error():
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.get = AsyncMock(return_value=_MockResponse("", status_code=404))

    with patch("app.knowledge_parser.httpx.AsyncClient", return_value=mock_client):
        result = await parse_url("https://example.com/missing")

    assert result.error is not None


@pytest.mark.asyncio
async def test_parse_url_empty_title_falls_back_to_url():
    html = "<html><body><p>内容</p></body></html>"
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.get = AsyncMock(return_value=_MockResponse(html))

    with patch("app.knowledge_parser.httpx.AsyncClient", return_value=mock_client):
        result = await parse_url("https://example.com/notitle")

    assert result.metadata["title"] == "https://example.com/notitle"


# ---------------------------------------------------------------------------
# parse_video_url — YouTube / Bilibili dispatch
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_parse_video_url_youtube_with_transcript():
    transcript = [
        {"text": "大家好"}, {"text": "今天介绍黄芪"}, {"text": "补气升阳"},
    ]

    with patch("app.knowledge_parser._fetch_youtube_transcript", return_value=transcript):
        result = await parse_video_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    assert result.type == "video"
    assert result.error is None
    assert result.metadata["platform"] == "youtube"
    assert result.metadata["video_id"] == "dQw4w9WgXcQ"
    full = result.full_text
    assert "大家好" in full
    assert "黄芪" in full
    assert "补气升阳" in full


@pytest.mark.asyncio
async def test_parse_video_url_youtube_dataclass_segments():
    """v1.x youtube-transcript-api returns dataclass objects with .text attr."""
    Snippet = type("Snippet", (), {"text": "黄芪补气升阳"})

    with patch("app.knowledge_parser._fetch_youtube_transcript", return_value=[Snippet()]):
        result = await parse_video_url("https://youtu.be/dQw4w9WgXcQ")

    assert result.type == "video"
    assert result.error is None
    assert "黄芪补气升阳" in result.full_text


@pytest.mark.asyncio
async def test_parse_video_url_youtube_transcript_fails_falls_back_to_page():
    """When YouTube transcript API fails, fall back to parse_url."""
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.get = AsyncMock(return_value=_MockResponse(SAMPLE_HTML))

    with patch("app.knowledge_parser._fetch_youtube_transcript", side_effect=Exception("No transcript")):
        with patch("app.knowledge_parser.httpx.AsyncClient", return_value=mock_client):
            result = await parse_video_url("https://youtu.be/dQw4w9WgXcQ")

    assert result.type == "url"
    assert result.error is None
    assert "补气升阳" in result.full_text


@pytest.mark.asyncio
async def test_parse_video_url_youtube_no_api_installed_falls_back(monkeypatch):
    """When youtube-transcript-api is not installed, fall back to parse_url."""
    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

    def blocking_import(name, *args, **kwargs):
        if name == "youtube_transcript_api":
            raise ImportError("not installed")
        return real_import(name, *args, **kwargs)

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.get = AsyncMock(return_value=_MockResponse(SAMPLE_HTML))

    monkeypatch.setattr("app.knowledge_parser.logger.info", lambda *a, **kw: None)
    with patch("builtins.__import__", side_effect=blocking_import):
        with patch("app.knowledge_parser.httpx.AsyncClient", return_value=mock_client):
            result = await parse_video_url("https://www.youtube.com/watch?v=abc12345678")

    assert result.type == "url"
    assert result.error is None


@pytest.mark.asyncio
async def test_parse_video_url_bilibili_falls_back_to_page():
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.get = AsyncMock(return_value=_MockResponse(SAMPLE_HTML))

    with patch("app.knowledge_parser.httpx.AsyncClient", return_value=mock_client):
        result = await parse_video_url("https://www.bilibili.com/video/BV1xx411c7mD")

    assert result.metadata.get("platform") == "bilibili"
    assert "补气升阳" in result.full_text


@pytest.mark.asyncio
async def test_parse_video_url_unknown_host_uses_parse_url():
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.get = AsyncMock(return_value=_MockResponse(SAMPLE_HTML))

    with (
        patch("app.knowledge_parser.httpx.AsyncClient", return_value=mock_client),
        patch("app.url_validator.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 0))]),
    ):
        result = await parse_video_url("https://random-blog.com/post/123")

    assert result.type == "url"
    assert "补气升阳" in result.full_text


@pytest.mark.asyncio
async def test_parse_video_url_youtube_no_id_match_falls_back():
    """YouTube URL without a valid 11-char ID falls back to page extraction."""
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.get = AsyncMock(return_value=_MockResponse(SAMPLE_HTML))

    with patch("app.knowledge_parser.httpx.AsyncClient", return_value=mock_client):
        result = await parse_video_url("https://www.youtube.com/feed/trending")

    assert result.type == "url"


# ---------------------------------------------------------------------------
# parse_audio — whisper transcription / graceful degradation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_parse_audio_whisper_not_installed_returns_error(monkeypatch):
    import app.knowledge_parser as kp

    monkeypatch.setattr(kp, "_load_whisper", lambda: None)

    result = await parse_audio("/tmp/fake.mp3")

    assert result.type == "audio"
    assert result.error is not None
    assert "Whisper" in result.error


@pytest.mark.asyncio
async def test_parse_audio_whisper_success(tmp_path, monkeypatch):
    fake_whisper = MagicMock()
    fake_model = MagicMock()
    fake_model.transcribe.return_value = {"text": "黄芪补气升阳，固表止汗。"}
    fake_whisper.load_model.return_value = fake_model

    monkeypatch.setattr("app.knowledge_parser._load_whisper", lambda: fake_whisper)

    audio_file = tmp_path / "recording.wav"
    audio_file.write_bytes(b"fake audio bytes")

    result = await parse_audio(str(audio_file))

    assert result.type == "audio"
    assert result.error is None
    assert "黄芪补气升阳" in result.full_text
    assert result.metadata["engine"] == "whisper"
    fake_whisper.load_model.assert_called_once_with("base")
    fake_model.transcribe.assert_called_once_with(str(audio_file), language="zh")


@pytest.mark.asyncio
async def test_parse_audio_whisper_raises_returns_error(tmp_path, monkeypatch):
    fake_whisper = MagicMock()
    fake_model = MagicMock()
    fake_model.transcribe.side_effect = RuntimeError("model load failed")
    fake_whisper.load_model.return_value = fake_model

    monkeypatch.setattr("app.knowledge_parser._load_whisper", lambda: fake_whisper)

    audio_file = tmp_path / "bad.wav"
    audio_file.write_bytes(b"\x00")

    result = await parse_audio(str(audio_file))

    assert result.type == "audio"
    assert result.error is not None
    assert "音频转录失败" in result.error


@pytest.mark.asyncio
async def test_parse_audio_empty_transcript(tmp_path, monkeypatch):
    fake_whisper = MagicMock()
    fake_model = MagicMock()
    fake_model.transcribe.return_value = {"text": ""}
    fake_whisper.load_model.return_value = fake_model

    monkeypatch.setattr("app.knowledge_parser._load_whisper", lambda: fake_whisper)

    audio_file = tmp_path / "silent.wav"
    audio_file.write_bytes(b"\x00" * 100)

    result = await parse_audio(str(audio_file))

    assert result.error is None
    assert result.full_text == ""


# ---------------------------------------------------------------------------
# parse_video_file — ffmpeg + whisper / graceful degradation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_parse_video_file_ffmpeg_not_installed_returns_error(tmp_path, monkeypatch):
    monkeypatch.setattr("app.knowledge_parser.shutil.which", lambda cmd: None)

    video_file = tmp_path / "clip.mp4"
    video_file.write_bytes(b"fake video")

    result = await parse_video_file(str(video_file))

    assert result.type == "video"
    assert result.error is not None
    assert "ffmpeg" in result.error


@pytest.mark.asyncio
async def test_parse_video_file_success(tmp_path, monkeypatch):
    video_file = tmp_path / "clip.mp4"
    video_file.write_bytes(b"fake video")

    fake_proc = MagicMock()
    fake_proc.returncode = 0
    fake_proc.stderr = ""

    def fake_ffmpeg(vp, ap):
        # Simulate ffmpeg creating the audio file
        with open(ap, "wb") as f:
            f.write(b"fake audio")
        return fake_proc

    fake_whisper = MagicMock()
    fake_model = MagicMock()
    fake_model.transcribe.return_value = {"text": "视频转录文本：黄芪补气。"}
    fake_whisper.load_model.return_value = fake_model

    monkeypatch.setattr("app.knowledge_parser.shutil.which", lambda cmd: "/usr/bin/ffmpeg")
    monkeypatch.setattr("app.knowledge_parser._ffmpeg_extract_audio", fake_ffmpeg)
    monkeypatch.setattr("app.knowledge_parser._load_whisper", lambda: fake_whisper)

    result = await parse_video_file(str(video_file))

    assert result.type == "video"
    assert result.error is None
    assert "黄芪补气" in result.full_text
    assert result.metadata["extracted_audio"] is True
    # Audio temp file should be cleaned up
    audio_path = str(video_file).rsplit(".", 1)[0] + "_audio.wav"
    assert not os.path.exists(audio_path)


@pytest.mark.asyncio
async def test_parse_video_file_ffmpeg_failure_returns_error(tmp_path, monkeypatch):
    video_file = tmp_path / "bad.mp4"
    video_file.write_bytes(b"corrupt")

    fake_proc = MagicMock()
    fake_proc.returncode = 1
    fake_proc.stderr = "Invalid data found"

    monkeypatch.setattr("app.knowledge_parser.shutil.which", lambda cmd: "/usr/bin/ffmpeg")
    monkeypatch.setattr("app.knowledge_parser._ffmpeg_extract_audio", lambda vp, ap: fake_proc)

    result = await parse_video_file(str(video_file))

    assert result.type == "video"
    assert result.error is not None
    assert "ffmpeg 提取音频失败" in result.error


@pytest.mark.asyncio
async def test_parse_video_file_ffmpeg_timeout(tmp_path, monkeypatch):
    video_file = tmp_path / "long.mp4"
    video_file.write_bytes(b"very long video")

    def fake_ffmpeg(vp, ap):
        raise subprocess.TimeoutExpired(cmd="ffmpeg", timeout=300)

    monkeypatch.setattr("app.knowledge_parser.shutil.which", lambda cmd: "/usr/bin/ffmpeg")
    monkeypatch.setattr("app.knowledge_parser._ffmpeg_extract_audio", fake_ffmpeg)

    result = await parse_video_file(str(video_file))

    assert result.type == "video"
    assert result.error is not None
    assert "超时" in result.error


@pytest.mark.asyncio
async def test_parse_video_file_whisper_missing_after_ffmpeg(tmp_path, monkeypatch):
    """ffmpeg works but whisper not installed → error with audio cleanup."""
    video_file = tmp_path / "clip.mp4"
    video_file.write_bytes(b"fake")

    fake_proc = MagicMock()
    fake_proc.returncode = 0
    fake_proc.stderr = ""

    created_paths: list[str] = []

    def fake_ffmpeg(vp, ap):
        with open(ap, "wb") as f:
            f.write(b"audio")
        created_paths.append(ap)
        return fake_proc

    monkeypatch.setattr("app.knowledge_parser.shutil.which", lambda cmd: "/usr/bin/ffmpeg")
    monkeypatch.setattr("app.knowledge_parser._ffmpeg_extract_audio", fake_ffmpeg)
    monkeypatch.setattr("app.knowledge_parser._load_whisper", lambda: None)

    result = await parse_video_file(str(video_file))

    assert result.type == "video"
    assert result.error is not None
    assert "Whisper" in result.error
    # Audio temp file must be cleaned up even on whisper-missing path
    for p in created_paths:
        assert not os.path.exists(p)


# ---------------------------------------------------------------------------
# parse_file dispatch — audio/video routing
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_parse_file_audio_routes_to_parse_audio(tmp_path, monkeypatch):
    audio_file = tmp_path / "rec.mp3"
    audio_file.write_bytes(b"fake")

    fake_whisper = MagicMock()
    fake_model = MagicMock()
    fake_model.transcribe.return_value = {"text": "转录文本"}
    fake_whisper.load_model.return_value = fake_model

    monkeypatch.setattr("app.knowledge_parser._load_whisper", lambda: fake_whisper)

    result = await parse_file(str(audio_file), "rec.mp3")

    assert result.type == "audio"
    assert result.error is None
    assert "转录文本" in result.full_text


@pytest.mark.asyncio
async def test_parse_file_audio_whisper_missing_returns_error(tmp_path, monkeypatch):
    audio_file = tmp_path / "rec.mp3"
    audio_file.write_bytes(b"fake")

    monkeypatch.setattr("app.knowledge_parser._load_whisper", lambda: None)

    result = await parse_file(str(audio_file), "rec.mp3")

    assert result.type == "audio"
    assert result.error is not None


@pytest.mark.asyncio
async def test_parse_file_video_routes_to_parse_video_file(tmp_path, monkeypatch):
    video_file = tmp_path / "clip.mp4"
    video_file.write_bytes(b"fake video")

    fake_proc = MagicMock()
    fake_proc.returncode = 0
    fake_proc.stderr = ""

    fake_whisper = MagicMock()
    fake_model = MagicMock()
    fake_model.transcribe.return_value = {"text": "视频内容"}
    fake_whisper.load_model.return_value = fake_model

    monkeypatch.setattr("app.knowledge_parser.shutil.which", lambda cmd: "/usr/bin/ffmpeg")
    monkeypatch.setattr(
        "app.knowledge_parser._ffmpeg_extract_audio",
        lambda vp, ap: (open(ap, "wb").write(b"x"), fake_proc)[1],
    )
    monkeypatch.setattr("app.knowledge_parser._load_whisper", lambda: fake_whisper)

    result = await parse_file(str(video_file), "clip.mp4")

    assert result.type == "video"
    assert result.error is None


@pytest.mark.asyncio
async def test_parse_file_txt_still_works(tmp_path):
    """Regression: existing TXT parsing must not be affected by new code."""
    path = tmp_path / "guide.txt"
    path.write_text("黄芪补气升阳。", encoding="utf-8")
    result = await parse_file(str(path), "guide.txt")
    assert result.type == "txt"
    assert result.error is None
    assert "黄芪补气升阳" in result.full_text


# ---------------------------------------------------------------------------
# HTTP endpoint tests — /api/knowledge-hub/import-url
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_import_url_endpoint_success(client, auth_headers):
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.get = AsyncMock(return_value=_MockResponse(SAMPLE_HTML))

    with patch("app.knowledge_parser.httpx.AsyncClient", return_value=mock_client):
        resp = await client.post(
            "/api/knowledge-hub/import-url",
            json={"url": "https://example.com/huangqi"},
            headers=auth_headers,
        )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["entity"]["title"] == "黄芪的功效与作用"
    assert body["source_url"] == "https://example.com/huangqi"
    assert body["parse_metadata"]["source_url"] == "https://example.com/huangqi"


@pytest.mark.asyncio
async def test_import_url_endpoint_custom_title(client, auth_headers):
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.get = AsyncMock(return_value=_MockResponse(SAMPLE_HTML))

    with patch("app.knowledge_parser.httpx.AsyncClient", return_value=mock_client):
        resp = await client.post(
            "/api/knowledge-hub/import-url",
            json={"url": "https://example.com/huangqi", "title": "自定义标题"},
            headers=auth_headers,
        )

    assert resp.status_code == 201
    assert resp.json()["entity"]["title"] == "自定义标题"


@pytest.mark.asyncio
async def test_import_url_endpoint_fetch_failure(client, auth_headers):
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.get = AsyncMock(side_effect=Exception("Network error"))

    with patch("app.knowledge_parser.httpx.AsyncClient", return_value=mock_client):
        resp = await client.post(
            "/api/knowledge-hub/import-url",
            json={"url": "https://example.com/fail"},
            headers=auth_headers,
        )

    assert resp.status_code == 422
    assert "网页抓取失败" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_import_url_endpoint_requires_auth(raw_client):
    resp = await raw_client.post(
        "/api/knowledge-hub/import-url",
        json={"url": "https://example.com/test"},
    )
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_import_url_endpoint_empty_url_validation(client, auth_headers):
    """Empty URL fails Pydantic min_length validation → 422."""
    resp = await client.post(
        "/api/knowledge-hub/import-url",
        json={"url": ""},
        headers=auth_headers,
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# HTTP endpoint tests — /api/knowledge-hub/import-video-url
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_import_video_url_endpoint_youtube(client, auth_headers):
    transcript = [{"text": "黄芪"}, {"text": "补气升阳"}]

    with patch("app.knowledge_parser._fetch_youtube_transcript", return_value=transcript):
        resp = await client.post(
            "/api/knowledge-hub/import-video-url",
            json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
            headers=auth_headers,
        )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert "黄芪" in body["entity"]["summary"] or "黄芪" in body["entity"].get("content_preview", "")
    assert body["parse_metadata"]["platform"] == "youtube"
    assert body["source_url"] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


@pytest.mark.asyncio
async def test_import_video_url_endpoint_bilibili_fallback(client, auth_headers):
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.get = AsyncMock(return_value=_MockResponse(SAMPLE_HTML))

    with patch("app.knowledge_parser.httpx.AsyncClient", return_value=mock_client):
        resp = await client.post(
            "/api/knowledge-hub/import-video-url",
            json={"url": "https://www.bilibili.com/video/BV1xx411c7mD"},
            headers=auth_headers,
        )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["parse_metadata"]["platform"] == "bilibili"


@pytest.mark.asyncio
async def test_import_video_url_endpoint_requires_auth(raw_client):
    resp = await raw_client.post(
        "/api/knowledge-hub/import-video-url",
        json={"url": "https://www.youtube.com/watch?v=abc12345678"},
    )
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# HTTP endpoint tests — /api/knowledge-hub/import-file with multimedia
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_import_file_mp3_accepted(client, auth_headers, monkeypatch):
    """uploading a .mp3 is accepted (whisper mocked)."""
    fake_whisper = MagicMock()
    fake_model = MagicMock()
    fake_model.transcribe.return_value = {"text": "音频转录内容：黄芪补气。"}
    fake_whisper.load_model.return_value = fake_model
    monkeypatch.setattr("app.knowledge_parser._load_whisper", lambda: fake_whisper)

    resp = await client.post(
        "/api/knowledge-hub/import-file",
        files={"file": ("rec.mp3", io.BytesIO(b"fake audio"), "audio/mpeg")},
        headers=auth_headers,
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["filename"] == "rec.mp3"


@pytest.mark.asyncio
async def test_import_file_mp3_whisper_missing_returns_422(client, auth_headers, monkeypatch):
    """When whisper is not installed, mp3 upload returns 422 with friendly error."""
    monkeypatch.setattr("app.knowledge_parser._load_whisper", lambda: None)

    resp = await client.post(
        "/api/knowledge-hub/import-file",
        files={"file": ("rec.mp3", io.BytesIO(b"fake audio"), "audio/mpeg")},
        headers=auth_headers,
    )

    assert resp.status_code == 422
    assert "Whisper" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_import_file_mp4_accepted(client, auth_headers, monkeypatch):
    """uploading a .mp4 is accepted (ffmpeg+whisper mocked)."""
    fake_proc = MagicMock()
    fake_proc.returncode = 0
    fake_proc.stderr = ""

    fake_whisper = MagicMock()
    fake_model = MagicMock()
    fake_model.transcribe.return_value = {"text": "视频转录文本。"}
    fake_whisper.load_model.return_value = fake_model

    monkeypatch.setattr("app.knowledge_parser.shutil.which", lambda cmd: "/usr/bin/ffmpeg")
    monkeypatch.setattr(
        "app.knowledge_parser._ffmpeg_extract_audio",
        lambda vp, ap: (open(ap, "wb").write(b"x"), fake_proc)[1],
    )
    monkeypatch.setattr("app.knowledge_parser._load_whisper", lambda: fake_whisper)

    resp = await client.post(
        "/api/knowledge-hub/import-file",
        files={"file": ("clip.mp4", io.BytesIO(b"fake video"), "video/mp4")},
        headers=auth_headers,
    )

    assert resp.status_code == 201, resp.text


@pytest.mark.asyncio
async def test_import_file_mp4_ffmpeg_missing_returns_422(client, auth_headers, monkeypatch):
    monkeypatch.setattr("app.knowledge_parser.shutil.which", lambda cmd: None)

    resp = await client.post(
        "/api/knowledge-hub/import-file",
        files={"file": ("clip.mp4", io.BytesIO(b"fake"), "video/mp4")},
        headers=auth_headers,
    )

    assert resp.status_code == 422
    assert "ffmpeg" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_import_file_txt_still_works(client, auth_headers):
    """Regression: TXT upload via hub endpoint must still work."""
    resp = await client.post(
        "/api/knowledge-hub/import-file",
        files={"file": ("guide.txt", io.BytesIO("黄芪补气升阳。".encode("utf-8")), "text/plain")},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text


@pytest.mark.asyncio
async def test_import_file_unsupported_extension_rejected(client, auth_headers):
    """Truly unsupported extensions (.exe) are still rejected."""
    resp = await client.post(
        "/api/knowledge-hub/import-file",
        files={"file": ("malware.exe", io.BytesIO(b"MZ"), "application/octet-stream")},
        headers=auth_headers,
    )
    assert resp.status_code == 422
    assert "不支持的文件格式" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Security boundary — legacy /api/knowledge-import/upload still rejects multimedia
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_legacy_upload_rejects_mp4(client, auth_headers):
    """The legacy document-only router must continue to reject .mp4 (security boundary)."""
    resp = await client.post(
        "/api/knowledge-import/upload",
        files={"file": ("video.mp4", io.BytesIO(b"fake"), "video/mp4")},
        headers=auth_headers,
    )
    assert resp.status_code == 422
    assert "不支持的文件格式" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_legacy_upload_rejects_mp3(client, auth_headers):
    resp = await client.post(
        "/api/knowledge-import/upload",
        files={"file": ("audio.mp3", io.BytesIO(b"fake"), "audio/mpeg")},
        headers=auth_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_legacy_upload_accepts_txt(client, auth_headers):
    """Regression: legacy router still accepts documents."""
    resp = await client.post(
        "/api/knowledge-import/upload",
        files={"file": ("ok.txt", io.BytesIO("黄芪补气".encode("utf-8")), "text/plain")},
        headers=auth_headers,
    )
    assert resp.status_code == 201
