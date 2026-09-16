/* Часть 30: страница диагностики — версии, БД, integrity, сессии, лог. */
window.diagPage = function () {
  return {
    d: null,
    disk: null,
    log: [],
    busy: true,
    logLimit: 40,
    sessions: [],
    sessionsBusy: false,
    checkedAt: "",

    ru: (a, b) => I18N.lang === "ru" ? a : b,

    init() {
      this.load();
    },

    fmtBytes(n) {
      if (n == null) return "—";
      if (n >= 1073741824) return (n / 1073741824).toFixed(2) + " GB";
      if (n >= 1048576) return (n / 1048576).toFixed(1) + " MB";
      if (n >= 1024) return (n / 1024).toFixed(0) + " KB";
      return n + " B";
    },

    uptime() {
      if (!this.d || !this.d.app) return "—";
      const s = this.d.app.uptime_sec || 0;
      const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
      if (h) return `${h} ч ${m} мин`;
      return `${m} мин`;
    },

    dbCounts() {
      if (!this.d || !this.d.database || !this.d.database.counts) return "—";
      const c = this.d.database.counts;
      return [
        `${this.ru("пользователей","users")}: ${c.users || 0}`,
        `${this.ru("таблиц","tables")}: ${this.d.database.integrity.tables || 0}`,
      ].join(" · ");
    },

    uaShort(ua) {
      if (!ua) return "—";
      let s = ua;
      const m = s.match(/(Firefox|Chrome|Safari|Edg\/?\d*|OPR\/?\d*)[\/ ]([\d.]+)/);
      if (m) s = m[1] + " " + m[2];
      return s.slice(0, 48);
    },

    async load() {
      this.busy = true;
      try {
        const [d, l, disk] = await Promise.all([
          API.get("/diag/summary"),
          API.get(`/diag/log?limit=${this.logLimit}`),
          API.get("/diag/disk"),
        ]);
        this.d = d;
        this.log = l.items || [];
        this.disk = disk;
        this.checkedAt = new Date().toLocaleString(
          I18N.lang === "ru" ? "ru-RU" : "en-US");
      } catch (e) {
        Toast.show(e.message || "diag error", "error");
      }
      this.busy = false;
    },

    async loadSessions() {
      this.sessionsBusy = true;
      try {
        const r = await API.get("/auth/sessions");
        this.sessions = r.sessions || [];
      } catch (e) { Toast.show(e.message || "sessions error", "error"); }
      this.sessionsBusy = false;
    },

    async revoke(s) {
      try {
        await API.post(`/auth/sessions/${s.id}/revoke`);
        Toast.show(this.ru("Сессия завершена ✓", "Session ended ✓"), "success");
        await this.loadSessions();
      } catch (e) { Toast.show(e.message, "error"); }
    },

    async revokeAll() {
      try {
        for (const s of this.sessions) {
          if (!s.revoked) await API.post(`/auth/sessions/${s.id}/revoke`);
        }
        Toast.show(this.ru("Все сессии завершены ✓", "All sessions ended ✓"), "success");
        await this.loadSessions();
      } catch (e) { Toast.show(e.message, "error"); }
    },

    refresh() {
      this.load();
    },
  };
};