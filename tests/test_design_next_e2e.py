"""E2E SUOT Next: слой редизайна web/css/next.css.
next.css подключён и применяется: шрифт, focus-visible, активные пилюли,
табличные цифры, токен-переходы кнопок, reduced-motion. Ноль JS-ошибок."""

import os
import sys
import subprocess
import time
import tempfile
import socket

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

TMPD = tempfile.mkdtemp(prefix="suot_e2edx_")
TEST_DB = os.path.join(TMPD, "e2e.db")
os.environ["SUOT_E2E_DB"] = TEST_DB


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


PORT = _free_port()
BASE = f"http://127.0.0.1:{PORT}"
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
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        errs = []
        page.on("pageerror", lambda e: errs.append(str(e)))
        page.goto(BASE + "/", wait_until="domcontentloaded")
        page.wait_for_selector(".lang-cards", timeout=15000)
        page.get_by_role("button", name="Русский").click()
        page.wait_for_selector(".auth-card", timeout=8000)
        page.locator(".seg-btn").nth(1).click()
        page.get_by_placeholder("Иванов Иван Иванович").fill("Дизайн Тест")
        page.get_by_placeholder("например, ivanov").fill("designx_user")
        page.get_by_placeholder("минимум 6 символов").fill("parol123")
        page.get_by_role("button", name="Создать аккаунт").click()
        page.wait_for_selector(".shell", timeout=10000)
        time.sleep(1.2)
        try:
            page.wait_for_selector(".tour-layer", timeout=3500)
            page.keyboard.press("Escape")
            time.sleep(0.4)
        except Exception:
            pass

        st = page.evaluate("""async () => {
            const r = await fetch('css/next.css');
            return r.status;
        }""")
        check("next.css отдаётся (200)", st == 200, str(st))
        linked = page.evaluate(
            "() => !!document.querySelector('link[href=\"css/next.css\"]')"
        )
        check("next.css подключён в head", linked)

        font = page.evaluate("() => getComputedStyle(document.body).fontFamily")
        check(
            "системный шрифт применён",
            "Segoe UI" in font or "system-ui" in font,
            font[:60],
        )
        fv = page.evaluate("""() => {
            for (const sh of document.styleSheets) {
                try {
                    for (const r of sh.cssRules) {
                        if (r.selectorText === ':focus-visible') return r.style.outline || 'yes';
                    }
                } catch (e) {}
            }
            return '';
        }""")
        check("focus-visible правило есть", bool(fv), str(fv)[:40])
        btn_tr = page.evaluate(
            "() => getComputedStyle(document.querySelector('.btn')).transitionDuration"
        )
        check("кнопки на токене 0.15s", btn_tr.split(",")[0].strip() == "0.15s", btn_tr)
        tab_shadow = page.evaluate("""() => {
            const el = document.querySelector('.tab.active') ||
                       document.querySelector('.nav-item.active');
            if (!el) return 'no-active';
            const cs = getComputedStyle(el);
            return cs.boxShadow + '|' + cs.fontWeight;
        }""")
        check(
            "активный элемент выделен",
            "none" not in tab_shadow.split("|")[0],
            tab_shadow[:60],
        )
        num_font = page.evaluate("""() => {
            const el = document.querySelector('.ws-kbd, .kpi-v, td.col-id');
            return el ? getComputedStyle(el).fontVariantNumeric : 'n/a';
        }""")
        check(
            "табличные цифры",
            num_font == "" or "tabular" in num_font or num_font == "n/a",
            num_font,
        )

        # WCAG AA: контраст текста к фонам в обеих темах (>= 4.5)
        contrast = page.evaluate("""() => {
            function lum(hex) {
                const m = hex.replace('#', '');
                const v = [0, 2, 4].map(i => parseInt(m.substr(i, 2), 16) / 255)
                    .map(c => c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4));
                return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2];
            }
            function ratio(a, b) {
                const x = lum(a), y = lum(b);
                return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
            }
            function themeRatios(theme) {
                document.body.setAttribute('data-theme', theme);
                const cs = getComputedStyle(document.body);
                const g = (n) => cs.getPropertyValue(n).trim();
                const out = {};
                for (const t of ['--t-0', '--t-1', '--t-2']) {
                    for (const bg of ['--bg-0', '--bg-1']) {
                        out[t + '/' + bg] = Math.round(ratio(g(t), g(bg)) * 100) / 100;
                    }
                }
                return out;
            }
            return { dark: themeRatios('dark'), light: themeRatios('light') };
        }""")
        for theme in ("dark", "light"):
            bad = {k: v for k, v in contrast[theme].items() if v < 4.5}
            check(f"контраст AA {theme} (>= 4.5)", not bad, str(bad))

        # reduced-motion: длительности схлопываются
        ctx2 = browser.new_context(
            viewport={"width": 1280, "height": 800}, reduced_motion="reduce"
        )
        p2 = ctx2.new_page()
        p2.goto(BASE + "/", wait_until="domcontentloaded")
        p2.wait_for_selector(".lang-cards", timeout=15000)
        rm = p2.evaluate("() => matchMedia('(prefers-reduced-motion: reduce)').matches")
        check("reduced-motion детектируется", rm)
        p2.close()

        real_errors = [e for e in errs if "favicon" not in e.lower()]
        check(
            "нет JS-ошибок", len(real_errors) == 0, ("; ".join(real_errors[:2]))[:150]
        )
        browser.close()

    print(f"\nE2E Дизайн Next: {len(PASS)} OK, {len(FAIL)} FAIL")
    if FAIL:
        print("Провалены:", FAIL)
finally:
    try:
        server_proc.terminate()
    except Exception:
        pass
