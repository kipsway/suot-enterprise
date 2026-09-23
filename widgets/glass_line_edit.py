from typing import Optional

from PyQt5.QtCore import QEvent, QRectF, Qt
from PyQt5.QtGui import QColor, QFocusEvent, QPainter, QPainterPath, QPen, QPaintEvent
from PyQt5.QtWidgets import QLineEdit, QWidget

from app_core.design_tokens import RADIUS, palette
from app_core.theme_engine import ThemeEngine


class GlassLineEdit(QLineEdit):
    def __init__(
        self, text: str = "", parent: Optional[QWidget] = None, placeholder: str = ""
    ) -> None:
        super().__init__(text, parent)
        self._focused = False
        self._has_error = False
        self.setMinimumHeight(40)
        if placeholder:
            self.setPlaceholderText(placeholder)
        self.setAttribute(Qt.WA_StyledBackground, True)

    def _is_dark(self) -> bool:
        return ThemeEngine._current_theme == "dark"

    def set_has_error(self, err: bool) -> None:
        self._has_error = err
        self.update()

    def focusInEvent(self, event: QFocusEvent) -> None:
        self._focused = True
        self.update()
        super().focusInEvent(event)

    def focusOutEvent(self, event: QFocusEvent) -> None:
        self._focused = False
        self.update()
        super().focusOutEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        dark = self._is_dark()
        pal = palette(dark)
        r = int(RADIUS.md.replace("px", ""))
        rect = self.rect().adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(QRectF(rect), r, r)

        bg = QColor(pal.bg_secondary) if not dark else QColor(pal.bg_secondary)
        if self._focused:
            bg = bg.lighter(105) if not dark else bg
        p.fillPath(path, bg)

        if self._has_error:
            p.setPen(QPen(QColor(pal.border_error), 1.5))
        elif self._focused:
            p.setPen(QPen(QColor(pal.border_focus), 1.5))
        else:
            p.setPen(QPen(QColor(pal.border), 1))
        p.drawPath(path)
        p.end()

        super().paintEvent(event)

    def setText(self, text: str) -> None:
        super().setText(text)
