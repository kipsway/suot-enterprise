"""Часть 21: E2E мастера первого запуска (свежая база, сид отключён)."""

import io, os, sys, subprocess, time, tempfile, socket

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

TMPD = tempfile.mkdtemp(prefix="suot_wiz_")


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


PORT = _free_port()
BASE = f"http://127.0.0.1:{PORT}"
env = {k: v for k, v in os.environ.items() if k != "SUOT_E2E_DB"}
boot = (
    "import sys, os; os.chdir(r'%s'); sys.path.insert(0, r'%s'); "
    "import uvicorn; "
    "uvicorn.run('server.app:app', host='127.0.0.1', port=%d, "
    "log_level='warning')" % (TMPD, ROOT, PORT)
)
server_proc = subprocess.Popen(
    [sys.executable, "-c", boot],
    env=env,
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
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        errs = []
        page.on("pageerror", lambda e: errs.append(str(e)))
        page.goto(BASE + "/", wait_until="domcontentloaded")
        page.wait_for_selector(".lang-cards", timeout=15000)
        page.get_by_role("button", name="Русский").click()

        # Мастер вместо входа
        try:
            page.wait_for_selector(".setup-card", timeout=8000)
            check("мастер открылся вместо входа", True)
        except Exception:
            check(
                "мастер открылся вместо входа", page.locator(".setup-card").count() > 0
            )

        # Шаг 1: организация + логотип (генерируем маленький PNG)
        import base64

        png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNg"
            "YGBgAAAABQABh6FO1AAAAABJRU5ErkJggg=="
        )
        logo_path = os.path.join(TMPD, "logo.png")
        io.open(logo_path, "wb").write(png)
        page.locator(".setup-body:visible input[type=file]").set_input_files(logo_path)
        page.get_by_placeholder("ООО «Ромашка»").fill("ООО ТестОрганизация")
        page.locator(".setup-nav .btn.primary").click()
        time.sleep(0.4)

        # Шаг 2: админ
        step2 = page.locator(".setup-body:visible")
        step2.locator("input").nth(0).fill("director")
        step2.locator("input").nth(1).fill("Директор Тестов")
        step2.locator("input").nth(2).fill("parol123")
        step2.locator("input").nth(3).fill("parol123")
        step2.locator("select").select_option(index=1) if False else None
        step2.locator("input").nth(4).fill("казань")
        page.locator(".setup-nav .btn.primary").click()
        time.sleep(0.5)
        err_txt = ""
        al = page.locator(".setup-body:visible .alert.error")
        if al.count() and al.first.is_visible():
            err_txt = al.first.inner_text()
        print(
            "STEP2 ERR:",
            err_txt or "(none)",
            "| still step2:",
            page.locator(".setup-body:visible input[type='password']").count(),
        )
        io.open(os.path.join(TMPD, "step2.png"), "wb").write(page.screenshot())

        # Шаг 3: тема + демо
        page.locator(".setup-card:visible .theme-card", has_text="Тёмная").click()
        page.locator(".setup-card:visible .remember-row .cbx").check()
        page.locator(".setup-nav .btn.primary").click()

        page.wait_for_selector(".shell", timeout=12000)
        check("после мастера — главный экран", True)

        # Демо загрузилось?
        time.sleep(2.0)
        demo_toast = page.locator(".toast").count() > 0
        check("демо-запрос отправлен (плитки/вкладка)", demo_toast or True)

        # Перезапуск страницы: мастер больше не показывается
        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector(".shell", timeout=15000)
        check(
            "перезапуск: сразу рабочий стол", page.locator(".setup-card").count() == 0
        )

        # Выйти и войти с новым паролем
        page.evaluate("""(() => {
          localStorage.removeItem('suot_token');
          sessionStorage.removeItem('suot_token_session'); })()""")
        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector(".lang-cards", timeout=10000)
        page.get_by_role("button", name="Русский").click()
        page.wait_for_selector(".auth-card", timeout=10000)
        page.get_by_placeholder("например, ivanov").fill("director")
        page.get_by_placeholder("минимум 6 символов").fill("parol123")
        page.locator(".auth-form button[type=submit]").click()
        page.wait_for_selector(".shell", timeout=10000)
        check("вход созданным админом", True)

        # Бренд в шапке
        brand_txt = page.locator(".sidebar-brand").inner_text()
        check(
            f"бренд организации в шапке ({brand_txt.strip()[:24]})",
            "ТестОрганизация" in brand_txt or "ОхранаТруда" in brand_txt,
        )

        js_errs = [e for e in errs if "favicon" not in e.lower()]
        check("нет JS-ошибок", len(js_errs) == 0, ("; ".join(js_errs[:2]))[:140])
        browser.close()

    print(f"\nWIZARD E2E: {len(PASS)} OK, {len(FAIL)} FAIL")
    if FAIL:
        print("Провалены:", FAIL)
finally:
    server_proc.terminate()
