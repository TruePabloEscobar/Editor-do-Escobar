"""Main PySide6 review interface."""

from __future__ import annotations

import json
import shutil
import sys
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    QModelIndex,
    QPersistentModelIndex,
    QSize,
    QSortFilterProxyModel,
    QThread,
)
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QTableView,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from o_editor.application.analyze_timeline import AnalysisResult, AnalyzeTimeline
from o_editor.application.apply_plan import ApplyPlan
from o_editor.application.approved_plan import save_approved_plan
from o_editor.application.build_plan import build_application_plan
from o_editor.application.generate_report import (
    render_application_report,
    save_application_plan,
)
from o_editor.bootstrap import bootstrap, project_root
from o_editor.domain.enums import ChannelMode
from o_editor.domain.models import ApplicationReport, CapabilityResult, Suggestion
from o_editor.domain.voice_tracks import (
    AudioTrackSnapshot,
    SelectedVoiceTrack,
    suggest_voice_tracks,
    validate_voice_selection,
)
from o_editor.errors import OEditorError
from o_editor.infrastructure.analysis.heuristic import HeuristicAnalyzer
from o_editor.infrastructure.cache import JsonCache, default_app_cache_root
from o_editor.infrastructure.config import AppConfig
from o_editor.infrastructure.ffmpeg.runner import FFmpegRunner
from o_editor.infrastructure.resolve.adapter import ResolveAdapter
from o_editor.infrastructure.resolve.audio_exporter import (
    AudioExporter,
    InternalVoiceAudioExporter,
    ManualAudioExporter,
    ResolveAudioExporter,
)
from o_editor.infrastructure.resolve.internal_adapter import InternalContextAdapter
from o_editor.infrastructure.resolve.launch_context import (
    consume_launch_context,
    reconcile_launch_context,
)
from o_editor.infrastructure.resolve.mock_adapter import MockResolveAdapter
from o_editor.infrastructure.resolve.native_bridge import NativeResolveBridge
from o_editor.infrastructure.resolve.real_adapter import RealResolveAdapter
from o_editor.infrastructure.status import ComponentState, OperationalStatus
from o_editor.infrastructure.transcription.base import (
    CancellationToken,
    TranscriptionProvider,
)
from o_editor.infrastructure.transcription.faster_whisper import FasterWhisperProvider
from o_editor.infrastructure.transcription.mock import MockTranscriptionProvider
from o_editor.infrastructure.voice_track_settings import VoiceTrackSettingsStore
from o_editor.ui.capability_dialog import CapabilityDialog
from o_editor.ui.controllers.workers import AnalysisWorker, ApplyWorker, ContextRefreshWorker
from o_editor.ui.models.suggestion_model import SuggestionTableModel
from o_editor.ui.settings_window import SettingsDialog
from o_editor.ui.theme import STYLESHEET, BrandHeader
from o_editor.ui.theme import label as ui_label
from o_editor.ui.transcript_panel import TranscriptPanel
from o_editor.ui.voice_track_selector import VoiceTrackSelector


class SuggestionFilterModel(QSortFilterProxyModel):
    def filterAcceptsRow(
        self,
        source_row: int,
        source_parent: QModelIndex | QPersistentModelIndex,
    ) -> bool:
        selected = self.filterRegularExpression().pattern()
        if not selected or selected == "todos":
            return True
        index = self.sourceModel().index(source_row, 2, source_parent)
        value = str(self.sourceModel().data(index)).casefold()
        return value.startswith(selected)


class MainWindow(QMainWindow):
    def __init__(
        self,
        *,
        config: AppConfig,
        root: Path,
        use_mock: bool,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__()
        self._config = config
        self._root = root
        self._use_mock = use_mock
        self._context = context or {}
        if use_mock and not self._context:
            snapshot = MockResolveAdapter().original_snapshot
            self._context = {
                "project_name": snapshot.project_name,
                "timeline_name": snapshot.timeline_name,
                "timeline_id": snapshot.timeline_id,
                "fps": snapshot.fps,
                "start_frame": snapshot.start_frame,
                "end_frame": snapshot.end_frame,
                "duration_frames": snapshot.duration_frames,
                "track_counts": {
                    "video": snapshot.video_track_count,
                    "audio": snapshot.audio_track_count,
                    "subtitle": 0,
                },
                "audio_track_count": snapshot.audio_track_count,
                "audio_tracks": [track.to_dict() for track in snapshot.audio_tracks],
            }
        self._internal_host = self._context.get("integration_mode") == "internal_resolve_host"
        self._external_bridge_enabled = config.resolve.external_bridge_enabled
        self._adapter: ResolveAdapter | None = None
        self._analysis_result: AnalysisResult | None = None
        self._manual_audio: Path | None = None
        settings_root = root / "runtime" / "mock-projects" if use_mock else None
        self._voice_settings = VoiceTrackSettingsStore(settings_root)
        self._voice_context_identity: tuple[str, str] | None = None
        self._refresh_thread: QThread | None = None
        self._refresh_worker: ContextRefreshWorker | None = None
        self._settings_dialog: SettingsDialog | None = None
        self._suggestion_kind = "zoom"
        self._busy = False
        self._thread: QThread | None = None
        self._worker: AnalysisWorker | ApplyWorker | None = None
        self._cancellation: CancellationToken | None = None
        self._capabilities = _load_capabilities(root / "runtime" / "resolve_capabilities.json")
        self._model = SuggestionTableModel()
        self._model.dataChanged.connect(self._approved_suggestions_changed)
        self._proxy = SuggestionFilterModel(self)
        self._proxy.setSourceModel(self._model)
        self.setWindowTitle("Editor Do Escobar — EDE")
        self.setStyleSheet(STYLESHEET)
        self.setMinimumSize(1000, 680)
        self.resize(1280, 820)
        self._build_ui()
        self._show_initial_status()

    def _build_ui(self) -> None:
        central = QWidget()
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        self.setCentralWidget(central)
        root_layout.addWidget(BrandHeader())

        context_bar = QHBoxLayout()
        context_bar.setContentsMargins(20, 10, 20, 10)
        context_bar.setSpacing(16)
        self._project_label = QLabel("—")
        self._timeline_label = QLabel("—")
        self._timeline_label.setWordWrap(True)
        self._timeline_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._duration_label = QLabel("—")
        self._fps_label = QLabel("—")
        self._mode_label = ui_label(
            "DEMONSTRAÇÃO" if self._use_mock else "AGUARDANDO TIMELINE", "badge"
        )
        for caption, widget in (
            ("PROJETO", self._project_label),
            ("TIMELINE", self._timeline_label),
            ("DURAÇÃO", self._duration_label),
            ("FPS", self._fps_label),
        ):
            column = QVBoxLayout()
            column.setSpacing(3)
            column.addWidget(ui_label(caption, "eyebrow"))
            column.addWidget(widget)
            context_bar.addLayout(column, 1)
        self._refresh_timeline_button = QPushButton("Atualizar timeline")
        self._refresh_timeline_button.setObjectName("refreshTimeline")
        self._refresh_timeline_button.setToolTip(
            "Ler a timeline atual e seus clipes no DaVinci Resolve."
        )
        self._refresh_timeline_button.clicked.connect(self._refresh_timeline)
        context_bar.addWidget(self._refresh_timeline_button)
        context_bar.addWidget(self._mode_label)
        root_layout.addLayout(context_bar)

        navigation_bar = QWidget()
        navigation_bar.setObjectName("workflowBar")
        navigation = QHBoxLayout(navigation_bar)
        navigation.setContentsMargins(16, 6, 16, 6)
        navigation.setSpacing(6)
        self._workflow_buttons: list[QPushButton] = []
        for index, title in enumerate(
            (
                "01  Faixas de voz",
                "02  Transcrição",
                "03  Revisão",
                "04  Prévia e cortes",
                "Zoom",
                "Legendas",
            )
        ):
            button = QPushButton(title)
            if index >= 4:
                button.setMinimumWidth(84)
            button.setProperty("role", "nav")
            button.setCheckable(True)
            button.clicked.connect(lambda _checked=False, step=index: self._navigate(step))
            navigation.addWidget(button, 1 if index < 4 else 0)
            self._workflow_buttons.append(button)
        self._settings_button = QPushButton()
        self._settings_button.setObjectName("settingsButton")
        self._settings_button.setAccessibleName("Configurações")
        self._settings_button.setToolTip("Configurações: transcrição, GPU e diagnóstico")
        self._settings_button.setIcon(QIcon(str(Path(__file__).parent / "assets" / "gear.svg")))
        self._settings_button.setIconSize(QSize(22, 22))
        self._settings_button.setFixedSize(42, 40)
        navigation.addWidget(self._settings_button)
        root_layout.addWidget(navigation_bar)
        self._workspace = QStackedWidget()
        root_layout.addWidget(self._workspace, 1)

        source_page = QWidget()
        source_layout = QVBoxLayout(source_page)
        source_layout.setContentsMargins(18, 12, 18, 12)
        source_layout.addWidget(ui_label("Faixas de voz", "heading"))
        source_layout.addWidget(ui_label("Selecione as faixas para transcrever."))
        self._voice_selector = VoiceTrackSelector()
        source_layout.addWidget(self._voice_selector, 1)
        self._source_notice = ui_label(
            "Ao trocar os clipes no Resolve, clique em Atualizar timeline.", "notice"
        )
        source_layout.addWidget(self._source_notice)
        source_actions = QHBoxLayout()
        self._manual_audio_button = QPushButton("Selecionar WAV para análise")
        source_actions.addWidget(self._manual_audio_button)
        source_actions.addStretch()
        self._source_next_button = QPushButton("Continuar para transcrição  →")
        self._source_next_button.setProperty("role", "primary")
        self._source_next_button.clicked.connect(lambda: self._navigate(1))
        source_actions.addWidget(self._source_next_button)
        source_layout.addLayout(source_actions)
        self._workspace.addWidget(source_page)

        self._transcript_panel = TranscriptPanel(
            config=self._config,
            root=self._root,
            use_mock=self._use_mock,
            context_provider=lambda: self._context,
            selected_tracks_provider=lambda: self._voice_selector.selected_tracks(),
        )
        self._transcript_panel.stage_requested.connect(self._navigate)
        self._transcript_panel.activity_changed.connect(self._update_refresh_availability)
        suggestions_page = QWidget()
        suggestions_layout = QVBoxLayout(suggestions_page)
        suggestions_layout.setContentsMargins(26, 20, 26, 16)
        self._suggestions_title = ui_label("Zoom", "heading")
        suggestions_layout.addWidget(self._suggestions_title)
        controls = QGroupBox("Como analisar")
        controls_layout = QFormLayout(controls)
        self._suggestions_controls = controls_layout
        self._zoom_intensity = QComboBox()
        _add_localized_items(
            self._zoom_intensity,
            (
                ("Muito suave", "very_soft"),
                ("Suave", "soft"),
                ("Média", "medium"),
                ("Forte", "strong"),
            ),
            self._config.zoom.intensity,
        )
        self._zoom_frequency = QComboBox()
        _add_localized_items(
            self._zoom_frequency,
            (("Baixa", "low"), ("Média", "medium"), ("Alta", "high")),
            self._config.zoom.frequency,
        )
        self._text_frequency = QComboBox()
        _add_localized_items(
            self._text_frequency,
            (("Baixa", "low"), ("Média", "medium"), ("Alta", "high")),
            self._config.text.frequency,
        )
        controls_layout.addRow("Intensidade do zoom", self._zoom_intensity)
        controls_layout.addRow("Frequência de zoom", self._zoom_frequency)
        controls_layout.addRow("Frequência de legendas/textos", self._text_frequency)
        self._analyze_button = QPushButton("Analisar timeline")
        self._analyze_button.setProperty("role", "primary")
        controls_layout.addRow(self._analyze_button)
        suggestions_layout.addWidget(controls)
        review_actions = QHBoxLayout()
        self._filter = QComboBox()
        _add_localized_items(
            self._filter, (("Todos", "todos"), ("Zoom", "zoom"), ("Texto", "text")), "todos"
        )
        approve_button = QPushButton("Aprovar todos")
        self._approve_suggestions_button = approve_button
        reject_button = QPushButton("Rejeitar todos")
        self._reject_suggestions_button = reject_button
        goto_button = QPushButton("Ir ao ponto no Resolve")
        for review_widget in (self._filter, approve_button, reject_button, goto_button):
            review_actions.addWidget(review_widget)
        review_actions.addStretch()
        self._filter.hide()
        suggestions_layout.addLayout(review_actions)
        self._table = QTableView()
        self._table.setModel(self._proxy)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(True)
        self._table.horizontalHeader().setStretchLastSection(True)
        suggestions_layout.addWidget(self._table, 1)
        export_button = QPushButton("Exportar plano JSON")
        self._dry_run = QCheckBox("Simular aplicação (dry-run)")
        self._dry_run.setChecked(self._config.safety.dry_run_default)
        self._apply_button = QPushButton("Aplicar aprovados")
        self._apply_button.setEnabled(False)
        suggestion_footer = QHBoxLayout()
        for footer_widget in (export_button, self._dry_run, self._apply_button):
            suggestion_footer.addWidget(footer_widget)
        suggestions_layout.addLayout(suggestion_footer)
        self._tabs = QTabWidget()
        self._tabs.tabBar().hide()
        self._tabs.addTab(self._transcript_panel, "Transcrição e Rough Cut")
        self._tabs.addTab(suggestions_page, "Sugestões de zoom e texto")
        self._workspace.addWidget(self._tabs)

        diagnostics = QWidget(self)
        self._diagnostics_page = diagnostics
        diagnostics_layout = QVBoxLayout(diagnostics)
        self._diagnostics_layout = diagnostics_layout
        diagnostics_layout.setContentsMargins(26, 20, 26, 16)
        diagnostics_layout.addWidget(ui_label("FERRAMENTAS / DIAGNÓSTICO", "eyebrow"))
        diagnostics_layout.addWidget(ui_label("Estado do ambiente", "heading"))
        status_group = QGroupBox("Conexão e recursos")
        status_layout = QFormLayout(status_group)
        self._app_status_label = QLabel("PASSED")
        self._internal_host_label = QLabel("READY" if self._internal_host else "UNVERIFIED")
        self._external_bridge_label = QLabel(
            "UNVERIFIED" if self._external_bridge_enabled else "DISABLED"
        )
        self._ffmpeg_label = QLabel("Verificando…")
        self._whisper_label = QLabel("Não configurado")
        self._overall_status_label = QLabel("READY_OFFLINE")
        for caption, widget in (
            ("Aplicativo", self._app_status_label),
            ("Host interno", self._internal_host_label),
            ("Ponte externa", self._external_bridge_label),
            ("FFmpeg", self._ffmpeg_label),
            ("Whisper", self._whisper_label),
            ("Estado geral", self._overall_status_label),
        ):
            status_layout.addRow(caption, widget)
        diagnostics_layout.addWidget(status_group)
        diagnostic_button = QPushButton("Detalhes das capacidades")
        diagnostics_layout.addWidget(diagnostic_button)
        self._report = QTextEdit()
        self._report.setReadOnly(True)
        self._report.setPlaceholderText("Relatórios e avisos do aplicativo aparecem aqui.")
        diagnostics_layout.addWidget(self._report, 1)
        diagnostics.hide()

        self._analysis_footer = QWidget()
        footer = QHBoxLayout(self._analysis_footer)
        footer.setContentsMargins(16, 8, 16, 8)
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._cancel_button = QPushButton("Cancelar análise")
        self._cancel_button.setEnabled(False)
        footer.addWidget(self._progress, 1)
        footer.addWidget(self._cancel_button)
        root_layout.addWidget(self._analysis_footer)
        self._analysis_footer.hide()
        self._voice_selector.selection_changed.connect(self._voice_selection_changed)
        self._analyze_button.clicked.connect(self._start_analysis)
        self._manual_audio_button.clicked.connect(self._select_wav)
        diagnostic_button.clicked.connect(
            lambda: CapabilityDialog(self._root, self._diagnostics_page.window()).exec()
        )
        self._settings_button.clicked.connect(self._open_settings)
        self._cancel_button.clicked.connect(self._cancel)
        self._filter.currentIndexChanged.connect(self._set_filter)
        approve_button.clicked.connect(
            lambda: self._model.set_all_approved(True, kind=self._suggestion_kind)
        )
        reject_button.clicked.connect(
            lambda: self._model.set_all_approved(False, kind=self._suggestion_kind)
        )
        goto_button.clicked.connect(self._go_to_selected)
        export_button.clicked.connect(self._export_plan)
        self._apply_button.clicked.connect(self._start_apply)
        self._navigate(0)

    def _open_settings(self, *, show_diagnostics: bool = False) -> None:
        self._update_refresh_availability()
        if not show_diagnostics and not self._settings_button.isEnabled():
            return
        if self._settings_dialog is None:
            self._settings_dialog = SettingsDialog(
                self._config, self, diagnostics=self._diagnostics_page
            )
            self._settings_dialog.accepted.connect(self._settings_saved)
        dialog = self._settings_dialog
        if not dialog.isVisible():
            dialog.reset_config(self._config)
            dialog.refresh_devices()
        dialog.set_editable(self._settings_button.isEnabled())
        dialog.tabs.setCurrentWidget(
            self._diagnostics_page if show_diagnostics else dialog.config_page
        )
        # Nonblocking: IPC reports must receive an ACK without waiting for a dialog to close.
        dialog.open()

    def _show_diagnostics(self) -> None:
        self._open_settings(show_diagnostics=True)

    def _settings_saved(self) -> None:
        dialog = self._settings_dialog
        if dialog is not None and dialog.selected_config is not None:
            self._config = dialog.selected_config
            self._transcript_panel.set_config(self._config)
            self._whisper_label.setText(ComponentState.READY.value)
            self._whisper_label.setToolTip(self._config.transcription.model_path or "")
            self._overall_status_label.setText(
                OperationalStatus(
                    internal_context=ComponentState.READY
                    if self._internal_host
                    else ComponentState.UNVERIFIED,
                    external_fusionscript_bridge=ComponentState.UNVERIFIED
                    if self._external_bridge_enabled
                    else ComponentState.DISABLED,
                    ffmpeg=ComponentState(self._ffmpeg_label.text()),
                    whisper=ComponentState.READY,
                ).overall.value
            )
            self.statusBar().showMessage("Modelo e dispositivo salvos para a próxima transcrição.")

    def _navigate(self, step: int) -> None:
        """Change presentation only; sessions, plans and safety checks stay intact."""
        if not 0 <= step < len(self._workflow_buttons):
            return
        for index, button in enumerate(self._workflow_buttons):
            button.setChecked(index == step)
        if step == 0:
            self._workspace.setCurrentIndex(0)
        else:
            self._workspace.setCurrentIndex(1)
            self._tabs.setCurrentIndex(1 if step >= 4 else 0)
            if step < 4:
                self._transcript_panel.set_stage(step - 1)
            else:
                self._set_suggestion_mode("zoom" if step == 4 else "text")

    def _set_suggestion_mode(self, kind: str) -> None:
        self._suggestion_kind = kind
        zoom = kind == "zoom"
        self._suggestions_title.setText("Zoom" if zoom else "Legendas / textos")
        self._suggestions_controls.setRowVisible(self._zoom_intensity, zoom)
        self._suggestions_controls.setRowVisible(self._zoom_frequency, zoom)
        self._suggestions_controls.setRowVisible(self._text_frequency, not zoom)
        self._filter.setCurrentIndex(self._filter.findData(kind))
        self._analyze_button.setText("Analisar zoom" if zoom else "Analisar textos")
        self._apply_button.setText(
            "Aplicar zooms aprovados" if zoom else "Aplicar textos aprovados"
        )
        self._apply_button.setToolTip("Aplica apenas as sugestões aprovadas desta seção.")

    def _current_suggestions(self) -> tuple[Suggestion, ...]:
        return tuple(s for s in self._model.suggestions if s.kind.value == self._suggestion_kind)

    def _show_initial_status(self) -> None:
        self._mode_label.setText(
            "DEMONSTRAÇÃO"
            if self._use_mock
            else "TIMELINE CARREGADA"
            if self._internal_host
            else "AGUARDANDO TIMELINE"
        )
        self._project_label.setText(str(self._context.get("project_name", "—")))
        self._timeline_label.setText(str(self._context.get("timeline_name", "—")))
        self._timeline_label.setToolTip(self._timeline_label.text())
        if self._context.get("duration_frames") is not None and self._context.get("fps"):
            duration = float(self._context["duration_frames"]) / float(self._context["fps"])
            self._duration_label.setText(f"{duration:.1f} segundos")
        if self._context.get("fps"):
            self._fps_label.setText(str(self._context["fps"]))
        ffmpeg = FFmpegRunner(
            ffmpeg_path=(
                Path(self._config.ffmpeg.ffmpeg_path) if self._config.ffmpeg.ffmpeg_path else None
            ),
            ffprobe_path=(
                Path(self._config.ffmpeg.ffprobe_path) if self._config.ffmpeg.ffprobe_path else None
            ),
        ).version()
        ffmpeg_state = ComponentState.READY if ffmpeg else ComponentState.PENDING
        self._ffmpeg_label.setText(ffmpeg_state.value)
        whisper_ready = self._use_mock or bool(
            self._config.transcription.model_path
            and Path(self._config.transcription.model_path).exists()
        )
        whisper_state = ComponentState.READY if whisper_ready else ComponentState.PENDING
        self._whisper_label.setText(whisper_state.value)
        if not self._use_mock and self._config.transcription.model_path:
            self._whisper_label.setToolTip(self._config.transcription.model_path)
        internal_state = ComponentState.READY if self._internal_host else ComponentState.UNVERIFIED
        bridge_state = (
            ComponentState.UNVERIFIED if self._external_bridge_enabled else ComponentState.DISABLED
        )
        status = OperationalStatus(
            internal_context=internal_state,
            external_fusionscript_bridge=bridge_state,
            ffmpeg=ffmpeg_state,
            whisper=whisper_state,
        )
        self._overall_status_label.setText(status.overall.value)
        self._analyze_button.setEnabled(
            self._use_mock or self._internal_host or self._external_bridge_enabled
        )
        mode_message = (
            "Integração: Host interno do DaVinci Resolve"
            if self._internal_host
            else "Modo offline. Abra O Editor pelo menu Scripts do DaVinci "
            "ou use o mock para uma demonstração completa."
        )
        context_message = str(self._context.get("connection_status") or "")
        self._report.setPlainText(
            mode_message + (f"\n{context_message}" if context_message else "")
        )
        self._refresh_voice_tracks()

    def _apply_context(self, context: dict[str, Any]) -> None:
        self._context = context
        self._internal_host = context.get("integration_mode") == "internal_resolve_host"
        self._project_label.setText(str(context.get("project_name") or "—"))
        self._timeline_label.setText(str(context.get("timeline_name") or "—"))
        self._timeline_label.setToolTip(self._timeline_label.text())
        fps = context.get("fps")
        duration_frames = context.get("duration_frames")
        if fps:
            self._fps_label.setText(str(fps))
        if fps and duration_frames is not None:
            self._duration_label.setText(f"{float(duration_frames) / float(fps):.1f} segundos")
        self._internal_host_label.setText("READY" if self._internal_host else "UNVERIFIED")
        if self._internal_host:
            self._overall_status_label.setText("READY_INTERNAL")
            self._mode_label.setText("TIMELINE CARREGADA")
        self._refresh_voice_tracks()

    def _update_refresh_availability(self) -> None:
        blocked = (
            self._busy
            or self._refresh_thread is not None
            or self._transcript_panel.operation_active
        )
        self._refresh_timeline_button.setEnabled(not blocked and not self._use_mock)
        self._settings_button.setEnabled(not blocked)
        if self._settings_dialog is not None:
            self._settings_dialog.set_editable(not blocked)

    def _refresh_timeline(self) -> None:
        if (
            self._busy
            or self._refresh_thread is not None
            or self._transcript_panel.operation_active
        ):
            return
        self._transcript_panel._save_session_edits()
        self._refresh_thread = QThread(self)
        self._refresh_worker = ContextRefreshWorker(
            NativeResolveBridge(root=self._root, config=self._config.resolve, timeout_seconds=15)
        )
        self._refresh_worker.moveToThread(self._refresh_thread)
        self._refresh_thread.started.connect(self._refresh_worker.run)
        self._refresh_worker.finished.connect(self._timeline_refreshed)
        self._refresh_worker.failed.connect(self._timeline_refresh_failed)
        self._refresh_worker.finished.connect(self._refresh_thread.quit)
        self._refresh_worker.failed.connect(self._refresh_thread.quit)
        self._refresh_thread.finished.connect(self._refresh_worker.deleteLater)
        self._refresh_thread.finished.connect(self._refresh_finished)
        self._refresh_timeline_button.setText("Atualizando…")
        self._workspace.setEnabled(False)
        self._update_refresh_availability()
        self.statusBar().showMessage("Lendo a timeline atual do Resolve…")
        self._refresh_thread.start()

    def _timeline_refreshed(self, context: dict[str, Any]) -> None:
        self._apply_context(context)
        self._analysis_result = None
        self._adapter = None
        self._manual_audio = None
        self._manual_audio_button.setText("Selecionar WAV para análise")
        self._model.replace_suggestions((), fps=float(context.get("fps") or 30), drop_frame=False)
        self._apply_button.setEnabled(False)
        self._source_notice.setText("Timeline atualizada. Selecione as faixas de voz.")
        self._navigate(0)
        self.statusBar().showMessage(
            "Timeline atualizada. Selecione as faixas de voz para continuar."
        )

    def _timeline_refresh_failed(self, message: str) -> None:
        self.statusBar().showMessage(
            "Não foi possível atualizar a timeline. Os dados anteriores foram mantidos."
        )
        self._source_notice.setText(message)

    def _refresh_finished(self) -> None:
        thread = self._refresh_thread
        self._refresh_thread = None
        self._refresh_worker = None
        if thread is not None:
            thread.deleteLater()
        self._workspace.setEnabled(True)
        self._refresh_timeline_button.setText("Atualizar timeline")
        self._update_refresh_availability()

    def closeEvent(self, event: Any) -> None:
        if self._refresh_thread is not None or self._transcript_panel.has_running_worker:
            self.statusBar().showMessage("Aguarde a operação em andamento terminar para fechar.")
            event.ignore()
            return
        if self._settings_dialog is not None:
            self._settings_dialog.reject()
        super().closeEvent(event)

    def _refresh_voice_tracks(self) -> None:
        raw_tracks = self._context.get("audio_tracks", [])
        tracks: tuple[AudioTrackSnapshot, ...] = ()
        if isinstance(raw_tracks, list):
            try:
                tracks = tuple(
                    AudioTrackSnapshot.from_dict(item)
                    for item in raw_tracks
                    if isinstance(item, dict)
                )
            except (KeyError, TypeError, ValueError):
                tracks = ()
        project = str(self._context.get("project_name") or "")
        timeline = str(self._context.get("timeline_name") or "")
        identity = (project, timeline)
        selected: tuple[SelectedVoiceTrack, ...] = ()
        warnings: tuple[str, ...] = ()
        if identity == self._voice_context_identity:
            selected, warnings = validate_voice_selection(
                tracks, self._voice_selector.selected_tracks()
            )
        elif project and timeline:
            try:
                restored = self._voice_settings.load(
                    project=project,
                    timeline=timeline,
                    timeline_fingerprint=self._voice_timeline_fingerprint(),
                    audio_tracks=tracks,
                )
                selected = restored.selected_voice_tracks
                warnings = restored.warnings
                self._manual_audio = restored.manual_wav
            except OEditorError as exc:
                warnings = (str(exc),)
        suggested = suggest_voice_tracks(tracks)
        if self._use_mock and not selected:
            selected = tuple(
                _default_selected_track(track) for track in tracks if track.index in set(suggested)
            )
        self._voice_context_identity = identity
        self._voice_selector.set_tracks(
            tracks,
            selected=selected,
            suggested_indices=suggested,
            warnings=warnings,
        )
        self._transcript_panel.context_changed()
        if self._manual_audio:
            self._manual_audio_button.setText(f"WAV: {self._manual_audio.name}")
        self._update_analysis_availability()

    def _voice_timeline_fingerprint(self) -> str:
        payload = {
            key: self._context.get(key)
            for key in (
                "project_name",
                "timeline_name",
                "timeline_id",
                "fps",
                "start_frame",
                "end_frame",
                "track_counts",
                "audio_tracks",
            )
        }
        return JsonCache.make_key(json.dumps(payload, ensure_ascii=False, sort_keys=True))

    def _voice_selection_changed(self) -> None:
        project = str(self._context.get("project_name") or "")
        timeline = str(self._context.get("timeline_name") or "")
        if project and timeline:
            try:
                self._voice_settings.save(
                    project=project,
                    timeline=timeline,
                    timeline_fingerprint=self._voice_timeline_fingerprint(),
                    selected_voice_tracks=self._voice_selector.selected_tracks(),
                    manual_wav=self._manual_audio,
                )
            except OEditorError as exc:
                self._voice_selector.warning_label.setText(str(exc))
        self._update_analysis_availability()
        self._transcript_panel.selection_changed()

    def _update_analysis_availability(self) -> None:
        has_source = bool(self._voice_selector.selected_tracks() or self._manual_audio)
        has_context = self._use_mock or self._internal_host or self._external_bridge_enabled
        self._analyze_button.setEnabled(not self._busy and has_context and has_source)
        self._source_next_button.setEnabled(
            has_context and (self._use_mock or bool(self._voice_selector.selected_tracks()))
        )
        if not has_source:
            self._analyze_button.setToolTip(
                "Selecione pelo menos uma faixa de voz ou forneça um WAV manual."
            )
        else:
            self._analyze_button.setToolTip("")

    def _make_analysis_service(self) -> AnalyzeTimeline:
        zoom_gap, zoom_maximum = {
            "low": (20.0, 1),
            "medium": (8.0, 3),
            "high": (4.0, 6),
        }[_combo_value(self._zoom_frequency)]
        text_gap, text_maximum = {
            "low": (10.0, 2),
            "medium": (7.0, 4),
            "high": (4.0, 6),
        }[_combo_value(self._text_frequency)]
        analyzer = HeuristicAnalyzer(
            zoom=replace(
                self._config.zoom,
                intensity=_combo_value(self._zoom_intensity),
                frequency=_combo_value(self._zoom_frequency),
                minimum_gap_seconds=zoom_gap,
                maximum_per_minute=zoom_maximum,
            ),
            text=replace(
                self._config.text,
                frequency=_combo_value(self._text_frequency),
                minimum_gap_seconds=text_gap,
                maximum_per_minute=text_maximum,
            ),
            configured_keywords=self._config.analysis.keywords,
        )
        adapter: ResolveAdapter
        exporter: AudioExporter
        provider: TranscriptionProvider
        selected = self._voice_selector.selected_tracks()
        backend = "manual_wav" if self._manual_audio else "internal_resolve_lua"
        if self._use_mock:
            adapter = MockResolveAdapter()
            exporter = ResolveAudioExporter(adapter)
            provider = MockTranscriptionProvider()
            backend = "mock_voice_tracks"
        elif self._internal_host:
            adapter = InternalContextAdapter(self._context)
            exporter = (
                ManualAudioExporter(self._manual_audio)
                if self._manual_audio
                else InternalVoiceAudioExporter()
            )
            provider = FasterWhisperProvider(
                model_path=(
                    Path(self._config.transcription.model_path)
                    if self._config.transcription.model_path
                    else None
                ),
                configured_model_name=self._config.transcription.model,
                device=self._config.transcription.device,
                device_index=self._config.transcription.device_index,
                compute_type=self._config.transcription.compute_type,
            )
        elif self._external_bridge_enabled:
            adapter = RealResolveAdapter(
                self._config.resolve,
                self._capabilities,
                root=self._root,
            )
            exporter = (
                ManualAudioExporter(self._manual_audio)
                if self._manual_audio
                else ResolveAudioExporter(adapter)
            )
            backend = "manual_wav" if self._manual_audio else "external_fusionscript_bridge"
            provider = FasterWhisperProvider(
                model_path=(
                    Path(self._config.transcription.model_path)
                    if self._config.transcription.model_path
                    else None
                ),
                configured_model_name=self._config.transcription.model,
                device=self._config.transcription.device,
                device_index=self._config.transcription.device_index,
                compute_type=self._config.transcription.compute_type,
            )
        else:
            raise OEditorError(
                "A análise exige um contexto interno do Resolve. "
                "A ponte externa experimental está desabilitada."
            )
        self._adapter = adapter
        cache_root = (
            self._root / "runtime" / "cache" if self._use_mock else default_app_cache_root()
        )
        return AnalyzeTimeline(
            adapter=adapter,
            audio_exporter=exporter,
            transcription_provider=provider,
            analyzer=analyzer,
            cache=JsonCache(cache_root),
            selected_voice_tracks=selected,
            audio_backend=backend,
            allow_manual_without_tracks=self._manual_audio is not None,
        )

    def _start_analysis(self) -> None:
        if self._thread is not None:
            return
        if not self._voice_selector.selected_tracks() and self._manual_audio is None:
            self._report.setPlainText(
                "Selecione pelo menos uma faixa de voz ou forneça um WAV manual."
            )
            return
        if not (self._use_mock or self._internal_host or self._external_bridge_enabled):
            self._report.setPlainText(
                "A análise está indisponível sem contexto de timeline. "
                "Selecionar WAV permanece disponível."
            )
            return
        self._progress.setValue(0)
        self._set_busy(True)
        self._cancellation = CancellationToken()
        worker = AnalysisWorker(
            self._make_analysis_service(),
            self._root / "runtime",
            self._config.transcription.language,
            self._cancellation,
        )
        self._start_worker(worker, worker.finished, self._analysis_finished)

    def _analysis_finished(self, result: AnalysisResult) -> None:
        self._analysis_result = result
        snapshot = result.snapshot
        self._project_label.setText(snapshot.project_name)
        self._timeline_label.setText(snapshot.timeline_name)
        self._timeline_label.setToolTip(snapshot.timeline_name)
        self._duration_label.setText(f"{snapshot.duration_frames / snapshot.fps:.1f} segundos")
        self._fps_label.setText(f"{snapshot.fps:g}{' DF' if snapshot.drop_frame else ''}")
        self._internal_host_label.setText("READY" if self._internal_host else "UNVERIFIED")
        self._model.replace_suggestions(
            result.suggestions,
            fps=snapshot.fps,
            drop_frame=snapshot.drop_frame,
        )
        self._table.resizeColumnsToContents()
        self._apply_button.setEnabled(bool(result.suggestions))
        voice_summary = (
            ", ".join(f"A{item.index}" for item in result.selected_voice_tracks) or "WAV manual"
        )
        self._report.setPlainText(
            f"Análise {result.analysis_id}\n"
            f"{len(result.transcript.segments)} segmentos transcritos\n"
            f"{len(result.suggestions)} sugestões geradas\n"
            f"Voz: {voice_summary}\n"
            f"Backend de áudio: {result.audio_backend}\n"
            f"Origem: {result.audio_origin}\n"
            f"Cache: {result.audio_cache_key}\n"
            "Revise, edite e aprove as sugestões antes de aplicar."
        )
        self._progress.setValue(100)

    def _source_context_with_audio(self) -> dict[str, Any]:
        if self._analysis_result is None:
            return dict(self._context)
        result = self._analysis_result
        return {
            **self._context,
            "selected_voice_tracks": [item.to_dict() for item in result.selected_voice_tracks],
            "audio_backend": result.audio_backend,
            "audio_cache_key": result.audio_cache_key,
            "audio_file": str(result.audio_path),
            "audio_duration_seconds": result.snapshot.duration_frames / result.snapshot.fps,
            "audio_sample_rate": 48_000,
            "audio_origin": result.audio_origin,
        }

    def _start_apply(self) -> None:
        if self._analysis_result is None or self._adapter is None or self._thread is not None:
            return
        try:
            built = build_application_plan(
                analysis_id=self._analysis_result.analysis_id,
                analyzed_snapshot=self._analysis_result.snapshot,
                current_snapshot=self._analysis_result.snapshot,
                suggestions=self._current_suggestions(),
                capabilities=self._capabilities,
                dry_run=self._dry_run.isChecked(),
                duplicate_suffix=self._config.resolve.duplicate_suffix,
            )
            save_application_plan(built.plan, self._root / "runtime")
            approved_paths = save_approved_plan(
                snapshot=self._analysis_result.snapshot,
                suggestions=self._current_suggestions(),
                source_context=self._source_context_with_audio(),
            )
        except OEditorError as exc:
            self._show_error(str(exc))
            return
        if not self._use_mock:
            self._report.setPlainText(
                "Plano aprovado salvo para o host interno.\n"
                + "\n".join(str(path) for path in approved_paths)
                + "\nA aplicação externa não executou mutações."
            )
            return
        self._progress.setValue(0)
        self._set_busy(True)
        self._cancellation = CancellationToken()
        worker = ApplyWorker(
            ApplyPlan(
                self._adapter,
                text_track_name=self._config.resolve.text_track_name,
            ),
            built.plan,
            self._root / "runtime",
            self._cancellation,
        )
        self._start_worker(worker, worker.finished, self._application_finished)

    def _application_finished(
        self,
        report: ApplicationReport,
        paths: tuple[Path, Path],
    ) -> None:
        self._report.setPlainText(
            render_application_report(report)
            + "\nArquivos:\n"
            + "\n".join(str(path) for path in paths)
        )
        self._progress.setValue(100)

    def _start_worker(
        self,
        worker: AnalysisWorker | ApplyWorker,
        finished_signal: Any,
        finished_slot: Callable[..., None],
    ) -> None:
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._update_progress) if isinstance(
            worker, AnalysisWorker
        ) else None
        finished_signal.connect(finished_slot)
        finished_signal.connect(thread.quit)
        worker.failed.connect(self._worker_failed)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(self._thread_finished)
        self._thread = thread
        self._worker = worker
        thread.start()

    def _thread_finished(self) -> None:
        self._thread = None
        self._worker = None
        self._cancellation = None
        self._set_busy(False)

    def _worker_failed(self, message: str) -> None:
        self._report.setPlainText("Falha controlada: " + message)
        self._show_diagnostics()
        self.statusBar().showMessage("Componente indisponível; a interface continua ativa.")

    def _update_progress(self, value: float, message: str) -> None:
        self._progress.setValue(round(value * 100))
        self.statusBar().showMessage(message)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._update_refresh_availability()
        self._analysis_footer.setVisible(busy)
        self._update_analysis_availability()
        self._cancel_button.setEnabled(busy)
        self._apply_button.setEnabled(not busy and self._analysis_result is not None)

    def _cancel(self) -> None:
        self._transcript_panel.cancel()
        if self._cancellation:
            self._cancellation.cancel()
            self.statusBar().showMessage("Cancelamento solicitado…")

    def _select_wav(self) -> None:
        path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Selecionar WAV exportado da timeline",
            "",
            "Áudio WAV (*.wav)",
        )
        if path:
            self._manual_audio = Path(path)
            self._manual_audio_button.setText(f"WAV: {self._manual_audio.name}")
            self._voice_selection_changed()

    def _set_filter(self, _index: int) -> None:
        value = _combo_value(self._filter)
        self._proxy.setFilterRegularExpression("" if value == "todos" else value)
        self._proxy.invalidateFilter()

    def _go_to_selected(self) -> None:
        selection = self._table.selectionModel().selectedRows()
        if not selection or self._adapter is None:
            return
        source = self._proxy.mapToSource(selection[0])
        suggestion = self._model.suggestion_at(source.row())
        if suggestion and not self._adapter.set_playhead(suggestion.timeline_start_frame):
            self._show_error("O Resolve não confirmou a mudança do playhead.")

    def _export_plan(self) -> None:
        if self._analysis_result is None:
            self._show_error("Analise uma timeline antes de exportar o plano.")
            return
        try:
            built = build_application_plan(
                analysis_id=self._analysis_result.analysis_id,
                analyzed_snapshot=self._analysis_result.snapshot,
                current_snapshot=self._analysis_result.snapshot,
                suggestions=self._current_suggestions(),
                capabilities=self._capabilities,
                dry_run=self._dry_run.isChecked(),
                duplicate_suffix=self._config.resolve.duplicate_suffix,
            )
            source = save_application_plan(built.plan, self._root / "runtime")
            approved_paths = save_approved_plan(
                snapshot=self._analysis_result.snapshot,
                suggestions=self._current_suggestions(),
                source_context=self._source_context_with_audio(),
            )
        except OEditorError as exc:
            self._show_error(str(exc))
            return
        destination, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "Exportar plano",
            "application_plan.json",
            "JSON (*.json)",
        )
        if destination:
            try:
                shutil.copy2(source, destination)
            except OSError as exc:
                self._show_error(f"Não foi possível exportar o plano: {exc}")
        self.statusBar().showMessage(
            "Plano aprovado salvo: " + ", ".join(str(path) for path in approved_paths)
        )

    def _approved_suggestions_changed(self, *_args: Any) -> None:
        if self._analysis_result is None:
            return
        try:
            paths = save_approved_plan(
                snapshot=self._analysis_result.snapshot,
                suggestions=self._current_suggestions(),
                source_context=self._source_context_with_audio(),
            )
        except OEditorError as exc:
            self.statusBar().showMessage(f"Plano aprovado não pôde ser salvo: {exc}")
            return
        self.statusBar().showMessage(f"Plano aprovado atualizado: {paths[0]}")

    def _show_error(self, message: str) -> None:
        QMessageBox.critical(self, "EDE", message)


def _load_capabilities(path: Path) -> tuple[CapabilityResult, ...]:
    if not path.exists():
        return ()
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        results = value.get("results", []) if isinstance(value, dict) else []
        return tuple(CapabilityResult.from_dict(item) for item in results if isinstance(item, dict))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return ()


def _load_context(
    path: str | None,
    *,
    use_mock: bool,
    config: AppConfig,
    root: Path,
    internal_host: bool = False,
) -> dict[str, Any] | None:
    if not path:
        return None
    context = None
    try:
        context = consume_launch_context(
            Path(path),
            require_internal_host=internal_host,
        )
        if use_mock:
            return context.to_dict()
        if internal_host:
            return {
                **context.to_dict(),
                "real_integration_available": True,
                "integration_mode": "internal_resolve_host",
                "connection_status": "Contexto recebido e validado pelo host interno.",
            }
        if config.resolve.external_bridge_enabled:
            return reconcile_launch_context(context, config.resolve, root=root)
        return {
            **context.to_dict(),
            "real_integration_available": False,
            "integration_mode": "legacy_launcher_context",
            "connection_status": (
                "Ponte externa desabilitada. O contexto do launcher foi preservado "
                "sem reconexão nativa."
            ),
        }
    except OEditorError as exc:
        preserved_context = context.to_dict() if context else {}
        return {
            **preserved_context,
            "real_integration_available": False,
            "connection_status": (
                f"Contexto não confirmado: {exc} A interface continua disponível em modo seguro."
            ),
        }


def run_ui(*, use_mock: bool, context_path: str | None, internal_host: bool = False) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    config = bootstrap()
    root = project_root()
    window = MainWindow(
        config=config,
        root=root,
        use_mock=use_mock,
        context=_load_context(
            context_path,
            use_mock=use_mock,
            config=config,
            root=root,
            internal_host=internal_host,
        ),
    )
    window.show()
    return int(app.exec())


def _add_localized_items(
    combo: QComboBox,
    items: tuple[tuple[str, str], ...],
    selected: str,
) -> None:
    for label, value in items:
        combo.addItem(label, value)
    index = combo.findData(selected)
    combo.setCurrentIndex(max(0, index))


def _default_selected_track(track: AudioTrackSnapshot) -> SelectedVoiceTrack:
    mode = ChannelMode.MONO if track.audio_type == "mono" else ChannelMode.BOTH
    return SelectedVoiceTrack(track.index, track.name, mode)


def _combo_value(combo: QComboBox) -> str:
    value = combo.currentData()
    return str(value) if value is not None else combo.currentText()
