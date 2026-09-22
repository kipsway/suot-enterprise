"""Часть 26: Правовая база — каталог НПА, фасеты, поиск, избранное,
импорт списком, права администратора, единый поиск."""

import os, sys, tempfile
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

TMP_DB = os.path.join(tempfile.gettempdir(), "suot_test_part26.db")
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

print("== Seed каталога ==")
r = client.get("/api/npa/facets", headers=HA)
facet = r.json()
check("фасеты: 200", r.status_code == 200)
kinds = facet.get("kinds", [])
check("есть все виды НПА", len(kinds) >= 5, f"kinds={len(kinds)}")
total_in_kinds = sum(k["count"] for k in kinds)
check("сумма по видам >=70", total_in_kinds >= 70, f"total={total_in_kinds}")
check("фасеты по категориям", len(facet.get("categories", [])) >= 10)
check("фасеты по статусам", len(facet.get("statuses", [])) >= 2)
check("фасеты по годам", len(facet.get("years", [])) >= 5)

print("== Список и поиск ==")
r = client.get("/api/npa/list", headers=HA)
items = r.json()["items"]
check(
    "список НПА не пуст", r.status_code == 200 and len(items) >= 70, f"n={len(items)}"
)
titles = " ".join(i["title"] for i in items[:3]).lower()
first = items[0]
check(
    "карточка содержит реквизиты",
    first.get("number") and first.get("date") and first.get("url"),
)

since = list(filter(lambda i: i["title"].startswith("Трудовой кодекс"), items))
check("в каталоге есть Трудовой кодекс РФ", len(since) >= 1)
tk = since[0] if since else items[0]
check("kind=кодекс", tk.get("kind") == "кодекс", tk.get("kind"))

# фасетный поиск «приказ СИЗ 2021»
r = client.get(
    "/api/npa/list",
    params={"q": "СИЗ", "kind": "приказ", "year": "2021"},
    headers=HA,
)
sc = r.json()
check(
    "q=СИЗ kind=приказ год=2021",
    sc["total"] >= 1
    and all(i["kind"] == "приказ" and i["date"][6:10] == "2021" for i in sc["items"]),
    f"n={sc['total']}",
)
r = client.get("/api/npa/list", params={"q": "специальная оценка"}, headers=HA)
check("поиск 'специальная оценка'", r.json()["total"] >= 2, f"n={r.json()['total']}")

print("== Детальная карточка ==")
doc_id = items[0]["id"]
r = client.get(f"/api/npa/{doc_id}", headers=HA)
check("детализация", r.status_code == 200 and r.json()["item"]["id"] == doc_id)

print("== Избранное ==")
r = client.post(f"/api/npa/{doc_id}/fav", headers=HA)
check("добавлено в избранное", r.status_code == 200 and r.json()["is_fav"] is True)
r = client.get("/api/npa/list", params={"fav": "1"}, headers=HA)
check(
    "список избранного", r.json()["total"] == 1 and r.json()["items"][0]["id"] == doc_id
)
r = client.post(f"/api/npa/{doc_id}/fav", headers=HA)
check("убрано из избранного", r.status_code == 200 and r.json()["is_fav"] is False)
r = client.get("/api/npa/list", params={"fav": "1"}, headers=HA)
check("избранное пусто после снятия", r.json()["total"] == 0)
r = client.post("/api/npa/99999/fav", headers=HA)
check("избранное несущ. документа = 404", r.status_code == 404)

print("== CRUD администратора ==")
num = str(datetime.now(tz=None).year)
payload = {
    "kind": "приказ",
    "number": "TEST-1",
    "title": "Тестовый приказ по охране труда (PK-тест)",
    "date": "15.02.2026",
    "status": "действует",
    "category": "Обучение",
    "audience": "Все работодатели",
    "url": "https://pravo.gov.ru/proxy/ips/?searchstr=TEST-1",
    "notes": "Создан автотестом",
}
r = client.post("/api/npa", headers=HA, json=payload)
new_id = r.json().get("id", 0) if r.status_code == 200 else 0
check("админ создаёт документ", r.status_code == 200 and new_id > 0, r.text[:120])
if new_id:
    r = client.get(f"/api/npa/{new_id}", headers=HA)
    check(
        "документ в БД",
        r.status_code == 200 and "PK-тест" in r.json()["item"]["title"],
    )
    r = client.put(
        f"/api/npa/{new_id}",
        headers=HA,
        json={**payload, "title": "Тестовый приказ (обновлён)", "status": "изменён"},
    )
    get_it = client.get(f"/api/npa/{new_id}", headers=HA).json()["item"]
    check(
        "документ обновлён (статус)",
        get_it["status"] == "изменён" and "обновлён" in get_it["title"],
    )

print("== Ограничения не-админа ==")
r2 = client.post(
    "/api/auth/register", json={"username": "watcher26", "password": "secret123"}
)
token2 = r2.json().get("token") if r2.status_code == 200 else ""
HU = {"Authorization": "Bearer " + token2} if token2 else None
if HU:
    r = client.post("/api/npa", headers=HU, json=payload)
    check("не-админ не создаёт документ", r.status_code == 403)
    r = client.post(f"/api/npa/{doc_id}/fav", headers=HU)
    check("не-админ может избранное", r.status_code == 200)
    r = client.delete(f"/api/npa/{doc_id}", headers=HU)
    check("не-админ не удаляет документ", r.status_code == 403)

print("== Импорт списком ==")
r = client.post(
    "/api/npa/import",
    headers=HA,
    json={
        "items": [
            {
                "kind": "постановление",
                "number": "IMP-1",
                "title": "Импортированное постановление",
                "date": "10.01.2025",
                "status": "действует",
                "category": "Обучение",
            },
            {
                "kind": "СП",
                "number": "IMP-2",
                "title": "Импортированные санитарные правила",
                "date": "2025",
                "status": "действует",
                "category": "Гигиена труда",
            },
        ]
    },
)
check(
    "импорт двух документов",
    r.status_code == 200 and r.json()["imported"] == 2,
    r.text[:120],
)
r = client.get(
    "/api/npa/list", params={"q": "Импортированное постановление"}, headers=HA
)
check("импорт виден в поиске", r.json()["total"] >= 1)
r = client.post("/api/npa/import", headers=HA, json={"items": []})
check("импорт пустого списка = 400", r.status_code == 400)
r = client.post(
    "/api/npa/import",
    headers=HA,
    json={
        "csv": (
            "постановление;CSV-1;Правила по охране труда CSV;"
            "15.03.2026;действует;Обучение"
        )
    },
)
check(
    "импорт CSV строки",
    r.status_code == 200 and r.json()["imported"] == 1,
    r.text[:120],
)

print("== Единый поиск ==")
r = client.get("/api/search", params={"q": "специальная оценка"}, headers=HA)
res = r.json()["results"]
npa_res = [x for x in res if x.get("table") == "npa"]
check("единый поиск находит НПА", len(npa_res) >= 1, f"npa={len(npa_res)}")
if npa_res:
    check(
        "результат НПА помечен",
        "НПА" in npa_res[0].get("matched_field", "") or "426" in npa_res[0]["title"],
    )

print("== Удаление ==")
if new_id:
    r = client.delete(f"/api/npa/{new_id}", headers=HA)
    check("документ удалён", r.status_code == 200)
    r = client.get(f"/api/npa/{new_id}", headers=HA)
    check("после удаления 404", r.status_code == 404)

fmt = "Итого Ч26: " + str(len(PASS)) + " OK, " + str(len(FAIL)) + " FAIL"
print(fmt)
try:
    client_ctx.__exit__(None, None, None)
except Exception:
    pass
sys.exit(1 if FAIL else 0)
