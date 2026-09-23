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
                f"[REST API] {args[0]} {args[1]} {args[2]}" if args else fmt % args
            )

    def _send_json(self, data: Any, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header(
            "Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS"
        )
        self.send_header("Access-Control-Allow-Headers", "X-API-Key, Content-Type")
        self.end_headers()
        self.wfile.write(
            json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        )

    def _send_error(self, message: str, status: int = 400) -> None:
        self._send_json({"error": message}, status)

    def _check_auth(self) -> bool:
        if not self.api_key:
            return True
        key = self.headers.get("X-API-Key", "")
        return key == self.api_key

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header(
            "Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS"
        )
        self.send_header("Access-Control-Allow-Headers", "X-API-Key, Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        path = self.path.rstrip("/")
        if path == "/" or path == "" or path == "/dashboard":
            self._serve_dashboard()
            return
        if path == f"{API_PREFIX}/docs":
            self._serve_swagger()
            return
        if path == f"{API_PREFIX}/openapi.json":
            self._serve_openapi_spec()
            return
        if not self._check_auth():
            self._send_error("Unauthorized", 401)
            return
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
            elif path.startswith(f"{API_PREFIX}/companies/"):
                self._handle_company(path)
            elif path == f"{API_PREFIX}/reminders":
                self._handle_reminders()
            elif path == f"{API_PREFIX}/stats":
                self._handle_stats()
            elif path == f"{API_PREFIX}/dashboard":
                self._handle_dashboard_json()
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
            elif path == f"{API_PREFIX}/violations":
                self._handle_create_violation()
            elif path == f"{API_PREFIX}/employees":
                self._handle_create_employee()
            elif path == f"{API_PREFIX}/companies":
                self._handle_create_company()
            else:
                self._send_error("Not found", 404)
        except Exception as exc:
            self._send_error(str(exc), 500)

    def do_PUT(self) -> None:
        if not self._check_auth():
            self._send_error("Unauthorized", 401)
            return
        path = self.path.rstrip("/")
        try:
            if path.startswith(f"{API_PREFIX}/violations/"):
                self._handle_update_violation(path)
            elif path.startswith(f"{API_PREFIX}/employees/"):
                self._handle_update_employee(path)
            elif path.startswith(f"{API_PREFIX}/companies/"):
                self._handle_update_company(path)
            else:
                self._send_error("Not found", 404)
        except Exception as exc:
            self._send_error(str(exc), 500)

    def do_DELETE(self) -> None:
        if not self._check_auth():
            self._send_error("Unauthorized", 401)
            return
        path = self.path.rstrip("/")
        try:
            if path.startswith(f"{API_PREFIX}/violations/"):
                self._handle_delete_violation(path)
            elif path.startswith(f"{API_PREFIX}/employees/"):
                self._handle_delete_employee(path)
            elif path.startswith(f"{API_PREFIX}/companies/"):
                self._handle_delete_company(path)
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
        self._send_json(
            {
                "status": "ok",
                "version": "1.0",
                "timestamp": datetime.now().isoformat(),
            }
        )

    def _handle_violations(self) -> None:
        params = self._parse_params()
        limit = min(int(params.get("limit", 50)), 500)
        status_filter = params.get("status", "")
        records = self.db.get_json_records("violations", limit=limit)
        if status_filter:
            records = [
                r
                for r in records
                if r.get("data_json", r).get("Статус", "") == status_filter
            ]
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
            records = [
                r
                for r in records
                if search
                in json.dumps(r.get("data_json", r), ensure_ascii=False).lower()
            ]
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

    def _handle_company(self, path: str) -> None:
        rid = self._parse_id(path, "companies")
        if rid is None:
            return
        company = self.db.get_company(rid)
        if not company:
            self._send_error("Not found", 404)
            return
        self._send_json(company)

    def _handle_reminders(self) -> None:
        reminders = self.db.get_reminders(include_done=False)
        results = []
        for r in reminders:
            results.append(
                {
                    "id": r.get("id"),
                    "title": r.get("title"),
                    "description": r.get("description"),
                    "due_date": r.get("due_date"),
                    "check_interval": r.get("check_interval"),
                    "is_done": r.get("is_done", False),
                }
            )
        self._send_json({"count": len(results), "data": results})

    def _handle_stats(self) -> None:
        emps = self.db.get_json_records("employees")
        viols = self.db.get_json_records("violations")
        companies = self.db.get_companies()
        active = sum(
            1 for v in viols if v.get("data_json", v).get("Статус", "") == "Активно"
        )
        overdue_v = sum(
            1 for v in viols if v.get("data_json", v).get("Статус", "") == "Просрочено"
        )
        self._send_json(
            {
                "employees": len(emps),
                "violations": len(viols),
                "violations_active": active,
                "violations_overdue": overdue_v,
                "companies": len(companies),
            }
        )

    def _handle_audit(self) -> None:
        params = self._parse_params()
        limit = min(int(params.get("limit", 50)), 500)
        severity = params.get("severity", "")
        events = self.db.get_audit_events(limit=limit, severity=severity or None)
        self._send_json({"count": len(events), "data": events})

    def _handle_search(self) -> None:
        body = self._read_body()
        query = body.get("query", "").strip().lower()
        if not query:
            self._send_error("query is required")
            return
        results: Dict[str, List[Dict[str, Any]]] = {"employees": [], "violations": []}
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

    # --- CRUD helpers ---

    def _delete_json_record(self, table: str, record_id: int) -> bool:
        try:
            self.db.conn.execute(f"DELETE FROM {table} WHERE id=?", (record_id,))
            self.db.conn.commit()
            self.db.log_event(
                f"Record deleted via REST API",
                "WARNING",
                {"table": table, "id": record_id},
            )
            return True
        except Exception:
            self.db.conn.rollback()
            return False

    # --- CRUD: Violations ---

    def _handle_create_violation(self) -> None:
        body = self._read_body()
        if not body:
            self._send_error("Empty body", 400)
            return
        rid = self.db.save_json_record("violations", 0, body, user_id=1)
        self._send_json({"id": rid, "message": "Created"}, 201)

    def _handle_update_violation(self, path: str) -> None:
        rid = self._parse_id(path, "violations")
        if rid is None:
            return
        body = self._read_body()
        if not body:
            self._send_error("Empty body", 400)
            return
        record = self.db.get_json_record("violations", rid)
        if not record:
            self._send_error("Not found", 404)
            return
        self.db.save_json_record("violations", rid, body, user_id=1)
        self._send_json({"id": rid, "message": "Updated"})

    def _handle_delete_violation(self, path: str) -> None:
        rid = self._parse_id(path, "violations")
        if rid is None:
            return
        if not self._delete_json_record("violations", rid):
            self._send_error("Delete failed", 500)
            return
        self._send_json({"id": rid, "message": "Deleted"})

    # --- CRUD: Employees ---

    def _handle_create_employee(self) -> None:
        body = self._read_body()
        if not body:
            self._send_error("Empty body", 400)
            return
        rid = self.db.save_json_record("employees", 0, body, user_id=1)
        self._send_json({"id": rid, "message": "Created"}, 201)

    def _handle_update_employee(self, path: str) -> None:
        rid = self._parse_id(path, "employees")
        if rid is None:
            return
        body = self._read_body()
        if not body:
            self._send_error("Empty body", 400)
            return
        record = self.db.get_json_record("employees", rid)
        if not record:
            self._send_error("Not found", 404)
            return
        self.db.save_json_record("employees", rid, body, user_id=1)
        self._send_json({"id": rid, "message": "Updated"})

    def _handle_delete_employee(self, path: str) -> None:
        rid = self._parse_id(path, "employees")
        if rid is None:
            return
        if not self._delete_json_record("employees", rid):
            self._send_error("Delete failed", 500)
            return
        self._send_json({"id": rid, "message": "Deleted"})

    # --- CRUD: Companies ---

    def _handle_create_company(self) -> None:
        body = self._read_body()
        name = body.get("name", "").strip()
        if not name:
            self._send_error("name is required", 400)
            return
        rid = self.db.save_company(
            name=name,
            address=body.get("address", ""),
            contact=body.get("contact", ""),
            data_json=body.get("data_json", {}),
        )
        self._send_json({"id": rid, "message": "Created"}, 201)

    def _handle_update_company(self, path: str) -> None:
        rid = self._parse_id(path, "companies")
        if rid is None:
            return
        body = self._read_body()
        if not body:
            self._send_error("Empty body", 400)
            return
        company = self.db.get_company(rid)
        if not company:
            self._send_error("Not found", 404)
            return
        self.db.save_company(
            name=body.get("name", company.get("name", "")),
            address=body.get("address", company.get("address", "")),
            contact=body.get("contact", company.get("contact", "")),
            data_json=body.get("data_json", {}),
            company_id=rid,
        )
        self._send_json({"id": rid, "message": "Updated"})

    def _handle_delete_company(self, path: str) -> None:
        rid = self._parse_id(path, "companies")
        if rid is None:
            return
        if not self.db.delete_company(rid):
            self._send_error("Delete failed", 500)
            return
        self._send_json({"id": rid, "message": "Deleted"})

    # --- OpenAPI / Swagger ---

    def _serve_openapi_spec(self) -> None:
        P = {
            "summary": "OK",
            "security": [],
            "responses": {"200": {"description": "OK"}},
        }
        spec = {
            "openapi": "3.0.3",
            "info": {
                "title": "SUOT Enterprise REST API",
                "version": "1.0.0",
                "description": "REST API for SUOT Enterprise — full CRUD on violations, employees, companies.",
            },
            "servers": [
                {"url": "http://127.0.0.1:8888", "description": "Local server"}
            ],
            "security": [{"ApiKeyAuth": []}],
            "components": {
                "securitySchemes": {
                    "ApiKeyAuth": {
                        "type": "apiKey",
                        "in": "header",
                        "name": "X-API-Key",
                    },
                },
            },
            "paths": self._build_openapi_paths(),
        }
        self._send_json(spec)

    def _build_openapi_paths(self) -> Dict[str, Any]:
        R = {"required": True, "schema": {"type": "integer"}}
        O = {"content": {"application/json": {"schema": {"type": "object"}}}}
        C = {
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "address": {"type": "string"},
                            "contact": {"type": "string"},
                        },
                        "required": ["name"],
                    }
                }
            }
        }
        S = {
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                    }
                }
            }
        }
        P = lambda n, **kw: [{"name": n, "in": "path", **R, **kw}]
        Q = {"name": "limit", "in": "query", "schema": {"type": "integer"}}
        Q2 = {"name": "status", "in": "query", "schema": {"type": "string"}}
        Q3 = {"name": "search", "in": "query", "schema": {"type": "string"}}
        Q4 = {"name": "severity", "in": "query", "schema": {"type": "string"}}
        D200 = {"responses": {"200": {"description": "OK"}}}
        paths = dict()
        paths["/api/health"] = {
            "get": {"summary": "Health check", "security": [], **D200}
        }
        paths["/api/stats"] = {
            "get": {
                "summary": "Aggregate statistics",
                "responses": {"200": {"description": "JSON stats"}},
            }
        }
        paths["/api/violations"] = {
            "get": {
                "summary": "List violations",
                "parameters": [Q, Q2],
                "responses": {"200": {"description": "Violations list"}},
            },
            "post": {
                "summary": "Create violation",
                "requestBody": O,
                "responses": {"201": {"description": "Created"}},
            },
        }
        paths["/api/violations/{id}"] = {
            "get": {
                "summary": "Get violation by ID",
                "parameters": P("id"),
                "responses": {"200": {"description": "Violation detail"}},
            },
            "put": {
                "summary": "Update violation",
                "parameters": P("id"),
                "requestBody": O,
                "responses": {"200": {"description": "Updated"}},
            },
            "delete": {
                "summary": "Delete violation",
                "parameters": P("id"),
                "responses": {"200": {"description": "Deleted"}},
            },
        }
        paths["/api/employees"] = {
            "get": {
                "summary": "List employees",
                "parameters": [Q, Q3],
                "responses": {"200": {"description": "Employees list"}},
            },
            "post": {
                "summary": "Create employee",
                "requestBody": O,
                "responses": {"201": {"description": "Created"}},
            },
        }
        paths["/api/employees/{id}"] = {
            "get": {
                "summary": "Get employee by ID",
                "parameters": P("id"),
                "responses": {"200": {"description": "Employee detail"}},
            },
            "put": {
                "summary": "Update employee",
                "parameters": P("id"),
                "requestBody": O,
                "responses": {"200": {"description": "Updated"}},
            },
            "delete": {
                "summary": "Delete employee",
                "parameters": P("id"),
                "responses": {"200": {"description": "Deleted"}},
            },
        }
        paths["/api/companies"] = {
            "get": {
                "summary": "List companies",
                "responses": {"200": {"description": "Companies list"}},
            },
            "post": {
                "summary": "Create company",
                "requestBody": C,
                "responses": {"201": {"description": "Created"}},
            },
        }
        paths["/api/companies/{id}"] = {
            "get": {
                "summary": "Get company by ID",
                "parameters": P("id"),
                "responses": {"200": {"description": "Company detail"}},
            },
            "put": {
                "summary": "Update company",
                "parameters": P("id"),
                "requestBody": O,
                "responses": {"200": {"description": "Updated"}},
            },
            "delete": {
                "summary": "Delete company",
                "parameters": P("id"),
                "responses": {"200": {"description": "Deleted"}},
            },
        }
        paths["/api/reminders"] = {
            "get": {
                "summary": "List pending reminders",
                "responses": {"200": {"description": "Reminders list"}},
            }
        }
        paths["/api/audit"] = {
            "get": {
                "summary": "Audit log",
                "parameters": [Q, Q4],
                "responses": {"200": {"description": "Audit events"}},
            }
        }
        paths["/api/search"] = {
            "post": {
                "summary": "Full-text search",
                "requestBody": S,
                "responses": {"200": {"description": "Search results"}},
            }
        }
        paths["/api/dashboard"] = {
            "get": {
                "summary": "Dashboard data",
                "responses": {"200": {"description": "Dashboard JSON"}},
            }
        }
        return paths

    def _serve_swagger(self) -> None:
        html = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>SUOT API — Swagger UI</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css">
</head>
<body style="margin:0">
<div id="swagger-ui"></div>
<script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
<script>
SwaggerUIBundle({
  url: '/api/openapi.json',
  dom_id: '#swagger-ui',
  presets: [SwaggerUIBundle.presets.apis],
  layout: 'BaseLayout',
});
</script>
</body>
</html>"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

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

    def _serve_dashboard(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(_DASHBOARD_HTML.encode("utf-8"))

    def _handle_dashboard_json(self) -> None:
        from datetime import datetime, timedelta

        emps = self.db.get_json_records("employees")
        viols = self.db.get_json_records("violations")
        incidents = self.db.get_json_records("incidents")
        companies = self.db.get_companies()
        training = self.db.get_json_records("training")
        ppe = self.db.get_json_records("ppe")
        permits = self.db.get_json_records("permits")
        audit = self.db.get_audit_events(limit=10)

        now = datetime.now()
        month_start = now.strftime("%Y-%m")
        viols_month = sum(
            1
            for v in viols
            if v.get("data_json", {}).get("date", "").startswith(month_start)
        )
        incidents_month = sum(
            1
            for inc in incidents
            if inc.get("data_json", {}).get("date", "").startswith(month_start)
        )
        overdue_v = sum(
            1 for v in viols if v.get("data_json", {}).get("status", "") == "Просрочено"
        )
        expired_training = sum(
            1
            for t in training
            if t.get("data_json", {}).get("status", "") == "Просрочено"
        )

        recent = []
        for table, label in [
            ("violations", "Нарушения"),
            ("incidents", "Происшествия"),
            ("employees", "Сотрудники"),
            ("training", "Обучение"),
        ]:
            records = self.db.get_json_records(table, limit=3)
            for r in records:
                dj = r.get("data_json", {})
                recent.append(
                    {
                        "table": label,
                        "id": r.get("id", 0),
                        "title": (
                            dj.get("description")
                            or dj.get("full_name")
                            or dj.get("name")
                            or ""
                        ),
                        "date": dj.get("date", dj.get("created_at", ""))[:10],
                    }
                )
        recent.sort(key=lambda x: x["date"], reverse=True)
        recent = recent[:8]

        self._send_json(
            {
                "stats": {
                    "employees": len(emps),
                    "violations": len(viols),
                    "violations_active": sum(
                        1
                        for v in viols
                        if v.get("data_json", {}).get("status", "") == "Открыто"
                    ),
                    "violations_overdue": overdue_v,
                    "incidents": len(incidents),
                    "incidents_month": incidents_month,
                    "violations_month": viols_month,
                    "companies": len(companies),
                    "training": len(training),
                    "training_expired": expired_training,
                    "ppe": len(ppe),
                    "permits": len(permits),
                },
                "recent": recent,
                "timestamp": now.isoformat(),
            }
        )


_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>SUOT Enterprise — Dashboard</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,'Segoe UI',sans-serif;background:#0d0d10;color:#e0e0e8;padding:20px;min-height:100vh}
h1{font-size:24px;margin-bottom:8px;font-weight:700}
.subtitle{color:#8e8e93;font-size:13px;margin-bottom:24px}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:12px;margin-bottom:28px}
.card{background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.08);border-radius:14px;padding:18px 16px}
.card .val{font-size:28px;font-weight:700;margin-bottom:4px}
.card .lbl{font-size:12px;color:#8e8e93}
.card.red .val{color:#ff453a}
.card.orange .val{color:#ff9f0a}
.card.green .val{color:#30d158}
.card.blue .val{color:#0a84ff}
.card.purple .val{color:#bf5af2}
h2{font-size:16px;margin-bottom:12px;font-weight:600}
.recent{background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.06);border-radius:14px;padding:16px}
.recent table{width:100%;border-collapse:collapse;font-size:13px}
.recent td,.recent th{padding:10px 12px;text-align:left;border-bottom:1px solid rgba(255,255,255,0.04)}
.recent th{color:#8e8e93;font-weight:500;font-size:11px;text-transform:uppercase}
.recent tr:last-child td{border:none}
.badge{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;background:rgba(10,132,255,0.2);color:#0a84ff}
.error{color:#ff453a;padding:20px;text-align:center}
.loading{text-align:center;padding:40px;color:#8e8e93}
@media(max-width:600px){.cards{grid-template-columns:repeat(2,1fr)}h1{font-size:20px}}
</style>
</head>
<body>
<h1>SUOT Enterprise</h1>
<p class="subtitle" id="ts">Загрузка...</p>
<div id="app"><div class="loading">Загрузка данных...</div></div>
<script>
async function load(){
 try{
  const r=await fetch('/api/dashboard');
  if(!r.ok)throw new Error('HTTP '+r.status);
  const d=await r.json();
  const s=d.stats;
  document.getElementById('ts').textContent='Обновлено: '+new Date(d.timestamp).toLocaleString('ru-RU');
  document.getElementById('app').innerHTML=
   '<div class="cards">'+
   c('blue',s.employees,'Сотрудники')+
   c('orange',s.violations,'Нарушения всего')+
   c('red',s.violations_overdue,'Просрочено')+
   c('purple',s.incidents,'Происшествия')+
   c('green',s.training,'Обучение')+
   c('orange',s.training_expired,'Просрочено обучение')+
   c('blue',s.ppe,'СИЗ')+
   c('purple',s.permits,'Наряды-допуски')+
   c('green',s.companies,'Компании')+
   '</div>'+
   '<h2>Последние записи</h2>'+
   '<div class="recent"><table><tr><th>Дата</th><th>Модуль</th><th>Запись</th></tr>'+
   (d.recent||[]).map(r=>'<tr><td style="color:#8e8e93">'+r.date+'</td><td><span class="badge">'+r.table+'</span></td><td>'+esc(r.title)+'</td></tr>').join('')+
   '</table></div>';
 }catch(e){
  document.getElementById('app').innerHTML='<div class="error">Ошибка: '+e.message+'</div>';
 }
}
function c(clr,val,lbl){return '<div class="card '+clr+'"><div class="val">'+val+'</div><div class="lbl">'+lbl+'</div></div>'}
function esc(s){const d=document.createElement('div');d.textContent=s||'';return d.innerHTML}
load();
setInterval(load,30000);
</script>
</body>
</html>"""


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
            self._on_log(f"REST API server started on http://127.0.0.1:{self._port}")
            try:
                self._server.serve_forever()
            except Exception:
                pass

    def _on_log(self, message: str) -> None:
        self.log_received.emit(message)
