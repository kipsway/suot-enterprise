/* SUOT Neo — Реестр «Всё» (Часть 24): единая таблица по всем модулям.
   Сквозной поиск q, фильтр по разделам, сортировка, пагинация, экспорт. */
(function () {

  function debounce(fn, ms) {
    let t;
    return function () {
      const that = this;
      const args = arguments;
      clearTimeout(t);
      t = setTimeout(() => fn.apply(that, args), ms);
    };
  }

  window.unionPage = function () {
    return {
      key: "all",
      rows: [],
      total: 0,
      page: 1,
      pageSize: 50,
      q: "",
      sections: [],           // [{section,label,count}]
      selSections: new Set(), // выбранные разделы (пусто → все)
      loading: true,
      exportBusy: false,
      err: "",
      cols: [],               // серверный union-список колонок (первые 5 показываем)
      sorting: "",
      order: "asc",

      icons: window.ICONS,
      t: (k) => I18N.t(k),
      ru: (a, b) => I18N.lang === "ru" ? a : b,

      async init() {
        await this.loadMeta();
        await this.reload();
      },

      async loadMeta() {
        try {
          const res = await API.get("/union/sections");
          this.sections = res.sections || [];
        } catch (e) { this.err = e.message; }
      },

      _qs() {
        const p = new URLSearchParams();
        p.set("page", this.page);
        p.set("page_size", this.pageSize);
        if (this.q && this.q.trim())
          p.set("q", this.q.trim());
        if (this.selSections.size)
          p.set("f_section", [...this.selSections].join(","));
        if (this.sorting) {
          p.set("sort_by", this.sorting);
          p.set("order", this.order);
        }
        return p.toString();
      },

      async reload() {
        this.loading = true;
        try {
          const res = await API.get("/union/records?" + this._qs());
          this.rows = res.items || [];
          this.total = res.total || 0;
          this.cols = (res.columns || []).slice(0, 5);
        } catch (e) { this.err = e.message; }
        this.loading = false;
      },
      onSearch: debounce(function () { this.page = 1; this.reload(); }, 300),

      toggleSection(sec) {
        if (this.selSections.has(sec)) this.selSections.delete(sec);
        else this.selSections.add(sec);
        this.page = 1;
        this.reload();
      },
      colCount() {
        return this.selSections.size;
      },
      clearSections() {
        this.selSections.clear();
        this.page = 1;
        this.reload();
      },

      go(p) {
        const maxp = Math.max(1, Math.ceil(this.total / this.pageSize));
        if (p < 1 || p > maxp) return;
        this.page = p;
        this.reload();
      },
      maxPage() {
        return Math.max(1, Math.ceil(this.total / this.pageSize));
      },
      sortBy(name) {
        if (this.sorting === name) {
          this.order = this.order === "asc" ? "desc" : "asc";
        } else {
          this.sorting = name;
          this.order = "asc";
        }
        this.page = 1;
        this.reload();
      },
      sortIc(name) {
        if (this.sorting !== name) return "";
        return this.order === "asc" ? "▲" : "▼";
      },

      cellValue(row, col) {
        const v = row.data ? row.data[col] : "";
        return v === undefined || v === null ? "—" :
          (typeof v === "object" ? JSON.stringify(v) : String(v));
      },

      openSection(section) {
        Alpine.store("tabs").open(section);
      },
      openRow(row) {
        Alpine.store("tabs").open(row.section);
      },

      async exportXlsx() {
        if (this.exportBusy) return;
        this.exportBusy = true;
        try {
          const body = {
            q: this.q.trim(),
            sections: [...this.selSections],
            columns: this.cols,
            format: "xlsx",
            title: this.ru("Реестр «Всё»", "All records"),
          };
          const res = await fetch("/api/union/export", {
            method: "POST",
            headers: { "Authorization": "Bearer " +
              (localStorage.getItem("suot_token") ||
               sessionStorage.getItem("suot_token_session") || ""),
              "Content-Type": "application/json" },
            body: JSON.stringify(body),
          });
          if (!res.ok) {
            let msg = "HTTP " + res.status;
            try { msg = (await res.json()).detail || msg; } catch (_) {}
            throw new Error(msg);
          }
          const blob = await res.blob();
          const a = document.createElement("a");
          a.href = URL.createObjectURL(blob);
          a.download = "union_" + new Date().toISOString().slice(0, 10) + ".xlsx";
          document.body.appendChild(a);
          a.click();
          a.remove();
          URL.revokeObjectURL(a.href);
          Toast.show(this.ru("Экспорт готов ✓", "Export ready ✓"), "success");
        } catch (e) { this.err = e.message; }
        this.exportBusy = false;
      },
    };
  };
})();