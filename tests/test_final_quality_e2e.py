"""E2E SUOT Next Блок 10 (финальное качество): a11y новых панелей,
EN-смог Documents/Plugins, перф-бюджеты, консистентность версий,
ноль JS-ошибок."""

import json
import os
import re
import sys
import subprocess
import time
import tempfile
import socket

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

TMPD = tempfile.mkdtemp(prefix="suot_final_")
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


def _has_cyrillic(s):
    return bool(re.search(r"[А-Яа-яЁё]", s or ""))


try:
    with sync_playwright() as pw:
        # ── версии: APP_VERSION = сайт-манифест = installer ──
        m = re.search(
            r'APP_VERSION\s*=\s*"([^"]+)"',
            open(os.path.join(ROOT, "app_core", "version.py"), encoding="utf-8").read(),
        )
        app_ver = m.group(1) if m else ""
        idx = json.load(
            open(
                os.path.join(ROOT, "site", "downloads", "index.json"), encoding="utf-8"
            )
        )
        site_ver = idx.get("version") or idx.get("latest") or ""
        if isinstance(site_ver, dict):
            site_ver = site_ver.get("version", "")
        iss = open(
            os.path.join(ROOT, "installer", "suot_neo.iss"),
            encoding="utf-8",
            errors="replace",
        ).read()
        im = re.search(r"#define\s+AppVersion\s+\"([^\"]+)\"", iss)
        iss_ver = im.group(1).strip() if im else ""
        check(
            "версия консистентна",
            bool(app_ver) and app_ver in site_ver and app_ver in iss_ver,
            f"app={app_ver} site={site_ver} iss={iss_ver}",
        )

        # ── перф API ──
        t0 = time.time()
        st, _ = _api("GET", "/api/dash/stats?period=all", TOKEN)
        dt_stats = time.time() - t0
        check("dash/stats < 3с", st == 200 and dt_stats < 3.0, f"{dt_stats:.2f}с")
        t0 = time.time()
        st, _ = _api("GET", "/api/data/employees?page_size=50", TOKEN)
        dt_list = time.time() - t0
        check("data/employees < 3с", st == 200 and dt_list < 3.0, f"{dt_list:.2f}с")

        # ── RU-сессия: a11y + перф рендера ──
        browser = pw.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1500, "height": 900})
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.add_init_script(f"localStorage.setItem('suot_token', '{TOKEN}');")
        t0 = time.time()
        page.goto(BASE_URL + "/", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector(".shell", timeout=15000)
        check("вход по токену", True)
        check("shell < 15с", time.time() - t0 < 15.0)
        try:
            page.wait_for_selector(".tour-layer", timeout=3500)
            page.keyboard.press("Escape")
            time.sleep(0.5)
        except Exception:
            pass

        _api(
            "POST",
            "/api/print/templates",
            TOKEN,
            {"name": "ФиналТест", "html_content": "<p>{ФИО}</p>"},
        )
        t0 = time.time()
        page.locator(".nav-item", has_text="Документы").first.click()
        page.wait_for_selector(".doc-center", timeout=10000)
        time.sleep(1.0)
        check("центр < 5с", time.time() - t0 < 5.0)

        # a11y: сегменты — нативные кнопки
        tags = page.evaluate(
            "() => [...document.querySelectorAll('.doc-center .seg-btn')]"
            ".map(e => e.tagName)"
        )
        check("сегменты — кнопки", tags and all(t == "BUTTON" for t in tags), str(tags))

        # a11y: модалка preview — role=dialog + Escape
        page.locator(".doc-prev-btn").first.click()
        page.wait_for_selector(".doc-center .modal[role='dialog']", timeout=8000)
        dlg = page.evaluate(
            "() => { const m = document.querySelector('.doc-center .modal[role=dialog]');"
            " return m ? m.getAttribute('aria-modal') + '/' + !!m.getAttribute('aria-label') : 'NO'; }"
        )
        check("dialog с aria", dlg == "true/true", dlg)
        page.keyboard.press("Escape")
        time.sleep(0.5)
        check(
            "Escape закрывает",
            page.locator(".doc-center .modal[role='dialog']:visible").count() == 0,
        )

        # a11y: инпуты настроек плагинов внутри label
        page.evaluate(
            "() => document.dispatchEvent(new CustomEvent('suot-open-settings',"
            " {bubbles: true}))"
        )
        page.wait_for_selector(".sc-modal", timeout=10000)
        page.locator(".sc-tab", has_text="Плагины").click()
        time.sleep(1.2)
        page.locator(".plug-settings-btn").first.click()
        page.wait_for_selector(".plug-settings-editor:visible", timeout=8000)
        unlabeled = page.evaluate(
            "() => { const ed = [...document.querySelectorAll("
            "'.plug-settings-editor')]"
            ".find(e => !!e.getClientRects().length);"
            " if (!ed) return -1;"
            " return [...ed.querySelectorAll('input, select')]"
            ".filter(e => !e.closest('label')).length; }"
        )
        check("инпуты с лейблами", unlabeled == 0, str(unlabeled))
        page.keyboard.press("Escape")
        time.sleep(0.4)
        browser.close()

        # ── EN-сессия: хром новых UI без кириллицы ──
        _api("POST", "/api/auth/locale", TOKEN, {"language": "en"})
        b2 = pw.chromium.launch()
        ctx2 = b2.new_context(viewport={"width": 1500, "height": 900})
        ctx2.add_init_script(
            "localStorage.setItem('suot_token', '" + TOKEN + "');"
            "localStorage.setItem('suot_lang', 'en');"
        )
        en = ctx2.new_page()
        en.on("pageerror", lambda e: errors.append("EN:" + str(e)))
        en.goto(BASE_URL + "/", wait_until="domcontentloaded", timeout=30000)
        en.wait_for_selector(".shell", timeout=15000)
        time.sleep(1.5)
        try:
            en.wait_for_selector(".tour-layer", timeout=3500)
            en.keyboard.press("Escape")
            time.sleep(0.5)
        except Exception:
            pass
        en.locator(".nav-item", has_text="Documents").first.click()
        en.wait_for_selector(".doc-center", timeout=10000)
        time.sleep(1.0)
        segs = en.evaluate(
            "() => [...document.querySelectorAll('.doc-center .seg-btn')]"
            ".map(e => e.innerText)"
        )
        check("EN сегменты", segs == ["Templates", "Reports", "Print queue"], str(segs))
        chrome = en.evaluate(
            "() => [...document.querySelectorAll('.doc-center .tbl-toolbar',"
            " '.doc-center .muted')].map(e => e.innerText).join(' ')"
        )
        check("EN хром без кириллицы", not _has_cyrillic(chrome), chrome[:100])
        en.evaluate(
            "() => document.dispatchEvent(new CustomEvent('suot-open-settings',"
            " {bubbles: true}))"
        )
        en.wait_for_selector(".sc-modal", timeout=10000)
        en.locator(".sc-tab", has_text="Plugins").click()
        time.sleep(1.2)
        plug_body = en.locator(".sc-modal").first.inner_text()
        check(
            "EN плагины",
            "Settings" in plug_body and "Copy selection to clipboard" in plug_body,
            plug_body[:120].replace("\n", " "),
        )
        b2.close()

        js_err = [e for e in errors if "favicon" not in e.lower()]
        check("нет JS-ошибок", not js_err, "; ".join(js_err[:2]))
finally:
    cleanup()

print(f"\n{len(PASS)} OK, {len(FAIL)} FAIL")
sys.exit(1 if FAIL else 0)
