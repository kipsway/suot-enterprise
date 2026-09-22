"""Часть 27: E2E AI-центр. Треды (история диалогов), переименование/удаление,
инсайты, ping-статус провайдера, агент с предпросмотром diff."""

import os, sys, subprocess, time, tempfile, socket

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TMPD = tempfile.mkdtemp(prefix="suot_e2e27_")
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


def _alt_lang(page):
    """Открыть AI-вкладку: кнопка в сайдбаре."""
    page.locator(".nav-item", has_text="AI-ассистент").first.click()


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

        # ══ AI-центр: открыть вкладку ══
        page.locator(".nav-item", has_text="AI-ассистент").first.click()
        page.wait_for_selector(".tabpane:visible .ai-center", timeout=10000)
        time.sleep(1.0)
        pane = page.locator(".tabpane:visible")
        check("AI-центр открыт (макет тредов)", pane.locator(".ai-side").count() == 1)
        check(
            "поле сообщений есть",
            pane.locator(".ai-messages").count() == 1,
        )

        # ══ Треды ══
        # пустой список
        empty_note = pane.locator(".ai-thread-list").inner_text()
        check("список тредов пуст (подсказка)", "Диалогов пока нет" in empty_note)

        # создать тред
        thread_input = pane.locator(".ai-side > .field-input")
        thread_input.fill("Стаж работников")
        pane.locator(".ai-side-head .btn", has_text="Новый").click()
        time.sleep(0.9)
        threads_txt = pane.locator(".ai-thread-list").inner_text()
        check("тред создан (виден в списке)", "Стаж работников" in threads_txt)

        # ══ Инсайты по разделу ══
        pane.locator(".ai-head .btn", has_text="Инсайты по разделу").click()
        page.wait_for_function(
            """() => {
              const pane = [...document.querySelectorAll('.tabpane')]
                .find(el => el.offsetParent !== null && el.querySelector('.ai-messages'));
              if (!pane) return false;
              const msgs = [...pane.querySelectorAll('.ai-msg.assistant')]
                .filter(el => el.offsetParent !== null);
              const last = msgs[msgs.length - 1];
              return !!last && !!last.innerText.trim();
            }""",
            timeout=15000,
        )
        ai_txt = pane.locator(".ai-messages").inner_text()
        check("инсайты: запрос добавлен в чат", "инсайт" in ai_txt.lower())
        # LLM недоступен → ассистент отвечает ошибкой, но сообщение user записано
        check(
            "инсайты: ассистент дал ответ (текст)",
            "Покажи инсайты" in ai_txt or "Недоступен" in ai_txt or "⚠" in ai_txt,
        )

        # ══ Настройки + ping ══
        pane.locator(".ai-head .btn", has_text="Настройки").click()
        time.sleep(0.5)
        pane.locator(".ai-settings .btn", has_text="Проверить статус").click()
        page.wait_for_function(
            """() => {
              const pane = [...document.querySelectorAll('.tabpane')]
                .find(el => el.offsetParent !== null && el.querySelector('.ai-settings'));
              if (!pane) return false;
              return (pane.querySelector('.ai-settings').innerText || '')
                .includes('Недоступен');
            }""",
            timeout=8000,
        )
        set_txt = pane.locator(".ai-settings").inner_text()
        check("ping: статус показан (недоступен)", "Недоступен" in set_txt)

        # закрыть настройки
        pane.locator(".ai-head .btn", has_text="Настройки").click()
        time.sleep(0.4)

        # ══ Переименование треда ══
        thread_el = pane.locator(".ai-thread", has_text="Стаж работников").first
        thread_el.locator(".btn", has_text="Переименовать").click()
        time.sleep(0.3)
        re_input = pane.locator(".ai-thread .field-input").first
        re_input.fill("Стаж работников v2")
        pane.locator(".ai-thread .btn.primary", has_text="ОК").click()
        page.wait_for_function(
            """() => {
              const pane = [...document.querySelectorAll('.tabpane')]
                .find(el => el.offsetParent !== null && el.querySelector('.ai-thread-list'));
              if (!pane) return false;
              return (pane.querySelector('.ai-thread-list').innerText || '')
                .includes('Стаж работников v2');
            }""",
            timeout=8000,
        )
        threads_txt2 = pane.locator(".ai-thread-list").inner_text()
        check("тред переименован", "Стаж работников v2" in threads_txt2)

        # ══ Сохранение через чат: история остаётся ══
        # отправка сообщения без подписки на stream — завершится error, но user-сообщение останется в треде

        # ══ Агент: diff не вызываем без LLM, кнопка доступна ══
        agent_btn = pane.locator(".ai-input-row .btn", has_text="Агент").count()
        check("кнопка «Агент» есть", agent_btn == 1)

        # ══ Удаление треда ══
        page.on("dialog", lambda d: d.accept())
        del_thread = pane.locator(".ai-thread", has_text="Стаж работников v2").first
        del_thread.locator(".btn", has_text="Удалить").click()
        time.sleep(0.9)
        threads_txt3 = pane.locator(".ai-thread-list").inner_text()
        check("тред удалён", "Стаж работников" not in threads_txt3)
        noleft = "Диалогов пока нет" in threads_txt3
        check("список снова пуст", noleft)

        # ══ Проверка журнала: диалог пережил переименование до удаления? ══
        # (сохранение в БД уже покрыто server-тестом)

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

    print(f"\nE2E Часть 27: {len(PASS)} OK, {len(FAIL)} FAIL")
    if FAIL:
        print("Провалены:", FAIL)
finally:
    srv.terminate()
