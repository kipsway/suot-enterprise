/* SUOT Next Core — Navigation Registry + Workspace Shell (Блок 1).
   Модель: Workspace → View → Context → Command → Task.
   Старый tabs.js остаётся compatibility layer: все переходы идут через
   проверенные методы tabs (open, openWelcome, openJournal и другие) —
   новых DOM-контрактов для таблиц не вводится. RU/EN — через labelRu/labelEn. */
document.addEventListener("alpine:init", () => {
  const GROUPS = [
    { id: "core", order: 0, ru: "Главное", en: "Main" },
    { id: "safety", order: 1, ru: "Безопасность", en: "Safety" },
    { id: "work", order: 2, ru: "Работа", en: "Work" },
    { id: "service", order: 3, ru: "Сервис", en: "Service" },
  ];

   /* view: welcome|table|all|journal|ai|calendar|npa|tools|diagnostics|
      game2048|game_bb|settings|documents. key — для table/all. */
  const REGISTRY = [
    { id: "overview", view: "welcome", labelRu: "Обзор", labelEn: "Overview",
      icon: "dashboard", group: "core", order: 0, aliases: ["home", "welcome", "dashboard"] },
    { id: "people", view: "table", key: "employees", labelRu: "Люди", labelEn: "People",
      icon: "users", group: "core", order: 1, aliases: ["employees", "staff"] },
    { id: "risk", view: "table", key: "risks", labelRu: "Риски и сроки", labelEn: "Risks & deadlines",
      icon: "alert", group: "safety", order: 0, aliases: ["risks"] },
    { id: "violations", view: "table", key: "violations", labelRu: "Нарушения", labelEn: "Violations",
      icon: "alert", group: "safety", order: 1, aliases: ["violations"] },
    { id: "incidents", view: "table", key: "incidents", labelRu: "Происшествия", labelEn: "Incidents",
      icon: "inbox", group: "safety", order: 2, aliases: ["incidents"] },
    { id: "ppe", view: "table", key: "ppe", labelRu: "СИЗ", labelEn: "PPE",
      icon: "hardhat", group: "safety", order: 3, aliases: ["ppe"] },
    { id: "ppe_inspections", view: "table", key: "ppe_inspections", labelRu: "Осмотры СИЗ", labelEn: "PPE inspections",
      icon: "clipboard", group: "safety", order: 4, aliases: ["ppe_inspections"] },
    { id: "training", view: "table", key: "training", labelRu: "Обучение", labelEn: "Training",
      icon: "checkAll", group: "safety", order: 5, aliases: ["training"] },
    { id: "permits", view: "table", key: "permits", labelRu: "Допуски", labelEn: "Permits",
      icon: "command", group: "safety", order: 6, aliases: ["permits"] },
    { id: "work_orders", view: "table", key: "work_orders", labelRu: "Наряды", labelEn: "Work orders",
      icon: "refresh", group: "safety", order: 7, aliases: ["work_orders"] },
    { id: "documents", view: "documents", key: "protocols", labelRu: "Документы", labelEn: "Documents",
      icon: "fileText", group: "work", order: 0, aliases: ["protocols", "docs", "templates", "print"] },
    { id: "capa", view: "table", key: "capa", labelRu: "CAPA", labelEn: "CAPA",
      icon: "linkIc", group: "work", order: 1, aliases: ["capa"] },
    { id: "checklists", view: "table", key: "checklists", labelRu: "Чек-листы", labelEn: "Checklists",
      icon: "clipboard", group: "work", order: 2, aliases: ["checklists"] },
    { id: "analytics", view: "welcome", labelRu: "Аналитика", labelEn: "Analytics",
      icon: "chart", group: "work", order: 3, aliases: ["reports"] },
    { id: "companies", view: "table", key: "companies", labelRu: "Компании", labelEn: "Companies",
      icon: "home", group: "work", order: 4, aliases: ["companies"] },
    { id: "ledger", view: "table", key: "custom_ledger", labelRu: "Реестр", labelEn: "Ledger",
      icon: "database", group: "work", order: 5, aliases: ["custom_ledger"] },
    { id: "textbook", view: "table", key: "textbook", labelRu: "Справочник", labelEn: "Dictionary",
      icon: "bookmark", group: "work", order: 6, aliases: ["textbook"] },
    { id: "all", view: "all", labelRu: "Реестр «Всё»", labelEn: "All records",
      icon: "layers", group: "work", order: 7, aliases: ["all", "registry"] },
    { id: "journal", view: "journal", labelRu: "Журнал", labelEn: "Journal",
      icon: "fileText", group: "work", order: 8, aliases: ["journal", "audit"] },
    { id: "calendar", view: "calendar", labelRu: "Календарь", labelEn: "Calendar",
      icon: "calendar", group: "work", order: 9, aliases: ["calendar"] },
    { id: "npa", view: "npa", labelRu: "Правовая база", labelEn: "Legal base",
      icon: "bookmark", group: "work", order: 10, aliases: ["npa"] },
    { id: "tools", view: "tools", labelRu: "Инструменты", labelEn: "Tools",
      icon: "tools", group: "work", order: 11, aliases: ["tools"] },
    { id: "ai", view: "ai", labelRu: "AI-ассистент", labelEn: "AI Assistant",
      icon: "layers", group: "service", order: 0, aliases: ["ai"] },
    { id: "diagnostics", view: "diagnostics", labelRu: "Диагностика", labelEn: "Diagnostics",
      icon: "pulse", group: "service", order: 1, aliases: ["diagnostics", "diag"] },
    { id: "settings", view: "settings", labelRu: "Настройки", labelEn: "Settings",
      icon: "settings", group: "service", order: 2, aliases: ["settings"] },
    { id: "game2048", view: "game2048", labelRu: "2048", labelEn: "2048",
      icon: "grid", group: "service", order: 3, aliases: ["game2048"] },
    { id: "game_bb", view: "game_bb", labelRu: "Block Blast", labelEn: "Block Blast",
      icon: "blocks", group: "service", order: 4, aliases: ["game_bb", "blockblast"] },
  ];

  const RECENT_KEY = "suot_next_recent";
  const PINNED_KEY = "suot_next_pinned";
  const RECENT_MAX = 12;

  function readList(key, fallback) {
    try {
      const v = JSON.parse(localStorage.getItem(key) || "null");
      return Array.isArray(v) ? v.filter((x) => typeof x === "string") : fallback;
    } catch (_) { return fallback; }
  }

  Alpine.store("next", {
    registry: REGISTRY,
    activeId: "overview",
    mode: "welcome",
    context: {},
    pinned: readList(PINNED_KEY, ["overview"]),
    recent: readList(RECENT_KEY, []),
    switcherOpen: false,

    lang() { try { return (window.I18N && I18N.lang) || "ru"; } catch (_) { return "ru"; } },
    labelOf(item, lang) {
      if (!item) return "";
      const L = lang || this.lang();
      return L === "en" ? (item.labelEn || item.labelRu) : (item.labelRu || item.labelEn);
    },
    groupTitle(gid, lang) {
      const g = GROUPS.find((x) => x.id === gid);
      if (!g) return gid;
      const L = lang || this.lang();
      return L === "en" ? g.en : g.ru;
    },
    groups() { return GROUPS.slice().sort((a, b) => a.order - b.order); },
    byGroup(gid) {
      return this.registry
        .filter((x) => x.group === gid)
        .sort((a, b) => a.order - b.order);
    },
    all() { return this.registry; },
    byId(id) { return this.registry.find((x) => x.id === id); },
    resolve(idOrKeyOrAlias) {
      if (!idOrKeyOrAlias) return this.byId("overview");
      const q = String(idOrKeyOrAlias);
      return this.registry.find((x) =>
        x.id === q || x.key === q || (x.aliases || []).includes(q)
      ) || this.byId("overview");
    },
    pinnedItems() {
      return this.pinned.map((id) => this.byId(id)).filter(Boolean);
    },
    recentItems() {
      return this.recent.map((id) => this.byId(id)).filter(Boolean);
    },
    togglePin(id) {
      if (!this.byId(id)) return;
      const i = this.pinned.indexOf(id);
      if (i >= 0) this.pinned.splice(i, 1);
      else this.pinned.push(id);
      this.persist();
    },
    recordRecent(id) {
      if (!this.byId(id)) return;
      this.recent = [id].concat(this.recent.filter((x) => x !== id)).slice(0, RECENT_MAX);
      try { localStorage.setItem(RECENT_KEY, JSON.stringify(this.recent)); } catch (_) {}
    },
    persist() {
      try { localStorage.setItem(PINNED_KEY, JSON.stringify(this.pinned)); } catch (_) {}
    },
    setContext(context) { this.context = Object.assign({}, this.context, context || {}); },

    open(id, context) {
      const item = typeof id === "string" ? this.resolve(id) : (id || this.byId("overview"));
      if (!item) return false;
      this.activeId = item.id;
      this.mode = item.view;
      this.setContext(context);
      let ok = false;
      try {
        const tabs = Alpine.store("tabs");
        switch (item.view) {
          case "welcome": tabs.openWelcome(); ok = true; break;
          case "all": tabs.openAll(); ok = true; break;
          case "journal": tabs.openJournal(); ok = true; break;
          case "documents": tabs.openDocuments(); ok = true; break;
          case "ai": tabs.openAI(); ok = true; break;
          case "calendar": tabs.openCalendar(); ok = true; break;
          case "npa": tabs.openNpa(); ok = true; break;
          case "tools": tabs.openTools(); ok = true; break;
          case "diagnostics": tabs.openDiagnostics(); ok = true; break;
          case "game2048": tabs.openGame2048(); ok = true; break;
          case "game_bb": tabs.openBlockBlast(); ok = true; break;
          case "settings":
            document.dispatchEvent(new CustomEvent("suot-open-settings", { bubbles: true }));
            ok = true; break;
          default:
            /* Табличный маршрут — напрямую через адаптер (без рекурсии
               в tabs.open: тот сам сюда делегирует именованные виды). */
            if (item.key && tabs._openTableKey) {
              tabs._openTableKey(item.key); ok = true;
            } else if (item.key) { tabs.open(item.key); ok = true; }
        }
      } catch (_) { ok = false; }
      if (ok) this.recordRecent(item.id);
      /* Detail Workspace: контекст записи ведёт в досье (только если сущность
         известна Entity Registry — иначе просто открыт вид). */
      try {
        const ctx = context || {};
        if (ok && ctx.recordId && window.SUOT_ENTITIES) {
          const desc = SUOT_ENTITIES.descriptor(item.key || item.id);
          if (desc && desc.kind !== "none") {
            const rid = parseInt(ctx.recordId, 10) || 0;
            if (rid) {
              document.dispatchEvent(new CustomEvent("suot-detail-open",
                { bubbles: true, detail: { table: desc.key, id: rid } }));
            }
          }
        }
      } catch (_) {}
      this.notice = this.labelOf(item);
      const self = this;
      setTimeout(() => { self.notice = ""; }, 1800);
      return ok;
    },
    go(key, context) { return this.open(this.resolve(key), context); },
    /* Точное совпадение id/key/alias без fallback (для адаптера tabs.open).
       Возвращает true, если вид найден и открыт. */
    openKey(idOrKey, context) {
      if (!idOrKey) return false;
      const q = String(idOrKey);
      const item = this.registry.find((x) =>
        x.id === q || x.key === q || (x.aliases || []).includes(q));
      if (!item) return false;
      return this.open(item.id, context);
    },
    /* Точное совпадение без fallback: для палитры и тестов. */
    openViewExact(idOrKey, context) {
      if (!idOrKey) return false;
      const q = String(idOrKey);
      const item = this.registry.find((x) =>
        x.id === q || x.key === q || (x.aliases || []).includes(q));
      if (!item) return false;
      return this.open(item.id, context);
    },
    run(command) { if (typeof command === "function") command(this); },
    filtered(q) {
      const needle = String(q || "").trim().toLowerCase();
      const L = this.lang();
      return this.registry.filter((x) => {
        if (!needle) return true;
        const hay = ((x.labelRu || "") + " " + (x.labelEn || "") + " " + x.id + " " +
          (x.key || "") + " " + (x.aliases || []).join(" ")).toLowerCase();
        void L;
        return hay.includes(needle);
      });
    },
  });

  /* Alpine.store(name, value) регистрирует и ничего не возвращает —
     забираем реактивный стор отдельным вызовом. */
  const store = Alpine.store("next");

  document.addEventListener("suot-next-open",
    (e) => store.open(e.detail && e.detail.id, e.detail && e.detail.context));

  /* Alt+1..9 — закреплённые виды. Ставится один раз; пропускает поля ввода
     и открытые диалоги (фокус остаётся в модалке). */
  function overlayOpen() {
    try {
      const els = document.querySelectorAll(".overlay");
      for (let i = 0; i < els.length; i++) {
        if (getComputedStyle(els[i]).display !== "none") return true;
      }
    } catch (_) {}
    return false;
  }
  if (!window.__suotNextKeys) {
    window.__suotNextKeys = true;
    document.addEventListener("keydown", (e) => {
      try {
        if (!e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return;
        const m = /^Digit([1-9])$/.exec(e.code || "");
        if (!m) return;
        const t = e.target;
        if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" ||
            t.tagName === "SELECT" || t.isContentEditable)) return;
        if (overlayOpen()) return;
        const items = store.pinnedItems();
        const item = items[parseInt(m[1], 10) - 1];
        if (item) { e.preventDefault(); store.open(item.id); }
      } catch (_) {}
    });
  }
});

/* Панель-переключатель Workspace (shell). Классы только ws-*: существующие
   тесты и селекторы не затрагиваются. */
window.wsSwitcher = function () {
  return {
    open: false,
    q: "",
    icons: window.ICONS || {},
    ru: (a, b) => { try { return I18N.lang === "ru" ? a : b; } catch (_) { return a; } },
    store() { try { return Alpine.store("next"); } catch (_) { return null; } },
    show() {
      const st = this.store();
      if (!st) return;
      st.switcherOpen = true;
      this.open = true;
      this.q = "";
      this.$nextTick(() => {
        const inp = this.$refs.wsSearch;
        if (inp) inp.focus();
      });
    },
    hide() {
      const st = this.store();
      if (st) st.switcherOpen = false;
      this.open = false;
    },
    pick(id) {
      const st = this.store();
      if (st) st.open(id);
      this.hide();
    },
    bus() { try { return window.SUOT_COMMANDS || null; } catch (_) { return null; } },
    wsCommands() {
      const b = this.bus();
      if (!b) return [];
      try { return b.search(this.q); } catch (_) { return []; }
    },
    cmdLabel(c) {
      const b = this.bus();
      try { return b ? b.labelOf(c) : ""; } catch (_) { return ""; }
    },
    cmdIcon(c) {
      const k = (c && c.icon) || "layers";
      try { return (window.ICONS && window.ICONS[k]) || window.ICONS.layers || ""; }
      catch (_) { return ""; }
    },
    cmdShortcut(c) {
      const b = this.bus();
      try { return b ? (b.shortcutFor(c) || "") : ""; } catch (_) { return ""; }
    },
    runCommand(id) {
      const b = this.bus();
      let ok = false;
      try { ok = b ? b.run(id) : false; } catch (_) { ok = false; }
      if (ok) this.hide();
    },
    iconFor(item) {
      const k = (item && item.icon) || "layers";
      try { return (window.ICONS && window.ICONS[k]) || window.ICONS.layers || ""; }
      catch (_) { return ""; }
    },
  };
};
document.addEventListener("suot-ws-toggle", () => {
  try {
    const st = Alpine.store("next");
    st.switcherOpen = !st.switcherOpen;
    /* bubbles:true — иначе .window-подписчики панели событие не увидят */
    document.dispatchEvent(new CustomEvent("suot-ws-state",
      { bubbles: true, detail: { open: st.switcherOpen } }));
  } catch (_) {}
});
