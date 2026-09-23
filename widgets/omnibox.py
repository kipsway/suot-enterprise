from typing import Any, Dict, List, Optional, Tuple
from difflib import SequenceMatcher

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QKeyEvent, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app_core.design_tokens import RADIUS, palette
from app_core.theme_engine import ThemeEngine

from services.database import DatabaseManager


_JSON_TABLES = [
    "employees",
    "violations",
    "custom_ledger",
    "incidents",
    "ppe",
    "training",
    "permits",
    "companies",
]
_TABLE_LABELS = {
    "employees": "Сотрудники",
    "violations": "Нарушения",
    "custom_ledger": "Журнал",
    "incidents": "Происшествия",
    "ppe": "СИЗ",
    "training": "Обучение",
    "permits": "Наряды-допуски",
    "companies": "Компании",
}


def _fuzzy_score(query: str, text: str) -> float:
    if not query:
        return 0.0
    q = query.lower()
    t = text.lower()
    if q in t:
        return 1.0 + (len(t) - len(q)) / max(len(t), 1)
    return SequenceMatcher(None, q, t).ratio()


class Omnibox(QFrame):
    recordSelected = pyqtSignal(str, int)
    commandTriggered = pyqtSignal(str)
    tabNavigated = pyqtSignal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._parent = parent
        self._results: List[Dict[str, Any]] = []
        self._history: List[str] = []
        self._all_data: Dict[str, List[Dict[str, Any]]] = {}

        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedWidth(520)
        self.setMaximumHeight(460)

        self._build_ui()
        self._preload_data()
        ThemeEngine.on_change(self.update)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        self._input = QLineEdit()
        self._input.setPlaceholderText("Поиск по программе... (/ для команд)")
        self._input.setMinimumHeight(40)
        self._input.textChanged.connect(self._on_text_changed)
        self._input.returnPressed.connect(self._on_enter)
        layout.addWidget(self._input)

        self._results_list = QListWidget()
        self._results_list.setFrameShape(QListWidget.NoFrame)
        self._results_list.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self._results_list, 1)

    def _preload_data(self) -> None:
        db = DatabaseManager()
        for table in _JSON_TABLES:
            records = db.get_json_records(table)
            self._all_data[table] = records

    def show_at(self) -> None:
        if self._parent:
            pos = self._parent.mapToGlobal(self._parent.rect().topLeft())
            self.move(
                pos.x() + self._parent.width() // 2 - self.width() // 2, pos.y() + 60
            )
        self._input.clear()
        self._results_list.clear()
        self.show()
        self._input.setFocus()
        self.raise_()

    def _on_text_changed(self, text: str) -> None:
        self._results_list.clear()
        if not text.strip():
            self._show_history()
            return

        if text.startswith("/"):
            self._search_commands(text[1:])
            return

        self._search_records(text)
        self._search_tabs(text)

    def _show_history(self) -> None:
        for h in self._history[-5:]:
            item = QListWidgetItem(f"🕐 {h}")
            item.setData(Qt.UserRole, ("history", h))
            self._results_list.addItem(item)

    def _search_commands(self, query: str) -> None:
        commands = [
            ("/ai", "Открыть AI чат", "ai"),
            ("/ai-report", "AI-отчёт", "report"),
            ("/settings", "Настройки", "settings"),
            ("/backup", "Создать бэкап", "backup"),
            ("/calc", "Калькулятор рисков", "calc"),
            ("/search", "Расширенный поиск", "search"),
            ("/report", "Глобальный отчёт", "report"),
            ("/export", "Экспорт данных", "export"),
        ]
        q = query.lower()
        for cmd, desc, action in commands:
            if q in cmd.lower() or q in desc.lower():
                item = QListWidgetItem(f"⚡ {cmd} — {desc}")
                item.setData(Qt.UserRole, ("command", action))
                self._results_list.addItem(item)

    def _search_records(self, query: str) -> None:
        results: List[Tuple[float, str, int, str, str]] = []
        for table, records in self._all_data.items():
            for rec in records:
                dj = rec.get("data_json", {})
                rid = rec.get("id", 0)
                best_score = 0.0
                best_field = ""
                best_val = ""
                for k, v in dj.items():
                    score = _fuzzy_score(query, str(v))
                    if score > best_score:
                        best_score = score
                        best_field = k
                        best_val = str(v)[:80]
                if best_score > 0.3:
                    results.append((best_score, table, rid, best_field, best_val))

        results.sort(key=lambda x: -x[0])
        for score, table, rid, field, val in results[:20]:
            label = _TABLE_LABELS.get(table, table)
            text = f"{label} #{rid} — {field}: {val}"
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, ("record", table, rid))
            self._results_list.addItem(item)

    def _search_tabs(self, query: str) -> None:
        tabs = [
            ("tab.dashboard", "Главная"),
            ("tab.employees", "Сотрудники"),
            ("tab.violations", "Нарушения"),
            ("tab.incidents", "Происшествия"),
            ("tab.ppe", "СИЗ"),
            ("tab.training", "Обучение"),
            ("tab.permits", "Наряды-допуски"),
        ]
        q = query.lower()
        for key, label in tabs:
            if q in label.lower():
                item = QListWidgetItem(f"📑 {label}")
                item.setData(Qt.UserRole, ("tab", key))
                self._results_list.addItem(item)

    def _on_enter(self) -> None:
        item = self._results_list.currentItem()
        if item:
            self._activate_item(item)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        self._activate_item(item)

    def _activate_item(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.UserRole)
        if not data:
            return
        kind = data[0]
        text = item.text()

        if text not in self._history:
            self._history.append(text)

        if kind == "record":
            table, rid = data[1], data[2]
            self.recordSelected.emit(table, rid)
        elif kind == "command":
            self.commandTriggered.emit(data[1])
        elif kind == "tab":
            self.tabNavigated.emit(data[1])
        self.close()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key_Escape:
            self.close()
        elif event.key() == Qt.Key_Up:
            idx = self._results_list.currentRow()
            if idx > 0:
                self._results_list.setCurrentRow(idx - 1)
        elif event.key() == Qt.Key_Down:
            idx = self._results_list.currentRow()
            if idx < self._results_list.count() - 1:
                self._results_list.setCurrentRow(idx + 1)
        elif event.key() == Qt.Key_Up or event.key() == Qt.Key_Down:
            pass
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        dark = ThemeEngine._current_theme == "dark"
        pal = palette(dark)
        r = int(RADIUS.lg.replace("px", ""))
        from PyQt5.QtCore import QRectF

        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), r, r)
        bg = QColor(30, 30, 35, 245) if dark else QColor(255, 255, 255, 248)
        p.fillPath(path, bg)
        p.setPen(QPen(QColor(pal.border), 0.5))
        p.drawPath(path)
        p.end()

    def focusOutEvent(self, event) -> None:
        QTimer.singleShot(100, self.close)
        super().focusOutEvent(event)
