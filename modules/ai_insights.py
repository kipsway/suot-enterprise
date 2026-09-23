from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QWidget,
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QGridLayout,
    QApplication,
)

from widgets.glass_button import GlassButton

from app_core.i18n import I18n
from app_core.theme_engine import ThemeEngine
from app_core.utils import apply_glass_style
from services.database import DatabaseManager
from modules.ai import AIEngine
from services.predictive import PredictiveModel
from widgets.toast import ToastNotification


class AIInsightsWidget(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.db = DatabaseManager()
        self._engine = AIEngine()
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        header_row = QHBoxLayout()
        heading = QLabel("🧠 " + I18n._("analytics.title"))
        heading.setProperty("heading", True)
        header_row.addWidget(heading)
        header_row.addStretch()

        self._refresh_btn = GlassButton("🔄 " + I18n._("common.refresh"))
        self._refresh_btn.setProperty("small", True)
        self._refresh_btn.clicked.connect(self._generate_insights)
        header_row.addWidget(self._refresh_btn)

        self._ai_btn = GlassButton("🤖 " + I18n._("ai.generate_insights"))
        self._ai_btn.setProperty("small", True)
        self._ai_btn.clicked.connect(self._generate_ai_insights)
        header_row.addWidget(self._ai_btn)

        layout.addLayout(header_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setSpacing(16)
        scroll.setWidget(self._content)
        layout.addWidget(scroll, 1)

        self._show_stats()

    def _make_card(self, title: str) -> QFrame:
        card = QFrame()
        card.setProperty("card", True)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(20, 18, 20, 18)
        cl.setSpacing(8)
        lbl = QLabel(title)
        lbl.setStyleSheet("font-size: 16px; font-weight: 700;")
        cl.addWidget(lbl)
        return card

    def _show_stats(self) -> None:
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        stats = self.db.get_statistics()
        now = datetime.now()

        # KPI grid
        kpi_card = self._make_card(I18n._("stat.title"))
        grid = QGridLayout()
        grid.setSpacing(12)
        kpis = [
            (
                "👤",
                I18n._("stat.employees_total"),
                str(stats["employees_total"]),
                "#2196F3",
            ),
            (
                "⚠",
                I18n._("stat.violations_total"),
                str(stats["violations_total"]),
                "#FF3B30",
            ),
            (
                "🏢",
                I18n._("stat.companies_total"),
                str(stats["companies_total"]),
                "#34C759",
            ),
            (
                "⏰",
                I18n._("stat.overdue_total"),
                str(stats["overdue_total"]),
                "#FF9500",
            ),
            (
                "💰",
                I18n._("stat.fines_total"),
                f"{stats['fines_total']:,.0f} ₽".replace(",", " "),
                "#AF52DE",
            ),
        ]
        for i, (icon, label, value, color) in enumerate(kpis):
            cell = QFrame()
            cell.setStyleSheet(f"""
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {color}15, stop:1 {color}08);
                border: 1px solid {color}30;
                border-radius: 12px; padding: 14px;
            """)
            cl2 = QVBoxLayout(cell)
            cl2.setContentsMargins(12, 10, 12, 10)
            cl2.setSpacing(4)
            lbl_icon = QLabel(icon)
            lbl_icon.setStyleSheet(f"font-size: 22px;")
            cl2.addWidget(lbl_icon)
            lbl_val = QLabel(value)
            lbl_val.setStyleSheet(f"font-size: 26px; font-weight: 700; color: {color};")
            cl2.addWidget(lbl_val)
            lbl_label = QLabel(label)
            lbl_label.setStyleSheet("font-size: 11px; color: #8E8E93;")
            cl2.addWidget(lbl_label)
            grid.addWidget(cell, i // 3, i % 3)

        kpi_card.findChild(QVBoxLayout).addLayout(grid)
        self._content_layout.addWidget(kpi_card)

        # Overdue violations
        overdue_card = self._make_card("⏰ " + I18n._("stat.overdue_total"))
        overdue_layout = overdue_card.findChild(QVBoxLayout)
        overdue_items = self._get_overdue_items()
        if overdue_items:
            for item in overdue_items:
                lbl = QLabel(item)
                lbl.setWordWrap(True)
                lbl.setStyleSheet("font-size: 12px; padding: 4px 0;")
                overdue_layout.addWidget(lbl)
        else:
            overdue_layout.addWidget(QLabel("✅ " + I18n._("dashboard.no_activity")))
        self._content_layout.addWidget(overdue_card)

        # Recent activity
        recent_card = self._make_card("📋 " + I18n._("dashboard.recent"))
        recent_layout = recent_card.findChild(QVBoxLayout)
        recent = self.db.fetch_all(
            "SELECT event, created_at FROM audit_log ORDER BY id DESC LIMIT 10"
        )
        if recent:
            for r in recent:
                ts = r["created_at"][:16] if r["created_at"] else ""
                ev = r["event"][:70] if r["event"] else ""
                lbl = QLabel(f"• [{ts}] {ev}")
                lbl.setWordWrap(True)
                lbl.setStyleSheet("font-size: 11px; padding: 2px 0;")
                recent_layout.addWidget(lbl)
        else:
            recent_layout.addWidget(QLabel(I18n._("dashboard.no_activity")))
        self._content_layout.addWidget(recent_card)

        # AI insights placeholder
        self._ai_card = self._make_card("🤖 " + I18n._("ai.insights"))
        self._ai_content = QLabel(I18n._("ai.insights_hint"))
        self._ai_content.setWordWrap(True)
        self._ai_content.setStyleSheet(
            "font-size: 13px; color: #8E8E93; padding: 8px 0;"
        )
        self._ai_card.findChild(QVBoxLayout).addWidget(self._ai_content)
        self._content_layout.addWidget(self._ai_card)

        # Predictive risk
        try:
            pm = PredictiveModel()
            risk = pm.risk_score()
            risk_card = self._make_card("📊 Прогноз рисков")
            risk_layout = risk_card.findChild(QVBoxLayout)
            level_colors = {"low": "#34C759", "medium": "#FF9500", "high": "#FF3B30"}
            lvl_color = level_colors.get(risk["level"], "#8E8E93")
            risk_lbl = QLabel(
                f"Общий риск: <b style='color:{lvl_color}'>{risk['total_risk']}</b> "
                f"(уровень: <b style='color:{lvl_color}'>{risk['level']}</b>)"
            )
            risk_lbl.setStyleSheet("font-size: 14px; padding: 4px 0;")
            risk_layout.addWidget(risk_lbl)
            for b in risk.get("breakdown", []):
                bc = level_colors.get(b["trend"], "#8E8E93")
                bl = QLabel(
                    f"• {b['table']}: {b['count']} зап. "
                    f"(вклад: {b['contribution']}, тренд: <span style='color:{bc}'>{b['trend']}</span>)"
                )
                bl.setStyleSheet("font-size: 12px; padding: 2px 0;")
                risk_layout.addWidget(bl)
            self._content_layout.addWidget(risk_card)
        except Exception:
            pass

        self._content_layout.addStretch()

    def _get_overdue_items(self) -> List[str]:
        items = []
        for v in self.db.get_json_records("violations"):
            dj = v.get("data_json", {})
            dl = dj.get("Срок устранения", "")
            if not dl:
                continue
            try:
                p = dl.split(".")
                if len(p) == 3:
                    d = datetime(int(p[2]), int(p[1]), int(p[0]))
                    if d < datetime.now():
                        desc = dj.get("Описание", f"#{v['id']}")[:50]
                        company = dj.get("Фирма", "—")
                        items.append(f"⚠ <b>{desc}</b> — {company} (срок: {dl})")
            except Exception:
                pass
        return items[:10]

    def _generate_insights(self) -> None:
        self._show_stats()
        ToastNotification.notify(I18n._("common.refreshed"), "success", 2000)

    def _generate_ai_insights(self) -> None:
        self._ai_btn.setEnabled(False)
        self._ai_btn.setText("⏳ " + I18n._("ai.thinking"))
        QApplication.processEvents()

        local_noauth = any(
            x in self._engine.api_url.lower()
            for x in ["localhost", "127.0.0.1", "ollama"]
        )
        if not self._engine.api_key and not local_noauth:
            self._ai_content.setText("⚠️ " + I18n._("ai.no_key"))
            self._ai_btn.setEnabled(True)
            self._ai_btn.setText("🤖 " + I18n._("ai.generate_insights"))
            return

        stats = self.db.get_statistics()
        prompt = (
            f"Analyze this safety data and provide insights:\n"
            f"- Employees: {stats['employees_total']}\n"
            f"- Violations: {stats['violations_total']}\n"
            f"- Companies: {stats['companies_total']}\n"
            f"- Overdue items: {stats['overdue_total']}\n"
            f"- Total fines: {stats['fines_total']} RUB\n\n"
            "Provide:\n"
            "1. Key observations about safety performance\n"
            "2. Risk assessment (low/medium/high)\n"
            "3. Top 3 recommended actions\n"
            "4. Any positive trends\n"
            "Keep it concise, 3-5 sentences per section."
        )

        try:
            response = self._engine.send_request([], prompt)
            if response and not response.startswith(
                ("HTTP Error", "Connection Error", "Error:")
            ):
                self._ai_content.setText(response)
                self._ai_content.setStyleSheet("font-size: 13px; padding: 8px 0;")
            else:
                self._ai_content.setText("⚠️ " + (response or I18n._("error.generic")))
        except Exception as e:
            self._ai_content.setText(f"⚠️ Error: {e}")
        finally:
            self._ai_btn.setEnabled(True)
            self._ai_btn.setText("🤖 " + I18n._("ai.generate_insights"))
