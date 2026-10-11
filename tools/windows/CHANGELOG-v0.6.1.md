# 0.6.1 — Conversation performance

- Keep four bounded INT8 Argos models for bidirectional English pivoting, retaining decoding quality.
- Reuse up to four SentencePiece processors; invalidate by size and modification timestamp.
- Keep two Piper voices for alternating conversation turns, instead of reloading on every direction change.
- Resample synthesized live replies inside installed PyAV instead of launching FFmpeg for every speech turn. Video processing still uses FFmpeg.
- Record ASR, translation, TTS and PCM conversion times separately. Show total text translation time in Windows.
- Windows real-model CI records repeated bidirectional translation and audio stage timings. Measurements on CI hardware are not promises about user hardware.
- Retain three-point-two-second microphone segments and existing Whisper/translation decoding settings. First model use may still take longer than subsequent turns.
