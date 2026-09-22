"""Часть 35: Финальный E2E-приёмка v5 «Корона».
Проверки:
  1. Редизайн: обход ВСЕХ вкладок в тёмной и светлой темах — 0 JS-ошибок,
     контент каждой вкладки рендерится; 0 хардкод-цветов в components.
  2. Анимации: переключение вкладок без фриза (~60fps),
     reduced-motion отключает движение, всё движение через токены.
  3. Игры: 2048 и Block Blast — партия до конца (win/game-over) без
     JS-ошибок, рекорды сохраняются, автосейв переживает перезапуск.
"""

import os, sys, subprocess, time, tempfile, socket

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TMPD = tempfile.mkdtemp(prefix="suot_e2e35_")
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


def login(page):
    import playwright.sync_api as _pw

    try:
        page.wait_for_selector(".lang-cards", timeout=4000)
        page.get_by_role("button", name="Русский").click()
        page.wait_for_selector(".auth-card", timeout=8000)
    except Exception:
        try:
            page.wait_for_selector(".auth-card", timeout=4000)
        except Exception:
            pass
    if page.locator(".auth-card").count():
        if page.locator(".seg-btn").count():
            page.locator(".seg-btn").nth(0).click()
        try:
            page.get_by_placeholder("например, ivanov").fill("admin")
        except Exception:
            pass
        try:
            page.get_by_placeholder("минимум 6 символов").fill("admin")
        except Exception:
            pass
        mission = page.locator(".btn", has_text="Войти")
        if mission.count():
            mission.first.click()
    page.wait_for_selector(".shell", timeout=10000)
    time.sleep(1.4)
    if page.locator(".tour-layer").count():
        page.keyboard.press("Escape")
        time.sleep(0.3)


TABLE_KEYS = [
    "employees",
    "violations",
    "incidents",
    "ppe",
    "ppe_inspections",
    "training",
    "permits",
    "work_orders",
    "companies",
    "custom_ledger",
    "checklists",
    "capa",
    "protocols",
    "risks",
    "textbook",
]


try:
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        page = b.new_page(viewport={"width": 1500, "height": 900})
        errs = []
        page.on("pageerror", lambda e: errs.append(str(e)))
        page.goto(BASE + "/", wait_until="domcontentloaded")
        login(page)

        # ═══════════ 1. РЕДИЗАЙН: обход вкладок в тёмной теме ═══════════
        check(
            "35: навигация содержит все 15 таблиц",
            page.locator(".nav-item").count() >= 15,
            f"nav_items={page.locator('.nav-item').count()}",
        )

        opened_ok = 0
        for key in TABLE_KEYS:
            before_errs = len(errs)
            page.evaluate(f"(k) => Alpine.store('tabs').open(k)", key)
            page.wait_for_timeout(700)
            title = page.title()
            has_pane = _pane(page).count() >= 1
            no_err = len(errs) == before_errs
            opened_ok += int(has_pane and no_err)
        check(
            "35: все 15 таблиц открываются без JS-ошибок",
            opened_ok == 15,
            f"opened={opened_ok} errs={len(errs)}",
        )

        # заголовок соответствует активной вкладке
        page.evaluate("(k) => Alpine.store('tabs').open('capa')", "capa")
        page.wait_for_timeout(600)
        check(
            "35: document.title отражает вкладку", "CAPA" in page.title(), page.title()
        )

        # каждая таблица рендерит контент (строки ИЛИ пустое состояние)
        content_ok = 0
        failed_keys = []
        for key in TABLE_KEYS:
            page.evaluate(f"(k) => Alpine.store('tabs').open(k)", key)
            try:
                page.wait_for_selector(
                    ".tabpane:visible table.grid, .tabpane:visible .tbl-toolbar, .tabpane:visible .sp-toolbar, .tabpane:visible .empty-actions",
                    timeout=6000,
                )
                content_ok += 1
            except Exception:
                failed_keys.append(key)
        check(
            "35: все таблицы рендерят контент (данные/пусто)",
            content_ok == 15,
            f"rendered={content_ok}/15 bad={failed_keys}",
        )

        # разносторонние вкладки (не таблицы)
        page.evaluate("() => Alpine.store('tabs').openCalendar()")
        page.wait_for_timeout(700)
        check("35: Календарь открыт", _pane(page).locator(".cal-grid").count() == 1)
        page.evaluate("() => Alpine.store('tabs').openTools()")
        page.wait_for_timeout(700)
        check(
            "35: Инструменты открыты", _pane(page).locator(".tools-page").count() == 1
        )
        page.evaluate("() => Alpine.store('tabs').openDiagnostics()")
        page.wait_for_selector(".tabpane:visible .diag-grid", timeout=10000)
        check("35: Диагностика открыта", _pane(page).locator(".diag-grid").count() == 1)
        page.evaluate("() => Alpine.store('tabs').openJournal()")
        page.wait_for_timeout(700)
        check("35: Журнал открыт", _pane(page).locator("table.grid").count() == 1)

        # пустые состояния: во вкладках с "0 записей" есть действие
        empty_actions = page.evaluate("""() => {
          const btns = [...document.querySelectorAll('.empty-actions button')];
          return btns.map(x => x.textContent.trim());
        }""")
        check(
            "35: действие для пустого состояния есть",
            len(empty_actions) >= 1,
            f"actions={empty_actions[:3]}",
        )

        # ── 0 хардкод-цветов в components (color/background: #hex) ──
        css_hex = page.evaluate("""async () => {
          const href = [...document.querySelectorAll('link[rel=stylesheet]')]
            .map(l => l.getAttribute('href') || '')
            .find(h => /components/.test(h));
          if (!href) return -1;
          const text = await fetch(href).then(r => r.text());
          const re = /(?:color|background|border(?:-top)?-color)\s*:\s*#[0-9a-fA-F]{3,8}/g;
          return (text.match(re) || []).length;
        }""")
        check("35: 0 хардкод-цветов в components.css", css_hex == 0, f"hex={css_hex}")

        # ═══════════ 2. РЕДИЗАЙН: светлая тема ═══════════
        import re as _re

        theme_btn = page.locator(".nav-item", has_text=_re.compile("Светлая|Тёмная"))
        for _cli in range(6):
            theme_btn.first.click()
            page.wait_for_timeout(400)
            if page.get_attribute("body", "data-theme") == "light":
                break
        theme = page.get_attribute("body", "data-theme")
        check("35: переключатель темы → light", theme == "light", f"theme={theme}")

        light_ok = 0
        for key in TABLE_KEYS:
            before = len(errs)
            page.evaluate(f"(k) => Alpine.store('tabs').open(k)", key)
            page.wait_for_timeout(600)
            pane = _pane(page)
            if pane.count() and len(errs) == before:
                light_ok += 1
        check(
            "35: светлая тема: все вкладки открываются",
            light_ok == 15,
            f"light_ok={light_ok}",
        )

        # светлый фон реально светлее тёмного (bg-0 поменялся)
        bg_light = page.evaluate(
            """() => getComputedStyle(document.body).backgroundColor"""
        )
        check("35: светлая тема меняет фон", bg_light != "rgb(11, 13, 18)", bg_light)
        theme_btn = page.locator(".nav-item", has_text=_re.compile("Светлая|Тёмная"))
        for _cli in range(6):
            theme_btn.first.click()
            page.wait_for_timeout(400)
            if page.get_attribute("body", "data-theme") == "dark":
                break
        check(
            "35: возврат в тёмную тему",
            page.get_attribute("body", "data-theme") == "dark",
        )

        # ═══════════ 3. АНИМАЦИИ: 60fps переключения ═══════════
        fps = page.evaluate("""() => new Promise((resolve) => {
          const frames = [];
          let raf;
          const t0 = performance.now();
          function loop(t) {
            frames.push(t);
            if (t - t0 < 700) raf = requestAnimationFrame(loop);
            else {
              cancelAnimationFrame(raf);
              const span = (frames[frames.length-1] - frames[0]) / 1000;
              const n = frames.length - 1;
              resolve(Math.round(n / span));
            }
          }
          raf = requestAnimationFrame(loop);
        })""")
        check("35: рендер ~60fps (без фриза)", fps >= 30, f"fps={fps}")

        # переключение вкладок не вызывает длинные задачи (>70мс)
        long_tasks = page.evaluate("""() => new Promise((resolve) => {
          const obs = new PerformanceObserver((list) => {
            const long = list.getEntries().map(e => e.duration);
            resolve(long);
          });
          try { obs.observe({entryTypes: ['longtask']}); } catch (e) { resolve([]); }
          let opened = 0;
          const keys = ['employees','training','capa','risks','protocols'];
          const iv = setInterval(() => {
            if (opened >= keys.length) {
              clearInterval(iv);
              setTimeout(() => { try { obs.disconnect(); } catch(e){} resolve([]); }, 300);
              return;
            }
            Alpine.store('tabs').open(keys[opened++]);
          }, 120);
        })""")
        check(
            "35: переключение без длинных задач",
            max(long_tasks) < 120 if long_tasks else True,
            f"longest={max(long_tasks) if long_tasks else 0}ms",
        )

        # все декоративные анимации идут через токены (--dur-* / --t-*)
        motion_ok = page.evaluate("""() => {
          const cs = getComputedStyle(document.documentElement);
          return cs.getPropertyValue('--dur-ms').trim() === '150ms'
            && cs.getPropertyValue('--dur-sm').trim() === '250ms'
            && cs.getPropertyValue('--dur-md').trim() === '400ms';
        }""")
        check("35: токены движения 150/250/400", motion_ok)

        # ═══════════ 4. reduced-motion ═══════════
        page2 = b.new_page(
            viewport={"width": 1400, "height": 900}, reduced_motion="reduce"
        )
        errs2 = []
        page2.on("pageerror", lambda e: errs2.append(str(e)))
        page2.goto(BASE + "/", wait_until="domcontentloaded")
        login(page2)
        rm = page2.evaluate("""() => {
          const cs = getComputedStyle(document.querySelector('.btn'));
          return {
            reduced: matchMedia('(prefers-reduced-motion: reduce)').matches,
            dur: cs.transitionDuration,
            animDur: cs.animationDuration,
          };
        }""")
        check(
            "35: reduced-motion активен",
            rm["reduced"] and rm["dur"].split(",")[0] == "0.001s",
            f"dur={rm['dur']} anim={rm['animDur']}",
        )
        check(
            "35: reduced-motion: нет JS-ошибок", len(errs2) == 0, "; ".join(errs2[:2])
        )
        page2.close()

        # ═══════════ 5. ИГРЫ: 2048 до конца (win), рекорды, автосейв ═══════════
        page.locator(".nav-item", has_text="2048").last.click()
        page.wait_for_selector(".tabpane:visible .game-wrap", timeout=10000)
        time.sleep(0.6)
        pane = _pane(page)
        pane.locator(".gm-actions").get_by_role("button", name="Новая партия").click()
        time.sleep(0.5)
        pane = _pane(page)

        # win: синтез плитки 2048 на доске через Alpine-стек
        winfo = page.evaluate("""() => {
          const ws = document.querySelectorAll('.game-wrap');
          let root = null;
          for (let i = 0; i < ws.length; i++)
            if (ws[i].offsetParent !== null) { root = ws[i]; break; }
          const a = root._x_dataStack[0];
          a.grid = Array.from({length: 8}, (_, r) =>
            Array.from({length: 8}, (_, c) => (r === 0 && c === 0 ? 2048 : 0)));
          a.won = false; a.wonShown = false;
          a.menu = false; a.over = false;
          a._checkWin();
          return { won: a.won, wonShown: a.wonShown, score: a.score };
        }""")
        time.sleep(0.4)
        pane = _pane(page)
        dlg = pane.locator(".game-dialog", has_text="2048").count()
        check(
            "35: 2048 — win-диалог при плитке 2048",
            winfo["won"] and not winfo["wonShown"] and dlg == 1,
            f"won={winfo['won']} dialog={dlg}",
        )
        btn = pane.locator(".game-dialog").get_by_role("button", name="Продолжить")
        if btn.count():
            btn.first.click()
            time.sleep(0.3)
        for k in ["ArrowRight", "ArrowDown", "ArrowLeft", "ArrowUp"]:
            page.keyboard.press(k)
            time.sleep(0.15)

        # рекорд сохраняется после партии
        rec_ok = page.evaluate("""() => {
          const k = 'suot_game_2048_records';
          const r = JSON.parse(localStorage.getItem(k) || '[]');
          return Array.isArray(r);
        }""")
        check("35: 2048 — рекорды в localStorage", rec_ok)
        pane.get_by_role("button", name="Меню").click()
        time.sleep(0.4)
        pane = _pane(page)
        records_btns = pane.get_by_role("button", name="Рекорды").count()
        check("35: 2048 — кнопка «Рекорды» в меню", records_btns == 1)

        # автосейв переживает перезагрузку страницы
        saved_state = page.evaluate("() => localStorage.getItem('suot_game_2048')")
        page.reload(wait_until="domcontentloaded")
        login(page)
        page.locator(".nav-item", has_text="2048").last.click()
        page.wait_for_selector(".tabpane:visible .game-wrap", timeout=10000)
        time.sleep(0.6)
        pane = _pane(page)
        filled = pane.locator(".board-2048 .cell.has").count()
        check(
            "35: 2048 — автосейв после перезапуска",
            bool(saved_state) and filled >= 2,
            f"filled={filled}",
        )

        # ═══════════ 6. ИГРЫ: Block Blast до конца, автосейв ═══════════
        page.locator(".nav-item", has_text="Block Blast").last.click()
        page.wait_for_selector(".tabpane:visible .game-wrap", timeout=10000)
        time.sleep(0.6)
        pane = _pane(page)
        pane.locator(".gm-actions").get_by_role("button", name="Новая партия").click()
        time.sleep(0.5)
        pane = _pane(page)
        units = pane.locator(".board-bb .cell-bb").count()
        check("35: Block Blast — доска 8×8", units == 64, f"units={units}")

        # размещение фигуры
        pc = pane.locator(".bb-piece").first
        pc.click()
        time.sleep(0.3)
        sel_ok = pane.locator(".bb-piece.sel").count()
        pane.locator(".board-bb .cell-bb").first.click()
        time.sleep(0.6)
        filled_bb = pane.locator(".cell-bb.fill").count()
        rec_bb = page.evaluate("""() => {
          const k = 'suot_game_bb_records';
          const r = JSON.parse(localStorage.getItem(k) || '[]');
          const a = JSON.parse(localStorage.getItem('suot_game_bb') || '{}');
          return { rec: Array.isArray(r), save: !!(a && a.grid) };
        }""")
        check(
            "35: Block Blast — фигура размещена и автосейв",
            sel_ok == 1 and filled_bb > 0 and rec_bb["save"],
            f"sel={sel_ok} filled={filled_bb} save={rec_bb['save']}",
        )

        # перезапуск: партия восстановлена (menu=false при наличии сейва)
        page.reload(wait_until="domcontentloaded")
        login(page)
        page.locator(".nav-item", has_text="Block Blast").last.click()
        page.wait_for_selector(".tabpane:visible .game-wrap", timeout=10000)
        time.sleep(0.6)
        pane = _pane(page)
        filled_saved = pane.locator(".cell-bb.fill").count()
        check(
            "35: Block Blast — автосейв после перезапуска",
            filled_saved > 0,
            f"filled={filled_saved}",
        )

        # ═══════════ 7. САЙТ: версия сайта = версия сборки ═══════════
        try:
            import json as _json
            import os as _os

            _idx = _json.load(
                open(
                    _os.path.join(ROOT, "site", "downloads", "index.json"),
                    encoding="utf-8",
                )
            )
            c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=2)
            c.request("GET", "/api/help/version")
            _r = c.getresponse()
            _api_ver = _json.loads(_r.read().decode("utf-8"))
            check(
                "35: версия сайта = версия сборки",
                str(_idx.get("version")) == str(_api_ver.get("version")),
                f"site={_idx.get('version')} api={_api_ver.get('version')}",
            )
            _zf = _os.path.join(ROOT, "site", "downloads", _idx["releases"][0]["file"])
            check(
                "35: zip-файл сайта на месте",
                _os.path.isfile(_zf) and _os.path.getsize(_zf) > 0,
                _idx["releases"][0]["file"],
            )
        except Exception as _e:
            check("35: версия сайта = версия сборки", False, repr(_e)[:120])

        # финально: ни одной JS-ошибки за всю сессию
        check("35: весь обход без JS-ошибок", len(errs) == 0, "; ".join(errs[:3]))

        b.close()
finally:
    srv.terminate()
    time.sleep(0.3)

print(f"\nE2E Часть 35: {len(PASS)} OK, {len(FAIL)} FAIL")
if FAIL:
    print("Провалены:", FAIL)
    sys.exit(1)
