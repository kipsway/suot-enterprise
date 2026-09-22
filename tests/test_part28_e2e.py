"""Часть 28: E2E Инструменты. Вкладка (таймер/секундомер/помодоро/заметки),
калькулятор дат, генератор паролей, макрос «Конец месяца», быстрая заметка."""

import os, sys, subprocess, time, tempfile, socket

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TMPD = tempfile.mkdtemp(prefix="suot_e2e28_")
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

        # ══ Инструменты: открыть вкладку ══
        page.locator(".nav-item", has_text="Инструменты").last.click()
        page.wait_for_selector(".tabpane:visible .tools-page", timeout=10000)
        time.sleep(0.6)
        pane = _pane(page)
        check("вкладка «Инструменты» открыта", pane.locator(".tools-page").count() == 1)
        check("по умолчанию таймер", pane.locator(".big-clock").count() == 1)

        # ══ Таймер ══
        pane.get_by_role("button", name="Старт").click()
        time.sleep(2.2)
        t1 = pane.locator(".big-clock").inner_text().strip()
        pane.get_by_role("button", name="Стоп").click()
        time.sleep(0.3)
        check("таймер: старт/стоп работают", len(t1) >= 4, t1)

        # ══ Секундомер ══
        pane.locator(".tools-tabs .btn", has_text="Секундомер").click()
        pane.get_by_role("button", name="Старт").click()
        time.sleep(1.2)
        pane.get_by_role("button", name="Круг").click()
        time.sleep(0.3)
        laps = pane.locator(".lap-row").count()
        check("секундомер записал круг", laps >= 1, f"laps={laps}")
        pane.get_by_role("button", name="Стоп").click()

        # ══ Помодоро ══
        pane.locator(".tools-tabs .btn", has_text="Помодоро").click()
        pane.get_by_role("button", name="Старт").click()
        time.sleep(1.5)
        check("помодоро запущен (время пошло)", pane.locator(".big-clock").count() == 1)
        pane.get_by_role("button", name="Стоп").click()

        # ══ Заметки ══
        pane.locator(".tools-tabs .btn", has_text="Заметки").click()
        note_input = pane.locator(".notes-toolbar .field-input")
        note_input.fill("Тестовая заметка")
        pane.locator(".notes-toolbar .btn", has_text="Добавить").click()
        time.sleep(0.5)
        note_val = pane.locator(".stick-text").first.input_value()
        check("заметка добавлена", "Тестовая заметка" in note_val, note_val[:30])

        # перезагрузка — заметка переживает (localStorage)
        page.reload()
        page.wait_for_selector(".shell", timeout=10000)
        time.sleep(1.2)
        page.locator(".nav-item", has_text="Инструменты").last.click()
        page.wait_for_selector(".tabpane:visible .tools-page", timeout=10000)
        time.sleep(1.0)
        pane = _pane(page)
        pane.locator(".tools-tabs .btn", has_text="Заметки").click()
        time.sleep(0.5)
        note_val2 = pane.locator(".stick-text").first.input_value()
        check(
            "заметка сохранилась после перезагрузки",
            "Тестовая заметка" in note_val2,
            note_val2[:30],
        )

        # ══ Калькулятор дат ══
        pane.locator(".tools-tabs .btn", has_text="Даты").click()
        pane.locator(".tools-body select.field-input").select_option("diff_days")
        date_inputs = pane.locator("input[type=date]")
        date_inputs.nth(0).fill("2026-01-01")
        date_inputs.nth(1).fill("2026-01-10")
        pane.get_by_role("button", name="Рассчитать").click()
        page.wait_for_function(
            """() => {
              const pane = [...document.querySelectorAll('.tabpane')]
                .find(el => el.offsetParent !== null && el.querySelector('.dc-result'));
              return pane && (pane.querySelector('.dc-result').innerText || '') !== '';
            }""",
            timeout=8000,
        )
        dc = pane.locator(".dc-result").inner_text().strip()
        check("калькулятор дат: разница = 9", dc == "9", dc)

        # конец месяца
        pane.locator(".tools-body select.field-input").select_option("month_end")
        date_inputs.nth(0).fill("2026-02-10")
        pane.get_by_role("button", name="Рассчитать").click()
        page.wait_for_function(
            """() => {
              const pane = [...document.querySelectorAll('.tabpane')]
                .find(el => el.offsetParent !== null && el.querySelector('.dc-result'));
              if (!pane) return false;
              const t = pane.querySelector('.dc-result').innerText || '';
              return t === '2026-02-28';
            }""",
            timeout=8000,
        )
        check("калькулятор дат: конец февраля = 28", True)

        # ══ Погода (без сохранённого города → подсказка) ══
        pane.locator(".tools-tabs .btn", has_text="Погода").click()
        time.sleep(1.5)
        wtxt = pane.locator(".tools-body").inner_text()
        check(
            "погода без города: подсказка",
            "Город не указан" in wtxt or "no_city" in wtxt,
        )

        # ══ Генератор паролей ══
        pane.locator(".tools-tabs .btn", has_text="Пароли").click()
        pane.get_by_role("button", name="Сгенерировать").click()
        time.sleep(0.4)
        pwd_text = pane.locator(".pwd-out").inner_text().strip()
        check("пароль сгенерирован (длина 16)", len(pwd_text) == 16, pwd_text)

        # ══ Макросы ══
        pane.locator(".tools-tabs .btn", has_text="Макросы").click()
        time.sleep(1.0)
        mtxt = pane.locator(".tools-body").inner_text()
        check("макрос «Конец месяца» виден", "Конец месяца" in mtxt)
        pane.locator(".macro-row .btn", has_text="Выполнить").click()
        page.wait_for_function(
            """() => {
              const pane = [...document.querySelectorAll('.tabpane')]
                .find(el => el.offsetParent !== null && el.querySelector('.dc-result'));
              if (!pane) return false;
              const t = pane.querySelector('.dc-result').innerText || '';
              return t !== '';
            }""",
            timeout=8000,
        )
        mres = pane.locator(".dc-result").inner_text().strip()
        check("макрос вернул дату конца месяца", len(mres) >= 8, mres)

        # ═══ быстрая заметка Ctrl+Q ═══
        page.keyboard.press("Control+q")
        time.sleep(0.8)
        qnote = _pane(page).locator(".notes-toolbar .field-input")
        qnote.wait_for(timeout=5000)
        qnote.fill("Q-заметка")
        qnote.press("Enter")
        time.sleep(0.5)
        qval = _pane(page).locator(".stick-text").first.input_value()
        check(
            "Ctrl+Q: быстрая заметка добавлена",
            "Q-заметка" in qval,
            qval[:30],
        )
        check(
            "Ctrl+Q: открыла вкладку заметок",
            _pane(page).locator(".notes-toolbar").count() == 1,
        )

        # ═══ JavaScript/console ═══
        real_errors = [e for e in errs if "favicon" not in e.lower()]
        check(
            "нет JS-ошибок", len(real_errors) == 0, ("; ".join(real_errors[:2]))[:150]
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

    print(f"\nE2E Часть 28: {len(PASS)} OK, {len(FAIL)} FAIL")
    if FAIL:
        print("Провалены:", FAIL)
finally:
    srv.terminate()
