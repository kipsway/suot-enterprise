"""Часть 18: тесты (версия, журнал, пользователи, пароли, обновления)."""

import os
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

p = os.path.join(tempfile.gettempdir(), "suot_h18.db")
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
    # admin/admin сид + обычный пользователь
    radmin = client.post(
        "/api/auth/login", json={"username": "admin", "password": "admin"}
    )
    HAdm = {"Authorization": "Bearer " + radmin.json()["token"]}
    ru = client.post(
        "/api/auth/register",
        json={
            "username": "h18_user",
            "password": "parol123",
            "full_name": "Журналистов Ж",
        },
    )
    HU = {"Authorization": "Bearer " + ru.json()["token"]}

    # Версия
    rv = client.get("/api/help/version")
    check(
        "version endpoint",
        rv.status_code == 200 and rv.json()["version"].count(".") == 2,
    )

    # События появляются (логин/регистрация уже записаны)
    re1 = client.get("/api/events", headers=HAdm)
    check("events: список не пуст", re1.json()["total"] >= 2, str(re1.json()["total"]))
    ev_user = client.get("/api/events", headers=HU)
    check(
        "events: юзер видит только свои",
        all(i["username"] in ("h18_user",) for i in ev_user.json()["items"]),
        f"n={ev_user.json()['total']}",
    )

    # Фильтр q
    rq = client.get("/api/events?q=login", headers=HAdm)
    check(
        "events: фильтр q",
        all(
            "login" in i["event"].lower() or "login" in i["details"].lower()
            for i in rq.json()["items"]
        )
        and rq.json()["total"] >= 1,
        str(rq.json()["total"]),
    )

    # CSV
    rc = client.get("/api/events/export.csv", headers=HAdm)
    check(
        "events: CSV с BOM и заголовком",
        rc.status_code == 200
        and rc.content[:3] == b"\xef\xbb\xbf"
        and "Событие".encode("utf-8") in rc.content[:200],
    )

    # Пользователи: не-админ → 403
    r403 = client.get("/api/admin/users", headers=HU)
    check("users: не-админ → 403", r403.status_code == 403)

    ra = client.get("/api/admin/users", headers=HAdm)
    users = {u["username"]: u for u in ra.json()["users"]}
    check(
        "users: список с ролями",
        users["admin"]["role"] == "Administrator"
        and users["h18_user"]["records"] == 0
        and users["h18_user"]["active"] is True,
    )

    uid = users["h18_user"]["id"]
    adm_id = users["admin"]["id"]

    # Смена роли
    rr = client.post(
        f"/api/admin/users/{uid}/role", headers=HAdm, json={"role": "Administrator"}
    )
    check("role → Administrator", rr.status_code == 200)
    rr_back = client.post(
        f"/api/admin/users/{uid}/role", headers=HAdm, json={"role": "user"}
    )
    check("role обратно → user", rr_back.status_code == 200)
    rself = client.post(
        f"/api/admin/users/{adm_id}/role", headers=HAdm, json={"role": "user"}
    )
    check("role: снять с себя → 400", rself.status_code == 400)

    # Блокировка: вход и существующий токен отвергаются
    rb = client.post(
        f"/api/admin/users/{uid}/block", headers=HAdm, json={"blocked": True}
    )
    check("block ok", rb.status_code == 200)
    rl = client.post(
        "/api/auth/login", json={"username": "h18_user", "password": "parol123"}
    )
    check("заблокирован: login → 403", rl.status_code == 403, str(rl.status_code))
    rme = client.get("/api/auth/me", headers=HU)
    # Сессии отзываются при блокировке → старый токен мёртв (401 вместо 403).
    check("заблокирован: старый токен → 401", rme.status_code == 401)
    runb = client.post(
        f"/api/admin/users/{uid}/block", headers=HAdm, json={"blocked": False}
    )
    check("unblock ok", runb.status_code == 200)
    rl2 = client.post(
        "/api/auth/login", json={"username": "h18_user", "password": "parol123"}
    )
    check("после unblock вход работает", rl2.status_code == 200)
    HU2 = {"Authorization": "Bearer " + rl2.json()["token"]}
    rself_block = client.post(
        f"/api/admin/users/{adm_id}/block", headers=HAdm, json={"blocked": True}
    )
    check("block себя → 400", rself_block.status_code == 400)

    # Сброс пароля админом
    rp = client.post(f"/api/admin/users/{uid}/reset_password", headers=HAdm)
    new_pwd = rp.json().get("new_password", "")
    check("reset_password выдаёт новый", len(new_pwd) >= 8)
    rl_old = client.post(
        "/api/auth/login", json={"username": "h18_user", "password": "parol123"}
    )
    check("старый пароль больше не работает", rl_old.status_code == 401)
    rl_new = client.post(
        "/api/auth/login", json={"username": "h18_user", "password": new_pwd}
    )
    check("вход с новым паролем", rl_new.status_code == 200)
    HU3 = {"Authorization": "Bearer " + rl_new.json()["token"]}

    # Смена своего пароля
    rw = client.post(
        "/api/auth/change_password",
        headers=HU3,
        json={"old_password": "nevedomoparol", "new_password": "newpass99"},
    )
    check("смена: неверный старый → 400", rw.status_code == 400)
    rok = client.post(
        "/api/auth/change_password",
        headers=HU3,
        json={"old_password": new_pwd, "new_password": "newpass99"},
    )
    check("смена пароля ок", rok.status_code == 200)
    rl3 = client.post(
        "/api/auth/login", json={"username": "h18_user", "password": "newpass99"}
    )
    check("вход после смены", rl3.status_code == 200)

    # Обновления
    rnc = client.post("/api/update/check", headers=HAdm, json={})
    check(
        "update: with default manifest",
        rnc.json()["status"] in ("ok", "unreachable"),
    )
    runr = client.post(
        "/api/update/check",
        headers=HAdm,
        json={"manifest_url": "http://127.0.0.1:9/manifest.json"},
    )
    check("update: недоступен → unreachable", runr.json()["status"] == "unreachable")

for s in ("", "-wal", "-shm"):
    try:
        os.remove(p + s)
    except OSError:
        pass

print(f"\nИТОГО: {len(PASS)} OK, {len(FAIL)} FAIL")
if FAIL:
    print("Провалены:", FAIL)
    sys.exit(1)
