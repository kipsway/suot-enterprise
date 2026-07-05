from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QLineEdit, QTextEdit, QPushButton, QListWidget,
                             QListWidgetItem, QMessageBox, QWidget)

from app_core.i18n import I18n
from services.database import DatabaseManager
from widgets.toast import ToastNotification


class NotesDialog(QDialog):
    def __init__(self, entity_type: str = "global", entity_id: int = 0,
                 entity_name: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.db = DatabaseManager()
        self._entity_type = entity_type
        self._entity_id = entity_id
        self.setWindowTitle(f"{I18n._('notes.title')} — {entity_name}" if entity_name
                            else I18n._("notes.title"))
        self.setMinimumSize(600, 450)
        self.resize(700, 500)
        self._build_ui()
        self._load_notes()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        heading = QLabel(I18n._("notes.title"))
        heading.setProperty("heading", True)
        layout.addWidget(heading)

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText(I18n._("common.search_hint"))
        self._search_edit.textChanged.connect(self._filter_notes)
        layout.addWidget(self._search_edit)

        self._list = QListWidget()
        self._list.itemClicked.connect(self._on_note_selected)
        layout.addWidget(self._list)

        self._editor = QTextEdit()
        self._editor.setPlaceholderText(I18n._("notes.placeholder"))
        self._editor.setMinimumHeight(120)
        layout.addWidget(self._editor)

        btn_layout = QHBoxLayout()
        self._add_btn = QPushButton(I18n._("notes.add"))
        self._add_btn.setProperty("success", True)
        self._add_btn.clicked.connect(self._add_note)
        btn_layout.addWidget(self._add_btn)
        self._save_btn = QPushButton(I18n._("common.save"))
        self._save_btn.clicked.connect(self._save_note)
        btn_layout.addWidget(self._save_btn)
        self._delete_btn = QPushButton(I18n._("notes.delete"))
        self._delete_btn.setProperty("danger", True)
        self._delete_btn.clicked.connect(self._delete_note)
        btn_layout.addWidget(self._delete_btn)
        btn_layout.addStretch()
        self._close_btn = QPushButton(I18n._("common.close"))
        self._close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self._close_btn)
        layout.addLayout(btn_layout)

        self._current_note_id: Optional[int] = None

    def _filter_notes(self) -> None:
        query = self._search_edit.text().strip().lower()
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item:
                item.setHidden(bool(query) and query not in item.text().lower())

    def _load_notes(self) -> None:
        self._list.clear()
        notes = self.db.get_notes(self._entity_type, self._entity_id)
        for n in notes:
            content = n.get("content", "")
            preview = content[:80].replace("<", "&lt;").replace(">", "&gt;").replace("\n", " ") if content else ""
            title = n.get("title") or I18n._("notes.title") + f" #{n['id']}"
            item = QListWidgetItem(f"{title} — {preview}" if preview else title)
            item.setData(Qt.UserRole, n["id"])
            item.setData(Qt.UserRole + 1, content)
            item.setToolTip(content[:200].replace("<", "&lt;").replace(">", "&gt;") if content else "")
            self._list.addItem(item)

    def _on_note_selected(self, item: QListWidgetItem) -> None:
        self._current_note_id = item.data(Qt.UserRole)
        content = item.data(Qt.UserRole + 1) or ""
        self._editor.setHtml(content)

    def _add_note(self) -> None:
        self._current_note_id = None
        self._editor.clear()
        self._editor.setFocus()

    def _save_note(self) -> None:
        content = self._editor.toHtml() if self._editor.toPlainText().strip() else ""
        if not content:
            return
        title = I18n._("notes.title") + f" #{self._current_note_id or ''}"
        try:
            self.db.save_note(self._entity_type, self._entity_id,
                              title, content, self._current_note_id or 0)
            self._load_notes()
            ToastNotification.notify(I18n._("common.success"), "success", 3000)
        except Exception:
            ToastNotification.notify(I18n._("error.generic"), "error", 5000)

    def _delete_note(self) -> None:
        if not self._current_note_id:
            return
        reply = QMessageBox.question(self, I18n._("common.confirm"),
                                     I18n._("notes.delete") + "?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.db.delete_note(self._current_note_id)
            self._current_note_id = None
            self._editor.clear()
            self._load_notes()
            ToastNotification.notify(I18n._("toast.delete_success"), "success", 3000)
