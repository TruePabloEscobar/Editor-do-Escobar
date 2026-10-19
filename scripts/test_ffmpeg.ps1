[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$configPath = [IO.Path]::Combine($env:APPDATA, "O Editor", "config.json")
$reportDirectory = [IO.Path]::Combine($projectRoot, "runtime", "reports")
$jsonPath = [IO.Path]::Combine($reportDirectory, "ffmpeg_validation_report.json")
$markdownPath = [IO.Path]::Combine($reportDirectory, "FFMPEG_VALIDATION_REPORT.md")
$temporaryRoot = [IO.Path]::Combine(
    [IO.Path]::GetTempPath(),
    "o-editor-ffmpeg-" + [Guid]::NewGuid().ToString("N")
)
$temporaryBase = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$resolvedTemporaryRoot = [IO.Path]::GetFullPath($temporaryRoot)
if (-not $resolvedTemporaryRoot.StartsWith(
    $temporaryBase,
    [StringComparison]::OrdinalIgnoreCase
)) {
    throw "Diretório temporário fora da raiz permitida."
}

if (-not [IO.File]::Exists($configPath)) {
    throw "Configuração local não encontrada: $configPath"
}
$config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
$ffmpeg = [string]$config.ffmpeg.ffmpeg_path
$ffprobe = [string]$config.ffmpeg.ffprobe_path
if (-not [IO.File]::Exists($ffmpeg) -or -not [IO.File]::Exists($ffprobe)) {
    throw "FFmpeg/FFprobe explícitos não foram encontrados na configuração."
}

[IO.Directory]::CreateDirectory($reportDirectory) | Out-Null
[IO.Directory]::CreateDirectory($temporaryRoot) | Out-Null
$wav = [IO.Path]::Combine($temporaryRoot, "fixture.wav")
try {
    & $ffmpeg -hide_banner -loglevel error -f lavfi -i "sine=frequency=440:duration=1" `
        -ac 1 -ar 16000 -c:a pcm_s16le -y $wav
    if ($LASTEXITCODE -ne 0 -or -not [IO.File]::Exists($wav)) {
        throw "FFmpeg não criou o WAV de teste."
    }
    $probeText = & $ffprobe -v error -select_streams a:0 `
        -show_entries "stream=codec_name,sample_rate,channels:format=duration" `
        -of json $wav
    if ($LASTEXITCODE -ne 0) {
        throw "FFprobe não validou o WAV de teste."
    }
    $probe = ($probeText | Out-String) | ConvertFrom-Json
    $stream = $probe.streams[0]
    $duration = [double]::Parse(
        [string]$probe.format.duration,
        [Globalization.CultureInfo]::InvariantCulture
    )
    $passed = (
        $stream.codec_name -eq "pcm_s16le" -and
        [int]$stream.sample_rate -eq 16000 -and
        [int]$stream.channels -eq 1 -and
        [Math]::Abs($duration - 1.0) -lt 0.05
    )
    if (-not $passed) {
        throw "Metadados inesperados no WAV produzido."
    }
    $ffmpegVersion = (& $ffmpeg -version | Select-Object -First 1)
    $ffprobeVersion = (& $ffprobe -version | Select-Object -First 1)
    $report = [ordered]@{
        schema_version = 1
        generated_at = [DateTimeOffset]::UtcNow.ToString("o")
        status = "PASSED"
        ffmpeg_path = $ffmpeg
        ffprobe_path = $ffprobe
        ffmpeg_version = $ffmpegVersion
        ffprobe_version = $ffprobeVersion
        fixture = [ordered]@{
            temporary = $true
            codec = [string]$stream.codec_name
            sample_rate = [int]$stream.sample_rate
            channels = [int]$stream.channels
            duration_seconds = $duration
        }
    }
    [IO.File]::WriteAllText(
        $jsonPath,
        ($report | ConvertTo-Json -Depth 8) + "`n",
        [Text.UTF8Encoding]::new($false)
    )
    $lines = @(
        "# Validação do FFmpeg",
        "",
        "- Status: ``PASSED``",
        "- FFmpeg: ``$ffmpegVersion``",
        "- FFprobe: ``$ffprobeVersion``",
        "- Caminho FFmpeg: ``$ffmpeg``",
        "- Caminho FFprobe: ``$ffprobe``",
        "- Fixture: WAV temporário PCM 16-bit, mono, 16 kHz, 1 segundo",
        "- Mídia versionada: ``não``",
        ""
    )
    [IO.File]::WriteAllLines($markdownPath, $lines, [Text.UTF8Encoding]::new($false))
    Write-Host "FFmpeg: PASSED"
    Write-Host "Relatório: $markdownPath"
} finally {
    if ([IO.Directory]::Exists($resolvedTemporaryRoot)) {
        Remove-Item -LiteralPath $resolvedTemporaryRoot -Recurse -Force
    }
}

