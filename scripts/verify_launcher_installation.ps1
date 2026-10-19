[CmdletBinding()]
param(
    [string]$Destination,
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [switch]$SkipProcessStart
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = New-Object Text.UTF8Encoding($false)
$OutputEncoding = [Console]::OutputEncoding
$env:PYTHONUTF8 = "1"

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

$ProjectRoot = [System.IO.Path]::GetFullPath(
    $ProjectRoot.Trim().Trim([char[]]@(34, 39))
)
if (-not [System.IO.Directory]::Exists($ProjectRoot)) {
    throw "Raiz do projeto não encontrada: $ProjectRoot"
}
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
$Destination = [System.IO.Path]::GetFullPath(
    $Destination.Trim().Trim([char[]]@(34, 39))
)
$configurationDirectory = [System.IO.Path]::Combine($env:APPDATA, "O Editor")
$configurationPath = [System.IO.Path]::Combine($configurationDirectory, "launcher.json")
$launchCommandPath = [System.IO.Path]::Combine($configurationDirectory, "launch-editor.cmd")
$commonInstalled = [System.IO.Path]::Combine($configurationDirectory, "internal_common.lua")
$diagnosticName = [string]::Concat("O Editor - Diagn", [char]0x00F3, "stico.lua")
$luaNames = @(
    "O Editor - Teste de Menu.lua",
    $diagnosticName,
    "O Editor - Abrir.lua",
    "O Editor - Capability Probe.lua",
    "O Editor - Aplicar Plano.lua",
    "O Editor - Aplicar Rough Cut.lua"
)

foreach ($obsolete in @("O Editor.py", "O Editor - Diagnostico.lua")) {
    $obsoletePath = [System.IO.Path]::Combine($Destination, $obsolete)
    if ([System.IO.File]::Exists($obsoletePath)) {
        throw "Script obsoleto ainda instalado: $obsoletePath"
    }
}

$internalScripts = [IO.Path]::Combine($configurationDirectory, "internal-scripts")
$pairs = [System.Collections.Generic.List[object]]::new()
$pairs.Add([pscustomobject]@{
    source = [IO.Path]::Combine($ProjectRoot, "launcher", "O EDITOR.lua")
    installed = [IO.Path]::Combine($Destination, "O EDITOR.lua")
})
$publicScripts = @(Get-ChildItem -LiteralPath $Destination -File | Where-Object {
    $_.Name -match '(?i)^O[ _-]*Editor.*\.(lua|py)$'
})
if ($publicScripts.Count -ne 1 -or $publicScripts[0].Name -cne "O EDITOR.lua") {
    throw "O menu deve conter somente O EDITOR.lua."
}
foreach ($name in $luaNames) {
    $pairs.Add([pscustomobject]@{
        source = [System.IO.Path]::Combine($ProjectRoot, "launcher", $name)
        installed = [System.IO.Path]::Combine($internalScripts, $name)
    })
}
$pairs.Add([pscustomobject]@{
    source = [System.IO.Path]::Combine($ProjectRoot, "launcher", "internal_common.lua")
    installed = $commonInstalled
})
foreach ($pair in $pairs) {
    if (-not [System.IO.File]::Exists($pair.source)) {
        throw "Fonte não encontrada: $($pair.source)"
    }
    if (-not [System.IO.File]::Exists($pair.installed)) {
        throw "Arquivo instalado não encontrado: $($pair.installed)"
    }
    Assert-Utf8NoBom -Path $pair.source
    Assert-Utf8NoBom -Path $pair.installed
    $sourceHash = Get-FileSha256 -Path $pair.source
    $installedHash = Get-FileSha256 -Path $pair.installed
    if ($sourceHash -ne $installedHash) {
        throw "SHA-256 divergente: $($pair.installed)"
    }
    Write-Host "[OK] SHA-256 $sourceHash  $($pair.installed)"
}

if (-not [System.IO.File]::Exists($configurationPath)) {
    throw "Configuração não encontrada: $configurationPath"
}
Assert-Utf8NoBom -Path $configurationPath
Assert-Utf8NoBom -Path $launchCommandPath
try {
    $configuration = [System.IO.File]::ReadAllText(
        $configurationPath,
        [System.Text.Encoding]::UTF8
    ) | ConvertFrom-Json
}
catch {
    throw "launcher.json inválido: $($_.Exception.Message)"
}
if (
    $configuration.schema_version -ne 1 -or
    $configuration.module -ne "o_editor" -or
    $configuration.internal_host_enabled -ne $true -or
    $configuration.external_bridge_enabled -ne $false
) {
    throw "Configuração do launcher incompatível."
}
if (-not [System.IO.Directory]::Exists($configuration.project_root)) {
    throw "Raiz configurada não existe: $($configuration.project_root)"
}
if (-not [System.IO.File]::Exists($configuration.python_executable)) {
    throw "Python configurado não existe: $($configuration.python_executable)"
}
if (-not [System.IO.Directory]::Exists(
    [System.IO.Path]::Combine($configuration.project_root, ".venv")
)) {
    throw "A virtual environment configurada não existe."
}

$version = & $configuration.python_executable -c `
    'import struct,sys; print(str(sys.version_info.major)+chr(46)+str(sys.version_info.minor)+chr(124)+str(struct.calcsize(chr(80))*8))'
if ($LASTEXITCODE -ne 0 -or $version.Trim() -ne "3.11|64") {
    throw "Python configurado não é 3.11 x64: $version"
}
& $configuration.python_executable -c "import o_editor; print(o_editor.__version__)"
if ($LASTEXITCODE -ne 0) {
    throw "O pacote o_editor não pode ser importado pelo Python configurado."
}

$loadedUi = & $configuration.python_executable -c "import o_editor.ui.main_window as ui; print(ui.__file__)"
$expectedUi = [IO.Path]::Combine($configuration.project_root, "src", "o_editor", "ui", "main_window.py")
if ($LASTEXITCODE -ne 0 -or [IO.Path]::GetFullPath($loadedUi.Trim()) -ne $expectedUi) {
    throw "O Python não está carregando a interface do checkout configurado: $loadedUi"
}
Write-Host "[OK] Interface atual: $loadedUi"

$commandText = [System.IO.File]::ReadAllText(
    $launchCommandPath,
    [System.Text.Encoding]::UTF8
)
foreach ($required in @(
    "--internal-action-request",
    "%*",
    [string]$configuration.python_executable,
    [string]$configuration.project_root
)) {
    if (-not $commandText.Contains($required)) {
        throw "launch-editor.cmd não contém o valor obrigatório: $required"
    }
}

foreach ($name in $luaNames) {
    $luaPath = [System.IO.Path]::Combine($internalScripts, $name)
    $luaText = [System.IO.File]::ReadAllText($luaPath, [System.Text.Encoding]::UTF8)
    foreach ($required in @(
        "SCRIPT_VERSION",
        "BUILD_HASH",
        "xpcall",
        "run_internal_action"
    )) {
        if (-not $luaText.Contains($required)) {
            throw "Script Lua não contém $required`: $luaPath"
        }
    }
    if (
        $luaText -match
        "(?i)DaVinciResolveScript|scriptapp|fusionscript\.dll|PySide6|faster[_-]whisper|ctranslate2"
    ) {
        throw "Script Lua contém dependência proibida: $luaPath"
    }
    $scriptVersion = [regex]::Match(
        $luaText,
        'local SCRIPT_VERSION = "([^"]+)"'
    )
    $buildHash = [regex]::Match(
        $luaText,
        'local BUILD_HASH = "([^"]+)"'
    )
    if (
        -not $scriptVersion.Success -or
        $scriptVersion.Groups[1].Value -ne $configuration.script_version
    ) {
        throw "SCRIPT_VERSION instalado diverge de launcher.json: $luaPath"
    }
    if (
        -not $buildHash.Success -or
        $buildHash.Groups[1].Value -ne $configuration.build_hash
    ) {
        throw "BUILD_HASH instalado diverge de launcher.json: $luaPath"
    }
}

$commonText = [System.IO.File]::ReadAllText(
    $commonInstalled,
    [System.Text.Encoding]::UTF8
)
$commonVersion = [regex]::Match($commonText, 'M.COMMON_VERSION = "([^"]+)"')
$commonHash = [regex]::Match($commonText, 'M.COMMON_HASH = "([^"]+)"')
if (
    -not $commonVersion.Success -or
    $commonVersion.Groups[1].Value -ne $configuration.script_version -or
    -not $commonHash.Success -or
    $commonHash.Groups[1].Value -ne $configuration.build_hash
) {
    throw "Versão/hash do helper instalado diverge de launcher.json."
}

foreach ($directoryName in @("requests", "logs", "plans", "reports")) {
    $path = [System.IO.Path]::Combine($configurationDirectory, $directoryName)
    if (-not [System.IO.Directory]::Exists($path)) {
        throw "Diretório obrigatório ausente: $path"
    }
}

$permissionTest = [System.IO.Path]::Combine(
    $configurationDirectory,
    "launcher-permission-test.tmp"
)
[System.IO.File]::WriteAllText(
    $permissionTest,
    "ok",
    (New-Object Text.UTF8Encoding($false))
)
[System.IO.File]::Delete($permissionTest)

if (-not $SkipProcessStart) {
    & $configuration.python_executable -m o_editor --self-test
    if ($LASTEXITCODE -ne 0) {
        throw "O self-test externo retornou $LASTEXITCODE."
    }
    & $configuration.python_executable -m o_editor.internal_actions.simulate menu_test
    if ($LASTEXITCODE -ne 0) {
        throw "O self-test IPC retornou $LASTEXITCODE."
    }
}

Write-Host "[OK] Configuração: $configurationPath"
Write-Host "[OK] Python: $version"
Write-Host "[OK] Projeto: $($configuration.project_root)"
Write-Host "[OK] launch-editor.cmd: $launchCommandPath"
Write-Host "[OK] Menu público: O EDITOR; auxiliares fora do menu: $($luaNames.Count)"
Write-Host "[OK] Launcher Python legado ausente do Utility"
Write-Host "[OK] IPC/self-test: $(if ($SkipProcessStart) { 'não executado por opção' } else { 'PASSED' })"
$resolveRunning = $null -ne (Get-Process -Name "Resolve" -ErrorAction SilentlyContinue)
if ($resolveRunning) {
    Write-Host "[MANUAL] Scripts atualizados. Reinicie o DaVinci Resolve antes do teste manual."
}
else {
    Write-Host "[MANUAL] Abra o Resolve e use Workspace > Scripts > Utility."
}
