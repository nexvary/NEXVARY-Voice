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
import re
import stat
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path
from .diagnostics import system_probes, inspect_binary
from .downloads import fetch_verified, digest_file
from .asset_inventory import voice_map, functional_report

LANG_CODES = ("ar", "en", "it", "ru", "es", "bn")
RUNTIME_VERSIONS = {"faster-whisper":"1.2.1", "argostranslate":"1.11.0", "piper-tts":"1.8.0", "nexvary-voice-engine":"0.6.2"}
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
    # Python aliases/state can otherwise land in roaming AppData and encounter
    # cloud-provider reparse points even with UV_PYTHON_INSTALL_DIR set.
    env["UV_DATA_DIR"] = str(dest / "uv-data")
    env["UV_PYTHON_BIN_DIR"] = str(dest / "python-links")
    env["UV_LINK_MODE"] = "copy"
    env["UV_PYTHON_INSTALL_DIR"] = str(dest / "pythons")
    env["UV_NO_PROGRESS"] = "1"
    env["ARGOS_PACKAGES_DIR"] = str(dest / "argos")
    env["HF_HOME"] = str(dest / "huggingface")
    env["NEXVARY_WHISPER_MODEL"] = load_preferences(dest).get("whisper_model", "base")
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env["UV_PYTHON_INSTALL_BIN"] = "0"
    env["UV_PYTHON_INSTALL_REGISTRY"] = "0"
    env["OMP_NUM_THREADS"] = str(max(1, min(4, (os.cpu_count() or 2) // 2)))
    env["ARGOS_DEVICE_TYPE"] = "cpu"
    env["NEXVARY_NATIVE_ARGOS"] = "1"
    env["NEXVARY_PIPER_API"] = "1"
    env["XDG_DATA_HOME"] = str(dest/'data')
    env["XDG_CONFIG_HOME"] = str(dest/'config')
    env["XDG_CACHE_HOME"] = str(dest/'cache')
    env["NEXVARY_ASR_DEVICE"] = "cpu"
    env["PATH"] = str(binaries(dest)) + os.pathsep + str(python_path(dest).parent) + os.pathsep + env.get("PATH", "")
    pair = ffmpeg_pair(dest)
    for executable in pair:
        if executable: env['PATH'] = str(Path(executable).parent) + os.pathsep + env['PATH']
    voices = voice_map(dest)
    if voices: env['NEXVARY_PIPER_VOICES'] = json.dumps(voices)
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
    ffmpeg, ffprobe = shutil.which('ffmpeg'), shutil.which('ffprobe')
    if ffmpeg and ffprobe: return ffmpeg, ffprobe
    roots = [resources()/'bin', Path('C:/ffmpeg/bin'), Path('C:/Program Files/ffmpeg/bin')]
    for root in roots:
        a,p = root/'ffmpeg.exe',root/'ffprobe.exe'
        if a.is_file() and p.is_file(): return str(a),str(p)
    return ffmpeg,ffprobe


def existing_system_python() -> Path | None:
    """Detect compatible Python 3.11 already on Windows without modifying it."""
    candidates = []
    if shutil.which("py"):
        candidates.append(["py", "-3.11"])
    if shutil.which("python"):
        candidates.append(["python"])
    for command in candidates:
        try:
            result = subprocess.run(
                command + ["-c", "import sys; print(sys.version_info[:2] == (3, 11)); print(sys.executable)"],
                capture_output=True, text=True, encoding="utf-8", timeout=8,
                creationflags=NO_WINDOW
            )
            lines = result.stdout.strip().splitlines()
            if result.returncode == 0 and len(lines) >= 2 and lines[0].strip() == "True":
                exe = Path(lines[-1].strip())
                if exe.is_file():
                    return exe
        except (OSError, subprocess.SubprocessError):
            continue
    return None


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
        audio_reason = "تم تعداد أجهزة الصوت؛ يلزم اختبار التسجيل والاستماع."
        microphone = any(d["max_input_channels"] > 0 for d in devices)
        speakers = any(d["max_output_channels"] > 0 for d in devices)
    except Exception:
        audio_reason = "تعذر تعداد أجهزة الصوت أو لم تُثبّت مكونات الصوت."
        microphone = speakers = False
    model = model_report(dest)
    whisper_dir = dest / "huggingface" / "hub" / ("models--Systran--faster-whisper-" + load_preferences(dest).get("whisper_model", "base"))
    whisper = whisper_dir / "snapshots"
    whisper_present = whisper.is_dir() and any(
        (child / "model.bin").is_file() for child in whisper.iterdir() if child.is_dir()
    )
    probes = system_probes(dest, resources())
    ffmpeg_status, ffprobe_status = inspect_binary(ffmpeg), inspect_binary(ffprobe)
    runtime_details = runtime_report(dest)
    return {
        "probes": probes, "ffmpeg_status": ffmpeg_status, "ffprobe_status": ffprobe_status,
        "runtime_details": runtime_details,
        "recommended_model": "tiny" if (memory_gb() or 4) < 6 or (os.cpu_count() or 2) < 4 else "base",
        "selected_model": load_preferences(dest).get("whisper_model", "base"),
        "os": platform.platform(), "cpu": platform.processor() or platform.machine(),
        "cores": os.cpu_count(), "ram_gb": memory_gb(), "disk_free_gb": free,
        "audio_reason":audio_reason, "microphone": microphone, "speakers": speakers,
        "ffmpeg": ffmpeg_status["state"] == "ready", "ffprobe": ffprobe_status["state"] == "ready",
        "runtime": python_path(dest).is_file(),
        "system_python": str(existing_system_python() or ""),
        "uv_bundled": uv_path().is_file(),
        "translation_ready": bool(model and model.get("translation_ready")),
        "voices_ready": bool(model and model.get("piper_ready")),
        "whisper_cached": whisper_present,
        "model_details": model, "functional_tests": functional_report(dest),
        "discovered_voices":voice_map(dest),
    }


class SetupCommandError(RuntimeError):
    """Bounded subprocess evidence used for narrowly scoped recovery."""
    def __init__(self, label: str, code: int, output: str):
        super().__init__("فشل " + label + f" (code {code}).")
        self.code = code
        self.output = output[-12000:]


def managed_python(base: Path | None = None) -> Path | None:
    """Probe full patch directories only; never traverse uv minor-version links.

    A failed alias operation can leave a complete, usable interpreter behind.
    Reject links escaping our store and test Python, architecture and stdlib
    before using an existing extraction. No writes or downloads here.
    """
    root = (base or home()) / "pythons"
    try:
        children = sorted(root.iterdir(), reverse=True)[:64]
    except OSError:
        return None
    for child in children:
        if not re.fullmatch(r"cpython-3\.11\.\d+-windows-x86_64-none", child.name):
            continue
        try:
            attributes = getattr(child.lstat(), "st_file_attributes", 0)
            if child.is_symlink() or attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 1024):
                continue
            executable = child / "python.exe"
            if not executable.is_file() or not executable.resolve().is_relative_to(root.resolve()):
                continue
            result = subprocess.run(
                [str(executable), "-I", "-c",
                 "import sys,struct,ssl,venv; print(sys.version_info[:2]==(3,11) and struct.calcsize('P')==8)"],
                capture_output=True, text=True, encoding="utf-8", timeout=8,
                creationflags=NO_WINDOW)
            if result.returncode == 0 and result.stdout.strip() == "True":
                return executable
        except (OSError, subprocess.SubprocessError):
            continue
    return None


def prepare_python(execute, log, *, base: Path | None = None, cancelled=None) -> Path | None:
    """Recover a downloaded interpreter without accepting a failed installation.

    Windows 448 during uv's optional alias creation is recoverable only if the
    real downloaded executable independently passes our functional probe.
    Connection, extraction and cancellation failures remain failures.
    """
    dest = base or home()
    if cancelled and cancelled():
        raise RuntimeError("تم إيقاف الإعداد.")
    if python_path(dest).is_file():
        return None
    interpreter = managed_python(dest) or existing_system_python()
    if interpreter:
        log("تم اختبار Python الموجود؛ لا حاجة لإعادة تنزيله.")
        return interpreter
    if not uv_path().is_file():
        raise RuntimeError("لم يتم تضمين محرك إعداد Python في برنامج Windows.")
    try:
        execute([str(uv_path()), "python", "install", "3.11"], "تنزيل واختبار Python مستقل")
    except SetupCommandError as exc:
        if cancelled and cancelled():
            raise RuntimeError("تم إيقاف الإعداد.") from exc
        evidence = exc.output.lower()
        if "minor version link directory" not in evidence or "os error 448" not in evidence:
            raise
        interpreter = managed_python(dest)
        if not interpreter:
            raise RuntimeError("رفض Windows الرابط الداخلي (448)، ولم يجتز Python المنزّل اختبار التشغيل؛ لم يكتمل الإعداد.") from exc
        log("رفض Windows رابط Python الداخلي (448). اجتاز الملف المنزّل اختبار التشغيل؛ نكمل باستخدامه مباشرة دون إنشاء ذلك الرابط.")
        return interpreter
    if cancelled and cancelled():
        raise RuntimeError("تم إيقاف الإعداد.")
    interpreter = managed_python(dest)
    if not interpreter:
        raise RuntimeError("لم يجتز Python المنزّل اختبار التشغيل والتوافق.")
    return interpreter


def pipeline(base: Path | None = None, *, interpreter: Path | None = None) -> list[list[str]]:
    dest = base or home()
    uv = uv_path()
    src = source_dir()
    if not uv.is_file():
        raise RuntimeError("لم يتم تضمين محرك إعداد Python في برنامج Windows.")
    if not (src / "pyproject.toml").is_file():
        raise RuntimeError("ملفات المحرك البرمجية غير موجودة في حزمة Windows.")
    env = python_path(dest)
    commands = []
    if not env.is_file():
        interpreter = interpreter or managed_python(dest) or existing_system_python()
        if not interpreter:
            raise RuntimeError("يجب تجهيز Python واختباره قبل إنشاء البيئة المستقلة.")
        # stdlib venv with copies bypasses uv's minor-version junction machinery.
        # pip need not be bootstrapped: bundled uv installs into the private venv.
        commands.append([str(interpreter), "-I", "-m", "venv", "--copies", "--without-pip", str(env.parent.parent)])
    commands.append([str(uv), "pip", "install", "--python", str(env), str(src) + "[offline,speech]"])
    return commands


def model_command(kind: str, base: Path | None = None) -> list[str]:
    python = python_path(base)
    if not python.is_file():
        raise RuntimeError("محرك Python غير مثبت. اضغط تجهيز المحرك أولًا.")
    if kind not in {"translations", "whisper", "voices"}:
        raise ValueError("Unknown setup stage")
    return [str(python), "-m", "voice_engine.setup_assets", kind]


def download_ffmpeg(log, base: Path | None = None, *, progress=None, cancelled=None) -> None:
    """Validate upstream SHA-256 before extracting or running any binary."""
    dest = base or home()
    destination = binaries(dest)
    destination.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(FFMPEG_URL + ".sha256", headers={"User-Agent": "NEXVARY-Voice/0.5.1"})
    with urllib.request.urlopen(request, timeout=20) as response:
        if not response.geturl().startswith("https://"):
            raise ValueError("Insecure checksum source")
        checksum = response.read(4096).decode("ascii").strip().split()[0]
    temporary = dest / "ffmpeg-download.zip"
    log("تنزيل FFmpeg والتحقق من SHA-256 المنشور من المصدر …")
    fetch_verified(FFMPEG_URL, temporary, expected_digest=checksum,
                   progress=progress, cancelled=cancelled)
    # Extract both to staging and test them before changing installed binaries.
    with zipfile.ZipFile(temporary) as archive:
        stages = []
        try:
            for filename in ("ffmpeg.exe", "ffprobe.exe"):
                if cancelled and cancelled():
                    raise RuntimeError("تم إيقاف الإعداد.")
                matches = [entry for entry in archive.infolist()
                           if entry.filename.replace("\\", "/").endswith("/bin/" + filename)]
                if len(matches) != 1 or not 0 < matches[0].file_size < 180 * 1024 * 1024:
                    raise ValueError("Archive missing expected FFmpeg binaries")
                stage = destination / ("staged-" + filename)
                stages.append((stage, destination / filename))
                with archive.open(matches[0]) as content, stage.open("wb") as target:
                    shutil.copyfileobj(content, target, length=1024 * 1024)
                if inspect_binary(str(stage))["state"] != "ready":
                    raise RuntimeError("فشل اختبار تشغيل " + filename)
            for stage, output in stages:
                stage.replace(output)
                log("تم التحقق وتجهيز " + output.name)
        finally:
            for stage, _ in stages: stage.unlink(missing_ok=True)
    temporary.unlink(missing_ok=True)


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


def load_preferences(base: Path | None = None) -> dict:
    try:
        value = json.loads(((base or home()) / "preferences.json").read_text(encoding="utf-8"))
        model = value.get("whisper_model", "base")
        return {"whisper_model": model if model in WHISPER_SIZE else "base"}
    except (ValueError, OSError, AttributeError):
        return {"whisper_model": "base"}


def save_preferences(model: str, base: Path | None = None):
    if model not in WHISPER_SIZE: raise ValueError("Unsupported model")
    dest = base or home()
    dest.mkdir(parents=True, exist_ok=True)
    stage = dest / "preferences.json.partial"
    stage.write_text(json.dumps({"whisper_model": model}), encoding="utf-8")
    stage.replace(dest / "preferences.json")


def runtime_report(base: Path | None = None) -> dict:
    dest = base or home()
    py = python_path(dest)
    if not py.is_file(): return {"state": "missing", "reason": "لا يوجد Runtime مستقل بعد."}
    script = """import sys,json,importlib.metadata as m,importlib
names={'faster-whisper':'faster_whisper','argostranslate':'argostranslate','piper-tts':'piper','nexvary-voice-engine':'voice_engine.api'}
result={'version':list(sys.version_info[:3]),'modules':{}}
for name,module in names.items():
 try:
  importlib.import_module(module)
  result['modules'][name]={'version':m.version(name),'state':'ready'}
 except Exception as exc: result['modules'][name]={'state':'repair','reason':type(exc).__name__}
print(json.dumps(result))
"""
    try:
        result = subprocess.run([str(py), "-c", script], cwd=dest, env=setup_environment(dest),
                                capture_output=True, text=True, encoding="utf-8", timeout=45,
                                creationflags=NO_WINDOW)
        data = json.loads(result.stdout)
        okay = result.returncode == 0 and data["version"][:2] == [3, 11]
        okay = okay and all(v["state"] == "ready" for v in data["modules"].values())
        mismatched = [name for name,version in RUNTIME_VERSIONS.items() if data['modules'].get(name,{}).get('version') != version]
        okay = okay and not mismatched
        data['incompatible_components'] = mismatched
        data.update(state="ready" if okay else "incompatible" if mismatched else "repair", reason=("تم استيراد المكونات والتحقق من Python 3.11." if okay else "تحتاج البيئة تحديثًا أو إصلاحًا: " + ", ".join(mismatched) if mismatched else "بيئة المعالجة ناقصة أو غير صالحة."))
        return data
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        return {"state": "failed", "reason": "تعذر اختبار Runtime؛ قد تكون البيئة ناقصة أو تالفة."}


class EngineManager:
    """Only terminate the process started by this application instance."""
    def __init__(self):
        self.process = None
        self.last_state = 'stopped'

    def health(self):
        try:
            with urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2) as response:
                data = json.loads(response.read(4096))
            return data.get('component') == 'voice-engine' and data.get('status') == 'ok'
        except (OSError, ValueError): return False

    def start(self):
        import time
        if self.process is not None and self.process.poll() is None:
            if self.health(): return 'المحرك المحلي يعمل بالفعل.'
            raise RuntimeError('المحرك المملوك للتطبيق ما زال يبدأ أو لا يستجيب؛ استخدم إعادة التشغيل.')
        if self.health():
            self.last_state = 'external'
            return 'محرك NEXVARY محلي موجود بالفعل. يمكن الاتصال به؛ إيقافه يتم من البرنامج الذي بدأه.'
        self.process = start_local_engine()
        self.last_state = 'starting'
        for _ in range(60):
            if self.process.poll() is not None:
                self.last_state = 'failed'
                raise RuntimeError('توقف المحرك أثناء الإقلاع. راجع سجل المحرك من مركز التشخيص.')
            if self.health():
                self.last_state = 'running'
                return 'المحرك جاهز ويستجيب على 127.0.0.1:8000.'
            time.sleep(0.25)
        self.stop()
        raise RuntimeError('لم يستجب المحرك خلال مهلة الإقلاع.')

    def stop(self):
        if self.process is None:
            return 'لا توجد عملية محرك مملوكة للتطبيق لإيقافها.'
        if self.process.poll() is None:
            self.process.terminate()
            try: self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill(); self.process.wait(timeout=5)
        self.process = None
        self.last_state = 'stopped'
        return 'تم إيقاف المحرك المحلي الذي بدأه التطبيق.'

    def restart(self):
        self.stop()
        return self.start()

    def metrics(self):
        if self.process is None or self.process.poll() is not None:
            return {'state':self.last_state, 'cpu_percent':None, 'ram_mb':None}
        try:
            import psutil
            proc = psutil.Process(self.process.pid)
            if getattr(self, '_metric_pid', None) != proc.pid:
                self._metric_proc = proc; self._metric_pid = proc.pid
            return {'state':self.last_state, 'cpu_percent':self._metric_proc.cpu_percent(),
                    'ram_mb':round(proc.memory_info().rss/1024**2,1)}
        except Exception:
            return {'state':self.last_state,'cpu_percent':None,'ram_mb':None}


def stop_owned_process(process):
    """Stop only the installer Popen and its children, without touching services."""
    if process is None or process.poll() is not None: return
    try:
        import psutil
        parent = psutil.Process(process.pid)
        children = parent.children(recursive=True)
        for child in reversed(children):
            try: child.terminate()
            except psutil.Error: pass
    except (ImportError, OSError): pass
    except Exception: pass
    try: process.terminate()
    except OSError: pass
