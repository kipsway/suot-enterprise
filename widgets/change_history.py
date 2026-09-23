"""Change History UI — view changes, diff viewer, rollback."""

from typing import Any, Dict, List, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QMessageBox,
    QWidget,
)

from app_core.i18n import I18n
from services.database import DatabaseManager


class ChangeHistoryDialog(QDialog):
    def __init__(
        self, table: str, record_id: int, parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._db = DatabaseManager()
        self._table = table
        self._record_id = record_id
        self.setWindowTitle(f"История изменений — {table}#{record_id}")
        self.setMinimumSize(700, 450)
        self.resize(800, 500)
        self._build_ui()
        self._load()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        heading = QLabel(f"История изменений: {self._table} #{self._record_id}")
        heading.setProperty("heading", True)
        layout.addWidget(heading)

        self._table_widget = QTableWidget(0, 5)
        self._table_widget.setHorizontalHeaderLabels(
            ["Дата", "Поле", "Было", "Стало", "Пользователь"]
        )
        self._table_widget.horizontalHeader().setStretchLastSection(True)
        self._table_widget.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.Stretch
        )
        self._table_widget.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.Stretch
        )
        self._table_widget.setSelectionBehavior(QTableWidget.SelectRows)
        self._table_widget.setAlternatingRowColors(True)
        self._table_widget.verticalHeader().setVisible(False)
        self._table_widget.itemSelectionChanged.connect(self._on_select)
        layout.addWidget(self._table_widget)

        diff_label = QLabel("Просмотр изменений:")
        diff_label.setProperty("heading", True)
        layout.addWidget(diff_label)

        diff_layout = QHBoxLayout()
        self._old_view = QTextEdit()
        self._old_view.setReadOnly(True)
        self._old_view.setMaximumHeight(120)
        self._old_view.setStyleSheet(
            "background: rgba(255,59,48,0.06); border: 1px solid rgba(255,59,48,0.2);"
            " border-radius: 8px; padding: 8px;"
        )
        diff_layout.addWidget(QLabel("Было:"))
        diff_layout.addWidget(self._old_view)

        self._new_view = QTextEdit()
        self._new_view.setReadOnly(True)
        self._new_view.setMaximumHeight(120)
        self._new_view.setStyleSheet(
            "background: rgba(52,199,89,0.06); border: 1px solid rgba(52,199,89,0.2);"
            " border-radius: 8px; padding: 8px;"
        )
        diff_layout.addWidget(QLabel("Стало:"))
        diff_layout.addWidget(self._new_view)
        layout.addLayout(diff_layout)

        self._rollback_btn = QPushButton("↩ Откатить выбранное изменение")
        self._rollback_btn.clicked.connect(self._rollback)
        self._rollback_btn.setEnabled(False)
        layout.addWidget(self._rollback_btn)

    def _load(self) -> None:
        changes = self._db.get_change_history(self._table, self._record_id)
        self._table_widget.setRowCount(len(changes))
        for i, c in enumerate(changes):
            self._table_widget.setItem(i, 0, QTableWidgetItem(c.get("created_at", "")))
            self._table_widget.setItem(i, 1, QTableWidgetItem(c.get("field", "")))
            self._table_widget.setItem(i, 2, QTableWidgetItem(c.get("old_value", "")))
            self._table_widget.setItem(i, 3, QTableWidgetItem(c.get("new_value", "")))
            self._table_widget.setItem(i, 4, QTableWidgetItem(c.get("username", "")))
            self._table_widget.item(i, 0).setData(Qt.UserRole, c.get("id"))

    def _on_select(self) -> None:
        row = self._table_widget.currentRow()
        if row >= 0:
            old_val = self._table_widget.item(row, 2).text()
            new_val = self._table_widget.item(row, 3).text()
            self._old_view.setPlainText(old_val)
            self._new_view.setPlainText(new_val)
            self._rollback_btn.setEnabled(True)
        else:
            self._old_view.clear()
            self._new_view.clear()
            self._rollback_btn.setEnabled(False)

    def _rollback(self) -> None:
        row = self._table_widget.currentRow()
        if row < 0:
            return
        h_id = self._table_widget.item(row, 0).data(Qt.UserRole)
        if not h_id:
            return
        ret = QMessageBox.question(
            self,
            "Подтверждение отката",
            "Восстановить старое значение для этого поля?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if ret == QMessageBox.Yes:
            if self._db.rollback_change(h_id):
                QMessageBox.information(self, "Готово", "Изменение откачено.")
                self._load()
            else:
                QMessageBox.warning(self, "Ошибка", "Не удалось откатить изменение.")


def show_change_history(
    table: str, record_id: int, parent: Optional[QWidget] = None
) -> None:
    dlg = ChangeHistoryDialog(table, record_id, parent)
    dlg.exec_()
