"""NEXVARY first-launch graphical diagnostics and one-click setup.

First scan never modifies computer. Downloads only from an explicit button
with a clear confirmation. Managed runtime remains isolated under LocalAppData.
"""
from __future__ import annotations

import os
import json
import subprocess
import threading
from pathlib import Path

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QTextEdit,
    QPushButton, QMessageBox, QProgressBar, QFrame, QSizePolicy, QScrollArea, QWidget, QComboBox, QDialogButtonBox, QTabWidget
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
    progress = Signal(object)
    planned = Signal(object)

    def __init__(self, mode: str, parent=None, *, plan_mode="all", state=None):
        super().__init__(parent)
        self.mode = mode
        self.plan_mode = plan_mode
        self.state = state or {}
        self._stop = threading.Event()
        self._process = None

    def cancel(self):
        self._stop.set()
        if self._process and self._process.poll() is None:
            setup.stop_owned_process(self._process)

    def execute(self, argv, label):
        if self._stop.is_set(): raise RuntimeError("تم إيقاف الإعداد.")
        self.message.emit(label)
        self.progress.emit({"component":label, "bytes":0, "total":None})
        dest = setup.home(); dest.mkdir(parents=True, exist_ok=True)
        self._process = subprocess.Popen(argv, env=setup.setup_environment(), cwd=str(dest),
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1, creationflags=setup.NO_WINDOW)
        try:
            for line in self._process.stdout:
                if self._stop.is_set(): setup.stop_owned_process(self._process); break
                text = line.strip()
                if text.startswith("PROGRESS:"):
                    try: self.progress.emit(json.loads(text[9:]))
                    except ValueError: pass
                elif text: self.message.emit(text[-350:])
            code = self._process.wait(timeout=10)
            if self._stop.is_set(): raise RuntimeError("تم إيقاف الإعداد؛ أعد المحاولة لاستكمال المكونات الناقصة.")
            if code: raise RuntimeError("فشل " + label + f" (code {code}).")
        finally:
            if self._process.poll() is None:
                self._process.kill(); self._process.wait(timeout=5)
            self._process = None

    def check_runtime(self):
        return setup.runtime_report().get("state") == "ready"

    def install_runtime(self):
        from .diagnostics import write_probe
        write_probe(setup.home())
        if self.check_runtime():
            self.message.emit("تم التحقق من Runtime الموجود؛ لا حاجة لإعادة التثبيت."); return
        for command in setup.pipeline(): self.execute(command, "تهيئة Runtime مستقل")
        if not self.check_runtime(): raise RuntimeError("فشل اختبار استيراد مكونات المحرك.")

    def verify(self, stage):
        self.execute([str(setup.python_path()), "-m", "voice_engine.validation", stage],
                     "اختبار وظيفي: " + stage)

    def run(self):
        okay = False
        try:
            if self.mode == "audit":
                self.report.emit(setup.detect()); okay = True
            elif self.mode == "plan":
                from .setup_plan import build_plan
                self.planned.emit(build_plan(self.state, setup.home(), self.plan_mode)); okay = True
            elif self.mode == "verify":
                self.verify("all"); okay = True
            else:
                stages = {"all":("runtime","ffmpeg","translations","whisper","voices"),
                          "runtime":("runtime",), "ffmpeg":("ffmpeg",),
                          "translations":("translations",), "whisper":("whisper",), "voices":("voices",)}.get(self.mode)
                if stages is None: raise RuntimeError("عملية غير معروفة.")
                failures = []
                for stage in stages:
                    if self._stop.is_set(): raise RuntimeError("تم إيقاف الإعداد.")
                    try:
                        if stage == "runtime": self.install_runtime()
                        elif stage == "ffmpeg":
                            state = setup.detect()
                            if state['ffmpeg'] and state['ffprobe']:
                                self.message.emit("FFmpeg وFFprobe اجتازا اختبار التشغيل؛ لا تنزيل جديد.")
                            else:
                                setup.download_ffmpeg(self.message.emit,
                                    progress=lambda n,t:self.progress.emit({"component":"FFmpeg", "bytes":n, "total":t}),
                                    cancelled=self._stop.is_set)
                        else:
                            if not self.check_runtime(): raise RuntimeError("بيئة المعالجة غير جاهزة.")
                            self.execute(setup.model_command(stage), "تجهيز " + stage)
                            if stage in {"translations","voices"}: self.verify(stage)
                    except Exception as exc:
                        failures.append(stage + ": " + str(exc))
                        self.problem.emit(failures[-1])
                        if stage == "runtime" or self._stop.is_set(): break
                if self.mode == "all" and not self._stop.is_set() and self.check_runtime():
                    for stage in ('whisper','video'):
                        try: self.verify(stage)
                        except Exception as exc:
                            failures.append(stage + ': ' + str(exc)); self.problem.emit(failures[-1])
                if failures: raise RuntimeError("لم يكتمل الإعداد: " + "; ".join(failures))
                okay = True
        except Exception as exc:
            self.problem.emit(str(exc)[:500])
        finally:
            if self.mode not in {"audit","plan"}:
                try: self.report.emit(setup.detect())
                except Exception as exc: self.problem.emit("تعذر إعادة الفحص: " + str(exc)[:200])
            self.done.emit(okay)


class SetupDialog(QDialog):
    def __init__(self, parent=None, *, audit=True):
        super().__init__(parent)
        self.setWindowTitle("NEXVARY Voice — فحص الجهاز وتجهيز الذكاء الاصطناعي")
        self.setMinimumSize(660, 540)
        self.resize(820, 710)
        self.setLayoutDirection(Qt.RightToLeft)
        self.setStyleSheet("""
            QDialog {background:#08111f;color:#edf3fa;font:11pt 'Segoe UI';}
            QLabel {color:#edf3fa;background:transparent;}
            QTabWidget::pane {border:1px solid #314a65;}
            QTabBar::tab {background:#13243b;color:#edf3fa;padding:12px;}
            QTabBar::tab:selected {color:#e7c17f;border-bottom:2px solid #e7c17f;}
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
        self._okay = False
        self._pending_plan = None
        self._thread: SetupTask | None = None
        self._result: dict | None = None
        self._build_ui()
        if audit:
            self._start("audit")

    def _build_ui(self):
        outer = QVBoxLayout(self)
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        content = QWidget(); scroll.setWidget(content); outer.addWidget(scroll)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(22, 17, 22, 17)
        layout.setSpacing(12)
        headline = QLabel("فحص الجهاز وتجهيز محرك الذكاء الاصطناعي")
        headline.setStyleSheet("color:#e7c17f;font-size:20pt;font-weight:700")
        layout.addWidget(headline)
        sub = QLabel("سيحدد البرنامج المتطلبات الموجودة والناقصة تلقائيًا. الفحص فقط لا يثبت أي شيء.")
        sub.setWordWrap(True)
        sub.setStyleSheet("color:#adbed0")
        layout.addWidget(sub)

        outer_layout = layout
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs,1)
        overview = QWidget(); layout = QVBoxLayout(overview)
        self.tabs.addTab(overview,'نتائج الفحص')
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
            field = QFrame(); field.setObjectName('information')
            field_layout = QVBoxLayout(field)
            field_layout.addWidget(label); field_layout.addWidget(value)
            info.addWidget(field,index//2,index%2)
            self.rows[key] = value
        info.setColumnStretch(1, 1)
        layout.addWidget(box)
        self.details = QLabel("")
        self.details.setWordWrap(True)
        layout.addWidget(self.details)
        row = QHBoxLayout()
        row.addWidget(QLabel("جودة Whisper — CPU INT8"))
        self.model_choice = QComboBox()
        for name in ('tiny','base','small'): self.model_choice.addItem(name, name)
        self.model_choice.setCurrentText(setup.load_preferences()['whisper_model'])
        self.model_choice.currentTextChanged.connect(lambda name: setup.save_preferences(name))
        row.addWidget(self.model_choice)
        layout.addLayout(row)

        controls = QWidget(); layout = QVBoxLayout(controls)
        self.tabs.addTab(controls,'التجهيز والاختبارات')
        self.buttons = {}
        for mode, text in [
            ("all", "تجهيز محرك الذكاء الاصطناعي تلقائيًا"),
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
        self.verify_button = QPushButton("اختبار النماذج فعليًا — الترجمة والأصوات ودبلجة عينة")
        self.verify_button.clicked.connect(lambda: self._start("verify"))
        layout.addWidget(self.verify_button)
        layout.addStretch()
        layout = outer_layout
        self.progress_info = QLabel("لا توجد عملية تنزيل نشطة")
        self.progress_info.setWordWrap(True)
        layout.addWidget(self.progress_info)
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
        self.details.setText("\n".join(
            f"{v['name']}: {v['state']} — {v['reason']}" for v in data.get('probes',{}).values() if isinstance(v,dict) and 'state' in v))
        def label(value):
            return "متوفر — لم يُختبر وظيفيًا" if value else "يحتاج إعدادًا — مفقود أو غير صالح"
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
        self.rows['runtime'].setText(data.get('runtime_details',{}).get('reason','لم يُفحص Runtime بعد'))
        self.rows['whisper'].setText(('ملف نموذج موجود؛ يلزم اختبار ASR' if data['whisper_cached'] else 'نموذج مفقود') + ' | المحدد: ' + data.get('selected_model','base') + ' | المقترح المبدئي: ' + data.get('recommended_model','base'))
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
        self.log.append(str(msg).replace(os.getenv("NEXVARY_API_TOKEN", "") or "\0", "[REDACTED]"))
        scroll = self.log.verticalScrollBar()
        scroll.setValue(scroll.maximum())

    def _start(self, mode):
        if self._thread and self._thread.isRunning():
            return
        self._okay = False
        self.progress.setRange(0, 0)
        self.model_choice.setEnabled(False)
        self.verify_button.setEnabled(False)
        self.scan.setEnabled(False)
        self.launch.setEnabled(False)
        self.dismiss.setEnabled(False)
        self.stop.setEnabled(mode != "audit")
        for b in self.buttons.values():
            b.setEnabled(False)
        job = SetupTask(mode, self, plan_mode=getattr(self, "_plan_mode", "all"), state=self._result)
        self._thread = job
        job.message.connect(self._log)
        job.progress.connect(self._progress)
        job.planned.connect(lambda plan: setattr(self, "_pending_plan", plan))
        job.report.connect(self._display)
        job.problem.connect(lambda err: self._log("خطأ: " + err))
        job.done.connect(self._outcome)
        job.finished.connect(lambda: self._finished(job))
        job.start()

    def _finished(self, worker):
        if self._thread is worker:
            self._thread = None
        worker.deleteLater()
        if self.progress.maximum() == 0:
            self.progress.setRange(0, 100); self.progress.setValue(0)
        self.model_choice.setEnabled(True)
        self.verify_button.setEnabled(True)
        self.scan.setEnabled(True)
        self.launch.setEnabled(True)
        self.dismiss.setEnabled(True)
        self.stop.setEnabled(False)
        for b in self.buttons.values():
            b.setEnabled(True)
        if self._pending_plan is not None:
            plan, self._pending_plan = self._pending_plan, None
            self._review_plan(plan)
        if self._result and not self._result.get("uv_bundled"):
            self.buttons["all"].setEnabled(False)
            self.buttons["runtime"].setEnabled(False)

    def _progress(self, data):
        n, total = data.get('bytes',0), data.get('total')
        self.progress_info.setText(data.get('component','') + ' — ' + f'{n/1024**2:.1f} MB' + (f' / {total/1024**2:.1f} MB' if total else ' — حجم إجمالي غير معروف'))
        if total:
            self.progress.setRange(0,100); self.progress.setValue(min(100, int(n*100/total)))
        else: self.progress.setRange(0,0)

    def _outcome(self, okay):
        self._okay = okay
        self._log('اكتملت المرحلة واجتازت اختبارات هذه المرحلة.' if okay else 'لم تكتمل العملية؛ راجع أسباب الفشل وأعد المحاولة.')

    def _confirm_and_start(self, mode):
        self.tabs.setCurrentIndex(1)
        self._plan_mode = mode
        self._start('plan')

    def _review_plan(self, plan):
        if plan['unavailable']:
            self._log('تنبيه — غير متاح من المصدر: ' + '; '.join(plan['unavailable']))
        disk = (self._result or {}).get('disk_free_gb')
        if disk is not None and disk < plan['storage_estimate_gb']:
            QMessageBox.warning(self, 'مساحة غير كافية', 'المساحة الاحتياطية المطلوبة: ' + str(plan['storage_estimate_gb']) + ' GB'); return
        dialog = QDialog(self); dialog.setWindowTitle('المكونات والتراخيص — موافقة واحدة قبل التنزيل')
        dialog.resize(650,560); dialog.setLayoutDirection(Qt.RightToLeft)
        layout = QVBoxLayout(dialog)
        details = QTextEdit(); details.setReadOnly(True)
        details.setPlainText('المكونات الناقصة أو المطلوب التحقق منها:\n' + '\n'.join(plan['missing']) +
            '\n\nتنزيل أصوات ناقصة: ' + str(round(plan['voice_download_bytes']/1024**2,1)) + ' MB' +
            '\nمساحة احتياطية: ' + str(plan['storage_estimate_gb']) + ' GB\n' + plan['execution'] + '\n' + plan['note'] +
            '\n\nتراخيص الأصوات والمكونات:\n' + '\n\n'.join(plan['licenses']) +
            '\n\nالموافقة تسمح بتنزيل المكونات الناقصة وتشغيل اختبارات محلية فقط.')
        layout.addWidget(details)
        controls = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        controls.button(QDialogButtonBox.Ok).setText('أوافق — بدء التجهيز')
        controls.button(QDialogButtonBox.Cancel).setText('إلغاء')
        controls.accepted.connect(dialog.accept); controls.rejected.connect(dialog.reject)
        layout.addWidget(controls)
        if dialog.exec() == QDialog.Accepted: self._start(self._plan_mode)

    def _launch_engine(self):
        parent = self.parent()
        if parent is not None and hasattr(parent, '_engine_action'):
            parent._engine_action('start')
            self._log('بدء اختبار تشغيل المحرك؛ تظهر النتيجة في حالة التطبيق.')
        else:
            QMessageBox.information(self, 'المحرك المحلي', 'استخدم لوحة إدارة المحرك في البرنامج.')

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
