import re
from typing import Any, Dict, List, Tuple, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QKeyEvent
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QLineEdit, QTextEdit, QPushButton, QTableWidget,
                             QTableWidgetItem, QHeaderView, QAbstractItemView,
                             QInputDialog, QMessageBox, QWidget)

from app_core.i18n import I18n
from app_core.utils import wrap_table_with_glow
from services.database import DatabaseManager
from widgets.toast import ToastNotification


class TextbookEngine:
    _rules: Dict[str, str] = {}
    _enabled: bool = True
    _manual_mode: bool = False

    @classmethod
    def load(cls) -> None:
        try:
            db = DatabaseManager()
            cls._rules = db.get_textbook()
        except Exception:
            cls._rules = {}

    @classmethod
    def set_enabled(cls, enabled: bool) -> None:
        cls._enabled = enabled

    @classmethod
    def is_enabled(cls) -> bool:
        return cls._enabled

    @classmethod
    def set_manual_mode(cls, manual: bool) -> None:
        cls._manual_mode = manual

    @classmethod
    def is_manual(cls) -> bool:
        return cls._manual_mode

    @classmethod
    def process(cls, text: str) -> Tuple[str, bool]:
        if not cls._enabled or cls._manual_mode:
            return text, False
        lower = text.lower().strip()
        if lower in cls._rules:
            return cls._rules[lower], True
        return text, False

    @classmethod
    def manual_replace(cls, text: str) -> Tuple[str, bool]:
        lower = text.lower().strip()
        if lower in cls._rules:
            return cls._rules[lower], True
        return text, False

    @classmethod
    def get_rules(cls) -> Dict[str, str]:
        return dict(cls._rules)

    @classmethod
    def add_rule(cls, short_code: str, full_text: str) -> bool:
        try:
            db = DatabaseManager()
            r = db.save_textbook_entry(short_code, full_text)
            cls._rules[short_code] = full_text
            return True
        except Exception:
            return False

    @classmethod
    def delete_rule(cls, short_code: str) -> bool:
        try:
            db = DatabaseManager()
            r = db.delete_textbook_entry(short_code)
            cls._rules.pop(short_code, None)
            return True
        except Exception:
            return False


class TextbookLineEdit(QLineEdit):
    def __init__(self, parent: Optional[QWidget] = None,
                 placeholder: str = "") -> None:
        super().__init__(parent)
        if placeholder:
            self.setPlaceholderText(placeholder)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        super().keyPressEvent(event)
        if event.key() in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter):
            if not TextbookEngine.is_manual():
                text = self.text()
                words = text.split(" ")
                if words:
                    last_word = words[-1]
                    replacement, replaced = TextbookEngine.process(last_word)
                    if replaced:
                        words[-1] = replacement
                        self.setText(" ".join(words))
                        self.setCursorPosition(len(self.text()))


class TextbookTextEdit(QTextEdit):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        super().keyPressEvent(event)
        if event.key() in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter):
            if not TextbookEngine.is_manual():
                text = self.toPlainText()
                words = text.split(" ")
                if words:
                    last_word = words[-1].strip()
                    replacement, replaced = TextbookEngine.process(last_word)
                    if replaced:
                        words[-1] = replacement
                        self.setPlainText(" ".join(words).replace("\n ", "\n").replace(" \n", "\n"))
                        cursor = self.textCursor()
                        cursor.movePosition(cursor.End)
                        self.setTextCursor(cursor)


class TextbookDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.db = DatabaseManager()
        self.setWindowTitle(I18n._("textbook.edit"))
        self.setMinimumSize(600, 450)
        self.resize(700, 500)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        heading = QLabel(I18n._("textbook.auto_replace"))
        heading.setProperty("heading", True)
        layout.addWidget(heading)

        hint = QLabel(I18n._("textbook.trigger_hint"))
        hint.setStyleSheet("font-size: 12px;")
        layout.addWidget(hint)

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText(I18n._("common.search_hint"))
        self._search_edit.textChanged.connect(self._filter_rules)
        layout.addWidget(self._search_edit)

        self._table = QTableWidget()
        self._table.setColumnCount(2)
        self._table.setHorizontalHeaderLabels([
            I18n._("textbook.shortcode"), I18n._("textbook.fulltext")])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        layout.addWidget(wrap_table_with_glow(self._table, self))

        btn_layout = QHBoxLayout()
        add_btn = QPushButton(I18n._("textbook.add"))
        add_btn.clicked.connect(self._add_rule)
        btn_layout.addWidget(add_btn)
        del_btn = QPushButton(I18n._("textbook.delete"))
        del_btn.setProperty("danger", True)
        del_btn.clicked.connect(self._delete_rule)
        btn_layout.addWidget(del_btn)
        btn_layout.addStretch()
        close_btn = QPushButton(I18n._("common.close"))
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

        self._load_rules()

        self._all_rules: List[Tuple[str, str]] = []

    def _filter_rules(self) -> None:
        query = self._search_edit.text().strip().lower()
        rules = self._all_rules
        if query:
            rules = [(c, t) for c, t in rules
                     if query in c.lower() or query in t.lower()]
        self._table.setRowCount(len(rules))
        for i, (code, text) in enumerate(rules):
            code_item = QTableWidgetItem(code)
            code_item.setFlags(code_item.flags() & ~Qt.ItemIsEditable)
            self._table.setItem(i, 0, code_item)
            text_item = QTableWidgetItem(text[:80] + ("..." if len(text) > 80 else ""))
            text_item.setFlags(text_item.flags() & ~Qt.ItemIsEditable)
            text_item.setToolTip(text)
            self._table.setItem(i, 1, text_item)
        self._table.resizeColumnsToContents()

    def _load_rules(self) -> None:
        self._all_rules = sorted(TextbookEngine.get_rules().items())
        self._filter_rules()

    def _add_rule(self) -> None:
        code, ok = QInputDialog.getText(
            self, I18n._("textbook.add"), I18n._("textbook.shortcode"))
        if not ok or not code:
            return
        text, ok2 = QInputDialog.getMultiLineText(
            self, I18n._("textbook.add"), I18n._("textbook.fulltext"))
        if ok2 and text:
            TextbookEngine.add_rule(code.strip(), text.strip())
            self._load_rules()
            ToastNotification.notify(I18n._("common.success"), "success", 3000)

    def _delete_rule(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            return
        code = self._table.item(row, 0).text()
        reply = QMessageBox.question(
            self, I18n._("common.confirm"),
            f"{I18n._('common.delete')}: '{code}'?",
            QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            TextbookEngine.delete_rule(code)
            self._load_rules()
            ToastNotification.notify(I18n._("toast.delete_success"), "success", 3000)


DATE_PATTERN = re.compile(r"(\d{2})-(\d{2})-(\d{4})")


def auto_format_date(text: str) -> str:
    def _replacer(m: re.Match) -> str:
        month, day, year = m.group(1), m.group(2), m.group(3)
        return f"{day}.{month}.{year}"
    return DATE_PATTERN.sub(_replacer, text)


class DateAwareLineEdit(QLineEdit):
    def __init__(self, parent: Optional[QWidget] = None,
                 placeholder: str = "ДД.ММ.ГГГГ") -> None:
        super().__init__(parent)
        self.setPlaceholderText(placeholder)

    def focusOutEvent(self, event: Any) -> None:
        old = self.text()
        formatted = auto_format_date(old)
        if formatted != old:
            self.setText(formatted)
        super().focusOutEvent(event)
