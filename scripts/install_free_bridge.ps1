[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$ProjectRoot,
    [Parameter(Mandatory=$true)][string]$PythonExecutable,
    [string]$Destination,
    [switch]$SkipShortcut
)
$ErrorActionPreference = 'Stop'
$env:PSModulePath = (Join-Path $env:WINDIR 'System32/WindowsPowerShell/v1.0/Modules') + ';' + (Join-Path $env:ProgramFiles 'WindowsPowerShell/Modules')
[Console]::OutputEncoding = New-Object Text.UTF8Encoding($false)
$OutputEncoding = [Console]::OutputEncoding
$env:PYTHONUTF8 = '1'
$ProjectRoot = [IO.Path]::GetFullPath($ProjectRoot)
if (-not $Destination) {
    $Destination = Join-Path $env:APPDATA 'Blackmagic Design/DaVinci Resolve/Support/Fusion/Scripts/Utility'
}
$Destination = [IO.Path]::GetFullPath($Destination)
$base = Join-Path $env:APPDATA 'O Editor'
$mailbox = Join-Path $base 'free-bridge'
[IO.Directory]::CreateDirectory($mailbox) | Out-Null
[IO.Directory]::CreateDirectory($Destination) | Out-Null
$target = Join-Path $Destination 'EDE Bridge.lua'
$stage = Join-Path $mailbox ('bridge-' + [Guid]::NewGuid().ToString('N') + '.lua')
& $PythonExecutable (Join-Path $ProjectRoot 'src/o_editor/infrastructure/resolve/bridge_bundle.py') --root $ProjectRoot --mailbox $mailbox --output $stage
if ($LASTEXITCODE -ne 0 -or -not [IO.File]::Exists($stage)) { throw 'Falha ao gerar EDE Bridge. Integracao anterior preservada.' }
if ([IO.File]::Exists($target)) {
    $backup = Join-Path $mailbox ('backups/' + [Guid]::NewGuid().ToString('N') + '.lua')
    [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($backup)) | Out-Null
    Copy-Item -LiteralPath $target -Destination $backup
    if ((Get-FileHash -LiteralPath $backup).Hash -ne (Get-FileHash -LiteralPath $target).Hash) { throw 'Backup do Bridge divergente.' }
}
Copy-Item -LiteralPath $stage -Destination $target -Force
if ((Get-FileHash -LiteralPath $stage).Hash -ne (Get-FileHash -LiteralPath $target).Hash) { throw 'Bridge instalado divergente.' }
[IO.File]::Delete($stage)
if (-not $SkipShortcut) {
    $shortcutPath = Join-Path ([Environment]::GetFolderPath('Programs')) 'EDE - Editor Do Escobar.lnk'
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = Join-Path $ProjectRoot 'O Editor.cmd'
    $shortcut.WorkingDirectory = $ProjectRoot
    $shortcut.Description = 'EDE. Inicie EDE Bridge no Resolve e clique em Atualizar timeline.'
    $shortcut.Save()
}
Write-Host "EDE Bridge instalado e hash conferido: $target"
Write-Host 'Abra o EDE pelo menu Iniciar. No Resolve: Workspace > Scripts > EDE Bridge. No EDE: Atualizar timeline.'
