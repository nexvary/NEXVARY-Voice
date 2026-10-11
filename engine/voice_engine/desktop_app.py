"""NEXVARY Voice Studio — standalone, Arabic-first Windows graphical client.

PySide6 interface, HTTPS/WS speech transport, remote video jobs, SRT translation.
No system drivers or speech models are silently installed. Windows EXE runs
without a separately installed Python interpreter.
"""
from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

from PySide6.QtCore import Qt, QObject, QThread, QTimer, Signal, QByteArray, QSize
from PySide6.QtGui import QIcon, QPixmap, QPainter, QFont, QColor, QDesktopServices
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QHBoxLayout, QVBoxLayout,
    QGridLayout, QLabel, QPushButton, QLineEdit, QTextEdit, QComboBox,
    QStackedWidget, QFileDialog, QMessageBox, QScrollArea, QProgressBar,
    QSpacerItem, QSizePolicy, QCheckBox
)

from .desktop_api import DesktopAPI, ClientError, websocket_url
from .desktop_audio import run_audio_session
from .setup_wizard import SetupDialog
from . import desktop_setup

COLORS = {
    "background": "#08111f", "panel": "#101e32", "raised": "#172942",
    "border": "#2e455f", "gold": "#e7c17f", "cyan": "#49dacc",
    "silver": "#edf3fa", "muted": "#a3b6cb", "blue": "#62acff",
    "red": "#ef868c",
}
LANGS = {"العربية": "ar", "English": "en", "हिन्दी": "hi", "Türkçe": "tr",
         "Français": "fr", "Deutsch": "de", "Español": "es", "Italiano": "it", "Русский": "ru", "বাংলা": "bn"}
ICON_PATHS = {
    "home": '<path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1z"/>',
    "languages": '<path d="M5 8h12M9 5v3c0 6-3 9-6 11M6 12c3 2 5 4 9 5M14 19l4-9 4 9M15 17h6"/>',
    "mic": '<rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10v2a7 7 0 0 0 14 0v-2M12 19v3M8 22h8"/>',
    "video": '<rect x="2" y="4" width="20" height="16" rx="3"/><path d="m10 8 6 4-6 4z"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M5 19l2-2M17 7l2-2"/>',
    "swap": '<path d="M4 7h16m-4-4 4 4-4 4M20 17H4m4-4-4 4 4 4"/>',
    "cloud": '<path d="M6 18h13a4 4 0 0 0 0-8h-1a6 6 0 0 0-11-2 5 5 0 0 0-1 10z"/>',
    "file": '<path d="M6 2h8l6 6v14H6zM14 2v6h6M9 13h8M9 17h7"/>',
    "play": '<path d="m8 5 12 7-12 7z"/>',
    "stop": '<rect x="6" y="6" width="12" height="12" rx="2"/>',
    "download": '<path d="M12 3v13m-4-4 4 4 4-4M4 19v3h16v-3"/>',
    "check": '<path d="m3 12 6 6L21 6"/>',
    "copy": '<rect x="8" y="8" width="12" height="13" rx="2"/><path d="M16 8V5H4v12h4"/>',
}


def vector_icon(name: str, color: str, size: int = 30) -> QIcon:
    shape = ICON_PATHS[name]
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
           'fill="none" stroke="' + color + '" stroke-width="1.8" '
           'stroke-linecap="round" stroke-linejoin="round">' + shape + '</svg>')
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    QSvgRenderer(QByteArray(svg.encode("utf-8"))).render(painter)
    painter.end()
    return QIcon(pix)


class JobThread(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, target, parent=None):
        super().__init__(parent)
        self.target = target

    def run(self):
        try:
            self.completed.emit(self.target())
        except Exception as exc:
            self.failed.emit(str(exc)[:350])


class LiveThread(QThread):
    note = Signal(str)
    failed = Signal(str)

    def __init__(self, url, token, source, target, input_device, output_device, parent=None):
        super().__init__(parent)
        self.url, self.token = url, token
        self.source, self.target = source, target
        self.input_device, self.output_device = input_device, output_device
        self.stop_signal = threading.Event()

    def run(self):
        try:
            run_audio_session(self.url, self.token, self.source, self.target,
                              self.stop_signal, self.note.emit,
                              self.input_device, self.output_device)
        except Exception as exc:
            if not self.stop_signal.is_set():
                self.failed.emit(str(exc)[:300])

    def stop(self):
        self.stop_signal.set()


def button(text: str, icon: str | None = None, primary: bool = True) -> QPushButton:
    btn = QPushButton(text)
    btn.setCursor(Qt.PointingHandCursor)
    btn.setMinimumHeight(45)
    btn.setProperty("kind", "primary" if primary else "secondary")
    if icon:
        btn.setIcon(vector_icon(icon, COLORS["background"] if primary else COLORS["cyan"], 22))
        btn.setIconSize(QSize(22, 22))
    return btn


def field(placeholder="", secret=False) -> QLineEdit:
    entry = QLineEdit()
    entry.setPlaceholderText(placeholder)
    entry.setMinimumHeight(43)
    if secret:
        entry.setEchoMode(QLineEdit.Password)
    return entry


def title(text: str, muted=False, point=13) -> QLabel:
    label = QLabel(text)
    label.setObjectName("secondaryText" if muted else "sectionText")
    label.setFont(QFont("Segoe UI", point, QFont.DemiBold if not muted else QFont.Normal))
    label.setWordWrap(True)
    return label


def card() -> tuple[QFrame, QVBoxLayout]:
    outer = QFrame()
    outer.setObjectName("contentCard")
    vertical = QVBoxLayout(outer)
    vertical.setContentsMargins(22, 19, 22, 21)
    vertical.setSpacing(12)
    return outer, vertical


def language_box(default="ar") -> QComboBox:
    combo = QComboBox()
    for label, code in LANGS.items():
        combo.addItem(label, code)
    position = combo.findData(default)
    combo.setCurrentIndex(max(0, position))
    combo.setMinimumHeight(42)
    return combo


class VoiceWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NEXVARY Voice Studio  |  Windows")
        self.resize(1150, 790)
        self.setMinimumSize(880, 620)
        self._tasks: list[JobThread] = []
        self._live: LiveThread | None = None
        self._polling = False
        self._video_job = ""
        self._video_file = Path()
        self._translated_srt = ""
        self._init_ui()
        self._set_page(0)
        self._set_status("جاهز — اضبط عنوان المحرك من الإعدادات.", False)

    def _init_ui(self):
        self.setStyleSheet(STYLE)
        parent = QWidget()
        self.setCentralWidget(parent)
        layout = QHBoxLayout(parent)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(245)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(15, 26, 15, 20)
        side.setSpacing(11)
        brand = title("NEXVARY", point=24)
        brand.setObjectName("brand")
        side.addWidget(brand)
        side.addWidget(title("VOICE  /  STUDIO", muted=True, point=11))
        side.addSpacing(28)
        self.nav: list[QPushButton] = []
        for i, (label, ico) in enumerate([
            ("الرئيسية", "home"), ("مترجم المحادثات", "languages"),
            ("ترجمة الصوت", "mic"), ("دبلجة الفيديو", "video"),
            ("إعدادات الاتصال", "settings")
        ]):
            nav = button(label, ico, primary=False)
            nav.setObjectName("navButton")
            nav.setCheckable(True)
            nav.clicked.connect(lambda checked=False, idx=i: self._set_page(idx))
            self.nav.append(nav)
            side.addWidget(nav)
        side.addStretch()
        setup_button = button("فحص الجهاز وتجهيز الذكاء الاصطناعي", "settings", primary=False)
        setup_button.clicked.connect(self.open_device_setup)
        side.addWidget(setup_button)
        side.addWidget(title("DESKTOP EDITION  •  v0.5.0", muted=True, point=10))
        side.addWidget(title("Windows 10 / 11", muted=True, point=10))

        main = QFrame()
        main.setObjectName("mainArea")
        body = QVBoxLayout(main)
        body.setContentsMargins(26, 21, 26, 19)
        body.setSpacing(10)
        headline = QHBoxLayout()
        headline.addWidget(title("NEXVARY VOICE  |  منصة الترجمة الذكية", point=18), 1)
        self.indicator = QLabel("○  لم يُختبر الاتصال")
        self.indicator.setObjectName("indicator")
        headline.addWidget(self.indicator)
        body.addLayout(headline)
        self.stack = QStackedWidget()
        body.addWidget(self.stack, 1)
        statusbar = QFrame()
        statusbar.setObjectName("statusBar")
        status_row = QHBoxLayout(statusbar)
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        status_row.addWidget(self.status_label, 1)
        body.addWidget(statusbar)
        layout.addWidget(sidebar)
        layout.addWidget(main, 1)

        self.stack.addWidget(self._home())
        self.stack.addWidget(self._conversation())
        self.stack.addWidget(self._audio())
        self.stack.addWidget(self._video())
        self.stack.addWidget(self._settings())

    def _viewport(self, name, desc):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        base = QWidget()
        col = QVBoxLayout(base)
        col.setContentsMargins(4, 15, 7, 18)
        col.setSpacing(17)
        col.addWidget(title(name, point=24))
        col.addWidget(title(desc, muted=True, point=11))
        scroll.setWidget(base)
        return scroll, col

    def _home(self):
        scroll, col = self._viewport("تواصل بلغتك… أينما كنت",
            "محادثات متعددة اللغات  •  تعليق صوتي مترجم  •  دبلجة فيديو")
        hero, inner = card()
        hero.setObjectName("heroCard")
        inner.addWidget(title("لغة واحدة لم تعد حاجزًا", point=21))
        inner.addWidget(title("ابدأ ترجمة المحادثات، أو استخدم ميكروفون الكمبيوتر، أو أرسل فيديو للدبلجة.",
                              muted=True, point=12))
        go = button("ابدأ محادثة", "languages")
        go.clicked.connect(lambda: self._set_page(1))
        inner.addWidget(go)
        inspect_button = button("فحص الجهاز وتجهيز النماذج", "settings", primary=False)
        inspect_button.clicked.connect(self.open_device_setup)
        inner.addWidget(inspect_button)
        col.addWidget(hero)
        for name, note, ico, target in [
            ("مترجم المحادثات", "ترجمة النص في الاتجاهين من خلال محركك الخاص.", "languages", 1),
            ("ترجمة صوتية عبر الميكروفون", "مقاطع PCM16 مع استماع صوتي؛ ليست بثًا متزامنًا صفري التأخير.", "mic", 2),
            ("دبلجة MP4", "رفع فيديو، متابعة المهمة، وحفظ النسخة المدبلجة.", "video", 3)
        ]:
            frame, row = card()
            header = QHBoxLayout()
            label = QLabel()
            label.setPixmap(vector_icon(ico, COLORS["cyan"], 30).pixmap(30, 30))
            header.addWidget(label)
            header.addWidget(title(name, point=14), 1)
            visit = button("فتح", primary=False)
            visit.clicked.connect(lambda checked=False, idx=target: self._set_page(idx))
            header.addWidget(visit)
            row.addLayout(header)
            row.addWidget(title(note, muted=True, point=11))
            col.addWidget(frame)
        col.addStretch()
        return scroll

    def _pair(self, source="ar", target="en"):
        bar = QHBoxLayout()
        left = language_box(source)
        right = language_box(target)
        swap = button("تبديل", "swap", primary=False)
        swap.clicked.connect(lambda: self._swap(left, right))
        bar.addWidget(title("من", point=11))
        bar.addWidget(left, 1)
        bar.addWidget(swap)
        bar.addWidget(title("إلى", point=11))
        bar.addWidget(right, 1)
        return bar, left, right

    @staticmethod
    def _swap(first, second):
        left, right = first.currentIndex(), second.currentIndex()
        first.setCurrentIndex(right)
        second.setCurrentIndex(left)

    def _conversation(self):
        scroll, col = self._viewport("مترجم المحادثات",
            "ترجمة النصوص بالتناوب: اختر لغة المتحدث ولغة المستمع.")
        panel, form = card()
        pair, self.text_source, self.text_target = self._pair("hi", "ar")
        form.addLayout(pair)
        form.addWidget(title("كلام المتحدث", point=12))
        self.original = QTextEdit()
        self.original.setPlaceholderText("اكتب هنا العبارة المطلوب ترجمتها…")
        self.original.setMinimumHeight(120)
        form.addWidget(self.original)
        self.text_go = button("ترجم الآن", "languages")
        self.text_go.clicked.connect(self._translate)
        form.addWidget(self.text_go)
        form.addWidget(title("النص المترجم", point=12))
        self.translation = QTextEdit()
        self.translation.setReadOnly(True)
        self.translation.setMinimumHeight(120)
        form.addWidget(self.translation)
        row = QHBoxLayout()
        copied = button("نسخ الترجمة", "copy", primary=False)
        copied.clicked.connect(self._copy_translation)
        swap = button("رد باللغة الأخرى", "swap", primary=False)
        swap.clicked.connect(self._reply)
        row.addWidget(copied)
        row.addWidget(swap)
        form.addLayout(row)
        col.addWidget(panel)
        col.addStretch()
        return scroll

    def _audio(self):
        scroll, col = self._viewport("الترجمة الصوتية عبر Windows",
            "التقاط الميكروفون وإرسال مقاطع 3.2 ثوانٍ، وتشغيل الرد عبر سماعات Windows.")
        panel, form = card()
        pair, self.audio_source, self.audio_target = self._pair("ar", "en")
        form.addLayout(pair)
        form.addWidget(title("ميكروفون الكمبيوتر", point=12))
        self.input_device = QComboBox()
        self.output_device = QComboBox()
        self.input_device.addItem("الميكروفون الافتراضي (Windows)", None)
        self.output_device.addItem("السماعة الافتراضية (Windows)", None)
        form.addWidget(self.input_device)
        form.addWidget(title("الصوت المترجم يخرج من", point=12))
        form.addWidget(self.output_device)
        reload_devices = button("تحديث أجهزة الصوت", primary=False)
        reload_devices.clicked.connect(self._list_audio_devices)
        form.addWidget(reload_devices)
        buttons = QHBoxLayout()
        self.audio_start = button("ابدأ ترجمة الصوت", "mic")
        self.audio_start.clicked.connect(self._start_audio)
        self.audio_stop = button("إيقاف الميكروفون", "stop", primary=False)
        self.audio_stop.clicked.connect(self._stop_audio)
        self.audio_stop.setEnabled(False)
        buttons.addWidget(self.audio_start)
        buttons.addWidget(self.audio_stop)
        form.addLayout(buttons)
        form.addWidget(title("سجل التعرف على الكلام والترجمة", point=12))
        self.audio_log = QTextEdit()
        self.audio_log.setReadOnly(True)
        self.audio_log.setMinimumHeight(150)
        form.addWidget(self.audio_log)
        form.addWidget(title(
            "يحتاج WSS آمنًا، ومزود Whisper/ترجمة/صوت مثبتًا. لا ينشئ ميكروفونًا افتراضيًا لبرامج البث.",
            muted=True, point=11))
        col.addWidget(panel)
        col.addStretch()
        return scroll

    def _video(self):
        scroll, col = self._viewport("دبلجة الفيديو",
            "أرسل MP4 إلى المحرك، تابع تقدم المهمة، ثم احفظ الملف النهائي.")
        panel, form = card()
        pair, self.video_source, self.video_target = self._pair("ar", "en")
        form.addLayout(pair)
        choose = button("اختيار ملف فيديو MP4", "file", primary=False)
        choose.clicked.connect(self._pick_video)
        form.addWidget(choose)
        self.selected_video = title("لم يتم اختيار فيديو", muted=True, point=11)
        form.addWidget(self.selected_video)
        self.upload = button("إرسال الفيديو للدبلجة", "video")
        self.upload.clicked.connect(self._upload_video)
        form.addWidget(self.upload)
        self.job_status = title("لا توجد مهمة دبلجة نشطة.", muted=True, point=11)
        form.addWidget(self.job_status)
        self.video_poll = QTimer(self)
        self.video_poll.setInterval(3000)
        self.video_poll.timeout.connect(self._check_video)
        self.video_save = button("حفظ الفيديو المدبلج", "download")
        self.video_save.setEnabled(False)
        self.video_save.clicked.connect(self._save_video)
        form.addWidget(self.video_save)
        form.addWidget(title(
            "حد الرفع 80 MB. قد تفشل المهمة إذا لم تُثبَّت نماذج Whisper وArgos وPiper على محرك المعالجة.",
            muted=True, point=11))
        col.addWidget(panel)
        sub, sub_form = card()
        sub_form.addWidget(title("ترجمة الترجمة الزمنية SRT", point=15))
        self.srt_file = Path()
        self.srt_info = title("اختر ملف SRT ثم احفظ الترجمة النصية.", muted=True, point=11)
        sub_form.addWidget(self.srt_info)
        line = QHBoxLayout()
        browse = button("اختيار SRT", "file", primary=False)
        browse.clicked.connect(self._pick_srt)
        self.srt_translate = button("ترجمة ملف SRT", "languages")
        self.srt_translate.clicked.connect(self._translate_srt)
        line.addWidget(browse)
        line.addWidget(self.srt_translate)
        sub_form.addLayout(line)
        col.addWidget(sub)
        col.addStretch()
        return scroll

    def _settings(self):
        scroll, col = self._viewport("الاتصال والإعدادات",
            "اتصال بمحرك على نفس الكمبيوتر أو على خادم آمن؛ دون حفظ رموز المصادقة على القرص.")
        panel, form = card()
        form.addWidget(title("عنوان خادم الترجمة", point=12))
        self.endpoint = field("https://your-domain.example")
        self.endpoint.setLayoutDirection(Qt.LeftToRight)
        self.endpoint.setText(os.getenv("NEXVARY_VOICE_URL", "http://127.0.0.1:8000"))
        self._endpoint_value = self.endpoint.text()
        self.endpoint.textChanged.connect(lambda value: setattr(self, "_endpoint_value", value))
        form.addWidget(self.endpoint)
        form.addWidget(title("API Token", point=12))
        self.secret = field("Bearer token (session only)", secret=True)
        self.secret.setLayoutDirection(Qt.LeftToRight)
        self._secret_value = ""
        self.secret.textChanged.connect(lambda value: setattr(self, "_secret_value", value))
        # Do not persist secrets in registry, AppData or Qt settings.
        form.addWidget(self.secret)
        setup_btn = button("فحص الجهاز وتثبيت المكونات الناقصة", "settings", primary=False)
        setup_btn.clicked.connect(self.open_device_setup)
        form.addWidget(setup_btn)
        check = button("اختبار الاتصال", "cloud")
        check.clicked.connect(self._check_connection)
        form.addWidget(check)
        form.addWidget(title(
            "محرك محلي: شغّل خدمة Python منفصلة بنماذجك، ثم استخدم عنوان 127.0.0.1. "
            "خادم Ubuntu الخفيف لا يعالج الصوت بنفسه، ويجب ربطه بمحرك استدلال.",
            muted=True, point=11))
        col.addWidget(panel)
        panel2, more = card()
        more.addWidget(title("حماية البيانات والخصوصية", point=15))
        more.addWidget(title("الصوت والفيديو ينتقلان إلى الخادم الذي تختاره فقط بعد الضغط على البدء. "
                             "لا يتم تنزيل نماذج أو تثبيت تعريفات أو تعديل إعدادات Windows تلقائيًا.",
                             muted=True, point=11))
        more.addWidget(title("التطبيق لا يحفظ رمز API، ولا يستبدل ميكروفون تطبيقات أخرى. "
                             "يستخدم سماعات Windows والتوجيه القياسي للصوت.",
                             muted=True, point=11))
        col.addWidget(panel2)
        col.addStretch()
        return scroll

    def open_device_setup(self):
        dialog = SetupDialog(self)
        dialog.exec()
        self._set_status("أُغلق معالج الإعداد. تحقق من الاتصال بمحركك المحلي.", False)

    def _set_page(self, index):
        self.stack.setCurrentIndex(index)
        for i, nav in enumerate(self.nav):
            nav.setChecked(i == index)

    def _set_status(self, message: str, success: bool):
        self.status_label.setText(("●  " if success else "◌  ") + message)
        self.status_label.setStyleSheet("color:" + (COLORS["cyan"] if success else COLORS["muted"]))

    def _api(self):
        return DesktopAPI(self._endpoint_value, self._secret_value)

    def _task(self, func, success, *, on_error=None):
        worker = JobThread(func, self)
        self._tasks.append(worker)

        def completed(data):
            success(data)

        def failed(reason):
            self._set_status(reason, False)
            if on_error:
                on_error(reason)

        def cleanup():
            if worker in self._tasks:
                self._tasks.remove(worker)
            worker.deleteLater()

        worker.completed.connect(completed)
        worker.failed.connect(failed)
        worker.finished.connect(cleanup)
        worker.start()

    def _check_connection(self):
        self._set_status("جاري فحص الخادم…", False)
        self._task(lambda: self._api().health(), self._health_result)

    def _health_result(self, data):
        if data.get("worker_configured") is False:
            self.indicator.setText("●  بوابة دون محرك")
            self._set_status("البوابة متصلة، لكن خادم الاستدلال غير مرتبط بعد.", False)
        else:
            self.indicator.setText("●  الخادم يستجيب")
            self._set_status("استجاب الخادم. يلزم اختبار النماذج أيضًا.", True)

    def _translate(self):
        text = self.original.toPlainText().strip()
        if not text:
            self._set_status("أدخل النص أولًا.", False)
            return
        source, target = self.text_source.currentData(), self.text_target.currentData()
        self.text_go.setEnabled(False)
        self._set_status("جارٍ ترجمة النص…", False)

        def success(value):
            self.text_go.setEnabled(True)
            self.translation.setPlainText(value)
            self._set_status("اكتملت الترجمة.", True)

        self._task(lambda: self._api().translate(text, source, target),
                   success, on_error=lambda _: self.text_go.setEnabled(True))

    def _copy_translation(self):
        text = self.translation.toPlainText()
        if text:
            QApplication.clipboard().setText(text)
            self._set_status("تم نسخ الترجمة.", True)

    def _reply(self):
        text = self.translation.toPlainText().strip()
        if not text: return
        self._swap(self.text_source, self.text_target)
        self.original.setPlainText(text)
        self.translation.clear()

    def _list_audio_devices(self):
        self.input_device.clear()
        self.output_device.clear()
        self.input_device.addItem("الميكروفون الافتراضي (Windows)", None)
        self.output_device.addItem("السماعة الافتراضية (Windows)", None)
        try:
            import sounddevice as sd
            for index, device in enumerate(sd.query_devices()):
                name = f"{index}  {device['name']}"
                if device["max_input_channels"] > 0:
                    self.input_device.addItem(name, index)
                if device["max_output_channels"] > 0:
                    self.output_device.addItem(name, index)
            self._set_status("تم تحميل قائمة أجهزة الصوت.", True)
        except Exception as exc:
            self._set_status("تعذر قراءة أجهزة الصوت: " + type(exc).__name__, False)

    def _start_audio(self):
        if self._live and self._live.isRunning():
            return
        try:
            url = websocket_url(self.endpoint.text())
        except ClientError as exc:
            self._set_status(str(exc), False)
            return
        source, target = self.audio_source.currentData(), self.audio_target.currentData()
        if source == target:
            self._set_status("اختر لغتين مختلفتين.", False)
            return
        self._live = LiveThread(url, self.secret.text(), source, target,
                                self.input_device.currentData(), self.output_device.currentData(), self)
        self._live.note.connect(self._audio_note)
        self._live.failed.connect(self._audio_failed)
        self._live.finished.connect(self._audio_stopped)
        self.audio_log.clear()
        self.audio_start.setEnabled(False)
        self.audio_stop.setEnabled(True)
        self._live.start()
        self._set_status("جارٍ بدء التقاط الصوت…", False)

    def _audio_note(self, text):
        self.audio_log.append(text)
        self._set_status(text, True)

    def _audio_failed(self, text):
        self.audio_log.append("خطأ: " + text)
        self._set_status(text, False)

    def _stop_audio(self):
        if self._live:
            self._live.stop()
        self.audio_stop.setEnabled(False)

    def _audio_stopped(self):
        self.audio_start.setEnabled(True)
        self.audio_stop.setEnabled(False)
        self._live = None

    def _pick_video(self):
        path, _ = QFileDialog.getOpenFileName(self, "اختيار فيديو", "", "MP4 video (*.mp4)")
        if path:
            self._video_file = Path(path)
            self.selected_video.setText(self._video_file.name)

    def _upload_video(self):
        if not self._video_file.is_file():
            self._set_status("اختر فيديو MP4 صحيحًا.", False)
            return
        self.upload.setEnabled(False)
        self.video_save.setEnabled(False)
        self._set_status("جارٍ رفع الفيديو إلى محرك الدبلجة…", False)
        source, target = self.video_source.currentData(), self.video_target.currentData()

        def success(data):
            self.upload.setEnabled(True)
            self._video_job = str(data["job_id"])
            self.job_status.setText("المهمة " + self._video_job[:16] + " • " + str(data.get("status")))
            self.video_poll.start()
            self._set_status("تم إرسال الفيديو؛ يجري فحص حالة المهمة.", True)

        self._task(lambda: self._api().submit_video(self._video_file, source, target),
                   success, on_error=lambda _: self.upload.setEnabled(True))

    def _check_video(self):
        if self._polling or not self._video_job: return
        self._polling = True

        def done(data):
            self._polling = False
            state = str(data.get("status", "unknown"))
            self.job_status.setText("حالة الدبلجة: " + state)
            if state in ("complete", "failed"):
                self.video_poll.stop()
            if state == "complete":
                self.video_save.setEnabled(True)
                self._set_status("انتهت الدبلجة؛ اختر حفظ الفيديو.", True)
            if state == "failed":
                self._set_status("تعذرت الدبلجة: " + str(data.get("error", ""))[:180], False)

        self._task(lambda: self._api().video_status(self._video_job), done,
                   on_error=lambda _: setattr(self, "_polling", False))

    def _save_video(self):
        if not self._video_job: return
        path, _ = QFileDialog.getSaveFileName(self, "حفظ الفيديو المدبلج",
                                              "NEXVARY-Dubbed.mp4", "MP4 video (*.mp4)")
        if not path: return
        self.video_save.setEnabled(False)
        self._set_status("جارٍ تنزيل الفيديو النهائي…", False)
        def success(p):
            self.video_save.setEnabled(True)
            self._set_status("تم حفظ الفيديو: " + str(p), True)
        self._task(lambda: self._api().download_video(self._video_job, Path(path)),
                   success, on_error=lambda _: self.video_save.setEnabled(True))

    def _pick_srt(self):
        path, _ = QFileDialog.getOpenFileName(self, "اختيار ملف ترجمة", "", "SRT files (*.srt)")
        if path:
            self.srt_file = Path(path)
            self.srt_info.setText(self.srt_file.name)

    def _translate_srt(self):
        if not self.srt_file.is_file():
            self._set_status("اختر ملف SRT أولًا.", False)
            return
        output, _ = QFileDialog.getSaveFileName(self, "حفظ SRT المترجم",
            str(self.srt_file.with_name(self.srt_file.stem + "-translated.srt")),
            "SRT files (*.srt)")
        if not output: return
        if Path(output).exists():
            self._set_status("اختر اسم ملف جديدًا؛ لا يُسمح باستبدال الملف الحالي.", False)
            return
        source, target = self.video_source.currentData(), self.video_target.currentData()
        self.srt_translate.setEnabled(False)

        def task():
            text = self.srt_file.read_text(encoding="utf-8-sig")
            translated = self._api().translate_srt(text, source, target)
            with Path(output).open("x", encoding="utf-8") as stream:
                stream.write(translated)
            return output
        self._task(task, lambda value: (self.srt_translate.setEnabled(True),
                 self._set_status("تم حفظ ملف الترجمة: " + value, True)),
                 on_error=lambda _: self.srt_translate.setEnabled(True))

    def closeEvent(self, event):
        if self._live and self._live.isRunning():
            self._live.stop()
            if not self._live.wait(2500):
                self._set_status("أوقف الميكروفون قبل إغلاق التطبيق.", False)
                event.ignore()
                return
        if self._tasks:
            QMessageBox.information(self, "NEXVARY Voice",
                                    "توجد عملية نقل أو ترجمة قيد التنفيذ. أعد المحاولة بعد انتهائها.")
            event.ignore()
            return
        self.video_poll.stop()
        event.accept()


STYLE = """
QWidget { background:#08111f; color:#edf3fa; font-family:'Segoe UI'; font-size:13px; }
QFrame#sidebar { background:#101e32; border-right:1px solid #2e455f; }
QFrame#mainArea { background:#08111f; }
QLabel#brand { color:#e7c17f; letter-spacing:2px; }
QLabel#secondaryText { color:#a3b6cb; }
QLabel#sectionText { color:#edf3fa; }
QLabel#indicator { color:#49dacc; font-weight:600; padding:9px 13px;
    border:1px solid #2e455f; border-radius:13px; background:#172942; }
QFrame#contentCard { border:1px solid #2e455f; border-radius:19px; background:#101e32; }
QFrame#heroCard { border:1px solid #b6955e; border-radius:19px; background:#182c45; }
QFrame#statusBar { background:#101e32; border:1px solid #2e455f; border-radius:10px; }
QPushButton { border-radius:11px; background:#172942; border:1px solid #2e455f;
    color:#edf3fa; padding:9px 15px; font-weight:600; text-align:center; }
QPushButton:hover { background:#28445f; border-color:#49dacc; }
QPushButton:pressed { background:#2a5068; }
QPushButton:disabled { color:#75869b; background:#18263a; border-color:#25344a; }
QPushButton[kind="primary"] { color:#08111f; background:#e7c17f; border-color:#e7c17f; }
QPushButton[kind="primary"]:hover { background:#ffe0a9; }
QPushButton#navButton { text-align:left; padding-left:16px; min-height:29px; }
QPushButton#navButton:checked { color:#e7c17f; background:#1c3550; border:1px solid #b6955e; }
QLineEdit, QTextEdit, QComboBox { background:#0d1929; border:1px solid #35506b;
    border-radius:10px; padding:10px; selection-background-color:#2b6885; }
QLineEdit:focus, QTextEdit:focus, QComboBox:focus { border-color:#e7c17f; }
QComboBox::drop-down { border:none; width:24px; }
QComboBox QAbstractItemView { background:#172942; selection-background-color:#315476; }
QScrollArea { border:none; background:transparent; }
QScrollBar:vertical { width:10px; background:#101e32; }
QScrollBar::handle:vertical { background:#365370; border-radius:5px; min-height:25px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
"""


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("NEXVARY.Voice.Studio")
        except Exception:
            pass
    app = QApplication([sys.argv[0]])
    app.setFont(QFont("Segoe UI", 11))
    app.setLayoutDirection(Qt.RightToLeft)
    window = VoiceWindow()
    if "--self-test" in argv:
        assert window.stack.count() == 5
        assert len(window.nav) == 5
        assert window.audio_start.isEnabled()
        assert window.upload.isEnabled()
        if getattr(sys, "frozen", False):
            assert desktop_setup.uv_path().is_file(), "uv.exe missing from frozen package"
            assert (desktop_setup.source_dir() / "pyproject.toml").is_file()
            assert (desktop_setup.source_dir() / "voice_engine" / "setup_assets.py").is_file()
        # PyInstaller --windowed can have sys.stdout=None; printing then exits 1.
        if sys.stdout is not None:
            try:
                print("NEXVARY Voice Desktop UI smoke test: PASS")
            except (OSError, ValueError):
                pass
        return 0
    window.show()
    QTimer.singleShot(350, window.open_device_setup)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
