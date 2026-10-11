# Private Ubuntu deployment — NEXVARY Voice

**Never run this deployment blindly on a server hosting other applications.** Perform a read-only preflight first. The app has an isolated Docker Compose project and defaults to **loopback only** at port 18781. It does not change existing Nginx, SSH, firewall, DNS, certificates or existing containers.

## 1. Preflight (no changes)

```bash
bash deploy/ubuntu/preflight.sh
```

Confirm port 18781 is unused, enough free space/RAM exists, and Docker Compose is installed. Argos models may need gigabytes of RAM/disk (depending on languages). Do not expose this service on a public IP.

## 2. Install as separate project

```bash
git clone https://github.com/nexvary/NEXVARY-Voice.git
cd NEXVARY-Voice/deploy/ubuntu
cp .env.example .env
# Replace placeholder with a random 32+ character token (e.g. openssl rand -hex 32)
chmod 600 .env
docker compose --env-file .env up -d --build
curl --fail http://127.0.0.1:18781/health
```

For models, add one pair at a time; this writes only to the dedicated Docker named model volume, **not** other services:

```bash
docker compose --env-file .env run --rm --user 0 --entrypoint python voice-engine -m voice_engine.install_models --source ar --target en --accept-download
docker compose --env-file .env run --rm --user 0 --entrypoint python voice-engine -m voice_engine.install_models --source en --target ar --accept-download
docker compose --env-file .env run --rm --user 0 --entrypoint python voice-engine -m voice_engine.install_models --source hi --target en --accept-download
docker compose --env-file .env run --rm --user 0 --entrypoint python voice-engine -m voice_engine.install_models --source en --target hi --accept-download
docker compose --env-file .env restart voice-engine
```

Language coverage depends on published Argos packages and installed pair direction. There is no claim that every pair will work.

## 3. Connect phones safely

For a real Android phone, use a trusted TLS reverse proxy for a domain/subdomain **after checking current Nginx routing and certificates**, or a private VPN/tunnel with correctly configured HTTPS. There is deliberately **no Nginx auto-install**. Android release clients reject cleartext HTTP. Never paste the token into a video or issue. In the app's Settings set the HTTPS endpoint and bearer token. The temporary token field is not persisted.

The service's port binding is `127.0.0.1:18781:8000` so it is **not directly reachable remotely** by design. Public access should additionally have a reverse proxy with TLS, per-client authentication, rate limits, and monitoring; bearer authentication alone is MVP-only.

## 4. Commands

```bash
docker compose --env-file .env ps
docker compose --env-file .env logs --tail=100 voice-engine
docker compose --env-file .env down
```

The `down` command stops **only** containers belonging to the `nexvary-voice` project; do not use `down -v` unless you intentionally want to delete stored models. Do not change unrelated workloads.

## 5. Audio interpreter models (v0.3)

The engine now accepts microphone PCM16 via authenticated WebSocket `/v1/live/audio`.
It processes 3.2-second turns (plus inference/TTS latency), returns JSON and
raw PCM16 speech; it is **not** low-latency simultaneous or overlapping-speaker
interpretation. The Docker image includes optional speech dependencies and FFmpeg,
but **does not bundle pretrained ASR, Argos, or voice weights**.

Before starting, initialize the *dedicated* model volume (no other volume is touched):
```bash
docker compose --env-file .env run --rm --user 0 --entrypoint sh voice-engine -c 'mkdir -p /models/argos /models/voices /models/huggingface /models/cache && chown -R 10001:10001 /models'
```

Install speech recognition model **with explicit download intent**:
```bash
docker compose --env-file .env run --rm --entrypoint python voice-engine -c 'from faster_whisper import WhisperModel; WhisperModel("small", device="cpu", compute_type="int8", local_files_only=False)'
```

Download compatible Piper ONNX voices and their matching `.onnx.json` configs
from the provider (check availability/license per language), then copy them into
`/models/voices` inside the dedicated volume. Do not point configuration to files
that do not exist. Voice languages are not guaranteed by the bundled image.
The source/target Argos models must also be installed. Set
`NEXVARY_PIPER_VOICES` in `.env` as compact JSON keyed by ISO language code.

To inspect just this application's model volume:
```bash
docker compose --env-file .env run --rm --entrypoint ls voice-engine -lah /models/voices
```

HTTPS reverse-proxy must support WebSocket `Upgrade` headers. Keep container bound
to 127.0.0.1, and add an authenticated TLS route using your **existing** Nginx
configuration only after verifying that it will not interfere with other sites.
Never post API tokens, recordings, transcripts, or private voice models to GitHub.

## 6. Video dubbing

Local Windows/Ubuntu: `python -m voice_engine.dubbing` provides full
ASR -> translation -> new TTS speech -> MP4 + SRT for videos up to 30 minutes.
This offline workflow needs `ffmpeg`, `ffprobe`, language models, and a Piper
model for the output language. Add `--tts edge --allow-cloud-tts` only if you
agree to sending translated text to an online TTS provider. Details in
`docs/AUDIO_WORKFLOWS.md`.
