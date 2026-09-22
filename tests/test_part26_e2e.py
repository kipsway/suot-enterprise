"""Часть 26: E2E Правовая база. Открытие вкладки, фасетный поиск,
избранное, карточка с pravo.gov.ru, редактирование админом, импорт."""

import os, sys, subprocess, time, tempfile, socket

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TMPD = tempfile.mkdtemp(prefix="suot_e2e26_")
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
        page.locator(".seg-btn").nth(0).click()
        page.get_by_placeholder("например, ivanov").fill("admin")
        page.get_by_placeholder("минимум 6 символов").fill("admin")
        page.get_by_role("button", name="Войти").click()
        page.wait_for_selector(".shell", timeout=10000)
        time.sleep(1.6)
        if page.locator(".tour-layer").count():
            page.keyboard.press("Escape")
            time.sleep(0.3)

        # ══ Открыть вкладку «Правовая база» через палитру ══
        page.keyboard.press("Control+k")
        page.wait_for_selector(".palette-input", timeout=5000)
        page.locator(".palette-input").fill("правовая")
        time.sleep(0.4)
        page.keyboard.press("Enter")
        page.wait_for_selector(".npa-page", timeout=10000)
        time.sleep(1.2)
        pane = page.locator(".tabpane:visible")
        n_items = pane.locator(".npa-item").count()
        check(f"NPA вкладка открыта (карточек {n_items})", 10 <= n_items <= 70)

        # фаcеты загружены
        kinds = pane.locator(".npa-chip").count()
        check(f"чипсы фасетов загружены ({kinds})", kinds >= 10)

        # список НЕ пуст, мета «Всего»
        meta = pane.locator(".npa-meta").inner_text()
        check("счётчик Всего", "Всего" in meta and "70" in meta)

        # фасетный поиск (приёмка: мгновенный debounce-поиск)
        page.locator(".npa-q").fill("СИЗ")
        time.sleep(0.8)
        after_q = pane.locator(".npa-item").count()
        check(f"поиск 'СИЗ' → карточки {after_q}", after_q >= 1)

        # сброс поиска перед фасетом вида
        page.get_by_role("button", name="Сброс").click()
        time.sleep(0.8)
        # вид «приказ» фасетом
        pane.locator(".npa-chip", has_text="Приказы").first.click()
        time.sleep(0.8)
        pr_kind = pane.locator(".npa-item").count()
        check(f"фасет Приказы → карточек {pr_kind}", pr_kind >= 1)

        # карточка с ссылкой pravo.gov.ru
        first_card = pane.locator(".npa-item").first
        gov_href = first_card.locator(".npa-gov").get_attribute("href")
        check(
            "ссылка pravo.gov.ru в карточке",
            gov_href and "pravo.gov.ru" in gov_href,
            gov_href or "",
        )

        # открыть карточку → конспект/модалка
        first_card.locator(".npa-item-main").click()
        page.wait_for_selector(".npa-modal", timeout=5000)
        time.sleep(0.4)
        m_title = page.locator(".npa-modal-title").inner_text()
        check(f"карточка открылась ({m_title})", len(m_title) > 0)
        npa_btn = page.get_by_role("link", name="Открыть на pravo.gov.ru").first
        npa_link = npa_btn.get_attribute("href")
        check(
            "в карточке ссылка pravo.gov.ru",
            npa_link and "pravo.gov.ru" in npa_link,
            npa_link or "",
        )
        page.get_by_role("button", name="Закрыть").first.click()
        time.sleep(0.3)

        # избранное
        star = pane.locator(".npa-star").first
        star.click()
        time.sleep(0.6)
        page.locator(".npa-toolbar .btn", has_text="Избранное").click()
        time.sleep(0.8)
        fav_n = pane.locator(".npa-item").count()
        check(f"избранное: карточка в фильтре ({fav_n})", fav_n >= 1)
        page.locator(".npa-toolbar .btn", has_text="Избранное").click()
        time.sleep(0.5)

        # Отмена фасета Приказы, чтобы вернуть полный список
        pane.locator(".npa-chip.on").first.click()
        time.sleep(0.6)

        # редактирование (админ): открыть карточку, изменить конспект
        time.sleep(1.2)
        p_modal_before = page.locator(".npa-page .overlay").count()
        pane.locator(".npa-item-main").first.click()
        page.wait_for_selector(".npa-modal", timeout=8000)
        time.sleep(0.5)
        if not page.locator(".npa-modal .npa-notes:visible").count():
            check(
                "отладочная: модалка без notes",
                False,
                "overlay=" + str(p_modal_before) + " errs=" + str(errs),
            )
        page.locator(".npa-modal-acts .btn", has_text="Редактировать").click()
        page.wait_for_selector(".npa-notes-ta", timeout=5000)
        page.locator(".npa-notes-ta").fill("E2E конспект: требования к СИЗ.")
        page.locator(".npa-modal .btn.primary", has_text="Сохранить").click()
        page.wait_for_selector(".npa-modal", state="hidden", timeout=5000)
        time.sleep(0.5)
        # переоткрыть карточку и проверить сохранённый конспект
        pane.locator(".npa-item-main").first.click()
        page.wait_for_selector(".npa-modal .npa-notes", timeout=8000)
        notes_txt = page.locator(".npa-modal .npa-notes").inner_text()
        check("конспект сохранён", "E2E конспект" in notes_txt)
        page.get_by_role("button", name="Закрыть").first.click()
        time.sleep(0.3)

        # создание (админ)
        page.locator(".npa-toolbar .btn", has_text="Добавить").click()
        page.wait_for_selector(".npa-modal h3", timeout=5000)
        page.locator(".npa-modal input").first.fill("Тестовый документ E2E")
        page.locator(".npa-modal .btn.primary", has_text="Сохранить").click()
        page.wait_for_selector(".npa-modal", state="hidden", timeout=5000)
        time.sleep(0.9)
        page.locator(".npa-q").fill("Тестовый документ E2E")
        time.sleep(1.2)
        found_new = pane.locator(".npa-item", has_text="Тестовый документ E2E").count()
        check(f"созданный документ в поиске ({found_new})", found_new >= 1)
        page.locator(".npa-q").fill("")
        time.sleep(0.8)

        # импорт CSV (админ)
        page.locator(".npa-toolbar .btn", has_text="Импорт").click()
        page.wait_for_selector(".npa-imp-ta", timeout=5000)
        page.locator(".npa-imp-ta").fill(
            "постановление;E2E-1;Импортируемое постановление E2E;"
            "10.02.2026;действует;Обучение"
        )
        page.get_by_role("button", name="Импортировать").click()
        time.sleep(1.0)
        page.locator(".npa-q").fill("Импортируемое постановление E2E")
        time.sleep(0.8)
        imp_n = pane.locator(
            ".npa-item", has_text="Импортируемое постановление"
        ).count()
        check("импорт CSV виден", imp_n >= 1)
        page.locator(".npa-q").fill("")
        time.sleep(0.8)
        imp_n = pane.locator(
            ".npa-item", has_text="Импортируемое постановление"
        ).count()
        check("импортованная запись видна", imp_n >= 1)
        page.locator(".npa-q").fill("")
        time.sleep(0.8)

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

    print(f"\nE2E Часть 26: {len(PASS)} OK, {len(FAIL)} FAIL")
    if FAIL:
        print("Провалены:", FAIL)
finally:
    srv.terminate()
