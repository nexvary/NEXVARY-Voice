"""Optional, explicit-install audio backends. No models are silently downloaded."""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from functools import lru_cache


@dataclass(frozen=True)
class Segment:
    start: float
    end: float
    text: str


class AudioBackendUnavailable(RuntimeError):
    pass


class WhisperASR:
    """ASR with optional locally cached model; callers opt in to downloads."""

    def __init__(self, model: str = "small", *, allow_download: bool = False,
                 device: str = "cpu"):
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise AudioBackendUnavailable("Install engine extra: pip install -e '.[speech]'") from exc
        try:
            self.model = WhisperModel(model, device=device,
                                      compute_type="int8" if device == "cpu" else "auto",
                                      local_files_only=not allow_download,
                                      cpu_threads=max(1, min(4, (os.cpu_count() or 2)//2)), num_workers=1)
        except Exception as exc:
            raise AudioBackendUnavailable(
                "Whisper model is unavailable locally. Use --allow-model-download or install it first."
            ) from exc

    def transcribe(self, path: Path, language: str) -> list[Segment]:
        segments, _ = self.model.transcribe(str(path), language=language,
                                            task="transcribe", beam_size=5, vad_filter=True)
        return [Segment(max(0.0, float(s.start)), float(s.end), s.text.strip())
                for s in segments if s.text.strip()]


def run_checked(argv: list[str], *, input_text: str | None = None,
                timeout: int = 180) -> None:
    """Execute binary with argument list, no shell, and bounded time."""
    try:
        subprocess.run(argv, check=True, input=input_text, text=True,
                       capture_output=True, encoding="utf-8", errors="replace", timeout=timeout,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except FileNotFoundError as exc:
        raise AudioBackendUnavailable(f"Executable not installed: {argv[0]}") from exc
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        detail = str(getattr(exc, "stderr", "") or "")[-1200:]
        raise AudioBackendUnavailable(f"Audio processing failed: {argv[0]}: {detail}") from exc


class PiperTTS:
    """Offline TTS with explicit voice-model mapping; model paths must already exist."""

    def __init__(self, voices: dict[str, str] | None = None):
        if voices is None:
            raw = os.getenv("NEXVARY_PIPER_VOICES", "{}")
            try:
                voices = json.loads(raw)
            except (TypeError, json.JSONDecodeError) as exc:
                raise AudioBackendUnavailable("NEXVARY_PIPER_VOICES must be a JSON object") from exc
        if not isinstance(voices, dict):
            raise AudioBackendUnavailable("NEXVARY_PIPER_VOICES must be a JSON object")
        self.voices = voices

    def synthesize(self, text: str, language: str, target: Path) -> None:
        model = self.voices.get(language)
        if not isinstance(model, str) or not Path(model).is_file():
            raise AudioBackendUnavailable(
                f"Offline Piper voice for '{language}' missing. Configure NEXVARY_PIPER_VOICES."
            )
        run_checked(["piper", "--model", model, "--output_file", str(target)],
                    input_text=text + "\n", timeout=120)
        if not target.is_file() or target.stat().st_size < 44:
            raise AudioBackendUnavailable("Piper did not produce a WAV audio file")


class EdgeTTS:
    """Online TTS. Use only following explicit user permission for cloud processing."""
    DEFAULT_VOICES = {"ar": "ar-EG-SalmaNeural", "en": "en-US-JennyNeural",
                      "hi": "hi-IN-SwaraNeural", "tr": "tr-TR-EmelNeural",
                      "fr": "fr-FR-DeniseNeural", "de": "de-DE-KatjaNeural",
                      "es": "es-ES-ElviraNeural", "it": "it-IT-ElsaNeural",
                      "ru": "ru-RU-SvetlanaNeural", "bn": "bn-BD-NabanitaNeural"}

    def __init__(self, allow_cloud: bool = False, voice: str | None = None):
        if not allow_cloud:
            raise AudioBackendUnavailable("Cloud TTS requires explicit --allow-cloud-tts")
        self.voice = voice

    def synthesize(self, text: str, language: str, target: Path) -> None:
        try:
            import edge_tts
        except ImportError as exc:
            raise AudioBackendUnavailable("Install engine extra: pip install -e '.[cloud]'") from exc
        voice = self.voice or self.DEFAULT_VOICES.get(language)
        if voice is None:
            raise AudioBackendUnavailable(f"No default TTS voice for {language}")
        try:
            asyncio.run(edge_tts.Communicate(text=text, voice=voice).save(str(target)))
        except Exception as exc:
            raise AudioBackendUnavailable("Cloud TTS unavailable; check connectivity and provider") from exc
        if not target.is_file() or target.stat().st_size == 0:
            raise AudioBackendUnavailable("Cloud TTS produced no audio")


@lru_cache(maxsize=1)
def cached_asr(model: str, device: str = "cpu") -> WhisperASR:
    return WhisperASR(model, allow_download=False, device=device)
