"""E2E-тест Части 18: F1-центр, тур, журнал аудита, пользователи,
смена пароля."""

import io, os, sys, subprocess, time, tempfile, socket

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

TMPD = tempfile.mkdtemp(prefix="suot_e2e18_")
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


def login_as(page, username, password, full_name=None):
    page.goto(BASE_URL + "/", wait_until="domcontentloaded")
    page.wait_for_selector(".lang-cards", timeout=15000)
    page.get_by_role("button", name="Русский").click()
    page.wait_for_selector(".auth-card", timeout=8000)
    # уже на вкладке входа по умолчанию (seg-btn[0])
    page.get_by_placeholder("например, ivanov").fill(username)
    page.get_by_placeholder("минимум 6 символов").fill(password)
    page.get_by_role("button", name=re.compile("Вой|войти"), exact=False).first.click()
    page.wait_for_selector(".shell", timeout=10000)


import re

try:
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1400, "height": 900})
        errors = []
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on(
            "console", lambda m: errors.append(m.text) if m.type == "error" else None
        )

        # ── Регистрация новичка → тур должен стартовать ──
        page.goto(BASE_URL + "/", wait_until="domcontentloaded")
        page.wait_for_selector(".lang-cards", timeout=15000)
        page.get_by_role("button", name="Русский").click()
        page.wait_for_selector(".auth-card", timeout=8000)
        page.locator(".seg-btn").nth(1).click()
        page.get_by_placeholder("Иванов Иван Иванович").fill("Новичков Тур")
        page.get_by_placeholder("например, ivanov").fill("tour_user")
        page.get_by_placeholder("минимум 6 символов").fill("parol123")
        page.get_by_role("button", name="Создать аккаунт").click()
        page.wait_for_selector(".shell", timeout=10000)
        try:
            page.wait_for_selector(".tour-layer", timeout=5000)
            check("тур стартовал автоматически", True)
        except Exception:
            check(
                "тур стартовал автоматически", page.locator(".tour-layer").count() > 0
            )

        # Шаги тура: далее ×3 → готово
        for i in range(4):
            btn = page.locator(".tour-card .btn.primary")
            btn.click()
            time.sleep(0.35)
        gone = page.locator(".tour-layer").count() == 0
        check(f"тур завершён за 4 шага ({4})", gone)

        # После reload не повторяется
        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector(".shell", timeout=15000)
        time.sleep(1.5)
        again = page.locator(".tour-layer").count() > 0
        check("после reload тур не повторяется", not again)

        # ── Журнал аудита ──
        page.locator(".nav-item", has_text="Сотрудники").click()
        pane_sel = ".tabpane:visible table.grid"
        page.wait_for_selector(pane_sel, timeout=8000)
        # создаём запись чтобы было событие? (регистрации уже в журнале)
        page.locator(".sidebar-foot .nav-item", has_text="Журнал").click()
        page.wait_for_selector(".jn-sev", timeout=8000)
        rows = page.locator(".tabpane:visible tbody tr").count()
        check(f"журнал открыт, строк: {rows}", rows > 0)

        # Фильтр q
        page.locator(".jn-q").fill("login")
        page.keyboard.press("Enter")
        time.sleep(0.6)
        frows = page.locator(".tabpane:visible tbody tr").count()
        check(f"фильтр q=login сузил ({rows}→{frows})", frows < rows)

        # CSV скачивается
        with page.expect_download() as dl_info:
            page.locator(
                ".tabpane:visible .btn.primary", has_text="Экспорт CSV"
            ).click()
        dl = dl_info.value
        csv_path = os.path.join(TMPD, "audit.csv")
        dl.save_as(csv_path)
        content = io.open(csv_path, encoding="utf-8-sig").read()
        check(
            "CSV журнала скачан с заголовком", "Событие" in content and ";" in content
        )

        page.keyboard.press("Escape")

        # ── Пользователи: не-админ видит пусто/ошибку ──
        page.locator(".sidebar-foot .nav-item", has_text="Пользователи").click()
        time.sleep(0.7)
        ua_open = page.evaluate("[...document.querySelectorAll('.ua-row')].length")
        check("не-админ: панель не открывается/пуста", ua_open == 0, str(ua_open))
        for _ in range(2):
            page.keyboard.press("Escape")
            time.sleep(0.2)

        # Выход новичка
        page.evaluate("""(() => {
          localStorage.removeItem('suot_token');
          sessionStorage.removeItem('suot_token_session'); })()""")
        ctx.close()

        # ── Админ: панель пользователей + блокировка ──
        # Пароль сида "admin" короче 6 символов — UI не пустит,
        # поэтому получаем токен через API и инжектим в localStorage.
        import urllib.request, json as _json

        req = urllib.request.Request(
            BASE_URL + "/api/auth/login",
            data=_json.dumps({"username": "admin", "password": "admin"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        adm_token = _json.loads(urllib.request.urlopen(req).read())["token"]
        ctx2 = browser.new_context(viewport={"width": 1400, "height": 900})
        ctx2.add_init_script("localStorage.setItem('suot_token', '%s');" % adm_token)
        p2 = ctx2.new_page()
        p2.on("pageerror", lambda e: errors.append(str(e)))
        p2.goto(BASE_URL + "/", wait_until="domcontentloaded")
        p2.wait_for_selector(".shell", timeout=15000)
        time.sleep(1.5)
        # Тур у админа тоже первый раз — пропустить
        if p2.locator(".tour-layer").count():
            p2.locator(".tour-card .btn.ghost-sm", has_text="Пропустить").click()
            time.sleep(0.3)

        p2.locator(".sidebar-foot .nav-item", has_text="Пользователи").click()
        p2.wait_for_selector(".ua-row", timeout=6000)
        urows = p2.locator(".ua-row").count()
        check(f"админ видит пользователей ({urows})", urows >= 2)

        # Блокируем tour_user
        row_tour = p2.locator(".ua-row", has_text="tour_user")
        row_tour.locator(".btn", has_text="Блокировать").click()
        p2.wait_for_selector(".modal:visible .modal-foot .btn.primary", timeout=4000)
        p2.locator(".modal:visible .modal-foot .btn.primary").click()
        time.sleep(0.8)
        blocked_badge = row_tour.locator(".ua-badge.off").count() > 0
        check("бейдж «заблокирован» появился", blocked_badge)

        # Разблокируем обратно
        row_tour.locator(".btn", has_text="Разблокировать").click()
        p2.locator(".modal:visible .modal-foot .btn.primary").wait_for(timeout=4000)
        p2.locator(".modal:visible .modal-foot .btn.primary").click()
        try:
            row_tour.locator(".ua-badge.off").wait_for(state="hidden", timeout=5000)
            unlocked = True
        except Exception:
            unlocked = False
        check("разблокирован", unlocked)

        # Сброс пароля tour_user
        row_tour.locator(".btn", has_text="Сброс пароля").click()
        p2.wait_for_selector(".modal:visible .modal-foot .btn.primary", timeout=4000)
        p2.locator(".modal:visible .modal-foot .btn.primary").click()
        p2.wait_for_selector(".ua-pwd code", timeout=5000)
        new_pwd = p2.locator(".ua-pwd code").inner_text().strip()
        check(f"новый пароль показан ({len(new_pwd)} симв.)", len(new_pwd) >= 8)
        p2.locator(".overlay", has_text="Новый пароль").locator(".btn.primary").click()
        time.sleep(0.4)
        for _ in range(2):
            p2.keyboard.press("Escape")
            time.sleep(0.2)

        # ── Смена своего пароля (у админа) ──
        p2.locator(".statusbar-cmd").last.click()
        p2.wait_for_selector(".sc-modal:visible", timeout=6000)
        p2.locator(".sc-tab", has_text="Аккаунт").click()
        time.sleep(0.3)
        pwd_inputs = p2.locator(".sc-body:visible input[type=password]")
        pwd_inputs.nth(0).fill("admin")
        pwd_inputs.nth(1).fill("newadminpw1")
        pwd_inputs.nth(2).fill("newadminpw1")
        p2.locator(".btn", has_text="Сменить пароль").click()
        p2.wait_for_selector(".toast.success", timeout=6000)
        check("смена пароля: toast успеха", True)
        p2.keyboard.press("Escape")

        # ── F1 центр помощи ──
        p2.keyboard.press("F1")
        p2.wait_for_selector(".sc-modal:visible", timeout=6000)
        tabs_n = p2.locator(".sc-tabs .sc-tab").count()
        check(f"F1 открыл центр помощи ({tabs_n} вкладки)", tabs_n >= 4)

        # Чит-лист: клик по «Палитра команд» выполняет действие
        p2.locator(".sc-modal:visible .sc-tab", has_text="Горячие клавиши").click()
        time.sleep(0.3)
        p2.locator(".hk-click", has_text="Палитра команд").click()
        time.sleep(0.6)
        pal_open = p2.evaluate(
            "[...document.querySelectorAll('.palette-overlay')]"
            ".some(o => getComputedStyle(o).display !== 'none')"
        )
        check("клик по чит-листу выполнил действие (палитра)", pal_open)
        p2.keyboard.press("Escape")
        time.sleep(0.3)

        # О программе: версия + проверка обновлений
        p2.keyboard.press("F1")
        p2.wait_for_selector(".sc-modal:visible", timeout=6000)
        p2.locator(".sc-modal:visible .sc-tab", has_text="О программе").click()
        time.sleep(0.4)
        ver_txt = p2.locator(".sc-body:visible .muted").first.inner_text()
        check("версия отображается", "." in ver_txt, ver_txt[:40])
        p2.locator(".btn", has_text="Проверить обновления").click()
        p2.wait_for_selector(".sc-body:visible .alert", timeout=6000)
        alert_txt = p2.locator(".sc-modal:visible .sc-body:visible .alert").inner_text()
        check(
            "проверка обновлений: статус-сообщение", len(alert_txt) > 5, alert_txt[:60]
        )

        real_errors = [e for e in errors if "favicon" not in e.lower()]
        check(
            "нет JS-ошибок в консоли",
            len(real_errors) == 0,
            ("; ".join(real_errors[:2]))[:160],
        )
        browser.close()

    print(f"\nE2E Часть 18: {len(PASS)} OK, {len(FAIL)} FAIL")
    if FAIL:
        print("Провалены:", FAIL)
finally:
    cleanup()
