"""Real resampling fixtures and bounded cache checks; no downloaded models."""
import math
import struct
import sys
import types
import wave
import pytest
from voice_engine.live import wav_to_pcm, pcm_rms
from voice_engine import native_translate

@pytest.mark.parametrize('rate,channels',[(16000,1),(22050,1),(24000,1),(48000,2)])
def test_real_resampler_duration_and_sound(tmp_path,rate,channels):
    pytest.importorskip('av')
    source=tmp_path/'صوت.wav'
    values=[int(8000*math.sin(2*math.pi*440*i/rate)) for i in range(rate)]
    with wave.open(str(source),'wb') as output:
        output.setnchannels(channels);output.setsampwidth(2);output.setframerate(rate)
        output.writeframes(b''.join(struct.pack('<h',v)*channels for v in values))
    pcm=wav_to_pcm(source)
    assert abs(len(pcm)-32000)<=4
    assert pcm_rms(pcm)>3000

def test_bidirectional_pivot_keeps_four_models_without_reload(monkeypatch):
    created=[]
    class Model:
        def __init__(self,path,**options):created.append(path)
    monkeypatch.setitem(sys.modules,'ctranslate2',types.SimpleNamespace(Translator=Model))
    native_translate.model.cache_clear()
    try:
        for _ in range(3):
            for path in ['ar-en','en-ru','ru-en','en-ar']:native_translate.model(path,'1')
        assert len(created)==4
        native_translate.model('es-en','1')
        assert native_translate.model.cache_info().currsize==4
    finally:native_translate.model.cache_clear()

def test_tokenizer_reused_and_invalidated_when_model_changes(monkeypatch,tmp_path):
    created=[]
    class Processor:
        def __init__(self,model_proto):created.append(model_proto)
    monkeypatch.setitem(sys.modules,'sentencepiece',types.SimpleNamespace(SentencePieceProcessor=Processor))
    path=tmp_path/'نموذج.model';path.write_bytes(b'first')
    native_translate.sentencepiece_processor.cache_clear()
    try:
        first=native_translate.sentencepiece_processor(str(path),5,1)
        assert native_translate.sentencepiece_processor(str(path),5,1) is first
        path.write_bytes(b'second')
        assert native_translate.sentencepiece_processor(str(path),6,2) is not first
        assert created==[b'first',b'second']
    finally:native_translate.sentencepiece_processor.cache_clear()
