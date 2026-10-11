"""Read-only system probes. A failed probe never means 'ready'."""
from __future__ import annotations
import json
import os
import platform
import socket
import subprocess
import tempfile
from pathlib import Path

STATES = {'ready', 'missing', 'incompatible', 'repair', 'failed', 'unsupported', 'unverified'}


def item(name, state, reason):
    assert state in STATES
    return {'name': name, 'state': state, 'reason': reason}


def inspect_binary(path: str | None) -> dict:
    if not path: return item('binary', 'missing', 'لم يُعثر على ملف تنفيذي في مسارات التطبيق أو PATH.')
    try:
        result = subprocess.run([str(path), '-version'], capture_output=True, text=True,
                                timeout=8, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode != 0: return item('binary', 'repair', 'الملف موجود لكن اختبار التشغيل فشل.')
        lines = result.stdout.splitlines()
        if not lines or not lines[0].lower().startswith(('ffmpeg version','ffprobe version')):
            return item('binary','repair','الملف لا يعرّف نفسه كإصدار FFmpeg/FFprobe صالح.')
        return item('binary', 'ready', lines[0][:160])
    except (OSError, subprocess.SubprocessError):
        return item('binary', 'failed', 'تعذر تشغيل الملف للتحقق من الإصدار.')


def system_probes(base: Path, application: Path) -> dict:
    result = {}
    supported = platform.system() == 'Windows' and platform.machine().lower() in {'amd64', 'x86_64'}
    result['windows'] = item('Windows x64', 'ready' if supported else 'unsupported', platform.platform())
    try:
        import psutil
        mem = psutil.virtual_memory()
        result['ram_available_gb'] = round(mem.available / 1024**3, 1)
        result['physical_cores'] = psutil.cpu_count(logical=False)
        result['logical_cores'] = psutil.cpu_count()
    except ImportError:
        result['ram_available_gb'] = None
        result['physical_cores'] = None
        result['logical_cores'] = os.cpu_count()
    try:
        with socket.create_connection(('huggingface.co', 443), timeout=3): pass
        result['internet'] = item('الاتصال بالإنترنت', 'ready', 'نجح اتصال TCP بمنفذ HTTPS؛ صلاحية التنزيل تُفحص عند الطلب.')
    except OSError:
        result['internet'] = item('الاتصال بالإنترنت', 'failed', 'تعذر الاتصال بمصدر النماذج؛ قد يكون الاتصال محجوبًا أو منقطعًا.')
    # Check OS access without creating files during discovery.
    for key, folder in [('data_writable', base), ('application_writable', application)]:
        ancestor = folder
        while not ancestor.exists() and ancestor != ancestor.parent: ancestor = ancestor.parent
        result[key] = item('الكتابة في المجلد', 'unverified' if os.access(ancestor, os.W_OK) else 'repair',
                           'صلاحية نظام الملفات متاحة؛ اختبار كتابة فعلي يُجرى قبل الإعداد.' if os.access(ancestor, os.W_OK)
                           else 'صلاحية الكتابة غير متاحة. لا تُغيّر صلاحيات Windows تلقائيًا.')
    with socket.socket() as sock:
        sock.settimeout(0.3)
        occupied = sock.connect_ex(('127.0.0.1', 8000)) == 0
    result['port'] = item('127.0.0.1:8000', 'unverified' if occupied else 'ready',
                          'المنفذ مستخدم؛ يلزم التحقق من هوية الخدمة قبل استخدامه.' if occupied else 'المنفذ متاح للمحرك المحلي.')
    result['gpu'] = item('GPU', 'unverified', 'وجود GPU لا يضمن تسريع Whisper. يُستخدم CPU INT8 حتى يُثبت دعم CUDA.')
    if platform.system() == 'Windows':
        # Query device metadata through a fixed read-only script, never user text.
        script = ('Get-CimInstance Win32_VideoController | Select-Object Name,AdapterRAM | ConvertTo-Json -Compress')
        try:
            out = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                                 capture_output=True, text=True, timeout=8,
                                 creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if out.returncode == 0 and out.stdout.strip():
                result['gpu_devices'] = json.loads(out.stdout)
        except (OSError, ValueError, subprocess.SubprocessError): pass
    result['bluetooth'] = item('Bluetooth Audio', 'unverified',
                               'تظهر أجهزة الصوت المتصلة في قائمة الإدخال والإخراج؛ لا يتم البحث أو الاقتران تلقائيًا.')
    return result


def write_probe(base: Path):
    base.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryFile(dir=base) as output:
        output.write(b'NEXVARY write probe')
        output.flush()
