"""Часть 27: история AI-диалогов (threads + messages, переименование, удаление)."""

import os
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

p = os.path.join(tempfile.gettempdir(), "suot_part27.db")
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
        "/api/auth/register", json={"username": "part27_user", "password": "parol123"}
    )
    HB = {"Authorization": "Bearer " + r.json()["token"]}

    # Пустой список диалогов
    rl = client.get("/api/ai/threads", headers=HB)
    check("треды: пустой список", rl.json()["items"] == [])

    # Создание
    rc = client.post("/api/ai/threads", headers=HB, json={"title": "Стаж работников"})
    tid = rc.json()["id"]
    check("тред: создание", rc.status_code == 200 and tid > 0)

    # Создание с пустым заголовком → дефолт
    rc2 = client.post("/api/ai/threads", headers=HB, json={})
    tid2 = rc2.json()["id"]
    lst = client.get("/api/ai/threads", headers=HB).json()["items"]
    titles = {t["id"]: t["title"] for t in lst}
    check("тред: дефолтный заголовок", titles.get(tid2) == "Новый диалог")

    # Переименование
    rr = client.patch(
        f"/api/ai/threads/{tid}", headers=HB, json={"title": "Переименован"}
    )
    check("тред: переименование", rr.status_code == 200)
    lst = client.get("/api/ai/threads", headers=HB).json()["items"]
    titles = {t["id"]: t["title"] for t in lst}
    check("тред: новое имя сохранено", titles.get(tid) == "Переименован")

    # Сообщения: пустые
    rm = client.get(f"/api/ai/threads/{tid}/messages", headers=HB)
    check("тред: сообщений нет", rm.json()["items"] == [])

    # Сохранение сообщений через чат (LLM недоступен — сохраняется история от клиента)
    resp = client.post(
        "/api/ai/chat",
        headers=HB,
        json={
            "thread_id": tid,
            "table": "employees",
            "messages": [
                {"role": "user", "content": "Сколько всего сотрудников?"},
                {"role": "assistant", "content": "В таблице employees 5 записей."},
            ],
        },
    )
    # потоковый ответ может вернуть ошибку (нет LLM) — но история должна сохраниться
    rm = client.get(f"/api/ai/threads/{tid}/messages", headers=HB).json()["items"]
    roles = [m["role"] for m in rm]
    check(
        "чат: сообщения сохранены",
        len(rm) >= 2 and "user" in roles and "assistant" in roles,
        f"roles={roles}",
    )

    # Сообщение приходит в списке тредов
    lst = client.get("/api/ai/threads", headers=HB).json()["items"]
    tinfo = next((t for t in lst if t["id"] == tid), None)
    check(
        "тред: preview последнего сообщения",
        tinfo and tinfo.get("message_count", 0) >= 2,
    )

    # Удаление (каскадно с сообщениями)
    rd = client.delete(f"/api/ai/threads/{tid}", headers=HB)
    check("тред: удаление", rd.status_code == 200)
    rm = client.get(f"/api/ai/threads/{tid}/messages", headers=HB).json()["items"]
    check("тред: сообщения удалены каскадом", rm == [])

    # Чужая запись: не-владелец не может удалить/переименовать (отрицательный кейс через отсутствие id)
    r2 = client.post(
        "/api/auth/register", json={"username": "part27_other", "password": "parol123"}
    )
    HB2 = {"Authorization": "Bearer " + r2.json()["token"]}
    rc3 = client.post("/api/ai/threads", headers=HB2, json={"title": "Чужой"})
    tid3 = rc3.json()["id"]
    rdel = client.delete(f"/api/ai/threads/{tid3}", headers=HB)
    check("тред: чужой нельзя удалить → 404", rdel.status_code == 404)
    rren = client.patch(f"/api/ai/threads/{tid3}", headers=HB, json={"title": "Хак"})
    check("тред: чужой нельзя переименовать → 404", rren.status_code == 404)

    # Персистентность: отдельное подключение (симуляция перезапуска) видит треды и сообщения
    import sqlite3

    created = client.post(
        "/api/ai/threads", headers=HB, json={"title": "После рестарта"}
    ).json()
    tid4 = created["id"]
    client.post(
        "/api/ai/chat",
        headers=HB,
        json={
            "thread_id": tid4,
            "messages": [
                {"role": "user", "content": "привет"},
                {"role": "assistant", "content": "здравствуй"},
            ],
        },
    )
    conn2 = sqlite3.connect(p)
    conn2.row_factory = sqlite3.Row
    urow = conn2.execute("SELECT id FROM users WHERE username='part27_user'").fetchone()
    uid_me = int(urow["id"]) if urow else -1
    th = conn2.execute(
        "SELECT * FROM chat_threads WHERE user_id=? ORDER BY id",
        (uid_me,),
    ).fetchall()
    msgs = conn2.execute(
        "SELECT * FROM chat_messages WHERE thread_id=? ORDER BY id",
        (tid4,),
    ).fetchall()
    ok_persist = any(t["id"] == tid4 for t in th) and len(msgs) >= 2
    check("диалог сохранён после рестарта приложения", ok_persist)
    conn2.close()

    # ── Ping провайдера ──
    rp = client.post("/api/ai/ping", headers=HB)
    body = rp.json()
    check(
        "ping: ответ содержит ok, ms, provider",
        rp.status_code == 200
        and "ok" in body
        and "ms" in body
        and body["provider"] == "ollama",
        f"body={body}",
    )
    check(
        "ping: провайдер недоступен → ok=false",
        body["ok"] is False and len(body.get("error", "")) > 0,
    )

    # ── Batch-операции (агент preview + execute) ──
    # Создадим записи для пакетной обработки
    for i in range(3):
        client.post(
            "/api/data/violations",
            headers=HB,
            json={
                "data": {
                    "Описание": f"Пакетная проверка #{i + 1}",
                    "Статус": "На устранении",
                }
            },
        )
    # Пакетное обновление через execute
    rc_batch = client.post(
        "/api/ai/agent/execute",
        headers=HB,
        json={
            "action": "batch_update",
            "params": {
                "table": "violations",
                "query": "Пакетная проверка",
                "filter": {},
                "data": {"Статус": "Устранено"},
            },
        },
    )
    check(
        "batch_update: выполнено",
        rc_batch.status_code == 200 and rc_batch.json().get("count", 0) >= 3,
        f"body={rc_batch.json()}",
    )
    # Проверка, что статусы обновились
    rv = client.get(
        "/api/data/violations",
        headers=HB,
        params={"q": "Пакетная проверка", "page_size": 50},
    )
    items = rv.json().get("items", [])
    statuses = [r["data"].get("Статус", "") for r in items]
    all_updated = all(s == "Устранено" for s in statuses) if statuses else False
    check(
        "batch_update: статусы обновились",
        all_updated and len(statuses) >= 3,
        f"n={len(statuses)}",
    )

    # Пакетное удаление через execute
    for i in range(2):
        client.post(
            "/api/data/violations",
            headers=HB,
            json={"data": {"Описание": "На удаление", "Статус": "Удалить"}},
        )
    rc_del = client.post(
        "/api/ai/agent/execute",
        headers=HB,
        json={
            "action": "batch_delete",
            "params": {
                "table": "violations",
                "query": "На удаление",
                "filter": {},
            },
        },
    )
    check(
        "batch_delete: выполнено",
        rc_del.status_code == 200 and rc_del.json().get("count", 0) >= 2,
        f"body={rc_del.json()}",
    )

    # Неверная таблица → 400
    rc_bad = client.post(
        "/api/ai/agent/execute",
        headers=HB,
        json={"action": "batch_delete", "params": {"table": "no_table", "query": ""}},
    )
    check("batch_delete: неверная таблица → 400", rc_bad.status_code == 400)

for s in ("", "-wal", "-shm"):
    try:
        os.remove(p + s)
    except OSError:
        pass

print(f"\nИтого Ч27-бэк: {len(PASS)} OK, {len(FAIL)} FAIL")
if FAIL:
    print("Провалены:", FAIL)
    sys.exit(1)
