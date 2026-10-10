import pytest

from voice_engine.subtitles import translate_srt


class FakeTranslator:
    def translate(self, text, source, target):
        return "EN: " + text


SAMPLE = "1\n00:00:00,000 --> 00:00:02,000\nأهلا بكم\n\n2\n00:00:02,500 --> 00:00:04,000\nمنتج رائع\n"


def test_srt_preserves_timing():
    result = translate_srt(SAMPLE, "ar", "en", FakeTranslator())
    assert "00:00:02,500 --> 00:00:04,000" in result
    assert "EN: أهلا بكم" in result
    assert result.count("-->") == 2


def test_srt_rejects_malformed_cues():
    with pytest.raises(ValueError):
        translate_srt("Hello", "ar", "en", FakeTranslator())
