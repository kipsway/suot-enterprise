"""Аудит безопасности 2.2.3: 25 проверок закрытых исправлений.

Проверяет: allowlist колонок custom/values, отзыв сессий при смене/сбросе/
блокировке пароля, маскировку ai_api_key, SSRF-защиту /update/check,
валидацию update_url, auth на /update/open, escape в /print/preview,
единую версию API.

Запуск:  python tests/test_security_audit.py
"""

import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

TMP_DB = os.path.join(tempfile.gettempdir(), "suot_audit_fix.db")
for sfx in ("", "-wal", "-shm"):
    try:
        if os.path.exists(TMP_DB + sfx):
            os.remove(TMP_DB + sfx)
    except PermissionError:
        pass
os.environ["SUOT_E2E_DB"] = TMP_DB

from fastapi.testclient import TestClient  # noqa: E402

from app_core.version import APP_VERSION  # noqa: E402
from server.app import app  # noqa: E402

client_ctx = TestClient(app)
c = client_ctx.__enter__()
PASS, FAIL = [], []


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(("  OK " if cond else "FAIL ") + name + (f" | {extra}" if extra else ""))


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


print("== setup ==")
# При SUOT_E2E_DB сидится admin/admin — входим им.
r = c.post("/api/auth/login", json={"username": "admin", "password": "admin"})
check("login admin/admin (seed)", r.status_code == 200, r.status_code)
ADMIN = r.json()["token"]

r = c.post(
    "/api/auth/register",
    json={"username": "worker1", "password": "secret12", "full_name": "W1"},
)
check("register user", r.status_code == 201, r.status_code)

print("== values allowlist ==")
r = c.post(
    "/api/custom/tables",
    headers=H(ADMIN),
    json={"label": "T", "columns": [{"name": "Note", "type": "Текст"}]},
)
KEY = r.json().get("key", "")
check("custom table", r.status_code == 201 and KEY, f"{r.status_code} {KEY}")
rid = c.post(
    f"/api/custom/records/{KEY}",
    headers=H(ADMIN),
    json={"data": {"Note": "<script>alert(1)</script>"}},
).json()["id"]
r = c.get(f"/api/custom/values/{KEY}", params={"col": "Note"}, headers=H(ADMIN))
check(
    "values valid col",
    r.status_code == 200 and len(r.json()["values"]) == 1,
    f"{r.status_code}",
)
r = c.get(
    f"/api/custom/values/{KEY}",
    params={"col": 'x" OR "1"="1'},
    headers=H(ADMIN),
)
check("values injection -> 400", r.status_code == 400, r.status_code)
r = c.get(f"/api/custom/values/{KEY}", params={"col": "Nope"}, headers=H(ADMIN))
check("values unknown -> 400", r.status_code == 400, r.status_code)

print("== session revoke: change_password ==")
tA = c.post(
    "/api/auth/login", json={"username": "worker1", "password": "secret12"}
).json()["token"]
tB = c.post(
    "/api/auth/login", json={"username": "worker1", "password": "secret12"}
).json()["token"]
check("tokens unique", tA != tB)
r = c.post(
    "/api/auth/change_password",
    headers=H(tA),
    json={"old_password": "secret12", "new_password": "secret34"},
)
check("change password", r.status_code == 200, r.status_code)
check("current session alive", c.get("/api/auth/me", headers=H(tA)).status_code == 200)
check(
    "other session revoked",
    c.get("/api/auth/me", headers=H(tB)).status_code == 401,
    c.get("/api/auth/me", headers=H(tB)).status_code,
)

print("== session revoke: admin reset + block ==")
uid = c.get("/api/auth/me", headers=H(tA)).json()["user"]["id"]
r = c.post(f"/api/admin/users/{uid}/reset_password", headers=H(ADMIN))
check(
    "admin reset",
    r.status_code == 200 and r.json().get("new_password"),
    r.status_code,
)
check(
    "session dead after reset", c.get("/api/auth/me", headers=H(tA)).status_code == 401
)
newpwd = r.json()["new_password"]
tC = c.post("/api/auth/login", json={"username": "worker1", "password": newpwd}).json()[
    "token"
]
r = c.post(f"/api/admin/users/{uid}/block", headers=H(ADMIN), json={"blocked": True})
check("block", r.status_code == 200, r.status_code)
check(
    "session dead after block",
    c.get("/api/auth/me", headers=H(tC)).status_code in (401, 403),
)
c.post(f"/api/admin/users/{uid}/block", headers=H(ADMIN), json={"blocked": False})
tD = c.post("/api/auth/login", json={"username": "worker1", "password": newpwd}).json()[
    "token"
]
check("login after unblock", bool(tD))

print("== ai key masking ==")
r = c.get("/api/ai/settings", headers=H(tD))
check(
    "non-admin key masked",
    r.json().get("api_key") == "" and isinstance(r.json().get("api_key_set"), bool),
    str({k: v for k, v in r.json().items() if k != "api_key"}),
)
r = c.get("/api/ai/settings", headers=H(ADMIN))
check(
    "admin settings ok",
    r.status_code == 200 and "api_key_set" in r.json(),
    r.status_code,
)

print("== update SSRF ==")
# Локальный сервер отдаёт манифест 9.9.9 — проверяем, КТО его реально запросил.
_hits = []


class _H(BaseHTTPRequestHandler):
    def do_GET(self):
        _hits.append(self.path)
        data = json.dumps({"version": "9.9.9", "releases": []}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


_srv = HTTPServer(("127.0.0.1", 0), _H)
EVIL = f"http://127.0.0.1:{_srv.server_port}/evil.json"
threading.Thread(target=_srv.serve_forever, daemon=True).start()
r = c.post("/api/update/check", headers=H(tD), json={"manifest_url": EVIL})
check(
    "non-admin override ignored",
    r.json().get("latest") != "9.9.9" and _hits == [],
    f"latest={r.json().get('latest')} hits={_hits}",
)
r = c.post("/api/update/check", headers=H(ADMIN), json={"manifest_url": EVIL})
check(
    "admin override honored",
    r.json().get("latest") == "9.9.9" and _hits == ["/evil.json"],
    f"latest={r.json().get('latest')} hits={_hits}",
)
_srv.shutdown()
r = c.post(
    "/api/admin/update_url",
    headers=H(ADMIN),
    json={"manifest_url": "file:///etc/passwd"},
)
check("bad update_url -> 400", r.status_code == 400, r.status_code)
r = c.post("/api/admin/update_url", headers=H(ADMIN), json={"manifest_url": ""})
check("clear update_url", r.status_code == 200, r.status_code)
r = c.post("/api/update/open", json={"url": "https://example.com/x"})
check("open_update w/o auth -> 401", r.status_code == 401, r.status_code)

print("== preview XSS ==")
r = c.post(
    "/api/print/preview",
    headers=H(ADMIN),
    json={"html_content": "<div>{Note}</div>", "table": KEY, "record_id": rid},
)
h = r.json().get("html", "")
check("preview escaped", "<script>" not in h and "&lt;script&gt;" in h, h[:100])

print("== versions ==")
r = c.get("/api/help/version")
check("help version", r.json().get("version") == APP_VERSION, r.json().get("version"))
r = c.get("/api/diag/summary", headers=H(ADMIN))
check(
    "diag version",
    r.json().get("app", {}).get("version") == APP_VERSION,
    r.json().get("app", {}).get("version"),
)

print(f"\n=> {len(PASS)} OK, {len(FAIL)} FAIL")
if FAIL:
    print("FAILED:", FAIL)
    sys.exit(1)
