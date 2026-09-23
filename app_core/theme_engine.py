import os
from typing import Callable, List, Optional
from PyQt5.QtWidgets import QApplication
from services.database import DatabaseManager


_THEME_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "resources", "themes"
)


def _detect_system_theme() -> str:
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as k:
            v, _ = winreg.QueryValueEx(k, "AppsUseLightTheme")
            return "light" if v else "dark"
    except Exception:
        return "light"


class ThemeEngine:
    _app: Optional[QApplication] = None
    _current_theme: str = "light"
    _current_accent: str = "#2196F3"
    _listeners: List[Callable[[], None]] = []

    @classmethod
    def on_change(cls, callback: Callable[[], None]) -> None:
        cls._listeners.append(callback)

    @classmethod
    def _notify(cls) -> None:
        for cb in cls._listeners:
            try:
                cb()
            except Exception:
                pass

    @classmethod
    def init(cls, app: QApplication) -> None:
        cls._app = app

    @classmethod
    def apply(cls, theme: Optional[str] = None, accent: Optional[str] = None) -> None:
        db = DatabaseManager()
        theme = theme or db.get_setting("theme", "")
        if not theme or theme == "auto":
            theme = _detect_system_theme()
        cls._current_theme = theme
        cls._current_accent = accent or db.get_setting("accent_color", "#2196F3")
        if cls._app:
            css = cls._load_qss()
            cls._app.setStyleSheet(css)
        cls._notify()

    @classmethod
    def theme(cls) -> str:
        return cls._current_theme

    @classmethod
    def accent(cls) -> str:
        return cls._current_accent

    @staticmethod
    def _contrast_accent(hex_color: str) -> str:
        h = hex_color.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255
        return "#FFFFFF" if lum < 0.5 else "#1C1C1E"

    @classmethod
    def _load_qss(cls) -> str:
        name = "dark.qss" if cls._current_theme == "dark" else "light.qss"
        path = os.path.join(_THEME_DIR, name)
        if not os.path.exists(path):
            return ""
        with open(path, "r", encoding="utf-8") as f:
            qss = f.read()
        a = cls._current_accent
        at = cls._contrast_accent(a)
        t = "#F5F5F7" if cls._current_theme == "dark" else "#1C1C1E"
        s = "#8E8E93" if cls._current_theme == "dark" else "#6C6C70"
        return (
            qss.replace("{{a}}", a)
            .replace("{{at}}", at)
            .replace("{{t}}", t)
            .replace("{{s}}", s)
        )
