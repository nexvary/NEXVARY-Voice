"""Real TLS/HTTP/WebSocket transport; backend text here is a synthetic fixture."""
import json
import socket
import ssl
import threading
import time
from pathlib import Path
import httpx
import pytest
import uvicorn
from fastapi import FastAPI,WebSocket
from fastapi.testclient import TestClient
from voice_engine.phone_bridge import PairingState,PhoneBridge,relay_app,lan_address


def test_pairing_is_one_use_expiring_and_revocable():
    state=PairingState();code=state.new_code();token=state.pair(code,'local')
    assert state.authorized('Bearer '+token)
    with pytest.raises(Exception):state.pair(code,'local')
    state.revoke();assert not state.authorized('Bearer '+token)
    code=state.new_code();state.deadline=0
    with pytest.raises(Exception):state.pair(code,'local')


def test_reject_public_bind_and_limit_pair_attempts():
    for address in ('0.0.0.0','8.8.8.8','127.0.0.1','::','example.com'):
        with pytest.raises(ValueError): PhoneBridge(address)
    assert lan_address('192.168.1.2') and lan_address('10.1.2.3')
    state=PairingState();state.new_code()
    for n in range(6):
        with pytest.raises(Exception):state.pair('wrong','attacker')
    with pytest.raises(Exception) as exc:state.pair(state.code,'attacker')
    assert exc.value.status_code==429


def test_unauthenticated_and_unknown_routes_never_reach_engine():
    state=PairingState();client=TestClient(relay_app(state))
    assert client.get('/health').status_code==401
    assert client.post('/pair',content='x'*1025).status_code==413
    assert client.post('/pair',content='not-json').status_code==400
    token=client.post('/pair',json={'code':state.new_code()}).json()['token']
    assert client.get('/admin',headers={'Authorization':'Bearer '+token}).status_code==404


def test_real_tls_http_and_binary_websocket_proxy():
    app=FastAPI()
    @app.get('/health')
    def health():return {'status':'ok','service':'synthetic-backend'}
    @app.post('/v1/translate')
    def translate(payload:dict):return {'translated_text':'fixture:'+payload['text']}
    @app.websocket('/v1/live/audio')
    async def echo(ws:WebSocket):
        await ws.accept()
        try:
            while True:
                value=await ws.receive_bytes();await ws.send_bytes(value)
        except Exception:pass
    sock=socket.socket();sock.bind(('127.0.0.1',0));sock.listen(4)
    server=uvicorn.Server(uvicorn.Config(app,access_log=False,log_level='error'))
    thread=threading.Thread(target=server.run,kwargs={'sockets':[sock]},daemon=True);thread.start()
    bridge=PhoneBridge('127.0.0.1',allow_loopback=True,backend=f'http://127.0.0.1:{sock.getsockname()[1]}')
    try:
        assert bridge.start() is bridge
        assert bridge.qr().startswith(b'\x89PNG')
        context=ssl.create_default_context(cafile=str(Path(bridge.temp.name)/'cert.pem'))
        # System trust must reject the private certificate until physically paired.
        with pytest.raises(httpx.ConnectError): httpx.get(bridge.endpoint+'/health',trust_env=False)
        with httpx.Client(verify=context,trust_env=False) as client:
            assert client.get(bridge.endpoint+'/health').status_code==401
            token=client.post(bridge.endpoint+'/pair',json={'code':bridge.state.code}).json()['token']
            headers={'Authorization':'Bearer '+token}
            assert client.get(bridge.endpoint+'/health',headers=headers).json()['status']=='ok'
            assert client.post(bridge.endpoint+'/v1/translate',headers=headers,json={'text':'أهلاً'}).json()['translated_text']=='fixture:أهلاً'
        from websockets.sync.client import connect
        with connect(bridge.endpoint.replace('https://','wss://')+'/v1/live/audio',ssl=context,
                     additional_headers=headers) as ws:
            ws.send(b'actual PCM transport');assert ws.recv(timeout=5)==b'actual PCM transport'
        bridge.state.revoke()
        assert httpx.get(bridge.endpoint+'/health',verify=context,headers=headers,trust_env=False).status_code==401
    finally:
        bridge.stop();server.should_exit=True;thread.join(timeout=5);sock.close()
