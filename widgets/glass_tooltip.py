from typing import Optional

from PyQt5.QtCore import QPropertyAnimation, QRectF, Qt, QTimer
from PyQt5.QtGui import QColor, QFontMetrics, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from app_core.animation_manager import fade_in
from app_core.design_tokens import RADIUS, palette
from app_core.theme_engine import ThemeEngine


class GlassTooltip(QFrame):
    _active: Optional["GlassTooltip"] = None

    def __init__(self, text: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        self._label = QLabel(text)
        self._label.setWordWrap(True)
        self._label.setMaximumWidth(280)
        layout.addWidget(self._label)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fade_out)

    def _is_dark(self) -> bool:
        return ThemeEngine._current_theme == "dark"

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        dark = self._is_dark()
        pal = palette(dark)
        r = int(RADIUS.md.replace("px", ""))
        rect = self.rect()
        path = QPainterPath()
        path.addRoundedRect(QRectF(rect), r, r)
        bg = QColor(pal.bg_secondary)
        p.fillPath(path, bg)
        p.setPen(QPen(QColor(pal.border), 0.5))
        p.drawPath(path)
        p.setPen(QColor(pal.text_primary))
        font = self.font()
        font.setPointSize(11)
        p.setFont(font)
        p.drawText(
            rect.adjusted(12, 8, -12, -8),
            Qt.AlignLeft | Qt.AlignVCenter,
            self._label.text(),
        )
        p.end()

    def show_at(self, pos, duration: int = 3000) -> None:
        self.adjustSize()
        self.move(pos)
        self.show()
        fade_in(self, 150)
        self._timer.start(duration)

    def _fade_out(self) -> None:
        from app_core.animation_manager import fade_out

        anim = fade_out(self, 150, self.close)
        anim.start()

    @classmethod
    def show_tooltip(cls, text: str, pos, duration: int = 3000) -> None:
        if cls._active:
            cls._active.close()
        cls._active = cls(text)
        cls._active.show_at(pos, duration)
