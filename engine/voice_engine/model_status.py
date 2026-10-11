"""Read-only six-language model readiness report; no downloads."""
from __future__ import annotations
import json
from pathlib import Path

CODES = ("ar", "en", "it", "ru", "es", "bn")

def installed_pairs() -> set[tuple[str, str]]:
    try:
        import argostranslate.package as packages
        return {(p.from_code, p.to_code) for p in packages.get_installed_packages()}
    except Exception:
        return set()

def report(voices_path: Path | None = None) -> dict:
    pairs = installed_pairs()
    voices_path = voices_path or Path("voices.json")
    try:
        voices = json.loads(voices_path.read_text(encoding="utf-8")) if voices_path.is_file() else {}
    except (ValueError, OSError):
        voices = {}
    if not isinstance(voices, dict):
        voices = {}
    states = {}
    def path_available(source, target):
        if source == target: return True
        seen, todo = {source}, [source]
        while todo:
            node = todo.pop()
            for a,b in pairs:
                if a == node and b not in seen:
                    if b == target: return True
                    seen.add(b); todo.append(b)
        return False
    for code in CODES:
        incoming = path_available(code, "en")
        outgoing = path_available("en", code)
        voice = voices.get(code)
        good_voice = isinstance(voice, str) and Path(voice).is_file() and Path(voice + ".json").is_file()
        reason = "ملف الصوت أو ملف الإعداد غير موجود."
        if good_voice:
            try:
                config = json.loads(Path(voice + ".json").read_text(encoding="utf-8"))
                good_voice = Path(voice).stat().st_size > 1024 and isinstance(config.get("audio", {}).get("sample_rate"), int) and bool(config.get("phoneme_id_map"))
                reason = "الملفات سليمة بنيويًا؛ يلزم اختبار توليد صوت." if good_voice else "ملف ONNX أو التكوين ناقص أو غير صالح."
            except (OSError, ValueError, AttributeError):
                good_voice = False; reason = "ملف إعداد الصوت تالف."
        states[code] = {"to_english": incoming, "from_english": outgoing,
                        "piper_voice_ready": good_voice, "voice_reason": reason, "voice_state": "unverified" if good_voice else "repair" if voice else "missing",
                        "translation_state": "unverified" if incoming and outgoing else "missing"}
    return {"languages": states, "readiness_kind": "installed_files_only",
            "translation_pairs": [list(p) for p in sorted(pairs)],
            "translation_ready": all(v["to_english"] and v["from_english"] for v in states.values()),
            "piper_ready": all(v["piper_voice_ready"] for v in states.values())}

def main():
    print(json.dumps(report(), ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
