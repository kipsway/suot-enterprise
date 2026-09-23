import math
from typing import Any, Callable, Dict, List, Optional

from PyQt5.QtCore import QEvent, QMimeData, QPoint, QRect, QSize, Qt, QTimer, QUrl
from PyQt5.QtGui import (
    QColor,
    QDragEnterEvent,
    QDropEvent,
    QFontMetrics,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPalette,
)
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QHBoxLayout,
    QMenu,
    QPushButton,
    QShortcut,
    QStyle,
    QStyleOptionTab,
    QTabBar,
    QTabWidget,
    QWidget,
)

from app_core.i18n import I18n
from app_core.theme_engine import ThemeEngine
from services.database import DatabaseManager


_CLOSE_SIZE = 16


def _is_dark() -> bool:
    return ThemeEngine._current_theme == "dark"


class BrowserTabBar(QTabBar):
    _drag_file_received = __import__("PyQt5.QtCore").QtCore.pyqtSignal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setExpanding(False)
        self.setDrawBase(False)
        self.setDocumentMode(True)
        self.setTabsClosable(False)
        self.setMovable(True)
        self._hover_close: int = -1
        self._locked: set = set()
        self.setMouseTracking(True)
        self.setUsesScrollButtons(True)
        self.setElideMode(Qt.ElideRight)
        self.tabBarClicked.connect(self._on_tab_clicked)
        self.setAcceptDrops(True)

    def lock_tab(self, index: int) -> None:
        self._locked.add(index)

    def unlock_tab(self, index: int) -> None:
        self._locked.discard(index)

    def is_locked(self, index: int) -> bool:
        return index in self._locked

    def tabSizeHint(self, index: int) -> QSize:
        if index in self._locked:
            return QSize(48, 34)
        text = self.tabText(index)
        fm = QFontMetrics(self.font())
        tw = fm.horizontalAdvance(text)
        return QSize(max(tw + 42, 100), 34)

    def mouseMoveEvent(self, event) -> None:
        pos = event.pos()
        old = self._hover_close
        self._hover_close = -1
        for i in range(self.count()):
            if i in self._locked:
                continue
            rect = self._close_rect(i)
            if rect.contains(pos):
                self._hover_close = i
                break
        if old != self._hover_close:
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover_close = -1
        self.update()
        super().leaveEvent(event)

    def _close_rect(self, index: int) -> QRect:
        rect = self.tabRect(index)
        x = rect.right() - _CLOSE_SIZE - 6
        y = rect.center().y() - _CLOSE_SIZE // 2
        return QRect(int(x), int(y), _CLOSE_SIZE, _CLOSE_SIZE)

    def _on_tab_clicked(self, index: int) -> None:
        if self._hover_close == index and index not in self._locked:
            tw = self.parent()
            if tw and hasattr(tw, "removeTab"):
                tw.removeTab(index)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        mime = event.mimeData()
        if mime.hasUrls() or mime.hasText():
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:
        event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        mime = event.mimeData()
        paths = []
        if mime.hasUrls():
            for url in mime.urls():
                if url.isLocalFile():
                    paths.append(url.toLocalFile())
                else:
                    paths.append(url.toString())
        elif mime.hasText():
            paths.append(mime.text())
        for p in paths:
            self._drag_file_received.emit(p)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        dark = _is_dark()
        bg = QColor(255, 255, 255)
        selected_bg = QColor(255, 255, 255)
        inactive_bg = QColor(0, 0, 0, 0)
        selected_text = QColor(30, 30, 30)
        inactive_text = QColor(120, 120, 120)
        hover_bg = QColor(0, 0, 0, 20)

        if dark:
            bg = QColor(30, 30, 35)
            selected_bg = QColor(42, 42, 48)
            inactive_bg = QColor(0, 0, 0, 0)
            selected_text = QColor(230, 230, 235)
            inactive_text = QColor(140, 140, 145)
            hover_bg = QColor(255, 255, 255, 12)

        for i in range(self.count()):
            rect = self.tabRect(i)
            selected = i == self.currentIndex()

            path = QPainterPath()
            r = 8
            path.moveTo(rect.left(), rect.bottom())
            path.lineTo(rect.left(), rect.top() + r)
            path.quadTo(rect.left(), rect.top(), rect.left() + r, rect.top())
            path.lineTo(rect.right() - r, rect.top())
            path.quadTo(rect.right(), rect.top(), rect.right(), rect.top() + r)
            path.lineTo(rect.right(), rect.bottom())
            path.closeSubpath()

            if selected:
                painter.fillPath(path, selected_bg)
            elif i == self._hover_close:
                painter.fillPath(path, hover_bg)

            painter.setPen(selected_text if selected else inactive_text)
            fm = QFontMetrics(self.font())
            if i in self._locked:
                pin_rect = rect.adjusted(0, 0, 0, 0)
                painter.setPen(selected_text if selected else inactive_text)
                painter.drawText(pin_rect, Qt.AlignCenter, "📌")
            else:
                text_rect = rect.adjusted(14, 0, -(_CLOSE_SIZE + 10), 0)
                elided = fm.elidedText(
                    self.tabText(i), Qt.ElideRight, text_rect.width()
                )
                painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, elided)

            if i not in self._locked:
                cr = self._close_rect(i)
                if i == self._hover_close:
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(
                        QColor(200, 60, 60) if selected else QColor(160, 160, 160)
                    )
                    painter.drawRoundedRect(cr, 3, 3)
                    painter.setPen(Qt.white)
                    painter.setFont(self.font())
                    painter.drawText(cr, Qt.AlignCenter, "×")
                elif selected:
                    painter.setPen(QColor(160, 160, 160))
                    painter.drawText(cr, Qt.AlignCenter, "×")

        painter.end()

    def mousePressEvent(self, event) -> None:
        pos = event.pos()
        for i in range(self.count()):
            if i in self._locked:
                continue
            if self._close_rect(i).contains(pos):
                tw = self.parent()
                if tw and hasattr(tw, "removeTab"):
                    tw.removeTab(i)
                return
        super().mousePressEvent(event)

    def contextMenuEvent(self, event) -> None:
        pos = event.pos()
        idx = self.tabAt(pos)
        if idx < 0:
            return
        menu = QMenu(self)
        dark = _is_dark()
        menu.setStyleSheet(f"""
            QMenu {{ background: {"#2A2A30" if dark else "#FFFFFF"};
                      border: 1px solid {"#3A3A42" if dark else "#E0E0E8"};
                      border-radius: 6px; padding: 4px; }}
            QMenu::item {{ padding: 6px 20px; border-radius: 4px;
                          color: {"#e0e0e0" if dark else "#333"}; }}
            QMenu::item:selected {{ background: {"#3A3A42" if dark else "#E0E0E8"}; }}
        """)
        if idx in self._locked:
            action = QAction(I18n._("browser.unpin_tab"), menu)
            action.triggered.connect(lambda: self._toggle_pin(idx))
            menu.addAction(action)
        else:
            action = QAction(I18n._("browser.pin_tab"), menu)
            action.triggered.connect(lambda: self._toggle_pin(idx))
            menu.addAction(action)
        menu.addSeparator()
        menu.addAction(
            I18n._("browser.duplicate_tab"), lambda: self._duplicate_tab(idx)
        )
        menu.addSeparator()
        menu.addAction(I18n._("browser.rename_tab"), lambda: self._rename_tab(idx))
        menu.exec_(event.globalPos())

    def _toggle_pin(self, index: int) -> None:
        tw = self.parent()
        if not tw:
            return
        if index in self._locked:
            self.unlock_tab(index)
            tw.setTabText(
                index,
                tw._saved_tab_names.get(index, tw.tabText(index)) or tw.tabText(index),
            )
        else:
            self.lock_tab(index)
            tw._saved_tab_names[index] = tw.tabText(index)
            tw.setTabText(index, "")
        self.update()

    def _rename_tab(self, index: int) -> None:
        from PyQt5.QtWidgets import QInputDialog

        tw = self.parent()
        if not tw:
            return
        saved = getattr(tw, "_saved_tab_names", {})
        text = tw.tabText(index) or saved.get(index, "")
        new_name, ok = QInputDialog.getText(
            tw, I18n._("browser.rename_tab"), I18n._("browser.rename_hint"), text=text
        )
        if ok and new_name:
            if index in self._locked and hasattr(tw, "_saved_tab_names"):
                tw._saved_tab_names[index] = new_name
            else:
                tw.setTabText(index, new_name)

    def _duplicate_tab(self, index: int) -> None:
        tw = self.parent()
        if tw and hasattr(tw, "duplicate_tab"):
            tw.duplicate_tab(index)


class BrowserTabWidget(QTabWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        bar = BrowserTabBar()
        self.setTabBar(bar)
        self.setDocumentMode(True)
        self.setMovable(True)
        self._saved_tab_names: Dict[int, str] = {}
        self._skeleton_widgets: Dict[int, Any] = {}
        self._db = DatabaseManager()
        bar._drag_file_received.connect(self._on_file_dropped)
        self._auto_restore_session()
        QTimer.singleShot(2000, self._auto_save_session)
        self._apply_style()
        self._setup_shortcuts()
        self._build_buttons()

    def _build_buttons(self) -> None:
        bar = self.tabBar()
        tb = bar.parent() if hasattr(bar, "parent") else None

        self._add_tab_btn = QPushButton("+")
        self._add_tab_btn.setFixedSize(28, 24)
        self._add_tab_btn.setCursor(Qt.PointingHandCursor)
        self._add_tab_btn.clicked.connect(self._add_new_tab)
        self._add_tab_btn.setToolTip("Новая вкладка")

        self._menu_btn = QPushButton("≡")
        self._menu_btn.setFixedSize(28, 24)
        self._menu_btn.setCursor(Qt.PointingHandCursor)
        self._menu_btn.clicked.connect(self._show_overflow_menu)
        self._menu_btn.setToolTip("Меню вкладок")

        corner = QWidget()
        hl = QHBoxLayout(corner)
        hl.setContentsMargins(0, 0, 4, 0)
        hl.setSpacing(2)
        hl.addWidget(self._add_tab_btn)
        hl.addWidget(self._menu_btn)
        self.setCornerWidget(corner, Qt.TopRightCorner)

        self._style_buttons()

    def _style_buttons(self) -> None:
        dark = _is_dark()
        fg = "#e0e0e0" if dark else "#333"
        bg = "#3a3a42" if dark else "#e0e0e8"
        hover_bg = "#50505a" if dark else "#d0d0d8"
        style = f"""
            QPushButton {{
                border: none; border-radius: 4px; font-size: 14px;
                color: {fg}; background: transparent;
            }}
            QPushButton:hover {{
                background: {hover_bg};
            }}
        """
        self._add_tab_btn.setStyleSheet(style)
        self._menu_btn.setStyleSheet(style)

    def _setup_shortcuts(self) -> None:
        self._shortcut_next = QShortcut(QKeySequence("Ctrl+Tab"), self)
        self._shortcut_next.activated.connect(self._next_tab)
        self._shortcut_prev = QShortcut(QKeySequence("Ctrl+Shift+Tab"), self)
        self._shortcut_prev.activated.connect(self._prev_tab)

    def _next_tab(self) -> None:
        i = self.currentIndex()
        self.setCurrentIndex((i + 1) % self.count())

    def _prev_tab(self) -> None:
        i = self.currentIndex()
        self.setCurrentIndex((i - 1) % self.count())

    def _auto_save_session(self) -> None:
        self._save_session()
        self._auto_save_timer = QTimer(self)
        self._auto_save_timer.timeout.connect(self._save_session)
        self._auto_save_timer.start(60000)

    def _auto_restore_session(self) -> None:
        try:
            tabs = self._db.load_tab_session()
            if len(tabs) > 1:
                self._restore_session()
        except Exception:
            pass

    def _add_new_tab(self) -> None:
        from widgets.home_page import HomePage

        hp = HomePage()
        hp.navigateTo.connect(lambda k: self._navigate_from_home(k))
        idx = self.addTab(hp, "🏠 Главная")
        self.setCurrentIndex(idx)

    def _navigate_from_home(self, key: str) -> None:
        if self.parent() and hasattr(self.parent(), "_omnibox_navigate_tab"):
            self.parent()._omnibox_navigate_tab(key)

    def _show_overflow_menu(self) -> None:
        menu = QMenu(self)
        dark = _is_dark()
        menu.setStyleSheet(f"""
            QMenu {{
                background: {"#2A2A30" if dark else "#FFFFFF"};
                border: 1px solid {"#3A3A42" if dark else "#E0E0E8"};
                border-radius: 6px; padding: 4px;
            }}
            QMenu::item {{
                padding: 6px 20px; border-radius: 4px;
                color: {"#e0e0e0" if dark else "#333"};
            }}
            QMenu::item:selected {{
                background: {"#3A3A42" if dark else "#E0E0E8"};
            }}
        """)
        bar = self.tabBar()
        for i in range(self.count()):
            text = bar.tabText(i) or f"Вкладка {i + 1}"
            action = menu.addAction(text)
            action.setData(i)
        menu.addSeparator()
        menu.addAction("💾 Сохранить сессию", self._save_session)
        menu.addAction("📂 Восстановить сессию", self._restore_session)
        menu.addSeparator()
        menu.addAction("❌ Закрыть все", self._close_all_tabs)
        action = menu.exec_(
            self._menu_btn.mapToGlobal(self._menu_btn.rect().bottomLeft())
        )
        if action and action.data() is not None:
            self.setCurrentIndex(action.data())

    def _save_session(self) -> None:
        bar = self.tabBar()
        tabs = []
        for i in range(self.count()):
            tabs.append(
                {
                    "text": bar.tabText(i),
                    "locked": bar.is_locked(i),
                    "type": "home",
                    "data": "",
                }
            )
        self._db.save_tab_session(tabs)

    def _restore_session(self) -> None:
        try:
            tabs = self._db.load_tab_session()
        except Exception:
            return
        if not tabs:
            return
        while self.count() > 0:
            self.removeTab(0)
        for tab in tabs:
            from widgets.home_page import HomePage

            hp = HomePage()
            hp.navigateTo.connect(lambda k: self._navigate_from_home(k))
            idx = self.addTab(hp, tab.get("text", "🏠 Главная"))
            if tab.get("locked"):
                self.tabBar().lock_tab(idx)

    def _on_file_dropped(self, path: str) -> None:
        from widgets.home_page import HomePage

        hp = HomePage()
        hp.navigateTo.connect(lambda k: self._navigate_from_home(k))
        idx = self.addTab(hp, path)
        self.setCurrentIndex(idx)

    def duplicate_tab(self, index: int) -> None:
        widget = self.widget(index)
        if widget:
            from copy import deepcopy

            try:
                new_widget = deepcopy(widget)
            except Exception:
                from widgets.home_page import HomePage

                new_widget = HomePage()
            text = self.tabText(index) or self._saved_tab_names.get(index, "Tab")
            new_idx = self.addTab(new_widget, text)
            self.setCurrentIndex(new_idx)

    def show_skeleton(self, index: int) -> None:
        from widgets.skeleton import SkeletonWidget

        sk = SkeletonWidget()
        self._skeleton_widgets[index] = sk
        w = self.widget(index)
        if w:
            sk.setParent(w)
            sk.setGeometry(w.rect())
            sk.show()
            sk.raise_()

    def hide_skeleton(self, index: int) -> None:
        sk = self._skeleton_widgets.pop(index, None)
        if sk:
            sk.hide()
            sk.deleteLater()

    def _close_all_tabs(self) -> None:
        while self.count() > 0:
            self.removeTab(0)

    def _apply_style(self) -> None:
        dark = _is_dark()
        bg = "#1E1E23" if dark else "#F5F5FA"
        pane_bg = "#2A2A30" if dark else "#FFFFFF"
        border = "#3A3A42" if dark else "#E0E0E8"

        self.setStyleSheet(f"""
        QTabWidget::pane {{
            border: none;
            background: {pane_bg};
            border-top: 1px solid {border};
        }}
        """)
