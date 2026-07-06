import json
from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QHeaderView


class ColumnWidthMixin:
    TABLE_NAME: str = ""
    _widths_loaded: bool = False

    def _setup_column_widths(self) -> None:
        self._widths_loaded = False
        hdr = self._table.horizontalHeader()
        hdr.sectionResized.connect(self._on_section_resized)

    def _save_column_widths(self) -> None:
        if not self.TABLE_NAME:
            return
        widths = {}
        hdr = self._table.horizontalHeader()
        for i in range(hdr.count()):
            logical = hdr.logicalIndex(i)
            if logical >= 0:
                widths[str(logical)] = hdr.sectionSize(logical)
        self.db.set_setting(f"col_widths_{self.TABLE_NAME}", json.dumps(widths, ensure_ascii=False))

    def _restore_column_widths(self) -> None:
        if not self.TABLE_NAME:
            return
        raw = self.db.get_setting(f"col_widths_{self.TABLE_NAME}", "")
        if not raw:
            return
        try:
            widths = json.loads(raw)
        except Exception:
            return
        hdr = self._table.horizontalHeader()
        for logical_str, w in widths.items():
            logical = int(logical_str)
            if 0 <= logical < hdr.count():
                hdr.resizeSection(logical, int(w))
        self._widths_loaded = True

    def _on_section_resized(self, logical: int, old_size: int, new_size: int) -> None:
        if self._widths_loaded:
            self._save_column_widths()
