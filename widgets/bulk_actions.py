from typing import Callable, List, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QTableWidget,
    QMessageBox,
    QInputDialog,
)

from app_core.i18n import I18n
from services.database import DatabaseManager
from widgets.toast import ToastNotification


def get_selected_ids(table: QTableWidget) -> List[int]:
    rows = set()
    for item in table.selectedItems():
        rows.add(item.row())
    ids = []
    for row in rows:
        item = table.item(row, 0)
        if item:
            rid = item.data(Qt.UserRole)
            if rid is not None:
                ids.append(int(rid))
    return ids


def count_selected(table: QTableWidget) -> int:
    rows = set()
    for item in table.selectedItems():
        rows.add(item.row())
    return len(rows)


def build_bulk_toolbar(
    table: QTableWidget,
    table_name: str,
    on_refresh: Optional[Callable] = None,
) -> QHBoxLayout:
    layout = QHBoxLayout()
    layout.setSpacing(6)

    db = DatabaseManager()

    delete_btn = QPushButton(I18n._("bulk.delete_selected"))
    delete_btn.setProperty("danger", True)
    delete_btn.clicked.connect(lambda: _bulk_delete(table, table_name, db, on_refresh))
    layout.addWidget(delete_btn)

    status_btn = QPushButton(I18n._("bulk.change_status"))
    status_btn.clicked.connect(
        lambda: _bulk_change_status(table, table_name, db, on_refresh)
    )
    layout.addWidget(status_btn)

    export_btn = QPushButton(I18n._("bulk.export_selected"))
    export_btn.setProperty("flat", True)
    export_btn.clicked.connect(lambda: _bulk_export(table, table_name))
    layout.addWidget(export_btn)

    layout.addStretch()
    return layout


def _bulk_delete(
    table: QTableWidget,
    table_name: str,
    db: DatabaseManager,
    on_refresh: Optional[Callable] = None,
) -> None:
    ids = _get_ids(table)
    if not ids:
        return
    reply = QMessageBox.question(
        table,
        I18n._("common.confirm"),
        I18n._("bulk.confirm_delete").format(count=len(ids)),
        QMessageBox.Yes | QMessageBox.No,
    )
    if reply != QMessageBox.Yes:
        return
    deleted = 0
    for rid in ids:
        try:
            if db.delete_json_record(table_name, rid):
                deleted += 1
        except Exception:
            pass
    ToastNotification.notify(
        I18n._("bulk.deleted").format(count=deleted), "success", 3000
    )
    if on_refresh:
        on_refresh()


def _bulk_change_status(
    table: QTableWidget,
    table_name: str,
    db: DatabaseManager,
    on_refresh: Optional[Callable] = None,
) -> None:
    ids = _get_ids(table)
    if not ids:
        return
    statuses = ["Активно", "Исполнено", "Просрочено", "Архив"]
    status, ok = QInputDialog.getItem(
        table,
        I18n._("bulk.change_status"),
        I18n._("bulk.select_status"),
        statuses,
        0,
        False,
    )
    if not ok or not status:
        return
    updated = 0
    for rid in ids:
        try:
            record = db.get_json_record(table_name, rid)
            if record:
                dj = dict(record.get("data_json", {}))
                dj["Статус"] = status
                db.save_json_record(table_name, rid, dj)
                updated += 1
        except Exception:
            pass
    ToastNotification.notify(
        I18n._("bulk.status_updated").format(count=updated), "success", 3000
    )
    if on_refresh:
        on_refresh()


def _bulk_export(table: QTableWidget, table_name: str) -> None:
    ids = _get_ids(table)
    if not ids:
        return
    db = DatabaseManager()
    records = []
    for rid in ids:
        record = db.get_json_record(table_name, rid)
        if record:
            records.append(record)
    if not records:
        return

    from datetime import datetime
    import csv
    from PyQt5.QtWidgets import QFileDialog

    path, _ = QFileDialog.getSaveFileName(
        table,
        I18n._("export.title"),
        f"{table_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        "CSV (*.csv)",
    )
    if not path:
        return

    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        flat = []
        for r in records:
            dj = r.get("data_json", r)
            flat.append({k: v for k, v in dj.items() if not k.startswith("_")})
        if flat:
            w = csv.DictWriter(f, fieldnames=list(flat[0].keys()))
            w.writeheader()
            w.writerows(flat)
    ToastNotification.notify(
        I18n._("export.success").format(path=path), "success", 3000
    )


def _get_ids(table: QTableWidget) -> List[int]:
    ids = get_selected_ids(table)
    if not ids:
        ToastNotification.notify(I18n._("bulk.no_selection"), "warning", 2000)
    return ids
