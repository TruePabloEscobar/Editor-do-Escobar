[CmdletBinding()]
param(
    [string]$PythonPath = "python",
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA "O Editor"),
    [string]$SourceRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$LauncherDestination,
    [switch]$SkipEnvironmentPersistence
)

$ErrorActionPreference = "Stop"

Write-Host "O Editor - instalação local"
Write-Host "Origem: $SourceRoot"
Write-Host "Destino: $InstallRoot"

if (-not (Test-Path -LiteralPath (Join-Path $SourceRoot "pyproject.toml"))) {
    throw "pyproject.toml não encontrado em $SourceRoot"
}

try {
    $version = & $PythonPath -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
}
catch {
    throw "Python 3.11 não foi encontrado. Informe -PythonPath com o executável correto."
}

if ($LASTEXITCODE -ne 0 -or $version.Trim() -ne "3.11") {
    throw "Esta versão exige Python 3.11; encontrado: $version"
}

$venvPath = Join-Path $InstallRoot ".venv"
$venvPython = Join-Path $venvPath "Scripts\python.exe"
New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null

if (-not (Test-Path -LiteralPath $venvPython)) {
    & $PythonPath -m venv $venvPath
    if ($LASTEXITCODE -ne 0) { throw "Falha ao criar o ambiente Python." }
}

& $venvPython -m pip install --upgrade 'pip>=26.2' 'setuptools>=83'
if ($LASTEXITCODE -ne 0) { throw "Falha ao preparar pip." }
$packageSpec = "${SourceRoot}[whisper]"
& $venvPython -m pip install -e $packageSpec
if ($LASTEXITCODE -ne 0) { throw "Falha ao instalar as dependências; launcher preservado." }

$userConfigDir = Join-Path $env:APPDATA "O Editor"
$userConfig = Join-Path $userConfigDir "config.json"
New-Item -ItemType Directory -Force -Path $userConfigDir | Out-Null
if (-not (Test-Path -LiteralPath $userConfig)) {
    Copy-Item -LiteralPath (Join-Path $SourceRoot "config\defaults.json") -Destination $userConfig
}

$launcherArgs = @{
    ProjectRoot = $SourceRoot
    PythonExecutable = $venvPython
}
if ($LauncherDestination) {
    $launcherArgs.Destination = $LauncherDestination
}
& (Join-Path $SourceRoot "scripts\install_launcher.ps1") @launcherArgs

if (-not $SkipEnvironmentPersistence) {
    [Environment]::SetEnvironmentVariable("O_EDITOR_HOME", $InstallRoot, "User")
    [Environment]::SetEnvironmentVariable("O_EDITOR_CONFIG", $userConfig, "User")
}

$ffmpeg = Get-Command ffmpeg -ErrorAction SilentlyContinue
$resolve = Join-Path $env:PROGRAMFILES "Blackmagic Design\DaVinci Resolve\Resolve.exe"
$resolveDocs = Join-Path $env:PROGRAMDATA "Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting\README.txt"

Write-Host ""
Write-Host "Instalação concluída."
Write-Host "Aplicativo: $(Join-Path $venvPath 'Scripts\o-editor.exe')"
Write-Host "Configuração: $userConfig"
Write-Host "FFmpeg: $(if ($ffmpeg) { $ffmpeg.Source } else { 'não encontrado; instale e adicione ao PATH' })"
Write-Host "Resolve: $(if (Test-Path -LiteralPath $resolve) { $resolve } else { 'não encontrado' })"
Write-Host "Documentação Resolve: $(if (Test-Path -LiteralPath $resolveDocs) { $resolveDocs } else { 'não encontrada' })"
Write-Host ""
Write-Host "Nenhum modelo Whisper foi baixado automaticamente."
Write-Host "Configure transcription.model_path no arquivo de usuário antes da transcrição real."
Write-Host "Execute scripts\doctor.ps1 para o diagnóstico completo."
