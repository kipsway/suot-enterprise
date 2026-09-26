"""Часть 34: Веб-сайт программы (E2E). Проверки: секции сайта, карусель
скриншотов, скачивание актуальной сборки, история версий из index.json,
контрольные хэши, навигация без битых якорей, нет JS-ошибок."""

import http.server
import hashlib
import json
import os
import re
import socketserver
import sys
import threading
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site")

PASS, FAIL = [], []


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(("  OK " if cond else "FAIL ") + name + (f" | {extra}" if extra else ""))


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def serve():
    os.chdir(SITE)
    handler = type("Q", (QuietHandler,), {"directory": SITE})
    srv = socketserver.TCPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


try:
    from playwright.sync_api import sync_playwright
except Exception as e:
    print("PLAYWRIGHT_NOPE", e)
    sys.exit(2)

srv, PORT = serve()
BASE = f"http://127.0.0.1:{PORT}"

# ── статические проверки файлов ──
html = open(os.path.join(SITE, "index.html"), encoding="utf-8", errors="replace").read()
js = open(
    os.path.join(SITE, "js", "site.js"), encoding="utf-8", errors="replace"
).read()

anchors = ["features", "screens", "download", "guide", "support"]
for a in anchors:
    check(f"34: секция #{a} существует", f'id="{a}"' in html)
nav_links = ["#features", "#screens", "#download", "#guide", "#support", "#demo"]
for n in nav_links:
    check(f"34: ссылка в nav {n}", n in html)

# скриншоты
import glob

shots = sorted(glob.glob(os.path.join(SITE, "media", "shots", "*.png")))
check(
    "34: карусель скриншотов присутствует",
    "data-carousel" in html and len(shots) >= 5,
    f"shots={len(shots)}",
)

# downloads/index.json
idx_path = os.path.join(SITE, "downloads", "index.json")
check("34: index.json существует", os.path.isfile(idx_path))
with open(idx_path, encoding="utf-8") as f:
    idx = json.load(f)
zip_info = idx["releases"][0]
zip_path = os.path.join(SITE, "downloads", zip_info["file"])
check(
    "34: zip-файл на месте",
    os.path.isfile(zip_path),
    f"{zip_info['file']} {zip_info['size_mb']} МБ",
)
real_hash = hashlib.sha256(open(zip_path, "rb").read()).hexdigest()
check(
    "34: SHA-256 в index.json совпадает",
    real_hash == zip_info["sha256"],
    zip_info["sha256"][:12] + "…",
)
check("34: история версий не пуста", len(idx.get("history", [])) > 0)
check("34: в HTML нет мёртвых якорей #start/#cp", "#start" not in html)

try:
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        errors = []
        page = b.new_page(viewport={"width": 1440, "height": 900})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(BASE + "/", wait_until="domcontentloaded")
        page.wait_for_selector("#heroVer", timeout=10000)
        time.sleep(0.8)

        ver_text = page.text_content("#heroVer")
        check(
            "34: версия из index.json подставлена",
            ver_text == idx["version"],
            f"ver={ver_text}",
        )

        zip_size_el = page.text_content("#dlZipSize")
        check(
            "34: размер ZIP в карточке", "МБ" in (zip_size_el or ""), zip_size_el or ""
        )

        hash_text = page.text_content("#dlHashZip")
        check(
            "34: хэш показывается на странице",
            idx["releases"][0]["sha256"] in (hash_text or "")[:80].replace(" ", ""),
            (hash_text or "")[:40],
        )

        rows = page.locator("#verBody tr").count()
        check("34: таблица истории заполнена", rows >= 1, f"rows={rows}")

        # каросель
        page.evaluate("window.scrollTo(0, 900)")
        time.sleep(0.4)
        car = page.locator(".carousel")
        page.locator("[data-car-next]").click()
        time.sleep(0.1)
        page.locator("[data-car-next]").click()
        time.sleep(0.1)
        page.locator("[data-car-prev]").click()
        time.sleep(0.15)
        dots = page.locator(".car-dot").count()
        check(
            "34: карусель переключается без ошибок",
            dots >= 5 and len(errors) == 0,
            f"dots={dots}",
        )

        # живое демо: вкладки переключаются
        tabs = ["employees", "ppe", "training", "calendar", "tools", "dashboard"]
        demo_ok = True
        for tb in tabs:
            # клик по вкладке (evaluate с аргументом)
            page.evaluate(
                "function (t) { var el = document.querySelector('.mini-side span[data-tab=\"' + t + '\"]'); if (el) { el.click(); } }",
                tb,
            )
            time.sleep(0.05)
            shown = page.evaluate(
                "function (t) { var v = document.querySelector('[data-view=\"' + t + '\"]'); return !!v && v.style.display !== 'none'; }",
                tb,
            )
            active = page.evaluate(
                "function (t) { var s = document.querySelector('.mini-side span[data-tab=\"' + t + '\"]'); return !!s && s.classList.contains('active'); }",
                tb,
            )
            if not (shown and active):
                demo_ok = False
        check("34: демо-вкладки переключаются", demo_ok, "tabs=%d" % len(tabs))

        # живое демо: поиск по сотрудникам фильтрует
        page.evaluate(
            'function () { var el = document.querySelector("#empSearch");'
            ' el.value = "Ивано";'
            ' el.dispatchEvent(new Event("input")); }'
        )
        time.sleep(0.05)
        vis_rows = page.evaluate(
            "function () { var r = document.querySelectorAll('#empTable tbody tr');"
            " var n = 0; for (var i = 0; i < r.length; i++) {"
            " if (r[i].style.display !== 'none') { n++; } } return n; }"
        )
        check(
            "34: демо-поиск по сотрудникам фильтрует",
            vis_rows == 1,
            "rows=%s" % vis_rows,
        )

        # все битые ссылки
        broken = []
        hrefs = page.evaluate("""() => {
          return Array.from(document.querySelectorAll('a[href]'))
            .map(a => a.getAttribute('href')).filter(h => h && h.charAt(0) === '#');
        }""")
        existing = page.evaluate("""() => {
          return Array.from(document.querySelectorAll('[id]'))
            .map(e => e.id);
        }""")
        for h in set(hrefs):
            if h[1:] not in existing:
                broken.append(h)
        check("34: нет битых якорей", len(broken) == 0, ", ".join(broken))

        # тёмная/светлая тема
        page.click("#themeToggle")
        time.sleep(0.2)
        theme = page.get_attribute("body", "data-theme")
        check("34: переключатель темы работает", theme == "light", f"theme={theme}")

        # скачивание zip (заголовок/статус)
        dlp = page.request.get(BASE + "/downloads/SUOT_Neo_portable.zip")
        check(
            "34: файл скачивается (HTTP 200)",
            dlp.status == 200 and int(dlp.headers.get("content-length", 0)) > 0,
            f"status={dlp.status}",
        )

        # Aurora v2: иконки инжектятся, слайдов 7, EN-переключатель
        check(
            "34: SVG-иконки инжектятся",
            page.locator("[data-ic-done]").count() >= 20,
            str(page.locator("[data-ic-done]").count()),
        )
        check(
            "34: слайдов 7 (включая Документы)",
            page.locator("[data-slide]").count() == 7,
            str(page.locator("[data-slide]").count()),
        )
        page.locator("#langToggle").click()
        time.sleep(0.6)
        h1en = page.locator(".hero h1").inner_text()
        check(
            "34: EN-переключатель",
            "workplace safety" in h1en.lower(),
            h1en[:50].replace("\n", " "),
        )
        page.locator("#langToggle").click()
        time.sleep(0.6)

        # reduced-motion
        page2 = b.new_page(
            viewport={"width": 1400, "height": 900}, reduced_motion="reduce"
        )
        errs2 = []
        page2.on("pageerror", lambda e: errs2.append(str(e)))
        page2.goto(BASE + "/", wait_until="domcontentloaded")
        page2.wait_for_selector("#heroVer", timeout=10000)
        time.sleep(0.4)
        check("34: reduced-motion без ошибок", len(errs2) == 0, "; ".join(errs2[:2]))
        page2.close()

        check("34: нет JS-ошибок на странице", len(errors) == 0, "; ".join(errors[:2]))

        b.close()
finally:
    srv.shutdown()

print()
print(f"E2E Часть 34: {len(PASS)} OK, {len(FAIL)} FAIL")
if FAIL:
    print("Провалены:", FAIL)
    sys.exit(1)
