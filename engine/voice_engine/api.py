"""HTTP and text-WebSocket API. Audio streaming is not implemented in this release."""
from __future__ import annotations

import hmac
import json
import os
from functools import lru_cache

from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field, field_validator

from .translator import ArgosTranslator, TranslationUnavailable, Translator

app = FastAPI(title="NEXVARY Voice Engine", version="0.1.0", docs_url="/docs")

LANGUAGES = {
    "ar": "Arabic", "en": "English", "hi": "Hindi", "tr": "Turkish",
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
    return {"status": "ok", "component": "voice-engine", "audio_streaming": False}


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
