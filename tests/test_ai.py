"""Часть 16: тесты AI (настройки, переменные, агент execute, preview)."""

import os
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

p = os.path.join(tempfile.gettempdir(), "suot_ai.db")
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
        "/api/auth/register", json={"username": "ai_user", "password": "parol123"}
    )
    HB = {"Authorization": "Bearer " + r.json()["token"]}
    radmin = client.post(
        "/api/auth/login", json={"username": "admin", "password": "admin"}
    )
    HAdm = {"Authorization": "Bearer " + radmin.json()["token"]}

    # Настройки: чтение defaults
    rs = client.get("/api/ai/settings", headers=HB)
    check("настройки: defaults", rs.json()["provider"] == "ollama")

    # Настройки: сохранение (админ)
    rsv = client.post(
        "/api/ai/settings",
        headers=HAdm,
        json={
            "provider": "openai",
            "base_url": "https://api.openai.com",
            "api_key": "sk-test",
            "model": "gpt-4",
        },
    )
    check("настройки: сохранение админом", rsv.status_code == 200)

    # Не-админ не может менять настройки
    rden = client.post("/api/ai/settings", headers=HB, json={"provider": "ollama"})
    check("не-админ → 403", rden.status_code == 403)

    # Переменные
    rv = client.get("/api/print/variables/employees", headers=HB)
    check("переменные доступны", rv.status_code == 200 and len(rv.json()["items"]) > 0)

    # Данные для агента
    client.post(
        "/api/data/employees",
        headers=HB,
        json={"data": {"ФИО": "Агентов Тест", "Должность": "Сварщик"}},
    )

    # Агент: execute create
    rex = client.post(
        "/api/ai/agent/execute",
        headers=HB,
        json={
            "action": "create_record",
            "params": {
                "table": "violations",
                "data": {"Описание": "AI-созданное нарушение"},
            },
        },
    )
    check("агент: create_record", rex.status_code == 200)

    # Агент: execute search
    rse = client.post(
        "/api/ai/agent/execute",
        headers=HB,
        json={
            "action": "search_records",
            "params": {"table": "employees", "query": "Агентов"},
        },
    )
    check(
        "агент: search_records",
        rse.status_code == 200 and rse.json()["results"][0]["ФИО"] == "Агентов Тест",
    )

    # Агент: execute update
    emp_id = rse.json()["results"][0]["id"]
    rup = client.post(
        "/api/ai/agent/execute",
        headers=HB,
        json={
            "action": "update_record",
            "params": {
                "table": "employees",
                "record_id": emp_id,
                "data": {"Должность": "Старший сварщик"},
            },
        },
    )
    check("агент: update_record", rup.status_code == 200)

    # Preview с данными
    rpv = client.post(
        "/api/print/preview",
        headers=HB,
        json={
            "html_content": "<p>{ФИО} — {Должность}</p>",
            "table": "employees",
            "record_id": emp_id,
        },
    )
    check("preview с данными", "Старший сварщик" in rpv.json()["html"])

for s in ("", "-wal", "-shm"):
    try:
        os.remove(p + s)
    except OSError:
        pass

print(f"\nИТОГО: {len(PASS)} OK, {len(FAIL)} FAIL")
if FAIL:
    print("Провалены:", FAIL)
    sys.exit(1)
