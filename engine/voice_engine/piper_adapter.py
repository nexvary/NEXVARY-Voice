"""Offline Piper API adapter; no implicit Arabic diacritizer downloads.

Windows espeak's narrow native paths can reject Arabic usernames. Try the OS
short-path alias, otherwise stage only bundled public phoneme data in an owned
ASCII temporary folder. No model redownload, system edit or admin requirement.
"""
from __future__ import annotations
import atexit
import ctypes
import os
import shutil
import tempfile
import threading
import wave
from functools import lru_cache
from pathlib import Path

_lock = threading.RLock()


def short_path(path: Path) -> str:
    value = str(path.resolve())
    if os.name != 'nt' or value.isascii(): return value
    buffer = ctypes.create_unicode_buffer(32768)
    size = ctypes.windll.kernel32.GetShortPathNameW(value,buffer,len(buffer))
    return buffer.value if 0 < size < len(buffer) and buffer.value.isascii() else value


@lru_cache(maxsize=1)
def phoneme_data() -> str:
    import piper
    source = Path(piper.__file__).parent/'espeak-ng-data'
    if not (source/'phontab').is_file(): raise RuntimeError('بيانات Piper espeak-ng غير مرفقة في Runtime.')
    alias = short_path(source)
    if os.name != 'nt' or alias.isascii(): return alias
    # Only package-owned public data is copied, not user audio or transcripts.
    candidates = [Path(tempfile.gettempdir())]
    windir = os.getenv('WINDIR')
    if windir: candidates.append(Path(windir)/'Temp')
    for parent in candidates:
        if not parent.is_dir(): continue
        owned = None
        try:
            owned = Path(tempfile.mkdtemp(prefix='nexvary-phonemes-',dir=parent))
            candidate = owned/'espeak-ng-data'
            candidate_alias = short_path(candidate)
            # Parent alias is sufficient before candidate is created.
            if not str(Path(short_path(owned))/'espeak-ng-data').isascii():
                shutil.rmtree(owned);continue
            shutil.copytree(source,candidate)
            alias = short_path(candidate)
            atexit.register(shutil.rmtree,owned,ignore_errors=True)
            return alias
        except OSError:
            if owned: shutil.rmtree(owned,ignore_errors=True)
    raise RuntimeError('تعذر إنشاء مسار متوافق لبيانات النطق؛ لم تتغير إعدادات الجهاز.')


@lru_cache(maxsize=2)
def voice(model: str, revision: tuple):
    from piper import PiperVoice
    instance = PiperVoice.load(model,espeak_data_dir=phoneme_data())
    if hasattr(instance,'use_tashkeel'): instance.use_tashkeel = False
    return instance


def synthesize(text: str, model: str, target: Path):
    path = Path(model)
    config = Path(model+'.json')
    if not config.is_file(): raise RuntimeError('ملف إعداد الصوت غير موجود.')
    with _lock:
        instance = voice(str(path),(path.stat().st_size,path.stat().st_mtime_ns,config.stat().st_mtime_ns))
        with wave.open(str(target),'wb') as wav:
            if hasattr(instance,'synthesize_wav'): instance.synthesize_wav(text,wav)
            else: instance.synthesize(text,wav)
