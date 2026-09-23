from PyQt5.QtCore import QPropertyAnimation, QRect, Qt, QTimer
from PyQt5.QtGui import QColor, QLinearGradient, QPainter, QPen
from PyQt5.QtWidgets import QWidget


class SkeletonWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._offset = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(30)

    def _tick(self):
        self._offset += 0.03
        if self._offset > 1.0:
            self._offset = 0.0
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        dark = self._is_dark()

        bg = QColor(30, 30, 35) if dark else QColor(240, 240, 245)
        shimmer_color = QColor(50, 50, 58) if dark else QColor(255, 255, 255)

        painter.fillRect(self.rect(), bg)

        line_h = 14
        gap = 10
        margin = 20
        pad = 12
        lines = max(1, (h - margin) // (line_h + gap))
        for i in range(lines):
            y = margin + i * (line_h + gap)
            lw = w - margin * 2 - pad * (i % 3)
            x = margin + pad * (i % 3) // 2
            rect = QRect(int(x), y, int(lw), line_h)

            grad = QLinearGradient(rect.left(), 0, rect.right(), 0)
            pos = self._offset
            grad.setColorAt(max(0.0, pos - 0.3), bg)
            grad.setColorAt(pos, shimmer_color)
            grad.setColorAt(min(1.0, pos + 0.3), bg)
            painter.fillRect(rect, grad)

            painter.setPen(QPen(QColor(0, 0, 0, 0)))
            painter.drawRoundedRect(rect, 4, 4)

        painter.end()

    def _is_dark(self):
        from app_core.theme_engine import ThemeEngine

        return ThemeEngine._current_theme == "dark"
