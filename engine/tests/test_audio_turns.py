import struct
import pytest
from voice_engine.audio_turns import SpeechTurns, FRAME_BYTES
from voice_engine.live import CHUNK_BYTES, MIN_CHUNK_BYTES
QUIET = b'\0' * FRAME_BYTES
SPEECH = struct.pack('<h', 1200) * (FRAME_BYTES // 2)


def test_idle_silence_never_creates_requests():
    turns = SpeechTurns()
    assert all(turns.feed(QUIET) is None for _ in range(1000))
    assert not turns.buffer


def test_short_turn_ends_after_400_ms_and_keeps_onset():
    turns = SpeechTurns()
    assert turns.feed(QUIET) is None
    for _ in range(3): assert turns.feed(SPEECH) is None
    for _ in range(3): assert turns.feed(QUIET) is None
    assert turns.feed(QUIET) == QUIET + SPEECH * 3 + QUIET * 4
    assert not turns.buffer


def test_pause_within_sentence_does_not_end_turn():
    turns = SpeechTurns()
    for frame in [SPEECH]*4 + [QUIET]*3 + [SPEECH]*4:
        assert turns.feed(frame) is None
    assert turns.quiet == 0


def test_long_speech_is_bounded_and_next_turn_starts_clean():
    turns = SpeechTurns()
    for _ in range(32): result = turns.feed(SPEECH)
    assert len(result) == CHUNK_BYTES
    assert turns.feed(SPEECH) is None
    assert len(turns.buffer) == FRAME_BYTES


def test_single_block_speech_meets_server_minimum():
    turns = SpeechTurns()
    turns.feed(SPEECH)
    for _ in range(3): turns.feed(QUIET)
    assert len(turns.feed(QUIET)) >= MIN_CHUNK_BYTES


def test_reset_discards_cancelled_speech():
    turns = SpeechTurns()
    turns.feed(SPEECH)
    turns.reset()
    assert turns.feed(QUIET) is None
    with pytest.raises(ValueError): turns.feed(b'\0')


def test_empty_recognition_acknowledges_flush(monkeypatch):
    from fastapi.testclient import TestClient
    import voice_engine.api as api
    class Quiet:
        def process(self, pcm, source, target): return None
    monkeypatch.setattr(api, 'get_live_processor', lambda: Quiet())
    monkeypatch.delenv('NEXVARY_API_TOKEN', raising=False)
    with TestClient(api.app) as client:
        with client.websocket_connect('/v1/live/audio') as ws:
            ws.send_json(dict(source_language='ar', target_language='en', format='pcm_s16le', sample_rate=16000))
            ws.send_bytes(SPEECH*5)
            ws.send_json({'type':'flush'})
            assert ws.receive_json() == {'type':'idle'}
            ws.send_json({'type':'stop'})


def test_local_audio_check_is_local_and_reports_signal(monkeypatch):
    import sys
    from types import SimpleNamespace
    from voice_engine.desktop_audio import test_audio_devices as check
    calls = []
    class Stream:
        def __init__(self, **kwargs): calls.append(kwargs)
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, frames):
            assert frames == 48000
            return SPEECH * 30, False
        def write(self, pcm):
            assert pcm == SPEECH * 30
            return False
    monkeypatch.setitem(sys.modules, 'sounddevice', SimpleNamespace(
        check_input_settings=lambda **kw: calls.append(kw),
        check_output_settings=lambda **kw: calls.append(kw),
        RawInputStream=Stream, RawOutputStream=Stream))
    assert '1200' in check(2, 7)
    assert [c['device'] for c in calls] == [2, 7, 2, 7]


def test_silent_microphone_is_not_reported_ready(monkeypatch):
    import sys
    from types import SimpleNamespace
    from voice_engine.desktop_audio import test_audio_devices as check
    from voice_engine.desktop_api import ClientError
    class Input:
        def __init__(self, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, count): return QUIET * 30, False
    def forbidden(**kwargs): raise AssertionError('Must not play a silent success sample')
    monkeypatch.setitem(sys.modules, 'sounddevice', SimpleNamespace(
        check_input_settings=lambda **kw: None, check_output_settings=lambda **kw: None,
        RawInputStream=Input, RawOutputStream=forbidden))
    with pytest.raises(ClientError): check()


def test_voice_client_sends_short_turn_and_pauses_capture(monkeypatch):
    import sys, threading, json
    from types import SimpleNamespace
    import websockets.sync.client
    from voice_engine.desktop_audio import run_audio_session
    stopping = threading.Event()
    sent, played = [], []
    available = threading.Event()
    capture = [None]
    class Socket:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def send(self, value):
            sent.append(value)
            if isinstance(value, str) and json.loads(value).get('type') == 'flush':
                # While inference is in flight these frames must be dropped.
                for _ in range(50): capture[0](SPEECH,1600,None,None)
                available.set()
        def __iter__(self):
            assert available.wait(3)
            yield json.dumps({'type':'translated','processing_seconds':0.1,'chunk_seconds':0.5})
            yield SPEECH
        def close(self): available.set()
    class Output:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def write(self, value): played.append(value); stopping.set()
    class Input:
        def __init__(self, callback, **kwargs): capture[0] = callback
        def __enter__(self):
            for frame in [SPEECH] + [QUIET]*4: capture[0](frame,1600,None,None)
            return self
        def __exit__(self, *args): pass
    monkeypatch.setitem(sys.modules,'sounddevice',SimpleNamespace(RawInputStream=Input,RawOutputStream=Output))
    monkeypatch.setattr(websockets.sync.client,'connect',lambda *args,**kwargs: Socket())
    run_audio_session('ws://127.0.0.1:8000/v1/live/audio','','ar','en',stopping,lambda text: None)
    assert b''.join(v for v in sent if isinstance(v,bytes)) == SPEECH + QUIET*4
    assert played == [SPEECH]
    assert sum(isinstance(v,str) and json.loads(v).get('type')=='flush' for v in sent) == 1
