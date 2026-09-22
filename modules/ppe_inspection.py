from datetime import date, datetime
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from services.database import DatabaseManager
from widgets.glass_button import GlassButton
from widgets.glass_line_edit import GlassLineEdit
from widgets.glass_combo_box import GlassComboBox
from widgets.glass_checkbox import GlassCheckBox
from widgets.glass_table import apply_glass_table
from widgets.glass_scrollbar import apply_glass_scrollbars
from widgets.toast import ToastNotification

PPE_CATEGORIES = [
    "Защита головы",
    "Защита глаз",
    "Защита органов дыхания",
    "Защита рук",
    "Защита ног",
    "Защита от падений",
    "Спецодежда",
    "Защита слуха",
]
PPE_INSPECTION_STATUSES = ["Годен", "Требует замены", "Списан", "Просрочен"]


class PPEInspectionDialog(QDialog):
    def __init__(
        self, record: Optional[Dict[str, Any]] = None, parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent)
        self.db = DatabaseManager()
        self._record = record
        self.setWindowTitle("Инспекция СИЗ" if not record else "Редактирование СИЗ")
        self.setMinimumWidth(500)
        self.result_data: Optional[Dict[str, Any]] = None
        self._build_ui()
        if record:
            self._load_record()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        form = QFormLayout()
        form.setSpacing(6)

        self._employee = GlassLineEdit()
        self._employee.setPlaceholderText("ФИО сотрудника")
        form.addRow("Сотрудник:", self._employee)

        self._item_name = GlassLineEdit()
        self._item_name.setPlaceholderText("Наименование СИЗ")
        form.addRow("Наименование:", self._item_name)

        self._category = GlassComboBox()
        self._category.addItems(PPE_CATEGORIES)
        form.addRow("Категория:", self._category)

        self._serial = GlassLineEdit()
        self._serial.setPlaceholderText("Серийный номер / партия")
        form.addRow("Серийный №:", self._serial)

        self._issue_date = QDateEdit()
        self._issue_date.setCalendarPopup(True)
        self._issue_date.setDate(datetime.now().date())
        form.addRow("Дата выдачи:", self._issue_date)

        self._expiry_date = QDateEdit()
        self._expiry_date.setCalendarPopup(True)
        self._expiry_date.setDate(datetime.now().date())
        form.addRow("Срок годности:", self._expiry_date)

        self._status = GlassComboBox()
        self._status.addItems(PPE_INSPECTION_STATUSES)
        form.addRow("Статус:", self._status)

        self._notes = QTextEdit()
        self._notes.setPlaceholderText("Замечания по инспекции")
        self._notes.setMaximumHeight(80)
        form.addRow("Заметки:", self._notes)

        self._needs_replacement = GlassCheckBox("Требует замены")
        form.addRow("", self._needs_replacement)

        layout.addLayout(form)

        btn_row = QHBoxLayout()
        self._save_btn = GlassButton("💾 Сохранить")
        self._save_btn.clicked.connect(self._save)
        btn_row.addStretch()
        btn_row.addWidget(self._save_btn)
        cancel_btn = GlassButton("Отмена", variant="ghost")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def _load_record(self) -> None:
        dj = self._record.get("data_json", {})
        if not dj:
            return
        self._employee.setText(dj.get("employee", ""))
        self._item_name.setText(dj.get("item_name", ""))
        idx = self._category.findText(dj.get("category", ""))
        if idx >= 0:
            self._category.setCurrentIndex(idx)
        self._serial.setText(dj.get("serial", ""))
        try:
            self._issue_date.setDate(date.fromisoformat(dj.get("issue_date", "")))
        except (ValueError, TypeError):
            pass
        try:
            self._expiry_date.setDate(date.fromisoformat(dj.get("expiry_date", "")))
        except (ValueError, TypeError):
            pass
        idx = self._status.findText(dj.get("status", ""))
        if idx >= 0:
            self._status.setCurrentIndex(idx)
        self._notes.setText(dj.get("notes", ""))
        self._needs_replacement.setChecked(dj.get("needs_replacement", False))

    def _save(self) -> None:
        item_name = self._item_name.text().strip()
        if not item_name:
            QMessageBox.warning(self, "Ошибка", "Наименование СИЗ обязательно")
            return
        data = {
            "employee": self._employee.text().strip(),
            "item_name": item_name,
            "category": self._category.currentText(),
            "serial": self._serial.text().strip(),
            "issue_date": self._issue_date.date().toString("yyyy-MM-dd"),
            "expiry_date": self._expiry_date.date().toString("yyyy-MM-dd"),
            "status": self._status.currentText(),
            "notes": self._notes.toPlainText().strip(),
            "needs_replacement": self._needs_replacement.isChecked(),
            "inspection_date": datetime.now().strftime("%Y-%m-%d"),
        }
        self.result_data = data
        self.accept()


class PPEInspectionWidget(QWidget):
    def __init__(self, user_id: int = 0, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.db = DatabaseManager()
        self._user_id = user_id
        self._build_ui()
        self._load_data()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        toolbar = QHBoxLayout()
        self._add_btn = GlassButton("➕ Добавить")
        self._add_btn.clicked.connect(self._add)
        toolbar.addWidget(self._add_btn)
        self._edit_btn = GlassButton("✏️ Инспектировать")
        self._edit_btn.clicked.connect(self._edit)
        toolbar.addWidget(self._edit_btn)
        self._delete_btn = GlassButton("🗑️ Удалить", variant="ghost")
        self._delete_btn.clicked.connect(self._delete)
        toolbar.addWidget(self._delete_btn)
        toolbar.addWidget(QLabel("Категория:"))
        self._filter_cat = GlassComboBox()
        self._filter_cat.addItems(["Все"] + PPE_CATEGORIES)
        self._filter_cat.currentTextChanged.connect(lambda _: self._load_data())
        toolbar.addWidget(self._filter_cat)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self._table = QTableWidget(self)
        apply_glass_table(self._table)
        apply_glass_scrollbars(self._table)
        self._table.setColumnCount(9)
        self._table.setHorizontalHeaderLabels(
            [
                "ID",
                "Сотрудник",
                "СИЗ",
                "Категория",
                "Серийный №",
                "Выдан",
                "Годен до",
                "Статус",
                "Замена",
            ]
        )
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._table.doubleClicked.connect(self._edit)
        layout.addWidget(self._table, 1)

    def _load_data(self) -> None:
        records = self.db.get_json_records("ppe_inspections")
        cat_filter = self._filter_cat.currentText()

        self._table.setRowCount(0)
        for rec in records:
            dj = rec.get("data_json", {})
            if cat_filter != "Все" and dj.get("category") != cat_filter:
                continue
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(str(rec["id"])))
            self._table.setItem(row, 1, QTableWidgetItem(dj.get("employee", "")))
            self._table.setItem(row, 2, QTableWidgetItem(dj.get("item_name", "")))
            self._table.setItem(row, 3, QTableWidgetItem(dj.get("category", "")))
            self._table.setItem(row, 4, QTableWidgetItem(dj.get("serial", "")))
            self._table.setItem(row, 5, QTableWidgetItem(dj.get("issue_date", "")))
            self._table.setItem(row, 6, QTableWidgetItem(dj.get("expiry_date", "")))
            self._table.setItem(row, 7, QTableWidgetItem(dj.get("status", "")))
            self._table.setItem(
                row, 8, QTableWidgetItem("⚠️" if dj.get("needs_replacement") else "✅")
            )

            expiry = dj.get("expiry_date", "")
            if expiry:
                try:
                    exp_date = datetime.strptime(expiry, "%Y-%m-%d")
                    if exp_date < datetime.now():
                        for col in range(self._table.columnCount()):
                            self._table.item(row, col).setBackground(
                                QColor(255, 69, 58, 25)
                            )
                except ValueError:
                    pass

        self._table.resizeColumnsToContents()

    def _add(self) -> None:
        dlg = PPEInspectionDialog(parent=self)
        if dlg.exec_() == QDialog.Accepted and dlg.result_data:
            self.db.save_json_record("ppe_inspections", 0, dlg.result_data)
            ToastNotification.notify("СИЗ добавлен", "success")
            self._load_data()

    def _edit(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            return
        rid = int(self._table.item(row, 0).text())
        records = self.db.get_json_records("ppe_inspections")
        rec = next((r for r in records if r["id"] == rid), None)
        if not rec:
            return
        dlg = PPEInspectionDialog(record=rec, parent=self)
        if dlg.exec_() == QDialog.Accepted and dlg.result_data:
            self.db.save_json_record("ppe_inspections", rid, dlg.result_data)
            ToastNotification.notify("СИЗ обновлён", "success")
            self._load_data()

    def _delete(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            return
        rid = int(self._table.item(row, 0).text())
        if (
            QMessageBox.question(
                self,
                "Подтверждение",
                "Удалить запись СИЗ?",
                QMessageBox.Yes | QMessageBox.No,
            )
            != QMessageBox.Yes
        ):
            return
        self.db.delete_json_record("ppe_inspections", rid)
        ToastNotification.notify("Запись удалена", "warning")
        self._load_data()
