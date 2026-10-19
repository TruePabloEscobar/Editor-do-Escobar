[CmdletBinding()]
param(
    [switch]$Mock,
    [switch]$Headless,
    [string]$LaunchContext,
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = New-Object Text.UTF8Encoding($false)
$OutputEncoding = [Console]::OutputEncoding
$env:PYTHONUTF8 = "1"
$python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Ambiente virtual não encontrado. Crie .venv e instale: pip install -e `".[dev]`""
}

$arguments = @("-m", "o_editor")
if ($Mock) {
    $arguments += "--mock"
}
if ($Headless) {
    $arguments += "--headless"
}
if ($LaunchContext) {
    $arguments += @("--launch-context", $LaunchContext)
}

& $python @arguments
exit $LASTEXITCODE
