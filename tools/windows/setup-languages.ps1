# NEXVARY Voice: explicitly download translation and ASR models for six languages.
param([switch]$AcceptDownloads, [ValidateSet('tiny','base','small')][string]$WhisperModel = 'base', [switch]$SkipWhisper)
$ErrorActionPreference = 'Stop'
if (-not $AcceptDownloads) { throw "Read README-LANGUAGES.md then re-run with -AcceptDownloads." }
$project = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$engine = Join-Path $project 'engine'
$python = Join-Path $engine '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { throw "First run tools/windows/install.ps1 to create the Python 3.11 environment." }
Push-Location $engine
try {
    # Two directions for every non-English language, English as pivot.
    foreach ($code in @('ar', 'it', 'ru', 'es', 'bn')) {
        foreach ($pair in @(@($code, 'en'), @('en', $code))) {
            Write-Host ("Downloading Argos {0} -> {1}" -f $pair[0], $pair[1]) -ForegroundColor Cyan
            & $python -m voice_engine.install_models --source $pair[0] --target $pair[1] --accept-download
            if ($LASTEXITCODE -ne 0) { throw ("Argos installation failed: {0}->{1}" -f $pair[0], $pair[1]) }
        }
    }
    if (-not $SkipWhisper) {
        Write-Host "Caching multilingual faster-whisper $WhisperModel for CPU..." -ForegroundColor Cyan
        & $python -c "from faster_whisper import WhisperModel; WhisperModel('$WhisperModel', device='cpu', compute_type='int8', local_files_only=False); print('Whisper cached successfully')"
        if ($LASTEXITCODE -ne 0) { throw "Whisper installation failed" }
    }
    & $python -m voice_engine.model_status
    if ($LASTEXITCODE -ne 0) { throw "Status check failed" }
    Write-Host "Translation models installed. Piper voices are separate; see README-LANGUAGES.md." -ForegroundColor Green
} finally { Pop-Location }
