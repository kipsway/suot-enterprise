/* SUOT Neo — менеджер браузерных вкладок (Alpine.store) */
document.addEventListener("alpine:init", () => {
  const LABELS = () => ({
    employees: I18N.t("nav.employees"),
    violations: I18N.t("nav.violations"),
    incidents: I18N.lang === "ru" ? "Происшествия" : "Incidents",
    ppe: I18N.t("nav.ppe"),
    training: I18N.lang === "ru" ? "Обучение" : "Training",
    permits: I18N.lang === "ru" ? "Допуски" : "Permits",
    work_orders: I18N.lang === "ru" ? "Наряды" : "Work orders",
    companies: I18N.lang === "ru" ? "Компании" : "Companies",
    checklists: I18N.t("nav.checklists"),
    ppe_inspections: I18N.lang === "ru" ? "Осмотры СИЗ" : "PPE inspections",
    custom_ledger: I18N.lang === "ru" ? "Реестр" : "Ledger",
    checklists: I18N.t("cl.checklists"),
    capa: "CAPA",
    protocols: I18N.lang === "ru" ? "Протоколы" : "Protocols",
    risks: I18N.lang === "ru" ? "Риски" : "Risks",
    textbook: I18N.lang === "ru" ? "Справочник" : "Dictionary",
    game2048: "2048",
    game_bb: "Block Blast",
  });

  const TABLE_KEYS = ["employees", "violations", "incidents", "ppe",
    "ppe_inspections", "training", "permits", "work_orders",
    "companies", "custom_ledger", "checklists", "capa", "protocols",
    "risks", "textbook"];

  function labelFor(key) {
    if (!key) return "";
    if (key === "all")
      return I18N.lang === "ru" ? "Реестр «Всё»" : "All records";
    if (key.startsWith("u_")) {
      try {
        const st = Alpine.store("custom");
        const t = st && st.byKey[key];
        if (t) return t.label;
      } catch (_) {}
      return key;
    }
    return LABELS()[key] || key;
  }

  /* Иконка вкладки (часть 31): модуль → иконка */
  const TAB_ICONS = {
    all: "layers",
    employees: "users",
    violations: "alert",
    incidents: "inbox",
    ppe: "hardhat",
    ppe_inspections: "clipboard",
    training: "checkAll",
    permits: "command",
    work_orders: "refresh",
    companies: "home",
    custom_ledger: "database",
    checklists: "checkAll",
    capa: "linkIc",
    protocols: "fileText",
    risks: "alert",
    print_editor: "fileText",
    textbook: "bookmark",
  };
  function iconFor(key) {
    if (!key) return "database";
    if (key.startsWith("u_")) {
      try {
        const st = Alpine.store("custom");
        const t = st && st.byKey[key];
        if (t && t.icon && window.ICONS[t.icon]) return t.icon;
      } catch (_) {}
      return "database";
    }
    return TAB_ICONS[key] || "database";
  }
  /* Иконка вкладки по типу (часть 31) */
  const TYPE_ICONS = { welcome: "home", all: "layers",
    ai: "layers", journal: "fileText", calendar: "calendar",
    npa: "bookmark", tools: "tools", diag: "pulse",
    print_editor: "fileText", union: "layers",
    game2048: "grid", game_bb: "blocks" };
  function iconForType(tb) {
    if (!tb) return "database";
    if (tb.type === "table") return iconFor(tb.key);
    return TYPE_ICONS[tb.type] || "database";
  }

  Alpine.store("recent", { items: [] });

  function pushRecent(key, label) {
    try {
      const arr = JSON.parse(localStorage.getItem("suot_recent") || "[]")
        .filter((x) => x.key !== key);
      arr.unshift({ key, label, ts: Date.now() });
      localStorage.setItem("suot_recent",
        JSON.stringify(arr.slice(0, 8)));
      const st = Alpine.store("recent");
      if (st) st.items = arr.slice(0, 8);
      document.dispatchEvent(new CustomEvent("suot-recent-changed",
        { bubbles: true }));
    } catch (_) {}
    localStorage.setItem("suot_last", key);
  }

  Alpine.store("tabs", {
    list: [],
    activeId: null,
    _seq: 0,
    _draftTick: 0,
    ovMenu: false,
    overflowList: [],
    TABLE_KEYS,
    labelFor,
    iconFor,
    iconForType,

    activate(id) {
      this.activeId = id;
      this.ovMenu = false;
      this._setTitle();
    },
    toggleOverflow() {
      this.ovMenu = !this.ovMenu;
      this._recomputeOverflow();
    },
    _recomputeOverflow(el, widthUsed) {
      try {
        if (!el) { this.overflowList = []; return; }
        const tabs = Array.from(el.children);
        const cab = el.parentElement && el.parentElement.clientWidth;
        if (!cab) { this.overflowList = []; return; }
        let used = widthUsed || 40;
        const hidden = [];
        tabs.forEach((node) => {
          const isTab = node.classList && node.classList.contains("tab");
          const isAdd = node.classList && node.classList.contains("tab-add");
          const isMore = node.classList && node.classList.contains("tab-more");
          used += isTab ? node.offsetWidth + 4 : (isAdd || isMore) ? node.offsetWidth + 4 : 0;
          if (isTab && used > cab && hidden.length < 3) {
            const idx = Array.prototype.indexOf.call(
              el.querySelectorAll(".tab"), node);
            hidden.push(this.list[idx] || null);
          }
          if (isTab && used > cab) node.style.display = "none";
          else if (isTab) node.style.removeProperty("display");
        });
        this.overflowList = hidden.filter(Boolean);
      } catch (_) { this.overflowList = []; }
    },

    hasDraft(key) {
      try {
        return !!localStorage.getItem("suot_draft_" + key);
      } catch (_) { return false; }
    },
    touch() { this._draftTick++; },

    _setTitle() {
      const a = this.active;
      document.title = (a && a.label ? a.label + " — " : "") +
        "ОхранаТруда Про";
    },

    get active() {
      return this.list.find((tb) => tb.id === this.activeId) || null;
    },

    openWelcome() {
      const ex = this.list.find((tb) => tb.type === "welcome");
      if (ex) { this.activeId = ex.id; this._setTitle(); return; }
      const id = ++this._seq;
      this.list.push({ id, type: "welcome",
        label: I18N.t("tab.welcome") });
      this._persist();
      this.activeId = id;
      this._setTitle();
      localStorage.setItem("suot_last", "welcome");
    },

    openAll() {
      const key = "all";
      const ex = this.list.find((tb) => tb.type === "all");
      if (ex) { this.activeId = ex.id; this._setTitle();
        pushRecent(key, labelFor(key)); return; }
      const id = ++this._seq;
      this.list.push({ id, type: "all", key,
        label: I18N.lang === "ru" ? "Реестр «Всё»" : "All records" });
      this._persist();
      this.activeId = id;
      this._setTitle();
      pushRecent(key, labelFor(key));
    },

    openAI() {
      const ex = this.list.find((tb) => tb.type === "ai");
      if (ex) { this.activeId = ex.id; return; }
      const id = ++this._seq;
      this.list.push({ id, type: "ai",
        label: I18N.lang === "ru" ? "AI-ассистент" : "AI Assistant" });
      this._persist();
      this.activeId = id;
      this._setTitle();
    },

    openJournal() {
      const ex = this.list.find((tb) => tb.type === "journal");
      if (ex) { this.activeId = ex.id; this._setTitle(); return; }
      const id = ++this._seq;
      this.list.push({ id, type: "journal",
        label: I18N.lang === "ru" ? "Журнал" : "Audit log" });
      this._persist();
      this.activeId = id;
      this._setTitle();
    },

    openCalendar() {
      const ex = this.list.find((tb) => tb.type === "calendar");
      if (ex) { this.activeId = ex.id; this._setTitle(); return; }
      const id = ++this._seq;
      this.list.push({ id, type: "calendar",
        label: I18N.lang === "ru" ? "Календарь" : "Calendar" });
      this._persist();
      this.activeId = id;
      this._setTitle();
    },

    openNpa() {
      const ex = this.list.find((tb) => tb.type === "npa");
      if (ex) { this.activeId = ex.id; this._setTitle(); return; }
      const id = ++this._seq;
      this.list.push({ id, type: "npa",
        label: I18N.lang === "ru" ? "Правовая база" : "Legal base" });
      this._persist();
      this.activeId = id;
      this._setTitle();
    },

    openTools() {
      const ex = this.list.find((tb) => tb.type === "tools");
      if (ex) { this.activeId = ex.id; this._setTitle(); return; }
      const id = ++this._seq;
      this.list.push({ id, type: "tools",
        label: I18N.lang === "ru" ? "Инструменты" : "Tools" });
      this._persist();
      this.activeId = id;
      this._setTitle();
    },

    openDiagnostics() {
      const ex = this.list.find((tb) => tb.type === "diag");
      if (ex) { this.activeId = ex.id; this._setTitle(); return; }
      const id = ++this._seq;
      this.list.push({ id, type: "diag",
        label: I18N.lang === "ru" ? "Диагностика" : "Diagnostics" });
      this._persist();
      this.activeId = id;
      this._setTitle();
    },

    openGame2048() {
      const ex = this.list.find((tb) => tb.type === "game2048");
      if (ex) { this.activeId = ex.id; this._setTitle(); return; }
      const id = ++this._seq;
      this.list.push({ id, type: "game2048",
        label: I18N.lang === "ru" ? "2048" : "2048" });
      this._persist();
      this.activeId = id;
      this._setTitle();
      pushRecent("game2048", labelFor("game2048"));
    },

    openBlockBlast() {
      const ex = this.list.find((tb) => tb.type === "game_bb");
      if (ex) { this.activeId = ex.id; this._setTitle(); return; }
      const id = ++this._seq;
      this.list.push({ id, type: "game_bb",
        label: I18N.lang === "ru" ? "Block Blast" : "Block Blast" });
      this._persist();
      this.activeId = id;
      this._setTitle();
      pushRecent("game_bb", labelFor("game_bb"));
    },

    open(key) {
      if (key === "all") { this.openAll(); return; }
      const ex = this.list.find(
        (tb) => tb.type === "table" && tb.key === key);
      if (ex) { this.activeId = ex.id; this._setTitle();
        pushRecent(key, labelFor(key)); return; }
      const id = ++this._seq;
      this.list.push({ id, type: "table", key, label: labelFor(key) });
      this.activeId = id;
      this._setTitle();
      pushRecent(key, labelFor(key));
    },

    close(id) {
      const i = this.list.findIndex((tb) => tb.id === id);
      if (i < 0) return;
      if (this.list[i].type === "welcome") return; /* Рабочий стол закреплён */
      this.list.splice(i, 1);
      this._persist();
      if (this.activeId === id) {
        const next = this.list[Math.min(i, this.list.length - 1)];
        if (next) { this.activeId = next.id; this._setTitle(); }
        else this.openWelcome();
      }
    },

    _persist() {
      try {
        const snap = this.list.map((tb) => ({ type: tb.type,
          key: tb.key || "", label: tb.label }));
        localStorage.setItem("suot_tabs",
          JSON.stringify({ tabs: snap,
            active: Math.max(0, this.list.findIndex(
              (t) => t.id === this.activeId)) }));
        this._detectOverflow();
      } catch (_) {}
    },
    restore() {
      try {
        const raw = localStorage.getItem("suot_tabs");
        if (!raw) return false;
        const data = JSON.parse(raw);
        if (!Array.isArray(data.tabs) || !data.tabs.length) return false;
        this.list = data.tabs.map((t, i) => ({ id: ++this._seq,
          type: t.type || "table",
          key: t.key || undefined, label: t.label }));
        if (!this.list.some((t) => t.type === "welcome"))
          this.list.unshift({ id: ++this._seq, type: "welcome",
            label: I18N.t("tab.welcome") });
        this.activeId = this.list[Math.min(data.active || 0,
          this.list.length - 1)].id;
        this._setTitle();
        this._bindOverflow();
        return true;
      } catch (_) { return false; }
    },
    _bindOverflow() {
      try {
        this._ovTimer = null;
        const doCalc = () => {
          const sc = document.querySelector(".tabs-scroll");
          if (sc) this._recomputeOverflow(sc);
        };
        window.addEventListener("resize", doCalc);
        document.addEventListener("suot-tabs-updated", doCalc);
        setTimeout(doCalc, 250);
      } catch (_) {}
    },
    _detectOverflow() {
      document.dispatchEvent(new CustomEvent("suot-tabs-updated"));
    },
  });
});
