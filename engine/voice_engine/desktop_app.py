"""NEXVARY Voice Studio — standalone, Arabic-first Windows graphical client.

PySide6 interface, HTTPS/WS speech transport, remote video jobs, SRT translation.
No system drivers or speech models are silently installed. Windows EXE runs
without a separately installed Python interpreter.
"""
from __future__ import annotations

import os
import sys
import threading
import json
import re
import subprocess
import time
from pathlib import Path

from PySide6.QtCore import Qt, QObject, QThread, QTimer, Signal, QByteArray, QSize, QUrl
from PySide6.QtGui import QIcon, QPixmap, QPainter, QFont, QColor, QDesktopServices, QFontDatabase, QFontMetrics
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
        self.setMinimumSize(780, 560)
        self.engine_manager = desktop_setup.EngineManager()
        self._engine_busy = False
        self._history = []
        self._tasks: list[JobThread] = []
        self._live: LiveThread | None = None
        self._polling = False
        self._video_job = ""
        self._video_file = Path()
        self._translated_srt = ""
        self._init_ui()
        self._set_page(0)
        self._set_status("جاهز — افحص الجهاز ثم جهّز المحرك المحلي.", False)
        self.metrics_timer = QTimer(self)
        self.metrics_timer.setInterval(2000)
        self.metrics_timer.timeout.connect(self._refresh_metrics)
        self.metrics_timer.start()

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
        side.setContentsMargins(12, 14, 12, 14)
        side.setSpacing(6)
        brand = title("NEXVARY", point=24)
        brand.setObjectName("brand")
        side.addWidget(brand)
        side.addWidget(title("VOICE  /  STUDIO", muted=True, point=11))
        side.addSpacing(10)
        self.nav: list[QPushButton] = []
        for i, (label, ico) in enumerate([
            ("الرئيسية", "home"), ("مترجم المحادثات", "languages"),
            ("ترجمة الصوت", "mic"), ("دبلجة الفيديو", "video"),
            ("اللغات والأصوات", "languages"), ("فحص الجهاز", "check"),
            ("إعداد الذكاء الاصطناعي", "download"),
            ("إعدادات الاتصال", "settings"), ("سجل العمليات والتشخيص", "file")
        ]):
            nav = button(label, ico, primary=False)
            nav.setObjectName("navButton")
            nav.setCheckable(True)
            nav.clicked.connect(lambda checked=False, idx=i: self._set_page(idx))
            self.nav.append(nav)
            side.addWidget(nav)
        side.addStretch()
        back = button("رجوع", "swap", primary=False)
        back.clicked.connect(self._back)
        side.addWidget(back)
        side.addWidget(title("DESKTOP EDITION  •  v0.5.2", muted=True, point=10))
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
        sidebar_scroll = QScrollArea()
        sidebar_scroll.setWidgetResizable(True); sidebar_scroll.setFixedWidth(255)
        sidebar_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        sidebar_scroll.setWidget(sidebar)
        layout.addWidget(sidebar_scroll)
        layout.addWidget(main, 1)

        self.stack.addWidget(self._home())
        self.stack.addWidget(self._conversation())
        self.stack.addWidget(self._audio())
        self.stack.addWidget(self._video())
        self.stack.addWidget(self._languages())
        self.stack.addWidget(self._diagnostic_page())
        self.stack.addWidget(self._setup_page())
        self.stack.addWidget(self._settings())
        self.stack.addWidget(self._logs_page())

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
        self.video_srt_save = button('حفظ SRT للدبلجة','download',primary=False)
        self.video_srt_save.setEnabled(False); self.video_srt_save.clicked.connect(self._save_dub_srt)
        form.addWidget(self.video_srt_save)
        self.video_cancel = button('إلغاء مهمة الدبلجة','stop',primary=False)
        self.video_cancel.setEnabled(False); self.video_cancel.clicked.connect(self._cancel_video)
        form.addWidget(self.video_cancel)
        preview = button('معاينة آخر فيديو محفوظ','play',primary=False)
        preview.clicked.connect(self._preview_video); form.addWidget(preview)
        self._last_video = None
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
            "المحرك المحلي: افتح مركز إعداد الذكاء الاصطناعي، جهّز المكونات ثم اضغط تشغيل المحرك. "
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

    def _back(self):
        if self._history:
            index = self._history.pop()
            self.stack.setCurrentIndex(index)
            for i,nav in enumerate(self.nav): nav.setChecked(i == index)
        else: self._set_page(0)

    def _setup_page(self):
        scroll,col = self._viewport("مركز إعداد الذكاء الاصطناعي", "تجهيز مستقل في بيانات المستخدم، ثم تشغيل محرك محلي خاص بهذا الجهاز.")
        panel,form = card()
        audit = button("فحص وتجهيز المكونات الناقصة", "download")
        audit.clicked.connect(self.open_device_setup); form.addWidget(audit)
        self.engine_controls = []
        for action,label,ico in [('start','تشغيل المحرك','play'),('stop','إيقاف المحرك','stop'),('restart','إعادة تشغيل المحرك','swap')]:
            btn = button(label,ico,primary=False)
            btn.clicked.connect(lambda checked=False,a=action:self._engine_action(a))
            form.addWidget(btn); self.engine_controls.append(btn)
        check = button("اختبار اتصال المحرك", "check", primary=False)
        check.clicked.connect(self._check_connection); form.addWidget(check)
        self.engine_metrics = title("المحرك متوقف", muted=True, point=11); form.addWidget(self.engine_metrics)
        self.quality = QComboBox()
        for model in ('tiny','base','small'): self.quality.addItem(model,model)
        self.quality.setCurrentText(desktop_setup.load_preferences()['whisper_model'])
        self.quality.currentTextChanged.connect(self._quality_changed)
        form.addWidget(title("جودة Whisper — تُطبق بعد تجهيز النموذج وإعادة تشغيل المحرك",point=12))
        form.addWidget(self.quality)
        col.addWidget(panel); col.addStretch(); return scroll

    def _quality_changed(self, model):
        desktop_setup.save_preferences(model)
        self._set_status("تم حفظ النموذج " + model + ". جهّزه من معالج الإعداد ثم أعد تشغيل المحرك.", True)

    def _engine_action(self, action):
        if self._engine_busy: return
        if self._live and self._live.isRunning() or self.video_poll.isActive():
            self._set_status("أوقف المحادثة أو انتظر انتهاء الدبلجة قبل تغيير حالة المحرك.",False); return
        self._engine_busy = True
        for btn in self.engine_controls: btn.setEnabled(False)
        self._set_status("جارٍ " + action + " للمحرك المحلي…",False)
        def done(message):
            self._engine_busy = False
            for btn in self.engine_controls: btn.setEnabled(True)
            if action != 'stop': self.endpoint.setText('http://127.0.0.1:8000')
            self._set_status(message,True)
        def failed(_):
            self._engine_busy = False
            for btn in self.engine_controls: btn.setEnabled(True)
        self._task(getattr(self.engine_manager,action),done,on_error=failed)

    def _refresh_metrics(self):
        metrics = self.engine_manager.metrics()
        self.engine_metrics.setText(f"حالة المحرك: {metrics['state']} | CPU: {metrics['cpu_percent'] if metrics['cpu_percent'] is not None else 'غير مقاس'} % | RAM: {metrics['ram_mb'] if metrics['ram_mb'] is not None else 'غير مقاسة'} MB")

    def _diagnostic_page(self):
        scroll,col = self._viewport("NEXVARY Smart System Diagnostic", "فحص آمن دون حذف أو تثبيت أي مكونات.")
        panel,form = card()
        self.diagnostic_text = QTextEdit(); self.diagnostic_text.setReadOnly(True); self.diagnostic_text.setMinimumHeight(280)
        form.addWidget(self.diagnostic_text)
        check = button("فحص الجهاز الآن",'check'); check.clicked.connect(self._audit)
        form.addWidget(check); self.audit_button = check
        col.addWidget(panel); col.addStretch(); return scroll

    def _audit(self):
        self.audit_button.setEnabled(False)
        def done(data):
            self.audit_button.setEnabled(True)
            states = {'ready':'متوفر وجاهز','missing':'يحتاج تثبيتًا','incompatible':'إصدار غير متوافق',
                      'repair':'يحتاج إصلاحًا','failed':'فشل الفحص','unsupported':'غير مدعوم','unverified':'يحتاج اختبارًا فعليًا'}
            lines = [f"النظام: {data.get('os','غير معروف')}",f"المعالج: {data.get('cpu','غير معروف')}",
                     f"الأنوية المنطقية: {data.get('cores','غير معروف')}",
                     f"RAM: {data.get('ram_gb','غير معروفة')} GB — المتاح: {data.get('probes',{}).get('ram_available_gb','غير معروف')} GB",
                     f"المساحة الحرة: {data.get('disk_free_gb','غير معروفة')} GB",
                     f"أجهزة الصوت: {data.get('audio_reason','غير مفحوصة')}"]
            for value in data.get('probes',{}).values():
                if isinstance(value,dict) and 'state' in value:
                    lines.append(value['name']+' — '+states.get(value['state'],value['state'])+'\n'+value['reason'])
            for label,key in [('Runtime','runtime_details'),('FFmpeg','ffmpeg_status'),('FFprobe','ffprobe_status')]:
                value = data.get(key,{})
                lines.append(label+' — '+states.get(value.get('state'), 'لم يُفحص')+'\n'+value.get('reason',''))
            self.diagnostic_text.setPlainText('\n\n'.join(lines))
            self._language_result(data)
            self._set_status("اكتمل فحص الجهاز؛ الاختبارات الوظيفية منفصلة عن وجود الملفات.",True)
        self._task(desktop_setup.detect,done,on_error=lambda _:self.audit_button.setEnabled(True))

    def _languages(self):
        scroll,col = self._viewport("إدارة اللغات والأصوات", "حالة الترجمة في الاتجاهين، وصوت Piper لكل لغة. الاختيار لا يعني جاهزية النموذج.")
        panel,form = card()
        self.language_rows = {}
        for name,code in LANGS.items():
            row = QHBoxLayout(); row.addWidget(title(name,point=12))
            state = title("لم تُفحص النماذج بعد",muted=True,point=10)
            row.addWidget(state,1); self.language_rows[code] = state
            sample = button('استماع','play',primary=False)
            sample.clicked.connect(lambda checked=False,c=code:self._sample(c)); row.addWidget(sample)
            form.addLayout(row)
        refresh = button('فحص اللغات المثبتة','check'); refresh.clicked.connect(self._audit)
        form.addWidget(refresh)
        verify = button('اختبار فعلي وتجهيز أصوات ناقصة','settings',primary=False)
        verify.clicked.connect(self.open_device_setup); form.addWidget(verify)
        col.addWidget(panel); col.addStretch(); return scroll

    def _language_result(self, data):
        states = (data.get('model_details') or {}).get('languages',{})
        functional = data.get('functional_tests',{})
        for code,label in self.language_rows.items():
            state = states.get(code)
            if state:
                translations=functional.get('translations',{})
                results=translations.get('data',{})
                directions=[v for k,v in results.items() if code in k.split('->')]
                translation_ok=len(directions)==10 and all(v.get('state')=='ready' for v in directions) and translations.get('current_assets_unchanged')
                voice_result=functional.get('voices',{})
                voice_ok=voice_result.get('current_assets_unchanged') and voice_result.get('data',{}).get(code,{}).get('state')=='ready'
                label.setText(('الترجمة: اجتازت الاختبار' if translation_ok else 'الترجمة: نموذج موجود ويحتاج اختبارًا' if state['to_english'] and state['from_english'] else 'الترجمة: مسار ناقص') + ' | ' + ('الصوت: اجتاز توليد WAV' if voice_ok else state.get('voice_reason','يحتاج فحصًا')))

            else: label.setText('لم يُعثر على تقرير لهذه اللغة؛ لا تُعتبر جاهزة.')

    def _sample(self, code):
        path = desktop_setup.home()/'samples'/(code+'.wav')
        if not path.is_file():
            self._set_status('لا توجد عينة فعلية. جهّز الأصوات ثم شغّل الاختبار الوظيفي.',False); return
        output_device = self.output_device.currentData()
        def play():
            import sounddevice as sd
            import wave
            with wave.open(str(path)) as wav:
                with sd.RawOutputStream(samplerate=wav.getframerate(),channels=wav.getnchannels(),
                                        dtype='int16',device=output_device) as stream:
                    stream.write(wav.readframes(wav.getnframes()))
            return 'تم إرسال العينة إلى السماعة المحددة؛ تحقق من سماعها.'
        self._task(play,lambda result:self._set_status(result,True))

    def _logs_page(self):
        scroll,col = self._viewport('سجل العمليات والتشخيص','أخطاء مفهومة وتقارير الاختبارات المحلية دون حفظ رموز API.')
        self.operation_log = QTextEdit(); self.operation_log.setReadOnly(True); self.operation_log.setMinimumHeight(280)
        col.addWidget(self.operation_log)
        read = button('عرض تقرير الاختبارات الفعلية','file',primary=False)
        read.clicked.connect(self._read_validation); col.addWidget(read)
        engine = button('عرض سجل المحرك المحلي','file',primary=False)
        engine.clicked.connect(self._read_engine_log); col.addWidget(engine)
        col.addStretch(); return scroll

    def _safe_log(self, message):
        if self._secret_value: message = message.replace(self._secret_value,'[REDACTED]')
        message = re.sub(r'(?i)Bearer\s+[^\s]+', 'Bearer [REDACTED]', str(message))
        return message

    def _read_validation(self):
        path = desktop_setup.home()/'functional-tests.json'
        try: self.operation_log.setPlainText(self._safe_log(path.read_text(encoding='utf-8')))
        except OSError: self._set_status('لا يوجد تقرير اختبارات فعلية بعد؛ شغّل الاختبار من معالج الإعداد.',False)

    def _read_engine_log(self):
        path = desktop_setup.home()/'engine.log'
        try:
            with path.open('rb') as source:
                source.seek(max(0,path.stat().st_size-40000))
                self.operation_log.setPlainText(self._safe_log(source.read().decode('utf-8',errors='replace')))
        except OSError: self._set_status('لا يوجد سجل للمحرك المحلي بعد.',False)

    def open_device_setup(self):
        dialog = SetupDialog(self)
        dialog.exec()
        if dialog._result: self._language_result(dialog._result)
        self._set_status("أُغلق معالج الإعداد. شغّل المحرك من مركز إعداد الذكاء الاصطناعي.", False)

    def _set_page(self, index):
        current = self.stack.currentIndex()
        if current != index: self._history.append(current)
        self.stack.setCurrentIndex(index)
        for i, nav in enumerate(self.nav):
            nav.setChecked(i == index)

    def _set_status(self, message: str, success: bool):
        if hasattr(self, 'operation_log'):
            self.operation_log.append(self._safe_log(message))
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
            if getattr(self, '_closing_after_engine', False) and not self._tasks:
                self._closing_after_engine = False
                QTimer.singleShot(0,self.close)

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
        if self._video_job and self.video_poll.isActive():
            self._set_status("انتظر انتهاء الدبلجة قبل بدء المحادثة الصوتية.", False); return
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
        if self._live and self._live.isRunning():
            self._set_status("أوقف المحادثة الصوتية قبل بدء الدبلجة.", False); return
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
            self.video_cancel.setEnabled(True)
            self.video_srt_save.setEnabled(False)
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
            self.job_status.setText("حالة الدبلجة: " + state + " | " + str(data.get("phase", "")) + " | " + str(data.get("completed_segments",0)) + "/" + str(data.get("total_segments") or "غير معروف"))
            if state in ("complete", "failed", "cancelled"):
                self.video_cancel.setEnabled(False)
                self.video_poll.stop()
            if state == "complete":
                self.video_save.setEnabled(True)
                self.video_srt_save.setEnabled(True)
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
            self._last_video = Path(p)
            self._set_status("تم حفظ الفيديو: " + str(p), True)
        self._task(lambda: self._api().download_video(self._video_job, Path(path)),
                   success, on_error=lambda _: self.video_save.setEnabled(True))

    def _cancel_video(self):
        if not self._video_job: return
        self.video_cancel.setEnabled(False)
        self._task(lambda:self._api().cancel_video(self._video_job),
                   lambda _:self._set_status('تم طلب الإلغاء؛ يتوقف بعد مرحلة النموذج الحالية.',True),
                   on_error=lambda _:self.video_cancel.setEnabled(True))

    def _save_dub_srt(self):
        path,_ = QFileDialog.getSaveFileName(self,'حفظ SRT للدبلجة','NEXVARY-Dubbed.srt','SRT (*.srt)')
        if not path: return
        self._task(lambda:self._api().download_subtitles(self._video_job,Path(path)),
                   lambda result:self._set_status('تم حفظ '+str(result),True))

    def _preview_video(self):
        if self._last_video and self._last_video.is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._last_video.resolve())))
        else: self._set_status('احفظ فيديو مكتملًا أولًا ثم شغّل المعاينة.',False)

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
        self.metrics_timer.stop()
        if self.engine_manager.process is not None:
            # Shutdown only our own loopback child. Never terminate external services.
            if self._engine_busy:
                event.ignore(); return
            self._engine_busy = True
            self._closing_after_engine = True
            self._task(self.engine_manager.stop, lambda _: setattr(self, '_engine_busy', False),
                       on_error=lambda _: setattr(self, '_engine_busy',False))
            event.ignore(); return
        event.accept()


STYLE = """
QWidget { background:#08111f; color:#edf3fa; font-family:'Segoe UI'; }
QLabel { background:transparent; }
QPushButton, QLineEdit, QComboBox, QTextEdit { font-size:13px; }
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
    # The offscreen Windows Qt platform may not enumerate system fonts. Register
    # Windows' installed UI fonts explicitly, also covering frozen GUI captures.
    if sys.platform == 'win32':
        font_dir = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts'
        for name in ('segoeui.ttf', 'segoeuib.ttf', 'seguisb.ttf', 'arial.ttf'):
            path = font_dir / name
            if path.is_file():
                QFontDatabase.addApplicationFont(str(path))
    app.setFont(QFont("Segoe UI", 11))
    app.setLayoutDirection(Qt.RightToLeft)
    window = VoiceWindow()
    if "--screenshots" in argv:
        directory = Path(argv[argv.index('--screenshots')+1]); directory.mkdir(parents=True,exist_ok=True)
        window.show()
        for index,name in [(0,'dashboard'),(4,'languages'),(6,'setup'),(3,'video')]:
            window._set_page(index); app.processEvents()
            window.grab().save(str(directory/(name+'.png')))
        wizard = SetupDialog(window,audit=False); wizard.show(); app.processEvents()
        wizard.grab().save(str(directory/'diagnostic.png'))
        wizard.close(); window.close()
        return 0
    if "--self-test" in argv:
        assert QFontMetrics(app.font()).inFontUcs4(0x0627), 'Arabic font glyph missing'
        wizard = SetupDialog(window, audit=False)
        assert len(wizard.rows) == 8
        assert "all" in wizard.buttons
        wizard.close()
        assert window.stack.count() == 9
        assert len(window.nav) == 9
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
