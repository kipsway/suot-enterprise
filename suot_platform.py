# suot_platform.py
# Occupational Safety and Health Management Platform / СУОТ Enterprise
# Part 1 of 10: Core bootstrap, database engine, security, i18n

import sys, os, re, csv, json, hmac, uuid, math, shutil, ctypes, sqlite3
import zipfile, tempfile, webbrowser, traceback, hashlib, base64, secrets
import smtplib, mimetypes, string, subprocess
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Optional, Union, Dict, List, Tuple, Any, Callable
from PyQt5.QtCore import (Qt, QObject, QThread, QThreadPool, QRunnable,
                          pyqtSignal, pyqtSlot, QPropertyAnimation,
                          QEasingCurve, QPoint, QRect, QSize, QSizeF,
                          QTimer, QSettings,
                           QParallelAnimationGroup, QSequentialAnimationGroup,
                           QEvent)
from PyQt5.QtGui import (QFont, QColor, QPainter, QPen, QBrush,
                         QLinearGradient, QConicalGradient, QFontDatabase,
                         QIcon, QPixmap, QPalette, QTransform, QPolygonF,
                         QFontMetrics, QCursor, QClipboard, QShowEvent,
                         QMouseEvent, QKeyEvent, QCloseEvent, QKeySequence,
                         QTextDocument,
                         QTextTable, QTextTableFormat, QTextLength,
                          QTextBlockFormat, QTextCharFormat, QTextFormat, QTextListFormat,
                          QSyntaxHighlighter)
from PyQt5.QtPrintSupport import QPrinter, QPrintDialog
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QDialog,
    QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout, QStackedLayout,
    QLabel, QLineEdit, QPushButton, QCheckBox, QComboBox, QTabWidget,
    QFrame, QScrollArea, QSizePolicy, QToolBar, QStatusBar, QMessageBox,
    QInputDialog, QFileDialog, QMenu, QAction, QToolButton, QButtonGroup,
    QRadioButton, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox,
    QDateEdit, QTimeEdit, QDateTimeEdit, QDialogButtonBox, QGroupBox,
    QSplitter, QSlider, QListWidget, QListWidgetItem, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QStyledItemDelegate,
     QGraphicsDropShadowEffect, QWidgetAction, QSystemTrayIcon, QTextBrowser,
      QTreeWidget, QTreeWidgetItem, QShortcut, QGraphicsOpacityEffect,
       QFontComboBox, QColorDialog, QScroller, QGraphicsScene, QGraphicsView)

# ---------------------------------------------------------------------------
# SECTION 1.0: High-DPI / Qt Plugin Path (must run before QApplication)
# ---------------------------------------------------------------------------

import os, sys
os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")
os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
os.environ.setdefault("QT_SCALE_FACTOR_ROUNDING_POLICY", "RoundPreferFloor")

try:
    from PyQt5.QtCore import QCoreApplication
    QCoreApplication.setAttribute(0x00000002, True)  # Qt.AA_EnableHighDpiScaling
    QCoreApplication.setAttribute(0x00001000, True)  # Qt.AA_UseHighDpiPixmaps
except Exception:
    pass

# Qt plugin path fix for Windows
def get_short_path(path: str) -> str:
    if sys.platform == "win32":
        try:
            buf = ctypes.create_unicode_buffer(520)
            ctypes.windll.kernel32.GetShortPathNameW(path, buf, 520)
            return buf.value if buf.value else path
        except Exception:
            return path
    return path


def normalize_plugin_path() -> None:
    if sys.platform == "win32":
        try:
            import PyQt5
            for cand in [
                os.path.join(os.path.dirname(PyQt5.__file__), "Qt5", "plugins"),
                os.path.join(os.path.dirname(PyQt5.__file__), "Qt", "plugins"),
                os.path.join(os.path.dirname(PyQt5.__file__), "plugins"),
            ]:
                if os.path.isdir(cand):
                    sp = get_short_path(os.path.abspath(cand))
                    os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = sp
                    os.environ["QT_PLUGIN_PATH"] = sp
                    break
        except Exception:
            pass


normalize_plugin_path()


# ---------------------------------------------------------------------------
# SECTION 1.2: Application Configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RuntimePaths:
    app_dir: str
    database_path: str
    backup_dir: str
    media_dir: str
    export_dir: str
    templates_dir: str


class AppConfig:
    APP_NAME = "СУОТ Enterprise"
    DB_NAME = "suot_platform.db"
    DATA_DIR = "data"
    BACKUP_DIR = "backups"
    MEDIA_DIR = "media"
    EXPORT_DIR = "exports"
    TEMPLATES_DIR = "templates"
    PBKDF2_ITERATIONS = 100_000
    TOKEN_LENGTH = 64
    TOKEN_TTL_DAYS = 30
    DEFAULT_LANG = "ru"
    DEFAULT_THEME = "light"
    DEFAULT_ACCENT = "#2196F3"
    AUTO_SAVE_INTERVAL = 300
    REMINDER_CHECK_INTERVAL = 60
    APP_VERSION = "2.0.0"


class PathManager:
    @staticmethod
    def create() -> RuntimePaths:
        ad = os.path.abspath(os.path.dirname(__file__ if "__file__" in dir() else "."))
        for d in [AppConfig.BACKUP_DIR, AppConfig.MEDIA_DIR,
                  AppConfig.EXPORT_DIR, AppConfig.TEMPLATES_DIR]:
            os.makedirs(os.path.join(ad, d), exist_ok=True)
        return RuntimePaths(
            app_dir=get_short_path(ad),
            database_path=get_short_path(os.path.join(ad, AppConfig.DB_NAME)),
            backup_dir=get_short_path(os.path.join(ad, AppConfig.BACKUP_DIR)),
            media_dir=get_short_path(os.path.join(ad, AppConfig.MEDIA_DIR)),
            export_dir=get_short_path(os.path.join(ad, AppConfig.EXPORT_DIR)),
            templates_dir=get_short_path(os.path.join(ad, AppConfig.TEMPLATES_DIR)),
        )


RUNTIME_PATHS = PathManager.create()



def parse_date_flexible(date_str: Any) -> Optional[datetime]:
    if not date_str or str(date_str).strip() in ('', '—', 'None'):
        return None
    s = str(date_str).split(' (')[0].replace('.', '-').replace('/', '-').strip()
    parts = s.split('-')
    try:
        if len(parts) == 3:
            if len(parts[0]) == 2 and len(parts[2]) == 4:
                return datetime(int(parts[2]), int(parts[1]), int(parts[0]))
            if len(parts[0]) == 4 and len(parts[2]) == 2:
                return datetime(int(parts[0]), int(parts[1]), int(parts[2]))
    except ValueError:
        return None
    return None


def get_valid_until_bg(date_str: Any, is_dark: bool) -> Optional[QColor]:
    dt = parse_date_flexible(date_str)
    if not dt:
        return None
    today = datetime.now()
    if dt < today:
        return QColor('#582525' if is_dark else '#f8d7da')
    if dt <= today + timedelta(days=30):
        return QColor('#614d17' if is_dark else '#fff3cd')
    return QColor('#254b32' if is_dark else '#d4edda')


def get_date_indicator_bg(date_str: Any, is_dark: bool, date_mode: str = 'Действует до') -> Optional[QColor]:
    dt = parse_date_flexible(date_str)
    if not dt:
        return None
    if date_mode == 'Дата проведения':
        dt = dt + timedelta(days=365)
    today = datetime.now()
    if dt < today:
        return QColor('#582525' if is_dark else '#f8d7da')
    if dt <= today + timedelta(days=30):
        return QColor('#614d17' if is_dark else '#fff3cd')
    return QColor('#254b32' if is_dark else '#d4edda')


def get_status_indicator_bg(status_str: Any, is_dark: bool) -> Optional[QColor]:
    status = str(status_str).strip()
    if status in ('Устранено', 'Исполнено', 'Resolved', 'Соответствует'):
        return QColor('#254b32' if is_dark else '#d4edda')
    if status in ('Активно', 'Активен', 'Active'):
        return QColor('#614d17' if is_dark else '#fff3cd')
    if status in ('Просрочено', 'Expired'):
        return QColor('#582525' if is_dark else '#f8d7da')
    if status in ('Архив', 'Уволен'):
        return QColor('#313244' if is_dark else '#f1f3f5')
    return None


def fade_in_widget(widget: QWidget, duration: int = 300) -> None:
    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    anim = QPropertyAnimation(effect, b"opacity")
    anim.setDuration(duration)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.OutCubic)
    anim.start(QPropertyAnimation.DeleteWhenStopped)


def wrap_table_with_glow(table: QTableWidget, parent: QWidget) -> QFrame:
    QScroller.grabGesture(table, QScroller.LeftMouseButtonGesture)
    container = QFrame(parent)
    container.setObjectName("tableGlowContainer")
    is_dark = ThemeEngine._current_theme == "dark"
    if is_dark:
        glow = """
            QFrame#tableGlowContainer {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(255,255,255,0.04), stop:0.3 transparent, stop:0.7 transparent, stop:1 rgba(255,255,255,0.04));
                border-radius: 14px;
                border: 1px solid rgba(255,255,255,0.04);
            }
        """
    else:
        glow = """
            QFrame#tableGlowContainer {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(0,0,0,0.03), stop:0.3 transparent, stop:0.7 transparent, stop:1 rgba(0,0,0,0.03));
                border-radius: 14px;
                border: 1px solid rgba(0,0,0,0.03);
            }
        """
    container.setStyleSheet(glow)
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(table)
    return container


ACCENT_COLORS = {
    "blue": "#2196F3",
    "teal": "#00BCD4",
    "green": "#4CAF50",
    "purple": "#9C27B0",
    "orange": "#FF9800",
    "red": "#F44336",
    "pink": "#E91E63",
    "cyan": "#00BCD4",
    "grey": "#607D8B",
    "amber": "#FFC107",
}


# ---------------------------------------------------------------------------
# SECTION 1.3: JSON Utilities
# ---------------------------------------------------------------------------

class JsonUtils:
    @staticmethod
    def dumps(data: Any) -> str:
        try:
            return json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        except Exception:
            return "{}"

    @staticmethod
    def loads(text: str) -> Dict[str, Any]:
        try:
            if not text:
                return {}
            r = json.loads(text)
            return r if isinstance(r, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def pretty(data: Any) -> str:
        try:
            return json.dumps(data, ensure_ascii=False, indent=2, default=str)
        except Exception:
            return "{}"


# ---------------------------------------------------------------------------
# SECTION 1.4: Security Engine (PBKDF2-HMAC-SHA256)
# ---------------------------------------------------------------------------

class SecurityEngine:
    @staticmethod
    def generate_hash(password: str, salt: Optional[bytes] = None) -> Tuple[str, str]:
        safe_salt = salt if salt is not None else os.urandom(32)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                 safe_salt, AppConfig.PBKDF2_ITERATIONS)
        return dk.hex(), safe_salt.hex()

    @staticmethod
    def verify(stored_hash: str, salt_hex: str, provided: str) -> bool:
        try:
            salt = bytes.fromhex(salt_hex)
            h, _ = SecurityEngine.generate_hash(provided, salt)
            return hmac.compare_digest(stored_hash, h)
        except Exception:
            return False

    @staticmethod
    def create_token(length: int = AppConfig.TOKEN_LENGTH) -> str:
        return secrets.token_hex(max(32, length) // 2)

    @staticmethod
    def valid_password(password: str) -> bool:
        return isinstance(password, str) and len(password) >= 6


# ---------------------------------------------------------------------------
# SECTION 1.5: Session Manager (Remember Me)
# ---------------------------------------------------------------------------

class SessionManager:
    def __init__(self, db: "DatabaseManager") -> None:
        self.db = db

    def save_remember_me(self, username: str, token: str, expiry: datetime) -> None:
        try:
            self.db.execute("UPDATE users SET session_token=?, token_expiry=? WHERE username=?",
                            (token, expiry.isoformat(), username))
            self.db.upsert_setting("remember_me_token", token)
            self.db.upsert_setting("remember_me_expiry", expiry.isoformat())
            self.db.log_event("Remember Me session activated", "INFO")
            self.db.commit()
        except Exception:
            self.db.rollback()
            self.db.log_event(f"Remember Me failed: {traceback.format_exc()}", "CRITICAL")

    def clear_remember_me(self) -> None:
        try:
            self.db.execute("UPDATE users SET session_token=NULL, token_expiry=NULL")
            self.db.upsert_setting("remember_me_token", "")
            self.db.upsert_setting("remember_me_expiry", "")
            self.db.log_event("Remember Me session cleared", "INFO")
            self.db.commit()
        except Exception:
            self.db.rollback()
            self.db.log_event(f"Clear session failed: {traceback.format_exc()}", "CRITICAL")

    def validate_remember_me(self) -> Optional[Dict[str, Any]]:
        try:
            token = self.db.get_setting("remember_me_token", "")
            if not token:
                return None
            row = self.db.fetch_one(
                "SELECT id,username,password_hash,salt,role,session_token,token_expiry "
                "FROM users WHERE session_token=?", (token,))
            if not row:
                self.clear_remember_me()
                return None
            try:
                expiry = datetime.fromisoformat(row.get("token_expiry") or "")
            except Exception:
                self.clear_remember_me()
                return None
            if datetime.now() > expiry:
                self.clear_remember_me()
                return None
            self.db.log_event(f"Remember Me auto-login for {row.get('username')}", "INFO")
            return row
        except Exception:
            self.db.log_event(f"Remember Me validation error: {traceback.format_exc()}", "CRITICAL")
            return None


# ---------------------------------------------------------------------------
# SECTION 1.6: Internationalisation (RU / EN)
# ---------------------------------------------------------------------------

class I18n:
    _current = AppConfig.DEFAULT_LANG

    _ru: Dict[str, str] = {
        "app.name": "СУОТ Enterprise",
        "app.version": "Версия",
        "app.copyright": "© 2024 СУОТ Enterprise",

        "login.title": "Авторизация — СУОТ Enterprise",
        "login.username": "Имя пользователя",
        "login.password": "Пароль",
        "login.remember": "Запомнить меня",
        "login.btn": "Войти",
        "login.error.empty": "Заполните все поля",
        "login.error.invalid": "Неверное имя пользователя или пароль",
        "login.error.locked": "Учётная запись заблокирована",
        "login.success": "Вход выполнен успешно",
        "login.logout": "Выйти из системы",
        "login.no_session": "Сессия не найдена",

        "common.ok": "OK",
        "common.cancel": "Отмена",
        "common.save": "Сохранить",
        "common.rename": "Переименовать",
        "common.save_as": "Сохранить как",
        "common.delete": "Удалить",
        "common.yes": "Да",
        "common.no": "Нет",
        "dashboard.recent": "Последние действия",
        "dashboard.no_activity": "Нет активности",
        "common.close": "Закрыть",
        "common.global_search": "🔍 Глобальный поиск…",
        "common.copy": "Копировать",
        "common.apply": "Применить",
        "common.reset": "Сбросить",
        "common.search_hint": "Поиск…",
        "common.add": "Добавить",
        "common.edit": "Изменить",
        "common.remove": "Убрать",
        "common.search": "Поиск",
        "common.find": "Найти",
        "common.size": "Размер",
        "common.filter": "Фильтр",
        "common.clear": "Очистить",
        "common.export": "Экспорт",
        "common.import_": "Импорт",
        "common.print": "Печать",
        "common.settings": "Настройки",
        "common.help": "Помощь",
        "common.about": "О программе",
        "common.system": "Система",
        "common.no_selection": "Ничего не выбрано",
        "common.confirm": "Подтверждение",
        "common.warning": "Предупреждение",
        "common.error": "Ошибка",
        "common.info": "Информация",
        "common.success": "Успешно",
        "common.loading": "Загрузка...",
        "common.processing": "Обработка...",
        "common.done": "Готово",
        "common.more": "Ещё",
        "common.backup": "Резервная копия",
        "common.restore": "Восстановить",
        "common.refresh": "Обновить",
        "common.select_all": "Выбрать всё",
        "common.deselect_all": "Снять выделение",
        "common.name": "Название",
        "common.date": "Дата",
        "common.description": "Описание",
        "common.status": "Статус",
        "common.actions": "Действия",
        "common.cut": "Вырезать",
        "common.paste": "Вставить",
        "common.undo": "Отменить",
        "common.redo": "Повторить",
        "common.no_data": "Нет данных",
        "common.field": "Поле",
        "common.value": "Значение",
        "common.notes": "Заметки",
        "common.notes_hint": "Введите текст заметки...",
        "common.saved": "Сохранено",
        "common.reminders": "Напоминания",
        "common.templates": "Шаблоны",
        "common.report": "Отчёт",
        "common.preview": "Предпросмотр",
        "common.table": "Таблица",
        "common.format": "Формат",
        "common.count": "Количество",
        "common.rename": "Переименовать",
        "common.currency": "руб",
        "common.align_left": "По левому краю",
        "common.align_center": "По центру",
        "common.align_right": "По правому краю",
        "common.paragraph": "Абзац",
        "common.zoom_in": "Приблизить",
        "common.zoom_out": "Отдалить",
        "common.reset_zoom": "Сбросить масштаб (100%)",
        "common.fullscreen": "На весь экран",

        "tab.dashboard": "KPI-панель",
        "tab.employees": "Сотрудники",
        "tab.violations": "Нарушения",
        "tab.companies": "Контрагенты",
        "tab.custom_ledger": "Произвольный",
        "tab.statistics": "Статистика",
        "tab.audit": "Аудит",
        "tab.ai": "ИИ-ассистент",
        "tab.reminders": "Напоминания",

        "emp.id": "ID",
        "emp.fio": "ФИО",
        "emp.position": "Должность",
        "emp.department": "Подразделение",
        "emp.company": "Фирма",
        "emp.phone": "Телефон",
        "emp.medical_date": "Дата медосмотра",
        "emp.qualification": "Квалификация",
        "emp.date_conducted": "Дата проведения",
        "emp.photo": "Фото",
        "emp.status": "Статус",
        "emp.add": "Добавить сотрудника",
        "emp.edit": "Редактировать сотрудника",
        "emp.delete": "Удалить сотрудника",
        "emp.delete_confirm": "Вы уверены, что хотите удалить {count} сотрудника(ов)?",
        "emp.import": "Импорт сотрудников",
        "emp.export": "Экспорт сотрудников",
        "emp.duplicate_found": "Сотрудник уже существует. Обновить существующую запись?",
        "emp.duplicate_updated": "Данные существующего сотрудника обновлены",

        "viol.id": "ID",
        "viol.date": "Дата",
        "viol.company": "Фирма",
        "viol.department": "Подразделение",
        "viol.risk_category": "Категория риска",
        "viol.description": "Описание",
        "viol.responsible": "Ответственный",
        "viol.deadline": "Срок устранения",
        "viol.fine": "Штраф",
        "viol.status": "Статус",
        "viol.photo": "Фото",
        "viol.types": "Типы нарушений",
        "viol.type_name": "Наименование",
        "viol.add": "Добавить нарушение",
        "viol.edit": "Редактировать нарушение",
        "viol.delete": "Удалить нарушение",
        "viol.delete_confirm": "Вы уверены, что хотите удалить нарушение?",
        "viol.import": "Импорт нарушений",
        "viol.export": "Экспорт нарушений",
        "viol.use_template": "Использовать шаблон",
        "viol.create_reminder": "Создать напоминание",
        "viol.duplicate_found": "Нарушение для этой фирмы с таким описанием уже существует. Обновить существующую запись?",
        "viol.duplicate_updated": "Существующее нарушение обновлено",

        "company.id": "ID",
        "company.name": "Название",
        "company.address": "Адрес",
        "company.contact": "Контакт",
        "company.employees_count": "Сотрудников",
        "company.violations_count": "Нарушений",
        "company.fines_total": "Сумма штрафов",
        "company.add": "Добавить фирму",
        "company.edit": "Редактировать фирму",
        "company.delete": "Удалить фирму",

        "ledger.id": "ID",
        "ledger.date": "Дата",
        "ledger.category": "Категория",
        "ledger.description": "Описание",
        "ledger.responsible": "Ответственный",
        "ledger.status": "Статус",
        "ledger.photo": "Фото",
        "ledger.note": "Примечание",
        "ledger.add": "Добавить запись",
        "ledger.edit": "Редактировать запись",
        "ledger.delete": "Удалить запись",
        "ledger.delete_confirm": "Вы уверены, что хотите удалить запись?",

        "column.rename": "Переименовать колонку",
        "column.name_empty": "Название не может быть пустым",
        "column.add": "Добавить колонку",
        "column.delete": "Удалить колонку",
        "column.change_type": "Изменить тип",
        "column.rename_prompt": "Введите новое название колонки:",
        "column.add_prompt": "Введите название новой колонки:",
        "column.duplicate_error": "Колонка с таким именем уже существует",
        "column.type_text": "Текст",
        "column.type_number": "Число",
        "column.type_date": "Годен до",
        "column.type_date_conducted": "Дата проведения",
        "column.type_status": "Статус",
        "column.type_media": "Медиа",

        "search.placeholder": "Поиск по таблице...",
        "search.global": "Глобальный поиск",
        "search.global_placeholder": "Поиск по всей программе...",
        "search.regex": "Рег. выражение",
        "search.no_results": "Ничего не найдено",

        "status.compliant": "Соответствует",
        "status.expiring": "Истекает срок",
        "status.overdue": "Просрочено",
        "status.archived": "Архивная",
        "status.active": "Активно",
        "status.resolved": "Исполнено",

        "date.format_hint": "Формат: ДД.ММ.ГГГГ (авто-замена из MM-DD-YYYY)",
        "date.overdue": "Просрочено на {days} дн.",
        "date.expiring": "Истекает через {days} дн.",
        "date.ok": "В норме",
        "date.conducted_marker": "Дата проведения (архив)",

        "notes.title": "Заметки",
        "notes.global": "Общие заметки",
        "notes.entity": "Заметки записи",
        "notes.add": "Добавить заметку",
        "notes.delete": "Удалить заметку",
        "notes.placeholder": "Введите текст заметки...",

        "reminder.title": "Напоминания",
        "reminder.add": "Добавить напоминание",
        "reminder.edit": "Редактировать напоминание",
        "reminder.delete": "Удалить напоминание",
        "reminder.title_field": "Заголовок",
        "reminder.description": "Описание",
        "reminder.due_date": "Дата напоминания",
        "reminder.interval": "Интервал проверки (сек.)",
        "reminder.is_done": "Выполнено",
        "reminder.no_items": "Нет напоминаний",
        "reminder.notification": "Напоминание: {title}",
        "reminder.all": "Все напоминания",
        "reminder.overdue_section": "Просроченные напоминания",
        "reminder.upcoming_section": "Ближайшие напоминания",
        "reminder.overdue_only": "Только просроченные",
        "reminder.quick_all": "Все",
        "reminder.quick_overdue": "Просроченные",
        "reminder.quick_3days": "На 3 дня",
        "reminder.quick_30days": "На 30 дней",
        "reminder.sort_order": "Сортировка",
        "reminder.sort_priority": "Сначала просроченные",
        "reminder.sort_due_asc": "По ближайшему сроку",
        "reminder.sort_due_desc": "По дальнему сроку",
        "reminder.type": "Тип",
        "reminder.entity": "Объект",
        "reminder.days_left": "Осталось дней",
        "reminder.expiring_hint": "Срок действия следующих позиций истекает в ближайшие 30 дней.",
        "reminder.overdue": "Просрочено на {days} дн.",
        "reminder.today": "Сегодня",
        "reminder.days_format": "{days} дн.",
        "reminder.startup_popup": "У вас {count} истекающих позиций. Открыть напоминания?",

        "print.title": "Печать бланка",
        "print.template": "Шаблон печати",
        "print.order": "Предписание",
        "print.report": "Отчёт",
        "print.edit_template": "Редактировать шаблон",
        "print.preview": "Предпросмотр",
        "print.open_browser": "Открыть в браузере",
        "print.generated": "Документ сформирован",
        "print.portrait": "Книжная",
        "print.landscape": "Альбомная",
        "print.orientation": "Ориентация",
        "print.without_template": "Без шаблона",
        "print.any_table": "Печать",

        "settings.title": "Настройки системы",
        "settings.language": "Язык интерфейса",
        "settings.theme": "Тема оформления",
        "settings.accent_color": "Цвет акцента",
        "settings.light": "Светлая",
        "settings.dark": "Тёмная",
        "settings.auto_save": "Авто-сохранение (сек.)",
        "settings.reminder_interval": "Интервал напоминаний (сек.)",
        "settings.media_path": "Папка для медиа",
        "settings.saved": "Настройки сохранены",

        "user.title": "Управление пользователями",
        "user.add": "Добавить пользователя",
        "user.delete": "Удалить пользователя",
        "user.change_password": "Сменить пароль",
        "user.change_role": "Изменить роль",
        "user.username": "Имя пользователя",
        "user.password": "Пароль",
        "user.role": "Роль",
        "user.role_admin": "Администратор",
        "user.role_inspector": "Инспектор",
        "user.role_manager": "Менеджер",
        "user.delete_confirm": "Удалить пользователя {username}?",
        "user.password_change_title": "Смена пароля",

        "stat.title": "Статистика",
        "stat.employees_total": "Всего сотрудников",
        "stat.violations_total": "Всего нарушений",
        "stat.companies_total": "Всего фирм",
        "stat.overdue_total": "Просрочено",
        "stat.fines_total": "Сумма штрафов",
        "stat.safety_score": "Индекс безопасности",
        "stat.by_company": "По фирмам",
        "stat.by_category": "По категориям",
        "stat.by_status": "По статусам",
        "stat.status_distribution": "Распределение по статусам",
        "stat.overdue_trend": "Просроченные нарушения",

        "audit.title": "Хронология аудита",
        "audit.timestamp": "Время",
        "audit.event": "Событие",
        "audit.severity": "Уровень",
        "audit.details": "Детали",
        "audit.info": "Информация",
        "audit.warning": "Предупреждение",
        "audit.critical": "Критично",
        "audit.filter_severity": "Фильтр по уровню",

        "backup.title": "Резервные копии",
        "backup.create": "Создать копию",
        "backup.restore": "Восстановить",
        "backup.delete": "Удалить копию",
        "backup.created_at": "Создана",
        "backup.size": "Размер",
        "backup.sha256": "Контр. сумма",
        "backup.restore_confirm": "Восстановить базу из копии от {date}?",
        "backup.restore_warning": "Все текущие данные будут заменены!",
        "backup.success": "Резервная копия создана",
        "backup.restore_success": "База восстановлена из копии",

        "ai.title": "ИИ-ассистент",
        "ai.api_url": "API URL",
        "ai.api_key": "API Ключ",
        "ai.model": "Модель",
        "ai.mode": "Режим",
        "ai.mode_chat": "Чат",
        "ai.mode_search": "Поиск",
        "ai.mode_agent": "Агент",
        "ai.send": "Отправить",
        "ai.clear": "Очистить",
        "ai.attach_tooltip": "Прикрепить файл или фото",
        "ai.attach_file": "Выберите файл",
        "ai.attach_filter": "Все файлы (*);;Изображения (*.png *.jpg *.jpeg *.gif *.bmp);;Документы (*.pdf *.doc *.docx *.txt);;Текстовые файлы (*.txt)",
        "ai.placeholder": "Введите сообщение...",
        "ai.thinking": "ИИ печатает...",
        "ai.error": "Ошибка ИИ: {error}",
        "ai.no_key": "Укажите API ключ в настройках",
        "ai.confirm_action": "ИИ хочет выполнить действие: {action}\nРазрешить?",
        "ai.action_executed": "Действие выполнено: {action}",
        "ai.action_cancelled": "Действие отклонено",
        "ai.provider": "Провайдер",
        "ai.temperature": "Температура",
        "ai.system_prompt": "Ты — ИИ-ассистент системы управления охраной труда. "
                            "У тебя есть доступ к базе данных. Ты можешь искать, анализировать "
                            "и изменять данные (с подтверждением пользователя).",

        "report.title": "Общий отчёт",
        "report.company": "Отчёт по фирме",
        "report.all_companies": "По всем фирмам",
        "report.include": "Включить в отчёт:",
        "report.employees": "Сотрудники",
        "report.violations": "Нарушения",
        "report.fines": "Штрафы",
        "report.summary": "Сводка",
        "report.no_data": "Нет данных для отчёта",
        "report.generated": "Отчёт сформирован",

        "import.title": "Импорт данных",
        "import.file": "Файл",
        "import.select": "Выберите файл",
        "import.execute": "Импорт",
        "import.success": "Импортировано {count} записей",
        "import.log_title": "Результаты импорта",
        "import.updated": "Обновлено",
        "import.save_log": "Сохранить лог",
        "import.skip": "Пропустить",

        "template.title": "Шаблоны печати",

        "help.title": "Справка",
        "help.shortcuts": "Горячие клавиши",
        "help.features": "Возможности программы",
        "help.version": "Версия",
        "help.nav_table": "Навигация по строкам таблицы",
        "help.search": "Поиск (фокус в строку поиска)",
        "help.save": "Сохранить текущую запись",
        "help.print": "Печать",
        "help.export": "Экспорт выделенной записи",
        "help.add_record": "Добавить новую запись",
        "help.delete": "Удалить выделенное",
        "help.edit": "Редактировать запись",
        "help.click_column": "Клик по заголовку столбца",
        "help.sort": "Сортировка по столбцу",
        "help.right_click_column": "Правый клик по заголовку столбца",
        "help.column_menu": "Меню: переименовать/добавить/удалить столбец",
        "help.right_click_row": "Правый клик по строке",
        "help.row_menu": "Контекстное меню строки",
        "help.feat_multi_user": "Многопользовательский режим с разграничением доступа",
        "help.feat_ai_assistant": "AI-ассистент с поддержкой нескольких провайдеров",
        "help.feat_import_export": "Импорт из Excel и экспорт в CSV",
        "help.feat_print_templates": "Гибкие шаблоны печати",
        "help.feat_photo": "Прикрепление фотографий к сотрудникам и предписаниям",
        "help.feat_notes": "Заметки к любой записи",
        "help.feat_color_indicators": "Цветовая индикация сроков и статусов",
        "help.feat_reports": "Генерация отчётов (Word, Excel, HTML)",
        "help.feat_auto_save": "Автоматическое резервное копирование",
        "help.feat_custom_columns": "Настраиваемые столбцы в журналах",
        "help.toolbar": "Панель инструментов",
        "help.toolbar_desc": "Кнопки на верхней панели: переключение темы/языка, пользователь, импорт/экспорт, печать, AI-чат, заметки, аналитика, учебник, расчёт рисков, резервное копирование, отчёт, экспорт лога, диагностика AI, база знаний",
        "help.tabs": "Вкладки",
        "help.tabs_desc": "Дашборд (статистика) → Сотрудники → Предписания → Компании → Журнал → Статистика → Аудит → Напоминания → AI-чат",
        "help.tables": "Работа с таблицами",
        "help.tables_desc": "Поиск по тексту и рег.выражениям, сортировка кликом по заголовку, авто-подгонка ширины двойным кликом по заголовку, перетаскивание колонок, контекстное меню строки (копировать/редактировать/удалить/печать), контекстное меню заголовка (переименовать/добавить/удалить/тип колонки)",
        "help.import": "Импорт данных",
        "help.import_desc": "Поддерживаются CSV и Excel (.xlsx). При импорте можно сопоставить колонки источника с полями программы. Автоматическое обнаружение дубликатов и объединение.",
        "help.export_desc": "Экспорт выделенных строк в CSV или Excel (.xlsx). Выберите строки и нажмите кнопку экспорта.",
        "help.ai": "AI-ассистент",
        "help.ai_desc": "Поддерживает OpenAI, OpenRouter, DeepSeek, Anthropic Claude, Google Gemini, Groq, локальные Ollama/LM Studio. Режимы: чат (свободное общение), поиск (поиск по БД), агент (выполнение действий: создание/изменение записей, отчёты).",
        "help.print_templates": "Шаблоны печати",
        "help.print_templates_desc": "Редактор шаблонов с WYSIWYG: выбор шрифта, размера, цвета, жирный/курсив/подчёркнутый, выравнивание, вставка переменных полей из дерева. Предпросмотр перед печатью.",
        "help.analytics": "Аналитика",
        "help.analytics_desc": "По компаниям: количество нарушений, штрафы, сотрудники. По категориям риска: распределение нарушений, процент устранения.",
        "help.reminders": "Напоминания",
        "help.reminders_desc": "Автоматическая проверка просроченных напоминаний при запуске. Фильтры: все/просроченные/3 дня/30 дней. Сортировка по приоритету или дате. Экспорт в CSV/Excel.",
        "help.security": "Безопасность",
        "help.security_desc": "Вход по паролю (PBKDF2-SHA256), роли (Администратор/Пользователь), журнал аудита всех действий, резервное копирование с проверкой целостности.",
        "help.tips": "Советы и фишки",
        "help.tips_list": "• Двойной клик по заголовку столбца — авто-подгонка ширины\n• Правый клик по ячейке — копировать значение\n• Ctrl+F — фокус в строку поиска\n• Ctrl+N — добавить запись\n• Ctrl+E — экспорт\n• Ctrl+P — печать\n• Delete — удалить\n• Перетаскивание колонок — смена порядка\n• Двойной клик по вкладке — переименовать\n• Глобальный поиск (строка сверху) — поиск по всем таблицам + заметкам\n• AI-агент может создавать и изменять записи голосом/текстом\n• Учебник автозамены — сокращайте часто вводимые фразы",
        "help.global_search": "Глобальный поиск",
        "help.global_search_desc": "Ищет по сотрудникам, предписаниям, компаниям, журналу и заметкам. Результаты отображаются в виде дерева; двойной клик переходит к записи.",
        "help.dashboard": "Дашборд",
        "help.dashboard_desc": "Отображает общую статистику: количество сотрудников, предписаний, компаний, просроченных напоминаний, общую сумму штрафов. График безопасности (Safety Score). Лента последних действий.",
        "help.notes": "Заметки",
        "help.notes_desc": "К каждой записи можно добавить заметку (богатый текст HTML). Также доступны глобальные заметки. Поиск по всем заметкам.",
        "help.photos": "Фотографии",
        "help.photos_desc": "К сотрудникам и предписаниям можно прикреплять фотографии. Поддерживается drag-and-drop, просмотр в галерее, увеличение/панорамирование.",
        "help.reports": "Отчёты",
        "help.reports_desc": "Глобальный отчёт по всем компаниям (сводка + активные предписания) в формате HTML или DOC. Экспорт лога аудита в LOG-файл.",
        "help.backup": "Резервное копирование",
        "help.backup_desc": "Автоматический бекап при первом запуске за день. Ручное создание и восстановление из ZIP-архивов с проверкой SHA-256.",
        "help.settings": "Настройки",
        "help.settings_desc": "Вкладки: Общие (язык, тема, акцентный цвет), Система (интервал автосохранения, проверка напоминаний, директория медиа), Настройка (подписи кнопок панели инструментов).",
        "help.textbook": "Учебник автозамены",
        "help.textbook_desc": "Набор правил вида 'код → текст'. При вводе кода и нажатии пробела/Enter код автоматически заменяется на полный текст. Удобно для часто вводимых фраз по охране труда.",
        "help.risk_calc": "Калькулятор рисков (Fine-Kinney)",
        "help.risk_calc_desc": "Оценка риска по методике Fine-Kinney: вероятность, экспозиция, последствия. Автоматический расчёт итогового балла и уровня риска (зелёный/жёлтый/красный).",
        "help.column_customization": "Настройка колонок",
        "help.column_customization_desc": "В каждой таблице можно: переименовать колонку, добавить новую (с выбором типа: текст/дата/число/список/фото/логика), удалить, изменить порядок перетаскиванием.",
        "help.color_indicators": "Цветовая индикация",
        "help.color_indicators_desc": "Статусы подсвечиваются цветом: зелёный (активно/выполнено), жёлтый (предупреждение/скоро истекает), красный (просрочено/критично), серый (неактивно).",
        "help.knowledge_base": "База знаний AI",
        "help.knowledge_base_desc": "Текстовый файл с дополнительной информацией, которую AI использует при ответах. Можно редактировать встроенным редактором.",
        "help.autosave": "Автосохранение",
        "help.autosave_desc": "Периодическое автосохранение изменений (интервал настраивается в Настройках → Система).",
        "help.duplicate_merge": "Обнаружение дубликатов",
        "help.duplicate_merge_desc": "При добавлении записи система проверяет возможные дубликаты по ФИО/названию и предлагает объединить или пропустить.",
        "help.hotkey_manager": "Менеджер горячих клавиш",
        "help.hotkey_manager_desc": "Ctrl+N (добавить), Ctrl+E (экспорт), Ctrl+P (печать), Ctrl+S (сохранить), Ctrl+F (поиск), Delete (удалить).",

        "import.preview": "Предпросмотр",
        "import.column_map": "Соответствие колонок",
        "import.source": "Источник",
        "import.destination": "Цель",
        "import.error": "Ошибка импорта: {error}",

        "export.title": "Экспорт данных",
        "export.csv": "CSV",
        "export.excel": "Excel (.xlsx)",
        "export.success": "Экспорт завершён: {path}",
        "export.error": "Ошибка экспорта: {error}",

        "sort.asc": "по возрастанию",
        "sort.desc": "по убыванию",
        "sort.none": "без сортировки",

        "filter.all": "Все",
        "filter.company": "Фирма: {name}",
        "filter.status": "Статус: {status}",
        "filter.date_from": "Дата с",
        "filter.date_to": "Дата по",

        "toast.reminder": "Напоминание",
        "toast.backup": "Резервное копирование",
        "toast.error": "Ошибка",
        "toast.save_success": "Сохранено",
        "toast.delete_success": "Удалено",
        "toast.backup_created": "Резервная копия создана",
        "emp.backup_before_delete": "Создать резервную копию перед удалением?",

        "hotkeys.title": "Горячие клавиши",
        "hotkeys.save": "Ctrl+S — Сохранить",
        "hotkeys.search": "Ctrl+F — Поиск",
        "hotkeys.new": "Ctrl+N — Новая запись",
        "hotkeys.delete": "Del — Удалить",
        "hotkeys.autoreplace": "Ctrl+Shift+A — Автозамена",
        "hotkeys.refresh": "F5 — Обновить",
        "hotkeys.fullscreen": "F11 — Полный экран",
        "hotkeys.undo": "Ctrl+Z — Отменить",
        "hotkeys.redo": "Ctrl+Y — Повторить",

        "datetime.now": "сейчас",
        "datetime.minutes_ago": "{n} мин. назад",
        "datetime.hours_ago": "{n} ч. назад",
        "datetime.days_ago": "{n} дн. назад",
        "datetime.today": "Сегодня",
        "datetime.yesterday": "Вчера",

        "error.generic": "Произошла ошибка",
        "error.db_locked": "База данных заблокирована",
        "error.no_permission": "Недостаточно прав",
        "error.not_found": "Запись не найдена",
        "error.invalid_data": "Некорректные данные",
        "error.file_not_found": "Файл не найден",
        "error.import_failed": "Ошибка импорта файла",

        "textbook.auto_replace": "Автозамена (Textbook)",
        "textbook.edit": "Редактор автозамен",
        "textbook.shortcode": "Код",
        "textbook.fulltext": "Полный текст",
        "textbook.add": "Добавить правило",
        "textbook.delete": "Удалить правило",
        "textbook.enable_auto": "Авто-замена при вводе",
        "textbook.trigger_hint": "Наберите код и нажмите Пробел или Enter",

        "template.edit": "Редактор шаблонов",
        "template.name": "Название шаблона",
        "template.html": "HTML шаблон",
        "template.css": "CSS стили",
        "template.preview": "Предпросмотр",
        "template.choose": "Выберите шаблон печати:",
        "template.save": "Сохранить шаблон",
        "template.reset": "Сбросить на стандартный",
        "template.delete_confirm": "Удалить шаблон?",
        "template.variables": "Доступные переменные: {name}, {date}, {company}, {description}, {responsible}, {deadline}, {fine}, {photos}",
        "template.insert_variable": "Вставить переменную",
        "template.insert_table": "Вставить таблицу",
        "template.table_rows": "Количество строк:",
        "template.table_columns": "Количество столбцов:",
        "template.fit_page": "Подогнать лист",
        "template.copy_html": "Копировать HTML",
        "template.available_fields": "Доступные поля",
        "template.variables_group": "Поля шаблона",
        "template.empty_hint": "Начните редактирование шаблона — предпросмотр появится автоматически",
        "template.preview_error": "Ошибка предпросмотра",
        "template.select": "Выбрать шаблон",
        "template.untitled": "Без названия",
        "template.heading1": "Заголовок 1",
        "template.heading2": "Заголовок 2",
        "template.heading3": "Заголовок 3",
        "template.chars": "симв.",
        "template.words": "слов",
        "template.word_wrap": "Перенос",
        "template.match_case": "С учётом регистра",
        "template.record_number": "№ записи",
        "template.violation_number": "№ нарушения",
        "template.multi_record_hint": "При выборе нескольких предписаний, переменные выше повторяются для каждого",
        "template.multi_record_hint2": "эти поля автоматически подставляются из каждого выбранного предписания",
        "template.fit_width": "По ширине",
        "template.page_break": "Разрыв страницы",
        "template.insert_date": "Вставить дату",
        "template.page_settings": "Поля страницы",
        "template.margin_left": "Слева",
        "template.margin_right": "Справа",
        "template.margin_top": "Сверху",
        "template.margin_bottom": "Снизу",
        "template.repeat_group": "Повтор для каждого предписания",
        "template.repeat_group_hint": "Всё между метками ниже будет повторяться для 1, 2, 3 и следующих предписаний",
        "template.repeat_start": "Начать блок предписаний",
        "template.repeat_end": "Завершить блок предписаний",
        "template.violation_index": "Порядковый номер предписания",
        "template.page_shadow": "Тень листа",
        "template.duplicate": "Дублировать шаблон",
        "template.insert_page_number": "Вставить номер страницы",
        "template.table_hint_rows": "Строки — по вертикали",
        "template.table_hint_columns": "Столбцы — по горизонтали",
        "template.name_live": "Имя для сохранения",
        "template.preview_multi": "Показать 3 предписания",
        "template.auto_format": "Автоформат",
        "template.insert_header": "Вставить шапку",
        "template.insert_signature": "Вставить подпись",
        "template.page": "Стр.",
        "template.margin_preset": "Поля",
        "template.margin_normal": "Обычные",
        "template.margin_narrow": "Узкие",
        "template.margin_wide": "Широкие",
        "template.quick_blocks": "Быстрые блоки",
        "template.block_title": "Титульный блок",
        "template.block_violations": "Блок предписаний",

        "settings.customize": "Кастомизация",
        "settings.customize_hint": "Настройте текст кнопок панели инструментов",
        "settings.browser": "Браузер для печати",
        "settings.browser_default": "Системный по умолчанию",
        "settings.browser_custom": "Другой (указать путь)",
        "settings.browser_path_hint": "Укажите путь к браузеру (если выбрано \"Другой\")",
        "settings.btn_theme": "Тема",
        "settings.btn_lang": "Язык",
        "settings.btn_logout": "Выйти",
        "settings.btn_settings": "Настройки",
        "settings.btn_users": "Пользователи",
        "settings.btn_ai": "ИИ",
        "settings.btn_notes": "Заметки",
        "settings.btn_analytics": "Аналитика",
        "settings.btn_textbook": "Автозамена",
        "settings.btn_risk": "Файн-Кинни",
        "settings.btn_backup": "Бэкап",
        "settings.btn_report": "Отчёт",
        "settings.btn_export_log": "Лог",
        "settings.btn_merge": "Объединить дубли",
        "settings.btn_ai_diag": "Диагностика ИИ",
        "settings.btn_knowledge": "Нормативы",
        "settings.btn_print": "Печать",
        "settings.btn_about": "О программе",
        "settings.button_text": "Текст кнопки",
        "settings.default": "По умолчанию",

        "risk.title": "Экспресс-анализ риска (Файн-Кинни)",
        "risk.probability": "Вероятность (П)",
        "risk.exposure": "Частота воздействия (Э)",
        "risk.consequence": "Тяжесть (С)",
        "risk.calculate": "Рассчитать индекс опасности",
        "risk.index": "Индекс риска (R)",
        "risk.classification": "Классификация риска",
        "risk.low": "Малый риск. Особых мер не требуется.",
        "risk.moderate": "Умеренный риск. Требуется плановый контроль.",
        "risk.substantial": "Существенный риск. Нужны корректирующие действия.",
        "risk.high": "Высокий риск. Требуется немедленное вмешательство.",
        "risk.critical": "Критический риск! Работы должны быть остановлены!",
        "risk.prob_opts": "10.0 — Ожидаемо;6.0 — Вполне возможно;3.0 — Необычно;1.0 — Маловероятно;0.5 — Очень маловероятно;0.1 — Почти невозможно",
        "risk.exp_opts": "10.0 — Постоянно (ежедневно);6.0 — Часто (еженедельно);3.0 — Периодически (ежемесячно);2.0 — Временами;1.0 — Редко;0.5 — Очень редко",
        "risk.cons_opts": "100.0 — Катастрофические;40.0 — Тяжелые (смерть);15.0 — Серьезные (утрата трудосп.);7.0 — Средней тяжести;3.0 — Легкие;1.0 — Незначительные",

        "textbook.title": "Справочник автозамены формулировок ТБ",
        "textbook.instruction": "Введите короткое слово-триггер и длинный текст. При вводе триггера в карточках нарушений программа автоматически подставит развёрнутую формулировку.",
        "textbook.trigger": "Краткая фраза (триггер)",
        "textbook.expanded": "Развёрнутая формулировка",
        "textbook.new_trigger": "новый_триггер",
        "textbook.new_fulltext": "Полное описание...",
        "textbook.saved": "Справочник автозамены успешно обновлён!",

        "backup.list": "Список резервных копий",
        "backup.none": "Нет резервных копий",
        "backup.restored": "База данных успешно восстановлена",

        "analytics.title": "Аналитика",
        "analytics.contractor": "Сводный аудит подрядчиков",
        "analytics.category": "Аналитический свод по категориям",
        "analytics.total": "Всего нарушений",
        "analytics.active": "Активных предписаний",
        "analytics.fines_sum": "Сумма штрафов",
        "analytics.resolved": "Устранено",
        "analytics.control_pct": "Уровень контроля (%)",

        "knowledge.title": "Нормативная база СУОТ",
        "knowledge.save": "Сохранить изменения",

        "report.global_title": "Генеральный аналитический свод СУОТ",
        "report.active_violations": "Список нерешённых нарушений",
        "report.none_active": "Все предписания устранены. Риски отсутствуют.",
        "report.generated_html": "HTML-отчёт сформирован",

        "audit.export_title": "Экспорт журнала аудита",
        "audit.export_success": "Лог успешно выгружен",

        "template.register": "Добавление шаблона",
        "template.name_prompt": "Название пресета:",
        "template.desc_prompt": "Описание требований безопасности:",
        "template.cat_prompt": "Категория:",
        "template.fine_prompt": "Штраф по умолчанию (руб):",
        "template.registered": "Шаблон внедрён в систему!",

        "emp.passport": "Паспорт ТБ (.doc)",
        "emp.passport_saved": "Документ экспортирован и готов к редактированию в MS Word!",
        "emp.pin_generated": "Персональный цифровой ПИН-код: {pin}",

        "viol.word_report": "Печать бланка предписания",
        "viol.word_saved": "Бланк предписания успешно сохранён",
        "viol.archive_confirm": "Переместить {count} закрытых дел в архив?",
        "viol.archive_done": "Устранённые инциденты заархивированы",
        "viol.archive_none": "Нет исполненных предписаний со статусом 'Устранено'",

        "import.history_title": "История импорта",
        "import.history_empty": "История импорта пуста",
        "import.log_updated": "Обновлено записей: {count}",
        "import.log_created": "Создано записей: {count}",
        "import.log_merged": "Объединено дубликатов: {count}",
        "tools.merge_duplicates": "Объединить дубликаты",
        "tools.merge_employees": "Сотрудники",
        "tools.merge_violations": "Предписания",
        "tools.merge_ledger": "Произвольный",
        "tools.merge_done": "Объединение завершено. Объединено: {count}",
        "tools.merge_desc": "Выберите таблицу для объединения дубликатов. Записи с одинаковыми ключевыми полями будут объединены, а дубликаты удалены.",
        "ai.diagnostics": "Диагностика ИИ",
        "ai.test_connection": "Проверить подключение",
        "ai.connection_ok": "Подключение успешно",
        "ai.connection_failed": "Ошибка подключения: {error}",
        "ai.current_config": "Текущая конфигурация",
        "ai.provider_label": "Провайдер",
        "ai.url_label": "URL",
        "ai.model_label": "Модель",
        "ai.mode_label": "Режим",
        "ai.temp_label": "Температура",
        "ai.empty_response": "Пустой ответ от ИИ",
        "common.replace": "Заменить",
        "common.confirm_close": "Закрыть без сохранения?",
        "stat.document_stats": "Статистика документа",
        "stat.words": "Слов",
        "stat.characters": "Символов",
        "stat.characters_no_spaces": "Символов без пробелов",
        "stat.paragraphs": "Параграфов",
        "stat.pages": "Страниц",
        "stat.lines": "Строк",
        "template.imported": "Шаблон импортирован",
        "template.exported": "Шаблон экспортирован",
        "template.no_active": "Нет активного шаблона",
        "template.favorite_removed": "★ Избранное удалено",
        "template.favorite_added": "★ Добавлено в избранное",
        "template.notes_saved": "Заметки сохранены",
        "template.pasted_plain": "Текст вставлен без форматирования",
        "template.pdf_sent": "PDF отправлен на печать",
        "template.html_source": "HTML код шаблона",
        "template.special_chars": "Спецсимволы",
        "template.notes_title": "Заметки к шаблону",
        "template.notes_placeholder": "Заметки к шаблону (не попадают в печать)...",
        "template.document_outline": "Структура документа",
        "template.replace_all": "Заменить всё",
        "common.ruler": "Линейка",
        "common.replaced_count": "Заменено: {count}",
        "template.ruler_cm": "см",
        "template.ruler_in": "дюймы",
    }

    _en: Dict[str, str] = {
        "app.name": "OSH Enterprise",
        "app.version": "Version",
        "app.copyright": "© 2024 OSH Enterprise",

        "login.title": "Login — OSH Enterprise",
        "login.username": "Username",
        "login.password": "Password",
        "login.remember": "Remember Me",
        "login.btn": "Sign In",
        "login.error.empty": "Please fill all fields",
        "login.error.invalid": "Invalid username or password",
        "login.error.locked": "Account is locked",
        "login.success": "Login successful",
        "login.logout": "Log Out",
        "login.no_session": "No active session",

        "common.ok": "OK",
        "common.cancel": "Cancel",
        "common.save": "Save",
        "common.rename": "Rename",
        "common.delete": "Delete",
        "common.yes": "Yes",
        "common.no": "No",
        "dashboard.recent": "Recent Activity",
        "dashboard.no_activity": "No activity",
        "common.close": "Close",
        "common.global_search": "🔍 Global search…",
        "common.copy": "Copy",
        "common.apply": "Apply",
        "common.reset": "Reset",
        "common.search_hint": "Search…",
        "common.add": "Add",
        "common.edit": "Edit",
        "common.remove": "Remove",
        "common.search": "Search",
        "common.cut": "Cut",
        "common.paste": "Paste",
        "common.undo": "Undo",
        "common.redo": "Redo",
        "common.no_data": "No data",
        "common.field": "Field",
        "common.value": "Value",
        "common.find": "Find",
        "common.size": "Size",
        "common.filter": "Filter",
        "common.clear": "Clear",
        "common.export": "Export",
        "common.import_": "Import",
        "common.print": "Print",
        "common.settings": "Settings",
        "common.help": "Help",
        "common.about": "About",
        "common.system": "System",
        "common.no_selection": "No selection",
        "common.confirm": "Confirm",
        "common.warning": "Warning",
        "common.error": "Error",
        "common.info": "Information",
        "common.success": "Success",
        "common.loading": "Loading...",
        "common.processing": "Processing...",
        "common.done": "Done",
        "common.more": "More",
        "common.backup": "Backup",
        "common.restore": "Restore",
        "common.refresh": "Refresh",
        "common.select_all": "Select All",
        "common.deselect_all": "Deselect All",
        "common.name": "Name",
        "common.date": "Date",
        "common.description": "Description",
        "common.status": "Status",
        "common.actions": "Actions",
        "common.notes": "Notes",
        "common.notes_hint": "Enter note text...",
        "common.saved": "Saved",
        "common.reminders": "Reminders",
        "common.templates": "Templates",
        "common.report": "Report",
        "common.preview": "Preview",
        "common.table": "Table",
        "common.format": "Format",
        "common.count": "Count",
        "common.rename": "Rename",
        "common.currency": "RUB",
        "common.align_left": "Align Left",
        "common.align_center": "Center",
        "common.align_right": "Align Right",
        "common.paragraph": "Paragraph",
        "common.zoom_in": "Zoom In",
        "common.zoom_out": "Zoom Out",
        "common.reset_zoom": "Reset Zoom (100%)",
        "common.fullscreen": "Fullscreen",

        "tab.dashboard": "KPI Dashboard",
        "tab.employees": "Employees",
        "tab.violations": "Violations",
        "tab.companies": "Companies",
        "tab.custom_ledger": "Custom Ledger",
        "tab.statistics": "Statistics",
        "tab.audit": "Audit",
        "tab.ai": "AI Assistant",
        "tab.reminders": "Reminders",

        "emp.id": "ID",
        "emp.fio": "Full Name",
        "emp.position": "Position",
        "emp.department": "Department",
        "emp.company": "Company",
        "emp.phone": "Phone",
        "emp.medical_date": "Medical Check",
        "emp.qualification": "Qualification",
        "emp.date_conducted": "Date Conducted",
        "emp.photo": "Photo",
        "emp.status": "Status",
        "emp.add": "Add Employee",
        "emp.edit": "Edit Employee",
        "emp.delete": "Delete Employee",
        "emp.delete_confirm": "Are you sure you want to delete {count} employee(s)?",
        "emp.import": "Import Employees",
        "emp.export": "Export Employees",
        "emp.duplicate_found": "Employee already exists. Update the existing record?",
        "emp.duplicate_updated": "Existing employee updated",
        "viol.duplicate_found": "Violation already exists. Update the existing record?",
        "viol.duplicate_updated": "Existing violation updated",
        "import.history_title": "Import History",
        "import.history_empty": "Import history is empty",
        "import.log_updated": "Records updated: {count}",
        "import.log_created": "Records created: {count}",
        "import.log_merged": "Duplicates merged: {count}",
        "tools.merge_duplicates": "Merge Duplicates",
        "tools.merge_employees": "Employees",
        "tools.merge_violations": "Violations",
        "tools.merge_ledger": "Custom Ledger",
        "tools.merge_done": "Merge completed. Merged: {count}",
        "tools.merge_desc": "Select a table to merge duplicates. Records with matching key fields will be merged, and duplicates removed.",
        "ai.diagnostics": "AI Diagnostics",
        "ai.test_connection": "Test Connection",
        "ai.connection_ok": "Connection successful",
        "ai.connection_failed": "Connection failed: {error}",
        "ai.current_config": "Current Configuration",
        "ai.provider_label": "Provider",
        "ai.url_label": "URL",
        "ai.model_label": "Model",
        "ai.mode_label": "Mode",
        "ai.temp_label": "Temperature",
        "viol.duplicate_found": "A violation for this company and description already exists. Update existing record?",
        "viol.duplicate_updated": "Existing violation record updated",
        "import.history_title": "Import History",
        "import.history_empty": "Import history is empty",
        "import.log_updated": "Updated records: {count}",
        "import.log_created": "Created records: {count}",
        "import.log_merged": "Merged duplicates: {count}",
        "tools.merge_duplicates": "Merge Duplicates",
        "tools.merge_employees": "Employees",
        "tools.merge_violations": "Violations",
        "tools.merge_ledger": "Custom Ledger",
        "tools.merge_done": "Merge complete. Merged: {count}",
        "tools.merge_desc": "Select a table to merge duplicates. Records with identical key fields will be merged and duplicates removed.",
        "ai.diagnostics": "AI Diagnostics",
        "ai.test_connection": "Test Connection",
        "ai.connection_ok": "Connection successful",
        "ai.connection_failed": "Connection failed: {error}",
        "ai.current_config": "Current Configuration",
        "ai.provider_label": "Provider",
        "ai.url_label": "URL",
        "ai.model_label": "Model",
        "ai.mode_label": "Mode",
        "ai.temp_label": "Temperature",

        "viol.id": "ID",
        "viol.date": "Date",
        "viol.company": "Company",
        "viol.department": "Department",
        "viol.risk_category": "Risk Category",
        "viol.description": "Description",
        "viol.responsible": "Responsible",
        "viol.deadline": "Due Date",
        "viol.fine": "Fine",
        "viol.status": "Status",
        "viol.photo": "Photo",
        "viol.types": "Violation Types",
        "viol.type_name": "Name",
        "viol.add": "Add Violation",
        "viol.edit": "Edit Violation",
        "viol.delete": "Delete Violation",
        "viol.delete_confirm": "Are you sure you want to delete this violation?",
        "viol.import": "Import Violations",
        "viol.export": "Export Violations",
        "viol.use_template": "Use Template",
        "viol.create_reminder": "Create Reminder",
        "viol.duplicate_found": "Violation for this company with this description already exists. Update existing record?",
        "viol.duplicate_updated": "Existing violation updated",

        "company.id": "ID",
        "company.name": "Name",
        "company.address": "Address",
        "company.contact": "Contact",
        "company.employees_count": "Employees",
        "company.violations_count": "Violations",
        "company.fines_total": "Total Fines",
        "company.add": "Add Company",
        "company.edit": "Edit Company",
        "company.delete": "Delete Company",

        "ledger.id": "ID",
        "ledger.date": "Date",
        "ledger.category": "Category",
        "ledger.description": "Description",
        "ledger.responsible": "Responsible",
        "ledger.status": "Status",
        "ledger.photo": "Photo",
        "ledger.note": "Note",
        "ledger.add": "Add Record",
        "ledger.edit": "Edit Record",
        "ledger.delete": "Delete Record",
        "ledger.delete_confirm": "Are you sure you want to delete this record?",

        "column.rename": "Rename Column",
        "column.name_empty": "Name cannot be empty",
        "column.add": "Add Column",
        "column.delete": "Delete Column",
        "column.change_type": "Change Type",
        "column.rename_prompt": "Enter new column name:",
        "column.add_prompt": "Enter new column name:",
        "column.duplicate_error": "A column with this name already exists",
        "column.type_text": "Text",
        "column.type_number": "Number",
        "column.type_date": "Valid until",
        "column.type_date_conducted": "Date Conducted",
        "column.type_status": "Status",
        "column.type_media": "Media",

        "search.placeholder": "Search table...",
        "search.global": "Global Search",
        "search.global_placeholder": "Search across the entire application...",
        "search.regex": "Regex",
        "search.no_results": "No results found",

        "status.compliant": "Compliant",
        "status.expiring": "Expiring Soon",
        "status.overdue": "Overdue",
        "status.archived": "Archived",
        "status.active": "Active",
        "status.resolved": "Resolved",

        "date.format_hint": "Format: DD.MM.YYYY (auto-convert from MM-DD-YYYY)",
        "date.overdue": "Overdue by {days} days",
        "date.expiring": "Expires in {days} days",
        "date.ok": "In compliance",
        "date.conducted_marker": "Date Conducted (archived)",

        "notes.title": "Notes",
        "notes.global": "General Notes",
        "notes.entity": "Record Notes",
        "notes.add": "Add Note",
        "notes.delete": "Delete Note",
        "notes.placeholder": "Enter note text...",

        "reminder.title": "Reminders",
        "reminder.add": "Add Reminder",
        "reminder.edit": "Edit Reminder",
        "reminder.delete": "Delete Reminder",
        "reminder.title_field": "Title",
        "reminder.description": "Description",
        "reminder.due_date": "Due Date",
        "reminder.interval": "Check Interval (sec.)",
        "reminder.is_done": "Completed",
        "reminder.no_items": "No reminders",
        "reminder.notification": "Reminder: {title}",
        "reminder.all": "All Reminders",
        "reminder.overdue_section": "Overdue reminders",
        "reminder.upcoming_section": "Upcoming reminders",
        "reminder.overdue_only": "Only overdue",
        "reminder.quick_all": "All",
        "reminder.quick_overdue": "Overdue",
        "reminder.quick_3days": "Next 3 days",
        "reminder.quick_30days": "Next 30 days",
        "reminder.sort_order": "Sort order",
        "reminder.sort_priority": "Overdue first",
        "reminder.sort_due_asc": "Nearest due first",
        "reminder.sort_due_desc": "Latest due first",
        "reminder.type": "Type",
        "reminder.entity": "Entity",
        "reminder.days_left": "Days Left",
        "reminder.expiring_hint": "The following items are expiring within 30 days.",
        "reminder.overdue": "Overdue by {days} day(s)",
        "reminder.today": "Today",
        "reminder.days_format": "{days} day(s)",
        "reminder.startup_popup": "You have {count} expiring items. Open reminders?",

        "print.title": "Print Document",
        "print.template": "Print Template",
        "print.order": "Safety Order",
        "print.report": "Report",
        "print.edit_template": "Edit Template",
        "print.preview": "Preview",
        "print.open_browser": "Open in browser",
        "print.generated": "Document generated",
        "print.portrait": "Portrait",
        "print.landscape": "Landscape",
        "print.orientation": "Orientation",
        "print.without_template": "Without template",
        "print.any_table": "Print current table",

        "settings.title": "System Settings",
        "settings.language": "Interface Language",
        "settings.theme": "Theme",
        "settings.accent_color": "Accent Color",
        "settings.light": "Light",
        "settings.dark": "Dark",
        "settings.auto_save": "Auto-Save Interval (sec.)",
        "settings.reminder_interval": "Reminder Interval (sec.)",
        "settings.media_path": "Media Folder",
        "settings.saved": "Settings saved",

        "user.title": "User Management",
        "user.add": "Add User",
        "user.delete": "Delete User",
        "user.change_password": "Change Password",
        "user.change_role": "Change Role",
        "user.username": "Username",
        "user.password": "Password",
        "user.role": "Role",
        "user.role_admin": "Administrator",
        "user.role_inspector": "Inspector",
        "user.role_manager": "Manager",
        "user.delete_confirm": "Delete user {username}?",
        "user.password_change_title": "Change Password",

        "stat.title": "Statistics",
        "stat.employees_total": "Total Employees",
        "stat.violations_total": "Total Violations",
        "stat.companies_total": "Total Companies",
        "stat.overdue_total": "Overdue Items",
        "stat.fines_total": "Total Fines",
        "stat.safety_score": "Safety Score",
        "stat.by_company": "By Company",
        "stat.by_category": "By Category",
        "stat.by_status": "By Status",
        "stat.status_distribution": "Status Distribution",
        "stat.overdue_trend": "Overdue Violations",

        "audit.title": "Audit Trail",
        "audit.timestamp": "Timestamp",
        "audit.event": "Event",
        "audit.severity": "Severity",
        "audit.details": "Details",
        "audit.info": "Info",
        "audit.warning": "Warning",
        "audit.critical": "Critical",
        "audit.filter_severity": "Filter by Severity",

        "backup.title": "Backups",
        "backup.create": "Create Backup",
        "backup.restore": "Restore",
        "backup.delete": "Delete Backup",
        "backup.created_at": "Created",
        "backup.size": "Size",
        "backup.sha256": "Checksum",
        "backup.restore_confirm": "Restore database from backup dated {date}?",
        "backup.restore_warning": "All current data will be replaced!",
        "backup.success": "Backup created",
        "backup.restore_success": "Database restored from backup",

        "ai.title": "AI Assistant",
        "ai.api_url": "API URL",
        "ai.api_key": "API Key",
        "ai.model": "Model",
        "ai.mode": "Mode",
        "ai.mode_chat": "Chat",
        "ai.mode_search": "Search",
        "ai.mode_agent": "Agent",
        "ai.send": "Send",
        "ai.clear": "Clear",
        "ai.attach_tooltip": "Attach file or image",
        "ai.attach_file": "Select a file",
        "ai.attach_filter": "All files (*);;Images (*.png *.jpg *.jpeg *.gif *.bmp);;Documents (*.pdf *.doc *.docx *.txt);;Text files (*.txt)",
        "ai.placeholder": "Type your message...",
        "ai.thinking": "AI is thinking...",
        "ai.error": "AI Error: {error}",
        "ai.empty_response": "Empty AI response",
        "ai.no_key": "Please set your API key in settings",
        "ai.confirm_action": "AI wants to perform: {action}\nAllow?",
        "ai.action_executed": "Action executed: {action}",
        "ai.action_cancelled": "Action cancelled",
        "ai.provider": "Provider",
        "ai.temperature": "Temperature",
        "ai.system_prompt": "You are an AI assistant for an Occupational Safety and Health "
                            "management system. You have access to the database. You can search, "
                            "analyze and modify data (with user confirmation).",

        "report.title": "General Report",
        "report.company": "Company Report",
        "report.all_companies": "All Companies",
        "report.include": "Include in report:",
        "report.employees": "Employees",
        "report.violations": "Violations",
        "report.fines": "Fines",
        "report.summary": "Summary",
        "report.no_data": "No data for report",
        "report.generated": "Report generated",

        "import.title": "Import Data",
        "import.file": "File",
        "import.select": "Select File",
        "import.execute": "Import",
        "import.success": "Imported {count} records",
        "import.log_title": "Import Results",
        "import.updated": "Updated",
        "import.save_log": "Save Log",
        "import.skip": "Skip",

        "template.title": "Print Templates",

        "help.title": "Help",
        "help.shortcuts": "Keyboard Shortcuts",
        "help.features": "Program Features",
        "help.version": "Version",
        "help.nav_table": "Navigate table rows",
        "help.search": "Search (focus search field)",
        "help.save": "Save current record",
        "help.print": "Print",
        "help.export": "Export selected record",
        "help.add_record": "Add new record",
        "help.delete": "Delete selected",
        "help.edit": "Edit record",
        "help.click_column": "Click column header",
        "help.sort": "Sort by column",
        "help.right_click_column": "Right-click column header",
        "help.column_menu": "Menu: rename/add/delete column",
        "help.right_click_row": "Right-click row",
        "help.row_menu": "Row context menu",
        "help.feat_multi_user": "Multi-user mode with access control",
        "help.feat_ai_assistant": "AI assistant with multiple provider support",
        "help.feat_import_export": "Import from Excel and export to CSV",
        "help.feat_print_templates": "Flexible print templates",
        "help.feat_photo": "Attach photos to employees and violations",
        "help.feat_notes": "Notes for any record",
        "help.feat_color_indicators": "Color indicators for deadlines and statuses",
        "help.feat_reports": "Report generation (Word, Excel, HTML)",
        "help.feat_auto_save": "Automatic backup",
        "help.feat_custom_columns": "Customizable columns in journals",
        "help.toolbar": "Toolbar",
        "help.toolbar_desc": "Top bar buttons: theme/language toggle, user, import/export, print, AI chat, notes, analytics, textbook, risk calculator, backup, report, log export, AI diagnostics, knowledge base",
        "help.tabs": "Tabs",
        "help.tabs_desc": "Dashboard → Employees → Violations → Companies → Custom Ledger → Statistics → Audit → Reminders → AI Chat",
        "help.tables": "Table Operations",
        "help.tables_desc": "Text & regex search, click header to sort, double-click header to auto-fit, drag columns to reorder, row context menu (copy/edit/delete/print), header context menu (rename/add/delete column type)",
        "help.import": "Import Data",
        "help.import_desc": "Supports CSV and Excel (.xlsx). Column mapping from source to program fields. Automatic duplicate detection and merge.",
        "help.export_desc": "Export selected rows to CSV or Excel (.xlsx). Select rows and click export button.",
        "help.ai": "AI Assistant",
        "help.ai_desc": "Supports OpenAI, OpenRouter, DeepSeek, Anthropic Claude, Google Gemini, Groq, local Ollama/LM Studio. Modes: chat (free conversation), search (database search), agent (perform actions: create/edit records, reports).",
        "help.print_templates": "Print Templates",
        "help.print_templates_desc": "WYSIWYG template editor: font selection, size, color, bold/italic/underline, alignment, variable insertion from field tree. Preview before printing.",
        "help.analytics": "Analytics",
        "help.analytics_desc": "By company: violation counts, fines, employees. By risk category: violation distribution, resolution percentage.",
        "help.reminders": "Reminders",
        "help.reminders_desc": "Automatic overdue check on startup. Filters: All/Overdue/3 days/30 days. Sort by priority or date. Export to CSV/Excel.",
        "help.security": "Security",
        "help.security_desc": "Password login (PBKDF2-SHA256), roles (Administrator/User), audit log of all actions, backup with integrity verification.",
        "help.tips": "Tips & Tricks",
        "help.tips_list": "• Double-click column header — auto-fit width\n• Right-click cell — copy value\n• Ctrl+F — focus search\n• Ctrl+N — new record\n• Ctrl+E — export\n• Ctrl+P — print\n• Delete — delete record\n• Drag columns to reorder\n• Double-click a tab to rename\n• Global search (top bar) — searches all tables + notes\n• AI agent can create/edit records by voice/text\n• Textbook auto-replace — shorten frequently typed phrases",
        "help.global_search": "Global Search",
        "help.global_search_desc": "Searches employees, violations, companies, custom ledger and notes. Results displayed as a tree; double-click navigates to record.",
        "help.dashboard": "Dashboard",
        "help.dashboard_desc": "Shows overall statistics: employee count, violations, companies, overdue reminders, total fines. Safety Score gauge. Recent activity feed.",
        "help.notes": "Notes",
        "help.notes_desc": "Each record can have rich text (HTML) notes. Global notes also available. Search across all notes.",
        "help.photos": "Photos",
        "help.photos_desc": "Attach photos to employees and violations. Drag-and-drop support, gallery view, zoom/pan.",
        "help.reports": "Reports",
        "help.reports_desc": "Global report across all companies (summary + active violations) in HTML or DOC format. Audit log export to LOG file.",
        "help.backup": "Backup",
        "help.backup_desc": "Automatic daily backup on first launch. Manual create and restore from ZIP archives with SHA-256 verification.",
        "help.settings": "Settings",
        "help.settings_desc": "Tabs: General (language, theme, accent color), System (autosave interval, reminder check, media directory), Customization (toolbar button labels).",
        "help.textbook": "Auto-Replace Textbook",
        "help.textbook_desc": "Set of 'code → text' rules. When typing a code and pressing Space/Enter, the code is automatically replaced with the full text. Useful for frequently typed OSH phrases.",
        "help.risk_calc": "Risk Calculator (Fine-Kinney)",
        "help.risk_calc_desc": "Risk assessment using Fine-Kinney method: probability, exposure, consequences. Automatic score calculation and risk level (green/yellow/red).",
        "help.column_customization": "Column Customization",
        "help.column_customization_desc": "In each table: rename column, add new (with type selection: text/date/number/list/photo/boolean), delete, reorder by dragging.",
        "help.color_indicators": "Color Indicators",
        "help.color_indicators_desc": "Statuses highlighted by color: green (active/completed), yellow (warning/expiring soon), red (overdue/critical), grey (inactive).",
        "help.knowledge_base": "AI Knowledge Base",
        "help.knowledge_base_desc": "Text file with additional information used by AI when answering. Editable via built-in editor.",
        "help.autosave": "Autosave",
        "help.autosave_desc": "Periodic autosave of changes (interval configurable in Settings → System).",
        "help.duplicate_merge": "Duplicate Detection",
        "help.duplicate_merge_desc": "When adding a record, the system checks for potential duplicates by name/full name and offers to merge or skip.",
        "help.hotkey_manager": "Hotkey Manager",
        "help.hotkey_manager_desc": "Ctrl+N (add), Ctrl+E (export), Ctrl+P (print), Ctrl+S (save), Ctrl+F (search), Delete (delete).",

        "import.preview": "Preview",
        "import.column_map": "Column Mapping",
        "import.source": "Source",
        "import.destination": "Destination",
        "import.skip": "Skip",
        "import.execute": "Import",
        "import.success": "Imported {count} records",
        "import.error": "Import error: {error}",

        "export.title": "Export Data",
        "export.csv": "CSV",
        "export.excel": "Excel (.xlsx)",
        "export.success": "Export complete: {path}",
        "export.error": "Export error: {error}",

        "sort.asc": "ascending",
        "sort.desc": "descending",
        "sort.none": "no sorting",

        "filter.all": "All",
        "filter.company": "Company: {name}",
        "filter.status": "Status: {status}",
        "filter.date_from": "Date from",
        "filter.date_to": "Date to",

        "toast.reminder": "Reminder",
        "toast.backup": "Backup",
        "toast.error": "Error",
        "toast.save_success": "Saved",
        "toast.delete_success": "Deleted",
        "toast.backup_created": "Backup created",
        "emp.backup_before_delete": "Create backup before deleting?",

        "hotkeys.title": "Hotkeys",
        "hotkeys.save": "Ctrl+S — Save",
        "hotkeys.search": "Ctrl+F — Search",
        "hotkeys.new": "Ctrl+N — New Record",
        "hotkeys.delete": "Del — Delete",
        "hotkeys.autoreplace": "Ctrl+Shift+A — Auto-Replace",
        "hotkeys.refresh": "F5 — Refresh",
        "hotkeys.fullscreen": "F11 — Full Screen",
        "hotkeys.undo": "Ctrl+Z — Undo",
        "hotkeys.redo": "Ctrl+Y — Redo",

        "datetime.now": "now",
        "datetime.minutes_ago": "{n} minutes ago",
        "datetime.hours_ago": "{n} hours ago",
        "datetime.days_ago": "{n} days ago",
        "datetime.today": "Today",
        "datetime.yesterday": "Yesterday",

        "error.generic": "An error occurred",
        "error.db_locked": "Database is locked",
        "error.no_permission": "Insufficient permissions",
        "error.not_found": "Record not found",
        "error.invalid_data": "Invalid data",
        "error.file_not_found": "File not found",
        "error.import_failed": "File import failed",

        "textbook.auto_replace": "Auto-Replace (Textbook)",
        "textbook.edit": "Auto-Replace Editor",
        "textbook.shortcode": "Code",
        "textbook.fulltext": "Full Text",
        "textbook.add": "Add Rule",
        "textbook.delete": "Delete Rule",
        "textbook.enable_auto": "Auto-replace on input",
        "textbook.trigger_hint": "Type the code and press Space or Enter",

        "template.edit": "Template Editor",
        "template.name": "Template Name",
        "template.html": "HTML Template",
        "template.css": "CSS Styles",
        "template.preview": "Preview",
        "template.choose": "Select print template:",
        "template.save": "Save Template",
        "template.reset": "Reset to Default",
        "template.delete_confirm": "Delete template?",
        "template.variables": "Available variables: {name}, {date}, {company}, {description}, {responsible}, {deadline}, {fine}, {photos}",
        "template.insert_variable": "Insert Variable",
        "template.insert_table": "Insert Table",
        "template.table_rows": "Number of rows:",
        "template.table_columns": "Number of columns:",
        "template.fit_page": "Fit Page",
        "template.copy_html": "Copy HTML",
        "template.available_fields": "Available Fields",
        "template.variables_group": "Template Fields",
        "template.empty_hint": "Start editing the template — live preview will appear automatically",
        "template.preview_error": "Preview error",
        "template.select": "Select Template",
        "template.untitled": "Untitled",
        "template.heading1": "Heading 1",
        "template.heading2": "Heading 2",
        "template.heading3": "Heading 3",
        "template.chars": "chars",
        "template.words": "words",
        "template.word_wrap": "Word Wrap",
        "template.match_case": "Match Case",
        "template.record_number": "Record #",
        "template.violation_number": "Violation #",
        "template.multi_record_hint": "When selecting multiple violations, variables above repeat for each one",
        "template.multi_record_hint2": "these fields are auto-filled from each selected violation",
        "template.fit_width": "Fit Width",
        "template.page_break": "Page Break",
        "template.insert_date": "Insert Date",
        "template.page_settings": "Page Margins",
        "template.margin_left": "Left",
        "template.margin_right": "Right",
        "template.margin_top": "Top",
        "template.margin_bottom": "Bottom",
        "template.repeat_group": "Repeat For Each Violation",
        "template.repeat_group_hint": "Everything between the markers below is repeated for the 1st, 2nd, 3rd and next violations",
        "template.repeat_start": "Start Violations Block",
        "template.repeat_end": "End Violations Block",
        "template.violation_index": "Violation Order Number",
        "template.page_shadow": "Page Shadow",
        "template.duplicate": "Duplicate Template",
        "template.insert_page_number": "Insert Page Number",
        "template.table_hint_rows": "Rows — vertical direction",
        "template.table_hint_columns": "Columns — horizontal direction",
        "template.name_live": "Name for saving",
        "template.preview_multi": "Show 3 violations",
        "template.auto_format": "Auto Format",
        "template.insert_header": "Insert Header",
        "template.insert_signature": "Insert Signature",
        "template.page": "Page",
        "template.margin_preset": "Margins",
        "template.margin_normal": "Normal",
        "template.margin_narrow": "Narrow",
        "template.margin_wide": "Wide",
        "template.quick_blocks": "Quick Blocks",
        "template.block_title": "Title Block",
        "template.block_violations": "Violations Block",

        "settings.customize": "Customize",
        "settings.customize_hint": "Customize toolbar button labels",
        "settings.browser": "Print Browser",
        "settings.browser_default": "System Default",
        "settings.browser_custom": "Custom (specify path)",
        "settings.browser_path_hint": "Path to browser executable (only for custom)",
        "settings.btn_theme": "Theme",
        "settings.btn_lang": "Language",
        "settings.btn_logout": "Logout",
        "settings.btn_settings": "Settings",
        "settings.btn_users": "Users",
        "settings.btn_ai": "AI",
        "settings.btn_notes": "Notes",
        "settings.btn_analytics": "Analytics",
        "settings.btn_textbook": "Autoreplace",
        "settings.btn_risk": "Fine-Kinney",
        "settings.btn_backup": "Backup",
        "settings.btn_report": "Report",
        "settings.btn_export_log": "Audit Log",
        "settings.btn_merge": "Merge Duplicates",
        "settings.btn_ai_diag": "AI Diagnostics",
        "settings.btn_knowledge": "Knowledge",
        "settings.btn_print": "Print",
        "settings.btn_about": "About",
        "settings.button_text": "Button text",
        "settings.default": "Default",

        "risk.title": "Risk Express Analysis (Fine-Kinney)",
        "risk.probability": "Probability (P)",
        "risk.exposure": "Exposure Frequency (E)",
        "risk.consequence": "Consequence Severity (C)",
        "risk.calculate": "Calculate Risk Index",
        "risk.index": "Risk Index (R)",
        "risk.classification": "Risk Classification",
        "risk.low": "Low Risk. No special measures required.",
        "risk.moderate": "Moderate Risk. Scheduled control required.",
        "risk.substantial": "Substantial Risk. Corrective actions needed.",
        "risk.high": "High Risk. Immediate intervention required.",
        "risk.critical": "Critical Risk! Work must be stopped!",
        "risk.prob_opts": "10.0 — Expected/Certain;6.0 — Quite possible;3.0 — Unusual;1.0 — Unlikely;0.5 — Very unlikely;0.1 — Almost impossible",
        "risk.exp_opts": "10.0 — Constantly (daily);6.0 — Often (weekly);3.0 — Periodically (monthly);2.0 — Sometimes;1.0 — Rarely;0.5 — Very rarely",
        "risk.cons_opts": "100.0 — Catastrophic (multiple deaths);40.0 — Severe (one death);15.0 — Serious (permanent disability);7.0 — Moderate (extended sick leave);3.0 — Minor (first aid);1.0 — Negligible",

        "textbook.title": "Autocomplete Reference (Textbook)",
        "textbook.instruction": "Enter a short trigger word and the expanded text. When you type the trigger in violation cards, the program will auto-substitute the full text.",
        "textbook.trigger": "Short phrase (Trigger)",
        "textbook.expanded": "Expanded safety wording",
        "textbook.new_trigger": "new_trigger",
        "textbook.new_fulltext": "Full description...",
        "textbook.saved": "Textbook updated successfully!",

        "backup.list": "Backup list",
        "backup.none": "No backups available",
        "backup.restored": "Database successfully restored",

        "analytics.title": "Analytics",
        "analytics.contractor": "Contractor Audit Summary",
        "analytics.category": "Risk Category Analytics",
        "analytics.total": "Total violations",
        "analytics.active": "Active orders",
        "analytics.fines_sum": "Total fines",
        "analytics.resolved": "Resolved",
        "analytics.control_pct": "Control rate (%)",

        "knowledge.title": "OSH Knowledge Base",
        "knowledge.save": "Save changes",

        "report.global_title": "OSH Global Analytic Report",
        "report.active_violations": "Unresolved violations list",
        "report.none_active": "All violations resolved. No risks.",
        "report.generated_html": "HTML report generated",

        "audit.export_title": "Export audit log",
        "audit.export_success": "Log exported successfully",

        "template.register": "Register template",
        "template.name_prompt": "Preset name:",
        "template.desc_prompt": "Safety requirement description:",
        "template.cat_prompt": "Category:",
        "template.fine_prompt": "Default fine (RUB):",
        "template.registered": "Template registered!",

        "emp.passport": "Safety Passport (.doc)",
        "emp.passport_saved": "Document exported and ready for editing in MS Word!",
        "emp.pin_generated": "Personal security PIN: {pin}",

        "viol.word_report": "Print violation order (.doc)",
        "viol.word_saved": "Violation order saved successfully",
        "viol.archive_confirm": "Archive {count} resolved cases?",
        "viol.archive_done": "Resolved incidents archived",
        "viol.archive_none": "No resolved violations found",
        "common.replace": "Replace",
        "common.confirm_close": "Close without saving?",
        "stat.document_stats": "Document Statistics",
        "stat.words": "Words",
        "stat.characters": "Characters",
        "stat.characters_no_spaces": "Characters (no spaces)",
        "stat.paragraphs": "Paragraphs",
        "stat.pages": "Pages",
        "stat.lines": "Lines",
        "template.imported": "Template imported",
        "template.exported": "Template exported",
        "template.no_active": "No active template",
        "template.favorite_removed": "★ Removed from favorites",
        "template.favorite_added": "★ Added to favorites",
        "template.notes_saved": "Notes saved",
        "template.pasted_plain": "Text pasted without formatting",
        "template.pdf_sent": "PDF sent to print",
        "template.html_source": "HTML Source Code",
        "template.special_chars": "Special Characters",
        "template.notes_title": "Template Notes",
        "template.notes_placeholder": "Template notes (not printed)...",
        "template.document_outline": "Document Outline",
        "common.ruler": "Ruler",
        "common.replaced_count": "Replaced: {count}",
        "template.replace_all": "Replace All",
        "template.ruler_cm": "cm",
        "template.ruler_in": "inches",
    }

    @classmethod
    def set_language(cls, lang: str) -> None:
        if lang in ("ru", "en"):
            cls._current = lang

    @classmethod
    def current(cls) -> str:
        return cls._current

    @classmethod
    def _(cls, key: str, default: Optional[str] = None, **fmt_args: Any) -> str:
        d = cls._ru if cls._current == "ru" else cls._en
        val = d.get(key, default)
        if val is None:
            val = key
        if fmt_args:
            try:
                val = val.format(**fmt_args)
            except KeyError:
                pass
        return val

    @classmethod
    def get_all_keys(cls) -> List[str]:
        return list(cls._ru.keys())


# ---------------------------------------------------------------------------
# SECTION 1.7: Async Worker Pool (QRunnable + QThreadPool)
# ---------------------------------------------------------------------------

try:
    from PyQt5.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal


    class WorkerSignals(QObject):
        started = pyqtSignal()
        progress = pyqtSignal(int, str)
        result = pyqtSignal(object)
        error = pyqtSignal(str)
        finished = pyqtSignal()


    class Worker(QRunnable):
        def __init__(self, fn: Callable, *args: Any, **kwargs: Any) -> None:
            super().__init__()
            self.fn = fn
            self.args = args
            self.kwargs = kwargs
            self.signals = WorkerSignals()

        def run(self) -> None:
            try:
                self.signals.started.emit()
                result = self.fn(*self.args, **self.kwargs)
                self.signals.result.emit(result)
            except Exception:
                self.signals.error.emit(traceback.format_exc())
            finally:
                self.signals.finished.emit()


    class AsyncPool:
        _pool = QThreadPool()

        @classmethod
        def start(cls, worker: Worker) -> None:
            cls._pool.start(worker)

        @classmethod
        def max_thread_count(cls) -> int:
            return cls._pool.maxThreadCount()
except ImportError:
    Worker = None
    AsyncPool = None
    WorkerSignals = None


# ---------------------------------------------------------------------------
# SECTION 1.8: Database Manager (Hybrid Relational-Document)
# ---------------------------------------------------------------------------

class DatabaseManager:
    _instance: Optional["DatabaseManager"] = None
    _lock: Any = None
    _cache: Dict[str, tuple] = {}

    def invalidate_cache(self, category: str = "") -> None:
        if category:
            self._cache = {k: v for k, v in self._cache.items() if category not in k}
        else:
            self._cache.clear()

    def __new__(cls, *args: Any, **kwargs: Any) -> "DatabaseManager":
        if cls._instance is None:
            from threading import Lock
            cls._lock = Lock()
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(DatabaseManager, cls).__new__(cls)
        return cls._instance

    def __init__(self, database_path: Optional[str] = None) -> None:
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self.database_path = database_path or RUNTIME_PATHS.database_path
        self._lock = __import__('threading').Lock()
        self.conn = sqlite3.connect(self.database_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA synchronous=NORMAL;")
        self.conn.execute("PRAGMA foreign_keys=ON;")
        self.conn.execute("PRAGMA busy_timeout=5000;")
        self.conn.execute("PRAGMA cache_size=-8000;")
        self._session_manager: Optional[SessionManager] = None
        self._init_schema()
        self._seed_defaults()
        self._fix_column_types()

    @property
    def session_manager(self) -> SessionManager:
        if self._session_manager is None:
            self._session_manager = SessionManager(self)
        return self._session_manager

    # -----------------------------------------------------------------------
    # SCHEMA
    # -----------------------------------------------------------------------

    def _init_schema(self) -> None:
        try:
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'Inspector',
                    session_token TEXT,
                    token_expiry TEXT
                );

                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS columns_config (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL DEFAULT 'Текст',
                    position INTEGER NOT NULL DEFAULT 0,
                    visible INTEGER NOT NULL DEFAULT 1,
                    UNIQUE(category, name)
                );

                CREATE TABLE IF NOT EXISTS employees (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    data_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS violations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    data_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS custom_ledger (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    data_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS companies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    address TEXT DEFAULT '',
                    contact TEXT DEFAULT '',
                    data_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_type TEXT NOT NULL DEFAULT 'global',
                    entity_id INTEGER,
                    title TEXT DEFAULT '',
                    content TEXT DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    due_date TEXT NOT NULL,
                    check_interval INTEGER NOT NULL DEFAULT 60,
                    is_done INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS custom_templates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    data_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS textbook (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    short_code TEXT UNIQUE NOT NULL,
                    full_text TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
                    event TEXT NOT NULL,
                    severity TEXT NOT NULL DEFAULT 'INFO',
                    details TEXT NOT NULL DEFAULT '{}',
                    username TEXT DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS backups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    file_path TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL DEFAULT 0,
                    sha256 TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS print_templates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    template_type TEXT NOT NULL DEFAULT 'order',
                    html_content TEXT NOT NULL DEFAULT '',
                    css_content TEXT DEFAULT '',
                    is_default INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS ai_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL DEFAULT ''
                );

                CREATE TRIGGER IF NOT EXISTS trg_audit_insert_only
                BEFORE UPDATE ON audit_log
                BEGIN
                    SELECT RAISE(ABORT, 'Audit log is immutable');
                END;

                CREATE TRIGGER IF NOT EXISTS trg_audit_no_delete
                BEFORE DELETE ON audit_log
                BEGIN
                    SELECT RAISE(ABORT, 'Audit log is immutable');
                END;

                CREATE TABLE IF NOT EXISTS violation_types (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    risk_category TEXT NOT NULL DEFAULT 'Средняя',
                    description TEXT DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS import_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
                    table_name TEXT NOT NULL,
                    source_file TEXT,
                    imported INTEGER NOT NULL DEFAULT 0,
                    updated INTEGER NOT NULL DEFAULT 0,
                    errors INTEGER NOT NULL DEFAULT 0,
                    details TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_audit_severity ON audit_log(severity);
                CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp);
                CREATE INDEX IF NOT EXISTS idx_employees_json ON employees(data_json);
                CREATE INDEX IF NOT EXISTS idx_violations_json ON violations(data_json);
                CREATE INDEX IF NOT EXISTS idx_notes_entity ON notes(entity_type, entity_id);
                CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders(due_date);
            """)
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

        # Migrate: add user_id column to json data tables
        for tbl in ("employees", "violations", "custom_ledger"):
            try:
                self.conn.execute(f"ALTER TABLE {tbl} ADD COLUMN user_id INTEGER DEFAULT 0")
            except Exception:
                pass  # column already exists
        self.conn.commit()

    # -----------------------------------------------------------------------
    # SEED DEFAULT DATA
    # -----------------------------------------------------------------------

    def _insert_or_ignore(self, table: str, values: Dict[str, Any]) -> None:
        if table not in {"settings", "users", "ai_settings", "columns_config",
                          "violation_types", "reminders", "notes", "audit_log",
                          "employees", "violations", "custom_ledger", "companies"}:
            raise ValueError(f"Invalid table: {table}")
        try:
            cols = ", ".join(values.keys())
            plc = ", ".join(["?" for _ in values])
            self.conn.execute(f"INSERT OR IGNORE INTO {table} ({cols}) VALUES ({plc})",
                              tuple(values.values()))
        except Exception:
            self.conn.rollback()

    def _fix_column_types(self) -> None:
        try:
            fixes = {
                "employees": {
                    "Дата медосмотра": "Годен до",
                    "Дата проведения": "Дата проведения",
                    "Статус": "Статус",
                },
                "violations": {
                    "Дата": "Годен до",
                    "Срок устранения": "Годен до",
                    "Статус": "Статус",
                },
                "custom_ledger": {
                    "Дата": "Годен до",
                    "Статус": "Статус",
                },
            }
            for cat, col_fixes in fixes.items():
                for col_name, expected_type in col_fixes.items():
                    cur = self.conn.execute(
                        "SELECT type FROM columns_config WHERE category=? AND name=?",
                        (cat, col_name))
                    row = cur.fetchone()
                    if row and row["type"] != expected_type:
                        self.conn.execute(
                            "UPDATE columns_config SET type=? WHERE category=? AND name=?",
                            (expected_type, cat, col_name))
            self.conn.commit()
        except Exception:
            self.conn.rollback()

    def _seed_defaults(self) -> None:
        try:
            self._seed_settings()
            self._seed_column_configs()
            self._seed_textbook()
            self._seed_templates()
            self._seed_admin_user()
            self._seed_companies()
            self._seed_employees()
            self._seed_violations()
            self._seed_print_templates()
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            self.log_event(f"Seed failed: {traceback.format_exc()}", "CRITICAL")

    def _seed_settings(self) -> None:
        defaults = {
            "app_language": AppConfig.DEFAULT_LANG,
            "theme": AppConfig.DEFAULT_THEME,
            "accent_color": AppConfig.DEFAULT_ACCENT,
            "tab_dashboard": I18n._("tab.dashboard"),
            "tab_employees": I18n._("tab.employees"),
            "tab_violations": I18n._("tab.violations"),
            "tab_companies": I18n._("tab.companies"),
            "tab_custom_ledger": I18n._("tab.custom_ledger"),
            "tab_statistics": I18n._("tab.statistics"),
            "tab_audit": I18n._("tab.audit"),
            "tab_ai": I18n._("tab.ai"),
            "tab_reminders": I18n._("tab.reminders"),
            "auto_save_interval": str(AppConfig.AUTO_SAVE_INTERVAL),
            "reminder_check_interval": str(AppConfig.REMINDER_CHECK_INTERVAL),
            "media_path": RUNTIME_PATHS.media_dir,
            "remember_me_token": "",
            "remember_me_expiry": "",
        }
        for k, v in defaults.items():
            self._insert_or_ignore("settings", {"key": k, "value": str(v)})

    def _seed_column_configs(self) -> None:
        configs: Dict[str, List[Tuple[str, str, int]]] = {
            "employees": [
                ("ID", "Число", 0), ("ФИО", "Текст", 1),
                ("Должность", "Текст", 2), ("Подразделение", "Текст", 3),
                ("Фирма", "Текст", 4), ("Телефон", "Текст", 5),
                ("Дата медосмотра", "Годен до", 6), ("Квалификация", "Текст", 7),
                ("Дата проведения", "Дата проведения", 8),
                ("Фото", "Медиа", 9), ("Статус", "Статус", 10),
            ],
            "violations": [
                ("ID", "Число", 0), ("Дата", "Годен до", 1),
                ("Фирма", "Текст", 2), ("Подразделение", "Текст", 3),
                ("Категория риска", "Текст", 4), ("Описание", "Текст", 5),
                ("Ответственный", "Текст", 6), ("Срок устранения", "Годен до", 7),
                ("Штраф", "Число", 8), ("Статус", "Статус", 9),
                ("Фото", "Медиа", 10),
            ],
            "custom_ledger": [
                ("ID", "Число", 0), ("Дата", "Годен до", 1),
                ("Категория", "Текст", 2), ("Описание", "Текст", 3),
                ("Ответственный", "Текст", 4), ("Статус", "Статус", 5),
                ("Фото", "Медиа", 6), ("Примечание", "Текст", 7),
            ],
        }
        for cat, cols in configs.items():
            for name, typ, pos in cols:
                self._insert_or_ignore("columns_config", {
                    "category": cat, "name": name, "type": typ, "position": pos,
                })

    def _seed_textbook(self) -> None:
        items = {
            "сиз": "Средства индивидуальной защиты должны применяться в соответствии "
                   "с требованиями охраны труда, утверждёнными работодателем. Работник "
                   "обязан использовать выданные средства по назначению, хранить их в "
                   "установленном месте и своевременно сообщать о повреждении или утрате.",
            "ограждение": "Ограждение опасных зон должно быть выполнено таким образом, "
                          "чтобы исключать несанкционированный доступ работников. Ограждения "
                          "должны быть устойчивыми, видимыми и сопровождаться "
                          "предупредительными знаками безопасности.",
            "инструктаж": "Инструктаж по охране труда проводится в установленном порядке "
                          "до допуска работника к самостоятельной работе. Факт проведения "
                          "инструктажа фиксируется в журнале с подписями инструктируемого "
                          "и инструктирующего лица.",
            "лоут": "Лист оценки условий труда используется для фиксации выявленных опасных "
                    "и вредных производственных факторов, а также для планирования "
                    "корректирующих мероприятий.",
            "журнал": "Журнал регистрации инструктажей является документом внутреннего "
                      "контроля и должен храниться в соответствии с установленными сроками "
                      "документооборота организации.",
            "пожар": "Пожарная безопасность: все работники должны знать пути эвакуации, "
                     "места расположения огнетушителей и планы действий при пожаре.",
            "электро": "Электробезопасность: работы с электрооборудованием должны "
                       "проводиться только обученным персоналом с соответствующей "
                       "группой допуска.",
            "высота": "Работы на высоте: обязательное применение страховочных систем, "
                      "предохранительных поясов и наличие наряда-допуска.",
        }
        for code, text in items.items():
            self._insert_or_ignore("textbook", {"short_code": code, "full_text": text})

    def _seed_templates(self) -> None:
        templates = [
            {
                "name": "Нарушение применения СИЗ",
                "data": {
                    "category": "Средства индивидуальной защиты",
                    "risk_level": "Средний",
                    "regulation": "Требования охраны труда по применению СИЗ",
                    "recommended_action": "Выдать средства защиты, провести повторный "
                                          "инструктаж, зафиксировать нарушение в журнале.",
                },
            },
            {
                "name": "Отсутствие ограждения",
                "data": {
                    "category": "Опасные зоны",
                    "risk_level": "Высокий",
                    "regulation": "Требования к ограждению опасных производственных зон",
                    "recommended_action": "Установить временное или постоянное ограждение "
                                          "опасной зоны, разместить предупреждающие знаки.",
                },
            },
            {
                "name": "Непроведение инструктажа",
                "data": {
                    "category": "Обучение и инструктаж",
                    "risk_level": "Высокий",
                    "regulation": "Требования к проведению инструктажей по охране труда",
                    "recommended_action": "Немедленно провести целевой инструктаж, внести "
                                          "запись в журнал, назначить ответственное лицо.",
                },
            },
            {
                "name": "Нарушение электробезопасности",
                "data": {
                    "category": "Электробезопасность",
                    "risk_level": "Высокий",
                    "regulation": "Правила устройства электроустановок (ПУЭ)",
                    "recommended_action": "Отстранить работника, провести внеочередную "
                                          "проверку знаний, устранить нарушение.",
                },
            },
            {
                "name": "Пожарная безопасность",
                "data": {
                    "category": "Пожарная безопасность",
                    "risk_level": "Критический",
                    "regulation": "Правила противопожарного режима в РФ",
                    "recommended_action": "Устранить нарушение, провести внеплановый "
                                          "противопожарный инструктаж.",
                },
            },
        ]
        for t in templates:
            self._insert_or_ignore("custom_templates", {
                "name": t["name"], "data_json": JsonUtils.dumps(t["data"]),
            })

    def _seed_admin_user(self) -> None:
        if self.fetch_one("SELECT id FROM users"):
            return
        pw_hash, salt = SecurityEngine.generate_hash("admin")
        self.conn.execute(
            "INSERT INTO users (username, password_hash, salt, role) VALUES (?, ?, ?, ?)",
            ("admin", pw_hash, salt, "Administrator"),
        )
        self.log_event("Default admin user created (admin/admin)", "WARNING")

    def _seed_companies(self) -> None:
        if self.fetch_one("SELECT id FROM companies"):
            return
        companies = [
            ("ООО ТехСтрой", "г. Москва, ул. Строителей, 15", "+7 (495) 123-45-67"),
            ("АО ПромБезопасность", "г. Санкт-Петербург, пр. Промышленный, 42",
             "+7 (812) 765-43-21"),
            ("ИП Иванов", "г. Новосибирск, ул. Рабочая, 8", "+7 (383) 987-65-43"),
        ]
        for name, addr, contact in companies:
            self.conn.execute(
                "INSERT INTO companies (name, address, contact) VALUES (?, ?, ?)",
                (name, addr, contact),
            )
        self.log_event("Demo companies seeded", "INFO")

    def _seed_employees(self) -> None:
        if self.fetch_one("SELECT id FROM employees"):
            return
        now = datetime.now()
        employees = [
            ("Иванов Иван Иванович", "Инженер по охране труда", "ОТиПБ",
             "ООО ТехСтрой", "+7 (495) 111-11-11",
             (now - timedelta(days=30)).strftime("%d.%m.%Y"),
             "5-й уровень", (now - timedelta(days=180)).strftime("%d.%m.%Y"), "Активен"),
            ("Петров Пётр Петрович", "Начальник цеха", "Цех №1",
             "ООО ТехСтрой", "+7 (495) 111-11-12",
             (now - timedelta(days=45)).strftime("%d.%m.%Y"),
             "4-й уровень", (now - timedelta(days=90)).strftime("%d.%m.%Y"), "Активен"),
            ("Сидоров Сидор Сидорович", "Электромонтёр", "Электроцех",
             "ООО ТехСтрой", "+7 (495) 111-11-13",
             (now - timedelta(days=320)).strftime("%d.%m.%Y"),
             "3-й уровень", (now - timedelta(days=60)).strftime("%d.%m.%Y"), "Активен"),
            ("Кузнецов Алексей Сергеевич", "Сварщик", "Цех №2",
             "ООО ТехСтрой", "+7 (495) 111-11-14",
             (now - timedelta(days=15)).strftime("%d.%m.%Y"),
             "4-й уровень", (now - timedelta(days=30)).strftime("%d.%m.%Y"), "Активен"),
            ("Смирнова Ольга Владимировна", "Бухгалтер", "Бухгалтерия",
             "ООО ТехСтрой", "+7 (495) 111-11-15",
             (now - timedelta(days=180)).strftime("%d.%m.%Y"),
             "5-й уровень", "", "Активен"),
            ("Васильев Дмитрий Андреевич", "Инспектор по охране труда", "ОТиПБ",
             "АО ПромБезопасность", "+7 (812) 222-22-21",
             (now - timedelta(days=10)).strftime("%d.%m.%Y"),
             "5-й уровень", (now - timedelta(days=45)).strftime("%d.%m.%Y"), "Активен"),
            ("Николаев Артём Павлович", "Начальник смены", "Смена №1",
             "АО ПромБезопасность", "+7 (812) 222-22-22",
             (now - timedelta(days=365)).strftime("%d.%m.%Y"),
             "4-й уровень", (now - timedelta(days=365)).strftime("%d.%m.%Y"), "Архив"),
            ("Козлова Елена Михайловна", "Химик-лаборант", "Лаборатория",
             "АО ПромБезопасность", "+7 (812) 222-22-23",
             (now - timedelta(days=200)).strftime("%d.%m.%Y"),
             "4-й уровень", (now - timedelta(days=120)).strftime("%d.%m.%Y"), "Активен"),
            ("Морозов Сергей Викторович", "Грузчик", "Склад",
             "АО ПромБезопасность", "+7 (812) 222-22-24",
             (now - timedelta(days=5)).strftime("%d.%m.%Y"),
             "2-й уровень", (now - timedelta(days=15)).strftime("%d.%m.%Y"), "Активен"),
            ("Фёдорова Анна Павловна", "Секретарь", "Администрация",
             "АО ПромБезопасность", "+7 (812) 222-22-25",
             (now - timedelta(days=90)).strftime("%d.%m.%Y"),
             "3-й уровень", "", "Активен"),
            ("Григорьев Илья Алексеевич", "Разнорабочий", "Производство",
             "ИП Иванов", "+7 (383) 333-33-31",
             (now - timedelta(days=60)).strftime("%d.%m.%Y"),
             "2-й уровень", (now - timedelta(days=10)).strftime("%d.%m.%Y"), "Активен"),
            ("Тимофеев Максим Денисович", "Водитель", "Транспорт",
             "ИП Иванов", "+7 (383) 333-33-32",
             (now - timedelta(days=365 + 30)).strftime("%d.%m.%Y"),
             "3-й уровень", (now - timedelta(days=200)).strftime("%d.%m.%Y"), "Активен"),
            ("Архипов Виктор Николаевич", "Кладовщик", "Склад",
             "ИП Иванов", "+7 (383) 333-33-33",
             (now - timedelta(days=25)).strftime("%d.%m.%Y"),
             "3-й уровень", (now - timedelta(days=90)).strftime("%d.%m.%Y"), "Активен"),
            ("Белова Татьяна Олеговна", "Уборщица", "Хоз. часть",
             "ИП Иванов", "+7 (383) 333-33-34",
             (now - timedelta(days=150)).strftime("%d.%m.%Y"),
             "1-й уровень", "", "Активен"),
            ("Дмитриев Константин Борисович", "Менеджер", "Офис",
             "ИП Иванов", "+7 (383) 333-33-35",
             (now - timedelta(days=45)).strftime("%d.%m.%Y"),
             "4-й уровень", (now - timedelta(days=30)).strftime("%d.%m.%Y"), "Активен"),
        ]
        for emp in employees:
            data = {
                "ФИО": emp[0], "Должность": emp[1], "Подразделение": emp[2],
                "Фирма": emp[3], "Телефон": emp[4], "Дата медосмотра": emp[5],
                "Квалификация": emp[6], "Дата проведения": emp[7], "Статус": emp[8],
                "Фото": [],
            }
            self.conn.execute("INSERT INTO employees (data_json) VALUES (?)",
                              (JsonUtils.dumps(data),))
        self.log_event("Demo employees seeded (15 records)", "INFO")

    def _seed_violations(self) -> None:
        if self.fetch_one("SELECT id FROM violations"):
            return
        now = datetime.now()
        violations = [
            ("10.01.2024", "ООО ТехСтрой", "Цех №1", "Средства индивидуальной защиты",
             "Работник находился на рабочем месте без защитной каски",
             "Петров Пётр Петрович",
             (now - timedelta(days=10)).strftime("%d.%m.%Y"), "5000", "Активно"),
            ("15.02.2024", "ООО ТехСтрой", "Цех №2", "Электробезопасность",
             "Неисправность заземления электрооборудования",
             "Кузнецов Алексей Сергеевич",
             (now + timedelta(days=20)).strftime("%d.%m.%Y"), "15000", "Активно"),
            ("20.03.2024", "АО ПромБезопасность", "Лаборатория", "Пожарная безопасность",
             "Загромождение путей эвакуации",
             "Козлова Елена Михайловна",
             (now - timedelta(days=5)).strftime("%d.%m.%Y"), "10000", "Активно"),
            ("05.04.2024", "АО ПромБезопасность", "Склад", "Опасные зоны",
             "Отсутствует ограждение опасной зоны погрузки",
             "Морозов Сергей Викторович",
             (now - timedelta(days=60)).strftime("%d.%m.%Y"), "20000", "Просрочено"),
            ("12.05.2024", "ИП Иванов", "Производство", "Обучение и инструктаж",
             "Не проведён инструктаж новому работнику",
             "Григорьев Илья Алексеевич",
             (now + timedelta(days=5)).strftime("%d.%m.%Y"), "8000", "Активно"),
            ("01.06.2024", "ИП Иванов", "Транспорт", "Средства индивидуальной защиты",
             "Отсутствие сигнального жилета у водителя",
             "Тимофеев Максим Денисович",
             (now - timedelta(days=90)).strftime("%d.%m.%Y"), "3000", "Исполнено"),
            ("15.06.2024", "ООО ТехСтрой", "ОТиПБ", "Документация",
             "Отсутствует журнал регистрации инструктажей",
             "Иванов Иван Иванович",
             (now + timedelta(days=45)).strftime("%d.%m.%Y"), "5000", "Активно"),
            ("20.07.2024", "АО ПромБезопасность", "Администрация", "Пожарная безопасность",
             "Не проведена проверка огнетушителей",
             "Фёдорова Анна Павловна",
             (now - timedelta(days=365)).strftime("%d.%m.%Y"), "7000", "Исполнено"),
        ]
        for v in violations:
            data = {
                "Дата": v[0], "Фирма": v[1], "Подразделение": v[2],
                "Категория риска": v[3], "Описание": v[4],
                "Ответственный": v[5], "Срок устранения": v[6],
                "Штраф": v[7], "Статус": v[8], "Фото": [],
            }
            self.conn.execute("INSERT INTO violations (data_json) VALUES (?)",
                              (JsonUtils.dumps(data),))
        self.log_event("Demo violations seeded (8 records)", "INFO")

    def _seed_print_templates(self) -> None:
        if self.fetch_one("SELECT id FROM print_templates"):
            return
        default_order_html = """<!DOCTYPE html>
<html lang="ru">
<head><meta charset="UTF-8">
<style>
body{font-family:'Segoe UI',Arial,sans-serif;margin:40px;color:#333;line-height:1.6}
h1{color:#1a237e;border-bottom:2px solid #1a237e;padding-bottom:10px;font-size:24px}
h2{color:#283593;font-size:18px;margin-top:30px}
.meta{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:20px 0;padding:15px;background:#f5f5f5;border-radius:6px}
.meta div{font-size:14px}
.label{color:#666;font-weight:600}
.content{margin:20px 0;padding:15px;border:1px solid #e0e0e0;border-radius:6px}
.photos{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:15px;margin-top:20px}
.photos img{width:100%;border-radius:4px;box-shadow:0 2px 8px rgba(0,0,0,.15)}
.footer{margin-top:40px;padding-top:15px;border-top:1px solid #e0e0e0;font-size:12px;color:#999;text-align:center}
</style></head>
<body>
<h1>ПРЕДПИСАНИЕ №{id}</h1>
<div class="meta">
<div><span class="label">Дата:</span> {date}</div>
<div><span class="label">Фирма:</span> {company}</div>
<div><span class="label">Ответственный:</span> {responsible}</div>
<div><span class="label">Срок устранения:</span> {deadline}</div>
</div>
<div class="content">
<h2>Описание нарушения</h2>
<p>{description}</p>
<h2>Рекомендуемые меры</h2>
<p>{recommended_action}</p>
{h2}<p>Сумма штрафа: <strong>{fine} руб.</strong></p>
</div>
{photos_section}
<div class="footer">{app_name} — Документ сформирован {generated_at}</div>
</body></html>"""

        default_report_html = """<!DOCTYPE html>
<html lang="ru">
<head><meta charset="UTF-8">
<style>
body{font-family:'Segoe UI',Arial,sans-serif;margin:40px;color:#333;line-height:1.6}
h1{color:#1a237e;border-bottom:2px solid #1a237e;padding-bottom:10px}
table{width:100%;border-collapse:collapse;margin:20px 0}
th{background:#1a237e;color:#fff;padding:10px;text-align:left;font-size:14px}
td{padding:8px 10px;border-bottom:1px solid #e0e0e0;font-size:13px}
tr:nth-child(even){background:#f5f5f5}
.summary{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:15px;margin:20px 0}
.card{padding:15px;background:#f5f5f5;border-radius:8px;text-align:center}
.card .value{font-size:28px;font-weight:700;color:#1a237e}
.card .label{font-size:12px;color:#666;margin-top:5px}
.footer{margin-top:40px;padding-top:15px;border-top:1px solid #e0e0e0;font-size:12px;color:#999;text-align:center}
</style></head>
<body>
<h1>ОТЧЁТ ПО ОХРАНЕ ТРУДА</h1>
<p><strong>Фирма:</strong> {company_name} | <strong>Дата:</strong> {date}</p>
<div class="summary">
<div class="card"><div class="value">{emp_count}</div><div class="label">Сотрудников</div></div>
<div class="card"><div class="value">{viol_count}</div><div class="label">Нарушений</div></div>
<div class="card"><div class="value">{fines_total} ₽</div><div class="label">Штрафов</div></div>
<div class="card"><div class="value">{overdue_count}</div><div class="label">Просрочено</div></div>
</div>
{table_html}
<div class="footer">{app_name} — Отчёт сформирован {generated_at}</div>
</body></html>"""

        self.conn.execute("""INSERT INTO print_templates (name, template_type, html_content, is_default)
            VALUES (?, ?, ?, 1)""", ("Стандартное предписание", "order", default_order_html))
        self.conn.execute("""INSERT INTO print_templates (name, template_type, html_content, is_default)
            VALUES (?, ?, ?, 1)""", ("Стандартный отчёт", "report", default_report_html))
        self.log_event("Default print templates seeded", "INFO")

    # -----------------------------------------------------------------------
    # GENERIC CRUD
    # -----------------------------------------------------------------------

    def execute(self, sql: str, params: Tuple[Any, ...] = ()) -> sqlite3.Cursor:
        with self._lock:
            try:
                return self.conn.execute(sql, params)
            except Exception:
                self.conn.rollback()
                self.log_event(f"SQL error: {traceback.format_exc()}", "CRITICAL")
                raise

    def commit(self) -> None:
        with self._lock:
            try:
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                self.log_event(f"Commit error: {traceback.format_exc()}", "CRITICAL")
                raise

    def rollback(self) -> None:
        with self._lock:
            try:
                self.conn.rollback()
            except Exception:
                self.log_event(f"Rollback error: {traceback.format_exc()}", "CRITICAL")

    def fetch_all(self, sql: str, params: Tuple[Any, ...] = ()) -> List[Dict[str, Any]]:
        with self._lock:
            try:
                return [dict(r) for r in self.conn.execute(sql, params).fetchall()]
            except Exception:
                self.conn.rollback()
                self.log_event(f"Fetch error: {traceback.format_exc()}", "CRITICAL")
                return []

    def fetch_one(self, sql: str, params: Tuple[Any, ...] = ()) -> Optional[Dict[str, Any]]:
        with self._lock:
            try:
                r = self.conn.execute(sql, params).fetchone()
                return dict(r) if r else None
            except Exception:
                self.conn.rollback()
                self.log_event(f"Fetch one error: {traceback.format_exc()}", "CRITICAL")
                return None

    # -----------------------------------------------------------------------
    # SETTINGS
    # -----------------------------------------------------------------------

    def upsert_setting(self, key: str, value: Any) -> None:
        try:
            self.conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, str(value)))
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            self.log_event(f"Setting upsert error: {traceback.format_exc()}", "CRITICAL")

    def get_setting(self, key: str, default: Any = None) -> Any:
        r = self.fetch_one("SELECT value FROM settings WHERE key=?", (key,))
        return r["value"] if r else default

    def get_all_settings(self) -> Dict[str, str]:
        rows = self.fetch_all("SELECT key, value FROM settings")
        return {r["key"]: r["value"] for r in rows}

    # -----------------------------------------------------------------------
    # AUDIT LOG
    # -----------------------------------------------------------------------

    def log_event(self, event: str, severity: str = "INFO",
                  details: Optional[Dict[str, Any]] = None,
                  username: str = "") -> None:
        try:
            self.conn.execute(
                "INSERT INTO audit_log (timestamp, event, severity, details, username) "
                "VALUES (?, ?, ?, ?, ?)",
                (datetime.now().isoformat(), event, severity,
                 JsonUtils.dumps(details or {}), username))
            self.conn.commit()
        except Exception:
            self.conn.rollback()

    def get_audit_events(self, limit: int = 500,
                         severity: Optional[str] = None) -> List[Dict[str, Any]]:
        if severity:
            return self.fetch_all(
                "SELECT * FROM audit_log WHERE severity=? ORDER BY id DESC LIMIT ?",
                (severity, limit))
        return self.fetch_all(
            "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))

    # -----------------------------------------------------------------------
    # JSON RECORD CRUD
    # -----------------------------------------------------------------------

    JSON_TABLES = {"employees", "violations", "custom_ledger"}

    def _validate_json_table(self, name: str) -> str:
        if name not in self.JSON_TABLES:
            raise ValueError(f"Unsupported JSON table: {name}")
        return name

    def find_violation_duplicate(self, data: Dict[str, Any], exclude_id: int = 0) -> Optional[Dict[str, Any]]:
        company = str(data.get("Фирма", "")).strip().lower()
        description = str(data.get("Описание", "")).strip().lower()
        if not company or not description:
            return None
        for rec in self.get_json_records("violations"):
            if exclude_id and int(rec.get("id", 0)) == int(exclude_id):
                continue
            dj = rec.get("data_json", {})
            if str(dj.get("Фирма", "")).strip().lower() != company:
                continue
            if str(dj.get("Описание", "")).strip().lower() != description:
                continue
            return rec
        return None

    def find_violation_duplicate(self, data: Dict[str, Any], exclude_id: int = 0,
                                 user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        company = str(data.get("Фирма", "")).strip().lower()
        description = str(data.get("Описание", "")).strip().lower()
        if not company or not description:
            return None
        for rec in self.get_json_records("violations", user_id=user_id):
            if exclude_id and int(rec.get("id", 0)) == int(exclude_id):
                continue
            dj = rec.get("data_json", {})
            if str(dj.get("Фирма", "")).strip().lower() != company:
                continue
            if str(dj.get("Описание", "")).strip().lower() != description:
                continue
            return rec
        return None

    def find_violation_duplicate(self, data: Dict[str, Any], exclude_id: int = 0,
                                 user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        date = str(data.get("Дата", "")).strip()
        if not date:
            return None
        company = str(data.get("Фирма", "")).strip().lower()
        department = str(data.get("Подразделение", "")).strip().lower()
        description = str(data.get("Описание", "")).strip().lower()
        for rec in self.get_json_records("violations", user_id=user_id):
            if exclude_id and int(rec.get("id", 0)) == int(exclude_id):
                continue
            dj = rec.get("data_json", {})
            if str(dj.get("Дата", "")).strip() != date:
                continue
            rec_company = str(dj.get("Фирма", "")).strip().lower()
            rec_department = str(dj.get("Подразделение", "")).strip().lower()
            rec_description = str(dj.get("Описание", "")).strip().lower()
            if company and rec_company and company != rec_company:
                continue
            if department and rec_department and department != rec_department:
                continue
            if description and rec_description and description != rec_description:
                continue
            return rec
        return None

    def get_import_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        rows = self.fetch_all(
            "SELECT * FROM import_history ORDER BY timestamp DESC LIMIT ?", (limit,))
        return [dict(r) for r in rows] if rows else []

    def merge_duplicates(self, table: str, user_id: Optional[int] = None) -> int:
        merged = 0
        if table == "employees":
            merged = self._merge_employees(user_id)
        elif table == "violations":
            merged = self._merge_violations(user_id)
        elif table == "custom_ledger":
            merged = self._merge_ledger(user_id)
        return merged

    def _merge_employees(self, user_id: Optional[int] = None) -> int:
        records = self.get_json_records("employees", user_id=user_id)
        seen: Dict[str, Dict[str, Any]] = {}
        for rec in records:
            dj = rec.get("data_json", {})
            key = (
                str(dj.get("ФИО", "")).strip().lower(),
                str(dj.get("Фирма", "")).strip().lower(),
                str(dj.get("Подразделение", "")).strip().lower(),
            )
            if key in seen:
                existing = seen[key]
                merged_data = dict(existing.get("data_json", {}))
                for k, v in dj.items():
                    if isinstance(v, list):
                        if v:
                            merged_data[k] = v
                    elif str(v).strip():
                        merged_data[k] = v
                self.save_json_record("employees", existing["id"], merged_data, user_id=user_id)
                self.delete_json_record("employees", rec["id"])
                merged += 1
            else:
                seen[key] = rec
        return merged

    def _merge_violations(self, user_id: Optional[int] = None) -> int:
        records = self.get_json_records("violations", user_id=user_id)
        seen: Dict[tuple, Dict[str, Any]] = {}
        for rec in records:
            dj = rec.get("data_json", {})
            key = (
                str(dj.get("Дата", "")).strip(),
                str(dj.get("Фирма", "")).strip().lower(),
                str(dj.get("Подразделение", "")).strip().lower(),
                str(dj.get("Описание", "")).strip().lower(),
            )
            if key in seen:
                existing = seen[key]
                merged_data = dict(existing.get("data_json", {}))
                for k, v in dj.items():
                    if isinstance(v, list):
                        if v:
                            merged_data[k] = v
                    elif str(v).strip():
                        merged_data[k] = v
                self.save_json_record("violations", existing["id"], merged_data, user_id=user_id)
                self.delete_json_record("violations", rec["id"])
                merged += 1
            else:
                seen[key] = rec
        return merged

    def _merge_ledger(self, user_id: Optional[int] = None) -> int:
        records = self.get_json_records("custom_ledger", user_id=user_id)
        seen: Dict[str, Dict[str, Any]] = {}
        for rec in records:
            dj = rec.get("data_json", {})
            key = (
                str(dj.get("Дата", "")).strip(),
                str(dj.get("Категория", "")).strip().lower(),
                str(dj.get("Описание", "")).strip().lower(),
            )
            if key in seen:
                existing = seen[key]
                merged_data = dict(existing.get("data_json", {}))
                for k, v in dj.items():
                    if isinstance(v, list):
                        if v:
                            merged_data[k] = v
                    elif str(v).strip():
                        merged_data[k] = v
                self.save_json_record("custom_ledger", existing["id"], merged_data, user_id=user_id)
                self.delete_json_record("custom_ledger", rec["id"])
                merged += 1
            else:
                seen[key] = rec
        return merged

    def save_json_record(self, table: str, record_id: int,
                         data: Dict[str, Any],
                         user_id: int = 0) -> int:
        self._validate_json_table(table)
        self.invalidate_cache(table)
        try:
            payload = JsonUtils.dumps(data)
            if record_id > 0:
                exists = self.fetch_one(f"SELECT id FROM {table} WHERE id=?", (record_id,))
                if exists:
                    self.conn.execute(
                        f"UPDATE {table} SET data_json=?, updated_at=datetime('now') "
                        f"WHERE id=?", (payload, record_id))
                    self.conn.commit()
                    self.log_event(f"Record updated in {table}", "INFO", {"id": record_id})
                    return record_id
            cur = self.conn.execute(
                f"INSERT INTO {table} (data_json, user_id) VALUES (?, ?)",
                (payload, user_id))
            self.conn.commit()
            new_id = int(cur.lastrowid)
            self.log_event(f"Record inserted in {table}", "INFO", {"id": new_id})
            return new_id
        except Exception:
            self.conn.rollback()
            self.log_event(f"Save record error: {traceback.format_exc()}", "CRITICAL")
            raise

    def get_json_records(self, table: str, limit: int = 2000,
                         user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        from time import time
        cache_key = f"records:{table}:{limit}:{user_id}"
        if cache_key in self._cache:
            ts, data = self._cache[cache_key]
            if time() - ts < 1.0:
                return data
        self._validate_json_table(table)
        if user_id:
            rows = self.fetch_all(
                f"SELECT id, data_json, created_at, updated_at, user_id "
                f"FROM {table} WHERE user_id=? OR user_id=0 ORDER BY id DESC LIMIT ?",
                (user_id, limit))
        else:
            rows = self.fetch_all(
                f"SELECT id, data_json, created_at, updated_at, user_id "
                f"FROM {table} ORDER BY id DESC LIMIT ?",
                (limit,))
        result: List[Dict[str, Any]] = []
        for r in rows:
            dj = JsonUtils.loads(r["data_json"])
            rec: Dict[str, Any] = {"id": r["id"], "data_json": dj}
            rec.update(dj)
            result.append(rec)
        self._cache[cache_key] = (time(), result)
        return result

    def get_json_record(self, table: str, record_id: int) -> Optional[Dict[str, Any]]:
        self._validate_json_table(table)
        r = self.fetch_one(
            f"SELECT id, data_json, created_at, updated_at FROM {table} WHERE id=?",
            (record_id,))
        if not r:
            return None
        dj = JsonUtils.loads(r["data_json"])
        rec: Dict[str, Any] = {"id": r["id"], "data_json": dj}
        rec.update(dj)
        return rec

    def delete_json_record(self, table: str, record_id: int) -> bool:
        self._validate_json_table(table)
        self.invalidate_cache(table)
        try:
            self.create_backup()
            self.conn.execute(f"DELETE FROM {table} WHERE id=?", (record_id,))
            self.conn.commit()
            self.log_event("Record deleted", "WARNING", {"table": table, "id": record_id})
            return True
        except Exception:
            self.conn.rollback()
            self.log_event(f"Delete error: {traceback.format_exc()}", "CRITICAL")
            return False

    # -----------------------------------------------------------------------
    # COLUMNS CONFIG
    # -----------------------------------------------------------------------

    def get_columns_config(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        from time import time
        cache_key = f"columns:{category or 'all'}"
        if cache_key in self._cache:
            ts, data = self._cache[cache_key]
            if time() - ts < 2.0:
                return data
        if category:
            result = self.fetch_all(
                "SELECT * FROM columns_config WHERE category=? ORDER BY position",
                (category,))
        else:
            result = self.fetch_all(
                "SELECT * FROM columns_config ORDER BY category, position")
        self._cache[cache_key] = (time(), result)
        return result

    def set_columns_config(self, category: str,
                           configs: List[Tuple[str, str, int]]) -> None:
        self.invalidate_cache(f"columns:{category}")
        try:
            self.create_backup()
            self.conn.execute("DELETE FROM columns_config WHERE category=?", (category,))
            for name, typ, pos in configs:
                self.conn.execute(
                    "INSERT INTO columns_config (category, name, type, position) "
                    "VALUES (?, ?, ?, ?)", (category, name, typ, pos))
            self.conn.commit()
            self.log_event(f"Columns config updated for {category}", "INFO")
        except Exception:
            self.conn.rollback()
            self.log_event(f"Columns config error: {traceback.format_exc()}", "CRITICAL")
            raise

    def rename_column(self, category: str, old_name: str,
                      new_name: str) -> bool:
        if not new_name or old_name == new_name:
            return False
        dup = self.fetch_one(
            "SELECT id FROM columns_config WHERE category=? AND name=?",
            (category, new_name))
        if dup:
            return False
        table_map = {"employees": "employees", "violations": "violations",
                     "custom_ledger": "custom_ledger"}
        table = table_map.get(category)
        if not table:
            return False
        try:
            self.create_backup()
            self.invalidate_cache(f"columns:{category}")
            self.conn.execute(
                "UPDATE columns_config SET name=? WHERE category=? AND name=?",
                (new_name, category, old_name))
            self._migrate_json_key(table, old_name, new_name)
            self.conn.commit()
            self.log_event("Column renamed", "INFO", {
                "category": category, "old": old_name, "new": new_name})
            return True
        except Exception:
            self.conn.rollback()
            self.log_event(f"Rename column error: {traceback.format_exc()}", "CRITICAL")
            return False

    def add_column(self, category: str, name: str, typ: str) -> bool:
        if not name:
            return False
        dup = self.fetch_one(
            "SELECT id FROM columns_config WHERE category=? AND name=?",
            (category, name))
        if dup:
            return False
        max_pos = self.fetch_one(
            "SELECT MAX(position) as mp FROM columns_config WHERE category=?",
            (category,))
        pos = (max_pos["mp"] + 1) if (max_pos is not None and max_pos["mp"] is not None) else 0
        try:
            self.invalidate_cache(f"columns:{category}")
            self.conn.execute(
                "INSERT INTO columns_config (category, name, type, position) "
                "VALUES (?, ?, ?, ?)", (category, name, typ, pos))
            self.conn.commit()
            self.log_event("Column added", "INFO", {"category": category, "name": name})
            return True
        except Exception:
            self.conn.rollback()
            self.log_event(f"Add column error: {traceback.format_exc()}", "CRITICAL")
            return False

    def delete_column(self, category: str, name: str) -> bool:
        try:
            self.create_backup()
            self.invalidate_cache(f"columns:{category}")
            self.conn.execute(
                "DELETE FROM columns_config WHERE category=? AND name=?",
                (category, name))
            table_map = {"employees": "employees", "violations": "violations",
                         "custom_ledger": "custom_ledger"}
            table = table_map.get(category)
            if table:
                rows = self.fetch_all(f"SELECT id, data_json FROM {table}")
                for r in rows:
                    dj = JsonUtils.loads(r["data_json"])
                    if name in dj:
                        del dj[name]
                        self.conn.execute(
                            f"UPDATE {table} SET data_json=? WHERE id=?",
                            (JsonUtils.dumps(dj), r["id"]))
            self.conn.commit()
            self.log_event("Column deleted with data migration", "WARNING",
                           {"category": category, "name": name})
            return True
        except Exception:
            self.conn.rollback()
            self.log_event(f"Delete column error: {traceback.format_exc()}", "CRITICAL")
            return False

    def _migrate_json_key(self, table: str, old_key: str, new_key: str) -> None:
        allowed = {"employees", "violations", "custom_ledger"}
        if table not in allowed:
            self.log_event(f"Invalid table name in _migrate_json_key: {table}", "CRITICAL")
            return
        rows = self.fetch_all(f"SELECT id, data_json FROM {table}")
        for r in rows:
            dj = JsonUtils.loads(r["data_json"])
            if old_key in dj:
                dj[new_key] = dj.pop(old_key)
                self.conn.execute(
                    f"UPDATE {table} SET data_json=? WHERE id=?",
                    (JsonUtils.dumps(dj), r["id"]))

    # -----------------------------------------------------------------------
    # COMPANIES
    # -----------------------------------------------------------------------

    def get_companies(self) -> List[Dict[str, Any]]:
        return self.fetch_all("SELECT * FROM companies ORDER BY name")

    def get_company(self, company_id: int) -> Optional[Dict[str, Any]]:
        return self.fetch_one("SELECT * FROM companies WHERE id=?", (company_id,))

    def save_company(self, name: str, address: str = "",
                     contact: str = "", data_json: Optional[Dict[str, Any]] = None,
                     company_id: int = 0) -> int:
        try:
            dj = JsonUtils.dumps(data_json or {})
            if company_id > 0:
                self.conn.execute(
                    "UPDATE companies SET name=?, address=?, contact=?, data_json=? "
                    "WHERE id=?", (name, address, contact, dj, company_id))
                self.conn.commit()
                return company_id
            cur = self.conn.execute(
                "INSERT INTO companies (name, address, contact, data_json) "
                "VALUES (?, ?, ?, ?)", (name, address, contact, dj))
            self.conn.commit()
            return int(cur.lastrowid)
        except Exception:
            self.conn.rollback()
            self.log_event(f"Company save error: {traceback.format_exc()}", "CRITICAL")
            raise

    def delete_company(self, company_id: int) -> bool:
        try:
            self.create_backup()
            self.conn.execute("DELETE FROM companies WHERE id=?", (company_id,))
            self.conn.commit()
            self.log_event("Company deleted", "WARNING", {"id": company_id})
            return True
        except Exception:
            self.conn.rollback()
            self.log_event(f"Delete company error: {traceback.format_exc()}", "CRITICAL")
            return False

    # -----------------------------------------------------------------------
    # NOTES
    # -----------------------------------------------------------------------

    def save_note(self, entity_type: str = "global", entity_id: int = 0,
                  title: str = "", content: str = "", note_id: int = 0) -> int:
        try:
            if note_id > 0:
                self.conn.execute(
                    "UPDATE notes SET title=?, content=?, updated_at=datetime('now') "
                    "WHERE id=?", (title, content, note_id))
                self.conn.commit()
                return note_id
            cur = self.conn.execute(
                "INSERT INTO notes (entity_type, entity_id, title, content) "
                "VALUES (?, ?, ?, ?)", (entity_type, entity_id, title, content))
            self.conn.commit()
            return int(cur.lastrowid)
        except Exception:
            self.conn.rollback()
            self.log_event(f"Note save error: {traceback.format_exc()}", "CRITICAL")
            raise

    def get_notes(self, entity_type: str = "global",
                  entity_id: int = 0) -> List[Dict[str, Any]]:
        if entity_type == "global":
            return self.fetch_all(
                "SELECT * FROM notes WHERE entity_type='global' ORDER BY updated_at DESC")
        return self.fetch_all(
            "SELECT * FROM notes WHERE entity_type=? AND entity_id=? "
            "ORDER BY updated_at DESC", (entity_type, entity_id))

    def delete_note(self, note_id: int) -> bool:
        try:
            self.conn.execute("DELETE FROM notes WHERE id=?", (note_id,))
            self.conn.commit()
            return True
        except Exception:
            self.conn.rollback()
            return False

    # -----------------------------------------------------------------------
    # REMINDERS
    # -----------------------------------------------------------------------

    def save_reminder(self, title: str, description: str, due_date: str,
                      check_interval: int = 60, is_done: int = 0,
                      reminder_id: int = 0) -> int:
        try:
            if reminder_id > 0:
                self.conn.execute(
                    "UPDATE reminders SET title=?, description=?, due_date=?, "
                    "check_interval=?, is_done=? WHERE id=?",
                    (title, description, due_date, check_interval, is_done, reminder_id))
                self.conn.commit()
                return reminder_id
            cur = self.conn.execute(
                "INSERT INTO reminders (title, description, due_date, check_interval) "
                "VALUES (?, ?, ?, ?)", (title, description, due_date, check_interval))
            self.conn.commit()
            return int(cur.lastrowid)
        except Exception:
            self.conn.rollback()
            self.log_event(f"Reminder save error: {traceback.format_exc()}", "CRITICAL")
            raise

    def get_reminders(self, include_done: bool = False) -> List[Dict[str, Any]]:
        if include_done:
            return self.fetch_all("SELECT * FROM reminders ORDER BY due_date")
        return self.fetch_all(
            "SELECT * FROM reminders WHERE is_done=0 ORDER BY due_date")

    def get_due_reminders(self) -> List[Dict[str, Any]]:
        return self.fetch_all(
            "SELECT * FROM reminders WHERE is_done=0 AND due_date <= ?",
            (datetime.now().isoformat()[:10],))

    def delete_reminder(self, reminder_id: int) -> bool:
        try:
            self.conn.execute("DELETE FROM reminders WHERE id=?", (reminder_id,))
            self.conn.commit()
            return True
        except Exception:
            self.conn.rollback()
            return False

    # -----------------------------------------------------------------------
    # TEMPLATES
    # -----------------------------------------------------------------------

    def get_templates(self) -> List[Dict[str, Any]]:
        rows = self.fetch_all("SELECT * FROM custom_templates ORDER BY name")
        for r in rows:
            r["data"] = JsonUtils.loads(r.get("data_json", "{}"))
        return rows

    # -----------------------------------------------------------------------
    # TEXTBOOK
    # -----------------------------------------------------------------------

    def get_textbook(self) -> Dict[str, str]:
        rows = self.fetch_all("SELECT short_code, full_text FROM textbook")
        return {r["short_code"]: r["full_text"] for r in rows}

    def save_textbook_entry(self, short_code: str, full_text: str) -> bool:
        try:
            self.conn.execute(
                "INSERT INTO textbook (short_code, full_text) VALUES (?, ?) "
                "ON CONFLICT(short_code) DO UPDATE SET full_text=excluded.full_text",
                (short_code, full_text))
            self.conn.commit()
            return True
        except Exception:
            self.conn.rollback()
            return False

    def delete_textbook_entry(self, short_code: str) -> bool:
        try:
            self.conn.execute("DELETE FROM textbook WHERE short_code=?", (short_code,))
            self.conn.commit()
            return True
        except Exception:
            self.conn.rollback()
            return False

    # -----------------------------------------------------------------------
    # PRINT TEMPLATES
    # -----------------------------------------------------------------------

    def get_print_templates(self, template_type: str = "order") -> List[Dict[str, Any]]:
        return self.fetch_all(
            "SELECT * FROM print_templates WHERE template_type=? ORDER BY is_default DESC",
            (template_type,))

    def get_all_print_templates(self) -> List[Dict[str, Any]]:
        return self.fetch_all(
            "SELECT * FROM print_templates ORDER BY is_default DESC, name")

    def save_print_template(self, name: str, template_type: str,
                            html_content: str, css_content: str = "",
                            template_id: int = 0) -> int:
        try:
            if template_id > 0:
                self.conn.execute(
                    "UPDATE print_templates SET name=?, html_content=?, css_content=? "
                    "WHERE id=?", (name, html_content, css_content, template_id))
                self.conn.commit()
                return template_id
            cur = self.conn.execute(
                "INSERT INTO print_templates (name, template_type, html_content, css_content) "
                "VALUES (?, ?, ?, ?)", (name, template_type, html_content, css_content))
            self.conn.commit()
            return int(cur.lastrowid)
        except Exception:
            self.conn.rollback()
            self.log_event(f"Print template error: {traceback.format_exc()}", "CRITICAL")
            raise

    # -----------------------------------------------------------------------
    # AI SETTINGS
    # -----------------------------------------------------------------------

    def get_ai_setting(self, key: str, default: str = "") -> str:
        r = self.fetch_one("SELECT value FROM ai_settings WHERE key=?", (key,))
        return r["value"] if r else default

    def set_ai_setting(self, key: str, value: str) -> None:
        try:
            self.conn.execute(
                "INSERT INTO ai_settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value))
            self.conn.commit()
        except Exception:
            self.conn.rollback()

    # -----------------------------------------------------------------------
    # CSV EXPORT
    # -----------------------------------------------------------------------

    def export_to_csv(self, table: str, file_path: Optional[str] = None) -> str:
        if not file_path:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_path = os.path.join(RUNTIME_PATHS.export_dir, f"{table}_{ts}.csv")
        records = self.get_json_records(table)
        fieldnames = ["id"]
        for r in records:
            for k in r:
                if k not in fieldnames:
                    fieldnames.append(k)
        with open(file_path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            for r in records:
                wr = {}
                for k in fieldnames:
                    v = r.get(k, "")
                    if isinstance(v, (list, dict)):
                        v = json.dumps(v, ensure_ascii=False)
                    wr[k] = v
                w.writerow(wr)
        self.log_event("CSV export completed", "INFO", {"table": table, "path": file_path})
        return file_path

    # -----------------------------------------------------------------------
    # BACKUP SYSTEM
    # -----------------------------------------------------------------------

    @staticmethod
    def sha256_file(file_path: str) -> str:
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()

    def create_backup(self) -> str:
        os.makedirs(RUNTIME_PATHS.backup_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        tmp = os.path.join(tempfile.gettempdir(), f"suot_backup_{ts}.db")
        zip_path = os.path.join(RUNTIME_PATHS.backup_dir, f"suot_backup_{ts}.zip")
        try:
            os.remove(tmp)
        except OSError:
            pass
        src = sqlite3.connect(self.database_path)
        dst = sqlite3.connect(tmp)
        with src:
            src.backup(dst)
        dst.close()
        src.close()
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.write(tmp, arcname=AppConfig.DB_NAME)
        os.remove(tmp)
        csum = self.sha256_file(zip_path)
        size_b = os.path.getsize(zip_path)
        self.conn.execute(
            "INSERT INTO backups (created_at, file_path, size_bytes, sha256) "
            "VALUES (?, ?, ?, ?)",
            (datetime.now().isoformat(), zip_path, size_b, csum))
        self.conn.commit()
        self.log_event("Backup created", "INFO", {
            "path": zip_path, "size": size_b, "sha256": csum})
        return zip_path

    def get_backups(self) -> List[Dict[str, Any]]:
        return self.fetch_all("SELECT * FROM backups ORDER BY created_at DESC")

    def restore_backup(self, backup_id: int) -> bool:
        try:
            bk = self.fetch_one("SELECT * FROM backups WHERE id=?", (backup_id,))
            if not bk:
                self.log_event("Backup not found", "ERROR", {"id": backup_id})
                return False
            zip_path = bk["file_path"]
            if not os.path.isfile(zip_path):
                self.log_event("Backup file missing", "ERROR", {"path": zip_path})
                return False
            expected = bk["sha256"]
            actual = self.sha256_file(zip_path)
            if expected != actual:
                self.log_event("Backup checksum mismatch", "CRITICAL",
                               {"expected": expected, "actual": actual})
                return False
            tmp = os.path.join(tempfile.gettempdir(), "suot_restore_tmp.db")
            with zipfile.ZipFile(zip_path, "r") as z:
                z.extract(AppConfig.DB_NAME, tempfile.gettempdir())
                extracted = os.path.join(tempfile.gettempdir(), AppConfig.DB_NAME)
                os.replace(extracted, tmp)
            self.conn.close()
            shutil.copy2(tmp, self.database_path)
            self.conn = sqlite3.connect(self.database_path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            self._configure_pragmas()
            os.remove(tmp)
            self.log_event("Database restored from backup", "WARNING",
                           {"backup_id": backup_id, "path": zip_path})
            return True
        except Exception:
            self.log_event(f"Restore error: {traceback.format_exc()}", "CRITICAL")
            return False

    def delete_backup(self, backup_id: int) -> bool:
        try:
            bk = self.fetch_one("SELECT * FROM backups WHERE id=?", (backup_id,))
            if bk:
                fp = bk["file_path"]
                if os.path.isfile(fp):
                    os.remove(fp)
                self.conn.execute("DELETE FROM backups WHERE id=?", (backup_id,))
                self.conn.commit()
                self.log_event("Backup deleted", "INFO", {"id": backup_id, "path": fp})
            return True
        except Exception:
            self.conn.rollback()
            self.log_event(f"Delete backup error: {traceback.format_exc()}", "CRITICAL")
            return False

    def _configure_pragmas(self) -> None:
        try:
            self.conn.execute("PRAGMA journal_mode=WAL;")
            self.conn.execute("PRAGMA synchronous=NORMAL;")
            self.conn.execute("PRAGMA foreign_keys=ON;")
            self.conn.execute("PRAGMA busy_timeout=5000;")
            self.conn.execute("PRAGMA cache_size=-8000;")
        except Exception:
            pass  # non-critical

    # -----------------------------------------------------------------------
    # STATISTICS HELPERS
    # -----------------------------------------------------------------------

    def get_statistics(self) -> Dict[str, Any]:
        emp_count = self.fetch_one("SELECT COUNT(*) as c FROM employees")
        viol_count = self.fetch_one("SELECT COUNT(*) as c FROM violations")
        comp_count = self.fetch_one("SELECT COUNT(*) as c FROM companies")
        now = datetime.now()
        overdue = 0
        fines_total = 0.0
        for v in self.get_json_records("violations"):
            dj = v.get("data_json", {})
            status = dj.get("Статус", "")
            deadline_str = dj.get("Срок устранения", "")
            if status == "Просрочено":
                overdue += 1
            elif status == "Активно" and deadline_str:
                try:
                    parts = deadline_str.split(".")
                    if len(parts) == 3:
                        dl = datetime(int(parts[2]), int(parts[1]), int(parts[0]))
                        if dl < now:
                            overdue += 1
                except Exception:
                    pass  # expected
            fine_str = str(dj.get("Штраф", "0")).replace(" ", "").replace(",", ".")
            try:
                fines_total += float(fine_str)
            except Exception:
                pass  # expected
        return {
            "employees_total": emp_count["c"] if emp_count else 0,
            "violations_total": viol_count["c"] if viol_count else 0,
            "companies_total": comp_count["c"] if comp_count else 0,
            "overdue_total": overdue,
            "fines_total": fines_total,
        }

    def close(self) -> None:
        try:
            self.conn.close()
        except Exception:
            pass  # non-critical


# ===========================================================================
# END OF PART 1 — BEGIN PART 2: UI Theme, Login, MainWindow, Dashboard
# ===========================================================================

# ---------------------------------------------------------------------------
# SECTION 2.1: Theme Engine (Light / Dark QSS with accent colors)
# ---------------------------------------------------------------------------

class ThemeEngine:
    _app: Optional[QApplication] = None
    _current_theme: str = "light"
    _current_accent: str = AppConfig.DEFAULT_ACCENT

    @classmethod
    def init(cls, app: QApplication) -> None:
        cls._app = app

    @classmethod
    def apply(cls, theme: Optional[str] = None,
              accent: Optional[str] = None) -> None:
        db = DatabaseManager()
        cls._current_theme = theme or db.get_setting("theme", "light")
        cls._current_accent = accent or db.get_setting("accent_color", AppConfig.DEFAULT_ACCENT)
        if cls._app:
            css = cls._build_dark() if cls._current_theme == "dark" else cls._build_light()
            cls._app.setStyleSheet(css)

    @classmethod
    def theme(cls) -> str:
        return cls._current_theme

    @classmethod
    def accent(cls) -> str:
        return cls._current_accent

    @staticmethod
    def _contrast_accent(hex_color: str) -> str:
        h = hex_color.lstrip('#')
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255
        return "#FFFFFF" if lum < 0.5 else "#1C1C1E"

    @staticmethod
    def _build_light() -> str:
        a = ThemeEngine._current_accent
        at = ThemeEngine._contrast_accent(a)
        t = "#1C1C1E"
        s = "#6C6C70"
        return f"""
        QMainWindow, QDialog, QWidget {{
            background-color: #F5F5F7; color: {t};
            font-family: -apple-system, "Segoe UI", "Helvetica Neue", Arial, sans-serif;
            font-size: 13px;
        }}
        QLabel {{
            color: {t}; background: transparent; border: none;
        }}
        QLabel[heading="true"] {{
            font-size: 22px; font-weight: 700; color: {t};
            padding: 6px 0; letter-spacing: -0.3px;
        }}
        QLabel[card_value="true"] {{
            font-size: 34px; font-weight: 700; color: {at};
            letter-spacing: -0.5px;
        }}
        QLabel[card_label="true"] {{
            font-size: 12px; color: {s}; font-weight: 500;
            letter-spacing: 0.3px;
        }}
        QLabel[status_green="true"] {{ color: #34C759; font-weight: 600; }}
        QLabel[status_yellow="true"] {{ color: #FF9500; font-weight: 600; }}
        QLabel[status_red="true"] {{ color: #FF3B30; font-weight: 600; }}
        QLabel[status_grey="true"] {{ color: {s}; font-weight: 600; }}

        QFrame {{
            border: none; background: transparent;
        }}
        QFrame[card="true"] {{
            background: rgba(255,255,255,0.85);
            border-radius: 14px;
            border: 1px solid rgba(0,0,0,0.06);
        }}
        QFrame[card_hover="true"]:hover {{
            background: rgba(255,255,255,0.95);
            border: 1px solid {a}66;
        }}

        QPushButton {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {a}, stop:1 {a}BB);
            color: {at}; border: none;
            border-radius: 10px; padding: 11px 26px; font-size: 13px;
            font-weight: 600; min-height: 18px;
        }}
        QPushButton:hover {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {a}, stop:1 {a}DD);
            border: 1px solid rgba(255,255,255,0.15);
        }}
        QPushButton:pressed {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {a}88, stop:1 {a}AA);
            padding-top: 13px; padding-bottom: 9px;
        }}
        QPushButton:disabled {{
            background: #E5E5EA; color: #C7C7CC;
        }}
        QPushButton[flat="true"] {{
            background: transparent; color: {at}; border: 1.5px solid {a}55;
            font-weight: 600;
        }}
        QPushButton[flat="true"]:hover {{
            background: {a}15; border: 1.5px solid {a};
        }}
        QPushButton[flat="true"]:pressed {{
            background: {a}25;
        }}
        QPushButton[small="true"] {{
            padding: 7px 16px; font-size: 12px; min-height: 14px;
            border-radius: 8px; font-weight: 600;
        }}

        QToolButton {{
            background: transparent; border: none; border-radius: 8px;
            padding: 6px 10px; color: {s}; font-size: 12px;
            font-weight: 500; min-height: 24px;
        }}
        QToolButton:hover {{
            background: {a}15; color: {at};
        }}
        QToolButton:checked {{
            background: {a}20; color: {at}; font-weight: 600;
        }}

        QLineEdit, QTextEdit, QPlainTextEdit {{
            background: rgba(255,255,255,0.9); color: {t};
            border: 1.5px solid #D2D2D7; border-radius: 10px;
            padding: 9px 14px; font-size: 13px;
            selection-background-color: {a}40;
        }}
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
            border: 1.5px solid {a};
            background: #FFFFFF;
        }}
        QLineEdit:disabled, QTextEdit:disabled {{
            background: #F0F0F5; color: #C7C7CC;
        }}

        QComboBox {{
            background: rgba(255,255,255,0.9); color: {t};
            border: 1.5px solid #D2D2D7; border-radius: 10px;
            padding: 8px 14px; font-size: 13px;
            min-height: 18px;
        }}
        QComboBox:hover, QComboBox:focus {{
            border: 1.5px solid {a};
        }}
        QComboBox::drop-down {{
            subcontrol-origin: padding; subcontrol-position: top right;
            width: 30px; border: none; border-left: 1px solid #E5E5EA;
            border-top-right-radius: 10px; border-bottom-right-radius: 10px;
        }}
        QComboBox QAbstractItemView {{
            background: rgba(255,255,255,0.98); color: {t};
            border: 1px solid #D2D2D7; border-radius: 10px;
            selection-background-color: {a}20;
            selection-color: {t}; outline: none;
            padding: 4px;
        }}

        QCheckBox, QRadioButton {{
            spacing: 8px; color: {t}; font-size: 13px;
        }}
        QCheckBox::indicator, QRadioButton::indicator {{
            width: 20px; height: 20px; border-radius: 5px;
            border: 1.5px solid #C7C7CC;
            background: rgba(255,255,255,0.9);
        }}
        QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
            background: {a}; border: 1.5px solid {a};
        }}
        QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
            border: 1.5px solid {a};
        }}
        QRadioButton::indicator {{ border-radius: 11px; }}

        QSpinBox, QDoubleSpinBox, QDateEdit, QTimeEdit, QDateTimeEdit {{
            background: rgba(255,255,255,0.9); color: {t};
            border: 1.5px solid #D2D2D7; border-radius: 10px;
            padding: 8px 14px; font-size: 13px; min-height: 18px;
        }}
        QSpinBox:focus, QDoubleSpinBox:focus, QDateEdit:focus {{
            border: 1.5px solid {a};
        }}

        QTableWidget {{
            background: #FFFFFF; color: {t};
            border: 1px solid #E5E5EA; border-radius: 12px;
            gridline-color: #F0F0F5;
            selection-background-color: {a}; selection-color: #FFFFFF;
            font-size: 13px; alternate-background-color: #FAFAFD;
        }}
        QTableWidget::item {{
            padding: 10px 14px; border-bottom: 1px solid #F0F0F5;
            min-height: 24px; color: {t};
        }}
        QTableWidget::item:hover {{ background: {a}15; }}
        QTableWidget::item:selected {{ background: {a}; color: #FFFFFF; }}
        QTableWidget::item:selected:!active {{ background: {a}CC; color: #FFFFFF; }}
        QHeaderView::section {{
            background: #F2F2F7; color: {s}; font-weight: 600;
            font-size: 12px; padding: 11px 14px; border: none;
            border-bottom: 1.5px solid #E5E5EA;
            border-right: 1.5px solid #E5E5EA; min-height: 26px;
        }}
        QHeaderView::section:last {{ border-right: none; }}
        QHeaderView::section:hover {{ background: #E8E8ED; color: {t}; }}
        QHeaderView::section:active {{ background: {a}15; color: {t}; }}

        QTabWidget::pane {{ border: none; background: transparent; }}
        QTabBar::tab {{
            background: transparent; color: {s}; font-size: 13px;
            font-weight: 500; padding: 12px 24px; border: none;
            border-bottom: 2.5px solid transparent; min-height: 20px;
        }}
        QTabBar::tab:hover {{
            color: {t}; background: rgba(0,0,0,0.04);
            border-radius: 8px 8px 0 0;
        }}
        QTabBar::tab:selected {{
            color: {at}; border-bottom: 2.5px solid {a};
        }}

        QScrollBar:vertical {{
            background: transparent; width: 6px; border-radius: 3px;
        }}
        QScrollBar::handle:vertical {{
            background: #C7C7CC; border-radius: 3px; min-height: 30px;
        }}
        QScrollBar::handle:vertical:hover {{ background: #AEAEB2; }}
        QScrollBar:horizontal {{
            background: transparent; height: 6px; border-radius: 3px;
        }}
        QScrollBar::handle:horizontal {{
            background: #C7C7CC; border-radius: 3px; min-width: 30px;
        }}
        QScrollBar::handle:horizontal:hover {{ background: #AEAEB2; }}

        QMenu {{
            background: rgba(255,255,255,0.97);
            color: {t}; border: 1px solid rgba(0,0,0,0.08);
            border-radius: 12px; padding: 6px;
        }}
        QMenu::item {{
            padding: 9px 36px 9px 18px; border-radius: 6px; font-size: 13px;
        }}
        QMenu::item:selected {{ background: {a}15; color: {at}; }}
        QMenu::separator {{
            height: 1px; background: #E5E5EA; margin: 4px 12px;
        }}

        QMenuBar {{
            background: rgba(255,255,255,0.9); color: {t};
            border-bottom: 1px solid #E5E5EA; padding: 2px;
        }}
        QMenuBar::item {{ padding: 7px 14px; border-radius: 6px; }}
        QMenuBar::item:selected {{ background: {a}15; }}

        QToolBar {{
            background: rgba(255,255,255,0.92);
            border: none; border-bottom: 1px solid #E5E5EA;
            padding: 4px 8px; spacing: 2px;
        }}

        QStatusBar {{
            background: rgba(255,255,255,0.92); color: {s};
            font-size: 12px;
            border-top: 1px solid #E5E5EA; padding: 3px 12px;
        }}

        QGroupBox {{
            font-weight: 600; font-size: 14px; color: {t};
            border: 1px solid #E5E5EA; border-radius: 12px;
            margin-top: 18px; padding: 18px 14px 14px 14px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin; subcontrol-position: top left;
            padding: 4px 12px; background: #F5F5F7;
            border-radius: 6px; left: 14px;
        }}

        QListWidget {{
            background: rgba(255,255,255,0.9); color: {t};
            border: 1px solid #E5E5EA; border-radius: 12px;
            padding: 4px; outline: none;
        }}
        QListWidget::item {{
            padding: 9px 14px; border-radius: 6px; margin: 2px 0;
        }}
        QListWidget::item:selected {{ background: {a}20; color: {t}; }}
        QListWidget::item:hover {{ background: {a}10; }}

        QScrollArea {{ border: none; background: transparent; }}
        QSplitter::handle {{ background: #E5E5EA; width: 1px; }}

        QToolTip {{
            background: rgba(0,0,0,0.85); color: #FFFFFF;
            font-size: 12px; border: none; border-radius: 8px;
            padding: 8px 14px;
        }}

        QMessageBox {{ background: rgba(255,255,255,0.97); }}
        QMessageBox QLabel {{ color: {t}; font-size: 13px; }}

        QProgressBar {{
            background: #E5E5EA; border: none; border-radius: 4px;
            height: 6px; text-align: center; font-size: 10px;
        }}
        QProgressBar::chunk {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 {a}, stop:1 {a}AA);
            border-radius: 4px;
        }}

        QTreeWidget {{
            background: #FFFFFF; color: {t};
            border: 1px solid #E5E5EA; border-radius: 10px;
            outline: none; alternate-background-color: #FAFAFD;
        }}
        QTreeWidget::item {{ padding: 7px 10px; border-radius: 5px; }}
        QTreeWidget::item:selected {{ background: {a}20; color: {t}; }}
        QTreeWidget::item:hover {{ background: {a}10; }}

        QTextBrowser {{
            background: #FFFFFF; color: {t};
            border: 1px solid #E5E5EA; border-radius: 10px;
            padding: 10px;
        }}

        QDialog {{ background: rgba(245,245,247,0.98); }}
        """

    @staticmethod
    def _build_dark() -> str:
        a = ThemeEngine._current_accent
        at = ThemeEngine._contrast_accent(a)
        t = "#F5F5F7"
        s = "#8E8E93"
        return f"""
        QMainWindow, QDialog, QWidget {{
            background-color: #000000; color: {t};
            font-family: -apple-system, "Segoe UI", "Helvetica Neue", Arial, sans-serif;
            font-size: 13px;
        }}
        QLabel {{
            color: {t}; background: transparent; border: none;
        }}
        QLabel[heading="true"] {{
            font-size: 22px; font-weight: 700; color: #FFFFFF;
            padding: 6px 0; letter-spacing: -0.3px;
        }}
        QLabel[card_value="true"] {{
            font-size: 34px; font-weight: 700; color: {at};
            letter-spacing: -0.5px;
        }}
        QLabel[card_label="true"] {{
            font-size: 12px; color: {s}; font-weight: 500;
            letter-spacing: 0.3px;
        }}
        QLabel[status_green="true"] {{ color: #30D158; font-weight: 600; }}
        QLabel[status_yellow="true"] {{ color: #FF9F0A; font-weight: 600; }}
        QLabel[status_red="true"] {{ color: #FF453A; font-weight: 600; }}
        QLabel[status_grey="true"] {{ color: {s}; font-weight: 600; }}

        QFrame {{
            border: none; background: transparent;
        }}
        QFrame[card="true"] {{
            background: rgba(28,28,30,0.85);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 14px;
        }}
        QFrame[card_hover="true"]:hover {{
            background: rgba(44,44,46,0.9);
            border: 1px solid {a}88;
        }}

        QPushButton {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {a}, stop:1 {a}BB);
            color: {at}; border: none;
            border-radius: 10px; padding: 11px 26px; font-size: 13px;
            font-weight: 600; min-height: 18px;
        }}
        QPushButton:hover {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {a}, stop:1 {a}DD);
            border: 1px solid rgba(255,255,255,0.15);
        }}
        QPushButton:pressed {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {a}88, stop:1 {a}AA);
            padding-top: 13px; padding-bottom: 9px;
        }}
        QPushButton:disabled {{
            background: #3A3A3C; color: #636366;
        }}
        QPushButton[flat="true"] {{
            background: transparent; color: {at}; border: 1.5px solid {a}55;
            font-weight: 600;
        }}
        QPushButton[flat="true"]:hover {{
            background: {a}22; border: 1.5px solid {a};
        }}
        QPushButton[flat="true"]:pressed {{
            background: {a}30;
        }}
        QPushButton[small="true"] {{
            padding: 7px 16px; font-size: 12px; min-height: 14px;
            border-radius: 8px; font-weight: 600;
        }}

        QToolButton {{
            background: transparent; border: none; border-radius: 8px;
            padding: 6px 10px; color: {s}; font-size: 12px;
            font-weight: 500;
        }}
        QToolButton:hover {{
            background: {a}22; color: {at};
        }}
        QToolButton:checked {{
            background: {a}30; color: {at}; font-weight: 600;
        }}

        QLineEdit, QTextEdit, QPlainTextEdit {{
            background: rgba(28,28,30,0.9); color: {t};
            border: 1.5px solid #3A3A3C; border-radius: 10px;
            padding: 9px 14px; font-size: 13px;
            selection-background-color: {a}40;
        }}
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
            border: 1.5px solid {a};
            background: rgba(44,44,46,0.95);
        }}
        QLineEdit:disabled, QTextEdit:disabled {{
            background: #1C1C1E; color: #636366;
        }}

        QComboBox {{
            background: rgba(28,28,30,0.9); color: {t};
            border: 1.5px solid #3A3A3C; border-radius: 10px;
            padding: 8px 14px; font-size: 13px;
            min-height: 18px;
        }}
        QComboBox:hover, QComboBox:focus {{
            border: 1.5px solid {a};
        }}
        QComboBox::drop-down {{
            subcontrol-origin: padding; subcontrol-position: top right;
            width: 30px; border: none; border-left: 1px solid #3A3A3C;
            border-top-right-radius: 10px; border-bottom-right-radius: 10px;
        }}
        QComboBox QAbstractItemView {{
            background: rgba(28,28,30,0.98); color: {t};
            border: 1px solid #3A3A3C; border-radius: 10px;
            selection-background-color: {a}30;
            selection-color: {t}; outline: none;
            padding: 4px;
        }}

        QCheckBox, QRadioButton {{
            spacing: 8px; color: {t}; font-size: 13px;
        }}
        QCheckBox::indicator, QRadioButton::indicator {{
            width: 20px; height: 20px; border-radius: 5px;
            border: 1.5px solid #636366;
            background: rgba(28,28,30,0.9);
        }}
        QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
            background: {a}; border: 1.5px solid {a};
        }}
        QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
            border: 1.5px solid {a};
        }}
        QRadioButton::indicator {{
            border-radius: 11px;
        }}

        QSpinBox, QDoubleSpinBox, QDateEdit, QTimeEdit, QDateTimeEdit {{
            background: rgba(28,28,30,0.9); color: {t};
            border: 1.5px solid #3A3A3C; border-radius: 10px;
            padding: 8px 14px; font-size: 13px;
            min-height: 18px;
        }}
        QSpinBox:focus, QDoubleSpinBox:focus, QDateEdit:focus {{
            border: 1.5px solid {a};
        }}
        QSpinBox::up-button, QDoubleSpinBox::up-button,
        QDateEdit::up-button, QTimeEdit::up-button {{
            subcontrol-origin: border; subcontrol-position: top right;
            width: 26px; border-left: 1px solid #3A3A3C;
            border-top-right-radius: 10px;
        }}
        QSpinBox::down-button, QDoubleSpinBox::down-button,
        QDateEdit::down-button, QTimeEdit::down-button {{
            subcontrol-origin: border; subcontrol-position: bottom right;
            width: 26px; border-left: 1px solid #3A3A3C;
            border-bottom-right-radius: 10px;
        }}

        QTableWidget {{
            background: #1C1C1E; color: {t};
            border: 1px solid #2C2C2E; border-radius: 12px;
            gridline-color: #2C2C2E;
            selection-background-color: {a}; selection-color: #FFFFFF;
            font-size: 13px; alternate-background-color: #222224;
        }}
        QTableWidget::item {{
            padding: 10px 14px; border-bottom: 1px solid #2C2C2E;
            min-height: 24px;
            color: {t};
        }}
        QTableWidget::item:hover {{
            background: {a}25;
        }}
        QTableWidget::item:selected {{
            background: {a}; color: #FFFFFF;
        }}
        QTableWidget::item:selected:!active {{
            background: {a}CC; color: #FFFFFF;
        }}
        QHeaderView::section {{
            background: #1C1C1E; color: {s}; font-weight: 600;
            font-size: 12px; padding: 11px 14px; border: none;
            border-bottom: 1.5px solid #2C2C2E;
            border-right: 1.5px solid #2C2C2E; min-height: 26px;
        }}
        QHeaderView::section:last {{ border-right: none; }}
        QHeaderView::section:hover {{
            background: #2C2C2E; color: {t};
        }}
        QHeaderView::section:active {{
            background: {a}20; color: {t};
        }}

        QTabWidget::pane {{
            border: none; background: transparent;
        }}
        QTabBar::tab {{
            background: transparent; color: {s}; font-size: 13px;
            font-weight: 500; padding: 12px 24px; border: none;
            border-bottom: 2.5px solid transparent;
            min-height: 20px;
        }}
        QTabBar::tab:hover {{
            color: {t}; background: rgba(255,255,255,0.06);
            border-radius: 8px 8px 0 0;
        }}
        QTabBar::tab:selected {{
            color: {at}; border-bottom: 2.5px solid {a};
        }}

        QScrollBar:vertical {{
            background: transparent; width: 6px; border-radius: 3px;
        }}
        QScrollBar::handle:vertical {{
            background: #48484A; border-radius: 3px; min-height: 30px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: #636366;
        }}
        QScrollBar:horizontal {{
            background: transparent; height: 6px; border-radius: 3px;
        }}
        QScrollBar::handle:horizontal {{
            background: #48484A; border-radius: 3px; min-width: 30px;
        }}
        QScrollBar::handle:horizontal:hover {{
            background: #636366;
        }}

        QMenu {{
            background: rgba(28,28,30,0.97);
            color: {t}; border: 1px solid rgba(255,255,255,0.08);
            border-radius: 12px; padding: 6px;
        }}
        QMenu::item {{
            padding: 9px 36px 9px 18px; border-radius: 6px; font-size: 13px;
        }}
        QMenu::item:selected {{
            background: {a}28; color: {at};
        }}
        QMenu::separator {{
            height: 1px; background: #3A3A3C; margin: 4px 12px;
        }}

        QMenuBar {{
            background: rgba(28,28,30,0.95); color: {t};
            border-bottom: 1px solid #2C2C2E; padding: 2px;
        }}
        QMenuBar::item {{
            padding: 7px 14px; border-radius: 6px;
        }}
        QMenuBar::item:selected {{
            background: {a}22;
        }}

        QToolBar {{
            background: rgba(28,28,30,0.95);
            border: none; border-bottom: 1px solid #2C2C2E;
            padding: 4px 8px; spacing: 2px;
        }}

        QStatusBar {{
            background: rgba(28,28,30,0.95); color: {s};
            font-size: 12px;
            border-top: 1px solid #2C2C2E; padding: 3px 12px;
        }}

        QGroupBox {{
            font-weight: 600; font-size: 14px; color: {t};
            border: 1px solid #2C2C2E; border-radius: 12px;
            margin-top: 18px; padding: 18px 14px 14px 14px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin; subcontrol-position: top left;
            padding: 4px 12px; background: #000000;
            border-radius: 6px; left: 14px;
        }}

        QListWidget {{
            background: rgba(28,28,30,0.9); color: {t};
            border: 1px solid #2C2C2E; border-radius: 12px;
            padding: 4px; outline: none;
        }}
        QListWidget::item {{
            padding: 9px 14px; border-radius: 6px; margin: 2px 0;
        }}
        QListWidget::item:selected {{
            background: {a}30; color: {t};
        }}
        QListWidget::item:hover {{
            background: {a}15;
        }}

        QScrollArea {{
            border: none; background: transparent;
        }}

        QSplitter::handle {{
            background: #2C2C2E; width: 1px;
        }}

        QToolTip {{
            background: rgba(0,0,0,0.9); color: {t};
            font-size: 12px; border: 1px solid #3A3A3C;
            border-radius: 8px; padding: 8px 14px;
        }}

        QMessageBox {{
            background: rgba(28,28,30,0.97);
        }}
        QMessageBox QLabel {{
            color: {t}; font-size: 13px;
        }}

        QProgressBar {{
            background: #2C2C2E; border: none; border-radius: 4px;
            height: 6px; text-align: center; font-size: 10px;
        }}
        QProgressBar::chunk {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 {a}, stop:1 {a}AA);
            border-radius: 4px;
        }}

        QTreeWidget {{
            background: #1C1C1E; color: {t};
            border: 1px solid #2C2C2E; border-radius: 10px;
            outline: none; alternate-background-color: #222224;
        }}
        QTreeWidget::item {{
            padding: 7px 10px; border-radius: 5px;
        }}
        QTreeWidget::item:selected {{
            background: {a}30; color: {t};
        }}
        QTreeWidget::item:hover {{
            background: {a}15;
        }}

        QTextBrowser {{
            background: #1C1C1E; color: {t};
            border: 1px solid #2C2C2E; border-radius: 10px;
            padding: 10px;
        }}

        QDialog {{
            background: rgba(0,0,0,0.98);
        }}
        """


# ---------------------------------------------------------------------------
# SECTION 2.2: Toast Notification Widget
# ---------------------------------------------------------------------------

class ToastNotification(QFrame):
    _instance: Optional["ToastNotification"] = None
    _active_toasts: List["ToastNotification"] = []

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                            | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self._timeout = 5000
        self._opacity = 0.98
        self._build_ui()

    def _build_ui(self) -> None:
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(16, 12, 16, 12)
        self._layout.setSpacing(10)

        self._icon_label = QLabel()
        self._icon_label.setFixedSize(20, 20)
        self._icon_label.setAlignment(Qt.AlignCenter)
        self._layout.addWidget(self._icon_label)

        self._text_label = QLabel()
        self._text_label.setWordWrap(True)
        self._text_label.setMaximumWidth(320)
        self._layout.addWidget(self._text_label)

        self.setFixedWidth(380)

    def _apply_style(self, toast_type: str) -> None:
        colors = {
            "info": ("#2196F3", "#E3F2FD"),
            "success": ("#27AE60", "#E8F5E9"),
            "warning": ("#F39C12", "#FFF8E1"),
            "error": ("#E74C3C", "#FFEBEE"),
        }
        border_c, bg = colors.get(toast_type, colors["info"])
        is_dark = ThemeEngine._current_theme == "dark"
        text_color = "#E0E0E8" if is_dark else "#2C3E50"
        if is_dark:
            bg = "#2A2B45"
            border_c = colors.get(toast_type, ("#55557A",))[0]
        self.setStyleSheet(f"""
            ToastNotification {{
                background: {bg}; border: 1px solid {border_c};
                border-radius: 10px;
            }}
            QLabel {{ color: {text_color}; font-size: 13px; background: transparent; }}
        """)

    def show_toast(self, message: str, toast_type: str = "info",
                   timeout: int = 5000) -> None:
        self._timeout = timeout
        self._text_label.setText(message)
        self._apply_style(toast_type)
        icons = {
            "info": "ℹ", "success": "✓", "warning": "⚠", "error": "✕",
        }
        self._icon_label.setText(icons.get(toast_type, "ℹ"))
        self.adjustSize()
        self._position_toast()
        self.show()
        QTimer.singleShot(self._timeout, self._fade_out)

    def _position_toast(self) -> None:
        desktop = QApplication.primaryScreen().availableGeometry()
        offset_y = 20
        for t in ToastNotification._active_toasts:
            if t is not self and t.isVisible():
                offset_y += t.height() + 10
        x = desktop.width() - self.width() - 20
        y = desktop.y() + 20 + offset_y
        self.move(x, y)
        if self not in ToastNotification._active_toasts:
            ToastNotification._active_toasts.append(self)

    def _fade_out(self) -> None:
        self.anim = QPropertyAnimation(self, b"windowOpacity")
        self.anim.setDuration(300)
        self.anim.setStartValue(self.windowOpacity())
        self.anim.setEndValue(0.0)
        self.anim.finished.connect(self._close_toast)
        self.anim.start(QPropertyAnimation.DeleteWhenStopped)

    def _close_toast(self) -> None:
        if self in ToastNotification._active_toasts:
            ToastNotification._active_toasts.remove(self)
        self.close()

    @classmethod
    def notify(cls, message: str, toast_type: str = "info",
               timeout: int = 5000) -> None:
        toast = cls()
        toast.show_toast(message, toast_type, timeout)


# ---------------------------------------------------------------------------
# SECTION 2.3: Login Dialog with Shake Animation
# ---------------------------------------------------------------------------

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
        self.setFixedSize(400, 460)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        main = QVBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)

        container = QFrame()
        container.setObjectName("loginContainer")
        container.setStyleSheet(f"""
            QFrame#loginContainer {{
                background: {"#FFFFFF" if ThemeEngine._current_theme == "light" else "#252640"};
                border-radius: 16px; margin: 20px;
            }}
        """)
        cl = QVBoxLayout(container)
        cl.setContentsMargins(32, 32, 32, 32)
        cl.setSpacing(16)

        title = QLabel(I18n._("app.name"))
        title.setProperty("heading", True)
        title.setAlignment(Qt.AlignCenter)
        cl.addWidget(title)

        subtitle = QLabel(I18n._("login.title"))
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("font-size: 13px; margin-bottom: 8px;")
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


# ---------------------------------------------------------------------------
# SECTION 2.4: Safety Score Gauge (QPainter Custom Widget)
# ---------------------------------------------------------------------------

class SafetyScoreGauge(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._score: float = 75.0
        self.setMinimumSize(200, 200)
        self.setMaximumSize(400, 400)

    def set_score(self, score: float) -> None:
        self._score = max(0.0, min(100.0, score))
        self.update()

    def paintEvent(self, event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        w = self.width()
        h = self.height()
        side = min(w, h)
        margin = 20
        gauge_rect = QRect((w - side) // 2 + margin, (h - side) // 2 + margin,
                           side - margin * 2, side - margin * 2)
        cx = gauge_rect.center().x()
        cy = gauge_rect.center().y() + gauge_rect.height() * 0.1
        radius = min(gauge_rect.width(), gauge_rect.height()) * 0.42

        # Background arc
        pen_bg = QPen(QColor("#E8ECF1" if ThemeEngine._current_theme == "light"
                              else "#333458"), radius * 0.18)
        pen_bg.setCapStyle(Qt.RoundCap)
        painter.setPen(pen_bg)
        painter.drawArc(QRect(int(cx - radius), int(cy - radius),
                              int(radius * 2), int(radius * 2)),
                        180 * 16, 180 * 16)

        # Score arc (0-100 maps to 0-180 degrees)
        angle = int(180.0 * self._score / 100.0)
        score_color = QColor("#27AE60") if self._score >= 70 else (
            QColor("#F39C12") if self._score >= 40 else QColor("#E74C3C"))
        pen_score = QPen(score_color, radius * 0.18)
        pen_score.setCapStyle(Qt.RoundCap)
        painter.setPen(pen_score)
        painter.drawArc(QRect(int(cx - radius), int(cy - radius),
                              int(radius * 2), int(radius * 2)),
                        180 * 16, -angle * 16)

        # Tick marks and labels
        painter.setPen(QPen(QColor("#95A5A6" if ThemeEngine._current_theme == "light"
                                   else "#8888A0"), 1))
        font = QFont("Segoe UI", 9)
        painter.setFont(font)
        for i in range(0, 101, 10):
            rad = math.radians(180 - 180.0 * i / 100.0)
            inner_r = radius * 0.75
            outer_r = radius * 0.85
            tick_len = radius * 0.12 if i % 20 == 0 else radius * 0.07
            x1 = cx + inner_r * math.cos(rad)
            y1 = cy - inner_r * math.sin(rad)
            x2 = cx + (inner_r + tick_len) * math.cos(rad)
            y2 = cy - (inner_r + tick_len) * math.sin(rad)
            painter.drawLine(QPoint(int(x1), int(y1)), QPoint(int(x2), int(y2)))

            if i % 20 == 0:
                label_r = radius * 0.58
                lx = cx + label_r * math.cos(rad)
                ly = cy - label_r * math.sin(rad)
                painter.drawText(QRect(int(lx) - 15, int(ly) - 10, 30, 20),
                                 Qt.AlignCenter, str(i))

        # Needle
        needle_rad = math.radians(180 - 180.0 * self._score / 100.0)
        needle_len = radius * 0.65
        nx = cx + needle_len * math.cos(needle_rad)
        ny = cy - needle_len * math.sin(needle_rad)
        painter.setPen(QPen(score_color, 3, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(int(cx), int(cy), int(nx), int(ny))

        # Center circle
        painter.setBrush(score_color)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(int(cx), int(cy), int(radius * 0.08), int(radius * 0.08))

        # Score text
        font_big = QFont("Segoe UI", 28, QFont.Bold)
        painter.setFont(font_big)
        painter.setPen(QColor("#2C3E50" if ThemeEngine._current_theme == "light"
                              else "#E0E0E8"))
        score_text = f"{self._score:.0f}%"
        painter.drawText(QRect(int(cx) - 60, int(cy) + int(radius * 0.35),
                               120, 40), Qt.AlignCenter, score_text)

        # Label below score
        font_small = QFont("Segoe UI", 10)
        painter.setFont(font_small)
        painter.setPen(QColor("#95A5A6" if ThemeEngine._current_theme == "light"
                              else "#8888A0"))
        painter.drawText(QRect(int(cx) - 90, int(cy) + int(radius * 0.35) + 36,
                               180, 22), Qt.AlignCenter, I18n._("stat.safety_score"))

        painter.end()


# ---------------------------------------------------------------------------
# SECTION 2.5: KPI Card Widget
# ---------------------------------------------------------------------------

class KpiCard(QFrame):
    def __init__(self, title: str, value: str, color: str,
                 icon: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setProperty("card", True)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self._color = color
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(6)

        header = QHBoxLayout()
        if icon:
            icon_label = QLabel(icon)
            icon_label.setStyleSheet(f"font-size: 22px; color: {color};")
            header.addWidget(icon_label)
        header.addStretch()

        self._value_label = QLabel(str(value))
        self._value_label.setProperty("card_value", True)
        self._value_label.setStyleSheet(f"color: {color}; font-size: 30px; font-weight: 700;")

        self._title_label = QLabel(title)
        self._title_label.setProperty("card_label", True)
        self._title_label.setWordWrap(True)

        layout.addLayout(header)
        layout.addWidget(self._value_label)
        layout.addWidget(self._title_label)

    def setText(self, value: str) -> None:
        self._value_label.setText(str(value))

    def setTitle(self, title: str) -> None:
        self._title_label.setText(title)


# ---------------------------------------------------------------------------
# SECTION 2.6: Dashboard Tab
# ---------------------------------------------------------------------------

class DashboardTab(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.db = DatabaseManager()
        self._build_ui()
        self._refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(20)

        heading = QLabel(I18n._("tab.dashboard"))
        heading.setProperty("heading", True)
        layout.addWidget(heading)

        self._cards_layout = QHBoxLayout()
        self._cards_layout.setSpacing(16)
        layout.addLayout(self._cards_layout)

        body = QHBoxLayout()
        body.setSpacing(20)

        gauge_widget = QFrame()
        gauge_widget.setProperty("card", True)
        gauge_layout = QVBoxLayout(gauge_widget)
        gauge_layout.setContentsMargins(16, 16, 16, 16)
        self._gauge = SafetyScoreGauge()
        gauge_layout.addWidget(self._gauge, 0, Qt.AlignCenter)
        body.addWidget(gauge_widget, 2)

        stats_widget = QFrame()
        stats_widget.setProperty("card", True)
        stats_layout = QVBoxLayout(stats_widget)
        stats_layout.setContentsMargins(16, 16, 16, 16)
        stats_layout.setSpacing(12)
        stats_heading = QLabel(I18n._("stat.title"))
        stats_heading.setProperty("heading", True)
        stats_heading.setStyleSheet("font-size: 16px;")
        stats_layout.addWidget(stats_heading)
        self._stats_labels: Dict[str, QLabel] = {}
        stat_items = [
            ("stat.employees_total", "👤", "#2196F3"),
            ("stat.violations_total", "⚠", "#E74C3C"),
            ("stat.companies_total", "🏢", "#27AE60"),
            ("stat.overdue_total", "⏰", "#F39C12"),
            ("stat.fines_total", "💰", "#9C27B0"),
        ]
        for key, icon, color in stat_items:
            row = QHBoxLayout()
            row.setSpacing(10)
            icon_lbl = QLabel(icon)
            icon_lbl.setStyleSheet(f"font-size: 18px;")
            row.addWidget(icon_lbl)
            val = QLabel("—")
            val.setStyleSheet(f"font-size: 18px; font-weight: 600; color: {color};")
            row.addWidget(val)
            lbl = QLabel(I18n._(key))
            lbl.setStyleSheet("font-size: 13px;")
            row.addWidget(lbl)
            row.addStretch()
            stats_layout.addLayout(row)
            self._stats_labels[key] = val
        stats_layout.addStretch()
        body.addWidget(stats_widget, 3)
        layout.addLayout(body)

        recent_widget = QFrame()
        recent_widget.setProperty("card", True)
        recent_layout = QVBoxLayout(recent_widget)
        recent_layout.setContentsMargins(16, 16, 16, 16)
        recent_layout.setSpacing(8)
        recent_heading = QLabel(I18n._("dashboard.recent"))
        recent_heading.setProperty("heading", True)
        recent_heading.setStyleSheet("font-size: 16px;")
        recent_layout.addWidget(recent_heading)
        self._recent_label = QLabel()
        self._recent_label.setWordWrap(True)
        self._recent_label.setStyleSheet("font-size: 12px;")
        recent_layout.addWidget(self._recent_label)
        layout.addWidget(recent_widget)

    def _refresh(self) -> None:
        try:
            stats = self.db.get_statistics()
            self._stats_labels["stat.employees_total"].setText(str(stats["employees_total"]))
            self._stats_labels["stat.violations_total"].setText(str(stats["violations_total"]))
            self._stats_labels["stat.companies_total"].setText(str(stats["companies_total"]))
            self._stats_labels["stat.overdue_total"].setText(str(stats["overdue_total"]))
            fines = stats["fines_total"]
            self._stats_labels["stat.fines_total"].setText(
                f"{fines:,.0f} ₽".replace(",", " "))
            total = stats["employees_total"] + stats["violations_total"]
            overdue = stats["overdue_total"]
            score = 100.0
            if total > 0:
                score = max(0.0, 100.0 - (overdue / max(total, 1)) * 100.0)
            self._gauge.set_score(score)

            recent = self.db.fetch_all(
                "SELECT event, created_at FROM audit_log ORDER BY id DESC LIMIT 5")
            lines = []
            for r in recent:
                ts = r["created_at"][:16] if r["created_at"] else ""
                ev = r["event"][:60] if r["event"] else ""
                lines.append(f"• [{ts}] {ev}")
            self._recent_label.setText("\n".join(lines) if lines else I18n._("dashboard.no_activity"))
        except Exception:
            import traceback
            traceback.print_exc()


# ---------------------------------------------------------------------------
# SECTION 2.7: Main Application Window
# ---------------------------------------------------------------------------


# ===========================================================================
# END OF PART 2 — BEGIN PART 3: Employee Registry
# ===========================================================================

# ---------------------------------------------------------------------------
# SECTION 3.1: Photo Gallery Dialog (drag-drop, thumbnails, preview)
# ---------------------------------------------------------------------------

def _abs_photo_path(path: str) -> str:
    if not path:
        return ""
    if path.startswith("__MEDIA__"):
        return os.path.join(RUNTIME_PATHS.media_dir, path[9:])
    if not os.path.isabs(path):
        return os.path.join(RUNTIME_PATHS.app_dir, path)
    return path

def _rel_photo_path(path: str) -> str:
    try:
        rel = os.path.relpath(path, RUNTIME_PATHS.media_dir)
        if not rel.startswith(".."):
            return "__MEDIA__/" + rel.replace("\\", "/")
        rel2 = os.path.relpath(path, RUNTIME_PATHS.app_dir)
        return rel2.replace("\\", "/")
    except Exception:
        return path


class PhotoPreviewDialog(QDialog):
    def __init__(self, file_path: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setWindowTitle(I18n._("emp.photo"))
        self.setWindowFlags(Qt.Window)
        self.setMinimumSize(800, 600)
        self.resize(1000, 750)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setAlignment(Qt.AlignCenter)
        self._label = QLabel()
        self._label.setAlignment(Qt.AlignCenter)
        pix = QPixmap(_abs_photo_path(file_path))
        if not pix.isNull():
            screen = QApplication.primaryScreen().availableGeometry()
            max_w = screen.width() * 0.8
            max_h = screen.height() * 0.8
            pix = pix.scaled(int(max_w), int(max_h), Qt.KeepAspectRatio,
                             Qt.SmoothTransformation)
            self._label.setPixmap(pix)
            self.setWindowTitle(os.path.basename(file_path))
        else:
            self._label.setText(I18n._("error.file_not_found"))
        scroll.setWidget(self._label)
        layout.addWidget(scroll)
        btn = QPushButton(I18n._("common.close"))
        btn.clicked.connect(self.close)
        layout.addWidget(btn, 0, Qt.AlignCenter)


class PhotoGalleryDialog(QDialog):
    def __init__(self, photos: List[str], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._photos = [_rel_photo_path(p) for p in (photos or [])]
        self.setWindowTitle(I18n._("emp.photo"))
        self.setMinimumSize(600, 450)
        self.resize(800, 600)
        self.setAcceptDrops(True)
        self._build_ui()
        self._render()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        heading = QLabel(I18n._("emp.photo"))
        heading.setProperty("heading", True)
        layout.addWidget(heading)
        hint = QLabel(I18n._("common.add") + ": drag & drop")
        hint.setStyleSheet("font-size: 12px;")
        layout.addWidget(hint)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._content = QWidget()
        self._grid = QGridLayout(self._content)
        self._grid.setSpacing(12)
        self._scroll.setWidget(self._content)
        layout.addWidget(self._scroll)

        btn_layout = QHBoxLayout()
        add_btn = QPushButton(I18n._("common.add"))
        add_btn.clicked.connect(self._add_photos)
        btn_layout.addWidget(add_btn)
        btn_layout.addStretch()
        close_btn = QPushButton(I18n._("common.close"))
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

    def _render(self) -> None:
        for i in reversed(range(self._grid.count())):
            item = self._grid.takeAt(i)
            if item and item.widget():
                item.widget().setParent(None)
                item.widget().deleteLater()
        row, col = 0, 0
        for path in self._photos:
            card = self._create_thumbnail_card(path)
            self._grid.addWidget(card, row, col)
            col += 1
            if col >= 4:
                col = 0
                row += 1

    def _create_thumbnail_card(self, path: str) -> QFrame:
        abs_path = _abs_photo_path(path)
        card = QFrame()
        card.setProperty("card", True)
        card.setFixedSize(160, 180)
        card.setCursor(QCursor(Qt.PointingHandCursor))
        cl = QVBoxLayout(card)
        cl.setContentsMargins(4, 4, 4, 4)
        cl.setSpacing(4)

        pix = QPixmap(abs_path)
        thumb = pix.scaled(150, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation) if not pix.isNull() else QPixmap()
        img_label = QLabel()
        if not thumb.isNull():
            img_label.setPixmap(thumb)
        else:
            img_label.setText("?")
            img_label.setAlignment(Qt.AlignCenter)
        img_label.setFixedSize(150, 120)
        img_label.setAlignment(Qt.AlignCenter)
        img_label.setStyleSheet("background: #F0F1F3; border-radius: 4px;")
        cl.addWidget(img_label, 0, Qt.AlignCenter)

        name_label = QLabel(os.path.basename(path)[:20])
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setStyleSheet("font-size: 11px; ;")
        name_label.setWordWrap(True)
        cl.addWidget(name_label)

        del_btn = QPushButton("✕")
        del_btn.setFixedSize(24, 24)
        del_btn.setProperty("small", True)
        del_btn.clicked.connect(lambda checked, p=path: self._remove_photo(p))
        del_btn.move(130, 4)
        del_btn.setParent(img_label)

        img_label.mouseDoubleClickEvent = lambda e, p=path: self._preview_photo(p)
        return card

    def _add_photos(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self, I18n._("common.add"), "",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp)")
        for f in files:
            rel = _rel_photo_path(f)
            if rel not in self._photos:
                self._photos.append(rel)
        self._render()

    def _remove_photo(self, path: str) -> None:
        if path in self._photos:
            self._photos.remove(path)
        self._render()

    def _preview_photo(self, path: str) -> None:
        dlg = PhotoPreviewDialog(_abs_photo_path(path), self)
        dlg.exec_()

    def dragEnterEvent(self, event: Any) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event: Any) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: Any) -> None:
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                path = url.toLocalFile()
                ext = os.path.splitext(path)[1].lower()
                if ext in (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp") and os.path.isfile(path):
                    rel = _rel_photo_path(path)
                    if rel not in self._photos:
                        self._photos.append(rel)
            self._render()
            event.acceptProposedAction()

    def get_photos(self) -> List[str]:
        return self._photos


class EmployeeEditDialog(QDialog):
    def __init__(self, data: Dict[str, Any] = None,
                 columns: List[Dict[str, Any]] = None,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._data = dict(data or {})
        self._columns = columns or []
        self._fields: Dict[str, QWidget] = {}
        self._photo_paths: List[str] = self._data.get("Фото", [])
        self.setWindowTitle(I18n._("emp.edit") if data else I18n._("emp.add"))
        self.setMinimumSize(760, 620)
        self.resize(900, 720)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        heading_text = I18n._("emp.edit") if self._data.get("id") else I18n._("emp.add")
        heading = QLabel(heading_text)
        heading.setProperty("heading", True)
        layout.addWidget(heading)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        container = QWidget()
        form = QFormLayout(container)
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignRight)

        for col in self._columns:
            name = col["name"]
            typ = col["type"]
            if name == "ID":
                continue
            if typ == "Медиа":
                continue
            value = self._data.get(name, "")
            if typ == "Число":
                w = QSpinBox()
                w.setRange(0, 999999999)
                w.setMinimumHeight(36)
                try:
                    w.setValue(int(float(str(value).replace(" ", "").replace(",", "."))))
                except Exception:
                    w.setValue(0)
            elif typ in ("Дата", "Годен до", "Дата проведения", "Date", "Date of", "Valid until"):
                w = DateAwareLineEdit(placeholder="ДД.ММ.ГГГГ")
                w.setMinimumHeight(36)
                w.setText(str(value))
            elif typ == "Статус":
                w = QComboBox()
                w.setMinimumHeight(36)
                statuses = ["Активен", "Архив", "В отпуске", "Уволен"]
                w.addItems(statuses)
                idx = w.findText(str(value))
                if idx >= 0:
                    w.setCurrentIndex(idx)
            else:
                w = TextbookLineEdit(placeholder="")
                w.setText(str(value))
                w.setMinimumHeight(36)
            self._fields[name] = w
            form.addRow(f"{name}:", w)

        # Photo attachment row
        photo_row = QHBoxLayout()
        self._photo_btn = QPushButton("📷 " + I18n._("emp.photo"))
        self._photo_btn.clicked.connect(self._select_photos)
        self._photo_btn.setMinimumHeight(36)
        photo_row.addWidget(self._photo_btn)
        self._photo_label = QLabel()
        self._update_photo_label()
        photo_row.addWidget(self._photo_label, 1)
        form.addRow("", photo_row)

        scroll.setWidget(container)
        layout.addWidget(scroll, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _select_photos(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self, I18n._("emp.photo"), "",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif);;All files (*.*)")
        if files:
            self._photo_paths.extend(files)
            self._update_photo_label()

    def _update_photo_label(self) -> None:
        cnt = len(self._photo_paths)
        self._photo_label.setText(f"{cnt} {I18n._('emp.photo').lower()}(s)" if cnt else "")

    def get_data(self) -> Dict[str, Any]:
        result = dict(self._data)
        result["Фото"] = self._photo_paths
        for col in self._columns:
            name = col["name"]
            if name == "ID":
                continue
            if col["type"] == "Медиа":
                continue
            w = self._fields.get(name)
            if w is None:
                continue
            if isinstance(w, QSpinBox):
                result[name] = str(w.value())
            elif isinstance(w, QComboBox):
                result[name] = w.currentText()
            else:
                result[name] = w.text().strip()
        return result


# ---------------------------------------------------------------------------
# SECTION 3.3: Employee Table Widget (core registry with all features)
# ---------------------------------------------------------------------------

class EmployeeTableWidget(QWidget):
    def __init__(self, parent: Optional[QWidget] = None,
                 user_id: int = 0) -> None:
        super().__init__(parent)
        self.db = DatabaseManager()
        self._user_id = user_id
        self._columns: List[Dict[str, Any]] = []
        self._records: List[Dict[str, Any]] = []
        self._all_records: List[Dict[str, Any]] = []
        self._sort_col: int = -1
        self._sort_order: int = Qt.AscendingOrder
        self._build_ui()
        self._load_data()

    def set_user_id(self, uid: int) -> None:
        self._user_id = uid
        self._load_data()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)

        self._search_edit = QLineEdit()
        self._search_edit.setProperty("search", True)
        self._search_edit.setPlaceholderText(I18n._("search.placeholder"))
        self._search_edit.setMinimumHeight(36)
        self._search_timer = QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(self._apply_filter)
        self._search_edit.textChanged.connect(self._search_timer.start)
        toolbar.addWidget(self._search_edit, 1)

        self._company_filter = QComboBox()
        self._company_filter.setMinimumHeight(36)
        self._company_filter.setMinimumWidth(180)
        self._company_filter.currentIndexChanged.connect(self._apply_filter)
        toolbar.addWidget(self._company_filter)

        self._add_btn = QPushButton(I18n._("emp.add"))
        self._add_btn.clicked.connect(self._add_record)
        toolbar.addWidget(self._add_btn)

        self._edit_btn = QPushButton(I18n._("common.edit"))
        self._edit_btn.clicked.connect(self._edit_selected)
        toolbar.addWidget(self._edit_btn)

        self._delete_btn = QPushButton(I18n._("common.delete"))
        self._delete_btn.clicked.connect(self._delete_selected)
        toolbar.addWidget(self._delete_btn)

        self._photos_btn = QPushButton("📷 " + I18n._("emp.photo"))
        self._photos_btn.setProperty("flat", True)
        self._photos_btn.clicked.connect(self._open_photos)
        toolbar.addWidget(self._photos_btn)

        self._notes_btn = QPushButton("📝 " + I18n._("common.notes"))
        self._notes_btn.setProperty("flat", True)
        self._notes_btn.clicked.connect(self._open_notes)
        toolbar.addWidget(self._notes_btn)

        self._export_btn = QPushButton("📤 " + I18n._("export.title"))
        self._export_btn.setProperty("flat", True)
        self._export_btn.clicked.connect(self._export_selected)
        toolbar.addWidget(self._export_btn)

        self._print_btn = QPushButton("🖨 " + I18n._("print.any_table"))
        self._print_btn.setProperty("flat", True)
        self._print_btn.clicked.connect(self._print_selected)
        toolbar.addWidget(self._print_btn)

        self._refresh_btn = QPushButton(I18n._("common.refresh"))
        self._refresh_btn.setProperty("flat", True)
        self._refresh_btn.clicked.connect(self._load_data)
        toolbar.addWidget(self._refresh_btn)

        layout.addLayout(toolbar)

        self._table = QTableWidget()
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().hide()
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionsClickable(True)
        self._table.horizontalHeader().setSectionsMovable(True)
        self._table.horizontalHeader().sectionClicked.connect(self._on_header_clicked)
        self._table.horizontalHeader().setContextMenuPolicy(Qt.CustomContextMenu)
        self._table.horizontalHeader().customContextMenuRequested.connect(
            self._on_header_context_menu)
        self._table.horizontalHeader().sectionDoubleClicked.connect(
            lambda idx: self._table.resizeColumnToContents(idx))
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.itemChanged.connect(self._on_item_changed)
        self._table.itemDoubleClicked.connect(lambda: self._edit_selected())
        
        self._table.setSortingEnabled(False)
        self._table.setContextMenuPolicy(Qt.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_table_context_menu)
        self._table.verticalHeader().setDefaultSectionSize(36)
        layout.addWidget(wrap_table_with_glow(self._table, self))

        # Status bar
        self._info_label = QLabel()
        self._info_label.setStyleSheet("font-size: 12px; padding: 4px 0;")
        layout.addWidget(self._info_label)

    # -----------------------------------------------------------------------
    # Data Loading
    # -----------------------------------------------------------------------

    def _load_data(self) -> None:
        self._columns = self.db.get_columns_config("employees")
        records = self.db.get_json_records("employees",
                                           user_id=self._user_id)
        self._all_records = records
        self._search_edit.clear()
        self._populate_filter()
        self._apply_filter()

    def _populate_filter(self) -> None:
        current = self._company_filter.currentText()
        self._company_filter.blockSignals(True)
        self._company_filter.clear()
        self._company_filter.addItem(I18n._("filter.all"))
        companies: List[str] = []
        for r in self._all_records:
            dj = r.get("data_json", {})
            c = str(dj.get("Фирма", "")).strip()
            if c and c not in companies:
                companies.append(c)
        companies.sort()
        self._company_filter.addItems(companies)
        idx = self._company_filter.findText(current)
        if idx >= 0:
            self._company_filter.setCurrentIndex(idx)
        self._company_filter.blockSignals(False)

    # -----------------------------------------------------------------------
    # Filtering & Search
    # -----------------------------------------------------------------------

    def _apply_filter(self) -> None:
        search_text = self._search_edit.text().strip().lower()
        company_text = self._company_filter.currentText().strip()
        is_regex = False
        if search_text.startswith("/") and search_text.endswith("/"):
            regex_pattern = search_text[1:-1]
            is_regex = True
        else:
            regex_pattern = ""

        self._records = []
        for r in self._all_records:
            dj = r.get("data_json", {})
            # Company filter
            if company_text and company_text != I18n._("filter.all"):
                emp_company = str(dj.get("Фирма", "")).strip()
                if emp_company != company_text:
                    continue
            # Text search
            if search_text:
                found = False
                if is_regex:
                    try:
                        pat = re.compile(regex_pattern, re.IGNORECASE)
                        for val in dj.values():
                            if isinstance(val, str) and pat.search(val):
                                found = True
                                break
                    except re.error:
                        pass
                else:
                    for val in dj.values():
                        if isinstance(val, str) and search_text in val.lower():
                            found = True
                            break
                if not found:
                    continue
            self._records.append(r)
        self._render_table()

    # -----------------------------------------------------------------------
    # Table Rendering
    # -----------------------------------------------------------------------

    def _render_table(self) -> None:
        self._table.blockSignals(True)
        self._table.setRowCount(0)
        cols = self._columns
        self._table.setColumnCount(len(cols))
        headers = [c["name"] for c in cols]
        self._table.setHorizontalHeaderLabels(headers)

        now = datetime.now()
        self._table.setRowCount(len(self._records))
        for row_idx, rec in enumerate(self._records):
            dj = rec.get("data_json", {})
            for col_idx, col in enumerate(cols):
                name = col["name"]
                typ = col["type"]
                value = dj.get(name, "")
                item = QTableWidgetItem()

                if typ == "Число":
                    try:
                        num = float(str(value).replace(" ", "").replace(",", "."))
                        if num == int(num):
                            item.setData(Qt.DisplayRole, int(num))
                            item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                        else:
                            item.setData(Qt.DisplayRole, num)
                            item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    except Exception:
                        item.setText(str(value))
                elif typ == "Медиа":
                    photos = value if isinstance(value, list) else []
                    count = len(photos)
                    icon = "🖼" if count > 0 else "□"
                    item.setText(f"{icon} {count}" if count > 0 else icon)
                    item.setTextAlignment(Qt.AlignCenter)
                elif typ == "Статус":
                    item.setText(str(value))
                    item.setTextAlignment(Qt.AlignCenter)
                elif typ in ("Дата", "Годен до", "Дата проведения", "Date", "Date of", "Valid until"):
                    item.setText(str(value))
                    item.setTextAlignment(Qt.AlignCenter)
                elif name == "ID":
                    item.setText(str(rec.get("id", "")))
                    item.setTextAlignment(Qt.AlignCenter)
                else:
                    item.setText(str(value))

                item.setData(Qt.UserRole, rec.get("id", 0))
                item.setData(Qt.UserRole + 1, name)

                bg = self._get_cell_color(typ, str(value), dj, name)
                if bg:
                    item.setBackground(bg)

                self._table.setItem(row_idx, col_idx, item)

        self._table.resizeColumnsToContents()
        self._table.blockSignals(False)
        self._update_info()

    def _get_cell_color(self, typ: str, value: str,
                        data: Dict[str, Any],
                        field_name: str) -> Optional[QColor]:
        is_dark = ThemeEngine._current_theme == "dark"
        now = datetime.now()

        if typ in ("Дата проведения", "Date of") and value:
            date_mode = str(data.get(f"{field_name}_mode", "Дата проведения"))
            return get_date_indicator_bg(value, is_dark, date_mode)

        if typ == "Статус":
            return get_status_indicator_bg(value, is_dark)

        if typ in ("Годен до", "Valid until") and value:
            return get_valid_until_bg(value, is_dark)

        if typ in ("Дата", "Date") and value:
            date_mode = str(data.get(f"{field_name}_mode", "Действует до"))
            return get_date_indicator_bg(value, is_dark, date_mode)

        return None


    def _update_info(self) -> None:
        total = len(self._all_records)
        shown = len(self._records)
        text = f"{I18n._('common.filter')}: {shown} / {total}"
        self._info_label.setText(text)
        try:
            p = self.parent()
            if p and hasattr(p, 'setTabText'):
                tw = p
            else:
                tw = getattr(p, 'parent', lambda: None)() if p else None
            if tw and hasattr(tw, 'setTabText'):
                for i in range(tw.count()):
                    if tw.widget(i) is self:
                        tw.setTabText(i, f"{I18n._('tab.employees')} ({total})")
                        break
        except Exception:
            pass

    # -----------------------------------------------------------------------
    # Sorting
    # -----------------------------------------------------------------------

    def _on_header_clicked(self, col_idx: int) -> None:
        if self._sort_col == col_idx:
            # Cycle: asc -> desc -> none
            if self._sort_order == Qt.AscendingOrder:
                self._sort_order = Qt.DescendingOrder
            else:
                self._sort_col = -1
                self._sort_order = Qt.AscendingOrder
        else:
            self._sort_col = col_idx
            self._sort_order = Qt.AscendingOrder
        self._sort_data()
        self._render_table()

    def _sort_data(self) -> None:
        if self._sort_col < 0 or self._sort_col >= len(self._columns):
            self._records.sort(key=lambda r: str(r.get("data_json", {}).get("ФИО", "")).lower())
            return
        col = self._columns[self._sort_col]
        name = col["name"]
        typ = col["type"]

        def sort_key(rec: Dict[str, Any]) -> Any:
            dj = rec.get("data_json", {})
            val = dj.get(name, "")
            if typ == "Число":
                try:
                    return float(str(val).replace(" ", "").replace(",", "."))
                except Exception:
                    return 0.0
            if typ in ("Дата", "Годен до", "Дата проведения", "Date", "Valid until"):
                try:
                    p = str(val).split(".")
                    if len(p) == 3:
                        return datetime(int(p[2]), int(p[1]), int(p[0])).isoformat()
                except Exception:
                    pass  # expected
                return str(val)
            return str(val).lower()

        reverse = self._sort_order == Qt.DescendingOrder
        self._records.sort(key=sort_key, reverse=reverse)

    # -----------------------------------------------------------------------
    # CRUD
    # -----------------------------------------------------------------------

    def _add_record(self) -> None:
        dlg = EmployeeEditDialog({}, self._columns, self)
        if dlg.exec_() == QDialog.Accepted:
            data = dlg.get_data()
            try:
                duplicate = self.db.find_employee_duplicate(data, user_id=self._user_id)
                if duplicate:
                    merged = dict(duplicate.get("data_json", {}))
                    merged.update({k: v for k, v in data.items() if str(v).strip() != ""})
                    self.db.save_json_record("employees", duplicate["id"], merged,
                                             user_id=self._user_id)
                    self._load_data()
                    ToastNotification.notify(I18n._("emp.duplicate_updated"), "success", 3000)
                    self.db.merge_duplicates("employees")
                    return
                self.db.save_json_record("employees", 0, data,
                                         user_id=self._user_id)
                self.db.merge_duplicates("employees")
                self._load_data()
                ToastNotification.notify(I18n._("common.success"), "success", 3000)
            except Exception:
                ToastNotification.notify(I18n._("error.generic"), "error", 5000)

    def _edit_record(self, record: Dict[str, Any]) -> None:
        dj = record.get("data_json", {})
        dlg = EmployeeEditDialog(dj, self._columns, self)
        if dlg.exec_() == QDialog.Accepted:
            data = dlg.get_data()
            try:
                duplicate = self.db.find_employee_duplicate(data, exclude_id=record["id"], user_id=self._user_id)
                if duplicate:
                    QMessageBox.warning(self, I18n._("common.warning"), I18n._("emp.duplicate_found"))
                    return
                self.db.save_json_record("employees", record["id"], data,
                                         user_id=self._user_id)
                self.db.merge_duplicates("employees")
                self._load_data()
                ToastNotification.notify(I18n._("common.success"), "success", 3000)
            except Exception:
                ToastNotification.notify(I18n._("error.generic"), "error", 5000)

    def _edit_selected(self) -> None:
        row = self._table.currentRow()
        if row < 0 or row >= len(self._records):
            return
        self._edit_record(self._records[row])

    def _delete_selected(self) -> None:
        rows = set()
        for idx in self._table.selectedIndexes():
            rows.add(idx.row())
        if not rows:
            ToastNotification.notify(I18n._("common.no_selection"), "warning", 3000)
            return
        if len(rows) > 3:
            backup_reply = QMessageBox.question(
                self, I18n._("common.confirm"),
                I18n._("emp.backup_before_delete") if hasattr(I18n, "_") else
                f"Создать резервную копию перед удалением {len(rows)} записей?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
            if backup_reply == QMessageBox.Cancel:
                return
            if backup_reply == QMessageBox.Yes:
                try:
                    self.db.create_backup()
                    ToastNotification.notify(I18n._("toast.backup_created"), "info", 3000)
                except Exception:
                    pass  # non-critical
        reply = QMessageBox.question(
            self, I18n._("common.confirm"),
            I18n._("emp.delete_confirm").format(
                count=len(rows)) if hasattr(I18n, "_") else
            f"{I18n._('common.delete')} {len(rows)} {I18n._('emp.fio')}?",
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        for row in sorted(rows, reverse=True):
            if 0 <= row < len(self._records):
                rid = self._records[row].get("id", 0)
                if rid:
                    self.db.delete_json_record("employees", rid)
        self._load_data()
        ToastNotification.notify(I18n._("toast.delete_success"), "success", 3000)

    def _export_selected(self) -> None:
        row = self._table.currentRow()
        if row < 0 or row >= len(self._records):
            ToastNotification.notify(I18n._("common.no_selection"), "warning", 3000)
            return
        rec = self._records[row]
        dj = rec.get("data_json", {})
        from PyQt5.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(self, I18n._("export.title"),
                                               f"record_{rec['id']}.csv",
                                               "CSV (*.csv)")
        if not path:
            return
        try:
            import csv
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow([c["name"] for c in self._columns])
                row_data = [dj.get(c["name"], "") for c in self._columns]
                w.writerow(row_data)
            ToastNotification.notify(I18n._("export.success").format(path=path), "success", 3000)
        except Exception as e:
            ToastNotification.notify(I18n._("export.error").format(error=str(e)), "error", 5000)

    def _print_selected(self) -> None:
        rows = sorted(set(idx.row() for idx in self._table.selectedIndexes()))
        if not rows:
            ToastNotification.notify(I18n._("common.no_selection"), "warning", 3000)
            return
        records = []
        for row in rows:
            if row >= 0 and row < len(self._records):
                records.append(self._records[row])
        if not records:
            return
        html = PrintEngine.render_with_template(self, "order", records, self._columns)
        PrintEngine.print_document(html)

    def _open_photos(self) -> None:
        row = self._table.currentRow()
        if row < 0 or row >= len(self._records):
            return
        rec = self._records[row]
        dj = rec.get("data_json", {})
        photos = dj.get("Фото", [])
        if not isinstance(photos, list):
            photos = []
        dlg = PhotoGalleryDialog(photos, self)
        if dlg.exec_() == QDialog.Accepted:
            new_photos = dlg.get_photos()
            dj["Фото"] = new_photos
            try:
                self.db.save_json_record("employees", rec["id"], dj,
                                         user_id=self._user_id)
                self._load_data()
            except Exception:
                ToastNotification.notify(I18n._("error.generic"), "error", 5000)

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        row = item.row()
        col = item.column()
        if row < 0 or row >= len(self._records) or col < 0 or col >= len(self._columns):
            return
        rec = self._records[row]
        dj = rec.get("data_json", {})
        name = self._columns[col]["name"]
        typ = self._columns[col]["type"]
        if typ == "Медиа":
            return  # Photo editing via dedicated dialog
        if name == "ID":
            return  # ID column is auto-filled
        new_value = item.text().strip()
        dj[name] = new_value
        try:
            self.db.save_json_record("employees", rec["id"], dj,
                                     user_id=self._user_id)
        except Exception:
            traceback.print_exc()

    def _open_notes(self) -> None:
        row = self._table.currentRow()
        if row < 0 or row >= len(self._records):
            ToastNotification.notify(I18n._("common.no_selection"), "warning", 3000)
            return
        rec = self._records[row]
        dlg = NotesDialog("employees", rec["id"], "", self)
        dlg.exec_()

    # -----------------------------------------------------------------------
    # Context Menus
    # -----------------------------------------------------------------------

    def _on_header_context_menu(self, pos: QPoint) -> None:
        col_idx = self._table.horizontalHeader().logicalIndexAt(pos)
        if col_idx < 0:
            return
        col = self._columns[col_idx]
        menu = QMenu(self)
        rename_a = menu.addAction(I18n._("column.rename"))
        add_a = menu.addAction(I18n._("column.add"))
        del_a = menu.addAction(I18n._("column.delete"))
        chg_a = menu.addAction(I18n._("column.change_type"))
        action = menu.exec_(self._table.horizontalHeader().mapToGlobal(pos))
        if action == rename_a:
            self._rename_column(col)
        elif action == add_a:
            self._add_column()
        elif action == del_a:
            self._delete_column(col)
        elif action == chg_a:
            self._change_column_type(col)
        return

    def _rename_column(self, col: Dict[str, Any]) -> None:
        new_name, ok = QInputDialog.getText(
            self, I18n._("column.rename"), I18n._("column.rename_prompt"),
            text=col["name"])
        if ok and new_name:
            if self.db.rename_column("employees", col["name"], new_name):
                self._load_data()
                ToastNotification.notify(I18n._("common.success"), "success", 3000)
            else:
                QMessageBox.warning(self, I18n._("common.warning"),
                                    I18n._("column.duplicate_error"))

    def _add_column(self) -> None:
        name, ok = QInputDialog.getText(
            self, I18n._("column.add"), I18n._("column.add_prompt"))
        if ok and name:
            types = [I18n._("column.type_text"), I18n._("column.type_number"),
                     I18n._("column.type_date"), I18n._("column.type_date_conducted"),
                     I18n._("column.type_status"), I18n._("column.type_media")]
            typ, ok2 = QInputDialog.getItem(
                self, I18n._("column.change_type"), "",
                types, 0, False)
            if ok2 and typ:
                type_map = {
                    I18n._("column.type_text"): "Текст",
                    I18n._("column.type_number"): "Число",
                    I18n._("column.type_date"): "Годен до",
                    I18n._("column.type_date_conducted"): "Дата проведения",
                    I18n._("column.type_status"): "Статус",
                    I18n._("column.type_media"): "Медиа",
                }
                mapped_type = type_map.get(typ, "Текст")
                if self.db.add_column("employees", name, mapped_type):
                    self._load_data()
                    ToastNotification.notify(I18n._("common.success"), "success", 3000)

    def _delete_column(self, col: Dict[str, Any]) -> None:
        reply = QMessageBox.question(
            self, I18n._("common.confirm"),
            f"{I18n._('column.delete')}: '{col['name']}'?",
            QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            if self.db.delete_column("employees", col["name"]):
                self._load_data()
                ToastNotification.notify(I18n._("toast.delete_success"), "success", 3000)

    def _change_column_type(self, col: Dict[str, Any]) -> None:
        types = [I18n._("column.type_text"), I18n._("column.type_number"),
                 I18n._("column.type_date"), I18n._("column.type_date_conducted"),
                 I18n._("column.type_status"), I18n._("column.type_media")]
        typ, ok = QInputDialog.getItem(
            self, I18n._("column.change_type"), "",
            types, 0, False)
        if ok and typ:
            type_map = {
                I18n._("column.type_text"): "Текст",
                I18n._("column.type_number"): "Число",
                I18n._("column.type_date"): "Годен до",
                I18n._("column.type_date_conducted"): "Дата проведения",
                I18n._("column.type_status"): "Статус",
                I18n._("column.type_media"): "Медиа",
            }
            mapped_type = type_map.get(typ, "Текст")
            try:
                self.db.create_backup()
                self.db.conn.execute(
                    "UPDATE columns_config SET type=? WHERE category=? AND name=?",
                    (mapped_type, "employees", col["name"]))
                self.db.conn.commit()
                self._load_data()
                ToastNotification.notify(I18n._("common.success"), "success", 3000)
            except Exception:
                ToastNotification.notify(I18n._("error.generic"), "error", 5000)

    def _on_table_context_menu(self, pos: QPoint) -> None:
        row = self._table.rowAt(pos.y())
        if row < 0:
            return
        self._table.selectRow(row)
        menu = QMenu(self)
        edit_a = menu.addAction(I18n._("common.edit"))
        del_a = menu.addAction(I18n._("common.delete"))
        photo_a = menu.addAction("📷 " + I18n._("emp.photo"))
        print_a = menu.addAction("🖨 " + I18n._("print.any_table"))
        menu.addSeparator()
        copy_a = menu.addAction(I18n._("common.copy"))
        action = menu.exec_(self._table.mapToGlobal(pos))
        if action == edit_a:
            self._edit_selected()
        elif action == del_a:
            self._delete_selected()
        elif action == photo_a:
            self._open_photos()
        elif action == print_a:
            self._print_selected()
        elif action == copy_a:
            item = self._table.item(row, self._table.currentColumn())
            if item and item.text():
                QApplication.clipboard().setText(item.text())

    # -----------------------------------------------------------------------
    # External access
    # -----------------------------------------------------------------------

    def refresh(self) -> None:
        self._load_data()

    def focus_record(self, record_id: Any) -> bool:
        self._load_data()
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if item and item.text().strip() == str(record_id):
                self._table.selectRow(row)
                self._table.scrollToItem(item, QAbstractItemView.PositionAtCenter)
                return True
        return False


# ===========================================================================
# END OF PART 3 — BEGIN PART 4: Violations, Textbook Engine, Auto-Dates
# ===========================================================================

# ---------------------------------------------------------------------------
# SECTION 4.1: Textbook Engine (Auto-Replace / Macro Expansion)
# ---------------------------------------------------------------------------

class TextbookEngine:
    _rules: Dict[str, str] = {}
    _enabled: bool = True
    _manual_mode: bool = False

    @classmethod
    def load(cls) -> None:
        try:
            db = DatabaseManager()
            cls._rules = db.get_textbook()
        except Exception:
            cls._rules = {}

    @classmethod
    def set_enabled(cls, enabled: bool) -> None:
        cls._enabled = enabled

    @classmethod
    def is_enabled(cls) -> bool:
        return cls._enabled

    @classmethod
    def set_manual_mode(cls, manual: bool) -> None:
        cls._manual_mode = manual

    @classmethod
    def is_manual(cls) -> bool:
        return cls._manual_mode

    @classmethod
    def process(cls, text: str) -> Tuple[str, bool]:
        if not cls._enabled or cls._manual_mode:
            return text, False
        lower = text.lower().strip()
        if lower in cls._rules:
            return cls._rules[lower], True
        return text, False

    @classmethod
    def manual_replace(cls, text: str) -> Tuple[str, bool]:
        lower = text.lower().strip()
        if lower in cls._rules:
            return cls._rules[lower], True
        return text, False

    @classmethod
    def get_rules(cls) -> Dict[str, str]:
        return dict(cls._rules)

    @classmethod
    def add_rule(cls, short_code: str, full_text: str) -> bool:
        try:
            db = DatabaseManager()
            r = db.save_textbook_entry(short_code, full_text)
            cls._rules[short_code] = full_text
            return True
        except Exception:
            return False

    @classmethod
    def delete_rule(cls, short_code: str) -> bool:
        try:
            db = DatabaseManager()
            r = db.delete_textbook_entry(short_code)
            cls._rules.pop(short_code, None)
            return True
        except Exception:
            return False


class TextbookLineEdit(QLineEdit):
    def __init__(self, parent: Optional[QWidget] = None,
                 placeholder: str = "") -> None:
        super().__init__(parent)
        if placeholder:
            self.setPlaceholderText(placeholder)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        super().keyPressEvent(event)
        if event.key() in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter):
            if not TextbookEngine.is_manual():
                text = self.text()
                words = text.split(" ")
                if words:
                    last_word = words[-1]
                    replacement, replaced = TextbookEngine.process(last_word)
                    if replaced:
                        words[-1] = replacement
                        self.setText(" ".join(words))
                        self.setCursorPosition(len(self.text()))


class TextbookTextEdit(QTextEdit):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        super().keyPressEvent(event)
        if event.key() in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter):
            if not TextbookEngine.is_manual():
                text = self.toPlainText()
                words = text.split(" ")
                if words:
                    last_word = words[-1].strip()
                    replacement, replaced = TextbookEngine.process(last_word)
                    if replaced:
                        words[-1] = replacement
                        self.setPlainText(" ".join(words).replace("\n ", "\n").replace(" \n", "\n"))
                        cursor = self.textCursor()
                        cursor.movePosition(cursor.End)
                        self.setTextCursor(cursor)


class TextbookDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.db = DatabaseManager()
        self.setWindowTitle(I18n._("textbook.edit"))
        self.setMinimumSize(600, 450)
        self.resize(700, 500)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        heading = QLabel(I18n._("textbook.auto_replace"))
        heading.setProperty("heading", True)
        layout.addWidget(heading)

        hint = QLabel(I18n._("textbook.trigger_hint"))
        hint.setStyleSheet("font-size: 12px;")
        layout.addWidget(hint)

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText(I18n._("common.search_hint"))
        self._search_edit.textChanged.connect(self._filter_rules)
        layout.addWidget(self._search_edit)

        self._table = QTableWidget()
        self._table.setColumnCount(2)
        self._table.setHorizontalHeaderLabels([
            I18n._("textbook.shortcode"), I18n._("textbook.fulltext")])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        layout.addWidget(wrap_table_with_glow(self._table, self))

        btn_layout = QHBoxLayout()
        add_btn = QPushButton(I18n._("textbook.add"))
        add_btn.clicked.connect(self._add_rule)
        btn_layout.addWidget(add_btn)
        del_btn = QPushButton(I18n._("textbook.delete"))
        del_btn.setProperty("danger", True)
        del_btn.clicked.connect(self._delete_rule)
        btn_layout.addWidget(del_btn)
        btn_layout.addStretch()
        close_btn = QPushButton(I18n._("common.close"))
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

        self._load_rules()

        self._all_rules: List[Tuple[str, str]] = []

    def _filter_rules(self) -> None:
        query = self._search_edit.text().strip().lower()
        rules = self._all_rules
        if query:
            rules = [(c, t) for c, t in rules
                     if query in c.lower() or query in t.lower()]
        self._table.setRowCount(len(rules))
        for i, (code, text) in enumerate(rules):
            code_item = QTableWidgetItem(code)
            code_item.setFlags(code_item.flags() & ~Qt.ItemIsEditable)
            self._table.setItem(i, 0, code_item)
            text_item = QTableWidgetItem(text[:80] + ("..." if len(text) > 80 else ""))
            text_item.setFlags(text_item.flags() & ~Qt.ItemIsEditable)
            text_item.setToolTip(text)
            self._table.setItem(i, 1, text_item)
        self._table.resizeColumnsToContents()

    def _load_rules(self) -> None:
        self._all_rules = sorted(TextbookEngine.get_rules().items())
        self._filter_rules()

    def _add_rule(self) -> None:
        code, ok = QInputDialog.getText(
            self, I18n._("textbook.add"), I18n._("textbook.shortcode"))
        if not ok or not code:
            return
        text, ok2 = QInputDialog.getMultiLineText(
            self, I18n._("textbook.add"), I18n._("textbook.fulltext"))
        if ok2 and text:
            TextbookEngine.add_rule(code.strip(), text.strip())
            self._load_rules()
            ToastNotification.notify(I18n._("common.success"), "success", 3000)

    def _delete_rule(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            return
        code = self._table.item(row, 0).text()
        reply = QMessageBox.question(
            self, I18n._("common.confirm"),
            f"{I18n._('common.delete')}: '{code}'?",
            QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            TextbookEngine.delete_rule(code)
            self._load_rules()
            ToastNotification.notify(I18n._("toast.delete_success"), "success", 3000)


# ---------------------------------------------------------------------------
# SECTION 4.2: Auto-Date Formatter (MM-DD-YYYY -> DD.MM.YYYY)
# ---------------------------------------------------------------------------

DATE_PATTERN = re.compile(r"(\d{2})-(\d{2})-(\d{4})")

def auto_format_date(text: str) -> str:
    def _replacer(m: re.Match) -> str:
        month, day, year = m.group(1), m.group(2), m.group(3)
        return f"{day}.{month}.{year}"
    return DATE_PATTERN.sub(_replacer, text)


class DateAwareLineEdit(QLineEdit):
    def __init__(self, parent: Optional[QWidget] = None,
                 placeholder: str = "ДД.ММ.ГГГГ") -> None:
        super().__init__(parent)
        self.setPlaceholderText(placeholder)

    def focusOutEvent(self, event: Any) -> None:
        old = self.text()
        formatted = auto_format_date(old)
        if formatted != old:
            self.setText(formatted)
        super().focusOutEvent(event)


# ---------------------------------------------------------------------------
# SECTION 4.3: Violation Edit Dialog (with Template Picker)
# ---------------------------------------------------------------------------

class ViolationEditDialog(QDialog):
    def __init__(self, data: Dict[str, Any] = None,
                 columns: List[Dict[str, Any]] = None,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._data = dict(data or {})
        self._columns = columns or []
        self._fields: Dict[str, QWidget] = {}
        self._photo_paths: List[str] = self._data.get("Фото", [])
        self.setWindowTitle(I18n._("viol.edit") if data else I18n._("viol.add"))
        self.setMinimumSize(820, 700)
        self.resize(980, 780)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(10)

        heading_text = I18n._("viol.edit") if self._data.get("id") else I18n._("viol.add")
        heading = QLabel(heading_text)
        heading.setProperty("heading", True)
        layout.addWidget(heading)

        # Template picker
        template_layout = QHBoxLayout()
        template_label = QLabel(I18n._("viol.use_template") + ":")
        template_label.setStyleSheet("font-size: 12px; ;")
        template_layout.addWidget(template_label)
        self._template_combo = QComboBox()
        self._template_combo.addItem("— " + I18n._("common.templates") + " —")
        try:
            db = DatabaseManager()
            for t in db.get_templates():
                self._template_combo.addItem(t["name"], t)
        except Exception:
            pass  # non-critical
        self._template_combo.currentIndexChanged.connect(self._on_template_selected)
        template_layout.addWidget(self._template_combo, 1)
        layout.addLayout(template_layout)

        # Reminder checkbox
        self._reminder_cb = QCheckBox("🔔 " + I18n._("viol.create_reminder"))
        layout.addWidget(self._reminder_cb)

        # Form
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        container = QWidget()
        form = QFormLayout(container)
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight)

        self._date_fields: List[str] = []

        for col in self._columns:
            name = col["name"]
            typ = col["type"]
            if name == "ID":
                continue
            if typ == "Медиа":
                continue
            value = self._data.get(name, "")

            if typ == "Число":
                w = QSpinBox()
                w.setRange(0, 999999999)
                w.setMinimumHeight(36)
                try:
                    w.setValue(int(float(str(value).replace(" ", "").replace(",", "."))))
                except Exception:
                    w.setValue(0)
            elif typ in ("Дата", "Годен до", "Дата проведения", "Date", "Date of", "Valid until"):
                w = DateAwareLineEdit()
                w.setMinimumHeight(36)
                w.setText(str(value))
                self._date_fields.append(name)
            elif typ == "Статус":
                w = QComboBox()
                w.setMinimumHeight(36)
                statuses = ["Активно", "Исполнено", "Просрочено", "Архив"]
                w.addItems(statuses)
                idx = w.findText(str(value))
                if idx >= 0:
                    w.setCurrentIndex(idx)
            else:
                w = TextbookLineEdit(placeholder="")
                w.setMinimumHeight(36)
                w.setText(str(value))

            self._fields[name] = w
            form.addRow(f"{name}:", w)

        scroll.setWidget(container)
        layout.addWidget(scroll, 1)

        # Photo attachment row
        photo_row = QHBoxLayout()
        self._photo_btn = QPushButton("📷 " + I18n._("viol.photo"))
        self._photo_btn.clicked.connect(self._select_photos)
        self._photo_btn.setMinimumHeight(36)
        photo_row.addWidget(self._photo_btn)
        self._photo_label = QLabel()
        self._update_photo_label()
        photo_row.addWidget(self._photo_label, 1)
        layout.addLayout(photo_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _select_photos(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self, I18n._("viol.photo"), "",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif);;All files (*.*)")
        if files:
            self._photo_paths.extend(files)
            self._update_photo_label()

    def _update_photo_label(self) -> None:
        cnt = len(self._photo_paths)
        self._photo_label.setText(f"{cnt} {I18n._('viol.photo').lower()}(s)" if cnt else "")

    def _on_template_selected(self, idx: int) -> None:
        if idx <= 0:
            return
        template = self._template_combo.currentData()
        if not template:
            return
        data = template.get("data", {})
        mapping = {
            "Категория риска": "category",
            "Описание": "recommended_action",
        }
        for field_name, template_key in mapping.items():
            w = self._fields.get(field_name)
            if w and template_key in data:
                val = str(data[template_key])
                if isinstance(w, QLineEdit):
                    w.setText(val)
                elif isinstance(w, QTextEdit):
                    w.setPlainText(val)
                elif isinstance(w, QComboBox):
                    idx2 = w.findText(val)
                    if idx2 >= 0:
                        w.setCurrentIndex(idx2)

    def get_data(self) -> Dict[str, Any]:
        result = dict(self._data)
        for col in self._columns:
            name = col["name"]
            if name == "ID":
                continue
            if col["type"] == "Медиа":
                continue
            w = self._fields.get(name)
            if w is None:
                continue
            if isinstance(w, QSpinBox):
                result[name] = str(w.value())
            elif isinstance(w, QComboBox):
                result[name] = w.currentText()
            elif isinstance(w, QTextEdit):
                result[name] = w.toPlainText().strip()
            else:
                result[name] = w.text().strip()
        return result

    def should_create_reminder(self) -> bool:
        return self._reminder_cb.isChecked()


# ---------------------------------------------------------------------------
# SECTION 4.4: Violations Table Widget
# ---------------------------------------------------------------------------

class ViolationsTableWidget(QWidget):
    def __init__(self, parent: Optional[QWidget] = None,
                 user_id: int = 0) -> None:
        super().__init__(parent)
        self.db = DatabaseManager()
        self._user_id = user_id
        self._columns: List[Dict[str, Any]] = []
        self._records: List[Dict[str, Any]] = []
        self._all_records: List[Dict[str, Any]] = []
        self._sort_col: int = -1
        self._sort_order: int = Qt.AscendingOrder
        self._build_ui()
        self._load_data()

    def set_user_id(self, uid: int) -> None:
        self._user_id = uid
        self._load_data()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)

        self._search_edit = QLineEdit()
        self._search_edit.setProperty("search", True)
        self._search_edit.setPlaceholderText(I18n._("search.placeholder"))
        self._search_edit.setMinimumHeight(36)
        self._search_timer = QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(self._apply_filter)
        self._search_edit.textChanged.connect(self._search_timer.start)
        toolbar.addWidget(self._search_edit, 1)

        self._company_filter = QComboBox()
        self._company_filter.setMinimumHeight(36)
        self._company_filter.setMinimumWidth(180)
        self._company_filter.currentIndexChanged.connect(self._apply_filter)
        toolbar.addWidget(self._company_filter)

        self._add_btn = QPushButton(I18n._("viol.add"))
        self._add_btn.clicked.connect(self._add_record)
        toolbar.addWidget(self._add_btn)

        self._edit_btn = QPushButton(I18n._("common.edit"))
        self._edit_btn.clicked.connect(self._edit_selected)
        toolbar.addWidget(self._edit_btn)

        self._delete_btn = QPushButton(I18n._("common.delete"))
        self._delete_btn.clicked.connect(self._delete_selected)
        toolbar.addWidget(self._delete_btn)

        self._photos_btn = QPushButton("📷 " + I18n._("viol.photo"))
        self._photos_btn.setProperty("flat", True)
        self._photos_btn.clicked.connect(self._open_photos)
        toolbar.addWidget(self._photos_btn)

        self._notes_btn = QPushButton("📝 " + I18n._("common.notes"))
        self._notes_btn.setProperty("flat", True)
        self._notes_btn.clicked.connect(self._open_notes)
        toolbar.addWidget(self._notes_btn)

        self._textbook_btn = QPushButton("📖 " + I18n._("textbook.edit"))
        self._textbook_btn.setProperty("flat", True)
        self._textbook_btn.clicked.connect(self._open_textbook)
        toolbar.addWidget(self._textbook_btn)

        self._types_btn = QPushButton("🏷 " + I18n._("viol.types"))
        self._types_btn.setProperty("flat", True)
        self._types_btn.clicked.connect(self._open_type_manager)
        toolbar.addWidget(self._types_btn)

        self._export_btn = QPushButton("📤 " + I18n._("export.title"))
        self._export_btn.setProperty("flat", True)
        self._export_btn.clicked.connect(self._export_selected)
        toolbar.addWidget(self._export_btn)

        self._print_btn = QPushButton("🖨 " + I18n._("print.any_table"))
        self._print_btn.setProperty("flat", True)
        self._print_btn.clicked.connect(self._print_selected)
        toolbar.addWidget(self._print_btn)

        self._refresh_btn = QPushButton(I18n._("common.refresh"))
        self._refresh_btn.setProperty("flat", True)
        self._refresh_btn.clicked.connect(self._load_data)
        toolbar.addWidget(self._refresh_btn)

        layout.addLayout(toolbar)

        self._table = QTableWidget()
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().hide()
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionsClickable(True)
        self._table.horizontalHeader().setSectionsMovable(True)
        self._table.horizontalHeader().sectionClicked.connect(self._on_header_clicked)
        self._table.horizontalHeader().setContextMenuPolicy(Qt.CustomContextMenu)
        self._table.horizontalHeader().customContextMenuRequested.connect(
            self._on_header_context_menu)
        self._table.horizontalHeader().sectionDoubleClicked.connect(
            lambda idx: self._table.resizeColumnToContents(idx))
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.itemChanged.connect(self._on_item_changed)
        self._table.itemDoubleClicked.connect(lambda: self._edit_selected())
        
        self._table.setSortingEnabled(False)
        self._table.setContextMenuPolicy(Qt.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_table_context_menu)
        self._table.verticalHeader().setDefaultSectionSize(36)
        layout.addWidget(wrap_table_with_glow(self._table, self))

        self._info_label = QLabel()
        self._info_label.setStyleSheet("font-size: 12px; padding: 4px 0;")
        layout.addWidget(self._info_label)

    # -----------------------------------------------------------------------
    # Data Loading
    # -----------------------------------------------------------------------

    def _load_data(self) -> None:
        self._columns = self.db.get_columns_config("violations")
        records = self.db.get_json_records("violations",
                                           user_id=self._user_id)
        self._all_records = records
        self._search_edit.clear()
        self._populate_filter()
        self._apply_filter()

    def _populate_filter(self) -> None:
        current = self._company_filter.currentText()
        self._company_filter.blockSignals(True)
        self._company_filter.clear()
        self._company_filter.addItem(I18n._("filter.all"))
        companies: List[str] = []
        for r in self._all_records:
            dj = r.get("data_json", {})
            c = str(dj.get("Фирма", "")).strip()
            if c and c not in companies:
                companies.append(c)
        companies.sort()
        self._company_filter.addItems(companies)
        idx = self._company_filter.findText(current)
        if idx >= 0:
            self._company_filter.setCurrentIndex(idx)
        self._company_filter.blockSignals(False)

    # -----------------------------------------------------------------------
    # Filtering & Search
    # -----------------------------------------------------------------------

    def _apply_filter(self) -> None:
        search_text = self._search_edit.text().strip().lower()
        company_text = self._company_filter.currentText().strip()
        is_regex = search_text.startswith("/") and search_text.endswith("/")
        regex_pattern = search_text[1:-1] if is_regex else ""

        self._records = []
        for r in self._all_records:
            dj = r.get("data_json", {})
            if company_text and company_text != I18n._("filter.all"):
                v_company = str(dj.get("Фирма", "")).strip()
                if v_company != company_text:
                    continue
            if search_text:
                found = False
                if is_regex:
                    try:
                        pat = re.compile(regex_pattern, re.IGNORECASE)
                        for val in dj.values():
                            if isinstance(val, str) and pat.search(val):
                                found = True
                                break
                    except re.error:
                        pass
                else:
                    for val in dj.values():
                        if isinstance(val, str) and search_text in val.lower():
                            found = True
                            break
                if not found:
                    continue
            self._records.append(r)
        self._render_table()

    # -----------------------------------------------------------------------
    # Table Rendering
    # -----------------------------------------------------------------------

    def _render_table(self) -> None:
        self._table.blockSignals(True)
        self._table.setRowCount(0)
        cols = self._columns
        self._table.setColumnCount(len(cols))
        headers = [c["name"] for c in cols]
        self._table.setHorizontalHeaderLabels(headers)

        now = datetime.now()
        self._table.setRowCount(len(self._records))
        for row_idx, rec in enumerate(self._records):
            dj = rec.get("data_json", {})
            for col_idx, col in enumerate(cols):
                name = col["name"]
                typ = col["type"]
                value = dj.get(name, "")
                item = QTableWidgetItem()

                if typ == "Число":
                    try:
                        num = float(str(value).replace(" ", "").replace(",", "."))
                        if num == int(num):
                            item.setData(Qt.DisplayRole, int(num))
                        else:
                            item.setData(Qt.DisplayRole, num)
                        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    except Exception:
                        item.setText(str(value))
                elif typ == "Медиа":
                    photos = value if isinstance(value, list) else []
                    cnt = len(photos)
                    item.setText(f"🖼 {cnt}" if cnt > 0 else "□")
                    item.setTextAlignment(Qt.AlignCenter)
                elif typ == "Статус":
                    item.setText(str(value))
                    item.setTextAlignment(Qt.AlignCenter)
                elif typ in ("Дата", "Годен до", "Дата проведения", "Date", "Date of", "Valid until"):
                    item.setText(str(value))
                    item.setTextAlignment(Qt.AlignCenter)
                elif name == "ID":
                    item.setText(str(rec.get("id", "")))
                    item.setTextAlignment(Qt.AlignCenter)
                else:
                    item.setText(str(value))

                item.setData(Qt.UserRole, rec.get("id", 0))
                item.setData(Qt.UserRole + 1, name)

                bg = self._get_cell_color(typ, str(value), dj, name)
                if bg:
                    item.setBackground(bg)

                self._table.setItem(row_idx, col_idx, item)

        self._table.resizeColumnsToContents()
        self._table.blockSignals(False)
        self._update_info()

    def _get_cell_color(self, typ: str, value: str,
                        data: Dict[str, Any],
                        field_name: str) -> Optional[QColor]:
        is_dark = ThemeEngine._current_theme == "dark"
        now = datetime.now()

        if typ in ("Дата проведения", "Date of") and value:
            date_mode = str(data.get(f"{field_name}_mode", "Дата проведения"))
            return get_date_indicator_bg(value, is_dark, date_mode)

        if typ == "Статус":
            return get_status_indicator_bg(value, is_dark)

        if typ in ("Годен до", "Valid until") and value:
            return get_valid_until_bg(value, is_dark)

        if typ in ("Дата", "Date") and value:
            date_mode = str(data.get(f"{field_name}_mode", "Действует до"))
            return get_date_indicator_bg(value, is_dark, date_mode)
        return None


    def _update_info(self) -> None:
        total = len(self._all_records)
        shown = len(self._records)
        text = f"{I18n._('common.filter')}: {shown} / {total}"
        self._info_label.setText(text)
        try:
            p = self.parent()
            if p and hasattr(p, 'setTabText'):
                tw = p
            else:
                tw = getattr(p, 'parent', lambda: None)() if p else None
            if tw and hasattr(tw, 'setTabText'):
                for i in range(tw.count()):
                    if tw.widget(i) is self:
                        tw.setTabText(i, f"{I18n._('tab.violations')} ({total})")
                        break
        except Exception:
            pass

    # -----------------------------------------------------------------------
    # Sorting
    # -----------------------------------------------------------------------

    def _on_header_clicked(self, col_idx: int) -> None:
        if self._sort_col == col_idx:
            if self._sort_order == Qt.AscendingOrder:
                self._sort_order = Qt.DescendingOrder
            else:
                self._sort_col = -1
                self._sort_order = Qt.AscendingOrder
        else:
            self._sort_col = col_idx
            self._sort_order = Qt.AscendingOrder
        self._sort_data()
        self._render_table()

    def _sort_data(self) -> None:
        if self._sort_col < 0 or self._sort_col >= len(self._columns):
            self._records.sort(key=lambda r: str(r.get("data_json", {}).get("Описание", "")).lower())
            return
        col = self._columns[self._sort_col]
        name = col["name"]
        typ = col["type"]

        def sort_key(rec: Dict[str, Any]) -> Any:
            dj = rec.get("data_json", {})
            val = dj.get(name, "")
            if typ == "Число":
                try:
                    return float(str(val).replace(" ", "").replace(",", "."))
                except Exception:
                    return 0.0
            if typ in ("Дата", "Годен до", "Дата проведения", "Date", "Date of", "Valid until"):
                try:
                    p = str(val).split(".")
                    if len(p) == 3:
                        return datetime(int(p[2]), int(p[1]), int(p[0])).isoformat()
                except Exception:
                    pass  # expected
                return str(val)
            return str(val).lower()

        reverse = self._sort_order == Qt.DescendingOrder
        self._records.sort(key=sort_key, reverse=reverse)

    # -----------------------------------------------------------------------
    # CRUD
    # -----------------------------------------------------------------------

    def _add_record(self) -> None:
        dlg = ViolationEditDialog({}, self._columns, self)
        if dlg.exec_() == QDialog.Accepted:
            data = dlg.get_data()
            try:
                duplicate = self.db.find_violation_duplicate(data, user_id=self._user_id)
                if duplicate:
                    merged = dict(duplicate.get("data_json", {}))
                    merged.update({k: v for k, v in data.items() if str(v).strip() != ""})
                    self.db.save_json_record("violations", duplicate["id"], merged,
                                             user_id=self._user_id)
                    self._load_data()
                    ToastNotification.notify(I18n._("viol.duplicate_updated"), "success", 3000)
                    self.db.merge_duplicates("violations")
                    return
                rid = self.db.save_json_record("violations", 0, data,
                                               user_id=self._user_id)
                if dlg.should_create_reminder():
                    deadline = data.get("Срок устранения", "")
                    title = f"{I18n._('viol.deadline')}: #{rid}"
                    self.db.save_reminder(title, data.get("Описание", ""), deadline)
                    ToastNotification.notify(I18n._("toast.reminder"), "info", 3000)
                self.db.merge_duplicates("violations")
                self._load_data()
                ToastNotification.notify(I18n._("common.success"), "success", 3000)            
            except Exception:
                ToastNotification.notify(I18n._("error.generic"), "error", 5000)
                return

    def _edit_record(self, record: Dict[str, Any]) -> None:
        dj = record.get("data_json", {})
        dlg = ViolationEditDialog(dj, self._columns, self)
        if dlg.exec_() == QDialog.Accepted:
            data = dlg.get_data()
            try:
                duplicate = self.db.find_violation_duplicate(data, exclude_id=record["id"], user_id=self._user_id)
                if duplicate:
                    QMessageBox.warning(self, I18n._("common.warning"), I18n._("viol.duplicate_found"))
                    return
                self.db.save_json_record("violations", record["id"], data,
                                         user_id=self._user_id)
                self.db.merge_duplicates("violations")
                self._load_data()
                ToastNotification.notify(I18n._("common.success"), "success", 3000)
            except Exception:
                ToastNotification.notify(I18n._("error.generic"), "error", 5000)

    def _edit_selected(self) -> None:
        row = self._table.currentRow()
        if row < 0 or row >= len(self._records):
            return
        self._edit_record(self._records[row])

    def _delete_selected(self) -> None:
        rows = set()
        for idx in self._table.selectedIndexes():
            rows.add(idx.row())
        if not rows:
            return
        reply = QMessageBox.question(
            self, I18n._("common.confirm"),
            I18n._("viol.delete_confirm"),
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        for row in sorted(rows, reverse=True):
            if 0 <= row < len(self._records):
                rid = self._records[row].get("id", 0)
                if rid:
                    self.db.delete_json_record("violations", rid)
        self._load_data()
        ToastNotification.notify(I18n._("toast.delete_success"), "success", 3000)

    def _export_selected(self) -> None:
        row = self._table.currentRow()
        if row < 0 or row >= len(self._records):
            ToastNotification.notify(I18n._("common.no_selection"), "warning", 3000)
            return
        rec = self._records[row]
        dj = rec.get("data_json", {})
        from PyQt5.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(self, I18n._("export.title"),
                                               f"record_{rec['id']}.csv",
                                               "CSV (*.csv)")
        if not path:
            return
        try:
            import csv
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow([c["name"] for c in self._columns])
                row_data = [dj.get(c["name"], "") for c in self._columns]
                w.writerow(row_data)
            ToastNotification.notify(I18n._("export.success").format(path=path), "success", 3000)
        except Exception as e:
            ToastNotification.notify(I18n._("export.error").format(error=str(e)), "error", 5000)

    def _print_selected(self) -> None:
        rows = sorted(set(idx.row() for idx in self._table.selectedIndexes()))
        if not rows:
            ToastNotification.notify(I18n._("common.no_selection"), "warning", 3000)
            return
        records = []
        for row in rows:
            if row >= 0 and row < len(self._records):
                records.append(self._records[row])
        if not records:
            return
        html = PrintEngine.render_with_template(self, "order", records, self._columns)
        PrintEngine.print_document(html)

    def _open_photos(self) -> None:
        row = self._table.currentRow()
        if row < 0 or row >= len(self._records):
            return
        row_data = self._records[row]
        dj = row_data.get("data_json", {})
        photos = dj.get("Фото", [])
        if not isinstance(photos, list):
            photos = []
        dlg = PhotoGalleryDialog(photos, self)
        if dlg.exec_() == QDialog.Accepted:
            dj["Фото"] = dlg.get_photos()
            try:
                self.db.save_json_record("violations", rec["id"], dj,
                                         user_id=self._user_id)
                self._load_data()
            except Exception:
                ToastNotification.notify(I18n._("error.generic"), "error", 5000)

    def _open_textbook(self) -> None:
        dlg = TextbookDialog(self)
        dlg.exec_()

    def _open_type_manager(self) -> None:
        dlg = ViolationTypeDialog(self)
        dlg.exec_()

    # -----------------------------------------------------------------------
    # In-place Editing
    # -----------------------------------------------------------------------

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        row = item.row()
        col = item.column()
        if row < 0 or row >= len(self._records) or col < 0 or col >= len(self._columns):
            return
        rec = self._records[row]
        dj = rec.get("data_json", {})
        name = self._columns[col]["name"]
        typ = self._columns[col]["type"]
        if typ == "Медиа":
            return
        if name == "ID":
            return
        new_value = item.text().strip()
        formatted = auto_format_date(new_value)
        dj[name] = formatted
        try:
            self.db.save_json_record("violations", rec["id"], dj,
                                     user_id=self._user_id)
        except Exception:
            ToastNotification.notify(I18n._("error.generic"), "error", 5000)

    def _open_notes(self) -> None:
        row = self._table.currentRow()
        if row < 0 or row >= len(self._records):
            ToastNotification.notify(I18n._("common.no_selection"), "warning", 3000)
            return
        rec = self._records[row]
        dlg = NotesDialog("violations", rec["id"], self)
        dlg.exec_()

    # -----------------------------------------------------------------------
    # Context Menus
    # -----------------------------------------------------------------------

    def _on_header_context_menu(self, pos: QPoint) -> None:
        col_idx = self._table.horizontalHeader().logicalIndexAt(pos)
        if col_idx < 0:
            return
        col = self._columns[col_idx]
        menu = QMenu(self)
        rename_a = menu.addAction(I18n._("column.rename"))
        add_a = menu.addAction(I18n._("column.add"))
        del_a = menu.addAction(I18n._("column.delete"))
        chg_a = menu.addAction(I18n._("column.change_type"))
        action = menu.exec_(self._table.horizontalHeader().mapToGlobal(pos))
        if action == rename_a:
            self._rename_column(col)
        elif action == add_a:
            self._add_column()
        elif action == del_a:
            self._delete_column(col)
        elif action == chg_a:
            self._change_column_type(col)

    def _rename_column(self, col: Dict[str, Any]) -> None:
        new_name, ok = QInputDialog.getText(
            self, I18n._("column.rename"), I18n._("column.rename_prompt"),
            text=col["name"])
        if ok and new_name:
            if self.db.rename_column("violations", col["name"], new_name):
                self._load_data()
                ToastNotification.notify(I18n._("common.success"), "success", 3000)
            else:
                QMessageBox.warning(self, I18n._("common.warning"),
                                    I18n._("column.duplicate_error"))

    def _add_column(self) -> None:
        name, ok = QInputDialog.getText(
            self, I18n._("column.add"), I18n._("column.add_prompt"))
        if ok and name:
            types_list = [I18n._("column.type_text"), I18n._("column.type_number"),
                          I18n._("column.type_date"), I18n._("column.type_date_conducted"),
                          I18n._("column.type_status"), I18n._("column.type_media")]
            typ, ok2 = QInputDialog.getItem(
                self, I18n._("column.change_type"), "", types_list, 0, False)
            if ok2 and typ:
                tm = {I18n._("column.type_text"): "Текст",
                      I18n._("column.type_number"): "Число",
                      I18n._("column.type_date"): "Годен до",
                      I18n._("column.type_date_conducted"): "Дата проведения",
                      I18n._("column.type_status"): "Статус",
                      I18n._("column.type_media"): "Медиа"}
                if self.db.add_column("violations", name, tm.get(typ, "Текст")):
                    self._load_data()
                    ToastNotification.notify(I18n._("common.success"), "success", 3000)

    def _delete_column(self, col: Dict[str, Any]) -> None:
        reply = QMessageBox.question(
            self, I18n._("common.confirm"),
            f"{I18n._('column.delete')}: '{col['name']}'?",
            QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            if self.db.delete_column("violations", col["name"]):
                self._load_data()
                ToastNotification.notify(I18n._("toast.delete_success"), "success", 3000)

    def _change_column_type(self, col: Dict[str, Any]) -> None:
        types_list = [I18n._("column.type_text"), I18n._("column.type_number"),
                      I18n._("column.type_date"), I18n._("column.type_date_conducted"),
                      I18n._("column.type_status"), I18n._("column.type_media")]
        typ, ok = QInputDialog.getItem(
            self, I18n._("column.change_type"), "", types_list, 0, False)
        if ok and typ:
            tm = {I18n._("column.type_text"): "Текст",
                  I18n._("column.type_number"): "Число",
                  I18n._("column.type_date"): "Годен до",
                  I18n._("column.type_date_conducted"): "Дата проведения",
                  I18n._("column.type_status"): "Статус",
                  I18n._("column.type_media"): "Медиа"}
            try:
                self.db.create_backup()
                self.db.conn.execute(
                    "UPDATE columns_config SET type=? WHERE category=? AND name=?",
                    (tm.get(typ, "Текст"), "violations", col["name"]))
                self.db.conn.commit()
                self._load_data()
                ToastNotification.notify(I18n._("common.success"), "success", 3000)
            except Exception:
                ToastNotification.notify(I18n._("error.generic"), "error", 5000)

    def _on_table_context_menu(self, pos: QPoint) -> None:
        row = self._table.rowAt(pos.y())
        if row < 0:
            return
        self._table.selectRow(row)
        menu = QMenu(self)
        edit_a = menu.addAction(I18n._("common.edit"))
        del_a = menu.addAction(I18n._("common.delete"))
        photo_a = menu.addAction("📷 " + I18n._("viol.photo"))
        print_a = menu.addAction("🖨 " + I18n._("print.any_table"))
        menu.addSeparator()
        copy_a = menu.addAction(I18n._("common.copy"))
        action = menu.exec_(self._table.mapToGlobal(pos))
        if action == edit_a:
            self._edit_selected()
        elif action == del_a:
            self._delete_selected()
        elif action == photo_a:
            self._open_photos()
        elif action == print_a:
            self._print_selected()
        elif action == copy_a:
            item = self._table.item(row, self._table.currentColumn())
            if item and item.text():
                QApplication.clipboard().setText(item.text())

    def refresh(self) -> None:
        self._load_data()

    def focus_record(self, record_id: Any) -> bool:
        self._load_data()
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if item and item.text().strip() == str(record_id):
                self._table.selectRow(row)
                self._table.scrollToItem(item, QAbstractItemView.PositionAtCenter)
                return True
        return False


# ===========================================================================
# END OF PART 4 — BEGIN PART 5: Companies, Custom Ledger, Column Utils
# ===========================================================================

# ---------------------------------------------------------------------------
# SECTION 5.1: Company Edit Dialog
# ---------------------------------------------------------------------------

class CompanyEditDialog(QDialog):
    def __init__(self, data: Optional[Dict[str, Any]] = None,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._data = dict(data or {})
        is_new = not bool(self._data.get("id"))
        self.setWindowTitle(I18n._("company.add") if is_new else I18n._("company.edit"))
        self.setMinimumSize(450, 300)
        self.resize(500, 320)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)
        heading = QLabel(I18n._("company.edit") if self._data.get("id")
                         else I18n._("company.add"))
        heading.setProperty("heading", True)
        layout.addWidget(heading)

        form = QFormLayout()
        form.setSpacing(10)
        self._name_edit = QLineEdit(self._data.get("name", ""))
        form.addRow(f"{I18n._('company.name')}:", self._name_edit)
        self._addr_edit = QLineEdit(self._data.get("address", ""))
        form.addRow(f"{I18n._('company.address')}:", self._addr_edit)
        self._contact_edit = QLineEdit(self._data.get("contact", ""))
        form.addRow(f"{I18n._('company.contact')}:", self._contact_edit)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_data(self) -> Dict[str, str]:
        return {
            "name": self._name_edit.text().strip(),
            "address": self._addr_edit.text().strip(),
            "contact": self._contact_edit.text().strip(),
        }


# ---------------------------------------------------------------------------
# SECTION 5.2: Companies Tab
# ---------------------------------------------------------------------------

class CompaniesTab(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.db = DatabaseManager()
        self._build_ui()
        self._load_data()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        heading = QLabel(I18n._("tab.companies"))
        heading.setProperty("heading", True)
        layout.addWidget(heading)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        self._add_btn = QPushButton(I18n._("company.add"))
        self._add_btn.clicked.connect(self._add_company)
        toolbar.addWidget(self._add_btn)
        self._edit_btn = QPushButton(I18n._("common.edit"))
        self._edit_btn.clicked.connect(self._edit_company)
        toolbar.addWidget(self._edit_btn)
        self._delete_btn = QPushButton(I18n._("common.delete"))
        self._delete_btn.clicked.connect(self._delete_company)
        toolbar.addWidget(self._delete_btn)
        self._refresh_btn = QPushButton(I18n._("common.refresh"))
        self._refresh_btn.setProperty("flat", True)
        self._refresh_btn.clicked.connect(self._load_data)
        toolbar.addWidget(self._refresh_btn)

        self._print_btn = QPushButton("🖨 " + I18n._("print.any_table"))
        self._print_btn.setProperty("flat", True)
        self._print_btn.clicked.connect(self._print_selected)
        toolbar.addWidget(self._print_btn)

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText(I18n._("common.search_hint"))
        self._search_edit.setMaximumWidth(250)
        self._search_edit.textChanged.connect(self._filter_table)
        toolbar.addWidget(self._search_edit)

        toolbar.addStretch()

        layout.addLayout(toolbar)

        self._table = QTableWidget()
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().hide()
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        headers = [I18n._("company.id"), I18n._("company.name"),
                   I18n._("company.address"), I18n._("company.contact"),
                   I18n._("company.employees_count"), I18n._("company.violations_count"),
                   I18n._("company.fines_total")]
        self._table.setColumnCount(len(headers))
        self._table.setHorizontalHeaderLabels(headers)
        self._table.setSortingEnabled(True)
        self._table.itemDoubleClicked.connect(self._edit_company)
        layout.addWidget(wrap_table_with_glow(self._table, self))

    def _load_data(self) -> None:
        companies = self.db.get_companies()
        self._table.setRowCount(len(companies))
        for i, c in enumerate(companies):
            cid = c["id"]
            self._table.setItem(i, 0, QTableWidgetItem(str(cid)))
            self._table.setItem(i, 1, QTableWidgetItem(c.get("name", "")))
            self._table.setItem(i, 2, QTableWidgetItem(c.get("address", "")))
            self._table.setItem(i, 3, QTableWidgetItem(c.get("contact", "")))

            emp_count = 0
            viol_count = 0
            fines = 0.0
            name = c.get("name", "")
            for emp in self.db.get_json_records("employees"):
                dj = emp.get("data_json", {})
                if dj.get("Фирма") == name:
                    emp_count += 1
            for viol in self.db.get_json_records("violations"):
                dj = viol.get("data_json", {})
                if dj.get("Фирма") == name:
                    viol_count += 1
                    try:
                        fines += float(str(dj.get("Штраф", "0"))
                                       .replace(" ", "").replace(",", "."))
                    except Exception:
                        pass  # expected

            self._table.setItem(i, 4, QTableWidgetItem(str(emp_count)))
            self._table.setItem(i, 5, QTableWidgetItem(str(viol_count)))
            fine_item = QTableWidgetItem(f"{fines:,.0f} ₽".replace(",", " "))
            fine_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._table.setItem(i, 6, fine_item)
        self._table.resizeColumnsToContents()
        self._all_companies: List[Dict[str, Any]] = companies

    def _filter_table(self) -> None:
        query = self._search_edit.text().strip().lower()
        filtered = self._all_companies if not query else [
            c for c in self._all_companies
            if query in str(c.get("name", "")).lower()
            or query in str(c.get("address", "")).lower()
            or query in str(c.get("contact", "")).lower()
        ]
        self._table.setRowCount(len(filtered))
        for i, c in enumerate(filtered):
            cid = c["id"]
            self._table.setItem(i, 0, QTableWidgetItem(str(cid)))
            self._table.setItem(i, 1, QTableWidgetItem(c.get("name", "")))
            self._table.setItem(i, 2, QTableWidgetItem(c.get("address", "")))
            self._table.setItem(i, 3, QTableWidgetItem(c.get("contact", "")))
            emp_count = 0
            viol_count = 0
            fines = 0.0
            name = c.get("name", "")
            for emp in self.db.get_json_records("employees"):
                dj = emp.get("data_json", {})
                if dj.get("Фирма") == name:
                    emp_count += 1
            for viol in self.db.get_json_records("violations"):
                dj = viol.get("data_json", {})
                if dj.get("Фирма") == name:
                    viol_count += 1
                    try:
                        fines += float(str(dj.get("Штраф", "0"))
                                       .replace(" ", "").replace(",", "."))
                    except Exception:
                        pass
            self._table.setItem(i, 4, QTableWidgetItem(str(emp_count)))
            self._table.setItem(i, 5, QTableWidgetItem(str(viol_count)))
            fine_item = QTableWidgetItem(f"{fines:,.0f} ₽".replace(",", " "))
            fine_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._table.setItem(i, 6, fine_item)
        self._table.resizeColumnsToContents()

    def _add_company(self) -> None:
        dlg = CompanyEditDialog(parent=self)
        if dlg.exec_() == QDialog.Accepted:
            data = dlg.get_data()
            if data["name"]:
                try:
                    self.db.save_company(data["name"], data["address"], data["contact"])
                    self._load_data()
                    ToastNotification.notify(I18n._("common.success"), "success", 3000)
                except sqlite3.IntegrityError:
                    QMessageBox.warning(self, I18n._("common.warning"),
                                        f"{I18n._('company.name')} '{data['name']}' "
                                        f"{I18n._('column.duplicate_error')}")

    def _edit_company(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            return
        cid = int(self._table.item(row, 0).text())
        comp = self.db.get_company(cid)
        if not comp:
            return
        dlg = CompanyEditDialog(dict(comp), self)
        if dlg.exec_() == QDialog.Accepted:
            data = dlg.get_data()
            if data["name"]:
                try:
                    self.db.save_company(data["name"], data["address"],
                                         data["contact"], company_id=cid)
                    self._load_data()
                    ToastNotification.notify(I18n._("common.success"), "success", 3000)
                except sqlite3.IntegrityError:
                    QMessageBox.warning(self, I18n._("common.warning"),
                                        I18n._("column.duplicate_error"))

    def _delete_company(self) -> None:
        rows = set()
        for idx in self._table.selectedIndexes():
            rows.add(idx.row())
        if not rows:
            return
        reply = QMessageBox.question(
            self, I18n._("common.confirm"),
            f"{I18n._('common.delete')} {len(rows)} {I18n._('company.name').lower()}?",
            QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            for row in sorted(rows, reverse=True):
                cid = int(self._table.item(row, 0).text())
                self.db.delete_company(cid)
        self._load_data()
        ToastNotification.notify(I18n._("toast.delete_success"), "success", 3000)

    def _print_selected(self) -> None:
        rows = sorted(set(idx.row() for idx in self._table.selectedIndexes()))
        if not rows:
            ToastNotification.notify(I18n._("common.no_selection"), "warning", 3000)
            return
        parts = []
        for row in rows:
            if row < 0 or row >= self._table.rowCount():
                continue
            name = self._table.item(row, 1).text() if self._table.item(row, 1) else ""
            address = self._table.item(row, 2).text() if self._table.item(row, 2) else ""
            contact = self._table.item(row, 3).text() if self._table.item(row, 3) else ""
            emp_c = self._table.item(row, 4).text() if self._table.item(row, 4) else "0"
            viol_c = self._table.item(row, 5).text() if self._table.item(row, 5) else "0"
            fines = self._table.item(row, 6).text() if self._table.item(row, 6) else "0"
            lines = [
                f"<h1>{I18n._('company.title')}: {name}</h1><table>",
                f"<tr><td><b>{I18n._('company.address')}</b></td><td>{address}</td></tr>",
                f"<tr><td><b>{I18n._('company.contact')}</b></td><td>{contact}</td></tr>",
                f"<tr><td><b>{I18n._('company.employees_count')}</b></td><td>{emp_c}</td></tr>",
                f"<tr><td><b>{I18n._('company.violations_count')}</b></td><td>{viol_c}</td></tr>",
                f"<tr><td><b>{I18n._('company.fines_total')}</b></td><td>{fines}</td></tr>",
                "</table><hr>",
            ]
            parts.append("".join(lines))
        if not parts:
            return
        html = "<html><body>" + "".join(parts) + "</body></html>"
        PrintEngine.print_document(html)

    def _export_selected(self) -> None:
        rows = sorted(set(idx.row() for idx in self._table.selectedIndexes()))
        if not rows:
            ToastNotification.notify(I18n._("common.no_selection"), "warning", 3000)
            return
        import csv
        from PyQt5.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(self, I18n._("export.title"),
                                               "companies.csv", "CSV (*.csv)")
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                headers = []
                for c in range(self._table.columnCount()):
                    item = self._table.horizontalHeaderItem(c)
                    headers.append(item.text() if item else str(c))
                w.writerow(headers)
                for row in rows:
                    row_data = []
                    for c in range(self._table.columnCount()):
                        item = self._table.item(row, c)
                        row_data.append(item.text() if item else "")
                    w.writerow(row_data)
            ToastNotification.notify(I18n._("export.success").format(path=path), "success", 3000)
        except Exception as e:
            ToastNotification.notify(I18n._("export.error").format(error=str(e)), "error", 5000)

    def refresh(self) -> None:
        self._load_data()


# ---------------------------------------------------------------------------
# SECTION 5.3: Custom Ledger Edit Dialog
# ---------------------------------------------------------------------------

class CustomLedgerEditDialog(QDialog):
    def __init__(self, data: Dict[str, Any] = None,
                 columns: List[Dict[str, Any]] = None,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._data = dict(data or {})
        self._columns = columns or []
        self._fields: Dict[str, QWidget] = {}
        self.setWindowTitle(I18n._("ledger.edit") if data else I18n._("ledger.add"))
        self.setMinimumSize(500, 400)
        self.resize(550, 450)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)
        heading = QLabel(I18n._("ledger.edit") if self._data.get("id")
                         else I18n._("ledger.add"))
        heading.setProperty("heading", True)
        layout.addWidget(heading)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        container = QWidget()
        form = QFormLayout(container)
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight)

        for col in self._columns:
            name = col["name"]
            typ = col["type"]
            if name == "ID":
                continue
            if typ == "Медиа":
                continue
            value = self._data.get(name, "")
            if typ == "Число":
                w = QSpinBox()
                w.setRange(0, 999999999)
                w.setMinimumHeight(36)
                try:
                    w.setValue(int(float(str(value).replace(" ", "").replace(",", "."))))
                except Exception:
                    w.setValue(0)
            elif typ in ("Дата", "Годен до", "Дата проведения", "Date", "Date of", "Valid until"):
                w = DateAwareLineEdit()
                w.setMinimumHeight(36)
                w.setText(str(value))
            elif typ == "Статус":
                w = QComboBox()
                w.setMinimumHeight(36)
                w.addItems(["Активно", "Исполнено", "Архив"])
                idx = w.findText(str(value))
                if idx >= 0:
                    w.setCurrentIndex(idx)
            else:
                w = QLineEdit(str(value))
                w.setMinimumHeight(36)
            self._fields[name] = w
            form.addRow(f"{name}:", w)

        scroll.setWidget(container)
        layout.addWidget(scroll, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


    def get_data(self) -> Dict[str, Any]:
        result = dict(self._data)
        for col in self._columns:
            name = col["name"]
            if name == "ID" or col["type"] == "Медиа":
                continue
            w = self._fields.get(name)
            if w is None:
                continue
            if isinstance(w, QSpinBox):
                result[name] = str(w.value())
            elif isinstance(w, QComboBox):
                result[name] = w.currentText()
            else:
                result[name] = w.text().strip()
        return result


# ---------------------------------------------------------------------------
# SECTION 5.4: Custom Ledger Table Widget
# ---------------------------------------------------------------------------

class CustomLedgerTableWidget(QWidget):
    def __init__(self, parent: Optional[QWidget] = None,
                 user_id: int = 0) -> None:
        super().__init__(parent)
        self.db = DatabaseManager()
        self._user_id = user_id
        self._columns: List[Dict[str, Any]] = []
        self._records: List[Dict[str, Any]] = []
        self._all_records: List[Dict[str, Any]] = []
        self._sort_col: int = -1
        self._sort_order: int = Qt.AscendingOrder
        self._build_ui()
        self._load_data()

    def set_user_id(self, uid: int) -> None:
        self._user_id = uid
        self._load_data()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        self._search_edit = QLineEdit()
        self._search_edit.setProperty("search", True)
        self._search_edit.setPlaceholderText(I18n._("search.placeholder"))
        self._search_edit.setMinimumHeight(36)
        self._search_timer = QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(self._apply_filter)
        self._search_edit.textChanged.connect(self._search_timer.start)
        toolbar.addWidget(self._search_edit, 1)

        self._add_btn = QPushButton(I18n._("ledger.add"))
        self._add_btn.clicked.connect(self._add_record)
        toolbar.addWidget(self._add_btn)
        self._edit_btn = QPushButton(I18n._("common.edit"))
        self._edit_btn.clicked.connect(self._edit_selected)
        toolbar.addWidget(self._edit_btn)
        self._delete_btn = QPushButton(I18n._("common.delete"))
        self._delete_btn.clicked.connect(self._delete_selected)
        toolbar.addWidget(self._delete_btn)
        self._photos_btn = QPushButton("📷 " + I18n._("ledger.photo"))
        self._photos_btn.setProperty("flat", True)
        self._photos_btn.clicked.connect(self._open_photos)
        toolbar.addWidget(self._photos_btn)
        self._notes_btn = QPushButton("📝 " + I18n._("common.notes"))
        self._notes_btn.setProperty("flat", True)
        self._notes_btn.clicked.connect(self._open_notes)
        toolbar.addWidget(self._notes_btn)
        self._export_btn = QPushButton("📤 " + I18n._("export.title"))
        self._export_btn.setProperty("flat", True)
        self._export_btn.clicked.connect(self._export_selected)
        toolbar.addWidget(self._export_btn)
        self._print_btn = QPushButton("🖨 " + I18n._("print.any_table"))
        self._print_btn.setProperty("flat", True)
        self._print_btn.clicked.connect(self._print_selected)
        toolbar.addWidget(self._print_btn)
        self._refresh_btn = QPushButton(I18n._("common.refresh"))
        self._refresh_btn.setProperty("flat", True)
        self._refresh_btn.clicked.connect(self._load_data)
        toolbar.addWidget(self._refresh_btn)

        layout.addLayout(toolbar)

        self._table = QTableWidget()
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().hide()
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionsClickable(True)
        self._table.horizontalHeader().setSectionsMovable(True)
        self._table.horizontalHeader().sectionClicked.connect(self._on_header_clicked)
        self._table.horizontalHeader().setContextMenuPolicy(Qt.CustomContextMenu)
        self._table.horizontalHeader().customContextMenuRequested.connect(
            self._on_header_context_menu)
        self._table.horizontalHeader().sectionDoubleClicked.connect(
            lambda idx: self._table.resizeColumnToContents(idx))
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.itemChanged.connect(self._on_item_changed)
        self._table.itemDoubleClicked.connect(lambda: self._edit_selected())
        
        self._table.setSortingEnabled(False)
        self._table.setContextMenuPolicy(Qt.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_table_context_menu)
        self._table.verticalHeader().setDefaultSectionSize(36)
        layout.addWidget(wrap_table_with_glow(self._table, self))

        self._info_label = QLabel()
        self._info_label.setStyleSheet("font-size: 12px; padding: 4px 0;")
        layout.addWidget(self._info_label)

    # -----------------------------------------------------------------------
    # Data
    # -----------------------------------------------------------------------

    def _load_data(self) -> None:
        self._columns = self.db.get_columns_config("custom_ledger")
        records = self.db.get_json_records("custom_ledger",
                                           user_id=self._user_id)
        self._all_records = records
        self._search_edit.clear()
        self._apply_filter()

    def _apply_filter(self) -> None:
        search_text = self._search_edit.text().strip().lower()
        is_regex = search_text.startswith("/") and search_text.endswith("/")
        regex_pattern = search_text[1:-1] if is_regex else ""
        self._records = []
        for r in self._all_records:
            dj = r.get("data_json", {})
            if search_text:
                found = False
                if is_regex:
                    try:
                        pat = re.compile(regex_pattern, re.IGNORECASE)
                        for val in dj.values():
                            if isinstance(val, str) and pat.search(val):
                                found = True
                                break
                    except re.error:
                        pass
                else:
                    for val in dj.values():
                        if isinstance(val, str) and search_text in val.lower():
                            found = True
                            break
                if not found:
                    continue
            self._records.append(r)
        self._render_table()

    # -----------------------------------------------------------------------
    # Rendering
    # -----------------------------------------------------------------------

    def _render_table(self) -> None:
        self._table.blockSignals(True)
        self._table.setRowCount(0)
        cols = self._columns
        self._table.setColumnCount(len(cols))
        self._table.setHorizontalHeaderLabels([c["name"] for c in cols])
        self._table.setRowCount(len(self._records))
        for row_idx, rec in enumerate(self._records):
            dj = rec.get("data_json", {})
            for col_idx, col in enumerate(cols):
                name = col["name"]
                typ = col["type"]
                value = dj.get(name, "")
                item = QTableWidgetItem()
                if typ == "Число":
                    try:
                        num = float(str(value).replace(" ", "").replace(",", "."))
                        item.setData(Qt.DisplayRole, int(num) if num == int(num) else num)
                        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    except Exception:
                        item.setText(str(value))
                elif typ == "Медиа":
                    photos = value if isinstance(value, list) else []
                    item.setText(f"🖼 {len(photos)}" if photos else "□")
                    item.setTextAlignment(Qt.AlignCenter)
                elif typ == "Статус":
                    item.setText(str(value))
                    item.setTextAlignment(Qt.AlignCenter)
                elif typ in ("Дата", "Годен до", "Дата проведения", "Date", "Date of", "Valid until"):
                    item.setText(str(value))
                    item.setTextAlignment(Qt.AlignCenter)
                else:
                    item.setText(str(value))
                item.setData(Qt.UserRole, rec.get("id", 0))
                item.setData(Qt.UserRole + 1, name)
                bg = self._get_cell_color(typ, str(value), dj, name)
                if bg:
                    item.setBackground(bg)
                self._table.setItem(row_idx, col_idx, item)
        self._table.resizeColumnsToContents()
        self._table.blockSignals(False)
        total = len(self._all_records)
        shown = len(self._records)
        self._info_label.setText(f"{I18n._('common.filter')}: {shown} / {total}")
        try:
            p = self.parent()
            if p and hasattr(p, 'setTabText'):
                tw = p
            else:
                tw = getattr(p, 'parent', lambda: None)() if p else None
            if tw and hasattr(tw, 'setTabText'):
                for i in range(tw.count()):
                    if tw.widget(i) is self:
                        tw.setTabText(i, f"{I18n._('tab.custom_ledger')} ({total})")
                        break
        except Exception:
            pass

    def _get_cell_color(self, typ: str, value: str,
                        data: Dict[str, Any],
                        field_name: str) -> Optional[QColor]:
        is_dark = ThemeEngine._current_theme == "dark"
        now = datetime.now()
        if typ in ("Дата проведения", "Date of") and value:
            date_mode = str(data.get(f"{field_name}_mode", "Дата проведения"))
            return get_date_indicator_bg(value, is_dark, date_mode)
        if typ == "Статус":
            return get_status_indicator_bg(value, is_dark)
        if typ in ("Годен до", "Valid until") and value:
            return get_valid_until_bg(value, is_dark)
        if typ in ("Дата", "Date") and value:
            date_mode = str(data.get(f"{field_name}_mode", "Действует до"))
            return get_date_indicator_bg(value, is_dark, date_mode)
        return None


    # -----------------------------------------------------------------------
    # Sorting
    # -----------------------------------------------------------------------

    def _on_header_clicked(self, col_idx: int) -> None:
        if self._sort_col == col_idx:
            if self._sort_order == Qt.AscendingOrder:
                self._sort_order = Qt.DescendingOrder
            else:
                self._sort_col = -1
                self._sort_order = Qt.AscendingOrder
        else:
            self._sort_col = col_idx
            self._sort_order = Qt.AscendingOrder
        self._sort_data()
        self._render_table()

    def _sort_data(self) -> None:
        if self._sort_col < 0 or self._sort_col >= len(self._columns):
            return
        col = self._columns[self._sort_col]
        name = col["name"]
        typ = col["type"]

        def sort_key(rec: Dict[str, Any]) -> Any:
            dj = rec.get("data_json", {})
            val = dj.get(name, "")
            if typ == "Число":
                try:
                    return float(str(val).replace(" ", "").replace(",", "."))
                except Exception:
                    return 0.0
            if typ in ("Дата", "Годен до", "Дата проведения", "Date", "Date of", "Valid until"):
                try:
                    p = str(val).split(".")
                    if len(p) == 3:
                        return datetime(int(p[2]), int(p[1]), int(p[0])).isoformat()
                except Exception:
                    pass  # expected
            return str(val).lower()

        self._records.sort(key=sort_key,
                           reverse=(self._sort_order == Qt.DescendingOrder))

    # -----------------------------------------------------------------------
    # CRUD
    # -----------------------------------------------------------------------

    def _add_record(self) -> None:
        dlg = ViolationEditDialog({}, self._columns, self)
        if dlg.exec_() == QDialog.Accepted:
            data = dlg.get_data()
            try:
                duplicate = self.db.find_violation_duplicate(data, user_id=self._user_id)
                if duplicate:
                    merged = dict(duplicate.get("data_json", {}))
                    merged.update({k: v for k, v in data.items() if str(v).strip() != ""})
                    self.db.save_json_record("violations", duplicate["id"], merged,
                                             user_id=self._user_id)
                    self._load_data()
                    ToastNotification.notify(I18n._("viol.duplicate_updated"), "success", 3000)
                    self.db.merge_duplicates("custom_ledger")
                    return
                self.db.save_json_record("violations", 0, data,
                                         user_id=self._user_id)
                self.db.merge_duplicates("custom_ledger")
                self._load_data()
                ToastNotification.notify(I18n._("common.success"), "success", 3000)
            except Exception:
                ToastNotification.notify(I18n._("error.generic"), "error", 5000)


    def _edit_selected(self) -> None:
        row = self._table.currentRow()
        if row < 0 or row >= len(self._records):
            return
        rec = self._records[row]
        dj = rec.get("data_json", {})
        dlg = CustomLedgerEditDialog(dj, self._columns, self)
        if dlg.exec_() == QDialog.Accepted:
            data = dlg.get_data()
            try:
                self.db.save_json_record("custom_ledger", rec["id"], data,
                                         user_id=self._user_id)
                self.db.merge_duplicates("custom_ledger")
                self._load_data()
                ToastNotification.notify(I18n._("common.success"), "success", 3000)
            except Exception:
                ToastNotification.notify(I18n._("error.generic"), "error", 5000)

    def _delete_selected(self) -> None:
        rows = set()
        for idx in self._table.selectedIndexes():
            rows.add(idx.row())
        if not rows:
            return
        reply = QMessageBox.question(
            self, I18n._("common.confirm"),
            I18n._("ledger.delete_confirm"),
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        for row in sorted(rows, reverse=True):
            if 0 <= row < len(self._records):
                rid = self._records[row].get("id", 0)
                if rid:
                    self.db.delete_json_record("custom_ledger", rid)
        self._load_data()
        ToastNotification.notify(I18n._("toast.delete_success"), "success", 3000)

    def _print_selected(self) -> None:
        rows = sorted(set(idx.row() for idx in self._table.selectedIndexes()))
        if not rows:
            ToastNotification.notify(I18n._("common.no_selection"), "warning", 3000)
            return
        records = []
        for row in rows:
            if row >= 0 and row < len(self._records):
                records.append(self._records[row])
        if not records:
            return
        html = PrintEngine.render_with_template(self, "report", records, self._columns)
        PrintEngine.print_document(html)

    def _export_selected(self) -> None:
        row = self._table.currentRow()
        if row < 0 or row >= len(self._records):
            ToastNotification.notify(I18n._("common.no_selection"), "warning", 3000)
            return
        rec = self._records[row]
        dj = rec.get("data_json", {})
        from PyQt5.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(self, I18n._("export.title"),
                                               f"record_{rec['id']}.csv",
                                               "CSV (*.csv)")
        if not path:
            return
        try:
            import csv
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow([c["name"] for c in self._columns])
                row_data = [dj.get(c["name"], "") for c in self._columns]
                w.writerow(row_data)
            ToastNotification.notify(I18n._("export.success").format(path=path), "success", 3000)
        except Exception as e:
            ToastNotification.notify(I18n._("export.error").format(error=str(e)), "error", 5000)

    def _open_photos(self) -> None:
        row = self._table.currentRow()
        if row < 0 or row >= len(self._records):
            return
        rec = self._records[row]
        dj = rec.get("data_json", {})
        photos = dj.get("Фото", [])
        if not isinstance(photos, list):
            photos = []
        dlg = PhotoGalleryDialog(photos, self)
        if dlg.exec_() == QDialog.Accepted:
            dj["Фото"] = dlg.get_photos()
            try:
                self.db.save_json_record("custom_ledger", rec["id"], dj,
                                         user_id=self._user_id)
                self._load_data()
            except Exception:
                ToastNotification.notify(I18n._("error.generic"), "error", 5000)

    # -----------------------------------------------------------------------
    # In-place editing
    # -----------------------------------------------------------------------

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        row = item.row()
        col = item.column()
        if row < 0 or row >= len(self._records) or col < 0 or col >= len(self._columns):
            return
        rec = self._records[row]
        dj = rec.get("data_json", {})
        name = self._columns[col]["name"]
        if self._columns[col]["type"] == "Медиа":
            return
        if name == "ID":
            return
        dj[name] = item.text().strip()
        try:
            self.db.save_json_record("custom_ledger", rec["id"], dj,
                                     user_id=self._user_id)
        except Exception:
            ToastNotification.notify(I18n._("error.generic"), "error", 5000)

    def _open_notes(self) -> None:
        row = self._table.currentRow()
        if row < 0 or row >= len(self._records):
            ToastNotification.notify(I18n._("common.no_selection"), "warning", 3000)
            return
        rec = self._records[row]
        dlg = NotesDialog("custom_ledger", rec["id"], self)
        dlg.exec_()

    # -----------------------------------------------------------------------
    # Context Menus
    # -----------------------------------------------------------------------

    def _on_header_context_menu(self, pos: QPoint) -> None:
        col_idx = self._table.horizontalHeader().logicalIndexAt(pos)
        if col_idx < 0:
            return
        col = self._columns[col_idx]
        menu = QMenu(self)
        rename_a = menu.addAction(I18n._("column.rename"))
        add_a = menu.addAction(I18n._("column.add"))
        del_a = menu.addAction(I18n._("column.delete"))
        chg_a = menu.addAction(I18n._("column.change_type"))
        action = menu.exec_(self._table.horizontalHeader().mapToGlobal(pos))
        if action == rename_a:
            new_name, ok = QInputDialog.getText(
                self, I18n._("column.rename"), I18n._("column.rename_prompt"),
                text=col["name"])
            if ok and new_name and self.db.rename_column("custom_ledger", col["name"], new_name):
                self._load_data()
                ToastNotification.notify(I18n._("common.success"), "success", 3000)
            elif ok and new_name:
                QMessageBox.warning(self, I18n._("common.warning"),
                                    I18n._("column.duplicate_error"))
            elif ok:
                QMessageBox.warning(self, I18n._("common.warning"),
                                    I18n._("column.name_empty"))
        elif action == add_a:
            name, ok = QInputDialog.getText(self, I18n._("column.add"),
                                            I18n._("column.add_prompt"))
            if ok and name:
                types_list = [I18n._("column.type_text"), I18n._("column.type_number"),
                              I18n._("column.type_date"),
                              I18n._("column.type_date_conducted"),
                              I18n._("column.type_status"), I18n._("column.type_media")]
                typ, ok2 = QInputDialog.getItem(self, I18n._("column.change_type"),
                                                "", types_list, 0, False)
                if ok2 and typ:
                    tm = {I18n._("column.type_text"): "Текст",
                          I18n._("column.type_number"): "Число",
                          I18n._("column.type_date"): "Годен до",
                          I18n._("column.type_date_conducted"): "Дата проведения",
                          I18n._("column.type_status"): "Статус",
                          I18n._("column.type_media"): "Медиа"}
                    if self.db.add_column("custom_ledger", name, tm.get(typ, "Текст")):
                        self._load_data()
                        ToastNotification.notify(I18n._("common.success"), "success", 3000)
        elif action == del_a:
            reply = QMessageBox.question(self, I18n._("common.confirm"),
                f"{I18n._('column.delete')}: '{col['name']}'?",
                QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes and self.db.delete_column("custom_ledger", col["name"]):
                self._load_data()
                ToastNotification.notify(I18n._("toast.delete_success"), "success", 3000)
        elif action == chg_a:
            types_list = [I18n._("column.type_text"), I18n._("column.type_number"),
                          I18n._("column.type_date"), I18n._("column.type_date_conducted"),
                          I18n._("column.type_status"), I18n._("column.type_media")]
            typ, ok = QInputDialog.getItem(self, I18n._("column.change_type"),
                                           "", types_list, 0, False)
            if ok and typ:
                tm = {I18n._("column.type_text"): "Текст",
                      I18n._("column.type_number"): "Число",
                      I18n._("column.type_date"): "Годен до",
                      I18n._("column.type_date_conducted"): "Дата проведения",
                      I18n._("column.type_status"): "Статус",
                      I18n._("column.type_media"): "Медиа"}
                try:
                    self.db.create_backup()
                    self.db.conn.execute(
                        "UPDATE columns_config SET type=? WHERE category=? AND name=?",
                        (tm.get(typ, "Текст"), "custom_ledger", col["name"]))
                    self.db.conn.commit()
                    self._load_data()
                    ToastNotification.notify(I18n._("common.success"), "success", 3000)
                except Exception:
                    ToastNotification.notify(I18n._("error.generic"), "error", 5000)

    def _on_table_context_menu(self, pos: QPoint) -> None:
        row = self._table.rowAt(pos.y())
        if row < 0:
            return
        self._table.selectRow(row)
        menu = QMenu(self)
        edit_a = menu.addAction(I18n._("common.edit"))
        del_a = menu.addAction(I18n._("common.delete"))
        photo_a = menu.addAction("📷 " + I18n._("ledger.photo"))
        print_a = menu.addAction("🖨 " + I18n._("print.any_table"))
        menu.addSeparator()
        copy_a = menu.addAction(I18n._("common.copy"))
        action = menu.exec_(self._table.mapToGlobal(pos))
        if action == edit_a:
            self._edit_selected()
        elif action == del_a:
            self._delete_selected()
        elif action == photo_a:
            self._open_photos()
        elif action == print_a:
            self._print_selected()
        elif action == copy_a:
            item = self._table.item(row, self._table.currentColumn())
            if item and item.text():
                QApplication.clipboard().setText(item.text())

    def refresh(self) -> None:
        self._load_data()

    def focus_record(self, record_id: Any) -> bool:
        self._load_data()
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if item and item.text().strip() == str(record_id):
                self._table.selectRow(row)
                self._table.scrollToItem(item, QAbstractItemView.PositionAtCenter)
                return True
        return False


# ---------------------------------------------------------------------------
# SECTION 5.5: Statistics Tab
# ---------------------------------------------------------------------------

class StatisticsTab(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.db = DatabaseManager()
        self._build_ui()
        self._refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(20)

        heading = QLabel(I18n._("stat.title"))
        heading.setProperty("heading", True)
        layout.addWidget(heading)

        cards = QHBoxLayout()
        cards.setSpacing(16)
        stats = self.db.get_statistics()
        self._cards: Dict[str, KpiCard] = {}
        card_data = [
            ("stat.employees_total", "employees_total", "#2196F3", "👤"),
            ("stat.violations_total", "violations_total", "#E74C3C", "⚠"),
            ("stat.companies_total", "companies_total", "#27AE60", "🏢"),
            ("stat.overdue_total", "overdue_total", "#F39C12", "⏰"),
            ("stat.fines_total", "fines_total", "#9C27B0", "💰"),
        ]
        for key, skey, color, icon in card_data:
            val = stats.get(skey, 0) if skey != "fines_total" else f"{stats.get(skey, 0):,.0f} ₽".replace(",", " ")
            card = KpiCard(I18n._(key), str(val), color, icon)
            cards.addWidget(card)
            self._cards[skey] = card
        layout.addLayout(cards)

        mid = QHBoxLayout()
        mid.setSpacing(20)

        by_company = QFrame()
        by_company.setProperty("card", True)
        by_company_layout = QVBoxLayout(by_company)
        by_company_layout.setContentsMargins(16, 16, 16, 16)
        co_heading = QLabel(I18n._("stat.by_company"))
        co_heading.setProperty("heading", True)
        co_heading.setStyleSheet("font-size: 16px;")
        by_company_layout.addWidget(co_heading)
        self._company_table = QTableWidget()
        self._company_table.setColumnCount(4)
        self._company_table.setHorizontalHeaderLabels([
            I18n._("company.name"), I18n._("company.employees_count"),
            I18n._("company.violations_count"), I18n._("company.fines_total")])
        self._company_table.resizeColumnsToContents()
        self._company_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self._company_table.horizontalHeader().setStretchLastSection(True)
        self._company_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._company_table.setAlternatingRowColors(True)
        self._company_table.verticalHeader().hide()
        by_company_layout.addWidget(self._company_table)
        mid.addWidget(by_company, 1)

        by_category = QFrame()
        by_category.setProperty("card", True)
        by_category_layout = QVBoxLayout(by_category)
        by_category_layout.setContentsMargins(16, 16, 16, 16)
        cat_heading = QLabel(I18n._("stat.by_category"))
        cat_heading.setProperty("heading", True)
        cat_heading.setStyleSheet("font-size: 16px;")
        by_category_layout.addWidget(cat_heading)
        self._category_table = QTableWidget()
        self._category_table.setColumnCount(2)
        self._category_table.setHorizontalHeaderLabels([
            I18n._("viol.risk_category"), I18n._("common.count")])
        self._category_table.resizeColumnsToContents()
        self._category_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self._category_table.horizontalHeader().setStretchLastSection(True)
        self._category_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._category_table.setAlternatingRowColors(True)
        self._category_table.verticalHeader().hide()
        by_category_layout.addWidget(self._category_table)
        mid.addWidget(by_category, 1)

        layout.addLayout(mid)

        # Detailed analytics row
        bottom = QHBoxLayout()
        bottom.setSpacing(20)

        status_frame = QFrame()
        status_frame.setProperty("card", True)
        status_layout = QVBoxLayout(status_frame)
        status_layout.setContentsMargins(16, 16, 16, 16)
        st_heading = QLabel(I18n._("stat.status_distribution"))
        st_heading.setProperty("heading", True)
        st_heading.setStyleSheet("font-size: 16px;")
        status_layout.addWidget(st_heading)
        self._status_table = QTableWidget()
        self._status_table.setColumnCount(2)
        self._status_table.setHorizontalHeaderLabels([
            I18n._("common.status"), I18n._("common.count")])
        self._status_table.resizeColumnsToContents()
        self._status_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self._status_table.horizontalHeader().setStretchLastSection(True)
        self._status_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._status_table.setAlternatingRowColors(True)
        self._status_table.verticalHeader().hide()
        status_layout.addWidget(self._status_table)
        bottom.addWidget(status_frame, 1)

        overdue_frame = QFrame()
        overdue_frame.setProperty("card", True)
        overdue_layout = QVBoxLayout(overdue_frame)
        overdue_layout.setContentsMargins(16, 16, 16, 16)
        ov_heading = QLabel(I18n._("stat.overdue_trend"))
        ov_heading.setProperty("heading", True)
        ov_heading.setStyleSheet("font-size: 16px;")
        overdue_layout.addWidget(ov_heading)
        self._overdue_label = QLabel()
        self._overdue_label.setWordWrap(True)
        self._overdue_label.setStyleSheet("font-size: 13px; color: #E74C3C; padding: 8px;")
        overdue_layout.addWidget(self._overdue_label)
        bottom.addWidget(overdue_frame, 1)

        layout.addLayout(bottom)

        self._refresh_btn = QPushButton(I18n._("common.refresh"))
        self._refresh_btn.setProperty("flat", True)
        self._refresh_btn.clicked.connect(self._refresh)
        layout.addWidget(self._refresh_btn, 0, Qt.AlignLeft)

    def _refresh(self) -> None:
        stats = self.db.get_statistics()
        for skey in self._cards:
            if skey == "fines_total":
                self._cards[skey].setText(
                    f"{stats.get(skey, 0):,.0f} ₽".replace(",", " "))
            else:
                self._cards[skey].setText(str(stats.get(skey, 0)))

        companies = self.db.get_companies()
        self._company_table.setRowCount(len(companies))
        for i, c in enumerate(companies):
            name = c.get("name", "")
            emp_count = 0
            viol_count = 0
            fines = 0.0
            for emp in self.db.get_json_records("employees"):
                if emp.get("data_json", {}).get("Фирма") == name:
                    emp_count += 1
            for viol in self.db.get_json_records("violations"):
                dj = viol.get("data_json", {})
                if dj.get("Фирма") == name:
                    viol_count += 1
                    try:
                        fines += float(str(dj.get("Штраф", "0"))
                                       .replace(" ", "").replace(",", "."))
                    except Exception:
                        pass  # expected
            self._company_table.setItem(i, 0, QTableWidgetItem(name))
            self._company_table.setItem(i, 1, QTableWidgetItem(str(emp_count)))
            self._company_table.setItem(i, 2, QTableWidgetItem(str(viol_count)))
            fine_item = QTableWidgetItem(f"{fines:,.0f} ₽".replace(",", " "))
            fine_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._company_table.setItem(i, 3, fine_item)

        categories: Dict[str, int] = {}
        statuses: Dict[str, int] = {}
        now = datetime.now()
        overdue_list = []
        for viol in self.db.get_json_records("violations"):
            dj = viol.get("data_json", {})
            cat = dj.get("Категория риска", "Не указана")
            categories[cat] = categories.get(cat, 0) + 1
            status = dj.get("Статус", "Не указан")
            statuses[status] = statuses.get(status, 0) + 1
            deadline = dj.get("Срок устранения", "")
            try:
                if deadline:
                    parts = deadline.split(".")
                    if len(parts) == 3:
                        dt = datetime(int(parts[2]), int(parts[1]), int(parts[0]))
                        if dt < now and status != "Исполнено":
                            overdue_list.append(f"- {dj.get('Описание', '?')[:40]} (до {deadline})")
            except Exception:
                pass  # expected

        self._category_table.setRowCount(len(categories))
        for i, (cat, cnt) in enumerate(sorted(categories.items(),
                                               key=lambda x: -x[1])):
            self._category_table.setItem(i, 0, QTableWidgetItem(cat))
            self._category_table.setItem(i, 1, QTableWidgetItem(str(cnt)))

        self._status_table.setRowCount(len(statuses))
        for i, (st, cnt) in enumerate(sorted(statuses.items(),
                                              key=lambda x: -x[1])):
            self._status_table.setItem(i, 0, QTableWidgetItem(st))
            self._status_table.setItem(i, 1, QTableWidgetItem(str(cnt)))

        self._overdue_label.setText(
            f"Просрочено: {len(overdue_list)}\n" + "\n".join(overdue_list[:10])
            if overdue_list else "Нет просрочек")

        self._company_table.resizeColumnsToContents()
        self._category_table.resizeColumnsToContents()
        self._status_table.resizeColumnsToContents()

    def refresh(self) -> None:
        self._refresh()


# ===========================================================================
# END OF PART 5 — BEGIN PART 6: Notes, Reminders, Print Engine
# ===========================================================================

# ---------------------------------------------------------------------------
# SECTION 6.1: Notes Dialog (Rich Text / Global + Entity)
# ---------------------------------------------------------------------------

class NotesDialog(QDialog):
    def __init__(self, entity_type: str = "global", entity_id: int = 0,
                 entity_name: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.db = DatabaseManager()
        self._entity_type = entity_type
        self._entity_id = entity_id
        self.setWindowTitle(f"{I18n._('notes.title')} — {entity_name}" if entity_name
                            else I18n._("notes.title"))
        self.setMinimumSize(600, 450)
        self.resize(700, 500)
        self._build_ui()
        self._load_notes()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        heading = QLabel(I18n._("notes.title"))
        heading.setProperty("heading", True)
        layout.addWidget(heading)

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText(I18n._("common.search_hint"))
        self._search_edit.textChanged.connect(self._filter_notes)
        layout.addWidget(self._search_edit)

        self._list = QListWidget()
        self._list.itemClicked.connect(self._on_note_selected)
        layout.addWidget(self._list)

        self._editor = QTextEdit()
        self._editor.setPlaceholderText(I18n._("notes.placeholder"))
        self._editor.setMinimumHeight(120)
        layout.addWidget(self._editor)

        btn_layout = QHBoxLayout()
        self._add_btn = QPushButton(I18n._("notes.add"))
        self._add_btn.setProperty("success", True)
        self._add_btn.clicked.connect(self._add_note)
        btn_layout.addWidget(self._add_btn)
        self._save_btn = QPushButton(I18n._("common.save"))
        self._save_btn.clicked.connect(self._save_note)
        btn_layout.addWidget(self._save_btn)
        self._delete_btn = QPushButton(I18n._("notes.delete"))
        self._delete_btn.setProperty("danger", True)
        self._delete_btn.clicked.connect(self._delete_note)
        btn_layout.addWidget(self._delete_btn)
        btn_layout.addStretch()
        self._close_btn = QPushButton(I18n._("common.close"))
        self._close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self._close_btn)
        layout.addLayout(btn_layout)

        self._current_note_id: Optional[int] = None

    def _filter_notes(self) -> None:
        query = self._search_edit.text().strip().lower()
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item:
                item.setHidden(bool(query) and query not in item.text().lower())

    def _load_notes(self) -> None:
        self._list.clear()
        notes = self.db.get_notes(self._entity_type, self._entity_id)
        for n in notes:
            content = n.get("content", "")
            preview = content[:80].replace("<", "&lt;").replace(">", "&gt;").replace("\n", " ") if content else ""
            title = n.get("title") or I18n._("notes.title") + f" #{n['id']}"
            item = QListWidgetItem(f"{title} — {preview}" if preview else title)
            item.setData(Qt.UserRole, n["id"])
            item.setData(Qt.UserRole + 1, content)
            item.setToolTip(content[:200].replace("<", "&lt;").replace(">", "&gt;") if content else "")
            self._list.addItem(item)

    def _on_note_selected(self, item: QListWidgetItem) -> None:
        self._current_note_id = item.data(Qt.UserRole)
        content = item.data(Qt.UserRole + 1) or ""
        self._editor.setHtml(content)

    def _add_note(self) -> None:
        self._current_note_id = None
        self._editor.clear()
        self._editor.setFocus()

    def _save_note(self) -> None:
        content = self._editor.toHtml() if self._editor.toPlainText().strip() else ""
        if not content:
            return
        title = I18n._("notes.title") + f" #{self._current_note_id or ''}"
        try:
            self.db.save_note(self._entity_type, self._entity_id,
                              title, content, self._current_note_id or 0)
            self._load_notes()
            ToastNotification.notify(I18n._("common.success"), "success", 3000)
        except Exception:
            ToastNotification.notify(I18n._("error.generic"), "error", 5000)

    def _delete_note(self) -> None:
        if not self._current_note_id:
            return
        reply = QMessageBox.question(self, I18n._("common.confirm"),
                                     I18n._("notes.delete") + "?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.db.delete_note(self._current_note_id)
            self._current_note_id = None
            self._editor.clear()
            self._load_notes()
            ToastNotification.notify(I18n._("toast.delete_success"), "success", 3000)


# ---------------------------------------------------------------------------
# SECTION 6.2: Reminders Dialog
# ---------------------------------------------------------------------------

class RemindersDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.db = DatabaseManager()
        self.setWindowTitle(I18n._("reminder.all"))
        self.setMinimumSize(550, 450)
        self.resize(600, 500)
        self._build_ui()
        self._load_reminders()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        heading = QLabel(I18n._("reminder.title"))
        heading.setProperty("heading", True)
        layout.addWidget(heading)

        self._table = QTableWidget()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels([
            I18n._("reminder.title_field"), I18n._("reminder.description"),
            I18n._("reminder.due_date"), I18n._("reminder.interval"),
            I18n._("reminder.is_done")])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().hide()
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(wrap_table_with_glow(self._table, self))

        btn_layout = QHBoxLayout()
        self._add_btn = QPushButton(I18n._("reminder.add"))
        self._add_btn.setProperty("success", True)
        self._add_btn.clicked.connect(self._add_reminder)
        btn_layout.addWidget(self._add_btn)
        self._edit_btn = QPushButton(I18n._("common.edit"))
        self._edit_btn.clicked.connect(self._edit_reminder)
        btn_layout.addWidget(self._edit_btn)
        self._delete_btn = QPushButton(I18n._("reminder.delete"))
        self._delete_btn.setProperty("danger", True)
        self._delete_btn.clicked.connect(self._delete_reminder)
        btn_layout.addWidget(self._delete_btn)
        self._toggle_btn = QPushButton(I18n._("common.done"))
        self._toggle_btn.clicked.connect(self._toggle_done)
        btn_layout.addWidget(self._toggle_btn)
        btn_layout.addStretch()
        close_btn = QPushButton(I18n._("common.close"))
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

    def _load_reminders(self) -> None:
        reminders = self.db.get_reminders(include_done=True)
        self._table.setRowCount(len(reminders))
        for i, r in enumerate(reminders):
            self._table.setItem(i, 0, QTableWidgetItem(r.get("title", "")))
            desc = r.get("description", "")
            self._table.setItem(i, 1, QTableWidgetItem(
                desc[:60] + ("..." if len(desc) > 60 else "")))
            self._table.setItem(i, 2, QTableWidgetItem(r.get("due_date", "")))
            self._table.setItem(i, 3, QTableWidgetItem(f"{r.get('check_interval', 60)}c"))
            done_item = QTableWidgetItem(
                "✓" if r.get("is_done") else "☐")
            done_item.setTextAlignment(Qt.AlignCenter)
            self._table.setItem(i, 4, done_item)
            self._table.item(i, 0).setData(Qt.UserRole, r["id"])
        self._table.resizeColumnsToContents()

    def _add_reminder(self) -> None:
        title, ok = QInputDialog.getText(self, I18n._("reminder.add"),
                                         I18n._("reminder.title_field"))
        if not ok or not title:
            return
        desc, ok2 = QInputDialog.getMultiLineText(self, I18n._("reminder.add"),
                                                   I18n._("reminder.description"))
        if not ok2:
            desc = ""
        due, ok3 = QInputDialog.getText(self, I18n._("reminder.add"),
                                         I18n._("reminder.due_date"),
                                         text=datetime.now().strftime("%d.%m.%Y"))
        if not ok3 or not due:
            return
        interval, ok4 = QInputDialog.getInt(self, I18n._("reminder.add"),
                                             I18n._("reminder.interval"), 60, 10, 86400)
        if not ok4:
            return
        self.db.save_reminder(title.strip(), desc.strip(), due.strip(), interval)
        self._load_reminders()
        ToastNotification.notify(I18n._("common.success"), "success", 3000)

    def _edit_reminder(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            return
        rid = self._table.item(row, 0).data(Qt.UserRole)
        title = self._table.item(row, 0).text()
        desc = self._table.item(row, 1).text()
        due = self._table.item(row, 2).text()

        new_title, ok = QInputDialog.getText(self, I18n._("reminder.edit"),
                                              I18n._("reminder.title_field"),
                                              text=title)
        if not ok:
            return
        new_due, ok2 = QInputDialog.getText(self, I18n._("reminder.edit"),
                                             I18n._("reminder.due_date"),
                                             text=due)
        if not ok2:
            return
        self.db.save_reminder(new_title.strip(), desc, new_due.strip(),
                              60, reminder_id=rid)
        self._load_reminders()
        ToastNotification.notify(I18n._("common.success"), "success", 3000)

    def _delete_reminder(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            return
        rid = self._table.item(row, 0).data(Qt.UserRole)
        reply = QMessageBox.question(self, I18n._("common.confirm"),
                                     I18n._("reminder.delete") + "?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.db.delete_reminder(rid)
            self._load_reminders()
            ToastNotification.notify(I18n._("toast.delete_success"), "success", 3000)

    def _toggle_done(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            return
        rid = self._table.item(row, 0).data(Qt.UserRole)
        reminders = self.db.get_reminders(include_done=True)
        for r in reminders:
            if r["id"] == rid:
                new_done = 0 if r.get("is_done") else 1
                self.db.save_reminder(r["title"], r.get("description", ""),
                                      r["due_date"], r.get("check_interval", 60),
                                      is_done=new_done, reminder_id=rid)
                break
        self._load_reminders()


# ---------------------------------------------------------------------------
# SECTION 6.3: Reminder Background Engine
# ---------------------------------------------------------------------------

class ReminderEngine(QObject):
    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.db = DatabaseManager()
        self._notified: set = set()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._check)
        self._interval = int(self.db.get_setting("reminder_check_interval", "60"))
        self._timer.start(self._interval * 1000)

    def _check(self) -> None:
        try:
            reminders = self.db.get_due_reminders()
            now = datetime.now()
            for r in reminders:
                rid = r.get("id", 0)
                if rid in self._notified:
                    continue
                due_str = r.get("due_date", "")
                try:
                    p = due_str.split(".")
                    if len(p) == 3:
                        due = datetime(int(p[2]), int(p[1]), int(p[0]))
                        if due <= now and not r.get("is_done"):
                            self._notified.add(rid)
                            title = r.get("title", I18n._("reminder.title"))
                            ToastNotification.notify(
                                f"🔔 {title}", "warning", 8000)
                except Exception:
                    pass
            # Clean up old done reminders from notified set
            if reminders:
                active = {r["id"] for r in reminders}
                self._notified &= active
        except Exception:
            pass

    def update_interval(self, interval: int) -> None:
        self._interval = max(10, interval)
        self._timer.setInterval(self._interval * 1000)

    def stop(self) -> None:
        self._timer.stop()


class ExpiringRemindersTab(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.db = DatabaseManager()
        self._quick_filter = self.db.get_setting("reminder_quick_filter", "all")
        self._build_ui()
        self._load_data()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        heading = QLabel(I18n._("reminder.title"))
        heading.setProperty("heading", True)
        layout.addWidget(heading)

        hint = QLabel(I18n._("reminder.expiring_hint"))
        hint.setWordWrap(True)
        hint.setStyleSheet("font-size: 12px;")
        layout.addWidget(hint)

        quick_layout = QHBoxLayout()
        self._quick_buttons: Dict[str, QPushButton] = {}
        self._quick_button_labels: Dict[str, str] = {}
        for key, label_key in [
            ("all", "reminder.quick_all"),
            ("overdue", "reminder.quick_overdue"),
            ("3days", "reminder.quick_3days"),
            ("30days", "reminder.quick_30days"),
        ]:
            btn = QPushButton(I18n._(label_key))
            btn.setProperty("flat", True)
            btn.clicked.connect(lambda _=False, k=key: self._set_quick_filter(k))
            quick_layout.addWidget(btn)
            self._quick_buttons[key] = btn
            self._quick_button_labels[key] = label_key
        quick_layout.addStretch()
        layout.addLayout(quick_layout)

        filter_layout = QHBoxLayout()
        self._overdue_only_cb = QCheckBox(I18n._("reminder.overdue_only"))
        self._overdue_only_cb.toggled.connect(self._apply_filters)
        filter_layout.addWidget(self._overdue_only_cb)
        filter_layout.addSpacing(16)
        filter_layout.addWidget(QLabel(I18n._("reminder.sort_order") + ":"))
        self._sort_combo = QComboBox()
        self._sort_combo.addItem(I18n._("reminder.sort_priority"), "priority")
        self._sort_combo.addItem(I18n._("reminder.sort_due_asc"), "due_asc")
        self._sort_combo.addItem(I18n._("reminder.sort_due_desc"), "due_desc")
        saved_sort = self.db.get_setting("reminder_sort_order", "priority")
        idx = self._sort_combo.findData(saved_sort)
        if idx >= 0:
            self._sort_combo.setCurrentIndex(idx)
        self._sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        filter_layout.addWidget(self._sort_combo)
        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        splitter = QSplitter(Qt.Vertical)
        self._overdue_group = QGroupBox(I18n._("reminder.overdue_section"))
        overdue_layout = QVBoxLayout(self._overdue_group)
        self._overdue_table = self._create_table()
        self._overdue_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self._overdue_table.customContextMenuRequested.connect(lambda pos: self._show_table_menu(self._overdue_table, pos))
        self._overdue_table.itemDoubleClicked.connect(lambda item: self._open_item_from_table(self._overdue_table, item.row()))
        overdue_layout.addWidget(self._overdue_table)
        splitter.addWidget(self._overdue_group)

        self._upcoming_group = QGroupBox(I18n._("reminder.upcoming_section"))
        upcoming_layout = QVBoxLayout(self._upcoming_group)
        self._upcoming_table = self._create_table()
        self._upcoming_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self._upcoming_table.customContextMenuRequested.connect(lambda pos: self._show_table_menu(self._upcoming_table, pos))
        self._upcoming_table.itemDoubleClicked.connect(lambda item: self._open_item_from_table(self._upcoming_table, item.row()))
        upcoming_layout.addWidget(self._upcoming_table)
        splitter.addWidget(self._upcoming_group)
        splitter.setSizes([220, 300])
        layout.addWidget(splitter, 1)

        btn_layout = QHBoxLayout()
        self._refresh_btn = QPushButton(I18n._("common.refresh"))
        self._refresh_btn.clicked.connect(self._load_data)
        btn_layout.addWidget(self._refresh_btn)
        self._export_csv_btn = QPushButton(I18n._("common.export") + " CSV")
        self._export_csv_btn.clicked.connect(lambda: self._export_reminders("csv"))
        btn_layout.addWidget(self._export_csv_btn)
        self._export_excel_btn = QPushButton(I18n._("common.export") + " Excel")
        self._export_excel_btn.clicked.connect(lambda: self._export_reminders("xlsx"))
        btn_layout.addWidget(self._export_excel_btn)
        btn_layout.addStretch()
        self._open_btn = QPushButton(I18n._("reminder.all"))
        self._open_btn.clicked.connect(self._open_all)
        btn_layout.addWidget(self._open_btn)
        layout.addLayout(btn_layout)

        self._auto_refresh_timer = QTimer(self)
        self._auto_refresh_timer.timeout.connect(self._load_data)
        self._auto_refresh_timer.start(120000)

        self._update_quick_filter_buttons()

    def _create_table(self) -> QTableWidget:
        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels([
            I18n._("reminder.type"), I18n._("reminder.title_field"),
            I18n._("reminder.entity"), I18n._("reminder.due_date"),
            I18n._("reminder.days_left")])
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        table.setColumnWidth(1, 140)
        table.setColumnWidth(2, 180)
        table.setColumnWidth(3, 120)
        table.setColumnWidth(4, 100)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setAlternatingRowColors(True)
        table.verticalHeader().hide()
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSortingEnabled(False)
        return table

    def _set_quick_filter(self, key: str) -> None:
        self._quick_filter = key
        self.db.upsert_setting("reminder_quick_filter", key)
        self._update_quick_filter_buttons()
        self._apply_filters()

    def _update_quick_filter_buttons(self) -> None:
        accent = self.db.get_setting("accent_color", "#2196F3")
        items = list(getattr(self, "_items", []))
        counters = {
            "all": len(items),
            "overdue": len([x for x in items if x.get("days", 999) < 0]),
            "3days": len([x for x in items if 0 <= x.get("days", 999) <= 3]),
            "30days": len([x for x in items if 0 <= x.get("days", 999) <= 30]),
        }
        for key, btn in getattr(self, "_quick_buttons", {}).items():
            active = key == getattr(self, "_quick_filter", "all")
            label_key = self._quick_button_labels.get(key, "")
            btn.setText(f"{I18n._(label_key)} ({counters.get(key, 0)})")
            btn.setStyleSheet(
                f"padding: 6px 12px; border-radius: 6px;"
                f"background: {accent + ('30' if active else '10')};"
                f"border: 1px solid {accent if active else accent + '30'};"
                f"font-weight: {'600' if active else '500'};")

    def _on_sort_changed(self) -> None:
        self.db.upsert_setting("reminder_sort_order", self._sort_combo.currentData())
        self._apply_filters()

    def _load_data(self) -> None:
        self._items: List[Dict[str, Any]] = []
        now = datetime.now()
        try:
            employees = self.db.get_json_records("employees")
            for emp in employees:
                dj = emp.get("data_json", {})
                for key in ("Дата медосмотра",):
                    val = dj.get(key, "")
                    try:
                        p = val.split(".")
                        if len(p) == 3:
                            dt = datetime(int(p[2]), int(p[1]), int(p[0]))
                            left = (dt - now).days
                            self._items.append({
                                "type": I18n._("tab.employees"),
                                "title": key,
                                "entity": dj.get("ФИО", f"#{emp['id']}"),
                                "due": val,
                                "days": left,
                                "_table": "employees",
                                "_record_id": emp.get("id"),
                                "_ts": dt.timestamp(),
                            })
                    except Exception:
                        pass

            violations = self.db.get_json_records("violations")
            for viol in violations:
                dj = viol.get("data_json", {})
                for key in ("Срок устранения", "Дата", "Годен до"):
                    val = dj.get(key, "")
                    try:
                        p = val.split(".")
                        if len(p) == 3:
                            dt = datetime(int(p[2]), int(p[1]), int(p[0]))
                            left = (dt - now).days
                            self._items.append({
                                "type": I18n._("tab.violations"),
                                "title": key,
                                "entity": f"#{viol['id']} {dj.get('Описание', '')[:30]}",
                                "due": val,
                                "days": left,
                                "_table": "violations",
                                "_record_id": viol.get("id"),
                                "_ts": dt.timestamp(),
                            })
                    except Exception:
                        pass

            reminders = self.db.get_reminders(include_done=False)
            for r in reminders:
                due_str = r.get("due_date", "")
                try:
                    p = due_str.split(".")
                    if len(p) == 3:
                        dt = datetime(int(p[2]), int(p[1]), int(p[0]))
                        left = (dt - now).days
                        self._items.append({
                            "type": I18n._("reminder.title"),
                            "title": r.get("title", ""),
                            "entity": "",
                            "due": due_str,
                            "days": left,
                            "_table": "reminders",
                            "_record_id": r.get("id"),
                            "_id": r["id"],
                            "_done": r.get("is_done", False),
                            "_ts": dt.timestamp(),
                        })
                except Exception:
                    pass
        except Exception:
            import traceback; traceback.print_exc()

        self._apply_filters()

    def _apply_filters(self) -> None:
        items = list(getattr(self, "_items", []))
        quick = getattr(self, "_quick_filter", "all")
        if quick == "overdue":
            items = [item for item in items if item.get("days", 999) < 0]
        elif quick == "3days":
            items = [item for item in items if 0 <= item.get("days", 999) <= 3]
        elif quick == "30days":
            items = [item for item in items if 0 <= item.get("days", 999) <= 30]

        if getattr(self, "_overdue_only_cb", None) and self._overdue_only_cb.isChecked():
            items = [item for item in items if item.get("days", 999) < 0]

        sort_mode = self._sort_combo.currentData() if hasattr(self, "_sort_combo") else "priority"

        def _sort_key(item: Dict[str, Any]) -> Tuple[int, int, float]:
            d = int(item.get("days", 999))
            ts = float(item.get("_ts", 0.0))
            if sort_mode == "due_desc":
                return (0, 0, -ts)
            if sort_mode == "due_asc":
                return (0, 0, ts)
            group = 0 if d < 0 else (1 if d <= 3 else 2)
            return (group, abs(d) if d < 0 else d, ts)

        items.sort(key=_sort_key)
        self._visible_items = items
        overdue_items = [item for item in items if item.get("days", 999) < 0]
        upcoming_items = [item for item in items if item.get("days", 999) >= 0]
        self._fill_table(self._overdue_table, overdue_items)
        self._fill_table(self._upcoming_table, upcoming_items)
        self._overdue_group.setTitle(f"{I18n._('reminder.overdue_section')} ({len(overdue_items)})")
        self._upcoming_group.setTitle(f"{I18n._('reminder.upcoming_section')} ({len(upcoming_items)})")
        self._overdue_group.setVisible(bool(overdue_items) or quick in ("all", "overdue") or self._overdue_only_cb.isChecked())
        self._upcoming_group.setVisible(not self._overdue_only_cb.isChecked())
        self._update_quick_filter_buttons()

    def _fill_table(self, table: QTableWidget, items: List[Dict[str, Any]]) -> None:
        table.setSortingEnabled(False)
        table.setRowCount(len(items))
        icon_map = {
            I18n._("tab.employees"): "👤 ",
            I18n._("tab.violations"): "⚠ ",
            I18n._("reminder.title"): "🔔 ",
        }
        is_dark = ThemeEngine._current_theme == "dark"
        for i, item in enumerate(items):
            prefix = icon_map.get(item["type"], "")
            days = item["days"]
            if days < 0:
                days_str = I18n._("reminder.overdue").format(days=abs(days))
                row_bg = QColor("#582525" if is_dark else "#f8d7da")
            elif days <= 3:
                days_str = I18n._("reminder.today") if days == 0 else I18n._("reminder.days_format").format(days=days)
                row_bg = QColor("#614d17" if is_dark else "#fff3cd")
            else:
                days_str = I18n._("reminder.days_format").format(days=days)
                row_bg = QColor("#254b32" if is_dark else "#d4edda")
            row_fg = QColor("#FFFFFF") if row_bg.lightness() < 140 else QColor("#1E1E2E")
            values = [prefix + item["type"], item["title"], item["entity"], item["due"], days_str]
            for col, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setBackground(row_bg)
                cell.setForeground(row_fg)
                if col == 4:
                    cell.setTextAlignment(Qt.AlignCenter)
                cell.setData(Qt.UserRole, item)
                table.setItem(i, col, cell)
        table.resizeColumnsToContents()
        table.setSortingEnabled(True)

    def _open_item_from_table(self, table: QTableWidget, row: int) -> None:
        item = table.item(row, 0)
        if not item:
            return
        data = item.data(Qt.UserRole) or {}
        mw = self.window()
        if mw and hasattr(mw, "open_reminder_target"):
            mw.open_reminder_target(data)

    def _open_item_from_table(self, table: QTableWidget, row: int) -> None:
        item = table.item(row, 0)
        if not item:
            return
        data = item.data(Qt.UserRole) or {}
        mw = self.window()
        if mw and hasattr(mw, "open_reminder_target"):
            mw.open_reminder_target(data)

    def _show_table_menu(self, table: QTableWidget, pos: QPoint) -> None:
        row = table.rowAt(pos.y())
        if row >= 0:
            table.selectRow(row)
        menu = QMenu(self)
        open_a = menu.addAction(I18n._("common.edit"))
        refresh_a = menu.addAction(I18n._("common.refresh"))
        export_csv_a = menu.addAction(I18n._("common.export") + " CSV")
        export_xlsx_a = menu.addAction(I18n._("common.export") + " Excel")
        action = menu.exec_(table.mapToGlobal(pos))
        if action == open_a and row >= 0:
            self._open_item_from_table(table, row)
        elif action == refresh_a:
            self._load_data()
        elif action == export_csv_a:
            self._export_reminders("csv")
        elif action == export_xlsx_a:
            self._export_reminders("xlsx")

    def _export_reminders(self, fmt: str = "csv") -> None:
        items = list(getattr(self, "_visible_items", []))
        if not items:
            return
        if fmt == "csv":
            path, _ = QFileDialog.getSaveFileName(self, I18n._("export.title"),
                                                  "reminders.csv", "CSV (*.csv)")
            if not path:
                return
            try:
                with open(path, "w", newline="", encoding="utf-8-sig") as f:
                    w = csv.writer(f)
                    w.writerow([I18n._("reminder.type"), I18n._("reminder.title_field"),
                                I18n._("reminder.entity"), I18n._("reminder.due_date"),
                                I18n._("reminder.days_left")])
                    for item in items:
                        days = item.get("days", 0)
                        days_str = I18n._("reminder.overdue").format(days=abs(days)) if days < 0 else (
                            I18n._("reminder.today") if days == 0 else I18n._("reminder.days_format").format(days=days))
                        w.writerow([item.get("type", ""), item.get("title", ""), item.get("entity", ""), item.get("due", ""), days_str])
                ToastNotification.notify(I18n._("export.success").format(path=path), "success", 3000)
            except Exception as e:
                ToastNotification.notify(I18n._("export.error").format(error=str(e)), "error", 5000)
            return
        path, _ = QFileDialog.getSaveFileName(self, I18n._("export.title"),
                                              "reminders.xlsx", "Excel (*.xlsx)")
        if not path:
            return
        try:
            import openpyxl
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Reminders"
            headers = [I18n._("reminder.type"), I18n._("reminder.title_field"),
                       I18n._("reminder.entity"), I18n._("reminder.due_date"),
                       I18n._("reminder.days_left")]
            for c, h in enumerate(headers, 1):
                ws.cell(row=1, column=c, value=h)
            for r, item in enumerate(items, 2):
                days = item.get("days", 0)
                days_str = I18n._("reminder.overdue").format(days=abs(days)) if days < 0 else (
                    I18n._("reminder.today") if days == 0 else I18n._("reminder.days_format").format(days=days))
                vals = [item.get("type", ""), item.get("title", ""), item.get("entity", ""), item.get("due", ""), days_str]
                for c, v in enumerate(vals, 1):
                    ws.cell(row=r, column=c, value=v)
            wb.save(path)
            ToastNotification.notify(I18n._("export.success").format(path=path), "success", 3000)
        except Exception as e:
            ToastNotification.notify(I18n._("export.error").format(error=str(e)), "error", 5000)

    def has_expiring(self) -> bool:
        return any(item.get("days", 999) <= 3 for item in getattr(self, "_items", []))

    def get_expiring_count(self) -> int:
        return len([item for item in getattr(self, "_items", []) if item.get("days", 999) <= 30])

    def _open_all(self) -> None:
        RemindersDialog(self).exec_()

    def refresh(self) -> None:
        self._load_data()
        self._update_quick_filter_buttons()


class ReminderFloatingDialog(QDialog):

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.Window | Qt.WindowStaysOnTopHint | Qt.WindowCloseButtonHint |
            Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint)
        self.setWindowTitle(I18n._("reminder.title"))
        self.setMinimumSize(500, 350)
        self.resize(600, 400)
        self.db = DatabaseManager()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)
        heading = QLabel(I18n._("reminder.title"))
        heading.setProperty("heading", True)
        layout.addWidget(heading)
        self._table = QTableWidget()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels([
            I18n._("reminder.type"), I18n._("reminder.title_field"),
            I18n._("reminder.entity"), I18n._("reminder.due_date"),
            I18n._("reminder.days_left")])
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.Interactive)
        hdr.setStretchLastSection(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().hide()
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self._table, 1)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        close_btn = QPushButton(I18n._("common.close"))
        close_btn.clicked.connect(self.close)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)
        self._load_data()

    def _load_data(self) -> None:
        now = datetime.now()
        items: List[Tuple[str, str, str, str, int, float]] = []
        try:
            for emp in self.db.get_json_records("employees"):
                dj = emp.get("data_json", {})
                for key in ("Дата медосмотра",):
                    val = dj.get(key, "")
                    try:
                        p = val.split(".")
                        if len(p) == 3:
                            dt = datetime(int(p[2]), int(p[1]), int(p[0]))
                            left = (dt - now).days
                            if left <= 30:
                                items.append(("👤 " + I18n._("tab.employees"), key,
                                              dj.get("ФИО", f"#{emp['id']}"), val, left, dt.timestamp()))
                    except Exception:
                        pass
            for viol in self.db.get_json_records("violations"):
                dj = viol.get("data_json", {})
                for key in ("Срок устранения", "Дата", "Годен до"):
                    val = dj.get(key, "")
                    try:
                        p = val.split(".")
                        if len(p) == 3:
                            dt = datetime(int(p[2]), int(p[1]), int(p[0]))
                            left = (dt - now).days
                            if left <= 30:
                                items.append(("⚠ " + I18n._("tab.violations"), key,
                                              f"#{viol['id']}", val, left, dt.timestamp()))
                    except Exception:
                        pass
        except Exception:
            pass
        items.sort(key=lambda x: (0 if x[4] < 0 else 1, x[5]))
        self._table.setRowCount(len(items))
        for i, (typ, title, entity, due, days, _ts) in enumerate(items):
            if days < 0:
                ds = I18n._("reminder.overdue").format(days=abs(days))
            elif days == 0:
                ds = I18n._("reminder.today")
            else:
                ds = I18n._("reminder.days_format").format(days=days)
            self._table.setItem(i, 0, QTableWidgetItem(typ))
            self._table.setItem(i, 1, QTableWidgetItem(title))
            self._table.setItem(i, 2, QTableWidgetItem(entity))
            self._table.setItem(i, 3, QTableWidgetItem(due))
            di = QTableWidgetItem(ds)
            di.setTextAlignment(Qt.AlignCenter)
            if days < 0:
                di.setForeground(QColor("#E53935"))
            elif days <= 3:
                di.setForeground(QColor("#FF9800"))
            else:
                di.setForeground(QColor("#4CAF50"))
            self._table.setItem(i, 4, di)
        self._table.resizeColumnsToContents()


# ---------------------------------------------------------------------------
# SECTION 6.4: Print Engine (HTML5 + Base64 Images)
# ---------------------------------------------------------------------------

class PrintEngine:
    @staticmethod
    def image_to_base64(path: str) -> str:
        try:
            with open(path, "rb") as f:
                data = f.read()
                ext = os.path.splitext(path)[1].lower().replace(".", "")
                mime = mimetypes.guess_type(path)[0] or f"image/{ext}"
                return f"data:{mime};base64,{base64.b64encode(data).decode()}"
        except Exception:
            return ""

    @staticmethod
    def render_order(data: Dict[str, Any],
                     photos: Optional[List[str]] = None,
                     template_html: Optional[str] = None) -> str:
        db = DatabaseManager()
        if not template_html:
            templates = db.get_print_templates("order")
            template_html = templates[0]["html_content"] if templates else ""
        if not template_html:
            template_html = "<h1>Order</h1><p>{description}</p>"

        photos_html = ""
        if photos:
            photo_items = ""
            for p in photos:
                if os.path.isfile(p):
                    b64 = PrintEngine.image_to_base64(p)
                    photo_items += f'<img src="{b64}" alt="photo" />'
            if photo_items:
                photos_html = f'<div class="photos">{photo_items}</div>'

        now_str = datetime.now().strftime("%d.%m.%Y %H:%M")
        ctx = {
            "id": data.get("id", ""),
            "date": data.get("Дата", now_str),
            "company": data.get("Фирма", ""),
            "responsible": data.get("Ответственный", ""),
            "deadline": data.get("Срок устранения", ""),
            "description": data.get("Описание", ""),
            "recommended_action": data.get("Рекомендуемые меры", ""),
            "fine": data.get("Штраф", "0"),
            "photos_section": photos_html,
            "app_name": I18n._("app.name"),
            "generated_at": now_str,
            "record_number": data.get("id", str(data.get("id", ""))),
        }
        result = template_html
        for key, val in ctx.items():
            result = result.replace(f"{{{key}}}", str(val))
        return result

    @staticmethod
    def render_report(company_name: str = "",
                      include_employees: bool = True,
                      include_violations: bool = True,
                      include_fines: bool = True,
                      template_html: Optional[str] = None) -> str:
        db = DatabaseManager()
        if not template_html:
            templates = db.get_print_templates("report")
            template_html = templates[0]["html_content"] if templates else ""
        if not template_html:
            template_html = "<h1>Report</h1><p>{company_name}</p>"

        emp_count = 0
        viol_count = 0
        fines = 0.0
        overdue = 0
        rows_html = ""
        now = datetime.now()

        if company_name:
            companies_data = [{"name": company_name}]
        else:
            companies_data = db.get_companies()

        for company in companies_data:
            cname = company.get("name", "")
            c_emp = 0
            c_viol = 0
            c_fines = 0.0
            c_overdue = 0
            viol_rows = ""

            for emp in db.get_json_records("employees"):
                if emp.get("data_json", {}).get("Фирма") == cname:
                    c_emp += 1

            for viol in db.get_json_records("violations"):
                dj = viol.get("data_json", {})
                if dj.get("Фирма") == cname:
                    c_viol += 1
                    try:
                        f = float(str(dj.get("Штраф", "0"))
                                  .replace(" ", "").replace(",", "."))
                        c_fines += f
                    except Exception:
                        f = 0
                    deadline = dj.get("Срок устранения", "")
                    if deadline:
                        try:
                            p = deadline.split(".")
                            if len(p) == 3:
                                dl = datetime(int(p[2]), int(p[1]), int(p[0]))
                                if dl < now:
                                    c_overdue += 1
                        except Exception:
                            pass  # expected
                    if include_violations:
                        viol_rows += f"""<tr>
                            <td>{dj.get("Дата", "")}</td>
                            <td>{dj.get("Категория риска", "")}</td>
                            <td>{dj.get("Описание", "")[:50]}</td>
                            <td>{dj.get("Ответственный", "")}</td>
                            <td>{dj.get("Срок устранения", "")}</td>
                            <td>{dj.get("Штраф", "0")}</td>
                            <td>{dj.get("Статус", "")}</td>
                        </tr>"""

            emp_count += c_emp
            viol_count += c_viol
            fines += c_fines
            overdue += c_overdue

            if include_employees and include_violations:
                rows_html += f"""<tr>
                    <td>{cname}</td>
                    <td>{c_emp}</td>
                    <td>{c_viol}</td>
                    <td>{c_fines:,.0f}</td>
                    <td>{c_overdue}</td>
                </tr>"""

        all_viol_rows = ""
        if include_violations and not company_name:
            for viol in db.get_json_records("violations"):
                dj = viol.get("data_json", {})
                all_viol_rows += f"""<tr>
                    <td>{dj.get("Фирма", "")}</td>
                    <td>{dj.get("Дата", "")}</td>
                    <td>{dj.get("Категория риска", "")}</td>
                    <td>{dj.get("Описание", "")[:50]}</td>
                    <td>{dj.get("Штраф", "0")}</td>
                    <td>{dj.get("Статус", "")}</td>
                </tr>"""

        table_html = ""
        if rows_html:
            table_html = """<table>
                <tr><th>Компания</th><th>Сотрудников</th><th>Нарушений</th>
                <th>Штрафы</th><th>Просрочено</th></tr>""" + rows_html + "</table>"
        if all_viol_rows:
            table_html += """<h2>Все нарушения</h2><table>
                <tr><th>Фирма</th><th>Дата</th><th>Категория</th>
                <th>Описание</th><th>Штраф</th><th>Статус</th></tr>""" + all_viol_rows + "</table>"

        now_str = datetime.now().strftime("%d.%m.%Y %H:%M")
        ctx = {
            "company_name": company_name or I18n._("filter.all"),
            "date": now_str,
            "emp_count": str(emp_count),
            "viol_count": str(viol_count),
            "fines_total": f"{fines:,.0f}",
            "overdue_count": str(overdue),
            "table_html": table_html,
            "app_name": I18n._("app.name"),
            "generated_at": now_str,
        }
        result = template_html
        for key, val in ctx.items():
            result = result.replace(f"{{{key}}}", str(val))
        return result

    @staticmethod
    def select_template(parent: QWidget, template_type: str = "order") -> Optional[str]:
        db = DatabaseManager()
        templates = db.get_print_templates(template_type)
        if not templates:
            return None
        names = [t["name"] for t in templates]
        name, ok = QInputDialog.getItem(parent, I18n._("template.title"),
                                        I18n._("template.choose"), names, 0, False)
        if ok and name:
            for t in templates:
                if t["name"] == name:
                    return t.get("html_content", "")
        return None

    @staticmethod
    def render_with_template(parent: QWidget, template_type: str,
                             records_data: List[Dict[str, Any]],
                             columns: List[Dict[str, Any]],
                             template_html: Optional[str] = None) -> str:
        html = template_html if template_html is not None else PrintEngine.select_template(parent, template_type)
        if html is None:
            parts = []
            for rec in records_data:
                dj = rec.get("data_json", {})
                lbl = I18n._("tab.employees") if template_type == "order" else I18n._("tab.violations")
                lines = [f"<h1>{lbl} #{rec.get('id', '')}</h1><table>"]
                for col in columns:
                    name = col["name"]
                    val = dj.get(name, "")
                    lines.append(f"<tr><td><b>{name}</b></td><td>{val}</td></tr>")
                lines.append("</table><hr>")
                parts.append("".join(lines))
            return "<html><body>" + "".join(parts) + "</body></html>"
        repeat_start = "ПОВТОРЯЕМЫЙ БЛОК: 1-е, 2-е, 3-е и следующие предписания"
        repeat_end = "КОНЕЦ ПОВТОРЯЕМОГО БЛОКА"
        if repeat_start in html and repeat_end in html:
            before, rest = html.split(repeat_start, 1)
            block, after = rest.split(repeat_end, 1)
            rendered_parts = []
            for index, rec in enumerate(records_data, start=1):
                dj = rec.get("data_json", {})
                rendered = block
                for key, val in dj.items():
                    rendered = rendered.replace(f"{{{key}}}", str(val))
                rendered = rendered.replace("{id}", str(rec.get("id", "")))
                rendered = rendered.replace("{record_number}", str(rec.get("id", "")))
                rendered = rendered.replace("{violation_number}", str(index))
                rendered = rendered.replace("{violation_index}", str(index))
                rendered = rendered.replace("{page_number}", str(index))
                rendered_parts.append(rendered)
            result = before + "".join(rendered_parts) + after
            return "<html><body>" + result + "</body></html>"

        parts = []
        for index, rec in enumerate(records_data, start=1):
            dj = rec.get("data_json", {})
            rendered = html
            for key, val in dj.items():
                rendered = rendered.replace(f"{{{key}}}", str(val))
            rendered = rendered.replace("{id}", str(rec.get("id", "")))
            rendered = rendered.replace("{record_number}", str(rec.get("id", "")))
            rendered = rendered.replace("{violation_number}", str(index))
            rendered = rendered.replace("{page_number}", str(index))
            parts.append(rendered)
        result = "<html><body>" + "".join(parts) + "</body></html>"
        if len(parts) > 1 and "page-break-before" not in result:
            result = "<html><body>" + parts[0] + "".join(
                "<div style='page-break-before:always; margin:0; padding:0; height:1px;'></div>" + p
                for p in parts[1:]) + "</body></html>"
        return result

    @staticmethod
    def print_document(html: str, parent: Optional[QWidget] = None) -> None:
        try:
            import re
            # Remove empty pages (page breaks followed by blank content)
            def _has_content(segment: str) -> bool:
                clean = segment
                for tag in ["<p></p>", "<p> </p>", "<p>&nbsp;</p>", "<br>", "<br/>",
                            "<div></div>", "<div> </div>", "<div>&nbsp;</div>",
                            "<hr>", "<hr/>"]:
                    clean = clean.replace(tag, "")
                clean = re.sub(r'<[^>]+>', '', clean).strip()
                return bool(clean)
            parts = re.split(
                r'<(div|p)\s+[^>]*?page-break-before:always[^>]*?>.*?</\1>',
                html)
            merged = parts[0]
            for i in range(1, len(parts)):
                if _has_content(parts[i]):
                    merged += parts[i]
            if merged != html:
                html = merged

            printer = QPrinter(QPrinter.HighResolution)
            dialog = QPrintDialog(printer, parent)
            dialog.setWindowTitle(I18n._("common.print"))
            if dialog.exec_() != QDialog.Accepted:
                return
            browser = QTextBrowser()
            browser.setHtml(html)
            browser.print_(printer)
            ToastNotification.notify(I18n._("print.generated"), "success", 3000)
        except Exception:
            ToastNotification.notify(I18n._("error.generic"), "error", 5000)


# ---------------------------------------------------------------------------
# SECTION 6.5: Print Template Editor (WYSIWYG)
# ---------------------------------------------------------------------------

class _ViewResizeFilter(QObject):
    def __init__(self, view: QGraphicsView, callback: Callable[[], None]) -> None:
        super().__init__(view)
        self._callback = callback

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Resize:
            try:
                if isinstance(obj.parent(), QGraphicsView):
                    self._callback()
            except RuntimeError:
                pass
        return super().eventFilter(obj, event)

class FieldHighlighter(QSyntaxHighlighter):
    def __init__(self, document: QTextDocument) -> None:
        super().__init__(document)
        from PyQt5.QtCore import QRegExp
        self._rule = QRegExp(r'\{[^{}]+\}')
        self._fmt = QTextCharFormat()
        self._fmt.setForeground(QColor("#4B7BFF"))
        self._fmt.setFontWeight(QFont.Bold)

    def highlightBlock(self, text: str) -> None:
        from PyQt5.QtCore import QRegExp
        idx = self._rule.indexIn(text)
        while idx >= 0:
            length = self._rule.matchedLength()
            self.setFormat(idx, length, self._fmt)
            idx = self._rule.indexIn(text, idx + length)

class RulerWidget(QWidget):
    def __init__(self, editor: QTextEdit) -> None:
        super().__init__(editor.parent())
        self._editor = editor
        self.setFixedHeight(22)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.hide()

    def update_position(self) -> None:
        eg = self._editor.geometry()
        self.setGeometry(eg.x(), eg.y() - self.height(), eg.width(), self.height())
        self.show(); self.update()

    def paintEvent(self, event: Any) -> None:
        if self.width() <= 0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#F0F2F5"))
        painter.setPen(QPen(QColor("#C0C4CC"), 1))
        painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
        step = max(30, self.width() // 20)
        painter.setPen(QPen(QColor("#8E8E93"), 1))
        font = QFont("Segoe UI", 6)
        painter.setFont(font)
        for x in range(step, self.width(), step):
            painter.drawLine(x, self.height() - 8, x, self.height() - 1)
            if x % (step * 2) == 0 and step >= 25:
                painter.drawText(x - 6, 8, f"{x}")
        painter.setPen(QPen(QColor("#4B7BFF"), 2))
        painter.drawLine(0, 0, 0, self.height())
        painter.drawLine(self.width() - 1, 0, self.width() - 1, self.height())

class PageGuideWidget(QWidget):
    def __init__(self, editor: QTextEdit, owner: 'PrintTemplateEditor') -> None:
        super().__init__(editor.parent())
        self._editor = editor
        self._owner = owner
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.hide()

    def paintEvent(self, event: Any) -> None:
        if not self._editor.isVisible() or self.width() <= 0 or self.height() <= 0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor("#D6DAE1"))
        pen.setWidth(1)
        painter.setPen(pen)
        fm = QFont("Segoe UI", 8)
        painter.setFont(fm)
        try:
            page_count = max(1, self._editor.document().pageCount())
        except Exception:
            page_count = 1
        pw, ph = self._owner._orientations.get(self._owner._orientation, (794, 1123))
        scale = max(0.05, self._owner._editor.width() / float(pw)) if pw else 1.0
        page_h = max(1, int(ph * scale))
        for page in range(1, page_count):
            y = page * page_h - self._owner._editor.verticalScrollBar().value()
            if y < -50 or y > self.height() + 50:
                continue
            # Shadow beneath page break
            for i in range(4):
                alpha = max(0, 20 - i * 5)
                painter.setPen(QPen(QColor(0, 0, 0, alpha)))
                painter.drawLine(20 + i, y + 1 + i, max(20, self.width() - 20 - i), y + 1 + i)
            painter.setPen(pen)
            painter.drawLine(18, y, max(18, self.width() - 18), y)
            painter.setPen(QColor("#8E8E93"))
            painter.drawText(24, y - 6, f"A4 • {page + 1}")
            painter.setPen(pen)

class PrintTemplateEditor(QDialog):
    ORDER_FIELDS = [
        ("id", "ID"),
        ("date", I18n._("common.date")),
        ("company", I18n._("emp.company")),
        ("responsible", I18n._("viol.responsible")),
        ("deadline", I18n._("viol.deadline")),
        ("description", I18n._("viol.description")),
        ("recommended_action", "Рекомендации"),
        ("fine", I18n._("viol.fine")),
        ("photos_section", I18n._("emp.photo")),
        ("app_name", I18n._("app.name")),
        ("generated_at", I18n._("common.date")),
        ("record_number", I18n._("template.record_number")),
        ("violation_number", I18n._("template.violation_number")),
        ("violation_index", I18n._("template.violation_index")),
        ("page_number", I18n._("template.insert_page_number")),
    ]
    REPORT_FIELDS = [
        ("company_name", I18n._("company.name")),
        ("date", I18n._("common.date")),
        ("emp_count", I18n._("company.employees_count")),
        ("viol_count", I18n._("company.violations_count")),
        ("fines_total", I18n._("company.fines_total")),
        ("overdue_count", I18n._("stat.overdue_total")),
        ("table_html", "HTML " + I18n._("common.table")),
        ("app_name", I18n._("app.name")),
        ("generated_at", I18n._("common.date")),
    ]

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.db = DatabaseManager()
        self.setWindowTitle(I18n._("template.edit"))
        screen = QApplication.primaryScreen().availableGeometry()
        sw, sh = screen.width(), screen.height()
        w = min(1650, sw - 40)
        h = min(900, sh - 80)
        self.setMinimumSize(1200, 600)
        self.resize(w, h)
        self.move(max(0, (sw - w) // 2), max(0, (sh - h) // 2))
        self._current_id: int = 0
        self._saved: bool = True
        self.selected_id: Optional[int] = None
        self._page_width: int = 794
        self._page_height: int = 1123
        self._page_margin_left: int = 60
        self._page_margin_right: int = 60
        self._page_margin_top: int = 50
        self._page_margin_bottom: int = 50
        self._zoom_level: int = 100
        self._show_page_shadow: bool = True
        self._orientations: Dict[str, Tuple[int, int]] = {
            "portrait": (794, 1123),
            "landscape": (1123, 794),
        }
        self._orientation: str = "portrait"
        settings = QSettings("SUOT", "PrintTemplate")
        self._page_margin_left = int(settings.value("page_margin_left", self._page_margin_left))
        self._page_margin_right = int(settings.value("page_margin_right", self._page_margin_right))
        self._page_margin_top = int(settings.value("page_margin_top", self._page_margin_top))
        self._page_margin_bottom = int(settings.value("page_margin_bottom", self._page_margin_bottom))
        self._show_page_shadow = str(settings.value("page_shadow", "true")).lower() in ("1", "true", "yes")
        self._orientation = settings.value("page_orientation", self._orientation)
        self._build_ui()
        self._load_templates()
        self._apply_page_margins()
        QTimer.singleShot(200, self._fit_page)
        self._auto_save_timer = QTimer(self)
        self._auto_save_timer.timeout.connect(self._auto_save)
        self._auto_save_timer.start(300000)

    def closeEvent(self, event: Any) -> None:
        if not self._saved:
            result = QMessageBox.question(self, I18n._("template.edit"),
                                          I18n._("common.confirm_close"),
                                          QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                                          QMessageBox.Cancel)
            if result == QMessageBox.Save:
                self._save_template()
                event.accept()
            elif result == QMessageBox.Discard:
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

    def _build_ui(self) -> None:
        is_dark_tmpl = ThemeEngine._current_theme == "dark"
        self.setStyleSheet(
            f"PrintTemplateEditor {{ background: {'#1C1C1E' if is_dark_tmpl else '#F5F5F7'}; }}")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(3)

        _rh = 26
        def _sep() -> QFrame:
            s = QFrame(); s.setFrameShape(QFrame.VLine); s.setStyleSheet("color:#D0D4DC;"); return s
        def _tb(emoji, tip, cb, w=30) -> QToolButton:
            b = QToolButton(); b.setText(emoji); b.setToolTip(tip)
            b.setFixedSize(w, _rh); b.clicked.connect(cb); return b
        def _make_btn(text: str, cb, w=70) -> QPushButton:
            b = QPushButton(text); b.setFixedHeight(_rh); b.setMinimumWidth(w)
            b.clicked.connect(cb); return b

        # ═══ Ряд 1: Тип + Шаблон + Имя + Файл ══════════════════════════
        row1 = QHBoxLayout(); row1.setSpacing(3)
        row1.addWidget(QLabel(I18n._("print.template") + ":"))
        self._type_combo = QComboBox()
        self._type_combo.addItem(I18n._("print.order"), "order")
        self._type_combo.addItem(I18n._("print.report"), "report")
        self._type_combo.currentIndexChanged.connect(self._on_type_changed)
        self._type_combo.setMinimumWidth(90); self._type_combo.setFixedHeight(_rh)
        row1.addWidget(self._type_combo)
        self._template_combo = QComboBox()
        self._template_combo.setMinimumWidth(160); self._template_combo.setFixedHeight(_rh)
        self._template_combo.currentIndexChanged.connect(self._on_template_changed)
        row1.addWidget(self._template_combo)
        self._template_name_edit = QLineEdit()
        self._template_name_edit.setPlaceholderText(I18n._("template.name"))
        self._template_name_edit.setMinimumWidth(140); self._template_name_edit.setFixedHeight(_rh)
        row1.addWidget(self._template_name_edit)
        self._template_search = QLineEdit()
        self._template_search.setPlaceholderText("🔍" + I18n._("common.find"))
        self._template_search.setFixedHeight(_rh); self._template_search.setMaximumWidth(100)
        self._template_search.textChanged.connect(self._filter_templates)
        row1.addWidget(self._template_search)
        row1.addWidget(_sep())
        row1.addWidget(_tb("➕", I18n._("common.add"), self._new_template))
        row1.addWidget(_tb("💾", I18n._("common.save"), self._save_template))
        row1.addWidget(_tb("📋", I18n._("template.duplicate"), self._duplicate_template))
        row1.addWidget(_tb("✏️", I18n._("common.rename"), self._rename_template))
        row1.addWidget(_tb("🗑️", I18n._("common.delete"), self._delete_template))
        row1.addWidget(_tb("✅", I18n._("template.select"), self._select_and_close))
        row1.addWidget(_tb("📂", "Импорт", self._import_template))
        row1.addWidget(_tb("📤", "Экспорт", self._export_template))
        row1.addStretch()
        layout.addLayout(row1)

        # ═══ Ряд 2: Страница + Масштаб ══════════════════════════════════
        row2 = QHBoxLayout(); row2.setSpacing(3)
        row2.addWidget(QLabel("📄" + I18n._("template.page_settings") + ":"))
        row2.addWidget(_sep())
        # margin spins with compact labels
        for attr, label, rmin, rmax in [
            ("_margin_left_spin", "←", 10, 160),
            ("_margin_right_spin", "→", 10, 160),
            ("_margin_top_spin", "↑", 10, 180),
            ("_margin_bottom_spin", "↓", 10, 180),
        ]:
            row2.addWidget(QLabel(label))
            spin = QSpinBox()
            spin.setRange(rmin, rmax)
            spin.setFixedWidth(54); spin.setFixedHeight(_rh)
            spin.setSuffix("")
            setattr(self, attr, spin)
            row2.addWidget(spin)
        self._margin_left_spin.setValue(self._page_margin_left)
        self._margin_right_spin.setValue(self._page_margin_right)
        self._margin_top_spin.setValue(self._page_margin_top)
        self._margin_bottom_spin.setValue(self._page_margin_bottom)
        row2.addWidget(_sep())
        row2.addWidget(QLabel(I18n._("template.margin_preset") + ":"))
        self._margin_preset_combo = QComboBox()
        self._margin_preset_combo.addItem(I18n._("template.margin_normal"), "normal")
        self._margin_preset_combo.addItem(I18n._("template.margin_narrow"), "narrow")
        self._margin_preset_combo.addItem(I18n._("template.margin_wide"), "wide")
        self._margin_preset_combo.setMinimumWidth(70); self._margin_preset_combo.setFixedHeight(_rh)
        row2.addWidget(self._margin_preset_combo)
        self._page_shadow_cb = QCheckBox(I18n._("template.page_shadow"))
        self._page_shadow_cb.setChecked(self._show_page_shadow)
        self._page_shadow_cb.setFixedHeight(_rh)
        row2.addWidget(self._page_shadow_cb)
        row2.addWidget(_sep())
        row2.addWidget(QLabel(I18n._("print.orientation") + ":"))
        self._orientation_combo = QComboBox()
        self._orientation_combo.addItem(I18n._("print.portrait"), "portrait")
        self._orientation_combo.addItem(I18n._("print.landscape"), "landscape")
        self._orientation_combo.setMinimumWidth(70); self._orientation_combo.setFixedHeight(_rh)
        self._orientation_combo.currentIndexChanged.connect(self._on_orientation_changed)
        row2.addWidget(self._orientation_combo)
        saved_orientation_idx = self._orientation_combo.findData(self._orientation)
        if saved_orientation_idx >= 0:
            self._orientation_combo.setCurrentIndex(saved_orientation_idx)
        row2.addWidget(_sep())
        self._zoom_slider = QSlider(Qt.Horizontal)
        self._zoom_slider.setRange(10, 400); self._zoom_slider.setValue(self._zoom_level)
        self._zoom_slider.setFixedWidth(100); self._zoom_slider.setFixedHeight(18)
        self._zoom_slider.setToolTip(I18n._("common.zoom"))
        self._zoom_slider.valueChanged.connect(self._apply_zoom_slider)
        row2.addWidget(self._zoom_slider)
        self._zoom_label = QPushButton()
        self._zoom_label.setFixedSize(46, _rh)
        self._zoom_label.setStyleSheet("font-weight:bold; font-size:10px; padding:0;")
        self._zoom_label.setToolTip(I18n._("common.reset_zoom"))
        self._zoom_label.clicked.connect(self._reset_zoom)
        row2.addWidget(self._zoom_label)
        row2.addStretch()
        layout.addLayout(row2)

        # ═══ Ряд 3: Формат ══════════════════════════════════════════════
        row3 = QHBoxLayout(); row3.setSpacing(3)
        row3.addWidget(QLabel("🎨" + I18n._("common.format") + ":"))
        row3.addWidget(_sep())
        self._heading_combo = QComboBox()
        self._heading_combo.addItem(I18n._("common.paragraph"), "p")
        self._heading_combo.addItem(I18n._("template.heading1"), "h1")
        self._heading_combo.addItem(I18n._("template.heading2"), "h2")
        self._heading_combo.addItem(I18n._("template.heading3"), "h3")
        self._heading_combo.setMinimumWidth(95); self._heading_combo.setFixedHeight(_rh)
        self._heading_combo.currentIndexChanged.connect(self._on_heading_changed)
        row3.addWidget(self._heading_combo)
        row3.addWidget(QLabel(I18n._("common.size") + ":"))
        self._size_combo = QComboBox()
        self._size_combo.setEditable(True)
        self._size_combo.setMinimumWidth(48); self._size_combo.setFixedHeight(_rh)
        for s in ("8","9","10","11","12","14","16","18","20","22","24","28","32","36","40","48","56","64","72"):
            self._size_combo.addItem(s)
        self._size_combo.setCurrentText("12")
        self._size_combo.currentTextChanged.connect(self._on_size_changed)
        row3.addWidget(self._size_combo)
        row3.addWidget(_tb("🧹", I18n._("common.clear"), self._clear_formatting))
        row3.addWidget(_sep())
        for txt, tip, attr, cb in [
            ("B", "Жирный (Ctrl+B)", "_bold_btn", self._toggle_bold),
            ("I", "Курсив (Ctrl+I)", "_italic_btn", self._toggle_italic),
            ("U", "Подчёркнутый (Ctrl+U)", "_underline_btn", self._toggle_underline),
            ("S", "Зачёркнутый", "_strike_btn", self._toggle_strikethrough),
        ]:
            b = QToolButton(); b.setText(txt); b.setCheckable(True);
            b.setFixedSize(28, _rh); b.setToolTip(tip); b.clicked.connect(cb)
            if txt == "B": b.setFont(QFont("Segoe UI", 9, QFont.Bold))
            elif txt == "I": b.setFont(QFont("", -1, -1, True))
            elif txt == "U": f = QFont("", -1, -1); f.setUnderline(True); b.setFont(f)
            elif txt == "S": f = QFont("", -1, -1); f.setStrikeOut(True); b.setFont(f)
            setattr(self, attr, b); row3.addWidget(b)
        row3.addWidget(_sep())
        self._font_combo = QFontComboBox()
        self._font_combo.setMinimumWidth(110); self._font_combo.setFixedHeight(_rh)
        self._font_combo.setFontFilters(QFontComboBox.AllFonts)
        self._font_combo.currentFontChanged.connect(self._on_font_changed)
        row3.addWidget(self._font_combo)
        self._color_btn = QToolButton()
        self._color_btn.setText("A"); self._color_btn.setFixedSize(28, _rh)
        self._color_btn.setStyleSheet("color:#1a365d; font-weight:bold;")
        self._color_btn.setToolTip(I18n._("common.format"))
        self._color_btn.clicked.connect(self._pick_color)
        row3.addWidget(self._color_btn)
        row3.addWidget(_sep())
        for txt, tip, attr, align in [
            ("≡L", I18n._("common.align_left"), "_align_left_btn", Qt.AlignLeft),
            ("≡C", I18n._("common.align_center"), "_align_center_btn", Qt.AlignCenter),
            ("≡R", I18n._("common.align_right"), "_align_right_btn", Qt.AlignRight),
        ]:
            b = QToolButton(); b.setText(txt); b.setCheckable(True)
            b.setFixedSize(28, _rh); b.setToolTip(tip)
            b.clicked.connect(lambda a=align: self._set_alignment(a))
            setattr(self, attr, b); row3.addWidget(b)
        row3.addWidget(_sep())
        self._bullet_btn = QToolButton()
        self._bullet_btn.setText("•"); self._bullet_btn.setCheckable(True)
        self._bullet_btn.setFixedSize(28, _rh); self._bullet_btn.setToolTip("Список")
        self._bullet_btn.clicked.connect(self._toggle_bullet)
        row3.addWidget(self._bullet_btn)
        self._number_btn = QToolButton()
        self._number_btn.setText("1."); self._number_btn.setCheckable(True)
        self._number_btn.setFixedSize(28, _rh); self._number_btn.setToolTip("Нумерация")
        self._number_btn.clicked.connect(self._toggle_number)
        row3.addWidget(self._number_btn)
        row3.addWidget(_sep())
        row3.addWidget(_tb("↔→", "Увеличить отступ", self._indent))
        row3.addWidget(_tb("←↔", "Уменьшить отступ", self._unindent))
        row3.addWidget(_sep())
        row3.addWidget(_tb("↩", I18n._("common.undo") + " (Ctrl+Z)", lambda: self._editor.undo() if hasattr(self, '_editor') else None, 28))
        row3.addWidget(_tb("↪", I18n._("common.redo") + " (Ctrl+Y)", lambda: self._editor.redo() if hasattr(self, '_editor') else None, 28))
        row3.addWidget(_sep())
        row3.addWidget(_tb("Aa↓", "нижний регистр", self._case_lower))
        row3.addWidget(_tb("Aa↑", "ВЕРХНИЙ РЕГИСТР", self._case_upper))
        row3.addWidget(_tb("Aa⇔", "Заглавные", self._case_title))
        row3.addWidget(_tb("Ω", "Спецсимволы", self._special_chars))
        row3.addWidget(_sep())
        self._quick_style_combo = QComboBox()
        self._quick_style_combo.setFixedHeight(_rh); self._quick_style_combo.setMinimumWidth(110)
        self._quick_style_combo.addItem("🎨 Стиль...", "")
        self._quick_style_combo.addItem("📋 Цитата", "quote")
        self._quick_style_combo.addItem("⚠️ Предупреждение", "alert")
        self._quick_style_combo.addItem("💻 Код", "code")
        self._quick_style_combo.activated.connect(self._apply_quick_style)
        row3.addWidget(self._quick_style_combo)
        row3.addWidget(_sep())
        row3.addWidget(QLabel("Инт:"))
        self._line_spacing_spin = QDoubleSpinBox()
        self._line_spacing_spin.setRange(0.5, 3.0); self._line_spacing_spin.setSingleStep(0.1)
        self._line_spacing_spin.setValue(1.0); self._line_spacing_spin.setFixedWidth(50)
        self._line_spacing_spin.setFixedHeight(_rh)
        self._line_spacing_spin.valueChanged.connect(self._apply_line_spacing)
        row3.addWidget(self._line_spacing_spin)
        row3.addWidget(_sep())
        row3.addWidget(_tb("◁", "По левому краю", self._align_left, 26))
        row3.addWidget(_tb("≡", "По центру", self._align_center, 26))
        row3.addWidget(_tb("▷", "По правому краю", self._align_right, 26))
        row3.addWidget(_tb("⊞", "По ширине", self._align_justify, 26))
        row3.addWidget(_sep())
        row3.addWidget(_tb("📊", I18n._("stat.document_stats"), self._document_stats, 30))
        row3.addWidget(_sep())
        row3.addWidget(_tb("📋", "Вставить без форматирования", self._paste_plain, 30))
        row3.addStretch()
        layout.addLayout(row3)

        # ═══ Ряд 4: Вставка + Поля ══════════════════════════════════════
        row4 = QHBoxLayout(); row4.setSpacing(3)
        row4.addWidget(QLabel("📦" + I18n._("template.insert_table") + ":"))
        row4.addWidget(_sep())
        row4.addWidget(_tb("📊", I18n._("template.insert_table"), self._insert_table, 32))
        row4.addWidget(_tb("📝", I18n._("template.insert_header"), self._insert_header_block, 32))
        row4.addWidget(_tb("✍️", I18n._("template.insert_signature"), self._insert_signature_block, 32))
        row4.addWidget(_tb("🔧", I18n._("template.auto_format"), self._auto_format_document, 32))
        row4.addWidget(_tb("↔", I18n._("template.fit_width"), self._fit_width, 32))
        row4.addWidget(_tb("🖼", "Вставить картинку", self._insert_image, 32))
        row4.addWidget(_sep())
        self._field_search = QLineEdit()
        self._field_search.setPlaceholderText("🔍" + I18n._("common.search") + "...")
        self._field_search.setMinimumHeight(_rh); self._field_search.setMaximumWidth(100)
        self._field_search.textChanged.connect(self._filter_field_tree)
        row4.addWidget(self._field_search)
        self._field_combo = QComboBox()
        self._field_combo.setEditable(True)
        self._field_combo.setInsertPolicy(QComboBox.NoInsert)
        self._field_combo.setMinimumWidth(160); self._field_combo.setFixedHeight(_rh)
        self._field_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._field_combo.activated[int].connect(self._on_field_combo_selected)
        self._field_combo.lineEdit().setPlaceholderText("🔍 Поле...")
        row4.addWidget(self._field_combo)
        row4.addWidget(_sep())
        row4.addWidget(_tb("▶", I18n._("template.repeat_start"), self._insert_repeat_block_start))
        row4.addWidget(_tb("■", I18n._("template.repeat_end"), self._insert_repeat_block_end))
        row4.addWidget(_sep())
        self._quick_blocks_combo = QComboBox()
        self._quick_blocks_combo.setFixedHeight(_rh); self._quick_blocks_combo.setMinimumWidth(110)
        self._quick_blocks_combo.addItem(I18n._("template.block_title"), "title")
        self._quick_blocks_combo.addItem(I18n._("template.block_violations"), "violations")
        self._quick_blocks_combo.addItem(I18n._("template.insert_header"), "header")
        self._quick_blocks_combo.addItem(I18n._("template.insert_signature"), "signature")
        row4.addWidget(self._quick_blocks_combo)
        row4.addWidget(_tb("➕", I18n._("common.add"), self._insert_quick_block))
        row4.addWidget(_sep())
        row4.addWidget(_tb("👁", I18n._("template.preview_multi"), lambda: self._preview_template(multi_sample=True)))
        row4.addWidget(_tb("🎨", "Фон страницы", self._page_bg_color))
        row4.addWidget(_sep())
        row4.addWidget(QLabel("№:"))
        self._page_num_fmt = QComboBox()
        self._page_num_fmt.setFixedHeight(_rh); self._page_num_fmt.setMinimumWidth(80)
        self._page_num_fmt.addItem("{n}", "n")
        self._page_num_fmt.addItem("{n}/{total}", "n_total")
        self._page_num_fmt.addItem("Стр.{n}", "page_n")
        self._page_num_fmt.currentIndexChanged.connect(lambda: None)
        row4.addWidget(self._page_num_fmt)
        row4.addStretch()
        layout.addLayout(row4)

        # ── Скрытое дерево полей ─────────────────────────────────────
        self._field_tree = QTreeWidget()
        self._field_tree.setHeaderHidden(True)
        self._field_tree.setRootIsDecorated(True)
        self._field_tree.setIndentation(16)
        self._field_tree.itemDoubleClicked.connect(lambda item, _: self._insert_field(item))
        self._field_tree.setVisible(False)

        # ═══ Ряд 5: Редактор ════════════════════════════════════════════
        self._editor_scroll = QScrollArea()
        self._editor_scroll.setWidgetResizable(True)
        self._editor_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self._editor_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._editor_scroll.setStyleSheet(
            "QScrollArea { border: none; background: #E8ECF1; }"
            "QScrollBar:vertical { width: 14px; background: #E8ECF1; margin: 0; }"
            "QScrollBar::handle:vertical { background: #B0B0B0; min-height: 24px; border-radius: 5px; margin: 2px; }"
            "QScrollBar::handle:vertical:hover { background: #909090; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }")

        self._editor_container = QWidget()
        self._editor_container.setStyleSheet("background: #E8ECF1;")
        self._editor_container_layout = QVBoxLayout(self._editor_container)
        self._editor_container_layout.setContentsMargins(14, 14, 14, 14)
        self._editor_container_layout.setAlignment(Qt.AlignCenter)

        self._editor = QTextEdit()
        self._editor.setAcceptRichText(True)
        self._editor.setContextMenuPolicy(Qt.CustomContextMenu)
        self._editor.customContextMenuRequested.connect(self._editor_context_menu)
        self._editor.setMinimumWidth(400)
        self._editor.setMinimumHeight(250)
        self._editor.document().setDocumentMargin(0)
        self._editor.document().setDefaultFont(QFont("Segoe UI", 11))
        self._editor.setStyleSheet(
            "QTextEdit { background: #FFFFFF; color: #2C3E50; border: 1px solid #C0C4CC; "
            "border-radius: 2px; padding: 40px 50px; font-size: 11pt; }")
        self._editor.cursorPositionChanged.connect(self._update_format_buttons)
        self._editor.selectionChanged.connect(self._update_format_buttons)
        self._editor.textChanged.connect(self._update_status)
        self._editor.textChanged.connect(self._sync_editor_height)
        self._editor.textChanged.connect(lambda: setattr(self, '_saved', False))
        self._editor.verticalScrollBar().valueChanged.connect(lambda _: self._update_page_guide())
        self._editor.textChanged.connect(self._update_word_count)
        self._field_hl = FieldHighlighter(self._editor.document())
        QShortcut(QKeySequence.Save, self, self._save_template)
        QShortcut(QKeySequence(Qt.CTRL + Qt.Key_B), self, self._toggle_bold)
        QShortcut(QKeySequence(Qt.CTRL + Qt.Key_I), self, self._toggle_italic)
        QShortcut(QKeySequence(Qt.CTRL + Qt.Key_U), self, self._toggle_underline)
        QShortcut(QKeySequence(Qt.CTRL + Qt.Key_F), self, self._find_text)
        QShortcut(QKeySequence(Qt.CTRL + Qt.Key_H), self, self._find_replace)
        QShortcut(QKeySequence(Qt.CTRL + Qt.Key_Plus), self, self._increase_font_size)
        QShortcut(QKeySequence(Qt.CTRL + Qt.Key_Minus), self, self._decrease_font_size)
        settings = QSettings("SUOT", "PrintTemplate")
        saved_font = settings.value("font_family", "Segoe UI")
        saved_size = int(settings.value("font_size", 11))
        if saved_font:
            self._editor.setCurrentFont(QFont(saved_font, saved_size))
            self._font_combo.setCurrentFont(QFont(saved_font, saved_size))
        self._size_combo.setCurrentText(str(saved_size))
        for spin in (self._margin_left_spin, self._margin_right_spin, self._margin_top_spin, self._margin_bottom_spin):
            spin.valueChanged.connect(self._apply_page_margins)
        self._margin_preset_combo.currentIndexChanged.connect(self._apply_margin_preset)
        self._page_shadow_cb.toggled.connect(self._apply_page_margins)
        self._template_name_edit.textChanged.connect(self._update_status)
        self._editor_container_layout.addWidget(self._editor)
        self._ruler = RulerWidget(self._editor)
        self._page_guide = PageGuideWidget(self._editor, self)
        self._page_guide.raise_()
        self._editor_scroll.setWidget(self._editor_container)
        layout.addWidget(self._editor_scroll, 1)

        # ═══ Нижняя панель ══════════════════════════════════════════════
        bottom = QHBoxLayout(); bottom.setSpacing(3)
        _bot_h = 26
        self._reset_btn = QPushButton("🔄" + I18n._("template.reset"))
        self._reset_btn.setFixedHeight(_bot_h); self._reset_btn.setFixedWidth(60)
        self._reset_btn.clicked.connect(self._reset_template)
        bottom.addWidget(self._reset_btn)
        self._page_nav_label = QLabel("📄")
        self._page_nav_label.setStyleSheet("font-size:11px;")
        bottom.addWidget(self._page_nav_label)
        self._page_nav_spin = QSpinBox()
        self._page_nav_spin.setPrefix("")
        self._page_nav_spin.setMinimum(1); self._page_nav_spin.setMaximum(9999)
        self._page_nav_spin.setFixedWidth(80); self._page_nav_spin.setFixedHeight(_bot_h)
        self._page_nav_spin.valueChanged.connect(self._go_to_page)
        bottom.addWidget(self._page_nav_spin)
        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color:#8E8E93; font-size:10px; padding:0 4px;")
        bottom.addWidget(self._status_label)
        self._word_count_label = QLabel("")
        self._word_count_label.setStyleSheet("color:#8E8E93; font-size:10px; padding:0 4px;")
        bottom.addWidget(self._word_count_label, 1)
        for emoji, tip, cb in [
            ("📏", "Линейка", self._toggle_ruler),
            ("📐", "Ед. изм.", self._toggle_ruler_units),
            ("📝", "Заметки", self._template_notes),
            ("📑", "Структура", self._document_outline),
            ("📕", "PDF", self._export_pdf),
            ("</>", "HTML код", self._show_html_source),
            ("⭐", "Избранное", self._toggle_favorite),
            ("⬅", "Первая стр.", self._go_first_page),
            ("➡", "Посл. стр.", self._go_last_page),
            ("🔍", I18n._("common.find"), self._find_text),
            ("🔎", "Найти/Заменить", self._find_replace),
            ("📅", I18n._("template.insert_date"), self._insert_date),
            ("#", I18n._("template.insert_page_number"), self._insert_page_number),
            ("🖨", I18n._("common.print"), self._quick_print),
            ("👁", I18n._("template.preview"), self._preview_template),
            ("⛶", I18n._("common.fullscreen"), self._toggle_fullscreen),
            ("❌", I18n._("common.close"), self.accept),
        ]:
            bottom.addWidget(_tb(emoji, tip, cb, 30))
        layout.addLayout(bottom)

    def _build_field_tree(self) -> None:
        self._field_tree.clear()
        self._field_combo.blockSignals(True)
        self._field_combo.clear()
        self._field_combo.addItem("— " + I18n._("common.select") + " —", "")
        template_type = self._type_combo.currentData()
        fields_group = QTreeWidgetItem([I18n._("template.variables_group")])
        f = fields_group.font(0); f.setBold(True); fields_group.setFont(0, f)
        self._field_tree.addTopLevelItem(fields_group)
        available = self.ORDER_FIELDS if template_type == "order" else self.REPORT_FIELDS
        for key, label in available:
            item = QTreeWidgetItem([f"{{{key}}} — {label}"])
            item.setData(0, Qt.UserRole, key)
            fields_group.addChild(item)
            self._field_combo.addItem(f"{{{key}}} — {label}", key)
        fields_group.setExpanded(True)
        for table_key, table_label in [("employees", I18n._("tab.employees")),
                                       ("violations", I18n._("tab.violations")),
                                       ("custom_ledger", I18n._("tab.custom_ledger"))]:
            cols = self.db.get_columns_config(table_key)
            if not cols:
                continue
            ti = QTreeWidgetItem([table_label])
            ff = ti.font(0); ff.setBold(True); ti.setFont(0, ff)
            for c in cols:
                item = QTreeWidgetItem([f"{{{{{table_key}.{c['name']}}}}} — {c['name']}"])
                item.setData(0, Qt.UserRole, f"{table_key}.{c['name']}")
                ti.addChild(item)
                self._field_combo.addItem(f"{{{{{table_key}.{c['name']}}}}} — {c['name']}", f"{table_key}.{c['name']}")
            self._field_tree.addTopLevelItem(ti)
        self._field_combo.blockSignals(False)

    def _on_field_combo_selected(self, idx: int) -> None:
        key = self._field_combo.currentData()
        if key:
            self._editor.insertPlainText("{" + key + "}")
        self._field_combo.setCurrentIndex(0)

    def _insert_field(self, item: QTreeWidgetItem) -> None:
        key = item.data(0, Qt.UserRole)
        if key:
            self._editor.insertPlainText(f"{{{key}}}")

    def _toggle_bold(self) -> None:
        self._editor.setFontWeight(QFont.Bold if self._bold_btn.isChecked() else QFont.Normal)

    def _toggle_italic(self) -> None:
        self._editor.setFontItalic(self._italic_btn.isChecked())

    def _toggle_underline(self) -> None:
        self._editor.setFontUnderline(self._underline_btn.isChecked())

    def _toggle_strikethrough(self) -> None:
        fmt = self._editor.currentCharFormat()
        fmt.setFontStrikeOut(self._strike_btn.isChecked())
        self._editor.mergeCurrentCharFormat(fmt)

    def _on_heading_changed(self, idx: int) -> None:
        tag = self._heading_combo.itemData(idx)
        cursor = self._editor.textCursor()
        fmt = cursor.blockFormat()
        if tag == "p":
            fmt.setProperty(QTextFormat.BlockTrailingHorizontalRulerWidth, -1)
            cursor.setBlockFormat(fmt)
            cfmt = self._editor.currentCharFormat()
            cfmt.setFontPointSize(11)
            self._editor.setCurrentCharFormat(cfmt)
        elif tag == "h1":
            fmt.setProperty(QTextFormat.BlockTrailingHorizontalRulerWidth, -1)
            cursor.setBlockFormat(fmt)
            cfmt = self._editor.currentCharFormat()
            cfmt.setFontPointSize(22); cfmt.setFontWeight(QFont.Bold)
            self._editor.setCurrentCharFormat(cfmt)
        elif tag == "h2":
            cfmt = self._editor.currentCharFormat()
            cfmt.setFontPointSize(18); cfmt.setFontWeight(QFont.Bold)
            self._editor.setCurrentCharFormat(cfmt)
        elif tag == "h3":
            cfmt = self._editor.currentCharFormat()
            cfmt.setFontPointSize(14); cfmt.setFontWeight(QFont.Bold)
            self._editor.setCurrentCharFormat(cfmt)

    def _on_font_changed(self, font: QFont) -> None:
        self._editor.setCurrentFont(font)
        settings = QSettings("SUOT", "PrintTemplate")
        settings.setValue("font_family", font.family())

    def _on_size_changed(self, text: str) -> None:
        try:
            sz = float(text)
            self._editor.setFontPointSize(sz)
            settings = QSettings("SUOT", "PrintTemplate")
            settings.setValue("font_size", int(sz))
        except ValueError:
            pass

    def _pick_color(self) -> None:
        c = QColorDialog.getColor(self._editor.textColor(), self, I18n._("common.format"))
        if c.isValid():
            self._editor.setTextColor(c)
            self._color_btn.setStyleSheet(f"color: {c.name()}; font-weight: bold;")

    def _set_alignment(self, align: int) -> None:
        self._editor.setAlignment(align)
        self._align_left_btn.setChecked(align == Qt.AlignLeft)
        self._align_center_btn.setChecked(align == Qt.AlignCenter)
        self._align_right_btn.setChecked(align == Qt.AlignRight)

    def _apply_page_margins(self) -> None:
        self._page_margin_left = self._margin_left_spin.value()
        self._page_margin_right = self._margin_right_spin.value()
        self._page_margin_top = self._margin_top_spin.value()
        self._page_margin_bottom = self._margin_bottom_spin.value()
        self._show_page_shadow = self._page_shadow_cb.isChecked()
        settings = QSettings("SUOT", "PrintTemplate")
        settings.setValue("page_margin_left", self._page_margin_left)
        settings.setValue("page_margin_right", self._page_margin_right)
        settings.setValue("page_margin_top", self._page_margin_top)
        settings.setValue("page_margin_bottom", self._page_margin_bottom)
        settings.setValue("page_shadow", self._show_page_shadow)
        settings.setValue("page_orientation", self._orientation)
        shadow = "" if not self._show_page_shadow else "selection-background-color:#DCEBFF;"
        page_border = "border: 1px solid #C0C4CC;"
        if self._show_page_shadow:
            page_border = "border: 1px solid #C7CDD8;"
        self._editor.setStyleSheet(
            "QTextEdit { background: #FFFFFF; color: #2C3E50; "
            f"{page_border} border-radius: 2px; padding: {self._page_margin_top}px {self._page_margin_right}px {self._page_margin_bottom}px {self._page_margin_left}px; "
            f"font-size: 11pt; {shadow}}}")
        container_style = "background: #E8ECF1;"
        if self._show_page_shadow:
            container_style = (
                "background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #EEF2F7, stop:1 #E3E7ED);"
            )
        self._editor_container.setStyleSheet(container_style)
        self._sync_editor_height()

    def _apply_margin_preset(self) -> None:
        preset = self._margin_preset_combo.currentData()
        if preset == "narrow":
            vals = (30, 30, 30, 30)
        elif preset == "wide":
            vals = (90, 90, 70, 70)
        else:
            vals = (60, 60, 50, 50)
        spins = (self._margin_left_spin, self._margin_right_spin, self._margin_top_spin, self._margin_bottom_spin)
        for spin, val in zip(spins, vals):
            spin.blockSignals(True)
            spin.setValue(val)
            spin.blockSignals(False)
        self._apply_page_margins()

    def _insert_quick_block(self) -> None:
        block = self._quick_blocks_combo.currentData()
        if block == "title":
            self._editor.insertHtml("<h1 style='text-align:center;'>Документ</h1><p style='text-align:center;'>{company}</p><p><br></p>")
        elif block == "violations":
            self._insert_repeat_block_start()
            self._insert_repeat_block_end()
        elif block == "header":
            self._insert_header_block()
        elif block == "signature":
            self._insert_signature_block()
        self._sync_editor_height()

    def _insert_repeat_block_start(self) -> None:
        self._editor.insertHtml(
            "<div data-repeat='violations' style='border:1px dashed #7C8AA5; background:#F7F9FC; padding:12px; margin:12px 0; border-radius:8px;'>"
            "<div style='font-size:10pt; color:#4B5563; margin-bottom:8px; font-weight:bold;'>"
            "ПОВТОРЯЕМЫЙ БЛОК: 1-е, 2-е, 3-е и следующие предписания</div>"
            "<div style='font-size:9.5pt; color:#6B7280; margin-bottom:10px;'>"
            "Используйте {violation_index} или {violation_number}, чтобы показывать номер предписания внутри списка.</div>"
        )
        self._editor.insertPlainText("Предписание {violation_index}\nОписание: {description}\nСрок: {deadline}\nМеры: {recommended_action}\nШтраф: {fine}")
        self._sync_editor_height()

    def _insert_repeat_block_end(self) -> None:
        self._editor.insertHtml(
            "<div style='font-size:10pt; color:#4B5563; margin-top:10px; font-weight:bold;'>КОНЕЦ ПОВТОРЯЕМОГО БЛОКА</div></div><p><br></p>"
        )
        self._sync_editor_height()

    def _insert_page_number(self) -> None:
        self._editor.insertPlainText("{page_number}")

    def _duplicate_template(self) -> None:
        html = self._editor.toHtml().strip()
        if not html:
            ToastNotification.notify(I18n._("error.invalid_data"), "error", 3000)
            return
        base_name = self._template_name_edit.text().strip() or self._template_combo.currentText().rsplit(" ", 1)[0].strip()
        new_name, ok = QInputDialog.getText(self, I18n._("template.duplicate"), I18n._("template.name"), text=base_name + " (копия)")
        if not ok or not new_name.strip():
            return
        template_type = self._type_combo.currentData()
        new_id = self.db.save_print_template(new_name.strip(), template_type, html)
        self._current_id = new_id
        self._load_templates()
        for i in range(self._template_combo.count()):
            if self._template_combo.itemData(i) == new_id:
                self._template_combo.setCurrentIndex(i)
                break
        self._template_name_edit.setText(new_name.strip())

    def _update_format_buttons(self) -> None:
        fmt = self._editor.currentCharFormat()
        self._bold_btn.setChecked(self._editor.fontWeight() >= QFont.Bold)
        self._italic_btn.setChecked(fmt.fontItalic())
        self._underline_btn.setChecked(fmt.fontUnderline())
        self._strike_btn.setChecked(fmt.fontStrikeOut())
        a = self._editor.alignment()
        self._align_left_btn.setChecked(a == Qt.AlignLeft)
        self._align_center_btn.setChecked(a == Qt.AlignCenter)
        self._align_right_btn.setChecked(a == Qt.AlignRight)
        cursor = self._editor.textCursor()
        self._bullet_btn.setChecked(bool(cursor.currentList()) and cursor.currentList().format().style() == QTextListFormat.ListDisc)
        self._number_btn.setChecked(bool(cursor.currentList()) and cursor.currentList().format().style() == QTextListFormat.ListDecimal)
        self._heading_combo.blockSignals(True)
        html = self._editor.toHtml()
        if "<h1>" in html: self._heading_combo.setCurrentIndex(1)
        elif "<h2>" in html: self._heading_combo.setCurrentIndex(2)
        elif "<h3>" in html: self._heading_combo.setCurrentIndex(3)
        else: self._heading_combo.setCurrentIndex(0)
        self._heading_combo.blockSignals(False)

    def _on_type_changed(self) -> None:
        self._load_templates()
        self._build_field_tree()

    def _on_template_changed(self, idx: int) -> None:
        self._load_template_content(idx)

    def _load_templates(self) -> None:
        self._template_combo.blockSignals(True)
        self._template_combo.clear()
        template_type = self._type_combo.currentData()
        suffix = " 📄" if template_type == "order" else " 📊"
        for t in self.db.get_print_templates(template_type):
            self._template_combo.addItem(t["name"] + suffix, t["id"])
        self._template_combo.blockSignals(False)
        if self._template_combo.count():
            self._template_combo.setCurrentIndex(0)
            self._load_template_content(0)
        else:
            self._editor.clear()
            self._current_id = 0
        self._build_field_tree()
        self._update_status()

    def _update_status(self) -> None:
        plain = self._editor.toPlainText()
        chars = len(plain)
        words = len(plain.split()) if plain.strip() else 0
        try:
            pages = self._editor.document().pageCount()
        except Exception:
            pages = 1
        name = self._template_name_edit.text().strip() or self._template_combo.currentText() or I18n._("template.untitled")
        repeat_used = " | 🔁" if "ПОВТОРЯЕМЫЙ БЛОК" in plain else ""
        self._status_label.setText(f"{name}  |  {I18n._('common.count')}: {chars} {I18n._('template.chars')}, {words} {I18n._('template.words')}{repeat_used}")
        self._update_page_nav(keep_position=True)

    def _editor_context_menu(self, pos: QPoint) -> None:
        menu = QMenu(self._editor)
        menu.setStyleSheet("""
            QMenu { background: #2C2C2E; color: #FFFFFF; border: 1px solid #3A3A3C;
                    border-radius: 8px; padding: 4px; }
            QMenu::item { padding: 8px 28px 8px 14px; border-radius: 4px; }
            QMenu::item:selected { background: #0A84FF; color: #FFFFFF; }
            QMenu::separator { height: 1px; background: #3A3A3C; margin: 4px 10px; }
        """)
        menu.addAction(I18n._("common.undo"), lambda: self._editor.undo(), QKeySequence.Undo)
        menu.addAction(I18n._("common.redo"), lambda: self._editor.redo(), QKeySequence.Redo)
        menu.addSeparator()
        menu.addAction(I18n._("common.cut"), lambda: self._editor.cut(), QKeySequence.Cut)
        menu.addAction(I18n._("common.copy"), lambda: self._editor.copy(), QKeySequence.Copy)
        menu.addAction(I18n._("common.paste"), lambda: self._editor.paste(), QKeySequence.Paste)
        menu.addSeparator()
        menu.addAction(I18n._("common.select_all"), lambda: self._editor.selectAll(), QKeySequence.SelectAll)
        cursor = self._editor.textCursor()
        pos_in_doc = cursor.position()
        root = self._editor.document().rootFrame()
        in_table = False
        for fr in root.childFrames():
            if isinstance(fr, QTextTable):
                if fr.firstPosition() <= pos_in_doc <= fr.lastPosition():
                    in_table = True
                    break
        if in_table:
            menu.addSeparator()
            menu.addAction("↔ 100%", lambda: self._resize_table(100))
            menu.addAction("↔ 75%", lambda: self._resize_table(75))
            menu.addAction("↔ 50%", lambda: self._resize_table(50))
            menu.addAction("↔ 25%", lambda: self._resize_table(25))
        menu.exec_(self._editor.viewport().mapToGlobal(pos))

    def _filter_field_tree(self, text: str) -> None:
        for i in range(self._field_tree.topLevelItemCount()):
            parent = self._field_tree.topLevelItem(i)
            parent.setHidden(True)
            visible = False
            for j in range(parent.childCount()):
                child = parent.child(j)
                match = not text or text.lower() in child.text(0).lower()
                child.setHidden(not match)
                if match:
                    visible = True
            parent.setHidden(not visible)
            if visible:
                parent.setExpanded(True)
        self._field_combo.blockSignals(True)
        current = self._field_combo.currentIndex()
        for i in range(self._field_combo.count()):
            if i == 0:
                continue
            item_text = self._field_combo.itemText(i)
            self._field_combo.setItemHidden(i, bool(text) and text.lower() not in item_text.lower())
        if current > 0 and self._field_combo.isItemHidden(current):
            self._field_combo.setCurrentIndex(0)
        self._field_combo.blockSignals(False)

    def _load_template_content(self, idx: int) -> None:
        if idx < 0:
            return
        tid = self._template_combo.itemData(idx)
        if not tid:
            return
        t = self.db.fetch_one("SELECT * FROM print_templates WHERE id=?", (tid,))
        if t:
            self._current_id = t["id"]
            self._editor.setHtml(t.get("html_content", ""))
            self._template_name_edit.setText(t.get("name", ""))

    def _new_template(self) -> None:
        name, ok = QInputDialog.getText(self, I18n._("template.register"),
                                        I18n._("template.name_prompt"))
        if not ok or not name.strip():
            return
        template_type = self._type_combo.currentData()
        t = I18n._("print.order") if template_type == "order" else I18n._("print.report")
        default_html = f"<h1>{t}</h1><p>« {I18n._('template.edit')} »</p>"
        try:
            new_id = self.db.save_print_template(name.strip(), template_type, default_html)
            self._current_id = new_id
            self._load_templates()
            for i in range(self._template_combo.count()):
                if self._template_combo.itemData(i) == new_id:
                    self._template_combo.setCurrentIndex(i)
                    break
            self._editor.setHtml(default_html)
            self._template_name_edit.setText(name.strip())
            ToastNotification.notify(I18n._("common.success"), "success", 3000)
        except Exception:
            ToastNotification.notify(I18n._("error.generic"), "error", 5000)

    def _save_template(self) -> None:
        html = self._editor.toHtml().strip()
        if not html:
            ToastNotification.notify(I18n._("error.invalid_data"), "error", 3000)
            return
        name = self._template_name_edit.text().strip() or self._template_combo.currentText().strip()
        if not name:
            ToastNotification.notify(I18n._("error.invalid_data"), "error", 3000)
            return
        template_type = self._type_combo.currentData()
        try:
            if self._current_id:
                self.db.save_print_template(name, template_type, html, template_id=self._current_id)
            else:
                new_id = self.db.save_print_template(name, template_type, html)
                self._current_id = new_id
            self._load_templates()
            for i in range(self._template_combo.count()):
                if self._template_combo.itemData(i) == self._current_id:
                    self._template_combo.setCurrentIndex(i)
                    break
            self._template_name_edit.setText(name)
            ToastNotification.notify(I18n._("common.saved"), "success", 3000)
            self._saved = True
        except Exception:
            ToastNotification.notify(I18n._("error.generic"), "error", 5000)

    def _auto_save(self) -> None:
        if self._editor.document().isModified():
            self._save_template()
            self._editor.document().setModified(False)

    def _delete_template(self) -> None:
        if not self._current_id:
            return
        reply = QMessageBox.question(self, I18n._("common.confirm"),
                                     I18n._("template.delete_confirm"),
                                     QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        self.db.execute("DELETE FROM print_templates WHERE id=?", (self._current_id,))
        self._current_id = 0
        self._load_templates()
        ToastNotification.notify(I18n._("common.done"), "success", 3000)

    def _reset_template(self) -> None:
        reply = QMessageBox.question(self, I18n._("common.confirm"),
                                     I18n._("template.reset") + "?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        template_type = self._type_combo.currentData()
        defaults = self.db.fetch_one(
            "SELECT * FROM print_templates WHERE template_type=? AND is_default=1",
            (template_type,))
        if defaults:
            self._editor.setHtml(defaults.get("html_content", ""))
            ToastNotification.notify(I18n._("common.done"), "success", 3000)

    def _rename_template(self) -> None:
        tid = self._template_combo.currentData()
        if not tid:
            ToastNotification.notify(I18n._("common.no_data"), "warning", 3000)
            return
        old_name = self._template_combo.currentText().rsplit(" ", 1)[0]
        new_name, ok = QInputDialog.getText(self, I18n._("common.rename"),
                                             I18n._("template.name"), text=old_name)
        if ok and new_name.strip():
            self.db.execute("UPDATE print_templates SET name=? WHERE id=?", (new_name.strip(), tid))
            self._template_name_edit.setText(new_name.strip())
            self._load_templates()
            ToastNotification.notify(I18n._("common.done"), "success", 3000)

    def _zoom_in(self) -> None:
        self._zoom_level = min(400, self._zoom_level + 10)
        self._apply_zoom()

    def _zoom_out(self) -> None:
        self._zoom_level = max(5, self._zoom_level - 10)
        self._apply_zoom()

    def _reset_zoom(self) -> None:
        self._zoom_level = 100
        self._apply_zoom()

    def _apply_zoom(self) -> None:
        self._zoom_label.setText(f"{self._zoom_level}%")
        self._zoom_slider.blockSignals(True)
        self._zoom_slider.setValue(self._zoom_level)
        self._zoom_slider.blockSignals(False)
        self._resize_editor()
        self._sync_editor_height()

    def _apply_zoom_slider(self, val: int) -> None:
        self._zoom_level = val
        self._apply_zoom()

    def _resize_editor(self) -> None:
        vs = self._editor_scroll.viewport().size()
        page_padding = 60
        fit_width = max(520, vs.width() - page_padding)
        fit_height = max(700, vs.height() - page_padding)

        pw, ph = self._orientations[self._orientation]
        width_scale = fit_width / float(pw)
        height_scale = fit_height / float(ph)
        fit_scale = min(width_scale, height_scale)
        fit_scale = max(0.2, fit_scale)
        zoom_scale = fit_scale * (self._zoom_level / 100.0)

        w = max(420, int(pw * zoom_scale))
        h = max(594, int(ph * zoom_scale))

        self._editor.setMinimumSize(w, h)
        self._editor.setMaximumWidth(w)
        self._editor.setMaximumHeight(16777215)
        self._editor.resize(w, h)
        self._editor.document().setPageSize(QSizeF(w, h))

    def _fit_page(self) -> None:
        self._zoom_level = 100
        self._apply_zoom()

    def _fit_width(self) -> None:
        vs = self._editor_scroll.viewport().size()
        pw, ph = self._orientations[self._orientation]
        w = max(520, vs.width() - 40)
        h = max(594, int(w * (ph / float(pw))))
        self._editor.setMinimumSize(w, h)
        self._editor.setMaximumWidth(w)
        self._editor.resize(w, h)
        self._zoom_level = 100
        self._zoom_label.setText("100%")
        self._sync_editor_height()

    def _get_page_pixel_height(self) -> int:
        pw, ph = self._orientations[self._orientation]
        return max(1, int(self._editor.width() * (ph / float(pw))))

    def _update_page_guide(self) -> None:
        if not hasattr(self, '_page_guide'):
            return
        self._page_guide.setGeometry(self._editor.geometry())
        self._page_guide.show()
        self._page_guide.raise_()
        self._page_guide.update()
        if hasattr(self, '_ruler'):
            self._ruler.update_position()

    def _update_page_nav(self, keep_position: bool = False) -> None:
        try:
            total = max(1, self._editor.document().pageCount())
        except Exception:
            total = 1
        current = min(self._page_nav_spin.value(), total) if keep_position else 1
        self._page_nav_spin.blockSignals(True)
        self._page_nav_spin.setMaximum(total)
        self._page_nav_spin.setValue(current)
        self._page_nav_spin.setSuffix(" / " + str(total))
        self._page_nav_spin.blockSignals(False)

    def _go_to_page(self, page: int) -> None:
        try:
            pw, ph = self._orientations[self._orientation]
            scale = self._editor.width() / float(pw) if pw else 1.0
            page_h = max(594, int(ph * scale))
            scroll_to = (page - 1) * page_h
            self._editor.verticalScrollBar().setValue(scroll_to)
        except Exception:
            pass

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        QTimer.singleShot(50, self._update_page_guide)
        if event.oldSize().width() != event.size().width():
            QTimer.singleShot(200, lambda: (self._update_page_guide(), self._sync_editor_height()))

    def _sync_editor_height(self) -> None:
        pw, ph = self._orientations[self._orientation]
        scale = self._editor.width() / float(pw) if pw else 1.0
        page_h = max(594, int(ph * scale))
        self._editor.document().setPageSize(QSizeF(self._editor.width(), page_h))
        page_count = self._editor.document().pageCount()
        target_h = max(page_h, page_count * page_h)
        self._editor.setMinimumHeight(target_h)
        self._editor.resize(self._editor.width(), target_h)
        self._update_page_guide()
        self._update_page_nav()

    def _on_orientation_changed(self, idx: int) -> None:
        self._orientation = self._orientation_combo.itemData(idx)
        self._apply_page_margins()
        self._fit_page()
        self._sync_editor_height()

    def _toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _insert_table(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle(I18n._("template.insert_table"))
        dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        dlg.setMinimumSize(420, 240)
        dlg.resize(520, 260)
        dlg.setStyleSheet(
            "QDialog { background: #F5F5F7; }"
            "QSpinBox { min-height: 30px; min-width: 90px; padding-right: 26px; }"
            "QSpinBox::up-button, QSpinBox::down-button { width: 24px; border-left: 1px solid #C0C4CC; background: #FFFFFF; }"
            "QSpinBox::up-arrow { image: none; width: 0; height: 0; border-left: 4px solid transparent; border-right: 4px solid transparent; border-bottom: 6px solid #2C3E50; }"
            "QSpinBox::down-arrow { image: none; width: 0; height: 0; border-left: 4px solid transparent; border-right: 4px solid transparent; border-top: 6px solid #2C3E50; }"
        )
        lay = QVBoxLayout(dlg)
        lay.setSpacing(8)

        # Preview grid: show a visual table preview
        preview_label = QLabel(I18n._("template.insert_table") + ":")
        preview_label.setStyleSheet("font-weight: bold;")
        lay.addWidget(preview_label)

        # Rows
        rows_hint = QLabel("<b>" + I18n._("template.table_rows") + "</b>  <span style='color:#6B7280;'>" + I18n._("template.table_hint_rows") + "</span>")
        rows_hint.setWordWrap(True)
        lay.addWidget(rows_hint)
        rl = QHBoxLayout()
        rs = QSpinBox(); rs.setRange(1, 20); rs.setValue(3)
        rs.setMinimumHeight(28)
        rs.setStyleSheet(
            "QSpinBox { padding: 4px 28px 4px 8px; border: 1px solid #999; border-radius: 6px; background: #FFFFFF; color: #2C3E50; }"
            "QSpinBox::up-button { subcontrol-origin: border; subcontrol-position: top right; width: 24px; border-left: 1px solid #999; border-top-right-radius: 6px; }"
            "QSpinBox::up-arrow { width: 8px; height: 8px; }"
            "QSpinBox::down-button { subcontrol-origin: border; subcontrol-position: bottom right; width: 24px; border-left: 1px solid #999; border-bottom-right-radius: 6px; }"
            "QSpinBox::down-arrow { width: 8px; height: 8px; }")
        rl.addWidget(rs)
        lay.addLayout(rl)
        cols_hint = QLabel("<b>" + I18n._("template.table_columns") + "</b>  <span style='color:#6B7280;'>" + I18n._("template.table_hint_columns") + "</span>")
        cols_hint.setWordWrap(True)
        lay.addWidget(cols_hint)
        cl = QHBoxLayout()
        cs = QSpinBox(); cs.setRange(1, 10); cs.setValue(3)
        cs.setMinimumHeight(28)
        cs.setStyleSheet(
            "QSpinBox { padding: 4px 28px 4px 8px; border: 1px solid #999; border-radius: 6px; background: #FFFFFF; color: #2C3E50; }"
            "QSpinBox::up-button { subcontrol-origin: border; subcontrol-position: top right; width: 24px; border-left: 1px solid #999; border-top-right-radius: 6px; }"
            "QSpinBox::up-arrow { width: 8px; height: 8px; }"
            "QSpinBox::down-button { subcontrol-origin: border; subcontrol-position: bottom right; width: 24px; border-left: 1px solid #999; border-bottom-right-radius: 6px; }"
            "QSpinBox::down-arrow { width: 8px; height: 8px; }")
        cl.addWidget(cs)
        lay.addLayout(cl)
        btn_lay = QHBoxLayout()
        ok_btn = QPushButton(I18n._("common.ok"))
        ok_btn.clicked.connect(dlg.accept)
        btn_lay.addWidget(ok_btn)
        cancel_btn = QPushButton(I18n._("common.cancel"))
        cancel_btn.clicked.connect(dlg.reject)
        btn_lay.addWidget(cancel_btn)
        lay.addLayout(btn_lay)
        if dlg.exec_() != QDialog.Accepted:
            return
        rows, cols = rs.value(), cs.value()
        col_width = round(100 / max(1, cols), 2)
        table_html = (
            "<table border='1' cellspacing='0' cellpadding='0' "
            "style='border-collapse:collapse;width:100%;table-layout:fixed;margin:8px 0;'>"
        )
        for r in range(rows):
            table_html += "<tr>"
            for c in range(cols):
                table_html += (
                    f"<td style='width:{col_width}%;padding:8px;vertical-align:top;"
                    "word-break:break-word;overflow-wrap:anywhere;'>"
                    "&nbsp;</td>"
                )
            table_html += "</tr>"
        table_html += "</table>"
        table_html += (
            "<style>table img, td img {max-width:100%;height:auto;display:block;} "
            "table p {margin:0 0 6px 0;} table td {vertical-align:top;}</style>"
            "<p><br></p>"
        )
        self._editor.insertHtml(table_html)
        self._sync_editor_height()

    def _resize_table(self, pct: int) -> None:
        cursor = self._editor.textCursor()
        pos = cursor.position()
        doc = self._editor.document()
        root = doc.rootFrame()
        target_table = None
        for fr in root.childFrames():
            if isinstance(fr, QTextTable):
                if fr.firstPosition() <= pos <= fr.lastPosition():
                    target_table = fr
                    break
        if not target_table:
            return
        col_count = target_table.columns()
        col_pct = round(pct / max(1, col_count), 2)
        fmt = target_table.format()
        widths = [QTextLength(QTextLength.PercentageLength, col_pct)] * col_count
        fmt.setColumnWidthConstraints(widths)
        target_table.setFormat(fmt)
        self._sync_editor_height()


    def _clear_formatting(self) -> None:
        cursor = self._editor.textCursor()
        if cursor.hasSelection():
            html = cursor.selection().toHtml()
            import re
            html = re.sub(r'style="[^"]*"', '', html)
            html = re.sub(r'<span[^>]*>', '', html)
            html = re.sub(r'</span>', '', html)
            html = re.sub(r'<font[^>]*>', '', html)
            html = re.sub(r'</font>', '', html)
            cursor.insertHtml(html)
        else:
            dfmt = self._editor.currentCharFormat()
            dfmt.setFont(QFont("Segoe UI", 11))
            dfmt.setFontWeight(QFont.Normal)
            dfmt.setFontItalic(False)
            dfmt.setFontUnderline(False)
            dfmt.setFontStrikeOut(False)
            dfmt.setForeground(QColor("#2C3E50"))
            self._editor.setCurrentCharFormat(dfmt)

    def _apply_line_spacing(self, val: float) -> None:
        cursor = self._editor.textCursor()
        fmt = cursor.blockFormat()
        fmt.setLineHeight(val * 100, QTextBlockFormat.ProportionalHeight)
        cursor.setBlockFormat(fmt)
        self._editor.setTextCursor(cursor)

    def _auto_format_document(self) -> None:
        import re
        html = self._editor.toHtml().strip()
        if not html:
            return
        html = re.sub(
            r"<table(?![^>]*table-layout:fixed)([^>]*)>",
            r"<table\1 style='width:100%;border-collapse:collapse;table-layout:fixed;margin:8px 0;'>",
            html
        )
        html = re.sub(
            r"<td(?![^>]*vertical-align:top)([^>]*)>",
            r"<td\1 style='padding:8px;vertical-align:top;word-break:break-word;overflow-wrap:anywhere;'>",
            html
        )
        html = re.sub(r"<img(?![^>]*max-width:100%)([^>]*)>", r"<img\1 style='max-width:100%;height:auto;display:block;'>", html)
        html = html.replace("<p></p>", "<p><br></p>")
        self._editor.blockSignals(True)
        self._editor.setHtml(html)
        self._editor.blockSignals(False)
        self._sync_editor_height()
        self._update_status()

    def _insert_header_block(self) -> None:
        self._editor.insertHtml(
            "<table style='width:100%; border-collapse:collapse; margin-bottom:16px;'><tr>"
            "<td style='width:50%; vertical-align:top;'><b>{company}</b><br>{date}</td>"
            "<td style='width:50%; text-align:right; vertical-align:top;'>№ {record_number}</td>"
            "</tr></table><p><br></p>"
        )
        self._sync_editor_height()

    def _insert_signature_block(self) -> None:
        self._editor.insertHtml(
            "<p><br></p><table style='width:100%; border-collapse:collapse; margin-top:20px;'><tr>"
            "<td style='width:60%;'>Ответственный: {responsible}</td>"
            "<td style='width:40%; text-align:right;'>Подпись: ____________</td>"
            "</tr></table>"
        )
        self._sync_editor_height()

    def _find_text(self) -> None:
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QCheckBox
        dlg = QDialog(self)
        dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        dlg.setWindowTitle(I18n._("common.find"))
        dlg.setFixedSize(360, 140)
        lay = QVBoxLayout(dlg)
        search_input = QLineEdit()
        search_input.setPlaceholderText(I18n._("common.find"))
        lay.addWidget(search_input)
        case_cb = QCheckBox(I18n._("template.match_case"))
        lay.addWidget(case_cb)
        btn_lay = QHBoxLayout()
        def _do_find():
            flags = QTextDocument.FindFlags()
            if case_cb.isChecked():
                flags |= QTextDocument.FindCaseSensitively
            self._editor.find(search_input.text(), flags)
        find_btn = QPushButton(I18n._("common.find"))
        find_btn.clicked.connect(_do_find)
        btn_lay.addWidget(find_btn)
        close_btn = QPushButton(I18n._("common.close"))
        close_btn.clicked.connect(dlg.accept)
        btn_lay.addWidget(close_btn)
        lay.addLayout(btn_lay)
        search_input.returnPressed.connect(_do_find)
        dlg.exec_()

    def _insert_separator(self) -> None:
        self._editor.insertHtml("<hr style='border:none;border-top:1px solid #C0C4CC;margin:12px 0;'>")

    def _insert_page_break(self) -> None:
        self._editor.insertHtml(
            "<div style='page-break-before:always; border-top: 2px dashed #A0A4AC; "
            "margin: 30px 0 10px 0; padding: 4px 0; text-align: center;'>"
            "<span style='background:#E8ECF1; color:#8E8E93; font-size:9pt; "
            "padding:2px 16px; border-radius:8px;'>📄 A4</span></div>")

    def _insert_date(self) -> None:
        from datetime import datetime
        self._editor.insertPlainText(datetime.now().strftime("%d.%m.%Y"))

    def _quick_print(self) -> None:
        PrintEngine.print_document(self._editor.toHtml(), self)

    def _insert_image(self) -> None:
        from PyQt5.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(self, "Выберите изображение",
                                               "", "Изображения (*.png *.jpg *.jpeg *.gif *.bmp)")
        if not path:
            return
        import os
        size_mb = os.path.getsize(path) / (1024 * 1024)
        if size_mb > 10:
            QMessageBox.warning(self, "Ошибка",
                f"Файл слишком большой ({size_mb:.1f} МБ). Максимум 10 МБ.")
            return
        import base64
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        ext = path.rsplit(".", 1)[-1].lower()
        mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                "gif": "image/gif", "bmp": "image/bmp"}.get(ext, "image/png")
        self._editor.insertHtml(
            f'<p><img src="data:{mime};base64,{b64}" '
            f'style="max-width:100%;height:auto;display:block;margin:8px 0;"></p>')
        self._sync_editor_height()

    def _indent(self) -> None:
        cursor = self._editor.textCursor()
        block = cursor.block()
        fmt = block.blockFormat()
        fmt.setIndent(fmt.indent() + 1)
        cursor.setBlockFormat(fmt)
        self._editor.setTextCursor(cursor)

    def _unindent(self) -> None:
        cursor = self._editor.textCursor()
        block = cursor.block()
        fmt = block.blockFormat()
        fmt.setIndent(max(0, fmt.indent() - 1))
        cursor.setBlockFormat(fmt)
        self._editor.setTextCursor(cursor)

    def _import_template(self) -> None:
        from PyQt5.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(self, "Импорт шаблона",
                                               "", "HTML файлы (*.html *.htm);;Все файлы (*)")
        if path:
            with open(path, "r", encoding="utf-8") as f:
                html = f.read()
            self._editor.blockSignals(True)
            self._editor.setHtml(html)
            self._editor.blockSignals(False)
            self._sync_editor_height()
            self._update_status()
            ToastNotification.notify(I18n._("template.imported"), "success", 3000)

    def _export_template(self) -> None:
        from PyQt5.QtWidgets import QFileDialog
        html = self._editor.toHtml().strip()
        if not html:
            ToastNotification.notify(I18n._("error.invalid_data"), "error", 3000)
            return
        name = self._template_name_edit.text().strip() or "template"
        path, _ = QFileDialog.getSaveFileName(self, "Экспорт шаблона",
                                               f"{name}.html",
                                               "HTML файлы (*.html *.htm);;Все файлы (*)")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(html)
            ToastNotification.notify(I18n._("template.exported"), "success", 3000)

    def _toggle_ruler(self) -> None:
        if hasattr(self, '_ruler'):
            self._ruler.setVisible(not self._ruler.isVisible())
            if self._ruler.isVisible():
                self._ruler.update_position()

    def _export_pdf(self) -> None:
        from PyQt5.QtPrintSupport import QPrinter, QPrintDialog
        printer = QPrinter(QPrinter.HighResolution)
        printer.setPageSize(QPrinter.A4)
        dlg = QPrintDialog(printer, self)
        if dlg.exec_() == QPrintDialog.Accepted:
            self._editor.document().print_(printer)
            ToastNotification.notify(I18n._("template.pdf_sent"), "success", 3000)

    def _show_html_source(self) -> None:
        from PyQt5.QtWidgets import QPlainTextEdit
        dlg = QDialog(self)
        dlg.setWindowTitle(I18n._("template.html_source"))
        dlg.resize(700, 500)
        lay = QVBoxLayout(dlg)
        editor = QPlainTextEdit()
        editor.setPlainText(self._editor.toHtml())
        editor.setStyleSheet("font-family:Consolas,'Courier New'; font-size:10pt;")
        editor.setReadOnly(True)
        lay.addWidget(editor, 1)
        btn = QPushButton(I18n._("common.close"))
        btn.clicked.connect(dlg.accept)
        hlay = QHBoxLayout()
        hlay.addStretch()
        hlay.addWidget(btn)
        lay.addLayout(hlay)
        dlg.exec_()

    def _toggle_favorite(self) -> None:
        from PyQt5.QtWidgets import QInputDialog
        name = self._template_name_edit.text().strip() or self._template_combo.currentText().strip()
        if not name:
            ToastNotification.notify(I18n._("template.no_active"), "warning", 3000)
            return
        # Toggle favorite via rename prefix
        if name.startswith("★ "):
            new_name = name[2:]
            ToastNotification.notify(I18n._("template.favorite_removed"), "info", 3000)
        else:
            new_name = "★ " + name
            ToastNotification.notify(I18n._("template.favorite_added"), "success", 3000)
        if self._current_id:
            self.db.execute("UPDATE print_templates SET name=? WHERE id=?", (new_name, self._current_id))
            self._template_name_edit.setText(new_name)
            self._load_templates()

    def _case_lower(self) -> None:
        cursor = self._editor.textCursor()
        if cursor.hasSelection():
            cursor.insertText(cursor.selectedText().lower())

    def _case_upper(self) -> None:
        cursor = self._editor.textCursor()
        if cursor.hasSelection():
            cursor.insertText(cursor.selectedText().upper())

    def _case_title(self) -> None:
        cursor = self._editor.textCursor()
        if cursor.hasSelection():
            cursor.insertText(cursor.selectedText().title())

    def _special_chars(self) -> None:
        from PyQt5.QtWidgets import QGridLayout
        dlg = QDialog(self)
        dlg.setWindowTitle(I18n._("template.special_chars"))
        dlg.setFixedSize(420, 260)
        lay = QVBoxLayout(dlg)
        glyphs = "©®™§°±¶•·←↑→↓↔↕♦♥♣♠◘○◙♂♀♪♫☼►◄↕‼¶§▬↨↑↓→←∟↔▲▼"
        glay = QGridLayout()
        glay.setSpacing(4)
        row = col = 0
        for ch in glyphs:
            btn = QPushButton(ch)
            btn.setFixedSize(32, 32)
            btn.setStyleSheet("font-size:14px;")
            btn.clicked.connect(lambda checked, c=ch: (self._editor.insertPlainText(c), dlg.accept()))
            glay.addWidget(btn, row, col)
            col += 1
            if col > 9:
                col = 0; row += 1
        lay.addLayout(glay)
        close_btn = QPushButton(I18n._("common.close"))
        close_btn.clicked.connect(dlg.reject)
        lay.addWidget(close_btn)
        dlg.exec_()

    def _apply_quick_style(self, idx: int) -> None:
        style = self._quick_style_combo.itemData(idx)
        if not style:
            return
        self._quick_style_combo.setCurrentIndex(0)
        html = self._editor.toHtml()
        cursor = self._editor.textCursor()
        if style == "quote":
            cursor.insertHtml('<blockquote style="border-left:4px solid #4B7BFF; margin:12px 0; padding:8px 16px; background:#F7F9FC; color:#4B5563;">Цитата</blockquote>')
        elif style == "alert":
            cursor.insertHtml('<div style="border:1px solid #FFC107; background:#FFF8E1; border-radius:8px; padding:12px; margin:12px 0; color:#856404;">⚠️ Внимание!</div>')
        elif style == "code":
            cursor.insertHtml('<pre style="background:#1E1E2E; color:#D4D4D4; border-radius:6px; padding:12px; font-family:Consolas; font-size:10pt;">код</pre>')
        self._sync_editor_height()

    def _page_bg_color(self) -> None:
        from PyQt5.QtGui import QColorDialog
        color = QColorDialog.getColor(QColor("#FFFFFF"), self, "Цвет фона страницы")
        if color.isValid():
            self._editor.setStyleSheet(
                re.sub(r'background:#[A-Fa-f0-9]{6}', f'background:{color.name()}', self._editor.styleSheet())
                if 'background:#' in self._editor.styleSheet()
                else self._editor.styleSheet() + f" QTextEdit {{ background: {color.name()}; }}")

    def _filter_templates(self, text: str) -> None:
        if not text:
            if hasattr(self, '_saved_template_items'):
                self._template_combo.blockSignals(True)
                self._template_combo.clear()
                for name, data in self._saved_template_items:
                    self._template_combo.addItem(name, data)
                self._template_combo.blockSignals(False)
                del self._saved_template_items
            return
        if not hasattr(self, '_saved_template_items'):
            self._saved_template_items = [(self._template_combo.itemText(i), self._template_combo.itemData(i))
                                          for i in range(self._template_combo.count())]
        self._template_combo.blockSignals(True)
        self._template_combo.clear()
        for name, data in self._saved_template_items:
            if text.lower() in (name or "").lower():
                self._template_combo.addItem(name, data)
        self._template_combo.blockSignals(False)

    def _update_word_count(self) -> None:
        text = self._editor.toPlainText()
        words = len(text.split()) if text.strip() else 0
        chars = len(text)
        self._word_count_label.setText(f"{words} / {chars}")

    def _template_notes(self) -> None:
        from PyQt5.QtWidgets import QTextEdit as QTextEditDialog
        dlg = QDialog(self)
        dlg.setWindowTitle(I18n._("template.notes_title"))
        dlg.resize(400, 300)
        lay = QVBoxLayout(dlg)
        notes = QTextEditDialog()
        notes.setPlainText(self._template_notes_text if hasattr(self, '_template_notes_text') else "")
        notes.setPlaceholderText(I18n._("template.notes_placeholder"))
        lay.addWidget(notes, 1)
        hlay = QHBoxLayout()
        save_btn = QPushButton(I18n._("common.save"))
        def _save_notes():
            self._template_notes_text = notes.toPlainText()
            ToastNotification.notify(I18n._("template.notes_saved"), "success", 2000)
            dlg.accept()
        save_btn.clicked.connect(_save_notes)
        hlay.addStretch()
        hlay.addWidget(save_btn)
        close_btn = QPushButton(I18n._("common.close"))
        close_btn.clicked.connect(dlg.reject)
        hlay.addWidget(close_btn)
        lay.addLayout(hlay)
        dlg.exec_()

    def _document_outline(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle(I18n._("template.document_outline"))
        dlg.resize(300, 400)
        lay = QVBoxLayout(dlg)
        tree = QTreeWidget()
        tree.setHeaderLabels(["Заголовок"])
        tree.setAnimated(True); tree.setIndentation(12)
        doc = self._editor.document()
        block = doc.begin()
        level_map = {}
        root_items = {}
        while block != doc.end():
            fmt = block.blockFormat()
            level = fmt.headingLevel()
            if level > 0:
                text = block.text()[:80]
                item = QTreeWidgetItem([text if text else "(пусто)"])
                item.setData(0, Qt.UserRole, block.position())
                if level == 1:
                    tree.addTopLevelItem(item)
                    level_map = {1: item}
                    root_items[1] = item
                else:
                    parent = level_map.get(level - 1) or root_items.get(1) or tree
                    if isinstance(parent, QTreeWidgetItem):
                        parent.addChild(item)
                    else:
                        tree.addTopLevelItem(item)
                    level_map[level] = item
                for k in list(level_map.keys()):
                    if k > level:
                        del level_map[k]
            block = block.next()
        def _go_to(pos):
            cursor = self._editor.textCursor()
            cursor.setPosition(pos)
            self._editor.setTextCursor(cursor)
            self._editor.setFocus()
            dlg.accept()
        tree.itemDoubleClicked.connect(lambda item, col: _go_to(item.data(0, Qt.UserRole)))
        lay.addWidget(tree, 1)
        close_btn = QPushButton(I18n._("common.close"))
        close_btn.clicked.connect(dlg.reject)
        lay.addWidget(close_btn)
        dlg.exec_()

    # ═══ 10 global changes ═══════════════════════════════════════════

    def _find_replace(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle(I18n._("common.find") + " / " + I18n._("common.replace"))
        dlg.setFixedSize(400, 200)
        lay = QVBoxLayout(dlg)
        find_lay = QHBoxLayout()
        find_lay.addWidget(QLabel(I18n._("common.find") + ":"))
        find_input = QLineEdit()
        find_input.setPlaceholderText(I18n._("common.find"))
        find_lay.addWidget(find_input, 1)
        lay.addLayout(find_lay)
        repl_lay = QHBoxLayout()
        repl_lay.addWidget(QLabel(I18n._("common.replace") + ":"))
        repl_input = QLineEdit()
        repl_input.setPlaceholderText(I18n._("common.replace"))
        repl_lay.addWidget(repl_input, 1)
        lay.addLayout(repl_lay)
        case_cb = QCheckBox(I18n._("template.match_case"))
        lay.addWidget(case_cb)
        btn_lay = QHBoxLayout()
        def _find():
            text = find_input.text()
            if not text:
                return
            flags = QTextDocument.FindFlags() if not case_cb.isChecked() else QTextDocument.FindCaseSensitively
            if not self._editor.find(text, flags):
                cursor = self._editor.textCursor()
                cursor.movePosition(QTextCursor.Start)
                self._editor.setTextCursor(cursor)
                self._editor.find(text, flags)
        def _replace():
            text = find_input.text()
            if not text:
                return
            cursor = self._editor.textCursor()
            if cursor.hasSelection() and cursor.selectedText() == text:
                cursor.insertText(repl_input.text())
            self._editor.find(text)
        def _replace_all():
            text = find_input.text()
            if not text:
                return
            cursor = self._editor.textCursor()
            cursor.movePosition(QTextCursor.Start)
            self._editor.setTextCursor(cursor)
            count = 0
            while self._editor.find(text):
                self._editor.textCursor().insertText(repl_input.text())
                count += 1
            ToastNotification.notify(I18n._("common.replaced_count", count=count), "info", 3000)
        btn_lay.addWidget(_make_btn(I18n._("common.find"), _find))
        btn_lay.addWidget(_make_btn(I18n._("common.replace"), _replace))
        btn_lay.addWidget(_make_btn(I18n._("template.replace_all"), _replace_all))
        btn_lay.addStretch()
        btn_lay.addWidget(_make_btn(I18n._("common.close"), dlg.reject))
        lay.addLayout(btn_lay)
        dlg.exec_()

    def _document_stats(self) -> None:
        doc = self._editor.document()
        text = self._editor.toPlainText()
        words = len(text.split()) if text.strip() else 0
        chars = len(text)
        chars_no_space = len(text.replace(" ", ""))
        paras = doc.blockCount()
        pages = max(1, int(doc.pageCount()))
        lines = 0
        block = doc.begin()
        while block != doc.end():
            lines += block.lineCount()
            block = block.next()
        msg = (
            f"📊 {I18n._('stat.words')}: {words}\n"
            f"🔤 {I18n._('stat.characters')}: {chars}\n"
            f"✏️ {I18n._('stat.characters_no_spaces')}: {chars_no_space}\n"
            f"📝 {I18n._('stat.paragraphs')}: {paras}\n"
            f"📄 {I18n._('stat.pages')}: {pages}\n"
            f"📏 {I18n._('stat.lines')}: {lines}"
        )
        QMessageBox.information(self, I18n._("stat.document_stats"), msg)

    def _increase_font_size(self) -> None:
        cursor = self._editor.textCursor()
        fmt = cursor.charFormat()
        size = fmt.fontPointSize()
        if size <= 0:
            size = 11
        fmt.setFontPointSize(min(72, size + 1))
        cursor.setCharFormat(fmt)
        self._editor.setTextCursor(cursor)
        self._update_format_buttons()

    def _decrease_font_size(self) -> None:
        cursor = self._editor.textCursor()
        fmt = cursor.charFormat()
        size = fmt.fontPointSize()
        if size <= 0:
            size = 11
        fmt.setFontPointSize(max(6, size - 1))
        cursor.setCharFormat(fmt)
        self._editor.setTextCursor(cursor)
        self._update_format_buttons()

    def _align_left(self) -> None:
        self._editor.setAlignment(Qt.AlignLeft)

    def _align_center(self) -> None:
        self._editor.setAlignment(Qt.AlignCenter)

    def _align_right(self) -> None:
        self._editor.setAlignment(Qt.AlignRight)

    def _align_justify(self) -> None:
        self._editor.setAlignment(Qt.AlignJustify)

    def _paste_plain(self) -> None:
        clipboard = QApplication.clipboard()
        text = clipboard.text()
        if text:
            cursor = self._editor.textCursor()
            cursor.insertText(text)
            ToastNotification.notify(I18n._("template.pasted_plain"), "info", 2000)

    def _toggle_ruler_units(self) -> None:
        self._ruler_units = getattr(self, '_ruler_units', 'cm')
        self._ruler_units = 'in' if self._ruler_units == 'cm' else 'cm'
        unit_name = I18n._("template.ruler_cm") if self._ruler_units == 'cm' else I18n._("template.ruler_in")
        ToastNotification.notify(f"{I18n._('common.ruler')}: {unit_name}", "info", 2000)
        if hasattr(self, '_ruler'):
            self._ruler.update()

    def _go_first_page(self) -> None:
        self._editor.verticalScrollBar().setValue(0)
        self._page_nav_spin.setValue(1)

    def _go_last_page(self) -> None:
        scrollbar = self._editor.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        doc = self._editor.document()
        total = max(1, int(doc.pageCount()))
        self._page_nav_spin.setValue(total)

    def _toggle_bullet(self) -> None:
        cursor = self._editor.textCursor()
        block = cursor.block()
        fmt = block.blockFormat()
        if fmt.indent() > 0 or cursor.currentList():
            cursor.currentList().remove(cursor.block())
        else:
            cursor.insertList(QTextListFormat.ListDisc)
        self._bullet_btn.setChecked(cursor.currentList() is not None)

    def _toggle_number(self) -> None:
        cursor = self._editor.textCursor()
        block = cursor.block()
        fmt = block.blockFormat()
        if fmt.indent() > 0 or cursor.currentList():
            cursor.currentList().remove(cursor.block())
        else:
            cursor.insertList(QTextListFormat.ListDecimal)
        self._number_btn.setChecked(cursor.currentList() is not None)

    def _preview_template(self, multi_sample: bool = False) -> None:
        try:
            dlg = QDialog(self)
            dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint)
            dlg.setWindowTitle(I18n._("template.preview"))
            screen = QApplication.primaryScreen().availableGeometry()
            dlg.resize(int(screen.width() * 0.85), int(screen.height() * 0.85))
            dlg.move((screen.width() - dlg.width()) // 2, (screen.height() - dlg.height()) // 2)
            layout = QVBoxLayout(dlg)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)

            pbrowser = QTextBrowser()
            pbrowser.setStyleSheet(
                "QTextBrowser { background: #FFFFFF; color: #2C3E50; border: none; "
                "padding: 30px 40px; font-size: 11pt; }")
            pbrowser.document().setDefaultFont(QFont("Segoe UI", 11))

            raw_html = self._editor.toHtml().strip()
            rendered = raw_html
            if raw_html:
                if self._type_combo.currentData() == "order":
                    if multi_sample:
                        records = [
                            {"id": 1, "data_json": {"description": "Описание нарушения 1", "deadline": "01.07.2026", "recommended_action": "Устранить 1", "fine": "1000", "responsible": "Ответственный 1", "company": "ООО Тест", "date": "01.06.2026"}},
                            {"id": 2, "data_json": {"description": "Описание нарушения 2", "deadline": "05.07.2026", "recommended_action": "Устранить 2", "fine": "2000", "responsible": "Ответственный 2", "company": "ООО Тест", "date": "01.06.2026"}},
                            {"id": 3, "data_json": {"description": "Описание нарушения 3", "deadline": "10.07.2026", "recommended_action": "Устранить 3", "fine": "3000", "responsible": "Ответственный 3", "company": "ООО Тест", "date": "01.06.2026"}},
                        ]
                        repeat_start = "ПОВТОРЯЕМЫЙ БЛОК: 1-е, 2-е, 3-е и следующие предписания"
                        repeat_end = "КОНЕЦ ПОВТОРЯЕМОГО БЛОКА"
                        if repeat_start in raw_html and repeat_end in raw_html:
                            before, rest = raw_html.split(repeat_start, 1)
                            block, after = rest.split(repeat_end, 1)
                            parts = []
                            for index, rec in enumerate(records, start=1):
                                rendered_part = block
                                for key, val in rec["data_json"].items():
                                    rendered_part = rendered_part.replace(f"{{{key}}}", str(val))
                                rendered_part = rendered_part.replace("{id}", str(rec["id"]))
                                rendered_part = rendered_part.replace("{record_number}", str(rec["id"]))
                                rendered_part = rendered_part.replace("{violation_number}", str(index))
                                rendered_part = rendered_part.replace("{violation_index}", str(index))
                                rendered_part = rendered_part.replace("{page_number}", str(index))
                                parts.append(rendered_part)
                            rendered = "<html><body>" + before + "".join(parts) + after + "</body></html>"
                        else:
                            rendered_parts = []
                            for index, rec in enumerate(records, start=1):
                                rendered_part = raw_html
                                for key, val in rec["data_json"].items():
                                    rendered_part = rendered_part.replace(f"{{{key}}}", str(val))
                                rendered_part = rendered_part.replace("{id}", str(rec["id"]))
                                rendered_part = rendered_part.replace("{record_number}", str(rec["id"]))
                                rendered_part = rendered_part.replace("{violation_number}", str(index))
                                rendered_part = rendered_part.replace("{violation_index}", str(index))
                                rendered_part = rendered_part.replace("{page_number}", str(index))
                                rendered_parts.append(rendered_part)
                            rendered = "<html><body>" + rendered_parts[0] + "".join("<div style='page-break-before:always; margin:0; padding:0; height:1px;'></div>" + p for p in rendered_parts[1:]) + "</body></html>"
                    else:
                        sample = {"id": "1", "date": "01.06.2026", "company": "ООО Тест",
                                  "responsible": "Иванов И.И.", "deadline": "30.07.2026",
                                  "description": "Тестовое описание нарушения",
                                  "recommended_action": "Устранить нарушение", "fine": "5000",
                                  "photos_section": "", "app_name": "SUOT", "generated_at": "01.06.2026",
                                  "record_number": "1", "page_number": "1"}
                        rendered = PrintEngine.render_order(sample, photos=[], template_html=raw_html)
                else:
                    rendered = PrintEngine.render_report("ООО Тест", template_html=raw_html)
                pbrowser.setHtml(rendered)
            layout.addWidget(pbrowser, 1)

            btn_layout = QHBoxLayout()
            btn_layout.setContentsMargins(12, 8, 12, 8)
            print_btn = QPushButton("🖨 " + I18n._("common.print"))
            print_btn.clicked.connect(lambda: PrintEngine.print_document(pbrowser.toHtml(), dlg))
            btn_layout.addWidget(print_btn)
            btn_layout.addStretch()
            close_btn = QPushButton(I18n._("common.close"))
            close_btn.clicked.connect(dlg.accept)
            btn_layout.addWidget(close_btn)
            layout.addLayout(btn_layout)

            dlg.exec_()
        except Exception as exc:
            QMessageBox.critical(self, I18n._("template.preview_error"), str(exc))

    def _select_and_close(self) -> None:
        if self._current_id:
            self.selected_id = self._current_id
        self.accept()


# ===========================================================================
# END OF PART 6 — BEGIN PART 7: Import/Export, Global Search, Reports
# ===========================================================================

# ---------------------------------------------------------------------------
# SECTION 7.1: Import Dialog (CSV/Excel with column mapping)
# ---------------------------------------------------------------------------

class ImportDialog(QDialog):
    def __init__(self, table: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.db = DatabaseManager()
        self.setWindowTitle(I18n._("import.title"))
        self.setMinimumSize(700, 550)
        self.resize(800, 600)
        self._source_columns: List[str] = []
        self._source_data: List[Dict[str, str]] = []
        self._target_table: str = table or "employees"
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        heading = QLabel(I18n._("import.title"))
        heading.setProperty("heading", True)
        layout.addWidget(heading)

        file_layout = QHBoxLayout()
        self._file_path = QLineEdit()
        self._file_path.setPlaceholderText(I18n._("import.select"))
        file_layout.addWidget(self._file_path, 1)
        browse_btn = QPushButton("...")
        browse_btn.setFixedWidth(40)
        browse_btn.clicked.connect(self._browse_file)
        file_layout.addWidget(browse_btn)
        layout.addLayout(file_layout)

        table_layout = QHBoxLayout()
        table_layout.addWidget(QLabel(I18n._("common.table") + ":"))
        self._table_combo = QComboBox()
        self._table_combo.addItem(I18n._("tab.employees"), "employees")
        self._table_combo.addItem(I18n._("tab.violations"), "violations")
        self._table_combo.addItem(I18n._("tab.custom_ledger"), "custom_ledger")
        idx = self._table_combo.findData(self._target_table)
        if idx >= 0:
            self._table_combo.setCurrentIndex(idx)
        table_layout.addWidget(self._table_combo)
        table_layout.addStretch()
        parse_btn = QPushButton(I18n._("common.preview"))
        parse_btn.clicked.connect(self._parse_file)
        table_layout.addWidget(parse_btn)
        layout.addLayout(table_layout)

        self._preview_table = QTableWidget()
        self._preview_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._preview_table.setAlternatingRowColors(True)
        self._preview_table.verticalHeader().hide()
        layout.addWidget(self._preview_table, 1)

        map_heading = QLabel(I18n._("import.column_map"))
        map_heading.setStyleSheet("font-weight: 600; font-size: 14px;")
        layout.addWidget(map_heading)

        self._map_layout = QVBoxLayout()
        layout.addLayout(self._map_layout)

        self._mapping_widgets: List[Tuple[QLabel, QComboBox]] = []

        btn_layout = QHBoxLayout()
        self._import_btn = QPushButton(I18n._("import.execute"))
        self._import_btn.setProperty("success", True)
        self._import_btn.clicked.connect(self._execute_import)
        self._import_btn.setEnabled(False)
        btn_layout.addWidget(self._import_btn)
        btn_layout.addStretch()
        close_btn = QPushButton(I18n._("common.close"))
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

    def _browse_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, I18n._("import.select"), "",
            "CSV (*.csv);;Excel (*.xlsx *.xls);;All files (*.*)")
        if path:
            self._file_path.setText(path)

    def _parse_file(self) -> None:
        path = self._file_path.text().strip()
        if not path or not os.path.isfile(path):
            QMessageBox.warning(self, I18n._("common.error"),
                                I18n._("error.file_not_found"))
            return
        ext = os.path.splitext(path)[1].lower()
        try:
            if ext == ".csv":
                self._parse_csv(path)
            elif ext in (".xlsx", ".xls"):
                self._parse_excel(path)
            else:
                QMessageBox.warning(self, I18n._("common.error"),
                                    I18n._("error.import_failed"))
                return
            self._target_table = self._table_combo.currentData()
            self._build_mapping()
            self._import_btn.setEnabled(True)
        except Exception as e:
            QMessageBox.critical(self, I18n._("common.error"),
                                 f"{I18n._('error.import_failed')}: {e}")

    def _parse_csv(self, path: str) -> None:
        with open(path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            self._source_columns = reader.fieldnames or []
            self._source_data = []
            for i, row in enumerate(reader):
                if i >= 100:
                    break
                self._source_data.append(row)
        self._show_preview()

    def _parse_excel(self, path: str) -> None:
        try:
            import openpyxl
            wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
            ws = wb.active
            rows_data = list(ws.iter_rows(values_only=True))
            if not rows_data:
                return
            headers = [str(h) if h is not None else "" for h in rows_data[0]]
            self._source_columns = headers
            self._source_data = []
            for row in rows_data[1:101]:
                d = {}
                for i, h in enumerate(headers):
                    val = row[i] if i < len(row) else ""
                    d[h] = str(val) if val is not None else ""
                self._source_data.append(d)
            wb.close()
            self._show_preview()
        except ImportError:
            QMessageBox.warning(self, I18n._("common.error"),
                                "openpyxl " + I18n._("error.not_found"))

    def _show_preview(self) -> None:
        if not self._source_columns or not self._source_data:
            return
        self._preview_table.setColumnCount(len(self._source_columns))
        self._preview_table.setHorizontalHeaderLabels(self._source_columns)
        self._preview_table.setRowCount(min(len(self._source_data), 10))
        for i, row in enumerate(self._source_data[:10]):
            for j, col in enumerate(self._source_columns):
                self._preview_table.setItem(i, j,
                    QTableWidgetItem(row.get(col, "")))
        self._preview_table.resizeColumnsToContents()

    def _build_mapping(self) -> None:
        while self._map_layout.count():
            item = self._map_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        self._mapping_widgets.clear()

        target_cols = self.db.get_columns_config(self._target_table)
        target_names = [c["name"] for c in target_cols if c["name"] != "ID"]

        for src_col in self._source_columns:
            row = QHBoxLayout()
            src_label = QLabel(f"  {src_col}:")
            src_label.setFixedWidth(160)
            row.addWidget(src_label)
            arrow = QLabel("→")
            arrow.setFixedWidth(20)
            arrow.setAlignment(Qt.AlignCenter)
            row.addWidget(arrow)
            combo = QComboBox()
            combo.addItem("— " + I18n._("import.skip") + " —", "")
            for tn in target_names:
                combo.addItem(tn, tn)
            guess = self._guess_mapping(src_col, target_names)
            if guess:
                idx = combo.findText(guess)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
            row.addWidget(combo, 1)
            self._map_layout.addLayout(row)
            self._mapping_widgets.append((src_label, combo))

    def _guess_mapping(self, source: str, targets: List[str]) -> Optional[str]:
        sl = source.lower().strip()
        alias_map = {
            "фио": "ФИО", "fio": "ФИО", "full name": "ФИО", "name": "ФИО",
            "должность": "Должность", "position": "Должность",
            "фирма": "Фирма", "company": "Фирма", "организация": "Фирма",
            "телефон": "Телефон", "phone": "Телефон",
            "дата": "Дата", "date": "Дата",
            "статус": "Статус", "status": "Статус",
            "описание": "Описание", "description": "Описание",
            "штраф": "Штраф", "fine": "Штраф", "сумма": "Штраф",
            "категория": "Категория риска", "category": "Категория риска",
            "ответственный": "Ответственный", "responsible": "Ответственный",
            "подразделение": "Подразделение", "department": "Подразделение",
            "квалификация": "Квалификация", "qualification": "Квалификация",
        }
        for alias, target in alias_map.items():
            if alias in sl or sl in alias:
                if target in targets:
                    return target
        for t in targets:
            if t.lower().startswith(sl) or sl.startswith(t.lower()):
                return t
        return None

    def _execute_import(self) -> None:
        target_map: Dict[str, str] = {}
        for src_label, combo in self._mapping_widgets:
            src = src_label.text().strip().rstrip(":").strip()
            dst = combo.currentData()
            if dst:
                target_map[src] = dst
        if not target_map:
            QMessageBox.warning(self, I18n._("common.warning"),
                                I18n._("import.execute") + "?")
            return

        # Auto-create missing columns in target table
        target_cols = self.db.get_columns_config(self._target_table)
        existing_names = {c["name"] for c in target_cols}
        max_pos = max((c["position"] for c in target_cols), default=-1)
        for src, dst in target_map.items():
            if dst and dst not in existing_names:
                guessed_type = "Текст"
                lc = dst.lower()
                if any(x in lc for x in ["дата", "date", "срок", "deadline"]):
                    guessed_type = "Дата"
                elif any(x in lc for x in ["штраф", "fine", "сумма", "цена", "price"]):
                    guessed_type = "Число"
                elif any(x in lc for x in ["статус", "status"]):
                    guessed_type = "Статус"
                elif any(x in lc for x in ["фото", "photo", "media"]):
                    guessed_type = "Медиа"
                max_pos += 1
                self.db.execute(
                    "INSERT INTO columns_config (category, name, type, position) VALUES (?, ?, ?, ?)",
                    (self._target_table, dst, guessed_type, max_pos))
                self.db.conn.commit()
                existing_names.add(dst)

        imported = 0
        updated = 0
        errors = 0
        import_log: List[str] = []
        for row_idx, row_data in enumerate(self._source_data):
            try:
                record: Dict[str, Any] = {}
                for src, dst in target_map.items():
                    record[dst] = row_data.get(src, "")
                record.setdefault("Фото", [])
                for c in self.db.get_columns_config(self._target_table):
                    if c["name"] not in record:
                        if c["type"] == "Статус":
                            record[c["name"]] = "Активно"
                        elif c["type"] in ("Дата", "Годен до", "Date", "Valid until"):
                            record[c["name"]] = ""
                        elif c["type"] == "Число":
                            record[c["name"]] = "0"
                        elif c["type"] == "Медиа":
                            record[c["name"]] = []
                        else:
                            record[c["name"]] = ""

                action = "created"
                target_id = 0
                if self._target_table == "employees":
                    existing = self.db.find_employee_duplicate(record)
                    if existing:
                        merged = dict(existing.get("data_json", {}))
                        for k, v in record.items():
                            if isinstance(v, list):
                                if v:
                                    merged[k] = v
                            elif str(v).strip() != "":
                                merged[k] = v
                        self.db.save_json_record("employees", existing["id"], merged)
                        updated += 1
                        action = "updated"
                        target_id = existing["id"]
                        continue
                elif self._target_table == "violations":
                    existing = self.db.find_violation_duplicate(record)
                    if existing:
                        merged = dict(existing.get("data_json", {}))
                        for k, v in record.items():
                            if isinstance(v, list):
                                if v:
                                    merged[k] = v
                            elif str(v).strip() != "":
                                merged[k] = v
                        self.db.save_json_record("violations", existing["id"], merged)
                        updated += 1
                        action = "updated"
                        target_id = existing["id"]
                        continue

                target_id = self.db.save_json_record(self._target_table, 0, record)
                imported += 1
                import_log.append(f"Строка {row_idx+1}: {action} ID={target_id} | {record.get('ФИО', record.get('Описание', record.get('Название', '?')))[:60]}")
            except Exception as e:
                errors += 1
                import_log.append(f"Строка {row_idx+1}: ОШИБКА — {e}")

        self.db.log_event(f"Import: {imported} records, {updated} updated, {errors} errors",
                          "INFO", {"table": self._target_table})
        try:
            self.db.execute(
                "INSERT INTO import_history (table_name, source_file, imported, updated, errors, details) VALUES (?, ?, ?, ?, ?, ?)",
                (self._target_table, getattr(self, "_source_file", ""), imported, updated, errors, "\n".join(import_log[:50])))
            self.db.conn.commit()
        except Exception:
            pass
        self._show_import_log_dialog(imported, updated, errors, import_log)

    def _show_import_log_dialog(self, imported: int, updated: int, errors: int, log: List[str]) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle(I18n._("import.log_title"))
        dlg.resize(700, 450)
        layout = QVBoxLayout(dlg)
        summary = QLabel(
            f"<b>{I18n._('import.success').format(count=imported)}</b>"
            + (f" | {I18n._('import.updated')}: {updated}" if updated else "")
            + (f" | {I18n._('error.generic')}: {errors}" if errors else "")
        )
        summary.setTextFormat(Qt.RichText)
        summary.setWordWrap(True)
        layout.addWidget(summary)
        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setPlainText("\n".join(log))
        text.setLineWrapMode(QPlainTextEdit.NoWrap)
        layout.addWidget(text, 1)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Save)
        btns.accepted.connect(dlg.accept)
        btns.button(QDialogButtonBox.Save).clicked.connect(lambda: self._save_import_log(log))
        layout.addWidget(btns)
        dlg.exec_()

    def _save_import_log(self, log: List[str]) -> None:
        path, _ = QFileDialog.getSaveFileName(self, I18n._("import.save_log"),
                                              "import_log.txt", "Text (*.txt)")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(log))
            ToastNotification.notify(I18n._("export.success").format(path=path), "success", 3000)


# ---------------------------------------------------------------------------
# SECTION 7.2: Export Dialog (CSV / Excel)
# ---------------------------------------------------------------------------

class ExportDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.db = DatabaseManager()
        self.setWindowTitle(I18n._("export.title"))
        self.setMinimumSize(400, 250)
        self.resize(450, 280)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        heading = QLabel(I18n._("export.title"))
        heading.setProperty("heading", True)
        layout.addWidget(heading)

        form = QFormLayout()
        form.setSpacing(10)

        self._table_combo = QComboBox()
        self._table_combo.addItem(I18n._("tab.employees"), "employees")
        self._table_combo.addItem(I18n._("tab.violations"), "violations")
        self._table_combo.addItem(I18n._("tab.custom_ledger"), "custom_ledger")
        form.addRow(I18n._("common.table") + ":", self._table_combo)

        self._format_combo = QComboBox()
        self._format_combo.addItem("CSV (.csv)", "csv")
        self._format_combo.addItem("Excel (.xlsx)", "xlsx")
        form.addRow(I18n._("common.format") + ":", self._format_combo)

        layout.addLayout(form)

        btn_layout = QHBoxLayout()
        self._export_btn = QPushButton(I18n._("common.export"))
        self._export_btn.setProperty("success", True)
        self._export_btn.clicked.connect(self._do_export)
        btn_layout.addWidget(self._export_btn)
        btn_layout.addStretch()
        close_btn = QPushButton(I18n._("common.close"))
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

        self._status_label = QLabel()
        self._status_label.setStyleSheet("font-size: 12px;")
        self._status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._status_label)

    def _do_export(self) -> None:
        table = self._table_combo.currentData()
        fmt = self._format_combo.currentData()
        ext = ".csv" if fmt == "csv" else ".xlsx"
        default_name = f"{table}_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"
        default_path = os.path.join(RUNTIME_PATHS.export_dir, default_name)
        path, _ = QFileDialog.getSaveFileName(
            self, I18n._("common.export"), default_path,
            "CSV (*.csv)" if fmt == "csv" else "Excel (*.xlsx)")
        if not path:
            return

        try:
            if fmt == "csv":
                result = self.db.export_to_csv(table, path)
            else:
                result = self._export_excel(table, path)
            self._status_label.setText(
                I18n._("export.success").format(path=os.path.basename(result)))
            ToastNotification.notify(I18n._("export.success").format(
                path=os.path.basename(result)), "success", 5000)
        except Exception as e:
            self._status_label.setText(I18n._("export.error").format(error=str(e)))
            ToastNotification.notify(I18n._("export.error").format(error=str(e)),
                                   "error", 5000)

    def _export_excel(self, table: str, path: str) -> str:
        try:
            import openpyxl
            from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        except ImportError:
            QMessageBox.warning(self, I18n._("common.error"),
                                "openpyxl " + I18n._("error.not_found"))
            return path

        records = self.db.get_json_records(table)
        columns = self.db.get_columns_config(table)
        headers = [c["name"] for c in columns]

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = table

        header_font = Font(bold=True, color="FFFFFF", size=11)
        header_fill = PatternFill(start_color="1A237E", end_color="1A237E",
                                  fill_type="solid")
        header_align = Alignment(horizontal="center", vertical="center")
        thin_border = Border(
            left=Side(style="thin", color="E0E0E0"),
            right=Side(style="thin", color="E0E0E0"),
            top=Side(style="thin", color="E0E0E0"),
            bottom=Side(style="thin", color="E0E0E0"))

        for ci, h in enumerate(headers, 1):
            cell = ws.cell(row=1, column=ci, value=h)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_align
            cell.border = thin_border

        for ri, rec in enumerate(records, 2):
            dj = rec.get("data_json", {})
            for ci, col in enumerate(columns, 1):
                name = col["name"]
                val = dj.get(name, "")
                if isinstance(val, list):
                    val = ", ".join(val) if val else ""
                cell = ws.cell(row=ri, column=ci, value=str(val))
                cell.border = thin_border
                cell.alignment = Alignment(vertical="center")

        for col in ws.columns:
            max_len = 0
            col_letter = col[0].column_letter
            for cell in col:
                try:
                    max_len = max(max_len, len(str(cell.value or "")))
                except Exception:
                    pass  # non-critical
            ws.column_dimensions[col_letter].width = min(max_len + 4, 40)

        wb.save(path)
        self.db.log_event("Excel export completed", "INFO",
                          {"table": table, "path": path})
        return path


# ---------------------------------------------------------------------------
# SECTION 7.3: Global Search Dialog
# ---------------------------------------------------------------------------

class GlobalSearchDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.db = DatabaseManager()
        self.setWindowTitle(I18n._("search.global"))
        self.setMinimumSize(700, 500)
        self.resize(800, 550)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        heading = QLabel(I18n._("search.global"))
        heading.setProperty("heading", True)
        layout.addWidget(heading)

        search_layout = QHBoxLayout()
        self._search_edit = QLineEdit()
        self._search_edit.setProperty("search", True)
        self._search_edit.setPlaceholderText(I18n._("search.global_placeholder"))
        self._search_edit.textChanged.connect(self._do_search)
        search_layout.addWidget(self._search_edit, 1)
        self._regex_cb = QCheckBox(I18n._("search.regex"))
        self._regex_cb.toggled.connect(self._do_search)
        search_layout.addWidget(self._regex_cb)
        layout.addLayout(search_layout)

        self._results_tree = QTreeWidget()
        self._results_tree.setHeaderLabels([I18n._("search.global"),
                                            I18n._("common.description")])
        self._results_tree.setAlternatingRowColors(True)
        self._results_tree.setColumnWidth(0, 200)
        self._results_tree.itemDoubleClicked.connect(self._on_result_clicked)
        layout.addWidget(self._results_tree)

        self._info_label = QLabel()
        self._info_label.setStyleSheet("font-size: 12px;")
        layout.addWidget(self._info_label)

        close_btn = QPushButton(I18n._("common.close"))
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, 0, Qt.AlignCenter)

    def _do_search(self) -> None:
        text = self._search_edit.text().strip()
        self._results_tree.clear()
        if not text:
            self._info_label.setText("")
            return

        use_regex = self._regex_cb.isChecked()
        pattern = None
        if use_regex:
            try:
                pattern = re.compile(text, re.IGNORECASE)
            except re.error:
                self._info_label.setText(I18n._("error.generic"))
                return

        total = 0
        tables = [
            ("employees", I18n._("tab.employees"), "ФИО"),
            ("violations", I18n._("tab.violations"), "Описание"),
            ("custom_ledger", I18n._("tab.custom_ledger"), "Описание"),
            ("companies", I18n._("tab.companies"), "name"),
        ]
        for table, label, title_field in tables:
            records = []
            if table == "companies":
                records_data = self.db.fetch_all(
                    "SELECT id, name, address, contact, data_json FROM companies")
                for r in records_data:
                    rec = dict(r)
                    rec["data_json"] = JsonUtils.loads(r.get("data_json", "{}"))
                    records.append(rec)
            else:
                records = self.db.get_json_records(table)

            matched = []
            for rec in records:
                dj = rec.get("data_json", {})
                searchable = {**dj}
                if table == "companies":
                    searchable["name"] = rec.get("name", "")
                    searchable["address"] = rec.get("address", "")
                found = False
                for val in searchable.values():
                    sval = str(val)
                    if use_regex:
                        if pattern and pattern.search(sval):
                            found = True
                            break
                    else:
                        if text.lower() in sval.lower():
                            found = True
                            break
                if found:
                    matched.append(rec)

            if matched:
                parent_item = QTreeWidgetItem(self._results_tree)
                parent_item.setText(0, f"{label} ({len(matched)})")
                parent_item.setText(1, "")
                parent_item.setExpanded(False)
                for rec in matched:
                    dj = rec.get("data_json", {})
                    title_val = dj.get(title_field, dj.get("name", ""))
                    desc = dj.get("Описание", dj.get("address", ""))
                    if isinstance(desc, str) and len(desc) > 80:
                        desc = desc[:80] + "..."
                    child = QTreeWidgetItem(parent_item)
                    child.setText(0, str(title_val)[:60])
                    child.setText(1, str(desc)[:120])
                    child.setData(0, Qt.UserRole, table)
                    child.setData(0, Qt.UserRole + 1, rec.get("id", 0))
                total += len(matched)

        self._info_label.setText(
            f"{I18n._('common.filter')}: {total}")

    def _on_result_clicked(self, item: QTreeWidgetItem, col: int) -> None:
        table = item.data(0, Qt.UserRole)
        rid = item.data(0, Qt.UserRole + 1)
        if table and rid and isinstance(self.parent(), QMainWindow):
            mw = self.parent()
            tab_map = {"employees": 1, "violations": 2, "custom_ledger": 4, "companies": 3}
            if table in tab_map:
                mw._tab_widget.setCurrentIndex(tab_map[table])
                tab_w = mw._tab_widget.currentWidget()
                if hasattr(tab_w, '_load_data'):
                    tab_w._load_data()
            ToastNotification.notify(f"{table} #{rid}", "info", 3000)


# ---------------------------------------------------------------------------
# SECTION 7.4: Report Dialog
# ---------------------------------------------------------------------------

class ReportDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.db = DatabaseManager()
        self.setWindowTitle(I18n._("report.title"))
        self.setMinimumSize(500, 450)
        self.resize(550, 500)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        heading = QLabel(I18n._("report.title"))
        heading.setProperty("heading", True)
        layout.addWidget(heading)

        form = QFormLayout()
        form.setSpacing(10)

        self._company_combo = QComboBox()
        self._company_combo.addItem(I18n._("report.all_companies"), "")
        for c in self.db.get_companies():
            self._company_combo.addItem(c["name"], c["name"])
        form.addRow(I18n._("report.company") + ":", self._company_combo)

        self._include_emp = QCheckBox(I18n._("report.employees"))
        self._include_emp.setChecked(True)
        form.addRow("", self._include_emp)

        self._include_viol = QCheckBox(I18n._("report.violations"))
        self._include_viol.setChecked(True)
        form.addRow("", self._include_viol)

        self._include_fines = QCheckBox(I18n._("report.fines"))
        self._include_fines.setChecked(True)
        form.addRow("", self._include_fines)

        layout.addLayout(form)

        btn_layout = QHBoxLayout()
        self._preview_btn = QPushButton(I18n._("common.preview"))
        self._preview_btn.clicked.connect(self._generate_report)
        btn_layout.addWidget(self._preview_btn)
        self._export_html_btn = QPushButton(I18n._("export.title") + " HTML")
        self._export_html_btn.clicked.connect(self._export_html)
        btn_layout.addWidget(self._export_html_btn)
        self._export_excel_btn = QPushButton(I18n._("export.title") + " Excel")
        self._export_excel_btn.clicked.connect(self._export_excel_report)
        btn_layout.addWidget(self._export_excel_btn)
        btn_layout.addStretch()
        close_btn = QPushButton(I18n._("common.close"))
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

        self._status_lbl = QLabel()
        self._status_lbl.setStyleSheet("font-size: 12px;")
        self._status_lbl.setWordWrap(True)
        layout.addWidget(self._status_lbl)

        self._last_html: str = ""

    def _generate_report(self) -> str:
        company = self._company_combo.currentData() or ""
        include_emp = self._include_emp.isChecked()
        include_viol = self._include_viol.isChecked()
        include_fines = self._include_fines.isChecked()
        html = PrintEngine.render_report(company, include_emp, include_viol, include_fines)
        self._last_html = html
        preview_path = os.path.join(tempfile.gettempdir(), "suot_report_preview.html")
        with open(preview_path, "w", encoding="utf-8") as f:
            f.write(html)
        webbrowser.open(f"file://{preview_path}")
        self._status_lbl.setText(I18n._("report.generated"))
        return html

    def _export_html(self) -> None:
        if not self._last_html:
            self._generate_report()
        path, _ = QFileDialog.getSaveFileName(
            self, I18n._("common.export"),
            os.path.join(RUNTIME_PATHS.export_dir,
                         f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"),
            "HTML (*.html)")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self._last_html)
            self._status_lbl.setText(I18n._("export.success").format(path=os.path.basename(path)))

    def _export_excel_report(self) -> None:
        if not self._last_html:
            self._generate_report()
        path, _ = QFileDialog.getSaveFileName(
            self, I18n._("common.export"),
            os.path.join(RUNTIME_PATHS.export_dir,
                         f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"),
            "Excel (*.xlsx)")
        if not path:
            return
        try:
            import openpyxl
            from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        except ImportError:
            QMessageBox.warning(self, I18n._("common.error"), "openpyxl required")
            return

        company = self._company_combo.currentData() or ""
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = I18n._("report.title")

        header_font = Font(bold=True, color="FFFFFF", size=12)
        header_fill = PatternFill(start_color="1A237E", end_color="1A237E",
                                  fill_type="solid")
        thin_border = Border(
            left=Side(style="thin"), right=Side(style="thin"),
            top=Side(style="thin"), bottom=Side(style="thin"))

        # Title
        ws.cell(row=1, column=1,
                value=f"{I18n._('report.title')} — {company or I18n._('report.all_companies')}")
        ws.cell(row=1, column=1).font = Font(bold=True, size=14)
        ws.merge_cells("A1:E1")

        now = datetime.now()
        ws.cell(row=2, column=1, value=now.strftime("%d.%m.%Y %H:%M"))
        ws.merge_cells("A2:E2")

        # Summary header
        row = 4
        headers = [I18n._("company.name"), I18n._("company.employees_count"),
                   I18n._("company.violations_count"), I18n._("company.fines_total"),
                   I18n._("stat.overdue_total")]
        for ci, h in enumerate(headers, 1):
            cell = ws.cell(row=row, column=ci, value=h)
            cell.font = header_font
            cell.fill = header_fill
            cell.border = thin_border
            cell.alignment = Alignment(horizontal="center")

        if company:
            companies_data = [{"name": company}]
        else:
            companies_data = self.db.get_companies()

        for ri, comp in enumerate(companies_data, row + 1):
            cname = comp.get("name", "")
            emp_c = sum(1 for e in self.db.get_json_records("employees")
                        if e.get("data_json", {}).get("Фирма") == cname)
            viol_c = 0
            fines = 0.0
            overdue = 0
            for v in self.db.get_json_records("violations"):
                dj = v.get("data_json", {})
                if dj.get("Фирма") == cname:
                    viol_c += 1
                    try:
                        fines += float(str(dj.get("Штраф", "0"))
                                       .replace(" ", "").replace(",", "."))
                    except Exception:
                        pass  # expected
                    dl = dj.get("Срок устранения", "")
                    try:
                        p = dl.split(".")
                        if len(p) == 3:
                            if datetime(int(p[2]), int(p[1]), int(p[0])) < now:
                                overdue += 1
                    except Exception:
                        pass  # expected
            vals = [cname, emp_c, viol_c, fines, overdue]
            for ci, v in enumerate(vals, 1):
                cell = ws.cell(row=ri, column=ci, value=v)
                cell.border = thin_border
                cell.alignment = Alignment(horizontal="right" if ci > 1 else "left")

        ws.column_dimensions["A"].width = 25
        for c in "BCDE":
            ws.column_dimensions[c].width = 18
        wb.save(path)
        self._status_lbl.setText(I18n._("export.success").format(path=os.path.basename(path)))
        ToastNotification.notify(I18n._("common.success"), "success", 3000)


# ---------------------------------------------------------------------------
# SECTION 7.5: Quick Report Button (global report from toolbar)
# ---------------------------------------------------------------------------

class QuickReportDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.db = DatabaseManager()
        self.setWindowTitle(I18n._("report.title"))
        self.setMinimumSize(900, 600)
        self.resize(1000, 650)
        self._build_ui()
        self._generate()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        heading = QLabel(I18n._("report.title"))
        heading.setProperty("heading", True)
        layout.addWidget(heading)

        self._browser = QTextBrowser()
        self._browser.setOpenExternalLinks(True)
        layout.addWidget(self._browser)

        btn_layout = QHBoxLayout()
        export_btn = QPushButton(I18n._("common.export") + " HTML")
        export_btn.clicked.connect(self._export_html)
        btn_layout.addWidget(export_btn)
        export_excel_btn = QPushButton(I18n._("common.export") + " Excel")
        export_excel_btn.clicked.connect(self._export_excel)
        btn_layout.addWidget(export_excel_btn)
        print_btn = QPushButton(I18n._("common.print"))
        print_btn.clicked.connect(self._print)
        btn_layout.addWidget(print_btn)
        refresh_btn = QPushButton(I18n._("common.refresh"))
        refresh_btn.clicked.connect(self._generate)
        btn_layout.addWidget(refresh_btn)
        btn_layout.addStretch()
        close_btn = QPushButton(I18n._("common.close"))
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

        self._html: str = ""

    def _generate(self) -> None:
        html = PrintEngine.render_report("", True, True, True)
        self._html = html
        self._browser.setHtml(html)

    def _export_html(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, I18n._("common.export"),
            os.path.join(RUNTIME_PATHS.export_dir,
                         f"quick_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"),
            "HTML (*.html)")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self._html)
            ToastNotification.notify(I18n._("common.success"), "success", 3000)

    def _export_excel(self) -> None:
        try:
            import openpyxl
        except ImportError:
            QMessageBox.warning(self, I18n._("common.error"), "openpyxl required")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, I18n._("common.export"),
            os.path.join(RUNTIME_PATHS.export_dir,
                         f"quick_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"),
            "Excel (*.xlsx)")
        if path:
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Report"
            now = datetime.now()
            ws.cell(row=1, column=1, value=f"{I18n._('report.title')} — {now.strftime('%d.%m.%Y')}")
            ws.merge_cells("A1:E1")
            ws.cell(row=1, column=1).font = openpyxl.styles.Font(bold=True, size=14)

            headers = [I18n._("company.name"), I18n._("company.employees_count"),
                       I18n._("company.violations_count"), I18n._("company.fines_total"),
                       I18n._("stat.overdue_total")]
            for ci, h in enumerate(headers, 1):
                cell = ws.cell(row=3, column=ci, value=h)
                cell.font = openpyxl.styles.Font(bold=True, color="FFFFFF")
                cell.fill = openpyxl.styles.PatternFill(start_color="1A237E",
                                                         end_color="1A237E",
                                                         fill_type="solid")
            row = 4
            for comp in self.db.get_companies():
                cname = comp.get("name", "")
                data = {"name": cname}
                ws.cell(row=row, column=1, value=cname)
                ws.cell(row=row, column=2,
                        value=sum(1 for e in self.db.get_json_records("employees")
                                  if e.get("data_json", {}).get("Фирма") == cname))
                viols = [v for v in self.db.get_json_records("violations")
                         if v.get("data_json", {}).get("Фирма") == cname]
                ws.cell(row=row, column=3, value=len(viols))
                fines = 0.0
                overdue = 0
                for v in viols:
                    dj = v.get("data_json", {})
                    try:
                        fines += float(str(dj.get("Штраф", "0"))
                                       .replace(" ", "").replace(",", "."))
                    except Exception:
                        pass  # expected
                    dl = dj.get("Срок устранения", "")
                    try:
                        p = dl.split(".")
                        if len(p) == 3 and datetime(int(p[2]), int(p[1]), int(p[0])) < now:
                            overdue += 1
                    except Exception:
                        pass  # expected
                ws.cell(row=row, column=4, value=fines)
                ws.cell(row=row, column=5, value=overdue)
                row += 1

            ws.column_dimensions["A"].width = 25
            for c in "BCDE":
                ws.column_dimensions[c].width = 18
            wb.save(path)
            ToastNotification.notify(I18n._("common.success"), "success", 3000)

    def _print(self) -> None:
        PrintEngine.print_document(self._html)


# ===========================================================================
# END OF PART 7 — BEGIN PART 8: AI Chat Agent
# ===========================================================================

# ---------------------------------------------------------------------------
# SECTION 8.1: AI Engine (OpenAI-compatible HTTP client)
# ---------------------------------------------------------------------------

import urllib.request as _urllib_request
import urllib.error as _urllib_error


class AIEngine:
    DEFAULT_URL = "https://api.openai.com/v1"
    DEFAULT_MODEL = "gpt-3.5-turbo"

    def __init__(self) -> None:
        self.db = DatabaseManager()
        self.provider: str = self.db.get_ai_setting("provider", "openai")
        self.api_url: str = self.db.get_ai_setting("api_url", self.DEFAULT_URL)
        self.api_key: str = self.db.get_ai_setting("api_key", "")
        self.model: str = self.db.get_ai_setting("model", self.DEFAULT_MODEL)
        self.mode: str = self.db.get_ai_setting("mode", "chat")
        self.temperature: float = float(self.db.get_ai_setting("temperature", "0.7"))

    def save_settings(self) -> None:
        self.db.set_ai_setting("provider", self.provider)
        self.db.set_ai_setting("api_url", self.api_url)
        self.db.set_ai_setting("api_key", self.api_key)
        self.db.set_ai_setting("model", self.model)
        self.db.set_ai_setting("mode", self.mode)
        self.db.set_ai_setting("temperature", str(self.temperature))

    @staticmethod
    def build_system_prompt(db_schema: str = "") -> str:
        schema_section = f"\n\nActual database schema (auto-detected):\n{db_schema}" if db_schema else ""
        return (
            "You are an AI assistant for an Occupational Safety and Health (OSH) "
            "management system called 'СУОТ Enterprise'. "
            "Your tasks: answer questions, search data, analyze statistics, "
            "generate reports, and modify records (only with user confirmation).\n\n"
            "Database schema:\n"
            "1. employees - employee records (fields: ФИО, Должность, Подразделение, "
            "Фирма, Телефон, Дата медосмотра, Квалификация, Дата проведения, Статус)\n"
            "2. violations - safety violations (fields: Дата, Фирма, Подразделение, "
            "Категория риска, Описание, Ответственный, Срок устранения, Штраф, Статус)\n"
            "3. companies - organizations (fields: name, address, contact)\n"
            "4. custom_ledger - custom records (variable fields)\n"
            "5. notes - text notes\n\n"
            "When in AGENT mode, respond with a JSON object:\n"
            "{\"thought\": \"...\", \"action\": \"action_name\", \"params\": {...}}\n\n"
            "Available actions:\n"
            "- respond: just reply to user (params: {\"message\": \"...\"})\n"
            "- search_db: search across tables (params: {\"query\": \"...\", \"table\": \"...\"})\n"
            "- get_stats: get summary statistics\n"
            "- add_record: add a new record (params: {\"table\": \"...\", \"data\": {\"field1\": \"value1\", ...}})\n"
            "- modify_record: modify a record (params: {\"table\": \"...\", \"id\": ..., "
            "\"field\": \"...\", \"value\": \"...\"})\n"
            "- delete_record: delete a record (params: {\"table\": \"...\", \"id\": ...})\n"
            "- create_report: generate company report (params: {\"company\": \"...\"})\n"
            "- rename_column: rename a column (params: {\"table\": \"...\", \"old\": \"...\", "
            "\"new\": \"...\"})\n"
            "- add_note: add a note (params: {\"entity_type\": \"...\", \"entity_id\": ..., \"text\": \"...\"})\n"
            "For 'modify_record', 'add_record', 'delete_record', 'rename_column' and 'add_note', "
            "user confirmation is required."
            + schema_section
        )

    def _build_messages(self, history: List[Dict[str, str]],
                        query: str, schema: str) -> List[Dict[str, str]]:
        msgs = [{"role": "system", "content": self.build_system_prompt(schema)}]
        for h in history:
            msgs.append(h)
        msgs.append({"role": "user", "content": query})
        return msgs

    def send_request(self, history: List[Dict[str, str]],
                     query: str, schema: str = "") -> Optional[str]:
        local_noauth = any(x in self.api_url.lower() for x in ["localhost", "127.0.0.1", "ollama"])
        if not self.api_key and not local_noauth:
            return None
        try:
            provider = self.provider.lower()
            messages = self._build_messages(history, query, schema)

            if provider == "anthropic":
                url = f"{self.api_url.rstrip('/')}/messages"
                payload = json.dumps({
                    "model": self.model,
                    "max_tokens": 4000,
                    "messages": [{"role": m["role"], "content": m["content"]}
                                 for m in messages if m["role"] != "system"],
                    "system": next((m["content"] for m in messages if m["role"] == "system"), ""),
                }).encode("utf-8")
                headers = {
                    "Content-Type": "application/json",
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                }
                req = _urllib_request.Request(url, data=payload, headers=headers)
                resp = _urllib_request.urlopen(req, timeout=90)
                data = json.loads(resp.read().decode("utf-8"))
                if "content" in data and len(data["content"]) > 0:
                    return "".join(b.get("text", "") for b in data["content"] if b.get("type") == "text")
                return json.dumps(data, ensure_ascii=False)[:500]

            if provider == "gemini":
                model_name = self.model.split("/")[-1] if "/" in self.model else self.model
                url = f"{self.api_url.rstrip('/')}/models/{model_name}:generateContent"
                gemini_msgs = []
                for m in messages:
                    role = "user" if m["role"] in ("user", "system") else "model"
                    gemini_msgs.append({"role": role, "parts": [{"text": m["content"]}]})
                payload = json.dumps({"contents": gemini_msgs}).encode("utf-8")
                headers = {"Content-Type": "application/json"}
                if self.api_key:
                    url += f"?key={self.api_key}"
                req = _urllib_request.Request(url, data=payload, headers=headers)
                resp = _urllib_request.urlopen(req, timeout=90)
                data = json.loads(resp.read().decode("utf-8"))
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    return "".join(p.get("text", "") for p in parts)
                return json.dumps(data, ensure_ascii=False)[:500]

            # OpenAI-compatible (default)
            url = f"{self.api_url.rstrip('/')}/chat/completions"
            payload = json.dumps({
                "model": self.model,
                "messages": messages,
                "temperature": self.temperature,
                "max_tokens": 4000,
            }).encode("utf-8")
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            req = _urllib_request.Request(url, data=payload, headers=headers)
            resp = _urllib_request.urlopen(req, timeout=90)
            data = json.loads(resp.read().decode("utf-8"))
            if "choices" in data and len(data["choices"]) > 0:
                return data["choices"][0]["message"]["content"]
            return f"Unexpected response: {json.dumps(data, ensure_ascii=False)[:300]}"
        except _urllib_error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")[:500]
            return f"HTTP Error {e.code}: {e.reason} — {body}"
        except _urllib_error.URLError as e:
            return f"Connection Error: {e.reason}"
        except Exception as e:
            import traceback
            return f"Error: {str(e)}\n{traceback.format_exc()[:300]}"

    def parse_agent_response(self, response: str) -> Dict[str, Any]:
        try:
            cleaned = response.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.strip("`")
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:]
            return json.loads(cleaned)
        except Exception:
            return {"thought": "", "action": "respond",
                    "params": {"message": response}}

    def execute_action(self, action: str, params: Dict[str, Any]) -> str:
        try:
            if action == "respond":
                return params.get("message", "")
            elif action == "search_db":
                query = params.get("query", "")
                table = params.get("table", "")
                return self._action_search(query, table)
            elif action == "get_stats":
                return self._action_stats()
            elif action == "add_record":
                return self._action_add(params)
            elif action == "modify_record":
                return self._action_modify(params)
            elif action == "delete_record":
                return self._action_delete(params)
            elif action == "create_report":
                company = params.get("company", "")
                return self._action_report(company)
            elif action == "rename_column":
                return self._action_rename(params)
            elif action == "add_note":
                return self._action_add_note(params)
            return f"Unknown action: {action}"
        except Exception as e:
            return f"Action error: {e}"

    def _action_search(self, query: str, table: str) -> str:
        results: List[str] = []
        tables_to_search = [table] if table else ["employees", "violations",
                                                    "custom_ledger", "companies"]
        for t in tables_to_search:
            if t == "companies":
                rows = self.db.fetch_all(
                    "SELECT id, name, address, contact FROM companies")
            else:
                rows = self.db.get_json_records(t)
            for r in rows:
                dj = r.get("data_json", {}) if t != "companies" else r
                for val in dj.values():
                    if isinstance(val, str) and query.lower() in val.lower():
                        label = r.get("ФИО", r.get("name", r.get("Описание", f"#{r['id']}")))
                        results.append(f"[{t}] {label}: id={r['id']}")
                        break
        if not results:
            return "No results found."
        return "Found:\n" + "\n".join(results[:20])

    def _action_stats(self) -> str:
        s = self.db.get_statistics()
        return (
            f"Employees: {s['employees_total']}\n"
            f"Violations: {s['violations_total']}\n"
            f"Companies: {s['companies_total']}\n"
            f"Overdue: {s['overdue_total']}\n"
            f"Total Fines: {s['fines_total']:,.0f} RUB")

    def _action_add(self, params: Dict[str, Any]) -> str:
        table = params.get("table", "")
        data = params.get("data", {})
        if not table or not data:
            return "Error: 'table' and 'data' params required"
        cols = self.db.get_columns_config(table)
        record: Dict[str, Any] = {}
        for c in cols:
            if c["name"] in data:
                record[c["name"]] = data[c["name"]]
            elif c["type"] == "Статус":
                record[c["name"]] = "Активно"
            elif c["type"] == "Медиа":
                record[c["name"]] = []
            else:
                record[c["name"]] = ""
        rec_id = self.db.save_json_record(table, 0, record)
        self.db.log_event(f"AI added record #{rec_id} to {table}", "INFO", {"table": table})
        return f"Record #{rec_id} added to {table}."

    def _action_modify(self, params: Dict[str, Any]) -> str:
        table = params.get("table", "")
        rec_id = params.get("id", 0)
        field = params.get("field", "")
        value = params.get("value", "")
        if not table or not rec_id or not field:
            return "Error: 'table', 'id', and 'field' params required"
        records = self.db.get_json_records(table)
        for r in records:
            if r["id"] == rec_id:
                data = r.get("data_json", {})
                data[field] = value
                r["data_json"] = data
                self.db.save_json_record(table, rec_id, data)
                self.db.log_event(f"AI modified record #{rec_id} in {table}: {field} = {value}",
                                  "INFO", {"table": table})
                return f"Record #{rec_id} updated: {field} = {value}"
        return f"Record #{rec_id} not found in {table}."

    def _action_delete(self, params: Dict[str, Any]) -> str:
        table = params.get("table", "")
        rec_id = params.get("id", 0)
        if not table or not rec_id:
            return "Error: 'table' and 'id' params required"
        records = self.db.get_json_records(table)
        for r in records:
            if r["id"] == rec_id:
                self.db.execute("DELETE FROM json_data WHERE id = ? AND category = ?",
                                (rec_id, table))
                self.db.conn.commit()
                self.db.log_event(f"AI deleted record #{rec_id} from {table}",
                                  "INFO", {"table": table})
                return f"Record #{rec_id} deleted from {table}."
        return f"Record #{rec_id} not found in {table}."

    def _action_report(self, company: str) -> str:
        html = PrintEngine.render_report(company, True, True, True)
        return f"Report generated for {company or 'all companies'}."

    def _action_rename(self, params: Dict[str, Any]) -> str:
        table = params.get("table", "")
        old_name = params.get("old", "")
        new_name = params.get("new", "")
        if not table or not old_name or not new_name:
            return "Error: 'table', 'old', and 'new' params required"
        self.db.execute(
            "UPDATE columns_config SET name = ? WHERE category = ? AND name = ?",
            (new_name, table, old_name))
        self.db.conn.commit()
        self.db.log_event(f"AI renamed column '{old_name}' to '{new_name}' in {table}",
                          "INFO", {"table": table})
        return f"Column '{old_name}' renamed to '{new_name}' in {table}."

    def _action_add_note(self, params: Dict[str, Any]) -> str:
        entity_type = params.get("entity_type", "global")
        entity_id = params.get("entity_id", 0)
        text = params.get("text", "")
        if not text:
            return "Error: 'text' param required"
        note_id = self.db.save_note(entity_type=entity_type, entity_id=entity_id,
                                     title=text[:50], content=text)
        self.db.log_event(f"AI added note #{note_id} for {entity_type}:{entity_id}",
                          "INFO", {"entity_type": entity_type})
        return f"Note #{note_id} added for {entity_type}:{entity_id}."


# ---------------------------------------------------------------------------
# SECTION 8.2: AI Chat Dialog
# ---------------------------------------------------------------------------

class AIChatDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.db = DatabaseManager()
        self.engine = AIEngine()
        self._history: List[Dict[str, str]] = []
        self._attachment_path: str = ""
        self.setWindowTitle(I18n._("ai.title"))
        self.setMinimumSize(700, 550)
        self.resize(800, 600)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QFrame()
        header.setStyleSheet("background: transparent; padding: 12px 16px;")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(16, 8, 16, 8)

        heading = QLabel("🤖 " + I18n._("ai.title"))
        heading.setProperty("heading", True)
        hl.addWidget(heading)
        hl.addStretch()

        self._config_toggle = QPushButton("⚙")
        self._config_toggle.setProperty("flat", True)
        self._config_toggle.setFixedSize(32, 32)
        self._config_toggle.setCheckable(True)
        self._config_toggle.toggled.connect(self._toggle_config)
        hl.addWidget(self._config_toggle)

        self._clear_btn = QPushButton(I18n._("ai.clear"))
        self._clear_btn.setProperty("flat", True)
        self._clear_btn.clicked.connect(self._clear_history)
        hl.addWidget(self._clear_btn)

        close_btn = QPushButton("✕")
        close_btn.setProperty("flat", True)
        close_btn.setFixedSize(32, 32)
        close_btn.clicked.connect(self.accept)
        hl.addWidget(close_btn)

        layout.addWidget(header)

        # Config panel (collapsible)
        self._config_panel = QFrame()
        self._config_panel.setProperty("card", True)
        self._config_panel.setVisible(False)
        cl = QFormLayout(self._config_panel)
        cl.setContentsMargins(16, 12, 16, 12)
        cl.setSpacing(8)

        self._provider_combo = QComboBox()
        self._provider_combo.setEditable(True)
        self._provider_combo.setMinimumHeight(36)
        self._provider_combo.addItem("OpenAI", "openai")
        self._provider_combo.addItem("OpenRouter", "openrouter")
        self._provider_combo.addItem("DeepSeek", "deepseek")
        self._provider_combo.addItem("Anthropic", "anthropic")
        self._provider_combo.addItem("Google Gemini", "gemini")
        self._provider_combo.addItem("Groq", "groq")
        self._provider_combo.addItem("Локальный (Local)", "local")
        self._provider_combo.addItem("Пользовательский (Custom)", "custom")
        current_provider = getattr(self.engine, 'provider', 'openai')
        pidx = self._provider_combo.findData(current_provider)
        if pidx >= 0:
            self._provider_combo.setCurrentIndex(pidx)
        self._provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        cl.addRow(I18n._("ai.provider") + ":", self._provider_combo)

        self._api_url_edit = QLineEdit(self.engine.api_url)
        self._api_url_edit.setPlaceholderText("https://api.openai.com/v1")
        self._api_url_edit.setMinimumHeight(36)
        cl.addRow(I18n._("ai.api_url") + ":", self._api_url_edit)

        self._api_key_edit = QLineEdit(self.engine.api_key)
        self._api_key_edit.setEchoMode(QLineEdit.Password)
        self._api_key_edit.setPlaceholderText("sk-...")
        self._api_key_edit.setMinimumHeight(36)
        cl.addRow(I18n._("ai.api_key") + ":", self._api_key_edit)

        self._model_combo = QComboBox()
        self._model_combo.setEditable(True)
        self._model_combo.setMinimumHeight(36)
        self._populate_models(current_provider)
        current_model = self.engine.model
        midx = self._model_combo.findText(current_model)
        if midx >= 0:
            self._model_combo.setCurrentIndex(midx)
        else:
            self._model_combo.setEditText(current_model)
        cl.addRow(I18n._("ai.model") + ":", self._model_combo)

        self._temperature_slider = QSlider(Qt.Horizontal)
        self._temperature_slider.setRange(0, 100)
        self._temperature_slider.setValue(int(float(getattr(self.engine, 'temperature', 0.7)) * 100))
        self._temp_label = QLabel(f"{self._temperature_slider.value() / 100:.1f}")
        self._temperature_slider.valueChanged.connect(
            lambda v: self._temp_label.setText(f"{v / 100:.1f}"))
        temp_row = QHBoxLayout()
        temp_row.addWidget(self._temperature_slider)
        temp_row.addWidget(self._temp_label)
        cl.addRow(I18n._("ai.temperature") + ":", temp_row)

        self._mode_combo = QComboBox()
        self._mode_combo.setMinimumHeight(36)
        self._mode_combo.addItem(I18n._("ai.mode_chat"), "chat")
        self._mode_combo.addItem(I18n._("ai.mode_search"), "search")
        self._mode_combo.addItem(I18n._("ai.mode_agent"), "agent")
        idx = self._mode_combo.findData(self.engine.mode)
        if idx >= 0:
            self._mode_combo.setCurrentIndex(idx)
        cl.addRow(I18n._("ai.mode") + ":", self._mode_combo)

        save_cfg_btn = QPushButton(I18n._("common.save"))
        save_cfg_btn.setProperty("success", True)
        save_cfg_btn.setMinimumHeight(36)
        save_cfg_btn.clicked.connect(self._save_config)
        cl.addRow("", save_cfg_btn)

        layout.addWidget(self._config_panel)

        # Messages area
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self._messages_widget = QWidget()
        self._messages_layout = QVBoxLayout(self._messages_widget)
        self._messages_layout.setContentsMargins(16, 8, 16, 8)
        self._messages_layout.setSpacing(8)
        self._messages_layout.addStretch()
        self._scroll.setWidget(self._messages_widget)
        layout.addWidget(self._scroll, 1)

        # Input area
        input_frame = QFrame()
        input_frame.setProperty("card", True)
        input_layout = QHBoxLayout(input_frame)
        input_layout.setContentsMargins(12, 8, 12, 8)
        input_layout.setSpacing(8)

        self._input_edit = QTextEdit()
        self._input_edit.setPlaceholderText(I18n._("ai.placeholder"))
        self._input_edit.setMaximumHeight(80)
        self._input_edit.setAcceptRichText(False)
        self._input_edit.installEventFilter(self)
        input_layout.addWidget(self._input_edit, 1)

        self._attach_btn = QPushButton("📎")
        self._attach_btn.setFixedSize(36, 36)
        self._attach_btn.setToolTip("Прикрепить файл")
        self._attach_btn.clicked.connect(self._attach_file)
        input_layout.addWidget(self._attach_btn)

        self._send_btn = QPushButton(I18n._("ai.send"))
        self._send_btn.setProperty("success", True)
        self._send_btn.setFixedHeight(36)
        self._send_btn.clicked.connect(self._send_message)
        input_layout.addWidget(self._send_btn)

        layout.addWidget(input_frame)

    def _populate_models(self, provider: str) -> None:
        self._model_combo.clear()
        models = {
            "openai": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
            "openrouter": ["openai/gpt-4o", "anthropic/claude-3-opus", "anthropic/claude-3.5-sonnet", "deepseek/deepseek-r1", "google/gemini-pro"],
            "deepseek": ["deepseek-chat", "deepseek-reasoner"],
            "anthropic": ["claude-3-opus-20240229", "claude-3.5-sonnet-20240620", "claude-3-haiku-20240307"],
            "gemini": ["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"],
            "groq": ["llama-3.3-70b-versatile", "mixtral-8x7b-32768", "gemma2-9b-it"],
            "local": ["llama3", "mistral", "qwen2.5", "phi-3"],
        }
        self._model_combo.addItems(models.get(provider, ["gpt-3.5-turbo"]))

    def _on_provider_changed(self, idx: int) -> None:
        provider = self._provider_combo.currentData()
        default_urls = {
            "openai": "https://api.openai.com/v1",
            "openrouter": "https://openrouter.ai/api/v1",
            "deepseek": "https://api.deepseek.com/v1",
            "anthropic": "https://api.anthropic.com/v1",
            "gemini": "https://generativelanguage.googleapis.com/v1beta",
            "groq": "https://api.groq.com/openai/v1",
            "local": "http://localhost:11434/v1",
            "custom": "",
        }
        self._api_url_edit.setText(default_urls.get(provider, "https://api.openai.com/v1"))
        self._populate_models(provider)

    def _toggle_config(self, visible: bool) -> None:
        self._config_panel.setVisible(visible)

    def _save_config(self) -> None:
        self.engine.provider = self._provider_combo.currentData()
        self.engine.api_url = self._api_url_edit.text().strip()
        self.engine.api_key = self._api_key_edit.text().strip()
        self.engine.model = self._model_combo.currentText().strip()
        self.engine.temperature = self._temperature_slider.value() / 100.0
        self.engine.mode = self._mode_combo.currentData()
        self.engine.save_settings()
        ToastNotification.notify(I18n._("common.success"), "success", 3000)

    def _clear_history(self) -> None:
        self._history.clear()
        while self._messages_layout.count() > 1:
            item = self._messages_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

    def _add_message_bubble(self, text: str, is_user: bool = False,
                            is_error: bool = False) -> None:
        bubble = QFrame()
        bubble.setStyleSheet(f"""
            QFrame {{
                background: {"#2196F3" if is_user else ("#F44336" if is_error else "#E8ECF1")};
                border-radius: 12px;
                padding: 10px 14px;
                margin: {"0 60px 0 0" if is_user else "0 0 0 60px"};
            }}
            QLabel {{
                color: {"#FFFFFF" if is_user or is_error else "#2C3E50"};
                font-size: 13px; background: transparent;
            }}
        """)
        bl = QHBoxLayout(bubble)
        bl.setContentsMargins(0, 0, 0, 0)
        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        bl.addWidget(label)
        idx = self._messages_layout.count() - 1
        self._messages_layout.insertWidget(idx, bubble)
        QApplication.processEvents()
        fade_in_widget(bubble, 250)
        QTimer.singleShot(50, self._scroll_to_bottom)

    def _scroll_to_bottom(self) -> None:
        scrollbar = self._scroll.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _attach_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, I18n._("ai.attach_file"), "",
            I18n._("ai.attach_filter"))
        if path:
            self._attachment_path = path
            filename = os.path.basename(path)
            self._attach_btn.setText(f"📎 {filename}")

    def _send_message(self) -> None:
        text = self._input_edit.toPlainText().strip()
        if not text and not self._attachment_path:
            return
        full_text = text
        if self._attachment_path:
            path = self._attachment_path
            fname = os.path.basename(path)
            ext = os.path.splitext(path)[1].lower()
            img_exts = {'.png', '.jpg', '.jpeg', '.gif', '.bmp'}
            text_exts = {'.txt', '.py', '.md', '.csv', '.json', '.xml', '.html', '.css', '.js'}
            if ext in img_exts:
                full_text = f"{text}\n\n[Изображение: {fname}]"
            elif ext in text_exts:
                try:
                    with open(path, "r", encoding="utf-8", errors="replace") as fh:
                        content = fh.read(10000)
                    full_text = f"{text}\n\n[Файл: {fname}]\n```\n{content}\n```"
                except Exception:
                    full_text = f"{text}\n\n[Файл: {fname} (не удалось прочитать)]"
            else:
                full_text = f"{text}\n\n[Файл: {fname}]"
            self._attachment_path = ""
            self._attach_btn.setText("📎")
        self._input_edit.clear()
        self._add_message_bubble(full_text, is_user=True)
        self._history.append({"role": "user", "content": full_text})
        if not self._send_btn.isEnabled():
            return
        self._send_btn.setEnabled(False)
        self._send_btn.setText("⏳ " + I18n._("ai.thinking"))
        QApplication.processEvents()
        QTimer.singleShot(50, lambda: self._process_ai(full_text))

    def _process_ai(self, text: str) -> None:
        try:
            local_noauth = any(x in self.engine.api_url.lower() for x in ["localhost", "127.0.0.1", "ollama"])
            if not self.engine.api_key and not local_noauth:
                self._add_message_bubble(I18n._("ai.no_key"), is_error=True)
                self._send_btn.setEnabled(True)
                self._send_btn.setText(I18n._("ai.send"))
                return

            is_agent = self.engine.mode == "agent"
            schema = self._get_schema_summary() if is_agent else ""

            response = self.engine.send_request(self._history[:-1],
                                                 text, schema)
            if response is None:
                self._add_message_bubble(I18n._("ai.no_key"), is_error=True)
            elif response.startswith("HTTP Error") or response.startswith("Connection Error"):
                self._add_message_bubble(response, is_error=True)
            elif response.startswith("Error:"):
                self._add_message_bubble(response, is_error=True)
            elif not response.strip():
                self._add_message_bubble(I18n._("ai.empty_response") if I18n._("ai.empty_response") != "ai.empty_response" else "Пустой ответ от ИИ", is_error=True)
            elif is_agent:
                self._handle_agent_response(response)
            else:
                self._add_message_bubble(response)
                self._history.append({"role": "assistant", "content": response})
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            self._add_message_bubble(f"Error: {str(e)}\n{tb[:200]}", is_error=True)
        finally:
            self._send_btn.setEnabled(True)
            self._send_btn.setText(I18n._("ai.send"))

    def _get_schema_summary(self) -> str:
        parts = []
        for table in ["employees", "violations", "custom_ledger"]:
            cols = self.db.get_columns_config(table)
            parts.append(f"{table}: {', '.join(c['name'] for c in cols)}")
        companies = self.db.get_companies()
        parts.append(f"companies: {len(companies)} registered")
        return "; ".join(parts)

    def _handle_agent_response(self, response: str) -> None:
        parsed = self.engine.parse_agent_response(response)
        thought = parsed.get("thought", "")
        action = parsed.get("action", "respond")
        params = parsed.get("params", {})

        if thought:
            self._add_message_bubble(f"🤔 {thought}")
            self._history.append({"role": "assistant", "content": f"[Thought] {thought}"})

        if action == "respond":
            msg = params.get("message", response)
            self._add_message_bubble(msg)
            self._history.append({"role": "assistant", "content": msg})
            return

        # Actions that need execution
        if action in ("add_record", "modify_record", "delete_record", "rename_column", "add_note"):
            confirm_text = f"⚠️ AI wants to: {action}\n{json.dumps(params, ensure_ascii=False, indent=2)}"
            reply = QMessageBox.question(self, I18n._("ai.confirm_action").format(action=action),
                                         confirm_text,
                                         QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                result = self.engine.execute_action(action, params)
                self._add_message_bubble(f"✅ {result}")
                self._history.append({"role": "assistant", "content": result})
            else:
                self._add_message_bubble("⛔ " + I18n._("ai.action_cancelled"))
                self._history.append({"role": "assistant",
                                       "content": I18n._("ai.action_cancelled")})
        else:
            result = self.engine.execute_action(action, params)
            self._add_message_bubble(f"📊 {result}")
            self._history.append({"role": "assistant", "content": result})

    def eventFilter(self, obj: QObject, event: Any) -> bool:
        if obj == self._input_edit and event.type() == event.KeyPress:
            if (event.key() == Qt.Key_Return and
                    event.modifiers() != Qt.ShiftModifier):
                if self._send_btn.isEnabled():
                    self._send_message()
                return True
        return super().eventFilter(obj, event)


class AIChatInlineWidget(QWidget):
    """Embedded AI chat widget for use as a tab."""
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.db = DatabaseManager()
        self.engine = AIEngine()
        self._history: List[Dict[str, str]] = []
        self._attachment_path: str = ""
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Config panel
        self._config_panel = QFrame()
        self._config_panel.setProperty("card", True)
        cl = QFormLayout(self._config_panel)
        cl.setContentsMargins(16, 12, 16, 12)
        cl.setSpacing(8)

        self._provider_combo = QComboBox()
        self._provider_combo.setEditable(True)
        self._provider_combo.setMinimumHeight(36)
        self._provider_combo.addItem("OpenAI", "openai")
        self._provider_combo.addItem("OpenRouter", "openrouter")
        self._provider_combo.addItem("DeepSeek", "deepseek")
        self._provider_combo.addItem("Anthropic", "anthropic")
        self._provider_combo.addItem("Google Gemini", "gemini")
        self._provider_combo.addItem("Groq", "groq")
        self._provider_combo.addItem("Локальный (Local)", "local")
        self._provider_combo.addItem("Пользовательский (Custom)", "custom")
        current_provider = getattr(self.engine, 'provider', 'openai')
        pidx = self._provider_combo.findData(current_provider)
        if pidx >= 0:
            self._provider_combo.setCurrentIndex(pidx)
        self._provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        cl.addRow(I18n._("ai.provider") + ":", self._provider_combo)

        self._api_url_edit = QLineEdit(self.engine.api_url)
        self._api_url_edit.setPlaceholderText("https://api.openai.com/v1")
        self._api_url_edit.setMinimumHeight(36)
        cl.addRow(I18n._("ai.api_url") + ":", self._api_url_edit)

        self._api_key_edit = QLineEdit(self.engine.api_key)
        self._api_key_edit.setEchoMode(QLineEdit.Password)
        self._api_key_edit.setPlaceholderText("sk-...")
        self._api_key_edit.setMinimumHeight(36)
        cl.addRow(I18n._("ai.api_key") + ":", self._api_key_edit)

        self._model_combo = QComboBox()
        self._model_combo.setEditable(True)
        self._model_combo.setMinimumHeight(36)
        self._populate_models(current_provider)
        current_model = self.engine.model
        midx = self._model_combo.findText(current_model)
        if midx >= 0:
            self._model_combo.setCurrentIndex(midx)
        else:
            self._model_combo.setEditText(current_model)
        cl.addRow(I18n._("ai.model") + ":", self._model_combo)

        self._temperature_slider = QSlider(Qt.Horizontal)
        self._temperature_slider.setRange(0, 100)
        self._temperature_slider.setValue(int(float(getattr(self.engine, 'temperature', 0.7)) * 100))
        self._temp_label = QLabel(f"{self._temperature_slider.value() / 100:.1f}")
        self._temperature_slider.valueChanged.connect(
            lambda v: self._temp_label.setText(f"{v / 100:.1f}"))
        temp_row = QHBoxLayout()
        temp_row.addWidget(self._temperature_slider)
        temp_row.addWidget(self._temp_label)
        cl.addRow(I18n._("ai.temperature") + ":", temp_row)

        self._mode_combo = QComboBox()
        self._mode_combo.setMinimumHeight(36)
        self._mode_combo.addItem(I18n._("ai.mode_chat"), "chat")
        self._mode_combo.addItem(I18n._("ai.mode_search"), "search")
        self._mode_combo.addItem(I18n._("ai.mode_agent"), "agent")
        idx = self._mode_combo.findData(self.engine.mode)
        if idx >= 0:
            self._mode_combo.setCurrentIndex(idx)
        cl.addRow(I18n._("ai.mode") + ":", self._mode_combo)

        save_cfg_btn = QPushButton(I18n._("common.save"))
        save_cfg_btn.setProperty("success", True)
        save_cfg_btn.setMinimumHeight(36)
        save_cfg_btn.clicked.connect(self._save_config)
        cl.addRow("", save_cfg_btn)

        layout.addWidget(self._config_panel)

        # Messages area
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self._messages_widget = QWidget()
        self._messages_layout = QVBoxLayout(self._messages_widget)
        self._messages_layout.setContentsMargins(16, 8, 16, 8)
        self._messages_layout.setSpacing(8)
        self._messages_layout.addStretch()
        self._scroll.setWidget(self._messages_widget)
        layout.addWidget(self._scroll, 1)

        # Input area
        input_frame = QFrame()
        input_frame.setProperty("card", True)
        input_layout = QHBoxLayout(input_frame)
        input_layout.setContentsMargins(12, 8, 12, 8)
        input_layout.setSpacing(8)

        self._input_edit = QTextEdit()
        self._input_edit.setPlaceholderText(I18n._("ai.placeholder"))
        self._input_edit.setMaximumHeight(80)
        self._input_edit.setAcceptRichText(False)
        self._input_edit.installEventFilter(self)
        input_layout.addWidget(self._input_edit, 1)

        self._attach_btn = QPushButton("📎")
        self._attach_btn.setFixedSize(36, 36)
        self._attach_btn.setToolTip(I18n._("ai.attach_tooltip"))
        self._attach_btn.clicked.connect(self._attach_file)
        input_layout.addWidget(self._attach_btn)

        self._send_btn = QPushButton(I18n._("ai.send"))
        self._send_btn.setProperty("success", True)
        self._send_btn.setFixedHeight(36)
        self._send_btn.clicked.connect(self._send_message)
        input_layout.addWidget(self._send_btn)

        self._clear_btn = QPushButton(I18n._("ai.clear"))
        self._clear_btn.setProperty("flat", True)
        self._clear_btn.clicked.connect(self._clear_history)
        input_layout.addWidget(self._clear_btn)

        layout.addWidget(input_frame)

    def _populate_models(self, provider: str) -> None:
        self._model_combo.clear()
        models = {
            "openai": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
            "openrouter": ["openai/gpt-4o", "anthropic/claude-3.5-sonnet", "deepseek/deepseek-r1", "google/gemini-2.0-flash-001", "meta-llama/llama-3.3-70b-instruct"],
            "deepseek": ["deepseek-chat", "deepseek-reasoner"],
            "anthropic": ["claude-3-5-sonnet-20241022", "claude-3-opus-20240229", "claude-3-haiku-20240307"],
            "gemini": ["gemini-2.0-flash-001", "gemini-1.5-pro", "gemini-1.5-flash"],
            "groq": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"],
            "local": ["llama3", "mistral", "qwen2.5", "phi-3", "deepseek-r1"],
            "custom": [],
        }
        self._model_combo.addItems(models.get(provider, ["gpt-3.5-turbo"]))

    def _on_provider_changed(self, idx: int) -> None:
        provider = self._provider_combo.currentData()
        default_urls = {
            "openai": "https://api.openai.com/v1",
            "openrouter": "https://openrouter.ai/api/v1",
            "deepseek": "https://api.deepseek.com/v1",
            "anthropic": "https://api.anthropic.com/v1",
            "gemini": "https://generativelanguage.googleapis.com/v1beta",
            "groq": "https://api.groq.com/openai/v1",
            "local": "http://localhost:11434/v1",
            "custom": "",
        }
        self._api_url_edit.setText(default_urls.get(provider, "https://api.openai.com/v1"))
        self._populate_models(provider)

    def _save_config(self) -> None:
        self.engine.provider = self._provider_combo.currentData()
        self.engine.api_url = self._api_url_edit.text().strip()
        self.engine.api_key = self._api_key_edit.text().strip()
        self.engine.model = self._model_combo.currentText().strip()
        self.engine.temperature = self._temperature_slider.value() / 100.0
        self.engine.mode = self._mode_combo.currentData()
        self.engine.save_settings()
        self._config_panel.setVisible(False)
        ToastNotification.notify(I18n._("common.success"), "success", 3000)

    def _clear_history(self) -> None:
        self._history.clear()
        while self._messages_layout.count() > 1:
            item = self._messages_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

    def _add_message_bubble(self, text: str, is_user: bool = False,
                            is_error: bool = False) -> None:
        bubble = QFrame()
        bubble.setStyleSheet(f"""
            QFrame {{
                background: {"#2196F3" if is_user else ("#F44336" if is_error else "#E8ECF1")};
                border-radius: 12px;
                padding: 10px 14px;
                margin: {"0 60px 0 0" if is_user else "0 0 0 60px"};
            }}
            QLabel {{
                color: {"#FFFFFF" if is_user or is_error else "#2C3E50"};
                font-size: 13px; background: transparent;
            }}
        """)
        bl = QHBoxLayout(bubble)
        bl.setContentsMargins(0, 0, 0, 0)
        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        bl.addWidget(label)
        idx = self._messages_layout.count() - 1
        self._messages_layout.insertWidget(idx, bubble)
        QApplication.processEvents()
        fade_in_widget(bubble, 250)
        QTimer.singleShot(50, self._scroll_to_bottom)

    def _scroll_to_bottom(self) -> None:
        scrollbar = self._scroll.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _attach_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, I18n._("ai.attach_file"), "",
            I18n._("ai.attach_filter"))
        if path:
            self._attachment_path = path
            filename = os.path.basename(path)
            self._attach_btn.setText(f"📎 {filename}")

    def _send_message(self) -> None:
        text = self._input_edit.toPlainText().strip()
        if not text and not self._attachment_path:
            return
        full_text = text
        if self._attachment_path:
            path = self._attachment_path
            fname = os.path.basename(path)
            ext = os.path.splitext(path)[1].lower()
            img_exts = {'.png', '.jpg', '.jpeg', '.gif', '.bmp'}
            text_exts = {'.txt', '.py', '.md', '.csv', '.json', '.xml', '.html', '.css', '.js'}
            if ext in img_exts:
                full_text = f"{text}\n\n[Изображение: {fname}]"
            elif ext in text_exts:
                try:
                    with open(path, "r", encoding="utf-8", errors="replace") as fh:
                        content = fh.read(10000)
                    full_text = f"{text}\n\n[Файл: {fname}]\n```\n{content}\n```"
                except Exception:
                    full_text = f"{text}\n\n[Файл: {fname} (не удалось прочитать)]"
            else:
                full_text = f"{text}\n\n[Файл: {fname}]"
            self._attachment_path = ""
            self._attach_btn.setText("📎")
        self._input_edit.clear()
        self._add_message_bubble(full_text, is_user=True)
        self._history.append({"role": "user", "content": full_text})
        if not self._send_btn.isEnabled():
            return
        self._send_btn.setEnabled(False)
        self._send_btn.setText("⏳ " + I18n._("ai.thinking"))
        QApplication.processEvents()
        QTimer.singleShot(50, lambda: self._process_ai(full_text))

    def _process_ai(self, text: str) -> None:
        try:
            local_noauth = any(x in self.engine.api_url.lower() for x in ["localhost", "127.0.0.1", "ollama"])
            if not self.engine.api_key and not local_noauth:
                self._add_message_bubble(I18n._("ai.no_key"), is_error=True)
                self._send_btn.setEnabled(True)
                self._send_btn.setText(I18n._("ai.send"))
                return

            is_agent = self.engine.mode == "agent"
            schema = self._get_schema_summary() if is_agent else ""

            response = self.engine.send_request(self._history[:-1],
                                                 text, schema)
            if response is None:
                self._add_message_bubble(I18n._("ai.no_key"), is_error=True)
            elif response.startswith("HTTP Error") or response.startswith("Connection Error"):
                self._add_message_bubble(response, is_error=True)
            elif response.startswith("Error:"):
                self._add_message_bubble(response, is_error=True)
            elif not response.strip():
                self._add_message_bubble(I18n._("ai.empty_response") if I18n._("ai.empty_response") != "ai.empty_response" else "Пустой ответ от ИИ", is_error=True)
            elif is_agent:
                self._handle_agent_response(response)
            else:
                self._add_message_bubble(response)
                self._history.append({"role": "assistant", "content": response})
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            self._add_message_bubble(f"Error: {str(e)}\n{tb[:200]}", is_error=True)
        finally:
            self._send_btn.setEnabled(True)
            self._send_btn.setText(I18n._("ai.send"))

    def _get_schema_summary(self) -> str:
        parts = []
        for table in ["employees", "violations", "custom_ledger"]:
            cols = self.db.get_columns_config(table)
            parts.append(f"{table}: {', '.join(c['name'] for c in cols)}")
        companies = self.db.get_companies()
        parts.append(f"companies: {len(companies)} registered")
        return "; ".join(parts)

    def _handle_agent_response(self, response: str) -> None:
        parsed = self.engine.parse_agent_response(response)
        thought = parsed.get("thought", "")
        action = parsed.get("action", "respond")
        params = parsed.get("params", {})

        if thought:
            self._add_message_bubble(f"🤔 {thought}")
            self._history.append({"role": "assistant", "content": f"[Thought] {thought}"})

        if action == "respond":
            msg = params.get("message", response)
            self._add_message_bubble(msg)
            self._history.append({"role": "assistant", "content": msg})
            return

        if action in ("add_record", "modify_record", "delete_record", "rename_column", "add_note"):
            confirm_text = f"⚠️ AI wants to: {action}\n{json.dumps(params, ensure_ascii=False, indent=2)}"
            reply = QMessageBox.question(self, I18n._("ai.confirm_action"),
                                         confirm_text,
                                         QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                result = self.engine.execute_action(action, params)
                self._add_message_bubble(f"✅ {result}")
                self._history.append({"role": "assistant", "content": result})
            else:
                self._add_message_bubble("⛔ " + I18n._("ai.action_cancelled"))
                self._history.append({"role": "assistant",
                                       "content": I18n._("ai.action_cancelled")})
        else:
            result = self.engine.execute_action(action, params)
            self._add_message_bubble(f"📊 {result}")
            self._history.append({"role": "assistant", "content": result})

    def eventFilter(self, obj: QObject, event: Any) -> bool:
        if obj == self._input_edit and event.type() == event.KeyPress:
            if (event.key() == Qt.Key_Return and
                    event.modifiers() != Qt.ShiftModifier):
                if self._send_btn.isEnabled():
                    self._send_message()
                return True
        return super().eventFilter(obj, event)


# ===========================================================================
# END OF PART 8 — BEGIN PART 9: Settings + Users + Main Entry Point
# ===========================================================================

# ---------------------------------------------------------------------------
# SECTION 9.1: Settings Dialog
# ---------------------------------------------------------------------------

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

        tabs.addTab(system, I18n._("common.system"))

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


# ---------------------------------------------------------------------------
# SECTION 9.2: Users Dialog
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# SECTION 9.3: Application Entry Point
# ---------------------------------------------------------------------------

import faulthandler
faulthandler.enable()

def global_exception_handler(exc_type, exc_value, exc_traceback):
    import traceback
    msg = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    try:
        from PyQt5.QtWidgets import QApplication, QMessageBox
        if QApplication.instance():
            QMessageBox.critical(None, "Ошибка",
                                 f"Необработанная ошибка:\n\n{msg}")
        else:
            print(msg, file=sys.stderr)
    except Exception:
        print(msg, file=sys.stderr)
    sys.exit(1)

sys.excepthook = global_exception_handler

class SafeApplication(QApplication):
    def notify(self, receiver, event):
        try:
            return super().notify(receiver, event)
        except Exception:
            import traceback
            traceback.print_exc()
            return False

def main() -> None:
    try:
        import ctypes
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "suot.enterprise.1.0")
        except Exception:
            pass  # non-critical

        app = SafeApplication(sys.argv)
        app.setApplicationName("СУОТ Enterprise")
        app.setApplicationVersion(AppConfig.APP_VERSION)
        app.setOrganizationName("SuotEnterprise")

        font = QFont("Segoe UI", 10)
        font.setStyleStrategy(QFont.PreferAntialias)
        app.setFont(font)

        app.setStyle("Fusion")

        # Initialize database + theme
        db = DatabaseManager()
        current_theme = db.get_setting("theme", AppConfig.DEFAULT_THEME)
        current_accent = db.get_setting("accent_color", AppConfig.DEFAULT_ACCENT)
        ThemeEngine.init(app)
        ThemeEngine.apply(current_theme, current_accent)

        # Startup backup (once per day)
        try:
            last_backup = db.get_setting("last_backup_date", "")
            today = datetime.now().strftime("%Y-%m-%d")
            if last_backup != today:
                db.create_backup()
                db.upsert_setting("last_backup_date", today)
        except Exception:
            pass  # non-critical

        # Start reminder engine
        _reminder_engine = ReminderEngine()

        # Login
        login = LoginDialog()
        if getattr(login, '_auto_logged_in', False):
            user = login.authenticated_user()
        else:
            if login.exec_() != QDialog.Accepted:
                sys.exit(0)
            user = login.authenticated_user()
        if not user:
            sys.exit(0)

        # Main window
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



class ViolationTypeDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.db = DatabaseManager()
        self.setWindowTitle(I18n._("viol.types"))
        self.setMinimumSize(550, 400)
        self.resize(600, 450)
        self._build_ui()
        self._load()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)
        heading = QLabel(I18n._("viol.types"))
        heading.setProperty("heading", True)
        layout.addWidget(heading)

        self._table = QTableWidget()
        self._table.setColumnCount(3)
        self._table.setHorizontalHeaderLabels([
            I18n._("viol.type_name"), I18n._("viol.risk_category"),
            I18n._("common.description")])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        layout.addWidget(wrap_table_with_glow(self._table, self))

        btn_layout = QHBoxLayout()
        add_btn = QPushButton(I18n._("common.add"))
        add_btn.setProperty("success", True)
        add_btn.clicked.connect(self._add)
        btn_layout.addWidget(add_btn)
        del_btn = QPushButton(I18n._("common.delete"))
        del_btn.setProperty("danger", True)
        del_btn.clicked.connect(self._delete)
        btn_layout.addWidget(del_btn)
        btn_layout.addStretch()
        close_btn = QPushButton(I18n._("common.close"))
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

    def _load(self) -> None:
        self._table.setRowCount(0)
        rows = self.db.fetch_all("SELECT id, name, risk_category, description FROM violation_types ORDER BY name")
        self._table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            self._table.setItem(i, 0, QTableWidgetItem(r["name"]))
            self._table.setItem(i, 1, QTableWidgetItem(r["risk_category"]))
            desc = QTableWidgetItem(r.get("description", ""))
            desc.setToolTip(r.get("description", ""))
            self._table.setItem(i, 2, desc)
        self._table.resizeColumnsToContents()

    def _add(self) -> None:
        name, ok = QInputDialog.getText(self, I18n._("viol.type_name"), I18n._("viol.type_name"))
        if not ok or not name:
            return
        risk, ok2 = QInputDialog.getItem(self, I18n._("viol.risk_category"), "",
                                          ["Низкая", "Средняя", "Высокая", "Критическая"], 1, False)
        if not ok2:
            return
        desc, ok3 = QInputDialog.getMultiLineText(self, I18n._("common.description"), I18n._("common.description"))
        if not ok3:
            desc = ""
        try:
            self.db.conn.execute("INSERT INTO violation_types (name, risk_category, description) VALUES (?,?,?)",
                                 (name.strip(), risk, desc.strip()))
            self.db.conn.commit()
            self._load()
            ToastNotification.notify(I18n._("common.success"), "success", 3000)
        except Exception:
            ToastNotification.notify(I18n._("error.generic"), "error", 5000)

    def _delete(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            return
        name = self._table.item(row, 0).text()
        reply = QMessageBox.question(self, I18n._("common.confirm"),
                                     f"{I18n._('common.delete')}: '{name}'?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.db.conn.execute("DELETE FROM violation_types WHERE name=?", (name,))
            self.db.conn.commit()
            self._load()
            ToastNotification.notify(I18n._("toast.delete_success"), "success", 3000)


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


# ---------------------------------------------------------------------------
# SECTION 10.2: Hotkey Manager
# ---------------------------------------------------------------------------

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


# ===========================================================================
# END OF PART 10
# ===========================================================================

# ---------------------------------------------------------------------------
# FineKinneyCalculator — Risk Analysis Dialog
# ---------------------------------------------------------------------------

class FineKinneyCalculator(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(I18n._("risk.title"))
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setMinimumSize(520, 420)
        self.resize(540, 450)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        form = QFormLayout(container)
        form.setSpacing(10)

        prob_items = I18n._("risk.prob_opts").split(";")
        self._prob_cb = QComboBox()
        self._prob_cb.setMinimumHeight(32)
        self._prob_cb.addItems(prob_items)
        form.addRow(I18n._("risk.probability") + ":", self._prob_cb)

        exp_items = I18n._("risk.exp_opts").split(";")
        self._exp_cb = QComboBox()
        self._exp_cb.setMinimumHeight(32)
        self._exp_cb.addItems(exp_items)
        form.addRow(I18n._("risk.exposure") + ":", self._exp_cb)

        cons_items = I18n._("risk.cons_opts").split(";")
        self._cons_cb = QComboBox()
        self._cons_cb.setMinimumHeight(32)
        self._cons_cb.addItems(cons_items)
        form.addRow(I18n._("risk.consequence") + ":", self._cons_cb)

        calc_btn = QPushButton(I18n._("risk.calculate"))
        calc_btn.setProperty("success", True)
        calc_btn.setMinimumHeight(36)
        calc_btn.clicked.connect(self._calculate)
        form.addRow(calc_btn)

        self._res_label = QLabel(f"<b>{I18n._('risk.index')}:</b> -")
        self._res_label.setStyleSheet("font-size: 16px;")
        form.addRow(self._res_label)

        self._desc_label = QLabel(f"<b>{I18n._('risk.classification')}:</b> -")
        self._desc_label.setWordWrap(True)
        form.addRow(self._desc_label)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton(I18n._("common.close"))
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        form.addRow(btn_row)

        scroll.setWidget(container)
        layout.addWidget(scroll)

    def _calculate(self) -> None:
        p = float(self._prob_cb.currentText().split(" —")[0].split("-")[0].strip())
        e = float(self._exp_cb.currentText().split(" —")[0].split("-")[0].strip())
        c = float(self._cons_cb.currentText().split(" —")[0].split("-")[0].strip())
        r = p * e * c
        self._res_label.setText(f"<b>{I18n._('risk.index')}:</b> {r:.1f}")

        if r < 20:
            text, color = I18n._("risk.low"), "#2ecc71"
        elif r < 70:
            text, color = I18n._("risk.moderate"), "#f1c40f"
        elif r < 200:
            text, color = I18n._("risk.substantial"), "#e67e22"
        elif r < 400:
            text, color = I18n._("risk.high"), "#e74c3c"
        else:
            text, color = I18n._("risk.critical"), "#8b0000"

        self._desc_label.setText(
            f"<b>{I18n._('risk.classification')}:</b> "
            f"<span style='color:{color};font-weight:bold;'>{text}</span>")


# ---------------------------------------------------------------------------
# TextbookManagerDialog — Autocomplete / Textbook Editor
# ---------------------------------------------------------------------------

class TextbookManagerDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.db = DatabaseManager()
        self.setWindowTitle(I18n._("textbook.title"))
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setMinimumSize(700, 500)
        self.resize(750, 550)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)

        heading = QLabel(I18n._("textbook.title"))
        heading.setProperty("heading", True)
        layout.addWidget(heading)

        hint = QLabel(I18n._("textbook.instruction"))
        hint.setWordWrap(True)
        hint.setStyleSheet("font-size: 12px;")
        layout.addWidget(hint)

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText(I18n._("common.search_hint"))
        self._search_edit.textChanged.connect(self._filter_rows)
        layout.addWidget(self._search_edit)

        self._table = QTableWidget()
        self._table.setColumnCount(2)
        self._table.setHorizontalHeaderLabels([
            I18n._("textbook.trigger"), I18n._("textbook.expanded")])
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch)
        self._table.setAlternatingRowColors(True)
        layout.addWidget(self._table, 1)

        btn_row = QHBoxLayout()
        add_btn = QPushButton(I18n._("common.add"))
        add_btn.clicked.connect(self._add_row)
        del_btn = QPushButton(I18n._("common.delete"))
        del_btn.clicked.connect(self._delete_row)
        save_btn = QPushButton(I18n._("common.save"))
        save_btn.setProperty("success", True)
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(del_btn)
        btn_row.addStretch()
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

        self._load_data()

        self._all_rows: List[Tuple[str, str]] = []

    def _filter_rows(self) -> None:
        query = self._search_edit.text().strip().lower()
        filtered = self._all_rows
        if query:
            filtered = [(s, t) for s, t in filtered
                        if query in s.lower() or query in t.lower()]
        self._table.setRowCount(len(filtered))
        for i, (short_code, full_text) in enumerate(filtered):
            self._table.setItem(i, 0, QTableWidgetItem(short_code))
            self._table.setItem(i, 1, QTableWidgetItem(full_text))
        self._table.resizeColumnsToContents()

    def _load_data(self) -> None:
        self._all_rows = self.db.fetch_all(
            "SELECT short_code, full_text FROM textbook ORDER BY short_code")
        self._filter_rows()

    def _add_row(self) -> None:
        r = self._table.rowCount()
        self._table.insertRow(r)
        self._table.setItem(r, 0, QTableWidgetItem(I18n._("textbook.new_trigger")))
        self._table.setItem(r, 1, QTableWidgetItem(I18n._("textbook.new_fulltext")))

    def _delete_row(self) -> None:
        r = self._table.currentRow()
        if r >= 0:
            self._table.removeRow(r)

    def _save(self) -> None:
        self.db.execute("DELETE FROM textbook")
        for i in range(self._table.rowCount()):
            short_item = self._table.item(i, 0)
            long_item = self._table.item(i, 1)
            if short_item and long_item and short_item.text().strip():
                self.db.execute(
                    "INSERT INTO textbook (short_code, full_text) VALUES (?, ?)",
                    (short_item.text().strip().lower(), long_item.text().strip()))
        ToastNotification.notify(I18n._("textbook.saved"), "success", 3000)
        self.accept()


# ---------------------------------------------------------------------------
# PrintDialog — Print any table data as HTML
# ---------------------------------------------------------------------------

class PrintDialog(QDialog):
    TABLES = {
        "employees": "tab.employees",
        "violations": "tab.violations",
        "custom_ledger": "tab.custom_ledger",
        "companies": "tab.companies",
    }

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.db = DatabaseManager()
        self.setWindowTitle(I18n._("common.print"))
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setMinimumSize(500, 300)
        self.resize(550, 350)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        heading = QLabel(I18n._("common.print"))
        heading.setProperty("heading", True)
        layout.addWidget(heading)

        form = QFormLayout()
        self._table_combo = QComboBox()
        self._table_combo.setMinimumHeight(32)
        for tbl, label_key in self.TABLES.items():
            self._table_combo.addItem(I18n._(label_key), tbl)
        form.addRow(I18n._("common.table") + ":", self._table_combo)

        self._template_combo = QComboBox()
        self._template_combo.setMinimumHeight(32)
        self._template_combo.addItem("— " + I18n._("print.without_template") + " —", 0)
        for t in self.db.get_all_print_templates():
            suffix = " 📄" if t["template_type"] == "order" else " 📊"
            self._template_combo.addItem(t["name"] + suffix, t["id"])
        form.addRow(I18n._("print.template") + ":", self._template_combo)

        self._all_cb = QCheckBox(I18n._("common.select_all"))
        self._all_cb.setChecked(True)
        form.addRow(self._all_cb)
        layout.addLayout(form)

        btn_row = QHBoxLayout()
        print_btn = QPushButton(I18n._("common.print"))
        print_btn.setMinimumHeight(36)
        print_btn.clicked.connect(self._do_print)
        btn_row.addWidget(print_btn)
        btn_row.addStretch()
        close_btn = QPushButton(I18n._("common.close"))
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _do_print(self) -> None:
        table = self._table_combo.currentData()
        label = self._table_combo.currentText()
        cols = self.db.get_columns_config(table)
        records = self.db.get_json_records(table)
        template_id = self._template_combo.currentData()

        rows_html = ""
        for rec in records:
            dj = rec.get("data_json", {})
            cells = "".join(
                f"<td>{str(dj.get(c['name'], '—'))}</td>" for c in cols)
            rows_html += f"<tr>{cells}</tr>"

        headers = "".join(f"<th>{c['name']}</th>" for c in cols)

        if template_id:
            templates = self.db.get_all_print_templates()
            tmpl = next((t for t in templates if t["id"] == template_id), None)
            if tmpl:
                html = PrintEngine.render_report(label, template_html=tmpl["html_content"])
            else:
                html = f"""<html><head><meta charset='utf-8'><style>body{{font-family:Arial,sans-serif;margin:30px;}}table{{width:100%;border-collapse:collapse;margin-top:16px;}}th,td{{border:1px solid #999;padding:8px;text-align:left;font-size:12px;}}</style></head><body><h2>{label}</h2><p>{I18n._('common.count')}: {len(records)}</p><table><thead><tr>{headers}</tr></thead><tbody>{rows_html}</tbody></table></body></html>"""
        else:
            html = f"""<html><head><meta charset='utf-8'>
            <style>
            body{{font-family:Arial,sans-serif;margin:30px;}}
            h2{{color:#1a365d;}}
            table{{width:100%;border-collapse:collapse;margin-top:16px;}}
            th,td{{border:1px solid #999;padding:8px;text-align:left;font-size:12px;}}
            th{{background:#313244;color:#cdd6f4;}}
            tr:nth-child(even){{background:#f5f5f7;}}
            </style></head><body>
            <h2>{label}</h2>
            <p>{I18n._('common.date')}: {datetime.now().strftime('%d.%m.%Y %H:%M')}</p>
            <p>{I18n._('common.count')}: {len(records)}</p>
            <table><thead><tr>{headers}</tr></thead>
            <tbody>{rows_html if rows_html else '<tr><td colspan="' + str(len(cols)) + '">' + I18n._("report.no_data") + '</td></tr>'}</tbody></table>
            </body></html>"""

        try:
            printer = QPrinter(QPrinter.HighResolution)
            dialog = QPrintDialog(printer, self)
            dialog.setWindowTitle(I18n._("common.print"))
            if dialog.exec_() != QDialog.Accepted:
                return
            browser = QTextBrowser()
            browser.setHtml(html)
            browser.print_(printer)
            ToastNotification.notify(I18n._("print.generated"), "success", 3000)
            self.accept()
        except Exception as ex:
            QMessageBox.critical(self, I18n._("common.error"), str(ex))


class MainWindow(QMainWindow):
    def __init__(self, user: Optional[Dict[str, Any]] = None) -> None:
        super().__init__()
        self.db = DatabaseManager()
        self._user = user or {}
        self._build_ui()
        self._setup_toolbar()
        self._load_settings()
        self._populate_dashboard()
        self._init_auto_save()
        self._hotkeys = HotkeyManager(self)

    def _btn_text(self, key: str, fallback: str) -> str:
        """Return custom button label from settings if available."""
        custom = self.db.get_setting(key, "")
        return custom if custom else fallback

    def closeEvent(self, event: Any) -> None:
        try:
            self._auto_save_timer.stop()
        except Exception:
            pass
        try:
            self._tab_widget.blockSignals(True)
        except Exception:
            pass
        event.accept()

    def _build_ui(self) -> None:
        self.setWindowTitle(I18n._("app.name"))
        self.setMinimumSize(1200, 750)
        self.resize(1400, 850)
        center = QApplication.primaryScreen().availableGeometry().center()
        self.move(center.x() - 700, center.y() - 425)

        self._tab_widget = QTabWidget()
        self._tab_widget.setDocumentMode(True)
        self._tab_widget.setMovable(True)
        self._tab_widget.setTabsClosable(False)
        self._tab_widget.tabBar().setContextMenuPolicy(Qt.CustomContextMenu)
        self._tab_widget.tabBar().customContextMenuRequested.connect(
            self._on_tab_context_menu)
        self.setCentralWidget(self._tab_widget)

        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status_label = QLabel()
        self._status.addPermanentWidget(self._status_label)

    def _setup_toolbar(self) -> None:
        tb = QToolBar()
        tb.setMovable(False)
        tb.setIconSize(QSize(14, 14))
        tb.setStyleSheet("QToolBar { spacing: 1px; padding: 2px 4px; }")
        self.addToolBar(tb)

        def tb_btn(icon: str, tip: str, slot) -> QToolButton:
            btn = QToolButton()
            btn.setText(icon)
            btn.setToolTip(tip)
            btn.clicked.connect(slot)
            btn.setStyleSheet("QToolButton { padding: 4px 6px; font-size: 13px; min-width: 22px; }")
            tb.addWidget(btn)
            return btn

        self._theme_btn = tb_btn("☀" if ThemeEngine._current_theme == "light" else "☾",
               I18n._("settings.theme"), self._toggle_theme)
        self._lang_btn = tb_btn("RU" if I18n.current() == "ru" else "EN",
               I18n._("settings.language"), self._toggle_lang)
        tb.addSeparator()
        user_name = self._user.get("username", "?")
        role = self._user.get("role", "")
        ubtn = tb_btn(f"👤{user_name}", f"{I18n._('user.role')}: {role}", lambda: None)
        ubtn.setEnabled(False)
        tb_btn("🚪", I18n._("login.logout"), self._on_logout)
        tb_btn("⚙", I18n._("common.settings"), self._open_settings)
        tb_btn("👥", I18n._("user.title"), self._open_users)
        tb.addSeparator()
        tb_btn("📥", I18n._("import.title"), self._open_import_dialog)
        tb_btn("📜", I18n._("audit.export_title"), self._export_audit_log)
        tb_btn("📝", I18n._("template.title"), self._open_print_templates)
        tb.addSeparator()
        tb_btn("📖", I18n._("common.notes"), self._open_global_notes)
        tb_btn("📚", I18n._("knowledge.title"), self._open_knowledge)
        tb_btn("✏️", I18n._("textbook.title"), self._open_textbook)
        tb_btn("📊", I18n._("analytics.title"), self._open_analytics_menu)
        tb_btn("📋", I18n._("report.global_title"), self._generate_global_report)
        tb_btn("⚠️", I18n._("risk.title"), self._open_risk_calc)
        tb.addSeparator()
        tb_btn("🤖", I18n._("ai.title"), self._open_ai_chat)
        tb_btn("🩺", I18n._("ai.diagnostics"), self._open_ai_diagnostics)
        tb.addSeparator()
        tb_btn("💾", I18n._("common.backup"), self._open_backup_dialog)
        tb_btn("🖨", I18n._("print.any_table"), self._open_print_dialog)
        tb_btn("❓", I18n._("help.title"), self._open_help)
        tb_btn("ℹ️", I18n._("common.about"), self._show_about)
        self._global_search = QLineEdit()
        self._global_search.setPlaceholderText(I18n._("common.global_search"))
        self._global_search.setClearButtonEnabled(True)
        self._global_search.setMinimumWidth(120)
        self._global_search.setMaximumWidth(160)
        self._global_search.returnPressed.connect(self._on_global_search)
        tb.addWidget(self._global_search)

    def _load_settings(self) -> None:
        self._tabs_data: Dict[str, Tuple[int, QWidget]] = {}
        self._tab_widget.clear()
        self.dashboard_tab = DashboardTab()

        uid = self._user.get("id", 0)

        # Create real widgets for each tab
        self._employees_tab = EmployeeTableWidget(user_id=uid)
        self._violations_tab = ViolationsTableWidget(user_id=uid)
        self._companies_tab = CompaniesTab()
        self._custom_ledger_tab = CustomLedgerTableWidget(user_id=uid)
        self._statistics_tab = StatisticsTab()
        self._audit_tab = AuditTab()

        # AI tab: embedded chat widget
        self._ai_tab = AIChatInlineWidget()

        # Reminders tab: expiring items
        self._reminders_tab = ExpiringRemindersTab()

        tab_defs = [
            ("tab.dashboard", self.dashboard_tab),
            ("tab.employees", self._employees_tab),
            ("tab.violations", self._violations_tab),
            ("tab.companies", self._companies_tab),
            ("tab.custom_ledger", self._custom_ledger_tab),
            ("tab.statistics", self._statistics_tab),
            ("tab.audit", self._audit_tab),
            ("tab.reminders", self._reminders_tab),
            ("tab.ai", self._ai_tab),
        ]
        for key, widget in tab_defs:
            label = self.db.get_setting(f"tab_{key.split('.')[1]}", I18n._(key))
            idx = self._tab_widget.addTab(widget, label)
            self._tabs_data[key] = (idx, widget)

        self._tab_widget.tabBar().installEventFilter(self)
        self._tab_widget.currentChanged.connect(self._on_tab_changed)
        self._update_tab_badges()
        self._update_status()

        # Tab bar style with eliding for long text
        self._tab_widget.tabBar().setExpanding(True)
        self._tab_widget.tabBar().setUsesScrollButtons(True)
        try:
            self._tab_widget.tabBar().setElideMode(Qt.ElideRight)
        except Exception:
            pass

        # Startup reminder popup (disabled — was intrusive during AI processing)

    def _show_startup_reminders(self) -> None:
        try:
            tab = getattr(self, "_reminders_tab", None)
            if tab and tab.has_expiring():
                dlg = ReminderFloatingDialog(self)
                dlg.setWindowOpacity(0.0)
                dlg.show()
                anim = QPropertyAnimation(dlg, b"windowOpacity")
                anim.setDuration(400)
                anim.setStartValue(0.0)
                anim.setEndValue(1.0)
                anim.setEasingCurve(QEasingCurve.OutCubic)
                anim.start()
        except Exception:
            pass

    def _populate_dashboard(self) -> None:
        self.dashboard_tab._refresh()

    def _init_auto_save(self) -> None:
        try:
            interval = int(self.db.get_setting("auto_save_interval", "60"))
        except Exception:
            interval = 60
        self._auto_save_timer = QTimer(self)
        self._auto_save_timer.timeout.connect(lambda: self.db.create_backup())
        self._auto_save_timer.start(max(10, interval) * 1000)

        # Periodic reminder refresh (every 2 minutes)
        self._reminder_refresh_timer = QTimer(self)
        self._reminder_refresh_timer.timeout.connect(self._refresh_reminders)
        self._reminder_refresh_timer.start(120000)

    def _refresh_reminders(self) -> None:
        try:
            if hasattr(self, '_reminders_tab'):
                self._reminders_tab._load_data()
                self._update_tab_badges()
        except Exception:
            pass

    def _refresh_current_tab(self) -> None:
        idx = self._tab_widget.currentIndex()
        if not hasattr(self, '_tabs_data'):
            return
        for key, (i, widget) in self._tabs_data.items():
            if i == idx:
                name = key.split(".")[1]
                if name == "dashboard":
                    self.dashboard_tab._refresh()
                elif hasattr(self, f"_{name}_tab"):
                    t = getattr(self, f"_{name}_tab")
                    if hasattr(t, "_load_data"):
                        t._load_data()
                    elif hasattr(t, "_refresh"):
                        t._refresh()
                break

    def _update_tab_badges(self) -> None:
        if not hasattr(self, '_tabs_data'):
            return
        try:
            emp_count = len(self.db.get_json_records("employees"))
            viol_count = len(self.db.get_json_records("violations"))
            remind_count = self._reminders_tab.get_expiring_count() if hasattr(self, '_reminders_tab') else 0
        except Exception:
            return
        for key, (idx, widget) in self._tabs_data.items():
            label = self.db.get_setting(f"tab_{key.split('.')[1]}", I18n._(key))
            if key == "tab.employees" and emp_count:
                self._tab_widget.setTabText(idx, f"{label} ({emp_count})")
            elif key == "tab.violations" and viol_count:
                self._tab_widget.setTabText(idx, f"{label} ({viol_count})")
            elif key == "tab.reminders" and remind_count:
                self._tab_widget.setTabText(idx, f"{label} ({remind_count})")
            else:
                self._tab_widget.setTabText(idx, label)

    def _tab_name_by_index(self) -> Dict[int, str]:
        if not hasattr(self, '_tabs_data'):
            return {}
        return {idx: key.split(".")[1] for key, (idx, _) in self._tabs_data.items()}

    def open_reminder_target(self, item: Dict[str, Any]) -> None:
        table = str(item.get("_table", "")).strip()
        record_id = item.get("_record_id")
        if table == "employees" and hasattr(self, "_employees_tab"):
            self._tab_widget.setCurrentIndex(self._tabs_data["tab.employees"][0])
            self._employees_tab.focus_record(record_id)
        elif table == "violations" and hasattr(self, "_violations_tab"):
            self._tab_widget.setCurrentIndex(self._tabs_data["tab.violations"][0])
            self._violations_tab.focus_record(record_id)
        elif table == "custom_ledger" and hasattr(self, "_custom_ledger_tab"):
            self._tab_widget.setCurrentIndex(self._tabs_data["tab.custom_ledger"][0])
            self._custom_ledger_tab.focus_record(record_id)
        elif table == "reminders":
            RemindersDialog(self).exec_()

    def _open_global_search(self) -> None:
        GlobalSearchDialog(self).exec_()

    def _on_global_search(self) -> None:
        text = self._global_search.text().strip()
        if not text:
            return
        results = []
        db = DatabaseManager()
        text_lower = text.lower()
        seen = set()
        for table, label_key in [("employees", "tab.employees"),
                                  ("violations", "tab.violations"),
                                  ("custom_ledger", "tab.custom_ledger"),
                                  ("companies", "company.title")]:
            for rec in db.get_json_records(table):
                dj = rec.get("data_json", {})
                rid = rec.get("id", 0)
                for k, v in dj.items():
                    if text_lower in str(v).lower():
                        key = (table, rid)
                        if key not in seen:
                            seen.add(key)
                            results.append((table, label_key, rid, k, str(v)[:80]))
                            break
        for note in db.get_notes():
            if text_lower in note.get("text", "").lower():
                results.append(("notes", "common.notes", note.get("id", 0),
                                I18n._("common.notes"), note.get("text", "")[:80]))
        results.sort(key=lambda r: r[4])
        self._show_search_results(text, results)

    def _show_search_results(self, query: str, results: list) -> None:
        if not results:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(f"{I18n._('common.search')}: {query}")
        dlg.setMinimumSize(500, 400)
        dlg.resize(600, 500)
        lay = QVBoxLayout(dlg)
        tree = QTreeWidget()
        tree.setHeaderLabels([I18n._("common.table"), I18n._("common.field"), I18n._("common.value")])
        tree.setRootIsDecorated(False)
        tree.setAlternatingRowColors(True)
        tree.itemDoubleClicked.connect(lambda item, _: self._navigate_to_record(item))
        for table, label_key, rid, field, value in results:
            QTreeWidgetItem(tree, [I18n._(label_key), field, value]).setData(
                0, Qt.UserRole, (table, rid))
        lay.addWidget(tree)
        close_btn = QPushButton(I18n._("common.close"))
        close_btn.clicked.connect(dlg.accept)
        lay.addWidget(close_btn)
        dlg.exec_()

    def _navigate_to_record(self, item: QTreeWidgetItem) -> None:
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        table, rid = data
        tab_key = {"employees": "tab.employees", "violations": "tab.violations",
                   "custom_ledger": "tab.custom_ledger", "notes": "tab.notes",
                   "companies": "tab.companies"}.get(table)
        if tab_key and tab_key in self._tabs_data:
            idx, widget = self._tabs_data[tab_key]
            self._tab_widget.setCurrentIndex(idx)
            if hasattr(widget, 'focus_record'):
                widget.focus_record(rid)
            elif hasattr(widget, 'focus_note'):
                widget.focus_note(rid)

    def _open_ai_chat(self) -> None:
        db = DatabaseManager()
        key = db.get_ai_setting("api_key", "")
        if not key:
            QMessageBox.information(self, I18n._("ai.title"),
                                    I18n._("ai.no_key"))
        dlg = AIChatDialog(self)
        dlg.exec_()
        self._refresh_current_tab()

    def _open_global_notes(self) -> None:
        NotesDialog(entity_type="global", entity_id=0,
                    entity_name=I18n._("tab.dashboard"), parent=self).exec_()

    def _open_import_dialog(self) -> None:
        dlg = ImportDialog("", self)
        if dlg.exec_() == QDialog.Accepted:
            for tab_name in ("employees", "violations", "custom_ledger"):
                widget = getattr(self, f"_{tab_name}_tab", None)
                if widget and hasattr(widget, "_load_data"):
                    widget._load_data()

    def _open_print_templates(self) -> None:
        dlg = PrintTemplateEditor(self)
        dlg.exec_()

    def _open_help(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        dlg.setWindowTitle(I18n._("help.title"))
        dlg.setMinimumSize(700, 600)
        dlg.resize(750, 650)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        a = ThemeEngine._current_accent
        at = ThemeEngine._contrast_accent(a)
        is_dark = ThemeEngine._current_theme == "dark"
        bg = "#1C1C1E" if is_dark else "#FFFFFF"
        text = "#F5F5F7" if is_dark else "#1C1C1E"
        sec_text = "#98989D" if is_dark else "#6C6C70"
        card_bg = "rgba(44,44,46,0.85)" if is_dark else "rgba(255,255,255,0.7)"
        card_border = "rgba(255,255,255,0.08)" if is_dark else "rgba(0,0,0,0.04)"
        div_border = "#3A3A3C" if is_dark else "#E5E5EA"
        browser.setHtml(f"""
        <style>
            body {{ font-family: -apple-system, 'Segoe UI', Arial, sans-serif; font-size: 13px; line-height: 1.7; color: {text}; margin: 0; padding: 0; }}
            h2 {{ font-size: 24px; font-weight: 700; color: {text}; margin: 0 0 4px 0; letter-spacing: -0.5px; }}
            .subtitle {{ color: {sec_text}; font-size: 13px; margin: 0 0 16px 0; }}
            h3 {{ font-size: 15px; font-weight: 600; color: {text}; margin: 20px 0 8px 0; padding: 0 0 6px 0; border-bottom: 1.5px solid {div_border}; }}
            .section {{ background: {card_bg}; border-radius: 10px; padding: 12px 16px; margin: 8px 0; border: 1px solid {card_border}; }}
            .section p {{ margin: 4px 0; color: {text}; }}
            table.shortcuts {{ border-collapse: collapse; width: 100%; }}
            table.shortcuts td {{ padding: 5px 10px; font-size: 13px; border-bottom: 1px solid {div_border}; }}
            table.shortcuts td:first-child {{ color: {at}; font-weight: 600; white-space: nowrap; width: 1%; }}
            table.shortcuts td:last-child {{ color: {text}; }}
            ul {{ margin: 4px 0; padding-left: 20px; }}
            li {{ margin: 3px 0; color: {text}; line-height: 1.6; }}
            .tag {{ display: inline-block; background: {a}22; color: {at}; padding: 1px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }}
        </style>
        <h2>{I18n._('app.name')}</h2>
        <p class="subtitle">{I18n._('help.version')} {AppConfig.APP_VERSION} &middot; {I18n._('app.copyright')}</p>

        <div class="section">
        <h3>{I18n._('help.shortcuts')}</h3>
        <table class="shortcuts">
        <tr><td><b>Ctrl+&uarr;/&darr;</b></td><td>{I18n._('help.nav_table')}</td></tr>
        <tr><td><b>Ctrl+F</b></td><td>{I18n._('help.search')}</td></tr>
        <tr><td><b>Ctrl+N</b></td><td>{I18n._('help.add_record')}</td></tr>
        <tr><td><b>Ctrl+E</b></td><td>{I18n._('help.export')}</td></tr>
        <tr><td><b>Ctrl+P</b></td><td>{I18n._('help.print')}</td></tr>
        <tr><td><b>Ctrl+S</b></td><td>{I18n._('help.save')} / backup</td></tr>
        <tr><td><b>Delete</b></td><td>{I18n._('help.delete')}</td></tr>
        <tr><td><b>Alt+1..9</b></td><td>{I18n._('help.tabs')}</td></tr>
        <tr><td><b>F5</b></td><td>{I18n._('common.refresh')}</td></tr>
        <tr><td><b>{I18n._('help.click_column')}</b></td><td>{I18n._('help.sort')}</td></tr>
        <tr><td><b>{I18n._('help.right_click_column')}</b></td><td>{I18n._('help.column_menu')}</td></tr>
        <tr><td><b>{I18n._('help.right_click_row')}</b></td><td>{I18n._('help.row_menu')}</td></tr>
        </table>
        </div>

        <div class="section">
        <h3>{I18n._('help.toolbar')}</h3>
        <p>{I18n._('help.toolbar_desc')}</p>
        </div>

        <div class="section">
        <h3>{I18n._('help.tabs')}</h3>
        <p>{I18n._('help.tabs_desc')}</p>
        </div>

        <div class="section">
        <h3>{I18n._('help.tables')}</h3>
        <p>{I18n._('help.tables_desc')}</p>
        </div>

        <div class="section">
        <h3>{I18n._('help.dashboard')}</h3>
        <p>{I18n._('help.dashboard_desc')}</p>
        </div>

        <div class="section">
        <h3>{I18n._('common.notes')}</h3>
        <p>{I18n._('help.notes_desc')}</p>
        </div>

        <div class="section">
        <h3>{I18n._('help.photos')}</h3>
        <p>{I18n._('help.photos_desc')}</p>
        </div>

        <div class="section">
        <h3>{I18n._('import.title')} / {I18n._('export.title')}</h3>
        <p><b>{I18n._('import.title')}:</b> {I18n._('help.import_desc')}</p>
        <p><b>{I18n._('export.title')}:</b> {I18n._('help.export_desc')}</p>
        </div>

        <div class="section">
        <h3>{I18n._('help.print_templates')}</h3>
        <p>{I18n._('help.print_templates_desc')}</p>
        </div>

        <div class="section">
        <h3>{I18n._('ai.title')}</h3>
        <p>{I18n._('help.ai_desc')}</p>
        </div>

        <div class="section">
        <h3>{I18n._('analytics.title')}</h3>
        <p>{I18n._('help.analytics_desc')}</p>
        </div>

        <div class="section">
        <h3>{I18n._('reminder.all')}</h3>
        <p>{I18n._('help.reminders_desc')}</p>
        </div>

        <div class="section">
        <h3>{I18n._('help.reports')} &amp; {I18n._('common.backup')}</h3>
        <p><b>{I18n._('help.reports')}:</b> {I18n._('help.reports_desc')}</p>
        <p><b>{I18n._('common.backup')}:</b> {I18n._('help.backup_desc')}</p>
        </div>

        <div class="section">
        <h3>{I18n._('help.security')}</h3>
        <p>{I18n._('help.security_desc')}</p>
        </div>

        <div class="section">
        <h3>{I18n._('common.settings')}</h3>
        <p>{I18n._('help.settings_desc')}</p>
        </div>

        <div class="section">
        <h3>{I18n._('textbook.title')}</h3>
        <p>{I18n._('help.textbook_desc')}</p>
        </div>

        <div class="section">
        <h3>{I18n._('risk.title')}</h3>
        <p>{I18n._('help.risk_calc_desc')}</p>
        </div>

        <div class="section">
        <h3>{I18n._('help.column_customization')}</h3>
        <p>{I18n._('help.column_customization_desc')}</p>
        </div>

        <div class="section">
        <h3>{I18n._('help.color_indicators')}</h3>
        <p>{I18n._('help.color_indicators_desc')}</p>
        </div>

        <div class="section">
        <h3>{I18n._('help.global_search')}</h3>
        <p>{I18n._('help.global_search_desc')}</p>
        </div>

        <div class="section">
        <h3>{I18n._('help.duplicate_merge')}</h3>
        <p>{I18n._('help.duplicate_merge_desc')}</p>
        </div>

        <div class="section">
        <h3>{I18n._('help.tips')}</h3>
        <pre style="font-family: -apple-system, 'Segoe UI', Arial, sans-serif; font-size: 13px; color: {text}; margin: 0; line-height: 1.7;">{I18n._('help.tips_list')}</pre>
        </div>
        """)
        layout.addWidget(browser)

        close_btn = QPushButton(I18n._("common.ok"))
        close_btn.clicked.connect(dlg.accept)
        close_btn.setFixedWidth(100)
        layout.addWidget(close_btn, 0, Qt.AlignCenter)
        fade_in_widget(dlg, 250)
        dlg.exec_()

    def _open_settings(self) -> None:
        SettingsDialog(self).exec_()

    def _open_users(self) -> None:
        UsersDialog(self).exec_()

    def _on_tab_changed(self, index: int) -> None:
        self._update_status()
        try:
            self._refresh_current_tab()
        except Exception:
            pass

    def _update_status(self) -> None:
        idx = self._tab_widget.currentIndex()
        if idx >= 0:
            tab_text = self._tab_widget.tabText(idx)
            user_name = self._user.get("username", "?")
            self._status_label.setText(
                f"👤 {user_name}  |  📋 {tab_text}")

    # -----------------------------------------------------------------------
    # Tab Renaming (double-click)
    # -----------------------------------------------------------------------

    def eventFilter(self, obj: QObject, event: Any) -> bool:
        if (obj == self._tab_widget.tabBar() and
                event.type() == event.MouseButtonDblClick):
            idx = self._tab_widget.tabBar().tabAt(event.pos())
            if idx >= 0:
                self._rename_tab(idx)
            return True
        return super().eventFilter(obj, event)

    def _rename_tab(self, index: int) -> None:
        old_name = self._tab_widget.tabText(index)
        new_name, ok = QInputDialog.getText(
            self, I18n._("common.rename"), "",
            text=old_name)
        if ok and new_name and new_name != old_name:
            self._tab_widget.setTabText(index, new_name)
            tab_key = self._get_tab_key(index)
            if tab_key:
                self.db.upsert_setting(f"tab_{tab_key}", new_name)
                self.db.log_event(f"Tab renamed: {old_name} -> {new_name}", "INFO")
                self._update_status()

    def _get_tab_key(self, index: int) -> Optional[str]:
        mapping = [
            "dashboard", "employees", "violations", "companies",
            "custom_ledger", "statistics", "audit", "reminders", "ai",
        ]
        return mapping[index] if 0 <= index < len(mapping) else None

    def _on_tab_context_menu(self, pos: QPoint) -> None:
        idx = self._tab_widget.tabBar().tabAt(pos)
        if idx < 0:
            return
        menu = QMenu(self)
        rename_action = menu.addAction(I18n._("column.rename"))
        action = menu.exec_(self._tab_widget.tabBar().mapToGlobal(pos))
        if action == rename_action:
            self._rename_tab(idx)

    # -----------------------------------------------------------------------
    # Theme / Language Toggle
    # -----------------------------------------------------------------------

    def _toggle_theme(self) -> None:
        new_theme = "dark" if ThemeEngine._current_theme == "light" else "light"
        self.db.upsert_setting("theme", new_theme)
        self._restart_app()

    def _restart_app(self) -> None:
        try:
            import subprocess, os
            script = getattr(sys, '_MEIPASS', __file__)
            exe = sys.executable if not getattr(sys, 'frozen', False) else script
            subprocess.Popen([exe, script] if not getattr(sys, 'frozen', False) else [script])
        except Exception:
            try:
                from PyQt5.QtCore import QProcess
                QProcess.startDetached(sys.executable, [__file__])
            except Exception:
                pass
        self.close()
        QApplication.quit()

    def _toggle_lang(self) -> None:
        new_lang = "en" if I18n.current() == "ru" else "ru"
        I18n.set_language(new_lang)
        self.db.upsert_setting("app_language", new_lang)
        default_text = "RU" if new_lang == "ru" else "EN"
        self._lang_btn.setText(default_text)
        self._retranslate_ui()
        ToastNotification.notify(
            I18n._("settings.saved"), "success", 3000)

    def _retranslate_ui(self) -> None:
        self.setWindowTitle(I18n._("app.name"))
        for i in range(self._tab_widget.count()):
            key = self._get_tab_key(i)
            if key:
                saved = self.db.get_setting(f"tab_{key}", "")
                self._tab_widget.setTabText(
                    i, saved if saved else I18n._(f"tab.{key}"))
        # Update toolbar button tooltips with current language
        def tooltip(key: str, fallback: str) -> str:
            return self.db.get_setting(f"tip_{key}", fallback)
        self._theme_btn.setToolTip(tooltip("theme", I18n._("settings.theme")))
        self._lang_btn.setToolTip(tooltip("lang", I18n._("settings.language")))
        self._update_status()

    # -----------------------------------------------------------------------
    # Block 4 ported utilities (from 9.5.py reference)
    # -----------------------------------------------------------------------

    def _open_textbook(self) -> None:
        TextbookManagerDialog(self).exec_()

    def _open_risk_calc(self) -> None:
        FineKinneyCalculator(self).exec_()

    def _open_print_dialog(self) -> None:
        dlg = PrintDialog(self)
        dlg.exec_()

    def _open_analytics_menu(self) -> None:
        menu = QMenu(self)
        cat_action = menu.addAction(I18n._("analytics.category"))
        contr_action = menu.addAction(I18n._("analytics.contractor"))
        action = menu.exec_(QCursor.pos())
        if action == cat_action:
            self._global_category_analytics()
        elif action == contr_action:
            self._global_contractor_analytics()

    def _open_backup_dialog(self) -> None:
        self._global_restore_from_backup()

    def _open_knowledge(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        dlg.setWindowTitle(I18n._("knowledge.title"))
        dlg.setMinimumSize(600, 420)
        lay = QVBoxLayout(dlg)
        editor = QTextEdit()
        kf = os.path.join(RUNTIME_PATHS.app_dir, AppConfig.DATA_DIR, "knowledge.txt")
        if os.path.exists(kf):
            try:
                with open(kf, "r", encoding="utf-8") as f:
                    editor.setText(f.read())
            except Exception:
                pass
        lay.addWidget(editor)
        save_btn = QPushButton(I18n._("knowledge.save"))
        def _save_knowledge():
            try:
                with open(kf, "w", encoding="utf-8") as f:
                    f.write(editor.toPlainText())
                dlg.accept()
            except Exception as ex:
                QMessageBox.critical(self, I18n._("common.error"), str(ex))
        save_btn.clicked.connect(_save_knowledge)
        lay.addWidget(save_btn)
        dlg.exec_()

    def _export_audit_log(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, I18n._("audit.export_title"),
            f"suot_audit_{datetime.now().strftime('%Y%m%d')}.log",
            "Log Files (*.log)")
        if not path:
            return
        try:
            rows = self.db.fetch_all(
                "SELECT timestamp, event FROM audit_log ORDER BY id ASC")
            lines = [f"[{r['timestamp']}] {r['event']}" for r in rows]
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            ToastNotification.notify(
                I18n._("audit.export_success"), "success", 3000)
        except Exception as ex:
            QMessageBox.critical(self, I18n._("common.error"), str(ex))

        except Exception as ex:
            QMessageBox.critical(self, I18n._("common.error"), str(ex))


    def _open_ai_diagnostics(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        dlg.setWindowTitle(I18n._("ai.diagnostics"))
        dlg.setMinimumSize(650, 500)
        lay = QVBoxLayout(dlg)
        
        heading = QLabel(I18n._("ai.diagnostics"))
        heading.setProperty("heading", True)
        lay.addWidget(heading)
        
        config_frame = QGroupBox(I18n._("ai.current_config"))
        config_lay = QFormLayout(config_frame)
        
        db = DatabaseManager()
        provider = db.get_ai_setting("provider", "openai")
        api_url = db.get_ai_setting("api_url", "")
        model = db.get_ai_setting("model", "")
        mode = db.get_ai_setting("mode", "chat")
        temperature = db.get_ai_setting("temperature", "0.7")
        
        config_lay.addRow(I18n._("ai.provider_label") + ":", QLabel(provider))
        config_lay.addRow(I18n._("ai.url_label") + ":", QLabel(api_url or "—"))
        config_lay.addRow(I18n._("ai.model_label") + ":", QLabel(model or "—"))
        config_lay.addRow(I18n._("ai.mode_label") + ":", QLabel(mode))
        config_lay.addRow(I18n._("ai.temp_label") + ":", QLabel(str(temperature)))
        
        lay.addWidget(config_frame)
        
        test_btn = QPushButton(I18n._("ai.test_connection"))
        test_btn.setProperty("success", True)
        result_label = QLabel()
        result_label.setWordWrap(True)
        
        def run_test():
            test_btn.setEnabled(False)
            test_btn.setText(I18n._("common.loading"))
            QApplication.processEvents()
            try:
                engine = AIEngine()
                test_result = engine.send_request([], "Test connection", "")
                if test_result and not test_result.startswith("Error:") and not test_result.startswith("HTTP Error"):
                    result_label.setText(f"<span style='color: #27AE60;'>{I18n._('ai.connection_ok')}</span>")
                    result_label.setToolTip(test_result[:500])
                else:
                    result_label.setText(f"<span style='color: #E74C3C;'>{I18n._('ai.connection_failed').format(error=test_result or 'Unknown')}</span>")
                    result_label.setToolTip(test_result or "")
            except Exception as ex:
                result_label.setText(f"<span style='color: #E74C3C;'>{I18n._('ai.connection_failed').format(error=str(ex))}</span>")
                result_label.setToolTip(str(ex))
            finally:
                test_btn.setEnabled(True)
                test_btn.setText(I18n._("ai.test_connection"))
        
        test_btn.clicked.connect(run_test)
        lay.addWidget(test_btn)
        lay.addWidget(result_label)
        
        close_btn = QPushButton(I18n._("common.close"))
        close_btn.clicked.connect(dlg.accept)
        lay.addWidget(close_btn)
        dlg.exec_()

    def _generate_global_report(self) -> None:
        html_path = os.path.abspath(
            os.path.join(AppConfig.DATA_DIR, "global_report.html"))
        word_path = os.path.abspath(
            os.path.join(AppConfig.DATA_DIR, "global_report.doc"))
        stats = self.db.get_statistics()
        status_col = "Статус"
        try:
            records = self.db.get_json_records("violations",
                                               user_id=self._user.get("id", 0))
        except Exception:
            records = []
        active = []
        for rec in records:
            dj = rec.get("data_json", {})
            if dj.get(status_col) in ("Активно", "Active", "Просрочено", "Expired"):
                active.append(dj)

        try:
            emp_records = self.db.get_json_records("employees",
                                                   user_id=self._user.get("id", 0))
        except Exception:
            emp_records = []
        active_emp = sum(1 for r in emp_records
                         if r.get("data_json", {}).get(status_col) in ("Активен", "Active"))

        li = "".join(
            f"<li><b>{v.get('Фирма', 'Контрагент')}:</b> "
            f"{v.get('Описание', 'Замечание по ТБ')}</li>"
            for v in active)
        now_str = datetime.now().strftime('%d.%m.%Y %H:%M')
        html = f"""<html><head><meta charset='utf-8'>
        <style>body{{font-family:Arial;margin:40px;background:#fafafa;}}
        .c{{background:#fff;padding:30px;border-radius:8px;
        box-shadow:0 2px 5px rgba(0,0,0,0.1);}}
        table{{width:100%;border-collapse:collapse;margin:16px 0;}}
        th,td{{border:1px solid #dee2e6;padding:8px 12px;text-align:left;}}
        th{{background:#f8f9fa;}}</style></head>
        <body><div class="c">
        <h2>{I18n._("report.global_title")}</h2>
        <p>{I18n._("common.date")}: {now_str}</p>
        <h3>📊 {I18n._("analytics.title")}</h3>
        <table>
        <tr><th>{I18n._("tab.employees")}</th><td>{stats['employees_total']}</td></tr>
        <tr><th>{I18n._("tab.violations")}</th><td>{stats['violations_total']}</td></tr>
        <tr><th>{I18n._("report.active_employees")}</th><td>{active_emp}</td></tr>
        <tr><th>{I18n._("report.active_violations")}</th><td>{len(active)}</td></tr>
        <tr><th>{I18n._("analytics.total_fines")}</th><td>{stats['fines_total']:,.0f} RUB</td></tr>
        </table>
        <h3>{I18n._("report.active_violations")} ({len(active)}):</h3>
        <ul>{li if li else f"<li>{I18n._('report.none_active')}</li>"}</ul>
        <hr><button onclick="window.print()">{I18n._("common.print")}</button>
        </div></body></html>"""
        try:
            os.makedirs(AppConfig.DATA_DIR, exist_ok=True)
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html)
            # Also save as .doc (Word-compatible HTML)
            with open(word_path, "w", encoding="utf-8") as f:
                f.write(html)
            reply = QMessageBox.question(
                self, I18n._("report.global_title"),
                I18n._("report.open_html") + f"\n\n{I18n._('report.word_saved')}",
                QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                webbrowser.open(f"file:///{html_path}")
            ToastNotification.notify(
                I18n._("report.generated_html"), "success", 3000)
        except Exception as ex:
            QMessageBox.critical(self, I18n._("common.error"), str(ex))

    def _global_restore_from_backup(self) -> None:
        bdir = RUNTIME_PATHS.backup_dir
        if not os.path.isdir(bdir):
            QMessageBox.information(self, I18n._("common.backup"),
                                    I18n._("backup.none"))
            return
        files = sorted(
            [f for f in os.listdir(bdir) if f.endswith(".zip")], reverse=True)
        if not files:
            QMessageBox.information(self, I18n._("common.backup"),
                                    I18n._("backup.none"))
            return
        display_names = [f.replace("suot_backup_", "").replace(".zip", "")
                         for f in files]
        chosen_display, ok = QInputDialog.getItem(
            self, I18n._("common.restore"), I18n._("backup.list"),
            display_names, 0, False)
        if ok and chosen_display:
            idx = display_names.index(chosen_display)
            chosen_file = files[idx]
            reply = QMessageBox.question(
                self, I18n._("common.confirm"),
                I18n._("backup.restore_confirm").format(
                    date=chosen_display.replace("_", " ")),
                QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                try:
                    zip_path = os.path.join(bdir, chosen_file)
                    self.db.conn.close()
                    import zipfile
                    tmp = os.path.join(tempfile.gettempdir(), "suot_restore_tmp.db")
                    with zipfile.ZipFile(zip_path, "r") as zf:
                        zf.extractall(tempfile.gettempdir())
                    db_file_in_zip = "suot_platform.db"
                    extracted = os.path.join(tempfile.gettempdir(), db_file_in_zip)
                    if os.path.exists(extracted):
                        shutil.copy2(extracted, self.db.database_path)
                    self.db = DatabaseManager()
                    self.db.log_event(
                        f"System restored from backup: {chosen_display}", "INFO")
                    ToastNotification.notify(
                        I18n._("backup.restored"), "success", 3000)
                    self._restart_app()
                except Exception as ex:
                    QMessageBox.critical(
                        self, I18n._("common.error"), str(ex))
                except Exception as ex:
                    QMessageBox.critical(
                        self, I18n._("common.error"), str(ex))

    def _global_contractor_analytics(self) -> None:
        try:
            records = self.db.get_json_records("violations")
        except Exception:
            records = []
        org_col = "Фирма"
        status_col = "Статус"
        fine_col = "Штраф"
        stats: Dict[str, Dict[str, Any]] = {}
        for rec in records:
            dj = rec.get("data_json", {})
            org = str(dj.get(org_col, I18n._("common.no_selection")))
            st = str(dj.get(status_col, "Активно"))
            fv = 0.0
            try:
                raw = str(dj.get(fine_col, "0"))
                cleaned = "".join(x for x in raw if x.isdigit() or x == ".")
                if cleaned:
                    fv = float(cleaned)
            except Exception:
                pass
            stats.setdefault(org, {"total": 0, "active": 0, "fines": 0.0})
            stats[org]["total"] += 1
            if st in ("Активно", "Active", "Просрочено", "Expired"):
                stats[org]["active"] += 1
            stats[org]["fines"] += fv
        dlg = QDialog(self)
        dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        dlg.setWindowTitle(I18n._("analytics.contractor"))
        dlg.setMinimumSize(700, 450)
        lay = QVBoxLayout(dlg)
        t = QTableWidget()
        t.setColumnCount(4)
        t.setHorizontalHeaderLabels([
            I18n._("company.name"), I18n._("analytics.total"),
            I18n._("analytics.active"), I18n._("analytics.fines_sum")])
        t.setRowCount(len(stats))
        for r, (org, info) in enumerate(sorted(stats.items())):
            t.setItem(r, 0, QTableWidgetItem(org))
            t.setItem(r, 1, QTableWidgetItem(str(info["total"])))
            t.setItem(r, 2, QTableWidgetItem(str(info["active"])))
            t.setItem(r, 3, QTableWidgetItem(
                f"{info['fines']:,.2f} {I18n._('common.currency')}"))
        t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        t.verticalHeader().setVisible(False)
        lay.addWidget(t)
        close_btn = QPushButton(I18n._("common.close"))
        close_btn.clicked.connect(dlg.accept)
        lay.addWidget(close_btn, 0, Qt.AlignCenter)
        dlg.exec_()

    def _global_category_analytics(self) -> None:
        try:
            records = self.db.get_json_records("violations")
        except Exception:
            records = []
        cat_col = "Категория риска"
        fine_col = "Штраф"
        status_col = "Статус"
        stats: Dict[str, Dict[str, Any]] = {}
        for rec in records:
            dj = rec.get("data_json", {})
            cat = str(dj.get(cat_col, I18n._("common.no_selection")))
            st = str(dj.get(status_col, "Активно"))
            fv = 0.0
            try:
                raw = str(dj.get(fine_col, "0"))
                cleaned = "".join(x for x in raw if x.isdigit() or x == ".")
                if cleaned:
                    fv = float(cleaned)
            except Exception:
                pass
            stats.setdefault(cat, {"total": 0, "resolved": 0, "fines": 0.0})
            stats[cat]["total"] += 1
            if st in ("Устранено", "Resolved"):
                stats[cat]["resolved"] += 1
            stats[cat]["fines"] += fv
        dlg = QDialog(self)
        dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        dlg.setWindowTitle(I18n._("analytics.category"))
        dlg.setMinimumSize(750, 450)
        lay = QVBoxLayout(dlg)
        t = QTableWidget()
        t.setColumnCount(5)
        t.setHorizontalHeaderLabels([
            I18n._("common.name"), I18n._("analytics.total"),
            I18n._("analytics.resolved"), I18n._("analytics.control_pct"),
            I18n._("analytics.fines_sum")])
        t.setRowCount(len(stats))
        for r, (cat, info) in enumerate(sorted(stats.items())):
            t.setItem(r, 0, QTableWidgetItem(cat))
            t.setItem(r, 1, QTableWidgetItem(str(info["total"])))
            t.setItem(r, 2, QTableWidgetItem(str(info["resolved"])))
            pct = (info["resolved"] / info["total"] * 100) if info["total"] > 0 else 100
            t.setItem(r, 3, QTableWidgetItem(f"{pct:.1f}%"))
            t.setItem(r, 4, QTableWidgetItem(
                f"{info['fines']:,.2f} {I18n._('common.currency')}"))
        t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        t.verticalHeader().setVisible(False)
        lay.addWidget(t)
        close_btn = QPushButton(I18n._("common.close"))
        close_btn.clicked.connect(dlg.accept)
        lay.addWidget(close_btn, 0, Qt.AlignCenter)
        dlg.exec_()

    # -----------------------------------------------------------------------
    # Logout
    # -----------------------------------------------------------------------

    def _on_logout(self) -> None:
        reply = QMessageBox.question(
            self, I18n._("login.logout"),
            I18n._("login.logout") + "?",
            QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.db.session_manager.clear_remember_me()
            self.db.log_event(f"User logged out: {self._user.get('username','?')}",
                              "INFO")
            self.close()
            QApplication.quit()

    # -----------------------------------------------------------------------
    # About
    # -----------------------------------------------------------------------

    def _show_about(self) -> None:
        QMessageBox.about(self, I18n._("common.about"),
            f"<h3>{I18n._('app.name')}</h3>"
            f"<p>{I18n._('app.version')}: {AppConfig.APP_VERSION}</p>"
            f"<p>{I18n._('app.copyright')}</p>"
            f"<p>{I18n._('settings.light')}/{I18n._('settings.dark')} · {I18n._('settings.language')}: RU/EN</p>")

    # -----------------------------------------------------------------------
    # Accessors for sub-tab injection
    # -----------------------------------------------------------------------

    def get_tab_widget(self, index: int) -> QWidget:
        return self._tab_widget.widget(index)

    def replace_tab(self, index: int, widget: QWidget, label: str) -> None:
        self._tab_widget.removeTab(index)
        self._tab_widget.insertTab(index, widget, label)


# ===========================================================================
# END OF PART 9 — BEGIN PART 10: Final Polish, Hotkeys & Integration
# ===========================================================================

# ---------------------------------------------------------------------------
# SECTION 10.1: Audit Tab
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    main()

