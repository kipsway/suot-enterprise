"""Часть 6 (SUOT Next, Блок 6): серверные задачи bulk jobs.
Создание/выполнение/отмена/retry/history/export, изоляция по владельцу.

Запуск: python tests/test_tasks_server.py
"""

import os
import sys
import tempfile
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

TMP_DB = os.path.join(tempfile.gettempdir(), "suot_tasks_srv.db")
for sfx in ("", "-wal", "-shm"):
    try:
        if os.path.exists(TMP_DB + sfx):
            os.remove(TMP_DB + sfx)
    except PermissionError:
        pass
os.environ["SUOT_E2E_DB"] = TMP_DB

from fastapi.testclient import TestClient  # noqa: E402

from server.app import app  # noqa: E402

c = TestClient(app).__enter__()
PASS, FAIL = [], []


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(("  OK " if cond else "FAIL ") + name + (f" | {extra}" if extra else ""))


def H(t):
    return {"Authorization": "Bearer " + t}


def wait_job(tok, jid, timeout=30):
    deadline = time.time() + timeout
    last = {}
    while time.time() < deadline:
        last = c.get(f"/api/jobs/{jid}", headers=H(tok)).json()
        if last.get("status") in ("completed", "failed", "cancelled"):
            return last
        time.sleep(0.2)
    return last


adm = c.post("/api/auth/login", json={"username": "admin", "password": "admin"}).json()[
    "token"
]
c.post(
    "/api/auth/register",
    json={"username": "worker2", "password": "secret12", "full_name": "W2"},
)
usr = c.post(
    "/api/auth/login", json={"username": "worker2", "password": "secret12"}
).json()["token"]

print("== validation ==")
r = c.post(
    "/api/jobs/bulk",
    headers=H(adm),
    json={"kind": "nope", "target": "employees", "ids": [1]},
)
check("bad kind -> 400", r.status_code == 400, r.status_code)
r = c.post(
    "/api/jobs/bulk",
    headers=H(adm),
    json={"kind": "edit", "target": "employees", "ids": []},
)
check("empty ids -> 400", r.status_code == 400, r.status_code)
r = c.post(
    "/api/jobs/bulk",
    headers=H(adm),
    json={"kind": "edit", "target": "no_table", "ids": [1]},
)
check("bad target -> 400", r.status_code == 400, r.status_code)
r = c.post(
    "/api/jobs/bulk",
    headers=H(adm),
    json={
        "kind": "custom_edit",
        "target": "u_missing",
        "ids": [1],
        "field": "F",
        "value": "v",
    },
)
check("missing custom table -> 400", r.status_code == 400, r.status_code)
r = c.post(
    "/api/jobs/bulk",
    headers=H(usr),
    json={"kind": "edit", "target": "no_table", "ids": [1]},
)
check("user bad target -> 400", r.status_code == 400, r.status_code)

print("== edit lifecycle ==")
ids = []
for i in range(3):
    r = c.post(
        "/api/data/employees", headers=H(adm), json={"data": {"ФИО": f"Job {i}"}}
    )
    ids.append(r.json()["id"])
r = c.post(
    "/api/jobs/bulk",
    headers=H(adm),
    json={
        "kind": "edit",
        "target": "employees",
        "ids": ids,
        "field": "Должность",
        "value": "Мастер",
    },
)
check("create 202", r.status_code == 202, r.status_code)
jid = r.json()["job_id"]
j = wait_job(adm, jid)
check("completed", j.get("status") == "completed", j.get("status"))
check("done==3", j.get("done") == 3, j.get("done"))
vals = {
    c.get(f"/api/data/employees/{i}", headers=H(adm)).json()["data"].get("Должность")
    for i in ids
}
check("values applied", vals == {"Мастер"}, str(vals))

print("== failed + retry ==")
r = c.post(
    "/api/jobs/bulk",
    headers=H(adm),
    json={
        "kind": "edit",
        "target": "employees",
        "ids": ids,
        "field": "НетТакойКолонки",
        "value": "x",
    },
)
fj = r.json()["job_id"]
f = wait_job(adm, fj)
check("bad field -> failed", f.get("status") == "failed", f.get("status"))
check("error text", bool(f.get("error")), str(f.get("error"))[:60])
r = c.post(f"/api/jobs/{fj}/retry", headers=H(adm))
check("retry accepted", r.status_code == 200, r.status_code)
f2 = wait_job(adm, fj)
check("retry re-executed", f2.get("status") == "failed", f2.get("status"))
r = c.post(f"/api/jobs/{jid}/retry", headers=H(adm))
check("retry completed -> 409", r.status_code == 409, r.status_code)
r = c.post("/api/jobs/does-not-exist/retry", headers=H(adm))
check("retry missing -> 404", r.status_code == 404, r.status_code)

print("== cancel + resume ==")
big = []
for i in range(150):
    r = c.post(
        "/api/data/employees", headers=H(adm), json={"data": {"ФИО": f"Bulk {i}"}}
    )
    big.append(r.json()["id"])
r = c.post(
    "/api/jobs/bulk",
    headers=H(adm),
    json={"kind": "delete", "target": "employees", "ids": big},
)
cj = r.json()["job_id"]
r = c.post(f"/api/jobs/{cj}/cancel", headers=H(adm))
check("cancel accepted", r.status_code == 200, r.status_code)
g = wait_job(adm, cj)
check(
    "cancelled state",
    g.get("status") == "cancelled",
    f"{g.get('status')} done={g.get('done')}",
)
r = c.post(f"/api/jobs/{cj}/retry", headers=H(adm))
check("retry cancelled -> queued", r.status_code == 200, r.status_code)
g2 = wait_job(adm, cj, timeout=60)
check(
    "retry after cancel completes",
    g2.get("status") == "completed",
    f"{g2.get('status')} done={g2.get('done')}/{g2.get('total')}",
)

print("== isolation + history + export ==")
uj = c.post(
    "/api/jobs/bulk",
    headers=H(usr),
    json={
        "kind": "edit",
        "target": "employees",
        "ids": ids[:1],
        "field": "Должность",
        "value": "Стажёр",
    },
).json()["job_id"]
wait_job(usr, uj)
r = c.get(f"/api/jobs/{uj}", headers=H(adm))
check("admin reads user job", r.status_code == 200, r.status_code)
r = c.get(f"/api/jobs/{jid}", headers=H(usr))
check("user чужой job -> 403", r.status_code == 403, r.status_code)
mine = c.get("/api/jobs/history", headers=H(usr)).json()["items"]
check(
    "user sees only own", all(x["username"] == "worker2" for x in mine), str(len(mine))
)
allh = c.get("/api/jobs/history", headers=H(adm)).json()["items"]
check("admin sees all", len(allh) >= len(mine) + 1, str(len(allh)))
r = c.get("/api/jobs/export.csv", headers=H(adm))
check(
    "export.csv",
    r.status_code == 200
    and "suot-bulk-jobs" in r.headers.get("content-disposition", ""),
    r.status_code,
)

print(f"\n=> {len(PASS)} OK, {len(FAIL)} FAIL")
if FAIL:
    print("FAILED:", FAIL)
    sys.exit(1)
