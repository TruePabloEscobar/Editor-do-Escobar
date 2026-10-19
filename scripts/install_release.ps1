[CmdletBinding()]
param(
    [string]$SourceRoot,
    [string]$PythonPath,
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA "Editor Do Escobar\releases"),
    [string]$LauncherDestination,
    [switch]$ValidateOnly,
    [switch]$OfflineDependencies
)
$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"
if (-not $SourceRoot) { $SourceRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path) }
$SourceRoot = [IO.Path]::GetFullPath($SourceRoot)
$manifestPath = Join-Path $SourceRoot "package-manifest.json"
if (-not (Test-Path -LiteralPath $manifestPath)) { throw "Extraia o ZIP completo antes de instalar." }
$manifest = Get-Content -Raw -LiteralPath $manifestPath -Encoding UTF8 | ConvertFrom-Json
if ($manifest.format -ne 1 -or $manifest.version -notmatch '^\d+\.\d+\.\d+$' -or
    $manifest.build -notmatch '^[0-9a-f]{12}$') { throw "Manifesto de pacote invalido." }
$files = @($manifest.files.PSObject.Properties)
foreach ($entry in $files) {
    $path = [IO.Path]::GetFullPath((Join-Path $SourceRoot $entry.Name))
    if (-not $path.StartsWith($SourceRoot.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Caminho inseguro no pacote."
    }
    if (-not [IO.File]::Exists($path) -or
        (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.Value) {
        throw "Arquivo ausente ou alterado no pacote: $($entry.Name)"
    }
}
if ($ValidateOnly) { Write-Host "Pacote integro: $($files.Count) arquivos."; return }
if (-not $PythonPath) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $PythonPath = & py -3.11 -c 'import sys; print(sys.executable)'
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        $PythonPath = (Get-Command python).Source
    }
}
if (-not $PythonPath) { throw "Instale Python 3.11 x64: https://www.python.org/downloads/" }
$version = & $PythonPath -c 'import struct,sys; print(str(sys.version_info.major)+chr(46)+str(sys.version_info.minor)+chr(124)+str(struct.calcsize(chr(80))*8))'
if ($LASTEXITCODE -ne 0 -or $version.Trim() -ne '3.11|64') { throw "Python 3.11 x64 obrigatorio." }
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue) -or
    -not (Get-Command ffprobe -ErrorAction SilentlyContinue)) {
    throw "Instale FFmpeg e ffprobe no PATH. Exemplo: winget install Gyan.FFmpeg"
}
$destination = Join-Path ([IO.Path]::GetFullPath($InstallRoot)) ($manifest.version + '-' + $manifest.build)
if ($SourceRoot -eq $destination) { throw "Extraia o pacote fora do destino de instalacao." }
$running = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -match '^pythonw?\.exe$' -and $_.CommandLine -like "*$destination*"
}
if ($running) { throw "Feche o EDE antes de reinstalar esta mesma versao." }
[IO.Directory]::CreateDirectory($destination) | Out-Null
foreach ($entry in $files) {
    $target = Join-Path $destination $entry.Name
    [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($target)) | Out-Null
    Copy-Item -LiteralPath (Join-Path $SourceRoot $entry.Name) -Destination $target -Force
}
Copy-Item -LiteralPath $manifestPath -Destination (Join-Path $destination 'package-manifest.json') -Force
$python = Join-Path $destination '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    & $PythonPath -m venv (Join-Path $destination '.venv')
    if ($LASTEXITCODE -ne 0) { throw "Falha ao criar o ambiente Python." }
}
# Editable install preserves the composition root, config, assets and Lua helpers together.
if (-not $OfflineDependencies) {
    & $python -m pip install --upgrade 'pip>=26.2' 'setuptools>=83'
    if ($LASTEXITCODE -ne 0) { throw "Falha ao atualizar ferramentas de instalacao; menu preservado." }
}
$pipArgs = @('-m', 'pip', 'install', '-e', "${destination}[whisper]", '-c',
    (Join-Path $destination 'requirements\runtime-windows.txt'))
if ($OfflineDependencies) { $pipArgs += @('--no-index', '--no-build-isolation') }
& $python @pipArgs
if ($LASTEXITCODE -ne 0) { throw "Instalacao de dependencias falhou. O menu anterior foi preservado." }
& $python -m pip check
if ($LASTEXITCODE -ne 0) { throw "Dependencias inconsistentes; instalacao interrompida." }
$launcherArgs = @{ProjectRoot=$destination; PythonExecutable=$python}
$verifyArgs = @{ProjectRoot=$destination; SkipProcessStart=$true}
if ($LauncherDestination) {
    $launcherArgs.Destination=$LauncherDestination
    $verifyArgs.Destination=$LauncherDestination
}
& (Join-Path $destination 'scripts\install_launcher.ps1') @launcherArgs
& (Join-Path $destination 'scripts\verify_launcher_installation.ps1') @verifyArgs
Write-Host "EDE instalado em: $destination"
Write-Host "Reabra o Resolve. Area de Trabalho > Scripts > O EDITOR."
Write-Host "Engrenagem > Baixar modelo para configurar a transcricao."
Write-Host "Configuracoes, sessoes, modelos e versoes anteriores foram preservados."
