from typing import Optional

from PyQt5.QtCore import QPointF, QPropertyAnimation, QRectF, Qt
from PyQt5.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import QCheckBox, QWidget

from app_core.design_tokens import RADIUS, palette
from app_core.theme_engine import ThemeEngine


class GlassCheckBox(QCheckBox):
    def __init__(self, text: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(text, parent)

    def _is_dark(self) -> bool:
        return ThemeEngine._current_theme == "dark"

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        dark = self._is_dark()
        pal = palette(dark)
        r = 4
        cb_size = 18
        y = (self.height() - cb_size) // 2
        rect = QRectF(4, y, cb_size, cb_size)
        path = QPainterPath()
        path.addRoundedRect(rect, r, r)

        if self.isChecked():
            p.fillPath(path, QColor(pal.accent))
            p.setPen(QPen(QColor(pal.text_inverse), 2))
            p.drawLine(
                QPointF(rect.left() + 5, rect.center().y()),
                QPointF(rect.center().x() - 1, rect.bottom() - 4),
            )
            p.drawLine(
                QPointF(rect.center().x() - 1, rect.bottom() - 4),
                QPointF(rect.right() - 4, rect.top() + 4),
            )
        else:
            p.fillPath(path, QColor(pal.bg_secondary))
            p.setPen(QPen(QColor(pal.border), 1))
            p.drawPath(path)

        p.setPen(QColor(pal.text_primary))
        p.drawText(
            QRectF(rect.right() + 8, 0, self.width() - rect.right() - 8, self.height()),
            Qt.AlignVCenter | Qt.AlignLeft,
            self.text(),
        )
        p.end()
