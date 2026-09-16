/* SUOT Neo — мини-игра «2048» на поле 8×8 (Часть 32).
   Механика: полное совпадение с описанием ТЗ — 2 стартовые плитки (90% «2»/10% «4»),
   строгая однократность слияний за ход, приоритет ближним к целевой стороне,
   новая плитка только при реальном движении, счёт по номиналам слияний,
   диалог при первой «2048» (рестарт/продолжить), поражение при блокировке поля,
   автосейв состояния после каждого хода и при закрытии/сворачивании. */

window.game2048Page = function () {
  const N = 8;                       // размер поля 8×8 (64 слота)
  const KEY = "suot_game_2048";      // ключ автосейва

  /* Каскадная матовая эстетика: класс плитки по номиналу */
  function tileCls(v) {
    if (v <= 0) return "";
    if (v < 8) return "tk-" + v;
    if (v >= 16384) return "tk-super";
    return "tk-" + v;
  }
  function tileText(v) {
    return v > 0 ? String(v) : "";
  }
  /* Автоуменьшение шрифта по разрядности */
  function tileFont(v) {
    const len = String(v).length;
    if (len >= 8) return "15px";
    if (len >= 7) return "17px";
    if (len >= 6) return "20px";
    if (len >= 5) return "23px";
    return "";
  }

  function emptyGrid() {
    const g = [];
    for (let r = 0; r < N; r++) {
      const row = [];
      for (let c = 0; c < N; c++) row.push(0);
      g.push(row);
    }
    return g;
  }

  function gridClone(g) {
    return g.map((row) => row.slice());
  }

  function freeCells(g) {
    const out = [];
    for (let r = 0; r < N; r++)
      for (let c = 0; c < N; c++)
        if (!g[r][c]) out.push([r, c]);
    return out;
  }

  function gridHasMoves(g) {
    for (let r = 0; r < N; r++)
      for (let c = 0; c < N; c++) {
        const v = g[r][c];
        if (!v) return true;
        if (c + 1 < N && g[r][c + 1] === v) return true;
        if (r + 1 < N && g[r + 1][c] === v) return true;
      }
    return false;
  }

  return {
    N: N,
    busy: false,               // защита от двойных ходов во время анимации
    grid: emptyGrid(),         // матрица 8×8
    score: 0,
    best: 0,
    over: false,               // поражение
    won: false,                // достигнута «2048» (диалог уже показан)
    wonShown: false,           // диалог первой 2048 показан
    menu: true,                // главное меню
    showRecords: false,        // показать рекорды в меню
    records: [],
    soundOn: true,
    vibrationOn: true,
    icons: window.ICONS,
    ru: (a, b) => I18N.lang === "ru" ? a : b,

    init() {
      this.loadPrefs();
      this.loadRecords();
      const saved = this.loadSave();
      if (saved) {
        this.grid = saved.grid || emptyGrid();
        this.score = saved.score || 0;
        this.over = !!saved.over;
        this.won = !!saved.won;
        this.wonShown = !!saved.wonShown;
        this.menu = false;
      } else {
        this.menu = true;
      }
      this.best = Math.max(this.loadBest(), this.score);
      this.sx = 0;
      this.sy = 0;
      this._bindPersist();
    },
    destroy() {
      if (this._ftimer) clearTimeout(this._ftimer);
    },

    /* ── звук и вибрация ── */
    _sfx(kind) {
      if (!this.soundOn) return;
      try {
        const AC = window.AudioContext || window.webkitAudioContext;
        const ctx = new AC();
        const o = ctx.createOscillator();
        const g = ctx.createGain();
        o.type = "triangle";
        const base = kind === "merge" ? 520 : kind === "new" ? 660 : 300;
        o.frequency.value = base;
        g.gain.value = 0.14;
        g.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.12);
        o.connect(g); g.connect(ctx.destination);
        o.start();
        o.stop(ctx.currentTime + 0.14);
      } catch (e) {}
    },
    _vibrate(ms) {
      if (!this.vibrationOn) return;
      try {
        if (navigator.vibrate) navigator.vibrate(ms);
      } catch (e) {}
    },
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
        localStorage.setItem("suot_game_2048_prefs", JSON.stringify({
          sound: this.soundOn, vibro: this.vibrationOn }));
      } catch (e) {}
    },
    loadPrefs() {
      try {
        const p = JSON.parse(localStorage.getItem("suot_game_2048_prefs") || "{}");
        this.soundOn = p.sound !== false;
        this.vibrationOn = p.vibro !== false;
      } catch (e) {}
    },

    /* ── рекорды и статистика ── */
    loadBest() {
      try {
        const r = JSON.parse(localStorage.getItem("suot_game_2048_records") || "[]");
        return r.length ? Math.max.apply(null, r.map((x) => x.score || 0)) : 0;
      } catch (e) { return 0; }
    },
    loadRecords() {
      try {
        this.records = JSON.parse(
          localStorage.getItem("suot_game_2048_records") || "[]");
        if (!Array.isArray(this.records)) this.records = [];
      } catch (e) { this.records = []; }
    },
    _tryRecord() {
      if (this.score > this.best) this.best = this.score;
      const entry = { score: this.score, date: new Date().toISOString() };
      this.records.push(entry);
      this.records.sort((a, b) => (b.score || 0) - (a.score || 0));
      this.records = this.records.slice(0, 10);
      try {
        localStorage.setItem("suot_game_2048_records",
          JSON.stringify(this.records));
      } catch (e) {}
    },

    /* ── автосейв ── */
    saveSave() {
      try {
        localStorage.setItem(KEY, JSON.stringify({
          grid: this.grid, score: this.score, over: this.over,
          won: this.won, wonShown: this.wonShown, ts: Date.now(),
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
    clearSave() {
      try { localStorage.removeItem(KEY); } catch (e) {}
    },
    _bindPersist() {
      const save = () => { if (!this.menu && !this.over) this.saveSave(); };
      window.addEventListener("beforeunload", save);
      document.addEventListener("visibilitychange", () => {
        if (document.hidden) save();
      });
    },

    /* ── управление: стрелки привязаны через @keydown.window в разметке ── */
    onKey(e) {
      if (this.menu || this.over) return;
      const key = e.code || e.key;
      const dirs = {
        ArrowUp: [0, -1], KeyW: [0, -1],
        ArrowDown: [0, 1], KeyS: [0, 1],
        ArrowLeft: [-1, 0], KeyA: [-1, 0],
        ArrowRight: [1, 0], KeyD: [1, 0],
      };
      const dir = dirs[key] || dirs[e.key];
      if (!dir) return;
      e.preventDefault();
      this.move(dir[0], dir[1]);
    },
    /* свайпы: @touchstart.window / @touchend.window в разметке */
    onTouchStart(e) {
      if (!e.target.closest("[data-g2048-board]")) return;
      this.sx = e.touches[0].clientX;
      this.sy = e.touches[0].clientY;
    },
    onTouchEnd(e) {
      if (!this.sx || !e.target.closest("[data-g2048-board]")) return;
      const dx = e.changedTouches[0].clientX - this.sx;
      const dy = e.changedTouches[0].clientY - this.sy;
      const ax = Math.abs(dx), ay = Math.abs(dy);
      this.sx = 0; this.sy = 0;
      if (Math.max(ax, ay) < 30) return;
      if (ax > ay) this.move(dx > 0 ? 1 : -1, 0);
      else this.move(0, dy > 0 ? 1 : -1);
    },

    /* ── главное меню ── */
    newGame() {
      this.grid = emptyGrid();
      this.score = 0;
      this.over = false;
      this.won = false;
      this.wonShown = false;
      this.clearSave();
      this.menu = false;
      this._spawnTile();
      this._spawnTile();
      this.saveSave();
      this._flashNew("— Новая партия —");
    },
    continueGame() {
      const saved = this.loadSave();
      if (saved) {
        this.grid = saved.grid || emptyGrid();
        this.score = saved.score || 0;
        this.over = !!saved.over;
        this.won = !!saved.won;
        this.wonShown = !!saved.wonShown;
      } else {
        this.newGame();
        return;
      }
      this.menu = false;
    },
    openRecords() {
      this.loadRecords();
      this.best = this.loadBest();
    },
    toMenu() {
      if (!this.over) this.saveSave();
      this.menu = true;
    },
    hasSavedGame() {
      const s = this.loadSave();
      return !!(s && s.grid && !s.over);
    },

    _flashNew(msg) {
      this.flash = msg;
      this._ftimer = setTimeout(() => { this.flash = ""; }, 1600);
    },
    _fmtDate(iso) {
      if (!iso) return "";
      const d = new Date(iso);
      const months = I18N.lang === "ru"
        ? ["янв","фев","мар","апр","май","июн","июл","авг","сен","окт","ноя","дек"]
        : ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
      return (d.getDate() < 10 ? "0" + d.getDate() : d.getDate()) + " " +
        months[d.getMonth()] + " " + d.getFullYear();
    },

    /* ── генерация новой плитки: 90% «2» / 10% «4» ── */
    _spawnTile() {
      const free = freeCells(this.grid);
      if (!free.length) return false;
      const i = Math.floor(Math.random() * free.length);
      const [r, c] = free[i];
      this.grid[r][c] = Math.random() < 0.9 ? 2 : 4;
      this._sfx("new");
      return true;
    },

    /* ── ход: dirX = -1|0|1, dirY = -1|0|1 ── */
    move(dirX, dirY) {
      if (this.busy || this.menu || this.over) return;
      const before = gridClone(this.grid);
      let gained = 0;
      let mergedAny = false;

      /* Проход линиями. Для строк: сдвиг по горизонтали в направлении,
         для столбцов — по вертикали. В каждом ряду обрабатываем от целевой
         стороны: ближние к цели сливаются в приоритете. */
      const loop = dirX !== 0 ? this._rows() : this._cols();
      loop.forEach((line) => {
        const arr = line.map(([r, c]) => this.grid[r][c]);
        const { row, gain, moved } = this._slide(arr, dirX !== 0 ? dirX : dirY);
        if (!moved) return;
        line.forEach(([r, c], i) => {
          this.grid[r][c] = row[i];
        });
        gained += gain;
        if (gain > 0) mergedAny = true;
      });

      const movedAny = JSON.stringify(before) !== JSON.stringify(this.grid);
      if (!movedAny) return;              // ход не засчитан, генерации нет

      this.score += gained;
      if (this.score > this.best) this.best = this.score;   // рекорд в реальном времени
      this._vibrate(gained > 0 ? 30 : 10);
      if (gained > 0) this._sfx("merge");

      if (!this._spawnTile()) {
        if (!gridHasMoves(this.grid)) { this.over = true; }
      }
      this._checkWin();
      if (this.over) this._tryRecord();
      else this.saveSave();
    },

    _rows() {
      const out = [];
      for (let r = 0; r < N; r++) {
        const cells = [];
        for (let c = 0; c < N; c++) cells.push([r, c]);
        out.push(cells);
      }
      return out;
    },
    _cols() {
      const out = [];
      for (let c = 0; c < N; c++) {
        const cells = [];
        for (let r = 0; r < N; r++) cells.push([r, c]);
        out.push(cells);
      }
      return out;
    },

    /* Скольжение одного ряда к target-стороне. direction: 1 → вправо/вниз
       (рост индексов), -1 → влево/вверх. Ближние к целевой стороне элементы
       имеют приоритет слияния; каждый элемент объединяется только один раз. */
    _slide(line, direction) {
      const nonZero = line.filter((v) => v > 0);
      /* порядок от целевой стороны */
      const seq = direction === 1 ? nonZero.slice().reverse() : nonZero;
      const merged = [];
      let gain = 0;
      let i = 0;
      while (i < seq.length) {
        const v = seq[i];
        if (i + 1 < seq.length && seq[i + 1] === v) {
          const fv = v * 2;
          merged.push(fv);
          gain += fv;
          i += 2;               // каждый элемент участвует один раз
        } else {
          merged.push(v);
          i += 1;
        }
      }
      const result = [];
      for (let k = 0; k < N; k++) result.push(0);
      if (direction === 1) {
        for (let j = 0; j < merged.length; j++) result[N - 1 - j] = merged[j];
      } else {
        for (let j = 0; j < merged.length; j++) result[j] = merged[j];
      }
      let moved = JSON.stringify(result) !== JSON.stringify(line);
      return { row: result, gain, moved };
    },

    _checkWin() {
      if (this.won || this.wonShown) return;
      for (let r = 0; r < N; r++)
        for (let c = 0; c < N; c++)
          if (this.grid[r][c] === 2048) {
            /* первая «2048»: показываем диалог (won=true, wonShown=false).
               wonShown станет true только после продолжения/перезапуска. */
            this.won = true;
            this.wonShown = false;
            this.saveSave();
            return;
          }
    },

    /* продолжение после «2048» — партия идёт в бесконечном режиме */
    continueAfterWin() {
      this.wonShown = true;
      this.saveSave();
    },
    restartAfterWin() {
      this.newGame();
    },

    maxTile() {
      let m = 0;
      for (let r = 0; r < N; r++)
        for (let c = 0; c < N; c++)
          if (this.grid[r][c] > m) m = this.grid[r][c];
      return m;
    },

    tileCls, tileText, tileFont,

    /* время последнего сохранения для заголовка */
    lastSavedLabel() {
      return this.ru("Автосохранение включено",
        "Auto-save enabled");
    },
  };
};