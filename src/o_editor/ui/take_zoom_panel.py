"""'Zoom' step: optional fixed zoom per take, applied in Resolve with undo.

Two ways to use it, both optional:
* together with the Rough Cut (the zoom goes inside the plan of step 03);
* afterwards, on a timeline created by O Editor that is open in Resolve.
"""

from __future__ import annotations

import json
import random
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

from PySide6.QtCore import QSettings, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLayout,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from o_editor.application.rough_cut import cancel_plan_for_resolve
from o_editor.application.take_zoom import (
    TakeZoomPreview,
    TimelineRegistry,
    ZoomHistory,
    build_apply_plan,
    build_undo_plan,
    is_o_editor_timeline,
    preview_take_zoom,
    record_take_zoom_outcome,
    save_request,
)
from o_editor.domain.enums import TrackType
from o_editor.domain.rough_cut import RoughCutPlan
from o_editor.domain.take_zoom import (
    FREQUENCY_MAX,
    OFFSET_LIMIT_PIXELS,
    ZOOM_MAX_PERCENT,
    ZOOM_MIN_PERCENT,
    TakeAssignment,
    TakeZoomSettings,
    ValueRange,
    assign_takes,
    summarize,
    takes_from_bounds,
)
from o_editor.domain.timecode import frames_to_clock
from o_editor.domain.timeline_layout import LayoutError, TimelineLayout
from o_editor.errors import OEditorError
from o_editor.infrastructure.config import AppConfig
from o_editor.infrastructure.resolve.native_bridge import NativeResolveBridge
from o_editor.internal_actions.presentation import render_internal_action
from o_editor.internal_actions.request import InternalActionRequest
from o_editor.ui.controllers.workers import ContextRefreshWorker, RoughCutDispatchWorker
from o_editor.ui.theme import label

SETTINGS_KEY = "take_zoom/settings"
WITH_CUT_KEY = "take_zoom/with_rough_cut"
PREVIEW_ROWS = 500


class RangeField(QWidget):
    """'Fixo' or 'Faixa' (from/to) integer value with the app's unit toggles."""

    changed = Signal()

    def __init__(
        self,
        *,
        minimum: int,
        maximum: int,
        suffix: str = "",
        before: str = "",
        after: str = "",
        name: str,
    ) -> None:
        super().__init__()
        self.setObjectName(name)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        self.fixed_button = QPushButton("Fixo")
        self.range_button = QPushButton("Faixa")
        self._group = QButtonGroup(self)
        for button in (self.fixed_button, self.range_button):
            button.setProperty("role", "unit")
            button.setCheckable(True)
            self._group.addButton(button)
            row.addWidget(button)
        row.addSpacing(6)
        if before:
            row.addWidget(label(before))
        self.minimum_spin = QSpinBox()
        self.maximum_spin = QSpinBox()
        for spin in (self.minimum_spin, self.maximum_spin):
            spin.setRange(minimum, maximum)
            spin.setSuffix(suffix)
            spin.setMinimumWidth(92)
            spin.setKeyboardTracking(False)
        self._between = label("a")
        row.addWidget(self.minimum_spin)
        row.addWidget(self._between)
        row.addWidget(self.maximum_spin)
        if after:
            row.addWidget(label(after))
        row.addStretch()
        self.fixed_button.setChecked(True)
        self._group.buttonClicked.connect(self._mode_clicked)
        self.minimum_spin.valueChanged.connect(self._values_changed)
        self.maximum_spin.valueChanged.connect(self._values_changed)
        self._sync_mode()

    @property
    def is_range(self) -> bool:
        return self.range_button.isChecked()

    def value_range(self) -> ValueRange:
        low = float(self.minimum_spin.value())
        if not self.is_range:
            return ValueRange.fixed(low)
        return ValueRange(low, float(self.maximum_spin.value())).ordered()

    def set_value_range(self, value: ValueRange) -> None:
        ordered = value.ordered()
        for spin, number in (
            (self.minimum_spin, ordered.minimum),
            (self.maximum_spin, ordered.maximum),
        ):
            spin.blockSignals(True)
            spin.setValue(round(number))
            spin.blockSignals(False)
        (self.fixed_button if ordered.is_fixed else self.range_button).setChecked(True)
        self._sync_mode()

    def _mode_clicked(self, *_args: Any) -> None:
        if self.is_range and self.maximum_spin.value() <= self.minimum_spin.value():
            self.maximum_spin.blockSignals(True)
            self.maximum_spin.setValue(self.minimum_spin.value() + 1)
            self.maximum_spin.blockSignals(False)
        self._sync_mode()
        self.changed.emit()

    def _values_changed(self, *_args: Any) -> None:
        self.changed.emit()

    def _sync_mode(self) -> None:
        self._between.setVisible(self.is_range)
        self.maximum_spin.setVisible(self.is_range)


class TakeZoomPanel(QWidget):
    settings_changed = Signal()
    activity_changed = Signal()

    def __init__(
        self,
        *,
        config: AppConfig,
        root: Path,
        use_mock: bool,
        plan_provider: Callable[[], RoughCutPlan | None],
        busy_provider: Callable[[], bool] = lambda: False,
        plans_directory: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("takeZoomPanel")
        self._config = config
        self._root = root
        self._use_mock = use_mock
        self._plan_provider = plan_provider
        self._busy_provider = busy_provider
        self._plans_directory = plans_directory
        self._preferences = QSettings(
            str(root / "runtime/ui-preferences.ini"), QSettings.Format.IniFormat
        )
        self._layout: TimelineLayout | None = None
        self._take_starts: list[int] | None = None
        self._preview: TakeZoomPreview | None = None
        self._pending_plan_id: str | None = None
        self._pending_purpose: str | None = None
        self._refresh_thread: QThread | None = None
        self._dispatch_thread: QThread | None = None
        self._dispatch_worker: RoughCutDispatchWorker | None = None
        self._refresh_worker: ContextRefreshWorker | None = None
        self._request_timer = QTimer(self)
        self._request_timer.setSingleShot(True)
        self._request_timer.setInterval(300_000)
        self._request_timer.timeout.connect(self._request_expired)
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(150)
        self._preview_timer.timeout.connect(self.refresh_preview)
        self._build_ui()
        self._load_settings()
        self.refresh_preview()

    # ------------------------------------------------------------------ layout
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 8, 18, 8)
        layout.setSpacing(8)
        header = QHBoxLayout()
        self.enabled_check = QCheckBox("Usar zoom por take")
        self.enabled_check.setObjectName("takeZoomEnabled")
        self.enabled_check.setToolTip("Etapa opcional: desmarcada, nenhum zoom é aplicado.")
        header.addWidget(self.enabled_check)
        header.addSpacing(12)
        self.status_label = label("", "muted")
        self.status_label.setWordWrap(True)
        header.addWidget(self.status_label, 1)
        layout.addLayout(header)

        self.controls = QGroupBox("Como aplicar")
        grid = QGridLayout(self.controls)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(6)
        grid.setColumnStretch(1, 1)
        self.scale_field = RangeField(
            minimum=int(ZOOM_MIN_PERCENT),
            maximum=int(ZOOM_MAX_PERCENT),
            suffix="%",
            name="zoomScale",
        )
        self.scale_field.setToolTip(
            "100% é o quadro normal do Resolve. Abaixo de 100% a imagem diminui."
        )
        self.every_field = RangeField(
            minimum=1, maximum=FREQUENCY_MAX, before="1 a cada", after="takes", name="zoomEvery"
        )
        self.every_field.setToolTip("Na faixa, o intervalo até o próximo zoom é sorteado.")
        base_row = QHBoxLayout()
        self.base_spin = QSpinBox()
        self.base_spin.setObjectName("zoomBase")
        self.base_spin.setRange(int(ZOOM_MIN_PERCENT), int(ZOOM_MAX_PERCENT))
        self.base_spin.setSuffix("%")
        self.base_spin.setMinimumWidth(92)
        self.keep_base_check = QCheckBox("Manter como estão")
        base_row.addWidget(self.base_spin)
        base_row.addWidget(self.keep_base_check)
        base_row.addStretch()
        point_row = QHBoxLayout()
        self.offset_x = QSpinBox()
        self.offset_y = QSpinBox()
        for caption, spin in (("X", self.offset_x), ("Y", self.offset_y)):
            spin.setRange(-int(OFFSET_LIMIT_PIXELS), int(OFFSET_LIMIT_PIXELS))
            spin.setSuffix(" px")
            spin.setMinimumWidth(100)
            point_row.addWidget(label(caption))
            point_row.addWidget(spin)
        self.center_button = QPushButton("Centro")
        point_row.addWidget(self.center_button)
        point_row.addStretch()
        tracks_row = QHBoxLayout()
        self._track_checks: dict[int, QCheckBox] = {}
        self._tracks_row = tracks_row
        self.tracks_hint = label("V1", "muted")
        tracks_row.addWidget(self.tracks_hint)
        tracks_row.addStretch()
        seed_row = QHBoxLayout()
        self.seed_label = label("", "muted")
        self.redraw_button = QPushButton("Sortear de novo")
        self.redraw_button.setObjectName("zoomRedraw")
        seed_row.addWidget(self.redraw_button)
        seed_row.addWidget(self.seed_label)
        seed_row.addStretch()
        cells: tuple[tuple[str, QWidget | QLayout], ...] = (
            ("Zoom", self.scale_field),
            ("Ponto do zoom", point_row),
            ("Frequência", self.every_field),
            ("Faixas de vídeo", tracks_row),
            ("Takes sem zoom", base_row),
            ("Sorteio", seed_row),
        )
        # Two columns keep the take list visible in the compact 1000x680 window.
        for position, (caption, content) in enumerate(cells):
            row, column = divmod(position, 2)
            grid.addWidget(label(caption), row, column * 2)
            if isinstance(content, QLayout):
                grid.addLayout(content, row, column * 2 + 1)
            else:
                grid.addWidget(content, row, column * 2 + 1)
        grid.setColumnStretch(3, 1)
        point_tip = (
            "Ponto do zoom: centro do quadro por padrão (X 0, Y 0). Mova em pixels se o "
            "vídeo estiver torto ou fora do centro (Anchor Point do Inspector)."
        )
        for widget in (self.offset_x, self.offset_y, self.center_button):
            widget.setToolTip(point_tip)
        layout.addWidget(self.controls)

        where = QHBoxLayout()
        where.addStretch()
        self.timeline_label = label("Nenhuma timeline do O Editor lida.", "muted")
        where.addWidget(self.timeline_label)
        self.read_button = QPushButton("Ler timeline aberta")
        self.read_button.setObjectName("zoomReadTimeline")
        self.read_button.setToolTip(
            "Lê a timeline aberta no Resolve (somente leitura) para aplicar o zoom "
            "depois dos cortes."
        )
        where.addWidget(self.read_button)
        layout.addLayout(where)

        self.table = QTableWidget(0, 4)
        self.table.setObjectName("zoomPreviewTable")
        self.table.setHorizontalHeaderLabels(("Take", "Início", "Duração", "Zoom"))
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)

        actions = QHBoxLayout()
        self.undo_button = QPushButton("Desfazer (Ctrl+Z)")
        self.undo_button.setObjectName("zoomUndo")
        self.cancel_button = QPushButton("Cancelar solicitação")
        self.cancel_button.setObjectName("zoomCancelRequest")
        self.apply_button = QPushButton("Aplicar zoom na timeline")
        self.apply_button.setObjectName("zoomApply")
        self.apply_button.setProperty("role", "danger")
        actions.addWidget(self.undo_button)
        actions.addWidget(self.cancel_button)
        actions.addStretch()
        actions.addWidget(self.apply_button)
        layout.addLayout(actions)
        self.result_label = label("", "muted")
        self.result_label.setObjectName("zoomResult")
        self.result_label.setWordWrap(True)
        self.result_label.hide()
        layout.addWidget(self.result_label)

        self.undo_shortcut = QShortcut(QKeySequence.StandardKey.Undo, self)
        self.undo_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.undo_shortcut.activated.connect(self.undo)

        self.enabled_check.toggled.connect(self._settings_edited)
        self.scale_field.changed.connect(self._settings_edited)
        self.every_field.changed.connect(self._settings_edited)
        self.base_spin.valueChanged.connect(self._settings_edited)
        self.keep_base_check.toggled.connect(self._settings_edited)
        self.offset_x.valueChanged.connect(self._settings_edited)
        self.offset_y.valueChanged.connect(self._settings_edited)
        self.center_button.clicked.connect(self._center)
        self.redraw_button.clicked.connect(self._redraw)
        self.read_button.clicked.connect(self.read_timeline)
        self.apply_button.clicked.connect(self.apply)
        self.undo_button.clicked.connect(self.undo)
        self.cancel_button.clicked.connect(self._cancel_request)

    def _set_result(self, text: str) -> None:
        self.result_label.setText(text)
        self.result_label.setVisible(bool(text))

    # ---------------------------------------------------------------- settings
    def _load_settings(self) -> None:
        raw = str(self._preferences.value(SETTINGS_KEY, "", type=str) or "")
        try:
            settings = TakeZoomSettings.from_dict(json.loads(raw)) if raw else TakeZoomSettings()
        except (TypeError, ValueError, KeyError):
            settings = TakeZoomSettings()
        if settings.problems():
            settings = TakeZoomSettings()
        self._seed = settings.seed
        self._selected_tracks = set(settings.video_tracks)
        widgets = (
            self.enabled_check,
            self.base_spin,
            self.keep_base_check,
            self.offset_x,
            self.offset_y,
        )
        for widget in widgets:
            widget.blockSignals(True)
        self.enabled_check.setChecked(settings.enabled)
        self.scale_field.set_value_range(settings.scale)
        self.every_field.set_value_range(settings.every)
        self.base_spin.setValue(round(settings.base_scale or 100))
        self.keep_base_check.setChecked(settings.base_scale is None)
        self.offset_x.setValue(round(settings.offset_x))
        self.offset_y.setValue(round(settings.offset_y))
        for widget in widgets:
            widget.blockSignals(False)
        self._rebuild_track_checks()
        self._sync_enabled()

    def settings(self) -> TakeZoomSettings:
        tracks = tuple(sorted(index for index in self._selected_tracks if index >= 1)) or (1,)
        return TakeZoomSettings(
            enabled=self.enabled_check.isChecked(),
            scale=self.scale_field.value_range(),
            every=self.every_field.value_range(),
            base_scale=None if self.keep_base_check.isChecked() else float(self.base_spin.value()),
            offset_x=float(self.offset_x.value()),
            offset_y=float(self.offset_y.value()),
            video_tracks=tracks,
            seed=self._seed,
        )

    def settings_for_rough_cut(self) -> TakeZoomSettings | None:
        """Read configured values for an explicit APLICAR decision in the modal."""
        settings = replace(self.settings(), enabled=True)
        settings.validated()
        return settings

    @property
    def request_pending(self) -> bool:
        return self._pending_plan_id is not None

    @property
    def operation_active(self) -> bool:
        return (
            self._pending_plan_id is not None
            or self._refresh_thread is not None
            or self._dispatch_thread is not None
        )

    @property
    def has_running_worker(self) -> bool:
        return self._refresh_thread is not None or self._dispatch_thread is not None

    def _save_settings(self) -> None:
        self._preferences.setValue(SETTINGS_KEY, json.dumps(self.settings().to_dict()))

    def _settings_edited(self, *_args: Any) -> None:
        self._save_settings()
        self._sync_enabled()
        self._preview_timer.start()
        self.settings_changed.emit()

    def _center(self) -> None:
        self.offset_x.setValue(0)
        self.offset_y.setValue(0)

    def _redraw(self) -> None:
        self._seed = random.SystemRandom().randint(1, 999_999)
        self._settings_edited()

    def _sync_enabled(self) -> None:
        enabled = self.enabled_check.isChecked()
        self.controls.setEnabled(enabled)
        self.base_spin.setEnabled(enabled and not self.keep_base_check.isChecked())
        self.seed_label.setText(f"Sorteio nº {self._seed}")

    # -------------------------------------------------------------- video tracks
    def _video_track_indices(self) -> list[int]:
        layout = self._layout
        if layout is None:
            plan = self._plan_provider()
            layout = plan.layout if plan is not None else None
        if layout is None:
            return sorted(self._selected_tracks or {1})
        indices = [track.index for track in layout.tracks_of(TrackType.VIDEO)]
        return indices or [1]

    def _rebuild_track_checks(self) -> None:
        for check in self._track_checks.values():
            self._tracks_row.removeWidget(check)
            check.hide()
            check.deleteLater()
        self._track_checks = {}
        indices = self._video_track_indices()
        if not self._selected_tracks.intersection(indices):
            self._selected_tracks = {indices[0]}
        for position, index in enumerate(indices):
            check = QCheckBox(f"V{index}")
            check.setChecked(index in self._selected_tracks)
            check.toggled.connect(lambda checked, value=index: self._track_toggled(value, checked))
            self._tracks_row.insertWidget(position, check)
            self._track_checks[index] = check
        self.tracks_hint.setText("")
        self.tracks_hint.setToolTip("Os takes seguem os cortes da faixa mais baixa marcada.")

    def _track_toggled(self, index: int, checked: bool) -> None:
        if checked:
            self._selected_tracks.add(index)
        elif len(self._selected_tracks) > 1:
            self._selected_tracks.discard(index)
        else:
            check = self._track_checks.get(index)
            if check is not None:
                check.blockSignals(True)
                check.setChecked(True)
                check.blockSignals(False)
            return
        self._settings_edited()

    # ------------------------------------------------------------------ preview
    def plan_changed(self) -> None:
        """Step 04 preview changed: refresh takes shown for the 'together' mode."""
        if self._layout is None:
            self._rebuild_track_checks()
        self._preview_timer.start()

    def refresh_preview(self) -> None:
        settings = self.settings()
        self._preview = None
        assignments: tuple[TakeAssignment, ...] = ()
        fps = 30.0
        start = 0
        problems = settings.problems()
        if not settings.enabled:
            message = "Etapa opcional desligada: nenhum zoom será aplicado."
        elif problems:
            message = " ".join(problems)
        elif self._layout is not None:
            try:
                self._preview = preview_take_zoom(
                    self._layout, settings, take_starts=self._take_starts
                )
            except OEditorError as exc:
                message = str(exc)
            else:
                assignments = self._preview.assignments
                fps, start = self._layout.fps, self._layout.start_frame
                origin = (
                    "cortes do O Editor"
                    if self._preview.cut_points_known
                    else f"clipes da faixa V{settings.reference_track}"
                )
                message = self._summary_text(assignments) + f" — takes pelos {origin}."
        else:
            plan = self._plan_provider()
            if plan is not None and plan.keep_ranges:
                takes = takes_from_bounds(
                    (keep.record_start, keep.record_start + keep.duration_frames)
                    for keep in plan.keep_ranges
                )
                assignments = assign_takes(takes, settings)
                fps, start = plan.layout.fps, plan.layout.start_frame
                message = (
                    self._summary_text(assignments)
                    + " — prévia da etapa 03; confirme APLICAR ou REVISAR ao executar os cortes."
                )
            else:
                message = (
                    "Gere a prévia dos cortes (etapa 03) para aplicar junto, ou abra no Resolve "
                    "uma timeline criada pelo O Editor e clique em 'Ler timeline aberta'."
                )
        self.status_label.setText(message)
        self._fill_table(assignments, fps, start)
        self._update_buttons()

    @staticmethod
    def _summary_text(assignments: tuple[TakeAssignment, ...]) -> str:
        summary = summarize(assignments)
        if not summary["zoomed"]:
            return f"{summary['takes']} takes, nenhum com zoom"
        if summary["minimum"] == summary["maximum"]:
            scale = f"{summary['minimum']:g}%"
        else:
            scale = f"{summary['minimum']:g} a {summary['maximum']:g}%"
        return f"{summary['takes']} takes, {summary['zoomed']} com zoom ({scale})"

    def _fill_table(self, assignments: tuple[TakeAssignment, ...], fps: float, start: int) -> None:
        settings = self.settings()
        visible = assignments[:PREVIEW_ROWS]
        self.table.setRowCount(len(visible))
        for row, assignment in enumerate(visible):
            take = assignment.take
            if assignment.scale is not None:
                zoom = f"{assignment.scale:g}%"
            elif settings.base_scale is None:
                zoom = "sem alteração"
            else:
                zoom = f"{settings.base_scale:g}% (sem zoom)"
            values = (
                str(take.index),
                frames_to_clock(take.start_frame - start, fps),
                frames_to_clock(take.duration_frames, fps),
                zoom,
            )
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                if column != 2 and assignment.zoomed:
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                self.table.setItem(row, column, item)

    # ---------------------------------------------------------------- timeline
    def read_timeline(self) -> None:
        if self.operation_active or self._use_mock:
            if self._use_mock:
                self._set_result("Modo demonstração: não há timeline real para ler.")
            return
        self._refresh_thread = QThread(self)
        self._refresh_worker = ContextRefreshWorker(
            NativeResolveBridge(root=self._root, config=self._config.resolve, timeout_seconds=15)
        )
        self._refresh_worker.moveToThread(self._refresh_thread)
        self._refresh_thread.started.connect(self._refresh_worker.run)
        self._refresh_worker.finished.connect(self.load_context)
        self._refresh_worker.failed.connect(self._read_failed)
        self._refresh_worker.finished.connect(self._refresh_thread.quit)
        self._refresh_worker.failed.connect(self._refresh_thread.quit)
        self._refresh_thread.finished.connect(self._refresh_worker.deleteLater)
        self._refresh_thread.finished.connect(self._read_finished)
        self.read_button.setText("Lendo…")
        self._update_buttons()
        self._refresh_thread.start()

    def load_context(self, context: dict[str, Any]) -> None:
        """Use a freshly captured context (only O Editor timelines can be changed)."""
        try:
            layout = TimelineLayout.from_internal_context(context)
        except (LayoutError, ValueError, KeyError, TypeError) as exc:
            self._set_result(f"Não foi possível ler os clipes da timeline: {exc}")
            return
        if not is_o_editor_timeline(layout.timeline_name):
            self._layout = None
            self._take_starts = None
            self.timeline_label.setText(f"Aberta: {layout.timeline_name}")
            self._set_result(
                "A timeline aberta não foi criada pelo O Editor e não será alterada. "
                "Abra uma timeline '_OE_ROUGHCUT_' no Resolve e leia novamente."
            )
        else:
            self._layout = layout
            entry = self._registry().get(layout.timeline_id)
            starts = entry.get("take_starts") if entry else None
            self._take_starts = [int(value) for value in starts] if starts else None
            self.timeline_label.setText(f"Timeline: {layout.timeline_name}")
            self._set_result("")
        self._rebuild_track_checks()
        self.refresh_preview()

    def _read_failed(self, message: str) -> None:
        self._set_result(f"Não foi possível ler a timeline do Resolve. {message}")

    def _read_finished(self) -> None:
        thread = self._refresh_thread
        self._refresh_thread, self._refresh_worker = None, None
        if thread is not None:
            thread.deleteLater()
        self.read_button.setText("Ler timeline aberta")
        self._update_buttons()

    def _registry(self) -> TimelineRegistry:
        return TimelineRegistry(self._plans_directory)

    def _history(self) -> ZoomHistory:
        return ZoomHistory(self._plans_directory)

    # ------------------------------------------------------------------ actions
    def busy_changed(self) -> None:
        """Another step started or finished a Resolve request."""
        self._update_buttons()

    def _update_buttons(self) -> None:
        idle = not self.operation_active and not self._busy_provider()
        layout = self._layout
        depth = self._history().depth(layout.timeline_id) if layout is not None else 0
        from o_editor.infrastructure.resolve.lua_mailbox import integration_mode

        free_write_blocked = not self._use_mock and integration_mode() == "Free"
        self.apply_button.setEnabled(idle and self._preview is not None and not free_write_blocked)
        self.undo_button.setEnabled(not free_write_blocked and idle and depth > 0)
        self.undo_button.setText(f"Desfazer (Ctrl+Z) · {depth}" if depth else "Desfazer (Ctrl+Z)")
        self.read_button.setEnabled(idle and not self._use_mock)
        self.cancel_button.setVisible(self._pending_plan_id is not None)
        if self._busy_provider() and self._pending_plan_id is None:
            self.apply_button.setToolTip("Aguarde o pedido do Rough Cut terminar no Resolve.")
        else:
            self.apply_button.setToolTip(
                "Zoom no Resolve Free: escrita NÃO VALIDADA; prévia disponível."
                if free_write_blocked
                else "Somente Zoom e Anchor Point mudam; dá para desfazer."
            )
        self.activity_changed.emit()

    def apply(self) -> None:
        from o_editor.infrastructure.resolve.lua_mailbox import integration_mode

        if not self._use_mock and integration_mode() == "Free":
            self._set_result("Zoom no Free: escrita NÃO VALIDADA; prévia disponível.")
            return
        preview = self._preview
        if preview is None or self.operation_active or self._busy_provider():
            return
        summary = self._summary_text(preview.assignments)
        answer = QMessageBox.question(
            self,
            "Aplicar zoom",
            f"Aplicar o zoom em '{preview.layout.timeline_name}'?\n\n{summary}; "
            f"{len(preview.targets)} clipes de vídeo.\nSomente Zoom e Anchor Point mudam; "
            "a timeline original não é tocada. Você poderá desfazer.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._send(build_apply_plan(preview))

    def undo(self) -> None:
        from o_editor.infrastructure.resolve.lua_mailbox import integration_mode

        if not self._use_mock and integration_mode() == "Free":
            self._set_result("Zoom no Free: escrita NÃO VALIDADA; prévia disponível.")
            return
        layout = self._layout
        if layout is None or self.operation_active or self._busy_provider():
            return
        entry = self._history().last(layout.timeline_id)
        if entry is None:
            self._set_result("Nada para desfazer nesta timeline.")
            return
        try:
            plan = build_undo_plan(entry, project_name=layout.project_name)
        except (OEditorError, KeyError, TypeError, ValueError) as exc:
            self._set_result(f"Não foi possível preparar o desfazer: {exc}")
            return
        self._send(plan)

    def _send(self, plan: dict[str, Any]) -> None:
        from o_editor.infrastructure.resolve.lua_mailbox import integration_mode

        if not self._use_mock and integration_mode() == "Free":
            self._set_result("Zoom no Free: escrita NÃO VALIDADA; prévia disponível.")
            return
        if self._use_mock:
            self._set_result("Modo demonstração: o pedido foi montado, mas não há Resolve real.")
            return
        try:
            save_request(plan, directory=self._plans_directory)
        except OEditorError as exc:
            self._set_result(str(exc))
            return
        self._pending_plan_id = str(plan["plan_id"])
        self._pending_purpose = str(plan["purpose"])
        self._request_timer.start()
        action = "Desfazendo" if self._pending_purpose == "undo" else "Aplicando"
        self._set_result(f"{action} no Resolve… aguarde a conferência.")
        self._update_buttons()
        self._start_dispatch()

    def _start_dispatch(self) -> None:
        if self._pending_plan_id is None:
            return
        if not (self._root / "launcher/internal_common.lua").is_file():
            self._set_result(
                "Execute Área de Trabalho > Scripts > O EDITOR no Resolve em até 5 minutos."
            )
            return
        thread = QThread(self)
        worker = RoughCutDispatchWorker(
            NativeResolveBridge(root=self._root, config=self._config.resolve, timeout_seconds=15),
            self._pending_plan_id,
            "APPLY",
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.failed.connect(self._dispatch_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(self._dispatch_finished)
        self._dispatch_thread, self._dispatch_worker = thread, worker
        self._update_buttons()
        thread.start()

    def _dispatch_failed(self, message: str) -> None:
        if self._pending_plan_id is not None:
            self._set_result("Não foi possível confirmar o acionamento automático. " + message)

    def _dispatch_finished(self) -> None:
        thread = self._dispatch_thread
        self._dispatch_thread, self._dispatch_worker = None, None
        if thread is not None:
            thread.deleteLater()
        self._update_buttons()

    def _cancel_request(self) -> None:
        if self._pending_plan_id is None:
            return
        try:
            cancelled = cancel_plan_for_resolve(
                plan_id=self._pending_plan_id,
                mode="APPLY",
                directory=self._plans_directory,
                action="take_zoom",
            )
        except OEditorError as exc:
            self._set_result(str(exc))
            return
        if not cancelled:
            self._set_result("O Resolve já recebeu o pedido. Aguarde o resultado.")
            return
        self._request_timer.stop()
        self._pending_plan_id = self._pending_purpose = None
        self._set_result("Pedido de zoom cancelado. Nada foi alterado.")
        self._update_buttons()

    def _request_expired(self) -> None:
        self._pending_plan_id = self._pending_purpose = None
        self._set_result("O Resolve não confirmou o pedido de zoom em 5 minutos. Tente novamente.")
        self._update_buttons()

    def display_result(self, request: InternalActionRequest) -> bool:
        """Record the Resolve reply in the undo history and show it."""
        details = request.details
        outcome = record_take_zoom_outcome(request.status, details, directory=self._plans_directory)
        if self._pending_plan_id is None or details.get("plan_id") == self._pending_plan_id:
            self._request_timer.stop()
            self._pending_plan_id = self._pending_purpose = None
        prefix = {"applied": "Zoom aplicado.", "undone": "Zoom desfeito."}.get(outcome, "")
        self._set_result(f"{prefix} {request.status}: {request.message}".strip())
        self.result_label.setToolTip(render_internal_action(request))
        self._update_buttons()
        return True
