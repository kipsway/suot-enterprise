/* SUOT Neo — мини-игра «Block Blast» на поле 8×8 (Часть 32).
   Механика по ТЗ: поле 8×8 без таймера и гравитации; лоток ровно из 3 фигур,
   новая тройка только после размещения всех трёх; drag&drop + клик-размещение
   с проекционной тенью; полные строки/столбцы сгорают синхронно (8 строк И 8
   столбцов за прогон), без гравитации; счёт = 1 очко/кубик + 10·N² за N линий +
   бонус серии комбо (серия·10/шаг, сброс при ходе без сгорания); автосейв после
   каждого действия (занятые ячейки, лоток, счёт, рекорд, серия). */

window.gameBlockBlastPage = function () {
  const N = 8;
  const KEY = "suot_game_bb";
  const COLORS = ["var(--g-b-1)", "var(--g-b-2)", "var(--g-b-3)",
    "var(--g-b-4)", "var(--g-b-5)", "var(--g-b-6)", "var(--g-b-7)"];

  /* ── полимино: базовые формы [(dr,dc)] ── */
  const BASE_SHAPES = [
    [[0, 0]],                                              // единица
    [[0, 0], [0, 1]],                                      // линия 2
    [[0, 0], [0, 1], [0, 2]],                             // линия 3
    [[0, 0], [0, 1], [0, 2], [0, 3]],                      // линия 4
    [[0, 0], [0, 1], [0, 2], [0, 3], [0, 4]],              // линия 5
    [[0, 0], [0, 1], [1, 0], [1, 1]],                      // квадрат 2×2
    [[0, 0], [0, 1], [0, 2], [1, 0], [1, 1], [1, 2],
     [2, 0], [2, 1], [2, 2]],                              // квадрат 3×3
    [[0, 0], [0, 1], [0, 2], [1, 0]],                      // угол L
    [[0, 0], [1, 0], [1, 1], [1, 2]],                      // угол L (зеркальный)
    [[0, 0], [0, 1], [0, 2], [1, 1]],                      // T
    [[0, 1], [0, 2], [1, 0], [1, 1]],                      // ступень S
    [[0, 0], [0, 1], [1, 1], [1, 2]],                      // ступень Z
    [[0, 0], [0, 1], [0, 2], [1, 0], [1, 1]],              // L+ (пятиклеточный)
  ];

  function rot90(cells) {
    // поворот по часовой: (r,c) → (c, maxR - r)
    let maxR = 0;
    cells.forEach(([r, c]) => { if (r > maxR) maxR = r; });
    return cells.map(([r, c]) => [c, maxR - r]);
  }
  function norm(cells) {
    let minR = 0, minC = 0;
    cells.forEach(([r, c]) => {
      if (r < minR) minR = r;
      if (c < minC) minC = c;
    });
    const out = cells.map(([r, c]) => [r - minR, c - minC]);
    out.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
    return out;
  }
  function keyOf(cells) {
    return norm(cells).map(([r, c]) => r + ":" + c).join("|");
  }
  /* пул всех форм во всех уникальных поворотах */
  function buildPool() {
    const pool = [];
    const seen = {};
    BASE_SHAPES.forEach((shape) => {
      let cur = shape;
      for (let k = 0; k < 4; k++) {
        const kk = keyOf(cur);
        if (!seen[kk]) { seen[kk] = 1; pool.push(norm(cur)); }
        cur = rot90(cur);
      }
    });
    return pool;
  }
  const POOL = buildPool();

  function randomShape() {
    return POOL[Math.floor(Math.random() * POOL.length)]
      .map(([r, c]) => [r, c]);
  }
  function newTray() {
    const tray = [];
    for (let i = 0; i < 3; i++) tray.push({
      cells: randomShape(), color: COLORS[i % COLORS.length],
    });
    return tray;
  }

  function emptyGrid() {
    const g = [];
    for (let r = 0; r < N; r++) {
      const row = [];
      for (let c = 0; c < N; c++) row.push("");
      g.push(row);
    }
    return g;
  }
  function cloneGrid(g) {
    return g.map((row) => row.slice());
  }
  /* можно ли поставить cells так, чтобы верхний-левый край фигуры был в (br,bc) */
  function canPlace(g, cells, br, bc) {
    for (let i = 0; i < cells.length; i++) {
      const r = br + cells[i][0];
      const c = bc + cells[i][1];
      if (r < 0 || r >= N || c < 0 || c >= N) return false;
      if (g[r][c]) return false;
    }
    return true;
  }
  function placeCells(g, cells, br, bc, color) {
    const out = cloneGrid(g);
    cells.forEach(([dr, dc]) => { out[br + dr][bc + dc] = color; });
    return out;
  }
  /* полные строки/столбцы (все 8 заняты) — сгорают синхронно */
  function burnLines(g) {
    const burnR = [];
    const burnC = [];
    for (let r = 0; r < N; r++) {
      if (g[r].every((v) => v)) burnR.push(r);
    }
    for (let c = 0; c < N; c++) {
      let full = true;
      for (let r = 0; r < N; r++) if (!g[r][c]) { full = false; break; }
      if (full) burnC.push(c);
    }
    const out = cloneGrid(g);
    burnR.forEach((r) => { for (let c = 0; c < N; c++) out[r][c] = ""; });
    burnC.forEach((c) => { for (let r = 0; r < N; r++) out[r][c] = ""; });
    return { out, rows: burnR, cols: burnC };
  }
  function anyPlace(g, tray) {
    for (let i = 0; i < tray.length; i++) {
      const cells = tray[i].cells;
      for (let r = 0; r < N; r++)
        for (let c = 0; c < N; c++)
          if (canPlace(g, cells, r, c)) return true;
    }
    return false;
  }

  return {
    N: N,
    idx: Array.from({ length: N * N }, (_, i) => i),
    grid: emptyGrid(),
    tray: [],
    active: -1,           // выбранный слот лотка (-1 = нет)
    score: 0,
    best: 0,
    comboSeq: 0,          // текущая непрерывная серия сгораний
    over: false,
    menu: true,
    showRecords: false,
    records: [],
    soundOn: true,
    vibrationOn: true,
    icons: window.ICONS,
    ru: (a, b) => I18N.lang === "ru" ? a : b,

    /* ── инициализация ── */
    init() {
      this.loadPrefs();
      this.loadRecords();
      const saved = this.loadSave();
      if (saved) {
        this.grid = saved.grid || emptyGrid();
        this.tray = saved.tray && saved.tray.length ? saved.tray : newTray();
        this.score = saved.score || 0;
        this.over = !!saved.over;
        this.comboSeq = saved.comboSeq || 0;
      } else {
        this.grid = emptyGrid();
        this.tray = newTray();
      }
      this.best = Math.max(this.loadBest(), this.score);
      this.menu = !saved;
      this._bindPersist();
    },

    /* ── префы ── */
    toggleSound() {
      this.soundOn = !this.soundOn;
      this.savePrefs();
    },
    toggleVibro() {
      this.vibrationOn = !this.vibrationOn;
      this.savePrefs();
    },
    savePrefs() {
      try {
        localStorage.setItem("suot_game_bb_prefs", JSON.stringify({
          sound: this.soundOn, vibro: this.vibrationOn }));
      } catch (e) {}
    },
    loadPrefs() {
      try {
        const p = JSON.parse(localStorage.getItem("suot_game_bb_prefs") || "{}");
        this.soundOn = p.sound !== false;
        this.vibrationOn = p.vibro !== false;
      } catch (e) {}
    },
    _sfx(kind) {
      if (!this.soundOn) return;
      try {
        const AC = window.AudioContext || window.webkitAudioContext;
        const ctx = new AC();
        const o = ctx.createOscillator();
        const g = ctx.createGain();
        o.type = "sine";
        o.frequency.value = kind === "line" ? 760 : kind === "place" ? 420 : 340;
        g.gain.value = 0.12;
        g.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.14);
        o.connect(g); g.connect(ctx.destination);
        o.start();
        o.stop(ctx.currentTime + 0.16);
      } catch (e) {}
    },
    _vibrate(ms) {
      if (!this.vibrationOn) return;
      try { if (navigator.vibrate) navigator.vibrate(ms); } catch (e) {}
    },

    /* ── рекорды ── */
    loadBest() {
      try {
        const r = JSON.parse(localStorage.getItem("suot_game_bb_records") || "[]");
        return r.length ? Math.max.apply(null, r.map((x) => x.score || 0)) : 0;
      } catch (e) { return 0; }
    },
    loadRecords() {
      try {
        this.records = JSON.parse(
          localStorage.getItem("suot_game_bb_records") || "[]");
        if (!Array.isArray(this.records)) this.records = [];
      } catch (e) { this.records = []; }
    },
    recordScore() {
      if (this.score > this.best) this.best = this.score;
      const entry = { score: this.score, date: new Date().toISOString() };
      this.records.push(entry);
      this.records.sort((a, b) => (b.score || 0) - (a.score || 0));
      this.records = this.records.slice(0, 10);
      try {
        localStorage.setItem("suot_game_bb_records",
          JSON.stringify(this.records));
      } catch (e) {}
    },

    /* ── автосейв ── */
    saveSave() {
      try {
        localStorage.setItem(KEY, JSON.stringify({
          grid: this.grid, tray: this.tray, score: this.score,
          comboSeq: this.comboSeq, over: this.over, best: this.best,
          ts: Date.now(),
        }));
      } catch (e) {}
    },
    loadSave() {
      try {
        const raw = localStorage.getItem(KEY);
        if (!raw) return null;
        const d = JSON.parse(raw);
        if (!d || !d.grid || d.grid.length !== N) return null;
        return d;
      } catch (e) { return null; }
    },
    removeSave() {
      try { localStorage.removeItem(KEY); } catch (e) {}
    },
    _bindPersist() {
      const save = () => { if (!this.menu && !this.over) this.saveSave(); };
      window.addEventListener("beforeunload", save);
      document.addEventListener("visibilitychange", () => {
        if (document.hidden) save();
      });
    },

    /* ── меню ── */
    newGame() {
      this.grid = emptyGrid();
      this.tray = newTray();
      this.score = 0;
      this.over = false;
      this.comboSeq = 0;
      this.active = -1;
      this.menu = false;
      this.removeSave();
      this.saveSave();
    },
    continueGame() {
      const saved = this.loadSave();
      if (!saved || saved.over) { this.newGame(); return; }
      this.grid = saved.grid || emptyGrid();
      this.tray = saved.tray && saved.tray.length ? saved.tray : newTray();
      this.score = saved.score || 0;
      this.over = !!saved.over;
      this.comboSeq = saved.comboSeq || 0;
      this.menu = false;
    },
    openRecords() {
      this.loadRecords();
      this.best = this.loadBest() || this.best;
    },
    toMenu() {
      if (!this.over) this.saveSave();
      this.menu = true;
    },
    hasSavedGame() {
      const s = this.loadSave();
      return !!(s && s.grid && !s.over);
    },

    /* ── выбор фигуры ── */
    selectSlot(i) {
      if (this.menu || this.over) return;
      this.active = this.active === i ? -1 : i;
    },

    /* ── drag&drop: перетаскивание фигуры на доску ── */
    dragging: false,
    dMoved: false,
    dragX: 0,
    dragY: 0,
    ghostCell: 36,
    bumpSlot: -1,
    grabPiece(i, e) {
      if (this.menu || this.over) return;
      this.active = i;
      this.dragging = true;
      this.dMoved = false;
      this.dragX = e.clientX;
      this.dragY = e.clientY;
      const board = document.querySelector("[data-gbb-board]");
      if (board) this.ghostCell = Math.max(14, board.getBoundingClientRect().width / N);
      this._pm = (ev) => this._dragMove(ev);
      this._pu = (ev) => this._dragUp(ev);
      window.addEventListener("pointermove", this._pm);
      window.addEventListener("pointerup", this._pu);
      try { e.currentTarget.setPointerCapture(e.pointerId); } catch (err) {}
    },
    _dragMove(e) {
      if (!this.dragging) return;
      const dx = e.clientX - this.dragX;
      const dy = e.clientY - this.dragY;
      if (dx * dx + dy * dy > 64) this.dMoved = true;
      this.dragX = e.clientX;
      this.dragY = e.clientY;
      const board = document.querySelector("[data-gbb-board]");
      if (!board) return;
      const rect = board.getBoundingClientRect();
      const cell = rect.width / N;
      const c = Math.floor((e.clientX - rect.left) / cell);
      const r = Math.floor((e.clientY - rect.top) / cell);
      if (r >= 0 && r < N && c >= 0 && c < N) this.setHover(r, c);
      else this.clearHover();
    },
    _dragUp() {
      if (!this.dragging) return;
      window.removeEventListener("pointermove", this._pm);
      window.removeEventListener("pointerup", this._pu);
      this._pm = this._pu = null;
      const cell = this.hoverCells.length ? this.hoverCells[0] : null;
      const moved = this.dMoved;
      this.dragging = false;
      if (moved && cell) {
        this.place(cell[0], cell[1]);
      } else {
        this.clearHover();
        if (moved) {              // анимированный возврат в слот
          this.bumpSlot = this.active;
          this._btimer = setTimeout(() => { this.bumpSlot = -1; }, 460);
        }
      }
    },
    ghostColor() {
      const t = this.tray[this.active];
      return t ? t.color : "var(--g-b-1)";
    },
    ghostStyle() {
      return {
        left: (this.dragX + 10) + "px",
        top: (this.dragY + 10) + "px",
        "--gc": this.ghostCell + "px",
        "--pc": this.ghostColor(),
      };
    },
    destroy() {
      if (this._btimer) clearTimeout(this._btimer);
      if (this._pm) window.removeEventListener("pointermove", this._pm);
      if (this._pu) window.removeEventListener("pointerup", this._pu);
    },

    /* ── проекционная тень подсветки ячеек ── */
    hoverCells: [],         // [[r,c], ...] под курсором
    setHover(br, bc) {
      this.hoverCells = [];
      if (this.active < 0 || !this.tray[this.active]) return;
      const cells = this.tray[this.active].cells;
      const ok = canPlace(this.grid, cells, br, bc);
      this.hoverCells = ok ? cells.map(([dr, dc]) => [br + dr, bc + dc]) : [];
    },
    clearHover() {
      this.hoverCells = [];
    },
    inHover(r, c) {
      for (let i = 0; i < this.hoverCells.length; i++) {
        if (this.hoverCells[i][0] === r && this.hoverCells[i][1] === c)
          return true;
      }
      return false;
    },
    cellAt(n) {
      return this.grid[Math.floor(n / 8)][n % 8];
    },
    hoverAt(n) {
      return this.inHover(Math.floor(n / 8), n % 8);
    },

    /* ── размещение ── */
    place(br, bc) {
      if (this.menu || this.over || this.active < 0) return;
      const shape = this.tray[this.active];
      if (!shape || !canPlace(this.grid, shape.cells, br, bc)) { return; }

      const base = shape.cells.length;                        // 1 очко/кубик
      this.grid = placeCells(this.grid, shape.cells, br, bc, shape.color);

      const burn = burnLines(this.grid);
      if (burn.rows.length || burn.cols.length) {
        this.grid = burn.out;
        const nLines = burn.rows.length + burn.cols.length;
        this.comboSeq += 1;
        const linePoints = 10 * nLines * nLines;              // 2→40, 3→90, 4→160
        const comboBonus = this.comboSeq * 10;                // серия·10
        const total = base + linePoints + comboBonus;
        this.score += total;
        this.lastGain = total;
        this.lastLine = nLines;
        this.lastCombo = this.comboSeq;
        this._sfx("line");
        this._vibrate(40);
      } else {
        this.comboSeq = 0;                                    // сброс серии
        this.lastGain = base;
        this.lastLine = 0;
        this.lastCombo = 0;
        this.score += base;
        this._sfx("place");
        this._vibrate(15);
      }
      if (this.score > this.best) this.best = this.score;

      /* убираем размещённую фигуру из лотка */
      this.tray.splice(this.active, 1);
      this.active = -1;

      /* лоток пуст → новая тройка */
      if (!this.tray.length) this.tray = newTray();

      /* поражение: ни одну из оставшихся фигур нельзя разместить */
      if (!anyPlace(this.grid, this.tray)) {
        this.over = true;
        this.recordScore();
      } else {
        this.recordScore();
        this.saveSave();
      }
    },

    /* статистика для меню */
    maxScore() { return this.best; },
    _fmtDate(iso) {
      if (!iso) return "";
      const d = new Date(iso);
      const months = I18N.lang === "ru"
        ? ["янв","фев","мар","апр","май","июн","июл","авг","сен","окт","ноя","дек"]
        : ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
      return (d.getDate() < 10 ? "0" + d.getDate() : d.getDate()) + " " +
        months[d.getMonth()] + " " + d.getFullYear();
    },
    cellsFilled() {
      let n = 0;
      for (let r = 0; r < N; r++)
        for (let c = 0; c < N; c++)
          if (this.grid[r][c]) n++;
      return n;
    },
    trayMini(i) {
      const t = this.tray[i];
      if (!t) return [];
      const minR = Math.min.apply(null, t.cells.map((c) => c[0]));
      const minC = Math.min.apply(null, t.cells.map((c) => c[1]));
      const maxR = Math.max.apply(null, t.cells.map((c) => c[0]));
      const maxC = Math.max.apply(null, t.cells.map((c) => c[1]));
      const rows = maxR - minR + 1;
      const cols = maxC - minC + 1;
      const m = [];
      for (let r = 0; r < rows; r++) {
        const row = [];
        for (let c = 0; c < cols; c++) row.push(0);
        m.push(row);
      }
      t.cells.forEach(([dr, dc]) => { m[dr - minR][dc - minC] = 1; });
      return m;
    },
  };
};
window.gameBlockBlast = window.gameBlockBlastPage;   // alias для тестов