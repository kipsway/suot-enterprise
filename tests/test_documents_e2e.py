"""E2E SUOT Next Documents Center (Блок 7): шаблоны + версии/откат,
HTML-предпросмотр, сохранённые отчёты (запуск + спека из конструктора),
очередь печати (прогресс, скачивание PDF, preview), IDOR, RU, ноль JS-ошибок."""

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

TMPD = tempfile.mkdtemp(prefix="suot_docs_")
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
    conn = http.client.HTTPConnection("127.0.0.1", PORT, timeout=15)
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    conn.request(method, path, json.dumps(body) if body is not None else None, headers)
    resp = conn.getresponse()
    data = resp.read().decode("utf-8", "replace")
    conn.close()
    try:
        return resp.status, json.loads(data) if data else {}
    except Exception:
        return resp.status, {}


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
        ctx = browser.new_context(viewport={"width": 1500, "height": 900})
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.add_init_script(f"localStorage.setItem('suot_token', '{TOKEN}');")
        page.goto(BASE_URL + "/", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector(".shell", timeout=15000)
        check("вход по токену", True)
        try:
            page.wait_for_selector(".tour-layer", timeout=3500)
            page.keyboard.press("Escape")
            time.sleep(0.5)
        except Exception:
            pass

        # Детерминированные данные: 2 сотрудника + шаблон v1 -> v2
        _api(
            "POST",
            "/api/data/employees",
            TOKEN,
            {"data": {"ФИО": "Доков Д", "Дата медосмотра": "01.01.2030"}},
        )
        _api(
            "POST",
            "/api/data/employees",
            TOKEN,
            {"data": {"ФИО": "Печатов П", "Дата медосмотра": "01.01.2030"}},
        )
        st, tpl = _api(
            "POST",
            "/api/print/templates",
            TOKEN,
            {"name": "ДокТест", "html_content": "<h1>{ФИО} v1</h1>"},
        )
        TID = tpl.get("id", 0)
        check("шаблон создан", st == 201 and TID, f"id={TID}")
        _api(
            "PUT",
            f"/api/print/templates/{TID}",
            TOKEN,
            {"name": "ДокТест", "html_content": "<h1>{ФИО} v2</h1>"},
        )

        # Центр открывается
        page.locator(".nav-item", has_text="Документы").first.click()
        page.wait_for_selector(".doc-center", timeout=10000)
        time.sleep(1.2)
        check("центр открыт", True)
        names = page.locator(".doc-center").inner_text()
        check("шаблон в списке", "ДокТест" in names)

        # История версий: v1 после правки
        page.locator(".doc-vers-btn").first.click()
        page.wait_for_selector(".doc-vers", timeout=8000)
        time.sleep(0.8)
        vers = page.locator(".doc-vers").inner_text()
        check("версия v1 видна", "v1" in vers, vers[:80].replace("\n", " "))
        check("кнопка отката есть", page.locator(".doc-restore-btn").count() >= 1)

        # Откат: правим до v3 через API, откатываем к v1 через UI
        _api(
            "PUT",
            f"/api/print/templates/{TID}",
            TOKEN,
            {"name": "ДокТест", "html_content": "<h1>{ФИО} v3</h1>"},
        )
        page.on("dialog", lambda d: d.accept())
        page.locator(".doc-restore-btn").first.click()
        time.sleep(1.2)
        st, cur = _api("GET", f"/api/print/templates/{TID}", TOKEN)
        check(
            "откат к v1",
            "v1</h1>" in (cur.get("template", {}) or {}).get("html_content", ""),
        )

        # HTML-предпросмотр шаблона
        page.locator(".doc-prev-btn").first.click()
        page.wait_for_selector(".doc-htmlprev", timeout=8000)
        time.sleep(0.6)
        html_prev = page.locator(".doc-htmlprev").inner_text()
        check(
            "предпросмотр HTML",
            "v1" in html_prev or "—" in html_prev,
            html_prev[:60].replace("\n", " "),
        )
        page.keyboard.press("Escape")
        time.sleep(0.4)

        # Сохранённый отчёт: создание через API + запуск через UI
        st, rep = _api(
            "POST",
            "/api/documents/reports/saved",
            TOKEN,
            {"name": "РепТест", "table": "employees", "columns": ["ФИО"]},
        )
        RID = rep.get("id", 0)
        page.locator(".doc-center .seg-btn", has_text="Отчёты").click()
        time.sleep(1.0)
        check("отчёт в списке", "РепТест" in page.locator(".doc-center").inner_text())
        page.locator(".doc-run-btn").first.click()
        grid_ok = False
        for _ in range(10):
            time.sleep(1.0)
            try:
                if page.locator(".doc-run table.grid:visible").count():
                    grid_ok = True
                    break
            except Exception:
                pass
        if not grid_ok:
            print(
                "   STATE:",
                page.evaluate(
                    "() => { const d = Alpine.$data("
                    "document.querySelector('.doc-center'));"
                    " return {busy: d.runBusy, err: d.runError, res: d.runResult"
                    " ? d.runResult.mode + '/' + d.runResult.total : null}; }"
                ),
            )
        check("отчёт выполняется", grid_ok)

        # Конструктор -> выполнить -> сохранить спеку -> видна в списке
        page.locator(".doc-center .btn", has_text="Конструктор").click()
        page.wait_for_selector(".rb-modal:visible", timeout=8000)
        time.sleep(0.8)
        page.locator(".rb-modal .btn.primary", has_text="Выполнить").click()
        page.wait_for_selector(".rb-result", timeout=10000)
        time.sleep(0.5)
        page.locator(".rb-save-name").fill("ИзКонструктора")
        page.locator(".rb-modal .btn.sm", has_text="Сохранить").click()
        time.sleep(1.2)
        page.keyboard.press("Escape")
        time.sleep(0.5)
        check(
            "спека из конструктора сохранена",
            "ИзКонструктора" in page.locator(".doc-center").inner_text(),
        )

        # Очередь печати: форма -> задание -> done
        page.locator(".doc-center .seg-btn", has_text="Очередь").click()
        time.sleep(0.8)
        page.locator(".doc-job-name").fill("ПечатьТест")
        page.locator(".doc-job-tpl").select_option(str(TID))
        page.locator(".doc-job-create").click()
        page.wait_for_selector(".doc-job", timeout=15000)
        check("задание создано", True)
        done = False
        last_badge = ""
        for _ in range(75):
            time.sleep(2.0)
            try:
                # .badge рендерится в uppercase через CSS — сравниваем нижний регистр
                badge = page.locator(".doc-job .badge").first.inner_text().lower()
                last_badge = badge
            except Exception:
                badge = ""
            if "готово" in badge or "done" in badge:
                done = True
                break
            if "ошибка" in badge or "error" in badge:
                break
        if not done:
            try:
                err_txt = page.locator(".doc-job .alert.error").first.inner_text()
            except Exception:
                err_txt = ""
            print(f"   JOB: badge={last_badge} err={err_txt[:120]}")
        check("задание выполнено", done)
        if done:
            with page.expect_download(timeout=15000) as dl_info:
                page.locator(".doc-job-dl").first.click()
            dl = dl_info.value
            path = dl.path()
            import os as _os

            size = _os.path.getsize(path) if path else 0
            check(
                "PDF скачан",
                dl.suggested_filename.endswith(".pdf") and size > 500,
                f"{dl.suggested_filename} {size}b",
            )
            # PDF-preview в iframe
            page.locator(".doc-job-prev").first.click()
            page.wait_for_selector("iframe[src^='blob:']", timeout=10000)
            check("preview PDF в iframe", True)
            page.keyboard.press("Escape")
            time.sleep(0.4)

        # IDOR: второй пользователь не трогает чужие объекты
        st, reg = _api(
            "POST",
            "/api/auth/register",
            "",
            {"username": "doc_b", "password": "parol123"},
        )
        BTOK = reg.get("token", "") if st in (200, 201) else ""
        check("второй пользователь", bool(BTOK))
        if BTOK:
            s1, _ = _api("GET", f"/api/documents/templates/{TID}/versions", BTOK)
            s2, _ = _api("POST", "/api/documents/reports/saved/1/run", BTOK, {})
            s3, _ = _api("GET", "/api/documents/print/jobs/1/download", BTOK)
            check(
                "IDOR версий/отчёта/файла",
                s1 == 403 and s2 == 403 and s3 in (403, 404),
                f"{s1}/{s2}/{s3}",
            )

        js_err = [e for e in errors if "favicon" not in e.lower()]
        check("нет JS-ошибок", not js_err, "; ".join(js_err[:2]))
        browser.close()
finally:
    cleanup()

print(f"\n{len(PASS)} OK, {len(FAIL)} FAIL")
sys.exit(1 if FAIL else 0)
