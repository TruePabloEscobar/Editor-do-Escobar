"""Global rough-cut planning: which timeline ranges stay, and how to rebuild them.

Cuts are decided once, on the *global* timeline, and then applied identically to every
participating track, so all participants (and their images) stay in sync. Valid speech
on any track is never removed by an automatic rule.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum
from itertools import pairwise
from typing import Any

from o_editor.domain.enums import TrackType
from o_editor.domain.intervals import (
    Interval,
    clip_to,
    expand,
    intersect,
    normalize,
    subtract,
    total,
    union,
)
from o_editor.domain.microphone_cleanup import (
    MicrophoneCleanupSettings,
    MicrophoneMute,
    confirmed_microphone_segments,
    microphone_mutes,
)
from o_editor.domain.speech import SegmentFlag, SegmentState, SpeechSegment, TranscriptSession
from o_editor.domain.timeline_layout import ClipInfo, TimelineLayout

PLAN_SCHEMA_VERSION = 1


class TrackPolicy(StrEnum):
    FOLLOW = "FOLLOW"
    OMIT = "OMIT"


class SilencePreset(StrEnum):
    OFF = "OFF"
    LIGHT = "LIGHT"
    MEDIUM = "MEDIUM"
    STRONG = "STRONG"
    CUSTOM = "CUSTOM"


class RemovalReason(StrEnum):
    TEXT_CUT = "TEXTO_CUT"
    SILENCE_START = "SILENCIO_INICIAL"
    SILENCE_END = "SILENCIO_FINAL"
    SILENCE_PAUSE = "PAUSA_LONGA"


@dataclass(frozen=True, slots=True)
class SilenceSettings:
    enabled: bool = True
    minimum_silence_ms: int = 1200
    keep_before_speech_ms: int = 250
    keep_after_speech_ms: int = 350
    protect_untranscribed_sound: bool = True
    trim_start_and_end: bool = True

    @classmethod
    def from_preset(cls, preset: SilencePreset) -> SilenceSettings:
        if preset == SilencePreset.OFF:
            return cls(enabled=False)
        values = {
            SilencePreset.LIGHT: (2000, 400, 500),
            SilencePreset.MEDIUM: (1200, 250, 350),
            SilencePreset.STRONG: (700, 150, 200),
        }.get(preset, (1200, 250, 350))
        return cls(
            enabled=True,
            minimum_silence_ms=values[0],
            keep_before_speech_ms=values[1],
            keep_after_speech_ms=values[2],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "minimum_silence_ms": self.minimum_silence_ms,
            "keep_before_speech_ms": self.keep_before_speech_ms,
            "keep_after_speech_ms": self.keep_after_speech_ms,
            "protect_untranscribed_sound": self.protect_untranscribed_sound,
            "trim_start_and_end": self.trim_start_and_end,
        }


@dataclass(frozen=True, slots=True)
class CutSettings:
    speech_guard_before_ms: int = 100
    speech_guard_after_ms: int = 150
    minimum_cut_ms: int = 120

    def to_dict(self) -> dict[str, Any]:
        return {
            "speech_guard_before_ms": self.speech_guard_before_ms,
            "speech_guard_after_ms": self.speech_guard_after_ms,
            "minimum_cut_ms": self.minimum_cut_ms,
        }


@dataclass(frozen=True, slots=True)
class PlanIssue:
    severity: str
    message: str

    def render(self) -> str:
        return f"[{self.severity}] {self.message}"


@dataclass(frozen=True, slots=True)
class RemovedRange:
    start_frame: int
    end_frame: int
    reasons: tuple[str, ...]
    segment_ids: tuple[str, ...] = ()

    @property
    def duration_frames(self) -> int:
        return self.end_frame - self.start_frame


@dataclass(frozen=True, slots=True)
class KeepRange:
    source_start: int
    source_end: int
    record_start: int

    @property
    def duration_frames(self) -> int:
        return self.source_end - self.source_start


@dataclass(frozen=True, slots=True)
class RebuildOperation:
    op_id: str
    track_type: TrackType
    track_index: int
    source_item_id: str
    media_pool_item_id: str
    media_type: int
    source_start: int
    source_end: int
    record_start: int
    record_end: int
    keep_index: int
    clip_name: str
    enabled: bool = True
    link_group: str | None = None
    # Zoom per take (ZoomX/ZoomY/AnchorPointX/AnchorPointY); None leaves the copy as is.
    zoom: Mapping[str, float] | None = None

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "op_id": self.op_id,
            "track_type": self.track_type.value,
            "track_index": self.track_index,
            "source_item_id": self.source_item_id,
            "media_pool_item_id": self.media_pool_item_id,
            "media_type": self.media_type,
            "source_start": self.source_start,
            "source_end": self.source_end,
            "record_start": self.record_start,
            "record_end": self.record_end,
            "keep_index": self.keep_index,
            "clip_name": self.clip_name,
            "enabled": self.enabled,
            "link_group": self.link_group,
        }
        if self.zoom is not None:
            value["zoom"] = dict(self.zoom)
        return value


@dataclass(frozen=True, slots=True)
class RoughCutStats:
    original_frames: int
    new_frames: int
    removed_frames: int
    silence_frames: int
    text_frames: int
    removed_segments: int
    partially_removed_segments: int
    kept_segments: int
    operations: int

    def to_dict(self) -> dict[str, int]:
        return {
            "original_frames": self.original_frames,
            "new_frames": self.new_frames,
            "removed_frames": self.removed_frames,
            "silence_frames": self.silence_frames,
            "text_frames": self.text_frames,
            "removed_segments": self.removed_segments,
            "partially_removed_segments": self.partially_removed_segments,
            "kept_segments": self.kept_segments,
            "operations": self.operations,
        }


@dataclass(frozen=True, slots=True)
class RoughCutPlan:
    plan_id: str
    created_at: str
    session_id: str
    session_revision: int
    layout: TimelineLayout
    target_timeline_name: str
    keep_ranges: tuple[KeepRange, ...]
    removed_ranges: tuple[RemovedRange, ...]
    operations: tuple[RebuildOperation, ...]
    track_policies: Mapping[str, TrackPolicy]
    silence: SilenceSettings
    cut: CutSettings
    stats: RoughCutStats
    issues: tuple[PlanIssue, ...] = field(default=())
    microphone_cleanup: MicrophoneCleanupSettings = field(default_factory=MicrophoneCleanupSettings)
    microphone_mutes: tuple[MicrophoneMute, ...] = ()
    # Settings and summary of the zoom per take applied together with the cut.
    take_zoom: Mapping[str, Any] | None = None

    @property
    def blocked(self) -> bool:
        return any(issue.severity == "BLOQUEIO" for issue in self.issues)

    def to_dict(self, *, mode: str = "VALIDATE", confirmed_by_user: bool = False) -> dict[str, Any]:
        layout = self.layout
        value: dict[str, Any] = {
            "schema_version": PLAN_SCHEMA_VERSION,
            "kind": "rough_cut",
            "plan_id": self.plan_id,
            "created_at": self.created_at,
            "mode": mode,
            "confirmed_by_user": confirmed_by_user,
            "session_id": self.session_id,
            "session_revision": self.session_revision,
            "source": {
                "project_name": layout.project_name,
                "timeline_name": layout.timeline_name,
                "timeline_id": layout.timeline_id,
                "fps": layout.fps,
                "start_frame": layout.start_frame,
                "end_frame": layout.end_frame,
                "start_timecode": layout.start_timecode,
                "layout_fingerprint": layout.fingerprint,
                "clips": [
                    {
                        "item_id": clip.item_id,
                        "track_type": clip.track_type.value,
                        "track_index": clip.track_index,
                        "start_frame": clip.start_frame,
                        "end_frame": clip.end_frame,
                        "media_pool_item_id": clip.media_pool_item_id,
                        "left_offset_frames": clip.left_offset_frames,
                        "source_start_frame": clip.source_start_frame,
                        "enabled": clip.enabled,
                        "audio_channel_mapping": clip.audio_channel_mapping,
                    }
                    for clip in layout.clips
                ],
                "track_counts": {
                    kind.value: len(layout.tracks_of(kind))
                    for kind in (TrackType.VIDEO, TrackType.AUDIO, TrackType.SUBTITLE)
                },
            },
            "target": {"timeline_name": self.target_timeline_name},
            "keep_ranges": [
                {
                    "source_start": item.source_start,
                    "source_end": item.source_end,
                    "record_start": item.record_start,
                }
                for item in self.keep_ranges
            ],
            "removed_ranges": [
                {
                    "start_frame": item.start_frame,
                    "end_frame": item.end_frame,
                    "reasons": list(item.reasons),
                    "segment_ids": list(item.segment_ids),
                }
                for item in self.removed_ranges
            ],
            "operations": [operation.to_dict() for operation in self.operations],
            "track_policies": {
                key: value.value for key, value in sorted(self.track_policies.items())
            },
            "silence": self.silence.to_dict(),
            "cut": self.cut.to_dict(),
            "microphone_cleanup": self.microphone_cleanup.to_dict(),
            "microphone_mutes": [item.to_dict() for item in self.microphone_mutes],
            "stats": self.stats.to_dict(),
            "issues": [issue.render() for issue in self.issues],
        }
        if self.take_zoom is not None:
            value["take_zoom"] = dict(self.take_zoom)
        return value


def build_rough_cut_plan(
    session: TranscriptSession,
    layout: TimelineLayout,
    *,
    silence: SilenceSettings,
    cut: CutSettings,
    track_policies: Mapping[str, TrackPolicy] | None = None,
    microphone_cleanup: MicrophoneCleanupSettings | None = None,
    target_timeline_name: str,
    plan_id: str,
    created_at: str,
) -> RoughCutPlan:
    issues: list[PlanIssue] = []
    policies = dict(track_policies or {})
    cleanup = microphone_cleanup or MicrophoneCleanupSettings()
    routing_session = session
    if cleanup.enabled:
        audible_tracks = {
            track.index
            for track in layout.tracks
            if track.track_type == TrackType.AUDIO
            and track.enabled is not False
            and policies.get(track.key, TrackPolicy.FOLLOW) != TrackPolicy.OMIT
        }
        # A muted/omitted reference cannot justify muting the only remaining voice.
        # Keep the original session intact; only the gating evidence is restricted.
        routing_session = replace(
            session,
            tracks=tuple(t for t in session.tracks if t.track_index in audible_tracks),
            segments=tuple(s for s in session.segments if s.track_index in audible_tracks),
        )
        confirmed = {s.segment_id: s for s in confirmed_microphone_segments(routing_session)}
        session = replace(
            session, segments=tuple(confirmed.get(s.segment_id, s) for s in session.segments)
        )
    mic_mutes = microphone_mutes(routing_session, cleanup)
    if session.pending_missing:
        issues.append(
            PlanIssue(
                "BLOQUEIO",
                f"{len(session.pending_missing)} trecho(s) ausente(s) do TXT importado aguardam "
                "sua confirmação (remover ou manter).",
            )
        )
    if layout.fingerprint != session.layout_fingerprint:
        issues.append(
            PlanIssue(
                "BLOQUEIO",
                "A timeline atual é diferente da timeline transcrita. Transcreva novamente "
                "antes de cortar.",
            )
        )
    problems = layout.validate()
    issues.extend(PlanIssue("BLOQUEIO", problem) for problem in problems)

    def frames(milliseconds: int) -> int:
        return max(0, round(milliseconds * layout.fps / 1000))

    bounds: Interval = (layout.start_frame, layout.end_frame)
    speech = [item for item in session.segments if not item.is_bleed]
    protected = clip_to(
        expand(
            ((item.start_frame, item.end_frame) for item in speech if item.protects_audio),
            frames(cut.speech_guard_before_ms),
            frames(cut.speech_guard_after_ms),
        ),
        bounds,
    )
    cut_segments = [item for item in speech if item.state == SegmentState.CUT]
    cut_ranges = normalize((item.start_frame, item.end_frame) for item in cut_segments)
    activity: tuple[Interval, ...] = ()
    if silence.protect_untranscribed_sound:
        activity = subtract(union(*(ranges for ranges in session.activity.values())), cut_ranges)
    occupied = union(
        ((item.start_frame, item.end_frame) for item in speech if item.protects_audio),
        activity,
    )

    silence_ranges: list[tuple[Interval, RemovalReason]] = []
    if silence.enabled:
        before = frames(silence.keep_before_speech_ms)
        after = frames(silence.keep_after_speech_ms)
        minimum = frames(silence.minimum_silence_ms)
        gaps = subtract((bounds,), occupied)
        if gaps == (bounds,):
            issues.append(
                PlanIssue(
                    "AVISO", "Nenhuma fala ou som foi detectado; silêncios não serão removidos."
                )
            )
            gaps = ()
        for start, end in gaps:
            if start == bounds[0]:
                if not silence.trim_start_and_end:
                    continue
                candidate, reason = (start, end - before), RemovalReason.SILENCE_START
            elif end == bounds[1]:
                if not silence.trim_start_and_end:
                    continue
                candidate, reason = (start + after, end), RemovalReason.SILENCE_END
            else:
                if end - start < minimum:
                    continue
                candidate, reason = (start + after, end - before), RemovalReason.SILENCE_PAUSE
            if candidate[1] > candidate[0]:
                silence_ranges.append((candidate, reason))

    text_pieces = subtract(cut_ranges, protected)
    candidates = union((item[0] for item in silence_ranges), text_pieces)
    removed = subtract(clip_to(candidates, bounds), protected)
    minimum_cut = max(1, frames(cut.minimum_cut_ms))
    removed = tuple(item for item in removed if item[1] - item[0] >= minimum_cut)
    keep_intervals = subtract((bounds,), removed)

    keep_ranges: list[KeepRange] = []
    cursor = layout.start_frame
    for start, end in keep_intervals:
        keep_ranges.append(KeepRange(start, end, cursor))
        cursor += end - start

    removed_ranges = _annotate(removed, silence_ranges, cut_segments)
    removed_segments, partial, kept_count = _segment_outcomes(
        session, speech, cut_segments, removed, issues
    )
    if mic_mutes:
        boundaries = sorted({n for mute in mic_mutes for n in (mute.start_frame, mute.end_frame)})
        split = []
        for keep in keep_ranges:
            points = [
                keep.source_start,
                *(n for n in boundaries if keep.source_start < n < keep.source_end),
                keep.source_end,
            ]
            for lo, hi in pairwise(points):
                split.append(KeepRange(lo, hi, keep.record_start + lo - keep.source_start))
        keep_ranges = split
    operations = _operations(layout, tuple(keep_ranges), policies, issues, mic_mutes)
    if not keep_ranges:
        issues.append(PlanIssue("BLOQUEIO", "O plano removeria a timeline inteira."))
    if not operations and keep_ranges:
        issues.append(PlanIssue("BLOQUEIO", "Nenhum clipe reconstruível foi encontrado."))
    overlap_count = sum(1 for item in speech if SegmentFlag.OVERLAP in item.flags)
    if overlap_count:
        issues.append(
            PlanIssue(
                "INFO",
                f"{overlap_count} trecho(s) com fala simultânea foram preservados nos intervalos "
                "sobrepostos.",
            )
        )
    bleed_count = sum(1 for item in session.segments if item.is_bleed)
    if bleed_count:
        issues.append(
            PlanIssue(
                "INFO",
                f"{bleed_count} trecho(s) de vazamento entre microfones não protegem intervalos "
                "(a fala original continua protegida na faixa de quem falou).",
            )
        )
    silence_frames = total(intersect(removed, (item[0] for item in silence_ranges)))
    text_frames = total(intersect(removed, text_pieces))
    stats = RoughCutStats(
        original_frames=layout.duration_frames,
        new_frames=sum(item.duration_frames for item in keep_ranges),
        removed_frames=total(removed),
        silence_frames=silence_frames,
        text_frames=text_frames,
        removed_segments=removed_segments,
        partially_removed_segments=partial,
        kept_segments=kept_count,
        operations=len(operations),
    )
    return RoughCutPlan(
        plan_id=plan_id,
        created_at=created_at,
        session_id=session.session_id,
        session_revision=session.revision,
        layout=layout,
        target_timeline_name=target_timeline_name,
        keep_ranges=tuple(keep_ranges),
        removed_ranges=removed_ranges,
        operations=operations,
        track_policies={
            track.key: policies.get(track.key, TrackPolicy.FOLLOW) for track in layout.tracks
        },
        silence=silence,
        cut=cut,
        stats=stats,
        issues=tuple(issues),
        microphone_cleanup=cleanup,
        microphone_mutes=mic_mutes,
    )


def _annotate(
    removed: Iterable[Interval],
    silence_ranges: list[tuple[Interval, RemovalReason]],
    cut_segments: list[SpeechSegment],
) -> tuple[RemovedRange, ...]:
    result: list[RemovedRange] = []
    for start, end in removed:
        reasons: list[str] = []
        segment_ids: list[str] = []
        for (silence_start, silence_end), reason in silence_ranges:
            if silence_start < end and start < silence_end and reason.value not in reasons:
                reasons.append(reason.value)
        for segment in cut_segments:
            if segment.start_frame < end and start < segment.end_frame:
                segment_ids.append(segment.segment_id)
        if segment_ids:
            reasons.insert(0, RemovalReason.TEXT_CUT.value)
        result.append(RemovedRange(start, end, tuple(reasons), tuple(segment_ids)))
    return tuple(result)


def _segment_outcomes(
    session: TranscriptSession,
    speech: list[SpeechSegment],
    cut_segments: list[SpeechSegment],
    removed: tuple[Interval, ...],
    issues: list[PlanIssue],
) -> tuple[int, int, int]:
    removed_count = 0
    partial = 0
    for segment in cut_segments:
        length = segment.duration_frames
        gone = total(intersect(((segment.start_frame, segment.end_frame),), removed))
        if gone == 0:
            issues.append(
                PlanIssue(
                    "AVISO",
                    f"{segment.segment_id} ({session.speaker_name(segment.track_index)}) está "
                    "marcado como CUT, mas coincide totalmente com fala mantida de outra faixa "
                    "e não foi removido.",
                )
            )
        elif gone < length * 0.95:
            partial += 1
            issues.append(
                PlanIssue(
                    "AVISO",
                    f"{segment.segment_id} ({session.speaker_name(segment.track_index)}) foi "
                    "removido parcialmente: parte dele coincide com fala mantida de outra faixa.",
                )
            )
        else:
            removed_count += 1
    kept = sum(1 for item in speech if item.state == SegmentState.KEEP)
    return removed_count, partial, kept


def _link_groups(layout: TimelineLayout) -> dict[str, str]:
    parent: dict[str, str] = {clip.item_id: clip.item_id for clip in layout.clips}

    def find(item: str) -> str:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    for clip in layout.clips:
        for other in clip.linked_item_ids:
            if other in parent:
                left, right = find(clip.item_id), find(other)
                if left != right:
                    parent[max(left, right)] = min(left, right)
    groups: dict[str, list[str]] = {}
    for item in parent:
        groups.setdefault(find(item), []).append(item)
    return {item: root for root, members in groups.items() if len(members) > 1 for item in members}


def _operations(
    layout: TimelineLayout,
    keep_ranges: tuple[KeepRange, ...],
    policies: Mapping[str, TrackPolicy],
    issues: list[PlanIssue],
    mic_mutes: tuple[MicrophoneMute, ...] = (),
) -> tuple[RebuildOperation, ...]:
    groups = _link_groups(layout)
    # Index containment by track, retaining the old "one mute covers the whole
    # piece" rule even for overlapping/non-disjoint intervals. Prefix maxima
    # prevent a short later interval from hiding a longer containing interval.
    mute_ranges: dict[int, list[tuple[int, int]]] = {}
    for mute in mic_mutes:
        mute_ranges.setdefault(mute.track_index, []).append((mute.start_frame, mute.end_frame))
    mute_index: dict[int, tuple[list[int], list[int]]] = {}
    for index, ranges in mute_ranges.items():
        starts, ends = [], []
        maximum = -1
        for start, end in sorted(ranges):
            starts.append(start)
            maximum = max(maximum, end)
            ends.append(maximum)
        mute_index[index] = starts, ends
    operations: list[RebuildOperation] = []
    for track in sorted(layout.tracks, key=lambda item: (item.track_type.value, item.index)):
        mute_starts, mute_ends = (
            mute_index.get(track.index, ([], []))
            if track.track_type == TrackType.AUDIO
            else ([], [])
        )
        clips = layout.clips_in_track(track.track_type, track.index)
        policy = policies.get(track.key, TrackPolicy.FOLLOW)
        if policy == TrackPolicy.OMIT:
            if clips:
                issues.append(
                    PlanIssue("INFO", f"{track.display_name} será omitida da nova timeline.")
                )
            continue
        if track.track_type == TrackType.SUBTITLE:
            if clips:
                issues.append(
                    PlanIssue(
                        "AVISO",
                        f"{track.display_name}: legendas não são reconstruídas e ficarão vazias.",
                    )
                )
            continue
        for clip in clips:
            pieces = _clip_pieces(clip, keep_ranges)
            if not pieces:
                continue
            reason = _unsupported_reason(clip)
            if reason:
                if track.track_type == TrackType.AUDIO:
                    # Dropping audio silently could remove a participant: block instead.
                    issues.append(
                        PlanIssue(
                            "BLOQUEIO",
                            f"{track.display_name}: '{clip.name or clip.item_id}' não pode ser "
                            f"reconstruído ({reason}). Ajuste o clipe ou defina a faixa como "
                            "'Omitir' se ela não deve entrar na nova timeline.",
                        )
                    )
                else:
                    issues.append(
                        PlanIssue(
                            "AVISO",
                            f"{track.display_name}: '{clip.name or clip.item_id}' não será "
                            f"incluído na nova timeline ({reason}).",
                        )
                    )
                continue
            if clip.fusion_comp_count:
                issues.append(
                    PlanIssue(
                        "AVISO",
                        f"{track.display_name}: composições Fusion de '{clip.name}' não são "
                        "copiadas para a nova timeline.",
                    )
                )
            assert clip.media_pool_item_id is not None
            for keep_index, start, end, keep in pieces:
                record_start = keep.record_start + (start - keep.source_start)
                group = groups.get(clip.item_id)
                mute_position = bisect_right(mute_starts, start) - 1
                muted = mute_position >= 0 and mute_ends[mute_position] >= end
                operations.append(
                    RebuildOperation(
                        op_id=f"OP_{len(operations) + 1:05d}",
                        track_type=track.track_type,
                        track_index=track.index,
                        source_item_id=clip.item_id,
                        media_pool_item_id=clip.media_pool_item_id,
                        media_type=1 if track.track_type == TrackType.VIDEO else 2,
                        source_start=clip.source_frame_at(start, timeline_fps=layout.fps),
                        source_end=clip.source_frame_at(end, timeline_fps=layout.fps),
                        record_start=record_start,
                        record_end=record_start + (end - start),
                        keep_index=keep_index,
                        clip_name=clip.name,
                        enabled=clip.enabled and not muted,
                        link_group=f"{group}#{keep_index}" if group else None,
                    )
                )
    operations.sort(
        key=lambda item: (
            item.keep_index,
            0 if item.track_type == TrackType.VIDEO else 1,
            item.track_index,
        )
    )
    return tuple(
        replace(item, op_id=f"OP_{index:05d}") for index, item in enumerate(operations, start=1)
    )


def _clip_pieces(
    clip: ClipInfo, keep_ranges: tuple[KeepRange, ...]
) -> list[tuple[int, int, int, KeepRange]]:
    pieces = []
    for index, keep in enumerate(keep_ranges):
        start = max(clip.start_frame, keep.source_start)
        end = min(clip.end_frame, keep.source_end)
        if end > start:
            pieces.append((index, start, end, keep))
    return pieces


def _unsupported_reason(clip: ClipInfo) -> str | None:
    if clip.item_type not in {"video", "audio"}:
        return f"item do tipo {clip.item_type}"
    if clip.media_pool_item_id is None:
        return "sem item do Media Pool"
    if not clip.has_source_range:
        return "sem intervalo de origem legível"
    if not clip.is_unit_speed:
        return "velocidade diferente de 100%"
    return None
