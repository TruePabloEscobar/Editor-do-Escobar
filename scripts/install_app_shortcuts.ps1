[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$ProjectRoot,
    [string[]]$Destination
)
# Standalone access for both editions: Desktop and Start menu open the EDE directly,
# without depending on Resolve scripting (unavailable to external apps in Resolve Free).
$ErrorActionPreference = 'Stop'
$env:PSModulePath = (Join-Path $env:WINDIR 'System32/WindowsPowerShell/v1.0/Modules') + ';' + (Join-Path $env:ProgramFiles 'WindowsPowerShell/Modules')
[Console]::OutputEncoding = New-Object Text.UTF8Encoding($false)
$ProjectRoot = [IO.Path]::GetFullPath($ProjectRoot)
$target = Join-Path $ProjectRoot 'Editor Do Escobar.exe'
$arguments = ''
if (-not [IO.File]::Exists($target)) {
    # Source package without the compiled launcher keeps the existing batch entry point.
    $target = Join-Path $ProjectRoot 'O Editor.cmd'
}
if (-not [IO.File]::Exists($target)) { throw "Ponto de entrada do EDE ausente: $target" }
$programs = [Environment]::GetFolderPath('Programs')
if (-not $Destination) {
    $Destination = @([Environment]::GetFolderPath('DesktopDirectory'), $programs)
    # Older Free installers created this entry pointing to O Editor.cmd; replace it.
    $legacy = Join-Path $programs 'EDE - Editor Do Escobar.lnk'
    if ([IO.File]::Exists($legacy)) { [IO.File]::Delete($legacy) }
}
$shell = New-Object -ComObject WScript.Shell
foreach ($directory in $Destination) {
    if ([string]::IsNullOrWhiteSpace($directory)) { throw 'Destino de atalho invalido.' }
    [IO.Directory]::CreateDirectory($directory) | Out-Null
    $path = Join-Path $directory 'Editor Do Escobar.lnk'
    $shortcut = $shell.CreateShortcut($path)
    $shortcut.TargetPath = $target
    $shortcut.Arguments = $arguments
    $shortcut.WorkingDirectory = $ProjectRoot
    $shortcut.Description = 'EDE - Editor Do Escobar'
    $shortcut.IconLocation = "$target,0"
    $shortcut.Save()
    $verified = $shell.CreateShortcut($path)
    if ($verified.TargetPath -ne $target -or $verified.WorkingDirectory -ne $ProjectRoot) {
        throw "Falha ao verificar o atalho: $path"
    }
    Write-Host "Atalho verificado: $path"
}
