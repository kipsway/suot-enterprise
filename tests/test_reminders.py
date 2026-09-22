"""Часть 15: тесты напоминаний (list/settings)."""

import os
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

p = os.path.join(tempfile.gettempdir(), "suot_rem.db")
for s in ("", "-wal", "-shm"):
    try:
        os.remove(p + s)
    except OSError:
        pass
os.environ["SUOT_E2E_DB"] = p

from fastapi.testclient import TestClient  # noqa: E402
from server.app import app  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(("  OK " if cond else "FAIL ") + name + (f" | {extra}" if extra else ""))


client = TestClient(app)
with client:
    r = client.post(
        "/api/auth/register", json={"username": "rem_user", "password": "parol123"}
    )
    HB = {"Authorization": "Bearer " + r.json()["token"]}

    from datetime import datetime, timedelta

    upcoming_date = (datetime.now() + timedelta(days=15)).strftime("%d.%m.%Y")
    # Данные с просрочкой и предстоящим
    client.post(
        "/api/data/employees",
        headers=HB,
        json={"data": {"ФИО": "Просроченный", "Дата медосмотра": "01.01.2024"}},
    )
    client.post(
        "/api/data/employees",
        headers=HB,
        json={"data": {"ФИО": "Предстоящий", "Дата медосмотра": upcoming_date}},
    )

    # Список
    rl = client.get("/api/reminders/list", headers=HB)
    j = rl.json()
    check("напоминания: 2 записи", j["total"] == 2, str(j["total"]))
    check("1 просрочка", j["overdue_count"] == 1)
    check("1 предстоящая", j["upcoming_count"] == 1)
    check("первая — просрочка", j["items"][0]["status"] == "overdue")

    # Настройки: чтение
    rs = client.get("/api/reminders/settings", headers=HB)
    check("настройки: defaults", rs.json()["settings"].get("medical") == 30)

    # Настройки: сохранение (только админ)
    radmin = client.post(
        "/api/auth/login", json={"username": "admin", "password": "admin"}
    )
    HAdm = {"Authorization": "Bearer " + radmin.json()["token"]}
    rsv = client.post(
        "/api/reminders/settings", headers=HAdm, json={"lead_days": {"medical": 60}}
    )
    check("настройки: сохранение", rsv.status_code == 200)
    rs2 = client.get("/api/reminders/settings", headers=HB)
    check("настройки: применены (60)", rs2.json()["settings"].get("medical") == 60)

    # Не-админ не может менять настройки
    r2 = client.post(
        "/api/auth/register", json={"username": "rem2", "password": "parol123"}
    )
    HB2 = {"Authorization": "Bearer " + r2.json()["token"]}
    rdenied = client.post(
        "/api/reminders/settings", headers=HB2, json={"lead_days": {"medical": 1}}
    )
    check("не-админ → 403", rdenied.status_code == 403)

for s in ("", "-wal", "-shm"):
    try:
        os.remove(p + s)
    except OSError:
        pass

print(f"\nИТОГО: {len(PASS)} OK, {len(FAIL)} FAIL")
if FAIL:
    print("Провалены:", FAIL)
    sys.exit(1)
