import pytest
from fastapi.testclient import TestClient
from voice_engine.api import app
from voice_engine.desktop_api import DesktopAPI, LANGUAGES

CODES = ("ar", "en", "it", "ru", "es", "bn")

@pytest.mark.parametrize("source", CODES)
@pytest.mark.parametrize("target", CODES)
def test_all_requested_language_directions(fake_engine, source, target):
    assert source in LANGUAGES
    assert target in LANGUAGES
    if source == target:
        return
    with TestClient(app) as client:
        response = client.post("/v1/translate", json={
            "text": "test", "source_language": source, "target_language": target
        })
    assert response.status_code == 200
    assert response.json()["translated_text"] == f"[{source}>{target}] test"
