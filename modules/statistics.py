from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QTableWidget, QTableWidgetItem,
                             QHeaderView, QAbstractItemView, QFrame,
                             QScrollArea, QSplitter)

from app_core.i18n import I18n
from services.database import DatabaseManager
from modules.dashboard import KpiCard
from widgets.charts import BarChart, PieChart, TrendChart


CHART_PALETTE = [
    "#2196F3", "#E74C3C", "#27AE60", "#F39C12", "#9C27B0",
    "#00BCD4", "#FF5722", "#4CAF50", "#FF9800", "#3F51B5",
]


class StatisticsTab(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.db = DatabaseManager()
        self._build_ui()
        self._refresh()

    def _build_ui(self) -> None:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(20)

        heading = QLabel(I18n._("stat.title"))
        heading.setProperty("heading", True)
        layout.addWidget(heading)

        # KPI cards row
        cards = QHBoxLayout()
        cards.setSpacing(16)
        stats = self.db.get_statistics()
        self._cards: Dict[str, KpiCard] = {}
        card_data = [
            ("stat.employees_total", "employees_total", "#2196F3", "👤"),
            ("stat.violations_total", "violations_total", "#E74C3C", "⚠"),
            ("stat.companies_total", "companies_total", "#27AE60", "🏢"),
            ("stat.overdue_total", "overdue_total", "#F39C12", "⏰"),
            ("stat.fines_total", "fines_total", "#9C27B0", "💰"),
        ]
        for key, skey, color, icon in card_data:
            val = stats.get(skey, 0) if skey != "fines_total" else f"{stats.get(skey, 0):,.0f} ₽".replace(",", " ")
            card = KpiCard(I18n._(key), str(val), color, icon)
            cards.addWidget(card)
            self._cards[skey] = card
        layout.addLayout(cards)

        # Charts row 1: Violations by company + Status distribution
        charts_row1 = QHBoxLayout()
        charts_row1.setSpacing(20)

        self._company_chart = BarChart()
        self._company_chart.setMinimumHeight(220)
        company_frame = QFrame()
        company_frame.setProperty("card", True)
        company_cl = QVBoxLayout(company_frame)
        company_cl.setContentsMargins(16, 16, 16, 16)
        company_cl.addWidget(self._company_chart)
        charts_row1.addWidget(company_frame, 1)

        self._status_chart = PieChart()
        self._status_chart.setMinimumHeight(220)
        status_frame = QFrame()
        status_frame.setProperty("card", True)
        status_cl = QVBoxLayout(status_frame)
        status_cl.setContentsMargins(16, 16, 16, 16)
        status_cl.addWidget(self._status_chart)
        charts_row1.addWidget(status_frame, 1)

        layout.addLayout(charts_row1)

        # Charts row 2: Risk categories + Violations trend
        charts_row2 = QHBoxLayout()
        charts_row2.setSpacing(20)

        self._category_chart = BarChart()
        self._category_chart.setMinimumHeight(220)
        cat_frame = QFrame()
        cat_frame.setProperty("card", True)
        cat_cl = QVBoxLayout(cat_frame)
        cat_cl.setContentsMargins(16, 16, 16, 16)
        cat_cl.addWidget(self._category_chart)
        charts_row2.addWidget(cat_frame, 1)

        self._trend_chart = TrendChart()
        self._trend_chart.setMinimumHeight(220)
        trend_frame = QFrame()
        trend_frame.setProperty("card", True)
        trend_cl = QVBoxLayout(trend_frame)
        trend_cl.setContentsMargins(16, 16, 16, 16)
        trend_cl.addWidget(self._trend_chart)
        charts_row2.addWidget(trend_frame, 1)

        layout.addLayout(charts_row2)

        # Tables row
        tables_row = QHBoxLayout()
        tables_row.setSpacing(20)

        # Company detail table
        co_frame = QFrame()
        co_frame.setProperty("card", True)
        co_layout = QVBoxLayout(co_frame)
        co_layout.setContentsMargins(16, 16, 16, 16)
        co_heading = QLabel(I18n._("stat.by_company"))
        co_heading.setProperty("heading", True)
        co_heading.setStyleSheet("font-size: 14px;")
        co_layout.addWidget(co_heading)
        self._company_table = QTableWidget()
        self._company_table.setColumnCount(4)
        self._company_table.setHorizontalHeaderLabels([
            I18n._("company.name"), I18n._("company.employees_count"),
            I18n._("company.violations_count"), I18n._("company.fines_total")])
        self._company_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._company_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._company_table.setAlternatingRowColors(True)
        self._company_table.verticalHeader().hide()
        self._company_table.setMaximumHeight(180)
        co_layout.addWidget(self._company_table)
        tables_row.addWidget(co_frame, 1)

        # Overdue list
        overdue_frame = QFrame()
        overdue_frame.setProperty("card", True)
        overdue_layout = QVBoxLayout(overdue_frame)
        overdue_layout.setContentsMargins(16, 16, 16, 16)
        ov_heading = QLabel(I18n._("stat.overdue_trend"))
        ov_heading.setProperty("heading", True)
        ov_heading.setStyleSheet("font-size: 14px;")
        overdue_layout.addWidget(ov_heading)
        self._overdue_label = QLabel()
        self._overdue_label.setWordWrap(True)
        self._overdue_label.setStyleSheet("font-size: 12px; color: #E74C3C; padding: 4px;")
        overdue_layout.addWidget(self._overdue_label)
        tables_row.addWidget(overdue_frame, 1)

        layout.addLayout(tables_row)

        self._refresh_btn = QPushButton(I18n._("common.refresh"))
        self._refresh_btn.setProperty("flat", True)
        self._refresh_btn.clicked.connect(self._refresh)
        layout.addWidget(self._refresh_btn, 0, Qt.AlignLeft)

        layout.addStretch()
        scroll.setWidget(inner)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def _refresh(self) -> None:
        stats = self.db.get_statistics()
        for skey in self._cards:
            if skey == "fines_total":
                self._cards[skey].setText(
                    f"{stats.get(skey, 0):,.0f} ₽".replace(",", " "))
            else:
                self._cards[skey].setText(str(stats.get(skey, 0)))

        companies = self.db.get_companies()
        now = datetime.now()

        # Company data
        company_stats: List[Tuple[str, int, int, float]] = []
        categories: Dict[str, int] = {}
        statuses: Dict[str, int] = {}
        monthly: Dict[str, int] = defaultdict(int)
        overdue_list: List[Tuple[str, str, str]] = []

        for c in companies:
            name = c.get("name", "")
            emp_count = 0
            viol_count = 0
            fines = 0.0
            for emp in self.db.get_json_records("employees"):
                if emp.get("data_json", {}).get("Фирма") == name:
                    emp_count += 1
            for viol in self.db.get_json_records("violations"):
                dj = viol.get("data_json", {})
                if dj.get("Фирма") == name:
                    viol_count += 1
                    try:
                        fines += float(str(dj.get("Штраф", "0"))
                                       .replace(" ", "").replace(",", "."))
                    except Exception:
                        pass
            if viol_count > 0:
                company_stats.append((name, emp_count, viol_count, fines))

        # Violation analysis
        for viol in self.db.get_json_records("violations"):
            dj = viol.get("data_json", {})
            cat = dj.get("Категория риска", "Не указана")
            categories[cat] = categories.get(cat, 0) + 1
            status = dj.get("Статус", "Не указан")
            statuses[status] = statuses.get(status, 0) + 1

            deadline = dj.get("Срок устранения", "")
            try:
                if deadline:
                    parts = deadline.split(".")
                    if len(parts) == 3:
                        dt = datetime(int(parts[2]), int(parts[1]), int(parts[0]))
                        if dt < now and status != "Исполнено":
                            desc = str(dj.get("Описание", "?"))[:40]
                            overdue_list.append((desc, deadline, dj.get("Фирма", "")))
            except Exception:
                pass

            created = viol.get("created_at", "")
            if created and len(created) >= 7:
                monthly[created[:7]] = monthly.get(created[:7], 0) + 1

        # Update charts
        company_sorted = sorted(company_stats, key=lambda x: -x[2])[:10]
        if company_sorted:
            bar_data = [(n, v) for n, _, v, _ in company_sorted]
            self._company_chart.set_data(bar_data, I18n._("stat.by_company"), "#2196F3")

        if statuses:
            sorted_statuses = sorted(statuses.items(), key=lambda x: -x[1])
            self._status_chart.set_data(sorted_statuses, I18n._("stat.status_distribution"))

        if categories:
            sorted_cats = sorted(categories.items(), key=lambda x: -x[1])
            self._category_chart.set_data(sorted_cats, I18n._("stat.by_category"), "#9C27B0")

        if monthly:
            sorted_months = sorted(monthly.items())
            self._trend_chart.set_data(sorted_months, I18n._("stat.monthly_trend"), "#27AE60")

        # Update company table
        self._company_table.setRowCount(len(company_stats))
        for i, (name, ec, vc, fines) in enumerate(company_stats):
            self._company_table.setItem(i, 0, QTableWidgetItem(name))
            self._company_table.setItem(i, 1, QTableWidgetItem(str(ec)))
            self._company_table.setItem(i, 2, QTableWidgetItem(str(vc)))
            fine_item = QTableWidgetItem(f"{fines:,.0f} ₽".replace(",", " "))
            fine_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._company_table.setItem(i, 3, fine_item)
        self._company_table.resizeColumnsToContents()

        # Overdue list
        if overdue_list:
            lines = [f"<b>{I18n._('stat.overdue_total')}: {len(overdue_list)}</b>"]
            for desc, deadline, company in overdue_list[:10]:
                lines.append(f"• {desc} — {deadline} ({company})")
            self._overdue_label.setText("<br>".join(lines))
        else:
            self._overdue_label.setText(I18n._("stat.no_overdue"))

    def refresh(self) -> None:
        self._refresh()
