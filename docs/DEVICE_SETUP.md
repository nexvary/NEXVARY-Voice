# Windows first-run detection and installation

This replaces the former command-line-only setup with a guided graphical
experience. The wizard opens automatically on first launch and can be
reopened from the Home, Settings or navigation panel.

1. **Audit (no changes):** CPU, RAM, SSD, microphone/speakers, FFmpeg,
   local private Python runtime, installed Argos packs, Whisper cached model,
   and configured Piper voices.
2. **Explicit approval:** One-click install or individual repair buttons.
   Confirmation discloses sources, storage/network requirements, voice licenses.
3. **Private Python:** bundled uv.exe manages Python 3.11 in LocalAppData;
   installs the matching NEXVARY Python engine packaged in the installer.
4. **Models:** translation packages English↔(Arabic, Italian, Russian,
   Spanish, Bengali), faster-whisper base, model+config+MODEL_CARD for six
   Piper voices, verified against official upstream manifest.
5. **Video:** FFmpeg and FFprobe downloaded separately, unzipping only the
   two expected executables with bounded archive and entry sizes.
6. **Start localhost:** explicitly launch the model service listening
   only on 127.0.0.1:8000; use the existing Windows GUI to test translations.

Nothing is downloaded during the audit. Never open public firewall
ports automatically. The installer remains unsigned and uses online
dependencies; users should verify provenance and licenses.

## Limits and open testing

CI checks source syntax and GUI bootstrap without actual multi-gigabyte
downloads. Real voice initialization, dependency wheels for a specific
Windows CPU, Bluetooth routing, runtime performance and voice license
compliance require testing on the end-user computer. The wizard must
report failures rather than claiming a complete installation.
