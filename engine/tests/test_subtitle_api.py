from fastapi.testclient import TestClient
from voice_engine.api import app

SRT = "1\n00:00:00,000 --> 00:00:01,200\nمرحبا\n"

def test_subtitle_endpoint(fake_engine):
    with TestClient(app) as client:
        r = client.post("/v1/subtitles/translate", json={
            "srt": SRT, "source_language": "ar", "target_language": "en"
        })
    assert r.status_code == 200
    assert "[ar>en] مرحبا" in r.json()["srt"]
    assert "00:00:01,200" in r.json()["srt"]

def test_invalid_subtitle_rejected(fake_engine):
    with TestClient(app) as client:
        r = client.post("/v1/subtitles/translate", json={
            "srt": "this is not SRT", "source_language": "ar", "target_language": "hi"
        })
    assert r.status_code == 422
