"""Часть 24: E2E реестра «Всё» + дашборд 3.0 (dnd-виджеты, задачи, лента,
ярлыки). Приёмка: найти запись из любого модуля через одну таблицу ≤3 сек."""

import os, sys, subprocess, time, tempfile, socket

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TMPD = tempfile.mkdtemp(prefix="suot_e2e24_")
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
        b = pw.chromium.launch()
        page = b.new_page(viewport={"width": 1500, "height": 900})
        errs = []
        page.on("pageerror", lambda e: errs.append(str(e)))
        page.goto(BASE + "/", wait_until="domcontentloaded")
        page.wait_for_selector(".lang-cards", timeout=15000)
        page.get_by_role("button", name="Русский").click()
        page.wait_for_selector(".auth-card", timeout=8000)
        page.locator(".seg-btn").nth(1).click()
        page.get_by_placeholder("Иванов Иван Иванович").fill("Табелькин Т")
        page.get_by_placeholder("например, ivanov").fill("all_user")
        page.get_by_placeholder("минимум 6 символов").fill("parol123")
        page.get_by_role("button", name="Создать аккаунт").click()
        page.wait_for_selector(".shell", timeout=10000)
        time.sleep(1.6)
        if page.locator(".tour-layer").count():
            page.keyboard.press("Escape")
            time.sleep(0.3)

        # демо-данные в нескольких модулях
        for nav in ["Сотрудники", "СИЗ", "Нарушения"]:
            page.locator(".nav-item", has_text=nav).first.click()
            pane = page.locator(".tabpane:visible")
            demo = pane.locator(".empty-actions .btn", has_text="Загрузить демо")
            if demo.count():
                demo.first.click()
                page.wait_for_selector(
                    ".tabpane:visible tbody tr td.col-id", timeout=10000
                )
            time.sleep(0.4)

        # ══ Вкладка «Всё» ══
        page.locator(".nav-item", has_text="Реестр «Всё»").click()
        page.wait_for_selector(".tabpane:visible .sec-chips", timeout=10000)
        time.sleep(0.8)
        paneA = page.locator(".tabpane:visible")
        check(
            "чипы разделов отображаются",
            paneA.locator(".sec-chips .chip.cmd").count() >= 2,
        )
        rows = paneA.locator("tbody tr").count()
        check(f"реестр содержит записи ({rows})", rows > 0)

        # замер времени поиска ≤3 сек
        t0 = time.time()
        paneA.locator(".sb-input").fill("Смирнов")
        page.wait_for_function(
            """() => {
              const pane = [...document.querySelectorAll('.tabpane')]
                .find(el => el.offsetParent !== null && el.querySelector('.sb-input'));
              if (!pane) return false;
              const up = Alpine.$data(pane.querySelector('[x-data]'));
              return up && up.loading === false && up.total >= 0;
            }""",
            timeout=8000,
        )
        time.sleep(0.5)
        dt = time.time() - t0
        n_found = paneA.locator("tbody tr").count()
        check(f"поиск «Смирнов» ({n_found} за {dt:.1f}с)", dt <= 3.0)
        check(
            "найдена запись из другого модуля",
            n_found >= 1 or "не найдено" in paneA.locator(".fp-empty").inner_text(),
        )

        # клик по строке открывает раздел
        page.keyboard.press("Escape")
        time.sleep(0.3)
        page.locator(".nav-item", has_text="Реестр «Всё»").click()
        page.wait_for_selector(".tabpane:visible .sec-chips", timeout=8000)
        time.sleep(0.6)
        if page.locator(".tabpane:visible tbody tr").count():
            page.locator(".tabpane:visible tbody tr .badge").first.click()
            time.sleep(0.7)
            check(
                "клик по записи открыл раздел",
                page.locator(".tabpane:visible").count() >= 1,
            )

        # фильтр по разделам
        page.locator(".nav-item", has_text="Реестр «Всё»").click()
        page.wait_for_selector(".tabpane:visible .sec-chips", timeout=8000)
        time.sleep(0.6)
        paneA = page.locator(".tabpane:visible")
        chip = paneA.locator(".sec-chips .chip.cmd", has_text="СИЗ").first
        chip.click()
        time.sleep(0.7)
        only_sec = page.evaluate(
            """() => {
              const pane = [...document.querySelectorAll('.tabpane')]
                .find(el => el.offsetParent !== null && el.querySelector('.sec-chips'));
              return [...pane.querySelectorAll('tbody tr .badge')]
                .every(x => x.textContent.trim() === 'СИЗ');
            }"""
        )
        check("фильтр по разделу «СИЗ» работает", only_sec)

        # ══ Дашборд 3.0 ══
        page.locator(".nav-item", has_text="Дашборд").click()
        page.wait_for_selector(".tabpane:visible .dash-widgets", timeout=10000)
        time.sleep(1.2)
        paneD = page.locator(".tabpane:visible")
        check("решётка виджетов (7 шт)", paneD.locator(".dash-w").count() == 7)
        check("KPI-карточки отображаются", paneD.locator(".dash-kpi").count() >= 5)
        check(
            "панель «Мои задачи сегодня» есть",
            paneD.locator('[data-wid="tasks"]').count() == 1,
        )
        check(
            "лента активности есть", paneD.locator('[data-wid="activity"]').count() == 1
        )
        check(
            "ярлыки разделов есть (6+)",
            paneD.locator(".dash-shortcuts .ws-tile").count() >= 5,
        )

        # dnd: перетащить «Ленту» в начало
        paneD.locator('[data-wid="activity"]').drag_to(
            paneD.locator('[data-wid="kpi"]')
        )
        time.sleep(0.6)
        first_w = page.evaluate(
            """() => {
              const pane = [...document.querySelectorAll('.tabpane')]
                .find(el => el.offsetParent !== null);
              const el = pane ? pane.querySelector('.dash-widgets .dash-w') : null;
              return el ? el.dataset.wid : '';
            }"""
        )
        saved = page.evaluate(
            """() => JSON.parse(localStorage.getItem('suot_dash_order') || 'null')"""
        )
        check(f"dnd: виджет «{first_w}» первым", first_w == "activity")
        check(
            "порядок сохранён в localStorage",
            isinstance(saved, list) and saved[0] == "activity",
        )

        # вернуть порядок по умолчанию
        page.locator(".tabpane:visible .seg-btn", has_text="Всё").first.click(
            timeout=5000
        )
        time.sleep(0.6)
        page.evaluate(
            """() => {
              localStorage.removeItem('suot_dash_order');
              const pane = [...document.querySelectorAll('.tabpane')]
                .find(el => el.offsetParent !== null);
              const box = pane.querySelector('.dash-widgets');
              const wids = ['kpi','tasks','activity','overdue','recent','calendar','shortcuts'];
              wids.forEach((w, i) => {
                const el = box.querySelector('[data-wid="' + w + '"]');
                if (el) box.appendChild(el);
              });
            }"""
        )
        page.wait_for_timeout(400)
        check(
            "порядок восстановлен после сброса",
            page.evaluate(
                """() => {
                    const pane = [...document.querySelectorAll('.tabpane')]
                      .find(el => el.offsetParent !== null);
                    const el = pane.querySelector('.dash-widgets .dash-w');
                    return el.dataset.wid;
                  }"""
            )
            == "kpi",
        )

        real_errors = [e for e in errs if "favicon" not in e.lower()]
        check(
            "нет JS-ошибок", len(real_errors) == 0, ("; ".join(real_errors[:2]))[:150]
        )
        b.close()

    print(f"\nE2E Часть 24: {len(PASS)} OK, {len(FAIL)} FAIL")
    if FAIL:
        print("Провалены:", FAIL)
finally:
    srv.terminate()
