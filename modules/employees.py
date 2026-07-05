import csv, re, traceback
from datetime import datetime
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import Qt, QPoint, QTimer
from PyQt5.QtGui import QColor, QCursor
from PyQt5.QtWidgets import (QApplication, QDialog, QWidget, QFrame,
                             QVBoxLayout, QHBoxLayout, QFormLayout,
                             QLabel, QLineEdit, QPushButton, QComboBox,
                             QSpinBox, QScrollArea, QTableWidget,
                             QTableWidgetItem, QHeaderView, QAbstractItemView,
                             QDialogButtonBox, QMenu, QInputDialog, QMessageBox,
                             QFileDialog)

from app_core.i18n import I18n
from app_core.theme_engine import ThemeEngine
from app_core.utils import (wrap_table_with_glow, get_date_indicator_bg,
                            get_status_indicator_bg, get_valid_until_bg)
from services.database import DatabaseManager
from widgets.toast import ToastNotification
from widgets.photos import PhotoGalleryDialog
from modules.textbook import TextbookLineEdit, DateAwareLineEdit

from modules.print_engine import PrintEngine
from modules.notes import NotesDialog


class EmployeeEditDialog(QDialog):
    def __init__(self, data: Dict[str, Any] = None,
                 columns: List[Dict[str, Any]] = None,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._data = dict(data or {})
        self._columns = columns or []
        self._fields: Dict[str, QWidget] = {}
        self._photo_paths: List[str] = self._data.get("Фото", [])
        self.setWindowTitle(I18n._("emp.edit") if data else I18n._("emp.add"))
        self.setMinimumSize(760, 620)
        self.resize(900, 720)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        heading_text = I18n._("emp.edit") if self._data.get("id") else I18n._("emp.add")
        heading = QLabel(heading_text)
        heading.setProperty("heading", True)
        layout.addWidget(heading)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        container = QWidget()
        form = QFormLayout(container)
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignRight)

        for col in self._columns:
            name = col["name"]
            typ = col["type"]
            if name == "ID":
                continue
            if typ == "Медиа":
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
                w = DateAwareLineEdit(placeholder="ДД.ММ.ГГГГ")
                w.setMinimumHeight(36)
                w.setText(str(value))
            elif typ == "Статус":
                w = QComboBox()
                w.setMinimumHeight(36)
                statuses = ["Активен", "Архив", "В отпуске", "Уволен"]
                w.addItems(statuses)
                idx = w.findText(str(value))
                if idx >= 0:
                    w.setCurrentIndex(idx)
            else:
                w = TextbookLineEdit(placeholder="")
                w.setText(str(value))
                w.setMinimumHeight(36)
            self._fields[name] = w
            form.addRow(f"{name}:", w)

        photo_row = QHBoxLayout()
        self._photo_btn = QPushButton("📷 " + I18n._("emp.photo"))
        self._photo_btn.clicked.connect(self._select_photos)
        self._photo_btn.setMinimumHeight(36)
        photo_row.addWidget(self._photo_btn)
        self._photo_label = QLabel()
        self._update_photo_label()
        photo_row.addWidget(self._photo_label, 1)
        form.addRow("", photo_row)

        scroll.setWidget(container)
        layout.addWidget(scroll, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _select_photos(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self, I18n._("emp.photo"), "",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif);;All files (*.*)")
        if files:
            self._photo_paths.extend(files)
            self._update_photo_label()

    def _update_photo_label(self) -> None:
        cnt = len(self._photo_paths)
        self._photo_label.setText(f"{cnt} {I18n._('emp.photo').lower()}(s)" if cnt else "")

    def get_data(self) -> Dict[str, Any]:
        result = dict(self._data)
        result["Фото"] = self._photo_paths
        for col in self._columns:
            name = col["name"]
            if name == "ID":
                continue
            if col["type"] == "Медиа":
                continue
            w = self._fields.get(name)
            if w is None:
                continue
            if isinstance(w, QSpinBox):
                result[name] = str(w.value())
            elif isinstance(w, QComboBox):
                result[name] = w.currentText()
            else:
                result[name] = w.text().strip()
        return result


class EmployeeTableWidget(QWidget):
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

        self._company_filter = QComboBox()
        self._company_filter.setMinimumHeight(36)
        self._company_filter.setMinimumWidth(180)
        self._company_filter.currentIndexChanged.connect(self._apply_filter)
        toolbar.addWidget(self._company_filter)

        self._add_btn = QPushButton(I18n._("emp.add"))
        self._add_btn.clicked.connect(self._add_record)
        toolbar.addWidget(self._add_btn)

        self._edit_btn = QPushButton(I18n._("common.edit"))
        self._edit_btn.clicked.connect(self._edit_selected)
        toolbar.addWidget(self._edit_btn)

        self._delete_btn = QPushButton(I18n._("common.delete"))
        self._delete_btn.clicked.connect(self._delete_selected)
        toolbar.addWidget(self._delete_btn)

        self._photos_btn = QPushButton("📷 " + I18n._("emp.photo"))
        self._photos_btn.setProperty("flat", True)
        self._photos_btn.clicked.connect(self._open_photos)
        toolbar.addWidget(self._photos_btn)

        self._notes_btn = QPushButton("📝 " + I18n._("common.notes"))
        self._notes_btn.setProperty("flat", True)
        self._notes_btn.clicked.connect(self._open_notes)
        toolbar.addWidget(self._notes_btn)

        self._export_btn = QPushButton("📤 " + I18n._("export.title"))
        self._export_btn.setProperty("flat", True)
        self._export_btn.clicked.connect(self._export_selected)
        toolbar.addWidget(self._export_btn)

        self._print_btn = QPushButton("🖨 " + I18n._("print.any_table"))
        self._print_btn.setProperty("flat", True)
        self._print_btn.clicked.connect(self._print_selected)
        toolbar.addWidget(self._print_btn)

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
        self._table.horizontalHeader().customContextMenuRequested.connect(
            self._on_header_context_menu)
        self._table.horizontalHeader().sectionDoubleClicked.connect(
            lambda idx: self._table.resizeColumnToContents(idx))
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.itemChanged.connect(self._on_item_changed)
        self._table.itemDoubleClicked.connect(lambda: self._edit_selected())

        self._table.setSortingEnabled(False)
        self._table.setContextMenuPolicy(Qt.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_table_context_menu)
        self._table.verticalHeader().setDefaultSectionSize(36)
        layout.addWidget(wrap_table_with_glow(self._table, self))

        self._info_label = QLabel()
        self._info_label.setStyleSheet("font-size: 12px; padding: 4px 0;")
        layout.addWidget(self._info_label)

    def _load_data(self) -> None:
        self._columns = self.db.get_columns_config("employees")
        records = self.db.get_json_records("employees",
                                           user_id=self._user_id)
        self._all_records = records
        self._search_edit.clear()
        self._populate_filter()
        self._apply_filter()

    def _populate_filter(self) -> None:
        current = self._company_filter.currentText()
        self._company_filter.blockSignals(True)
        self._company_filter.clear()
        self._company_filter.addItem(I18n._("filter.all"))
        companies: List[str] = []
        for r in self._all_records:
            dj = r.get("data_json", {})
            c = str(dj.get("Фирма", "")).strip()
            if c and c not in companies:
                companies.append(c)
        companies.sort()
        self._company_filter.addItems(companies)
        idx = self._company_filter.findText(current)
        if idx >= 0:
            self._company_filter.setCurrentIndex(idx)
        self._company_filter.blockSignals(False)

    def _apply_filter(self) -> None:
        search_text = self._search_edit.text().strip().lower()
        company_text = self._company_filter.currentText().strip()
        is_regex = False
        if search_text.startswith("/") and search_text.endswith("/"):
            regex_pattern = search_text[1:-1]
            is_regex = True
        else:
            regex_pattern = ""

        self._records = []
        for r in self._all_records:
            dj = r.get("data_json", {})
            if company_text and company_text != I18n._("filter.all"):
                emp_company = str(dj.get("Фирма", "")).strip()
                if emp_company != company_text:
                    continue
            if search_text:
                found = False
                if is_regex:
                    try:
                        pat = re.compile(regex_pattern, re.IGNORECASE)
                        for val in dj.values():
                            if isinstance(val, str) and pat.search(val):
                                found = True
                                break
                    except re.error:
                        pass
                else:
                    for val in dj.values():
                        if isinstance(val, str) and search_text in val.lower():
                            found = True
                            break
                if not found:
                    continue
            self._records.append(r)
        self._render_table()

    def _render_table(self) -> None:
        self._table.blockSignals(True)
        self._table.setRowCount(0)
        cols = self._columns
        self._table.setColumnCount(len(cols))
        headers = [c["name"] for c in cols]
        self._table.setHorizontalHeaderLabels(headers)

        now = datetime.now()
        self._table.setRowCount(len(self._records))
        for row_idx, rec in enumerate(self._records):
            dj = rec.get("data_json", {})
            for col_idx, col in enumerate(cols):
                name = col["name"]
                typ = col["type"]
                value = dj.get(name, "")
                item = QTableWidgetItem()

                if typ == "Число":
                    try:
                        num = float(str(value).replace(" ", "").replace(",", "."))
                        if num == int(num):
                            item.setData(Qt.DisplayRole, int(num))
                            item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                        else:
                            item.setData(Qt.DisplayRole, num)
                            item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    except Exception:
                        item.setText(str(value))
                elif typ == "Медиа":
                    photos = value if isinstance(value, list) else []
                    count = len(photos)
                    icon = "🖼" if count > 0 else "□"
                    item.setText(f"{icon} {count}" if count > 0 else icon)
                    item.setTextAlignment(Qt.AlignCenter)
                elif typ == "Статус":
                    item.setText(str(value))
                    item.setTextAlignment(Qt.AlignCenter)
                elif typ in ("Дата", "Годен до", "Дата проведения", "Date", "Date of", "Valid until"):
                    item.setText(str(value))
                    item.setTextAlignment(Qt.AlignCenter)
                elif name == "ID":
                    item.setText(str(rec.get("id", "")))
                    item.setTextAlignment(Qt.AlignCenter)
                else:
                    item.setText(str(value))

                item.setData(Qt.UserRole, rec.get("id", 0))
                item.setData(Qt.UserRole + 1, name)

                bg = self._get_cell_color(typ, str(value), dj, name)
                if bg:
                    item.setBackground(bg)

                self._table.setItem(row_idx, col_idx, item)

        self._table.resizeColumnsToContents()
        self._table.blockSignals(False)
        self._update_info()

    def _get_cell_color(self, typ: str, value: str,
                        data: Dict[str, Any],
                        field_name: str) -> Optional[QColor]:
        is_dark = ThemeEngine._current_theme == "dark"
        now = datetime.now()

        if typ in ("Дата проведения", "Date of") and value:
            date_mode = str(data.get(f"{field_name}_mode", "Дата проведения"))
            return get_date_indicator_bg(value, is_dark, date_mode)

        if typ == "Статус":
            return get_status_indicator_bg(value, is_dark)

        if typ in ("Годен до", "Valid until") and value:
            return get_valid_until_bg(value, is_dark)

        if typ in ("Дата", "Date") and value:
            date_mode = str(data.get(f"{field_name}_mode", "Действует до"))
            return get_date_indicator_bg(value, is_dark, date_mode)

        return None

    def _update_info(self) -> None:
        total = len(self._all_records)
        shown = len(self._records)
        text = f"{I18n._('common.filter')}: {shown} / {total}"
        self._info_label.setText(text)
        try:
            p = self.parent()
            if p and hasattr(p, 'setTabText'):
                tw = p
            else:
                tw = getattr(p, 'parent', lambda: None)() if p else None
            if tw and hasattr(tw, 'setTabText'):
                for i in range(tw.count()):
                    if tw.widget(i) is self:
                        tw.setTabText(i, f"{I18n._('tab.employees')} ({total})")
                        break
        except Exception:
            pass

    def _on_header_clicked(self, col_idx: int) -> None:
        if self._sort_col == col_idx:
            if self._sort_order == Qt.AscendingOrder:
                self._sort_order = Qt.DescendingOrder
            else:
                self._sort_col = -1
                self._sort_order = Qt.AscendingOrder
        else:
            self._sort_col = col_idx
            self._sort_order = Qt.AscendingOrder
        self._sort_data()
        self._render_table()

    def _sort_data(self) -> None:
        if self._sort_col < 0 or self._sort_col >= len(self._columns):
            self._records.sort(key=lambda r: str(r.get("data_json", {}).get("ФИО", "")).lower())
            return
        col = self._columns[self._sort_col]
        name = col["name"]
        typ = col["type"]

        def sort_key(rec: Dict[str, Any]) -> Any:
            dj = rec.get("data_json", {})
            val = dj.get(name, "")
            if typ == "Число":
                try:
                    return float(str(val).replace(" ", "").replace(",", "."))
                except Exception:
                    return 0.0
            if typ in ("Дата", "Годен до", "Дата проведения", "Date", "Valid until"):
                try:
                    p = str(val).split(".")
                    if len(p) == 3:
                        return datetime(int(p[2]), int(p[1]), int(p[0])).isoformat()
                except Exception:
                    pass
                return str(val)
            return str(val).lower()

        reverse = self._sort_order == Qt.DescendingOrder
        self._records.sort(key=sort_key, reverse=reverse)

    def _add_record(self) -> None:
        dlg = EmployeeEditDialog({}, self._columns, self)
        if dlg.exec_() == QDialog.Accepted:
            data = dlg.get_data()
            try:
                duplicate = self.db.find_employee_duplicate(data, user_id=self._user_id)
                if duplicate:
                    merged = dict(duplicate.get("data_json", {}))
                    merged.update({k: v for k, v in data.items() if str(v).strip() != ""})
                    self.db.save_json_record("employees", duplicate["id"], merged,
                                             user_id=self._user_id)
                    self._load_data()
                    ToastNotification.notify(I18n._("emp.duplicate_updated"), "success", 3000)
                    self.db.merge_duplicates("employees")
                    return
                self.db.save_json_record("employees", 0, data,
                                         user_id=self._user_id)
                self.db.merge_duplicates("employees")
                self._load_data()
                ToastNotification.notify(I18n._("common.success"), "success", 3000)
            except Exception:
                ToastNotification.notify(I18n._("error.generic"), "error", 5000)

    def _edit_record(self, record: Dict[str, Any]) -> None:
        dj = record.get("data_json", {})
        dlg = EmployeeEditDialog(dj, self._columns, self)
        if dlg.exec_() == QDialog.Accepted:
            data = dlg.get_data()
            try:
                duplicate = self.db.find_employee_duplicate(data, exclude_id=record["id"], user_id=self._user_id)
                if duplicate:
                    QMessageBox.warning(self, I18n._("common.warning"), I18n._("emp.duplicate_found"))
                    return
                self.db.save_json_record("employees", record["id"], data,
                                         user_id=self._user_id)
                self.db.merge_duplicates("employees")
                self._load_data()
                ToastNotification.notify(I18n._("common.success"), "success", 3000)
            except Exception:
                ToastNotification.notify(I18n._("error.generic"), "error", 5000)

    def _edit_selected(self) -> None:
        row = self._table.currentRow()
        if row < 0 or row >= len(self._records):
            return
        self._edit_record(self._records[row])

    def _delete_selected(self) -> None:
        rows = set()
        for idx in self._table.selectedIndexes():
            rows.add(idx.row())
        if not rows:
            ToastNotification.notify(I18n._("common.no_selection"), "warning", 3000)
            return
        if len(rows) > 3:
            backup_reply = QMessageBox.question(
                self, I18n._("common.confirm"),
                I18n._("emp.backup_before_delete") if hasattr(I18n, "_") else
                f"Создать резервную копию перед удалением {len(rows)} записей?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
            if backup_reply == QMessageBox.Cancel:
                return
            if backup_reply == QMessageBox.Yes:
                try:
                    self.db.create_backup()
                    ToastNotification.notify(I18n._("toast.backup_created"), "info", 3000)
                except Exception:
                    pass
        reply = QMessageBox.question(
            self, I18n._("common.confirm"),
            I18n._("emp.delete_confirm").format(
                count=len(rows)) if hasattr(I18n, "_") else
            f"{I18n._('common.delete')} {len(rows)} {I18n._('emp.fio')}?",
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        for row in sorted(rows, reverse=True):
            if 0 <= row < len(self._records):
                rid = self._records[row].get("id", 0)
                if rid:
                    self.db.delete_json_record("employees", rid)
        self._load_data()
        ToastNotification.notify(I18n._("toast.delete_success"), "success", 3000)

    def _export_selected(self) -> None:
        row = self._table.currentRow()
        if row < 0 or row >= len(self._records):
            ToastNotification.notify(I18n._("common.no_selection"), "warning", 3000)
            return
        rec = self._records[row]
        dj = rec.get("data_json", {})
        path, _ = QFileDialog.getSaveFileName(self, I18n._("export.title"),
                                               f"record_{rec['id']}.csv",
                                               "CSV (*.csv)")
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow([c["name"] for c in self._columns])
                row_data = [dj.get(c["name"], "") for c in self._columns]
                w.writerow(row_data)
            ToastNotification.notify(I18n._("export.success").format(path=path), "success", 3000)
        except Exception as e:
            ToastNotification.notify(I18n._("export.error").format(error=str(e)), "error", 5000)

    def _print_selected(self) -> None:
        rows = sorted(set(idx.row() for idx in self._table.selectedIndexes()))
        if not rows:
            ToastNotification.notify(I18n._("common.no_selection"), "warning", 3000)
            return
        records = []
        for row in rows:
            if row >= 0 and row < len(self._records):
                records.append(self._records[row])
        if not records:
            return
        html = PrintEngine.render_with_template(self, "order", records, self._columns)
        PrintEngine.print_document(html)

    def _open_photos(self) -> None:
        row = self._table.currentRow()
        if row < 0 or row >= len(self._records):
            return
        rec = self._records[row]
        dj = rec.get("data_json", {})
        photos = dj.get("Фото", [])
        if not isinstance(photos, list):
            photos = []
        dlg = PhotoGalleryDialog(photos, self)
        if dlg.exec_() == QDialog.Accepted:
            new_photos = dlg.get_photos()
            dj["Фото"] = new_photos
            try:
                self.db.save_json_record("employees", rec["id"], dj,
                                         user_id=self._user_id)
                self._load_data()
            except Exception:
                ToastNotification.notify(I18n._("error.generic"), "error", 5000)

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        row = item.row()
        col = item.column()
        if row < 0 or row >= len(self._records) or col < 0 or col >= len(self._columns):
            return
        rec = self._records[row]
        dj = rec.get("data_json", {})
        name = self._columns[col]["name"]
        typ = self._columns[col]["type"]
        if typ == "Медиа":
            return
        if name == "ID":
            return
        new_value = item.text().strip()
        dj[name] = new_value
        try:
            self.db.save_json_record("employees", rec["id"], dj,
                                     user_id=self._user_id)
        except Exception:
            traceback.print_exc()

    def _open_notes(self) -> None:
        row = self._table.currentRow()
        if row < 0 or row >= len(self._records):
            ToastNotification.notify(I18n._("common.no_selection"), "warning", 3000)
            return
        rec = self._records[row]
        dlg = NotesDialog("employees", rec["id"], "", self)
        dlg.exec_()

    def _on_header_context_menu(self, pos: QPoint) -> None:
        col_idx = self._table.horizontalHeader().logicalIndexAt(pos)
        if col_idx < 0:
            return
        col = self._columns[col_idx]
        menu = QMenu(self)
        rename_a = menu.addAction(I18n._("column.rename"))
        add_a = menu.addAction(I18n._("column.add"))
        del_a = menu.addAction(I18n._("column.delete"))
        chg_a = menu.addAction(I18n._("column.change_type"))
        action = menu.exec_(self._table.horizontalHeader().mapToGlobal(pos))
        if action == rename_a:
            self._rename_column(col)
        elif action == add_a:
            self._add_column()
        elif action == del_a:
            self._delete_column(col)
        elif action == chg_a:
            self._change_column_type(col)
        return

    def _rename_column(self, col: Dict[str, Any]) -> None:
        new_name, ok = QInputDialog.getText(
            self, I18n._("column.rename"), I18n._("column.rename_prompt"),
            text=col["name"])
        if ok and new_name:
            if self.db.rename_column("employees", col["name"], new_name):
                self._load_data()
                ToastNotification.notify(I18n._("common.success"), "success", 3000)
            else:
                QMessageBox.warning(self, I18n._("common.warning"),
                                    I18n._("column.duplicate_error"))

    def _add_column(self) -> None:
        name, ok = QInputDialog.getText(
            self, I18n._("column.add"), I18n._("column.add_prompt"))
        if ok and name:
            types = [I18n._("column.type_text"), I18n._("column.type_number"),
                     I18n._("column.type_date"), I18n._("column.type_date_conducted"),
                     I18n._("column.type_status"), I18n._("column.type_media")]
            typ, ok2 = QInputDialog.getItem(
                self, I18n._("column.change_type"), "",
                types, 0, False)
            if ok2 and typ:
                type_map = {
                    I18n._("column.type_text"): "Текст",
                    I18n._("column.type_number"): "Число",
                    I18n._("column.type_date"): "Годен до",
                    I18n._("column.type_date_conducted"): "Дата проведения",
                    I18n._("column.type_status"): "Статус",
                    I18n._("column.type_media"): "Медиа",
                }
                mapped_type = type_map.get(typ, "Текст")
                if self.db.add_column("employees", name, mapped_type):
                    self._load_data()
                    ToastNotification.notify(I18n._("common.success"), "success", 3000)

    def _delete_column(self, col: Dict[str, Any]) -> None:
        reply = QMessageBox.question(
            self, I18n._("common.confirm"),
            f"{I18n._('column.delete')}: '{col['name']}'?",
            QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            if self.db.delete_column("employees", col["name"]):
                self._load_data()
                ToastNotification.notify(I18n._("toast.delete_success"), "success", 3000)

    def _change_column_type(self, col: Dict[str, Any]) -> None:
        types = [I18n._("column.type_text"), I18n._("column.type_number"),
                 I18n._("column.type_date"), I18n._("column.type_date_conducted"),
                 I18n._("column.type_status"), I18n._("column.type_media")]
        typ, ok = QInputDialog.getItem(
            self, I18n._("column.change_type"), "",
            types, 0, False)
        if ok and typ:
            type_map = {
                I18n._("column.type_text"): "Текст",
                I18n._("column.type_number"): "Число",
                I18n._("column.type_date"): "Годен до",
                I18n._("column.type_date_conducted"): "Дата проведения",
                I18n._("column.type_status"): "Статус",
                I18n._("column.type_media"): "Медиа",
            }
            mapped_type = type_map.get(typ, "Текст")
            try:
                self.db.create_backup()
                self.db.conn.execute(
                    "UPDATE columns_config SET type=? WHERE category=? AND name=?",
                    (mapped_type, "employees", col["name"]))
                self.db.conn.commit()
                self._load_data()
                ToastNotification.notify(I18n._("common.success"), "success", 3000)
            except Exception:
                ToastNotification.notify(I18n._("error.generic"), "error", 5000)

    def _on_table_context_menu(self, pos: QPoint) -> None:
        row = self._table.rowAt(pos.y())
        if row < 0:
            return
        self._table.selectRow(row)
        menu = QMenu(self)
        edit_a = menu.addAction(I18n._("common.edit"))
        del_a = menu.addAction(I18n._("common.delete"))
        photo_a = menu.addAction("📷 " + I18n._("emp.photo"))
        print_a = menu.addAction("🖨 " + I18n._("print.any_table"))
        menu.addSeparator()
        copy_a = menu.addAction(I18n._("common.copy"))
        action = menu.exec_(self._table.mapToGlobal(pos))
        if action == edit_a:
            self._edit_selected()
        elif action == del_a:
            self._delete_selected()
        elif action == photo_a:
            self._open_photos()
        elif action == print_a:
            self._print_selected()
        elif action == copy_a:
            item = self._table.item(row, self._table.currentColumn())
            if item and item.text():
                QApplication.clipboard().setText(item.text())

    def refresh(self) -> None:
        self._load_data()

    def focus_record(self, record_id: Any) -> bool:
        self._load_data()
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if item and item.text().strip() == str(record_id):
                self._table.selectRow(row)
                self._table.scrollToItem(item, QAbstractItemView.PositionAtCenter)
                return True
        return False
