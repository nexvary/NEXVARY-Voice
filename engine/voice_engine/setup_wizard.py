"""NEXVARY first-launch graphical diagnostics and one-click setup.

First scan never modifies computer. Downloads only from an explicit button
with a clear confirmation. Managed runtime remains isolated under LocalAppData.
"""
from __future__ import annotations

import os
import subprocess
import threading
from pathlib import Path

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QTextEdit,
    QPushButton, QMessageBox, QProgressBar, QFrame, QSizePolicy
)

from . import desktop_setup as setup

BG = "#08111f"
PANEL = "#13243b"
MUTED = "#adbed0"
GOLD = "#e7c17f"
CYAN = "#49dacc"


class SetupTask(QThread):
    message = Signal(str)
    report = Signal(object)
    problem = Signal(str)
    done = Signal(bool)

    def __init__(self, mode: str, parent=None):
        super().__init__(parent)
        self.mode = mode
        self._stop = threading.Event()
        self._process: subprocess.Popen | None = None

    def cancel(self):
        self._stop.set()
        if self._process and self._process.poll() is None:
            self._process.terminate()

    def execute(self, argv: list[str], label: str):
        if self._stop.is_set():
            raise RuntimeError("تم إيقاف العملية بناءً على طلب المستخدم.")
        self.message.emit("● " + label)
        env = setup.setup_environment()
        home = setup.home()
        home.mkdir(parents=True, exist_ok=True)
        self._process = subprocess.Popen(
            argv, env=env, cwd=str(home), stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
            creationflags=setup.NO_WINDOW,
        )
        try:
            assert self._process.stdout is not None
            for line in self._process.stdout:
                if self._stop.is_set():
                    self._process.terminate()
                    break
                stripped = line.strip()
                if stripped:
                    self.message.emit(stripped[-350:])
            code = self._process.wait()
            if self._stop.is_set():
                raise RuntimeError("تم إيقاف الإعداد.")
            if code:
                raise RuntimeError("تعذرت خطوة " + label + f" (code {code}). راجع سجل العملية.")
        finally:
            self._process = None

    def install_runtime(self):
        state = setup.detect()
        if state["runtime"] and self.check_runtime():
            self.message.emit("✓ تم العثور على محرك Python جاهز.")
            return
        for index, command in enumerate(setup.pipeline(), 1):
            self.execute(command, f"تهيئة المحرك {index}/3")
        if not self.check_runtime():
            raise RuntimeError("انتهى التثبيت دون نجاح اختبار استيراد وحدات المعالجة.")

    def check_runtime(self):
        py = setup.python_path()
        if not py.is_file():
            return False
        try:
            result = subprocess.run(
                [str(py), "-c", "import voice_engine.api, argostranslate, faster_whisper, piper"],
                env=setup.setup_environment(), cwd=str(setup.home()), timeout=30,
                creationflags=setup.NO_WINDOW, capture_output=True
            )
            return result.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    def run(self):
        okay = False
        try:
            if self.mode == "audit":
                self.report.emit(setup.detect())
                okay = True
            else:
                required = {
                    "all": ("runtime", "translations", "whisper", "voices", "ffmpeg"),
                    "runtime": ("runtime",),
                    "translations": ("translations",),
                    "whisper": ("whisper",),
                    "voices": ("voices",),
                    "ffmpeg": ("ffmpeg",),
                }.get(self.mode)
                if required is None:
                    raise RuntimeError("عملية إعداد غير معروفة.")
                for i, stage in enumerate(required, 1):
                    if self._stop.is_set():
                        raise RuntimeError("تم إيقاف الإعداد.")
                    self.message.emit(f"المرحلة {i}/{len(required)}: {stage}")
                    if stage == "runtime":
                        self.install_runtime()
                    elif stage == "ffmpeg":
                        a, b = setup.ffmpeg_pair()
                        if a and b:
                            self.message.emit("✓ FFmpeg وFFprobe مثبتان بالفعل.")
                        else:
                            setup.download_ffmpeg(self.message.emit)
                    else:
                        if not self.check_runtime():
                            raise RuntimeError("ثبّت محرك Python أولًا.")
                        self.execute(setup.model_command(stage),
                                     {"translations": "نماذج الترجمة الست",
                                      "whisper": "التعرف على الكلام Whisper",
                                      "voices": "أصوات Piper الست"}[stage])
                self.report.emit(setup.detect())
                okay = True
        except Exception as exc:
            self.problem.emit(str(exc)[:500])
        finally:
            self.done.emit(okay)


class SetupDialog(QDialog):
    def __init__(self, parent=None, *, audit=True):
        super().__init__(parent)
        self.setWindowTitle("NEXVARY Voice — فحص الجهاز وتجهيز الذكاء الاصطناعي")
        self.setMinimumSize(700, 620)
        self.resize(820, 710)
        self.setLayoutDirection(Qt.RightToLeft)
        self.setStyleSheet("""
            QDialog {background:#08111f;color:#edf3fa;font:11pt 'Segoe UI';}
            QLabel {color:#edf3fa;}
            QTextEdit {background:#0b192a;color:#dce7f5;border:1px solid #35516f;
                       border-radius:12px;padding:10px;font:10pt 'Consolas';}
            QPushButton {background:#1e3954;color:#edf3fa;border:1px solid #35516f;
                         border-radius:10px;padding:10px;font-weight:600;min-height:25px;}
            QPushButton:hover {border-color:#49dacc;background:#2d4b66;}
            QPushButton:disabled {color:#74889d;}
            QPushButton#primary {background:#e7c17f;color:#08111f;border:1px solid #e7c17f;}
            QFrame#information {background:#12243a;border:1px solid #314a65;border-radius:13px;}
            QProgressBar {border:1px solid #314a65;border-radius:7px;
                          background:#0d1929;text-align:center;color:#edf3fa;min-height:14px;}
            QProgressBar::chunk {background:#49dacc;border-radius:7px;}
        """)
        self._thread: SetupTask | None = None
        self._result: dict | None = None
        self._build_ui()
        if audit:
            self._start("audit")

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 17, 22, 17)
        layout.setSpacing(12)
        headline = QLabel("فحص الجهاز وتجهيز محرك الذكاء الاصطناعي")
        headline.setStyleSheet("color:#e7c17f;font-size:20pt;font-weight:700")
        layout.addWidget(headline)
        sub = QLabel("سيحدد البرنامج المتطلبات الموجودة والناقصة تلقائيًا. الفحص فقط لا يثبت أي شيء.")
        sub.setWordWrap(True)
        sub.setStyleSheet("color:#adbed0")
        layout.addWidget(sub)

        box = QFrame()
        box.setObjectName("information")
        info = QGridLayout(box)
        self.rows = {}
        captions = [
            ("system", "Windows والمعالج"),
            ("memory", "RAM والمساحة الحرة"),
            ("audio", "الميكروفون والسماعات"),
            ("runtime", "محرك الذكاء الاصطناعي"),
            ("translation", "نماذج الترجمة الست"),
            ("whisper", "التعرف على الكلام Whisper"),
            ("voices", "أصوات النطق الست"),
            ("ffmpeg", "دبلجة الفيديو FFmpeg"),
        ]
        for index, (key, caption) in enumerate(captions):
            label = QLabel(caption)
            label.setStyleSheet("color:#a6b9cf")
            value = QLabel("قيد الفحص …")
            value.setWordWrap(True)
            value.setStyleSheet("color:#e7c17f;font-weight:600")
            info.addWidget(label, index, 0)
            info.addWidget(value, index, 1)
            self.rows[key] = value
        info.setColumnStretch(1, 1)
        layout.addWidget(box)

        self.buttons = {}
        for mode, text in [
            ("all", "تجهيز جميع المكونات تلقائيًا"),
            ("runtime", "تثبيت محرك Python"),
            ("translations", "تحميل الترجمة"),
            ("whisper", "تحميل Whisper"),
            ("voices", "تحميل الأصوات"),
            ("ffmpeg", "تجهيز الفيديو"),
        ]:
            btn = QPushButton(text)
            if mode == "all":
                btn.setObjectName("primary")
            btn.clicked.connect(lambda checked=False, m=mode: self._confirm_and_start(m))
            self.buttons[mode] = btn
        # Multiple rows avoid clipped actions on small laptop screens.
        layout.addWidget(self.buttons["all"])
        second = QHBoxLayout()
        for name in ("runtime", "translations", "whisper"):
            second.addWidget(self.buttons[name])
        layout.addLayout(second)
        third = QHBoxLayout()
        for name in ("voices", "ffmpeg"):
            third.addWidget(self.buttons[name])
        layout.addLayout(third)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        layout.addWidget(self.progress)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("نتائج الفحص والتنزيل ستظهر هنا …")
        self.log.setMinimumHeight(100)
        layout.addWidget(self.log, 1)

        bottom = QHBoxLayout()
        self.scan = QPushButton("إعادة فحص الجهاز")
        self.scan.clicked.connect(lambda: self._start("audit"))
        self.launch = QPushButton("تشغيل محرك الترجمة محليًا")
        self.launch.clicked.connect(self._launch_engine)
        self.stop = QPushButton("إيقاف العملية")
        self.stop.clicked.connect(self._cancel)
        self.dismiss = QPushButton("الانتقال إلى البرنامج")
        self.dismiss.clicked.connect(self.accept)
        bottom.addWidget(self.scan)
        bottom.addWidget(self.launch)
        bottom.addWidget(self.stop)
        bottom.addWidget(self.dismiss)
        layout.addLayout(bottom)
        self.stop.setEnabled(False)

    def _display(self, data):
        self._result = data
        def label(value):
            return "✓ متوفر" if value else "✕ يحتاج إعدادًا"
        cores = data.get("cores") or "?"
        self.rows["system"].setText(str(data.get("os", "?"))[:60] + f" • {cores} معالجات منطقية")
        ram, disk = data.get("ram_gb"), data.get("disk_free_gb")
        self.rows["memory"].setText(f"{ram if ram else 'غير معروف'} GB RAM • {disk if disk else 'غير معروف'} GB مساحة حرة")
        self.rows["audio"].setText("الميكروفون: " + label(data["microphone"]) +
                                   " | السماعات: " + label(data["speakers"]))
        for key, item in [
            ("runtime", "runtime"), ("translation", "translation_ready"),
            ("whisper", "whisper_cached"), ("voices", "voices_ready")
        ]:
            self.rows[key].setText(label(data[item]))
        if data.get("system_python"):
            self.rows["runtime"].setText(
                self.rows["runtime"].text() + " | Python 3.11 موجود بالفعل على الجهاز")
        self.rows["ffmpeg"].setText(
            label(data["ffmpeg"] and data["ffprobe"]) + " (FFmpeg + FFprobe)")
        if not data["uv_bundled"]:
            self._log("تحذير: أداة التثبيت المحمولة غير موجودة في هذا الإصدار.")
            self.buttons["all"].setEnabled(False)
            self.buttons["runtime"].setEnabled(False)
        if ram and ram < 4:
            self._log("ذاكرة الجهاز أقل من 4 GB؛ قد لا تعمل النماذج الثقيلة بصورة مناسبة.")
        if disk is not None and disk < 5:
            self._log("مساحة القرص أقل من 5 GB؛ تجنب تنزيل جميع النماذج قبل توفير مساحة.")

    def _log(self, msg):
        self.log.append(msg)
        scroll = self.log.verticalScrollBar()
        scroll.setValue(scroll.maximum())

    def _start(self, mode):
        if self._thread and self._thread.isRunning():
            return
        self.progress.setRange(0, 0)
        self.scan.setEnabled(False)
        self.launch.setEnabled(False)
        self.dismiss.setEnabled(False)
        self.stop.setEnabled(mode != "audit")
        for b in self.buttons.values():
            b.setEnabled(False)
        job = SetupTask(mode, self)
        self._thread = job
        job.message.connect(self._log)
        job.report.connect(self._display)
        job.problem.connect(lambda err: self._log("خطأ: " + err))
        job.done.connect(lambda okay: self._log("✓ اكتملت العملية." if okay else "لم تكتمل العملية."))
        job.finished.connect(lambda: self._finished(job))
        job.start()

    def _finished(self, worker):
        if self._thread is worker:
            self._thread = None
        worker.deleteLater()
        self.progress.setRange(0, 100)
        self.progress.setValue(100 if self._result else 0)
        self.scan.setEnabled(True)
        self.launch.setEnabled(True)
        self.dismiss.setEnabled(True)
        self.stop.setEnabled(False)
        for b in self.buttons.values():
            b.setEnabled(True)
        if self._result and not self._result.get("uv_bundled"):
            self.buttons["all"].setEnabled(False)
            self.buttons["runtime"].setEnabled(False)

    def _confirm_and_start(self, mode):
        ram = (self._result or {}).get("ram_gb")
        disk = (self._result or {}).get("disk_free_gb")
        if disk is not None and disk < 3:
            QMessageBox.warning(self, "مساحة غير كافية", "يحتاج الإعداد إلى مساحة خالية لا تقل عن 3 GB.")
            return
        if ram is not None and ram < 3 and mode in {"all", "runtime", "whisper"}:
            QMessageBox.warning(self, "ذاكرة غير كافية", "لا يُنصح بتشغيل محرك الصوت على جهاز يقل عن 3 GB RAM.")
            return
        notes = ("ستُنزّل المكونات الناقصة إلى مجلد NEXVARY الخاص بك فقط."
                 " قد يتطلب الإعداد عدة جيجابايت من الإنترنت ومساحة التخزين."
                 " المصادر: Astral uv وPython وPyPI وArgos وHugging Face وgyan.dev."
                 " لا توجد تغييرات في إعدادات النظام أو الشبكة."
                 " تنزيل الأصوات يخضع لتراخيصها الفردية.")
        if QMessageBox.question(self, "تأكيد تنزيل المكونات", notes,
                                QMessageBox.Yes | QMessageBox.No,
                                QMessageBox.No) != QMessageBox.Yes:
            return
        self._start(mode)

    def _launch_engine(self):
        try:
            proc = setup.start_local_engine()
            self._log(f"تم بدء المحرك المحلي (PID {proc.pid}) على 127.0.0.1:8000.")
            self._log("قد يستغرق الإقلاع وقتًا قصيرًا؛ يمكنك الآن فتح إعدادات الاتصال.")
        except Exception as exc:
            QMessageBox.warning(self, "تعذر بدء المحرك", str(exc)[:350])

    def _cancel(self):
        if self._thread:
            self._thread.cancel()
            self._log("طلب إيقاف العملية …")

    def accept(self):
        if self._thread and self._thread.isRunning():
            QMessageBox.information(self, "عملية نشطة",
                                    "لضمان سلامة التثبيت، أوقف العملية أولًا أو انتظر اكتمالها.")
            return
        super().accept()

    def reject(self):
        if self._thread and self._thread.isRunning():
            if self._thread.mode != "audit":
                self._thread.cancel()
            self._thread.wait(2500)
            if self._thread.isRunning():
                QMessageBox.warning(self, "عملية نشطة", "جاري إيقاف مهمة الإعداد؛ أعد محاولة الإغلاق.")
                return
        super().reject()

    def closeEvent(self, event):
        if self._thread and self._thread.isRunning():
            self._thread.cancel()
            if not self._thread.wait(2500):
                event.ignore()
                return
        event.accept()
