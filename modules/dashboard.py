import math
from typing import Optional, Dict, Any

from PyQt5.QtCore import Qt, QRect, QPoint, QTimer
from PyQt5.QtGui import QFont, QColor, QPainter, QPen, QFontMetrics, QCursor
from PyQt5.QtWidgets import (
    QWidget,
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QGridLayout,
    QPushButton,
)

from app_core.i18n import I18n
from app_core.theme_engine import ThemeEngine
from services.database import DatabaseManager
from widgets.toast import ToastNotification


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
        w, h = self.width(), self.height()
        side = min(w, h)
        margin = 20
        gauge_rect = QRect(
            (w - side) // 2 + margin,
            (h - side) // 2 + margin,
            side - margin * 2,
            side - margin * 2,
        )
        cx, cy = (
            gauge_rect.center().x(),
            gauge_rect.center().y() + gauge_rect.height() * 0.1,
        )
        radius = min(gauge_rect.width(), gauge_rect.height()) * 0.42
        bg_color = QColor(
            "#E8ECF1" if ThemeEngine._current_theme == "light" else "#333458"
        )
        pen_bg = QPen(bg_color, radius * 0.18)
        pen_bg.setCapStyle(Qt.RoundCap)
        painter.setPen(pen_bg)
        painter.drawArc(
            QRect(int(cx - radius), int(cy - radius), int(radius * 2), int(radius * 2)),
            180 * 16,
            180 * 16,
        )
        angle = int(180.0 * self._score / 100.0)
        score_color = (
            QColor("#27AE60")
            if self._score >= 70
            else (QColor("#F39C12") if self._score >= 40 else QColor("#E74C3C"))
        )
        pen_score = QPen(score_color, radius * 0.18)
        pen_score.setCapStyle(Qt.RoundCap)
        painter.setPen(pen_score)
        painter.drawArc(
            QRect(int(cx - radius), int(cy - radius), int(radius * 2), int(radius * 2)),
            180 * 16,
            -angle * 16,
        )
        painter.setPen(
            QPen(
                QColor(
                    "#95A5A6" if ThemeEngine._current_theme == "light" else "#8888A0"
                ),
                1,
            )
        )
        f = QFont("Segoe UI", round(radius * 0.35), QFont.Bold)
        painter.setFont(f)
        painter.drawText(
            QRect(
                int(cx - radius), int(cy - radius * 0.1), int(radius * 2), int(radius)
            ),
            Qt.AlignCenter,
            f"{self._score:.0f}%",
        )
        f2 = QFont("Segoe UI", round(radius * 0.13))
        painter.setFont(f2)
        painter.drawText(
            QRect(
                int(cx - radius),
                int(cy + radius * 0.25),
                int(radius * 2),
                int(radius * 0.3),
            ),
            Qt.AlignCenter,
            I18n._("stat.safety_score"),
        )


class KpiCard(QFrame):
    def __init__(
        self,
        title: str,
        value: str,
        color: str,
        icon: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
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
        self._value_label.setStyleSheet(
            f"color: {color}; font-size: 30px; font-weight: 700;"
        )
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
        self._cards: Dict[str, KpiCard] = {}
        self._build_ui()
        self._refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        heading = QLabel(I18n._("tab.dashboard"))
        heading.setProperty("heading", True)
        layout.addWidget(heading)

        self._kpi_grid = QGridLayout()
        self._kpi_grid.setSpacing(14)
        kpi_defs = [
            ("stat.employees_total", "employees_total", "👤", "#2196F3"),
            ("stat.violations_total", "violations_total", "⚠", "#E74C3C"),
            ("stat.companies_total", "companies_total", "🏢", "#27AE60"),
            ("stat.fines_total", "fines_total", "💰", "#9C27B0"),
            ("stat.incidents", "incidents_total", "🔍", "#FF5722"),
            ("stat.ppe", "ppe_total", "🛡", "#00BCD4"),
            ("stat.training", "training_total", "📜", "#4CAF50"),
            ("stat.permits", "permits_total", "📋", "#FF9800"),
        ]
        for i, (key, stat_key, icon, color) in enumerate(kpi_defs):
            card = KpiCard(I18n._(key), "—", color, icon)
            self._kpi_grid.addWidget(card, i // 4, i % 4)
            self._cards[stat_key] = card
        layout.addLayout(self._kpi_grid)

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
        stats_layout.setSpacing(10)
        stats_heading = QLabel(I18n._("stat.overdue_summary"))
        stats_heading.setProperty("heading", True)
        stats_heading.setStyleSheet("font-size: 16px;")
        stats_layout.addWidget(stats_heading)
        self._overdue_labels: Dict[str, QLabel] = {}
        overdue_defs = [
            ("stat.overdue_total", "overdue_total", "⏰", "#F39C12"),
            ("overdue_ppe", "overdue_ppe", "🛡", "#E74C3C"),
            ("overdue_training", "overdue_training", "📜", "#E74C3C"),
            ("overdue_permits", "overdue_permits", "📋", "#E74C3C"),
        ]
        for key, stat_key, icon, color in overdue_defs:
            row = QHBoxLayout()
            row.setSpacing(8)
            icon_lbl = QLabel(icon)
            icon_lbl.setStyleSheet("font-size: 16px;")
            row.addWidget(icon_lbl)
            val = QLabel("—")
            val.setStyleSheet(f"font-size: 18px; font-weight: 600; color: {color};")
            row.addWidget(val)
            lbl = QLabel(I18n._(key))
            lbl.setStyleSheet("font-size: 12px;")
            row.addWidget(lbl)
            row.addStretch()
            stats_layout.addLayout(row)
            self._overdue_labels[stat_key] = val
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

        self._refresh_timer = QTimer()
        self._refresh_timer.setInterval(60000)
        self._refresh_timer.timeout.connect(self._refresh)
        self._refresh_timer.start()

    def _refresh(self) -> None:
        try:
            stats = self.db.get_statistics()
            for stat_key, card in self._cards.items():
                val = stats.get(stat_key, 0)
                if stat_key == "fines_total":
                    card.setText(f"{val:,.0f} ₽".replace(",", " "))
                else:
                    card.setText(str(val))

            for stat_key, label in self._overdue_labels.items():
                val = stats.get(stat_key, 0)
                label.setText(str(val))

            total = stats.get("employees_total", 0) + stats.get("violations_total", 0)
            overdue = stats.get("overdue_total", 0)
            score = 100.0
            if total > 0:
                score = max(0.0, 100.0 - (overdue / max(total, 1)) * 100.0)
            self._gauge.set_score(score)

            recent = self.db.fetch_all(
                "SELECT event, created_at FROM audit_log ORDER BY id DESC LIMIT 5"
            )
            lines = []
            for r in recent:
                ts = r["created_at"][:16] if r["created_at"] else ""
                ev = r["event"][:60] if r["event"] else ""
                lines.append(f"• [{ts}] {ev}")
            self._recent_label.setText(
                "\n".join(lines) if lines else I18n._("dashboard.no_activity")
            )
        except Exception:
            import traceback

            traceback.print_exc()
