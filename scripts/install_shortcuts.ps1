[CmdletBinding()]
param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [string[]]$DestinationDirectories
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object Text.UTF8Encoding($false)
$ProjectRoot = [IO.Path]::GetFullPath($ProjectRoot)
$python = Join-Path $ProjectRoot '.venv\Scripts\pythonw.exe'
if (-not [IO.File]::Exists($python)) {
    throw "Python do aplicativo não encontrado: $python"
}
if (-not $DestinationDirectories) {
    $DestinationDirectories = @(
        [Environment]::GetFolderPath('DesktopDirectory'),
        (Join-Path ([Environment]::GetFolderPath('Programs')) 'O Editor')
    )
}
$shell = New-Object -ComObject WScript.Shell
foreach ($directory in $DestinationDirectories) {
    if ([string]::IsNullOrWhiteSpace($directory)) { throw 'Destino de atalho inválido.' }
    [IO.Directory]::CreateDirectory($directory) | Out-Null
    $path = Join-Path $directory 'O EDITOR.lnk'
    $shortcut = $shell.CreateShortcut($path)
    $shortcut.TargetPath = $python
    $shortcut.Arguments = '-m o_editor'
    $shortcut.WorkingDirectory = $ProjectRoot
    $shortcut.Description = 'O EDITOR - transcrição, revisão e cortes'
    $shortcut.IconLocation = "$python,0"
    $shortcut.Save()
    $verified = $shell.CreateShortcut($path)
    if ($verified.TargetPath -ne $python -or $verified.Arguments -ne '-m o_editor' -or
        $verified.WorkingDirectory -ne $ProjectRoot) {
        throw "Falha ao verificar o atalho: $path"
    }
    Write-Host "Atalho verificado: $path"
}
