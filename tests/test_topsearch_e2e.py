"""Часть 22 (доп): постоянная строка глобального поиска сверху."""

import os, sys, subprocess, time, tempfile, socket

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TMPD = tempfile.mkdtemp(prefix="suot_s22_")
os.environ["SUOT_E2E_DB"] = os.path.join(TMPD, "e2e.db")


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


PORT = _free_port()
BASE = f"http://127.0.0.1:{PORT}"
srv = subprocess.Popen(
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

for _ in range(100):
    try:
        c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=0.5)
        c.request("GET", "/api/health")
        if c.getresponse().status == 200:
            break
    except Exception:
        time.sleep(0.2)

from playwright.sync_api import sync_playwright

PASS, FAIL = [], []


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(("  OK " if cond else "FAIL ") + name + (f" | {extra}" if extra else ""))


try:
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        page = b.new_page(viewport={"width": 1440, "height": 900})
        errs = []
        page.on("pageerror", lambda e: errs.append(str(e)))
        page.goto(BASE + "/", wait_until="domcontentloaded")
        page.wait_for_selector(".lang-cards", timeout=15000)
        page.get_by_role("button", name="Русский").click()
        page.wait_for_selector(".auth-card", timeout=8000)
        page.locator(".seg-btn").nth(1).click()
        page.get_by_placeholder("Иванов Иван Иванович").fill("Поискин Г")
        page.get_by_placeholder("например, ivanov").fill("search_user")
        page.get_by_placeholder("минимум 6 символов").fill("parol123")
        page.get_by_role("button", name="Создать аккаунт").click()
        page.wait_for_selector(".shell", timeout=10000)
        time.sleep(1.6)
        if page.locator(".tour-layer").count():
            page.keyboard.press("Escape")
            time.sleep(0.3)

        # Печатаем прямо в строку сверху — палитра открывается и ищет
        page.locator(".topsearch-input").click()
        page.locator(".topsearch-input").type("сотр", delay=40)
        time.sleep(0.6)
        pal_open = page.evaluate(
            "[...document.querySelectorAll('.palette-overlay')]"
            ".some(o => getComputedStyle(o).display !== 'none')"
        )
        check("ввод в строке открыл палитру", pal_open)
        q_sync = page.evaluate(
            "Alpine.$data(document.querySelector('.palette-overlay')).query"
        )
        check(f"запрос синхронизирован ({q_sync!r})", q_sync == "сотр")
        items = page.locator(".palette-item").count()
        check(f"результаты есть ({items})", items >= 1)

        # Enter — выполнить первый результат (Сотрудники)
        page.keyboard.press("Enter")
        time.sleep(0.8)
        tab_open = page.evaluate("(Alpine.store('tabs').active || {}).key")
        check(f"Enter открыл раздел ({tab_open})", tab_open == "employees")
        cleared = page.locator(".topsearch-input").input_value()
        check("строка очистилась после Enter", cleared == "")

        js_errs = [e for e in errs if "favicon" not in e.lower()]
        check("нет JS-ошибок", len(js_errs) == 0, ("; ".join(js_errs[:2]))[:140])
        b.close()

    print(f"\nTOPSEARCH E2E: {len(PASS)} OK, {len(FAIL)} FAIL")
    if FAIL:
        print("Провалены:", FAIL)
finally:
    srv.terminate()
