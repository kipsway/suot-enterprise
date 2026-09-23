from typing import Optional

from PyQt5.QtCore import QRectF, Qt
from PyQt5.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import QComboBox, QStylePainter, QWidget

from app_core.design_tokens import RADIUS, palette
from app_core.theme_engine import ThemeEngine


class GlassComboBox(QComboBox):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(40)
        self.setAttribute(Qt.WA_StyledBackground, True)

    def _is_dark(self) -> bool:
        return ThemeEngine._current_theme == "dark"

    def paintEvent(self, event) -> None:
        p = QStylePainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        dark = self._is_dark()
        pal = palette(dark)
        r = int(RADIUS.md.replace("px", ""))
        rect = self.rect().adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(QRectF(rect), r, r)
        p.fillPath(path, QColor(pal.bg_secondary))
        p.setPen(QPen(QColor(pal.border), 1))
        p.drawPath(path)
        super().paintEvent(event)
