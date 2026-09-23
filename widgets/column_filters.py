from typing import Any, Dict, List, Optional, Set

from PyQt5.QtCore import QEvent, QPoint, QRect, Qt, pyqtSignal
from PyQt5.QtGui import QCursor, QColor, QFontMetrics, QMouseEvent, QPainter, QPen
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)


class FilterPopup(QFrame):
    filterApplied = pyqtSignal(int, set)

    def __init__(
        self,
        section: int,
        values: List[str],
        selected: Set[str],
        parent: QWidget = None,
    ) -> None:
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self._section = section
        self._all_values = sorted(set(v for v in values if v))
        self._selected: Set[str] = set(selected)
        self._item_widgets: Dict[str, QCheckBox] = {}

        self.setMinimumWidth(220)
        self.setMaximumWidth(350)
        self.setMaximumHeight(400)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("""
            FilterPopup {
                background: palette(window);
                border: 1px solid palette(mid);
                border-radius: 8px;
            }
        """)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        search = QLineEdit()
        search.setPlaceholderText("Поиск...")
        search.setMinimumHeight(30)
        search.textChanged.connect(self._filter_list)
        layout.addWidget(search)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        container = QWidget()
        self._list_layout = QVBoxLayout(container)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(2)
        scroll.setWidget(container)
        layout.addWidget(scroll, 1)

        for val in self._all_values:
            cb = QCheckBox(val)
            if val in self._selected:
                cb.setChecked(True)
            cb.toggled.connect(lambda checked, v=val: self._on_toggle(v, checked))
            self._list_layout.addWidget(cb)
            self._item_widgets[val] = cb

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(6)
        sel_all = QPushButton("Все")
        sel_all.clicked.connect(self._select_all)
        clear_all = QPushButton("Очистить")
        clear_all.clicked.connect(self._clear_all)
        btn_layout.addWidget(sel_all)
        btn_layout.addWidget(clear_all)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

    def _filter_list(self, text: str) -> None:
        for val, cb in self._item_widgets.items():
            cb.setVisible(text.lower() in val.lower())

    def _on_toggle(self, val: str, checked: bool) -> None:
        if checked:
            self._selected.add(val)
        else:
            self._selected.discard(val)

    def _select_all(self) -> None:
        for val, cb in self._item_widgets.items():
            cb.setChecked(True)
            self._selected.add(val)

    def _clear_all(self) -> None:
        for val, cb in self._item_widgets.items():
            cb.setChecked(False)
        self._selected.clear()

    def closeEvent(self, event) -> None:
        self.filterApplied.emit(self._section, set(self._selected))
        super().closeEvent(event)


class FilterHeaderView(QHeaderView):
    filterChanged = pyqtSignal()

    def __init__(
        self, orientation: Qt.Orientation, parent: QTableWidget = None
    ) -> None:
        super().__init__(orientation, parent)
        self.setSectionsClickable(True)
        self.setHighlightSections(False)
        self._filters: Dict[int, Set[str]] = {}
        self._all_values: Dict[int, List[str]] = {}
        self._active_popup: Optional[FilterPopup] = None
        self.sectionClicked.connect(self._on_section_clicked)

    def set_column_values(self, section: int, values: List[str]) -> None:
        self._all_values[section] = values

    def set_filter(self, section: int, selected: Set[str]) -> None:
        original = set(self._filters.get(section, set()))
        if selected:
            self._filters[section] = selected
        elif section in self._filters:
            del self._filters[section]
        if original != self._filters.get(section, set()):
            self.filterChanged.emit()
            self.updateSection(section)

    def has_active_filter(self, section: int) -> bool:
        return section in self._filters

    def is_value_visible(self, section: int, value: str) -> bool:
        if section not in self._filters:
            return True
        return value in self._filters[section]

    def clear_all_filters(self) -> None:
        self._filters.clear()
        self.filterChanged.emit()
        self.update()

    def _on_section_clicked(self, section: int) -> None:
        if self._active_popup:
            self._active_popup.close()
            self._active_popup = None
            return

        pos = QCursor.pos()
        values = self._all_values.get(section, [])
        selected = self._filters.get(section, set())
        popup = FilterPopup(section, values, selected, self)
        popup.filterApplied.connect(self.set_filter)
        popup.setAttribute(Qt.WA_DeleteOnClose)
        popup.installEventFilter(self)
        popup.show()
        pw = popup.width()
        popup.move(pos.x() - pw // 2, pos.y() + 10)
        self._active_popup = popup

    def paintSection(self, painter: QPainter, rect: QRect, section: int) -> None:
        super().paintSection(painter, rect, section)

        if section in self._filters:
            painter.save()
            painter.setRenderHint(QPainter.Antialiasing)
            icon_rect = QRect(rect.right() - 18, rect.center().y() - 5, 10, 10)
            painter.setPen(QPen(QColor(80, 130, 230), 1.5))
            painter.drawText(icon_rect, Qt.AlignCenter, "▼")
            painter.restore()

    def eventFilter(self, obj, event) -> bool:
        if obj is self._active_popup and event.type() == QEvent.Close:
            self._active_popup = None
        return super().eventFilter(obj, event)
