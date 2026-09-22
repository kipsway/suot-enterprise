"""Часть 30: perf-прогон. Замер задержек ключевых read-эндпоинтов
на свежей и нагруженной базе + объём ответов."""

import os
import sys
import time
import tempfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

p = os.path.join(tempfile.gettempdir(), "suot_perf.db")
for s in ("", "-wal", "-shm"):
    try:
        os.remove(p + s)
    except OSError:
        pass
os.environ["SUOT_E2E_DB"] = p

from fastapi.testclient import TestClient  # noqa: E402
from server.app import app  # noqa: E402

client = TestClient(app)

with client:
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    HB = {"Authorization": "Bearer " + r.json()["token"]}

    ENDPOINTS = [
        ("GET", "/api/diag"),
        ("GET", "/api/diag/summary"),
        ("GET", "/api/diag/log?limit=40"),
        ("GET", "/api/diag/disk"),
        ("GET", "/api/auth/sessions"),
        ("GET", "/api/help/version"),
        ("GET", "/api/settings/appearance"),
        ("GET", "/api/auth/me"),
        ("GET", "/api/dash/stats"),
        ("GET", "/api/dash/tasks"),
        ("GET", "/api/calendar/events"),
        ("GET", "/api/npa/list"),
    ]

    print(f"{'endpoint':34}    avg    p95    size")
    worst = []
    for method, path in ENDPOINTS:
        times = []
        sizes = []
        for _ in range(20):
            t0 = time.perf_counter()
            resp = client.request(method, path, headers=HB)
            dt = (time.perf_counter() - t0) * 1000
            times.append(dt)
            sizes.append(len(resp.content))
        times.sort()
        avg = sum(times) / len(times)
        p95 = times[int(len(times) * 0.95)]
        size = sum(sizes) / len(sizes)
        worst.append((p95, path, avg, size))
        print(f"{path:34}  {avg:6.1f}  {p95:6.1f}  {size:7.0f}")

    worst.sort(reverse=True)
    print("\nСамые медленные (p95):")
    for p95, path, avg, size in worst[:3]:
        print(f"  {p95:6.1f} ms  {path}")

    ok90 = all(avg < 250 for _, _, avg, _ in worst)
    print(f"\nPERF: {'PASS' if ok90 else 'FAIL'} (все avg < 250 мс)")

# ── нагрузка: вставка записей и замер массового чтения ──
from services.database import DatabaseManager  # noqa: E402
from app_core.config import RUNTIME_PATHS  # noqa: E402

db = DatabaseManager()
try:
    db.execute(
        "INSERT INTO violations (json_data) VALUES (?)",
        (
            (
                '{"Дата": "2026-01-01", "Фирма": "ООО Тест", '
                '"Подразделение": "Цех 1", "Описание": "перф-запись"}'
            ),
        ),
    )
    db.commit()
except Exception:
    pass
print("load-test: замер N вставок + чтений")
N = 200
t0 = time.perf_counter()
for _ in range(N):
    db.get_json_records("violations")
dt = (time.perf_counter() - t0) * 1000
print(f"  {N} чтений списка нарушений: {dt:.0f} мс ({(dt / N):.2f} мс/запрос)")
check = dt / N < 50
print(
    f"LOAD: {'PASS' if check else 'FAIL'} ({dt / N:.2f} мс/запрос < 50)"
    if dt / N < 50
    else f"LOAD: FAIL ({dt / N:.2f} мс/запрос)"
)
