"""Mux a user-supplied synthesized voice track with original video using FFmpeg."""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


def build_command(video: Path, audio: Path, output: Path) -> list[str]:
    if any(not x.is_file() for x in (video, audio)):
        raise FileNotFoundError("Both source video and translated audio must exist")
    if output.resolve() in {video.resolve(), audio.resolve()}:
        raise ValueError("Output must not overwrite an input")
    return [
        "ffmpeg", "-hide_banner", "-nostdin", "-y",
        "-i", str(video), "-i", str(audio),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy", "-c:a", "aac", "-shortest",
        str(output),
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Mux existing dubbed audio into an MP4 (no speech synthesis)")
    parser.add_argument("video", type=Path)
    parser.add_argument("audio", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    subprocess.run(build_command(args.video, args.audio, args.output), check=True)


if __name__ == "__main__":
    main()
