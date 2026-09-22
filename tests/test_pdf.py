"""Часть 13: тесты PDF-генерации и пакетной печати."""

import io
import os
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

p = os.path.join(tempfile.gettempdir(), "suot_pdf_t.db")
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
        "/api/auth/register", json={"username": "pdf_user", "password": "parol123"}
    )
    HB = {"Authorization": "Bearer " + r.json()["token"]}

    # Edge доступен?
    re_ = client.get("/api/print/edge_available", headers=HB)
    edge_ok = re_.json().get("available", False)
    check(f"Edge headless доступен ({edge_ok})", edge_ok)

    if not edge_ok:
        print("  SKIP: Edge не найден, PDF-тесты пропущены")
    else:
        # Одиночный PDF
        rp = client.post(
            "/api/print/pdf",
            headers=HB,
            json={
                "html_content": "<h1>Тестовый документ</h1>"
                "<p>Содержимое для проверки.</p>",
                "page_size": "A4",
                "orientation": "portrait",
            },
        )
        check(
            "одиночный PDF",
            rp.status_code == 200 and rp.content[:4] == b"%PDF",
            str(len(rp.content)),
        )

        # С водяным знаком (предложение 3)
        rp2 = client.post(
            "/api/print/pdf",
            headers=HB,
            json={
                "html_content": "<p>С водяным знаком</p>",
                "watermark_text": "ЧЕРНОВИК",
            },
        )
        check(
            "PDF с водяным знаком",
            rp2.status_code == 200 and rp2.content[:4] == b"%PDF",
        )

        # Пакетная печать (предложение 1)
        for i in range(3):
            client.post(
                "/api/data/employees",
                headers=HB,
                json={"data": {"ФИО": f"Печатов {i + 1}"}},
            )
        rows = client.get("/api/data/employees?page_size=10", headers=HB).json()[
            "items"
        ]
        ids = [r["id"] for r in rows]
        rb = client.post(
            "/api/print/batch_pdf",
            headers=HB,
            json={
                "template_html": "<h1>{ФИО}</h1><p>Документ</p>",
                "table": "employees",
                "record_ids": ids,
                "merge": True,
            },
        )
        check(
            f"пакетная печать: {len(ids)} записей merged",
            rb.status_code == 200 and rb.content[:4] == b"%PDF",
            str(len(rb.content)),
        )

        # Пакетная печать: отдельные файлы (ZIP)
        rb2 = client.post(
            "/api/print/batch_pdf",
            headers=HB,
            json={
                "template_html": "<h1>{ФИО}</h1>",
                "table": "employees",
                "record_ids": ids,
                "merge": False,
            },
        )
        check(
            "пакетная печать ZIP", rb2.status_code == 200 and rb2.content[:2] == b"PK"
        )

        # Водяной знак в пакетной печати
        rb3 = client.post(
            "/api/print/batch_pdf",
            headers=HB,
            json={
                "template_html": "<p>{ФИО}</p>",
                "table": "employees",
                "record_ids": ids,
                "watermark_text": "КОПИЯ",
                "merge": True,
            },
        )
        check("пакетный PDF с водяным знаком", rb3.status_code == 200)

for s in ("", "-wal", "-shm"):
    try:
        os.remove(p + s)
    except OSError:
        pass

print(f"\nИТОГО: {len(PASS)} OK, {len(FAIL)} FAIL")
if FAIL:
    print("Провалены:", FAIL)
    sys.exit(1)
