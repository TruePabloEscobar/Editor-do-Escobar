[CmdletBinding()]
param(
    [object]$Destination,
    [object]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [object]$PythonExecutable
)

$ErrorActionPreference = "Stop"
$env:PSModulePath = (Join-Path $env:WINDIR "System32\WindowsPowerShell\v1.0\Modules") + ";" + (Join-Path $env:ProgramFiles "WindowsPowerShell\Modules")
[Console]::OutputEncoding = New-Object Text.UTF8Encoding($false)
$OutputEncoding = [Console]::OutputEncoding
$env:PYTHONUTF8 = "1"

function ConvertTo-NormalizedPath {
    [OutputType([string])]
    param(
        [Parameter(Mandatory = $true)][AllowEmptyString()][object]$Value,
        [Parameter(Mandatory = $true)][string]$Name,
        [ValidateSet("Any", "File", "Directory")][string]$ExistingType = "Any"
    )

    if ($Value -is [array]) {
        throw "$Name recebeu um array; era esperada exatamente uma string."
    }
    if ($null -eq $Value -or $Value -isnot [string]) {
        throw "$Name deve ser uma string."
    }
    $candidate = ([string]$Value).Trim()
    while (
        $candidate.Length -gt 0 -and
        ($candidate[0] -eq [char]34 -or $candidate[0] -eq [char]39)
    ) {
        $candidate = $candidate.Substring(1).TrimStart()
    }
    while (
        $candidate.Length -gt 0 -and
        (
            $candidate[$candidate.Length - 1] -eq [char]34 -or
            $candidate[$candidate.Length - 1] -eq [char]39
        )
    ) {
        $candidate = $candidate.Substring(0, $candidate.Length - 1).TrimEnd()
    }
    if ([string]::IsNullOrWhiteSpace($candidate)) {
        throw "$Name não pode ser vazio."
    }
    if ($candidate.IndexOfAny([char[]]@("`r", "`n", "`t")) -ge 0) {
        throw "$Name contém CR, LF ou TAB."
    }
    if ($candidate.Contains([string][char]34) -or $candidate.Contains([string][char]39)) {
        throw "$Name contém aspas incorporadas."
    }
    try {
        $fullPath = [System.IO.Path]::GetFullPath($candidate)
    }
    catch {
        throw "$Name contém um caminho inválido: <$Value>. $($_.Exception.Message)"
    }
    $pathRoot = [System.IO.Path]::GetPathRoot($fullPath)
    if ($fullPath.Length -gt $pathRoot.Length) {
        $fullPath = $fullPath.TrimEnd(
            [System.IO.Path]::DirectorySeparatorChar,
            [System.IO.Path]::AltDirectorySeparatorChar
        )
    }
    if ($ExistingType -eq "File" -and -not [System.IO.File]::Exists($fullPath)) {
        throw "$Name não encontrado: $fullPath"
    }
    if (
        $ExistingType -eq "Directory" -and
        -not [System.IO.Directory]::Exists($fullPath)
    ) {
        throw "$Name não encontrado: $fullPath"
    }
    return [string]$fullPath
}

function Get-FileSha256 {
    [OutputType([string])]
    param([Parameter(Mandatory = $true)][string]$Path)

    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
}

function Assert-Utf8NoBom {
    param([Parameter(Mandatory = $true)][string]$Path)

    $bytes = [System.IO.File]::ReadAllBytes($Path)
    if (
        $bytes.Length -ge 3 -and
        $bytes[0] -eq 0xEF -and
        $bytes[1] -eq 0xBB -and
        $bytes[2] -eq 0xBF
    ) {
        throw "UTF-8 BOM não permitido: $Path"
    }
    $strictUtf8 = New-Object System.Text.UTF8Encoding($false, $true)
    try {
        $null = $strictUtf8.GetString($bytes)
    }
    catch {
        throw "UTF-8 inválido: $Path"
    }
}

$ProjectRoot = ConvertTo-NormalizedPath `
    -Value $ProjectRoot `
    -Name "Raiz do projeto" `
    -ExistingType "Directory"
if (-not $Destination) {
    $Destination = [System.IO.Path]::Combine(
        $env:APPDATA,
        "Blackmagic Design",
        "DaVinci Resolve",
        "Support",
        "Fusion",
        "Scripts",
        "Utility"
    )
}
$Destination = ConvertTo-NormalizedPath -Value $Destination -Name "Destino do launcher"
if (-not $PythonExecutable) {
    $PythonExecutable = [System.IO.Path]::Combine(
        $ProjectRoot,
        ".venv",
        "Scripts",
        "python.exe"
    )
}
$PythonExecutable = ConvertTo-NormalizedPath `
    -Value $PythonExecutable `
    -Name "Python da virtual environment" `
    -ExistingType "File"

$version = & $PythonExecutable -c `
    'import struct,sys; print(str(sys.version_info.major)+chr(46)+str(sys.version_info.minor)+chr(124)+str(struct.calcsize(chr(80))*8))'
if ($LASTEXITCODE -ne 0 -or $version.Trim() -ne "3.11|64") {
    throw "O launcher exige Python 3.11 x64; encontrado: $version"
}

$launcherDirectory = [System.IO.Path]::Combine($ProjectRoot, "launcher")
$commonSource = ConvertTo-NormalizedPath `
    -Value ([System.IO.Path]::Combine($launcherDirectory, "internal_common.lua")) `
    -Name "Biblioteca Lua interna" `
    -ExistingType "File"
$diagnosticName = [string]::Concat("O Editor - Diagn", [char]0x00F3, "stico.lua")
$luaNames = @(
    "O Editor - Teste de Menu.lua",
    $diagnosticName,
    "O Editor - Abrir.lua",
    "O Editor - Capability Probe.lua",
    "O Editor - Aplicar Plano.lua",
    "O Editor - Aplicar Rough Cut.lua"
)
$luaSources = foreach ($name in $luaNames) {
    ConvertTo-NormalizedPath `
        -Value ([System.IO.Path]::Combine($launcherDirectory, $name)) `
        -Name "Script interno $name" `
        -ExistingType "File"
}
$menuSource = [IO.Path]::Combine($launcherDirectory, "O EDITOR.lua")
foreach ($path in @($commonSource, $menuSource) + @($luaSources)) {
    Assert-Utf8NoBom -Path ([string]$path)
}

# Derive the release from the installed source, never a duplicated constant.
$sourceCommonText = [IO.File]::ReadAllText($commonSource, [Text.Encoding]::UTF8)
$sourceVersionMatch = [regex]::Match($sourceCommonText, 'M.COMMON_VERSION = "([^"]+)"')
$sourceBuildMatch = [regex]::Match($sourceCommonText, 'M.COMMON_HASH = "([^"]+)"')
if (-not $sourceVersionMatch.Success -or -not $sourceBuildMatch.Success) {
    throw "Biblioteca Lua sem identificacao de versao/build valida."
}
$sourceScriptVersion = $sourceVersionMatch.Groups[1].Value
$sourceBuildHash = $sourceBuildMatch.Groups[1].Value
foreach ($sourceLua in $luaSources) {
    $sourceLuaText = [IO.File]::ReadAllText($sourceLua, [Text.Encoding]::UTF8)
    $luaVersion = [regex]::Match($sourceLuaText, 'local SCRIPT_VERSION = "([^"]+)"')
    $luaBuild = [regex]::Match($sourceLuaText, 'local BUILD_HASH = "([^"]+)"')
    if (-not $luaVersion.Success -or -not $luaBuild.Success -or
        $luaVersion.Groups[1].Value -ne $sourceScriptVersion -or
        $luaBuild.Groups[1].Value -ne $sourceBuildHash) {
        throw "Os helpers Lua pertencem a versoes diferentes: $sourceLua"
    }
}

[System.IO.Directory]::CreateDirectory($Destination) | Out-Null
$configurationDirectory = [System.IO.Path]::Combine($env:APPDATA, "O Editor")
$legacyDirectory = [System.IO.Path]::Combine($configurationDirectory, "legacy")
foreach ($directory in @(
    $configurationDirectory,
    $legacyDirectory,
    ([System.IO.Path]::Combine($configurationDirectory, "logs")),
    ([System.IO.Path]::Combine($configurationDirectory, "requests")),
    ([System.IO.Path]::Combine($configurationDirectory, "requests", "processed")),
    ([System.IO.Path]::Combine($configurationDirectory, "reports")),
    ([System.IO.Path]::Combine($configurationDirectory, "plans"))
)) {
    [System.IO.Directory]::CreateDirectory($directory) | Out-Null
}

$legacyPython = [System.IO.Path]::Combine($Destination, "O Editor.py")
if ([System.IO.File]::Exists($legacyPython)) {
    $legacyTarget = [System.IO.Path]::Combine($legacyDirectory, "O Editor.py")
    if ([System.IO.File]::Exists($legacyTarget)) {
        $archiveName = "O Editor-{0}.py" -f (Get-Date -Format "yyyyMMdd-HHmmss")
        $archivePath = [System.IO.Path]::Combine($legacyDirectory, $archiveName)
        [System.IO.File]::Move($legacyTarget, $archivePath)
        Write-Host "Backup legado anterior: $archivePath"
    }
    [System.IO.File]::Move($legacyPython, $legacyTarget)
    Write-Host "Launcher Python legado movido: $legacyTarget"
}

foreach ($obsoleteName in @("O Editor.lua", "O Editor - Diagnostico.lua")) {
    $obsoletePath = [System.IO.Path]::Combine($Destination, $obsoleteName)
    if ([System.IO.File]::Exists($obsoletePath)) {
        $legacyTarget = [System.IO.Path]::Combine($legacyDirectory, $obsoleteName)
        if ([System.IO.File]::Exists($legacyTarget)) {
            $legacyTarget = [System.IO.Path]::Combine(
                $legacyDirectory,
                (([System.IO.Path]::GetFileNameWithoutExtension($obsoleteName)) +
                    "-" + (Get-Date -Format "yyyyMMdd-HHmmss") +
                    ([System.IO.Path]::GetExtension($obsoleteName)))
            )
        }
        [System.IO.File]::Move($obsoletePath, $legacyTarget)
        Write-Host "Script obsoleto movido: $legacyTarget"
    }
}

# Keep only the entry point public. Helpers are not scanned by Resolve's menu.
$internalScripts = [IO.Path]::Combine($configurationDirectory, "internal-scripts")
[IO.Directory]::CreateDirectory($internalScripts) | Out-Null
foreach ($name in $luaNames) {
    $oldMenuPath = [IO.Path]::Combine($Destination, $name)
    if ([IO.File]::Exists($oldMenuPath)) {
        $archive = [IO.Path]::Combine($legacyDirectory, ([guid]::NewGuid().ToString("N") + "-" + $name))
        [IO.File]::Move($oldMenuPath, $archive)
    }
}
$installedPairs = [System.Collections.Generic.List[object]]::new()
$menuInstalled = [IO.Path]::Combine($Destination, "O EDITOR.lua")
[IO.File]::Copy($menuSource, $menuInstalled, $true)
$installedPairs.Add([pscustomobject]@{ name = "O EDITOR.lua"; source = $menuSource; installed = $menuInstalled })
for ($index = 0; $index -lt $luaNames.Count; $index++) {
    $installed = [System.IO.Path]::Combine($internalScripts, $luaNames[$index])
    [System.IO.File]::Copy([string]$luaSources[$index], $installed, $true)
    $installedPairs.Add([pscustomobject]@{
        name = $luaNames[$index]
        source = [string]$luaSources[$index]
        installed = $installed
    })
}
$installedCommon = [System.IO.Path]::Combine(
    $configurationDirectory,
    "internal_common.lua"
)
[System.IO.File]::Copy($commonSource, $installedCommon, $true)
$installedPairs.Add([pscustomobject]@{
    name = "internal_common.lua"
    source = $commonSource
    installed = $installedCommon
})

$artifacts = [ordered]@{}
foreach ($pair in $installedPairs) {
    Assert-Utf8NoBom -Path $pair.installed
    $sourceHash = Get-FileSha256 -Path $pair.source
    $installedHash = Get-FileSha256 -Path $pair.installed
    if ($sourceHash -ne $installedHash) {
        throw "SHA-256 divergente após instalação: $($pair.installed)"
    }
    $artifacts[$pair.name] = [ordered]@{
        source_sha256 = $sourceHash
        installed_sha256 = $installedHash
    }
    Write-Host "Instalado: $($pair.installed)"
    Write-Host "SHA-256: $installedHash"
}

$configurationPath = [System.IO.Path]::Combine(
    $configurationDirectory,
    "launcher.json"
)
$resolveRunning = $null -ne (Get-Process -Name "Resolve" -ErrorAction SilentlyContinue)
$configuration = [ordered]@{
    schema_version = 1
    project_root = $ProjectRoot
    python_executable = $PythonExecutable
    module = "o_editor"
    internal_host_enabled = $true
    external_bridge_enabled = $false
    installed_at = (Get-Date).ToString("o")
    resolve_was_running = $resolveRunning
    script_version = $sourceScriptVersion
    build_hash = $sourceBuildHash
    artifacts = $artifacts
}
[System.IO.File]::WriteAllText(
    $configurationPath,
    ($configuration | ConvertTo-Json -Depth 8),
    (New-Object Text.UTF8Encoding($false))
)

$launchCommandPath = [System.IO.Path]::Combine(
    $configurationDirectory,
    "launch-editor.cmd"
)
$commandLines = @(
    "@echo off",
    "setlocal",
    "chcp 65001 >nul",
    "set `"PYTHONUTF8=1`"",
    "set `"ROOT=$ProjectRoot`"",
    "set `"PYTHON=$PythonExecutable`"",
    "set `"MODULE=o_editor`"",
    "set `"LOG=$configurationDirectory\launcher-external.log`"",
    "if `"%~1`"==`"`" exit /b 2",
    "set `"PYTHONPATH=%ROOT%\src;%PYTHONPATH%`"",
    "if exist `"%ROOT%\tools\ffmpeg\bin\ffmpeg.exe`" set `"PATH=%ROOT%\tools\ffmpeg\bin;%PATH%`"",
    "rem Encaminha todos os argumentos, incluindo --internal-action-request.",
    "start `"`" /b `"%PYTHON%`" -m `"%MODULE%`" %* >> `"%LOG%`" 2>&1",
    "exit /b %ERRORLEVEL%"
)
[System.IO.File]::WriteAllLines(
    $launchCommandPath,
    $commandLines,
    (New-Object Text.UTF8Encoding($false))
)
Assert-Utf8NoBom -Path $configurationPath
Assert-Utf8NoBom -Path $launchCommandPath

if ([System.IO.File]::Exists($legacyPython)) {
    throw "O launcher Python legado ainda está instalado no Utility."
}
# The technical Workflow Integration is not a second public entry point.
$standardDestination = [IO.Path]::Combine($env:APPDATA, "Blackmagic Design", "DaVinci Resolve", "Support", "Fusion", "Scripts", "Utility")
if ($Destination -eq $standardDestination) {
    $pluginManifest = [IO.Path]::Combine($env:PROGRAMDATA, "Blackmagic Design", "DaVinci Resolve", "Support", "Workflow Integration Plugins", "com.oeditor.resolve.internalhost", "manifest.xml")
    if ([IO.File]::Exists($pluginManifest)) {
        $manifestBackup = [IO.Path]::Combine($legacyDirectory, ("workflow-manifest-" + [guid]::NewGuid().ToString("N") + ".xml"))
        [IO.File]::Move($pluginManifest, $manifestBackup)
        Write-Host "Host técnico retirado do menu; manifesto preservado em: $manifestBackup"
    }
}
Write-Host "Configuração instalada: $configurationPath"
Write-Host "Comando externo: $launchCommandPath"
Write-Host "Requests: $configurationDirectory\requests"
Write-Host "Logs: $configurationDirectory\logs"
Write-Host "Relatórios: $configurationDirectory\reports"
Write-Host "Bridge externa: desabilitada"
if ($resolveRunning) {
    Write-Host "Scripts atualizados. Reinicie o DaVinci Resolve antes do teste manual."
}
else {
    Write-Host "Scripts atualizados. Abra o DaVinci Resolve para o teste manual."
}
