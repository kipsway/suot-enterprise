"""Часть 29: i18n-audit EN. Новые блоки (help-гайд, toast-центр, error boundary)
работают и остаются двуязычными в английском интерфейсе."""

import os, sys, subprocess, time, tempfile, socket
import http.client

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TMPD = tempfile.mkdtemp(prefix="suot_en29_")
os.environ["SUOT_E2E_DB"] = os.path.join(TMPD, "en29.db")


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
for _ in range(120):
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
        page = b.new_page(viewport={"width": 1500, "height": 900})
        errs = []
        page.on("pageerror", lambda e: errs.append(str(e)))
        page.goto(BASE + "/", wait_until="domcontentloaded")
        page.wait_for_selector(".lang-cards", timeout=15000)
        page.get_by_role("button", name="English").click()
        page.wait_for_selector(".auth-card", timeout=8000)
        page.locator(".seg-btn").nth(0).click()
        page.get_by_placeholder("e.g. jsmith").fill("admin")
        page.get_by_placeholder("at least 6 characters").fill("admin")
        page.get_by_role("button", name="Sign in", exact=True).last.click()
        page.wait_for_selector(".shell", timeout=10000)
        time.sleep(1.4)
        if page.locator(".tour-layer").count():
            page.keyboard.press("Escape")
            time.sleep(0.3)

        # Help + гайд на EN
        page.locator(".statusbar-cmd", has_text="?").click()
        helpbox = (
            page.locator(".sc-overlay")
            .filter(has=page.locator(".sc-tab", has_text="Guide"))
            .first
        )
        try:
            helpbox.wait_for(state="visible", timeout=5000)
        except Exception:
            print(
                "  DBG overlays:",
                page.locator(".sc-overlay").count(),
                "sc-modal:",
                page.locator(".sc-modal").count(),
            )
            print(
                "  DBG lang:",
                page.evaluate("I18N.lang"),
                "docLang:",
                page.evaluate("document.documentElement.lang"),
            )
            for i in range(page.locator(".sc-overlay").count()):
                print(
                    "  DBG overlay",
                    i,
                    repr(page.locator(".sc-overlay").nth(i).inner_text()[:60]),
                )
            raise
        helpbox.locator(".sc-tab", has_text="Guide").click()
        time.sleep(0.3)
        check(
            "guide: заголовок роли EN",
            "HSE engineer" in helpbox.locator(".hc-rolecard").first.inner_text(),
        )
        check(
            "guide: ASCII-схема EN",
            "UI MAP" in helpbox.locator(".hc-ascii").inner_text(),
        )
        check(
            "guide: прогресс EN",
            "mastered" in helpbox.locator(".hc-progress").inner_text(),
        )
        page.keyboard.press("Escape")
        time.sleep(0.3)

        # Toast-центр подписан на EN
        page.evaluate("window.Toast.show('EN toast', 'success')")
        page.wait_for_selector(".toast", timeout=3000)
        page.locator(".statusbar-wrap .statusbar-cmd").first.click(force=True)
        page.wait_for_selector(".toast-hist", timeout=3000)
        hist_txt = page.locator(".toast-hist").inner_text()
        check("toast-центр: заголовок EN", "History" in hist_txt)
        check("toast-центр: сообщение сохранено", "EN toast" in hist_txt)
        page.keyboard.press("Escape")
        time.sleep(0.2)

        # Error Boundary на EN
        page.evaluate("window.onerror('SYNTH_EN', 'app.js', 1, 1, null)")
        page.wait_for_selector(".eb-layer", timeout=3000)
        eb_txt = page.locator(".eb-layer").inner_text()
        check("error boundary: заголовок EN", "went wrong" in eb_txt)
        check("error boundary: кнопка Copy", "Copy" in eb_txt)
        page.reload()
        page.wait_for_selector(".shell", timeout=10000)
        time.sleep(1.2)

        real_errors = [
            e for e in errs if "favicon" not in e.lower() and "SYNTH_EN" not in e
        ]
        check(
            "нет JS-ошибок (EN-сессия)",
            len(real_errors) == 0,
            ("; ".join(real_errors[:2]))[:150],
        )
        b.close()

    print(f"\nE2E EN Часть 29: {len(PASS)} OK, {len(FAIL)} FAIL")
    if FAIL:
        print("Провалены:", FAIL)
finally:
    srv.terminate()
