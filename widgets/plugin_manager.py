"""Plugin Manager UI — list, enable/disable plugins."""

import os
from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QMessageBox,
)

from app_core.config import RUNTIME_PATHS
from app_core.i18n import I18n
from app_core.plugin_system import PluginManager, PluginInfo


class PluginManagerWidget(QFrame):
    def __init__(self, parent: Optional[QFrame] = None):
        super().__init__(parent)
        self.setProperty("card", True)
        self._manager = PluginManager(RUNTIME_PATHS.plugins_dir)
        self._build_ui()
        self._load()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        heading = QLabel("Плагины")
        heading.setProperty("heading", True)
        layout.addWidget(heading)

        hint = QLabel("Управление плагинами — включение/отключение, обнаружение новых.")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["Плагин", "Версия", "Статус"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setMinimumHeight(150)
        layout.addWidget(self._table)

        btn_layout = QHBoxLayout()
        refresh_btn = QPushButton("🔄 Обнаружить")
        refresh_btn.clicked.connect(self._load)
        btn_layout.addWidget(refresh_btn)

        toggle_btn = QPushButton("🔀 Вкл/Выкл")
        toggle_btn.clicked.connect(self._toggle_selected)
        btn_layout.addWidget(toggle_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

    def _load(self) -> None:
        plugins = self._manager.discover_plugins()
        self._table.setRowCount(len(plugins))
        for i, p in enumerate(plugins):
            self._table.setItem(i, 0, QTableWidgetItem(p.name))
            self._table.setItem(i, 1, QTableWidgetItem(p.instance.version))
            status = "✅ Включён" if p.enabled else "⛔ Отключён"
            item = QTableWidgetItem(status)
            item.setTextAlignment(Qt.AlignCenter)
            self._table.setItem(i, 2, item)

    def _toggle_selected(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            return
        name = self._table.item(row, 0).text()
        current_status = self._table.item(row, 2).text()
        enabled = "⛔" not in current_status
        self._manager.set_plugin_enabled(name, not enabled)
        self._load()
