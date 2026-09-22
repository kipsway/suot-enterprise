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
    QComboBox,
    QListWidget,
    QListWidgetItem,
    QSplitter,
)

from app_core.i18n import I18n
from app_core.theme_engine import ThemeEngine
from app_core.utils import wrap_table_with_glow
from services.database import DatabaseManager
from widgets.glass_button import GlassButton
from widgets.glass_line_edit import GlassLineEdit
from widgets.toast import ToastNotification


class ChecklistEditDialog(QDialog):
    def __init__(
        self, record: Optional[Dict[str, Any]] = None, parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._record = record or {}
        self._items: List[str] = []
        self.setWindowTitle("Чек-лист")
        self.setMinimumSize(500, 400)
        self._build_ui()
        if record:
            self._load_data()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._title_edit = GlassLineEdit()
        self._title_edit.setPlaceholderText("Название чек-листа")
        self._title_edit.setMinimumHeight(32)
        form.addRow("Название:", self._title_edit)

        self._desc_edit = QTextEdit()
        self._desc_edit.setPlaceholderText("Описание")
        self._desc_edit.setMaximumHeight(60)
        form.addRow("Описание:", self._desc_edit)
        layout.addLayout(form)

        layout.addWidget(QLabel("Пункты чек-листа:"))
        self._item_input = GlassLineEdit()
        self._item_input.setPlaceholderText("Новый пункт...")
        self._item_input.setMinimumHeight(30)
        item_row = QHBoxLayout()
        item_row.addWidget(self._item_input, 1)
        add_item_btn = GlassButton("➕")
        add_item_btn.setFixedSize(30, 30)
        add_item_btn.clicked.connect(self._add_item)
        item_row.addWidget(add_item_btn)
        layout.addLayout(item_row)

        self._item_list = QListWidget()
        layout.addWidget(self._item_list, 1)

        btn_row = QHBoxLayout()
        del_item_btn = GlassButton("🗑 Удалить пункт")
        del_item_btn.clicked.connect(self._remove_item)
        btn_row.addWidget(del_item_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _add_item(self) -> None:
        text = self._item_input.text().strip()
        if text:
            self._items.append(text)
            QListWidgetItem(text, self._item_list)
            self._item_input.clear()

    def _remove_item(self) -> None:
        row = self._item_list.currentRow()
        if row >= 0:
            self._item_list.takeItem(row)
            if row < len(self._items):
                self._items.pop(row)

    def _load_data(self) -> None:
        r = self._record
        self._title_edit.setText(r.get("title", ""))
        self._desc_edit.setPlainText(r.get("description", ""))
        try:
            rows = self._db.fetch_all(
                "SELECT * FROM checklist_items WHERE checklist_id=? ORDER BY position",
                (r["id"],),
            )
            for row in rows:
                text = row["item_text"]
                self._items.append(text)
                QListWidgetItem(text, self._item_list)
        except Exception:
            pass

    def _save(self) -> None:
        self._data = {
            "title": self._title_edit.text().strip(),
            "description": self._desc_edit.toPlainText().strip(),
            "items": self._items[:],
        }
        self.accept()

    def result_data(self) -> Dict[str, Any]:
        return getattr(self, "_data", {})


class ChecklistsTab(QWidget):
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

        run_btn = GlassButton("✅ Провести инспекцию")
        run_btn.clicked.connect(self._run_inspection)
        toolbar.addWidget(run_btn)

        toolbar.addStretch()
        layout.addLayout(toolbar)

        splitter = QSplitter(Qt.Vertical)

        self._table = QTableWidget()
        self._table.setColumnCount(3)
        self._table.setHorizontalHeaderLabels(["ID", "Название", "Пунктов"])
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.verticalHeader().setVisible(False)
        self._table.doubleClicked.connect(self._edit_selected)
        splitter.addWidget(wrap_table_with_glow(self._table, self))

        self._results_table = QTableWidget()
        self._results_table.setColumnCount(4)
        self._results_table.setHorizontalHeaderLabels(
            ["ID", "Чек-лист", "Дата", "Статус"]
        )
        self._results_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._results_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._results_table.verticalHeader().setVisible(False)
        splitter.addWidget(self._results_table)

        layout.addWidget(splitter)

    def _load(self) -> None:
        try:
            self._records = self.db.fetch_all(
                "SELECT * FROM inspection_checklists ORDER BY id DESC"
            )
        except Exception:
            self._records = []
        self._table.setRowCount(0)
        for r in self._records:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(str(r["id"])))
            self._table.setItem(row, 1, QTableWidgetItem(r.get("title", "")))
            cnt = 0
            try:
                cur = self.db.conn.execute(
                    "SELECT COUNT(*) AS c FROM checklist_items WHERE checklist_id=?",
                    (r["id"],),
                )
                cnt = cur.fetchone()["c"]
            except Exception:
                pass
            self._table.setItem(row, 2, QTableWidgetItem(str(cnt)))
        self._table.resizeColumnsToContents()
        self._load_results()

    def _load_results(self) -> None:
        try:
            results = self.db.fetch_all(
                "SELECT r.*, c.title AS checklist_title FROM inspection_results r "
                "LEFT JOIN inspection_checklists c ON r.checklist_id=c.id "
                "ORDER BY r.id DESC LIMIT 50"
            )
        except Exception:
            results = []
        self._results_table.setRowCount(0)
        for r in results:
            row = self._results_table.rowCount()
            self._results_table.insertRow(row)
            self._results_table.setItem(row, 0, QTableWidgetItem(str(r["id"])))
            self._results_table.setItem(
                row, 1, QTableWidgetItem(r.get("checklist_title", ""))
            )
            self._results_table.setItem(
                row, 2, QTableWidgetItem(r.get("conducted_date", ""))
            )
            item = QTableWidgetItem(r.get("status", ""))
            item.setForeground(
                QColor("#34C759" if r.get("status") == "pass" else "#FF3B30")
            )
            self._results_table.setItem(row, 3, item)
        self._results_table.resizeColumnsToContents()

    def _add(self) -> None:
        dlg = ChecklistEditDialog(None, self)
        if dlg.exec_() == QDialog.Accepted:
            data = dlg.result_data()
            try:
                cur = self.db.conn.execute(
                    "INSERT INTO inspection_checklists (title, description) VALUES (?, ?)",
                    (data["title"], data["description"]),
                )
                cl_id = cur.lastrowid
                for i, item in enumerate(data.get("items", [])):
                    self.db.conn.execute(
                        "INSERT INTO checklist_items (checklist_id, item_text, position) "
                        "VALUES (?, ?, ?)",
                        (cl_id, item, i),
                    )
                self.db.conn.commit()
                self._load()
            except Exception as e:
                QMessageBox.warning(self, "Error", str(e))

    def _edit_selected(self) -> None:
        row = self._table.currentRow()
        if row < 0 or row >= len(self._records):
            return
        dlg = ChecklistEditDialog(self._records[row], self)
        dlg._db = self.db
        if dlg.exec_() == QDialog.Accepted:
            data = dlg.result_data()
            rid = self._records[row]["id"]
            try:
                self.db.conn.execute(
                    "UPDATE inspection_checklists SET title=?, description=? WHERE id=?",
                    (data["title"], data["description"], rid),
                )
                self.db.conn.execute(
                    "DELETE FROM checklist_items WHERE checklist_id=?", (rid,)
                )
                for i, item in enumerate(data.get("items", [])):
                    self.db.conn.execute(
                        "INSERT INTO checklist_items (checklist_id, item_text, position) "
                        "VALUES (?, ?, ?)",
                        (rid, item, i),
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
            "Удалить чек-лист?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            rid = self._records[row]["id"]
            try:
                self.db.conn.execute(
                    "DELETE FROM checklist_items WHERE checklist_id=?", (rid,)
                )
                self.db.conn.execute(
                    "DELETE FROM inspection_checklists WHERE id=?", (rid,)
                )
                self.db.conn.commit()
                self._load()
            except Exception as e:
                QMessageBox.warning(self, "Error", str(e))

    def _run_inspection(self) -> None:
        row = self._table.currentRow()
        if row < 0 or row >= len(self._records):
            return
        checklist = self._records[row]
        try:
            items = self.db.fetch_all(
                "SELECT * FROM checklist_items WHERE checklist_id=? ORDER BY position",
                (checklist["id"],),
            )
        except Exception:
            items = []
        dlg = InspectionDialog(checklist, items, self)
        if dlg.exec_() == QDialog.Accepted:
            self._load()


class InspectionDialog(QDialog):
    def __init__(
        self,
        checklist: Dict[str, Any],
        items: List[Dict[str, Any]],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._checklist = checklist
        self._items = items
        self._values: List[str] = ["na"] * len(items)
        self._comments: List[str] = [""] * len(items)
        self.setWindowTitle(f"Инспекция: {checklist.get('title', '')}")
        self.setMinimumSize(500, 400)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self._date_edit = QDateEdit()
        self._date_edit.setCalendarPopup(True)
        self._date_edit.setDate(datetime.now())
        form.addRow("Дата:", self._date_edit)

        self._inspector_edit = GlassLineEdit()
        self._inspector_edit.setPlaceholderText("Кто проводит")
        form.addRow("Проверяющий:", self._inspector_edit)
        layout.addLayout(form)

        self._item_widgets: List[tuple] = []
        for i, item in enumerate(self._items):
            row = QHBoxLayout()
            label = QLabel(item.get("item_text", f"Пункт {i + 1}"))
            label.setWordWrap(True)
            row.addWidget(label, 1)
            combo = QComboBox()
            combo.addItems(["yes", "no", "na"])
            combo.currentIndexChanged.connect(
                lambda idx, pos=i: self._on_value_changed(pos, idx)
            )
            row.addWidget(combo)
            comment_edit = GlassLineEdit()
            comment_edit.setPlaceholderText("Комментарий")
            comment_edit.textChanged.connect(
                lambda text, pos=i: self._on_comment_changed(pos, text)
            )
            row.addWidget(comment_edit)
            self._item_widgets.append((combo, comment_edit))
            layout.addLayout(row)

        layout.addSpacing(8)
        self._notes_edit = QTextEdit()
        self._notes_edit.setPlaceholderText("Общие заметки...")
        self._notes_edit.setMaximumHeight(80)
        layout.addWidget(QLabel("Заметки:"))
        layout.addWidget(self._notes_edit)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _on_value_changed(self, pos: int, idx: int) -> None:
        combo = self._item_widgets[pos][0]
        self._values[pos] = combo.currentText()

    def _on_comment_changed(self, pos: int, text: str) -> None:
        self._comments[pos] = text

    def _save(self) -> None:
        db = DatabaseManager()
        try:
            # Count pass/fail
            yes_count = self._values.count("yes")
            no_count = self._values.count("no")
            status = "pass" if no_count == 0 else "fail"

            cur = db.conn.execute(
                "INSERT INTO inspection_results (checklist_id, conducted_date, conducted_by, notes, status) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    self._checklist["id"],
                    self._date_edit.date().toString("yyyy-MM-dd"),
                    self._inspector_edit.text().strip(),
                    self._notes_edit.toPlainText().strip(),
                    status,
                ),
            )
            result_id = cur.lastrowid

            for i, item in enumerate(self._items):
                db.conn.execute(
                    "INSERT INTO inspection_result_items (result_id, item_id, value, comment) "
                    "VALUES (?, ?, ?, ?)",
                    (result_id, item["id"], self._values[i], self._comments[i]),
                )

            db.conn.commit()
            ToastNotification.notify("Инспекция сохранена", "success", 3000)
            self.accept()
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))
