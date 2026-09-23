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
print("== IDOR: изоляция записей (аудит 7.2 п.1-9) ==")
# Запись админа — недоступна worker1 (tD) ни через один из путей.
r = c.post(
    "/api/data/employees",
    headers=H(ADMIN),
    json={"data": {"ФИО": "IDOR-Test AdminRecord", "Должность": "Тест"}},
)
check("admin record created", r.status_code == 201, r.status_code)
AREC = r.json()["id"]

# п.1: экспорт по ids без проверки владельца
r = c.post(
    "/api/export/json/employees",
    headers=H(tD),
    json={"table": "employees", "ids": [AREC]},
)
leaked = [i for i in r.json().get("items", []) if i.get("id") == AREC or i.get("ФИО") == "IDOR-Test AdminRecord"]
check("export ids: чужая запись отфильтрована", r.status_code == 200 and not leaked, r.status_code)

# п.2: batch_pdf по record_ids без проверки владельца
r = c.post(
    "/api/print/batch_pdf",
    headers=H(tD),
    json={"template_html": "<div>{ФИО}</div>", "table": "employees", "record_ids": [AREC]},
)
check("batch_pdf: чужие ids -> 404 (нет записей)", r.status_code == 404, r.status_code)

# п.3: preview чужой записи
r = c.post(
    "/api/print/preview",
    headers=H(tD),
    json={"html_content": "<div>{ФИО}</div>", "table": "employees", "record_id": AREC},
)
check("preview чужой записи -> 403", r.status_code == 403, r.status_code)

# п.4: transfer из системной таблицы чужих записей
r = c.post(
    "/api/custom/transfer",
    headers=H(tD),
    json={"from_key": "employees", "to_key": "violations", "ids": [AREC], "move": False},
)
check("transfer чужой записи -> moved=0", r.status_code == 200 and r.json().get("moved") == 0, f"{r.status_code} {r.json()}")

# п.5: удаление чужих заметок/связей
nid = c.post(
    f"/api/record/employees/{AREC}/notes",
    headers=H(ADMIN),
    json={"title": "n", "content": "secret"},
).json()["id"]
r = c.delete(f"/api/record/notes/{nid}", headers=H(tD))
check("note_del чужой -> 403", r.status_code == 403, r.status_code)
r = c.delete(f"/api/record/notes/{nid}", headers=H(ADMIN))
check("note_del свой -> 200", r.status_code == 200, r.status_code)

r = c.post(
    "/api/data/employees",
    headers=H(ADMIN),
    json={"data": {"ФИО": "IDOR-Test Target"}},
)
AREC2 = r.json()["id"]
c.post(
    f"/api/record/employees/{AREC}/links",
    headers=H(ADMIN),
    json={"target_table": "employees", "target_id": AREC2},
)
links = c.get(f"/api/record/employees/{AREC}/links", headers=H(ADMIN)).json()["items"]
lid = links[0]["id"] if links else 0
r = c.delete(f"/api/record/links/{lid}", headers=H(tD))
check("link_del чужой -> 403", r.status_code == 403, r.status_code)
# link_add к чужой целевой записи
wrec = c.post(
    "/api/data/employees",
    headers=H(tD),
    json={"data": {"ФИО": "IDOR-Test WorkerRec"}},
).json()["id"]
r = c.post(
    f"/api/record/employees/{wrec}/links",
    headers=H(tD),
    json={"target_table": "employees", "target_id": AREC2},
)
check("link_add к чужой цели -> 403", r.status_code == 403, r.status_code)

# п.6: импорт — STASH, undo, history привязаны к пользователю
r = c.post(
    "/api/import/upload_text",
    headers=H(ADMIN),
    json={"text": "ФИО\nIDOR Import Row", "filename": "idor.csv"},
)
fid_admin = r.json()["file_id"]
r = c.get(f"/api/import/preview/{fid_admin}", headers=H(tD))
check("import preview чужого файла -> 403", r.status_code == 403, r.status_code)
r = c.post(
    "/api/import/run",
    headers=H(ADMIN),
    json={"file_id": fid_admin, "table": "employees", "mapping": {"ФИО": "ФИО"}, "mode": "insert"},
)
imp_id = r.json().get("import_id", 0)
check("admin import run", r.status_code == 200 and imp_id, f"{r.status_code} {imp_id}")
r = c.post("/api/import/undo", headers=H(tD), json={"import_id": imp_id})
check("import undo чужого -> 403", r.status_code == 403, r.status_code)
hist_w = c.get("/api/import/history", headers=H(tD)).json()["items"]
check("import history изолирована", all(h["id"] != imp_id for h in hist_w), str([h["id"] for h in hist_w]))
hist_a = c.get("/api/import/history", headers=H(ADMIN)).json()["items"]
check("admin видит свой импорт", any(h["id"] == imp_id for h in hist_a))
r = c.post("/api/import/undo", headers=H(ADMIN), json={"import_id": imp_id})
check("import undo свой -> 200", r.status_code == 200, r.status_code)

# п.7: exporter run_now — только админ
r = c.post("/api/exporter/run_now", headers=H(tD))
check("exporter run_now non-admin -> 403", r.status_code == 403, r.status_code)

# п.8: diag — только админ
for ep in ("/api/diag/summary", "/api/diag/log", "/api/diag/disk"):
    r = c.get(ep, headers=H(tD))
    check(f"diag {ep.split('/')[-1]} non-admin -> 403", r.status_code == 403, r.status_code)
r = c.get("/api/diag/summary", headers=H(ADMIN))
check("diag summary admin -> 200", r.status_code == 200, r.status_code)

# п.9: календарь — обновление чужой категории
cid = c.post(
    "/api/calendar/categories", headers=H(ADMIN), json={"name": "IDOR Cat"}
).json()["id"]
r = c.put(
    f"/api/calendar/categories/{cid}", headers=H(tD), json={"name": "Hacked"}
)
check("calendar update чужой категории -> 404", r.status_code == 404, r.status_code)
r = c.put(
    f"/api/calendar/categories/{cid}", headers=H(ADMIN), json={"name": "IDOR Cat 2"}
)
check("calendar update своей -> 200", r.status_code == 200, r.status_code)

print(f"\n=> {len(PASS)} OK, {len(FAIL)} FAIL")
if FAIL:
    print("FAILED:", FAIL)
    sys.exit(1)
