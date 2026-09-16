/* SUOT Neo — корневое состояние приложения (Alpine.js) */
document.addEventListener("alpine:init", () => {
  Alpine.store("version", "2.2.1");
  Alpine.store("brand", { org_name: "", logo: "" });
  Alpine.store("startScreen", localStorage.getItem("suot_start")
    || "workspace");

  Alpine.data("suotApp", () => ({
    screen: "lang",
    authMode: "login",
    theme: localStorage.getItem("suot_theme") || "dark",
    lang: I18N.lang,
    dateFormat: localStorage.getItem("suot_date_format") || "ru",
    user: null,
    error: "",
    busy: false,
    capsOn: false,
    showPassword: false,
    toasts: [],
    _toastId: 0,
    toastHist: null,          // lazy: история уведомлений (до 50)
    toastHistOpen: false,

    loginForm: { username: "", password: "", remember: true },
    regForm: { full_name: "" },
    demoNeeded: false,
    demoBusy: false,
    counts: {},
    updAvailable: false,
    reduceMotion: false,
    customTables: [],
    pinned: JSON.parse(localStorage.getItem("suot_pinned") || "[]"),
    wsSearch: "",
    recent: [],
    /* создание своей таблицы */
    ctOpen: false, ctEditKey: null, ctBusy: false,
    ctForm: { label: "", icon: "database", color: "#6366F1",
              columns: [{ name: "", type: "Текст" }] },
    ctIcons: ["database", "users", "alert", "hardhat", "clipboard",
      "calendar", "chart", "home", "inbox", "settings", "bookmark",
      "linkIc", "checkAll", "refresh", "fileText", "layers"],
    ctColors: ["#6366F1", "#22D3EE", "#10B981", "#F59E0B", "#EF4444",
      "#A855F7", "#EC4899", "#64748B"],
    /* корзина */
    trashOpen: false, trashList: [],
    /* настройки таблицы */
    settingsKey: null,
    reduceMotion: false,
    apiOk: true,
    appVersion: "",
    showTop: false,
    railMode: localStorage.getItem("suot_rail") === "1",
    _healthTimer: null,
    fatal: null,               // {msg, stack, url, ua, at} для Error Boundary

    setupErrorBoundary() {
      window.onerror = (msg, src, line, col, err) => {
        this.reportFatal(msg, (err && err.stack) || "", src || "");
        return false;
      };
      window.addEventListener("unhandledrejection", (e) => {
        const r = e.reason;
        this.reportFatal((r && r.message) || String(r),
          (r && r.stack) || "", location.href);
      });
    },

    reportFatal(msg, stack, url) {
      if (this.fatal || this.screen === "auth") return;
      this.fatal = {
        msg: String(msg),
        stack: String(stack).slice(0, 4000),
        url: url || location.href,
        ua: navigator.userAgent,
        at: new Date().toISOString(),
        app: this.appVersion || "",
      };
    },

    copyDiagnostics() {
      if (!this.fatal) return;
      const text = "SUOT Neo Error Report\n" +
        "time: " + this.fatal.at + "\n" +
        "version: " + this.fatal.app + "\n" +
        "message: " + this.fatal.msg + "\n" +
        "url: " + this.fatal.url + "\n" +
        "userAgent: " + this.fatal.ua + "\n\n" +
        this.fatal.stack;
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text);
      } else {
        const ta = document.createElement("textarea");
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        try { document.execCommand("copy"); } catch (_) {}
        ta.remove();
      }
      Toast.show(this.ru("Диагностика скопирована", "Diagnostics copied"),
        "success");
    },

    reloadApp() {
      location.reload();
    },

    toggleRail() {
      this.railMode = !this.railMode;
      localStorage.setItem("suot_rail", this.railMode ? "1" : "0");
      Sounds.play("click");
    },

    /* ── Toast-центр: история уведомлений (последние 50) ── */
    get toastHistory() {
      if (!this.toastHist) {
        try {
          this.toastHist = JSON.parse(
            localStorage.getItem("suot_toast_hist") || "[]");
        } catch (_) { this.toastHist = []; }
      }
      return this.toastHist;
    },
    pushToastHist(item) {
      const h = this.toastHistory;
      h.push(item);
      if (h.length > 50) h.splice(0, h.length - 50);
      try {
        localStorage.setItem("suot_toast_hist", JSON.stringify(h));
      } catch (_) {}
    },
    toggleToastHist() {
      this.toastHistOpen = !this.toastHistOpen;
      Sounds.play("click");
    },
    clearToastHist() {
      this.toastHist = [];
      localStorage.removeItem("suot_toast_hist");
      Sounds.play("click");
    },
    fmtToastTime(ts) {
      const d = new Date(ts);
      if (isNaN(d.getTime())) return "";
      const p = (n) => String(n).padStart(2, "0");
      return p(d.getHours()) + ":" + p(d.getMinutes()) + ":" +
        p(d.getSeconds());
    },

    icons: window.ICONS,
    t: (k) => I18N.t(k),
    ru: (a, b) => I18N.lang === "ru" ? a : b,

    async init() {
      if (this._initRan) return;
      this._initRan = true;
      this.setupErrorBoundary();
      try {
        this.reduceMotion = window.matchMedia &&
          window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      } catch (_) {}
      document.addEventListener("suot-toast", (e) => {
        const id = ++this._toastId;
        const msg = e.detail.msg, type = e.detail.type || "";
        this.toasts.push({ id, msg, type });
        this.pushToastHist({ msg, type, ts: Date.now() });
        setTimeout(() => {
          this.toasts = this.toasts.filter((x) => x.id !== id);
        }, 3200);
      });

      document.addEventListener("suot-open-palette", () => {
        this.openPalette();
      });

      document.addEventListener("suot-hotkey-ai-chat", () => {
        try { Alpine.store("tabs").openAI(); } catch (_) {}
      });

      document.addEventListener("suot-hotkey-quick-capture", () => {
        try {
          Alpine.store("tabs").openTools();
          sessionStorage.setItem("suot_quick_capture", "1");
        } catch (_) {}
      });

      document.addEventListener("suot-counts-changed", () => {
        if (this.screen === "main") this.refreshCounts();
      });

      document.addEventListener("suot-recent-changed", () => {
        this.refreshRecent();
      });

      document.addEventListener("suot-update-checked", (e) => {
        const st = e.detail && e.detail.state;
        this.updAvailable = !!(st && st.status === "ok" &&
          !st.up_to_date && st.download_url);
      });

      /* Ripple-эффект на кнопках */
      document.addEventListener("click", (e) => {
        const btn = e.target.closest(".btn");
        if (!btn || this.reduceMotion) return;
        const rect = btn.getBoundingClientRect();
        const d = Math.max(rect.width, rect.height) * 2;
        const r = document.createElement("span");
        r.className = "ripple";
        r.style.width = r.style.height = d + "px";
        r.style.left = (e.clientX - rect.left - d / 2) + "px";
        r.style.top = (e.clientY - rect.top - d / 2) + "px";
        btn.appendChild(r);
        r.addEventListener("animationend", () => r.remove());
        setTimeout(() => r.remove(), 900);
      });

      if (!API.hasToken()) return;
      try {
        const me = await API.get("/auth/me");
        this.user = me.user;
        Alpine.store("user", me.user);
        this.enterMain();
      } catch (_) {
        API.setToken("");
      }
    },

    enterMain() {
      this.screen = "main";
      document.dispatchEvent(new CustomEvent("suot-check-update-auto",
        { bubbles: true }));
      const restored = Alpine.store("tabs").restore();
      if (!restored && (!this.tabs &&
          Alpine.store("tabs").list.length === 0))
        this.applyStartScreen();
      this.refreshCounts();
      this.loadCustom();
      this.refreshRecent();
      if (window.Appearance) window.Appearance.load();
      if (window.Hotkeys) window.Hotkeys.load();
      if (Alpine.store("plugins")) Alpine.store("plugins").load();
      API.get("/setup/branding").then((b) => {
        Alpine.store("brand", { org_name: b.org_name || "",
                                logo: b.logo || "" });
      }).catch(() => {});
      this.applyUserLocale();
      this.startHealthLoop();
      this.initScrollTop();
      setTimeout(() => {
        if (Alpine.store("tabs").list.length <= 1)
          document.dispatchEvent(new CustomEvent("suot-tour-start",
            { bubbles: true }));
      }, 900);
    },

    applyStartScreen() {
      const s = localStorage.getItem("suot_start") || "workspace";
      const tabs = Alpine.store("tabs");
      if (s === "last") {
        const last = localStorage.getItem("suot_last");
        if (last === "welcome") tabs.openWelcome();
        else if (last) tabs.open(last);
        else tabs.openWelcome();
      } else if (s && s !== "workspace") {
        tabs.open(s);
      } else {
        tabs.openWelcome();
      }
    },

    async loadCustom() {
      try {
        const res = await API.get("/custom/tables");
        this.customTables = res.items;
        const byKey = {};
        for (const t of res.items) byKey[t.key] = t;
        Alpine.store("custom", { list: res.items, byKey,
          labelFor: (k) => (byKey[k] ? byKey[k].label : k) });
      } catch (_) {}
    },

    refreshRecent() {
      try {
        this.recent = JSON.parse(
          localStorage.getItem("suot_recent") || "[]");
      } catch (_) { this.recent = []; }
    },

    isPinned(key) { return this.pinned.includes(key); },
    togglePin(key) {
      this.pinned = this.isPinned(key)
        ? this.pinned.filter((k) => k !== key)
        : [...this.pinned, key];
      localStorage.setItem("suot_pinned", JSON.stringify(this.pinned));
    },

    /* ── Рабочий стол ── */
    get wsTiles() {
      const q = this.wsSearch.trim().toLowerCase();
      let keys = ["welcome", ...Alpine.store("tabs").TABLE_KEYS];
      keys = keys.filter((k) => k !== "textbook" || true);
      const custom = this.customTables.map((t) => t.key);
      const order = JSON.parse(
        localStorage.getItem("suot_ws_order") || "null");
      let all = [...new Set([...keys, ...custom])];
      if (order) {
        all = [...order.filter((k) => all.includes(k)),
               ...all.filter((k) => !order.includes(k))];
      }
      const label = (k) => {
        if (k === "welcome")
          return I18N.lang === "ru" ? "Дашборд" : "Dashboard";
        if (k && k.startsWith("u_")) {
          const t = this.customTables.find((x) => x.key === k);
          return t ? t.label : k;
        }
        return Alpine.store("tabs").labelFor(k);
      };
      const icon = (k) => {
        if (k === "welcome") return "dashboard";
        if (k && k.startsWith("u_")) {
          const t = this.customTables.find((x) => x.key === k);
          return t ? t.icon : "database";
        }
        const map = { employees: "users", violations: "alert",
          incidents: "inbox", ppe: "hardhat",
          ppe_inspections: "clipboard", training: "checkAll",
          permits: "command", work_orders: "refresh",
          companies: "home", custom_ledger: "database",
          checklists: "checkAll", capa: "linkIc",
          protocols: "fileText", risks: "alert", textbook: "bookmark" };
        return map[k] || "database";
      };
      const color = (k) => {
        if (k && k.startsWith("u_")) {
          const t = this.customTables.find((x) => x.key === k);
          return t ? t.color : "var(--acc)";
        }
        return "var(--acc)";
      };
      return all
        .map((k) => ({ key: k, label: label(k), icon: icon(k),
                       color: color(k),
                       count: this.counts[k] || 0 }))
        .filter((t) => !q || t.label.toLowerCase().includes(q));
    },

    wsDragKey: null,
    wsDrop(targetKey) {
      const from = this.wsTiles.findIndex((t) => t.key === this.wsDragKey);
      const to = this.wsTiles.findIndex((t) => t.key === targetKey);
      if (from < 0 || to < 0 || from === to) return;
      const order = this.wsTiles.map((t) => t.key);
      const [moved] = order.splice(from, 1);
      order.splice(to, 0, moved);
      localStorage.setItem("suot_ws_order", JSON.stringify(order));
      this.wsDragKey = null;
      this.wsSearch = "";   // сброс, чтобы порядок перерисовался
    },

    openCreateTable() {
      this.ctEditKey = null;
      this.ctForm = { label: "", icon: "database", color: "#6366F1",
        columns: [{ name: "", type: "Текст" }] };
      this.ctOpen = true;
    },
    openTableSettings(key) {
      const t = this.customTables.find((x) => x.key === key);
      if (!t) return;
      this.ctEditKey = key;
      this.ctForm = { label: t.label, icon: t.icon, color: t.color,
        columns: (t.columns || []).map((c) => ({ ...c })) };
      if (!this.ctForm.columns.length)
        this.ctForm.columns = [{ name: "", type: "Текст" }];
      this.ctOpen = true;
    },
    async saveCustomTable() {
      if (this.ctBusy) return;
      const label = this.ctForm.label.trim();
      if (!label) return;
      const columns = this.ctForm.columns
        .filter((c) => c.name.trim())
        .map((c) => ({ name: c.name.trim(), type: c.type,
                       visible: true }));
      this.ctBusy = true;
      try {
        let key;
        if (this.ctEditKey) {
          await API.put("/custom/tables/" + this.ctEditKey,
            { label, icon: this.ctForm.icon, color: this.ctForm.color,
              columns });
          key = this.ctEditKey;
        } else {
          const res = await API.post("/custom/tables",
            { label, icon: this.ctForm.icon, color: this.ctForm.color,
              columns });
          key = res.key;
        }
        this.ctOpen = false;
        await this.loadCustom();
        this.refreshCounts();
        // переоткрыть вкладку, чтобы подтянулась мета
        const tabs = Alpine.store("tabs");
        const tab = tabs.list.find(
          (t) => t.type === "table" && t.key === key);
        if (tab) { tabs.close(tab.id); }
        tabs.open(key);
        Toast.show(I18N.t("tbl.savedOk"), "success");
      } catch (e) {
        Toast.show(e.message, "error");
      }
      this.ctBusy = false;
    },

    async trashCustomTable(key) {
      try {
        await API.del("/custom/tables/" + key);
        this.ctOpen = false;
        Alpine.store("tabs").close(key);
        await this.loadCustom();
        this.refreshCounts();
        Toast.show(I18N.t("tbl.deletedOk").replace("{n}", 1), "success");
      } catch (e) { Toast.show(e.message, "error"); }
    },

    /* ── Корзина таблиц ── */
    async openTrash() {
      this.trashOpen = true;
      try {
        const res = await API.get("/custom/trash");
        this.trashList = res.items;
      } catch (e) { Toast.show(e.message, "error"); }
    },
    async restoreTrash(t) {
      try {
        await API.post(`/custom/tables/${t.key}/restore`);
        this.trashList = this.trashList.filter((x) => x.key !== t.key);
        await this.loadCustom();
        Toast.show(I18N.t("tr.restored"), "success");
      } catch (e) { Toast.show(e.message, "error"); }
    },
    async purgeTrash(t, withCsv) {
      try {
        if (withCsv) {
          const res = await API.get(
            `/custom/records/${t.key}?page_size=500`);
          const cols = (t.columns || []);
          const esc = (v) => '"' +
            String(v === undefined || v === null ? "" : v)
              .replace(/"/g, '""') + '"';
          const head = ["ID", ...cols.map((c) => c.name)]
            .map(esc).join(";");
          const lines = res.items.map((r) =>
            [esc(r.id), ...cols.map((c) => esc(r.data[c.name]))]
              .join(";"));
          const blob = new Blob(
            ["\ufeff" + head + "\n" + lines.join("\n")],
            { type: "text/csv;charset=utf-8" });
          const a = document.createElement("a");
          a.href = URL.createObjectURL(blob);
          a.download = t.label + ".csv";
          a.click();
          URL.revokeObjectURL(a.href);
        }
        await API.del(`/custom/tables/${t.key}/purge`);
        this.trashList = this.trashList.filter((x) => x.key !== t.key);
        this.refreshCounts();
        Toast.show(I18N.t("tbl.deletedOk").replace("{n}", 1), "success");
      } catch (e) { Toast.show(e.message, "error"); }
    },

    openPalette() {
      if (this.screen !== "main") return;
      document.dispatchEvent(new CustomEvent("suot-palette-open", { bubbles: true }));
    },

    async refreshCounts() {
      try {
        const res = await API.get("/me/counts");
        this.counts = res.counts || {};
        this.demoNeeded = Object.values(this.counts).every((n) => n === 0);
      } catch (_) { this.demoNeeded = false; }
    },

    toast(msg, type = "") {
      document.dispatchEvent(
        new CustomEvent("suot-toast", { detail: { msg, type }, bubbles: true }));
    },

    async chooseLang(l) {
      I18N.setLang(l);
      this.lang = l;
      document.documentElement.lang = l;
      window.dispatchEvent(new CustomEvent("suot-lang-change",
        { detail: { lang: l } }));
      try { await API.post("/auth/language", { language: l }); } catch (_) {}
      try {
        const st = await API.get("/setup/status");
        if (st.needed) { this.screen = "setup"; return; }
      } catch (_) {}
      this.screen = "auth";
      this.authMode = "login";
    },

    finishSetup(user, token) {
      API.setToken(token, true);
      this.user = user;
      Alpine.store("user", user);
      this.screen = "main";
      this.enterMain();
    },

    toggleTheme() {
      if (window.Appearance) {
        const cur = document.body.dataset.theme ||
                    document.documentElement.dataset.theme || "dark";
        const ids = window.Appearance.THEMES.map((t) => t.id)
          .filter((id) => id !== "auto");
        const i = ids.indexOf(cur);
        window.Appearance.save({ theme: ids[(i + 1) % ids.length] });
      } else {
        this.theme = this.theme === "dark" ? "light" : "dark";
        localStorage.setItem("suot_theme", this.theme);
      }
    },

    applyUserLocale() {
      API.get("/auth/locale").then((loc) => {
        if (loc && loc.language && loc.language !== I18N.lang) {
          I18N.setLang(loc.language);
          this.lang = loc.language;
          document.documentElement.lang = loc.language;
          window.dispatchEvent(new CustomEvent("suot-lang-change",
            { detail: { lang: loc.language } }));
        }
        if (loc && loc.date_format) {
          this.dateFormat = loc.date_format;
          localStorage.setItem("suot_date_format", loc.date_format);
        }
      }).catch(() => {});
    },

    startHealthLoop() {
      if (this._healthTimer) return;
      const ping = async () => {
        try {
          await API.get("/help/version");
          this.apiOk = true;
        } catch (_) { this.apiOk = false; }
      };
      ping();
      this._healthTimer = setInterval(ping, 20000);
      API.get("/help/version").then(
        (v) => { this.appVersion = v.version; }).catch(() => {});
    },

    initScrollTop() {
      this.$nextTick(() => {
        const c = document.querySelector(".content");
        if (!c) return;
        c.addEventListener("scroll", () => {
          this.showTop = c.scrollTop > 400;
        }, { passive: true });
      });
    },
    toTop() {
      const c = document.querySelector(".content");
      if (c) c.scrollTo({
        top: 0, behavior:
          this.reduceMotion ? "auto" : "smooth" });
    },

    roleLabel() {
      const r = (this.user && this.user.role || "user").toLowerCase();
      return this.t("role." + r);
    },

    validate() {
      const u = this.loginForm.username.trim();
      if (u.length < 3) return I18N.t("auth.usernamePh");
      /* длина пароля проверяется на сервере — сид-пароли тоже валидны */
      return "";
    },

    checkCaps(e) {
      try { this.capsOn = e.getModifierState &&
            e.getModifierState("CapsLock"); } catch (_) {}
    },

    async submitAuth() {
      if (this.busy) return;
      this.error = this.validate();
      if (this.error) return;
      this.busy = true;
      try {
        const body = {
          username: this.loginForm.username.trim(),
          password: this.loginForm.password,
          remember: !!this.loginForm.remember,
        };
        let resp;
        if (this.authMode === "register") {
          body.full_name = this.regForm.full_name.trim();
          resp = await API.post("/auth/register", body);
          this.toast(I18N.t("auth.createAccount") + " OK", "success");
        } else {
          resp = await API.post("/auth/login", body);
        }
        API.setToken(resp.token, !!body.remember);
        this.user = resp.user;
        Alpine.store("user", resp.user);
        this.loginForm.password = "";
        this.showPassword = false;
        this.enterMain();
      } catch (e) {
        this.error = e.message;
      } finally {
        this.busy = false;
      }
    },

    logout() {
      API.setToken("", false);
      this.user = null;
      Alpine.store("user", {});
      this.demoNeeded = false;
      this.screen = "auth";
      this.authMode = "login";
    },

    async seedDemoAll() {
      if (this.demoBusy) return;
      this.demoBusy = true;
      try {
        const res = await API.post("/demo/seed", {});
        const n = Object.values(res.created || {})
          .reduce((a, b) => a + b, 0);
        this.toast(I18N.t("demo.seededOk") + " (" + n + ")", "success");
        this.demoNeeded = false;
        document.dispatchEvent(new CustomEvent("suot-reload-tables", { bubbles: true }));
      } catch (e) {
        this.toast(e.message, "error");
      } finally {
        this.demoBusy = false;
      }
    },
  }));

  /* Глобальный доступ к тостам для дочерних компонентов */
  window.Toast.show = function (msg, type) {
    document.dispatchEvent(new CustomEvent("suot-toast",
      { detail: { msg, type: type || "" }, bubbles: true }));
  };
});
