[CmdletBinding()]
param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = New-Object Text.UTF8Encoding($false)
$OutputEncoding = [Console]::OutputEncoding

$ProjectRoot = [System.IO.Path]::GetFullPath($ProjectRoot)
$runtimeRoot = [System.IO.Path]::Combine($ProjectRoot, "runtime")
$reportRoot = [System.IO.Path]::Combine($runtimeRoot, "reports")
[System.IO.Directory]::CreateDirectory($reportRoot) | Out-Null
$stagingRoot = [System.IO.Path]::Combine(
    $runtimeRoot,
    ("internal-action-debug-staging-{0}-{1}" -f $PID, [guid]::NewGuid().ToString("N"))
)
if (-not $stagingRoot.StartsWith($runtimeRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Diretório temporário fora de runtime: $stagingRoot"
}
[System.IO.Directory]::CreateDirectory($stagingRoot) | Out-Null

function Copy-DebugFile {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$RelativeDestination
    )

    if (-not [System.IO.File]::Exists($Source)) {
        return
    }
    $destination = [System.IO.Path]::Combine($stagingRoot, $RelativeDestination)
    $parent = [System.IO.Path]::GetDirectoryName($destination)
    [System.IO.Directory]::CreateDirectory($parent) | Out-Null
    [System.IO.File]::Copy($Source, $destination, $true)
}

function Copy-DebugDirectoryFiles {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$RelativeDestination,
        [string[]]$Patterns = @("*")
    )

    if (-not [System.IO.Directory]::Exists($Source)) {
        return
    }
    foreach ($pattern in $Patterns) {
        Get-ChildItem -LiteralPath $Source -Filter $pattern -File -ErrorAction SilentlyContinue |
            ForEach-Object {
                Copy-DebugFile `
                    -Source $_.FullName `
                    -RelativeDestination ([System.IO.Path]::Combine(
                        $RelativeDestination,
                        $_.Name
                    ))
            }
    }
}

try {
    $launcherSource = [System.IO.Path]::Combine($ProjectRoot, "launcher")
    Copy-DebugDirectoryFiles `
        -Source $launcherSource `
        -RelativeDestination "source\launcher" `
        -Patterns @("*.lua")

    $utility = [System.IO.Path]::Combine(
        $env:APPDATA,
        "Blackmagic Design",
        "DaVinci Resolve",
        "Support",
        "Fusion",
        "Scripts",
        "Utility"
    )
    Copy-DebugDirectoryFiles `
        -Source $utility `
        -RelativeDestination "installed\Utility" `
        -Patterns @("O Editor*.lua", "O Editor.py")

    $appRoot = [System.IO.Path]::Combine($env:APPDATA, "O Editor")
    foreach ($rootLog in @(
        "launcher-external.log",
        "launcher-internal.log",
        "menu-test.log"
    )) {
        Copy-DebugFile `
            -Source ([System.IO.Path]::Combine($appRoot, $rootLog)) `
            -RelativeDestination ([System.IO.Path]::Combine("logs\appdata-root", $rootLog))
    }
    Copy-DebugFile `
        -Source ([System.IO.Path]::Combine($appRoot, "internal-capabilities.json")) `
        -RelativeDestination "evidence\internal-capabilities.json"
    Copy-DebugFile `
        -Source ([System.IO.Path]::Combine($appRoot, "internal_common.lua")) `
        -RelativeDestination "installed\O Editor\internal_common.lua"
    Copy-DebugFile `
        -Source ([System.IO.Path]::Combine($appRoot, "launch-editor.cmd")) `
        -RelativeDestination "installed\O Editor\launch-editor.cmd"
    Copy-DebugFile `
        -Source ([System.IO.Path]::Combine($appRoot, "menu-test-success.txt")) `
        -RelativeDestination "evidence\menu-test-success.txt"
    Copy-DebugDirectoryFiles `
        -Source ([System.IO.Path]::Combine($appRoot, "logs")) `
        -RelativeDestination "logs\appdata"
    Copy-DebugDirectoryFiles `
        -Source ([System.IO.Path]::Combine($appRoot, "requests")) `
        -RelativeDestination "requests"
    Copy-DebugDirectoryFiles `
        -Source ([System.IO.Path]::Combine($appRoot, "reports")) `
        -RelativeDestination "reports\appdata" `
        -Patterns @("*.json", "*.md", "*.log", "*.txt")
    Copy-DebugDirectoryFiles `
        -Source ([System.IO.Path]::Combine($runtimeRoot, "logs")) `
        -RelativeDestination "logs\runtime"
    Copy-DebugDirectoryFiles `
        -Source $reportRoot `
        -RelativeDestination "reports\runtime" `
        -Patterns @("*.json", "*.md")

    $launcherConfiguration = [System.IO.Path]::Combine($appRoot, "launcher.json")
    if ([System.IO.File]::Exists($launcherConfiguration)) {
        $sanitized = Get-Content -Raw -Encoding UTF8 -LiteralPath $launcherConfiguration |
            ConvertFrom-Json
        $sanitized.project_root = "<PROJECT_ROOT>"
        $sanitized.python_executable = "<PROJECT_ROOT>\.venv\Scripts\python.exe"
        $sanitizedPath = [System.IO.Path]::Combine(
            $stagingRoot,
            "installed",
            "O Editor",
            "launcher.sanitized.json"
        )
        [System.IO.Directory]::CreateDirectory(
            [System.IO.Path]::GetDirectoryName($sanitizedPath)
        ) | Out-Null
        [System.IO.File]::WriteAllText(
            $sanitizedPath,
            ($sanitized | ConvertTo-Json -Depth 10),
            (New-Object Text.UTF8Encoding($false))
        )
    }

    $hashEntries = [System.Collections.Generic.List[object]]::new()
    Get-ChildItem -LiteralPath $stagingRoot -Recurse -File | ForEach-Object {
        $hashEntries.Add([ordered]@{
            path = $_.FullName.Substring($stagingRoot.Length + 1)
            sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
            size = $_.Length
        })
    }
    $gitCommit = (git -C $ProjectRoot rev-parse HEAD 2>$null | Out-String).Trim()
    $gitBranch = (git -C $ProjectRoot branch --show-current 2>$null | Out-String).Trim()
    $gitStatus = (git -C $ProjectRoot status --short 2>$null | Out-String).Trim()
    $manifest = [ordered]@{
        schema_version = 1
        generated_at = (Get-Date).ToString("o")
        project_root = "<PROJECT_ROOT>"
        git = [ordered]@{
            commit = $gitCommit
            branch = $gitBranch
            status = if ($gitStatus) { $gitStatus } else { "clean" }
        }
        resolve_running = $null -ne (
            Get-Process -Name "Resolve" -ErrorAction SilentlyContinue
        )
        mutations_executed = $false
        excluded = @(
            "media",
            "full transcripts",
            "Whisper models",
            "user config",
            "secrets"
        )
        files = $hashEntries
    }
    [System.IO.File]::WriteAllText(
        ([System.IO.Path]::Combine($stagingRoot, "manifest.json")),
        ($manifest | ConvertTo-Json -Depth 12),
        (New-Object Text.UTF8Encoding($false))
    )

    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $zipPath = [System.IO.Path]::Combine(
        $reportRoot,
        "internal-action-debug-$timestamp.zip"
    )
    Compress-Archive `
        -Path ([System.IO.Path]::Combine($stagingRoot, "*")) `
        -DestinationPath $zipPath `
        -CompressionLevel Optimal
    if (-not [System.IO.File]::Exists($zipPath)) {
        throw "O bundle não foi criado: $zipPath"
    }
    Write-Host "Bundle de diagnóstico: $zipPath"
    Write-Host "SHA-256: $((Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash)"
}
finally {
    if (
        [System.IO.Directory]::Exists($stagingRoot) -and
        $stagingRoot.StartsWith($runtimeRoot, [System.StringComparison]::OrdinalIgnoreCase)
    ) {
        Remove-Item -LiteralPath $stagingRoot -Recurse -Force
    }
}
