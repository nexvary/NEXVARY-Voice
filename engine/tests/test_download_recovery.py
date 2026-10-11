"""Simulated network failure tests, not real model download validation."""
import hashlib
import io
import json
import threading
from pathlib import Path
from email.message import Message
import pytest
from voice_engine.downloads import fetch_verified, DownloadCancelled

PAYLOAD = b'abcdefgh' * 100000
DIGEST = hashlib.sha256(PAYLOAD).hexdigest()
URL = 'https://example.invalid/model'

class Response(io.BytesIO):
    def __init__(self, data, status=200, offset=0, announced=None):
        super().__init__(data); self.status=status; self.headers=Message()
        self.headers['ETag']='"model-v1"'
        self.headers['Content-Length']=str(len(data) if announced is None else announced)
        if status==206: self.headers['Content-Range']=f'bytes {offset}-{len(PAYLOAD)-1}/{len(PAYLOAD)}'
    def geturl(self): return URL


def test_cancel_resume_and_no_redownload(tmp_path):
    path=tmp_path/'بيانات'/'voice.onnx'; stop=threading.Event(); requests=[]
    def opener(req,timeout):
        requests.append(req)
        offset=int((req.get_header('Range') or 'bytes=0-').split('=')[1].split('-')[0])
        return Response(PAYLOAD[offset:],206 if offset else 200,offset)
    def progress(done,total):
        if done>=256*1024: stop.set()
    with pytest.raises(DownloadCancelled):
        fetch_verified(URL,path,expected_digest=DIGEST,expected_size=len(PAYLOAD),opener=opener,
                       cancelled=stop.is_set,progress=progress)
    assert not path.exists()
    assert path.with_name(path.name+'.partial').exists()
    stop.clear()
    fetch_verified(URL,path,expected_digest=DIGEST,expected_size=len(PAYLOAD),opener=opener)
    assert requests[-1].get_header('Range') == 'bytes=262144-'
    assert path.read_bytes()==PAYLOAD
    fetch_verified(URL,path,expected_digest=DIGEST,expected_size=len(PAYLOAD),opener=lambda *a,**k:pytest.fail('redownload'))


def test_range_ignored_restarts_safely(tmp_path):
    path=tmp_path/'voice'; stage=tmp_path/'voice.partial';stage.write_bytes(PAYLOAD[:10])
    (tmp_path/'voice.partial.json').write_text(json.dumps({'url':URL,'digest':DIGEST,'algorithm':'sha256','validator':'"model-v1"'}))
    fetch_verified(URL,path,expected_digest=DIGEST,opener=lambda *a,**k:Response(PAYLOAD))
    assert path.read_bytes()==PAYLOAD


def test_integrity_failure_never_replaces_existing_file(tmp_path):
    path=tmp_path/'voice';path.write_bytes(b'existing-user-data')
    with pytest.raises(ValueError,match='سلامة'):
        fetch_verified(URL,path,expected_digest=DIGEST,opener=lambda *a,**k:Response(b'corrupt'))
    assert path.read_bytes()==b'existing-user-data'


def test_disconnection_keeps_partial_for_retry(tmp_path):
    path=tmp_path/'voice'
    with pytest.raises(RuntimeError,match='انقطع'):
        fetch_verified(URL,path,expected_digest=DIGEST,expected_size=len(PAYLOAD),
                       opener=lambda *a,**k:Response(PAYLOAD[:1000],announced=len(PAYLOAD)))
    assert (tmp_path/'voice.partial').stat().st_size==1000


def test_insecure_source_rejected(tmp_path):
    with pytest.raises(ValueError): fetch_verified('http://example.invalid',tmp_path/'voice',expected_digest=DIGEST)
