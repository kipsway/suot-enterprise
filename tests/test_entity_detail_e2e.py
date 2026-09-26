"""E2E SUOT Next Блок 2: Entity Registry + Detail Workspace.
Дескрипторы, досье (поля/заметки/связи/история), настоящий rollback,
вход из старой панели и через контекст реестра, RU, ноль JS-ошибок."""

import json
import os
import sys
import subprocess
import time
import tempfile
import socket

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

TMPD = tempfile.mkdtemp(prefix="suot_ent2_")
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


def _api(method, path, token="", body=None):
    conn = http.client.HTTPConnection("127.0.0.1", PORT, timeout=10)
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    conn.request(method, path, json.dumps(body) if body is not None else None, headers)
    resp = conn.getresponse()
    data = resp.read().decode("utf-8", "replace")
    conn.close()
    return resp.status, json.loads(data) if data else {}


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

st, login = _api(
    "POST", "/api/auth/login", "", {"username": "admin", "password": "admin"}
)
TOKEN = login.get("token", "") if st == 200 else ""

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
        ctx = browser.new_context(viewport={"width": 1400, "height": 900})
        ctx.add_init_script(f"localStorage.setItem('suot_token', '{TOKEN}');")
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(BASE_URL + "/", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector(".shell", timeout=15000)
        check("вход по токену", True)
        try:
            page.wait_for_selector(".tour-layer", timeout=3500)
            page.keyboard.press("Escape")
            time.sleep(0.5)
        except Exception:
            pass

        # Entity Registry: дескрипторы
        ent = page.evaluate("""() => {
            const E = window.SUOT_ENTITIES;
            if (!E) return null;
            const emp = E.descriptor('employees');
            return {
                empKind: emp.kind,
                empTitle: E.titleOf(emp, {data: {'ФИО': 'Иван'}}),
                customKind: E.descriptor('u_abc').kind,
                structKind: E.descriptor('capa').kind,
                structNotes: E.descriptor('capa').notes,
                urlJson: E.recordUrl(emp, 5),
                urlCustom: E.recordUrl(E.descriptor('u_abc'), 7),
                urlNone: E.recordUrl(E.descriptor('capa'), 7),
            };
        }""")
        check("entities загружен", ent is not None)
        check("дескриптор employees", ent["empKind"] == "json", ent["empKind"])
        check("title по ФИО", ent["empTitle"] == "Иван", ent["empTitle"])
        check(
            "custom/structured kinds",
            ent["customKind"] == "custom"
            and ent["structKind"] == "none"
            and ent["structNotes"] is False,
        )
        check(
            "URL записей",
            ent["urlJson"] == "/data/employees/5"
            and ent["urlCustom"] == "/custom/record/u_abc/7"
            and ent["urlNone"] == "",
        )

        # Записи через API
        st1, r1 = _api(
            "POST",
            "/api/data/employees",
            TOKEN,
            {"data": {"ФИО": "Досье Тест", "Должность": "Инженер"}},
        )
        st2, r2 = _api(
            "POST", "/api/data/employees", TOKEN, {"data": {"ФИО": "Связанный Человек"}}
        )
        rid, rid2 = r1.get("id"), r2.get("id")
        check("записи созданы", st1 == 201 and st2 == 201, f"{rid}/{rid2}")

        # Досье через событие
        page.evaluate(
            "() => document.dispatchEvent(new CustomEvent('suot-detail-open',"
            + " {bubbles: true, detail: {table: 'employees', id: "
            + str(rid)
            + "}}))"
        )
        page.wait_for_selector(".dt-overlay:visible", timeout=8000)
        # Заголовок виден только после загрузки данных — ждём его, иначе гонка
        page.wait_for_selector(".dt-title-main:visible", timeout=8000)
        title = page.locator(".dt-title-main").inner_text()
        check("досье открылось с именем", "Досье Тест" in title, title[:60])
        # Поля рендерятся тем же блоком; читаем в цикле — вердикт по факту,
        # а не по одному мгновенному чтению (рендер может догонять)
        fields_ok = False
        body_txt = ""
        for _ in range(6):
            try:
                body_txt = page.locator(".dt-panel").inner_text()
            except Exception:
                body_txt = ""
            if "Инженер" in body_txt:
                fields_ok = True
                break
            time.sleep(1.0)
        check("поля видны", fields_ok and "Инженер" in body_txt)
        check("шапка Досье", "Досье" in body_txt)

        # Заметки
        page.locator(".dt-tab", has_text="Заметки").click()
        page.locator(".dt-panel input[type=text]").fill("План проверки")
        page.locator(".dt-panel textarea").fill("Проверить СИЗ до пятницы")
        page.get_by_role("button", name="Добавить заметку").click()
        page.locator(".dt-panel", has_text="План проверки").wait_for(timeout=8000)
        check(
            "заметка добавлена",
            "План проверки" in page.locator(".dt-panel").inner_text(),
        )

        # Связи
        page.locator(".dt-tab", has_text="Связи").click()
        page.locator(".dt-panel input[type=number]").fill(str(rid2))
        page.get_by_role("button", name="Привязать").click()
        page.locator(".dt-panel", has_text="Связанный Человек").wait_for(timeout=8000)
        check(
            "связь добавлена",
            "Связанный Человек" in page.locator(".dt-panel").inner_text(),
        )

        # История + настоящий rollback
        _api(
            "PUT",
            f"/api/data/employees/{rid}",
            TOKEN,
            {"data": {"ФИО": "Досье Тест", "Должность": "Мастер"}},
        )
        page.locator(".dt-tab", has_text="История").click()
        page.wait_for_selector(".dt-hist", timeout=8000)
        check("история показана", "Мастер" in page.locator(".dt-panel").inner_text())
        page.on("dialog", lambda d: d.accept())
        page.get_by_role("button", name="Откатить").first.click()
        time.sleep(1.5)
        st3, rec = _api("GET", f"/api/data/employees/{rid}", TOKEN)
        check(
            "rollback вернул значение",
            rec.get("data", {}).get("Должность") == "Инженер",
            str(rec.get("data", {}).get("Должность")),
        )

        # Esc закрывает
        page.keyboard.press("Escape")
        time.sleep(0.4)
        check(
            "Escape закрывает досье", page.locator(".dt-overlay:visible").count() == 0
        )

        # Вход из старой панели таблицы (редактирование -> заметки -> досье)
        page.locator(".nav-item", has_text="Сотрудники").first.click()
        page.wait_for_selector("table.grid:visible", timeout=10000)
        time.sleep(0.8)
        page.locator(
            "table.grid tbody tr td.col-actions .icon-btn:not(.danger)"
        ).first.click()
        page.wait_for_selector(".modal:visible", timeout=8000)
        page.locator(".panel-btns .icon-btn").first.click()
        page.wait_for_selector(".panel-modal:visible", timeout=8000)
        page.get_by_role("button", name="Открыть досье").click()
        page.wait_for_selector(".dt-overlay:visible", timeout=8000)
        check(
            "досье из старой панели", page.locator(".dt-overlay:visible").count() == 1
        )
        check(
            "старая панель закрылась", page.locator(".panel-modal:visible").count() == 0
        )
        page.keyboard.press("Escape")
        time.sleep(0.3)

        # Контекст реестра: open с recordId
        page.evaluate(
            "() => document.dispatchEvent(new CustomEvent('suot-next-open',"
            f" {{detail: {{id: 'people', context: {{recordId: {rid}}}}}}}))"
        )
        page.wait_for_selector(".dt-overlay:visible", timeout=8000)
        page.wait_for_selector(".dt-title-main:visible", timeout=8000)
        check(
            "досье через контекст реестра",
            "Досье Тест" in page.locator(".dt-title-main").inner_text(),
        )
        page.keyboard.press("Escape")

        js_err = [e for e in errors if "favicon" not in e]
        check("нет JS-ошибок", not js_err, "; ".join(js_err[:2]))
        browser.close()
finally:
    cleanup()

print(f"\n{len(PASS)} OK, {len(FAIL)} FAIL")
sys.exit(1 if FAIL else 0)
