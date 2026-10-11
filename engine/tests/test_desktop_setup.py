"""Read-only hardware audit, safe paths, package validation without any downloads."""
import hashlib
import json
from pathlib import Path

import pytest

from voice_engine import desktop_setup as setup
from voice_engine import setup_assets


def test_resources_are_embedded_or_repository():
    assert (setup.source_dir() / "pyproject.toml").is_file()


def test_app_data_is_isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    root = setup.home()
    assert root == tmp_path / "NEXVARY" / "Voice"
    assert str(setup.python_path()).endswith(str(Path("runtime") / "Scripts" / "python.exe"))
    env = setup.setup_environment()
    assert env["UV_CACHE_DIR"].startswith(str(root))
    assert env["ARGOS_PACKAGES_DIR"].startswith(str(root))
    assert env["HF_HOME"].startswith(str(root))


def test_uv_pipeline_never_installs_to_global_python(monkeypatch, tmp_path):
    monkeypatch.setattr(setup, "resources", lambda: tmp_path)
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "uv.exe").write_bytes(b"mock")
    (tmp_path / "engine").mkdir()
    (tmp_path / "engine" / "pyproject.toml").write_text("[project]")
    monkeypatch.setattr(setup, "existing_system_python", lambda: None)
    base = tmp_path / "local"
    actions = setup.pipeline(base)
    assert len(actions) == 3
    assert all(str(tmp_path / "bin" / "uv.exe") == cmd[0] for cmd in actions)
    assert str(setup.python_path(base)) in actions[-1]
    assert str(base / "runtime") in actions[1]


def test_setup_stages_restricted(monkeypatch, tmp_path):
    python = setup.python_path(tmp_path)
    python.parent.mkdir(parents=True)
    python.write_text("fixture")
    for stage in ("translations", "whisper", "voices"):
        args = setup.model_command(stage, tmp_path)
        assert args[-1] == stage
    with pytest.raises(ValueError):
        setup.model_command("rm -rf", tmp_path)


def test_device_audit_requires_no_installer(monkeypatch, tmp_path):
    monkeypatch.setattr(setup, "model_report", lambda base=None: None)
    monkeypatch.setattr(setup, "memory_gb", lambda: 16)
    monkeypatch.setattr(setup, "ffmpeg_pair", lambda base=None: (None, None))
    monkeypatch.setattr(setup, "uv_path", lambda: tmp_path / "missing.exe")
    state = setup.detect(tmp_path)
    assert state["ram_gb"] == 16
    assert state["runtime"] is False
    assert state["voices_ready"] is False
    assert state["translation_ready"] is False
    assert state["ffmpeg"] is False


def test_voice_registry_file_list_validation():
    registry = {"ar_JO-kareem-medium": {"files": {
        "ar/voice.onnx": {"size_bytes": 3, "md5_digest": "0"*32},
        "ar/voice.onnx.json": {"size_bytes": 3, "md5_digest": "0"*32},
        "ar/MODEL_CARD": {"size_bytes": 3, "md5_digest": "0"*32},
    }}}
    assert len(setup_assets.model_entries(registry, "ar_JO-kareem-medium")) == 3
    with pytest.raises(RuntimeError):
        setup_assets.model_entries({}, "ar_JO-kareem-medium")


def test_integrity_check(tmp_path):
    file = tmp_path / "voice.onnx"
    file.write_bytes(b"abc")
    record = {"size_bytes": 3, "md5_digest": hashlib.md5(b"abc").hexdigest()}
    assert setup_assets.verified_file(file, record)
    file.write_bytes(b"abd")
    assert not setup_assets.verified_file(file, record)


def test_all_six_voices_configured():
    assert set(setup_assets.VOICES) == {"ar", "en", "it", "ru", "es", "bn"}

def test_existing_python_is_reused_without_global_install(monkeypatch, tmp_path):
    monkeypatch.setattr(setup, "resources", lambda: tmp_path)
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "uv.exe").write_bytes(b"mock")
    (tmp_path / "engine").mkdir()
    (tmp_path / "engine" / "pyproject.toml").write_text("[project]")
    existing = tmp_path / "Python311" / "python.exe"
    existing.parent.mkdir()
    existing.write_bytes(b"fixture")
    monkeypatch.setattr(setup, "existing_system_python", lambda: existing)
    actions = setup.pipeline(tmp_path / "user")
    assert len(actions) == 2
    assert str(existing) in actions[0]
    assert "pip" in actions[1]
    assert "--python" in actions[1]
