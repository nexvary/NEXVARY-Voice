# NEXVARY Voice 0.3 audio workflows

## Capability matrix — distinguish working code from end-to-end evidence

| Workflow | Implemented in source | Physical/device validation |
| --- | --- | --- |
| Android bilingual turns with OS SpeechRecognizer | Yes | Required |
| Android 16 kHz PCM WebSocket microphone + audio playback | Yes | Required |
| Ubuntu CPU ASR+Argos+Piper segmented interpreter | Yes | Requires separately installed voices and models |
| Windows mic + translated speaker output | Yes; source-based CLI or Tkinter | Required on Windows 10 and BT headset |
| Video MP4 -> ASR -> translation -> translated TTS audio -> MP4+SRT | Yes | Synthetic FFmpeg E2E test; real multi-language content validation needed |
| Automatic voice cloning / speaker diarization | No | Not implemented |
| Direct Android microphone replacement in other apps | No | OS restriction |
| Windows OBS broadcast routing | OBS/application-capture workflow possible; built-in virtual microphone not implemented | Required |
| Two-phone QR pairing | No | Planned |
| Signed Android release / Windows installer | No | Planned |

## Recorded-video dubbing (from engine directory)

Install prerequisites, FFmpeg, ffprobe and language models. Models must be installed explicitly.

```powershell
python -m pip install -e ".[offline,speech,dev]"
python -m voice_engine.install_models --source ar --target en --accept-download
# Install Whisper model in cache explicitly (requires internet once):
python -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8', local_files_only=False)"
# Download a compatible Piper ONNX + ONNX.JSON voice separately, after license review.
python -m voice_engine.dubbing product.mp4 product-en.mp4 --source ar --target en --whisper-model small --piper-model C:\\voices\\en_US.onnx
```

The output contains translated spoken audio and an SRT file. The TTS is a
**different voice**, not cloning your original voice. Subtitle and audio durations
may need final editorial adjustment if the translated speech is longer than the
original phrase. The original voice audio track is replaced; there is no automatic
music/speech source separation in this version.

### Online English speech option

Install `pip install -e ".[offline,speech,cloud]"` and use
`--tts edge --voice en-US-JennyNeural --allow-cloud-tts`. This sends translated
text to an online speech service; provider availability and terms may change.
Do not use with confidential scripts without appropriate permission.

## Real translated-audio streaming

The new endpoint `wss://example.com/v1/live/audio` requires bearer-token
authentication when `NEXVARY_API_TOKEN` is set.

1. Send handshake JSON: `{"source_language":"hi","target_language":"ar","format":"pcm_s16le","sample_rate":16000}`.
2. Send binary little-endian signed PCM16, mono, 16000 Hz frames (maximum 32000 bytes/frame).
3. Server accumulates 102400 bytes (3.2 seconds), runs Whisper, MT, Piper voice.
4. Server sends JSON `{"type":"translated", "original_text":"...", "translated_text":"...", "pcm_bytes":N}` then N raw PCM16 bytes, 16 kHz mono.
5. Client plays that audio to the selected sound device and suppresses microphone sending while output is playing.

Text is not stored by the API. Audio is processed within a temporary directory
removed after each turn. **Latency is >3.2 seconds plus model inference**.
Do not promise instantaneous translation.

## Windows installer helper

On Windows 10/11, from the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\windows\install.ps1
powershell -ExecutionPolicy Bypass -File .\tools\windows\launch.ps1
```

These scripts create a dedicated Python 3.11 virtual environment under the
repository and start the native Tkinter desktop program. They do **not**
install virtual audio drivers, models or a system-wide service. Always inspect
downloaded scripts before execution.

## Desktop client

```powershell
pip install -e ".[offline,speech,desktop,dev]"
python -m voice_engine.desktop_gui
```

Select the secure server address, source/target, then microphone mode.
For CLI microphone mode:

```powershell
$env:NEXVARY_API_TOKEN="your-secret"
python -m voice_engine.live_client --url wss://your-server/v1/live/audio --source ar --target en
```

On the same machine only for development:
`--url ws://127.0.0.1:8000/v1/live/audio --allow-insecure-localhost`.

OBS can capture the translated playback via supported application audio capture
or a user-installed virtual loopback device. The application **does not itself
install or create a virtual microphone**.

## Ubuntu service

See [Ubuntu deployment](../deploy/ubuntu/README.md). The Docker service only
binds 127.0.0.1:18781 on the host. It is not remotely accessible without a
separately secured TLS reverse proxy. No server changes have been made for the user.

## Validation

CI tests all Python APIs on Ubuntu and Windows, Kotlin/Android assemble and
unit tests, and Docker Compose schema. An FFmpeg synthetic-media integration test
runs where FFmpeg is available. End-to-end tests with real models, accents,
background noise, Bluetooth, phones and latency are outstanding.
