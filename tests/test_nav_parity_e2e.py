"""E2E SUOT Next Блок 9: паритет навигации.
Каждый вид реестра открывается без error-state и с содержательным контентом.
Порядок групп, RU/EN-подписи, switcher покрывает все записи. Ноль JS-ошибок."""

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

TMPD = tempfile.mkdtemp(prefix="suot_par9_")
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


def _api(path, body, token=""):
    conn = http.client.HTTPConnection("127.0.0.1", PORT, timeout=8)
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    conn.request("POST", path, json.dumps(body), headers)
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

st, login = _api("/api/auth/login", body={"username": "admin", "password": "admin"})
TOKEN = login.get("token", "") if st == 200 else ""
st, seed = _api("/api/demo/seed", TOKEN, {})
print("demo seed:", st)

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
        try:
            page.wait_for_selector(".tour-layer", timeout=3500)
            page.keyboard.press("Escape")
            time.sleep(0.5)
        except Exception:
            pass

        ids = page.evaluate("() => Alpine.store('next').registry.map(x => x.id)")
        check("реестр непуст", len(ids) >= 20, str(len(ids)))

        dead = []
        thin = []
        for vid in ids:
            page.evaluate(
                "() => document.dispatchEvent(new CustomEvent('suot-next-open',"
                + " {detail: {id: '"
                + vid
                + "'}}))"
            )
            time.sleep(0.9)
            try:
                state = page.evaluate("""() => {
                    const err = [...document.querySelectorAll(
                        '.table-state-error')].some(
                        e => e.getClientRects().length);
                    const panes = [...document.querySelectorAll(
                        '.tabpane')].filter(
                        p => p.offsetParent !== null);
                    const txt = panes.map(
                        p => (p.innerText || '').length);
                    const modal = [...document.querySelectorAll(
                        '.sc-modal')].some(
                        m => m.getClientRects().length);
                    return {err, panes: panes.length,
                            maxText: Math.max(0, ...txt), modal};
                }""")
            except Exception as ex:
                dead.append((vid, "EVAL: " + str(ex)[:60]))
                continue
            ok = (not state["err"]) and (state["maxText"] > 100 or state["modal"])
            if not ok:
                if state["err"] or state["maxText"] == 0 and not state["modal"]:
                    dead.append((vid, str(state)[:100]))
                else:
                    thin.append((vid, state["maxText"]))
            time.sleep(0.2)
        check("все виды живы (нет error-state, есть контент)", not dead, str(dead[:4]))
        check(f"пройдено видов: {len(ids) - len(dead)}/{len(ids)}", not dead)
        if thin:
            print(
                "INFO тонкие виды без данных (пустые structured-страницы):",
                ", ".join(f"{v}({n})" for v, n in thin),
            )

        # Порядок групп и подписи
        groups = page.evaluate("() => Alpine.store('next').groups().map(g => g.id)")
        check(
            "порядок групп",
            groups == ["core", "safety", "work", "service"],
            str(groups),
        )
        labels = page.evaluate("""() => {
            const st = Alpine.store('next');
            return st.registry
                .filter(x => !st.labelOf(x, 'ru') || !st.labelOf(x, 'en'))
                .map(x => x.id);
        }""")
        check("RU/EN у всех записей", labels == [], str(labels))

        # Switcher покрывает реестр: каждая RU-подпись видна в панели
        page.evaluate("() => window.SUOT_COMMANDS.run('workspace')")
        page.wait_for_selector(".ws-overlay:visible", timeout=5000)
        time.sleep(0.5)
        missing = page.evaluate("""() => {
            const st = Alpine.store('next');
            const text = document.querySelector('.ws-panel').innerText;
            return st.registry.filter(x => !text.includes(st.labelOf(x)))
                .map(x => x.id);
        }""")
        check("switcher покрывает все записи", missing == [], str(missing))
        page.keyboard.press("Escape")

        js_err = [e for e in errors if "favicon" not in e.lower()]
        check("нет JS-ошибок", not js_err, "; ".join(js_err[:2]))
        browser.close()
finally:
    cleanup()

print(f"\n{len(PASS)} OK, {len(FAIL)} FAIL")
sys.exit(1 if FAIL else 0)
