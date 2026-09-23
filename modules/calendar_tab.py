from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

from PyQt5.QtCore import Qt, QDate
from PyQt5.QtGui import QColor, QFont, QTextCharFormat
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QAbstractItemView,
    QFrame,
    QCalendarWidget,
    QSplitter,
    QInputDialog,
    QMessageBox,
)

from widgets.glass_button import GlassButton
from widgets.glass_checkbox import GlassCheckBox

from app_core.i18n import I18n
from app_core.theme_engine import ThemeEngine
from services.database import DatabaseManager
from widgets.toast import ToastNotification


EVENT_COLORS = {
    "violation": QColor("#E74C3C"),
    "medical": QColor("#2196F3"),
    "reminder": QColor("#F39C12"),
    "other": QColor("#27AE60"),
}


class CalendarTab(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.db = DatabaseManager()
        self._events: Dict[str, List[Dict[str, Any]]] = {}
        self._build_ui()
        self._load_events()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        heading = QLabel(I18n._("calendar.title"))
        heading.setProperty("heading", True)
        layout.addWidget(heading)

        splitter = QSplitter(Qt.Horizontal)

        # Left: Calendar
        calendar_frame = QFrame()
        calendar_frame.setProperty("card", True)
        cal_layout = QVBoxLayout(calendar_frame)
        cal_layout.setContentsMargins(12, 12, 12, 12)

        self._calendar = QCalendarWidget()
        self._calendar.setGridVisible(True)
        self._calendar.setFirstDayOfWeek(Qt.Monday)
        self._calendar.clicked.connect(self._on_date_selected)
        self._calendar.currentPageChanged.connect(self._update_calendar_colors)
        cal_layout.addWidget(self._calendar)

        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel(I18n._("calendar.show") + ":"))
        self._filter_violations = GlassCheckBox(I18n._("tab.violations"))
        self._filter_violations.setChecked(True)
        self._filter_violations.toggled.connect(self._refresh)
        filter_layout.addWidget(self._filter_violations)
        self._filter_medical = GlassCheckBox(I18n._("calendar.medical"))
        self._filter_medical.setChecked(True)
        self._filter_medical.toggled.connect(self._refresh)
        filter_layout.addWidget(self._filter_medical)
        self._filter_reminders = GlassCheckBox(I18n._("tab.reminders"))
        self._filter_reminders.setChecked(True)
        self._filter_reminders.toggled.connect(self._refresh)
        filter_layout.addWidget(self._filter_reminders)
        filter_layout.addStretch()
        cal_layout.addLayout(filter_layout)

        splitter.addWidget(calendar_frame)

        # Right: Event list
        events_frame = QFrame()
        events_frame.setProperty("card", True)
        ev_layout = QVBoxLayout(events_frame)
        ev_layout.setContentsMargins(12, 12, 12, 12)

        self._selected_date_label = QLabel()
        self._selected_date_label.setStyleSheet("font-size: 14px; font-weight: 600;")
        ev_layout.addWidget(self._selected_date_label)

        self._event_table = QTableWidget()
        self._event_table.setColumnCount(4)
        self._event_table.setHorizontalHeaderLabels(
            [
                I18n._("calendar.event_type"),
                I18n._("calendar.event_title"),
                I18n._("calendar.event_detail"),
                I18n._("common.status"),
            ]
        )
        hdr = self._event_table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.Interactive)
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setStretchLastSection(True)
        self._event_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._event_table.setAlternatingRowColors(True)
        self._event_table.verticalHeader().hide()
        self._event_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._event_table.itemDoubleClicked.connect(self._on_event_double_click)
        ev_layout.addWidget(self._event_table, 1)

        btn_layout = QHBoxLayout()
        self._add_reminder_btn = GlassButton(I18n._("calendar.add_reminder"))
        self._add_reminder_btn.setProperty("success", True)
        self._add_reminder_btn.clicked.connect(self._add_reminder_for_date)
        btn_layout.addWidget(self._add_reminder_btn)
        btn_layout.addStretch()
        self._refresh_btn = GlassButton(I18n._("common.refresh"))
        self._refresh_btn.clicked.connect(self._refresh)
        btn_layout.addWidget(self._refresh_btn)
        ev_layout.addLayout(btn_layout)

        splitter.addWidget(events_frame)
        splitter.setSizes([400, 300])

        layout.addWidget(splitter, 1)

        self._update_date_label()

    def _load_events(self) -> None:
        self._events = defaultdict(list)
        now = datetime.now()

        # Violation deadlines
        if self._filter_violations.isChecked():
            for viol in self.db.get_json_records("violations", limit=5000):
                dj = viol.get("data_json", viol)
                deadline = dj.get("Срок устранения", "")
                if deadline:
                    try:
                        p = deadline.split(".")
                        if len(p) == 3:
                            dt = datetime(int(p[2]), int(p[1]), int(p[0]))
                            key = dt.strftime("%Y-%m-%d")
                            status = dj.get("Статус", "")
                            self._events[key].append(
                                {
                                    "type": "violation",
                                    "title": I18n._("calendar.deadline"),
                                    "detail": str(dj.get("Описание", f"#{viol['id']}"))[
                                        :50
                                    ],
                                    "status": status,
                                    "date": deadline,
                                    "_table": "violations",
                                    "_id": viol["id"],
                                    "_dt": dt,
                                    "_status": status,
                                }
                            )
                    except Exception:
                        pass

        # Employee medical checkups
        if self._filter_medical.isChecked():
            for emp in self.db.get_json_records("employees", limit=5000):
                dj = emp.get("data_json", emp)
                med = dj.get("Дата медосмотра", "")
                if med:
                    try:
                        p = med.split(".")
                        if len(p) == 3:
                            dt = datetime(int(p[2]), int(p[1]), int(p[0]))
                            key = dt.strftime("%Y-%m-%d")
                            self._events[key].append(
                                {
                                    "type": "medical",
                                    "title": I18n._("calendar.medical"),
                                    "detail": str(dj.get("ФИО", f"#{emp['id']}"))[:50],
                                    "status": "",
                                    "date": med,
                                    "_table": "employees",
                                    "_id": emp["id"],
                                    "_dt": dt,
                                }
                            )
                    except Exception:
                        pass

        # Reminders
        if self._filter_reminders.isChecked():
            for r in self.db.get_reminders(include_done=False):
                due = r.get("due_date", "")
                if due:
                    try:
                        p = due.split(".")
                        if len(p) == 3:
                            dt = datetime(int(p[2]), int(p[1]), int(p[0]))
                            key = dt.strftime("%Y-%m-%d")
                            self._events[key].append(
                                {
                                    "type": "reminder",
                                    "title": str(r.get("title", ""))[:50],
                                    "detail": str(r.get("description", ""))[:50],
                                    "status": "✓" if r.get("is_done") else "☐",
                                    "date": due,
                                    "_table": "reminders",
                                    "_id": r["id"],
                                    "_dt": dt,
                                    "_done": r.get("is_done", False),
                                }
                            )
                    except Exception:
                        pass

        self._update_calendar_colors()
        self._on_date_selected(self._calendar.selectedDate())

    def _update_calendar_colors(self) -> None:
        is_dark = ThemeEngine._current_theme == "dark"
        fmt = QTextCharFormat()

        # Reset all dates
        for date in self._iterate_month():
            self._calendar.setDateTextFormat(date, fmt)

        # Mark dates with events
        for date_str, events in self._events.items():
            qd = QDate.fromString(date_str, "yyyy-MM-dd")
            if not qd.isValid():
                continue
            has_overdue = any(
                e.get("_status") == "Просрочено"
                or (
                    e.get("_dt")
                    and e["_dt"] < datetime.now()
                    and e.get("_status") != "Исполнено"
                )
                for e in events
            )
            has_violation = any(e["type"] == "violation" for e in events)
            has_medical = any(e["type"] == "medical" for e in events)

            if has_overdue:
                color = QColor("#E74C3C")
            elif has_violation:
                color = QColor("#F39C12")
            elif has_medical:
                color = QColor("#2196F3")
            else:
                color = QColor("#27AE60")

            event_fmt = QTextCharFormat()
            event_fmt.setBackground(color.lighter(160 if is_dark else 180))
            event_fmt.setForeground(QColor("#FFFFFF" if is_dark else "#1E1E2E"))
            self._calendar.setDateTextFormat(qd, event_fmt)

    def _iterate_month(self) -> List[QDate]:
        year = self._calendar.yearShown()
        month = self._calendar.monthShown()
        results = []
        qd = QDate(year, month, 1)
        while qd.month() == month:
            results.append(qd)
            qd = qd.addDays(1)
        return results

    def _on_date_selected(self, qd: QDate) -> None:
        date_str = qd.toString("yyyy-MM-dd")
        self._selected_date_label.setText(
            I18n._("calendar.events_for").format(date=qd.toString("dd.MM.yyyy (dddd)"))
        )
        events = self._events.get(date_str, [])
        events.sort(
            key=lambda e: (
                0 if e.get("_status") == "Просрочено" else 1,
                e.get("_dt", datetime.max) if e.get("_dt") else datetime.max,
            )
        )
        self._event_table.setRowCount(len(events))
        icon_map = {
            "violation": "⚠",
            "medical": "🏥",
            "reminder": "🔔",
        }
        for i, ev in enumerate(events):
            icon = icon_map.get(ev["type"], "📌")
            self._event_table.setItem(i, 0, QTableWidgetItem(f"{icon} {ev['title']}"))
            self._event_table.setItem(i, 1, QTableWidgetItem(ev["detail"]))
            self._event_table.setItem(i, 2, QTableWidgetItem(ev["date"]))
            status = ev.get("status", "")
            status_item = QTableWidgetItem(status)
            if status == "Просрочено":
                status_item.setForeground(QColor("#E74C3C"))
            elif status == "Исполнено":
                status_item.setForeground(QColor("#27AE60"))
            self._event_table.setItem(i, 3, status_item)
            self._event_table.item(i, 0).setData(Qt.UserRole, ev)

        self._event_table.resizeColumnsToContents()

    def _update_date_label(self) -> None:
        self._on_date_selected(self._calendar.selectedDate())

    def _on_event_double_click(self, item: QTableWidgetItem) -> None:
        row = item.row()
        ev_item = self._event_table.item(row, 0)
        if not ev_item:
            return
        ev = ev_item.data(Qt.UserRole) or {}
        table = ev.get("_table", "")
        rid = ev.get("_id")
        if table and rid:
            mw = self.window()
            if mw and hasattr(mw, "open_reminder_target"):
                mw.open_reminder_target(
                    {
                        "_table": table,
                        "_record_id": rid,
                    }
                )

    def _add_reminder_for_date(self) -> None:
        qd = self._calendar.selectedDate()
        default_date = qd.toString("dd.MM.yyyy")

        title, ok = QInputDialog.getText(
            self, I18n._("reminder.add"), I18n._("reminder.title_field")
        )
        if not ok or not title:
            return

        desc, ok2 = QInputDialog.getMultiLineText(
            self, I18n._("reminder.add"), I18n._("reminder.description")
        )
        if not ok2:
            desc = ""

        self.db.save_reminder(title.strip(), desc.strip(), default_date, 60)
        ToastNotification.notify(I18n._("calendar.reminder_added"), "success", 3000)
        self._load_events()

    def _refresh(self) -> None:
        self._load_events()

    def refresh(self) -> None:
        self._refresh()
