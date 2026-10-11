# Delivery milestones

- [x] Added isolated 1 GiB-host lightweight gateway with authenticated HTTP/WebSocket forwarding, bounded MP4 relay, Docker Compose and CI tests. It **does not** perform AI inference locally.
- [ ] Connect a separate trusted speech-inference worker and benchmark the actual Arabic/Hindi conversion on real microphones.

- [x] Foundation: public source repository, versioned Python API, explicit Argos model handling, unit/API tests, Android app scaffold, GitHub Actions.
- [x] v0.2 premium Compose multi-screen Arabic RTL interface with conversation, studio, connectivity and genuine SRT export.
- [x] Isolated Ubuntu Docker Compose manifests with loopback port binding and preflight; actual server deployment is not performed.
- [x] Push-to-talk Android text capture -> server translation -> system TTS with source/target swap.
- [x] Text-turn WebSocket protocol for future live mode; clearly marked non-audio.
- [x] SRT translation tool + existing translated-audio mux tool.
- [ ] Run Android on physical Oppo/other device, verify mic permissions, Hindi/Arabic TTS voices and Bluetooth selection.
- [ ] Install/evaluate real model packages and Hindi<->Arabic via English, including translation-quality evaluation.
- [ ] Secure remote pairing (QR, user consent, per-session auth), privacy controls and encrypted WebRTC audio.
- [x] Segmented microphone PCM16 WebSocket -> ASR/MT/TTS pipeline (3.2-second turns); model and phone latency still unverified.\n- [ ] True streaming low-latency ASR/VAD/MT/TTS, interruption benchmarks and overlapping-speaker handling.
- [x] Windows mic streaming client and source-based Tkinter GUI, including playback-to-mic loop suppression.\n- [ ] Windows virtual-mic/OBS integration, full audio-device picker, and signed installer.
- [x] Video ASR + MT + TTS + actual MP4 audio mux and SRT, with synthetic FFmpeg validation.\n- [ ] Editorial speech-duration alignment, background music retention, multi-speaker voices and voice identity consent workflow.
- [ ] UI polish, instrumentation tests, hardware lab, app signing, signed releases.

**Release criteria:** no false "instant" claim; paired-device A/B tests; authenticated transport; failure UX; full license/model asset inventory; CI green; documented offline/online limits.
