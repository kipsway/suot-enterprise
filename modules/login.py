from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from PyQt5.QtCore import Qt, QEasingCurve, QPoint, QPropertyAnimation, QTimer
from PyQt5.QtGui import QCursor
from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QFrame,
    QWidget,
    QHBoxLayout,
)
from widgets.glass_checkbox import GlassCheckBox

from app_core.config import AppConfig
from app_core.i18n import I18n
from app_core.theme_engine import ThemeEngine
from services.security import SecurityEngine, RateLimiter
from services.database import DatabaseManager


class LoginDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.db = DatabaseManager()
        self._authenticated_user: Optional[Dict[str, Any]] = None
        self._rate_limiter = RateLimiter()
        self._step = "credentials"
        self._build_ui()
        self._try_auto_login()
        # Center on screen
        QTimer.singleShot(0, self._center_on_screen)

    def _build_ui(self) -> None:
        self.setWindowTitle("СУОТ Enterprise")
        self.setFixedSize(420, 520)
        self.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)
        self.setAttribute(Qt.WA_TranslucentBackground, False)

        is_dark = ThemeEngine._current_theme == "dark"
        glass_bg = (
            (
                "qlineargradient(x1:0, y1:0, x2:0, y2:1,"
                "  stop:0 rgba(255,255,255,0.82), stop:1 rgba(255,255,255,0.65))"
            )
            if not is_dark
            else (
                "qlineargradient(x1:0, y1:0, x2:0, y2:1,"
                "  stop:0 rgba(255,255,255,0.09), stop:1 rgba(255,255,255,0.04))"
            )
        )
        glass_border = (
            "rgba(255,255,255,0.40)" if not is_dark else "rgba(255,255,255,0.08)"
        )

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
        self._cl = QVBoxLayout(container)
        self._cl.setContentsMargins(36, 36, 36, 36)
        self._cl.setSpacing(16)

        title = QLabel(I18n._("app.name"))
        title.setProperty("heading", True)
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 26px; letter-spacing: -0.5px;")
        self._cl.addWidget(title)

        self._subtitle = QLabel(I18n._("login.title"))
        self._subtitle.setAlignment(Qt.AlignCenter)
        self._subtitle.setStyleSheet(
            "font-size: 14px; margin-bottom: 4px; opacity: 0.7;"
        )
        self._cl.addWidget(self._subtitle)

        self._cl.addSpacing(8)

        self._username_edit = QLineEdit()
        self._username_edit.setPlaceholderText(I18n._("login.username"))
        self._cl.addWidget(self._username_edit)

        self._password_edit = QLineEdit()
        self._password_edit.setPlaceholderText(I18n._("login.password"))
        self._password_edit.setEchoMode(QLineEdit.Password)
        self._cl.addWidget(self._password_edit)

        self._remember_cb = GlassCheckBox(I18n._("login.remember"))
        self._cl.addWidget(self._remember_cb)

        self._totp_layout = QHBoxLayout()
        self._totp_label = QLabel(I18n._("login.totp"))
        self._totp_label.hide()
        self._totp_layout.addWidget(self._totp_label)
        self._totp_edit = QLineEdit()
        self._totp_edit.setPlaceholderText("000000 " + I18n._("login.or_backup"))
        self._totp_edit.setMaxLength(30)
        self._totp_edit.hide()
        self._totp_layout.addWidget(self._totp_edit)
        self._cl.addLayout(self._totp_layout)

        self._lockout_label = QLabel()
        self._lockout_label.setStyleSheet("color: #E74C3C; font-size: 12px;")
        self._lockout_label.setAlignment(Qt.AlignCenter)
        self._lockout_label.hide()
        self._cl.addWidget(self._lockout_label)

        self._error_label = QLabel()
        self._error_label.setStyleSheet("color: #E74C3C; font-size: 12px;")
        self._error_label.setAlignment(Qt.AlignCenter)
        self._error_label.hide()
        self._cl.addWidget(self._error_label)

        self._login_btn = QPushButton(I18n._("login.btn"))
        self._login_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self._login_btn.clicked.connect(self._on_login)
        self._login_btn.setDefault(True)
        self._login_btn.setMinimumHeight(44)
        self._login_btn.setStyleSheet(
            "font-size: 15px; font-weight: 700; letter-spacing: 0.3px;"
        )
        self._cl.addWidget(self._login_btn)

        self._password_edit.returnPressed.connect(self._login_btn.click)
        self._username_edit.returnPressed.connect(self._password_edit.setFocus)
        self._totp_edit.returnPressed.connect(self._login_btn.click)

        main.addWidget(container, 0, Qt.AlignCenter)

        self._original_pos: Optional[QPoint] = None

    def _center_on_screen(self) -> None:
        from PyQt5.QtWidgets import QApplication

        screen = QApplication.primaryScreen()
        if screen:
            rect = screen.availableGeometry()
            self.move(rect.center() - self.rect().center())
        self.raise_()
        self.activateWindow()

    def _try_auto_login(self) -> None:
        user = self.db.session_manager.validate_remember_me()
        if user:
            self._authenticated_user = user
            I18n.set_language(self.db.get_setting("app_language", "ru"))
            self._auto_logged_in = True

    def _on_login(self) -> None:
        if self._step == "credentials":
            self._do_credentials_step()
        elif self._step == "totp":
            self._do_totp_step()

    def _do_credentials_step(self) -> None:
        username = self._username_edit.text().strip()
        password = self._password_edit.text()

        locked, remaining = self._rate_limiter.check_login(username)
        if locked:
            self._show_lockout(remaining)
            self.db.log_event(
                f"Login blocked (rate limit): {username}",
                "WARNING",
                {"username": username, "remaining": remaining},
            )
            return
        if not username or not password:
            self._show_error(I18n._("login.error.empty"))
            return
        user = self.db.fetch_one(
            "SELECT id, username, password_hash, salt, role, totp_secret, backup_codes "
            "FROM users WHERE username=?",
            (username,),
        )
        if not user:
            self._rate_limiter.record_login(username)
            self._show_error(I18n._("login.error.invalid"))
            self._shake()
            return

        stored_hash = user["password_hash"]
        salt = user["salt"]
        totp_secret = user.get("totp_secret", "") or ""

        if not SecurityEngine.verify(stored_hash, salt, password):
            self._rate_limiter.record_login(username)
            self._show_error(I18n._("login.error.invalid"))
            self._shake()
            self.db.log_event(
                f"Failed login: {username}", "WARNING", {"username": username}
            )
            return

        self._pending_user = user
        if totp_secret:
            self._step = "totp"
            self._subtitle.setText(I18n._("login.totp_title"))
            self._username_edit.hide()
            self._password_edit.hide()
            self._remember_cb.hide()
            self._totp_label.show()
            self._totp_edit.show()
            self._totp_edit.setFocus()
            self._login_btn.setText(I18n._("login.verify"))
        else:
            self._complete_login(user)

    def _do_totp_step(self) -> None:
        import json

        code = self._totp_edit.text().strip()
        pending = self._pending_user or {}
        totp_secret = str(pending.get("totp_secret", "") or "")
        if SecurityEngine.verify_totp(totp_secret, code):
            self._complete_login(pending)
            return
        raw_bc = str(pending.get("backup_codes", "[]") or "[]")
        try:
            hashed_codes = json.loads(raw_bc)
        except Exception:
            hashed_codes = []
        idx = SecurityEngine.verify_backup_code(hashed_codes, code)
        if idx is not None:
            hashed_codes.pop(idx)
            self.db.execute(
                "UPDATE users SET backup_codes=? WHERE id=?",
                (json.dumps(hashed_codes), pending["id"]),
            )
            self.db.conn.commit()
            self._complete_login(pending)
            return
        self._show_error(I18n._("login.totp_invalid"))
        self._shake()

    def _complete_login(self, user: Any) -> None:
        self._authenticated_user = user
        self._rate_limiter.clear_login(user["username"])
        self.db.log_event(
            f"User logged in: {user['username']}",
            "INFO",
            {"username": user["username"], "role": user.get("role")},
        )
        if self._remember_cb.isChecked() and self._step == "credentials":
            token = SecurityEngine.create_token()
            expiry = datetime.now() + timedelta(days=AppConfig.TOKEN_TTL_DAYS)
            self.db.session_manager.save_remember_me(user["username"], token, expiry)
        I18n.set_language(self.db.get_setting("app_language", "ru"))
        self.accept()

    def _show_lockout(self, remaining: int) -> None:
        self._lockout_label.setText(I18n._("login.locked").format(seconds=remaining))
        self._lockout_label.show()

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
            (0.00, pos),
            (0.10, pos + QPoint(15, 0)),
            (0.25, pos - QPoint(15, 0)),
            (0.40, pos + QPoint(10, 0)),
            (0.55, pos - QPoint(10, 0)),
            (0.70, pos + QPoint(6, 0)),
            (0.85, pos - QPoint(6, 0)),
            (1.00, pos),
        ]
        for frac, pt in steps:
            anim.setKeyValueAt(frac, pt)
        anim.start()

    def authenticated_user(self) -> Optional[Dict[str, Any]]:
        return self._authenticated_user
