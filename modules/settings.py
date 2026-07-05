import json, os, csv, re, traceback, webbrowser, tempfile
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Callable
from PyQt5.QtCore import Qt, QTimer, QSettings
from PyQt5.QtGui import QColor, QFont, QPixmap, QCursor, QKeySequence
from PyQt5.QtWidgets import (QApplication, QDialog, QWidget, QFrame,
    QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QSpinBox, QCheckBox, QTabWidget,
    QListWidget, QListWidgetItem, QGroupBox, QMessageBox,
    QInputDialog, QFileDialog, QColorDialog, QHeaderView,
    QAbstractItemView, QTableWidget, QTableWidgetItem, QMenu,
    QDialogButtonBox, QScrollArea, QShortcut, QMainWindow)

from app_core.i18n import I18n
from app_core.config import RUNTIME_PATHS, AppConfig
from app_core.theme_engine import ThemeEngine
from app_core.utils import ACCENT_COLORS, JsonUtils
from services.database import DatabaseManager
from services.security import SecurityEngine
from modules.reminders import ReminderEngine
from modules.email_settings import EmailSettingsWidget
from modules.rest_api_settings import RESTAPISettingsWidget
from modules.telegram_settings import TelegramSettingsWidget
from modules.webhook_settings import WebhookSettingsWidget
from modules.system_monitor import SystemMonitorWidget
from widgets.toast import ToastNotification

from modules.employees import EmployeeEditDialog
from modules.violations import ViolationEditDialog
from modules.data_dialogs import ExportDialog, ImportDialog, ReportDialog


class SettingsDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.db = DatabaseManager()
        self.setWindowTitle(I18n._("settings.title"))
        self.setMinimumSize(520, 400)
        self.resize(560, 420)
        self._build_ui()
        self._load_values()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)

        tabs = QTabWidget()
        layout.addWidget(tabs)

        # --- General tab ---
        general = QFrame()
        general.setProperty("card", True)
        gl = QFormLayout(general)
        gl.setContentsMargins(20, 20, 20, 20)
        gl.setSpacing(12)

        self._lang_combo = QComboBox()
        self._lang_combo.addItem("Русский", "ru")
        self._lang_combo.addItem("English", "en")
        gl.addRow(I18n._("settings.language") + ":", self._lang_combo)

        self._theme_combo = QComboBox()
        self._theme_combo.addItem(I18n._("settings.light"), "light")
        self._theme_combo.addItem(I18n._("settings.dark"), "dark")
        gl.addRow(I18n._("settings.theme") + ":", self._theme_combo)

        # Accent color picker
        accent_frame = QFrame()
        af = QHBoxLayout(accent_frame)
        af.setContentsMargins(0, 0, 0, 0)
        af.setSpacing(6)
        self._accent_btns: Dict[str, QPushButton] = {}
        for name, color in ACCENT_COLORS.items():
            btn = QPushButton()
            btn.setFixedSize(28, 28)
            btn.setStyleSheet(
                f"background: {color}; border-radius: 14px; "
                f"border: 2px solid {'#2C3E50' if color == self.db.get_setting('accent_color', '#2196F3') else 'transparent'};")
            btn.setCursor(QCursor(Qt.PointingHandCursor))
            btn.setToolTip(name.capitalize())
            btn.clicked.connect(lambda checked, c=color, b=btn: self._select_accent(c, b))
            af.addWidget(btn)
            self._accent_btns[name] = btn
        af.addStretch()
        gl.addRow(I18n._("settings.accent_color") + ":", accent_frame)

        tabs.addTab(general, I18n._("settings.title"))

        # --- System tab ---
        system = QFrame()
        system.setProperty("card", True)
        sl = QFormLayout(system)
        sl.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        sl.setContentsMargins(20, 20, 20, 20)
        sl.setSpacing(12)

        self._auto_save_spin = QSpinBox()
        self._auto_save_spin.setRange(5, 600)
        self._auto_save_spin.setSuffix(" sec")
        sl.addRow(I18n._("settings.auto_save") + ":", self._auto_save_spin)

        self._reminder_spin = QSpinBox()
        self._reminder_spin.setRange(10, 3600)
        self._reminder_spin.setSuffix(" sec")
        sl.addRow(I18n._("settings.reminder_interval") + ":", self._reminder_spin)

        media_layout = QHBoxLayout()
        self._media_path_edit = QLineEdit()
        self._media_path_edit.setMinimumWidth(250)
        media_layout.addWidget(self._media_path_edit)
        browse_btn = QPushButton("...")
        browse_btn.setFixedWidth(36)
        browse_btn.clicked.connect(self._browse_media)
        media_layout.addWidget(browse_btn)
        sl.addRow(I18n._("settings.media_path") + ":", media_layout)

        # --- Браузер для печати ---
        browser_layout = QHBoxLayout()
        self._browser_combo = QComboBox()
        self._browser_combo.setEditable(True)
        self._browser_combo.addItem(I18n._("settings.browser_default"), "default")
        self._browser_combo.addItem("Google Chrome", "chrome")
        self._browser_combo.addItem("Mozilla Firefox", "firefox")
        self._browser_combo.addItem("Microsoft Edge", "edge")
        self._browser_combo.addItem(I18n._("settings.browser_custom"), "custom")
        self._browser_combo.setMinimumWidth(200)
        browser_layout.addWidget(self._browser_combo)
        self._browser_path_edit = QLineEdit()
        self._browser_path_edit.setPlaceholderText(I18n._("settings.browser_path_hint"))
        self._browser_path_edit.setMinimumWidth(200)
        browser_layout.addWidget(self._browser_path_edit)
        sl.addRow(I18n._("settings.browser") + ":", browser_layout)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("border: none; border-top: 1px solid #ddd; margin: 8px 0;")
        sl.addRow(sep)

        self._auto_backup_cb = QCheckBox(I18n._("backup.auto_enable"))
        self._auto_backup_cb.setChecked(
            self.db.get_setting("auto_backup_enabled", "false") == "true")
        sl.addRow("", self._auto_backup_cb)

        backup_int_layout = QHBoxLayout()
        self._backup_interval = QSpinBox()
        self._backup_interval.setRange(1, 168)
        self._backup_interval.setValue(
            int(self.db.get_setting("auto_backup_interval_hours", "24")))
        self._backup_interval.setSuffix(" " + I18n._("backup.hours"))
        self._backup_interval.setMinimumHeight(36)
        backup_int_layout.addWidget(self._backup_interval)
        backup_int_layout.addStretch()
        sl.addRow(I18n._("backup.auto_interval") + ":", backup_int_layout)

        backup_max_layout = QHBoxLayout()
        self._backup_max = QSpinBox()
        self._backup_max.setRange(0, 100)
        self._backup_max.setValue(
            int(self.db.get_setting("auto_backup_max", "10")))
        self._backup_max.setSpecialValueText(I18n._("backup.keep_all"))
        self._backup_max.setMinimumHeight(36)
        backup_max_layout.addWidget(self._backup_max)
        backup_max_layout.addStretch()
        sl.addRow(I18n._("backup.keep") + ":", backup_max_layout)

        tabs.addTab(system, I18n._("common.system"))

        # --- Telegram tab ---
        self._telegram_tab = TelegramSettingsWidget()
        tabs.addTab(self._telegram_tab, I18n._("telegram.title"))

        # --- REST API tab ---
        self._rest_api_tab = RESTAPISettingsWidget()
        tabs.addTab(self._rest_api_tab, I18n._("rest_api.title"))

        # --- Email tab ---
        self._email_tab = EmailSettingsWidget()
        tabs.addTab(self._email_tab, I18n._("email.title"))

        # --- Webhook tab ---
        self._webhook_tab = WebhookSettingsWidget()
        tabs.addTab(self._webhook_tab, I18n._("webhook.title"))

        # --- System Monitor tab ---
        self._monitor_tab = SystemMonitorWidget()
        tabs.addTab(self._monitor_tab, I18n._("monitor.title"))

        # --- Customization tab ---
        custom = QFrame()
        custom.setProperty("card", True)
        cl = QVBoxLayout(custom)
        cl.setContentsMargins(20, 20, 20, 20)
        cl.setSpacing(8)

        hint = QLabel(I18n._("settings.customize_hint"))
        hint.setWordWrap(True)
        hint.setStyleSheet("font-size: 13px; padding: 6px 0;")
        cl.addWidget(hint)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll_inner = QWidget()
        scroll_form = QFormLayout(scroll_inner)
        scroll_form.setSpacing(8)
        scroll_form.setContentsMargins(0, 0, 0, 0)

        btn_defs = [
            ("btn_theme", I18n._("settings.btn_theme")),
            ("btn_lang", I18n._("settings.btn_lang")),
            ("btn_logout", I18n._("settings.btn_logout")),
            ("btn_user", I18n._("user.title")),
            ("btn_settings", I18n._("settings.btn_settings")),
            ("btn_users", I18n._("settings.btn_users")),
            ("btn_ai", I18n._("settings.btn_ai")),
            ("btn_notes", I18n._("settings.btn_notes")),
            ("btn_analytics", I18n._("settings.btn_analytics")),
            ("btn_textbook", I18n._("settings.btn_textbook")),
            ("btn_risk", I18n._("settings.btn_risk")),
            ("btn_backup", I18n._("settings.btn_backup")),
            ("btn_report", I18n._("settings.btn_report")),
            ("btn_export_log", I18n._("settings.btn_export_log")),
            ("btn_merge", I18n._("settings.btn_merge")),
            ("btn_ai_diag", I18n._("settings.btn_ai_diag")),
            ("btn_knowledge", I18n._("settings.btn_knowledge")),
            ("btn_print", I18n._("settings.btn_print")),
            ("btn_about", I18n._("settings.btn_about")),
        ]
        self._btn_fields = {}
        scroll_form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        for key, default_label in btn_defs:
            field_widget = QWidget()
            field_layout = QHBoxLayout(field_widget)
            field_layout.setContentsMargins(0, 0, 0, 0)
            field_layout.setSpacing(8)
            edit_field = QLineEdit()
            saved = self.db.get_setting(key, "")
            edit_field.setText(saved)
            edit_field.setPlaceholderText(default_label)
            edit_field.setMinimumHeight(28)
            field_layout.addWidget(edit_field, 1)
            reset_btn = QPushButton(I18n._("common.reset"))
            reset_btn.setFixedWidth(60)
            reset_btn.clicked.connect(lambda checked, k=key, e=edit_field, d=default_label: e.setText(d))
            field_layout.addWidget(reset_btn)
            scroll_form.addRow(default_label, field_widget)
            self._btn_fields[key] = edit_field

        scroll.setWidget(scroll_inner)
        cl.addWidget(scroll, 1)

        tabs.addTab(custom, I18n._("settings.customize"))

        # --- Buttons ---
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        save_btn = QPushButton(I18n._("common.save"))
        save_btn.setProperty("success", True)
        save_btn.clicked.connect(self._save)
        btn_layout.addWidget(save_btn)

        cancel_btn = QPushButton(I18n._("common.cancel"))
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(btn_layout)

    def _select_accent(self, color: str, btn: QPushButton) -> None:
        for b in self._accent_btns.values():
            b.setStyleSheet(b.styleSheet().replace(
                "border: 2px solid #2C3E50", "border: 2px solid transparent"))
        btn.setStyleSheet(
            f"background: {color}; border-radius: 14px; "
            f"border: 2px solid #2C3E50;")
        self._selected_accent = color

    def _browse_media(self) -> None:
        path = QFileDialog.getExistingDirectory(self, I18n._("settings.media_path"),
                                                 self._media_path_edit.text())
        if path:
            self._media_path_edit.setText(path)

    def _load_values(self) -> None:
        idx = self._lang_combo.findData(self.db.get_setting("app_language", "ru"))
        if idx >= 0:
            self._lang_combo.setCurrentIndex(idx)
        idx = self._theme_combo.findData(self.db.get_setting("theme", "light"))
        if idx >= 0:
            self._theme_combo.setCurrentIndex(idx)
        self._selected_accent = self.db.get_setting("accent_color", "#2196F3")
        for name, color in ACCENT_COLORS.items():
            if color == self._selected_accent:
                self._accent_btns[name].setStyleSheet(
                    f"background: {color}; border-radius: 14px; "
                    f"border: 2px solid #2C3E50;")
                break
        try:
            self._auto_save_spin.setValue(
                int(self.db.get_setting("auto_save_interval", "60")))
        except Exception:
            self._auto_save_spin.setValue(60)
        try:
            self._reminder_spin.setValue(
                int(self.db.get_setting("reminder_check_interval", "60")))
        except Exception:
            self._reminder_spin.setValue(60)
        self._media_path_edit.setText(
            self.db.get_setting("media_path", RUNTIME_PATHS.media_dir))

        # Load browser setting
        browser_type = self.db.get_setting("print_browser_type", "default")
        browser_path = self.db.get_setting("print_browser_path", "")
        bt_idx = self._browser_combo.findData(browser_type)
        if bt_idx >= 0:
            self._browser_combo.setCurrentIndex(bt_idx)
        self._browser_path_edit.setText(browser_path)

    def _save(self) -> None:
        lang = self._lang_combo.currentData()
        theme = self._theme_combo.currentData()
        accent = self._selected_accent
        auto_save = str(self._auto_save_spin.value())
        reminder = str(self._reminder_spin.value())
        media_path = self._media_path_edit.text().strip()
        browser_type = self._browser_combo.currentData() or "default"
        browser_path = self._browser_path_edit.text().strip()

        self.db.upsert_setting("app_language", lang)
        self.db.upsert_setting("theme", theme)
        self.db.upsert_setting("accent_color", accent)
        self.db.upsert_setting("auto_save_interval", auto_save)
        self.db.upsert_setting("reminder_check_interval", reminder)
        self.db.upsert_setting("media_path", media_path)
        self.db.upsert_setting("print_browser_type", browser_type)
        self.db.upsert_setting("print_browser_path", browser_path)

        self.db.upsert_setting("auto_backup_enabled",
                                "true" if self._auto_backup_cb.isChecked() else "false")
        self.db.upsert_setting("auto_backup_interval_hours",
                                str(self._backup_interval.value()))
        self.db.upsert_setting("auto_backup_max", str(self._backup_max.value()))

        try:
            self._telegram_tab._save_values()
        except Exception:
            pass
        try:
            self._rest_api_tab._save_values()
        except Exception:
            pass
        try:
            self._email_tab._save_values()
        except Exception:
            pass

        # Save custom button labels
        for key, field in self._btn_fields.items():
            val = field.text().strip()
            if val:
                self.db.upsert_setting(key, val)
            else:
                self.db.upsert_setting(key, "")

        if I18n.current() != lang:
            I18n.set_language(lang)
        ThemeEngine.apply(theme, accent)
        ToastNotification.notify(I18n._("settings.saved"), "success", 3000)
        self.accept()


class UsersDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.db = DatabaseManager()
        self.setWindowTitle(I18n._("user.title"))
        self.setMinimumSize(550, 400)
        self.resize(600, 450)
        self._build_ui()
        self._refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)

        toolbar = QHBoxLayout()
        add_btn = QPushButton(I18n._("user.add"))
        add_btn.setProperty("success", True)
        add_btn.clicked.connect(self._add_user)
        toolbar.addWidget(add_btn)

        self._delete_btn = QPushButton(I18n._("user.delete"))
        self._delete_btn.setProperty("danger", True)
        self._delete_btn.clicked.connect(self._delete_user)
        toolbar.addWidget(self._delete_btn)

        pw_btn = QPushButton(I18n._("user.change_password"))
        pw_btn.clicked.connect(self._change_password)
        toolbar.addWidget(pw_btn)

        role_btn = QPushButton(I18n._("user.change_role"))
        role_btn.clicked.connect(self._change_role)
        toolbar.addWidget(role_btn)

        totp_btn = QPushButton(I18n._("user.totp_setup"))
        totp_btn.clicked.connect(self._setup_totp)
        toolbar.addWidget(totp_btn)

        toolbar.addStretch()
        layout.addLayout(toolbar)

        self._table = QTableWidget()
        self._table.setColumnCount(3)
        self._table.setHorizontalHeaderLabels([
            I18n._("user.username"), I18n._("user.role"), ""])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setSelectionMode(QTableWidget.SingleSelection)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.verticalHeader().hide()
        layout.addWidget(self._table, 1)

    def _refresh(self) -> None:
        self._table.setRowCount(0)
        users = self.db.fetch_all(
            "SELECT id, username, role FROM users ORDER BY id")
        self._user_ids: List[int] = []
        for row in users:
            n = self._table.rowCount()
            self._table.insertRow(n)
            self._table.setItem(n, 0, QTableWidgetItem(row["username"]))
            self._table.setItem(n, 1, QTableWidgetItem(row["role"]))
            self._user_ids.append(row["id"])
        self._table.resizeColumnsToContents()

    def _selected_user_id(self) -> Optional[int]:
        row = self._table.currentRow()
        if row < 0 or row >= len(self._user_ids):
            ToastNotification.notify(I18n._("common.no_selection"), "warning", 2000)
            return None
        return self._user_ids[row]

    def _add_user(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle(I18n._("user.add"))
        dlg.setMinimumWidth(320)
        fl = QFormLayout(dlg)
        fl.setContentsMargins(16, 16, 16, 16)
        fl.setSpacing(10)

        ue = QLineEdit()
        ue.setPlaceholderText(I18n._("user.username"))
        fl.addRow(I18n._("user.username") + ":", ue)

        pe = QLineEdit()
        pe.setEchoMode(QLineEdit.Password)
        pe.setPlaceholderText(I18n._("user.password"))
        fl.addRow(I18n._("user.password") + ":", pe)

        rc = QComboBox()
        rc.addItem(I18n._("user.role_admin"), "Administrator")
        rc.addItem(I18n._("user.role_inspector"), "Inspector")
        rc.addItem(I18n._("user.role_manager"), "Manager")
        fl.addRow(I18n._("user.role") + ":", rc)

        bl = QHBoxLayout()
        bl.addStretch()
        ok_btn = QPushButton(I18n._("common.save"))
        ok_btn.setProperty("success", True)
        ok_btn.clicked.connect(dlg.accept)
        bl.addWidget(ok_btn)
        cancel_btn = QPushButton(I18n._("common.cancel"))
        cancel_btn.clicked.connect(dlg.reject)
        bl.addWidget(cancel_btn)
        fl.addRow(bl)

        if dlg.exec_() != QDialog.Accepted:
            return
        username = ue.text().strip()
        password = pe.text().strip()
        role = rc.currentData()
        if not username or not password:
            ToastNotification.notify(I18n._("login.error.empty"), "warning", 2000)
            return
        pw_hash, salt = SecurityEngine.generate_hash(password)
        try:
            self.db.execute(
                "INSERT INTO users (username, password_hash, salt, role) VALUES (?, ?, ?, ?)",
                (username, pw_hash, salt, role))
            self.db.log_event(f"User created: {username}", "INFO")
            self._refresh()
            ToastNotification.notify(I18n._("common.success"), "success", 2000)
        except Exception as e:
            ToastNotification.notify(str(e), "danger", 3000)

    def _delete_user(self) -> None:
        uid = self._selected_user_id()
        if uid is None:
            return
        user = self.db.fetch_one(
            "SELECT username FROM users WHERE id=?", (uid,))
        if not user:
            return
        if user["username"] == getattr(getattr(self, 'parent')(), '_user', {}).get("username", ""):
            ToastNotification.notify("Cannot delete yourself", "warning", 3000)
            return
        reply = QMessageBox.question(
            self, I18n._("user.delete"),
            I18n._("user.delete_confirm").format(username=user["username"]),
            QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.db.execute("DELETE FROM users WHERE id=?", (uid,))
            self.db.log_event(f"User deleted: {user['username']}", "WARNING")
            self._refresh()
            ToastNotification.notify(I18n._("common.success"), "success", 2000)

    def _change_password(self) -> None:
        uid = self._selected_user_id()
        if uid is None:
            return
        user = self.db.fetch_one(
            "SELECT username FROM users WHERE id=?", (uid,))
        if not user:
            return
        password, ok = QInputDialog.getText(
            self, I18n._("user.password_change_title"),
            I18n._("user.password"), echo=QLineEdit.Password)
        if ok and password.strip():
            pw_hash, salt = SecurityEngine.generate_hash(password.strip())
            self.db.execute(
                "UPDATE users SET password_hash=?, salt=? WHERE id=?",
                (pw_hash, salt, uid))
            self.db.log_event(f"Password changed for: {user['username']}", "INFO")
            ToastNotification.notify(I18n._("common.success"), "success", 2000)

    def _change_role(self) -> None:
        uid = self._selected_user_id()
        if uid is None:
            return
        user = self.db.fetch_one(
            "SELECT username, role FROM users WHERE id=?", (uid,))
        if not user:
            return
        roles = ["Administrator", "Inspector", "Manager"]
        role, ok = QInputDialog.getItem(
            self, I18n._("user.change_role"),
            I18n._("user.role"), roles, 0, False)
        if ok and role:
            self.db.execute("UPDATE users SET role=? WHERE id=?",
                            (role, uid))
            self.db.log_event(f"Role changed for {user['username']}: {role}", "INFO")
            self._refresh()
            ToastNotification.notify(I18n._("common.success"), "success", 2000)

    def _setup_totp(self) -> None:
        uid = self._selected_user_id()
        if uid is None:
            return
        user = self.db.fetch_one(
            "SELECT username, totp_secret, backup_codes FROM users WHERE id=?", (uid,))
        if not user:
            return
        from services.security import SecurityEngine
        from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QLabel, QPushButton,
                                     QHBoxLayout, QTextEdit, QFrame)
        dlg = QDialog(self)
        dlg.setWindowTitle(I18n._("user.totp_setup"))
        dlg.setMinimumWidth(500)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        secret = user.get("totp_secret", "") or ""
        if not secret:
            secret = SecurityEngine.generate_totp_secret_b32()
        uri = SecurityEngine.get_totp_uri(secret, user["username"])
        layout.addWidget(QLabel(I18n._("user.totp_instruction")))
        code_label = QLabel(f"<b>{secret}</b>")
        code_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        code_label.setAlignment(Qt.AlignCenter)
        code_label.setStyleSheet("font-size: 18px; letter-spacing: 2px; padding: 8px;")
        layout.addWidget(code_label)
        uri_edit = QTextEdit()
        uri_edit.setPlainText(uri)
        uri_edit.setMaximumHeight(60)
        uri_edit.setReadOnly(True)
        layout.addWidget(uri_edit)

        # Backup codes section
        backup_frame = QFrame()
        backup_frame.setStyleSheet("background: #FFF8E1; border: 1px solid #FFE082; border-radius: 8px;")
        bl = QVBoxLayout(backup_frame)
        bl.setContentsMargins(12, 10, 12, 10)
        bl.setSpacing(6)
        backup_heading = QLabel(I18n._("user.backup_codes_title"))
        backup_heading.setStyleSheet("font-weight: 600; font-size: 14px; color: #F57F17;")
        bl.addWidget(backup_heading)
        backup_desc = QLabel(I18n._("user.backup_codes_desc"))
        backup_desc.setStyleSheet("font-size: 11px; color: #795548;")
        backup_desc.setWordWrap(True)
        bl.addWidget(backup_desc)

        backup_codes = SecurityEngine.generate_backup_codes(10)
        codes_text = QTextEdit()
        codes_text.setPlainText("\n".join(f"{i+1}. {c}" for i, c in enumerate(backup_codes)))
        codes_text.setMaximumHeight(160)
        codes_text.setReadOnly(True)
        codes_text.setStyleSheet("font-family: monospace; font-size: 13px; padding: 6px;")
        bl.addWidget(codes_text)
        layout.addWidget(backup_frame)

        btn_layout = QHBoxLayout()
        save_btn = QPushButton(I18n._("common.save"))
        def _do_save():
            hashed = SecurityEngine.hash_backup_codes(backup_codes)
            import json
            self.db.execute(
                "UPDATE users SET totp_secret=?, backup_codes=? WHERE id=?",
                (secret, json.dumps(hashed), uid))
            self.db.log_event(f"TOTP + backup codes set up for {user['username']}", "INFO")
            dlg.accept()
            ToastNotification.notify(I18n._("user.totp_saved"), "success", 3000)
        save_btn.clicked.connect(_do_save)
        btn_layout.addWidget(save_btn)
        cancel_btn = QPushButton(I18n._("common.cancel"))
        cancel_btn.clicked.connect(dlg.reject)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        dlg.exec_()


class AuditTab(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.db = DatabaseManager()
        self._build_ui()
        self._refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        toolbar = QHBoxLayout()
        lbl = QLabel(I18n._("audit.filter_severity") + ":")
        toolbar.addWidget(lbl)

        self._severity_filter = QComboBox()
        self._severity_filter.addItem(I18n._("filter.all"), "")
        self._severity_filter.addItem(I18n._("audit.info"), "INFO")
        self._severity_filter.addItem(I18n._("audit.warning"), "WARNING")
        self._severity_filter.addItem(I18n._("audit.critical"), "CRITICAL")
        self._severity_filter.currentIndexChanged.connect(self._refresh)
        toolbar.addWidget(self._severity_filter)

        refresh_btn = QPushButton(I18n._("common.refresh"))
        refresh_btn.setProperty("flat", True)
        refresh_btn.clicked.connect(self._refresh)
        toolbar.addWidget(refresh_btn)

        toolbar.addStretch()
        layout.addLayout(toolbar)

        self._table = QTableWidget()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels([
            I18n._("audit.timestamp"), I18n._("audit.event"),
            I18n._("audit.severity"), I18n._("audit.details"), ""])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.verticalHeader().hide()
        self._table.setAlternatingRowColors(True)
        layout.addWidget(self._table, 1)

    def _refresh(self) -> None:
        self._table.setRowCount(0)
        severity = self._severity_filter.currentData()
        try:
            if severity:
                rows = self.db.fetch_all(
                    "SELECT * FROM audit_log WHERE severity=? ORDER BY id DESC LIMIT 500",
                    (severity,))
            else:
                rows = self.db.fetch_all(
                    "SELECT * FROM audit_log ORDER BY id DESC LIMIT 500")
        except Exception:
            return
        for row in rows:
            n = self._table.rowCount()
            self._table.insertRow(n)
            ts = row.get("timestamp", "")
            event = row.get("event", "")
            sev = row.get("severity", "INFO")
            details = row.get("details", "{}")
            try:
                dd = json.loads(details) if isinstance(details, str) and details else {}
            except Exception:
                dd = {}
            detail_str = "; ".join(f"{k}={v}" for k, v in dd.items()) if dd else ""
            self._table.setItem(n, 0, QTableWidgetItem(ts))
            self._table.setItem(n, 1, QTableWidgetItem(event))
            self._table.setItem(n, 2, QTableWidgetItem(sev))
            self._table.setItem(n, 3, QTableWidgetItem(detail_str))
            color = "#27AE60" if sev == "INFO" else ("#F39C12" if sev == "WARNING" else "#E74C3C")
            self._table.item(n, 2).setForeground(QColor(color))
        self._table.resizeColumnsToContents()


class HotkeyManager:
    def __init__(self, window: QMainWindow) -> None:
        self._window = window
        self._shortcuts: List[QShortcut] = []
        self._setup()

    def _add(self, key: str, callback: Callable[[], None]) -> None:
        s = QShortcut(QKeySequence(key), self._window)
        s.activated.connect(callback)
        self._shortcuts.append(s)

    def _setup(self) -> None:
        w = self._window
        self._add("Ctrl+N", lambda: self._try_open(w, "employee_add"))
        self._add("Ctrl+V", lambda: self._try_open(w, "violation_add"))
        self._add("Ctrl+F", lambda: w._open_global_search())
        self._add("Ctrl+E", lambda: self._try_open(w, "export"))
        self._add("Ctrl+I", lambda: self._try_open(w, "import_"))
        self._add("Ctrl+R", lambda: self._try_open(w, "report"))
        self._add("Ctrl+S", lambda: (w.db.create_backup(),
            ToastNotification.notify(I18n._("common.success"), "success", 2000)))
        self._add("Ctrl+Q", w.close)
        self._add("F5", lambda: self._try_open(w, "refresh"))
        self._add("F1", lambda: w._show_about())
        # Tab switching shortcuts
        for i in range(1, 10):
            self._add(f"Alt+{i}", lambda idx=i-1: w._tab_widget.setCurrentIndex(idx) if idx < w._tab_widget.count() else None)

    @staticmethod
    def _try_open(window: QMainWindow, action: str) -> None:
        if action == "employee_add":
            db = DatabaseManager()
            cols = db.get_columns_config("employees")
            dlg = EmployeeEditDialog({}, cols, window)
            if dlg.exec_() == QDialog.Accepted:
                window._refresh_current_tab()
        elif action == "violation_add":
            db = DatabaseManager()
            cols = db.get_columns_config("violations")
            dlg = ViolationEditDialog({}, cols, window)
            if dlg.exec_() == QDialog.Accepted:
                window._refresh_current_tab()
        elif action == "export":
            dlg = ExportDialog(window)
            dlg.exec_()
        elif action == "import_":
            dlg = ImportDialog(window)
            if dlg.exec_() == QDialog.Accepted:
                window._refresh_current_tab()
        elif action == "report":
            dlg = ReportDialog(window)
            dlg.exec_()
        elif action == "refresh":
            window._refresh_current_tab()
