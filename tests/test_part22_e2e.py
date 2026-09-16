"""Часть 22: E2E — дизайн «Минимал»: рельс, топбар, пресеты, custom CSS."""

import io, os, sys, subprocess, time, tempfile, socket

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

TMPD = tempfile.mkdtemp(prefix="suot_e2e22_")
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

PASS, FAIL = [], []


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(("  OK " if cond else "FAIL ") + name + (f" | {extra}" if extra else ""))


try:
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        errs = []
        page.on("pageerror", lambda e: errs.append(str(e)))
        page.goto(BASE + "/", wait_until="domcontentloaded")
        page.wait_for_selector(".lang-cards", timeout=15000)
        page.get_by_role("button", name="Русский").click()
        page.wait_for_selector(".auth-card", timeout=8000)
        page.locator(".seg-btn").nth(1).click()
        page.get_by_placeholder("Иванов Иван Иванович").fill("Дизайнер Т")
        page.get_by_placeholder("например, ivanov").fill("design_user")
        page.get_by_placeholder("минимум 6 символов").fill("parol123")
        page.get_by_role("button", name="Создать аккаунт").click()
        page.wait_for_selector(".shell", timeout=10000)
        time.sleep(1.6)
        if page.locator(".tour-layer").count():
            page.keyboard.press("Escape")
            time.sleep(0.4)

        # ── Топбар: поиск + пользователь ──
        check("топбар-поиск виден", page.locator(".topsearch").is_visible())
        page.locator(".topsearch").click()
        page.wait_for_selector(".palette:visible", timeout=5000)
        check("топбар открывает палитру", True)
        page.keyboard.press("Escape")
        time.sleep(0.3)

        check("чип пользователя виден", page.locator(".userchip-btn").is_visible())
        page.locator(".userchip-btn").click()
        time.sleep(0.3)
        check(
            "меню пользователя открылось",
            page.locator(".user-pop .more-item").count() >= 4,
        )
        page.locator(".user-pop .more-item", has_text="Настройки").click()
        page.wait_for_selector(".sc-modal:visible", timeout=6000)
        check("чип → настройки", True)
        page.keyboard.press("Escape")
        time.sleep(0.3)

        # ── Рельс ──
        page.locator(".rail-toggle").click()
        time.sleep(0.5)
        check(
            "сайдбар свернулся в рельс",
            page.evaluate(
                "document.querySelector('.sidebar').classList.contains('rail')"
            ),
        )
        nav_ok = page.evaluate(
            "[...document.querySelectorAll('.nav-item')]"
            ".every(b => b.getBoundingClientRect().width < 70)"
        )
        check("пункты рельса узкие", nav_ok)
        page.locator(".rail-toggle").click()
        time.sleep(0.5)
        check(
            "сайдбар развернулся обратно",
            not page.evaluate(
                "document.querySelector('.sidebar').classList.contains('rail')"
            ),
        )

        # ── Пресеты акцентов + custom CSS ──
        page.locator(".statusbar-cmd").last.click()
        page.wait_for_selector(".sc-modal:visible", timeout=6000)
        dots = page.locator(".acc-dot")
        check(f"пресеты акцентов ({dots.count()})", dots.count() == 6)
        dots.nth(3).click()
        time.sleep(0.5)
        acc = page.evaluate(
            "getComputedStyle(document.documentElement)"
            ".getPropertyValue('--acc').trim()"
        )
        check(f"пресет применился ({acc})", "#10B981" in acc)

        page.locator(".sc-body:visible textarea").fill(
            ".tab-title { letter-spacing: 2px; }"
        )
        page.locator(".sc-body:visible .btn", has_text="Сохранить").last.click()
        page.wait_for_selector(".toast.success", timeout=5000)
        time.sleep(0.4)
        ls_applied = page.evaluate("document.getElementById('user-css') !== null")
        check("custom CSS применён (<style id=user-css>)", ls_applied)

        # Переживает перезагрузку
        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector(".shell", timeout=15000)
        time.sleep(1.2)
        still = page.evaluate("document.getElementById('user-css')?.textContent || ''")
        check("custom CSS после reload", "letter-spacing" in still)
        rail_kept = page.evaluate("localStorage.getItem('suot_rail') !== null")
        check("состояние рельса сохраняется", rail_kept)

        # ── Брендинг ──
        title = page.title()
        check(f"заголовок окна ({title[:26]})", "ОхранаТруда" in title)
        brand = page.locator(".sidebar-brand").inner_text()
        check("сайдбар: ОхранаТруда Про", "ОхранаТруда" in brand)

        real_errors = [e for e in errs if "favicon" not in e.lower()]
        check(
            "нет JS-ошибок", len(real_errors) == 0, ("; ".join(real_errors[:2]))[:150]
        )
        browser.close()

    print(f"\nE2E Часть 22: {len(PASS)} OK, {len(FAIL)} FAIL")
    if FAIL:
        print("Провалены:", FAIL)
finally:
    server_proc.terminate()
