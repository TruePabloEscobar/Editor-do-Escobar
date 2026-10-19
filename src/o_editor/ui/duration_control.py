"""Synchronized duration knob/editor; milliseconds remain canonical."""

from __future__ import annotations

import math
import re

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPaintEvent, QPen, QValidator
from PySide6.QtWidgets import QDial, QSpinBox, QVBoxLayout, QWidget


class DurationKnob(QDial):
    """Vertical drag, keyboard/wheel input and a double-click reset."""

    reset_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setFixedSize(68, 68)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._drag_start: QPoint | None = None
        self._drag_value = 0
        self.setToolTip("Arraste para cima/baixo. Shift: ajuste fino. Duplo clique: valor padrão.")

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.setFocus()
            self._drag_start = event.position().toPoint()
            self._drag_value = self.value()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_start is not None:
            delta = self._drag_start.y() - event.position().y()
            fine = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            step = (
                self.singleStep()
                if fine
                else max(self.singleStep(), (self.maximum() - self.minimum()) / 180)
            )
            self.setValue(round(self._drag_value + delta * step))
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_start = None
        event.accept()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.reset_requested.emit()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.isEnabled():
            painter.setOpacity(0.4)
        arc = QRectF(7, 7, 54, 54)
        fraction = (self.value() - self.minimum()) / max(1, self.maximum() - self.minimum())
        painter.setPen(QPen(QColor("#494142"), 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawArc(arc, 225 * 16, -270 * 16)
        painter.setPen(QPen(QColor("#AF8E77"), 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawArc(arc, 225 * 16, round(-270 * 16 * fraction))
        painter.setBrush(QColor("#353132"))
        painter.setPen(QPen(QColor("#65564B"), 1))
        painter.drawEllipse(QRectF(15, 15, 38, 38))
        angle = math.radians(225 - 270 * fraction)
        painter.setPen(QPen(QColor("#FCF5F1"), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(
            QPointF(34 + 8 * math.cos(angle), 34 - 8 * math.sin(angle)),
            QPointF(34 + 16 * math.cos(angle), 34 - 16 * math.sin(angle)),
        )
        if self.hasFocus():
            painter.setPen(QPen(QColor("#AF8E77"), 1, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QRectF(2, 2, 64, 64))


class DurationSpinBox(QSpinBox):
    def __init__(self, minimum: int, maximum: int, value: int) -> None:
        self._frames = False
        self._fps: float | None = None
        super().__init__()
        self.setRange(minimum, maximum)
        self.setValue(value)
        self.setSingleStep(10)
        self.setKeyboardTracking(False)
        self.setMinimumWidth(112)
        self.setMaximumWidth(130)
        self.setToolTip(
            "Digite a duração: por exemplo, 250 ms ou 1,2 s. Em Frames, digite quadros inteiros."
        )

    def set_display(self, frames: bool, fps: float | None) -> None:
        self.interpretText()
        self._fps = fps if fps and math.isfinite(fps) and fps > 0 else None
        self._frames = frames and self._fps is not None
        self.lineEdit().setText(self.textFromValue(self.value()))

    def textFromValue(self, value: int) -> str:
        if self._frames and self._fps:
            return f"{round(value * self._fps / 1000)} frames"
        if value < 1000:
            return f"{value} ms"
        seconds = f"{value / 1000:.3f}".rstrip("0").rstrip(".").replace(".", ",")
        return f"{seconds} s"

    def valueFromText(self, text: str) -> int:
        if text.strip() == self.textFromValue(self.value()):
            return self.value()
        match = re.fullmatch(r"\s*(\d+(?:[.,]\d+)?)\s*(ms|s|frames?|quadros?)?\s*", text)
        if not match:
            return self.value()
        value = float(match[1].replace(",", "."))
        if not math.isfinite(value):
            return self.maximum() + 1
        unit = match[2]
        if self._frames and self._fps:
            return round(value * 1000 / self._fps)
        seconds = unit == "s" or (unit is None and self.value() >= 1000)
        return round(value * 1000 if seconds else value)

    def validate(self, text: str, pos: int) -> tuple[QValidator.State, str, int]:
        pattern = (
            r"\s*\d+\s*(frames?|quadros?)?\s*"
            if self._frames
            else r"\s*\d+(?:[.,]\d+)?\s*(ms|s)?\s*"
        )
        if re.fullmatch(pattern, text):
            value = self.valueFromText(text)
            state = (
                QValidator.State.Acceptable
                if self.minimum() <= value <= self.maximum()
                else QValidator.State.Intermediate
            )
        elif not text.strip() or re.fullmatch(r"\s*\d+[.,]\s*", text):
            state = QValidator.State.Intermediate
        else:
            state = QValidator.State.Invalid
        return state, text, pos

    def stepBy(self, steps: int) -> None:
        if self._frames and self._fps:
            frame = round(self.value() * self._fps / 1000) + steps
            self.setValue(round(frame * 1000 / self._fps))
        else:
            super().stepBy(steps)


class DurationControl(QWidget):
    valueChanged = Signal(int)

    def __init__(self, minimum: int, maximum: int, value: int, name: str) -> None:
        super().__init__()
        self._frames = False
        self._fps: float | None = None
        self.editor = DurationSpinBox(minimum, maximum, value)
        self.knob = DurationKnob()
        self.slider = self.knob  # Existing automation and control contracts remain valid.
        self.slider.setAccessibleName(name)
        self.editor.setAccessibleName(f"{name}: valor")
        self.editor.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row = QVBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(2)
        row.addWidget(self.knob, 0, Qt.AlignmentFlag.AlignHCenter)
        row.addWidget(self.editor, 0, Qt.AlignmentFlag.AlignHCenter)
        self.knob.reset_requested.connect(lambda: self.setValue(value))
        self.editor.valueChanged.connect(self._editor_changed)
        self.slider.valueChanged.connect(self._slider_changed)
        self._sync_slider()

    def value(self) -> int:
        return self.editor.value()

    def setValue(self, value: int) -> None:
        self.editor.setValue(value)

    def set_display(self, frames: bool, fps: float | None) -> None:
        self.editor.set_display(frames, fps)
        self._fps = self.editor._fps
        self._frames = self.editor._frames
        self._sync_slider()

    def _sync_slider(self) -> None:
        def display(value: int) -> int:
            return round(value * self._fps / 1000) if self._frames and self._fps else value

        self.slider.blockSignals(True)
        self.slider.setRange(display(self.editor.minimum()), display(self.editor.maximum()))
        self.slider.setSingleStep(1 if self._frames else 10)
        self.slider.setPageStep(10 if self._frames else 100)
        self.slider.setNotchTarget(8)
        self.slider.setValue(display(self.value()))
        self.slider.blockSignals(False)

    def _editor_changed(self, value: int) -> None:
        self._sync_slider()
        self.valueChanged.emit(value)

    def _slider_changed(self, value: int) -> None:
        milliseconds = round(value * 1000 / self._fps) if self._frames and self._fps else value
        self.setValue(milliseconds)
