[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = [IO.Path]::Combine($projectRoot, ".venv", "Scripts", "python.exe")
$configPath = [IO.Path]::Combine($env:APPDATA, "O Editor", "config.json")
$reportDirectory = [IO.Path]::Combine($projectRoot, "runtime", "reports")
$jsonPath = [IO.Path]::Combine($reportDirectory, "whisper_validation_report.json")
$markdownPath = [IO.Path]::Combine($reportDirectory, "WHISPER_VALIDATION_REPORT.md")

if (-not [IO.File]::Exists($python)) {
    throw "Python do projeto não encontrado: $python"
}
if (-not [IO.File]::Exists($configPath)) {
    throw "Configuração local não encontrada: $configPath"
}
$config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
$model = [string]$config.transcription.model
$modelPath = [string]$config.transcription.model_path
if (-not [IO.File]::Exists([IO.Path]::Combine($modelPath, "model.bin"))) {
    throw "Modelo Whisper local ausente ou incompleto: $modelPath"
}
[IO.Directory]::CreateDirectory($reportDirectory) | Out-Null

& $python -m o_editor.infrastructure.transcription.setup `
    --test `
    --model $model `
    --model-path $modelPath `
    --config-path $configPath `
    --report-path $jsonPath
if ($LASTEXITCODE -ne 0) {
    throw "O teste local do Whisper falhou. Consulte $jsonPath"
}
$report = Get-Content -LiteralPath $jsonPath -Raw | ConvertFrom-Json
$test = $report.inference_test
$gpuStatus = if (
    [int]$report.cuda_device_count -gt 0 -and
    [string]$test.device_used -ne "cuda"
) { "FAILED" } else { "PASSED" }
$operationalStatus = if ($gpuStatus -eq "PASSED") { "PASSED" } else { "DEGRADED" }
$report | Add-Member -NotePropertyName gpu_status -NotePropertyValue $gpuStatus -Force
$report | Add-Member `
    -NotePropertyName operational_status `
    -NotePropertyValue $operationalStatus `
    -Force
[IO.File]::WriteAllText(
    $jsonPath,
    ($report | ConvertTo-Json -Depth 12) + "`n",
    [Text.UTF8Encoding]::new($false)
)
$lines = @(
    "# Validação do Whisper",
    "",
    "- Status operacional: ``$operationalStatus``",
    "- Inferência local: ``$($report.status)``",
    "- faster-whisper: ``$($report.faster_whisper_version)``",
    "- Modelo local: ``$modelPath``",
    "- Download solicitado: ``$($report.download_requested)``",
    "- CUDA devices: ``$($report.cuda_device_count)``",
    "- Device usado: ``$($test.device_used)``",
    "- CUDA: ``$gpuStatus``",
    "- Fallback: $($test.fallback_reason)",
    "- Fixture: $($test.audio)",
    "- Segmentos: ``$($test.segments)``",
    "- Timestamps por palavra: ``$($test.word_timestamps)``",
    "- Conteúdo transcrito registrado: ``$($test.transcript_content_logged)``",
    ""
)
[IO.File]::WriteAllLines($markdownPath, $lines, [Text.UTF8Encoding]::new($false))
Write-Host "Whisper: $operationalStatus"
Write-Host "Relatório: $markdownPath"

