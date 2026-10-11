"""Offscreen Qt tests with simulated diagnostics, not microphone hardware tests."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import time
import pytest
pytest.importorskip('PySide6')
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from voice_engine.setup_wizard import SetupDialog,SetupTask
from voice_engine.desktop_app import VoiceWindow

@pytest.fixture(scope='module')
def app(): return QApplication.instance() or QApplication([])


def test_ui_responsive_while_audit_worker_runs(app,monkeypatch):
    from voice_engine import desktop_setup
    monkeypatch.setattr(desktop_setup,'detect',lambda:(time.sleep(.18),{})[1])
    worker=SetupTask('audit'); ticks=[]
    timer=QTimer();timer.setInterval(10);timer.timeout.connect(lambda:ticks.append(1));timer.start()
    worker.start()
    while worker.isRunning(): app.processEvents();time.sleep(.002)
    app.processEvents();timer.stop()
    assert len(ticks)>5
    worker.wait()


def test_failed_install_does_not_display_fake_completion(app):
    dialog=SetupDialog(audit=False)
    dialog._result={'previous_audit':True}
    dialog.progress.setRange(0,0)
    worker=SetupTask('all')
    dialog._outcome(False);dialog._finished(worker)
    assert dialog.progress.value()!=100
    assert 'لم تكتمل' in dialog.log.toPlainText()
    dialog.close()


def test_nine_pages_back_and_secret_redaction(app):
    window=VoiceWindow()
    assert window.stack.count()==9
    window._set_page(3);window._set_page(6);window._back()
    assert window.stack.currentIndex()==3
    window.secret.setText('secret-example')
    window._set_status('Bearer secret-example',False)
    assert 'secret-example' not in window.operation_log.toPlainText()
    window.close()
