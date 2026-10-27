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
$env:PSModulePath = (Join-Path $env:WINDIR "System32\WindowsPowerShell\v1.0\Modules") + ";" + (Join-Path $env:ProgramFiles "WindowsPowerShell\Modules")
[Console]::OutputEncoding = New-Object Text.UTF8Encoding($false)
$OutputEncoding = [Console]::OutputEncoding
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
$portable = Test-Path -LiteralPath (Join-Path $SourceRoot 'runtime-profile.json')
function Test-CompatiblePython([string]$Candidate) {
    if (-not $Candidate -or -not [IO.File]::Exists($Candidate)) { return $false }
    try {
        $value = & $Candidate -I -c 'import struct,sys; print(str(sys.version_info.major)+chr(46)+str(sys.version_info.minor)+chr(124)+str(struct.calcsize(chr(80))*8))' 2>$null
        return ($LASTEXITCODE -eq 0 -and ([string]$value).Trim() -eq '3.11|64')
    } catch { return $false }
}
if ($portable) {
    if (-not ($files | Where-Object { $_.Name -eq 'runtime-profile.json' })) {
        throw 'Perfil de runtime fora do manifesto; extraia novamente o instalador completo.'
    }
    $profile = Get-Content -Raw -LiteralPath (Join-Path $SourceRoot 'runtime-profile.json') -Encoding UTF8 | ConvertFrom-Json
    if ($profile.kind -ne 'self-contained' -or $profile.format -ne 1) { throw 'Perfil de runtime invalido.' }
    $PythonPath = Join-Path $SourceRoot 'python\python.exe'
    if (-not (Test-CompatiblePython $PythonPath)) { throw 'Python integrado danificado ou Windows incompativel. Extraia novamente o pacote completo.' }
    foreach ($tool in @('ffmpeg.exe', 'ffprobe.exe')) {
        $bundledTool = Join-Path (Join-Path $SourceRoot 'tools/ffmpeg/bin') $tool
        if (-not [IO.File]::Exists($bundledTool)) { throw "Ferramenta integrada ausente: $tool" }
    }
} else {
    $candidates = @()
    if ($PythonPath) { $candidates += $PythonPath }
    else {
        if (Get-Command py -ErrorAction SilentlyContinue) {
            try {
                $fromLauncher = & py -3.11 -c 'import sys; print(sys.executable)' 2>$null
                if ($LASTEXITCODE -eq 0) { $candidates += [string]$fromLauncher }
            } catch { Write-Host 'Python Launcher sem 3.11; procurando outras instalacoes.' }
        }
        $candidates += @(Get-Command python.exe -CommandType Application -All -ErrorAction SilentlyContinue | ForEach-Object { $_.Source })
        $candidates += @((Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311\python.exe'),
            (Join-Path $env:ProgramFiles 'Python311\python.exe'))
    }
    $PythonPath = $candidates | Where-Object { Test-CompatiblePython ([string]$_) } | Select-Object -First 1
    if (-not $PythonPath) {
        throw 'Este e o pacote de fontes. Use EDE-Instalador-Windows-x64.exe, com Python e FFmpeg incluidos, ou informe -PythonPath para Python 3.11 x64.'
    }
    if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue) -or
        -not (Get-Command ffprobe -ErrorAction SilentlyContinue)) {
        throw 'FFmpeg/ffprobe ausentes. Use o instalador autossuficiente ou instale as ferramentas para o pacote de fontes.'
    }
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
if ($portable) {
    $python = Join-Path $destination 'python\python.exe'
    $env:PATH = (Join-Path $destination 'tools/ffmpeg/bin') + ';' + $env:PATH
    & $python (Join-Path $destination 'scripts\check_installation.py')
    if ($LASTEXITCODE -ne 0) { throw 'Falha na verificacao do ambiente integrado. O menu anterior foi preservado.' }
} else {
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
 }
# Verify the actual installed copy, including binaries, before changing the menu.
foreach ($entry in $files) {
    if ((Get-FileHash -LiteralPath (Join-Path $destination $entry.Name) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.Value) {
        throw "Copia instalada divergente: $($entry.Name). Menu anterior preservado."
    }
}
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
