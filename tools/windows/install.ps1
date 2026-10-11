# NEXVARY Voice Studio - Windows 10/11 installation (run in PowerShell).
# Does not install system services, firewall rules, or drivers.
$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..\..\engine')
if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "Python Launcher missing. Install Python 3.11 x64 from python.org and retry."
}
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Warning "FFmpeg not found in PATH. Full video dubbing requires ffmpeg + ffprobe."
}
if (-not (Test-Path '.venv')) {
    & py -3.11 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "Python 3.11 virtual environment failed" }
}
$exe = Join-Path (Get-Location) '.venv\Scripts\python.exe'
& $exe -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed" }
& $exe -m pip install -e ".[offline,speech,desktop,dev]"
if ($LASTEXITCODE -ne 0) { throw "Required packages failed. Inspect pip output." }
Write-Host "NEXVARY Voice installed. Model weights are NOT downloaded automatically." -ForegroundColor Green
Write-Host "Run: .\launch.ps1 (from tools\windows)" -ForegroundColor Cyan
