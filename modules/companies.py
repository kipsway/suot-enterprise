import csv, sqlite3
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QWidget,
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QAbstractItemView,
    QDialogButtonBox,
    QMessageBox,
    QFileDialog,
)
from widgets.glass_button import GlassButton
from widgets.export_helpers import add_export_buttons
from widgets.glass_line_edit import GlassLineEdit

from app_core.i18n import I18n
from app_core.utils import wrap_table_with_glow
from services.database import DatabaseManager
from widgets.toast import ToastNotification
from modules.print_engine import PrintEngine
from widgets.record_links import RecordLinksDialog


class CompanyEditDialog(QDialog):
    def __init__(
        self, data: Optional[Dict[str, Any]] = None, parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._data = dict(data or {})
        is_new = not bool(self._data.get("id"))
        self.setWindowTitle(I18n._("company.add") if is_new else I18n._("company.edit"))
        self.setMinimumSize(450, 300)
        self.resize(500, 320)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)
        heading = QLabel(
            I18n._("company.edit") if self._data.get("id") else I18n._("company.add")
        )
        heading.setProperty("heading", True)
        layout.addWidget(heading)

        form = QFormLayout()
        form.setSpacing(10)
        self._name_edit = GlassLineEdit(self._data.get("name", ""))
        form.addRow(f"{I18n._('company.name')}:", self._name_edit)
        self._addr_edit = GlassLineEdit(self._data.get("address", ""))
        form.addRow(f"{I18n._('company.address')}:", self._addr_edit)
        self._contact_edit = GlassLineEdit(self._data.get("contact", ""))
        form.addRow(f"{I18n._('company.contact')}:", self._contact_edit)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_data(self) -> Dict[str, str]:
        return {
            "name": self._name_edit.text().strip(),
            "address": self._addr_edit.text().strip(),
            "contact": self._contact_edit.text().strip(),
        }


class CompaniesTab(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.db = DatabaseManager()
        self._build_ui()
        self._load_data()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        heading = QLabel(I18n._("tab.companies"))
        heading.setProperty("heading", True)
        layout.addWidget(heading)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        self._add_btn = GlassButton(I18n._("company.add"))
        self._add_btn.clicked.connect(self._add_company)
        toolbar.addWidget(self._add_btn)
        self._edit_btn = GlassButton(I18n._("common.edit"))
        self._edit_btn.clicked.connect(self._edit_company)
        toolbar.addWidget(self._edit_btn)
        self._delete_btn = GlassButton(I18n._("common.delete"))
        self._delete_btn.clicked.connect(self._delete_company)
        toolbar.addWidget(self._delete_btn)
        self._refresh_btn = GlassButton(I18n._("common.refresh"))
        self._refresh_btn.setProperty("flat", True)
        self._refresh_btn.clicked.connect(self._load_data)
        toolbar.addWidget(self._refresh_btn)

        add_export_buttons(
            toolbar,
            lambda: self._all_companies,
            lambda: [{"name": h} for h in self._headers],
            "companies",
            self,
        )

        self._links_btn = GlassButton(
            "\U0001f517 \u0421\u0432\u044f\u0437\u0430\u0442\u044c"
        )
        self._links_btn.setProperty("flat", True)
        self._links_btn.clicked.connect(self._open_links)
        toolbar.addWidget(self._links_btn)

        self._print_btn = GlassButton("\U0001f5a8 " + I18n._("print.any_table"))
        self._print_btn.setProperty("flat", True)
        self._print_btn.clicked.connect(self._print_selected)
        toolbar.addWidget(self._print_btn)

        self._search_edit = GlassLineEdit()
        self._search_edit.setPlaceholderText(I18n._("common.search_hint"))
        self._search_edit.setMaximumWidth(250)
        self._search_edit.textChanged.connect(self._filter_table)
        toolbar.addWidget(self._search_edit)

        toolbar.addStretch()

        layout.addLayout(toolbar)

        self._table = QTableWidget()
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().hide()
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        headers = [
            I18n._("company.id"),
            I18n._("company.name"),
            I18n._("company.address"),
            I18n._("company.contact"),
            I18n._("company.employees_count"),
            I18n._("company.violations_count"),
            I18n._("company.fines_total"),
        ]
        self._table.setColumnCount(len(headers))
        self._table.setHorizontalHeaderLabels(headers)
        self._table.setSortingEnabled(True)
        self._table.itemDoubleClicked.connect(self._edit_company)
        layout.addWidget(wrap_table_with_glow(self._table, self))

    def _load_data(self) -> None:
        companies = self.db.get_companies()
        self._table.setRowCount(len(companies))
        for i, c in enumerate(companies):
            cid = c["id"]
            self._table.setItem(i, 0, QTableWidgetItem(str(cid)))
            self._table.setItem(i, 1, QTableWidgetItem(c.get("name", "")))
            self._table.setItem(i, 2, QTableWidgetItem(c.get("address", "")))
            self._table.setItem(i, 3, QTableWidgetItem(c.get("contact", "")))

            emp_count = 0
            viol_count = 0
            fines = 0.0
            name = c.get("name", "")
            for emp in self.db.get_json_records("employees"):
                dj = emp.get("data_json", {})
                if dj.get("Фирма") == name:
                    emp_count += 1
            for viol in self.db.get_json_records("violations"):
                dj = viol.get("data_json", {})
                if dj.get("Фирма") == name:
                    viol_count += 1
                    try:
                        fines += float(
                            str(dj.get("Штраф", "0")).replace(" ", "").replace(",", ".")
                        )
                    except Exception:
                        pass

            self._table.setItem(i, 4, QTableWidgetItem(str(emp_count)))
            self._table.setItem(i, 5, QTableWidgetItem(str(viol_count)))
            fine_item = QTableWidgetItem(f"{fines:,.0f} ₽".replace(",", " "))
            fine_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._table.setItem(i, 6, fine_item)
        self._table.resizeColumnsToContents()
        self._all_companies: List[Dict[str, Any]] = companies

    def _filter_table(self) -> None:
        query = self._search_edit.text().strip().lower()
        filtered = (
            self._all_companies
            if not query
            else [
                c
                for c in self._all_companies
                if query in str(c.get("name", "")).lower()
                or query in str(c.get("address", "")).lower()
                or query in str(c.get("contact", "")).lower()
            ]
        )
        self._table.setRowCount(len(filtered))
        for i, c in enumerate(filtered):
            cid = c["id"]
            self._table.setItem(i, 0, QTableWidgetItem(str(cid)))
            self._table.setItem(i, 1, QTableWidgetItem(c.get("name", "")))
            self._table.setItem(i, 2, QTableWidgetItem(c.get("address", "")))
            self._table.setItem(i, 3, QTableWidgetItem(c.get("contact", "")))
            emp_count = 0
            viol_count = 0
            fines = 0.0
            name = c.get("name", "")
            for emp in self.db.get_json_records("employees"):
                dj = emp.get("data_json", {})
                if dj.get("Фирма") == name:
                    emp_count += 1
            for viol in self.db.get_json_records("violations"):
                dj = viol.get("data_json", {})
                if dj.get("Фирма") == name:
                    viol_count += 1
                    try:
                        fines += float(
                            str(dj.get("Штраф", "0")).replace(" ", "").replace(",", ".")
                        )
                    except Exception:
                        pass
            self._table.setItem(i, 4, QTableWidgetItem(str(emp_count)))
            self._table.setItem(i, 5, QTableWidgetItem(str(viol_count)))
            fine_item = QTableWidgetItem(f"{fines:,.0f} ₽".replace(",", " "))
            fine_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._table.setItem(i, 6, fine_item)
        self._table.resizeColumnsToContents()

    def _add_company(self) -> None:
        dlg = CompanyEditDialog(parent=self)
        if dlg.exec_() == QDialog.Accepted:
            data = dlg.get_data()
            if data["name"]:
                try:
                    self.db.save_company(data["name"], data["address"], data["contact"])
                    self._load_data()
                    ToastNotification.notify(I18n._("common.success"), "success", 3000)
                except sqlite3.IntegrityError:
                    QMessageBox.warning(
                        self,
                        I18n._("common.warning"),
                        f"{I18n._('company.name')} '{data['name']}' "
                        f"{I18n._('column.duplicate_error')}",
                    )

    def _edit_company(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            return
        cid = int(self._table.item(row, 0).text())
        comp = self.db.get_company(cid)
        if not comp:
            return
        dlg = CompanyEditDialog(dict(comp), self)
        if dlg.exec_() == QDialog.Accepted:
            data = dlg.get_data()
            if data["name"]:
                try:
                    self.db.save_company(
                        data["name"], data["address"], data["contact"], company_id=cid
                    )
                    self._load_data()
                    ToastNotification.notify(I18n._("common.success"), "success", 3000)
                except sqlite3.IntegrityError:
                    QMessageBox.warning(
                        self, I18n._("common.warning"), I18n._("column.duplicate_error")
                    )

    def _delete_company(self) -> None:
        rows = set()
        for idx in self._table.selectedIndexes():
            rows.add(idx.row())
        if not rows:
            return
        reply = QMessageBox.question(
            self,
            I18n._("common.confirm"),
            f"{I18n._('common.delete')} {len(rows)} {I18n._('company.name').lower()}?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            for row in sorted(rows, reverse=True):
                cid = int(self._table.item(row, 0).text())
                self.db.delete_company(cid)
        self._load_data()
        ToastNotification.notify(I18n._("toast.delete_success"), "success", 3000)

    def _open_links(self) -> None:
        row = self._table.currentRow()
        if row < 0 or row >= len(self._records):
            ToastNotification.notify(I18n._("common.no_selection"), "warning", 3000)
            return
        rec = self._records[row]
        name = rec.get("name", f"#{rec['id']}")
        dlg = RecordLinksDialog("companies", rec["id"], name, self)
        dlg.exec_()

    def _print_selected(self) -> None:
        rows = sorted(set(idx.row() for idx in self._table.selectedIndexes()))
        if not rows:
            ToastNotification.notify(I18n._("common.no_selection"), "warning", 3000)
            return
        parts = []
        for row in rows:
            if row < 0 or row >= self._table.rowCount():
                continue
            name = self._table.item(row, 1).text() if self._table.item(row, 1) else ""
            address = (
                self._table.item(row, 2).text() if self._table.item(row, 2) else ""
            )
            contact = (
                self._table.item(row, 3).text() if self._table.item(row, 3) else ""
            )
            emp_c = self._table.item(row, 4).text() if self._table.item(row, 4) else "0"
            viol_c = (
                self._table.item(row, 5).text() if self._table.item(row, 5) else "0"
            )
            fines = self._table.item(row, 6).text() if self._table.item(row, 6) else "0"
            lines = [
                f"<h1>{I18n._('company.title')}: {name}</h1><table>",
                f"<tr><td><b>{I18n._('company.address')}</b></td><td>{address}</td></tr>",
                f"<tr><td><b>{I18n._('company.contact')}</b></td><td>{contact}</td></tr>",
                f"<tr><td><b>{I18n._('company.employees_count')}</b></td><td>{emp_c}</td></tr>",
                f"<tr><td><b>{I18n._('company.violations_count')}</b></td><td>{viol_c}</td></tr>",
                f"<tr><td><b>{I18n._('company.fines_total')}</b></td><td>{fines}</td></tr>",
                "</table><hr>",
            ]
            parts.append("".join(lines))
        if not parts:
            return
        html = "<html><body>" + "".join(parts) + "</body></html>"
        PrintEngine.print_document(html)

    def _export_selected(self) -> None:
        rows = sorted(set(idx.row() for idx in self._table.selectedIndexes()))
        if not rows:
            ToastNotification.notify(I18n._("common.no_selection"), "warning", 3000)
            return
        path, _ = QFileDialog.getSaveFileName(
            self, I18n._("export.title"), "companies.csv", "CSV (*.csv)"
        )
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                headers = []
                for c in range(self._table.columnCount()):
                    item = self._table.horizontalHeaderItem(c)
                    headers.append(item.text() if item else str(c))
                w.writerow(headers)
                for row in rows:
                    row_data = []
                    for c in range(self._table.columnCount()):
                        item = self._table.item(row, c)
                        row_data.append(item.text() if item else "")
                    w.writerow(row_data)
            ToastNotification.notify(
                I18n._("export.success").format(path=path), "success", 3000
            )
        except Exception as e:
            ToastNotification.notify(
                I18n._("export.error").format(error=str(e)), "error", 5000
            )

    def refresh(self) -> None:
        self._load_data()
