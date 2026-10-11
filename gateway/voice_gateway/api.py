"""Private routing gateway; never loads Whisper/Piper/Argos on this host.

Authentication is required for all API endpoints other than local health.
Worker destination and worker credential are operator-controlled environment variables.
"""
from __future__ import annotations

import asyncio
import hmac
import json
import os
import re
import tempfile
from urllib.parse import urlsplit

import httpx
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile, WebSocket
from fastapi.responses import JSONResponse, StreamingResponse
from websockets.asyncio.client import connect as websocket_connect

app = FastAPI(title="NEXVARY Voice — Lightweight Gateway", version="0.1.0",
              docs_url=None, redoc_url=None)
MAX_JSON = 600_000
MAX_UPLOAD = 80 * 1024 * 1024
VIDEO_ID = re.compile(r"^[a-f0-9-]{36}$")


def valid_bearer(header: str | None) -> bool:
    secret = os.environ.get("NEXVARY_GATEWAY_TOKEN", "")
    if len(secret) < 32 or "CHANGE" in secret.upper():
        return False
    return bool(header and hmac.compare_digest(header, "Bearer " + secret))


def authenticate(authorization: str | None = Header(default=None)) -> None:
    if not valid_bearer(authorization):
        raise HTTPException(401, detail="Unauthorized")


def worker_address() -> str:
    url = os.environ.get("NEXVARY_WORKER_URL", "").rstrip("/")
    if not url:
        raise HTTPException(503, detail="No inference worker configured")
    parsed = urlsplit(url)
    if (parsed.scheme not in ("https", "http") or not parsed.netloc
        or parsed.username or parsed.password or parsed.path not in ("", "/")
        or parsed.query or parsed.fragment):
        raise HTTPException(503, detail="Invalid worker URL configuration")
    local = parsed.hostname in ("127.0.0.1", "localhost", "::1")
    if parsed.scheme != "https" and not (local or os.environ.get("NEXVARY_ALLOW_PRIVATE_HTTP_WORKER") == "1"):
        raise HTTPException(503, detail="Remote worker must use HTTPS")
    return url


def upstream_headers() -> dict[str, str]:
    token = os.environ.get("NEXVARY_WORKER_TOKEN", "")
    return {"Authorization": "Bearer " + token} if token else {}


def make_client(*, timeout: float = 40.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout, trust_env=False, follow_redirects=False)


def safe_upstream(response: httpx.Response) -> JSONResponse:
    try:
        payload = response.json()
    except ValueError:
        payload = {"detail": "Worker returned a non-JSON response"}
    return JSONResponse(status_code=response.status_code, content=payload)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "voice-gateway", "mode": "lightweight",
            "worker_configured": bool(os.environ.get("NEXVARY_WORKER_URL"))}


@app.get("/v1/capabilities", dependencies=[Depends(authenticate)])
async def capabilities():
    configured = bool(os.environ.get("NEXVARY_WORKER_URL"))
    return {"gateway": True, "local_speech_models": False,
            "worker_configured": configured,
            "audio_and_dubbing_available": "depends_on_worker" if configured else False}


@app.post("/v1/translate", dependencies=[Depends(authenticate)])
@app.post("/v1/subtitles/translate", dependencies=[Depends(authenticate)])
async def forward_json(request: Request):
    worker = worker_address()
    payload = bytearray()
    async for part in request.stream():
        payload.extend(part)
        if len(payload) > MAX_JSON:
            raise HTTPException(413, detail="JSON request too large")
    try:
        obj = json.loads(payload)
    except ValueError as exc:
        raise HTTPException(422, detail="Invalid JSON") from exc
    path = request.url.path
    try:
        async with make_client() as client:
            upstream = await client.post(worker + path, json=obj, headers=upstream_headers())
            return safe_upstream(upstream)
    except httpx.TimeoutException as exc:
        raise HTTPException(504, detail="Inference worker timed out") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(502, detail="Inference worker unreachable") from exc


@app.get("/v1/dub/jobs/{job_id}", dependencies=[Depends(authenticate)])
async def job_status(job_id: str):
    if not VIDEO_ID.fullmatch(job_id):
        raise HTTPException(422, detail="Invalid job ID")
    worker = worker_address()
    try:
        async with make_client() as client:
            resp = await client.get(worker + "/v1/dub/jobs/" + job_id, headers=upstream_headers())
            return safe_upstream(resp)
    except httpx.HTTPError as exc:
        raise HTTPException(502, detail="Inference worker unreachable") from exc


@app.delete("/v1/dub/jobs/{job_id}", dependencies=[Depends(authenticate)])
async def job_delete(job_id: str):
    if not VIDEO_ID.fullmatch(job_id):
        raise HTTPException(422, detail="Invalid job ID")
    worker = worker_address()
    try:
        async with make_client() as client:
            resp = await client.delete(worker + "/v1/dub/jobs/" + job_id, headers=upstream_headers())
            return safe_upstream(resp)
    except httpx.HTTPError as exc:
        raise HTTPException(502, detail="Inference worker unreachable") from exc


@app.post("/v1/dub/jobs", dependencies=[Depends(authenticate)], status_code=202)
async def upload_video(file: UploadFile = File(...), source_language: str = Form(...),
                       target_language: str = Form(...)):
    worker = worker_address()
    if not file.filename or not file.filename.lower().endswith(".mp4"):
        raise HTTPException(415, detail="Only MP4 is allowed")
    if not re.fullmatch(r"[a-z]{2}(?:-[A-Za-z]{2})?", source_language) or not re.fullmatch(r"[a-z]{2}(?:-[A-Za-z]{2})?", target_language):
        raise HTTPException(422, detail="Invalid language")
    if source_language == target_language:
        raise HTTPException(422, detail="Choose distinct languages")
    try:
        with tempfile.TemporaryFile(mode="w+b") as temporary:
            total = 0
            while True:
                buf = await file.read(65536)
                if not buf:
                    break
                total += len(buf)
                if total > MAX_UPLOAD:
                    raise HTTPException(413, detail="Video exceeds 80 MiB")
                temporary.write(buf)
            if not total:
                raise HTTPException(422, detail="Empty video")
            temporary.seek(0)
            try:
                async with make_client(timeout=180) as client:
                    resp = await client.post(
                        worker + "/v1/dub/jobs", headers=upstream_headers(),
                        files={"file": ("video.mp4", temporary, "video/mp4")},
                        data={"source_language": source_language, "target_language": target_language}
                    )
                    return safe_upstream(resp)
            except httpx.HTTPError as exc:
                raise HTTPException(502, detail="Inference worker upload failed") from exc
    finally:
        await file.close()


@app.get("/v1/dub/jobs/{job_id}/video", dependencies=[Depends(authenticate)])
async def download_video(job_id: str):
    if not VIDEO_ID.fullmatch(job_id):
        raise HTTPException(422, detail="Invalid job ID")
    worker = worker_address()
    client = make_client(timeout=180)
    try:
        req = client.build_request("GET", worker + "/v1/dub/jobs/" + job_id + "/video",
                                   headers=upstream_headers())
        resp = await client.send(req, stream=True)
    except httpx.HTTPError as exc:
        await client.aclose()
        raise HTTPException(502, detail="Inference worker unreachable") from exc
    if resp.status_code != 200:
        code = resp.status_code
        await resp.aclose()
        await client.aclose()
        raise HTTPException(code, detail="Video not ready or unavailable")

    async def output_stream():
        try:
            async for piece in resp.aiter_bytes(chunk_size=65536):
                yield piece
        finally:
            await resp.aclose()
            await client.aclose()

    return StreamingResponse(output_stream(), media_type="video/mp4",
                             headers={"Content-Disposition": 'attachment; filename="NEXVARY-Voice-Dubbed.mp4"'})


@app.websocket("/v1/live/audio")
async def speech_audio(websocket: WebSocket):
    if not valid_bearer(websocket.headers.get("authorization")):
        await websocket.close(code=1008)
        return
    try:
        base = worker_address()
    except HTTPException:
        await websocket.close(code=1013)
        return
    scheme = "wss" if base.startswith("https://") else "ws"
    target = scheme + "://" + base.split("://", 1)[1] + "/v1/live/audio"
    try:
        async with websocket_connect(target, additional_headers=upstream_headers(),
                                     max_size=8_000_000, max_queue=8,
                                     open_timeout=12) as upstream:
            await websocket.accept()

            async def from_phone():
                while True:
                    message = await websocket.receive()
                    if message["type"] == "websocket.disconnect":
                        return
                    body = message.get("bytes")
                    if body is not None:
                        if not 0 < len(body) <= 32000:
                            await websocket.close(code=1009)
                            return
                        await upstream.send(body)
                    else:
                        text = message.get("text")
                        if text is None or len(text) > 8192:
                            await websocket.close(code=1009)
                            return
                        await upstream.send(text)

            async def from_worker():
                async for message in upstream:
                    if isinstance(message, bytes):
                        await websocket.send_bytes(message)
                    else:
                        await websocket.send_text(message)

            tasks = [asyncio.create_task(from_phone()), asyncio.create_task(from_worker())]
            try:
                done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    task.result()
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
    except Exception:
        try:
            await websocket.close(code=1011)
        except RuntimeError:
            pass
