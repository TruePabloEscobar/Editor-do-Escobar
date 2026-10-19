"""Prepare, preview and hand off a rough-cut plan to the internal Resolve host."""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

from o_editor.application.microphone_analysis import with_cached_signal_fingerprints
from o_editor.domain.microphone_cleanup import MicrophoneCleanupSettings
from o_editor.domain.rough_cut import (
    CutSettings,
    RoughCutPlan,
    SilenceSettings,
    TrackPolicy,
    build_rough_cut_plan,
)
from o_editor.domain.speech import SegmentState, TranscriptSession
from o_editor.domain.timecode import frames_to_clock, frames_to_timecode
from o_editor.domain.timeline_layout import TimelineLayout
from o_editor.errors import OEditorError

PENDING_PLAN_NAME = "rough-cut-pending.json"
APPLY_SCRIPT_MENU = "Área de Trabalho > Scripts > O EDITOR"


class RoughCutError(OEditorError):
    """A rough-cut plan could not be prepared or saved."""


def prepare_rough_cut(
    session: TranscriptSession,
    *,
    layout: TimelineLayout | None = None,
    silence: SilenceSettings,
    cut: CutSettings | None = None,
    track_policies: Mapping[str, TrackPolicy] | None = None,
    suffix: str = "_OE_ROUGHCUT_001",
    microphone_cleanup: MicrophoneCleanupSettings | None = None,
) -> RoughCutPlan:
    current = layout or TimelineLayout.from_dict(dict(session.layout))
    if (
        microphone_cleanup
        and microphone_cleanup.enabled
        and current.fingerprint == session.layout_fingerprint
    ):
        session = with_cached_signal_fingerprints(session)
    return build_rough_cut_plan(
        session,
        current,
        silence=silence,
        cut=cut or CutSettings(),
        track_policies=track_policies,
        microphone_cleanup=microphone_cleanup,
        target_timeline_name=f"{current.timeline_name}{suffix}",
        plan_id=uuid.uuid4().hex,
        created_at=datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    )


def render_preview(plan: RoughCutPlan, session: TranscriptSession, *, limit: int = 40) -> str:
    stats = plan.stats
    fps = plan.layout.fps
    start = plan.layout.start_frame

    def clock(frames: int) -> str:
        return frames_to_clock(frames, fps)

    def position(frame: int) -> str:
        return clock(frame - start)

    lines = [
        "PRÉVIA DO ROUGH CUT",
        f"Timeline de origem: {plan.layout.timeline_name} (não será alterada)",
        f"Nova timeline: {plan.target_timeline_name}",
        f"Duração original: {clock(stats.original_frames)}",
        f"Duração estimada: {clock(stats.new_frames)}",
        f"Tempo removido: {clock(stats.removed_frames)} "
        f"(silêncio {clock(stats.silence_frames)}, cortes de texto {clock(stats.text_frames)})",
        f"Trechos removidos: {stats.removed_segments} completos, "
        f"{stats.partially_removed_segments} parciais",
        f"Trechos mantidos: {stats.kept_segments}",
        f"Intervalos mantidos: {len(plan.keep_ranges)}; itens a criar: {stats.operations}",
        "",
    ]
    lines.append(
        "MICROFONES: "
        + ("limpeza ativada" if plan.microphone_cleanup.enabled else "limpeza desligada")
    )
    for mute in plan.microphone_mutes[:limit]:
        lines.append(
            f"  A{mute.track_index} desativada {position(mute.start_frame)} → "
            f"{position(mute.end_frame)}: {mute.reason}"
        )
    if len(plan.microphone_mutes) > limit:
        lines.append(f"  … e mais {len(plan.microphone_mutes) - limit} intervalos")
    lines.append("A desativação afeta só os clipes da cópia; vídeo e sincronismo são preservados.")
    if plan.blocked:
        lines.append("APLICAÇÃO BLOQUEADA — resolva os itens marcados com [BLOQUEIO].")
    if plan.issues:
        lines.append("Alertas:")
        lines.extend(f"  {issue.render()}" for issue in plan.issues)
        lines.append("")
    lines.append("Trechos descartados:")
    cut_segments = [item for item in session.segments if item.state == SegmentState.CUT]
    for segment in cut_segments[:limit]:
        lines.append(
            f"  {segment.segment_id} [{position(segment.start_frame)}] "
            f"{session.speaker_name(segment.track_index)}: {segment.text}"
        )
    if len(cut_segments) > limit:
        lines.append(f"  … e mais {len(cut_segments) - limit}")
    if not cut_segments:
        lines.append("  nenhum trecho marcado como CUT")
    lines.append("")
    lines.append("Intervalos removidos:")
    for item in plan.removed_ranges[:limit]:
        reason = ", ".join(item.reasons)
        ids = f" ({', '.join(item.segment_ids)})" if item.segment_ids else ""
        lines.append(
            f"  {position(item.start_frame)} → {position(item.end_frame)} "
            f"[{clock(item.duration_frames)}] {reason}{ids}"
        )
    if len(plan.removed_ranges) > limit:
        lines.append(f"  … e mais {len(plan.removed_ranges) - limit}")
    lines.append("")
    lines.append("Trechos mantidos (amostra):")
    kept = [item for item in session.segments if item.state == SegmentState.KEEP]
    for segment in kept[: min(limit, 15)]:
        lines.append(
            f"  {segment.segment_id} [{position(segment.start_frame)} | TC "
            f"{frames_to_timecode(segment.start_frame, fps, drop_frame=plan.layout.drop_frame)}] "
            f"{session.speaker_name(segment.track_index)}: {segment.text}"
        )
    return "\n".join(lines)


def plans_directory() -> Path:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise RoughCutError("APPDATA não está disponível para salvar o plano de rough cut.")
    return Path(appdata) / "O Editor" / "plans"


def save_plan_for_resolve(
    plan: RoughCutPlan,
    *,
    apply: bool,
    directory: Path | None = None,
) -> Path:
    """Write a plan and a one-use, short-lived request for the single Resolve menu."""

    if plan.blocked:
        raise RoughCutError("O plano está bloqueado e não pode ser enviado ao Resolve.")
    target_directory = directory or plans_directory()
    target_directory.mkdir(parents=True, exist_ok=True)
    (target_directory / "applied").mkdir(exist_ok=True)
    payload = plan.to_dict(mode="APPLY" if apply else "VALIDATE", confirmed_by_user=apply)
    text = json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True)
    archive = target_directory / f"rough-cut-{plan.plan_id}.json"
    pending = target_directory / PENDING_PLAN_NAME
    _atomic_write(archive, text)
    _atomic_write(pending, text)
    request = {
        "schema_version": 1,
        "request_id": uuid.uuid4().hex,
        "action": "rough_cut",
        "plan_id": plan.plan_id,
        "mode": "APPLY" if apply else "VALIDATE",
        "created_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }
    _atomic_write(target_directory / "menu-action.json", json.dumps(request))
    return pending


def cancel_plan_for_resolve(*, plan_id: str, mode: str, directory: Path | None = None) -> bool:
    """Claim and archive only a matching request that Resolve has not consumed."""
    root = directory or plans_directory()
    request = root / "menu-action.json"
    cancelled = root / f"menu-action-{uuid.uuid4().hex}.cancelled.json"
    try:
        # Competes with the menu's one-use rename; a consumed request cannot be cancelled.
        request.rename(cancelled)
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise RoughCutError("Não foi possível cancelar a solicitação pendente.") from exc
    try:
        payload = json.loads(cancelled.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or (
            payload.get("schema_version") != 1
            or payload.get("action") != "rough_cut"
            or payload.get("plan_id") != plan_id
            or payload.get("mode") != mode
        ):
            raise ValueError("A solicitação pertence a outro plano.")
    except (OSError, UnicodeError, ValueError) as exc:
        try:
            # Windows rename refuses to overwrite a newer request at the original path.
            cancelled.rename(request)
        except OSError as restore_error:
            raise RoughCutError(
                "A solicitação diferente foi preservada no histórico; confira o Diagnóstico."
            ) from restore_error
        raise RoughCutError("O pedido atual não corresponde ao plano desta janela.") from exc
    return True


def _atomic_write(path: Path, content: str) -> None:
    temporary: Path | None = None
    try:
        descriptor, name = tempfile.mkstemp(prefix=".oe-", suffix=".tmp", dir=path.parent)
        temporary = Path(name)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise RoughCutError(f"Não foi possível gravar {path.name}.") from exc
