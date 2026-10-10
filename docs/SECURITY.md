# Security & privacy

- Python server binds to `127.0.0.1` by default. Bind to `0.0.0.0` only on a trusted lab network after enabling bearer auth and network restrictions. Always use TLS for access from outside the device; never expose plain HTTP/TTS streams over the internet.
- Configure `NEXVARY_API_TOKEN` using environment variables / secret manager, never commit credentials. This is an initial shared-key mechanism, **not** multi-user session auth.
- Android release builds disallow cleartext HTTP. Debug builds allow it for local development only.
- Android speech recognition may send audio to the OS service/provider. Do not describe it as offline or private by default.
- No transcript persistence is implemented. Future telemetry must avoid plaintext audio/transcripts without consent and retention settings.
- Reused/transformed voice identities require permission; document applicable model and voice licenses.
- WebSocket text prototype has basic size validation but no production-ready rate limiting, quota, anti-abuse controls, or per-room authorization.
- Never upload real user voice recordings to GitHub issues, CI artifacts, or a public repository.
