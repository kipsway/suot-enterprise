import json
from typing import Any, Dict, List

from PyQt5.QtWidgets import (
    QAction,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QWidget,
)

from app_core.i18n import I18n
from services.database import DatabaseManager


class FilterPresetsWidget(QWidget):
    def __init__(
        self,
        table_name: str,
        search_edit: QLineEdit,
        filter_combo: QComboBox,
        parent: QWidget = None,
    ) -> None:
        super().__init__(parent)
        self._table_name = table_name
        self._search = search_edit
        self._filter = filter_combo
        self.db = DatabaseManager()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._preset_combo = QComboBox()
        self._preset_combo.setMinimumWidth(140)
        self._preset_combo.setPlaceholderText(" " + I18n._("filter.presets"))
        self._preset_combo.currentIndexChanged.connect(self._on_preset_selected)
        layout.addWidget(self._preset_combo)

        self._save_btn = QPushButton("💾")
        self._save_btn.setToolTip(I18n._("filter.save"))
        self._save_btn.setFixedWidth(32)
        self._save_btn.clicked.connect(self._save_preset)
        layout.addWidget(self._save_btn)

        self._refresh_presets()

    def _get_presets_key(self) -> str:
        return f"filter_presets_{self._table_name}"

    def _get_presets(self) -> Dict[str, Any]:
        raw = self.db.get_setting(self._get_presets_key(), "{}")
        try:
            return json.loads(raw)
        except Exception:
            return {}

    def _save_presets(self, presets: Dict[str, Any]) -> None:
        self.db.set_setting(
            self._get_presets_key(), json.dumps(presets, ensure_ascii=False)
        )

    def _refresh_presets(self) -> None:
        self._preset_combo.blockSignals(True)
        self._preset_combo.clear()
        self._preset_combo.addItem(" " + I18n._("filter.presets"), "")
        for name in sorted(self._get_presets().keys()):
            self._preset_combo.addItem(name, name)
        self._preset_combo.blockSignals(False)

    def _on_preset_selected(self, idx: int) -> None:
        name = self._preset_combo.itemData(idx)
        if not name:
            return
        presets = self._get_presets()
        if name not in presets:
            return
        p = presets[name]
        self._search.setText(p.get("search", ""))
        filter_val = p.get("filter", "")
        if filter_val:
            fi = self._filter.findText(filter_val)
            if fi >= 0:
                self._filter.setCurrentIndex(fi)
        self._preset_combo.setCurrentIndex(0)
        menu = QMenu(self)
        load_a = menu.addAction(I18n._("filter.load"))
        del_a = menu.addAction(I18n._("filter.delete"))
        action = menu.exec_(
            self._preset_combo.mapToGlobal(self._preset_combo.rect().bottomLeft())
        )
        if action == del_a:
            reply = QMessageBox.question(
                self,
                I18n._("common.confirm"),
                I18n._("filter.delete_confirm").format(name=name),
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                del presets[name]
                self._save_presets(presets)
                self._refresh_presets()

    def _save_preset(self) -> None:
        name, ok = QInputDialog.getText(
            self, I18n._("filter.save"), I18n._("filter.name_prompt")
        )
        if not ok or not name.strip():
            return
        name = name.strip()
        presets = self._get_presets()
        presets[name] = {
            "search": self._search.text(),
            "filter": self._filter.currentText(),
        }
        self._save_presets(presets)
        self._refresh_presets()
