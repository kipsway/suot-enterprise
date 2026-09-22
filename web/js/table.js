/* SUOT Neo — универсальный движок таблиц (Alpine-компонент tablePage).
   Сортировка, фильтры по колонкам, поиск, пагинация, выбор строк,
   массовые действия, инлайн-редактирование, CRUD-диалог, экспорт CSV. */
(function () {

  const NUM_TYPES = new Set(["Число", "ID"]);

  function debounce(fn, ms) {
    let t;
    return function (...args) {
      clearTimeout(t);
      t = setTimeout(() => fn.apply(this, args), ms);
    };
  }

  window.tablePage = function (tableKey) {
    return {
      /* ── состояние ── */
      key: tableKey,
      label: "",
      columns: [],              // [{name,type,visible}]
      rows: [],
      total: 0,
      page: 1,
      pageSize: parseInt(localStorage.getItem("suot_pagesize") || "50", 10),
      q: "",
      sortBy: "",
      order: "asc",
      filters: {},               // {colName: Set(values)}
      loading: true,
      selected: new Set(),
      /* popup фильтра */
      filterCol: null,
      filterValues: [],
      filterChecked: {},
      /* диалог */
      dialog: null,              // {mode:'add'|'edit', id?, form:{}}
      dialogBusy: false,
      /* подтверждение */
      confirm: null,             // {msg, ids}
      confirmBusy: false,
      /* инлайн-редактор */
      editing: null,             // {id, col, value}
      seeding: false,
      /* быстрый фильтр (по странице) */
      qfOn: localStorage.getItem("suot_qf") === "1",
      qf: {},                    // {colName: text}
      /* контекстное меню сортировки */
      ctx: null,                 // {col, x, y}
      /* загрузка фото */
      dzBusy: false,
      /* Часть 4: пресеты, плотность, справочники, дубликаты, запись-панель */
      density: localStorage.getItem("suot_density") || "comfortable",
      presets: [],
      presetName: "",
      presetsOpen: false,
      typesOpen: false,
      types: [],
      typeForm: { name: "", risk_category: "Средняя", description: "" },
      typeEditId: null,
      templates: [],
      tplChosen: "",
      dupWarn: null,             // {msg, payload}
      panel: null,               // {tab, items, ...}
      /* Часть 5: предпросмотр, undo, черновики, batch edit */
      previewRow: null,          // строка для панели-предпросмотра
      undoStack: [],             // [{undo: fn}]
      draftDirty: false,
      draftConfirm: null,        // true → показать модалку черновика
      cardMode: "table",         // Часть 21: table | cards
      /* ── Часть 23: колонки/группировка/комментарии ── */
      colWidths: {},
      colOrder: [],
      frozenCount: 0,
      dragCol: null,
      groupKey: "",
      collapsedGroups: [],
      cellCmt: null,
      _pendingDraft: null,
      bulkEditOpen: false,       // {field, value}
      beField: "",
      beValue: "",
      /* перенос записей */
      transferOpen: false,
      transferTo: "",
      transferMove: true,
      /* Часть 8: свои колонки, виды, предпросмотр */
      userCols: [],
      hiddenCols: new Set(JSON.parse(
        localStorage.getItem("suot_hidden_" + (tableKey || "")) || "[]")),
      viewsOpen: false,
      views: [],
      viewName: "",
      colsMgmtOpen: false,
      cmTab: "list",             // list | add
      cmForm: { name: "", type: "Текст", template: "" },
      cmEditId: null,
      cmRenameId: null,
      cmRenameVal: "",
      cmDupId: null,
      cmDupName: "",

      icons: window.ICONS,
      t: (k) => I18N.t(k),
      ru: (a, b) => I18N.lang === "ru" ? a : b,

      isCustom() { return (this.key || "").startsWith("u_"); },
      apiBase() {
        return this.key.startsWith("u_")
          ? "/custom/records/" + this.key : "/data/" + this.key;
      },
      valuesBase() {
        return this.key.startsWith("u_")
          ? `/custom/values/${this.key}` : `/data/${this.key}/values`;
      },

      /* ── Статусы и просрочка ── */
      DONE_SET: ["устранено", "исполнено", "resolved", "соответствует",
        "выполнено", "готово", "закрыто", "done", "архив", "уволен",
        "отменено", "closed"],
      badgeClass(val) {
        const v = String(val || "").trim().toLowerCase();
        if (!v) return "";
        if (["просрочено", "expired", "критический", "критическая"].includes(v))
          return "b-red";
        if (["устранено", "исполнено", "resolved", "соответствует",
             "выполнено", "готово", "закрыто", "done",
             "низкий", "низкая"].includes(v)) return "b-green";
        if (["активно", "активен", "active", "в работе", "на проверке",
             "средний", "средняя"].includes(v)) return "b-amber";
        if (["высокий", "высокая", "high"].includes(v)) return "b-orange";
        if (["архив", "уволен", "отменено", "closed"].includes(v))
          return "b-gray";
        return "b-blue";
      },
      isDone(val) {
        return this.DONE_SET.includes(String(val || "").trim().toLowerCase());
      },
      isDateCol(col) {
        return ["Годен до", "Дата проведения", "Дата", "Дата окончания",
                "Срок устранения", "Дата медосмотра", "Срок действия",
                "Дата выдачи"].includes(col.type) ||
               /срок|годен|окончан/i.test(col.name);
      },
      parseRuDate(s) {
        const m = /^(\d{2})\.(\d{2})\.(\d{4})$/.exec(String(s || "").trim());
        if (!m) return null;
        return new Date(+m[3], +m[2] - 1, +m[1]);
      },
      isOverdue(row, col) {
        if (!this.isDateCol(col)) return false;
        const d = this.parseRuDate(this.cell(row, col));
        if (!d) return false;
        const statusCol = this.columns.find((c) =>
          c.name === "Статус" || c.name === "Тяжесть");
        if (statusCol && this.isDone(row.data[statusCol.name])) return false;
        return d.getTime() < Date.now() - 86400000;
      },

      get visibleCols() {
        const base = this.columns.filter((c) => c.visible && c.name !== "ID"
          && !this.hiddenCols.has(c.name));
        const ucs = this.userCols.filter((c) => c.visible)
          .map((c) => ({ name: c.name, type: c.type,
                         template: c.template || "",
                         user: true, ucid: c.id }));
        const all = [...base, ...ucs];
        const order = this.viewOrder || [];
        if (order.length) {
          all.sort((a, b) => {
            const ia = order.indexOf(a.name);
            const ib = order.indexOf(b.name);
            return (ia < 0 ? 999 : ia) - (ib < 0 ? 999 : ib);
          });
        }
        return all;
      },
      isMedia(col) {
        return col.type === "Медиа" || col.type === "Фото";
      },
      isComputed(col) { return col.type === "Вычисляемая"; },
      colDisplay(row, col) {
        if (this.isComputed(col) && col.template) {
          return col.template.replace(/\{([^}]+)\}/g, (_, n) => {
            const v = row.data[n];
            return v === undefined || v === null ? "" : String(v);
          }).trim();
        }
        const v = row.data[col.name];
        return v === undefined || v === null ? "" : String(v);
      },
      typeIcon(col) {
        const m = { "Текст": "fileText", "Число": "command",
          "Дата": "calendar", "Годен до": "calendar",
          "Дата проведения": "calendar", "Статус": "bookmark",
          "Чекбокс": "checkAll", "Деньги": "database",
          "Вычисляемая": "layers", "Медиа": "image", "Фото": "image" };
        return this.icons[m[col.type]] || "";
      },
      isStatusCol(col) {
        return col.type === "Статус" || col.name === "Статус" ||
               col.name === "Тяжесть" || col.name === "Категория риска";
      },
      get isAdminUser() {
        try {
          return (Alpine.store("user") || {}).role === "Administrator";
        } catch (_) {
          return false;
        }
      },
      get pagesTotal() {
        return Math.max(1, Math.ceil(this.total / this.pageSize));
      },
      get pageNumbers() {
        const t = this.pagesTotal, cur = this.page, out = [];
        const from = Math.max(1, Math.min(cur - 2, t - 4));
        for (let i = from; i <= Math.min(t, from + 4); i++) out.push(i);
        return out;
      },
      get activeFilterCount() {
        return Object.values(this.filters).filter(
          (s) => s && s.size).length;
      },
      get rowsFiltered() {
        const qf = this.qf;
        const keys = Object.keys(qf).filter((k) => qf[k] && qf[k].trim());
        if (!keys.length) return this.rows;
        return this.rows.filter((row) =>
          keys.every((k) => {
            const col = this.columns.find((c) => c.name === k) ||
              this.userCols.find((c) => c.name === k);
            const colDef = col ? { name: k, type: col.type,
              template: col.template || "" } : { name: k, type: "Текст" };
            const v = this.colDisplay(row, colDef);
            return v.toLowerCase().includes(qf[k].trim().toLowerCase());
          }));
      },
      cell(row, col) {
        return this.colDisplay(row, col);
      },

      async init() {
        this.initCardMode();
        this.loadColPrefs();
        try {
          const meta = await API.get(this.isCustom() ? "/custom/meta/" + this.key : "/meta/" + this.key);
          this.label = meta.label_ru;
          this.columns = meta.columns.map((c) => ({
            name: c.name, type: c.type || "Текст",
            visible: c.visible !== 0 && c.visible !== false,
          }));
        } catch (e) {
          Toast.show(e.message, "error");
        }
        await this.reload();
        /* Горячие клавиши таблицы — только когда вкладка активна */
        this._keys = (e) => {
          const pane = this.$el.closest(".tabpane");
          if (pane && pane.style.display === "none") return;
          if (!this.$el.isConnected) {
            window.removeEventListener("keydown", this._keys);
            return;
          }
          const tag = (e.target.tagName || "").toLowerCase();
          const typing = tag === "input" || tag === "textarea" ||
                         tag === "select";
          if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "n") {
            e.preventDefault();
            this.openAdd();
          } else if ((e.ctrlKey || e.metaKey) &&
                     e.key.toLowerCase() === "z") {
            if (typing) return;
            e.preventDefault();
            this.undo();
          } else if (e.key === "F5") {
            e.preventDefault();
            this.reload(false);
          } else if (e.key === "Delete" && !typing &&
                     this.selected.size > 0) {
            e.preventDefault();
            this.askDelete([...this.selected]);
          }
        };
        window.addEventListener("keydown", this._keys);
        /* отладочный/тестовый доступ к инстансу таблицы */
        window.__tables = window.__tables || {};
        window.__tables[this.key] = this;
        if (!this.isCustom()) await this.loadUserCols();
        this.loadViews();
        this.loadPresets();
        /* дефолтный пресет (Q88) */
        const dp = localStorage.getItem("suot_defpreset_" + this.key);
        if (dp) {
          const p = this.presets.find((x) => x.name === dp);
          if (p) {
            this.q = p.q || "";
            this.filters = Object.fromEntries(
              Object.entries(p.filters || {}).map(([k, v]) =>
                [k, new Set(v)]));
            this.sortBy = p.sortBy || "";
            this.order = p.order || "asc";
            this.cast = p.cast || "";
            await this.reload();
          }
        }
      },

      /* ── Свои колонки (Часть 8) ── */
      async loadUserCols() {
        try {
          const res = await API.get("/ucols/" + this.key);
          this.userCols = res.items;
        } catch (_) { this.userCols = []; }
      },
      renderTemplate(tpl, row) {
        return String(tpl || "").replace(/\{([^}]+)\}/g, (_, n) => {
          const v = row.data[n];
          return v === undefined || v === null ? "" : String(v);
        }).trim();
      },

      /* ── Виды таблиц (Q83) ── */
      loadViews() {
        try {
          this.views = JSON.parse(
            localStorage.getItem("suot_views_" + this.key) || "[]");
        } catch (_) { this.views = []; }
      },
      saveView() {
        const name = this.viewName.trim();
        if (!name) return;
        this.views.push({
          name,
          hidden: [...this.hiddenCols],
          hiddenUser: this.userCols.filter((c) => !c.visible)
            .map((c) => c.name),
        });
        localStorage.setItem("suot_views_" + this.key,
          JSON.stringify(this.views));
        this.viewName = "";
        Toast.show(I18N.t("pr.saved"), "success");
      },
      async applyView(v) {
        this.hiddenCols = new Set(v.hidden || []);
        localStorage.setItem("suot_hidden_" + this.key,
          JSON.stringify([...this.hiddenCols]));
        for (const uc of this.userCols) {
          const want = !(v.hiddenUser || []).includes(uc.name);
          if (!!uc.visible !== want) {
            try {
              await API.put(`/ucols/${this.key}/${uc.id}`,
                            { visible: want });
              uc.visible = want ? 1 : 0;
            } catch (_) {}
          }
        }
        this.viewsOpen = false;
        Toast.show(I18N.t("pr.appliedOk"), "success");
      },
      deleteView(i) {
        this.views.splice(i, 1);
        localStorage.setItem("suot_views_" + this.key,
          JSON.stringify(this.views));
      },
      toggleHidden(name) {
        if (this.hiddenCols.has(name)) this.hiddenCols.delete(name);
        else this.hiddenCols.add(name);
        this.hiddenCols = new Set(this.hiddenCols);
        localStorage.setItem("suot_hidden_" + this.key,
          JSON.stringify([...this.hiddenCols]));
      },
      setDefaultPreset(name) {
        const cur = localStorage.getItem("suot_defpreset_" + this.key);
        if (cur === name) localStorage.removeItem("suot_defpreset_" + this.key);
        else localStorage.setItem("suot_defpreset_" + this.key, name);
      },
      isDefaultPreset(name) {
        return localStorage.getItem("suot_defpreset_" + this.key) === name;
      },

      /* ── Менеджер колонок ── */
      openColsManager() {
        this.cmTab = "list";
        this.cmForm = { name: "", type: "Текст", template: "" };
        this.cmEditId = null;
        this.cmRenameId = null;
        this.cmDupId = null;
        this.colsMgmtOpen = true;
      },
      get mergedForManager() {
        const sys = this.columns.filter((c) => c.name !== "ID")
          .map((c) => ({ name: c.name, type: c.type, template: "",
                         source: "sys",
                         hidden: this.hiddenCols.has(c.name) }));
        const mine = this.userCols.map((c) => ({
          id: c.id, name: c.name, type: c.type, template: c.template,
          source: "my", visible: !!c.visible }));
        return [...sys, ...mine];
      },
      async cmAdd() {
        if (!this.cmForm.name.trim()) return;
        try {
          await API.post("/ucols/" + this.key, this.cmForm);
          await this.loadUserCols();
          this.cmForm = { name: "", type: "Текст", template: "" };
          this.cmTab = "list";
          Toast.show(I18N.t("col.added"), "success");
        } catch (e) { Toast.show(e.message, "error"); }
      },
      async cmRename(id, oldName) {
        const val = this.cmRenameVal.trim();
        if (!val || val === oldName) { this.cmRenameId = null; return; }
        try {
          await API.put(`/ucols/${this.key}/${id}`, { name: val });
          this.cmRenameId = null;
          await this.loadUserCols();
        } catch (e) { Toast.show(e.message, "error"); }
      },
      async cmPatch(id, patch) {
        try {
          await API.put(`/ucols/${this.key}/${id}`, patch);
          await this.loadUserCols();
        } catch (e) { Toast.show(e.message, "error"); }
      },
      async cmDuplicate(id) {
        const name = this.cmDupName.trim();
        if (!name) return;
        try {
          await API.post(`/ucols/${this.key}/${id}/duplicate`,
                         { name });
          this.cmDupId = null;
          this.cmDupName = "";
          await this.loadUserCols();
          await this.reload();
          Toast.show(I18N.t("col.duplicated"), "success");
        } catch (e) { Toast.show(e.message, "error"); }
      },
      async cmDelete(id) {
        try {
          await API.del(`/ucols/${this.key}/${id}`);
          await this.loadUserCols();
        } catch (e) { Toast.show(e.message, "error"); }
      },
      cmPreview() {
        const f = this.cmForm;
        if (f.type === "Вычисляемая" && f.template) {
          const row = this.rows[0] || { data: {} };
          return this.renderTemplate(f.template, row) || "—";
        }
        return this.rows[0]
          ? this.cell(this.rows[0], { name: f.name, type: f.type })
          : "";
      },

      /* ── Пресеты фильтров ── */
      loadPresets() {
        try {
          this.presets = JSON.parse(
            localStorage.getItem("suot_presets_" + this.key) || "[]");
        } catch (_) {
          this.presets = [];
        }
      },
      savePreset() {
        const name = this.presetName.trim();
        if (!name) return;
        this.presets.push({
          name,
          q: this.q,
          filters: Object.fromEntries(
            Object.entries(this.filters).map(([k, s]) => [k, [...s]])),
          sortBy: this.sortBy, order: this.order, cast: this.cast,
        });
        localStorage.setItem("suot_presets_" + this.key,
          JSON.stringify(this.presets));
        this.presetName = "";
        Toast.show(I18N.t("pr.saved"), "success");
      },
      applyPreset(p) {
        this.q = p.q || "";
        this.filters = Object.fromEntries(
          Object.entries(p.filters || {}).map(([k, v]) => [k, new Set(v)]));
        this.sortBy = p.sortBy || "";
        this.order = p.order || "asc";
        this.cast = p.cast || "";
        this.page = 1;
        this.presetsOpen = false;
        this.reload();
      },
      deletePreset(i) {
        this.presets.splice(i, 1);
        localStorage.setItem("suot_presets_" + this.key,
          JSON.stringify(this.presets));
      },
      toggleDensity() {
        this.density = this.density === "comfortable" ? "compact"
          : "comfortable";
        localStorage.setItem("suot_density", this.density);
      },

      bumpCounts() {
        document.dispatchEvent(new CustomEvent("suot-counts-changed",
          { bubbles: true }));
      },

      async reload(keepSelection = true) {
        if (!keepSelection) this.selected.clear();
        this.loading = true;
        try {
          const params = new URLSearchParams({
            page: this.page, page_size: this.pageSize,
          });
          if (this.q.trim()) params.set("q", this.q.trim());
          if (this.sortBy) {
            params.set("sort_by", this.sortBy);
            params.set("order", this.order);
            if (this.cast) params.set("order_cast", this.cast);
          }
          for (const [col, set] of Object.entries(this.filters)) {
            if (set && set.size)
              params.set("f_" + col, [...set].join(","));
          }
          const res = await API.get(this.apiBase() + "?" + params);
          this.rows = res.items;
          this.total = res.total;
          const maxPage = Math.max(1, Math.ceil(this.total / this.pageSize));
          if (this.page > maxPage) { this.page = maxPage; return this.reload(); }
        } catch (e) {
          Toast.show(e.message, "error");
        } finally {
          this.loading = false;
        }
      },

      debouncedReload: null,
      onSearch() {
        if (!this.debouncedReload) {
          this.debouncedReload = debounce(() => {
            this.page = 1;
            this.reload(false);
          }, 300);
        }
        this.debouncedReload();
      },

      /* ── сортировка ── */
      cast: "",
      sortByCol(col, dir, cast) {
        this.sortBy = col;
        this.order = dir;
        this.cast = cast || "";
        this.ctx = null;
        this.reload();
      },
      toggleSort(col) {
        if (this.sortBy !== col) {
          this.sortBy = col;
          this.order = "asc";
          this.cast = "";
        } else if (this.order === "asc") {
          this.order = "desc";
        } else {
          this.sortBy = "";
          this.order = "asc";
          this.cast = "";
        }
        this.reload();
      },
      openCtx(e, col) {
        this.ctx = { col, x: e.clientX, y: e.clientY };
      },
      ctxSort(dir, cast) {
        this.sortByCol(this.ctx.col, dir, cast);
      },
      sortIcon(col) {
        if (this.sortBy !== col) return "";
        return this.order === "asc"
          ? this.icons.chevronUp : this.icons.chevronDown;
      },

      /* ── фильтр колонки ── */
      async openFilter(col) {
        if (this.filterCol === col) { this.filterCol = null; return; }
        this.filterCol = col;
        this.filterValues = [];
        this.filterChecked = {};
        const cur = this.filters[col];
        try {
          const res = await API.get(
            `${this.valuesBase()}?col=${encodeURIComponent(col)}`);
          this.filterValues = res.values.slice(0, 200);
          for (const v of this.filterValues)
            this.filterChecked[v] = !cur || cur.has(v);
        } catch (e) {
          Toast.show(e.message, "error");
          this.filterCol = null;
        }
      },
      applyFilter() {
        const chosen = new Set(Object.entries(this.filterChecked)
          .filter(([, v]) => v).map(([k]) => k));
        if (chosen.size && chosen.size < this.filterValues.length)
          this.filters[this.filterCol] = chosen;
        else delete this.filters[this.filterCol];
        this.filterCol = null;
        this.page = 1;
        this.reload();
      },
      resetFilter() {
        delete this.filters[this.filterCol];
        this.filterCol = null;
        this.page = 1;
        this.reload();
      },
      isFiltered(col) {
        const s = this.filters[col];
        return !!(s && s.size);
      },

      /* ── выбор строк ── */
      pageAllSelected() {
        return this.rows.length > 0 &&
          this.rows.every((r) => this.selected.has(r.id));
      },
      toggleAll() {
        if (this.pageAllSelected())
          this.rows.forEach((r) => this.selected.delete(r.id));
        else this.rows.forEach((r) => this.selected.add(r.id));
        this.selected = new Set(this.selected);   // триггер реактивности
      },
      toggleRow(id) {
        if (this.selected.has(id)) this.selected.delete(id);
        else this.selected.add(id);
        this.selected = new Set(this.selected);
      },
      clearSelection() {
        this.selected = new Set();
      },

      /* ── CRUD ── */
      openAdd() {
        const form = {};
        for (const c of this.visibleCols) form[c.name] = "";
        let restored = false;
        try {
          const draft = JSON.parse(
            localStorage.getItem(this._draftKey()) || "null");
          if (draft) {
            for (const k of Object.keys(form))
              if (draft[k]) { form[k] = draft[k]; restored = true; }
          }
        } catch (_) {}
        this.dialog = { mode: "add", form };
        this.draftDirty = false;
        this.tplChosen = "";
        if (this.key === "violations") this.loadTemplates();
        if (restored) Toast.show(I18N.t("dr.restored"));
      },
      async loadTemplates() {
        if (this.templates.length) return;
        try {
          const res = await API.get("/dicts/violation_templates");
          this.templates = res.items;
        } catch (_) {}
      },
      applyTemplate() {
        const t = this.templates.find((x) => String(x.id) === this.tplChosen);
        if (!t || !this.dialog) return;
        const d = t.data || {};
        if (d.risk_level) this.dialog.form["Категория риска"] = d.risk_level;
        if (t.name) this.dialog.form["Описание"] = t.name;
        if (d.recommended_action && !this.dialog.form["Описание"])
          this.dialog.form["Описание"] = d.recommended_action;
      },
      openEdit(row) {
        const form = {};
        for (const c of this.visibleCols) {
          const v = row.data[c.name];
          form[c.name] = v === undefined || v === null ? "" : String(v);
        }
        this.dialog = { mode: "edit", id: row.id, form };
      },

      /* ── Типы нарушений ── */
      async openTypes() {
        this.typesOpen = true;
        await this.loadTypes();
      },
      async loadTypes() {
        try {
          const res = await API.get("/dicts/violation_types");
          this.types = res.items;
        } catch (e) {
          Toast.show(e.message, "error");
        }
      },
      async saveType() {
        const f = this.typeForm;
        if (!f.name.trim()) return;
        try {
          if (this.typeEditId)
            await API.put("/dicts/violation_types/" + this.typeEditId, f);
          else
            await API.post("/dicts/violation_types", f);
          this.typeForm = { name: "", risk_category: "Средняя",
                            description: "" };
          this.typeEditId = null;
          await this.loadTypes();
        } catch (e) {
          Toast.show(e.message, "error");
        }
      },
      editType(t) {
        this.typeEditId = t.id;
        this.typeForm = { name: t.name, risk_category: t.risk_category,
                          description: t.description || "" };
      },
      async deleteType(t) {
        try {
          await API.del("/dicts/violation_types/" + t.id);
          await this.loadTypes();
        } catch (e) {
          Toast.show(e.message, "error");
        }
      },

      /* ── Проверка дубликата (violations) ── */
      async preSaveCheck(payload) {
        if (this.key !== "violations") { await this.doSave(payload); return; }
        const p = new URLSearchParams();
        for (const k of ["Дата", "Фирма", "Подразделение", "Описание"])
          if (payload.data[k]) p.set(k, payload.data[k]);
        if (![...p.keys()].length) { await this.doSave(payload); return; }
        try {
          const res = await API.get(
            "/data/violations/duplicate_check?" + p);
          if (res.found) {
            this.dupWarn = { id: res.id, payload,
              preview: res.preview || {} };
            return;
          }
        } catch (_) { /* сервер недоступен для проверки — сохраняем */ }
        await this.doSave(payload);
      },
      async doSave(payload) {
        let createdId = null;
        if (payload.mode === "add") {
          const res = await API.post(this.apiBase(),
                                     { data: payload.data });
          createdId = res.id;
        } else {
          await API.put(
            this.isCustom() ? `/custom/records/${this.key}/${payload.id}`
              : `/data/${this.key}/${payload.id}`, { data: payload.data });
        }
        this.toast(I18N.t("tbl.savedOk"), "success");
        this.dialog = null;
        this.draftDirty = false;
        localStorage.removeItem(this._draftKey());
        try { Alpine.store("tabs").touch(); } catch (_) {}
        await this.reload();
        this.bumpCounts();
        if (payload.mode === "add" && createdId) {
          this.pushUndo({
            label: "create",
            run: async () => {
              await API.del(
            this.isCustom() ? `/custom/records/${this.key}/${createdId}`
              : `/data/${this.key}/${createdId}`);
            },
          });
        } else if (payload.prevData) {
          const pid = payload.id;
          const prev = payload.prevData;
          this.pushUndo({
            label: "update",
            run: async () => {
              await API.put(
            this.isCustom() ? `/custom/records/${this.key}/${pid}`
              : `/data/${this.key}/${pid}`, { data: prev });
            },
          });
        }
      },
      async saveDupAnyway() {
        const p = this.dupWarn;
        this.dupWarn = null;
        if (p) await this.doSave(p.payload);
      },
      inputType(col) {
        if (col.type === "Число") return "number";
        return "text";
      },

      /* ── Фото (dropzone в диалоге) ── */
      dzPick(col) {
        const inp = document.getElementById(
          "dz-file-" + this.key + "-" + this._colSlug(col.name));
        if (inp) inp.click();
      },
      _colSlug(name) {
        let h = 0;
        for (let i = 0; i < name.length; i++)
          h = ((h << 5) - h + name.charCodeAt(i)) | 0;
        return Math.abs(h).toString(36);
      },
      async dzFiles(e, col) {
        const files = e.target.files || e.dataTransfer.files;
        e.target.value = "";
        if (!files || !files.length) return;
        this.dzBusy = true;
        try {
          const url = await Photos.upload(files[0]);
          if (this.dialog) this.dialog.form[col] = url;
          Toast.show("✓", "success");
        } catch (err) {
          Toast.show(err.message, "error");
        } finally {
          this.dzBusy = false;
        }
      },
      dzDrop(e, col) {
        e.preventDefault();
        e.currentTarget.classList.remove("dz-over");
        this.dzFiles(e, col);
      },
      removePhoto(col) {
        if (this.dialog) this.dialog.form[col] = "";
      },
      async saveDialog() {
        if (!this.dialog) return;
        this.dialogBusy = true;
        try {
          let prevData = null;
          let data;
          if (this.dialog.mode === "edit") {
            const r = this.rows.find((x) => x.id === this.dialog.id);
            prevData = r ? JSON.parse(JSON.stringify(r.data)) : null;
            data = prevData ? JSON.parse(JSON.stringify(prevData)) : {};
          } else {
            data = {};
          }
          for (const c of this.visibleCols) {
            const raw = this.dialog.form[c.name];
            const v = String(raw === undefined || raw === null
              ? "" : raw).trim();
            if (v !== "" || data[c.name] !== undefined)
              data[c.name] = col_is_number(c) ? (v === "" ? "" : Number(v)) : v;
          }
          if (this.dialog.mode === "add")
            await this.preSaveCheck({ mode: "add", data });
          else
            await this.preSaveCheck({ mode: "edit",
              id: this.dialog.id, data, prevData });
          /* dialog/reload закрывает doSave; при dupWarn форма остаётся */
        } catch (e) {
          Toast.show(e.message, "error");
        } finally {
          this.dialogBusy = false;
        }
      },
      askDelete(ids) {
        this.confirm = { ids };
      },
      async doConfirm() {
        if (!this.confirm) return;
        this.confirmBusy = true;
        try {
          const snapshots = [];
          for (const rid of this.confirm.ids) {
            const r = this.rows.find((x) => x.id === rid);
            if (r) snapshots.push(JSON.parse(JSON.stringify(r.data)));
          }
          const ids = [...this.confirm.ids];
          const res = await API.post(
            this.isCustom() ? `/custom/bulk_delete/${this.key}`
              : `/data/${this.key}/bulk_delete`, { ids });
          this.toast(
            I18N.t("tbl.deletedOk").replace("{n}", res.deleted), "success");
          this.selected.clear();
          this.selected = new Set();
          this.confirm = null;
          await this.reload();
          this.bumpCounts();
          if (snapshots.length) {
            this.pushUndo({
              label: "delete",
              run: async () => {
                for (const snap of snapshots) {
                  await API.post(this.apiBase(), { data: snap });
                }
              },
            });
          }
        } catch (e) {
          Toast.show(e.message, "error");
        } finally {
          this.confirmBusy = false;
        }
      },

      /* ── инлайн-редактирование ── */
      startEdit(row, col) {
        if (col.type === "Медиа" || col.type === "Фото") return;
        clearTimeout(this._pvTimer);
        this.closePreview();
        this.editing = {
          id: row.id, col: col.name,
          value: this.cell(row, col),
        };
        this.$nextTick(() => {
          const el = document.querySelector(".cell-input");
          if (el) { el.focus(); el.select(); }
        });
      },
      async saveInline() {
        const e = this.editing;
        if (!e) return;
        this.editing = null;
        const row = this.rows.find((r) => r.id === e.id);
        if (!row) return;
        const cur = row.data[e.col];
        if (String(cur === undefined || cur === null ? "" : cur)
            === e.value.trim()) return;
        const data = JSON.parse(JSON.stringify(row.data));
        const prevData = JSON.parse(JSON.stringify(row.data));
        data[e.col] = e.value.trim();
        try {
          await API.put(
            this.isCustom() ? `/custom/records/${this.key}/${e.id}`
              : `/data/${this.key}/${e.id}`, { data });
          row.data[e.col] = data[e.col];
          Toast.show(I18N.t("tbl.savedOk"), "success");
          const rid = e.id;
          this.pushUndo({
            label: "inline",
            run: async () => {
              await API.put(
            this.isCustom() ? `/custom/records/${this.key}/${rid}`
              : `/data/${this.key}/${rid}`, { data: prevData });
            },
          });
        } catch (err) {
          Toast.show(err.message, "error");
        }
      },
      cancelInline() { this.editing = null; },

      /* ── Часть 5: предпросмотр, undo, метки, дублирование ── */
      rowLabel(row) {
        if (row.data && row.data._label) return row.data._label;
        // авто-правило: просроченная строка → красная
        return this.columns.some((c) => this.isOverdue(row, c))
          ? "red" : "";
      },
      rowClick(e, row) {
        if (e.target.closest("input,button,a,select,textarea,.cell-input," +
                             ".badge,.tbl-thumb")) return;
        if (this.editing) return;
        clearTimeout(this._pvTimer);
        this._pvRow = row;
        this._pvTimer = setTimeout(() => {
          this.previewRow = this._pvRow;
        }, 250);
      },
      closePreview() {
        clearTimeout(this._pvTimer);
        this.previewRow = null;
      },
      pvFields(row) {
        return this.visibleCols.map((c) => ({
          name: c.name, type: c.type,
          value: this.cell(row, c),
          media: this.isMedia(c),
          status: this.isStatusCol(c),
          overdue: this.isOverdue(row, c),
        }));
      },
      pvEdit() {
        const r = this.previewRow;
        this.closePreview();
        if (r) this.openEdit(r);
      },
      async pvDuplicate() {
        const r = this.previewRow;
        this.closePreview();
        if (r) await this.duplicateRecord(r);
      },
      pvPanel(tab) {
        const r = this.previewRow;
        this.closePreview();
        if (r) this.openPanel(tab, r);
      },
  async setLabel(row, color) {
    const prev = row.data._label || "";
    try {
      await API.post(
        this.isCustom() ? `/custom/label/${this.key}/${row.id}`
          : `/data/${this.key}/${row.id}/label`, { color });
      if (color) row.data._label = color;
      else delete row.data._label;
      this.pushUndo({
        label: "label",
        run: async () => {
              await API.post(
            this.isCustom() ? `/custom/label/${this.key}/${row.id}`
              : `/data/${this.key}/${row.id}/label`, { color: prev });
              const r = this.rows.find((x) => x.id === row.id);
              if (r) {
                if (prev) r.data._label = prev;
                else delete r.data._label;
              }
            },
          });
        } catch (e) {
          Toast.show(e.message, "error");
        }
      },
      /* ── Часть 19: поведения плагинов ── */
      /* ── Часть 21: карточный вид ── */
      initCardMode() {
        try {
          const saved = localStorage.getItem("suot_vm_" + this.key);
          if (saved) this.cardMode = saved;
          else if (window.innerWidth < 900) this.cardMode = "cards";
        } catch (_) {}
      },
      toggleCards() {
        this.cardMode = this.cardMode === "cards" ? "table" : "cards";
        try {
          localStorage.setItem("suot_vm_" + this.key, this.cardMode);
        } catch (_) {}
      },
      cardTitle(row) {
        const c = (this.visibleCols || [])[0];
        const v = c ? (row.data || {})[c.name] : "";
        return (v && String(v).trim()) ? String(v)
          : ("#" + row.id);
      },

      /* ── Часть 23: колонки 2.0 ── */
      get dataCols() {
        const cols = this.visibleCols;
        if (!this.colOrder.length) return cols;
        return [...cols].sort((a, b) => {
          const ia = this.colOrder.indexOf(a.name);
          const ib = this.colOrder.indexOf(b.name);
          return (ia < 0 ? 999 : ia) - (ib < 0 ? 999 : ib);
        });
      },
      _cwKey() { return "suot_cw_" + this.key; },
      _coKey() { return "suot_co_" + this.key; },
      loadColPrefs() {
        try {
          this.colWidths = JSON.parse(
            localStorage.getItem(this._cwKey()) || "{}");
          this.colOrder = JSON.parse(
            localStorage.getItem(this._coKey()) || "[]");
        } catch (_) {}
      },
      colStyle(c, isTh) {
        const w = this.colWidths[c.name];
        const st = {};
        if (w) {
          st.width = w + "px";
          st.minWidth = w + "px";
        }
        const idx = this.dataCols.findIndex((x) => x.name === c.name);
        if (idx > -1 && idx < this.frozenCount) {
          st.position = "sticky";
          let left = 0;
          for (let i = 0; i < idx; i++) {
            const w2 = this.colWidths[this.dataCols[i].name];
            left += w2 || (this.dataCols[i].name.length > 8 ? 160 : 110);
          }
          st.left = left + "px";
          st.zIndex = isTh ? 3 : 2;
        }
        return st;
      },
      fzClass(c) {
        const idx = this.dataCols.findIndex((x) => x.name === c.name);
        return idx > -1 && idx < this.frozenCount ? "fz" : "";
      },
      startResize(e, c) {
        e.preventDefault();
        e.stopPropagation();
        const th = e.target.closest("th");
        const startX = e.clientX;
        const startW = th ? th.offsetWidth : 120;
        const move = (ev) => {
          const w = Math.max(56, startW + ev.clientX - startX);
          this.colWidths[c.name] = w;
          if (th) {
            th.style.width = w + "px";
            th.style.minWidth = w + "px";
          }
        };
        const up = () => {
          window.removeEventListener("mousemove", move);
          window.removeEventListener("mouseup", up);
          try {
            localStorage.setItem(this._cwKey(),
              JSON.stringify(this.colWidths));
          } catch (_) {}
          this.forceRedraw();
        };
        window.addEventListener("mousemove", move);
        window.addEventListener("mouseup", up);
      },
      onColDragStart(e, c) {
        this.dragCol = c.name;
        e.dataTransfer.effectAllowed = "move";
      },
      onColDrop(e, target) {
        e.preventDefault();
        const srcName = this.dragCol;
        this.dragCol = null;
        if (!srcName || srcName === target) return;
        const names = this.dataCols.map((x) => x.name);
        const from = names.indexOf(srcName);
        const to = names.indexOf(target);
        if (from < 0 || to < 0) return;
        names.splice(to, 0, names.splice(from, 1)[0]);
        this.colOrder = names;
        try {
          localStorage.setItem(this._coKey(), JSON.stringify(names));
        } catch (_) {}
      },
      resetColLayout() {
        this.colWidths = {};
        this.colOrder = [];
        this.frozenCount = 0;
        try {
          localStorage.removeItem(this._cwKey());
          localStorage.removeItem(this._coKey());
        } catch (_) {}
        this.forceRedraw();
        Toast.show(I18N.lang === "ru"
          ? "Раскладка колонок сброшена" : "Column layout reset",
          "success");
      },
      forceRedraw() {
        const t = this.rows;
        this.rows = [];
        this.$nextTick(() => { this.rows = t; });
      },

      /* ── Часть 23: агрегаты футера ── */
      fmtNum(n) {
        const s = (Math.round(n * 100) / 100).toString();
        const parts = s.split(".");
        parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, " ");
        return parts.join(",");
      },
      footerAgg(c) {
        const rows = this.rowsFiltered;
        if (c.type === "Число") {
          const vals = rows
            .map((r) => Number((r.data || {})[c.name]))
            .filter((v) => !isNaN(v));
          if (vals.length) {
            const sum = vals.reduce((a, b) => a + b, 0);
            const avg = sum / vals.length;
            return "Σ " + this.fmtNum(sum) + " · x̄ " + this.fmtNum(avg);
          }
          return "";
        }
        let nonEmpty = 0;
        for (const r of rows) {
          const v = (r.data || {})[c.name];
          if (v !== undefined && v !== null && String(v).trim() !== "")
            nonEmpty++;
        }
        return nonEmpty ? String(nonEmpty) : "";
      },
      footerId() {
        return I18N.lang === "ru"
          ? "Строк: " + this.rowsFiltered.length
          : "Rows: " + this.rowsFiltered.length;
      },

      /* ── Часть 23: группировка строк ── */
      rowsView() {
        if (!this.groupKey) return null;
        const map = new Map();
        for (const r of this.rowsFiltered) {
          const k = String((r.data || {})[this.groupKey] || "—");
          if (!map.has(k)) map.set(k, []);
          map.get(k).push(r);
        }
        const out = [];
        for (const [k, rows] of map) {
          const open = !this.collapsedGroups.includes(k);
          out.push({ grp: true, name: k, count: rows.length, open });
          if (open) for (const r of rows) out.push({ row: r });
        }
        return out;
      },
      displayRows() {
        if (!this.groupKey) {
          return this.rowsFiltered.map((r) => ({ row: r }));
        }
        return this.rowsView();
      },
      toggleGroup(name) {
        const i = this.collapsedGroups.indexOf(name);
        if (i > -1) this.collapsedGroups.splice(i, 1);
        else this.collapsedGroups.push(name);
      },
      setGroupKey(name) {
        this.groupKey = this.groupKey === name ? "" : name;
        this.collapsedGroups = [];
      },

      /* ── Часть 23: светофор сроков ── */
      dateClass(row, c) {
        if (c.type !== "Годен до") return "";
        const raw = String((row.data || {})[c.name] || "").trim();
        const m = /^(\d{2})\.(\d{2})\.(\d{4})/.exec(raw);
        if (!m) return "";
        const d = new Date(+m[3], +m[2] - 1, +m[1]);
        if (isNaN(d.getTime())) return "";
        const days = Math.floor((d - new Date()) / 86400000);
        if (days < 0) return "dt-over";
        if (days <= 30) return "dt-warn";
        return "dt-ok";
      },

      /* ── Часть 23: комментарии к ячейке ── */
      cmtOf(row, c) {
        return (row.data || {})["_cmt_" + c.name] || "";
      },
      openCellComment(row, c) {
        this.cellCmt = { rowId: row.id, col: c.name,
          text: this.cmtOf(row, c) };
      },
      async saveCellComment() {
        const cm = this.cellCmt;
        if (!cm) return;
        const row = this.rows.find((r) => r.id === cm.rowId);
        if (!row) { this.cellCmt = null; return; }
        const data = Object.assign({}, row.data || {});
        if (cm.text.trim()) data["_cmt_" + cm.col] = cm.text.trim();
        else delete data["_cmt_" + cm.col];
        try {
          await API.put(
            this.isCustom()
              ? "/custom/records/" + this.key + "/" + cm.rowId
              : "/data/" + this.key + "/" + cm.rowId,
            { data: data });
          row.data = data;
          Toast.show(I18N.t("tbl.savedOk"), "success");
        } catch (e) {
          Toast.show(e.message, "error");
        }
        this.cellCmt = null;
      },

      /* ── Часть 21: печать текущего вида ── */      async printList() {
        if (this._printBusy) return;
        this._printBusy = true;
        const cols = (this.visibleCols || []).map((c) => c.name);
        if (!cols.length) {
          Toast.show(I18N.lang === "ru" ? "Нет колонок" : "No columns",
            "error");
          this._printBusy = false;
          return;
        }
        const rows = this.rowsFiltered.map((r) =>
          cols.map((c) => {
            const v = (r.data || {})[c];
            return v === undefined || v === null ? "" : String(v);
          }));
        try {
          const tok = localStorage.getItem("suot_token") ||
                      sessionStorage.getItem("suot_token_session") || "";
          const res = await fetch("/api/print/list-pdf", {
            method: "POST",
            headers: { "Authorization": "Bearer " + tok,
                       "Content-Type": "application/json" },
            body: JSON.stringify({
              title: Alpine.store("tabs").labelFor(this.key),
              columns: cols, rows,
              orientation: cols.length > 6 ? "landscape" : "portrait",
              watermark_text: window.SUOT_WATERMARK || "",
            }),
          });
          if (!res.ok) throw new Error("HTTP " + res.status);
          const blob = await res.blob();
          const a = document.createElement("a");
          a.href = URL.createObjectURL(blob);
          a.download = "print.pdf";
          document.body.appendChild(a);
          a.click();
          a.remove();
          URL.revokeObjectURL(a.href);
          Sounds.play("success");
        } catch (e) {
          Toast.show(e.message, "error");
          Sounds.play("error");
        } finally {
          this._printBusy = false;
        }
      },
      async pluginAction(behavior) {
        if (behavior === "overdue_label") {
          const ids = [...(this.selected || [])];
          if (!ids.length) {
            Toast.show(I18N.lang === "ru"
              ? "Сначала выберите строки" : "Select rows first",
              "error");
            return;
          }
          try {
            for (const id of ids) {
              await API.post(
                this.isCustom()
                  ? `/custom/label/${this.key}/${id}`
                  : `/data/${this.key}/${id}/label`,
                { color: "red" });
              const r = this.rowsFiltered.find((x) => x.id === id);
              if (r) r.data._label = "red";
            }
            Toast.show(I18N.lang === "ru"
              ? `Метка «Просрочка»: ${ids.length}`
              : `Overdue label: ${ids.length}`, "success");
            Sounds.play("success");
          } catch (e) {
            Toast.show(e.message, "error");
            Sounds.play("error");
          }
          return;
        }
        if (behavior === "copy_tsv") {
          const cols = this.visibleCols || [];
          const chosen = (this.selected && this.selected.size)
            ? this.rowsFiltered.filter(
                (r) => this.selected.has(r.id))
            : this.rowsFiltered;
          const head = cols.map((c) => c.name).join("\t");
          const lines = chosen.map((r) =>
            cols.map((c) => {
              const v = (r.data || {})[c.name];
              return String(v === undefined || v === null
                ? "" : v);
            }).join("\t"));
          const text = [head].concat(lines).join("\n");
          let ok = false;
          try {
            await navigator.clipboard.writeText(text);
            ok = true;
          } catch (_) {}
          if (!ok) {
            try {
              const ta = document.createElement("textarea");
              ta.value = text;
              ta.style.position = "fixed";
              ta.style.opacity = "0";
              document.body.appendChild(ta);
              ta.select();
              ok = document.execCommand("copy");
              ta.remove();
            } catch (_) { ok = false; }
          }
          if (ok) {
            Toast.show(I18N.lang === "ru"
              ? `Скопировано строк: ${chosen.length}`
              : `Copied rows: ${chosen.length}`, "success");
            Sounds.play("success");
          } else {
            Toast.show(I18N.lang === "ru"
              ? "Не удалось скопировать" : "Copy failed", "error");
          }
          return;
        }
        Toast.show(I18N.lang === "ru"
          ? `Плагин: неизвестное поведение «${behavior}»`
          : `Unknown behavior: ${behavior}`, "error");
      },
      async duplicateRecord(row) {
        try {
          const res = await API.post(
            this.isCustom() ? `/custom/duplicate/${this.key}/${row.id}`
              : `/data/${this.key}/${row.id}/duplicate`);
          this.toast(I18N.t("dup.done")
            .replace("{id}", res.id), "success");
          await this.reload();
          this.bumpCounts();
          this.pushUndo({
            label: "duplicate",
            run: async () => {
              await API.del(
            this.isCustom() ? `/custom/records/${this.key}/${res.id}`
              : `/data/${this.key}/${res.id}`);
            },
          });
        } catch (e) {
          Toast.show(e.message, "error");
        }
      },

      /* ── Перенос записей в другую таблицу ── */
      get transferTargets() {
        const tabs = Alpine.store("tabs");
        const out = [];
        for (const k of tabs.TABLE_KEYS)
          if (k !== this.key)
            out.push({ key: k, label: tabs.labelFor(k) });
        try {
          const st = Alpine.store("custom");
          if (st) for (const t of st.list)
            if (t.key !== this.key)
              out.push({ key: t.key, label: t.label });
        } catch (_) {}
        return out;
      },
      openTransfer() {
        if (!this.selected.size) return;
        this.transferTo = this.transferTargets.length
          ? this.transferTargets[0].key : "";
        this.transferMove = true;
        this.transferOpen = true;
      },
      async doTransfer() {
        if (!this.transferTo) return;
        try {
          const res = await API.post("/custom/transfer",
            { from_key: this.key, to_key: this.transferTo,
              ids: [...this.selected], move: this.transferMove });
          Toast.show(I18N.t("tr.moved").replace("{n}", res.moved),
                     "success");
          this.transferOpen = false;
          this.clearSelection();
          await this.reload();
          this.bumpCounts();
        } catch (e) {
          Toast.show(e.message, "error");
        }
      },

      /* ── Undo (Ctrl+Z) ── */
      pushUndo(entry) {
        this.undoStack.push(entry);
        if (this.undoStack.length > 25) this.undoStack.shift();
      },
      async undo() {
        const entry = this.undoStack.pop();
        if (!entry) {
          Toast.show(I18N.t("undo.empty"));
          return;
        }
        try {
          await entry.run();
          Toast.show(I18N.t("undo.done"), "success");
          await this.reload();
        } catch (e) {
          Toast.show(e.message, "error");
        }
      },

      /* ── Массовое редактирование поля ── */
      openBulkEdit() {
        if (!this.selected.size) return;
        this.beField = this.visibleCols.length
          ? this.visibleCols[0].name : "";
        this.beValue = "";
        this.bulkEditOpen = true;
      },
      async applyBulkEdit() {
        if (!this.beField) return;
        const ids = [...this.selected];
        const prevs = [];
        for (const id of ids) {
          const r = this.rows.find((x) => x.id === id);
          if (r) prevs.push({ id, data: JSON.parse(
            JSON.stringify(r.data)) });
        }
        try {
          const res = await API.post(
            this.isCustom() ? `/custom/bulk_edit/${this.key}`
              : `/data/${this.key}/bulk_edit`,
            { ids, field: this.beField, value: this.beValue });
          this.toast(I18N.t("be.done")
            .replace("{n}", res.updated), "success");
          this.bulkEditOpen = false;
          this.clearSelection();
          await this.reload();
          this.bumpCounts();
          if (prevs.length) {
            this.pushUndo({
              label: "bulkEdit",
              run: async () => {
                for (const p of prevs) {
                  await API.put(
            this.isCustom() ? `/custom/records/${this.key}/${p.id}`
              : `/data/${this.key}/${p.id}`, { data: p.data });
                }
              },
            });
          }
        } catch (e) {
          Toast.show(e.message, "error");
        }
      },

      /* ── Черновики формы добавления ── */
      _draftKey() { return "suot_draft_" + this.key; },
      markDraft() { this.draftDirty = true; },
      requestCloseDialog() {
        if (this.dialog && this.dialog.mode === "add" && this.draftDirty) {
          /* сначала закрываем диалог, форма уходит в stash —
             избегаем одновременного маунта двух оверлеев */
          this._pendingDraft = JSON.parse(JSON.stringify(
            this.dialog.form));
          this.dialog = null;
          this.draftConfirm = true;
          return;
        }
        this.dialog = null;
        this.draftDirty = false;
      },
      saveDraftAndClose() {
        if (this._pendingDraft) {
          const slim = {};
          for (const c of this.visibleCols)
            slim[c.name] = this._pendingDraft[c.name] || "";
          localStorage.setItem(this._draftKey(), JSON.stringify(slim));
        }
        this._pendingDraft = null;
        this.draftConfirm = null;
        this.draftDirty = false;
        try { Alpine.store("tabs").touch(); } catch (_) {}
        Toast.show(I18N.t("dr.cleared"));
      },
      discardDraftAndClose() {
        localStorage.removeItem(this._draftKey());
        this._pendingDraft = null;
        this.draftConfirm = null;
        this.draftDirty = false;
        try { Alpine.store("tabs").touch(); } catch (_) {}
      },

      /* ── Панель записи: заметки / связи / история ── */
      async openPanel(tab, row) {
        this.panel = { tab, rowId: row.id, items: [],
                       noteTitle: "", noteContent: "",
                       linkTable: "employees", linkId: "" };
        await this.loadPanel();
      },
      async loadPanel() {
        const p = this.panel;
        if (!p) return;
        const base = `/record/${this.key}/${p.rowId}`;
        try {
          if (p.tab === "notes")
            p.items = (await API.get(base + "/notes")).items;
          else if (p.tab === "links") {
            const res = await API.get(base + "/links");
            p.items = res.items;
          } else if (p.tab === "history")
            p.items = (await API.get(base + "/history")).items;
        } catch (e) {
          Toast.show(e.message, "error");
        }
      },
      setPanelTab(tab) {
        if (this.panel) { this.panel.tab = tab; this.loadPanel(); }
      },
      async addNote() {
        const p = this.panel;
        if (!p || (!p.noteTitle.trim() && !p.noteContent.trim())) return;
        try {
          await API.post(`/record/${this.key}/${p.rowId}/notes`,
            { title: p.noteTitle, content: p.noteContent });
          p.noteTitle = "";
          p.noteContent = "";
          await this.loadPanel();
        } catch (e) {
          Toast.show(e.message, "error");
        }
      },
      async delNote(id) {
        try {
          await API.del("/record/notes/" + id);
          await this.loadPanel();
        } catch (e) {
          Toast.show(e.message, "error");
        }
      },
      async addLink() {
        const p = this.panel;
        if (!p || !p.linkId) return;
        try {
          await API.post(`/record/${this.key}/${p.rowId}/links`,
            { target_table: p.linkTable, target_id: Number(p.linkId),
              link_type: "related" });
          p.linkId = "";
          await this.loadPanel();
        } catch (e) {
          Toast.show(e.message, "error");
        }
      },
      async delLink(id) {
        try {
          await API.del("/record/links/" + id);
          await this.loadPanel();
        } catch (e) {
          Toast.show(e.message, "error");
        }
      },
      async rollbackHistory(h) {
        try {
          await API.post(
            `/record/${this.key}/${this.panel.rowId}/history/${h.id}/rollback`);
          Toast.show(I18N.t("rp.rollbackOk"), "success");
          await this.loadPanel();
          await this.reload();
        } catch (e) {
          Toast.show(e.message, "error");
        }
      },

      /* ── демо и экспорт ── */
      async seedDemo() {
        if (this.seeding) return;
        this.seeding = true;
        try {
          await API.post("/demo/seed", { tables: [this.key] });
          Toast.show(I18N.t("demo.seededOk"), "success");
          await this.reload(false);
          this.bumpCounts();
        } catch (e) {
          Toast.show(e.message, "error");
        } finally {
          this.seeding = false;
        }
      },
      exportCsv(selectedOnly = false) {
        const rows = selectedOnly
          ? this.rows.filter((r) => this.selected.has(r.id))
          : this.rows;
        if (!rows.length) return;
        const cols = this.visibleCols;
        const esc = (v) => '"' + String(v === undefined || v === null ? "" : v).replace(/"/g, '""') + '"';
        const head = ["ID", ...cols.map((c) => c.name)].map(esc).join(";");
        const lines = rows.map((r) =>
          [esc(r.id), ...cols.map((c) => esc(this.cell(r, c)))].join(";"));
        const blob = new Blob(["\ufeff" + head + "\n" + lines.join("\n")],
          { type: "text/csv;charset=utf-8" });
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = `${this.key}_${new Date().toISOString().slice(0, 10)}.csv`;
        a.click();
        URL.revokeObjectURL(a.href);
      },
      changePageSize() {
        localStorage.setItem("suot_pagesize", this.pageSize);
        this.page = 1;
        this.reload();
      },
      toast(msg, type) { Toast.show(msg, type); },
    };

    function col_is_number(c) { return NUM_TYPES.has(c.type); }
  };

  /* Глобальные тосты — единый стек поверх всех компонентов */
  window.Toast = {
    show(msg, type = "") {
      document.dispatchEvent(new CustomEvent("suot-toast",
        { detail: { msg, type }, bubbles: true }));
    },
  };
})();
