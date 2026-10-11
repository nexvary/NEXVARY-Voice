import json
from voice_engine import model_status

def test_missing_models_are_reported(monkeypatch, tmp_path):
    monkeypatch.setattr(model_status, "installed_pairs", lambda: set())
    state = model_status.report(tmp_path / "voices.json")
    assert set(state["languages"]) == {"ar", "en", "it", "ru", "es", "bn"}
    assert state["languages"]["en"]["to_english"]
    assert not state["languages"]["bn"]["to_english"]
    assert not state["translation_ready"]
    assert not state["piper_ready"]

def test_all_ten_pairs_and_voice_configuration(monkeypatch, tmp_path):
    pairs = {(code, "en") for code in model_status.CODES if code != "en"} | {
        ("en", code) for code in model_status.CODES if code != "en"}
    monkeypatch.setattr(model_status, "installed_pairs", lambda: pairs)
    voices = {}
    for code in model_status.CODES:
        model = tmp_path / (code + ".onnx")
        model.write_bytes(b"fixture")
        (tmp_path / (code + ".onnx.json")).write_text("{}")
        voices[code] = str(model)
    settings = tmp_path / "voices.json"
    settings.write_text(json.dumps(voices), encoding="utf-8")
    state = model_status.report(settings)
    assert state["translation_ready"]
    assert state["piper_ready"]
