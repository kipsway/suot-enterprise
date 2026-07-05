import json
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

import requests
from PyQt5.QtCore import QObject, QThread, pyqtSignal

from services.database import DatabaseManager
from app_core.i18n import I18n


API_BASE = "https://api.telegram.org/bot{token}/{method}"


class TelegramBotWorker(QObject):
    message_received = pyqtSignal(str, int)
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
        resp = requests.get(url, params={
            "offset": self._offset,
            "timeout": 30,
        }, timeout=35)
        if resp.status_code != 200:
            return
        data = resp.json()
        if not data.get("ok"):
            return
        for update in data.get("result", []):
            self._offset = update["update_id"] + 1
            msg = update.get("message")
            if not msg:
                continue
            chat_id = msg["chat"]["id"]
            text = msg.get("text", "").strip()
            if text:
                self.message_received.emit(text, chat_id)

    def send_message(self, chat_id: int, text: str,
                     parse_mode: str = "HTML") -> bool:
        if not self._token:
            return False
        try:
            url = API_BASE.format(token=self._token, method="sendMessage")
            resp = requests.post(url, json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode,
            }, timeout=10)
            return resp.status_code == 200
        except Exception:
            return False


class TelegramBot(QObject):
    _instance: Optional["TelegramBot"] = None

    def __new__(cls, *args: Any, **kwargs: Any) -> "TelegramBot":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, parent: Optional[QObject] = None) -> None:
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        super().__init__(parent)
        self._db = DatabaseManager()
        self._worker: Optional[TelegramBotWorker] = None
        self._thread: Optional[QThread] = None
        self._chat_map: Dict[str, int] = {}
        self._command_handlers: Dict[str, Any] = {}
        self._load_chat_map()
        self._register_default_commands()

    def _load_chat_map(self) -> None:
        raw = self._db.get_setting("telegram_chat_map", "{}")
        try:
            self._chat_map = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            self._chat_map = {}

    def _save_chat_map(self) -> None:
        self._db.upsert_setting("telegram_chat_map",
                                json.dumps(self._chat_map, ensure_ascii=False))

    def _register_default_commands(self) -> None:
        self.register_command("start", self._cmd_start)
        self.register_command("help", self._cmd_help)
        self.register_command("violations", self._cmd_violations)
        self.register_command("reminders", self._cmd_reminders)
        self.register_command("stats", self._cmd_stats)
        self.register_command("search", self._cmd_search)
        self.register_command("register", self._cmd_register)
        self.register_command("employees", self._cmd_employees)

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

    def _on_error(self, msg: str) -> None:
        self._db.log_event(f"TelegramBot: {msg}", "WARNING")

    def _t(self, key: str, **fmt: Any) -> str:
        return I18n._(key).format(**fmt) if fmt else I18n._(key)

    def _safe_send(self, chat_id: int, text: str) -> bool:
        if self._worker:
            return self._worker.send_message(chat_id, text)
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

    def _cmd_start(self, chat_id: int, args: List[str]) -> None:
        self._safe_send(chat_id, self._t("telegram.welcome"))

    def _cmd_help(self, chat_id: int, args: List[str]) -> None:
        help_text = "\n".join([
            f"/{cmd} - {self._t(f'telegram.help_{cmd}', default=cmd)}"
            for cmd in ("start", "help", "violations", "reminders",
                        "stats", "search", "register", "employees")
        ])
        self._safe_send(chat_id, f"<b>{self._t('telegram.help_title')}</b>\n{help_text}")

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
        active = sum(1 for v in viols
                     if v.get("data_json", v).get("Статус", "") == "Активно")
        overdue_v = sum(1 for v in viols
                        if v.get("data_json", v).get("Статус", "") == "Просрочено")
        stats = "\n".join([
            f"<b>{self._t('telegram.stats_title')}</b>",
            f"👥 {self._t('telegram.stats_employees')}: {len(emps)}",
            f"⚠ {self._t('telegram.stats_violations')}: {len(viols)}",
            f"🔴 {self._t('telegram.stats_active')}: {active}",
            f"🚨 {self._t('telegram.stats_overdue')}: {overdue_v}",
            f"🏢 {self._t('telegram.stats_companies')}: {len(companies)}",
        ])
        self._safe_send(chat_id, stats)

    def _cmd_search(self, chat_id: int, args: List[str]) -> None:
        query = " ".join(args).strip().lower()
        if not query:
            self._safe_send(chat_id, self._t("telegram.search_hint"))
            return
        results: List[str] = []
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
            self._safe_send(chat_id,
                            f"<b>{self._t('telegram.search_title')}: {query}</b>\n" +
                            "\n".join(results))

    def _cmd_register(self, chat_id: int, args: List[str]) -> None:
        if not args:
            self._safe_send(chat_id, self._t("telegram.register_hint"))
            return
        username = args[0]
        users = self._db.fetch_all(
            "SELECT username FROM users WHERE username=?", (username,))
        if not users:
            self._safe_send(chat_id,
                            self._t("telegram.register_not_found").format(user=username))
            return
        self._chat_map[username] = chat_id
        self._save_chat_map()
        self._safe_send(chat_id,
                        self._t("telegram.register_ok").format(user=username))

    def send_notification(self, title: str, message: str,
                          severity: str = "info") -> int:
        icon = {"info": "ℹ", "warning": "⚠", "error": "🚨", "success": "✅"}.get(severity, "ℹ")
        text = f"{icon} <b>{title}</b>\n{message}"
        return self.broadcast(text)
