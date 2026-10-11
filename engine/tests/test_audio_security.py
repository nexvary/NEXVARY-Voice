import json
import pytest
from fastapi.testclient import TestClient

from voice_engine.api import app
from voice_engine.live import get_live_processor


def test_reject_unsupported_audio_handshake(monkeypatch):
    monkeypatch.delenv("NEXVARY_API_TOKEN", raising=False)
    with TestClient(app) as client:
        with client.websocket_connect("/v1/live/audio") as ws:
            ws.send_json({"source_language": "ar", "target_language": "en",
                          "format": "mp3", "sample_rate": 16000})
            assert ws.receive_json()["type"] == "error"


def test_reject_malformed_pcm_packet(monkeypatch):
    import voice_engine.api as api
    monkeypatch.setattr(api, "get_live_processor", lambda: object())
    monkeypatch.delenv("NEXVARY_API_TOKEN", raising=False)
    with TestClient(app) as client:
        with client.websocket_connect("/v1/live/audio") as ws:
            ws.send_json({"source_language": "ar", "target_language": "en",
                          "format": "pcm_s16le", "sample_rate": 16000})
            ws.send_bytes(b"\x00")  # odd number of bytes
            assert ws.receive_json()["type"] == "error"
