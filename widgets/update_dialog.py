from typing import Any, Dict, Optional
from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QProgressBar,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from app_core.config import AppConfig
from app_core.i18n import I18n
from widgets.glass_button import GlassButton
from widgets.toast import ToastNotification


class UpdateCheckThread(QThread):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, parent: Optional[QDialog] = None) -> None:
        super().__init__(parent)
        self._checker = None

    def run(self) -> None:
        try:
            from scripts.update import UpdateChecker

            self._checker = UpdateChecker()
            result = self._checker.check_now()
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class UpdateDialog(QDialog):
    def __init__(self, parent: Optional[QDialog] = None) -> None:
        super().__init__(parent)
        self._checker = None
        self._download_url = ""
        self.setWindowTitle("Проверка обновлений")
        self.setMinimumSize(520, 380)
        self._build_ui()
        self._check()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        header = QLabel(f"<b>Текущая версия: {AppConfig.APP_VERSION}</b>")
        header.setStyleSheet("font-size: 14px;")
        layout.addWidget(header)

        self._status_label = QLabel("Проверка...")
        layout.addWidget(self._status_label)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setMaximumHeight(6)
        layout.addWidget(self._progress)

        self._release_notes = QTextEdit()
        self._release_notes.setReadOnly(True)
        self._release_notes.setPlaceholderText("Примечания к релизу...")
        layout.addWidget(self._release_notes, 1)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self._update_btn = GlassButton("Скачать и установить")
        self._update_btn.setEnabled(False)
        self._update_btn.clicked.connect(self._download_and_install)
        btn_layout.addWidget(self._update_btn)

        close_btn = GlassButton(I18n._("common.close"))
        close_btn.clicked.connect(self.reject)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

    def _check(self) -> None:
        self._status_label.setText("Проверка обновлений...")
        self._progress.setRange(0, 0)
        self._thread = UpdateCheckThread(self)
        self._thread.finished.connect(self._on_check_result)
        self._thread.error.connect(self._on_check_error)
        self._thread.start()

    def _on_check_result(self, result: Dict[str, Any]) -> None:
        self._progress.setRange(0, 100)
        self._progress.setValue(100)
        if "error" in result:
            self._status_label.setText(f"Ошибка: {result['error']}")
            return
        current = result.get("current_version", AppConfig.APP_VERSION)
        latest = result.get("latest_version", current)
        available = result.get("update_available", False)
        if available:
            self._status_label.setText(
                f'<span style="color:green;">Доступна версия {latest}</span>'
            )
            self._update_btn.setEnabled(True)
            self._download_url = result.get("download_url", "")
        else:
            self._status_label.setText(
                f'<span style="color:gray;">Установлена последняя версия ({latest})</span>'
            )
        notes = result.get("release_notes", "")
        if notes:
            self._release_notes.setPlainText(notes)
        self._checker = None

    def _on_check_error(self, error: str) -> None:
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._status_label.setText(f"Ошибка проверки: {error}")

    def _download_and_install(self) -> None:
        if not self._download_url:
            return
        self._update_btn.setEnabled(False)
        self._status_label.setText("Скачивание обновления...")
        try:
            from scripts.update import UpdateChecker

            checker = UpdateChecker()
            if checker.apply_update(self._download_url):
                ToastNotification.notify(
                    "Обновление установлено. Перезапустите приложение.", "success", 6000
                )
                self._status_label.setText(
                    "Обновление установлено. Перезапустите приложение."
                )
            else:
                ToastNotification.notify("Ошибка установки обновления.", "error", 5000)
                self._status_label.setText("Ошибка установки обновления.")
        except Exception as e:
            ToastNotification.notify(f"Ошибка: {e}", "error", 5000)
            self._status_label.setText(f"Ошибка: {e}")
