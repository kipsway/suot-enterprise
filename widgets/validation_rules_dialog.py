from typing import Any, Dict, List

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app_core.i18n import I18n
from services.validation import ValidationEngine


JSON_TABLES = [
    ("employees", "Сотрудники"),
    ("violations", "Нарушения"),
    ("custom_ledger", "Журнал"),
    ("incidents", "Происшествия"),
    ("ppe", "СИЗ"),
    ("training", "Обучение"),
    ("permits", "Наряды-допуски"),
]


class ValidationRulesDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(I18n._("validation.title"))
        self.setMinimumSize(700, 550)
        self.resize(800, 600)
        self._current_table = "employees"
        self._editors: Dict[str, Dict[str, Any]] = {}
        self._build_ui()
        self._load_rules()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        heading = QLabel(I18n._("validation.title"))
        heading.setProperty("heading", True)
        layout.addWidget(heading)

        sel_layout = QHBoxLayout()
        sel_layout.addWidget(QLabel(I18n._("validation.table") + ":"))
        self._table_combo = QComboBox()
        for tbl_id, tbl_name in JSON_TABLES:
            self._table_combo.addItem(tbl_name, tbl_id)
        self._table_combo.currentIndexChanged.connect(self._on_table_changed)
        sel_layout.addWidget(self._table_combo, 1)
        layout.addLayout(sel_layout)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        self._container = QWidget()
        self._form = QFormLayout(self._container)
        self._form.setSpacing(8)
        self._form.setLabelAlignment(Qt.AlignRight)
        scroll.setWidget(self._container)
        layout.addWidget(scroll, 1)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        save_btn = QPushButton(I18n._("common.save"))
        save_btn.clicked.connect(self._save_rules)
        btn_layout.addWidget(save_btn)
        cancel_btn = QPushButton(I18n._("common.cancel"))
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def _get_column_defs(self, table_id: str) -> List[Dict[str, str]]:
        from services.database import DatabaseManager

        db = DatabaseManager()
        return db.get_columns_config(table_id)

    def _on_table_changed(self) -> None:
        self._current_table = self._table_combo.currentData()
        self._load_rules()

    def _load_rules(self) -> None:
        rules = ValidationEngine.get_rules(self._current_table)
        self._clear_form()
        columns = self._get_column_defs(self._current_table)
        for col in columns:
            name = col["name"]
            col_type = col.get("type", "Текст")
            if name == "ID" or col_type == "Медиа":
                continue
            key = ValidationEngine.get_column_key(name)
            field_rules = rules.get(key, {})
            self._add_field_row(name, col_type, field_rules)

    def _clear_form(self) -> None:
        while self._form.count():
            item = self._form.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._editors.clear()

    def _add_field_row(self, name: str, col_type: str, rules: Dict[str, Any]) -> None:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        editors: Dict[str, Any] = {}

        cb = QCheckBox(I18n._("validation.required"))
        cb.setChecked(rules.get("required", False))
        layout.addWidget(cb)
        editors["required"] = cb

        if col_type == "Текст":
            hl = QHBoxLayout()
            hl.addWidget(QLabel(I18n._("validation.min_len")))
            min_spin = QSpinBox()
            min_spin.setRange(0, 1000)
            min_spin.setValue(rules.get("min_len", 0))
            hl.addWidget(min_spin)
            hl.addWidget(QLabel(I18n._("validation.max_len")))
            max_spin = QSpinBox()
            max_spin.setRange(0, 10000)
            max_spin.setValue(rules.get("max_len", 0))
            hl.addWidget(max_spin)
            hl.addStretch()
            layout.addLayout(hl)
            editors["min_len"] = min_spin
            editors["max_len"] = max_spin
        else:
            min_spin = QSpinBox()
            max_spin = QSpinBox()
            editors["min_len"] = min_spin
            editors["max_len"] = max_spin

        pl = QHBoxLayout()
        pl.addWidget(QLabel(I18n._("validation.pattern")))
        pattern_edit = QLineEdit()
        pattern_edit.setText(rules.get("pattern", ""))
        pattern_edit.setPlaceholderText(I18n._("validation.pattern_hint"))
        pl.addWidget(pattern_edit, 1)
        layout.addLayout(pl)
        editors["pattern"] = pattern_edit
        editors["pattern_msg"] = QLineEdit(rules.get("pattern_msg", ""))
        editors["pattern_msg"].setPlaceholderText(I18n._("validation.pattern_msg_hint"))
        layout.addWidget(editors["pattern_msg"])

        self._form.addRow(f"{name}:", container)
        self._editors[name] = editors

    def _save_rules(self) -> None:
        rules: Dict[str, Any] = {}
        for field_name, editors in self._editors.items():
            key = ValidationEngine.get_column_key(field_name)
            rule: Dict[str, Any] = {}
            if editors["required"].isChecked():
                rule["required"] = True
                rule["required_msg"] = f'Поле "{field_name}" обязательно'
            min_v = editors["min_len"].value()
            max_v = editors["max_len"].value()
            if min_v > 0:
                rule["min_len"] = min_v
                rule["min_msg"] = f"Минимум {min_v} символов"
            if max_v > 0:
                rule["max_len"] = max_v
                rule["max_msg"] = f"Максимум {max_v} символов"
            pattern = editors["pattern"].text().strip()
            if pattern:
                rule["pattern"] = pattern
                msg = editors["pattern_msg"].text().strip()
                if msg:
                    rule["pattern_msg"] = msg
                else:
                    rule["pattern_msg"] = "Неверный формат"
            if rule:
                rules[key] = rule
        ValidationEngine.save_rules(self._current_table, rules)
        self.accept()
