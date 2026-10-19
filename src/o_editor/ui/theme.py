"""Pablo palette with print-zine typography, paper, ink and restrained distress."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QPen, QPolygon
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

PALETTE = {
    "background": "#272425",
    "surface": "#2B2B2B",
    "earth": "#4B372C",
    "sand": "#AF8E77",
    "green": "#1C5427",
    "red": "#B9322D",
    "paper": "#FCF5F1",
}

STYLESHEET = """
QMainWindow, QDialog { background: #272425;
    }
QWidget { background: #272425;
    color: #FCF5F1;
    font-family: "Segoe UI";
    font-size: 13px;
    }
QLabel { background: transparent; }
QWidget#sidebar { background: #242223;
    border-right: 1px solid #4B372C;
    }
QLabel[role="eyebrow"] { color: #AF8E77;
    font-size: 11px;
    font-weight: 700;
    }
QLabel[role="heading"] { font-size: 25px;
    font-weight: 700;
    }
QLabel[role="subheading"] { font-size: 17px;
    font-weight: 600;
    }
QLabel[role="muted"] { color: #D3C3B8;
    }
QLabel[role="notice"] { background: #4B372C;
    color: #FCF5F1;
    padding: 12px;
    border-left: 3px solid #AF8E77;
    }
QLabel[role="badge"] { background: #1C5427;
    color: #FCF5F1;
    padding: 6px 10px;
    font-size: 11px;
    font-weight: 700;
    }
QGroupBox { background: #2B2B2B;
    border: 1px solid #53483F;
    border-radius: 4px;
    margin-top: 14px;
    padding: 16px 12px 10px;
    font-weight: 600;
    }
QGroupBox::title { subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #D3B49C;
    }
QPushButton { background: #353132;
    border: 1px solid #65564B;
    border-radius: 4px;
    padding: 9px 13px;
    font-weight: 600;
    }
QPushButton:hover { background: #4B372C;
    border-color: #AF8E77;
    }
QSlider::groove:horizontal { background: #211F20; height: 5px; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #AF8E77; border-radius: 2px; }
QSlider::handle:horizontal { background: #AF8E77; width: 13px;
    margin: -5px 0; border-radius: 6px; }
QSlider::handle:horizontal:hover { background: #FCF5F1; }
QSlider::groove:horizontal:disabled, QSlider::sub-page:horizontal:disabled {
    background: #494142; }
QSlider::handle:horizontal:disabled { background: #65564B; }
QPushButton:pressed { background: #272425;
    }
QPushButton:focus, QComboBox:focus, QLineEdit:focus, QSpinBox:focus,
QTableView:focus { border: 2px solid #AF8E77;
    }
QPushButton[role="unit"]:checked { background: #4B372C; border-color: #AF8E77; }
QPushButton[role="primary"] { background: #1C5427;
    border: 1px solid #498653;
    color: #FCF5F1;
    }
QPushButton[role="primary"]:hover { background: #286934;
    }
QPushButton[role="danger"] { background: #B9322D;
    border-color: #D5665E;
    }
QPushButton:disabled { background: #2B292A;
    border-color: #494142;
    color: #958981;
    }
QPushButton[role="nav"] { text-align: left;
    border: 0;
    border-left: 3px solid transparent;
    border-radius: 0;
    padding: 14px 12px;
    font-weight: 500;
    color: #C9B9AD;
    }
QPushButton[role="nav"]:checked { background: #34302D;
    border-left: 3px solid #AF8E77;
    color: #FCF5F1;
    font-weight: 700;
    }
QLineEdit, QComboBox, QSpinBox { background: #211F20;
    border: 1px solid #65564B;
    border-radius: 3px;
    padding: 6px 8px;
    min-height: 20px;
    selection-background-color: #1C5427;
    }
QComboBox::drop-down { border: 0;
    width: 24px;
    }
QComboBox::down-arrow { image: url("DOWN_PATH"); width: 14px; height: 14px; }
QSpinBox::up-button, QSpinBox::down-button { width: 20px; background: #353132; }
QSpinBox::up-arrow { image: url("UP_PATH"); width: 12px; height: 10px; }
QSpinBox::down-arrow { image: url("DOWN_PATH"); width: 12px; height: 10px; }
QComboBox QAbstractItemView { background: #2B2B2B;
    selection-background-color: #1C5427;
    }
QTableView, QTextEdit { background: #242223;
    alternate-background-color: #2B2829;
    border: 1px solid #53483F;
    border-radius: 4px;
    gridline-color: #3C3633;
    selection-background-color: #1C5427;
    selection-color: #FCF5F1;
    }
QTableView { padding: 2px;
    }
QHeaderView::section { background: #3A302B;
    color: #E4D2C5;
    border: 0;
    border-bottom: 1px solid #65564B;
    padding: 9px 8px;
    font-size: 12px;
    font-weight: 600;
    }
QCheckBox { spacing: 8px;
    padding: 4px 0;
    }
QCheckBox::indicator { width: 17px;
    height: 17px;
    border: 1px solid #AF8E77;
    border-radius: 3px;
    background: #211F20;
    }
QCheckBox::indicator:checked { background: #1C5427;
    border: 2px solid #AF8E77;
    image: url("CHECKMARK_PATH");
    }
QProgressBar { background: #211F20;
    border: 0;
    border-radius: 3px;
    color: #E4D2C5;
    text-align: center;
    max-height: 16px;
    min-height: 10px;
    }
QProgressBar::chunk { background: #1C5427;
    border-radius: 3px;
    }
QScrollArea { background: transparent;
    border: 0;
    }
QScrollBar:vertical { background: #272425;
    width: 10px;
    margin: 0;
    }
QScrollBar::handle:vertical { background: #65564B;
    min-height: 26px;
    border-radius: 4px;
    }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0;
    }
QScrollBar:horizontal { background: #272425;
    height: 10px;
    }
QScrollBar::handle:horizontal { background: #65564B;
    min-width: 26px;
    }
QSplitter::handle { background: #4B372C;
    }
QStatusBar { background: #242223;
    color: #D3C3B8;
    font-size: 11px;
    }
QToolTip { background: #FCF5F1;
    color: #272425;
    border: 1px solid #AF8E77;
    padding: 6px;
    }
"""
# Printed-zine surfaces use local fonts; data/editing surfaces remain untextured.
STYLESHEET += """
QLabel[role="brand"] { color: #272425; font-family: "Impact";
    font-size: 31px; font-weight: 900; }
QLabel[role="brandMeta"] { color: #4B372C; font-family: "Consolas";
    font-size: 11px; font-weight: 700; }
QLabel[role="heading"] { font-family: "Arial Narrow"; font-weight: 900;
    font-size: 28px; }
QLabel[role="eyebrow"] { font-family: "Consolas"; color: #D3B49C;
    font-weight: 700; }
QGroupBox { border-radius: 0; border: 1px solid #65564B;
    border-top: 3px solid #AF8E77; }
QGroupBox::title { font-family: "Consolas"; color: #FCF5F1; }
QPushButton { border-radius: 0; border: 2px solid #65564B;
    font-family: "Arial Narrow"; font-weight: 700; }
QPushButton[role="primary"] { border: 2px solid #498653; }
QPushButton[role="danger"] { border: 2px solid #D5665E; }
QPushButton[role="nav"] { font-family: "Consolas"; border-bottom: 1px solid #4B372C; }
QPushButton[role="nav"]:checked { background: #FCF5F1; color: #272425;
    border-left: 5px solid #B9322D; font-weight: 900; }
QPushButton:focus, QComboBox:focus, QLineEdit:focus, QSpinBox:focus,
QTableView:focus { border: 2px dashed #AF8E77; }
QHeaderView::section { background: #FCF5F1; color: #272425;
    border-bottom: 3px solid #B9322D; font-family: "Consolas"; }
QTextEdit, QTableView, QLineEdit, QComboBox, QSpinBox { border-radius: 0; }
QLabel[role="badge"] { font-family: "Consolas"; border: 1px solid #498653; }
"""


STYLESHEET += """
QWidget#workflowBar { background: #242223; border-bottom: 1px solid #4B372C; }
QPushButton[role="nav"] { text-align: center; font-family: "Segoe UI"; font-size: 12px;
    padding: 10px 8px; border: 0; border-bottom: 3px solid transparent; }
QPushButton[role="nav"]:checked { background: #FCF5F1; color: #272425;
    border: 0; border-bottom: 3px solid #B9322D; }
QTabWidget::pane { border: 1px solid #65564B; background: #2B2B2B; }
QTabBar::tab { background: #353132; color: #D3C3B8; padding: 7px 15px;
    border-bottom: 2px solid transparent; }
QTabBar::tab:selected { background: #4B372C; color: #FCF5F1;
    border-bottom: 2px solid #AF8E77; }
"""


for token, filename in (
    ("CHECKMARK_PATH", "check.svg"),
    ("DOWN_PATH", "chevron-down.svg"),
    ("UP_PATH", "chevron-up.svg"),
):
    STYLESHEET = STYLESHEET.replace(token, (Path(__file__).parent / "assets" / filename).as_posix())


def label(text: str, role: str = "muted") -> QLabel:
    """Create a wrapping label with a shared visual role."""
    widget = QLabel(text)
    widget.setProperty("role", role)
    widget.setWordWrap(True)
    return widget


class BrandHeader(QWidget):
    """Grain stays in an empty band, away from text and editing controls."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(64)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 4, 20, 12)
        title = label("Editor Do Escobar", "brand")
        title.setObjectName("brandTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(PALETTE["paper"]))
        # A deterministic torn edge and misregistered print line; no raster assets.
        edge = [QPoint(0, self.height())]
        for x in range(0, self.width() + 20, 16):
            edge.append(QPoint(x, self.height() - 6 - (x // 16 % 3) * 2))
        edge.append(QPoint(self.width(), self.height()))
        painter.setPen(QPen(QColor(PALETTE["background"]), 1))
        painter.setBrush(QColor(PALETTE["background"]))
        painter.drawPolygon(QPolygon(edge))
        painter.fillRect(0, self.height() - 13, min(140, self.width()), 3, QColor(PALETTE["red"]))
        painter.setPen(QPen(QColor(75, 55, 44, 24), 1))
        for index in range(180):
            x = (index * 67) % max(1, self.width())
            y = self.height() - 22 + (index * 7 % 8)
            painter.drawPoint(x, y)
        painter.end()
