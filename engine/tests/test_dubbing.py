import json
from pathlib import Path

import pytest
from voice_engine.dubbing import Segment, timecode, captions, validated_segments, make_mix_command, dub_video


class FakeASR:
    def transcribe(self, path, language):
        assert path.name == "original.wav"
        return [Segment(0.5, 1.5, "مرحبا"), Segment(1.7, 3.0, "كيف حالك")]


class FakeTranslation:
    def translate(self, text, source, target):
        assert (source, target) == ("ar", "en")
        return {"مرحبا": "Hello", "كيف حالك": "How are you"}[text]


class FakeTTS:
    def synthesize(self, text, language, path):
        assert language == "en"
        path.write_bytes(b"fake-wav-bytes")


def test_timecodes_and_subtitles():
    assert timecode(3661.002) == "01:01:01,002"
    assert "00:00:01,700 --> 00:00:03,000" in captions([Segment(1.7, 3, "Hello")])


def test_reject_invalid_media_segments():
    with pytest.raises(ValueError):
        validated_segments([Segment(-1, 2, "bad")], 5)
    with pytest.raises(ValueError):
        validated_segments([], 5)


def test_mix_filter_starts_clips_at_original_times(tmp_path):
    script = tmp_path / "filter.txt"
    cmd = make_mix_command([(0.5, Path("one.wav")), (1.7, Path("two.wav"))],
                           4.0, script, tmp_path / "track.wav")
    assert cmd[0] == "ffmpeg"
    assert "adelay=500:all=1" in script.read_text()
    assert "adelay=1700:all=1" in script.read_text()


def test_video_dubbing_pipeline_with_fake_audio_backends(tmp_path):
    video = tmp_path / "input.mp4"
    video.write_bytes(b"fake video")
    output = tmp_path / "output.mp4"
    calls = []

    def fake_runner(cmd):
        calls.append(cmd)
        if cmd[-1].endswith((".mp4", ".wav")):
            Path(cmd[-1]).write_bytes(b"fake output")

    report = dub_video(video, output, "ar", "en", FakeASR(),
                       FakeTranslation(), FakeTTS(),
                       runner=fake_runner, duration_probe=lambda _: 4.0)
    assert report["segments"] == 2
    assert output.is_file()
    assert output.with_suffix(".srt").is_file()
    assert "Hello" in output.with_suffix(".srt").read_text()
    with pytest.raises(FileExistsError):
        dub_video(video, output, "ar", "en", FakeASR(),
                  FakeTranslation(), FakeTTS(),
                  runner=fake_runner, duration_probe=lambda _: 4.0)
    assert len(calls) == 3
