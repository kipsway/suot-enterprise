"""E2E Фаза 2 (полировка): наложения интерактивных элементов
(виды x темы x ширины) + порядок кнопок в модалках/тулбарах.
Ноль JS-ошибок."""

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

TMPD = tempfile.mkdtemp(prefix="suot_polish_")
SHOTD = os.path.join(TMPD, "shots")
os.makedirs(SHOTD, exist_ok=True)
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


OVERLAP_JS = """() => {
  const visAt = (el, x, y) => {
    // точка видна, если её не обрезает ни один overflow-предок
    let n = el.parentElement;
    while (n && n !== document.body) {
      let cs = null;
      try { cs = getComputedStyle(n); } catch (_) { break; }
      const ox = cs.overflowX, oy = cs.overflowY;
      if (ox === 'auto' || ox === 'scroll' || ox === 'hidden' ||
          oy === 'auto' || oy === 'scroll' || oy === 'hidden') {
        const r = n.getBoundingClientRect();
        if (x < r.left || x > r.right || y < r.top || y > r.bottom) return false;
      }
      n = n.parentElement;
    }
    return true;
  };
  const els = [...document.querySelectorAll(
    'button, input, select, textarea, a, .nav-item')]
    .filter(e => {
      const r = e.getBoundingClientRect();
      if (r.width < 4 || r.height < 4) return false;
      if (r.width >= window.innerWidth - 2) return false;
      const cs = getComputedStyle(e);
      if (cs.visibility === 'hidden' || cs.display === 'none') return false;
      return true;
    });
  const desc = (e) => (e.tagName.toLowerCase() + '.' +
    (e.className && e.className.baseVal === undefined
      ? String(e.className).split(' ').slice(0, 2).join('.') : '') +
    ' "' + (e.innerText || e.value || e.placeholder || '').slice(0, 24) + '"');
  const bad = [];
  for (let i = 0; i < els.length; i++) {
    for (let j = i + 1; j < els.length; j++) {
      const a = els[i], b = els[j];
      if (a.contains(b) || b.contains(a)) continue;
      const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
      const ix = Math.max(0, Math.min(ra.right, rb.right) - Math.max(ra.left, rb.left));
      const iy = Math.max(0, Math.min(ra.bottom, rb.bottom) - Math.max(ra.top, rb.top));
      if (ix < 3 || iy < 3) continue; // касание краёв — не наложение
      const area = ix * iy;
      const small = Math.min(ra.width * ra.height, rb.width * rb.height);
      if (area > 120 && area > small * 0.15) {
        // один внутри оверлея/модалки, другой снаружи — слои, не баг
        const la = a.closest('.overlay,.modal,.palette-panel,.ctx-menu,.tooltip,.tour-layer');
        const lb = b.closest('.overlay,.modal,.palette-panel,.ctx-menu,.tooltip,.tour-layer');
        if (!!la !== !!lb) continue;
        // пересечение rect ≠ видимость: под overflow-скроллом элементы
        // обрезаны. Реально только то, что хиттится в точке пересечения,
        // причём оба элемента должны быть видимы в ней.
        const cx = Math.max(ra.left, rb.left) + ix / 2;
        const cy = Math.max(ra.top, rb.top) + iy / 2;
        if (!visAt(a, cx, cy) || !visAt(b, cx, cy)) continue;
        let hit = null;
        try { hit = document.elementFromPoint(cx, cy); } catch (_) {}
        if (!hit || (hit !== a && hit !== b && !a.contains(hit) && !b.contains(hit)))
          continue;
        bad.push(desc(a) + '  X  ' + desc(b));
        if (bad.length >= 6) return bad;
      }
    }
  }
  return bad;
}"""

FOOT_JS = """() => {
  const bad = [];
  [...document.querySelectorAll('.modal-foot')].forEach((f) => {
    if (!f.getClientRects().length) return;
    const btns = [...f.querySelectorAll('button')]
      .filter((b) => !!b.getClientRects().length);
    if (btns.length > 1) {
      const last = btns[btns.length - 1];
      if (!last.classList.contains('primary'))
        bad.push('last-not-primary: ' + btns.map((b) => b.innerText.slice(0, 14)).join('|'));
    }
  });
  return bad;
}"""


def _overlaps(page, tag):
    bad = page.evaluate(OVERLAP_JS)
    if bad:
        page.screenshot(path=os.path.join(SHOTD, tag + ".png"))
    return bad


try:
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for theme in ("dark", "light"):
            ctx = browser.new_context(viewport={"width": 1500, "height": 900})
            page = ctx.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.add_init_script(
                f"localStorage.setItem('suot_token', '{TOKEN}');"
                f"localStorage.setItem('suot_theme', '{theme}');"
            )
            page.goto(BASE_URL + "/", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_selector(".shell", timeout=15000)
            time.sleep(2.0)
            try:
                page.wait_for_selector(".tour-layer", timeout=3500)
                page.keyboard.press("Escape")
                time.sleep(0.5)
            except Exception:
                pass

            for width in (1280, 1920):
                page.set_viewport_size({"width": width, "height": 900})
                time.sleep(0.8)
                # дашборд
                page.locator(".nav-item", has_text="Дашборд").first.click()
                page.wait_for_selector(".dash-widgets", timeout=10000)
                time.sleep(1.0)
                bad = _overlaps(page, f"{theme}-{width}-dash")
                check(
                    f"наложения дашборд [{theme} {width}]", not bad, "; ".join(bad[:2])
                )
                # таблица + bulkbar + меню
                page.locator(".nav-item", has_text="Сотрудники").first.click()
                page.wait_for_selector("table.grid:visible", timeout=10000)
                time.sleep(1.0)
                boxes = page.locator(".tabpane:visible tbody .cbx")
                if boxes.count():
                    boxes.first.check()
                    time.sleep(0.5)
                bad = _overlaps(page, f"{theme}-{width}-table")
                check(
                    f"наложения таблица [{theme} {width}]", not bad, "; ".join(bad[:2])
                )
                # центр документов
                page.locator(".nav-item", has_text="Документы").first.click()
                page.wait_for_selector(".doc-center", timeout=10000)
                time.sleep(1.0)
                bad = _overlaps(page, f"{theme}-{width}-docs")
                check(
                    f"наложения документы [{theme} {width}]",
                    not bad,
                    "; ".join(bad[:2]),
                )

            # порядок кнопок в футерах (одна ширина достаточно)
            page.set_viewport_size({"width": 1500, "height": 900})
            page.evaluate(
                "() => document.dispatchEvent(new CustomEvent('suot-open-settings',"
                " {bubbles: true}))"
            )
            page.wait_for_selector(".sc-modal", timeout=10000)
            time.sleep(0.8)
            bad = page.evaluate(FOOT_JS)
            check(f"футеры модалок [{theme}]", not bad, "; ".join(bad[:2]))
            page.keyboard.press("Escape")

            js_err = [e for e in errors if "favicon" not in e.lower()]
            check(f"нет JS-ошибок [{theme}]", not js_err, "; ".join(js_err[:2]))
            ctx.close()
        browser.close()
finally:
    cleanup()

print(f"\n{len(PASS)} OK, {len(FAIL)} FAIL (shots: {SHOTD})")
sys.exit(1 if FAIL else 0)
