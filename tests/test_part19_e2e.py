"""E2E-тест Части 19: плагины (тулбар/палитра/поведения) и бэкапы."""

import io, os, sys, subprocess, time, tempfile, socket, urllib.request, json

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

TMPD = tempfile.mkdtemp(prefix="suot_e2e19_")
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

        # Токен админа через API
        req = urllib.request.Request(
            BASE_URL + "/api/auth/login",
            data=json.dumps({"username": "admin", "password": "admin"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        adm_token = json.loads(urllib.request.urlopen(req).read())["token"]

        ctx = browser.new_context(viewport={"width": 1400, "height": 900})
        ctx.grant_permissions(["clipboard-read", "clipboard-write"])
        ctx.add_init_script("localStorage.setItem('suot_token', '%s');" % adm_token)
        errors = []
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on(
            "console", lambda m: errors.append(m.text) if m.type == "error" else None
        )

        page.goto(BASE_URL + "/", wait_until="domcontentloaded")
        page.wait_for_selector(".shell", timeout=15000)
        time.sleep(1.8)
        if page.locator(".tour-layer").count():
            page.keyboard.press("Escape")
            time.sleep(0.4)

        # ── Плагины в тулбаре таблицы ──
        page.locator(".nav-item", has_text="Сотрудники").click()
        page.wait_for_selector(".tabpane:visible table.grid", timeout=8000)
        time.sleep(0.8)
        # Часть 21: плагины переехали в меню «Ещё ▾»
        more_btn = page.locator(".tbl-toolbar .more-wrap > .btn")
        more_btn.click()
        time.sleep(0.3)
        more_items = page.locator(".more-pop .more-item")
        n_items = more_items.count()
        check(f"меню «Ещё»: пунктов ({n_items})", n_items >= 3, str(n_items))

        # Загрузим демо и выберем строки → copy_tsv из буфера
        pane = page.locator(".tabpane:visible")
        empty_demo = pane.locator(".empty-actions .btn", has_text="Загрузить демо")
        if empty_demo.count():
            empty_demo.first.click()
            page.wait_for_selector(".tabpane:visible tbody tr td.col-id", timeout=10000)
        time.sleep(0.6)
        rows_before = pane.locator("tbody tr").count()
        check(f"демо-строки ({rows_before})", rows_before > 0)

        # Выбираем 2 строки через чекбоксы
        boxes = pane.locator("tbody .cbx")
        for i in range(min(2, boxes.count())):
            boxes.nth(i).check()
            time.sleep(0.15)
        sel_cnt = page.evaluate(
            """(() => {
              const p = [...document.querySelectorAll('.tabpane')]
                .find(p => p.offsetParent !== null);
              const d = Alpine.$data(p.querySelector('[x-data]'));
              return d && d.selected ? d.selected.size : -1; })()"""
        )
        check(f"выбрано строк: {sel_cnt}", sel_cnt == 2)

        # copy_tsv через меню «Ещё ▾»
        more_btn.click()
        page.locator(".more-pop .more-item", has_text="Копировать как таблицу").click()
        page.wait_for_selector(".toast.success", timeout=6000)
        toast_txt = page.locator(".toast.success").last.inner_text()
        check(f"copy_tsv: {toast_txt}", "Скопировано" in toast_txt)

        clip_text = page.evaluate("navigator.clipboard.readText()")
        lines = [l for l in clip_text.strip().split("\n") if l]
        check(
            f"в буфере TSV ({len(lines)} строк)",
            len(lines) == 3 and "\t" in lines[0],
            lines[0][:60] if lines else "",
        )

        # overdue_label через меню «Ещё ▾»
        more_btn.click()
        page.locator(".more-pop .more-item", has_text="Просрочка").click()
        page.wait_for_selector(".toast.success", timeout=6000)
        lbl_toast = page.locator(".toast.success").last.inner_text()
        check(f"overdue_label: {lbl_toast}", "Просрочка" in lbl_toast)
        marked = page.locator(
            ".tabpane:visible tbody tr .lbl-red,.tabpane:visible tbody tr[class*='lbl']"
        )
        time.sleep(0.4)
        check("метки применились визуально", marked.count() >= 1, str(marked.count()))

        # ── Палитра содержит команды плагинов ──
        page.keyboard.press("Control+k")
        page.wait_for_selector(".palette:visible", timeout=5000)
        page.locator(".palette-input").fill("буфер")
        time.sleep(0.4)
        items = page.locator(".palette-item").count()
        check(f"палитра нашла команду плагина ({items})", items >= 1)
        page.keyboard.press("Escape")
        time.sleep(0.3)

        # ── Настройки → Данные: создание бэкапа ──
        page.locator(".statusbar-cmd").last.click()
        page.wait_for_selector(".sc-modal:visible", timeout=6000)
        page.locator(".sc-modal:visible .sc-tab", has_text="Данные").click()
        page.locator(".btn", has_text="Создать резервную копию").wait_for(timeout=5000)
        with page.expect_response(
            lambda r: r.url.endswith("/api/backup/create")
        ) as resp:
            page.locator(".btn", has_text="Создать резервную копию").click()
        time.sleep(0.8)
        blist = page.locator(".hk-row", has_text="manual_")
        check("бэкап появился в списке", blist.count() >= 1)

        # Предпросмотр состава
        blist.first.locator(".btn", has_text="Состав").click()
        page.wait_for_selector("text=Пользователей", timeout=5000)
        stats_txt = page.locator(".sc-body:visible .card", has_text="v2.2").inner_text()
        check(
            "предпросмотр: пользователи+таблицы",
            "Пользователей" in stats_txt and "employees" in stats_txt,
        )

        # Авто-бэкап переключение сохраняется
        page.locator(
            ".sc-body:visible .switch-row .seg button", has_text="Выкл"
        ).first.click()
        time.sleep(0.5)
        st = page.evaluate("""(() => {
          const d = Alpine.$data(document.querySelector(
            '[x-data*=\"backupCenter\"]'));
          return d.settings; })()""")
        check("авто-бэкап выкл сохранён", st["enabled"] is False)
        page.locator(
            ".sc-body:visible .switch-row .seg button", has_text="Вкл"
        ).first.click()
        time.sleep(0.5)

        # ── Вкладка Плагины: выключить quick-overdue → кнопка исчезла ──
        page.locator(".sc-modal:visible .sc-tab", has_text="Плагины").click()
        page.locator(".hk-row", has_text="Быстрая метка").wait_for(timeout=5000)
        row_plug = page.locator(".hk-row", has_text="Быстрая метка")
        row_plug.locator(".btn", has_text="Выключить").click()
        page.wait_for_selector(".toast.success", timeout=5000)
        time.sleep(0.6)
        check("toggle: бейдж «выключен»", row_plug.locator(".ua-badge").count() == 1)

        # Закрыть настройки, проверить что пункт плагина пропал из «Ещё»
        page.keyboard.press("Escape")
        time.sleep(0.4)
        page.locator(".tbl-toolbar .more-wrap > .btn").click()
        time.sleep(0.3)
        items_after = page.locator(".more-pop .more-item").count()
        check(
            f"после выключения пунктов в меню: {items_after}",
            items_after == n_items - 1,
        )
        page.keyboard.press("Escape")

        # Вернуть включённым
        page.locator(".statusbar-cmd").last.click()
        page.wait_for_selector(".sc-modal:visible", timeout=6000)
        page.locator(".sc-modal:visible .sc-tab", has_text="Плагины").click()
        row_plug = page.locator(".hk-row", has_text="Быстрая метка")
        row_plug.locator(".btn", has_text="Включить").click()
        time.sleep(0.7)
        page.keyboard.press("Escape")

        real_errors = [e for e in errors if "favicon" not in e.lower()]
        check(
            "нет JS-ошибок в консоли",
            len(real_errors) == 0,
            ("; ".join(real_errors[:2]))[:160],
        )
        browser.close()

    print(f"\nE2E Часть 19: {len(PASS)} OK, {len(FAIL)} FAIL")
    if FAIL:
        print("Провалены:", FAIL)
finally:
    cleanup()
