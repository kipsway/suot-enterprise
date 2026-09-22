"""Часть 9: тесты импорт-мастера (upload/analyze/run/undo/template/photos)."""

import io
import os
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

p = os.path.join(tempfile.gettempdir(), "suot_imp.db")
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
        "/api/auth/register", json={"username": "imp_user", "password": "parol123"}
    )
    HB = {"Authorization": "Bearer " + r.json()["token"]}

    # ── шаблон импорта (предложение 1) ──
    rt = client.get("/api/import/template/employees", headers=HB)
    check("шаблон xlsx скачивается", rt.status_code == 200 and len(rt.content) > 1000)
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(rt.content))
    ws = wb.active
    hdrs = [ws.cell(row=1, column=i).value for i in range(1, ws.max_column + 1)]
    check("шаблон содержит заголовки", "ФИО" in hdrs, str(hdrs[:5]))

    # ── CSV импорт: dry-run + run + undo (предложения 3, 4) ──
    csv_content = (
        "ФИО;Должность;Подразделение;Дата медосмотра\n"
        "Импортов Первый;Сварщик;Цех №1;01.02.2026\n"
        "Импортов Второй;Монтажник;Цех №2;2026-03-05\n"
        "Импортов Третий;Слесарь;;13/13/2026\n"
    ).encode("utf-8")
    rup = client.post(
        "/api/import/upload",
        headers=HB,
        files={"file": ("imp.csv", csv_content, "text/csv")},
    )
    check("CSV загружен", rup.status_code == 200)
    fid = rup.json()["file_id"]

    rprev = client.get(f"/api/import/preview/{fid}", headers=HB)
    check(
        "предпросмотр: 3 строки", rprev.json()["total"] == 3, str(rprev.json()["total"])
    )

    mapping = {
        "ФИО": "ФИО",
        "Должность": "Должность",
        "Подразделение": "Подразделение",
        "Дата медосмотра": "Дата медосмотра",
    }
    body = {"file_id": fid, "table": "employees", "mapping": mapping, "mode": "insert"}
    ran = client.post("/api/import/analyze", headers=HB, json=body)
    j = ran.json()
    check(
        "analyze: 2 к созданию (ошибочная отсечена)",
        j["to_create"] == 2,
        str(j["total"]),
    )
    check(
        "analyze: 1 ошибка (неверная дата)",
        j["error_count"] == 1 and "неверная дата" in j["errors"][0]["error"],
        str(j["errors"][:1]),
    )

    rrun = client.post("/api/import/run", headers=HB, json=body)
    jr = rrun.json()
    check(
        "run: создано 2 (ошибочная пропущена)",
        jr["created"] == 2 and jr["error_count"] == 1,
        str(jr)[:120],
    )
    import_id = jr["import_id"]

    # даты нормализованы (2026-03-05 → 05.03.2026)
    rl = client.get("/api/data/employees?page_size=100", headers=HB)
    imp_rows = [
        i
        for i in rl.json()["items"]
        if str(i["data"].get("ФИО", "")).startswith("Импортов")
    ]
    dates = sorted(i["data"].get("Дата медосмотра", "") for i in imp_rows)
    check(
        "даты нормализованы в ДД.ММ.ГГГГ",
        all("." in d and len(d) == 10 for d in dates),
        str(dates),
    )

    # upsert: тот же файл → все обновятся
    body_up = {**body, "mode": "upsert", "key_field": "ФИО"}
    ran2 = client.post("/api/import/analyze", headers=HB, json=body_up)
    check(
        "upsert analyze: 2 к обновлению",
        ran2.json()["to_update"] == 2,
        str(ran2.json()),
    )
    rrun2 = client.post("/api/import/run", headers=HB, json=body_up)
    check(
        "upsert run: обновлено 2, создано 0",
        rrun2.json()["updated"] == 2 and rrun2.json()["created"] == 0,
        str(rrun2.json())[:120],
    )

    # объединение колонок (Фамилия+Имя → ФИО)
    csv2 = "Фамилия;Имя\nПетров;Пётр\n".encode("utf-8")
    rup2 = client.post(
        "/api/import/upload", headers=HB, files={"file": ("m.csv", csv2, "text/csv")}
    )
    fid2 = rup2.json()["file_id"]
    body_m = {
        "file_id": fid2,
        "table": "employees",
        "mapping": {},
        "mode": "insert",
        "merges": [{"target": "ФИО", "parts": ["Фамилия", "Имя"], "sep": " "}],
    }
    ranm = client.post("/api/import/analyze", headers=HB, json=body_m)
    check(
        "merge: ФИО собрано",
        ranm.json()["sample"][0].get("ФИО") == "Петров Пётр",
        str(ranm.json()["sample"][:1]),
    )
    rrunm = client.post("/api/import/run", headers=HB, json=body_m)
    check("merge run: создано 1", rrunm.json()["created"] == 1)

    # история (предложение 2)
    rh = client.get("/api/import/history", headers=HB)
    check(f"история импортов ({len(rh.json()['items'])})", len(rh.json()["items"]) >= 3)

    # undo (предложение 4): отменить merge → запись удалится
    run_id = rrunm.json()["import_id"]
    ru = client.post("/api/import/undo", headers=HB, json={"import_id": run_id})
    check("undo merge", ru.json().get("undone") == 1, str(ru.json()))
    rl2 = client.get("/api/data/employees?page_size=100", headers=HB)
    check(
        "запись после undo удалена",
        not any("Петров" in str(i["data"].get("ФИО", "")) for i in rl2.json()["items"]),
    )

    # буфер обмена (TSV)
    tsv = "ФИО\tДолжность\nБуфернов Тест;Бухгалтер".encode("utf-8")
    rtxt = client.post(
        "/api/import/upload_text",
        headers=HB,
        json={"text": tsv.decode("utf-8"), "filename": "clipboard.tsv"},
    )
    fid3 = rtxt.json()["file_id"]
    body_t = {
        "file_id": fid3,
        "table": "employees",
        "mapping": {"ФИО": "ФИО", "Должность": "Должность"},
        "mode": "insert",
    }
    rrunt = client.post("/api/import/run", headers=HB, json=body_t)
    check("импорт из буфера (TSV)", rrunt.json()["created"] == 1)

    # фото из ZIP (предложение из part9-плана: фото по ФИО)
    import zipfile
    from PIL import Image

    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, "w") as zf:
        img = io.BytesIO()
        Image.new("RGB", (20, 20), (10, 200, 90)).save(img, "PNG")
        zf.writestr("Импортов Первый.png", img.getvalue())
        zf.writestr("НеКого.png", img.getvalue())
    rz = client.post(
        "/api/import/upload",
        headers=HB,
        files={"file": ("photos.zip", zbuf.getvalue(), "application/zip")},
    )
    fidz = rz.json()["file_id"]
    rph = client.post(
        "/api/import/photos_zip",
        headers=HB,
        json={"file_id": fidz, "table": "employees", "match_by": "ФИО"},
    )
    jph = rph.json()
    check(
        "фото: 1 совпала, 1 нет",
        jph["matched"] == 1 and jph["unmatched_count"] == 1,
        str(jph),
    )
    rl3 = client.get("/api/data/employees?page_size=100", headers=HB)
    imp1 = next(
        i for i in rl3.json()["items"] if i["data"].get("ФИО") == "Импортов Первый"
    )
    check(
        "фото привязано к записи",
        str(imp1["data"].get("Фото", "")).startswith("/media/"),
    )

    # изоляция: чужой импорт не отменить
    radmin = client.post(
        "/api/auth/login", json={"username": "admin", "password": "admin"}
    )
    HAdm = {"Authorization": "Bearer " + radmin.json()["token"]}
    rimp2 = client.post(
        "/api/import/run",
        headers=HB,
        json={
            "file_id": fid,
            "table": "employees",
            "mapping": mapping,
            "mode": "insert",
        },
    )
    imp2_id = rimp2.json()["import_id"]
    ru_admin = client.post(
        "/api/import/undo", headers=HAdm, json={"import_id": imp2_id}
    )
    check("админ может отменить чужой импорт", ru_admin.status_code == 200)

for s in ("", "-wal", "-shm"):
    try:
        os.remove(p + s)
    except OSError:
        pass

print(f"\nИТОГО: {len(PASS)} OK, {len(FAIL)} FAIL")
if FAIL:
    print("Провалены:", FAIL)
    sys.exit(1)
