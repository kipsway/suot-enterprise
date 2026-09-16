/* SUOT Neo — командная палитра Ctrl+K */
(function () {
  window.cmdPalette = function () {
    return {
      open: false,
      query: "",
      idx: 0,
      dataResults: [],

      icons: window.ICONS,
      t: (k) => I18N.t(k),

      _theme() {
        const th = document.body.getAttribute("data-theme");
        return th || localStorage.getItem("suot_theme") || "dark";
      },

      get filtered() {
        const q = this.query.trim().toLowerCase();
        const all = [...this.buildItems(), ...this.dataResults];
        if (!q) return all;
        return all.filter((it) =>
          it.label.toLowerCase().includes(q) ||
          (it.hint || "").toLowerCase().includes(q));
      },
      async doSearch(q) {
        if (!q || q.length < 2) { this.dataResults = []; return; }
        try {
          const res = await API.get("/search?q=" + encodeURIComponent(q));
          this.dataResults = res.results.slice(0, 8).map((r) => ({
            id: "data:" + r.table + ":" + r.id,
            group: this.t("pal.tables"),
            label: r.title || ("#" + r.id),
            icon: ICONS.search,
            run: () => this.openData(r),
          }));
        } catch (_) { this.dataResults = []; }
      },

      openData(r) {
        const tabs = Alpine.store("tabs");
        if (r.table === "npa") { tabs.openNpa(); return; }
        tabs.open(r.table);
      },

      buildItems() {
        const t = (k) => I18N.t(k);
        const tabs = Alpine.store("tabs");
        const out = [];
        for (const key of tabs.TABLE_KEYS) {
          out.push({
            id: "tab:" + key,
            group: t("pal.tables"),
            label: tabs.labelFor(key),
            icon: ICONS.database,
            run: () => tabs.open(key),
          });
        }
        out.push({
          id: "tab:all", group: t("pal.tables"),
          label: tabs.labelFor("all"),
          icon: ICONS.layers,
          run: () => tabs.open("all"),
        });
        out.push(
          {
            id: "act:wel", group: t("pal.actions"),
            label: t("pal.openWelcome"), icon: ICONS.home,
            run: () => tabs.openWelcome(),
          },
          {
            id: "act:calendar", group: t("pal.actions"),
            label: t("nav.calendar"), icon: ICONS.calendar,
            run: () => tabs.openCalendar(),
          },
          {
            id: "act:npa", group: t("pal.actions"),
            label: t("nav.legalBase"), icon: ICONS.bookmark,
            run: () => tabs.openNpa(),
          },
          {
            id: "act:theme", group: t("pal.actions"),
            label: this._theme() === "dark"
              ? t("nav.lightTheme") : t("nav.darkTheme"),
            icon: this._theme() === "dark" ? ICONS.sun : ICONS.moon,
            run: () => document.body.dispatchEvent(
              new CustomEvent("suot-toggle-theme", { bubbles: true })),
          },
          {
            id: "act:logout", group: t("pal.actions"),
            label: t("nav.logout"), icon: ICONS.logout,
            run: () => document.dispatchEvent(
              new CustomEvent("suot-logout", { bubbles: true })),
          },
        );
        out.push(...(window.PLUGIN_COMMANDS || []));
        return out;
      },

      show(startQuery) {
        this.query = startQuery || "";
        this.idx = 0;
        this.dataResults = [];
        this.open = true;
        setTimeout(() => {
          const el = document.querySelector(".palette-input");
          if (el) { el.focus(); el.select(); }
        }, 30);
      },
      hide() { this.open = false; },
      move(d) {
        const n = this.filtered.length;
        if (!n) return;
        this.idx = (this.idx + d + n) % n;
        this.$nextTick(() => {
          const el = document.querySelector(".palette-item.active");
          if (el) el.scrollIntoView({ block: "nearest" });
        });
      },
      runSelected() {
        const it = this.filtered[this.idx];
        if (!it) return;
        this.hide();
        it.run();
      },
    };
  };
})();
