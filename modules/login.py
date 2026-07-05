from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from PyQt5.QtCore import Qt, QEasingCurve, QPoint, QPropertyAnimation, QTimer
from PyQt5.QtGui import QCursor
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QLabel, QLineEdit,
                             QPushButton, QCheckBox, QFrame, QWidget)

from app_core.config import AppConfig
from app_core.i18n import I18n
from app_core.theme_engine import ThemeEngine
from services.security import SecurityEngine
from services.database import DatabaseManager


class LoginDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.db = DatabaseManager()
        self._authenticated_user: Optional[Dict[str, Any]] = None
        self._build_ui()
        self._try_auto_login()

    def _build_ui(self) -> None:
        self.setWindowTitle(I18n._("login.title"))
        self.setFixedSize(420, 480)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        is_dark = ThemeEngine._current_theme == "dark"
        glass_bg = (
            "qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            "  stop:0 rgba(255,255,255,0.82), stop:1 rgba(255,255,255,0.65))"
        ) if not is_dark else (
            "qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            "  stop:0 rgba(255,255,255,0.09), stop:1 rgba(255,255,255,0.04))"
        )
        glass_border = "rgba(255,255,255,0.40)" if not is_dark else "rgba(255,255,255,0.08)"

        main = QVBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)

        container = QFrame()
        container.setObjectName("loginContainer")
        container.setStyleSheet(f"""
            QFrame#loginContainer {{
                background: {glass_bg};
                border: 1px solid {glass_border};
                border-radius: 20px;
            }}
        """)
        cl = QVBoxLayout(container)
        cl.setContentsMargins(36, 36, 36, 36)
        cl.setSpacing(16)

        title = QLabel(I18n._("app.name"))
        title.setProperty("heading", True)
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 26px; letter-spacing: -0.5px;")
        cl.addWidget(title)

        subtitle = QLabel(I18n._("login.title"))
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("font-size: 14px; margin-bottom: 4px; opacity: 0.7;")
        cl.addWidget(subtitle)

        cl.addSpacing(8)

        self._username_edit = QLineEdit()
        self._username_edit.setPlaceholderText(I18n._("login.username"))
        cl.addWidget(self._username_edit)

        self._password_edit = QLineEdit()
        self._password_edit.setPlaceholderText(I18n._("login.password"))
        self._password_edit.setEchoMode(QLineEdit.Password)
        cl.addWidget(self._password_edit)

        self._remember_cb = QCheckBox(I18n._("login.remember"))
        cl.addWidget(self._remember_cb)

        self._error_label = QLabel()
        self._error_label.setStyleSheet(f"color: #E74C3C; font-size: 12px;")
        self._error_label.setAlignment(Qt.AlignCenter)
        self._error_label.hide()
        cl.addWidget(self._error_label)

        login_btn = QPushButton(I18n._("login.btn"))
        login_btn.setCursor(QCursor(Qt.PointingHandCursor))
        login_btn.clicked.connect(self._on_login)
        login_btn.setDefault(True)
        login_btn.setMinimumHeight(44)
        login_btn.setStyleSheet(
            "font-size: 15px; font-weight: 700; letter-spacing: 0.3px;"
        )
        cl.addWidget(login_btn)

        self._password_edit.returnPressed.connect(login_btn.click)
        self._username_edit.returnPressed.connect(self._password_edit.setFocus)

        main.addWidget(container, 0, Qt.AlignCenter)

        self._original_pos: Optional[QPoint] = None

    def _try_auto_login(self) -> None:
        user = self.db.session_manager.validate_remember_me()
        if user:
            self._authenticated_user = user
            I18n.set_language(self.db.get_setting("app_language", "ru"))
            self._auto_logged_in = True

    def _on_login(self) -> None:
        username = self._username_edit.text().strip()
        password = self._password_edit.text()
        if not username or not password:
            self._show_error(I18n._("login.error.empty"))
            return
        user = self.db.fetch_one(
            "SELECT id, username, password_hash, salt, role FROM users WHERE username=?",
            (username,))
        if not user:
            self._show_error(I18n._("login.error.invalid"))
            self._shake()
            self.db.log_event(f"Failed login attempt for: {username}", "WARNING",
                              {"username": username})
            return
        stored_hash = user["password_hash"]
        salt = user["salt"]
        if not SecurityEngine.verify(stored_hash, salt, password):
            self._show_error(I18n._("login.error.invalid"))
            self._shake()
            self.db.log_event(f"Failed login attempt for: {username}", "WARNING",
                              {"username": username})
            return
        self._authenticated_user = user
        self.db.log_event(f"User logged in: {username}", "INFO",
                          {"username": username, "role": user.get("role")})
        if self._remember_cb.isChecked():
            token = SecurityEngine.create_token()
            expiry = datetime.now() + timedelta(days=AppConfig.TOKEN_TTL_DAYS)
            self.db.session_manager.save_remember_me(username, token, expiry)
        self._on_auth_success()

    def _on_auth_success(self) -> None:
        I18n.set_language(self.db.get_setting("app_language", "ru"))
        self.accept()

    def _show_error(self, msg: str) -> None:
        self._error_label.setText(msg)
        self._error_label.show()
        QTimer.singleShot(3000, self._error_label.hide)

    def _shake(self) -> None:
        if self._original_pos is None:
            self._original_pos = self.mapToGlobal(QPoint(0, 0))
        pos = self._original_pos
        anim = QPropertyAnimation(self, b"pos")
        anim.setDuration(400)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        steps = [
            (0.00, pos), (0.10, pos + QPoint(15, 0)),
            (0.25, pos - QPoint(15, 0)), (0.40, pos + QPoint(10, 0)),
            (0.55, pos - QPoint(10, 0)), (0.70, pos + QPoint(6, 0)),
            (0.85, pos - QPoint(6, 0)), (1.00, pos),
        ]
        for frac, pt in steps:
            anim.setKeyValueAt(frac, pt)
        anim.start()

    def authenticated_user(self) -> Optional[Dict[str, Any]]:
        return self._authenticated_user
