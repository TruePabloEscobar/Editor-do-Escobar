[CmdletBinding()]
param(
    [switch]$VerifyOnly,
    [switch]$Elevate,
    [string]$ProjectRoot,
    [string]$DeveloperRoot,
    [string]$Destination
)

$ErrorActionPreference = "Stop"
if (-not $ProjectRoot) {
    $ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
}
$env:PSModulePath = (Join-Path $env:WINDIR 'System32/WindowsPowerShell/v1.0/Modules') + ';' + (Join-Path $env:ProgramFiles 'WindowsPowerShell/Modules')
[Console]::OutputEncoding = New-Object Text.UTF8Encoding($false)
$pluginName = "com.oeditor.resolve.internalhost"
$source = [IO.Path]::Combine($projectRoot, "workflow_integration", $pluginName)
if (-not $DeveloperRoot) {
    $developerRoot = [IO.Path]::Combine(
        $env:PROGRAMDATA,
        "Blackmagic Design",
        "DaVinci Resolve",
        "Support",
        "Developer",
        "Workflow Integrations"
    )
}
$moduleSource = [IO.Path]::Combine(
    $developerRoot,
    "Examples",
    "SamplePlugin",
    "WorkflowIntegration.node"
)
if (-not $Destination) {
    $destination = [IO.Path]::Combine(
        $env:PROGRAMDATA,
        "Blackmagic Design",
        "DaVinci Resolve",
        "Support",
        "Workflow Integration Plugins",
        $pluginName
    )
}

if (-not [IO.Directory]::Exists($source)) {
    throw "Fonte do Workflow Integration não encontrada: $source"
}

function Invoke-ElevatedWorkflowInstall {
    if (-not $Elevate) { throw 'Sem permissão para instalar o plugin. Execute com -Elevate para solicitar autorização do Windows.' }
    $arguments = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $PSCommandPath,
        '-ProjectRoot', $ProjectRoot, '-DeveloperRoot', $DeveloperRoot, '-Destination', $destination)
    $quoted = foreach ($argument in $arguments) {
        if ($argument -match '["\r\n]') { throw 'Argumento inválido para a instalação elevada.' }
        '"' + $argument.TrimEnd('\') + '"'
    }
    $process = Start-Process -FilePath (Join-Path $env:WINDIR 'System32/WindowsPowerShell/v1.0/powershell.exe') `
        -Verb RunAs -WindowStyle Hidden -ArgumentList ($quoted -join ' ') -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw "Instalação do plugin não concluída (código $($process.ExitCode)). O acesso por Scripts permanece disponível." }
    & $PSCommandPath -VerifyOnly -ProjectRoot $ProjectRoot -DeveloperRoot $DeveloperRoot -Destination $destination
}
if (-not [IO.File]::Exists($moduleSource)) {
    throw "Módulo oficial WorkflowIntegration.node não encontrado: $moduleSource"
}

$sourceFiles = Get-ChildItem -LiteralPath $source -File
$required = @(
    "manifest.xml",
    "package.json",
    "main.js",
    "preload.js",
    "renderer.js",
    "index.html",
    "styles.css",
    "open-editor.lua"
)
foreach ($name in $required) {
    if (-not [IO.File]::Exists([IO.Path]::Combine($source, $name))) {
        throw "Artefato obrigatório ausente: $name"
    }
}

$moduleInstalled = [IO.Path]::Combine($destination, "WorkflowIntegration.node")
# Fail before changing anything when the plugin is loaded, even if its binary matches.
if (-not $VerifyOnly -and [IO.Directory]::Exists($destination)) {
    foreach ($installedFile in (Get-ChildItem -LiteralPath $destination -File)) {
        try {
            $handle = [IO.File]::Open($installedFile.FullName, 'Open', 'ReadWrite', 'None')
            $handle.Dispose()
        } catch {
            if ($_.Exception.GetBaseException() -is [UnauthorizedAccessException] -and $Elevate) {
                Invoke-ElevatedWorkflowInstall
                return
            }
            throw "Feche a janela EDE e tente novamente. O plugin está em uso. Nenhum arquivo foi atualizado."
        }
    }
}

if (-not $VerifyOnly) {
    $destination = [IO.Path]::GetFullPath($destination)
    $parent = [IO.Path]::GetDirectoryName($destination)
    $stage = Join-Path $parent ('.ede-stage-' + [Guid]::NewGuid().ToString('N'))
    try {
        [IO.Directory]::CreateDirectory($stage) | Out-Null
    } catch [UnauthorizedAccessException] {
        Invoke-ElevatedWorkflowInstall
        return
    }
    foreach ($file in $sourceFiles) {
        $target = Join-Path $stage $file.Name
        [IO.File]::Copy($file.FullName, $target, $false)
        if ((Get-FileHash -LiteralPath $file.FullName).Hash -ne (Get-FileHash -LiteralPath $target).Hash) {
            throw "Cópia do plugin divergente antes da ativação: $($file.Name)"
        }
    }
    $stagedModule = Join-Path $stage 'WorkflowIntegration.node'
    [IO.File]::Copy($moduleSource, $stagedModule, $false)
    if ((Get-FileHash -LiteralPath $moduleSource).Hash -ne (Get-FileHash -LiteralPath $stagedModule).Hash) {
        throw 'Módulo oficial divergente antes da ativação.'
    }
    $backup = $null
    if ([IO.Directory]::Exists($destination)) {
        # One hidden container outside the enumerated plugin; originals are retained.
        $backup = Join-Path (Join-Path $parent '.ede-backups') ([IO.Path]::GetFileName($destination) + '-' + [Guid]::NewGuid().ToString('N'))
        [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($backup)) | Out-Null
        [IO.Directory]::Move($destination, $backup)
    }
    try { [IO.Directory]::Move($stage, $destination) }
    catch {
        if ($backup -and -not [IO.Directory]::Exists($destination)) { [IO.Directory]::Move($backup, $destination) }
        throw
    }
    if ($backup) { Write-Host "Plugin anterior preservado em: $backup" }
}

$verification = [Collections.Generic.List[object]]::new()
foreach ($file in $sourceFiles) {
    $installed = [IO.Path]::Combine($destination, $file.Name)
    if (-not [IO.File]::Exists($installed)) {
        throw "Arquivo do plugin não instalado: $installed"
    }
    $sourceHash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash
    $installedHash = (Get-FileHash -LiteralPath $installed -Algorithm SHA256).Hash
    if ($sourceHash -ne $installedHash) {
        throw "Hash divergente no plugin: $($file.Name)"
    }
    $verification.Add([ordered]@{
        name = $file.Name
        sha256 = $installedHash
    })
}

$moduleInstalled = [IO.Path]::Combine($destination, "WorkflowIntegration.node")
if (-not [IO.File]::Exists($moduleInstalled)) {
    throw "WorkflowIntegration.node não foi instalado."
}
$officialHash = (Get-FileHash -LiteralPath $moduleSource -Algorithm SHA256).Hash
$installedModuleHash = (Get-FileHash -LiteralPath $moduleInstalled -Algorithm SHA256).Hash
if ($officialHash -ne $installedModuleHash) {
    throw "WorkflowIntegration.node instalado diverge do módulo oficial local."
}

Write-Host "Workflow Integration: PASSED"
Write-Host "Destino: $destination"
Write-Host "Módulo oficial SHA-256: $officialHash"
Write-Host "Reinicie o Resolve para enumerar Workspace > Workflow Integrations > EDE - Editor Do Escobar."

