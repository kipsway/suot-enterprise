"""Часть 14: тесты глобального поиска + конструктор отчётов."""

import os
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

p = os.path.join(tempfile.gettempdir(), "suot_sr.db")
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
        "/api/auth/register", json={"username": "sr_user", "password": "parol123"}
    )
    HB = {"Authorization": "Bearer " + r.json()["token"]}

    # данные
    client.post(
        "/api/data/employees",
        headers=HB,
        json={
            "data": {
                "ФИО": "Алексеев Алексей",
                "Подразделение": "Цех №1",
                "Должность": "Сварщик",
            }
        },
    )
    client.post(
        "/api/data/employees",
        headers=HB,
        json={
            "data": {
                "ФИО": "Борисов Борис",
                "Подразделение": "Цех №1",
                "Должность": "Монтажник",
            }
        },
    )
    client.post(
        "/api/data/employees",
        headers=HB,
        json={
            "data": {
                "ФИО": "Смирнова Вера",
                "Подразделение": "Склад",
                "Должность": "Кладовщик",
            }
        },
    )
    client.post(
        "/api/data/violations",
        headers=HB,
        json={
            "data": {
                "Описание": "Нарушение Алексеева",
                "Категория риска": "Высокий",
                "Статус": "Активно",
            }
        },
    )

    # ── Глобальный поиск ──
    rs = client.get("/api/search?q=Алексеев", headers=HB)
    results = rs.json()["results"]
    check("поиск находит Алексеева", len(results) >= 1, str(len(results)))
    check("поиск находит в employees", any(r["table"] == "employees" for r in results))
    check(
        "поиск находит в violations", any(r["table"] == "violations" for r in results)
    )
    check("matched_field заполнено", any(r.get("matched_field") for r in results))
    check(
        "snippet содержит контекст",
        any("Алексеев" in r.get("snippet", "") for r in results),
    )

    rs_empty = client.get("/api/search?q=zzzzz", headers=HB)
    check("пустой результат", len(rs_empty.json()["results"]) == 0)
    rs_short = client.get("/api/search?q=a", headers=HB)
    check("короткий запрос → пусто", len(rs_short.json()["results"]) == 0)

    # ── Конструктор отчётов ──
    # flat
    rr = client.post(
        "/api/reports/run",
        headers=HB,
        json={"table": "employees", "columns": ["ФИО", "Подразделение"]},
    )
    check("отчёт flat: 3 записи", rr.json()["total"] == 3)
    check("отчёт flat: колонки", set(rr.json()["columns"]) == {"ФИО", "Подразделение"})

    # группировка
    rr_g = client.post(
        "/api/reports/run",
        headers=HB,
        json={"table": "employees", "group_by": "Подразделение", "aggregate": "count"},
    )
    groups = rr_g.json()["groups"]
    check("группировка: 2 группы", len(groups) == 2)
    ceh1 = next((g for g in groups if g["group"] == "Цех №1"), None)
    check("Цех №1: 2 записи", ceh1 and ceh1["count"] == 2)

    # группировка + фильтр
    rr_f = client.post(
        "/api/reports/run",
        headers=HB,
        json={
            "table": "employees",
            "group_by": "Подразделение",
            "aggregate": "count",
            "filters": {"Подразделение": ["Цех №1"]},
        },
    )
    check("группировка с фильтром: 1 группа", len(rr_f.json()["groups"]) == 1)

    # ── Быстрые фильтры ──
    rqf = client.get("/api/quick_filters/violations", headers=HB)
    qf_keys = [f["key"] for f in rqf.json()["filters"]]
    check("быстрые фильтры: active", "active" in qf_keys)
    check("быстрые фильтры: done", "done" in qf_keys)
    check("быстрые фильтры: mine", "mine" in qf_keys)

for s in ("", "-wal", "-shm"):
    try:
        os.remove(p + s)
    except OSError:
        pass

print(f"\nИТОГО: {len(PASS)} OK, {len(FAIL)} FAIL")
if FAIL:
    print("Провалены:", FAIL)
    sys.exit(1)
