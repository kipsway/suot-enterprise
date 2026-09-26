"""E2E SUOT Next Блок 7: Query Engine + серверные виды.
Smart-фильтры пользовательских таблиц, сохранение вида через UI,
переживание wipe localStorage (доказательство сервера), применение,
удаление, RU, ноль JS-ошибок."""

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

TMPD = tempfile.mkdtemp(prefix="suot_views7_")
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
        ctx = browser.new_context(viewport={"width": 1400, "height": 900})
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
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

        # Custom-таблица с датой и статусом + 3 записи
        st, tbl = _api(
            "POST",
            "/api/custom/tables",
            TOKEN,
            {
                "label": "CT E2E",
                "icon": "database",
                "color": "#10B981",
                "columns": [
                    {"name": "Название", "type": "Текст"},
                    {"name": "Срок", "type": "Годен до"},
                    {"name": "Статус", "type": "Статус"},
                ],
            },
        )
        check("custom таблица", st == 201, str(st))
        ck = tbl.get("key", "")
        for name, due, status in (
            ("Старая", "01.01.2020", "Активен"),
            ("Готовая", "01.01.2020", "Готово"),
            ("Будущая", "01.01.2030", "Активен"),
        ):
            _api(
                "POST",
                f"/api/custom/records/{ck}",
                TOKEN,
                {"data": {"Название": name, "Срок": due, "Статус": status}},
            )

        # Открываем таблицу через сайдбар (перезагрузка: список своих таблиц
        # грузится при входе, а таблица создана уже после)
        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector(".shell", timeout=15000)
        time.sleep(1.0)
        page.locator(".nav-item", has_text="CT E2E").click()
        page.wait_for_selector("table.grid:visible", timeout=10000)
        time.sleep(1.0)
        n_all = page.locator("table.grid tbody tr").count()
        check("3 строки видно", n_all == 3, str(n_all))

        # Smart-фильтр custom-таблицы (чипы теперь видны и для custom).
        # Уточняем класс: есть ещё quick-filter чип с тем же текстом.
        page.locator(".smart-filter-chip", has_text="Просроченные").click()
        time.sleep(1.2)
        n_over = page.locator("table.grid tbody tr").count()
        check("просроченные -> 1", n_over == 1, str(n_over))
        page.locator(".smart-filter-chip", has_text="Просроченные").click()
        time.sleep(1.0)

        # Поиск "Старая" войдёт в сохраняемый вид (поиск активной вкладки)
        page.locator(".tabpane:visible .sb-input").fill("Старая")
        time.sleep(1.2)

        # Сохранение вида через UI (второй .preset-wrap — виды с глазом)
        page.locator(".preset-wrap").nth(1).locator("button.btn").first.click()
        page.wait_for_selector(".views-pop:visible", timeout=5000)
        page.locator(".views-pop .pr-name").fill("Мой вид")
        page.locator(".views-pop .btn.primary").click()
        time.sleep(0.8)
        check(
            "вид сохранён", page.locator(".pr-apply", has_text="Мой вид").count() >= 1
        )

        # Wipe localStorage views -> reload -> вид должен выжить (сервер)
        page.evaluate(
            "() => Object.keys(localStorage)"
            ".filter(k => k.startsWith('suot_views_'))"
            ".forEach(k => localStorage.removeItem(k))"
        )
        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector(".shell", timeout=15000)
        time.sleep(1.0)
        page.locator(".nav-item", has_text="CT E2E").click()
        page.wait_for_selector("table.grid:visible", timeout=10000)
        time.sleep(0.8)
        page.locator(".preset-wrap").nth(1).locator("button.btn").first.click()
        page.wait_for_selector(".views-pop:visible", timeout=5000)
        time.sleep(0.4)
        check(
            "вид пережил wipe localStorage",
            page.locator(".pr-apply", has_text="Мой вид").count() >= 1,
        )

        # Применение вида: в нём q="Старая" -> после apply одна строка
        page.locator(".pr-apply", has_text="Мой вид").click()
        time.sleep(1.2)
        n_applied = page.locator("table.grid tbody tr").count()
        check("применение вида (q работает)", n_applied == 1, str(n_applied))

        # Удаление вида через UI (попап закрылся при apply — открываем заново)
        page.locator(".preset-wrap").nth(1).locator("button.btn").first.click()
        page.wait_for_selector(".views-pop:visible", timeout=5000)
        time.sleep(0.3)
        page.locator(".pr-item", has_text="Мой вид").locator(".icon-btn.danger").click()
        time.sleep(0.8)
        check("вид удалён", page.locator(".pr-apply", has_text="Мой вид").count() == 0)
        # ... и на сервере тоже
        st, lst = _api("GET", f"/api/views?scope={ck}", TOKEN)
        check("сервер пуст", lst.get("items") == [], str(lst.get("items")))
        page.keyboard.press("Escape")

        js_err = [e for e in errors if "favicon" not in e.lower()]
        check("нет JS-ошибок", not js_err, "; ".join(js_err[:2]))
        browser.close()
finally:
    cleanup()

print(f"\n{len(PASS)} OK, {len(FAIL)} FAIL")
sys.exit(1 if FAIL else 0)
