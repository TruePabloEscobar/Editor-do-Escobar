[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA "O Editor"),
    [string]$LauncherPath = (Join-Path $env:APPDATA "Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility\O EDITOR.lua"),
    [switch]$RemoveUserConfig
)

$ErrorActionPreference = "Stop"

function Assert-SafeChildPath {
    param(
        [Parameter(Mandatory = $true)][string]$Target,
        [Parameter(Mandatory = $true)][string]$AllowedRoot
    )
    $targetFull = [IO.Path]::GetFullPath($Target).TrimEnd('\')
    $rootFull = [IO.Path]::GetFullPath($AllowedRoot).TrimEnd('\')
    if ($targetFull -eq $rootFull -or -not $targetFull.StartsWith($rootFull + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Alvo inseguro fora da raiz permitida: $targetFull"
    }
    return $targetFull
}

$safeInstallRoot = Assert-SafeChildPath -Target $InstallRoot -AllowedRoot $env:LOCALAPPDATA
$safeLauncherPath = Assert-SafeChildPath -Target $LauncherPath -AllowedRoot $env:APPDATA

if ((Test-Path -LiteralPath $safeInstallRoot) -and $PSCmdlet.ShouldProcess($safeInstallRoot, "Remover instalação")) {
    Remove-Item -LiteralPath $safeInstallRoot -Recurse -Force
}

if ((Test-Path -LiteralPath $safeLauncherPath) -and $PSCmdlet.ShouldProcess($safeLauncherPath, "Remover launcher")) {
    Remove-Item -LiteralPath $safeLauncherPath -Force
}

if ($RemoveUserConfig) {
    $configDir = Assert-SafeChildPath -Target (Join-Path $env:APPDATA "O Editor") -AllowedRoot $env:APPDATA
    if ((Test-Path -LiteralPath $configDir) -and $PSCmdlet.ShouldProcess($configDir, "Remover configuração do usuário")) {
        Remove-Item -LiteralPath $configDir -Recurse -Force
    }
}

$configuredHome = [Environment]::GetEnvironmentVariable("O_EDITOR_HOME", "User")
if ($configuredHome -and ([IO.Path]::GetFullPath($configuredHome) -eq [IO.Path]::GetFullPath($safeInstallRoot))) {
    [Environment]::SetEnvironmentVariable("O_EDITOR_HOME", $null, "User")
    [Environment]::SetEnvironmentVariable("O_EDITOR_CONFIG", $null, "User")
}

Write-Host "O Editor foi removido."
if (-not $RemoveUserConfig) {
    Write-Host "A configuração do usuário foi preservada. Use -RemoveUserConfig para removê-la."
}

