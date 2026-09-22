"""Часть 21: мастер первого запуска + восстановление по вопросу."""

import os
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Чистая база БЕЗ сида: убираем env до импорта приложения
p = os.path.join(tempfile.gettempdir(), "suot_setup21.db")
for s in ("", "-wal", "-shm"):
    try:
        os.remove(p + s)
    except OSError:
        pass
os.environ.pop("SUOT_E2E_DB", None)
os.environ["SUOT_DB_PATH"] = p

from fastapi.testclient import TestClient  # noqa: E402
import services.database as sdb  # noqa: E402

_orig_init = sdb.DatabaseManager.__init__


def _init(self, database_path=None):
    if hasattr(self, "_initialized"):
        return
    database_path = database_path or p
    _orig_init(self, database_path)


sdb.DatabaseManager.__init__ = _init
# Перезапуск синглтона на чистую базу без сид-админа
if hasattr(sdb.DatabaseManager, "_instance"):
    sdb.DatabaseManager._instance = None

from server.app import app  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(("  OK " if cond else "FAIL ") + name + (f" | {extra}" if extra else ""))


client = TestClient(app)

with client:
    st = client.get("/api/setup/status")
    check("status: нужен мастер", st.json()["needed"] is True)

    r = client.post("/api/auth/login", json={"username": "x", "password": "xxxxxx"})
    check("вход до настройки → 401", r.status_code == 401)

    # admin/admin запрещён явно
    bad = client.post(
        "/api/setup/admin",
        json={
            "username": "admin",
            "password": "admin",
            "sec_question": "Город?",
            "sec_answer": "Москва",
        },
    )
    check("admin/admin отклонён", bad.status_code == 400)

    # Короткий пароль
    short = client.post(
        "/api/setup/admin",
        json={
            "username": "boss",
            "password": "123",
            "sec_question": "Город?",
            "sec_answer": "Москва",
        },
    )
    check("короткий пароль → 400", short.status_code == 400)

    ok = client.post(
        "/api/setup/admin",
        json={
            "org_name": "ООО Ромашка",
            "username": "boss",
            "password": "parol123",
            "full_name": "Босс Организации",
            "sec_question": "Город рождения?",
            "sec_answer": "казань",
            "theme": "dark",
            "lang": "ru",
        },
    )
    check(
        "админ создан мастером",
        ok.status_code == 200 and ok.json()["user"]["role"] == "Administrator",
    )
    H = {"Authorization": "Bearer " + ok.json()["token"]}

    st2 = client.get("/api/setup/status")
    check("после мастера: not needed", st2.json()["needed"] is False)

    dup = client.post(
        "/api/setup/admin",
        json={
            "username": "other",
            "password": "parol123",
            "sec_question": "?",
            "sec_answer": "?",
        },
    )
    check("повторный мастер → 409", dup.status_code == 409)

    me = client.get("/api/auth/me", headers=H)
    check(
        "токен из мастера работает",
        me.status_code == 200 and me.json()["user"]["username"] == "boss",
    )

    br = client.get("/api/setup/branding", headers=H)
    check("брендинг сохранён", br.json()["org_name"] == "ООО Ромашка")

    # ── Восстановление по секретному вопросу ──
    q = client.post("/api/setup/recover/question", json={"username": "BOSS"})
    check(
        "вопрос получен (регистронезависимо)",
        q.status_code == 200 and "Город" in q.json()["question"],
    )

    wrong = client.post(
        "/api/setup/recover/reset",
        json={"username": "boss", "answer": "москва", "new_password": "newpass99"},
    )
    check("неверный ответ → 401", wrong.status_code == 401)

    good = client.post(
        "/api/setup/recover/reset",
        json={"username": "boss", "answer": "КАЗАНЬ", "new_password": "newpass99"},
    )
    check(
        "сброс по верному ответу (без учёта регистра)",
        good.status_code == 200 and good.json().get("token"),
    )

    relog = client.post(
        "/api/auth/login", json={"username": "boss", "password": "newpass99"}
    )
    check("вход с новым паролем", relog.status_code == 200)

    noq = client.post("/api/setup/recover/question", json={"username": "ghost"})
    check("нет юзера/вопроса → 404", noq.status_code == 404)

for s in ("", "-wal", "-shm"):
    try:
        os.remove(p + s)
    except OSError:
        pass

print(f"\nИТОГО: {len(PASS)} OK, {len(FAIL)} FAIL")
if FAIL:
    print("Провалены:", FAIL)
    sys.exit(1)
