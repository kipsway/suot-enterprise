import secrets
from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QSpinBox,
    QGroupBox,
    QTextEdit,
)
from widgets.glass_checkbox import GlassCheckBox

from widgets.glass_button import GlassButton
from widgets.glass_line_edit import GlassLineEdit

from app_core.i18n import I18n
from services.database import DatabaseManager
from services.rest_api import RESTAPIServer
from widgets.toast import ToastNotification


class RESTAPISettingsWidget(QFrame):
    def __init__(self, parent: Optional[QFrame] = None) -> None:
        super().__init__(parent)
        self.setProperty("card", True)
        self.db = DatabaseManager()
        self._server: Optional[RESTAPIServer] = None
        self._build_ui()
        self._load_values()
        self._update_status()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self._enabled_cb = GlassCheckBox(I18n._("rest_api.enabled"))
        self._enabled_cb.toggled.connect(self._on_enabled_toggled)
        form.addRow("", self._enabled_cb)

        self._port_spin = QSpinBox()
        self._port_spin.setRange(1024, 65535)
        form.addRow(I18n._("rest_api.port") + ":", self._port_spin)

        api_key_layout = QHBoxLayout()
        self._api_key_edit = GlassLineEdit()
        self._api_key_edit.setEchoMode(GlassLineEdit.Password)
        api_key_layout.addWidget(self._api_key_edit)
        self._show_key_cb = GlassCheckBox(I18n._("rest_api.show_key"))
        self._show_key_cb.toggled.connect(
            lambda c: self._api_key_edit.setEchoMode(
                GlassLineEdit.Normal if c else GlassLineEdit.Password
            )
        )
        api_key_layout.addWidget(self._show_key_cb)
        gen_btn = GlassButton(I18n._("rest_api.generate_key"))
        gen_btn.clicked.connect(self._generate_key)
        api_key_layout.addWidget(gen_btn)
        form.addRow(I18n._("rest_api.api_key") + ":", api_key_layout)

        layout.addLayout(form)

        # --- Status ---
        status_group = QGroupBox(I18n._("rest_api.server_status"))
        status_layout = QVBoxLayout(status_group)
        self._status_label = QLabel()
        status_layout.addWidget(self._status_label)
        btn_layout = QHBoxLayout()
        self._start_btn = GlassButton(I18n._("rest_api.start"))
        self._start_btn.setProperty("success", True)
        self._start_btn.clicked.connect(self._start_server)
        btn_layout.addWidget(self._start_btn)
        self._stop_btn = GlassButton(I18n._("rest_api.stop"))
        self._stop_btn.setProperty("danger", True)
        self._stop_btn.clicked.connect(self._stop_server)
        btn_layout.addWidget(self._stop_btn)
        btn_layout.addStretch()
        self._refresh_btn = GlassButton(I18n._("common.refresh"))
        self._refresh_btn.clicked.connect(self._update_status)
        btn_layout.addWidget(self._refresh_btn)
        status_layout.addLayout(btn_layout)
        layout.addWidget(status_group)

        # --- Log ---
        log_group = QGroupBox(I18n._("rest_api.log"))
        log_layout = QVBoxLayout(log_group)
        self._log_view = QTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setMaximumHeight(150)
        log_layout.addWidget(self._log_view)
        layout.addWidget(log_group)

        layout.addStretch()

    def _load_values(self) -> None:
        enabled = self.db.get_setting("rest_api_enabled", "false")
        self._enabled_cb.setChecked(enabled == "true")
        try:
            port = int(self.db.get_setting("rest_api_port", "8888"))
        except (ValueError, TypeError):
            port = 8888
        self._port_spin.setValue(port)
        key = self.db.get_setting("rest_api_key", "")
        self._api_key_edit.setText(key)

    def _save_values(self) -> None:
        enabled = "true" if self._enabled_cb.isChecked() else "false"
        port = str(self._port_spin.value())
        key = self._api_key_edit.text().strip()
        old_enabled = self.db.get_setting("rest_api_enabled", "false")
        old_port = self.db.get_setting("rest_api_port", "8888")
        old_key = self.db.get_setting("rest_api_key", "")
        self.db.upsert_setting("rest_api_enabled", enabled)
        self.db.upsert_setting("rest_api_port", port)
        self.db.upsert_setting("rest_api_key", key)
        if enabled != old_enabled or port != old_port or key != old_key:
            if self._server:
                self._server.restart()

    def _on_enabled_toggled(self, checked: bool) -> None:
        self._start_btn.setEnabled(checked)

    def _generate_key(self) -> None:
        key = secrets.token_urlsafe(32)
        self._api_key_edit.setText(key)

    def _update_status(self) -> None:
        if self._server and self._server.is_running:
            self._status_label.setText(
                f"<span style='color:#4CAF50; font-size:14px;'>"
                f"● {I18n._('rest_api.running')} "
                f"http://127.0.0.1:{self._server.port}</span>"
            )
            self._start_btn.setEnabled(False)
            self._stop_btn.setEnabled(True)
        else:
            self._status_label.setText(
                f"<span style='color:#888; font-size:14px;'>"
                f"○ {I18n._('rest_api.stopped')}</span>"
            )
            self._start_btn.setEnabled(self._enabled_cb.isChecked())
            self._stop_btn.setEnabled(False)

    def _start_server(self) -> None:
        if not self._api_key_edit.text().strip():
            ToastNotification.notify(I18n._("rest_api.no_key_warning"), "warning", 3000)
        port = self._port_spin.value()
        self._server = RESTAPIServer()
        self._server.log_received.connect(self._on_log)
        self._server.start(port)
        self._update_status()

    def _stop_server(self) -> None:
        if self._server:
            self._server.stop()
        self._update_status()

    def _on_log(self, msg: str) -> None:
        self._log_view.append(msg)
