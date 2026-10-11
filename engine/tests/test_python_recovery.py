"""Simulated Windows 448; actual Windows/model proof is a separate CI stage."""
from types import SimpleNamespace
from pathlib import Path
import pytest
from voice_engine import desktop_setup as setup

ERROR = 'Failed to create Python minor version link directory\nThe path contains an untrusted mount point. (os error 448)'


def test_uv_state_is_private_even_with_roaming_environment(monkeypatch, tmp_path):
    monkeypatch.setenv('UV_DATA_DIR', 'cloud/untrusted')
    monkeypatch.setenv('UV_PYTHON_INSTALL_DIR', 'cloud/untrusted/python')
    env = setup.setup_environment(tmp_path / 'اختبار')
    assert Path(env['UV_DATA_DIR']) == tmp_path / 'اختبار' / 'uv-data'
    assert Path(env['UV_PYTHON_INSTALL_DIR']) == tmp_path / 'اختبار' / 'pythons'
    assert env['UV_LINK_MODE'] == 'copy'
    assert env['UV_PYTHON_INSTALL_BIN'] == env['UV_PYTHON_INSTALL_REGISTRY'] == '0'


@pytest.fixture
def host(monkeypatch, tmp_path):
    uv = tmp_path / 'uv.exe'; uv.touch()
    monkeypatch.setattr(setup, 'uv_path', lambda: uv)
    monkeypatch.setattr(setup, 'existing_system_python', lambda: None)
    return tmp_path


def test_recover_448_only_after_extracted_python_passes_probe(host, monkeypatch):
    interpreter = host / 'pythons' / 'cpython-3.11.15-windows-x86_64-none' / 'python.exe'
    checks = iter([None, interpreter])
    monkeypatch.setattr(setup, 'managed_python', lambda base: next(checks))
    commands, logs = [], []
    def execute(command, label):
        commands.append(command)
        raise setup.SetupCommandError(label, 2, ERROR)
    assert setup.prepare_python(execute, logs.append, base=host) == interpreter
    assert len(commands) == 1 and 'install' in commands[0]
    assert any('448' in message for message in logs)


@pytest.mark.parametrize('error', [ERROR, 'Connection reset by peer', 'archive extraction failed'])
def test_failed_or_incomplete_extraction_is_not_success(host, monkeypatch, error):
    monkeypatch.setattr(setup, 'managed_python', lambda base: None)
    def execute(command, label): raise setup.SetupCommandError(label, 2, error)
    with pytest.raises(RuntimeError): setup.prepare_python(execute, lambda message: None, base=host)


def test_other_failure_is_not_hidden_by_an_existing_interpreter(host, monkeypatch):
    checks = iter([None, host / 'python.exe'])
    monkeypatch.setattr(setup, 'managed_python', lambda base: next(checks))
    def execute(command, label): raise setup.SetupCommandError(label, 2, 'TLS verification failed')
    with pytest.raises(setup.SetupCommandError): setup.prepare_python(execute, lambda message: None, base=host)


def test_cancel_during_link_failure_never_recovers(host, monkeypatch):
    cancelled = [False]
    monkeypatch.setattr(setup, 'managed_python', lambda base: None)
    def execute(command, label):
        cancelled[0] = True
        raise setup.SetupCommandError(label, 2, ERROR)
    with pytest.raises(RuntimeError, match='إيقاف'):
        setup.prepare_python(execute, lambda message: None, base=host, cancelled=lambda: cancelled[0])


def test_restart_reuses_extraction_without_install(host, monkeypatch):
    interpreter = host / 'python.exe'
    monkeypatch.setattr(setup, 'managed_python', lambda base: interpreter)
    def forbidden(*args): pytest.fail('healthy extracted Python must not be downloaded again')
    assert setup.prepare_python(forbidden, lambda message: None, base=host) == interpreter


def test_probe_skips_minor_version_links_and_broken_executables(host, monkeypatch):
    root = host / 'pythons'; root.mkdir()
    # Minor alias must never even be executed, including a dangling alias.
    (root / 'cpython-3.11-windows-x86_64-none').mkdir()
    (root / 'cpython-3.11-windows-x86_64-none' / 'python.exe').touch()
    for version in ('14', '15'):
        directory = root / f'cpython-3.11.{version}-windows-x86_64-none'
        directory.mkdir(); (directory / 'python.exe').touch()
    called = []
    def probe(argv, **kwargs):
        called.append(argv)
        return SimpleNamespace(returncode=0, stdout='False' if '3.11.15' in argv[0] else 'True')
    monkeypatch.setattr(setup.subprocess, 'run', probe)
    assert '3.11.14' in str(setup.managed_python(host))
    assert len(called) == 2 and all('3.11.' in argv[0] and '-I' in argv for argv in called)


def test_probe_rejects_symlink_outside_store(host, monkeypatch):
    root = host / 'pythons'; root.mkdir()
    external = host / 'external'; external.mkdir(); (external / 'python.exe').touch()
    alias = root / 'cpython-3.11.15-windows-x86_64-none'
    try: alias.symlink_to(external, target_is_directory=True)
    except OSError: pytest.skip('host denies creation of symbolic links')
    monkeypatch.setattr(setup.subprocess, 'run', lambda *a, **k: pytest.fail('must not execute external alias'))
    assert setup.managed_python(host) is None
