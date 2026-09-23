from typing import Any, Dict, Optional
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QPushButton,
    QGroupBox,
    QMessageBox,
    QRadioButton,
    QButtonGroup,
)
from PyQt5.QtCore import Qt
from widgets.glass_button import GlassButton
from widgets.glass_line_edit import GlassLineEdit
from widgets.toast import ToastNotification
from app_core.i18n import I18n
from app_core.db_interface import create_backend, SQLiteBackend, PostgreSQLBackend


class DatabaseSettingsWidget(QWidget):
    def __init__(self, db: Any, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._db = db
        self._build_ui()
        self._load_settings()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # --- Backend type ---
        type_group = QGroupBox("Тип базы данных")
        type_layout = QVBoxLayout(type_group)
        self._type_group = QButtonGroup(self)
        self._rb_sqlite = QRadioButton("SQLite")
        self._rb_pg = QRadioButton("PostgreSQL")
        self._type_group.addButton(self._rb_sqlite, 1)
        self._type_group.addButton(self._rb_pg, 2)
        type_layout.addWidget(self._rb_sqlite)
        type_layout.addWidget(self._rb_pg)
        layout.addWidget(type_group)

        # --- PostgreSQL settings ---
        pg_group = QGroupBox("Параметры PostgreSQL")
        pg_layout = QFormLayout(pg_group)
        pg_layout.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self._pg_host = GlassLineEdit()
        self._pg_host.setPlaceholderText("localhost")
        pg_layout.addRow("Хост:", self._pg_host)

        self._pg_port = QSpinBox()
        self._pg_port.setRange(1, 65535)
        self._pg_port.setValue(5432)
        pg_layout.addRow("Порт:", self._pg_port)

        self._pg_dbname = GlassLineEdit()
        self._pg_dbname.setPlaceholderText("suot")
        pg_layout.addRow("База данных:", self._pg_dbname)

        self._pg_user = GlassLineEdit()
        self._pg_user.setPlaceholderText("suot")
        pg_layout.addRow("Пользователь:", self._pg_user)

        self._pg_password = QLineEdit()
        self._pg_password.setEchoMode(QLineEdit.EchoMode.Password)
        self._pg_password.setPlaceholderText("Пароль")
        pg_layout.addRow("Пароль:", self._pg_password)

        layout.addWidget(pg_group)

        # --- Test & Apply ---
        btn_layout = QHBoxLayout()
        test_btn = GlassButton("Проверить подключение")
        test_btn.clicked.connect(self._test_connection)
        btn_layout.addWidget(test_btn)

        apply_btn = GlassButton("Применить и перезапустить")
        apply_btn.clicked.connect(self._apply)
        btn_layout.addWidget(apply_btn)

        layout.addLayout(btn_layout)
        layout.addStretch()

        # Toggle PG fields based on selection
        self._rb_sqlite.toggled.connect(self._toggle_pg_fields)
        self._toggle_pg_fields()

    def _toggle_pg_fields(self) -> None:
        enabled = self._rb_pg.isChecked()
        for w in (
            self._pg_host,
            self._pg_port,
            self._pg_dbname,
            self._pg_user,
            self._pg_password,
        ):
            w.setEnabled(enabled)

    def _load_settings(self) -> None:
        backend_type = self._db.get_setting("db_type", "sqlite")
        if backend_type == "postgresql":
            self._rb_pg.setChecked(True)
        else:
            self._rb_sqlite.setChecked(True)
        self._pg_host.setText(self._db.get_setting("db_host", ""))
        port_val = self._db.get_setting("db_port", "5432")
        try:
            self._pg_port.setValue(int(port_val))
        except Exception:
            self._pg_port.setValue(5432)
        self._pg_dbname.setText(self._db.get_setting("db_dbname", ""))
        self._pg_user.setText(self._db.get_setting("db_user", ""))
        pw = (
            self._db.decrypt_value(self._db.get_setting("db_password_enc", ""))
            if hasattr(self._db, "decrypt_value")
            else self._db.get_setting("db_password", "")
        )
        self._pg_password.setText(pw)

    def _test_connection(self) -> None:
        if self._rb_sqlite.isChecked():
            ToastNotification.notify("SQLite всегда доступен", "success", 3000)
            return
        cfg = self._get_pg_config()
        try:
            backend = PostgreSQLBackend(**cfg)
            health = backend.health()
            backend.close()
            ToastNotification.notify(
                f"PostgreSQL OK — {health.get('tables', '?')} таблиц", "success", 5000
            )
        except Exception as e:
            QMessageBox.critical(self, "Ошибка подключения", str(e))
            ToastNotification.notify("Ошибка подключения к PostgreSQL", "error", 5000)

    def _get_pg_config(self) -> Dict[str, Any]:
        return {
            "host": self._pg_host.text().strip() or "localhost",
            "port": self._pg_port.value(),
            "dbname": self._pg_dbname.text().strip() or "suot",
            "user": self._pg_user.text().strip() or "suot",
            "password": self._pg_password.text(),
        }

    def _apply(self) -> None:
        backend_type = "postgresql" if self._rb_pg.isChecked() else "sqlite"
        self._db.upsert_setting("db_type", backend_type)
        if backend_type == "postgresql":
            cfg = self._get_pg_config()
            self._db.upsert_setting("db_host", cfg["host"])
            self._db.upsert_setting("db_port", str(cfg["port"]))
            self._db.upsert_setting("db_dbname", cfg["dbname"])
            self._db.upsert_setting("db_user", cfg["user"])
            if hasattr(self._db, "encrypt_value"):
                self._db.upsert_setting(
                    "db_password_enc", self._db.encrypt_value(cfg["password"])
                )
            else:
                self._db.upsert_setting("db_password", cfg["password"])
        ToastNotification.notify(
            "Настройки БД сохранены. Перезапустите приложение для применения.",
            "info",
            5000,
        )
