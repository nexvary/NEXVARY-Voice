# Start only localhost inference on Windows. No Windows firewall changes.
param([ValidateRange(1024,65535)][int]$Port = 8000)
$ErrorActionPreference = 'Stop'
$project = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$engine = Join-Path $project 'engine'
$python = Join-Path $engine '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { throw "Run tools/windows/install.ps1 first." }
$mapping = Join-Path $engine 'voices.json'
if (Test-Path $mapping) {
    $text = Get-Content $mapping -Raw -Encoding UTF8
    $obj = ConvertFrom-Json $text
    foreach ($code in @('ar','en','it','ru','es','bn')) {
        $voice = $obj.$code
        if ($voice -and -not (Test-Path $voice)) { throw "Missing Piper model for $code : $voice" }
        if ($voice -and -not (Test-Path ($voice + '.json'))) { throw "Missing Piper config for $code : $voice" }
    }
    $env:NEXVARY_PIPER_VOICES = $text
    Write-Host "Loaded six-language Piper voice mapping." -ForegroundColor Green
} else {
    Write-Warning "engine/voices.json is absent: text translation may work, but audio reply/video jobs need licensed Piper voices."
}
$env:NEXVARY_WHISPER_MODEL = if ($env:NEXVARY_WHISPER_MODEL) { $env:NEXVARY_WHISPER_MODEL } else { 'base' }
$env:NEXVARY_ASR_DEVICE = 'cpu'
Write-Host "Local engine: http://127.0.0.1:$Port/health" -ForegroundColor Cyan
Write-Host "Keep this window open. Stop with Ctrl+C." -ForegroundColor Yellow
Push-Location $engine
try {
    & $python -m uvicorn voice_engine.api:app --host 127.0.0.1 --port $Port
    if ($LASTEXITCODE -ne 0) { throw "The translation engine exited with an error." }
} finally { Pop-Location }
