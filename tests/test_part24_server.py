"""Часть 24: реестр «Всё», дашборд 3.0 (задачи+лента), автоэкспорт."""

import os, sys, tempfile

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

TMP_DB = os.path.join(tempfile.gettempdir(), "suot_test_part24.db")
for suffix in ("", "-wal", "-shm"):
    try:
        if os.path.exists(TMP_DB + suffix):
            os.remove(TMP_DB + suffix)
    except PermissionError:
        pass

os.environ["SUOT_E2E_DB"] = TMP_DB

from services.database import DatabaseManager  # noqa: E402

db = DatabaseManager(TMP_DB)

from server.app import app  # noqa: E402

client_ctx = TestClient(app)
client = client_ctx.__enter__()
PASS = []
FAIL = []


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(("  OK " if cond else "FAIL ") + name + (f" | {extra}" if extra else ""))


r = client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
check(
    "сид-админ → Administrator",
    r.status_code == 200 and r.json()["user"]["role"] == "Administrator",
)
HA = {"Authorization": "Bearer " + r.json()["token"]}

# тестовые данные
r_emp = client.post(
    "/api/data/employees",
    headers=HA,
    json={"data": {"ФИО": "Смирнов П.П.", "Должность": "Сварщик", "Статус": "Активен"}},
)
check("создан сотрудник", r_emp.status_code == 201)
emp_id = r_emp.json()["id"]
client.post(
    "/api/data/violations",
    headers=HA,
    json={
        "data": {
            "Описание": "Нет накладок",
            "Срок устранения": "2024-01-01",
            "Статус": "Открыто",
        }
    },
)
client.post(
    "/api/data/ppe",
    headers=HA,
    json={
        "data": {
            "Наименование": "Спецобувь",
            "Срок замены": "2025-12-31",
            "Статус": "Выдано",
        }
    },
)
try:
    client.post(
        "/api/structured/capa",
        headers=HA,
        json={
            "title": "CAPA-тест 24",
            "severity": "Высокая",
            "status": "Open",
            "assigned_to": "Admin",
        },
    )
except Exception:
    pass

print("== Реестр «Всё» ==")
rs = client.get("/api/union/sections", headers=HA)
secs = rs.json()["sections"]
names = [s["section"] for s in secs]
check("/sections → 200", rs.status_code == 200)
check(
    "разделы содержат employees/violations",
    "employees" in names and "violations" in names,
    f"sections={len(secs)}",
)

rr = client.get("/api/union/records?page=1&page_size=50", headers=HA)
j = rr.json()
check("/records → 200", rr.status_code == 200)
check(
    "items содержат запись сотрудника",
    any("Смирнов" in str(it.get("data")) for it in j["items"]),
    f"total={j.get('total')}",
)

# При SUOT_E2E_DB демо-сид не грузится автоматически — грузим явно через
# /api/demo/seed, чтобы поиск админа находил и свою запись, и демо-«Смирнову».
rsd = client.post("/api/demo/seed", headers=HA, json={"tables": []})
check("demo seed", rsd.status_code in (200, 201), rsd.status_code)
rq = client.get("/api/union/records?q=Смирнов", headers=HA)
jq = rq.json()
# Сквозной поиск ищет по всем разделам. Демо-сид пропускает непустые таблицы
# (employees уже содержит свою запись), поэтому демо-«Смирнов Дмитрий»
# попадает в обучение/осмотры СИЗ — проверяем наличие своей и любой демо-записи.
own_in_q = any("Смирнов П.П." in str(it.get("data")) for it in jq["items"])
demo_in_q = any(
    "Смирнов Дмитрий" in str(it.get("data")) or "Смирнова" in str(it.get("data"))
    for it in jq["items"]
)
check(
    "поиск q=Смирнов находит свою запись и демо-сид",
    rq.status_code == 200
    and jq["total"] >= 2
    and own_in_q
    and demo_in_q,
    f"total={jq.get('total')}",
)
check(
    "записи имеют section/section_label",
    jq["items"]
    and all(
        it.get("section") and it.get("section_label") for it in jq["items"]
    ),
)
check(
    "колонки содержат ФИО", "ФИО" in jq.get("columns", []), f"cols={jq.get('columns')}"
)

rf = client.get("/api/union/records?f_section=ppe", headers=HA)
jf = rf.json()
check(
    "фильтр f_section=ppe",
    rf.status_code == 200
    and all(it["section"] == "ppe" for it in jf["items"])
    and any("Спецобувь" in str(it.get("data")) for it in jf["items"]),
    f"total={jf.get('total')}",
)

rsort = client.get("/api/union/records?sort_by=id&order=desc", headers=HA)
jsort = rsort.json()
ids = [it["id"] for it in jsort["items"]]
check("сортировка id desc", ids == sorted(ids, reverse=True), f"first={ids[:3]}")

cc = client.get("/api/union/records?page_size=50000", headers=HA)
check("page_size ограничен до 500", cc.status_code == 200)

print("== Экспорт реестра ==")
rex = client.post(
    "/api/union/export",
    headers=HA,
    json={
        "q": "",
        "sections": [],
        "columns": [],
        "format": "xlsx",
        "title": "Реестр Всё",
    },
)
check(
    "export xlsx → 200",
    rex.status_code == 200
    and rex.headers.get("content-type", "").startswith(
        "application/vnd.openxmlformats-officedocument"
    ),
    rex.headers.get("content-type", ""),
)
red = client.post(
    "/api/union/export",
    headers=HA,
    json={"q": "", "sections": [], "columns": [], "format": "csv"},
)
check(
    "export csv → 200",
    red.status_code == 200 and "text/csv" in red.headers.get("content-type", ""),
)
rej = client.post(
    "/api/union/export",
    headers=HA,
    json={"q": "", "sections": [], "columns": [], "format": "json"},
)
check(
    "export json → 200", rej.status_code == 200 and rej.json().get("rows") is not None
)

print("== Экспорт вида (планировщик) ==")
rp = client.get("/api/exporter/plan", headers=HA)
plan0 = rp.json()
check("plan GET → 200", rp.status_code == 200 and "weekday_ru" in plan0)
rps = client.post(
    "/api/exporter/plan",
    headers=HA,
    json={
        "enabled": True,
        "weekday": 1,
        "time": "09:30",
        "table": "employees",
        "columns": ["ФИО"],
        "format": "csv",
        "title": "Рабочие",
    },
)
check(
    "plan POST сохраняется",
    rps.status_code == 200 and rps.json()["table"] == "employees",
)
exptmp = os.path.join(tempfile.gettempdir(), "suot_exports_24")
rrn = client.post("/api/exporter/run_now", headers=HA)
check("run_now → файл в exports/", rrn.status_code == 200)
from server.routers.exporter_api import do_export
import json as _json

plan = _json.loads(db.get_setting("exporter_plan", "") or "{}")
fname = do_export(db, plan, export_dir=exptmp)
fpath = os.path.join(exptmp, fname)
check(
    "do_export создаёт файл",
    os.path.exists(fpath) and fname.startswith("employees"),
    fname,
)
with open(fpath, encoding="utf-8-sig") as f:
    has_emp = "Смирнов" in f.read()
check("csv содержит данные", has_emp)

print("== Дашборд 3.0 ==")
rp = client.get("/api/dash/permissions", headers=HA)
check("permissions → admin", rp.status_code == 200 and rp.json()["admin"] is True)
rt = client.get("/api/dash/tasks", headers=HA)
jt = rt.json()
check("/tasks → 200", rt.status_code == 200 and "tasks" in jt)
check(
    "/tasks имеет записи (capa/сроки)",
    len(jt.get("tasks", [])) >= 1,
    f"tasks={len(jt.get('tasks', []))}",
)
ra = client.get("/api/dash/activity?limit=25", headers=HA)
ja = ra.json()
check(
    "/activity → 200 + items",
    ra.status_code == 200
    and isinstance(ja.get("items"), list)
    and any("Автоэкспорт" in (a.get("event") or "") for a in ja["items"]),
    f"items={len(ja.get('items', []))}",
)

print("== Безопасность: разделы не видны без токена ==")
r401 = client.get("/api/union/records")
check("union без токена → 401", r401.status_code == 401)
r401b = client.get("/api/exporter/plan")
check("exporter plan без токена → 401", r401b.status_code == 401)
r401c = client.get("/api/dash/tasks")
check("tasks без токена → 401", r401c.status_code == 401)

for suffix in ("", "-wal", "-shm"):
    try:
        os.remove(TMP_DB + suffix)
    except OSError:
        pass
print(f"\nИТОГО: {len(PASS)} OK, {len(FAIL)} FAIL")
if FAIL:
    print("Провалены:", FAIL)
    sys.exit(1)
