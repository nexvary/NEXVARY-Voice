"""Read-only six-language model readiness report; no downloads."""
from __future__ import annotations
import json
from pathlib import Path

CODES = ("ar", "en", "it", "ru", "es", "bn")

def installed_pairs() -> set[tuple[str, str]]:
    try:
        import argostranslate.package as packages
        return {(p.from_code, p.to_code) for p in packages.get_installed_packages()}
    except (ImportError, AttributeError):
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
    for code in CODES:
        incoming = code == "en" or (code, "en") in pairs
        outgoing = code == "en" or ("en", code) in pairs
        voice = voices.get(code)
        good_voice = isinstance(voice, str) and Path(voice).is_file() and Path(voice + ".json").is_file()
        states[code] = {"to_english": incoming, "from_english": outgoing,
                        "piper_voice_ready": good_voice}
    return {"languages": states,
            "translation_ready": all(v["to_english"] and v["from_english"] for v in states.values()),
            "piper_ready": all(v["piper_voice_ready"] for v in states.values())}

def main():
    print(json.dumps(report(), ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
