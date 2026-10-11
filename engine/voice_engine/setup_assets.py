"""Opt-in assets installation for the standalone Windows GUI managed worker.

All network sources are hardcoded HTTPS. Voice files are validated against the
upstream voices.json size/digest and kept in per-user application data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from .downloads import fetch_verified

CODES = ("ar", "en", "it", "ru", "es", "bn")
VOICES = {
    "ar": "ar_JO-kareem-medium",
    "en": "en_US-lessac-medium",
    "it": "it_IT-paola-medium",
    "ru": "ru_RU-irina-medium",
    "es": "es_ES-davefx-medium",
    "bn": "bn_BD-google-medium",
}
REGISTRY = "https://huggingface.co/rhasspy/piper-voices/resolve/main"


def say(message: str):
    print(message, flush=True)


def install_translations() -> None:
    import argostranslate.package as package
    installed = {(p.from_code, p.to_code) for p in package.get_installed_packages()}
    required = [(code, "en") for code in CODES if code != "en"]
    required += [("en", code) for code in CODES if code != "en"]
    missing = [(source, target) for source, target in required if (source, target) not in installed]
    if not missing:
        say("تم التحقق من نماذج الترجمة العشرة المثبتة بالفعل.")
        return
    say("قراءة فهرس حزم Argos Translate …")
    package.update_package_index()
    available = {(entry.from_code, entry.to_code): entry for entry in package.get_available_packages()}
    unavailable = [f"{source}->{target}" for source, target in missing
                   if (source, target) not in available]
    if unavailable:
        raise RuntimeError("نماذج غير متاحة في الفهرس الحالي: " + ", ".join(unavailable))
    for index, (source, target) in enumerate(missing, 1):
        say(f"[{index}/{len(missing)}] تنزيل ترجمة {source} إلى {target}")
        item = available[(source, target)]
        package.install_from_path(item.download())
    say("اكتمل تنزيل جميع اتجاهات الترجمة المطلوبة.")


def install_whisper() -> None:
    from faster_whisper import WhisperModel
    model = os.getenv("NEXVARY_WHISPER_MODEL", "base")
    say(f"تهيئة Whisper {model} متعدد اللغات للمعالج CPU. قد يستغرق التنزيل بعض الوقت.")
    WhisperModel(os.getenv("NEXVARY_WHISPER_MODEL", "base"), device="cpu", compute_type="int8", local_files_only=False, cpu_threads=max(1, min(4, (os.cpu_count() or 2)//2)))
    say("اكتمل تحميل واختبار تحميل Whisper " + model)


def model_entries(metadata: dict, name: str) -> list[tuple[str, dict]]:
    entry = metadata.get(name)
    if not isinstance(entry, dict) or not isinstance(entry.get("files"), dict):
        raise RuntimeError("بيانات صوت Piper المطلوبة غير موجودة في فهرس النموذج.")
    found = [(rel, val) for rel, val in entry["files"].items()
             if isinstance(rel, str) and isinstance(val, dict)
             and (rel.endswith(".onnx") or rel.endswith(".onnx.json") or rel.endswith("/MODEL_CARD"))]
    if len(found) != 3:
        raise RuntimeError("لا يتضمن النموذج الملفات الثلاثة المطلوبة: " + name)
    return found


def verified_file(path: Path, record: dict) -> bool:
    if not path.is_file():
        return False
    expected_size = record.get("size_bytes")
    expected_md5 = record.get("md5_digest")
    if not isinstance(expected_size, int) or not 0 < expected_size <= 180 * 1024 * 1024:
        raise RuntimeError("حجم ملف النموذج غير موثوق.")
    if not isinstance(expected_md5, str) or len(expected_md5) != 32:
        raise RuntimeError("بيانات التحقق من النموذج ناقصة.")
    if path.stat().st_size != expected_size:
        return False
    digest = hashlib.md5()
    with path.open("rb") as reader:
        for chunk in iter(lambda: reader.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().lower() == expected_md5.lower()


def download_blob(relative: str, record: dict, path: Path) -> None:
    if not relative or relative.startswith(("/", "\\")) or ".." in Path(relative.replace("\\", "/")).parts:
        raise RuntimeError("مسار غير صالح في فهرس نماذج Piper")
    def progress(done, total):
        print("PROGRESS:" + json.dumps({"component": path.name, "bytes": done, "total": total}), flush=True)
    fetch_verified(REGISTRY + "/" + urllib.parse.quote(relative, safe="/"), path,
                   expected_digest=record["md5_digest"], algorithm="md5",
                   expected_size=record["size_bytes"], maximum=180 * 1024 * 1024,
                   progress=progress)


def install_voices() -> None:
    root = Path.cwd()
    voices_dir = root / "models" / "voices"
    voices_dir.mkdir(parents=True, exist_ok=True)
    say("قراءة فهرس أصوات Piper الرسمي والتحقق من الملفات …")
    req = urllib.request.Request(REGISTRY + "/voices.json",
                                 headers={"User-Agent": "NEXVARY-Voice/0.5"})
    with urllib.request.urlopen(req, timeout=40) as response:
        raw = response.read(5 * 1024 * 1024 + 1)
    if len(raw) > 5 * 1024 * 1024:
        raise RuntimeError("فهرس الأصوات أكبر من الحد المسموح.")
    metadata = json.loads(raw.decode("utf-8"))
    try:
        mapping = json.loads((root / "voices.json").read_text(encoding="utf-8"))
    except (ValueError, OSError):
        mapping = {}
    if not isinstance(mapping, dict): mapping = {}
    failures = []
    for index, (lang, model_id) in enumerate(VOICES.items(), 1):
        say(f"[{index}/{len(VOICES)}] فحص صوت {lang} ({model_id})")
        try:
            entries = model_entries(metadata, model_id)
        except RuntimeError as exc:
            failures.append(lang + ": " + str(exc))
            say("FAILED: " + failures[-1])
            continue
        for relative, record in entries:
            filename = Path(relative).name
            if filename == "MODEL_CARD":
                filename = "MODEL_CARD-" + lang + ".txt"
            target = voices_dir / lang / filename
            if not verified_file(target, record):
                say("تنزيل " + filename)
                download_blob(relative, record, target)
        voice = voices_dir / lang / (model_id + ".onnx")
        config = Path(str(voice) + ".json")
        if not voice.is_file() or not config.is_file():
            raise RuntimeError("الصوت المثبت غير مكتمل: " + lang)
        json.loads(config.read_text(encoding="utf-8"))
        mapping[lang] = str(voice.resolve())
        stage = root / "voices.json.partial"
        stage.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(stage, root / "voices.json")
    dest = root / "voices.json"
    stage = dest.with_name("voices.json.partial")
    stage.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(stage, dest)
    if failures: raise RuntimeError("لم تكتمل الأصوات: " + "; ".join(failures))
    say("اكتمل تنزيل الأصوات؛ جاري التحقق الوظيفي من التوليد.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("translations", "whisper", "voices"))
    args = parser.parse_args()
    try:
        {"translations": install_translations, "whisper": install_whisper,
         "voices": install_voices}[args.stage]()
    except Exception as exc:
        say(f"FAILED: {type(exc).__name__}: {str(exc)[:250]}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
