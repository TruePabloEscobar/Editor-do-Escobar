[CmdletBinding()]
param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$JsonOutput,
    [string]$MarkdownOutput
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = New-Object Text.UTF8Encoding($false)
$OutputEncoding = [Console]::OutputEncoding
$env:PYTHONUTF8 = "1"
$python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Python da virtual environment não encontrado: $python"
}

$arguments = @("-m", "o_editor.infrastructure.resolve.connection_test", "--root", $ProjectRoot)
if ($JsonOutput) {
    $arguments += @("--json-output", $JsonOutput)
}
if ($MarkdownOutput) {
    $arguments += @("--markdown-output", $MarkdownOutput)
}

& $python @arguments
exit $LASTEXITCODE
