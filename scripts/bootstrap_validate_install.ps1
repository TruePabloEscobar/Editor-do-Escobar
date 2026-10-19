[CmdletBinding()]
param(
    [string]$PythonPath,
    [switch]$RecreateVenv,
    [switch]$InstallDependencies,
    [switch]$InstallLauncher,
    [switch]$RunValidation,
    [switch]$StartResolve,
    [switch]$StartEditor,
    [switch]$Mock,
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = New-Object Text.UTF8Encoding($false)
$OutputEncoding = [Console]::OutputEncoding
$env:PYTHONUTF8 = "1"
$venv = Join-Path $ProjectRoot ".venv"
$venvPython = Join-Path $venv "Scripts\python.exe"

if ($RecreateVenv) {
    if (-not $PythonPath) {
        throw "-RecreateVenv exige -PythonPath apontando para Python 3.11 x64."
    }
    $resolvedPython = (Resolve-Path -LiteralPath $PythonPath).Path
    $runtime = & $resolvedPython -c 'import struct,sys; print(str(sys.version_info.major)+chr(46)+str(sys.version_info.minor)+chr(124)+str(struct.calcsize(chr(80))*8))'
    if ($runtime.Trim() -ne "3.11|64") {
        throw "Python 3.11 x64 obrigatório; encontrado: $runtime"
    }
    if (Test-Path -LiteralPath $venv) {
        $resolvedVenv = [IO.Path]::GetFullPath($venv)
        $resolvedRoot = [IO.Path]::GetFullPath($ProjectRoot).TrimEnd('\')
        if (-not $resolvedVenv.StartsWith($resolvedRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
            throw "Caminho de .venv inseguro: $resolvedVenv"
        }
        Remove-Item -LiteralPath $resolvedVenv -Recurse -Force
    }
    & $resolvedPython -m venv $venv
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "A .venv não existe. Use -RecreateVenv -PythonPath <python311>."
}

if ($InstallDependencies) {
    $packageSpec = "${ProjectRoot}[dev,whisper]"
    Write-Host "Instalando dependências autorizadas com: $venvPython"
    & $venvPython -m pip install -e $packageSpec
    if ($LASTEXITCODE -ne 0) {
        throw "A instalação das dependências falhou."
    }
}
if ($InstallLauncher) {
    & (Join-Path $ProjectRoot "scripts\install_launcher.ps1") -ProjectRoot $ProjectRoot
    & (Join-Path $ProjectRoot "scripts\verify_launcher_installation.ps1") `
        -ProjectRoot $ProjectRoot
}
& (Join-Path $ProjectRoot "scripts\doctor.ps1") -ProjectRoot $ProjectRoot
if ($RunValidation) {
    & (Join-Path $ProjectRoot "scripts\validate_all.ps1") `
        -ProjectRoot $ProjectRoot `
        -Mock:$Mock `
        -ReadOnlyProbe
    if ($LASTEXITCODE -ne 0) {
        throw "A validação consolidada falhou com código $LASTEXITCODE."
    }
}
if ($StartResolve) {
    $resolve = Join-Path $env:PROGRAMFILES "Blackmagic Design\DaVinci Resolve\Resolve.exe"
    if (-not (Test-Path -LiteralPath $resolve)) {
        throw "Resolve não encontrado: $resolve"
    }
    Start-Process -FilePath $resolve
}
if ($StartEditor) {
    $arguments = @("-m", "o_editor")
    if ($Mock) {
        $arguments += "--mock"
    }
    Start-Process -FilePath $venvPython -ArgumentList $arguments -WorkingDirectory $ProjectRoot
}

Write-Host "Orquestração concluída. Nenhuma etapa não solicitada foi executada."
