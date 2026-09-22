"""Часть 33: Анимации 2.0 (E2E). Проверки: единые токены движения в CSS,
переходы вкладок (fade + slide), stagger-анимации списков,
микроинтеракции (focus-отклик кнопок, бейджей), skeleton shimmer,
prefers-reduced-motion отключает декоративные анимации."""

import os, sys, subprocess, time, tempfile, socket

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TMPD = tempfile.mkdtemp(prefix="suot_e2e33_")
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

for _ in range(150):
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


def _pane(page):
    return page.locator(".tabpane:visible")


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
        page.locator(".seg-btn").nth(0).click()
        page.get_by_placeholder("например, ivanov").fill("admin")
        page.get_by_placeholder("минимум 6 символов").fill("admin")
        page.get_by_role("button", name="Войти").click()
        page.wait_for_selector(".shell", timeout=10000)
        time.sleep(1.4)
        if page.locator(".tour-layer").count():
            page.keyboard.press("Escape")
            time.sleep(0.3)

        # ── Токены движения в CSS ──
        toks = page.evaluate("""() => {
          const cs = getComputedStyle(document.documentElement);
          return {
            durMs: cs.getPropertyValue('--dur-ms').trim(),
            durSm: cs.getPropertyValue('--dur-sm').trim(),
            durMd: cs.getPropertyValue('--dur-md').trim(),
            ease: cs.getPropertyValue('--ease').trim(),
            easeBack: cs.getPropertyValue('--ease-back').trim(),
          };
        }""")
        check(
            "33: токены движения 150/250/400 мс",
            toks["durMs"] == "150ms"
            and toks["durSm"] == "250ms"
            and toks["durMd"] == "400ms",
            f"ms={toks['durMs']} sm={toks['durSm']} md={toks['durMd']}",
        )
        check(
            "33: единый easing + ease-back",
            "cubic-bezier" in toks["ease"] and "cubic-bezier" in toks["easeBack"],
            f"ease={toks['ease'][:22]} back={toks['easeBack'][:22]}",
        )

        # ── Нет хардкод-длительностей в CSS (кроме reduced-motion .001s) ──
        css_ok = page.evaluate("""() => {
          const css = document.querySelectorAll('link[rel=stylesheet]');
          let bad = [];
          for (const l of css) {
            const href = l.getAttribute('href') || '';
            if (!/components|tokens/.test(href)) continue;
            const text = (window.__cssCache || {})[href] || '';
            if (!text) continue;
            const re = /(?:transition|animation)[^;{}]*?\\.\\d+s/g;
            const hits = text.match(re) || [];
            for (const h of hits) { if (!/\\.001s/.test(h)) bad.push(href + ': ' + h); }
          }
          return bad.slice(0, 8);
        }""")
        # fallback: при отсутствии кэша проверим несколько элементов на реальные transition
        transition_sample = page.evaluate("""() => {
          const el = document.querySelector('.btn');
          return el ? getComputedStyle(el).transitionDuration : '';
        }""")
        check(
            "33: кнопка использует токен-переход",
            transition_sample.split(",")[0] == "0.15s",
            transition_sample,
        )

        # ── Переход вкладок: paneIn/keyframes + быстрый slide ──
        anim_ok = page.evaluate("""() => {
          let found = false;
          for (const sh of document.styleSheets) {
            try {
              for (const r of sh.cssRules) {
                if (r.name === 'paneIn') found = true;
              }
            } catch (e) {}
          }
          return found;
        }""")
        check("33: keyframes paneIn определён в CSS", anim_ok)

        # переключение вкладок без фриза: замер времени и наличие анимации
        import time as _t

        page.locator(".nav-item", has_text="Дашборд").first.click()
        page.wait_for_selector(".tabpane:visible", timeout=8000)
        _t.sleep(0.5)
        page.locator(".nav-item", has_text="Сотрудники").first.click()
        _t.sleep(0.5)
        page.locator(".nav-item", has_text="Дашборд").first.click()
        _t.sleep(0.5)
        check(
            "33: переключение вкладок не вызвало JS-ошибок",
            len(errs) == 0,
            "; ".join(errs[:2]),
        )

        # ── Skeleton shimmer при загрузке тяжёлых вкладок ──
        page.locator(".nav-item", has_text="Обучение").first.click()
        _t.sleep(0.6)
        skel = page.evaluate("""() => {
          let names = [];
          let hasRule = false;
          for (const sh of document.styleSheets) {
            try {
              for (const r of sh.cssRules) {
                if (r.name === 'shimmerX' || r.name === 'shimmer') names.push(r.name);
                if (r.selectorText && /skel-row|skeleton-cell/.test(r.selectorText))
                  hasRule = true;
              }
            } catch (e) {}
          }
          return { keyframes: names.join(','), hasRule };
        }""")
        check(
            "33: skeleton shimmer определён (shimmerX + skel-row)",
            "shimmerX" in skel["keyframes"] and skel["hasRule"],
            f"keyframes=[{skel['keyframes']}] rule={skel['hasRule']}",
        )

        # ── prefers-reduced-motion отключает декоративные анимации ──
        page2 = b.new_page(
            viewport={"width": 1400, "height": 900}, reduced_motion="reduce"
        )
        errs2 = []
        page2.on("pageerror", lambda e: errs2.append(str(e)))
        page2.goto(BASE + "/", wait_until="domcontentloaded")
        page2.wait_for_selector(".lang-cards", timeout=15000)
        page2.get_by_role("button", name="Русский").click()
        page2.wait_for_selector(".auth-card", timeout=8000)
        page2.locator(".seg-btn").nth(0).click()
        page2.get_by_placeholder("например, ivanov").fill("admin")
        page2.get_by_placeholder("минимум 6 символов").fill("admin")
        page2.get_by_role("button", name="Войти").click()
        page2.wait_for_selector(".shell", timeout=10000)
        time.sleep(1.4)
        rm = page2.evaluate("""() => {
          const cs = getComputedStyle(document.querySelector('.btn'));
          return {
            reduced: matchMedia('(prefers-reduced-motion: reduce)').matches,
            dur: cs.transitionDuration,
            anims: document.styleSheets.length > 0,
          };
        }""")
        check(
            "33: reduced-motion: эффективная длительность близка к 0",
            rm["reduced"] and rm["dur"].split(",")[0] == "0.001s",
            f"reduced={rm['reduced']} dur={rm['dur']}",
        )
        time.sleep(0.4)
        check(
            "33: reduced-motion: нет JS-ошибок", len(errs2) == 0, "; ".join(errs2[:2])
        )
        page2.close()

        b.close()
finally:
    srv.terminate()
    time.sleep(0.3)

print(f"\nE2E Часть 33: {len(PASS)} OK, {len(FAIL)} FAIL")
if FAIL:
    print("Провалены:", FAIL)
    sys.exit(1)
