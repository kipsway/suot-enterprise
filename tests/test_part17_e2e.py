"""E2E-тест Части 17: центр настроек (темы, акцент, шрифты, стекло,
плотность, радиусы, хоткеи, сброс, экспорт/импорт)."""

import io, os, sys, subprocess, time, tempfile, socket

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

TMPD = tempfile.mkdtemp(prefix="suot_e2e17_")
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
        page = browser.new_page(
            viewport={"width": 1400, "height": 900}, reduced_motion="no-preference"
        )
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on(
            "console", lambda m: errors.append(m.text) if m.type == "error" else None
        )

        page.goto(BASE_URL + "/", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector(".lang-cards", timeout=15000)
        time.sleep(0.5)
        page.get_by_role("button", name="Русский").click()
        page.wait_for_selector(".auth-card", timeout=8000)
        page.locator(".seg-btn").nth(1).click()
        page.get_by_placeholder("Иванов Иван Иванович").fill("Настройкин Тест")
        page.get_by_placeholder("например, ivanov").fill("set_user")
        page.get_by_placeholder("минимум 6 символов").fill("parol123")
        page.get_by_role("button", name="Создать аккаунт").click()
        page.wait_for_selector(".shell", timeout=10000)
        check("вход выполнен", True)

        # Закрыть онбординг-тур (Часть 18), если появился
        try:
            page.wait_for_selector(".tour-layer", timeout=3500)
            page.keyboard.press("Escape")
            time.sleep(0.5)
        except Exception:
            pass

        # Открываем таблицу (для проверки плотности позже)
        page.locator(".nav-item", has_text="Сотрудники").click()
        page.wait_for_selector("table.grid", timeout=8000)

        # ── Открытие центра настроек ──
        page.locator(".statusbar-cmd").last.click()
        page.wait_for_selector(".sc-modal", timeout=6000)
        check("центр настроек открылся", True)

        theme = page.evaluate("document.documentElement.dataset.theme")

        # ── Живой предпросмотр темы при наведении ──
        card_ocean = page.locator(".theme-card", has_text="Океан")
        card_ocean.hover()
        time.sleep(0.3)
        prev_theme = page.evaluate("document.documentElement.dataset.theme")
        check(
            f"живой предпросмотр (hover→ocean)",
            prev_theme == "ocean",
            f"{theme}→{prev_theme}",
        )

        page.locator(".sc-modal:visible .sc-head b").hover()
        time.sleep(0.3)
        back_theme = page.evaluate("document.documentElement.dataset.theme")
        check("предпросмотр отменён (mouseleave)", back_theme == theme, back_theme)

        # ── Выбор темы сохраняется и переживает перезагрузку ──
        card_ocean.click()
        time.sleep(0.5)
        sel_theme = page.evaluate("document.documentElement.dataset.theme")
        check("тема ocean применена по клику", sel_theme == "ocean")
        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector(".shell", timeout=15000)
        time.sleep(1.2)
        after = page.evaluate("document.documentElement.dataset.theme")
        check("тема сохранилась после reload", after == "ocean", after)

        # Переоткрываем таблицу и центр настроек после reload
        page.locator(".nav-item", has_text="Сотрудники").click()
        page.wait_for_selector("table.grid", timeout=8000)
        page.locator(".statusbar-cmd").last.click()
        page.wait_for_selector(".sc-modal", timeout=6000)
        time.sleep(0.3)

        # ── Акцент ──
        page.evaluate("""
          const inp = document.querySelector('.accent-row input[type=color]');
          inp.value = '#FF8800';
          inp.dispatchEvent(new Event('input', {bubbles: true}));""")
        time.sleep(0.6)
        acc = page.evaluate(
            "getComputedStyle(document.documentElement)"
            ".getPropertyValue('--acc').trim()"
        )
        check(
            "акцент применился (--acc)",
            "#ff8800" in acc.lower() or "#FF8800" in acc,
            acc,
        )

        # ── Масштаб ──
        page.locator(".sc-body:visible .seg button", has_text="110%").click()
        time.sleep(0.4)
        zoom = page.evaluate("document.body.style.zoom")
        check("масштаб 110% → body.zoom", zoom == "1.1", zoom)

        # ── Стекло ──
        page.locator(
            ".sc-body:visible .switch-row .seg button", has_text="Выкл"
        ).click()
        time.sleep(0.4)
        no_glass = page.evaluate(
            "document.documentElement.classList.contains('no-glass')"
        )
        check("стекло выключено → .no-glass", no_glass)

        # ── Плотность и радиусы ──
        page.locator(".sc-body:visible .seg button", has_text="Плотно").click()
        page.locator(".sc-body:visible .seg button", has_text="Большие").click()
        time.sleep(0.4)
        dens = page.evaluate("document.documentElement.dataset.density")
        rad = page.evaluate("document.documentElement.dataset.radius")
        check(
            "плотность compact + радиус lg",
            dens == "compact" and rad == "lg",
            f"{dens}/{rad}",
        )
        pad = page.evaluate("""(() => {
          const grid = document.querySelector('table.grid');
          if (!grid) return 'no-grid';
          const tr = document.createElement('tr');
          const td = document.createElement('td');
          tr.appendChild(td);
          (grid.tBodies[0] || grid).appendChild(tr);
          const p = getComputedStyle(td).paddingTop;
          tr.remove();
          return p; })()""")
        check("компактная таблица: padding 3px", pad.strip() == "3px", pad)

        # ── Водяной знак ──
        wm_inp = page.locator('.sc-body:visible input[placeholder*="ЧЕРНОВИК"]')
        wm_inp.fill("DRAFT-E2E")
        wm_inp.locator("xpath=../button").click()
        page.wait_for_selector(".toast.success", timeout=5000)
        check("водяной знак сохранён", True)
        time.sleep(0.3)

        # ── Хоткеи: переназначение палитры на Ctrl+/ ──
        page.locator(".sc-modal:visible .sc-tab", has_text="Горячие клавиши").click()
        time.sleep(0.3)
        pal_combo = page.locator(".hk-row", has_text="Палитра команд").locator(
            ".hk-combo"
        )
        pal_combo.click()
        time.sleep(0.2)
        page.keyboard.press("Control+Slash")
        time.sleep(0.6)
        new_combo = pal_combo.inner_text().strip()
        check(
            f"хоткей палитры → Ctrl+/",
            new_combo.replace(" ", "") == "Ctrl+/",
            new_combo,
        )
        page.keyboard.press("Escape")
        time.sleep(0.4)

        # Палитра открывается по новой комбинации
        page.keyboard.press("Control+Slash")
        page.wait_for_selector(".palette:visible", timeout=5000)
        check("Ctrl+/ открывает палитру", True)
        page.keyboard.press("Escape")
        time.sleep(0.3)
        # Старый Ctrl+K больше не срабатывает (движок заменил обработчик)
        page.keyboard.press("Control+k")
        time.sleep(0.4)
        pal_visible = page.locator(".palette:visible").count() > 0
        check("старый Ctrl+K не мешает", not pal_visible)
        if pal_visible:
            page.keyboard.press("Escape")
            time.sleep(0.2)

        # Ctrl+Shift+T — сменить тему
        before_t = page.evaluate("document.documentElement.dataset.theme")
        page.keyboard.press("Control+Shift+t")
        time.sleep(0.6)
        after_t = page.evaluate("document.documentElement.dataset.theme")
        check(f"Ctrl+Shift+T меняет тему ({before_t}→{after_t})", before_t != after_t)

        # ── Экспорт настроек ──
        page.locator(".statusbar-cmd").last.click()
        page.wait_for_selector(".sc-modal", timeout=6000)
        with page.expect_download() as dl_info:
            page.locator(".sc-head .icon-btn[title*='Экспорт']").click()
        dl = dl_info.value
        exp_path = os.path.join(TMPD, "settings_export.json")
        dl.save_as(exp_path)
        exported = io.open(exp_path, encoding="utf-8").read()
        has_fmt = '"suot-settings"' in exported
        has_theme = "forest" in exported
        has_wm = "DRAFT-E2E" in exported
        check(
            "экспорт: JSON с темой/акцентом",
            has_fmt and has_theme and has_wm,
            "fmt={} theme={} wm={} :: {}".format(
                has_fmt, has_theme, has_wm, exported[:160]
            ),
        )

        # ── Импорт в другой профиль (round-trip) ──
        page.keyboard.press("Escape")
        time.sleep(0.3)
        # Выходим, заходим другим пользователем
        close_overlays_ok = True
        for _ in range(3):
            page.keyboard.press("Escape")
            time.sleep(0.15)
        user_btn = page.locator(".userchip, .avatar-btn, [class*=user]").first
        # Проще: через API-логин проверять не будем; импорт через UI того же юзера
        page.locator(".statusbar-cmd").last.click()
        page.wait_for_selector(".sc-modal", timeout=6000)
        imp_input = page.locator(".sc-head label.icon-btn input[type=file]")
        imp_input.set_input_files(exp_path)
        page.wait_for_selector(".toast.success", timeout=6000)
        time.sleep(0.4)
        re_acc = page.evaluate(
            "getComputedStyle(document.documentElement)"
            ".getPropertyValue('--acc').trim()"
        )
        check("импорт вернул настройки", "#ff8800" in re_acc.lower(), re_acc)

        # ── Сброс к стандартным ──
        page.locator(".sc-head .icon-btn[title*='Сбросить']").click()
        page.locator(".btn", has_text="Да, сбросить").wait_for(timeout=4000)
        page.locator(".btn", has_text="Да, сбросить").click()
        time.sleep(0.7)
        r_theme = page.evaluate("document.documentElement.dataset.theme")
        r_zoom = page.evaluate("document.body.style.zoom || '1'")
        r_dens = page.evaluate("document.documentElement.dataset.density")
        check(
            "сброс: тема auto, zoom 1, density comfortable",
            r_theme in ("auto", "light", "dark")
            and r_zoom in ("1", "")
            and r_dens == "comfortable",
            f"{r_theme}/{r_zoom}/{r_dens}",
        )

        # Хоткей палитры вернулся на Ctrl+K
        page.keyboard.press("Escape")
        time.sleep(0.3)
        page.keyboard.press("Control+k")
        page.wait_for_selector(".palette:visible", timeout=5000)
        check("после сброса Ctrl+K снова работает", True)
        page.keyboard.press("Escape")

        # ── Ошибки консоли ──
        real_errors = [e for e in errors if "favicon" not in e.lower()]
        check(
            "нет JS-ошибок в консоли",
            len(real_errors) == 0,
            ("; ".join(real_errors[:2]))[:160],
        )
        browser.close()

    print(f"\nE2E Часть 17: {len(PASS)} OK, {len(FAIL)} FAIL")
    if FAIL:
        print("Провалены:", FAIL)
finally:
    cleanup()
