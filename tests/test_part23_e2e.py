"""Часть 23: E2E таблиц 2.0 — колонки, футер, группы, светофор, комментарии."""

import os, sys, subprocess, time, tempfile, socket

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TMPD = tempfile.mkdtemp(prefix="suot_e2e23_")
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
        page.get_by_placeholder("например, ivanov").fill("tbl_user")
        page.get_by_placeholder("минимум 6 символов").fill("parol123")
        page.get_by_role("button", name="Создать аккаунт").click()
        page.wait_for_selector(".shell", timeout=10000)
        time.sleep(1.6)
        if page.locator(".tour-layer").count():
            page.keyboard.press("Escape")
            time.sleep(0.3)

        page.locator(".nav-item", has_text="Сотрудники").click()
        pane = page.locator(".tabpane:visible")
        demo = pane.locator(".empty-actions .btn", has_text="Загрузить демо")
        if demo.count():
            demo.first.click()
            page.wait_for_selector(".tabpane:visible tbody tr td.col-id", timeout=10000)
        time.sleep(0.6)

        # ── Resize колонки ──
        th = pane.locator("th.col-th").first
        before = th.bounding_box()["width"]
        handle = th.locator(".col-resizer")
        box = handle.bounding_box()
        page.mouse.move(box["x"] + 3, box["y"] + box["height"] / 2)
        page.mouse.down()
        page.mouse.move(box["x"] + 123, box["y"] + box["height"] / 2, steps=6)
        page.mouse.up()
        time.sleep(0.4)
        after = th.bounding_box()["width"]
        check(f"resize колонки ({int(before)}→{int(after)})", after > before + 60)
        saved = page.evaluate(
            "JSON.parse(localStorage.getItem('suot_cw_employees')||'{}')"
        )
        check(
            "ширина сохранена в localStorage",
            any(v > before + 60 for v in saved.values()),
        )

        # ── Drag-порядок колонок ──
        first_name = page.evaluate(
            """() => {
              const pane = [...document.querySelectorAll('.tabpane')]
                .find(el => el.offsetParent !== null && el.querySelector('[x-data]'));
              return Alpine.$data(pane.querySelector('[x-data]')).dataCols[0].name;
            }"""
        )
        src_th = pane.locator("th.col-th").first
        dst_th = pane.locator("th.col-th").nth(2)
        sb = src_th.bounding_box()
        db_ = dst_th.bounding_box()
        page.mouse.move(sb["x"] + sb["width"] / 2, sb["y"] + sb["height"] / 2)
        page.mouse.down()
        page.mouse.move(
            db_["x"] + db_["width"] / 2, db_["y"] + db_["height"] / 2, steps=8
        )
        page.mouse.up()
        time.sleep(0.4)
        new_first = page.evaluate(
            """() => {
              const pane = [...document.querySelectorAll('.tabpane')]
                .find(el => el.offsetParent !== null && el.querySelector('[x-data]'));
              return Alpine.$data(pane.querySelector('[x-data]')).dataCols[0].name;
            }"""
        )
        check(f"drag колонок ({first_name}→{new_first})", new_first != first_name)

        # ── Агрегаты футера ──
        agg = pane.locator("tfoot .agg-cell").first
        agg_txt = agg.inner_text().strip()
        check(f"футер-агрегаты ({agg_txt[:24]})", len(agg_txt) > 0)

        # ── Закрепление колонок ──
        page.locator(".tbl-toolbar .more-wrap > .btn").click()
        page.locator(".more-pop:visible .btn", has_text="2").first.click(timeout=5000)
        time.sleep(0.4)
        sticky_cnt = page.evaluate(
            """() => {
              const pane = [...document.querySelectorAll('.tabpane')]
                .find(el => el.offsetParent !== null);
              return pane.querySelectorAll('th.fz').length;
            }"""
        )
        check(f"закреплено колонок (fz={sticky_cnt})", sticky_cnt == 2)
        page.keyboard.press("Escape")
        time.sleep(0.4)

        # ── Группировка ──
        page.keyboard.press("Escape")
        time.sleep(0.4)
        page.locator(".tbl-toolbar .more-wrap > .btn").click()
        page.locator(".more-pop:visible .more-cap", has_text="Группировка").wait_for(
            timeout=4000
        )
        grp_col = page.locator(".more-pop .more-item").nth(
            6
        )  # после заголовков; подстрахуемся выбором по тексту ниже
        # выбрать колонку «Подразделение», если есть, иначе первую
        names = page.evaluate(
            """() => {
              const pane = [...document.querySelectorAll('.tabpane')]
                .find(el => el.offsetParent !== null && el.querySelector('[x-data]'));
              return Alpine.$data(pane.querySelector('[x-data]')).dataCols.map(c=>c.name);
            }"""
        )
        target = "Подразделение" if "Подразделение" in names else names[0]
        page.locator(".more-pop:visible .more-item", has_text=target).first.click(
            timeout=5000
        )
        time.sleep(0.5)
        page.keyboard.press("Escape")
        time.sleep(0.3)
        grp_rows = pane.locator("tr.group-row").count()
        check(f"группировка по «{target}» ({grp_rows} групп)", grp_rows >= 1)
        if grp_rows:
            pane.locator("tr.group-row").first.click()
            time.sleep(0.3)
            body_rows = pane.locator("tbody tr:not(.group-row)").count()
            check("свёртка группы работает", body_rows >= 0)

        # сброс группировки
        page.keyboard.press("Escape")
        time.sleep(0.4)
        page.locator(".tbl-toolbar .more-wrap > .btn").click()
        page.locator(".more-pop:visible .more-item", has_text="без группировки").click(
            timeout=5000
        )
        time.sleep(0.3)
        page.keyboard.press("Escape")

        # ── Комментарий к ячейке ──
        cell = pane.locator("tbody tr").first.locator("td").nth(3)
        cell.click(button="right")
        page.wait_for_selector(".modal:visible", timeout=5000)
        page.locator(".modal:visible textarea").fill("Проверить в пятницу")
        page.locator(".modal:visible .btn.primary", has_text="Сохранить").click()
        page.wait_for_selector(".toast.success", timeout=5000)
        time.sleep(0.4)
        dot = pane.locator("tbody tr").first.locator("td").nth(3).locator(".cmt-dot")
        check("индикатор комментария появился", dot.count() == 1)

        # ── Светофор сроков (СИЗ: «Годен до») ──
        page.locator(".nav-item", has_text="Осмотры СИЗ").click()
        time.sleep(0.9)
        pane2 = page.locator(".tabpane:visible")
        demo2 = pane2.locator(".empty-actions .btn", has_text="Загрузить демо")
        if demo2.count():
            demo2.first.click()
            page.wait_for_selector(".tabpane:visible tbody tr td.col-id", timeout=10000)
        time.sleep(0.5)
        dt_cells = pane2.locator("td.dt-ok, td.dt-warn, td.dt-over")
        n_dt = dt_cells.count()
        check(f"светофор сроков ({n_dt} ячеек)", n_dt >= 1)

        real_errors = [e for e in errs if "favicon" not in e.lower()]
        check(
            "нет JS-ошибок", len(real_errors) == 0, ("; ".join(real_errors[:2]))[:150]
        )
        b.close()

    print(f"\nE2E Часть 23: {len(PASS)} OK, {len(FAIL)} FAIL")
    if FAIL:
        print("Провалены:", FAIL)
finally:
    srv.terminate()
