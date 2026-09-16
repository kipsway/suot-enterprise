/* SUOT Neo — Web Audio API звуки (без файлов) + колокольчик напоминаний. */

window.Sounds = {
  _ctx: null,
  _enabled: localStorage.getItem("suot_sounds") !== "off",

  _getCtx() {
    if (!this._ctx) {
      this._ctx = new (window.AudioContext ||
                       window.webkitAudioContext)();
    }
    if (this._ctx.state === "suspended") this._ctx.resume();
    return this._ctx;
  },

  _tone(freq, dur, type, gainVal, delay) {
    const ctx = this._getCtx();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = type || "sine";
    osc.frequency.value = freq;
    gain.gain.setValueAtTime(gainVal || 0.15,
      ctx.currentTime + (delay || 0));
    gain.gain.exponentialRampToValueAtTime(0.001,
      ctx.currentTime + (delay || 0) + dur);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start(ctx.currentTime + (delay || 0));
    osc.stop(ctx.currentTime + (delay || 0) + dur);
  },

  play(name) {
    if (!this._enabled) return;
    try {
      switch (name) {
        case "success":
          this._tone(523, 0.15, "sine", 0.12);
          this._tone(659, 0.15, "sine", 0.12, 0.12);
          this._tone(784, 0.25, "sine", 0.12, 0.24);
          break;
        case "error":
          this._tone(220, 0.2, "square", 0.08);
          this._tone(180, 0.3, "square", 0.08, 0.15);
          break;
        case "notification":
          this._tone(880, 0.12, "sine", 0.1);
          this._tone(1100, 0.2, "sine", 0.1, 0.1);
          break;
        case "click":
          this._tone(1200, 0.05, "sine", 0.05);
          break;
      }
    } catch (_) {}
  },

  toggle() {
    this._enabled = !this._enabled;
    localStorage.setItem("suot_sounds",
      this._enabled ? "on" : "off");
    return this._enabled;
  },
  get enabled() { return this._enabled; },
};

/* Подключить звуки к тостам */
document.addEventListener("suot-toast", (e) => {
  if (e.detail.type === "success") Sounds.play("success");
  else if (e.detail.type === "error") Sounds.play("error");
  else Sounds.play("notification");
});

/* Колокольчик напоминаний */
window.reminderBell = function () {
  return {
    open: false,
    data: { items: [], overdue_count: 0, upcoming_count: 0, total: 0 },
    settingsOpen: false,
    settings: {},
    loading: false,

    icons: window.ICONS,
    t: (k) => I18N.t(k),
    ru: (a, b) => I18N.lang === "ru" ? a : b,

    async     init() {
      document.addEventListener("suot-counts-changed", () => {
        if (Alpine.store("tabs").list.length) this.load();
      });
      if (API.hasToken()) await this.load();
    },
    async load() {
      this.loading = true;
      try {
        this.data = await API.get("/reminders/list");
      } catch (_) {}
      this.loading = false;
    },
    async toggle() {
      this.open = !this.open;
      if (this.open) await this.load();
    },
    async openSettings() {
      this.settingsOpen = !this.settingsOpen;
      if (this.settingsOpen) {
        try {
          const res = await API.get("/reminders/settings");
          this.settings = res.settings;
        } catch (_) {}
      }
    },
    async saveSettings() {
      try {
        await API.post("/reminders/settings", { lead_days: this.settings });
        Toast.show(I18N.t("tbl.savedOk"), "success");
        this.settingsOpen = false;
        this.load();
      } catch (e) { Toast.show(e.message, "error"); }
    },
    openTable(table) {
      this.open = false;
      Alpine.store("tabs").open(table);
    },
  };
};
