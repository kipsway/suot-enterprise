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
    @staticmethod
    def _writable_base() -> str:
        import sys

        if getattr(sys, "frozen", False):
            return os.path.dirname(sys.executable)
        return os.path.abspath(
            os.path.dirname(__file__ if "__file__" in dir() else ".")
        )

    def create() -> RuntimePaths:
        ad = PathManager._writable_base()
        for d in [
            AppConfig.BACKUP_DIR,
            AppConfig.MEDIA_DIR,
            AppConfig.EXPORT_DIR,
            AppConfig.TEMPLATES_DIR,
            AppConfig.PLUGINS_DIR,
        ]:
            os.makedirs(os.path.join(ad, d), exist_ok=True)
        return RuntimePaths(
            app_dir=get_short_path(ad),
            database_path=get_short_path(os.path.join(ad, AppConfig.DB_NAME)),
            backup_dir=get_short_path(os.path.join(ad, AppConfig.BACKUP_DIR)),
            media_dir=get_short_path(os.path.join(ad, AppConfig.MEDIA_DIR)),
            export_dir=get_short_path(os.path.join(ad, AppConfig.EXPORT_DIR)),
            templates_dir=get_short_path(os.path.join(ad, AppConfig.TEMPLATES_DIR)),
            plugins_dir=get_short_path(os.path.join(ad, AppConfig.PLUGINS_DIR)),
        )


RUNTIME_PATHS = PathManager.create()
