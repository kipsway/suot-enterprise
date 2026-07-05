from datetime import datetime
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QTableWidget, QTableWidgetItem,
                             QHeaderView, QAbstractItemView, QFrame)

from app_core.i18n import I18n
from services.database import DatabaseManager
from modules.dashboard import KpiCard


class StatisticsTab(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.db = DatabaseManager()
        self._build_ui()
        self._refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(20)

        heading = QLabel(I18n._("stat.title"))
        heading.setProperty("heading", True)
        layout.addWidget(heading)

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

        mid = QHBoxLayout()
        mid.setSpacing(20)

        by_company = QFrame()
        by_company.setProperty("card", True)
        by_company_layout = QVBoxLayout(by_company)
        by_company_layout.setContentsMargins(16, 16, 16, 16)
        co_heading = QLabel(I18n._("stat.by_company"))
        co_heading.setProperty("heading", True)
        co_heading.setStyleSheet("font-size: 16px;")
        by_company_layout.addWidget(co_heading)
        self._company_table = QTableWidget()
        self._company_table.setColumnCount(4)
        self._company_table.setHorizontalHeaderLabels([
            I18n._("company.name"), I18n._("company.employees_count"),
            I18n._("company.violations_count"), I18n._("company.fines_total")])
        self._company_table.resizeColumnsToContents()
        self._company_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self._company_table.horizontalHeader().setStretchLastSection(True)
        self._company_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._company_table.setAlternatingRowColors(True)
        self._company_table.verticalHeader().hide()
        by_company_layout.addWidget(self._company_table)
        mid.addWidget(by_company, 1)

        by_category = QFrame()
        by_category.setProperty("card", True)
        by_category_layout = QVBoxLayout(by_category)
        by_category_layout.setContentsMargins(16, 16, 16, 16)
        cat_heading = QLabel(I18n._("stat.by_category"))
        cat_heading.setProperty("heading", True)
        cat_heading.setStyleSheet("font-size: 16px;")
        by_category_layout.addWidget(cat_heading)
        self._category_table = QTableWidget()
        self._category_table.setColumnCount(2)
        self._category_table.setHorizontalHeaderLabels([
            I18n._("viol.risk_category"), I18n._("common.count")])
        self._category_table.resizeColumnsToContents()
        self._category_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self._category_table.horizontalHeader().setStretchLastSection(True)
        self._category_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._category_table.setAlternatingRowColors(True)
        self._category_table.verticalHeader().hide()
        by_category_layout.addWidget(self._category_table)
        mid.addWidget(by_category, 1)

        layout.addLayout(mid)

        bottom = QHBoxLayout()
        bottom.setSpacing(20)

        status_frame = QFrame()
        status_frame.setProperty("card", True)
        status_layout = QVBoxLayout(status_frame)
        status_layout.setContentsMargins(16, 16, 16, 16)
        st_heading = QLabel(I18n._("stat.status_distribution"))
        st_heading.setProperty("heading", True)
        st_heading.setStyleSheet("font-size: 16px;")
        status_layout.addWidget(st_heading)
        self._status_table = QTableWidget()
        self._status_table.setColumnCount(2)
        self._status_table.setHorizontalHeaderLabels([
            I18n._("common.status"), I18n._("common.count")])
        self._status_table.resizeColumnsToContents()
        self._status_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self._status_table.horizontalHeader().setStretchLastSection(True)
        self._status_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._status_table.setAlternatingRowColors(True)
        self._status_table.verticalHeader().hide()
        status_layout.addWidget(self._status_table)
        bottom.addWidget(status_frame, 1)

        overdue_frame = QFrame()
        overdue_frame.setProperty("card", True)
        overdue_layout = QVBoxLayout(overdue_frame)
        overdue_layout.setContentsMargins(16, 16, 16, 16)
        ov_heading = QLabel(I18n._("stat.overdue_trend"))
        ov_heading.setProperty("heading", True)
        ov_heading.setStyleSheet("font-size: 16px;")
        overdue_layout.addWidget(ov_heading)
        self._overdue_label = QLabel()
        self._overdue_label.setWordWrap(True)
        self._overdue_label.setStyleSheet("font-size: 13px; color: #E74C3C; padding: 8px;")
        overdue_layout.addWidget(self._overdue_label)
        bottom.addWidget(overdue_frame, 1)

        layout.addLayout(bottom)

        self._refresh_btn = QPushButton(I18n._("common.refresh"))
        self._refresh_btn.setProperty("flat", True)
        self._refresh_btn.clicked.connect(self._refresh)
        layout.addWidget(self._refresh_btn, 0, Qt.AlignLeft)

    def _refresh(self) -> None:
        stats = self.db.get_statistics()
        for skey in self._cards:
            if skey == "fines_total":
                self._cards[skey].setText(
                    f"{stats.get(skey, 0):,.0f} ₽".replace(",", " "))
            else:
                self._cards[skey].setText(str(stats.get(skey, 0)))

        companies = self.db.get_companies()
        self._company_table.setRowCount(len(companies))
        for i, c in enumerate(companies):
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
            self._company_table.setItem(i, 0, QTableWidgetItem(name))
            self._company_table.setItem(i, 1, QTableWidgetItem(str(emp_count)))
            self._company_table.setItem(i, 2, QTableWidgetItem(str(viol_count)))
            fine_item = QTableWidgetItem(f"{fines:,.0f} ₽".replace(",", " "))
            fine_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._company_table.setItem(i, 3, fine_item)

        categories: Dict[str, int] = {}
        statuses: Dict[str, int] = {}
        now = datetime.now()
        overdue_list = []
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
                            overdue_list.append(f"- {dj.get('Описание', '?')[:40]} (до {deadline})")
            except Exception:
                pass

        self._category_table.setRowCount(len(categories))
        for i, (cat, cnt) in enumerate(sorted(categories.items(),
                                               key=lambda x: -x[1])):
            self._category_table.setItem(i, 0, QTableWidgetItem(cat))
            self._category_table.setItem(i, 1, QTableWidgetItem(str(cnt)))

        self._status_table.setRowCount(len(statuses))
        for i, (st, cnt) in enumerate(sorted(statuses.items(),
                                              key=lambda x: -x[1])):
            self._status_table.setItem(i, 0, QTableWidgetItem(st))
            self._status_table.setItem(i, 1, QTableWidgetItem(str(cnt)))

        self._overdue_label.setText(
            f"Просрочено: {len(overdue_list)}\n" + "\n".join(overdue_list[:10])
            if overdue_list else "Нет просрочек")

        self._company_table.resizeColumnsToContents()
        self._category_table.resizeColumnsToContents()
        self._status_table.resizeColumnsToContents()

    def refresh(self) -> None:
        self._refresh()
