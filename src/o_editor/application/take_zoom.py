"""Zoom per take: previews, one-use requests for Resolve and the undo history.

Mutations happen only inside Resolve (``M.apply_take_zoom`` in internal_common.lua),
only on timelines created by O Editor and always with readback. This module keeps:

* ``oe-timelines.json``: timelines created by O Editor and their cut points;
* ``take-zoom-history.json``: applied zooms per timeline (several undo levels).
"""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from o_editor.domain.take_zoom import (
    ZOOM_PROPERTY_KEYS,
    ItemZoomTarget,
    TakeAssignment,
    TakeZoomSettings,
    assign_takes,
    cut_points_match,
    item_targets,
    summarize,
    takes_from_layout,
)
from o_editor.domain.timeline_layout import TimelineLayout
from o_editor.errors import OEditorError

PENDING_NAME = "take-zoom-pending.json"
REGISTRY_NAME = "oe-timelines.json"
HISTORY_NAME = "take-zoom-history.json"
HISTORY_LEVELS = 50
SCHEMA_VERSION = 1


class TakeZoomApplicationError(OEditorError):
    """The zoom request could not be prepared."""


def plans_directory() -> Path:
    from o_editor.application.rough_cut import plans_directory as rough_cut_plans

    return rough_cut_plans()


def is_o_editor_timeline(name: str | None) -> bool:
    """Same rule as the Lua guard: created by O Editor and not a failed copy."""

    text = str(name or "")
    return "_OE_ROUGHCUT_" in text and not text.endswith("_FALHOU")


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return None


# --------------------------------------------------------------------- registry


class TimelineRegistry:
    """Timelines created by O Editor (id, name and cut points)."""

    def __init__(self, directory: Path | None = None) -> None:
        self.path = (directory or plans_directory()) / REGISTRY_NAME

    def _load(self) -> dict[str, Any]:
        data = _read_json(self.path)
        if not isinstance(data, dict) or not isinstance(data.get("timelines"), dict):
            return {"schema_version": SCHEMA_VERSION, "timelines": {}}
        return data

    def record(
        self,
        *,
        timeline_id: str,
        timeline_name: str,
        project_name: str | None,
        take_starts: Sequence[int],
        plan_id: str | None,
    ) -> None:
        if not timeline_id or not is_o_editor_timeline(timeline_name):
            return
        data = self._load()
        data["timelines"][timeline_id] = {
            "timeline_name": timeline_name,
            "project_name": project_name,
            "take_starts": sorted({int(value) for value in take_starts}),
            "plan_id": plan_id,
            "recorded_at": _now(),
        }
        _atomic_write(self.path, json.dumps(data, ensure_ascii=False, indent=1))

    def get(self, timeline_id: str | None) -> dict[str, Any] | None:
        if not timeline_id:
            return None
        entry = self._load()["timelines"].get(str(timeline_id))
        return entry if isinstance(entry, dict) else None


# ---------------------------------------------------------------------- history


class ZoomHistory:
    """Applied zooms per timeline id; the last one is undone first."""

    def __init__(self, directory: Path | None = None) -> None:
        self.path = (directory or plans_directory()) / HISTORY_NAME

    def _load(self) -> dict[str, Any]:
        data = _read_json(self.path)
        if not isinstance(data, dict) or not isinstance(data.get("timelines"), dict):
            return {"schema_version": SCHEMA_VERSION, "timelines": {}}
        return data

    def _save(self, data: dict[str, Any]) -> None:
        _atomic_write(self.path, json.dumps(data, ensure_ascii=False, indent=1))

    def entries(self, timeline_id: str | None) -> list[dict[str, Any]]:
        if not timeline_id:
            return []
        value = self._load()["timelines"].get(str(timeline_id))
        return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []

    def depth(self, timeline_id: str | None) -> int:
        return len(self.entries(timeline_id))

    def last(self, timeline_id: str | None) -> dict[str, Any] | None:
        entries = self.entries(timeline_id)
        return entries[-1] if entries else None

    def push(self, entry: Mapping[str, Any]) -> bool:
        timeline_id = str(entry.get("timeline_id") or "")
        journal = entry.get("journal")
        if not timeline_id or not isinstance(journal, list) or not journal:
            return False
        data = self._load()
        stack = data["timelines"].setdefault(timeline_id, [])
        if any(item.get("application_id") == entry.get("application_id") for item in stack):
            return False
        stack.append(dict(entry))
        del stack[:-HISTORY_LEVELS]
        self._save(data)
        return True

    def pop(self, timeline_id: str | None, application_id: str | None) -> bool:
        if not timeline_id or not application_id:
            return False
        data = self._load()
        stack = data["timelines"].get(str(timeline_id))
        if not isinstance(stack, list) or not stack:
            return False
        if stack[-1].get("application_id") != application_id:
            return False
        stack.pop()
        self._save(data)
        return True


# ---------------------------------------------------------------------- preview


@dataclass(frozen=True, slots=True)
class TakeZoomPreview:
    settings: TakeZoomSettings
    layout: TimelineLayout
    assignments: tuple[TakeAssignment, ...]
    targets: tuple[ItemZoomTarget, ...]
    cut_points_known: bool

    @property
    def summary(self) -> dict[str, Any]:
        return summarize(self.assignments)


def preview_take_zoom(
    layout: TimelineLayout,
    settings: TakeZoomSettings,
    *,
    take_starts: Sequence[int] | None = None,
) -> TakeZoomPreview:
    settings.validated()
    takes = takes_from_layout(layout, settings.reference_track, boundaries=take_starts)
    if not takes:
        raise TakeZoomApplicationError(
            f"A faixa V{settings.reference_track} não tem clipes para dividir em takes."
        )
    assignments = assign_takes(takes, settings)
    targets = item_targets(layout, assignments, settings)
    if not targets:
        raise TakeZoomApplicationError(
            "Nenhum clipe de vídeo das faixas escolhidas seria alterado."
        )
    known = bool(take_starts) and cut_points_match(
        layout, settings.reference_track, take_starts or ()
    )
    return TakeZoomPreview(settings, layout, assignments, targets, known)


def build_apply_plan(preview: TakeZoomPreview) -> dict[str, Any]:
    layout = preview.layout
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "take_zoom",
        "purpose": "apply",
        "plan_id": uuid.uuid4().hex,
        "created_at": _now(),
        "mode": "APPLY",
        "confirmed_by_user": True,
        "undo_of": None,
        "timeline": {
            "project_name": layout.project_name,
            "timeline_name": layout.timeline_name,
            "timeline_id": layout.timeline_id,
        },
        "settings": preview.settings.to_dict(),
        "summary": preview.summary,
        "items": [target.to_dict() for target in preview.targets],
    }


def build_undo_plan(entry: Mapping[str, Any], *, project_name: str) -> dict[str, Any]:
    """Restore the values from before ``entry``; Resolve checks nothing changed since."""

    items = []
    for record in entry.get("journal") or []:
        before = {key: float(record["before"][key]) for key in ZOOM_PROPERTY_KEYS}
        after = {key: float(record["after"][key]) for key in ZOOM_PROPERTY_KEYS}
        items.append(
            {
                "item_id": str(record["item_id"]),
                "track_index": int(record["track_index"]),
                "take_index": record.get("take_index"),
                "start_frame": int(record["start_frame"]),
                "end_frame": int(record["end_frame"]),
                "set": before,
                "expect": after,
            }
        )
    if not items:
        raise TakeZoomApplicationError("Não há valores anteriores para desfazer.")
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "take_zoom",
        "purpose": "undo",
        "plan_id": uuid.uuid4().hex,
        "created_at": _now(),
        "mode": "APPLY",
        "confirmed_by_user": True,
        "undo_of": entry.get("application_id"),
        "timeline": {
            "project_name": project_name,
            "timeline_name": entry.get("timeline_name"),
            "timeline_id": entry.get("timeline_id"),
        },
        "items": items,
    }


def save_request(plan: Mapping[str, Any], *, directory: Path | None = None) -> Path:
    """Write the plan and the one-use request consumed by the single Resolve menu."""

    if plan.get("kind") != "take_zoom" or plan.get("mode") != "APPLY":
        raise TakeZoomApplicationError("Pedido de zoom inválido.")
    if not is_o_editor_timeline((plan.get("timeline") or {}).get("timeline_name")):
        raise TakeZoomApplicationError(
            "O zoom só pode ser aplicado em timelines criadas pelo O Editor."
        )
    root = directory or plans_directory()
    root.mkdir(parents=True, exist_ok=True)
    (root / "applied").mkdir(exist_ok=True)
    text = json.dumps(plan, ensure_ascii=False, indent=1, sort_keys=True)
    _atomic_write(root / f"take-zoom-{plan['plan_id']}.json", text)
    pending = root / PENDING_NAME
    _atomic_write(pending, text)
    request = {
        "schema_version": 1,
        "request_id": uuid.uuid4().hex,
        "action": "take_zoom",
        "plan_id": plan["plan_id"],
        "mode": "APPLY",
        "created_at": _now(),
    }
    _atomic_write(root / "menu-action.json", json.dumps(request))
    return pending


# ---------------------------------------------------------------------- results


def record_rough_cut_outcome(
    details: Mapping[str, Any], *, project_name: str | None, directory: Path | None = None
) -> None:
    """Remember a timeline created by O Editor and any zoom applied together."""

    timeline_id = str(details.get("created_timeline_id") or "")
    timeline_name = str(details.get("created_timeline") or "")
    if not timeline_id or not is_o_editor_timeline(timeline_name):
        return
    starts = details.get("take_starts")
    TimelineRegistry(directory).record(
        timeline_id=timeline_id,
        timeline_name=timeline_name,
        project_name=project_name,
        take_starts=[int(value) for value in starts] if isinstance(starts, list) else [],
        plan_id=str(details.get("plan_id") or "") or None,
    )
    zoom = details.get("take_zoom")
    if isinstance(zoom, Mapping) and isinstance(zoom.get("journal"), list):
        ZoomHistory(directory).push(
            {
                "application_id": str(details.get("plan_id") or ""),
                "source": "rough_cut",
                "timeline_id": timeline_id,
                "timeline_name": timeline_name,
                "applied_at": _now(),
                "journal": zoom["journal"],
            }
        )


def record_take_zoom_outcome(
    status: str, details: Mapping[str, Any], *, directory: Path | None = None
) -> str:
    """Update the undo history from a Resolve result. Returns what happened."""

    if status != "SUCCESS":
        return "unchanged"
    history = ZoomHistory(directory)
    timeline_id = str(details.get("timeline_id") or "")
    if details.get("purpose") == "undo":
        return (
            "undone" if history.pop(timeline_id, str(details.get("undo_of") or "")) else "unchanged"
        )
    pushed = history.push(
        {
            "application_id": str(details.get("plan_id") or ""),
            "source": "take_zoom",
            "timeline_id": timeline_id,
            "timeline_name": details.get("timeline_name"),
            "applied_at": _now(),
            "journal": details.get("journal"),
        }
    )
    return "applied" if pushed else "unchanged"
