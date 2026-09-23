from typing import Optional

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QColor, QMouseEvent, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import QSlider, QWidget

from app_core.design_tokens import palette
from app_core.theme_engine import ThemeEngine


class GlassSlider(QSlider):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(Qt.Horizontal, parent)
        self.setMinimumHeight(24)

    def _is_dark(self) -> bool:
        return ThemeEngine._current_theme == "dark"

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        dark = self._is_dark()
        pal = palette(dark)

        track = QRectF(4, self.height() // 2 - 2, self.width() - 8, 4)
        path = QPainterPath()
        path.addRoundedRect(track, 2, 2)
        p.fillPath(path, QColor(0, 0, 0, 30) if not dark else QColor(255, 255, 255, 30))

        ratio = (self.value() - self.minimum()) / max(
            self.maximum() - self.minimum(), 1
        )
        filled = QRectF(track.x(), track.y(), track.width() * ratio, track.height())
        path2 = QPainterPath()
        path2.addRoundedRect(filled, 2, 2)
        p.fillPath(path2, QColor(pal.accent))

        handle_x = track.x() + track.width() * ratio
        handle_y = self.height() // 2
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(pal.surface_raised))
        p.drawEllipse(QPointF(handle_x, handle_y), 7, 7)
        p.setPen(QPen(QColor(pal.border), 1))
        p.drawEllipse(QPointF(handle_x, handle_y), 7, 7)
        p.end()
