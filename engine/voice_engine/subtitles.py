"""Translate standard SRT subtitles, preserving timecodes and cue layout."""
from __future__ import annotations

import argparse
import re
from pathlib import Path

from .translator import ArgosTranslator, Translator

TIMECODE = re.compile(r"^\d{2}:\d{2}:\d{2},\d{3}\s+-->\s+\d{2}:\d{2}:\d{2},\d{3}(?:\s+.*)?$")


def translate_srt(content: str, source: str, target: str, translator: Translator) -> str:
    blocks = re.split(r"\n\s*\n", content.strip().replace("\r\n", "\n"))
    output = []
    for block in blocks:
        lines = block.splitlines()
        time_index = next((i for i, line in enumerate(lines) if TIMECODE.match(line)), None)
        if time_index is None or time_index == len(lines) - 1:
            raise ValueError("Malformed SRT cue: missing timecode or text")
        text = "\n".join(lines[time_index + 1:])
        translated = translator.translate(text, source, target)
        output.append("\n".join(lines[:time_index + 1] + [translated]))
    return "\n\n".join(output) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Translate captions with installed Argos models")
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--source", required=True)
    parser.add_argument("--target", required=True)
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        parser.error("Output must differ from input")
    args.output.write_text(
        translate_srt(args.input.read_text(encoding="utf-8-sig"), args.source, args.target, ArgosTranslator()),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
