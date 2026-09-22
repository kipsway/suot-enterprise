"""Часть 30: Финал-качество. Диагностика (diag), активные сессии,
роль Observer; per-user язык/дата; автотема; миграция старой Qt-схемы."""

import os
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

p = os.path.join(tempfile.gettempdir(), "suot_part30.db")
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
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    check("auth: вход admin/admin", r.status_code == 200)
    HB = {"Authorization": "Bearer " + r.json()["token"]}

    # ── Диагностика ──
    d = client.get("/api/diag", headers=HB)
    check("diag: статус 200", d.status_code == 200)
    dj = d.json()
    check(
        "diag: секции app/runtime/server/database",
        all(k in dj for k in ("app", "runtime", "server", "database", "user")),
    )
    check(
        "diag: runtime python версия", dj["runtime"].get("python", "").count(".") >= 2
    )
    check(
        "diag: app name — продукт",
        dj["app"].get("name", "") in ("ОхранаТруда Про", "СУОТ Enterprise"),
    )
    check("diag: server webview2", isinstance(dj["server"].get("webview2"), dict))
    check("diag: user username", dj["user"].get("username") == "admin")
    check("diag: integrity ok", dj["database"]["integrity"].get("ok") is True)
    check(
        "diag: целостность таблиц >= 5",
        dj["database"]["integrity"].get("tables", 0) >= 5,
    )

    sm = client.get("/api/diag/summary", headers=HB).json()
    check(
        "diag/summary: название и порт",
        sm.get("app", {}).get("name", "") in ("ОхранаТруда Про", "СУОТ Enterprise")
        and sm.get("server", {}).get("port", 0) > 0,
    )
    check(
        "diag/summary: users >= 1",
        sm.get("database", {}).get("counts", {}).get("users", 0) >= 1,
    )

    lg = client.get("/api/diag/log", headers=HB)
    check("diag/log: статус 200", lg.status_code == 200)
    check("diag/log: список событий", isinstance(lg.json().get("items"), list))
    check(
        "diag/log: limit работает",
        len(client.get("/api/diag/log?limit=3", headers=HB).json().get("items", []))
        <= 3,
    )

    ds = client.get("/api/diag/disk", headers=HB).json()
    check(
        "diag/disk: каталоги и свободное место",
        "database" in ds.get("dirs", {}) and ds.get("free_bytes", 0) > 0,
    )

    # ── Активные сессии ──
    s0 = client.get("/api/auth/sessions", headers=HB)
    check("auth/sessions: статус 200", s0.status_code == 200)
    sess0 = s0.json().get("sessions", [])
    check("auth/sessions: >=1 сессия после входа", len(sess0) >= 1)
    sid0 = sess0[0]["id"]
    check(
        "auth/sessions: есть id и expires_at",
        bool(sid0) and bool(sess0[0].get("expires_at")),
    )
    check(
        "auth/sessions: не содержит токена/hash",
        all("token" not in k and "hash" not in k for k in sess0[0]),
    )

    # ── Per-user язык и формат даты ──
    loc = client.get("/api/auth/locale", headers=HB)
    check("auth/locale: статус 200", loc.status_code == 200)
    lp = client.post(
        "/api/auth/locale",
        headers=HB,
        json={"language": "en", "date_format": "YYYY-MM-DD"},
    )
    check("auth/locale: запись 200", lp.status_code == 200)
    check(
        "auth/locale: сохранено",
        client.get("/api/auth/locale", headers=HB).json().get("date_format")
        == "YYYY-MM-DD",
    )
    r2 = client.post(
        "/api/auth/register", json={"username": "part30_second", "password": "parol123"}
    )
    HB2 = {"Authorization": "Bearer " + r2.json()["token"]}
    check(
        "auth/locale: изоляция per-user",
        client.get("/api/auth/locale", headers=HB2).json().get("date_format")
        != "YYYY-MM-DD",
    )

    # ── Автотема по умолчанию ──
    ap = client.get("/api/settings/appearance", headers=HB).json()
    check("appearance: тема по умолчанию auto", ap.get("theme") == "auto")

    # ── Роль Observer ──
    set_obs = client.post(
        "/api/admin/users/{}/role".format(r2.json()["user"]["id"]),
        headers=HB,
        json={"role": "Observer"},
    )
    check("admin: роль Observer принята", set_obs.status_code == 200)
    me2 = client.get("/api/auth/me", headers=HB2).json()
    check("admin: me пользователя = Observer", me2["user"].get("role") == "Observer")
    ok_view = client.get("/api/help/version", headers=HB2).status_code
    check("observer: чтение разрешено", ok_view == 200)
    bad_act = client.post(
        "/api/admin/users/{}/role".format(r2.json()["user"]["id"]),
        headers=HB2,
        json={"role": "Administrator"},
    )
    check(
        "observer: смена чужой роли запрещена",
        bad_act.status_code in (401, 403),
    )

    # ── Revoke сессии и logout ──
    s1 = client.get("/api/auth/sessions", headers=HB).json().get("sessions", [])
    if len(s1) > 1:
        old = [x for x in s1 if x["id"] != sid0][0]
        rv = client.post("/api/auth/sessions/{}/revoke".format(old["id"]), headers=HB)
        check("sessions: revoke старой сессии 200", rv.status_code == 200)
    else:
        check("sessions: revoke (нет кандидатов, пропуск)", True)

    lg2 = client.post("/api/auth/logout", headers=HB).json()
    check("auth/logout: ok", lg2.get("ok"))
    me_after = client.get("/api/auth/me", headers=HB)
    check("auth: me после logout -> 401", me_after.status_code == 401)
    dl = client.get("/api/diag", headers=HB)
    check("diag: после logout -> 401", dl.status_code == 401)

# ── Миграция старой Qt-схемы (отдельный процесс: singleton) ──
import json as _json  # noqa: E402
import subprocess as _sp  # noqa: E402

_legacy_code = (
    "import os,sys,tempfile,sqlite3,json\n"
    "sys.stdout.reconfigure(encoding='utf-8',errors='replace')\n"
    "sys.path.insert(0, r'__ROOT__')\n"
    "oldp=os.path.join(tempfile.gettempdir(),'suot_legacy_qt.db')\n"
    "for s in ('','-wal','-shm'):\n"
    "    try: os.remove(oldp+s)\n"
    "    except OSError: pass\n"
    "con=sqlite3.connect(oldp)\n"
    'con.executescript("CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT,'
    " username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,"
    " full_name TEXT DEFAULT '', role TEXT DEFAULT 'user',"
    " created_at TEXT DEFAULT (datetime('now')), records INTEGER DEFAULT 0,"
    ' restored_at TEXT);")\n'
    "con.commit(); con.close()\n"
    "from services.database import DatabaseManager\n"
    "db=DatabaseManager(oldp)\n"
    "rep=db.migrate_legacy_qt()\n"
    "cols=[r[1] for r in db._backend.execute('PRAGMA table_info(users)').fetchall()]\n"
    'tabs=[r[0] for r in db._backend.execute("SELECT name FROM sqlite_master'
    " WHERE type='table'\").fetchall()]\n"
    "db.migrate_legacy_qt()\n"
    "db.close()\n"
    "print(json.dumps({'has_sec': ('sec_question' in cols and 'backup_codes' in cols),"
    " 'has_sessions': 'sessions' in tabs, 'patched': bool(rep.get('patched'))}))\n"
).replace("__ROOT__", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_mig_out = _sp.run(
    [sys.executable, "-c", _legacy_code], capture_output=True, text=True, timeout=60
)
if _mig_out.returncode == 0 and _mig_out.stdout.strip():
    _mig = _json.loads(_mig_out.stdout.strip().splitlines()[-1])
    check("migrate: колонки безопасности добавлены", _mig.get("has_sec"))
    check("migrate: таблица sessions создана", _mig.get("has_sessions"))
    check("migrate: отчёт о патчах не пуст", _mig.get("patched") is True)
else:
    check(
        "migrate: подпроцесс выполнился",
        False,
        _mig_out.stderr[:300] if _mig_out.stderr else _mig_out.stdout[:300],
    )

print(f"\nИтого Ч30-бэк: {len(PASS)} OK, {len(FAIL)} FAIL")
if FAIL:
    print("Провалены:", FAIL)
