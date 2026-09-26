/* SUOT Neo — Редактор печати (Часть 12).
   Мини-Word: форматирование, переменные, картинки, страницы,
   живой предпросмотр, копирование, экспорт/импорт, сетка. */

window.printEditor = function () {
  return {
    /* ── состояние ── */
    templates: [], tplFilter: "all", loading: true,
    cur: null,                  // {id, name, ...}
    editorHtml: "",
    editorOpen: false,
    gridOn: false,
    previewHtml: "",
    previewRecId: 0,
    previewRecords: [],
    vars: [],
    varSearch: "",
    varOpen: false,
    pageSetup: { size: "A4", orientation: "portrait", margins: "20mm" },
    setupOpen: false,
    form: { name: "", category: "", is_public: false },
    editMeta: false,
    busy: false,
    exportId: null,
    importFile: null,
    watermarkText: "",

    icons: window.ICONS,
    t: (k) => I18N.t(k),
    ru: (a, b) => I18N.lang === "ru" ? a : b,

    async init() {
      await this.load();
      /* Deep-link из Documents Center (Блок 7): открыть шаблон сразу. */
      try {
        const pid = window.__printEditId || 0;
        window.__printEditId = 0;
        if (pid) {
          const t = (this.templates || []).find((x) => x.id === pid);
          if (t) await this.openEditor(t);
        }
      } catch (_) {}
    },

    /* ── Список шаблонов ── */
    async load() {
      this.loading = true;
      try {
        this.templates = (await API.get("/print/templates")).items;
      } catch (e) { Toast.show(e.message, "error"); }
      this.loading = false;
    },
    get filtered() {
      if (this.tplFilter === "all") return this.templates;
      if (this.tplFilter === "my")
        return this.templates.filter((t) => !t.is_public);
      return this.templates.filter((t) => t.is_public);
    },

    /* ── CRUD ── */
    async openEditor(t) {
      if (t && t.id) {
        try {
          const res = await API.get("/print/templates/" + t.id);
          this.cur = res.template;
          this.editorHtml = res.template.html_content || "";
          this.pageSetup = {
            size: res.template.page_size || "A4",
            orientation: res.template.orientation || "portrait",
            margins: res.template.margins || "20mm",
          };
          this.form = { name: res.template.name,
                        category: res.template.category || "",
                        is_public: !!res.template.is_public };
        } catch (e) { Toast.show(e.message, "error"); return; }
      } else {
        this.cur = { id: null, name: this.ru("Новый шаблон", "New template") };
        this.editorHtml = "<p><br></p>";
        this.pageSetup = { size: "A4", orientation: "portrait",
                           margins: "20mm" };
        this.form = { name: this.ru("Новый шаблон", "New template"),
                      category: "", is_public: false };
      }
      this.editorOpen = true;
      this.gridOn = false;
      this.previewHtml = "";
      this.previewRecId = 0;
      await this.loadVars();
      await this.loadPreviewRecords();
      this.$nextTick(() => this.initEditor());
    },
    async loadVars() {
      const table = this.detectTable();
      if (!table) { this.vars = []; return; }
      try {
        this.vars = (await API.get("/print/variables/" + table)).items;
      } catch (_) { this.vars = []; }
    },
    detectTable() {
      for (const t of DatabaseManager_JSON_KEYS()) {
        if (this.editorHtml.includes("{" + t) ||
            this.cur && this.cur.category &&
            this.cur.category.toLowerCase().includes(t.slice(0, 4)))
          return t;
      }
      return "employees";
    },

    async saveTemplate() {
      if (!this.form.name.trim()) return;
      this.busy = true;
      const content = this.getEditorContent();
      const payload = { ...this.form, html_content: content,
        page_size: this.pageSetup.size,
        orientation: this.pageSetup.orientation,
        margins: this.pageSetup.margins };
      try {
        if (this.cur && this.cur.id)
          await API.put("/print/templates/" + this.cur.id, payload);
        else {
          const res = await API.post("/print/templates", payload);
          this.cur = { ...this.cur, id: res.id };
        }
        Toast.show(I18N.t("tbl.savedOk"), "success");
      } catch (e) { Toast.show(e.message, "error"); }
      this.busy = false;
    },
    async removeTemplate(t) {
      try {
        await API.del("/print/templates/" + t.id);
        this.load();
        Toast.show(I18N.t("tbl.deletedOk").replace("{n}", 1), "success");
      } catch (e) { Toast.show(e.message, "error"); }
    },
    async copyTemplate(t) {
      try {
        const res = await API.post("/print/templates/" + t.id + "/copy");
        Toast.show(I18N.t("cl.tplSaved"), "success");
        this.load();
      } catch (e) { Toast.show(e.message, "error"); }
    },

    /* ── Экспорт/импорт (предложение 3) ── */
    async exportTemplate(t) {
      try {
        const data = await API.get("/print/templates/" + t.id + "/export");
        const blob = new Blob([JSON.stringify(data, null, 2)],
          { type: "application/json" });
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = t.name.replace(/[^a-zA-Zа-яА-Я0-9 _-]/g, "") + ".stpl";
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(a.href);
      } catch (e) { Toast.show(e.message, "error"); }
    },
    async importTemplate(ev) {
      const f = ev.target.files && ev.target.files[0];
      if (!f) return;
      ev.target.value = "";
      try {
        const text = await f.text();
        const data = JSON.parse(text);
        if (data._export !== "suot_template_v1")
          throw new Error(this.ru("Неверный формат файла",
            "Invalid file format"));
        const res = await API.post("/print/import_template", {
          name: data.name + " (импорт)",
          category: data.category || "",
          html_content: data.html_content || "",
          page_size: data.page_size || "A4",
          orientation: data.orientation || "portrait",
          margins: data.margins || "20mm",
        });
        Toast.show(I18N.t("tbl.savedOk"), "success");
        this.load();
      } catch (e) { Toast.show(e.message, "error"); }
    },

    /* ── Редактор ── */
    initEditor() {
      const el = document.getElementById("print-editor-area");
      if (el) { el.innerHTML = this.editorHtml || "<p><br></p>"; }
    },
    getEditorContent() {
      const el = document.getElementById("print-editor-area");
      return el ? el.innerHTML : "";
    },
    execCmd(cmd, val) {
      document.execCommand(cmd, false, val || null);
      const el = document.getElementById("print-editor-area"); if (el) el.focus();
    },
    insertHtml(html) {
      document.execCommand("insertHTML", false, html);
      const el = document.getElementById("print-editor-area"); if (el) el.focus();
    },
    insertVariable(v) {
      this.insertHtml('<span class="tpl-var" contenteditable="false">' +
        v + "</span>&nbsp;");
      this.varOpen = false;
    },
    insertImage() {
      const inp = document.createElement("input");
      inp.type = "file";
      inp.accept = "image/*";
      inp.onchange = () => {
        const file = inp.files && inp.files[0];
        if (!file) return;
        if (file.size > 2 * 1024 * 1024) {
          Toast.show(this.ru("Картинка больше 2 МБ", "Image > 2MB"), "error");
          return;
        }
        const reader = new FileReader();
        reader.onload = () => {
          this.insertHtml('<img src="' + reader.result +
            '" style="max-width:100%;border-radius:8px" contenteditable="false">');
        };
        reader.readAsDataURL(file);
      };
      inp.click();
    },
    insertTable() {
      this.insertHtml(
        '<table class="print-tbl" style="border-collapse:collapse;width:100%">' +
        '<tr><td style="border:1px solid #ccc;padding:6px">Колонка 1</td>' +
        '<td style="border:1px solid #ccc;padding:6px">Колонка 2</td></tr>' +
        '<tr><td style="border:1px solid #ccc;padding:6px"></td>' +
        '<td style="border:1px solid #ccc;padding:6px"></td></tr></table><p><br></p>');
    },

    /* ── Предпросмотр (предложение 1) ── */
    async loadPreviewRecords() {
      const table = this.detectTable();
      try {
        const res = await API.get("/data/" + table + "?page_size=20");
        this.previewRecords = res.items.map((r) => ({
          id: r.id, label: String(r.data["ФИО"] ||
            r.data["Описание"] || r.data["Наименование"] ||
            r.data["title"] || "#" + r.id),
        }));
      } catch (_) { this.previewRecords = []; }
      if (this.previewRecords.length) {
        this.previewRecId = this.previewRecords[0].id;
        await this.doPreview();
      }
    },
    async doPreview() {
      if (!this.previewRecId) return;
      try {
        const res = await API.post("/print/preview", {
          html_content: this.getEditorContent(),
          table: this.detectTable(),
          record_id: this.previewRecId,
        });
        this.previewHtml = res.html;
      } catch (e) { Toast.show(e.message, "error"); }
    },

    /* ── Страница ── */
    get pageCss() {
      const sizes = { A4: "210mm 297mm", A5: "148mm 210mm" };
      let w = "210mm", h = "297mm";
      if (sizes[this.pageSetup.size]) {
        [w, h] = sizes[this.pageSetup.size].split(" ");
      }
      if (this.pageSetup.orientation === "landscape")
        [w, h] = [h, w];
      return `width:${w};min-height:${h};padding:${this.pageSetup.margins}`;
    },
    toggleGrid() {
      this.gridOn = !this.gridOn;
      const el = document.getElementById("print-editor-area");
      if (el) el.style.backgroundImage = this.gridOn
        ? "repeating-linear-gradient(0deg, transparent, transparent 23px, rgba(99,102,241,.06) 24px)"
        : "";
    },
  };
};

function DatabaseManager_JSON_KEYS() {
  return ["employees", "violations", "incidents", "ppe", "training",
          "permits", "work_orders", "companies", "custom_ledger"];
}
