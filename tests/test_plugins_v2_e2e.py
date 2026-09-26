"""E2E SUOT Next Plugin/Capability v2 (Блок 8): manifest validate,
capabilities/grants, per-user settings с валидацией, поведение читает
настройки, гейт без капа, Plugin Center UI, RU, ноль JS-ошибок."""

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

TMPD = tempfile.mkdtemp(prefix="suot_plug2_")
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


try:
    with sync_playwright() as pw:
        # ── серверный уровень ──
        st, lst = _api("GET", "/api/plugins", TOKEN)
        items = {p["id"]: p for p in lst.get("items", [])}
        check(
            "3 плагина, manifest v2",
            st == 200
            and len(items) == 3
            and all(p.get("manifest_version") == 2 for p in items.values()),
            str(sorted(items)),
        )
        qo = items.get("quick-overdue", {})
        check(
            "бандл с авто-грантом write",
            "table.write" in qo.get("granted_capabilities", []),
            str(qo.get("granted_capabilities")),
        )
        check(
            "needs_grant пуст у бандлов",
            not items.get("copy-tsv", {}).get("needs_grant")
            and not qo.get("needs_grant"),
        )

        st, v = _api(
            "POST",
            "/api/plugins/validate",
            TOKEN,
            {
                "manifest": {
                    "commands": [{"behavior": "nope"}],
                    "capabilities": ["fly"],
                    "settings_schema": [{"key": "x", "type": "weird"}],
                    "min_app_version": "notaversion",
                }
            },
        )
        check(
            "битый манифест: ошибки",
            st == 200 and not v.get("ok") and len(v.get("errors", [])) >= 4,
            "; ".join(v.get("errors", [])[:3]),
        )
        st, v = _api(
            "POST",
            "/api/plugins/validate",
            TOKEN,
            {
                "manifest": {
                    "id": "future",
                    "min_app_version": "99.0.0",
                    "commands": [{"behavior": "copy_tsv"}],
                    "capabilities": ["table.read", "clipboard"],
                }
            },
        )
        check(
            "несовместимая версия",
            not v.get("ok") and any("99.0.0" in e for e in v.get("errors", [])),
        )
        st, v = _api(
            "POST",
            "/api/plugins/validate",
            TOKEN,
            {"manifest": {"id": "legacy", "commands": [{"behavior": "copy_tsv"}]}},
        )
        check(
            "v1: ок с варнингом",
            v.get("ok") and any("legacy" in w for w in v.get("warnings", [])),
            str(v.get("warnings")),
        )

        st, gs = _api("GET", "/api/plugins/quick-overdue/settings", TOKEN)
        check(
            "дефолты настроек",
            st == 200 and gs.get("settings", {}).get("color") == "red",
            str(gs.get("settings")),
        )
        st, _ = _api(
            "PUT", "/api/plugins/quick-overdue/settings", TOKEN, {"color": "purple"}
        )
        check("невалидная опция → 400", st == 400)
        st, _ = _api("PUT", "/api/plugins/copy-tsv/settings", TOKEN, {"header": "yes"})
        check("неверный тип → 400", st == 400)
        st, _ = _api("PUT", "/api/plugins/copy-tsv/settings", TOKEN, {"nope": 1})
        check("неизвестный ключ → 400", st == 400)
        st, gs = _api(
            "PUT",
            "/api/plugins/copy-tsv/settings",
            TOKEN,
            {"delimiter": "semicolon", "header": False},
        )
        check(
            "валидные настройки",
            st == 200 and gs.get("settings", {}).get("delimiter") == "semicolon",
        )

        st, reg = _api(
            "POST",
            "/api/auth/register",
            "",
            {"username": "plug_b", "password": "parol123"},
        )
        BTOK = reg.get("token", "") if st in (200, 201) else ""
        st, _ = _api("POST", "/api/plugins/quick-overdue/grants", BTOK, {"grants": []})
        check("гранты не-админ → 403", st == 403)
        st, bs = _api("GET", "/api/plugins/copy-tsv/settings", BTOK)
        check(
            "настройки изолированы по юзерам",
            st == 200 and bs.get("settings", {}).get("delimiter") == "tab",
            str(bs.get("settings")),
        )

        # ── браузерный уровень ──
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

        _api(
            "POST",
            "/api/data/employees",
            TOKEN,
            {"data": {"ФИО": "Плагинов П", "Дата медосмотра": "01.01.2030"}},
        )

        # Поведение читает настройку: ставим orange через API, жмём через UI
        _api("PUT", "/api/plugins/quick-overdue/settings", TOKEN, {"color": "orange"})
        page.locator(".nav-item", has_text="Сотрудники").first.click()
        page.wait_for_selector("table.grid:visible", timeout=10000)
        time.sleep(1.2)
        page.locator(".tabpane:visible td.col-sel input.cbx").first.check()
        time.sleep(0.4)
        page.evaluate("() => window.__pluginRun('overdue_label')")
        time.sleep(1.5)
        st, lst = _api("GET", "/api/data/employees", TOKEN)
        labels = [
            str((it.get("data") or {}).get("_label", "")) for it in lst.get("items", [])
        ]
        check("метка цвета из настроек", "orange" in labels, str(labels[:3]))

        # Гейт: отзываем грант → кнопка скрыта, запуск блокируется
        _api("POST", "/api/plugins/quick-overdue/grants", TOKEN, {"grants": []})
        page.evaluate("() => Alpine.store('plugins').load()")
        time.sleep(1.0)
        tb_btns = page.evaluate(
            "() => Alpine.store('plugins').toolbarFor('employees').map(b => b.behavior)"
        )
        check("тулбар скрыт без капа", "overdue_label" not in tb_btns, str(tb_btns))
        toasts = []
        page.on("console", lambda m: None)
        page.evaluate("() => window.__pluginRun('overdue_label')")
        time.sleep(0.8)
        toast_txt = page.evaluate(
            "() => [...document.querySelectorAll('.toast')].map(e => e.innerText).join(' | ')"
        )
        check(
            "запуск блокируется тостом",
            "Missing" in toast_txt or "Нет возможности" in toast_txt,
            toast_txt[:100],
        )
        _api(
            "POST",
            "/api/plugins/quick-overdue/grants",
            TOKEN,
            {"grants": ["table.write"]},
        )

        # Plugin Center UI: настройки через редактор
        page.evaluate(
            "() => document.dispatchEvent(new CustomEvent('suot-open-settings',"
            " {bubbles: true}))"
        )
        page.wait_for_selector(".sc-modal", timeout=10000)
        time.sleep(1.0)
        page.locator(".sc-tab", has_text="Плагины").click()
        time.sleep(1.2)
        body_txt = page.locator(".sc-modal").first.inner_text()
        check(
            "центр показывает v2 и капы",
            "v2" in body_txt and "table.write" in body_txt,
        )
        check("кнопка настроек есть", page.locator(".plug-settings-btn").count() >= 1)
        page.locator(".plug-settings-btn").first.click()
        page.wait_for_selector(".plug-settings-editor:visible select", timeout=8000)
        time.sleep(0.4)
        page.locator(".plug-settings-editor:visible select").first.select_option(
            "semicolon"
        )
        page.locator(".plug-settings-editor:visible .plug-settings-save").click()
        time.sleep(1.0)
        st, gs = _api("GET", "/api/plugins/copy-tsv/settings", TOKEN)
        check(
            "редактор сохранил delimiter",
            gs.get("settings", {}).get("delimiter") == "semicolon",
        )

        js_err = [e for e in errors if "favicon" not in e.lower()]
        check("нет JS-ошибок", not js_err, "; ".join(js_err[:2]))
        browser.close()
finally:
    cleanup()

print(f"\n{len(PASS)} OK, {len(FAIL)} FAIL")
sys.exit(1 if FAIL else 0)
