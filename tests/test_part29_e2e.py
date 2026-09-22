"""Часть 29: UX-полировка. Toast-центр (история), Error Boundary, help-оверлей
«?», расширенный гайд + чеклист, ARIA-метки, пустые состояния."""

import os, sys, subprocess, time, tempfile, socket

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TMPD = tempfile.mkdtemp(prefix="suot_e2e29_")
os.environ["SUOT_E2E_DB"] = os.path.join(TMPD, "e2e.db")


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
import http.client

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


def _pane(page):
    return page.locator(".tabpane:visible")


try:
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        page = b.new_page(viewport={"width": 1500, "height": 900})
        errs = []
        cb_log = []
        page.on("pageerror", lambda e: errs.append(str(e)))
        page.on("console", lambda m: cb_log.append(m.type + ": " + m.text[:220]))
        page.goto(BASE + "/", wait_until="domcontentloaded")
        page.wait_for_selector(".lang-cards", timeout=15000)
        page.get_by_role("button", name="Русский").click()
        page.wait_for_selector(".auth-card", timeout=8000)
        page.locator(".seg-btn").nth(0).click()
        page.get_by_placeholder("например, ivanov").fill("admin")
        page.get_by_placeholder("минимум 6 символов").fill("admin")
        page.get_by_role("button", name="Войти").click()
        page.wait_for_selector(".shell", timeout=10000)
        time.sleep(1.6)
        if page.locator(".tour-layer").count():
            page.keyboard.press("Escape")
            time.sleep(0.3)

        # ══ ARIA-метки ══
        check(
            "ARIA: сайдбар «Главное меню»",
            page.locator('.sidebar[aria-label="Главное меню"]').count() == 1,
        )
        check(
            "ARIA: статус-бар с label",
            page.locator(".statusbar[aria-label]").count() == 1,
        )
        # ══ Help-оверлей «?» ══
        page.locator(".statusbar-cmd", has_text="?").click()
        helpbox = (
            page.locator(".sc-overlay")
            .filter(has=page.locator(".sc-tab", has_text="Руководство"))
            .first
        )
        helpbox.wait_for(state="visible", timeout=5000)
        check(
            "help-оверлей открыт кнопкой «?»",
            page.locator(".sc-modal:visible").count() >= 1,
        )

        # Гайд: роли + ASCII + чеклист
        helpbox.locator(".sc-tab", has_text="Руководство").click()
        time.sleep(0.3)
        gtxt = helpbox.locator(".hc-intro").inner_text()
        check(
            "гайд: ASCII-схема интерфейса",
            "СХЕМА" in helpbox.locator(".hc-ascii").inner_text(),
        )
        check(
            "гайд: сценарий по роли",
            "Инженер по охране труда"
            in helpbox.locator(".hc-rolecard").first.inner_text(),
        )
        check(
            "гайд: чеклист с чекбоксами",
            helpbox.locator(".hc-mod input[type=checkbox]").count() >= 5,
        )

        # клик по чекбоксу сохраняет прогресс
        helpbox.locator(".hc-mod input[type=checkbox]").first.check()
        time.sleep(0.3)
        saved = page.evaluate("localStorage.getItem('suot_checklist')")
        check(
            "чеклист сохраняется в localStorage",
            saved and '"dashboard":true' in saved,
            (saved or "")[:80],
        )
        check("прогресс-бар виден", helpbox.locator(".hc-progress-fill").count() == 1)
        # закрываем F1-справку
        page.keyboard.press("Escape")
        time.sleep(0.3)

        # ══ Toast-центр ══
        page.evaluate("window.Toast.show('Привет из теста', 'success')")
        page.wait_for_selector(".toast", timeout=3000)
        toast_n = page.locator(".toast").count()
        check("toast показан один раз", toast_n == 1, f"n={toast_n}")
        page.locator(".statusbar-wrap .statusbar-cmd").first.click(force=True)
        page.wait_for_selector(".toast-hist", timeout=3000)
        check("toast-центр открывается", page.locator(".toast-hist").is_visible())
        hist_txt = page.locator(".toast-hist").inner_text()
        check("toast-центр хранит сообщение", "Привет из теста" in hist_txt)
        # очистка истории
        page.locator(".toast-hist .icon-btn").click()
        time.sleep(0.4)
        empty_txt = page.locator(".toast-hist").inner_text()
        check("toast-центр: очистка истории", "Пока пусто" in empty_txt)
        page.keyboard.press("Escape")
        time.sleep(0.2)

        # ══ Error Boundary ══
        page.evaluate("window.onerror('SYNTH_ERR', 'app.js', 1, 1, null)")
        page.wait_for_selector(".eb-layer", timeout=3000)
        check("Error Boundary: экран ошибки", page.locator(".eb-layer").is_visible())
        eb_txt = page.locator(".eb-layer").inner_text()
        check("Error Boundary: сообщение", "SYNTH_ERR" in eb_txt)
        check(
            "Error Boundary: кнопки",
            page.locator(".eb-layer button", has_text="Копировать").count() == 1,
        )
        # перезагрузка снимает экран
        page.reload()
        page.wait_for_selector(".shell", timeout=10000)
        time.sleep(1.2)
        if page.locator(".tour-layer").count():
            page.keyboard.press("Escape")
            time.sleep(0.3)
        check(
            "Error Boundary: reload убирает экран",
            page.locator(".eb-layer").count() == 0,
        )

        # ══ Пустые состояния: таблица ══
        page.locator(".nav-item", has_text="Сотрудники").last.click()
        page.wait_for_selector(".tabpane:visible .tablewrap", timeout=10000)
        time.sleep(0.8)
        pane = _pane(page)
        has_empty = (
            pane.locator(".empty-cell").count() or pane.locator(".fp-empty").count()
        )
        empty_btn = pane.locator(".empty-cell button", has_text="Добавить").count()
        check("пустое состояние таблицы ", has_empty > 0)
        check("пустое состояние: есть действие «Добавить»", empty_btn >= 1)

        # ══ Тулбар/навигация доступны после всех проверок ══
        page.locator(".nav-item", has_text="Инструменты").last.click()
        page.wait_for_selector(".tabpane:visible .tools-page", timeout=10000)
        time.sleep(0.5)
        check(
            "после UX-правок инструменты работают",
            _pane(page).locator(".big-clock").count() == 1,
        )

        # ═══ JavaScript/console ═══
        real_errors = [
            e for e in errs if "favicon" not in e.lower() and "SYNTH_ERR" not in e
        ]
        check(
            "нет реальных JS-ошибок",
            len(real_errors) == 0,
            ("; ".join(real_errors[:2]))[:150],
        )
        console_issues = [
            c
            for c in cb_log
            if "favicon" not in c.lower()
            and "404" not in c
            and "ERR_CONNECTION" not in c
        ]
        check(
            "нет console-ошибок",
            len(console_issues) == 0,
            ("; ".join(console_issues[:3]))[:200],
        )
        b.close()

    print(f"\nE2E Часть 29: {len(PASS)} OK, {len(FAIL)} FAIL")
    if FAIL:
        print("Провалены:", FAIL)
finally:
    srv.terminate()
