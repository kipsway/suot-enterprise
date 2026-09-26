"""E2E SUOT Next Блок 9 (миграция legacy UI): workspace-first адаптер.
Registry-маппинг видов, legacy табличные маршруты без изменений,
алиасы, fallback неизвестных ключей, ноль JS-ошибок."""

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

TMPD = tempfile.mkdtemp(prefix="suot_migr_")
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
    try:
        return resp.status, json.loads(data) if data else {}
    except Exception:
        return resp.status, {}


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


def _active(page):
    return page.evaluate(
        "() => { const t = Alpine.store('tabs'); const a = t.active || {};"
        " return {type: a.type || '', key: a.key || ''}; }"
    )


def _via_registry(page, vid):
    page.evaluate(
        "() => document.dispatchEvent(new CustomEvent('suot-next-open',"
        " {detail: {id: '" + vid + "'}}))"
    )
    time.sleep(0.9)
    return _active(page)


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

        # Registry-маппинг: id -> ожидаемый таб
        mapping = {
            "overview": ("welcome", ""),
            "people": ("table", "employees"),
            "documents": ("documents", ""),
            "journal": ("journal", ""),
            "ai": ("ai", ""),
            "calendar": ("calendar", ""),
            "analytics": ("welcome", ""),
            "all": ("all", "all"),
        }
        bad = []
        for vid, want in mapping.items():
            got = _via_registry(page, vid)
            if (got["type"], got["key"]) != want:
                bad.append(f"{vid}={got}")
        check("registry-маппинг", not bad, "; ".join(bad[:4]))

        # Legacy: tabs.open таблиц — те же табы, таблицы рендерятся
        legacy_ok = True
        for key in ("employees", "protocols", "capa", "print_editor"):
            page.evaluate(f"(k) => Alpine.store('tabs').open(k)", key)
            time.sleep(0.7)
            a = _active(page)
            if a["type"] != "table" or a["key"] != key:
                legacy_ok = False
        check("legacy таблицы напрямую", legacy_ok)
        page.evaluate("(k) => Alpine.store('tabs').open(k)", "employees")
        time.sleep(0.8)
        check(
            "таблица рендерится",
            page.locator(".tabpane:visible table.grid").count() >= 1,
        )

        # Алиасы через адаптер
        page.evaluate("() => Alpine.store('tabs').open('docs')")
        time.sleep(0.7)
        check("алиас docs → центр", _active(page)["type"] == "documents")
        page.evaluate("() => Alpine.store('tabs').open('home')")
        time.sleep(0.7)
        check("алиас home → welcome", _active(page)["type"] == "welcome")

        # openKey: точное совпадение и miss
        r = page.evaluate("""() => { const n = Alpine.store('next');
            return {hit: n.openKey('npa'), miss: n.openKey('no_such_view')}; }""")
        time.sleep(0.7)
        check("openKey hit/miss", r["hit"] is True and r["miss"] is False, str(r))
        check("openKey открыл НПА", _active(page)["type"] == "npa")

        # Сайдбар идёт через тот же результат (клик Документы → центр)
        page.locator(".nav-item", has_text="Документы").first.click()
        time.sleep(0.9)
        check("сайдбар → центр", _active(page)["type"] == "documents")

        js_err = [e for e in errors if "favicon" not in e.lower()]
        check("нет JS-ошибок", not js_err, "; ".join(js_err[:2]))
        browser.close()
finally:
    cleanup()

print(f"\n{len(PASS)} OK, {len(FAIL)} FAIL")
sys.exit(1 if FAIL else 0)
