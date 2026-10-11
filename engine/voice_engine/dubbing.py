"""Real recorded-video dubbing: FFmpeg -> Whisper -> Argos -> TTS -> aligned audio -> MP4.

The result is new translated speech (not mere subtitles). Not a human-quality guarantee.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Protocol

from .speech import Segment, WhisperASR, PiperTTS, EdgeTTS, AudioBackendUnavailable, run_checked
from .translator import ArgosTranslator, Translator


class SpeechRecognizer(Protocol):
    def transcribe(self, path: Path, language: str) -> list[Segment]: ...


class SpeechSynthesizer(Protocol):
    def synthesize(self, text: str, language: str, target: Path) -> None: ...


def timecode(seconds: float) -> str:
    millis = round(max(0, seconds) * 1000)
    h, rest = divmod(millis, 3_600_000)
    m, rest = divmod(rest, 60_000)
    s, ms = divmod(rest, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def captions(segments: list[Segment]) -> str:
    return "\n\n".join(
        f"{i}\n{timecode(s.start)} --> {timecode(s.end)}\n{s.text}"
        for i, s in enumerate(segments, 1)
    ) + ("\n" if segments else "")


def validated_segments(segments: list[Segment], duration: float) -> list[Segment]:
    if not (0 < duration <= 1800):
        raise ValueError("Only videos up to 30 minutes are supported")
    result = []
    for s in segments:
        if not s.text.strip():
            continue
        if not (0 <= s.start < s.end <= duration + 0.4):
            raise ValueError("Invalid ASR timestamps")
        result.append(Segment(s.start, min(s.end, duration), s.text.strip()))
    if not result:
        raise ValueError("No spoken words were detected")
    if len(result) > 200:
        raise ValueError("More than 200 speech segments; split the video first")
    return result


def probe_duration(video: Path) -> float:
    try:
        data = subprocess.run([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "json", str(video)
        ], capture_output=True, text=True, check=True, timeout=30)
        duration = float(json.loads(data.stdout)["format"]["duration"])
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired,
            ValueError, KeyError, json.JSONDecodeError) as exc:
        raise AudioBackendUnavailable("Cannot inspect input video with ffprobe") from exc
    return duration


def make_mix_command(clips: list[tuple[float, Path]], duration: float,
                     script: Path, output: Path) -> list[str]:
    """Use a bounded filter script instead of inlining user text in a shell command."""
    if not clips or len(clips) > 200 or duration <= 0:
        raise ValueError("Invalid audio clip layout")
    argv = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
            "-f", "lavfi", "-t", f"{duration:.3f}", "-i",
            "anullsrc=channel_layout=mono:sample_rate=16000"]
    filters = []
    names = ["[0:a]"]
    for i, (start, path) in enumerate(clips, 1):
        if not 0 <= start < duration:
            raise ValueError("Audio clip starts outside video")
        argv.extend(["-i", str(path)])
        # delay in milliseconds, all channels, then normalize to PCM 16 kHz
        delay = round(start * 1000)
        name = f"[v{i}]"
        filters.append(f"[{i}:a]aresample=16000,aformat=sample_fmts=fltp:channel_layouts=mono,"
                       f"adelay={delay}:all=1{name}")
        names.append(name)
    filters.append("".join(names) +
                   f"amix=inputs={len(names)}:duration=first:normalize=0,"
                   "alimiter=limit=0.95[mix]")
    script.write_text(";\n".join(filters), encoding="utf-8")
    argv.extend(["-filter_complex_script", str(script), "-map", "[mix]",
                 "-c:a", "pcm_s16le", str(output)])
    return argv


def dub_video(video: Path, output: Path, source: str, target: str,
              asr: SpeechRecognizer, translator: Translator, tts: SpeechSynthesizer,
              *, runner=run_checked, duration_probe=probe_duration) -> dict:
    """Create translated speech, SRT, and muxed MP4; refuse overwriting any file."""
    video, output = Path(video), Path(output)
    if not video.is_file():
        raise FileNotFoundError(f"Video not found: {video}")
    if video.resolve() == output.resolve() or output.exists():
        raise FileExistsError("Output MP4 exists or would overwrite source")
    subtitle_output = output.with_suffix(".srt")
    if subtitle_output.exists():
        raise FileExistsError("Output SRT already exists")
    if source == target:
        raise ValueError("Use two different languages")
    duration = duration_probe(video)
    if not 0 < duration <= 1800:
        raise ValueError("Only videos up to 30 minutes are supported")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="nexvary-dub-") as folder:
        work = Path(folder)
        raw_audio = work / "original.wav"
        runner(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                "-i", str(video), "-vn", "-ac", "1", "-ar", "16000",
                "-c:a", "pcm_s16le", str(raw_audio)])
        original = validated_segments(asr.transcribe(raw_audio, source), duration)
        translated = []
        clips = []
        for index, seg in enumerate(original):
            translated_text = translator.translate(seg.text, source, target).strip()
            if not translated_text:
                raise AudioBackendUnavailable("Translation engine returned empty text")
            translated.append(Segment(seg.start, seg.end, translated_text))
            clip_path = work / f"voice_{index:04}.wav"
            tts.synthesize(translated_text, target, clip_path)
            if not clip_path.is_file() or clip_path.stat().st_size == 0:
                raise AudioBackendUnavailable("Missing synthesized voice clip")
            clips.append((seg.start, clip_path))
        voice_track = work / "translated.wav"
        runner(make_mix_command(clips, duration, work / "mix.filter", voice_track))
        staged_video = work / "dubbed.mp4"
        runner(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                "-i", str(video), "-i", str(voice_track),
                "-map", "0:v:0", "-map", "1:a:0",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-t",
                f"{duration:.3f}", "-movflags", "+faststart", str(staged_video)])
        if not staged_video.is_file() or staged_video.stat().st_size == 0:
            raise AudioBackendUnavailable("FFmpeg failed to create dubbed MP4")
        staged_srt = work / "dubbed.srt"
        staged_srt.write_text(captions(translated), encoding="utf-8")
        os.replace(staged_video, output)
        os.replace(staged_srt, subtitle_output)
    return {"video": str(output), "subtitles": str(subtitle_output),
            "segments": len(translated), "source": source, "target": target,
            "duration_seconds": duration}


def main() -> None:
    parser = argparse.ArgumentParser(description="Create an AI translated speech track and MP4")
    parser.add_argument("video", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--source", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--whisper-model", default="small")
    parser.add_argument("--allow-model-download", action="store_true")
    parser.add_argument("--tts", choices=["piper", "edge"], default="piper")
    parser.add_argument("--piper-model", type=Path)
    parser.add_argument("--voice")
    parser.add_argument("--allow-cloud-tts", action="store_true")
    args = parser.parse_args()
    if args.tts == "edge" and not args.allow_cloud_tts:
        parser.error("--tts edge requires --allow-cloud-tts: voice text is sent to an online service")
    if args.tts == "piper" and not args.piper_model:
        parser.error("Offline Piper requires --piper-model /path/to/voice.onnx")
    asr = WhisperASR(args.whisper_model, allow_download=args.allow_model_download)
    tts = (EdgeTTS(allow_cloud=True, voice=args.voice) if args.tts == "edge"
           else PiperTTS({args.target: str(args.piper_model)}))
    try:
        report = dub_video(args.video, args.output, args.source, args.target,
                           asr, ArgosTranslator(), tts)
    except (AudioBackendUnavailable, ValueError, FileExistsError) as exc:
        parser.exit(1, f"Dubbing error: {exc}\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
