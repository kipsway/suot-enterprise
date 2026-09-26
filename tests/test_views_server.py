"""Часть 7 (SUOT Next, Блок 7): серверные виды таблиц + smart-фильтры
пользовательских таблиц.

Запуск: python tests/test_views_server.py
"""

import os
import sys
import tempfile

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

TMP_DB = os.path.join(tempfile.gettempdir(), "suot_views_srv.db")
for sfx in ("", "-wal", "-shm"):
    try:
        if os.path.exists(TMP_DB + sfx):
            os.remove(TMP_DB + sfx)
    except PermissionError:
        pass
os.environ["SUOT_E2E_DB"] = TMP_DB

from fastapi.testclient import TestClient  # noqa: E402

from server.app import app  # noqa: E402

c = TestClient(app).__enter__()
PASS, FAIL = [], []


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(("  OK " if cond else "FAIL ") + name + (f" | {extra}" if extra else ""))


def H(t):
    return {"Authorization": "Bearer " + t}


adm = c.post("/api/auth/login", json={"username": "admin", "password": "admin"}).json()[
    "token"
]
c.post(
    "/api/auth/register",
    json={"username": "worker3", "password": "secret12", "full_name": "W3"},
)
usr = c.post(
    "/api/auth/login", json={"username": "worker3", "password": "secret12"}
).json()["token"]

print("== views CRUD ==")
r = c.post(
    "/api/views",
    headers=H(adm),
    json={
        "scope": "employees",
        "name": "Мои",
        "query": {
            "q": "Иван",
            "smartFilter": "active",
            "sortBy": "id",
            "order": "desc",
        },
    },
)
check("create 201", r.status_code == 201, r.status_code)
vid = r.json().get("id")
r = c.get("/api/views", params={"scope": "employees"}, headers=H(adm))
items = r.json().get("items", [])
check(
    "list has it",
    len(items) == 1
    and items[0]["name"] == "Мои"
    and items[0]["query"].get("smartFilter") == "active",
    str(len(items)),
)
r = c.put(f"/api/views/{vid}", headers=H(adm), json={"name": "Мои 2"})
check("rename 200", r.status_code == 200, r.status_code)
r = c.get("/api/views", params={"scope": "employees"}, headers=H(adm))
check("renamed", r.json()["items"][0]["name"] == "Мои 2")
r = c.put(
    f"/api/views/{vid}",
    headers=H(adm),
    json={"query": {"q": "Петр", "zzz_nope": 1, "page_size": 25}},
)
check("update query 200", r.status_code == 200, r.status_code)
q = c.get("/api/views", params={"scope": "employees"}, headers=H(adm)).json()["items"][
    0
]["query"]
check(
    "unknown keys stripped",
    q.get("q") == "Петр" and "zzz_nope" not in q and q.get("page_size") == 25,
    str(q),
)

print("== views validation ==")
r = c.post(
    "/api/views", headers=H(adm), json={"scope": "../x", "name": "B", "query": {}}
)
check("bad scope -> 400", r.status_code == 400, r.status_code)
r = c.post(
    "/api/views", headers=H(adm), json={"scope": "employees", "name": "", "query": {}}
)
check("empty name -> 400", r.status_code == 400, r.status_code)
r = c.post(
    "/api/views",
    headers=H(adm),
    json={"scope": "employees", "name": "B", "query": [1, 2]},
)
check("non-dict query -> 400/422", r.status_code in (400, 422), r.status_code)
r = c.post(
    "/api/views",
    headers=H(adm),
    json={"scope": "employees", "name": "B", "query": {"q": "x" * 9000}},
)
check("oversize query -> 400", r.status_code == 400, r.status_code)
r = c.put("/api/views/999999", headers=H(adm), json={"name": "Z"})
check("update missing -> 404", r.status_code == 404, r.status_code)
r = c.delete("/api/views/999999", headers=H(adm))
check("delete missing -> 404", r.status_code == 404, r.status_code)
r = c.get("/api/views", headers=H(adm))
check("scope required -> 422", r.status_code == 422, r.status_code)

print("== views isolation ==")
r = c.post(
    "/api/views",
    headers=H(usr),
    json={"scope": "employees", "name": "UserView", "query": {"q": "a"}},
)
uv = r.json().get("id")
mine = c.get("/api/views", params={"scope": "employees"}, headers=H(usr)).json()[
    "items"
]
check("user sees only own", all(x["name"] == "UserView" for x in mine), str(len(mine)))
allh = c.get("/api/views", params={"scope": "employees"}, headers=H(adm)).json()[
    "items"
]
check("admin sees all", len(allh) >= 2, str(len(allh)))
r = c.delete(f"/api/views/{vid}", headers=H(usr))
check("user чужой view -> 403", r.status_code == 403, r.status_code)
r = c.delete(f"/api/views/{uv}", headers=H(usr))
check("user deletes own", r.status_code == 200, r.status_code)
r = c.delete(f"/api/views/{vid}", headers=H(adm))
check("admin deletes", r.status_code == 200, r.status_code)
r = c.get("/api/views", params={"scope": "employees"}, headers=H(adm))
check("empty after delete", r.json()["items"] == [], str(r.json()["items"]))

print("== custom smart filters ==")
r = c.post(
    "/api/custom/tables",
    headers=H(adm),
    json={
        "label": "CT Smart",
        "icon": "database",
        "color": "#10B981",
        "columns": [
            {"name": "Название", "type": "Текст"},
            {"name": "Срок", "type": "Годен до"},
            {"name": "Статус", "type": "Статус"},
        ],
    },
)
check("custom table 201", r.status_code == 201, r.status_code)
ck = r.json()["key"]
c.post(
    f"/api/custom/records/{ck}",
    headers=H(adm),
    json={"data": {"Название": "Старая", "Срок": "01.01.2020", "Статус": "Активен"}},
)
c.post(
    f"/api/custom/records/{ck}",
    headers=H(adm),
    json={"data": {"Название": "Готовая", "Срок": "01.01.2020", "Статус": "Готово"}},
)
c.post(
    f"/api/custom/records/{ck}",
    headers=H(adm),
    json={"data": {"Название": "Будущая", "Срок": "01.01.2030", "Статус": "Активен"}},
)


def total(params):
    r = c.get(f"/api/custom/records/{ck}", params=params, headers=H(adm))
    return r.status_code, r.json().get("total")


st, t = total({})
check("total 3", st == 200 and t == 3, f"{st} {t}")
st, t = total({"smart_filter": "overdue"})
check("overdue -> 1 (Старая)", st == 200 and t == 1, f"{st} {t}")
st, t = total({"smart_filter": "active"})
check("active -> 2", st == 200 and t == 2, f"{st} {t}")
st, t = total({"smart_filter": "done"})
check("done -> 1 (Готовая)", st == 200 and t == 1, f"{st} {t}")
st, t = total({"smart_filter": "bogus"})
check("bogus ignored", st == 200 and t == 3, f"{st} {t}")

print("== custom smart without date/status cols ==")
r = c.post(
    "/api/custom/tables",
    headers=H(adm),
    json={"label": "CT Plain", "columns": [{"name": "Название", "type": "Текст"}]},
)
pk = r.json()["key"]
c.post(f"/api/custom/records/{pk}", headers=H(adm), json={"data": {"Название": "X"}})
r = c.get(
    f"/api/custom/records/{pk}", params={"smart_filter": "overdue"}, headers=H(adm)
)
check(
    "no date cols -> unfiltered", r.json().get("total") == 1, str(r.json().get("total"))
)

print(f"\n=> {len(PASS)} OK, {len(FAIL)} FAIL")
if FAIL:
    print("FAILED:", FAIL)
    sys.exit(1)
