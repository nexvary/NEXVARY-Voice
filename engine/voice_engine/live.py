"""Bounded real-time speech-turn pipeline: PCM16 microphone -> ASR -> MT -> Piper TTS -> PCM16.

Not zero-delay simultaneous interpretation. Processing uses 3.2-second chunks with additional
ASR/MT/TTS latency; 16 kHz signed little-endian mono. No transcript persistence.
"""
from __future__ import annotations

import math
import time
import os
import tempfile
import wave
from functools import lru_cache
from pathlib import Path

from .speech import WhisperASR, cached_asr, PiperTTS, AudioBackendUnavailable
from .translator import ArgosTranslator, Translator, TranslationUnavailable

SAMPLE_RATE = 16000
BYTES_PER_SAMPLE = 2
CHUNK_BYTES = 102400  # 3.2 seconds
MAX_FRAME_BYTES = 32000
MIN_CHUNK_BYTES = 16000  # 0.5s flush


def pcm_rms(pcm: bytes) -> float:
    """RMS without audioop (removed in Python 3.13), bounded by max chunk size."""
    if len(pcm) % 2:
        raise ValueError("Malformed PCM sample length")
    if not pcm:
        return 0.0
    import struct
    total = sum(sample * sample for (sample,) in struct.iter_unpack("<h", pcm))
    return math.sqrt(total / (len(pcm) // 2))


def wav_to_pcm(path: Path) -> bytes:
    """Resample inside the already installed PyAV runtime; no child process."""
    import av
    resampler=av.AudioResampler(format='s16',layout='mono',rate=SAMPLE_RATE)
    output=bytearray()
    with av.open(str(path)) as audio:
        for frame in audio.decode(audio=0):
            for converted in resampler.resample(frame):
                output.extend(converted.to_ndarray().astype('<i2',copy=False).tobytes())
                if len(output)>16*1024*1024: raise AudioBackendUnavailable('Synthesized audio exceeds live reply limit')
        for converted in resampler.resample(None):
            output.extend(converted.to_ndarray().astype('<i2',copy=False).tobytes())
    if not output: raise AudioBackendUnavailable('Empty synthesized PCM')
    return bytes(output)


class LiveAudioProcessor:
    def __init__(self, recognizer, translator: Translator, synthesizer):
        self.recognizer = recognizer
        self.translator = translator
        self.synthesizer = synthesizer

    def process(self, pcm: bytes, source: str, target: str):
        """Returns (metadata, translated PCM) or None for quiet input."""
        started = time.monotonic()
        if len(pcm) < MIN_CHUNK_BYTES or len(pcm) > CHUNK_BYTES:
            raise ValueError("Chunk exceeds permitted audio size")
        if pcm_rms(pcm) < 170:
            return None
        with tempfile.TemporaryDirectory(prefix="nexvary-live-") as temporary:
            folder = Path(temporary)
            original = folder / "speech.wav"
            with wave.open(str(original), "wb") as audio:
                audio.setnchannels(1)
                audio.setsampwidth(BYTES_PER_SAMPLE)
                audio.setframerate(SAMPLE_RATE)
                audio.writeframes(pcm)
            stage=time.monotonic()
            segments = self.recognizer.transcribe(original, source)
            asr_seconds=time.monotonic()-stage
            transcript = " ".join(part.text.strip() for part in segments).strip()
            if not transcript:
                return None
            stage=time.monotonic()
            translated = self.translator.translate(transcript, source, target).strip()
            translation_seconds=time.monotonic()-stage
            if not translated:
                raise TranslationUnavailable("Empty translation")
            track = folder / "voice.wav"
            stage=time.monotonic()
            self.synthesizer.synthesize(translated, target, track)
            tts_seconds=time.monotonic()-stage
            if not track.is_file():
                raise AudioBackendUnavailable("No synthesized audio produced")
            stage=time.monotonic()
            audio_pcm = wav_to_pcm(track)
            conversion_seconds=time.monotonic()-stage
            # The audio reply follows the JSON metadata as one binary WebSocket frame.
            return {"type": "translated", "original_text": transcript,
                    "translated_text": translated,
                    "source_language": source, "target_language": target,
                    "processing_seconds": round(time.monotonic() - started, 3),
                    "chunk_seconds": len(pcm) / (SAMPLE_RATE * BYTES_PER_SAMPLE),
                    "stage_seconds": {"asr":round(asr_seconds,3),"translation":round(translation_seconds,3),
                                      "tts":round(tts_seconds,3),"conversion":round(conversion_seconds,3)},
                    "pcm_bytes": len(audio_pcm)}, audio_pcm


@lru_cache(maxsize=1)
def get_live_processor() -> LiveAudioProcessor:
    model = os.getenv("NEXVARY_WHISPER_MODEL", "small")
    return LiveAudioProcessor(
        cached_asr(model, os.getenv("NEXVARY_ASR_DEVICE", "cpu")),
        ArgosTranslator(), PiperTTS()
    )
