/* SUOT Neo — Инструменты (Часть 28).
   Таймеры + стикеры + калькулятор дат + погода + пароли + макросы. */

window.toolsPage = function () {
  return {
    /* ── навигация ── */
    tab: "timer",  // timer|stopwatch|pomodoro|notes|date|weather|pwd|macro

    /* ── таймеры ── */
    timerMins: 5,
    timerLeft: 0,
    timerTotal: 0,
    timerRunning: false,
    timerInt: null,

    stopwatchMs: 0,
    stopwatchRunning: false,
    stopwatchInt: null,
    stopwatchLaps: [],

    pomodoroWork: 25,
    pomodoroBreak: 5,
    pomodoroLeft: 0,
    pomodoroTotal: 0,
    pomodoroRunning: false,
    pomodoroWorkPhase: true,
    pomodoroInt: null,
    pomoSessions: 0,

    /* ── стикеры ── */
    notes: [],
    noteText: "",
    quickNotePending: false,

    /* ── калькулятор дат ── */
    dcOp: "diff_days",       // diff_days|workdays|seniority|month_end
    dcA: "",
    dcB: "",
    dcResult: "",
    dcLoading: false,

    /* ── погода ── */
    weatherCity: "",
    weatherData: null,
    weatherLoading: false,
    weatherCitySaving: false,

    /* ── генератор паролей ── */
    pwdLen: 16,
    pwdUpper: true,
    pwdLower: true,
    pwdDigits: true,
    pwdSymbols: true,
    pwd: "",
    pwdCopied: false,

    /* ── макросы ── */
    macroItems: [],
    macroResult: "",
    macroLoading: false,

    icons: window.ICONS,
    ru: (a, b) => I18N.lang === "ru" ? a : b,
    t: (k) => I18N.t(k),

    /* ── init ── */
    init() {
      this.loadNotes();
      this.timerLeft = this.timerMins * 60;
      this.pomodoroLeft = this.pomodoroWork * 60;
      try {
        const pending = sessionStorage.getItem("suot_quick_capture") === "1";
        sessionStorage.removeItem("suot_quick_capture");
        if (pending) this.quickNotePending = true;
      } catch (e) {}
      if (window.__suotQcHandler) {
        document.removeEventListener("suot-hotkey-quick-capture", window.__suotQcHandler);
      }
      window.__suotQcHandler = () => {
        try { sessionStorage.removeItem("suot_quick_capture"); } catch (e) {}
        this.quickCapture();
      };
      document.addEventListener("suot-hotkey-quick-capture", window.__suotQcHandler);
      if (this.quickNotePending) {
        this.quickNotePending = false;
        this.$nextTick(() => this.quickCapture());
      }
    },

    /* ── helpers ── */
    _fmt(sec) {
      sec = Math.max(0, Math.floor(sec));
      const m = Math.floor(sec / 60);
      const s = sec % 60;
      return (m < 10 ? "0" + m : m) + ":" + (s < 10 ? "0" + s : s);
    },
    _fmtMs(ms) {
      const c = Math.floor(ms % 1000 / 100);
      const s = Math.floor(ms / 1000);
      const m = Math.floor(s / 60);
      return this._fmt(m * 60 + s % 60) + "." + c;
    },
    beep() {
      try {
        const AC = window.AudioContext || window.webkitAudioContext;
        const ctx = new AC();
        const o = ctx.createOscillator();
        const g = ctx.createGain();
        o.type = "sine"; o.frequency.value = 880;
        g.gain.value = 0.25;
        o.connect(g); g.connect(ctx.destination);
        o.start();
        o.frequency.setValueAtTime(880, ctx.currentTime);
        o.frequency.setValueAtTime(1100, ctx.currentTime + 0.25);
        o.stop(ctx.currentTime + 0.8);
      } catch (e) {}
    },
    _todayISO() {
      return new Date().toISOString().slice(0, 10);
    },
    _fmtDom(iso) {
      if (!iso) return "";
      const d = new Date(iso + "T00:00:00");
      const months = I18N.lang === "ru"
        ? ["янв","фев","мар","апр","май","июн","июл","авг","сен","окт","ноя","дек"]
        : ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
      return d.getDate() + " " + months[d.getMonth()];
    },

    /* ── Quick Capture Ctrl+Q ── */
    quickCapture() {
      this.tab = "notes";
      this.$nextTick(() => {
        const el = document.querySelector(".notes-toolbar .field-input");
        if (el) el.focus();
      });
      if (typeof Toast !== "undefined")
        Toast.show(this.ru("Быстрая заметка: введите текст", "Quick note: type text"), "info");
    },

    /* ═══ ТАЙМЕР ═══ */
    setTimerMins(v) {
      this.timerMins = parseInt(v, 10) || 1;
      if (!this.timerRunning) this.timerLeft = this.timerMins * 60;
    },
    startTimer() {
      if (this.timerRunning) return;
      this.timerRunning = true;
      this.timerTotal = this.timerLeft || this.timerMins * 60;
      this.timerLeft = this.timerTotal;
      this.timerInt = setInterval(() => {
        this.timerLeft -= 1;
        if (this.timerLeft <= 0) {
          this.stopTimer();
          this.beep();
        }
      }, 1000);
    },
    stopTimer() {
      this.timerRunning = false;
      if (this.timerInt) clearInterval(this.timerInt);
      this.timerInt = null;
    },
    resetTimer() {
      this.stopTimer();
      this.timerLeft = this.timerMins * 60;
    },

    /* ═══ СЕКУНДОМЕР ═══ */
    startStopwatch() {
      if (this.stopwatchRunning) return;
      this.stopwatchRunning = true;
      const t0 = Date.now() - this.stopwatchMs;
      this.stopwatchInt = setInterval(() => {
        this.stopwatchMs = Date.now() - t0;
      }, 40);
    },
    stopStopwatch() {
      this.stopwatchRunning = false;
      if (this.stopwatchInt) clearInterval(this.stopwatchInt);
      this.stopwatchInt = null;
    },
    resetStopwatch() {
      this.stopStopwatch();
      this.stopwatchMs = 0;
      this.stopwatchLaps = [];
    },
    lapStopwatch() {
      if (!this.stopwatchRunning) return;
      this.stopwatchLaps.unshift({
        n: this.stopwatchLaps.length + 1,
        t: this._fmtMs(this.stopwatchMs),
      });
    },

    /* ═══ ПОМОДОРО ═══ */
    setPomodoroWork(v) {
      this.pomodoroWork = parseInt(v, 10) || 1;
      if (!this.pomodoroRunning && this.pomodoroWorkPhase)
        this.pomodoroLeft = this.pomodoroWork * 60;
    },
    setPomodoroBreak(v) {
      this.pomodoroBreak = parseInt(v, 10) || 1;
      if (!this.pomodoroRunning && !this.pomodoroWorkPhase)
        this.pomodoroLeft = this.pomodoroBreak * 60;
    },
    startPomodoro() {
      if (this.pomodoroRunning) return;
      this.pomodoroRunning = true;
      this.pomodoroTotal = this.pomodoroLeft ||
        (this.pomodoroWorkPhase ? this.pomodoroWork * 60 : this.pomodoroBreak * 60);
      this.pomodoroLeft = this.pomodoroTotal;
      this.pomodoroInt = setInterval(() => {
        this.pomodoroLeft -= 1;
        if (this.pomodoroLeft <= 0) this._pomodoroSwitch();
      }, 1000);
    },
    _pomodoroSwitch() {
      this.beep();
      if (this.pomodoroWorkPhase) {
        this.pomodoroWorkPhase = false;
        this.pomodoroLeft = this.pomodoroBreak * 60;
        this.pomoSessions++;
      } else {
        this.pomodoroWorkPhase = true;
        this.pomodoroLeft = this.pomodoroWork * 60;
      }
    },
    stopPomodoro() {
      this.pomodoroRunning = false;
      if (this.pomodoroInt) clearInterval(this.pomodoroInt);
      this.pomodoroInt = null;
    },
    resetPomodoro() {
      this.stopPomodoro();
      this.pomodoroWorkPhase = true;
      this.pomodoroLeft = this.pomodoroWork * 60;
      this.pomoSessions = 0;
    },

    /* ═══ СТИКЕРЫ ═══ */
    NOTES_KEY: "suot_notes",
    loadNotes() {
      try {
        const raw = localStorage.getItem(this.NOTES_KEY);
        this.notes = raw ? JSON.parse(raw) : [];
        this.notes.sort((a, b) => (b.pinned ? 1 : 0) - (a.pinned ? 1 : 0) ||
          (b.ts - a.ts));
      } catch (e) { this.notes = []; }
    },
    saveNotes() {
      try { localStorage.setItem(this.NOTES_KEY, JSON.stringify(this.notes)); }
      catch (e) {}
    },
    addNote() {
      const text = this.noteText.trim();
      if (!text) return;
      this.notes.unshift({
        id: "n" + Date.now() + Math.floor(Math.random() * 1000),
        text: text, color: "#fde68a", pinned: false, ts: Date.now(),
      });
      this.noteText = "";
      this.saveNotes();
    },
    updateNote(id, text) {
      const n = this.notes.find((x) => x.id === id);
      if (!n) return;
      n.text = text;
      if (text.trim()) { n.ts = Date.now(); this.saveNotes(); }
    },
    setNoteColor(id, color) {
      const n = this.notes.find((x) => x.id === id);
      if (!n) return;
      n.color = color;
      this.saveNotes();
    },
    pinNote(id) {
      const n = this.notes.find((x) => x.id === id);
      if (!n) return;
      n.pinned = !n.pinned;
      this.notes.sort((a, b) => (b.pinned ? 1 : 0) - (a.pinned ? 1 : 0) ||
        (b.ts - a.ts));
      this.saveNotes();
    },
    deleteNote(id) {
      this.notes = this.notes.filter((x) => x.id !== id);
      this.saveNotes();
    },
    clearNotes() {
      if (this.notes.length && confirm(this.ru("Удалить все заметки?", "Delete all notes?")))
        { this.notes = []; this.saveNotes(); }
    },

    /* ═══ КАЛЬКУЛЯТОР ДАТ ═══ */
    dcRun() {
      this.dcLoading = true;
      this.dcResult = "";
      const body = { op: this.dcOp, a: this.dcA || "", b: this.dcB || "" };
      API.post("/tools/datecalc", body)
        .then((r) => {
          this.dcLoading = false;
          if (r.ok) {
            this.dcResult = r.result !== undefined && r.result !== null
              ? String(r.result)
              : "";
          } else {
            this.dcResult = "⚠ " + (r.error || "Error");
          }
        })
        .catch((e) => {
          this.dcLoading = false;
          this.dcResult = "⚠ " + e.message;
        });
    },

    /* ═══ ПОГОДА ═══ */
    weatherLoad() {
      this.weatherLoading = true;
      this.weatherData = null;
      API.get("/tools/weather")
        .then((r) => {
          this.weatherLoading = false;
          this.weatherData = r;
        })
        .catch((e) => {
          this.weatherLoading = false;
          this.weatherData = { ok: false, error: e.message };
        });
    },
    weatherSaveCity() {
      const city = (this.weatherCity || "").trim();
      if (!city) return;
      this.weatherCitySaving = true;
      API.post("/tools/weather/city", { city: city })
        .then((r) => {
          this.weatherCitySaving = false;
          this.weatherCity = r.city || city;
          if (typeof Toast !== "undefined")
            Toast.show(this.ru("Город сохранён", "City saved"), "success");
        })
        .catch((e) => {
          this.weatherCitySaving = false;
          if (typeof Toast !== "undefined") Toast.show(e.message, "error");
        });
    },
    _wcodeToText(code) {
      const m = {
        0: this.ru("Ясно", "Clear"),
        1: this.ru("Малооблачно", "Mostly clear"),
        2: this.ru("Облачно", "Cloudy"),
        3: this.ru("Пасмурно", "Overcast"),
        45: this.ru("Туман", "Fog"),
        48: this.ru("Туман с изморозью", "Rime fog"),
        51: this.ru("Лёгкая морось", "Light drizzle"),
        53: this.ru("Морось", "Drizzle"),
        55: this.ru("Сильная морось", "Heavy drizzle"),
        61: this.ru("Небольшой дождь", "Light rain"),
        63: this.ru("Дождь", "Rain"),
        65: this.ru("Сильный дождь", "Heavy rain"),
        71: this.ru("Небольшой снег", "Light snow"),
        73: this.ru("Снег", "Snow"),
        75: this.ru("Сильный снег", "Heavy snow"),
        80: this.ru("Ливень", "Rain showers"),
        81: this.ru("Сильный ливень", "Heavy showers"),
        82: this.ru("Проливной дождь", "Violent showers"),
        95: this.ru("Гроза", "Thunderstorm"),
        96: this.ru("Гроза с градом", "Thunderstorm + hail"),
      };
      return m[code] || this.ru("Неизвестно", "Unknown");
    },

    /* ═══ ГЕНЕРАТОР ПАРОЛЕЙ ═══ */
    genPwd() {
      const up = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
      const lo = "abcdefghijklmnopqrstuvwxyz";
      const dg = "0123456789";
      const sy = "!@#$%^&*()-_=+[]{}|;:,.<>?";
      let ch = "";
      if (this.pwdUpper) ch += up;
      if (this.pwdLower) ch += lo;
      if (this.pwdDigits) ch += dg;
      if (this.pwdSymbols) ch += sy;
      if (!ch) ch = lo;
      const arr = new Uint32Array(this.pwdLen);
      crypto.getRandomValues(arr);
      this.pwd = Array.from(arr, (v) => ch[v % ch.length]).join("");
      this.pwdCopied = false;
    },
    copyPwd() {
      if (!this.pwd) return;
      navigator.clipboard.writeText(this.pwd).then(() => {
        this.pwdCopied = true;
        if (typeof Toast !== "undefined")
          Toast.show(this.ru("Скопировано!", "Copied!"), "success");
      }).catch(() => {});
    },

    /* ═══ МАКРОСЫ ═══ */
    loadMacros() {
      API.get("/tools/macros")
        .then((r) => { this.macroItems = (r && r.items) || []; })
        .catch(() => { this.macroItems = []; });
    },
    runMacro(name) {
      this.macroLoading = true;
      this.macroResult = "";
      API.post("/tools/macros/run", { name: name })
        .then((r) => {
          this.macroLoading = false;
          if (r.ok) {
            this.macroResult = r.result || "";
            navigator.clipboard.writeText(this.macroResult).catch(() => {});
            if (typeof Toast !== "undefined")
              Toast.show(this.ru("Результат в буфере обмена", "Result copied to clipboard"), "success");
          } else {
            this.macroResult = "⚠ " + (r.error || "Error");
          }
        })
        .catch((e) => {
          this.macroLoading = false;
          this.macroResult = "⚠ " + e.message;
        });
    },
  };
};