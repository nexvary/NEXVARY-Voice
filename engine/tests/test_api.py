from fastapi.testclient import TestClient

from voice_engine.api import app


def test_health():
    with TestClient(app) as client:
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["audio_streaming"] is True
        assert r.json()["protocol"] == "segmented_pcm16_speech_turns"


def test_two_way_translation(fake_engine):
    with TestClient(app) as client:
        incoming = client.post("/v1/translate", json={"text": "नमस्ते", "source_language": "hi-IN", "target_language": "ar-EG"})
        outgoing = client.post("/v1/translate", json={"text": "أهلا", "source_language": "ar", "target_language": "hi"})
    assert incoming.status_code == outgoing.status_code == 200
    assert incoming.json()["translated_text"] == "[hi>ar] नमस्ते"
    assert outgoing.json()["translated_text"] == "[ar>hi] أهلا"


def test_validation_rejects_blanks_and_unknown_codes(fake_engine):
    with TestClient(app) as client:
        assert client.post("/v1/translate", json={"text": "  ", "source_language": "ar", "target_language": "hi"}).status_code == 422
        assert client.post("/v1/translate", json={"text": "hi", "source_language": "xx", "target_language": "hi"}).status_code == 422


def test_authenticated_requests(monkeypatch, fake_engine):
    monkeypatch.setenv("NEXVARY_API_TOKEN", "test-secret")
    body = {"text": "مرحبا", "source_language": "ar", "target_language": "en"}
    with TestClient(app) as client:
        assert client.post("/v1/translate", json=body).status_code == 401
        r = client.post("/v1/translate", json=body, headers={"Authorization": "Bearer test-secret"})
    assert r.status_code == 200


def test_text_websocket(fake_engine):
    with TestClient(app) as client:
        with client.websocket_connect("/v1/live/text") as ws:
            ws.send_json({"text": "Hello", "source_language": "en", "target_language": "hi"})
            assert ws.receive_json()["translated_text"] == "[en>hi] Hello"
            ws.send_text("not json")
            assert ws.receive_json()["error"] == "invalid_turn"
