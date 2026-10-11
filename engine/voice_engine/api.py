"""Text, subtitle and segmented speech-audio WebSocket API."""
from __future__ import annotations

import hmac
import json
import os
from functools import lru_cache

from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect, UploadFile, File, Form
from fastapi.responses import FileResponse
from .video_jobs import get_job_queue, MAX_UPLOAD_BYTES
from starlette.concurrency import run_in_threadpool
from .speech import AudioBackendUnavailable
from .live import CHUNK_BYTES, MAX_FRAME_BYTES, MIN_CHUNK_BYTES, get_live_processor
from .subtitles import translate_srt
from pydantic import BaseModel, Field, field_validator

from .translator import ArgosTranslator, TranslationUnavailable, Translator

app = FastAPI(title="NEXVARY Voice Engine", version="0.5.2", docs_url="/docs")

LANGUAGES = {
    "ar": "Arabic", "en": "English", "hi": "Hindi", "tr": "Turkish",
    "ru": "Russian", "bn": "Bengali",
    "fr": "French", "de": "German", "es": "Spanish", "it": "Italian",
}


class Turn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    source_language: str = Field(min_length=2, max_length=10)
    target_language: str = Field(min_length=2, max_length=10)

    @field_validator("source_language", "target_language")
    @classmethod
    def validate_language(cls, value: str) -> str:
        code = value.split("-")[0].lower()
        if code not in LANGUAGES:
            raise ValueError("Unsupported language code")
        return code

    @field_validator("text")
    @classmethod
    def strip_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Text cannot be blank")
        return value


class SubtitleRequest(BaseModel):
    srt: str = Field(min_length=1, max_length=500_000)
    source_language: str
    target_language: str

    @field_validator("source_language", "target_language")
    @classmethod
    def validate_language(cls, value: str) -> str:
        return Turn.validate_language(value)


class SubtitleResult(BaseModel):
    srt: str
    source_language: str
    target_language: str


class TranslationResult(BaseModel):
    original_text: str
    translated_text: str
    source_language: str
    target_language: str


@lru_cache
def get_translator() -> Translator:
    return ArgosTranslator()


def token_valid(header: str | None) -> bool:
    token = os.environ.get("NEXVARY_API_TOKEN")
    if not token:
        return True  # loopback-only development; never expose without token and TLS
    return bool(header and hmac.compare_digest(header, f"Bearer {token}"))


def require_token(authorization: str | None = Header(default=None)) -> None:
    if not token_valid(authorization):
        raise HTTPException(status_code=401, detail="Unauthorized")


def process_turn(turn: Turn, translator: Translator) -> TranslationResult:
    translated = translator.translate(turn.text, turn.source_language, turn.target_language)
    return TranslationResult(
        original_text=turn.text,
        translated_text=translated,
        source_language=turn.source_language,
        target_language=turn.target_language,
    )


@app.get("/health")
def health():
    return {"status": "ok", "component": "voice-engine", "audio_streaming": True, "protocol": "segmented_pcm16_speech_turns"}


@app.get("/v1/languages", dependencies=[Depends(require_token)])
def languages():
    return {"languages": LANGUAGES, "availability": "requires installed models"}


@app.post("/v1/translate", response_model=TranslationResult, dependencies=[Depends(require_token)])
def translate(turn: Turn, translator: Translator = Depends(get_translator)):
    try:
        return process_turn(turn, translator)
    except TranslationUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "model_unavailable", "message": str(exc)},
        ) from exc


@app.post("/v1/subtitles/translate", response_model=SubtitleResult, dependencies=[Depends(require_token)])
def translate_subtitles(payload: SubtitleRequest, translator: Translator = Depends(get_translator)):
    """Translate existing subtitle text. Does not synthesize voices."""
    if payload.source_language == payload.target_language:
        return SubtitleResult(srt=payload.srt, source_language=payload.source_language,
                              target_language=payload.target_language)
    try:
        translated = translate_srt(payload.srt, payload.source_language, payload.target_language, translator)
        return SubtitleResult(srt=translated, source_language=payload.source_language,
                              target_language=payload.target_language)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except TranslationUnavailable as exc:
        raise HTTPException(status_code=503, detail={"code": "model_unavailable",
                                                       "message": str(exc)}) from exc


@app.websocket("/v1/live/text")
async def live_text(websocket: WebSocket, translator: Translator = Depends(get_translator)):
    # This endpoint only transports text turns; audio / lip sync are out of scope.
    if not token_valid(websocket.headers.get("authorization")):
        await websocket.close(code=1008, reason="Unauthorized")
        return
    await websocket.accept()
    try:
        while True:
            raw = await websocket.receive_text()
            if len(raw) > 8192:
                await websocket.send_json({"error": "message_too_large"})
                continue
            try:
                turn = Turn.model_validate(json.loads(raw))
                translated = process_turn(turn, translator)
                await websocket.send_json(translated.model_dump())
            except (ValueError, TypeError) as exc:
                await websocket.send_json({"error": "invalid_turn", "message": str(exc)[:160]})
            except TranslationUnavailable as exc:
                await websocket.send_json({"error": "model_unavailable", "message": str(exc)})
    except WebSocketDisconnect:
        pass


@app.websocket("/v1/live/audio")
async def live_audio(websocket: WebSocket):
    """Authenticated half-duplex PCM16 audio turns, 3.2 seconds per ASR pass.

    Handshake JSON: {"source_language":"hi","target_language":"ar",
                     "format":"pcm_s16le","sample_rate":16000}
    Then send binary microphone PCM. Reply: translated JSON followed by raw PCM16
    binary at 16 kHz. This is not continuous overlapping-speaker diarization.
    """
    if not token_valid(websocket.headers.get("authorization")):
        await websocket.close(code=1008, reason="Unauthorized")
        return
    await websocket.accept()
    try:
        hello = await websocket.receive_json()
        source = Turn.validate_language(str(hello.get("source_language", "")))
        target = Turn.validate_language(str(hello.get("target_language", "")))
        if (source == target or hello.get("format") != "pcm_s16le"
                or hello.get("sample_rate") != 16000):
            await websocket.send_json({"type": "error", "message": "Invalid PCM16 session parameters"})
            await websocket.close(code=1003)
            return
        try:
            processor = await run_in_threadpool(get_live_processor)
        except AudioBackendUnavailable as exc:
            await websocket.send_json({"type": "error", "message": str(exc)})
            await websocket.close(code=1011)
            return
        buffer = bytearray()
        async def handle(chunk: bytes) -> None:
            try:
                def run_chunk():
                    from .workload import exclusive
                    with exclusive('live-audio'): return processor.process(chunk, source, target)
                translated = await run_in_threadpool(run_chunk)
                if translated is None:
                    return
                meta, pcm = translated
                await websocket.send_json(meta)
                await websocket.send_bytes(pcm)
            except (AudioBackendUnavailable, TranslationUnavailable, ValueError, RuntimeError) as exc:
                await websocket.send_json({"type": "error", "message": str(exc)[:180]})

        while True:
            incoming = await websocket.receive()
            if incoming["type"] == "websocket.disconnect":
                return
            data = incoming.get("bytes")
            if data is None:
                try:
                    message = json.loads(incoming.get("text") or "{}")
                except ValueError:
                    await websocket.send_json({"type": "error", "message": "Invalid control message"})
                    continue
                if message.get("type") == "stop":
                    return
                if message.get("type") == "flush":
                    if len(buffer) >= MIN_CHUNK_BYTES:
                        await handle(bytes(buffer))
                    buffer.clear()
                continue
            if not data or len(data) > MAX_FRAME_BYTES or len(data) % 2:
                await websocket.send_json({"type": "error", "message": "Invalid PCM frame size"})
                continue
            buffer.extend(data)
            while len(buffer) >= CHUNK_BYTES:
                chunk = bytes(buffer[:CHUNK_BYTES])
                del buffer[:CHUNK_BYTES]
                await handle(chunk)
    except (WebSocketDisconnect, KeyError, ValueError, TypeError):
        # End malformed client sessions without traceback or transcript persistence.
        try:
            await websocket.close(code=1003)
        except RuntimeError:
            pass


@app.post("/v1/dub/jobs", status_code=202, dependencies=[Depends(require_token)])
async def video_job_submit(
    file: UploadFile = File(...),
    source_language: str = Form(...),
    target_language: str = Form(...)
):
    """Receive MP4 up to 80 MiB, queue on-prem speech dub and return job ID."""
    try:
        source = Turn.validate_language(source_language)
        target = Turn.validate_language(target_language)
    except ValueError as exc:
        raise HTTPException(422, detail="Unsupported language") from exc
    if source == target:
        raise HTTPException(422, detail="Choose two different languages")
    if not file.filename or not file.filename.lower().endswith(".mp4"):
        raise HTTPException(415, detail="Only MP4 video uploads supported")
    queue = get_job_queue()
    try:
        job = queue.allocate(source, target)
    except RuntimeError as exc:
        raise HTTPException(429, detail=str(exc)) from exc
    try:
        total = 0
        path = job.workdir / "source.mp4"
        with path.open("wb") as sink:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, detail="Video must be at most 80 MiB")
                sink.write(chunk)
        if total == 0:
            raise HTTPException(422, detail="Empty video")
        queue.start(job)
        return job.view()
    except Exception:
        queue.fail_upload(job.job_id)
        raise
    finally:
        await file.close()


@app.get("/v1/dub/jobs/{job_id}", dependencies=[Depends(require_token)])
def video_job_status(job_id: str):
    job = get_job_queue().get(job_id)
    if job is None:
        raise HTTPException(404, detail="Unknown or expired video job")
    return job.view()


@app.get("/v1/dub/jobs/{job_id}/video", dependencies=[Depends(require_token)])
def video_job_download(job_id: str):
    job = get_job_queue().get(job_id)
    if job is None:
        raise HTTPException(404, detail="Unknown or expired video job")
    if job.status != "complete" or job.output is None or not job.output.is_file():
        raise HTTPException(409, detail="Dubbing is not complete")
    return FileResponse(job.output, media_type="video/mp4",
                        filename="NEXVARY-Voice-Dubbed.mp4")


@app.delete("/v1/dub/jobs/{job_id}", dependencies=[Depends(require_token)])
def video_job_delete(job_id: str):
    try:
        deleted = get_job_queue().delete(job_id)
    except RuntimeError as exc:
        raise HTTPException(409, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(404, detail="Unknown video job")
    return {"deleted": True}


@app.get('/v1/models/status', dependencies=[Depends(require_token)])
def model_readiness():
    from .model_status import report
    return report()


@app.get('/v1/dub/jobs/{job_id}/subtitles', dependencies=[Depends(require_token)])
def video_subtitles(job_id: str):
    job = get_job_queue().get(job_id)
    if job is None: raise HTTPException(404,detail='Unknown video job')
    if job.status != 'complete' or job.output is None: raise HTTPException(409,detail='Dubbing not complete')
    path = job.output.with_suffix('.srt')
    if not path.is_file(): raise HTTPException(404,detail='Subtitles unavailable')
    return FileResponse(path,media_type='application/x-subrip',filename='NEXVARY-Dubbed.srt')


@app.post('/v1/dub/jobs/{job_id}/cancel', dependencies=[Depends(require_token)])
def video_cancel(job_id: str):
    if not get_job_queue().cancel(job_id): raise HTTPException(404,detail='Unknown video job')
    return {'cancel_requested':True}
