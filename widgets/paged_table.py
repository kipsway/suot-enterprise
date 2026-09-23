import math
from typing import Any, Callable, Dict, List, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QAbstractItemView,
    QHeaderView,
)

from app_core.design_tokens import palette
from app_core.theme_engine import ThemeEngine
from widgets.glass_button import GlassButton


class PagedTableWidget(QWidget):
    def __init__(self, page_size: int = 50, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._page_size = page_size
        self._all_data: List[Dict[str, Any]] = []
        self._filtered_data: List[Dict[str, Any]] = []
        self._current_page = 0
        self._columns: List[str] = []
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._table = QTableWidget()
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setSortingEnabled(False)
        layout.addWidget(self._table, 1)

        controls = QFrame()
        cl = QHBoxLayout(controls)
        cl.setContentsMargins(4, 2, 4, 2)
        cl.setSpacing(4)

        self._info_label = QLabel("0 записей")
        cl.addWidget(self._info_label)

        self._first_btn = GlassButton("⏮")
        self._first_btn.setFixedSize(28, 26)
        self._first_btn.setProperty("flat", True)
        self._first_btn.clicked.connect(lambda: self.go_to_page(0))
        cl.addWidget(self._first_btn)

        self._prev_btn = GlassButton("◀")
        self._prev_btn.setFixedSize(28, 26)
        self._prev_btn.setProperty("flat", True)
        self._prev_btn.clicked.connect(self._prev_page)
        cl.addWidget(self._prev_btn)

        self._page_spin = QSpinBox()
        self._page_spin.setMinimum(1)
        self._page_spin.setFixedWidth(56)
        self._page_spin.setMinimumHeight(26)
        self._page_spin.valueChanged.connect(self._on_spin_changed)
        cl.addWidget(self._page_spin)

        self._total_label = QLabel("из 1")
        cl.addWidget(self._total_label)

        self._next_btn = GlassButton("▶")
        self._next_btn.setFixedSize(28, 26)
        self._next_btn.setProperty("flat", True)
        self._next_btn.clicked.connect(self._next_page)
        cl.addWidget(self._next_btn)

        self._last_btn = GlassButton("⏭")
        self._last_btn.setFixedSize(28, 26)
        self._last_btn.setProperty("flat", True)
        self._last_btn.clicked.connect(self._go_last)
        cl.addWidget(self._last_btn)

        cl.addStretch()

        cl.addWidget(QLabel("На странице:"))
        self._size_combo = QComboBox()
        self._size_combo.setMinimumHeight(26)
        self._size_combo.addItems(["20", "50", "100", "200", "500"])
        self._size_combo.setCurrentText(str(self._page_size))
        self._size_combo.currentTextChanged.connect(self._on_size_changed)
        cl.addWidget(self._size_combo)

        layout.addWidget(controls)

    def set_columns(self, columns: List[str]) -> None:
        self._columns = columns
        self._table.setColumnCount(len(columns))
        self._table.setHorizontalHeaderLabels(columns)

    def set_data(
        self, data: List[Dict[str, Any]], extract_fn: Optional[Callable] = None
    ) -> None:
        self._all_data = data
        self._filtered_data = list(data)
        self._current_page = 0
        self._update_table(extract_fn)

    def _update_table(self, extract_fn: Optional[Callable] = None) -> None:
        total = len(self._filtered_data)
        total_pages = max(1, math.ceil(total / self._page_size))
        if self._current_page >= total_pages:
            self._current_page = total_pages - 1

        start = self._current_page * self._page_size
        end = min(start + self._page_size, total)
        page_data = self._filtered_data[start:end]

        self._table.setRowCount(0)
        for rec in page_data:
            row = self._table.rowCount()
            self._table.insertRow(row)
            for col, col_name in enumerate(self._columns):
                val = extract_fn(rec, col_name) if extract_fn else rec.get(col_name, "")
                item = QTableWidgetItem(str(val))
                self._table.setItem(row, col, item)

        self._table.resizeColumnsToContents()
        self._info_label.setText(
            f"{total} записей (стр. {self._current_page + 1} из {total_pages})"
        )
        self._page_spin.blockSignals(True)
        self._page_spin.setMaximum(total_pages)
        self._page_spin.setValue(self._current_page + 1)
        self._page_spin.blockSignals(False)
        self._total_label.setText(f"из {total_pages}")
        self._first_btn.setEnabled(self._current_page > 0)
        self._prev_btn.setEnabled(self._current_page > 0)
        self._next_btn.setEnabled(self._current_page < total_pages - 1)
        self._last_btn.setEnabled(self._current_page < total_pages - 1)

    def go_to_page(self, page: int) -> None:
        self._current_page = max(0, min(page, self._total_pages() - 1))
        self._update_table()

    def _prev_page(self) -> None:
        if self._current_page > 0:
            self._current_page -= 1
            self._update_table()

    def _next_page(self) -> None:
        if self._current_page < self._total_pages() - 1:
            self._current_page += 1
            self._update_table()

    def _go_last(self) -> None:
        self._current_page = self._total_pages() - 1
        self._update_table()

    def _total_pages(self) -> int:
        return max(1, math.ceil(len(self._filtered_data) / self._page_size))

    def _on_spin_changed(self, val: int) -> None:
        self.go_to_page(val - 1)

    def _on_size_changed(self, text: str) -> None:
        self._page_size = int(text)
        self._current_page = 0
        self._update_table()

    @property
    def table(self) -> QTableWidget:
        return self._table

    @property
    def current_page_data(self) -> List[Dict[str, Any]]:
        total = len(self._filtered_data)
        start = self._current_page * self._page_size
        end = min(start + self._page_size, total)
        return self._filtered_data[start:end]

    @property
    def all_filtered_data(self) -> List[Dict[str, Any]]:
        return self._filtered_data
