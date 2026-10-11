# Run NEXVARY Voice Windows desktop GUI.
$ErrorActionPreference = 'Stop'
$exe = Join-Path $PSScriptRoot '..\..\engine\.venv\Scripts\python.exe'
if (-not (Test-Path $exe)) {
    throw "Run tools\windows\install.ps1 first."
}
& $exe -m voice_engine.desktop_gui
exit $LASTEXITCODE
