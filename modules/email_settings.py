from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QSpinBox,
    QGroupBox,
)

from widgets.glass_button import GlassButton
from widgets.glass_checkbox import GlassCheckBox
from widgets.glass_line_edit import GlassLineEdit

from app_core.i18n import I18n
from services.database import DatabaseManager
from services.email_service import EmailService
from widgets.toast import ToastNotification


class EmailSettingsWidget(QFrame):
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

        self._enabled_cb = GlassCheckBox(I18n._("email.enabled"))
        form.addRow("", self._enabled_cb)

        self._host_edit = GlassLineEdit()
        self._host_edit.setPlaceholderText("smtp.gmail.com")
        form.addRow(I18n._("email.smtp_host") + ":", self._host_edit)

        self._port_spin = QSpinBox()
        self._port_spin.setRange(1, 65535)
        self._port_spin.setValue(587)
        form.addRow(I18n._("email.smtp_port") + ":", self._port_spin)

        self._tls_cb = GlassCheckBox(I18n._("email.use_tls"))
        self._tls_cb.setChecked(True)
        form.addRow("", self._tls_cb)

        self._username_edit = GlassLineEdit()
        form.addRow(I18n._("email.username") + ":", self._username_edit)

        self._password_edit = GlassLineEdit()
        self._password_edit.setEchoMode(GlassLineEdit.Password)
        pw_layout = QHBoxLayout()
        pw_layout.addWidget(self._password_edit)
        show_cb = GlassCheckBox(I18n._("email.show_password"))
        show_cb.toggled.connect(
            lambda c: self._password_edit.setEchoMode(
                GlassLineEdit.Normal if c else GlassLineEdit.Password
            )
        )
        pw_layout.addWidget(show_cb)
        form.addRow(I18n._("email.password") + ":", pw_layout)

        self._from_edit = GlassLineEdit()
        self._from_edit.setPlaceholderText("noreply@example.com")
        form.addRow(I18n._("email.from") + ":", self._from_edit)

        self._to_edit = GlassLineEdit()
        self._to_edit.setPlaceholderText("admin@example.com")
        form.addRow(I18n._("email.default_to") + ":", self._to_edit)

        layout.addLayout(form)

        # --- Test section ---
        test_group = QGroupBox(I18n._("email.test_title"))
        test_layout = QHBoxLayout(test_group)
        self._test_to_edit = GlassLineEdit()
        self._test_to_edit.setPlaceholderText("test@example.com")
        test_layout.addWidget(self._test_to_edit, 1)
        self._test_btn = GlassButton(I18n._("email.test_send"))
        self._test_btn.clicked.connect(self._send_test)
        test_layout.addWidget(self._test_btn)
        layout.addWidget(test_group)

        layout.addStretch()

    def _load_values(self) -> None:
        self._enabled_cb.setChecked(
            self.db.get_setting("email_enabled", "false") == "true"
        )
        self._host_edit.setText(self.db.get_setting("email_smtp_host", ""))
        try:
            self._port_spin.setValue(int(self.db.get_setting("email_smtp_port", "587")))
        except (ValueError, TypeError):
            self._port_spin.setValue(587)
        self._tls_cb.setChecked(self.db.get_setting("email_smtp_tls", "true") == "true")
        self._username_edit.setText(self.db.get_setting("email_username", ""))
        self._password_edit.setText(self.db.get_setting("email_password", ""))
        self._from_edit.setText(self.db.get_setting("email_from", ""))
        self._to_edit.setText(self.db.get_setting("email_default_to", ""))

    def _save_values(self) -> None:
        old_enabled = self.db.get_setting("email_enabled", "false")
        old_host = self.db.get_setting("email_smtp_host", "")
        enabled = "true" if self._enabled_cb.isChecked() else "false"
        self.db.upsert_setting("email_enabled", enabled)
        self.db.upsert_setting("email_smtp_host", self._host_edit.text().strip())
        self.db.upsert_setting("email_smtp_port", str(self._port_spin.value()))
        self.db.upsert_setting(
            "email_smtp_tls", "true" if self._tls_cb.isChecked() else "false"
        )
        self.db.upsert_setting("email_username", self._username_edit.text().strip())
        self.db.upsert_setting("email_password", self._password_edit.text())
        self.db.upsert_setting("email_from", self._from_edit.text().strip())
        self.db.upsert_setting("email_default_to", self._to_edit.text().strip())

    def _send_test(self) -> None:
        to_addr = self._test_to_edit.text().strip()
        if not to_addr:
            ToastNotification.notify(I18n._("email.test_no_recipient"), "warning", 3000)
            return
        err = EmailService().send_test(to_addr)
        if err:
            ToastNotification.notify(
                I18n._("email.test_error").format(error=err), "error", 5000
            )
        else:
            ToastNotification.notify(I18n._("email.test_ok"), "success", 5000)
