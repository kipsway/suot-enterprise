/* SUOT Neo — Правовая база (Часть 26)
   Каталог НПА по охране труда: фасетный поиск, избранное, конспект, импорт. */
window.npaPage = function () {
  return {
    loading: false,
    q: "",
    qBuf: "",
    kind: "",
    category: "",
    status: "",
    year: "",
    favOnly: false,
    items: [],
    total: 0,
    facets: { kinds: [], categories: [], statuses: [], years: [] },
    selected: null,       // открытая карточка
    notesOpen: false,     // конспект в модалке
    notesText: "",
    importOpen: false,
    importText: "",
    editing: false,
    edit: { id: 0, kind: "приказ", number: "", title: "", date: "",
            status: "действует", category: "", audience: "", url: "", notes: "" },
    isAdmin: false,
    icons: window.ICONS,
    ru: (a, b) => I18N.lang === "ru" ? a : b,
    _deb: 0,

    async init() {
      try { this.isAdmin = (Alpine.store("user") || {}).role === "Administrator"; }
      catch (_) { this.isAdmin = false; }
      await Promise.all([this.loadFacets(), this.load()]);
    },

    debounced(e) {
      this.qBuf = e.target.value;
      clearTimeout(this._deb);
      this._deb = setTimeout(() => { this.q = this.qBuf; this.load(); }, 300);
    },
    applyFacet() { this.load(); },
    clearFilters() {
      this.q = ""; this.qBuf = "";
      this.kind = ""; this.category = ""; this.status = ""; this.year = "";
      this.favOnly = false;
      const inp = document.querySelector(".npa-q");
      if (inp) inp.value = "";
      this.load();
    },

    async loadFacets() {
      try {
        this.facets = await API.get("/npa/facets");
      } catch (e) { Toast.show(e.message, "error"); }
    },
    async load() {
      this.loading = true;
      try {
        const params = [];
        if (this.q.trim()) params.push("q=" + encodeURIComponent(this.q.trim()));
        if (this.kind) params.push("kind=" + encodeURIComponent(this.kind));
        if (this.category) params.push("category=" + encodeURIComponent(this.category));
        if (this.status) params.push("status=" + encodeURIComponent(this.status));
        if (this.year) params.push("year=" + encodeURIComponent(this.year));
        if (this.favOnly) params.push("fav=1");
        const r = await API.get("/npa/list" + (params.length ? "?" + params.join("&") : ""));
        this.items = r.items || [];
        this.total = r.total || 0;
        const openId = this.selected ? this.selected.id : 0;
        if (openId) {
          for (const it of this.items) if (it.id === openId) this.selected = it;
        }
      } catch (e) { Toast.show(e.message, "error"); }
      this.loading = false;
    },

    async openCard(id) {
      this.editing = false;
      this.importOpen = false;
      try {
        const r = await API.get("/npa/" + id);
        this.selected = r.item;
        this.notesText = this.selected.notes || "";
        this.notesOpen = true;
      } catch (e) { Toast.show(e.message, "error"); }
    },
    closeCard() {
      this.notesOpen = false;
      this.importOpen = false;
      this.editing = false;
      this.selected = null;
    },

    async toggleFav(it) {
      try {
        const r = await API.post("/npa/" + it.id + "/fav");
        it.is_fav = r.is_fav;
        if (this.favOnly && !r.is_fav) this.load();
      } catch (e) { Toast.show(e.message, "error"); }
    },

    govUrl(it) {
      const q = encodeURIComponent((it.number || "") + " " + (it.title || ""));
      return "https://pravo.gov.ru/search/?q=" + q;
    },

    fmtDate(d) {
      if (!d) return "—";
      if (d.length === 10 && d[2] === ".") return d;
      if (d.length === 10 && d[4] === "-") {
        const p = d.split("-");
        return p[2] + "." + p[1] + "." + p[0];
      }
      return d;
    },

    /* ── создание/редактирование ── */
    openNew() {
      this.editing = true;
      this.importOpen = false;
      this.selected = null;
      this.edit = { id: 0, kind: "приказ", number: "", title: "", date: "",
        status: "действует", category: "", audience: "", url: "", notes: "" };
      this.notesOpen = true;
    },
    openEdit(it) {
      this.editing = true;
      this.importOpen = false;
      this.edit = {
        id: it.id, kind: it.kind, number: it.number || "", title: it.title,
        date: it.date || "", status: it.status, category: it.category || "",
        audience: it.audience || "", url: it.url || "", notes: it.notes || "",
      };
      this.notesOpen = true;
      this.notesText = it.notes || "";
    },
    async saveEdit() {
      const e = this.edit;
      if (!e.title.trim()) { Toast.show(this.ru("Укажите название", "Title is required"), "error"); return; }
      try {
        if (e.id) await API.put("/npa/" + e.id, e);
        else await API.post("/npa", e);
        Toast.show(this.ru("Документ сохранён", "Saved"), "ok");
        this.closeCard();
        await Promise.all([this.loadFacets(), this.load()]);
      } catch (err) { Toast.show(err.message, "error"); }
    },
    async removeEdit() {
      if (!confirm(this.ru("Удалить документ?", "Delete document?"))) return;
      try {
        await API.del("/npa/" + this.edit.id);
        Toast.show(this.ru("Документ удалён", "Deleted"), "ok");
        this.closeCard();
        await Promise.all([this.loadFacets(), this.load()]);
      } catch (e) { Toast.show(e.message, "error"); }
    },

    /* ── импорт списком (JSON или CSV) ── */
    openImport() {
      this.importOpen = true;
      this.importText = "";
    },
    async runImport() {
      const txt = this.importText.trim();
      if (!txt) { Toast.show(this.ru("Пустой список", "Empty list"), "error"); return; }
      let body;
      if (txt.startsWith("{")) {
        try { body = JSON.parse(txt); }
        catch (_) {
          Toast.show(this.ru("Ошибка JSON — передан CSV?", "Invalid JSON"), "error");
          return;
        }
        if (!body.items || !Array.isArray(body.items)) {
          Toast.show(this.ru('Ожидается {"items": [...]}', 'Expected {"items": [...]}'), "error");
          return;
        }
      }
      try {
        const r = await API.post("/npa/import", body || { csv: txt });
        Toast.show(this.ru("Импортировано: " + r.imported, "Imported: " + r.imported), "ok");
        this.importOpen = false;
        await Promise.all([this.loadFacets(), this.load()]);
      } catch (e) { Toast.show(e.message, "error"); }
    },
  };
};