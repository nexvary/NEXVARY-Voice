"""Explicit, revocable LAN-only TLS relay to the unchanged loopback engine.

No firewall changes, public binding, persisted bearer secrets or access logs.
QR pins a fresh certificate and carries a one-use 180-second pairing secret.
"""
from __future__ import annotations
import asyncio
import datetime as dt
import hashlib
import hmac
import io
import ipaddress
import json
import os
import re
import secrets
import socket
import tempfile
import threading
import time
from pathlib import Path
import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request, WebSocket
from starlette.responses import StreamingResponse
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

NETWORKS = tuple(ipaddress.ip_network(n) for n in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16'))

def lan_address(value):
    try: return any(ipaddress.ip_address(value) in n for n in NETWORKS)
    except ValueError: return False


def interfaces():
    import psutil
    result = []
    try: adapters = psutil.net_if_addrs()
    except OSError: return []
    for name, addresses in adapters.items():
        for entry in addresses:
            if entry.family == socket.AF_INET and lan_address(entry.address):
                result.append((name, entry.address))
    return result


class PairingState:
    def __init__(self):
        self.lock = threading.Lock()
        self.sessions = {}
        self.code = ''
        self.deadline = 0
        self.attempts = {}

    def new_code(self):
        with self.lock:
            self.code = secrets.token_urlsafe(32)
            self.deadline = time.monotonic()+180
            return self.code

    def pair(self, code, address):
        with self.lock:
            now = time.monotonic()
            # Bounded rate tracking; no secrets retained as keys.
            self.attempts = {a:v for a,v in self.attempts.items() if now-v[0]<60}
            started, count = self.attempts.get(address,(now,0))
            if count >= 6 or len(self.attempts)>128: raise HTTPException(429,'Too many pairing attempts')
            self.attempts[address] = (started,count+1)
            if not self.code or now>self.deadline or not isinstance(code,str) or not hmac.compare_digest(code,self.code):
                raise HTTPException(403,'Pairing code expired or invalid')
            self.sessions = {t:e for t,e in self.sessions.items() if e>now}
            if len(self.sessions)>=4: raise HTTPException(409,'Disconnect phones before pairing more')
            self.code = ''
            token = secrets.token_urlsafe(32)
            self.sessions[token] = now+8*3600
            return token

    def authorized(self, header):
        if not header or not header.startswith('Bearer '): return False
        token = header[7:]
        with self.lock:
            return any(expiry>time.monotonic() and hmac.compare_digest(token,known) for known,expiry in self.sessions.items())

    def revoke(self):
        with self.lock:
            self.sessions.clear(); self.code='';self.deadline=0


_ALLOWED = re.compile(r'/(?:health|v1/(?:languages|models/status|translate|subtitles/translate|dub/jobs(?:/[a-f0-9-]{36}(?:/(?:video|subtitles|cancel))?)?))\Z')

def relay_app(state: PairingState, backend='http://127.0.0.1:8000'):
    app = FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
    def upstream_headers():
        token = os.environ.get('NEXVARY_API_TOKEN','')
        return {'Authorization':'Bearer '+token} if token else {}

    @app.post('/pair')
    async def pair(request: Request):
        body = await request.body()
        if len(body)>1024: raise HTTPException(413,'Pairing payload too large')
        try: code = json.loads(body).get('code')
        except (ValueError,AttributeError): raise HTTPException(400,'Invalid pairing payload')
        return {'token':state.pair(code,request.client.host if request.client else 'unknown'), 'expires_in':28800}

    @app.api_route('/{path:path}',methods=['GET','POST','DELETE'])
    async def proxy(path: str, request: Request):
        if not state.authorized(request.headers.get('authorization')): raise HTTPException(401,'Unauthorized')
        route = '/'+path
        if not _ALLOWED.fullmatch(route): raise HTTPException(404,'Unknown route')
        headers = upstream_headers()
        if request.headers.get('content-type'): headers['Content-Type'] = request.headers['content-type']
        async def upload():
            total = 0
            async for part in request.stream():
                total += len(part)
                if total>82*1024*1024: raise HTTPException(413,'Upload exceeds limit')
                yield part
        client = httpx.AsyncClient(timeout=httpx.Timeout(120,connect=5),follow_redirects=False,trust_env=False)
        try:
            upstream = await client.send(client.build_request(request.method,backend+route,headers=headers,
                content=upload() if request.method=='POST' else None),stream=True)
        except Exception:
            await client.aclose();raise HTTPException(502,'Local engine unavailable')
        async def download():
            try:
                async for part in upstream.aiter_bytes(): yield part
            finally: await upstream.aclose();await client.aclose()
        return StreamingResponse(download(),status_code=upstream.status_code,
            media_type=upstream.headers.get('content-type','application/octet-stream'))

    @app.websocket('/v1/live/{kind}')
    async def live(ws: WebSocket,kind: str):
        if kind not in {'audio','text'} or not state.authorized(ws.headers.get('authorization')):
            await ws.close(code=1008);return
        from websockets.asyncio.client import connect
        import inspect
        options = {'proxy': None} if 'proxy' in inspect.signature(connect).parameters else {}
        await ws.accept()
        try:
            async with connect(backend.replace('http://','ws://')+'/v1/live/'+kind,
                               additional_headers=upstream_headers(),max_size=2*1024*1024,**options) as upstream:
                async def send():
                    while True:
                        item = await ws.receive()
                        if item['type']=='websocket.disconnect': return
                        await upstream.send(item.get('bytes') if item.get('bytes') is not None else item['text'])
                async def receive():
                    async for item in upstream:
                        if isinstance(item,bytes): await ws.send_bytes(item)
                        else: await ws.send_text(item)
                async def expiry():
                    while state.authorized(ws.headers.get('authorization')):
                        await asyncio.sleep(1)
                    await ws.close(code=1008,reason='Pairing session expired or revoked')
                tasks = [asyncio.create_task(send()),asyncio.create_task(receive()),asyncio.create_task(expiry())]
                try: await asyncio.wait(tasks,return_when=asyncio.FIRST_COMPLETED)
                finally:
                    for task in tasks: task.cancel()
                    await asyncio.gather(*tasks,return_exceptions=True)
        except Exception:
            try: await ws.close(code=1011,reason='Local engine connection lost')
            except RuntimeError: pass
    return app


class PhoneBridge:
    def __init__(self, host: str, *, allow_loopback=False, backend='http://127.0.0.1:8000'):
        if not lan_address(host) and not (allow_loopback and host=='127.0.0.1'):
            raise ValueError('اختر عنوان شبكة محلية خاصة؛ الربط العام غير مسموح.')
        self.host=host;self.backend=backend;self.state=PairingState();self.server=None;self.thread=None;self.temp=None

    def start(self):
        self.temp=tempfile.TemporaryDirectory(prefix='nexvary-phone-')
        root=Path(self.temp.name)
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'NEXVARY local phone bridge')])
        now=dt.datetime.now(dt.timezone.utc)
        certificate=(x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now-dt.timedelta(minutes=5))
            .not_valid_after(now+dt.timedelta(days=2)).add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address(self.host))]),critical=False)
            .sign(key,hashes.SHA256()))
        (root/'cert.pem').write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
        (root/'key.pem').write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
        self.fingerprint=certificate.fingerprint(hashes.SHA256()).hex()
        sock=socket.socket();sock.bind((self.host,0));sock.listen(16)
        self.endpoint=f'https://{self.host}:{sock.getsockname()[1]}'
        config=uvicorn.Config(relay_app(self.state,self.backend),host=self.host,ssl_certfile=str(root/'cert.pem'),
            ssl_keyfile=str(root/'key.pem'),access_log=False,log_level='error',limit_concurrency=16,timeout_keep_alive=5,timeout_graceful_shutdown=3,ws_max_size=2*1024*1024)
        self.server=uvicorn.Server(config)
        self.thread=threading.Thread(target=self.server.run,kwargs={'sockets':[sock]},daemon=True);self.thread.start()
        deadline=time.monotonic()+8
        while not self.server.started:
            if not self.thread.is_alive() or time.monotonic()>deadline:
                sock.close();self.stop();raise RuntimeError('تعذر فتح ربط الهاتف؛ تحقق من الشبكة أو برنامج الحماية دون تعطيله.')
            time.sleep(.03)
        return self

    def qr(self):
        from urllib.parse import urlencode
        import qrcode
        code=self.state.new_code()
        payload='nexvary-voice://pair?'+urlencode({'endpoint':self.endpoint,'fingerprint':self.fingerprint,'code':code})
        image=qrcode.make(payload);stream=io.BytesIO();image.save(stream,format='PNG')
        return stream.getvalue()

    def stop(self):
        self.state.revoke()
        if self.server: self.server.should_exit=True
        if self.thread:
            self.thread.join(timeout=5)
            if self.thread.is_alive(): raise RuntimeError('لا يزال اتصال الهاتف يُغلق؛ أعد المحاولة.')
        if self.temp: self.temp.cleanup()
        self.server=None;self.thread=None;self.temp=None
