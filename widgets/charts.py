import math
from typing import Any, Dict, List, Optional, Tuple

from PyQt5.QtCore import Qt, QRect, QPointF
from PyQt5.QtGui import (QFont, QColor, QPainter, QPen, QBrush,
                         QFontMetrics, QLinearGradient, QPolygonF)
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel

from app_core.theme_engine import ThemeEngine
from app_core.i18n import I18n


CHART_COLORS = [
    "#2196F3", "#E74C3C", "#27AE60", "#F39C12", "#9C27B0",
    "#00BCD4", "#FF5722", "#795548", "#607D8B", "#4CAF50",
    "#FF9800", "#3F51B5", "#E91E63", "#009688", "#CDDC39",
]


class BarChart(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._data: List[Tuple[str, float]] = []
        self._title: str = ""
        self._bar_color: str = "#2196F3"
        self.setMinimumHeight(200)

    def set_data(self, data: List[Tuple[str, float]], title: str = "",
                 color: str = "#2196F3") -> None:
        self._data = data
        self._title = title
        self._bar_color = color
        self.update()

    def paintEvent(self, event: Any) -> None:
        if not self._data:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        w = self.width()
        h = self.height()
        is_dark = ThemeEngine._current_theme == "dark"
        text_color = QColor("#E0E0E8" if is_dark else "#2C3E50")
        grid_color = QColor("#444466" if is_dark else "#E8ECF1")

        margin_left = 80
        margin_right = 20
        margin_top = 40 if self._title else 16
        margin_bottom = 60

        chart_w = w - margin_left - margin_right
        chart_h = h - margin_top - margin_bottom

        if chart_w < 20 or chart_h < 20:
            painter.end()
            return

        # Title
        if self._title:
            font_t = QFont("Segoe UI", 11, QFont.Bold)
            painter.setFont(font_t)
            painter.setPen(text_color)
            painter.drawText(QRect(0, 4, w, 28), Qt.AlignCenter, self._title)

        # Grid lines
        max_val = max(v for _, v in self._data) if self._data else 1
        if max_val == 0:
            max_val = 1
        steps = 4
        font_s = QFont("Segoe UI", 8)
        painter.setFont(font_s)
        for i in range(steps + 1):
            y = margin_top + chart_h - (chart_h * i // steps)
            painter.setPen(grid_color)
            painter.drawLine(margin_left, int(y), w - margin_right, int(y))
            val = max_val * i / steps
            painter.setPen(text_color)
            text = f"{val:.0f}" if val >= 1 else f"{val:.1f}"
            painter.drawText(QRect(0, int(y) - 10, margin_left - 8, 20),
                             Qt.AlignRight | Qt.AlignVCenter, text)

        # Bars
        bar_count = len(self._data)
        total_width = chart_w / bar_count if bar_count > 0 else chart_w
        bar_width = max(8, total_width * 0.6)
        spacing = total_width * 0.4

        bar_color = QColor(self._bar_color)
        for i, (label, value) in enumerate(self._data):
            x = margin_left + i * total_width + spacing / 2
            bar_h = (value / max_val) * chart_h if max_val > 0 else 0
            y = margin_top + chart_h - bar_h

            if bar_h > 0:
                gradient = QLinearGradient(x, y, x, margin_top + chart_h)
                gradient.setColorAt(0.0, bar_color.lighter(120))
                gradient.setColorAt(1.0, bar_color)
                painter.setBrush(QBrush(gradient))
                painter.setPen(QPen(bar_color.darker(110), 1))
                painter.drawRoundedRect(QRect(int(x), int(y),
                                               int(bar_width), int(bar_h)),
                                        3, 3)

            # Label
            painter.setFont(font_s)
            painter.setPen(text_color)
            label_rect = QRect(int(x) - 10, margin_top + chart_h + 4,
                               int(bar_width) + 20, 40)
            painter.drawText(label_rect, Qt.AlignHCenter | Qt.AlignTop,
                             label, QRect(1, 1, 1, 1) if len(label) > 10 else None)

        painter.end()


class PieChart(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._data: List[Tuple[str, float]] = []
        self._title: str = ""
        self._donut: bool = True
        self.setMinimumHeight(200)

    def set_data(self, data: List[Tuple[str, float]], title: str = "",
                 donut: bool = True) -> None:
        self._data = data
        self._title = title
        self._donut = donut
        self.update()

    def paintEvent(self, event: Any) -> None:
        if not self._data:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        w = self.width()
        h = self.height()
        is_dark = ThemeEngine._current_theme == "dark"
        text_color = QColor("#E0E0E8" if is_dark else "#2C3E50")

        total = sum(v for _, v in self._data)
        if total == 0:
            painter.end()
            return

        # Title
        if self._title:
            font_t = QFont("Segoe UI", 11, QFont.Bold)
            painter.setFont(font_t)
            painter.setPen(text_color)
            painter.drawText(QRect(0, 4, w, 24), Qt.AlignCenter, self._title)

        # Pie/donut
        cx = int(w * 0.35)
        cy = int(h * 0.52)
        radius = int(min(w, h) * 0.30)
        inner_r = int(radius * 0.55) if self._donut else 0

        start_angle = 90 * 16
        for i, (label, value) in enumerate(self._data):
            span = int((value / total) * 360 * 16)
            color = QColor(CHART_COLORS[i % len(CHART_COLORS)])
            painter.setBrush(color)
            painter.setPen(QPen(QColor("#FFFFFF" if is_dark else "#FFFFFF"), 1))
            painter.drawPie(cx - radius, cy - radius, radius * 2, radius * 2,
                            start_angle, span)
            if self._donut:
                painter.setBrush(QColor("#1E1E2E" if is_dark else "#FFFFFF"))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(cx - inner_r, cy - inner_r,
                                    inner_r * 2, inner_r * 2)
            start_angle += span

        # Legend
        legend_x = int(w * 0.68)
        legend_y = int(h * 0.15)
        font_l = QFont("Segoe UI", 9)
        painter.setFont(font_l)
        for i, (label, value) in enumerate(self._data):
            y = legend_y + i * 24
            color = QColor(CHART_COLORS[i % len(CHART_COLORS)])
            painter.setBrush(color)
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(legend_x, y, 12, 12, 2, 2)
            pct = value / total * 100
            painter.setPen(text_color)
            painter.drawText(legend_x + 18, y - 2, 140, 16,
                             Qt.AlignLeft | Qt.AlignVCenter,
                             f"{label} ({pct:.1f}%)")

        painter.end()


class TrendChart(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._points: List[Tuple[str, float]] = []
        self._title: str = ""
        self._line_color: str = "#2196F3"
        self._fill_color: str = "#2196F3"
        self.setMinimumHeight(200)

    def set_data(self, points: List[Tuple[str, float]], title: str = "",
                 color: str = "#2196F3") -> None:
        self._points = points
        self._title = title
        self._line_color = color
        c = QColor(color)
        c.setAlpha(30)
        self._fill_color = c.name(QColor.HexArgb)
        self.update()

    def paintEvent(self, event: Any) -> None:
        if len(self._points) < 2:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        w = self.width()
        h = self.height()
        is_dark = ThemeEngine._current_theme == "dark"
        text_color = QColor("#E0E0E8" if is_dark else "#2C3E50")
        grid_color = QColor("#444466" if is_dark else "#E8ECF1")

        margin_left = 60
        margin_right = 20
        margin_top = 40 if self._title else 16
        margin_bottom = 50

        chart_w = w - margin_left - margin_right
        chart_h = h - margin_top - margin_bottom

        if chart_w < 20 or chart_h < 20:
            painter.end()
            return

        if self._title:
            font_t = QFont("Segoe UI", 11, QFont.Bold)
            painter.setFont(font_t)
            painter.setPen(text_color)
            painter.drawText(QRect(0, 4, w, 24), Qt.AlignCenter, self._title)

        values = [v for _, v in self._points]
        min_val = min(values)
        max_val = max(values)
        if max_val == min_val:
            max_val = min_val + 1
        val_range = max_val - min_val
        n = len(self._points)

        # Grid
        steps = 4
        font_s = QFont("Segoe UI", 8)
        painter.setFont(font_s)
        for i in range(steps + 1):
            y = margin_top + chart_h - (chart_h * i // steps)
            painter.setPen(grid_color)
            painter.drawLine(margin_left, int(y), w - margin_right, int(y))
            val = min_val + val_range * i / steps
            painter.setPen(text_color)
            painter.drawText(QRect(0, int(y) - 10, margin_left - 8, 20),
                             Qt.AlignRight | Qt.AlignVCenter, f"{val:.0f}")

        # Build polygon
        line_color = QColor(self._line_color)
        fill_c = QColor(self._fill_color)

        # Draw line
        pen = QPen(line_color, 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)
        first = True
        for i, (_, val) in enumerate(self._points):
            x = margin_left + chart_w * i / (n - 1)
            y = margin_top + chart_h - ((val - min_val) / val_range) * chart_h
            if first:
                painter.moveTo(int(x), int(y))
                first = False
            else:
                painter.lineTo(int(x), int(y))

        # Fill under curve
        fill_poly = QPolygonF()
        fill_poly.append(QPointF(margin_left, margin_top + chart_h))
        for i, (_, val) in enumerate(self._points):
            x = margin_left + chart_w * i / (n - 1)
            y = margin_top + chart_h - ((val - min_val) / val_range) * chart_h
            fill_poly.append(QPointF(x, y))
        fill_poly.append(
            QPointF(margin_left + chart_w, margin_top + chart_h))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(fill_c))
        painter.drawPolygon(fill_poly)

        # X labels
        painter.setFont(font_s)
        painter.setPen(text_color)
        label_step = max(1, n // 8)
        for i in range(0, n, label_step):
            label = self._points[i][0]
            x = margin_left + chart_w * i / (n - 1)
            painter.drawText(QRect(int(x) - 30, margin_top + chart_h + 4,
                                   60, 20),
                             Qt.AlignCenter, label)

        painter.end()
