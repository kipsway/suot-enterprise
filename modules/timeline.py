import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import Qt, QSize, QTimer
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import (
    QWidget,
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
)

from widgets.glass_button import GlassButton
from widgets.glass_line_edit import GlassLineEdit
from widgets.glass_combo_box import GlassComboBox

from app_core.i18n import I18n
from app_core.theme_engine import ThemeEngine
from services.database import DatabaseManager


EVENT_ICONS = {
    "login": "🔑",
    "logout": "🚪",
    "User logged in": "🔑",
    "Failed login": "❌",
    "TOTP": "🔐",
    "created": "➕",
    "updated": "✏️",
    "deleted": "🗑",
    "Import": "📥",
    "Export": "📤",
    "Backup": "💾",
    "Restore": "♻",
    "Import:": "📥",
    "Seed": "🌱",
}


def _get_event_icon(event: str) -> str:
    for key, icon in EVENT_ICONS.items():
        if key in event:
            return icon
    return "📌"


def _get_event_color(severity: str) -> str:
    return {"INFO": "#27AE60", "WARNING": "#F39C12", "CRITICAL": "#E74C3C"}.get(
        severity, "#888"
    )


class TimelineItemWidget(QFrame):
    def __init__(
        self,
        event: str,
        severity: str,
        details: str,
        timestamp: str,
        username: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setProperty("card", True)
        self.setStyleSheet("margin: 2px 0;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)

        icon = _get_event_icon(event)
        icon_lbl = QLabel(icon)
        icon_lbl.setFixedWidth(30)
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet("font-size: 20px;")
        layout.addWidget(icon_lbl)

        dot = QLabel("●")
        dot_color = _get_event_color(severity)
        dot.setStyleSheet(f"color: {dot_color}; font-size: 14px;")
        dot.setFixedWidth(14)
        layout.addWidget(dot)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        event_lbl = QLabel(event[:80])
        event_lbl.setStyleSheet("font-weight: 600; font-size: 13px;")
        event_lbl.setWordWrap(True)
        text_layout.addWidget(event_lbl)
        if details:
            det_lbl = QLabel(details[:120])
            det_lbl.setStyleSheet("font-size: 11px; color: #888;")
            det_lbl.setWordWrap(True)
            text_layout.addWidget(det_lbl)
        layout.addLayout(text_layout, 1)

        meta_layout = QVBoxLayout()
        meta_layout.setSpacing(0)
        meta_layout.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        ts_lbl = QLabel(timestamp[-8:] if len(timestamp) >= 16 else timestamp)
        ts_lbl.setStyleSheet("font-size: 11px; color: #999; font-family: monospace;")
        meta_layout.addWidget(ts_lbl)
        if username:
            u_lbl = QLabel(username[:20])
            u_lbl.setStyleSheet("font-size: 10px; color: #aaa;")
            meta_layout.addWidget(u_lbl)
        layout.addLayout(meta_layout)


class TimelineTab(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.db = DatabaseManager()
        self._build_ui()
        self._load_events()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self._search_edit = GlassLineEdit()
        self._search_edit.setProperty("search", True)
        self._search_edit.setPlaceholderText(I18n._("search.placeholder"))
        self._search_edit.setMinimumHeight(32)
        self._search_edit.textChanged.connect(self._load_events)
        toolbar.addWidget(self._search_edit, 1)

        self._severity_filter = GlassComboBox()
        self._severity_filter.setMinimumHeight(32)
        self._severity_filter.addItem(I18n._("filter.all"), "")
        self._severity_filter.addItem(I18n._("audit.info"), "INFO")
        self._severity_filter.addItem(I18n._("audit.warning"), "WARNING")
        self._severity_filter.addItem(I18n._("audit.critical"), "CRITICAL")
        self._severity_filter.currentIndexChanged.connect(self._load_events)
        toolbar.addWidget(self._severity_filter)

        self._limit_combo = GlassComboBox()
        self._limit_combo.setMinimumHeight(32)
        for val in (50, 100, 200, 500):
            self._limit_combo.addItem(str(val), val)
        self._limit_combo.setCurrentIndex(1)
        self._limit_combo.currentIndexChanged.connect(self._load_events)
        toolbar.addWidget(QLabel(I18n._("common.count") + ":"))
        toolbar.addWidget(self._limit_combo)

        refresh_btn = GlassButton(I18n._("common.refresh"))
        refresh_btn.setProperty("flat", True)
        refresh_btn.clicked.connect(self._load_events)
        toolbar.addWidget(refresh_btn)

        layout.addLayout(toolbar)

        self._list = QListWidget()
        self._list.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self._list.setSpacing(4)
        self._list.setFrameShape(QFrame.NoFrame)
        layout.addWidget(self._list)

        self._info_label = QLabel()
        self._info_label.setStyleSheet("font-size: 12px; padding: 2px 0;")
        layout.addWidget(self._info_label)

    def _load_events(self) -> None:
        self._list.clear()
        severity = self._severity_filter.currentData()
        limit = self._limit_combo.currentData() or 100
        search = self._search_edit.text().strip().lower()
        try:
            if severity:
                rows = self.db.fetch_all(
                    "SELECT * FROM audit_log WHERE severity=? ORDER BY id DESC LIMIT ?",
                    (severity, limit),
                )
            else:
                rows = self.db.fetch_all(
                    "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)
                )
        except Exception:
            rows = []

        filtered = 0
        for r in rows:
            event = str(r.get("event", ""))
            details_raw = r.get("details", "{}")
            try:
                dd = (
                    json.loads(details_raw)
                    if isinstance(details_raw, str) and details_raw
                    else {}
                )
            except Exception:
                dd = {}
            detail_str = "; ".join(f"{k}={v}" for k, v in dd.items()) if dd else ""
            if (
                search
                and search not in event.lower()
                and search not in detail_str.lower()
            ):
                continue
            filtered += 1
            item = QListWidgetItem()
            widget = TimelineItemWidget(
                event=str(r.get("event", "")),
                severity=str(r.get("severity", "INFO")),
                details=detail_str,
                timestamp=str(r.get("timestamp", "")),
                username=str(r.get("username", "")),
            )
            item.setSizeHint(widget.sizeHint())
            self._list.addItem(item)
            self._list.setItemWidget(item, widget)

        total = len(rows)
        self._info_label.setText(f"{I18n._('common.count')}: {filtered} / {total}")
