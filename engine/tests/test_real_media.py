"""True FFmpeg integration without pretending synthetic speech is an AI quality test."""
from __future__ import annotations

import shutil
import subprocess
import wave
from pathlib import Path
import pytest

from voice_engine.speech import Segment, PiperTTS, AudioBackendUnavailable
from voice_engine.dubbing import dub_video, probe_duration


class SyntheticASR:
    def transcribe(self, path, language):
        return [Segment(0.25, 0.85, "مرحبا"), Segment(1.1, 1.7, "أهلا")]


class SyntheticTranslator:
    def translate(self, text, source, target):
        return {"مرحبا": "Hello", "أهلا": "Welcome"}[text]


class SyntheticTTS:
    def synthesize(self, text, language, path):
        # A real PCM WAV file, not a claim of realistic speech.
        with wave.open(str(path), "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(16000)
            out.writeframes(b"\x00\x08" * 4800)


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
                    reason="FFmpeg binaries not installed")
def test_real_ffmpeg_video_and_translated_audio_mux(tmp_path):
    source = tmp_path / "input.mp4"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", "color=c=black:s=320x180:d=3:r=15",
         "-f", "lavfi", "-i", "sine=frequency=400:duration=3",
         "-c:v", "mpeg4", "-c:a", "aac", "-shortest", str(source)],
        check=True, timeout=30
    )
    output = tmp_path / "dubbed.mp4"
    report = dub_video(source, output, "ar", "en", SyntheticASR(),
                       SyntheticTranslator(), SyntheticTTS())
    assert report["segments"] == 2
    assert output.stat().st_size > 1000
    assert abs(probe_duration(output) - 3) < 0.2
    assert output.with_suffix(".srt").exists()
    assert "Welcome" in output.with_suffix(".srt").read_text(encoding="utf-8")


def test_piper_rejects_missing_model_without_fetching(tmp_path):
    with pytest.raises(AudioBackendUnavailable, match="missing"):
        PiperTTS({"en": str(tmp_path / "missing.onnx")}).synthesize(
            "Hello", "en", tmp_path / "output.wav"
        )
