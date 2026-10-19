"""Read-only conversion from documented Resolve objects into domain snapshots."""

from __future__ import annotations

from typing import Any

from o_editor.domain.enums import TrackType
from o_editor.domain.models import TimelineItemSnapshot, TimelineSnapshot, stable_id
from o_editor.errors import ResolveUnavailableError


def read_timeline_snapshot(resolve: Any) -> TimelineSnapshot:
    project_manager = _required_call(resolve, "GetProjectManager")
    project = _required_call(project_manager, "GetCurrentProject")
    if project is None:
        raise ResolveUnavailableError("Nenhum projeto está ativo no DaVinci Resolve.")
    timeline = _required_call(project, "GetCurrentTimeline")
    if timeline is None:
        raise ResolveUnavailableError("Nenhuma timeline está ativa no DaVinci Resolve.")

    project_name = str(_required_call(project, "GetName"))
    timeline_name = str(_required_call(timeline, "GetName"))
    start_frame = int(_required_call(timeline, "GetStartFrame"))
    end_frame = int(_required_call(timeline, "GetEndFrame"))
    video_tracks = int(_required_call(timeline, "GetTrackCount", "video"))
    audio_tracks = int(_required_call(timeline, "GetTrackCount", "audio"))
    fps_value = _required_call(timeline, "GetSetting", "timelineFrameRate")
    fps, drop_frame = _parse_fps(fps_value)
    timeline_id = _optional_string_call(timeline, "GetUniqueId")

    items: list[TimelineItemSnapshot] = []
    for track_type, count in (
        (TrackType.VIDEO, video_tracks),
        (TrackType.AUDIO, audio_tracks),
    ):
        for track_index in range(1, count + 1):
            source_items = _required_call(
                timeline,
                "GetItemListInTrack",
                track_type.value,
                track_index,
            )
            for source_item in source_items or ():
                items.append(_read_item(source_item, track_type, track_index))

    return TimelineSnapshot(
        project_name=project_name,
        timeline_name=timeline_name,
        timeline_id=timeline_id,
        fps=fps,
        drop_frame=drop_frame,
        start_frame=start_frame,
        end_frame=end_frame,
        video_track_count=video_tracks,
        audio_track_count=audio_tracks,
        items=tuple(sorted(items, key=lambda item: (item.start_frame, item.track_type, item.id))),
    )


def _read_item(source: Any, track_type: TrackType, track_index: int) -> TimelineItemSnapshot:
    name = str(_required_call(source, "GetName"))
    start = int(_required_call(source, "GetStart"))
    end = int(_required_call(source, "GetEnd"))
    source_start = int(_required_call(source, "GetSourceStartFrame"))
    source_end = int(_required_call(source, "GetSourceEndFrame"))
    item_id = _optional_string_call(source, "GetUniqueId")
    media_pool_item = _required_call(source, "GetMediaPoolItem")
    media_id = _optional_string_call(media_pool_item, "GetMediaId") if media_pool_item else None
    source_path: str | None = None
    if media_pool_item:
        properties = _required_call(media_pool_item, "GetClipProperty")
        if isinstance(properties, dict):
            source_path = _first_string(properties, ("File Path", "FilePath", "Path"))
    enabled_value = _required_call(source, "GetClipEnabled")
    fusion_count = int(_required_call(source, "GetFusionCompCount"))
    properties_value = _required_call(source, "GetProperty")
    properties = (
        tuple(
            sorted(
                (str(key), str(value))
                for key, value in properties_value.items()
                if isinstance(value, str | int | float | bool)
            )
        )
        if isinstance(properties_value, dict)
        else ()
    )
    identity = {
        "track_type": track_type,
        "track_index": track_index,
        "start": start,
        "end": end,
        "source_start": source_start,
        "source_end": source_end,
        "name": name,
        "media_id": media_id,
    }
    return TimelineItemSnapshot(
        id=item_id or stable_id("clip", identity),
        track_type=track_type,
        track_index=track_index,
        start_frame=start,
        end_frame=end,
        source_start_frame=source_start,
        source_end_frame=source_end,
        name=name,
        media_id=media_id,
        source_path=source_path,
        enabled=bool(enabled_value),
        fusion_comp_count=fusion_count,
        is_multicam=_looks_multicam(properties_value),
        properties=properties,
    )


def _required_call(target: Any, method_name: str, *args: Any) -> Any:
    if target is None:
        raise ResolveUnavailableError(f"Objeto ausente antes de {method_name}().")
    method = getattr(target, method_name, None)
    if not callable(method):
        raise ResolveUnavailableError(f"A API instalada não expõe {method_name}().")
    try:
        return method(*args)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise ResolveUnavailableError(f"Falha ao executar {method_name}().") from exc


def _optional_string_call(target: Any, method_name: str) -> str | None:
    if target is None:
        return None
    method = getattr(target, method_name, None)
    if not callable(method):
        return None
    try:
        value = method()
    except (OSError, RuntimeError, TypeError, ValueError):
        return None
    return str(value) if value not in (None, "") else None


def _parse_fps(value: Any) -> tuple[float, bool]:
    normalized = str(value).strip().upper()
    drop_frame = normalized.endswith("DF")
    number = normalized.removesuffix("DF").strip()
    try:
        return float(number), drop_frame
    except ValueError as exc:
        raise ResolveUnavailableError(
            f"O Resolve retornou um frame rate inválido: {value!r}."
        ) from exc


def _first_string(data: dict[Any, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _looks_multicam(properties: Any) -> bool:
    if not isinstance(properties, dict):
        return False
    return any(
        "multicam" in str(key).casefold() and str(value).casefold() not in ("", "false", "0")
        for key, value in properties.items()
    )
