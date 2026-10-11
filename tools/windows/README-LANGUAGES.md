# NEXVARY Voice: Arabic, English, Italian, Russian, Spanish, Bengali

## Installation on an existing Windows 10/11 computer

No virtual Ubuntu machine and no new VPS are required for initial trials.
Run PowerShell **in the repository root**.

Prerequisites: Python **3.11 x64** including the Python Launcher (`py`),
Git, FFmpeg/ffprobe on PATH, a microphone and speakers/headphones.
The installer EXE is only the GUI; the AI engine runs separately.
These commands install packages and download model weights **only when you run them**.

### One-time setup

```powershell
git clone https://github.com/nexvary/NEXVARY-Voice.git
cd NEXVARY-Voice
powershell -ExecutionPolicy Bypass -File .\tools\windows\install.ps1
powershell -ExecutionPolicy Bypass -File .\tools\windows\setup-languages.ps1 -AcceptDownloads -WhisperModel base
```

The second command installs **ten Argos packages**: ar↔en, it↔en, ru↔en,
es↔en, bn↔en. English pivoting permits up to 30 translation directions,
but language-pair quality varies; loading multiple model packages can
increase memory use. Bengali is `bn`, not Hindi `hi`. `faster-whisper
base` supports all six target languages, but accuracy varies by accent
and recording quality. Use `-WhisperModel tiny` for a smaller/faster initial
trial or `small` for heavier ASR. Model downloads are one-time and may
need ample SSD space and network connectivity.

### Voice synthesis for translated microphone replies and dubbing

Review each voice's MODEL_CARD and license, then explicitly download
six Piper voices with:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\windows\download-voices.ps1 -AcceptDownloads
```

This downloads two required files (`.onnx` and `.onnx.json`) per voice,
plus its licensing MODEL_CARD, from
https://huggingface.co/rhasspy/piper-voices/tree/main .
For the six language choices it uses:

- ar_JO-kareem-medium
- en_US-lessac-medium
- it_IT-paola-medium
- ru_RU-irina-medium
- es_ES-davefx-medium
- bn_BD-google-medium

An `engine/voices.json` map of absolute local paths is generated,
and `tools/windows/start-engine.ps1` loads that mapping. These model
files and mappings are excluded from Git and should never be committed.

*Limitations:* Arabic Piper voice is Jordanian and Bengali voices may
have pronunciation/performance limitations on the specific Windows
setup. The existence of a model does **not** guarantee high-quality
dubbing or compatibility with every CPU. Review usage rights for each
individual model.

### Start the local voice engine

Open one PowerShell terminal in the same checkout and run:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\windows\start-engine.ps1
```

Keep that terminal open. Open another PowerShell terminal to verify:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

For a model-readiness report:

```powershell
cd engine
.\.venv\Scripts\python.exe -m voice_engine.model_status
cd ..
```

`translation_ready: true` verifies the **installed package list**,
not translation quality. `piper_ready: true` verifies ONNX/config file
presence, not real speech output. Test real audio and an actual 10–20 s
video before depending on the project.

In the Windows GUI, open **Settings**, put
`http://127.0.0.1:8000` in the server field, and press the connection
test. Then test two-way text translation before the microphone feature.

### Fix common problems

- **503**: missing language model or Piper voice, or the worker is absent.
  Run `python -m voice_engine.model_status` and inspect the server terminal.
- **No voice output**: check ONNX + corresponding ONNX.JSON, the installed
  Piper executable, and the output audio device.
- **No server connection**: keep the PowerShell engine window open,
  and use localhost rather than the Ubuntu gateway until inference is ready.
- **Slow translation**: start with Whisper `tiny` or `base`,
  speak one sentence at a time, use headphones, and avoid running video
  dubbing simultaneously. The live protocol buffers 3.2 seconds before
  ASR, so there is inherent delay even on a fast computer.
- **FFmpeg not found**: install the trusted FFmpeg binary, then reopen
  PowerShell so PATH is refreshed.

No script in this setup opens network ports to the internet or changes
Nginx, Docker containers or your Ubuntu server. Only an explicit
second-stage network deployment would change that.
