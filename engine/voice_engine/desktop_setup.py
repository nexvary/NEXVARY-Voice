"""Windows first-run audit and managed inference installation.

Never modifies firewall, system Python, PATH, Nginx or Ubuntu.
Only explicit GUI action authorizes model/binary downloads. A bundled uv.exe
manages an isolated Python 3.11 environment under LocalAppData.
"""
from __future__ import annotations

import ctypes
import json
import os
import platform
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

LANG_CODES = ("ar", "en", "it", "ru", "es", "bn")
WHISPER_SIZE = {"tiny", "base", "small"}
FFMPEG_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def home() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "NEXVARY" / "Voice"


def resources() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))


def source_dir() -> Path:
    return resources() / "engine"


def uv_path() -> Path:
    return resources() / "bin" / "uv.exe"


def python_path(base: Path | None = None) -> Path:
    return (base or home()) / "runtime" / "Scripts" / "python.exe"


def binaries(base: Path | None = None) -> Path:
    return (base or home()) / "bin"


def setup_environment(base: Path | None = None) -> dict[str, str]:
    dest = base or home()
    env = dict(os.environ)
    env["UV_CACHE_DIR"] = str(dest / "cache")
    env["UV_PYTHON_INSTALL_DIR"] = str(dest / "pythons")
    env["UV_NO_PROGRESS"] = "1"
    env["ARGOS_PACKAGES_DIR"] = str(dest / "argos")
    env["HF_HOME"] = str(dest / "huggingface")
    env["NEXVARY_WHISPER_MODEL"] = "base"
    env["NEXVARY_ASR_DEVICE"] = "cpu"
    env["PATH"] = str(binaries(dest)) + os.pathsep + str(python_path(dest).parent) + os.pathsep + env.get("PATH", "")
    voice_file = dest / "voices.json"
    if voice_file.exists():
        try:
            voices = json.loads(voice_file.read_text(encoding="utf-8-sig"))
            if isinstance(voices, dict):
                env["NEXVARY_PIPER_VOICES"] = json.dumps(voices)
        except (ValueError, OSError):
            pass
    return env


def memory_gb() -> float | None:
    if sys.platform != "win32":
        return None
    class Mem(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ulong),
                    ("memory_load", ctypes.c_ulong),
                    ("total_phys", ctypes.c_ulonglong),
                    ("avail_phys", ctypes.c_ulonglong),
                    ("total_page", ctypes.c_ulonglong),
                    ("avail_page", ctypes.c_ulonglong),
                    ("total_virtual", ctypes.c_ulonglong),
                    ("avail_virtual", ctypes.c_ulonglong),
                    ("avail_extended", ctypes.c_ulonglong)]
    m = Mem()
    m.length = ctypes.sizeof(m)
    if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
        return round(m.total_phys / (1024 ** 3), 1)
    return None


def ffmpeg_pair(base: Path | None = None) -> tuple[str | None, str | None]:
    b = binaries(base)
    a = b / "ffmpeg.exe"
    p = b / "ffprobe.exe"
    if a.is_file() and p.is_file():
        return str(a), str(p)
    return shutil.which("ffmpeg"), shutil.which("ffprobe")


def model_report(base: Path | None = None) -> dict | None:
    dest = base or home()
    python = python_path(dest)
    if not python.is_file():
        return None
    try:
        result = subprocess.run(
            [str(python), "-m", "voice_engine.model_status"],
            cwd=str(dest), env=setup_environment(dest), capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=45,
            creationflags=NO_WINDOW, check=True
        )
        return json.loads(result.stdout)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def detect(base: Path | None = None) -> dict:
    """Non-mutating report. No downloads, shell commands or Python prompts."""
    dest = base or home()
    try:
        free = round(shutil.disk_usage(dest if dest.exists() else dest.anchor or Path.home()).free / 1024 ** 3, 1)
    except OSError:
        free = None
    ffmpeg, ffprobe = ffmpeg_pair(dest)
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        microphone = any(d["max_input_channels"] > 0 for d in devices)
        speakers = any(d["max_output_channels"] > 0 for d in devices)
    except Exception:
        microphone = speakers = False
    model = model_report(dest)
    whisper_dir = dest / "huggingface" / "hub" / "models--Systran--faster-whisper-base"
    whisper = whisper_dir / "snapshots"
    whisper_present = whisper.is_dir() and any(
        (child / "model.bin").is_file() for child in whisper.iterdir() if child.is_dir()
    )
    return {
        "os": platform.platform(), "cpu": platform.processor() or platform.machine(),
        "cores": os.cpu_count(), "ram_gb": memory_gb(), "disk_free_gb": free,
        "microphone": microphone, "speakers": speakers,
        "ffmpeg": bool(ffmpeg), "ffprobe": bool(ffprobe),
        "runtime": python_path(dest).is_file(),
        "uv_bundled": uv_path().is_file(),
        "translation_ready": bool(model and model.get("translation_ready")),
        "voices_ready": bool(model and model.get("piper_ready")),
        "whisper_cached": whisper_present,
        "model_details": model,
    }


def pipeline(base: Path | None = None) -> list[list[str]]:
    dest = base or home()
    uv = uv_path()
    src = source_dir()
    if not uv.is_file():
        raise RuntimeError("لم يتم تضمين محرك إعداد Python في برنامج Windows.")
    if not (src / "pyproject.toml").is_file():
        raise RuntimeError("ملفات المحرك البرمجية غير موجودة في حزمة Windows.")
    env = python_path(dest)
    # Separate per-user runtime; never install packages into system Python.
    return [
        [str(uv), "python", "install", "3.11"],
        [str(uv), "venv", "--python", "3.11", str(env.parent.parent)],
        [str(uv), "pip", "install", "--python", str(env), str(src) + "[offline,speech]"],
    ]


def model_command(kind: str, base: Path | None = None) -> list[str]:
    python = python_path(base)
    if not python.is_file():
        raise RuntimeError("محرك Python غير مثبت. اضغط تجهيز المحرك أولًا.")
    if kind not in {"translations", "whisper", "voices"}:
        raise ValueError("Unknown setup stage")
    return [str(python), "-m", "voice_engine.setup_assets", kind]


def download_ffmpeg(log, base: Path | None = None) -> None:
    """Opt-in download; extract ONLY ffmpeg.exe/ffprobe.exe, bounded sizes."""
    dest = base or home()
    destination = binaries(dest)
    destination.mkdir(parents=True, exist_ok=True)
    temporary = dest / "ffmpeg-download.partial"
    if temporary.exists():
        temporary.unlink()
    try:
        log("تنزيل FFmpeg من gyan.dev …")
        request = urllib.request.Request(FFMPEG_URL, headers={"User-Agent": "NEXVARY-Voice/0.5"})
        with urllib.request.urlopen(request, timeout=35) as source, temporary.open("xb") as sink:
            total = 0
            while True:
                chunk = source.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > 220 * 1024 * 1024:
                    raise ValueError("FFmpeg download exceeds safe maximum")
                sink.write(chunk)
                if total % (20 * 1024 * 1024) < len(chunk):
                    log(f"تم تحميل {total // (1024 * 1024)} MB")
        with zipfile.ZipFile(temporary) as archive:
            for filename in ("ffmpeg.exe", "ffprobe.exe"):
                matches = [entry for entry in archive.infolist()
                           if entry.filename.replace("\\", "/").endswith("/bin/" + filename)]
                if len(matches) != 1 or not 0 < matches[0].file_size < 180 * 1024 * 1024:
                    raise ValueError("Archive missing expected FFmpeg binaries")
                out = destination / filename
                stage = destination / (filename + ".partial")
                try:
                    with archive.open(matches[0]) as content, stage.open("wb") as target:
                        shutil.copyfileobj(content, target, length=1024 * 1024)
                    stage.replace(out)
                finally:
                    if stage.exists():
                        stage.unlink()
                log("تم تجهيز " + filename)
    finally:
        if temporary.exists():
            temporary.unlink()


def start_local_engine(base: Path | None = None) -> subprocess.Popen:
    dest = base or home()
    py = python_path(dest)
    if not py.is_file():
        raise RuntimeError("ثبّت المحرك أولًا.")
    dest.mkdir(parents=True, exist_ok=True)
    # Avoid starting another server if port 8000 is occupied.
    import socket
    with socket.socket() as sock:
        if sock.connect_ex(("127.0.0.1", 8000)) == 0:
            raise RuntimeError("المنفذ 8000 مستخدم. أوقف الخدمة الموجودة أو اختر خادمًا آخر.")
    log = (dest / "engine.log").open("ab")
    try:
        process = subprocess.Popen(
            [str(py), "-m", "uvicorn", "voice_engine.api:app",
             "--host", "127.0.0.1", "--port", "8000"],
            cwd=str(dest), env=setup_environment(dest),
            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
            creationflags=NO_WINDOW,
        )
    finally:
        log.close()
    return process
