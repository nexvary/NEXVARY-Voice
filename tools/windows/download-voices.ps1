# Download 6 selected OFFLINE Piper TTS voices from the public upstream model registry.
# Downloads model, JSON config and MODEL_CARD for each. No secrets or system modifications.
param([switch]$AcceptDownloads)
$ErrorActionPreference = 'Stop'
if (-not $AcceptDownloads) {
    throw "Review Piper voice licenses on https://huggingface.co/rhasspy/piper-voices/tree/main ; then run with -AcceptDownloads."
}
$project = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$engine = Join-Path $project 'engine'
$folder = Join-Path $engine 'models\voices'
New-Item -ItemType Directory -Force -Path $folder | Out-Null
$voices = @(
    @('ar', 'ar_JO', 'kareem', 'medium'),
    @('en', 'en_US', 'lessac', 'medium'),
    @('it', 'it_IT', 'paola', 'medium'),
    @('ru', 'ru_RU', 'irina', 'medium'),
    @('es', 'es_ES', 'davefx', 'medium'),
    @('bn', 'bn_BD', 'google', 'medium')
)
$mapping = @{}
foreach ($voice in $voices) {
    $language, $locale, $speaker, $quality = $voice
    $name = "$locale-$speaker-$quality"
    $path = Join-Path $folder $language
    New-Item -ItemType Directory -Force -Path $path | Out-Null
    $uri = "https://huggingface.co/rhasspy/piper-voices/resolve/main/$language/$locale/$speaker/$quality"
    foreach ($file in @("$name.onnx", "$name.onnx.json", "MODEL_CARD")) {
        $targetName = if ($file -eq 'MODEL_CARD') { "MODEL_CARD-$language.txt" } else { $file }
        $output = Join-Path $path $targetName
        if (-not (Test-Path $output)) {
            $partial = $output + '.partial'
            try {
                Invoke-WebRequest -Uri "$uri/$file" -OutFile $partial -MaximumRedirection 10 -UseBasicParsing
                if ($file.EndsWith('.onnx') -and (Get-Item $partial).Length -lt 1MB) {
                    throw "Voice model download too small: $name"
                }
                if ($file.EndsWith('.json')) {
                    $null = Get-Content -LiteralPath $partial -Raw -Encoding UTF8 | ConvertFrom-Json
                }
                Move-Item $partial $output
            } finally {
                if (Test-Path $partial) { Remove-Item $partial -Force }
            }
        }
    }
    $mapping[$language] = (Join-Path $path "$name.onnx")
    Write-Host "Voice $language downloaded and configured" -ForegroundColor Green
}
$configuration = Join-Path $engine 'voices.json'
[System.IO.File]::WriteAllText($configuration, ($mapping | ConvertTo-Json), [System.Text.UTF8Encoding]::new($false))
Write-Host "Local voice map created: $configuration" -ForegroundColor Cyan
Write-Host "Review the MODEL_CARD files for individual voices before using them." -ForegroundColor Yellow
