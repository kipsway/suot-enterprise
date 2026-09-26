/* SUOT Next — Documents Center (Блок 7).
   Шаблоны печати (CRUD + версии + restore + предпросмотр),
   сохранённые отчёты (запуск/удаление + сохранение спеки из конструктора),
   очередь печати (создание, прогресс, отмена, повтор, скачивание, PDF-preview).
   Все строки RU/EN; состояния loading/empty/error/busy явные. */

window.docCenter = function () {
  return {
    tab: "templates",
    ru: (a, b) => { try { return I18N.lang === "ru" ? a : b; } catch (_) { return a; } },

    /* ── справочники ── */
    tables: [],

    /* ── шаблоны ── */
    templates: [],
    tplLoading: false, tplError: "",
    versTplId: 0, versions: [], versLoading: false, versError: "",

    /* ── предпросмотр ── */
    prevTitle: "", prevHtml: "", prevPdfUrl: "", prevBusy: false, prevError: "",

    /* ── отчёты ── */
    saved: [], repLoading: false, repError: "",
    runTitle: "", runResult: null, runBusy: false, runError: "",

    /* ── очередь печати ── */
    jobs: [], jobsLoading: false, jobsError: "",
    jobForm: { name: "", template_id: 0, table: "employees", ids: "",
      watermark: "", merge: true, page: "A4", orient: "portrait", margins: "15mm" },
    jobBusy: false, jobError: "",
    _pollTimer: 0,

    async init() {
      await this.loadTables();
      await Promise.all([this.loadTemplates(), this.loadSaved(), this.loadJobs()]);
      this._poll();
    },

    /* Списки свежие при каждом возврате на вкладку (как дашборд):
       шаблоны могли измениться в редакторе, отчёты — в конструкторе. */
    onTabActive() {
      try {
        const a = Alpine.store("tabs").active;
        if (a && a.type === "documents") {
          this.loadTemplates(); this.loadSaved(); this.loadJobs();
        }
      } catch (_) {}
    },

    /* ── общее ── */
    errMsg(e, fallback) {
      const m = (e && (e.message || e.detail)) || "";
      return m || fallback;
    },
    jobActive(j) {
      return j && (j.status === "queued" || j.status === "running");
    },
    jobStatusRu(s) {
      const map = { queued: this.ru("В очереди", "Queued"),
        running: this.ru("Выполняется", "Running"),
        done: this.ru("Готово", "Done"), error: this.ru("Ошибка", "Error"),
        canceled: this.ru("Отменено", "Canceled") };
      return map[s] || s;
    },

    async loadTables() {
      try {
        const r = await API.get("/documents/tables");
        this.tables = r.items || [];
      } catch (_) { this.tables = []; }
    },

    /* ── шаблоны ── */
    async loadTemplates() {
      this.tplLoading = true; this.tplError = "";
      try {
        const r = await API.get("/print/templates");
        this.templates = r.items || [];
      } catch (e) {
        this.tplError = this.errMsg(e, this.ru("Не загрузилось", "Load failed"));
      }
      this.tplLoading = false;
    },
    /* Редактирование — в полноценном редакторе печати (print_editor),
       здесь только deep-link, без дублирования мини-Word. */
    openInEditor(id) {
      try { window.__printEditId = id || 0; } catch (_) {}
      try { Alpine.store("tabs").open("print_editor"); } catch (_) {}
    },
    async deleteTemplate(id) {
      if (!confirm(this.ru("Удалить шаблон?", "Delete template?"))) return;
      try {
        await API.del("/print/templates/" + id);
        if (this.versTplId === id) { this.versTplId = 0; this.versions = []; }
        await this.loadTemplates();
      } catch (e) {
        Toast.show(this.errMsg(e, this.ru("Не удалилось", "Delete failed")), "error");
      }
    },
    async previewTemplateHtml(id) {
      this.prevTitle = ""; this.prevHtml = ""; this.prevPdfUrl = "";
      this.prevBusy = true; this.prevError = "";
      try {
        const r = await API.get("/print/templates/" + id);
        const t = r.template || {};
        this.prevTitle = t.name || "";
        const p = await API.post("/print/preview",
          { html_content: t.html_content || "", table: "employees", record_id: 0 });
        this.prevHtml = p.html || "";
      } catch (e) {
        this.prevError = this.errMsg(e, this.ru("Не открылось", "Open failed"));
      }
      this.prevBusy = false;
    },
    closePreview() {
      try {
        if (this.prevPdfUrl) URL.revokeObjectURL(this.prevPdfUrl);
      } catch (_) {}
      this.prevTitle = ""; this.prevHtml = ""; this.prevPdfUrl = "";
      this.prevError = "";
    },

    /* ── версии ── */
    async toggleVersions(id) {
      if (this.versTplId === id) { this.versTplId = 0; this.versions = []; return; }
      this.versTplId = id; this.versions = [];
      this.versLoading = true; this.versError = "";
      try {
        const r = await API.get("/documents/templates/" + id + "/versions");
        this.versions = r.items || [];
      } catch (e) {
        this.versError = this.errMsg(e, this.ru("Не загрузилось", "Load failed"));
      }
      this.versLoading = false;
    },
    async restoreVersion(tid, vid) {
      if (!confirm(this.ru("Откатить к этой версии? Текущий контент сохранится как новая версия.",
        "Restore this version? Current content will be kept as a new version."))) return;
      try {
        await API.post("/documents/templates/" + tid + "/restore", { version_id: vid });
        this.versTplId = 0; this.versions = [];
        await this.toggleVersions(tid);
        await this.loadTemplates();
        Toast.show(this.ru("Версия восстановлена", "Version restored"), "success");
      } catch (e) {
        Toast.show(this.errMsg(e, this.ru("Не откатилось", "Restore failed")), "error");
      }
    },

    /* ── сохранённые отчёты ── */
    async loadSaved() {
      this.repLoading = true; this.repError = "";
      try {
        const r = await API.get("/documents/reports/saved");
        this.saved = r.items || [];
      } catch (e) {
        this.repError = this.errMsg(e, this.ru("Не загрузилось", "Load failed"));
      }
      this.repLoading = false;
    },
    openBuilder() {
      const table = this.jobForm.table || "employees";
      document.dispatchEvent(new CustomEvent("suot-reports",
        { bubbles: true, detail: { key: table } }));
    },
    async runSaved(rep) {
      this.runTitle = rep.name || ""; this.runResult = null;
      this.runBusy = true; this.runError = "";
      try {
        this.runResult = await API.post(
          "/documents/reports/saved/" + rep.id + "/run", {});
      } catch (e) {
        this.runError = this.errMsg(e, this.ru("Не выполнилось", "Run failed"));
      }
      this.runBusy = false;
      if (!this.runError) {
        try {
          document.querySelector(".doc-center .doc-run").scrollIntoView({ block: "nearest" });
        } catch (_) {}
      }
    },
    async deleteSaved(id) {
      if (!confirm(this.ru("Удалить отчёт?", "Delete report?"))) return;
      try {
        await API.del("/documents/reports/saved/" + id);
        if (this.runTitle) { this.runTitle = ""; this.runResult = null; }
        await this.loadSaved();
      } catch (e) {
        Toast.show(this.errMsg(e, this.ru("Не удалилось", "Delete failed")), "error");
      }
    },

    /* ── очередь печати ── */
    async loadJobs() {
      this.jobsLoading = true; this.jobsError = "";
      try {
        const r = await API.get("/documents/print/jobs");
        this.jobs = r.items || [];
      } catch (e) {
        this.jobsError = this.errMsg(e, this.ru("Не загрузилось", "Load failed"));
      }
      this.jobsLoading = false;
    },
    _poll() {
      try { if (this._pollTimer) clearTimeout(this._pollTimer); } catch (_) {}
      this._pollTimer = 0;
      const active = (this.jobs || []).some((j) => this.jobActive(j));
      if (!active) return;
      this._pollTimer = setTimeout(async () => {
        try {
          if (!document.querySelector(".doc-center")) return; // pane уничтожен
          const r = await API.get("/documents/print/jobs");
          this.jobs = r.items || [];
        } catch (_) {}
        this._poll();
      }, 2500);
    },
    parseIds() {
      const out = [];
      String(this.jobForm.ids || "").split(/[^0-9]+/).forEach((s) => {
        const n = parseInt(s, 10);
        if (n > 0) out.push(n);
      });
      return out.slice(0, 200);
    },
    async createJob() {
      const f = this.jobForm;
      if (!f.template_id) {
        this.jobError = this.ru("Выберите шаблон", "Select a template");
        return;
      }
      this.jobBusy = true; this.jobError = "";
      try {
        const r = await API.post("/documents/print/jobs", {
          name: f.name || "", template_id: Number(f.template_id),
          table: f.table || "employees", record_ids: this.parseIds(),
          watermark_text: f.watermark || "", merge: !!f.merge,
          page_size: f.page || "A4", orientation: f.orient || "portrait",
          margins: f.margins || "15mm",
        });
        this.jobForm = { name: "", template_id: f.template_id,
          table: f.table, ids: "", watermark: "", merge: true,
          page: "A4", orient: "portrait", margins: "15mm" };
        await this.loadJobs();
        this._poll();
        Toast.show(this.ru("Задание создано", "Job created") + " #" + r.job_id, "success");
      } catch (e) {
        this.jobError = this.errMsg(e, this.ru("Не создалось", "Create failed"));
      }
      this.jobBusy = false;
    },
    async cancelJob(id) {
      try {
        await API.post("/documents/print/jobs/" + id + "/cancel", {});
        await this.loadJobs();
      } catch (e) {
        Toast.show(this.errMsg(e, this.ru("Не отменилось", "Cancel failed")), "error");
      }
    },
    async retryJob(id) {
      try {
        await API.post("/documents/print/jobs/" + id + "/retry", {});
        await this.loadJobs();
        this._poll();
      } catch (e) {
        Toast.show(this.errMsg(e, this.ru("Не перезапустилось", "Retry failed")), "error");
      }
    },
    async downloadJob(id) {
      try {
        const res = await fetch("/api/documents/print/jobs/" + id + "/download",
          { headers: API.authHeaders() });
        if (!res.ok) throw new Error("HTTP " + res.status);
        const blob = await res.blob();
        const cd = res.headers.get("Content-Disposition") || "";
        const m = cd.match(/filename=([^;]+)/);
        const name = (m && m[1].trim()) || ("print_job_" + id + ".pdf");
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url; a.download = name;
        document.body.appendChild(a); a.click();
        setTimeout(() => { try { URL.revokeObjectURL(url); a.remove(); } catch (_) {} }, 4000);
      } catch (e) {
        Toast.show(this.errMsg(e, this.ru("Не скачалось", "Download failed")), "error");
      }
    },
    async previewJobPdf(job) {
      this.prevTitle = job.name || ("#" + job.id);
      this.prevHtml = ""; this.prevPdfUrl = "";
      this.prevBusy = true; this.prevError = "";
      try {
        const res = await fetch("/api/documents/print/jobs/" + job.id + "/preview",
          { headers: API.authHeaders() });
        if (!res.ok) throw new Error("HTTP " + res.status);
        const blob = await res.blob();
        this.prevPdfUrl = URL.createObjectURL(blob);
      } catch (e) {
        this.prevError = this.errMsg(e, this.ru("Не открылось", "Open failed"));
      }
      this.prevBusy = false;
    },
  };
};
