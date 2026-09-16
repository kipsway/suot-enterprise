"""Часть 19: тесты бэкапов и плагинов."""

import io
import json
import os
import sys
import tempfile
import zipfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

p = os.path.join(tempfile.gettempdir(), "suot_b19.db")
for s in ("", "-wal", "-shm"):
    try:
        os.remove(p + s)
    except OSError:
        pass
os.environ["SUOT_E2E_DB"] = p

from fastapi.testclient import TestClient  # noqa: E402
from server.app import app  # noqa: E402
from server.routers.backup_api import create_backup_file, run_auto_backup, prune_backups  # noqa: E402
from services.database import DatabaseManager  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(("  OK " if cond else "FAIL ") + name + (f" | {extra}" if extra else ""))


client = TestClient(app)
with client:
    radmin = client.post(
        "/api/auth/login", json={"username": "admin", "password": "admin"}
    )
    HA = {"Authorization": "Bearer " + radmin.json()["token"]}
    ru = client.post(
        "/api/auth/register", json={"username": "b19_user", "password": "parol123"}
    )
    HU = {"Authorization": "Bearer " + ru.json()["token"]}

    # Данные до бэкапа
    rc = client.post(
        "/api/data/employees",
        headers=HA,
        json={"data": {"ФИО": "Бэкапов Тест", "Должность": "Хранитель"}},
    )
    check("данные созданы", rc.status_code == 201)

    # Не-админ → 403 на операции изменения
    r = client.post("/api/backup/create", headers=HU)
    check("не-админ create → 403", r.status_code == 403)
    rp = client.post(
        "/api/backup/settings", headers=HU, json={"enabled": False, "keep": 1}
    )
    check("не-админ settings POST → 403", rp.status_code == 403)

    # Настройки авто-бэкапа roundtrip
    rs = client.post(
        "/api/backup/settings", headers=HA, json={"enabled": True, "keep": 7}
    )
    rg = client.get("/api/backup/settings", headers=HA)
    check(
        "настройки: keep=7 сохранён",
        rg.json()["enabled"] is True and rg.json()["keep"] == 7,
    )

    # Создание бэкапа
    rb = client.post("/api/backup/create", headers=HA)
    check(
        "бэкап создан",
        rb.status_code == 200 and rb.json()["file"].endswith(".zip"),
        str(rb.json())[:90],
    )
    fname = rb.json()["file"]

    # ZIP валиден: database.db + manifest.json + stats
    bdir = os.path.join(os.path.dirname(p), "backups")
    zpath = os.path.join(bdir, fname)
    with zipfile.ZipFile(zpath) as z:
        names = z.namelist()
        man = json.loads(z.read("manifest.json"))
    check(
        "ZIP содержит БД+манифест",
        "database.db" in names and "manifest.json" in names,
        str(names[:4]),
    )
    check(
        "манифест: версия+stats.users>=2",
        man["app_version"].startswith("2.2")
        and man["stats"]["users"] >= 2
        and man["stats"]["tables"].get("employees", 0) >= 1,
        f"users={man['stats']['users']}",
    )

    # Список
    rl = client.get("/api/backup/list", headers=HA)
    check("list содержит бэкап", any(i["name"] == fname for i in rl.json()["items"]))

    # Предпросмотр (stats) без распаковки
    rst = client.get(f"/api/backup/stats?name={fname}", headers=HA)
    st = rst.json()
    check(
        "предпросмотр: created_at+employees>=1",
        st["created_at"] and st["stats"]["tables"]["employees"] >= 1,
    )

    # Path traversal защита
    rbad = client.get("/api/backup/stats?name=../../secret.zip", headers=HA)
    check("path traversal → 400", rbad.status_code == 400)

    # Изменяем данные после бэкапа
    client.post(
        "/api/data/employees", headers=HA, json={"data": {"ФИО": "ПослеБэкапа Кто-то"}}
    )
    before_cnt = client.get("/api/data/employees", headers=HA).json()["total"]
    check("после бэкапа добавлен второй", before_cnt >= 2, str(before_cnt))

    # Восстановление
    rr = client.post(f"/api/backup/restore?name={fname}", headers=HA)
    check("restore ok", rr.status_code == 200, str(rr.json())[:80])
    after = client.get(
        "/api/data/employees?q=" + "ПослеБэкапа".encode("utf-8").hex(), headers=HA
    )
    # q принимает текст — кодируем нормально:
    import urllib.parse

    after = client.get(
        "/api/data/employees", params={"q": "ПослеБэкапа"}, headers=HA
    ).json()
    check("после restore второй исчез", after["total"] == 0, f"total={after['total']}")
    # Сессии живы после подмены файла
    ra = client.get("/api/auth/me", headers=HA)
    check("сессия админа жива после restore", ra.status_code == 200)

    # Скачивание
    rd = client.get(f"/api/backup/download?name={fname}", headers=HA)
    check("download 200 zip", rd.status_code == 200 and rd.content[:2] == b"PK")

# ── Авто-бэкап и ротация (прямые вызовы) ────────────────────────
db = DatabaseManager(p)
p1 = create_backup_file(db, tag="auto")
p2 = create_backup_file(db, tag="auto")
check("два auto-бэкапа созданы", os.path.isfile(p1) and os.path.isfile(p2))
db.upsert_setting("auto_backup_enabled", "1")
db.upsert_setting("auto_backup_keep", "5")
again = run_auto_backup(db)
bdir = os.path.join(os.path.dirname(p), "backups")
autos_today = [f for f in os.listdir(bdir) if f.startswith("auto_")]
check(
    "повторный авто-бэкап сегодня пропущен",
    again is None and len(autos_today) >= 2,
    str(len(autos_today)),
)
removed = prune_backups(db)
files_now = [f for f in os.listdir(bdir) if f.endswith(".zip")]
check(
    f"ротация: осталось <=5 ({len(files_now)})",
    len(files_now) <= 5,
    f"removed={removed}",
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
