/* SUOT Neo — диалог экспорта (Часть 10). */
(function () {
  window.exportDialog = function () {
    return {
      open: false,
      tableKey: "",
      tableLabel: "",
      cols: [],                    // [{name,type,source,checked}]
      range: "filtered",           // selected | filtered | all
      format: "xlsx",
      withPhotos: false,
      zipPhotos: false,
      busy: false,
      error: "",

      icons: window.ICONS,
      t: (k) => I18N.t(k),
      ru: (a, b) => I18N.lang === "ru" ? a : b,

      async openD(key) {
        this.tableKey = key;
        this.tableLabel = Alpine.store("tabs").labelFor(key);
        this.open = true;
        this.error = "";
        this.range = "filtered";
        this.format = "xlsx";
        this.withPhotos = false;
        this.zipPhotos = false;
        try {
          const res = await API.get(
            this.isCustom ? `/custom/meta/${key}` : `/meta/${key}`);
          this.cols = (res.columns || [])
            .filter((c) => c.name !== "ID")
            .map((c) => ({ name: c.name, type: c.type || "Текст",
                           checked: true }));
        } catch (e) { this.cols = []; }
      },
      get isCustom() { return this.tableKey.startsWith("u_"); },
      get checkedCount() {
        return this.cols.filter((c) => c.checked).length;
      },
      selectAllCols(v) { this.cols.forEach((c) => (c.checked = v)); },

      get hasPhotoCol() {
        return this.cols.some((c) =>
          c.name === "Фото" || c.type === "Медиа");
      },
      get canPhotos() {
        return this.format === "xlsx" && this.hasPhotoCol;
      },

      _query() {
        const tp = window.__tables && window.__tables[this.tableKey];
        if (this.range === "all" || !tp) return {};
        const params = new URLSearchParams();
        if (this.range === "filtered") {
          if (tp.q && tp.q.trim()) params.set("q", tp.q.trim());
          for (const [col, set] of Object.entries(tp.filters || {}))
            if (set && set.size)
              params.set("f_" + col, [...set].join(","));
          if (tp.sortBy) {
            params.set("sort_by", tp.sortBy);
            params.set("order", tp.order);
          }
        }
        return params;
      },
      _ids() {
        if (this.range !== "selected") return [];
        const tp = window.__tables && window.__tables[this.tableKey];
        return tp ? [...tp.selected] : [];
      },

      async doExport() {
        if (this.busy) return;
        const cols = this.cols.filter((c) => c.checked)
          .map((c) => c.name);
        if (!cols.length) {
          this.error = this.ru("Выберите хотя бы одну колонку",
                               "Select at least one column");
          return;
        }
        this.busy = true;
        this.error = "";
        try {
          const body = {
            table: this.tableKey, columns: cols,
            ids: this._ids(), with_photos: this.withPhotos,
            title: this.tableLabel,
          };
          const qs = this._query();
          let url;
          if (this.format === "xlsx" && this.zipPhotos)
            url = `/export/xlsx_photos_zip/${this.tableKey}`;
          else
            url = `/export/${this.format}/${this.tableKey}`;
          const qp = qs.toString();
          const res = await fetch(url + (qp ? "?" + qp : ""), {
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
          const ext = this.format === "xlsx" && this.zipPhotos
            ? "zip" : this.format;
          const a = document.createElement("a");
          a.href = URL.createObjectURL(blob);
          a.download = `${this.tableLabel || this.tableKey}_` +
            `${new Date().toISOString().slice(0, 10)}.${ext}`;
          document.body.appendChild(a);
          a.click();
          a.remove();
          URL.revokeObjectURL(a.href);
          Toast.show(this.ru("Экспорт готов ✓", "Export ready ✓"),
                     "success");
          this.open = false;
        } catch (e) { this.error = e.message; }
        this.busy = false;
      },
    };
  };
})();
