# 0.6.2 — Shorter speech turns and local audio check

Windows voice capture ends a turn after 400 ms of low-energy audio, up to the existing 3.2-second maximum. Quiet input does not trigger requests. The detector uses PCM energy, not linguistic VAD: background noise can delay endpoints and pauses can split sentences. Model quality is unchanged.

Only one Windows voice turn is in flight. Capture pauses during processing and playback, avoiding queued stale speech. The engine acknowledges silent or empty recognition so capture resumes. A 90-second timeout ends stalled sessions.

The audio page includes explicit local-only three-second microphone recording and playback through the chosen devices. Audio stays in memory and is not sent or saved. Silence, overflow and underrun are detected; the user must confirm audibility. Physical testing remains required on the user's PC.

Elapsed response timing supplements per-stage metrics. This is not zero-delay interpretation. Update the private engine using the setup wizard before using the new client, then restart it. Healthy models and compatible dependencies are reused.

Automated tests cover quiet input, onset retention, short and long turns, pauses, reset, minimum duration, and empty-recognition acknowledgements. CI also runs frozen EXE/setup checks and real ASR/translation/TTS/video pipelines. Physical mic/speaker success cannot be inferred from CI.
