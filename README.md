# NEXVARY Voice

**Professional Android voice-translation studio with an isolated Ubuntu translation service.**

> Status: **v0.2 functional prototype**, not a finished simultaneous interpreter. Android now has a premium four-tab Material3 Compose Arabic RTL interface, turn-taking speech translation, voice preview, server connectivity tests, and SRT import/translation/export. Real translation requires separately installed Argos Translate language models. Video subtitle translation works when models are installed; automated speech replacement and live broadcast audio routing remain planned.

## Modules

| Module | Current implementation | Planned next |
| --- | --- | --- |
| Android interpreter | Premium Compose UI, typed or speech-recognized turns, direction swap, HTTPS translation API, system TTS | QR two-phone pairing, speaker diarization, local engine |
| Python translation engine | FastAPI text translation, Argos installed-model backend, explicit errors, optional token, WebSocket text-turn prototype | Streaming speech decoding, VAD, translation chunking |
| Live broadcast | Authenticated WebSocket **text** transport prototype | Audio capture, jitter buffer, multilingual TTS, OBS / virtual audio device integration |
| Recorded video | Android SRT import/translate/export, Python SRT subtitle translation CLI and existing-voice-track mux helper | ASR timestamps, per-speaker TTS, time alignment, quality checks |
| Windows | Design documented | GUI, OBS/virtual-audio adapter |

## Quick start (engine)

Requires Python 3.11+.

```sh
cd engine
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
uvicorn voice_engine.api:app --host 127.0.0.1 --port 8000
```

On Windows activate with `.venv\Scripts\activate` instead.

Models are *not bundled* and never downloaded automatically:

```sh
pip install argostranslate
python -m voice_engine.install_models --source ar --target en --accept-download
python -m voice_engine.install_models --source en --target hi --accept-download
```

Some language pairs require a pivot through English and installed models in **both directions** for a full bilingual conversation. Availability depends on Argos catalog coverage.

```sh
curl http://127.0.0.1:8000/health
curl -X POST http://127.0.0.1:8000/v1/translate -H "Content-Type: application/json" -d '{"text":"مرحبا","source_language":"ar","target_language":"en"}'
```

An unavailable pair responds with HTTP 503 and `model_unavailable` rather than fabricated text. When `NEXVARY_API_TOKEN` is set, add `Authorization: Bearer <token>` to API requests; enable HTTPS and authentication **before any network exposure**. Never expose a development HTTP server publicly.

## Ubuntu Docker deployment

Read [deploy/ubuntu/README.md](deploy/ubuntu/README.md). **No remote server installation has been performed**. Run the read-only preflight before deploying into any existing Ubuntu production machine.

## Android

Open `android/` in Android Studio with JDK 17 and Android SDK 35. Build with Gradle 8.9:

```sh
cd android
gradle :app:assembleDebug :app:testDebugUnitTest
```

The debug build permits cleartext for local Wi-Fi development only, and defaults to the Android emulator's host address `http://10.0.2.2:8000`. On a physical phone configure your **own** reachable HTTPS endpoint; Android release builds reject HTTP. The engine binds loopback by default. To connect across LAN requires an explicitly configured local bind, firewall rules, and appropriate authentication. Text entry still works if Android voice recognition is absent. Bluetooth output follows Android system routing; it is not yet a custom low-level Bluetooth controller.

## Other commands

```sh
cd engine
python -m pytest -q
python -m voice_engine.subtitles input.ar.srt output.en.srt --source ar --target en
python -m voice_engine.video_mux video.mp4 translated_audio.wav output.mp4
```

The last command **only** combines audio already produced elsewhere. It does not claim to synthesize translated speech.

## Architecture, security and product roadmap

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/ROADMAP.md](docs/ROADMAP.md), and [docs/SECURITY.md](docs/SECURITY.md).

## Current scope

Production-ready simultaneous speech streaming, automatic voice dubbing of arbitrary videos, and Windows virtual-microphone routing **are not yet implemented**. A successful APK build does not establish low-latency translation quality. The backend needs language packs and HTTPS when accessed across the internet.

## License

No license grant has been selected yet. Third-party models and software have their own licenses; verify their compatibility before distributing. Do not interpret the repository's public visibility as an open-source license grant.
