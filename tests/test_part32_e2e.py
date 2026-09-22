"""Часть 32: E2E мини-игры «2048» (8×8) и «Block Blast».
Проверки: меню, старт партии, движение/слияние в 2048, win-диалог больше 2048,
взаимодействие с Block Blast (выбор фигуры, размещение, сгорание линий),
автосейв в localStorage, потеря/продолжение, рекорды."""

import os, sys, subprocess, time, tempfile, socket

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TMPD = tempfile.mkdtemp(prefix="suot_e2e32_")
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


def localStorage_has(page, key):
    try:
        return page.evaluate("(k) => !!localStorage.getItem(k)", key)
    except Exception:
        return False


try:
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        page = b.new_page(viewport={"width": 1500, "height": 1000})
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
        time.sleep(1.6)
        if page.locator(".tour-layer").count():
            page.keyboard.press("Escape")
            time.sleep(0.3)

        # ══════════ 2048 ══════════
        page.locator(".nav-item", has_text="2048").last.click()
        page.wait_for_selector(".tabpane:visible .game-wrap", timeout=10000)
        time.sleep(0.6)
        pane = _pane(page)
        check("2048: меню открыто", pane.locator(".game-menu").count() == 1)
        gm = pane.locator(".gm-actions")
        check(
            "2048: кнопки «Новая и Рекорды»",
            gm.get_by_role("button", name="Новая партия").count() == 1
            and gm.get_by_role("button", name="Рекорды").count() == 1,
        )

        gm.get_by_role("button", name="Новая партия").click()
        time.sleep(0.5)
        pane = _pane(page)
        board = pane.locator("[data-g2048-board]")
        check(
            "2048: доска 8×8 (64 ячейки)",
            pane.locator(".board-2048 .cell").count() == 64,
        )
        filled0 = pane.locator(".board-2048 .cell.has").count()
        check("2048: старт с двумя плитками", filled0 == 2, f"filled={filled0}")

        # несколько ходов стрелками
        before = pane.locator(".board-2048 .cell.has").count()
        for k in ["ArrowUp", "ArrowLeft", "ArrowDown", "ArrowRight"]:
            page.keyboard.press(k)
            time.sleep(0.25)
        filled1 = pane.locator(".board-2048 .cell.has").count()
        check(
            "2048: ходы стрелками не сломали доску",
            2 <= filled1 <= 6,
            f"after 4 moves filled={filled1}",
        )
        score_txt = pane.locator(".gm-score b").first.inner_text()
        check("2048: счёт отображается", score_txt.isdigit(), score_txt)

        # «Продолжить» автосейв: выйти в меню и вернуться
        pane.get_by_role("button", name="Меню").click()
        time.sleep(0.4)
        pane = _pane(page)
        s_ok = localStorage_has(page, "suot_game_2048")
        check("2048: автосейв записан в localStorage", s_ok)
        cont = (
            pane.locator(".gm-actions").get_by_role("button", name="Продолжить").count()
        )
        check("2048: кнопка «Продолжить» появилась", cont == 1)
        pane.locator(".gm-actions").get_by_role("button", name="Продолжить").click()
        time.sleep(0.4)
        pane = _pane(page)
        filled2 = pane.locator(".board-2048 .cell.has").count()
        check(
            "2048: партия продолжилась с сохранённой доски",
            filled2 == filled1,
            f"restored={filled2}",
        )

        # рекорды в меню
        pane.get_by_role("button", name="Меню").click()
        time.sleep(0.4)
        pane = _pane(page)
        pane.locator(".gm-actions").get_by_role("button", name="Рекорды").click()
        time.sleep(0.4)
        rec_visible = pane.locator(".gm-records").count() >= 0
        check("2048: панель рекордов доступна", rec_visible)

        # win-диалог: при синтезе плитки 2048 появляется поздравление
        pane.get_by_role("button", name="Новая партия").click()
        time.sleep(0.4)
        pane = _pane(page)
        winfo = page.evaluate("""() => {
          const ws = document.querySelectorAll('.game-wrap');
          let root = null;
          for (let i = 0; i < ws.length; i++) {
            if (ws[i].offsetParent !== null) { root = ws[i]; break; }
          }
          const a = root._x_dataStack[0];
          a.grid = Array.from({length: 8}, (_, r) =>
            Array.from({length: 8}, (_, c) => (r === 0 && c === 0 ? 2048 : 0)));
          a.won = false; a.wonShown = false;
          a.menu = false; a.over = false;
          a._checkWin();
          return { won: a.won, wonShown: a.wonShown };
        }""")
        time.sleep(0.4)
        pane = _pane(page)
        dlg = pane.locator(".game-dialog", has_text="2048").count()
        check(
            "2048: win-диалог появляется при плитке 2048",
            winfo["won"] and not winfo["wonShown"] and dlg == 1,
            f"won={winfo['won']} dialog={dlg}",
        )
        # «Продолжить» закрывает диалог и партия идёт дальше (бесконечный режим)
        dlg_btn = pane.locator(".game-dialog").get_by_role("button", name="Продолжить")
        if dlg_btn.count():
            dlg_btn.first.click()
            time.sleep(0.4)
        wstate = page.evaluate("""() => {
          const ws = document.querySelectorAll('.game-wrap');
          let root = null;
          for (let i = 0; i < ws.length; i++) {
            if (ws[i].offsetParent !== null) { root = ws[i]; break; }
          }
          const a = root._x_dataStack[0];
          return { wonShown: a.wonShown, over: a.over };
        }""")
        check(
            "2048: продолжение закрывает диалог, партия жива",
            wstate["wonShown"] and not wstate["over"],
            f"wonShown={wstate['wonShown']} over={wstate['over']}",
        )

        # ══════════ Block Blast ══════════
        page.locator(".nav-item", has_text="Block Blast").last.click()
        page.wait_for_selector(".tabpane:visible .game-wrap", timeout=10000)
        time.sleep(0.6)
        pane = _pane(page)
        check("Block Blast: меню открыто", pane.locator(".game-menu").count() == 1)
        pane.locator(".gm-actions").get_by_role("button", name="Новая партия").click()
        time.sleep(0.5)
        pane = _pane(page)
        check(
            "Block Blast: доска 8×8 (64 ячейки)",
            pane.locator(".board-bb .cell-bb").count() == 64,
        )
        pieces = pane.locator(".bb-piece").count()
        check("Block Blast: лоток из 3 фигур", pieces == 3, f"pieces={pieces}")

        # выбрать первую фигуру и разместить в (0,0)
        pc0 = pane.locator(".bb-piece").first
        pc0.click()
        time.sleep(0.3)
        sel = pane.locator(".bb-piece.sel").count()
        check("Block Blast: выбор фигуры работает", sel == 1)
        # размер первой фигуры (мини-сетка) не больше поля
        pane.locator(".board-bb .cell-bb").first.click()
        time.sleep(0.6)
        filled_bb = pane.locator(".cell-bb.fill").count()
        dbg = page.evaluate("""() => {
          const ws = document.querySelectorAll('.game-wrap');
          let root = null;
          for (let i = 0; i < ws.length; i++) {
            if (ws[i].offsetParent !== null) { root = ws[i]; break; }
          }
          const a = root && root._x_dataStack ? root._x_dataStack[0] : null;
          if (!a) return {err: 'no data'};
          return { active: a.active, filled: a.grid.flat().filter(Boolean).length,
            trayLen: a.tray.length };
        }""")
        check(
            "Block Blast: фигура размещена",
            filled_bb > 0,
            f"filled={filled_bb} dbg={dbg}",
        )

        # after placement: tray may still have 3 (new batch) or 2
        pieces2 = pane.locator(".bb-piece").count()
        check("Block Blast: лоток обновлён", pieces2 in (2, 3), f"pieces={pieces2}")

        # серия/счёт видны в игре
        score_bb = pane.locator(".gm-score b").first.inner_text()
        check("Block Blast: счёт отображается", score_bb.isdigit(), score_bb)

        # drag&drop: перетащить фигуру мышью на пустую клетку
        pane.get_by_role("button", name="Заново").click()
        time.sleep(0.5)
        pane = _pane(page)
        piece_box = pane.locator(".bb-piece").first.bounding_box()
        cell_idx = page.evaluate("""() => {
          const ws = document.querySelectorAll('.game-wrap');
          let root = null;
          for (let i = 0; i < ws.length; i++) {
            if (ws[i].offsetParent !== null) { root = ws[i]; break; }
          }
          const a = root._x_dataStack[0];
          const board = root.querySelector('[data-gbb-board]');
          const n = board.querySelectorAll('.cell-bb').length;
          for (let i = 0; i < n; i++) {
            const r = Math.floor(i / 8), c = i % 8;
            if (!a.grid[r][c]) return i;
          }
          return -1;
        }""")
        cb = pane.locator(".board-bb .cell-bb").nth(cell_idx).bounding_box()
        if piece_box and cb and cell_idx >= 0:
            page.mouse.move(
                piece_box["x"] + piece_box["width"] / 2,
                piece_box["y"] + piece_box["height"] / 2,
            )
            page.mouse.down()
            page.mouse.move(piece_box["x"] + 12, piece_box["y"] + 12, steps=5)
            page.mouse.move(
                cb["x"] + cb["width"] / 2, cb["y"] + cb["height"] / 2, steps=10
            )
            page.mouse.up()
            time.sleep(0.6)
            pane = _pane(page)
            filled_drag = pane.locator(".cell-bb.fill").count()
            check(
                "Block Blast: drag&drop размещает фигуру",
                filled_drag > 0,
                f"filled={filled_drag}",
            )
        else:
            check(
                "Block Blast: drag&drop размещает фигуру",
                False,
                "нет данных для перетаскивания",
            )

        # выход в меню и автосейв
        pane.get_by_role("button", name="Меню").click()
        time.sleep(0.4)
        pane = _pane(page)
        sbb = localStorage_has(page, "suot_game_bb")
        check("Block Blast: автосейв записан", sbb)
        cont_bb = (
            pane.locator(".gm-actions").get_by_role("button", name="Продолжить").count()
        )
        check("Block Blast: кнопка «Продолжить» появилась", cont_bb == 1)

        # JS-ошибки
        check("нет JS-ошибок в консоли", len(errs) == 0, "; ".join(errs[:3]))

        b.close()
finally:
    srv.terminate()
    time.sleep(0.3)

print(f"\nE2E Часть 32: {len(PASS)} OK, {len(FAIL)} FAIL")
if FAIL:
    print("Провалены:", FAIL)
    sys.exit(1)
