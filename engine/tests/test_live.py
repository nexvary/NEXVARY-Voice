import json
import math
import struct
import pytest
from fastapi.testclient import TestClient

from voice_engine.api import app
from voice_engine.live import CHUNK_BYTES, pcm_rms, get_live_processor


class FakeLive:
    def process(self, pcm, source, target):
        assert len(pcm) == CHUNK_BYTES
        return ({"type": "translated", "original_text": "hello",
                 "translated_text": "مرحبا", "source_language": source,
                 "target_language": target, "pcm_bytes": 4},
                b"\x00\x01\x02\x03")


def test_rms_silence_and_tone():
    assert pcm_rms(b"\x00\x00" * 100) == 0
    assert math.isclose(pcm_rms(struct.pack("<hh", 1000, -1000)), 1000)
    with pytest.raises(ValueError):
        pcm_rms(b"\xff")


def test_live_auth(monkeypatch):
    monkeypatch.setenv("NEXVARY_API_TOKEN", "test")
    with TestClient(app) as client:
        with pytest.raises(Exception):
            with client.websocket_connect("/v1/live/audio"):
                pass


def test_audio_session_chunk_transport(monkeypatch):
    app.dependency_overrides.clear()
    # Audio module's cache provider is invoked from the imported API namespace.
    import voice_engine.api as api
    monkeypatch.setattr(api, "get_live_processor", lambda: FakeLive())
    monkeypatch.delenv("NEXVARY_API_TOKEN", raising=False)
    with TestClient(app) as client:
        with client.websocket_connect("/v1/live/audio") as ws:
            ws.send_json({"source_language": "en", "target_language": "ar",
                          "format": "pcm_s16le", "sample_rate": 16000})
            for _ in range(CHUNK_BYTES // 3200):
                ws.send_bytes(struct.pack("<h", 1000) * 1600)
            meta = ws.receive_json()
            assert meta["type"] == "translated"
            assert meta["translated_text"] == "مرحبا"
            assert ws.receive_bytes() == b"\x00\x01\x02\x03"
            ws.send_json({"type": "stop"})
