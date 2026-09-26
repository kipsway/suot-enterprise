/* SUOT Next — Task Center (Блок 6).
   Единый центр фоновых задач поверх /api/jobs/*: активные с прогрессом
   и отменой, завершённые с retry, история, экспорт CSV. Бейдж активных —
   в root (taskActiveCount), обновляется по событию suot-tasks-changed.
   RU/EN, Esc, polling только пока открыт. */
window.taskCenter = function () {
  return {
    open: false,
    loading: false,
    loadError: "",
    jobs: [],
    busyId: "",
    _timer: null,

    icons: window.ICONS || {},
    t: (k) => { try { return I18N.t(k); } catch (_) { return k; } },
    ru: (a, b) => { try { return I18N.lang === "ru" ? a : b; } catch (_) { return a; } },

    show() {
      this.open = true;
      this.load();
      this.stopPoll();
      this._timer = setInterval(() => { this.load(true); }, 2000);
      this.$nextTick(() => {
        const el = this.$refs.tcClose;
        if (el) el.focus();
      });
    },
    hide() {
      this.open = false;
      this.stopPoll();
    },
    stopPoll() {
      if (this._timer) { clearInterval(this._timer); this._timer = null; }
    },
    activeJobs() {
      return (this.jobs || []).filter(
        (j) => j.status === "queued" || j.status === "running");
    },
    doneJobs() {
      return (this.jobs || []).filter(
        (j) => j.status !== "queued" && j.status !== "running");
    },
    kindLabel(kind) {
      const map = {
        delete: ["Удаление", "Delete"],
        edit: ["Изменение", "Edit"],
        custom_delete: ["Удаление", "Delete"],
        custom_edit: ["Изменение", "Edit"],
      };
      const pair = map[kind] || [kind, kind];
      return this.ru(pair[0], pair[1]);
    },
    statusLabel(st) {
      const map = {
        queued: ["В очереди", "Queued"],
        running: ["Выполняется", "Running"],
        completed: ["Готово", "Done"],
        failed: ["Ошибка", "Failed"],
        cancelled: ["Отменена", "Cancelled"],
      };
      const pair = map[st] || [st, st];
      return this.ru(pair[0], pair[1]);
    },
    async load(silent) {
      if (!this.open && !silent) return;
      if (!silent) { this.loading = true; this.loadError = ""; }
      try {
        const r = await API.get("/jobs/history?limit=50");
        this.jobs = r.items || [];
        try {
          document.dispatchEvent(new CustomEvent("suot-tasks-changed",
            { bubbles: true }));
        } catch (_) {}
      } catch (e) {
        if (!silent) this.loadError = e.message || String(e);
      } finally {
        if (!silent) this.loading = false;
      }
    },
    pct(j) {
      const t = parseInt(j.total, 10) || 0;
      if (!t) return 0;
      return Math.min(100, Math.round((parseInt(j.done, 10) || 0) * 100 / t));
    },
    async retryJob(id) {
      this.busyId = id;
      try {
        await API.post(`/jobs/${id}/retry`, {});
        await this.load();
        try { Sounds.play("success"); } catch (_) {}
      } catch (e) { Toast.show(e.message, "error"); }
      finally { this.busyId = ""; }
    },
    async cancelJob(id) {
      this.busyId = id;
      try {
        await API.post(`/jobs/${id}/cancel`, {});
        await this.load();
      } catch (e) { Toast.show(e.message, "error"); }
      finally { this.busyId = ""; }
    },
    async exportCsv() {
      try {
        const res = await fetch("/api/jobs/export.csv",
          { headers: API.authHeaders() });
        if (!res.ok) throw new Error("HTTP " + res.status);
        const blob = await res.blob();
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = "suot-bulk-jobs.csv";
        document.body.appendChild(a);
        a.click();
        setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 4000);
      } catch (e) { Toast.show(e.message, "error"); }
    },
  };
};
