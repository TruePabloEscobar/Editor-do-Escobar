[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = [IO.Path]::Combine($projectRoot, ".venv", "Scripts", "python.exe")
$reportDirectory = [IO.Path]::Combine($projectRoot, "runtime", "reports")
$reportPath = [IO.Path]::Combine($reportDirectory, "VOICE_EXPORT_MOCK_REPORT.md")
[IO.Directory]::CreateDirectory($reportDirectory) | Out-Null

Push-Location $projectRoot
try {
    & $python -m pytest `
        tests/unit/test_voice_tracks.py `
        tests/unit/test_resolve_internal_host.py `
        tests/unit/test_ffmpeg_runner.py `
        tests/unit/test_faster_whisper.py
    if ($LASTEXITCODE -ne 0) {
        throw "Testes mock de exportação de voz falharam."
    }
    $headless = & $python -m o_editor --mock --headless
    if ($LASTEXITCODE -ne 0) {
        throw "Fluxo mock headless falhou."
    }
    $lines = @(
        "# Validação mock da exportação de voz",
        "",
        "- Status: ``PASSED``",
        "- Render real: ``não executado``",
        "- Mutações no Resolve: ``não``",
        "- Testes: voice tracks, host protocol, FFmpeg runner e faster-whisper",
        "- Headless: $($headless | Out-String)",
        ""
    )
    [IO.File]::WriteAllLines($reportPath, $lines, [Text.UTF8Encoding]::new($false))
    Write-Host "Voice export mock: PASSED"
    Write-Host "Relatório: $reportPath"
} finally {
    Pop-Location
}

