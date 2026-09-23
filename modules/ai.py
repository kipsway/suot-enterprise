import json, os, sys
import urllib.request as _urllib_request
import urllib.error as _urllib_error
from typing import Any, Dict, List, Optional, Generator
import io
import time
from PyQt5 import sip
from PyQt5.QtCore import Qt, QTimer, QObject, QEvent
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QApplication,
    QDialog,
    QWidget,
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QLineEdit,
    QSlider,
    QTextEdit,
    QTextBrowser,
    QScrollArea,
    QFileDialog,
    QMessageBox,
)
from widgets.glass_button import GlassButton
from widgets.glass_line_edit import GlassLineEdit
from widgets.glass_combo_box import GlassComboBox

from app_core.i18n import I18n
from app_core.markdown_renderer import markdown_to_html
from app_core.theme_engine import ThemeEngine
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
        enc_key = self.db.get_ai_setting("api_key", "")
        self.api_key: str = self.db.decrypt_value(enc_key)
        self.model: str = self.db.get_ai_setting("model", self.DEFAULT_MODEL)
        self.mode: str = self.db.get_ai_setting("mode", "chat")
        self.temperature: float = float(self.db.get_ai_setting("temperature", "0.7"))
        self._last_image_path: str = ""

    @staticmethod
    def _is_vision_model(model: str) -> bool:
        model_lower = model.lower()
        keywords = ["vision", "gpt-4o", "gemini-2.0", "gemini-1.5", "claude-3"]
        return any(k in model_lower for k in keywords)

    @staticmethod
    def _encode_image(filepath: str) -> str:
        import base64

        with open(filepath, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    @staticmethod
    def _mime_from_ext(path: str) -> str:
        ext = os.path.splitext(path)[1].lower()
        mime_map = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".bmp": "image/bmp",
            ".webp": "image/webp",
        }
        return mime_map.get(ext, "image/jpeg")

    def save_settings(self) -> None:
        self.db.set_ai_setting("provider", self.provider)
        self.db.set_ai_setting("api_url", self.api_url)
        self.db.set_ai_setting("api_key", self.db.encrypt_value(self.api_key))
        self.db.set_ai_setting("model", self.model)
        self.db.set_ai_setting("mode", self.mode)
        self.db.set_ai_setting("temperature", str(self.temperature))

    @staticmethod
    def build_system_prompt(db_schema: str = "") -> str:
        schema_section = (
            f"\n\nActual database schema (auto-detected):\n{db_schema}"
            if db_schema
            else ""
        )
        return (
            "You are an AI assistant for an Occupational Safety and Health (OSH) "
            "management system called 'СУОТ Enterprise'. "
            "Your tasks: answer questions, search data, analyze statistics, "
            "generate reports, and modify records (only with user confirmation).\n\n"
            "Database schema:\n"
            "1. employees - employee records\n"
            "   Fields: ФИО (text), Должность (text), Подразделение (text), "
            "Фирма (text), Телефон (text), Дата медосмотра (date), "
            "Квалификация (text), Дата проведения (date), Статус (status)\n"
            "2. violations - safety violations\n"
            "   Fields: Дата (date), Фирма (text), Подразделение (text), "
            "Категория риска (risk category), Описание (text), "
            "Ответственный (text), Срок устранения (date), Штраф (number), Статус (status)\n"
            "3. companies - organizations\n"
            "   Fields: name (text), address (text), contact (text)\n"
            "4. custom_ledger - custom records (variable fields)\n"
            "5. notes - text notes\n\n"
            "Safety recommendations: When asked about safety, always analyze "
            "violations data and provide actionable recommendations. Consider "
            "risk categories, overdue items, and historical trends.\n\n"
            "When in AGENT mode, respond with a valid JSON object on a single line:\n"
            '{"thought": "...", "action": "action_name", "params": {...}}\n\n'
            "JSON formatting rules:\n"
            "- Always use double quotes for keys and string values\n"
            "- No trailing commas\n"
            "- No comments inside JSON\n"
            "- Escape special characters properly\n\n"
            "Available actions:\n"
            '- respond: just reply to user (params: {"message": "..."})\n'
            '- search_db: search across tables (params: {"query": "...", "table": "..."})\n'
            "- get_stats: get summary statistics\n"
            '- add_record: add a new record (params: {"table": "...", "data": {"field1": "value1", ...}})\n'
            '- modify_record: modify a record (params: {"table": "...", "id": ..., '
            '"field": "...", "value": "..."})\n'
            '- delete_record: delete a record (params: {"table": "...", "id": ...})\n'
            '- create_report: generate company report (params: {"company": "..."})\n'
            '- rename_column: rename a column (params: {"table": "...", "old": "...", '
            '"new": "..."})\n'
            '- add_note: add a note (params: {"entity_type": "...", "entity_id": ..., "text": "..."})\n'
            "For 'modify_record', 'add_record', 'delete_record', 'rename_column' and 'add_note', "
            "user confirmation is required." + schema_section
        )

    def _build_messages(
        self, history: List[Dict[str, str]], query: str, schema: str
    ) -> List[Dict[str, Any]]:
        msgs: List[Dict[str, Any]] = [
            {"role": "system", "content": self.build_system_prompt(schema)}
        ]
        for h in history:
            msgs.append(h)
        if self._is_vision_model(self.model) and self._has_image_marker(query):
            data = self._resolve_vision_content(query)
            if data is not None:
                msgs.append(data)
            else:
                msgs.append({"role": "user", "content": query})
        else:
            msgs.append({"role": "user", "content": query})
        return msgs

    def _has_image_marker(self, text: str) -> bool:
        return (
            "[\u0418\u0437\u043e\u0431\u0440\u0430\u0436\u0435\u043d\u0438\u0435:"
            in text
        )

    def _resolve_vision_content(self, text: str) -> Optional[Dict[str, Any]]:
        import re

        m = re.search(r"\[Изображение:\s*(.+?)\]", text)
        if not m:
            return None
        fname = m.group(1).strip()
        filepath = self._find_image_file(fname)
        if not filepath:
            return None
        b64 = self._encode_image(filepath)
        mime = self._mime_from_ext(filepath)
        clean_text = text[: m.start()].strip() + text[m.end() :].strip()
        content: list = []
        if clean_text:
            content.append({"type": "text", "text": clean_text})
        content.append(
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}
        )
        return {"role": "user", "content": content}

    def _find_image_file(self, fname: str) -> Optional[str]:
        if self._last_image_path and os.path.isfile(self._last_image_path):
            return self._last_image_path
        media_path = self.db.get_setting("media_path", "media")
        candidates = [
            fname,
            os.path.join(media_path, fname) if media_path else "",
            os.path.join(os.getcwd(), "media", fname),
            os.path.join(os.getcwd(), fname),
        ]
        for c in candidates:
            if c and os.path.isfile(c):
                return c
        return None

    def send_request(
        self, history: List[Dict[str, str]], query: str, schema: str = ""
    ) -> Optional[str]:
        local_noauth = any(
            x in self.api_url.lower() for x in ["localhost", "127.0.0.1", "ollama"]
        )
        if not self.api_key and not local_noauth:
            return None
        try:
            provider = self.provider.lower()
            messages = self._build_messages(history, query, schema)

            if provider == "anthropic":
                url = f"{self.api_url.rstrip('/')}/messages"
                payload = json.dumps(
                    {
                        "model": self.model,
                        "max_tokens": 4000,
                        "messages": [
                            {"role": m["role"], "content": m["content"]}
                            for m in messages
                            if m["role"] != "system"
                        ],
                        "system": next(
                            (m["content"] for m in messages if m["role"] == "system"),
                            "",
                        ),
                    }
                ).encode("utf-8")
                headers = {
                    "Content-Type": "application/json",
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                }
                req = _urllib_request.Request(url, data=payload, headers=headers)
                resp = _urllib_request.urlopen(req, timeout=90)
                data = json.loads(resp.read().decode("utf-8"))
                if "content" in data and len(data["content"]) > 0:
                    return "".join(
                        b.get("text", "")
                        for b in data["content"]
                        if b.get("type") == "text"
                    )
                return json.dumps(data, ensure_ascii=False)[:500]

            if provider == "gemini":
                model_name = (
                    self.model.split("/")[-1] if "/" in self.model else self.model
                )
                url = f"{self.api_url.rstrip('/')}/models/{model_name}:generateContent"
                gemini_msgs = []
                for m in messages:
                    role = "user" if m["role"] in ("user", "system") else "model"
                    if isinstance(m.get("content"), list):
                        parts = []
                        for item in m["content"]:
                            if item["type"] == "text":
                                parts.append({"text": item["text"]})
                            elif item["type"] == "image_url":
                                data_url = item["image_url"]["url"]
                                if data_url.startswith("data:"):
                                    _, b64part = data_url.split(",", 1)
                                    mime = data_url.split(";")[0].split(":")[1]
                                    parts.append(
                                        {
                                            "inline_data": {
                                                "mime_type": mime,
                                                "data": b64part,
                                            }
                                        }
                                    )
                        gemini_msgs.append({"role": role, "parts": parts})
                    else:
                        gemini_msgs.append(
                            {"role": role, "parts": [{"text": m["content"]}]}
                        )
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
            payload = json.dumps(
                {
                    "model": self.model,
                    "messages": messages,
                    "temperature": self.temperature,
                    "max_tokens": 4000,
                }
            ).encode("utf-8")
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
            return f"HTTP Error {e.code}: {e.reason} \u2014 {body}"
        except _urllib_error.URLError as e:
            return f"Connection Error: {e.reason}"
        except Exception as e:
            import traceback

            return f"Error: {str(e)}\n{traceback.format_exc()[:300]}"

    def send_request_stream(
        self, history: List[Dict[str, str]], query: str, schema: str = ""
    ) -> Generator[str, None, None]:
        provider = self.provider.lower()
        if provider in ("anthropic", "gemini"):
            result = self.send_request(history, query, schema)
            if result:
                yield result
            return

        local_noauth = any(
            x in self.api_url.lower() for x in ["localhost", "127.0.0.1", "ollama"]
        )
        if not self.api_key and not local_noauth:
            yield "[ERROR: No API key configured]"
            return

        try:
            messages = self._build_messages(history, query, schema)
            url = f"{self.api_url.rstrip('/')}/chat/completions"
            payload = json.dumps(
                {
                    "model": self.model,
                    "messages": messages,
                    "temperature": self.temperature,
                    "max_tokens": 4000,
                    "stream": True,
                }
            ).encode("utf-8")
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            req = _urllib_request.Request(url, data=payload, headers=headers)
            resp = _urllib_request.urlopen(req, timeout=90)
            while True:
                raw = resp.readline()
                if not raw:
                    break
                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                if line == "data: [DONE]":
                    break
                if line.startswith("data: "):
                    try:
                        chunk = json.loads(line[6:])
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue
        except _urllib_error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")[:500]
            yield f"[HTTP Error {e.code}: {e.reason} \u2014 {body}]"
        except _urllib_error.URLError as e:
            yield f"[Connection Error: {e.reason}]"
        except Exception as e:
            import traceback

            yield f"[Error: {str(e)}\n{traceback.format_exc()[:300]}]"

    def parse_agent_response(self, response: str) -> Dict[str, Any]:
        try:
            cleaned = response.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.strip("`")
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:]
            return json.loads(cleaned)
        except Exception:
            return {"thought": "", "action": "respond", "params": {"message": response}}

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
        tables_to_search = (
            [table]
            if table
            else ["employees", "violations", "custom_ledger", "companies"]
        )
        for t in tables_to_search:
            if t == "companies":
                rows = self.db.fetch_all(
                    "SELECT id, name, address, contact FROM companies"
                )
            else:
                rows = self.db.get_json_records(t)
            for r in rows:
                dj = r.get("data_json", {}) if t != "companies" else r
                for val in dj.values():
                    if isinstance(val, str) and query.lower() in val.lower():
                        label = r.get(
                            "\u0424\u0418\u041e",
                            r.get(
                                "name",
                                r.get(
                                    "\u041e\u043f\u0438\u0441\u0430\u043d\u0438\u0435",
                                    f"#{r['id']}",
                                ),
                            ),
                        )
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
            f"Total Fines: {s['fines_total']:,.0f} RUB"
        )

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
            elif c["type"] == "\u0421\u0442\u0430\u0442\u0443\u0441":
                record[c["name"]] = "\u0410\u043a\u0442\u0438\u0432\u043d\u043e"
            elif c["type"] == "\u041c\u0435\u0434\u0438\u0430":
                record[c["name"]] = []
            else:
                record[c["name"]] = ""
        rec_id = self.db.save_json_record(table, 0, record)
        self.db.log_event(
            f"AI added record #{rec_id} to {table}", "INFO", {"table": table}
        )
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
                self.db.log_event(
                    f"AI modified record #{rec_id} in {table}: {field} = {value}",
                    "INFO",
                    {"table": table},
                )
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
                self.db.execute(
                    "DELETE FROM json_data WHERE id = ? AND category = ?",
                    (rec_id, table),
                )
                self.db.conn.commit()
                self.db.log_event(
                    f"AI deleted record #{rec_id} from {table}",
                    "INFO",
                    {"table": table},
                )
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
            (new_name, table, old_name),
        )
        self.db.conn.commit()
        self.db.log_event(
            f"AI renamed column '{old_name}' to '{new_name}' in {table}",
            "INFO",
            {"table": table},
        )
        return f"Column '{old_name}' renamed to '{new_name}' in {table}."

    def _action_add_note(self, params: Dict[str, Any]) -> str:
        entity_type = params.get("entity_type", "global")
        entity_id = params.get("entity_id", 0)
        text = params.get("text", "")
        if not text:
            return "Error: 'text' param required"
        note_id = self.db.save_note(
            entity_type=entity_type, entity_id=entity_id, title=text[:50], content=text
        )
        self.db.log_event(
            f"AI added note #{note_id} for {entity_type}:{entity_id}",
            "INFO",
            {"entity_type": entity_type},
        )
        return f"Note #{note_id} added for {entity_type}:{entity_id}."


class _BaseAIChat(sip.wrapper):
    """Mixin with shared AI chat logic for both dialog and inline widget."""

    def _setup_ai(self) -> None:
        self.db = DatabaseManager()
        self.engine = AIEngine()
        self._history: List[Dict[str, str]] = []
        self._session_id: str = "default"
        self._attachment_path: str = ""
        self._stream_label: Optional[QLabel] = None
        self._stream_buffer: str = ""
        self._load_chat_history()
        if not self.db.get_ai_setting("ollama_suggested", ""):
            if not self.engine.api_key:
                self.db.set_ai_setting("ollama_suggested", "1")
                from PyQt5.QtCore import QTimer

                if isinstance(self, QWidget):
                    QTimer.singleShot(
                        0,
                        lambda: QMessageBox.information(
                            self,
                            I18n._("ai.ollama_title"),
                            I18n._("ai.ollama_suggestion"),
                        ),
                    )

    def _build_config_form(self) -> None:
        cl = QFormLayout(self._config_panel)
        cl.setContentsMargins(16, 12, 16, 12)
        cl.setSpacing(8)

        self._provider_combo = GlassComboBox()
        self._provider_combo.setEditable(True)
        self._provider_combo.setMinimumHeight(36)
        self._provider_combo.addItem("OpenAI", "openai")
        self._provider_combo.addItem("OpenRouter", "openrouter")
        self._provider_combo.addItem("DeepSeek", "deepseek")
        self._provider_combo.addItem("Anthropic", "anthropic")
        self._provider_combo.addItem("Google Gemini", "gemini")
        self._provider_combo.addItem("Groq", "groq")
        self._provider_combo.addItem(
            "\u041b\u043e\u043a\u0430\u043b\u044c\u043d\u044b\u0439 (Local)", "local"
        )
        self._provider_combo.addItem(
            "\u041f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044c\u0441\u043a\u0438\u0439 (Custom)",
            "custom",
        )
        current_provider = getattr(self.engine, "provider", "openai")
        pidx = self._provider_combo.findData(current_provider)
        if pidx >= 0:
            self._provider_combo.setCurrentIndex(pidx)
        self._provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        cl.addRow(I18n._("ai.provider") + ":", self._provider_combo)

        self._api_url_edit = GlassLineEdit(self.engine.api_url)
        self._api_url_edit.setPlaceholderText("https://api.openai.com/v1")
        self._api_url_edit.setMinimumHeight(36)
        cl.addRow(I18n._("ai.api_url") + ":", self._api_url_edit)

        self._api_key_edit = GlassLineEdit(self.engine.api_key)
        self._api_key_edit.setEchoMode(QLineEdit.Password)
        self._api_key_edit.setPlaceholderText("sk-...")
        self._api_key_edit.setMinimumHeight(36)
        cl.addRow(I18n._("ai.api_key") + ":", self._api_key_edit)

        self._model_combo = GlassComboBox()
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
        self._temperature_slider.setValue(
            int(float(getattr(self.engine, "temperature", 0.7)) * 100)
        )
        self._temp_label = QLabel(f"{self._temperature_slider.value() / 100:.1f}")
        self._temperature_slider.valueChanged.connect(
            lambda v: self._temp_label.setText(f"{v / 100:.1f}")
        )
        temp_row = QHBoxLayout()
        temp_row.addWidget(self._temperature_slider)
        temp_row.addWidget(self._temp_label)
        cl.addRow(I18n._("ai.temperature") + ":", temp_row)

        self._mode_combo = GlassComboBox()
        self._mode_combo.setMinimumHeight(36)
        self._mode_combo.addItem(I18n._("ai.mode_chat"), "chat")
        self._mode_combo.addItem(I18n._("ai.mode_search"), "search")
        self._mode_combo.addItem(I18n._("ai.mode_agent"), "agent")
        idx = self._mode_combo.findData(self.engine.mode)
        if idx >= 0:
            self._mode_combo.setCurrentIndex(idx)
        cl.addRow(I18n._("ai.mode") + ":", self._mode_combo)

        save_cfg_btn = GlassButton(I18n._("common.save"))
        save_cfg_btn.setProperty("success", True)
        save_cfg_btn.setMinimumHeight(36)
        save_cfg_btn.clicked.connect(self._save_config)
        cl.addRow("", save_cfg_btn)

    def _populate_models(self, provider: str) -> None:
        self._model_combo.clear()
        models = {
            "openai": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
            "openrouter": [
                "openai/gpt-4o",
                "anthropic/claude-3.5-sonnet",
                "deepseek/deepseek-r1",
                "google/gemini-2.0-flash-001",
                "meta-llama/llama-3.3-70b-instruct",
            ],
            "deepseek": ["deepseek-chat", "deepseek-reasoner"],
            "anthropic": [
                "claude-3-5-sonnet-20241022",
                "claude-3-opus-20240229",
                "claude-3-haiku-20240307",
            ],
            "gemini": ["gemini-2.0-flash-001", "gemini-1.5-pro", "gemini-1.5-flash"],
            "groq": ["llama-3.3-70b-versatile", "mixtral-8x7b-32768", "gemma2-9b-it"],
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
        self._api_url_edit.setText(
            default_urls.get(provider, "https://api.openai.com/v1")
        )
        self._populate_models(provider)

    def _save_config(self) -> None:
        self.engine.provider = self._provider_combo.currentData()
        self.engine.api_url = self._api_url_edit.text().strip()
        self.engine.api_key = self._api_key_edit.text().strip()
        self.engine.model = self._model_combo.currentText().strip()
        self.engine.temperature = self._temperature_slider.value() / 100.0
        self.engine.mode = self._mode_combo.currentData()
        self.engine.save_settings()
        ToastNotification.notify(I18n._("common.success"), "success", 3000)

    def _load_chat_history(self) -> None:
        try:
            rows = self.db.get_chat_history(self._session_id, limit=200)
            for row in rows:
                self._history.append(
                    {
                        "role": row["role"],
                        "content": row["content"],
                    }
                )
        except Exception:
            pass

    def _save_chat_session(self, session_id: str = "") -> None:
        if session_id:
            self._session_id = session_id

    def _clear_history(self) -> None:
        self._history.clear()
        self.db.clear_chat_history(self._session_id)
        while self._messages_layout.count() > 1:
            item = self._messages_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

    def _add_message_bubble(
        self, text: str, is_user: bool = False, is_error: bool = False
    ) -> None:
        bubble = QFrame()
        dark = getattr(self, "_is_dark", lambda: ThemeEngine._current_theme == "dark")()
        user_bg = "rgba(33, 150, 243, 0.85)" if not dark else "rgba(33, 150, 243, 0.7)"
        err_bg = "rgba(244, 67, 54, 0.85)" if not dark else "rgba(244, 67, 54, 0.7)"
        ai_bg = "rgba(255, 255, 255, 0.6)" if not dark else "rgba(44, 44, 48, 0.8)"
        ai_color = "#2C3E50" if not dark else "#E0E0E8"
        bubble.setStyleSheet(f"""
            QFrame {{
                background: {"qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 " + user_bg + ",stop:1 " + user_bg + ")" if is_user else ("qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 " + err_bg + ",stop:1 " + err_bg + ")" if is_error else "qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 " + ai_bg + ",stop:1 " + ai_bg + ")")};
                border: 1px solid {"rgba(255,255,255,0.3)" if not dark else "rgba(255,255,255,0.08)"};
                border-radius: 12px;
                padding: 10px 14px;
                margin: {"0 60px 0 0" if is_user else "0 0 0 60px"};
            }}
        """)
        bl = QHBoxLayout(bubble)
        bl.setContentsMargins(0, 0, 0, 0)
        if is_user:
            label = QLabel(text)
            label.setStyleSheet(f"color:#FFFFFF;font-size:13px;background:transparent;")
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            bl.addWidget(label)
        else:
            html = markdown_to_html(text)
            browser = QTextBrowser()
            browser.setHtml(
                f"<div style='color:{ai_color};font-size:13px;'>{html}</div>"
            )
            browser.setOpenExternalLinks(True)
            browser.setFrameShape(QFrame.NoFrame)
            browser.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            browser.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            browser.setStyleSheet("background:transparent;")
            browser.document().setDocumentMargin(0)
            browser.setTextInteractionFlags(
                Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse
            )
            bl.addWidget(browser, 1)
            copy_btn = GlassButton("\U0001f4cb")
            copy_btn.setProperty("flat", True)
            copy_btn.setFixedSize(24, 24)
            copy_btn.setToolTip(I18n._("ai.copy"))
            copy_btn.clicked.connect(lambda checked, t=text: self._copy_text(t))
            bl.addWidget(copy_btn)
        idx = self._messages_layout.count() - 1
        self._messages_layout.insertWidget(idx, bubble)
        QApplication.processEvents()
        fade_in_widget(bubble, 250)
        QTimer.singleShot(50, self._scroll_to_bottom)

    def _copy_text(self, text: str) -> None:
        QApplication.clipboard().setText(text)
        ToastNotification.notify(I18n._("common.copied", "Copied"), "success", 2000)

    def _add_stream_bubble(self, initial_text: str = "") -> QLabel:
        bubble = QFrame()
        dark = getattr(self, "_is_dark", lambda: ThemeEngine._current_theme == "dark")()
        ai_bg = "rgba(255, 255, 255, 0.6)" if not dark else "rgba(44, 44, 48, 0.8)"
        ai_color = "#2C3E50" if not dark else "#E0E0E8"
        bubble.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 {ai_bg},stop:1 {ai_bg});
                border: 1px solid {"rgba(255,255,255,0.3)" if not dark else "rgba(255,255,255,0.08)"};
                border-radius: 12px;
                padding: 10px 14px;
                margin: 0 0 0 60px;
            }}
            QLabel {{
                color: {ai_color};
                font-size: 13px; background: transparent;
            }}
        """)
        bl = QHBoxLayout(bubble)
        bl.setContentsMargins(0, 0, 0, 0)
        browser = QTextBrowser()
        browser.setFrameShape(QFrame.NoFrame)
        browser.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        browser.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        browser.setStyleSheet(
            f"background:transparent;color:{ai_color};font-size:13px;"
        )
        browser.document().setDocumentMargin(0)
        browser.setTextInteractionFlags(Qt.TextSelectableByMouse)
        bl.addWidget(browser, 1)
        idx = self._messages_layout.count() - 1
        self._messages_layout.insertWidget(idx, bubble)
        self._stream_label = browser
        QApplication.processEvents()
        fade_in_widget(bubble, 250)
        QTimer.singleShot(50, self._scroll_to_bottom)
        return browser

    def _scroll_to_bottom(self) -> None:
        scrollbar = self._scroll.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _attach_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, I18n._("ai.attach_file"), "", I18n._("ai.attach_filter")
        )
        if path:
            self._attachment_path = path
            filename = os.path.basename(path)
            self._attach_btn.setText(f"\U0001f4ce {filename}")

    def _send_message(self) -> None:
        text = self._input_edit.toPlainText().strip()
        if not text and not self._attachment_path:
            return
        full_text = text
        if self._attachment_path:
            path = self._attachment_path
            fname = os.path.basename(path)
            ext = os.path.splitext(path)[1].lower()
            img_exts = {".png", ".jpg", ".jpeg", ".gif", ".bmp"}
            text_exts = {
                ".txt",
                ".py",
                ".md",
                ".csv",
                ".json",
                ".xml",
                ".html",
                ".css",
                ".js",
            }
            if ext in img_exts:
                full_text = f"{text}\n\n[\u0418\u0437\u043e\u0431\u0440\u0430\u0436\u0435\u043d\u0438\u0435: {fname}]"
                self.engine._last_image_path = path
            elif ext in text_exts:
                try:
                    with open(path, "r", encoding="utf-8", errors="replace") as fh:
                        content = fh.read(10000)
                    full_text = f"{text}\n\n[\u0424\u0430\u0439\u043b: {fname}]\n```\n{content}\n```"
                except Exception:
                    full_text = f"{text}\n\n[\u0424\u0430\u0439\u043b: {fname} (\u043d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u043f\u0440\u043e\u0447\u0438\u0442\u0430\u0442\u044c)]"
            else:
                full_text = f"{text}\n\n[\u0424\u0430\u0439\u043b: {fname}]"
            self._attachment_path = ""
            self._attach_btn.setText("\U0001f4ce")
        self._input_edit.clear()
        self._add_message_bubble(full_text, is_user=True)
        self._history.append({"role": "user", "content": full_text})
        self.db.save_chat_message("default", "user", full_text, self.engine.model)
        if not self._send_btn.isEnabled():
            return
        self._send_btn.setEnabled(False)
        self._send_btn.setText("\u23f3 " + I18n._("ai.thinking"))
        QApplication.processEvents()
        if self.engine.mode == "agent":
            QTimer.singleShot(50, lambda: self._process_ai(full_text))
        else:
            QTimer.singleShot(50, lambda: self._process_ai_stream(full_text))

    def _process_ai(self, text: str) -> None:
        try:
            local_noauth = any(
                x in self.engine.api_url.lower()
                for x in ["localhost", "127.0.0.1", "ollama"]
            )
            if not self.engine.api_key and not local_noauth:
                self._add_message_bubble(I18n._("ai.no_key"), is_error=True)
                self._send_btn.setEnabled(True)
                self._send_btn.setText(I18n._("ai.send"))
                return

            is_agent = self.engine.mode == "agent"
            schema = self._get_schema_summary() if is_agent else ""

            response = self.engine.send_request(self._history[:-1], text, schema)
            if response is None:
                self._add_message_bubble(I18n._("ai.no_key"), is_error=True)
            elif response.startswith("HTTP Error") or response.startswith(
                "Connection Error"
            ):
                self._add_message_bubble(response, is_error=True)
            elif response.startswith("Error:"):
                self._add_message_bubble(response, is_error=True)
            elif not response.strip():
                empty_msg = I18n._("ai.empty_response")
                if empty_msg == "ai.empty_response":
                    empty_msg = "\u041f\u0443\u0441\u0442\u043e\u0439 \u043e\u0442\u0432\u0435\u0442 \u043e\u0442 \u0418\u0418"
                self._add_message_bubble(empty_msg, is_error=True)
            elif is_agent:
                self._handle_agent_response(response)
            else:
                self._add_message_bubble(response)
                self._history.append({"role": "assistant", "content": response})
                self.db.save_chat_message(
                    "default", "assistant", response, self.engine.model
                )
        except Exception as e:
            import traceback

            tb = traceback.format_exc()
            self._add_message_bubble(f"Error: {str(e)}\n{tb[:200]}", is_error=True)
        finally:
            self._send_btn.setEnabled(True)
            self._send_btn.setText(I18n._("ai.send"))

    def _process_ai_stream(self, text: str) -> None:
        try:
            local_noauth = any(
                x in self.engine.api_url.lower()
                for x in ["localhost", "127.0.0.1", "ollama"]
            )
            dark = getattr(
                self, "_is_dark", lambda: ThemeEngine._current_theme == "dark"
            )()
            ai_color = "#2C3E50" if not dark else "#E0E0E8"
            if not self.engine.api_key and not local_noauth:
                self._add_message_bubble(I18n._("ai.no_key"), is_error=True)
                self._send_btn.setEnabled(True)
                self._send_btn.setText(I18n._("ai.send"))
                return

            is_agent = self.engine.mode == "agent"
            schema = self._get_schema_summary() if is_agent else ""
            self._stream_buffer = ""
            self._add_stream_bubble("")

            full_response = ""
            last_update = 0.0
            for token in self.engine.send_request_stream(
                self._history[:-1], text, schema
            ):
                if (
                    token.startswith("[ERROR")
                    or token.startswith("[HTTP Error")
                    or token.startswith("[Connection Error")
                ):
                    full_response = token
                    if self._stream_label:
                        self._stream_label.setHtml(
                            f"<div style='color:{ai_color};font-size:13px;'>{full_response}</div>"
                        )
                    QApplication.processEvents()
                    break
                full_response += token
                self._stream_buffer = full_response
                now = time.time()
                if now - last_update >= 0.05:
                    if self._stream_label:
                        html = markdown_to_html(full_response)
                        self._stream_label.setHtml(
                            f"<div style='color:{ai_color};font-size:13px;'>{html}</div>"
                        )
                    QApplication.processEvents()
                    last_update = now

            if (
                full_response.startswith("[ERROR")
                or full_response.startswith("[HTTP Error")
                or full_response.startswith("[Connection Error")
            ):
                display_text = full_response.strip("[]")
                self._add_message_bubble(display_text, is_error=True)
            elif not full_response.strip():
                empty_msg = I18n._("ai.empty_response")
                if empty_msg == "ai.empty_response":
                    empty_msg = "\u041f\u0443\u0441\u0442\u043e\u0439 \u043e\u0442\u0432\u0435\u0442 \u043e\u0442 \u0418\u0418"
                self._add_message_bubble(empty_msg, is_error=True)
            elif is_agent:
                self._handle_agent_response(full_response)
            else:
                if self._stream_label:
                    html = markdown_to_html(full_response)
                    self._stream_label.setHtml(
                        f"<div style='color:{ai_color};font-size:13px;'>{html}</div>"
                    )
                self._history.append({"role": "assistant", "content": full_response})
                self.db.save_chat_message(
                    "default", "assistant", full_response, self.engine.model
                )
        except Exception as e:
            import traceback

            tb = traceback.format_exc()
            self._add_message_bubble(f"Error: {str(e)}\n{tb[:200]}", is_error=True)
        finally:
            self._stream_label = None
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
            self._add_message_bubble(f"\U0001f914 {thought}")
            self._history.append(
                {"role": "assistant", "content": f"[Thought] {thought}"}
            )
            self.db.save_chat_message(
                "default", "assistant", f"[Thought] {thought}", self.engine.model
            )

        if action == "respond":
            msg = params.get("message", response)
            self._add_message_bubble(msg)
            self._history.append({"role": "assistant", "content": msg})
            self.db.save_chat_message("default", "assistant", msg, self.engine.model)
            return

        if action in (
            "add_record",
            "modify_record",
            "delete_record",
            "rename_column",
            "add_note",
        ):
            confirm_text = f"\u26a0\ufe0f AI wants to: {action}\n{json.dumps(params, ensure_ascii=False, indent=2)}"
            reply = QMessageBox.question(
                self,
                I18n._("ai.confirm_action").format(action=action),
                confirm_text,
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                result = self.engine.execute_action(action, params)
                self._add_message_bubble(f"\u2705 {result}")
                self._history.append({"role": "assistant", "content": result})
                self.db.save_chat_message(
                    "default", "assistant", result, self.engine.model
                )
            else:
                self._add_message_bubble("\u26d4 " + I18n._("ai.action_cancelled"))
                self._history.append(
                    {"role": "assistant", "content": I18n._("ai.action_cancelled")}
                )
        else:
            result = self.engine.execute_action(action, params)
            self._add_message_bubble(f"\U0001f4ca {result}")
            self._history.append({"role": "assistant", "content": result})

    def eventFilter(self, obj: QObject, event: Any) -> bool:
        if obj == self._input_edit and event.type() == event.KeyPress:
            if event.key() == Qt.Key_Return and event.modifiers() != Qt.ShiftModifier:
                if self._send_btn.isEnabled():
                    self._send_message()
                return True
        try:
            return super().eventFilter(obj, event)
        except AttributeError:
            return False


class AIChatDialog(QDialog, _BaseAIChat):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._setup_ai()
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

        heading = QLabel("\U0001f916 " + I18n._("ai.title"))
        heading.setProperty("heading", True)
        hl.addWidget(heading)
        hl.addStretch()

        self._config_toggle = GlassButton("\u2699")
        self._config_toggle.setProperty("flat", True)
        self._config_toggle.setFixedSize(32, 32)
        self._config_toggle.setCheckable(True)
        self._config_toggle.toggled.connect(self._toggle_config)
        hl.addWidget(self._config_toggle)

        self._clear_btn = GlassButton(I18n._("ai.clear"))
        self._clear_btn.setProperty("flat", True)
        self._clear_btn.clicked.connect(self._clear_history)
        hl.addWidget(self._clear_btn)

        close_btn = GlassButton("\u2715")
        close_btn.setProperty("flat", True)
        close_btn.setFixedSize(32, 32)
        close_btn.clicked.connect(self.accept)
        hl.addWidget(close_btn)

        layout.addWidget(header)

        # Config panel (collapsible)
        self._config_panel = QFrame()
        self._config_panel.setProperty("card", True)
        self._config_panel.setVisible(False)
        self._build_config_form()
        layout.addWidget(self._config_panel)

        # Messages area
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
        )

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

        self._attach_btn = GlassButton("\U0001f4ce")
        self._attach_btn.setFixedSize(36, 36)
        self._attach_btn.setToolTip(
            "\u041f\u0440\u0438\u043a\u0440\u0435\u043f\u0438\u0442\u044c \u0444\u0430\u0439\u043b"
        )
        self._attach_btn.clicked.connect(self._attach_file)
        input_layout.addWidget(self._attach_btn)

        self._send_btn = GlassButton(I18n._("ai.send"))
        self._send_btn.setProperty("success", True)
        self._send_btn.setFixedHeight(36)
        self._send_btn.clicked.connect(self._send_message)
        input_layout.addWidget(self._send_btn)

        layout.addWidget(input_frame)

    def _toggle_config(self, visible: bool) -> None:
        self._config_panel.setVisible(visible)


class AIChatInlineWidget(QWidget, _BaseAIChat):
    """Embedded AI chat widget for use as a tab."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._setup_ai()
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Config panel
        self._config_panel = QFrame()
        self._config_panel.setProperty("card", True)
        self._build_config_form()
        layout.addWidget(self._config_panel)

        # Messages area
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
        )

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

        self._attach_btn = GlassButton("\U0001f4ce")
        self._attach_btn.setFixedSize(36, 36)
        self._attach_btn.setToolTip(I18n._("ai.attach_tooltip"))
        self._attach_btn.clicked.connect(self._attach_file)
        input_layout.addWidget(self._attach_btn)

        self._send_btn = GlassButton(I18n._("ai.send"))
        self._send_btn.setProperty("success", True)
        self._send_btn.setFixedHeight(36)
        self._send_btn.clicked.connect(self._send_message)
        input_layout.addWidget(self._send_btn)

        self._settings_btn = GlassButton("\u2699")
        self._settings_btn.setProperty("flat", True)
        self._settings_btn.setFixedSize(32, 32)
        self._settings_btn.setToolTip(I18n._("ai.config"))
        self._settings_btn.clicked.connect(lambda: self._toggle_config())
        input_layout.addWidget(self._settings_btn)

        self._clear_btn = GlassButton(I18n._("ai.clear"))
        self._clear_btn.setProperty("flat", True)
        self._clear_btn.clicked.connect(self._clear_history)
        input_layout.addWidget(self._clear_btn)

        layout.addWidget(input_frame)

    def _toggle_config(self, visible: Optional[bool] = None) -> None:
        if visible is None:
            visible = not self._config_panel.isVisible()
        self._config_panel.setVisible(visible)

    def _save_config(self) -> None:
        super()._save_config()
        self._config_panel.setVisible(False)
