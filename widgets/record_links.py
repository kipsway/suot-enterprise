from typing import Any, Dict, List, Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
from widgets.toast import ToastNotification

from app_core.design_tokens import palette
from app_core.i18n import I18n
from app_core.theme_engine import ThemeEngine
from services.database import DatabaseManager
from widgets.glass_button import GlassButton


class RecordLinksDialog(QDialog):
    link_activated = pyqtSignal(str, int)

    def __init__(
        self,
        table: str,
        record_id: int,
        record_name: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._table = table
        self._record_id = record_id
        self._record_name = record_name
        self._db = DatabaseManager()
        self.setWindowTitle(f"🔗 Связи: {record_name or f'#{record_id}'}")
        self.setMinimumSize(480, 360)
        self.resize(520, 420)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        title = QLabel(
            f"🔗 Связи для <b>{self._record_name or f'#{self._record_id}'}</b> "
            f"({self._table})"
        )
        title.setWordWrap(True)
        layout.addWidget(title)

        self._links_list = QVBoxLayout()
        self._links_list.setSpacing(4)
        self._refresh_links()
        layout.addLayout(self._links_list)

        layout.addSpacing(8)

        add_layout = QHBoxLayout()
        add_layout.setSpacing(8)

        self._target_table = QComboBox()
        self._target_table.setMinimumHeight(32)
        self._target_table.addItems(
            [
                "employees",
                "violations",
                "companies",
                "incidents",
                "ppe",
                "training",
                "permits",
                "custom_ledger",
                "notes",
            ]
        )
        add_layout.addWidget(self._target_table)

        self._target_id = QSpinBox()
        self._target_id.setMinimum(1)
        self._target_id.setMaximum(999999)
        self._target_id.setMinimumHeight(32)
        add_layout.addWidget(self._target_id)

        add_btn = GlassButton(I18n._("common.add"))
        add_btn.setFixedHeight(32)
        add_btn.clicked.connect(self._add_link)
        add_layout.addWidget(add_btn)

        layout.addLayout(add_layout)

        close_btn = GlassButton(I18n._("common.close"))
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignRight)

    def _refresh_links(self) -> None:
        while self._links_list.count():
            item = self._links_list.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        links = self._db.get_record_links(self._table, self._record_id)
        if not links:
            label = QLabel("Нет связей")
            label.setStyleSheet("color: #888; font-style: italic;")
            self._links_list.addWidget(label)
            return

        dark = ThemeEngine._current_theme == "dark"
        pal = palette(dark)
        for link in links:
            if (
                link["source_table"] == self._table
                and link["source_id"] == self._record_id
            ):
                other_table = link["target_table"]
                other_id = link["target_id"]
            else:
                other_table = link["source_table"]
                other_id = link["source_id"]

            name = self._db.get_linked_record_name(other_table, other_id)

            row = QFrame()
            row.setStyleSheet(f"""
                QFrame {{
                    background: {pal.bg_tertiary};
                    border-radius: 6px; padding: 6px 10px;
                }}
            """)
            rl = QHBoxLayout(row)
            rl.setContentsMargins(8, 4, 8, 4)

            icon_map = {
                "employees": "🧑‍💼",
                "violations": "⚠️",
                "companies": "🏢",
                "incidents": "🔥",
                "ppe": "🛡️",
                "training": "📚",
                "permits": "📋",
                "custom_ledger": "📓",
                "notes": "📝",
            }
            icon = QLabel(icon_map.get(other_table, "📎"))
            rl.addWidget(icon)

            text = QLabel(f"<b>{other_table}</b> #{other_id}: {name}")
            text.setWordWrap(True)
            rl.addWidget(text, 1)

            open_btn = GlassButton("→")
            open_btn.setFixedSize(28, 28)
            open_btn.setProperty("flat", True)
            open_btn.setToolTip("Открыть")
            open_btn.clicked.connect(
                lambda checked, t=other_table, i=other_id: self._open_link(t, i)
            )
            rl.addWidget(open_btn)

            del_btn = GlassButton("✕")
            del_btn.setFixedSize(28, 28)
            del_btn.setProperty("flat", True)
            del_btn.setStyleSheet("color: #FF3B30;")
            del_btn.clicked.connect(
                lambda checked, lid=link["id"]: self._delete_link(lid)
            )
            rl.addWidget(del_btn)

            self._links_list.addWidget(row)

    def _add_link(self) -> None:
        target_table = self._target_table.currentText()
        target_id = self._target_id.value()
        if self._db.add_record_link(
            self._table, self._record_id, target_table, target_id
        ):
            self._refresh_links()

    def _delete_link(self, link_id: int) -> None:
        reply = QMessageBox.question(
            self,
            I18n._("common.confirm"),
            "Удалить связь?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._db.remove_record_link(link_id)
            self._refresh_links()

    def _open_link(self, table: str, record_id: int) -> None:
        self.link_activated.emit(table, record_id)
        self.accept()
