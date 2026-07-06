import csv
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QCursor
from PyQt5.QtWidgets import (QApplication, QDialog, QWidget, QFrame,
                             QVBoxLayout, QHBoxLayout, QFormLayout,
                             QLabel, QLineEdit, QPushButton, QComboBox,
                             QTextEdit, QScrollArea,
                             QTableWidget, QTableWidgetItem, QHeaderView,
                             QAbstractItemView, QDialogButtonBox, QMenu,
                             QMessageBox, QFileDialog)

from app_core.i18n import I18n
from app_core.utils import wrap_table_with_glow, get_status_indicator_bg
from services.database import DatabaseManager
from widgets.toast import ToastNotification
from widgets.inline_edit_mixin import InlineEditMixin
from widgets.column_width_mixin import ColumnWidthMixin
from modules.textbook import DateAwareLineEdit

TABLE_NAME = "permits"
WORK_TYPES = [
    "Работы на высоте", "Электротехнические работы",
    "Огневые работы", "Работы в замкнутом пространстве",
    "Земляные работы", "Грузоподъёмные работы",
    "Работы с вредными веществами", "Радиационно-опасные работы",
    "Ремонтные работы", "Строительно-монтажные работы"]
PERMIT_STATUSES = ["Оформлен", "Действует", "Приостановлен", "Закрыт", "Аннулирован"]


class PermitEditDialog(QDialog):
    def __init__(self, data: Dict[str, Any] = None,
                 columns: List[Dict[str, Any]] = None,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._data = dict(data or {})
        self._columns = columns or []
        self._fields: Dict[str, QWidget] = {}
        self.setWindowTitle(I18n._("permits.edit") if data else I18n._("permits.add"))
        self.setMinimumSize(720, 620)
        self.resize(880, 720)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(10)
        heading = QLabel(I18n._("permits.edit") if self._data.get("id") else I18n._("permits.add"))
        heading.setProperty("heading", True)
        layout.addWidget(heading)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        container = QWidget()
        form = QFormLayout(container)
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight)
        for col in self._columns:
            name = col["name"]
            typ = col["type"]
            if name == "ID":
                continue
            value = self._data.get(name, "")
            if typ == "Число":
                w = QSpinBox()
                w.setRange(0, 999999999)
                w.setMinimumHeight(36)
                try:
                    w.setValue(int(float(str(value).replace(" ", "").replace(",", "."))))
                except Exception:
                    w.setValue(0)
            elif typ in ("Дата", "Годен до", "Дата проведения", "Date", "Date of", "Valid until"):
                w = DateAwareLineEdit()
                w.setMinimumHeight(36)
                w.setText(str(value))
            elif typ == "Статус":
                w = QComboBox()
                w.setMinimumHeight(36)
                if name == "Тип работ":
                    w.addItems(WORK_TYPES)
                else:
                    w.addItems(PERMIT_STATUSES)
                idx = w.findText(str(value))
                if idx >= 0:
                    w.setCurrentIndex(idx)
            elif name in ("Описание работ", "Меры безопасности", "Состав бригады"):
                w = QTextEdit()
                w.setMinimumHeight(70)
                w.setPlainText(str(value))
            else:
                w = QLineEdit()
                w.setMinimumHeight(36)
                w.setText(str(value))
            self._fields[name] = w
            form.addRow(f"{name}:", w)
        scroll.setWidget(container)
        layout.addWidget(scroll, 1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_data(self) -> Dict[str, Any]:
        result = dict(self._data)
        for col in self._columns:
            name = col["name"]
            if name == "ID":
                continue
            w = self._fields.get(name)
            if w is None:
                continue
            if isinstance(w, QSpinBox):
                result[name] = str(w.value())
            elif isinstance(w, QComboBox):
                result[name] = w.currentText()
            elif isinstance(w, QTextEdit):
                result[name] = w.toPlainText().strip()
            else:
                result[name] = w.text().strip()
        return result


class PermitsTableWidget(QWidget, InlineEditMixin, ColumnWidthMixin):
    TABLE_NAME = "permits"

    def __init__(self, parent: Optional[QWidget] = None,
                 user_id: int = 0) -> None:
        super().__init__(parent)
        self.db = DatabaseManager()
        self._user_id = user_id
        self._columns: List[Dict[str, Any]] = []
        self._records: List[Dict[str, Any]] = []
        self._all_records: List[Dict[str, Any]] = []
        self._sort_col: int = -1
        self._sort_order: int = Qt.AscendingOrder
        self._build_ui()
        self._load_data()

    def set_user_id(self, uid: int) -> None:
        self._user_id = uid
        self._load_data()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        self._search_edit = QLineEdit()
        self._search_edit.setProperty("search", True)
        self._search_edit.setPlaceholderText(I18n._("search.placeholder"))
        self._search_edit.setMinimumHeight(36)
        self._search_timer = QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(self._apply_filter)
        self._search_edit.textChanged.connect(self._search_timer.start)
        toolbar.addWidget(self._search_edit, 1)
        self._status_filter = QComboBox()
        self._status_filter.setMinimumHeight(36)
        self._status_filter.setMinimumWidth(160)
        self._status_filter.currentIndexChanged.connect(self._apply_filter)
        toolbar.addWidget(self._status_filter)
        self._add_btn = QPushButton(I18n._("permits.add"))
        self._add_btn.clicked.connect(self._add_record)
        toolbar.addWidget(self._add_btn)
        self._edit_btn = QPushButton(I18n._("common.edit"))
        self._edit_btn.clicked.connect(self._edit_selected)
        toolbar.addWidget(self._edit_btn)
        self._delete_btn = QPushButton(I18n._("common.delete"))
        self._delete_btn.clicked.connect(self._delete_selected)
        toolbar.addWidget(self._delete_btn)
        self._export_btn = QPushButton("📤 " + I18n._("export.title"))
        self._export_btn.setProperty("flat", True)
        self._export_btn.clicked.connect(self._export_selected)
        toolbar.addWidget(self._export_btn)
        self._refresh_btn = QPushButton(I18n._("common.refresh"))
        self._refresh_btn.setProperty("flat", True)
        self._refresh_btn.clicked.connect(self._load_data)
        toolbar.addWidget(self._refresh_btn)
        layout.addLayout(toolbar)
        self._table = QTableWidget()
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().hide()
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionsClickable(True)
        self._table.horizontalHeader().setSectionsMovable(True)
        self._table.horizontalHeader().sectionClicked.connect(self._on_header_clicked)
        self._table.horizontalHeader().setContextMenuPolicy(Qt.CustomContextMenu)
        self._table.horizontalHeader().customContextMenuRequested.connect(self._on_header_context_menu)
        self._table.horizontalHeader().sectionDoubleClicked.connect(lambda idx: self._table.resizeColumnToContents(idx))
        self._setup_inline_editing()
        self._table.setSortingEnabled(False)
        self._table.setContextMenuPolicy(Qt.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_table_context_menu)
        self._table.verticalHeader().setDefaultSectionSize(36)
        layout.addWidget(wrap_table_with_glow(self._table, self))
        self._setup_column_widths()

        self._info_label = QLabel()
        self._info_label.setStyleSheet("font-size: 12px; padding: 4px 0;")
        layout.addWidget(self._info_label)

    def _load_data(self) -> None:
        self._columns = self.db.get_columns_config(TABLE_NAME)
        self._all_records = self.db.get_json_records(TABLE_NAME, user_id=self._user_id)
        self._search_edit.clear()
        self._populate_filter()
        self._apply_filter()

    def _populate_filter(self) -> None:
        current = self._status_filter.currentText()
        self._status_filter.blockSignals(True)
        self._status_filter.clear()
        self._status_filter.addItem(I18n._("filter.all"))
        st = sorted(set(str(r.get("data_json", {}).get("Статус", "")).strip() for r in self._all_records if r.get("data_json", {}).get("Статус", "").strip()))
        self._status_filter.addItems(st)
        idx = self._status_filter.findText(current)
        if idx >= 0:
            self._status_filter.setCurrentIndex(idx)
        self._status_filter.blockSignals(False)

    def _apply_filter(self) -> None:
        search_text = self._search_edit.text().strip().lower()
        status_text = self._status_filter.currentText().strip()
        self._records = []
        for r in self._all_records:
            dj = r.get("data_json", {})
            if status_text and status_text != I18n._("filter.all") and str(dj.get("Статус", "")).strip() != status_text:
                continue
            if search_text and not any(search_text in str(dj.get(c["name"], "")).lower() for c in self._columns):
                continue
            self._records.append(r)
        self._populate_table()

    def _populate_table(self) -> None:
        visible_cols = [c for c in self._columns if c.get("visible", True)]
        self._table.setColumnCount(len(visible_cols))
        self._table.setHorizontalHeaderLabels([c["name"] for c in visible_cols])
        self._table.setRowCount(len(self._records))
        self._table.blockSignals(True)
        for row, rec in enumerate(self._records):
            dj = rec.get("data_json", {})
            for col_idx, col in enumerate(visible_cols):
                name = col["name"]
                val = str(dj.get(name, ""))
                item = QTableWidgetItem(val)
                item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsEditable)
                if name == "ID":
                    item.setText(str(rec.get("id", "")))
                if name == "Статус":
                    bg = get_status_indicator_bg(val)
                    if bg:
                        item.setBackground(QColor(bg))
                is_end = name in ("Дата окончания", "Срок устранения", "Срок замены", "Срок действия")
                if is_end and val:
                    item.setForeground(QColor("#E74C3C"))
                self._table.setItem(row, col_idx, item)
        self._table.blockSignals(False)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self._restore_column_widths()
        self._info_label.setText(f'{I18n._("common.count")}: {len(self._records)} / {len(self._all_records)}')

    def _on_header_clicked(self, idx: int) -> None:
        visible_cols = [c for c in self._columns if c.get("visible", True)]
        if idx < 0 or idx >= len(visible_cols):
            return
        col_name = visible_cols[idx]["name"]
        if self._sort_col == idx:
            self._sort_order = Qt.DescendingOrder if self._sort_order == Qt.AscendingOrder else Qt.AscendingOrder
        else:
            self._sort_col = idx
            self._sort_order = Qt.AscendingOrder
        self._records.sort(key=lambda r: str(r.get("data_json", {}).get(col_name, "")),
                           reverse=(self._sort_order == Qt.DescendingOrder))
        self._populate_table()

    def _on_header_context_menu(self, pos: Any) -> None:
        visible_cols = [c for c in self._columns if c.get("visible", True)]
        idx = self._table.horizontalHeader().logicalIndexAt(pos)
        if idx < 0 or idx >= len(visible_cols):
            return
        col_name = visible_cols[idx]["name"]
        menu = QMenu()
        hide_action = menu.addAction(I18n._("column.delete").format(name=col_name))
        if menu.exec_(QCursor.pos()) == hide_action:
            for c in self._columns:
                if c["name"] == col_name:
                    c["visible"] = False
                    break
            self._populate_table()

    def _on_table_context_menu(self, pos: Any) -> None:
        row = self._table.rowAt(pos.y())
        if row < 0 or row >= len(self._records):
            return
        rec = self._records[row]
        menu = QMenu()
        edit_action = menu.addAction(I18n._("common.edit"))
        delete_action = menu.addAction(I18n._("common.delete"))
        action = menu.exec_(QCursor.pos())
        if action == edit_action:
            self._edit_record(rec)
        elif action == delete_action:
            self._delete_record(rec)

    def _add_record(self) -> None:
        dlg = PermitEditDialog({}, self._columns, self)
        if dlg.exec_() == QDialog.Accepted:
            try:
                self.db.save_json_record(TABLE_NAME, 0, dlg.get_data(), user_id=self._user_id)
                self._load_data()
                ToastNotification.notify(I18n._("common.success"), "success", 3000)
            except Exception:
                ToastNotification.notify(I18n._("error.generic"), "error", 5000)

    def _edit_record(self, record: Dict[str, Any]) -> None:
        dlg = PermitEditDialog(record.get("data_json", {}), self._columns, self)
        if dlg.exec_() == QDialog.Accepted:
            try:
                self.db.save_json_record(TABLE_NAME, record["id"], dlg.get_data(), user_id=self._user_id)
                self._load_data()
                ToastNotification.notify(I18n._("common.success"), "success", 3000)
            except Exception:
                ToastNotification.notify(I18n._("error.generic"), "error", 5000)

    def _edit_selected(self) -> None:
        row = self._table.currentRow()
        if 0 <= row < len(self._records):
            self._edit_record(self._records[row])

    def _delete_selected(self) -> None:
        rows = sorted(set(idx.row() for idx in self._table.selectedIndexes()), reverse=True)
        if not rows or QMessageBox.question(self, I18n._("common.confirm"), I18n._("permits.delete_confirm"),
                                             QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        for row in rows:
            if 0 <= row < len(self._records):
                rid = self._records[row].get("id", 0)
                if rid:
                    self.db.delete_json_record(TABLE_NAME, rid)
        self._load_data()
        ToastNotification.notify(I18n._("toast.delete_success"), "success", 3000)

    def _delete_record(self, record: Dict[str, Any]) -> None:
        if QMessageBox.question(self, I18n._("common.confirm"), I18n._("permits.delete_confirm"),
                                 QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        rid = record.get("id", 0)
        if rid:
            self.db.delete_json_record(TABLE_NAME, rid)
        self._load_data()
        ToastNotification.notify(I18n._("toast.delete_success"), "success", 3000)

    def _export_selected(self) -> None:
        row = self._table.currentRow()
        if row < 0 or row >= len(self._records):
            ToastNotification.notify(I18n._("common.no_selection"), "warning", 3000)
            return
        dj = self._records[row].get("data_json", {})
        rid = self._records[row]["id"]
        path, _ = QFileDialog.getSaveFileName(self, I18n._("export.title"),
                                               f"permit_{rid}.csv", "CSV (*.csv)")
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow([c["name"] for c in self._columns])
                w.writerow([dj.get(c["name"], "") for c in self._columns])
            ToastNotification.notify(I18n._("export.success").format(path=path), "success", 3000)
        except Exception as e:
            ToastNotification.notify(I18n._("export.error").format(error=str(e)), "error", 5000)
