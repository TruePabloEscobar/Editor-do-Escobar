[CmdletBinding()]
param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = New-Object Text.UTF8Encoding($false)
$OutputEncoding = [Console]::OutputEncoding
$env:PYTHONUTF8 = "1"

function Show-Check {
    param([string]$Name, [bool]$Ok, [string]$Detail)
    $state = if ($Ok) { "OK" } else { "ATENÇÃO" }
    Write-Host ("[{0}] {1}: {2}" -f $state, $Name, $Detail)
}

Write-Host "O Editor - diagnóstico"
Write-Host "Projeto: $ProjectRoot"
Write-Host ""

$venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$venvExists = Test-Path -LiteralPath $venvPython
Show-Check "Ambiente virtual" $venvExists $(if ($venvExists) { (& $venvPython --version 2>&1) } else { $venvPython })
if ($venvExists) {
    $runtime = & $venvPython -c 'import struct,sys; print(str(sys.version_info.major)+chr(46)+str(sys.version_info.minor)+chr(124)+str(struct.calcsize(chr(80))*8))'
    Show-Check "Runtime obrigatório" ($runtime.Trim() -eq "3.11|64") $runtime
}

$resolveExe = Join-Path $env:PROGRAMFILES "Blackmagic Design\DaVinci Resolve\Resolve.exe"
$resolveApi = Join-Path $env:PROGRAMDATA "Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting"
$resolveModule = Join-Path $resolveApi "Modules\DaVinciResolveScript.py"
$resolveLib = Join-Path $env:PROGRAMFILES "Blackmagic Design\DaVinci Resolve\fusionscript.dll"
$resolveDocs = Join-Path $resolveApi "README.txt"
Show-Check "DaVinci Resolve" (Test-Path -LiteralPath $resolveExe) $resolveExe
Show-Check "Resolve API" (Test-Path -LiteralPath $resolveModule) $resolveModule
Show-Check "Resolve library" (Test-Path -LiteralPath $resolveLib) $resolveLib
Show-Check "Resolve docs" (Test-Path -LiteralPath $resolveDocs) $resolveDocs
Show-Check "RESOLVE_SCRIPT_API" ($null -ne $env:RESOLVE_SCRIPT_API) $(if ($env:RESOLVE_SCRIPT_API) { $env:RESOLVE_SCRIPT_API } else { "não configurado; descoberta automática será usada" })
Show-Check "RESOLVE_SCRIPT_LIB" ($null -ne $env:RESOLVE_SCRIPT_LIB) $(if ($env:RESOLVE_SCRIPT_LIB) { $env:RESOLVE_SCRIPT_LIB } else { "não configurado; descoberta automática será usada" })

$configPath = if ($env:O_EDITOR_CONFIG) { $env:O_EDITOR_CONFIG } else { Join-Path $env:APPDATA "O Editor\config.json" }
$configuredFfmpeg = $null
$configuredFfprobe = $null
if (Test-Path -LiteralPath $configPath) {
    try {
        $runtimeConfig = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $configuredFfmpeg = $runtimeConfig.ffmpeg.ffmpeg_path
        $configuredFfprobe = $runtimeConfig.ffmpeg.ffprobe_path
    }
    catch {
        $configuredFfmpeg = $null
        $configuredFfprobe = $null
    }
}
$ffmpegCandidate = if ($env:FFMPEG_PATH) { $env:FFMPEG_PATH } else { $configuredFfmpeg }
$ffprobeCandidate = if ($env:FFPROBE_PATH) { $env:FFPROBE_PATH } else { $configuredFfprobe }
$ffmpeg = if ($ffmpegCandidate -and [IO.File]::Exists($ffmpegCandidate)) {
    Get-Item -LiteralPath $ffmpegCandidate
}
else {
    Get-Command ffmpeg -ErrorAction SilentlyContinue
}
$ffprobe = if ($ffprobeCandidate -and [IO.File]::Exists($ffprobeCandidate)) {
    Get-Item -LiteralPath $ffprobeCandidate
}
else {
    Get-Command ffprobe -ErrorAction SilentlyContinue
}
Show-Check "FFmpeg" ($null -ne $ffmpeg) $(if ($ffmpeg) { (& $ffmpeg.FullName -version 2>&1 | Select-Object -First 1) } else { "não encontrado; FFMPEG_PATH/config.json não apontam para um arquivo" })
Show-Check "FFprobe" ($null -ne $ffprobe) $(if ($ffprobe) { (& $ffprobe.FullName -version 2>&1 | Select-Object -First 1) } else { "não encontrado" })

$nvidia = Get-Command nvidia-smi -ErrorAction SilentlyContinue
Show-Check "NVIDIA/CUDA" ($null -ne $nvidia) $(if ($nvidia) { (& $nvidia.Source --query-gpu=name,driver_version --format=csv,noheader 2>&1 | Select-Object -First 1) } else { "nvidia-smi não encontrado; CPU será o fallback" })

$modelPath = $null
if (Test-Path -LiteralPath $configPath) {
    try {
        $config = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $modelPath = $config.transcription.model_path
    }
    catch {
        Write-Host "[ATENÇÃO] Configuração: JSON inválido em $configPath"
    }
}
Show-Check "Configuração de usuário" (Test-Path -LiteralPath $configPath) $configPath
Show-Check "Modelo Whisper local" ($modelPath -and (Test-Path -LiteralPath $modelPath)) $(if ($modelPath) { $modelPath } else { "model_path não configurado; nenhum download automático será feito" })
if ($venvExists) {
    $whisperRuntime = & $venvPython -c 'import ctranslate2,faster_whisper; print(faster_whisper.__version__+chr(124)+str(ctranslate2.get_cuda_device_count()))' 2>&1
    Show-Check "Runtime Whisper" ($LASTEXITCODE -eq 0) ($whisperRuntime | Out-String).Trim()
}

$launcherConfig = Join-Path $env:APPDATA "O Editor\launcher.json"
$launcherOk = $false
$launcherDetail = $launcherConfig
if (Test-Path -LiteralPath $launcherConfig) {
    try {
        $launcher = Get-Content -Raw -LiteralPath $launcherConfig -Encoding UTF8 | ConvertFrom-Json
        $launcherOk = (
            $launcher.internal_host_enabled -eq $true -and
            $launcher.external_bridge_enabled -eq $false
        )
        $launcherDetail = "internal_host_enabled=$($launcher.internal_host_enabled); external_bridge_enabled=$($launcher.external_bridge_enabled)"
    }
    catch {
        $launcherDetail = "JSON inválido: $($_.Exception.Message)"
    }
}
Show-Check "Configuração do launcher interno" $launcherOk $launcherDetail

$utility = Join-Path $env:APPDATA "Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility"
$diagnosticName = "O Editor - Diagn" + [char]0x00F3 + "stico.lua"
$luaNames = @(
    "O Editor - Teste de Menu.lua",
    $diagnosticName,
    "O Editor - Abrir.lua",
    "O Editor - Capability Probe.lua",
    "O Editor - Aplicar Plano.lua",
    "O Editor - Aplicar Rough Cut.lua"
)
$missingLua = @($luaNames | Where-Object { -not (Test-Path -LiteralPath (Join-Path $utility $_)) })
Show-Check "Scripts Lua internos" ($missingLua.Count -eq 0) $(if ($missingLua.Count -eq 0) { $utility } else { "ausentes: $($missingLua -join ', ')" })

$runtime = Join-Path $ProjectRoot "runtime"
$permissionOk = $false
$permissionDetail = $runtime
try {
    New-Item -ItemType Directory -Force -Path $runtime | Out-Null
    $testFile = Join-Path $runtime "OE_DOCTOR_PERMISSION_TEST.tmp"
    Set-Content -LiteralPath $testFile -Value "test" -Encoding UTF8
    Remove-Item -LiteralPath $testFile -Force
    $permissionOk = $true
}
catch {
    $permissionDetail = $_.Exception.Message
}
Show-Check "Permissão de runtime" $permissionOk $permissionDetail

$logPath = Join-Path $runtime "logs\o-editor.log"
Show-Check "Logs" (Test-Path -LiteralPath $logPath) $(if (Test-Path -LiteralPath $logPath) { $logPath } else { "ainda não gerados" })

Write-Host ""
if ($venvExists) {
    Write-Host "Probe somente leitura:"
    Write-Host "& '$venvPython' -m o_editor.infrastructure.resolve.capabilities --root '$ProjectRoot' --read-only"
}
