# NEXVARY Voice Studio — Windows graphical application

Version 0.4.0 is a full PySide6 graphical application packaged as an EXE and an Inno Setup installer for Windows 10/11 x64.

The interface offers five working pages: home, two-way text interpretation, microphone speech translation, MP4 dubbing uploads, and server configuration. The microphone mode sends PCM16 WebSocket chunks to an actual speech worker; it is NOT simultaneous zero-latency translation or virtual microphone injection. Dubbing uploads an MP4 to the existing video job API; models must be installed on the connected inference worker.

## Download and install

Open the latest successful GitHub Actions run:
https://github.com/nexvary/NEXVARY-Voice/actions

Download artifact NEXVARY-Voice-Windows-Setup, extract the ZIP, and run NEXVARY-Voice-Setup-v0.4.0.exe.

The Windows Portable artifact contains the whole unpacked application directory. Do not move the EXE outside that directory because the bundled Qt DLLs in _internal are necessary.

The build is unsigned, so Windows SmartScreen may display a warning. Inspect the source, CI checks and SHA-256 checksums. The installer creates a per-user installation without requiring Python, system services, firewall changes or audio drivers.

## Connect to a speech engine

In Settings use https://your-private-host or http://127.0.0.1:8000 for a local engine. The lightweight Ubuntu gateway alone cannot run AI inference: connect it to a separate worker first.

The EXE intentionally does not bundle multi-gigabyte model weights. It does bundle its Windows graphical libraries and desktop microphone transport. No secrets are stored, no voice files are written into the installer, and no automatic model downloads occur.

## Optional local inference on Windows

From the repo checkout:
- Run tools/windows/install.ps1 with PowerShell and Python 3.11 installed
- Install your own Argos, Whisper, and Piper voice models after reviewing licenses
- Run the engine in the engine directory with its virtual environment Python:
  .venv/Scripts/python.exe -m uvicorn voice_engine.api:app --host 127.0.0.1 --port 8000

## Reproduce

Install Python 3.11, packages from engine[desktop,dev], PyInstaller, and Pillow. Generate the ICO using tools/windows/make_icon.py, then build PyInstaller --onedir --windowed and compile tools/windows/NEXVARY-Voice.iss with Inno Setup 6. GitHub Actions automates unit tests, Qt offscreen UI checks, EXE launch tests, installer packaging, and SHA-256.
