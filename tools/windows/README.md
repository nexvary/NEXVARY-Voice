# NEXVARY Voice Studio — Windows 0.5.0

## Automatic first-run assistant: no command line for users

When opening the Windows GUI the first time, a read-only compatibility
audit runs automatically. It checks:

- CPU, logical cores, physical RAM and free SSD space
- Microphone and output audio devices
- Presence of FFmpeg **and** FFprobe
- Managed private Python 3.11 inference runtime
- Installed Argos translation models for 6 languages, cached Whisper base
  and licensed Piper voice model+JSON files

Use the large **تجهيز جميع المكونات تلقائيًا** button to download and
install missing components after reading the confirmation. You can also
selectively install/repair one component and re-run the device scan.
Progress and errors are displayed **inside** the program, not in PowerShell.

### How it works

The installer bundles the [Astral uv](https://docs.astral.sh/uv/) executable
and the NEXVARY inference engine source code. With explicit approval,
the setup assistant installs its own Python 3.11 environment under
`%LOCALAPPDATA%\NEXVARY\Voice`, then installs AI dependencies and downloads
Argos, Whisper and Piper models using HTTPS. FFmpeg/FFprobe are downloaded
separately and kept under the same app-owned folder.

It does not change global Python, drivers, user PATH, firewall, Nginx or your
Ubuntu server. Audio and translation stay local when you start localhost
inference, unless you select a remote server in Settings.
A read-only scan never downloads or changes files.

### Finishing setup

Press **تشغيل محرك الترجمة محليًا** in the assistant, return to Settings,
verify that the endpoint is `http://127.0.0.1:8000`, and press
**اختبار الاتصال**. A successful health check means the service responds;
test actual text, microphone audio and a short video to verify the models.

The program shows explicit errors for inaccessible downloads or unsupported
dependencies. Setup can be stopped and resumed; previously verified model
files are preserved. Whisper model files, Argos packages and voice models are
*not* bundled in the Setup installer.

### Limitations

- Windows 10/11 x64. Requires Internet and several gigabytes of free SSD
  to prepare all six languages. 4GB+ RAM for initial trials, 8GB+ preferable.
- Six Piper voice licenses and model cards should be reviewed for intended use.
- Streaming is chunk-based (3.2 seconds plus inference), **not** simultaneous
  zero-delay translation or OBS virtual microphone replacement.
- Actual voice speed, Windows audio drivers and model reliability are not
  guaranteed by CI unit tests alone.
- EXE installer is unsigned; SmartScreen may warn.

### Developer / QA

Open the successful Windows Desktop Release Build on
https://github.com/nexvary/NEXVARY-Voice/actions and download
`NEXVARY-Voice-Windows-Setup`, extract it and run
`NEXVARY-Voice-Setup-v0.5.0.exe`.
Portable ZIP must keep all `_internal` libraries.

GitHub Actions tests the Python audit/config/download integrity logic,
Windows Qt offscreen GUI initialization, frozen EXE startup, bundled uv binary,
packaged inference source and Inno Setup installer.

No live model downloads are performed in GitHub CI.
