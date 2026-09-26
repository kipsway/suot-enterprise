"""E2E SUOT Next Dashboard v4: глубокие ссылки готовности/фокуса/KPI
с реальными серверными фильтрами, скролл к виджетам, RU, ноль JS-ошибок."""

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

TMPD = tempfile.mkdtemp(prefix="suot_dash4_")
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
        ctx = browser.new_context(viewport={"width": 1500, "height": 900})
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

        # Детерминированные записи: 1 просрочка + 1 норма
        _api(
            "POST",
            "/api/data/employees",
            TOKEN,
            {"data": {"ФИО": "Просроч П", "Дата медосмотра": "01.01.2020"}},
        )
        _api(
            "POST",
            "/api/data/employees",
            TOKEN,
            {"data": {"ФИО": "Норма Н", "Дата медосмотра": "01.01.2030"}},
        )

        # Дашборд виден (welcome)
        page.locator(".nav-item", has_text="Дашборд").first.click()
        page.wait_for_selector(".dash-widgets", timeout=10000)
        time.sleep(1.0)
        check("дашборд открыт", True)

        # Readiness: строка просрочек -> таблица с применённым фильтром
        page.locator(".readiness-check", has_text="Просроченные сроки").click()
        page.wait_for_selector("table.grid:visible", timeout=10000)
        time.sleep(1.5)
        chip_on = page.evaluate(
            "() => { const els = [...document.querySelectorAll("
            "'.smart-filter-chip')]; const b = els.find("
            "e => e.textContent.includes('Просроченные'));"
            " return b ? b.className.includes('on') : 'NOCHIP'; }"
        )
        check("фильтр Просроченные применён", chip_on is True, str(chip_on))
        rows = page.locator("table.grid tbody tr").count()
        names = page.locator("table.grid tbody").inner_text()
        check(
            "видна только просрочка", rows == 1 and "Просроч" in names, f"rows={rows}"
        )

        # Назад на дашборд: возврат на welcome перезагружает stats
        # (onTabActive), фокус-дня -> training + overdue.
        page.locator(".nav-item", has_text="Дашборд").first.click()
        page.wait_for_selector(".dash-widgets", timeout=10000)
        page.wait_for_selector(".readiness-check", timeout=10000)
        page.locator(".readiness-check", has_text="Просроченные сроки").wait_for(
            timeout=10000
        )
        page.locator(".focus-item", has_text="Закрыть просрочки").wait_for(
            timeout=10000
        )
        time.sleep(0.5)
        print(
            "   FOCUS:",
            page.evaluate(
                "() => [...document.querySelectorAll('.focus-item')].map("
                "e => e.innerText.slice(0, 45))"
            ),
        )
        # Тур мог всплыть заново и перехватывать клики — закрываем
        if page.locator(".tour-layer").count():
            page.keyboard.press("Escape")
            time.sleep(0.5)
        page.evaluate(
            "() => { const t = [...document.querySelectorAll('.focus-item')]"
            ".find(e => e.textContent.includes('Закрыть просрочки'));"
            " if (t) t.scrollIntoView({block: 'center'}); }"
        )
        time.sleep(0.6)
        page.locator(".focus-item", has_text="Закрыть просрочки").click()
        page.wait_for_selector("table.grid:visible", timeout=10000)
        time.sleep(1.5)
        tab = page.evaluate("() => (Alpine.store('tabs').active || {}).key")
        check("фокус ведёт в таблицу", tab == "employees", tab)

        # Readiness: задачи -> скролл к виджету
        page.locator(".nav-item", has_text="Дашборд").first.click()
        page.wait_for_selector(".dash-widgets", timeout=10000)
        time.sleep(0.8)
        page.locator(".readiness-check", has_text="Задачи на сегодня").click()
        time.sleep(1.0)
        in_view = page.evaluate("""() => {
            const el = document.querySelector('[data-wid="tasks"]');
            if (!el) return 'NOWID';
            const r = el.getBoundingClientRect();
            return r.top > 0 && r.top < window.innerHeight;
        }""")
        check("скролл к виджету задач", in_view is True, str(in_view))

        # KPI просрочки -> фильтр
        page.locator(".dash-kpi", has_text="Просрочки").click()
        page.wait_for_selector("table.grid:visible", timeout=10000)
        time.sleep(1.5)
        chip2 = page.evaluate(
            "() => { const els = [...document.querySelectorAll("
            "'.smart-filter-chip')]; const b = els.find("
            "e => e.textContent.includes('Просроченные'));"
            " return b ? b.className.includes('on') : 'NOCHIP'; }"
        )
        check("KPI ведёт с фильтром", chip2 is True, str(chip2))

        js_err = [e for e in errors if "favicon" not in e.lower()]
        check("нет JS-ошибок", not js_err, "; ".join(js_err[:2]))
        browser.close()
finally:
    cleanup()

print(f"\n{len(PASS)} OK, {len(FAIL)} FAIL")
sys.exit(1 if FAIL else 0)
