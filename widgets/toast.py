from PyQt5.QtCore import QEasingCurve, Qt, QPropertyAnimation, QTimer, QPoint
from PyQt5.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QWidget
from typing import Optional, List

from app_core.theme_engine import ThemeEngine


class ToastNotification(QFrame):
    _instance: Optional["ToastNotification"] = None
    _active_toasts: List["ToastNotification"] = []

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
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

    def show_toast(
        self, message: str, toast_type: str = "info", timeout: int = 5000
    ) -> None:
        self._timeout = timeout
        self._text_label.setText(message)
        self._apply_style(toast_type)
        icons = {
            "info": "ℹ",
            "success": "✓",
            "warning": "⚠",
            "error": "✕",
        }
        self._icon_label.setText(icons.get(toast_type, "ℹ"))
        self.adjustSize()
        self._position_toast()
        self.setWindowOpacity(0.0)
        self.show()
        self._slide_in = QPropertyAnimation(self, b"windowOpacity")
        self._slide_in.setDuration(350)
        self._slide_in.setStartValue(0.0)
        self._slide_in.setEndValue(0.98)
        self._slide_in.setEasingCurve(QEasingCurve.OutBack)
        self._slide_in.start(QPropertyAnimation.DeleteWhenStopped)
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
    def notify(
        cls, message: str, toast_type: str = "info", timeout: int = 5000
    ) -> None:
        toast = cls()
        toast.show_toast(message, toast_type, timeout)
        try:
            from services.tray_manager import TrayManager

            tray = TrayManager.instance()
            if tray.is_available():
                from PyQt5.QtWidgets import QSystemTrayIcon

                icon_map = {
                    "success": QSystemTrayIcon.Information,
                    "error": QSystemTrayIcon.Critical,
                    "warning": QSystemTrayIcon.Warning,
                }
                tray.notify(
                    "SUOT Enterprise",
                    message,
                    icon_map.get(toast_type, QSystemTrayIcon.Information),
                    5000,
                )
        except Exception:
            pass
