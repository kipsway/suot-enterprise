import os, json, math
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QFont, QPixmap, QDoubleValidator, QIntValidator
from PyQt5.QtPrintSupport import QPrinter, QPrintDialog
from PyQt5.QtWidgets import (
    QApplication,
    QDialog,
    QWidget,
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QScrollArea,
    QMessageBox,
    QInputDialog,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QAbstractItemView,
    QTextBrowser,
)

from widgets.glass_button import GlassButton
from widgets.glass_checkbox import GlassCheckBox
from widgets.glass_line_edit import GlassLineEdit
from widgets.glass_combo_box import GlassComboBox

from app_core.i18n import I18n
from app_core.config import RUNTIME_PATHS, AppConfig
from app_core.theme_engine import ThemeEngine
from app_core.utils import fade_in_widget, ACCENT_COLORS
from services.database import DatabaseManager
from modules.print_engine import PrintEngine
from widgets.toast import ToastNotification


class FineKinneyCalculator(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(I18n._("risk.title"))
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setMinimumSize(520, 420)
        self.resize(540, 450)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        form = QFormLayout(container)
        form.setSpacing(10)

        prob_items = I18n._("risk.prob_opts").split(";")
        self._prob_cb = GlassComboBox()
        self._prob_cb.setMinimumHeight(32)
        self._prob_cb.addItems(prob_items)
        form.addRow(I18n._("risk.probability") + ":", self._prob_cb)

        exp_items = I18n._("risk.exp_opts").split(";")
        self._exp_cb = GlassComboBox()
        self._exp_cb.setMinimumHeight(32)
        self._exp_cb.addItems(exp_items)
        form.addRow(I18n._("risk.exposure") + ":", self._exp_cb)

        cons_items = I18n._("risk.cons_opts").split(";")
        self._cons_cb = GlassComboBox()
        self._cons_cb.setMinimumHeight(32)
        self._cons_cb.addItems(cons_items)
        form.addRow(I18n._("risk.consequence") + ":", self._cons_cb)

        calc_btn = GlassButton(I18n._("risk.calculate"))
        calc_btn.setProperty("success", True)
        calc_btn.setMinimumHeight(36)
        calc_btn.clicked.connect(self._calculate)
        form.addRow(calc_btn)

        self._res_label = QLabel(f"<b>{I18n._('risk.index')}:</b> -")
        self._res_label.setStyleSheet("font-size: 16px;")
        form.addRow(self._res_label)

        self._desc_label = QLabel(f"<b>{I18n._('risk.classification')}:</b> -")
        self._desc_label.setWordWrap(True)
        form.addRow(self._desc_label)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = GlassButton(I18n._("common.close"))
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        form.addRow(btn_row)

        scroll.setWidget(container)
        layout.addWidget(scroll)

    def _calculate(self) -> None:
        p = float(self._prob_cb.currentText().split(" —")[0].split("-")[0].strip())
        e = float(self._exp_cb.currentText().split(" —")[0].split("-")[0].strip())
        c = float(self._cons_cb.currentText().split(" —")[0].split("-")[0].strip())
        r = p * e * c
        self._res_label.setText(f"<b>{I18n._('risk.index')}:</b> {r:.1f}")

        if r < 20:
            text, color = I18n._("risk.low"), "#2ecc71"
        elif r < 70:
            text, color = I18n._("risk.moderate"), "#f1c40f"
        elif r < 200:
            text, color = I18n._("risk.substantial"), "#e67e22"
        elif r < 400:
            text, color = I18n._("risk.high"), "#e74c3c"
        else:
            text, color = I18n._("risk.critical"), "#8b0000"

        self._desc_label.setText(
            f"<b>{I18n._('risk.classification')}:</b> "
            f"<span style='color:{color};font-weight:bold;'>{text}</span>"
        )


class TextbookManagerDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.db = DatabaseManager()
        self.setWindowTitle(I18n._("textbook.title"))
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setMinimumSize(700, 500)
        self.resize(750, 550)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)

        heading = QLabel(I18n._("textbook.title"))
        heading.setProperty("heading", True)
        layout.addWidget(heading)

        hint = QLabel(I18n._("textbook.instruction"))
        hint.setWordWrap(True)
        hint.setStyleSheet("font-size: 12px;")
        layout.addWidget(hint)

        self._search_edit = GlassLineEdit()
        self._search_edit.setPlaceholderText(I18n._("common.search_hint"))
        self._search_edit.textChanged.connect(self._filter_rows)
        layout.addWidget(self._search_edit)

        self._table = QTableWidget()
        self._table.setColumnCount(2)
        self._table.setHorizontalHeaderLabels(
            [I18n._("textbook.trigger"), I18n._("textbook.expanded")]
        )
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents
        )
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._table.setAlternatingRowColors(True)
        layout.addWidget(self._table, 1)

        btn_row = QHBoxLayout()
        add_btn = GlassButton(I18n._("common.add"))
        add_btn.clicked.connect(self._add_row)
        del_btn = GlassButton(I18n._("common.delete"))
        del_btn.clicked.connect(self._delete_row)
        save_btn = GlassButton(I18n._("common.save"))
        save_btn.setProperty("success", True)
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(del_btn)
        btn_row.addStretch()
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

        self._load_data()

        self._all_rows: List[Tuple[str, str]] = []

    def _filter_rows(self) -> None:
        query = self._search_edit.text().strip().lower()
        filtered = self._all_rows
        if query:
            filtered = [
                (s, t) for s, t in filtered if query in s.lower() or query in t.lower()
            ]
        self._table.setRowCount(len(filtered))
        for i, (short_code, full_text) in enumerate(filtered):
            self._table.setItem(i, 0, QTableWidgetItem(short_code))
            self._table.setItem(i, 1, QTableWidgetItem(full_text))
        self._table.resizeColumnsToContents()

    def _load_data(self) -> None:
        self._all_rows = self.db.fetch_all(
            "SELECT short_code, full_text FROM textbook ORDER BY short_code"
        )
        self._filter_rows()

    def _add_row(self) -> None:
        r = self._table.rowCount()
        self._table.insertRow(r)
        self._table.setItem(r, 0, QTableWidgetItem(I18n._("textbook.new_trigger")))
        self._table.setItem(r, 1, QTableWidgetItem(I18n._("textbook.new_fulltext")))

    def _delete_row(self) -> None:
        r = self._table.currentRow()
        if r >= 0:
            self._table.removeRow(r)

    def _save(self) -> None:
        self.db.execute("DELETE FROM textbook")
        for i in range(self._table.rowCount()):
            short_item = self._table.item(i, 0)
            long_item = self._table.item(i, 1)
            if short_item and long_item and short_item.text().strip():
                self.db.execute(
                    "INSERT INTO textbook (short_code, full_text) VALUES (?, ?)",
                    (short_item.text().strip().lower(), long_item.text().strip()),
                )
        ToastNotification.notify(I18n._("textbook.saved"), "success", 3000)
        self.accept()


class PrintDialog(QDialog):
    TABLES = {
        "employees": "tab.employees",
        "violations": "tab.violations",
        "custom_ledger": "tab.custom_ledger",
        "companies": "tab.companies",
    }

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.db = DatabaseManager()
        self.setWindowTitle(I18n._("common.print"))
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setMinimumSize(500, 300)
        self.resize(550, 350)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        heading = QLabel(I18n._("common.print"))
        heading.setProperty("heading", True)
        layout.addWidget(heading)

        form = QFormLayout()
        self._table_combo = GlassComboBox()
        self._table_combo.setMinimumHeight(32)
        for tbl, label_key in self.TABLES.items():
            self._table_combo.addItem(I18n._(label_key), tbl)
        form.addRow(I18n._("common.table") + ":", self._table_combo)

        self._template_combo = GlassComboBox()
        self._template_combo.setMinimumHeight(32)
        self._template_combo.addItem("— " + I18n._("print.without_template") + " —", 0)
        for t in self.db.get_all_print_templates():
            suffix = " 📄" if t["template_type"] == "order" else " 📊"
            self._template_combo.addItem(t["name"] + suffix, t["id"])
        form.addRow(I18n._("print.template") + ":", self._template_combo)

        self._all_cb = GlassCheckBox(I18n._("common.select_all"))
        self._all_cb.setChecked(True)
        form.addRow(self._all_cb)
        layout.addLayout(form)

        btn_row = QHBoxLayout()
        print_btn = GlassButton(I18n._("common.print"))
        print_btn.setMinimumHeight(36)
        print_btn.clicked.connect(self._do_print)
        btn_row.addWidget(print_btn)
        btn_row.addStretch()
        close_btn = GlassButton(I18n._("common.close"))
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _do_print(self) -> None:
        table = self._table_combo.currentData()
        label = self._table_combo.currentText()
        cols = self.db.get_columns_config(table)
        records = self.db.get_json_records(table)
        template_id = self._template_combo.currentData()

        rows_html = ""
        for rec in records:
            dj = rec.get("data_json", {})
            cells = "".join(f"<td>{str(dj.get(c['name'], '—'))}</td>" for c in cols)
            rows_html += f"<tr>{cells}</tr>"

        headers = "".join(f"<th>{c['name']}</th>" for c in cols)

        if template_id:
            templates = self.db.get_all_print_templates()
            tmpl = next((t for t in templates if t["id"] == template_id), None)
            if tmpl:
                html = PrintEngine.render_report(
                    label, template_html=tmpl["html_content"]
                )
            else:
                html = f"""<html><head><meta charset='utf-8'><style>body{{font-family:Arial,sans-serif;margin:30px;}}table{{width:100%;border-collapse:collapse;margin-top:16px;}}th,td{{border:1px solid #999;padding:8px;text-align:left;font-size:12px;}}</style></head><body><h2>{label}</h2><p>{I18n._("common.count")}: {len(records)}</p><table><thead><tr>{headers}</tr></thead><tbody>{rows_html}</tbody></table></body></html>"""
        else:
            html = f"""<html><head><meta charset='utf-8'>
            <style>
            body{{font-family:Arial,sans-serif;margin:30px;}}
            h2{{color:#1a365d;}}
            table{{width:100%;border-collapse:collapse;margin-top:16px;}}
            th,td{{border:1px solid #999;padding:8px;text-align:left;font-size:12px;}}
            th{{background:#313244;color:#cdd6f4;}}
            tr:nth-child(even){{background:#f5f5f7;}}
            </style></head><body>
            <h2>{label}</h2>
            <p>{I18n._("common.date")}: {datetime.now().strftime("%d.%m.%Y %H:%M")}</p>
            <p>{I18n._("common.count")}: {len(records)}</p>
            <table><thead><tr>{headers}</tr></thead>
            <tbody>{rows_html if rows_html else '<tr><td colspan="' + str(len(cols)) + '">' + I18n._("report.no_data") + "</td></tr>"}</tbody></table>
            </body></html>"""

        try:
            printer = QPrinter(QPrinter.HighResolution)
            dialog = QPrintDialog(printer, self)
            dialog.setWindowTitle(I18n._("common.print"))
            if dialog.exec_() != QDialog.Accepted:
                return
            browser = QTextBrowser()
            browser.setHtml(html)
            browser.print_(printer)
            ToastNotification.notify(I18n._("print.generated"), "success", 3000)
            self.accept()
        except Exception as ex:
            QMessageBox.critical(self, I18n._("common.error"), str(ex))
