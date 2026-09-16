/* SUOT Neo — мастер импорта (Часть 9).
   Файл/буфер → лист → маппинг (+схемы, объединение) → анализ → выполнение →
   отмена, история, шаблон, фото из ZIP. */
(function () {
  const COL_TYPES = {};

  window.importWizard = function () {
    return {
      open: false,
      step: 0,                    // 0 источник · 1 маппинг · 2 анализ · 3 итог
      tableKey: "",
      tableLabel: "",
      busy: false,
      error: "",

      fileId: "", filename: "",
      sheets: [], sheet: "",
      headers: [], previewRows: [],
      tableCols: [],

      mapping: {},                // колонка файла → колонка таблицы
      merges: [],                 // {target, partsStr, sep}
      keyField: "", mode: "upsert",

      schemes: [], schemeName: "",
      analysis: null,
      runResult: null,
      historyOpen: false, history: [],
      photoFile: null, photoResult: null,

      icons: window.ICONS,

      t: (k) => I18N.t(k),
      ru: (a, b) => I18N.lang === "ru" ? a : b,

      async openW(key) {
        this.tableKey = key;
        this.tableLabel = Alpine.store("tabs").labelFor(key);
        this.open = true;
        this.step = 0;
        this.error = "";
        this.fileId = "";
        this.sheets = [];
        this.headers = [];
        this.previewRows = [];
        this.mapping = {};
        this.merges = [];
        this.analysis = null;
        this.runResult = null;
        this.photoFile = null;
        this.photoResult = null;
        this.keyField = "";
        this.mode = "upsert";
        this.loadSchemes();
        this.loadHistory();
        try {
          const meta = await API.get(
            this.isCustom ? `/custom/meta/${key}` : `/meta/${key}`);
          this.tableCols = (meta.columns || [])
            .filter((c) => c.name !== "ID");
        } catch (e) { this.tableCols = []; }
      },

      get isCustom() { return this.tableKey.startsWith("u_"); },

      /* ── Источник ── */
      async pickFile(ev) {
        const f = ev.target.files && ev.target.files[0];
        if (!f) return;
        ev.target.value = "";
        this.busy = true;
        this.error = "";
        try {
          const fd = new FormData();
          fd.append("file", f);
          const res = await fetch("/api/import/upload", {
            method: "POST",
            headers: API.authHeaders(),
            body: fd,
          });
          const j = await res.json();
          if (!res.ok) throw new Error(j.detail || res.status);
          this.fileId = j.file_id;
          this.filename = j.filename;
          this.sheets = j.sheets.filter(Boolean);
          this.sheet = this.sheets[0] || "";
          await this.afterSource();
        } catch (e) { this.error = e.message; }
        this.busy = false;
      },
      async pickClipboard() {
        this.busy = true;
        this.error = "";
        try {
          const text = await navigator.clipboard.readText();
          if (!text.trim()) throw new Error(
            this.ru("Буфер обмена пуст", "Clipboard is empty"));
          const res = await API.post("/import/upload_text",
            { text, filename: "clipboard.tsv" });
          this.fileId = res.file_id;
          this.filename = res.filename;
          this.sheets = [];
          this.sheet = "";
          await this.afterSource();
        } catch (e) { this.error = e.message; }
        this.busy = false;
      },
      async afterSource() {
        const res = await API.get(
          `/import/preview/${this.fileId}?sheet=` +
          encodeURIComponent(this.sheet) + "&limit=5");
        this.headers = res.headers;
        this.previewRows = res.rows;
        this.autoMapping();
        this.step = 1;
      },
      async setSheet(s) {
        this.sheet = s;
        await this.afterSource();
      },

      /* ── Маппинг ── */
      autoMapping() {
        const m = {};
        for (const h of this.headers) {
          const hit = this.tableCols.find(
            (c) => c.name.toLowerCase() === h.toLowerCase());
          if (hit) m[h] = hit.name;
        }
        this.mapping = m;
        // авто-key: ФИО или Наименование
        const kf = ["ФИО", "Наименование", "Название", "Тема",
          "Номер наряда"].find((n) =>
          this.tableCols.some((c) => c.name === n));
        this.keyField = kf || "";
      },
      get mappedCount() {
        return Object.values(this.mapping).filter(Boolean).length;
      },
      addMerge() {
        this.merges.push({ target: "", partsStr: "", sep: " " });
      },
      removeMerge(i) { this.merges.splice(i, 1); },

      /* ── Схемы маппинга ── */
      loadSchemes() {
        try {
          this.schemes = JSON.parse(
            localStorage.getItem("suot_impmap_" + this.tableKey) || "[]");
        } catch (_) { this.schemes = []; }
      },
      saveScheme() {
        const name = this.schemeName.trim();
        if (!name) return;
        this.schemes.push({
          name,
          mapping: { ...this.mapping },
          merges: this.merges.map((m) => ({ ...m })),
          keyField: this.keyField, mode: this.mode,
        });
        localStorage.setItem("suot_impmap_" + this.tableKey,
          JSON.stringify(this.schemes));
        this.schemeName = "";
        Toast.show(I18N.t("pr.saved"), "success");
      },
      applyScheme(s) {
        this.mapping = { ...s.mapping };
        this.merges = (s.merges || []).map((m) => ({ ...m }));
        this.keyField = s.keyField || "";
        this.mode = s.mode || "upsert";
        Toast.show(I18N.t("pr.appliedOk"), "success");
      },
      deleteScheme(i) {
        this.schemes.splice(i, 1);
        localStorage.setItem("suot_impmap_" + this.tableKey,
          JSON.stringify(this.schemes));
      },

      /* ── Анализ и выполнение ── */
      _payload(dry) {
        return {
          file_id: this.fileId,
          sheet: this.sheet,
          table: this.tableKey,
          mapping: this.mapping,
          merges: this.merges.map((m) => ({
            target: m.target,
            parts: (m.partsStr || "").split(",").map(
              (x) => x.trim()).filter(Boolean),
            sep: m.sep || " ",
          })),
          key_field: this.keyField,
          mode: this.mode,
          dry,
        };
      },
      async doAnalyze() {
        if (!this.mappedCount) {
          this.error = this.ru(
            "Сопоставьте хотя бы одну колонку",
            "Map at least one column");
          return;
        }
        this.busy = true;
        this.error = "";
        try {
          this.analysis = await API.post("/import/analyze",
            this._payload(true));
          this.step = 2;
        } catch (e) { this.error = e.message; }
        this.busy = false;
      },
      async doRun() {
        this.busy = true;
        this.error = "";
        try {
          const payload = this._payload(false);
          delete payload.dry;
          this.runResult = await API.post("/import/run", payload);
          this.step = 3;
          document.dispatchEvent(new CustomEvent("suot-reload-tables",
            { bubbles: true }));
          document.dispatchEvent(new CustomEvent("suot-counts-changed",
            { bubbles: true }));
          this.loadHistory();
        } catch (e) { this.error = e.message; }
        this.busy = false;
      },
      async undoLast() {
        if (!this.runResult) return;
        try {
          const res = await API.post("/import/undo",
            { import_id: this.runResult.import_id });
          Toast.show(I18N.t("tbl.deletedOk")
            .replace("{n}", res.undone), "success");
          this.runResult = null;
          this.step = 0;
          document.dispatchEvent(new CustomEvent("suot-reload-tables",
            { bubbles: true }));
          this.loadHistory();
        } catch (e) { Toast.show(e.message, "error"); }
      },
      async loadHistory() {
        try {
          this.history = (await API.get("/import/history?limit=15")).items;
        } catch (_) { this.history = []; }
      },
      downloadErrors() {
        if (!this.runResult || !this.runResult.errors.length) return;
        const esc = (v) => '"' + String(v).replace(/"/g, '""') + '"';
        const lines = this.runResult.errors.map(
          (e) => [esc(e.row), esc(e.error)].join(";"));
        const blob = new Blob(["\ufeffстрока;ошибка\n" + lines.join("\n")],
          { type: "text/csv;charset=utf-8" });
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = "import_errors.csv";
        a.click();
        URL.revokeObjectURL(a.href);
      },
      downloadTemplate() {
        const a = document.createElement("a");
        a.href = "/api/import/template/" + this.tableKey;
        a.download = "template.xlsx";
        document.body.appendChild(a);
        a.click();
        a.remove();
      },
      close() {
        this.open = false;
        document.dispatchEvent(new CustomEvent("suot-reload-tables",
          { bubbles: true }));
      },

      /* ── Фото из ZIP ── */
      async pickPhotos(ev) {
        const f = ev.target.files && ev.target.files[0];
        if (!f) return;
        ev.target.value = "";
        this.busy = true;
        this.error = "";
        try {
          const fd = new FormData();
          fd.append("file", f);
          const res = await fetch("/api/import/upload", {
            method: "POST",
            headers: API.authHeaders(),
            body: fd,
          });
          const j = await res.json();
          if (!res.ok) throw new Error(j.detail || res.status);
          this.photoResult = await API.post("/import/photos_zip",
            { file_id: j.file_id, table: this.tableKey,
              match_by: this.keyField || "ФИО" });
          document.dispatchEvent(new CustomEvent("suot-reload-tables",
            { bubbles: true }));
        } catch (e) { this.error = e.message; }
        this.busy = false;
      },
    };
  };
})();
