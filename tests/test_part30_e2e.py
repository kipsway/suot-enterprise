"""Часть 30: Финал-качество (E2E). Страница диагностики (карточки, журнал,
активные сессии, отзыв сессии), роль Observer в панели пользователей,
интерфейс выбора ролей, автотема в настройках."""

import os, sys, subprocess, time, tempfile, socket

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TMPD = tempfile.mkdtemp(prefix="suot_e2e30_")
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

        # ══ Открытие страницы диагностики из футера сайдбара ══
        page.locator(".nav-item", has_text="Диагностика").last.click()
        page.wait_for_selector(".tabpane:visible .diag-grid", timeout=10000)
        time.sleep(1.2)
        pane = _pane(page)
        check(
            "diag: вкладка открыта и есть карточки",
            pane.locator(".diag-card").count() >= 4,
            f"cards={pane.locator('.diag-card').count()}",
        )
        check(
            "diag: карточка приложения",
            pane.locator(".diag-card", has_text="Приложение").count() == 1,
        )
        check(
            "diag: карточка среды",
            pane.locator(".diag-card", has_text="Среда").count() == 1,
        )
        check(
            "diag: карточка сервера",
            pane.locator(".diag-card", has_text="Сервер").count() == 1,
        )
        check(
            "diag: карточка базы данных",
            pane.locator(".diag-card", has_text="База данных").count() == 1,
        )
        # integrity отображается со статусом ok
        body_txt = pane.locator(".diag-card", has_text="База данных").inner_text()
        check("diag: integrity ок", "ok" in body_txt.lower(), body_txt[-80:])
        # версия Python в Среде
        env_txt = pane.locator(".diag-card", has_text="Среда").inner_text()
        check("diag: версия python", "Python" in env_txt or "python" in env_txt)
        # журнал событий: последние записи
        check(
            "diag: журнал событий",
            pane.locator(".diag-log-row").count() >= 1,
            f"rows={pane.locator('.diag-log-row').count()}",
        )
        # диск
        check(
            "diag: карточка диска",
            pane.locator(".diag-card", has_text="Диск").count() == 1,
        )

        # ══ Активные сессии ══
        page.locator(".diag-toolbar").get_by_role("button", name="Сессии").click()
        time.sleep(0.8)
        s_card = pane.locator(".diag-card", has_text="Активные сессии")
        check("diag: таблица активных сессий появилась", s_card.count() == 1)
        check(
            "diag: строка сессии присутствует",
            s_card.locator("tbody tr").count() >= 1,
            f"rows={s_card.locator('tbody tr').count()}",
        )
        # завершение сессии: кнопка присутствует у активной строки
        rows = s_card.locator("tbody tr")
        n0 = rows.count()
        check(
            "diag: кнопка «Завершить» у сессии",
            rows.last.get_by_role("button", name="Завершить").count() == 1,
        )

        # ══ Настройка темы: авто ══
        page.locator(".statusbar-cmd").last.click()
        page.wait_for_selector(".sc-modal", timeout=6000)
        time.sleep(0.5)
        theme_card = page.locator(".theme-card", has_text="Авто")
        check("настройки: тема «Авто» в списке", theme_card.count() == 1)
        theme_card.click()
        time.sleep(0.4)
        saved_theme = page.evaluate(
            "window.Appearance && window.Appearance.s ? window.Appearance.s.theme : ''"
        )
        check("настройки: тема сохранилась = auto", saved_theme == "auto", saved_theme)
        page.keyboard.press("Escape")
        time.sleep(0.3)

        # ══ Пользователи: выбор роли (Observer) ══
        page.evaluate(
            "fetch('/api/auth/register',"
            " { method:'POST', headers:{'Content-Type':'application/json'},"
            " body: JSON.stringify({username:'observer_e2e', password:'parol123'})}).then(r=>r.status)"
        )
        time.sleep(0.6)
        page.locator(".sidebar-foot .nav-item", has_text="Пользователи").click()
        page.wait_for_selector(".sc-overlay .ua-row", timeout=10000)
        time.sleep(0.6)
        b_row = page.locator(".ua-row", has_text="observer_e2e")
        check("users: строка второго пользователя", b_row.count() == 1)
        b_row.locator("button", has_text="Роль").click()
        time.sleep(0.3)
        obs_btn = b_row.locator(".role-pick button", has_text="Наблюдатель")
        check("users: в меню ролей есть Наблюдатель", obs_btn.count() == 1)
        obs_btn.click()
        time.sleep(0.8)
        badge_txt = b_row.locator(".ua-badge").first.inner_text()
        check("users: роль стала Наблюдатель", "Наблюдатель" in badge_txt, badge_txt)

        # ═══ JavaScript/console ═══
        real_errors = [e for e in errs if "favicon" not in e.lower()]
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

    print(f"\nE2E Часть 30: {len(PASS)} OK, {len(FAIL)} FAIL")
    if FAIL:
        print("Провалены:", FAIL)
finally:
    srv.terminate()
    try:
        srv.wait(timeout=5)
    except Exception:
        srv.kill()
