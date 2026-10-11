"""Simulated host probes and process ownership checks."""
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from voice_engine import desktop_setup as setup
from voice_engine.diagnostics import inspect_binary
from voice_engine import workload


def test_old_private_python_is_not_ready(monkeypatch,tmp_path):
    py=setup.python_path(tmp_path);py.parent.mkdir(parents=True);py.touch()
    monkeypatch.setattr(setup.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=0,stdout=json.dumps({'version':[3,8,10], 'modules':{'piper-tts':{'state':'ready'}}})))
    assert setup.runtime_report(tmp_path)['state']=='repair'


def test_existing_private_runtime_is_never_recreated(monkeypatch,tmp_path):
    uv=tmp_path/'bin'/'uv.exe';uv.parent.mkdir();uv.touch()
    source=tmp_path/'engine';source.mkdir();(source/'pyproject.toml').touch()
    monkeypatch.setattr(setup,'resources',lambda:tmp_path)
    monkeypatch.setattr(setup,'existing_system_python',lambda:None)
    base=tmp_path/'مجلد عربي';py=setup.python_path(base);py.parent.mkdir(parents=True);py.touch()
    commands=setup.pipeline(base)
    assert len(commands)==1
    assert commands[0][1:3]==['pip','install']
    assert not any('venv' in argv for argv in commands)


def test_external_ffmpeg_pair_is_reused(monkeypatch,tmp_path):
    root=tmp_path/'تثبيت خاص';root.mkdir()
    (root/'ffmpeg.exe').touch();(root/'ffprobe.exe').touch()
    monkeypatch.setattr(setup,'binaries',lambda base=None:root)
    assert setup.ffmpeg_pair(tmp_path)==(str(root/'ffmpeg.exe'),str(root/'ffprobe.exe'))


def test_external_engine_is_never_terminated(monkeypatch):
    manager=setup.EngineManager()
    monkeypatch.setattr(manager,'health',lambda:True)
    monkeypatch.setattr(setup,'start_local_engine',lambda:pytest.fail('duplicate engine'))
    assert 'موجود' in manager.start()
    assert manager.process is None
    manager.stop()
    assert manager.process is None


def test_only_one_heavy_workload_runs():
    with workload.exclusive('video'):
        with pytest.raises(RuntimeError):
            with workload.exclusive('live-audio'): pass
    assert workload.state=='idle'
    with workload.exclusive('live-audio'): assert workload.state=='live-audio'


def test_empty_binary_version_is_a_repair_state(monkeypatch):
    from voice_engine import diagnostics
    monkeypatch.setattr(diagnostics.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=0,stdout=''))
    assert inspect_binary('ffmpeg')['state']=='repair'
