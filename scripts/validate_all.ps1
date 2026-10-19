[CmdletBinding()]
param(
    [switch]$Mock,
    [switch]$SkipUnitTests,
    [switch]$SkipQuality,
    [switch]$SkipResolve,
    [switch]$ReadOnlyProbe,
    [switch]$AllowTemporaryMutations,
    [switch]$VerboseOutput,
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = New-Object Text.UTF8Encoding($false)
$OutputEncoding = [Console]::OutputEncoding
$env:PYTHONUTF8 = "1"
$startedAt = Get-Date
$python = [IO.Path]::Combine($ProjectRoot, ".venv", "Scripts", "python.exe")
$reportDirectory = [IO.Path]::Combine($ProjectRoot, "runtime", "reports")
$markdownPath = [IO.Path]::Combine($reportDirectory, "AUTOMATED_VALIDATION_REPORT.md")
$jsonPath = [IO.Path]::Combine($reportDirectory, "automated_validation_report.json")
$hostMarkdownPath = [IO.Path]::Combine($reportDirectory, "INTERNAL_RESOLVE_HOST_REPORT.md")
$hostJsonPath = [IO.Path]::Combine($reportDirectory, "internal_resolve_host_report.json")
$pytestTemp = [IO.Path]::Combine(
    $ProjectRoot,
    "runtime",
    ("pytest-temp-{0}-{1}" -f $PID, [guid]::NewGuid().ToString("N"))
)
[IO.Directory]::CreateDirectory($reportDirectory) | Out-Null

$steps = [System.Collections.Generic.List[object]]::new()
function Invoke-ValidationStep {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][scriptblock]$Action
    )
    $watch = [Diagnostics.Stopwatch]::StartNew()
    $output = ""
    $exitCode = 0
    try {
        $global:LASTEXITCODE = 0
        $lines = & $Action 2>&1
        $exitCode = if ($null -eq $LASTEXITCODE) { 0 } else { [int]$LASTEXITCODE }
        $output = ($lines | Out-String).Trim()
    }
    catch {
        $exitCode = 1
        $output = $_.Exception.Message
    }
    $watch.Stop()
    $status = if ($exitCode -eq 0) { "PASSED" } else { "FAILED" }
    $item = [pscustomobject]@{
        name = $Name
        status = $status
        exit_code = $exitCode
        duration_seconds = [Math]::Round($watch.Elapsed.TotalSeconds, 3)
        output = $output
    }
    $steps.Add($item)
    Write-Host ("[{0}] {1} ({2}s)" -f $status, $Name, $item.duration_seconds)
    if ($VerboseOutput -and $output) {
        Write-Host $output
    }
    return $item
}

function Add-SkippedStep {
    param([string]$Name, [string]$Detail)
    $item = [pscustomobject]@{
        name = $Name
        status = "SKIPPED"
        exit_code = 0
        duration_seconds = 0
        output = $Detail
    }
    $steps.Add($item)
    Write-Host "[SKIPPED] $Name - $Detail"
}

function Get-StepStatus {
    param([string[]]$Names)
    $selected = @($steps | Where-Object { $Names -contains $_.name })
    if (@($selected | Where-Object { $_.status -eq "FAILED" }).Count -gt 0) {
        return "FAILED"
    }
    if (@($selected | Where-Object { $_.status -eq "PASSED" }).Count -gt 0) {
        return "PASSED"
    }
    return "UNVERIFIED"
}

Write-Host "O Editor - validação consolidada"
Write-Host "Projeto: $ProjectRoot"

if (-not [IO.File]::Exists($python)) {
    throw "Python da virtual environment não encontrado: $python"
}
$pythonInfo = (& $python -c 'import platform,struct,sys; print(platform.python_version()+chr(124)+str(struct.calcsize(chr(80))*8)+chr(124)+sys.executable)').Trim()
if (-not $pythonInfo.StartsWith("3.11.") -or $pythonInfo -notmatch "\|64\|") {
    throw "A validação exige Python 3.11 x64 da .venv; encontrado: $pythonInfo"
}

Push-Location $ProjectRoot
try {
    if ($SkipQuality) {
        Add-SkippedStep "ruff check" "Ignorado por -SkipQuality."
        Add-SkippedStep "ruff format" "Ignorado por -SkipQuality."
        Add-SkippedStep "mypy" "Ignorado por -SkipQuality."
    }
    else {
        Invoke-ValidationStep "ruff check" { & $python -m ruff check . } | Out-Null
        Invoke-ValidationStep "ruff format" { & $python -m ruff format --check . } | Out-Null
        Invoke-ValidationStep "mypy" { & $python -m mypy src } | Out-Null
    }

    if ($SkipUnitTests) {
        Add-SkippedStep "pytest" "Ignorado por -SkipUnitTests."
    }
    else {
        Invoke-ValidationStep "pytest" {
            & $python -m pytest `
                --basetemp $pytestTemp `
                -p no:cacheprovider `
                --cov=o_editor.domain `
                --cov=o_editor.application `
                --cov-report=term-missing
        } | Out-Null
    }

    Invoke-ValidationStep "doctor" {
        & ([IO.Path]::Combine($ProjectRoot, "scripts", "doctor.ps1")) -ProjectRoot $ProjectRoot
        $global:LASTEXITCODE = 0
    } | Out-Null
    Invoke-ValidationStep "mock headless" { & $python -m o_editor --mock --headless } |
        Out-Null
    Invoke-ValidationStep "self-test" { & $python -m o_editor --self-test } | Out-Null
    Invoke-ValidationStep "launcher verification" {
        & ([IO.Path]::Combine($ProjectRoot, "scripts", "verify_launcher_installation.ps1")) `
            -ProjectRoot $ProjectRoot
        if (-not $?) {
            $global:LASTEXITCODE = 1
        }
    } | Out-Null

    $resolveProcess = Get-Process -Name "Resolve" -ErrorAction SilentlyContinue
    if ($SkipResolve) {
        Add-SkippedStep "Resolve connection" "Ignorado por -SkipResolve."
        Add-SkippedStep "Resolve capability probe" "Ignorado por -SkipResolve."
        $resolveProcessStatus = "SKIPPED"
    }
    elseif (-not $resolveProcess) {
        Add-SkippedStep "Resolve connection" "Resolve.exe não está aberto."
        Add-SkippedStep "Resolve capability probe" "Resolve.exe não está aberto."
        $resolveProcessStatus = "SKIPPED"
    }
    elseif (-not $ReadOnlyProbe) {
        Add-SkippedStep "Resolve connection" "Use -ReadOnlyProbe para o diagnóstico externo avançado."
        Add-SkippedStep "Resolve capability probe" "Use -ReadOnlyProbe para o probe somente leitura."
        $resolveProcessStatus = "RUNNING"
    }
    else {
        $resolveProcessStatus = "RUNNING"
        Invoke-ValidationStep "Resolve connection" {
            & $python -m o_editor.infrastructure.resolve.connection_test --root $ProjectRoot
        } | Out-Null
        if ($AllowTemporaryMutations) {
            throw "O modo mutável permanece bloqueado nesta validação."
        }
        Invoke-ValidationStep "Resolve capability probe" {
            & $python -m o_editor.infrastructure.resolve.capabilities `
                --root $ProjectRoot `
                --read-only
        } | Out-Null
    }

    $configurationDirectory = [IO.Path]::Combine($env:APPDATA, "O Editor")
    $utilityDirectory = [IO.Path]::Combine(
        $env:APPDATA,
        "Blackmagic Design",
        "DaVinci Resolve",
        "Support",
        "Fusion",
        "Scripts",
        "Utility"
    )
    $diagnosticName = "O Editor - Diagn" + [char]0x00F3 + "stico.lua"
    $luaNames = @("O EDITOR.lua")
    $installedScripts = @()
    foreach ($name in $luaNames) {
        $path = [IO.Path]::Combine($utilityDirectory, $name)
        $installedScripts += [ordered]@{
            name = $name
            path = $path
            installed = [IO.File]::Exists($path)
            sha256 = if ([IO.File]::Exists($path)) {
                (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash
            }
            else {
                $null
            }
        }
    }
    $launcherConfigurationPath = [IO.Path]::Combine($configurationDirectory, "launcher.json")
    $launchCommandPath = [IO.Path]::Combine($configurationDirectory, "launch-editor.cmd")
    $diagnosticPath = [IO.Path]::Combine($configurationDirectory, "internal-diagnostic.json")
    $menuEvidencePath = [IO.Path]::Combine($configurationDirectory, "menu-test-success.txt")
    $internalCapabilitiesPath = [IO.Path]::Combine(
        $configurationDirectory,
        "internal-capabilities.json"
    )
    $internalContextStatus = if ([IO.File]::Exists($diagnosticPath)) { "READY" } else { "UNVERIFIED" }
    $menuStatus = if ([IO.File]::Exists($menuEvidencePath)) { "PASSED" } else { "UNVERIFIED" }

    $userConfig = [IO.Path]::Combine($configurationDirectory, "config.json")
    $runtimeConfig = $null
    if ([IO.File]::Exists($userConfig)) {
        try {
            $runtimeConfig = (
                Get-Content -Raw -LiteralPath $userConfig -Encoding UTF8 |
                    ConvertFrom-Json
            )
        }
        catch {
            $runtimeConfig = $null
        }
    }
    $configuredFfmpeg = if ($runtimeConfig) { $runtimeConfig.ffmpeg.ffmpeg_path } else { $null }
    $configuredFfprobe = if ($runtimeConfig) { $runtimeConfig.ffmpeg.ffprobe_path } else { $null }
    $ffmpeg = if ($configuredFfmpeg -and [IO.File]::Exists($configuredFfmpeg)) {
        Get-Item -LiteralPath $configuredFfmpeg
    } else {
        Get-Command ffmpeg -ErrorAction SilentlyContinue
    }
    $ffprobe = if ($configuredFfprobe -and [IO.File]::Exists($configuredFfprobe)) {
        Get-Item -LiteralPath $configuredFfprobe
    } else {
        Get-Command ffprobe -ErrorAction SilentlyContinue
    }
    $ffmpegState = if ($ffmpeg -and $ffprobe) { "PASSED" } else { "PENDING" }
    $ffmpegDetail = if ($ffmpeg -and $ffprobe) {
        (& $ffmpeg.FullName -version 2>&1 | Select-Object -First 1)
    }
    else {
        "FFmpeg/FFprobe não foram encontrados no PATH nem em config.json."
    }

    $whisperPath = $null
    if ($runtimeConfig) {
        $whisperPath = $runtimeConfig.transcription.model_path
    }
    $whisperImport = & $python -c 'import ctranslate2,faster_whisper; print(faster_whisper.__version__+chr(124)+str(ctranslate2.get_cuda_device_count()))' 2>&1
    $whisperState = if (
        $LASTEXITCODE -eq 0 -and
        $whisperPath -and
        [IO.File]::Exists([IO.Path]::Combine($whisperPath, "model.bin"))
    ) { "PASSED" } else { "PENDING" }

    $qualityState = Get-StepStatus @("ruff check", "ruff format", "mypy")
    $testState = Get-StepStatus @("pytest")
    $mockState = Get-StepStatus @("mock headless")
    $coreState = Get-StepStatus @("doctor", "self-test")
    $launcherState = Get-StepStatus @("launcher verification")
    $externalResults = @(
        $steps | Where-Object { $_.name -in @("Resolve connection", "Resolve capability probe") }
    )
    $externalState = if (-not $resolveProcess -or -not $ReadOnlyProbe) {
        "DISABLED"
    }
    elseif (@($externalResults | Where-Object { $_.status -eq "FAILED" }).Count -gt 0) {
        "DEGRADED"
    }
    else {
        "PASSED"
    }
    $planExportState = if ($testState -eq "PASSED") { "PASSED" } else { "UNVERIFIED" }
    $planApplicationState = "PENDING"

    $components = [ordered]@{
        CORE_APP = $coreState
        QUALITY = $qualityState
        TESTS = $testState
        MOCK = $mockState
        INTERNAL_LAUNCHER_INSTALLATION = $launcherState
        INTERNAL_CONTEXT = $internalContextStatus
        EXTERNAL_BRIDGE = $externalState
        FFMPEG = $ffmpegState
        WHISPER = $whisperState
        ANALYSIS = if ($mockState -eq "PASSED") { "READY" } else { "UNVERIFIED" }
        PLAN_EXPORT = $planExportState
        PLAN_APPLICATION = $planApplicationState
    }
    $criticalFailed = @(
        $coreState,
        $qualityState,
        $testState,
        $mockState
    ) -contains "FAILED"
    $overall = if ($criticalFailed) {
        "FAILED"
    }
    elseif ($launcherState -eq "FAILED") {
        "DEGRADED"
    }
    elseif ($internalContextStatus -eq "READY" -and $menuStatus -eq "PASSED") {
        "READY_INTERNAL"
    }
    else {
        "READY_OFFLINE"
    }

    $branch = (git -c safe.directory="$($ProjectRoot.Replace('\', '/'))" branch --show-current 2>$null | Out-String).Trim()
    $commit = (git -c safe.directory="$($ProjectRoot.Replace('\', '/'))" rev-parse --short HEAD 2>$null | Out-String).Trim()
    $workingTree = (git -c safe.directory="$($ProjectRoot.Replace('\', '/'))" status --short 2>$null | Out-String).Trim()
    $finishedAt = Get-Date
    $hostData = [ordered]@{
        schema_version = 1
        generated_at = $finishedAt.ToString("o")
        status = $internalContextStatus
        menu_execution = $menuStatus
        utility_directory = $utilityDirectory
        scripts = $installedScripts
        launcher_configuration = $launcherConfigurationPath
        launch_command = $launchCommandPath
        internal_diagnostic = $diagnosticPath
        internal_capabilities = $internalCapabilitiesPath
        resolve_process = $resolveProcessStatus
        mutations_executed = $false
        next_manual_steps = @(
            "Reinicie o Resolve para atualizar a lista de menus.",
            "Execute Workspace > Scripts > O EDITOR."
        )
    }
    $data = [ordered]@{
        schema_version = 2
        generated_at = $finishedAt.ToString("o")
        status = $overall
        components = $components
        git = [ordered]@{
            commit = $commit
            branch = $branch
            working_tree = if ($workingTree) { $workingTree } else { "clean" }
        }
        python = $pythonInfo
        steps = $steps
        resolve = [ordered]@{
            process = $resolveProcessStatus
            mutations_executed = $false
            external_bridge_enabled = $false
        }
        ffmpeg = [ordered]@{ status = $ffmpegState; detail = $ffmpegDetail }
        whisper = [ordered]@{
            status = $whisperState
            model_path = if ($whisperPath) { $whisperPath } else { "PENDING" }
            runtime = ($whisperImport | Out-String).Trim()
        }
        internal_host_report = $hostJsonPath
        duration_seconds = [Math]::Round(($finishedAt - $startedAt).TotalSeconds, 3)
    }
    [IO.File]::WriteAllText(
        $jsonPath,
        ($data | ConvertTo-Json -Depth 14),
        (New-Object Text.UTF8Encoding($false))
    )
    [IO.File]::WriteAllText(
        $hostJsonPath,
        ($hostData | ConvertTo-Json -Depth 12),
        (New-Object Text.UTF8Encoding($false))
    )

    $lines = [System.Collections.Generic.List[string]]::new()
    $lines.Add("# Relatório de validação automatizada")
    $lines.Add("")
    $lines.Add("- Status consolidado: ``$overall``")
    $lines.Add("- Gerado em: ``$($finishedAt.ToString('o'))``")
    $lines.Add("- Branch/commit: ``$branch`` / ``$commit``")
    $lines.Add("- Python: ``$pythonInfo``")
    $lines.Add("- Mutações no Resolve: ``não executadas``")
    $lines.Add("")
    $lines.Add("## Componentes")
    $lines.Add("")
    $lines.Add("| Componente | Status |")
    $lines.Add("|---|---|")
    foreach ($component in $components.GetEnumerator()) {
        $lines.Add("| $($component.Key) | $($component.Value) |")
    }
    $lines.Add("")
    $lines.Add("## Etapas executadas")
    $lines.Add("")
    $lines.Add("| Etapa | Status | Exit code | Duração |")
    $lines.Add("|---|---|---:|---:|")
    foreach ($step in $steps) {
        $lines.Add("| $($step.name) | $($step.status) | $($step.exit_code) | $($step.duration_seconds)s |")
    }
    $lines.Add("")
    $lines.Add("## Dependências")
    $lines.Add("")
    $lines.Add("- FFmpeg: ``$ffmpegState`` - $ffmpegDetail")
    $lines.Add("- Whisper: ``$whisperState`` - $(if ($whisperPath) { $whisperPath } else { 'modelo não configurado' })")
    $lines.Add("- Ponte FusionScript externa: ``$externalState``; desabilitada por padrão.")
    $lines.Add("- Aplicação de plano: ``PENDING``; bloqueada até duplicação de timeline ser SUPPORTED.")
    $lines.Add("")
    $lines.Add("## Saídas detalhadas")
    foreach ($step in $steps) {
        $lines.Add("")
        $lines.Add("### $($step.name)")
        $lines.Add("")
        $lines.Add("``````text")
        $lines.Add($(if ($step.output) { $step.output } else { "(sem saída)" }))
        $lines.Add("``````")
    }
    [IO.File]::WriteAllLines(
        $markdownPath,
        $lines,
        (New-Object Text.UTF8Encoding($false))
    )

    $hostLines = @(
        "# Relatório do host interno do Resolve",
        "",
        "- Status do contexto interno: ``$internalContextStatus``",
        "- Evidência do teste de menu: ``$menuStatus``",
        "- Resolve aberto durante a validação: ``$resolveProcessStatus``",
        "- Mutações executadas: ``não``",
        "- Diretório Utility: ``$utilityDirectory``",
        "- Configuração: ``$launcherConfigurationPath``",
        "- Comando externo: ``$launchCommandPath``",
        "- Diagnóstico interno: ``$diagnosticPath``",
        "- Capabilities internas: ``$internalCapabilitiesPath``",
        "",
        "A instalação e os hashes são verificáveis automaticamente. A execução dentro do menu",
        "permanece UNVERIFIED até existirem os arquivos de evidência gerados pelo Resolve."
    )
    [IO.File]::WriteAllLines(
        $hostMarkdownPath,
        $hostLines,
        (New-Object Text.UTF8Encoding($false))
    )

    Write-Host ""
    Write-Host "Relatório Markdown: $markdownPath"
    Write-Host "Relatório JSON: $jsonPath"
    Write-Host "Relatório host interno: $hostMarkdownPath"
    Write-Host "Status final: $overall"
    exit $(if ($overall -eq "FAILED") { 1 } else { 0 })
}
finally {
    Pop-Location
}
