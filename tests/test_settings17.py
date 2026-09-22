"""Часть 17: тесты настроек (appearance, hotkeys, reset, export/import)."""

import os
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

p = os.path.join(tempfile.gettempdir(), "suot_set17.db")
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
    rA = client.post(
        "/api/auth/register", json={"username": "set_a", "password": "parol123"}
    )
    rB = client.post(
        "/api/auth/register", json={"username": "set_b", "password": "parol123"}
    )
    HA = {"Authorization": "Bearer " + rA.json()["token"]}
    HB = {"Authorization": "Bearer " + rB.json()["token"]}

    # Defaults
    d = client.get("/api/settings/appearance", headers=HA).json()
    check(
        "appearance: defaults",
        d["theme"] == "auto" and d["glass"] is True and d["font_scale"] == 1.0,
    )

    # Сохранение валидное
    rsv = client.post(
        "/api/settings/appearance",
        headers=HA,
        json={
            "theme": "ocean",
            "accent": "#0EA5E9",
            "font_family": "serif",
            "font_scale": 1.1,
            "glass": False,
            "density": "compact",
            "radius": "lg",
            "watermark": "ЧЕРНОВИК",
        },
    )
    check(
        "appearance: сохранение",
        rsv.status_code == 200 and rsv.json()["theme"] == "ocean",
    )

    # Изоляция: B видит дефолты
    db_ = client.get("/api/settings/appearance", headers=HB).json()
    check("изоляция: B видит defaults", db_["theme"] == "auto")

    # Невалидная тема → 400
    bad = client.post(
        "/api/settings/appearance", headers=HA, json={"theme": "purple-rain"}
    )
    check("неизвестная тема → 400", bad.status_code == 400)

    # Хоткеи: defaults
    hk = client.get("/api/settings/hotkeys", headers=HA).json()
    check("hotkeys: defaults", hk["palette"] == "Ctrl+K" and hk["help"] == "F1")

    # Хоткеи: переназначение
    hks = client.post(
        "/api/settings/hotkeys",
        headers=HA,
        json={
            "hotkeys": {
                "palette": "Ctrl+/",
                "new_record": "Ctrl+Alt+N",
                "bogus_key": "X",
                "help": "",
            }
        },
    )
    hj = hks.json()["hotkeys"]
    check(
        "hotkeys: сохранение+фильтр",
        hj["palette"] == "Ctrl+/" and "bogus_key" not in hj and hj["help"] == "F1",
    )

    # Сброс
    rs = client.post("/api/settings/reset", headers=HA)
    ra = client.get("/api/settings/appearance", headers=HA).json()
    rh = client.get("/api/settings/hotkeys", headers=HA).json()
    check(
        "reset возвращает defaults",
        rs.status_code == 200 and ra["theme"] == "auto" and rh["palette"] == "Ctrl+K",
    )

    # Экспорт
    client.post(
        "/api/settings/appearance",
        headers=HA,
        json={"theme": "sunset", "accent": "#F97316"},
    )
    ex = client.get("/api/settings/export", headers=HA)
    body = ex.json()
    check(
        "export: формат",
        body["_format"] == "suot-settings" and body["appearance"]["theme"] == "sunset",
    )

    # Импорт (в B)
    im = client.post(
        "/api/settings/import",
        headers=HB,
        json={"appearance": body["appearance"], "hotkeys": {"palette": "Ctrl+J"}},
    )
    imb = client.get("/api/settings/appearance", headers=HB).json()
    hkb = client.get("/api/settings/hotkeys", headers=HB).json()
    check(
        "import применён к B", imb["theme"] == "sunset" and hkb["palette"] == "Ctrl+J"
    )

    # Импорт мусора → 400
    junk = client.post("/api/settings/import", headers=HB, json={"unknown_field": True})
    check("import мусора → 400", junk.status_code == 400)

for s in ("", "-wal", "-shm"):
    try:
        os.remove(p + s)
    except OSError:
        pass

print(f"\nИТОГО: {len(PASS)} OK, {len(FAIL)} FAIL")
if FAIL:
    print("Провалены:", FAIL)
    sys.exit(1)
