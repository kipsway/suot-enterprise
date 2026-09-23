import sys, os, ctypes
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Log to file for debugging
_log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug.log")


def _log(msg: str) -> None:
    try:
        with open(_log_path, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat()} {msg}\n")
    except OSError:
        # Каталог может быть недоступен (Program Files) — лог не должен
        # блокировать запуск приложения.
        pass


_log("START")


# Fix Qt platform plugins BEFORE any PyQt5 imports
def _fix_qt_platform() -> None:
    try:
        import PyQt5

        d = os.path.dirname(PyQt5.__file__)
        plugins = os.path.join(d, "Qt5", "plugins", "platforms")
        _log(f"PyQt5 path: {d}")
        _log(f"Plugins dir exists: {os.path.isdir(plugins)}")
        if os.path.isdir(plugins):
            os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = plugins
            _log(f"Set QT_QPA_PLATFORM_PLUGIN_PATH = {plugins}")
    except Exception as e:
        _log(f"_fix_qt_platform error: {e}")


_fix_qt_platform()

_log("importing PyQt5.QtCore...")
from PyQt5.QtCore import Qt

_log("importing PyQt5.QtGui...")
from PyQt5.QtGui import QFont

_log("importing PyQt5.QtWidgets...")
from PyQt5.QtWidgets import QApplication, QDialog, QMessageBox

_log("importing app_core.config...")
from app_core.config import RUNTIME_PATHS, AppConfig

_log("importing app_core.i18n...")
from app_core.i18n import I18n

_log("importing app_core.utils...")
from app_core.utils import JsonUtils

_log("importing app_core.theme_engine...")
from app_core.theme_engine import ThemeEngine

_log("importing app_core.application...")
from app_core.application import SafeApplication

_log("importing services.security...")
from services.security import SecurityEngine

_log("importing services.database...")
from services.database import DatabaseManager

_log("importing modules.login...")
from modules.login import LoginDialog

_log("importing modules.main_window...")
from modules.main_window import MainWindow

_log("importing modules.reminders...")
from modules.reminders import ReminderEngine

_log("ALL IMPORTS OK")


def _ensure_dependencies() -> None:
    missing = []
    for mod in ("PyQt5", "openpyxl", "cryptography", "docx", "PIL"):
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        ret = QMessageBox.question(
            None,
            "СУОТ Enterprise — Установка зависимостей",
            f"Отсутствуют модули: {', '.join(missing)}.\n\n"
            "Запустить автоматическую установку?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if ret == QMessageBox.Yes:
            import subprocess

            subprocess.check_call(
                [sys.executable, "scripts/setup.py"],
                cwd=os.path.dirname(os.path.abspath(__file__)),
            )
            QMessageBox.information(
                None, "Готово", "Зависимости установлены. Перезапустите программу."
            )
        sys.exit(0)


def main() -> None:
    _log("main() started")
    try:
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "suot.enterprise.1.0"
            )
        except Exception:
            pass

        _log("Creating QApplication...")
        app = SafeApplication(sys.argv)
        _log("QApplication created")
        app.setApplicationName("СУОТ Enterprise")
        app.setApplicationVersion(AppConfig.APP_VERSION)
        app.setOrganizationName("SuotEnterprise")
        _log("app name set")

        font = QFont("Segoe UI", 10)
        font.setStyleStrategy(QFont.PreferAntialias)
        app.setFont(font)
        _log("font set")

        app.setStyle("Fusion")
        _log("style set")

        _ensure_dependencies()
        _log("deps checked")

        db = DatabaseManager()
        _log("db created")
        current_theme = db.get_setting("theme", AppConfig.DEFAULT_THEME)
        current_accent = db.get_setting("accent_color", AppConfig.DEFAULT_ACCENT)
        _log("settings read")
        ThemeEngine.init(app)
        ThemeEngine.apply(current_theme, current_accent)
        _log("theme applied")

        try:
            last_backup = db.get_setting("last_backup_date", "")
            today = datetime.now().strftime("%Y-%m-%d")
            if last_backup != today:
                _log("creating backup...")
                db.create_backup()
                db.upsert_setting("last_backup_date", today)
                _log("backup created")
        except Exception:
            _log("backup skipped/error")
            pass

        _log("creating ReminderEngine...")
        _reminder_engine = ReminderEngine()
        _log("ReminderEngine created")

        _log("creating LoginDialog...")
        login = LoginDialog()
        _log("LoginDialog created, calling exec_...")
        if getattr(login, "_auto_logged_in", False):
            _log("auto logged in")
            user = login.authenticated_user()
        else:
            _log("calling login.exec_()...")
            result = login.exec_()
            _log(f"login.exec_() returned {result}")
            if result != QDialog.Accepted:
                _log("login not accepted, exiting")
                sys.exit(0)
            user = login.authenticated_user()
        if not user:
            _log("no user, exiting")
            sys.exit(0)
        _log(f"user authenticated: {user.get('username', '?')}")

        _log("creating MainWindow...")
        window = MainWindow(user)
        _log("MainWindow created, showing...")
        window.show()
        _log("MainWindow shown, starting event loop...")

        sys.exit(app.exec_())
    except Exception as e:
        try:
            QMessageBox.critical(
                None, I18n._("common.error"), f"{I18n._('error.generic')}:\n{e}"
            )
        except Exception:
            import traceback

            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
