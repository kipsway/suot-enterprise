import sys, os, ctypes
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QApplication, QDialog, QMessageBox

from app_core.config import RUNTIME_PATHS, AppConfig
from app_core.i18n import I18n
from app_core.utils import JsonUtils
from app_core.theme_engine import ThemeEngine
from app_core.application import SafeApplication
from services.security import SecurityEngine
from services.database import DatabaseManager
from modules.login import LoginDialog
from modules.main_window import MainWindow
from modules.reminders import ReminderEngine


def main() -> None:
    try:
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "suot.enterprise.1.0")
        except Exception:
            pass

        app = SafeApplication(sys.argv)
        app.setApplicationName("СУОТ Enterprise")
        app.setApplicationVersion(AppConfig.APP_VERSION)
        app.setOrganizationName("SuotEnterprise")

        font = QFont("Segoe UI", 10)
        font.setStyleStrategy(QFont.PreferAntialias)
        app.setFont(font)

        app.setStyle("Fusion")

        db = DatabaseManager()
        current_theme = db.get_setting("theme", AppConfig.DEFAULT_THEME)
        current_accent = db.get_setting("accent_color", AppConfig.DEFAULT_ACCENT)
        ThemeEngine.init(app)
        ThemeEngine.apply(current_theme, current_accent)

        try:
            last_backup = db.get_setting("last_backup_date", "")
            today = datetime.now().strftime("%Y-%m-%d")
            if last_backup != today:
                db.create_backup()
                db.upsert_setting("last_backup_date", today)
        except Exception:
            pass

        _reminder_engine = ReminderEngine()

        login = LoginDialog()
        if getattr(login, '_auto_logged_in', False):
            user = login.authenticated_user()
        else:
            if login.exec_() != QDialog.Accepted:
                sys.exit(0)
            user = login.authenticated_user()
        if not user:
            sys.exit(0)

        window = MainWindow(user)
        window.show()

        sys.exit(app.exec_())
    except Exception as e:
        try:
            QMessageBox.critical(None, I18n._("common.error"),
                                 f"{I18n._('error.generic')}:\n{e}")
        except Exception:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
