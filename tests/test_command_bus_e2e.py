"""E2E SUOT Next Блок 5: Command Bus + keyboard-first.
Реестр команд (уникальные id, RU/EN, иконки), выполнение (тема, switcher,
help, logout), секция Команды в переключателе, focus-trap панелей,
Alt+2 гвард при открытой модалке, F5/Ctrl+F оживлены. Ноль JS-ошибок."""

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

TMPD = tempfile.mkdtemp(prefix="suot_cmd5_")
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


def _api(path, body):
    conn = http.client.HTTPConnection("127.0.0.1", PORT, timeout=8)
    conn.request("POST", path, json.dumps(body), {"Content-Type": "application/json"})
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

st, login = _api("/api/auth/login", {"username": "admin", "password": "admin"})
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


def in_el(page, sel):
    return page.evaluate(
        "() => { const m = document.querySelector('" + sel + "');"
        " return !!(m && m.contains(document.activeElement)); }"
    )


try:
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1400, "height": 900})
        ctx.add_init_script(f"localStorage.setItem('suot_token', '{TOKEN}');")
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(BASE_URL + "/", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector(".shell", timeout=15000)
        check("вход по токену", True)
        try:
            page.wait_for_selector(".tour-layer", timeout=3500)
            page.keyboard.press("Escape")
            time.sleep(0.5)
        except Exception:
            pass

        # Реестр команд
        reg = page.evaluate("""() => {
            const b = window.SUOT_COMMANDS;
            if (!b) return null;
            const all = b.all();
            return {
                n: all.length,
                ids: all.map(c => c.id),
                bad: all.filter(c => !c.id || !c.ru || !c.en || !c.icon
                    || !c.group || typeof c.run !== 'function').map(c => c.id),
                enTheme: b.labelOf(b.get('theme'), 'en'),
                shortcut: b.shortcutFor(b.get('theme')),
                unknown: b.run('no-such-command'),
            };
        }""")
        check("шина команд существует", reg is not None)
        check("команд >= 7", reg["n"] >= 7, str(reg["n"]))
        check("все команды полные", reg["bad"] == [], str(reg["bad"]))
        check("id уникальны", len(set(reg["ids"])) == len(reg["ids"]))
        check("EN-подпись", reg["enTheme"] == "Cycle theme", reg["enTheme"])
        check("подсказка шортката", reg["shortcut"] == "Ctrl+Shift+T", reg["shortcut"])
        check("неизвестная команда -> false", reg["unknown"] is False)

        # Выполнение: тема переключается
        before = page.evaluate("() => document.body.getAttribute('data-theme')")
        page.evaluate("() => window.SUOT_COMMANDS.run('theme')")
        time.sleep(0.8)
        after = page.evaluate("() => document.body.getAttribute('data-theme')")
        check("команда theme переключает тему", before != after, f"{before}->{after}")

        # Выполнение: help открывает справку
        ret = page.evaluate("() => window.SUOT_COMMANDS.run('help')")
        time.sleep(0.8)
        help_open = page.evaluate(
            "() => [...document.querySelectorAll("
            "'.help-modal, .help-center, .sc-modal')].some("
            "(m) => !!(m && m.getClientRects().length))"
        )
        dbg = page.evaluate(
            """() => {
                const el = document.querySelector('[x-data^="helpCenter"]');
                let open = 'NO EL';
                try { open = el ? Alpine.$data(el).open : 'NO EL'; }
                catch (e) { open = 'ERR'; }
                return {
                    open,
                    overlays: [...document.querySelectorAll('.sc-overlay')].map(
                        o => !!o.getClientRects().length),
                };
            }"""
        )
        check("команда help открывает справку", help_open, f"run={ret} {dbg}")
        page.keyboard.press("Escape")
        time.sleep(0.4)

        # Секция Команды в переключателе
        page.get_by_role("button", name="Рабочая область").click()
        page.wait_for_selector(".ws-overlay:visible", timeout=5000)
        cmds = page.locator(".ws-item", has_text="Сменить тему").count()
        check("команды в панели", cmds >= 1, str(cmds))
        page.locator(".ws-search").fill("справка")
        time.sleep(0.4)
        check(
            "поиск находит команду",
            page.locator(".ws-item:visible", has_text="Справка").count() >= 1,
        )
        page.locator(".ws-search").fill("")
        time.sleep(0.3)
        page.locator(".ws-item", has_text="Сменить тему").first.click()
        time.sleep(0.8)
        after2 = page.evaluate("() => document.body.getAttribute('data-theme')")
        check("команда из панели работает", after2 != after, f"{after}->{after2}")
        check(
            "панель закрылась после команды",
            page.locator(".ws-overlay:visible").count() == 0,
        )

        # Focus-trap switcher
        page.get_by_role("button", name="Рабочая область").click()
        page.wait_for_selector(".ws-overlay:visible", timeout=5000)
        time.sleep(0.4)
        trapped = True
        for _ in range(12):
            page.keyboard.press("Tab")
            if not in_el(page, ".ws-panel"):
                trapped = False
                break
        check("Tab не покидает switcher", trapped)
        page.keyboard.press("Escape")
        time.sleep(0.3)

        # Focus-trap dossier
        conn = http.client.HTTPConnection("127.0.0.1", PORT, timeout=8)
        conn.request(
            "POST",
            "/api/data/employees",
            json.dumps({"data": {"ФИО": "Trap Test"}}),
            {"Content-Type": "application/json", "Authorization": "Bearer " + TOKEN},
        )
        r = conn.getresponse()
        rid = json.loads(r.read().decode("utf-8", "replace")).get("id")
        conn.close()
        page.evaluate(
            "() => document.dispatchEvent(new CustomEvent('suot-detail-open',"
            + " {bubbles: true, detail: {table: 'employees', id: "
            + str(rid)
            + "}}))"
        )
        page.wait_for_selector(".dt-overlay:visible", timeout=8000)
        time.sleep(0.4)
        trapped2 = True
        for _ in range(12):
            page.keyboard.press("Tab")
            if not in_el(page, ".dt-panel"):
                trapped2 = False
                break
        check("Tab не покидает dossier", trapped2)
        page.keyboard.press("Escape")
        time.sleep(0.3)

        # Alt+2 гвард при открытой модалке
        page.evaluate(
            "() => { const st = Alpine.store('next');"
            " st.pinned = ['overview', 'people']; st.persist(); }"
        )
        page.locator(".nav-item", has_text="Сотрудники").first.click()
        page.wait_for_selector("table.grid:visible", timeout=8000)
        page.locator(
            "table.grid tbody tr td.col-actions .icon-btn:not(.danger)"
        ).first.click()
        page.wait_for_selector(".modal:visible", timeout=8000)
        before_nav = page.evaluate("() => Alpine.store('next').activeId")
        page.keyboard.press("Alt+2")
        time.sleep(0.6)
        after_nav = page.evaluate("() => Alpine.store('next').activeId")
        check(
            "Alt+2 заблокирован в модалке",
            before_nav == after_nav,
            f"{before_nav}->{after_nav}",
        )
        page.keyboard.press("Escape")
        time.sleep(0.3)
        page.keyboard.press("Alt+2")
        time.sleep(0.8)
        after_nav2 = page.evaluate("() => Alpine.store('next').activeId")
        check("Alt+2 работает без модалки", after_nav2 == "people", after_nav2)

        # Выход через шину — последним (завершает сессию)
        page.evaluate("() => window.SUOT_COMMANDS.run('logout')")
        page.wait_for_selector(".auth-card", timeout=8000)
        check("команда logout выводит на вход", True)

        js_err = [e for e in errors if "favicon" not in e.lower()]
        check("нет JS-ошибок", not js_err, "; ".join(js_err[:2]))
        browser.close()
finally:
    cleanup()

print(f"\n{len(PASS)} OK, {len(FAIL)} FAIL")
sys.exit(1 if FAIL else 0)
