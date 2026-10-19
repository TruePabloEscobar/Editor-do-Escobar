"""'Transcrição e Rough Cut' tab: transcribe tracks, TXT round trip, preview and apply."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QSettings, Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from o_editor.application.rough_cut import (
    APPLY_SCRIPT_MENU,
    cancel_plan_for_resolve,
    prepare_rough_cut,
    render_preview,
    save_plan_for_resolve,
)
from o_editor.application.transcribe_tracks import TranscribeTracks
from o_editor.application.transcript_exchange import (
    ImportPreview,
    confirm_import,
    decide_missing,
    export_transcripts,
    preview_import,
)
from o_editor.domain.microphone_cleanup import MicrophoneCleanupSettings
from o_editor.domain.rough_cut import (
    RoughCutPlan,
    SilencePreset,
    SilenceSettings,
    TrackPolicy,
)
from o_editor.domain.speech import TranscriptSession
from o_editor.domain.timeline_layout import LayoutError, TimelineLayout
from o_editor.domain.voice_tracks import SelectedVoiceTrack
from o_editor.errors import OEditorError
from o_editor.infrastructure.audio.track_renderer import TrackAudioRenderer
from o_editor.infrastructure.cache import JsonCache, default_app_cache_root
from o_editor.infrastructure.config import AppConfig
from o_editor.infrastructure.ffmpeg.runner import FFmpegRunner
from o_editor.infrastructure.resolve.native_bridge import NativeResolveBridge
from o_editor.infrastructure.transcript_sessions import SessionStore
from o_editor.infrastructure.transcription.base import CancellationToken
from o_editor.infrastructure.transcription.track import (
    FasterWhisperTrackTranscriber,
    SignalMockTranscriber,
    TrackTranscriber,
)
from o_editor.internal_actions.presentation import render_internal_action
from o_editor.internal_actions.request import InternalActionRequest
from o_editor.ui.controllers.workers import RoughCutDispatchWorker, TranscriptionWorker
from o_editor.ui.duration_control import DurationControl
from o_editor.ui.models.transcript_model import (
    TEXT_COLUMN,
    TranscriptFilterModel,
    TranscriptTableModel,
)
from o_editor.ui.theme import label

PRESET_LABELS = (
    ("Desligada", SilencePreset.OFF),
    ("Suave", SilencePreset.LIGHT),
    ("Média", SilencePreset.MEDIUM),
    ("Forte", SilencePreset.STRONG),
    ("Personalizada", SilencePreset.CUSTOM),
)


class TranscriptPanel(QWidget):
    stage_requested = Signal(int)
    activity_changed = Signal()

    def __init__(
        self,
        *,
        config: AppConfig,
        root: Path,
        use_mock: bool,
        context_provider: Callable[[], dict[str, Any]],
        selected_tracks_provider: Callable[[], tuple[SelectedVoiceTrack, ...]],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._root = root
        self._preferences = QSettings(
            str(root / "runtime/ui-preferences.ini"), QSettings.Format.IniFormat
        )
        self._use_mock = use_mock
        self._context_provider = context_provider
        self._selected_tracks_provider = selected_tracks_provider
        self._store = SessionStore(root / "runtime" / "mock-sessions" if use_mock else None)
        self._session: TranscriptSession | None = None
        self._layout: TimelineLayout | None = None
        self._layout_error: str | None = None
        self._plan: RoughCutPlan | None = None
        self._pending_plan_id: str | None = None
        self._pending_mode: str | None = None
        self._dispatch_thread: QThread | None = None
        self._dispatch_worker: RoughCutDispatchWorker | None = None
        self._automatic_dispatch = False
        self._dispatch_acknowledged = False
        self._resolve_timer = QTimer(self)
        self._resolve_timer.setSingleShot(True)
        self._resolve_timer.setInterval(300_000)
        self._resolve_timer.timeout.connect(self._resolve_request_expired)
        self._thread: QThread | None = None
        self._worker: TranscriptionWorker | None = None
        self._cancellation: CancellationToken | None = None
        self._identity: tuple[str, str] | None = None
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(700)
        self._save_timer.timeout.connect(self._save_session_edits)
        self._model = TranscriptTableModel()
        self._proxy = TranscriptFilterModel()
        self._proxy.setSourceModel(self._model)
        self._model.dataChanged.connect(self._segments_edited)
        self._build_ui()
        self._update_buttons()

    # ------------------------------------------------------------------ layout
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 12, 18, 12)
        layout.setSpacing(8)
        self.stage_caption = label("02 / TRANSCRIBIR", "eyebrow")
        self.stage_title = label("Da fala para o texto", "heading")
        self.stage_caption.hide()
        self.stage_title.hide()
        self.status_label = label("Abra O Editor pelo menu do Resolve para carregar a timeline.")
        layout.addWidget(self.status_label)
        self.pages = QStackedWidget()
        layout.addWidget(self.pages, 1)

        transcription = QWidget()
        preparation = QVBoxLayout(transcription)
        preparation.setContentsMargins(0, 0, 0, 0)
        intro = QGroupBox("Transcrição por participante")
        intro_layout = QVBoxLayout(intro)
        self.session_summary = label("Nenhuma transcrição nesta timeline.", "notice")
        intro_layout.addWidget(self.session_summary)
        intro_layout.addSpacing(14)
        top = QHBoxLayout()
        self.transcribe_button = QPushButton("Transcrever faixas selecionadas")
        self.transcribe_button.setProperty("role", "primary")
        self.retranscribe_button = QPushButton("Repetir transcrição")
        top.addWidget(self.transcribe_button)
        top.addWidget(self.retranscribe_button)
        top.addStretch()
        intro_layout.addLayout(top)
        preparation.addWidget(intro)
        preparation.addStretch()
        self.review_button = QPushButton("Continuar para revisão  →")
        self.review_button.setProperty("role", "primary")
        self.review_button.clicked.connect(lambda: self.stage_requested.emit(2))
        preparation.addWidget(self.review_button, 0, Qt.AlignmentFlag.AlignRight)
        self.pages.addWidget(transcription)

        review = QWidget()
        review_layout = QVBoxLayout(review)
        review_layout.setContentsMargins(0, 0, 0, 0)
        toolbar = QHBoxLayout()
        self.export_button = QPushButton("Exportar TXT")
        self.import_button = QPushButton("Importar TXT revisado")
        toolbar.addWidget(self.export_button)
        toolbar.addWidget(self.import_button)
        toolbar.addStretch()
        self.preview_step_button = QPushButton("Continuar para prévia  →")
        self.preview_step_button.clicked.connect(lambda: self.stage_requested.emit(3))
        toolbar.addWidget(self.preview_step_button)
        review_layout.addLayout(toolbar)
        missing = QHBoxLayout()
        self.missing_label = label("")
        self.remove_missing_button = QPushButton("Remover ausentes")
        self.keep_missing_button = QPushButton("Manter ausentes")
        missing.addWidget(self.missing_label, 1)
        missing.addWidget(self.remove_missing_button)
        missing.addWidget(self.keep_missing_button)
        review_layout.addLayout(missing)
        filters = QHBoxLayout()
        self.view_combo = QComboBox()
        self.view_combo.addItem("Geral (cronológica)", None)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Buscar uma fala ou ID…")
        self.show_bleed = QCheckBox("Vazamentos")
        self.detail_columns = QCheckBox("Detalhes")
        self.detail_columns.setToolTip("Mostrar ID, faixa e tempos de início e fim.")
        filters.addWidget(self.view_combo)
        filters.addWidget(self.search_edit, 1)
        filters.addWidget(self.show_bleed)
        filters.addWidget(self.detail_columns)
        review_layout.addLayout(filters)
        self.table = QTableView()
        self.table.setModel(self._proxy)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(42)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(TEXT_COLUMN, QHeaderView.ResizeMode.Stretch)
        for column in (1, 3, 4, 5):
            self.table.setColumnHidden(column, True)
        self.detail_columns.toggled.connect(self._toggle_detail_columns)
        review_layout.addWidget(self.table, 1)
        review_layout.addWidget(
            label("Desmarcar propõe um corte. Editar o texto preserva o áudio.")
        )
        self.pages.addWidget(review)

        preview = QWidget()
        preview_layout = QVBoxLayout(preview)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        self.preview_controls = QTabWidget()
        self.preview_controls.setObjectName("previewControls")
        self.preview_controls.setFixedHeight(214)
        self._preview_settings = self.preview_controls
        silence_page = QWidget()
        silence_layout = QVBoxLayout(silence_page)
        silence_layout.setContentsMargins(12, 8, 12, 8)
        silence_layout.setSpacing(4)
        top_row = QHBoxLayout()
        top_row.addWidget(label("Intensidade"))
        self.preset_combo = QComboBox()
        for caption, preset in PRESET_LABELS:
            self.preset_combo.addItem(caption, preset.value)
        self.preset_combo.setCurrentIndex(2)
        self.preset_combo.setMinimumWidth(130)
        top_row.addWidget(self.preset_combo)
        top_row.addSpacing(16)
        self.duration_units = QWidget()
        unit_row = QHBoxLayout(self.duration_units)
        unit_row.setContentsMargins(0, 0, 0, 0)
        self.time_units_button = QPushButton("Tempo")
        self.frame_units_button = QPushButton("Frames")
        self._unit_group = QButtonGroup(self)
        for button in (self.time_units_button, self.frame_units_button):
            button.setProperty("role", "unit")
            button.setCheckable(True)
            self._unit_group.addButton(button)
            unit_row.addWidget(button)
        self.time_units_button.setChecked(True)
        top_row.addWidget(self.duration_units)
        self.duration_fps_label = label("Carregue uma timeline para usar Frames.", "muted")
        top_row.addWidget(self.duration_fps_label)
        top_row.addStretch()
        silence_layout.addLayout(top_row)
        self.frame_units_button.toggled.connect(self._duration_units_changed)
        self.minimum_silence = DurationControl(200, 20_000, 1200, "Silêncio mínimo removível")
        self.keep_before = DurationControl(0, 3000, 250, "Margem antes da fala")
        self.keep_after = DurationControl(0, 3000, 350, "Margem depois da fala")
        knob_row = QHBoxLayout()
        for caption, control in (
            ("Silêncio mínimo", self.minimum_silence),
            ("Antes da fala", self.keep_before),
            ("Depois da fala", self.keep_after),
        ):
            knob_column = QVBoxLayout()
            caption_widget = label(caption)
            caption_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
            knob_column.addWidget(caption_widget)
            knob_column.addWidget(control)
            knob_row.addLayout(knob_column)
        knob_row.addSpacing(24)
        options = QVBoxLayout()
        self.protect_sounds = QCheckBox("Proteger risos e reações")
        self.protect_sounds.setToolTip("Preservar sons que não aparecem no texto transcrito.")
        self.protect_sounds.setChecked(True)
        self.trim_edges = QCheckBox("Remover silêncio nas extremidades")
        self.trim_edges.setChecked(True)
        options.addWidget(self.protect_sounds)
        options.addWidget(self.trim_edges)
        options.addStretch()
        knob_row.addLayout(options)
        knob_row.addStretch()
        silence_layout.addLayout(knob_row)
        self.preview_controls.addTab(silence_page, "Silêncios")

        microphones_page = QWidget()
        microphones_layout = QVBoxLayout(microphones_page)
        self.cleanup_microphones = QCheckBox("Limpar microfones sem fala / retorno")
        self.cleanup_microphones.setObjectName("cleanupMicrophones")
        self.cleanup_microphones.setChecked(
            bool(self._preferences.value("microphones/cleanup", True, type=bool))
        )
        self.cleanup_microphones.setToolTip(
            "Desativa trechos só na cópia. Falas diferentes simultâneas, risos e sons "
            "intencionais ficam ativos. Confirma retorno por áudio digital idêntico "
            "ou por texto idêntico com diferença de pelo menos 6 dB."
        )
        microphones_layout.addWidget(self.cleanup_microphones)
        microphones_layout.addWidget(
            label("Preserva falas simultâneas diferentes, risos e reações.")
        )
        microphones_layout.addStretch()
        self.preview_controls.addTab(microphones_page, "Microfones / retorno")
        self.cleanup_microphones.toggled.connect(self._microphone_cleanup_changed)

        policy_page = QWidget()
        policy_layout = QVBoxLayout(policy_page)
        policy_layout.setContentsMargins(8, 6, 8, 6)
        self.policy_table = QTableWidget(0, 2)
        self.policy_table.setHorizontalHeaderLabels(("Faixa", "Regra"))
        self.policy_table.horizontalHeader().setStretchLastSection(True)
        self.policy_table.verticalHeader().setVisible(False)
        self.policy_table.setMinimumHeight(90)
        policy_layout.addWidget(self.policy_table, 1)
        policy_layout.addWidget(
            label("Cortar junto mantém a sincronia. Omitir deixa a faixa vazia na cópia.")
        )
        self.preview_controls.addTab(policy_page, "Faixas na cópia")
        preview_layout.addWidget(self.preview_controls)
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setPlaceholderText(
            "Gere a prévia para revisar os cortes antes de aplicar."
        )
        preview_layout.addWidget(self.preview_text, 1)
        self.resolve_notice = QWidget()
        notice_layout = QHBoxLayout(self.resolve_notice)
        notice_layout.setContentsMargins(0, 0, 0, 0)
        self.resolve_notice_label = label("", "muted")
        self.resolve_notice_label.setWordWrap(True)
        notice_layout.addWidget(self.resolve_notice_label, 1)
        self.cancel_resolve_button = QPushButton("Cancelar solicitação")
        self.cancel_resolve_button.setObjectName("cancelResolveRequest")
        self.cancel_resolve_button.clicked.connect(self._cancel_resolve_request)
        notice_layout.addWidget(self.cancel_resolve_button)
        preview_layout.addWidget(self.resolve_notice)
        actions = QHBoxLayout()
        self.preview_button = QPushButton("Gerar prévia")
        self.preview_button.setProperty("role", "primary")
        self.validate_button = QPushButton("Validar no Resolve")
        self.apply_button = QPushButton("Aplicar Rough Cut")
        self.apply_button.setProperty("role", "danger")
        actions.addWidget(self.preview_button)
        actions.addStretch()
        actions.addWidget(self.validate_button)
        actions.addWidget(self.apply_button)
        preview_layout.addLayout(actions)
        self.apply_button.setToolTip("Exige confirmação e cria uma cópia verificada da timeline.")
        self.pages.addWidget(preview)
        self._transcription_footer = QWidget()
        bottom = QHBoxLayout(self._transcription_footer)
        bottom.setContentsMargins(0, 0, 0, 0)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.cancel_button = QPushButton("Cancelar transcrição")
        bottom.addWidget(self.progress, 1)
        bottom.addWidget(self.cancel_button)
        layout.addWidget(self._transcription_footer)
        self.transcribe_button.clicked.connect(lambda: self._start_transcription(force=False))
        self.retranscribe_button.clicked.connect(lambda: self._start_transcription(force=True))
        self.export_button.clicked.connect(self._export)
        self.import_button.clicked.connect(self._import)
        self.cancel_button.clicked.connect(self.cancel)
        self.remove_missing_button.clicked.connect(lambda: self._resolve_missing(remove=True))
        self.keep_missing_button.clicked.connect(lambda: self._resolve_missing(remove=False))
        self.view_combo.currentIndexChanged.connect(self._view_changed)
        self.search_edit.textChanged.connect(self._proxy.set_text)
        self.show_bleed.toggled.connect(self._proxy.set_show_bleed)
        self.preset_combo.currentIndexChanged.connect(self._preset_changed)
        self.protect_sounds.toggled.connect(self._preview_settings_changed)
        self.trim_edges.toggled.connect(self._preview_settings_changed)
        for spin in (self.minimum_silence, self.keep_before, self.keep_after):
            spin.valueChanged.connect(self._custom_values_changed)
        self.preview_button.clicked.connect(self._preview)
        self.validate_button.clicked.connect(lambda: self._send_plan(apply=False))
        self.apply_button.clicked.connect(lambda: self._send_plan(apply=True))
        self._preset_changed()
        self.set_stage(0)

    def set_stage(self, stage: int) -> None:
        """Switch pages without discarding transcription or plan state."""
        if not 0 <= stage < 3:
            return
        self.pages.setCurrentIndex(stage)
        captions = ("02 / TRANSCRIÇÃO", "03 / REVISÃO", "04 / PRÉVIA E CORTES")
        titles = ("Transcrição", "Revisão", "Prévia e cortes")
        self.stage_caption.setText(captions[stage])
        self.stage_title.setText(titles[stage])
        self._transcription_footer.setVisible(stage == 0 or self._thread is not None)

    def set_config(self, config: AppConfig) -> None:
        """Use the new engine settings for future jobs, without deleting edited sessions."""
        if self.operation_active:
            raise RuntimeError("Aguarde a operação atual antes de alterar as configurações.")
        self._config = config
        self._update_buttons()

    def selection_changed(self) -> None:
        """Refresh action availability after source selection changes."""
        self._update_buttons()

    def _toggle_detail_columns(self, visible: bool) -> None:
        for column in (1, 3, 4, 5):
            self.table.setColumnHidden(column, not visible)

    # ------------------------------------------------------------------ context
    def context_changed(self) -> None:
        previous_fingerprint = self._layout.fingerprint if self._layout else None
        context = self._context_provider()
        project = str(context.get("project_name") or "")
        timeline = str(context.get("timeline_name") or "")
        identity = (project, timeline)
        keep_previous = (
            not self._use_mock
            and not isinstance(context.get("layout"), dict)
            and identity == self._identity
            and self._layout is not None
        )
        if not keep_previous:
            self._layout_error = None
            try:
                self._layout = self._resolve_layout(context)
            except LayoutError as exc:
                self._layout = None
                self._layout_error = str(exc)
        if self._layout is not None and previous_fingerprint != self._layout.fingerprint:
            self._plan = None
            self.preview_text.clear()
        if identity != self._identity:
            self._identity = identity
            self._plan = None
            session = None
            if project and timeline:
                try:
                    session = self._store.latest_for(project, timeline)
                except OEditorError:
                    session = None
            self._set_session(session)
        self._duration_units_changed()
        self._fill_policies()
        self._update_status()
        self._update_buttons()

    def _resolve_layout(self, context: dict[str, Any]) -> TimelineLayout | None:
        if self._use_mock:
            from o_editor.demo_podcast import podcast_layout

            return podcast_layout(self._root / "runtime" / "mock-media")
        if not context.get("project_name"):
            return None
        return TimelineLayout.from_internal_context(context)

    def _set_session(self, session: TranscriptSession | None) -> None:
        self._session = session
        self.session_summary.setText(
            f"{len(session.segments)} trechos em {len(session.tracks)} faixas. Pronto para revisar."
            if session
            else "Nenhuma transcrição nesta timeline."
        )
        self._model.set_session(session)
        current = self.view_combo.currentData()
        self.view_combo.blockSignals(True)
        self.view_combo.clear()
        self.view_combo.addItem("Geral (cronológica)", None)
        if session:
            for track in session.tracks:
                self.view_combo.addItem(f"{track.key}: {track.name}", track.track_index)
        index = self.view_combo.findData(current)
        self.view_combo.setCurrentIndex(max(0, index))
        self.view_combo.blockSignals(False)
        self._view_changed()
        self.table.resizeColumnsToContents()
        self._update_missing()

    def _fill_policies(self) -> None:
        previous = self.track_policies()
        self.policy_table.setRowCount(0)
        if self._layout is None:
            return
        for track in sorted(
            self._layout.tracks, key=lambda item: (item.track_type.value != "video", item.key)
        ):
            if track.track_type.value == "subtitle":
                continue
            self.policy_table.insertRow(self.policy_table.rowCount())
            row = self.policy_table.rowCount() - 1
            item = QTableWidgetItem(track.display_name)
            item.setData(Qt.ItemDataRole.UserRole, track.key)
            item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.policy_table.setItem(row, 0, item)
            combo = QComboBox()
            combo.addItem("Cortar junto", TrackPolicy.FOLLOW.value)
            combo.addItem("Omitir", TrackPolicy.OMIT.value)
            policy = previous.get(track.key, TrackPolicy.FOLLOW)
            combo.setCurrentIndex(0 if policy == TrackPolicy.FOLLOW else 1)
            self.policy_table.setCellWidget(row, 1, combo)
            combo.currentIndexChanged.connect(self._preview_settings_changed)

    def track_policies(self) -> dict[str, TrackPolicy]:
        result: dict[str, TrackPolicy] = {}
        for row in range(self.policy_table.rowCount()):
            item = self.policy_table.item(row, 0)
            combo = self.policy_table.cellWidget(row, 1)
            if item is None or not isinstance(combo, QComboBox):
                continue
            result[str(item.data(Qt.ItemDataRole.UserRole))] = TrackPolicy(str(combo.currentData()))
        return result

    # ------------------------------------------------------------------ status
    def _update_status(self) -> None:
        if self._pending_plan_id is not None:
            self.status_label.setText(
                "Aguardando o resultado da execução automática no Resolve."
                if self._automatic_dispatch
                else f"Aguardando execução no Resolve: {APPLY_SCRIPT_MENU}."
            )
            return
        if self._layout_error:
            self.status_label.setText(self._layout_error)
            return
        if self._layout is None:
            self.status_label.setText(
                "Sem timeline carregada. Execute 'O EDITOR' no menu Scripts do Resolve."
            )
            return
        clips = len(self._layout.clips)
        if self._session is None:
            self.status_label.setText(
                f"{self._layout.timeline_name}: {clips} clipes capturados. Selecione as faixas de "
                "voz na primeira etapa e inicie a transcrição."
            )
            return
        session = self._session
        cut = sum(1 for item in session.segments if item.state.value == "CUT")
        stale = (
            " A timeline mudou desde a transcrição: transcreva novamente."
            if session.layout_fingerprint != self._layout.fingerprint
            else ""
        )
        self.status_label.setText(
            f"Revisão {session.revision}: {len(session.segments)} trechos "
            f"em {len(session.tracks)} faixa(s), {cut} marcado(s) como CUT.{stale}"
        )

    def _update_missing(self) -> None:
        pending = self._session.pending_missing if self._session else ()
        visible = bool(pending)
        self.missing_label.setText(
            f"{len(pending)} trecho(s) não apareceram no TXT importado: "
            + ", ".join(pending[:12])
            + (" …" if len(pending) > 12 else "")
            + ". Confirme o que fazer antes de aplicar cortes."
            if visible
            else ""
        )
        for widget in (self.missing_label, self.remove_missing_button, self.keep_missing_button):
            widget.setVisible(visible)

    @property
    def operation_active(self) -> bool:
        return self.has_running_worker or self._pending_plan_id is not None

    @property
    def has_running_worker(self) -> bool:
        return self._thread is not None or self._dispatch_thread is not None

    def _update_buttons(self) -> None:
        transcribing = self._thread is not None
        busy = self.has_running_worker
        waiting = self._pending_plan_id is not None
        editing = not busy and not waiting
        self.resolve_notice.setVisible(waiting)
        self.cancel_resolve_button.setEnabled(waiting and not self._dispatch_acknowledged)
        verb = "Aplicação" if self._pending_mode == "APPLY" else "Validação"
        self.resolve_notice_label.setText(
            f"{verb} enviada ao Resolve. Aguarde a conferência e o resultado nesta janela."
            if self._automatic_dispatch
            else f"{verb} aguardando execução. No DaVinci Resolve, execute {APPLY_SCRIPT_MENU}. "
            "Para alterar a prévia, cancele esta solicitação."
        )
        self._preview_settings.setEnabled(not waiting)
        self.table.setEnabled(not waiting)
        has_layout = self._layout is not None
        has_session = self._session is not None
        has_selected = self._use_mock or bool(self._selected_tracks_provider())
        self.transcribe_button.setEnabled(editing and has_layout and has_selected)
        self.retranscribe_button.setEnabled(editing and has_layout and has_session)
        self.export_button.setEnabled(editing and has_session)
        self.import_button.setEnabled(editing)
        self.preview_button.setEnabled(editing and has_session and has_layout)
        ready = (
            self._plan is not None
            and not self._plan.blocked
            and not busy
            and self._pending_plan_id is None
        )
        self.validate_button.setEnabled(ready and not self._use_mock)
        self.apply_button.setEnabled(ready)
        self.cancel_button.setEnabled(transcribing)
        self.cancel_button.setVisible(transcribing)
        self._transcription_footer.setVisible(transcribing or self.pages.currentIndex() == 0)
        self.review_button.setEnabled(has_session and not busy)
        self.preview_step_button.setEnabled(has_session and not busy)
        self.activity_changed.emit()

    # ------------------------------------------------------------------ transcription
    def _start_transcription(self, *, force: bool) -> None:
        if self._thread is not None or self._layout is None or self._pending_plan_id is not None:
            return
        selected = self._selected_tracks_provider()
        if self._use_mock:
            from o_editor.demo_podcast import SPEAKERS
            from o_editor.domain.enums import ChannelMode

            # The mock demo always transcribes the four demo microphones.
            selected = tuple(
                SelectedVoiceTrack(index, name, ChannelMode.MONO)
                for index, name in SPEAKERS.items()
            )
        if not selected:
            self._error("Selecione pelo menos uma faixa de voz na lista 'Faixas usadas para voz'.")
            return
        try:
            service = self._make_service(selected, force=force)
        except OEditorError as exc:
            self._error(str(exc))
            return
        self._cancellation = CancellationToken()
        worker = TranscriptionWorker(service, self._cancellation)
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._progress)
        worker.finished.connect(self._transcription_finished)
        worker.failed.connect(self._transcription_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(self._thread_finished)
        self._thread = thread
        self._worker = worker
        self.progress.setValue(0)
        self._update_buttons()
        thread.start()

    def _make_service(
        self, selected: tuple[SelectedVoiceTrack, ...], *, force: bool
    ) -> TranscribeTracks:
        assert self._layout is not None
        config = self._config
        runner = FFmpegRunner(
            ffmpeg_path=Path(config.ffmpeg.ffmpeg_path) if config.ffmpeg.ffmpeg_path else None,
            ffprobe_path=Path(config.ffmpeg.ffprobe_path) if config.ffmpeg.ffprobe_path else None,
        )
        transcriber: TrackTranscriber
        if self._use_mock:
            from o_editor.demo_podcast import demo_phrase_resolver, write_podcast_media

            media = self._root / "runtime" / "mock-media"
            if not (media / "mic_01.wav").is_file():
                write_podcast_media(media)
            cache_root = self._root / "runtime" / "cache"
            transcriber = SignalMockTranscriber(demo_phrase_resolver)
        else:
            cache_root = default_app_cache_root()
            transcriber = FasterWhisperTrackTranscriber(
                model_path=(
                    Path(config.transcription.model_path)
                    if config.transcription.model_path
                    else None
                ),
                configured_model_name=config.transcription.model,
                device=config.transcription.device,
                device_index=config.transcription.device_index,
                compute_type=config.transcription.compute_type,
            )
        return TranscribeTracks(
            layout=self._layout,
            selected_tracks=selected,
            renderer=TrackAudioRenderer(runner, cache_root),
            transcriber=transcriber,
            transcript_cache=JsonCache(cache_root),
            session_store=self._store,
            language=config.transcription.language,
            previous_session=self._session,
            force_tracks=frozenset(item.index for item in selected) if force else frozenset(),
        )

    def _progress(self, value: float, message: str) -> None:
        self.progress.setValue(round(value * 100))
        self.status_label.setText(message)

    def _transcription_finished(self, session: TranscriptSession) -> None:
        self._plan = None
        self._set_session(session)
        self.progress.setValue(100)
        self._update_status()
        warnings = "\n".join(f"- {item}" for item in session.warnings)
        self.preview_text.setPlainText(
            f"Transcrição concluída: {len(session.segments)} trechos.\n"
            + (f"\nAvisos:\n{warnings}" if warnings else "")
        )

    def _transcription_failed(self, message: str) -> None:
        self.status_label.setText("Falha controlada: " + message)
        self.preview_text.setPlainText("A transcrição não foi concluída.\n\n" + message)

    def _thread_finished(self) -> None:
        self._thread = None
        self._worker = None
        self._cancellation = None
        self._update_buttons()

    def cancel(self) -> None:
        if self._cancellation:
            self._cancellation.cancel()
            self.status_label.setText("Cancelamento solicitado…")

    # ------------------------------------------------------------------ edits
    def _segments_edited(self, *_args: Any) -> None:
        session = self._model.session
        if session is None:
            return
        self._session = session
        self._plan = None
        self._update_buttons()
        self._save_timer.start()

    def _save_session_edits(self) -> None:
        if self._session is None:
            return
        try:
            self._store.save(self._session)
        except OEditorError as exc:
            self.status_label.setText(f"Não foi possível salvar as edições: {exc}")
            return
        self._update_status()

    def _view_changed(self, *_args: Any) -> None:
        value = self.view_combo.currentData()
        self._proxy.set_track(int(value) if value is not None else None)

    # ------------------------------------------------------------------ TXT
    def _export(self) -> None:
        if self._session is None:
            return
        self._save_timer.stop()
        self._save_session_edits()
        directory = QFileDialog.getExistingDirectory(self, "Pasta para exportar a transcrição")
        if not directory:
            return
        try:
            result = export_transcripts(self._session, Path(directory), self._store)
        except OEditorError as exc:
            self._error(str(exc))
            return
        self._session = result.session
        self._model.set_session(result.session)
        self.preview_text.setPlainText(
            "Arquivos exportados:\n"
            + "\n".join(f"- {path}" for path in result.files)
            + "\n\nEdite qualquer um deles (inclusive com uma IA) e use "
            "'Importar transcrição editada'."
        )
        self.status_label.setText(
            f"Transcrição exportada: {len(result.files)} arquivos em {directory}."
        )

    def _import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Importar transcrição editada", "", "Texto (*.txt);;Todos os arquivos (*)"
        )
        if not path:
            return
        self._save_timer.stop()
        self._save_session_edits()
        try:
            preview = preview_import(Path(path), self._store)
        except OEditorError as exc:
            self._error(str(exc))
            return
        self.preview_text.setPlainText("\n".join(preview.summary_lines()))
        self.stage_requested.emit(3)
        if preview.blocked:
            return
        if not self._confirm_import(preview):
            self.preview_text.append("\nImportação cancelada; nada foi alterado.")
            return
        try:
            session = confirm_import(preview, self._store)
        except OEditorError as exc:
            self._error(str(exc))
            return
        self._plan = None
        if self._identity == (session.project_name, session.timeline_name):
            self._set_session(session)
        self.preview_text.append(
            "\nImportação aplicada à sessão. Gere a prévia para revisar os cortes."
        )
        self._update_status()
        self._update_buttons()

    def _confirm_import(self, preview: ImportPreview) -> bool:
        review = preview.review
        message = (
            f"Aplicar a importação de {preview.path.name}?\n\n"
            f"CUT: {len(review.cut_ids)} | correções: {len(review.corrections)} | "
            f"ausentes: {len(review.missing)}\n\n"
            "Nenhum corte será feito no Resolve nesta etapa."
        )
        answer = QMessageBox.question(self, "EDE", message)
        return answer == QMessageBox.StandardButton.Yes

    def _resolve_missing(self, *, remove: bool) -> None:
        if self._session is None or not self._session.pending_missing:
            return
        verb = "REMOVER" if remove else "MANTER"
        answer = QMessageBox.question(
            self,
            "EDE",
            f"Confirma {verb} {len(self._session.pending_missing)} trecho(s) ausente(s) do TXT?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self._set_session(decide_missing(self._session, self._store, remove=remove))
        except OEditorError as exc:
            self._error(str(exc))
            return
        self._plan = None
        self._update_status()
        self._update_buttons()

    # ------------------------------------------------------------------ rough cut
    def _duration_units_changed(self, *_args: Any) -> None:
        fps = self._layout.fps if self._layout is not None else None
        self.frame_units_button.setEnabled(fps is not None)
        self.frame_units_button.setToolTip(
            "Editar em quadros usando o FPS da timeline."
            if fps
            else "Carregue uma timeline para usar Frames."
        )
        if fps is None and self.frame_units_button.isChecked():
            self.time_units_button.setChecked(True)
        frames = self.frame_units_button.isChecked()
        for control in (self.minimum_silence, self.keep_before, self.keep_after):
            control.set_display(frames, fps)
        self.duration_fps_label.setText(
            f"{fps:g} fps · 1 quadro por passo" if fps and frames else ""
        )
        self.duration_fps_label.setVisible(frames)

    def _microphone_cleanup_changed(self, enabled: bool) -> None:
        self._preferences.setValue("microphones/cleanup", enabled)
        self._preferences.sync()
        self._preview_settings_changed()

    def silence_settings(self) -> SilenceSettings:
        preset = SilencePreset(str(self.preset_combo.currentData()))
        if preset == SilencePreset.OFF:
            return SilenceSettings(enabled=False)
        return SilenceSettings(
            enabled=True,
            minimum_silence_ms=self.minimum_silence.value(),
            keep_before_speech_ms=self.keep_before.value(),
            keep_after_speech_ms=self.keep_after.value(),
            protect_untranscribed_sound=self.protect_sounds.isChecked(),
            trim_start_and_end=self.trim_edges.isChecked(),
        )

    def _preset_changed(self, *_args: Any) -> None:
        preset = SilencePreset(str(self.preset_combo.currentData()))
        enabled = preset != SilencePreset.OFF
        for widget in (self.minimum_silence, self.keep_before, self.keep_after):
            widget.setEnabled(enabled)
        if preset in {SilencePreset.LIGHT, SilencePreset.MEDIUM, SilencePreset.STRONG}:
            values = SilenceSettings.from_preset(preset)
            for spin, value in (
                (self.minimum_silence, values.minimum_silence_ms),
                (self.keep_before, values.keep_before_speech_ms),
                (self.keep_after, values.keep_after_speech_ms),
            ):
                spin.blockSignals(True)
                spin.setValue(value)
                spin.blockSignals(False)
        self._preview_settings_changed()

    def _custom_values_changed(self, *_args: Any) -> None:
        custom = self.preset_combo.findData(SilencePreset.CUSTOM.value)
        if self.preset_combo.currentIndex() != custom:
            self.preset_combo.blockSignals(True)
            self.preset_combo.setCurrentIndex(custom)
            self.preset_combo.blockSignals(False)
        self._preview_settings_changed()

    def _preview_settings_changed(self, *_args: Any) -> None:
        self._plan = None
        self._update_status()
        if self._session is not None and self._pending_plan_id is None:
            self.status_label.setText(
                "Prévia desatualizada. Clique em 'Gerar prévia' "
                "para validar ou aplicar as mudanças."
            )
        self._update_buttons()

    def _preview(self) -> None:
        if self._pending_plan_id is not None:
            self._update_status()
            return
        if self._session is None or self._layout is None:
            return
        self._save_timer.stop()
        self._save_session_edits()
        try:
            self._plan = prepare_rough_cut(
                self._session,
                layout=self._layout,
                silence=self.silence_settings(),
                microphone_cleanup=MicrophoneCleanupSettings(
                    enabled=self.cleanup_microphones.isChecked()
                ),
                track_policies=self.track_policies(),
            )
        except (OEditorError, ValueError) as exc:
            self._plan = None
            self._error(str(exc))
            return
        self.preview_text.setPlainText(render_preview(self._plan, self._session))
        self.status_label.setText(
            "Prévia bloqueada. Confira os alertas no plano."
            if self._plan.blocked
            else "Prévia pronta para revisão."
        )
        self._update_buttons()

    def _send_plan(self, *, apply: bool) -> None:
        plan = self._plan
        if plan is None or plan.blocked or self._pending_plan_id is not None:
            return
        if apply:
            answer = QMessageBox.question(
                self,
                "Aplicar Rough Cut",
                f"Criar a nova timeline '{plan.target_timeline_name}' com "
                f"{plan.stats.operations} itens?\n\nA timeline original não será alterada. "
                "Após confirmar, o programa executará o pedido no Resolve.",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        if self._use_mock:
            self.preview_text.append(
                "\n[Mock] O plano foi gerado, mas nenhuma timeline real existe neste modo."
            )
            return
        try:
            path = save_plan_for_resolve(plan, apply=apply)
        except OEditorError as exc:
            self._error(str(exc))
            return
        self._pending_plan_id = plan.plan_id
        self._pending_mode = "APPLY" if apply else "VALIDATE"
        self._dispatch_acknowledged = False
        self._resolve_timer.start()
        self.status_label.setText(
            f"Aguardando o Resolve: execute {APPLY_SCRIPT_MENU} em até 5 minutos."
        )
        self._update_buttons()
        action = "aplicar" if apply else "validar (sem alterações)"
        automatic = (self._root / "launcher/internal_common.lua").is_file()
        instructions = (
            "O script será acionado automaticamente. Aguarde o resultado nesta janela."
            if automatic
            else f"No DaVinci Resolve, execute: {APPLY_SCRIPT_MENU}"
        )
        self.preview_text.append(f"\nPlano pronto para {action}: {path}\n{instructions}")
        self._start_automatic_dispatch()

    def _start_automatic_dispatch(self) -> None:
        if self._pending_plan_id is None or self._pending_mode is None:
            return
        if not (self._root / "launcher/internal_common.lua").is_file():
            return  # Incomplete installation: the existing explicit menu fallback stays available.
        thread = QThread(self)
        worker = RoughCutDispatchWorker(
            NativeResolveBridge(root=self._root, config=self._config.resolve, timeout_seconds=15),
            self._pending_plan_id,
            self._pending_mode,
        )
        self._dispatch_thread, self._dispatch_worker = thread, worker
        self._automatic_dispatch = True
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._dispatch_started)
        worker.failed.connect(self._dispatch_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(self._dispatch_finished)
        self.status_label.setText("Acionando o Resolve… Aguarde o resultado nesta janela.")
        self._update_buttons()
        thread.start()

    def _dispatch_started(self, result: dict[str, Any]) -> None:
        if self._pending_plan_id == result.get("plan_id") and self._pending_mode == result.get(
            "mode"
        ):
            self._dispatch_acknowledged = True
            self._update_buttons()
            self.status_label.setText("Pedido iniciado no Resolve. Aguardando a conferência final…")
            self.preview_text.append("\nScript acionado automaticamente. Aguarde o resultado.")

    def _dispatch_failed(self, message: str) -> None:
        if self._pending_plan_id is None:
            return
        from o_editor.internal_actions.request import app_data_root

        self._automatic_dispatch = not (app_data_root() / "plans/menu-action.json").exists()
        self._dispatch_acknowledged = self._automatic_dispatch
        self.status_label.setText("Não foi possível confirmar o acionamento automático. " + message)
        self.preview_text.append("\n" + message)
        self._update_buttons()

    def _dispatch_finished(self) -> None:
        thread = self._dispatch_thread
        self._dispatch_thread, self._dispatch_worker = None, None
        if thread is not None:
            thread.deleteLater()
        self._update_buttons()

    def _cancel_resolve_request(self) -> None:
        if self._pending_plan_id is None or self._pending_mode is None:
            return
        try:
            cancelled = cancel_plan_for_resolve(
                plan_id=self._pending_plan_id, mode=self._pending_mode
            )
        except OEditorError as exc:
            self._error(str(exc))
            return
        if not cancelled:
            message = "Solicitação já recebida pelo Resolve. Aguarde o resultado da execução."
            self.status_label.setText(message)
            self.resolve_notice_label.setText(message)
            self.cancel_resolve_button.setEnabled(False)
            return
        self._resolve_timer.stop()
        self._pending_plan_id = None
        self._pending_mode = None
        self.status_label.setText("Solicitação cancelada. Você pode revisar e gerar outra prévia.")
        self._update_buttons()

    def display_rough_cut_result(self, request: InternalActionRequest) -> bool:
        """Show the reply in the originating preview without replacing source context."""
        plan_id = request.details.get("plan_id")
        mode = request.details.get("mode")
        if self._pending_plan_id is not None and (
            plan_id != self._pending_plan_id or mode != self._pending_mode
        ):
            return False
        self._resolve_timer.stop()
        self._pending_plan_id = None
        self._pending_mode = None
        self.status_label.setText(f"{request.status}: {request.message}")
        self.preview_text.append("\n" + render_internal_action(request))
        if request.status == "SUCCESS" and request.details.get("created_timeline"):
            self._plan = None
        self._update_buttons()
        return True

    def _resolve_request_expired(self) -> None:
        self._pending_plan_id = None
        self._pending_mode = None
        message = (
            "O Resolve não confirmou a solicitação em 5 minutos. "
            "Gere a prévia e envie novamente; confira o Diagnóstico se o menu não responder."
        )
        self.status_label.setText(message)
        self.preview_text.append("\n" + message)
        self._update_buttons()

    def _error(self, message: str) -> None:
        QMessageBox.warning(self, "EDE", message)
        self.status_label.setText(message)
