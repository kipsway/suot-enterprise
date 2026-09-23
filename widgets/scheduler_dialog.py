from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QVBoxLayout,
    QWidget,
    QAbstractItemView,
    QPushButton,
)

from app_core.i18n import I18n
from services.database import DatabaseManager
from services.schedule_service import ScheduleService
from widgets.glass_button import GlassButton
from widgets.glass_line_edit import GlassLineEdit
from widgets.glass_combo_box import GlassComboBox
from widgets.toast import ToastNotification


AVAILABLE_TASKS: Dict[str, str] = {
    "backup_auto": "Авто-резервное копирование",
    "email_report": "Email-рассылка отчётов",
    "cleanup_logs": "Очистка логов",
    "sync_telegram": "Синхронизация Telegram",
    "check_reminders": "Проверка напоминаний",
}


class SchedulerDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._db = DatabaseManager()
        self._scheduler = ScheduleService()
        self.setWindowTitle("Планировщик задач")
        self.setMinimumSize(600, 400)
        self.resize(650, 450)
        self._build_ui()
        self._load()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        header = QLabel("📅 Периодические задачи")
        f = self.font()
        f.setPointSize(14)
        f.setBold(True)
        header.setFont(f)
        layout.addWidget(header)

        self._table = QTableWidget()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(
            ["Задача", "Интервал", "Включена", "Последний запуск", "Действия"]
        )
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self._table, 1)

        add_layout = QHBoxLayout()
        add_layout.setSpacing(6)

        self._task_combo = GlassComboBox()
        self._task_combo.setMinimumWidth(200)
        self._task_combo.setMinimumHeight(32)
        for key, label in AVAILABLE_TASKS.items():
            self._task_combo.addItem(label, key)
        add_layout.addWidget(self._task_combo)

        sep_lbl = QLabel("каждые")
        add_layout.addWidget(sep_lbl)

        self._interval_spin = QSpinBox()
        self._interval_spin.setRange(1, 1440)
        self._interval_spin.setValue(60)
        self._interval_spin.setMinimumHeight(32)
        add_layout.addWidget(self._interval_spin)

        self._interval_unit = GlassComboBox()
        self._interval_unit.setMinimumHeight(32)
        self._interval_unit.addItems(["минут", "часов", "дней"])
        self._interval_unit.setCurrentIndex(1)
        add_layout.addWidget(self._interval_unit)

        add_btn = GlassButton("➕ Добавить")
        add_btn.setMinimumHeight(32)
        add_btn.clicked.connect(self._add_job)
        add_layout.addWidget(add_btn)

        layout.addLayout(add_layout)

        start_btn = GlassButton("▶ Запустить планировщик")
        start_btn.clicked.connect(self._start_scheduler)
        layout.addWidget(start_btn)

        stop_btn = GlassButton("⏹ Остановить планировщик")
        stop_btn.clicked.connect(self._stop_scheduler)
        layout.addWidget(stop_btn)

        close_btn = GlassButton(I18n._("common.close"))
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignRight)

    def _load(self) -> None:
        jobs = self._scheduler.get_jobs()
        self._table.setRowCount(0)
        for j in jobs:
            row = self._table.rowCount()
            self._table.insertRow(row)
            name = j.get("name", "")
            label = AVAILABLE_TASKS.get(name, name)
            self._table.setItem(row, 0, QTableWidgetItem(label))

            mins = j.get("interval_minutes", 0)
            hrs = j.get("interval_hours", 0)
            days = j.get("interval_days", 0)
            if days:
                interval_text = f"{days} дн."
            elif hrs:
                interval_text = f"{hrs} ч."
            else:
                interval_text = f"{mins} мин."
            self._table.setItem(row, 1, QTableWidgetItem(interval_text))

            enabled = j.get("enabled", True)
            en_item = QTableWidgetItem("✅" if enabled else "❌")
            self._table.setItem(row, 2, en_item)

            last_run = self._db.get_setting(f"sched_{name}_last", "")
            self._table.setItem(
                row, 3, QTableWidgetItem(last_run[:16] if last_run else "—")
            )

            actions_w = QWidget()
            al = QHBoxLayout(actions_w)
            al.setContentsMargins(2, 0, 2, 0)
            al.setSpacing(2)

            toggle_btn = GlassButton("⏯")
            toggle_btn.setFixedSize(26, 26)
            toggle_btn.setProperty("flat", True)
            toggle_btn.clicked.connect(lambda checked, n=name: self._toggle_job(n))
            al.addWidget(toggle_btn)

            del_btn = GlassButton("✕")
            del_btn.setFixedSize(26, 26)
            del_btn.setProperty("flat", True)
            del_btn.setStyleSheet("color: #FF3B30;")
            del_btn.clicked.connect(lambda checked, n=name: self._delete_job(n))
            al.addWidget(del_btn)

            self._table.setCellWidget(row, 4, actions_w)

        self._table.resizeColumnsToContents()

    def _add_job(self) -> None:
        key = self._task_combo.currentData()
        interval_val = self._interval_spin.value()
        unit = self._interval_unit.currentText()

        kw = {"interval_minutes": 0, "interval_hours": 0, "interval_days": 0}
        if unit == "минут":
            kw["interval_minutes"] = interval_val
        elif unit == "часов":
            kw["interval_hours"] = interval_val
        else:
            kw["interval_days"] = interval_val

        cb = self._get_callback(key)
        self._scheduler.add_job(key, cb, **kw)
        self._load()
        ToastNotification.notify(
            f"Задача '{AVAILABLE_TASKS.get(key, key)}' добавлена", "success", 3000
        )

    def _delete_job(self, name: str) -> None:
        reply = QMessageBox.question(
            self,
            I18n._("common.confirm"),
            f"Удалить задачу '{AVAILABLE_TASKS.get(name, name)}'?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._scheduler.remove_job(name)
            self._load()

    def _toggle_job(self, name: str) -> None:
        raw = self._db.get_setting(f"sched_{name}", "{}")
        try:
            import json

            config = json.loads(raw) if raw else {}
        except Exception:
            config = {}
        config["enabled"] = not config.get("enabled", True)
        self._db.upsert_setting(f"sched_{name}", json.dumps(config))
        self._load()

    def _get_callback(self, key: str) -> Callable:
        callbacks = {
            "backup_auto": lambda: self._run_backup(),
            "email_report": lambda: self._run_email_report(),
            "cleanup_logs": lambda: self._run_cleanup(),
            "sync_telegram": lambda: None,
            "check_reminders": lambda: None,
        }
        return callbacks.get(key, lambda: None)

    def _run_backup(self) -> None:
        try:
            from services.database import backup_database

            path = backup_database()
            self._db.upsert_setting(
                "sched_backup_auto_last", datetime.now().isoformat()
            )
        except Exception:
            pass

    def _run_email_report(self) -> None:
        try:
            from modules.print_engine import PrintEngine

            html = PrintEngine.render_report("", True, True, True)
            from services.email_service import EmailService

            email = EmailService()
            email.send_report(html)
            self._db.upsert_setting(
                "sched_email_report_last", datetime.now().isoformat()
            )
        except Exception:
            pass

    def _run_cleanup(self) -> None:
        try:
            self._db.execute(
                "DELETE FROM audit_log WHERE timestamp < datetime('now', '-90 days')"
            )
            self._db.conn.commit()
            self._db.upsert_setting(
                "sched_cleanup_logs_last", datetime.now().isoformat()
            )
        except Exception:
            pass

    def _start_scheduler(self) -> None:
        self._scheduler.start()
        ToastNotification.notify("Планировщик запущен", "success", 3000)

    def _stop_scheduler(self) -> None:
        self._scheduler.stop()
        ToastNotification.notify("Планировщик остановлен", "info", 3000)
