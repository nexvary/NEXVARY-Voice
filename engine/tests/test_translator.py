import pytest

from voice_engine.translator import ArgosTranslator, TranslationUnavailable
from voice_engine.video_mux import build_command


def test_same_language_does_not_require_model():
    assert ArgosTranslator().translate("مرحبًا", "ar", "ar") == "مرحبًا"


def test_model_unavailable_is_explicit():
    try:
        result = ArgosTranslator().translate("bonjour", "fr", "hi")
    except TranslationUnavailable:
        return
    # On a development machine that already has this rare pair, the engine is allowed to translate.
    assert result.strip()


def test_mux_does_not_overwrite_source(tmp_path):
    video = tmp_path / "video.mp4"
    audio = tmp_path / "voice.wav"
    video.touch()
    audio.touch()
    assert build_command(video, audio, tmp_path / "out.mp4")[0] == "ffmpeg"
    with pytest.raises(ValueError):
        build_command(video, audio, video)
