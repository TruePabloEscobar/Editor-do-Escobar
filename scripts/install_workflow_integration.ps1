[CmdletBinding()]
param(
    [switch]$VerifyOnly,
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$DeveloperRoot,
    [string]$Destination
)

$ErrorActionPreference = "Stop"
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
    "styles.css"
)
foreach ($name in $required) {
    if (-not [IO.File]::Exists([IO.Path]::Combine($source, $name))) {
        throw "Artefato obrigatório ausente: $name"
    }
}

$moduleInstalled = [IO.Path]::Combine($destination, "WorkflowIntegration.node")
$copyModule = -not [IO.File]::Exists($moduleInstalled)
if (-not $copyModule) {
    $copyModule = (Get-FileHash -LiteralPath $moduleSource -Algorithm SHA256).Hash -ne `
        (Get-FileHash -LiteralPath $moduleInstalled -Algorithm SHA256).Hash
}
# Fail before updating any JavaScript if the required native binary is loaded.
if (-not $VerifyOnly -and $copyModule -and [IO.File]::Exists($moduleInstalled)) {
    try {
        $handle = [IO.File]::Open($moduleInstalled, "Open", "ReadWrite", "None")
        $handle.Dispose()
    }
    catch {
        throw "Feche a janela O Editor - Host Interno e tente novamente. O módulo oficial precisa ser atualizado, mas está em uso. Nenhum arquivo foi atualizado."
    }
}

if (-not $VerifyOnly) {
    [IO.Directory]::CreateDirectory($destination) | Out-Null
    foreach ($file in $sourceFiles) {
        [IO.File]::Copy(
            $file.FullName,
            [IO.Path]::Combine($destination, $file.Name),
            $true
        )
    }
    if ($copyModule) {
        [IO.File]::Copy($moduleSource, $moduleInstalled, $true)
    }
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
Write-Host "Reinicie o Resolve para enumerar Workspace > Workflow Integrations > O Editor - Host Interno."

