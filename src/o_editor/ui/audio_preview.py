"""Grunge waveform viewer and read-only audio audition of the final plan."""

from __future__ import annotations

from bisect import bisect_right
from itertools import islice
from pathlib import Path
from typing import Any

from PySide6.QtCore import QPointF, QRect, QRectF, Qt, QThreadPool, QUrl, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPaintEvent, QPen, QResizeEvent
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from o_editor.domain.audio_preview import (
    PreviewRegion,
    RegionKind,
    original_to_result,
    original_to_sample,
    regions_for_track,
    result_to_original,
    sample_to_original,
    timeline_timecode,
)
from o_editor.domain.enums import TrackType
from o_editor.domain.rough_cut import RoughCutPlan
from o_editor.domain.speech import TranscriptSession
from o_editor.domain.timecode import frames_to_clock
from o_editor.infrastructure.audio.preview import PEAK_SAMPLES, PreviewAudio, build_preview_audio
from o_editor.infrastructure.audio.track_renderer import TrackAudioRenderer
from o_editor.infrastructure.config import AppConfig
from o_editor.infrastructure.ffmpeg.runner import FFmpegRunner
from o_editor.infrastructure.transcription.base import CancellationToken
from o_editor.ui.controllers.preview_workers import PreviewJob
from o_editor.ui.theme import PALETTE, label

COLORS = {
    RegionKind.KEEP: PALETTE["green"],
    RegionKind.CUT: PALETTE["red"],
    RegionKind.MUTE: "#646060",
}
LEFT = 62
HEADER = 26
ROW = 66


class WaveformCanvas(QWidget):
    seek_requested = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.plan: RoughCutPlan | None = None
        self.audio: PreviewAudio | None = None
        self.playhead = 0
        self.regions: dict[int, tuple[PreviewRegion, ...]] = {}
        self._region_starts: dict[int, list[int]] = {}
        self.setMouseTracking(True)
        self.setAccessibleName("Waveform dos cortes por faixa")

    def set_plan(self, plan: RoughCutPlan | None) -> None:
        self.plan, self.audio = plan, None
        self.regions = (
            {
                t.index: regions_for_track(plan, t.index)
                for t in plan.layout.tracks_of(TrackType.AUDIO)
            }
            if plan
            else {}
        )
        self._region_starts = {
            index: [r.start_frame for r in regions] for index, regions in self.regions.items()
        }
        self.playhead = plan.layout.start_frame if plan else 0
        self.setMinimumHeight(HEADER + ROW * max(1, len(self.regions)))
        self.update()

    def x_at(self, frame: int) -> float:
        if self.plan is None:
            return float(LEFT)
        layout = self.plan.layout
        return LEFT + (frame - layout.start_frame) * (self.width() - LEFT) / max(
            1, layout.end_frame - layout.start_frame
        )

    def frame_at(self, x: float) -> int:
        if self.plan is None:
            return 0
        layout = self.plan.layout
        frame = layout.start_frame + round(
            (x - LEFT) * (layout.end_frame - layout.start_frame) / max(1, self.width() - LEFT)
        )
        return max(layout.start_frame, min(layout.end_frame, frame))

    def set_playhead(self, frame: int) -> None:
        """Repaint only cursor strips; long waveforms are not rescanned on every tick."""
        previous = round(self.x_at(self.playhead))
        self.playhead = frame
        current = round(self.x_at(frame))
        for x in (previous, current):
            self.update(QRect(x - 3, 0, 7, self.height()))

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.fillRect(event.rect(), QColor(PALETTE["surface"]))
        plan = self.plan
        if plan is None:
            painter.setPen(QColor(PALETTE["sand"]))
            painter.drawText(
                event.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "Gere a prévia para visualizar as faixas.",
            )
            return
        layout = plan.layout
        painter.setPen(QColor(PALETTE["paper"]))
        # Labels use the actual timeline timecode, including a non-zero start.
        for x in range(
            max(LEFT, LEFT + (event.rect().left() - LEFT) // 150 * 150), event.rect().right(), 150
        ):
            frame = self.frame_at(x)
            tc_offset = timeline_timecode(layout, frame)
            painter.drawText(x + 3, 17, tc_offset)
        waves = {t.index: t for t in self.audio.tracks} if self.audio else {}
        for row, (index, regions) in enumerate(self.regions.items()):
            top = HEADER + row * ROW
            if top > event.rect().bottom() or top + ROW < event.rect().top():
                continue
            painter.setPen(QColor(PALETTE["paper"]))
            painter.drawText(5, top + 24, f"A{index}")
            position = max(
                0, bisect_right(self._region_starts[index], self.frame_at(event.rect().left())) - 1
            )
            for region in islice(regions, position, None):
                left, right = self.x_at(region.start_frame), self.x_at(region.end_frame)
                if left > event.rect().right():
                    break
                if right < event.rect().left():
                    continue
                color = QColor(COLORS[region.kind])
                color.setAlpha(175)
                painter.fillRect(QRectF(left, top, right - left, ROW - 2), color)
                painter.setPen(QPen(QColor(COLORS[region.kind]).lighter(155), 1))
                for boundary in (left, right):
                    painter.drawLine(QPointF(boundary, top), QPointF(boundary, top + ROW - 2))
            wave = waves.get(index)
            if wave:
                painter.setPen(QPen(QColor(PALETTE["paper"]), 1))
                for x in range(
                    max(LEFT, event.rect().left()), min(self.width(), event.rect().right() + 1)
                ):
                    a = (self.frame_at(x) - layout.start_frame) * wave.sample_rate / layout.fps
                    b = (self.frame_at(x + 1) - layout.start_frame) * wave.sample_rate / layout.fps
                    lo = max(0, int(a // PEAK_SAMPLES))
                    hi = min(len(wave.peaks), max(lo + 1, int(b // PEAK_SAMPLES) + 1))
                    if hi <= lo:
                        continue
                    peaks = wave.peaks[lo:hi]
                    low, high = min(p[0] for p in peaks), max(p[1] for p in peaks)
                    mid = top + ROW / 2
                    painter.drawLine(
                        QPointF(x, mid - high / 32768 * (ROW / 2 - 5)),
                        QPointF(x, mid - low / 32768 * (ROW / 2 - 5)),
                    )
            else:
                painter.setPen(QColor(PALETTE["sand"]))
                painter.drawText(LEFT + 8, top + 36, "Waveform aguardando áudio…")
        painter.setPen(QPen(QColor(PALETTE["sand"]), 2))
        cursor_x = self.x_at(self.playhead)
        painter.drawLine(QPointF(cursor_x, HEADER), QPointF(cursor_x, self.height()))
        painter.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and event.position().x() >= LEFT:
            self.seek_requested.emit(self.frame_at(event.position().x()))

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self.plan is None:
            return
        row = int((event.position().y() - HEADER) // ROW)
        indices = list(self.regions)
        if row < 0 or row >= len(indices):
            return
        frame = self.frame_at(event.position().x())
        for region in self.regions[indices[row]]:
            if region.start_frame <= frame < region.end_frame:
                fps = self.plan.layout.fps
                text = (
                    f"A{indices[row]} · {region.kind.value} · "
                    f"{timeline_timecode(self.plan.layout, region.start_frame)} → "
                    f"{timeline_timecode(self.plan.layout, region.end_frame)} · "
                    f"Duração: {frames_to_clock(region.end_frame - region.start_frame, fps)}"
                )
                if region.muted_under_cut:
                    text += "\nDesativação desta faixa também registrada sob o corte."
                QToolTip.showText(event.globalPosition().toPoint(), text, self)
                return
        QToolTip.hideText()


class AudioPreviewWidget(QWidget):
    def __init__(self, config: AppConfig, cache_root: Path) -> None:
        super().__init__()
        self._config, self._cache_root = config, cache_root
        self._plan: RoughCutPlan | None = None
        self._session: TranscriptSession | None = None
        self._revision = 0
        self._cancellation: CancellationToken | None = None
        self._loading = False
        self._running = False
        self._job: PreviewJob | None = None
        self._audio: PreviewAudio | None = None
        self._seek_ms = 0
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        controls = QHBoxLayout()
        self.play_button = QPushButton("Play")
        self.play_button.setAccessibleName("Reproduzir ou pausar prévia")
        self.play_button.setFixedHeight(28)
        self.play_button.setStyleSheet("QPushButton { padding: 3px 8px; }")
        self.play_button.setEnabled(False)
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Áudio original", "Simulação editada"])
        self.mode_combo.setFixedHeight(28)
        self.clock_label = label("—", "muted")
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(1, 100)
        self.zoom_slider.setValue(1)
        self.zoom_slider.setMaximumWidth(140)
        self.zoom_slider.setToolTip("Zoom horizontal da waveform")
        for widget in (self.play_button, self.mode_combo, self.clock_label):
            controls.addWidget(widget)
        controls.addStretch()
        controls.addWidget(label("Zoom"))
        controls.addWidget(self.zoom_slider)
        layout.addLayout(controls)
        self.scroll_area = QScrollArea()
        self.scroll_area.setMinimumHeight(60)
        self.scroll_area.setWidgetResizable(False)
        self.canvas = WaveformCanvas()
        self.scroll_area.setWidget(self.canvas)
        layout.addWidget(self.scroll_area, 1)
        self.status_label = label("Verde: MANTER · Vermelho: CORTAR · Cinza: DESATIVAR", "muted")
        self.status_label.setToolTip(
            "Prévia mono das fontes e canais, sem efeitos de mixagem do Resolve."
        )
        self.status_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        legend_row = QHBoxLayout()
        self.legend_label = label("Verde: MANTER · Vermelho: CORTAR · Cinza: DESATIVAR", "muted")
        legend_row.addWidget(self.legend_label)
        legend_row.addWidget(self.status_label, 1)
        layout.addLayout(legend_row)
        self.status_label.setText("Prévia mono")
        self.player = QMediaPlayer(self)
        self.output = QAudioOutput(self)
        self.player.setAudioOutput(self.output)
        self.player.positionChanged.connect(self._position_changed)
        self.player.mediaStatusChanged.connect(self._media_status_changed)
        self.player.playbackStateChanged.connect(self._playback_changed)
        self.player.errorOccurred.connect(self._playback_error)
        self.canvas.seek_requested.connect(self.seek)
        self.zoom_slider.valueChanged.connect(self._resize_canvas)
        self.play_button.clicked.connect(self._toggle_play)
        self.mode_combo.currentIndexChanged.connect(self._mode_changed)

    def set_plan(self, plan: RoughCutPlan | None, session: TranscriptSession | None) -> None:
        self.invalidate()
        self._plan, self._session = plan, session
        self.canvas.set_plan(plan)
        self._resize_canvas()
        if plan is not None and self.isVisible():
            self.ensure_audio()

    def invalidate(self) -> None:
        self._revision += 1
        if self._cancellation:
            self._cancellation.cancel()
        self.player.stop()
        self.player.setSource(QUrl())
        self._audio = None
        self._loading = False
        self._plan = None
        self._session = None
        self.canvas.set_plan(None)
        self.play_button.setEnabled(False)
        self.status_label.setText("Prévia mono")

    def ensure_audio(self) -> None:
        if self._plan is None or self._session is None or self._audio or self._running:
            return
        plan, session = self._plan, self._session
        self._loading = True
        self._running = True
        self._cancellation = cancellation = CancellationToken()
        config = self._config.ffmpeg
        renderer = TrackAudioRenderer(
            FFmpegRunner(
                ffmpeg_path=Path(config.ffmpeg_path) if config.ffmpeg_path else None,
                ffprobe_path=Path(config.ffprobe_path) if config.ffprobe_path else None,
            ),
            self._cache_root,
        )
        job = PreviewJob(
            self._revision,
            lambda: build_preview_audio(
                plan,
                session,
                renderer,
                self._cache_root,
                cancellation,
                progress=lambda message: job.signals.progress.emit(job.revision, message),
            ),
        )
        job.signals.progress.connect(self._audio_progress)
        job.signals.finished.connect(self._audio_ready)
        job.signals.failed.connect(self._audio_failed)
        self._job = job
        self.status_label.setText(
            "Preparando waveform e áudio… · Verde manter / vermelho cortar / cinza desativar"
        )
        QThreadPool.globalInstance().start(job)

    def _audio_progress(self, revision: int, message: str) -> None:
        if revision == self._revision:
            self.status_label.setText(message)
            self.status_label.setToolTip(message)

    def _audio_ready(self, revision: int, result: PreviewAudio) -> None:
        self._running = False
        if revision != self._revision or self._plan is None:
            if self.isVisible():
                self.ensure_audio()
            return
        self._loading = False
        self._audio = result
        self.canvas.audio = result
        self.canvas.update()
        self.play_button.setEnabled(not self._plan.blocked and self._plan.stats.new_frames > 0)
        self.status_label.setText(
            "Prévia mono" + (" · Avisos (passe o mouse)" if result.warnings else "")
        )
        self.status_label.setToolTip(
            "Prévia mono das fontes, sem efeitos de mixagem do Resolve.\n"
            + "\n".join(result.warnings)
        )
        self._mode_changed()

    def _audio_failed(self, revision: int, message: str) -> None:
        self._running = False
        if revision != self._revision:
            if self.isVisible():
                self.ensure_audio()
            return
        if revision == self._revision:
            self._loading = False
            self.status_label.setText("Áudio indisponível: " + message)
            self.status_label.setToolTip(message)

    def _mode_changed(self, *_args: Any) -> None:
        if not self._audio:
            return
        self.play_button.setEnabled(
            self.mode_combo.currentIndex() == 0
            or (
                self._plan is not None
                and not self._plan.blocked
                and self._plan.stats.new_frames > 0
            )
        )
        frame = self.canvas.playhead
        self.player.pause()
        path = (
            self._audio.edited_path if self.mode_combo.currentIndex() else self._audio.original_path
        )
        self.player.setSource(QUrl.fromLocalFile(str(path)))
        self.seek(frame)

    def seek(self, frame: int) -> None:
        if self._plan is None:
            return
        plan = self._plan
        frame = max(plan.layout.start_frame, min(plan.layout.end_frame, frame))
        result = original_to_result(plan, frame) if self.mode_combo.currentIndex() else frame
        self._seek_ms = round((result - plan.layout.start_frame) * 1000 / plan.layout.fps)
        if self.mode_combo.currentIndex() and self._audio:
            rate = self._audio.tracks[0].sample_rate
            self._seek_ms = round(original_to_sample(plan, frame, rate) * 1000 / rate)
        self.player.setPosition(self._seek_ms)
        self._position_changed(self._seek_ms)

    def _media_status_changed(self, status: QMediaPlayer.MediaStatus) -> None:
        if status == QMediaPlayer.MediaStatus.LoadedMedia:
            self.player.setPosition(self._seek_ms)

    def _position_changed(self, milliseconds: int) -> None:
        if self._plan is None:
            return
        plan = self._plan
        frame = plan.layout.start_frame + round(milliseconds * plan.layout.fps / 1000)
        if self.mode_combo.currentIndex():
            original, result = result_to_original(plan, frame), frame
            if self._audio:
                rate = self._audio.tracks[0].sample_rate
                original = sample_to_original(plan, round(milliseconds * rate / 1000), rate)
        else:
            original, result = frame, original_to_result(plan, frame)
        self.canvas.set_playhead(original)
        self.clock_label.setText(
            f"{timeline_timecode(plan.layout, original)} · "
            f"Resultado {frames_to_clock(result - plan.layout.start_frame, plan.layout.fps)}"
        )
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.scroll_area.ensureVisible(
                round(self.canvas.x_at(original)),
                self.scroll_area.verticalScrollBar().value() + 20,
                50,
                0,
            )

    def _toggle_play(self) -> None:
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        elif self._audio and self.play_button.isEnabled():
            self.player.play()

    def _playback_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        self.play_button.setText(
            "Pause" if state == QMediaPlayer.PlaybackState.PlayingState else "Play"
        )

    def _playback_error(self, error: QMediaPlayer.Error, message: str) -> None:
        if error != QMediaPlayer.Error.NoError:
            self.status_label.setText("Falha na reprodução: " + message)

    def _resize_canvas(self, *_args: Any) -> None:
        width = max(100, self.scroll_area.viewport().width())
        self.canvas.resize(
            LEFT + (width - LEFT) * self.zoom_slider.value(), self.canvas.minimumHeight()
        )

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._resize_canvas()

    def showEvent(self, event: Any) -> None:
        super().showEvent(event)
        self._resize_canvas()
        self.ensure_audio()
