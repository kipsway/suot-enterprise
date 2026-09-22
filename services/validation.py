import json
import re
from typing import Any, Dict, List, Optional

from PyQt5.QtWidgets import QComboBox, QSpinBox, QTextEdit

from services.database import DatabaseManager


FIELD_RULES_KEY = "validation_rules_{table}"


def _get_widget_value(w: Any) -> str:
    if isinstance(w, QSpinBox):
        return str(w.value())
    if isinstance(w, QComboBox):
        return w.currentText()
    if isinstance(w, QTextEdit):
        return w.toPlainText().strip()
    return w.text().strip()


class ValidationEngine:
    @staticmethod
    def get_rules(table_name: str) -> Dict[str, Any]:
        db = DatabaseManager()
        raw = db.get_setting(FIELD_RULES_KEY.format(table=table_name), "{}")
        try:
            return json.loads(raw)
        except Exception:
            return {}

    @staticmethod
    def save_rules(table_name: str, rules: Dict[str, Any]) -> None:
        db = DatabaseManager()
        db.set_setting(
            FIELD_RULES_KEY.format(table=table_name),
            json.dumps(rules, ensure_ascii=False),
        )

    @staticmethod
    def validate_field(value: str, rules: Dict[str, Any]) -> Optional[str]:
        if rules.get("required") and not value.strip():
            return rules.get("required_msg", "Обязательное поле")
        if value.strip():
            try:
                min_len = rules.get("min_len")
                if min_len is not None and len(value.strip()) < int(min_len):
                    return rules.get("min_msg", f"Минимум {min_len} символов")
            except (ValueError, TypeError):
                pass
            try:
                max_len = rules.get("max_len")
                if max_len is not None and len(value.strip()) > int(max_len):
                    return rules.get("max_msg", f"Максимум {max_len} символов")
            except (ValueError, TypeError):
                pass
            pattern = rules.get("pattern")
            if pattern:
                try:
                    if not re.match(pattern, value.strip()):
                        return rules.get("pattern_msg", "Неверный формат")
                except re.error:
                    pass
        return None

    @staticmethod
    def validate_record(data: Dict[str, str], table_name: str) -> Dict[str, str]:
        rules = ValidationEngine.get_rules(table_name)
        errors: Dict[str, str] = {}
        for field_name, field_rules in rules.items():
            value = data.get(field_name, "")
            err = ValidationEngine.validate_field(value, field_rules)
            if err:
                errors[field_name] = err
        return errors

    @staticmethod
    def get_column_key(column_name: str) -> str:
        return column_name.lower().replace(" ", "_").replace(".", "")

    @staticmethod
    def validate_dialog(
        dialog_fields: Dict[str, Any], columns: List[Dict[str, Any]], table_name: str
    ) -> Dict[str, str]:
        """Validates dialog fields against rules. Sets Qt property on error widgets.
        Returns dict of {field_name: error_msg}."""
        rules = ValidationEngine.get_rules(table_name)
        errors: Dict[str, str] = {}
        for col in columns:
            name = col["name"]
            if name == "ID" or col.get("type") == "Медиа":
                continue
            w = dialog_fields.get(name)
            if w is None:
                continue
            widget_val = _get_widget_value(w)
            key = ValidationEngine.get_column_key(name)
            field_rules = rules.get(key, {})
            if not field_rules:
                continue
            err = ValidationEngine.validate_field(widget_val, field_rules)
            if err:
                w.setProperty("validationError", True)
                w.setToolTip(err)
                w.style().unpolish(w)
                w.style().polish(w)
                errors[name] = err
            else:
                w.setProperty("validationError", False)
                w.setToolTip("")
                w.style().unpolish(w)
                w.style().polish(w)
        return errors

    @staticmethod
    def get_rules_for_columns(
        table_name: str, columns: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        rules = ValidationEngine.get_rules(table_name)
        result = {}
        for col in columns:
            name = col["name"]
            if name == "ID" or col.get("type") == "Медиа":
                continue
            key = ValidationEngine.get_column_key(name)
            result[name] = rules.get(key, {})
        return result
