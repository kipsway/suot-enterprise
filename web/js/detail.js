/* SUOT Next — Detail Workspace (Блок 2).
   Слайдер-досье записи: поля + заметки + связи + история с настоящим
   откатом (POST .../history/{id}/rollback, без фиктивного undo).
   Открытие: событие suot-detail-open {table|key, id}. Все подписи RU/EN,
   состояния loading/error/empty, Esc закрывает. */
window.entityDetail = function () {
  return {
    open: false,
    loading: false,
    loadError: "",
    tab: "fields",
    desc: null,
    table: "",
    rid: 0,
    title: "",
    fields: [],
    notes: [],
    links: [],
    history: [],
    noteTitle: "",
    noteContent: "",
    linkTable: "employees",
    linkId: "",
    busy: false,

    icons: window.ICONS || {},
    t: (k) => { try { return I18N.t(k); } catch (_) { return k; } },
    ru: (a, b) => { try { return I18N.lang === "ru" ? a : b; } catch (_) { return a; } },

    ent() {
      try {
        if (window.SUOT_ENTITIES) return SUOT_ENTITIES.descriptor(this.table);
      } catch (_) {}
      return null;
    },
    entLabel() {
      try {
        if (window.SUOT_ENTITIES) return SUOT_ENTITIES.labelOf(this.desc);
      } catch (_) {}
      return this.table;
    },

    async show(detail) {
      const d = detail || {};
      this.table = d.table || d.key || "";
      this.rid = parseInt(d.id, 10) || 0;
      if (!this.table || !this.rid) return;
      this.desc = this.ent();
      this.tab = "fields";
      this.open = true;
      this.$nextTick(() => {
        const el = this.$refs.dtClose;
        if (el) el.focus();
      });
      await this.loadAll();
    },
    hide() {
      this.open = false;
      this.loadError = "";
      this.record = null;
      this.notes = [];
      this.links = [];
      this.history = [];
      this.noteTitle = "";
      this.noteContent = "";
    },

    async loadAll() {
      this.loading = true;
      this.loadError = "";
      try {
        const E = window.SUOT_ENTITIES;
        const url = E ? E.recordUrl(this.desc, this.rid) : "";
        if (!url) throw new Error("unsupported entity");
        const rec = await API.get(url);
        const dj = rec.data || rec;
        this.title = (E ? E.titleOf(this.desc, rec) : "") || ("#" + this.rid);
        this.fields = E ? E.fieldEntries(rec) : [];
        this.record = rec;
        await Promise.all([this.loadNotes(true), this.loadLinks(true), this.loadHistory(true)]);
      } catch (e) {
        this.loadError = e.message || String(e);
      } finally {
        this.loading = false;
      }
    },

    async loadNotes(silent) {
      this.notes = [];
      if (!this.desc || !this.desc.notes) return;
      try {
        const r = await API.get(`/record/${this.table}/${this.rid}/notes`);
        this.notes = r.items || [];
      } catch (e) { if (!silent) Toast.show(e.message, "error"); }
    },
    async loadLinks(silent) {
      this.links = [];
      if (!this.desc || !this.desc.links) return;
      try {
        const r = await API.get(`/record/${this.table}/${this.rid}/links`);
        this.links = r.items || [];
      } catch (e) { if (!silent) Toast.show(e.message, "error"); }
    },
    async loadHistory(silent) {
      this.history = [];
      if (!this.desc || !this.desc.history) return;
      try {
        const r = await API.get(`/record/${this.table}/${this.rid}/history`);
        this.history = r.items || [];
      } catch (e) { if (!silent) Toast.show(e.message, "error"); }
    },

    async addNote() {
      const title = (this.noteTitle || "").trim();
      const content = (this.noteContent || "").trim();
      if (!title && !content) return;
      this.busy = true;
      try {
        await API.post(`/record/${this.table}/${this.rid}/notes`, { title, content });
        this.noteTitle = "";
        this.noteContent = "";
        await this.loadNotes();
        try { Sounds.play("success"); } catch (_) {}
      } catch (e) { Toast.show(e.message, "error"); }
      finally { this.busy = false; }
    },
    async delNote(id) {
      this.busy = true;
      try {
        await API.del(`/record/notes/${id}`);
        this.notes = this.notes.filter((n) => n.id !== id);
      } catch (e) { Toast.show(e.message, "error"); }
      finally { this.busy = false; }
    },
    async addLink() {
      const tid = parseInt(this.linkId, 10) || 0;
      if (!this.linkTable || !tid) return;
      this.busy = true;
      try {
        await API.post(`/record/${this.table}/${this.rid}/links`,
          { target_table: this.linkTable, target_id: tid, link_type: "related" });
        this.linkId = "";
        await this.loadLinks();
        try { Sounds.play("success"); } catch (_) {}
      } catch (e) { Toast.show(e.message, "error"); }
      finally { this.busy = false; }
    },
    async delLink(id) {
      this.busy = true;
      try {
        await API.del(`/record/links/${id}`);
        this.links = this.links.filter((l) => l.id !== id);
      } catch (e) { Toast.show(e.message, "error"); }
      finally { this.busy = false; }
    },
    async rollback(hid) {
      const ok = confirm(this.ru("Откатить это изменение?", "Roll back this change?"));
      if (!ok) return;
      this.busy = true;
      try {
        await API.post(`/record/${this.table}/${this.rid}/history/${hid}/rollback`);
        await this.loadAll();
        try { Sounds.play("success"); } catch (_) {}
      } catch (e) { Toast.show(e.message, "error"); }
      finally { this.busy = false; }
    },

    fmtVal(v) {
      if (v === null || v === undefined) return "—";
      if (typeof v === "boolean") return v ? "✓" : "—";
      const s = String(v);
      return s.length > 300 ? s.slice(0, 300) + "…" : s;
    },
  };
};
