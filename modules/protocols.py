from datetime import datetime
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import Qt, QTimer
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


class ProtocolEditDialog(QDialog):
    def __init__(
        self, record: Optional[Dict[str, Any]] = None, parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._record = record or {}
        is_new = record is None
        self.setWindowTitle(I18n._("common.add") if is_new else I18n._("common.edit"))
        self.setMinimumSize(500, 400)
        self._build_ui()
        if not is_new:
            self._load_data()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(8)

        self._date_edit = QDateEdit()
        self._date_edit.setCalendarPopup(True)
        self._date_edit.setDate(datetime.now())
        self._date_edit.setMinimumHeight(32)
        form.addRow("Дата:", self._date_edit)

        self._topic_edit = GlassLineEdit()
        self._topic_edit.setPlaceholderText("Тема совещания")
        self._topic_edit.setMinimumHeight(32)
        form.addRow("Тема:", self._topic_edit)

        self._participants_edit = GlassLineEdit()
        self._participants_edit.setPlaceholderText("Участники (через запятую)")
        self._participants_edit.setMinimumHeight(32)
        form.addRow("Участники:", self._participants_edit)

        self._agenda_edit = QTextEdit()
        self._agenda_edit.setPlaceholderText("Повестка дня")
        self._agenda_edit.setMinimumHeight(80)
        form.addRow("Повестка:", self._agenda_edit)

        self._decisions_edit = QTextEdit()
        self._decisions_edit.setPlaceholderText("Принятые решения")
        self._decisions_edit.setMinimumHeight(80)
        form.addRow("Решения:", self._decisions_edit)

        self._status_combo = GlassComboBox()
        self._status_combo.addItems(["active", "completed", "cancelled"])
        self._status_combo.setMinimumHeight(32)
        form.addRow("Статус:", self._status_combo)

        layout.addLayout(form)
        layout.addSpacing(12)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _load_data(self) -> None:
        from datetime import date

        r = self._record
        try:
            self._date_edit.setDate(
                datetime.strptime(r.get("date", ""), "%Y-%m-%d").date()
            )
        except Exception:
            pass
        self._topic_edit.setText(r.get("topic", ""))
        self._participants_edit.setText(r.get("participants", ""))
        self._agenda_edit.setPlainText(r.get("agenda", ""))
        self._decisions_edit.setPlainText(r.get("decisions", ""))
        idx = self._status_combo.findText(r.get("status", "active"))
        if idx >= 0:
            self._status_combo.setCurrentIndex(idx)

    def _save(self) -> None:
        self._data = {
            "date": self._date_edit.date().toString("yyyy-MM-dd"),
            "topic": self._topic_edit.text().strip(),
            "participants": self._participants_edit.text().strip(),
            "agenda": self._agenda_edit.toPlainText().strip(),
            "decisions": self._decisions_edit.toPlainText().strip(),
            "status": self._status_combo.currentText(),
        }
        self.accept()

    def result_data(self) -> Dict[str, str]:
        return getattr(self, "_data", {})


class ProtocolsTab(QWidget):
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
        toolbar.setSpacing(6)

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
        layout.addLayout(toolbar)

        self._table = QTableWidget()
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels(
            ["ID", "Дата", "Тема", "Участники", "Решения", "Статус"]
        )
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self._table.verticalHeader().setVisible(False)
        self._table.setSortingEnabled(True)
        self._table.doubleClicked.connect(self._edit_selected)
        layout.addWidget(wrap_table_with_glow(self._table, self))

    def _load(self) -> None:
        try:
            self._records = self.db.fetch_all(
                "SELECT * FROM ot_protocols ORDER BY date DESC"
            )
        except Exception:
            self._records = []
        self._table.setRowCount(0)
        for r in self._records:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(str(r["id"])))
            self._table.setItem(row, 1, QTableWidgetItem(r.get("date", "")))
            self._table.setItem(row, 2, QTableWidgetItem(r.get("topic", "")[:60]))
            self._table.setItem(
                row, 3, QTableWidgetItem(r.get("participants", "")[:60])
            )
            self._table.setItem(row, 4, QTableWidgetItem(r.get("decisions", "")[:80]))
            status = r.get("status", "active")
            item = QTableWidgetItem(status)
            item.setForeground(
                QColor(
                    "#34C759"
                    if status == "completed"
                    else "#FF9500"
                    if status == "active"
                    else "#FF3B30"
                )
            )
            self._table.setItem(row, 5, item)
        self._table.resizeColumnsToContents()

    def _add(self) -> None:
        dlg = ProtocolEditDialog(None, self)
        if dlg.exec_() == QDialog.Accepted:
            data = dlg.result_data()
            try:
                self.db.execute(
                    "INSERT INTO ot_protocols (date, topic, participants, agenda, decisions, status) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        data["date"],
                        data["topic"],
                        data["participants"],
                        data["agenda"],
                        data["decisions"],
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
        dlg = ProtocolEditDialog(self._records[row], self)
        if dlg.exec_() == QDialog.Accepted:
            data = dlg.result_data()
            rid = self._records[row]["id"]
            try:
                self.db.execute(
                    "UPDATE ot_protocols SET date=?, topic=?, participants=?, agenda=?, decisions=?, status=? WHERE id=?",
                    (
                        data["date"],
                        data["topic"],
                        data["participants"],
                        data["agenda"],
                        data["decisions"],
                        data["status"],
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
                self.db.execute("DELETE FROM ot_protocols WHERE id=?", (rid,))
                self.db.conn.commit()
                self._load()
            except Exception as e:
                QMessageBox.warning(self, "Error", str(e))
