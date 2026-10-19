"""Locate the media time that corresponds to a timeline clip (pure, verifiable).

Resolve reports the in-point in several ways whose reference is not fully specified by
the documentation. The offset is accepted only when independent readings agree and the
resulting range fits inside the probed media duration; otherwise the clip is refused.
"""

from __future__ import annotations

from dataclasses import dataclass

from o_editor.domain.timecode import source_time_matches_frame
from o_editor.domain.timeline_layout import ClipInfo


@dataclass(frozen=True, slots=True)
class SourceTiming:
    offset_seconds: float
    duration_seconds: float
    method: str
    warnings: tuple[str, ...] = ()


class SourceTimingError(ValueError):
    """The clip's media offset could not be established safely."""


def resolve_source_timing(
    clip: ClipInfo,
    *,
    timeline_fps: float,
    media_duration_seconds: float | None,
    tolerance_frames: float = 1.5,
) -> SourceTiming:
    if not clip.is_unit_speed:
        raise SourceTimingError(
            f"O clipe {clip.name or clip.item_id} ({clip.track_key}) usa velocidade ou "
            "conformação diferente de 100%; a reconstrução do áudio não é suportada."
        )
    duration = clip.duration_frames / timeline_fps
    tolerance = tolerance_frames / timeline_fps
    candidates: list[tuple[str, float]] = []
    if clip.left_offset_frames is not None:
        candidates.append(("left_offset", clip.left_offset_frames / timeline_fps))
    if clip.source_start_frame is not None:
        media_fps = clip.media_fps if clip.media_fps and clip.media_fps > 0 else timeline_fps
        candidates.append(("source_start_frame", clip.source_start_frame / media_fps))
    if clip.source_start_seconds is not None:
        candidates.append(("source_start_time", clip.source_start_seconds))
    if not candidates:
        raise SourceTimingError(
            f"O clipe {clip.name or clip.item_id} não informou o ponto de entrada na mídia."
        )
    warnings: list[str] = []
    chosen: tuple[str, float] | None = None
    for index, (name, value) in enumerate(candidates):
        agreeing = [
            other
            for other_index, other in enumerate(candidates)
            if other_index != index and abs(other[1] - value) <= tolerance
        ]
        if agreeing:
            chosen = (name, value)
            break
    if chosen is None:
        if len(candidates) == 1:
            chosen = candidates[0]
            warnings.append(
                f"Deslocamento de {clip.name or clip.item_id} obtido apenas por {chosen[0]}."
            )
        else:
            readings = ", ".join(f"{name}={value:.3f}s" for name, value in candidates)
            raise SourceTimingError(
                f"Leituras divergentes do ponto de entrada de {clip.name or clip.item_id} "
                f"({readings}); a faixa não será reconstruída para evitar dessincronização."
            )
    offset = chosen[1]
    if offset < -tolerance:
        raise SourceTimingError(f"Ponto de entrada negativo em {clip.name or clip.item_id}.")
    offset = max(0.0, offset)
    range_tolerance = max(tolerance, 0.05)
    # Resolve can expose an inclusive/padded final range at the captured source EOF.
    # Keep this separate from in-point agreement and never extend interior clips.
    if clip.right_offset_frames == 0:
        range_tolerance = max(range_tolerance, 2.0 / timeline_fps + 0.001)
        # The rounded FPS label accumulates wall-clock drift on long NTSC media.
        # Compensate only the independently confirmed source-end time, preserving
        # the timeline's sample grid and the existing bounded physical EOF padding.
        if (
            clip.left_offset_frames is not None
            and clip.source_end_seconds is not None
            and clip.media_fps is not None
            and abs(clip.media_fps - timeline_fps) < 0.001
        ):
            end_frame = clip.left_offset_frames + clip.duration_frames
            if float(end_frame).is_integer() and source_time_matches_frame(
                clip.source_end_seconds, int(end_frame), timeline_fps
            ):
                range_tolerance += max(0.0, offset + duration - clip.source_end_seconds)
    if (
        media_duration_seconds is not None
        and offset + duration > media_duration_seconds + range_tolerance
    ):
        raise SourceTimingError(
            f"O trecho de {clip.name or clip.item_id} ({offset:.2f}s + {duration:.2f}s) "
            f"ultrapassa a duração do arquivo ({media_duration_seconds:.2f}s)."
        )
    if media_duration_seconds is not None and offset + duration > media_duration_seconds:
        warnings.append(
            f"O final de {clip.name or clip.item_id} excede a mídia em "
            f"{offset + duration - media_duration_seconds:.3f}s; "
            "a cauda será completada com silêncio, preservando a posição na timeline."
        )
    return SourceTiming(
        offset_seconds=offset,
        duration_seconds=duration,
        method=chosen[0],
        warnings=tuple(warnings),
    )
