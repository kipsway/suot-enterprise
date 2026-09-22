"""Часть 34: скриншоты интерфейса приложения для карусели на сайте.

Запуск:  python scripts/make_screenshots.py
Сохраняет в site/media/shots/*.png  (тёмная тема, вкладки приложения).
"""

import os
import socket
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "site", "media", "shots")
os.environ["SUOT_E2E_DB"] = os.path.join(ROOT, "exports", "shots_e2e.db")


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def main():
    os.makedirs(OUT, exist_ok=True)
    db = os.environ["SUOT_E2E_DB"]
    if os.path.isfile(db):
        os.remove(db)
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    srv = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "server.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=ROOT,
        env={**os.environ},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        import http.client

        for _ in range(200):
            try:
                c = http.client.HTTPConnection("127.0.0.1", port, timeout=0.5)
                c.request("GET", "/api/health")
                if c.getresponse().status == 200:
                    break
            except Exception:
                time.sleep(0.2)

        from playwright.sync_api import sync_playwright

        shots = [
            ("dashboard", "Дашборд", 0.9),
            ("employees", "Сотрудники", 1.0),
            ("ppe", "СИЗ", 1.0),
            ("training", "Обучение", 1.3),
            ("calendar", "Календарь", 1.2),
            ("game", "2048", 0.8),
        ]
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            page = b.new_page(viewport={"width": 1440, "height": 860})
            errs = []
            page.on("pageerror", lambda e: errs.append(str(e)))
            page.goto(base + "/", wait_until="domcontentloaded")
            page.wait_for_selector(".lang-cards", timeout=20000)
            page.get_by_role("button", name="Русский").click()
            page.wait_for_selector(".auth-card", timeout=20000)
            # мастер первого запуска
            if page.locator(".s-step").count() > 0:
                page.locator(".field-input").nth(0).fill("Демо-организация")

                def _fi(idx, val):
                    page.locator(".field-input").nth(idx).fill(val)

                # после шага 1 -> шаг 2
                page.get_by_role("button", name="Далее").click()
                _fi(0 if page.locator(".field-input").count() > 0 else 0, "admin")
                _fi(1, "Администратор")
                _fi(2, "admin")
                _fi(3, "admin")
                page.get_by_role("button", name="Далее").click()
                page.get_by_role("button", name="Далее").click()
                page.get_by_role("button", name="Завершить").click()
            else:
                page.locator(".seg-btn").nth(0).click()
                page.get_by_placeholder("например, ivanov").fill("admin")
                page.get_by_placeholder("минимум 6 символов").fill("admin")
                page.get_by_role("button", name="Войти").click()
            page.wait_for_selector(".shell", timeout=20000)
            time.sleep(1.2)
            # закрыть onboarding-тур, если он активен (кнопка «Пропустить»)
            try:
                page.locator(".tour-layer button", has_text="Пропустить").click(
                    timeout=3000
                )
            except Exception:
                pass
            time.sleep(0.5)
            if page.locator(".tour-layer").count() > 0:
                page.keyboard.press("Escape")
                time.sleep(0.4)

            shot_files = []
            for key, label, wait in shots:
                page.locator(".nav-item", has_text=label).first.click()
                time.sleep(wait)
                page.wait_for_timeout(200)
                fp = os.path.join(OUT, f"shot-{key}.png")
                page.screenshot(path=fp)
                shot_files.append(f"shot-{key}.png")
                print("shot:", key, fp)

            # тёмная тема уже стандартная; доп. форма входа не нужна
            print("JS errors:", len(errs))
            b.close()
        return 0
    finally:
        srv.terminate()


if __name__ == "__main__":
    raise SystemExit(main())
