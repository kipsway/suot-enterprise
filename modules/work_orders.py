from datetime import datetime, timedelta
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
from widgets.glass_table import apply_glass_table
from widgets.glass_scrollbar import apply_glass_scrollbars
from widgets.toast import ToastNotification

WORK_ORDER_TYPES = ["Предписание", "Предупреждение", "Предписание с приостановкой"]
WORK_ORDER_STATUSES = ["Открыто", "В работе", "Выполнено", "Просрочено", "Отменено"]
WORK_ORDER_PRIORITIES = ["Низкий", "Средний", "Высокий", "Критический"]


class WorkOrderEditDialog(QDialog):
    def __init__(
        self, record: Optional[Dict[str, Any]] = None, parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent)
        self.db = DatabaseManager()
        self._record = record
        self.setWindowTitle(
            "Предписание" if not record else "Редактирование предписания"
        )
        self.setMinimumWidth(520)
        self.result_data: Optional[Dict[str, Any]] = None
        self._build_ui()
        if record:
            self._load_record()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        form = QFormLayout()
        form.setSpacing(6)

        self._order_type = GlassComboBox()
        self._order_type.addItems(WORK_ORDER_TYPES)
        form.addRow("Тип:", self._order_type)

        self._title = GlassLineEdit()
        self._title.setPlaceholderText("Краткое описание")
        form.addRow("Заголовок:", self._title)

        self._description = QTextEdit()
        self._description.setPlaceholderText("Подробное описание нарушения/требования")
        self._description.setMaximumHeight(100)
        form.addRow("Описание:", self._description)

        self._responsible = GlassLineEdit()
        self._responsible.setPlaceholderText("ФИО ответственного")
        form.addRow("Ответственный:", self._responsible)

        self._deadline = QDateEdit()
        self._deadline.setCalendarPopup(True)
        self._deadline.setDate(datetime.now().date() + timedelta(days=30))
        form.addRow("Срок:", self._deadline)

        self._priority = GlassComboBox()
        self._priority.addItems(WORK_ORDER_PRIORITIES)
        form.addRow("Приоритет:", self._priority)

        self._status = GlassComboBox()
        self._status.addItems(WORK_ORDER_STATUSES)
        form.addRow("Статус:", self._status)

        self._location = GlassLineEdit()
        self._location.setPlaceholderText("Цех, участок, объект")
        form.addRow("Объект:", self._location)

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
        dj = self._record.get("data_json", {}) if self._record else {}
        if not dj:
            return
        idx = self._order_type.findText(dj.get("order_type", ""))
        if idx >= 0:
            self._order_type.setCurrentIndex(idx)
        self._title.setText(dj.get("title", ""))
        self._description.setText(dj.get("description", ""))
        self._responsible.setText(dj.get("responsible", ""))
        try:
            self._deadline.setDate(
                datetime.strptime(dj.get("deadline", ""), "%Y-%m-%d").date()
            )
        except (ValueError, TypeError):
            pass
        idx = self._priority.findText(dj.get("priority", ""))
        if idx >= 0:
            self._priority.setCurrentIndex(idx)
        idx = self._status.findText(dj.get("status", ""))
        if idx >= 0:
            self._status.setCurrentIndex(idx)
        self._location.setText(dj.get("location", ""))

    def _save(self) -> None:
        title = self._title.text().strip()
        if not title:
            QMessageBox.warning(self, "Ошибка", "Заголовок обязателен")
            return
        data = {
            "order_type": self._order_type.currentText(),
            "title": title,
            "description": self._description.toPlainText().strip(),
            "responsible": self._responsible.text().strip(),
            "deadline": self._deadline.date().toString("yyyy-MM-dd"),
            "priority": self._priority.currentText(),
            "status": self._status.currentText(),
            "location": self._location.text().strip(),
            "created_at": datetime.now().strftime("%Y-%m-%d"),
        }
        self.result_data = data
        self.accept()


class WorkOrdersTableWidget(QWidget):
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
        self._edit_btn = GlassButton("✏️ Редактировать")
        self._edit_btn.clicked.connect(self._edit)
        toolbar.addWidget(self._edit_btn)
        self._delete_btn = GlassButton("🗑️ Удалить", variant="ghost")
        self._delete_btn.clicked.connect(self._delete)
        toolbar.addWidget(self._delete_btn)
        toolbar.addWidget(QLabel("Статус:"))
        self._filter_status = GlassComboBox()
        self._filter_status.addItems(["Все"] + WORK_ORDER_STATUSES)
        self._filter_status.currentTextChanged.connect(lambda _: self._load_data())
        toolbar.addWidget(self._filter_status)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self._table = QTableWidget(self)
        apply_glass_table(self._table)
        apply_glass_scrollbars(self._table)
        self._table.setColumnCount(8)
        self._table.setHorizontalHeaderLabels(
            [
                "ID",
                "Тип",
                "Заголовок",
                "Ответственный",
                "Срок",
                "Приоритет",
                "Статус",
                "Объект",
            ]
        )
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._table.doubleClicked.connect(self._edit)
        layout.addWidget(self._table, 1)

    def _load_data(self) -> None:
        records = self.db.get_json_records("work_orders")
        status_filter = self._filter_status.currentText()

        self._table.setRowCount(0)
        for rec in records:
            dj = rec.get("data_json", {})
            if status_filter != "Все" and dj.get("status") != status_filter:
                continue
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(str(rec["id"])))
            self._table.setItem(row, 1, QTableWidgetItem(dj.get("order_type", "")))
            self._table.setItem(row, 2, QTableWidgetItem(dj.get("title", "")))
            self._table.setItem(row, 3, QTableWidgetItem(dj.get("responsible", "")))
            self._table.setItem(row, 4, QTableWidgetItem(dj.get("deadline", "")))
            self._table.setItem(row, 5, QTableWidgetItem(dj.get("priority", "")))
            self._table.setItem(row, 6, QTableWidgetItem(dj.get("status", "")))
            self._table.setItem(row, 7, QTableWidgetItem(dj.get("location", "")))

            status = dj.get("status", "")
            if status == "Просрочено":
                color = QColor(255, 69, 58, 30)
                for col in range(self._table.columnCount()):
                    self._table.item(row, col).setBackground(color)
            elif status == "Выполнено":
                color = QColor(48, 209, 88, 20)
                for col in range(self._table.columnCount()):
                    self._table.item(row, col).setBackground(color)

        self._table.resizeColumnsToContents()

    def _add(self) -> None:
        dlg = WorkOrderEditDialog(parent=self)
        if dlg.exec_() == QDialog.Accepted and dlg.result_data:
            self.db.save_json_record("work_orders", 0, dlg.result_data)
            self.db.log_event("Предписание создано", "INFO")
            ToastNotification.notify("Предписание добавлено", "success")
            self._load_data()

    def _edit(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            return
        rid = int(self._table.item(row, 0).text())
        records = self.db.get_json_records("work_orders")
        rec = next((r for r in records if r["id"] == rid), None)
        if not rec:
            return
        dlg = WorkOrderEditDialog(record=rec, parent=self)
        if dlg.exec_() == QDialog.Accepted and dlg.result_data:
            self.db.save_json_record("work_orders", rid, dlg.result_data)
            ToastNotification.notify("Предписание обновлено", "success")
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
                "Удалить предписание?",
                QMessageBox.Yes | QMessageBox.No,
            )
            != QMessageBox.Yes
        ):
            return
        self.db.delete_json_record("work_orders", rid)
        ToastNotification.notify("Предписание удалено", "warning")
        self._load_data()
