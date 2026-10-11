# Delivery milestones

- [x] Foundation: public source repository, versioned Python API, explicit Argos model handling, unit/API tests, Android app scaffold, GitHub Actions.
- [x] v0.2 premium Compose multi-screen Arabic RTL interface with conversation, studio, connectivity and genuine SRT export.
- [x] Isolated Ubuntu Docker Compose manifests with loopback port binding and preflight; actual server deployment is not performed.
- [x] Push-to-talk Android text capture -> server translation -> system TTS with source/target swap.
- [x] Text-turn WebSocket protocol for future live mode; clearly marked non-audio.
- [x] SRT translation tool + existing translated-audio mux tool.
- [ ] Run Android on physical Oppo/other device, verify mic permissions, Hindi/Arabic TTS voices and Bluetooth selection.
- [ ] Install/evaluate real model packages and Hindi<->Arabic via English, including translation-quality evaluation.
- [ ] Secure remote pairing (QR, user consent, per-session auth), privacy controls and encrypted WebRTC audio.
- [ ] Genuine streaming ASR / VAD / MT / low-latency TTS with latency and interruption benchmarks.
- [ ] Windows audio capture, virtual mic routing for OBS/live apps, closed-loop echo prevention.
- [ ] Video ASR + TTS + alignment with audible final export; voice identity controls.
- [ ] UI polish, instrumentation tests, hardware lab, app signing, signed releases.

**Release criteria:** no false "instant" claim; paired-device A/B tests; authenticated transport; failure UX; full license/model asset inventory; CI green; documented offline/online limits.
