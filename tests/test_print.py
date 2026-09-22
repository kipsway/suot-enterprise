"""Часть 12: тесты редактора печати."""

import os
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

p = os.path.join(tempfile.gettempdir(), "suot_pe.db")
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
        "/api/auth/register", json={"username": "pe_user", "password": "parol123"}
    )
    HB = {"Authorization": "Bearer " + r.json()["token"]}

    # Создание
    rt = client.post(
        "/api/print/templates",
        headers=HB,
        json={
            "name": "Акт осмотра",
            "category": "Осмотры",
            "html_content": "<h1>Акт осмотра {ФИО}</h1><p>Дата: {today}</p>",
            "page_size": "A4",
            "orientation": "portrait",
            "margins": "20mm",
        },
    )
    check("шаблон создан", rt.status_code == 201)
    tid = rt.json()["id"]

    # Чтение
    rg = client.get(f"/api/print/templates/{tid}", headers=HB)
    check(
        "шаблон прочитан",
        rg.status_code == 200 and rg.json()["template"]["name"] == "Акт осмотра",
    )

    # Список
    rl = client.get("/api/print/templates", headers=HB)
    check("в списке", any(t["id"] == tid for t in rl.json()["items"]))

    # Переменные
    rv = client.get("/api/print/variables/employees", headers=HB)
    vnames = [v["name"] for v in rv.json()["items"]]
    check(
        "переменные содержат ФИО и today", "ФИО" in vnames and "Дата печати" in vnames
    )

    # Предпросмотр с данными (предложение 1)
    re_ = client.post(
        "/api/data/employees", headers=HB, json={"data": {"ФИО": "Предпросмотр Тест"}}
    )
    rec_id = re_.json()["id"]
    rpv = client.post(
        "/api/print/preview",
        headers=HB,
        json={
            "html_content": "<p>Сотрудник: {ФИО}, дата: {today}</p>",
            "table": "employees",
            "record_id": rec_id,
        },
    )
    pv = rpv.json()["html"]
    check("предпросмотр: переменная подставлена", "Предпросмотр Тест" in pv, pv[:80])
    check("предпросмотр: today подставлен", "2026" in pv or "2025" in pv)

    # Копирование (предложение 2)
    rc = client.post(f"/api/print/templates/{tid}/copy", headers=HB)
    check("копия создана", rc.status_code == 201)
    copy_id = rc.json()["id"]
    rgc = client.get(f"/api/print/templates/{copy_id}", headers=HB)
    check("копия содержит '(копия)'", "копия" in rgc.json()["template"]["name"])

    # Обновление
    ru = client.put(
        f"/api/print/templates/{tid}",
        headers=HB,
        json={
            "name": "Акт осмотра v2",
            "category": "Осмотры",
            "html_content": "<h1>v2</h1>",
            "is_public": True,
        },
    )
    check("обновлён", ru.status_code == 200)

    # Публичный виден другому
    r2 = client.post(
        "/api/auth/register", json={"username": "pe2", "password": "parol123"}
    )
    HB2 = {"Authorization": "Bearer " + r2.json()["token"]}
    rlist2 = client.get("/api/print/templates", headers=HB2)
    check(
        "публичный шаблон виден другому",
        any(t["id"] == tid for t in rlist2.json()["items"]),
    )

    # Экспорт шаблона (предложение 3)
    rex = client.get(f"/api/print/templates/{tid}/export", headers=HB)
    check(
        "экспорт JSON",
        rex.status_code == 200 and rex.json()["_export"] == "suot_template_v1",
    )

    # Импорт шаблона (предложение 3)
    rim = client.post(
        "/api/print/import_template",
        headers=HB,
        json={
            "name": "Импортированный",
            "html_content": "<p>imported</p>",
            "page_size": "A5",
            "orientation": "landscape",
        },
    )
    check("импорт шаблона", rim.status_code == 201)

    # Удаление
    rdel = client.delete(f"/api/print/templates/{copy_id}", headers=HB)
    check("удаление", rdel.status_code == 200)

    # Сетка/линейка (предложение 4) — фронтенд, здесь проверяем что page_size работает
    rt2 = client.post(
        "/api/print/templates",
        headers=HB,
        json={"name": "A5 Landscape", "page_size": "A5", "orientation": "landscape"},
    )
    rg2 = client.get(f"/api/print/templates/{rt2.json()['id']}", headers=HB).json()[
        "template"
    ]
    check(
        "page_size A5 + landscape сохранены",
        rg2["page_size"] == "A5" and rg2["orientation"] == "landscape",
    )

for s in ("", "-wal", "-shm"):
    try:
        os.remove(p + s)
    except OSError:
        pass

print(f"\nИТОГО: {len(PASS)} OK, {len(FAIL)} FAIL")
if FAIL:
    print("Провалены:", FAIL)
    sys.exit(1)
