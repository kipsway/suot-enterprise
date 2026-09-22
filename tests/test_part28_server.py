"""Часть 28: Инструменты — погода (no-city/graceful), калькулятор дат,
макросы v1 «Конец месяца», сохранение города."""

import os
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

p = os.path.join(tempfile.gettempdir(), "suot_part28.db")
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
        "/api/auth/register", json={"username": "part28_user", "password": "parol123"}
    )
    HB = {"Authorization": "Bearer " + r.json()["token"]}

    # ── Погода: без города → вежливая подсказка ──
    w = client.get("/api/tools/weather", headers=HB).json()
    check(
        "погода: без города → подсказка",
        not w.get("ok") and w.get("error") == "no_city",
    )

    # ── Погода: сохранить город (per-user) ──
    cs = client.post("/api/tools/weather/city", headers=HB, json={"city": "Москва"})
    check(
        "погода: сохранение города",
        cs.status_code == 200 and cs.json().get("city") == "Москва",
    )
    # город сохранился → запрос уходит в open-meteo; проверяем только что endpoint не падает
    w2 = client.get("/api/tools/weather", headers=HB)
    check("погода: запрос с городом не падает (200)", w2.status_code == 200)

    # ── Погода: другой пользователь не видит чужой город ──
    r2 = client.post(
        "/api/auth/register", json={"username": "part28_user2", "password": "parol123"}
    )
    HB2 = {"Authorization": "Bearer " + r2.json()["token"]}
    w3 = client.get("/api/tools/weather", headers=HB2).json()
    check("погода: изоляция города per-user", w3.get("error") == "no_city")

    # ── Калькулятор: разница в днях ──
    dd = client.post(
        "/api/tools/datecalc",
        headers=HB,
        json={"op": "diff_days", "a": "2026-01-01", "b": "2026-01-31"},
    ).json()
    check("даты: разница дней = 30", dd.get("result") == 30)

    # ── Стаж: годы/месяцы/дни ──
    se = client.post(
        "/api/tools/datecalc",
        headers=HB,
        json={"op": "seniority", "a": "2020-05-10", "b": "2026-02-25"},
    ).json()
    check(
        "даты: стаж 5г 9м 15д",
        (se.get("years"), se.get("months"), se.get("days")) == (5, 9, 15),
    )

    # ── Стаж: конец раньше начала → ошибка ──
    se_bad = client.post(
        "/api/tools/datecalc",
        headers=HB,
        json={"op": "seniority", "a": "2026-05-10", "b": "2020-02-25"},
    ).json()
    check("даты: стаж (конец<начало) → ошибка", not se_bad.get("ok"))

    # ── Рабочие дни: январь 2026 = 22 ──
    wd = client.post(
        "/api/tools/datecalc",
        headers=HB,
        json={"op": "workdays", "a": "2026-01-01", "b": "2026-01-31"},
    ).json()
    check("даты: рабочие дни января = 22", wd.get("result") == 22)

    # ── Рабочие дни: без конца → до сегодня ──
    wd2 = client.post(
        "/api/tools/datecalc",
        headers=HB,
        json={"op": "workdays", "a": "2026-01-01"},
    ).json()
    check("даты: рабочие дни (a..сегодня) OK", wd2.get("result", -1) > 0)

    # ── Конец месяца ──
    me = client.post(
        "/api/tools/datecalc",
        headers=HB,
        json={"op": "month_end", "a": "2026-02-10"},
    ).json()
    check("даты: конец февраля 2026 = 28", me.get("result") == "2026-02-28")
    me2 = client.post(
        "/api/tools/datecalc",
        headers=HB,
        json={"op": "month_end", "a": "2026-03-15"},
    ).json()
    check("даты: конец марта 2026 = 31", me2.get("result") == "2026-03-31")

    # ── Макросы: список ──
    ml = client.get("/api/tools/macros", headers=HB).json()
    names = [m["name"] for m in ml["items"]]
    check("макросы: месяц-конец в списке", "month_end" in names)

    # ── Макрос: запуск «Конец месяца» ──
    mr = client.post(
        "/api/tools/macros/run", headers=HB, json={"name": "month_end"}
    ).json()
    check(
        "макрос: month_end → ISO дата", mr.get("ok") and len(mr.get("result", "")) == 10
    )

    # ── Погода: доступ без токена → 401 ──
    anon = client.get("/api/tools/weather")
    check("tools: без токена → 401", anon.status_code == 401)

print(f"\nИтого Ч28-бэк: {len(PASS)} OK, {len(FAIL)} FAIL")
if FAIL:
    print("Провалены:", FAIL)
