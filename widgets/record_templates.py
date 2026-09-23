import json
from typing import Any, Dict, List, Optional

from PyQt5 import sip
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QWidget,
)

from app_core.i18n import I18n
from services.database import DatabaseManager


TEMPLATES_KEY = "record_templates_{table}"


class RecordTemplateMixin(sip.wrapper):
    def _init_templates(self, table_name: str) -> None:
        self._template_table = table_name
        self.db = DatabaseManager()

    def _build_template_bar(self, layout, insert_before: int = -1) -> None:
        bar = QHBoxLayout()
        bar.setSpacing(6)
        bar.addWidget(QLabel("📋 " + I18n._("templates.label") + ":"))

        self._template_combo = QComboBox()
        self._template_combo.setMinimumWidth(180)
        self._template_combo.currentIndexChanged.connect(self._on_template_selected)
        bar.addWidget(self._template_combo)

        save_btn = QPushButton("💾")
        save_btn.setFixedWidth(32)
        save_btn.setToolTip(I18n._("templates.save"))
        save_btn.clicked.connect(self._save_template)
        bar.addWidget(save_btn)

        del_btn = QPushButton("🗑")
        del_btn.setFixedWidth(32)
        del_btn.setToolTip(I18n._("templates.delete"))
        del_btn.clicked.connect(self._delete_template)
        bar.addWidget(del_btn)

        bar.addStretch()

        if insert_before >= 0:
            layout.insertLayout(insert_before, bar)
        else:
            layout.addLayout(bar)

        self._refresh_templates()

    def _get_templates(self) -> Dict[str, Any]:
        raw = self.db.get_setting(
            TEMPLATES_KEY.format(table=self._template_table), "{}"
        )
        try:
            return json.loads(raw)
        except Exception:
            return {}

    def _save_templates(self, templates: Dict[str, Any]) -> None:
        self.db.set_setting(
            TEMPLATES_KEY.format(table=self._template_table),
            json.dumps(templates, ensure_ascii=False),
        )

    def _refresh_templates(self) -> None:
        self._template_combo.blockSignals(True)
        current = self._template_combo.currentText()
        self._template_combo.clear()
        self._template_combo.addItem(" " + I18n._("templates.select"), "")
        names = sorted(self._get_templates().keys())
        for n in names:
            self._template_combo.addItem(n, n)
        idx = self._template_combo.findText(current)
        if idx >= 0:
            self._template_combo.setCurrentIndex(idx)
        self._template_combo.blockSignals(False)

    def _on_template_selected(self, idx: int) -> None:
        name = self._template_combo.itemData(idx)
        if not name:
            return
        templates = self._get_templates()
        if name not in templates:
            return
        data = templates[name]
        for field_name, value in data.items():
            w = self._fields.get(field_name)
            if w is None:
                continue
            if hasattr(w, "setText"):
                w.setText(str(value))
            elif hasattr(w, "setValue"):
                try:
                    w.setValue(int(float(str(value).replace(" ", ""))))
                except Exception:
                    pass
            elif hasattr(w, "setCurrentText"):
                fi = w.findText(str(value))
                if fi >= 0:
                    w.setCurrentIndex(fi)
            elif hasattr(w, "setPlainText"):
                w.setPlainText(str(value))
        self._template_combo.setCurrentIndex(0)

    def _save_template(self) -> None:
        name, ok = QInputDialog.getText(
            self, I18n._("templates.save"), I18n._("templates.name_prompt")
        )
        if not ok or not name.strip():
            return
        name = name.strip()
        data = self._gather_field_values()
        templates = self._get_templates()
        templates[name] = data
        self._save_templates(templates)
        self._refresh_templates()

    def _delete_template(self) -> None:
        idx = self._template_combo.currentIndex()
        name = self._template_combo.itemData(idx)
        if not name:
            return
        reply = QMessageBox.question(
            self,
            I18n._("common.confirm"),
            I18n._("templates.delete_confirm").format(name=name),
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        templates = self._get_templates()
        if name in templates:
            del templates[name]
        self._save_templates(templates)
        self._refresh_templates()

    def _gather_field_values(self) -> Dict[str, str]:
        data: Dict[str, str] = {}
        for name, w in self._fields.items():
            if hasattr(w, "text") and callable(w.text):
                try:
                    data[name] = w.text().strip()
                except Exception:
                    pass
            elif hasattr(w, "currentText"):
                data[name] = w.currentText()
            elif hasattr(w, "toPlainText"):
                data[name] = w.toPlainText().strip()
            elif hasattr(w, "value"):
                try:
                    data[name] = str(w.value())
                except Exception:
                    pass
        return data
