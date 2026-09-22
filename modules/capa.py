from datetime import datetime
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QMessageBox,
    QDateEdit,
)

from app_core.i18n import I18n
from app_core.theme_engine import ThemeEngine
from app_core.utils import wrap_table_with_glow
from services.database import DatabaseManager
from widgets.glass_button import GlassButton
from widgets.glass_line_edit import GlassLineEdit
from widgets.glass_combo_box import GlassComboBox


class CAPAEditDialog(QDialog):
    def __init__(
        self, record: Optional[Dict[str, Any]] = None, parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._record = record or {}
        self.setWindowTitle("CAPA")
        self.setMinimumSize(550, 450)
        self._build_ui()
        if record:
            self._load_data()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(8)

        self._title_edit = GlassLineEdit()
        self._title_edit.setPlaceholderText("Краткое описание")
        self._title_edit.setMinimumHeight(32)
        form.addRow("Название:", self._title_edit)

        self._desc_edit = QTextEdit()
        self._desc_edit.setPlaceholderText("Описание проблемы")
        self._desc_edit.setMinimumHeight(60)
        form.addRow("Описание:", self._desc_edit)

        self._root_cause_edit = QTextEdit()
        self._root_cause_edit.setPlaceholderText("Корневая причина")
        self._root_cause_edit.setMinimumHeight(60)
        form.addRow("Корневая причина:", self._root_cause_edit)

        self._action_plan_edit = QTextEdit()
        self._action_plan_edit.setPlaceholderText("План корректирующих действий")
        self._action_plan_edit.setMinimumHeight(60)
        form.addRow("План действий:", self._action_plan_edit)

        self._severity_combo = GlassComboBox()
        self._severity_combo.addItems(["low", "medium", "high", "critical"])
        self._severity_combo.setMinimumHeight(32)
        form.addRow("Серьёзность:", self._severity_combo)

        self._assigned_edit = GlassLineEdit()
        self._assigned_edit.setPlaceholderText("ФИО ответственного")
        self._assigned_edit.setMinimumHeight(32)
        form.addRow("Назначено:", self._assigned_edit)

        self._deadline_edit = QDateEdit()
        self._deadline_edit.setCalendarPopup(True)
        self._deadline_edit.setDate(datetime.now())
        self._deadline_edit.setMinimumHeight(32)
        form.addRow("Срок:", self._deadline_edit)

        self._status_combo = GlassComboBox()
        self._status_combo.addItems(["open", "in_progress", "closed", "cancelled"])
        self._status_combo.setMinimumHeight(32)
        form.addRow("Статус:", self._status_combo)

        layout.addLayout(form)
        layout.addSpacing(12)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _load_data(self) -> None:
        r = self._record
        self._title_edit.setText(r.get("title", ""))
        self._desc_edit.setPlainText(r.get("description", ""))
        self._root_cause_edit.setPlainText(r.get("root_cause", ""))
        self._action_plan_edit.setPlainText(r.get("action_plan", ""))
        sidx = self._severity_combo.findText(r.get("severity", "medium"))
        if sidx >= 0:
            self._severity_combo.setCurrentIndex(sidx)
        self._assigned_edit.setText(r.get("assigned_to", ""))
        try:
            from datetime import date

            dd = self._record.get("deadline", "")
            if dd:
                self._deadline_edit.setDate(datetime.strptime(dd, "%Y-%m-%d").date())
        except Exception:
            pass
        stidx = self._status_combo.findText(r.get("status", "open"))
        if stidx >= 0:
            self._status_combo.setCurrentIndex(stidx)

    def _save(self) -> None:
        self._data = {
            "title": self._title_edit.text().strip(),
            "description": self._desc_edit.toPlainText().strip(),
            "root_cause": self._root_cause_edit.toPlainText().strip(),
            "action_plan": self._action_plan_edit.toPlainText().strip(),
            "severity": self._severity_combo.currentText(),
            "assigned_to": self._assigned_edit.text().strip(),
            "deadline": self._deadline_edit.date().toString("yyyy-MM-dd"),
            "status": self._status_combo.currentText(),
        }
        self.accept()

    def result_data(self) -> Dict[str, str]:
        return getattr(self, "_data", {})


class CAPATab(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.db = DatabaseManager()
        self._records: List[Dict[str, Any]] = []
        self._build_ui()
        self._load()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        toolbar = QHBoxLayout()
        add_btn = GlassButton("➕ " + I18n._("common.add"))
        add_btn.clicked.connect(self._add)
        toolbar.addWidget(add_btn)

        edit_btn = GlassButton("✏️ " + I18n._("common.edit"))
        edit_btn.clicked.connect(self._edit_selected)
        toolbar.addWidget(edit_btn)

        del_btn = GlassButton("🗑 " + I18n._("common.delete"))
        del_btn.clicked.connect(self._delete_selected)
        toolbar.addWidget(del_btn)

        refresh_btn = GlassButton("🔄")
        refresh_btn.setFixedSize(32, 32)
        refresh_btn.setProperty("flat", True)
        refresh_btn.clicked.connect(self._load)
        toolbar.addWidget(refresh_btn)
        toolbar.addStretch()

        self._filter_combo = GlassComboBox()
        self._filter_combo.addItems(
            ["all", "open", "in_progress", "closed", "cancelled"]
        )
        self._filter_combo.setMinimumHeight(32)
        self._filter_combo.currentTextChanged.connect(self._load)
        toolbar.addWidget(QLabel("Фильтр:"))
        toolbar.addWidget(self._filter_combo)

        layout.addLayout(toolbar)

        self._table = QTableWidget()
        self._table.setColumnCount(8)
        self._table.setHorizontalHeaderLabels(
            [
                "ID",
                "Название",
                "Серьёзность",
                "Статус",
                "Назначено",
                "Срок",
                "Корневая причина",
                "Создан",
            ]
        )
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setSortingEnabled(True)
        self._table.doubleClicked.connect(self._edit_selected)
        layout.addWidget(wrap_table_with_glow(self._table, self))

    def _load(self) -> None:
        try:
            filt = self._filter_combo.currentText()
            query = "SELECT * FROM capa_records"
            params: tuple = ()
            if filt != "all":
                query += " WHERE status=?"
                params = (filt,)
            query += " ORDER BY id DESC"
            self._records = self.db.fetch_all(query, params)
        except Exception:
            self._records = []
        self._table.setRowCount(0)
        sev_colors = {
            "low": "#34C759",
            "medium": "#FF9500",
            "high": "#FF3B30",
            "critical": "#FF2D55",
        }
        for r in self._records:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(str(r["id"])))
            self._table.setItem(row, 1, QTableWidgetItem(r.get("title", "")[:60]))
            sev = r.get("severity", "medium")
            sev_item = QTableWidgetItem(sev)
            sev_item.setForeground(QColor(sev_colors.get(sev, "#888")))
            self._table.setItem(row, 2, sev_item)
            st = r.get("status", "open")
            st_item = QTableWidgetItem(st)
            st_item.setForeground(
                QColor(
                    "#34C759"
                    if st == "closed"
                    else "#FF9500"
                    if st == "in_progress"
                    else "#FF3B30"
                )
            )
            self._table.setItem(row, 3, st_item)
            self._table.setItem(row, 4, QTableWidgetItem(r.get("assigned_to", "")))
            self._table.setItem(row, 5, QTableWidgetItem(r.get("deadline", "")))
            self._table.setItem(row, 6, QTableWidgetItem(r.get("root_cause", "")[:40]))
            self._table.setItem(row, 7, QTableWidgetItem(r.get("created_at", "")[:10]))
        self._table.resizeColumnsToContents()

    def _add(self) -> None:
        dlg = CAPAEditDialog(None, self)
        if dlg.exec_() == QDialog.Accepted:
            data = dlg.result_data()
            try:
                self.db.execute(
                    "INSERT INTO capa_records (title, description, root_cause, action_plan, "
                    "severity, assigned_to, deadline, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        data["title"],
                        data["description"],
                        data["root_cause"],
                        data["action_plan"],
                        data["severity"],
                        data["assigned_to"],
                        data["deadline"],
                        data["status"],
                    ),
                )
                self.db.conn.commit()
                self._load()
            except Exception as e:
                QMessageBox.warning(self, "Error", str(e))

    def _edit_selected(self) -> None:
        row = self._table.currentRow()
        if row < 0 or row >= len(self._records):
            return
        dlg = CAPAEditDialog(self._records[row], self)
        if dlg.exec_() == QDialog.Accepted:
            data = dlg.result_data()
            rid = self._records[row]["id"]
            closed = data["status"]
            closed_date = (
                datetime.now().strftime("%Y-%m-%d") if closed == "closed" else ""
            )
            try:
                self.db.execute(
                    "UPDATE capa_records SET title=?, description=?, root_cause=?, action_plan=?, "
                    "severity=?, assigned_to=?, deadline=?, status=?, closed_date=? WHERE id=?",
                    (
                        data["title"],
                        data["description"],
                        data["root_cause"],
                        data["action_plan"],
                        data["severity"],
                        data["assigned_to"],
                        data["deadline"],
                        data["status"],
                        closed_date,
                        rid,
                    ),
                )
                self.db.conn.commit()
                self._load()
            except Exception as e:
                QMessageBox.warning(self, "Error", str(e))

    def _delete_selected(self) -> None:
        row = self._table.currentRow()
        if row < 0 or row >= len(self._records):
            return
        reply = QMessageBox.question(
            self,
            I18n._("common.confirm"),
            I18n._("common.delete") + "?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            rid = self._records[row]["id"]
            try:
                self.db.execute("DELETE FROM capa_records WHERE id=?", (rid,))
                self.db.conn.commit()
                self._load()
            except Exception as e:
                QMessageBox.warning(self, "Error", str(e))
