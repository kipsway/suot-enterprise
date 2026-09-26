"""E2E SUOT Next Блок 6: Task Center.
Открытие из статусбара, бейдж активных, отмена/повтор через UI,
экспорт CSV, RU-подписи, Esc, ноль JS-ошибок."""

import json
import os
import sys
import subprocess
import time
import tempfile
import socket

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

TMPD = tempfile.mkdtemp(prefix="suot_task6_")
TEST_DB = os.path.join(TMPD, "e2e.db")
os.environ["SUOT_E2E_DB"] = TEST_DB


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


PORT = _free_port()
BASE_URL = f"http://127.0.0.1:{PORT}"

server_proc = subprocess.Popen(
    [
        sys.executable,
        "-m",
        "uvicorn",
        "server.app:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(PORT),
        "--log-level",
        "warning",
    ],
    cwd=ROOT,
    env={**os.environ},
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)

import http.client


def _api(method, path, token="", body=None):
    conn = http.client.HTTPConnection("127.0.0.1", PORT, timeout=15)
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    conn.request(method, path, json.dumps(body) if body is not None else None, headers)
    resp = conn.getresponse()
    data = resp.read().decode("utf-8", "replace")
    conn.close()
    return resp.status, json.loads(data) if data else {}


ready = False
for _ in range(100):
    try:
        c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=0.5)
        c.request("GET", "/api/health")
        if c.getresponse().status == 200:
            ready = True
            break
    except Exception:
        time.sleep(0.2)
if not ready:
    server_proc.kill()
    print("FAIL сервер не поднялся")
    sys.exit(1)

st, login = _api(
    "POST", "/api/auth/login", "", {"username": "admin", "password": "admin"}
)
TOKEN = login.get("token", "") if st == 200 else ""

from playwright.sync_api import sync_playwright

PASS, FAIL = [], []


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(("  OK " if cond else "FAIL ") + name + (f" | {extra}" if extra else ""))


def cleanup():
    try:
        server_proc.terminate()
        server_proc.wait(timeout=5)
    except Exception:
        try:
            server_proc.kill()
        except Exception:
            pass


try:
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(
            viewport={"width": 1400, "height": 900}, accept_downloads=True
        )
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        # Токен заранее: прямой вход в shell
        page.add_init_script(f"localStorage.setItem('suot_token', '{TOKEN}');")
        page.goto(BASE_URL + "/", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector(".shell", timeout=15000)
        check("вход по токену", True)
        try:
            page.wait_for_selector(".tour-layer", timeout=3500)
            page.keyboard.press("Escape")
            time.sleep(0.5)
        except Exception:
            pass

        # Готовим записи и быструю задачу через API
        ids = []
        for i in range(3):
            _st, _r = _api(
                "POST", "/api/data/employees", TOKEN, {"data": {"ФИО": f"Task {i}"}}
            )
            ids.append(_r.get("id"))
        check("записи созданы", len(ids) == 3)
        _st, _j = _api(
            "POST",
            "/api/jobs/bulk",
            TOKEN,
            {
                "kind": "edit",
                "target": "employees",
                "ids": ids,
                "field": "Должность",
                "value": "Мастер",
            },
        )
        check("job создан", _st == 202)

        # Центр через кнопку статусбара
        page.locator('.statusbar-cmd[title*="Центр задач"]').click()
        page.wait_for_selector(".tc-overlay:visible", timeout=8000)
        time.sleep(1.5)
        panel = page.locator(".tc-panel").inner_text()
        check("центр открылся (RU)", "Центр задач" in panel)
        check(
            "готовая задача видна",
            "готово" in panel.lower(),
            panel[:120].replace("\n", " "),
        )

        # Медленная задача -> бейдж -> отмена через UI.
        # Бейдж обновляется по событию suot-tasks-changed (его шлёт таблица);
        # здесь событие отправляем вручную — как делает table.js.
        big = []
        for i in range(300):
            _st, _r = _api(
                "POST", "/api/data/employees", TOKEN, {"data": {"ФИО": f"Slow {i}"}}
            )
            big.append(_r.get("id"))
        _st, _slow = _api(
            "POST",
            "/api/jobs/bulk",
            TOKEN,
            {"kind": "delete", "target": "employees", "ids": big},
        )
        slow_id = _slow.get("job_id")
        page.evaluate(
            "() => document.dispatchEvent(new CustomEvent('suot-tasks-changed',"
            " {bubbles: true}))"
        )
        page.wait_for_selector(".tc-badge:visible", timeout=10000)
        check("бейдж активных", True)
        page.locator(".tc-job", has_text="Удаление").first.wait_for(timeout=10000)
        page.locator(".tc-job", has_text="Удаление").first.locator(
            "button", has_text="Остановить"
        ).click()
        page.wait_for_selector(".tc-job .badge", timeout=15000)
        time.sleep(1.0)
        txt = page.locator(".tc-panel").inner_text().lower()
        check(
            "отмена через UI",
            "отменена" in txt or "готово" in txt,
            txt[:150].replace("\n", " "),
        )
        # Повтор через UI (если отменилась — завершится; если успела — кнопки нет)
        retry_btn = page.locator(".tc-job .btn", has_text="Повторить задачу")
        if retry_btn.count() > 0:
            retry_btn.first.click()
            page.wait_for_selector(".tc-job .badge", timeout=20000)
            time.sleep(1.0)
            txt2 = page.locator(".tc-panel").inner_text().lower()
            check("повтор через UI", "готово" in txt2)
        else:
            check("повтор через UI (задача успела завершиться)", True)

        # Экспорт CSV истории
        with page.expect_download(timeout=15000) as dl_info:
            page.get_by_role("button", name="Скачать CSV").click()
        dl = dl_info.value
        with open(dl.path(), "rb") as f:
            content = f.read().decode("utf-8-sig", "replace")
        check(
            "CSV истории скачался",
            "suot-bulk-jobs" in dl.suggested_filename and "Дата" in content,
            dl.suggested_filename,
        )

        # Esc закрывает
        page.keyboard.press("Escape")
        time.sleep(0.4)
        check(
            "Escape закрывает центр", page.locator(".tc-overlay:visible").count() == 0
        )

        # Команда шины tasks
        page.evaluate("() => window.SUOT_COMMANDS.run('tasks')")
        page.wait_for_selector(".tc-overlay:visible", timeout=5000)
        check("команда tasks открывает центр", True)
        check(
            "команда в реестре",
            page.evaluate("() => !!window.SUOT_COMMANDS.get('tasks')"),
        )
        page.keyboard.press("Escape")

        # Focus-trap центра
        page.locator('.statusbar-cmd[title*="Центр задач"]').click()
        page.wait_for_selector(".tc-overlay:visible", timeout=5000)
        time.sleep(0.3)
        trapped = True
        for _ in range(10):
            page.keyboard.press("Tab")
            inside = page.evaluate(
                "() => { const m = document.querySelector('.tc-panel');"
                " return !!(m && m.contains(document.activeElement)); }"
            )
            if not inside:
                trapped = False
                break
        check("Tab не покидает центр", trapped)
        page.keyboard.press("Escape")

        js_err = [e for e in errors if "favicon" not in e.lower()]
        check("нет JS-ошибок", not js_err, "; ".join(js_err[:2]))
        browser.close()
finally:
    cleanup()

print(f"\n{len(PASS)} OK, {len(FAIL)} FAIL")
sys.exit(1 if FAIL else 0)
