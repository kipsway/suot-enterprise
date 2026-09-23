from typing import Any, Dict, List, Optional, Callable
from PyQt5.QtWidgets import QHBoxLayout, QFileDialog, QWidget
from PyQt5.QtCore import Qt
from widgets.glass_button import GlassButton
from widgets.toast import ToastNotification
from app_core.i18n import I18n
from services.database import DatabaseManager


def _export_docx(
    records: List[Dict[str, Any]],
    columns: List[Dict[str, Any]],
    table_name: str,
    parent: QWidget,
) -> None:
    from services.docx_service import is_available, export_records_to_docx

    if not is_available():
        ToastNotification.notify("python-docx не установлен", "error", 4000)
        return
    path, _ = QFileDialog.getSaveFileName(
        parent, I18n._("export.title"), f"{table_name}_report.docx", "DOCX (*.docx)"
    )
    if not path:
        return
    col_names = [c["name"] for c in columns]
    flat = []
    for r in records:
        dj = r.get("data_json", r)
        flat.append({k: str(v) for k, v in dj.items() if k in col_names})
    ok = export_records_to_docx(flat, col_names, path, f"Report: {table_name}")
    if ok:
        ToastNotification.notify(
            I18n._("export.success").format(path=path), "success", 3000
        )
    else:
        ToastNotification.notify(
            I18n._("export.error").format(error="DOCX"), "error", 5000
        )


def _export_excel(
    records: List[Dict[str, Any]],
    columns: List[Dict[str, Any]],
    table_name: str,
    parent: QWidget,
) -> None:
    from services.excel_service import is_available, export_to_excel

    if not is_available():
        ToastNotification.notify("openpyxl не установлен", "error", 4000)
        return
    path, _ = QFileDialog.getSaveFileName(
        parent, I18n._("export.title"), f"{table_name}_export.xlsx", "Excel (*.xlsx)"
    )
    if not path:
        return
    col_names = [c["name"] for c in columns]
    flat = []
    for r in records:
        dj = r.get("data_json", r)
        flat.append({k: str(v) for k, v in dj.items() if k in col_names})
    ok = export_to_excel(flat, col_names, path, table_name)
    if ok:
        ToastNotification.notify(
            I18n._("export.success").format(path=path), "success", 3000
        )
    else:
        ToastNotification.notify(
            I18n._("export.error").format(error="XLSX"), "error", 5000
        )


def add_export_buttons(
    layout: QHBoxLayout,
    get_records: Callable,
    get_columns: Callable,
    table_name: str,
    parent: QWidget,
) -> None:
    docx_btn = GlassButton("📝 DOCX")
    docx_btn.clicked.connect(
        lambda: _export_docx(get_records(), get_columns(), table_name, parent)
    )
    layout.addWidget(docx_btn)

    xlsx_btn = GlassButton("📊 XLSX")
    xlsx_btn.clicked.connect(
        lambda: _export_excel(get_records(), get_columns(), table_name, parent)
    )
    layout.addWidget(xlsx_btn)
