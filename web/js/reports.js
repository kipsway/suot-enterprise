/* SUOT Neo — Конструктор отчётов + быстрые фильтры (Часть 14). */

window.reportBuilder = function () {
  return {
    open: false, busy: false, error: "",
    saveName: "", saveBusy: false, saveMsg: "",
    tableKey: "", tableLabel: "",
    cols: [], selectedCols: new Set(),
    groupBy: "", aggregate: "count", aggField: "",
    q: "", filters: {},
    result: null,

    icons: window.ICONS,
    t: (k) => I18N.t(k),
    ru: (a, b) => I18N.lang === "ru" ? a : b,

    async openR(key) {
      this.tableKey = key;
      this.tableLabel = Alpine.store("tabs").labelFor(key);
      this.open = true;
      this.result = null;
      this.error = "";
      this.groupBy = "";
      this.aggField = "";
      this.q = "";
      this.filters = {};
      try {
        const meta = await API.get(
          this.isCustom ? `/custom/meta/${key}` : `/meta/${key}`);
        this.cols = (meta.columns || [])
          .filter((c) => c.name !== "ID")
          .map((c) => ({ name: c.name, type: c.type || "Текст",
                         checked: true }));
        this.selectedCols = new Set(this.cols.map((c) => c.name));
      } catch (e) { this.cols = []; }
    },
    get isCustom() { return this.tableKey.startsWith("u_"); },
    toggleCol(name) {
      if (this.selectedCols.has(name)) this.selectedCols.delete(name);
      else this.selectedCols.add(name);
    },
    addFilter() {
      this.filters[""] = [];
    },
    removeFilter(key) { delete this.filters[key]; },
    setFilterKey(oldKey, newKey) {
      if (oldKey === newKey) return;
      const vals = this.filters[oldKey] || [];
      delete this.filters[oldKey];
      this.filters[newKey] = vals;
    },

    async run() {
      this.busy = true;
      this.error = "";
      try {
        const body = {
          table: this.tableKey,
          columns: [...this.selectedCols],
          group_by: this.groupBy,
          aggregate: this.aggregate,
          aggregate_field: this.aggField,
          q: this.q,
          filters: Object.fromEntries(
            Object.entries(this.filters)
              .filter(([k]) => k)
              .map(([k, v]) => [k, Array.isArray(v) ? v : [v]])),
        };
        this.result = await API.post("/reports/run", body);
      } catch (e) { this.error = e.message; }
      this.busy = false;
    },
    async saveSpec() {
      /* Сохранить текущую спеку в Documents Center (Блок 7). */
      if (!String(this.saveName || "").trim()) {
        this.saveMsg = this.ru("Укажите название", "Name is required");
        return;
      }
      this.saveBusy = true; this.saveMsg = "";
      try {
        await API.post("/documents/reports/saved", {
          name: this.saveName.trim(),
          table: this.tableKey,
          columns: [...this.selectedCols],
          group_by: this.groupBy,
          aggregate: this.aggregate,
          aggregate_field: this.aggField,
          q: this.q,
          filters: Object.fromEntries(
            Object.entries(this.filters)
              .filter(([k]) => k)
              .map(([k, v]) => [k, Array.isArray(v) ? v : [v]])),
        });
        this.saveMsg = this.ru("Сохранено", "Saved");
        this.saveName = "";
        document.dispatchEvent(new CustomEvent("suot-saved-reports-changed",
          { bubbles: true }));
      } catch (e) { this.saveMsg = e.message; }
      this.saveBusy = false;
    },
    exportCsv() {
      if (!this.result) return;
      let lines;
      if (this.result.mode === "grouped") {
        lines = ["Группа;Количество;" + (this.result.groups[0]
          ? this.result.groups[0].aggregate_label : "")];
        this.result.groups.forEach((g) =>
          lines.push(`${g.group};${g.count};${g.aggregate}`));
      } else {
        lines = [this.result.columns.join(";")];
        this.result.items.forEach((r) =>
          lines.push(this.result.columns.map(
            (c) => `"${r[c] || ""}"`).join(";")));
      }
      const blob = new Blob(["\ufeff" + lines.join("\n")],
        { type: "text/csv;charset=utf-8" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `report_${this.tableKey}.csv`;
      a.click();
      URL.revokeObjectURL(a.href);
    },
  };
};

/* Быстрые фильтры-чипсы для tablePage */
window.applyQuickFilter = async function (key, filter) {
  const tp = window.__tables && window.__tables[key];
  if (!tp) return;
  if (filter === "mine") {
    tp.q = "";
    tp.filters = {};
    await tp.reload();
    return;
  }
  try {
    const res = await API.get(`/quick_filters/${key}`);
    const f = res.filters.find((f) => f.key === filter);
    if (!f) return;
    if (f.field === "Статус") {
      tp.filters = { "Статус": new Set(f.values) };
    }
    tp.page = 1;
    await tp.reload();
  } catch (e) { Toast.show(e.message, "error"); }
};
