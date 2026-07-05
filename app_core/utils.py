import json
from typing import Any, Dict, Optional
from datetime import datetime, timedelta
from PyQt5.QtCore import QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QWidget, QFrame, QVBoxLayout, QTableWidget, QScroller, QGraphicsOpacityEffect


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


def get_valid_until_bg(date_str: Any, is_dark: bool):
    dt = parse_date_flexible(date_str)
    if not dt:
        return None
    today = datetime.now()
    if dt < today:
        return QColor('#582525' if is_dark else '#f8d7da')
    if dt <= today + timedelta(days=30):
        return QColor('#614d17' if is_dark else '#fff3cd')
    return QColor('#254b32' if is_dark else '#d4edda')


def get_date_indicator_bg(date_str: Any, is_dark: bool, date_mode: str = 'Действует до'):
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


def get_status_indicator_bg(status_str: Any, is_dark: bool):
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


def apply_glass_style(widget: QWidget, intensity: str = "medium") -> None:
    from app_core.theme_engine import ThemeEngine
    is_dark = ThemeEngine._current_theme == "dark"
    if intensity == "high":
        bg = "rgba(255,255,255,0.12)" if not is_dark else "rgba(255,255,255,0.10)"
        bg_to = "rgba(255,255,255,0.06)" if not is_dark else "rgba(255,255,255,0.04)"
    elif intensity == "low":
        bg = "rgba(255,255,255,0.55)" if not is_dark else "rgba(255,255,255,0.04)"
        bg_to = "rgba(255,255,255,0.40)" if not is_dark else "rgba(255,255,255,0.02)"
    else:
        bg = "rgba(255,255,255,0.75)" if not is_dark else "rgba(255,255,255,0.07)"
        bg_to = "rgba(255,255,255,0.55)" if not is_dark else "rgba(255,255,255,0.03)"
    border = "rgba(255,255,255,0.35)" if not is_dark else "rgba(255,255,255,0.07)"
    widget.setStyleSheet(f"""
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {bg}, stop:1 {bg_to});
        border: 1px solid {border};
        border-radius: 14px;
    """)


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
    from app_core.theme_engine import ThemeEngine
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
