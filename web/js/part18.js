/* SUOT Neo — Часть 18: F1-центр помощи, тур новичка,
 * журнал аудита, управление пользователями. */

/* ── F1 центр помощи ── */
window.helpCenter = function () {
  return {
    open: false,
    tab: "quick",           // quick | keys | guide | about
    version: "",
    updateState: null,      // результат /api/update/check
    updateUrl: "",
    checking: false,
    hkRows: [],
    lang: I18N.lang,

    icons: window.ICONS,
    t: (k) => I18N.t(k),
    ru: function (a, b) { return this.lang === "ru" ? a : b; },

    init() {
      const app = this;
      window.addEventListener("suot-lang-change", (e) => {
        app.lang = e.detail.lang;
      });
      document.addEventListener("suot-check-update-auto", () => {
        window.setTimeout(() => {
          if (!app.updateState) app.checkUpdate();
        }, 1500);
      });
    },

    MODULES: [
      ["dashboard", "Рабочий стол", "KPI, просрочки, календарь мероприятий, " +
        "недавние таблицы и поиск по названию."],
      ["employees", "Сотрудники", "Карточки работников, фото, должности. " +
        "Двойной клик по ячейке — быстрое редактирование, звёздочка — метки."],
      ["violations", "Нарушения", "Фиксация нарушений с шаблонами, типами и " +
        "автоопределением дубликатов. Панель справа — заметки и связи."],
      ["incidents", "Происшествия", "Учёт инцидентов с тяжестью и статусом."],
      ["ppe", "СИЗ", "Выдача средств защиты, размеры, сроки."],
      ["checklists", "Чек-листы", "Обходы по пунктам; сохраняйте удачные " +
        "наборы как шаблоны."],
      ["capa", "CAPA", "Корректирующие действия: цепочка причина → мера → " +
        "проверка эффективности."],
      ["risks", "Риски", "Матрица P×C, автоматический уровень риска."],
      ["tools", "Инструменты", "Помодоро/таймер, заметки-стикеры, калькулятор " +
        "дат, погода, генератор паролей, макросы. Quick Capture — Ctrl+Q."],
      ["ai", "AI-ассистент", "Диалоги с разделами, инсайты по данным, " +
        "поиск и генерация текста."],
    ],

    /* ── Чеклист освоения (по модулям) ── */
    checklistDone(key) {
      try {
        const saved = JSON.parse(
          localStorage.getItem("suot_checklist") || "{}");
        return !!saved[key];
      } catch (_) { return false; }
    },
    toggleCheck(key) {
      const el = document.querySelector(`[data-check="${CSS.escape(key)}"]`);
      const cur = el ? el.classList.contains("on") : this.checklistDone(key);
      const saved = {};
      try {
        Object.assign(saved, JSON.parse(
          localStorage.getItem("suot_checklist") || "{}"));
      } catch (_) {}
      saved[key] = !cur;
      localStorage.setItem("suot_checklist", JSON.stringify(saved));
      Sounds.play(!cur ? "success" : "click");
    },
    clsProgress() {
      const items = this.MODULES.filter((m) => this.checklistDone(m[0]));
      return Math.round((items.length / this.MODULES.length) * 100);
    },

    openHelp(tab) {
      this.tab = tab || "quick";
      this.hkRows = this.hotkeyRows;
      this.open = true;
      this.loadVersion();
      if (this.tab === "about") {
        this.checkUpdate();
      }
    },

    get hotkeyRows() {
      const b = (window.Hotkeys && window.Hotkeys.bindings) || {};
      return Object.keys(b).map((k) =>
        ({ action: k, label: (window.Hotkeys.LABELS[k] || k),
           combo: b[k] }));
    },

    async loadVersion() {
      if (this.version) return;
      try {
        const v = await API.get("/help/version");
        this.version = v.version;
        const me = await API.get("/auth/me");
        if ((me.user.role || "").toLowerCase() === "administrator") {
          const u = await API.get("/admin/update_url");
          this.updateUrl = u.manifest_url || "";
        }
      } catch (_) {}
    },

    async checkUpdate() {
      this.checking = true;
      try {
        this.updateState = await API.post("/update/check",
          { manifest_url: this.updateUrl });
        document.dispatchEvent(new CustomEvent("suot-update-checked",
          { detail: { state: this.updateState } }));
        if (I18N.lang === undefined) {} // no-op
        Sounds.play(this.updateState.status === "ok" &&
          !this.updateState.up_to_date ? "notification" : "click");
      } catch (e) {
        Toast.show(e.message, "error");
      }
      this.checking = false;
    },

    async openUpdateForm() {
      if (!this.updateState || !this.updateState.download_url) return;
      try {
        await API.post("/update/open", { url: this.updateState.download_url });
        Toast.show(this.ru(
          "Открываем страницу загрузки в браузере…",
          "Opening download page in the browser…"), "info");
      } catch (e) { Toast.show(e.message, "error"); }
    },

    async saveUpdateUrl() {
      try {
        await API.post("/admin/update_url",
          { manifest_url: this.updateUrl });
        Toast.show(I18N.t("tbl.savedOk"), "success");
      } catch (e) { Toast.show(e.message, "error"); }
    },

    runHotkey(action) {
      this.open = false;
      setTimeout(() => window.Hotkeys.run(action), 120);
    },
  };
};

/* ── Тур новичка ── */
window.onboardingTour = function () {
  return {
    active: false,
    step: 0,
    rect: null,

    icons: window.ICONS,
    ru: (a, b) => I18N.lang === "ru" ? a : b,

    STEPS: [
      { sel: ".sidebar", title: "Разделы",
        text: "Все модули СУОТ слева. Плитки на рабочем столе открывают то же самое." },
      { sel: ".tiles-grid, .workspace-grid, .ws-tiles, .content",
        title: "Рабочий стол",
        text: "Плитки с счётчиками, недавние таблицы, поиск по названию." },
      { sel: ".statusbar", title: "Статус-бар",
        text: "Колокольчик напоминаний, звуки, AI-ассистент и настройки — справа внизу." },
      { sel: null, title: "Горячие клавиши",
        text: "Ctrl+K — палитра команд, Ctrl+N — новая запись, F1 — справка. Готово!" },
    ],

    tourKey() {
      const u = Alpine.store("user");
      return "suot_tour_" + ((u && u.username) || "");
    },

    start(force) {
      if (!force && localStorage.getItem(this.tourKey())) return;
      this.active = true;
      this.step = 0;
      this.place();
    },

    place() {
      const st = this.STEPS[this.step];
      this.rect = null;
      if (st.sel) {
        const el = document.querySelector(st.sel);
        if (el) {
          const r = el.getBoundingClientRect();
          if (r.width > 0)
            this.rect = [r.top, r.left, r.width, r.height];
        }
      }
    },

    next() {
      if (this.step < this.STEPS.length - 1) {
        this.step++;
        this.place();
      } else this.finish();
    },
    prev() {
      if (this.step > 0) { this.step--; this.place(); }
    },
    finish() {
      this.active = false;
      localStorage.setItem(this.tourKey(), "1");
      Sounds.play("success");
    },
  };
};

/* ── Журнал аудита ── */
window.journalView = function () {
  return {
    items: [],
    total: 0,
    limit: 100,
    loading: false,
    q: "",
    severity: "",
    icons: window.ICONS,
    ru: (a, b) => I18N.lang === "ru" ? a : b,

    async init() { await this.load(); },
    reload() { this.limit = 100; this.load(); },
    async load() {
      this.loading = true;
      try {
        const p = new URLSearchParams({ q: this.q,
          severity: this.severity, limit: this.limit });
        const r = await API.get("/events?" + p.toString());
        this.items = r.items;
        this.total = r.total;
      } catch (e) { Toast.show(e.message, "error"); }
      this.loading = false;
    },
    more() { this.limit += 200; this.load(); },
    async exportCsv() {
      try {
        const res = await fetch("/api/events/export.csv", {
          headers: { Authorization: "Bearer " + (
            localStorage.getItem("suot_token") ||
            sessionStorage.getItem("suot_token_session") || "") } });
        const blob = await res.blob();
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = "audit.csv";
        a.click();
        URL.revokeObjectURL(a.href);
      } catch (e) { Toast.show(e.message, "error"); }
    },
    sevClass(s) {
      return s === "WARNING" ? "warn" :
             s === "ERROR" ? "err" : "info";
    },
  };
};

/* ── Управление пользователями (админ) ── */
window.usersAdmin = function () {
  return {
    open: false,
    users: [],
    confirmAction: null,   // {uid, kind}
    newPwd: null,
    rolePick: -1,          // id пользователя с открытым выбором роли

    icons: window.ICONS,
    ru: (a, b) => I18N.lang === "ru" ? a : b,

    roleOptions: [
      { value: "user", ru: "Пользователь", en: "User" },
      { value: "Manager", ru: "Руководитель", en: "Manager" },
      { value: "Inspector", ru: "Инспектор", en: "Inspector" },
      { value: "Observer", ru: "Наблюдатель", en: "Observer" },
      { value: "Administrator", ru: "Администратор", en: "Administrator" },
    ],

    roleLabel(r) {
      const key = "role." + (r || "user").toLowerCase();
      return I18N.t(key) || r;
    },

    roleName(r) {
      const o = this.roleOptions.find((x) => x.value === r);
      return o ? (I18N.lang === "ru" ? o.ru : o.en) : r;
    },

    toggleRolePick(u) {
      if (this.isSelf(u) && u.role === "Administrator") return;
      this.rolePick = this.rolePick === u.id ? -1 : u.id;
    },

    async setRole(u, value) {
      if (value === u.role) { this.rolePick = -1; return; }
      try {
        await API.post(`/admin/users/${u.id}/role`, { role: value });
        Sounds.play("click");
        await this.load();
      } catch (e) { Toast.show(e.message, "error"); }
      this.rolePick = -1;
    },

    async openPanel() {
      this.open = true;
      await this.load();
    },
    async load() {
      try {
        const r = await API.get("/admin/users");
        this.users = r.users;
      } catch (e) { Toast.show(e.message, "error"); this.open = false; }
    },
    get isAdmin() {
      const u = Alpine.store("user");
      return u && (u.role || "").toLowerCase() === "administrator";
    },
    isSelf(u) {
      const me = Alpine.store("user");
      return me && me.id === u.id;
    },
    ask(u, kind) {
      this.confirmAction = { uid: u.id, username: u.username, kind };
    },
    async doConfirm() {
      const c = this.confirmAction;
      if (!c) return;
      try {
        if (c.kind === "block" || c.kind === "unblock") {
          await API.post(`/admin/users/${c.uid}/block`,
            { blocked: c.kind === "block" });
        } else if (c.kind === "role") {
          const target = this.users.find((x) => x.id === c.uid);
          const chain = ["user", "Manager", "Inspector", "Observer", "Administrator"];
          let nr = c.nextRole !== undefined
            ? c.nextRole
            : chain[(chain.indexOf(target.role) + 1) % chain.length];
          await API.post(`/admin/users/${c.uid}/role`, { role: nr });
        } else if (c.kind === "reset") {
          const r = await API.post(`/admin/users/${c.uid}/reset_password`);
          this.newPwd = r.new_password;
        }
        Sounds.play(c.kind === "reset" ? "notification" : "click");
        await this.load();
      } catch (e) { Toast.show(e.message, "error"); }
      this.confirmAction = null;
    },
    copyPwd() {
      if (!this.newPwd) return;
      navigator.clipboard && navigator.clipboard.writeText(this.newPwd);
      Toast.show(this.ru("Скопировано", "Copied"), "success");
    },
  };
};
