# Technical architecture

## MVP data flow

1. Android microphone -> Android SpeechRecognizer (device/system service, may require internet).
2. Recognized text -> `POST /v1/translate` with source and target BCP-47 language tags.
3. Python validates and normalizes language codes; Argos translates through explicitly installed model packages, failing closed when missing.
4. Android presents original and translated text, then Android TextToSpeech reads the target language through the OS-selected output (phone or paired Bluetooth earbuds).
5. "Swap" button reverses the two participants' languages. This is turn-taking, **not** speaker diarization or simultaneous bidirectional translation.

Engine has no hard-coded provider credentials. Per-turn text is processed in memory; requests are not stored in a database. There is no local offline speech recognition guarantee: the device controls Android speech availability.

## Real-time broadcasting (foundation only)

`/v1/live/text` accepts JSON text turns over WebSocket and sends translations. It is not a microphone/audio stream. Planned system: AudioCapture -> VAD/streaming ASR -> incremental MT -> streaming TTS -> buffer/clock sync -> OBS/virtual microphone. On Windows use a supported virtual audio device and explicit user-selected routing; Android cannot universally replace other apps' microphone streams. Record separate tracks for retransmission and editing.

## Video dubbing (foundation only)

`python -m voice_engine.subtitles` translates an existing SRT, keeping timestamps. `video_mux` attaches an already-prepared audio file to video. Planned next: audio separation -> multilingual ASR -> sentence timestamps -> edit/approve text -> MT -> synthetic voice -> align duration -> mux -> review. Voice cloning requires explicit consent and licensing review.

## Windows architecture

Plan: Kotlin Multiplatform client or Qt desktop UI (decision pending benchmarking) + the same HTTP/WebSocket API. Prefer Qt/Python for MVP because Python engine and FFmpeg audio pipeline already exist. Add WASAPI capture, device selection, loopback guard, audio-meter, segment cache, OBS integration. No Windows installer or Windows binary in v0.1.0.

## Validation boundary

FastAPI unit/API/WebSocket tests use **fake, deterministically labeled** translation only within tests. They do not prove AI translation model accuracy, end-to-end audio, live latency, or Android device compatibility. CI also compiles Android and runs JVM unit tests. Audio tests require physical devices, Bluetooth pairing, and representative noise/accent scenarios.
