"""Часть 25: Календарь+Время — события, повторение, категории, ДР,
агенда дня, напоминания в колокольчике."""

import os, sys, tempfile
from datetime import date, timedelta

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

TMP_DB = os.path.join(tempfile.gettempdir(), "suot_test_part25.db")
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

# создаём сотрудника с днём рождения
bd = date.today() + timedelta(days=30)
client.post(
    "/api/data/employees",
    headers=HA,
    json={
        "data": {
            "ФИО": "Юбиляр Т.Т.",
            "ДР": bd.strftime("%Y-%m-%d"),
            "Статус": "Активен",
        }
    },
)
client.post("/api/data/employees", headers=HA, json={"data": {"ФИО": "БезДН Р.Р."}})

print("== Категории ==")
r = client.get("/api/calendar/categories", headers=HA)
check(
    "категории по умолчанию (6)",
    r.status_code == 200 and len(r.json()["categories"]) >= 6,
    f"count={len(r.json().get('categories', []))}",
)
cats = r.json()["categories"]
cat_ev = next(
    (c for c in cats if "Собрание" in c["name"] or "Совещ" in c["name"]), cats[0]
)

r = client.post(
    "/api/calendar/categories", headers=HA, json={"name": "Рейд", "color": "#00BCD4"}
)
check("создана новая категория", r.status_code == 200 and r.json()["id"] > 0)
new_cat = r.json()["id"]

r = client.put(
    f"/api/calendar/categories/{new_cat}",
    headers=HA,
    json={"name": "Рейд-выезд", "color": "#FF5722"},
)
check(
    "категория переименована",
    r.status_code == 200
    and any(
        c["name"] == "Рейд-выезд"
        for c in client.get("/api/calendar/categories", headers=HA).json()["categories"]
    ),
)

print("== События ==")
base = date.today() + timedelta(days=5)
r = client.post(
    "/api/calendar/events",
    headers=HA,
    json={
        "title": "Проверка СИЗ",
        "date": base.strftime("%Y-%m-%d"),
        "time": "10:30",
        "all_day": False,
        "category_id": cat_ev["id"],
        "repeat": "",
        "remind_min": 1440,
        "note": "Ежемесячный рейд цеха №2",
        "location": "Цех №2",
    },
)
check("создано событие", r.status_code == 200 and r.json()["id"] > 0)
ev1 = r.json()["id"]

r = client.post(
    "/api/calendar/events",
    headers=HA,
    json={
        "title": "Испытание СИЗ нового образца",
        "date": (base + timedelta(days=1)).strftime("%Y-%m-%d"),
        "time": "14:00",
        "category_id": 0,
        "repeat": "weekly",
        "remind_min": 0,
        "note": "",
        "location": "",
    },
)
check("создано повторяющееся событие", r.status_code == 200)
ev2 = r.json()["id"]

r = client.get(
    "/api/calendar/events",
    params={
        "start": base.strftime("%Y-%m-%d"),
        "end": (base + timedelta(days=40)).strftime("%Y-%m-%d"),
        "include_bdays": "1",
    },
    headers=HA,
)
evs = r.json()["events"]
check(
    "события в диапазоне (повтор weekly развёрнут)",
    r.status_code == 200 and len(evs) >= 6,
    f"n={len(evs)}",
)
bdy = [e for e in evs if e.get("_birthday") or e.get("source") == "birthday"]
check("день рождения сотрудника в календаре", len(bdy) >= 1, f"bd={len(bdy)}")
if bdy:
    check("ДР помечен source=birthday", bdy[0].get("source") == "birthday")

r = client.put(
    f"/api/calendar/events/{ev1}",
    headers=HA,
    json={
        "title": "Проверка СИЗ (перенесено)",
        "date": (date.today() + timedelta(days=1)).strftime("%Y-%m-%d"),
        "time": "09:00",
        "category_id": 0,
        "repeat": "",
        "remind_min": 30,
        "note": "",
        "location": "",
    },
)
check("событие обновлено", r.status_code == 200)
evs_after = client.get(
    "/api/calendar/events",
    params={
        "start": (date.today() + timedelta(days=1)).strftime("%Y-%m-%d"),
        "end": (date.today() + timedelta(days=1)).strftime("%Y-%m-%d"),
    },
    headers=HA,
).json()["events"]
check(
    "изменение применилось",
    any(e.get("title", "").startswith("Проверка СИЗ (перенесено)") for e in evs_after),
)
r = client.get(
    f"/api/calendar/events?start={base.strftime('%Y-%m-%d')}"
    f"&end={(base + timedelta(days=5)).strftime('%Y-%m-%d')}",
    headers=HA,
)
check(
    "событие ушло из старого дня",
    r.status_code == 200 and not any(e["id"] == ev1 for e in r.json()["events"]),
)

print("== Агенда дня ==")
agenda_day = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
r = client.get("/api/calendar/agenda", params={"day": agenda_day}, headers=HA)
ag = r.json()
check(
    "агенда дня содержит событие",
    r.status_code == 200 and any(i.get("type") == "event" for i in ag["items"]),
)
if ag["items"]:
    check(
        "агенда отсортирована (all_day вначале)",
        ag["items"][0].get("all_day") or not any(i.get("all_day") for i in ag["items"]),
    )

print("== Напоминания (колокольчик) ==")
r = client.get("/api/reminders/list", headers=HA)
rem = r.json()
cal_rem = [i for i in rem["items"] if i["table"] == "calendar"]
check(
    "событие календаря в колокольчике",
    any(i["title"].startswith("Проверка СИЗ (перенесено)") for i in cal_rem),
    f"cal_rem={len(cal_rem)}",
)
check(
    "счётчики колокольчика валидны",
    rem["total"] == rem["overdue_count"] + rem["upcoming_count"],
)

r = client.delete(f"/api/calendar/events/{ev1}", headers=HA)
check("событие удалено", r.status_code == 200)
evs_final = client.get(
    "/api/calendar/events",
    params={
        "start": base.strftime("%Y-%m-%d"),
        "end": (base + timedelta(days=100)).strftime("%Y-%m-%d"),
    },
    headers=HA,
).json()["events"]
check("после удаления нет события ev1", not any(e["id"] == ev1 for e in evs_final))

r = client.post(
    "/api/calendar/events", headers=HA, json={"title": "", "date": "2026-01-01"}
)
check("пустое название = 400", r.status_code == 400)
r = client.post(
    "/api/calendar/events",
    headers=HA,
    json={"title": "Плохая дата", "date": "31.09.2026"},
)
check("неверная дата = 400", r.status_code == 400)
r = client.post(
    "/api/calendar/events",
    headers=HA,
    json={"title": "Событие в DD.MM.YYYY", "date": "05.03.2027"},
)
check(
    "дата DD.MM.YYYY принята",
    r.status_code == 200,
    r.text[:80] if r.status_code != 200 else "",
)

# валидация доступа не-админа
r2 = client.post(
    "/api/auth/register", json={"username": "watcher25", "password": "secret123"}
)
token2 = r2.json().get("token") if r2.status_code == 200 else ""
HU = {"Authorization": "Bearer " + token2} if token2 else None
if HU:
    r = client.delete(f"/api/calendar/events/{ev2}", headers=HU)
    check("не-админ не удаляет чужое событие", r.status_code == 403)

fmt = "Итого Ч25: " + str(len(PASS)) + " OK, " + str(len(FAIL)) + " FAIL"
print(fmt)
try:
    client_ctx.__exit__(None, None, None)
except Exception:
    pass
sys.exit(1 if FAIL else 0)
