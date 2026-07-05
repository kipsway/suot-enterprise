import json
import traceback
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import QObject, QThread, pyqtSignal

from services.database import DatabaseManager
from app_core.i18n import I18n


API_PREFIX = "/api"


class APIHandler(BaseHTTPRequestHandler):
    db: DatabaseManager = DatabaseManager()
    api_key: str = ""
    server_instance: Optional["RESTAPIServer"] = None

    def log_message(self, fmt: str, *args: Any) -> None:
        if self.server_instance:
            self.server_instance._on_log(
                f"[REST API] {args[0]} {args[1]} {args[2]}" if args else fmt % args)

    def _send_json(self, data: Any, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "X-API-Key, Content-Type")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False,
                                     default=str).encode("utf-8"))

    def _send_error(self, message: str, status: int = 400) -> None:
        self._send_json({"error": message}, status)

    def _check_auth(self) -> bool:
        if not self.api_key:
            return True
        key = self.headers.get("X-API-Key", "")
        return key == self.api_key

    def do_OPTIONS(self) -> None:
        self._send_json({"ok": True})

    def do_GET(self) -> None:
        if not self._check_auth():
            self._send_error("Unauthorized", 401)
            return
        path = self.path.rstrip("/")
        try:
            if path == f"{API_PREFIX}/health":
                self._handle_health()
            elif path == f"{API_PREFIX}/violations":
                self._handle_violations()
            elif path.startswith(f"{API_PREFIX}/violations/"):
                self._handle_violation(path)
            elif path == f"{API_PREFIX}/employees":
                self._handle_employees()
            elif path.startswith(f"{API_PREFIX}/employees/"):
                self._handle_employee(path)
            elif path == f"{API_PREFIX}/companies":
                self._handle_companies()
            elif path == f"{API_PREFIX}/reminders":
                self._handle_reminders()
            elif path == f"{API_PREFIX}/stats":
                self._handle_stats()
            elif path == f"{API_PREFIX}/audit":
                self._handle_audit()
            else:
                self._send_error("Not found", 404)
        except Exception as exc:
            self._send_error(str(exc), 500)

    def do_POST(self) -> None:
        if not self._check_auth():
            self._send_error("Unauthorized", 401)
            return
        path = self.path.rstrip("/")
        try:
            if path == f"{API_PREFIX}/search":
                self._handle_search()
            else:
                self._send_error("Not found", 404)
        except Exception as exc:
            self._send_error(str(exc), 500)

    def _read_body(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", 0))
        if length:
            raw = self.rfile.read(length)
            return json.loads(raw.decode("utf-8"))
        return {}

    def _handle_health(self) -> None:
        self._send_json({
            "status": "ok",
            "version": "1.0",
            "timestamp": datetime.now().isoformat(),
        })

    def _handle_violations(self) -> None:
        params = self._parse_params()
        limit = min(int(params.get("limit", 50)), 500)
        status_filter = params.get("status", "")
        records = self.db.get_json_records("violations", limit=limit)
        if status_filter:
            records = [r for r in records
                       if r.get("data_json", r).get("Статус", "") == status_filter]
        results = [self._clean_record(r) for r in records]
        self._send_json({"count": len(results), "data": results})

    def _handle_violation(self, path: str) -> None:
        rid = self._parse_id(path, "violations")
        if rid is None:
            return
        record = self.db.get_json_record("violations", rid)
        if not record:
            self._send_error("Not found", 404)
            return
        self._send_json(self._clean_record(record))

    def _handle_employees(self) -> None:
        params = self._parse_params()
        limit = min(int(params.get("limit", 50)), 500)
        search = params.get("search", "").strip().lower()
        records = self.db.get_json_records("employees", limit=limit)
        if search:
            records = [r for r in records
                       if search in json.dumps(r.get("data_json", r),
                                               ensure_ascii=False).lower()]
        results = [self._clean_record(r) for r in records]
        self._send_json({"count": len(results), "data": results})

    def _handle_employee(self, path: str) -> None:
        rid = self._parse_id(path, "employees")
        if rid is None:
            return
        record = self.db.get_json_record("employees", rid)
        if not record:
            self._send_error("Not found", 404)
            return
        self._send_json(self._clean_record(record))

    def _handle_companies(self) -> None:
        companies = self.db.get_companies()
        self._send_json({"count": len(companies), "data": companies})

    def _handle_reminders(self) -> None:
        reminders = self.db.get_reminders(include_done=False)
        results = []
        for r in reminders:
            results.append({
                "id": r.get("id"),
                "title": r.get("title"),
                "description": r.get("description"),
                "due_date": r.get("due_date"),
                "check_interval": r.get("check_interval"),
                "is_done": r.get("is_done", False),
            })
        self._send_json({"count": len(results), "data": results})

    def _handle_stats(self) -> None:
        emps = self.db.get_json_records("employees")
        viols = self.db.get_json_records("violations")
        companies = self.db.get_companies()
        active = sum(1 for v in viols
                     if v.get("data_json", v).get("Статус", "") == "Активно")
        overdue_v = sum(1 for v in viols
                        if v.get("data_json", v).get("Статус", "") == "Просрочено")
        self._send_json({
            "employees": len(emps),
            "violations": len(viols),
            "violations_active": active,
            "violations_overdue": overdue_v,
            "companies": len(companies),
        })

    def _handle_audit(self) -> None:
        params = self._parse_params()
        limit = min(int(params.get("limit", 50)), 500)
        severity = params.get("severity", "")
        events = self.db.get_audit_events(limit=limit,
                                           severity=severity or None)
        self._send_json({"count": len(events), "data": events})

    def _handle_search(self) -> None:
        body = self._read_body()
        query = body.get("query", "").strip().lower()
        if not query:
            self._send_error("query is required")
            return
        results: Dict[str, List[Dict[str, Any]]] = {
            "employees": [], "violations": []}
        for table in ("employees", "violations"):
            records = self.db.get_json_records(table, limit=200)
            for r in records:
                dj = r.get("data_json", r)
                for val in dj.values():
                    if query in str(val).lower():
                        results[table].append(self._clean_record(r))
                        break
                if len(results[table]) >= 20:
                    break
        self._send_json(results)

    def _parse_params(self) -> Dict[str, str]:
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        return {k: v[0] for k, v in qs.items()}

    def _parse_id(self, path: str, table: str) -> Optional[int]:
        parts = path.rstrip("/").split("/")
        try:
            return int(parts[-1])
        except (ValueError, IndexError):
            self._send_error("Invalid ID", 400)
            return None

    def _clean_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        dj = record.get("data_json", record)
        result: Dict[str, Any] = {"id": record.get("id")}
        result.update(dj)
        if "data_json" in record:
            result["_meta"] = {
                "created_at": record.get("created_at"),
                "updated_at": record.get("updated_at"),
                "user_id": record.get("user_id"),
            }
        return result

    def do_HEAD(self) -> None:
        self._send_json({"ok": True})


class RESTAPIServer(QObject):
    log_received = pyqtSignal(str)
    started = pyqtSignal()
    stopped = pyqtSignal()

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._db = DatabaseManager()
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[QThread] = None
        self._port: int = 8888

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.isRunning()

    @property
    def port(self) -> int:
        return self._port

    def start(self, port: Optional[int] = None) -> None:
        if self.is_running:
            return
        api_key = self._db.get_setting("rest_api_key", "")
        enabled = self._db.get_setting("rest_api_enabled", "false")
        if enabled != "true":
            return
        self._port = port or int(self._db.get_setting("rest_api_port", "8888"))
        try:
            APIHandler.api_key = api_key
            APIHandler.server_instance = self
            self._server = HTTPServer(("127.0.0.1", self._port), APIHandler)
            self._thread = QThread(self)
            self._thread.started.connect(self._serve)
            self._thread.start()
            self.started.emit()
        except OSError as exc:
            self._on_log(f"Failed to start REST API: {exc}")
            self._server = None

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
        if self._thread:
            self._thread.quit()
            self._thread.wait(3000)
        self._server = None
        self._thread = None
        self.stopped.emit()

    def restart(self) -> None:
        self.stop()
        self.start()

    def _serve(self) -> None:
        if self._server:
            self._on_log(
                f"REST API server started on http://127.0.0.1:{self._port}")
            try:
                self._server.serve_forever()
            except Exception:
                pass

    def _on_log(self, message: str) -> None:
        self.log_received.emit(message)
