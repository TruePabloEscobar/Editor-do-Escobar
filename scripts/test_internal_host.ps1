[CmdletBinding()]
param(
    [ValidateRange(1, 120)]
    [int]$TimeoutSeconds = 5
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = [IO.Path]::Combine($projectRoot, ".venv", "Scripts", "python.exe")
$reportDirectory = [IO.Path]::Combine($projectRoot, "runtime", "reports")
$jsonPath = [IO.Path]::Combine($reportDirectory, "resolve_internal_host_spike.json")
$jsonAliasPath = [IO.Path]::Combine($reportDirectory, "internal_host_spike_report.json")
$markdownPath = [IO.Path]::Combine($reportDirectory, "RESOLVE_INTERNAL_HOST_SPIKE.md")
$markdownAliasPath = [IO.Path]::Combine($reportDirectory, "INTERNAL_HOST_SPIKE_REPORT.md")
$pluginPath = [IO.Path]::Combine(
    $env:PROGRAMDATA,
    "Blackmagic Design",
    "DaVinci Resolve",
    "Support",
    "Workflow Integration Plugins",
    "com.oeditor.resolve.internalhost"
)

if (-not [IO.File]::Exists($python)) {
    throw "Python do projeto não encontrado: $python"
}
[IO.Directory]::CreateDirectory($reportDirectory) | Out-Null

& $python -m o_editor.internal_actions.host_spike `
    --timeout $TimeoutSeconds `
    --report $jsonPath
$spikeExitCode = $LASTEXITCODE
if (-not [IO.File]::Exists($jsonPath)) {
    throw "O spike não produziu o relatório JSON."
}

$report = Get-Content -LiteralPath $jsonPath -Raw | ConvertFrom-Json
[IO.File]::Copy($jsonPath, $jsonAliasPath, $true)
$hostStatusPath = [IO.Path]::Combine(
    $env:APPDATA,
    "O Editor",
    "resolve-internal-host",
    "host-status.json"
)
$hostStatus = if ([IO.File]::Exists($hostStatusPath)) {
    Get-Content -LiteralPath $hostStatusPath -Raw | ConvertFrom-Json
} else {
    $null
}
$pluginInstalled = [IO.File]::Exists([IO.Path]::Combine($pluginPath, "manifest.xml"))
$resolveRunning = @(Get-Process -Name "Resolve" -ErrorAction SilentlyContinue).Count -gt 0

$lines = @(
    "# Spike do host persistente do Resolve",
    "",
    "- Capability: ``$($report.status)``",
    "- Detalhe: $($report.detail)",
    "- Plugin instalado: ``$pluginInstalled``",
    "- Resolve em execução: ``$resolveRunning``",
    "- Host observado: ``$(if ($hostStatus) { $hostStatus.status } else { 'UNVERIFIED' })``",
    "- Mutações executadas: ``não``",
    "",
    "## Critério de prova",
    "",
    "O host só é classificado como ``SUPPORTED`` quando uma request criada pelo aplicativo",
    "é consumida pelo Workflow Integration dentro do Resolve e uma resposta contém",
    "``pong=true`` com projeto/timeline lidos pela API oficial.",
    "",
    "A instalação e a estrutura oficial, isoladamente, não provam execução real.",
    ""
)
[IO.File]::WriteAllLines($markdownPath, $lines, [Text.UTF8Encoding]::new($false))
[IO.File]::Copy($markdownPath, $markdownAliasPath, $true)

Write-Host "Spike do host: $($report.status)"
Write-Host "Relatório: $markdownPath"
Write-Host "JSON: $jsonPath"
exit $spikeExitCode

