"""E2E UX (Блок 1.5 п.3): таблица не выходит за экран, sticky-заголовки,
единый focus-trap модалок (Tab циклится внутри, автопри открытии)."""

import io, json, os, sys, subprocess, time, tempfile, socket

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

TMPD = tempfile.mkdtemp(prefix="suot_e2eux_")
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
        page = browser.new_page(
            viewport={"width": 1280, "height": 800}, reduced_motion="no-preference"
        )
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on(
            "console", lambda m: errors.append(m.text) if m.type == "error" else None
        )

        page.goto(BASE_URL + "/", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector(".lang-cards", timeout=15000)
        time.sleep(0.5)
        page.get_by_role("button", name="Русский").click()
        page.wait_for_selector(".auth-card", timeout=8000)
        page.locator(".seg-btn").nth(1).click()
        page.get_by_placeholder("Иванов Иван Иванович").fill("Юхкес Тест")
        page.get_by_placeholder("например, ivanov").fill("ux_user")
        page.get_by_placeholder("минимум 6 символов").fill("parol123")
        page.get_by_role("button", name="Создать аккаунт").click()
        page.wait_for_selector(".shell", timeout=10000)
        check("вход выполнен", True)

        # ── Засеять демо-данные через API (нужны строки таблицы) ──
        def _api(method, path, body, token=None):
            conn = http.client.HTTPConnection("127.0.0.1", PORT, timeout=8)
            headers = {"Content-Type": "application/json"}
            if token:
                headers["Authorization"] = "Bearer " + token
            conn.request(method, path, json.dumps(body), headers)
            resp = conn.getresponse()
            data = resp.read().decode("utf-8", "replace")
            conn.close()
            return resp.status, data

        st, data = _api(
            "POST", "/api/auth/login", {"username": "ux_user", "password": "parol123"}
        )
        token = json.loads(data).get("token") if st == 200 else None
        st2 = _api("POST", "/api/demo/seed", {}, token)[0] if token else 0
        check("демо-данные засеяны", st == 200 and st2 == 200, f"login={st} seed={st2}")

        # Закрыть онбординг-тур, если появился
        try:
            page.wait_for_selector(".tour-layer", timeout=3500)
            page.keyboard.press("Escape")
            time.sleep(0.5)
        except Exception:
            pass

        # ── Таблица: нет горизонтального скролла страницы ──
        page.locator(".nav-item", has_text="Сотрудники").click()
        page.wait_for_selector("table.grid", timeout=8000)
        time.sleep(0.6)
        overflow = page.evaluate(
            "() => document.documentElement.scrollWidth"
            " - document.documentElement.clientWidth"
        )
        check(
            "страница не распирает по горизонтали",
            overflow <= 0,
            f"overflow={overflow}",
        )

        # ── Sticky-заголовки и угловая ячейка (в видимой вкладке) ──
        th_pos = page.locator(".tabpane:visible table.grid th").first.evaluate(
            "el => getComputedStyle(el).position"
        )
        check("заголовок таблицы sticky", th_pos == "sticky", th_pos)
        corner_z = page.locator(
            ".tabpane:visible table.grid thead th:first-child"
        ).first.evaluate("el => getComputedStyle(el).zIndex")
        check("угловая ячейка z-index=6", corner_z == "6", corner_z)

        # ── Focus-trap: центр настроек ──
        page.locator(".statusbar-cmd").last.click()
        page.wait_for_selector(".sc-modal:visible", timeout=6000)
        time.sleep(0.4)

        def in_sc():
            return page.evaluate(
                "() => { const m = document.querySelector('.sc-modal');"
                " return !!(m && m.contains(document.activeElement)); }"
            )

        check("автофокус внутри модалки при открытии", in_sc())

        trapped = True
        for _ in range(15):
            page.keyboard.press("Tab")
            if not in_sc():
                trapped = False
                break
        check("Tab не покидает модалку (15 шагов)", trapped)

        page.keyboard.press("Shift+Tab")
        check("Shift+Tab остаётся в модалке", in_sc())

        page.keyboard.press("Escape")
        time.sleep(0.5)
        check(
            "Escape закрывает модалку", page.locator(".sc-modal:visible").count() == 0
        )

        # ── Модалка подтверждения: футер sticky и кликабелен ──
        try:
            page.wait_for_selector(
                "table.grid tbody td.col-actions .icon-btn.danger", timeout=10000
            )
            page.locator(
                "table.grid tbody td.col-actions .icon-btn.danger"
            ).first.click()
            page.wait_for_selector(".modal:visible", timeout=4000)
            foot_pos = page.locator(".modal-foot:visible").first.evaluate(
                "el => getComputedStyle(el).position"
            )
            check("футер подтверждения sticky", foot_pos == "sticky", str(foot_pos))
            page.locator(".modal:visible .modal-foot .btn").first.click()
            time.sleep(0.4)
            check(
                "отмена удаления закрыла модалку",
                page.locator(".modal:visible").count() == 0,
            )
        except Exception as ex:
            check("модалка подтверждения удаления", False, repr(ex)[:120])

        js_err = [e for e in errors if "favicon" not in e]
        check("нет JS-ошибок", not js_err, "; ".join(js_err[:2]))

        browser.close()
finally:
    cleanup()

print(f"\n{len(PASS)} OK, {len(FAIL)} FAIL")
sys.exit(1 if FAIL else 0)
