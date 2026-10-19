"""Rebuild the isolated audio of one timeline track from its original media.

Resolve cannot render a single track through its documented render settings, and the
user's mute/solo state must never be touched. Instead every clip of the track is decoded
from its source file with FFmpeg and written at its exact timeline position (sample
accurate), with digital silence in the gaps. Sample 0 corresponds to the timeline start.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import wave
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from o_editor.domain.enums import ChannelMode, TrackType
from o_editor.domain.source_timing import SourceTimingError, resolve_source_timing
from o_editor.domain.timeline_layout import ClipInfo, TimelineLayout
from o_editor.errors import CancelledError, OEditorError
from o_editor.infrastructure.ffmpeg.runner import FFmpegError, FFmpegRunner
from o_editor.infrastructure.transcription.base import CancellationToken

RENDER_VERSION = "track-render-2-multistream"
_NO_WINDOW = int(getattr(subprocess, "CREATE_NO_WINDOW", 0)) if os.name == "nt" else 0
CHUNK_BYTES = 1 << 16
ProgressCallback = Callable[[float, str], None]


class TrackRenderError(OEditorError):
    """A track could not be reconstructed safely."""


@dataclass(frozen=True, slots=True)
class AudioStreamInfo:
    index: int
    channels: int


@dataclass(frozen=True, slots=True)
class MediaInfo:
    duration_seconds: float | None
    channels: int
    sample_rate: int | None
    streams: tuple[AudioStreamInfo, ...]


@dataclass(frozen=True, slots=True)
class RenderedTrack:
    track_index: int
    path: Path
    sample_rate: int
    fps: float
    timeline_start_frame: int
    sample_count: int
    rendered_clips: int
    warnings: tuple[str, ...]
    cache_key: str
    from_cache: bool = False


def _selected_channels(
    file_channels: int,
    mapping_channels: tuple[int, ...] | None,
    channel_mode: ChannelMode,
) -> tuple[tuple[int, ...], tuple[str, ...]]:
    """Resolve one-based embedded channel numbers before selecting streams."""

    warnings: list[str] = []
    channels: tuple[int, ...]
    if mapping_channels is not None and mapping_channels:
        invalid = [item for item in mapping_channels if item > file_channels]
        if invalid:
            warnings.append(
                "O mapeamento de canais do Resolve referencia canais inexistentes no arquivo; "
                "usando a seleção de canal da faixa."
            )
            channels = tuple(range(1, file_channels + 1))
        else:
            channels = mapping_channels
    else:
        channels = tuple(range(1, file_channels + 1))
        if file_channels > 2:
            warnings.append(
                f"Arquivo com {file_channels} canais sem mapeamento informado; "
                "usando a média de todos os canais."
            )
    if channel_mode == ChannelMode.LEFT and len(channels) >= 2:
        channels = (channels[0],)
    elif channel_mode == ChannelMode.RIGHT and len(channels) >= 2:
        channels = (channels[1],)
    return channels, tuple(warnings)


def channel_filter(
    file_channels: int,
    mapping_channels: tuple[int, ...] | None,
    channel_mode: ChannelMode,
) -> tuple[str | None, tuple[str, ...]]:
    """Return the mono pan expression for a single audio stream."""
    channels, warnings = _selected_channels(file_channels, mapping_channels, channel_mode)
    if len(channels) == 1:
        if file_channels == 1:
            return None, tuple(warnings)
        return f"pan=mono|c0=c{channels[0] - 1}", tuple(warnings)
    weight = 1.0 / len(channels)
    terms = "+".join(f"{weight:.6f}*c{item - 1}" for item in channels)
    return f"pan=mono|c0={terms}", tuple(warnings)


def _decode_options(
    info: MediaInfo,
    mapping_channels: tuple[int, ...] | None,
    channel_mode: ChannelMode,
    sample_rate: int,
) -> tuple[list[str], tuple[str, ...]]:
    """Mix exactly the mapped channels, including channels in later audio streams."""
    channels, warnings = _selected_channels(info.channels, mapping_channels, channel_mode)
    graph: list[str] = []
    labels: list[str] = []
    offset = 0
    weight = 1.0 / len(channels)
    for stream in info.streams:
        local_channels = tuple(
            channel - offset - 1
            for channel in channels
            if offset < channel <= offset + stream.channels
        )
        offset += stream.channels
        if not local_channels:
            continue
        name = f"oe{len(labels)}"
        terms = "+".join(f"{weight:.9f}*c{channel}" for channel in local_channels)
        graph.append(f"[0:{stream.index}]pan=mono|c0={terms},aresample={sample_rate}[{name}]")
        labels.append(f"[{name}]")
    if len(labels) == 1:
        graph.append(f"{labels[0]}anull[oeout]")
    else:
        graph.append(
            "".join(labels) + f"amix=inputs={len(labels)}:duration=longest:"
            "dropout_transition=0:normalize=0[oeout]"
        )
    return ["-filter_complex", ";".join(graph), "-map", "[oeout]"], warnings


class TrackAudioRenderer:
    def __init__(
        self,
        ffmpeg: FFmpegRunner,
        cache_root: Path,
        *,
        sample_rate: int = 16_000,
    ) -> None:
        self._ffmpeg = ffmpeg
        self._cache_root = cache_root
        self._sample_rate = sample_rate
        self._media_info: dict[str, MediaInfo] = {}

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    def cache_key(self, layout: TimelineLayout, track_index: int, channel_mode: ChannelMode) -> str:
        clips = [
            [
                clip.item_id,
                clip.start_frame,
                clip.end_frame,
                clip.source_start_frame,
                clip.source_end_frame,
                clip.left_offset_frames,
                clip.right_offset_frames,
                clip.source_start_seconds,
                clip.source_end_seconds,
                clip.media_fps,
                clip.file_path,
                clip.enabled,
                clip.audio_channel_mapping,
                clip.speed_percent,
                _file_signature(clip.file_path),
            ]
            for clip in layout.clips_in_track(TrackType.AUDIO, track_index)
        ]
        payload = {
            "version": RENDER_VERSION,
            "fps": layout.fps,
            "start": layout.start_frame,
            "end": layout.end_frame,
            "track": track_index,
            "mode": channel_mode.value,
            "rate": self._sample_rate,
            "clips": clips,
        }
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def render(
        self,
        layout: TimelineLayout,
        track_index: int,
        channel_mode: ChannelMode,
        *,
        progress: ProgressCallback | None = None,
        cancellation: CancellationToken | None = None,
        use_cache: bool = True,
    ) -> RenderedTrack:
        if layout.track(TrackType.AUDIO, track_index) is None:
            raise TrackRenderError(f"A faixa A{track_index} não existe na timeline capturada.")
        key = self.cache_key(layout, track_index, channel_mode)
        directory = self._cache_root / "tracks" / key
        target = directory / "track.wav"
        metadata_path = directory / "metadata.json"
        total_samples = self._sample_index(layout, layout.end_frame)
        if use_cache:
            cached = _load_metadata(metadata_path)
            if (
                cached is not None
                and cached.get("cache_key") == key
                and target.is_file()
                and _wav_frames(target) == total_samples
            ):
                return RenderedTrack(
                    track_index=track_index,
                    path=target,
                    sample_rate=self._sample_rate,
                    fps=layout.fps,
                    timeline_start_frame=layout.start_frame,
                    sample_count=total_samples,
                    rendered_clips=int(cached.get("rendered_clips", 0)),
                    warnings=tuple(str(item) for item in cached.get("warnings", ())),
                    cache_key=key,
                    from_cache=True,
                )
        ffmpeg = self._ffmpeg.find()
        if ffmpeg is None:
            raise TrackRenderError(
                "FFmpeg não foi encontrado. Configure ffmpeg.ffmpeg_path em config.json."
            )
        directory.mkdir(parents=True, exist_ok=True)
        temporary = directory / "track.wav.partial"
        warnings: list[str] = []
        rendered = 0
        clips = layout.clips_in_track(TrackType.AUDIO, track_index)
        try:
            with wave.open(str(temporary), "wb") as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(self._sample_rate)
                cursor = 0
                for number, clip in enumerate(clips, start=1):
                    _raise_if_cancelled(cancellation)
                    if progress:
                        progress(
                            (number - 1) / max(1, len(clips)),
                            f"Reconstruindo A{track_index}: clipe {number}/{len(clips)}",
                        )
                    first = self._sample_index(layout, clip.start_frame)
                    last = self._sample_index(layout, clip.end_frame)
                    if first < cursor:
                        warnings.append(
                            f"O clipe {clip.name or clip.item_id} começa antes do fim do anterior; "
                            "o trecho sobreposto foi ignorado."
                        )
                        first = cursor
                    if last <= first:
                        continue
                    _write_silence(output, first - cursor)
                    cursor = first
                    written, clip_warnings = self._render_clip(
                        ffmpeg,
                        output,
                        layout,
                        clip,
                        channel_mode,
                        last - first,
                        cancellation,
                    )
                    warnings.extend(clip_warnings)
                    if written:
                        rendered += 1
                    cursor = last
                _write_silence(output, total_samples - cursor)
        except CancelledError:
            temporary.unlink(missing_ok=True)
            raise
        except (OSError, wave.Error) as exc:
            temporary.unlink(missing_ok=True)
            raise TrackRenderError(
                f"Falha ao gravar o áudio reconstruído de A{track_index}."
            ) from exc
        os.replace(temporary, target)
        _save_metadata(
            metadata_path,
            {
                "cache_key": key,
                "track_index": track_index,
                "channel_mode": channel_mode.value,
                "sample_rate": self._sample_rate,
                "samples": total_samples,
                "rendered_clips": rendered,
                "warnings": warnings,
                "render_version": RENDER_VERSION,
            },
        )
        if progress:
            progress(1.0, f"A{track_index} reconstruída")
        return RenderedTrack(
            track_index=track_index,
            path=target,
            sample_rate=self._sample_rate,
            fps=layout.fps,
            timeline_start_frame=layout.start_frame,
            sample_count=total_samples,
            rendered_clips=rendered,
            warnings=tuple(warnings),
            cache_key=key,
        )

    def _sample_index(self, layout: TimelineLayout, frame: int) -> int:
        return round((frame - layout.start_frame) * self._sample_rate / layout.fps)

    def _render_clip(
        self,
        ffmpeg: Path,
        output: wave.Wave_write,
        layout: TimelineLayout,
        clip: ClipInfo,
        channel_mode: ChannelMode,
        expected_samples: int,
        cancellation: CancellationToken | None,
    ) -> tuple[bool, list[str]]:
        label = clip.name or clip.item_id
        warnings: list[str] = []
        if not clip.enabled:
            _write_silence(output, expected_samples)
            return False, [f"O clipe {label} está desabilitado na timeline; tratado como silêncio."]
        if clip.item_type != "audio" or not clip.file_path:
            _write_silence(output, expected_samples)
            return False, [f"O item {label} não possui arquivo de áudio de origem; ignorado."]
        source = Path(clip.file_path)
        if not source.is_file():
            raise TrackRenderError(
                f"Arquivo de origem não encontrado para {label} ({clip.track_key}): {source}"
            )
        info = self._probe(source)
        try:
            timing = resolve_source_timing(
                clip, timeline_fps=layout.fps, media_duration_seconds=info.duration_seconds
            )
        except SourceTimingError as exc:
            raise TrackRenderError(str(exc)) from exc
        warnings.extend(timing.warnings)
        decode_options, channel_warnings = _decode_options(
            info, clip.source_channel_indices(), channel_mode, self._sample_rate
        )
        warnings.extend(f"{label}: {item}" for item in channel_warnings)
        if clip.source_channel_indices() == ():
            _write_silence(output, expected_samples)
            warnings.append(f"O clipe {label} está com o canal mudo no mapeamento; silêncio.")
            return False, warnings
        command = [
            str(ffmpeg),
            "-nostdin",
            "-v",
            "error",
            "-ss",
            f"{timing.offset_seconds:.6f}",
            "-t",
            f"{timing.duration_seconds + 0.05:.6f}",
            "-i",
            str(source),
            "-vn",
            *decode_options,
            "-ac",
            "1",
            "-f",
            "s16le",
            "-acodec",
            "pcm_s16le",
            "pipe:1",
        ]
        expected_bytes = expected_samples * 2
        written = 0
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=_NO_WINDOW,
            )
        except OSError as exc:
            raise TrackRenderError("Não foi possível executar o FFmpeg.") from exc
        assert process.stdout is not None
        reached_eof = False
        try:
            while written < expected_bytes:
                if cancellation and cancellation.cancelled:
                    process.kill()
                    raise CancelledError("A reconstrução do áudio foi cancelada.")
                chunk = process.stdout.read(min(CHUNK_BYTES, expected_bytes - written))
                if not chunk:
                    reached_eof = True
                    break
                if len(chunk) % 2:
                    chunk = chunk[:-1]
                output.writeframes(chunk)
                written += len(chunk)
        finally:
            if not reached_eof and process.poll() is None:
                process.kill()
            try:
                _stdout, stderr = process.communicate(timeout=30)
            except subprocess.TimeoutExpired as exc:
                process.kill()
                process.communicate()
                raise TrackRenderError(
                    f"O FFmpeg não concluiu a decodificação de {label}."
                ) from exc
        if reached_eof and process.returncode != 0:
            message = stderr.decode("utf-8", "replace").strip()[:300] if stderr else ""
            raise TrackRenderError(f"O FFmpeg falhou ao decodificar {label}: {message}")
        shortfall = expected_bytes - written
        if shortfall > 0:
            _write_silence(output, shortfall // 2)
            if shortfall / 2 / self._sample_rate > 0.1:
                warnings.append(
                    f"O arquivo de {label} terminou {shortfall / 2 / self._sample_rate:.2f}s "
                    "antes do esperado; completado com silêncio."
                )
        return True, warnings

    def _probe(self, path: Path) -> MediaInfo:
        key = str(path)
        cached = self._media_info.get(key)
        if cached is not None:
            return cached
        probe = self._ffmpeg.find_probe()
        if probe is None:
            raise TrackRenderError("FFprobe não foi encontrado; configure ffmpeg.ffprobe_path.")
        try:
            result = subprocess.run(
                [
                    str(probe),
                    "-v",
                    "error",
                    "-select_streams",
                    "a",
                    "-show_entries",
                    "stream=index,channels,sample_rate,duration:format=duration",
                    "-of",
                    "json",
                    str(path),
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=60,
                creationflags=_NO_WINDOW,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise FFmpegError(f"O FFprobe não respondeu para {path}.") from exc
        try:
            value = json.loads(result.stdout or "{}")
        except json.JSONDecodeError as exc:
            raise TrackRenderError(f"Resposta inválida do FFprobe para {path}.") from exc
        streams = value.get("streams") or []
        if not streams:
            raise TrackRenderError(f"O arquivo não contém áudio: {path}")
        stream = streams[0]
        duration = _float_or_none((value.get("format") or {}).get("duration"))
        if duration is None:
            durations = [_float_or_none(item.get("duration")) for item in streams]
            duration = max((item for item in durations if item is not None), default=None)
        audio_streams = tuple(
            AudioStreamInfo(
                index=int(item["index"]), channels=max(1, int(item.get("channels") or 1))
            )
            for item in streams
        )
        info = MediaInfo(
            duration_seconds=duration,
            channels=sum(item.channels for item in audio_streams),
            sample_rate=int(stream["sample_rate"]) if stream.get("sample_rate") else None,
            streams=audio_streams,
        )
        self._media_info[key] = info
        return info


def _write_silence(output: wave.Wave_write, samples: int) -> None:
    remaining = max(0, samples)
    block = bytes(min(remaining, CHUNK_BYTES // 2) * 2)
    while remaining > 0:
        count = min(remaining, len(block) // 2)
        output.writeframes(block[: count * 2])
        remaining -= count


def _wav_frames(path: Path) -> int | None:
    try:
        with wave.open(str(path), "rb") as handle:
            return handle.getnframes()
    except (OSError, wave.Error, EOFError):
        return None


def _file_signature(path: str | None) -> list[Any] | None:
    if not path:
        return None
    try:
        stat = Path(path).stat()
    except OSError:
        return None
    return [stat.st_size, int(stat.st_mtime)]


def _load_metadata(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _save_metadata(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "", "N/A") else None
    except (TypeError, ValueError):
        return None


def _raise_if_cancelled(cancellation: CancellationToken | None) -> None:
    if cancellation and cancellation.cancelled:
        raise CancelledError("A operação foi cancelada.")
