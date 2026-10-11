# NEXVARY Voice

**Professional Android voice-translation studio with an isolated Ubuntu translation service.**

> Status: **v0.3 audio-capable development release**, not a finished simultaneous interpreter. Android now has a premium four-tab Material3 Compose Arabic RTL interface, turn-taking speech translation, voice preview, server connectivity tests, and SRT import/translation/export. Real translation requires separately installed Argos Translate language models. Recorded-video translated-speech dubbing and segmented WebSocket speech turns now have executable implementations. These require manually installed ASR/translation/TTS models, and have not been validated on real multilingual production footage or physical two-phone hardware.

## Modules

| Module | Current implementation | Planned next |
| --- | --- | --- |
| Android interpreter | Premium Compose UI, typed or speech-recognized turns, direction swap, HTTPS translation API, system TTS | QR two-phone pairing, speaker diarization, local engine |
| Python translation engine | FastAPI text translation, Argos installed-model backend, explicit errors, optional token, text and segmented PCM16 audio WebSocket with optional Whisper ASR + Piper speech output | Latency optimization, model benchmarking |
| Live broadcast | Android microphone PCM16 transport, desktop microphone client and half-duplex translated TTS | Faster streaming, OBS virtual-mic adapter and low latency |
| Recorded video | Android SRT import/export; offline Whisper/Argos/Piper (or opt-in Edge online) auto-dubbing to MP4+SRT | Speaker diarization, voice cloning with consent, quality alignment |
| Windows | Working Tkinter Voice Studio GUI and microphone client source | Installer and OBS virtual-mic driver integration |

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

## Lightweight control-plane gateway for resource-constrained Ubuntu

For existing Ubuntu systems with about 1 GiB RAM, **do not run the full speech-model container**. A separate, non-inference gateway is now available with its own Dockerfile and Compose project, at a localhost-only port (default 18782). It forwards requests to a separate authenticated HTTPS inference worker **only after you configure that worker**; otherwise translation correctly returns HTTP 503. No model files are downloaded and existing FG MTM/Outline/Nginx services are not modified.

See [lightweight gateway deployment](docs/GATEWAY_DEPLOYMENT.md). No deployment on the user's Ubuntu host has been performed.

## Ubuntu Docker deployment

Read [deploy/ubuntu/README.md](deploy/ubuntu/README.md). **No remote server installation has been performed**. Run the read-only preflight before deploying into any existing Ubuntu production machine.

## Android

Open `android/` in Android Studio with JDK 17 and Android SDK 35. Build with Gradle 8.9:

```sh
cd android
gradle :app:assembleDebug :app:testDebugUnitTest
```

The debug build permits cleartext for local Wi-Fi development only, and defaults to the Android emulator's host address `http://10.0.2.2:8000`. On a physical phone configure your **own** reachable HTTPS endpoint; Android release builds reject HTTP. The engine binds loopback by default. To connect across LAN requires an explicitly configured local bind, firewall rules, and appropriate authentication. Text entry still works if Android voice recognition is absent. Bluetooth output follows Android system routing; it is not yet a custom low-level Bluetooth controller.

For complete microphone and full-video commands see [Audio workflows](docs/AUDIO_WORKFLOWS.md).\n\n## Other commands

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

Segmented speech translation and automatic dubbed MP4 generation are implemented but need model setup and real-content validation; simultaneous zero-delay conversation and Windows virtual microphone injection are **not** implemented. A successful APK build does not establish low-latency translation quality or Bluetooth headset compatibility. The backend needs language packs and HTTPS when accessed across the internet.

## License

No license grant has been selected yet. Third-party models and software have their own licenses; verify their compatibility before distributing. Do not interpret the repository's public visibility as an open-source license grant.
