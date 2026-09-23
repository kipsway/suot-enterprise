from typing import Any, Dict, List, Optional, Set

from PyQt5 import sip
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QTableWidget, QHeaderView

from widgets.column_filters import FilterHeaderView


class ColumnFilterMixin(sip.wrapper):
    def _setup_header_filters(self) -> None:
        if not hasattr(self, "_table") or self._table is None:
            return
        tv = self._table
        old = tv.horizontalHeader()
        if isinstance(old, FilterHeaderView):
            if hasattr(self, "_columns"):
                self._populate_filter_header_values(old)
            return

        fh = FilterHeaderView(Qt.Horizontal, tv)
        fh.filterChanged.connect(self._on_header_filter_changed)

        # 1) Считываем настройки СО СТАРОГО заголовка до его удаления:
        #    QTableWidget.setHorizontalHeader() удаляет прежний QHeaderView.
        old_count = old.count()
        modes = [old.sectionResizeMode(i) for i in range(old_count)]
        stretch_last = old.stretchLastSection()
        sections_movable = old.sectionsMovable()
        sections_clickable = old.sectionsClickable()

        # 2) Прикрепляем новый (получает модель таблицы),
        #    иначе секционные операции на "модель-less" QHeaderView крашат.
        tv.setHorizontalHeader(fh)

        if hasattr(self, "_columns"):
            self._populate_filter_header_values(fh)

        for i in range(min(old_count, len(modes))):
            fh.setSectionResizeMode(i, modes[i])
        fh.setStretchLastSection(stretch_last)
        fh.setSectionsMovable(sections_movable)
        fh.setSectionsClickable(sections_clickable)

        if hasattr(self, "_restore_column_widths"):
            self._restore_column_widths()
        if hasattr(self, "_setup_inline_editing"):
            self._setup_inline_editing()

    def _populate_filter_header_values(self, fh: FilterHeaderView) -> None:
        for i, col in enumerate(getattr(self, "_columns", [])):
            visible = col.get("visible", True)
            if not visible:
                continue
            col_type = col.get("type", "Текст")
            name = col["name"]
            if col_type not in ("Медиа", "Фото"):
                vals = self._collect_column_values(name)
                fh.set_column_values(i, vals)

    def _collect_column_values(self, name: str) -> List[str]:
        seen: Set[str] = set()
        all_records = getattr(self, "_all_records", [])
        for rec in all_records:
            dj = rec if isinstance(rec, dict) else rec.get("data_json", {})
            v = str(dj.get(name, "")).strip()
            if v and v not in seen:
                seen.add(v)
        return sorted(seen)

    def _check_header_filter(self, record: Dict[str, Any]) -> bool:
        fh = self._get_filter_header()
        if fh is None:
            return True
        for i, col in enumerate(getattr(self, "_columns", [])):
            visible = col.get("visible", True)
            if not visible:
                continue
            if fh.has_active_filter(i):
                val = str(record.get(col["name"], "")).strip()
                if not fh.is_value_visible(i, val):
                    return False
        return True

    def _get_filter_header(self) -> Optional[FilterHeaderView]:
        tv = getattr(self, "_table", None)
        if tv is None:
            return None
        h = tv.horizontalHeader()
        if isinstance(h, FilterHeaderView):
            return h
        return None

    def _on_header_filter_changed(self) -> None:
        self._apply_filter()

    def _rebuild_column_values(self) -> None:
        fh = self._get_filter_header()
        if fh is None:
            return
        self._populate_filter_header_values(fh)
