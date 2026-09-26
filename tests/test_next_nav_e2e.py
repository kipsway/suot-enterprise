"""E2E SUOT Next Блок 1: Navigation Registry + Workspace Shell.
Реестр, пины/недавние (persist + cap), Alt+1..9, панель-переключатель,
RU/EN-подписи, регрессия сайдбара, ноль JS-ошибок."""

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

TMPD = tempfile.mkdtemp(prefix="suot_next1_")
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


def _api(path, body):
    conn = http.client.HTTPConnection("127.0.0.1", PORT, timeout=8)
    conn.request("POST", path, json.dumps(body), {"Content-Type": "application/json"})
    resp = conn.getresponse()
    data = resp.read().decode("utf-8", "replace")
    conn.close()
    return resp.status, json.loads(data) if data else {}


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

        # Тур новичка может стартовать на свежей сессии — закрываем
        try:
            page.wait_for_selector(".tour-layer", timeout=3500)
            page.keyboard.press("Escape")
            time.sleep(0.5)
        except Exception:
            pass

        snap = page.evaluate("""() => {
            const st = Alpine.store('next');
            if (!st) return null;
            return {
                n: st.registry.length,
                ids: st.registry.map(x => x.id),
                bad: st.registry.filter(x =>
                    !x.id || !x.view || !x.labelRu || !x.labelEn ||
                    !x.icon || !x.group || x.order === undefined).map(x => x.id),
                groups: [...new Set(st.registry.map(x => x.group))].sort(),
                resolveEmp: (st.resolve('employees') || {}).id || null,
                resolveDiag: (st.resolve('diag') || {}).id || null,
                resolveNope: (st.resolve('no-such-thing') || {}).id || null,
                enPeople: st.labelOf(st.byId('people'), 'en'),
            };
        }""")
        check("стор next существует", snap is not None)
        check("реестр >= 20 записей", snap["n"] >= 20, str(snap["n"]))
        check("все записи полные", snap["bad"] == [], str(snap["bad"]))
        check(
            "группы core/safety/service/work",
            snap["groups"] == ["core", "safety", "service", "work"],
            str(snap["groups"]),
        )
        check(
            "resolve по key/alias/fallback",
            snap["resolveEmp"] == "people"
            and snap["resolveDiag"] == "diagnostics"
            and snap["resolveNope"] == "overview",
            f"{snap['resolveEmp']}/{snap['resolveDiag']}/{snap['resolveNope']}",
        )
        check("EN-подпись", snap["enPeople"] == "People", snap["enPeople"])

        # Открытие через событие-адаптер
        page.evaluate(
            "() => document.dispatchEvent(new CustomEvent('suot-next-open',"
            " {detail: {id: 'people'}}))"
        )
        page.wait_for_selector("table.grid:visible", timeout=10000)
        active = page.evaluate("() => Alpine.store('next').activeId")
        check("открытие people через реестр", active == "people", active)

        # Пины переживают перезагрузку
        page.evaluate(
            "() => { const st = Alpine.store('next');"
            " st.pinned = ['overview', 'people', 'risk']; st.persist(); }"
        )
        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector(".shell", timeout=15000)
        pins = page.evaluate("() => Alpine.store('next').pinned")
        check("пины persist", pins == ["overview", "people", "risk"], str(pins))

        # Recent capped (открываем 14 разных)
        ids = page.evaluate("() => Alpine.store('next').registry.map(x => x.id)")
        for vid in ids[:14]:
            page.evaluate(
                "() => document.dispatchEvent(new CustomEvent('suot-next-open',"
                f" {{detail: {{id: '{vid}'}}}}))"
            )
            time.sleep(0.15)
        recent = page.evaluate("() => Alpine.store('next').recent")
        check("recent capped 12", len(recent) <= 12, f"len={len(recent)}")
        check("recent: последний первый", recent[0] == ids[13], str(recent[:3]))

        # Alt+2 открывает второй закреплённый
        page.keyboard.press("Escape")
        time.sleep(0.3)
        page.mouse.click(700, 20)
        page.keyboard.press("Alt+2")
        time.sleep(0.8)
        active2 = page.evaluate("() => Alpine.store('next').activeId")
        check("Alt+2 открывает закреплённое", active2 == "people", active2)

        # Панель-переключатель
        page.get_by_role("button", name="Рабочая область").click()
        page.wait_for_selector(".ws-overlay:visible", timeout=5000)
        panel_text = page.locator(".ws-panel").inner_text()
        low = panel_text.lower()
        check(
            "панель открылась (RU)",
            "закреплено" in low and "недавние" in low,
            panel_text[:80].replace("\n", " "),
        )
        n_items = page.locator(".ws-item").count()
        check("элементов в панели > 20", n_items > 20, str(n_items))
        page.keyboard.press("Escape")
        time.sleep(0.4)
        check(
            "Escape закрывает панель", page.locator(".ws-overlay:visible").count() == 0
        )
        # Поиск фильтрует
        page.get_by_role("button", name="Рабочая область").click()
        page.locator(".ws-search").fill("календарь")
        time.sleep(0.4)
        vis_items = page.locator(".ws-item:visible").count()
        check(
            "поиск фильтрует",
            0 < vis_items < n_items,
            f"visible={vis_items} total={n_items}",
        )
        page.keyboard.press("Escape")
        time.sleep(0.3)

        # Регрессия сайдбара
        page.locator(".nav-item", has_text="Сотрудники").click()
        page.wait_for_selector("table.grid:visible", timeout=8000)
        check("сайдбар открывает таблицу", True)

        js_err = [e for e in errors if "favicon" not in e]
        check("нет JS-ошибок", not js_err, "; ".join(js_err[:2]))
        browser.close()
finally:
    cleanup()

print(f"\n{len(PASS)} OK, {len(FAIL)} FAIL")
sys.exit(1 if FAIL else 0)
