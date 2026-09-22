from typing import Callable, Optional

from PyQt5.QtCore import Qt, QObject
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon, QWidget


class TrayManager(QObject):
    _instance: Optional["TrayManager"] = None

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._parent = parent
        self._tray: Optional[QSystemTrayIcon] = None
        self._on_show: Optional[Callable] = None
        self._on_quit: Optional[Callable] = None

    @classmethod
    def instance(cls, parent: Optional[QWidget] = None) -> "TrayManager":
        if cls._instance is None:
            cls._instance = cls(parent)
        return cls._instance

    def init(
        self, on_show: Optional[Callable] = None, on_quit: Optional[Callable] = None
    ) -> None:
        self._on_show = on_show
        self._on_quit = on_quit

        if not QSystemTrayIcon.isSystemTrayAvailable():
            return

        pix = QPixmap(16, 16)
        pix.fill(Qt.transparent)
        icon = QIcon(pix)

        self._tray = QSystemTrayIcon(icon, self._parent)
        self._tray.setToolTip("SUOT Enterprise")

        menu = QMenu()
        show_action = menu.addAction("Показать")
        show_action.triggered.connect(self._on_show_action)
        quit_action = menu.addAction("Выход")
        quit_action.triggered.connect(self._on_quit_action)
        self._tray.setContextMenu(menu)

        self._tray.activated.connect(self._on_activated)
        self._tray.show()

    def notify(
        self,
        title: str,
        message: str,
        icon: int = QSystemTrayIcon.Information,
        duration_ms: int = 5000,
    ) -> None:
        if self._tray is not None:
            self._tray.showMessage(title, message, icon, duration_ms)

    def _on_show_action(self) -> None:
        if self._on_show:
            self._on_show()

    def _on_quit_action(self) -> None:
        if self._on_quit:
            self._on_quit()
        else:
            QApplication.quit()

    def _on_activated(self, reason: int) -> None:
        if reason == QSystemTrayIcon.DoubleClick and self._on_show:
            self._on_show()

    def is_available(self) -> bool:
        return self._tray is not None

    def shutdown(self) -> None:
        if self._tray:
            self._tray.hide()
            self._tray = None
