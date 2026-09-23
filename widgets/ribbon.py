from typing import Callable, Dict, List, Optional, Tuple

from PyQt5.QtCore import Qt, QSize, QTimer
from PyQt5.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QButtonGroup,
)

from app_core.design_tokens import palette
from app_core.theme_engine import ThemeEngine


class _RibbonGroup(QFrame):
    def __init__(self, title: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._title = title
        self._buttons: List[QToolButton] = []
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(4, 2, 4, 14)
        self._layout.setSpacing(2)
        self.setFixedHeight(72)

    def add_button(self, emoji: str, tip: str, cb: Callable) -> QToolButton:
        btn = QToolButton()
        btn.setText(emoji)
        btn.setToolTip(tip)
        btn.setFixedSize(36, 36)
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(cb)
        self._layout.addWidget(btn)
        self._buttons.append(btn)
        return btn

    def add_widget(self, widget: QWidget) -> None:
        self._layout.addWidget(widget)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        dark = ThemeEngine._current_theme == "dark"
        pal = palette(dark)
        r = 6
        from PyQt5.QtCore import QRectF

        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), r, r)
        bg = QColor(pal.bg_secondary)
        p.fillPath(path, bg)
        p.setPen(QPen(QColor(pal.border), 0.5))
        p.drawPath(path)
        p.setPen(QColor(pal.text_tertiary))
        f = self.font()
        f.setPointSize(8)
        p.setFont(f)
        p.drawText(
            self.rect().adjusted(0, 0, 0, -2),
            Qt.AlignBottom | Qt.AlignHCenter,
            self._title,
        )
        p.end()


class _TableGridPopup(QFrame):
    """10x10 grid for table insertion."""

    selected = None

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._rows = self._cols = 0
        self.setWindowFlags(Qt.Popup)
        dark = ThemeEngine._current_theme == "dark"
        pal = palette(dark)
        g = QGridLayout(self)
        g.setSpacing(2)
        g.setContentsMargins(6, 6, 6, 6)
        self._cells: List[QPushButton] = []
        for r in range(10):
            for c in range(10):
                btn = QPushButton()
                btn.setFixedSize(16, 16)
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {pal.border}; border: 1px solid {pal.border};
                        border-radius: 2px;
                    }}
                    QPushButton:hover {{
                        background: {pal.accent};
                    }}
                """)
                btn.enterEvent = lambda e, rr=r, cc=c: self._hover(rr, cc)
                btn.mousePressEvent = lambda e, rr=r + 1, cc=c + 1: self._select(rr, cc)
                g.addWidget(btn, r, c)
                self._cells.append(btn)
        self._label = QLabel("0 × 0")
        self._label.setAlignment(Qt.AlignCenter)
        g.addWidget(self._label, 10, 0, 1, 10)

    def _hover(self, r: int, c: int) -> None:
        self._rows = r + 1
        self._cols = c + 1
        self._label.setText(f"{self._rows} × {self._cols}")
        for i, btn in enumerate(self._cells):
            rr = i // 10
            cc = i % 10
            if rr <= r and cc <= c:
                btn.setStyleSheet(
                    f"background: {palette(ThemeEngine._current_theme == 'dark').accent}; border-radius: 2px;"
                )
            else:
                dark = ThemeEngine._current_theme == "dark"
                btn.setStyleSheet(
                    f"background: {palette(dark).border}; border: 1px solid {palette(dark).border}; border-radius: 2px;"
                )

    def _select(self, r: int, c: int) -> None:
        self._rows = r
        self._cols = c
        self.selected = (r, c)
        self.close()


class _RibbonTabBar(QFrame):
    tab_selected = None

    def __init__(self, tabs: List[str], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tabs = tabs
        self._current = 0
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(4, 0, 4, 0)
        self._layout.setSpacing(0)
        self._buttons: List[QPushButton] = []
        for i, name in enumerate(tabs):
            btn = QPushButton(name)
            btn.setFixedHeight(26)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked, idx=i: self._select(idx))
            self._layout.addWidget(btn)
            self._buttons.append(btn)
        self._layout.addStretch()
        self.setFixedHeight(28)
        self._update_style()

    def _select(self, idx: int) -> None:
        self._current = idx
        self._update_style()
        if self.tab_selected:
            self.tab_selected(idx)

    def _update_style(self) -> None:
        dark = ThemeEngine._current_theme == "dark"
        pal = palette(dark)
        for i, btn in enumerate(self._buttons):
            if i == self._current:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {pal.bg_primary}; color: {pal.text_primary};
                        border: none; border-top: 2px solid {pal.accent};
                        border-radius: 0px; padding: 0 12px;
                        font-weight: bold; font-size: 11px;
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: transparent; color: {pal.text_tertiary};
                        border: none; padding: 0 12px;
                        font-size: 11px;
                    }}
                    QPushButton:hover {{
                        color: {pal.text_primary};
                    }}
                """)


class RibbonWidget(QFrame):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._collapsed = False
        self._groups: Dict[str, _RibbonGroup] = {}
        self._context_visible = False

        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(0, 0, 0, 0)
        self._main_layout.setSpacing(0)

        self._tab_bar = _RibbonTabBar(
            ["Главная", "Вставка", "Шаблон", "Макет", "Вид", "Таблица"], self
        )
        self._tab_bar.tab_selected = self._on_tab_selected
        self._main_layout.addWidget(self._tab_bar)

        self._content = QFrame()
        self._content_layout = QHBoxLayout(self._content)
        self._content_layout.setContentsMargins(4, 2, 4, 2)
        self._content_layout.setSpacing(6)
        self._main_layout.addWidget(self._content)

        self._setup_tabs()
        self._select_tab(0)
        self._tab_bar._buttons[-1].setVisible(False)

    def _setup_tabs(self) -> None:
        self._tab_groups: Dict[int, List[str]] = {}

        g = _RibbonGroup("Буфер обмена", self)
        g.add_button("✂️", "Вырезать", lambda: self._emit("cut"))
        g.add_button("📋", "Копировать", lambda: self._emit("copy"))
        g.add_button("📄", "Вставить", lambda: self._emit("paste"))
        self._tab_groups[0] = ["clipboard"]
        self._groups["clipboard"] = g

        g = _RibbonGroup("Шрифт", self)
        g.add_button("B", "Полужирный", lambda: self._emit("bold"))
        g.add_button("I", "Курсив", lambda: self._emit("italic"))
        g.add_button("U", "Подчеркнутый", lambda: self._emit("underline"))
        g.add_button("S", "Зачеркнутый", lambda: self._emit("strike"))
        self._tab_groups[0].append("font")
        self._groups["font"] = g

        g = _RibbonGroup("Абзац", self)
        g.add_button("◀", "По левому краю", lambda: self._emit("align_left"))
        g.add_button("■", "По центру", lambda: self._emit("align_center"))
        g.add_button("▶", "По правому краю", lambda: self._emit("align_right"))
        g.add_button("⇔", "По ширине", lambda: self._emit("align_justify"))
        self._tab_groups[0].append("paragraph")
        self._groups["paragraph"] = g

        g = _RibbonGroup("Вставка", self)
        g.add_button("⊞", "Таблица", lambda: self._emit("insert_table"))
        g.add_button("🖼", "Изображение", lambda: self._emit("insert_image"))
        g.add_button("🔗", "Ссылка", lambda: self._emit("insert_link"))
        g.add_button("↵", "Разрыв", lambda: self._emit("insert_break"))
        self._tab_groups[1] = ["insert"]
        self._groups["insert"] = g

        g = _RibbonGroup("Стили", self)
        g.add_button("🎨", "Стили", lambda: self._emit("styles"))
        g.add_button("🎯", "Цвета", lambda: self._emit("colors"))
        g.add_button("📁", "Шаблоны", lambda: self._emit("templates"))
        self._tab_groups[2] = ["styles"]
        self._groups["styles"] = g

        g = _RibbonGroup("Параметры", self)
        g.add_button("📐", "Поля", lambda: self._emit("margins"))
        g.add_button("🔄", "Ориентация", lambda: self._emit("orientation"))
        g.add_button("📏", "Размер", lambda: self._emit("page_size"))
        g.add_button("📰", "Колонки", lambda: self._emit("columns"))
        self._tab_groups[3] = ["params"]
        self._groups["params"] = g

        g = _RibbonGroup("Масштаб", self)
        g.add_button("🔍+", "Приблизить", lambda: self._emit("zoom_in"))
        g.add_button("🔍−", "Отдалить", lambda: self._emit("zoom_out"))
        g.add_button("100%", "Сбросить", lambda: self._emit("zoom_reset"))
        self._tab_groups[4] = ["zoom"]
        self._groups["zoom"] = g

        g = _RibbonGroup("Таблица", self)
        g.add_button("📊", "Вставить", lambda: self._emit("table_insert"))
        g.add_button("➕", "Добавить строку", lambda: self._emit("table_add_row"))
        g.add_button("➕", "Добавить столбец", lambda: self._emit("table_add_col"))
        g.add_button("➖", "Удалить строку", lambda: self._emit("table_del_row"))
        g.add_button("➖", "Удалить столбец", lambda: self._emit("table_del_col"))
        g.add_button("🔗", "Объединить", lambda: self._emit("table_merge"))
        g.add_button("✂️", "Разделить", lambda: self._emit("table_split"))
        self._tab_groups[5] = ["table"]
        self._groups["table"] = g

    def _select_tab(self, idx: int) -> None:
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            if item and item.widget():
                item.widget().setParent(None)
        names = self._tab_groups.get(idx, [])
        for name in names:
            g = self._groups.get(name)
            if g:
                self._content_layout.addWidget(g)
        self._content_layout.addStretch()

    def _on_tab_selected(self, idx: int) -> None:
        if idx == 5 and not self._context_visible:
            self._tab_bar._select(0)
            return
        self._select_tab(idx)

    def show_context_tab(self, visible: bool) -> None:
        self._context_visible = visible
        self._tab_bar._buttons[-1].setVisible(visible)
        if visible:
            self._tab_bar._select(5)

    def set_collapsed(self, collapsed: bool) -> None:
        self._collapsed = collapsed
        self._content.setVisible(not collapsed)
        self.setFixedHeight(28 if collapsed else 110)

    def toggle_collapsed(self) -> None:
        self.set_collapsed(not self._collapsed)

    def mouseDoubleClickEvent(self, event) -> None:
        self.toggle_collapsed()

    def _emit(self, action: str) -> None:
        p = self.parent()
        while p:
            if hasattr(p, "handle_ribbon_action"):
                p.handle_ribbon_action(action)
                return
            p = p.parent()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        dark = ThemeEngine._current_theme == "dark"
        pal = palette(dark)
        r = 8
        from PyQt5.QtCore import QRectF

        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), r, r)
        bg = QColor(pal.bg_secondary)
        p.fillPath(path, bg)
        p.setPen(QPen(QColor(pal.border), 0.5))
        p.drawPath(path)
        p.end()
