import os
from typing import Optional, Any

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QPushButton,
    QGridLayout,
)

from app_core.i18n import I18n
from app_core.config import RUNTIME_PATHS
from services.database import DatabaseManager


class SystemMonitorWidget(QFrame):
    def __init__(self, parent: Optional[QFrame] = None) -> None:
        super().__init__(parent)
        self.setProperty("card", True)
        self.db = DatabaseManager()
        self._labels: dict = {}
        self._build_ui()
        self._refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        heading = QLabel(I18n._("monitor.title"))
        heading.setProperty("heading", True)
        layout.addWidget(heading)

        # Database section
        db_group = QFrame()
        db_group.setProperty("card", True)
        db_group.setStyleSheet(
            "QFrame[card=true] { background: transparent; border: 1px solid #ddd; }"
        )
        dbl = QVBoxLayout(db_group)
        dbl.setContentsMargins(12, 10, 12, 10)
        dbl.setSpacing(6)
        db_heading = QLabel(I18n._("monitor.database"))
        db_heading.setStyleSheet("font-weight: 600; font-size: 14px;")
        dbl.addWidget(db_heading)
        db_form = QFormLayout()
        db_form.setSpacing(4)
        for key in (
            "db_path",
            "db_size",
            "cache_entries",
            "audit_entries",
            "users",
            "active_reminders",
            "active_webhooks",
        ):
            lbl = QLabel("—")
            lbl.setStyleSheet("font-size: 12px; font-family: monospace;")
            db_form.addRow(I18n._(f"monitor.{key}") + ":", lbl)
            self._labels[key] = lbl
        dbl.addLayout(db_form)
        layout.addWidget(db_group)

        # Tables section
        tables_group = QFrame()
        tables_group.setProperty("card", True)
        tables_group.setStyleSheet(
            "QFrame[card=true] { background: transparent; border: 1px solid #ddd; }"
        )
        tl = QVBoxLayout(tables_group)
        tl.setContentsMargins(12, 10, 12, 10)
        tl.setSpacing(6)
        tbl_heading = QLabel(I18n._("monitor.tables"))
        tbl_heading.setStyleSheet("font-weight: 600; font-size: 14px;")
        tl.addWidget(tbl_heading)
        self._tables_grid = QGridLayout()
        self._tables_grid.setSpacing(4)
        self._table_labels: dict = {}
        tl.addLayout(self._tables_grid)
        layout.addWidget(tables_group)

        # Storage section
        storage_group = QFrame()
        storage_group.setProperty("card", True)
        storage_group.setStyleSheet(
            "QFrame[card=true] { background: transparent; border: 1px solid #ddd; }"
        )
        sl = QVBoxLayout(storage_group)
        sl.setContentsMargins(12, 10, 12, 10)
        sl.setSpacing(6)
        st_heading = QLabel(I18n._("monitor.storage"))
        st_heading.setStyleSheet("font-weight: 600; font-size: 14px;")
        sl.addWidget(st_heading)
        st_form = QFormLayout()
        st_form.setSpacing(4)
        for key in ("media_size",):
            lbl = QLabel("—")
            lbl.setStyleSheet("font-size: 12px; font-family: monospace;")
            st_form.addRow(I18n._(f"monitor.{key}") + ":", lbl)
            self._labels[key] = lbl
        sl.addLayout(st_form)
        layout.addWidget(storage_group)

        refresh_btn = QPushButton(I18n._("common.refresh"))
        refresh_btn.clicked.connect(self._refresh)
        layout.addWidget(refresh_btn, 0, Qt.AlignLeft)

    def _refresh(self) -> None:
        health = self.db.get_health()
        db_path = self.db.database_path
        self._labels["db_path"].setText(db_path)
        size = health.get("db_size_bytes", 0)
        self._labels["db_size"].setText(self._fmt_size(size))
        self._labels["cache_entries"].setText(str(health.get("cache_entries", 0)))
        self._labels["audit_entries"].setText(str(health.get("audit_entries", 0)))
        self._labels["users"].setText(str(health.get("users", 0)))
        self._labels["active_reminders"].setText(str(health.get("active_reminders", 0)))
        self._labels["active_webhooks"].setText(str(health.get("active_webhooks", 0)))
        self._labels["media_size"].setText(
            self._fmt_size(health.get("media_size_bytes", 0))
        )

        tables = health.get("tables", {})
        self._clear_grid(self._tables_grid)
        self._table_labels = {}
        for i, (tbl, cnt) in enumerate(sorted(tables.items())):
            name_lbl = QLabel(tbl)
            name_lbl.setStyleSheet("font-size: 12px; font-family: monospace;")
            cnt_lbl = QLabel(str(cnt))
            cnt_lbl.setStyleSheet(
                "font-size: 12px; font-family: monospace; font-weight: 600;"
            )
            self._tables_grid.addWidget(name_lbl, i, 0)
            self._tables_grid.addWidget(cnt_lbl, i, 1)

    @staticmethod
    def _clear_grid(grid: Any) -> None:
        for i in reversed(range(grid.count())):
            w = grid.itemAt(i).widget()
            if w:
                w.setParent(None)
                w.deleteLater()

    @staticmethod
    def _fmt_size(b: int) -> str:
        for unit in ("B", "KB", "MB", "GB"):
            if b < 1024:
                return f"{b:.1f} {unit}"
            b /= 1024.0
        return f"{b:.1f} TB"
