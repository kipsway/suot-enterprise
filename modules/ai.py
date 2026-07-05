import json, os, sys
import urllib.request as _urllib_request
import urllib.error as _urllib_error
from typing import Any, Dict, List, Optional
from PyQt5.QtCore import Qt, QTimer, QObject, QEvent
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (QApplication, QDialog, QWidget, QFrame,
    QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QSlider, QTextEdit, QScrollArea,
    QFileDialog, QMessageBox, QSizePolicy)

from app_core.i18n import I18n
from app_core.utils import fade_in_widget
from services.database import DatabaseManager
from modules.print_engine import PrintEngine
from widgets.toast import ToastNotification


class AIEngine:
    DEFAULT_URL = "https://api.openai.com/v1"
    DEFAULT_MODEL = "gpt-3.5-turbo"

    def __init__(self) -> None:
        self.db = DatabaseManager()
        self.provider: str = self.db.get_ai_setting("provider", "openai")
        self.api_url: str = self.db.get_ai_setting("api_url", self.DEFAULT_URL)
        self.api_key: str = self.db.get_ai_setting("api_key", "")
        self.model: str = self.db.get_ai_setting("model", self.DEFAULT_MODEL)
        self.mode: str = self.db.get_ai_setting("mode", "chat")
        self.temperature: float = float(self.db.get_ai_setting("temperature", "0.7"))

    def save_settings(self) -> None:
        self.db.set_ai_setting("provider", self.provider)
        self.db.set_ai_setting("api_url", self.api_url)
        self.db.set_ai_setting("api_key", self.api_key)
        self.db.set_ai_setting("model", self.model)
        self.db.set_ai_setting("mode", self.mode)
        self.db.set_ai_setting("temperature", str(self.temperature))

    @staticmethod
    def build_system_prompt(db_schema: str = "") -> str:
        schema_section = f"\n\nActual database schema (auto-detected):\n{db_schema}" if db_schema else ""
        return (
            "You are an AI assistant for an Occupational Safety and Health (OSH) "
            "management system called 'СУОТ Enterprise'. "
            "Your tasks: answer questions, search data, analyze statistics, "
            "generate reports, and modify records (only with user confirmation).\n\n"
            "Database schema:\n"
            "1. employees - employee records (fields: ФИО, Должность, Подразделение, "
            "Фирма, Телефон, Дата медосмотра, Квалификация, Дата проведения, Статус)\n"
            "2. violations - safety violations (fields: Дата, Фирма, Подразделение, "
            "Категория риска, Описание, Ответственный, Срок устранения, Штраф, Статус)\n"
            "3. companies - organizations (fields: name, address, contact)\n"
            "4. custom_ledger - custom records (variable fields)\n"
            "5. notes - text notes\n\n"
            "When in AGENT mode, respond with a JSON object:\n"
            "{\"thought\": \"...\", \"action\": \"action_name\", \"params\": {...}}\n\n"
            "Available actions:\n"
            "- respond: just reply to user (params: {\"message\": \"...\"})\n"
            "- search_db: search across tables (params: {\"query\": \"...\", \"table\": \"...\"})\n"
            "- get_stats: get summary statistics\n"
            "- add_record: add a new record (params: {\"table\": \"...\", \"data\": {\"field1\": \"value1\", ...}})\n"
            "- modify_record: modify a record (params: {\"table\": \"...\", \"id\": ..., "
            "\"field\": \"...\", \"value\": \"...\"})\n"
            "- delete_record: delete a record (params: {\"table\": \"...\", \"id\": ...})\n"
            "- create_report: generate company report (params: {\"company\": \"...\"})\n"
            "- rename_column: rename a column (params: {\"table\": \"...\", \"old\": \"...\", "
            "\"new\": \"...\"})\n"
            "- add_note: add a note (params: {\"entity_type\": \"...\", \"entity_id\": ..., \"text\": \"...\"})\n"
            "For 'modify_record', 'add_record', 'delete_record', 'rename_column' and 'add_note', "
            "user confirmation is required."
            + schema_section
        )

    def _build_messages(self, history: List[Dict[str, str]],
                        query: str, schema: str) -> List[Dict[str, str]]:
        msgs = [{"role": "system", "content": self.build_system_prompt(schema)}]
        for h in history:
            msgs.append(h)
        msgs.append({"role": "user", "content": query})
        return msgs

    def send_request(self, history: List[Dict[str, str]],
                     query: str, schema: str = "") -> Optional[str]:
        local_noauth = any(x in self.api_url.lower() for x in ["localhost", "127.0.0.1", "ollama"])
        if not self.api_key and not local_noauth:
            return None
        try:
            provider = self.provider.lower()
            messages = self._build_messages(history, query, schema)

            if provider == "anthropic":
                url = f"{self.api_url.rstrip('/')}/messages"
                payload = json.dumps({
                    "model": self.model,
                    "max_tokens": 4000,
                    "messages": [{"role": m["role"], "content": m["content"]}
                                 for m in messages if m["role"] != "system"],
                    "system": next((m["content"] for m in messages if m["role"] == "system"), ""),
                }).encode("utf-8")
                headers = {
                    "Content-Type": "application/json",
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                }
                req = _urllib_request.Request(url, data=payload, headers=headers)
                resp = _urllib_request.urlopen(req, timeout=90)
                data = json.loads(resp.read().decode("utf-8"))
                if "content" in data and len(data["content"]) > 0:
                    return "".join(b.get("text", "") for b in data["content"] if b.get("type") == "text")
                return json.dumps(data, ensure_ascii=False)[:500]

            if provider == "gemini":
                model_name = self.model.split("/")[-1] if "/" in self.model else self.model
                url = f"{self.api_url.rstrip('/')}/models/{model_name}:generateContent"
                gemini_msgs = []
                for m in messages:
                    role = "user" if m["role"] in ("user", "system") else "model"
                    gemini_msgs.append({"role": role, "parts": [{"text": m["content"]}]})
                payload = json.dumps({"contents": gemini_msgs}).encode("utf-8")
                headers = {"Content-Type": "application/json"}
                if self.api_key:
                    url += f"?key={self.api_key}"
                req = _urllib_request.Request(url, data=payload, headers=headers)
                resp = _urllib_request.urlopen(req, timeout=90)
                data = json.loads(resp.read().decode("utf-8"))
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    return "".join(p.get("text", "") for p in parts)
                return json.dumps(data, ensure_ascii=False)[:500]

            # OpenAI-compatible (default)
            url = f"{self.api_url.rstrip('/')}/chat/completions"
            payload = json.dumps({
                "model": self.model,
                "messages": messages,
                "temperature": self.temperature,
                "max_tokens": 4000,
            }).encode("utf-8")
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            req = _urllib_request.Request(url, data=payload, headers=headers)
            resp = _urllib_request.urlopen(req, timeout=90)
            data = json.loads(resp.read().decode("utf-8"))
            if "choices" in data and len(data["choices"]) > 0:
                return data["choices"][0]["message"]["content"]
            return f"Unexpected response: {json.dumps(data, ensure_ascii=False)[:300]}"
        except _urllib_error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")[:500]
            return f"HTTP Error {e.code}: {e.reason} — {body}"
        except _urllib_error.URLError as e:
            return f"Connection Error: {e.reason}"
        except Exception as e:
            import traceback
            return f"Error: {str(e)}\n{traceback.format_exc()[:300]}"

    def parse_agent_response(self, response: str) -> Dict[str, Any]:
        try:
            cleaned = response.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.strip("`")
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:]
            return json.loads(cleaned)
        except Exception:
            return {"thought": "", "action": "respond",
                    "params": {"message": response}}

    def execute_action(self, action: str, params: Dict[str, Any]) -> str:
        try:
            if action == "respond":
                return params.get("message", "")
            elif action == "search_db":
                query = params.get("query", "")
                table = params.get("table", "")
                return self._action_search(query, table)
            elif action == "get_stats":
                return self._action_stats()
            elif action == "add_record":
                return self._action_add(params)
            elif action == "modify_record":
                return self._action_modify(params)
            elif action == "delete_record":
                return self._action_delete(params)
            elif action == "create_report":
                company = params.get("company", "")
                return self._action_report(company)
            elif action == "rename_column":
                return self._action_rename(params)
            elif action == "add_note":
                return self._action_add_note(params)
            return f"Unknown action: {action}"
        except Exception as e:
            return f"Action error: {e}"

    def _action_search(self, query: str, table: str) -> str:
        results: List[str] = []
        tables_to_search = [table] if table else ["employees", "violations",
                                                    "custom_ledger", "companies"]
        for t in tables_to_search:
            if t == "companies":
                rows = self.db.fetch_all(
                    "SELECT id, name, address, contact FROM companies")
            else:
                rows = self.db.get_json_records(t)
            for r in rows:
                dj = r.get("data_json", {}) if t != "companies" else r
                for val in dj.values():
                    if isinstance(val, str) and query.lower() in val.lower():
                        label = r.get("ФИО", r.get("name", r.get("Описание", f"#{r['id']}")))
                        results.append(f"[{t}] {label}: id={r['id']}")
                        break
        if not results:
            return "No results found."
        return "Found:\n" + "\n".join(results[:20])

    def _action_stats(self) -> str:
        s = self.db.get_statistics()
        return (
            f"Employees: {s['employees_total']}\n"
            f"Violations: {s['violations_total']}\n"
            f"Companies: {s['companies_total']}\n"
            f"Overdue: {s['overdue_total']}\n"
            f"Total Fines: {s['fines_total']:,.0f} RUB")

    def _action_add(self, params: Dict[str, Any]) -> str:
        table = params.get("table", "")
        data = params.get("data", {})
        if not table or not data:
            return "Error: 'table' and 'data' params required"
        cols = self.db.get_columns_config(table)
        record: Dict[str, Any] = {}
        for c in cols:
            if c["name"] in data:
                record[c["name"]] = data[c["name"]]
            elif c["type"] == "Статус":
                record[c["name"]] = "Активно"
            elif c["type"] == "Медиа":
                record[c["name"]] = []
            else:
                record[c["name"]] = ""
        rec_id = self.db.save_json_record(table, 0, record)
        self.db.log_event(f"AI added record #{rec_id} to {table}", "INFO", {"table": table})
        return f"Record #{rec_id} added to {table}."

    def _action_modify(self, params: Dict[str, Any]) -> str:
        table = params.get("table", "")
        rec_id = params.get("id", 0)
        field = params.get("field", "")
        value = params.get("value", "")
        if not table or not rec_id or not field:
            return "Error: 'table', 'id', and 'field' params required"
        records = self.db.get_json_records(table)
        for r in records:
            if r["id"] == rec_id:
                data = r.get("data_json", {})
                data[field] = value
                r["data_json"] = data
                self.db.save_json_record(table, rec_id, data)
                self.db.log_event(f"AI modified record #{rec_id} in {table}: {field} = {value}",
                                  "INFO", {"table": table})
                return f"Record #{rec_id} updated: {field} = {value}"
        return f"Record #{rec_id} not found in {table}."

    def _action_delete(self, params: Dict[str, Any]) -> str:
        table = params.get("table", "")
        rec_id = params.get("id", 0)
        if not table or not rec_id:
            return "Error: 'table' and 'id' params required"
        records = self.db.get_json_records(table)
        for r in records:
            if r["id"] == rec_id:
                self.db.execute("DELETE FROM json_data WHERE id = ? AND category = ?",
                                (rec_id, table))
                self.db.conn.commit()
                self.db.log_event(f"AI deleted record #{rec_id} from {table}",
                                  "INFO", {"table": table})
                return f"Record #{rec_id} deleted from {table}."
        return f"Record #{rec_id} not found in {table}."

    def _action_report(self, company: str) -> str:
        html = PrintEngine.render_report(company, True, True, True)
        return f"Report generated for {company or 'all companies'}."

    def _action_rename(self, params: Dict[str, Any]) -> str:
        table = params.get("table", "")
        old_name = params.get("old", "")
        new_name = params.get("new", "")
        if not table or not old_name or not new_name:
            return "Error: 'table', 'old', and 'new' params required"
        self.db.execute(
            "UPDATE columns_config SET name = ? WHERE category = ? AND name = ?",
            (new_name, table, old_name))
        self.db.conn.commit()
        self.db.log_event(f"AI renamed column '{old_name}' to '{new_name}' in {table}",
                          "INFO", {"table": table})
        return f"Column '{old_name}' renamed to '{new_name}' in {table}."

    def _action_add_note(self, params: Dict[str, Any]) -> str:
        entity_type = params.get("entity_type", "global")
        entity_id = params.get("entity_id", 0)
        text = params.get("text", "")
        if not text:
            return "Error: 'text' param required"
        note_id = self.db.save_note(entity_type=entity_type, entity_id=entity_id,
                                     title=text[:50], content=text)
        self.db.log_event(f"AI added note #{note_id} for {entity_type}:{entity_id}",
                          "INFO", {"entity_type": entity_type})
        return f"Note #{note_id} added for {entity_type}:{entity_id}."


class AIChatDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.db = DatabaseManager()
        self.engine = AIEngine()
        self._history: List[Dict[str, str]] = []
        self._attachment_path: str = ""
        self.setWindowTitle(I18n._("ai.title"))
        self.setMinimumSize(700, 550)
        self.resize(800, 600)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QFrame()
        header.setStyleSheet("background: transparent; padding: 12px 16px;")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(16, 8, 16, 8)

        heading = QLabel("🤖 " + I18n._("ai.title"))
        heading.setProperty("heading", True)
        hl.addWidget(heading)
        hl.addStretch()

        self._config_toggle = QPushButton("⚙")
        self._config_toggle.setProperty("flat", True)
        self._config_toggle.setFixedSize(32, 32)
        self._config_toggle.setCheckable(True)
        self._config_toggle.toggled.connect(self._toggle_config)
        hl.addWidget(self._config_toggle)

        self._clear_btn = QPushButton(I18n._("ai.clear"))
        self._clear_btn.setProperty("flat", True)
        self._clear_btn.clicked.connect(self._clear_history)
        hl.addWidget(self._clear_btn)

        close_btn = QPushButton("✕")
        close_btn.setProperty("flat", True)
        close_btn.setFixedSize(32, 32)
        close_btn.clicked.connect(self.accept)
        hl.addWidget(close_btn)

        layout.addWidget(header)

        # Config panel (collapsible)
        self._config_panel = QFrame()
        self._config_panel.setProperty("card", True)
        self._config_panel.setVisible(False)
        cl = QFormLayout(self._config_panel)
        cl.setContentsMargins(16, 12, 16, 12)
        cl.setSpacing(8)

        self._provider_combo = QComboBox()
        self._provider_combo.setEditable(True)
        self._provider_combo.setMinimumHeight(36)
        self._provider_combo.addItem("OpenAI", "openai")
        self._provider_combo.addItem("OpenRouter", "openrouter")
        self._provider_combo.addItem("DeepSeek", "deepseek")
        self._provider_combo.addItem("Anthropic", "anthropic")
        self._provider_combo.addItem("Google Gemini", "gemini")
        self._provider_combo.addItem("Groq", "groq")
        self._provider_combo.addItem("Локальный (Local)", "local")
        self._provider_combo.addItem("Пользовательский (Custom)", "custom")
        current_provider = getattr(self.engine, 'provider', 'openai')
        pidx = self._provider_combo.findData(current_provider)
        if pidx >= 0:
            self._provider_combo.setCurrentIndex(pidx)
        self._provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        cl.addRow(I18n._("ai.provider") + ":", self._provider_combo)

        self._api_url_edit = QLineEdit(self.engine.api_url)
        self._api_url_edit.setPlaceholderText("https://api.openai.com/v1")
        self._api_url_edit.setMinimumHeight(36)
        cl.addRow(I18n._("ai.api_url") + ":", self._api_url_edit)

        self._api_key_edit = QLineEdit(self.engine.api_key)
        self._api_key_edit.setEchoMode(QLineEdit.Password)
        self._api_key_edit.setPlaceholderText("sk-...")
        self._api_key_edit.setMinimumHeight(36)
        cl.addRow(I18n._("ai.api_key") + ":", self._api_key_edit)

        self._model_combo = QComboBox()
        self._model_combo.setEditable(True)
        self._model_combo.setMinimumHeight(36)
        self._populate_models(current_provider)
        current_model = self.engine.model
        midx = self._model_combo.findText(current_model)
        if midx >= 0:
            self._model_combo.setCurrentIndex(midx)
        else:
            self._model_combo.setEditText(current_model)
        cl.addRow(I18n._("ai.model") + ":", self._model_combo)

        self._temperature_slider = QSlider(Qt.Horizontal)
        self._temperature_slider.setRange(0, 100)
        self._temperature_slider.setValue(int(float(getattr(self.engine, 'temperature', 0.7)) * 100))
        self._temp_label = QLabel(f"{self._temperature_slider.value() / 100:.1f}")
        self._temperature_slider.valueChanged.connect(
            lambda v: self._temp_label.setText(f"{v / 100:.1f}"))
        temp_row = QHBoxLayout()
        temp_row.addWidget(self._temperature_slider)
        temp_row.addWidget(self._temp_label)
        cl.addRow(I18n._("ai.temperature") + ":", temp_row)

        self._mode_combo = QComboBox()
        self._mode_combo.setMinimumHeight(36)
        self._mode_combo.addItem(I18n._("ai.mode_chat"), "chat")
        self._mode_combo.addItem(I18n._("ai.mode_search"), "search")
        self._mode_combo.addItem(I18n._("ai.mode_agent"), "agent")
        idx = self._mode_combo.findData(self.engine.mode)
        if idx >= 0:
            self._mode_combo.setCurrentIndex(idx)
        cl.addRow(I18n._("ai.mode") + ":", self._mode_combo)

        save_cfg_btn = QPushButton(I18n._("common.save"))
        save_cfg_btn.setProperty("success", True)
        save_cfg_btn.setMinimumHeight(36)
        save_cfg_btn.clicked.connect(self._save_config)
        cl.addRow("", save_cfg_btn)

        layout.addWidget(self._config_panel)

        # Messages area
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self._messages_widget = QWidget()
        self._messages_layout = QVBoxLayout(self._messages_widget)
        self._messages_layout.setContentsMargins(16, 8, 16, 8)
        self._messages_layout.setSpacing(8)
        self._messages_layout.addStretch()
        self._scroll.setWidget(self._messages_widget)
        layout.addWidget(self._scroll, 1)

        # Input area
        input_frame = QFrame()
        input_frame.setProperty("card", True)
        input_layout = QHBoxLayout(input_frame)
        input_layout.setContentsMargins(12, 8, 12, 8)
        input_layout.setSpacing(8)

        self._input_edit = QTextEdit()
        self._input_edit.setPlaceholderText(I18n._("ai.placeholder"))
        self._input_edit.setMaximumHeight(80)
        self._input_edit.setAcceptRichText(False)
        self._input_edit.installEventFilter(self)
        input_layout.addWidget(self._input_edit, 1)

        self._attach_btn = QPushButton("📎")
        self._attach_btn.setFixedSize(36, 36)
        self._attach_btn.setToolTip("Прикрепить файл")
        self._attach_btn.clicked.connect(self._attach_file)
        input_layout.addWidget(self._attach_btn)

        self._send_btn = QPushButton(I18n._("ai.send"))
        self._send_btn.setProperty("success", True)
        self._send_btn.setFixedHeight(36)
        self._send_btn.clicked.connect(self._send_message)
        input_layout.addWidget(self._send_btn)

        layout.addWidget(input_frame)

    def _populate_models(self, provider: str) -> None:
        self._model_combo.clear()
        models = {
            "openai": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
            "openrouter": ["openai/gpt-4o", "anthropic/claude-3-opus", "anthropic/claude-3.5-sonnet", "deepseek/deepseek-r1", "google/gemini-pro"],
            "deepseek": ["deepseek-chat", "deepseek-reasoner"],
            "anthropic": ["claude-3-opus-20240229", "claude-3.5-sonnet-20240620", "claude-3-haiku-20240307"],
            "gemini": ["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"],
            "groq": ["llama-3.3-70b-versatile", "mixtral-8x7b-32768", "gemma2-9b-it"],
            "local": ["llama3", "mistral", "qwen2.5", "phi-3"],
        }
        self._model_combo.addItems(models.get(provider, ["gpt-3.5-turbo"]))

    def _on_provider_changed(self, idx: int) -> None:
        provider = self._provider_combo.currentData()
        default_urls = {
            "openai": "https://api.openai.com/v1",
            "openrouter": "https://openrouter.ai/api/v1",
            "deepseek": "https://api.deepseek.com/v1",
            "anthropic": "https://api.anthropic.com/v1",
            "gemini": "https://generativelanguage.googleapis.com/v1beta",
            "groq": "https://api.groq.com/openai/v1",
            "local": "http://localhost:11434/v1",
            "custom": "",
        }
        self._api_url_edit.setText(default_urls.get(provider, "https://api.openai.com/v1"))
        self._populate_models(provider)

    def _toggle_config(self, visible: bool) -> None:
        self._config_panel.setVisible(visible)

    def _save_config(self) -> None:
        self.engine.provider = self._provider_combo.currentData()
        self.engine.api_url = self._api_url_edit.text().strip()
        self.engine.api_key = self._api_key_edit.text().strip()
        self.engine.model = self._model_combo.currentText().strip()
        self.engine.temperature = self._temperature_slider.value() / 100.0
        self.engine.mode = self._mode_combo.currentData()
        self.engine.save_settings()
        ToastNotification.notify(I18n._("common.success"), "success", 3000)

    def _clear_history(self) -> None:
        self._history.clear()
        while self._messages_layout.count() > 1:
            item = self._messages_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

    def _add_message_bubble(self, text: str, is_user: bool = False,
                            is_error: bool = False) -> None:
        bubble = QFrame()
        bubble.setStyleSheet(f"""
            QFrame {{
                background: {"#2196F3" if is_user else ("#F44336" if is_error else "#E8ECF1")};
                border-radius: 12px;
                padding: 10px 14px;
                margin: {"0 60px 0 0" if is_user else "0 0 0 60px"};
            }}
            QLabel {{
                color: {"#FFFFFF" if is_user or is_error else "#2C3E50"};
                font-size: 13px; background: transparent;
            }}
        """)
        bl = QHBoxLayout(bubble)
        bl.setContentsMargins(0, 0, 0, 0)
        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        bl.addWidget(label)
        idx = self._messages_layout.count() - 1
        self._messages_layout.insertWidget(idx, bubble)
        QApplication.processEvents()
        fade_in_widget(bubble, 250)
        QTimer.singleShot(50, self._scroll_to_bottom)

    def _scroll_to_bottom(self) -> None:
        scrollbar = self._scroll.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _attach_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, I18n._("ai.attach_file"), "",
            I18n._("ai.attach_filter"))
        if path:
            self._attachment_path = path
            filename = os.path.basename(path)
            self._attach_btn.setText(f"📎 {filename}")

    def _send_message(self) -> None:
        text = self._input_edit.toPlainText().strip()
        if not text and not self._attachment_path:
            return
        full_text = text
        if self._attachment_path:
            path = self._attachment_path
            fname = os.path.basename(path)
            ext = os.path.splitext(path)[1].lower()
            img_exts = {'.png', '.jpg', '.jpeg', '.gif', '.bmp'}
            text_exts = {'.txt', '.py', '.md', '.csv', '.json', '.xml', '.html', '.css', '.js'}
            if ext in img_exts:
                full_text = f"{text}\n\n[Изображение: {fname}]"
            elif ext in text_exts:
                try:
                    with open(path, "r", encoding="utf-8", errors="replace") as fh:
                        content = fh.read(10000)
                    full_text = f"{text}\n\n[Файл: {fname}]\n```\n{content}\n```"
                except Exception:
                    full_text = f"{text}\n\n[Файл: {fname} (не удалось прочитать)]"
            else:
                full_text = f"{text}\n\n[Файл: {fname}]"
            self._attachment_path = ""
            self._attach_btn.setText("📎")
        self._input_edit.clear()
        self._add_message_bubble(full_text, is_user=True)
        self._history.append({"role": "user", "content": full_text})
        if not self._send_btn.isEnabled():
            return
        self._send_btn.setEnabled(False)
        self._send_btn.setText("⏳ " + I18n._("ai.thinking"))
        QApplication.processEvents()
        QTimer.singleShot(50, lambda: self._process_ai(full_text))

    def _process_ai(self, text: str) -> None:
        try:
            local_noauth = any(x in self.engine.api_url.lower() for x in ["localhost", "127.0.0.1", "ollama"])
            if not self.engine.api_key and not local_noauth:
                self._add_message_bubble(I18n._("ai.no_key"), is_error=True)
                self._send_btn.setEnabled(True)
                self._send_btn.setText(I18n._("ai.send"))
                return

            is_agent = self.engine.mode == "agent"
            schema = self._get_schema_summary() if is_agent else ""

            response = self.engine.send_request(self._history[:-1],
                                                 text, schema)
            if response is None:
                self._add_message_bubble(I18n._("ai.no_key"), is_error=True)
            elif response.startswith("HTTP Error") or response.startswith("Connection Error"):
                self._add_message_bubble(response, is_error=True)
            elif response.startswith("Error:"):
                self._add_message_bubble(response, is_error=True)
            elif not response.strip():
                self._add_message_bubble(I18n._("ai.empty_response") if I18n._("ai.empty_response") != "ai.empty_response" else "Пустой ответ от ИИ", is_error=True)
            elif is_agent:
                self._handle_agent_response(response)
            else:
                self._add_message_bubble(response)
                self._history.append({"role": "assistant", "content": response})
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            self._add_message_bubble(f"Error: {str(e)}\n{tb[:200]}", is_error=True)
        finally:
            self._send_btn.setEnabled(True)
            self._send_btn.setText(I18n._("ai.send"))

    def _get_schema_summary(self) -> str:
        parts = []
        for table in ["employees", "violations", "custom_ledger"]:
            cols = self.db.get_columns_config(table)
            parts.append(f"{table}: {', '.join(c['name'] for c in cols)}")
        companies = self.db.get_companies()
        parts.append(f"companies: {len(companies)} registered")
        return "; ".join(parts)

    def _handle_agent_response(self, response: str) -> None:
        parsed = self.engine.parse_agent_response(response)
        thought = parsed.get("thought", "")
        action = parsed.get("action", "respond")
        params = parsed.get("params", {})

        if thought:
            self._add_message_bubble(f"🤔 {thought}")
            self._history.append({"role": "assistant", "content": f"[Thought] {thought}"})

        if action == "respond":
            msg = params.get("message", response)
            self._add_message_bubble(msg)
            self._history.append({"role": "assistant", "content": msg})
            return

        # Actions that need execution
        if action in ("add_record", "modify_record", "delete_record", "rename_column", "add_note"):
            confirm_text = f"⚠️ AI wants to: {action}\n{json.dumps(params, ensure_ascii=False, indent=2)}"
            reply = QMessageBox.question(self, I18n._("ai.confirm_action").format(action=action),
                                         confirm_text,
                                         QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                result = self.engine.execute_action(action, params)
                self._add_message_bubble(f"✅ {result}")
                self._history.append({"role": "assistant", "content": result})
            else:
                self._add_message_bubble("⛔ " + I18n._("ai.action_cancelled"))
                self._history.append({"role": "assistant",
                                       "content": I18n._("ai.action_cancelled")})
        else:
            result = self.engine.execute_action(action, params)
            self._add_message_bubble(f"📊 {result}")
            self._history.append({"role": "assistant", "content": result})

    def eventFilter(self, obj: QObject, event: Any) -> bool:
        if obj == self._input_edit and event.type() == event.KeyPress:
            if (event.key() == Qt.Key_Return and
                    event.modifiers() != Qt.ShiftModifier):
                if self._send_btn.isEnabled():
                    self._send_message()
                return True
        return super().eventFilter(obj, event)


class AIChatInlineWidget(QWidget):
    """Embedded AI chat widget for use as a tab."""
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.db = DatabaseManager()
        self.engine = AIEngine()
        self._history: List[Dict[str, str]] = []
        self._attachment_path: str = ""
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Config panel
        self._config_panel = QFrame()
        self._config_panel.setProperty("card", True)
        cl = QFormLayout(self._config_panel)
        cl.setContentsMargins(16, 12, 16, 12)
        cl.setSpacing(8)

        self._provider_combo = QComboBox()
        self._provider_combo.setEditable(True)
        self._provider_combo.setMinimumHeight(36)
        self._provider_combo.addItem("OpenAI", "openai")
        self._provider_combo.addItem("OpenRouter", "openrouter")
        self._provider_combo.addItem("DeepSeek", "deepseek")
        self._provider_combo.addItem("Anthropic", "anthropic")
        self._provider_combo.addItem("Google Gemini", "gemini")
        self._provider_combo.addItem("Groq", "groq")
        self._provider_combo.addItem("Локальный (Local)", "local")
        self._provider_combo.addItem("Пользовательский (Custom)", "custom")
        current_provider = getattr(self.engine, 'provider', 'openai')
        pidx = self._provider_combo.findData(current_provider)
        if pidx >= 0:
            self._provider_combo.setCurrentIndex(pidx)
        self._provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        cl.addRow(I18n._("ai.provider") + ":", self._provider_combo)

        self._api_url_edit = QLineEdit(self.engine.api_url)
        self._api_url_edit.setPlaceholderText("https://api.openai.com/v1")
        self._api_url_edit.setMinimumHeight(36)
        cl.addRow(I18n._("ai.api_url") + ":", self._api_url_edit)

        self._api_key_edit = QLineEdit(self.engine.api_key)
        self._api_key_edit.setEchoMode(QLineEdit.Password)
        self._api_key_edit.setPlaceholderText("sk-...")
        self._api_key_edit.setMinimumHeight(36)
        cl.addRow(I18n._("ai.api_key") + ":", self._api_key_edit)

        self._model_combo = QComboBox()
        self._model_combo.setEditable(True)
        self._model_combo.setMinimumHeight(36)
        self._populate_models(current_provider)
        current_model = self.engine.model
        midx = self._model_combo.findText(current_model)
        if midx >= 0:
            self._model_combo.setCurrentIndex(midx)
        else:
            self._model_combo.setEditText(current_model)
        cl.addRow(I18n._("ai.model") + ":", self._model_combo)

        self._temperature_slider = QSlider(Qt.Horizontal)
        self._temperature_slider.setRange(0, 100)
        self._temperature_slider.setValue(int(float(getattr(self.engine, 'temperature', 0.7)) * 100))
        self._temp_label = QLabel(f"{self._temperature_slider.value() / 100:.1f}")
        self._temperature_slider.valueChanged.connect(
            lambda v: self._temp_label.setText(f"{v / 100:.1f}"))
        temp_row = QHBoxLayout()
        temp_row.addWidget(self._temperature_slider)
        temp_row.addWidget(self._temp_label)
        cl.addRow(I18n._("ai.temperature") + ":", temp_row)

        self._mode_combo = QComboBox()
        self._mode_combo.setMinimumHeight(36)
        self._mode_combo.addItem(I18n._("ai.mode_chat"), "chat")
        self._mode_combo.addItem(I18n._("ai.mode_search"), "search")
        self._mode_combo.addItem(I18n._("ai.mode_agent"), "agent")
        idx = self._mode_combo.findData(self.engine.mode)
        if idx >= 0:
            self._mode_combo.setCurrentIndex(idx)
        cl.addRow(I18n._("ai.mode") + ":", self._mode_combo)

        save_cfg_btn = QPushButton(I18n._("common.save"))
        save_cfg_btn.setProperty("success", True)
        save_cfg_btn.setMinimumHeight(36)
        save_cfg_btn.clicked.connect(self._save_config)
        cl.addRow("", save_cfg_btn)

        layout.addWidget(self._config_panel)

        # Messages area
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self._messages_widget = QWidget()
        self._messages_layout = QVBoxLayout(self._messages_widget)
        self._messages_layout.setContentsMargins(16, 8, 16, 8)
        self._messages_layout.setSpacing(8)
        self._messages_layout.addStretch()
        self._scroll.setWidget(self._messages_widget)
        layout.addWidget(self._scroll, 1)

        # Input area
        input_frame = QFrame()
        input_frame.setProperty("card", True)
        input_layout = QHBoxLayout(input_frame)
        input_layout.setContentsMargins(12, 8, 12, 8)
        input_layout.setSpacing(8)

        self._input_edit = QTextEdit()
        self._input_edit.setPlaceholderText(I18n._("ai.placeholder"))
        self._input_edit.setMaximumHeight(80)
        self._input_edit.setAcceptRichText(False)
        self._input_edit.installEventFilter(self)
        input_layout.addWidget(self._input_edit, 1)

        self._attach_btn = QPushButton("📎")
        self._attach_btn.setFixedSize(36, 36)
        self._attach_btn.setToolTip(I18n._("ai.attach_tooltip"))
        self._attach_btn.clicked.connect(self._attach_file)
        input_layout.addWidget(self._attach_btn)

        self._send_btn = QPushButton(I18n._("ai.send"))
        self._send_btn.setProperty("success", True)
        self._send_btn.setFixedHeight(36)
        self._send_btn.clicked.connect(self._send_message)
        input_layout.addWidget(self._send_btn)

        self._clear_btn = QPushButton(I18n._("ai.clear"))
        self._clear_btn.setProperty("flat", True)
        self._clear_btn.clicked.connect(self._clear_history)
        input_layout.addWidget(self._clear_btn)

        layout.addWidget(input_frame)

    def _populate_models(self, provider: str) -> None:
        self._model_combo.clear()
        models = {
            "openai": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
            "openrouter": ["openai/gpt-4o", "anthropic/claude-3.5-sonnet", "deepseek/deepseek-r1", "google/gemini-2.0-flash-001", "meta-llama/llama-3.3-70b-instruct"],
            "deepseek": ["deepseek-chat", "deepseek-reasoner"],
            "anthropic": ["claude-3-5-sonnet-20241022", "claude-3-opus-20240229", "claude-3-haiku-20240307"],
            "gemini": ["gemini-2.0-flash-001", "gemini-1.5-pro", "gemini-1.5-flash"],
            "groq": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"],
            "local": ["llama3", "mistral", "qwen2.5", "phi-3", "deepseek-r1"],
            "custom": [],
        }
        self._model_combo.addItems(models.get(provider, ["gpt-3.5-turbo"]))

    def _on_provider_changed(self, idx: int) -> None:
        provider = self._provider_combo.currentData()
        default_urls = {
            "openai": "https://api.openai.com/v1",
            "openrouter": "https://openrouter.ai/api/v1",
            "deepseek": "https://api.deepseek.com/v1",
            "anthropic": "https://api.anthropic.com/v1",
            "gemini": "https://generativelanguage.googleapis.com/v1beta",
            "groq": "https://api.groq.com/openai/v1",
            "local": "http://localhost:11434/v1",
            "custom": "",
        }
        self._api_url_edit.setText(default_urls.get(provider, "https://api.openai.com/v1"))
        self._populate_models(provider)

    def _save_config(self) -> None:
        self.engine.provider = self._provider_combo.currentData()
        self.engine.api_url = self._api_url_edit.text().strip()
        self.engine.api_key = self._api_key_edit.text().strip()
        self.engine.model = self._model_combo.currentText().strip()
        self.engine.temperature = self._temperature_slider.value() / 100.0
        self.engine.mode = self._mode_combo.currentData()
        self.engine.save_settings()
        self._config_panel.setVisible(False)
        ToastNotification.notify(I18n._("common.success"), "success", 3000)

    def _clear_history(self) -> None:
        self._history.clear()
        while self._messages_layout.count() > 1:
            item = self._messages_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

    def _add_message_bubble(self, text: str, is_user: bool = False,
                            is_error: bool = False) -> None:
        bubble = QFrame()
        bubble.setStyleSheet(f"""
            QFrame {{
                background: {"#2196F3" if is_user else ("#F44336" if is_error else "#E8ECF1")};
                border-radius: 12px;
                padding: 10px 14px;
                margin: {"0 60px 0 0" if is_user else "0 0 0 60px"};
            }}
            QLabel {{
                color: {"#FFFFFF" if is_user or is_error else "#2C3E50"};
                font-size: 13px; background: transparent;
            }}
        """)
        bl = QHBoxLayout(bubble)
        bl.setContentsMargins(0, 0, 0, 0)
        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        bl.addWidget(label)
        idx = self._messages_layout.count() - 1
        self._messages_layout.insertWidget(idx, bubble)
        QApplication.processEvents()
        fade_in_widget(bubble, 250)
        QTimer.singleShot(50, self._scroll_to_bottom)

    def _scroll_to_bottom(self) -> None:
        scrollbar = self._scroll.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _attach_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, I18n._("ai.attach_file"), "",
            I18n._("ai.attach_filter"))
        if path:
            self._attachment_path = path
            filename = os.path.basename(path)
            self._attach_btn.setText(f"📎 {filename}")

    def _send_message(self) -> None:
        text = self._input_edit.toPlainText().strip()
        if not text and not self._attachment_path:
            return
        full_text = text
        if self._attachment_path:
            path = self._attachment_path
            fname = os.path.basename(path)
            ext = os.path.splitext(path)[1].lower()
            img_exts = {'.png', '.jpg', '.jpeg', '.gif', '.bmp'}
            text_exts = {'.txt', '.py', '.md', '.csv', '.json', '.xml', '.html', '.css', '.js'}
            if ext in img_exts:
                full_text = f"{text}\n\n[Изображение: {fname}]"
            elif ext in text_exts:
                try:
                    with open(path, "r", encoding="utf-8", errors="replace") as fh:
                        content = fh.read(10000)
                    full_text = f"{text}\n\n[Файл: {fname}]\n```\n{content}\n```"
                except Exception:
                    full_text = f"{text}\n\n[Файл: {fname} (не удалось прочитать)]"
            else:
                full_text = f"{text}\n\n[Файл: {fname}]"
            self._attachment_path = ""
            self._attach_btn.setText("📎")
        self._input_edit.clear()
        self._add_message_bubble(full_text, is_user=True)
        self._history.append({"role": "user", "content": full_text})
        if not self._send_btn.isEnabled():
            return
        self._send_btn.setEnabled(False)
        self._send_btn.setText("⏳ " + I18n._("ai.thinking"))
        QApplication.processEvents()
        QTimer.singleShot(50, lambda: self._process_ai(full_text))

    def _process_ai(self, text: str) -> None:
        try:
            local_noauth = any(x in self.engine.api_url.lower() for x in ["localhost", "127.0.0.1", "ollama"])
            if not self.engine.api_key and not local_noauth:
                self._add_message_bubble(I18n._("ai.no_key"), is_error=True)
                self._send_btn.setEnabled(True)
                self._send_btn.setText(I18n._("ai.send"))
                return

            is_agent = self.engine.mode == "agent"
            schema = self._get_schema_summary() if is_agent else ""

            response = self.engine.send_request(self._history[:-1],
                                                 text, schema)
            if response is None:
                self._add_message_bubble(I18n._("ai.no_key"), is_error=True)
            elif response.startswith("HTTP Error") or response.startswith("Connection Error"):
                self._add_message_bubble(response, is_error=True)
            elif response.startswith("Error:"):
                self._add_message_bubble(response, is_error=True)
            elif not response.strip():
                self._add_message_bubble(I18n._("ai.empty_response") if I18n._("ai.empty_response") != "ai.empty_response" else "Пустой ответ от ИИ", is_error=True)
            elif is_agent:
                self._handle_agent_response(response)
            else:
                self._add_message_bubble(response)
                self._history.append({"role": "assistant", "content": response})
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            self._add_message_bubble(f"Error: {str(e)}\n{tb[:200]}", is_error=True)
        finally:
            self._send_btn.setEnabled(True)
            self._send_btn.setText(I18n._("ai.send"))

    def _get_schema_summary(self) -> str:
        parts = []
        for table in ["employees", "violations", "custom_ledger"]:
            cols = self.db.get_columns_config(table)
            parts.append(f"{table}: {', '.join(c['name'] for c in cols)}")
        companies = self.db.get_companies()
        parts.append(f"companies: {len(companies)} registered")
        return "; ".join(parts)

    def _handle_agent_response(self, response: str) -> None:
        parsed = self.engine.parse_agent_response(response)
        thought = parsed.get("thought", "")
        action = parsed.get("action", "respond")
        params = parsed.get("params", {})

        if thought:
            self._add_message_bubble(f"🤔 {thought}")
            self._history.append({"role": "assistant", "content": f"[Thought] {thought}"})

        if action == "respond":
            msg = params.get("message", response)
            self._add_message_bubble(msg)
            self._history.append({"role": "assistant", "content": msg})
            return

        if action in ("add_record", "modify_record", "delete_record", "rename_column", "add_note"):
            confirm_text = f"⚠️ AI wants to: {action}\n{json.dumps(params, ensure_ascii=False, indent=2)}"
            reply = QMessageBox.question(self, I18n._("ai.confirm_action"),
                                         confirm_text,
                                         QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                result = self.engine.execute_action(action, params)
                self._add_message_bubble(f"✅ {result}")
                self._history.append({"role": "assistant", "content": result})
            else:
                self._add_message_bubble("⛔ " + I18n._("ai.action_cancelled"))
                self._history.append({"role": "assistant",
                                       "content": I18n._("ai.action_cancelled")})
        else:
            result = self.engine.execute_action(action, params)
            self._add_message_bubble(f"📊 {result}")
            self._history.append({"role": "assistant", "content": result})

    def eventFilter(self, obj: QObject, event: Any) -> bool:
        if obj == self._input_edit and event.type() == event.KeyPress:
            if (event.key() == Qt.Key_Return and
                    event.modifiers() != Qt.ShiftModifier):
                if self._send_btn.isEnabled():
                    self._send_message()
                return True
        return super().eventFilter(obj, event)
