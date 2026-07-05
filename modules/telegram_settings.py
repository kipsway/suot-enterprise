import json
from typing import Any, Dict, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QFrame, QVBoxLayout, QHBoxLayout, QFormLayout,
                             QLabel, QLineEdit, QPushButton, QCheckBox,
                             QTableWidget, QTableWidgetItem, QHeaderView,
                             QAbstractItemView, QGroupBox)

from app_core.i18n import I18n
from services.database import DatabaseManager
from services.telegram_bot import TelegramBot
from widgets.toast import ToastNotification


class TelegramSettingsWidget(QFrame):
    def __init__(self, parent: Optional[QFrame] = None) -> None:
        super().__init__(parent)
        self.setProperty("card", True)
        self.db = DatabaseManager()
        self._build_ui()
        self._load_values()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self._token_edit = QLineEdit()
        self._token_edit.setPlaceholderText("1234567890:ABCdefGHIjklMNOpqrsTUVwxyz")
        self._token_edit.setEchoMode(QLineEdit.Password)
        self._token_edit.textChanged.connect(self._on_token_changed)
        form.addRow(I18n._("telegram.bot_token") + ":", self._token_edit)

        token_layout = QHBoxLayout()
        self._show_token_cb = QCheckBox(I18n._("telegram.show_token"))
        self._show_token_cb.toggled.connect(self._toggle_token_visibility)
        token_layout.addWidget(self._show_token_cb)
        token_layout.addStretch()
        form.addRow("", token_layout)

        self._enabled_cb = QCheckBox(I18n._("telegram.enabled"))
        form.addRow("", self._enabled_cb)

        self._test_btn = QPushButton(I18n._("telegram.test_connection"))
        self._test_btn.clicked.connect(self._test_connection)
        form.addRow("", self._test_btn)

        layout.addLayout(form)

        # --- Registered users ---
        group = QGroupBox(I18n._("telegram.registered_users"))
        group_layout = QVBoxLayout(group)
        self._users_table = QTableWidget()
        self._users_table.setColumnCount(2)
        self._users_table.setHorizontalHeaderLabels([
            I18n._("user.username"), I18n._("telegram.chat_id")])
        hdr = self._users_table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.Stretch)
        self._users_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._users_table.verticalHeader().hide()
        self._users_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        group_layout.addWidget(self._users_table)
        layout.addWidget(group)

        btn_layout = QHBoxLayout()
        self._refresh_btn = QPushButton(I18n._("common.refresh"))
        self._refresh_btn.clicked.connect(self._refresh_users)
        btn_layout.addWidget(self._refresh_btn)
        btn_layout.addStretch()
        self._unregister_btn = QPushButton(I18n._("telegram.unregister"))
        self._unregister_btn.clicked.connect(self._unregister_user)
        btn_layout.addWidget(self._unregister_btn)
        layout.addLayout(btn_layout)

        layout.addStretch()

    def _load_values(self) -> None:
        token = self.db.get_setting("telegram_bot_token", "")
        self._token_edit.setText(token)
        enabled = self.db.get_setting("telegram_enabled", "false")
        self._enabled_cb.setChecked(enabled == "true")
        self._refresh_users()

    def _save_values(self) -> None:
        token = self._token_edit.text().strip()
        enabled = "true" if self._enabled_cb.isChecked() else "false"
        old_token = self.db.get_setting("telegram_bot_token", "")
        old_enabled = self.db.get_setting("telegram_enabled", "false")
        self.db.upsert_setting("telegram_bot_token", token)
        self.db.upsert_setting("telegram_enabled", enabled)
        bot = TelegramBot()
        if token != old_token or enabled != old_enabled:
            bot.restart()

    def _toggle_token_visibility(self, checked: bool) -> None:
        self._token_edit.setEchoMode(
            QLineEdit.Normal if checked else QLineEdit.Password)

    def _on_token_changed(self) -> None:
        pass

    def _test_connection(self) -> None:
        token = self._token_edit.text().strip()
        if not token:
            ToastNotification.notify(
                I18n._("telegram.no_token"), "warning", 3000)
            return
        try:
            import requests
            resp = requests.get(
                f"https://api.telegram.org/bot{token}/getMe", timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("ok"):
                    bot_info = data.get("result", {})
                    name = bot_info.get("first_name", "?")
                    username = bot_info.get("username", "?")
                    ToastNotification.notify(
                        I18n._("telegram.test_ok").format(name=name, username=username),
                        "success", 5000)
                    return
            ToastNotification.notify(
                I18n._("telegram.test_fail"), "error", 5000)
        except Exception as e:
            ToastNotification.notify(
                I18n._("telegram.test_error").format(error=str(e)), "error", 5000)

    def _refresh_users(self) -> None:
        bot = TelegramBot()
        bot._load_chat_map()
        chat_map = bot._chat_map
        self._users_table.setRowCount(len(chat_map))
        for i, (username, chat_id) in enumerate(sorted(chat_map.items())):
            self._users_table.setItem(i, 0, QTableWidgetItem(username))
            self._users_table.setItem(i, 1, QTableWidgetItem(str(chat_id)))
        self._users_table.resizeColumnsToContents()

    def _unregister_user(self) -> None:
        row = self._users_table.currentRow()
        if row < 0:
            return
        username = self._users_table.item(row, 0).text()
        bot = TelegramBot()
        if username in bot._chat_map:
            del bot._chat_map[username]
            bot._save_chat_map()
            self._refresh_users()
            ToastNotification.notify(
                I18n._("telegram.unregistered").format(user=username),
                "success", 3000)
