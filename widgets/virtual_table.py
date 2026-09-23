from typing import Any, Callable, Dict, List, Optional

from PyQt5.QtCore import Qt, QAbstractTableModel, QModelIndex, QVariant, QTimer
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QTableView, QHeaderView, QAbstractItemView, QWidget


class VirtualTableModel(QAbstractTableModel):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._data: List[Dict[str, Any]] = []
        self._columns: List[str] = []
        self._extract_fn: Optional[Callable] = None

    def set_columns(self, columns: List[str]) -> None:
        self.beginResetModel()
        self._columns = columns
        self.endResetModel()

    def set_data(
        self, data: List[Dict[str, Any]], extract_fn: Optional[Callable] = None
    ) -> None:
        self.beginResetModel()
        self._data = data
        self._extract_fn = extract_fn
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._data)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._columns)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid() or index.row() >= len(self._data):
            return QVariant()
        rec = self._data[index.row()]
        col_name = self._columns[index.column()]
        if role == Qt.DisplayRole or role == Qt.EditRole:
            if self._extract_fn:
                return self._extract_fn(rec, col_name)
            val = rec.get(col_name, "")
            return val if val is not None else ""
        if role == Qt.TextAlignmentRole:
            return int(Qt.AlignLeft | Qt.AlignVCenter)
        return QVariant()

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole
    ) -> Any:
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            if section < len(self._columns):
                return self._columns[section]
        return QVariant()

    def record_at(self, row: int) -> Optional[Dict[str, Any]]:
        if 0 <= row < len(self._data):
            return self._data[row]
        return None

    def sort(self, column: int, order: Qt.SortOrder = Qt.Ascending) -> None:
        col_name = self._columns[column] if column < len(self._columns) else ""
        if col_name:
            self.beginResetModel()
            reverse = order == Qt.DescendingOrder
            self._data.sort(
                key=lambda r: str(
                    self._extract_fn(r, col_name)
                    if self._extract_fn
                    else r.get(col_name, "")
                ).lower(),
                reverse=reverse,
            )
            self.endResetModel()


class VirtualTableView(QTableView):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._model = VirtualTableModel(self)
        self.setModel(self._model)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setStretchLastSection(True)
        self.setSortingEnabled(True)

    def set_columns(self, columns: List[str]) -> None:
        self._model.set_columns(columns)

    def set_data(
        self, data: List[Dict[str, Any]], extract_fn: Optional[Callable] = None
    ) -> None:
        self._model.set_data(data, extract_fn)
        self.resizeColumnsToContents()

    @property
    def model_(self) -> VirtualTableModel:
        return self._model


class Debouncer:
    def __init__(self, callback: Callable, delay_ms: int = 300) -> None:
        self._callback = callback
        self._delay = delay_ms
        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fire)

    def debounce(self) -> None:
        self._timer.stop()
        self._timer.start(self._delay)

    def _fire(self) -> None:
        self._callback()

    def cancel(self) -> None:
        self._timer.stop()
