import traceback
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QAbstractItemView
from modules.textbook import auto_format_date


class InlineEditMixin:
    TABLE_NAME: str = ""
    _saving: bool = False

    def _setup_inline_editing(self) -> None:
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.itemDoubleClicked.connect(self._on_inline_double_click)
        self._table.itemChanged.connect(self._on_inline_changed)

    def _on_inline_double_click(self, item) -> None:
        row = item.row()
        col = item.column()
        if row < 0 or row >= len(self._records):
            return
        if col < 0 or col >= len(self._columns):
            return
        name = self._columns[col]["name"]
        typ = self._columns[col].get("type", "")
        if name == "ID" or typ in ("Медиа", "Фото"):
            self._edit_selected()
            return
        if "date" in name.lower() or "срок" in name.lower() or "дата" in name.lower() or "годен" in name.lower():
            self._edit_selected()
            return
        if not self._table.editItem(item):
            self._edit_selected()

    def _on_inline_changed(self, item) -> None:
        if getattr(self, '_saving', False):
            return
        row = item.row()
        col = item.column()
        if row < 0 or row >= len(self._records) or col < 0 or col >= len(self._columns):
            return
        rec = self._records[row]
        dj = rec.get("data_json", {})
        name = self._columns[col]["name"]
        typ = self._columns[col].get("type", "")
        if name == "ID" or typ in ("Медиа", "Фото"):
            return
        new_value = item.text().strip()
        formatted = auto_format_date(new_value)
        self._saving = True
        if formatted != new_value:
            item.setText(formatted)
        dj[name] = formatted
        try:
            self.db.save_json_record(
                self.TABLE_NAME, rec["id"], dj, user_id=self._user_id
            )
        except Exception:
            traceback.print_exc()
        self._saving = False
