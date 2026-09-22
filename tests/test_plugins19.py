"""Часть 19: тесты плагинов."""

import os
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

p = os.path.join(tempfile.gettempdir(), "suot_pl19.db")
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
    radmin = client.post(
        "/api/auth/login", json={"username": "admin", "password": "admin"}
    )
    HA = {"Authorization": "Bearer " + radmin.json()["token"]}
    ru = client.post(
        "/api/auth/register", json={"username": "pl_user", "password": "parol123"}
    )
    HU = {"Authorization": "Bearer " + ru.json()["token"]}

    # Список из web/plugins
    rl = client.get("/api/plugins", headers=HA)
    items = {i["id"]: i for i in rl.json()["items"]}
    check("3 плагина найдены", len(items) == 3, str(list(items)))

    # Дефолты: два вкл, шаблон выкл
    check(
        "дефолты enabled_by_default",
        items["quick-overdue"]["enabled"] is True
        and items["copy-tsv"]["enabled"] is True
        and items["template-plugin"]["enabled"] is False,
    )

    # raw отдаёт только включённые с полным манифестом
    rr = client.get("/api/plugins/raw", headers=HA)
    raw_ids = [x["id"] for x in rr.json()["items"]]
    check(
        "raw: только включённые",
        set(raw_ids) == {"quick-overdue", "copy-tsv"}
        and all("commands" in x for x in rr.json()["items"]),
    )

    # Не-админ не может переключать
    rt = client.post(
        "/api/plugins/copy-tsv/toggle", headers=HU, json={"enabled": False}
    )
    check("toggle не-админ → 403", rt.status_code == 403)

    # Выключить copy-tsv
    rt1 = client.post(
        "/api/plugins/copy-tsv/toggle", headers=HA, json={"enabled": False}
    )
    rl2 = client.get("/api/plugins", headers=HA).json()
    st = {i["id"]: i["enabled"] for i in rl2["items"]}
    check("выключение сохранилось", st["copy-tsv"] is False)
    rr2 = client.get("/api/plugins/raw", headers=HA).json()
    check("raw исключил выключенный", "copy-tsv" not in [x["id"] for x in rr2["items"]])

    # Включить шаблон (default-false → force_enabled)
    rt2 = client.post(
        "/api/plugins/template-plugin/toggle", headers=HA, json={"enabled": True}
    )
    st2 = {
        i["id"]: i["enabled"]
        for i in client.get("/api/plugins", headers=HA).json()["items"]
    }
    check(
        "включение default-false работает",
        st2["template-plugin"] is True and st2["copy-tsv"] is False,
    )

    # Вернуть как было + несуществующий → 404
    client.post("/api/plugins/copy-tsv/toggle", headers=HA, json={"enabled": True})
    client.post(
        "/api/plugins/template-plugin/toggle", headers=HA, json={"enabled": False}
    )
    r404 = client.post("/api/plugins/nope/toggle", headers=HA, json={"enabled": True})
    check("неизвестный плагин → 404", r404.status_code == 404)

for s in ("", "-wal", "-shm"):
    try:
        os.remove(p + s)
    except OSError:
        pass

print(f"\nИТОГО: {len(PASS)} OK, {len(FAIL)} FAIL")
if FAIL:
    print("Провалены:", FAIL)
    sys.exit(1)
