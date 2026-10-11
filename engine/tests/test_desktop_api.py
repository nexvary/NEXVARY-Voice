from pathlib import Path

import httpx
import pytest

from voice_engine.desktop_api import DesktopAPI, ClientError, normalize_url, websocket_url


def test_secure_endpoints():
    assert normalize_url("https://voice.example.org/") == "https://voice.example.org"
    assert websocket_url("http://127.0.0.1:8000") == "ws://127.0.0.1:8000/v1/live/audio"
    assert websocket_url("https://voice.example.org") == "wss://voice.example.org/v1/live/audio"
    for addr in ("http://voice.example.org", "ftp://localhost", "https://u:p@example.org",
                 "https://voice.example.org/private", "https://voice.example.org?key=abc"):
        with pytest.raises(ClientError):
            normalize_url(addr)


def test_translation_with_bearer_and_no_token_in_url():
    calls = []
    def handler(request):
        calls.append(request)
        assert request.headers["authorization"] == "Bearer secret-for-tests"
        return httpx.Response(200, json={"translated_text": "Welcome"})
    client = DesktopAPI("https://voice.example.org", "secret-for-tests",
                        transport=httpx.MockTransport(handler))
    assert client.translate("أهلًا", "ar", "en") == "Welcome"
    assert len(calls) == 1
    assert "secret-for-tests" not in str(calls[0].url)


def test_unavailable_models_are_clear():
    api = DesktopAPI("https://voice.example.org",
        transport=httpx.MockTransport(lambda request: httpx.Response(503)))
    with pytest.raises(ClientError, match="503"):
        api.translate("hello", "en", "hi")


def test_job_upload_is_bounded(tmp_path):
    file = tmp_path / "large.mp4"
    with file.open("wb") as handle:
        handle.truncate(80 * 1024 * 1024 + 1)
    with pytest.raises(ClientError):
        DesktopAPI("https://voice.example.org").submit_video(file, "ar", "en")


def test_job_status_and_subtitles():
    def handler(request):
        if request.url.path.endswith("/subtitles/translate"):
            return httpx.Response(200, json={"srt":"1\\n00:00:00,000 --> 00:00:01,000\\nWelcome"})
        return httpx.Response(200, json={"job_id":"job-1","status":"complete"})
    api = DesktopAPI("https://voice.example.org", transport=httpx.MockTransport(handler))
    assert api.video_status("job-1")["status"] == "complete"
    assert "Welcome" in api.translate_srt("1\\n00:00:00,000 --> 00:00:01,000\\nHi", "en", "ar")
