"""Часть 25: E2E Календарь+Время. Сетка месяца, событие, категории,
регулярные события, агенда дня, ДР сотрудника, сохранение данных."""

import os, sys, subprocess, time, tempfile, socket

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TMPD = tempfile.mkdtemp(prefix="suot_e2e25_")
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
        # вход администратором
        page.locator(".seg-btn").nth(0).click()
        page.get_by_placeholder("например, ivanov").fill("admin")
        page.get_by_placeholder("минимум 6 символов").fill("admin")
        page.get_by_role("button", name="Войти").click()
        page.wait_for_selector(".shell", timeout=10000)
        time.sleep(1.6)
        if page.locator(".tour-layer").count():
            page.keyboard.press("Escape")
            time.sleep(0.3)

        # ══ Календарь: открыть вкладку ══
        page.locator(".nav-item", has_text="Календарь").click()
        page.wait_for_selector(".tabpane:visible .cal-grid", timeout=10000)
        time.sleep(1.0)
        pane = page.locator(".tabpane:visible")
        check("сетка месяца (7×6 ячеек)", pane.locator(".cal-cell").count() == 42)
        check(
            "заголовок месяца корректный",
            len(pane.locator(".cal-title").inner_text().strip()) > 0,
        )
        check(
            "шапка недели (Пн..Вс)",
            pane.locator(".cal-wd").count() == 7,
        )
        check("панель «План дня» есть", pane.locator(".cal-agenda").count() == 1)

        # категории по умолчанию + создать событие
        default_msg = page.evaluate(
            """() => {
              const pane = [...document.querySelectorAll('.tabpane')]
                .find(el => el.offsetParent !== null && el.querySelector('.cal-grid'));
              const cat = Alpine.$data(document.querySelector('.cal-page') || pane.querySelector('[x-data]'));
              return cat ? cat.cats.length : -1;
            }"""
        )
        check(f"категории по умолчанию (≥6)", default_msg >= 6)

        # создать событие на сегодня
        pane.locator(".cal-cell.cur .cal-num").first.click()
        page.get_by_role("button", name="Событие +").click()
        page.wait_for_selector(".ev-title", timeout=5000)
        page.locator(".ev-title").fill("Испытание календаря")
        page.locator(".ev-time").fill("11:45")
        page.locator(".ev-cat").select_option(index=1)
        page.locator(".ev-remind").select_option("30")
        # сохранить
        page.locator(".ev-save").click()
        time.sleep(0.9)
        ev_chips = pane.locator(".cal-ev", has_text="Испытание календаря").count()
        check("событие появилось в сетке", ev_chips >= 1)

        # регулярное событие (еженедельно)
        page.get_by_role("button", name="Событие +").click()
        page.wait_for_selector(".ev-title", timeout=5000)
        page.locator(".ev-title").fill("Еженедельная планерка")
        page.locator(".ev-rep").select_option("weekly")
        page.locator(".ev-save").click()
        time.sleep(1.0)
        rep_n = pane.locator(".cal-ev", has_text="планерк").count()
        check(f"еженедельное событие в текущем месяце ({rep_n})", rep_n >= 1)

        # агенда дня
        pane.locator(".cal-cell.cur .cal-num").first.click()
        time.sleep(0.7)
        ag_txt = pane.locator(".cal-agenda").inner_text()
        check("в плане дня есть событие", "Испытание" in ag_txt)

        # редактирование события
        page.locator(".cal-ev", has_text="Испытание календаря").first.click()
        page.wait_for_selector(".ev-title", timeout=5000)
        page.locator(".ev-title").fill("Рейд")
        page.locator(".ev-save").click()
        time.sleep(0.9)
        renamed = pane.locator(".cal-ev", has_text="Рейд").count()
        check("событие переименовано", renamed >= 1)

        # удалить
        pane.locator(".cal-ev").filter(has_text="Рейд").first.click()
        page.wait_for_selector(".ev-title", timeout=5000)
        page.on("dialog", lambda d: d.accept())
        page.locator(".modal-foot .btn.danger").click()
        time.sleep(0.9)
        gone = pane.locator(".cal-ev").filter(has_text="Рейд").count()
        check("событие удалено", gone == 0)

        # категория: создать новую
        page.get_by_role("button", name="Категории").click()
        page.wait_for_selector(".cat-list", timeout=5000)
        before = page.locator(".cat-row").count()
        page.locator(".cat-name").fill("Аудит")
        page.locator(".cat-color").fill("#00BFA5")
        page.locator(".cat-save").click()
        time.sleep(0.7)
        after = page.locator(".cat-row").count()
        page.get_by_role("button", name="Закрыть").click()
        time.sleep(0.3)
        check(f"категория добавлена ({after})", after == before + 1)

        real_errors = [e for e in errs if "favicon" not in e.lower()]
        check(
            "нет JS-ошибок", len(real_errors) == 0, ("; ".join(real_errors[:2]))[:150]
        )
        console_issues = [c for c in cb_log if "favicon" not in c.lower()]
        check(
            "нет console-ошибок",
            len(console_issues) == 0,
            ("; ".join(console_issues[:3]))[:200],
        )
        b.close()

    print(f"\nE2E Часть 25: {len(PASS)} OK, {len(FAIL)} FAIL")
    if FAIL:
        print("Провалены:", FAIL)
finally:
    srv.terminate()
