from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QAbstractItemView,
    QInputDialog,
    QMessageBox,
    QWidget,
)

from app_core.i18n import I18n
from app_core.utils import wrap_table_with_glow
from services.database import DatabaseManager
from widgets.toast import ToastNotification


class ViolationTypeDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.db = DatabaseManager()
        self.setWindowTitle(I18n._("viol.types"))
        self.setMinimumSize(550, 400)
        self.resize(600, 450)
        self._build_ui()
        self._load()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)
        heading = QLabel(I18n._("viol.types"))
        heading.setProperty("heading", True)
        layout.addWidget(heading)

        self._table = QTableWidget()
        self._table.setColumnCount(3)
        self._table.setHorizontalHeaderLabels(
            [
                I18n._("viol.type_name"),
                I18n._("viol.risk_category"),
                I18n._("common.description"),
            ]
        )
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        layout.addWidget(wrap_table_with_glow(self._table, self))

        btn_layout = QHBoxLayout()
        add_btn = QPushButton(I18n._("common.add"))
        add_btn.setProperty("success", True)
        add_btn.clicked.connect(self._add)
        btn_layout.addWidget(add_btn)
        del_btn = QPushButton(I18n._("common.delete"))
        del_btn.setProperty("danger", True)
        del_btn.clicked.connect(self._delete)
        btn_layout.addWidget(del_btn)
        btn_layout.addStretch()
        close_btn = QPushButton(I18n._("common.close"))
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

    def _load(self) -> None:
        self._table.setRowCount(0)
        rows = self.db.fetch_all(
            "SELECT id, name, risk_category, description FROM violation_types ORDER BY name"
        )
        self._table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            self._table.setItem(i, 0, QTableWidgetItem(r["name"]))
            self._table.setItem(i, 1, QTableWidgetItem(r["risk_category"]))
            desc = QTableWidgetItem(r.get("description", ""))
            desc.setToolTip(r.get("description", ""))
            self._table.setItem(i, 2, desc)
        self._table.resizeColumnsToContents()

    def _add(self) -> None:
        name, ok = QInputDialog.getText(
            self, I18n._("viol.type_name"), I18n._("viol.type_name")
        )
        if not ok or not name:
            return
        risk, ok2 = QInputDialog.getItem(
            self,
            I18n._("viol.risk_category"),
            "",
            ["Низкая", "Средняя", "Высокая", "Критическая"],
            1,
            False,
        )
        if not ok2:
            return
        desc, ok3 = QInputDialog.getMultiLineText(
            self, I18n._("common.description"), I18n._("common.description")
        )
        if not ok3:
            desc = ""
        try:
            self.db.conn.execute(
                "INSERT INTO violation_types (name, risk_category, description) VALUES (?,?,?)",
                (name.strip(), risk, desc.strip()),
            )
            self.db.conn.commit()
            self._load()
            ToastNotification.notify(I18n._("common.success"), "success", 3000)
        except Exception:
            ToastNotification.notify(I18n._("error.generic"), "error", 5000)

    def _delete(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            return
        name = self._table.item(row, 0).text()
        reply = QMessageBox.question(
            self,
            I18n._("common.confirm"),
            f"{I18n._('common.delete')}: '{name}'?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.db.conn.execute("DELETE FROM violation_types WHERE name=?", (name,))
            self.db.conn.commit()
            self._load()
            ToastNotification.notify(I18n._("toast.delete_success"), "success", 3000)
