from PyQt5.QtCore import QRectF, Qt, QTimer
from PyQt5.QtGui import QColor, QPainter, QPainterPath
from PyQt5.QtWidgets import QScrollBar

from app_core.design_tokens import palette
from app_core.theme_engine import ThemeEngine


def apply_glass_scrollbars(table) -> None:
    """Replace scrollbars on a QTableWidget or QAbstractScrollArea with GlassScrollBar."""
    table.setVerticalScrollBar(GlassScrollBar())
    table.setHorizontalScrollBar(GlassScrollBar())


class GlassScrollBar(QScrollBar):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(
            "QScrollBar:vertical { width: 6px; }"
            "QScrollBar:horizontal { height: 6px; }"
            "QScrollBar::handle:vertical, QScrollBar::handle:horizontal { background: transparent; border-radius: 3px; }"
            "QScrollBar::add-line, QScrollBar::sub-line { height: 0; }"
            "QScrollBar::add-page, QScrollBar::sub-page { background: none; }"
        )

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        dark = ThemeEngine._current_theme == "dark"
        pal = palette(dark)

        groove = self.rect()
        if self.orientation() == Qt.Vertical:
            groove.adjust(0, 2, 0, -2)
        else:
            groove.adjust(2, 0, -2, 0)

        path = QPainterPath()
        path.addRoundedRect(QRectF(groove), 3, 3)
        p.fillPath(path, QColor(0, 0, 0, 20) if not dark else QColor(255, 255, 255, 20))

        handle_size = self.pageStep()
        max_val = max(self.maximum() - self.minimum(), 1)
        ratio = min(1.0, handle_size / (handle_size + max_val))
        handle_len = max(
            int(groove.height() * ratio)
            if self.orientation() == Qt.Vertical
            else int(groove.width() * ratio),
            20,
        )

        if self.orientation() == Qt.Vertical:
            total = groove.height() - handle_len
            pos = int((self.sliderPosition() / max_val) * total) if max_val > 0 else 0
            handle_rect = QRectF(
                groove.x(), groove.y() + pos, groove.width(), handle_len
            )
        else:
            total = groove.width() - handle_len
            pos = int((self.sliderPosition() / max_val) * total) if max_val > 0 else 0
            handle_rect = QRectF(
                groove.x() + pos, groove.y(), handle_len, groove.height()
            )

        path2 = QPainterPath()
        path2.addRoundedRect(handle_rect, 3, 3)
        p.fillPath(path2, QColor(pal.scrollbar))
        p.end()
