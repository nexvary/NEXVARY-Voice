import pytest
from voice_engine.native_translate import route,chunks
from voice_engine.piper_adapter import short_path


def test_english_pivot_and_additional_language_routes():
    pairs={('bn','en'),('en','ar'),('ar','fr'),('fr','de')}
    assert route(pairs,'bn','ar')==[('bn','en'),('en','ar')]
    assert route(pairs,'bn','de')[-1]==('fr','de')
    with pytest.raises(RuntimeError): route(pairs,'de','bn')


def test_unicode_sentence_chunks_are_bounded_and_lossless():
    source=' '.join(['هذا نص عربي للاختبار']*100)
    parts=chunks(source,100)
    assert all(len(p)<=100 for p in parts)
    assert ' '.join(parts)==source
    assert chunks('Hello. مرحبا؟ বাংলা।')==['Hello.','مرحبا؟','বাংলা।']


def test_native_alias_preserves_unicode_path_off_windows(tmp_path):
    assert short_path(tmp_path/'ملف')
