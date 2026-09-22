import os, ctypes, sys
from dataclasses import dataclass

from app_core.version import APP_VERSION


def get_short_path(path: str) -> str:
    if sys.platform == "win32":
        try:
            buf = ctypes.create_unicode_buffer(520)
            ctypes.windll.kernel32.GetShortPathNameW(path, buf, 520)
            return buf.value if buf.value else path
        except Exception:
            return path
    return path


def _merge_short_path_wal(app_dir: str, db_name: str) -> None:
    """Одноразовая нормализация: раньше путь к БД укорачивали до 8.3
    (SUOT_P~1.DB), из-за чего WAL/SHM плодились под двумя именами для одного
    файла. Чекпоинтим кадры через короткое имя и удаляем сиротские -wal/-shm.
    """
    long_db = os.path.join(app_dir, db_name)
    try:
        short_db = get_short_path(long_db)
    except Exception:
        return
    if not short_db or short_db == long_db:
        return
    if not any(os.path.exists(short_db + sfx) for sfx in ("-wal", "-shm")):
        return
    try:
        import sqlite3

        con = sqlite3.connect(short_db)
        try:
            row = con.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            con.commit()
        finally:
            con.close()
        busy = (row or (1,))[0]
        if busy:
            return  # базу держит другой процесс — не трогаем
        for sfx in ("-shm", "-wal"):
            try:
                if os.path.exists(short_db + sfx):
                    os.remove(short_db + sfx)
            except OSError:
                pass
    except Exception:
        pass


@dataclass(frozen=True)
class RuntimePaths:
    app_dir: str
    database_path: str
    backup_dir: str
    media_dir: str
    export_dir: str
    templates_dir: str
    plugins_dir: str


class AppConfig:
    APP_NAME = "ОхранаТруда Про"
    DB_NAME = "suot_platform.db"
    DATA_DIR = "data"
    BACKUP_DIR = "backups"
    MEDIA_DIR = "media"
    EXPORT_DIR = "exports"
    TEMPLATES_DIR = "templates"
    PLUGINS_DIR = "plugins"
    PBKDF2_ITERATIONS = 100_000
    TOKEN_LENGTH = 64
    TOKEN_TTL_DAYS = 30
    DEFAULT_LANG = "ru"
    DEFAULT_THEME = "auto"
    DEFAULT_ACCENT = "#2196F3"
    AUTO_SAVE_INTERVAL = 300
    REMINDER_CHECK_INTERVAL = 60
    APP_VERSION = APP_VERSION


class PathManager:
    @staticmethod
    def _writable_base() -> str:
        import sys

        if getattr(sys, "frozen", False):
            exe_dir = os.path.dirname(sys.executable)
            try:
                if os.access(exe_dir, os.W_OK):
                    return exe_dir
            except Exception:
                pass
            # exe в Program Files (только чтение): данные — в LOCALAPPDATA.
            base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
            fallback = os.path.join(base, "SUOT_Neo")
            os.makedirs(fallback, exist_ok=True)
            return fallback
        # Исходники: исторически база живёт в CWD (e2e-тесты изолируются
        # через chdir во временную папку) — поведение сохраняем.
        return os.path.abspath(".")

    def create() -> RuntimePaths:
        ad = PathManager._writable_base()
        _merge_short_path_wal(ad, AppConfig.DB_NAME)
        for d in [
            AppConfig.BACKUP_DIR,
            AppConfig.MEDIA_DIR,
            AppConfig.EXPORT_DIR,
            AppConfig.TEMPLATES_DIR,
            AppConfig.PLUGINS_DIR,
        ]:
            os.makedirs(os.path.join(ad, d), exist_ok=True)
        return RuntimePaths(
            app_dir=ad,
            database_path=os.path.join(ad, AppConfig.DB_NAME),
            backup_dir=os.path.join(ad, AppConfig.BACKUP_DIR),
            media_dir=os.path.join(ad, AppConfig.MEDIA_DIR),
            export_dir=os.path.join(ad, AppConfig.EXPORT_DIR),
            templates_dir=os.path.join(ad, AppConfig.TEMPLATES_DIR),
            plugins_dir=os.path.join(ad, AppConfig.PLUGINS_DIR),
        )


RUNTIME_PATHS = PathManager.create()
