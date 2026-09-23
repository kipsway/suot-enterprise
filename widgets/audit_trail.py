from typing import Any, Dict, List

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
)

from app_core.i18n import I18n
from services.database import DatabaseManager


class AuditTrailDialog(QDialog):
    def __init__(
        self, table: str, record_id: int, title: str = "", parent=None
    ) -> None:
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.db = DatabaseManager()
        self._table = table
        self._record_id = record_id
        self.setWindowTitle(
            f"{I18n._('audit.title')} #{record_id} — {table}" if not title else title
        )
        self.setMinimumSize(650, 450)
        self.resize(700, 500)
        self._build_ui()
        self._load_events()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        heading = QLabel(f"{I18n._('audit.title')} #{self._record_id}")
        heading.setProperty("heading", True)
        layout.addWidget(heading)

        self._list = QListWidget()
        self._list.setAlternatingRowColors(True)
        self._list.itemClicked.connect(self._on_event_selected)
        layout.addWidget(self._list)

        self._detail_label = QLabel()
        self._detail_label.setWordWrap(True)
        self._detail_label.setStyleSheet(
            "padding: 8px; background: rgba(0,0,0,0.05); border-radius: 4px;"
        )
        self._detail_label.setMinimumHeight(60)
        layout.addWidget(self._detail_label)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        close_btn = QPushButton(I18n._("common.close"))
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

    def _load_events(self) -> None:
        self._list.clear()
        events = self.db.get_audit_events_for_record(self._table, self._record_id)
        for ev in events:
            ts = str(ev.get("timestamp", ""))[:19]
            event = str(ev.get("event", ""))
            severity = str(ev.get("severity", "INFO"))
            username = str(ev.get("username", ""))
            icon = "ℹ️" if severity == "INFO" else "⚠️" if severity == "WARNING" else "🚫"
            text = f"{icon} [{ts}] {event}"
            if username:
                text += f" — {username}"
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, ev.get("details", "{}"))
            item.setData(Qt.UserRole + 1, ev.get("id", 0))
            if severity == "WARNING":
                item.setForeground(Qt.darkYellow)
            elif severity == "CRITICAL":
                item.setForeground(Qt.red)
            self._list.addItem(item)

        count = self._list.count()
        self.setWindowTitle(
            f"{self.windowTitle().split(' — ')[0]} — {count} {I18n._('audit.events')}"
        )

    def _on_event_selected(self, item: QListWidgetItem) -> None:
        raw = item.data(Qt.UserRole)
        try:
            import json

            details = json.loads(raw)
            self._detail_label.setText(
                "\n".join(f"{k}: {v}" for k, v in details.items())
            )
        except Exception:
            self._detail_label.setText(raw)
