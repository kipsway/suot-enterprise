/* SUOT Neo — страницы структурированных разделов (Часть 6).
   Чек-листы (+шаблоны), CAPA (цепочка), Протоколы, Риски, Справочник. */

window.STRUCTURED_PAGES = {
  checklists: "checklistsPage",
  capa: "capaPage",
  protocols: "protocolsPage",
  risks: "risksPage",
  textbook: "textbookPage",
  print_editor: "printEditor",
};

window.resolvePage = function (key) {
  const name = window.STRUCTURED_PAGES[key];
  return name && window[name] ? window[name]() : window.tablePage(key);
};

/* ── общие хелперы ── */
const SP = {
  badge: (v) => {
    const s = String(v || "").toLowerCase();
    if (["fail", "просрочено", "критический", "verified", "закрыто"]
      .includes(s)) return "b-red";
    if (["pass", "устранено", "выполнено", "низкий"].includes(s))
      return "b-green";
    if (["open", "активно", "в работе"].includes(s)) return "b-amber";
    if (["high", "высокий"].includes(s)) return "b-orange";
    if (["medium", "средний"].includes(s)) return "b-amber";
    return "b-blue";
  },
  level: (n) => {
    if (n >= 15) return { cls: "b-red", name: "Критический" };
    if (n >= 10) return { cls: "b-orange", name: "Высокий" };
    if (n >= 5) return { cls: "b-amber", name: "Средний" };
    return { cls: "b-green", name: "Низкий" };
  },
};

/* ═══ ЧЕК-ЛИСТЫ ═══ */
window.checklistsPage = function () {
  return {
    list: [], mode: "all", loading: true,
    cur: null, items: [], results: [],
    editOpen: false,
    form: { title: "", description: "", is_template: false },
    itemTexts: [""],
    fillMode: false,
    fill: {},                   // item_id → {value, comment}
    fillBy: "", fillNotes: "",
    icons: window.ICONS,
    t: (k) => I18N.t(k),

    async init() {
      await this.load();
    },
    async load() {
      this.loading = true;
      try {
        const res = await API.get("/s/checklists?mode=" + this.mode);
        this.list = res.items;
      } catch (e) { Toast.show(e.message, "error"); }
      this.loading = false;
    },
    setMode(m) { this.mode = m; this.load(); },

    async open(id) {
      try {
        const res = await API.get("/s/checklists/" + id);
        this.cur = res.checklist;
        this.items = res.items;
        this.results = res.results;
        this.fillMode = false;
        this.fill = {};
      } catch (e) { Toast.show(e.message, "error"); }
    },
    openCreate() {
      this.cur = { id: null, title: "", description: "",
                   is_template: this.mode === "templates" };
      this.items = [];
      this.itemTexts = [""];
      this.results = [];
      this.editOpen = true;
    },
    openEdit() {
      this.form = { title: this.cur.title,
                    description: this.cur.description,
                    is_template: !!this.cur.is_template };
      this.itemTexts = this.items.map((i) => i.item_text).concat([""]);
      this.editOpen = true;
    },
    async saveEdit() {
      const payload = {
        title: this.form.title,
        description: this.form.description,
        is_template: !!this.form.is_template,
        items: this.itemTexts.filter((x) => x.trim()),
      };
      try {
        if (this.cur.id) await API.put("/s/checklists/" + this.cur.id, payload);
        else {
          const res = await API.post("/s/checklists", payload);
          this.cur.id = res.id;
        }
        this.editOpen = false;
        Toast.show(I18N.t("tbl.savedOk"), "success");
        await this.open(this.cur.id);
        this.load();
      } catch (e) { Toast.show(e.message, "error"); }
    },
    async saveAsTemplate() {
      try {
        const res = await API.post(
          `/s/checklists/${this.cur.id}/save_as_template`);
        Toast.show(I18N.t("cl.tplSaved"), "success");
        await this.open(res.id);
        this.load();
      } catch (e) { Toast.show(e.message, "error"); }
    },
    async createFromTemplate() {
      try {
        const res = await API.post(
          `/s/checklists/from_template/${this.cur.id}`);
        await this.load();
        await this.open(res.id);
      } catch (e) { Toast.show(e.message, "error"); }
    },
    async remove() {
      if (!this.cur || !this.cur.id) return;
      try {
        await API.del("/s/checklists/" + this.cur.id);
        this.cur = null;
        this.load();
        Toast.show(I18N.t("tbl.deletedOk").replace("{n}", 1), "success");
      } catch (e) { Toast.show(e.message, "error"); }
    },

    startFill() {
      this.fillMode = true;
      this.fill = {};
      for (const i of this.items)
        this.fill[i.id] = { value: "na", comment: "" };
      this.fillBy = "";
      this.fillNotes = "";
    },
    async saveFill() {
      const answers = this.items.map((i) => ({
        item_id: i.id, value: this.fill[i.id].value,
        comment: this.fill[i.id].comment,
      }));
      try {
        const res = await API.post(
          `/s/checklists/${this.cur.id}/results`,
          { conducted_by: this.fillBy, notes: this.fillNotes, answers });
        Toast.show(I18N.t("cl.resultSaved")
          .replace("{s}", res.status === "fail" ? "FAIL" : "OK"),
          res.status === "fail" ? "error" : "success");
        this.fillMode = false;
        await this.open(this.cur.id);
      } catch (e) { Toast.show(e.message, "error"); }
    },
    async delResult(rid) {
      try {
        await API.del("/s/results/" + rid);
        await this.open(this.cur.id);
      } catch (e) { Toast.show(e.message, "error"); }
    },
  };
};

/* ═══ CAPA ═══ */
window.capaPage = function () {
  const EMPTY = () => ({ title: "", description: "", root_cause: "",
    action_plan: "", effectiveness: "", severity: "medium",
    status: "open", assigned_to: "", deadline: "" });
  return {
    list: [], statusFilter: "", loading: true,
    dialog: null, form: EMPTY(), busy: false,
    chain: null,               // {record, links}
    icons: window.ICONS,
    t: (k) => I18N.t(k),

    async init() { await this.load(); },
    async load() {
      this.loading = true;
      try {
        const res = await API.get("/s/capa" +
          (this.statusFilter ? "?status=" + this.statusFilter : ""));
        this.list = res.items;
      } catch (e) { Toast.show(e.message, "error"); }
      this.loading = false;
    },
    openCreate() { this.form = EMPTY(); this.dialog = { id: null }; },
    openEdit(r) { this.form = { ...r }; this.dialog = { id: r.id }; },
    async save() {
      this.busy = true;
      try {
        if (this.dialog.id)
          await API.put("/s/capa/" + this.dialog.id, this.form);
        else
          await API.post("/s/capa", this.form);
        this.dialog = null;
        Toast.show(I18N.t("tbl.savedOk"), "success");
        this.load();
      } catch (e) { Toast.show(e.message, "error"); }
      this.busy = false;
    },
    async remove(r) {
      try {
        await API.del("/s/capa/" + r.id);
        this.load();
      } catch (e) { Toast.show(e.message, "error"); }
    },
    async openChain(r) {
      try {
        const res = await API.get("/s/capa/" + r.id);
        this.chain = res;
      } catch (e) { Toast.show(e.message, "error"); }
    },
    sevBadge(v) { return SP.badge(v); },
    stBadge(v) { return SP.badge(v); },
  };
};

/* ═══ ПРОТОКОЛЫ ═══ */
window.protocolsPage = function () {
  const EMPTY = () => ({ date: new Date().toISOString().slice(0, 10),
    topic: "", participants: "", agenda: "", decisions: "",
    status: "active" });
  return {
    list: [], loading: true,
    dialog: null, form: EMPTY(), busy: false,
    icons: window.ICONS,
    t: (k) => I18N.t(k),
    async init() { await this.load(); },
    async load() {
      this.loading = true;
      try {
        this.list = (await API.get("/s/protocols")).items;
      } catch (e) { Toast.show(e.message, "error"); }
      this.loading = false;
    },
    openCreate() { this.form = EMPTY(); this.dialog = { id: null }; },
    openEdit(r) { this.form = { ...r }; this.dialog = { id: r.id }; },
    async save() {
      this.busy = true;
      try {
        if (this.dialog.id)
          await API.put("/s/protocols/" + this.dialog.id, this.form);
        else
          await API.post("/s/protocols", this.form);
        this.dialog = null;
        Toast.show(I18N.t("tbl.savedOk"), "success");
        this.load();
      } catch (e) { Toast.show(e.message, "error"); }
      this.busy = false;
    },
    async remove(r) {
      try {
        await API.del("/s/protocols/" + r.id);
        this.load();
      } catch (e) { Toast.show(e.message, "error"); }
    },
  };
};

/* ═══ РИСКИ ═══ */
window.risksPage = function () {
  const EMPTY = () => ({ title: "", description: "", category: "",
    probability: 1, consequence: 1, mitigation: "", status: "active" });
  return {
    list: [], loading: true,
    dialog: null, form: EMPTY(), busy: false,
    icons: window.ICONS,
    t: (k) => I18N.t(k),
    async init() { await this.load(); },
    async load() {
      this.loading = true;
      try {
        this.list = (await API.get("/s/risks")).items;
      } catch (e) { Toast.show(e.message, "error"); }
      this.loading = false;
    },
    get formLevel() {
      return SP.level((this.form.probability || 1) *
                      (this.form.consequence || 1));
    },
    levelInfo(n) { return SP.level(n); },
    openCreate() { this.form = EMPTY(); this.dialog = { id: null }; },
    openEdit(r) { this.form = { ...r }; this.dialog = { id: r.id }; },
    async save() {
      this.busy = true;
      try {
        if (this.dialog.id)
          await API.put("/s/risks/" + this.dialog.id, this.form);
        else
          await API.post("/s/risks", this.form);
        this.dialog = null;
        Toast.show(I18N.t("tbl.savedOk"), "success");
        this.load();
      } catch (e) { Toast.show(e.message, "error"); }
      this.busy = false;
    },
    async remove(r) {
      try {
        await API.del("/s/risks/" + r.id);
        this.load();
      } catch (e) { Toast.show(e.message, "error"); }
    },
  };
};

/* ═══ СПРАВОЧНИК СОКРАЩЕНИЙ ═══ */
window.textbookPage = function () {
  return {
    list: [], q: "", loading: true,
    dialog: null, form: { short_code: "", full_text: "" },
    editCode: null,
    icons: window.ICONS,
    t: (k) => I18N.t(k),
    async init() { await this.load(); },
    async load() {
      this.loading = true;
      try {
        this.list = (await API.get("/s/textbook")).items;
      } catch (e) { Toast.show(e.message, "error"); }
      this.loading = false;
    },
    get filtered() {
      const q = this.q.trim().toLowerCase();
      if (!q) return this.list;
      return this.list.filter((i) =>
        i.short_code.toLowerCase().includes(q) ||
        i.full_text.toLowerCase().includes(q));
    },
    openCreate() {
      this.editCode = null;
      this.form = { short_code: "", full_text: "" };
      this.dialog = true;
    },
    openEdit(i) {
      this.editCode = i.short_code;
      this.form = { short_code: i.short_code, full_text: i.full_text };
      this.dialog = true;
    },
    async save() {
      if (!this.form.short_code.trim()) return;
      try {
        if (this.editCode)
          await API.put("/s/textbook/" +
            encodeURIComponent(this.editCode), this.form);
        else
          await API.post("/s/textbook", this.form);
        this.dialog = null;
        Toast.show(I18N.t("tbl.savedOk"), "success");
        this.load();
      } catch (e) { Toast.show(e.message, "error"); }
    },
    async remove(i) {
      try {
        await API.del("/s/textbook/" + encodeURIComponent(i.short_code));
        this.load();
      } catch (e) { Toast.show(e.message, "error"); }
    },
  };
};
