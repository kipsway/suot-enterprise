import math
from typing import Optional, Dict, Any

from PyQt5.QtCore import Qt, QRect, QPoint
from PyQt5.QtGui import (QFont, QColor, QPainter, QPen,
                         QFontMetrics, QCursor)
from PyQt5.QtWidgets import (QWidget, QFrame, QVBoxLayout, QHBoxLayout,
                             QLabel)

from app_core.i18n import I18n
from app_core.theme_engine import ThemeEngine
from services.database import DatabaseManager


class SafetyScoreGauge(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._score: float = 75.0
        self.setMinimumSize(200, 200)
        self.setMaximumSize(400, 400)

    def set_score(self, score: float) -> None:
        self._score = max(0.0, min(100.0, score))
        self.update()

    def paintEvent(self, event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        w = self.width()
        h = self.height()
        side = min(w, h)
        margin = 20
        gauge_rect = QRect((w - side) // 2 + margin, (h - side) // 2 + margin,
                           side - margin * 2, side - margin * 2)
        cx = gauge_rect.center().x()
        cy = gauge_rect.center().y() + gauge_rect.height() * 0.1
        radius = min(gauge_rect.width(), gauge_rect.height()) * 0.42

        pen_bg = QPen(QColor("#E8ECF1" if ThemeEngine._current_theme == "light"
                              else "#333458"), radius * 0.18)
        pen_bg.setCapStyle(Qt.RoundCap)
        painter.setPen(pen_bg)
        painter.drawArc(QRect(int(cx - radius), int(cy - radius),
                              int(radius * 2), int(radius * 2)),
                        180 * 16, 180 * 16)

        angle = int(180.0 * self._score / 100.0)
        score_color = QColor("#27AE60") if self._score >= 70 else (
            QColor("#F39C12") if self._score >= 40 else QColor("#E74C3C"))
        pen_score = QPen(score_color, radius * 0.18)
        pen_score.setCapStyle(Qt.RoundCap)
        painter.setPen(pen_score)
        painter.drawArc(QRect(int(cx - radius), int(cy - radius),
                              int(radius * 2), int(radius * 2)),
                        180 * 16, -angle * 16)

        painter.setPen(QPen(QColor("#95A5A6" if ThemeEngine._current_theme == "light"
                                   else "#8888A0"), 1))
        font = QFont("Segoe UI", 9)
        painter.setFont(font)
        for i in range(0, 101, 10):
            rad = math.radians(180 - 180.0 * i / 100.0)
            inner_r = radius * 0.75
            outer_r = radius * 0.85
            tick_len = radius * 0.12 if i % 20 == 0 else radius * 0.07
            x1 = cx + inner_r * math.cos(rad)
            y1 = cy - inner_r * math.sin(rad)
            x2 = cx + (inner_r + tick_len) * math.cos(rad)
            y2 = cy - (inner_r + tick_len) * math.sin(rad)
            painter.drawLine(QPoint(int(x1), int(y1)), QPoint(int(x2), int(y2)))

            if i % 20 == 0:
                label_r = radius * 0.58
                lx = cx + label_r * math.cos(rad)
                ly = cy - label_r * math.sin(rad)
                painter.drawText(QRect(int(lx) - 15, int(ly) - 10, 30, 20),
                                 Qt.AlignCenter, str(i))

        needle_rad = math.radians(180 - 180.0 * self._score / 100.0)
        needle_len = radius * 0.65
        nx = cx + needle_len * math.cos(needle_rad)
        ny = cy - needle_len * math.sin(needle_rad)
        painter.setPen(QPen(score_color, 3, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(int(cx), int(cy), int(nx), int(ny))

        painter.setBrush(score_color)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(int(cx), int(cy), int(radius * 0.08), int(radius * 0.08))

        font_big = QFont("Segoe UI", 28, QFont.Bold)
        painter.setFont(font_big)
        painter.setPen(QColor("#2C3E50" if ThemeEngine._current_theme == "light"
                              else "#E0E0E8"))
        score_text = f"{self._score:.0f}%"
        painter.drawText(QRect(int(cx) - 60, int(cy) + int(radius * 0.35),
                               120, 40), Qt.AlignCenter, score_text)

        font_small = QFont("Segoe UI", 10)
        painter.setFont(font_small)
        painter.setPen(QColor("#95A5A6" if ThemeEngine._current_theme == "light"
                              else "#8888A0"))
        painter.drawText(QRect(int(cx) - 90, int(cy) + int(radius * 0.35) + 36,
                               180, 22), Qt.AlignCenter, I18n._("stat.safety_score"))

        painter.end()


class KpiCard(QFrame):
    def __init__(self, title: str, value: str, color: str,
                 icon: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setProperty("card", True)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self._color = color
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(6)

        header = QHBoxLayout()
        if icon:
            icon_label = QLabel(icon)
            icon_label.setStyleSheet(f"font-size: 22px; color: {color};")
            header.addWidget(icon_label)
        header.addStretch()

        self._value_label = QLabel(str(value))
        self._value_label.setProperty("card_value", True)
        self._value_label.setStyleSheet(f"color: {color}; font-size: 30px; font-weight: 700;")

        self._title_label = QLabel(title)
        self._title_label.setProperty("card_label", True)
        self._title_label.setWordWrap(True)

        layout.addLayout(header)
        layout.addWidget(self._value_label)
        layout.addWidget(self._title_label)

    def setText(self, value: str) -> None:
        self._value_label.setText(str(value))

    def setTitle(self, title: str) -> None:
        self._title_label.setText(title)


class DashboardTab(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.db = DatabaseManager()
        self._build_ui()
        self._refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(20)

        heading = QLabel(I18n._("tab.dashboard"))
        heading.setProperty("heading", True)
        layout.addWidget(heading)

        self._cards_layout = QHBoxLayout()
        self._cards_layout.setSpacing(16)
        layout.addLayout(self._cards_layout)

        body = QHBoxLayout()
        body.setSpacing(20)

        gauge_widget = QFrame()
        gauge_widget.setProperty("card", True)
        gauge_layout = QVBoxLayout(gauge_widget)
        gauge_layout.setContentsMargins(16, 16, 16, 16)
        self._gauge = SafetyScoreGauge()
        gauge_layout.addWidget(self._gauge, 0, Qt.AlignCenter)
        body.addWidget(gauge_widget, 2)

        stats_widget = QFrame()
        stats_widget.setProperty("card", True)
        stats_layout = QVBoxLayout(stats_widget)
        stats_layout.setContentsMargins(16, 16, 16, 16)
        stats_layout.setSpacing(12)
        stats_heading = QLabel(I18n._("stat.title"))
        stats_heading.setProperty("heading", True)
        stats_heading.setStyleSheet("font-size: 16px;")
        stats_layout.addWidget(stats_heading)
        self._stats_labels: Dict[str, QLabel] = {}
        stat_items = [
            ("stat.employees_total", "👤", "#2196F3"),
            ("stat.violations_total", "⚠", "#E74C3C"),
            ("stat.companies_total", "🏢", "#27AE60"),
            ("stat.overdue_total", "⏰", "#F39C12"),
            ("stat.fines_total", "💰", "#9C27B0"),
        ]
        for key, icon, color in stat_items:
            row = QHBoxLayout()
            row.setSpacing(10)
            icon_lbl = QLabel(icon)
            icon_lbl.setStyleSheet(f"font-size: 18px;")
            row.addWidget(icon_lbl)
            val = QLabel("—")
            val.setStyleSheet(f"font-size: 18px; font-weight: 600; color: {color};")
            row.addWidget(val)
            lbl = QLabel(I18n._(key))
            lbl.setStyleSheet("font-size: 13px;")
            row.addWidget(lbl)
            row.addStretch()
            stats_layout.addLayout(row)
            self._stats_labels[key] = val
        stats_layout.addStretch()
        body.addWidget(stats_widget, 3)
        layout.addLayout(body)

        recent_widget = QFrame()
        recent_widget.setProperty("card", True)
        recent_layout = QVBoxLayout(recent_widget)
        recent_layout.setContentsMargins(16, 16, 16, 16)
        recent_layout.setSpacing(8)
        recent_heading = QLabel(I18n._("dashboard.recent"))
        recent_heading.setProperty("heading", True)
        recent_heading.setStyleSheet("font-size: 16px;")
        recent_layout.addWidget(recent_heading)
        self._recent_label = QLabel()
        self._recent_label.setWordWrap(True)
        self._recent_label.setStyleSheet("font-size: 12px;")
        recent_layout.addWidget(self._recent_label)
        layout.addWidget(recent_widget)

    def _refresh(self) -> None:
        try:
            stats = self.db.get_statistics()
            self._stats_labels["stat.employees_total"].setText(str(stats["employees_total"]))
            self._stats_labels["stat.violations_total"].setText(str(stats["violations_total"]))
            self._stats_labels["stat.companies_total"].setText(str(stats["companies_total"]))
            self._stats_labels["stat.overdue_total"].setText(str(stats["overdue_total"]))
            fines = stats["fines_total"]
            self._stats_labels["stat.fines_total"].setText(
                f"{fines:,.0f} ₽".replace(",", " "))
            total = stats["employees_total"] + stats["violations_total"]
            overdue = stats["overdue_total"]
            score = 100.0
            if total > 0:
                score = max(0.0, 100.0 - (overdue / max(total, 1)) * 100.0)
            self._gauge.set_score(score)

            recent = self.db.fetch_all(
                "SELECT event, created_at FROM audit_log ORDER BY id DESC LIMIT 5")
            lines = []
            for r in recent:
                ts = r["created_at"][:16] if r["created_at"] else ""
                ev = r["event"][:60] if r["event"] else ""
                lines.append(f"• [{ts}] {ev}")
            self._recent_label.setText("\n".join(lines) if lines else I18n._("dashboard.no_activity"))
        except Exception:
            import traceback
            traceback.print_exc()
