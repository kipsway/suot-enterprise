from typing import Callable, Optional

from PyQt5.QtCore import QEvent, QPoint, QPropertyAnimation, QRect, Qt, QTimer
from PyQt5.QtGui import QColor, QEnterEvent, QMouseEvent, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import QPushButton, QSizePolicy, QWidget
from PyQt5.QtCore import QRectF

from app_core.design_tokens import ANIM, RADIUS, palette
from app_core.theme_engine import ThemeEngine


class GlassButton(QPushButton):
    def __init__(
        self,
        text: str = "",
        parent: Optional[QWidget] = None,
        variant: str = "filled",
        icon: str = "",
    ) -> None:
        super().__init__(text, parent)
        self._variant = variant
        self._icon_text = icon
        self._hovered = False
        self._pressed = False
        self._ripple_pos: QPoint = QPoint()
        self._ripple_progress = 0.0
        self._ripple_anim: Optional[QPropertyAnimation] = None

        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(36)
        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)

        self.setAttribute(Qt.WA_Hover, True)
        self.installEventFilter(self)

    def set_variant(self, v: str) -> None:
        self._variant = v
        self.update()

    def _is_dark(self) -> bool:
        return ThemeEngine._current_theme == "dark"

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)

        dark = self._is_dark()
        pal = palette(dark)
        r = int(RADIUS.md.replace("px", ""))
        rect = self.rect()
        path = QPainterPath()
        path.addRoundedRect(QRectF(rect), r, r)

        if self._variant == "filled":
            bg = QColor(pal.accent)
            if self._pressed:
                bg = QColor(
                    pal.accent_pressed if hasattr(pal, "accent_pressed") else "#0055B3"
                )
            elif self._hovered:
                bg = QColor(
                    pal.accent_hover if hasattr(pal, "accent_hover") else "#0066D6"
                )
            p.fillPath(path, bg)
            text_color = QColor(pal.text_inverse)

        elif self._variant == "outlined":
            p.fillPath(path, QColor(0, 0, 0, 0))
            border_c = QColor(pal.accent) if self._hovered else QColor(pal.border)
            p.setPen(QPen(border_c, 1.5))
            p.drawPath(path)
            text_color = QColor(pal.accent)

        elif self._variant == "ghost":
            if self._hovered:
                bg = QColor(0, 0, 0, 15) if not dark else QColor(255, 255, 255, 15)
                p.fillPath(path, bg)
            text_color = QColor(pal.text_primary)

        else:
            p.fillPath(path, QColor(pal.bg_secondary))
            if self._hovered:
                p.fillPath(path, QColor(0, 0, 0, 10))
            text_color = QColor(pal.text_primary)

        if self._ripple_progress > 0 and not self._ripple_pos.isNull():
            ripple_r = max(rect.width(), rect.height()) * self._ripple_progress
            ripple_path = QPainterPath()
            ripple_path.addRoundedRect(QRectF(rect), r, r)
            p.setClipPath(ripple_path)
            ripple_color = QColor(255, 255, 255, int(60 * (1 - self._ripple_progress)))
            p.setPen(Qt.NoPen)
            p.setBrush(ripple_color)
            p.drawEllipse(self._ripple_pos, int(ripple_r), int(ripple_r))
            p.setClipping(False)

        p.setPen(text_color)
        font = self.font()
        font.setPointSize(13)
        p.setFont(font)

        txt = self.text()
        if self._icon_text:
            txt = self._icon_text + " " + txt

        p.drawText(rect.adjusted(16, 0, -16, 0), Qt.AlignVCenter | Qt.AlignLeft, txt)
        p.end()

    def eventFilter(self, obj, event) -> bool:
        if obj is self:
            if event.type() == QEvent.HoverEnter:
                self._hovered = True
                self.update()
            elif event.type() == QEvent.HoverLeave:
                self._hovered = False
                self._pressed = False
                self.update()
            elif event.type() == QEvent.MouseButtonPress:
                self._pressed = True
                me = event
                self._ripple_pos = me.pos()
                self._start_ripple()
                self.update()
            elif event.type() == QEvent.MouseButtonRelease:
                self._pressed = False
                self.update()
        return super().eventFilter(obj, event)

    def _start_ripple(self) -> None:
        self._ripple_progress = 0.0
        self._ripple_anim = QPropertyAnimation(self, b"rippleProgress")
        self._ripple_anim.setDuration(300)
        self._ripple_anim.setStartValue(0.0)
        self._ripple_anim.setEndValue(1.0)
        self._ripple_anim.finished.connect(
            lambda: setattr(self, "_ripple_progress", 0.0)
        )
        self._ripple_anim.start()

    def get_rippleProgress(self) -> float:
        return self._ripple_progress

    def set_rippleProgress(self, v: float) -> None:
        self._ripple_progress = v
        self.update()

    rippleProgress = property(get_rippleProgress, set_rippleProgress)
