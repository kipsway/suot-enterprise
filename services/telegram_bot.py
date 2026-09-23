"""Telegram bot — full 19-command interface with inline keyboard."""

import json
import os
import tempfile
import time
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

import requests
from PyQt5.QtCore import QObject, QThread, pyqtSignal

from services.database import DatabaseManager
from app_core.i18n import I18n

API_BASE = "https://api.telegram.org/bot{token}/{method}"


def _make_keyboard(buttons: List[List[Dict[str, str]]]) -> Dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {"text": b["text"], "callback_data": b.get("callback_data", b["text"])}
                for b in row
            ]
            for row in buttons
        ]
    }


class TelegramBotWorker(QObject):
    message_received = pyqtSignal(str, int)
    callback_received = pyqtSignal(str, int, str)
    error_occurred = pyqtSignal(str)
    poll_started = pyqtSignal()
    poll_stopped = pyqtSignal()

    def __init__(self, token: str, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._token = token
        self._running = False
        self._offset = 0
        self._poll_interval = 2.0
        self._db = DatabaseManager()

    @property
    def token(self) -> str:
        return self._token

    @token.setter
    def token(self, value: str) -> None:
        self._token = value

    def stop(self) -> None:
        self._running = False

    def run(self) -> None:
        self._running = True
        self.poll_started.emit()
        while self._running:
            try:
                self._poll_once()
            except requests.ConnectionError:
                self.error_occurred.emit("Connection failed, retrying...")
            except Exception as exc:
                self.error_occurred.emit(str(exc))
            QThread.msleep(int(self._poll_interval * 1000))

    def _poll_once(self) -> None:
        if not self._token:
            return
        url = API_BASE.format(token=self._token, method="getUpdates")
        resp = requests.get(
            url, params={"offset": self._offset, "timeout": 30}, timeout=35
        )
        if resp.status_code != 200:
            return
        data = resp.json()
        if not data.get("ok"):
            return
        for update in data.get("result", []):
            self._offset = update["update_id"] + 1
            cb = update.get("callback_query")
            if cb:
                cb_data = cb.get("data", "")
                chat_id = cb["message"]["chat"]["id"]
                msg_id = cb["message"]["message_id"]
                self.callback_received.emit(cb_data, chat_id, cb["id"])
                continue
            msg = update.get("message")
            if not msg:
                continue
            chat_id = msg["chat"]["id"]
            text = msg.get("text", "").strip()
            if text:
                self.message_received.emit(text, chat_id)

    def send_message(
        self,
        chat_id: int,
        text: str,
        parse_mode: str = "HTML",
        reply_markup: Optional[Dict] = None,
    ) -> bool:
        if not self._token:
            return False
        try:
            payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
            if reply_markup:
                payload["reply_markup"] = json.dumps(reply_markup)
            url = API_BASE.format(token=self._token, method="sendMessage")
            resp = requests.post(url, json=payload, timeout=10)
            return resp.status_code == 200
        except Exception:
            return False

    def send_document(self, chat_id: int, file_path: str, caption: str = "") -> bool:
        if not self._token or not os.path.exists(file_path):
            return False
        try:
            url = API_BASE.format(token=self._token, method="sendDocument")
            with open(file_path, "rb") as f:
                resp = requests.post(
                    url,
                    data={"chat_id": chat_id, "caption": caption},
                    files={"document": f},
                    timeout=30,
                )
            return resp.status_code == 200
        except Exception:
            return False

    def answer_callback(self, cb_id: str, text: str = "") -> None:
        try:
            url = API_BASE.format(token=self._token, method="answerCallbackQuery")
            requests.post(
                url, json={"callback_query_id": cb_id, "text": text}, timeout=5
            )
        except Exception:
            pass

    def edit_message(
        self, chat_id: int, msg_id: int, text: str, reply_markup: Optional[Dict] = None
    ) -> bool:
        try:
            payload = {
                "chat_id": chat_id,
                "message_id": msg_id,
                "text": text,
                "parse_mode": "HTML",
            }
            if reply_markup:
                payload["reply_markup"] = json.dumps(reply_markup)
            url = API_BASE.format(token=self._token, method="editMessageText")
            resp = requests.post(url, json=payload, timeout=10)
            return resp.status_code == 200
        except Exception:
            return False


class TelegramBot(QObject):
    _instance: Optional["TelegramBot"] = None
    _PAGE_SIZE = 10
    _initialized: bool = False

    def __new__(cls, *args: Any, **kwargs: Any) -> "TelegramBot":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, parent: Optional[QObject] = None) -> None:
        if type(self)._initialized:
            return
        super().__init__(parent)
        type(self)._initialized = True
        self._db = DatabaseManager()
        self._worker: Optional[TelegramBotWorker] = None
        self._thread: Optional[QThread] = None
        self._chat_map: Dict[str, int] = {}
        self._command_handlers: Dict[str, Any] = {}
        self._paginated: Dict[str, tuple] = {}
        self._load_chat_map()
        self._register_commands()

    def _load_chat_map(self) -> None:
        raw = self._db.get_setting("telegram_chat_map", "{}")
        try:
            self._chat_map = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            self._chat_map = {}

    def _save_chat_map(self) -> None:
        self._db.upsert_setting(
            "telegram_chat_map", json.dumps(self._chat_map, ensure_ascii=False)
        )

    def _register_commands(self) -> None:
        for cmd in (
            "start",
            "help",
            "violations",
            "reminders",
            "stats",
            "search",
            "register",
            "employees",
            "employee",
            "violation",
            "company",
            "report",
            "template",
            "settings",
            "menu",
        ):
            handler = getattr(self, f"_cmd_{cmd}", None)
            if handler:
                self.register_command(cmd, handler)

    def register_command(self, command: str, handler: Any) -> None:
        self._command_handlers[command.lower()] = handler

    def start(self) -> None:
        token = self._db.get_setting("telegram_bot_token", "")
        enabled = self._db.get_setting("telegram_enabled", "false")
        if not token or enabled != "true":
            return
        if self._thread and self._thread.isRunning():
            return
        self._thread = QThread(self)
        self._worker = TelegramBotWorker(token)
        self._worker.moveToThread(self._thread)
        self._worker.message_received.connect(self._on_message)
        self._worker.callback_received.connect(self._on_callback)
        self._worker.error_occurred.connect(self._on_error)
        self._thread.started.connect(self._worker.run)
        self._thread.finished.connect(self._cleanup_thread)
        self._thread.start()

    def stop(self) -> None:
        if self._worker:
            self._worker.stop()
        if self._thread:
            self._thread.quit()
            self._thread.wait(3000)
            self._thread = None
            self._worker = None

    def restart(self) -> None:
        self.stop()
        self.start()

    def _cleanup_thread(self) -> None:
        if self._worker:
            self._worker.deleteLater()
            self._worker = None
        self._thread = None

    def _on_message(self, text: str, chat_id: int) -> None:
        parts = text.split()
        cmd = parts[0].lstrip("/").lower() if parts else ""
        args = parts[1:] if len(parts) > 1 else []
        handler = self._command_handlers.get(cmd)
        if handler:
            try:
                handler(chat_id, args)
            except Exception as exc:
                self._safe_send(chat_id, f"Error: {exc}")
        else:
            self._safe_send(chat_id, self._t("telegram.unknown_command"))

    def _on_callback(self, cb_data: str, chat_id: int, cb_id: str) -> None:
        parts = cb_data.split(":")
        action = parts[0]
        if action == "page" and len(parts) >= 4:
            key = parts[1]
            page = int(parts[2])
            total = int(parts[3])
            self._send_page(chat_id, key, page, total)
            if self._worker:
                self._worker.answer_callback(cb_id)
        elif action == "menu":
            self._cmd_menu(chat_id, [])
            if self._worker:
                self._worker.answer_callback(cb_id)
        else:
            if self._worker:
                self._worker.answer_callback(cb_id, "OK")

    def _on_error(self, msg: str) -> None:
        self._db.log_event(f"TelegramBot: {msg}", "WARNING")

    def _t(self, key: str, **fmt: Any) -> str:
        return I18n._(key).format(**fmt) if fmt else I18n._(key)

    def _safe_send(
        self, chat_id: int, text: str, reply_markup: Optional[Dict] = None
    ) -> bool:
        if self._worker:
            return self._worker.send_message(chat_id, text, reply_markup=reply_markup)
        return False

    def broadcast(self, text: str) -> int:
        sent = 0
        for username, chat_id in self._chat_map.items():
            if self._safe_send(chat_id, text):
                sent += 1
        return sent

    def send_to_user(self, username: str, text: str) -> bool:
        chat_id = self._chat_map.get(username)
        if chat_id:
            return self._safe_send(chat_id, text)
        return False

    def send_notification(
        self, title: str, message: str, severity: str = "info"
    ) -> int:
        icon = {"info": "ℹ", "warning": "⚠", "error": "🚨", "success": "✅"}.get(
            severity, "ℹ"
        )
        text = f"{icon} <b>{title}</b>\n{message}"
        return self.broadcast(text)

    def _build_menu_keyboard(self) -> Dict:
        return _make_keyboard(
            [
                [
                    {
                        "text": self._t("telegram.menu_employee"),
                        "callback_data": "menu:employee",
                    },
                    {
                        "text": self._t("telegram.menu_violation"),
                        "callback_data": "menu:violation",
                    },
                ],
                [
                    {
                        "text": self._t("telegram.menu_company"),
                        "callback_data": "menu:company",
                    },
                    {
                        "text": self._t("telegram.menu_stats"),
                        "callback_data": "menu:stats",
                    },
                ],
                [
                    {
                        "text": self._t("telegram.menu_report"),
                        "callback_data": "menu:report",
                    },
                    {
                        "text": self._t("telegram.menu_help"),
                        "callback_data": "menu:help",
                    },
                ],
            ]
        )

    def _paginate(self, key: str, items: List[str], page: int = 1) -> tuple:
        total = max(1, (len(items) + self._PAGE_SIZE - 1) // self._PAGE_SIZE)
        page = max(1, min(page, total))
        start = (page - 1) * self._PAGE_SIZE
        chunk = items[start : start + self._PAGE_SIZE]
        kb = _make_keyboard(
            [
                [
                    {
                        "text": f"<<",
                        "callback_data": f"page:{key}:{max(1, page - 1)}:{total}",
                    },
                    {"text": f"{page}/{total}", "callback_data": "menu:nop"},
                    {
                        "text": f">>",
                        "callback_data": f"page:{key}:{min(total, page + 1)}:{total}",
                    },
                ],
                [{"text": "🏠 Главное меню", "callback_data": "menu"}],
            ]
        )
        self._paginated[key] = (items, page)
        return "\n".join(chunk), kb

    def _send_page(self, chat_id: int, key: str, page: int, total: int) -> None:
        data = self._paginated.get(key)
        if not data:
            return
        text, kb = self._paginate(key, data[0], page)
        if self._worker:
            self._worker.send_message(chat_id, text, reply_markup=kb)

    # --- Command handlers ---

    def _cmd_start(self, chat_id: int, args: List[str]) -> None:
        self._safe_send(
            chat_id,
            self._t("telegram.welcome"),
            reply_markup=self._build_menu_keyboard(),
        )

    def _cmd_help(self, chat_id: int, args: List[str]) -> None:
        commands = [
            "start",
            "help",
            "menu",
            "violations",
            "employees",
            "employee",
            "violation",
            "company",
            "reminders",
            "stats",
            "search",
            "report",
            "template",
            "settings",
            "register",
        ]
        lines = [f"<b>{self._t('telegram.help_title')}</b>"]
        for cmd in commands:
            key = f"telegram.help_{cmd}"
            desc = self._t(key) if I18n._(key) != key else cmd
            lines.append(f"/{cmd} — {desc}")
        self._safe_send(chat_id, "\n".join(lines))

    def _cmd_menu(self, chat_id: int, args: List[str]) -> None:
        self._safe_send(
            chat_id,
            self._t("telegram.menu_main"),
            reply_markup=self._build_menu_keyboard(),
        )

    def _cmd_violations(self, chat_id: int, args: List[str]) -> None:
        limit = 10
        try:
            if args and args[0].isdigit():
                limit = min(int(args[0]), 50)
        except ValueError:
            pass
        records = self._db.get_json_records("violations", limit=limit)
        if not records:
            self._safe_send(chat_id, self._t("telegram.no_violations"))
            return
        lines = [f"<b>{self._t('telegram.violations_title')}</b>"]
        for r in records[:limit]:
            dj = r.get("data_json", r)
            desc = str(dj.get("Описание", f"#{r['id']}"))[:60]
            status = str(dj.get("Статус", "?"))
            deadline = str(dj.get("Срок устранения", ""))
            lines.append(f"#{r['id']} {desc} | {status} | {deadline}")
        self._safe_send(chat_id, "\n".join(lines))

    def _cmd_employees(self, chat_id: int, args: List[str]) -> None:
        limit = 10
        try:
            if args and args[0].isdigit():
                limit = min(int(args[0]), 50)
        except ValueError:
            pass
        records = self._db.get_json_records("employees", limit=limit)
        if not records:
            self._safe_send(chat_id, self._t("telegram.no_employees"))
            return
        lines = [f"<b>{self._t('telegram.employees_title')}</b>"]
        for r in records[:limit]:
            dj = r.get("data_json", r)
            name = str(dj.get("ФИО", f"#{r['id']}"))
            company = str(dj.get("Фирма", ""))
            lines.append(f"#{r['id']} {name} | {company}")
        self._safe_send(chat_id, "\n".join(lines))

    def _cmd_employee(self, chat_id: int, args: List[str]) -> None:
        query = " ".join(args).strip().lower()
        if not query:
            self._safe_send(chat_id, self._t("telegram.help_employee"))
            return
        records = self._db.get_json_records("employees", limit=1000)
        matches = []
        for r in records:
            dj = r.get("data_json", r)
            name = str(dj.get("ФИО", "")).lower()
            if query in name:
                matches.append((r["id"], dj))
        if not matches:
            self._safe_send(chat_id, self._t("telegram.employee_not_found"))
            return
        items = [f"<b>{self._t('telegram.employee_title')}</b>"]
        for rid, dj in matches[:5]:
            items.append(
                f"#{rid} {dj.get('ФИО', '?')}\n"
                f"🏢 {dj.get('Фирма', '')}\n"
                f"💼 {dj.get('Должность', '')}"
            )
        self._safe_send(chat_id, "\n\n".join(items))

    def _cmd_violation(self, chat_id: int, args: List[str]) -> None:
        if not args:
            self._safe_send(chat_id, self._t("telegram.help_violation"))
            return
        rid = args[0].lstrip("#")
        if not rid.isdigit():
            self._safe_send(chat_id, self._t("telegram.help_violation"))
            return
        records = self._db.get_json_records("violations", limit=5000)
        match = None
        for r in records:
            if str(r["id"]) == rid:
                match = r.get("data_json", r)
                break
        if not match:
            self._safe_send(chat_id, self._t("telegram.violation_not_found"))
            return
        text = (
            f"<b>{self._t('telegram.violation_title')} #{rid}</b>\n"
            f"📋 {match.get('Описание', '')}\n"
            f"📌 Статус: {match.get('Статус', '?')}\n"
            f"🏢 {match.get('Фирма', '')}\n"
            f"📅 Срок: {match.get('Срок устранения', '')}\n"
            f"💰 Штраф: {match.get('Штраф', '')}"
        )
        self._safe_send(chat_id, text)

    def _cmd_company(self, chat_id: int, args: List[str]) -> None:
        query = " ".join(args).strip().lower()
        if not query:
            self._safe_send(chat_id, self._t("telegram.help_company"))
            return
        companies = self._db.get_companies()
        matches = [c for c in companies if query in str(c.get("name", "")).lower()]
        if not matches:
            self._safe_send(chat_id, self._t("telegram.no_company"))
            return
        items = [f"<b>{self._t('telegram.company_title')}</b>"]
        for c in matches[:5]:
            items.append(f"#{c['id']} {c.get('name', '?')}\n📍 {c.get('address', '')}")
        self._safe_send(chat_id, "\n\n".join(items))

    def _cmd_reminders(self, chat_id: int, args: List[str]) -> None:
        reminders = self._db.get_due_reminders()
        overdue = []
        upcoming = []
        now = datetime.now()
        for r in reminders:
            due_str = r.get("due_date", "")
            try:
                p = due_str.split(".")
                if len(p) == 3:
                    due = datetime(int(p[2]), int(p[1]), int(p[0]))
                    if due <= now:
                        overdue.append(r)
                    else:
                        upcoming.append(r)
            except Exception:
                pass
        lines = []
        if overdue:
            lines.append(f"<b>{self._t('telegram.overdue_title')}</b>")
            for r in overdue[:10]:
                lines.append(f"🔴 {r.get('title', '?')} — {r.get('due_date', '')}")
        if upcoming:
            lines.append(f"<b>{self._t('telegram.upcoming_title')}</b>")
            for r in upcoming[:10]:
                lines.append(f"🟡 {r.get('title', '?')} — {r.get('due_date', '')}")
        if not lines:
            lines.append(self._t("telegram.no_reminders"))
        self._safe_send(chat_id, "\n".join(lines))

    def _cmd_stats(self, chat_id: int, args: List[str]) -> None:
        emps = self._db.get_json_records("employees")
        viols = self._db.get_json_records("violations")
        companies = self._db.get_companies()
        active = sum(
            1 for v in viols if v.get("data_json", v).get("Статус", "") == "Активно"
        )
        overdue_v = sum(
            1 for v in viols if v.get("data_json", v).get("Статус", "") == "Просрочено"
        )
        text = "\n".join(
            [
                f"<b>{self._t('telegram.stats_title')}</b>",
                f"👥 {self._t('telegram.stats_employees')}: {len(emps)}",
                f"⚠ {self._t('telegram.stats_violations')}: {len(viols)}",
                f"🔴 {self._t('telegram.stats_active')}: {active}",
                f"🚨 {self._t('telegram.stats_overdue')}: {overdue_v}",
                f"🏢 {self._t('telegram.stats_companies')}: {len(companies)}",
            ]
        )
        self._safe_send(chat_id, text)

    def _cmd_search(self, chat_id: int, args: List[str]) -> None:
        query = " ".join(args).strip().lower()
        if not query:
            self._safe_send(chat_id, self._t("telegram.search_hint"))
            return
        results = []
        for table in ("employees", "violations"):
            records = self._db.get_json_records(table, limit=200)
            for r in records:
                dj = r.get("data_json", r)
                for val in dj.values():
                    if query in str(val).lower():
                        label = "👤" if table == "employees" else "⚠"
                        name = dj.get("ФИО", dj.get("Описание", f"#{r['id']}"))
                        results.append(f"{label} #{r['id']} {str(name)[:50]}")
                        break
                if len(results) >= 10:
                    break
            if len(results) >= 10:
                break
        if not results:
            self._safe_send(chat_id, self._t("telegram.no_results"))
        else:
            text = f"<b>{self._t('telegram.search_title')}: {query}</b>\n" + "\n".join(
                results
            )
            self._safe_send(chat_id, text)

    def _cmd_register(self, chat_id: int, args: List[str]) -> None:
        if not args:
            self._safe_send(chat_id, self._t("telegram.register_hint"))
            return
        username = args[0]
        users = self._db.fetch_all(
            "SELECT username FROM users WHERE username=?", (username,)
        )
        if not users:
            self._safe_send(
                chat_id, self._t("telegram.register_not_found").format(user=username)
            )
            return
        self._chat_map[username] = chat_id
        self._save_chat_map()
        self._safe_send(chat_id, self._t("telegram.register_ok").format(user=username))

    def _cmd_report(self, chat_id: int, args: List[str]) -> None:
        try:
            from services.excel_service import export_to_excel
        except ImportError:
            self._safe_send(chat_id, "Excel export not available")
            return
        self._safe_send(chat_id, self._t("telegram.report_generating"))
        tmp = os.path.join(
            tempfile.gettempdir(), f"report_{chat_id}_{int(time.time())}.xlsx"
        )
        headers = ["ID", "Описание", "Статус", "Срок", "Фирма"]
        records = self._db.get_json_records("violations", limit=100)
        data = []
        for r in records:
            dj = r.get("data_json", r)
            data.append(
                {
                    "ID": r["id"],
                    "Описание": dj.get("Описание", ""),
                    "Статус": dj.get("Статус", ""),
                    "Срок": dj.get("Срок устранения", ""),
                    "Фирма": dj.get("Фирма", ""),
                }
            )
        if export_to_excel(data, headers, tmp, "Report"):
            if self._worker:
                self._worker.send_document(
                    chat_id, tmp, self._t("telegram.report_ready")
                )
            try:
                os.unlink(tmp)
            except Exception:
                pass
        else:
            self._safe_send(chat_id, "Report generation failed")

    def _cmd_template(self, chat_id: int, args: List[str]) -> None:
        query = " ".join(args).strip().lower()
        if not query:
            templates = self._db.get_json_records("print_templates", limit=50)
            if templates:
                names = [
                    str(t.get("data_json", t).get("name", f"#{t['id']}"))
                    for t in templates
                ]
                text, kb = self._paginate("templates", names)
                self._safe_send(
                    chat_id, self._t("telegram.template_choose"), reply_markup=kb
                )
            else:
                self._safe_send(chat_id, self._t("telegram.template_not_found"))
            return
        templates = self._db.get_json_records("print_templates", limit=200)
        match = None
        for t in templates:
            name = str(t.get("data_json", t).get("name", ""))
            if query in name.lower():
                match = t
                break
        if not match:
            self._safe_send(chat_id, self._t("telegram.template_not_found"))
            return
        content = match.get("data_json", match).get("content", "")
        tmp = os.path.join(tempfile.gettempdir(), f"template_{chat_id}.html")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(content)
        if self._worker:
            self._worker.send_document(
                chat_id,
                tmp,
                f"{self._t('telegram.template_ready')} {match.get('data_json', match).get('name', '')}",
            )
        try:
            os.unlink(tmp)
        except Exception:
            pass

    def _cmd_settings(self, chat_id: int, args: List[str]) -> None:
        key = f"tg_notify_{chat_id}"
        if args:
            if args[0] in ("on", "1", "yes"):
                self._db.upsert_setting(key, "1")
                self._safe_send(chat_id, self._t("telegram.settings_on"))
            elif args[0] in ("off", "0", "no"):
                self._db.upsert_setting(key, "0")
                self._safe_send(chat_id, self._t("telegram.settings_off"))
            else:
                self._safe_send(chat_id, self._t("telegram.settings_hint"))
            return
        enabled = self._db.get_setting(key, "1") == "1"
        status = "✅ Вкл" if enabled else "❌ Выкл"
        self._safe_send(
            chat_id,
            f"<b>{self._t('telegram.settings_title')}</b>\n{status}\n{self._t('telegram.settings_hint')}",
        )
