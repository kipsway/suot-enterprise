"""Часть 21: E2E-обход всех разделов — каждый должен открыться без ошибок."""

import io, os, sys, subprocess, time, tempfile, socket

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

TMPD = tempfile.mkdtemp(prefix="suot_trav_")
TEST_DB = os.path.join(TMPD, "e2e.db")
os.environ["SUOT_E2E_DB"] = TEST_DB


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


PORT = _free_port()
BASE = f"http://127.0.0.1:{PORT}"
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

for _ in range(100):
    try:
        c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=0.5)
        c.request("GET", "/api/health")
        if c.getresponse().status == 200:
            break
    except Exception:
        time.sleep(0.2)

from playwright.sync_api import sync_playwright

PASS, FAIL, BROKEN = [], [], []


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(("  OK " if cond else "FAIL ") + name + (f" | {extra}" if extra else ""))


try:
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page_errors = []
        page = ctx.new_page()
        page.on("pageerror", lambda e: page_errors.append(str(e)))
        page.goto(BASE + "/", wait_until="domcontentloaded")
        page.wait_for_selector(".lang-cards", timeout=15000)
        page.get_by_role("button", name="Русский").click()
        # сид есть → auth; вход admin/admin
        page.wait_for_selector(".auth-card", timeout=8000)
        page.get_by_placeholder("например, ivanov").fill("admin")
        page.get_by_placeholder("минимум 6 символов").fill("admin")
        btn = page.locator(".auth-form button[type=submit]")
        btn.click()
        try:
            page.wait_for_selector(".shell", timeout=8000)
            check("вход admin/admin работает", True)
        except Exception:
            check("вход admin/admin работает", False)
            raise

        time.sleep(1.6)
        # тур — пропустить
        if page.locator(".tour-layer").count():
            page.keyboard.press("Escape")
            time.sleep(0.4)

        # Загрузим демо через плитку/пустое состояние для содержимого
        nav_texts = page.evaluate(
            """[...document.querySelectorAll('.nav-item')]
                .map(b => b.textContent.trim())"""
        )
        print("NAV:", " | ".join(nav_texts))

        broken = []
        for label in nav_texts:
            low = label.lower()
            if (
                not label.strip()
                or "тем" in low
                or "выход" in low
                or "выйти" in low
                or "рабочая область" in low
            ):
                continue
            el = page.locator(".sidebar .nav-item", has_text=label).first
            try:
                el.click(timeout=4000)
            except Exception as e:
                broken.append((label, "CLICK: " + str(e)[:80]))
                continue
            time.sleep(0.7)
            visible_pane = page.evaluate(
                "[...document.querySelectorAll('.tabpane')]"
                ".some(p => p.offsetParent !== null)"
            )
            ok = (
                visible_pane
                or page.locator(".welcome, .dash-grid, .sp-wrap").first.is_visible()
            )
            if not ok:
                broken.append((label, "NO PANE"))
            else:
                check(f"раздел «{label}» открыт", True)

        for lbl, why in broken:
            check(f"раздел «{lbl}» открыт", False, why)
            BROKEN.append(lbl)

        js_errs = [e for e in page_errors if "favicon" not in e.lower()]
        check(
            "нет JS-исключений при обходе",
            len(js_errs) == 0,
            ("; ".join(js_errs[:2]))[:160],
        )

        # Полосы вкладок больше нет (детэбификация): 8 видов открываем
        # через стор, проверяем journey-состояние и отсутствие tabbar в DOM.
        for key in (
            "employees",
            "violations",
            "incidents",
            "ppe",
            "training",
            "permits",
            "work_orders",
            "companies",
        ):
            page.evaluate(f"Alpine.store('tabs').open('{key}')")
        time.sleep(0.6)
        journey = page.evaluate("""(() => ({
          active: ((Alpine.store('tabs').active) || {}).key || '',
          hasBar: !!document.querySelector('.tabbar'),
          paneVisible: [...document.querySelectorAll('.tabpane')]
            .some((p) => p.offsetParent !== null
              && p.querySelector('table.grid')),
        }))()""")
        check(
            "8 видов открыты, активна companies",
            journey["active"] == "companies",
            journey["active"],
        )
        check("полосы вкладок нет в DOM", journey["hasBar"] is False)
        check("контент активного вида виден", journey["paneVisible"])

        browser.close()

    print(f"\nTRAVARSE: {len(PASS)} OK, {len(FAIL)} FAIL")
    if BROKEN:
        print("Сломанные разделы:", BROKEN)
    sys.exit(1 if FAIL else 0)
finally:
    try:
        server_proc.terminate()
        server_proc.wait(timeout=5)
    except Exception:
        server_proc.kill()
