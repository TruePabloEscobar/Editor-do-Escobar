[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$timestamp = [DateTimeOffset]::Now.ToString("yyyyMMdd-HHmmss")
$reportDirectory = [IO.Path]::Combine($projectRoot, "runtime", "reports")
$staging = [IO.Path]::Combine(
    [IO.Path]::GetTempPath(),
    "o-editor-voice-debug-" + [Guid]::NewGuid().ToString("N")
)
$archive = [IO.Path]::Combine(
    $reportDirectory,
    "voice-export-debug-$timestamp.zip"
)
$appRoot = [IO.Path]::Combine($env:APPDATA, "O Editor")
$temporaryBase = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$resolvedStaging = [IO.Path]::GetFullPath($staging)
if (-not $resolvedStaging.StartsWith(
    $temporaryBase,
    [StringComparison]::OrdinalIgnoreCase
)) {
    throw "Diretório de staging fora da raiz temporária permitida."
}

[IO.Directory]::CreateDirectory($reportDirectory) | Out-Null
[IO.Directory]::CreateDirectory($staging) | Out-Null
try {
    $safeFiles = @(
        [IO.Path]::Combine($appRoot, "launcher.json"),
        [IO.Path]::Combine($appRoot, "internal-capabilities.json"),
        [IO.Path]::Combine($appRoot, "resolve-internal-host", "host-status.json"),
        [IO.Path]::Combine(
            $appRoot,
            "resolve-internal-host",
            "logs",
            "workflow-integration.log"
        ),
        [IO.Path]::Combine($reportDirectory, "resolve_internal_host_spike.json"),
        [IO.Path]::Combine($reportDirectory, "ffmpeg_validation_report.json"),
        [IO.Path]::Combine($reportDirectory, "whisper_validation_report.json")
    )
    foreach ($file in $safeFiles) {
        if ([IO.File]::Exists($file)) {
            [IO.File]::Copy(
                $file,
                [IO.Path]::Combine($staging, [IO.Path]::GetFileName($file)),
                $true
            )
        }
    }
    $manifest = @(
        "O Editor voice export debug bundle",
        "Generated: $([DateTimeOffset]::UtcNow.ToString('o'))",
        "Audio included: false",
        "Transcript included: false",
        "Secrets included: false"
    )
    [IO.File]::WriteAllLines(
        [IO.Path]::Combine($staging, "MANIFEST.txt"),
        $manifest,
        [Text.UTF8Encoding]::new($false)
    )
    Compress-Archive -Path ([IO.Path]::Combine($resolvedStaging, "*")) `
        -DestinationPath $archive -Force
    Write-Host "Bundle seguro: $archive"
} finally {
    if ([IO.Directory]::Exists($resolvedStaging)) {
        Remove-Item -LiteralPath $resolvedStaging -Recurse -Force
    }
}

